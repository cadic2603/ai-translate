"""Generate Voice page UI for the AI Translate application.

Combines file selection and voice history into a unified interface.
A single shared FileDropWidget is reparented between two stacked views:
  - View 0 (default): drop area (full) + history table
  - View 1 (files selected): drop area (compact) + file selection list
"""

import logging
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QKeySequence, QShortcut, QShowEvent
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
    SUPPORTED_VOICE_INPUT,
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
    SETTING_LAST_VOICE_FORMAT,
    SETTING_VOICE_AUTO_REMOVE,
    SETTING_VOICE_TTS_METHOD,
    VOICE_TTS_EDGE,
)
from src.core.database import (
    add_voice_entry,
    delete_voice_entry,
    update_voice_status,
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
    VoiceSetupDialog,
    preflight_piper_voice,
    require_setup,
)
from src.ui.pages.voice_history import VoiceHistoryPage
from src.utils.config_manager import (
    check_elevenlabs_setup,
    check_google_cloud_setup,
    load_setting,
)
from src.utils.file_utils import format_file_size
from src.utils.path_manager import generate_voice_output_path

logger = logging.getLogger("voice")

# Stacked widget indices
_VIEW_HISTORY = 0
_VIEW_FILES = 1

# Maximum number of files accepted per drop/browse to keep the UI responsive.
# The user is notified when the cap is hit (prevents silent truncation).
_MAX_FILES_PER_DROP = 100

# File filter for QFileDialog
_VOICE_FILTER = (
    "Subtitle Files ("
    + " ".join("*" + ext for ext in SUPPORTED_VOICE_INPUT)
    + ");;All Files (*)"
)


# ── Background voice worker ────────────────────────────────────────────────


