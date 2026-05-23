"""Comprehensive tests for VoiceHistoryPage.

Covers page creation, widget structure, refresh_history, _fill_row,
_on_header_clicked, on_open_file, on_delete_selected, on_re_generate,
_update_button_states, apply_theme, apply_language, search filtering,
selection preservation, fingerprint checking, and edge cases.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableWidget

# ---------------------------------------------------------------------------
# Module-level patch path constants
# ---------------------------------------------------------------------------
_MOD = "src.ui.pages.voice_history"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def _mock_db():
    """Mocks database calls used by VoiceHistoryPage during construction."""
    with (
        patch(f"{_MOD}.get_voice_fingerprint", return_value=None),
        patch(f"{_MOD}.get_voice_history", return_value=[]),
    ):
        yield


@pytest.fixture()
def page(_mock_db, qtbot):
    """Creates a VoiceHistoryPage widget for testing."""
    from src.ui.pages.voice_history import VoiceHistoryPage  # noqa: PLC0415

    p = VoiceHistoryPage()
    qtbot.addWidget(p)
    return p


def _make_entry(  # noqa: PLR0913
    entry_id: int = 1,
    name: str = "speech.srt",
    file_size: int = 4096,
    source_path: str = "/tmp/source/speech.srt",
    output_path: str = "/tmp/output/speech.mp3",
    status: str = "Done",
    error_message: str | None = None,
    created_at: str = "2026-03-05 09:15:00",
) -> tuple:
    """Helper to build a voice history DB tuple."""
    return (
        entry_id,
        name,
        file_size,
        source_path,
        output_path,
        status,
        error_message,
        created_at,
    )


def _populate_table(page, entries):  # noqa: ANN001, ANN202
    """Populates the page table with the given entries via mocked refresh."""
    with (
        patch(
            f"{_MOD}.get_voice_fingerprint",
            return_value=(len(entries), len(entries), "x"),
        ),
        patch(f"{_MOD}.get_voice_history", return_value=entries),
    ):
        page.refresh_history(force=True)


# ===================================================================
# Widget Construction
# ===================================================================


class TestConstruction:
    """Tests for VoiceHistoryPage widget construction."""

    def test_page_created(self, page) -> None:  # noqa: ANN001
        """Page is created without error."""
        assert page is not None

    def test_has_table(self, page) -> None:  # noqa: ANN001
        """Page has a QTableWidget."""
        assert isinstance(page.table, QTableWidget)

    def test_table_column_count(self, page) -> None:  # noqa: ANN001
        """Table has 4 columns: name, size, status, date."""
        assert page.table.columnCount() == 4  # noqa: PLR2004

    def test_table_not_editable(self, page) -> None:  # noqa: ANN001
        """Table is read-only."""
        assert page.table.editTriggers() == QTableWidget.EditTrigger.NoEditTriggers

    def test_table_extended_selection(self, page) -> None:  # noqa: ANN001
        """Table supports multi-row selection."""
        assert (
            page.table.selectionMode() == QTableWidget.SelectionMode.ExtendedSelection
        )

    def test_has_search_input(self, page) -> None:  # noqa: ANN001
        """Page has a search input field."""
        assert hasattr(page, "search_input")

    def test_has_action_buttons(self, page) -> None:  # noqa: ANN001
        """Page has open, re-generate, and delete buttons."""
        assert hasattr(page, "open_btn")
        assert hasattr(page, "re_generate_btn")
        assert hasattr(page, "delete_btn")

    def test_buttons_disabled_initially(self, page) -> None:  # noqa: ANN001
        """Action buttons start disabled (no selection)."""
        assert not page.open_btn.isEnabled()
        assert not page.re_generate_btn.isEnabled()
        assert not page.delete_btn.isEnabled()

    def test_error_frame_hidden_initially(self, page) -> None:  # noqa: ANN001
        """Error banner is hidden at construction time."""
        assert not page.error_frame.isVisible()

    def test_highlight_delegate_attached(self, page) -> None:  # noqa: ANN001
        """HighlightDelegate is attached to column 0."""
        from src.ui.components import HighlightDelegate  # noqa: PLC0415

        assert isinstance(page.table.itemDelegateForColumn(0), HighlightDelegate)

    def test_status_delegate_attached(self, page) -> None:  # noqa: ANN001
        """ForegroundPreservingDelegate is attached to column 2."""
        from src.ui.components import ForegroundPreservingDelegate  # noqa: PLC0415

        assert isinstance(
            page.table.itemDelegateForColumn(2), ForegroundPreservingDelegate
        )


# ===================================================================
# Refresh History
# ===================================================================


class TestRefreshHistory:
    """Tests for refresh_history behavior."""

    def test_refresh_populates_table(self, page) -> None:  # noqa: ANN001
        """refresh_history populates table rows from DB entries."""
        entries = [_make_entry(1), _make_entry(2, name="narration.srt")]
        _populate_table(page, entries)
        assert page.table.rowCount() == 2  # noqa: PLR2004

    def test_refresh_clears_on_none(self, page) -> None:  # noqa: ANN001
        """Table is cleared when get_voice_history returns None."""
        with (
            patch(f"{_MOD}.get_voice_fingerprint", return_value=(0, 0, "x")),
            patch(f"{_MOD}.get_voice_history", return_value=None),
        ):
            page.refresh_history(force=True)
        assert page.table.rowCount() == 0

    def test_refresh_skips_when_fingerprint_unchanged(self, page) -> None:  # noqa: ANN001
        """Skips rebuild when fingerprint hasn't changed."""
        fp = (1, 1, "abc")
        history_mock = MagicMock(return_value=[])
        with (
            patch(f"{_MOD}.get_voice_fingerprint", return_value=fp),
            patch(f"{_MOD}.get_voice_history", return_value=[]),
        ):
            page.show()
        with (
            patch(f"{_MOD}.get_voice_fingerprint", return_value=fp),
            patch(f"{_MOD}.get_voice_history", history_mock),
        ):
            page._last_fingerprint = fp
            page.refresh_history(force=False)
            history_mock.assert_not_called()

    def test_force_refresh_always_rebuilds(self, page) -> None:  # noqa: ANN001
        """force=True rebuilds even when fingerprint matches."""
        fp = (1, 1, "abc")
        history_mock = MagicMock(return_value=[])
        with (
            patch(f"{_MOD}.get_voice_fingerprint", return_value=fp),
            patch(f"{_MOD}.get_voice_history", history_mock),
        ):
            page._last_fingerprint = fp
            page.refresh_history(force=True)
            history_mock.assert_called_once()

    def test_refresh_empty_history(self, page) -> None:  # noqa: ANN001
        """Empty history list results in 0 rows."""
        _populate_table(page, [])
        assert page.table.rowCount() == 0


# ===================================================================
# Fill Row
# ===================================================================


class TestFillRow:
    """Tests for _fill_row data mapping."""

    def test_stores_entry_id(self, page) -> None:  # noqa: ANN001
        """Entry ID is stored in UserRole on column 0."""
        entry_id = 33  # noqa: PLR2004
        _populate_table(page, [_make_entry(entry_id=entry_id)])
        item = page.table.item(0, 0)
        assert item.data(Qt.ItemDataRole.UserRole) == entry_id

    def test_stores_output_path(self, page) -> None:  # noqa: ANN001
        """Output path is stored in UserRole+1 on column 0."""
        _populate_table(page, [_make_entry(output_path="/out/audio.mp3")])
        item = page.table.item(0, 0)
        assert item.data(Qt.ItemDataRole.UserRole + 1) == "/out/audio.mp3"

    def test_stores_source_path(self, page) -> None:  # noqa: ANN001
        """Source path is stored in UserRole+2 on column 0."""
        _populate_table(page, [_make_entry(source_path="/src/sub.srt")])
        item = page.table.item(0, 0)
        assert item.data(Qt.ItemDataRole.UserRole + 2) == "/src/sub.srt"

    def test_stores_error_message(self, page) -> None:  # noqa: ANN001
        """Error message is stored in UserRole+3 on column 0."""
        _populate_table(page, [_make_entry(error_message="TTS_ERROR")])
        item = page.table.item(0, 0)
        assert item.data(Qt.ItemDataRole.UserRole + 3) == "TTS_ERROR"

    def test_file_name_displayed(self, page) -> None:  # noqa: ANN001
        """File name is shown as column 0 text."""
        _populate_table(page, [_make_entry(name="podcast.srt")])
        assert page.table.item(0, 0).text() == "podcast.srt"

    def test_size_formatted(self, page) -> None:  # noqa: ANN001
        """File size is formatted via format_file_size."""
        _populate_table(page, [_make_entry(file_size=8192)])
        size_text = page.table.item(0, 1).text()
        assert size_text  # Non-empty formatted string

    def test_size_zero_shows_0b(self, page) -> None:  # noqa: ANN001
        """Zero/None file size shows '0 B'."""
        _populate_table(page, [_make_entry(file_size=0)])
        assert page.table.item(0, 1).text() == "0 B"

    def test_status_done_stored(self, page) -> None:  # noqa: ANN001
        """Done status raw value is stored in UserRole."""
        _populate_table(page, [_make_entry(status="Done")])
        status_item = page.table.item(0, 2)
        assert status_item.data(Qt.ItemDataRole.UserRole) == "Done"

    def test_status_failed_stored(self, page) -> None:  # noqa: ANN001
        """Failed status raw value is stored in UserRole."""
        _populate_table(page, [_make_entry(status="Failed")])
        status_item = page.table.item(0, 2)
        assert status_item.data(Qt.ItemDataRole.UserRole) == "Failed"

    def test_status_generating_stored(self, page) -> None:  # noqa: ANN001
        """Generating status raw value is stored in UserRole."""
        _populate_table(page, [_make_entry(status="Generating")])
        status_item = page.table.item(0, 2)
        assert status_item.data(Qt.ItemDataRole.UserRole) == "Generating"

    def test_status_pending_stored(self, page) -> None:  # noqa: ANN001
        """Pending status raw value is stored in UserRole."""
        _populate_table(page, [_make_entry(status="Pending")])
        status_item = page.table.item(0, 2)
        assert status_item.data(Qt.ItemDataRole.UserRole) == "Pending"

    def test_date_column_present(self, page) -> None:  # noqa: ANN001
        """Date column has non-empty text."""
        _populate_table(page, [_make_entry()])
        assert page.table.item(0, 3).text()


# ===================================================================
# Header Click
# ===================================================================


class TestHeaderClick:
    """Tests for _on_header_clicked behavior."""

    def test_header_click_clears_selection(self, page) -> None:  # noqa: ANN001
        """Clicking a header clears the current selection."""
        _populate_table(page, [_make_entry(1), _make_entry(2)])
        page.table.selectRow(0)
        assert len(page.table.selectedItems()) > 0

        page._on_header_clicked(0)
        assert len(page.table.selectedItems()) == 0

    def test_header_click_disables_buttons(self, page) -> None:  # noqa: ANN001
        """Buttons are disabled after header click clears selection."""
        _populate_table(page, [_make_entry()])
        page.table.selectRow(0)
        page._on_header_clicked(0)
        assert not page.open_btn.isEnabled()
        assert not page.re_generate_btn.isEnabled()
        assert not page.delete_btn.isEnabled()


# ===================================================================
# Button States
# ===================================================================


