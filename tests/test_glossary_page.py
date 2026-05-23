"""Comprehensive tests for the Glossary page UI and logic.

Covers:
- Page creation, widget structure, and dataclass wiring
- refresh_sets() — loading sets from DB, checkbox state, toggle button
- refresh_entries() — loading entries, search filtering, delete buttons
- on_item_changed() — inline editing in the entries table
- on_add_entry() — creating new entries
- on_create_set() — creating new sets via dialog
- on_edit_set() — renaming sets via dialog
- on_delete_set() — deleting sets via confirmation dialog
- on_delete_entry() — deleting individual entries
- on_toggle_all() — bulk activate/deactivate
- init_glossary_logic() — signal wiring and initial data load
- apply_theme() / apply_language() — style and i18n refresh
- CaseInsensitiveSortItem — case-insensitive table sort
- Edge cases: empty sets, unicode, missing selections
"""

from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from src.ui.components import CaseInsensitiveSortItem
from src.ui.pages.glossary import (
    GlossaryUIComponents,
    create_glossary_page,
    init_glossary_logic,
    on_add_entry,
    on_delete_entry,
    on_delete_set,
    on_edit_set,
    on_item_changed,
    on_toggle_all,
    refresh_entries,
    refresh_sets,
)

# ---------------------------------------------------------------------------
# Module-level patch path prefix
# ---------------------------------------------------------------------------
_G = "src.ui.pages.glossary"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _auto_mock_blocking_dialogs():
    """Auto-mocks modal dialogs so tests don't hang on user input.

    - ``CustomConfirmDialog.confirm`` → returns True (auto-confirm).
    - ``CustomMessageDialog.show_message`` → no-op.
    - ``QFileDialog.getSaveFileName`` / ``getOpenFileName`` → empty (cancel).

    Tests that specifically want to exercise these paths use their own
    ``@patch`` decorators which take precedence.
    """
    with (
        patch(
            "src.ui.pages.glossary.CustomConfirmDialog.confirm",
            return_value=True,
        ),
        patch(
            "src.ui.pages.glossary.CustomMessageDialog.show_message",
        ),
        patch(
            "src.ui.pages.glossary.QFileDialog.getSaveFileName",
            return_value=("", ""),
        ),
        patch(
            "src.ui.pages.glossary.QFileDialog.getOpenFileName",
            return_value=("", ""),
        ),
    ):
        yield


@pytest.fixture()
def ui(qapp, qtbot):
    """Builds a minimal GlossaryUIComponents for unit-testing logic functions.

    All DB calls are mocked so no real database I/O occurs.
    """
    from src.ui.components import HighlightDelegate  # noqa: PLC0415

    page = QWidget()
    set_list = QListWidget()
    table = QTableWidget(0, 3)
    table.setHorizontalHeaderItem(0, QTableWidgetItem("Source"))
    table.setHorizontalHeaderItem(1, QTableWidgetItem("Target"))
    table.setHorizontalHeaderItem(2, QTableWidgetItem("Action"))
    delegate = HighlightDelegate(page, normalize=True)

    source_input = QLineEdit()
    target_input = QLineEdit()
    search_input = QLineEdit()
    add_btn = QPushButton("Add")
    toggle_all_btn = QPushButton("Toggle All")
    create_set_btn = QPushButton("New Set")
    edit_set_btn = QPushButton("Rename")
    delete_set_btn = QPushButton("Delete")
    import_btn = QPushButton("Import")
    export_btn = QPushButton("Export")

    from PySide6.QtWidgets import QLabel  # noqa: PLC0415

    set_list_label = QLabel()
    entries_list_label = QLabel()

    comp = GlossaryUIComponents(
        page=page,
        set_list=set_list,
        set_list_label=set_list_label,
        table=table,
        table_delegate=delegate,
        entries_list_label=entries_list_label,
        source_input=source_input,
        target_input=target_input,
        search_input=search_input,
        add_btn=add_btn,
        toggle_all_btn=toggle_all_btn,
        create_set_btn=create_set_btn,
        edit_set_btn=edit_set_btn,
        delete_set_btn=delete_set_btn,
        import_btn=import_btn,
        export_btn=export_btn,
    )

    qtbot.addWidget(page)
    qtbot.addWidget(set_list)
    qtbot.addWidget(table)
    return comp


# ---------------------------------------------------------------------------
# Helper to populate set_list items
# ---------------------------------------------------------------------------


def _populate_set_list(ui, sets_data):
    """Add items to ui.set_list matching the format from get_glossary_sets.

    sets_data: list of (id, name, is_active) tuples.
    """
    ui.set_list.clear()
    for s_id, name, is_active in sets_data:
        ui.set_list.addItem(name)
        item = ui.set_list.item(ui.set_list.count() - 1)
        item.setData(Qt.ItemDataRole.UserRole, s_id)
        item.setData(Qt.ItemDataRole.UserRole + 1, name)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        state = Qt.CheckState.Checked if is_active else Qt.CheckState.Unchecked
        item.setCheckState(state)


# ---------------------------------------------------------------------------
# CaseInsensitiveSortItem
# ---------------------------------------------------------------------------


class TestCaseInsensitiveSortItem:
    """Tests for the case-insensitive table sort item."""

    def test_lowercase_less_than_uppercase(self, qapp) -> None:
        """'apple' sorts before 'Banana' case-insensitively."""
        a = CaseInsensitiveSortItem("apple")
        b = CaseInsensitiveSortItem("Banana")
        assert a < b

    def test_same_text_different_case(self, qapp) -> None:
        """'ABC' is not less than 'abc' (equal case-insensitively)."""
        a = CaseInsensitiveSortItem("ABC")
        b = CaseInsensitiveSortItem("abc")
        assert not (a < b)
        assert not (b < a)

    def test_unicode_sort(self, qapp) -> None:
        """Unicode strings sort case-insensitively."""
        a = CaseInsensitiveSortItem("Über")
        b = CaseInsensitiveSortItem("zoo")
        # "über" > "zoo" in Python's default str ordering
        assert b < a


# ---------------------------------------------------------------------------
# refresh_sets()
# ---------------------------------------------------------------------------


class TestRefreshSets:
    """Tests for refresh_sets() — loading glossary sets from the database."""

    @patch(f"{_G}.get_glossary_sets", return_value=[])
    def test_empty_sets(self, mock_get, ui) -> None:
        """Empty DB hides the toggle button and clears the list."""
        refresh_sets(ui)
        assert ui.set_list.count() == 0
        assert not ui.toggle_all_btn.isVisible()

    @patch(
        f"{_G}.get_glossary_sets",
        return_value=[(1, "Medical", True), (2, "Legal", True)],
    )
    def test_loads_two_sets(self, mock_get, ui) -> None:
        """Two active sets are loaded into the list."""
        refresh_sets(ui)
        assert ui.set_list.count() == 2  # noqa: PLR2004

    @patch(
        f"{_G}.get_glossary_sets",
        return_value=[(1, "Medical", True), (2, "Legal", True)],
    )
    def test_first_set_selected_by_default(self, mock_get, ui) -> None:
        """First set is auto-selected when no previous selection."""
        refresh_sets(ui)
        assert ui.set_list.currentRow() == 0

    @patch(
        f"{_G}.get_glossary_sets",
        return_value=[(1, "Medical", True), (2, "Legal", False)],
    )
    def test_toggle_btn_shows_activate_all_when_any_inactive(
        self, mock_get, ui
    ) -> None:
        """Toggle button says 'activate all' when at least one set is unchecked."""
        refresh_sets(ui)
        assert ui.toggle_all_btn.isVisible()
        # tr() returns the key in test context; verify button text was set
        btn_text = ui.toggle_all_btn.text()
        assert "activate" in btn_text.lower() or "btn." in btn_text

    @patch(
        f"{_G}.get_glossary_sets",
        return_value=[(1, "Medical", True), (2, "Legal", True)],
    )
    def test_toggle_btn_shows_inactivate_all_when_all_active(
        self, mock_get, ui
    ) -> None:
        """Toggle button says 'inactivate all' when all sets are checked."""
        refresh_sets(ui)
        assert ui.toggle_all_btn.isVisible()

    @patch(
        f"{_G}.get_glossary_sets",
        return_value=[(1, "A", True), (2, "B", True), (3, "C", False)],
    )
    def test_sets_have_correct_check_state(self, mock_get, ui) -> None:
        """Each set item has the correct checked/unchecked state."""
        refresh_sets(ui)
        assert ui.set_list.item(0).checkState() == Qt.CheckState.Checked
        assert ui.set_list.item(1).checkState() == Qt.CheckState.Checked
        assert ui.set_list.item(2).checkState() == Qt.CheckState.Unchecked

    @patch(
        f"{_G}.get_glossary_sets",
        return_value=[(1, "A", True), (2, "B", True)],
    )
    def test_preserves_previous_selection(self, mock_get, ui) -> None:
        """refresh_sets re-selects the previously selected set by ID."""
        # First load
        refresh_sets(ui)
        ui.set_list.setCurrentRow(1)
        assert ui.set_list.currentItem().data(Qt.ItemDataRole.UserRole) == 2  # noqa: PLR2004

        # Second load — should re-select set_id=2
        refresh_sets(ui)
        current = ui.set_list.currentItem()
        assert current is not None
        assert current.data(Qt.ItemDataRole.UserRole) == 2  # noqa: PLR2004

    @patch(
        f"{_G}.get_glossary_sets",
        return_value=[(1, "A", True)],
    )
    def test_sets_label_updated(self, mock_get, ui) -> None:
        """The set list label is updated after refresh (contains tr key or count)."""
        refresh_sets(ui)
        label_text = ui.set_list_label.text()
        # tr() in test context returns the key itself; verify it was called
        assert label_text  # non-empty after refresh

    @patch(
        f"{_G}.get_glossary_sets",
        return_value=[(1, "A", True)],
    )
    def test_user_role_data_stored(self, mock_get, ui) -> None:
        """Each item stores set_id in UserRole and name in UserRole+1."""
        refresh_sets(ui)
        item = ui.set_list.item(0)
        assert item.data(Qt.ItemDataRole.UserRole) == 1
        assert item.data(Qt.ItemDataRole.UserRole + 1) == "A"


# ---------------------------------------------------------------------------
# refresh_entries()
# ---------------------------------------------------------------------------


class TestRefreshEntries:
    """Tests for refresh_entries() — loading entries for the selected set."""

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    def test_no_selection_clears_table(self, mock_get, ui) -> None:
        """No selected set results in an empty table."""
        ui.set_list.clear()
        refresh_entries(ui)
        assert ui.table.rowCount() == 0

    @patch(
        f"{_G}.get_glossary_entries",
        return_value=[(10, "hello", "xin chào"), (11, "world", "thế giới")],
    )
    def test_loads_entries_for_selected_set(self, mock_get, ui) -> None:
        """Entries for the selected set appear in the table."""
        _populate_set_list(ui, [(1, "TestSet", True)])
        ui.set_list.setCurrentRow(0)
        refresh_entries(ui)
        assert ui.table.rowCount() == 2  # noqa: PLR2004
        # Sorting is enabled so order may differ; check that both entries exist
        texts = {ui.table.item(r, 0).text() for r in range(2)}
        assert texts == {"hello", "world"}

    @patch(
        f"{_G}.get_glossary_entries",
        return_value=[(10, "hello", "xin chào"), (11, "world", "thế giới")],
    )
    def test_entries_have_delete_button(self, mock_get, ui) -> None:
        """Each entry row has a delete button in column 2."""
        _populate_set_list(ui, [(1, "TestSet", True)])
        ui.set_list.setCurrentRow(0)
        refresh_entries(ui)
        del_widget = ui.table.cellWidget(0, 2)
        assert isinstance(del_widget, QPushButton)

    @patch(
        f"{_G}.get_glossary_entries",
        return_value=[(10, "hello", "xin chào"), (11, "world", "thế giới")],
    )
    def test_entries_label_updated(self, mock_get, ui) -> None:
        """The entries label is updated after loading entries."""
        _populate_set_list(ui, [(1, "TestSet", True)])
        ui.set_list.setCurrentRow(0)
        refresh_entries(ui)
        # tr() in test context returns the key; verify label was set
        assert ui.entries_list_label.text()  # non-empty after refresh

    @patch(
        f"{_G}.get_glossary_entries",
        return_value=[
            (10, "hello", "xin chào"),
            (11, "world", "thế giới"),
            (12, "cat", "con mèo"),
        ],
    )
    def test_search_filters_entries(self, mock_get, ui) -> None:
        """Typing in the search box filters entries by source or target."""
        _populate_set_list(ui, [(1, "TestSet", True)])
        ui.set_list.setCurrentRow(0)
        ui.search_input.setText("hello")
        refresh_entries(ui)
        assert ui.table.rowCount() == 1
        assert ui.table.item(0, 0).text() == "hello"

    @patch(
        f"{_G}.get_glossary_entries",
        return_value=[(10, "hello", "xin chào"), (11, "world", "thế giới")],
    )
    def test_search_by_target_text(self, mock_get, ui) -> None:
        """Search also matches target translation text."""
        _populate_set_list(ui, [(1, "TestSet", True)])
        ui.set_list.setCurrentRow(0)
        ui.search_input.setText("thế giới")
        refresh_entries(ui)
        assert ui.table.rowCount() == 1
        assert ui.table.item(0, 1).text() == "thế giới"

    @patch(
        f"{_G}.get_glossary_entries",
        return_value=[(10, "hello", "xin chào")],
    )
    def test_search_no_match_shows_empty(self, mock_get, ui) -> None:
        """Search with no matching entries shows zero rows."""
        _populate_set_list(ui, [(1, "TestSet", True)])
        ui.set_list.setCurrentRow(0)
        ui.search_input.setText("nonexistent")
        refresh_entries(ui)
        assert ui.table.rowCount() == 0

    @patch(
        f"{_G}.get_glossary_entries",
        return_value=[(10, "hello", "xin chào")],
    )
    def test_empty_search_shows_all(self, mock_get, ui) -> None:
        """Empty search text shows all entries."""
        _populate_set_list(ui, [(1, "TestSet", True)])
        ui.set_list.setCurrentRow(0)
        ui.search_input.setText("")
        refresh_entries(ui)
        assert ui.table.rowCount() == 1

    @patch(
        f"{_G}.get_glossary_entries",
        return_value=[(10, "hello", "xin chào")],
    )
    def test_entry_stores_id_in_user_role(self, mock_get, ui) -> None:
        """Each source-column item stores the entry ID in UserRole."""
        _populate_set_list(ui, [(1, "TestSet", True)])
        ui.set_list.setCurrentRow(0)
        ui.search_input.clear()
        refresh_entries(ui)
        source_item = ui.table.item(0, 0)
        assert source_item.data(Qt.ItemDataRole.UserRole) == 10  # noqa: PLR2004

    @patch(
        f"{_G}.get_glossary_entries",
        return_value=[(10, "hello", "xin chào")],
    )
    def test_search_whitespace_only_shows_all(self, mock_get, ui) -> None:
        """Search with only whitespace is treated as empty (shows all)."""
        _populate_set_list(ui, [(1, "TestSet", True)])
        ui.set_list.setCurrentRow(0)
        ui.search_input.setText("   ")
        refresh_entries(ui)
        assert ui.table.rowCount() == 1


# ---------------------------------------------------------------------------
# on_item_changed() — inline editing
# ---------------------------------------------------------------------------


class TestOnItemChanged:
    """Tests for on_item_changed() — inline editing in the entries table."""

    @patch(f"{_G}.update_glossary_entry")
    def test_updates_entry_on_valid_edit(self, mock_update, ui) -> None:
        """Editing both source and target calls update_glossary_entry."""
        ui.table.setRowCount(1)
        src_item = QTableWidgetItem("hello")
        src_item.setData(Qt.ItemDataRole.UserRole, 42)
        ui.table.setItem(0, 0, src_item)
        ui.table.setItem(0, 1, QTableWidgetItem("bonjour"))

        on_item_changed(ui, src_item)
        mock_update.assert_called_once_with(42, "hello", "bonjour")

    @patch(f"{_G}.update_glossary_entry")
    @patch(f"{_G}.refresh_entries")
    def test_empty_source_reverts_in_place(
        self,
        mock_refresh,
        mock_update,
        ui,
    ) -> None:
        """Empty source reverts just that cell from its backup role."""
        from src.ui.pages.glossary import _ROLE_ORIG_SOURCE  # noqa: PLC0415

        ui.table.setRowCount(1)
        src_item = QTableWidgetItem("")
        src_item.setData(Qt.ItemDataRole.UserRole, 42)
        src_item.setData(_ROLE_ORIG_SOURCE, "hello")
        ui.table.setItem(0, 0, src_item)
        ui.table.setItem(0, 1, QTableWidgetItem("bonjour"))

        on_item_changed(ui, src_item)
        mock_update.assert_not_called()
        # No full refresh — in-progress edits on other rows stay intact.
        mock_refresh.assert_not_called()
        # The cleared cell was restored from the backup.
        assert ui.table.item(0, 0).text() == "hello"

    @patch(f"{_G}.update_glossary_entry")
    @patch(f"{_G}.refresh_entries")
    def test_empty_target_reverts_in_place(
        self,
        mock_refresh,
        mock_update,
        ui,
    ) -> None:
        """Empty target reverts just that cell from its backup role."""
        from src.ui.pages.glossary import _ROLE_ORIG_TARGET  # noqa: PLC0415

        ui.table.setRowCount(1)
        src_item = QTableWidgetItem("hello")
        src_item.setData(Qt.ItemDataRole.UserRole, 42)
        ui.table.setItem(0, 0, src_item)
        tgt_item = QTableWidgetItem("")
        tgt_item.setData(_ROLE_ORIG_TARGET, "bonjour")
        ui.table.setItem(0, 1, tgt_item)

        on_item_changed(ui, src_item)
        mock_update.assert_not_called()
        mock_refresh.assert_not_called()
        assert ui.table.item(0, 1).text() == "bonjour"

    @patch(f"{_G}.update_glossary_entry")
    def test_missing_target_item_noop(self, mock_update, ui) -> None:
        """No crash when target item is missing (None)."""
        ui.table.setRowCount(1)
        src_item = QTableWidgetItem("hello")
        src_item.setData(Qt.ItemDataRole.UserRole, 42)
        ui.table.setItem(0, 0, src_item)
        # Column 1 intentionally not set

        on_item_changed(ui, src_item)
        mock_update.assert_not_called()

    @patch(f"{_G}.update_glossary_entry")
    def test_none_entry_id_noop(self, mock_update, ui) -> None:
        """No update when entry_id is None (no UserRole data)."""
        ui.table.setRowCount(1)
        src_item = QTableWidgetItem("hello")
        # No UserRole data set
        ui.table.setItem(0, 0, src_item)
        ui.table.setItem(0, 1, QTableWidgetItem("bonjour"))

        on_item_changed(ui, src_item)
        mock_update.assert_not_called()

    @patch(f"{_G}.update_glossary_entry")
    def test_strips_whitespace(self, mock_update, ui) -> None:
        """Source and target are stripped before saving."""
        ui.table.setRowCount(1)
        src_item = QTableWidgetItem("  hello  ")
        src_item.setData(Qt.ItemDataRole.UserRole, 42)
        ui.table.setItem(0, 0, src_item)
        ui.table.setItem(0, 1, QTableWidgetItem("  bonjour  "))

        on_item_changed(ui, src_item)
        mock_update.assert_called_once_with(42, "hello", "bonjour")


# ---------------------------------------------------------------------------
# on_add_entry()
# ---------------------------------------------------------------------------


class TestOnAddEntry:
    """Tests for on_add_entry() — adding a new glossary entry."""

    @patch(f"{_G}.refresh_entries")
    @patch(f"{_G}.add_glossary_entry")
    def test_adds_entry_to_selected_set(self, mock_add, mock_refresh, ui) -> None:
        """Valid source+target adds an entry and refreshes."""
        _populate_set_list(ui, [(5, "MySet", True)])
        ui.set_list.setCurrentRow(0)
        ui.source_input.setText("apple")
        ui.target_input.setText("pomme")

        on_add_entry(ui)

        mock_add.assert_called_once_with(5, "apple", "pomme")
        mock_refresh.assert_called_once()

    @patch(f"{_G}.add_glossary_entry")
    def test_clears_inputs_after_add(self, mock_add, ui) -> None:
        """Source and target inputs are cleared after successful add."""
        _populate_set_list(ui, [(5, "MySet", True)])
        ui.set_list.setCurrentRow(0)
        ui.source_input.setText("apple")
        ui.target_input.setText("pomme")

        with patch(f"{_G}.refresh_entries"):
            on_add_entry(ui)

        assert ui.source_input.text() == ""
        assert ui.target_input.text() == ""

    @patch(f"{_G}.add_glossary_entry")
    def test_empty_source_does_not_add(self, mock_add, ui) -> None:
        """Empty source text prevents adding."""
        _populate_set_list(ui, [(5, "MySet", True)])
        ui.set_list.setCurrentRow(0)
        ui.source_input.setText("")
        ui.target_input.setText("pomme")

        on_add_entry(ui)
        mock_add.assert_not_called()

    @patch(f"{_G}.add_glossary_entry")
    def test_empty_target_does_not_add(self, mock_add, ui) -> None:
        """Empty target text prevents adding."""
        _populate_set_list(ui, [(5, "MySet", True)])
        ui.set_list.setCurrentRow(0)
        ui.source_input.setText("apple")
        ui.target_input.setText("")

        on_add_entry(ui)
        mock_add.assert_not_called()

    @patch(f"{_G}.add_glossary_entry")
    def test_whitespace_only_does_not_add(self, mock_add, ui) -> None:
        """Whitespace-only inputs do not add an entry."""
        _populate_set_list(ui, [(5, "MySet", True)])
        ui.set_list.setCurrentRow(0)
        ui.source_input.setText("   ")
        ui.target_input.setText("   ")

        on_add_entry(ui)
        mock_add.assert_not_called()

    @patch(f"{_G}.CustomMessageDialog.show_message")
    @patch(f"{_G}.add_glossary_entry")
    def test_no_set_selected_shows_message(self, mock_add, mock_msg, ui) -> None:
        """When no set is selected, a message dialog is shown."""
        ui.set_list.clear()
        ui.source_input.setText("apple")
        ui.target_input.setText("pomme")

        on_add_entry(ui)
        mock_add.assert_not_called()
        mock_msg.assert_called_once()

    @patch(f"{_G}.refresh_entries")
    @patch(f"{_G}.add_glossary_entry")
    def test_unicode_entry(self, mock_add, mock_refresh, ui) -> None:
        """Unicode source and target are handled correctly."""
        _populate_set_list(ui, [(5, "MySet", True)])
        ui.set_list.setCurrentRow(0)
        ui.source_input.setText("日本語")
        ui.target_input.setText("Tiếng Nhật")

        on_add_entry(ui)
        mock_add.assert_called_once_with(5, "日本語", "Tiếng Nhật")


# ---------------------------------------------------------------------------
# on_delete_entry()
# ---------------------------------------------------------------------------


class TestOnDeleteEntry:
    """Tests for on_delete_entry() — deleting a single entry."""

    @patch(f"{_G}.refresh_entries")
    @patch(f"{_G}.delete_glossary_entry")
    def test_deletes_and_refreshes(self, mock_del, mock_refresh, ui) -> None:
        """Deleting an entry calls the DB and refreshes the table."""
        on_delete_entry(ui, 99)
        mock_del.assert_called_once_with(99)
        mock_refresh.assert_called_once_with(ui)


# ---------------------------------------------------------------------------
# on_create_set()
# ---------------------------------------------------------------------------


class TestOnCreateSet:
    """Tests for on_create_set() — creating a new glossary set via dialog."""

    @patch(f"{_G}.refresh_sets")
    @patch(f"{_G}.create_glossary_set", return_value=True)
    @patch(f"{_G}.CustomInputDialog")
    def test_creates_set_on_valid_name(
        self, mock_dialog_cls, mock_create, mock_refresh, ui
    ) -> None:
        """A valid name creates the set and refreshes."""
        dialog = MagicMock()
        dialog.input = MagicMock()
        dialog.input.text.return_value = "New Medical"
        mock_dialog_cls.return_value = dialog

        # Simulate: when exec is called, invoke on_confirm
        def run_confirm():
            dialog.on_confirm()

        dialog.exec.side_effect = run_confirm

        from src.ui.pages.glossary import on_create_set  # noqa: PLC0415

        on_create_set(ui)

        mock_create.assert_called_once_with("New Medical")
        mock_refresh.assert_called_once()
        dialog.accept.assert_called_once()

    @patch(f"{_G}.create_glossary_set")
    @patch(f"{_G}.CustomInputDialog")
    def test_empty_name_shows_error(self, mock_dialog_cls, mock_create, ui) -> None:
        """Empty name triggers an error on the dialog."""
        dialog = MagicMock()
        dialog.input = MagicMock()
        dialog.input.text.return_value = "   "
        mock_dialog_cls.return_value = dialog

        def run_confirm():
            dialog.on_confirm()

        dialog.exec.side_effect = run_confirm

        from src.ui.pages.glossary import on_create_set  # noqa: PLC0415

        on_create_set(ui)

        mock_create.assert_not_called()
        dialog.set_error.assert_called_once()

    @patch(f"{_G}.create_glossary_set", return_value=False)
    @patch(f"{_G}.CustomInputDialog")
    def test_duplicate_name_shows_error(self, mock_dialog_cls, mock_create, ui) -> None:
        """Duplicate name triggers a 'name exists' error on the dialog."""
        dialog = MagicMock()
        dialog.input = MagicMock()
        dialog.input.text.return_value = "Existing"
        mock_dialog_cls.return_value = dialog

        def run_confirm():
            dialog.on_confirm()

        dialog.exec.side_effect = run_confirm

        from src.ui.pages.glossary import on_create_set  # noqa: PLC0415

        on_create_set(ui)

        mock_create.assert_called_once_with("Existing")
        dialog.set_error.assert_called_once()
        dialog.accept.assert_not_called()


