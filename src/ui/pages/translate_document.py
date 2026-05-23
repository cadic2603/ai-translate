"""Translate Document page UI for the AI Translate application.

Combines file selection and translation history into a unified interface.
A single shared FileDropWidget is reparented between two stacked views:
  - View 0 (default): drop area (full) + history table
  - View 1 (files selected): drop area (compact) + file selection list
"""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
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
    ALL_SUPPORTED_EXTENSIONS,
    DROP_AREA_HEIGHT,
    EMBEDDED_IMAGE_EXTENSIONS,
    FILE_FILTER,
    HEIGHT_CONTROL,
    SUPPORTED_IMAGES,
    style_delete_button,
    style_primary_button,
    tr,
)
from src.constants.settings import SETTING_TRANSLATE_DOC_IMAGES
from src.core.translator import setup_translation_tasks
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
    require_setup,
)
from src.ui.pages.history import HistoryPage
from src.ui.worker_utils import start_translation_worker
from src.utils.config_manager import check_llm_setup, check_ocr_setup, load_setting
from src.utils.file_utils import format_file_size

# Stacked widget indices
_VIEW_HISTORY = 0
_VIEW_FILES = 1

# Maximum number of files processed per drop/browse. Prevents UI freeze on
# accidental drops of huge trees. The user is notified when the cap is hit.
_MAX_FILES_PER_DROP = 100