class TestButtonStates:
    """Tests for _update_button_states logic."""

    def test_no_selection_all_disabled(self, page) -> None:  # noqa: ANN001
        """All buttons disabled when nothing is selected."""
        _populate_table(page, [_make_entry()])
        page.table.clearSelection()
        page._update_button_states()
        assert not page.open_btn.isEnabled()
        assert not page.re_generate_btn.isEnabled()
        assert not page.delete_btn.isEnabled()

    def test_done_selection_enables_all(self, page) -> None:  # noqa: ANN001
        """Selecting a Done entry enables all buttons."""
        _populate_table(page, [_make_entry(status="Done")])
        page.table.selectRow(0)
        assert page.open_btn.isEnabled()
        assert page.re_generate_btn.isEnabled()
        assert page.delete_btn.isEnabled()

    def test_pending_disables_re_generate(self, page) -> None:  # noqa: ANN001
        """Selecting a Pending entry disables re-generate but enables open/delete."""
        _populate_table(page, [_make_entry(status="Pending")])
        page.table.selectRow(0)
        assert page.open_btn.isEnabled()
        assert not page.re_generate_btn.isEnabled()
        assert page.delete_btn.isEnabled()

    def test_generating_disables_re_generate(self, page) -> None:  # noqa: ANN001
        """Selecting a Generating entry disables re-generate."""
        _populate_table(page, [_make_entry(status="Generating")])
        page.table.selectRow(0)
        assert not page.re_generate_btn.isEnabled()

    def test_error_message_shown_for_failed(self, page) -> None:  # noqa: ANN001
        """Error banner is shown when a single failed entry is selected."""
        page.show()
        _populate_table(
            page,
            [_make_entry(status="Failed", error_message="ERR_TTS")],
        )
        page.table.selectRow(0)
        assert page.error_frame.isVisible()

    def test_auth_error_service_suffix_renders_specific_service(
        self,
        page,  # noqa: ANN001
    ) -> None:
        """``AUTH_ERROR:ElevenLabs`` → "Invalid ElevenLabs API key…".

        Voice page surfaces TTS auth failures.  Pins service-aware
        copy so the user knows WHICH key to fix (Google Cloud /
        ElevenLabs / Gemini all reachable depending on TTS backend).
        """
        from src.constants.i18n import _set_initial_language  # noqa: PLC0415

        _set_initial_language("en-US")
        page.show()
        _populate_table(
            page,
            [_make_entry(status="Failed", error_message="AUTH_ERROR:ElevenLabs")],
        )
        page.table.selectRow(0)
        text = page.error_label.text()
        assert "ElevenLabs" in text, (
            f"service name missing from error label: {text!r}"
        )
        assert "API key" in text

    def test_error_hidden_for_done(self, page) -> None:  # noqa: ANN001
        """Error banner is hidden when a Done entry is selected."""
        _populate_table(page, [_make_entry(status="Done")])
        page.table.selectRow(0)
        assert not page.error_frame.isVisible()


# ===================================================================
# Open File
# ===================================================================


class TestOpenFile:
    """Tests for on_open_file behavior."""

    @patch(f"{_MOD}.QDesktopServices.openUrl")
    @patch(f"{_MOD}.Path.exists", return_value=True)
    def test_open_file_calls_desktop_services(
        self,
        mock_exists,
        mock_open,
        page,  # noqa: ANN001
    ) -> None:
        """Opens selected file via QDesktopServices."""
        _populate_table(page, [_make_entry(output_path="/out/audio.mp3")])
        page.table.selectRow(0)
        page.on_open_file()
        mock_open.assert_called_once()

    @patch(f"{_MOD}.QDesktopServices.openUrl")
    @patch(f"{_MOD}.Path.exists", return_value=False)
    def test_open_file_skips_missing(
        self,
        mock_exists,
        mock_open,
        page,  # noqa: ANN001
    ) -> None:
        """Skips opening when the output file does not exist."""
        _populate_table(page, [_make_entry(output_path="/out/missing.mp3")])
        page.table.selectRow(0)
        page.on_open_file()
        mock_open.assert_not_called()

    def test_open_file_no_selection(self, page) -> None:  # noqa: ANN001
        """Does nothing when no rows are selected."""
        _populate_table(page, [_make_entry()])
        page.table.clearSelection()
        page.on_open_file()  # Should not raise


# ===================================================================
# Delete Selected
# ===================================================================


class TestDeleteSelected:
    """Tests for on_delete_selected behavior."""

    @patch(f"{_MOD}.Path.is_file", return_value=True)
    @patch(f"{_MOD}.Path.unlink")
    @patch(f"{_MOD}.delete_voice_entry", return_value="/out/audio.mp3")
    @patch(f"{_MOD}.CustomConfirmDialog.confirm", return_value=True)
    def test_delete_confirmed(
        self,
        mock_confirm,
        mock_delete,
        mock_unlink,
        mock_is_file,
        page,  # noqa: ANN001
    ) -> None:
        """Delete confirmed: entry removed and file unlinked."""
        _populate_table(page, [_make_entry(entry_id=10)])
        page.table.selectRow(0)

        with (
            patch(f"{_MOD}.get_voice_fingerprint", return_value=(0, 0, "x")),
            patch(f"{_MOD}.get_voice_history", return_value=[]),
        ):
            page.on_delete_selected()

        mock_confirm.assert_called_once()
        mock_delete.assert_called_once_with(10)  # noqa: PLR2004

    @patch(f"{_MOD}.delete_voice_entry")
    @patch(f"{_MOD}.CustomConfirmDialog.confirm", return_value=False)
    def test_delete_cancelled(
        self,
        mock_confirm,
        mock_delete,
        page,  # noqa: ANN001
    ) -> None:
        """Delete cancelled: no entries removed."""
        _populate_table(page, [_make_entry()])
        page.table.selectRow(0)
        page.on_delete_selected()
        mock_delete.assert_not_called()

    def test_delete_no_selection(self, page) -> None:  # noqa: ANN001
        """Does nothing when no rows are selected."""
        _populate_table(page, [_make_entry()])
        page.table.clearSelection()
        page.on_delete_selected()  # Should not raise

    @patch(f"{_MOD}.Path.is_file", return_value=True)
    @patch(f"{_MOD}.Path.unlink")
    @patch(f"{_MOD}.delete_voice_entry", return_value="/out/audio.mp3")
    @patch(f"{_MOD}.CustomConfirmDialog.confirm", return_value=True)
    def test_delete_multiple(
        self,
        mock_confirm,
        mock_delete,
        mock_unlink,
        mock_is_file,
        page,  # noqa: ANN001
    ) -> None:
        """Deleting multiple rows deletes all selected entries."""
        entries = [_make_entry(entry_id=i) for i in range(1, 4)]
        _populate_table(page, entries)
        page.table.selectAll()

        with (
            patch(f"{_MOD}.get_voice_fingerprint", return_value=(0, 0, "x")),
            patch(f"{_MOD}.get_voice_history", return_value=[]),
        ):
            page.on_delete_selected()

        assert mock_delete.call_count == 3  # noqa: PLR2004


# ===================================================================
# Re-Generate
# ===================================================================


class TestReGenerate:
    """Tests for on_re_generate behavior."""

    @patch(f"{_MOD}.Path.exists", return_value=True)
    def test_re_generate_emits_signal(
        self,
        mock_exists,
        page,
        qtbot,  # noqa: ANN001
    ) -> None:
        """Re-generate emits re_generate_requested with correct tasks."""
        _populate_table(
            page,
            [_make_entry(entry_id=7, source_path="/src/sub.srt", status="Done")],
        )
        page.table.selectRow(0)

        with qtbot.waitSignal(page.re_generate_requested, timeout=1000) as sig:
            page.on_re_generate()

        assert len(sig.args[0]) == 1
        assert sig.args[0][0] == (7, "/src/sub.srt")

    @patch(f"{_MOD}.Path.exists", return_value=False)
    @patch(f"{_MOD}.CustomMessageDialog.show_message")
    @patch(f"{_MOD}.delete_voice_entry")
    def test_re_generate_missing_source(
        self,
        mock_delete,
        mock_msg,
        mock_exists,
        page,  # noqa: ANN001
    ) -> None:
        """Shows error dialog and deletes entry when source file is missing."""
        _populate_table(page, [_make_entry(entry_id=9, source_path="/gone.srt")])
        page.table.selectRow(0)

        with (
            patch(f"{_MOD}.get_voice_fingerprint", return_value=(0, 0, "x")),
            patch(f"{_MOD}.get_voice_history", return_value=[]),
        ):
            page.on_re_generate()

        mock_msg.assert_called_once()
        mock_delete.assert_called_once_with(9)  # noqa: PLR2004

    def test_re_generate_no_selection(self, page) -> None:  # noqa: ANN001
        """Does nothing when no rows are selected."""
        _populate_table(page, [_make_entry()])
        page.table.clearSelection()
        page.on_re_generate()  # Should not raise


# ===================================================================
# Search Filtering
# ===================================================================


class TestSearchFiltering:
    """Tests for client-side search filtering."""

    def test_search_filters_by_name(self, page) -> None:  # noqa: ANN001
        """Search filters entries by file name (case-insensitive)."""
        entries = [
            _make_entry(entry_id=1, name="Podcast.srt"),
            _make_entry(entry_id=2, name="Audiobook.srt"),
        ]
        page.search_input.setText("podcast")
        _populate_table(page, entries)
        assert page.table.rowCount() == 1

    def test_search_empty_shows_all(self, page) -> None:  # noqa: ANN001
        """Empty search shows all entries."""
        entries = [_make_entry(entry_id=1), _make_entry(entry_id=2)]
        page.search_input.setText("")
        _populate_table(page, entries)
        assert page.table.rowCount() == 2  # noqa: PLR2004

    def test_search_no_match_shows_none(self, page) -> None:  # noqa: ANN001
        """Search with no match shows 0 rows."""
        entries = [_make_entry(entry_id=1, name="speech.srt")]
        page.search_input.setText("nonexistent")
        _populate_table(page, entries)
        assert page.table.rowCount() == 0


# ===================================================================
# Selection Preservation
# ===================================================================


class TestSelectionPreservation:
    """Tests for selection preservation across refreshes."""

    def test_selection_restored_after_refresh(self, page) -> None:  # noqa: ANN001
        """Selected entry IDs are restored after refresh."""
        entries = [_make_entry(entry_id=1), _make_entry(entry_id=2)]
        _populate_table(page, entries)
        page.table.selectRow(0)

        _populate_table(page, entries)

        selected_ids = set()
        for item in page.table.selectedItems():
            if item.column() == 0:
                selected_ids.add(item.data(Qt.ItemDataRole.UserRole))
        assert len(selected_ids) > 0


# ===================================================================
# Theme / Language
# ===================================================================


class TestThemeAndLanguage:
    """Tests for apply_theme and apply_language methods."""

    def test_apply_theme_runs(self, page) -> None:  # noqa: ANN001
        """apply_theme() completes without error."""
        with (
            patch(f"{_MOD}.get_voice_fingerprint", return_value=None),
            patch(f"{_MOD}.get_voice_history", return_value=[]),
        ):
            page.apply_theme()

    def test_apply_language_runs(self, page) -> None:  # noqa: ANN001
        """apply_language() completes without error."""
        with (
            patch(f"{_MOD}.get_voice_fingerprint", return_value=None),
            patch(f"{_MOD}.get_voice_history", return_value=[]),
        ):
            page.apply_language()

    def test_apply_language_updates_headers(self, page) -> None:  # noqa: ANN001
        """apply_language updates all column header texts."""
        with (
            patch(f"{_MOD}.get_voice_fingerprint", return_value=None),
            patch(f"{_MOD}.get_voice_history", return_value=[]),
        ):
            page.apply_language()

        for col in range(page.table.columnCount()):
            header = page.table.horizontalHeaderItem(col)
            assert header is not None
            assert len(header.text()) > 0

    def test_apply_language_updates_button_text(self, page) -> None:  # noqa: ANN001
        """apply_language updates button labels."""
        with (
            patch(f"{_MOD}.get_voice_fingerprint", return_value=None),
            patch(f"{_MOD}.get_voice_history", return_value=[]),
        ):
            page.apply_language()

        assert page.open_btn.text()
        assert page.re_generate_btn.text()
        assert page.delete_btn.text()