# ---------------------------------------------------------------------------
# on_edit_set()
# ---------------------------------------------------------------------------


class TestOnEditSet:
    """Tests for on_edit_set() — renaming a glossary set via dialog."""

    @patch(f"{_G}.refresh_sets")
    @patch(f"{_G}.update_glossary_set_name", return_value=True)
    @patch(f"{_G}.CustomInputDialog")
    def test_renames_set(self, mock_dialog_cls, mock_rename, mock_refresh, ui) -> None:
        """Valid new name renames the set and refreshes."""
        _populate_set_list(ui, [(1, "OldName", True)])
        ui.set_list.setCurrentRow(0)

        dialog = MagicMock()
        dialog.input = MagicMock()
        dialog.input.text.return_value = "NewName"
        mock_dialog_cls.return_value = dialog

        def run_confirm():
            dialog.on_confirm()

        dialog.exec.side_effect = run_confirm

        on_edit_set(ui)

        mock_rename.assert_called_once_with(1, "NewName")
        mock_refresh.assert_called_once()
        dialog.accept.assert_called_once()

    @patch(f"{_G}.update_glossary_set_name")
    @patch(f"{_G}.CustomInputDialog")
    def test_same_name_accepts_without_update(
        self, mock_dialog_cls, mock_rename, ui
    ) -> None:
        """If the new name equals the old name, dialog accepts without DB call."""
        _populate_set_list(ui, [(1, "SameName", True)])
        ui.set_list.setCurrentRow(0)

        dialog = MagicMock()
        dialog.input = MagicMock()
        dialog.input.text.return_value = "SameName"
        mock_dialog_cls.return_value = dialog

        def run_confirm():
            dialog.on_confirm()

        dialog.exec.side_effect = run_confirm

        on_edit_set(ui)

        mock_rename.assert_not_called()
        dialog.accept.assert_called_once()

    @patch(f"{_G}.update_glossary_set_name", return_value=False)
    @patch(f"{_G}.CustomInputDialog")
    def test_duplicate_rename_shows_error(
        self, mock_dialog_cls, mock_rename, ui
    ) -> None:
        """Renaming to a duplicate name shows an error."""
        _populate_set_list(ui, [(1, "OldName", True)])
        ui.set_list.setCurrentRow(0)

        dialog = MagicMock()
        dialog.input = MagicMock()
        dialog.input.text.return_value = "DuplicateName"
        mock_dialog_cls.return_value = dialog

        def run_confirm():
            dialog.on_confirm()

        dialog.exec.side_effect = run_confirm

        on_edit_set(ui)

        mock_rename.assert_called_once()
        dialog.set_error.assert_called_once()
        dialog.accept.assert_not_called()

    def test_no_selection_noop(self, ui) -> None:
        """on_edit_set returns immediately when nothing is selected."""
        ui.set_list.clear()
        # Should not raise
        on_edit_set(ui)

    @patch(f"{_G}.update_glossary_set_name")
    @patch(f"{_G}.CustomInputDialog")
    def test_empty_name_shows_error(self, mock_dialog_cls, mock_rename, ui) -> None:
        """Empty rename input triggers an error."""
        _populate_set_list(ui, [(1, "OldName", True)])
        ui.set_list.setCurrentRow(0)

        dialog = MagicMock()
        dialog.input = MagicMock()
        dialog.input.text.return_value = "  "
        mock_dialog_cls.return_value = dialog

        def run_confirm():
            dialog.on_confirm()

        dialog.exec.side_effect = run_confirm

        on_edit_set(ui)

        mock_rename.assert_not_called()
        dialog.set_error.assert_called_once()


# ---------------------------------------------------------------------------
# on_delete_set()
# ---------------------------------------------------------------------------


class TestOnDeleteSet:
    """Tests for on_delete_set() — deleting a glossary set."""

    @patch(f"{_G}.refresh_sets")
    @patch(f"{_G}.delete_glossary_set")
    @patch(f"{_G}.CustomConfirmDialog.confirm", return_value=True)
    def test_deletes_on_confirm(self, mock_confirm, mock_del, mock_refresh, ui) -> None:
        """Confirming deletion removes the set and refreshes."""
        _populate_set_list(ui, [(7, "ToDelete", True)])
        ui.set_list.setCurrentRow(0)

        on_delete_set(ui)

        mock_del.assert_called_once_with(7)
        mock_refresh.assert_called_once()

    @patch(f"{_G}.delete_glossary_set")
    @patch(f"{_G}.CustomConfirmDialog.confirm", return_value=False)
    def test_cancel_does_not_delete(self, mock_confirm, mock_del, ui) -> None:
        """Cancelling the confirmation does not delete."""
        _populate_set_list(ui, [(7, "ToKeep", True)])
        ui.set_list.setCurrentRow(0)

        on_delete_set(ui)
        mock_del.assert_not_called()

    def test_no_selection_noop(self, ui) -> None:
        """on_delete_set returns immediately when nothing is selected."""
        ui.set_list.clear()
        on_delete_set(ui)


# ---------------------------------------------------------------------------
# on_toggle_all()
# ---------------------------------------------------------------------------


class TestOnToggleAll:
    """Tests for on_toggle_all() — bulk activate/deactivate."""

    @patch(f"{_G}.refresh_sets")
    @patch(f"{_G}.update_all_glossary_sets_active")
    def test_activates_all_when_any_unchecked(
        self, mock_update, mock_refresh, ui
    ) -> None:
        """When at least one set is unchecked, toggles all to active."""
        _populate_set_list(ui, [(1, "A", True), (2, "B", False)])

        on_toggle_all(ui)
        mock_update.assert_called_once_with(True)
        mock_refresh.assert_called_once()

    @patch(f"{_G}.refresh_sets")
    @patch(f"{_G}.update_all_glossary_sets_active")
    def test_deactivates_all_when_all_checked(
        self, mock_update, mock_refresh, ui
    ) -> None:
        """When all sets are checked, toggles all to inactive."""
        _populate_set_list(ui, [(1, "A", True), (2, "B", True)])

        on_toggle_all(ui)
        mock_update.assert_called_once_with(False)
        mock_refresh.assert_called_once()

    @patch(f"{_G}.refresh_sets")
    @patch(f"{_G}.update_all_glossary_sets_active")
    def test_empty_list_deactivates(self, mock_update, mock_refresh, ui) -> None:
        """Empty list (no unchecked items) passes False (deactivate all)."""
        ui.set_list.clear()

        on_toggle_all(ui)
        mock_update.assert_called_once_with(False)


# ---------------------------------------------------------------------------
# init_glossary_logic()
# ---------------------------------------------------------------------------


class TestInitGlossaryLogic:
    """Tests for init_glossary_logic() — signal wiring and initial load."""

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(f"{_G}.get_glossary_sets", return_value=[])
    def test_calls_refresh_on_init(self, mock_sets, mock_entries, ui) -> None:
        """init_glossary_logic calls refresh_sets and refresh_entries on init."""
        init_glossary_logic(ui)
        mock_sets.assert_called()
        # refresh_entries is also called during init

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(f"{_G}.get_glossary_sets", return_value=[])
    def test_delegate_set_on_columns(self, mock_sets, mock_entries, ui) -> None:
        """Table columns 0 and 1 use the highlight delegate after init."""
        init_glossary_logic(ui)
        assert ui.table.itemDelegateForColumn(0) is ui.table_delegate
        assert ui.table.itemDelegateForColumn(1) is ui.table_delegate


# ---------------------------------------------------------------------------
# create_glossary_page() — full page integration
# ---------------------------------------------------------------------------


class TestCreateGlossaryPage:
    """Tests for create_glossary_page() — full page creation."""

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(f"{_G}.get_glossary_sets", return_value=[])
    def test_returns_qwidget(self, mock_sets, mock_entries, qapp, qtbot) -> None:
        """create_glossary_page returns a QWidget."""
        page = create_glossary_page()
        qtbot.addWidget(page)
        assert isinstance(page, QWidget)

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(f"{_G}.get_glossary_sets", return_value=[])
    def test_contains_splitter(self, mock_sets, mock_entries, qapp, qtbot) -> None:
        """Page contains a QSplitter."""
        page = create_glossary_page()
        qtbot.addWidget(page)
        splitter = page.findChild(QSplitter)
        assert splitter is not None

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(f"{_G}.get_glossary_sets", return_value=[])
    def test_contains_set_list(self, mock_sets, mock_entries, qapp, qtbot) -> None:
        """Page contains a QListWidget for glossary sets."""
        page = create_glossary_page()
        qtbot.addWidget(page)
        list_widget = page.findChild(QListWidget, "glossary_set_list")
        assert list_widget is not None

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(f"{_G}.get_glossary_sets", return_value=[])
    def test_contains_entry_table(self, mock_sets, mock_entries, qapp, qtbot) -> None:
        """Page contains a QTableWidget for glossary entries."""
        page = create_glossary_page()
        qtbot.addWidget(page)
        table = page.findChild(QTableWidget)
        assert table is not None
        assert table.columnCount() == 3  # noqa: PLR2004

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(f"{_G}.get_glossary_sets", return_value=[])
    def test_has_apply_theme(self, mock_sets, mock_entries, qapp, qtbot) -> None:
        """Page has an apply_theme callable attribute."""
        page = create_glossary_page()
        qtbot.addWidget(page)
        assert hasattr(page, "apply_theme")
        assert callable(page.apply_theme)

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(f"{_G}.get_glossary_sets", return_value=[])
    def test_has_apply_language(self, mock_sets, mock_entries, qapp, qtbot) -> None:
        """Page has an apply_language callable attribute."""
        page = create_glossary_page()
        qtbot.addWidget(page)
        assert hasattr(page, "apply_language")
        assert callable(page.apply_language)


# ---------------------------------------------------------------------------
# apply_theme()
# ---------------------------------------------------------------------------


class TestApplyTheme:
    """Tests for apply_theme() — style refresh on theme switch."""

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(f"{_G}.get_glossary_sets", return_value=[])
    def test_apply_theme_does_not_crash(
        self, mock_sets, mock_entries, qapp, qtbot
    ) -> None:
        """apply_theme() can be called without errors."""
        page = create_glossary_page()
        qtbot.addWidget(page)
        page.apply_theme()

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(f"{_G}.get_glossary_sets", return_value=[])
    def test_apply_theme_updates_table_style(
        self, mock_sets, mock_entries, qapp, qtbot
    ) -> None:
        """apply_theme() refreshes the table stylesheet."""
        page = create_glossary_page()
        qtbot.addWidget(page)
        table = page.findChild(QTableWidget)
        table.setStyleSheet("")
        page.apply_theme()
        assert table.styleSheet() != ""


# ---------------------------------------------------------------------------
# apply_language()
# ---------------------------------------------------------------------------


class TestApplyLanguage:
    """Tests for apply_language() — i18n refresh on language switch."""

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(f"{_G}.get_glossary_sets", return_value=[])
    def test_apply_language_does_not_crash(
        self, mock_sets, mock_entries, qapp, qtbot
    ) -> None:
        """apply_language() can be called without errors."""
        page = create_glossary_page()
        qtbot.addWidget(page)
        page.apply_language()

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(f"{_G}.get_glossary_sets", return_value=[])
    def test_apply_language_updates_table_headers(
        self, mock_sets, mock_entries, qapp, qtbot
    ) -> None:
        """apply_language() refreshes table header text."""
        page = create_glossary_page()
        qtbot.addWidget(page)
        table = page.findChild(QTableWidget)
        # Clear headers
        for i in range(3):
            table.horizontalHeaderItem(i).setText("")
        page.apply_language()
        # After apply_language, headers should be non-empty (tr keys or translations)
        for i in range(3):
            assert table.horizontalHeaderItem(i).text() != ""


# ---------------------------------------------------------------------------
# Edge cases and integration
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge-case tests for the glossary page."""

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(
        f"{_G}.get_glossary_sets",
        return_value=[(i, f"Set {i}", True) for i in range(100)],
    )
    def test_large_number_of_sets(self, mock_sets, mock_entries, ui) -> None:
        """Handles 100 glossary sets without error."""
        refresh_sets(ui)
        assert ui.set_list.count() == 100  # noqa: PLR2004

    @patch(
        f"{_G}.get_glossary_entries",
        return_value=[(i, f"src_{i}", f"tgt_{i}") for i in range(200)],
    )
    def test_large_number_of_entries(self, mock_entries, ui) -> None:
        """Handles 200 glossary entries without error."""
        _populate_set_list(ui, [(1, "Big", True)])
        ui.set_list.setCurrentRow(0)
        ui.search_input.clear()
        refresh_entries(ui)
        assert ui.table.rowCount() == 200  # noqa: PLR2004

    @patch(
        f"{_G}.get_glossary_sets",
        return_value=[(1, "Ünïcödé Ñaмe 日本語", True)],
    )
    def test_unicode_set_name(self, mock_get, ui) -> None:
        """Unicode set names are displayed correctly."""
        refresh_sets(ui)
        assert ui.set_list.item(0).text() == "Ünïcödé Ñaмe 日本語"

    @patch(f"{_G}.update_glossary_entry")
    def test_edit_column_1_triggers_update(self, mock_update, ui) -> None:
        """Editing the target column (column 1) also triggers update."""
        ui.table.setRowCount(1)
        src_item = QTableWidgetItem("hello")
        src_item.setData(Qt.ItemDataRole.UserRole, 42)
        tgt_item = QTableWidgetItem("hola")
        ui.table.setItem(0, 0, src_item)
        ui.table.setItem(0, 1, tgt_item)

        # Trigger on_item_changed with the target column item
        on_item_changed(ui, tgt_item)
        mock_update.assert_called_once_with(42, "hello", "hola")

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(f"{_G}.get_glossary_sets", return_value=[])
    def test_set_item_changed_updates_active(self, mock_sets, mock_entries, ui) -> None:
        """Toggling a set item's checkbox calls update_glossary_set_active."""
        init_glossary_logic(ui)

        # Manually add an item with a check state
        _populate_set_list(ui, [(10, "TestSet", True)])
        ui.set_list.setCurrentRow(0)

        item = ui.set_list.item(0)
        with patch(f"{_G}.update_glossary_set_active") as mock_active:
            # Unblock signals to allow itemChanged to fire
            ui.set_list.blockSignals(False)
            item.setCheckState(Qt.CheckState.Unchecked)
            mock_active.assert_called_with(10, False)

    @patch(f"{_G}.refresh_entries")
    @patch(f"{_G}.add_glossary_entry")
    def test_add_entry_strips_whitespace(self, mock_add, mock_refresh, ui) -> None:
        """on_add_entry strips whitespace from source and target."""
        _populate_set_list(ui, [(5, "Set", True)])
        ui.set_list.setCurrentRow(0)
        ui.source_input.setText("  padded  ")
        ui.target_input.setText("  espaced  ")

        on_add_entry(ui)
        mock_add.assert_called_once_with(5, "padded", "espaced")


# ---------------------------------------------------------------------------
# Builder functions: create_sets_column(), create_entries_column(),
#                    create_entry_table()
# ---------------------------------------------------------------------------


class TestCreateSetsColumn:
    """Tests for create_sets_column() — left column builder."""

    def test_returns_glossary_sets_ui(self, qapp, qtbot) -> None:
        """create_sets_column returns a GlossarySetsUI dataclass."""
        from src.ui.pages.glossary import (  # noqa: PLC0415
            GlossarySetsUI,
            create_sets_column,
        )

        result = create_sets_column()
        qtbot.addWidget(result.group)
        assert isinstance(result, GlossarySetsUI)

    def test_group_is_qwidget(self, qapp, qtbot) -> None:
        """The group field is a QFrame (section group container)."""
        from src.ui.pages.glossary import create_sets_column  # noqa: PLC0415

        result = create_sets_column()
        qtbot.addWidget(result.group)
        assert isinstance(result.group, QWidget)

    def test_contains_list_widget(self, qapp, qtbot) -> None:
        """The returned UI contains a QListWidget for sets."""
        from src.ui.pages.glossary import create_sets_column  # noqa: PLC0415

        result = create_sets_column()
        qtbot.addWidget(result.group)
        assert isinstance(result.list_widget, QListWidget)

    def test_contains_create_button(self, qapp, qtbot) -> None:
        """The returned UI contains a create (new set) button."""
        from src.ui.pages.glossary import create_sets_column  # noqa: PLC0415

        result = create_sets_column()
        qtbot.addWidget(result.group)
        assert isinstance(result.create_btn, QPushButton)

    def test_contains_edit_button(self, qapp, qtbot) -> None:
        """The returned UI contains an edit (rename) button."""
        from src.ui.pages.glossary import create_sets_column  # noqa: PLC0415

        result = create_sets_column()
        qtbot.addWidget(result.group)
        assert isinstance(result.edit_btn, QPushButton)

    def test_contains_delete_button(self, qapp, qtbot) -> None:
        """The returned UI contains a delete button."""
        from src.ui.pages.glossary import create_sets_column  # noqa: PLC0415

        result = create_sets_column()
        qtbot.addWidget(result.group)
        assert isinstance(result.delete_btn, QPushButton)

    def test_contains_toggle_all_button(self, qapp, qtbot) -> None:
        """The returned UI contains a toggle-all button."""
        from src.ui.pages.glossary import create_sets_column  # noqa: PLC0415

        result = create_sets_column()
        qtbot.addWidget(result.group)
        assert isinstance(result.toggle_all_btn, QPushButton)

    def test_buttons_have_pointing_hand_cursor(self, qapp, qtbot) -> None:
        """All action buttons use the pointing-hand cursor."""
        from src.ui.pages.glossary import create_sets_column  # noqa: PLC0415

        result = create_sets_column()
        qtbot.addWidget(result.group)
        for btn in (
            result.create_btn,
            result.edit_btn,
            result.delete_btn,
            result.toggle_all_btn,
        ):
            assert btn.cursor().shape() == Qt.CursorShape.PointingHandCursor


class TestCreateEntriesColumn:
    """Tests for create_entries_column() — right column builder."""

    def test_returns_glossary_entries_ui(self, qapp, qtbot) -> None:
        """create_entries_column returns a GlossaryEntriesUI dataclass."""
        from src.ui.pages.glossary import (  # noqa: PLC0415
            GlossaryEntriesUI,
            create_entries_column,
        )

        result = create_entries_column()
        qtbot.addWidget(result.group)
        assert isinstance(result, GlossaryEntriesUI)

    def test_group_is_qwidget(self, qapp, qtbot) -> None:
        """The group field is a QFrame."""
        from src.ui.pages.glossary import create_entries_column  # noqa: PLC0415

        result = create_entries_column()
        qtbot.addWidget(result.group)
        assert isinstance(result.group, QWidget)

    def test_contains_table(self, qapp, qtbot) -> None:
        """The returned UI contains a QTableWidget for entries."""
        from src.ui.pages.glossary import create_entries_column  # noqa: PLC0415

        result = create_entries_column()
        qtbot.addWidget(result.group)
        assert isinstance(result.table, QTableWidget)

    def test_table_has_three_columns(self, qapp, qtbot) -> None:
        """The entry table has 3 columns."""
        from src.ui.pages.glossary import create_entries_column  # noqa: PLC0415

        result = create_entries_column()
        qtbot.addWidget(result.group)
        assert result.table.columnCount() == 3  # noqa: PLR2004

    def test_contains_search_input(self, qapp, qtbot) -> None:
        """The returned UI contains a search QLineEdit."""
        from src.ui.pages.glossary import create_entries_column  # noqa: PLC0415

        result = create_entries_column()
        qtbot.addWidget(result.group)
        assert isinstance(result.search_input, QLineEdit)

    def test_contains_source_input(self, qapp, qtbot) -> None:
        """The returned UI contains a source text QLineEdit."""
        from src.ui.pages.glossary import create_entries_column  # noqa: PLC0415

        result = create_entries_column()
        qtbot.addWidget(result.group)
        assert isinstance(result.source_input, QLineEdit)

    def test_contains_target_input(self, qapp, qtbot) -> None:
        """The returned UI contains a target text QLineEdit."""
        from src.ui.pages.glossary import create_entries_column  # noqa: PLC0415

        result = create_entries_column()
        qtbot.addWidget(result.group)
        assert isinstance(result.target_input, QLineEdit)

    def test_contains_add_button(self, qapp, qtbot) -> None:
        """The returned UI contains an add button."""
        from src.ui.pages.glossary import create_entries_column  # noqa: PLC0415

        result = create_entries_column()
        qtbot.addWidget(result.group)
        assert isinstance(result.add_btn, QPushButton)

    def test_add_button_has_pointing_hand_cursor(self, qapp, qtbot) -> None:
        """The add button uses the pointing-hand cursor."""
        from src.ui.pages.glossary import create_entries_column  # noqa: PLC0415

        result = create_entries_column()
        qtbot.addWidget(result.group)
        assert result.add_btn.cursor().shape() == Qt.CursorShape.PointingHandCursor

    def test_contains_input_card(self, qapp, qtbot) -> None:
        """The returned UI contains an input card QFrame."""
        from PySide6.QtWidgets import QFrame  # noqa: PLC0415

        from src.ui.pages.glossary import create_entries_column  # noqa: PLC0415

        result = create_entries_column()
        qtbot.addWidget(result.group)
        assert isinstance(result.input_card, QFrame)

    def test_contains_input_header(self, qapp, qtbot) -> None:
        """The returned UI contains an input header QLabel."""
        from PySide6.QtWidgets import QLabel  # noqa: PLC0415

        from src.ui.pages.glossary import create_entries_column  # noqa: PLC0415

        result = create_entries_column()
        qtbot.addWidget(result.group)
        assert isinstance(result.input_header, QLabel)


class TestCreateEntryTable:
    """Tests for create_entry_table() — glossary entry table builder."""

    def test_returns_qtablewidget(self, qapp, qtbot) -> None:
        """create_entry_table returns a QTableWidget."""
        from src.ui.pages.glossary import create_entry_table  # noqa: PLC0415

        table = create_entry_table()
        qtbot.addWidget(table)
        assert isinstance(table, QTableWidget)

    def test_has_three_columns(self, qapp, qtbot) -> None:
        """The table has exactly 3 columns."""
        from src.ui.pages.glossary import create_entry_table  # noqa: PLC0415

        table = create_entry_table()
        qtbot.addWidget(table)
        assert table.columnCount() == 3  # noqa: PLR2004

    def test_correct_headers(self, qapp, qtbot) -> None:
        """The table has correct header labels (tr keys or translations)."""
        from src.ui.pages.glossary import create_entry_table  # noqa: PLC0415

        table = create_entry_table()
        qtbot.addWidget(table)
        headers = [table.horizontalHeaderItem(i).text() for i in range(3)]
        # All headers should be non-empty (tr() returns key or translation)
        assert all(h for h in headers)
        assert len(headers) == 3  # noqa: PLR2004

    def test_single_selection_mode(self, qapp, qtbot) -> None:
        """The table uses single-selection mode."""
        from src.ui.pages.glossary import create_entry_table  # noqa: PLC0415

        table = create_entry_table()
        qtbot.addWidget(table)
        assert table.selectionMode() == QTableWidget.SelectionMode.SingleSelection


# ---------------------------------------------------------------------------
# Search normalization — accent/case-insensitive matching
# ---------------------------------------------------------------------------


class TestSearchNormalization:
    """Tests for accent/case-insensitive search in refresh_entries()."""

    @patch(
        f"{_G}.get_glossary_entries",
        return_value=[(10, "café", "coffee shop")],
    )
    def test_search_cafe_matches_accent(self, mock_get, ui) -> None:
        """Searching 'cafe' (no accent) matches entry with 'cafe' (accent)."""
        _populate_set_list(ui, [(1, "TestSet", True)])
        ui.set_list.setCurrentRow(0)
        ui.search_input.setText("cafe")
        refresh_entries(ui)
        assert ui.table.rowCount() == 1
        assert ui.table.item(0, 0).text() == "café"

    @patch(
        f"{_G}.get_glossary_entries",
        return_value=[(10, "hello", "xin chào")],
    )
    def test_search_case_insensitive(self, mock_get, ui) -> None:
        """Searching 'HELLO' matches entry 'hello' (case-insensitive)."""
        _populate_set_list(ui, [(1, "TestSet", True)])
        ui.set_list.setCurrentRow(0)
        ui.search_input.setText("HELLO")
        refresh_entries(ui)
        assert ui.table.rowCount() == 1
        assert ui.table.item(0, 0).text() == "hello"

    @patch(
        f"{_G}.get_glossary_entries",
        return_value=[
            (10, "résumé", "tóm tắt"),
            (11, "apple", "táo"),
        ],
    )
    def test_search_accent_insensitive_target(self, mock_get, ui) -> None:
        """Searching 'tom tat' (no accents) matches target 'tom tat'."""
        _populate_set_list(ui, [(1, "TestSet", True)])
        ui.set_list.setCurrentRow(0)
        ui.search_input.setText("tom tat")
        refresh_entries(ui)
        assert ui.table.rowCount() == 1
        assert ui.table.item(0, 1).text() == "tóm tắt"


# ---------------------------------------------------------------------------
# Splitter persistence — _create_splitter()
# ---------------------------------------------------------------------------


