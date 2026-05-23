"""Glossary page UI for the AI Translate application."""

import csv
import logging
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.constants import (
    GLOSSARY_ACTION_COL_WIDTH,
    GLOSSARY_DEFAULT_SPLITTER_SIZES,
    GLOSSARY_ENTRIES_PANEL_MIN_WIDTH,
    GLOSSARY_SET_PANEL_MIN_WIDTH,
    HEIGHT_CONTROL,
    SEARCH_DEBOUNCE_MS,
    SPLITTER_HANDLE_WIDTH,
    style_card_header,
    style_card_light,
    style_delete_button,
    style_input_field,
    style_link_button,
    style_list_widget,
    style_outlined_primary_button,
    style_primary_button,
    style_section_title,
    style_splitter,
    style_table,
    style_table_delete_button,
    tr,
)
from src.constants.settings import SETTING_GLOSSARY_SPLITTER_SIZES
from src.core.database import (
    add_glossary_entry,
    create_glossary_set,
    delete_glossary_entry,
    delete_glossary_set,
    find_glossary_entry_by_source,
    get_glossary_entries,
    get_glossary_entry_count,
    get_glossary_sets,
    update_all_glossary_sets_active,
    update_glossary_entry,
    update_glossary_set_active,
    update_glossary_set_name,
)
from src.ui.components import (
    CaseInsensitiveSortItem,
    HighlightDelegate,
    create_page_container,
    create_section_group,
    create_table,
)
from src.ui.dialogs import CustomConfirmDialog, CustomInputDialog, CustomMessageDialog
from src.utils.config_manager import load_setting, save_setting
from src.utils.text_utils import normalize_for_search

logger = logging.getLogger("glossary")

# Role slot on the source-column item that stores the original untouched text,
# used to revert empty / whitespace-only edits in place without a full refresh.
_ROLE_ORIG_SOURCE = Qt.ItemDataRole.UserRole + 2
_ROLE_ORIG_TARGET = Qt.ItemDataRole.UserRole + 3


@dataclass
class GlossarySetsUI:
    """Components for the dictionary sets column."""

    group: QFrame  # Outer card frame wrapping the entire sets panel
    label: QLabel  # Header label showing set count
    list_widget: QListWidget  # Checkable list of glossary sets
    toggle_all_btn: QPushButton  # Activate/deactivate all sets at once
    create_btn: QPushButton  # Create a new glossary set
    edit_btn: QPushButton  # Rename the selected set
    delete_btn: QPushButton  # Delete the selected set


@dataclass
class GlossaryEntriesUI:
    """Components for the translation entries column."""

    group: QFrame  # Outer card frame wrapping the entries panel
    table: QTableWidget  # Editable table of source/target pairs
    source_input: QLineEdit  # Quick-add source term field
    target_input: QLineEdit  # Quick-add target translation field
    search_input: QLineEdit  # Filter entries by text match
    add_btn: QPushButton  # Confirm quick-add entry
    label: QLabel  # Header label showing entry count
    input_card: QFrame  # Card frame around the quick-add row
    input_header: QLabel  # "Quick Add" title inside the input card
    import_btn: QPushButton  # Import entries from CSV
    export_btn: QPushButton  # Export entries to CSV


@dataclass
class GlossaryUIComponents:
    """Container for Glossary UI components.

    Aggregates references from both sets and entries panels so that
    logic functions can operate without knowing the panel layout.
    """

    page: QWidget  # Top-level page widget (parent for dialogs)
    set_list: QListWidget  # Glossary sets list (from GlossarySetsUI)
    set_list_label: QLabel  # Sets count header label
    table: QTableWidget  # Entries table (from GlossaryEntriesUI)
    table_delegate: HighlightDelegate  # Search-highlight delegate for entries table
    entries_list_label: QLabel  # Entries count header label
    source_input: QLineEdit  # Quick-add source field
    target_input: QLineEdit  # Quick-add target field
    search_input: QLineEdit  # Entries search/filter field
    add_btn: QPushButton  # Quick-add confirm button
    toggle_all_btn: QPushButton  # Activate/deactivate all sets
    create_set_btn: QPushButton  # Create new set
    edit_set_btn: QPushButton  # Rename selected set
    delete_set_btn: QPushButton  # Delete selected set
    import_btn: QPushButton  # Import entries from CSV
    export_btn: QPushButton  # Export entries to CSV