# ===================================================================
# showEvent Trigger
# ===================================================================


class TestShowEvent:
    """Tests that showEvent triggers refresh_history(force=True)."""

    def test_show_event_triggers_force_refresh(self, page) -> None:  # noqa: ANN001
        """showEvent() calls refresh_history(force=True)."""
        with patch.object(page, "refresh_history") as mock_refresh:
            page.showEvent(None)
            mock_refresh.assert_called_once_with(force=True)


# ===================================================================
# Sort Item Comparison
# ===================================================================


class TestSortItems:
    """Tests for custom sort item __lt__ implementations."""

    def test_case_insensitive_sort_item_ordering(self, page) -> None:  # noqa: ANN001
        """CaseInsensitiveSortItem sorts case-insensitively."""
        from src.ui.components import CaseInsensitiveSortItem  # noqa: PLC0415

        apple = CaseInsensitiveSortItem("apple")
        banana = CaseInsensitiveSortItem("Banana")
        cherry = CaseInsensitiveSortItem("CHERRY")

        assert apple < banana
        assert banana < cherry
        assert not cherry < apple

    def test_case_insensitive_sort_equal_different_case(self, page) -> None:  # noqa: ANN001
        """Same text with different case is neither less nor greater."""
        from src.ui.components import CaseInsensitiveSortItem  # noqa: PLC0415

        lower = CaseInsensitiveSortItem("hello")
        upper = CaseInsensitiveSortItem("HELLO")

        assert not lower < upper
        assert not upper < lower

    def test_numerical_sort_item_ordering(self, page) -> None:  # noqa: ANN001
        """NumericalSortItem sorts numerically, not lexicographically."""
        from src.ui.components import NumericalSortItem  # noqa: PLC0415

        nine = NumericalSortItem("9 KB", 9.0)
        ten = NumericalSortItem("10 KB", 10.0)
        hundred = NumericalSortItem("100 KB", 100.0)

        assert nine < ten
        assert ten < hundred
        assert not ten < nine

    def test_numerical_sort_item_equal_values(self, page) -> None:  # noqa: ANN001
        """Equal numerical values are neither less nor greater."""
        from src.ui.components import NumericalSortItem  # noqa: PLC0415

        a = NumericalSortItem("5 KB", 5.0)
        b = NumericalSortItem("5.0 KB", 5.0)

        assert not a < b
        assert not b < a

    def test_datetime_sort_item_ordering(self, page) -> None:  # noqa: ANN001
        """DateTimeSortItem sorts by ISO key, not display text."""
        from src.ui.components import DateTimeSortItem  # noqa: PLC0415

        earlier = DateTimeSortItem("Jan 1", "2026-01-01 00:00:00")
        later = DateTimeSortItem("Dec 31", "2026-12-31 23:59:59")

        assert earlier < later
        assert not later < earlier

    def test_datetime_sort_item_same_date(self, page) -> None:  # noqa: ANN001
        """Same ISO key means neither is less than the other."""
        from src.ui.components import DateTimeSortItem  # noqa: PLC0415

        a = DateTimeSortItem("Today", "2026-03-24 10:00:00")
        b = DateTimeSortItem("Now", "2026-03-24 10:00:00")

        assert not a < b
        assert not b < a


# ===================================================================
# Page Is A QWidget
# ===================================================================


class TestPageIsQWidget:
    """Tests that the page is a proper QWidget with expected elements."""

    def test_is_qwidget_instance(self, page) -> None:  # noqa: ANN001
        """VoiceHistoryPage is a QWidget."""
        from PySide6.QtWidgets import QWidget  # noqa: PLC0415

        assert isinstance(page, QWidget)

    def test_has_error_label(self, page) -> None:  # noqa: ANN001
        """Page has an error label widget."""
        assert hasattr(page, "error_label")

    def test_has_search_timer(self, page) -> None:  # noqa: ANN001
        """Page has a debounced search timer."""
        assert hasattr(page, "search_timer")
        assert page.search_timer.isSingleShot()

    def test_has_background_timer(self, page) -> None:  # noqa: ANN001
        """Page has a background refresh timer."""
        assert hasattr(page, "timer")
        assert page.timer.isActive()

    def test_search_input_max_width(self, page) -> None:  # noqa: ANN001
        """Search input has a maximum width of 360."""
        assert page.search_input.maximumWidth() == 360  # noqa: PLR2004

    def test_search_input_has_placeholder(self, page) -> None:  # noqa: ANN001
        """Search input has non-empty placeholder text."""
        assert page.search_input.placeholderText()

    def test_buttons_have_cursor(self, page) -> None:  # noqa: ANN001
        """All action buttons have pointing hand cursor."""
        for btn in [page.open_btn, page.re_generate_btn, page.delete_btn]:
            assert btn.cursor().shape() == Qt.CursorShape.PointingHandCursor

    def test_main_layout_no_margins(self, page) -> None:  # noqa: ANN001
        """Main layout has zero margins."""
        margins = page.main_layout.contentsMargins()
        assert margins.left() == 0
        assert margins.top() == 0
        assert margins.right() == 0
        assert margins.bottom() == 0


# ===================================================================
# Table Refresh Preservation
# ===================================================================


class TestTableRefreshPreservation:
    """Tests for scroll and selection preservation during refresh."""

    def test_scroll_position_restore_attempted(self, page) -> None:  # noqa: ANN001
        """Refresh attempts to restore scroll position (setValue is called)."""
        entries = [_make_entry(entry_id=i) for i in range(1, 10)]
        _populate_table(page, entries)
        scrollbar = page.table.verticalScrollBar()
        assert scrollbar is not None

    def test_multi_selection_preserved(self, page) -> None:  # noqa: ANN001
        """Multiple selections are preserved across refresh."""
        entries = [_make_entry(entry_id=i) for i in range(1, 4)]
        _populate_table(page, entries)
        page.table.selectAll()
        _populate_table(page, entries)
        selected_ids = set()
        for item in page.table.selectedItems():
            if item.column() == 0:
                selected_ids.add(item.data(Qt.ItemDataRole.UserRole))
        assert selected_ids == {1, 2, 3}

    def test_refresh_not_visible_no_force_skips(self, page) -> None:  # noqa: ANN001
        """refresh_history skips when page is not visible and force=False."""
        page.hide()
        history_mock = MagicMock(return_value=[_make_entry()])
        with (
            patch(f"{_MOD}.get_voice_fingerprint", return_value=(1, 1, "new")),
            patch(f"{_MOD}.get_voice_history", history_mock),
        ):
            page.refresh_history(force=False)
            history_mock.assert_not_called()

    def test_fingerprint_none_always_refreshes(self, page) -> None:  # noqa: ANN001
        """When fingerprint is None, always refreshes."""
        history_mock = MagicMock(return_value=[_make_entry()])
        page._last_fingerprint = (1, 1, "old")
        with (
            patch(f"{_MOD}.get_voice_fingerprint", return_value=None),
            patch(f"{_MOD}.get_voice_history", history_mock),
        ):
            page.show()
            page.refresh_history(force=False)
            history_mock.assert_called()


# ===================================================================
# Search Edge Cases
# ===================================================================


class TestSearchEdgeCases:
    """Tests for search edge cases."""

    def test_search_case_insensitive_uppercase(self, page) -> None:  # noqa: ANN001
        """Search is case-insensitive with uppercase query."""
        entries = [_make_entry(entry_id=1, name="speech.srt")]
        page.search_input.setText("SPEECH")
        _populate_table(page, entries)
        assert page.table.rowCount() == 1

    def test_search_partial_match(self, page) -> None:  # noqa: ANN001
        """Search matches partial file names."""
        entries = [_make_entry(entry_id=1, name="my_podcast_file.srt")]
        page.search_input.setText("podcast")
        _populate_table(page, entries)
        assert page.table.rowCount() == 1

    def test_search_with_special_characters(self, page) -> None:  # noqa: ANN001
        """Search handles special characters in file names."""
        entries = [_make_entry(entry_id=1, name="file (1).srt")]
        page.search_input.setText("(1)")
        _populate_table(page, entries)
        assert page.table.rowCount() == 1

    def test_search_whitespace_only_shows_all(self, page) -> None:  # noqa: ANN001
        """Whitespace-only search shows all entries (stripped to empty)."""
        entries = [_make_entry(entry_id=1), _make_entry(entry_id=2)]
        page.search_input.setText("   ")
        _populate_table(page, entries)
        assert page.table.rowCount() == 2  # noqa: PLR2004

    def test_search_updates_highlight_delegate(self, page) -> None:  # noqa: ANN001
        """Search text is passed to the highlight delegate."""
        entries = [_make_entry(entry_id=1, name="test.srt")]
        page.search_input.setText("test")
        _populate_table(page, entries)
        assert page.highlight_delegate.search_text == "test"


# ===================================================================
# Unicode and Long Filenames
# ===================================================================


class TestUnicodeAndLongFilenames:
    """Tests for edge cases with unicode and very long filenames."""

    def test_unicode_filename(self, page) -> None:  # noqa: ANN001
        """Unicode filenames are displayed correctly."""
        _populate_table(page, [_make_entry(name="\u97f3\u58f0\u6587\u4ef6.srt")])
        assert page.table.item(0, 0).text() == "\u97f3\u58f0\u6587\u4ef6.srt"

    def test_emoji_filename(self, page) -> None:  # noqa: ANN001
        """Emoji in filenames are displayed correctly."""
        _populate_table(page, [_make_entry(name="\U0001f3b5 music.srt")])
        assert page.table.item(0, 0).text() == "\U0001f3b5 music.srt"

    def test_very_long_filename(self, page) -> None:  # noqa: ANN001
        """Very long filenames are stored without truncation."""
        long_name = "a" * 500 + ".srt"
        _populate_table(page, [_make_entry(name=long_name)])
        assert page.table.item(0, 0).text() == long_name

    def test_empty_filename(self, page) -> None:  # noqa: ANN001
        """Empty filename is stored without error."""
        _populate_table(page, [_make_entry(name="")])
        assert page.table.item(0, 0).text() == ""

    def test_unicode_search(self, page) -> None:  # noqa: ANN001
        """Search works with unicode characters."""
        entries = [
            _make_entry(entry_id=1, name="\u97f3\u58f0.srt"),
            _make_entry(entry_id=2, name="english.srt"),
        ]
        page.search_input.setText("\u97f3\u58f0")
        _populate_table(page, entries)
        assert page.table.rowCount() == 1


# ===================================================================
# Status Colors
# ===================================================================


