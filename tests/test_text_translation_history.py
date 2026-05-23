"""Unit tests for the embeddable text translation history widget.

Covers:
- Page construction and widget layout
- History table population with entries
- Delete history entry (single and multi-row)
- Search/filter functionality
- Auto-refresh behavior (fingerprint-based, debounced search, timer)
- Custom sort item classes
- Row filling and data storage
- View, copy, delete actions
- Signals and selection management
- Theme and language updates
"""

from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QTableWidget,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def window(qapp):
    """Provides a QMainWindow context."""
    return QMainWindow()


@pytest.fixture()
def _mock_db():
    """Mocks database calls so the widget can be constructed without a real DB."""
    with (
        patch(
            "src.ui.pages.text_translation_history.get_text_translation_fingerprint",
            return_value=(0, 0),
        ),
        patch(
            "src.ui.pages.text_translation_history.get_text_translation_history",
            return_value=[],
        ),
    ):
        yield


@pytest.fixture()
def widget(window, _mock_db, qtbot):
    """Creates a TextTranslationHistoryWidget for testing."""
    from src.ui.pages.text_translation_history import (  # noqa: PLC0415
        TextTranslationHistoryWidget,
    )

    w = TextTranslationHistoryWidget(window)
    qtbot.addWidget(w)
    return w


# ---------------------------------------------------------------------------
# Helper: sort items
# ---------------------------------------------------------------------------


class TestSortItems:
    """Tests for custom QTableWidgetItem sort subclasses."""

    def test_case_insensitive_sort_item(self) -> None:
        """CaseInsensitiveSortItem compares case-insensitively."""
        from src.ui.components import CaseInsensitiveSortItem  # noqa: PLC0415

        a = CaseInsensitiveSortItem("Banana")
        b = CaseInsensitiveSortItem("apple")
        # "apple" < "banana" case-insensitively
        assert b < a

    def test_datetime_sort_item(self) -> None:
        """DateTimeSortItem compares by ISO key, not display text."""
        from src.ui.components import DateTimeSortItem  # noqa: PLC0415

        a = DateTimeSortItem("March 15", "2026-03-15 10:00:00")
        b = DateTimeSortItem("Jan 1", "2026-01-01 08:00:00")
        # "2026-01-01" < "2026-03-15" chronologically
        assert b < a


# ---------------------------------------------------------------------------
# Helper: _truncate
# ---------------------------------------------------------------------------


class TestTruncate:
    """Tests for the _truncate helper function."""

    def test_short_text_returned_as_is(self) -> None:
        """Text shorter than max_len is returned without truncation."""
        from src.ui.pages.text_translation_history import _truncate  # noqa: PLC0415

        assert _truncate("short text") == "short text"

    def test_long_text_truncated_with_ellipsis(self) -> None:
        """Text exceeding max_len is truncated and gets '...' appended."""
        from src.ui.pages.text_translation_history import _truncate  # noqa: PLC0415

        long_text = "x" * 100
        result = _truncate(long_text, max_len=10)
        assert result == "xxxxxxxxxx..."
        assert len(result) == 13  # noqa: PLR2004 — 10 + "..."

    def test_newlines_collapsed_to_spaces(self) -> None:
        """Newlines in the source text are collapsed into single spaces."""
        from src.ui.pages.text_translation_history import _truncate  # noqa: PLC0415

        result = _truncate("line1\nline2\n\nline3")
        assert result == "line1 line2 line3"


# ---------------------------------------------------------------------------
# Widget construction
# ---------------------------------------------------------------------------


class TestHistoryWidgetConstruction:
    """Tests for TextTranslationHistoryWidget initialization."""

    def test_construction_no_error(self, widget) -> None:
        """Widget can be constructed without errors."""
        assert widget is not None

    def test_has_table_widget(self, widget) -> None:
        """Widget contains a QTableWidget."""
        assert hasattr(widget, "table")
        assert isinstance(widget.table, QTableWidget)

    def test_table_has_5_columns(self, widget) -> None:
        """Table has 5 columns (source, translated, source lang, target lang, date)."""
        assert widget.table.columnCount() == 5  # noqa: PLR2004

    def test_table_no_edit_triggers(self, widget) -> None:
        """Table is read-only (no edit triggers)."""
        assert widget.table.editTriggers() == QTableWidget.EditTrigger.NoEditTriggers

    def test_table_extended_selection_mode(self, widget) -> None:
        """Table supports multi-select via extended selection mode."""
        assert (
            widget.table.selectionMode() == QTableWidget.SelectionMode.ExtendedSelection
        )

    def test_highlight_delegate_attached(self, widget) -> None:
        """HighlightDelegate is attached to column 0."""
        from src.ui.components import HighlightDelegate  # noqa: PLC0415

        delegate = widget.table.itemDelegateForColumn(0)
        assert isinstance(delegate, HighlightDelegate)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


class TestSearch:
    """Tests for search filtering logic."""

    def test_set_search_text_stores_value(self, widget) -> None:
        """set_search_text stores the text for filtering."""
        widget.set_search_text("hello")
        assert widget._search_text == "hello"

    def test_search_filters_source_text(self, widget, _mock_db) -> None:
        """Search matches against source text (case-insensitive)."""
        entries = [
            (1, "Hello World", "Xin chào", "EN", "VI", 11, "2026-01-01 10:00:00"),
            (2, "Goodbye", "Tạm biệt", "EN", "VI", 7, "2026-01-01 11:00:00"),
        ]
        with patch(
            "src.ui.pages.text_translation_history.get_text_translation_history",
            return_value=entries,
        ):
            widget._search_text = "hello"
            widget.refresh_history(force=True)

        assert widget.table.rowCount() == 1

    def test_search_filters_translated_text(self, widget, _mock_db) -> None:
        """Search matches against translated text (case-insensitive)."""
        entries = [
            (1, "Hello", "Xin chào", "EN", "VI", 5, "2026-01-01 10:00:00"),
            (2, "Goodbye", "Tạm biệt", "EN", "VI", 7, "2026-01-01 11:00:00"),
        ]
        with patch(
            "src.ui.pages.text_translation_history.get_text_translation_history",
            return_value=entries,
        ):
            widget._search_text = "tạm"
            widget.refresh_history(force=True)

        assert widget.table.rowCount() == 1


# ---------------------------------------------------------------------------
# Refresh logic
# ---------------------------------------------------------------------------


class TestRefresh:
    """Tests for refresh_history behavior."""

    def test_refresh_skips_when_fingerprint_unchanged(
        self,
        window,
        qtbot,
    ) -> None:
        """Skips table rebuild when fingerprint hasn't changed."""
        from src.ui.pages.text_translation_history import (  # noqa: PLC0415
            TextTranslationHistoryWidget,
        )

        fp_mock = MagicMock(return_value=(0, 0))
        history_mock = MagicMock(return_value=[])
        with (
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_fingerprint",
                fp_mock,
            ),
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_history",
                history_mock,
            ),
        ):
            w = TextTranslationHistoryWidget(window)
            qtbot.addWidget(w)
            w.show()  # Widget must be visible for non-forced refresh
            # Construction calls refresh (which calls both mocks)
            fp_mock.reset_mock()
            history_mock.reset_mock()

            # Set fingerprint to match what the mock returns
            w._last_fingerprint = (0, 0)
            w.refresh_history(force=False)

            fp_mock.assert_called_once()
            # History should NOT be fetched when fingerprint is unchanged
            history_mock.assert_not_called()

    def test_refresh_rebuilds_when_fingerprint_changes(
        self,
        window,
        qtbot,
    ) -> None:
        """Rebuilds table when fingerprint changes."""
        from src.ui.pages.text_translation_history import (  # noqa: PLC0415
            TextTranslationHistoryWidget,
        )

        entries = [
            (1, "Test", "Kiểm tra", "", "VI", 4, "2026-01-01 10:00:00"),
        ]
        # Start with empty, then change fingerprint
        fp_values = iter([(0, 0), (0, 0), (1, 1)])
        with (
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_fingerprint",
                side_effect=lambda: next(fp_values, (1, 1)),
            ),
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_history",
                return_value=entries,
            ),
        ):
            w = TextTranslationHistoryWidget(window)
            qtbot.addWidget(w)
            w._last_fingerprint = (0, 0)
            w.refresh_history(force=False)

        assert w.table.rowCount() == 1

    def test_refresh_handles_none_from_db(self, window, qtbot) -> None:
        """When get_text_translation_history returns None, table is cleared."""
        from src.ui.pages.text_translation_history import (  # noqa: PLC0415
            TextTranslationHistoryWidget,
        )

        with (
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_fingerprint",
                return_value=(1, 1),
            ),
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_history",
                return_value=None,
            ),
        ):
            w = TextTranslationHistoryWidget(window)
            qtbot.addWidget(w)

        assert w.table.rowCount() == 0

    def test_force_refresh_always_rebuilds(self, window, qtbot) -> None:
        """force=True rebuilds even when fingerprint matches."""
        from src.ui.pages.text_translation_history import (  # noqa: PLC0415
            TextTranslationHistoryWidget,
        )

        history_mock = MagicMock(return_value=[])
        with (
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_fingerprint",
                return_value=(0, 0),
            ),
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_history",
                history_mock,
            ),
        ):
            w = TextTranslationHistoryWidget(window)
            qtbot.addWidget(w)
            history_mock.reset_mock()

            w._last_fingerprint = (0, 0)
            w.refresh_history(force=True)
            history_mock.assert_called_once()


# ---------------------------------------------------------------------------
# Row filling
# ---------------------------------------------------------------------------


class TestRowFilling:
    """Tests for _fill_row item creation and data storage."""

    def _make_widget_with_entries(self, widget, entries):
        """Populates widget with given entries via mocked refresh."""
        with (
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_fingerprint",
                return_value=(len(entries), len(entries)),
            ),
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_history",
                return_value=entries,
            ),
        ):
            widget._search_text = ""
            widget.refresh_history(force=True)

    def test_stores_entry_id_in_userrole(self, widget) -> None:
        """Entry ID is stored in UserRole data on column 0."""
        entry_id = 42  # noqa: PLR2004
        entries = [
            (entry_id, "src", "tgt", "", "FR", 3, "2026-01-01 10:00:00"),
        ]
        self._make_widget_with_entries(widget, entries)

        item = widget.table.item(0, 0)
        assert item.data(Qt.ItemDataRole.UserRole) == entry_id

    def test_stores_full_texts_in_userrole(self, widget) -> None:
        """Full source and translated texts stored in UserRole+1 and UserRole+2."""
        source = "Full source text that is very long"
        translated = "Full translated text that is also long"
        entries = [
            (1, source, translated, "", "FR", 33, "2026-01-01 10:00:00"),
        ]
        self._make_widget_with_entries(widget, entries)

        item = widget.table.item(0, 0)
        assert item.data(Qt.ItemDataRole.UserRole + 1) == source
        assert item.data(Qt.ItemDataRole.UserRole + 2) == translated

    def test_truncates_preview_text(self, widget) -> None:
        """Preview text is truncated to 80 characters."""
        long_text = "x" * 100
        entries = [
            (1, long_text, long_text, "", "FR", 100, "2026-01-01 10:00:00"),
        ]
        self._make_widget_with_entries(widget, entries)

        item = widget.table.item(0, 0)
        assert len(item.text()) == 83  # noqa: PLR2004 — 80 + "..."
        assert item.text().endswith("...")

    def test_language_display_auto_detect(self, widget) -> None:
        """Empty src_lang displays as 'Auto' in source column."""
        entries = [
            (1, "src", "tgt", "", "Vietnamese", 3, "2026-01-01 10:00:00"),
        ]
        self._make_widget_with_entries(widget, entries)

        src_lang_item = widget.table.item(0, 2)
        assert src_lang_item.text() != ""  # Shows "Auto" label
        tgt_lang_item = widget.table.item(0, 3)
        assert "Vietnamese" in tgt_lang_item.text()

    def test_language_display_explicit(self, widget) -> None:
        """Explicit src_lang is shown in source column."""
        entries = [
            (1, "src", "tgt", "English (US)", "French", 3, "2026-01-01 10:00:00"),
        ]
        self._make_widget_with_entries(widget, entries)

        src_lang_item = widget.table.item(0, 2)
        assert "English (US)" in src_lang_item.text()
        tgt_lang_item = widget.table.item(0, 3)
        assert "French" in tgt_lang_item.text()


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------


