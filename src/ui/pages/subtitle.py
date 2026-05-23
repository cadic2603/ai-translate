"""Generate Subtitle page UI for the AI Translate application.

Combines file selection and subtitle history into a unified interface.
A single shared FileDropWidget is reparented between two stacked views:
  - View 0 (default): drop area (full) + history table
  - View 1 (files selected): drop area (compact) + file selection list
"""

import logging
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from src.constants import (
    DROP_AREA_HEIGHT,
    HEIGHT_CONTROL,
    SUPPORTED_MEDIA,
    style_delete_button,
    style_primary_button,
    style_warning_button,
    tr,
)
from src.constants.history import (
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_GENERATING,
    STATUS_PENDING,
)
from src.constants.settings import (
    SETTING_GOOGLE_STT_MODEL,
    SETTING_LAST_SUBTITLE_FORMAT,
    SETTING_LAST_SUBTITLE_LANGUAGE,
    SETTING_SUBTITLE_AUTO_REMOVE,
    SETTING_SUBTITLE_STT_METHOD,
    SETTING_WHISPER_MODEL,
    STT_WHISPER,
)
from src.core.database import (
    add_subtitle_entry,
    delete_subtitle_entry,
    update_subtitle_status,
)
from src.ui.components import (
    FileDropWidget,
    FileItemWidget,
    create_page_container,
    style_file_count_badge,
    style_section_label,
)
from src.ui.dialogs import (
    CustomConfirmDialog,
    CustomMessageDialog,
    SourceLanguageDialog,
    require_setup,
)
from src.ui.pages.subtitle_history import SubtitleHistoryPage
from src.utils.config_manager import check_google_cloud_setup, load_setting
from src.utils.file_utils import format_file_size
from src.utils.path_manager import generate_subtitle_output_path
from src.utils.subtitle_utils import parse_subtitle, serialize_subtitle

# Maximum number of files accepted per drop/browse to keep the UI responsive.
# Users are notified when the cap is hit (prevents silent truncation).
_MAX_FILES_PER_DROP = 100

logger = logging.getLogger("subtitle")


def _srt_time_to_ass(ts: str) -> str:
    """Converts an SRT timestamp ``HH:MM:SS,mmm`` to ASS ``H:MM:SS.cc``.

    ASS uses 1-digit hours, ``.`` as a separator, and centiseconds (cc)
    instead of milliseconds.
    """
    # Tolerant parsing: both "," and "." decimal separators accepted.
    normalized = ts.replace(",", ".").strip()
    try:
        hms, frac = normalized.split(".", 1)
    except ValueError:
        hms, frac = normalized, "000"
    h, m, s = hms.split(":")
    cs = (frac + "000")[:3][:2]  # first 2 digits → centiseconds
    return f"{int(h)}:{int(m):02d}:{int(s):02d}.{cs}"


def _build_ass_template(entries: list) -> list[str]:
    """Builds a minimal ASS/SSA file as a list of preserved_lines.

    Returns the list shape that ``serialize_ass`` expects: header lines plus
    one ``Dialogue:`` line per entry with a ``__SUB_N__`` placeholder that
    ``serialize_ass`` replaces with the entry's text.
    """
    lines: list[str] = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        (
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
            "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
            "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding"
        ),
        (
            "Style: Default,Arial,48,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,"
            "0,0,0,0,100,100,0,0,1,2,2,2,10,10,10,1"
        ),
        "",
        "[Events]",
        (
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
            "MarginV, Effect, Text"
        ),
    ]
    for entry in entries:
        start = _srt_time_to_ass(entry.start)
        end = _srt_time_to_ass(entry.end)
        lines.append(
            f"Dialogue: 0,{start},{end},Default,,0,0,0,,__SUB_{entry.index}__",
        )
    return lines