class TestStatusColors:
    """Tests for correct status color assignment."""

    def test_done_status_has_success_color(self, page) -> None:  # noqa: ANN001
        """Done status foreground uses success color."""
        from PySide6.QtGui import QColor  # noqa: PLC0415

        from src.constants import color as get_color  # noqa: PLC0415

        _populate_table(page, [_make_entry(status="Done")])
        status_item = page.table.item(0, 2)
        assert status_item.foreground().color() == QColor(get_color("success"))

    def test_failed_status_has_error_color(self, page) -> None:  # noqa: ANN001
        """Failed status foreground uses error color."""
        from PySide6.QtGui import QColor  # noqa: PLC0415

        from src.constants import color as get_color  # noqa: PLC0415

        _populate_table(page, [_make_entry(status="Failed")])
        status_item = page.table.item(0, 2)
        assert status_item.foreground().color() == QColor(get_color("error"))

    def test_generating_status_has_primary_color(self, page) -> None:  # noqa: ANN001
        """Generating status foreground uses primary color."""
        from PySide6.QtGui import QColor  # noqa: PLC0415

        from src.constants import color as get_color  # noqa: PLC0415

        _populate_table(page, [_make_entry(status="Generating")])
        status_item = page.table.item(0, 2)
        assert status_item.foreground().color() == QColor(get_color("primary"))

    def test_pending_status_has_text_primary_color(self, page) -> None:  # noqa: ANN001
        """Pending status foreground uses text_primary color."""
        from PySide6.QtGui import QColor  # noqa: PLC0415

        from src.constants import color as get_color  # noqa: PLC0415

        _populate_table(page, [_make_entry(status="Pending")])
        status_item = page.table.item(0, 2)
        assert status_item.foreground().color() == QColor(get_color("text_primary"))

    def test_status_text_uses_display_status(self, page) -> None:  # noqa: ANN001
        """Status column text uses display_status for translation."""
        from src.constants.history import display_status  # noqa: PLC0415

        _populate_table(page, [_make_entry(status="Done")])
        status_item = page.table.item(0, 2)
        assert status_item.text() == display_status("Done")


# ===================================================================
# Error Banner Edge Cases
# ===================================================================


class TestErrorBannerEdgeCases:
    """Tests for error banner behavior in various scenarios."""

    def test_error_hidden_when_multiple_selected(self, page) -> None:  # noqa: ANN001
        """Error banner is hidden when multiple entries are selected."""
        entries = [
            _make_entry(entry_id=1, status="Failed", error_message="ERR_1"),
            _make_entry(entry_id=2, status="Failed", error_message="ERR_2"),
        ]
        _populate_table(page, entries)
        page.table.selectAll()
        assert not page.error_frame.isVisible()

    def test_error_hidden_when_no_error_message(self, page) -> None:  # noqa: ANN001
        """Error banner is hidden for failed entry without error_message."""
        _populate_table(page, [_make_entry(status="Failed", error_message=None)])
        page.table.selectRow(0)
        assert not page.error_frame.isVisible()

    def test_error_hidden_after_deselection(self, page) -> None:  # noqa: ANN001
        """Error banner is hidden after deselecting a failed entry."""
        page.show()
        _populate_table(
            page,
            [_make_entry(status="Failed", error_message="ERR_TEST")],
        )
        page.table.selectRow(0)
        assert page.error_frame.isVisible()
        page.table.clearSelection()
        page._update_button_states()
        assert not page.error_frame.isVisible()


# ===================================================================
# Re-Generate Multiple Files
# ===================================================================


class TestReGenerateMultiple:
    """Tests for re-generating multiple files."""

    @patch(f"{_MOD}.Path.exists", return_value=True)
    def test_re_generate_multiple_emits_all(
        self,
        mock_exists,
        page,
        qtbot,  # noqa: ANN001
    ) -> None:
        """Re-generate with multiple selected emits all tasks."""
        entries = [
            _make_entry(entry_id=1, source_path="/src/s1.srt", status="Done"),
            _make_entry(entry_id=2, source_path="/src/s2.srt", status="Done"),
        ]
        _populate_table(page, entries)
        page.table.selectAll()

        with qtbot.waitSignal(page.re_generate_requested, timeout=1000) as sig:
            page.on_re_generate()

        assert len(sig.args[0]) == 2  # noqa: PLR2004


# ===================================================================
# Delete With File Cleanup
# ===================================================================


class TestDeleteFileCleanup:
    """Tests for file cleanup during delete operations."""

    @patch(f"{_MOD}.Path.is_file", return_value=False)
    @patch(f"{_MOD}.delete_voice_entry", return_value="/out/audio.mp3")
    @patch(f"{_MOD}.CustomConfirmDialog.confirm", return_value=True)
    def test_delete_file_not_on_disk(
        self,
        mock_confirm,
        mock_delete,
        mock_is_file,
        page,  # noqa: ANN001
    ) -> None:
        """When output file doesn't exist on disk, entry is still deleted."""
        _populate_table(page, [_make_entry(entry_id=5)])
        page.table.selectRow(0)

        with (
            patch(f"{_MOD}.get_voice_fingerprint", return_value=(0, 0, "x")),
            patch(f"{_MOD}.get_voice_history", return_value=[]),
        ):
            page.on_delete_selected()

        mock_delete.assert_called_once_with(5)  # noqa: PLR2004

    @patch(f"{_MOD}.delete_voice_entry", return_value=None)
    @patch(f"{_MOD}.CustomConfirmDialog.confirm", return_value=True)
    def test_delete_handles_none_output_path(
        self,
        mock_confirm,
        mock_delete,
        page,  # noqa: ANN001
    ) -> None:
        """Delete handles None output path gracefully."""
        _populate_table(page, [_make_entry(entry_id=1)])
        page.table.selectRow(0)

        with (
            patch(f"{_MOD}.get_voice_fingerprint", return_value=(0, 0, "x")),
            patch(f"{_MOD}.get_voice_history", return_value=[]),
        ):
            page.on_delete_selected()  # Should not raise

        mock_delete.assert_called_once()


# ===================================================================
# Sorting Behavior
# ===================================================================


class TestSortingBehavior:
    """Tests for table sorting."""

    def test_sort_by_name_column(self, page) -> None:  # noqa: ANN001
        """Sorting by name column orders rows alphabetically."""
        entries = [
            _make_entry(entry_id=1, name="Zebra.srt"),
            _make_entry(entry_id=2, name="Apple.srt"),
        ]
        _populate_table(page, entries)
        page.table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        assert page.table.item(0, 0).text() == "Apple.srt"
        assert page.table.item(1, 0).text() == "Zebra.srt"

    def test_sort_by_date_column_descending(self, page) -> None:  # noqa: ANN001
        """Sorting by date column descending puts newest first."""
        entries = [
            _make_entry(entry_id=1, created_at="2026-01-01 10:00:00"),
            _make_entry(entry_id=2, created_at="2026-12-31 10:00:00"),
        ]
        _populate_table(page, entries)
        page.table.sortByColumn(3, Qt.SortOrder.DescendingOrder)
        first_id = page.table.item(0, 0).data(Qt.ItemDataRole.UserRole)
        assert first_id == 2  # noqa: PLR2004

    def test_header_click_different_columns(self, page) -> None:  # noqa: ANN001
        """Clicking any header column index clears selection."""
        _populate_table(page, [_make_entry()])
        page.table.selectRow(0)
        for col in range(page.table.columnCount()):
            page._on_header_clicked(col)
            assert len(page.table.selectedItems()) == 0

    def test_sort_by_size_column(self, page) -> None:  # noqa: ANN001
        """Sorting by size column orders rows numerically."""
        entries = [
            _make_entry(entry_id=1, file_size=5000),
            _make_entry(entry_id=2, file_size=100),
        ]
        _populate_table(page, entries)
        page.table.sortByColumn(1, Qt.SortOrder.AscendingOrder)
        first_id = page.table.item(0, 0).data(Qt.ItemDataRole.UserRole)
        assert first_id == 2  # noqa: PLR2004


# ===================================================================
# Signals
# ===================================================================


class TestSignals:
    """Tests for Qt signal declarations."""

    def test_re_generate_requested_signal_exists(self, page) -> None:  # noqa: ANN001
        """VoiceHistoryPage has re_generate_requested signal."""
        assert hasattr(page, "re_generate_requested")


# ===================================================================
# Failed Selection Button States
# ===================================================================


class TestFailedSelectionStates:
    """Tests for button states with Failed status entries."""

    def test_failed_enables_re_generate(self, page) -> None:  # noqa: ANN001
        """Selecting a Failed entry enables re-generate."""
        _populate_table(page, [_make_entry(status="Failed")])
        page.table.selectRow(0)
        assert page.re_generate_btn.isEnabled()

    def test_mixed_done_and_pending_disables_re_generate(
        self,
        page,  # noqa: ANN001
    ) -> None:
        """Mixed Done + Pending selection disables re-generate."""
        entries = [
            _make_entry(entry_id=1, status="Done"),
            _make_entry(entry_id=2, status="Pending"),
        ]
        _populate_table(page, entries)
        page.table.selectAll()
        assert not page.re_generate_btn.isEnabled()

    def test_mixed_done_and_generating_disables_re_generate(
        self,
        page,  # noqa: ANN001
    ) -> None:
        """Mixed Done + Generating selection disables re-generate."""
        entries = [
            _make_entry(entry_id=1, status="Done"),
            _make_entry(entry_id=2, status="Generating"),
        ]
        _populate_table(page, entries)
        page.table.selectAll()
        assert not page.re_generate_btn.isEnabled()


# ===================================================================
# Apply Theme Updates Styles
# ===================================================================


class TestApplyThemeUpdatesStyles:
    """Tests for apply_theme updating widget styles."""

    def test_apply_theme_updates_all_button_styles(self, page) -> None:  # noqa: ANN001
        """apply_theme updates styles for all action buttons."""
        with (
            patch(f"{_MOD}.get_voice_fingerprint", return_value=None),
            patch(f"{_MOD}.get_voice_history", return_value=[]),
        ):
            page.apply_theme()

        assert page.open_btn.styleSheet()
        assert page.re_generate_btn.styleSheet()
        assert page.delete_btn.styleSheet()

    def test_apply_theme_updates_table_style(self, page) -> None:  # noqa: ANN001
        """apply_theme updates the table stylesheet."""
        with (
            patch(f"{_MOD}.get_voice_fingerprint", return_value=None),
            patch(f"{_MOD}.get_voice_history", return_value=[]),
        ):
            page.apply_theme()

        assert page.table.styleSheet()

    def test_apply_theme_updates_search_style(self, page) -> None:  # noqa: ANN001
        """apply_theme updates the search input stylesheet."""
        with (
            patch(f"{_MOD}.get_voice_fingerprint", return_value=None),
            patch(f"{_MOD}.get_voice_history", return_value=[]),
        ):
            page.apply_theme()

        assert page.search_input.styleSheet()

    def test_apply_language_updates_search_placeholder(
        self,
        page,  # noqa: ANN001
    ) -> None:
        """apply_language updates the search placeholder."""
        with (
            patch(f"{_MOD}.get_voice_fingerprint", return_value=None),
            patch(f"{_MOD}.get_voice_history", return_value=[]),
        ):
            page.apply_language()

        assert page.search_input.placeholderText()


# ===================================================================
# NEW: Extended Button State Combinations
# ===================================================================


