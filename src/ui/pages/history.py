"""History page UI for the AI Translate application.

Refactored for maintainability, stability, and readability.
"""

import shutil
import time
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import (
    QDateTime,
    QItemSelectionModel,
    QLocale,
    Qt,
    QTimer,
    QTimeZone,
    QUrl,
)
from PySide6.QtGui import QColor, QDesktopServices, QShowEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.constants import (
    ACTIVE_STATUSES,
    HEIGHT_CONTROL,
    HISTORY_COL_WIDTH,
    HISTORY_DATE_COL_WIDTH,
    REPROCESSABLE_STATUSES,
    SEARCH_DEBOUNCE_MS,
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_PAUSED,
    STATUS_PENDING,
    STATUS_TRANSLATING,
    SUPPORTED_IMAGES,
    color,
    localized_language_label,
    style_delete_button,
    style_input_field,
    style_link_button,
    style_outlined_primary_button,
    style_primary_button,
    style_table,
    style_warning_button,
    tr,
)
from src.constants.errors import ERR_NONE, display_error_message, get_error_message
from src.constants.history import display_status
from src.core.database import (
    batch_mark_deleting_history_entries,
    batch_pause_history_entries,
    batch_resume_history_entries,
    batch_retranslate_history_entries,
    delete_history_entry,
    get_history,
    get_history_fingerprint,
    is_any_translating,
)
from src.core.translator import TranslationWorker, resume_unfinished_translations
from src.ui.components import (
    CaseInsensitiveSortItem,
    DateTimeSortItem,
    ForegroundPreservingDelegate,
    HighlightDelegate,
    NumericalSortItem,
    create_banner,
    create_page_container,
    create_table,
)
from src.ui.dialogs import (
    CustomConfirmDialog,
    CustomMessageDialog,
    LanguageSelectionDialog,
)
from src.utils.config_manager import check_llm_setup, check_ocr_setup
from src.utils.file_utils import format_file_size


def _is_auto_source(value: str) -> bool:
    """Returns True when *value* is the auto-detect source language (empty string)."""
    return not value


# Table header translation keys (in column order)
_HEADER_KEYS = [
    "table.file_name",
    "table.size",
    "table.source",
    "table.target",
    "table.status",
    "table.progress",
    "table.date",
]


