"""Extract Text page UI for the AI Translate application.

Provides OCR- and LLM-based text extraction from images without translation.
A single shared FileDropWidget is reparented between two stacked views:
  - View 0 (default): drop area (full)
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
    SUPPORTED_IMAGES,
    style_delete_button,
    style_primary_button,
    tr,
)
from src.constants.history import (
    STATUS_DONE,
    STATUS_EXTRACTING,
    STATUS_FAILED,
    STATUS_PENDING,
)
from src.constants.ocr import OCR_METHOD_TESSERACT
from src.constants.settings import (
    EXTRACT_METHOD_LLM,
    EXTRACT_METHOD_OCR,
    SETTING_EXTRACT_METHOD,
    SETTING_OCR_METHOD,
)
from src.core.database import (
    add_extraction_entry,
    delete_extraction_entry,
    update_extraction_status,
)
from src.core.ocr_engine import OCRResult, merge_ocr_results, run_ocr
from src.ui.components import (
    FileDropWidget,
    FileItemWidget,
    create_page_container,
    style_file_count_badge,
    style_section_label,
)
from src.ui.dialogs import (
    CustomMessageDialog,
    SourceLanguageDialog,
    require_setup,
)
from src.ui.pages.extraction_history import ExtractionHistoryPage
from src.utils.config_manager import check_llm_setup, check_ocr_setup, load_setting
from src.utils.file_utils import format_file_size
from src.utils.path_manager import generate_extraction_output_path

logger = logging.getLogger("extract_text")

# Cap per drop/browse to keep the UI responsive.
_MAX_FILES_PER_DROP = 100


def _write_extraction_output(output_path: Path, text: str) -> None:
    """Writes extracted text to the given output path.

    Supports .txt (plain text) and .docx (python-docx).
    """
    ext = output_path.suffix.lower()
    if ext == ".docx":
        from docx import Document  # noqa: PLC0415

        doc = Document()
        for paragraph in text.split("\n"):
            doc.add_paragraph(paragraph)
        doc.save(str(output_path))
    else:
        # Plain text output (.txt)
        output_path.write_text(text, encoding="utf-8")


# Image-only file filter for QFileDialog
_IMAGE_FILTER = (
    f"Images ({' '.join('*' + ext for ext in SUPPORTED_IMAGES)});;All Files (*)"
)

# Stacked widget indices
_VIEW_HISTORY = 0
_VIEW_FILES = 1


# ── Background extraction worker ─────────────────────────────────────────────


class _ExtractionWorker(QThread):
    """Extracts text from images via OCR or LLM in a background thread."""

    progress = Signal(int, int)  # (current_index, total_count)
    finished_ok = Signal(list)  # list[(entry_id, image_path, text)]
    _is_any_worker_running = False  # Class-level flag

    def __init__(  # noqa: PLR0913
        self,
        tasks: list[tuple[int, str]],
        ocr_method: str,
        src_lang: str,
        extract_method: str = EXTRACT_METHOD_OCR,
        llm_provider: str | None = None,
        llm_model: str | None = None,
    ) -> None:
        """Initialize the extraction worker.

        Args:
            tasks: List of (entry_id, image_path) tuples to process.
            ocr_method: OCR backend identifier (e.g. Tesseract, EasyOCR).
            src_lang: Source language for OCR language-pack selection.
            extract_method: Extraction backend — OCR or LLM vision.
            llm_provider: Optional LLM provider override for vision extraction.
            llm_model: Optional LLM model override for vision extraction.
        """
        super().__init__()
        self._tasks = tasks  # [(entry_id, image_path), ...]
        self._ocr_method = ocr_method
        self._src_lang = src_lang
        self._extract_method = extract_method
        self._llm_provider = llm_provider
        self._llm_model = llm_model
        self._is_running = True

    @classmethod
    def is_busy(cls) -> bool:
        """Checks if an extraction worker is already running."""
        return cls._is_any_worker_running

    def stop(self) -> None:
        """Requests the worker to stop after the current image."""
        self._is_running = False

    def run(self) -> None:
        """Processes each image with OCR or LLM and emits results."""
        if _ExtractionWorker._is_any_worker_running:
            return
        _ExtractionWorker._is_any_worker_running = True

        results: list[tuple[int, str, str]] = []
        # Track which entries we actually attempted so the finally
        # block can mark the unstarted tail as cancelled.  Without
        # this, a Stop click mid-batch leaves queued rows stuck on
        # ``STATUS_PENDING`` (or the in-flight row on
        # ``STATUS_EXTRACTING``) — orphan rows the user has to
        # delete by hand.  Same orphan-cleanup pattern as Subtitle /
        # Voice / Dubbing pages.
        processed_ids: set[int] = set()
        total = len(self._tasks)

        try:
            for i, (entry_id, image_path) in enumerate(self._tasks):
                if not self._is_running:
                    break
                self.progress.emit(i + 1, total)
                update_extraction_status(entry_id, STATUS_EXTRACTING)

                try:
                    if self._extract_method == EXTRACT_METHOD_LLM:
                        text = self._extract_with_llm(image_path)
                    else:
                        text = self._extract_with_ocr(image_path)
                    results.append((entry_id, image_path, text))
                    processed_ids.add(entry_id)
                except Exception as exc:
                    logger.error(
                        "Extraction failed for task %d: %s",
                        entry_id,
                        exc,
                    )
                    update_extraction_status(
                        entry_id,
                        STATUS_FAILED,
                        error_message=str(exc),
                    )
                    # Count failure as "processed" — the row is no
                    # longer Pending, so it shouldn't be marked
                    # CANCELLED in the finally below.
                    processed_ids.add(entry_id)
        except Exception:
            logger.exception("Extraction worker crashed")
        finally:
            # Mark every queued-but-unstarted entry as FAILED so the
            # user sees a clear "you stopped this" status instead of
            # an orphan Pending row.  Wrapped in its own try/except
            # so a malformed task can't reset
            # ``_is_any_worker_running`` — the page's busy guard
            # depends on that flag flipping.
            try:
                for entry_id, _ in self._tasks:
                    if entry_id not in processed_ids:
                        update_extraction_status(
                            entry_id,
                            STATUS_FAILED,
                            error_message="CANCELLED",
                        )
            except Exception:
                logger.exception("Failed to mark cancelled extract tasks")
            _ExtractionWorker._is_any_worker_running = False
            self.finished_ok.emit(results)

    def _extract_with_ocr(self, image_path: str) -> str:
        """Extracts text from an image using the configured OCR engine."""
        ocr_results: list[OCRResult] = run_ocr(
            image_path,
            src_lang=self._src_lang,
            method=self._ocr_method,
        )
        merged = merge_ocr_results(ocr_results)
        return "\n".join(r.text for r in merged if r.text.strip())

    def _extract_with_llm(self, image_path: str) -> str:
        """Extracts text from an image using the configured LLM vision API."""
        from src.core.llm_engine import extract_image_text  # noqa: PLC0415

        llm_provider = getattr(self, "_llm_provider", None)
        llm_model = getattr(self, "_llm_model", None)
        if llm_provider or llm_model:
            return extract_image_text(
                image_path,
                provider=llm_provider,
                model=llm_model,
            )
        return extract_image_text(image_path)


class ExtractTextPage(QWidget):
    """Page for image text extraction via OCR.

    Layout (QStackedWidget with two views sharing one FileDropWidget):
        - View 0 (default): drop area (full)
        - View 1 (files selected): drop area (compact) + file selection list
    """

    def __init__(self, window: QMainWindow, parent: QWidget | None = None) -> None:
        """Initializes the ExtractTextPage.

        Args:
            window: The main application window, used for dialog parenting.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.window_context = window
        self.selected_files: list[str] = []
        self._worker: _ExtractionWorker | None = None
        self._pending_tasks: list[tuple[int, str]] = []
        self._output_format: str = ".txt"
        self._setup_ui()
        self._update_ui_state()

        # OCR / LLM-vision batches can run for minutes; make sure the worker
        # doesn't outlive the application and crash on torn-down widgets.
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._stop_all_workers)

    def _stop_all_workers(self) -> None:
        """Requests the worker to stop and waits briefly before shutdown."""
        if self._worker is not None:
            self._worker.stop()
            # Bounded wait — OCR libraries and LLM vision calls can't always
            # honour cancel mid-call, so don't block app exit forever.
            self._worker.wait(2000)
            self._worker = None

    # ------------------------------------------------------------------
    # UI Setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:  # noqa: PLR0915
        """Builds the full page layout."""
        page_container, content_layout = create_page_container(
            tr("page.extract_text"),
            tr_key="page.extract_text",
        )
        content_layout.setSpacing(15)
        content_layout.setContentsMargins(20, 10, 20, 10)

        # The surrounding navigation already renders a header for this page.
        page_container.header_label.setVisible(False)

        # Shared drop area (reparented between views on switch)
        self.drop_area = FileDropWidget()
        self.drop_area.setFixedHeight(DROP_AREA_HEIGHT)
        self.drop_area.files_dropped.connect(self._handle_files_dropped)
        # Override supported-formats label to show image formats only
        img_formats = ", ".join(ext.lstrip(".") for ext in sorted(SUPPORTED_IMAGES))
        self.drop_area.supported_label.setText(
            tr("drop.supported", formats=img_formats)
        )

        # --- View 0: drop area + extraction history ---
        self.history_wrapper = QWidget()
        self.history_wrapper_layout = QVBoxLayout(self.history_wrapper)
        self.history_wrapper_layout.setContentsMargins(0, 0, 0, 0)
        self.history_wrapper_layout.setSpacing(15)

        self.extraction_history = ExtractionHistoryPage()
        self.extraction_history.re_extract_requested.connect(self._handle_re_extract)
        self._clean_history_view()
        self.history_wrapper_layout.addWidget(self.drop_area)
        self.history_wrapper_layout.addWidget(self.extraction_history, 1)

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

        self._extract_shortcut = QShortcut(
            QKeySequence(get_shortcut("extract_text.extract")),
            self,
        )
        self._extract_shortcut.activated.connect(self._handle_primary_shortcut)

        self._focus_search_shortcut = QShortcut(
            QKeySequence(get_shortcut("common.focus_search")),
            self,
        )
        self._focus_search_shortcut.activated.connect(
            self.extraction_history.search_input.setFocus,
        )

        def _sync_shortcuts() -> None:
            self._extract_shortcut.setKey(
                QKeySequence(get_shortcut("extract_text.extract")),
            )
            self._focus_search_shortcut.setKey(
                QKeySequence(get_shortcut("common.focus_search")),
            )

        shortcuts_changed.connect(_sync_shortcuts)
        self._sync_shortcuts = _sync_shortcuts

    def _handle_primary_shortcut(self) -> None:
        """Dispatches Ctrl+Enter to the focused-context action.

        When the history table has focus with a selected row, re-extract
        the selected entries; otherwise fall through to the page's primary
        Extract action.
        """
        table = getattr(self.extraction_history, "table", None)
        if (
            table is not None
            and table.hasFocus()
            and table.selectionModel() is not None
            and table.selectionModel().hasSelection()
        ):
            self.extraction_history.on_re_extract()
            return
        self._handle_extract()

    def _create_file_list_section(self) -> QWidget:  # noqa: PLR0915
        """Creates the file selection header and scrollable file list."""
        section = QWidget()
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # Header row: badge + label + stretch + extract btn + delete all btn
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

        self.extract_btn = QPushButton(tr("extract_text.btn_extract"))
        self.extract_btn.setFixedHeight(HEIGHT_CONTROL)
        self.extract_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.extract_btn.setStyleSheet(style_primary_button())
        self.extract_btn.clicked.connect(self._handle_extract)
        header.addWidget(self.extract_btn)

        self.clear_all_btn = QPushButton(tr("btn.delete_all"))
        self.clear_all_btn.setFixedHeight(HEIGHT_CONTROL)
        self.clear_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_all_btn.setStyleSheet(style_delete_button())
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
        """Hides the standalone title and tightens margins.

        Makes the embedded ExtractionHistoryPage blend into the combined layout.
        """
        if not hasattr(self.extraction_history, "page"):
            return
        page_layout = self.extraction_history.page.layout()
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(10)
        header = getattr(self.extraction_history.page, "header_label", None)
        if header is not None:
            header.setVisible(False)

    # ------------------------------------------------------------------
    # Theme / Language
    # ------------------------------------------------------------------

    def apply_theme(self) -> None:
        """Re-applies theme-dependent styles."""
        self.files_badge.setStyleSheet(style_file_count_badge())
        self.section_label.setStyleSheet(style_section_label())
        self.extract_btn.setStyleSheet(style_primary_button())
        self.clear_all_btn.setStyleSheet(style_delete_button())

    def apply_language(self) -> None:
        """Re-applies all translatable text."""
        self.extract_btn.setText(tr("extract_text.btn_extract"))
        self.clear_all_btn.setText(tr("btn.delete_all"))
        self.section_label.setText(tr("files.selected"))
        img_formats = ", ".join(ext.lstrip(".") for ext in sorted(SUPPORTED_IMAGES))
        self.drop_area.supported_label.setText(
            tr("drop.supported", formats=img_formats)
        )
        self._clean_history_view()

    # ------------------------------------------------------------------
    # UI State
    # ------------------------------------------------------------------

    def _update_ui_state(self) -> None:
        """Switches views and reparents the shared drop area."""
        count = len(self.selected_files)
        has_files = count > 0

        self.extract_btn.setEnabled(has_files)
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
    ) -> tuple[list[Path], list[str]]:
        """Walks directories and collects up to ``_MAX_FILES_PER_DROP`` images.

        Only supported image files count toward the cap, so a directory full
        of non-image junk can't starve the cap and hide real images deeper
        in the tree.

        Returns a tuple of (supported_files, unsupported_names).
        """
        supported: list[Path] = []
        unsupported: list[str] = []

        def _cap_reached() -> bool:
            return len(supported) >= _MAX_FILES_PER_DROP

        for f in files:
            if _cap_reached():
                break
            p = Path(f).resolve()
            if p.is_dir():
                for child in p.rglob("*"):
                    if any(part.startswith(".") for part in child.relative_to(p).parts):
                        continue
                    if not child.is_file():
                        continue
                    if child.suffix.lower() in SUPPORTED_IMAGES:
                        supported.append(child)
                        if _cap_reached():
                            break
                    else:
                        unsupported.append(child.name)
            elif p.is_file():
                if p.suffix.lower() in SUPPORTED_IMAGES:
                    supported.append(p)
                else:
                    unsupported.append(p.name)

        return supported, unsupported

    def _handle_files_dropped(self, files: list[str]) -> None:
        """Processes dropped or browsed image files and directories."""
        if not files:
            files, _ = QFileDialog.getOpenFileNames(
                self.window_context,
                tr("extract_text.select_images"),
                "",
                _IMAGE_FILTER,
            )
        if not files:
            return

        added = False

        supported, walk_unsupported = self._walk_dropped_paths(files)
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

            if file_path not in self.selected_files:
                self.selected_files.append(file_path)
                self._add_file_widget(file_path)
                added = True

        if unsupported:
            unsupported_list = sorted(unsupported)

            # Truncate dialog text to prevent UI freeze
            max_display = 10
            if len(unsupported_list) > max_display:
                extra = len(unsupported_list) - max_display
                display_items = unsupported_list[:max_display]
                display_items.append(
                    tr("dialog.drop_unsupported_more", count=extra),
                )
            else:
                display_items = unsupported_list

            file_list = "\n".join(f"- {n}" for n in display_items)
            CustomMessageDialog.show_message(
                self.window_context,
                tr("dialog.unsupported_files"),
                tr("dialog.unsupported_msg", files=file_list),
            )
        if added:
            self._update_ui_state()

    def _add_file_widget(self, file_path: str) -> None:
        """Creates and inserts a FileItemWidget for the given path."""
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

    def _handle_clear_all(self) -> None:
        """Clears all selected files and switches back to history view."""
        self.selected_files.clear()
        while self.files_vbox.count() > 1:
            item = self.files_vbox.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._update_ui_state()

    # ------------------------------------------------------------------
    # OCR Extraction
    # ------------------------------------------------------------------

    def _check_extract_requirements(self) -> bool:
        """Ensures at least one extraction method (OCR or LLM) is configured."""
        return require_setup(
            self.window_context,
            lambda: check_ocr_setup() or check_llm_setup(),
            "extract_text.setup_required_title",
            "extract_text.setup_required_msg",
            3,
        )

    def _handle_extract(self) -> None:
        """Validates extraction setup, starts worker, clears files."""
        if not self.selected_files:
            return

        if self._worker is not None:
            # A batch is already running — starting another would clobber the
            # reference, and the new worker's class-level busy check would
            # make its run() return immediately without processing anything.
            CustomMessageDialog.show_message(
                self.window_context,
                tr("dialog.extract_busy_title"),
                tr("dialog.extract_busy_msg"),
            )
            return

        if not self._check_extract_requirements():
            return

        # Show source language dialog
        from src.constants.settings import (  # noqa: PLC0415
            SETTING_LLM_MODEL_EXTRACT,
        )

        src_lang, _, _model_id, accepted = SourceLanguageDialog.get_selection(
            self.window_context,
            model_setting_key=SETTING_LLM_MODEL_EXTRACT,
        )
        if not accepted:
            return

        ocr_method = load_setting(SETTING_OCR_METHOD, OCR_METHOD_TESSERACT)
        extract_method = load_setting(
            SETTING_EXTRACT_METHOD,
            EXTRACT_METHOD_OCR,
        )

        # Create "Pending" entries upfront (like Translate Document)
        tasks: list[tuple[int, str]] = []
        for file_path in self.selected_files:
            src = Path(file_path)
            try:
                file_size = src.stat().st_size if src.exists() else 0
            except OSError:
                file_size = 0
            entry_id = add_extraction_entry(
                file_name=src.name,
                file_size=file_size,
                source_path=file_path,
                output_path="",
                status=STATUS_PENDING,
            )
            if entry_id:
                tasks.append((entry_id, file_path))

        # Clear files and switch to history view (like Translate Document)
        self._handle_clear_all()
        self.extraction_history.refresh_history(force=True)

        if not tasks:
            return

        self._start_worker(tasks, ocr_method, src_lang, extract_method)

    def _handle_re_extract(
        self,
        tasks: list[tuple[int, str]],
    ) -> None:
        """Re-extracts text from images (triggered by history re-extract)."""
        if self._worker is not None:
            CustomMessageDialog.show_message(
                self.window_context,
                tr("dialog.extract_busy_title"),
                tr("dialog.extract_busy_msg"),
            )
            return

        if not self._check_extract_requirements():
            return

        # Show source language dialog
        from src.constants.settings import (  # noqa: PLC0415
            SETTING_LLM_MODEL_EXTRACT,
        )

        src_lang, _, _model_id, accepted = SourceLanguageDialog.get_selection(
            self.window_context,
            model_setting_key=SETTING_LLM_MODEL_EXTRACT,
        )
        if not accepted:
            return

        # Reset existing entries to "Pending" (like re-translate)
        for entry_id, _ in tasks:
            update_extraction_status(entry_id, STATUS_PENDING)
        self.extraction_history.refresh_history(force=True)

        ocr_method = load_setting(SETTING_OCR_METHOD, OCR_METHOD_TESSERACT)
        extract_method = load_setting(
            SETTING_EXTRACT_METHOD,
            EXTRACT_METHOD_OCR,
        )
        self._start_worker(tasks, ocr_method, src_lang, extract_method)

    def _start_worker(
        self,
        tasks: list[tuple[int, str]],
        ocr_method: str,
        src_lang: str,
        extract_method: str = EXTRACT_METHOD_OCR,
    ) -> None:
        """Starts the extraction background worker."""
        from src.constants.settings import (  # noqa: PLC0415
            SETTING_LAST_EXTRACT_FORMAT,
            SETTING_LLM_MODEL_EXTRACT,
        )
        from src.utils.config_manager import (  # noqa: PLC0415
            load_model_for_feature,
            parse_model_id,
        )

        self._pending_tasks = tasks
        self._output_format = load_setting(SETTING_LAST_EXTRACT_FORMAT, ".txt")
        selected_model = load_model_for_feature(SETTING_LLM_MODEL_EXTRACT)
        llm_provider, llm_model = (
            parse_model_id(selected_model) if selected_model else (None, None)
        )

        self._worker = _ExtractionWorker(
            tasks,
            ocr_method,
            src_lang,
            extract_method,
            llm_provider=llm_provider,
            llm_model=llm_model,
        )
        self._worker.finished_ok.connect(self._on_finished)
        self._worker.start()

    def _on_finished(self, results: list[tuple[int, str, str]]) -> None:
        """Saves extracted text and updates existing DB entries."""
        from src.constants.settings import (  # noqa: PLC0415
            SETTING_EXTRACT_AUTO_REMOVE,
        )

        if self._worker is not None:
            self._worker.wait()
            self._worker = None
        fmt = self._output_format
        auto_remove = bool(load_setting(SETTING_EXTRACT_AUTO_REMOVE, False))

        for entry_id, image_path, text in results:
            src = Path(image_path)
            out = generate_extraction_output_path(src, ext=fmt)
            try:
                _write_extraction_output(out, text)
                if auto_remove:
                    delete_extraction_entry(entry_id)
                else:
                    update_extraction_status(
                        entry_id, STATUS_DONE, output_path=str(out)
                    )
            except Exception as exc:
                logger.error("Failed to save %s: %s", out, exc)
                update_extraction_status(
                    entry_id, STATUS_FAILED, error_message=str(exc)
                )

        self.extraction_history.refresh_history(force=True)


# ── Factory function ──────────────────────────────────────────────────────────


def create_extract_text_page(window: QMainWindow) -> QWidget:
    """Factory function for the Extract Text page.

    Args:
        window: The main window instance for dialog parenting.

    Returns:
        QWidget: The configured page widget.
    """
    return ExtractTextPage(window)
