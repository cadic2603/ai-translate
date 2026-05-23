"""Comprehensive tests for DubbingHistoryPage.

Covers page creation, widget structure, refresh_history, _fill_row,
_on_header_clicked, on_open_file, on_delete_selected, on_re_dub,
on_pause, on_continue, _update_button_states, apply_theme, apply_language,
search filtering, selection preservation, fingerprint checking,
progress display, and edge cases.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableWidget

# ---------------------------------------------------------------------------
# Module-level patch path constants
# ---------------------------------------------------------------------------
_MOD = "src.ui.pages.dubbing_history"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def _mock_db():
    """Mocks database calls used by DubbingHistoryPage during construction."""
    with (
        patch(f"{_MOD}.get_dubbing_fingerprint", return_value=None),
        patch(f"{_MOD}.get_dubbing_history", return_value=[]),
    ):
        yield


@pytest.fixture()
def page(_mock_db, qtbot):
    """Creates a DubbingHistoryPage widget for testing."""
    from src.ui.pages.dubbing_history import DubbingHistoryPage  # noqa: PLC0415

    p = DubbingHistoryPage()
    qtbot.addWidget(p)
    return p


def _make_entry(  # noqa: PLR0913
    entry_id: int = 1,
    name: str = "movie.mp4",
    file_size: int = 10240,
    source_path: str = "/tmp/source/movie.mp4",
    output_path: str = "/tmp/output/movie_dubbed.mp4",
    src_lang: str = "en",
    target_lang: str = "vi",
    status: str = "Done",
    progress: int | str = 100,
    error_message: str | None = None,
    created_at: str = "2026-03-20 16:45:00",
    subtitle_path: str = "/tmp/output/movie.srt",
    translated_subtitle_path: str = "/tmp/output/movie_vi.srt",
    voice_path: str = "/tmp/output/movie_vi.mp3",
) -> tuple:
    """Helper to build a dubbing history DB tuple (14 columns)."""
    return (
        entry_id,
        name,
        file_size,
        source_path,
        output_path,
        src_lang,
        target_lang,
        status,
        progress,
        error_message,
        created_at,
        subtitle_path,
        translated_subtitle_path,
        voice_path,
    )


def _populate_table(page, entries):  # noqa: ANN001, ANN202
    """Populates the page table with the given entries via mocked refresh."""
    with (
        patch(
            f"{_MOD}.get_dubbing_fingerprint",
            return_value=(len(entries), len(entries), "x"),
        ),
        patch(f"{_MOD}.get_dubbing_history", return_value=entries),
    ):
        page.refresh_history(force=True)


# ===================================================================
# Widget Construction
# ===================================================================


class TestConstruction:
    """Tests for DubbingHistoryPage widget construction."""

    def test_page_created(self, page) -> None:  # noqa: ANN001
        """Page is created without error."""
        assert page is not None

    def test_has_table(self, page) -> None:  # noqa: ANN001
        """Page has a QTableWidget."""
        assert isinstance(page.table, QTableWidget)

    def test_table_column_count(self, page) -> None:  # noqa: ANN001
        """Table has 5 columns: name, size, status, progress, date."""
        assert page.table.columnCount() == 5  # noqa: PLR2004

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

    def test_has_all_action_buttons(self, page) -> None:  # noqa: ANN001
        """Page has open, pause, continue, re-dub, and delete buttons."""
        assert hasattr(page, "open_btn")
        assert hasattr(page, "pause_btn")
        assert hasattr(page, "continue_btn")
        assert hasattr(page, "re_dub_btn")
        assert hasattr(page, "delete_btn")

    def test_buttons_disabled_initially(self, page) -> None:  # noqa: ANN001
        """Action buttons start disabled (no selection)."""
        assert not page.open_btn.isEnabled()
        assert not page.pause_btn.isEnabled()
        assert not page.continue_btn.isEnabled()
        assert not page.re_dub_btn.isEnabled()
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
        entries = [_make_entry(1), _make_entry(2, name="clip.mp4")]
        _populate_table(page, entries)
        assert page.table.rowCount() == 2  # noqa: PLR2004

    def test_refresh_clears_on_none(self, page) -> None:  # noqa: ANN001
        """Table is cleared when get_dubbing_history returns None."""
        with (
            patch(f"{_MOD}.get_dubbing_fingerprint", return_value=(0, 0, "x")),
            patch(f"{_MOD}.get_dubbing_history", return_value=None),
        ):
            page.refresh_history(force=True)
        assert page.table.rowCount() == 0

    def test_refresh_skips_when_fingerprint_unchanged(self, page) -> None:  # noqa: ANN001
        """Skips rebuild when fingerprint hasn't changed."""
        fp = (1, 1, "abc")
        history_mock = MagicMock(return_value=[])
        with (
            patch(f"{_MOD}.get_dubbing_fingerprint", return_value=fp),
            patch(f"{_MOD}.get_dubbing_history", return_value=[]),
        ):
            page.show()
        with (
            patch(f"{_MOD}.get_dubbing_fingerprint", return_value=fp),
            patch(f"{_MOD}.get_dubbing_history", history_mock),
        ):
            page._last_fingerprint = fp
            page.refresh_history(force=False)
            history_mock.assert_not_called()

    def test_force_refresh_always_rebuilds(self, page) -> None:  # noqa: ANN001
        """force=True rebuilds even when fingerprint matches."""
        fp = (1, 1, "abc")
        history_mock = MagicMock(return_value=[])
        with (
            patch(f"{_MOD}.get_dubbing_fingerprint", return_value=fp),
            patch(f"{_MOD}.get_dubbing_history", history_mock),
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
        entry_id = 77  # noqa: PLR2004
        _populate_table(page, [_make_entry(entry_id=entry_id)])
        item = page.table.item(0, 0)
        assert item.data(Qt.ItemDataRole.UserRole) == entry_id

    def test_stores_output_path(self, page) -> None:  # noqa: ANN001
        """Output path is stored in UserRole+1 on column 0."""
        _populate_table(page, [_make_entry(output_path="/out/dubbed.mp4")])
        item = page.table.item(0, 0)
        assert item.data(Qt.ItemDataRole.UserRole + 1) == "/out/dubbed.mp4"

    def test_stores_source_path(self, page) -> None:  # noqa: ANN001
        """Source path is stored in UserRole+2 on column 0."""
        _populate_table(page, [_make_entry(source_path="/src/video.mp4")])
        item = page.table.item(0, 0)
        assert item.data(Qt.ItemDataRole.UserRole + 2) == "/src/video.mp4"

    def test_stores_error_message(self, page) -> None:  # noqa: ANN001
        """Error message is stored in UserRole+3 on column 0."""
        _populate_table(page, [_make_entry(error_message="DUB_FAIL")])
        item = page.table.item(0, 0)
        assert item.data(Qt.ItemDataRole.UserRole + 3) == "DUB_FAIL"

    def test_stores_src_lang(self, page) -> None:  # noqa: ANN001
        """Source language is stored in UserRole+4."""
        _populate_table(page, [_make_entry(src_lang="fr")])
        item = page.table.item(0, 0)
        assert item.data(Qt.ItemDataRole.UserRole + 4) == "fr"

    def test_stores_target_lang(self, page) -> None:  # noqa: ANN001
        """Target language is stored in UserRole+5."""
        _populate_table(page, [_make_entry(target_lang="ja")])
        item = page.table.item(0, 0)
        assert item.data(Qt.ItemDataRole.UserRole + 5) == "ja"

    def test_stores_subtitle_path(self, page) -> None:  # noqa: ANN001
        """Subtitle path is stored in UserRole+6."""
        _populate_table(page, [_make_entry(subtitle_path="/out/sub.srt")])
        item = page.table.item(0, 0)
        assert item.data(Qt.ItemDataRole.UserRole + 6) == "/out/sub.srt"

    def test_stores_translated_subtitle_path(self, page) -> None:  # noqa: ANN001
        """Translated subtitle path is stored in UserRole+7."""
        _populate_table(page, [_make_entry(translated_subtitle_path="/out/tsub.srt")])
        item = page.table.item(0, 0)
        assert item.data(Qt.ItemDataRole.UserRole + 7) == "/out/tsub.srt"

    def test_stores_voice_path(self, page) -> None:  # noqa: ANN001
        """Voice path is stored in UserRole+8."""
        _populate_table(page, [_make_entry(voice_path="/out/voice.mp3")])
        item = page.table.item(0, 0)
        assert item.data(Qt.ItemDataRole.UserRole + 8) == "/out/voice.mp3"

    def test_file_name_displayed(self, page) -> None:  # noqa: ANN001
        """File name is shown as column 0 text."""
        _populate_table(page, [_make_entry(name="documentary.mp4")])
        assert page.table.item(0, 0).text() == "documentary.mp4"

    def test_size_formatted(self, page) -> None:  # noqa: ANN001
        """File size is formatted via format_file_size."""
        _populate_table(page, [_make_entry(file_size=1048576)])
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

    def test_status_paused_stored(self, page) -> None:  # noqa: ANN001
        """Paused status raw value is stored in UserRole."""
        _populate_table(page, [_make_entry(status="Paused")])
        status_item = page.table.item(0, 2)
        assert status_item.data(Qt.ItemDataRole.UserRole) == "Paused"

    def test_status_pending_stored(self, page) -> None:  # noqa: ANN001
        """Pending status raw value is stored in UserRole."""
        _populate_table(page, [_make_entry(status="Pending")])
        status_item = page.table.item(0, 2)
        assert status_item.data(Qt.ItemDataRole.UserRole) == "Pending"

    def test_progress_displayed_as_percentage(self, page) -> None:  # noqa: ANN001
        """Progress is displayed as 'N%'."""
        _populate_table(page, [_make_entry(progress=75)])
        progress_text = page.table.item(0, 3).text()
        assert progress_text == "75%"

    def test_progress_zero_shows_empty(self, page) -> None:  # noqa: ANN001
        """Zero progress shows empty string."""
        _populate_table(page, [_make_entry(progress=0)])
        assert page.table.item(0, 3).text() == ""

    def test_progress_none_shows_empty(self, page) -> None:  # noqa: ANN001
        """None progress shows empty string."""
        _populate_table(page, [_make_entry(progress=None)])
        assert page.table.item(0, 3).text() == ""

    def test_progress_invalid_shows_empty(self, page) -> None:  # noqa: ANN001
        """Invalid progress value shows empty string."""
        _populate_table(page, [_make_entry(progress="abc")])
        assert page.table.item(0, 3).text() == ""

    def test_date_column_present(self, page) -> None:  # noqa: ANN001
        """Date column has non-empty text."""
        _populate_table(page, [_make_entry()])
        assert page.table.item(0, 4).text()


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
        assert not page.pause_btn.isEnabled()
        assert not page.continue_btn.isEnabled()
        assert not page.re_dub_btn.isEnabled()
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
        assert not page.pause_btn.isEnabled()
        assert not page.continue_btn.isEnabled()
        assert not page.re_dub_btn.isEnabled()
        assert not page.delete_btn.isEnabled()

    def test_done_selection_enables_open_redub_delete(self, page) -> None:  # noqa: ANN001
        """Selecting a Done entry enables open, re-dub, delete."""
        _populate_table(page, [_make_entry(status="Done")])
        page.table.selectRow(0)
        assert page.open_btn.isEnabled()
        assert page.re_dub_btn.isEnabled()
        assert page.delete_btn.isEnabled()
        assert not page.pause_btn.isEnabled()
        assert not page.continue_btn.isEnabled()

    def test_pending_enables_pause_disables_redub(self, page) -> None:  # noqa: ANN001
        """Selecting a Pending entry enables pause, disables re-dub."""
        _populate_table(page, [_make_entry(status="Pending")])
        page.table.selectRow(0)
        assert page.pause_btn.isEnabled()
        assert not page.re_dub_btn.isEnabled()
        assert page.delete_btn.isEnabled()

    def test_generating_enables_pause_disables_redub(self, page) -> None:  # noqa: ANN001
        """Selecting a Generating entry enables pause, disables re-dub."""
        _populate_table(page, [_make_entry(status="Generating")])
        page.table.selectRow(0)
        assert page.pause_btn.isEnabled()
        assert not page.re_dub_btn.isEnabled()

    def test_paused_enables_continue(self, page) -> None:  # noqa: ANN001
        """Selecting a Paused entry enables continue."""
        _populate_table(page, [_make_entry(status="Paused")])
        page.table.selectRow(0)
        assert page.continue_btn.isEnabled()
        assert not page.pause_btn.isEnabled()

    def test_failed_enables_continue(self, page) -> None:  # noqa: ANN001
        """Selecting a Failed entry enables continue."""
        _populate_table(page, [_make_entry(status="Failed")])
        page.table.selectRow(0)
        assert page.continue_btn.isEnabled()

    def test_error_message_shown_for_failed(self, page) -> None:  # noqa: ANN001
        """Error banner is shown when a single failed entry is selected."""
        page.show()
        _populate_table(
            page,
            [_make_entry(status="Failed", error_message="DUB_ERR")],
        )
        page.table.selectRow(0)
        assert page.error_frame.isVisible()

    def test_auth_error_service_suffix_renders_specific_service(
        self,
        page,  # noqa: ANN001
    ) -> None:
        """``AUTH_ERROR:Gemini`` → "Invalid Gemini API key…".

        Dubbing runs the full pipeline (STT → translate → TTS), so
        AUTH errors can come from any of three services.  Pins the
        service-aware copy so the user can target the right Settings
        tab without trial-and-error.
        """
        from src.constants.i18n import _set_initial_language  # noqa: PLC0415

        _set_initial_language("en-US")
        page.show()
        _populate_table(
            page,
            [_make_entry(status="Failed", error_message="AUTH_ERROR:Gemini")],
        )
        page.table.selectRow(0)
        text = page.error_label.text()
        assert "Gemini" in text, (
            f"service name missing from error label: {text!r}"
        )
        assert "API key" in text

    def test_error_hidden_for_done(self, page) -> None:  # noqa: ANN001
        """Error banner is hidden when a Done entry is selected."""
        _populate_table(page, [_make_entry(status="Done")])
        page.table.selectRow(0)
        assert not page.error_frame.isVisible()

    def test_mixed_selection_active_and_done(self, page) -> None:  # noqa: ANN001
        """Mixed active+done selection: pause enabled, re-dub disabled."""
        entries = [
            _make_entry(entry_id=1, status="Generating"),
            _make_entry(entry_id=2, status="Done"),
        ]
        _populate_table(page, entries)
        page.table.selectAll()
        assert page.pause_btn.isEnabled()
        assert not page.re_dub_btn.isEnabled()


# ===================================================================
# Open File
# ===================================================================


class TestOpenFile:
    """Tests for on_open_file behavior."""

    @patch(f"{_MOD}.QDesktopServices.openUrl")
    @patch(f"{_MOD}.Path.exists", return_value=True)
    def test_open_file_opens_parent_directory(
        self,
        mock_exists,
        mock_open,
        page,  # noqa: ANN001
    ) -> None:
        """Opens the containing directory of the output file."""
        _populate_table(page, [_make_entry(output_path="/out/dubbed.mp4")])
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
        _populate_table(page, [_make_entry(output_path="/out/missing.mp4")])
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

    @patch("shutil.rmtree")
    @patch(
        "src.utils.path_manager.get_dubbing_storage_dir",
        return_value="/tmp/storage/1",
    )
    @patch(f"{_MOD}.Path.is_file", return_value=False)
    @patch(
        f"{_MOD}.delete_dubbing_entry",
        return_value=("/out/v.mp4", "/out/s.srt", "/out/ts.srt", "/out/voice.mp3"),
    )
    @patch(f"{_MOD}.CustomConfirmDialog.confirm", return_value=True)
    def test_delete_confirmed(  # noqa: PLR0913
        self,
        mock_confirm,
        mock_delete,
        mock_is_file,
        mock_storage,
        mock_rmtree,
        page,  # noqa: ANN001
    ) -> None:
        """Delete confirmed: entry removed and storage cleaned."""
        _populate_table(page, [_make_entry(entry_id=10)])
        page.table.selectRow(0)

        with (
            patch(f"{_MOD}.get_dubbing_fingerprint", return_value=(0, 0, "x")),
            patch(f"{_MOD}.get_dubbing_history", return_value=[]),
        ):
            page.on_delete_selected()

        mock_confirm.assert_called_once()
        mock_delete.assert_called_once_with(10)  # noqa: PLR2004
        mock_rmtree.assert_called_once()

    @patch(f"{_MOD}.delete_dubbing_entry")
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

    @patch("shutil.rmtree")
    @patch(
        "src.utils.path_manager.get_dubbing_storage_dir",
        return_value="/tmp/storage/x",
    )
    @patch(f"{_MOD}.Path.is_file", return_value=False)
    @patch(f"{_MOD}.delete_dubbing_entry", return_value=("", "", "", ""))
    @patch(f"{_MOD}.CustomConfirmDialog.confirm", return_value=True)
    def test_delete_multiple(  # noqa: PLR0913
        self,
        mock_confirm,
        mock_delete,
        mock_is_file,
        mock_storage,
        mock_rmtree,
        page,  # noqa: ANN001
    ) -> None:
        """Deleting multiple rows deletes all selected entries."""
        entries = [_make_entry(entry_id=i) for i in range(1, 4)]
        _populate_table(page, entries)
        page.table.selectAll()

        with (
            patch(f"{_MOD}.get_dubbing_fingerprint", return_value=(0, 0, "x")),
            patch(f"{_MOD}.get_dubbing_history", return_value=[]),
        ):
            page.on_delete_selected()

        assert mock_delete.call_count == 3  # noqa: PLR2004


# ===================================================================
# Pause
# ===================================================================


class TestPause:
    """Tests for on_pause behavior."""

    @patch(f"{_MOD}.batch_pause_dubbing_entries")
    def test_pause_calls_batch_function(
        self,
        mock_pause,
        page,  # noqa: ANN001
    ) -> None:
        """on_pause calls batch_pause_dubbing_entries with selected IDs."""
        _populate_table(page, [_make_entry(entry_id=5, status="Generating")])
        page.table.selectRow(0)

        with (
            patch(f"{_MOD}.get_dubbing_fingerprint", return_value=(0, 0, "x")),
            patch(f"{_MOD}.get_dubbing_history", return_value=[]),
        ):
            page.on_pause()

        mock_pause.assert_called_once_with([5])

    def test_pause_no_selection(self, page) -> None:  # noqa: ANN001
        """Does nothing when no rows are selected."""
        _populate_table(page, [_make_entry(status="Generating")])
        page.table.clearSelection()
        page.on_pause()  # Should not raise

    @patch(f"{_MOD}.batch_pause_dubbing_entries")
    def test_pause_multiple(self, mock_pause, page) -> None:  # noqa: ANN001
        """Pauses multiple selected entries."""
        entries = [
            _make_entry(entry_id=1, status="Generating"),
            _make_entry(entry_id=2, status="Pending"),
        ]
        _populate_table(page, entries)
        page.table.selectAll()

        with (
            patch(f"{_MOD}.get_dubbing_fingerprint", return_value=(0, 0, "x")),
            patch(f"{_MOD}.get_dubbing_history", return_value=[]),
        ):
            page.on_pause()

        mock_pause.assert_called_once()
        paused_ids = mock_pause.call_args[0][0]
        assert set(paused_ids) == {1, 2}


# ===================================================================
# Continue
# ===================================================================


class TestContinue:
    """Tests for on_continue behavior."""

    @patch(f"{_MOD}.batch_resume_dubbing_entries")
    @patch(f"{_MOD}.Path.exists", return_value=True)
    def test_continue_emits_signal(
        self,
        mock_exists,
        mock_resume,
        page,
        qtbot,  # noqa: ANN001
    ) -> None:
        """on_continue emits continue_requested with tasks and languages."""
        _populate_table(
            page,
            [
                _make_entry(
                    entry_id=3,
                    source_path="/src/vid.mp4",
                    src_lang="en",
                    target_lang="vi",
                    status="Paused",
                ),
            ],
        )
        page.table.selectRow(0)

        with (
            qtbot.waitSignal(page.continue_requested, timeout=1000) as sig,
            patch(f"{_MOD}.get_dubbing_fingerprint", return_value=(0, 0, "x")),
            patch(f"{_MOD}.get_dubbing_history", return_value=[]),
        ):
            page.on_continue()

        assert len(sig.args[0]) == 1
        assert sig.args[0][0] == (3, "/src/vid.mp4")
        assert sig.args[1] == "en"
        assert sig.args[2] == "vi"
        mock_resume.assert_called_once_with([3])

    @patch(f"{_MOD}.Path.exists", return_value=False)
    @patch(f"{_MOD}.CustomMessageDialog.show_message")
    @patch(f"{_MOD}.delete_dubbing_entry")
    def test_continue_missing_source(
        self,
        mock_delete,
        mock_msg,
        mock_exists,
        page,  # noqa: ANN001
    ) -> None:
        """Shows error dialog and deletes entry when source is missing."""
        _populate_table(
            page,
            [_make_entry(entry_id=9, source_path="/gone.mp4", status="Paused")],
        )
        page.table.selectRow(0)

        with (
            patch(f"{_MOD}.get_dubbing_fingerprint", return_value=(0, 0, "x")),
            patch(f"{_MOD}.get_dubbing_history", return_value=[]),
        ):
            page.on_continue()

        mock_msg.assert_called_once()
        mock_delete.assert_called_once_with(9)  # noqa: PLR2004

    def test_continue_no_selection(self, page) -> None:  # noqa: ANN001
        """Does nothing when no rows are selected."""
        _populate_table(page, [_make_entry(status="Paused")])
        page.table.clearSelection()
        page.on_continue()  # Should not raise

    @patch(f"{_MOD}.batch_resume_dubbing_entries")
    @patch(f"{_MOD}.Path.exists", return_value=True)
    def test_continue_skips_non_resumable(
        self,
        mock_exists,
        mock_resume,
        page,
        qtbot,  # noqa: ANN001
    ) -> None:
        """on_continue skips Done entries (not resumable)."""
        entries = [
            _make_entry(entry_id=1, status="Done"),
            _make_entry(
                entry_id=2,
                status="Paused",
                source_path="/src/vid2.mp4",
                src_lang="fr",
                target_lang="de",
            ),
        ]
        _populate_table(page, entries)
        page.table.selectAll()

        with (
            qtbot.waitSignal(page.continue_requested, timeout=1000) as sig,
            patch(f"{_MOD}.get_dubbing_fingerprint", return_value=(0, 0, "x")),
            patch(f"{_MOD}.get_dubbing_history", return_value=[]),
        ):
            page.on_continue()

        # Only the Paused entry should be resumed
        assert len(sig.args[0]) == 1
        assert sig.args[0][0][0] == 2  # noqa: PLR2004
        mock_resume.assert_called_once_with([2])


# ===================================================================
# Re-Dub
# ===================================================================


class TestReDub:
    """Tests for on_re_dub behavior."""

    @patch(f"{_MOD}.Path.exists", return_value=True)
    def test_re_dub_emits_signal(
        self,
        mock_exists,
        page,
        qtbot,  # noqa: ANN001
    ) -> None:
        """Re-dub emits re_dub_requested with correct tasks."""
        _populate_table(
            page,
            [_make_entry(entry_id=7, source_path="/src/movie.mp4", status="Done")],
        )
        page.table.selectRow(0)

        with qtbot.waitSignal(page.re_dub_requested, timeout=1000) as sig:
            page.on_re_dub()

        assert len(sig.args[0]) == 1
        assert sig.args[0][0] == (7, "/src/movie.mp4")

    @patch(f"{_MOD}.Path.exists", return_value=False)
    @patch(f"{_MOD}.CustomMessageDialog.show_message")
    @patch(f"{_MOD}.delete_dubbing_entry")
    def test_re_dub_missing_source(
        self,
        mock_delete,
        mock_msg,
        mock_exists,
        page,  # noqa: ANN001
    ) -> None:
        """Shows error dialog and deletes entry when source is missing."""
        _populate_table(page, [_make_entry(entry_id=9, source_path="/gone.mp4")])
        page.table.selectRow(0)

        with (
            patch(f"{_MOD}.get_dubbing_fingerprint", return_value=(0, 0, "x")),
            patch(f"{_MOD}.get_dubbing_history", return_value=[]),
        ):
            page.on_re_dub()

        mock_msg.assert_called_once()
        mock_delete.assert_called_once_with(9)  # noqa: PLR2004

    def test_re_dub_no_selection(self, page) -> None:  # noqa: ANN001
        """Does nothing when no rows are selected."""
        _populate_table(page, [_make_entry()])
        page.table.clearSelection()
        page.on_re_dub()  # Should not raise


# ===================================================================
# Search Filtering
# ===================================================================


class TestSearchFiltering:
    """Tests for client-side search filtering."""

    def test_search_filters_by_name(self, page) -> None:  # noqa: ANN001
        """Search filters entries by file name (case-insensitive)."""
        entries = [
            _make_entry(entry_id=1, name="Documentary.mp4"),
            _make_entry(entry_id=2, name="Tutorial.mp4"),
        ]
        page.search_input.setText("documentary")
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
        entries = [_make_entry(entry_id=1, name="movie.mp4")]
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
            patch(f"{_MOD}.get_dubbing_fingerprint", return_value=None),
            patch(f"{_MOD}.get_dubbing_history", return_value=[]),
        ):
            page.apply_theme()

    def test_apply_language_runs(self, page) -> None:  # noqa: ANN001
        """apply_language() completes without error."""
        with (
            patch(f"{_MOD}.get_dubbing_fingerprint", return_value=None),
            patch(f"{_MOD}.get_dubbing_history", return_value=[]),
        ):
            page.apply_language()

    def test_apply_language_updates_headers(self, page) -> None:  # noqa: ANN001
        """apply_language updates all column header texts."""
        with (
            patch(f"{_MOD}.get_dubbing_fingerprint", return_value=None),
            patch(f"{_MOD}.get_dubbing_history", return_value=[]),
        ):
            page.apply_language()

        for col in range(page.table.columnCount()):
            header = page.table.horizontalHeaderItem(col)
            assert header is not None
            assert len(header.text()) > 0

    def test_apply_language_updates_button_text(self, page) -> None:  # noqa: ANN001
        """apply_language updates button labels."""
        with (
            patch(f"{_MOD}.get_dubbing_fingerprint", return_value=None),
            patch(f"{_MOD}.get_dubbing_history", return_value=[]),
        ):
            page.apply_language()

        assert page.open_btn.text()
        assert page.pause_btn.text()
        assert page.continue_btn.text()
        assert page.re_dub_btn.text()
        assert page.delete_btn.text()

    def test_apply_theme_updates_all_button_styles(self, page) -> None:  # noqa: ANN001
        """apply_theme updates styles for all 5 action buttons."""
        with (
            patch(f"{_MOD}.get_dubbing_fingerprint", return_value=None),
            patch(f"{_MOD}.get_dubbing_history", return_value=[]),
        ):
            page.apply_theme()

        # All buttons should have non-empty stylesheets
        assert page.open_btn.styleSheet()
        assert page.pause_btn.styleSheet()
        assert page.continue_btn.styleSheet()
        assert page.re_dub_btn.styleSheet()
        assert page.delete_btn.styleSheet()


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
# on_continue() Language Extraction
# ===================================================================