class HistoryPage(QWidget):
    """History page displaying translation logs with robust state management."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the translation history page."""
        super().__init__(parent)
        # Change-detection fingerprint to avoid unnecessary table rebuilds
        self._last_fingerprint: tuple[int, int, str] | None = None
        self._setup_ui()

        # Debounced search timer
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(SEARCH_DEBOUNCE_MS)
        self.search_timer.timeout.connect(lambda: self.refresh_history(force=True))
        self.search_input.textChanged.connect(self.search_timer.start)

        # Background refresh timer
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_history)
        self.timer.start(1000)

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        """Refreshes immediately when the page becomes visible."""
        super().showEvent(event)
        self.refresh_history(force=True)

    def _setup_ui(self) -> None:
        """Initializes the UI components."""
        self.page, self.layout = create_page_container(
            tr("page.translation_history"),
            tr_key="page.translation_history",
        )

        # --- Error Banner (own row, above actions) ---
        self.error_frame, self.error_label = create_banner("", variant="error")
        self.error_frame.setVisible(False)
        self.layout.addWidget(self.error_frame)

        # --- Actions Row (search + buttons) ---
        self.actions_layout = QHBoxLayout()
        self.actions_layout.setSpacing(10)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(tr("history.search_placeholder"))
        self.search_input.setStyleSheet(style_input_field())
        self.search_input.setFixedHeight(HEIGHT_CONTROL)
        self.search_input.setMaximumWidth(360)
        self.actions_layout.addWidget(self.search_input)

        self.actions_layout.addStretch()

        self.open_btn = self._create_action_button(
            tr("btn.open"), style_link_button(), self.on_open_file
        )
        self.pause_btn = self._create_action_button(
            tr("btn.pause"), style_warning_button(), self.on_pause
        )
        self.continue_btn = self._create_action_button(
            tr("btn.continue"), style_outlined_primary_button(), self.on_continue
        )
        self.retranslate_btn = self._create_action_button(
            tr("btn.retranslate"), style_primary_button(), self.on_retranslate
        )
        self.delete_btn = self._create_action_button(
            tr("btn.delete"), style_delete_button(), self.on_delete_selected
        )

        self.layout.addLayout(self.actions_layout)

        # --- History Table ---
        self._setup_table()
        self.layout.addWidget(self.table)

        self.refresh_history(force=True)

        # Main Layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.addWidget(self.page)

    def _create_action_button(
        self, text: str, style: str, callback: Callable[[], None]
    ) -> QPushButton:
        """Helper to create stylized action buttons."""
        btn = QPushButton(text)
        btn.setFixedHeight(HEIGHT_CONTROL)
        btn.setStyleSheet(style)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(callback)
        btn.setEnabled(False)
        self.actions_layout.addWidget(btn)
        return btn

    def _setup_table(self) -> None:
        """Configures the history table widget."""
        self.table = create_table(
            headers=[tr(k) for k in _HEADER_KEYS],
            interactive_columns=[0, 1, 2, 3, 4, 5, 6],
            column_widths={
                1: HISTORY_COL_WIDTH,
                2: HISTORY_COL_WIDTH,
                3: HISTORY_COL_WIDTH,
                4: HISTORY_COL_WIDTH,
                5: HISTORY_COL_WIDTH,
                6: HISTORY_DATE_COL_WIDTH,
            },
            enter_callback=self.on_open_file,
        )
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.table.sortByColumn(6, Qt.SortOrder.DescendingOrder)

        # Highlight delegate for file name column
        self.highlight_delegate = HighlightDelegate(self.table)
        self.highlight_delegate.set_selected_color(color("primary"))
        self.table.setItemDelegateForColumn(0, self.highlight_delegate)

        # Preserve status color on selection
        self._status_delegate = ForegroundPreservingDelegate(self.table)
        self.table.setItemDelegateForColumn(4, self._status_delegate)

        # Signals
        self.table.itemSelectionChanged.connect(self._update_button_states)
        self.table.horizontalHeader().sectionClicked.connect(self._on_header_clicked)

    def apply_theme(self) -> None:
        """Re-applies theme-dependent styles."""
        self.table.setStyleSheet(style_table())
        self.search_input.setStyleSheet(style_input_field())
        self.open_btn.setStyleSheet(style_link_button())
        self.pause_btn.setStyleSheet(style_warning_button())
        self.continue_btn.setStyleSheet(style_outlined_primary_button())
        self.retranslate_btn.setStyleSheet(style_primary_button())
        self.delete_btn.setStyleSheet(style_delete_button())
        if hasattr(self.error_frame, "apply_theme"):
            self.error_frame.apply_theme()
        # Update selected color for file name delegate
        self.highlight_delegate.set_selected_color(color("primary"))
        # Force a full refresh to re-apply cell foreground colors
        self.refresh_history(force=True)

    def apply_language(self) -> None:
        """Re-applies all translatable text."""
        self.search_input.setPlaceholderText(tr("history.search_placeholder"))
        self.open_btn.setText(tr("btn.open"))
        self.pause_btn.setText(tr("btn.pause"))
        self.continue_btn.setText(tr("btn.continue"))
        self.retranslate_btn.setText(tr("btn.retranslate"))
        self.delete_btn.setText(tr("btn.delete"))
        # Update table headers
        for i, key in enumerate(_HEADER_KEYS):
            self.table.horizontalHeaderItem(i).setText(tr(key))
        self.refresh_history(force=True)

    def _on_header_clicked(self, logical_index: int) -> None:
        """Handles header clicks to clear selection and reset anchor."""
        self.table.blockSignals(True)
        self.table.clearSelection()
        self.table.setCurrentCell(-1, -1)
        self.table.blockSignals(False)
        self._update_button_states()

    def refresh_history(self, force: bool = False) -> None:
        """Refreshes table content while preserving selection, scroll, and focus."""
        if not self.isVisible() and not is_any_translating():
            return

        # Quick check: skip full rebuild if data hasn't changed
        fingerprint = get_history_fingerprint()
        if (
            not force
            and fingerprint is not None
            and fingerprint == self._last_fingerprint
        ):
            return
        self._last_fingerprint = fingerprint

        # 1. Save State
        scroll_pos = self.table.verticalScrollBar().value()
        selected_ids = set()
        focused_id = None

        current_item = self.table.currentItem()
        if current_item:
            focused_id = self.table.item(current_item.row(), 0).data(
                Qt.ItemDataRole.UserRole
            )

        for item in self.table.selectedItems():
            if item.column() == 0:
                h_id = item.data(Qt.ItemDataRole.UserRole)
                if h_id is not None:
                    selected_ids.add(h_id)

        # 2. Rebuild Table
        self.table.setSortingEnabled(False)
        self.table.blockSignals(True)

        entries = get_history()
        if entries is None:
            self.table.setRowCount(0)
            self.table.blockSignals(False)
            self.table.setSortingEnabled(True)
            return

        # Client-side filtering by file name
        search_text = self.search_input.text().strip()
        self.highlight_delegate.set_search_text(search_text)
        if search_text:
            entries = [e for e in entries if search_text.lower() in e[1].lower()]

        self.table.setRowCount(0)
        self.table.setRowCount(len(entries))

        for row, data in enumerate(entries):
            self._fill_row(row, data, selected_ids, focused_id)

        # 3. Finalize
        self.table.setSortingEnabled(True)
        self.table.verticalScrollBar().setValue(scroll_pos)
        self.table.blockSignals(False)
        self._update_button_states()

    def _fill_row(
        self, row: int, data: tuple, selected_ids: set[int], focused_id: int | None
    ) -> None:
        """Creates and configures items for a single table row."""
        (
            h_id,
            name,
            src,
            target,
            status,
            progress,
            created_at,
            size,
            path,
            err_code,
            err_message,
        ) = data

        # File Name Column
        name_item = CaseInsensitiveSortItem(name)
        name_item.setData(Qt.ItemDataRole.UserRole, h_id)
        name_item.setData(Qt.ItemDataRole.UserRole + 1, path)
        name_item.setData(Qt.ItemDataRole.UserRole + 2, err_code)
        # Store the raw error tag so the error-display path can
        # render service-specific copy (e.g. "Invalid Gemini API
        # key") via display_error_message, which knows how to parse
        # the ``AUTH_ERROR:Service`` suffix.  Falls back to the
        # numeric code path for legacy rows that have err_code but
        # no err_message (pre-migration).
        name_item.setData(Qt.ItemDataRole.UserRole + 3, err_message)
        self.table.setItem(row, 0, name_item)

        # Data Columns
        self.table.setItem(
            row,
            1,
            NumericalSortItem(
                format_file_size(size) if size else "0 B", float(size or 0)
            ),
        )

        # Source language: show localized label, keep DB value in UserRole
        # so search and re-translate continue to work on the canonical
        # English form.  Auto-detect renders the locale's "Auto" copy;
        # everything else routes through ``localized_language_label`` so
        # a Vietnamese user sees "Tiếng Việt" instead of "Vietnamese"
        # (matching the language-picker convention).
        if _is_auto_source(src):
            display_src = tr("common.lang_auto_detect")
        else:
            display_src = localized_language_label(src)
        src_item = CaseInsensitiveSortItem(display_src)
        src_item.setData(Qt.ItemDataRole.UserRole, src)
        self.table.setItem(row, 2, src_item)

        # Target language: same localization treatment.  ``UserRole``
        # holds the canonical English value for the re-translate flow.
        target_item = CaseInsensitiveSortItem(localized_language_label(target))
        target_item.setData(Qt.ItemDataRole.UserRole, target)
        self.table.setItem(row, 3, target_item)

        # Status Column
        status_item = CaseInsensitiveSortItem(display_status(status))
        status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self._style_status_item(status_item, status, err_code)
        self.table.setItem(row, 4, status_item)

        # Progress Column
        self.table.setItem(
            row, 5, NumericalSortItem(f"{progress}%", float(progress or 0))
        )

        # Date Column (Locale aware display, ISO sort key)
        utc_dt = QDateTime.fromString(created_at, "yyyy-MM-dd HH:mm:ss")
        utc_dt.setTimeZone(QTimeZone.UTC)
        formatted_date = utc_dt.toLocalTime().toString(
            QLocale().dateTimeFormat(QLocale.FormatType.ShortFormat)
        )
        self.table.setItem(
            row,
            6,
            DateTimeSortItem(formatted_date, created_at),
        )

        # Restore State
        if h_id in selected_ids:
            for col in range(self.table.columnCount()):
                self.table.item(row, col).setSelected(True)

        if h_id == focused_id:
            index = self.table.model().index(row, 0)
            self.table.selectionModel().setCurrentIndex(
                index, QItemSelectionModel.SelectionFlag.NoUpdate
            )

    def _style_status_item(
        self, item: QTableWidgetItem, status: str, err_code: int | None
    ) -> None:
        """Applies semantic coloring and tooltips to the status cell."""
        status_lower = status.lower()
        if status_lower == STATUS_DONE.lower():
            item.setForeground(QColor(color("success")))
        elif status_lower == STATUS_FAILED.lower():
            item.setForeground(QColor(color("error")))
        elif status_lower == STATUS_PENDING.lower():
            item.setForeground(QColor(color("text_primary")))
        elif status_lower == STATUS_TRANSLATING.lower():
            item.setForeground(QColor(color("primary")))
        elif status_lower == STATUS_PAUSED.lower():
            item.setForeground(QColor(color("warning")))

    def _update_button_states(self) -> None:
        """Dynamically enables/disables action buttons based on selection."""
        selected_rows = sorted({item.row() for item in self.table.selectedItems()})
        has_selection = len(selected_rows) > 0

        can_pause = False
        can_continue = False
        can_retranslate = has_selection
        is_active_selected = False

        # Error display logic
        error_msg = ""
        if len(selected_rows) == 1:
            row = selected_rows[0]
            name_item = self.table.item(row, 0)
            err_code = (
                name_item.data(Qt.ItemDataRole.UserRole + 2) if name_item else None
            )
            err_message = (
                name_item.data(Qt.ItemDataRole.UserRole + 3) if name_item else None
            )
            if err_code is not None and err_code != ERR_NONE:
                # Prefer the raw tag (carries ``:Service`` suffix for
                # AUTH_ERROR, so the user sees "Invalid Google Cloud
                # API key" instead of generic "Invalid API key").
                # Falls back to the numeric-code path for legacy
                # rows from before the error_message column existed.
                if err_message:
                    localised = display_error_message(err_message)
                else:
                    localised = get_error_message(err_code)
                error_msg = tr("error.prefix", message=localised)

        for row in selected_rows:
            status_item = self.table.item(row, 4)
            if not status_item:
                continue

            status = status_item.text()
            if status in ACTIVE_STATUSES:
                can_pause = True
                is_active_selected = True
            elif status in (STATUS_PAUSED, STATUS_FAILED):
                can_continue = True
            elif status not in REPROCESSABLE_STATUSES:
                # Unknown or transitional statuses are treated as "active"
                # to prevent retranslate on rows still in flight.
                is_active_selected = True

        self.open_btn.setEnabled(has_selection)
        self.pause_btn.setEnabled(can_pause)
        self.continue_btn.setEnabled(can_continue)
        self.retranslate_btn.setEnabled(can_retranslate and not is_active_selected)
        self.delete_btn.setEnabled(has_selection)

        # Update error label
        self.error_label.setText(error_msg)
        self.error_frame.setVisible(bool(error_msg))

    def _validate_selection(self) -> list[int]:
        """Ensures selected files exist before acting on them."""
        selected_rows = sorted({item.row() for item in self.table.selectedItems()})
        valid_rows = []
        missing_found = False

        for row in selected_rows:
            h_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            path = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole + 1)
            name = self.table.item(row, 0).text()

            if path and Path(path).exists():
                valid_rows.append(row)
            else:
                CustomMessageDialog.show_message(
                    self.window(),
                    tr("dialog.file_not_found"),
                    tr("dialog.file_missing_msg", name=name),
                )
                delete_history_entry(h_id)
                missing_found = True

        if missing_found:
            self.refresh_history(force=True)
            return []
        return valid_rows

    def _check_requirements(self, paths: list[str]) -> bool:
        """Ensures LLM and OCR are configured before starting translation.

        Args:
            paths: File paths of the selected history entries.
        """
        if not check_llm_setup():
            confirmed = CustomConfirmDialog.confirm(
                self.window(),
                tr("dialog.llm_required_title"),
                tr("dialog.llm_required_msg"),
                confirm_text=tr("btn.go_to_settings"),
            )
            window = self.window()
            if confirmed and hasattr(window, "navigate_to_settings_tab"):
                window.navigate_to_settings_tab(4)  # LLM tab
            return False

        has_images = any(Path(p).suffix.lower() in SUPPORTED_IMAGES for p in paths if p)
        if has_images and not check_ocr_setup():
            confirmed = CustomConfirmDialog.confirm(
                self.window(),
                tr("dialog.ocr_required_title"),
                tr("dialog.ocr_required_msg"),
                confirm_text=tr("btn.go_to_settings"),
            )
            window = self.window()
            if confirmed and hasattr(window, "navigate_to_settings_tab"):
                window.navigate_to_settings_tab(3)  # OCR tab
            return False

        return True

    def on_pause(self) -> None:
        """Handles the Pause action."""
        valid_rows = self._validate_selection()
        if not valid_rows:
            return

        ids = [self.table.item(r, 0).data(Qt.ItemDataRole.UserRole) for r in valid_rows]
        batch_pause_history_entries(ids)

        self.refresh_history(force=True)

    def on_continue(self) -> None:
        """Handles the Continue action for Paused and Failed tasks.

        Resumes from the last saved checkpoint so completed stages
        (OCR, translated chunks, etc.) are not repeated.
        """
        valid_rows = self._validate_selection()
        if not valid_rows:
            return

        resumable = (STATUS_PAUSED, STATUS_FAILED)
        tasks = []
        ids_to_resume = []
        for row in valid_rows:
            if self.table.item(row, 4).text() in resumable:
                h_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
                path = self.table.item(row, 0).data(
                    Qt.ItemDataRole.UserRole + 1,
                )
                src = (
                    self.table.item(row, 2).data(
                        Qt.ItemDataRole.UserRole,
                    )
                    or ""
                )
                # Read the canonical English label from UserRole, NOT
                # ``.text()`` — the cell now displays the localised
                # form (Vietnamese: "Tiếng Việt") and the engine
                # expects "Vietnamese".
                target = (
                    self.table.item(row, 3).data(
                        Qt.ItemDataRole.UserRole,
                    )
                    or self.table.item(row, 3).text()
                )
                tasks.append((h_id, path, src, target))
                ids_to_resume.append(h_id)

        if not tasks:
            return

        # Verify LLM and OCR are configured before resuming
        task_paths = [t[1] for t in tasks]
        if not self._check_requirements(task_paths):
            return

        batch_resume_history_entries(ids_to_resume)
        self._start_worker_if_needed(tasks)
        self.refresh_history(force=True)

    def on_retranslate(self) -> None:
        """Handles the Re-translate action with language re-selection."""
        valid_rows = self._validate_selection()
        if not valid_rows:
            return

        # Verify LLM and OCR are configured before showing language dialog
        selected_paths = [
            self.table.item(r, 0).data(Qt.ItemDataRole.UserRole + 1) for r in valid_rows
        ]
        if not self._check_requirements(selected_paths):
            return

        # Pre-select languages from the first selected row
        first_row = valid_rows[0]
        prev_src = (
            self.table.item(first_row, 2).data(
                Qt.ItemDataRole.UserRole,
            )
            or ""
        )
        # Same canonical-label rule as the resume path: the displayed
        # text is the localised form; the LanguageSelectionDialog
        # expects the English DB value.
        prev_target = (
            self.table.item(first_row, 3).data(
                Qt.ItemDataRole.UserRole,
            )
            or self.table.item(first_row, 3).text()
        )
        from src.constants.settings import (  # noqa: PLC0415
            SETTING_LLM_MODEL_TRANSLATE_DOCUMENT,
        )

        result = LanguageSelectionDialog.get_selection(
            self.window(),
            prev_src,
            prev_target,
            model_setting_key=SETTING_LLM_MODEL_TRANSLATE_DOCUMENT,
        )
        src_lang, target_lang, _model_id, ok = result
        if not ok:
            return

        tasks = []
        ids_to_reset = []
        for row in valid_rows:
            if self.table.item(row, 4).text() in REPROCESSABLE_STATUSES:
                h_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
                path = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole + 1)
                tasks.append((h_id, path, src_lang, target_lang))
                ids_to_reset.append(h_id)

        if not tasks:
            return

        # Clear checkpoints to ensure fresh start with new languages
        from src.core.checkpoint import (  # noqa: PLC0415
            clear_checkpoints,
            get_storage_dir,
        )

        for _h_id, path, _src, _tgt in tasks:
            if path:
                clear_checkpoints(get_storage_dir(path))

        # Reset status and update languages in DB
        batch_retranslate_history_entries(ids_to_reset, src_lang, target_lang)

        self._start_worker_if_needed(tasks)
        self.refresh_history(force=True)

    def _start_worker_if_needed(self, tasks: list[tuple[int, str, str, str]]) -> None:
        """Initiates a background worker if one isn't already active."""
        if not TranslationWorker.is_busy():
            window = self.window()
            worker = TranslationWorker(tasks)
            # Store workers on the main window to prevent garbage-collection
            # while the background thread is still running.
            if not hasattr(window, "_workers"):
                window._workers = []
            window._workers.append(worker)

            def on_done() -> None:
                if worker in window._workers:
                    window._workers.remove(worker)
                resume_unfinished_translations()

            worker.finished.connect(on_done)
            worker.start()

    def on_open_file(self) -> None:
        """Opens selected files in system default viewer."""
        valid_rows = self._validate_selection()
        for row in valid_rows:
            path = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole + 1)
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def on_delete_selected(self) -> None:
        """Removes selected history entries and their disk folders."""
        selected_rows = sorted(
            {item.row() for item in self.table.selectedItems()}, reverse=True
        )
        if not selected_rows:
            return

        count = len(selected_rows)
        if not CustomConfirmDialog.confirm(
            self.window(),
            tr("dialog.delete_items"),
            tr("dialog.delete_items_msg", count=count),
            is_danger=True,
        ):
            return

        ids = [
            self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            for row in selected_rows
        ]

        batch_mark_deleting_history_entries(ids)

        # Grace period to let any running worker notice the "Deleting" status
        # and skip these entries before we remove their files from disk.
        time.sleep(0.1)

        for h_id in ids:
            storage_path = delete_history_entry(h_id)
            if storage_path:
                target_dir = (
                    Path(storage_path).parent
                    if Path(storage_path).is_file()
                    else Path(storage_path)
                )
                # Safety guard: only remove directories inside the "translations"
                # tree to prevent accidental deletion of unrelated paths.
                if target_dir.exists() and "translations" in target_dir.parts:
                    shutil.rmtree(target_dir, ignore_errors=True)

        self.refresh_history(force=True)


def create_history_page() -> QWidget:
    """Creates and returns a new HistoryPage instance."""
    return HistoryPage()
