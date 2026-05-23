"""Dubbing page UI for the AI Translate application.

Full dubbing pipeline: video → STT → translate → TTS → mix audio back.
Produces a dubbed video with translated speech in a single step.
"""

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QThread, QTimer, Signal
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
    style_delete_button,
    style_primary_button,
    style_warning_button,
    tr,
)
from src.constants.files import SUPPORTED_VIDEO
from src.constants.history import (
    DUBBING_PROGRESS_MIX_START,
    DUBBING_PROGRESS_STT_DONE,
    DUBBING_PROGRESS_STT_START,
    DUBBING_PROGRESS_TRANSLATE_DONE,
    DUBBING_PROGRESS_TTS_DONE,
    DUBBING_PROGRESS_TTS_START,
    PROGRESS_COMPLETE,
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_GENERATING,
    STATUS_PENDING,
)
from src.constants.settings import (
    SETTING_DUBBING_AUTO_REMOVE,
    SETTING_LAST_DUBBING_SRC_LANG,
    SETTING_LAST_DUBBING_TGT_LANG,
)
from src.core.database import (
    add_dubbing_entry,
    delete_dubbing_entry,
    get_dubbing_entry_status,
    get_unfinished_dubbing,
    update_dubbing_progress,
    update_dubbing_status,
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
    LanguageSelectionDialog,
    preflight_piper_voice,
    require_setup,
)
from src.ui.pages.dubbing_history import DubbingHistoryPage
from src.utils.config_manager import (
    check_elevenlabs_setup,
    load_setting,
)
from src.utils.file_utils import format_file_size
from src.utils.path_manager import generate_dubbing_output_path

logger = logging.getLogger("dubbing")

# Stacked widget indices
_VIEW_HISTORY = 0
_VIEW_FILES = 1

# Maximum number of files accepted per drop/browse. Prevents UI freeze on
# accidental drops of huge trees. The user is notified when the cap is hit.
_MAX_FILES_PER_DROP = 100

# File filter for QFileDialog
_VIDEO_FILTER = (
    f"Video Files ({' '.join('*' + ext for ext in SUPPORTED_VIDEO)});;All Files (*)"
)


# ── Background dubbing worker ─────────────────────────────────────────────