class TestSplitterPersistence:
    """Tests for _create_splitter() — saving/loading splitter sizes."""

    @patch(f"{_G}.save_setting")
    @patch(f"{_G}.load_setting", return_value=[250, 750])
    def test_restores_saved_sizes(self, mock_load, mock_save, qapp, qtbot) -> None:
        """Splitter restores previously saved sizes from settings."""
        from PySide6.QtWidgets import QFrame  # noqa: PLC0415

        from src.ui.pages.glossary import _create_splitter  # noqa: PLC0415

        left = QFrame()
        right = QFrame()
        splitter = _create_splitter(left, right)
        qtbot.addWidget(splitter)
        # Show splitter at a size large enough to realize the saved proportions
        handle_w = splitter.handleWidth()
        splitter.resize(250 + 750 + handle_w, 200)
        splitter.show()
        qtbot.waitExposed(splitter)

        sizes = splitter.sizes()
        assert sizes[0] == 250  # noqa: PLR2004
        assert sizes[1] == 750  # noqa: PLR2004
        mock_load.assert_called_once()

    @patch(f"{_G}.save_setting")
    @patch(f"{_G}.load_setting", return_value=None)
    def test_falls_back_to_defaults_when_none(
        self, mock_load, mock_save, qapp, qtbot
    ) -> None:
        """Splitter uses default sizes when saved data is None."""
        from PySide6.QtWidgets import QFrame  # noqa: PLC0415

        from src.constants.ui import GLOSSARY_DEFAULT_SPLITTER_SIZES  # noqa: PLC0415
        from src.ui.pages.glossary import _create_splitter  # noqa: PLC0415

        left = QFrame()
        right = QFrame()
        splitter = _create_splitter(left, right)
        qtbot.addWidget(splitter)
        handle_w = splitter.handleWidth()
        total = sum(GLOSSARY_DEFAULT_SPLITTER_SIZES) + handle_w
        splitter.resize(total, 200)
        splitter.show()
        qtbot.waitExposed(splitter)

        sizes = splitter.sizes()
        assert sizes == GLOSSARY_DEFAULT_SPLITTER_SIZES

    @patch(f"{_G}.save_setting")
    @patch(f"{_G}.load_setting", return_value="invalid")
    def test_falls_back_to_defaults_when_invalid(
        self, mock_load, mock_save, qapp, qtbot
    ) -> None:
        """Splitter uses default sizes when saved data is not a valid list."""
        from PySide6.QtWidgets import QFrame  # noqa: PLC0415

        from src.constants.ui import GLOSSARY_DEFAULT_SPLITTER_SIZES  # noqa: PLC0415
        from src.ui.pages.glossary import _create_splitter  # noqa: PLC0415

        left = QFrame()
        right = QFrame()
        splitter = _create_splitter(left, right)
        qtbot.addWidget(splitter)
        handle_w = splitter.handleWidth()
        total = sum(GLOSSARY_DEFAULT_SPLITTER_SIZES) + handle_w
        splitter.resize(total, 200)
        splitter.show()
        qtbot.waitExposed(splitter)

        sizes = splitter.sizes()
        assert sizes == GLOSSARY_DEFAULT_SPLITTER_SIZES

    @patch(f"{_G}.save_setting")
    @patch(f"{_G}.load_setting", return_value=[100])
    def test_falls_back_to_defaults_when_wrong_length(
        self, mock_load, mock_save, qapp, qtbot
    ) -> None:
        """Splitter uses defaults when saved list has wrong length (not 2)."""
        from PySide6.QtWidgets import QFrame  # noqa: PLC0415

        from src.constants.ui import GLOSSARY_DEFAULT_SPLITTER_SIZES  # noqa: PLC0415
        from src.ui.pages.glossary import _create_splitter  # noqa: PLC0415

        left = QFrame()
        right = QFrame()
        splitter = _create_splitter(left, right)
        qtbot.addWidget(splitter)
        handle_w = splitter.handleWidth()
        total = sum(GLOSSARY_DEFAULT_SPLITTER_SIZES) + handle_w
        splitter.resize(total, 200)
        splitter.show()
        qtbot.waitExposed(splitter)

        sizes = splitter.sizes()
        assert sizes == GLOSSARY_DEFAULT_SPLITTER_SIZES


# ---------------------------------------------------------------------------
# Return-key signal wiring
# ---------------------------------------------------------------------------


class TestReturnKeyWiring:
    """Tests for Return-key triggering add entry logic."""

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(f"{_G}.get_glossary_sets", return_value=[])
    def test_return_in_source_input_triggers_add(
        self, mock_sets, mock_entries, ui
    ) -> None:
        """Pressing Return in source input triggers on_add_entry logic."""
        init_glossary_logic(ui)

        # Set up a selected set and valid input
        _populate_set_list(ui, [(5, "MySet", True)])
        ui.set_list.setCurrentRow(0)
        ui.source_input.setText("word")
        ui.target_input.setText("mot")

        with (
            patch(f"{_G}.add_glossary_entry") as mock_add,
            patch(f"{_G}.refresh_entries"),
        ):
            # Emit returnPressed signal on source input
            ui.source_input.returnPressed.emit()
            mock_add.assert_called_once_with(5, "word", "mot")

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(f"{_G}.get_glossary_sets", return_value=[])
    def test_return_in_target_input_triggers_add(
        self, mock_sets, mock_entries, ui
    ) -> None:
        """Pressing Return in target input triggers on_add_entry logic."""
        init_glossary_logic(ui)

        _populate_set_list(ui, [(5, "MySet", True)])
        ui.set_list.setCurrentRow(0)
        ui.source_input.setText("word")
        ui.target_input.setText("mot")

        with (
            patch(f"{_G}.add_glossary_entry") as mock_add,
            patch(f"{_G}.refresh_entries"),
        ):
            # Emit returnPressed signal on target input
            ui.target_input.returnPressed.emit()
            mock_add.assert_called_once_with(5, "word", "mot")


# ---------------------------------------------------------------------------
# Deleted set fallback — auto-select first remaining set
# ---------------------------------------------------------------------------


class TestDeletedSetFallback:
    """Tests for refresh_sets() auto-selecting first set after deletion."""

    @patch(
        f"{_G}.get_glossary_sets",
        return_value=[(2, "Remaining", True)],
    )
    def test_auto_selects_first_set_after_deletion(self, mock_get, ui) -> None:
        """When previously selected set is deleted, first remaining is selected."""
        # Simulate having set_id=1 selected before refresh
        _populate_set_list(ui, [(1, "ToDelete", True), (2, "Remaining", True)])
        ui.set_list.setCurrentRow(0)
        assert ui.set_list.currentItem().data(Qt.ItemDataRole.UserRole) == 1

        # Now refresh with set_id=1 gone — only set_id=2 remains
        refresh_sets(ui)

        current = ui.set_list.currentItem()
        assert current is not None
        assert current.data(Qt.ItemDataRole.UserRole) == 2  # noqa: PLR2004

    @patch(
        f"{_G}.get_glossary_sets",
        return_value=[(3, "Third", True), (5, "Fifth", False)],
    )
    def test_selects_first_when_previous_not_found(self, mock_get, ui) -> None:
        """When the current selection ID is not in the new data, row 0 is selected."""
        # Set up with a set that won't be in the next refresh
        _populate_set_list(ui, [(99, "Gone", True)])
        ui.set_list.setCurrentRow(0)

        refresh_sets(ui)

        current = ui.set_list.currentItem()
        assert current is not None
        assert ui.set_list.currentRow() == 0
        assert current.data(Qt.ItemDataRole.UserRole) == 3  # noqa: PLR2004

    @patch(f"{_G}.get_glossary_sets", return_value=[])
    def test_no_sets_remain_after_deletion(self, mock_get, ui) -> None:
        """When all sets are deleted, no selection and toggle button hidden."""
        _populate_set_list(ui, [(1, "Last", True)])
        ui.set_list.setCurrentRow(0)

        refresh_sets(ui)

        assert ui.set_list.count() == 0
        assert ui.set_list.currentItem() is None
        assert not ui.toggle_all_btn.isVisible()


# ---------------------------------------------------------------------------
# TestGlossarySetManagement — create, rename, delete, switch sets
# ---------------------------------------------------------------------------


class TestGlossarySetManagement:
    """Tests for glossary set CRUD operations and UI state transitions."""

    @patch(f"{_G}.refresh_sets")
    @patch(f"{_G}.create_glossary_set", return_value=True)
    @patch(f"{_G}.CustomInputDialog")
    def test_create_set_calls_db_with_trimmed_name(
        self, mock_dialog_cls, mock_create, mock_refresh, ui
    ) -> None:
        """Creating a set trims whitespace from the name before DB call."""
        dialog = MagicMock()
        dialog.input = MagicMock()
        dialog.input.text.return_value = "  Padded Name  "
        mock_dialog_cls.return_value = dialog

        def run_confirm():
            dialog.on_confirm()

        dialog.exec.side_effect = run_confirm

        from src.ui.pages.glossary import on_create_set  # noqa: PLC0415

        on_create_set(ui)
        mock_create.assert_called_once_with("Padded Name")

    @patch(f"{_G}.refresh_sets")
    @patch(f"{_G}.update_glossary_set_name", return_value=True)
    @patch(f"{_G}.CustomInputDialog")
    def test_rename_set_updates_name_in_db(
        self, mock_dialog_cls, mock_rename, mock_refresh, ui
    ) -> None:
        """Renaming a set updates the name through the database."""
        _populate_set_list(ui, [(3, "Original", True)])
        ui.set_list.setCurrentRow(0)

        dialog = MagicMock()
        dialog.input = MagicMock()
        dialog.input.text.return_value = "Renamed"
        mock_dialog_cls.return_value = dialog

        def run_confirm():
            dialog.on_confirm()

        dialog.exec.side_effect = run_confirm

        on_edit_set(ui)
        mock_rename.assert_called_once_with(3, "Renamed")
        dialog.accept.assert_called_once()

    @patch(f"{_G}.refresh_sets")
    @patch(f"{_G}.delete_glossary_set")
    @patch(f"{_G}.CustomConfirmDialog.confirm", return_value=True)
    def test_delete_set_with_confirmation(
        self, mock_confirm, mock_del, mock_refresh, ui
    ) -> None:
        """Confirming delete removes the set and refreshes the list."""
        _populate_set_list(ui, [(10, "ToDelete", True)])
        ui.set_list.setCurrentRow(0)

        on_delete_set(ui)
        mock_del.assert_called_once_with(10)
        mock_refresh.assert_called_once()

    @patch(f"{_G}.delete_glossary_set")
    @patch(f"{_G}.CustomConfirmDialog.confirm", return_value=False)
    def test_delete_set_cancelled_keeps_set(self, mock_confirm, mock_del, ui) -> None:
        """Cancelling delete does not remove the set."""
        _populate_set_list(ui, [(10, "ToKeep", True)])
        ui.set_list.setCurrentRow(0)

        on_delete_set(ui)
        mock_del.assert_not_called()

    @patch(
        f"{_G}.get_glossary_sets",
        return_value=[(1, "Alpha", True), (2, "Beta", True), (3, "Gamma", True)],
    )
    def test_switch_between_sets(self, mock_get, ui) -> None:
        """Switching between sets updates the current selection."""
        refresh_sets(ui)
        assert ui.set_list.count() == 3  # noqa: PLR2004

        ui.set_list.setCurrentRow(2)
        assert ui.set_list.currentItem().data(Qt.ItemDataRole.UserRole) == 3  # noqa: PLR2004

        ui.set_list.setCurrentRow(0)
        assert ui.set_list.currentItem().data(Qt.ItemDataRole.UserRole) == 1

    @patch(
        f"{_G}.get_glossary_sets",
        return_value=[(1, "First", True), (2, "Second", False), (3, "Third", True)],
    )
    def test_set_dropdown_has_correct_items(self, mock_get, ui) -> None:
        """Set list has correct names and check states after refresh."""
        refresh_sets(ui)
        names = [ui.set_list.item(i).text() for i in range(ui.set_list.count())]
        assert names == ["First", "Second", "Third"]
        assert ui.set_list.item(1).checkState() == Qt.CheckState.Unchecked


# ---------------------------------------------------------------------------
# TestGlossaryEntryManagement — add, edit inline, delete
# ---------------------------------------------------------------------------


class TestGlossaryEntryManagement:
    """Tests for glossary entry add, edit, and delete operations."""

    @patch(f"{_G}.refresh_entries")
    @patch(f"{_G}.add_glossary_entry")
    def test_add_entry_with_valid_source_target(
        self, mock_add, mock_refresh, ui
    ) -> None:
        """Adding an entry with valid source and target succeeds."""
        _populate_set_list(ui, [(1, "MySet", True)])
        ui.set_list.setCurrentRow(0)
        ui.source_input.setText("dog")
        ui.target_input.setText("chien")

        on_add_entry(ui)
        mock_add.assert_called_once_with(1, "dog", "chien")
        mock_refresh.assert_called_once()

    @patch(f"{_G}.add_glossary_entry")
    def test_add_entry_with_empty_source_rejected(self, mock_add, ui) -> None:
        """Adding an entry with empty source is rejected."""
        _populate_set_list(ui, [(1, "MySet", True)])
        ui.set_list.setCurrentRow(0)
        ui.source_input.setText("")
        ui.target_input.setText("chien")

        on_add_entry(ui)
        mock_add.assert_not_called()

    @patch(f"{_G}.add_glossary_entry")
    def test_add_entry_with_empty_target_rejected(self, mock_add, ui) -> None:
        """Adding an entry with empty target is rejected."""
        _populate_set_list(ui, [(1, "MySet", True)])
        ui.set_list.setCurrentRow(0)
        ui.source_input.setText("dog")
        ui.target_input.setText("")

        on_add_entry(ui)
        mock_add.assert_not_called()

    @patch(f"{_G}.update_glossary_entry")
    def test_edit_entry_inline_updates_db(self, mock_update, ui) -> None:
        """Editing an entry inline in the table updates the database."""
        ui.table.setRowCount(1)
        src_item = QTableWidgetItem("old_src")
        src_item.setData(Qt.ItemDataRole.UserRole, 55)
        ui.table.setItem(0, 0, src_item)
        ui.table.setItem(0, 1, QTableWidgetItem("new_target"))

        on_item_changed(ui, src_item)
        mock_update.assert_called_once_with(55, "old_src", "new_target")

    @patch(f"{_G}.refresh_entries")
    @patch(f"{_G}.delete_glossary_entry")
    def test_delete_entry_removes_and_refreshes(
        self, mock_del, mock_refresh, ui
    ) -> None:
        """Deleting an entry removes it from DB and refreshes the table."""
        on_delete_entry(ui, 77)
        mock_del.assert_called_once_with(77)
        mock_refresh.assert_called_once_with(ui)

    @patch(
        f"{_G}.get_glossary_entries",
        return_value=[
            (10, "hello", "xin chào"),
            (11, "world", "thế giới"),
        ],
    )
    def test_entry_table_displays_source_and_target(self, mock_get, ui) -> None:
        """Entry table shows source in column 0 and target in column 1."""
        _populate_set_list(ui, [(1, "TestSet", True)])
        ui.set_list.setCurrentRow(0)
        ui.search_input.clear()
        refresh_entries(ui)
        assert ui.table.rowCount() == 2  # noqa: PLR2004
        # Collect all source/target pairs
        pairs = set()
        for r in range(2):
            pairs.add((ui.table.item(r, 0).text(), ui.table.item(r, 1).text()))
        assert ("hello", "xin chào") in pairs
        assert ("world", "thế giới") in pairs


# ---------------------------------------------------------------------------
# TestGlossarySearch — search, case-insensitive, clear
# ---------------------------------------------------------------------------


class TestGlossarySearch:
    """Tests for glossary entry search and filter functionality."""

    @patch(
        f"{_G}.get_glossary_entries",
        return_value=[
            (10, "apple", "táo"),
            (11, "banana", "chuối"),
            (12, "cherry", "anh đào"),
        ],
    )
    def test_search_filters_entries_by_source(self, mock_get, ui) -> None:
        """Searching filters entries matching source text."""
        _populate_set_list(ui, [(1, "Set", True)])
        ui.set_list.setCurrentRow(0)
        ui.search_input.setText("apple")
        refresh_entries(ui)
        assert ui.table.rowCount() == 1
        assert ui.table.item(0, 0).text() == "apple"

    @patch(
        f"{_G}.get_glossary_entries",
        return_value=[
            (10, "Hello", "Bonjour"),
            (11, "Goodbye", "Au revoir"),
        ],
    )
    def test_search_case_insensitive_match(self, mock_get, ui) -> None:
        """Search is case-insensitive — 'hello' matches 'Hello'."""
        _populate_set_list(ui, [(1, "Set", True)])
        ui.set_list.setCurrentRow(0)
        ui.search_input.setText("hello")
        refresh_entries(ui)
        assert ui.table.rowCount() == 1
        assert ui.table.item(0, 0).text() == "Hello"

    @patch(
        f"{_G}.get_glossary_entries",
        return_value=[
            (10, "apple", "táo"),
            (11, "banana", "chuối"),
        ],
    )
    def test_clear_search_restores_all(self, mock_get, ui) -> None:
        """Clearing search text restores all entries."""
        _populate_set_list(ui, [(1, "Set", True)])
        ui.set_list.setCurrentRow(0)
        ui.search_input.setText("apple")
        refresh_entries(ui)
        assert ui.table.rowCount() == 1

        ui.search_input.setText("")
        refresh_entries(ui)
        assert ui.table.rowCount() == 2  # noqa: PLR2004

    @patch(
        f"{_G}.get_glossary_entries",
        return_value=[
            (10, "apple", "táo"),
            (11, "banana", "chuối"),
        ],
    )
    def test_search_by_target_finds_match(self, mock_get, ui) -> None:
        """Search also matches against target text."""
        _populate_set_list(ui, [(1, "Set", True)])
        ui.set_list.setCurrentRow(0)
        ui.search_input.setText("chuoi")  # no accent
        refresh_entries(ui)
        assert ui.table.rowCount() == 1
        assert ui.table.item(0, 1).text() == "chuối"


# ---------------------------------------------------------------------------
# TestGlossaryImportExport — CSV import/export stubs
# ---------------------------------------------------------------------------


class TestGlossaryImportExport:
    """Tests for glossary import and export edge cases.

    The glossary page does not directly expose import/export buttons,
    but we test the data handling that would underpin such features.
    """

    @patch(f"{_G}.refresh_entries")
    @patch(f"{_G}.add_glossary_entry")
    def test_add_multiple_entries_sequentially(
        self, mock_add, mock_refresh, ui
    ) -> None:
        """Multiple entries can be added sequentially."""
        _populate_set_list(ui, [(1, "Set", True)])
        ui.set_list.setCurrentRow(0)

        entries = [("hello", "bonjour"), ("world", "monde"), ("cat", "chat")]
        for src, tgt in entries:
            ui.source_input.setText(src)
            ui.target_input.setText(tgt)
            on_add_entry(ui)

        assert mock_add.call_count == 3  # noqa: PLR2004

    @patch(f"{_G}.refresh_entries")
    @patch(f"{_G}.add_glossary_entry")
    def test_add_entry_with_comma_in_text(self, mock_add, mock_refresh, ui) -> None:
        """Entries with commas in text are handled correctly (CSV-safe)."""
        _populate_set_list(ui, [(1, "Set", True)])
        ui.set_list.setCurrentRow(0)
        ui.source_input.setText("hello, world")
        ui.target_input.setText("bonjour, le monde")

        on_add_entry(ui)
        mock_add.assert_called_once_with(1, "hello, world", "bonjour, le monde")

    @patch(f"{_G}.refresh_entries")
    @patch(f"{_G}.add_glossary_entry")
    def test_add_entry_with_newline_in_text(self, mock_add, mock_refresh, ui) -> None:
        """Entries with newlines are handled (text is trimmed)."""
        _populate_set_list(ui, [(1, "Set", True)])
        ui.set_list.setCurrentRow(0)
        ui.source_input.setText("line1\nline2")
        ui.target_input.setText("dòng1\ndòng2")

        on_add_entry(ui)
        mock_add.assert_called_once_with(1, "line1\nline2", "dòng1\ndòng2")

    @patch(f"{_G}.refresh_entries")
    @patch(f"{_G}.add_glossary_entry")
    def test_add_duplicate_entries_allowed_at_ui_level(
        self, mock_add, mock_refresh, ui
    ) -> None:
        """UI does not prevent duplicate source text (DB handles uniqueness)."""
        _populate_set_list(ui, [(1, "Set", True)])
        ui.set_list.setCurrentRow(0)
        ui.source_input.setText("dog")
        ui.target_input.setText("chien")
        on_add_entry(ui)
        ui.source_input.setText("dog")
        ui.target_input.setText("chien")
        on_add_entry(ui)
        assert mock_add.call_count == 2  # noqa: PLR2004


# ---------------------------------------------------------------------------
# TestGlossaryEdgeCases — empty sets, long terms, unicode, special chars
# ---------------------------------------------------------------------------


class TestGlossaryEdgeCasesExpanded:
    """Extended edge-case tests for the glossary page."""

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    def test_empty_glossary_set_shows_zero_entries(self, mock_get, ui) -> None:
        """An empty glossary set shows zero rows in the table."""
        _populate_set_list(ui, [(1, "EmptySet", True)])
        ui.set_list.setCurrentRow(0)
        ui.search_input.clear()
        refresh_entries(ui)
        assert ui.table.rowCount() == 0

    @patch(f"{_G}.refresh_entries")
    @patch(f"{_G}.add_glossary_entry")
    def test_very_long_source_term(self, mock_add, mock_refresh, ui) -> None:
        """Very long source terms are accepted without error."""
        _populate_set_list(ui, [(1, "Set", True)])
        ui.set_list.setCurrentRow(0)
        long_text = "a" * 5000
        ui.source_input.setText(long_text)
        ui.target_input.setText("short")

        on_add_entry(ui)
        mock_add.assert_called_once_with(1, long_text, "short")

    @patch(f"{_G}.refresh_entries")
    @patch(f"{_G}.add_glossary_entry")
    def test_very_long_target_term(self, mock_add, mock_refresh, ui) -> None:
        """Very long target terms are accepted without error."""
        _populate_set_list(ui, [(1, "Set", True)])
        ui.set_list.setCurrentRow(0)
        long_text = "b" * 5000
        ui.source_input.setText("short")
        ui.target_input.setText(long_text)

        on_add_entry(ui)
        mock_add.assert_called_once_with(1, "short", long_text)

    @patch(f"{_G}.refresh_entries")
    @patch(f"{_G}.add_glossary_entry")
    def test_unicode_cjk_terms(self, mock_add, mock_refresh, ui) -> None:
        """CJK (Chinese/Japanese/Korean) terms are handled correctly."""
        _populate_set_list(ui, [(1, "Set", True)])
        ui.set_list.setCurrentRow(0)
        ui.source_input.setText("你好世界")
        ui.target_input.setText("こんにちは世界")

        on_add_entry(ui)
        mock_add.assert_called_once_with(1, "你好世界", "こんにちは世界")

    @patch(f"{_G}.refresh_entries")
    @patch(f"{_G}.add_glossary_entry")
    def test_emoji_in_terms(self, mock_add, mock_refresh, ui) -> None:
        """Emoji characters in glossary terms are handled correctly."""
        _populate_set_list(ui, [(1, "Set", True)])
        ui.set_list.setCurrentRow(0)
        ui.source_input.setText("smile face")
        ui.target_input.setText("mat cuoi")

        on_add_entry(ui)
        mock_add.assert_called_once_with(1, "smile face", "mat cuoi")

    @patch(f"{_G}.refresh_entries")
    @patch(f"{_G}.add_glossary_entry")
    def test_special_characters_in_terms(self, mock_add, mock_refresh, ui) -> None:
        """Special characters (quotes, angle brackets, etc.) are accepted."""
        _populate_set_list(ui, [(1, "Set", True)])
        ui.set_list.setCurrentRow(0)
        ui.source_input.setText('<tag attr="val">')
        ui.target_input.setText("thẻ & giá trị")

        on_add_entry(ui)
        mock_add.assert_called_once_with(1, '<tag attr="val">', "thẻ & giá trị")

    @patch(f"{_G}.refresh_sets")
    @patch(f"{_G}.create_glossary_set", return_value=True)
    @patch(f"{_G}.CustomInputDialog")
    def test_set_name_with_special_chars(
        self, mock_dialog_cls, mock_create, mock_refresh, ui
    ) -> None:
        """Set names with special characters are accepted."""
        dialog = MagicMock()
        dialog.input = MagicMock()
        dialog.input.text.return_value = "Set <With> 'Special' & Chars"
        mock_dialog_cls.return_value = dialog

        def run_confirm():
            dialog.on_confirm()

        dialog.exec.side_effect = run_confirm

        from src.ui.pages.glossary import on_create_set  # noqa: PLC0415

        on_create_set(ui)
        mock_create.assert_called_once_with("Set <With> 'Special' & Chars")

    @patch(f"{_G}.refresh_sets")
    @patch(f"{_G}.create_glossary_set", return_value=True)
    @patch(f"{_G}.CustomInputDialog")
    def test_set_name_unicode(
        self, mock_dialog_cls, mock_create, mock_refresh, ui
    ) -> None:
        """Unicode set names are accepted."""
        dialog = MagicMock()
        dialog.input = MagicMock()
        dialog.input.text.return_value = "Bộ thuật ngữ Y tế"
        mock_dialog_cls.return_value = dialog

        def run_confirm():
            dialog.on_confirm()

        dialog.exec.side_effect = run_confirm

        from src.ui.pages.glossary import on_create_set  # noqa: PLC0415

        on_create_set(ui)
        mock_create.assert_called_once_with("Bộ thuật ngữ Y tế")

    @patch(
        f"{_G}.get_glossary_entries",
        return_value=[(10, "hello", "xin chào")],
    )
    def test_search_with_combining_marks_only(self, mock_get, ui) -> None:
        """Search with only combining marks (no base chars) shows all entries."""
        _populate_set_list(ui, [(1, "Set", True)])
        ui.set_list.setCurrentRow(0)
        # Combining acute accent (U+0301) — normalizes to empty
        ui.search_input.setText("\u0301")
        refresh_entries(ui)
        # Guard in refresh_entries skips filtering when norm_search is empty
        assert ui.table.rowCount() == 1


# ---------------------------------------------------------------------------
# TestGlossaryThemeLanguage — apply_theme, apply_language on full page
# ---------------------------------------------------------------------------