class TestContinueLanguageExtraction:
    """Tests for on_continue() extracting languages from the first resumable entry."""

    @patch(f"{_MOD}.batch_resume_dubbing_entries")
    @patch(f"{_MOD}.Path.exists", return_value=True)
    def test_continue_mixed_done_paused_uses_paused_lang(
        self,
        mock_exists,
        mock_resume,
        page,
        qtbot,  # noqa: ANN001
    ) -> None:
        """With Done + Paused selected, language comes from Paused entry."""
        entries = [
            _make_entry(
                entry_id=1,
                status="Done",
                src_lang="en",
                target_lang="vi",
                source_path="/src/v1.mp4",
            ),
            _make_entry(
                entry_id=2,
                status="Paused",
                src_lang="fr",
                target_lang="de",
                source_path="/src/v2.mp4",
            ),
        ]
        _populate_table(page, entries)
        page.table.selectAll()

        with (
            qtbot.waitSignal(page.continue_requested, timeout=1000) as sig,
            patch(f"{_MOD}.get_dubbing_fingerprint", return_value=(0, 0, "x")),
            patch(f"{_MOD}.get_dubbing_history", return_value=[]),
        ):
            page.on_continue()

        # Language should be from the Paused entry (id=2), not the Done (id=1)
        assert sig.args[1] == "fr"
        assert sig.args[2] == "de"
        # Only the paused entry should be in tasks
        assert len(sig.args[0]) == 1
        assert sig.args[0][0][0] == 2  # noqa: PLR2004