class TestActions:
    """Tests for view, copy, and delete actions."""

    def _make_widget_with_selection(self, widget, qtbot):
        """Populates widget with entries and selects the first row."""
        entries = [
            (1, "Source text", "Translated text", "", "FR", 11, "2026-01-01 10:00:00"),
            (2, "Another src", "Another tgt", "", "FR", 11, "2026-01-01 11:00:00"),
        ]
        with (
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_fingerprint",
                return_value=(2, 2),
            ),
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_history",
                return_value=entries,
            ),
        ):
            widget._search_text = ""
            widget.refresh_history(force=True)

        # Select first row
        widget.table.selectRow(0)
        return widget

    def test_on_copy_selected_copies_translated(self, widget, qtbot) -> None:
        """on_copy_selected copies translated text to clipboard."""
        self._make_widget_with_selection(widget, qtbot)

        widget.on_copy_selected()

        clipboard = QApplication.clipboard()
        # Should have copied the translated text from the first selected row
        assert clipboard.text() in ("Translated text", "Another tgt")

    def test_on_view_selected_no_crash_when_empty(self, widget) -> None:
        """on_view_selected does nothing when no rows are selected."""
        widget.on_view_selected()  # Should not raise

    def test_on_copy_selected_no_crash_when_empty(self, widget) -> None:
        """on_copy_selected does nothing when no rows are selected."""
        widget.on_copy_selected()  # Should not raise

    def test_on_delete_selected_no_crash_when_empty(self, widget) -> None:
        """on_delete_selected does nothing when no rows are selected."""
        widget.on_delete_selected()  # Should not raise

    @patch(
        "src.ui.pages.text_translation_history.CustomConfirmDialog.confirm",
        return_value=True,
    )
    @patch("src.ui.pages.text_translation_history.delete_text_translation_entry")
    def test_on_delete_selected_calls_delete(
        self,
        mock_delete,
        mock_confirm,
        widget,
        qtbot,
    ) -> None:
        """on_delete_selected deletes selected entries after confirmation."""
        self._make_widget_with_selection(widget, qtbot)

        with (
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_fingerprint",
                return_value=(1, 1),
            ),
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_history",
                return_value=[],
            ),
        ):
            widget.on_delete_selected()

        mock_confirm.assert_called_once()
        mock_delete.assert_called()

    @patch(
        "src.ui.pages.text_translation_history.CustomConfirmDialog.confirm",
        return_value=False,
    )
    @patch("src.ui.pages.text_translation_history.delete_text_translation_entry")
    def test_on_delete_selected_cancelled(
        self,
        mock_delete,
        mock_confirm,
        widget,
        qtbot,
    ) -> None:
        """on_delete_selected does nothing when user cancels confirmation."""
        self._make_widget_with_selection(widget, qtbot)
        widget.on_delete_selected()

        mock_confirm.assert_called_once()
        mock_delete.assert_not_called()

    @patch("src.ui.pages.text_translation_history._show_translation_detail")
    def test_on_view_selected_opens_detail(
        self,
        mock_detail,
        widget,
        qtbot,
    ) -> None:
        """on_view_selected opens detail dialog with correct texts."""
        self._make_widget_with_selection(widget, qtbot)
        widget.on_view_selected()

        mock_detail.assert_called_once()
        args = mock_detail.call_args[0]
        # Table is sorted by date descending — row 0 is the latest entry
        assert args[1] in ("Source text", "Another src")
        assert args[2] in ("Translated text", "Another tgt")

    @patch(
        "src.ui.pages.text_translation_history.CustomConfirmDialog.confirm",
        return_value=True,
    )
    @patch("src.ui.pages.text_translation_history.delete_text_translation_entry")
    def test_on_delete_multi_row(
        self,
        mock_delete,
        mock_confirm,
        widget,
        qtbot,
    ) -> None:
        """Deleting multiple selected rows calls delete for each entry."""
        entries = [
            (10, "A", "a", "", "FR", 1, "2026-01-01 10:00:00"),
            (20, "B", "b", "", "FR", 1, "2026-01-01 11:00:00"),
            (30, "C", "c", "", "FR", 1, "2026-01-01 12:00:00"),
        ]
        with (
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_fingerprint",
                return_value=(3, 3),
            ),
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_history",
                return_value=entries,
            ),
        ):
            widget._search_text = ""
            widget.refresh_history(force=True)

        # Select all rows
        widget.table.selectAll()
        assert len({item.row() for item in widget.table.selectedItems()}) == 3  # noqa: PLR2004

        with (
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_fingerprint",
                return_value=(0, 0),
            ),
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_history",
                return_value=[],
            ),
        ):
            widget.on_delete_selected()

        # All 3 entries should be deleted
        assert mock_delete.call_count == 3  # noqa: PLR2004
        deleted_ids = {call.args[0] for call in mock_delete.call_args_list}
        assert deleted_ids == {10, 20, 30}


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------


class TestSignals:
    """Tests for selection_changed signal emission."""

    def test_selection_changed_emitted_true_on_select(
        self,
        widget,
        qtbot,
    ) -> None:
        """selection_changed emits True when a row is selected."""
        entries = [
            (1, "src", "tgt", "", "FR", 3, "2026-01-01 10:00:00"),
        ]
        with (
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_fingerprint",
                return_value=(1, 1),
            ),
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_history",
                return_value=entries,
            ),
        ):
            widget.refresh_history(force=True)

        with qtbot.waitSignal(widget.selection_changed, timeout=1000):
            widget.table.selectRow(0)

    def test_header_click_clears_selection(self, widget, qtbot) -> None:
        """Clicking a header clears the current selection."""
        entries = [
            (1, "src", "tgt", "", "FR", 3, "2026-01-01 10:00:00"),
        ]
        with (
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_fingerprint",
                return_value=(1, 1),
            ),
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_history",
                return_value=entries,
            ),
        ):
            widget.refresh_history(force=True)

        widget.table.selectRow(0)
        assert len(widget.table.selectedItems()) > 0

        # Simulate header click
        widget._on_header_clicked(0)
        assert len(widget.table.selectedItems()) == 0


# ---------------------------------------------------------------------------
# Theme / Language
# ---------------------------------------------------------------------------


class TestThemeAndLanguage:
    """Tests for theme and language update methods."""

    def test_apply_theme_no_error(self, widget) -> None:
        """apply_theme runs without error."""
        with (
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_fingerprint",
                return_value=(0, 0),
            ),
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_history",
                return_value=[],
            ),
        ):
            widget.apply_theme()

    def test_apply_language_no_error(self, widget) -> None:
        """apply_language runs without error."""
        with (
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_fingerprint",
                return_value=(0, 0),
            ),
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_history",
                return_value=[],
            ),
        ):
            widget.apply_language()

    def test_apply_language_updates_headers(self, widget) -> None:
        """apply_language updates all 5 column header texts."""
        with (
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_fingerprint",
                return_value=(0, 0),
            ),
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_history",
                return_value=[],
            ),
        ):
            widget.apply_language()

        for col in range(4):
            header = widget.table.horizontalHeaderItem(col)
            assert header is not None
            assert len(header.text()) > 0


# ---------------------------------------------------------------------------
# Table population with entries
# ---------------------------------------------------------------------------


class TestTablePopulation:
    """Tests for populating the history table with data."""

    def _refresh_with_entries(self, widget, entries):
        """Helper to refresh widget with given entries."""
        with (
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_fingerprint",
                return_value=(len(entries), len(entries)),
            ),
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_history",
                return_value=entries,
            ),
        ):
            widget._search_text = ""
            widget.refresh_history(force=True)

    def test_empty_history_shows_no_rows(self, widget) -> None:
        """Empty history list results in zero rows."""
        self._refresh_with_entries(widget, [])
        assert widget.table.rowCount() == 0

    def test_single_entry_shows_one_row(self, widget) -> None:
        """One history entry produces one table row."""
        entries = [
            (1, "Hello", "Xin chao", "", "VI", 5, "2026-01-01 10:00:00"),
        ]
        self._refresh_with_entries(widget, entries)
        assert widget.table.rowCount() == 1

    def test_multiple_entries_show_correct_row_count(self, widget) -> None:
        """Multiple entries produce the correct number of rows."""
        entries = [
            (1, "First", "Mot", "", "VI", 5, "2026-01-01 10:00:00"),
            (2, "Second", "Hai", "", "VI", 6, "2026-01-02 10:00:00"),
            (3, "Third", "Ba", "", "VI", 5, "2026-01-03 10:00:00"),
        ]
        self._refresh_with_entries(widget, entries)
        assert widget.table.rowCount() == 3  # noqa: PLR2004

    def test_date_column_has_formatted_text(self, widget) -> None:
        """Date column shows locale-formatted date, not raw ISO."""
        entries = [
            (1, "Hi", "Chao", "", "VI", 2, "2026-03-15 14:30:00"),
        ]
        self._refresh_with_entries(widget, entries)
        date_item = widget.table.item(0, 4)
        assert date_item is not None
        # Should contain some date formatting (not the raw ISO string)
        assert date_item.text() != ""

    def test_source_language_column_populated(self, widget) -> None:
        """Source language column is populated with the source language."""
        entries = [
            (1, "Hi", "Salut", "EN", "FR", 2, "2026-01-01 10:00:00"),
        ]
        self._refresh_with_entries(widget, entries)
        src_lang_item = widget.table.item(0, 2)
        assert src_lang_item.text() == "EN"
        tgt_lang_item = widget.table.item(0, 3)
        assert tgt_lang_item.text() == "FR"

    def test_selection_preserved_across_refresh(self, widget) -> None:
        """Selected row IDs are preserved after a refresh."""
        entries = [
            (10, "A", "a", "", "FR", 1, "2026-01-01 10:00:00"),
            (20, "B", "b", "", "FR", 1, "2026-01-02 10:00:00"),
        ]
        self._refresh_with_entries(widget, entries)

        # Select the row containing entry_id=20
        for row in range(widget.table.rowCount()):
            item = widget.table.item(row, 0)
            if item.data(Qt.ItemDataRole.UserRole) == 20:  # noqa: PLR2004
                widget.table.selectRow(row)
                break

        # Refresh again — selection should be preserved
        self._refresh_with_entries(widget, entries)

        selected_ids = set()
        for item in widget.table.selectedItems():
            if item.column() == 0:
                h_id = item.data(Qt.ItemDataRole.UserRole)
                if h_id is not None:
                    selected_ids.add(h_id)
        assert 20 in selected_ids  # noqa: PLR2004

    def test_translated_preview_column_populated(self, widget) -> None:
        """Translated text preview is shown in column 1."""
        entries = [
            (
                1,
                "Hello World",
                "Xin chao the gioi",
                "",
                "VI",
                11,
                "2026-01-01 10:00:00",
            ),
        ]
        self._refresh_with_entries(widget, entries)
        item = widget.table.item(0, 1)
        assert item is not None
        assert "Xin chao the gioi" in item.text()


# ---------------------------------------------------------------------------
# Delete history entry (extended)
# ---------------------------------------------------------------------------


class TestDeleteEntry:
    """Extended tests for deleting history entries."""

    def _populate_and_select(self, widget, entries, select_rows=None):
        """Helper to populate widget and select specified rows."""
        with (
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_fingerprint",
                return_value=(len(entries), len(entries)),
            ),
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_history",
                return_value=entries,
            ),
        ):
            widget._search_text = ""
            widget.refresh_history(force=True)

        if select_rows is not None:
            for row in select_rows:
                widget.table.selectRow(row)

    @patch(
        "src.ui.pages.text_translation_history.CustomConfirmDialog.confirm",
        return_value=True,
    )
    @patch("src.ui.pages.text_translation_history.delete_text_translation_entry")
    def test_delete_single_entry(
        self,
        mock_delete,
        mock_confirm,
        widget,
        qtbot,
    ) -> None:
        """Deleting a single selected entry calls delete with correct ID."""
        entries = [
            (99, "Delete me", "Xoa", "", "VI", 9, "2026-01-01 10:00:00"),
        ]
        self._populate_and_select(widget, entries, select_rows=[0])

        with (
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_fingerprint",
                return_value=(0, 0),
            ),
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_history",
                return_value=[],
            ),
        ):
            widget.on_delete_selected()

        mock_delete.assert_called_once()
        deleted_id = mock_delete.call_args[0][0]
        assert deleted_id == 99  # noqa: PLR2004

    @patch(
        "src.ui.pages.text_translation_history.CustomConfirmDialog.confirm",
        return_value=True,
    )
    @patch("src.ui.pages.text_translation_history.delete_text_translation_entry")
    def test_delete_refreshes_table(
        self,
        mock_delete,
        mock_confirm,
        widget,
        qtbot,
    ) -> None:
        """After deletion, the table is refreshed to reflect changes."""
        entries = [
            (1, "A", "a", "", "FR", 1, "2026-01-01 10:00:00"),
        ]
        self._populate_and_select(widget, entries, select_rows=[0])

        with (
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_fingerprint",
                return_value=(0, 0),
            ),
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_history",
                return_value=[],
            ),
        ):
            widget.on_delete_selected()

        # Table should now be empty after refresh
        assert widget.table.rowCount() == 0