class TestExtendedButtonStateCombinations:
    """Tests for button states with various status combinations."""

    def test_all_done_selection(self, page) -> None:  # noqa: ANN001
        """Selecting all Done entries enables all buttons."""
        entries = [
            _make_entry(entry_id=1, status="Done"),
            _make_entry(entry_id=2, status="Done"),
        ]
        _populate_table(page, entries)
        page.table.selectAll()
        assert page.open_btn.isEnabled()
        assert page.re_generate_btn.isEnabled()
        assert page.delete_btn.isEnabled()

    def test_all_pending_selection(self, page) -> None:  # noqa: ANN001
        """Selecting all Pending entries disables re-generate."""
        entries = [
            _make_entry(entry_id=1, status="Pending"),
            _make_entry(entry_id=2, status="Pending"),
        ]
        _populate_table(page, entries)
        page.table.selectAll()
        assert not page.re_generate_btn.isEnabled()
        assert page.delete_btn.isEnabled()

    def test_all_failed_selection(self, page) -> None:  # noqa: ANN001
        """Selecting all Failed entries enables re-generate and delete."""
        entries = [
            _make_entry(entry_id=1, status="Failed"),
            _make_entry(entry_id=2, status="Failed"),
        ]
        _populate_table(page, entries)
        page.table.selectAll()
        assert page.re_generate_btn.isEnabled()
        assert page.delete_btn.isEnabled()

    def test_all_generating_selection(self, page) -> None:  # noqa: ANN001
        """Selecting all Generating entries disables re-generate."""
        entries = [
            _make_entry(entry_id=1, status="Generating"),
            _make_entry(entry_id=2, status="Generating"),
        ]
        _populate_table(page, entries)
        page.table.selectAll()
        assert not page.re_generate_btn.isEnabled()

    def test_mixed_done_and_failed(self, page) -> None:  # noqa: ANN001
        """Mixed Done+Failed enables re-generate and delete."""
        entries = [
            _make_entry(entry_id=1, status="Done"),
            _make_entry(entry_id=2, status="Failed"),
        ]
        _populate_table(page, entries)
        page.table.selectAll()
        assert page.re_generate_btn.isEnabled()
        assert page.delete_btn.isEnabled()

    def test_mixed_failed_and_pending(self, page) -> None:  # noqa: ANN001
        """Mixed Failed+Pending disables re-generate."""
        entries = [
            _make_entry(entry_id=1, status="Failed"),
            _make_entry(entry_id=2, status="Pending"),
        ]
        _populate_table(page, entries)
        page.table.selectAll()
        assert not page.re_generate_btn.isEnabled()

    def test_mixed_done_failed_generating(self, page) -> None:  # noqa: ANN001
        """Mixed Done+Failed+Generating disables re-generate."""
        entries = [
            _make_entry(entry_id=1, status="Done"),
            _make_entry(entry_id=2, status="Failed"),
            _make_entry(entry_id=3, status="Generating"),
        ]
        _populate_table(page, entries)
        page.table.selectAll()
        assert not page.re_generate_btn.isEnabled()

    def test_select_then_deselect(self, page) -> None:  # noqa: ANN001
        """Selecting then deselecting disables all buttons."""
        _populate_table(page, [_make_entry(status="Done")])
        page.table.selectRow(0)
        assert page.open_btn.isEnabled()
        page.table.clearSelection()
        page._update_button_states()
        assert not page.open_btn.isEnabled()
        assert not page.re_generate_btn.isEnabled()
        assert not page.delete_btn.isEnabled()


# ===================================================================
# NEW: Re-Generate Edge Cases
# ===================================================================


class TestReGenerateEdgeCases:
    """Tests for re-generate edge cases."""

    @patch(f"{_MOD}.Path.exists", return_value=True)
    def test_re_generate_single_correct_task(
        self,
        mock_exists,
        page,
        qtbot,  # noqa: ANN001
    ) -> None:
        """Re-generate single file emits correct task tuple."""
        _populate_table(
            page,
            [_make_entry(entry_id=42, source_path="/src/s.srt", status="Done")],
        )
        page.table.selectRow(0)
        with qtbot.waitSignal(page.re_generate_requested, timeout=1000) as sig:
            page.on_re_generate()
        assert sig.args[0] == [(42, "/src/s.srt")]

    @patch(f"{_MOD}.Path.exists", side_effect=[True, False])
    @patch(f"{_MOD}.CustomMessageDialog.show_message")
    @patch(f"{_MOD}.delete_voice_entry")
    def test_re_generate_second_file_missing(
        self,
        mock_delete,
        mock_msg,
        mock_exists,
        page,
        qtbot,  # noqa: ANN001
    ) -> None:
        """Second file missing stops re-generate and shows error."""
        entries = [
            _make_entry(entry_id=1, source_path="/src/a.srt", status="Done"),
            _make_entry(entry_id=2, source_path="/src/gone.srt", status="Done"),
        ]
        _populate_table(page, entries)
        page.table.selectAll()
        with (
            patch(f"{_MOD}.get_voice_fingerprint", return_value=(0, 0, "x")),
            patch(f"{_MOD}.get_voice_history", return_value=[]),
        ):
            page.on_re_generate()
        mock_msg.assert_called_once()


# ===================================================================
# NEW: Search Filtering Extended
# ===================================================================


class TestSearchFilteringExtended:
    """Extended search filtering tests."""

    def test_search_multiple_matches(self, page) -> None:  # noqa: ANN001
        """Search returns multiple matching entries."""
        entries = [
            _make_entry(entry_id=1, name="speech_part1.srt"),
            _make_entry(entry_id=2, name="speech_part2.srt"),
            _make_entry(entry_id=3, name="other.srt"),
        ]
        page.search_input.setText("speech")
        _populate_table(page, entries)
        assert page.table.rowCount() == 2  # noqa: PLR2004

    def test_search_by_extension(self, page) -> None:  # noqa: ANN001
        """Search matches file extension."""
        entries = [
            _make_entry(entry_id=1, name="file.srt"),
            _make_entry(entry_id=2, name="file.vtt"),
        ]
        page.search_input.setText(".vtt")
        _populate_table(page, entries)
        assert page.table.rowCount() == 1

    def test_search_clear_restores_all(self, page) -> None:  # noqa: ANN001
        """Clearing search shows all entries again."""
        entries = [_make_entry(entry_id=1), _make_entry(entry_id=2)]
        page.search_input.setText("nomatch")
        _populate_table(page, entries)
        assert page.table.rowCount() == 0
        page.search_input.setText("")
        _populate_table(page, entries)
        assert page.table.rowCount() == 2  # noqa: PLR2004

    def test_search_with_dots(self, page) -> None:  # noqa: ANN001
        """Search handles dots in queries."""
        entries = [_make_entry(entry_id=1, name="file.v2.srt")]
        page.search_input.setText("v2.srt")
        _populate_table(page, entries)
        assert page.table.rowCount() == 1

    def test_search_mixed_case(self, page) -> None:  # noqa: ANN001
        """Search works with mixed case."""
        entries = [_make_entry(entry_id=1, name="MySpeech.SRT")]
        page.search_input.setText("myspeech")
        _populate_table(page, entries)
        assert page.table.rowCount() == 1


# ===================================================================
# NEW: Theme and Language Extended
# ===================================================================


class TestThemeAndLanguageExtended:
    """Extended tests for apply_theme and apply_language."""

    def test_apply_language_preserves_data(self, page) -> None:  # noqa: ANN001
        """apply_language preserves existing table data."""
        entries = [_make_entry(entry_id=99, name="test.srt")]
        _populate_table(page, entries)
        with (
            patch(f"{_MOD}.get_voice_fingerprint", return_value=(1, 1, "x")),
            patch(f"{_MOD}.get_voice_history", return_value=entries),
        ):
            page.apply_language()
        assert page.table.rowCount() == 1

    def test_apply_theme_updates_highlight_delegate(self, page) -> None:  # noqa: ANN001
        """apply_theme updates the highlight delegate selected color."""
        with (
            patch(f"{_MOD}.get_voice_fingerprint", return_value=None),
            patch(f"{_MOD}.get_voice_history", return_value=[]),
        ):
            page.apply_theme()
        assert page.highlight_delegate is not None


# ===================================================================
# NEW: Open File Extended
# ===================================================================


class TestOpenFileExtended:
    """Extended tests for open file."""

    @patch(f"{_MOD}.QDesktopServices.openUrl")
    @patch(f"{_MOD}.Path.exists", return_value=True)
    def test_open_multiple_files(
        self,
        mock_exists,
        mock_open,
        page,  # noqa: ANN001
    ) -> None:
        """Opens multiple selected files."""
        entries = [
            _make_entry(entry_id=1, output_path="/out/a.mp3"),
            _make_entry(entry_id=2, output_path="/out/b.mp3"),
        ]
        _populate_table(page, entries)
        page.table.selectAll()
        page.on_open_file()
        assert mock_open.call_count == 2  # noqa: PLR2004

    def test_open_file_none_output(self, page) -> None:  # noqa: ANN001
        """Open file with None output path doesn't crash."""
        _populate_table(page, [_make_entry(output_path=None)])
        page.table.selectRow(0)
        page.on_open_file()  # Should not raise


# ===================================================================
# NEW: Large Dataset
# ===================================================================


class TestLargeDataset:
    """Tests with larger datasets."""

    def test_ten_entries(self, page) -> None:  # noqa: ANN001
        """Handles 10 entries correctly."""
        entries = [_make_entry(entry_id=i, name=f"file{i}.srt") for i in range(1, 11)]
        _populate_table(page, entries)
        assert page.table.rowCount() == 10  # noqa: PLR2004

    def test_select_all_in_large_dataset(self, page) -> None:  # noqa: ANN001
        """Select all in large dataset selects all rows."""
        entries = [_make_entry(entry_id=i) for i in range(1, 11)]
        _populate_table(page, entries)
        page.table.selectAll()
        selected_rows = {item.row() for item in page.table.selectedItems()}
        assert len(selected_rows) == 10  # noqa: PLR2004

    def test_search_in_large_dataset(self, page) -> None:  # noqa: ANN001
        """Search works correctly in large datasets."""
        entries = [_make_entry(entry_id=i, name=f"file{i}.srt") for i in range(1, 11)]
        page.search_input.setText("file5")
        _populate_table(page, entries)
        assert page.table.rowCount() == 1

    def test_mixed_statuses_large(self, page) -> None:  # noqa: ANN001
        """Large dataset with mixed statuses handles button states."""
        statuses = ["Done", "Failed", "Pending", "Generating"]
        entries = [_make_entry(entry_id=i, status=statuses[i % 4]) for i in range(8)]
        _populate_table(page, entries)
        page.table.selectAll()
        assert page.delete_btn.isEnabled()
        assert not page.re_generate_btn.isEnabled()


# ===================================================================
# NEW: Delete Extended
# ===================================================================


class TestDeleteExtended:
    """Extended tests for delete operations."""

    @patch(f"{_MOD}.delete_voice_entry", return_value=None)
    @patch(f"{_MOD}.CustomConfirmDialog.confirm", return_value=True)
    def test_delete_with_none_paths(
        self,
        mock_confirm,
        mock_delete,
        page,  # noqa: ANN001
    ) -> None:
        """Delete handles entries with None output paths."""
        _populate_table(page, [_make_entry(entry_id=1)])
        page.table.selectRow(0)
        with (
            patch(f"{_MOD}.get_voice_fingerprint", return_value=(0, 0, "x")),
            patch(f"{_MOD}.get_voice_history", return_value=[]),
        ):
            page.on_delete_selected()
        mock_delete.assert_called_once()

    @patch(f"{_MOD}.Path.is_file", return_value=True)
    @patch(f"{_MOD}.Path.unlink")
    @patch(f"{_MOD}.delete_voice_entry", return_value="/out/speech.mp3")
    @patch(f"{_MOD}.CustomConfirmDialog.confirm", return_value=True)
    def test_delete_five_entries(
        self,
        mock_confirm,
        mock_delete,
        mock_unlink,
        mock_is_file,
        page,  # noqa: ANN001
    ) -> None:
        """Deleting five entries calls delete five times."""
        entries = [_make_entry(entry_id=i) for i in range(1, 6)]
        _populate_table(page, entries)
        page.table.selectAll()
        with (
            patch(f"{_MOD}.get_voice_fingerprint", return_value=(0, 0, "x")),
            patch(f"{_MOD}.get_voice_history", return_value=[]),
        ):
            page.on_delete_selected()
        assert mock_delete.call_count == 5  # noqa: PLR2004


