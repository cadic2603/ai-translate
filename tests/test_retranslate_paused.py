"""Tests for Re-translate functionality in HistoryPage."""

from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtCore import Qt

from src.constants import (
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_PAUSED,
    STATUS_PENDING,
    STATUS_TRANSLATING,
)
from src.core.database import add_history_entry, clear_history
from src.ui.pages.history import HistoryPage


@pytest.fixture
def history_page(qtbot: object) -> HistoryPage:
    """Fixture to set up HistoryPage."""
    clear_history()  # Ensure fresh state for each test

    page = HistoryPage()
    # Stop the timer to avoid background refreshes during test
    page.timer.stop()
    page.show()
    qtbot.addWidget(page)
    return page


def test_retranslate_button_enabled_for_paused(
    history_page: HistoryPage,
    qtbot: object,
) -> None:
    """Verify that Re-translate button is enabled for Paused files."""
    add_history_entry("paused.txt", "English (US)", "French", STATUS_PAUSED)
    history_page.refresh_history()

    # Select the first row
    history_page.table.selectRow(0)

    # Re-translate should be enabled
    assert history_page.retranslate_btn.isEnabled(), (
        "Re-translate button should be enabled for PAUSED status"
    )
    # Continue should also be enabled
    assert history_page.continue_btn.isEnabled(), (
        "Continue button should be enabled for PAUSED status"
    )
    # Pause should be disabled
    assert not history_page.pause_btn.isEnabled(), (
        "Pause button should be disabled for PAUSED status"
    )


def test_retranslate_button_enabled_for_failed(
    history_page: HistoryPage,
    qtbot: object,
) -> None:
    """Verify that Re-translate button is enabled for Failed files."""
    add_history_entry("failed.txt", "English (US)", "French", STATUS_FAILED)
    history_page.refresh_history()

    # Select the first row
    history_page.table.selectRow(0)

    # Re-translate should be enabled
    assert history_page.retranslate_btn.isEnabled(), (
        "Re-translate button should be enabled for FAILED status"
    )
    # Continue should be enabled
    assert history_page.continue_btn.isEnabled(), (
        "Continue button should be enabled for FAILED status"
    )


def test_retranslate_button_enabled_for_done(
    history_page: HistoryPage,
    qtbot: object,
) -> None:
    """Verify that Re-translate button is enabled for Done files."""
    add_history_entry("done.txt", "English (US)", "French", STATUS_DONE)
    history_page.refresh_history()

    # Select the first row
    history_page.table.selectRow(0)

    # Re-translate should be enabled
    assert history_page.retranslate_btn.isEnabled(), (
        "Re-translate button should be enabled for DONE status"
    )


def test_retranslate_button_disabled_for_translating(
    history_page: HistoryPage,
    qtbot: object,
) -> None:
    """Verify that Re-translate button is disabled for Translating files."""
    add_history_entry("translating.txt", "English (US)", "French", STATUS_TRANSLATING)
    history_page.refresh_history()

    # Select the first row
    history_page.table.selectRow(0)

    # Re-translate should be disabled
    assert not history_page.retranslate_btn.isEnabled(), (
        "Re-translate button should be disabled for TRANSLATING status"
    )
    # Pause should be enabled
    assert history_page.pause_btn.isEnabled(), (
        "Pause button should be enabled for TRANSLATING status"
    )


def test_on_retranslate_action(
    history_page: HistoryPage,
    qtbot: object,
    tmp_path: Path,
) -> None:
    """Verify that on_retranslate action correctly resets DB state for paused files."""
    # Create a dummy file so _validate_selection passes
    dummy_file = tmp_path / "paused.txt"
    dummy_file.touch()

    h_id = add_history_entry(
        "paused.txt",
        "English (US)",
        "French",
        STATUS_PAUSED,
        source_path=str(dummy_file),
    )
    history_page.refresh_history()

    # In HistoryPage, path is stored in UserRole + 1 of the first item
    item = history_page.table.item(0, 0)
    item.setData(Qt.ItemDataRole.UserRole + 1, str(dummy_file))

    # Select the row
    history_page.table.selectRow(0)

    # Mock _start_worker_if_needed to avoid starting real threads
    history_page._start_worker_if_needed = lambda tasks: None

    # Mock LanguageSelectionDialog to return accepted selection
    with (
        patch(
            "src.ui.pages.history.LanguageSelectionDialog.get_selection",
            return_value=("English (US)", "Vietnamese", None, True),
        ),
        patch(
            "src.ui.pages.history.check_llm_setup",
            return_value=True,
        ),
    ):
        history_page.on_retranslate()

    # Verify DB state
    from src.core.database import get_history, get_history_entry_status  # noqa: PLC0415

    assert get_history_entry_status(h_id) == STATUS_PENDING

    # Check progress reset and language update in DB
    history = get_history()
    assert history[0][5] == 0
    # Verify languages were updated
    assert history[0][2] == "English (US)"
    assert history[0][3] == "Vietnamese"


def test_button_states_for_pending(
    history_page: HistoryPage,
    qtbot: object,
) -> None:
    """Verify button states when a Pending entry is selected."""
    add_history_entry("pending.txt", "English (US)", "French", STATUS_PENDING)
    history_page.refresh_history()

    history_page.table.selectRow(0)

    # Pending is an ACTIVE_STATUS: pause=enabled, retranslate=disabled,
    # continue=disabled, open=enabled, delete=enabled
    assert history_page.pause_btn.isEnabled(), (
        "Pause button should be enabled for PENDING status"
    )
    assert not history_page.retranslate_btn.isEnabled(), (
        "Re-translate button should be disabled for PENDING status"
    )
    assert not history_page.continue_btn.isEnabled(), (
        "Continue button should be disabled for PENDING status"
    )
    assert history_page.open_btn.isEnabled(), (
        "Open button should be enabled when a row is selected"
    )
    assert history_page.delete_btn.isEnabled(), (
        "Delete button should be enabled when a row is selected"
    )


def test_button_states_with_no_selection(
    history_page: HistoryPage,
    qtbot: object,
) -> None:
    """All action buttons are disabled when nothing is selected."""
    add_history_entry("no_sel.txt", "English (US)", "French", STATUS_DONE)
    history_page.refresh_history()
    # Do not select any row

    assert not history_page.pause_btn.isEnabled(), (
        "Pause button should be disabled with no selection"
    )
    assert not history_page.retranslate_btn.isEnabled(), (
        "Re-translate button should be disabled with no selection"
    )
    assert not history_page.continue_btn.isEnabled(), (
        "Continue button should be disabled with no selection"
    )
    assert not history_page.open_btn.isEnabled(), (
        "Open button should be disabled with no selection"
    )
    assert not history_page.delete_btn.isEnabled(), (
        "Delete button should be disabled with no selection"
    )