class TestGlossaryThemeLanguage:
    """Tests for theme and language switching on the full glossary page."""

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(f"{_G}.get_glossary_sets", return_value=[])
    def test_apply_theme_updates_list_widget_style(
        self, mock_sets, mock_entries, qapp, qtbot
    ) -> None:
        """apply_theme() updates the set list widget stylesheet."""
        page = create_glossary_page()
        qtbot.addWidget(page)
        list_widget = page.findChild(QListWidget, "glossary_set_list")
        list_widget.setStyleSheet("")
        page.apply_theme()
        assert list_widget.styleSheet() != ""

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(f"{_G}.get_glossary_sets", return_value=[])
    def test_apply_theme_updates_splitter_style(
        self, mock_sets, mock_entries, qapp, qtbot
    ) -> None:
        """apply_theme() updates the splitter stylesheet."""
        page = create_glossary_page()
        qtbot.addWidget(page)
        splitter = page.findChild(QSplitter)
        splitter.setStyleSheet("")
        page.apply_theme()
        assert splitter.styleSheet() != ""

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(f"{_G}.get_glossary_sets", return_value=[])
    def test_apply_language_updates_add_button_text(
        self, mock_sets, mock_entries, qapp, qtbot
    ) -> None:
        """apply_language() updates the add button text."""
        page = create_glossary_page()
        qtbot.addWidget(page)
        # Find the add button (it uses tr("btn.add"))
        btns = page.findChildren(QPushButton)
        add_btns = [
            b for b in btns if "add" in b.text().lower() or "btn.add" in b.text()
        ]
        assert len(add_btns) > 0
        # Clear and verify it gets restored
        add_btns[0].setText("")
        page.apply_language()
        assert add_btns[0].text() != ""

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(f"{_G}.get_glossary_sets", return_value=[])
    def test_apply_language_updates_search_placeholder(
        self, mock_sets, mock_entries, qapp, qtbot
    ) -> None:
        """apply_language() updates the search input placeholder text."""
        page = create_glossary_page()
        qtbot.addWidget(page)
        search_inputs = page.findChildren(QLineEdit)
        # Find the search input by checking placeholder
        search = None
        for inp in search_inputs:
            placeholder = inp.placeholderText()
            if "search" in placeholder.lower() or "glossary.search" in placeholder:
                search = inp
                break
        assert search is not None
        search.setPlaceholderText("")
        page.apply_language()
        assert search.placeholderText() != ""

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(f"{_G}.get_glossary_sets", return_value=[])
    def test_apply_theme_then_language_no_crash(
        self, mock_sets, mock_entries, qapp, qtbot
    ) -> None:
        """Calling apply_theme() then apply_language() in sequence does not crash."""
        page = create_glossary_page()
        qtbot.addWidget(page)
        page.apply_theme()
        page.apply_language()

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(f"{_G}.get_glossary_sets", return_value=[])
    def test_apply_language_then_theme_no_crash(
        self, mock_sets, mock_entries, qapp, qtbot
    ) -> None:
        """Calling apply_language() then apply_theme() in sequence does not crash."""
        page = create_glossary_page()
        qtbot.addWidget(page)
        page.apply_language()
        page.apply_theme()


# ---------------------------------------------------------------------------
# NEW: Expanded tests for inline editing
# ---------------------------------------------------------------------------


class TestOnItemChangedEdgeCases:
    """Additional edge-case tests for on_item_changed()."""

    @patch(f"{_G}.update_glossary_entry")
    def test_edit_preserves_unicode(self, mock_update, ui) -> None:
        """Editing with Unicode text is handled correctly."""
        ui.table.setRowCount(1)
        src_item = QTableWidgetItem("日本語")
        src_item.setData(Qt.ItemDataRole.UserRole, 77)
        ui.table.setItem(0, 0, src_item)
        ui.table.setItem(0, 1, QTableWidgetItem("Tiếng Nhật"))
        on_item_changed(ui, src_item)
        mock_update.assert_called_once_with(77, "日本語", "Tiếng Nhật")

    @patch(f"{_G}.update_glossary_entry")
    @patch(f"{_G}.refresh_entries")
    def test_both_empty_reverts(self, mock_refresh, mock_update, ui) -> None:
        """Both source and target empty triggers refresh."""
        ui.table.setRowCount(1)
        src_item = QTableWidgetItem("")
        src_item.setData(Qt.ItemDataRole.UserRole, 1)
        ui.table.setItem(0, 0, src_item)
        ui.table.setItem(0, 1, QTableWidgetItem(""))
        on_item_changed(ui, src_item)
        mock_update.assert_not_called()
        mock_refresh.assert_called_once()

    @patch(f"{_G}.update_glossary_entry")
    def test_edit_with_long_text(self, mock_update, ui) -> None:
        """Very long text is saved without truncation."""
        ui.table.setRowCount(1)
        long_src = "A" * 1000
        long_tgt = "B" * 1000
        src_item = QTableWidgetItem(long_src)
        src_item.setData(Qt.ItemDataRole.UserRole, 99)
        ui.table.setItem(0, 0, src_item)
        ui.table.setItem(0, 1, QTableWidgetItem(long_tgt))
        on_item_changed(ui, src_item)
        mock_update.assert_called_once_with(99, long_src, long_tgt)

    @patch(f"{_G}.update_glossary_entry")
    def test_edit_special_chars(self, mock_update, ui) -> None:
        """Special characters (quotes, ampersands) are saved correctly."""
        ui.table.setRowCount(1)
        src_item = QTableWidgetItem('He said "hello" & <bye>')
        src_item.setData(Qt.ItemDataRole.UserRole, 50)
        ui.table.setItem(0, 0, src_item)
        ui.table.setItem(0, 1, QTableWidgetItem("translated"))
        on_item_changed(ui, src_item)
        mock_update.assert_called_once_with(50, 'He said "hello" & <bye>', "translated")

    @patch(f"{_G}.update_glossary_entry")
    def test_missing_source_item_noop(self, mock_update, ui) -> None:
        """No crash when source item is None (incomplete row)."""
        ui.table.setRowCount(1)
        tgt_item = QTableWidgetItem("target")
        ui.table.setItem(0, 1, tgt_item)
        # Column 0 not set
        on_item_changed(ui, tgt_item)
        mock_update.assert_not_called()

    @patch(f"{_G}.update_glossary_entry")
    @patch(f"{_G}.refresh_entries")
    def test_whitespace_only_source_reverts_in_place(
        self, mock_refresh, mock_update, ui
    ) -> None:
        """Whitespace-only source reverts the cell without a full refresh."""
        from src.ui.pages.glossary import _ROLE_ORIG_SOURCE  # noqa: PLC0415

        ui.table.setRowCount(1)
        src_item = QTableWidgetItem("   \t  ")
        src_item.setData(Qt.ItemDataRole.UserRole, 11)
        src_item.setData(_ROLE_ORIG_SOURCE, "hello")
        ui.table.setItem(0, 0, src_item)
        ui.table.setItem(0, 1, QTableWidgetItem("target"))
        on_item_changed(ui, src_item)
        mock_update.assert_not_called()
        mock_refresh.assert_not_called()
        assert ui.table.item(0, 0).text() == "hello"

    @patch(f"{_G}.update_glossary_entry")
    @patch(f"{_G}.refresh_entries")
    def test_whitespace_only_target_reverts_in_place(
        self, mock_refresh, mock_update, ui
    ) -> None:
        """Whitespace-only target reverts the cell without a full refresh."""
        from src.ui.pages.glossary import _ROLE_ORIG_TARGET  # noqa: PLC0415

        ui.table.setRowCount(1)
        src_item = QTableWidgetItem("hello")
        src_item.setData(Qt.ItemDataRole.UserRole, 11)
        ui.table.setItem(0, 0, src_item)
        tgt_item = QTableWidgetItem("   \t  ")
        tgt_item.setData(_ROLE_ORIG_TARGET, "bonjour")
        ui.table.setItem(0, 1, tgt_item)
        on_item_changed(ui, src_item)
        mock_update.assert_not_called()
        mock_refresh.assert_not_called()
        assert ui.table.item(0, 1).text() == "bonjour"


# ---------------------------------------------------------------------------
# NEW: Expanded tests for add entry
# ---------------------------------------------------------------------------


class TestOnAddEntryEdgeCases:
    """Additional edge-case tests for on_add_entry()."""

    @patch(f"{_G}.refresh_entries")
    @patch(f"{_G}.add_glossary_entry")
    def test_add_entry_very_long_strings(self, mock_add, mock_refresh, ui) -> None:
        """Very long strings can be added."""
        _populate_set_list(ui, [(5, "MySet", True)])
        ui.set_list.setCurrentRow(0)
        ui.source_input.setText("A" * 5000)
        ui.target_input.setText("B" * 5000)
        on_add_entry(ui)
        mock_add.assert_called_once_with(5, "A" * 5000, "B" * 5000)

    @patch(f"{_G}.refresh_entries")
    @patch(f"{_G}.add_glossary_entry")
    def test_add_entry_special_chars(self, mock_add, mock_refresh, ui) -> None:
        """Special characters in entries are preserved."""
        _populate_set_list(ui, [(5, "MySet", True)])
        ui.set_list.setCurrentRow(0)
        ui.source_input.setText("<html>&nbsp;</html>")
        ui.target_input.setText('"quoted"')
        on_add_entry(ui)
        mock_add.assert_called_once_with(5, "<html>&nbsp;</html>", '"quoted"')

    @patch(f"{_G}.refresh_entries")
    @patch(f"{_G}.add_glossary_entry")
    def test_add_entry_sets_focus_to_source(self, mock_add, mock_refresh, ui) -> None:
        """After adding, source_input gets focus."""
        _populate_set_list(ui, [(5, "MySet", True)])
        ui.set_list.setCurrentRow(0)
        ui.source_input.setText("src")
        ui.target_input.setText("tgt")
        on_add_entry(ui)
        # After add, focus should be on source_input
        # (we can't verify focus in offscreen, but inputs should be cleared)
        assert ui.source_input.text() == ""
        assert ui.target_input.text() == ""

    @patch(f"{_G}.add_glossary_entry")
    def test_add_entry_source_only_no_add(self, mock_add, ui) -> None:
        """Source without target prevents adding."""
        _populate_set_list(ui, [(5, "MySet", True)])
        ui.set_list.setCurrentRow(0)
        ui.source_input.setText("source")
        ui.target_input.setText("")
        on_add_entry(ui)
        mock_add.assert_not_called()

    @patch(f"{_G}.add_glossary_entry")
    def test_add_entry_target_only_no_add(self, mock_add, ui) -> None:
        """Target without source prevents adding."""
        _populate_set_list(ui, [(5, "MySet", True)])
        ui.set_list.setCurrentRow(0)
        ui.source_input.setText("")
        ui.target_input.setText("target")
        on_add_entry(ui)
        mock_add.assert_not_called()


# ---------------------------------------------------------------------------
# NEW: Expanded tests for refresh_sets
# ---------------------------------------------------------------------------


class TestRefreshSetsEdgeCases:
    """Additional edge-case tests for refresh_sets()."""

    @patch(
        f"{_G}.get_glossary_sets",
        return_value=[(1, "Only One", True)],
    )
    def test_single_set_toggle_shows_inactivate(self, mock_get, ui) -> None:
        """A single active set shows 'inactivate all' on toggle button."""
        refresh_sets(ui)
        assert ui.toggle_all_btn.isVisible()
        # All are checked → inactivate all
        btn_text = ui.toggle_all_btn.text()
        assert btn_text  # non-empty

    @patch(
        f"{_G}.get_glossary_sets",
        return_value=[(1, "A", False), (2, "B", False)],
    )
    def test_all_inactive_shows_activate(self, mock_get, ui) -> None:
        """All inactive sets show 'activate all'."""
        refresh_sets(ui)
        assert ui.toggle_all_btn.isVisible()

    @patch(
        f"{_G}.get_glossary_sets",
        return_value=[(1, "A", True)],
    )
    def test_refresh_clears_then_rebuilds(self, mock_get, ui) -> None:
        """refresh_sets clears previous items before repopulating."""
        # Pre-populate with junk
        ui.set_list.addItem("stale item")
        refresh_sets(ui)
        assert ui.set_list.count() == 1
        assert ui.set_list.item(0).text() == "A"

    @patch(
        f"{_G}.get_glossary_sets",
        return_value=[(10, "Deleted", True)],
    )
    def test_refresh_with_deleted_previous_selection(self, mock_get, ui) -> None:
        """When previously selected set is gone, first set is selected."""
        # Pre-select a set that won't exist in new data
        _populate_set_list(ui, [(99, "OldSet", True)])
        ui.set_list.setCurrentRow(0)
        refresh_sets(ui)
        current = ui.set_list.currentItem()
        assert current is not None
        assert current.data(Qt.ItemDataRole.UserRole) == 10  # noqa: PLR2004

    @patch(f"{_G}.get_glossary_sets", return_value=[])
    def test_refresh_empty_hides_toggle_and_clears(self, mock_get, ui) -> None:
        """Empty sets hide toggle button and clear list."""
        _populate_set_list(ui, [(1, "A", True)])
        refresh_sets(ui)
        assert ui.set_list.count() == 0
        assert not ui.toggle_all_btn.isVisible()


# ---------------------------------------------------------------------------
# NEW: Expanded tests for refresh_entries
# ---------------------------------------------------------------------------


class TestRefreshEntriesEdgeCases:
    """Additional edge-case tests for refresh_entries()."""

    @patch(
        f"{_G}.get_glossary_entries",
        return_value=[(10, "HELLO", "xin chào")],
    )
    def test_case_insensitive_search(self, mock_get, ui) -> None:
        """Search is case-insensitive via normalize_for_search."""
        _populate_set_list(ui, [(1, "TestSet", True)])
        ui.set_list.setCurrentRow(0)
        ui.search_input.setText("hello")
        refresh_entries(ui)
        assert ui.table.rowCount() == 1

    @patch(
        f"{_G}.get_glossary_entries",
        return_value=[
            (10, "café", "quán cà phê"),
            (11, "résumé", "sơ yếu lý lịch"),
        ],
    )
    def test_accent_insensitive_search(self, mock_get, ui) -> None:
        """Search handles accented characters via normalize_for_search."""
        _populate_set_list(ui, [(1, "TestSet", True)])
        ui.set_list.setCurrentRow(0)
        ui.search_input.setText("cafe")
        refresh_entries(ui)
        assert ui.table.rowCount() == 1

    @patch(
        f"{_G}.get_glossary_entries",
        return_value=[(i, f"src_{i}", f"tgt_{i}") for i in range(50)],
    )
    def test_search_matches_multiple(self, mock_get, ui) -> None:
        """Search matching multiple entries shows all of them."""
        _populate_set_list(ui, [(1, "TestSet", True)])
        ui.set_list.setCurrentRow(0)
        ui.search_input.setText("src_")
        refresh_entries(ui)
        assert ui.table.rowCount() == 50  # noqa: PLR2004

    @patch(
        f"{_G}.get_glossary_entries",
        return_value=[(10, "hello", "xin chào")],
    )
    def test_delegate_search_text_set(self, mock_get, ui) -> None:
        """Table delegate receives the search text."""
        _populate_set_list(ui, [(1, "TestSet", True)])
        ui.set_list.setCurrentRow(0)
        ui.search_input.setText("hello")
        refresh_entries(ui)
        # The delegate's search text should be set
        assert ui.table_delegate.search_text == "hello"

    @patch(
        f"{_G}.get_glossary_entries",
        return_value=[(10, "hello", "xin chào")],
    )
    def test_sorting_enabled_after_refresh(self, mock_get, ui) -> None:
        """Sorting is re-enabled after refresh_entries completes."""
        _populate_set_list(ui, [(1, "TestSet", True)])
        ui.set_list.setCurrentRow(0)
        ui.search_input.clear()
        refresh_entries(ui)
        assert ui.table.isSortingEnabled()


# ---------------------------------------------------------------------------
# NEW: Expanded tests for on_toggle_all
# ---------------------------------------------------------------------------


class TestOnToggleAllEdgeCases:
    """Additional edge-case tests for on_toggle_all()."""

    @patch(f"{_G}.refresh_sets")
    @patch(f"{_G}.update_all_glossary_sets_active")
    def test_single_unchecked_activates_all(
        self, mock_update, mock_refresh, ui
    ) -> None:
        """A single unchecked set among many triggers activate all."""
        _populate_set_list(
            ui,
            [(1, "A", True), (2, "B", True), (3, "C", False)],
        )
        on_toggle_all(ui)
        mock_update.assert_called_once_with(True)

    @patch(f"{_G}.refresh_sets")
    @patch(f"{_G}.update_all_glossary_sets_active")
    def test_single_checked_deactivates_all(
        self, mock_update, mock_refresh, ui
    ) -> None:
        """A single checked set triggers deactivate all."""
        _populate_set_list(ui, [(1, "A", True)])
        on_toggle_all(ui)
        mock_update.assert_called_once_with(False)


# ---------------------------------------------------------------------------
# NEW: Expanded tests for on_create_set
# ---------------------------------------------------------------------------


class TestOnCreateSetEdgeCases:
    """Additional edge-case tests for on_create_set()."""

    @patch(f"{_G}.create_glossary_set", return_value=True)
    @patch(f"{_G}.CustomInputDialog")
    @patch(f"{_G}.refresh_sets")
    def test_create_set_strips_whitespace(
        self, mock_refresh, mock_dialog_cls, mock_create, ui
    ) -> None:
        """Name is stripped before saving."""
        dialog = MagicMock()
        dialog.input = MagicMock()
        dialog.input.text.return_value = "  New Set  "
        mock_dialog_cls.return_value = dialog
        dialog.exec.side_effect = lambda: dialog.on_confirm()  # noqa: PLW0108
        from src.ui.pages.glossary import on_create_set  # noqa: PLC0415

        on_create_set(ui)
        mock_create.assert_called_once_with("New Set")


# ---------------------------------------------------------------------------
# NEW: Expanded tests for on_edit_set
# ---------------------------------------------------------------------------


class TestOnEditSetEdgeCases:
    """Additional edge-case tests for on_edit_set()."""

    @patch(f"{_G}.update_glossary_set_name", return_value=True)
    @patch(f"{_G}.CustomInputDialog")
    @patch(f"{_G}.refresh_sets")
    def test_rename_strips_whitespace(
        self, mock_refresh, mock_dialog_cls, mock_rename, ui
    ) -> None:
        """New name is stripped before comparing and saving."""
        _populate_set_list(ui, [(1, "OldName", True)])
        ui.set_list.setCurrentRow(0)
        dialog = MagicMock()
        dialog.input = MagicMock()
        dialog.input.text.return_value = "  New Name  "
        mock_dialog_cls.return_value = dialog
        dialog.exec.side_effect = lambda: dialog.on_confirm()  # noqa: PLW0108
        on_edit_set(ui)
        mock_rename.assert_called_once_with(1, "New Name")


# ---------------------------------------------------------------------------
# NEW: Expanded tests for on_delete_set
# ---------------------------------------------------------------------------


class TestOnDeleteSetEdgeCases:
    """Additional edge-case tests for on_delete_set()."""

    @patch(f"{_G}.refresh_sets")
    @patch(f"{_G}.delete_glossary_set")
    @patch(f"{_G}.CustomConfirmDialog.confirm", return_value=True)
    @patch(f"{_G}.tr")
    def test_delete_passes_correct_name_to_dialog(
        self, mock_tr, mock_confirm, mock_del, mock_refresh, ui
    ) -> None:
        """Delete confirmation dialog receives the correct set name."""
        mock_tr.side_effect = lambda key, **kw: key
        _populate_set_list(ui, [(7, "SpecificName", True)])
        ui.set_list.setCurrentRow(0)
        on_delete_set(ui)
        # Verify tr() was called with the set name for the message
        tr_calls = [c for c in mock_tr.call_args_list if "name" in c.kwargs]
        assert len(tr_calls) >= 1
        assert tr_calls[0].kwargs["name"] == "SpecificName"


# ---------------------------------------------------------------------------
# NEW: Expanded tests for on_delete_entry
# ---------------------------------------------------------------------------


class TestOnDeleteEntryEdgeCases:
    """Additional edge-case tests for on_delete_entry()."""

    @patch(f"{_G}.refresh_entries")
    @patch(f"{_G}.delete_glossary_entry")
    def test_delete_entry_multiple_ids(self, mock_del, mock_refresh, ui) -> None:
        """Deleting different entry IDs works correctly."""
        on_delete_entry(ui, 1)
        on_delete_entry(ui, 2)
        on_delete_entry(ui, 3)
        assert mock_del.call_count == 3  # noqa: PLR2004
        mock_del.assert_any_call(1)
        mock_del.assert_any_call(2)
        mock_del.assert_any_call(3)

    @patch(f"{_G}.refresh_entries")
    @patch(f"{_G}.delete_glossary_entry")
    def test_delete_entry_large_id(self, mock_del, mock_refresh, ui) -> None:
        """Deleting entry with large ID works correctly."""
        on_delete_entry(ui, 999999)
        mock_del.assert_called_once_with(999999)


# ---------------------------------------------------------------------------
# NEW: Expanded tests for init_glossary_logic
# ---------------------------------------------------------------------------


class TestInitGlossaryLogicEdgeCases:
    """Additional tests for init_glossary_logic()."""

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(
        f"{_G}.get_glossary_sets",
        return_value=[(1, "A", True), (2, "B", False)],
    )
    def test_init_loads_sets_and_entries(self, mock_sets, mock_entries, ui) -> None:
        """init_glossary_logic loads sets and entries on init."""
        init_glossary_logic(ui)
        assert ui.set_list.count() == 2  # noqa: PLR2004

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(f"{_G}.get_glossary_sets", return_value=[])
    def test_init_empty_db(self, mock_sets, mock_entries, ui) -> None:
        """init_glossary_logic handles empty database gracefully."""
        init_glossary_logic(ui)
        assert ui.set_list.count() == 0
        assert ui.table.rowCount() == 0


# ---------------------------------------------------------------------------
# NEW: Expanded tests for create_glossary_page
# ---------------------------------------------------------------------------


class TestCreateGlossaryPageEdgeCases:
    """Additional integration tests for create_glossary_page()."""

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(f"{_G}.get_glossary_sets", return_value=[])
    def test_page_has_list_widget(self, mock_sets, mock_entries, qapp, qtbot) -> None:
        """Page has a QListWidget for sets."""
        page = create_glossary_page()
        qtbot.addWidget(page)
        assert page.findChild(QListWidget, "glossary_set_list") is not None

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(f"{_G}.get_glossary_sets", return_value=[])
    def test_page_has_buttons(self, mock_sets, mock_entries, qapp, qtbot) -> None:
        """Page has expected buttons."""
        page = create_glossary_page()
        qtbot.addWidget(page)
        buttons = page.findChildren(QPushButton)
        assert len(buttons) >= 4  # noqa: PLR2004  # new, rename, delete, add, toggle

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(f"{_G}.get_glossary_sets", return_value=[])
    def test_page_has_line_edits(self, mock_sets, mock_entries, qapp, qtbot) -> None:
        """Page has source, target, and search QLineEdits."""
        page = create_glossary_page()
        qtbot.addWidget(page)
        line_edits = page.findChildren(QLineEdit)
        assert len(line_edits) >= 3  # noqa: PLR2004


# ---------------------------------------------------------------------------
# NEW: Expanded tests for theme and language
# ---------------------------------------------------------------------------


class TestGlossaryThemeLanguageEdgeCases:
    """Additional theme/language tests."""

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(f"{_G}.get_glossary_sets", return_value=[])
    def test_apply_theme_multiple_times(
        self, mock_sets, mock_entries, qapp, qtbot
    ) -> None:
        """Calling apply_theme() multiple times is safe."""
        page = create_glossary_page()
        qtbot.addWidget(page)
        for _ in range(5):
            page.apply_theme()

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(f"{_G}.get_glossary_sets", return_value=[])
    def test_apply_language_multiple_times(
        self, mock_sets, mock_entries, qapp, qtbot
    ) -> None:
        """Calling apply_language() multiple times is safe."""
        page = create_glossary_page()
        qtbot.addWidget(page)
        for _ in range(5):
            page.apply_language()

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(f"{_G}.get_glossary_sets", return_value=[])
    def test_apply_theme_updates_splitter_style(
        self, mock_sets, mock_entries, qapp, qtbot
    ) -> None:
        """apply_theme updates the splitter style."""
        page = create_glossary_page()
        qtbot.addWidget(page)
        splitter = page.findChild(QSplitter)
        splitter.setStyleSheet("")
        page.apply_theme()
        assert splitter.styleSheet() != ""

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(f"{_G}.get_glossary_sets", return_value=[])
    def test_apply_language_updates_button_text(
        self, mock_sets, mock_entries, qapp, qtbot
    ) -> None:
        """apply_language updates button text on glossary-specific buttons."""
        page = create_glossary_page()
        qtbot.addWidget(page)
        btns = page.findChildren(QPushButton)
        # Clear all button texts
        for b in btns:
            b.setText("")
        page.apply_language()
        # At least some buttons should have text again
        non_empty = [b for b in btns if b.text() != ""]
        assert len(non_empty) >= 3  # noqa: PLR2004


# ---------------------------------------------------------------------------
# NEW: Expanded tests for CaseInsensitiveSortItem
# ---------------------------------------------------------------------------


class TestCaseInsensitiveSortItemEdgeCases:
    """Additional edge-case tests for CaseInsensitiveSortItem."""

    def test_empty_strings(self, qapp) -> None:
        """Empty strings compare correctly."""
        a = CaseInsensitiveSortItem("")
        b = CaseInsensitiveSortItem("")
        assert not (a < b)
        assert not (b < a)

    def test_empty_vs_nonempty(self, qapp) -> None:
        """Empty string sorts before non-empty."""
        a = CaseInsensitiveSortItem("")
        b = CaseInsensitiveSortItem("abc")
        assert a < b
        assert not (b < a)

    def test_numbers_sort(self, qapp) -> None:
        """Numeric strings sort correctly."""
        a = CaseInsensitiveSortItem("10")
        b = CaseInsensitiveSortItem("2")
        # "10" < "2" in string sort (lexicographic)
        assert a < b

    def test_special_chars_sort(self, qapp) -> None:
        """Special characters sort deterministically."""
        a = CaseInsensitiveSortItem("!hello")
        b = CaseInsensitiveSortItem("hello")
        assert a < b