# ===================================================================
# NEW: Sorting Behavior Extended
# ===================================================================


class TestSortingBehaviorExtended:
    """Extended tests for table sorting."""

    def test_sort_by_size_ascending(self, page) -> None:  # noqa: ANN001
        """Sorting by size column orders rows numerically."""
        entries = [
            _make_entry(entry_id=1, name="big.srt", file_size=10000),
            _make_entry(entry_id=2, name="small.srt", file_size=100),
        ]
        _populate_table(page, entries)
        page.table.sortByColumn(1, Qt.SortOrder.AscendingOrder)
        first_id = page.table.item(0, 0).data(Qt.ItemDataRole.UserRole)
        assert first_id == 2  # noqa: PLR2004

    def test_sort_by_name_ascending(self, page) -> None:  # noqa: ANN001
        """Sorting by name column orders alphabetically."""
        entries = [
            _make_entry(entry_id=1, name="Zebra.srt"),
            _make_entry(entry_id=2, name="Apple.srt"),
        ]
        _populate_table(page, entries)
        page.table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        assert page.table.item(0, 0).text() == "Apple.srt"

    def test_sort_by_date_descending(self, page) -> None:  # noqa: ANN001
        """Sorting by date column descending puts newest first."""
        entries = [
            _make_entry(entry_id=1, created_at="2026-01-01 10:00:00"),
            _make_entry(entry_id=2, created_at="2026-12-31 10:00:00"),
        ]
        _populate_table(page, entries)
        page.table.sortByColumn(3, Qt.SortOrder.DescendingOrder)
        first_id = page.table.item(0, 0).data(Qt.ItemDataRole.UserRole)
        assert first_id == 2  # noqa: PLR2004

    def test_header_click_different_columns(self, page) -> None:  # noqa: ANN001
        """Clicking any header column index clears selection."""
        _populate_table(page, [_make_entry()])
        page.table.selectRow(0)
        for col in range(page.table.columnCount()):
            page._on_header_clicked(col)
            assert len(page.table.selectedItems()) == 0


# ===================================================================
# NEW: Fingerprint and Timer
# ===================================================================


class TestFingerprintAndTimer:
    """Tests for fingerprint and timer behavior."""

    def test_timer_interval(self, page) -> None:  # noqa: ANN001
        """Background timer has 1000ms interval."""
        assert page.timer.interval() == 1000  # noqa: PLR2004

    def test_search_timer_interval(self, page) -> None:  # noqa: ANN001
        """Search timer has SEARCH_DEBOUNCE_MS interval."""
        from src.constants import SEARCH_DEBOUNCE_MS  # noqa: PLC0415

        assert page.search_timer.interval() == SEARCH_DEBOUNCE_MS

    def test_fingerprint_change_triggers_refresh(self, page) -> None:  # noqa: ANN001
        """Changing fingerprint triggers a refresh."""
        entries = [_make_entry(entry_id=1)]
        page._last_fingerprint = (0, 0, "old")
        page.show()
        history_mock = MagicMock(return_value=entries)
        with (
            patch(f"{_MOD}.get_voice_fingerprint", return_value=(1, 1, "new")),
            patch(f"{_MOD}.get_voice_history", history_mock),
        ):
            page.refresh_history(force=False)
            history_mock.assert_called_once()

    def test_last_fingerprint_updated(self, page) -> None:  # noqa: ANN001
        """_last_fingerprint is updated after refresh."""
        fp = (5, 5, "hash123")
        with (
            patch(f"{_MOD}.get_voice_fingerprint", return_value=fp),
            patch(f"{_MOD}.get_voice_history", return_value=[]),
        ):
            page.refresh_history(force=True)
        assert page._last_fingerprint == fp


# ===================================================================
# NEW: Button Fixed Height
# ===================================================================


class TestButtonFixedHeight:
    """Tests for button fixed height consistency."""

    def test_all_buttons_have_fixed_height(self, page) -> None:  # noqa: ANN001
        """All action buttons have HEIGHT_CONTROL fixed height."""
        from src.constants import HEIGHT_CONTROL  # noqa: PLC0415

        for btn in [page.open_btn, page.re_generate_btn, page.delete_btn]:
            assert btn.maximumHeight() == HEIGHT_CONTROL
            assert btn.minimumHeight() == HEIGHT_CONTROL

    def test_search_input_has_fixed_height(self, page) -> None:  # noqa: ANN001
        """Search input has HEIGHT_CONTROL fixed height."""
        from src.constants import HEIGHT_CONTROL  # noqa: PLC0415

        assert page.search_input.maximumHeight() == HEIGHT_CONTROL
        assert page.search_input.minimumHeight() == HEIGHT_CONTROL


# ===================================================================
# NEW: Multi Selection Preserved
# ===================================================================


class TestMultiSelectionPreserved:
    """Tests for multi-selection preservation across refreshes."""

    def test_multi_selection_preserved(self, page) -> None:  # noqa: ANN001
        """Multiple selections are preserved across refresh."""
        entries = [_make_entry(entry_id=i) for i in range(1, 4)]
        _populate_table(page, entries)
        page.table.selectAll()
        _populate_table(page, entries)
        selected_ids = set()
        for item in page.table.selectedItems():
            if item.column() == 0:
                selected_ids.add(item.data(Qt.ItemDataRole.UserRole))
        assert selected_ids == {1, 2, 3}


# ===================================================================
# NEW: ShowEvent Trigger
# ===================================================================


class TestShowEventTrigger:
    """Tests that showEvent triggers refresh_history(force=True)."""

    def test_show_event_calls_force_refresh(self, page) -> None:  # noqa: ANN001
        """showEvent() calls refresh_history(force=True)."""
        with patch.object(page, "refresh_history") as mock_refresh:
            page.showEvent(None)
            mock_refresh.assert_called_once_with(force=True)


# ===================================================================
# NEW: Unicode and Long Filenames
# ===================================================================


class TestUnicodeAndLongFilenames:
    """Tests for edge cases with unicode and very long filenames."""

    def test_unicode_filename(self, page) -> None:  # noqa: ANN001
        """Unicode filenames are displayed correctly."""
        _populate_table(page, [_make_entry(name="\u97f3\u58f0\u6587\u4ef6.srt")])
        assert page.table.item(0, 0).text() == "\u97f3\u58f0\u6587\u4ef6.srt"

    def test_very_long_filename(self, page) -> None:  # noqa: ANN001
        """Very long filenames are stored without truncation."""
        long_name = "a" * 500 + ".srt"
        _populate_table(page, [_make_entry(name=long_name)])
        assert page.table.item(0, 0).text() == long_name

    def test_empty_filename(self, page) -> None:  # noqa: ANN001
        """Empty filename is stored without error."""
        _populate_table(page, [_make_entry(name="")])
        assert page.table.item(0, 0).text() == ""

    def test_unicode_search(self, page) -> None:  # noqa: ANN001
        """Search works with unicode characters."""
        entries = [
            _make_entry(entry_id=1, name="\u97f3\u58f0.srt"),
            _make_entry(entry_id=2, name="english.srt"),
        ]
        page.search_input.setText("\u97f3\u58f0")
        _populate_table(page, entries)
        assert page.table.rowCount() == 1


# ===================================================================
# NEW: Error Banner Edge Cases
# ===================================================================


class TestErrorBannerEdgeCases:
    """Tests for error banner behavior in various scenarios."""

    def test_error_hidden_when_no_error_message(self, page) -> None:  # noqa: ANN001
        """Error banner is hidden for failed entry without error_message."""
        _populate_table(page, [_make_entry(status="Failed", error_message=None)])
        page.table.selectRow(0)
        assert not page.error_frame.isVisible()

    def test_error_hidden_after_deselection(self, page) -> None:  # noqa: ANN001
        """Error banner is hidden after deselecting a failed entry."""
        page.show()
        _populate_table(
            page,
            [_make_entry(status="Failed", error_message="ERR_TEST")],
        )
        page.table.selectRow(0)
        assert page.error_frame.isVisible()
        page.table.clearSelection()
        page._update_button_states()
        assert not page.error_frame.isVisible()

    def test_error_hidden_when_multiple_selected(self, page) -> None:  # noqa: ANN001
        """Error banner is hidden when multiple entries are selected."""
        entries = [
            _make_entry(entry_id=1, status="Failed", error_message="ERR_1"),
            _make_entry(entry_id=2, status="Failed", error_message="ERR_2"),
        ]
        _populate_table(page, entries)
        page.table.selectAll()
        assert not page.error_frame.isVisible()


# ===================================================================
# NEW: Status Colors
# ===================================================================


class TestStatusColors:
    """Tests for correct status color assignment."""

    def test_done_status_has_success_color(self, page) -> None:  # noqa: ANN001
        """Done status foreground uses success color."""
        from PySide6.QtGui import QColor  # noqa: PLC0415

        from src.constants import color as get_color  # noqa: PLC0415

        _populate_table(page, [_make_entry(status="Done")])
        status_item = page.table.item(0, 2)
        assert status_item.foreground().color() == QColor(get_color("success"))

    def test_failed_status_has_error_color(self, page) -> None:  # noqa: ANN001
        """Failed status foreground uses error color."""
        from PySide6.QtGui import QColor  # noqa: PLC0415

        from src.constants import color as get_color  # noqa: PLC0415

        _populate_table(page, [_make_entry(status="Failed")])
        status_item = page.table.item(0, 2)
        assert status_item.foreground().color() == QColor(get_color("error"))

    def test_generating_status_has_primary_color(self, page) -> None:  # noqa: ANN001
        """Generating status foreground uses primary color."""
        from PySide6.QtGui import QColor  # noqa: PLC0415

        from src.constants import color as get_color  # noqa: PLC0415

        _populate_table(page, [_make_entry(status="Generating")])
        status_item = page.table.item(0, 2)
        assert status_item.foreground().color() == QColor(get_color("primary"))

    def test_status_text_uses_display_status(self, page) -> None:  # noqa: ANN001
        """Status column text uses display_status for translation."""
        from src.constants.history import display_status  # noqa: PLC0415

        _populate_table(page, [_make_entry(status="Done")])
        status_item = page.table.item(0, 2)
        assert status_item.text() == display_status("Done")


# ===================================================================
# NEW: Page Is A QWidget
# ===================================================================


class TestPageIsQWidget:
    """Tests that the page is a proper QWidget with expected elements."""

    def test_is_qwidget_instance(self, page) -> None:  # noqa: ANN001
        """VoiceHistoryPage is a QWidget."""
        from PySide6.QtWidgets import QWidget  # noqa: PLC0415

        assert isinstance(page, QWidget)

    def test_has_error_label(self, page) -> None:  # noqa: ANN001
        """Page has an error label widget."""
        assert hasattr(page, "error_label")

    def test_main_layout_no_margins(self, page) -> None:  # noqa: ANN001
        """Main layout has zero margins."""
        margins = page.main_layout.contentsMargins()
        assert margins.left() == 0
        assert margins.top() == 0
        assert margins.right() == 0
        assert margins.bottom() == 0


# ===================================================================
# NEW: Refresh Not Visible
# ===================================================================