def _convert_subtitle_format(srt_text: str, target_ext: str) -> str:
    """Converts SRT text to any supported subtitle format.

    The STT engine always produces SRT. This parses it and re-serialises to
    the requested extension so ``.ass``, ``.ssa``, ``.vtt``, and ``.csv``
    produce valid files instead of SRT content with a misleading extension.
    CSV is a non-subtitle export for spreadsheet/analysis workflows — it
    drops the playback semantics but preserves the cue boundaries so the
    data round-trips into other tools.

    Args:
        srt_text: Raw SRT-formatted subtitle text.
        target_ext: Target extension (``.srt``, ``.vtt``, ``.ass``, ``.ssa``,
            ``.csv``).

    Returns:
        Subtitle text in the target format. Falls back to the original SRT
        when parsing fails or when the target extension is unsupported.
    """
    if target_ext == ".srt":
        return srt_text

    try:
        entries, _src_fmt_data = parse_subtitle(srt_text, ".srt")
    except ValueError:
        # Parser didn't recognise the SRT — keep original to avoid data loss.
        logger.warning("Could not parse generated SRT; emitting raw text.")
        return srt_text

    # CSV is a non-subtitle export.  Short-circuits the
    # serialize_subtitle path because that path is media-player-oriented
    # (expects SRT/VTT/ASS-style timing semantics).
    if target_ext == ".csv":
        # 4-column CSV: ``index, start, end, text``.  ``csv`` module
        # handles RFC 4180 quoting so commas / quotes / newlines inside
        # cue text don't break the spreadsheet import.  CRLF line
        # terminators match the RFC default; readers normalise on input.
        import csv  # noqa: PLC0415
        import io  # noqa: PLC0415

        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator="\r\n")
        writer.writerow(["index", "start", "end", "text"])
        for entry in entries:
            writer.writerow([entry.index, entry.start, entry.end, entry.text])
        return buf.getvalue()

    fmt_data: object
    if target_ext == ".vtt":
        # VTT requires ``HH:MM:SS.mmm`` timestamps (dot, not comma) and a
        # ``WEBVTT`` header. parse_srt keeps raw comma-separated timestamps.
        for entry in entries:
            entry.start = entry.start.replace(",", ".")
            entry.end = entry.end.replace(",", ".")
        fmt_data = "WEBVTT\n"
    elif target_ext in (".ass", ".ssa"):
        # ASS/SSA has no round-trippable form from SRT — synthesise a
        # minimal script template with placeholder Dialogue lines.
        fmt_data = _build_ass_template(entries)
    else:
        fmt_data = None

    try:
        return serialize_subtitle(entries, fmt_data, target_ext)
    except ValueError:
        logger.warning(
            "Unsupported target subtitle format %r; emitting SRT.",
            target_ext,
        )
        return srt_text


# Stacked widget indices
_VIEW_HISTORY = 0
_VIEW_FILES = 1

# Supported media file filter for QFileDialog
_MEDIA_FILTER = (
    f"Media Files ({' '.join('*' + ext for ext in SUPPORTED_MEDIA)});;All Files (*)"
)


# ── Background subtitle worker ──────────────────────────────────────────────