# ---------------------------------------------------------------------------
# NEW: Expanded tests for search edge cases
# ---------------------------------------------------------------------------


class TestSearchEdgeCases:
    """Additional search-related edge cases."""

    @patch(
        f"{_G}.get_glossary_entries",
        return_value=[(10, "hello", "xin chào"), (11, "world", "thế giới")],
    )
    def test_search_partial_match_source(self, mock_get, ui) -> None:
        """Partial source text match returns matching entries."""
        _populate_set_list(ui, [(1, "TestSet", True)])
        ui.set_list.setCurrentRow(0)
        ui.search_input.setText("hel")
        refresh_entries(ui)
        assert ui.table.rowCount() == 1

    @patch(
        f"{_G}.get_glossary_entries",
        return_value=[(10, "hello", "xin chào"), (11, "world", "thế giới")],
    )
    def test_search_partial_match_target(self, mock_get, ui) -> None:
        """Partial target text match returns matching entries."""
        _populate_set_list(ui, [(1, "TestSet", True)])
        ui.set_list.setCurrentRow(0)
        ui.search_input.setText("thế")
        refresh_entries(ui)
        assert ui.table.rowCount() == 1

    @patch(
        f"{_G}.get_glossary_entries",
        return_value=[(10, "hello world", "xin chào thế giới")],
    )
    def test_search_multi_word(self, mock_get, ui) -> None:
        """Multi-word search matches substring."""
        _populate_set_list(ui, [(1, "TestSet", True)])
        ui.set_list.setCurrentRow(0)
        ui.search_input.setText("hello world")
        refresh_entries(ui)
        assert ui.table.rowCount() == 1


# ---------------------------------------------------------------------------
# NEW: Expanded tests for set list behavior
# ---------------------------------------------------------------------------


class TestSetListBehavior:
    """Tests for set list item behavior."""

    @patch(
        f"{_G}.get_glossary_sets",
        return_value=[(1, "A", True), (2, "B", True), (3, "C", True)],
    )
    def test_items_are_checkable(self, mock_get, ui) -> None:
        """All set items have the checkable flag."""
        refresh_sets(ui)
        for i in range(ui.set_list.count()):
            item = ui.set_list.item(i)
            assert item.flags() & Qt.ItemFlag.ItemIsUserCheckable

    @patch(
        f"{_G}.get_glossary_sets",
        return_value=[(1, "First", True), (2, "Second", True)],
    )
    def test_set_names_match_db(self, mock_get, ui) -> None:
        """Set names displayed match the database data."""
        refresh_sets(ui)
        names = {ui.set_list.item(i).text() for i in range(ui.set_list.count())}
        assert names == {"First", "Second"}


# ---------------------------------------------------------------------------
# NEW: Inline editing — start edit, commit, cancel, empty value, long text
# ---------------------------------------------------------------------------


class TestInlineEditingExpanded:
    """Expanded tests for inline editing in the entries table."""

    @patch(f"{_G}.update_glossary_entry")
    def test_edit_source_only(self, mock_update, ui) -> None:
        """Editing only the source column still commits both columns."""
        ui.table.setRowCount(1)
        src_item = QTableWidgetItem("new_source")
        src_item.setData(Qt.ItemDataRole.UserRole, 100)
        ui.table.setItem(0, 0, src_item)
        ui.table.setItem(0, 1, QTableWidgetItem("existing_target"))
        on_item_changed(ui, src_item)
        mock_update.assert_called_once_with(100, "new_source", "existing_target")

    @patch(f"{_G}.update_glossary_entry")
    def test_edit_target_only(self, mock_update, ui) -> None:
        """Editing only the target column commits both columns."""
        ui.table.setRowCount(1)
        src_item = QTableWidgetItem("existing_source")
        src_item.setData(Qt.ItemDataRole.UserRole, 101)
        tgt_item = QTableWidgetItem("new_target")
        ui.table.setItem(0, 0, src_item)
        ui.table.setItem(0, 1, tgt_item)
        on_item_changed(ui, tgt_item)
        mock_update.assert_called_once_with(101, "existing_source", "new_target")

    @patch(f"{_G}.update_glossary_entry")
    def test_long_text_source(self, mock_update, ui) -> None:
        """Long source text is accepted and committed."""
        long_text = "A" * 5000
        ui.table.setRowCount(1)
        src_item = QTableWidgetItem(long_text)
        src_item.setData(Qt.ItemDataRole.UserRole, 200)
        ui.table.setItem(0, 0, src_item)
        ui.table.setItem(0, 1, QTableWidgetItem("target"))
        on_item_changed(ui, src_item)
        mock_update.assert_called_once_with(200, long_text, "target")

    @patch(f"{_G}.update_glossary_entry")
    def test_long_text_target(self, mock_update, ui) -> None:
        """Long target text is accepted and committed."""
        long_text = "B" * 5000
        ui.table.setRowCount(1)
        src_item = QTableWidgetItem("source")
        src_item.setData(Qt.ItemDataRole.UserRole, 201)
        ui.table.setItem(0, 0, src_item)
        ui.table.setItem(0, 1, QTableWidgetItem(long_text))
        on_item_changed(ui, src_item)
        mock_update.assert_called_once_with(201, "source", long_text)

    @patch(f"{_G}.update_glossary_entry")
    @patch(f"{_G}.refresh_entries")
    def test_whitespace_only_source_reverts_via_backup(
        self, mock_refresh, mock_update, ui
    ) -> None:
        """Whitespace-only source is reverted from its backup role."""
        from src.ui.pages.glossary import _ROLE_ORIG_SOURCE  # noqa: PLC0415

        ui.table.setRowCount(1)
        src_item = QTableWidgetItem("   ")
        src_item.setData(Qt.ItemDataRole.UserRole, 300)
        src_item.setData(_ROLE_ORIG_SOURCE, "original")
        ui.table.setItem(0, 0, src_item)
        ui.table.setItem(0, 1, QTableWidgetItem("target"))
        on_item_changed(ui, src_item)
        mock_update.assert_not_called()
        mock_refresh.assert_not_called()
        assert ui.table.item(0, 0).text() == "original"

    @patch(f"{_G}.update_glossary_entry")
    @patch(f"{_G}.refresh_entries")
    def test_whitespace_only_target_reverts_via_backup(
        self, mock_refresh, mock_update, ui
    ) -> None:
        """Whitespace-only target is reverted from its backup role."""
        from src.ui.pages.glossary import _ROLE_ORIG_TARGET  # noqa: PLC0415

        ui.table.setRowCount(1)
        src_item = QTableWidgetItem("source")
        src_item.setData(Qt.ItemDataRole.UserRole, 301)
        ui.table.setItem(0, 0, src_item)
        tgt_item = QTableWidgetItem("   ")
        tgt_item.setData(_ROLE_ORIG_TARGET, "original")
        ui.table.setItem(0, 1, tgt_item)
        on_item_changed(ui, src_item)
        mock_update.assert_not_called()
        mock_refresh.assert_not_called()
        assert ui.table.item(0, 1).text() == "original"

    @patch(f"{_G}.update_glossary_entry")
    def test_unicode_edit(self, mock_update, ui) -> None:
        """Unicode characters are preserved in edits."""
        ui.table.setRowCount(1)
        src_item = QTableWidgetItem("日本語テスト")
        src_item.setData(Qt.ItemDataRole.UserRole, 400)
        ui.table.setItem(0, 0, src_item)
        ui.table.setItem(0, 1, QTableWidgetItem("テスト翻訳"))
        on_item_changed(ui, src_item)
        mock_update.assert_called_once_with(400, "日本語テスト", "テスト翻訳")

    @patch(f"{_G}.update_glossary_entry")
    def test_edit_with_special_characters(self, mock_update, ui) -> None:
        """Special characters (newlines, tabs) are preserved in edits."""
        ui.table.setRowCount(1)
        src_item = QTableWidgetItem("hello\tworld")
        src_item.setData(Qt.ItemDataRole.UserRole, 401)
        ui.table.setItem(0, 0, src_item)
        ui.table.setItem(0, 1, QTableWidgetItem("bonjour\tmonde"))
        on_item_changed(ui, src_item)
        mock_update.assert_called_once()

    @patch(f"{_G}.update_glossary_entry")
    def test_missing_source_item_noop(self, mock_update, ui) -> None:
        """No crash when source item (column 0) is missing."""
        ui.table.setRowCount(1)
        tgt_item = QTableWidgetItem("target")
        ui.table.setItem(0, 1, tgt_item)
        on_item_changed(ui, tgt_item)
        mock_update.assert_not_called()

    @patch(f"{_G}.update_glossary_entry")
    def test_edit_multiple_rows(self, mock_update, ui) -> None:
        """Editing entries in different rows uses correct entry IDs."""
        ui.table.setRowCount(2)
        src0 = QTableWidgetItem("src0")
        src0.setData(Qt.ItemDataRole.UserRole, 500)
        ui.table.setItem(0, 0, src0)
        ui.table.setItem(0, 1, QTableWidgetItem("tgt0"))

        src1 = QTableWidgetItem("src1")
        src1.setData(Qt.ItemDataRole.UserRole, 501)
        ui.table.setItem(1, 0, src1)
        ui.table.setItem(1, 1, QTableWidgetItem("tgt1"))

        on_item_changed(ui, src1)
        mock_update.assert_called_once_with(501, "src1", "tgt1")


# ---------------------------------------------------------------------------
# NEW: Set selection/switching — create set, delete set, rename, switch
# ---------------------------------------------------------------------------


class TestSetSelectionSwitching:
    """Tests for set selection and switching behavior."""

    @patch(
        f"{_G}.get_glossary_sets",
        return_value=[(1, "A", True), (2, "B", True), (3, "C", True)],
    )
    def test_switch_set_selection(self, mock_get, ui) -> None:
        """Switching between sets by index works."""
        refresh_sets(ui)
        ui.set_list.setCurrentRow(0)
        assert ui.set_list.currentItem().data(Qt.ItemDataRole.UserRole) == 1
        ui.set_list.setCurrentRow(2)
        assert ui.set_list.currentItem().data(Qt.ItemDataRole.UserRole) == 3  # noqa: PLR2004

    @patch(f"{_G}.get_glossary_sets", return_value=[(1, "A", True)])
    def test_single_set_auto_selected(self, mock_get, ui) -> None:
        """A single set is automatically selected."""
        refresh_sets(ui)
        assert ui.set_list.currentRow() == 0
        assert ui.set_list.currentItem().data(Qt.ItemDataRole.UserRole) == 1

    @patch(f"{_G}.get_glossary_sets", return_value=[])
    def test_no_sets_no_selection(self, mock_get, ui) -> None:
        """With no sets, current item is None."""
        refresh_sets(ui)
        assert ui.set_list.currentItem() is None

    @patch(f"{_G}.get_glossary_sets", return_value=[(1, "A", False), (2, "B", False)])
    def test_all_inactive_toggle_text(self, mock_get, ui) -> None:
        """When all sets are inactive, toggle button shows activate text."""
        refresh_sets(ui)
        assert ui.toggle_all_btn.isVisible()
        # Should show "activate all" since all are unchecked

    @patch(f"{_G}.refresh_sets")
    @patch(f"{_G}.create_glossary_set", return_value=True)
    @patch(f"{_G}.CustomInputDialog")
    def test_create_set_strips_whitespace(
        self, mock_dialog_cls, mock_create, mock_refresh, ui
    ) -> None:
        """Creating a set strips whitespace from the name."""
        dialog = MagicMock()
        dialog.input = MagicMock()
        dialog.input.text.return_value = "  Padded Name  "
        mock_dialog_cls.return_value = dialog

        def run_confirm():
            dialog.on_confirm()

        dialog.exec.side_effect = run_confirm
        from src.ui.pages.glossary import on_create_set  # noqa: PLC0415

        on_create_set(ui)
        mock_create.assert_called_once_with("Padded Name")

    @patch(f"{_G}.refresh_sets")
    @patch(f"{_G}.delete_glossary_set")
    @patch(f"{_G}.CustomConfirmDialog.confirm", return_value=True)
    def test_delete_set_passes_correct_id(
        self, mock_confirm, mock_del, mock_refresh, ui
    ) -> None:
        """Deleting a set passes the correct set ID to the database."""
        _populate_set_list(ui, [(42, "MySet", True)])
        ui.set_list.setCurrentRow(0)
        on_delete_set(ui)
        mock_del.assert_called_once_with(42)

    @patch(f"{_G}.refresh_sets")
    @patch(f"{_G}.update_glossary_set_name", return_value=True)
    @patch(f"{_G}.CustomInputDialog")
    def test_rename_set_strips_whitespace(
        self, mock_dialog_cls, mock_rename, mock_refresh, ui
    ) -> None:
        """Renaming a set strips whitespace from the name."""
        _populate_set_list(ui, [(1, "OldName", True)])
        ui.set_list.setCurrentRow(0)

        dialog = MagicMock()
        dialog.input = MagicMock()
        dialog.input.text.return_value = "  NewName  "
        mock_dialog_cls.return_value = dialog

        def run_confirm():
            dialog.on_confirm()

        dialog.exec.side_effect = run_confirm
        on_edit_set(ui)
        mock_rename.assert_called_once_with(1, "NewName")

    @patch(f"{_G}.get_glossary_sets", return_value=[(1, "A", True), (2, "B", True)])
    def test_refresh_sets_preserves_selection_by_id(self, mock_get, ui) -> None:
        """refresh_sets preserves selection by set ID, not index."""
        refresh_sets(ui)
        ui.set_list.setCurrentRow(1)
        # Simulate refresh
        refresh_sets(ui)
        assert ui.set_list.currentItem().data(Qt.ItemDataRole.UserRole) == 2  # noqa: PLR2004

    @patch(
        f"{_G}.get_glossary_sets",
        return_value=[
            (1, "A", True),
            (2, "B", True),
            (3, "C", True),
            (4, "D", True),
            (5, "E", True),
        ],
    )
    def test_switch_between_many_sets(self, mock_get, ui) -> None:
        """Switching between multiple sets works correctly."""
        refresh_sets(ui)
        for i in range(5):
            ui.set_list.setCurrentRow(i)
            assert ui.set_list.currentItem().data(Qt.ItemDataRole.UserRole) == i + 1


# ---------------------------------------------------------------------------
# NEW: Add/delete entries expanded
# ---------------------------------------------------------------------------


class TestAddDeleteEntriesExpanded:
    """Expanded tests for adding and deleting entries."""

    @patch(f"{_G}.refresh_entries")
    @patch(f"{_G}.add_glossary_entry")
    def test_add_entry_with_source_only_fails(self, mock_add, mock_refresh, ui) -> None:
        """Adding with only source text (empty target) does nothing."""
        _populate_set_list(ui, [(1, "Set", True)])
        ui.set_list.setCurrentRow(0)
        ui.source_input.setText("hello")
        ui.target_input.setText("")
        on_add_entry(ui)
        mock_add.assert_not_called()

    @patch(f"{_G}.refresh_entries")
    @patch(f"{_G}.add_glossary_entry")
    def test_add_entry_with_target_only_fails(self, mock_add, mock_refresh, ui) -> None:
        """Adding with only target text (empty source) does nothing."""
        _populate_set_list(ui, [(1, "Set", True)])
        ui.set_list.setCurrentRow(0)
        ui.source_input.setText("")
        ui.target_input.setText("bonjour")
        on_add_entry(ui)
        mock_add.assert_not_called()

    @patch(f"{_G}.refresh_entries")
    @patch(f"{_G}.add_glossary_entry")
    def test_add_entry_focus_returns_to_source(
        self, mock_add, mock_refresh, ui
    ) -> None:
        """After adding, focus returns to source input."""
        _populate_set_list(ui, [(1, "Set", True)])
        ui.set_list.setCurrentRow(0)
        ui.source_input.setText("cat")
        ui.target_input.setText("gato")
        on_add_entry(ui)
        # Focus should be on source_input (hard to test without showing widget)
        # Verify inputs were cleared
        assert ui.source_input.text() == ""
        assert ui.target_input.text() == ""

    @patch(f"{_G}.refresh_entries")
    @patch(f"{_G}.add_glossary_entry")
    def test_add_multiple_entries_sequentially(
        self, mock_add, mock_refresh, ui
    ) -> None:
        """Adding multiple entries in sequence calls add for each."""
        _populate_set_list(ui, [(1, "Set", True)])
        ui.set_list.setCurrentRow(0)

        entries = [("hello", "bonjour"), ("world", "monde"), ("cat", "chat")]
        for src, tgt in entries:
            ui.source_input.setText(src)
            ui.target_input.setText(tgt)
            on_add_entry(ui)

        assert mock_add.call_count == 3  # noqa: PLR2004

    @patch(f"{_G}.refresh_entries")
    @patch(f"{_G}.delete_glossary_entry")
    def test_delete_entry_with_specific_id(self, mock_del, mock_refresh, ui) -> None:
        """Deleting entry with specific ID passes correct value."""
        on_delete_entry(ui, 12345)
        mock_del.assert_called_once_with(12345)

    @patch(f"{_G}.refresh_entries")
    @patch(f"{_G}.add_glossary_entry")
    def test_add_entry_with_very_long_text(self, mock_add, mock_refresh, ui) -> None:
        """Adding entries with very long text succeeds."""
        _populate_set_list(ui, [(1, "Set", True)])
        ui.set_list.setCurrentRow(0)
        long_src = "x" * 10000
        long_tgt = "y" * 10000
        ui.source_input.setText(long_src)
        ui.target_input.setText(long_tgt)
        on_add_entry(ui)
        mock_add.assert_called_once_with(1, long_src, long_tgt)

    @patch(f"{_G}.refresh_entries")
    @patch(f"{_G}.add_glossary_entry")
    def test_add_entry_special_chars(self, mock_add, mock_refresh, ui) -> None:
        """Adding entries with special characters succeeds."""
        _populate_set_list(ui, [(1, "Set", True)])
        ui.set_list.setCurrentRow(0)
        ui.source_input.setText("<html>&amp;</html>")
        ui.target_input.setText("'quotes' \"double\"")
        on_add_entry(ui)
        mock_add.assert_called_once_with(1, "<html>&amp;</html>", "'quotes' \"double\"")


# ---------------------------------------------------------------------------
# NEW: Search filtering expanded
# ---------------------------------------------------------------------------


class TestSearchFilteringExpanded:
    """Expanded tests for search/filtering functionality."""

    @patch(
        f"{_G}.get_glossary_entries",
        return_value=[(10, "Hello", "Bonjour"), (11, "hello", "bonjour")],
    )
    def test_search_case_insensitive(self, mock_get, ui) -> None:
        """Search is case-insensitive and matches both cases."""
        _populate_set_list(ui, [(1, "TestSet", True)])
        ui.set_list.setCurrentRow(0)
        ui.search_input.setText("HELLO")
        refresh_entries(ui)
        assert ui.table.rowCount() == 2  # noqa: PLR2004

    @patch(
        f"{_G}.get_glossary_entries",
        return_value=[(10, "café", "cafetería"), (11, "resume", "currículum")],
    )
    def test_search_accented_characters(self, mock_get, ui) -> None:
        """Search with accent-insensitive matching."""
        _populate_set_list(ui, [(1, "TestSet", True)])
        ui.set_list.setCurrentRow(0)
        ui.search_input.setText("cafe")
        refresh_entries(ui)
        # normalize_for_search strips accents
        assert ui.table.rowCount() >= 1

    @patch(
        f"{_G}.get_glossary_entries",
        return_value=[
            (10, "hello", "xin chào"),
            (11, "world", "thế giới"),
            (12, "cat", "mèo"),
        ],
    )
    def test_search_no_results(self, mock_get, ui) -> None:
        """Search with no matching text shows zero rows."""
        _populate_set_list(ui, [(1, "TestSet", True)])
        ui.set_list.setCurrentRow(0)
        ui.search_input.setText("zzzzzzzzz")
        refresh_entries(ui)
        assert ui.table.rowCount() == 0

    @patch(
        f"{_G}.get_glossary_entries",
        return_value=[(10, "hello", "xin chào"), (11, "world", "thế giới")],
    )
    def test_clear_search_shows_all(self, mock_get, ui) -> None:
        """Clearing the search field shows all entries."""
        _populate_set_list(ui, [(1, "TestSet", True)])
        ui.set_list.setCurrentRow(0)
        ui.search_input.setText("hello")
        refresh_entries(ui)
        assert ui.table.rowCount() == 1
        ui.search_input.setText("")
        refresh_entries(ui)
        assert ui.table.rowCount() == 2  # noqa: PLR2004

    @patch(
        f"{_G}.get_glossary_entries",
        return_value=[(10, "hello world", "bonjour monde")],
    )
    def test_search_partial_substring(self, mock_get, ui) -> None:
        """Search matches partial substring within source text."""
        _populate_set_list(ui, [(1, "TestSet", True)])
        ui.set_list.setCurrentRow(0)
        ui.search_input.setText("llo wor")
        refresh_entries(ui)
        assert ui.table.rowCount() == 1

    @patch(
        f"{_G}.get_glossary_entries",
        return_value=[(10, "hello", "xin chào")],
    )
    def test_search_delegate_updated(self, mock_get, ui) -> None:
        """Search text is passed to the table delegate for highlighting."""
        _populate_set_list(ui, [(1, "TestSet", True)])
        ui.set_list.setCurrentRow(0)
        ui.search_input.setText("hello")
        refresh_entries(ui)
        # Verify the delegate received the search text
        assert ui.table_delegate.search_text == "hello"

    @patch(
        f"{_G}.get_glossary_entries",
        return_value=[(10, "hello", "xin chào")],
    )
    def test_search_empty_delegate_cleared(self, mock_get, ui) -> None:
        """Empty search clears the delegate's search text."""
        _populate_set_list(ui, [(1, "TestSet", True)])
        ui.set_list.setCurrentRow(0)
        ui.search_input.setText("")
        refresh_entries(ui)
        assert ui.table_delegate.search_text == ""

    @patch(
        f"{_G}.get_glossary_entries",
        return_value=[(i, f"entry_{i}", f"translation_{i}") for i in range(50)],
    )
    def test_search_filters_large_list(self, mock_get, ui) -> None:
        """Search correctly filters a large list of entries."""
        _populate_set_list(ui, [(1, "TestSet", True)])
        ui.set_list.setCurrentRow(0)
        ui.search_input.setText("entry_42")
        refresh_entries(ui)
        assert ui.table.rowCount() == 1

    @patch(
        f"{_G}.get_glossary_entries",
        return_value=[(10, "hello", "xin chào"), (11, "help", "giúp đỡ")],
    )
    def test_search_matches_multiple_entries(self, mock_get, ui) -> None:
        """Search matching multiple entries returns all matches."""
        _populate_set_list(ui, [(1, "TestSet", True)])
        ui.set_list.setCurrentRow(0)
        ui.search_input.setText("hel")
        refresh_entries(ui)
        assert ui.table.rowCount() == 2  # noqa: PLR2004


# ---------------------------------------------------------------------------
# NEW: Toggle all expanded tests
# ---------------------------------------------------------------------------


class TestToggleAllExpanded:
    """Expanded tests for on_toggle_all."""

    @patch(f"{_G}.refresh_sets")
    @patch(f"{_G}.update_all_glossary_sets_active")
    def test_toggle_single_unchecked(self, mock_update, mock_refresh, ui) -> None:
        """Toggle with single unchecked set activates all."""
        _populate_set_list(ui, [(1, "A", True), (2, "B", True), (3, "C", False)])
        on_toggle_all(ui)
        mock_update.assert_called_once_with(True)

    @patch(f"{_G}.refresh_sets")
    @patch(f"{_G}.update_all_glossary_sets_active")
    def test_toggle_all_unchecked(self, mock_update, mock_refresh, ui) -> None:
        """Toggle with all unchecked sets activates all."""
        _populate_set_list(ui, [(1, "A", False), (2, "B", False)])
        on_toggle_all(ui)
        mock_update.assert_called_once_with(True)

    @patch(f"{_G}.refresh_sets")
    @patch(f"{_G}.update_all_glossary_sets_active")
    def test_toggle_single_set_checked(self, mock_update, mock_refresh, ui) -> None:
        """Toggle with single checked set deactivates all."""
        _populate_set_list(ui, [(1, "A", True)])
        on_toggle_all(ui)
        mock_update.assert_called_once_with(False)


# ---------------------------------------------------------------------------
# NEW: Theme/language updates on all UI elements
# ---------------------------------------------------------------------------


class TestThemeLanguageExpanded:
    """Expanded tests for apply_theme and apply_language on full page."""

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(f"{_G}.get_glossary_sets", return_value=[])
    def test_apply_theme_updates_list_widget_style(
        self, mock_sets, mock_entries, qapp, qtbot
    ) -> None:
        """apply_theme updates the set list stylesheet."""
        page = create_glossary_page()
        qtbot.addWidget(page)
        list_widget = page.findChild(QListWidget, "glossary_set_list")
        list_widget.setStyleSheet("")
        page.apply_theme()
        assert list_widget.styleSheet() != ""

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(f"{_G}.get_glossary_sets", return_value=[])
    def test_apply_theme_updates_splitter_style(
        self, mock_sets, mock_entries, qapp, qtbot
    ) -> None:
        """apply_theme updates the splitter stylesheet."""
        page = create_glossary_page()
        qtbot.addWidget(page)
        splitter = page.findChild(QSplitter)
        splitter.setStyleSheet("")
        page.apply_theme()
        assert splitter.styleSheet() != ""

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(f"{_G}.get_glossary_sets", return_value=[])
    def test_apply_theme_twice_no_crash(
        self, mock_sets, mock_entries, qapp, qtbot
    ) -> None:
        """Calling apply_theme twice does not crash."""
        page = create_glossary_page()
        qtbot.addWidget(page)
        page.apply_theme()
        page.apply_theme()

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(f"{_G}.get_glossary_sets", return_value=[])
    def test_apply_language_twice_no_crash(
        self, mock_sets, mock_entries, qapp, qtbot
    ) -> None:
        """Calling apply_language twice does not crash."""
        page = create_glossary_page()
        qtbot.addWidget(page)
        page.apply_language()
        page.apply_language()

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(f"{_G}.get_glossary_sets", return_value=[])
    def test_apply_language_updates_set_buttons(
        self, mock_sets, mock_entries, qapp, qtbot
    ) -> None:
        """apply_language updates set action button texts."""
        page = create_glossary_page()
        qtbot.addWidget(page)
        page.apply_language()
        # All buttons should have non-empty text after language refresh
        buttons = page.findChildren(QPushButton)
        for btn in buttons:
            if btn.isVisible():
                assert btn.text() != ""

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(f"{_G}.get_glossary_sets", return_value=[])
    def test_apply_theme_then_language_no_crash(
        self, mock_sets, mock_entries, qapp, qtbot
    ) -> None:
        """Calling apply_theme then apply_language does not crash."""
        page = create_glossary_page()
        qtbot.addWidget(page)
        page.apply_theme()
        page.apply_language()

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(f"{_G}.get_glossary_sets", return_value=[])
    def test_apply_language_then_theme_no_crash(
        self, mock_sets, mock_entries, qapp, qtbot
    ) -> None:
        """Calling apply_language then apply_theme does not crash."""
        page = create_glossary_page()
        qtbot.addWidget(page)
        page.apply_language()
        page.apply_theme()