class TestRefreshNotVisible:
    """Tests for refresh behavior based on visibility."""

    def test_refresh_not_visible_no_force_skips(self, page) -> None:  # noqa: ANN001
        """refresh_history skips when page is not visible and force=False."""
        page.hide()
        history_mock = MagicMock(return_value=[_make_entry()])
        with (
            patch(f"{_MOD}.get_voice_fingerprint", return_value=(1, 1, "new")),
            patch(f"{_MOD}.get_voice_history", history_mock),
        ):
            page.refresh_history(force=False)
            history_mock.assert_not_called()

    def test_fingerprint_none_always_refreshes(self, page) -> None:  # noqa: ANN001
        """When fingerprint is None, always refreshes."""
        history_mock = MagicMock(return_value=[_make_entry()])
        page._last_fingerprint = (1, 1, "old")
        with (
            patch(f"{_MOD}.get_voice_fingerprint", return_value=None),
            patch(f"{_MOD}.get_voice_history", history_mock),
        ):
            page.show()
            page.refresh_history(force=False)
            history_mock.assert_called()


# ===================================================================
# NEW: Error Banner Extended
# ===================================================================


class TestErrorBannerExtended:
    """Extended error banner tests."""

    def test_error_shown_for_single_failed_with_message(self, page) -> None:  # noqa: ANN001
        """Error banner shown for single failed entry with error message."""
        page.show()
        _populate_table(
            page,
            [_make_entry(status="Failed", error_message="TIMEOUT_ERROR")],
        )
        page.table.selectRow(0)
        assert page.error_frame.isVisible()

    def test_error_hidden_for_pending_status(self, page) -> None:  # noqa: ANN001
        """Error banner hidden for Pending entry."""
        _populate_table(page, [_make_entry(status="Pending")])
        page.table.selectRow(0)
        assert not page.error_frame.isVisible()

    def test_error_hidden_for_generating_status(self, page) -> None:  # noqa: ANN001
        """Error banner hidden for Generating entry."""
        _populate_table(page, [_make_entry(status="Generating")])
        page.table.selectRow(0)
        assert not page.error_frame.isVisible()


# ===================================================================
# NEW: Data Storage Verification
# ===================================================================


class TestDataStorageVerification:
    """Tests for data stored in table items."""

    def test_stores_source_path_data(self, page) -> None:  # noqa: ANN001
        """Source path is accessible from stored data."""
        _populate_table(page, [_make_entry(source_path="/src/test.srt")])
        item = page.table.item(0, 0)
        assert item.data(Qt.ItemDataRole.UserRole + 2) == "/src/test.srt"

    def test_status_raw_value_stored(self, page) -> None:  # noqa: ANN001
        """Raw status string is stored in UserRole on status column."""
        _populate_table(page, [_make_entry(status="Generating")])
        status_item = page.table.item(0, 2)
        assert status_item.data(Qt.ItemDataRole.UserRole) == "Generating"

    def test_date_column_non_empty(self, page) -> None:  # noqa: ANN001
        """Date column has formatted non-empty text."""
        _populate_table(page, [_make_entry()])
        assert page.table.item(0, 3).text()

    def test_size_column_for_large_file(self, page) -> None:  # noqa: ANN001
        """Size column formats large file sizes."""
        _populate_table(page, [_make_entry(file_size=1048576)])
        size_text = page.table.item(0, 1).text()
        assert size_text

    def test_entry_id_stored(self, page) -> None:  # noqa: ANN001
        """Entry ID is stored in UserRole on column 0."""
        _populate_table(page, [_make_entry(entry_id=77)])
        item = page.table.item(0, 0)
        assert item.data(Qt.ItemDataRole.UserRole) == 77  # noqa: PLR2004

    def test_output_path_stored(self, page) -> None:  # noqa: ANN001
        """Output path is stored in UserRole+1 on column 0."""
        _populate_table(page, [_make_entry(output_path="/out/voice.mp3")])
        item = page.table.item(0, 0)
        assert item.data(Qt.ItemDataRole.UserRole + 1) == "/out/voice.mp3"

    def test_error_message_stored(self, page) -> None:  # noqa: ANN001
        """Error message is stored in UserRole+3 on column 0."""
        _populate_table(page, [_make_entry(error_message="ERR_TTS")])
        item = page.table.item(0, 0)
        assert item.data(Qt.ItemDataRole.UserRole + 3) == "ERR_TTS"


# ===================================================================
# NEW: Page Structure Extended
# ===================================================================


class TestPageStructureExtended:
    """Extended tests for page structure."""

    def test_has_search_timer(self, page) -> None:  # noqa: ANN001
        """Page has a debounced search timer."""
        assert hasattr(page, "search_timer")
        assert page.search_timer.isSingleShot()

    def test_has_background_timer(self, page) -> None:  # noqa: ANN001
        """Page has a background refresh timer."""
        assert hasattr(page, "timer")
        assert page.timer.isActive()

    def test_search_input_max_width(self, page) -> None:  # noqa: ANN001
        """Search input has a maximum width of 360."""
        assert page.search_input.maximumWidth() == 360  # noqa: PLR2004

    def test_buttons_have_cursor(self, page) -> None:  # noqa: ANN001
        """All action buttons have pointing hand cursor."""
        for btn in [page.open_btn, page.re_generate_btn, page.delete_btn]:
            assert btn.cursor().shape() == Qt.CursorShape.PointingHandCursor

    def test_emoji_filename(self, page) -> None:  # noqa: ANN001
        """Emoji in filenames are displayed correctly."""
        _populate_table(page, [_make_entry(name="\U0001f3b5 audio.srt")])
        assert page.table.item(0, 0).text() == "\U0001f3b5 audio.srt"


# ===================================================================
# NEW: Re-Generate Multiple Extended
# ===================================================================


class TestReGenerateMultipleExtended:
    """Extended tests for re-generating multiple files."""

    @patch(f"{_MOD}.Path.exists", return_value=True)
    def test_re_generate_three_files(
        self,
        mock_exists,
        page,
        qtbot,  # noqa: ANN001
    ) -> None:
        """Re-generate with three selected emits three tasks."""
        entries = [
            _make_entry(entry_id=i, source_path=f"/src/v{i}.srt", status="Done")
            for i in range(1, 4)
        ]
        _populate_table(page, entries)
        page.table.selectAll()
        with qtbot.waitSignal(page.re_generate_requested, timeout=1000) as sig:
            page.on_re_generate()
        assert len(sig.args[0]) == 3  # noqa: PLR2004

    @patch(f"{_MOD}.Path.exists", return_value=True)
    def test_re_generate_failed_entries(
        self,
        mock_exists,
        page,
        qtbot,  # noqa: ANN001
    ) -> None:
        """Re-generate works with failed entries."""
        entries = [
            _make_entry(entry_id=1, source_path="/src/v1.srt", status="Failed"),
            _make_entry(entry_id=2, source_path="/src/v2.srt", status="Failed"),
        ]
        _populate_table(page, entries)
        page.table.selectAll()
        with qtbot.waitSignal(page.re_generate_requested, timeout=1000) as sig:
            page.on_re_generate()
        assert len(sig.args[0]) == 2  # noqa: PLR2004


# ===================================================================
# NEW: Delete File Cleanup Extended
# ===================================================================


class TestDeleteFileCleanupExtended:
    """Extended tests for file cleanup during deletion."""

    @patch(f"{_MOD}.Path.is_file", return_value=True)
    @patch(f"{_MOD}.Path.unlink")
    @patch(f"{_MOD}.delete_voice_entry", return_value="/out/voice.mp3")
    @patch(f"{_MOD}.CustomConfirmDialog.confirm", return_value=True)
    def test_delete_three_entries(
        self,
        mock_confirm,
        mock_delete,
        mock_unlink,
        mock_is_file,
        page,  # noqa: ANN001
    ) -> None:
        """Deleting three entries calls delete for each."""
        entries = [_make_entry(entry_id=i) for i in range(1, 4)]
        _populate_table(page, entries)
        page.table.selectAll()
        with (
            patch(f"{_MOD}.get_voice_fingerprint", return_value=(0, 0, "x")),
            patch(f"{_MOD}.get_voice_history", return_value=[]),
        ):
            page.on_delete_selected()
        assert mock_delete.call_count == 3  # noqa: PLR2004


# ===================================================================
# NEW: Status Colors Extended
# ===================================================================


class TestStatusColorsExtended:
    """Extended tests for status colors."""

    def test_pending_status_has_text_primary_color(self, page) -> None:  # noqa: ANN001
        """Pending status foreground uses text_primary color."""
        from PySide6.QtGui import QColor  # noqa: PLC0415

        from src.constants import color as get_color  # noqa: PLC0415

        _populate_table(page, [_make_entry(status="Pending")])
        status_item = page.table.item(0, 2)
        assert status_item.foreground().color() == QColor(get_color("text_primary"))

    def test_status_text_uses_display_status_failed(self, page) -> None:  # noqa: ANN001
        """Failed status text uses display_status."""
        from src.constants.history import display_status  # noqa: PLC0415

        _populate_table(page, [_make_entry(status="Failed")])
        status_item = page.table.item(0, 2)
        assert status_item.text() == display_status("Failed")


# ===================================================================
# NEW: Table Structure Verification
# ===================================================================


class TestTableStructureVerification:
    """Tests for table structure and item properties."""

    def test_status_column_centered(self, page) -> None:  # noqa: ANN001
        """Status column items are center-aligned."""
        _populate_table(page, [_make_entry()])
        status_item = page.table.item(0, 2)
        assert status_item.textAlignment() & Qt.AlignmentFlag.AlignCenter

    def test_table_row_selection_mode(self, page) -> None:  # noqa: ANN001
        """Table uses row-based selection."""
        assert (
            page.table.selectionBehavior() == QTableWidget.SelectionBehavior.SelectRows
        )

    def test_error_frame_hidden_initially_check(self, page) -> None:  # noqa: ANN001
        """Error banner is hidden at construction time."""
        assert not page.error_frame.isVisible()

    def test_size_zero_shows_0b(self, page) -> None:  # noqa: ANN001
        """Zero file size shows '0 B'."""
        _populate_table(page, [_make_entry(file_size=0)])
        assert page.table.item(0, 1).text() == "0 B"

    def test_file_name_displayed_correctly(self, page) -> None:  # noqa: ANN001
        """File name is shown as column 0 text."""
        _populate_table(page, [_make_entry(name="my_audio.srt")])
        assert page.table.item(0, 0).text() == "my_audio.srt"

    def test_table_column_count_is_4(self, page) -> None:  # noqa: ANN001
        """Table has 4 columns."""
        assert page.table.columnCount() == 4  # noqa: PLR2004

    def test_search_whitespace_shows_all(self, page) -> None:  # noqa: ANN001
        """Whitespace-only search shows all entries."""
        entries = [_make_entry(entry_id=1), _make_entry(entry_id=2)]
        page.search_input.setText("   ")
        _populate_table(page, entries)
        assert page.table.rowCount() == 2  # noqa: PLR2004

    def test_search_special_characters(self, page) -> None:  # noqa: ANN001
        """Search handles special characters."""
        entries = [_make_entry(entry_id=1, name="file (1).srt")]
        page.search_input.setText("(1)")
        _populate_table(page, entries)
        assert page.table.rowCount() == 1

    def test_search_partial_match(self, page) -> None:  # noqa: ANN001
        """Search matches partial file names."""
        entries = [_make_entry(entry_id=1, name="my_long_speech_file.srt")]
        page.search_input.setText("speech")
        _populate_table(page, entries)
        assert page.table.rowCount() == 1

    def test_search_uppercase(self, page) -> None:  # noqa: ANN001
        """Search is case-insensitive with uppercase query."""
        entries = [_make_entry(entry_id=1, name="audio.srt")]
        page.search_input.setText("AUDIO")
        _populate_table(page, entries)
        assert page.table.rowCount() == 1

    def test_search_no_match(self, page) -> None:  # noqa: ANN001
        """Search with no match shows 0 rows."""
        entries = [_make_entry(entry_id=1)]
        page.search_input.setText("zzzznotfound")
        _populate_table(page, entries)
        assert page.table.rowCount() == 0

    def test_search_updates_highlight_delegate(self, page) -> None:  # noqa: ANN001
        """Search text is passed to the highlight delegate."""
        entries = [_make_entry(entry_id=1, name="test.srt")]
        page.search_input.setText("test")
        _populate_table(page, entries)
        assert page.highlight_delegate.search_text == "test"

    def test_selection_restored_after_refresh(self, page) -> None:  # noqa: ANN001
        """Selected entry IDs are restored after refresh."""
        entries = [_make_entry(entry_id=1), _make_entry(entry_id=2)]
        _populate_table(page, entries)
        page.table.selectRow(0)
        _populate_table(page, entries)
        selected_ids = set()
        for item in page.table.selectedItems():
            if item.column() == 0:
                selected_ids.add(item.data(Qt.ItemDataRole.UserRole))
        assert len(selected_ids) > 0

    def test_refresh_empty_history_shows_zero(self, page) -> None:  # noqa: ANN001
        """Empty history list results in 0 rows."""
        _populate_table(page, [])
        assert page.table.rowCount() == 0

    def test_refresh_clears_on_none_voice(self, page) -> None:  # noqa: ANN001
        """Table is cleared when get_voice_history returns None."""
        with (
            patch(f"{_MOD}.get_voice_fingerprint", return_value=(0, 0, "x")),
            patch(f"{_MOD}.get_voice_history", return_value=None),
        ):
            page.refresh_history(force=True)
        assert page.table.rowCount() == 0