class _DubbingWorker(QThread):
    """Runs the full dubbing pipeline in a background thread."""

    finished_ok = Signal(list)  # list[(entry_id, output_path)]
    _is_any_worker_running = False  # Class-level flag

    def __init__(  # noqa: PLR0913
        self,
        tasks: list[tuple[int, str]],  # [(entry_id, video_path), ...]
        src_lang: str,
        target_lang: str,
        voice_gender: str = "FEMALE",
        llm_provider: str | None = None,
        llm_model: str | None = None,
    ) -> None:
        """Initializes the dubbing worker."""
        super().__init__()
        self._tasks = tasks
        self._src_lang = src_lang
        self._target_lang = target_lang
        self._voice_gender = voice_gender
        self._llm_provider = llm_provider
        self._llm_model = llm_model
        self._is_running = True

    @classmethod
    def is_busy(cls) -> bool:
        """Checks if a dubbing worker is already running."""
        return cls._is_any_worker_running

    def stop(self) -> None:
        """Requests the worker to stop."""
        self._is_running = False

    def _is_task_cancelled(self, entry_id: int) -> bool:
        """Checks if a task was paused or deleted while in progress.

        Returns True if the worker was stopped globally, or if the
        task's DB status is no longer 'Generating' (e.g. user paused).
        """
        if not self._is_running:
            return True
        status = get_dubbing_entry_status(entry_id)
        return status != STATUS_GENERATING

    def run(self) -> None:  # noqa: PLR0912, PLR0915
        """Runs the full dubbing pipeline for each video."""
        import shutil as _shutil  # noqa: PLC0415

        from src.constants.settings import (  # noqa: PLC0415
            SETTING_LAST_VOICE_FORMAT,
            SETTING_SUBTITLE_STT_METHOD,
            SETTING_VOICE_TTS_METHOD,
            SETTING_WHISPER_MODEL,
            STT_WHISPER,
            VOICE_TTS_EDGE,
        )
        from src.core.checkpoint import (  # noqa: PLC0415
            clear_checkpoints,
            load_dubbing_checkpoint,
            save_dubbing_checkpoint,
        )
        from src.core.database import (  # noqa: PLC0415
            get_active_glossary_sets,
            get_glossary_entries,
        )
        from src.core.llm_engine import translate_batch  # noqa: PLC0415
        from src.core.speech_engine import (  # noqa: PLC0415
            mix_audio_into_video,
            synthesize_timed_speech,
            transcribe_audio,
        )
        from src.utils.path_manager import (  # noqa: PLC0415
            get_dubbing_storage_dir,
        )
        from src.utils.subtitle_utils import (  # noqa: PLC0415
            parse_subtitle,
            serialize_subtitle,
        )

        stt_method = load_setting(SETTING_SUBTITLE_STT_METHOD, STT_WHISPER)
        model_size = load_setting(SETTING_WHISPER_MODEL, "base")
        tts_method = load_setting(SETTING_VOICE_TTS_METHOD, VOICE_TTS_EDGE)
        audio_fmt = load_setting(SETTING_LAST_VOICE_FORMAT, ".mp3")

        # Fetch active glossary entries once for all tasks
        glossary: list[tuple[int, str, str]] = []
        for set_id, _ in get_active_glossary_sets():
            glossary.extend(get_glossary_entries(set_id))

        if _DubbingWorker._is_any_worker_running:
            return
        _DubbingWorker._is_any_worker_running = True

        results: list[tuple[int, str, str, str, str]] = []

        try:
            for entry_id, video_path in self._tasks:
                if not self._is_running:
                    break

                update_dubbing_status(entry_id, STATUS_GENERATING)
                storage_dir = get_dubbing_storage_dir(entry_id)

                try:
                    self._run_dubbing_pipeline(
                        entry_id,
                        video_path,
                        storage_dir,
                        stt_method=stt_method,
                        model_size=model_size,
                        tts_method=tts_method,
                        audio_fmt=audio_fmt,
                        glossary_entries=glossary or None,
                        transcribe_audio=transcribe_audio,
                        translate_batch=translate_batch,
                        parse_subtitle=parse_subtitle,
                        serialize_subtitle=serialize_subtitle,
                        synthesize_timed_speech=synthesize_timed_speech,
                        mix_audio_into_video=mix_audio_into_video,
                        save_checkpoint=save_dubbing_checkpoint,
                        load_checkpoint=load_dubbing_checkpoint,
                        results=results,
                    )
                    # The pipeline signals cancel with a silent return, not an
                    # exception, so recheck before cleanup — otherwise a
                    # paused/stopped task's checkpoints would be wiped and
                    # resumption would start from scratch.
                    if self._is_task_cancelled(entry_id):
                        continue
                    # Success — clean up checkpoints and storage
                    clear_checkpoints(storage_dir)
                    _shutil.rmtree(storage_dir, ignore_errors=True)
                except Exception as exc:
                    logger.error(
                        "Dubbing failed for task %d: %s",
                        entry_id,
                        exc,
                    )
                    update_dubbing_status(
                        entry_id,
                        STATUS_FAILED,
                        error_message=str(exc),
                    )
                    # Storage dir persists so checkpoints survive
        except Exception:
            logger.exception("Dubbing worker crashed")
        finally:
            _DubbingWorker._is_any_worker_running = False
            self.finished_ok.emit(results)

    def _run_dubbing_pipeline(  # noqa: PLR0913, PLR0912, PLR0915
        self,
        entry_id: int,
        video_path: str,
        storage_dir: Path,
        *,
        stt_method: str,
        model_size: str,
        tts_method: str,
        audio_fmt: str,
        glossary_entries: list[tuple[int, str, str]] | None,
        transcribe_audio: Callable[..., Any],
        translate_batch: Callable[..., Any],
        parse_subtitle: Callable[..., Any],
        serialize_subtitle: Callable[..., Any],
        synthesize_timed_speech: Callable[..., Any],
        mix_audio_into_video: Callable[..., Any],
        save_checkpoint: Callable[..., Any],
        load_checkpoint: Callable[..., Any],
        results: list[tuple[int, str, str, str, str]],
    ) -> None:
        """Runs the 4-step dubbing pipeline with checkpoint resumption.

        Args:
            entry_id: Database ID for this dubbing task.
            video_path: Absolute path to the source video file.
            storage_dir: Directory for checkpoints and intermediate files.
            stt_method: Speech-to-text backend identifier.
            model_size: Whisper model size for STT.
            tts_method: Text-to-speech backend identifier.
            audio_fmt: Output audio format extension (e.g. ".mp3").
            glossary_entries: Optional glossary terms for translation.
            transcribe_audio: STT callable.
            translate_batch: LLM batch translation callable.
            parse_subtitle: Subtitle parser callable.
            serialize_subtitle: Subtitle serializer callable.
            synthesize_timed_speech: TTS callable.
            mix_audio_into_video: Audio mixing callable.
            save_checkpoint: Checkpoint writer callable.
            load_checkpoint: Checkpoint reader callable.
            results: Accumulator for successful result tuples.
        """
        cancel = lambda: self._is_task_cancelled(entry_id)  # noqa: E731

        # Load checkpoint for resumption
        ckpt = load_checkpoint(storage_dir)
        srt_text: str = ""
        original_srt: str = ""  # Raw STT output (pre-translation)
        voice_filename = f"voice{audio_fmt}"
        voice_path = storage_dir / voice_filename

        # Invalidate downstream checkpoints (translation & TTS) when the user
        # changed the target language between runs, so stale artifacts are not reused.
        if ckpt and ckpt.get("target_lang") != self._target_lang:
            ckpt.pop("translated_srt", None)
            ckpt.pop("voice_file", None)
            if voice_path.exists():
                voice_path.unlink(missing_ok=True)
            if ckpt.get("target_lang"):
                logger.info(
                    "Task %d: target language changed (%s → %s), re-translating",
                    entry_id,
                    ckpt["target_lang"],
                    self._target_lang,
                )

        # ── Step 1: STT (5–25%) ──────────────────────────────────────
        if ckpt and "srt_text" in ckpt:
            srt_text = ckpt["srt_text"]
            original_srt = srt_text
            logger.info("Task %d: resuming from STT checkpoint", entry_id)
            update_dubbing_progress(entry_id, DUBBING_PROGRESS_STT_DONE)
        else:
            update_dubbing_progress(entry_id, DUBBING_PROGRESS_STT_START)
            srt_text = transcribe_audio(
                video_path,
                src_lang=self._src_lang,
                stt_method=stt_method,
                model_size=model_size,
                is_cancelled=cancel,
            )
            if cancel():
                return
            if not srt_text.strip():
                msg = tr("dubbing.no_speech_detected")
                raise ValueError(msg)
            original_srt = srt_text
            save_checkpoint(
                storage_dir,
                srt_text=srt_text,
                target_lang=self._target_lang,
            )
            update_dubbing_progress(entry_id, DUBBING_PROGRESS_STT_DONE)

        # ── Step 2: Translate (25–50%) ───────────────────────────────
        if ckpt and "translated_srt" in ckpt:
            srt_text = ckpt["translated_srt"]
            logger.info("Task %d: resuming from translate checkpoint", entry_id)
            update_dubbing_progress(
                entry_id,
                DUBBING_PROGRESS_TRANSLATE_DONE,
            )
        else:
            entries, fmt_data = parse_subtitle(srt_text, ".srt")
            if entries:
                texts = [e.text for e in entries]
                src = self._src_lang or "Auto"
                llm_provider = getattr(self, "_llm_provider", None)
                llm_model = getattr(self, "_llm_model", None)
                translate_kwargs = {
                    "target_lang": self._target_lang,
                    "src_lang": src,
                    "glossary_entries": glossary_entries,
                    "cancel_check": cancel,
                }
                if llm_provider or llm_model:
                    translate_kwargs["provider"] = llm_provider
                    translate_kwargs["model"] = llm_model
                translated = translate_batch(texts, **translate_kwargs)
                if cancel():
                    return
                if translated and len(translated) == len(entries):
                    for entry, new_text in zip(
                        entries,
                        translated,
                        strict=True,
                    ):
                        entry.text = new_text
                srt_text = serialize_subtitle(
                    entries,
                    fmt_data,
                    ".srt",
                )
            # Only update ``translated_srt`` here — ``srt_text`` on disk
            # must remain the raw STT output so the original-language
            # subtitle file still contains the source text on resume.
            save_checkpoint(
                storage_dir,
                translated_srt=srt_text,
                target_lang=self._target_lang,
            )
            update_dubbing_progress(
                entry_id,
                DUBBING_PROGRESS_TRANSLATE_DONE,
            )

        # ── Step 3: TTS (50–90%) ────────────────────────────────────
        if cancel():
            return

        if ckpt and ckpt.get("voice_file") and voice_path.exists():
            logger.info("Task %d: resuming from TTS checkpoint", entry_id)
            update_dubbing_progress(entry_id, DUBBING_PROGRESS_TTS_DONE)
        else:
            entries, _ = parse_subtitle(srt_text, ".srt")
            if not entries:
                msg = tr("dubbing.no_speech_detected")
                raise ValueError(msg)

            # Per-entry TTS progress callback
            tts_range = DUBBING_PROGRESS_TTS_DONE - DUBBING_PROGRESS_TTS_START

            def _on_tts_progress(current: int, total: int) -> None:
                pct = DUBBING_PROGRESS_TTS_START + int(
                    current / total * tts_range,
                )
                update_dubbing_progress(entry_id, pct)

            synthesize_timed_speech(
                entries,
                target_lang=self._target_lang,
                voice_gender=self._voice_gender,
                output_path=str(voice_path),
                tts_method=tts_method,
                audio_format=audio_fmt,
                is_cancelled=cancel,
                on_progress=_on_tts_progress,
            )
            if cancel():
                return
            save_checkpoint(
                storage_dir,
                voice_file=voice_filename,
            )
            update_dubbing_progress(entry_id, DUBBING_PROGRESS_TTS_DONE)

        # ── Step 4: Mix (90–100%) ───────────────────────────────────
        if cancel():
            return
        update_dubbing_progress(entry_id, DUBBING_PROGRESS_MIX_START)
        output = generate_dubbing_output_path(
            Path(video_path),
            src_lang=self._src_lang,
            target_lang=self._target_lang,
        )
        mix_audio_into_video(
            video_path,
            str(voice_path),
            str(output),
        )

        # Save intermediate artifacts alongside the output video
        import shutil as _sh  # noqa: PLC0415

        from src.constants.languages import get_locale_code  # noqa: PLC0415

        out_dir = output.parent
        stem = Path(video_path).stem
        src_code = get_locale_code(self._src_lang) if self._src_lang else "auto"
        tgt_code = get_locale_code(self._target_lang) or "unknown"

        # Subtitle (original STT)
        srt_out = out_dir / f"{stem}_subtitle_{src_code}.srt"
        srt_out.write_text(original_srt, encoding="utf-8")

        # Translated subtitle
        translated_srt_out = out_dir / f"{stem}_subtitle_{tgt_code}.srt"
        translated_srt_out.write_text(srt_text, encoding="utf-8")

        # Voice audio (synthesized from translated subtitle)
        voice_out = out_dir / f"{stem}_voice_{tgt_code}{audio_fmt}"
        if voice_path.exists():
            _sh.copy2(voice_path, voice_out)

        update_dubbing_progress(entry_id, PROGRESS_COMPLETE)
        results.append(
            (
                entry_id,
                str(output),
                str(srt_out),
                str(translated_srt_out),
                str(voice_out),
            )
        )