class TranslateDocumentPage(QWidget):
    """Unified page for document translation and history management.

    Layout (QStackedWidget with two views sharing one FileDropWidget):
        - View 0: drop area (full) + history table
        - View 1: drop area (compact) + file selection list
    """

    def __init__(self, window: QMainWindow, parent: QWidget | None = None) -> None:
        """Initializes the TranslateDocumentPage."""
        super().__init__(parent)
        self.window_context = window
        self.selected_files: list[str] = []
        self._setup_ui()
        self._update_ui_state()

    # ------------------------------------------------------------------
    # UI Setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        """Builds the full page layout."""
        page_container, content_layout = create_page_container(
            tr("page.translate_document"),
            tr_key="page.translate_document",
        )
        content_layout.setSpacing(15)
        content_layout.setContentsMargins(20, 10, 20, 10)

        # We don't want the standalone title — the page renders its own
        # header via the surrounding navigation.
        page_container.header_label.setVisible(False)

        # Shared drop area (reparented between views on switch)
        self.drop_area = FileDropWidget()
        self.drop_area.setFixedHeight(DROP_AREA_HEIGHT)
        self.drop_area.files_dropped.connect(self._handle_files_dropped)

        # --- View 0: drop area + history table ---
        self.history_wrapper = QWidget()
        self.history_wrapper_layout = QVBoxLayout(self.history_wrapper)
        self.history_wrapper_layout.setContentsMargins(0, 0, 0, 0)
        self.history_wrapper_layout.setSpacing(15)

        self.history_view = HistoryPage()
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

        self._translate_shortcut = QShortcut(
            QKeySequence(get_shortcut("translate_document.translate")),
            self,
        )
        self._translate_shortcut.activated.connect(self._handle_primary_shortcut)

        self._focus_search_shortcut = QShortcut(
            QKeySequence(get_shortcut("common.focus_search")),
            self,
        )
        self._focus_search_shortcut.activated.connect(
            self.history_view.search_input.setFocus,
        )

        def _sync_shortcuts() -> None:
            self._translate_shortcut.setKey(
                QKeySequence(get_shortcut("translate_document.translate")),
            )
            self._focus_search_shortcut.setKey(
                QKeySequence(get_shortcut("common.focus_search")),
            )

        shortcuts_changed.connect(_sync_shortcuts)
        self._sync_shortcuts = _sync_shortcuts

    def _handle_primary_shortcut(self) -> None:
        """Dispatches Ctrl+Enter to the focused-context action.

        When the history table has focus with a selected row, re-translate
        the selected entries; otherwise fall through to the page's primary
        Translate action.
        """
        table = getattr(self.history_view, "table", None)
        if (
            table is not None
            and table.hasFocus()
            and table.selectionModel() is not None
            and table.selectionModel().hasSelection()
        ):
            self.history_view.on_retranslate()
            return
        self._handle_translate()

    def _create_file_list_section(self) -> QWidget:
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

        self.translate_btn = QPushButton(tr("btn.start_translation"))
        self.translate_btn.setFixedHeight(HEIGHT_CONTROL)
        self.translate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.translate_btn.setStyleSheet(style_primary_button())
        self.translate_btn.clicked.connect(self._handle_translate)
        header.addWidget(self.translate_btn)

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
        """Removes the standalone title and tightens margins.

        Makes the embedded HistoryPage blend into the combined layout.
        """
        if not hasattr(self.history_view, "page"):
            return
        page_layout = self.history_view.page.layout()
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(10)
        header = getattr(self.history_view.page, "header_label", None)
        if header is not None:
            header.setVisible(False)

    def apply_theme(self) -> None:
        """Re-applies theme-dependent styles for this page."""
        self.files_badge.setStyleSheet(style_file_count_badge())
        self.section_label.setStyleSheet(style_section_label())
        self.translate_btn.setStyleSheet(style_primary_button())
        self.clear_all_btn.setStyleSheet(style_delete_button())

    def apply_language(self) -> None:
        """Re-applies all translatable text for this page."""
        self.section_label.setText(tr("files.selected"))
        self.translate_btn.setText(tr("btn.start_translation"))
        self.clear_all_btn.setText(tr("btn.delete_all"))
        # Re-hide the history title after language update
        self._clean_history_view()

    # ------------------------------------------------------------------
    # UI State
    # ------------------------------------------------------------------

    def _update_ui_state(self) -> None:
        """Switches views and reparents the shared drop area."""
        count = len(self.selected_files)
        has_files = count > 0

        self.translate_btn.setEnabled(has_files)
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
        """Walks directories and collects up to ``_MAX_FILES_PER_DROP`` supported files.

        Only supported-extension files count toward the cap, so a directory
        full of junk (e.g. ``__pycache__``, README files, build artifacts)
        can't starve the cap and hide real documents deeper in the tree.

        Returns a tuple of (supported_files, unsupported_names, cap_hit_flag).
        Unsupported files are still reported so the user knows what was
        skipped.
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
                # Recursively walk, skipping hidden directories.
                for child in p.rglob("*"):
                    if any(part.startswith(".") for part in child.relative_to(p).parts):
                        continue
                    if not child.is_file():
                        continue
                    if child.suffix.lower() in ALL_SUPPORTED_EXTENSIONS:
                        supported.append(child)
                        if _cap_reached():
                            cap_hit = True
                            break
                    else:
                        unsupported.append(child.name)
            elif p.is_file():
                if p.suffix.lower() in ALL_SUPPORTED_EXTENSIONS:
                    supported.append(p)
                else:
                    unsupported.append(p.name)

        return supported, unsupported, cap_hit

    def _handle_files_dropped(self, files: list[str]) -> None:
        """Processes dropped or browsed files and directories."""
        if not files:
            files, _ = QFileDialog.getOpenFileNames(
                self.window_context,
                tr("files.select_dialog"),
                "",
                FILE_FILTER,
            )
        if not files:
            return

        added = False
        duplicates = 0

        supported, walk_unsupported, cap_hit = self._walk_dropped_paths(files)
        unsupported: set[str] = set(walk_unsupported)

        for p in supported:
            file_path = str(p)

            # Skip empty files.
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

        # One consolidated notification covering unsupported/duplicate/cap.
        self._notify_drop_results(
            unsupported=sorted(unsupported),
            duplicates=duplicates,
            cap_hit=cap_hit,
        )

        if added:
            self._update_ui_state()

    def _notify_drop_results(
        self,
        *,
        unsupported: list[str],
        duplicates: int,
        cap_hit: bool,
    ) -> None:
        """Shows a consolidated notification for skipped/capped drops."""
        if not unsupported and not duplicates and not cap_hit:
            return

        lines: list[str] = []

        if cap_hit:
            lines.append(
                tr("dialog.drop_capped", count=_MAX_FILES_PER_DROP),
            )

        if duplicates:
            lines.append(
                tr("dialog.drop_duplicates", count=duplicates),
            )

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

    def _handle_clear_all(self, *, confirm: bool = True) -> None:
        """Clears all selected files and switches back to history view.

        Args:
            confirm: Show a confirmation dialog first. Set to False for
                internal callers (e.g. post-translate cleanup).
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
    # Translation
    # ------------------------------------------------------------------

    def _handle_translate(self) -> None:
        """Validates setup, creates tasks, starts worker, clears files."""
        if not self.selected_files:
            return

        if not self._check_requirements():
            return
        from src.constants.settings import (  # noqa: PLC0415
            SETTING_LLM_MODEL_TRANSLATE_DOCUMENT,
        )

        result = LanguageSelectionDialog.get_selection(
            self.window_context,
            model_setting_key=SETTING_LLM_MODEL_TRANSLATE_DOCUMENT,
        )
        src_lang, target_lang, _model_id, ok = result
        if not ok:
            return

        tasks = setup_translation_tasks(
            self.selected_files,
            src_lang,
            target_lang,
        )
        if not tasks:
            # Downstream rejected every file (DB error or validation).
            # Keep the selection so the user can retry after fixing the cause.
            CustomMessageDialog.show_message(
                self.window_context,
                tr("dialog.translate_queue_failed_title"),
                tr("dialog.translate_queue_failed_msg"),
            )
            return

        worker = start_translation_worker(self.window_context, tasks)
        # Clear files (switches back to history view) and refresh table.
        self._handle_clear_all(confirm=False)
        self.history_view.refresh_history(force=True)

        if worker is None:
            # A translation is already running; the DB entries we just created
            # will be picked up by the active worker's pending-task poll.
            # Tell the user explicitly so the disappearing file list doesn't
            # look like their click was lost.
            CustomMessageDialog.show_message(
                self.window_context,
                tr("dialog.translate_queued_title"),
                tr("dialog.translate_queued_msg", count=len(tasks)),
            )

    def _needs_ocr(self) -> bool:
        """Returns True when any selected file may require OCR.

        Raw images always need OCR. Documents with embedded-image support
        (PDF, Office) also need OCR when the user has opted in via
        ``SETTING_TRANSLATE_DOC_IMAGES``.
        """
        for f in self.selected_files:
            ext = Path(f).suffix.lower()
            if ext in SUPPORTED_IMAGES:
                return True

        translate_embedded = bool(
            load_setting(SETTING_TRANSLATE_DOC_IMAGES, False),
        )
        if not translate_embedded:
            return False

        return any(
            Path(f).suffix.lower() in EMBEDDED_IMAGE_EXTENSIONS
            for f in self.selected_files
        )

    def _check_requirements(self) -> bool:
        """Ensures LLM and OCR are configured before translating.

        LLM is mandatory; OCR is conditionally required (raw images
        and embedded-image translation in documents).  Both gates use
        the shared ``require_setup`` helper — a "Cancel / Go to
        Settings" confirmation that routes the user to the relevant
        Settings tab on accept and aborts the queue on cancel.
        """
        if not require_setup(
            self.window_context,
            check_llm_setup,
            "dialog.llm_required_title",
            "dialog.llm_required_msg",
            4,
        ):
            return False

        if not self._needs_ocr():
            return True
        return require_setup(
            self.window_context,
            check_ocr_setup,
            "dialog.ocr_required_title",
            "dialog.ocr_required_msg",
            3,
        )


def create_translate_document_page(window: QMainWindow) -> QWidget:
    """Factory function for the merged Translate Document page."""
    return TranslateDocumentPage(window)