class _SubtitleWorker(QThread):
    """Generates subtitles from audio/video in a background thread."""

    finished_ok = Signal(list)  # list[(entry_id, file_path, srt_text)]
    _is_any_worker_running = False  # Class-level flag

    def __init__(  # noqa: PLR0913
        self,
        tasks: list[tuple[int, str]],
        src_lang: str,
        stt_method: str = "",
        model_size: str = "base",
        google_model: str = "default",
        target_lang: str = "",
        llm_provider: str | None = None,
        llm_model: str | None = None,
    ) -> None:
        super().__init__()
        self._tasks = tasks  # [(entry_id, file_path), ...]
        self._src_lang = src_lang
        self._stt_method = stt_method
        self._model_size = model_size
        self._google_model = google_model
        self._target_lang = target_lang
        self._llm_provider = llm_provider
        self._llm_model = llm_model
        self._is_running = True

    @classmethod
    def is_busy(cls) -> bool:
        """Checks if a subtitle worker is already running."""
        return cls._is_any_worker_running

    def stop(self) -> None:
        """Requests the worker to stop after the current file."""
        self._is_running = False

    def run(self) -> None:
        """Processes each file with STT, optionally translates, emits results."""
        if _SubtitleWorker._is_any_worker_running:
            return
        _SubtitleWorker._is_any_worker_running = True

        from src.core.speech_engine import transcribe_audio  # noqa: PLC0415

        results: list[tuple[int, str, str]] = []
        # Tracks which tasks the loop actually reached. Anything missing at
        # teardown was skipped (user hit Stop before its turn) and needs an
        # explicit terminal status so it doesn't sit as Pending forever.
        processed_ids: set[int] = set()

        try:
            for entry_id, file_path in self._tasks:
                if not self._is_running:
                    break
                processed_ids.add(entry_id)
                update_subtitle_status(entry_id, STATUS_GENERATING)

                try:
                    srt_text = transcribe_audio(
                        file_path,
                        src_lang=self._src_lang,
                        stt_method=self._stt_method,
                        model_size=self._model_size,
                        google_model=self._google_model,
                        is_cancelled=lambda: not self._is_running,
                    )

                    # Auto-translate if target language is set
                    if self._target_lang and srt_text.strip():
                        srt_text = self._translate_srt(srt_text)

                    results.append((entry_id, file_path, srt_text))
                except Exception as exc:
                    logger.error(
                        "Subtitle generation failed for task %d: %s",
                        entry_id,
                        exc,
                    )
                    update_subtitle_status(
                        entry_id,
                        STATUS_FAILED,
                        error_message=str(exc),
                    )
        except Exception:
            logger.exception("Subtitle worker crashed")
        finally:
            try:
                for entry_id, _ in self._tasks:
                    if entry_id not in processed_ids:
                        update_subtitle_status(
                            entry_id,
                            STATUS_FAILED,
                            error_message="CANCELLED",
                        )
            except Exception:
                logger.exception("Failed to mark cancelled subtitle tasks")
            _SubtitleWorker._is_any_worker_running = False
            self.finished_ok.emit(results)

    def _translate_srt(self, srt_text: str) -> str:
        """Translates SRT subtitle text to the target language.

        Parses entries, translates text via LLM, rebuilds SRT.

        Args:
            srt_text: Raw SRT-formatted subtitle text.

        Returns:
            Translated SRT text.
        """
        from src.core.database import (  # noqa: PLC0415
            get_active_glossary_sets,
            get_glossary_entries,
        )
        from src.core.llm_engine import translate_batch  # noqa: PLC0415
        from src.utils.subtitle_utils import (  # noqa: PLC0415
            parse_subtitle,
            serialize_subtitle,
        )

        entries, fmt_data = parse_subtitle(srt_text, ".srt")
        if not entries:
            return srt_text

        # Fetch active glossary entries
        glossary: list[tuple[int, str, str]] = []
        for set_id, _ in get_active_glossary_sets():
            glossary.extend(get_glossary_entries(set_id))

        # Extract text for translation
        texts = [e.text for e in entries]
        src = self._src_lang or "Auto"

        # Translate
        llm_provider = getattr(self, "_llm_provider", None)
        llm_model = getattr(self, "_llm_model", None)
        translate_kwargs = {
            "target_lang": self._target_lang,
            "src_lang": src,
            "glossary_entries": glossary or None,
            "cancel_check": lambda: not self._is_running,
        }
        if llm_provider or llm_model:
            translate_kwargs["provider"] = llm_provider
            translate_kwargs["model"] = llm_model
        translated = translate_batch(texts, **translate_kwargs)

        if translated and len(translated) == len(entries):
            for entry, new_text in zip(entries, translated, strict=True):
                entry.text = new_text

        return serialize_subtitle(entries, fmt_data, ".srt")


# ── Main page ────────────────────────────────────────────────────────────────