class _VoiceWorker(QThread):
    """Generates timed voice audio from subtitle files.

    Memory-safe: delegates to synthesize_timed_speech() which processes
    entries individually, writes each to a temp file, and concatenates
    via FFmpeg.
    """

    finished_ok = Signal(list)  # list[(entry_id, file_path, output_path)]
    _is_any_worker_running = False  # Class-level flag

    def __init__(  # noqa: PLR0913
        self,
        tasks: list[tuple[int, str]],  # [(entry_id, source_path), ...]
        target_lang: str,
        voice_gender: str,
        tts_method: str = "",
        audio_format: str = ".mp3",
    ) -> None:
        """Initializes the voice worker."""
        super().__init__()
        self._tasks = tasks
        self._target_lang = target_lang
        self._voice_gender = voice_gender
        self._tts_method = tts_method
        self._audio_format = audio_format
        self._is_running = True

    @classmethod
    def is_busy(cls) -> bool:
        """Checks if a voice worker is already running."""
        return cls._is_any_worker_running

    def stop(self) -> None:
        """Requests the worker to stop after the current file."""
        self._is_running = False

    def run(self) -> None:  # noqa: PLR0912 — sequential format/encode dispatch
        """Processes each file through timed TTS and emits results."""
        if _VoiceWorker._is_any_worker_running:
            return
        _VoiceWorker._is_any_worker_running = True

        from src.core.speech_engine import (  # noqa: PLC0415
            synthesize_speech,
            synthesize_timed_speech,
        )
        from src.utils.subtitle_utils import (  # noqa: PLC0415
            is_subtitle_format,
            parse_subtitle,
        )

        results: list[tuple[int, str, str]] = []
        # Tracks which tasks the loop actually reached. Anything missing at
        # teardown was skipped (user hit Stop before its turn) and needs an
        # explicit terminal status so it doesn't sit as Pending forever.
        processed_ids: set[int] = set()

        try:
            for entry_id, source_path in self._tasks:
                if not self._is_running:
                    break
                processed_ids.add(entry_id)

                update_voice_status(entry_id, STATUS_GENERATING)

                try:
                    content = Path(source_path).read_text(encoding="utf-8")
                    suffix = Path(source_path).suffix.lower()
                    out = generate_voice_output_path(
                        Path(source_path),
                        ext=self._audio_format,
                    )

                    # FLAC / OGG aren't supported by any TTS backend
                    # natively — synth produces WAV (or MP3), then we
                    # post-encode via ffmpeg.  MP3 / WAV stay on the
                    # native fast path.  Pattern mirrors LivePage's
                    # ``_finalise_audio_recording``.
                    fmt = self._audio_format.lstrip(".").lower()
                    needs_post_encode = fmt in ("flac", "ogg")
                    engine_ext = ".wav" if needs_post_encode else self._audio_format
                    engine_out = (
                        out.with_suffix(".intermediate.wav")
                        if needs_post_encode
                        else out
                    )

                    if is_subtitle_format(suffix):
                        entries, _ = parse_subtitle(content, suffix)
                        if not entries:
                            update_voice_status(
                                entry_id,
                                STATUS_FAILED,
                                error_message="EMPTY_TEXT",
                            )
                            continue
                        synthesize_timed_speech(
                            entries,
                            target_lang=self._target_lang,
                            voice_gender=self._voice_gender,
                            output_path=str(engine_out),
                            tts_method=self._tts_method,
                            audio_format=engine_ext,
                            is_cancelled=lambda: not self._is_running,
                        )
                    else:
                        # Plain text: untimed synthesis
                        synthesize_speech(
                            content,
                            target_lang=self._target_lang,
                            voice_gender=self._voice_gender,
                            output_path=str(engine_out),
                            tts_method=self._tts_method,
                            audio_format=engine_ext,
                            is_cancelled=lambda: not self._is_running,
                        )

                    if needs_post_encode:
                        from src.utils.audio_encoding import (  # noqa: PLC0415
                            post_encode_audio,
                        )

                        # ``post_encode_audio`` raises ``RuntimeError``
                        # on any failure (FFMPEG_NOT_FOUND / FFMPEG_FAILED
                        # / UNKNOWN_FORMAT).  The ``except Exception``
                        # below catches it and marks the task failed —
                        # the WAV intermediate is left on disk for
                        # recovery.  The Voice page pre-check
                        # (``_check_requirements``) normally blocks the
                        # no-ffmpeg case before this code runs.
                        final = post_encode_audio(
                            engine_out,
                            fmt,
                            output_path=out,
                        )
                        results.append((entry_id, source_path, str(final)))
                    else:
                        results.append((entry_id, source_path, str(out)))
                except Exception as exc:
                    logger.error(
                        "Voice generation failed for task %d: %s",
                        entry_id,
                        exc,
                    )
                    update_voice_status(
                        entry_id,
                        STATUS_FAILED,
                        error_message=str(exc),
                    )
        except Exception:
            logger.exception("Voice worker crashed")
        finally:
            try:
                for entry_id, _ in self._tasks:
                    if entry_id not in processed_ids:
                        update_voice_status(
                            entry_id,
                            STATUS_FAILED,
                            error_message="CANCELLED",
                        )
            except Exception:
                logger.exception("Failed to mark cancelled voice tasks")
            _VoiceWorker._is_any_worker_running = False
            self.finished_ok.emit(results)


# ── Main page ──────────────────────────────────────────────────────────────