def refresh_sets(ui: GlossaryUIComponents) -> None:
    """Reloads the list of dictionary sets from the database."""
    current_id = -1
    if ui.set_list.currentItem():
        current_id = ui.set_list.currentItem().data(Qt.ItemDataRole.UserRole)

    ui.set_list.blockSignals(True)
    ui.set_list.clear()
    sets = get_glossary_sets()
    ui.set_list_label.setText(tr("glossary.sets_count", count=len(sets)))
    for s_id, name, is_active in sets:
        ui.set_list.addItem(name)
        last_item = ui.set_list.item(ui.set_list.count() - 1)
        last_item.setData(Qt.ItemDataRole.UserRole, s_id)
        last_item.setData(Qt.ItemDataRole.UserRole + 1, name)

        # Set checkable state
        last_item.setFlags(last_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        state = Qt.CheckState.Checked if is_active else Qt.CheckState.Unchecked
        last_item.setCheckState(state)

    # Reselect previous if possible
    any_inactive = False
    for i in range(ui.set_list.count()):
        item = ui.set_list.item(i)
        if item.data(Qt.ItemDataRole.UserRole) == current_id:
            ui.set_list.setCurrentRow(i)
        if item.checkState() == Qt.CheckState.Unchecked:
            any_inactive = True

    if ui.set_list.count() == 0:
        ui.toggle_all_btn.setVisible(False)
    else:
        ui.toggle_all_btn.setVisible(True)
        ui.toggle_all_btn.setText(
            tr("btn.activate_all") if any_inactive else tr("btn.inactivate_all")
        )

    if not ui.set_list.currentItem() and ui.set_list.count() > 0:
        ui.set_list.setCurrentRow(0)
    ui.set_list.blockSignals(False)


def refresh_entries(ui: GlossaryUIComponents) -> None:
    """Reloads the glossary entries for the selected set."""
    ui.table.blockSignals(True)
    ui.table.setUpdatesEnabled(False)
    ui.table.setSortingEnabled(False)
    ui.table.setRowCount(0)
    ui.entries_list_label.setText(tr("glossary.pairs_count", count=0))
    current_item = ui.set_list.currentItem()
    if not current_item:
        ui.export_btn.setEnabled(False)
        ui.table.setUpdatesEnabled(True)
        ui.table.blockSignals(False)
        return

    set_id = current_item.data(Qt.ItemDataRole.UserRole)
    entries = get_glossary_entries(set_id)
    # Export operates on the full set, not the search-filtered view.
    ui.export_btn.setEnabled(len(entries) > 0)

    search_text = ui.search_input.text().strip()
    ui.table_delegate.set_search_text(search_text)

    if search_text:
        norm_search = normalize_for_search(search_text)
        # Guard: if search normalizes to empty (e.g. only combining marks),
        # skip filtering — "" in "..." is always True in Python.
        if norm_search:
            entries = [
                (e_id, src, tgt)
                for e_id, src, tgt in entries
                if norm_search in normalize_for_search(src)
                or norm_search in normalize_for_search(tgt)
            ]

    ui.table.setRowCount(len(entries))
    ui.entries_list_label.setText(tr("glossary.pairs_count", count=len(entries)))

    for row, (e_id, source, target) in enumerate(entries):
        src_item = CaseInsensitiveSortItem(source)
        src_item.setData(Qt.ItemDataRole.UserRole, e_id)
        src_item.setData(_ROLE_ORIG_SOURCE, source)
        ui.table.setItem(row, 0, src_item)
        tgt_item = CaseInsensitiveSortItem(target)
        tgt_item.setData(_ROLE_ORIG_TARGET, target)
        ui.table.setItem(row, 1, tgt_item)

        del_btn = QPushButton(tr("btn.delete"))
        # Re-translate per-row Delete button on language switch.  The
        # window's apply_language sweep walks every QWidget; binding
        # the tr key here means the button picks up the new locale
        # without needing the table to be fully rebuilt first.
        del_btn.apply_language = lambda b=del_btn: b.setText(tr("btn.delete"))
        del_btn.setStyleSheet(style_table_delete_button())
        del_btn.setFixedSize(60, 20)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.clicked.connect(lambda _, eid=e_id: on_delete_entry(ui, eid))
        ui.table.setCellWidget(row, 2, del_btn)

    ui.table.setSortingEnabled(True)
    ui.table.setUpdatesEnabled(True)
    ui.table.blockSignals(False)


def on_delete_entry(ui: GlossaryUIComponents, entry_id: int) -> None:
    """Deletes a single dictionary entry after confirmation."""
    if not CustomConfirmDialog.confirm(
        ui.page,
        tr("dialog.confirm_delete"),
        tr("dialog.delete_entry_msg"),
        is_danger=True,
    ):
        return
    delete_glossary_entry(entry_id)
    refresh_entries(ui)


def on_delete_selected_entries(ui: GlossaryUIComponents) -> None:
    """Deletes all currently selected entries after a single confirmation.

    No-op when nothing is selected.  Entry IDs are collected from column 0
    of each selected row (stored at ``Qt.ItemDataRole.UserRole``).
    """
    selected_rows = sorted({item.row() for item in ui.table.selectedItems()})
    entry_ids: list[int] = []
    for row in selected_rows:
        src_item = ui.table.item(row, 0)
        if src_item is None:
            continue
        eid = src_item.data(Qt.ItemDataRole.UserRole)
        if eid is not None:
            entry_ids.append(eid)
    if not entry_ids:
        return
    if not CustomConfirmDialog.confirm(
        ui.page,
        tr("dialog.confirm_delete"),
        tr("dialog.delete_entry_msg"),
        is_danger=True,
    ):
        return
    for eid in entry_ids:
        delete_glossary_entry(eid)
    refresh_entries(ui)


def on_item_changed(ui: GlossaryUIComponents, item: QTableWidgetItem) -> None:
    """Handles manual edits in the entries table.

    Empty / whitespace-only edits are reverted in place (the single cell is
    restored from its backup role) instead of triggering a full table refresh
    which would clobber any in-progress edit on other rows.
    """
    row = item.row()
    source_item = ui.table.item(row, 0)
    target_item = ui.table.item(row, 1)

    if not source_item or not target_item:
        return

    entry_id = source_item.data(Qt.ItemDataRole.UserRole)
    if entry_id is None:
        return

    src_text = source_item.text().strip()
    tgt_text = target_item.text().strip()

    if not src_text or not tgt_text:
        # Revert just the cleared cell — keep other rows' in-progress edits.
        ui.table.blockSignals(True)
        try:
            if not src_text:
                orig = source_item.data(_ROLE_ORIG_SOURCE) or ""
                source_item.setText(orig)
            if not tgt_text:
                orig = target_item.data(_ROLE_ORIG_TARGET) or ""
                target_item.setText(orig)
        finally:
            ui.table.blockSignals(False)
        return

    update_glossary_entry(entry_id, src_text, tgt_text)
    # Backup roles track the latest committed values so further empty edits
    # revert to the actually-persisted text, not the pre-edit version.
    source_item.setData(_ROLE_ORIG_SOURCE, src_text)
    target_item.setData(_ROLE_ORIG_TARGET, tgt_text)


def on_add_entry(ui: GlossaryUIComponents) -> None:
    """Adds a new translation entry to the active set.

    Detects existing entries with the same source (case-insensitive) and
    offers to replace the target rather than silently creating duplicates.
    """
    current_item = ui.set_list.currentItem()
    if not current_item:
        CustomMessageDialog.show_message(
            ui.page,
            tr("dialog.selection_required"),
            tr("dialog.select_set_msg"),
        )
        return

    source = ui.source_input.text().strip()
    target = ui.target_input.text().strip()

    if not source or not target:
        return

    set_id = current_item.data(Qt.ItemDataRole.UserRole)

    existing = find_glossary_entry_by_source(set_id, source)
    if existing is not None:
        entry_id, current_target = existing
        if current_target == target:
            # Identical row already exists — no-op with a gentle notification.
            CustomMessageDialog.show_message(
                ui.page,
                tr("dialog.glossary_duplicate_title"),
                tr(
                    "dialog.glossary_duplicate_exists_msg",
                    source=source,
                    target=current_target,
                ),
            )
            return
        if not CustomConfirmDialog.confirm(
            ui.page,
            tr("dialog.glossary_duplicate_title"),
            tr(
                "dialog.glossary_duplicate_replace_msg",
                source=source,
                old=current_target,
                new=target,
            ),
        ):
            return
        update_glossary_entry(entry_id, source, target)
    else:
        add_glossary_entry(set_id, source, target)

    ui.source_input.clear()
    ui.target_input.clear()
    ui.source_input.setFocus()
    refresh_entries(ui)


def on_create_set(ui: GlossaryUIComponents) -> None:
    """Handles creating a new dictionary set."""
    dialog = CustomInputDialog(
        ui.page,
        tr("dialog.new_set"),
        tr("dialog.new_set_label"),
        tr("dialog.new_set_placeholder"),
    )

    def attempt_save() -> None:
        """Validate and save the new glossary set name."""
        name = dialog.input.text().strip()
        if not name:
            dialog.set_error(tr("error.name_required"))
            return
        if create_glossary_set(name):
            refresh_sets(ui)
            dialog.accept()
        else:
            dialog.set_error(tr("error.name_exists"))

    dialog.on_confirm = attempt_save
    dialog.exec()


def on_edit_set(ui: GlossaryUIComponents) -> None:
    """Handles renaming the currently selected dictionary set."""
    current_item = ui.set_list.currentItem()
    if not current_item:
        return
    set_id = current_item.data(Qt.ItemDataRole.UserRole)
    old_name = current_item.data(Qt.ItemDataRole.UserRole + 1)
    dialog = CustomInputDialog(
        ui.page,
        tr("dialog.rename_set"),
        tr("dialog.rename_set_label"),
        old_name,
    )
    dialog.input.setText(old_name)
    dialog.input.selectAll()

    def attempt_save() -> None:
        """Validate and save the renamed glossary set."""
        new_name = dialog.input.text().strip()
        if not new_name:
            dialog.set_error(tr("error.name_required"))
            return
        if new_name == old_name:
            dialog.accept()
            return
        if update_glossary_set_name(set_id, new_name):
            refresh_sets(ui)
            dialog.accept()
        else:
            dialog.set_error(tr("error.name_exists"))

    dialog.on_confirm = attempt_save
    dialog.exec()


def on_delete_set(ui: GlossaryUIComponents) -> None:
    """Deletes the selected set. Warns about cascaded entry deletion."""
    current_item = ui.set_list.currentItem()
    if not current_item:
        return
    set_id = current_item.data(Qt.ItemDataRole.UserRole)
    name = current_item.data(Qt.ItemDataRole.UserRole + 1)
    entry_count = get_glossary_entry_count(set_id)

    # Pick the message that mentions the cascaded deletion when relevant.
    if entry_count > 0:
        message = tr(
            "dialog.delete_set_with_entries_msg",
            name=name,
            count=entry_count,
        )
    else:
        message = tr("dialog.delete_set_msg", name=name)

    if CustomConfirmDialog.confirm(
        ui.page,
        tr("dialog.confirm_delete"),
        message,
        is_danger=True,
    ):
        delete_glossary_set(set_id)
        refresh_sets(ui)


def on_export_entries(ui: GlossaryUIComponents) -> None:
    """Exports the current set's entries to a CSV file.

    The CSV is UTF-8 encoded with a ``source,target`` header row.
    """
    current_item = ui.set_list.currentItem()
    if not current_item:
        CustomMessageDialog.show_message(
            ui.page,
            tr("dialog.selection_required"),
            tr("dialog.select_set_msg"),
        )
        return

    set_id = current_item.data(Qt.ItemDataRole.UserRole)
    set_name = current_item.data(Qt.ItemDataRole.UserRole + 1) or "glossary"
    entries = get_glossary_entries(set_id)
    if not entries:
        CustomMessageDialog.show_message(
            ui.page,
            tr("dialog.glossary_export_empty_title"),
            tr("dialog.glossary_export_empty_msg"),
        )
        return

    default_name = f"{set_name}.csv"
    file_path, _ = QFileDialog.getSaveFileName(
        ui.page,
        tr("dialog.glossary_export_title"),
        default_name,
        "CSV (*.csv);;All Files (*)",
    )
    if not file_path:
        return

    try:
        with Path(file_path).open("w", encoding="utf-8", newline="") as fp:
            writer = csv.writer(fp)
            writer.writerow(["source", "target"])
            for _e_id, source, target in entries:
                writer.writerow([source, target])
    except OSError as exc:
        logger.exception("Failed to write glossary export: %s", exc)
        CustomMessageDialog.show_message(
            ui.page,
            tr("dialog.glossary_export_failed_title"),
            tr("dialog.glossary_export_failed_msg", error=str(exc)),
        )
        return

    CustomMessageDialog.show_message(
        ui.page,
        tr("dialog.glossary_export_ok_title"),
        tr(
            "dialog.glossary_export_ok_msg",
            count=len(entries),
            path=file_path,
        ),
    )


def _read_csv_pairs(path: Path) -> tuple[list[tuple[str, str]], int]:
    """Reads ``source,target`` pairs from a CSV file.

    Skips an optional header row (``source,target``, case-insensitive) and
    skips rows with fewer than two non-empty columns. Returns a tuple of
    ``(pairs, skipped_count)``.
    """
    pairs: list[tuple[str, str]] = []
    skipped = 0

    with path.open("r", encoding="utf-8-sig", newline="") as fp:
        reader = csv.reader(fp)
        for i, row in enumerate(reader):
            if len(row) < 2:  # noqa: PLR2004
                skipped += 1
                continue
            source = row[0].strip()
            target = row[1].strip()
            # Skip a header row of exactly "source,target".
            if i == 0 and source.lower() == "source" and target.lower() == "target":
                continue
            if not source or not target:
                skipped += 1
                continue
            pairs.append((source, target))

    return pairs, skipped


def on_import_entries(ui: GlossaryUIComponents) -> None:
    """Imports source/target pairs from a CSV file into the active set.

    Rows whose source matches an existing entry (case-insensitive) are
    updated to the new target; rows with no match are inserted.
    """
    current_item = ui.set_list.currentItem()
    if not current_item:
        CustomMessageDialog.show_message(
            ui.page,
            tr("dialog.selection_required"),
            tr("dialog.select_set_msg"),
        )
        return

    file_path, _ = QFileDialog.getOpenFileName(
        ui.page,
        tr("dialog.glossary_import_title"),
        "",
        "CSV (*.csv);;All Files (*)",
    )
    if not file_path:
        return

    try:
        pairs, skipped = _read_csv_pairs(Path(file_path))
    except (OSError, csv.Error, UnicodeDecodeError) as exc:
        logger.exception("Failed to read glossary import: %s", exc)
        CustomMessageDialog.show_message(
            ui.page,
            tr("dialog.glossary_import_failed_title"),
            tr("dialog.glossary_import_failed_msg", error=str(exc)),
        )
        return

    if not pairs:
        CustomMessageDialog.show_message(
            ui.page,
            tr("dialog.glossary_import_empty_title"),
            tr("dialog.glossary_import_empty_msg"),
        )
        return

    set_id = current_item.data(Qt.ItemDataRole.UserRole)
    added = 0
    updated = 0
    for source, target in pairs:
        existing = find_glossary_entry_by_source(set_id, source)
        if existing is None:
            add_glossary_entry(set_id, source, target)
            added += 1
        else:
            entry_id, current_target = existing
            if current_target != target:
                update_glossary_entry(entry_id, source, target)
                updated += 1

    CustomMessageDialog.show_message(
        ui.page,
        tr("dialog.glossary_import_ok_title"),
        tr(
            "dialog.glossary_import_ok_msg",
            added=added,
            updated=updated,
            skipped=skipped,
        ),
    )
    refresh_entries(ui)


def on_toggle_all(ui: GlossaryUIComponents) -> None:
    """Toggles active state for all dictionary sets."""
    # Check if any are currently unchecked
    any_unchecked = False
    for i in range(ui.set_list.count()):
        if ui.set_list.item(i).checkState() == Qt.CheckState.Unchecked:
            any_unchecked = True
            break

    # If any are unchecked, check all. Otherwise, uncheck all.
    update_all_glossary_sets_active(any_unchecked)
    refresh_sets(ui)


def init_glossary_logic(ui: GlossaryUIComponents) -> None:
    """Initializes the logic and signals for the Glossary page."""
    ui.table.setItemDelegateForColumn(0, ui.table_delegate)
    ui.table.setItemDelegateForColumn(1, ui.table_delegate)

    def on_set_item_changed(item: QListWidgetItem) -> None:
        """Toggle active state of a glossary set when its checkbox changes."""
        set_id = item.data(Qt.ItemDataRole.UserRole)
        is_active = item.checkState() == Qt.CheckState.Checked
        update_glossary_set_active(set_id, is_active)

    # Debounce search input
    search_timer = QTimer(ui.page)
    search_timer.setSingleShot(True)
    search_timer.setInterval(SEARCH_DEBOUNCE_MS)
    search_timer.timeout.connect(lambda: refresh_entries(ui))

    # Signals
    ui.toggle_all_btn.clicked.connect(lambda: on_toggle_all(ui))
    ui.create_set_btn.clicked.connect(lambda: on_create_set(ui))
    ui.edit_set_btn.clicked.connect(lambda: on_edit_set(ui))
    ui.delete_set_btn.clicked.connect(lambda: on_delete_set(ui))
    ui.set_list.currentItemChanged.connect(lambda: refresh_entries(ui))
    ui.set_list.itemChanged.connect(on_set_item_changed)
    ui.search_input.textChanged.connect(search_timer.start)
    ui.table.itemChanged.connect(lambda item: on_item_changed(ui, item))
    ui.add_btn.clicked.connect(lambda: on_add_entry(ui))
    ui.source_input.returnPressed.connect(lambda: on_add_entry(ui))
    ui.target_input.returnPressed.connect(lambda: on_add_entry(ui))
    ui.import_btn.clicked.connect(lambda: on_import_entries(ui))
    ui.export_btn.clicked.connect(lambda: on_export_entries(ui))

    # Keyboard shortcuts scoped to the page widget. Keys come from the
    # central registry so the Settings → Shortcuts tab can rebind them.
    from src.constants.shortcuts import (  # noqa: PLC0415
        get_shortcut,
        shortcuts_changed,
    )

    new_set_shortcut = QShortcut(
        QKeySequence(get_shortcut("glossary.new_set")),
        ui.page,
    )
    new_set_shortcut.activated.connect(lambda: on_create_set(ui))

    find_shortcut = QShortcut(
        QKeySequence(get_shortcut("glossary.focus_search")),
        ui.page,
    )
    find_shortcut.activated.connect(ui.search_input.setFocus)

    focus_new_pair_shortcut = QShortcut(
        QKeySequence(get_shortcut("glossary.focus_new_pair")),
        ui.page,
    )
    focus_new_pair_shortcut.activated.connect(ui.source_input.setFocus)

    rename_set_shortcut = QShortcut(
        QKeySequence(get_shortcut("glossary.rename_set")),
        ui.page,
    )
    rename_set_shortcut.activated.connect(lambda: on_edit_set(ui))

    def _sync_shortcuts() -> None:
        new_set_shortcut.setKey(QKeySequence(get_shortcut("glossary.new_set")))
        find_shortcut.setKey(QKeySequence(get_shortcut("glossary.focus_search")))
        focus_new_pair_shortcut.setKey(
            QKeySequence(get_shortcut("glossary.focus_new_pair")),
        )
        rename_set_shortcut.setKey(
            QKeySequence(get_shortcut("glossary.rename_set")),
        )

    shortcuts_changed.connect(_sync_shortcuts)

    # Accessible names for screen readers.
    ui.source_input.setAccessibleName(tr("glossary.source_placeholder"))
    ui.target_input.setAccessibleName(tr("glossary.target_placeholder"))
    ui.search_input.setAccessibleName(tr("glossary.search_placeholder"))
    ui.add_btn.setAccessibleName(tr("btn.add"))
    ui.import_btn.setAccessibleName(tr("btn.import"))
    ui.export_btn.setAccessibleName(tr("btn.export"))

    refresh_sets(ui)
    refresh_entries(ui)


def create_sets_column() -> GlossarySetsUI:
    """Creates the left column for dictionary sets."""
    set_group, set_layout, set_list_label = create_section_group(
        tr("glossary.sets_title"),
    )
    set_group.setMinimumWidth(GLOSSARY_SET_PANEL_MIN_WIDTH)
    set_layout.setContentsMargins(15, 15, 15, 15)
    set_layout.setSpacing(12)

    # Re-arrange title row to include toggle button
    set_layout.removeWidget(set_list_label)
    # Remove bottom padding so title aligns with the button
    set_list_label.setStyleSheet(
        style_section_title().replace("padding-bottom: 8px;", "")
    )
    header_layout = QHBoxLayout()
    header_layout.setContentsMargins(0, 0, 0, 0)
    header_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
    header_layout.addWidget(set_list_label)
    header_layout.addStretch()

    toggle_all_btn = QPushButton(tr("btn.toggle_all"))
    toggle_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    toggle_all_btn.setStyleSheet(style_link_button())
    header_layout.addWidget(toggle_all_btn)
    set_layout.insertLayout(0, header_layout)

    set_list = QListWidget()
    set_list.setObjectName("glossary_set_list")
    set_list.setStyleSheet(style_list_widget())
    set_list.setCursor(Qt.CursorShape.PointingHandCursor)
    set_list.setWordWrap(True)
    set_list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
    set_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    set_list.setResizeMode(QListWidget.ResizeMode.Adjust)
    set_layout.addWidget(set_list)

    set_btns_layout = QHBoxLayout()
    set_btns_layout.setSpacing(8)

    create_set_btn = QPushButton(tr("btn.new_set"))
    create_set_btn.setFixedHeight(HEIGHT_CONTROL)
    create_set_btn.setStyleSheet(style_primary_button())
    create_set_btn.setCursor(Qt.CursorShape.PointingHandCursor)

    edit_set_btn = QPushButton(tr("btn.rename"))
    edit_set_btn.setFixedHeight(HEIGHT_CONTROL)
    edit_set_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    edit_set_btn.setStyleSheet(style_outlined_primary_button())

    delete_set_btn = QPushButton(tr("btn.delete"))
    delete_set_btn.setFixedHeight(HEIGHT_CONTROL)
    delete_set_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    delete_set_btn.setStyleSheet(style_delete_button())

    set_btns_layout.addWidget(create_set_btn, 1)
    set_btns_layout.addWidget(edit_set_btn, 1)
    set_btns_layout.addWidget(delete_set_btn)
    set_layout.addLayout(set_btns_layout)

    return GlossarySetsUI(
        group=set_group,
        label=set_list_label,
        list_widget=set_list,
        toggle_all_btn=toggle_all_btn,
        create_btn=create_set_btn,
        edit_btn=edit_set_btn,
        delete_btn=delete_set_btn,
    )


def create_entry_table() -> QTableWidget:
    """Configures and returns the glossary entry table."""
    table = create_table(
        headers=[
            tr("table.source_text"),
            tr("table.target_translation"),
            tr("table.action"),
        ],
        interactive_columns=[0, 1],
        column_widths={2: GLOSSARY_ACTION_COL_WIDTH},
    )
    table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
    table.horizontalHeader().sectionClicked.connect(table.clearSelection)
    return table


def create_entries_column() -> GlossaryEntriesUI:  # noqa: PLR0915
    """Creates the right column for translation entries."""
    (
        entries_group,
        entries_layout,
        entries_list_label,
    ) = create_section_group(
        tr("glossary.pairs_title"),
    )
    entries_group.setMinimumWidth(GLOSSARY_ENTRIES_PANEL_MIN_WIDTH)
    entries_layout.setContentsMargins(15, 15, 15, 15)
    entries_layout.setSpacing(15)

    # Match vertical position with the sets column title
    # (which is centered with the toggle button's 10px padding)
    entries_list_label.setStyleSheet(
        style_section_title().replace(
            "padding-bottom: 8px;",
            "padding: 10px 0 0 0;",
        )
    )

    # Entry Input Area
    input_card = QFrame()
    input_card.setStyleSheet(style_card_light())
    input_card_layout = QVBoxLayout(input_card)
    input_card_layout.setContentsMargins(12, 12, 12, 12)

    input_header = QLabel(tr("glossary.quick_add"))
    input_header.apply_language = lambda w=input_header: w.setText(
        tr("glossary.quick_add"),
    )
    input_header.setStyleSheet(style_card_header() + "margin-bottom: 5px;")
    input_card_layout.addWidget(input_header)

    input_row = QHBoxLayout()
    input_row.setSpacing(10)

    source_input = QLineEdit()
    source_input.setPlaceholderText(tr("glossary.source_placeholder"))
    source_input.setStyleSheet(style_input_field())
    source_input.setFixedHeight(HEIGHT_CONTROL)

    target_input = QLineEdit()
    target_input.setPlaceholderText(tr("glossary.target_placeholder"))
    target_input.setStyleSheet(style_input_field())
    target_input.setFixedHeight(HEIGHT_CONTROL)

    add_btn = QPushButton(tr("btn.add"))
    add_btn.setFixedHeight(HEIGHT_CONTROL)
    add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    add_btn.setStyleSheet(style_primary_button())

    input_row.addWidget(source_input, 1)
    input_row.addWidget(QLabel("↔"), 0)
    input_row.addWidget(target_input, 1)
    input_row.addWidget(add_btn)
    input_card_layout.addLayout(input_row)
    entries_layout.addWidget(input_card)

    # Search + Import/Export row
    search_row = QHBoxLayout()
    search_row.setSpacing(8)

    search_input = QLineEdit()
    search_input.setPlaceholderText(tr("glossary.search_placeholder"))
    search_input.setStyleSheet(style_input_field())
    search_input.setFixedHeight(HEIGHT_CONTROL)
    search_row.addWidget(search_input, 1)

    import_btn = QPushButton(tr("btn.import"))
    import_btn.setFixedHeight(HEIGHT_CONTROL)
    import_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    import_btn.setStyleSheet(style_outlined_primary_button())
    search_row.addWidget(import_btn)

    export_btn = QPushButton(tr("btn.export"))
    export_btn.setFixedHeight(HEIGHT_CONTROL)
    export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    export_btn.setStyleSheet(style_outlined_primary_button())
    search_row.addWidget(export_btn)

    entries_layout.addLayout(search_row)

    table = create_entry_table()
    entries_layout.addWidget(table, 1)

    return GlossaryEntriesUI(
        group=entries_group,
        table=table,
        source_input=source_input,
        target_input=target_input,
        search_input=search_input,
        add_btn=add_btn,
        label=entries_list_label,
        input_card=input_card,
        input_header=input_header,
        import_btn=import_btn,
        export_btn=export_btn,
    )


def _create_splitter(left: QFrame, right: QFrame) -> QSplitter:
    """Creates a horizontal QSplitter with persisted pane sizes."""
    splitter = QSplitter(Qt.Orientation.Horizontal)
    splitter.setChildrenCollapsible(False)
    splitter.addWidget(left)
    splitter.addWidget(right)
    splitter.setStretchFactor(0, 0)  # Left pane: stays put on window resize
    splitter.setStretchFactor(1, 1)  # Right pane: absorbs extra space
    splitter.setHandleWidth(SPLITTER_HANDLE_WIDTH)
    splitter.setStyleSheet(style_splitter())

    # Restore persisted position or use default
    saved = load_setting(SETTING_GLOSSARY_SPLITTER_SIZES)
    if saved and isinstance(saved, list) and len(saved) == 2:  # noqa: PLR2004
        splitter.setSizes([int(s) for s in saved])
    else:
        splitter.setSizes(GLOSSARY_DEFAULT_SPLITTER_SIZES)

    # Persist splitter position on drag
    splitter.splitterMoved.connect(
        lambda: save_setting(SETTING_GLOSSARY_SPLITTER_SIZES, splitter.sizes())
    )
    return splitter


def create_glossary_page() -> QWidget:  # noqa: PLR0915
    """Creates the Glossary page content."""
    page, main_layout = create_page_container(
        tr("page.glossary"),
        tr_key="page.glossary",
    )
    # Hide the default title label from create_page_container
    if main_layout.count() > 0:
        main_layout.itemAt(0).widget().setVisible(False)
    sets_ui = create_sets_column()
    entries_ui = create_entries_column()
    table_delegate = HighlightDelegate(page, normalize=True)

    ui = GlossaryUIComponents(
        page=page,
        set_list=sets_ui.list_widget,
        set_list_label=sets_ui.label,
        table=entries_ui.table,
        table_delegate=table_delegate,
        entries_list_label=entries_ui.label,
        source_input=entries_ui.source_input,
        target_input=entries_ui.target_input,
        search_input=entries_ui.search_input,
        add_btn=entries_ui.add_btn,
        toggle_all_btn=sets_ui.toggle_all_btn,
        create_set_btn=sets_ui.create_btn,
        edit_set_btn=sets_ui.edit_btn,
        delete_set_btn=sets_ui.delete_btn,
        import_btn=entries_ui.import_btn,
        export_btn=entries_ui.export_btn,
    )
    init_glossary_logic(ui)

    splitter = _create_splitter(sets_ui.group, entries_ui.group)
    main_layout.addWidget(splitter, 1)

    # Theme switching for all glossary-specific widgets
    _base_apply_theme = page.apply_theme

    def apply_theme() -> None:
        """Reapply theme styles to all glossary-specific UI components."""
        _base_apply_theme()
        # Sets column
        sets_ui.toggle_all_btn.setStyleSheet(style_link_button())
        sets_ui.list_widget.setStyleSheet(style_list_widget())
        sets_ui.create_btn.setStyleSheet(style_primary_button())
        sets_ui.edit_btn.setStyleSheet(style_outlined_primary_button())
        sets_ui.delete_btn.setStyleSheet(style_delete_button())
        # Splitter handle
        splitter.setStyleSheet(style_splitter())
        # Entries column
        entries_ui.input_card.setStyleSheet(style_card_light())
        entries_ui.input_header.setStyleSheet(
            style_card_header() + "margin-bottom: 5px;"
        )
        entries_ui.source_input.setStyleSheet(style_input_field())
        entries_ui.target_input.setStyleSheet(style_input_field())
        entries_ui.add_btn.setStyleSheet(style_primary_button())
        entries_ui.search_input.setStyleSheet(style_input_field())
        entries_ui.import_btn.setStyleSheet(style_outlined_primary_button())
        entries_ui.export_btn.setStyleSheet(style_outlined_primary_button())
        entries_ui.table.setStyleSheet(style_table())

    page.apply_theme = apply_theme

    # Language switching for all glossary-specific widgets
    # Capture the page-container's apply_language before overriding
    # ``page.apply_language`` so we can chain into it — otherwise the
    # header label ("Glossary Management") never re-translates and
    # the page reads as half-localised after a language switch.
    _base_apply_language = page.apply_language

    def apply_language() -> None:
        """Update all glossary labels when the application language changes."""
        _base_apply_language()
        # Sets column
        sets_ui.create_btn.setText(tr("btn.new_set"))
        sets_ui.edit_btn.setText(tr("btn.rename"))
        sets_ui.delete_btn.setText(tr("btn.delete"))
        # Entries column
        entries_ui.input_header.setText(tr("glossary.quick_add"))
        entries_ui.source_input.setPlaceholderText(tr("glossary.source_placeholder"))
        entries_ui.target_input.setPlaceholderText(tr("glossary.target_placeholder"))
        entries_ui.add_btn.setText(tr("btn.add"))
        entries_ui.search_input.setPlaceholderText(tr("glossary.search_placeholder"))
        entries_ui.import_btn.setText(tr("btn.import"))
        entries_ui.export_btn.setText(tr("btn.export"))
        # Update table headers
        for i, key in enumerate(
            [
                "table.source_text",
                "table.target_translation",
                "table.action",
            ]
        ):
            entries_ui.table.horizontalHeaderItem(i).setText(tr(key))
        # Refresh dynamic labels
        refresh_sets(ui)
        refresh_entries(ui)

    page.apply_language = apply_language

    # Del-key dispatcher used by window.py's `common.delete_selected`
    # shortcut.  Routes to set-delete or bulk entry-delete based on focus.
    def on_delete_selected() -> None:
        from PySide6.QtWidgets import QApplication  # noqa: PLC0415

        focused = QApplication.focusWidget()
        if focused is ui.set_list:
            on_delete_set(ui)
        elif focused is ui.table:
            on_delete_selected_entries(ui)

    page.on_delete_selected = on_delete_selected

    # Auto-focus the search input when the page becomes visible. The page
    # is a plain QWidget (not subclassed), so we attach an event filter
    # rather than overriding showEvent.
    class _FocusSearchOnShow(QObject):
        def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802
            if event.type() == QEvent.Type.Show:
                entries_ui.search_input.setFocus()
            return False

    _focus_filter = _FocusSearchOnShow(page)
    page.installEventFilter(_focus_filter)
    page._focus_filter = _focus_filter  # prevent GC

    return page
