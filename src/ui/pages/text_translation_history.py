"""Embeddable text translation history table for the Translate Text page."""

from __future__ import annotations

from PySide6.QtCore import (
    QDateTime,
    QItemSelectionModel,
    QLocale,
    Qt,
    QTimer,
    QTimeZone,
    Signal,
)
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QPlainTextEdit,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from src.constants import (
    FLAG_ICON_HEIGHT,
    FLAG_ICON_WIDTH,
    FLAGS_DIR,
    HEIGHT_CONTROL,
    HISTORY_COL_WIDTH,
    HISTORY_DATE_COL_WIDTH,
    LANGUAGES,
    RADIUS_BUTTON,
    SEARCH_DEBOUNCE_MS,
    color,
    localized_language_label,
    style_primary_button,
    style_scrollbar,
    style_secondary_button,
    style_table,
    tr,
)
from src.core.database import (
    delete_text_translation_entry,
    get_text_translation_fingerprint,
    get_text_translation_history,
)
from src.ui.components import (
    CaseInsensitiveSortItem,
    DateTimeSortItem,
    HighlightDelegate,
    create_table,
)
from src.ui.dialogs import BaseDialog, CustomConfirmDialog

# Maximum characters shown in table preview columns
_PREVIEW_LEN = 80

# Table header translation keys (in column order)
_HEADER_KEYS = [
    "table.source_preview",
    "table.translated_preview",
    "table.source",
    "table.target",
    "table.date",
]

# Custom data roles stored on the source-preview item (column 0)
_ROLE_ENTRY_ID = Qt.ItemDataRole.UserRole
_ROLE_SOURCE_TEXT = Qt.ItemDataRole.UserRole + 1
_ROLE_TRANSLATED_TEXT = Qt.ItemDataRole.UserRole + 2
_ROLE_SRC_LANG = Qt.ItemDataRole.UserRole + 3
_ROLE_TARGET_LANG = Qt.ItemDataRole.UserRole + 4


def _truncate(text: str, max_len: int = _PREVIEW_LEN) -> str:
    """Truncates text to max_len, collapsing newlines into spaces."""
    flat = " ".join(text.split())
    if len(flat) <= max_len:
        return flat
    return flat[:max_len] + "..."


def _style_detail_card() -> str:
    """Returns QSS for the card container in the detail dialog."""
    return (
        f"#DetailCard {{"
        f"  background-color: {color('component_bg')};"
        f"  border: 1px solid {color('border_light')};"
        f"  border-radius: {RADIUS_BUTTON}px;"
        f"}}"
    )


def _style_detail_text() -> str:
    """Returns QSS for the borderless text areas inside the detail card."""
    return (
        f"QPlainTextEdit {{"
        f"  background-color: transparent;"
        f"  color: {color('text_primary')};"
        f"  border: none;"
        f"  padding: 12px 16px;"
        f"  font-size: 15px;"
        f"  selection-background-color: rgba(62, 121, 247, 0.2);"
        f"}}" + style_scrollbar()
    )


def _style_detail_label() -> str:
    """Returns QSS for section labels inside the detail card."""
    return (
        f"font-size: 11px; font-weight: 600;"
        f" color: {color('text_secondary')};"
        f" text-transform: uppercase; letter-spacing: 0.5px;"
        f" background: transparent; border: none;"
    )


def _separator_style() -> str:
    """Returns inline QSS for 1px separator widgets."""
    return f"background-color: {color('border_light')};"


# Reverse map: language label → flag icon filename
_LABEL_TO_FLAG: dict[str, str] = {label: icon for _, label, icon, _ in LANGUAGES}


def _build_lang_header(label: str, h_pad: int, v_pad: int) -> QWidget:
    """Builds a header cell with a flag icon and language label."""
    from PySide6.QtGui import QPixmap  # noqa: PLC0415
    from PySide6.QtWidgets import QHBoxLayout, QLabel  # noqa: PLC0415

    container = QWidget()
    layout = QHBoxLayout(container)
    layout.setContentsMargins(h_pad, v_pad, h_pad, v_pad)
    layout.setSpacing(8)

    # Flag icon (or globe emoji for auto-detect)
    icon_lbl = QLabel()
    icon_lbl.setFixedSize(FLAG_ICON_WIDTH, FLAG_ICON_HEIGHT)
    icon_lbl.setStyleSheet("background: transparent; border: none;")

    flag_file = _LABEL_TO_FLAG.get(label)
    if flag_file:
        pix = QPixmap(f"{FLAGS_DIR}/{flag_file}.png")
        if not pix.isNull():
            icon_lbl.setPixmap(
                pix.scaled(
                    FLAG_ICON_WIDTH,
                    FLAG_ICON_HEIGHT,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                ),
            )
    else:
        # Auto-detect: use globe emoji icon
        from src.ui.dialogs import _create_emoji_icon  # noqa: PLC0415

        icon = _create_emoji_icon()
        icon_lbl.setPixmap(icon.pixmap(FLAG_ICON_WIDTH, FLAG_ICON_HEIGHT))

    text_lbl = QLabel(label)
    text_lbl.setStyleSheet(_style_detail_label())

    layout.addWidget(icon_lbl)
    layout.addWidget(text_lbl)
    layout.addStretch()
    return container