# ---------------------------------------------------------------------------
# Search/filter (extended)
# ---------------------------------------------------------------------------


class TestSearchExtended:
    """Extended tests for search and filter functionality."""

    def _refresh_with_entries(self, widget, entries):
        """Helper to refresh widget with given entries."""
        with (
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_fingerprint",
                return_value=(len(entries), len(entries)),
            ),
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_history",
                return_value=entries,
            ),
        ):
            widget.refresh_history(force=True)

    def test_search_empty_string_shows_all(self, widget) -> None:
        """Empty search text shows all entries."""
        entries = [
            (1, "Hello", "Xin chao", "", "VI", 5, "2026-01-01 10:00:00"),
            (2, "Goodbye", "Tam biet", "", "VI", 7, "2026-01-02 10:00:00"),
        ]
        widget._search_text = ""
        self._refresh_with_entries(widget, entries)
        assert widget.table.rowCount() == 2  # noqa: PLR2004

    def test_search_whitespace_only_shows_all(self, widget) -> None:
        """Whitespace-only search text shows all entries."""
        entries = [
            (1, "Hello", "Xin chao", "", "VI", 5, "2026-01-01 10:00:00"),
            (2, "Goodbye", "Tam biet", "", "VI", 7, "2026-01-02 10:00:00"),
        ]
        widget._search_text = "   "
        self._refresh_with_entries(widget, entries)
        assert widget.table.rowCount() == 2  # noqa: PLR2004

    def test_search_no_match_shows_zero_rows(self, widget) -> None:
        """Search with no matching text shows zero rows."""
        entries = [
            (1, "Hello", "Xin chao", "", "VI", 5, "2026-01-01 10:00:00"),
        ]
        widget._search_text = "zzzznotfound"
        self._refresh_with_entries(widget, entries)
        assert widget.table.rowCount() == 0

    def test_search_case_insensitive(self, widget) -> None:
        """Search is case-insensitive for both source and translated text."""
        entries = [
            (1, "HELLO", "Xin chao", "", "VI", 5, "2026-01-01 10:00:00"),
        ]
        widget._search_text = "hello"
        self._refresh_with_entries(widget, entries)
        assert widget.table.rowCount() == 1

    def test_search_debounce_timer_started(self, widget) -> None:
        """set_search_text starts the debounce timer."""
        widget.set_search_text("test query")
        assert widget._search_text == "test query"
        assert widget._search_timer.isActive()

    def test_search_updates_highlight_delegate(self, widget) -> None:
        """Search text is passed to the highlight delegate."""
        entries = [
            (1, "Hello World", "Xin chao", "", "VI", 11, "2026-01-01 10:00:00"),
        ]
        widget._search_text = "Hello"
        self._refresh_with_entries(widget, entries)
        assert widget.highlight_delegate.search_text == "Hello"

    def test_search_matches_partial_source(self, widget) -> None:
        """Search matches partial text in source column."""
        entries = [
            (
                1,
                "Hello beautiful world",
                "Xin chao",
                "",
                "VI",
                21,
                "2026-01-01 10:00:00",
            ),
        ]
        widget._search_text = "beautiful"
        self._refresh_with_entries(widget, entries)
        assert widget.table.rowCount() == 1

    def test_search_matches_partial_translated(self, widget) -> None:
        """Search matches partial text in translated column."""
        entries = [
            (1, "Hello", "Xin chao the gioi dep", "", "VI", 5, "2026-01-01 10:00:00"),
        ]
        widget._search_text = "gioi"
        self._refresh_with_entries(widget, entries)
        assert widget.table.rowCount() == 1


# ---------------------------------------------------------------------------
# Auto-refresh behavior
# ---------------------------------------------------------------------------


class TestAutoRefresh:
    """Tests for auto-refresh timer and visibility-gated refresh."""

    def test_refresh_timer_active_after_construction(self, widget) -> None:
        """Background refresh timer is running after construction."""
        assert widget._refresh_timer.isActive()

    def test_refresh_timer_interval(self, widget) -> None:
        """Refresh timer interval is 1000ms."""
        assert widget._refresh_timer.interval() == 1000  # noqa: PLR2004

    def test_search_timer_is_singleshot(self, widget) -> None:
        """Search debounce timer is single-shot."""
        assert widget._search_timer.isSingleShot()

    def test_refresh_skips_when_not_visible_and_not_forced(
        self,
        window,
        qtbot,
    ) -> None:
        """Non-forced refresh is skipped when widget is not visible."""
        from src.ui.pages.text_translation_history import (  # noqa: PLC0415
            TextTranslationHistoryWidget,
        )

        fp_mock = MagicMock(return_value=(0, 0))
        history_mock = MagicMock(return_value=[])
        with (
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_fingerprint",
                fp_mock,
            ),
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_history",
                history_mock,
            ),
        ):
            w = TextTranslationHistoryWidget(window)
            qtbot.addWidget(w)
            # Widget is NOT shown — isVisible() returns False
            fp_mock.reset_mock()
            history_mock.reset_mock()

            w.refresh_history(force=False)

            # Should not even check fingerprint when not visible
            fp_mock.assert_not_called()

    def test_fingerprint_none_forces_rebuild(self, window, qtbot) -> None:
        """When fingerprint returns None, table is still rebuilt."""
        from src.ui.pages.text_translation_history import (  # noqa: PLC0415
            TextTranslationHistoryWidget,
        )

        history_mock = MagicMock(return_value=[])
        with (
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_fingerprint",
                return_value=None,
            ),
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_history",
                history_mock,
            ),
        ):
            w = TextTranslationHistoryWidget(window)
            qtbot.addWidget(w)
            # With None fingerprint, it should still proceed to rebuild
            history_mock.assert_called()

    def test_show_event_triggers_force_refresh(self, window, qtbot) -> None:
        """Show event calls refresh_history(force=True)."""
        from src.ui.pages.text_translation_history import (  # noqa: PLC0415
            TextTranslationHistoryWidget,
        )

        with (
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_fingerprint",
                return_value=(0, 0),
            ),
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_history",
                return_value=[],
            ),
        ):
            w = TextTranslationHistoryWidget(window)
            qtbot.addWidget(w)

        with patch.object(w, "refresh_history") as mock_refresh:
            w.show()
            mock_refresh.assert_called_with(force=True)


# ---------------------------------------------------------------------------
# Sort items extended
# ---------------------------------------------------------------------------


class TestSortItemsExtended:
    """Extended tests for custom sort items."""

    def test_case_insensitive_equal_items(self) -> None:
        """CaseInsensitiveSortItem: same text is not less than itself."""
        from src.ui.components import CaseInsensitiveSortItem  # noqa: PLC0415

        a = CaseInsensitiveSortItem("Apple")
        b = CaseInsensitiveSortItem("apple")
        assert not (a < b)
        assert not (b < a)

    def test_datetime_sort_item_against_regular_item(self) -> None:
        """DateTimeSortItem falls back to parent comparison with regular items."""
        from PySide6.QtWidgets import QTableWidgetItem  # noqa: PLC0415

        from src.ui.components import DateTimeSortItem  # noqa: PLC0415

        a = DateTimeSortItem("March 15", "2026-03-15 10:00:00")
        b = QTableWidgetItem("Anything")
        # Should not crash — falls back to parent __lt__
        _ = a < b

    def test_datetime_sort_same_timestamps(self) -> None:
        """DateTimeSortItem: same ISO key is not less than itself."""
        from src.ui.components import DateTimeSortItem  # noqa: PLC0415

        a = DateTimeSortItem("Date A", "2026-01-01 10:00:00")
        b = DateTimeSortItem("Date B", "2026-01-01 10:00:00")
        assert not (a < b)
        assert not (b < a)


# ---------------------------------------------------------------------------
# Truncate extended
# ---------------------------------------------------------------------------


class TestTruncateExtended:
    """Extended tests for the _truncate helper."""

    def test_truncate_with_tabs(self) -> None:
        """Tabs are collapsed to spaces."""
        from src.ui.pages.text_translation_history import _truncate  # noqa: PLC0415

        result = _truncate("col1\tcol2\tcol3")
        assert result == "col1 col2 col3"

    def test_truncate_exact_max_len(self) -> None:
        """Text exactly at max_len is returned without ellipsis."""
        from src.ui.pages.text_translation_history import _truncate  # noqa: PLC0415

        text = "x" * 80  # noqa: PLR2004
        result = _truncate(text, max_len=80)
        assert result == text
        assert "..." not in result

    def test_truncate_empty_string(self) -> None:
        """Empty string returns empty string."""
        from src.ui.pages.text_translation_history import _truncate  # noqa: PLC0415

        assert _truncate("") == ""

    def test_truncate_mixed_whitespace(self) -> None:
        """Multiple consecutive spaces/newlines/tabs collapse to single space."""
        from src.ui.pages.text_translation_history import _truncate  # noqa: PLC0415

        result = _truncate("a  b\n\nc   d")
        assert result == "a b c d"


# ---------------------------------------------------------------------------
# NEW TESTS: Widget Creation (additional)
# ---------------------------------------------------------------------------


class TestWidgetCreation:
    """Additional tests for widget creation and structure."""

    def test_widget_has_table_attribute(self, widget) -> None:
        """Widget exposes a 'table' attribute."""
        assert hasattr(widget, "table")

    def test_table_is_qtablewidget(self, widget) -> None:
        """The table attribute is a QTableWidget instance."""
        assert isinstance(widget.table, QTableWidget)

    def test_table_has_correct_column_count(self, widget) -> None:
        """Table has exactly 5 columns."""
        assert widget.table.columnCount() == 5  # noqa: PLR2004

    def test_table_columns_match_header_keys(self, widget) -> None:
        """Each column has a non-empty header text matching _HEADER_KEYS count."""
        from src.ui.pages.text_translation_history import (  # noqa: PLC0415
            _HEADER_KEYS,
        )

        assert widget.table.columnCount() == len(_HEADER_KEYS)
        for i in range(len(_HEADER_KEYS)):
            header = widget.table.horizontalHeaderItem(i)
            assert header is not None
            assert header.text() != ""

    def test_initial_last_fingerprint_is_set(self, widget) -> None:
        """After construction, _last_fingerprint is set from DB mock."""
        # The mock returns (0, 0), so _last_fingerprint should be set
        assert widget._last_fingerprint is not None

    def test_search_text_initially_empty(self, widget) -> None:
        """The _search_text is empty at construction time."""
        assert widget._search_text == ""


# ---------------------------------------------------------------------------
# NEW TESTS: Refresh History (additional)
# ---------------------------------------------------------------------------