# ===================================================================
# NEW: Apply Theme Extended
# ===================================================================


class TestApplyThemeExtended:
    """Extended tests for apply_theme."""

    def test_apply_language_preserves_data(self, page) -> None:  # noqa: ANN001
        """apply_language preserves existing table data."""
        entries = [_make_entry(entry_id=99, name="test.srt")]
        _populate_table(page, entries)
        with (
            patch(f"{_MOD}.get_voice_fingerprint", return_value=(1, 1, "x")),
            patch(f"{_MOD}.get_voice_history", return_value=entries),
        ):
            page.apply_language()
        assert page.table.rowCount() == 1

    def test_apply_theme_sets_table_style(self, page) -> None:  # noqa: ANN001
        """apply_theme sets non-empty table stylesheet."""
        with (
            patch(f"{_MOD}.get_voice_fingerprint", return_value=None),
            patch(f"{_MOD}.get_voice_history", return_value=[]),
        ):
            page.apply_theme()
        assert page.table.styleSheet()

    def test_apply_theme_sets_search_style(self, page) -> None:  # noqa: ANN001
        """apply_theme sets non-empty search input stylesheet."""
        with (
            patch(f"{_MOD}.get_voice_fingerprint", return_value=None),
            patch(f"{_MOD}.get_voice_history", return_value=[]),
        ):
            page.apply_theme()
        assert page.search_input.styleSheet()

    def test_apply_language_updates_headers(self, page) -> None:  # noqa: ANN001
        """apply_language updates all column header texts."""
        with (
            patch(f"{_MOD}.get_voice_fingerprint", return_value=None),
            patch(f"{_MOD}.get_voice_history", return_value=[]),
        ):
            page.apply_language()
        for col in range(page.table.columnCount()):
            header = page.table.horizontalHeaderItem(col)
            assert header is not None
            assert len(header.text()) > 0

    def test_apply_language_updates_button_text(self, page) -> None:  # noqa: ANN001
        """apply_language updates button labels."""
        with (
            patch(f"{_MOD}.get_voice_fingerprint", return_value=None),
            patch(f"{_MOD}.get_voice_history", return_value=[]),
        ):
            page.apply_language()
        assert page.open_btn.text()
        assert page.re_generate_btn.text()
        assert page.delete_btn.text()


# ===================================================================
# NEW: Voice History Extended Coverage
# ===================================================================


class TestVoiceHistoryExtendedCoverage:
    """Extended coverage tests for voice history page."""

    def test_error_banner_hidden_on_multi_select(self, page) -> None:  # noqa: ANN001
        """Error banner stays hidden when multiple rows selected."""
        entries = [
            _make_entry(entry_id=1, status="Failed", error_message="ERR"),
            _make_entry(entry_id=2, status="Failed", error_message="ERR2"),
        ]
        _populate_table(page, entries)
        for row in range(2):
            for col in range(page.table.columnCount()):
                item = page.table.item(row, col)
                if item:
                    item.setSelected(True)
        page._update_button_states()
        assert not page.error_frame.isVisible()

    def test_delete_btn_enabled_for_failed_voice(self, page) -> None:  # noqa: ANN001
        """Delete button is enabled for Failed status entries."""
        _populate_table(page, [_make_entry(status="Failed")])
        page.table.selectRow(0)
        assert page.delete_btn.isEnabled()

    def test_re_generate_btn_disabled_for_generating_voice(self, page) -> None:  # noqa: ANN001
        """Re-generate is disabled when a Generating row is selected."""
        _populate_table(page, [_make_entry(status="Generating")])
        page.table.selectRow(0)
        assert not page.re_generate_btn.isEnabled()

    def test_re_generate_btn_disabled_for_pending_voice(self, page) -> None:  # noqa: ANN001
        """Re-generate is disabled when a Pending row is selected."""
        _populate_table(page, [_make_entry(status="Pending")])
        page.table.selectRow(0)
        assert not page.re_generate_btn.isEnabled()

    def test_open_btn_enabled_for_done_voice(self, page) -> None:  # noqa: ANN001
        """Open button is enabled when a Done row is selected."""
        _populate_table(page, [_make_entry(status="Done")])
        page.table.selectRow(0)
        assert page.open_btn.isEnabled()

    def test_search_timer_is_single_shot_voice(self, page) -> None:  # noqa: ANN001
        """Search timer is configured as single-shot."""
        assert page.search_timer.isSingleShot()

    def test_background_timer_not_single_shot_voice(self, page) -> None:  # noqa: ANN001
        """Background refresh timer is not single-shot (repeating)."""
        assert not page.timer.isSingleShot()

    def test_table_selection_mode_extended_voice(self, page) -> None:  # noqa: ANN001
        """Table supports extended (multi) selection mode."""
        from PySide6.QtWidgets import QAbstractItemView  # noqa: PLC0415

        assert (
            page.table.selectionMode()
            == QAbstractItemView.SelectionMode.ExtendedSelection
        )

    def test_table_no_edit_triggers_voice(self, page) -> None:  # noqa: ANN001
        """Table has no edit triggers (read-only)."""
        from PySide6.QtWidgets import QAbstractItemView  # noqa: PLC0415

        assert page.table.editTriggers() == QAbstractItemView.EditTrigger.NoEditTriggers

    def test_error_banner_visible_single_failed_voice(self, page) -> None:  # noqa: ANN001
        """Error banner is not hidden when single failed row is selected."""
        entries = [_make_entry(status="Failed", error_message="QUOTA_ERROR")]
        _populate_table(page, entries)
        page.table.selectRow(0)
        assert not page.error_frame.isHidden()

    def test_error_banner_hidden_for_done_voice(self, page) -> None:  # noqa: ANN001
        """Error banner is hidden when a Done entry is selected."""
        entries = [_make_entry(status="Done")]
        _populate_table(page, entries)
        page.table.selectRow(0)
        assert not page.error_frame.isVisible()

    def test_highlight_delegate_exists_voice(self, page) -> None:  # noqa: ANN001
        """Page has a highlight delegate for file name column."""
        assert page.highlight_delegate is not None

    def test_status_delegate_exists_voice(self, page) -> None:  # noqa: ANN001
        """Page has a status delegate for status column."""
        assert page._status_delegate is not None

    def test_buttons_disabled_initially_voice(self, page) -> None:  # noqa: ANN001
        """All action buttons start disabled when no rows selected."""
        page.table.clearSelection()
        page._update_button_states()
        assert not page.open_btn.isEnabled()
        assert not page.re_generate_btn.isEnabled()
        assert not page.delete_btn.isEnabled()

    def test_main_layout_zero_margins_voice(self, page) -> None:  # noqa: ANN001
        """Main layout has zero margins."""
        margins = page.main_layout.contentsMargins()
        assert margins.left() == 0
        assert margins.top() == 0
        assert margins.right() == 0
        assert margins.bottom() == 0


# ===================================================================
# TestVoiceHistorySignalBlocking — blockSignals & setSortingEnabled
# ===================================================================


class TestVoiceHistorySignalBlocking:
    """Verifies that refresh_history blocks/unblocks signals and sorting."""

    def test_signals_unblocked_after_refresh_with_entries(self, page) -> None:  # noqa: ANN001
        """Signals are unblocked after a normal refresh with entries."""
        _populate_table(page, [_make_entry()])
        assert not page.table.signalsBlocked()

    def test_sorting_enabled_after_refresh_with_entries(self, page) -> None:  # noqa: ANN001
        """Sorting is re-enabled after a normal refresh with entries."""
        _populate_table(page, [_make_entry()])
        assert page.table.isSortingEnabled()

    def test_signals_unblocked_after_refresh_with_empty_data(self, page) -> None:  # noqa: ANN001
        """Signals are unblocked when refresh returns an empty list."""
        _populate_table(page, [])
        assert not page.table.signalsBlocked()

    def test_sorting_enabled_after_refresh_with_empty_data(self, page) -> None:  # noqa: ANN001
        """Sorting is re-enabled when refresh returns an empty list."""
        _populate_table(page, [])
        assert page.table.isSortingEnabled()

    def test_signals_unblocked_after_refresh_with_none(self, page) -> None:  # noqa: ANN001
        """Signals are unblocked when the DB returns None."""
        with (
            patch(
                f"{_MOD}.get_voice_fingerprint",
                return_value=(0, 0, ""),
            ),
            patch(f"{_MOD}.get_voice_history", return_value=None),
        ):
            page.refresh_history(force=True)

        assert not page.table.signalsBlocked()

    def test_sorting_enabled_after_refresh_with_none(self, page) -> None:  # noqa: ANN001
        """Sorting is re-enabled when the DB returns None."""
        with (
            patch(
                f"{_MOD}.get_voice_fingerprint",
                return_value=(0, 0, ""),
            ),
            patch(f"{_MOD}.get_voice_history", return_value=None),
        ):
            page.refresh_history(force=True)

        assert page.table.isSortingEnabled()

    def test_block_signals_called_in_correct_order(self, page) -> None:  # noqa: ANN001
        """blockSignals(True) is called before rebuild and (False) after."""
        calls: list[bool] = []
        original_block = page.table.blockSignals

        def _track(val: bool) -> bool:
            calls.append(val)
            return original_block(val)

        with patch.object(page.table, "blockSignals", side_effect=_track):
            _populate_table(page, [_make_entry()])

        assert True in calls
        assert False in calls
        first_true = calls.index(True)
        last_false = len(calls) - 1 - calls[::-1].index(False)
        assert first_true < last_false

    def test_set_sorting_enabled_called_in_correct_order(self, page) -> None:  # noqa: ANN001
        """setSortingEnabled(False) is called before rebuild, (True) after."""
        calls: list[bool] = []
        original_sort = page.table.setSortingEnabled

        def _track(val: bool) -> None:
            calls.append(val)
            original_sort(val)

        with patch.object(page.table, "setSortingEnabled", side_effect=_track):
            _populate_table(page, [_make_entry()])

        assert False in calls
        assert True in calls
        first_false = calls.index(False)
        last_true = len(calls) - 1 - calls[::-1].index(True)
        assert first_false < last_true