class VoicePage(QWidget):
    """Unified page for voice generation and history management.

    Layout (QStackedWidget with two views sharing one FileDropWidget):
        - View 0: drop area (full) + history table
        - View 1: drop area (compact) + file selection list
    """

    def __init__(
        self,
        window: QMainWindow,
        parent: QWidget | None = None,
    ) -> None:
        """Initializes the VoicePage."""
        super().__init__(parent)
        self.window_context = window
        self.selected_files: list[str] = []
        self._worker: _VoiceWorker | None = None
        self._pending_tasks: list[tuple[int, str]] = []
        # Reset entries stuck in "Generating" from a previous crash
        from src.core.database import reset_stuck_voice_entries  # noqa: PLC0415

        reset_stuck_voice_entries()
        self._setup_ui()
        self._update_ui_state()

        # Ensure the TTS/FFmpeg thread doesn't outlive the application.
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._stop_all_workers)

    def _stop_all_workers(self) -> None:
        """Requests the worker to stop and waits briefly before shutdown."""
        if self._worker is not None:
            self._worker.stop()
            # Bounded wait — some TTS backends / FFmpeg invocations can take
            # a few seconds to wind down. Don't block app exit forever.
            self._worker.wait(2000)
            self._worker = None

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 — Qt override
        """Re-checks ffmpeg availability on every page show.

        A user who installs ffmpeg in another window doesn't have to
        restart the app — switching to the Voice page re-syncs the
        top-of-page install banner.
        """
        super().showEvent(event)
        if hasattr(self, "_refresh_ffmpeg_banner"):
            self._refresh_ffmpeg_banner()

    # ------------------------------------------------------------------
    # UI Setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        """Builds the full page layout."""
        page_container, content_layout = create_page_container(
            tr("page.generate_voice"),
            tr_key="page.generate_voice",
        )
        content_layout.setSpacing(15)
        content_layout.setContentsMargins(20, 10, 20, 10)

        # The surrounding navigation already renders a header for this page.
        page_container.header_label.setVisible(False)

        # FFmpeg install banner at the top — Voice always needs ffmpeg
        # for chunk concatenation and most format-conversion paths.
        # Surfacing it here means users see the install instructions
        # before queuing 100 files, not after the modal block.  Visibility
        # auto-syncs on showEvent so installing ffmpeg in another window
        # clears the banner without an app restart.
        from src.ui.components import (  # noqa: PLC0415
            create_ffmpeg_install_banner,
        )

        self._ffmpeg_banner, self._refresh_ffmpeg_banner = (
            create_ffmpeg_install_banner()
        )
        content_layout.addWidget(self._ffmpeg_banner)
        self._refresh_ffmpeg_banner()

        # Shared drop area
        self.drop_area = FileDropWidget()
        self.drop_area.setFixedHeight(DROP_AREA_HEIGHT)
        self.drop_area.files_dropped.connect(self._handle_files_dropped)
        voice_formats = ", ".join(ext.lstrip(".") for ext in SUPPORTED_VOICE_INPUT)
        self.drop_area.supported_label.setText(
            tr("drop.supported", formats=voice_formats)
        )

        # --- View 0: drop area + history table ---
        self.history_wrapper = QWidget()
        self.history_wrapper_layout = QVBoxLayout(self.history_wrapper)
        self.history_wrapper_layout.setContentsMargins(0, 0, 0, 0)
        self.history_wrapper_layout.setSpacing(15)

        self.history_view = VoiceHistoryPage()
        self.history_view.re_generate_requested.connect(self._handle_re_generate)
        self._clean_history_view()
        self.history_wrapper_layout.addWidget(self.drop_area)
        self.history_wrapper_layout.addWidget(self.history_view, 1)

        # --- View 1: drop area (compact) + file list ---
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
            QKeySequence(get_shortcut("voice.generate")),
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
                QKeySequence(get_shortcut("voice.generate")),
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

        self.generate_btn = QPushButton(tr("voice.btn_generate"))
        self.generate_btn.setFixedHeight(HEIGHT_CONTROL)
        self.generate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.generate_btn.setStyleSheet(style_primary_button())
        self.generate_btn.setAccessibleName(tr("voice.btn_generate"))
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
        self.generate_btn.setText(tr("voice.btn_generate"))
        # Avoid clobbering "Stopping…" mid-cancel.
        if self._worker is None:
            self.stop_btn.setText(tr("btn.stop"))
        self.clear_all_btn.setText(tr("btn.delete_all"))
        voice_formats = ", ".join(ext.lstrip(".") for ext in SUPPORTED_VOICE_INPUT)
        self.drop_area.supported_label.setText(
            tr("drop.supported", formats=voice_formats)
        )
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
        """Walks directories and collects up to ``_MAX_FILES_PER_DROP`` supported files.

        Only supported subtitle/text extensions count toward the cap, so a
        directory full of junk (build artifacts, audio files, dotfiles) can't
        starve the cap and hide real subtitle files deeper in the tree.

        Returns a tuple of (supported_files, unsupported_names, cap_hit_flag).
        """
        supported: list[Path] = []
        unsupported: list[str] = []
        cap_hit = False

        def _cap_reached() -> bool:
            return len(supported) >= _MAX_FILES_PER_DROP

        for f in files:
            if _cap_reached():
                cap_hit = True
                break
            p = Path(f).resolve()
            if p.is_dir():
                for child in p.rglob("*"):
                    if any(part.startswith(".") for part in child.relative_to(p).parts):
                        continue
                    if not child.is_file():
                        continue
                    if child.suffix.lower() in SUPPORTED_VOICE_INPUT:
                        supported.append(child)
                        if _cap_reached():
                            cap_hit = True
                            break
                    else:
                        unsupported.append(child.name)
            elif p.is_file():
                if p.suffix.lower() in SUPPORTED_VOICE_INPUT:
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
        """Shows a consolidated dialog for skipped/duplicate/capped drops."""
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
        """Processes dropped or browsed subtitle/text files and directories."""
        if not files:
            files, _ = QFileDialog.getOpenFileNames(
                self.window_context,
                tr("voice.select_files"),
                "",
                _VOICE_FILTER,
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
            lambda _fp=file_path, _w=widget: self._handle_remove_file(
                _fp,
                _w,
            )
        )
        idx = self.files_vbox.count() - 1
        self.files_vbox.insertWidget(idx, widget)

    def _handle_remove_file(
        self,
        file_path: str,
        widget: FileItemWidget,
    ) -> None:
        """Removes a single file from the selection."""
        if file_path in self.selected_files:
            self.selected_files.remove(file_path)
        widget.setParent(None)
        widget.deleteLater()
        self._update_ui_state()

    def _handle_clear_all(self, *, confirm: bool = True) -> None:
        """Removes all files from the selection.

        Args:
            confirm: Ask the user to confirm. Internal callers (post-generate
                cleanup) pass ``False`` to skip the dialog.
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
        """Ensures TTS and FFmpeg prerequisites are met.

        Checks the configured TTS backend's credentials (Google Cloud or
        ElevenLabs) and FFmpeg availability.  FFmpeg is required
        defensively because the format-needs-ffmpeg matrix is
        backend-dependent (e.g. Edge+WAV needs ffmpeg for MP3→WAV
        transcode; Piper+MP3 needs ffmpeg for WAV→MP3) — surfacing the
        block up-front beats failing deep in the worker after queuing
        100 files.  An earlier attempt at a conditional check
        (``has_subtitle_input or fmt != ".wav"``) was wrong because
        "WAV" isn't universally ffmpeg-free — only when the backend's
        native output is also WAV (Piper).  See chat archaeology if
        re-introducing — the only correct version is a per-backend
        native-format map.
        """
        from src.constants.settings import (  # noqa: PLC0415
            VOICE_TTS_ELEVENLABS,
            VOICE_TTS_GOOGLE,
        )
        from src.core.speech_engine import check_ffmpeg_available  # noqa: PLC0415

        method = load_setting(SETTING_VOICE_TTS_METHOD, VOICE_TTS_EDGE)

        # Validate the credentials required for the selected TTS backend.
        if method == VOICE_TTS_GOOGLE and not require_setup(
            self.window_context,
            check_google_cloud_setup,
            "voice.setup_required_title",
            "voice.setup_required_msg",
            2,
        ):
            return False
        if method == VOICE_TTS_ELEVENLABS and not require_setup(
            self.window_context,
            check_elevenlabs_setup,
            "voice.elevenlabs_required_title",
            "voice.elevenlabs_required_msg",
            2,
        ):
            return False

        if not check_ffmpeg_available():
            from src.utils.install_hints import (  # noqa: PLC0415
                build_ffmpeg_install_message,
            )

            CustomMessageDialog.show_message(
                self.window_context,
                tr("voice.ffmpeg_required_title"),
                build_ffmpeg_install_message(),
            )
            return False

        return True

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
        """Validates setup, creates DB entries, starts worker."""
        if not self.selected_files or self._worker is not None:
            return

        if not self._check_requirements():
            return

        # Show voice setup dialog (language + gender)
        lang, gender, _model_id, accepted = VoiceSetupDialog.get_selection(
            self.window_context,
        )
        if not accepted:
            return

        # Pre-flight: when Piper is the active TTS engine, ensure
        # the per-language voice is on disk before queueing a batch
        # — otherwise every task would fail with
        # PIPER_VOICE_NOT_INSTALLED and the user would only see it
        # after every history row turned red.
        if not preflight_piper_voice(self.window_context, lang, gender):
            return

        tts_method = load_setting(SETTING_VOICE_TTS_METHOD, VOICE_TTS_EDGE)
        out_fmt = load_setting(SETTING_LAST_VOICE_FORMAT, ".mp3")

        # Create "Pending" entries upfront
        tasks: list[tuple[int, str]] = []
        for file_path in self.selected_files:
            src = Path(file_path)
            try:
                file_size = src.stat().st_size if src.exists() else 0
            except OSError:
                file_size = 0
            entry_id = add_voice_entry(
                file_name=src.name,
                file_size=file_size,
                source_path=file_path,
                output_path="",
                status=STATUS_PENDING,
            )
            if entry_id:
                tasks.append((entry_id, file_path))

        if not tasks:
            # Nothing queued — keep the selection so the user can retry.
            CustomMessageDialog.show_message(
                self.window_context,
                tr("dialog.voice_queue_failed_title"),
                tr("dialog.voice_queue_failed_msg"),
            )
            return

        # Only clear after at least one task was successfully queued.
        self._handle_clear_all(confirm=False)
        self.history_view.refresh_history(force=True)

        self._start_worker(tasks, lang, gender, tts_method, out_fmt)

    def _handle_re_generate(
        self,
        tasks: list[tuple[int, str]],
    ) -> None:
        """Re-generates voice for selected files."""
        if self._worker is not None:
            # Generation is already running — silent re-generate would
            # confuse users. Surface a message so they know to wait.
            CustomMessageDialog.show_message(
                self.window_context,
                tr("dialog.voice_busy_title"),
                tr("dialog.voice_busy_msg"),
            )
            return

        if not self._check_requirements():
            return

        lang, gender, _model_id, accepted = VoiceSetupDialog.get_selection(
            self.window_context,
        )
        if not accepted:
            return

        # Same Piper preflight as ``_handle_generate`` — applies to
        # the user-initiated re-generate flow too.
        if not preflight_piper_voice(self.window_context, lang, gender):
            return

        tts_method = load_setting(SETTING_VOICE_TTS_METHOD, VOICE_TTS_EDGE)
        out_fmt = load_setting(SETTING_LAST_VOICE_FORMAT, ".mp3")

        for entry_id, _ in tasks:
            update_voice_status(entry_id, STATUS_PENDING)
        self.history_view.refresh_history(force=True)

        self._start_worker(tasks, lang, gender, tts_method, out_fmt)

    def _handle_stop(self) -> None:
        """Requests the running worker to stop after the current file."""
        if self._worker is None:
            return
        self._worker.stop()
        self.stop_btn.setEnabled(False)
        self.stop_btn.setText(tr("voice.stopping"))

    def _start_worker(
        self,
        tasks: list[tuple[int, str]],
        target_lang: str,
        voice_gender: str,
        tts_method: str,
        audio_format: str,
    ) -> None:
        """Starts the voice generation background worker."""
        if self._worker is not None:
            return
        self._pending_tasks = tasks

        self._worker = _VoiceWorker(
            tasks,
            target_lang,
            voice_gender,
            tts_method=tts_method,
            audio_format=audio_format,
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

    def _on_finished(
        self,
        results: list[tuple[int, str, str]],
    ) -> None:
        """Updates DB entries with output paths."""
        self._safe_cleanup_worker()
        # Restore default header-button visibility.
        self.stop_btn.setVisible(False)
        self.generate_btn.setVisible(True)

        auto_remove = bool(load_setting(SETTING_VOICE_AUTO_REMOVE, False))

        for entry_id, _source_path, output_path in results:
            if auto_remove:
                delete_voice_entry(entry_id)
            else:
                update_voice_status(
                    entry_id,
                    STATUS_DONE,
                    output_path=output_path,
                )

        self.history_view.refresh_history(force=True)


def create_voice_page(window: QMainWindow) -> QWidget:
    """Creates the Generate Voice page.

    Args:
        window: The main application window.

    Returns:
        QWidget: The voice page widget.
    """
    return VoicePage(window)
