"""Subtitle history page showing speech-to-text subtitle results.

A simplified version of the translation HistoryPage — no pause/resume,
no progress tracking, just a table of completed/failed subtitle generations with
Open, Re-generate, and Delete actions.
"""

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
    Signal,
)
from PySide6.QtGui import QColor, QDesktopServices, QShowEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from src.constants import (
    HEIGHT_CONTROL,
    HISTORY_COL_WIDTH,
    HISTORY_DATE_COL_WIDTH,
    SEARCH_DEBOUNCE_MS,
    STATUS_DONE,
    STATUS_FAILED,
    color,
    style_delete_button,
    style_input_field,
    style_link_button,
    style_primary_button,
    style_table,
    tr,
)
from src.constants.errors import display_error_message
from src.constants.history import STATUS_GENERATING, STATUS_PENDING, display_status
from src.core.database import (
    delete_subtitle_entry,
    get_subtitle_fingerprint,
    get_subtitle_history,
)
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
)
from src.utils.file_utils import format_file_size

# Table header translation keys (in column order)
_HEADER_KEYS = [
    "table.file_name",
    "table.size",
    "table.status",
    "table.date",
]


class SubtitleHistoryPage(QWidget):
    """History page displaying subtitle generation results."""

    # Emitted when user requests re-generate: [(entry_id, source_path), ...]
    re_generate_requested = Signal(list)

    def __init__(self, parent: QWidget | None = None) -> None:  # noqa: D107
        super().__init__(parent)
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
            tr("page.subtitle_history"),
            tr_key="page.subtitle_history",
        )

        # --- Error Banner (own row, above actions) ---
        self.error_frame, self.error_label = create_banner("", variant="error")
        self.error_frame.setVisible(False)
        self.layout.addWidget(self.error_frame)

        # --- Actions Row (search + buttons) ---
        self.actions_layout = QHBoxLayout()
        self.actions_layout.setSpacing(10)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(tr("subtitle_history.search_placeholder"))
        self.search_input.setStyleSheet(style_input_field())
        self.search_input.setFixedHeight(HEIGHT_CONTROL)
        self.search_input.setMaximumWidth(360)
        self.actions_layout.addWidget(self.search_input)

        self.actions_layout.addStretch()

        self.open_btn = self._create_action_button(
            tr("btn.open"), style_link_button(), self.on_open_file
        )
        self.re_generate_btn = self._create_action_button(
            tr("btn.re_generate"), style_primary_button(), self.on_re_generate
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
        """Configures the subtitle history table widget."""
        self.table = create_table(
            headers=[tr(k) for k in _HEADER_KEYS],
            interactive_columns=[0, 1, 2, 3],
            column_widths={
                1: HISTORY_COL_WIDTH,
                2: HISTORY_COL_WIDTH,
                3: HISTORY_DATE_COL_WIDTH,
            },
            enter_callback=self.on_open_file,
        )
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.table.sortByColumn(3, Qt.SortOrder.DescendingOrder)

        # Highlight delegate for file name column
        self.highlight_delegate = HighlightDelegate(self.table)
        self.highlight_delegate.set_selected_color(color("primary"))
        self.table.setItemDelegateForColumn(0, self.highlight_delegate)

        # Preserve status color on selection
        self._status_delegate = ForegroundPreservingDelegate(self.table)
        self.table.setItemDelegateForColumn(2, self._status_delegate)

        # Signals
        self.table.itemSelectionChanged.connect(self._update_button_states)
        self.table.horizontalHeader().sectionClicked.connect(self._on_header_clicked)

    def apply_theme(self) -> None:
        """Re-applies theme-dependent styles."""
        self.table.setStyleSheet(style_table())
        self.search_input.setStyleSheet(style_input_field())
        self.open_btn.setStyleSheet(style_link_button())
        self.re_generate_btn.setStyleSheet(style_primary_button())
        self.delete_btn.setStyleSheet(style_delete_button())
        if hasattr(self.error_frame, "apply_theme"):
            self.error_frame.apply_theme()
        self.highlight_delegate.set_selected_color(color("primary"))
        self.refresh_history(force=True)

    def apply_language(self) -> None:
        """Re-applies all translatable text."""
        self.search_input.setPlaceholderText(tr("subtitle_history.search_placeholder"))
        self.open_btn.setText(tr("btn.open"))
        self.re_generate_btn.setText(tr("btn.re_generate"))
        self.delete_btn.setText(tr("btn.delete"))
        for i, key in enumerate(_HEADER_KEYS):
            self.table.horizontalHeaderItem(i).setText(tr(key))
        self.refresh_history(force=True)

    def _on_header_clicked(self, _logical_index: int) -> None:
        """Clears selection when header is clicked."""
        self.table.blockSignals(True)
        self.table.clearSelection()
        self.table.setCurrentCell(-1, -1)
        self.table.blockSignals(False)
        self._update_button_states()

    def refresh_history(self, force: bool = False) -> None:
        """Refreshes table content while preserving selection and scroll."""
        if not self.isVisible() and not force:
            return

        fingerprint = get_subtitle_fingerprint()
        if (
            not force
            and fingerprint is not None
            and fingerprint == self._last_fingerprint
        ):
            return
        self._last_fingerprint = fingerprint

        # Save state
        scroll_pos = self.table.verticalScrollBar().value()
        selected_ids: set[int] = set()
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

        # Rebuild table
        self.table.setSortingEnabled(False)
        self.table.blockSignals(True)

        entries = get_subtitle_history()
        if entries is None:
            self.table.setRowCount(0)
            self.table.blockSignals(False)
            self.table.setSortingEnabled(True)
            return

        # Client-side search filter
        search_text = self.search_input.text().strip()
        self.highlight_delegate.set_search_text(search_text)
        if search_text:
            entries = [e for e in entries if search_text.lower() in e[1].lower()]

        self.table.setRowCount(0)
        self.table.setRowCount(len(entries))

        for row, data in enumerate(entries):
            self._fill_row(row, data, selected_ids, focused_id)

        # Finalize
        self.table.setSortingEnabled(True)
        self.table.verticalScrollBar().setValue(scroll_pos)
        self.table.blockSignals(False)
        self._update_button_states()

    def _fill_row(
        self,
        row: int,
        data: tuple,
        selected_ids: set[int],
        focused_id: int | None,
    ) -> None:
        """Creates and configures items for a single table row."""
        (
            entry_id,
            name,
            file_size,
            _source_path,
            output_path,
            _src_lang,
            status,
            _error_message,
            created_at,
        ) = data

        # File Name column (stores entry_id, output_path, source_path)
        name_item = CaseInsensitiveSortItem(name)
        name_item.setData(Qt.ItemDataRole.UserRole, entry_id)
        name_item.setData(Qt.ItemDataRole.UserRole + 1, output_path)
        name_item.setData(Qt.ItemDataRole.UserRole + 2, _source_path)
        name_item.setData(Qt.ItemDataRole.UserRole + 3, _error_message)
        self.table.setItem(row, 0, name_item)

        # Size column
        self.table.setItem(
            row,
            1,
            NumericalSortItem(
                format_file_size(file_size) if file_size else "0 B",
                float(file_size or 0),
            ),
        )

        # Status column
        status_item = CaseInsensitiveSortItem(display_status(status))
        status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        status_lower = status.lower()
        if status_lower == STATUS_DONE.lower():
            status_item.setForeground(QColor(color("success")))
        elif status_lower == STATUS_FAILED.lower():
            status_item.setForeground(QColor(color("error")))
        elif status_lower == STATUS_GENERATING.lower():
            status_item.setForeground(QColor(color("primary")))
        elif status_lower == STATUS_PENDING.lower():
            status_item.setForeground(QColor(color("text_primary")))
        status_item.setData(Qt.ItemDataRole.UserRole, status)
        self.table.setItem(row, 2, status_item)

        # Date column
        utc_dt = QDateTime.fromString(created_at, "yyyy-MM-dd HH:mm:ss")
        utc_dt.setTimeZone(QTimeZone.UTC)
        formatted_date = utc_dt.toLocalTime().toString(
            QLocale().dateTimeFormat(QLocale.FormatType.ShortFormat)
        )
        self.table.setItem(row, 3, DateTimeSortItem(formatted_date, created_at))

        # Restore selection state
        if entry_id in selected_ids:
            for col in range(self.table.columnCount()):
                self.table.item(row, col).setSelected(True)

        if entry_id == focused_id:
            index = self.table.model().index(row, 0)
            self.table.selectionModel().setCurrentIndex(
                index, QItemSelectionModel.SelectionFlag.NoUpdate
            )

    def _update_button_states(self) -> None:
        """Enables/disables action buttons based on selection."""
        selected_rows = sorted({item.row() for item in self.table.selectedItems()})
        has_selection = len(selected_rows) > 0
        is_active_selected = False

        # Error display logic
        error_msg = ""
        if len(selected_rows) == 1:
            row = selected_rows[0]
            name_item = self.table.item(row, 0)
            if name_item:
                err = name_item.data(Qt.ItemDataRole.UserRole + 3)
                if err:
                    error_msg = tr(
                        "error.prefix",
                        message=display_error_message(str(err)),
                    )

        for row in selected_rows:
            status_item = self.table.item(row, 2)
            if not status_item:
                continue
            raw_status = status_item.data(Qt.ItemDataRole.UserRole)
            if raw_status in (STATUS_PENDING, STATUS_GENERATING):
                is_active_selected = True

        self.open_btn.setEnabled(has_selection)
        self.re_generate_btn.setEnabled(has_selection and not is_active_selected)
        self.delete_btn.setEnabled(has_selection)

        # Update error label
        self.error_label.setText(error_msg)
        self.error_frame.setVisible(bool(error_msg))

    def on_re_generate(self) -> None:
        """Re-generates subtitles for selected files."""
        selected_rows = sorted({item.row() for item in self.table.selectedItems()})
        if not selected_rows:
            return

        # Collect entry IDs + source paths and validate they still exist
        tasks: list[tuple[int, str]] = []
        for row in selected_rows:
            entry_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            source_path = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole + 2)
            if source_path and Path(source_path).exists():
                tasks.append((entry_id, source_path))
            else:
                name = self.table.item(row, 0).text()
                CustomMessageDialog.show_message(
                    self.window(),
                    tr("dialog.file_not_found"),
                    tr("dialog.file_missing_msg", name=name),
                )
                delete_subtitle_entry(entry_id)
                self.refresh_history(force=True)
                return

        self.re_generate_requested.emit(tasks)

    def on_open_file(self) -> None:
        """Opens selected output files in the system default viewer."""
        selected_rows = sorted({item.row() for item in self.table.selectedItems()})
        for row in selected_rows:
            path = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole + 1)
            if path and Path(path).exists():
                QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def on_delete_selected(self) -> None:
        """Removes selected subtitle history entries and output files."""
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

        for row in selected_rows:
            entry_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            output_path = delete_subtitle_entry(entry_id)
            if output_path:
                p = Path(output_path)
                if p.is_file():
                    p.unlink(missing_ok=True)

        self.refresh_history(force=True)