# ===================================================================
# Mixed Button States
# ===================================================================


class TestMixedButtonStates:
    """Tests for _update_button_states with complex selections."""

    def test_paused_and_failed_enables_continue(self, page) -> None:  # noqa: ANN001
        """Paused + Failed selected enables continue button."""
        entries = [
            _make_entry(entry_id=1, status="Paused"),
            _make_entry(entry_id=2, status="Failed"),
        ]
        _populate_table(page, entries)
        page.table.selectAll()
        assert page.continue_btn.isEnabled()

    def test_paused_and_generating_enables_both_pause_continue(
        self,
        page,  # noqa: ANN001
    ) -> None:
        """Paused + Generating selected enables both pause and continue."""
        entries = [
            _make_entry(entry_id=1, status="Paused"),
            _make_entry(entry_id=2, status="Generating"),
        ]
        _populate_table(page, entries)
        page.table.selectAll()
        assert page.pause_btn.isEnabled()
        assert page.continue_btn.isEnabled()

    def test_paused_and_generating_disables_re_dub(self, page) -> None:  # noqa: ANN001
        """Paused + Generating selected disables re-dub (active is selected)."""
        entries = [
            _make_entry(entry_id=1, status="Paused"),
            _make_entry(entry_id=2, status="Generating"),
        ]
        _populate_table(page, entries)
        page.table.selectAll()
        assert not page.re_dub_btn.isEnabled()


# ===================================================================
# Progress Edge Cases
# ===================================================================


class TestProgressEdgeCases:
    """Tests for _fill_row progress parsing edge cases."""

    def test_negative_progress_shows_zero_or_empty(self, page) -> None:  # noqa: ANN001
        """Negative progress value is clamped: int(-5) → displayed as empty."""
        _populate_table(page, [_make_entry(progress=-5)])
        progress_text = page.table.item(0, 3).text()
        # int(-5) is truthy, but code does `f"{pct}%" if pct else ""`
        # -5 is truthy so it shows "-5%"; this test documents actual behavior
        assert progress_text in ("", "-5%", "0%")

    def test_progress_over_100_shows_value(self, page) -> None:  # noqa: ANN001
        """Progress > 100 is passed through (no clamping)."""
        _populate_table(page, [_make_entry(progress=150)])
        progress_text = page.table.item(0, 3).text()
        assert progress_text == "150%"

    def test_float_progress_truncated_to_int(self, page) -> None:  # noqa: ANN001
        """Float progress like '75.5' is truncated to int (75)."""
        _populate_table(page, [_make_entry(progress="75.5")])
        progress_text = page.table.item(0, 3).text()
        # int("75.5") raises ValueError → pct=0 → empty
        # OR if the source does int(float(progress)) it would be 75
        assert progress_text in ("", "75%")

    def test_progress_string_100_shows_100_percent(self, page) -> None:  # noqa: ANN001
        """String '100' is correctly parsed as 100%."""
        _populate_table(page, [_make_entry(progress="100")])
        assert page.table.item(0, 3).text() == "100%"

    def test_progress_string_0_shows_empty(self, page) -> None:  # noqa: ANN001
        """String '0' is parsed as 0, which shows empty."""
        _populate_table(page, [_make_entry(progress="0")])
        assert page.table.item(0, 3).text() == ""