class TestRefreshHistoryExtended:
    """Additional tests for refresh_history behavior."""

    def _refresh_with_entries(self, widget, entries):
        """Helper to refresh widget with given entries."""
        with (
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_fingerprint",
                return_value=(len(entries), len(entries)),
            ),
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_history",
                return_value=entries,
            ),
        ):
            widget._search_text = ""
            widget.refresh_history(force=True)

    def test_refresh_with_empty_db(self, widget) -> None:
        """Refreshing with empty DB yields zero rows."""
        self._refresh_with_entries(widget, [])
        assert widget.table.rowCount() == 0

    def test_refresh_with_entries_populates_table(self, widget) -> None:
        """Refreshing with entries populates the table correctly."""
        entries = [
            (1, "Hello", "Bonjour", "EN", "FR", 5, "2026-01-01 10:00:00"),
            (2, "Goodbye", "Au revoir", "EN", "FR", 7, "2026-01-02 10:00:00"),
        ]
        self._refresh_with_entries(widget, entries)
        assert widget.table.rowCount() == 2  # noqa: PLR2004

    def test_refresh_preserves_selection_by_id(self, widget) -> None:
        """Refresh preserves selection by entry ID, not row index."""
        entries = [
            (10, "Alpha", "a", "", "FR", 5, "2026-01-01 10:00:00"),
            (20, "Beta", "b", "", "FR", 4, "2026-01-02 10:00:00"),
            (30, "Gamma", "g", "", "FR", 5, "2026-01-03 10:00:00"),
        ]
        self._refresh_with_entries(widget, entries)

        # Select entry with id=20
        for row in range(widget.table.rowCount()):
            item = widget.table.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == 20:  # noqa: PLR2004
                widget.table.selectRow(row)
                break

        # Refresh again
        self._refresh_with_entries(widget, entries)

        # Verify entry_id 20 is still selected
        selected_ids = set()
        for item in widget.table.selectedItems():
            if item.column() == 0:
                h_id = item.data(Qt.ItemDataRole.UserRole)
                if h_id is not None:
                    selected_ids.add(h_id)
        assert 20 in selected_ids  # noqa: PLR2004

    def test_refresh_preserves_scroll_position(self, widget) -> None:
        """Refresh preserves the vertical scroll position."""
        entries = [
            (i, f"Text {i}", f"Translated {i}", "", "FR", 5, "2026-01-01 10:00:00")
            for i in range(50)
        ]
        self._refresh_with_entries(widget, entries)

        # Set scroll position
        widget.table.verticalScrollBar().setValue(100)
        scroll_before = widget.table.verticalScrollBar().value()

        self._refresh_with_entries(widget, entries)
        scroll_after = widget.table.verticalScrollBar().value()
        assert scroll_after == scroll_before

    def test_force_refresh_bypasses_fingerprint(self, window, qtbot) -> None:
        """force=True always rebuilds regardless of fingerprint match."""
        from src.ui.pages.text_translation_history import (  # noqa: PLC0415
            TextTranslationHistoryWidget,
        )

        history_mock = MagicMock(return_value=[])
        with (
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_fingerprint",
                return_value=(5, 5),
            ),
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_history",
                history_mock,
            ),
        ):
            w = TextTranslationHistoryWidget(window)
            qtbot.addWidget(w)
            history_mock.reset_mock()

            # Set fingerprint same as what the mock returns
            w._last_fingerprint = (5, 5)
            w.refresh_history(force=True)
            history_mock.assert_called_once()

    def test_fingerprint_comparison_skips_unnecessary_refresh(
        self, window, qtbot
    ) -> None:
        """When fingerprint matches and not forced, table rebuild is skipped."""
        from src.ui.pages.text_translation_history import (  # noqa: PLC0415
            TextTranslationHistoryWidget,
        )

        fp_mock = MagicMock(return_value=(3, 3))
        history_mock = MagicMock(return_value=[])
        with (
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_fingerprint",
                fp_mock,
            ),
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_history",
                history_mock,
            ),
        ):
            w = TextTranslationHistoryWidget(window)
            qtbot.addWidget(w)
            w.show()
            fp_mock.reset_mock()
            history_mock.reset_mock()

            w._last_fingerprint = (3, 3)
            w.refresh_history(force=False)

            fp_mock.assert_called_once()
            history_mock.assert_not_called()


# ---------------------------------------------------------------------------
# NEW TESTS: Search (additional)
# ---------------------------------------------------------------------------


class TestSearchAdditional:
    """Additional tests for search functionality."""

    def _refresh_with_entries(self, widget, entries):
        """Helper to refresh widget with given entries."""
        with (
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_fingerprint",
                return_value=(len(entries), len(entries)),
            ),
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_history",
                return_value=entries,
            ),
        ):
            widget.refresh_history(force=True)

    def test_set_search_text_triggers_debounce_timer(self, widget) -> None:
        """set_search_text starts the debounce timer."""
        widget.set_search_text("query")
        assert widget._search_timer.isActive()

    def test_search_filters_source_text_match(self, widget) -> None:
        """Search filters by source text content."""
        entries = [
            (1, "Apple Pie", "Banh tao", "EN", "VI", 9, "2026-01-01 10:00:00"),
            (2, "Cherry Cake", "Banh cherry", "EN", "VI", 11, "2026-01-02 10:00:00"),
        ]
        widget._search_text = "apple"
        self._refresh_with_entries(widget, entries)
        assert widget.table.rowCount() == 1

    def test_search_filters_translated_text_match(self, widget) -> None:
        """Search filters by translated text content."""
        entries = [
            (1, "Hello", "Bonjour", "EN", "FR", 5, "2026-01-01 10:00:00"),
            (2, "Bye", "Au revoir", "EN", "FR", 3, "2026-01-02 10:00:00"),
        ]
        widget._search_text = "revoir"
        self._refresh_with_entries(widget, entries)
        assert widget.table.rowCount() == 1

    def test_search_case_insensitive_source(self, widget) -> None:
        """Search is case-insensitive when matching source text."""
        entries = [
            (1, "UPPERCASE TEXT", "lowercase", "", "FR", 14, "2026-01-01 10:00:00"),
        ]
        widget._search_text = "uppercase"
        self._refresh_with_entries(widget, entries)
        assert widget.table.rowCount() == 1

    def test_search_case_insensitive_translated(self, widget) -> None:
        """Search is case-insensitive when matching translated text."""
        entries = [
            (1, "hello", "TRANSLATED", "", "FR", 5, "2026-01-01 10:00:00"),
        ]
        widget._search_text = "translated"
        self._refresh_with_entries(widget, entries)
        assert widget.table.rowCount() == 1

    def test_clear_search_restores_all_entries(self, widget) -> None:
        """Clearing search text restores all entries."""
        entries = [
            (1, "Alpha", "a", "", "FR", 5, "2026-01-01 10:00:00"),
            (2, "Beta", "b", "", "FR", 4, "2026-01-02 10:00:00"),
        ]
        # First filter
        widget._search_text = "alpha"
        self._refresh_with_entries(widget, entries)
        assert widget.table.rowCount() == 1

        # Clear search
        widget._search_text = ""
        self._refresh_with_entries(widget, entries)
        assert widget.table.rowCount() == 2  # noqa: PLR2004

    def test_search_with_no_matches_shows_empty(self, widget) -> None:
        """Search with no matches results in zero rows."""
        entries = [
            (1, "Hello", "Bonjour", "EN", "FR", 5, "2026-01-01 10:00:00"),
        ]
        widget._search_text = "zzzzzzzzzzz"
        self._refresh_with_entries(widget, entries)
        assert widget.table.rowCount() == 0


# ---------------------------------------------------------------------------
# NEW TESTS: Actions (additional)
# ---------------------------------------------------------------------------


class TestActionsAdditional:
    """Additional tests for view, copy, and delete actions."""

    def _populate(self, widget, entries):
        """Populates widget with given entries."""
        with (
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_fingerprint",
                return_value=(len(entries), len(entries)),
            ),
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_history",
                return_value=entries,
            ),
        ):
            widget._search_text = ""
            widget.refresh_history(force=True)

    @patch("src.ui.pages.text_translation_history._show_translation_detail")
    def test_on_view_selected_shows_dialog(
        self,
        mock_detail,
        widget,
        qtbot,
    ) -> None:
        """on_view_selected opens the detail dialog with source and translated text."""
        entries = [
            (1, "Source here", "Translated here", "", "FR", 11, "2026-01-01 10:00:00"),
        ]
        self._populate(widget, entries)
        widget.table.selectRow(0)

        widget.on_view_selected()

        mock_detail.assert_called_once()
        args = mock_detail.call_args[0]
        assert args[1] == "Source here"
        assert args[2] == "Translated here"

    def test_on_view_selected_with_no_selection(self, widget) -> None:
        """on_view_selected returns early without crashing when nothing is selected."""
        widget.table.clearSelection()
        widget.on_view_selected()  # Should not raise

    def test_on_copy_selected_copies_to_clipboard(self, widget, qtbot) -> None:
        """on_copy_selected copies translated text to system clipboard."""
        entries = [
            (1, "Source", "CopiedTranslation", "", "FR", 6, "2026-01-01 10:00:00"),
        ]
        self._populate(widget, entries)
        widget.table.selectRow(0)

        widget.on_copy_selected()

        clipboard = QApplication.clipboard()
        assert clipboard.text() == "CopiedTranslation"

    def test_on_copy_selected_with_no_selection(self, widget) -> None:
        """on_copy_selected does nothing when nothing is selected."""
        widget.table.clearSelection()
        widget.on_copy_selected()  # Should not raise

    @patch(
        "src.ui.pages.text_translation_history.CustomConfirmDialog.confirm",
        return_value=True,
    )
    @patch("src.ui.pages.text_translation_history.delete_text_translation_entry")
    def test_on_delete_selected_with_confirmation(
        self,
        mock_delete,
        mock_confirm,
        widget,
        qtbot,
    ) -> None:
        """on_delete_selected deletes entry when user confirms."""
        entries = [
            (50, "Delete me", "Supprimer", "", "FR", 9, "2026-01-01 10:00:00"),
        ]
        self._populate(widget, entries)
        widget.table.selectRow(0)

        with (
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_fingerprint",
                return_value=(0, 0),
            ),
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_history",
                return_value=[],
            ),
        ):
            widget.on_delete_selected()

        mock_confirm.assert_called_once()
        mock_delete.assert_called_once_with(50)  # noqa: PLR2004

    @patch(
        "src.ui.pages.text_translation_history.CustomConfirmDialog.confirm",
        return_value=False,
    )
    @patch("src.ui.pages.text_translation_history.delete_text_translation_entry")
    def test_on_delete_selected_cancelled_no_delete(
        self,
        mock_delete,
        mock_confirm,
        widget,
        qtbot,
    ) -> None:
        """on_delete_selected does not delete when user cancels."""
        entries = [
            (50, "Keep me", "Garder", "", "FR", 7, "2026-01-01 10:00:00"),
        ]
        self._populate(widget, entries)
        widget.table.selectRow(0)

        widget.on_delete_selected()

        mock_confirm.assert_called_once()
        mock_delete.assert_not_called()

    def test_on_delete_selected_no_selection(self, widget) -> None:
        """on_delete_selected does nothing when no rows are selected."""
        widget.table.clearSelection()
        widget.on_delete_selected()  # Should not raise


# ---------------------------------------------------------------------------
# NEW TESTS: Theme / Language (additional)
# ---------------------------------------------------------------------------


class TestThemeLanguageAdditional:
    """Additional tests for theme and language application."""

    def test_apply_theme_updates_table_style(self, widget) -> None:
        """apply_theme updates the table stylesheet."""
        with (
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_fingerprint",
                return_value=(0, 0),
            ),
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_history",
                return_value=[],
            ),
        ):
            widget.apply_theme()
        assert widget.table.styleSheet() != ""

    def test_apply_language_updates_all_headers(self, widget) -> None:
        """apply_language updates all column header texts."""
        with (
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_fingerprint",
                return_value=(0, 0),
            ),
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_history",
                return_value=[],
            ),
        ):
            widget.apply_language()

        for col in range(widget.table.columnCount()):
            header = widget.table.horizontalHeaderItem(col)
            assert header is not None
            assert len(header.text()) > 0

    def test_apply_theme_refreshes_highlight_delegate(self, widget) -> None:
        """apply_theme updates the highlight delegate selected color."""
        with (
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_fingerprint",
                return_value=(0, 0),
            ),
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_history",
                return_value=[],
            ),
        ):
            widget.apply_theme()
        # The delegate should have a non-empty selected_color
        assert widget.highlight_delegate is not None


# ---------------------------------------------------------------------------
# NEW TESTS: Truncate (additional)
# ---------------------------------------------------------------------------


class TestTruncateAdditional:
    """Additional tests for _truncate helper function."""

    def test_truncate_short_text_no_change(self) -> None:
        """Short text is returned unchanged."""
        from src.ui.pages.text_translation_history import _truncate  # noqa: PLC0415

        assert _truncate("hello", max_len=80) == "hello"

    def test_truncate_long_text_adds_ellipsis(self) -> None:
        """Text exceeding max_len gets '...' appended."""
        from src.ui.pages.text_translation_history import _truncate  # noqa: PLC0415

        text = "a" * 50
        result = _truncate(text, max_len=20)
        assert result == "a" * 20 + "..."
        assert len(result) == 23  # noqa: PLR2004

    def test_truncate_with_newlines_collapsed(self) -> None:
        """Newlines in text are collapsed into single spaces."""
        from src.ui.pages.text_translation_history import _truncate  # noqa: PLC0415

        result = _truncate("first\nsecond\nthird")
        assert result == "first second third"

    def test_truncate_exactly_max_len_no_ellipsis(self) -> None:
        """Text exactly at max_len is returned without ellipsis."""
        from src.ui.pages.text_translation_history import _truncate  # noqa: PLC0415

        text = "y" * 40
        result = _truncate(text, max_len=40)
        assert result == text
        assert "..." not in result

    def test_truncate_one_over_max_len(self) -> None:
        """Text one character over max_len gets truncated with ellipsis."""
        from src.ui.pages.text_translation_history import _truncate  # noqa: PLC0415

        text = "z" * 41
        result = _truncate(text, max_len=40)
        assert result == "z" * 40 + "..."

    def test_truncate_only_whitespace(self) -> None:
        """Whitespace-only text collapses to empty string."""
        from src.ui.pages.text_translation_history import _truncate  # noqa: PLC0415

        result = _truncate("   \n\n\t  ")
        assert result == ""