class SubtitlePage(QWidget):
    """Unified page for subtitle generation and history management.

    Layout (QStackedWidget with two views sharing one FileDropWidget):
        - View 0: drop area (full) + history table
        - View 1: drop area (compact) + file selection list
    """

    def __init__(self, window: QMainWindow, parent: QWidget | None = None) -> None:
        """Initializes the SubtitlePage."""
        super().__init__(parent)
        self.window_context = window
        self.selected_files: list[str] = []
        self._worker: _SubtitleWorker | None = None
        self._pending_tasks: list[tuple[int, str]] = []
        # Reset entries stuck in "Generating" from a previous crash
        from src.core.database import reset_stuck_subtitle_entries  # noqa: PLC0415

        reset_stuck_subtitle_entries()
        self._setup_ui()
        self._update_ui_state()

        # Ensure the STT/translate thread doesn't outlive the application.
        # Whisper can block inside model inference for many seconds; leaving
        # a zombie QThread at shutdown risks torn-down-widget crashes.
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._stop_all_workers)

    def _stop_all_workers(self) -> None:
        """Requests the worker to stop and waits briefly before shutdown."""
        if self._worker is not None:
            self._worker.stop()
            # Bounded wait — Whisper cannot be interrupted mid-inference, so
            # we give it a short grace period and let the OS finish the job
            # rather than blocking app exit indefinitely.
            self._worker.wait(2000)
            self._worker = None

    # ------------------------------------------------------------------
    # UI Setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        """Builds the full page layout."""
        page_container, content_layout = create_page_container(
            tr("page.subtitle"),
            tr_key="page.subtitle",
        )
        content_layout.setSpacing(15)
        content_layout.setContentsMargins(20, 10, 20, 10)

        # The surrounding navigation already renders a header for this page.
        page_container.header_label.setVisible(False)

        # Shared drop area (reparented between views on switch)
        self.drop_area = FileDropWidget()
        self.drop_area.setFixedHeight(DROP_AREA_HEIGHT)
        self.drop_area.files_dropped.connect(self._handle_files_dropped)
        # Override supported-formats label to show media formats
        media_formats = ", ".join(ext.lstrip(".") for ext in sorted(SUPPORTED_MEDIA))
        self.drop_area.supported_label.setText(
            tr("drop.supported", formats=media_formats)
        )

        # --- View 0: drop area + history table ---
        self.history_wrapper = QWidget()
        self.history_wrapper_layout = QVBoxLayout(self.history_wrapper)
        self.history_wrapper_layout.setContentsMargins(0, 0, 0, 0)
        self.history_wrapper_layout.setSpacing(15)

        self.history_view = SubtitleHistoryPage()
        self.history_view.re_generate_requested.connect(self._handle_re_generate)
        self._clean_history_view()
        self.history_wrapper_layout.addWidget(self.drop_area)
        self.history_wrapper_layout.addWidget(self.history_view, 1)

        # --- View 1: drop area + file selection list ---
        self.files_wrapper = QWidget()
        self.files_wrapper_layout = QVBoxLayout(self.files_wrapper)
        self.files_wrapper_layout.setContentsMargins(0, 0, 0, 0)
        self.files_wrapper_layout.setSpacing(10)

        self.file_list_section = self._create_file_list_section()
        self.files_wrapper_layout.addWidget(self.file_list_section, 1)

        # --- Stacked widget ---
        self.stack = QStackedWidget()
        self.stack.addWidget(self.history_wrapper)
        self.stack.addWidget(self.files_wrapper)
        self.stack.setCurrentIndex(_VIEW_HISTORY)
        content_layout.addWidget(self.stack, 1)

        # Root layout
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(page_container)

        # Primary-action shortcut; rebinding is driven by the central registry.
        from src.constants.shortcuts import (  # noqa: PLC0415
            get_shortcut,
            shortcuts_changed,
        )

        self._generate_shortcut = QShortcut(
            QKeySequence(get_shortcut("subtitle.generate")),
            self,
        )
        self._generate_shortcut.activated.connect(self._handle_primary_shortcut)

        self._focus_search_shortcut = QShortcut(
            QKeySequence(get_shortcut("common.focus_search")),
            self,
        )
        self._focus_search_shortcut.activated.connect(
            self.history_view.search_input.setFocus,
        )

        def _sync_shortcuts() -> None:
            self._generate_shortcut.setKey(
                QKeySequence(get_shortcut("subtitle.generate")),
            )
            self._focus_search_shortcut.setKey(
                QKeySequence(get_shortcut("common.focus_search")),
            )

        shortcuts_changed.connect(_sync_shortcuts)
        self._sync_shortcuts = _sync_shortcuts

    def _create_file_list_section(self) -> QWidget:  # noqa: PLR0915
        """Creates the file selection header and scrollable file list."""
        section = QWidget()
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # Header row: badge + label + buttons
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)

        self.files_badge = QLabel("0")
        self.files_badge.setFixedSize(24, 24)
        self.files_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.files_badge.setStyleSheet(style_file_count_badge())
        header.addWidget(self.files_badge)

        self.section_label = QLabel(tr("files.selected"))
        self.section_label.setStyleSheet(style_section_label())
        header.addWidget(self.section_label)
        header.addStretch()

        self.generate_btn = QPushButton(tr("subtitle.btn_generate"))
        self.generate_btn.setFixedHeight(HEIGHT_CONTROL)
        self.generate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.generate_btn.setStyleSheet(style_primary_button())
        self.generate_btn.setAccessibleName(tr("subtitle.btn_generate"))
        self.generate_btn.clicked.connect(self._handle_generate)
        header.addWidget(self.generate_btn)

        # Stop button — only visible while a worker is running.
        self.stop_btn = QPushButton(tr("btn.stop"))
        self.stop_btn.setFixedHeight(HEIGHT_CONTROL)
        self.stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.stop_btn.setStyleSheet(style_warning_button())
        self.stop_btn.setVisible(False)
        self.stop_btn.setAccessibleName(tr("btn.stop"))
        self.stop_btn.clicked.connect(self._handle_stop)
        header.addWidget(self.stop_btn)

        self.clear_all_btn = QPushButton(tr("btn.delete_all"))
        self.clear_all_btn.setFixedHeight(HEIGHT_CONTROL)
        self.clear_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_all_btn.setStyleSheet(style_delete_button())
        self.clear_all_btn.setAccessibleName(tr("btn.delete_all"))
        self.clear_all_btn.clicked.connect(self._handle_clear_all)
        header.addWidget(self.clear_all_btn)

        layout.addLayout(header)

        # Scrollable file item list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        self.files_vbox = QVBoxLayout(container)
        self.files_vbox.setContentsMargins(0, 0, 0, 0)
        self.files_vbox.setSpacing(10)
        self.files_vbox.addStretch()

        scroll.setWidget(container)
        layout.addWidget(scroll, 1)

        return section

    def _clean_history_view(self) -> None:
        """Removes the standalone title and tightens margins."""
        if not hasattr(self.history_view, "page"):
            return
        page_layout = self.history_view.page.layout()
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(10)
        header = getattr(self.history_view.page, "header_label", None)
        if header is not None:
            header.setVisible(False)

    # ------------------------------------------------------------------
    # Theme / language
    # ------------------------------------------------------------------

    def apply_theme(self) -> None:
        """Re-applies theme-dependent styles for this page."""
        self.files_badge.setStyleSheet(style_file_count_badge())
        self.section_label.setStyleSheet(style_section_label())
        self.generate_btn.setStyleSheet(style_primary_button())
        self.stop_btn.setStyleSheet(style_warning_button())
        self.clear_all_btn.setStyleSheet(style_delete_button())

    def apply_language(self) -> None:
        """Re-applies all translatable text for this page."""
        self.section_label.setText(tr("files.selected"))
        self.generate_btn.setText(tr("subtitle.btn_generate"))
        # Only relabel the Stop button when idle; avoid clobbering
        # "stopping…" mid-cancel.
        if self._worker is None:
            self.stop_btn.setText(tr("btn.stop"))
        self.clear_all_btn.setText(tr("btn.delete_all"))
        # Re-apply media formats label (overrides default from FileDropWidget)
        media_formats = ", ".join(ext.lstrip(".") for ext in sorted(SUPPORTED_MEDIA))
        self.drop_area.supported_label.setText(
            tr("drop.supported", formats=media_formats)
        )
        # Re-hide the history title after language update
        self._clean_history_view()

    # ------------------------------------------------------------------
    # UI State
    # ------------------------------------------------------------------

    def _update_ui_state(self) -> None:
        """Switches views and reparents the shared drop area."""
        count = len(self.selected_files)
        has_files = count > 0

        self.generate_btn.setEnabled(has_files)
        self.files_badge.setText(str(count))

        # Reparent the shared drop area into the active view
        if has_files:
            self.files_wrapper_layout.insertWidget(0, self.drop_area)
            self.drop_area.info_label.setText(tr("drop.title_more"))
            self.stack.setCurrentIndex(_VIEW_FILES)
        else:
            self.history_wrapper_layout.insertWidget(0, self.drop_area)
            self.drop_area.info_label.setText(tr("drop.title"))
            self.stack.setCurrentIndex(_VIEW_HISTORY)

    # ------------------------------------------------------------------
    # File Handling
    # ------------------------------------------------------------------

    def _walk_dropped_paths(
        self,
        files: list[str],
    ) -> tuple[list[Path], list[str], bool]:
        """Walks directories and collects up to ``_MAX_FILES_PER_DROP`` media files.

        Only supported-media files count toward the cap, so a directory full
        of junk (build artifacts, docs, dotfiles already filtered elsewhere)
        can't starve the cap and hide real videos/audio deeper in the tree.

        Returns a tuple of (supported_files, unsupported_names, cap_hit_flag).
        """
        supported: list[Path] = []
        unsupported: list[str] = []
        cap_hit = False

        def _cap_reached() -> bool:
            return len(supported) >= _MAX_FILES_PER_DROP

        for raw_path in files:
            if _cap_reached():
                cap_hit = True
                break
            p = Path(raw_path).resolve()
            if p.is_dir():
                for child in p.rglob("*"):
                    if any(part.startswith(".") for part in child.relative_to(p).parts):
                        continue
                    if not child.is_file():
                        continue
                    if child.suffix.lower() in SUPPORTED_MEDIA:
                        supported.append(child)
                        if _cap_reached():
                            cap_hit = True
                            break
                    else:
                        unsupported.append(child.name)
            elif p.is_file():
                if p.suffix.lower() in SUPPORTED_MEDIA:
                    supported.append(p)
                else:
                    unsupported.append(p.name)

        return supported, unsupported, cap_hit

    def _notify_drop_results(
        self,
        *,
        unsupported: list[str],
        duplicates: int,
        cap_hit: bool,
    ) -> None:
        """Shows a consolidated dialog covering skipped/duplicate/capped drops."""
        if not unsupported and not duplicates and not cap_hit:
            return

        lines: list[str] = []
        if cap_hit:
            lines.append(tr("dialog.drop_capped", count=_MAX_FILES_PER_DROP))
        if duplicates:
            lines.append(tr("dialog.drop_duplicates", count=duplicates))
        if unsupported:
            max_display = 10
            if len(unsupported) > max_display:
                extra = len(unsupported) - max_display
                display_items = unsupported[:max_display]
                display_items.append(
                    tr("dialog.drop_unsupported_more", count=extra),
                )
            else:
                display_items = unsupported
            file_list = "\n".join(f"- {n}" for n in display_items)
            lines.append(tr("dialog.unsupported_msg", files=file_list))

        CustomMessageDialog.show_message(
            self.window_context,
            tr("dialog.unsupported_files"),
            "\n\n".join(lines),
        )

    def _handle_files_dropped(self, files: list[str]) -> None:
        """Processes dropped or browsed media files and directories."""
        if not files:
            files, _ = QFileDialog.getOpenFileNames(
                self.window_context,
                tr("subtitle.select_files"),
                "",
                _MEDIA_FILTER,
            )
        if not files:
            return

        added = False
        duplicates = 0

        supported, walk_unsupported, cap_hit = self._walk_dropped_paths(files)
        unsupported: set[str] = set(walk_unsupported)

        for p in supported:
            file_path = str(p)

            # Skip empty files
            try:
                if p.stat().st_size == 0:
                    unsupported.add(f"{p.name} (Empty)")
                    continue
            except OSError:
                unsupported.add(f"{p.name} (Unreadable)")
                continue

            if file_path in self.selected_files:
                duplicates += 1
                continue

            self.selected_files.append(file_path)
            self._add_file_widget(file_path)
            added = True

        self._notify_drop_results(
            unsupported=sorted(unsupported),
            duplicates=duplicates,
            cap_hit=cap_hit,
        )

        if added:
            self._update_ui_state()

    def _add_file_widget(self, file_path: str) -> None:
        """Adds a file item widget to the list."""
        widget = FileItemWidget(file_path, format_file_size)
        widget.remove_requested.connect(
            lambda _fp=file_path, _w=widget: self._handle_remove_file(_fp, _w)
        )
        idx = self.files_vbox.count() - 1  # before stretch
        self.files_vbox.insertWidget(idx, widget)

    def _handle_remove_file(self, file_path: str, widget: FileItemWidget) -> None:
        """Removes a single file from the selection."""
        if file_path in self.selected_files:
            self.selected_files.remove(file_path)
        widget.setParent(None)
        widget.deleteLater()
        self._update_ui_state()

    def _handle_clear_all(self, *, confirm: bool = True) -> None:
        """Removes all files from the selection.

        Args:
            confirm: Ask the user to confirm the destructive action. Internal
                callers (post-generate cleanup) pass False to skip the dialog.
        """
        if (
            confirm
            and self.selected_files
            and not CustomConfirmDialog.confirm(
                self.window_context,
                tr("dialog.clear_selection_title"),
                tr(
                    "dialog.clear_selection_msg",
                    count=len(self.selected_files),
                ),
                is_danger=True,
            )
        ):
            return
        self.selected_files.clear()
        while self.files_vbox.count() > 1:
            item = self.files_vbox.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._update_ui_state()

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    def _check_requirements(self) -> bool:
        """Ensures STT prerequisites are met."""
        from src.constants.settings import STT_GOOGLE  # noqa: PLC0415

        stt_method = load_setting(SETTING_SUBTITLE_STT_METHOD, STT_WHISPER)

        # Only Google Cloud STT needs an API key
        if stt_method == STT_GOOGLE:
            return require_setup(
                self.window_context,
                check_google_cloud_setup,
                "subtitle.setup_required_title",
                "subtitle.setup_required_msg",
                2,
            )
        return True

    def _check_llm_setup(self) -> bool:
        """Ensures LLM is configured for translation."""
        from src.utils.config_manager import check_llm_setup  # noqa: PLC0415

        return require_setup(
            self.window_context,
            check_llm_setup,
            "dialog.llm_required_title",
            "dialog.llm_required_msg",
            4,
        )

    def _handle_primary_shortcut(self) -> None:
        """Dispatches Ctrl+Enter to the focused-context action.

        When the history table has focus with a selected row, re-generate
        the selected entries; otherwise fall through to the page's primary
        Generate action.
        """
        table = getattr(self.history_view, "table", None)
        if (
            table is not None
            and table.hasFocus()
            and table.selectionModel() is not None
            and table.selectionModel().hasSelection()
        ):
            self.history_view.on_re_generate()
            return
        self._handle_generate()

    def _handle_generate(self) -> None:
        """Validates setup, starts worker, clears files."""
        if not self.selected_files or self._worker is not None:
            return

        if not self._check_requirements():
            return

        # Show source language dialog (with optional target for auto-translate)
        from src.constants.settings import (  # noqa: PLC0415
            SETTING_LAST_SUBTITLE_TARGET,
            SETTING_LLM_MODEL_SUBTITLE,
        )

        src_lang, target_lang, _model_id, accepted = SourceLanguageDialog.get_selection(
            self.window_context,
            title_key="subtitle.generation_setup",
            label_key="subtitle.source_language",
            confirm_key="subtitle.btn_generate",
            setting_key=SETTING_LAST_SUBTITLE_LANGUAGE,
            show_target=True,
            target_setting_key=SETTING_LAST_SUBTITLE_TARGET,
            model_setting_key=SETTING_LLM_MODEL_SUBTITLE,
        )
        if not accepted:
            return

        # Check LLM if translation is requested
        if target_lang and not self._check_llm_setup():
            return

        stt_method = load_setting(SETTING_SUBTITLE_STT_METHOD, STT_WHISPER)
        model_size = load_setting(SETTING_WHISPER_MODEL, "base")
        google_model = load_setting(SETTING_GOOGLE_STT_MODEL, "default")

        # Create "Pending" entries upfront
        tasks: list[tuple[int, str]] = []
        for file_path in self.selected_files:
            src = Path(file_path)
            try:
                file_size = src.stat().st_size if src.exists() else 0
            except OSError:
                file_size = 0
            entry_id = add_subtitle_entry(
                file_name=src.name,
                file_size=file_size,
                source_path=file_path,
                output_path="",
                src_lang=src_lang,
                status=STATUS_PENDING,
            )
            if entry_id:
                tasks.append((entry_id, file_path))

        if not tasks:
            # Nothing queued — keep the selection so the user can retry and
            # notify them instead of silently clearing.
            CustomMessageDialog.show_message(
                self.window_context,
                tr("dialog.subtitle_queue_failed_title"),
                tr("dialog.subtitle_queue_failed_msg"),
            )
            return

        # Only clear after at least one task was successfully queued.
        self._handle_clear_all(confirm=False)
        self.history_view.refresh_history(force=True)

        self._start_worker(
            tasks,
            src_lang,
            stt_method,
            model_size,
            google_model,
            target_lang,
        )

    def _handle_stop(self) -> None:
        """Requests the running worker to stop after the current file."""
        if self._worker is None:
            return
        self._worker.stop()
        self.stop_btn.setEnabled(False)
        self.stop_btn.setText(tr("subtitle.stopping"))

    def _handle_re_generate(
        self,
        tasks: list[tuple[int, str]],
    ) -> None:
        """Re-generates subtitles for selected files."""
        if self._worker is not None:
            # A generation is already running — re-generate silently would
            # confuse users. Surface a message so they know to wait.
            CustomMessageDialog.show_message(
                self.window_context,
                tr("dialog.subtitle_busy_title"),
                tr("dialog.subtitle_busy_msg"),
            )
            return

        if not self._check_requirements():
            return

        from src.constants.settings import (  # noqa: PLC0415
            SETTING_LAST_SUBTITLE_TARGET,
            SETTING_LLM_MODEL_SUBTITLE,
        )

        src_lang, target_lang, _model_id, accepted = SourceLanguageDialog.get_selection(
            self.window_context,
            title_key="subtitle.generation_setup",
            label_key="subtitle.source_language",
            confirm_key="subtitle.btn_generate",
            setting_key=SETTING_LAST_SUBTITLE_LANGUAGE,
            show_target=True,
            target_setting_key=SETTING_LAST_SUBTITLE_TARGET,
            model_setting_key=SETTING_LLM_MODEL_SUBTITLE,
        )
        if not accepted:
            return

        if target_lang and not self._check_llm_setup():
            return

        stt_method = load_setting(SETTING_SUBTITLE_STT_METHOD, STT_WHISPER)
        model_size = load_setting(SETTING_WHISPER_MODEL, "base")
        google_model = load_setting(SETTING_GOOGLE_STT_MODEL, "default")

        # Reset existing entries to "Pending"
        for entry_id, _ in tasks:
            update_subtitle_status(entry_id, STATUS_PENDING)
        self.history_view.refresh_history(force=True)

        self._start_worker(
            tasks,
            src_lang,
            stt_method,
            model_size,
            google_model,
            target_lang,
        )

    def _start_worker(  # noqa: PLR0913
        self,
        tasks: list[tuple[int, str]],
        src_lang: str,
        stt_method: str = "",
        model_size: str = "base",
        google_model: str = "default",
        target_lang: str = "",
    ) -> None:
        """Starts the subtitle generation background worker."""
        if self._worker is not None:
            return
        self._pending_tasks = tasks

        from src.constants.settings import (  # noqa: PLC0415
            SETTING_LLM_MODEL_SUBTITLE,
        )
        from src.utils.config_manager import (  # noqa: PLC0415
            load_model_for_feature,
            parse_model_id,
        )

        selected_model = load_model_for_feature(SETTING_LLM_MODEL_SUBTITLE)
        llm_provider, llm_model = (
            parse_model_id(selected_model) if selected_model else (None, None)
        )

        self._worker = _SubtitleWorker(
            tasks,
            src_lang,
            stt_method=stt_method,
            model_size=model_size,
            google_model=google_model,
            target_lang=target_lang,
            llm_provider=llm_provider,
            llm_model=llm_model,
        )
        self._worker.finished_ok.connect(self._on_finished)
        self._worker.start()
        # Flip the header button set to show Stop instead of Generate.
        self.stop_btn.setEnabled(True)
        self.stop_btn.setText(tr("btn.stop"))
        self.stop_btn.setVisible(True)
        self.generate_btn.setVisible(False)

    def _safe_cleanup_worker(self) -> None:
        """Waits for the worker thread to finish before dropping reference."""
        if self._worker is not None:
            self._worker.wait()
            self._worker = None

    def _on_finished(self, results: list[tuple[int, str, str]]) -> None:
        """Saves subtitle files and updates DB entries."""
        self._safe_cleanup_worker()
        # Restore default header-button visibility.
        self.stop_btn.setVisible(False)
        self.generate_btn.setVisible(True)

        auto_remove = bool(load_setting(SETTING_SUBTITLE_AUTO_REMOVE, False))
        out_fmt = load_setting(SETTING_LAST_SUBTITLE_FORMAT, ".srt")

        for entry_id, file_path, srt_text in results:
            src = Path(file_path)
            out = generate_subtitle_output_path(src, ext=out_fmt)
            try:
                output_text = _convert_subtitle_format(srt_text, out_fmt)
                out.write_text(output_text, encoding="utf-8")
                if auto_remove:
                    delete_subtitle_entry(entry_id)
                else:
                    update_subtitle_status(entry_id, STATUS_DONE, output_path=str(out))
            except Exception as exc:
                logger.error("Failed to save %s: %s", out, exc)
                update_subtitle_status(entry_id, STATUS_FAILED, error_message=str(exc))

        self.history_view.refresh_history(force=True)


def create_subtitle_page(window: QMainWindow) -> QWidget:
    """Creates the Generate Subtitle page.

    Args:
        window: The main application window.

    Returns:
        QWidget: The subtitle page widget.
    """
    return SubtitlePage(window)