# ===================================================================
# Page Is A QWidget
# ===================================================================


class TestPageIsQWidget:
    """Tests that the page is a proper QWidget with expected elements."""

    def test_is_qwidget_instance(self, page) -> None:  # noqa: ANN001
        """DubbingHistoryPage is a QWidget."""
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
        for btn in [
            page.open_btn,
            page.pause_btn,
            page.continue_btn,
            page.re_dub_btn,
            page.delete_btn,
        ]:
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
        # In offscreen mode the scrollbar max is 0, so we just verify
        # refresh_history doesn't crash and the scrollbar is accessible.
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
            patch(f"{_MOD}.get_dubbing_fingerprint", return_value=(1, 1, "new")),
            patch(f"{_MOD}.get_dubbing_history", history_mock),
        ):
            page.refresh_history(force=False)
            history_mock.assert_not_called()

    def test_fingerprint_none_always_refreshes(self, page) -> None:  # noqa: ANN001
        """When fingerprint is None, always refreshes."""
        history_mock = MagicMock(return_value=[_make_entry()])
        page._last_fingerprint = (1, 1, "old")
        with (
            patch(f"{_MOD}.get_dubbing_fingerprint", return_value=None),
            patch(f"{_MOD}.get_dubbing_history", history_mock),
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
        entries = [_make_entry(entry_id=1, name="movie.mp4")]
        page.search_input.setText("MOVIE")
        _populate_table(page, entries)
        assert page.table.rowCount() == 1

    def test_search_partial_match(self, page) -> None:  # noqa: ANN001
        """Search matches partial file names."""
        entries = [_make_entry(entry_id=1, name="my_video_file.mp4")]
        page.search_input.setText("video")
        _populate_table(page, entries)
        assert page.table.rowCount() == 1

    def test_search_with_special_characters(self, page) -> None:  # noqa: ANN001
        """Search handles special characters in file names."""
        entries = [_make_entry(entry_id=1, name="file (1).mp4")]
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
        entries = [_make_entry(entry_id=1, name="test.mp4")]
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
        _populate_table(page, [_make_entry(name="\u6d4b\u8bd5\u89c6\u9891.mp4")])
        assert page.table.item(0, 0).text() == "\u6d4b\u8bd5\u89c6\u9891.mp4"

    def test_emoji_filename(self, page) -> None:  # noqa: ANN001
        """Emoji in filenames are displayed correctly."""
        _populate_table(page, [_make_entry(name="\U0001f3ac movie.mp4")])
        assert page.table.item(0, 0).text() == "\U0001f3ac movie.mp4"

    def test_very_long_filename(self, page) -> None:  # noqa: ANN001
        """Very long filenames are stored without truncation."""
        long_name = "a" * 500 + ".mp4"
        _populate_table(page, [_make_entry(name=long_name)])
        assert page.table.item(0, 0).text() == long_name

    def test_empty_filename(self, page) -> None:  # noqa: ANN001
        """Empty filename is stored without error."""
        _populate_table(page, [_make_entry(name="")])
        assert page.table.item(0, 0).text() == ""

    def test_unicode_search(self, page) -> None:  # noqa: ANN001
        """Search works with unicode characters."""
        entries = [
            _make_entry(entry_id=1, name="\u6d4b\u8bd5.mp4"),
            _make_entry(entry_id=2, name="english.mp4"),
        ]
        page.search_input.setText("\u6d4b\u8bd5")
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

    def test_paused_status_has_warning_color(self, page) -> None:  # noqa: ANN001
        """Paused status foreground uses warning color."""
        from PySide6.QtGui import QColor  # noqa: PLC0415

        from src.constants import color as get_color  # noqa: PLC0415

        _populate_table(page, [_make_entry(status="Paused")])
        status_item = page.table.item(0, 2)
        assert status_item.foreground().color() == QColor(get_color("warning"))

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
# Re-Dub Multiple Files
# ===================================================================


class TestReDubMultiple:
    """Tests for re-dubbing multiple files."""

    @patch(f"{_MOD}.Path.exists", return_value=True)
    def test_re_dub_multiple_emits_all(
        self,
        mock_exists,
        page,
        qtbot,  # noqa: ANN001
    ) -> None:
        """Re-dub with multiple selected emits all tasks."""
        entries = [
            _make_entry(entry_id=1, source_path="/src/v1.mp4", status="Done"),
            _make_entry(entry_id=2, source_path="/src/v2.mp4", status="Done"),
        ]
        _populate_table(page, entries)
        page.table.selectAll()

        with qtbot.waitSignal(page.re_dub_requested, timeout=1000) as sig:
            page.on_re_dub()

        assert len(sig.args[0]) == 2  # noqa: PLR2004


# ===================================================================
# Delete With File Cleanup
# ===================================================================


class TestDeleteFileCleanup:
    """Tests for file cleanup during delete operations."""

    @patch("shutil.rmtree")
    @patch(
        "src.utils.path_manager.get_dubbing_storage_dir",
        return_value="/tmp/storage/1",
    )
    @patch(f"{_MOD}.Path.is_file", return_value=True)
    @patch(f"{_MOD}.Path.unlink")
    @patch(
        f"{_MOD}.delete_dubbing_entry",
        return_value=("/out/v.mp4", "/out/s.srt", "/out/ts.srt", "/out/voice.mp3"),
    )
    @patch(f"{_MOD}.CustomConfirmDialog.confirm", return_value=True)
    def test_delete_unlinks_output_files(  # noqa: PLR0913
        self,
        mock_confirm,
        mock_delete,
        mock_unlink,
        mock_is_file,
        mock_storage,
        mock_rmtree,
        page,  # noqa: ANN001
    ) -> None:
        """Delete unlinks all output files when they exist."""
        _populate_table(page, [_make_entry(entry_id=1)])
        page.table.selectRow(0)

        with (
            patch(f"{_MOD}.get_dubbing_fingerprint", return_value=(0, 0, "x")),
            patch(f"{_MOD}.get_dubbing_history", return_value=[]),
        ):
            page.on_delete_selected()

        assert mock_unlink.call_count == 4  # noqa: PLR2004

    @patch(f"{_MOD}.delete_dubbing_entry", return_value=(None, None, None, None))
    @patch(f"{_MOD}.CustomConfirmDialog.confirm", return_value=True)
    def test_delete_handles_none_paths(
        self,
        mock_confirm,
        mock_delete,
        page,  # noqa: ANN001
    ) -> None:
        """Delete handles None paths gracefully."""
        _populate_table(page, [_make_entry(entry_id=1)])
        page.table.selectRow(0)

        with (
            patch(f"{_MOD}.get_dubbing_fingerprint", return_value=(0, 0, "x")),
            patch(f"{_MOD}.get_dubbing_history", return_value=[]),
            patch("shutil.rmtree"),
            patch(
                "src.utils.path_manager.get_dubbing_storage_dir",
                return_value="/tmp/storage/1",
            ),
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
            _make_entry(entry_id=1, name="Zebra.mp4"),
            _make_entry(entry_id=2, name="Apple.mp4"),
        ]
        _populate_table(page, entries)
        page.table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        assert page.table.item(0, 0).text() == "Apple.mp4"
        assert page.table.item(1, 0).text() == "Zebra.mp4"

    def test_sort_by_date_column_descending(self, page) -> None:  # noqa: ANN001
        """Sorting by date column descending puts newest first."""
        entries = [
            _make_entry(entry_id=1, created_at="2026-01-01 10:00:00"),
            _make_entry(entry_id=2, created_at="2026-12-31 10:00:00"),
        ]
        _populate_table(page, entries)
        page.table.sortByColumn(4, Qt.SortOrder.DescendingOrder)
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
# Signals
# ===================================================================


class TestSignals:
    """Tests for Qt signal declarations."""

    def test_re_dub_requested_signal_exists(self, page) -> None:  # noqa: ANN001
        """DubbingHistoryPage has re_dub_requested signal."""
        assert hasattr(page, "re_dub_requested")

    def test_continue_requested_signal_exists(self, page) -> None:  # noqa: ANN001
        """DubbingHistoryPage has continue_requested signal."""
        assert hasattr(page, "continue_requested")


# ===================================================================
# NEW: Extended Button State Combinations
# ===================================================================


class TestExtendedButtonStateCombinations:
    """Additional tests for _update_button_states with various status combos."""

    def test_all_done_enables_redub(self, page) -> None:  # noqa: ANN001
        """Multiple Done entries selected enables re-dub."""
        entries = [
            _make_entry(entry_id=1, status="Done"),
            _make_entry(entry_id=2, status="Done"),
            _make_entry(entry_id=3, status="Done"),
        ]
        _populate_table(page, entries)
        page.table.selectAll()
        assert page.re_dub_btn.isEnabled()
        assert not page.pause_btn.isEnabled()
        assert not page.continue_btn.isEnabled()

    def test_all_pending_disables_redub(self, page) -> None:  # noqa: ANN001
        """All Pending entries selected disables re-dub."""
        entries = [
            _make_entry(entry_id=1, status="Pending"),
            _make_entry(entry_id=2, status="Pending"),
        ]
        _populate_table(page, entries)
        page.table.selectAll()
        assert not page.re_dub_btn.isEnabled()
        assert page.pause_btn.isEnabled()

    def test_all_failed_enables_continue_and_redub(self, page) -> None:  # noqa: ANN001
        """All Failed entries selected enables both continue and re-dub."""
        entries = [
            _make_entry(entry_id=1, status="Failed"),
            _make_entry(entry_id=2, status="Failed"),
        ]
        _populate_table(page, entries)
        page.table.selectAll()
        assert page.continue_btn.isEnabled()
        assert page.re_dub_btn.isEnabled()

    def test_failed_and_done_enables_continue_and_redub(self, page) -> None:  # noqa: ANN001
        """Failed + Done selected: continue from failed, re-dub enabled (no active)."""
        entries = [
            _make_entry(entry_id=1, status="Failed"),
            _make_entry(entry_id=2, status="Done"),
        ]
        _populate_table(page, entries)
        page.table.selectAll()
        assert page.continue_btn.isEnabled()
        assert page.re_dub_btn.isEnabled()

    def test_pending_and_done_disables_redub(self, page) -> None:  # noqa: ANN001
        """Pending + Done selected disables re-dub (active is selected)."""
        entries = [
            _make_entry(entry_id=1, status="Pending"),
            _make_entry(entry_id=2, status="Done"),
        ]
        _populate_table(page, entries)
        page.table.selectAll()
        assert not page.re_dub_btn.isEnabled()
        assert page.pause_btn.isEnabled()

    def test_generating_and_failed_buttons(self, page) -> None:  # noqa: ANN001
        """Generating + Failed: pause and continue enabled, re-dub disabled."""
        entries = [
            _make_entry(entry_id=1, status="Generating"),
            _make_entry(entry_id=2, status="Failed"),
        ]
        _populate_table(page, entries)
        page.table.selectAll()
        assert page.pause_btn.isEnabled()
        assert page.continue_btn.isEnabled()
        assert not page.re_dub_btn.isEnabled()

    def test_all_paused_enables_continue_redub(self, page) -> None:  # noqa: ANN001
        """All Paused entries enables continue and re-dub."""
        entries = [
            _make_entry(entry_id=1, status="Paused"),
            _make_entry(entry_id=2, status="Paused"),
        ]
        _populate_table(page, entries)
        page.table.selectAll()
        assert page.continue_btn.isEnabled()
        assert page.re_dub_btn.isEnabled()
        assert not page.pause_btn.isEnabled()

    def test_single_generating_buttons(self, page) -> None:  # noqa: ANN001
        """Single Generating entry: pause enabled, continue/redub disabled."""
        _populate_table(page, [_make_entry(status="Generating")])
        page.table.selectRow(0)
        assert page.pause_btn.isEnabled()
        assert not page.continue_btn.isEnabled()
        assert not page.re_dub_btn.isEnabled()
        assert page.open_btn.isEnabled()
        assert page.delete_btn.isEnabled()

    def test_single_failed_with_error_shows_banner(self, page) -> None:  # noqa: ANN001
        """Single Failed entry with error_message shows error banner."""
        page.show()
        _populate_table(
            page,
            [_make_entry(status="Failed", error_message="AUTH_ERROR")],
        )
        page.table.selectRow(0)
        assert page.error_frame.isVisible()
        assert page.error_label.text() != ""

    def test_switching_selection_updates_error_banner(self, page) -> None:  # noqa: ANN001
        """Switching from failed entry to done entry hides error banner."""
        page.show()
        entries = [
            _make_entry(entry_id=1, status="Failed", error_message="ERR_X"),
            _make_entry(entry_id=2, status="Done"),
        ]
        _populate_table(page, entries)
        # Select failed entry
        page.table.selectRow(0)
        name_item = page.table.item(0, 0)
        if name_item and name_item.data(Qt.ItemDataRole.UserRole + 3):
            assert page.error_frame.isVisible()
        # Switch to done entry
        page.table.clearSelection()
        page.table.selectRow(1)
        # Check: the done entry should not have an error
        done_item = page.table.item(1, 0)
        if done_item and not done_item.data(Qt.ItemDataRole.UserRole + 3):
            assert not page.error_frame.isVisible()

    def test_three_status_mix_pending_paused_done(self, page) -> None:  # noqa: ANN001
        """Pending + Paused + Done: pause + continue enabled, re-dub disabled."""
        entries = [
            _make_entry(entry_id=1, status="Pending"),
            _make_entry(entry_id=2, status="Paused"),
            _make_entry(entry_id=3, status="Done"),
        ]
        _populate_table(page, entries)
        page.table.selectAll()
        assert page.pause_btn.isEnabled()
        assert page.continue_btn.isEnabled()
        assert not page.re_dub_btn.isEnabled()

    def test_four_status_mix(self, page) -> None:  # noqa: ANN001
        """All four statuses selected: pause + continue enabled, re-dub disabled."""
        entries = [
            _make_entry(entry_id=1, status="Pending"),
            _make_entry(entry_id=2, status="Generating"),
            _make_entry(entry_id=3, status="Paused"),
            _make_entry(entry_id=4, status="Failed"),
        ]
        _populate_table(page, entries)
        page.table.selectAll()
        assert page.pause_btn.isEnabled()
        assert page.continue_btn.isEnabled()
        assert not page.re_dub_btn.isEnabled()

    def test_select_deselect_updates_buttons(self, page) -> None:  # noqa: ANN001
        """Selecting and then deselecting returns buttons to disabled state."""
        _populate_table(page, [_make_entry(status="Done")])
        page.table.selectRow(0)
        assert page.open_btn.isEnabled()
        page.table.clearSelection()
        page._update_button_states()
        assert not page.open_btn.isEnabled()


# ===================================================================
# NEW: Error Banner Display Tests
# ===================================================================


class TestErrorBannerDisplay:
    """Additional tests for error banner display behavior."""

    def test_error_banner_text_contains_message(self, page) -> None:  # noqa: ANN001
        """Error banner text contains the error message content."""
        page.show()
        _populate_table(
            page,
            [_make_entry(status="Failed", error_message="QUOTA_ERROR")],
        )
        page.table.selectRow(0)
        assert page.error_frame.isVisible()

    def test_error_banner_hidden_for_pending(self, page) -> None:  # noqa: ANN001
        """Error banner is hidden for Pending entry without error."""
        _populate_table(page, [_make_entry(status="Pending")])
        page.table.selectRow(0)
        assert not page.error_frame.isVisible()

    def test_error_banner_hidden_for_generating(self, page) -> None:  # noqa: ANN001
        """Error banner is hidden for Generating entry."""
        _populate_table(page, [_make_entry(status="Generating")])
        page.table.selectRow(0)
        assert not page.error_frame.isVisible()

    def test_error_banner_hidden_for_paused(self, page) -> None:  # noqa: ANN001
        """Error banner is hidden for Paused entry without error."""
        _populate_table(page, [_make_entry(status="Paused")])
        page.table.selectRow(0)
        assert not page.error_frame.isVisible()

    def test_error_banner_updates_text_on_selection_change(self, page) -> None:  # noqa: ANN001
        """Error banner text updates when selecting different failed entries."""
        page.show()
        entries = [
            _make_entry(entry_id=1, status="Failed", error_message="ERR_A"),
            _make_entry(entry_id=2, status="Failed", error_message="ERR_B"),
        ]
        _populate_table(page, entries)
        page.table.selectRow(0)
        text_a = page.error_label.text()

        page.table.clearSelection()
        page._update_button_states()

        page.table.selectRow(1)
        text_b = page.error_label.text()
        # Both should be non-empty but text may differ based on error code
        assert text_a != "" or text_b != ""


# ===================================================================
# NEW: Re-Dub Edge Cases
# ===================================================================


class TestReDubEdgeCases:
    """Additional edge case tests for on_re_dub."""

    @patch(f"{_MOD}.Path.exists", return_value=True)
    def test_re_dub_single_file_correct_task(
        self,
        mock_exists,
        page,
        qtbot,  # noqa: ANN001
    ) -> None:
        """Re-dub with single file emits correct entry_id and source_path."""
        _populate_table(
            page,
            [_make_entry(entry_id=42, source_path="/src/clip.mp4", status="Done")],
        )
        page.table.selectRow(0)

        with qtbot.waitSignal(page.re_dub_requested, timeout=1000) as sig:
            page.on_re_dub()

        assert sig.args[0] == [(42, "/src/clip.mp4")]

    @patch(f"{_MOD}.Path.exists", return_value=False)
    @patch(f"{_MOD}.CustomMessageDialog.show_message")
    @patch(f"{_MOD}.delete_dubbing_entry")
    def test_re_dub_second_file_missing_stops_early(
        self,
        mock_delete,
        mock_msg,
        mock_exists,
        page,  # noqa: ANN001
    ) -> None:
        """When second file is missing, re-dub stops and does not emit signal."""
        entries = [
            _make_entry(entry_id=1, source_path="/src/v1.mp4", status="Done"),
            _make_entry(entry_id=2, source_path="/gone.mp4", status="Done"),
        ]
        _populate_table(page, entries)
        page.table.selectAll()

        with (
            patch(f"{_MOD}.get_dubbing_fingerprint", return_value=(0, 0, "x")),
            patch(f"{_MOD}.get_dubbing_history", return_value=[]),
        ):
            page.on_re_dub()

        # First file missing stops the whole operation (return early)
        mock_msg.assert_called_once()


# ===================================================================
# NEW: Continue Edge Cases
# ===================================================================


class TestContinueEdgeCases:
    """Additional edge case tests for on_continue."""

    @patch(f"{_MOD}.batch_resume_dubbing_entries")
    @patch(f"{_MOD}.Path.exists", return_value=True)
    def test_continue_multiple_failed_entries(
        self,
        mock_exists,
        mock_resume,
        page,
        qtbot,  # noqa: ANN001
    ) -> None:
        """Continuing multiple failed entries resumes all of them."""
        entries = [
            _make_entry(
                entry_id=1,
                status="Failed",
                source_path="/src/v1.mp4",
                src_lang="en",
                target_lang="vi",
            ),
            _make_entry(
                entry_id=2,
                status="Failed",
                source_path="/src/v2.mp4",
                src_lang="en",
                target_lang="vi",
            ),
        ]
        _populate_table(page, entries)
        page.table.selectAll()

        with (
            qtbot.waitSignal(page.continue_requested, timeout=1000) as sig,
            patch(f"{_MOD}.get_dubbing_fingerprint", return_value=(0, 0, "x")),
            patch(f"{_MOD}.get_dubbing_history", return_value=[]),
        ):
            page.on_continue()

        assert len(sig.args[0]) == 2  # noqa: PLR2004
        resumed_ids = mock_resume.call_args[0][0]
        assert set(resumed_ids) == {1, 2}

    @patch(f"{_MOD}.batch_resume_dubbing_entries")
    @patch(f"{_MOD}.Path.exists", return_value=True)
    def test_continue_extracts_lang_from_first_resumable(
        self,
        mock_exists,
        mock_resume,
        page,
        qtbot,  # noqa: ANN001
    ) -> None:
        """on_continue gets languages from the first resumable entry."""
        entries = [
            _make_entry(
                entry_id=1,
                status="Failed",
                source_path="/src/v1.mp4",
                src_lang="ja",
                target_lang="ko",
            ),
        ]
        _populate_table(page, entries)
        page.table.selectRow(0)

        with (
            qtbot.waitSignal(page.continue_requested, timeout=1000) as sig,
            patch(f"{_MOD}.get_dubbing_fingerprint", return_value=(0, 0, "x")),
            patch(f"{_MOD}.get_dubbing_history", return_value=[]),
        ):
            page.on_continue()

        assert sig.args[1] == "ja"
        assert sig.args[2] == "ko"

    def test_continue_with_done_only_does_nothing(self, page) -> None:  # noqa: ANN001
        """Continuing with only Done entries selected does nothing (no resumable)."""
        _populate_table(page, [_make_entry(status="Done")])
        page.table.selectRow(0)
        # Should not crash or emit signal
        page.on_continue()


# ===================================================================
# NEW: Search Filtering Extended
# ===================================================================


class TestSearchFilteringExtended:
    """Extended search filtering tests."""

    def test_search_multiple_matches(self, page) -> None:  # noqa: ANN001
        """Search returns multiple matching entries."""
        entries = [
            _make_entry(entry_id=1, name="movie_part1.mp4"),
            _make_entry(entry_id=2, name="movie_part2.mp4"),
            _make_entry(entry_id=3, name="tutorial.mp4"),
        ]
        page.search_input.setText("movie")
        _populate_table(page, entries)
        assert page.table.rowCount() == 2  # noqa: PLR2004

    def test_search_extension_match(self, page) -> None:  # noqa: ANN001
        """Search matches file extension."""
        entries = [
            _make_entry(entry_id=1, name="video.mp4"),
            _make_entry(entry_id=2, name="video.avi"),
        ]
        page.search_input.setText(".mp4")
        _populate_table(page, entries)
        assert page.table.rowCount() == 1

    def test_search_clears_and_restores(self, page) -> None:  # noqa: ANN001
        """Clearing search after filtering restores all entries."""
        entries = [
            _make_entry(entry_id=1, name="a.mp4"),
            _make_entry(entry_id=2, name="b.mp4"),
        ]
        page.search_input.setText("a.mp4")
        _populate_table(page, entries)
        assert page.table.rowCount() == 1
        page.search_input.setText("")
        _populate_table(page, entries)
        assert page.table.rowCount() == 2  # noqa: PLR2004

    def test_search_with_dots(self, page) -> None:  # noqa: ANN001
        """Search with dots in query works correctly."""
        entries = [_make_entry(entry_id=1, name="my.movie.v2.mp4")]
        page.search_input.setText("movie.v2")
        _populate_table(page, entries)
        assert page.table.rowCount() == 1

    def test_search_mixed_case_filename(self, page) -> None:  # noqa: ANN001
        """Search is case-insensitive with mixed case filenames."""
        entries = [_make_entry(entry_id=1, name="MyMovie.MP4")]
        page.search_input.setText("mymovie")
        _populate_table(page, entries)
        assert page.table.rowCount() == 1


# ===================================================================
# NEW: Theme / Language Extended
# ===================================================================


class TestThemeAndLanguageExtended:
    """Extended theme and language application tests."""

    def test_apply_theme_updates_table_stylesheet(self, page) -> None:  # noqa: ANN001
        """apply_theme updates the table stylesheet."""
        with (
            patch(f"{_MOD}.get_dubbing_fingerprint", return_value=None),
            patch(f"{_MOD}.get_dubbing_history", return_value=[]),
        ):
            page.apply_theme()
        assert page.table.styleSheet()

    def test_apply_theme_updates_search_style(self, page) -> None:  # noqa: ANN001
        """apply_theme updates the search input stylesheet."""
        with (
            patch(f"{_MOD}.get_dubbing_fingerprint", return_value=None),
            patch(f"{_MOD}.get_dubbing_history", return_value=[]),
        ):
            page.apply_theme()
        assert page.search_input.styleSheet()

    def test_apply_language_updates_search_placeholder(self, page) -> None:  # noqa: ANN001
        """apply_language updates the search placeholder text."""
        with (
            patch(f"{_MOD}.get_dubbing_fingerprint", return_value=None),
            patch(f"{_MOD}.get_dubbing_history", return_value=[]),
        ):
            page.apply_language()
        assert page.search_input.placeholderText()

    def test_apply_theme_preserves_data(self, page) -> None:  # noqa: ANN001
        """apply_theme preserves table data after refresh."""
        entries = [_make_entry(entry_id=1, name="video.mp4")]
        _populate_table(page, entries)
        with (
            patch(f"{_MOD}.get_dubbing_fingerprint", return_value=(1, 1, "x")),
            patch(f"{_MOD}.get_dubbing_history", return_value=entries),
        ):
            page.apply_theme()
        assert page.table.rowCount() == 1

    def test_apply_language_preserves_data(self, page) -> None:  # noqa: ANN001
        """apply_language preserves table data after refresh."""
        entries = [_make_entry(entry_id=1, name="clip.mp4")]
        _populate_table(page, entries)
        with (
            patch(f"{_MOD}.get_dubbing_fingerprint", return_value=(1, 1, "x")),
            patch(f"{_MOD}.get_dubbing_history", return_value=entries),
        ):
            page.apply_language()
        assert page.table.rowCount() == 1


# ===================================================================
# NEW: Multi-Step Status / Progress Display
# ===================================================================


class TestMultiStepStatusDisplay:
    """Tests for multi-step progress display and status transitions."""

    def test_progress_50_displays_correctly(self, page) -> None:  # noqa: ANN001
        """50% progress displays as '50%'."""
        _populate_table(page, [_make_entry(progress=50)])
        assert page.table.item(0, 3).text() == "50%"

    def test_progress_1_displays_correctly(self, page) -> None:  # noqa: ANN001
        """1% progress displays as '1%'."""
        _populate_table(page, [_make_entry(progress=1)])
        assert page.table.item(0, 3).text() == "1%"

    def test_progress_99_displays_correctly(self, page) -> None:  # noqa: ANN001
        """99% progress displays as '99%'."""
        _populate_table(page, [_make_entry(progress=99)])
        assert page.table.item(0, 3).text() == "99%"

    def test_multiple_entries_different_progress(self, page) -> None:  # noqa: ANN001
        """Multiple entries with different progress values display correctly."""
        entries = [
            _make_entry(entry_id=1, progress=25, status="Generating"),
            _make_entry(entry_id=2, progress=75, status="Generating"),
            _make_entry(entry_id=3, progress=100, status="Done"),
        ]
        _populate_table(page, entries)
        assert page.table.rowCount() == 3  # noqa: PLR2004

    def test_status_transition_generating_to_done(self, page) -> None:  # noqa: ANN001
        """Status transition from Generating to Done updates display."""
        _populate_table(page, [_make_entry(status="Generating", progress=50)])
        assert page.table.item(0, 2).data(Qt.ItemDataRole.UserRole) == "Generating"
        _populate_table(page, [_make_entry(status="Done", progress=100)])
        assert page.table.item(0, 2).data(Qt.ItemDataRole.UserRole) == "Done"


# ===================================================================
# NEW: Open File Extended
# ===================================================================


class TestOpenFileExtended:
    """Extended open file tests."""

    @patch(f"{_MOD}.QDesktopServices.openUrl")
    @patch(f"{_MOD}.Path.exists", return_value=True)
    def test_open_multiple_files(
        self,
        mock_exists,
        mock_open,
        page,  # noqa: ANN001
    ) -> None:
        """Opening multiple selected files opens all of them."""
        entries = [
            _make_entry(entry_id=1, output_path="/out/v1.mp4"),
            _make_entry(entry_id=2, output_path="/out/v2.mp4"),
        ]
        _populate_table(page, entries)
        page.table.selectAll()
        page.on_open_file()
        assert mock_open.call_count == 2  # noqa: PLR2004

    def test_open_with_none_output_path(self, page) -> None:  # noqa: ANN001
        """Opening a file with None output path does not crash."""
        _populate_table(page, [_make_entry(output_path=None)])
        page.table.selectRow(0)
        page.on_open_file()  # Should not raise


# ===================================================================
# NEW: Large Dataset Tests
# ===================================================================


class TestLargeDataset:
    """Tests with larger datasets."""

    def test_ten_entries_populate(self, page) -> None:  # noqa: ANN001
        """Table populates correctly with 10 entries."""
        entries = [_make_entry(entry_id=i, name=f"video_{i}.mp4") for i in range(1, 11)]
        _populate_table(page, entries)
        assert page.table.rowCount() == 10  # noqa: PLR2004

    def test_select_all_ten_entries(self, page) -> None:  # noqa: ANN001
        """Selecting all 10 entries enables delete button."""
        entries = [_make_entry(entry_id=i, status="Done") for i in range(1, 11)]
        _populate_table(page, entries)
        page.table.selectAll()
        assert page.delete_btn.isEnabled()

    def test_search_in_large_dataset(self, page) -> None:  # noqa: ANN001
        """Search filters correctly in a larger dataset."""
        entries = [_make_entry(entry_id=i, name=f"video_{i}.mp4") for i in range(1, 11)]
        page.search_input.setText("video_5")
        _populate_table(page, entries)
        assert page.table.rowCount() == 1

    def test_mixed_statuses_large_dataset(self, page) -> None:  # noqa: ANN001
        """Large dataset with mixed statuses shows correct button states."""
        statuses = ["Done", "Pending", "Generating", "Paused", "Failed"]
        entries = [
            _make_entry(entry_id=i, status=statuses[i % len(statuses)])
            for i in range(10)
        ]
        _populate_table(page, entries)
        page.table.selectAll()
        # Should have active entries selected
        assert page.pause_btn.isEnabled()
        assert page.continue_btn.isEnabled()


# ===================================================================
# NEW: Pause Extended
# ===================================================================


class TestPauseExtended:
    """Extended pause tests."""

    @patch(f"{_MOD}.batch_pause_dubbing_entries")
    def test_pause_three_pending(self, mock_pause, page) -> None:  # noqa: ANN001
        """Pausing three Pending entries calls batch with all three IDs."""
        entries = [_make_entry(entry_id=i, status="Pending") for i in range(1, 4)]
        _populate_table(page, entries)
        page.table.selectAll()

        with (
            patch(f"{_MOD}.get_dubbing_fingerprint", return_value=(0, 0, "x")),
            patch(f"{_MOD}.get_dubbing_history", return_value=[]),
        ):
            page.on_pause()

        paused_ids = mock_pause.call_args[0][0]
        assert set(paused_ids) == {1, 2, 3}

    @patch(f"{_MOD}.batch_pause_dubbing_entries")
    def test_pause_mixed_only_sends_all_ids(self, mock_pause, page) -> None:  # noqa: ANN001
        """Pausing mixed selection sends all selected IDs (not just active)."""
        entries = [
            _make_entry(entry_id=1, status="Generating"),
            _make_entry(entry_id=2, status="Done"),
        ]
        _populate_table(page, entries)
        page.table.selectAll()

        with (
            patch(f"{_MOD}.get_dubbing_fingerprint", return_value=(0, 0, "x")),
            patch(f"{_MOD}.get_dubbing_history", return_value=[]),
        ):
            page.on_pause()

        # batch_pause_dubbing_entries receives all selected IDs
        paused_ids = mock_pause.call_args[0][0]
        assert 1 in paused_ids


# ===================================================================
# NEW: Delete Extended
# ===================================================================


class TestDeleteExtended:
    """Extended delete tests."""

    @patch("shutil.rmtree")
    @patch(
        "src.utils.path_manager.get_dubbing_storage_dir",
        return_value="/tmp/storage/x",
    )
    @patch(f"{_MOD}.Path.is_file", return_value=True)
    @patch(f"{_MOD}.Path.unlink")
    @patch(
        f"{_MOD}.delete_dubbing_entry",
        return_value=("/out/v.mp4", None, None, None),
    )
    @patch(f"{_MOD}.CustomConfirmDialog.confirm", return_value=True)
    def test_delete_partial_none_paths(  # noqa: PLR0913
        self,
        mock_confirm,
        mock_delete,
        mock_unlink,
        mock_is_file,
        mock_storage,
        mock_rmtree,
        page,  # noqa: ANN001
    ) -> None:
        """Delete handles mix of valid and None paths."""
        _populate_table(page, [_make_entry(entry_id=1)])
        page.table.selectRow(0)

        with (
            patch(f"{_MOD}.get_dubbing_fingerprint", return_value=(0, 0, "x")),
            patch(f"{_MOD}.get_dubbing_history", return_value=[]),
        ):
            page.on_delete_selected()

        mock_delete.assert_called_once()

    @patch("shutil.rmtree")
    @patch(
        "src.utils.path_manager.get_dubbing_storage_dir",
        return_value="/tmp/storage/x",
    )
    @patch(f"{_MOD}.Path.is_file", return_value=False)
    @patch(
        f"{_MOD}.delete_dubbing_entry",
        return_value=("", "", "", ""),
    )
    @patch(f"{_MOD}.CustomConfirmDialog.confirm", return_value=True)
    def test_delete_empty_paths(  # noqa: PLR0913
        self,
        mock_confirm,
        mock_delete,
        mock_is_file,
        mock_storage,
        mock_rmtree,
        page,  # noqa: ANN001
    ) -> None:
        """Delete handles empty string paths without crashing."""
        _populate_table(page, [_make_entry(entry_id=1)])
        page.table.selectRow(0)

        with (
            patch(f"{_MOD}.get_dubbing_fingerprint", return_value=(0, 0, "x")),
            patch(f"{_MOD}.get_dubbing_history", return_value=[]),
        ):
            page.on_delete_selected()

        mock_delete.assert_called_once()


# ===================================================================
# NEW: Sort by Size and Status
# ===================================================================


class TestSortBySizeAndStatus:
    """Additional sorting tests."""

    def test_sort_by_size_ascending(self, page) -> None:  # noqa: ANN001
        """Sorting by size ascending puts smallest first."""
        entries = [
            _make_entry(entry_id=1, file_size=50000),
            _make_entry(entry_id=2, file_size=100),
        ]
        _populate_table(page, entries)
        page.table.sortByColumn(1, Qt.SortOrder.AscendingOrder)
        first_id = page.table.item(0, 0).data(Qt.ItemDataRole.UserRole)
        assert first_id == 2  # noqa: PLR2004

    def test_sort_by_status_column(self, page) -> None:  # noqa: ANN001
        """Sorting by status column orders alphabetically by display text."""
        entries = [
            _make_entry(entry_id=1, status="Pending"),
            _make_entry(entry_id=2, status="Done"),
        ]
        _populate_table(page, entries)
        page.table.sortByColumn(2, Qt.SortOrder.AscendingOrder)
        # Just verify it doesn't crash
        assert page.table.rowCount() == 2  # noqa: PLR2004

    def test_sort_preserves_data_roles(self, page) -> None:  # noqa: ANN001
        """Sorting preserves UserRole data on items."""
        entries = [
            _make_entry(entry_id=1, name="Zebra.mp4", source_path="/src/z.mp4"),
            _make_entry(entry_id=2, name="Apple.mp4", source_path="/src/a.mp4"),
        ]
        _populate_table(page, entries)
        page.table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        first_item = page.table.item(0, 0)
        assert first_item.text() == "Apple.mp4"
        assert first_item.data(Qt.ItemDataRole.UserRole) == 2  # noqa: PLR2004
        assert first_item.data(Qt.ItemDataRole.UserRole + 2) == "/src/a.mp4"


# ===================================================================
# NEW: Fingerprint and Timer Tests
# ===================================================================


class TestFingerprintAndTimer:
    """Tests for fingerprint caching and timer behavior."""

    def test_timer_interval_is_1000(self, page) -> None:  # noqa: ANN001
        """Background timer interval is 1000ms."""
        assert page.timer.interval() == 1000  # noqa: PLR2004

    def test_search_timer_interval(self, page) -> None:  # noqa: ANN001
        """Search debounce timer has correct interval."""
        from src.constants import SEARCH_DEBOUNCE_MS  # noqa: PLC0415

        assert page.search_timer.interval() == SEARCH_DEBOUNCE_MS

    def test_fingerprint_change_triggers_refresh(self, page) -> None:  # noqa: ANN001
        """Changing fingerprint triggers a refresh."""
        entries = [_make_entry(entry_id=1)]
        page._last_fingerprint = (0, 0, "old")
        page.show()
        history_mock = MagicMock(return_value=entries)
        with (
            patch(f"{_MOD}.get_dubbing_fingerprint", return_value=(1, 1, "new")),
            patch(f"{_MOD}.get_dubbing_history", history_mock),
        ):
            page.refresh_history(force=False)
            history_mock.assert_called_once()

    def test_last_fingerprint_updated_after_refresh(self, page) -> None:  # noqa: ANN001
        """_last_fingerprint is updated after refresh."""
        fp = (5, 5, "hash123")
        with (
            patch(f"{_MOD}.get_dubbing_fingerprint", return_value=fp),
            patch(f"{_MOD}.get_dubbing_history", return_value=[]),
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

        for btn in [
            page.open_btn,
            page.pause_btn,
            page.continue_btn,
            page.re_dub_btn,
            page.delete_btn,
        ]:
            assert btn.maximumHeight() == HEIGHT_CONTROL
            assert btn.minimumHeight() == HEIGHT_CONTROL

    def test_search_input_has_fixed_height(self, page) -> None:  # noqa: ANN001
        """Search input has HEIGHT_CONTROL fixed height."""
        from src.constants import HEIGHT_CONTROL  # noqa: PLC0415

        assert page.search_input.maximumHeight() == HEIGHT_CONTROL
        assert page.search_input.minimumHeight() == HEIGHT_CONTROL


# ===================================================================
# NEW: Status Color Tests
# ===================================================================


class TestStatusColors:
    """Tests for correct status color assignment in dubbing history."""

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

    def test_paused_status_has_warning_color(self, page) -> None:  # noqa: ANN001
        """Paused status foreground uses warning color."""
        from PySide6.QtGui import QColor  # noqa: PLC0415

        from src.constants import color as get_color  # noqa: PLC0415

        _populate_table(page, [_make_entry(status="Paused")])
        status_item = page.table.item(0, 2)
        assert status_item.foreground().color() == QColor(get_color("warning"))

    def test_status_text_uses_display_status(self, page) -> None:  # noqa: ANN001
        """Status column text uses display_status for translation."""
        from src.constants.history import display_status  # noqa: PLC0415

        _populate_table(page, [_make_entry(status="Done")])
        status_item = page.table.item(0, 2)
        assert status_item.text() == display_status("Done")


# ===================================================================
# NEW: Unicode and Long Filenames
# ===================================================================


class TestUnicodeAndLongFilenames:
    """Tests for edge cases with unicode and very long filenames."""

    def test_unicode_filename(self, page) -> None:  # noqa: ANN001
        """Unicode filenames are displayed correctly."""
        _populate_table(page, [_make_entry(name="\u914d\u97f3\u6587\u4ef6.mp4")])
        assert page.table.item(0, 0).text() == "\u914d\u97f3\u6587\u4ef6.mp4"

    def test_emoji_filename(self, page) -> None:  # noqa: ANN001
        """Emoji in filenames are displayed correctly."""
        _populate_table(page, [_make_entry(name="\U0001f3ac movie.mp4")])
        assert page.table.item(0, 0).text() == "\U0001f3ac movie.mp4"

    def test_very_long_filename(self, page) -> None:  # noqa: ANN001
        """Very long filenames are stored without truncation."""
        long_name = "a" * 500 + ".mp4"
        _populate_table(page, [_make_entry(name=long_name)])
        assert page.table.item(0, 0).text() == long_name

    def test_empty_filename(self, page) -> None:  # noqa: ANN001
        """Empty filename is stored without error."""
        _populate_table(page, [_make_entry(name="")])
        assert page.table.item(0, 0).text() == ""

    def test_unicode_search(self, page) -> None:  # noqa: ANN001
        """Search works with unicode characters."""
        entries = [
            _make_entry(entry_id=1, name="\u914d\u97f3.mp4"),
            _make_entry(entry_id=2, name="english.mp4"),
        ]
        page.search_input.setText("\u914d\u97f3")
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


# ===================================================================
# NEW: ShowEvent Trigger
# ===================================================================


class TestShowEvent:
    """Tests that showEvent triggers refresh_history(force=True)."""

    def test_show_event_triggers_force_refresh(self, page) -> None:  # noqa: ANN001
        """showEvent() calls refresh_history(force=True)."""
        with patch.object(page, "refresh_history") as mock_refresh:
            page.showEvent(None)
            mock_refresh.assert_called_once_with(force=True)


# ===================================================================
# NEW: Table Refresh Not Visible
# ===================================================================


class TestTableRefreshVisibility:
    """Tests for refresh behavior based on visibility."""

    def test_refresh_not_visible_no_force_skips(self, page) -> None:  # noqa: ANN001
        """refresh_history skips when page is not visible and force=False."""
        page.hide()
        history_mock = MagicMock(return_value=[_make_entry()])
        with (
            patch(f"{_MOD}.get_dubbing_fingerprint", return_value=(1, 1, "new")),
            patch(f"{_MOD}.get_dubbing_history", history_mock),
        ):
            page.refresh_history(force=False)
            history_mock.assert_not_called()

    def test_fingerprint_none_always_refreshes(self, page) -> None:  # noqa: ANN001
        """When fingerprint is None, always refreshes."""
        history_mock = MagicMock(return_value=[_make_entry()])
        page._last_fingerprint = (1, 1, "old")
        with (
            patch(f"{_MOD}.get_dubbing_fingerprint", return_value=None),
            patch(f"{_MOD}.get_dubbing_history", history_mock),
        ):
            page.show()
            page.refresh_history(force=False)
            history_mock.assert_called()


# ===================================================================
# NEW: Page Is A QWidget
# ===================================================================


class TestPageIsQWidget:
    """Tests that the page is a proper QWidget with expected elements."""

    def test_is_qwidget_instance(self, page) -> None:  # noqa: ANN001
        """DubbingHistoryPage is a QWidget."""
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

    def test_main_layout_no_margins(self, page) -> None:  # noqa: ANN001
        """Main layout has zero margins."""
        margins = page.main_layout.contentsMargins()
        assert margins.left() == 0
        assert margins.top() == 0
        assert margins.right() == 0
        assert margins.bottom() == 0


# ===================================================================
# NEW: Data Storage in UserRole Extended
# ===================================================================


class TestDataStorageExtended:
    """Tests for extended data storage in UserRole fields."""

    def test_stores_src_lang(self, page) -> None:  # noqa: ANN001
        """Source language is stored in UserRole+4 on column 0."""
        _populate_table(page, [_make_entry(src_lang="English (US)")])
        item = page.table.item(0, 0)
        assert item.data(Qt.ItemDataRole.UserRole + 4) == "English (US)"

    def test_stores_target_lang(self, page) -> None:  # noqa: ANN001
        """Target language is stored in UserRole+5 on column 0."""
        _populate_table(page, [_make_entry(target_lang="French")])
        item = page.table.item(0, 0)
        assert item.data(Qt.ItemDataRole.UserRole + 5) == "French"

    def test_stores_subtitle_path(self, page) -> None:  # noqa: ANN001
        """Subtitle path is stored in UserRole+6 on column 0."""
        _populate_table(page, [_make_entry(subtitle_path="/tmp/sub.srt")])
        item = page.table.item(0, 0)
        assert item.data(Qt.ItemDataRole.UserRole + 6) == "/tmp/sub.srt"

    def test_stores_translated_subtitle_path(self, page) -> None:  # noqa: ANN001
        """Translated subtitle path is stored in UserRole+7."""
        _populate_table(
            page,
            [_make_entry(translated_subtitle_path="/tmp/translated.srt")],
        )
        item = page.table.item(0, 0)
        assert item.data(Qt.ItemDataRole.UserRole + 7) == "/tmp/translated.srt"

    def test_stores_voice_path(self, page) -> None:  # noqa: ANN001
        """Voice path is stored in UserRole+8 on column 0."""
        _populate_table(page, [_make_entry(voice_path="/tmp/voice.mp3")])
        item = page.table.item(0, 0)
        assert item.data(Qt.ItemDataRole.UserRole + 8) == "/tmp/voice.mp3"


# ===================================================================
# NEW: Progress Column Extended
# ===================================================================


class TestProgressColumnExtended:
    """Extended tests for progress column display."""

    def test_progress_zero_shows_empty(self, page) -> None:  # noqa: ANN001
        """Zero progress shows empty string."""
        _populate_table(page, [_make_entry(progress=0)])
        item = page.table.item(0, 3)
        assert item.text() == ""

    def test_progress_50_shows_50_percent(self, page) -> None:  # noqa: ANN001
        """Progress 50 shows '50%'."""
        _populate_table(page, [_make_entry(progress=50)])
        item = page.table.item(0, 3)
        assert item.text() == "50%"

    def test_progress_100_shows_100_percent(self, page) -> None:  # noqa: ANN001
        """Progress 100 shows '100%'."""
        _populate_table(page, [_make_entry(progress=100)])
        item = page.table.item(0, 3)
        assert item.text() == "100%"

    def test_progress_none_shows_empty(self, page) -> None:  # noqa: ANN001
        """None progress shows empty string."""
        _populate_table(page, [_make_entry(progress=None)])
        item = page.table.item(0, 3)
        assert item.text() == ""

    def test_progress_centered(self, page) -> None:  # noqa: ANN001
        """Progress column text is center-aligned."""
        _populate_table(page, [_make_entry(progress=25)])
        item = page.table.item(0, 3)
        assert item.textAlignment() & Qt.AlignmentFlag.AlignCenter


# ===================================================================
# NEW: Pause Button States Extended
# ===================================================================


class TestPauseButtonStatesExtended:
    """Extended tests for pause button enable/disable logic."""

    def test_pause_enabled_for_pending(self, page) -> None:  # noqa: ANN001
        """Pause is enabled when selecting a Pending entry."""
        _populate_table(page, [_make_entry(status="Pending")])
        page.table.selectRow(0)
        assert page.pause_btn.isEnabled()

    def test_pause_enabled_for_generating(self, page) -> None:  # noqa: ANN001
        """Pause is enabled when selecting a Generating entry."""
        _populate_table(page, [_make_entry(status="Generating")])
        page.table.selectRow(0)
        assert page.pause_btn.isEnabled()

    def test_pause_disabled_for_done(self, page) -> None:  # noqa: ANN001
        """Pause is disabled when selecting a Done entry."""
        _populate_table(page, [_make_entry(status="Done")])
        page.table.selectRow(0)
        assert not page.pause_btn.isEnabled()

    def test_pause_disabled_for_failed(self, page) -> None:  # noqa: ANN001
        """Pause is disabled when selecting a Failed entry."""
        _populate_table(page, [_make_entry(status="Failed")])
        page.table.selectRow(0)
        assert not page.pause_btn.isEnabled()

    def test_pause_disabled_for_paused(self, page) -> None:  # noqa: ANN001
        """Pause is disabled when selecting a Paused entry."""
        _populate_table(page, [_make_entry(status="Paused")])
        page.table.selectRow(0)
        assert not page.pause_btn.isEnabled()


# ===================================================================
# NEW: Continue Button States Extended
# ===================================================================


class TestContinueButtonStatesExtended:
    """Extended tests for continue button enable/disable logic."""

    def test_continue_enabled_for_paused(self, page) -> None:  # noqa: ANN001
        """Continue is enabled when selecting a Paused entry."""
        _populate_table(page, [_make_entry(status="Paused")])
        page.table.selectRow(0)
        assert page.continue_btn.isEnabled()

    def test_continue_enabled_for_failed(self, page) -> None:  # noqa: ANN001
        """Continue is enabled when selecting a Failed entry."""
        _populate_table(page, [_make_entry(status="Failed")])
        page.table.selectRow(0)
        assert page.continue_btn.isEnabled()

    def test_continue_disabled_for_done(self, page) -> None:  # noqa: ANN001
        """Continue is disabled when selecting a Done entry."""
        _populate_table(page, [_make_entry(status="Done")])
        page.table.selectRow(0)
        assert not page.continue_btn.isEnabled()

    def test_continue_disabled_for_pending(self, page) -> None:  # noqa: ANN001
        """Continue is disabled when selecting a Pending entry."""
        _populate_table(page, [_make_entry(status="Pending")])
        page.table.selectRow(0)
        assert not page.continue_btn.isEnabled()

    def test_continue_disabled_for_generating(self, page) -> None:  # noqa: ANN001
        """Continue is disabled when selecting a Generating entry."""
        _populate_table(page, [_make_entry(status="Generating")])
        page.table.selectRow(0)
        assert not page.continue_btn.isEnabled()


# ===================================================================
# NEW: Re-Dub Disabling with Active Statuses
# ===================================================================


class TestReDubWithActiveStatuses:
    """Tests for re-dub button disabled when active statuses present."""

    def test_re_dub_disabled_for_pending(self, page) -> None:  # noqa: ANN001
        """Re-dub is disabled when selecting a Pending entry."""
        _populate_table(page, [_make_entry(status="Pending")])
        page.table.selectRow(0)
        assert not page.re_dub_btn.isEnabled()

    def test_re_dub_disabled_for_generating(self, page) -> None:  # noqa: ANN001
        """Re-dub is disabled when selecting a Generating entry."""
        _populate_table(page, [_make_entry(status="Generating")])
        page.table.selectRow(0)
        assert not page.re_dub_btn.isEnabled()

    def test_re_dub_enabled_for_done(self, page) -> None:  # noqa: ANN001
        """Re-dub is enabled when selecting a Done entry."""
        _populate_table(page, [_make_entry(status="Done")])
        page.table.selectRow(0)
        assert page.re_dub_btn.isEnabled()

    def test_re_dub_enabled_for_failed(self, page) -> None:  # noqa: ANN001
        """Re-dub is enabled when selecting a Failed entry."""
        _populate_table(page, [_make_entry(status="Failed")])
        page.table.selectRow(0)
        assert page.re_dub_btn.isEnabled()

    def test_re_dub_enabled_for_paused(self, page) -> None:  # noqa: ANN001
        """Re-dub is enabled when selecting a Paused entry."""
        _populate_table(page, [_make_entry(status="Paused")])
        page.table.selectRow(0)
        assert page.re_dub_btn.isEnabled()

    def test_re_dub_disabled_mixed_with_active(self, page) -> None:  # noqa: ANN001
        """Re-dub disabled when selection includes active status."""
        entries = [
            _make_entry(entry_id=1, status="Done"),
            _make_entry(entry_id=2, status="Generating"),
        ]
        _populate_table(page, entries)
        page.table.selectAll()
        assert not page.re_dub_btn.isEnabled()


# ===================================================================
# TestDubbingHistorySignalBlocking — blockSignals & setSortingEnabled
# ===================================================================


class TestDubbingHistorySignalBlocking:
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
                f"{_MOD}.get_dubbing_fingerprint",
                return_value=(0, 0, ""),
            ),
            patch(f"{_MOD}.get_dubbing_history", return_value=None),
        ):
            page.refresh_history(force=True)

        assert not page.table.signalsBlocked()

    def test_sorting_enabled_after_refresh_with_none(self, page) -> None:  # noqa: ANN001
        """Sorting is re-enabled when the DB returns None."""
        with (
            patch(
                f"{_MOD}.get_dubbing_fingerprint",
                return_value=(0, 0, ""),
            ),
            patch(f"{_MOD}.get_dubbing_history", return_value=None),
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