# ── Embeddable table widget ───────────────────────────────────────────────


class TextTranslationHistoryWidget(QWidget):
    """Table-only history widget. Header controls are managed by the parent."""

    # Emitted when table selection changes (True if any row selected)
    selection_changed = Signal(bool)

    # Emitted when user requests to re-use a history entry
    # Args: entry_id, source_text, translated_text, src_lang, target_lang
    reuse_requested = Signal(int, str, str, str, str)

    def __init__(
        self,
        window: QWidget,
        parent: QWidget | None = None,
    ) -> None:
        """Initializes the TextTranslationHistoryWidget."""
        super().__init__(parent)
        self.window_context = window
        self._last_fingerprint: tuple[int, int] | None = None
        self._search_text = ""
        self._setup_ui()

        # Debounced search timer (triggered by set_search_text)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(SEARCH_DEBOUNCE_MS)
        self._search_timer.timeout.connect(
            lambda: self.refresh_history(force=True),
        )

        # Background refresh timer
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self.refresh_history)
        self._refresh_timer.start(1000)

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        """Refreshes immediately when the widget becomes visible."""
        super().showEvent(event)
        self.refresh_history(force=True)

    def _setup_ui(self) -> None:
        """Initializes the table."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._setup_table()
        layout.addWidget(self.table)

        self.refresh_history(force=True)

    def _setup_table(self) -> None:
        """Configures the text translation history table widget."""
        self.table = create_table(
            headers=[tr(k) for k in _HEADER_KEYS],
            interactive_columns=list(range(len(_HEADER_KEYS))),
            column_widths={
                2: HISTORY_COL_WIDTH,
                3: HISTORY_COL_WIDTH,
                4: HISTORY_DATE_COL_WIDTH,
            },
            enter_callback=self.on_view_selected,
        )
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(
            QTableWidget.SelectionMode.ExtendedSelection,
        )
        self.table.sortByColumn(4, Qt.SortOrder.DescendingOrder)

        # Highlight delegate for source text column
        self.highlight_delegate = HighlightDelegate(self.table)
        self.highlight_delegate.set_selected_color(color("primary"))
        self.table.setItemDelegateForColumn(0, self.highlight_delegate)

        # Signals
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.horizontalHeader().sectionClicked.connect(
            self._on_header_clicked,
        )

    # ── External control ─────────────────────────────────────────────

    def set_search_text(self, text: str) -> None:
        """Sets the search filter text (debounced refresh)."""
        self._search_text = text
        self._search_timer.start()

    # ── Theme / Language ──────────────────────────────────────────────

    def apply_theme(self) -> None:
        """Re-applies theme-dependent styles."""
        self.table.setStyleSheet(style_table())
        self.highlight_delegate.set_selected_color(color("primary"))
        self.refresh_history(force=True)

    def apply_language(self) -> None:
        """Re-applies table header text."""
        for i, key in enumerate(_HEADER_KEYS):
            self.table.horizontalHeaderItem(i).setText(tr(key))
        self.refresh_history(force=True)

    # ── Refresh ───────────────────────────────────────────────────────

    def _on_header_clicked(self, _logical_index: int) -> None:
        """Clears selection when header is clicked."""
        self.table.blockSignals(True)
        self.table.clearSelection()
        self.table.setCurrentCell(-1, -1)
        self.table.blockSignals(False)
        self._on_selection_changed()

    def _on_selection_changed(self) -> None:
        """Emits selection_changed signal."""
        has = any(self.table.selectedItems())
        self.selection_changed.emit(has)

    def refresh_history(self, force: bool = False) -> None:
        """Refreshes table content while preserving selection and scroll."""
        if not self.isVisible() and not force:
            return

        fingerprint = get_text_translation_fingerprint()
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
                _ROLE_ENTRY_ID,
            )

        for item in self.table.selectedItems():
            if item.column() == 0:
                h_id = item.data(_ROLE_ENTRY_ID)
                if h_id is not None:
                    selected_ids.add(h_id)

        # Rebuild table
        self.table.setSortingEnabled(False)
        self.table.blockSignals(True)

        entries = get_text_translation_history()
        if entries is None:
            self.table.setRowCount(0)
            self.table.blockSignals(False)
            self.table.setSortingEnabled(True)
            return

        # Client-side search filter (searches both source and translated)
        search_text = self._search_text.strip()
        self.highlight_delegate.set_search_text(search_text)
        if search_text:
            lower = search_text.lower()
            entries = [
                e for e in entries if lower in e[1].lower() or lower in e[2].lower()
            ]

        self.table.setRowCount(0)
        self.table.setRowCount(len(entries))

        for row, data in enumerate(entries):
            self._fill_row(row, data, selected_ids, focused_id)

        # Finalize
        self.table.setSortingEnabled(True)
        self.table.verticalScrollBar().setValue(scroll_pos)
        self.table.blockSignals(False)
        self._on_selection_changed()

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
            source_text,
            translated_text,
            src_lang,
            target_lang,
            _,
            created_at,
        ) = data

        # Source preview (stores full texts and language info in custom roles)
        src_item = CaseInsensitiveSortItem(_truncate(source_text))
        src_item.setData(_ROLE_ENTRY_ID, entry_id)
        src_item.setData(_ROLE_SOURCE_TEXT, source_text)
        src_item.setData(_ROLE_TRANSLATED_TEXT, translated_text)
        src_item.setData(_ROLE_SRC_LANG, src_lang)
        src_item.setData(_ROLE_TARGET_LANG, target_lang)
        self.table.setItem(row, 0, src_item)

        # Translation preview
        tgt_item = CaseInsensitiveSortItem(_truncate(translated_text))
        self.table.setItem(row, 1, tgt_item)

        # Source language column.  Display the localised form (Vietnamese
        # user sees "Tiếng Việt" instead of "Vietnamese") but keep the
        # raw English DB value in ``_ROLE_ENTRY_ID`` so the re-use flow
        # can still hand it back to the engine unchanged.
        if src_lang:
            src_display = localized_language_label(src_lang)
        else:
            src_display = tr("common.lang_auto_detect")
        src_lang_item = CaseInsensitiveSortItem(src_display)
        src_lang_item.setData(_ROLE_ENTRY_ID, src_lang)
        self.table.setItem(row, 2, src_lang_item)

        # Target language column — same localisation treatment.
        # Stash the canonical English value on the cell for the
        # re-use flow (which reads the row via ``_get_row_data``).
        target_lang_item = CaseInsensitiveSortItem(
            localized_language_label(target_lang),
        )
        target_lang_item.setData(_ROLE_ENTRY_ID, target_lang)
        self.table.setItem(row, 3, target_lang_item)

        # Date column
        utc_dt = QDateTime.fromString(created_at, "yyyy-MM-dd HH:mm:ss")
        utc_dt.setTimeZone(QTimeZone.UTC)
        formatted_date = utc_dt.toLocalTime().toString(
            QLocale().dateTimeFormat(QLocale.FormatType.ShortFormat),
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

    # ── Helpers ────────────────────────────────────────────────────────

    def _first_selected_row(self) -> int | None:
        """Returns the lowest selected row index, or None."""
        rows = {item.row() for item in self.table.selectedItems()}
        return min(rows) if rows else None

    def _get_row_data(
        self,
        row: int,
    ) -> tuple[str, str, str, str]:
        """Extracts (source, translated, src_lang, target_lang) from a row."""
        item = self.table.item(row, 0)
        return (
            item.data(_ROLE_SOURCE_TEXT) or "",
            item.data(_ROLE_TRANSLATED_TEXT) or "",
            item.data(_ROLE_SRC_LANG) or "",
            item.data(_ROLE_TARGET_LANG) or "",
        )

    # ── Actions ───────────────────────────────────────────────────────

    def on_view_selected(self) -> None:
        """Shows full source and translated text in a detail dialog."""
        row = self._first_selected_row()
        if row is None:
            return

        entry_id = self.table.item(row, 0).data(_ROLE_ENTRY_ID)
        source, translated, src_lang, target_lang = self._get_row_data(row)
        if _show_translation_detail(
            self.window_context,
            source,
            translated,
            src_lang,
            target_lang,
        ):
            self.reuse_requested.emit(
                entry_id,
                source,
                translated,
                src_lang,
                target_lang,
            )

    def on_copy_selected(self) -> None:
        """Copies translated text of the first selected entry to clipboard."""
        row = self._first_selected_row()
        if row is None:
            return

        _, translated, _, _ = self._get_row_data(row)
        QApplication.clipboard().setText(translated)

    def on_delete_selected(self) -> None:
        """Removes selected text translation history entries."""
        selected_rows = sorted(
            {item.row() for item in self.table.selectedItems()},
            reverse=True,
        )
        if not selected_rows:
            return

        count = len(selected_rows)
        if not CustomConfirmDialog.confirm(
            self.window_context,
            tr("dialog.delete_items"),
            tr("dialog.delete_items_msg", count=count),
            is_danger=True,
        ):
            return

        for row in selected_rows:
            entry_id = self.table.item(row, 0).data(_ROLE_ENTRY_ID)
            delete_text_translation_entry(entry_id)

        self.refresh_history(force=True)

    def on_reuse_selected(self) -> None:
        """Emits reuse_requested with the first selected entry's data."""
        row = self._first_selected_row()
        if row is None:
            return

        entry_id = self.table.item(row, 0).data(_ROLE_ENTRY_ID)
        source, translated, src_lang, target_lang = self._get_row_data(row)
        self.reuse_requested.emit(
            entry_id,
            source,
            translated,
            src_lang,
            target_lang,
        )