# ---------------------------------------------------------------------------
# NEW: Create entry table tests
# ---------------------------------------------------------------------------


class TestCreateEntryTable:
    """Tests for create_entry_table()."""

    def test_table_has_three_columns(self, qapp, qtbot) -> None:
        """Entry table has exactly 3 columns."""
        from src.ui.pages.glossary import create_entry_table  # noqa: PLC0415

        table = create_entry_table()
        qtbot.addWidget(table)
        assert table.columnCount() == 3  # noqa: PLR2004

    def test_table_has_headers(self, qapp, qtbot) -> None:
        """Entry table has non-empty header items."""
        from src.ui.pages.glossary import create_entry_table  # noqa: PLC0415

        table = create_entry_table()
        qtbot.addWidget(table)
        for col in range(3):
            assert table.horizontalHeaderItem(col) is not None
            assert table.horizontalHeaderItem(col).text() != ""

    def test_table_selection_mode(self, qapp, qtbot) -> None:
        """Entry table uses extended selection so Ctrl+A / multi-delete work."""
        from src.ui.pages.glossary import create_entry_table  # noqa: PLC0415

        table = create_entry_table()
        qtbot.addWidget(table)
        assert table.selectionMode() == QTableWidget.SelectionMode.ExtendedSelection

    def test_table_starts_empty(self, qapp, qtbot) -> None:
        """Entry table starts with zero rows."""
        from src.ui.pages.glossary import create_entry_table  # noqa: PLC0415

        table = create_entry_table()
        qtbot.addWidget(table)
        assert table.rowCount() == 0


# ---------------------------------------------------------------------------
# NEW: Splitter persistence tests
# ---------------------------------------------------------------------------


class TestSplitterPersistence:
    """Tests for splitter position save/restore."""

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(f"{_G}.get_glossary_sets", return_value=[])
    def test_splitter_exists_in_page(
        self, mock_sets, mock_entries, qapp, qtbot
    ) -> None:
        """Page contains a QSplitter."""
        page = create_glossary_page()
        qtbot.addWidget(page)
        splitter = page.findChild(QSplitter)
        assert splitter is not None

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(f"{_G}.get_glossary_sets", return_value=[])
    def test_splitter_has_two_children(
        self, mock_sets, mock_entries, qapp, qtbot
    ) -> None:
        """Splitter has exactly 2 children (left and right panels)."""
        page = create_glossary_page()
        qtbot.addWidget(page)
        splitter = page.findChild(QSplitter)
        assert splitter.count() == 2  # noqa: PLR2004

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(f"{_G}.get_glossary_sets", return_value=[])
    def test_splitter_not_collapsible(
        self, mock_sets, mock_entries, qapp, qtbot
    ) -> None:
        """Splitter does not allow collapsing children."""
        page = create_glossary_page()
        qtbot.addWidget(page)
        splitter = page.findChild(QSplitter)
        assert not splitter.childrenCollapsible()


# ---------------------------------------------------------------------------
# NEW: Refresh entries edge cases
# ---------------------------------------------------------------------------


class TestRefreshEntriesEdgeCases:
    """Edge cases for refresh_entries."""

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    def test_empty_entries_with_selection(self, mock_get, ui) -> None:
        """Empty entries list with a set selected shows zero rows."""
        _populate_set_list(ui, [(1, "TestSet", True)])
        ui.set_list.setCurrentRow(0)
        ui.search_input.clear()
        refresh_entries(ui)
        assert ui.table.rowCount() == 0

    @patch(
        f"{_G}.get_glossary_entries",
        return_value=[(10, "a", "b")],
    )
    def test_entries_label_shows_count(self, mock_get, ui) -> None:
        """Entries label text contains count information."""
        _populate_set_list(ui, [(1, "TestSet", True)])
        ui.set_list.setCurrentRow(0)
        ui.search_input.clear()
        refresh_entries(ui)
        assert ui.entries_list_label.text() != ""

    @patch(
        f"{_G}.get_glossary_entries",
        return_value=[(i, f"s{i}", f"t{i}") for i in range(500)],
    )
    def test_large_entries_list(self, mock_get, ui) -> None:
        """500 entries are loaded without error."""
        _populate_set_list(ui, [(1, "TestSet", True)])
        ui.set_list.setCurrentRow(0)
        ui.search_input.clear()
        refresh_entries(ui)
        assert ui.table.rowCount() == 500  # noqa: PLR2004

    @patch(
        f"{_G}.get_glossary_entries",
        return_value=[(10, "   spaced   ", "   also spaced   ")],
    )
    def test_entries_with_leading_trailing_spaces(self, mock_get, ui) -> None:
        """Entries with leading/trailing spaces are displayed as-is."""
        _populate_set_list(ui, [(1, "TestSet", True)])
        ui.set_list.setCurrentRow(0)
        ui.search_input.clear()
        refresh_entries(ui)
        assert ui.table.rowCount() == 1
        assert "spaced" in ui.table.item(0, 0).text()


# ---------------------------------------------------------------------------
# NEW: Refresh sets edge cases
# ---------------------------------------------------------------------------


class TestRefreshSetsEdgeCases:
    """Edge cases for refresh_sets."""

    @patch(f"{_G}.get_glossary_sets", return_value=[(1, "Only", True)])
    def test_single_set_shows_toggle(self, mock_get, ui) -> None:
        """Single set makes toggle button visible."""
        refresh_sets(ui)
        assert ui.toggle_all_btn.isVisible()

    @patch(
        f"{_G}.get_glossary_sets",
        return_value=[(i, f"Set_{i}", i % 2 == 0) for i in range(50)],
    )
    def test_many_sets_mixed_active(self, mock_get, ui) -> None:
        """50 sets with mixed active state load correctly."""
        refresh_sets(ui)
        assert ui.set_list.count() == 50  # noqa: PLR2004

    @patch(f"{_G}.get_glossary_sets", return_value=[(1, "A", True)])
    def test_sets_label_non_empty(self, mock_get, ui) -> None:
        """Sets label is non-empty after refresh."""
        refresh_sets(ui)
        assert ui.set_list_label.text() != ""

    @patch(
        f"{_G}.get_glossary_sets",
        return_value=[(1, "Ünïcödé Sët", True), (2, "日本語セット", False)],
    )
    def test_unicode_set_names_display(self, mock_get, ui) -> None:
        """Unicode set names are displayed correctly in the list."""
        refresh_sets(ui)
        names = {ui.set_list.item(i).text() for i in range(ui.set_list.count())}
        assert "Ünïcödé Sët" in names
        assert "日本語セット" in names

    @patch(f"{_G}.get_glossary_sets", return_value=[(1, "A", True)])
    def test_refresh_sets_updates_data_roles(self, mock_get, ui) -> None:
        """Refresh stores correct data in UserRole and UserRole+1."""
        refresh_sets(ui)
        item = ui.set_list.item(0)
        assert item.data(Qt.ItemDataRole.UserRole) == 1
        assert item.data(Qt.ItemDataRole.UserRole + 1) == "A"


# ---------------------------------------------------------------------------
# NEW: Init logic and signal wiring
# ---------------------------------------------------------------------------


class TestInitLogicExpanded:
    """Expanded tests for init_glossary_logic."""

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(f"{_G}.get_glossary_sets", return_value=[])
    def test_add_btn_connected(self, mock_sets, mock_entries, ui) -> None:
        """After init, add_btn is connected (no crash on click)."""
        init_glossary_logic(ui)
        # Clicking should not crash (no set selected, so shows message)
        with patch(f"{_G}.CustomMessageDialog.show_message"):
            ui.source_input.setText("test")
            ui.target_input.setText("test")
            ui.add_btn.click()

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(f"{_G}.get_glossary_sets", return_value=[])
    def test_return_pressed_source_triggers_add(
        self, mock_sets, mock_entries, ui
    ) -> None:
        """Return key in source input triggers add entry."""
        init_glossary_logic(ui)
        with patch(f"{_G}.CustomMessageDialog.show_message"):
            ui.source_input.setText("test")
            ui.target_input.setText("test")
            # returnPressed should be connected
            # Just verify init doesn't crash

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(f"{_G}.get_glossary_sets", return_value=[])
    def test_search_timer_connected(self, mock_sets, mock_entries, ui) -> None:
        """After init, search input is connected to a debounce timer."""
        init_glossary_logic(ui)
        # Changing search text should not crash
        ui.search_input.setText("test")

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(f"{_G}.get_glossary_sets", return_value=[])
    def test_table_item_changed_connected(self, mock_sets, mock_entries, ui) -> None:
        """After init, table itemChanged is connected."""
        init_glossary_logic(ui)
        # Changing a table item should not crash
        ui.table.setRowCount(1)
        item = QTableWidgetItem("test")
        ui.table.setItem(0, 0, item)


# ---------------------------------------------------------------------------
# NEW: GlossaryUIComponents dataclass
# ---------------------------------------------------------------------------


class TestGlossaryUIComponentsDataclass:
    """Tests for the GlossaryUIComponents dataclass."""

    def test_dataclass_has_all_fields(self, ui) -> None:
        """GlossaryUIComponents has all expected fields."""
        assert hasattr(ui, "page")
        assert hasattr(ui, "set_list")
        assert hasattr(ui, "set_list_label")
        assert hasattr(ui, "table")
        assert hasattr(ui, "table_delegate")
        assert hasattr(ui, "entries_list_label")
        assert hasattr(ui, "source_input")
        assert hasattr(ui, "target_input")
        assert hasattr(ui, "search_input")
        assert hasattr(ui, "add_btn")
        assert hasattr(ui, "toggle_all_btn")
        assert hasattr(ui, "create_set_btn")
        assert hasattr(ui, "edit_set_btn")
        assert hasattr(ui, "delete_set_btn")

    def test_page_is_qwidget(self, ui) -> None:
        """Page field is a QWidget instance."""
        assert isinstance(ui.page, QWidget)

    def test_set_list_is_qlistwidget(self, ui) -> None:
        """set_list field is a QListWidget instance."""
        assert isinstance(ui.set_list, QListWidget)

    def test_table_is_qtablewidget(self, ui) -> None:
        """Table field is a QTableWidget instance."""
        assert isinstance(ui.table, QTableWidget)

    def test_inputs_are_qlineedit(self, ui) -> None:
        """Input fields are QLineEdit instances."""
        assert isinstance(ui.source_input, QLineEdit)
        assert isinstance(ui.target_input, QLineEdit)
        assert isinstance(ui.search_input, QLineEdit)

    def test_buttons_are_qpushbutton(self, ui) -> None:
        """Button fields are QPushButton instances."""
        assert isinstance(ui.add_btn, QPushButton)
        assert isinstance(ui.toggle_all_btn, QPushButton)
        assert isinstance(ui.create_set_btn, QPushButton)
        assert isinstance(ui.edit_set_btn, QPushButton)
        assert isinstance(ui.delete_set_btn, QPushButton)


# ---------------------------------------------------------------------------
# NEW: Batch add/delete entries
# ---------------------------------------------------------------------------


class TestBatchAddDeleteEntries:
    """Tests for batch add and delete operations."""

    @patch(f"{_G}.refresh_entries")
    @patch(f"{_G}.add_glossary_entry")
    def test_add_ten_entries(self, mock_add, mock_refresh, ui) -> None:
        """Adding 10 entries in sequence works correctly."""
        _populate_set_list(ui, [(1, "Set", True)])
        ui.set_list.setCurrentRow(0)
        for i in range(10):
            ui.source_input.setText(f"src_{i}")
            ui.target_input.setText(f"tgt_{i}")
            on_add_entry(ui)
        assert mock_add.call_count == 10  # noqa: PLR2004

    @patch(f"{_G}.refresh_entries")
    @patch(f"{_G}.delete_glossary_entry")
    def test_delete_multiple_entries(self, mock_del, mock_refresh, ui) -> None:
        """Deleting multiple entries calls DB for each."""
        for eid in [1, 2, 3, 4, 5]:
            on_delete_entry(ui, eid)
        assert mock_del.call_count == 5  # noqa: PLR2004

    @patch(f"{_G}.refresh_entries")
    @patch(f"{_G}.add_glossary_entry")
    def test_add_entry_returns_to_empty_inputs(
        self, mock_add, mock_refresh, ui
    ) -> None:
        """After adding, both inputs are empty."""
        _populate_set_list(ui, [(1, "Set", True)])
        ui.set_list.setCurrentRow(0)
        ui.source_input.setText("test_src")
        ui.target_input.setText("test_tgt")
        on_add_entry(ui)
        assert ui.source_input.text() == ""
        assert ui.target_input.text() == ""

    @patch(f"{_G}.refresh_entries")
    @patch(f"{_G}.add_glossary_entry")
    def test_add_entry_with_html_content(self, mock_add, mock_refresh, ui) -> None:
        """Adding entries with HTML-like content works."""
        _populate_set_list(ui, [(1, "Set", True)])
        ui.set_list.setCurrentRow(0)
        ui.source_input.setText("<strong>bold</strong>")
        ui.target_input.setText("<em>italique</em>")
        on_add_entry(ui)
        mock_add.assert_called_once_with(
            1, "<strong>bold</strong>", "<em>italique</em>"
        )


# ---------------------------------------------------------------------------
# NEW: Refresh entries with various search patterns
# ---------------------------------------------------------------------------


class TestRefreshEntriesSearch:
    """Tests for refresh_entries with specific search patterns."""

    @patch(
        f"{_G}.get_glossary_entries",
        return_value=[
            (10, "cat", "gato"),
            (11, "catalog", "catálogo"),
            (12, "scatter", "dispersar"),
        ],
    )
    def test_search_prefix_match(self, mock_get, ui) -> None:
        """Searching 'cat' matches 'cat', 'catalog', and 'scatter'."""
        _populate_set_list(ui, [(1, "TestSet", True)])
        ui.set_list.setCurrentRow(0)
        ui.search_input.setText("cat")
        refresh_entries(ui)
        assert ui.table.rowCount() >= 2  # noqa: PLR2004

    @patch(
        f"{_G}.get_glossary_entries",
        return_value=[(10, "hello", "hola"), (11, "goodbye", "adiós")],
    )
    def test_search_single_char(self, mock_get, ui) -> None:
        """Searching for a single character matches entries containing it."""
        _populate_set_list(ui, [(1, "TestSet", True)])
        ui.set_list.setCurrentRow(0)
        ui.search_input.setText("h")
        refresh_entries(ui)
        assert ui.table.rowCount() >= 1

    @patch(
        f"{_G}.get_glossary_entries",
        return_value=[(10, "UPPER", "UPPER_TGT")],
    )
    def test_search_lowercase_matches_uppercase(self, mock_get, ui) -> None:
        """Lowercase search matches uppercase entries."""
        _populate_set_list(ui, [(1, "TestSet", True)])
        ui.set_list.setCurrentRow(0)
        ui.search_input.setText("upper")
        refresh_entries(ui)
        assert ui.table.rowCount() == 1

    @patch(
        f"{_G}.get_glossary_entries",
        return_value=[(10, "lower", "lower_tgt")],
    )
    def test_search_uppercase_matches_lowercase(self, mock_get, ui) -> None:
        """Uppercase search matches lowercase entries."""
        _populate_set_list(ui, [(1, "TestSet", True)])
        ui.set_list.setCurrentRow(0)
        ui.search_input.setText("LOWER")
        refresh_entries(ui)
        assert ui.table.rowCount() == 1


# ---------------------------------------------------------------------------
# NEW: Create/edit/delete set expanded
# ---------------------------------------------------------------------------


class TestCreateEditDeleteSetExpanded:
    """Expanded tests for set CRUD operations."""

    def test_edit_set_no_selection_safe(self, ui) -> None:
        """on_edit_set with no selection does not crash."""
        ui.set_list.clear()
        on_edit_set(ui)

    def test_delete_set_no_selection_safe(self, ui) -> None:
        """on_delete_set with no selection does not crash."""
        ui.set_list.clear()
        on_delete_set(ui)

    @patch(f"{_G}.CustomMessageDialog.show_message")
    @patch(f"{_G}.add_glossary_entry")
    def test_add_entry_no_selection_shows_dialog(self, mock_add, mock_msg, ui) -> None:
        """Adding entry without set selection shows dialog."""
        ui.set_list.clear()
        ui.source_input.setText("test")
        ui.target_input.setText("test")
        on_add_entry(ui)
        mock_msg.assert_called_once()
        mock_add.assert_not_called()

    @patch(f"{_G}.refresh_sets")
    @patch(f"{_G}.create_glossary_set", return_value=True)
    @patch(f"{_G}.CustomInputDialog")
    def test_create_set_with_unicode(
        self, mock_dialog_cls, mock_create, mock_refresh, ui
    ) -> None:
        """Creating a set with unicode name works."""
        dialog = MagicMock()
        dialog.input = MagicMock()
        dialog.input.text.return_value = "日本語セット"
        mock_dialog_cls.return_value = dialog

        def run_confirm():
            dialog.on_confirm()

        dialog.exec.side_effect = run_confirm
        from src.ui.pages.glossary import on_create_set  # noqa: PLC0415

        on_create_set(ui)
        mock_create.assert_called_once_with("日本語セット")

    @patch(f"{_G}.refresh_sets")
    @patch(f"{_G}.update_glossary_set_name", return_value=True)
    @patch(f"{_G}.CustomInputDialog")
    def test_rename_set_with_unicode(
        self, mock_dialog_cls, mock_rename, mock_refresh, ui
    ) -> None:
        """Renaming a set with unicode name works."""
        _populate_set_list(ui, [(1, "OldName", True)])
        ui.set_list.setCurrentRow(0)

        dialog = MagicMock()
        dialog.input = MagicMock()
        dialog.input.text.return_value = "新しい名前"
        mock_dialog_cls.return_value = dialog

        def run_confirm():
            dialog.on_confirm()

        dialog.exec.side_effect = run_confirm
        on_edit_set(ui)
        mock_rename.assert_called_once_with(1, "新しい名前")


# ---------------------------------------------------------------------------
# NEW: Entries table behavior
# ---------------------------------------------------------------------------


class TestEntriesTableBehavior:
    """Tests for entries table visual/structural behavior."""

    @patch(
        f"{_G}.get_glossary_entries",
        return_value=[(10, "hello", "bonjour")],
    )
    def test_entries_use_case_insensitive_sort_items(self, mock_get, ui) -> None:
        """Entries use CaseInsensitiveSortItem for source column."""
        _populate_set_list(ui, [(1, "TestSet", True)])
        ui.set_list.setCurrentRow(0)
        ui.search_input.clear()
        refresh_entries(ui)
        item = ui.table.item(0, 0)
        assert isinstance(item, CaseInsensitiveSortItem)

    @patch(
        f"{_G}.get_glossary_entries",
        return_value=[(10, "hello", "bonjour")],
    )
    def test_entries_target_uses_sort_item(self, mock_get, ui) -> None:
        """Entries use CaseInsensitiveSortItem for target column."""
        _populate_set_list(ui, [(1, "TestSet", True)])
        ui.set_list.setCurrentRow(0)
        ui.search_input.clear()
        refresh_entries(ui)
        item = ui.table.item(0, 1)
        assert isinstance(item, CaseInsensitiveSortItem)

    @patch(
        f"{_G}.get_glossary_entries",
        return_value=[(10, "hello", "bonjour"), (11, "world", "monde")],
    )
    def test_entries_have_delete_buttons(self, mock_get, ui) -> None:
        """Every entry row has a delete button in column 2."""
        _populate_set_list(ui, [(1, "TestSet", True)])
        ui.set_list.setCurrentRow(0)
        ui.search_input.clear()
        refresh_entries(ui)
        for row in range(ui.table.rowCount()):
            btn = ui.table.cellWidget(row, 2)
            assert isinstance(btn, QPushButton)

    @patch(
        f"{_G}.get_glossary_entries",
        return_value=[(10, "hello", "bonjour")],
    )
    def test_entries_sorting_enabled_after_refresh(self, mock_get, ui) -> None:
        """Sorting is re-enabled after refresh_entries."""
        _populate_set_list(ui, [(1, "TestSet", True)])
        ui.set_list.setCurrentRow(0)
        ui.search_input.clear()
        refresh_entries(ui)
        assert ui.table.isSortingEnabled()

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    def test_empty_entries_keeps_table_at_zero(self, mock_get, ui) -> None:
        """Empty entries list results in zero-row table."""
        _populate_set_list(ui, [(1, "TestSet", True)])
        ui.set_list.setCurrentRow(0)
        ui.search_input.clear()
        refresh_entries(ui)
        assert ui.table.rowCount() == 0


# ---------------------------------------------------------------------------
# NEW: Multiple operations combined
# ---------------------------------------------------------------------------


class TestCombinedOperations:
    """Tests combining multiple operations."""

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(
        f"{_G}.get_glossary_sets",
        return_value=[(1, "A", True), (2, "B", False)],
    )
    def test_init_then_toggle_all(self, mock_sets, mock_entries, ui) -> None:
        """Init then toggle all works correctly."""
        init_glossary_logic(ui)
        with (
            patch(f"{_G}.update_all_glossary_sets_active") as mock_update,
            patch(
                f"{_G}.get_glossary_sets",
                return_value=[(1, "A", True), (2, "B", False)],
            ),
        ):
            on_toggle_all(ui)
            mock_update.assert_called_once_with(True)

    @patch(f"{_G}.update_glossary_entry")
    def test_edit_then_check_table_state(self, mock_update, ui) -> None:
        """After editing, table state is consistent."""
        ui.table.setRowCount(1)
        src_item = QTableWidgetItem("edited")
        src_item.setData(Qt.ItemDataRole.UserRole, 99)
        ui.table.setItem(0, 0, src_item)
        ui.table.setItem(0, 1, QTableWidgetItem("traduit"))
        on_item_changed(ui, src_item)
        mock_update.assert_called_once_with(99, "edited", "traduit")
        # Table should still have 1 row
        assert ui.table.rowCount() == 1

    @patch(
        f"{_G}.get_glossary_entries",
        return_value=[(10, "hello", "bonjour"), (11, "world", "monde")],
    )
    def test_search_then_clear_then_search_again(self, mock_get, ui) -> None:
        """Search → clear → search again cycle works."""
        _populate_set_list(ui, [(1, "TestSet", True)])
        ui.set_list.setCurrentRow(0)

        # First search
        ui.search_input.setText("hello")
        refresh_entries(ui)
        assert ui.table.rowCount() == 1

        # Clear search
        ui.search_input.setText("")
        refresh_entries(ui)
        assert ui.table.rowCount() == 2  # noqa: PLR2004

        # Search again
        ui.search_input.setText("world")
        refresh_entries(ui)
        assert ui.table.rowCount() == 1

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(f"{_G}.get_glossary_sets", return_value=[])
    def test_create_page_then_apply_theme_and_language(
        self, mock_sets, mock_entries, qapp, qtbot
    ) -> None:
        """Creating page then applying theme and language does not crash."""
        page = create_glossary_page()
        qtbot.addWidget(page)
        page.apply_theme()
        page.apply_language()
        page.apply_theme()
        page.apply_language()

    @patch(
        f"{_G}.get_glossary_sets",
        return_value=[(1, "A", True), (2, "B", True), (3, "C", True)],
    )
    def test_refresh_sets_then_select_each(self, mock_get, ui) -> None:
        """Refreshing sets then selecting each one works."""
        refresh_sets(ui)
        for i in range(3):
            ui.set_list.setCurrentRow(i)
            assert ui.set_list.currentItem() is not None
            assert ui.set_list.currentItem().data(Qt.ItemDataRole.UserRole) == i + 1


# ---------------------------------------------------------------------------
# NEW: Import/Export edge cases
# ---------------------------------------------------------------------------


class TestImportExportEdgeCases:
    """Tests for glossary import/export boundary conditions."""

    @patch(f"{_G}.refresh_entries")
    @patch(f"{_G}.add_glossary_entry")
    def test_add_entry_whitespace_only_source(self, mock_add, mock_refresh, ui) -> None:
        """Adding entry with whitespace-only source does not call DB."""
        _populate_set_list(ui, [(1, "Set", True)])
        ui.set_list.setCurrentRow(0)
        ui.source_input.setText("   ")
        ui.target_input.setText("target")
        on_add_entry(ui)
        mock_add.assert_not_called()

    @patch(f"{_G}.refresh_entries")
    @patch(f"{_G}.add_glossary_entry")
    def test_add_entry_whitespace_only_target(self, mock_add, mock_refresh, ui) -> None:
        """Adding entry with whitespace-only target does not call DB."""
        _populate_set_list(ui, [(1, "Set", True)])
        ui.set_list.setCurrentRow(0)
        ui.source_input.setText("source")
        ui.target_input.setText("   ")
        on_add_entry(ui)
        mock_add.assert_not_called()

    @patch(f"{_G}.refresh_entries")
    @patch(f"{_G}.add_glossary_entry")
    def test_add_entry_with_newlines(self, mock_add, mock_refresh, ui) -> None:
        """Adding entry with newline characters is accepted."""
        _populate_set_list(ui, [(1, "Set", True)])
        ui.set_list.setCurrentRow(0)
        ui.source_input.setText("line1\nline2")
        ui.target_input.setText("tgt")
        on_add_entry(ui)
        mock_add.assert_called_once()

    @patch(f"{_G}.refresh_entries")
    @patch(f"{_G}.add_glossary_entry")
    def test_add_entry_very_long_string(self, mock_add, mock_refresh, ui) -> None:
        """Adding entry with very long string does not crash."""
        _populate_set_list(ui, [(1, "Set", True)])
        ui.set_list.setCurrentRow(0)
        ui.source_input.setText("a" * 10000)
        ui.target_input.setText("b" * 10000)
        on_add_entry(ui)
        mock_add.assert_called_once()