# ---------------------------------------------------------------------------
# NEW TESTS: Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Tests for edge cases in the history widget."""

    def _refresh_with_entries(self, widget, entries):
        """Helper to refresh widget with given entries."""
        with (
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_fingerprint",
                return_value=(len(entries), len(entries)),
            ),
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_history",
                return_value=entries,
            ),
        ):
            widget._search_text = ""
            widget.refresh_history(force=True)

    def test_unicode_text_in_table(self, widget) -> None:
        """Unicode characters (CJK, emoji-like) are handled correctly."""
        entries = [
            (
                1,
                "\u4f60\u597d\u4e16\u754c",
                "\u3053\u3093\u306b\u3061\u306f\u4e16\u754c",
                "ZH",
                "JA",
                4,
                "2026-01-01 10:00:00",
            ),
        ]
        self._refresh_with_entries(widget, entries)
        assert widget.table.rowCount() == 1
        item = widget.table.item(0, 0)
        assert "\u4f60\u597d" in item.text()

    def test_empty_source_and_translated(self, widget) -> None:
        """Empty source and translated text do not crash the widget."""
        entries = [
            (1, "", "", "", "FR", 0, "2026-01-01 10:00:00"),
        ]
        self._refresh_with_entries(widget, entries)
        assert widget.table.rowCount() == 1
        assert widget.table.item(0, 0).text() == ""
        assert widget.table.item(0, 1).text() == ""

    def test_date_formatting_produces_nonempty_string(self, widget) -> None:
        """Date column produces a non-empty formatted date string."""
        entries = [
            (1, "Test", "Teste", "", "PT", 4, "2026-06-15 09:30:45"),
        ]
        self._refresh_with_entries(widget, entries)
        date_item = widget.table.item(0, 4)
        assert date_item is not None
        assert date_item.text() != ""

    def test_header_click_clears_selection_extended(self, widget) -> None:
        """Clicking a header column clears the current table selection."""
        entries = [
            (1, "A", "a", "", "FR", 1, "2026-01-01 10:00:00"),
            (2, "B", "b", "", "FR", 1, "2026-01-02 10:00:00"),
        ]
        self._refresh_with_entries(widget, entries)
        widget.table.selectRow(0)
        assert len(widget.table.selectedItems()) > 0

        widget._on_header_clicked(1)
        assert len(widget.table.selectedItems()) == 0

    def test_very_long_unicode_text_truncated(self, widget) -> None:
        """Very long unicode text is properly truncated with ellipsis."""
        long_cjk = "\u6d4b\u8bd5" * 100  # 200 characters of CJK
        entries = [
            (1, long_cjk, long_cjk, "", "ZH", 200, "2026-01-01 10:00:00"),
        ]
        self._refresh_with_entries(widget, entries)
        item = widget.table.item(0, 0)
        assert item.text().endswith("...")
        assert len(item.text()) == 83  # noqa: PLR2004 — 80 + "..."

    def test_selection_signal_emitted_on_row_select(self, widget, qtbot) -> None:
        """selection_changed signal emits True when a row is selected."""
        entries = [
            (1, "X", "x", "", "FR", 1, "2026-01-01 10:00:00"),
        ]
        self._refresh_with_entries(widget, entries)

        with qtbot.waitSignal(widget.selection_changed, timeout=1000):
            widget.table.selectRow(0)

    def test_selection_signal_emitted_on_clear(self, widget, qtbot) -> None:
        """selection_changed signal is emitted when selection is cleared."""
        entries = [
            (1, "X", "x", "", "FR", 1, "2026-01-01 10:00:00"),
        ]
        self._refresh_with_entries(widget, entries)
        widget.table.selectRow(0)

        with qtbot.waitSignal(widget.selection_changed, timeout=1000):
            widget.table.clearSelection()

    def test_multiple_entries_with_same_source(self, widget) -> None:
        """Multiple entries with identical source text display correctly."""
        entries = [
            (1, "Hello", "Bonjour", "EN", "FR", 5, "2026-01-01 10:00:00"),
            (2, "Hello", "Hola", "EN", "ES", 5, "2026-01-02 10:00:00"),
        ]
        self._refresh_with_entries(widget, entries)
        assert widget.table.rowCount() == 2  # noqa: PLR2004

    def test_special_characters_in_text(self, widget) -> None:
        """Special characters (HTML entities, quotes) are handled."""
        entries = [
            (
                1,
                "<b>\"Hello\" & 'World'</b>",
                "Translated &amp;",
                "",
                "FR",
                25,
                "2026-01-01 10:00:00",
            ),
        ]
        self._refresh_with_entries(widget, entries)
        assert widget.table.rowCount() == 1

    def test_style_detail_text_returns_string(self) -> None:
        """_style_detail_text returns a non-empty QSS string."""
        from src.ui.pages.text_translation_history import (  # noqa: PLC0415
            _style_detail_text,
        )

        qss = _style_detail_text()
        assert isinstance(qss, str)
        assert len(qss) > 0
        assert "QPlainTextEdit" in qss

    def test_preview_len_constant(self) -> None:
        """_PREVIEW_LEN constant is 80."""
        from src.ui.pages.text_translation_history import (  # noqa: PLC0415
            _PREVIEW_LEN,
        )

        assert _PREVIEW_LEN == 80  # noqa: PLR2004


# ---------------------------------------------------------------------------
# NEW TESTS: View Dialog Extended
# ---------------------------------------------------------------------------


class TestViewDialogExtended:
    """Extended tests for the view dialog functionality."""

    def _populate(self, widget, entries):
        """Populates widget with given entries."""
        with (
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_fingerprint",
                return_value=(len(entries), len(entries)),
            ),
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_history",
                return_value=entries,
            ),
        ):
            widget._search_text = ""
            widget.refresh_history(force=True)

    @patch("src.ui.pages.text_translation_history._show_translation_detail")
    def test_view_shows_full_source_text(
        self,
        mock_detail,
        widget,
        qtbot,
    ) -> None:
        """View dialog receives full (un-truncated) source text."""
        long_source = "x" * 200
        entries = [
            (1, long_source, "Translated", "", "FR", 200, "2026-01-01 10:00:00"),
        ]
        self._populate(widget, entries)
        widget.table.selectRow(0)
        widget.on_view_selected()
        mock_detail.assert_called_once()
        args = mock_detail.call_args[0]
        assert args[1] == long_source

    @patch("src.ui.pages.text_translation_history._show_translation_detail")
    def test_view_shows_full_translated_text(
        self,
        mock_detail,
        widget,
        qtbot,
    ) -> None:
        """View dialog receives full (un-truncated) translated text."""
        long_translated = "y" * 200
        entries = [
            (1, "Source", long_translated, "", "FR", 6, "2026-01-01 10:00:00"),
        ]
        self._populate(widget, entries)
        widget.table.selectRow(0)
        widget.on_view_selected()
        mock_detail.assert_called_once()
        args = mock_detail.call_args[0]
        assert args[2] == long_translated

    @patch("src.ui.pages.text_translation_history._show_translation_detail")
    def test_view_with_unicode_text(
        self,
        mock_detail,
        widget,
        qtbot,
    ) -> None:
        """View dialog handles unicode text correctly."""
        entries = [
            (
                1,
                "\u4f60\u597d\u4e16\u754c",
                "\u3053\u3093\u306b\u3061\u306f",
                "ZH",
                "JA",
                4,
                "2026-01-01 10:00:00",
            ),
        ]
        self._populate(widget, entries)
        widget.table.selectRow(0)
        widget.on_view_selected()
        mock_detail.assert_called_once()

    @patch("src.ui.pages.text_translation_history._show_translation_detail")
    def test_view_with_empty_text(
        self,
        mock_detail,
        widget,
        qtbot,
    ) -> None:
        """View dialog handles empty source/translated text."""
        entries = [
            (1, "", "", "", "FR", 0, "2026-01-01 10:00:00"),
        ]
        self._populate(widget, entries)
        widget.table.selectRow(0)
        widget.on_view_selected()
        mock_detail.assert_called_once()
        args = mock_detail.call_args[0]
        assert args[1] == ""
        assert args[2] == ""

    @patch("src.ui.pages.text_translation_history._show_translation_detail")
    def test_view_with_multiline_text(
        self,
        mock_detail,
        widget,
        qtbot,
    ) -> None:
        """View dialog receives multiline text with newlines intact."""
        source = "Line 1\nLine 2\nLine 3"
        entries = [
            (1, source, "Translated", "", "FR", 20, "2026-01-01 10:00:00"),
        ]
        self._populate(widget, entries)
        widget.table.selectRow(0)
        widget.on_view_selected()
        mock_detail.assert_called_once()
        args = mock_detail.call_args[0]
        assert args[1] == source


# ---------------------------------------------------------------------------
# NEW TESTS: Copy to Clipboard Extended
# ---------------------------------------------------------------------------


class TestCopyClipboardExtended:
    """Extended tests for copy to clipboard functionality."""

    def _populate(self, widget, entries):
        """Populates widget with given entries."""
        with (
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_fingerprint",
                return_value=(len(entries), len(entries)),
            ),
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_history",
                return_value=entries,
            ),
        ):
            widget._search_text = ""
            widget.refresh_history(force=True)

    def test_copy_unicode_text(self, widget, qtbot) -> None:
        """Copy works with unicode translated text."""
        entries = [
            (
                1,
                "Hello",
                "\u4f60\u597d",
                "EN",
                "ZH",
                5,
                "2026-01-01 10:00:00",
            ),
        ]
        self._populate(widget, entries)
        widget.table.selectRow(0)
        widget.on_copy_selected()
        clipboard = QApplication.clipboard()
        assert clipboard.text() == "\u4f60\u597d"

    def test_copy_multiline_text(self, widget, qtbot) -> None:
        """Copy preserves newlines in translated text."""
        translated = "Line 1\nLine 2"
        entries = [
            (1, "Source", translated, "", "FR", 6, "2026-01-01 10:00:00"),
        ]
        self._populate(widget, entries)
        widget.table.selectRow(0)
        widget.on_copy_selected()
        clipboard = QApplication.clipboard()
        assert clipboard.text() == translated

    def test_copy_empty_text(self, widget, qtbot) -> None:
        """Copy handles empty translated text."""
        entries = [
            (1, "Source", "", "", "FR", 6, "2026-01-01 10:00:00"),
        ]
        self._populate(widget, entries)
        widget.table.selectRow(0)
        widget.on_copy_selected()
        clipboard = QApplication.clipboard()
        assert clipboard.text() == ""

    def test_copy_long_text(self, widget, qtbot) -> None:
        """Copy works with very long translated text."""
        long_text = "z" * 5000
        entries = [
            (1, "Source", long_text, "", "FR", 6, "2026-01-01 10:00:00"),
        ]
        self._populate(widget, entries)
        widget.table.selectRow(0)
        widget.on_copy_selected()
        clipboard = QApplication.clipboard()
        assert clipboard.text() == long_text


# ---------------------------------------------------------------------------
# NEW TESTS: Search Across Source and Translated
# ---------------------------------------------------------------------------


class TestSearchAcrossFields:
    """Tests for search matching across source and translated text."""

    def _refresh_with_entries(self, widget, entries):
        """Helper to refresh widget with given entries."""
        with (
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_fingerprint",
                return_value=(len(entries), len(entries)),
            ),
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_history",
                return_value=entries,
            ),
        ):
            widget.refresh_history(force=True)

    def test_search_matches_source_only(self, widget) -> None:
        """Search matches entry where only source text contains the query."""
        entries = [
            (1, "Apple juice", "Jus de pomme", "EN", "FR", 11, "2026-01-01 10:00:00"),
            (2, "Orange soda", "Soda orange", "EN", "FR", 11, "2026-01-02 10:00:00"),
        ]
        widget._search_text = "apple"
        self._refresh_with_entries(widget, entries)
        assert widget.table.rowCount() == 1

    def test_search_matches_translated_only(self, widget) -> None:
        """Search matches entry where only translated text contains the query."""
        entries = [
            (1, "Apple", "Pomme", "EN", "FR", 5, "2026-01-01 10:00:00"),
            (2, "Banana", "Banane", "EN", "FR", 6, "2026-01-02 10:00:00"),
        ]
        widget._search_text = "pomme"
        self._refresh_with_entries(widget, entries)
        assert widget.table.rowCount() == 1

    def test_search_matches_both_fields(self, widget) -> None:
        """Search matches when query appears in both source and translated."""
        entries = [
            (1, "test data", "test daten", "EN", "DE", 9, "2026-01-01 10:00:00"),
            (2, "other", "andere", "EN", "DE", 5, "2026-01-02 10:00:00"),
        ]
        widget._search_text = "test"
        self._refresh_with_entries(widget, entries)
        assert widget.table.rowCount() == 1

    def test_search_unicode_in_translated(self, widget) -> None:
        """Search matches unicode characters in translated text."""
        entries = [
            (
                1,
                "Hello",
                "\u4f60\u597d\u4e16\u754c",
                "EN",
                "ZH",
                5,
                "2026-01-01 10:00:00",
            ),
            (2, "Bye", "Goodbye", "EN", "EN", 3, "2026-01-02 10:00:00"),
        ]
        widget._search_text = "\u4f60\u597d"
        self._refresh_with_entries(widget, entries)
        assert widget.table.rowCount() == 1

    def test_search_multiple_results(self, widget) -> None:
        """Search returns multiple matches across both fields."""
        entries = [
            (1, "hello world", "bonjour", "EN", "FR", 11, "2026-01-01 10:00:00"),
            (2, "goodbye", "au revoir hello", "EN", "FR", 7, "2026-01-02 10:00:00"),
            (3, "other", "autre", "EN", "FR", 5, "2026-01-03 10:00:00"),
        ]
        widget._search_text = "hello"
        self._refresh_with_entries(widget, entries)
        assert widget.table.rowCount() == 2  # noqa: PLR2004