# ── Main page ──────────────────────────────────────────────────────────────


class DubbingPage(QWidget):
    """Page for video dubbing — full STT → translate → TTS → mix pipeline.

    Layout (QStackedWidget with two views sharing one FileDropWidget):
        - View 0: drop area (full) + history table
        - View 1: drop area (compact) + file selection list
    """

    def __init__(
        self,
        window: QMainWindow,
        parent: QWidget | None = None,
    ) -> None:
        """Initializes the DubbingPage."""
        super().__init__(parent)
        self.window_context = window
        self.selected_files: list[str] = []
        self._worker: _DubbingWorker | None = None
        self._pending_tasks: list[tuple[int, str]] = []
        self._setup_ui()
        self._update_ui_state()

        # Auto-resume pending entries from DB (e.g. after app restart)
        QTimer.singleShot(0, self._resume_pending)

        # Dubbing can run for many minutes across STT/LLM/TTS/FFmpeg stages;
        # keep the worker thread from outliving the app on shutdown.
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._stop_all_workers)

    def _stop_all_workers(self) -> None:
        """Requests the worker to stop and waits briefly before shutdown."""
        if self._worker is not None:
            self._worker.stop()
            # Bounded wait — the pipeline honours the cancel flag between
            # stages, but a stage mid-flight (e.g. FFmpeg mux) may not.
            self._worker.wait(2000)
            self._worker = None

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 — Qt override
        """Re-checks ffmpeg availability on every page show.

        A user who installs ffmpeg in another window doesn't have to
        restart the app — switching to the Dubbing page re-syncs the
        top-of-page install banner.
        """
        super().showEvent(event)
        if hasattr(self, "_refresh_ffmpeg_banner"):
            self._refresh_ffmpeg_banner()

    def _setup_ui(self) -> None:
        """Builds the full page layout."""
        page_container, content_layout = create_page_container(
            tr("page.dubbing"),
            tr_key="page.dubbing",
        )
        content_layout.setSpacing(15)
        content_layout.setContentsMargins(20, 10, 20, 10)

        # The surrounding navigation already renders a header for this page.
        page_container.header_label.setVisible(False)

        # FFmpeg install banner at top — Dubbing always needs ffmpeg
        # (final video mux + per-stage audio handling).  Same pattern
        # as Voice / Live pages so users see the install instructions
        # before queuing files.
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
        video_formats = ", ".join(ext.lstrip(".") for ext in SUPPORTED_VIDEO)
        self.drop_area.supported_label.setText(
            tr("drop.supported", formats=video_formats)
        )

        # --- View 0: drop area + history table ---
        self.history_wrapper = QWidget()
        self.history_wrapper_layout = QVBoxLayout(self.history_wrapper)
        self.history_wrapper_layout.setContentsMargins(0, 0, 0, 0)
        self.history_wrapper_layout.setSpacing(15)

        self.history_view = DubbingHistoryPage()
        self.history_view.re_dub_requested.connect(self._handle_re_dub)
        self.history_view.continue_requested.connect(self._handle_continue_dub)
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

        # Stacked widget
        self.stack = QStackedWidget()
        self.stack.addWidget(self.history_wrapper)
        self.stack.addWidget(self.files_wrapper)
        self.stack.setCurrentIndex(_VIEW_HISTORY)
        content_layout.addWidget(self.stack, 1)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(page_container)

        # Primary-action shortcut; rebinding is driven by the central registry.
        from src.constants.shortcuts import (  # noqa: PLC0415
            get_shortcut,
            shortcuts_changed,
        )

        self._generate_shortcut = QShortcut(
            QKeySequence(get_shortcut("dubbing.start")),
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
                QKeySequence(get_shortcut("dubbing.start")),
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

        self.generate_btn = QPushButton(tr("dubbing.btn_start"))
        self.generate_btn.setFixedHeight(HEIGHT_CONTROL)
        self.generate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.generate_btn.setStyleSheet(style_primary_button())
        self.generate_btn.setAccessibleName(tr("dubbing.btn_start"))
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
        """Re-applies theme-dependent styles."""
        self.files_badge.setStyleSheet(style_file_count_badge())
        self.section_label.setStyleSheet(style_section_label())
        self.generate_btn.setStyleSheet(style_primary_button())
        self.stop_btn.setStyleSheet(style_warning_button())
        self.clear_all_btn.setStyleSheet(style_delete_button())

    def apply_language(self) -> None:
        """Re-applies all translatable text."""
        self.section_label.setText(tr("files.selected"))
        self.generate_btn.setText(tr("dubbing.btn_start"))
        # Avoid clobbering "Stopping…" mid-cancel.
        if self._worker is None:
            self.stop_btn.setText(tr("btn.stop"))
        self.clear_all_btn.setText(tr("btn.delete_all"))
        video_formats = ", ".join(ext.lstrip(".") for ext in SUPPORTED_VIDEO)
        self.drop_area.supported_label.setText(
            tr("drop.supported", formats=video_formats)
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
        """Walks directories and collects up to ``_MAX_FILES_PER_DROP`` video files.

        Only supported video files count toward the cap, so a directory full
        of unrelated files (audio tracks, docs, build artifacts) can't starve
        the cap and hide real videos deeper in the tree.

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
                    if child.suffix.lower() in SUPPORTED_VIDEO:
                        supported.append(child)
                        if _cap_reached():
                            cap_hit = True
                            break
                    else:
                        unsupported.append(child.name)
            elif p.is_file():
                if p.suffix.lower() in SUPPORTED_VIDEO:
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
        """Processes dropped or browsed video files and directories."""
        if not files:
            files, _ = QFileDialog.getOpenFileNames(
                self.window_context,
                tr("dubbing.select_files"),
                "",
                _VIDEO_FILTER,
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
            confirm: Ask the user to confirm. Internal callers (post-start
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

    def _check_all_requirements(self) -> bool:
        """Checks STT, LLM, TTS, and FFmpeg prerequisites for dubbing.

        Dubbing runs a 4-stage pipeline that needs FFmpeg for audio
        extraction, voice concatenation, and final A/V mux — so a missing
        FFmpeg must be surfaced up-front rather than failing deep in the
        worker.
        """
        from src.constants.settings import (  # noqa: PLC0415
            SETTING_SUBTITLE_STT_METHOD,
            SETTING_VOICE_TTS_METHOD,
            STT_GOOGLE,
            STT_WHISPER,
            VOICE_TTS_EDGE,
            VOICE_TTS_ELEVENLABS,
            VOICE_TTS_GOOGLE,
        )
        from src.core.speech_engine import check_ffmpeg_available  # noqa: PLC0415
        from src.utils.config_manager import (  # noqa: PLC0415
            check_google_cloud_setup,
            check_llm_setup,
        )

        # 1. STT check (Google Cloud needs API key)
        stt = load_setting(SETTING_SUBTITLE_STT_METHOD, STT_WHISPER)
        if stt == STT_GOOGLE and not require_setup(
            self.window_context,
            check_google_cloud_setup,
            "subtitle.setup_required_title",
            "subtitle.setup_required_msg",
            2,
        ):
            return False

        # 2. LLM check (always required for translation).
        if not require_setup(
            self.window_context,
            check_llm_setup,
            "dialog.llm_required_title",
            "dialog.llm_required_msg",
            4,
        ):
            return False

        # 3. TTS credential check (Google Cloud or ElevenLabs).
        tts = load_setting(SETTING_VOICE_TTS_METHOD, VOICE_TTS_EDGE)
        if tts == VOICE_TTS_GOOGLE and not require_setup(
            self.window_context,
            check_google_cloud_setup,
            "voice.setup_required_title",
            "voice.setup_required_msg",
            2,
        ):
            return False
        if tts == VOICE_TTS_ELEVENLABS and not require_setup(
            self.window_context,
            check_elevenlabs_setup,
            "voice.elevenlabs_required_title",
            "voice.elevenlabs_required_msg",
            2,
        ):
            return False

        # 4. FFmpeg pre-check — dubbing needs it for every stage.
        # Reuses the shared install-message infrastructure
        # (``voice.ffmpeg_required_title`` + ``build_ffmpeg_install_message``)
        # so all three audio pages (Voice, Dubbing, Live) plus the
        # Listen-button pre-check show the SAME dialog wording with
        # the auto-detected per-OS install command.
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

        When the history table has focus with a selected row, re-dub the
        selected entries; otherwise fall through to the page's primary
        Dub action.
        """
        table = getattr(self.history_view, "table", None)
        if (
            table is not None
            and table.hasFocus()
            and table.selectionModel() is not None
            and table.selectionModel().hasSelection()
        ):
            self.history_view.on_re_dub()
            return
        self._handle_generate()

    def _handle_generate(self) -> None:
        """Validates setup, shows dialog, starts dubbing pipeline."""
        if not self.selected_files or self._worker is not None:
            return

        if not self._check_all_requirements():
            return

        # Language selection dialog
        from src.constants.settings import (  # noqa: PLC0415
            SETTING_LLM_MODEL_DUBBING,
        )

        result = LanguageSelectionDialog.get_selection(
            self.window_context,
            source_setting_key=SETTING_LAST_DUBBING_SRC_LANG,
            target_setting_key=SETTING_LAST_DUBBING_TGT_LANG,
            model_setting_key=SETTING_LLM_MODEL_DUBBING,
        )
        src_lang, target_lang, _model_id, accepted = result
        if not accepted or not target_lang:
            return

        # Pre-flight: when Piper is the active TTS engine, ensure
        # the per-language voice is on disk before queueing a batch.
        # Dubbing always uses the FEMALE voice (the worker has no
        # gender picker; ``_DubbingWorker._voice_gender`` defaults
        # to "FEMALE"), so we only need to check that one slot.
        if not preflight_piper_voice(
            self.window_context, target_lang, "FEMALE",
        ):
            return

        # Create DB entries
        tasks: list[tuple[int, str]] = []
        for file_path in self.selected_files:
            src = Path(file_path)
            try:
                file_size = src.stat().st_size if src.exists() else 0
            except OSError:
                file_size = 0
            entry_id = add_dubbing_entry(
                file_name=src.name,
                file_size=file_size,
                source_path=file_path,
                output_path="",
                status=STATUS_PENDING,
                src_lang=src_lang,
                target_lang=target_lang,
            )
            if entry_id:
                tasks.append((entry_id, file_path))

        if not tasks:
            # Nothing queued — keep the selection so the user can retry.
            CustomMessageDialog.show_message(
                self.window_context,
                tr("dialog.dubbing_queue_failed_title"),
                tr("dialog.dubbing_queue_failed_msg"),
            )
            return

        # Only clear after at least one task was successfully queued.
        self._handle_clear_all(confirm=False)
        self.history_view.refresh_history(force=True)

        self._start_worker(tasks, src_lang, target_lang)

    def _handle_continue_dub(
        self,
        tasks: list[tuple[int, str]],
        src_lang: str,
        target_lang: str,
    ) -> None:
        """Continues paused or failed dubbing tasks with stored languages."""
        if self._worker is not None:
            CustomMessageDialog.show_message(
                self.window_context,
                tr("dialog.dubbing_busy_title"),
                tr("dialog.dubbing_busy_msg"),
            )
            return

        if not self._check_all_requirements():
            return

        # Same Piper preflight as ``_handle_dub`` — a paused task
        # might have been queued before the user changed TTS engine
        # to Piper, so we need to validate again on every resume.
        if not preflight_piper_voice(
            self.window_context, target_lang, "FEMALE",
        ):
            return

        # Status already set to Pending by history page
        self._start_worker(tasks, src_lang, target_lang)

    def _handle_re_dub(
        self,
        tasks: list[tuple[int, str]],
    ) -> None:
        """Re-dubs selected videos."""
        if self._worker is not None:
            CustomMessageDialog.show_message(
                self.window_context,
                tr("dialog.dubbing_busy_title"),
                tr("dialog.dubbing_busy_msg"),
            )
            return

        if not self._check_all_requirements():
            return

        from src.constants.settings import (  # noqa: PLC0415
            SETTING_LLM_MODEL_DUBBING,
        )

        result = LanguageSelectionDialog.get_selection(
            self.window_context,
            source_setting_key=SETTING_LAST_DUBBING_SRC_LANG,
            target_setting_key=SETTING_LAST_DUBBING_TGT_LANG,
            model_setting_key=SETTING_LLM_MODEL_DUBBING,
        )
        src_lang, target_lang, _model_id, accepted = result
        if not accepted or not target_lang:
            return

        # Same Piper preflight as the other dubbing entry points.
        if not preflight_piper_voice(
            self.window_context, target_lang, "FEMALE",
        ):
            return

        for entry_id, _ in tasks:
            update_dubbing_status(entry_id, STATUS_PENDING)
        self.history_view.refresh_history(force=True)

        self._start_worker(tasks, src_lang, target_lang)

    def _handle_stop(self) -> None:
        """Requests the running worker to stop after the current stage."""
        if self._worker is None:
            return
        self._worker.stop()
        self.stop_btn.setEnabled(False)
        self.stop_btn.setText(tr("dubbing.stopping"))

    def _start_worker(
        self,
        tasks: list[tuple[int, str]],
        src_lang: str,
        target_lang: str,
    ) -> None:
        """Starts the dubbing background worker."""
        if self._worker is not None:
            return
        self._pending_tasks = tasks

        from src.constants.settings import (  # noqa: PLC0415
            SETTING_LLM_MODEL_DUBBING,
        )
        from src.utils.config_manager import (  # noqa: PLC0415
            load_model_for_feature,
            parse_model_id,
        )

        selected_model = load_model_for_feature(SETTING_LLM_MODEL_DUBBING)
        llm_provider, llm_model = (
            parse_model_id(selected_model) if selected_model else (None, None)
        )

        self._worker = _DubbingWorker(
            tasks,
            src_lang,
            target_lang,
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

    def _on_finished(self, results: list[tuple[int, str, str, str, str]]) -> None:
        """Updates DB entries with output paths, then auto-resumes pending."""
        self._safe_cleanup_worker()
        # Restore default header-button visibility.
        self.stop_btn.setVisible(False)
        self.generate_btn.setVisible(True)

        auto_remove = bool(load_setting(SETTING_DUBBING_AUTO_REMOVE, False))

        for result in results:
            entry_id, output_path = result[0], result[1]
            srt_path = result[2] if len(result) > 2 else ""  # noqa: PLR2004
            trans_srt = result[3] if len(result) > 3 else ""  # noqa: PLR2004
            voice_out = result[4] if len(result) > 4 else ""  # noqa: PLR2004

            if auto_remove:
                paths = delete_dubbing_entry(entry_id)
                # Delete all output files (video, subtitle, translated, voice)
                for fpath in paths:
                    if fpath:
                        p = Path(fpath)
                        if p.is_file():
                            p.unlink(missing_ok=True)
                # Clean up persistent storage directory (checkpoints)
                import shutil  # noqa: PLC0415

                from src.utils.path_manager import (  # noqa: PLC0415
                    get_dubbing_storage_dir,
                )

                storage = get_dubbing_storage_dir(entry_id)
                shutil.rmtree(storage, ignore_errors=True)
            else:
                update_dubbing_status(
                    entry_id,
                    STATUS_DONE,
                    output_path=output_path,
                    progress=str(PROGRESS_COMPLETE),
                    subtitle_path=srt_path,
                    translated_subtitle_path=trans_srt,
                    voice_path=voice_out,
                )

        self.history_view.refresh_history(force=True)

    def _resume_pending(self) -> None:
        """Checks DB for unfinished dubbing entries and restarts the worker.

        Groups pending entries by (src_lang, target_lang) and processes
        the first group. Subsequent groups are picked up on the next
        _on_finished cycle.
        """
        if self._worker is not None:
            return

        unfinished = get_unfinished_dubbing()
        if not unfinished:
            return

        # Group by language pair — worker uses a shared pair for all tasks
        first = unfinished[0]
        src_lang, target_lang = first[2], first[3]
        tasks: list[tuple[int, str]] = []
        for entry_id, source_path, s_lang, t_lang in unfinished:
            if s_lang == src_lang and t_lang == target_lang:
                tasks.append((entry_id, source_path))

        if tasks:
            self._start_worker(tasks, src_lang, target_lang)

    def _safe_cleanup_worker(self) -> None:
        """Waits for the worker thread to finish before dropping reference."""
        if self._worker is not None:
            self._worker.wait()
            self._worker = None


def create_dubbing_page(window: QMainWindow) -> QWidget:
    """Creates the Dubbing page.

    Args:
        window: The main application window.

    Returns:
        QWidget: The dubbing page widget.
    """
    return DubbingPage(window)