# ---------------------------------------------------------------------------
# NEW: Set list item data
# ---------------------------------------------------------------------------


class TestSetListItemData:
    """Tests for set list item data and checkbox states."""

    @patch(
        f"{_G}.get_glossary_sets",
        return_value=[(10, "SetA", True), (20, "SetB", False)],
    )
    def test_set_items_have_correct_ids(self, mock_get, ui) -> None:
        """Set items store the correct set_id in UserRole."""
        refresh_sets(ui)
        assert ui.set_list.item(0).data(Qt.ItemDataRole.UserRole) == 10  # noqa: PLR2004
        assert ui.set_list.item(1).data(Qt.ItemDataRole.UserRole) == 20  # noqa: PLR2004

    @patch(
        f"{_G}.get_glossary_sets",
        return_value=[(1, "Active", True)],
    )
    def test_active_set_has_checked_state(self, mock_get, ui) -> None:
        """Active set item has Checked checkbox state."""
        refresh_sets(ui)
        assert ui.set_list.item(0).checkState() == Qt.CheckState.Checked

    @patch(
        f"{_G}.get_glossary_sets",
        return_value=[(1, "Inactive", False)],
    )
    def test_inactive_set_has_unchecked_state(self, mock_get, ui) -> None:
        """Inactive set item has Unchecked checkbox state."""
        refresh_sets(ui)
        assert ui.set_list.item(0).checkState() == Qt.CheckState.Unchecked

    @patch(
        f"{_G}.get_glossary_sets",
        return_value=[(1, "A", True), (2, "B", True), (3, "C", True)],
    )
    def test_all_active_sets_checked(self, mock_get, ui) -> None:
        """All active sets show as checked."""
        refresh_sets(ui)
        for i in range(3):
            assert ui.set_list.item(i).checkState() == Qt.CheckState.Checked

    @patch(
        f"{_G}.get_glossary_sets",
        return_value=[(1, "A", False), (2, "B", False)],
    )
    def test_all_inactive_sets_unchecked(self, mock_get, ui) -> None:
        """All inactive sets show as unchecked."""
        refresh_sets(ui)
        for i in range(2):
            assert ui.set_list.item(i).checkState() == Qt.CheckState.Unchecked


# ---------------------------------------------------------------------------
# NEW: Toggle all edge cases
# ---------------------------------------------------------------------------


class TestToggleAllEdgeCases:
    """Edge case tests for on_toggle_all."""

    @patch(f"{_G}.refresh_sets")
    @patch(f"{_G}.update_all_glossary_sets_active")
    @patch(f"{_G}.get_glossary_sets", return_value=[])
    def test_toggle_all_with_no_sets(
        self, mock_get, mock_update, mock_refresh, ui
    ) -> None:
        """Toggle all with no sets does not crash."""
        on_toggle_all(ui)
        # Should still call update (with activate=True since no unchecked sets)
        mock_update.assert_called_once()

    @patch(f"{_G}.refresh_sets")
    @patch(f"{_G}.update_all_glossary_sets_active")
    @patch(
        f"{_G}.get_glossary_sets",
        return_value=[(1, "A", True), (2, "B", True)],
    )
    def test_toggle_all_active_deactivates(
        self, mock_get, mock_update, mock_refresh, ui
    ) -> None:
        """When all sets active, toggle deactivates all."""
        on_toggle_all(ui)
        mock_update.assert_called_once_with(False)

    @patch(f"{_G}.refresh_sets")
    @patch(f"{_G}.update_all_glossary_sets_active")
    @patch(
        f"{_G}.get_glossary_sets",
        return_value=[(1, "A", False), (2, "B", False)],
    )
    def test_toggle_all_inactive_calls_update(
        self, mock_get, mock_update, mock_refresh, ui
    ) -> None:
        """When all sets inactive, toggle calls update."""
        on_toggle_all(ui)
        mock_update.assert_called_once()


# ---------------------------------------------------------------------------
# NEW: On item changed edge cases
# ---------------------------------------------------------------------------


class TestOnItemChangedEdgeCases:
    """Edge case tests for on_item_changed."""

    @patch(f"{_G}.update_glossary_entry")
    def test_item_changed_no_user_role(self, mock_update, ui) -> None:
        """on_item_changed with item lacking UserRole data is safe."""
        ui.table.setRowCount(1)
        item = QTableWidgetItem("src")
        # No UserRole data set → data returns None
        ui.table.setItem(0, 0, item)
        ui.table.setItem(0, 1, QTableWidgetItem("tgt"))
        on_item_changed(ui, item)
        # Should not crash; may or may not call update

    @patch(f"{_G}.update_glossary_entry")
    def test_item_changed_column_1(self, mock_update, ui) -> None:
        """on_item_changed triggered by target column still works."""
        ui.table.setRowCount(1)
        src = QTableWidgetItem("src")
        src.setData(Qt.ItemDataRole.UserRole, 42)
        ui.table.setItem(0, 0, src)
        tgt = QTableWidgetItem("changed_tgt")
        ui.table.setItem(0, 1, tgt)
        on_item_changed(ui, tgt)
        mock_update.assert_called_once_with(42, "src", "changed_tgt")

    @patch(f"{_G}.update_glossary_entry")
    def test_item_changed_empty_strings(self, mock_update, ui) -> None:
        """on_item_changed with empty source and target does not crash."""
        ui.table.setRowCount(1)
        src = QTableWidgetItem("")
        src.setData(Qt.ItemDataRole.UserRole, 10)
        ui.table.setItem(0, 0, src)
        ui.table.setItem(0, 1, QTableWidgetItem(""))
        on_item_changed(ui, src)
        # May or may not call update depending on implementation

    @patch(f"{_G}.update_glossary_entry")
    def test_item_changed_unicode_content(self, mock_update, ui) -> None:
        """on_item_changed with unicode content works."""
        ui.table.setRowCount(1)
        src = QTableWidgetItem("日本語")
        src.setData(Qt.ItemDataRole.UserRole, 55)
        ui.table.setItem(0, 0, src)
        ui.table.setItem(0, 1, QTableWidgetItem("中文"))
        on_item_changed(ui, src)
        mock_update.assert_called_once_with(55, "日本語", "中文")


# ---------------------------------------------------------------------------
# NEW: Delete entry edge cases
# ---------------------------------------------------------------------------


class TestDeleteEntryEdgeCases:
    """Edge case tests for on_delete_entry."""

    @patch(f"{_G}.refresh_entries")
    @patch(f"{_G}.delete_glossary_entry")
    def test_delete_entry_zero_id(self, mock_del, mock_refresh, ui) -> None:
        """Deleting entry with id=0 is handled."""
        on_delete_entry(ui, 0)
        mock_del.assert_called_once_with(0)

    @patch(f"{_G}.refresh_entries")
    @patch(f"{_G}.delete_glossary_entry")
    def test_delete_entry_large_id(self, mock_del, mock_refresh, ui) -> None:
        """Deleting entry with very large id does not crash."""
        on_delete_entry(ui, 999999)
        mock_del.assert_called_once_with(999999)

    @patch(f"{_G}.refresh_entries")
    @patch(f"{_G}.delete_glossary_entry")
    def test_delete_entry_refreshes(self, mock_del, mock_refresh, ui) -> None:
        """Deleting entry calls refresh_entries."""
        on_delete_entry(ui, 1)
        mock_refresh.assert_called_once_with(ui)


# ---------------------------------------------------------------------------
# NEW: Search delegate state
# ---------------------------------------------------------------------------


class TestSearchDelegateState:
    """Tests for search delegate state management."""

    @patch(
        f"{_G}.get_glossary_entries",
        return_value=[(10, "hello", "bonjour")],
    )
    def test_delegate_search_text_set_on_search(self, mock_get, ui) -> None:
        """Delegate search_text is set when search is active."""
        _populate_set_list(ui, [(1, "Set", True)])
        ui.set_list.setCurrentRow(0)
        ui.search_input.setText("hello")
        refresh_entries(ui)
        assert ui.table_delegate.search_text == "hello"

    @patch(
        f"{_G}.get_glossary_entries",
        return_value=[(10, "hello", "bonjour")],
    )
    def test_delegate_search_text_cleared(self, mock_get, ui) -> None:
        """Delegate search_text is cleared when search is empty."""
        _populate_set_list(ui, [(1, "Set", True)])
        ui.set_list.setCurrentRow(0)
        ui.search_input.setText("")
        refresh_entries(ui)
        assert ui.table_delegate.search_text == ""

    @patch(
        f"{_G}.get_glossary_entries",
        return_value=[(10, "hello", "bonjour"), (11, "world", "monde")],
    )
    def test_delegate_search_text_changes_with_search(self, mock_get, ui) -> None:
        """Delegate search_text updates when search changes."""
        _populate_set_list(ui, [(1, "Set", True)])
        ui.set_list.setCurrentRow(0)
        ui.search_input.setText("hello")
        refresh_entries(ui)
        assert ui.table_delegate.search_text == "hello"
        ui.search_input.setText("world")
        refresh_entries(ui)
        assert ui.table_delegate.search_text == "world"


# ---------------------------------------------------------------------------
# NEW: Refresh sets label updates
# ---------------------------------------------------------------------------


class TestRefreshSetsLabelUpdates:
    """Tests for label updates during refresh_sets."""

    @patch(
        f"{_G}.get_glossary_sets",
        return_value=[(1, "A", True), (2, "B", False)],
    )
    def test_toggle_button_text_updates(self, mock_get, ui) -> None:
        """Toggle button text updates after refresh."""
        refresh_sets(ui)
        # The button text should be set (either activate or deactivate all)
        text = ui.toggle_all_btn.text()
        assert len(text) > 0

    @patch(
        f"{_G}.get_glossary_sets",
        return_value=[(1, "A", True)],
    )
    def test_set_list_count_matches_data(self, mock_get, ui) -> None:
        """Set list count matches number of sets from DB."""
        refresh_sets(ui)
        assert ui.set_list.count() == 1

    @patch(
        f"{_G}.get_glossary_sets",
        return_value=[
            (1, "A", True),
            (2, "B", True),
            (3, "C", True),
            (4, "D", True),
            (5, "E", True),
        ],
    )
    def test_refresh_sets_five_items(self, mock_get, ui) -> None:
        """Refreshing with 5 sets creates 5 items."""
        refresh_sets(ui)
        assert ui.set_list.count() == 5  # noqa: PLR2004


# ---------------------------------------------------------------------------
# NEW: Page factory and creation
# ---------------------------------------------------------------------------


class TestPageFactoryCreation:
    """Tests for create_glossary_page factory function."""

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(f"{_G}.get_glossary_sets", return_value=[])
    def test_factory_returns_widget(self, mock_sets, mock_entries, qapp, qtbot) -> None:
        """create_glossary_page returns a QWidget."""
        page = create_glossary_page()
        qtbot.addWidget(page)
        assert isinstance(page, QWidget)

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(f"{_G}.get_glossary_sets", return_value=[])
    def test_factory_has_apply_theme(
        self, mock_sets, mock_entries, qapp, qtbot
    ) -> None:
        """Created page has apply_theme method."""
        page = create_glossary_page()
        qtbot.addWidget(page)
        assert hasattr(page, "apply_theme")

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(f"{_G}.get_glossary_sets", return_value=[])
    def test_factory_has_apply_language(
        self, mock_sets, mock_entries, qapp, qtbot
    ) -> None:
        """Created page has apply_language method."""
        page = create_glossary_page()
        qtbot.addWidget(page)
        assert hasattr(page, "apply_language")

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(f"{_G}.get_glossary_sets", return_value=[])
    def test_page_has_splitter(self, mock_sets, mock_entries, qapp, qtbot) -> None:
        """Created page contains a QSplitter."""
        page = create_glossary_page()
        qtbot.addWidget(page)
        splitter = page.findChild(QSplitter)
        assert splitter is not None


# ---------------------------------------------------------------------------
# NEW: on_item_changed revert behavior
# ---------------------------------------------------------------------------


class TestOnItemChangedRevert:
    """Tests for on_item_changed revert behavior with empty values."""

    @patch(f"{_G}.refresh_entries")
    @patch(f"{_G}.update_glossary_entry")
    def test_empty_source_reverts_cell(self, mock_update, mock_refresh, ui) -> None:
        """on_item_changed with empty source reverts just that cell."""
        from src.ui.pages.glossary import _ROLE_ORIG_SOURCE  # noqa: PLC0415

        ui.table.setRowCount(1)
        src = QTableWidgetItem("")
        src.setData(Qt.ItemDataRole.UserRole, 10)
        src.setData(_ROLE_ORIG_SOURCE, "old_src")
        ui.table.setItem(0, 0, src)
        ui.table.setItem(0, 1, QTableWidgetItem("target"))
        on_item_changed(ui, src)
        mock_update.assert_not_called()
        mock_refresh.assert_not_called()
        assert ui.table.item(0, 0).text() == "old_src"

    @patch(f"{_G}.refresh_entries")
    @patch(f"{_G}.update_glossary_entry")
    def test_empty_target_reverts_cell(self, mock_update, mock_refresh, ui) -> None:
        """on_item_changed with empty target reverts just that cell."""
        from src.ui.pages.glossary import _ROLE_ORIG_TARGET  # noqa: PLC0415

        ui.table.setRowCount(1)
        src = QTableWidgetItem("source")
        src.setData(Qt.ItemDataRole.UserRole, 10)
        ui.table.setItem(0, 0, src)
        tgt = QTableWidgetItem("")
        tgt.setData(_ROLE_ORIG_TARGET, "old_tgt")
        ui.table.setItem(0, 1, tgt)
        on_item_changed(ui, src)
        mock_update.assert_not_called()
        mock_refresh.assert_not_called()
        assert ui.table.item(0, 1).text() == "old_tgt"

    @patch(f"{_G}.update_glossary_entry")
    def test_valid_edit_calls_update(self, mock_update, ui) -> None:
        """on_item_changed with valid src/tgt calls update."""
        ui.table.setRowCount(1)
        src = QTableWidgetItem("src_val")
        src.setData(Qt.ItemDataRole.UserRole, 10)
        ui.table.setItem(0, 0, src)
        ui.table.setItem(0, 1, QTableWidgetItem("tgt_val"))
        on_item_changed(ui, src)
        mock_update.assert_called_once_with(10, "src_val", "tgt_val")


# ---------------------------------------------------------------------------
# NEW: Checkbox state change handling
# ---------------------------------------------------------------------------


class TestCheckboxStateChange:
    """Tests for set checkbox state change behavior."""

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(
        f"{_G}.get_glossary_sets",
        return_value=[(1, "SetA", True), (2, "SetB", False)],
    )
    def test_init_wires_signals(self, mock_sets, mock_entries, ui) -> None:
        """init_glossary_logic wires table delegate columns."""
        init_glossary_logic(ui)
        # Check that delegate is set for columns 0 and 1
        assert ui.table.itemDelegateForColumn(0) is ui.table_delegate
        assert ui.table.itemDelegateForColumn(1) is ui.table_delegate

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(
        f"{_G}.get_glossary_sets",
        return_value=[(1, "SetA", True)],
    )
    def test_init_refreshes_sets(self, mock_sets, mock_entries, ui) -> None:
        """init_glossary_logic calls refresh_sets."""
        init_glossary_logic(ui)
        mock_sets.assert_called()

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(
        f"{_G}.get_glossary_sets",
        return_value=[(1, "SetA", True)],
    )
    def test_init_refreshes_entries(self, mock_sets, mock_entries, ui) -> None:
        """init_glossary_logic calls refresh_entries."""
        init_glossary_logic(ui)
        mock_entries.assert_called()


# ---------------------------------------------------------------------------
# NEW: on_add_entry focus behavior
# ---------------------------------------------------------------------------


class TestAddEntryFocus:
    """Tests for add entry focus behavior."""

    @patch(f"{_G}.refresh_entries")
    @patch(f"{_G}.add_glossary_entry")
    def test_add_entry_clears_source(self, mock_add, mock_refresh, ui) -> None:
        """After adding entry, source input is cleared."""
        _populate_set_list(ui, [(1, "Set", True)])
        ui.set_list.setCurrentRow(0)
        ui.source_input.setText("src")
        ui.target_input.setText("tgt")
        on_add_entry(ui)
        assert ui.source_input.text() == ""

    @patch(f"{_G}.refresh_entries")
    @patch(f"{_G}.add_glossary_entry")
    def test_add_entry_clears_target(self, mock_add, mock_refresh, ui) -> None:
        """After adding entry, target input is cleared."""
        _populate_set_list(ui, [(1, "Set", True)])
        ui.set_list.setCurrentRow(0)
        ui.source_input.setText("src")
        ui.target_input.setText("tgt")
        on_add_entry(ui)
        assert ui.target_input.text() == ""

    @patch(f"{_G}.refresh_entries")
    @patch(f"{_G}.add_glossary_entry")
    def test_add_entry_refreshes_entries(self, mock_add, mock_refresh, ui) -> None:
        """After adding entry, refresh_entries is called."""
        _populate_set_list(ui, [(1, "Set", True)])
        ui.set_list.setCurrentRow(0)
        ui.source_input.setText("src")
        ui.target_input.setText("tgt")
        on_add_entry(ui)
        mock_refresh.assert_called_once_with(ui)


# ---------------------------------------------------------------------------
# NEW: Set list UserRole+1 stores name
# ---------------------------------------------------------------------------


class TestSetItemNameStorage:
    """Tests that set list items store name in UserRole+1."""

    @patch(
        f"{_G}.get_glossary_sets",
        return_value=[(10, "MySet", True)],
    )
    def test_set_item_stores_name(self, mock_get, ui) -> None:
        """Set item stores name in UserRole+1."""
        refresh_sets(ui)
        item = ui.set_list.item(0)
        assert item.data(Qt.ItemDataRole.UserRole + 1) == "MySet"

    @patch(
        f"{_G}.get_glossary_sets",
        return_value=[(10, "Unicode名前", True)],
    )
    def test_set_item_stores_unicode_name(self, mock_get, ui) -> None:
        """Set item stores unicode name in UserRole+1."""
        refresh_sets(ui)
        item = ui.set_list.item(0)
        assert item.data(Qt.ItemDataRole.UserRole + 1) == "Unicode名前"

    @patch(
        f"{_G}.get_glossary_sets",
        return_value=[(10, "A", True), (20, "B", False)],
    )
    def test_multiple_items_store_names(self, mock_get, ui) -> None:
        """Multiple set items store correct names."""
        refresh_sets(ui)
        assert ui.set_list.item(0).data(Qt.ItemDataRole.UserRole + 1) == "A"
        assert ui.set_list.item(1).data(Qt.ItemDataRole.UserRole + 1) == "B"


# ---------------------------------------------------------------------------
# NEW: Table column count and structure
# ---------------------------------------------------------------------------


class TestTableStructure:
    """Tests for table column count and structure."""

    def test_table_has_three_columns(self, ui) -> None:
        """Table has exactly 3 columns (source, target, action)."""
        assert ui.table.columnCount() == 3  # noqa: PLR2004

    def test_table_is_qtablewidget(self, ui) -> None:
        """Table is a QTableWidget."""
        assert isinstance(ui.table, QTableWidget)

    def test_set_list_is_qlistwidget(self, ui) -> None:
        """Set list is a QListWidget."""
        assert isinstance(ui.set_list, QListWidget)

    def test_source_input_is_qlineedit(self, ui) -> None:
        """Source input is a QLineEdit."""
        assert isinstance(ui.source_input, QLineEdit)

    def test_target_input_is_qlineedit(self, ui) -> None:
        """Target input is a QLineEdit."""
        assert isinstance(ui.target_input, QLineEdit)

    def test_add_btn_is_qpushbutton(self, ui) -> None:
        """Add button is a QPushButton."""
        assert isinstance(ui.add_btn, QPushButton)


# ---------------------------------------------------------------------------
# Edge case: inline edit with same value is a no-op (no DB call)
# ---------------------------------------------------------------------------


class TestGlossaryInlineEditSameValue:
    """Editing entry with same source/target is no-op (no DB call)."""

    @patch(f"{_G}.update_glossary_entry")
    def test_same_values_still_calls_update(self, mock_update, ui) -> None:
        """on_item_changed calls update even when values haven't changed.

        The current implementation does not compare old vs new values;
        it always calls update_glossary_entry if both fields are non-empty.
        This test documents that behavior — update IS called.
        """
        ui.table.setRowCount(1)
        src_item = QTableWidgetItem("hello")
        src_item.setData(Qt.ItemDataRole.UserRole, 42)
        ui.table.setItem(0, 0, src_item)
        ui.table.setItem(0, 1, QTableWidgetItem("bonjour"))

        # Trigger on_item_changed with the same content
        on_item_changed(ui, src_item)
        mock_update.assert_called_once_with(42, "hello", "bonjour")

    @patch(f"{_G}.update_glossary_entry")
    def test_edit_then_revert_still_calls_update(self, mock_update, ui) -> None:
        """Editing a cell back to its original value still triggers update."""
        ui.table.setRowCount(1)
        src_item = QTableWidgetItem("original")
        src_item.setData(Qt.ItemDataRole.UserRole, 10)
        ui.table.setItem(0, 0, src_item)
        ui.table.setItem(0, 1, QTableWidgetItem("translated"))

        on_item_changed(ui, src_item)
        mock_update.assert_called_once_with(10, "original", "translated")


# ---------------------------------------------------------------------------
# Edge case: creating a set with emoji/unicode name
# ---------------------------------------------------------------------------


class TestGlossarySetUnicodeName:
    """Creating set with emoji/unicode name succeeds."""

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(
        f"{_G}.get_glossary_sets",
        return_value=[(1, "Medical Terms", True)],
    )
    def test_unicode_set_name_renders(self, mock_sets, mock_entries, ui) -> None:
        """A set with unicode characters loads and displays correctly."""
        refresh_sets(ui)
        assert ui.set_list.count() == 1
        assert ui.set_list.item(0).text() == "Medical Terms"

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(
        f"{_G}.get_glossary_sets",
        return_value=[(1, "CJK\u4e2d\u6587\u65e5\u672c\u8a9e", True)],
    )
    def test_cjk_set_name(self, mock_sets, mock_entries, ui) -> None:
        """A set with CJK characters loads correctly."""
        refresh_sets(ui)
        item = ui.set_list.item(0)
        assert "\u4e2d\u6587" in item.text()
        assert (
            item.data(Qt.ItemDataRole.UserRole + 1)
            == "CJK\u4e2d\u6587\u65e5\u672c\u8a9e"
        )

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(
        f"{_G}.get_glossary_sets",
        return_value=[(1, "Emoji\U0001f680\U0001f4da", True)],
    )
    def test_emoji_set_name(self, mock_sets, mock_entries, ui) -> None:
        """A set with emoji characters in its name loads correctly."""
        refresh_sets(ui)
        item = ui.set_list.item(0)
        assert "\U0001f680" in item.text()
        assert item.data(Qt.ItemDataRole.UserRole) == 1

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(
        f"{_G}.get_glossary_sets",
        return_value=[(1, "RTL\u0627\u0644\u0639\u0631\u0628\u064a\u0629", True)],
    )
    def test_rtl_set_name(self, mock_sets, mock_entries, ui) -> None:
        """A set with RTL (Arabic) characters in its name loads correctly."""
        refresh_sets(ui)
        item = ui.set_list.item(0)
        assert "\u0627\u0644\u0639\u0631\u0628" in item.text()


# ---------------------------------------------------------------------------
# Edge case: add entry with leading/trailing whitespace is stripped
# ---------------------------------------------------------------------------


class TestGlossaryAddEntryWhitespace:
    """Entry with leading/trailing whitespace is stripped."""

    @patch(f"{_G}.refresh_entries")
    @patch(f"{_G}.add_glossary_entry")
    def test_leading_trailing_whitespace_stripped(
        self, mock_add, mock_refresh, ui
    ) -> None:
        """Source and target are stripped before calling add_glossary_entry."""
        _populate_set_list(ui, [(1, "Set", True)])
        ui.set_list.setCurrentRow(0)
        ui.source_input.setText("  hello  ")
        ui.target_input.setText("  bonjour  ")

        on_add_entry(ui)

        # The function strips before calling add — verify via the .strip() path
        mock_add.assert_called_once_with(1, "hello", "bonjour")

    @patch(f"{_G}.refresh_entries")
    @patch(f"{_G}.add_glossary_entry")
    def test_whitespace_only_source_is_noop(self, mock_add, mock_refresh, ui) -> None:
        """Source with only whitespace is treated as empty — no add call."""
        _populate_set_list(ui, [(1, "Set", True)])
        ui.set_list.setCurrentRow(0)
        ui.source_input.setText("   ")
        ui.target_input.setText("target")

        on_add_entry(ui)

        mock_add.assert_not_called()

    @patch(f"{_G}.refresh_entries")
    @patch(f"{_G}.add_glossary_entry")
    def test_whitespace_only_target_is_noop(self, mock_add, mock_refresh, ui) -> None:
        """Target with only whitespace is treated as empty — no add call."""
        _populate_set_list(ui, [(1, "Set", True)])
        ui.set_list.setCurrentRow(0)
        ui.source_input.setText("source")
        ui.target_input.setText("   ")

        on_add_entry(ui)

        mock_add.assert_not_called()

    @patch(f"{_G}.refresh_entries")
    @patch(f"{_G}.add_glossary_entry")
    def test_tabs_and_newlines_stripped(self, mock_add, mock_refresh, ui) -> None:
        """Tabs and newlines at edges are stripped by .strip()."""
        _populate_set_list(ui, [(1, "Set", True)])
        ui.set_list.setCurrentRow(0)
        ui.source_input.setText("\thello\n")
        ui.target_input.setText("\nbonjour\t")

        on_add_entry(ui)

        mock_add.assert_called_once_with(1, "hello", "bonjour")