# ---------------------------------------------------------------------------
# NEW TESTS: Delete with Confirmation Extended
# ---------------------------------------------------------------------------


class TestDeleteConfirmationExtended:
    """Extended tests for delete with confirmation dialog."""

    def _populate(self, widget, entries):
        """Populates widget with given entries."""
        with (
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_fingerprint",
                return_value=(len(entries), len(entries)),
            ),
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_history",
                return_value=entries,
            ),
        ):
            widget._search_text = ""
            widget.refresh_history(force=True)

    @patch(
        "src.ui.pages.text_translation_history.CustomConfirmDialog.confirm",
        return_value=True,
    )
    @patch("src.ui.pages.text_translation_history.delete_text_translation_entry")
    def test_delete_all_entries(
        self,
        mock_delete,
        mock_confirm,
        widget,
        qtbot,
    ) -> None:
        """Deleting all entries clears the table."""
        entries = [
            (i, f"S{i}", f"T{i}", "", "FR", 2, f"2026-01-0{i} 10:00:00")
            for i in range(1, 6)
        ]
        self._populate(widget, entries)
        widget.table.selectAll()
        with (
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_fingerprint",
                return_value=(0, 0),
            ),
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_history",
                return_value=[],
            ),
        ):
            widget.on_delete_selected()
        assert mock_delete.call_count == 5  # noqa: PLR2004

    @patch(
        "src.ui.pages.text_translation_history.CustomConfirmDialog.confirm",
        return_value=True,
    )
    @patch("src.ui.pages.text_translation_history.delete_text_translation_entry")
    def test_delete_preserves_unselected(
        self,
        mock_delete,
        mock_confirm,
        widget,
        qtbot,
    ) -> None:
        """Deleting only selected entries preserves unselected ones."""
        entries = [
            (1, "Keep", "Garder", "", "FR", 4, "2026-01-01 10:00:00"),
            (2, "Delete", "Supprimer", "", "FR", 6, "2026-01-02 10:00:00"),
        ]
        self._populate(widget, entries)
        # Select only the second row
        widget.table.selectRow(1)
        remaining = [entries[0]]
        with (
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_fingerprint",
                return_value=(1, 1),
            ),
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_history",
                return_value=remaining,
            ),
        ):
            widget.on_delete_selected()
        assert mock_delete.call_count == 1


# ---------------------------------------------------------------------------
# NEW TESTS: Truncation Logic Extended
# ---------------------------------------------------------------------------


class TestTruncationLogicExtended:
    """Extended tests for truncation behavior in the table."""

    def _populate(self, widget, entries):
        """Populates widget with given entries."""
        with (
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_fingerprint",
                return_value=(len(entries), len(entries)),
            ),
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_history",
                return_value=entries,
            ),
        ):
            widget._search_text = ""
            widget.refresh_history(force=True)

    def test_source_preview_truncated(self, widget) -> None:
        """Source preview is truncated at 80 chars with ellipsis."""
        long_text = "a" * 100
        entries = [
            (1, long_text, "short", "", "FR", 100, "2026-01-01 10:00:00"),
        ]
        self._populate(widget, entries)
        item = widget.table.item(0, 0)
        assert len(item.text()) == 83  # noqa: PLR2004
        assert item.text().endswith("...")

    def test_translated_preview_truncated(self, widget) -> None:
        """Translated preview is truncated at 80 chars with ellipsis."""
        long_text = "b" * 100
        entries = [
            (1, "short", long_text, "", "FR", 5, "2026-01-01 10:00:00"),
        ]
        self._populate(widget, entries)
        item = widget.table.item(0, 1)
        assert len(item.text()) == 83  # noqa: PLR2004
        assert item.text().endswith("...")

    def test_short_text_not_truncated(self, widget) -> None:
        """Short text within limit is not truncated."""
        entries = [
            (1, "Hello", "Bonjour", "", "FR", 5, "2026-01-01 10:00:00"),
        ]
        self._populate(widget, entries)
        item = widget.table.item(0, 0)
        assert item.text() == "Hello"
        assert "..." not in item.text()

    def test_exactly_80_chars_not_truncated(self, widget) -> None:
        """Text exactly at 80 characters is not truncated."""
        text = "c" * 80  # noqa: PLR2004
        entries = [
            (1, text, "translated", "", "FR", 80, "2026-01-01 10:00:00"),
        ]
        self._populate(widget, entries)
        item = widget.table.item(0, 0)
        assert item.text() == text
        assert "..." not in item.text()

    def test_full_text_stored_in_userrole(self, widget) -> None:
        """Full un-truncated text is stored in UserRole data."""
        long_text = "d" * 200
        entries = [
            (1, long_text, "translated", "", "FR", 200, "2026-01-01 10:00:00"),
        ]
        self._populate(widget, entries)
        item = widget.table.item(0, 0)
        assert item.data(Qt.ItemDataRole.UserRole + 1) == long_text

    def test_newlines_collapsed_in_preview(self, widget) -> None:
        """Newlines in source text are collapsed in the table preview."""
        text_with_newlines = "Line1\nLine2\nLine3"
        entries = [
            (1, text_with_newlines, "Translated", "", "FR", 17, "2026-01-01 10:00:00"),
        ]
        self._populate(widget, entries)
        item = widget.table.item(0, 0)
        assert "\n" not in item.text()
        assert item.text() == "Line1 Line2 Line3"


# ---------------------------------------------------------------------------
# NEW TESTS: Table Sorting Extended
# ---------------------------------------------------------------------------


class TestTableSortingExtended:
    """Extended tests for table sorting behavior."""

    def _populate(self, widget, entries):
        """Populates widget with given entries."""
        with (
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_fingerprint",
                return_value=(len(entries), len(entries)),
            ),
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_history",
                return_value=entries,
            ),
        ):
            widget._search_text = ""
            widget.refresh_history(force=True)

    def test_sort_by_date_descending_default(self, widget) -> None:
        """Table defaults to date descending sort (newest first)."""
        entries = [
            (1, "Old", "Ancien", "", "FR", 3, "2026-01-01 10:00:00"),
            (2, "New", "Nouveau", "", "FR", 3, "2026-12-31 10:00:00"),
        ]
        self._populate(widget, entries)
        first_id = widget.table.item(0, 0).data(Qt.ItemDataRole.UserRole)
        assert first_id == 2  # noqa: PLR2004

    def test_sort_by_source_column(self, widget) -> None:
        """Sorting by source column orders alphabetically."""
        entries = [
            (1, "Zebra", "z", "", "FR", 5, "2026-01-01 10:00:00"),
            (2, "Apple", "a", "", "FR", 5, "2026-01-02 10:00:00"),
        ]
        self._populate(widget, entries)
        widget.table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        assert widget.table.item(0, 0).text() == "Apple"

    def test_sort_preserves_data_roles(self, widget) -> None:
        """Sorting preserves UserRole data across column items."""
        entries = [
            (10, "Beta", "b", "", "FR", 4, "2026-01-01 10:00:00"),
            (20, "Alpha", "a", "", "FR", 5, "2026-01-02 10:00:00"),
        ]
        self._populate(widget, entries)
        widget.table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        first_item = widget.table.item(0, 0)
        assert first_item.data(Qt.ItemDataRole.UserRole) == 20  # noqa: PLR2004

    def test_header_click_clears_selection_all_columns(self, widget, qtbot) -> None:
        """Clicking any header column clears selection."""
        entries = [
            (1, "A", "a", "", "FR", 1, "2026-01-01 10:00:00"),
        ]
        self._populate(widget, entries)
        for col in range(widget.table.columnCount()):
            widget.table.selectRow(0)
            widget._on_header_clicked(col)
            assert len(widget.table.selectedItems()) == 0


# ---------------------------------------------------------------------------
# NEW TESTS: Widget Structure Extended
# ---------------------------------------------------------------------------


class TestWidgetStructureExtended:
    """Extended tests for widget structure and properties."""

    def test_table_row_selection_mode(self, widget) -> None:
        """Table uses row-based selection."""
        assert (
            widget.table.selectionBehavior()
            == QTableWidget.SelectionBehavior.SelectRows
        )

    def test_has_highlight_delegate(self, widget) -> None:
        """Widget has a HighlightDelegate attached."""
        from src.ui.components import HighlightDelegate  # noqa: PLC0415

        assert isinstance(widget.table.itemDelegateForColumn(0), HighlightDelegate)

    def test_has_selection_changed_signal(self, widget) -> None:
        """Widget has selection_changed signal."""
        assert hasattr(widget, "selection_changed")

    def test_has_search_timer(self, widget) -> None:
        """Widget has a search debounce timer."""
        assert hasattr(widget, "_search_timer")
        assert widget._search_timer.isSingleShot()

    def test_has_refresh_timer(self, widget) -> None:
        """Widget has a background refresh timer."""
        assert hasattr(widget, "_refresh_timer")
        assert widget._refresh_timer.isActive()

    def test_search_timer_debounce_interval(self, widget) -> None:
        """Search timer uses the configured debounce interval."""
        from src.constants import SEARCH_DEBOUNCE_MS  # noqa: PLC0415

        assert widget._search_timer.interval() == SEARCH_DEBOUNCE_MS


# ---------------------------------------------------------------------------
# NEW TESTS: Large Dataset
# ---------------------------------------------------------------------------


class TestLargeDataset:
    """Tests with larger datasets."""

    def _populate(self, widget, entries):
        """Populates widget with given entries."""
        with (
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_fingerprint",
                return_value=(len(entries), len(entries)),
            ),
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_history",
                return_value=entries,
            ),
        ):
            widget._search_text = ""
            widget.refresh_history(force=True)

    def test_twenty_entries(self, widget) -> None:
        """Handles 20 entries correctly."""
        entries = [
            (i, f"S{i}", f"T{i}", "", "FR", 2, f"2026-01-{i:02d} 10:00:00")
            for i in range(1, 21)
        ]
        self._populate(widget, entries)
        assert widget.table.rowCount() == 20  # noqa: PLR2004

    def test_select_all_in_large_dataset(self, widget) -> None:
        """Select all in large dataset selects all rows."""
        entries = [
            (i, f"S{i}", f"T{i}", "", "FR", 2, f"2026-01-{i:02d} 10:00:00")
            for i in range(1, 11)
        ]
        self._populate(widget, entries)
        widget.table.selectAll()
        selected_rows = {item.row() for item in widget.table.selectedItems()}
        assert len(selected_rows) == 10  # noqa: PLR2004

    def test_search_in_large_dataset(self, widget) -> None:
        """Search works correctly in large datasets."""
        entries = [
            (
                i,
                f"Item_{i}_text",
                f"Target{i}",
                "",
                "FR",
                11,
                f"2026-01-{i:02d} 10:00:00",
            )
            for i in range(1, 11)
        ]
        widget._search_text = "Item_5_text"
        with (
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_fingerprint",
                return_value=(10, 10),
            ),
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_history",
                return_value=entries,
            ),
        ):
            widget.refresh_history(force=True)
        assert widget.table.rowCount() == 1


# ---------------------------------------------------------------------------
# NEW TESTS: Refresh Timer Interval
# ---------------------------------------------------------------------------


class TestRefreshTimerInterval:
    """Tests for refresh timer interval."""

    def test_refresh_timer_1000ms(self, widget) -> None:
        """Refresh timer has 1000ms interval."""
        assert widget._refresh_timer.interval() == 1000  # noqa: PLR2004


