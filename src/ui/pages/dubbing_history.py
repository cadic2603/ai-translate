"""Dubbing history page showing video dubbing results with progress."""

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
    style_outlined_primary_button,
    style_primary_button,
    style_table,
    style_warning_button,
    tr,
)
from src.constants.errors import display_error_message
from src.constants.history import (
    STATUS_GENERATING,
    STATUS_PAUSED,
    STATUS_PENDING,
    display_status,
)
from src.core.database import (
    batch_pause_dubbing_entries,
    batch_resume_dubbing_entries,
    delete_dubbing_entry,
    get_dubbing_fingerprint,
    get_dubbing_history,
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
    "table.progress",
    "table.date",
]


class DubbingHistoryPage(QWidget):
    """History page displaying dubbing results with progress."""

    # Emitted when user requests re-dub: [(entry_id, source_path), ...]
    re_dub_requested = Signal(list)
    # Emitted when user requests continue: (tasks, src_lang, target_lang)
    continue_requested = Signal(list, str, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the dubbing history page."""
        super().__init__(parent)
        # Change-detection fingerprint to avoid unnecessary table rebuilds
        self._last_fingerprint: tuple[int, int, str] | None = None
        self._setup_ui()

        # Debounced search timer
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(SEARCH_DEBOUNCE_MS)
        self.search_timer.timeout.connect(
            lambda: self.refresh_history(force=True),
        )
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
            tr("page.dubbing_history"),
            tr_key="page.dubbing_history",
        )

        # --- Error Banner (own row, above actions) ---
        self.error_frame, self.error_label = create_banner("", variant="error")
        self.error_frame.setVisible(False)
        self.layout.addWidget(self.error_frame)

        # --- Actions Row ---
        self.actions_layout = QHBoxLayout()
        self.actions_layout.setSpacing(10)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(tr("dubbing_history.search_placeholder"))
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
            tr("btn.continue"),
            style_outlined_primary_button(),
            self.on_continue,
        )
        self.re_dub_btn = self._create_action_button(
            tr("dubbing.btn_re_dub"),
            style_primary_button(),
            self.on_re_dub,
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
        self,
        text: str,
        style: str,
        callback: Callable[[], None],
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
        """Configures the dubbing history table widget."""
        self.table = create_table(
            headers=[tr(k) for k in _HEADER_KEYS],
            interactive_columns=[0, 1, 2, 3, 4],
            column_widths={
                1: HISTORY_COL_WIDTH,
                2: HISTORY_COL_WIDTH,
                3: HISTORY_COL_WIDTH,
                4: HISTORY_DATE_COL_WIDTH,
            },
            enter_callback=self.on_open_file,
        )
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(
            QTableWidget.SelectionMode.ExtendedSelection,
        )
        self.table.sortByColumn(4, Qt.SortOrder.DescendingOrder)

        self.highlight_delegate = HighlightDelegate(self.table)
        self.highlight_delegate.set_selected_color(color("primary"))
        self.table.setItemDelegateForColumn(0, self.highlight_delegate)

        self._status_delegate = ForegroundPreservingDelegate(self.table)
        self.table.setItemDelegateForColumn(2, self._status_delegate)

        self.table.itemSelectionChanged.connect(self._update_button_states)
        self.table.horizontalHeader().sectionClicked.connect(
            self._on_header_clicked,
        )

    def apply_theme(self) -> None:
        """Re-applies theme-dependent styles."""
        self.table.setStyleSheet(style_table())
        self.search_input.setStyleSheet(style_input_field())
        self.open_btn.setStyleSheet(style_link_button())
        self.pause_btn.setStyleSheet(style_warning_button())
        self.continue_btn.setStyleSheet(style_outlined_primary_button())
        self.re_dub_btn.setStyleSheet(style_primary_button())
        self.delete_btn.setStyleSheet(style_delete_button())
        if hasattr(self.error_frame, "apply_theme"):
            self.error_frame.apply_theme()
        self.highlight_delegate.set_selected_color(color("primary"))
        self.refresh_history(force=True)

    def apply_language(self) -> None:
        """Re-applies all translatable text."""
        self.search_input.setPlaceholderText(tr("dubbing_history.search_placeholder"))
        self.open_btn.setText(tr("btn.open"))
        self.pause_btn.setText(tr("btn.pause"))
        self.continue_btn.setText(tr("btn.continue"))
        self.re_dub_btn.setText(tr("dubbing.btn_re_dub"))
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

        fingerprint = get_dubbing_fingerprint()
        if (
            not force
            and fingerprint is not None
            and fingerprint == self._last_fingerprint
        ):
            return
        self._last_fingerprint = fingerprint

        # 1. Save State
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

        # 2. Rebuild Table
        self.table.setSortingEnabled(False)
        self.table.blockSignals(True)

        entries = get_dubbing_history()
        if entries is None:
            self.table.setRowCount(0)
            self.table.blockSignals(False)
            self.table.setSortingEnabled(True)
            return

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

    def _fill_row(  # noqa: PLR0912
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
            _target_lang,
            status,
            progress,
            _error_message,
            created_at,
            subtitle_path,
            translated_subtitle_path,
            voice_path,
        ) = data

        # File Name column
        name_item = CaseInsensitiveSortItem(name)
        name_item.setData(Qt.ItemDataRole.UserRole, entry_id)
        name_item.setData(Qt.ItemDataRole.UserRole + 1, output_path)
        name_item.setData(Qt.ItemDataRole.UserRole + 2, _source_path)
        name_item.setData(Qt.ItemDataRole.UserRole + 3, _error_message)
        name_item.setData(Qt.ItemDataRole.UserRole + 4, _src_lang)
        name_item.setData(Qt.ItemDataRole.UserRole + 5, _target_lang)
        name_item.setData(Qt.ItemDataRole.UserRole + 6, subtitle_path)
        name_item.setData(Qt.ItemDataRole.UserRole + 7, translated_subtitle_path)
        name_item.setData(Qt.ItemDataRole.UserRole + 8, voice_path)
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
        elif status_lower == STATUS_PAUSED.lower():
            status_item.setForeground(QColor(color("warning")))
        elif status_lower == STATUS_PENDING.lower():
            status_item.setForeground(QColor(color("text_primary")))
        status_item.setData(Qt.ItemDataRole.UserRole, status)
        self.table.setItem(row, 2, status_item)

        # Progress column (integer percentage)
        try:
            pct = int(progress) if progress else 0
        except (ValueError, TypeError):
            pct = 0
        progress_item = NumericalSortItem(
            f"{pct}%" if pct else "",
            float(pct),
        )
        progress_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row, 3, progress_item)

        # Date column
        utc_dt = QDateTime.fromString(created_at, "yyyy-MM-dd HH:mm:ss")
        utc_dt.setTimeZone(QTimeZone.UTC)
        formatted_date = utc_dt.toLocalTime().toString(
            QLocale().dateTimeFormat(QLocale.FormatType.ShortFormat)
        )
        self.table.setItem(
            row,
            4,
            DateTimeSortItem(formatted_date, created_at),
        )

        # Restore selection state
        if entry_id in selected_ids:
            for col in range(self.table.columnCount()):
                self.table.item(row, col).setSelected(True)

        if entry_id == focused_id:
            index = self.table.model().index(row, 0)
            self.table.selectionModel().setCurrentIndex(
                index,
                QItemSelectionModel.SelectionFlag.NoUpdate,
            )

    def _update_button_states(self) -> None:
        """Dynamically enables/disables action buttons based on selection."""
        selected_rows = sorted({item.row() for item in self.table.selectedItems()})
        has_selection = len(selected_rows) > 0

        can_pause = False
        can_continue = False
        can_re_dub = has_selection
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
                can_pause = True
                is_active_selected = True
            elif raw_status in (STATUS_PAUSED, STATUS_FAILED):
                can_continue = True

        self.open_btn.setEnabled(has_selection)
        self.pause_btn.setEnabled(can_pause)
        self.continue_btn.setEnabled(can_continue)
        self.re_dub_btn.setEnabled(can_re_dub and not is_active_selected)
        self.delete_btn.setEnabled(has_selection)

        # Update error label
        self.error_label.setText(error_msg)
        self.error_frame.setVisible(bool(error_msg))

    def on_pause(self) -> None:
        """Pauses selected active dubbing entries."""
        selected_rows = sorted(
            {item.row() for item in self.table.selectedItems()},
        )
        if not selected_rows:
            return

        ids = [
            self.table.item(r, 0).data(Qt.ItemDataRole.UserRole) for r in selected_rows
        ]
        batch_pause_dubbing_entries(ids)
        self.refresh_history(force=True)

    def on_continue(self) -> None:
        """Resumes selected paused or failed dubbing entries."""
        selected_rows = sorted(
            {item.row() for item in self.table.selectedItems()},
        )
        if not selected_rows:
            return

        resumable = (STATUS_PAUSED, STATUS_FAILED)
        tasks: list[tuple[int, str]] = []
        ids_to_resume: list[int] = []
        src_lang = ""
        target_lang = ""

        for row in selected_rows:
            status_item = self.table.item(row, 2)
            if not status_item:
                continue
            raw_status = status_item.data(Qt.ItemDataRole.UserRole)
            if raw_status not in resumable:
                continue

            name_item = self.table.item(row, 0)
            entry_id = name_item.data(Qt.ItemDataRole.UserRole)
            source_path = name_item.data(Qt.ItemDataRole.UserRole + 2)

            # Read stored languages from the first resumable entry
            if not target_lang:
                src_lang = name_item.data(Qt.ItemDataRole.UserRole + 4) or ""
                target_lang = name_item.data(Qt.ItemDataRole.UserRole + 5) or ""

            if source_path and Path(source_path).exists():
                tasks.append((entry_id, source_path))
                ids_to_resume.append(entry_id)
            else:
                name = name_item.text()
                CustomMessageDialog.show_message(
                    self.window(),
                    tr("dialog.file_not_found"),
                    tr("dialog.file_missing_msg", name=name),
                )
                delete_dubbing_entry(entry_id)
                self.refresh_history(force=True)
                return

        if not tasks:
            return

        batch_resume_dubbing_entries(ids_to_resume)
        self.continue_requested.emit(tasks, src_lang, target_lang)
        self.refresh_history(force=True)

    def on_re_dub(self) -> None:
        """Re-dubs selected videos."""
        selected_rows = sorted(
            {item.row() for item in self.table.selectedItems()},
        )
        if not selected_rows:
            return

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
                delete_dubbing_entry(entry_id)
                self.refresh_history(force=True)
                return

        self.re_dub_requested.emit(tasks)

    def on_open_file(self) -> None:
        """Opens the output directory for selected entries."""
        selected_rows = sorted(
            {item.row() for item in self.table.selectedItems()},
        )
        for row in selected_rows:
            name_item = self.table.item(row, 0)
            output = name_item.data(Qt.ItemDataRole.UserRole + 1)
            if output and Path(output).exists():
                # Open the containing directory so all artifacts are visible
                QDesktopServices.openUrl(
                    QUrl.fromLocalFile(str(Path(output).parent)),
                )

    def on_delete_selected(self) -> None:
        """Removes selected dubbing history entries and output files."""
        selected_rows = sorted(
            {item.row() for item in self.table.selectedItems()},
            reverse=True,
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
            paths = delete_dubbing_entry(entry_id)
            # Delete all output files (video, subtitle, translated, voice)
            for file_path in paths:
                if file_path:
                    p = Path(file_path)
                    if p.is_file():
                        p.unlink(missing_ok=True)
            # Clean up persistent storage directory (checkpoints)
            import shutil  # noqa: PLC0415

            from src.utils.path_manager import get_dubbing_storage_dir  # noqa: PLC0415

            storage = get_dubbing_storage_dir(entry_id)
            shutil.rmtree(storage, ignore_errors=True)

        self.refresh_history(force=True)