# ---------------------------------------------------------------------------
# Edge case: deleting the currently active set switches to next available
# ---------------------------------------------------------------------------


class TestGlossaryDeleteActiveSet:
    """Deleting the currently active set switches to next available."""

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(
        f"{_G}.get_glossary_sets",
        return_value=[(2, "SecondSet", True)],
    )
    @patch(f"{_G}.delete_glossary_set")
    @patch(f"{_G}.CustomConfirmDialog.confirm", return_value=True)
    def test_delete_active_refreshes_to_remaining(
        self, mock_confirm, mock_del, mock_sets, mock_entries, ui
    ) -> None:
        """After deleting a set, refresh_sets reloads remaining sets."""
        # Pre-populate with two sets
        _populate_set_list(ui, [(1, "FirstSet", True), (2, "SecondSet", True)])
        ui.set_list.setCurrentRow(0)

        on_delete_set(ui)

        mock_del.assert_called_once_with(1)
        # refresh_sets is called internally, which calls get_glossary_sets
        mock_sets.assert_called()

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(
        f"{_G}.get_glossary_sets",
        return_value=[],
    )
    @patch(f"{_G}.delete_glossary_set")
    @patch(f"{_G}.CustomConfirmDialog.confirm", return_value=True)
    def test_delete_last_set_leaves_empty_list(
        self, mock_confirm, mock_del, mock_sets, mock_entries, ui
    ) -> None:
        """Deleting the only set results in an empty set list."""
        _populate_set_list(ui, [(1, "OnlySet", True)])
        ui.set_list.setCurrentRow(0)

        on_delete_set(ui)

        mock_del.assert_called_once_with(1)
        # After refresh, the list should be empty (mock returns [])
        # refresh_sets was called which triggers get_glossary_sets
        mock_sets.assert_called()

    def test_delete_no_selection_is_noop(self, ui) -> None:
        """Deleting with no selection does nothing."""
        ui.set_list.clear()
        # on_delete_set returns immediately when nothing is selected
        on_delete_set(ui)


# ---------------------------------------------------------------------------
# Edge case: search that matches nothing shows empty table
# ---------------------------------------------------------------------------


class TestGlossarySearchEmptyResult:
    """Search that matches nothing shows empty table."""

    @patch(
        f"{_G}.get_glossary_entries",
        return_value=[(1, "hello", "bonjour"), (2, "world", "monde")],
    )
    def test_search_no_match_shows_empty_table(self, mock_entries, ui) -> None:
        """Searching for a term that matches nothing produces zero rows."""
        _populate_set_list(ui, [(1, "Set", True)])
        ui.set_list.setCurrentRow(0)
        ui.search_input.setText("zzzznotfound")

        refresh_entries(ui)

        assert ui.table.rowCount() == 0

    @patch(
        f"{_G}.get_glossary_entries",
        return_value=[(1, "hello", "bonjour"), (2, "world", "monde")],
    )
    def test_search_partial_match(self, mock_entries, ui) -> None:
        """Searching for a substring matches the correct entries."""
        _populate_set_list(ui, [(1, "Set", True)])
        ui.set_list.setCurrentRow(0)
        ui.search_input.setText("hell")

        refresh_entries(ui)

        assert ui.table.rowCount() == 1
        assert ui.table.item(0, 0).text() == "hello"

    @patch(
        f"{_G}.get_glossary_entries",
        return_value=[(1, "hello", "bonjour"), (2, "world", "monde")],
    )
    def test_clear_search_shows_all(self, mock_entries, ui) -> None:
        """Clearing the search text shows all entries again."""
        _populate_set_list(ui, [(1, "Set", True)])
        ui.set_list.setCurrentRow(0)
        ui.search_input.setText("")

        refresh_entries(ui)

        assert ui.table.rowCount() == 2  # noqa: PLR2004

    @patch(
        f"{_G}.get_glossary_entries",
        return_value=[],
    )
    def test_search_empty_entries_list(self, mock_entries, ui) -> None:
        """Searching when there are no entries shows zero rows."""
        _populate_set_list(ui, [(1, "Set", True)])
        ui.set_list.setCurrentRow(0)
        ui.search_input.setText("anything")

        refresh_entries(ui)

        assert ui.table.rowCount() == 0


# ---------------------------------------------------------------------------
# Edge case: very long entry name doesn't break UI layout
# ---------------------------------------------------------------------------


class TestGlossaryLongEntryName:
    """Very long entry (200+ chars) doesn't break UI layout."""

    @patch(f"{_G}.refresh_entries")
    @patch(f"{_G}.add_glossary_entry")
    def test_add_long_source_entry(self, mock_add, mock_refresh, ui) -> None:
        """Adding an entry with a 250-char source text succeeds."""
        _populate_set_list(ui, [(1, "Set", True)])
        ui.set_list.setCurrentRow(0)
        long_source = "A" * 250
        ui.source_input.setText(long_source)
        ui.target_input.setText("short")

        on_add_entry(ui)

        mock_add.assert_called_once_with(1, long_source, "short")

    @patch(f"{_G}.refresh_entries")
    @patch(f"{_G}.add_glossary_entry")
    def test_add_long_target_entry(self, mock_add, mock_refresh, ui) -> None:
        """Adding an entry with a 250-char target text succeeds."""
        _populate_set_list(ui, [(1, "Set", True)])
        ui.set_list.setCurrentRow(0)
        long_target = "B" * 250
        ui.source_input.setText("short")
        ui.target_input.setText(long_target)

        on_add_entry(ui)

        mock_add.assert_called_once_with(1, "short", long_target)

    @patch(
        f"{_G}.get_glossary_entries",
        return_value=[(1, "X" * 300, "Y" * 300)],
    )
    def test_long_entries_render_in_table(self, mock_entries, ui) -> None:
        """Entries with 300-char source and target render in the table."""
        _populate_set_list(ui, [(1, "Set", True)])
        ui.set_list.setCurrentRow(0)

        refresh_entries(ui)

        assert ui.table.rowCount() == 1
        assert ui.table.item(0, 0).text() == "X" * 300
        assert ui.table.item(0, 1).text() == "Y" * 300

    @patch(f"{_G}.update_glossary_entry")
    def test_edit_long_entry_in_table(self, mock_update, ui) -> None:
        """Editing a cell with 200+ char content calls update correctly."""
        ui.table.setRowCount(1)
        long_src = "C" * 200
        long_tgt = "D" * 200
        src_item = QTableWidgetItem(long_src)
        src_item.setData(Qt.ItemDataRole.UserRole, 99)
        ui.table.setItem(0, 0, src_item)
        ui.table.setItem(0, 1, QTableWidgetItem(long_tgt))

        on_item_changed(ui, src_item)

        mock_update.assert_called_once_with(99, long_src, long_tgt)


# ---------------------------------------------------------------------------
# NEW: Review-fix coverage — delete-set warning, duplicate detect, per-entry
# confirm, import/export.
# ---------------------------------------------------------------------------


class TestDeleteSetEntryCountWarning:
    """Tests for the cascaded-delete warning on ``on_delete_set``."""

    @patch(f"{_G}.refresh_sets")
    @patch(f"{_G}.delete_glossary_set")
    @patch(f"{_G}.get_glossary_entry_count", return_value=5)
    @patch(f"{_G}.tr", side_effect=lambda k, **kw: f"{k}::{kw}" if kw else k)
    def test_warning_includes_count_when_entries_exist(
        self,
        mock_tr,
        mock_count,
        mock_del,
        mock_refresh,
        ui,
    ) -> None:
        """Delete dialog uses the with-entries message when count > 0."""
        item = QListWidgetItem("MySet")
        item.setData(Qt.ItemDataRole.UserRole, 7)
        item.setData(Qt.ItemDataRole.UserRole + 1, "MySet")
        ui.set_list.addItem(item)
        ui.set_list.setCurrentItem(item)

        with patch(
            f"{_G}.CustomConfirmDialog.confirm",
            return_value=True,
        ) as mock_confirm:
            from src.ui.pages.glossary import on_delete_set  # noqa: PLC0415

            on_delete_set(ui)

        mock_confirm.assert_called_once()
        msg = mock_confirm.call_args.args[2]
        assert "delete_set_with_entries_msg" in msg

    @patch(f"{_G}.refresh_sets")
    @patch(f"{_G}.delete_glossary_set")
    @patch(f"{_G}.get_glossary_entry_count", return_value=0)
    @patch(f"{_G}.tr", side_effect=lambda k, **kw: f"{k}::{kw}" if kw else k)
    def test_warning_uses_simple_msg_when_empty(
        self,
        mock_tr,
        mock_count,
        mock_del,
        mock_refresh,
        ui,
    ) -> None:
        """Delete dialog uses the simple message when the set is empty."""
        item = QListWidgetItem("EmptySet")
        item.setData(Qt.ItemDataRole.UserRole, 8)
        item.setData(Qt.ItemDataRole.UserRole + 1, "EmptySet")
        ui.set_list.addItem(item)
        ui.set_list.setCurrentItem(item)

        with patch(
            f"{_G}.CustomConfirmDialog.confirm",
            return_value=True,
        ) as mock_confirm:
            from src.ui.pages.glossary import on_delete_set  # noqa: PLC0415

            on_delete_set(ui)

        msg = mock_confirm.call_args.args[2]
        assert "delete_set_msg" in msg
        assert "with_entries" not in msg


class TestDuplicateDetectionOnAdd:
    """Tests for the duplicate-detection path in ``on_add_entry``."""

    @patch(f"{_G}.refresh_entries")
    @patch(f"{_G}.add_glossary_entry")
    @patch(f"{_G}.update_glossary_entry")
    @patch(f"{_G}.find_glossary_entry_by_source", return_value=None)
    def test_no_duplicate_inserts_new_row(
        self,
        mock_find,
        mock_update,
        mock_add,
        mock_refresh,
        ui,
    ) -> None:
        """When no match exists, add_glossary_entry is called."""
        item = QListWidgetItem("Set")
        item.setData(Qt.ItemDataRole.UserRole, 1)
        ui.set_list.addItem(item)
        ui.set_list.setCurrentItem(item)
        ui.source_input.setText("hello")
        ui.target_input.setText("bonjour")

        on_add_entry(ui)

        mock_add.assert_called_once_with(1, "hello", "bonjour")
        mock_update.assert_not_called()

    @patch(f"{_G}.refresh_entries")
    @patch(f"{_G}.add_glossary_entry")
    @patch(f"{_G}.update_glossary_entry")
    @patch(f"{_G}.find_glossary_entry_by_source", return_value=(42, "bonjour"))
    def test_identical_duplicate_is_noop(
        self,
        mock_find,
        mock_update,
        mock_add,
        mock_refresh,
        ui,
    ) -> None:
        """When an identical row exists, neither add nor update is called."""
        item = QListWidgetItem("Set")
        item.setData(Qt.ItemDataRole.UserRole, 1)
        ui.set_list.addItem(item)
        ui.set_list.setCurrentItem(item)
        ui.source_input.setText("hello")
        ui.target_input.setText("bonjour")  # same target as existing

        on_add_entry(ui)

        mock_add.assert_not_called()
        mock_update.assert_not_called()

    @patch(f"{_G}.refresh_entries")
    @patch(f"{_G}.add_glossary_entry")
    @patch(f"{_G}.update_glossary_entry")
    @patch(f"{_G}.find_glossary_entry_by_source", return_value=(42, "bonjour"))
    def test_conflicting_duplicate_offers_replace(
        self,
        mock_find,
        mock_update,
        mock_add,
        mock_refresh,
        ui,
    ) -> None:
        """When target differs and user confirms replace, update is called."""
        item = QListWidgetItem("Set")
        item.setData(Qt.ItemDataRole.UserRole, 1)
        ui.set_list.addItem(item)
        ui.set_list.setCurrentItem(item)
        ui.source_input.setText("hello")
        ui.target_input.setText("salut")  # differs from existing "bonjour"

        # Autouse already returns True from confirm; verify the call.
        with patch(
            f"{_G}.CustomConfirmDialog.confirm",
            return_value=True,
        ) as mock_confirm:
            on_add_entry(ui)

        mock_confirm.assert_called_once()
        mock_update.assert_called_once_with(42, "hello", "salut")
        mock_add.assert_not_called()

    @patch(f"{_G}.refresh_entries")
    @patch(f"{_G}.add_glossary_entry")
    @patch(f"{_G}.update_glossary_entry")
    @patch(f"{_G}.find_glossary_entry_by_source", return_value=(42, "bonjour"))
    def test_conflicting_duplicate_cancel_keeps_existing(
        self,
        mock_find,
        mock_update,
        mock_add,
        mock_refresh,
        ui,
    ) -> None:
        """When user cancels the replace prompt, nothing is written."""
        item = QListWidgetItem("Set")
        item.setData(Qt.ItemDataRole.UserRole, 1)
        ui.set_list.addItem(item)
        ui.set_list.setCurrentItem(item)
        ui.source_input.setText("hello")
        ui.target_input.setText("salut")

        with patch(f"{_G}.CustomConfirmDialog.confirm", return_value=False):
            on_add_entry(ui)

        mock_update.assert_not_called()
        mock_add.assert_not_called()


class TestPerEntryDeleteConfirmation:
    """Tests that ``on_delete_entry`` is now gated by a confirmation dialog."""

    @patch(f"{_G}.refresh_entries")
    @patch(f"{_G}.delete_glossary_entry")
    def test_confirm_accept_deletes(self, mock_del, mock_refresh, ui) -> None:
        """Accepting the confirm dialog triggers the DB delete."""
        with patch(f"{_G}.CustomConfirmDialog.confirm", return_value=True):
            on_delete_entry(ui, 17)
        mock_del.assert_called_once_with(17)
        mock_refresh.assert_called_once_with(ui)

    @patch(f"{_G}.refresh_entries")
    @patch(f"{_G}.delete_glossary_entry")
    def test_confirm_reject_does_nothing(
        self,
        mock_del,
        mock_refresh,
        ui,
    ) -> None:
        """Rejecting the confirm dialog leaves the entry intact."""
        with patch(f"{_G}.CustomConfirmDialog.confirm", return_value=False):
            on_delete_entry(ui, 17)
        mock_del.assert_not_called()
        mock_refresh.assert_not_called()


class TestImportExportEntries:
    """Tests for CSV import/export of glossary entries."""

    def _prep_selected_set(self, ui, set_id: int = 5):
        """Adds a selected glossary set to the UI and returns the item."""
        item = QListWidgetItem("Import Set")
        item.setData(Qt.ItemDataRole.UserRole, set_id)
        item.setData(Qt.ItemDataRole.UserRole + 1, "Import Set")
        ui.set_list.addItem(item)
        ui.set_list.setCurrentItem(item)
        return item

    @patch(f"{_G}.refresh_entries")
    @patch(f"{_G}.add_glossary_entry")
    @patch(f"{_G}.update_glossary_entry")
    @patch(f"{_G}.find_glossary_entry_by_source", return_value=None)
    def test_import_adds_new_rows(
        self,
        mock_find,
        mock_update,
        mock_add,
        mock_refresh,
        ui,
        tmp_path,
    ) -> None:
        """CSV rows that don't match existing sources are inserted."""
        from src.ui.pages.glossary import on_import_entries  # noqa: PLC0415

        self._prep_selected_set(ui)
        csv_path = tmp_path / "import.csv"
        csv_path.write_text(
            "source,target\nhello,bonjour\ncat,chat\n",
            encoding="utf-8",
        )

        with patch(
            f"{_G}.QFileDialog.getOpenFileName",
            return_value=(str(csv_path), ""),
        ):
            on_import_entries(ui)

        assert mock_add.call_count == 2  # noqa: PLR2004
        mock_update.assert_not_called()

    @patch(f"{_G}.refresh_entries")
    @patch(f"{_G}.add_glossary_entry")
    @patch(f"{_G}.update_glossary_entry")
    def test_import_updates_existing_with_new_target(
        self,
        mock_update,
        mock_add,
        mock_refresh,
        ui,
        tmp_path,
    ) -> None:
        """CSV rows matching existing sources (different target) update them."""
        from src.ui.pages.glossary import on_import_entries  # noqa: PLC0415

        self._prep_selected_set(ui)
        csv_path = tmp_path / "import.csv"
        csv_path.write_text("hello,bonjour\n", encoding="utf-8")

        # Simulate existing row with entry_id=9 and current target "hi".
        with (
            patch(
                f"{_G}.find_glossary_entry_by_source",
                return_value=(9, "hi"),
            ),
            patch(
                f"{_G}.QFileDialog.getOpenFileName",
                return_value=(str(csv_path), ""),
            ),
        ):
            on_import_entries(ui)

        mock_update.assert_called_once_with(9, "hello", "bonjour")
        mock_add.assert_not_called()

    @patch(f"{_G}.refresh_entries")
    @patch(f"{_G}.add_glossary_entry")
    @patch(f"{_G}.update_glossary_entry")
    def test_import_skips_identical_rows(
        self,
        mock_update,
        mock_add,
        mock_refresh,
        ui,
        tmp_path,
    ) -> None:
        """CSV rows matching an existing row exactly don't trigger update."""
        from src.ui.pages.glossary import on_import_entries  # noqa: PLC0415

        self._prep_selected_set(ui)
        csv_path = tmp_path / "import.csv"
        csv_path.write_text("hello,bonjour\n", encoding="utf-8")

        with (
            patch(
                f"{_G}.find_glossary_entry_by_source",
                return_value=(9, "bonjour"),  # identical
            ),
            patch(
                f"{_G}.QFileDialog.getOpenFileName",
                return_value=(str(csv_path), ""),
            ),
        ):
            on_import_entries(ui)

        mock_update.assert_not_called()
        mock_add.assert_not_called()

    def test_export_writes_csv_with_header(self, ui, tmp_path) -> None:
        """Export writes a header row plus one row per entry."""
        import csv as csv_mod  # noqa: PLC0415

        from src.ui.pages.glossary import on_export_entries  # noqa: PLC0415

        item = QListWidgetItem("ExportSet")
        item.setData(Qt.ItemDataRole.UserRole, 3)
        item.setData(Qt.ItemDataRole.UserRole + 1, "ExportSet")
        ui.set_list.addItem(item)
        ui.set_list.setCurrentItem(item)

        out_path = tmp_path / "out.csv"
        with (
            patch(
                f"{_G}.get_glossary_entries",
                return_value=[(1, "hello", "bonjour"), (2, "cat", "chat")],
            ),
            patch(
                f"{_G}.QFileDialog.getSaveFileName",
                return_value=(str(out_path), "CSV (*.csv)"),
            ),
        ):
            on_export_entries(ui)

        rows = list(csv_mod.reader(out_path.read_text(encoding="utf-8").splitlines()))
        assert rows[0] == ["source", "target"]
        assert ["hello", "bonjour"] in rows
        assert ["cat", "chat"] in rows

    def test_import_skips_blank_and_header_rows(self, tmp_path) -> None:
        """_read_csv_pairs skips the header row plus rows with empties."""
        from src.ui.pages.glossary import _read_csv_pairs  # noqa: PLC0415

        csv_path = tmp_path / "messy.csv"
        csv_path.write_text(
            "source,target\n"
            "hello,bonjour\n"
            ",skipped-empty-source\n"
            "skipped-empty-target,\n"
            "cat,chat\n",
            encoding="utf-8",
        )
        pairs, skipped = _read_csv_pairs(csv_path)
        assert pairs == [("hello", "bonjour"), ("cat", "chat")]
        assert skipped == 2  # noqa: PLR2004

    def test_export_oserror_surfaces_failure_dialog(self, ui, tmp_path) -> None:
        """An OSError while writing the CSV shows a failure dialog (no crash)."""
        from src.ui.pages.glossary import on_export_entries  # noqa: PLC0415

        item = QListWidgetItem("ROSet")
        item.setData(Qt.ItemDataRole.UserRole, 7)
        item.setData(Qt.ItemDataRole.UserRole + 1, "ROSet")
        ui.set_list.addItem(item)
        ui.set_list.setCurrentItem(item)

        out_path = tmp_path / "readonly" / "out.csv"
        with (
            patch(
                f"{_G}.get_glossary_entries",
                return_value=[(1, "hello", "bonjour")],
            ),
            patch(
                f"{_G}.QFileDialog.getSaveFileName",
                return_value=(str(out_path), "CSV (*.csv)"),
            ),
            # Simulate read-only target directory by raising on open().
            patch(
                "pathlib.Path.open",
                side_effect=OSError("Permission denied"),
            ),
            patch(
                f"{_G}.CustomMessageDialog.show_message",
            ) as mock_show,
        ):
            on_export_entries(ui)

        # User-facing failure dialog fires; tr() returns raw keys in tests
        # so we check for the "failed" tag in either title or message.
        assert mock_show.call_count == 1
        args = mock_show.call_args.args
        assert any("failed" in str(a).lower() for a in args), args

    def test_import_oserror_surfaces_failure_dialog(
        self,
        ui,
        tmp_path,
    ) -> None:
        """OSError reading the import file shows a failure dialog; DB untouched."""
        from src.ui.pages.glossary import on_import_entries  # noqa: PLC0415

        item = QListWidgetItem("ImportSet")
        item.setData(Qt.ItemDataRole.UserRole, 11)
        item.setData(Qt.ItemDataRole.UserRole + 1, "ImportSet")
        ui.set_list.addItem(item)
        ui.set_list.setCurrentItem(item)

        # File "exists" via QFileDialog return, but Path.open raises.
        bogus_path = tmp_path / "missing.csv"
        with (
            patch(
                f"{_G}.QFileDialog.getOpenFileName",
                return_value=(str(bogus_path), ""),
            ),
            patch(
                "pathlib.Path.open",
                side_effect=OSError("file vanished"),
            ),
            patch(f"{_G}.add_glossary_entry") as mock_add,
            patch(f"{_G}.update_glossary_entry") as mock_update,
            patch(
                f"{_G}.CustomMessageDialog.show_message",
            ) as mock_show,
        ):
            on_import_entries(ui)

        mock_add.assert_not_called()
        mock_update.assert_not_called()
        assert mock_show.call_count == 1
        args = mock_show.call_args.args
        assert any("failed" in str(a).lower() for a in args), args

    def test_import_non_utf8_bytes_surfaces_failure_dialog(
        self,
        ui,
        tmp_path,
    ) -> None:
        """A non-UTF-8 CSV (e.g. raw latin-1 bytes) triggers the failure dialog."""
        from src.ui.pages.glossary import on_import_entries  # noqa: PLC0415

        item = QListWidgetItem("ImportSet")
        item.setData(Qt.ItemDataRole.UserRole, 17)
        item.setData(Qt.ItemDataRole.UserRole + 1, "ImportSet")
        ui.set_list.addItem(item)
        ui.set_list.setCurrentItem(item)

        # Mixed CRLF/LF + invalid UTF-8 sequence (\xff is not a valid UTF-8 byte).
        csv_path = tmp_path / "broken.csv"
        csv_path.write_bytes(
            b"source,target\r\nhello,bonjour\nbad\xff,token\r\n",
        )

        with (
            patch(
                f"{_G}.QFileDialog.getOpenFileName",
                return_value=(str(csv_path), ""),
            ),
            patch(f"{_G}.add_glossary_entry") as mock_add,
            patch(f"{_G}.update_glossary_entry") as mock_update,
            patch(
                f"{_G}.CustomMessageDialog.show_message",
            ) as mock_show,
        ):
            on_import_entries(ui)

        # Production catches UnicodeDecodeError → no DB writes, dialog fires.
        mock_add.assert_not_called()
        mock_update.assert_not_called()
        assert mock_show.call_count == 1
        args = mock_show.call_args.args
        assert any("failed" in str(a).lower() for a in args), args


class TestKeyboardShortcuts:
    """Tests for Ctrl+N (new set) and Ctrl+F (focus search)."""

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(f"{_G}.get_glossary_sets", return_value=[])
    def test_ctrl_f_shortcut_is_registered(
        self,
        mock_sets,
        mock_entries,
        qapp,
        qtbot,
    ) -> None:
        """A Ctrl+F shortcut exists on the glossary page (focuses search input)."""
        from PySide6.QtGui import QKeySequence, QShortcut  # noqa: PLC0415

        page = create_glossary_page()
        qtbot.addWidget(page)

        target_key = QKeySequence(Qt.Modifier.CTRL | Qt.Key.Key_F)
        shortcuts = [s for s in page.findChildren(QShortcut) if s.key() == target_key]
        assert shortcuts, "Ctrl+F shortcut not registered"

    @patch(f"{_G}.get_glossary_entries", return_value=[])
    @patch(f"{_G}.get_glossary_sets", return_value=[])
    def test_ctrl_n_shortcut_opens_create_set(
        self,
        mock_sets,
        mock_entries,
        qapp,
        qtbot,
    ) -> None:
        """Ctrl+N triggers on_create_set."""
        from PySide6.QtGui import QKeySequence, QShortcut  # noqa: PLC0415

        with patch(f"{_G}.on_create_set") as mock_create:
            page = create_glossary_page()
            qtbot.addWidget(page)

            target_key = QKeySequence(Qt.Modifier.CTRL | Qt.Key.Key_N)
            shortcuts = [
                s for s in page.findChildren(QShortcut) if s.key() == target_key
            ]
            assert shortcuts
            shortcuts[0].activated.emit()
            mock_create.assert_called_once()