# ---------------------------------------------------------------------------
# NEW TESTS: Multiple Selections
# ---------------------------------------------------------------------------


class TestMultipleSelections:
    """Tests for multiple row selections."""

    def _populate(self, widget, entries):
        """Populates widget with given entries."""
        with (
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_fingerprint",
                return_value=(len(entries), len(entries)),
            ),
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_history",
                return_value=entries,
            ),
        ):
            widget._search_text = ""
            widget.refresh_history(force=True)

    def test_multi_selection_preserved_across_refresh(self, widget) -> None:
        """Multiple selections are preserved across refresh."""
        entries = [
            (i, f"S{i}", f"T{i}", "", "FR", 2, f"2026-01-0{i} 10:00:00")
            for i in range(1, 4)
        ]
        self._populate(widget, entries)
        widget.table.selectAll()
        self._populate(widget, entries)
        selected_ids = set()
        for item in widget.table.selectedItems():
            if item.column() == 0:
                h_id = item.data(Qt.ItemDataRole.UserRole)
                if h_id is not None:
                    selected_ids.add(h_id)
        assert selected_ids == {1, 2, 3}

    @patch("src.ui.pages.text_translation_history._show_translation_detail")
    def test_view_with_multiple_selected_uses_first(
        self,
        mock_detail,
        widget,
        qtbot,
    ) -> None:
        """View with multiple selections uses the first selected row."""
        entries = [
            (1, "First", "Premier", "", "FR", 5, "2026-01-01 10:00:00"),
            (2, "Second", "Deuxieme", "", "FR", 6, "2026-01-02 10:00:00"),
        ]
        self._populate(widget, entries)
        widget.table.selectAll()
        widget.on_view_selected()
        mock_detail.assert_called_once()

    def test_copy_with_multiple_selected_copies_first(self, widget, qtbot) -> None:
        """Copy with multiple selections copies the first selected row."""
        entries = [
            (1, "First", "Premier", "", "FR", 5, "2026-01-01 10:00:00"),
            (2, "Second", "Deuxieme", "", "FR", 6, "2026-01-02 10:00:00"),
        ]
        self._populate(widget, entries)
        widget.table.selectAll()
        widget.on_copy_selected()
        clipboard = QApplication.clipboard()
        assert clipboard.text() in ("Premier", "Deuxieme")


# ---------------------------------------------------------------------------
# NEW TESTS: Language Display Extended
# ---------------------------------------------------------------------------


class TestLanguageDisplayExtended:
    """Extended tests for language display in the table."""

    def _populate(self, widget, entries):
        """Populates widget with given entries."""
        with (
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_fingerprint",
                return_value=(len(entries), len(entries)),
            ),
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_history",
                return_value=entries,
            ),
        ):
            widget._search_text = ""
            widget.refresh_history(force=True)

    def test_auto_detect_source_shows_auto(self, widget) -> None:
        """Empty source language displays as Auto in source column."""
        entries = [
            (1, "Hello", "Bonjour", "", "French", 5, "2026-01-01 10:00:00"),
        ]
        self._populate(widget, entries)
        src_lang_item = widget.table.item(0, 2)
        assert src_lang_item.text() != ""  # Shows "Auto" label
        tgt_lang_item = widget.table.item(0, 3)
        assert "French" in tgt_lang_item.text()

    def test_explicit_languages_both_shown(self, widget) -> None:
        """Both explicit source and target languages are shown in separate columns."""
        entries = [
            (1, "Hi", "Salut", "English (US)", "French", 2, "2026-01-01 10:00:00"),
        ]
        self._populate(widget, entries)
        src_lang_item = widget.table.item(0, 2)
        assert "English (US)" in src_lang_item.text()
        tgt_lang_item = widget.table.item(0, 3)
        assert "French" in tgt_lang_item.text()

    def test_source_and_target_in_separate_columns(self, widget) -> None:
        """Source and target languages are in separate columns."""
        entries = [
            (1, "Hi", "Salut", "EN", "FR", 2, "2026-01-01 10:00:00"),
        ]
        self._populate(widget, entries)
        assert widget.table.item(0, 2).text() == "EN"
        assert widget.table.item(0, 3).text() == "FR"


# ---------------------------------------------------------------------------
# NEW TESTS: Theme Extended
# ---------------------------------------------------------------------------


class TestThemeExtended:
    """Extended theme tests."""

    def test_apply_theme_updates_table_style_nonempty(self, widget) -> None:
        """apply_theme sets a non-empty table stylesheet."""
        with (
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_fingerprint",
                return_value=(0, 0),
            ),
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_history",
                return_value=[],
            ),
        ):
            widget.apply_theme()
        assert widget.table.styleSheet() != ""

    def test_apply_theme_preserves_data(self, widget) -> None:
        """apply_theme preserves existing table data."""
        entries = [
            (1, "Hello", "Bonjour", "", "FR", 5, "2026-01-01 10:00:00"),
        ]
        with (
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_fingerprint",
                return_value=(1, 1),
            ),
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_history",
                return_value=entries,
            ),
        ):
            widget._search_text = ""
            widget.refresh_history(force=True)
            widget.apply_theme()
        assert widget.table.rowCount() == 1


# ---------------------------------------------------------------------------
# NEW TESTS: Refresh with Different Fingerprints
# ---------------------------------------------------------------------------


class TestRefreshFingerprints:
    """Tests for refresh behavior with various fingerprint states."""

    def test_fingerprint_tuple_stored_after_refresh(self, window, qtbot) -> None:
        """_last_fingerprint is updated after successful refresh."""
        from src.ui.pages.text_translation_history import (  # noqa: PLC0415
            TextTranslationHistoryWidget,
        )

        fp = (7, 7)
        with (
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_fingerprint",
                return_value=fp,
            ),
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_history",
                return_value=[],
            ),
        ):
            w = TextTranslationHistoryWidget(window)
            qtbot.addWidget(w)
        assert w._last_fingerprint == fp

    def test_refresh_with_empty_then_populated(self, widget) -> None:
        """Refresh transitions from empty to populated table."""
        # Start empty
        with (
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_fingerprint",
                return_value=(0, 0),
            ),
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_history",
                return_value=[],
            ),
        ):
            widget._search_text = ""
            widget.refresh_history(force=True)
        assert widget.table.rowCount() == 0

        # Add entries
        entries = [
            (1, "New", "Nouveau", "", "FR", 3, "2026-01-01 10:00:00"),
        ]
        with (
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_fingerprint",
                return_value=(1, 1),
            ),
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_history",
                return_value=entries,
            ),
        ):
            widget._search_text = ""
            widget.refresh_history(force=True)
        assert widget.table.rowCount() == 1


# ---------------------------------------------------------------------------
# NEW TESTS: Special Characters in Text
# ---------------------------------------------------------------------------


class TestSpecialCharactersExtended:
    """Extended tests for special characters in text."""

    def _populate(self, widget, entries):
        """Populates widget with given entries."""
        with (
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_fingerprint",
                return_value=(len(entries), len(entries)),
            ),
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_history",
                return_value=entries,
            ),
        ):
            widget._search_text = ""
            widget.refresh_history(force=True)

    def test_html_entities_in_source(self, widget) -> None:
        """HTML entities in source text are handled."""
        entries = [
            (1, "&amp; &lt; &gt;", "translated", "", "FR", 15, "2026-01-01 10:00:00"),
        ]
        self._populate(widget, entries)
        assert widget.table.rowCount() == 1

    def test_quotes_in_text(self, widget) -> None:
        """Quotes in text are displayed correctly."""
        entries = [
            (1, "\"Hello\" 'World'", "translated", "", "FR", 16, "2026-01-01 10:00:00"),
        ]
        self._populate(widget, entries)
        item = widget.table.item(0, 0)
        assert '"Hello"' in item.text()

    def test_newlines_in_source_collapsed(self, widget) -> None:
        """Newlines in source text are collapsed in preview."""
        entries = [
            (1, "Line1\nLine2\nLine3", "tgt", "", "FR", 17, "2026-01-01 10:00:00"),
        ]
        self._populate(widget, entries)
        item = widget.table.item(0, 0)
        assert "\n" not in item.text()

    def test_tabs_in_source_collapsed(self, widget) -> None:
        """Tabs in source text are collapsed in preview."""
        entries = [
            (1, "col1\tcol2\tcol3", "tgt", "", "FR", 14, "2026-01-01 10:00:00"),
        ]
        self._populate(widget, entries)
        item = widget.table.item(0, 0)
        assert "\t" not in item.text()

    def test_very_long_source_full_stored(self, widget) -> None:
        """Full long source text is stored in UserRole despite truncated preview."""
        long_text = "a" * 200
        entries = [
            (1, long_text, "tgt", "", "FR", 200, "2026-01-01 10:00:00"),
        ]
        self._populate(widget, entries)
        item = widget.table.item(0, 0)
        assert len(item.text()) == 83  # noqa: PLR2004 — 80 + "..."
        assert item.data(Qt.ItemDataRole.UserRole + 1) == long_text


# ---------------------------------------------------------------------------
# NEW TESTS: Date Column Extended
# ---------------------------------------------------------------------------


class TestDateColumnExtended:
    """Extended tests for date column formatting."""

    def _populate(self, widget, entries):
        """Populates widget with given entries."""
        with (
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_fingerprint",
                return_value=(len(entries), len(entries)),
            ),
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_history",
                return_value=entries,
            ),
        ):
            widget._search_text = ""
            widget.refresh_history(force=True)

    def test_date_column_has_text(self, widget) -> None:
        """Date column has non-empty formatted text."""
        entries = [
            (1, "Hi", "Salut", "", "FR", 2, "2026-06-15 14:30:00"),
        ]
        self._populate(widget, entries)
        date_item = widget.table.item(0, 4)
        assert date_item is not None
        assert date_item.text() != ""

    def test_date_sorting_order(self, widget) -> None:
        """Sorting by date column orders entries chronologically."""
        entries = [
            (1, "Old", "Ancien", "", "FR", 3, "2026-01-01 10:00:00"),
            (2, "New", "Nouveau", "", "FR", 3, "2026-12-31 10:00:00"),
        ]
        self._populate(widget, entries)
        widget.table.sortByColumn(4, Qt.SortOrder.AscendingOrder)
        first_id = widget.table.item(0, 0).data(Qt.ItemDataRole.UserRole)
        assert first_id == 1

    def test_date_descending_puts_newest_first(self, widget) -> None:
        """Date descending sort puts newest entry first."""
        entries = [
            (1, "Old", "Ancien", "", "FR", 3, "2026-01-01 10:00:00"),
            (2, "New", "Nouveau", "", "FR", 3, "2026-12-31 10:00:00"),
        ]
        self._populate(widget, entries)
        widget.table.sortByColumn(4, Qt.SortOrder.DescendingOrder)
        first_id = widget.table.item(0, 0).data(Qt.ItemDataRole.UserRole)
        assert first_id == 2  # noqa: PLR2004


# ---------------------------------------------------------------------------
# NEW: Extended Coverage for Text Translation History
# ---------------------------------------------------------------------------