# ── Detail dialog ─────────────────────────────────────────────────────────


def _show_translation_detail(  # noqa: PLR0915
    parent: QWidget,
    source: str,
    translated: str,
    src_lang: str,
    target_lang: str,
) -> bool:
    """Shows a card-style dialog with side-by-side source and translated text.

    Returns True if the user clicked the Re-use button.
    """
    from PySide6.QtWidgets import QFrame, QPushButton  # noqa: PLC0415

    h_pad = 16
    v_pad = 12

    dialog = BaseDialog(parent)
    dialog.setWindowTitle(tr("text_history.view_title"))
    dialog.setMinimumSize(700, 450)
    reuse_clicked = False

    def _on_reuse() -> None:
        nonlocal reuse_clicked
        reuse_clicked = True
        dialog.accept()

    # Re-use is the primary action — Enter should trigger it, not Close.
    dialog.on_confirm = lambda *_args: _on_reuse()

    def _make_sep(*, vertical: bool = False) -> QWidget:
        """Creates a 1px themed separator."""
        sep = QWidget()
        if vertical:
            sep.setFixedWidth(1)
        else:
            sep.setFixedHeight(1)
        sep.setStyleSheet(_separator_style())
        return sep

    # ── Card container ────────────────────────────────────────────
    card = QFrame()
    card.setObjectName("DetailCard")
    card.setStyleSheet(_style_detail_card())

    card_layout = QVBoxLayout(card)
    card_layout.setContentsMargins(0, 0, 0, 0)
    card_layout.setSpacing(0)

    # ── Header: language labels (two columns matching text areas) ──
    header = QHBoxLayout()
    header.setContentsMargins(0, 0, 0, 0)
    header.setSpacing(0)

    # Localise the source / target headers the same way the table
    # cells are localised (via ``localized_language_label``) so the
    # detail dialog stays consistent with the row the user clicked
    # — Vietnamese user sees "Tiếng Việt" in both surfaces.
    if src_lang:
        src_display = localized_language_label(src_lang)
    else:
        src_display = tr("common.lang_auto_detect")
    target_display = localized_language_label(target_lang)
    header.addWidget(_build_lang_header(src_display, h_pad, v_pad), 1)
    header.addWidget(_make_sep(vertical=True))
    header.addWidget(_build_lang_header(target_display, h_pad, v_pad), 1)

    card_layout.addLayout(header)
    card_layout.addWidget(_make_sep())

    # ── Content: side-by-side text areas ──────────────────────────
    content = QHBoxLayout()
    content.setContentsMargins(0, 0, 0, 0)
    content.setSpacing(0)

    src_text = QPlainTextEdit()
    src_text.setPlainText(source)
    src_text.setReadOnly(True)
    src_text.setTabChangesFocus(True)
    src_text.setStyleSheet(_style_detail_text())

    tgt_text = QPlainTextEdit()
    tgt_text.setPlainText(translated)
    tgt_text.setReadOnly(True)
    tgt_text.setTabChangesFocus(True)
    tgt_text.setStyleSheet(_style_detail_text())

    content.addWidget(src_text, 1)
    content.addWidget(_make_sep(vertical=True))
    content.addWidget(tgt_text, 1)

    card_layout.addLayout(content, 1)

    dialog.layout.addWidget(card, 1)

    # ── Button row ────────────────────────────────────────────────
    btn_layout = QHBoxLayout()
    btn_layout.setSpacing(10)

    close_btn = QPushButton(tr("btn.close"))
    close_btn.setFixedHeight(HEIGHT_CONTROL)
    close_btn.setStyleSheet(style_secondary_button() + "padding: 0 30px;")
    close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    close_btn.setAutoDefault(False)
    close_btn.clicked.connect(dialog.accept)

    reuse_btn = QPushButton(tr("btn.reuse"))
    reuse_btn.setFixedHeight(HEIGHT_CONTROL)
    reuse_btn.setStyleSheet(style_primary_button() + "padding: 0 30px;")
    reuse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    reuse_btn.setAutoDefault(False)
    reuse_btn.clicked.connect(_on_reuse)

    btn_layout.addStretch()
    btn_layout.addWidget(reuse_btn)
    btn_layout.addWidget(close_btn)
    dialog.layout.addLayout(btn_layout)

    dialog.exec()
    return reuse_clicked