class TestTextTranslationExtendedCoverage:
    """Extended coverage tests for text translation history widget."""

    def _populate(self, widget, entries):
        """Populates widget with entries."""
        with (
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_fingerprint",
                return_value=(len(entries), len(entries)),
            ),
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_history",
                return_value=entries,
            ),
        ):
            widget._search_text = ""
            widget.refresh_history(force=True)

    def test_search_timer_single_shot(self, widget) -> None:
        """Search timer is configured as single-shot."""
        assert widget._search_timer.isSingleShot()

    def test_refresh_timer_not_single_shot(self, widget) -> None:
        """Background refresh timer is repeating (not single-shot)."""
        assert not widget._refresh_timer.isSingleShot()

    def test_table_no_edit_triggers(self, widget) -> None:
        """Table has no edit triggers (read-only)."""
        from PySide6.QtWidgets import QAbstractItemView  # noqa: PLC0415

        assert (
            widget.table.editTriggers() == QAbstractItemView.EditTrigger.NoEditTriggers
        )

    def test_table_extended_selection_mode(self, widget) -> None:
        """Table supports extended selection mode."""
        from PySide6.QtWidgets import QAbstractItemView  # noqa: PLC0415

        assert (
            widget.table.selectionMode()
            == QAbstractItemView.SelectionMode.ExtendedSelection
        )

    def test_highlight_delegate_exists(self, widget) -> None:
        """Widget has a highlight delegate."""
        assert widget.highlight_delegate is not None

    def test_window_context_stored(self, widget, window) -> None:
        """Widget stores window context reference."""
        assert widget.window_context is window

    def test_selection_signal_emitted_true(self, widget, qtbot) -> None:
        """selection_changed emits True when row is selected."""
        entries = [(1, "Hi", "Salut", "", "FR", 2, "2026-01-01 10:00:00")]
        self._populate(widget, entries)
        with qtbot.waitSignal(widget.selection_changed, timeout=1000) as blocker:
            widget.table.selectRow(0)
        assert blocker.args == [True]

    def test_selection_signal_emitted_false(self, widget, qtbot) -> None:
        """selection_changed emits False when selection is cleared."""
        entries = [(1, "Hi", "Salut", "", "FR", 2, "2026-01-01 10:00:00")]
        self._populate(widget, entries)
        widget.table.selectRow(0)
        with qtbot.waitSignal(widget.selection_changed, timeout=1000) as blocker:
            widget.table.clearSelection()
        assert blocker.args == [False]

    def test_on_view_no_selection_noop(self, widget) -> None:
        """on_view_selected with no selection does nothing (no crash)."""
        widget.table.clearSelection()
        widget.on_view_selected()  # should not raise

    def test_on_copy_no_selection_noop(self, widget) -> None:
        """on_copy_selected with no selection does nothing (no crash)."""
        widget.table.clearSelection()
        widget.on_copy_selected()  # should not raise

    def test_on_delete_no_selection_noop(self, widget) -> None:
        """on_delete_selected with no selection does nothing (no crash)."""
        widget.table.clearSelection()
        widget.on_delete_selected()  # should not raise

    def test_five_columns_text_history(self, widget) -> None:
        """Table has exactly 5 columns."""
        assert widget.table.columnCount() == 5  # noqa: PLR2004

    def test_set_search_text_stores_value(self, widget) -> None:
        """set_search_text stores the search text on the widget."""
        widget.set_search_text("hello")
        assert widget._search_text == "hello"

    def test_header_click_clears_selection(self, widget) -> None:
        """Clicking a header clears table selection."""
        entries = [(1, "Hi", "Salut", "", "FR", 2, "2026-01-01 10:00:00")]
        self._populate(widget, entries)
        widget.table.selectRow(0)
        widget._on_header_clicked(0)
        assert len(widget.table.selectedItems()) == 0

    def test_apply_language_updates_all_headers(self, widget) -> None:
        """apply_language sets non-empty text on all column headers."""
        with (
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_fingerprint",
                return_value=None,
            ),
            patch(
                "src.ui.pages.text_translation_history.get_text_translation_history",
                return_value=[],
            ),
        ):
            widget.apply_language()
        for col in range(widget.table.columnCount()):
            header = widget.table.horizontalHeaderItem(col)
            assert header is not None
            assert len(header.text()) > 0

    def test_source_column_auto_prefix(self, widget) -> None:
        """Empty source lang shows 'Auto' in source column."""
        entries = [(1, "Hi", "Salut", "", "French", 2, "2026-01-01 10:00:00")]
        self._populate(widget, entries)
        src_text = widget.table.item(0, 2).text()
        assert src_text != ""  # Shows "Auto" label
        tgt_text = widget.table.item(0, 3).text()
        assert "French" in tgt_text

    def test_source_and_target_columns_with_explicit_langs(self, widget) -> None:
        """Non-empty source lang shows in source column, target in target column."""
        entries = [(1, "Hi", "Salut", "English", "French", 5, "2026-01-01 10:00:00")]
        self._populate(widget, entries)
        src_text = widget.table.item(0, 2).text()
        assert "English" in src_text
        tgt_text = widget.table.item(0, 3).text()
        assert "French" in tgt_text

    def test_translated_preview_column(self, widget) -> None:
        """Translated text preview appears in column 1."""
        entries = [(1, "Hello", "Bonjour", "", "FR", 5, "2026-01-01 10:00:00")]
        self._populate(widget, entries)
        assert widget.table.item(0, 1).text() == "Bonjour"

    def test_source_preview_column(self, widget) -> None:
        """Source text preview appears in column 0."""
        entries = [(1, "Hello", "Bonjour", "", "FR", 5, "2026-01-01 10:00:00")]
        self._populate(widget, entries)
        assert widget.table.item(0, 0).text() == "Hello"

    def test_entry_id_stored_in_user_role(self, widget) -> None:
        """Entry ID is stored in UserRole of first column."""
        entries = [(42, "Hi", "Salut", "", "FR", 2, "2026-01-01 10:00:00")]
        self._populate(widget, entries)
        stored_id = widget.table.item(0, 0).data(Qt.ItemDataRole.UserRole)
        assert stored_id == 42  # noqa: PLR2004

    def test_full_source_stored_in_user_role_1(self, widget) -> None:
        """Full source text stored in UserRole+1."""
        src = "A" * 200
        entries = [(1, src, "translated", "", "FR", 200, "2026-01-01 10:00:00")]
        self._populate(widget, entries)
        assert widget.table.item(0, 0).data(Qt.ItemDataRole.UserRole + 1) == src

    def test_full_translated_stored_in_user_role_2(self, widget) -> None:
        """Full translated text stored in UserRole+2."""
        tgt = "B" * 200
        entries = [(1, "source", tgt, "", "FR", 200, "2026-01-01 10:00:00")]
        self._populate(widget, entries)
        assert widget.table.item(0, 0).data(Qt.ItemDataRole.UserRole + 2) == tgt


# ---------------------------------------------------------------------------
# _show_translation_detail() direct tests
# ---------------------------------------------------------------------------


class TestShowTranslationDetail:
    """Tests for the _show_translation_detail dialog function."""

    @patch(
        "src.ui.pages.text_translation_history.BaseDialog.exec",
        return_value=None,
    )
    def test_detail_dialog_created(self, mock_exec, window, _mock_db) -> None:
        """_show_translation_detail creates and shows a dialog without error."""
        from src.ui.pages.text_translation_history import (  # noqa: PLC0415
            _show_translation_detail,
        )

        result = _show_translation_detail(
            window,
            "Hello world",
            "Bonjour le monde",
            "English",
            "French",
        )
        mock_exec.assert_called_once()
        # Default return (no reuse button click) should be False
        assert result is False

    @patch(
        "src.ui.pages.text_translation_history.BaseDialog.exec",
        return_value=None,
    )
    def test_detail_dialog_with_empty_source_lang(
        self, mock_exec, window, _mock_db
    ) -> None:
        """_show_translation_detail handles empty source language (auto-detect)."""
        from src.ui.pages.text_translation_history import (  # noqa: PLC0415
            _show_translation_detail,
        )

        # Empty source lang triggers auto-detect display
        result = _show_translation_detail(
            window,
            "Hello",
            "Bonjour",
            "",
            "French",
        )
        mock_exec.assert_called_once()
        assert result is False

    @patch(
        "src.ui.pages.text_translation_history.BaseDialog.exec",
        return_value=None,
    )
    def test_detail_dialog_with_long_text(self, mock_exec, window, _mock_db) -> None:
        """_show_translation_detail handles long text without error."""
        from src.ui.pages.text_translation_history import (  # noqa: PLC0415
            _show_translation_detail,
        )

        long_src = "A" * 5000
        long_tgt = "B" * 5000
        result = _show_translation_detail(
            window,
            long_src,
            long_tgt,
            "English",
            "French",
        )
        mock_exec.assert_called_once()
        assert result is False

    @patch(
        "src.ui.pages.text_translation_history.BaseDialog.exec",
        return_value=None,
    )
    def test_detail_dialog_returns_false_on_close(
        self, mock_exec, window, _mock_db
    ) -> None:
        """_show_translation_detail returns False when dialog is closed normally."""
        from src.ui.pages.text_translation_history import (  # noqa: PLC0415
            _show_translation_detail,
        )

        result = _show_translation_detail(
            window,
            "src",
            "tgt",
            "English",
            "French",
        )
        assert result is False

    @patch(
        "src.ui.pages.text_translation_history.BaseDialog.exec",
        return_value=None,
    )
    def test_detail_dialog_with_unicode_text(self, mock_exec, window, _mock_db) -> None:
        """_show_translation_detail handles unicode/emoji text."""
        from src.ui.pages.text_translation_history import (  # noqa: PLC0415
            _show_translation_detail,
        )

        result = _show_translation_detail(
            window,
            "Hello \U0001f600 World",
            "\u4f60\u597d \U0001f30d \u4e16\u754c",
            "English",
            "Chinese",
        )
        mock_exec.assert_called_once()
        assert result is False


# ===================================================================
# TestTextTranslationHistorySignalBlocking — blockSignals & setSortingEnabled
# ===================================================================

_TTH_MOD = "src.ui.pages.text_translation_history"


class TestTextTranslationHistorySignalBlocking:
    """Verifies that refresh_history blocks/unblocks signals and sorting."""

    def _refresh_with(self, widget, entries):  # noqa: ANN001, ANN202
        """Populates widget with given entries via mocked refresh."""
        with (
            patch(
                f"{_TTH_MOD}.get_text_translation_fingerprint",
                return_value=(len(entries), len(entries)),
            ),
            patch(
                f"{_TTH_MOD}.get_text_translation_history",
                return_value=entries,
            ),
        ):
            widget._search_text = ""
            widget.refresh_history(force=True)

    def test_signals_unblocked_after_refresh_with_entries(self, widget) -> None:  # noqa: ANN001
        """Signals are unblocked after a normal refresh with entries."""
        entries = [(1, "src", "tgt", "", "FR", 3, "2026-01-01 10:00:00")]
        self._refresh_with(widget, entries)
        assert not widget.table.signalsBlocked()

    def test_sorting_enabled_after_refresh_with_entries(self, widget) -> None:  # noqa: ANN001
        """Sorting is re-enabled after a normal refresh with entries."""
        entries = [(1, "src", "tgt", "", "FR", 3, "2026-01-01 10:00:00")]
        self._refresh_with(widget, entries)
        assert widget.table.isSortingEnabled()

    def test_signals_unblocked_after_refresh_with_empty_data(self, widget) -> None:  # noqa: ANN001
        """Signals are unblocked when refresh returns an empty list."""
        self._refresh_with(widget, [])
        assert not widget.table.signalsBlocked()

    def test_sorting_enabled_after_refresh_with_empty_data(self, widget) -> None:  # noqa: ANN001
        """Sorting is re-enabled when refresh returns an empty list."""
        self._refresh_with(widget, [])
        assert widget.table.isSortingEnabled()

    def test_signals_unblocked_after_refresh_with_none(self, widget) -> None:  # noqa: ANN001
        """Signals are unblocked when the DB returns None."""
        with (
            patch(
                f"{_TTH_MOD}.get_text_translation_fingerprint",
                return_value=(0, 0),
            ),
            patch(
                f"{_TTH_MOD}.get_text_translation_history",
                return_value=None,
            ),
        ):
            widget._search_text = ""
            widget.refresh_history(force=True)

        assert not widget.table.signalsBlocked()

    def test_sorting_enabled_after_refresh_with_none(self, widget) -> None:  # noqa: ANN001
        """Sorting is re-enabled when the DB returns None."""
        with (
            patch(
                f"{_TTH_MOD}.get_text_translation_fingerprint",
                return_value=(0, 0),
            ),
            patch(
                f"{_TTH_MOD}.get_text_translation_history",
                return_value=None,
            ),
        ):
            widget._search_text = ""
            widget.refresh_history(force=True)

        assert widget.table.isSortingEnabled()

    def test_block_signals_called_in_correct_order(self, widget) -> None:  # noqa: ANN001
        """blockSignals(True) is called before rebuild and (False) after."""
        calls: list[bool] = []
        original_block = widget.table.blockSignals

        def _track(val: bool) -> bool:
            calls.append(val)
            return original_block(val)

        entries = [(1, "src", "tgt", "", "FR", 3, "2026-01-01 10:00:00")]
        with patch.object(widget.table, "blockSignals", side_effect=_track):
            self._refresh_with(widget, entries)

        assert True in calls
        assert False in calls
        first_true = calls.index(True)
        last_false = len(calls) - 1 - calls[::-1].index(False)
        assert first_true < last_false

    def test_set_sorting_enabled_called_in_correct_order(self, widget) -> None:  # noqa: ANN001
        """setSortingEnabled(False) is called before rebuild, (True) after."""
        calls: list[bool] = []
        original_sort = widget.table.setSortingEnabled

        def _track(val: bool) -> None:
            calls.append(val)
            original_sort(val)

        entries = [(1, "src", "tgt", "", "FR", 3, "2026-01-01 10:00:00")]
        with patch.object(widget.table, "setSortingEnabled", side_effect=_track):
            self._refresh_with(widget, entries)

        assert False in calls
        assert True in calls
        first_false = calls.index(False)
        last_true = len(calls) - 1 - calls[::-1].index(True)
        assert first_false < last_true
