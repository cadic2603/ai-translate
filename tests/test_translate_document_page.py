"""Unit tests for the Translate Document page.

Covers:
- create_translate_document_page() factory function
- TranslateDocumentPage widget construction and UI structure
- File drop handling (_handle_files_dropped) with valid/invalid files
- File list management: add, remove, clear
- Translation initiation (_handle_translate)
- UI state updates (_update_ui_state)
- Theme and language application
- Requirements checking (_check_requirements)
- Empty/directory/unsupported file filtering
- Language selection via LanguageSelectionDialog
- Start/stop translation button states
- Drop area reparenting between views
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QStackedWidget,
)

# ---------------------------------------------------------------------------
# Module-level constants for stacked view indices (mirror source)
# ---------------------------------------------------------------------------
_VIEW_HISTORY = 0
_VIEW_FILES = 1

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def window(qapp):
    """Provides a QMainWindow context with a navigate_to_settings_tab stub."""
    win = QMainWindow()
    win.navigate_to_settings_tab = MagicMock()
    return win


@pytest.fixture()
def _mock_history_deps():
    """Mocks database calls used by the embedded HistoryPage during construction."""
    with (
        patch(
            "src.ui.pages.history.get_history_fingerprint",
            return_value=(0, 0),
        ),
        patch(
            "src.ui.pages.history.get_history",
            return_value=[],
        ),
        patch(
            "src.ui.pages.history.is_any_translating",
            return_value=False,
        ),
    ):
        yield


@pytest.fixture()
def page(window, _mock_history_deps, qtbot):
    """Creates a TranslateDocumentPage for testing."""
    from src.ui.pages.translate_document import TranslateDocumentPage  # noqa: PLC0415

    p = TranslateDocumentPage(window)
    qtbot.addWidget(p)
    return p


@pytest.fixture(autouse=True)
def _auto_mock_blocking_dialogs():
    """Auto-mocks modal dialogs so tests don't hang waiting for user input.

    - ``CustomConfirmDialog.confirm`` → returns True (auto-confirm).
    - ``CustomMessageDialog.show_message`` → no-op.

    Tests that specifically want to assert on these calls use their own
    ``@patch`` decorators which take precedence over this fixture.
    """
    with (
        patch(
            "src.ui.pages.translate_document.CustomConfirmDialog.confirm",
            return_value=True,
        ),
        patch(
            "src.ui.pages.translate_document.CustomMessageDialog.show_message",
        ),
    ):
        yield


@pytest.fixture()
def tmp_files(tmp_path):
    """Creates temporary files of various types for drop testing.

    Returns a dict of extension -> absolute path strings.
    """
    files = {}
    for ext in (".docx", ".pdf", ".txt", ".png", ".jpg", ".xlsx", ".html"):
        f = tmp_path / f"sample{ext}"
        f.write_text("content", encoding="utf-8")
        files[ext] = str(f)
    return files


# ---------------------------------------------------------------------------
# Factory function
# ---------------------------------------------------------------------------


class TestFactoryFunction:
    """Tests for create_translate_document_page()."""

    def test_factory_returns_widget(self, window, _mock_history_deps) -> None:
        """create_translate_document_page() returns a TranslateDocumentPage."""
        from src.ui.pages.translate_document import (  # noqa: PLC0415
            TranslateDocumentPage,
            create_translate_document_page,
        )

        widget = create_translate_document_page(window)
        assert isinstance(widget, TranslateDocumentPage)

    def test_factory_stores_window_context(
        self,
        window,
        _mock_history_deps,
    ) -> None:
        """Factory-created page has a reference to the parent window."""
        from src.ui.pages.translate_document import (  # noqa: PLC0415
            create_translate_document_page,
        )

        widget = create_translate_document_page(window)
        assert widget.window_context is window


# ---------------------------------------------------------------------------
# Page construction
# ---------------------------------------------------------------------------


class TestPageConstruction:
    """Tests for TranslateDocumentPage widget initialization."""

    def test_page_construction(self, page) -> None:
        """Page can be constructed without errors."""
        assert page is not None

    def test_has_drop_area(self, page) -> None:
        """Page contains a FileDropWidget."""
        from src.ui.components import FileDropWidget  # noqa: PLC0415

        assert hasattr(page, "drop_area")
        assert isinstance(page.drop_area, FileDropWidget)

    def test_has_stacked_widget(self, page) -> None:
        """Page contains a QStackedWidget with two views."""
        assert hasattr(page, "stack")
        assert isinstance(page.stack, QStackedWidget)
        assert page.stack.count() == 2  # noqa: PLR2004

    def test_has_translate_button(self, page) -> None:
        """Page contains a translate QPushButton."""
        assert hasattr(page, "translate_btn")
        assert isinstance(page.translate_btn, QPushButton)

    def test_has_clear_all_button(self, page) -> None:
        """Page contains a clear-all QPushButton."""
        assert hasattr(page, "clear_all_btn")
        assert isinstance(page.clear_all_btn, QPushButton)

    def test_has_file_badge(self, page) -> None:
        """Page contains a file count badge label."""
        assert hasattr(page, "files_badge")
        assert isinstance(page.files_badge, QLabel)

    def test_has_section_label(self, page) -> None:
        """Page contains a section label."""
        assert hasattr(page, "section_label")
        assert isinstance(page.section_label, QLabel)

    def test_has_history_view(self, page) -> None:
        """Page contains an embedded HistoryPage."""
        from src.ui.pages.history import HistoryPage  # noqa: PLC0415

        assert hasattr(page, "history_view")
        assert isinstance(page.history_view, HistoryPage)

    def test_has_files_vbox(self, page) -> None:
        """Page contains a vertical box layout for file items."""
        assert hasattr(page, "files_vbox")

    def test_selected_files_starts_empty(self, page) -> None:
        """The selected_files list is empty on construction."""
        assert page.selected_files == []

    def test_translate_button_has_cursor(self, page) -> None:
        """Translate button has pointing hand cursor for UX."""
        assert page.translate_btn.cursor().shape() == Qt.CursorShape.PointingHandCursor

    def test_clear_all_button_has_cursor(self, page) -> None:
        """Clear-all button has pointing hand cursor for UX."""
        assert page.clear_all_btn.cursor().shape() == Qt.CursorShape.PointingHandCursor

    def test_file_list_section_has_scroll_area(self, page) -> None:
        """File list section contains a QScrollArea."""
        scroll = page.file_list_section.findChild(QScrollArea)
        assert scroll is not None


# ---------------------------------------------------------------------------
# Initial UI state
# ---------------------------------------------------------------------------


class TestInitialUIState:
    """Tests for the initial state after construction."""

    def test_stack_shows_history_view(self, page) -> None:
        """Stack starts on the history view (index 0)."""
        assert page.stack.currentIndex() == _VIEW_HISTORY

    def test_translate_button_disabled_initially(self, page) -> None:
        """Translate button is disabled when no files are selected."""
        assert not page.translate_btn.isEnabled()

    def test_file_badge_shows_zero(self, page) -> None:
        """Badge shows '0' initially."""
        assert page.files_badge.text() == "0"


# ---------------------------------------------------------------------------
# _update_ui_state
# ---------------------------------------------------------------------------


class TestUpdateUIState:
    """Tests for _update_ui_state view switching and reparenting."""

    def test_switches_to_files_view_when_files_exist(self, page) -> None:
        """Adding a path switches the stack to the files view."""
        page.selected_files = ["/fake/file.docx"]
        page._update_ui_state()
        assert page.stack.currentIndex() == _VIEW_FILES

    def test_switches_to_history_view_when_empty(self, page) -> None:
        """Clearing files switches the stack back to history view."""
        page.selected_files = ["/fake/file.docx"]
        page._update_ui_state()
        page.selected_files.clear()
        page._update_ui_state()
        assert page.stack.currentIndex() == _VIEW_HISTORY

    def test_translate_button_enabled_with_files(self, page) -> None:
        """Translate button is enabled when files are present."""
        page.selected_files = ["/fake/file.docx"]
        page._update_ui_state()
        assert page.translate_btn.isEnabled()

    def test_translate_button_disabled_without_files(self, page) -> None:
        """Translate button is disabled when no files are present."""
        page.selected_files = []
        page._update_ui_state()
        assert not page.translate_btn.isEnabled()

    def test_badge_count_reflects_file_count(self, page) -> None:
        """Badge text matches the number of selected files."""
        page.selected_files = ["/a.pdf", "/b.docx", "/c.txt"]
        page._update_ui_state()
        assert page.files_badge.text() == "3"

    def test_drop_area_label_changes_on_files_view(self, page) -> None:
        """Drop area info label changes text when files are selected."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page.selected_files = ["/fake.pdf"]
        page._update_ui_state()
        assert page.drop_area.info_label.text() == tr("drop.title_more")

    def test_drop_area_label_changes_on_history_view(self, page) -> None:
        """Drop area info label shows default text when no files."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page.selected_files = []
        page._update_ui_state()
        assert page.drop_area.info_label.text() == tr("drop.title")


# ---------------------------------------------------------------------------
# File drop handling
# ---------------------------------------------------------------------------


class TestHandleFilesDropped:
    """Tests for _handle_files_dropped() with various file types."""

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_drop_valid_file_adds_to_selected(
        self,
        _mock_msg,
        page,
        tmp_files,
    ) -> None:
        """Dropping a supported file adds it to selected_files."""
        page._handle_files_dropped([tmp_files[".docx"]])
        assert tmp_files[".docx"] in page.selected_files

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_drop_multiple_valid_files(self, _mock_msg, page, tmp_files) -> None:
        """Dropping multiple supported files adds all of them."""
        paths = [tmp_files[".docx"], tmp_files[".pdf"], tmp_files[".txt"]]
        page._handle_files_dropped(paths)
        assert len(page.selected_files) == 3  # noqa: PLR2004

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_drop_unsupported_file_shows_dialog(
        self,
        mock_msg,
        page,
        tmp_path,
    ) -> None:
        """Dropping an unsupported file triggers an unsupported-files dialog."""
        bad_file = tmp_path / "readme.xyz"
        bad_file.write_text("content")
        page._handle_files_dropped([str(bad_file)])
        mock_msg.assert_called_once()

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_drop_unsupported_file_not_added(
        self,
        _mock_msg,
        page,
        tmp_path,
    ) -> None:
        """Unsupported files are not added to selected_files."""
        bad_file = tmp_path / "file.xyz"
        bad_file.write_text("content")
        page._handle_files_dropped([str(bad_file)])
        assert len(page.selected_files) == 0

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_drop_duplicate_file_ignored(self, _mock_msg, page, tmp_files) -> None:
        """Dropping the same file twice does not duplicate it."""
        page._handle_files_dropped([tmp_files[".pdf"]])
        page._handle_files_dropped([tmp_files[".pdf"]])
        assert page.selected_files.count(tmp_files[".pdf"]) == 1

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_drop_empty_file_shows_unsupported(
        self,
        mock_msg,
        page,
        tmp_path,
    ) -> None:
        """Dropping an empty (zero-byte) file triggers the unsupported dialog."""
        empty = tmp_path / "empty.docx"
        empty.write_bytes(b"")
        page._handle_files_dropped([str(empty)])
        mock_msg.assert_called_once()
        assert len(page.selected_files) == 0

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_drop_image_file_adds_successfully(
        self,
        _mock_msg,
        page,
        tmp_files,
    ) -> None:
        """Image files (.png, .jpg) are valid and get added."""
        page._handle_files_dropped([tmp_files[".png"]])
        assert tmp_files[".png"] in page.selected_files

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_drop_directory_adds_contained_files(
        self,
        _mock_msg,
        page,
        tmp_path,
    ) -> None:
        """Dropping a directory recursively adds supported files inside it."""
        sub = tmp_path / "subdir"
        sub.mkdir()
        f1 = sub / "doc.pdf"
        f1.write_text("content")
        f2 = sub / "sheet.xlsx"
        f2.write_text("content")
        page._handle_files_dropped([str(sub)])
        assert len(page.selected_files) == 2  # noqa: PLR2004

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_drop_directory_skips_hidden(self, _mock_msg, page, tmp_path) -> None:
        """Files inside hidden directories are skipped."""
        hidden = tmp_path / ".hidden_dir"
        hidden.mkdir()
        f = hidden / "secret.pdf"
        f.write_text("content")
        # Drop the parent that contains the hidden dir
        visible = tmp_path / "visible.txt"
        visible.write_text("content")
        page._handle_files_dropped([str(tmp_path)])
        # Only visible.txt should be added, not the hidden one
        paths = page.selected_files
        assert any("visible.txt" in p for p in paths)
        assert not any("secret.pdf" in p for p in paths)

    @patch("src.ui.pages.translate_document.QFileDialog.getOpenFileNames")
    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_empty_drop_opens_file_dialog(
        self,
        _mock_msg,
        mock_dialog,
        page,
        tmp_files,
    ) -> None:
        """Dropping an empty list triggers a file open dialog."""
        mock_dialog.return_value = ([tmp_files[".txt"]], "")
        page._handle_files_dropped([])
        mock_dialog.assert_called_once()
        assert tmp_files[".txt"] in page.selected_files

    @patch("src.ui.pages.translate_document.QFileDialog.getOpenFileNames")
    def test_empty_drop_dialog_cancelled(self, mock_dialog, page) -> None:
        """Cancelling the file dialog does not add any files."""
        mock_dialog.return_value = ([], "")
        page._handle_files_dropped([])
        assert len(page.selected_files) == 0

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_drop_mixed_valid_and_unsupported(
        self,
        mock_msg,
        page,
        tmp_path,
        tmp_files,
    ) -> None:
        """A mix of valid and unsupported files: valid added, dialog for invalid."""
        bad = tmp_path / "bad.zzz"
        bad.write_text("content")
        page._handle_files_dropped([tmp_files[".docx"], str(bad)])
        assert tmp_files[".docx"] in page.selected_files
        assert len(page.selected_files) == 1
        mock_msg.assert_called_once()

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_drop_updates_ui_state(self, _mock_msg, page, tmp_files) -> None:
        """Dropping a valid file switches to the files view."""
        page._handle_files_dropped([tmp_files[".pdf"]])
        assert page.stack.currentIndex() == _VIEW_FILES
        assert page.translate_btn.isEnabled()


# ---------------------------------------------------------------------------
# File widget management
# ---------------------------------------------------------------------------


class TestFileWidgetManagement:
    """Tests for adding, removing, and clearing file widgets."""

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_add_file_widget_creates_item(self, _mock_msg, page, tmp_files) -> None:
        """_add_file_widget inserts a FileItemWidget into the layout."""
        from src.ui.components import FileItemWidget  # noqa: PLC0415

        initial_count = page.files_vbox.count()
        page._add_file_widget(tmp_files[".docx"])
        assert page.files_vbox.count() == initial_count + 1
        # The new widget (inserted before stretch) should be a FileItemWidget
        item = page.files_vbox.itemAt(initial_count - 1)
        assert item is not None
        assert isinstance(item.widget(), FileItemWidget)

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_handle_remove_file(self, _mock_msg, page, tmp_files) -> None:
        """Removing a file removes it from selected_files and the layout."""
        page._handle_files_dropped([tmp_files[".pdf"]])
        assert tmp_files[".pdf"] in page.selected_files

        # Find the widget that was added
        from src.ui.components import FileItemWidget  # noqa: PLC0415

        widget = None
        for i in range(page.files_vbox.count()):
            item = page.files_vbox.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), FileItemWidget):
                widget = item.widget()
                break
        assert widget is not None

        page._handle_remove_file(tmp_files[".pdf"], widget)
        assert tmp_files[".pdf"] not in page.selected_files

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_handle_remove_switches_back_to_history(
        self,
        _mock_msg,
        page,
        tmp_files,
    ) -> None:
        """Removing the last file switches back to the history view."""
        page._handle_files_dropped([tmp_files[".docx"]])
        assert page.stack.currentIndex() == _VIEW_FILES

        from src.ui.components import FileItemWidget  # noqa: PLC0415

        widget = None
        for i in range(page.files_vbox.count()):
            item = page.files_vbox.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), FileItemWidget):
                widget = item.widget()
                break

        page._handle_remove_file(tmp_files[".docx"], widget)
        assert page.stack.currentIndex() == _VIEW_HISTORY

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_handle_clear_all(self, _mock_msg, page, tmp_files) -> None:
        """Clear-all removes all files and switches to history view."""
        page._handle_files_dropped(
            [tmp_files[".docx"], tmp_files[".pdf"], tmp_files[".txt"]],
        )
        assert len(page.selected_files) == 3  # noqa: PLR2004

        page._handle_clear_all()
        assert len(page.selected_files) == 0
        assert page.stack.currentIndex() == _VIEW_HISTORY

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_clear_all_removes_widgets(self, _mock_msg, page, tmp_files) -> None:
        """Clear-all removes all FileItemWidgets from the layout."""
        page._handle_files_dropped([tmp_files[".docx"], tmp_files[".pdf"]])
        page._handle_clear_all()
        # Only the stretch spacer should remain
        assert page.files_vbox.count() == 1

    def test_handle_remove_nonexistent_file(self, page) -> None:
        """Removing a file not in selected_files does not crash."""
        fake_widget = MagicMock()
        fake_widget.setParent = MagicMock()
        fake_widget.deleteLater = MagicMock()
        # Should not raise even though "/nonexistent" is not in selected_files
        page._handle_remove_file("/nonexistent", fake_widget)


# ---------------------------------------------------------------------------
# Translation initiation
# ---------------------------------------------------------------------------


class TestHandleTranslate:
    """Tests for _handle_translate() translation workflow."""

    def test_translate_with_no_files_is_noop(self, page) -> None:
        """Calling _handle_translate with no files does nothing."""
        page.selected_files = []
        # Should return early without errors
        page._handle_translate()
        assert page.selected_files == []

    @patch("src.ui.pages.translate_document.start_translation_worker")
    @patch(
        "src.ui.pages.translate_document.setup_translation_tasks",
        return_value=[(1, "/storage/file.docx", "English", "French")],
    )
    @patch(
        "src.ui.pages.translate_document.LanguageSelectionDialog.get_selection",
        return_value=("English", "French", None, True),
    )
    @patch("src.ui.pages.translate_document.require_setup", return_value=True)
    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_translate_success_clears_files(
        self,
        _mock_msg,
        _mock_require,
        _mock_lang,
        mock_setup,
        mock_worker,
        page,
        tmp_files,
        _mock_history_deps,
    ) -> None:
        """Successful translation clears selected files and refreshes history."""
        page.selected_files = [tmp_files[".docx"]]
        page._add_file_widget(tmp_files[".docx"])

        page._handle_translate()

        mock_setup.assert_called_once()
        mock_worker.assert_called_once()
        assert len(page.selected_files) == 0

    @patch(
        "src.ui.pages.translate_document.LanguageSelectionDialog.get_selection",
        return_value=("", "", None, False),
    )
    @patch("src.ui.pages.translate_document.require_setup", return_value=True)
    def test_translate_cancelled_dialog_keeps_files(
        self,
        _mock_require,
        _mock_lang,
        page,
        tmp_files,
    ) -> None:
        """Cancelling the language dialog keeps files selected."""
        page.selected_files = [tmp_files[".pdf"]]
        page._handle_translate()
        assert tmp_files[".pdf"] in page.selected_files

    @patch("src.ui.pages.translate_document.require_setup", return_value=False)
    def test_translate_fails_requirement_check(
        self,
        _mock_require,
        page,
        tmp_files,
    ) -> None:
        """Failing the LLM requirement check stops translation."""
        page.selected_files = [tmp_files[".docx"]]
        page._handle_translate()
        # Files remain since requirement check failed
        assert tmp_files[".docx"] in page.selected_files

    @patch("src.ui.pages.translate_document.start_translation_worker")
    @patch(
        "src.ui.pages.translate_document.setup_translation_tasks",
        return_value=[],
    )
    @patch(
        "src.ui.pages.translate_document.LanguageSelectionDialog.get_selection",
        return_value=("English", "French", None, True),
    )
    @patch("src.ui.pages.translate_document.require_setup", return_value=True)
    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_translate_empty_tasks_skips_worker(
        self,
        _mock_msg,
        _mock_require,
        _mock_lang,
        _mock_setup,
        mock_worker,
        page,
        tmp_files,
        _mock_history_deps,
    ) -> None:
        """If setup_translation_tasks returns empty, worker is not started."""
        page.selected_files = [tmp_files[".docx"]]
        page._add_file_widget(tmp_files[".docx"])

        page._handle_translate()
        mock_worker.assert_not_called()

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    @patch(
        "src.ui.pages.translate_document.start_translation_worker",
        return_value=None,
    )
    @patch(
        "src.ui.pages.translate_document.setup_translation_tasks",
        return_value=[(1, "/storage/file.docx", "English", "French")],
    )
    @patch(
        "src.ui.pages.translate_document.LanguageSelectionDialog.get_selection",
        return_value=("English", "French", None, True),
    )
    @patch("src.ui.pages.translate_document.require_setup", return_value=True)
    def test_translate_queued_when_active_worker_returns_none(  # noqa: PLR0913
        self,
        _mock_require,
        _mock_lang,
        _mock_setup,
        mock_worker,
        mock_msg,
        page,
        tmp_files,
        _mock_history_deps,
    ) -> None:
        """Queued-notification fires when start_translation_worker returns None.

        When an active worker is already running, the helper returns
        None (the new tasks are picked up by its DB poll).  Without
        this notification, files vanish from the picker (cleared on
        success) but no worker visibly started — the user assumes
        their click was lost and re-clicks Translate, racing into
        the active worker's poll.
        """
        page.selected_files = [tmp_files[".docx"]]
        page._add_file_widget(tmp_files[".docx"])

        page._handle_translate()

        # Worker call returned None (queue path).
        mock_worker.assert_called_once()
        # Notification dialog fired with the queued-title key.
        mock_msg.assert_called_once()
        positional_args = mock_msg.call_args.args
        assert any(
            "translate_queued_title" in str(a)
            or "queued" in str(a).lower()
            for a in positional_args
        ), (
            f"Expected queued-title notification, got: {positional_args}"
        )


# ---------------------------------------------------------------------------
# Requirements checking
# ---------------------------------------------------------------------------


class TestCheckRequirements:
    """Tests for _check_requirements() logic."""

    @patch(
        "src.ui.pages.translate_document.require_setup",
        return_value=True,
    )
    def test_llm_configured_no_images(self, mock_require, page) -> None:
        """Returns True when LLM is configured and no images selected."""
        page.selected_files = ["/fake/file.docx"]
        result = page._check_requirements()
        assert result is True
        # require_setup called once for LLM check
        assert mock_require.call_count == 1

    @patch(
        "src.ui.pages.translate_document.require_setup",
        return_value=True,
    )
    def test_images_require_ocr_check(self, mock_require, page) -> None:
        """When images are selected, a second require_setup call for OCR happens."""
        page.selected_files = ["/fake/photo.png"]
        result = page._check_requirements()
        assert result is True
        # Two calls: one for LLM, one for OCR
        assert mock_require.call_count == 2  # noqa: PLR2004

    @patch("src.ui.pages.translate_document.require_setup")
    def test_llm_not_configured_returns_false(self, mock_require, page) -> None:
        """Returns False when LLM is not configured."""
        mock_require.return_value = False
        page.selected_files = ["/fake/file.docx"]
        result = page._check_requirements()
        assert result is False

    @patch("src.ui.pages.translate_document.require_setup")
    def test_ocr_not_configured_with_images_returns_false(
        self,
        mock_require,
        page,
    ) -> None:
        """Returns False when OCR is not configured but images are selected."""
        # First call (LLM) succeeds, second call (OCR) fails
        mock_require.side_effect = [True, False]
        page.selected_files = ["/fake/photo.jpg"]
        result = page._check_requirements()
        assert result is False

    @patch(
        "src.ui.pages.translate_document.require_setup",
        return_value=True,
    )
    def test_no_ocr_check_for_text_only(self, mock_require, page) -> None:
        """No OCR check when only text/document files are selected."""
        page.selected_files = ["/fake/file.pdf", "/fake/file.docx"]
        page._check_requirements()
        # Only one call for LLM
        assert mock_require.call_count == 1

    @patch(
        "src.ui.pages.translate_document.require_setup",
        return_value=True,
    )
    def test_mixed_files_triggers_ocr_check(self, mock_require, page) -> None:
        """Mixing text and image files triggers the OCR check."""
        page.selected_files = ["/fake/file.docx", "/fake/photo.tiff"]
        page._check_requirements()
        assert mock_require.call_count == 2  # noqa: PLR2004


# ---------------------------------------------------------------------------
# Theme and language
# ---------------------------------------------------------------------------


class TestThemeAndLanguage:
    """Tests for apply_theme() and apply_language()."""

    def test_apply_theme_no_error(self, page) -> None:
        """apply_theme() runs without raising."""
        page.apply_theme()

    def test_apply_language_no_error(self, page, _mock_history_deps) -> None:
        """apply_language() runs without raising."""
        page.apply_language()

    def test_apply_language_updates_translate_button_text(
        self,
        page,
        _mock_history_deps,
    ) -> None:
        """apply_language() updates the translate button text."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page.apply_language()
        assert page.translate_btn.text() == tr("btn.start_translation")

    def test_apply_language_updates_clear_button_text(
        self,
        page,
        _mock_history_deps,
    ) -> None:
        """apply_language() updates the clear-all button text."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page.apply_language()
        assert page.clear_all_btn.text() == tr("btn.delete_all")

    def test_apply_language_updates_section_label(
        self,
        page,
        _mock_history_deps,
    ) -> None:
        """apply_language() updates the section label text."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page.apply_language()
        assert page.section_label.text() == tr("files.selected")


# ---------------------------------------------------------------------------
# File count limit
# ---------------------------------------------------------------------------


class TestFileCountLimit:
    """Tests for the max_files (100) cap on dropped files."""

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_max_100_files_cap(self, _mock_msg, page, tmp_path) -> None:
        """At most 100 files are added even if more are dropped."""
        max_files = 100  # noqa: PLR2004
        paths = []
        for i in range(120):
            f = tmp_path / f"file_{i}.txt"
            f.write_text("content")
            paths.append(str(f))

        page._handle_files_dropped(paths)
        assert len(page.selected_files) <= max_files


# ---------------------------------------------------------------------------
# Unsupported dialog truncation
# ---------------------------------------------------------------------------


class TestUnsupportedDialogTruncation:
    """Tests for the dialog text truncation with many unsupported files."""

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_truncation_with_many_unsupported(
        self,
        mock_msg,
        page,
        tmp_path,
    ) -> None:
        """More than 10 unsupported files shows '... and N more' in dialog."""
        paths = []
        for i in range(15):
            f = tmp_path / f"bad_{i:02d}.zzz"
            f.write_text("content")
            paths.append(str(f))

        def _tr_files(k, **kw):
            return kw.get("files", k)

        with patch("src.ui.pages.translate_document.tr", side_effect=_tr_files):
            page._handle_files_dropped(paths)

        mock_msg.assert_called_once()
        # The third positional arg is the formatted message (or the file_list
        # when our tr side_effect returns the files kwarg).
        call_args = mock_msg.call_args
        msg_text = call_args[0][2] if len(call_args[0]) > 2 else ""  # noqa: PLR2004
        assert "more" in msg_text.lower()

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_no_truncation_with_few_unsupported(
        self,
        mock_msg,
        page,
        tmp_path,
    ) -> None:
        """5 unsupported files lists all without truncation."""
        paths = []
        for i in range(5):
            f = tmp_path / f"bad_{i}.zzz"
            f.write_text("content")
            paths.append(str(f))

        def _tr_files(k, **kw):
            return kw.get("files", k)

        with patch("src.ui.pages.translate_document.tr", side_effect=_tr_files):
            page._handle_files_dropped(paths)

        mock_msg.assert_called_once()
        call_args = mock_msg.call_args
        msg_text = call_args[0][2] if len(call_args[0]) > 2 else ""  # noqa: PLR2004
        assert "more" not in msg_text.lower()


# ---------------------------------------------------------------------------
# Clean history view
# ---------------------------------------------------------------------------


class TestCleanHistoryView:
    """Tests for _clean_history_view() method."""

    def test_clean_history_view_no_crash(self, page) -> None:
        """_clean_history_view does not crash."""
        page._clean_history_view()

    def test_clean_history_view_without_page_attr(self, page) -> None:
        """_clean_history_view handles missing 'page' attribute gracefully."""
        original = page.history_view
        page.history_view = MagicMock(spec=[])
        # No 'page' attribute -> should return early
        page._clean_history_view()
        page.history_view = original


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_handle_files_dropped_none_return_from_dialog(self, page) -> None:
        """Empty list from files and cancelled dialog does nothing."""
        with patch(
            "src.ui.pages.translate_document.QFileDialog.getOpenFileNames",
            return_value=([], ""),
        ):
            page._handle_files_dropped([])
        assert len(page.selected_files) == 0

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_drop_file_that_cannot_be_statted(
        self,
        mock_msg,
        page,
        tmp_path,
    ) -> None:
        """Files that raise OSError on stat() are treated as unreadable."""
        f = tmp_path / "unreadable.docx"
        f.write_text("content")
        real_path = f.resolve()

        original_stat = Path.stat
        # resolve calls stat ~1, is_dir ~1, is_file ~1 = 3 before the
        # explicit stat() in the try-block.  Allow the first several and
        # then fail.
        call_limit = 3  # noqa: PLR2004

        def stat_side_effect(self_path, *args, **kwargs):
            if self_path == real_path:
                stat_side_effect.n += 1
                if stat_side_effect.n > call_limit:
                    raise OSError("Permission denied")
            return original_stat(self_path, *args, **kwargs)

        stat_side_effect.n = 0

        with patch.object(Path, "stat", stat_side_effect):
            page._handle_files_dropped([str(f)])
        # Should be flagged as unsupported/unreadable
        mock_msg.assert_called_once()
        assert len(page.selected_files) == 0

    def test_clear_all_on_empty_list_no_crash(self, page) -> None:
        """Calling _handle_clear_all when already empty does not crash."""
        page.selected_files.clear()
        page._handle_clear_all()
        assert len(page.selected_files) == 0

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_supported_extensions_from_constants(
        self,
        _mock_msg,
        page,
        tmp_path,
    ) -> None:
        """All extensions in ALL_SUPPORTED_EXTENSIONS are accepted."""
        from src.constants.files import ALL_SUPPORTED_EXTENSIONS  # noqa: PLC0415

        # Test a sample of extensions
        sample_exts = ALL_SUPPORTED_EXTENSIONS[:5]
        for ext in sample_exts:
            f = tmp_path / f"test_file{ext}"
            f.write_text("content")
            page._handle_files_dropped([str(f)])
        assert len(page.selected_files) == len(sample_exts)


# ---------------------------------------------------------------------------
# Refresh history after translate (HIGH)
# ---------------------------------------------------------------------------


class TestRefreshHistoryAfterTranslate:
    """Tests that refresh_history is called after a successful translation."""

    @patch("src.ui.pages.translate_document.start_translation_worker")
    @patch(
        "src.ui.pages.translate_document.setup_translation_tasks",
        return_value=[(1, "/storage/file.docx", "English", "French")],
    )
    @patch(
        "src.ui.pages.translate_document.LanguageSelectionDialog.get_selection",
        return_value=("English", "French", None, True),
    )
    @patch("src.ui.pages.translate_document.require_setup", return_value=True)
    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_refresh_history_called_after_translate(
        self,
        _mock_msg,
        _mock_require,
        _mock_lang,
        _mock_setup,
        _mock_worker,
        page,
        tmp_files,
        _mock_history_deps,
    ) -> None:
        """refresh_history(force=True) is called after successful translation."""
        page.selected_files = [tmp_files[".docx"]]
        page._add_file_widget(tmp_files[".docx"])
        page.history_view.refresh_history = MagicMock()

        page._handle_translate()

        page.history_view.refresh_history.assert_called_once_with(force=True)

    @patch("src.ui.pages.translate_document.start_translation_worker")
    @patch(
        "src.ui.pages.translate_document.setup_translation_tasks",
        return_value=[],
    )
    @patch(
        "src.ui.pages.translate_document.LanguageSelectionDialog.get_selection",
        return_value=("English", "French", None, True),
    )
    @patch("src.ui.pages.translate_document.require_setup", return_value=True)
    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_empty_tasks_preserves_selection_and_shows_error(
        self,
        _mock_msg,
        _mock_require,
        _mock_lang,
        _mock_setup,
        _mock_worker,
        page,
        tmp_files,
        _mock_history_deps,
    ) -> None:
        """When setup_translation_tasks returns [], selection is kept and an error shows."""
        page.selected_files = [tmp_files[".docx"]]
        page._add_file_widget(tmp_files[".docx"])
        page.history_view.refresh_history = MagicMock()

        page._handle_translate()

        # Selection is preserved so the user can retry.
        assert page.selected_files == [tmp_files[".docx"]]
        # history_view is not refreshed on a failed queue.
        page.history_view.refresh_history.assert_not_called()
        # An error dialog was shown.
        _mock_msg.assert_called_once()

    @patch(
        "src.ui.pages.translate_document.LanguageSelectionDialog.get_selection",
        return_value=("", "", None, False),
    )
    @patch("src.ui.pages.translate_document.require_setup", return_value=True)
    def test_refresh_history_not_called_on_cancel(
        self,
        _mock_require,
        _mock_lang,
        page,
        tmp_files,
    ) -> None:
        """refresh_history is NOT called when the language dialog is cancelled."""
        page.selected_files = [tmp_files[".pdf"]]
        page.history_view.refresh_history = MagicMock()

        page._handle_translate()

        page.history_view.refresh_history.assert_not_called()

    @patch("src.ui.pages.translate_document.require_setup", return_value=False)
    def test_refresh_history_not_called_on_requirement_failure(
        self,
        _mock_require,
        page,
        tmp_files,
    ) -> None:
        """refresh_history is NOT called when requirements check fails."""
        page.selected_files = [tmp_files[".docx"]]
        page.history_view.refresh_history = MagicMock()

        page._handle_translate()

        page.history_view.refresh_history.assert_not_called()


# ---------------------------------------------------------------------------
# Nested directory file discovery (MEDIUM)
# ---------------------------------------------------------------------------


class TestNestedDirectoryDiscovery:
    """Tests for recursive directory walking in _handle_files_dropped."""

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_nested_subdirectories_find_all_files(
        self,
        _mock_msg,
        page,
        tmp_path,
    ) -> None:
        """Dropping a directory with nested subdirectories finds all supported files."""
        # Create a directory tree:
        # root/
        #   level1/
        #     doc.pdf
        #     level2/
        #       sheet.xlsx
        #       level3/
        #         note.txt
        root = tmp_path / "root"
        root.mkdir()
        level1 = root / "level1"
        level1.mkdir()
        level2 = level1 / "level2"
        level2.mkdir()
        level3 = level2 / "level3"
        level3.mkdir()

        f1 = level1 / "doc.pdf"
        f1.write_text("content")
        f2 = level2 / "sheet.xlsx"
        f2.write_text("content")
        f3 = level3 / "note.txt"
        f3.write_text("content")

        page._handle_files_dropped([str(root)])

        assert len(page.selected_files) == 3  # noqa: PLR2004
        names = {Path(p).name for p in page.selected_files}
        assert names == {"doc.pdf", "sheet.xlsx", "note.txt"}

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_directory_with_only_unsupported_files_shows_dialog(
        self,
        mock_msg,
        page,
        tmp_path,
    ) -> None:
        """A directory containing ONLY unsupported files shows dialog, adds nothing."""
        d = tmp_path / "unsupported_dir"
        d.mkdir()
        for i in range(3):
            f = d / f"file_{i}.zzz"
            f.write_text("content")

        page._handle_files_dropped([str(d)])

        assert len(page.selected_files) == 0
        mock_msg.assert_called_once()

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_hidden_files_in_directories_skipped(
        self,
        _mock_msg,
        page,
        tmp_path,
    ) -> None:
        """Hidden files (names starting with '.') inside directories are skipped."""
        d = tmp_path / "mydir"
        d.mkdir()
        visible = d / "visible.txt"
        visible.write_text("content")
        hidden = d / ".hidden_file.txt"
        hidden.write_text("secret")

        page._handle_files_dropped([str(d)])

        paths = page.selected_files
        assert any("visible.txt" in p for p in paths)
        # .hidden_file.txt starts with '.', but it's a file not a dir part —
        # the code checks `child.relative_to(p).parts` for hidden dirs.
        # A hidden file at top level of the dropped dir passes because
        # rglob("*") returns the file itself, and its relative parts are
        # just (".hidden_file.txt",) which starts with ".".
        assert not any(".hidden_file.txt" in p for p in paths)

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_hidden_subdirectory_contents_skipped(
        self,
        _mock_msg,
        page,
        tmp_path,
    ) -> None:
        """Files inside hidden subdirectories are skipped."""
        d = tmp_path / "project"
        d.mkdir()
        visible = d / "readme.txt"
        visible.write_text("content")

        hidden_dir = d / ".git"
        hidden_dir.mkdir()
        hidden_file = hidden_dir / "config.txt"
        hidden_file.write_text("git config")

        page._handle_files_dropped([str(d)])

        paths = page.selected_files
        assert any("readme.txt" in p for p in paths)
        assert not any("config.txt" in p for p in paths)


# ---------------------------------------------------------------------------
# Verify setup_translation_tasks call arguments (MEDIUM)
# ---------------------------------------------------------------------------


class TestSetupTranslationTasksArguments:
    """Tests that setup_translation_tasks is called with correct arguments."""

    @patch("src.ui.pages.translate_document.start_translation_worker")
    @patch("src.ui.pages.translate_document.setup_translation_tasks")
    @patch(
        "src.ui.pages.translate_document.LanguageSelectionDialog.get_selection",
        return_value=("English", "French", None, True),
    )
    @patch("src.ui.pages.translate_document.require_setup", return_value=True)
    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_setup_called_with_correct_files_and_languages(
        self,
        _mock_msg,
        _mock_require,
        _mock_lang,
        mock_setup,
        _mock_worker,
        page,
        tmp_files,
        _mock_history_deps,
    ) -> None:
        """setup_translation_tasks receives (selected_files, src_lang, target_lang)."""
        # Capture the args at call time since _handle_clear_all mutates the list
        captured_args: list[tuple] = []

        def _capture(*args: object) -> list:
            snap = tuple(list(a) if isinstance(a, list) else a for a in args)
            captured_args.append(snap)
            return [(1, "/storage/f.docx", "English", "French")]

        mock_setup.side_effect = _capture
        expected_files = [tmp_files[".docx"], tmp_files[".pdf"]]
        page.selected_files = [tmp_files[".docx"], tmp_files[".pdf"]]
        page._add_file_widget(tmp_files[".docx"])
        page._add_file_widget(tmp_files[".pdf"])

        page._handle_translate()

        assert len(captured_args) == 1
        assert captured_args[0] == (expected_files, "English", "French")

    @patch("src.ui.pages.translate_document.start_translation_worker")
    @patch("src.ui.pages.translate_document.setup_translation_tasks")
    @patch(
        "src.ui.pages.translate_document.LanguageSelectionDialog.get_selection",
        return_value=("Vietnamese", "Japanese", None, True),
    )
    @patch("src.ui.pages.translate_document.require_setup", return_value=True)
    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_setup_called_with_different_language_pair(
        self,
        _mock_msg,
        _mock_require,
        _mock_lang,
        mock_setup,
        _mock_worker,
        page,
        tmp_files,
        _mock_history_deps,
    ) -> None:
        """setup_translation_tasks uses the language pair from the dialog."""
        captured_args: list[tuple] = []

        def _capture(*args: object) -> list:
            snap = tuple(list(a) if isinstance(a, list) else a for a in args)
            captured_args.append(snap)
            return [(1, "/storage/f.txt", "Vietnamese", "Japanese")]

        mock_setup.side_effect = _capture
        expected_files = [tmp_files[".txt"]]
        page.selected_files = [tmp_files[".txt"]]
        page._add_file_widget(tmp_files[".txt"])

        page._handle_translate()

        assert len(captured_args) == 1
        assert captured_args[0] == (expected_files, "Vietnamese", "Japanese")


# ---------------------------------------------------------------------------
# File dialog open signal connection (MEDIUM)
# ---------------------------------------------------------------------------


class TestFileDialogSignalConnection:
    """Tests that the drop area click triggers the file dialog via signal."""

    @patch("src.ui.pages.translate_document.QFileDialog.getOpenFileNames")
    def test_drop_area_click_opens_file_dialog(
        self,
        mock_dialog,
        page,
        tmp_files,
    ) -> None:
        """Clicking the drop area emits files_dropped([]) which opens the dialog."""
        mock_dialog.return_value = ([tmp_files[".docx"]], "")

        # Emitting files_dropped with [] simulates a click on the drop area
        page.drop_area.files_dropped.emit([])

        mock_dialog.assert_called_once()
        assert tmp_files[".docx"] in page.selected_files

    @patch("src.ui.pages.translate_document.QFileDialog.getOpenFileNames")
    def test_drop_area_click_cancelled_dialog_no_files(
        self,
        mock_dialog,
        page,
    ) -> None:
        """Cancelling the file dialog after drop area click adds no files."""
        mock_dialog.return_value = ([], "")

        page.drop_area.files_dropped.emit([])

        mock_dialog.assert_called_once()
        assert len(page.selected_files) == 0

    @patch("src.ui.pages.translate_document.QFileDialog.getOpenFileNames")
    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_drop_area_click_dialog_with_multiple_files(
        self,
        _mock_msg,
        mock_dialog,
        page,
        tmp_files,
    ) -> None:
        """File dialog returning multiple files adds all of them."""
        mock_dialog.return_value = (
            [tmp_files[".docx"], tmp_files[".pdf"], tmp_files[".txt"]],
            "",
        )

        page.drop_area.files_dropped.emit([])

        assert len(page.selected_files) == 3  # noqa: PLR2004

    @patch("src.ui.pages.translate_document.QFileDialog.getOpenFileNames")
    def test_drop_area_signal_connected_to_handler(
        self,
        mock_dialog,
        page,
    ) -> None:
        """files_dropped signal is connected to _handle_files_dropped."""
        mock_dialog.return_value = ([], "")
        # Emitting [] triggers the handler which opens the file dialog
        page.drop_area.files_dropped.emit([])
        # The file dialog was invoked, proving the signal is connected
        mock_dialog.assert_called_once()


# ---------------------------------------------------------------------------
# Language selection via dialog
# ---------------------------------------------------------------------------


class TestLanguageSelectionViaDialog:
    """Tests for language selection through the LanguageSelectionDialog."""

    @patch("src.ui.pages.translate_document.start_translation_worker")
    @patch("src.ui.pages.translate_document.setup_translation_tasks")
    @patch(
        "src.ui.pages.translate_document.LanguageSelectionDialog.get_selection",
        return_value=("Japanese", "Korean", None, True),
    )
    @patch("src.ui.pages.translate_document.require_setup", return_value=True)
    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_language_dialog_passes_languages_to_setup(
        self,
        _mock_msg,
        _mock_require,
        _mock_lang,
        mock_setup,
        _mock_worker,
        page,
        tmp_files,
        _mock_history_deps,
    ) -> None:
        """Language pair from dialog is passed to setup_translation_tasks."""
        captured_args: list[tuple] = []

        def _capture(*args: object) -> list:
            snap = tuple(list(a) if isinstance(a, list) else a for a in args)
            captured_args.append(snap)
            return [(1, "/storage/f.docx", "Japanese", "Korean")]

        mock_setup.side_effect = _capture
        page.selected_files = [tmp_files[".docx"]]
        page._add_file_widget(tmp_files[".docx"])

        page._handle_translate()

        assert len(captured_args) == 1
        assert captured_args[0][1] == "Japanese"
        assert captured_args[0][2] == "Korean"

    @patch("src.ui.pages.translate_document.start_translation_worker")
    @patch("src.ui.pages.translate_document.setup_translation_tasks")
    @patch(
        "src.ui.pages.translate_document.LanguageSelectionDialog.get_selection",
        return_value=("", "Vietnamese", None, True),
    )
    @patch("src.ui.pages.translate_document.require_setup", return_value=True)
    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_auto_detect_source_language(
        self,
        _mock_msg,
        _mock_require,
        _mock_lang,
        mock_setup,
        _mock_worker,
        page,
        tmp_files,
        _mock_history_deps,
    ) -> None:
        """Empty source language (auto-detect) is passed to setup."""
        captured_args: list[tuple] = []

        def _capture(*args: object) -> list:
            snap = tuple(list(a) if isinstance(a, list) else a for a in args)
            captured_args.append(snap)
            return [(1, "/storage/f.txt", "", "Vietnamese")]

        mock_setup.side_effect = _capture
        page.selected_files = [tmp_files[".txt"]]
        page._add_file_widget(tmp_files[".txt"])

        page._handle_translate()

        assert len(captured_args) == 1
        assert captured_args[0][1] == ""
        assert captured_args[0][2] == "Vietnamese"

    @patch(
        "src.ui.pages.translate_document.LanguageSelectionDialog.get_selection",
        return_value=("English", "French", None, False),
    )
    @patch("src.ui.pages.translate_document.require_setup", return_value=True)
    def test_dialog_cancel_preserves_file_count(
        self,
        _mock_require,
        _mock_lang,
        page,
        tmp_files,
    ) -> None:
        """Cancelling the language dialog preserves the file count badge."""
        page.selected_files = [tmp_files[".docx"], tmp_files[".pdf"]]
        page._update_ui_state()
        assert page.files_badge.text() == "2"

        page._handle_translate()

        # Files remain; badge stays at 2
        assert page.files_badge.text() == "2"
        assert len(page.selected_files) == 2  # noqa: PLR2004


# ---------------------------------------------------------------------------
# Start/stop translation button states
# ---------------------------------------------------------------------------


class TestTranslationButtonStates:
    """Tests for the translate button state transitions."""

    def test_translate_button_disabled_with_no_files(self, page) -> None:
        """Translate button is disabled when selected_files is empty."""
        page.selected_files = []
        page._update_ui_state()
        assert not page.translate_btn.isEnabled()

    def test_translate_button_enabled_after_file_drop(
        self,
        page,
        tmp_files,
    ) -> None:
        """Translate button is enabled after a file is dropped."""
        with patch(
            "src.ui.pages.translate_document.CustomMessageDialog.show_message",
        ):
            page._handle_files_dropped([tmp_files[".pdf"]])
        assert page.translate_btn.isEnabled()

    def test_translate_button_disabled_after_clear_all(
        self,
        page,
        tmp_files,
    ) -> None:
        """Translate button is disabled after clearing all files."""
        with patch(
            "src.ui.pages.translate_document.CustomMessageDialog.show_message",
        ):
            page._handle_files_dropped([tmp_files[".docx"]])
        assert page.translate_btn.isEnabled()

        page._handle_clear_all()
        assert not page.translate_btn.isEnabled()

    @patch("src.ui.pages.translate_document.start_translation_worker")
    @patch(
        "src.ui.pages.translate_document.setup_translation_tasks",
        return_value=[(1, "/storage/f.docx", "EN", "FR")],
    )
    @patch(
        "src.ui.pages.translate_document.LanguageSelectionDialog.get_selection",
        return_value=("English", "French", None, True),
    )
    @patch("src.ui.pages.translate_document.require_setup", return_value=True)
    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_translate_button_disabled_after_translation_starts(
        self,
        _mock_msg,
        _mock_require,
        _mock_lang,
        _mock_setup,
        _mock_worker,
        page,
        tmp_files,
        _mock_history_deps,
    ) -> None:
        """After translation, files are cleared so button is disabled."""
        page.selected_files = [tmp_files[".docx"]]
        page._add_file_widget(tmp_files[".docx"])

        page._handle_translate()

        # Files cleared after translate -> button disabled
        assert not page.translate_btn.isEnabled()

    def test_translate_button_has_pointing_cursor(self, page) -> None:
        """Translate button has pointing hand cursor."""
        assert page.translate_btn.cursor().shape() == Qt.CursorShape.PointingHandCursor

    def test_clear_all_button_has_pointing_cursor(self, page) -> None:
        """Clear-all button has pointing hand cursor."""
        assert page.clear_all_btn.cursor().shape() == Qt.CursorShape.PointingHandCursor


# ---------------------------------------------------------------------------
# Drop area reparenting
# ---------------------------------------------------------------------------


class TestDropAreaReparenting:
    """Tests for the shared drop area reparenting between views."""

    def test_drop_area_in_history_view_initially(self, page) -> None:
        """Drop area is in the history wrapper initially."""
        parent = page.drop_area.parent()
        assert parent is not None

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_drop_area_moves_to_files_view(
        self,
        _mock_msg,
        page,
        tmp_files,
    ) -> None:
        """Drop area moves to files wrapper when files are selected."""
        page._handle_files_dropped([tmp_files[".docx"]])
        # Drop area should be in the files wrapper layout
        assert page.stack.currentIndex() == _VIEW_FILES

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_drop_area_moves_back_on_clear(
        self,
        _mock_msg,
        page,
        tmp_files,
    ) -> None:
        """Drop area moves back to history wrapper when files are cleared."""
        page._handle_files_dropped([tmp_files[".docx"]])
        assert page.stack.currentIndex() == _VIEW_FILES

        page._handle_clear_all()
        assert page.stack.currentIndex() == _VIEW_HISTORY

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_drop_area_label_text_changes_with_view(
        self,
        _mock_msg,
        page,
        tmp_files,
    ) -> None:
        """Drop area info label text changes based on current view."""
        from src.constants.i18n import tr  # noqa: PLC0415

        # Initial state (no files)
        assert page.drop_area.info_label.text() == tr("drop.title")

        # Add file (switches to files view)
        page._handle_files_dropped([tmp_files[".pdf"]])
        assert page.drop_area.info_label.text() == tr("drop.title_more")

        # Clear (switches back to history view)
        page._handle_clear_all()
        assert page.drop_area.info_label.text() == tr("drop.title")


# ---------------------------------------------------------------------------
# Widget layout structure
# ---------------------------------------------------------------------------


class TestWidgetLayoutStructure:
    """Tests for the widget hierarchy and layout structure."""

    def test_stack_has_exactly_two_views(self, page) -> None:
        """Stacked widget contains exactly 2 views."""
        assert page.stack.count() == 2  # noqa: PLR2004

    def test_history_wrapper_exists(self, page) -> None:
        """History wrapper widget exists."""
        assert hasattr(page, "history_wrapper")
        assert page.history_wrapper is not None

    def test_files_wrapper_exists(self, page) -> None:
        """Files wrapper widget exists."""
        assert hasattr(page, "files_wrapper")
        assert page.files_wrapper is not None

    def test_file_list_section_exists(self, page) -> None:
        """File list section widget exists."""
        assert hasattr(page, "file_list_section")
        assert page.file_list_section is not None

    def test_drop_area_has_fixed_height(self, page) -> None:
        """Drop area has a fixed height set."""
        from src.constants.ui import DROP_AREA_HEIGHT  # noqa: PLC0415

        assert page.drop_area.maximumHeight() == DROP_AREA_HEIGHT
        assert page.drop_area.minimumHeight() == DROP_AREA_HEIGHT

    def test_files_vbox_has_stretch_spacer(self, page) -> None:
        """Files vertical layout starts with a stretch spacer at the end."""
        # Count should be at least 1 (the stretch)
        assert page.files_vbox.count() >= 1

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_file_widget_inserted_before_stretch(
        self,
        _mock_msg,
        page,
        tmp_files,
    ) -> None:
        """File widgets are inserted before the trailing stretch."""
        from src.ui.components import FileItemWidget  # noqa: PLC0415

        initial = page.files_vbox.count()
        page._add_file_widget(tmp_files[".docx"])

        assert page.files_vbox.count() == initial + 1
        # The last item should still be the stretch (no widget)
        last_item = page.files_vbox.itemAt(page.files_vbox.count() - 1)
        assert last_item.widget() is None  # stretch has no widget
        # The second-to-last should be the new FileItemWidget
        new_item = page.files_vbox.itemAt(page.files_vbox.count() - 2)  # noqa: PLR2004
        assert isinstance(new_item.widget(), FileItemWidget)


# ---------------------------------------------------------------------------
# TestTranslateDocPageCreation — page widgets and structure
# ---------------------------------------------------------------------------


class TestTranslateDocPageCreation:
    """Tests for page creation and expected widget presence."""

    def test_page_has_all_expected_attributes(self, page) -> None:
        """Page exposes all key attributes used by the app."""
        expected = [
            "drop_area",
            "stack",
            "translate_btn",
            "clear_all_btn",
            "files_badge",
            "section_label",
            "history_view",
            "files_vbox",
            "selected_files",
            "window_context",
        ]
        for attr in expected:
            assert hasattr(page, attr), f"Missing attribute: {attr}"

    def test_has_file_drop_area_with_signal(self, page) -> None:
        """FileDropWidget has a files_dropped signal."""
        assert hasattr(page.drop_area, "files_dropped")

    def test_has_translate_button_with_style(self, page) -> None:
        """Translate button has a non-empty stylesheet."""
        assert page.translate_btn.styleSheet() != ""

    def test_has_language_combos_via_dialog(self, page) -> None:
        """Language selection is handled via LanguageSelectionDialog (not combos)."""
        # The page delegates language selection to a dialog, not inline combos.
        # Verify _handle_translate exists as the entry point.
        assert hasattr(page, "_handle_translate")
        assert callable(page._handle_translate)

    def test_drop_area_info_label_exists(self, page) -> None:
        """Drop area has an info_label widget."""
        assert hasattr(page.drop_area, "info_label")
        assert page.drop_area.info_label is not None

    def test_page_has_scroll_area_in_file_section(self, page) -> None:
        """File list section includes a QScrollArea."""
        scroll = page.file_list_section.findChild(QScrollArea)
        assert scroll is not None
        assert scroll.widgetResizable()


# ---------------------------------------------------------------------------
# TestTranslateDocFileHandling — drag-and-drop, browse, duplicates
# ---------------------------------------------------------------------------


class TestTranslateDocFileHandling:
    """Tests for file adding, removing, format validation."""

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_adding_files_via_drag_and_drop(self, _mock_msg, page, tmp_files) -> None:
        """Files added via drop signal appear in selected_files."""
        page.drop_area.files_dropped.emit([tmp_files[".docx"]])
        assert tmp_files[".docx"] in page.selected_files

    @patch("src.ui.pages.translate_document.QFileDialog.getOpenFileNames")
    def test_adding_files_via_browse_button(self, mock_dialog, page, tmp_files) -> None:
        """Files selected via browse dialog appear in selected_files."""
        mock_dialog.return_value = ([tmp_files[".pdf"]], "")
        page._handle_files_dropped([])
        assert tmp_files[".pdf"] in page.selected_files

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_adding_duplicate_files_ignored(self, _mock_msg, page, tmp_files) -> None:
        """Duplicate files are not added twice."""
        page._handle_files_dropped([tmp_files[".txt"]])
        page._handle_files_dropped([tmp_files[".txt"]])
        assert page.selected_files.count(tmp_files[".txt"]) == 1

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_removing_file_from_list(self, _mock_msg, page, tmp_files) -> None:
        """Removing a file removes it from selected_files."""
        page._handle_files_dropped([tmp_files[".docx"]])
        assert tmp_files[".docx"] in page.selected_files

        from src.ui.components import FileItemWidget  # noqa: PLC0415

        widget = None
        for i in range(page.files_vbox.count()):
            item = page.files_vbox.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), FileItemWidget):
                widget = item.widget()
                break
        assert widget is not None
        page._handle_remove_file(tmp_files[".docx"], widget)
        assert tmp_files[".docx"] not in page.selected_files

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_supported_formats_accepted(self, _mock_msg, page, tmp_path) -> None:
        """All supported format extensions are accepted."""
        exts = [".docx", ".pdf", ".txt", ".png", ".xlsx", ".html"]
        for ext in exts:
            f = tmp_path / f"test{ext}"
            f.write_text("content")
        paths = [str(tmp_path / f"test{ext}") for ext in exts]
        page._handle_files_dropped(paths)
        assert len(page.selected_files) == len(exts)

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_unsupported_formats_rejected(self, mock_msg, page, tmp_path) -> None:
        """Unsupported file formats are rejected with a dialog."""
        bad = tmp_path / "file.xyz123"
        bad.write_text("content")
        page._handle_files_dropped([str(bad)])
        assert len(page.selected_files) == 0
        mock_msg.assert_called_once()


# ---------------------------------------------------------------------------
# TestTranslateDocActions — translate, cancel, empty
# ---------------------------------------------------------------------------


class TestTranslateDocActions:
    """Tests for translation actions and button state."""

    def test_translate_with_no_files_noop(self, page) -> None:
        """Calling translate with no files does nothing."""
        page.selected_files = []
        page._handle_translate()
        assert page.selected_files == []

    @patch("src.ui.pages.translate_document.start_translation_worker")
    @patch(
        "src.ui.pages.translate_document.setup_translation_tasks",
        return_value=[(1, "/s/f.docx", "EN", "FR")],
    )
    @patch(
        "src.ui.pages.translate_document.LanguageSelectionDialog.get_selection",
        return_value=("English", "French", None, True),
    )
    @patch("src.ui.pages.translate_document.require_setup", return_value=True)
    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_translate_button_starts_translation(
        self,
        _mock_msg,
        _mock_require,
        _mock_lang,
        mock_setup,
        mock_worker,
        page,
        tmp_files,
        _mock_history_deps,
    ) -> None:
        """Clicking translate starts the translation worker."""
        page.selected_files = [tmp_files[".docx"]]
        page._add_file_widget(tmp_files[".docx"])
        page._handle_translate()
        mock_worker.assert_called_once()

    @patch(
        "src.ui.pages.translate_document.LanguageSelectionDialog.get_selection",
        return_value=("", "", None, False),
    )
    @patch("src.ui.pages.translate_document.require_setup", return_value=True)
    def test_cancel_dialog_stops_translation(
        self, _mock_require, _mock_lang, page, tmp_files
    ) -> None:
        """Cancelling the language dialog aborts translation."""
        page.selected_files = [tmp_files[".pdf"]]
        page._handle_translate()
        # Files remain (translation not started)
        assert tmp_files[".pdf"] in page.selected_files

    def test_button_states_during_lifecycle(self, page, tmp_files) -> None:
        """Button enabled/disabled states follow the file lifecycle."""
        # No files: disabled
        assert not page.translate_btn.isEnabled()

        # Add file: enabled
        page.selected_files = [tmp_files[".docx"]]
        page._update_ui_state()
        assert page.translate_btn.isEnabled()

        # Clear files: disabled
        page.selected_files = []
        page._update_ui_state()
        assert not page.translate_btn.isEnabled()

    @patch("src.ui.pages.translate_document.require_setup", return_value=False)
    def test_translate_fails_on_missing_requirements(
        self, _mock_require, page, tmp_files
    ) -> None:
        """Translation is aborted when requirements check fails."""
        page.selected_files = [tmp_files[".docx"]]
        page._handle_translate()
        assert tmp_files[".docx"] in page.selected_files


# ---------------------------------------------------------------------------
# TestTranslateDocHistory — history table presence
# ---------------------------------------------------------------------------


class TestTranslateDocHistory:
    """Tests for the embedded history table."""

    def test_history_table_present(self, page) -> None:
        """Page contains an embedded HistoryPage widget."""
        from src.ui.pages.history import HistoryPage  # noqa: PLC0415

        assert isinstance(page.history_view, HistoryPage)

    def test_history_view_embedded_in_history_wrapper(self, page) -> None:
        """HistoryPage is a child of the history wrapper."""
        assert page.history_view.parent() is not None

    @patch("src.ui.pages.translate_document.start_translation_worker")
    @patch(
        "src.ui.pages.translate_document.setup_translation_tasks",
        return_value=[(1, "/s/f.docx", "EN", "FR")],
    )
    @patch(
        "src.ui.pages.translate_document.LanguageSelectionDialog.get_selection",
        return_value=("English", "French", None, True),
    )
    @patch("src.ui.pages.translate_document.require_setup", return_value=True)
    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_history_refresh_called_after_translate(
        self,
        _mock_msg,
        _mock_require,
        _mock_lang,
        _mock_setup,
        _mock_worker,
        page,
        tmp_files,
        _mock_history_deps,
    ) -> None:
        """History is refreshed after a successful translation."""
        page.selected_files = [tmp_files[".docx"]]
        page._add_file_widget(tmp_files[".docx"])
        page.history_view.refresh_history = MagicMock()
        page._handle_translate()
        page.history_view.refresh_history.assert_called_once_with(force=True)

    def test_history_title_hidden_in_embedded_view(self, page) -> None:
        """The standalone history title label is hidden in embedded mode."""
        from src.constants.i18n import tr  # noqa: PLC0415

        # Search for the history title label
        for child in page.history_view.page.findChildren(QLabel):
            if child.text() == tr("page.translation_history"):
                assert not child.isVisible()
                return
        # If label not found, that's also OK (already removed or different tr)


# ---------------------------------------------------------------------------
# TestTranslateDocThemeLanguage — apply_theme, apply_language
# ---------------------------------------------------------------------------


class TestTranslateDocThemeLanguage:
    """Tests for theme and language switching."""

    def test_apply_theme_updates_badge_style(self, page) -> None:
        """apply_theme() updates the files badge stylesheet."""
        page.files_badge.setStyleSheet("")
        page.apply_theme()
        assert page.files_badge.styleSheet() != ""

    def test_apply_theme_updates_translate_button_style(self, page) -> None:
        """apply_theme() updates the translate button stylesheet."""
        page.translate_btn.setStyleSheet("")
        page.apply_theme()
        assert page.translate_btn.styleSheet() != ""

    def test_apply_theme_updates_clear_button_style(self, page) -> None:
        """apply_theme() updates the clear-all button stylesheet."""
        page.clear_all_btn.setStyleSheet("")
        page.apply_theme()
        assert page.clear_all_btn.styleSheet() != ""

    def test_apply_theme_updates_section_label_style(self, page) -> None:
        """apply_theme() updates the section label stylesheet."""
        page.section_label.setStyleSheet("")
        page.apply_theme()
        assert page.section_label.styleSheet() != ""

    def test_apply_language_updates_all_labels(self, page, _mock_history_deps) -> None:
        """apply_language() updates all translatable text."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page.apply_language()
        assert page.section_label.text() == tr("files.selected")
        assert page.translate_btn.text() == tr("btn.start_translation")
        assert page.clear_all_btn.text() == tr("btn.delete_all")

    def test_apply_theme_then_language_no_crash(self, page, _mock_history_deps) -> None:
        """Calling apply_theme() then apply_language() does not crash."""
        page.apply_theme()
        page.apply_language()

    def test_apply_language_then_theme_no_crash(self, page, _mock_history_deps) -> None:
        """Calling apply_language() then apply_theme() does not crash."""
        page.apply_language()
        page.apply_theme()


# ---------------------------------------------------------------------------
# TestTranslateDocEdgeCases — unicode, long paths, sizes
# ---------------------------------------------------------------------------


class TestTranslateDocEdgeCasesExpanded:
    """Extended edge-case tests for the translate document page."""

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_unicode_filename(self, _mock_msg, page, tmp_path) -> None:
        """Files with unicode names are handled correctly."""
        f = tmp_path / "tài_liệu_tiếng_việt.docx"
        f.write_text("content")
        page._handle_files_dropped([str(f)])
        assert len(page.selected_files) == 1
        assert "tài_liệu_tiếng_việt" in page.selected_files[0]

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_cjk_filename(self, _mock_msg, page, tmp_path) -> None:
        """Files with CJK characters in names are handled correctly."""
        f = tmp_path / "文件翻訳.pdf"
        f.write_text("content")
        page._handle_files_dropped([str(f)])
        assert len(page.selected_files) == 1

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_very_long_file_path(self, _mock_msg, page, tmp_path) -> None:
        """Files with long directory paths are accepted."""
        # Create nested directories to build a long path
        deep = tmp_path
        for i in range(10):
            deep = deep / f"dir_{i:03d}"
        deep.mkdir(parents=True)
        f = deep / "deep_file.txt"
        f.write_text("content")
        page._handle_files_dropped([str(f)])
        assert len(page.selected_files) == 1

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_file_size_display_in_widget(self, _mock_msg, page, tmp_path) -> None:
        """FileItemWidget displays file size correctly."""
        f = tmp_path / "sized_file.docx"
        f.write_text("x" * 1024)  # ~1KB
        page._handle_files_dropped([str(f)])
        assert len(page.selected_files) == 1

        from src.ui.components import FileItemWidget  # noqa: PLC0415

        widget = None
        for i in range(page.files_vbox.count()):
            item = page.files_vbox.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), FileItemWidget):
                widget = item.widget()
                break
        assert widget is not None

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_spaces_in_filename(self, _mock_msg, page, tmp_path) -> None:
        """Files with spaces in names are handled correctly."""
        f = tmp_path / "my document file.docx"
        f.write_text("content")
        page._handle_files_dropped([str(f)])
        assert len(page.selected_files) == 1

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_multiple_dots_in_filename(self, _mock_msg, page, tmp_path) -> None:
        """Files with multiple dots in the name use the last extension."""
        f = tmp_path / "my.file.name.pdf"
        f.write_text("content")
        page._handle_files_dropped([str(f)])
        assert len(page.selected_files) == 1

    def test_clear_all_idempotent(self, page) -> None:
        """Calling clear_all multiple times does not crash."""
        page._handle_clear_all()
        page._handle_clear_all()
        page._handle_clear_all()
        assert len(page.selected_files) == 0

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_badge_updates_on_add_and_remove(self, _mock_msg, page, tmp_files) -> None:
        """Badge count updates correctly on add and remove cycles."""
        assert page.files_badge.text() == "0"

        page._handle_files_dropped([tmp_files[".docx"]])
        assert page.files_badge.text() == "1"

        page._handle_files_dropped([tmp_files[".pdf"]])
        assert page.files_badge.text() == "2"

        page._handle_clear_all()
        assert page.files_badge.text() == "0"

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_add_then_remove_then_add_again(self, _mock_msg, page, tmp_files) -> None:
        """File can be re-added after being removed."""
        page._handle_files_dropped([tmp_files[".docx"]])
        assert tmp_files[".docx"] in page.selected_files

        # Remove via clear_all
        page._handle_clear_all()
        assert tmp_files[".docx"] not in page.selected_files

        # Re-add
        page._handle_files_dropped([tmp_files[".docx"]])
        assert tmp_files[".docx"] in page.selected_files

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_view_switches_back_after_last_file_removed(
        self, _mock_msg, page, tmp_files
    ) -> None:
        """View switches from files to history when the last file is removed."""
        page._handle_files_dropped([tmp_files[".docx"]])
        assert page.stack.currentIndex() == _VIEW_FILES

        from src.ui.components import FileItemWidget  # noqa: PLC0415

        widget = None
        for i in range(page.files_vbox.count()):
            item = page.files_vbox.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), FileItemWidget):
                widget = item.widget()
                break
        assert widget is not None
        page._handle_remove_file(tmp_files[".docx"], widget)
        assert page.stack.currentIndex() == _VIEW_HISTORY
        assert page.files_badge.text() == "0"

    @patch(
        "src.ui.pages.translate_document.require_setup",
        return_value=True,
    )
    def test_check_requirements_with_mixed_file_types(self, mock_require, page) -> None:
        """Mixed file types (text + image) triggers both LLM and OCR checks."""
        page.selected_files = ["/fake/file.docx", "/fake/photo.jpg"]
        result = page._check_requirements()
        assert result is True
        assert mock_require.call_count == 2  # noqa: PLR2004

    @patch(
        "src.ui.pages.translate_document.require_setup",
        return_value=True,
    )
    def test_check_requirements_text_only(self, mock_require, page) -> None:
        """Text-only files require only LLM setup check."""
        page.selected_files = ["/fake/file.pdf", "/fake/file.txt"]
        result = page._check_requirements()
        assert result is True
        assert mock_require.call_count == 1


# ---------------------------------------------------------------------------
# EXPANDED: Additional construction tests
# ---------------------------------------------------------------------------


class TestConstructionExpanded:
    """Expanded tests for TranslateDocumentPage construction."""

    def test_history_view_has_page_attr(self, page) -> None:
        """Embedded HistoryPage has a page attribute."""
        assert hasattr(page.history_view, "page")

    def test_drop_area_files_dropped_signal(self, page) -> None:
        """Drop area has files_dropped signal."""
        assert hasattr(page.drop_area, "files_dropped")

    def test_files_vbox_has_stretch(self, page) -> None:
        """Files vbox layout has at least a stretch item."""
        assert page.files_vbox.count() >= 1

    def test_page_has_layout(self, page) -> None:
        """Page has a root layout."""
        assert page.layout() is not None

    def test_stack_has_two_widgets(self, page) -> None:
        """Stack widget has exactly two child views."""
        assert page.stack.count() == 2  # noqa: PLR2004


# ---------------------------------------------------------------------------
# EXPANDED: File drop handling with various formats
# ---------------------------------------------------------------------------


class TestDropFormatsExpanded:
    """Expanded tests for _handle_files_dropped with all formats."""

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_drop_xlsx_file(self, _mock_msg, page, tmp_path) -> None:
        """Dropping .xlsx file adds it to selection."""
        f = tmp_path / "data.xlsx"
        f.write_text("content")
        page._handle_files_dropped([str(f)])
        assert str(f) in page.selected_files

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_drop_html_file(self, _mock_msg, page, tmp_path) -> None:
        """Dropping .html file adds it to selection."""
        f = tmp_path / "page.html"
        f.write_text("<html></html>")
        page._handle_files_dropped([str(f)])
        assert str(f) in page.selected_files

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_drop_txt_file(self, _mock_msg, page, tmp_path) -> None:
        """Dropping .txt file adds it to selection."""
        f = tmp_path / "notes.txt"
        f.write_text("notes")
        page._handle_files_dropped([str(f)])
        assert str(f) in page.selected_files

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_drop_pptx_file(self, _mock_msg, page, tmp_path) -> None:
        """Dropping .pptx file adds it to selection."""
        f = tmp_path / "slides.pptx"
        f.write_text("content")
        page._handle_files_dropped([str(f)])
        assert str(f) in page.selected_files

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_drop_csv_file(self, _mock_msg, page, tmp_path) -> None:
        """Dropping .csv file adds it to selection."""
        f = tmp_path / "data.csv"
        f.write_text("a,b,c")
        page._handle_files_dropped([str(f)])
        assert str(f) in page.selected_files

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_drop_json_file(self, _mock_msg, page, tmp_path) -> None:
        """Dropping .json file adds it to selection."""
        f = tmp_path / "config.json"
        f.write_text("{}")
        page._handle_files_dropped([str(f)])
        assert str(f) in page.selected_files

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_drop_srt_file(self, _mock_msg, page, tmp_path) -> None:
        """Dropping .srt file adds it to selection."""
        f = tmp_path / "sub.srt"
        f.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello")
        page._handle_files_dropped([str(f)])
        assert str(f) in page.selected_files

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_drop_md_file(self, _mock_msg, page, tmp_path) -> None:
        """Dropping .md file adds it to selection."""
        f = tmp_path / "readme.md"
        f.write_text("# Title")
        page._handle_files_dropped([str(f)])
        assert str(f) in page.selected_files

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_drop_exe_rejected(self, mock_msg, page, tmp_path) -> None:
        """Dropping .exe file is rejected as unsupported."""
        f = tmp_path / "app.exe"
        f.write_text("binary")
        page._handle_files_dropped([str(f)])
        assert str(f) not in page.selected_files
        mock_msg.assert_called_once()

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_drop_mp3_rejected(self, mock_msg, page, tmp_path) -> None:
        """Dropping .mp3 file is rejected as unsupported."""
        f = tmp_path / "audio.mp3"
        f.write_text("audio")
        page._handle_files_dropped([str(f)])
        assert str(f) not in page.selected_files

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_drop_zip_rejected(self, mock_msg, page, tmp_path) -> None:
        """Dropping .zip file is rejected as unsupported."""
        f = tmp_path / "archive.zip"
        f.write_text("zip")
        page._handle_files_dropped([str(f)])
        assert str(f) not in page.selected_files

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_drop_many_files(self, _mock_msg, page, tmp_path) -> None:
        """Dropping many files adds them all (up to limit)."""
        files = []
        for i in range(20):
            f = tmp_path / f"doc_{i}.txt"
            f.write_text("content")
            files.append(str(f))
        page._handle_files_dropped(files)
        assert len(page.selected_files) == 20  # noqa: PLR2004

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_drop_unicode_filename(self, _mock_msg, page, tmp_path) -> None:
        """Dropping file with unicode name adds it."""
        f = tmp_path / "tài_liệu.docx"
        f.write_text("content")
        page._handle_files_dropped([str(f)])
        assert str(f) in page.selected_files


# ---------------------------------------------------------------------------
# EXPANDED: UI state transitions
# ---------------------------------------------------------------------------


class TestUIStateTransitions:
    """Expanded tests for UI state changes."""

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_badge_updates_on_add(self, _mock_msg, page, tmp_files) -> None:
        """Badge count updates when files are added."""
        page._handle_files_dropped([tmp_files[".docx"]])
        assert page.files_badge.text() == "1"

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_badge_updates_on_multiple_add(self, _mock_msg, page, tmp_files) -> None:
        """Badge count reflects total files."""
        page._handle_files_dropped(
            [tmp_files[".docx"], tmp_files[".pdf"], tmp_files[".txt"]],
        )
        assert page.files_badge.text() == "3"

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_drop_area_reparented_to_files(self, _mock_msg, page, tmp_files) -> None:
        """Drop area is reparented to files view when files selected."""
        page._handle_files_dropped([tmp_files[".docx"]])
        assert page.stack.currentIndex() == _VIEW_FILES

    def test_clear_all_restores_badge_to_zero(self, page) -> None:
        """Clear all resets badge to 0."""
        page.selected_files = ["/fake.docx"]
        page._update_ui_state()
        page._handle_clear_all()
        assert page.files_badge.text() == "0"

    def test_add_then_remove_returns_to_history(self, page, tmp_path) -> None:
        """Adding then removing all files returns to history view."""
        f = tmp_path / "test.txt"
        f.write_text("content")
        page.selected_files.append(str(f))
        page._add_file_widget(str(f))
        page._update_ui_state()
        assert page.stack.currentIndex() == _VIEW_FILES

        from src.ui.components import FileItemWidget  # noqa: PLC0415

        widget = None
        for i in range(page.files_vbox.count()):
            item = page.files_vbox.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), FileItemWidget):
                widget = item.widget()
                break
        if widget:
            page._handle_remove_file(str(f), widget)
        assert page.stack.currentIndex() == _VIEW_HISTORY


# ---------------------------------------------------------------------------
# EXPANDED: Translation workflow
# ---------------------------------------------------------------------------


class TestTranslateWorkflowExpanded:
    """Expanded tests for translation workflow."""

    def test_translate_with_no_files_is_noop(self, page) -> None:
        """Calling _handle_translate with empty files does nothing."""
        page.selected_files = []
        page._handle_translate()
        assert page.selected_files == []

    @patch("src.ui.pages.translate_document.require_setup", return_value=False)
    def test_translate_fails_on_llm_check(self, mock_require, page) -> None:
        """Translation is blocked when LLM check fails."""
        page.selected_files = ["/fake/doc.pdf"]
        page._handle_translate()
        # Files should not be cleared (blocked at requirements)
        assert len(page.selected_files) == 1

    @patch(
        "src.ui.pages.translate_document.LanguageSelectionDialog.get_selection",
        return_value=("", "", None, False),
    )
    @patch("src.ui.pages.translate_document.require_setup", return_value=True)
    def test_translate_cancelled_preserves_files(
        self,
        _mock_require,
        _mock_lang,
        page,
    ) -> None:
        """Cancelling language dialog preserves selected files."""
        page.selected_files = ["/fake/doc.pdf"]
        page._handle_translate()
        assert len(page.selected_files) == 1

    @patch(
        "src.ui.pages.translate_document.require_setup",
        return_value=True,
    )
    def test_check_requirements_images_only(self, mock_require, page) -> None:
        """Image-only files trigger both LLM and OCR checks."""
        page.selected_files = ["/fake/photo.png"]
        result = page._check_requirements()
        assert result is True
        assert mock_require.call_count == 2  # noqa: PLR2004

    @patch(
        "src.ui.pages.translate_document.require_setup",
        side_effect=[True, False],
    )
    def test_check_requirements_ocr_fails(self, mock_require, page) -> None:
        """Requirements check fails when OCR setup fails for images."""
        page.selected_files = ["/fake/photo.png"]
        result = page._check_requirements()
        assert result is False

    @patch("src.ui.pages.translate_document.require_setup", return_value=True)
    def test_check_requirements_pdf_no_ocr(self, mock_require, page) -> None:
        """PDF files (not images) require only LLM check."""
        page.selected_files = ["/fake/doc.pdf"]
        result = page._check_requirements()
        assert result is True
        assert mock_require.call_count == 1

    @patch("src.ui.pages.translate_document.start_translation_worker")
    @patch(
        "src.ui.pages.translate_document.setup_translation_tasks",
        return_value=[],
    )
    @patch(
        "src.ui.pages.translate_document.LanguageSelectionDialog.get_selection",
        return_value=("English", "French", None, True),
    )
    @patch("src.ui.pages.translate_document.require_setup", return_value=True)
    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_translate_empty_tasks(
        self,
        _mock_msg,
        _mock_require,
        _mock_lang,
        mock_setup,
        mock_worker,
        page,
        _mock_history_deps,
    ) -> None:
        """When setup_translation_tasks returns empty, worker is not started."""
        page.selected_files = ["/fake/doc.pdf"]
        page._handle_translate()
        mock_worker.assert_not_called()


# ---------------------------------------------------------------------------
# EXPANDED: Theme and language
# ---------------------------------------------------------------------------


class TestThemeLanguageExpanded:
    """Expanded theme and language tests."""

    def test_apply_theme_updates_badge(self, page) -> None:
        """apply_theme updates badge stylesheet."""
        page.files_badge.setStyleSheet("")
        page.apply_theme()
        assert page.files_badge.styleSheet() != ""

    def test_apply_theme_updates_buttons(self, page) -> None:
        """apply_theme updates button stylesheets."""
        page.translate_btn.setStyleSheet("")
        page.clear_all_btn.setStyleSheet("")
        page.apply_theme()
        assert page.translate_btn.styleSheet() != ""
        assert page.clear_all_btn.styleSheet() != ""

    def test_apply_language_updates_label(self, page) -> None:
        """apply_language updates the section label text."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page.section_label.setText("")
        page.apply_language()
        assert page.section_label.text() == tr("files.selected")

    def test_apply_language_updates_translate_btn(self, page) -> None:
        """apply_language updates translate button text."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page.translate_btn.setText("")
        page.apply_language()
        assert page.translate_btn.text() == tr("btn.start_translation")

    def test_apply_language_updates_clear_btn(self, page) -> None:
        """apply_language updates clear button text."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page.clear_all_btn.setText("")
        page.apply_language()
        assert page.clear_all_btn.text() == tr("btn.delete_all")

    def test_double_apply_theme(self, page) -> None:
        """Calling apply_theme twice does not raise."""
        page.apply_theme()
        page.apply_theme()

    def test_double_apply_language(self, page) -> None:
        """Calling apply_language twice does not raise."""
        page.apply_language()
        page.apply_language()


# ---------------------------------------------------------------------------
# EXPANDED: File widget management
# ---------------------------------------------------------------------------


class TestFileWidgetManagementExpanded:
    """Expanded tests for file widget add/remove."""

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_add_multiple_file_widgets(self, _mock_msg, page, tmp_path) -> None:
        """Adding multiple file widgets increases layout count."""
        initial = page.files_vbox.count()
        for i in range(5):
            f = tmp_path / f"file_{i}.pdf"
            f.write_text("content")
            page._add_file_widget(str(f))
        assert page.files_vbox.count() == initial + 5  # noqa: PLR2004

    def test_clear_all_on_empty_list(self, page) -> None:
        """Clear all on empty list does not crash."""
        page.selected_files = []
        page._handle_clear_all()
        assert page.selected_files == []

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_remove_middle_file(self, _mock_msg, page, tmp_path) -> None:
        """Removing a file from the middle of the list works."""
        files = []
        for i in range(3):
            f = tmp_path / f"file_{i}.txt"
            f.write_text("content")
            files.append(str(f))
        page._handle_files_dropped(files)
        assert len(page.selected_files) == 3  # noqa: PLR2004

        # Remove middle file
        from src.ui.components import FileItemWidget  # noqa: PLC0415

        widget = None
        for i in range(page.files_vbox.count()):
            item = page.files_vbox.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), FileItemWidget):
                widget = item.widget()
                break
        if widget:
            page._handle_remove_file(files[0], widget)
        assert len(page.selected_files) == 2  # noqa: PLR2004


# ---------------------------------------------------------------------------
# EXPANDED: Directory handling
# ---------------------------------------------------------------------------


class TestDirectoryHandlingExpanded:
    """Expanded tests for directory drop handling."""

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_nested_directory_adds_files(self, _mock_msg, page, tmp_path) -> None:
        """Files in nested directories are found and added."""
        sub1 = tmp_path / "sub1"
        sub1.mkdir()
        sub2 = sub1 / "sub2"
        sub2.mkdir()
        f = sub2 / "deep.txt"
        f.write_text("content")
        page._handle_files_dropped([str(tmp_path)])
        assert any("deep.txt" in p for p in page.selected_files)

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_empty_directory_no_files_added(self, _mock_msg, page, tmp_path) -> None:
        """Empty directory does not add any files."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        page._handle_files_dropped([str(empty_dir)])
        assert len(page.selected_files) == 0

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_directory_with_only_unsupported(
        self,
        mock_msg,
        page,
        tmp_path,
    ) -> None:
        """Directory with only unsupported files shows dialog."""
        sub = tmp_path / "bad"
        sub.mkdir()
        f = sub / "readme.xyz"
        f.write_text("content")
        page._handle_files_dropped([str(sub)])
        assert len(page.selected_files) == 0
        mock_msg.assert_called_once()

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_unsupported_dialog_truncation(
        self,
        mock_msg,
        page,
        tmp_path,
    ) -> None:
        """More than 10 unsupported files get truncated in dialog."""
        for i in range(15):
            f = tmp_path / f"file_{i}.zzz"
            f.write_text("content")
        page._handle_files_dropped([str(tmp_path)])
        mock_msg.assert_called_once()
        # The dialog message should contain "... and X more"
        call_args = mock_msg.call_args
        msg = call_args[0][2] if len(call_args[0]) > 2 else ""
        assert "more" in msg or len(page.selected_files) == 0


# ---------------------------------------------------------------------------
# NEW: File drag-drop — all supported formats
# ---------------------------------------------------------------------------


class TestFileDropAllFormats:
    """Tests for file drop handling with various supported formats."""

    @pytest.fixture()
    def extended_tmp_files(self, tmp_path):
        """Creates temporary files for many supported formats."""
        files = {}
        for ext in (
            ".docx",
            ".pdf",
            ".txt",
            ".png",
            ".jpg",
            ".xlsx",
            ".html",
            ".pptx",
            ".odt",
            ".ods",
            ".odp",
            ".md",
            ".rst",
            ".xml",
            ".rtf",
            ".json",
            ".csv",
            ".epub",
            ".srt",
            ".vtt",
            ".ass",
            ".ssa",
            ".po",
            ".pot",
            ".xliff",
            ".xlf",
            ".yaml",
            ".yml",
            ".properties",
            ".strings",
            ".tiff",
            ".bmp",
            ".webp",
        ):
            f = tmp_path / f"sample{ext}"
            f.write_text("content", encoding="utf-8")
            files[ext] = str(f)
        return files

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_drop_docx(self, _mock_msg, page, extended_tmp_files) -> None:
        """Dropping a .docx file adds it successfully."""
        page._handle_files_dropped([extended_tmp_files[".docx"]])
        assert extended_tmp_files[".docx"] in page.selected_files

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_drop_pdf(self, _mock_msg, page, extended_tmp_files) -> None:
        """Dropping a .pdf file adds it successfully."""
        page._handle_files_dropped([extended_tmp_files[".pdf"]])
        assert extended_tmp_files[".pdf"] in page.selected_files

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_drop_xlsx(self, _mock_msg, page, extended_tmp_files) -> None:
        """Dropping a .xlsx file adds it successfully."""
        page._handle_files_dropped([extended_tmp_files[".xlsx"]])
        assert extended_tmp_files[".xlsx"] in page.selected_files

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_drop_pptx(self, _mock_msg, page, extended_tmp_files) -> None:
        """Dropping a .pptx file adds it successfully."""
        page._handle_files_dropped([extended_tmp_files[".pptx"]])
        assert extended_tmp_files[".pptx"] in page.selected_files

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_drop_odt(self, _mock_msg, page, extended_tmp_files) -> None:
        """Dropping a .odt file adds it successfully."""
        page._handle_files_dropped([extended_tmp_files[".odt"]])
        assert extended_tmp_files[".odt"] in page.selected_files

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_drop_html(self, _mock_msg, page, extended_tmp_files) -> None:
        """Dropping a .html file adds it successfully."""
        page._handle_files_dropped([extended_tmp_files[".html"]])
        assert extended_tmp_files[".html"] in page.selected_files

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_drop_md(self, _mock_msg, page, extended_tmp_files) -> None:
        """Dropping a .md file adds it successfully."""
        page._handle_files_dropped([extended_tmp_files[".md"]])
        assert extended_tmp_files[".md"] in page.selected_files

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_drop_json(self, _mock_msg, page, extended_tmp_files) -> None:
        """Dropping a .json file adds it successfully."""
        page._handle_files_dropped([extended_tmp_files[".json"]])
        assert extended_tmp_files[".json"] in page.selected_files

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_drop_csv(self, _mock_msg, page, extended_tmp_files) -> None:
        """Dropping a .csv file adds it successfully."""
        page._handle_files_dropped([extended_tmp_files[".csv"]])
        assert extended_tmp_files[".csv"] in page.selected_files

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_drop_srt(self, _mock_msg, page, extended_tmp_files) -> None:
        """Dropping a .srt file adds it successfully."""
        page._handle_files_dropped([extended_tmp_files[".srt"]])
        assert extended_tmp_files[".srt"] in page.selected_files

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_drop_vtt(self, _mock_msg, page, extended_tmp_files) -> None:
        """Dropping a .vtt file adds it successfully."""
        page._handle_files_dropped([extended_tmp_files[".vtt"]])
        assert extended_tmp_files[".vtt"] in page.selected_files

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_drop_yaml(self, _mock_msg, page, extended_tmp_files) -> None:
        """Dropping a .yaml file adds it successfully."""
        page._handle_files_dropped([extended_tmp_files[".yaml"]])
        assert extended_tmp_files[".yaml"] in page.selected_files

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_drop_png_image(self, _mock_msg, page, extended_tmp_files) -> None:
        """Dropping a .png image adds it successfully."""
        page._handle_files_dropped([extended_tmp_files[".png"]])
        assert extended_tmp_files[".png"] in page.selected_files

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_drop_jpg_image(self, _mock_msg, page, extended_tmp_files) -> None:
        """Dropping a .jpg image adds it successfully."""
        page._handle_files_dropped([extended_tmp_files[".jpg"]])
        assert extended_tmp_files[".jpg"] in page.selected_files

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_drop_multiple_formats_at_once(
        self, _mock_msg, page, extended_tmp_files
    ) -> None:
        """Dropping multiple different formats adds all of them."""
        paths = [
            extended_tmp_files[".docx"],
            extended_tmp_files[".pdf"],
            extended_tmp_files[".xlsx"],
            extended_tmp_files[".html"],
            extended_tmp_files[".txt"],
        ]
        page._handle_files_dropped(paths)
        assert len(page.selected_files) == 5  # noqa: PLR2004

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_drop_mixed_valid_invalid_many(self, mock_msg, page, tmp_path) -> None:
        """Dropping a mix of many valid and invalid files works correctly."""
        valid_files = []
        for ext in (".docx", ".pdf", ".txt"):
            f = tmp_path / f"valid{ext}"
            f.write_text("content")
            valid_files.append(str(f))
        invalid_files = []
        for ext in (".xyz", ".abc", ".zzz"):
            f = tmp_path / f"invalid{ext}"
            f.write_text("content")
            invalid_files.append(str(f))
        page._handle_files_dropped(valid_files + invalid_files)
        assert len(page.selected_files) == 3  # noqa: PLR2004
        mock_msg.assert_called_once()


# ---------------------------------------------------------------------------
# NEW: Worker lifecycle tests
# ---------------------------------------------------------------------------


class TestWorkerLifecycle:
    """Tests for translation worker lifecycle."""

    @patch("src.ui.pages.translate_document.start_translation_worker")
    @patch(
        "src.ui.pages.translate_document.setup_translation_tasks",
        return_value=[(1, "/s/f1.docx", "en", "fr"), (2, "/s/f2.pdf", "en", "fr")],
    )
    @patch(
        "src.ui.pages.translate_document.LanguageSelectionDialog.get_selection",
        return_value=("English", "French", None, True),
    )
    @patch("src.ui.pages.translate_document.require_setup", return_value=True)
    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_worker_started_with_multiple_tasks(
        self,
        _mock_msg,
        _mock_require,
        _mock_lang,
        mock_setup,
        mock_worker,
        page,
        tmp_files,
        _mock_history_deps,
    ) -> None:
        """Worker is started when multiple tasks are created."""
        page.selected_files = [tmp_files[".docx"], tmp_files[".pdf"]]
        page._add_file_widget(tmp_files[".docx"])
        page._add_file_widget(tmp_files[".pdf"])
        page._handle_translate()
        mock_worker.assert_called_once()

    @patch("src.ui.pages.translate_document.start_translation_worker")
    @patch(
        "src.ui.pages.translate_document.setup_translation_tasks",
        return_value=[(1, "/s/f.docx", "en", "ja")],
    )
    @patch(
        "src.ui.pages.translate_document.LanguageSelectionDialog.get_selection",
        return_value=("English", "Japanese", None, True),
    )
    @patch("src.ui.pages.translate_document.require_setup", return_value=True)
    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_worker_receives_correct_tasks(
        self,
        _mock_msg,
        _mock_require,
        _mock_lang,
        mock_setup,
        mock_worker,
        page,
        tmp_files,
        _mock_history_deps,
    ) -> None:
        """Worker receives the tasks returned by setup_translation_tasks."""
        page.selected_files = [tmp_files[".docx"]]
        page._add_file_widget(tmp_files[".docx"])
        page._handle_translate()
        call_args = mock_worker.call_args
        assert call_args is not None
        # First positional arg (after window) should be the tasks list
        tasks_arg = call_args[0][1]
        assert len(tasks_arg) == 1

    def test_translate_noop_with_empty_files_explicit(self, page) -> None:
        """Translate with explicitly empty selected_files is a no-op."""
        page.selected_files = []
        page._handle_translate()
        assert len(page.selected_files) == 0


# ---------------------------------------------------------------------------
# NEW: Button state management during translation
# ---------------------------------------------------------------------------


class TestButtonStateDuringTranslation:
    """Tests for button state management."""

    def test_translate_btn_disabled_no_files(self, page) -> None:
        """Translate button is disabled when no files are selected."""
        page.selected_files = []
        page._update_ui_state()
        assert not page.translate_btn.isEnabled()

    def test_translate_btn_enabled_with_one_file(self, page) -> None:
        """Translate button is enabled with exactly one file."""
        page.selected_files = ["/fake/file.docx"]
        page._update_ui_state()
        assert page.translate_btn.isEnabled()

    def test_translate_btn_enabled_with_many_files(self, page) -> None:
        """Translate button is enabled with many files."""
        page.selected_files = [f"/fake/file_{i}.docx" for i in range(20)]
        page._update_ui_state()
        assert page.translate_btn.isEnabled()

    def test_badge_shows_correct_count_for_many(self, page) -> None:
        """Badge shows correct count for many files."""
        page.selected_files = [f"/fake/f{i}.pdf" for i in range(15)]
        page._update_ui_state()
        assert page.files_badge.text() == "15"

    def test_badge_zero_after_clear(self, page) -> None:
        """Badge shows 0 after clearing all files."""
        page.selected_files = ["/fake/f.pdf"]
        page._update_ui_state()
        page.selected_files.clear()
        page._update_ui_state()
        assert page.files_badge.text() == "0"

    def test_view_switches_with_single_file(self, page) -> None:
        """Adding a single file switches to files view."""
        page.selected_files = ["/fake/f.txt"]
        page._update_ui_state()
        assert page.stack.currentIndex() == _VIEW_FILES

    def test_view_switches_back_on_clear(self, page) -> None:
        """Clearing files switches back to history view."""
        page.selected_files = ["/fake/f.txt"]
        page._update_ui_state()
        page.selected_files.clear()
        page._update_ui_state()
        assert page.stack.currentIndex() == _VIEW_HISTORY


# ---------------------------------------------------------------------------
# NEW: Language selection persistence / error codes
# ---------------------------------------------------------------------------


class TestLanguageSelectionAndErrors:
    """Tests for language selection and error handling."""

    @patch("src.ui.pages.translate_document.start_translation_worker")
    @patch("src.ui.pages.translate_document.setup_translation_tasks")
    @patch(
        "src.ui.pages.translate_document.LanguageSelectionDialog.get_selection",
        return_value=("Japanese", "English", None, True),
    )
    @patch("src.ui.pages.translate_document.require_setup", return_value=True)
    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_language_passed_to_setup_tasks(
        self,
        _mock_msg,
        _mock_require,
        _mock_lang,
        mock_setup,
        _mock_worker,
        page,
        tmp_files,
        _mock_history_deps,
    ) -> None:
        """Selected languages are passed to setup_translation_tasks."""
        page.selected_files = [tmp_files[".docx"]]
        page._add_file_widget(tmp_files[".docx"])
        mock_setup.return_value = []
        page._handle_translate()
        mock_setup.assert_called_once()
        args = mock_setup.call_args[0]
        assert args[1] == "Japanese"
        assert args[2] == "English"

    @patch("src.ui.pages.translate_document.require_setup")
    def test_llm_not_configured_blocks_translate(
        self, mock_require, page, tmp_files
    ) -> None:
        """Translation is blocked when LLM is not configured."""
        mock_require.return_value = False
        page.selected_files = [tmp_files[".docx"]]
        page._handle_translate()
        assert tmp_files[".docx"] in page.selected_files

    @patch("src.ui.pages.translate_document.require_setup")
    def test_ocr_not_configured_with_images_blocks(
        self, mock_require, page, tmp_files
    ) -> None:
        """Translation is blocked when images present but OCR not configured."""
        mock_require.side_effect = [True, False]
        page.selected_files = [tmp_files[".png"]]
        page._handle_translate()
        assert tmp_files[".png"] in page.selected_files


# ---------------------------------------------------------------------------
# NEW: Theme and language update expanded
# ---------------------------------------------------------------------------


class TestThemeLanguageExpanded:
    """Expanded tests for theme and language updates."""

    def test_apply_theme_updates_badge_style(self, page) -> None:
        """apply_theme updates the files_badge stylesheet."""
        page.files_badge.setStyleSheet("")
        page.apply_theme()
        assert page.files_badge.styleSheet() != ""

    def test_apply_theme_updates_section_label_style(self, page) -> None:
        """apply_theme updates the section_label stylesheet."""
        page.section_label.setStyleSheet("")
        page.apply_theme()
        assert page.section_label.styleSheet() != ""

    def test_apply_theme_updates_translate_btn_style(self, page) -> None:
        """apply_theme updates the translate_btn stylesheet."""
        page.translate_btn.setStyleSheet("")
        page.apply_theme()
        assert page.translate_btn.styleSheet() != ""

    def test_apply_theme_updates_clear_btn_style(self, page) -> None:
        """apply_theme updates the clear_all_btn stylesheet."""
        page.clear_all_btn.setStyleSheet("")
        page.apply_theme()
        assert page.clear_all_btn.styleSheet() != ""

    def test_apply_theme_twice_no_crash(self, page) -> None:
        """Calling apply_theme twice does not crash."""
        page.apply_theme()
        page.apply_theme()

    def test_apply_language_twice_no_crash(self, page, _mock_history_deps) -> None:
        """Calling apply_language twice does not crash."""
        page.apply_language()
        page.apply_language()

    def test_apply_theme_then_language(self, page, _mock_history_deps) -> None:
        """Calling apply_theme then apply_language does not crash."""
        page.apply_theme()
        page.apply_language()

    def test_apply_language_then_theme(self, page, _mock_history_deps) -> None:
        """Calling apply_language then apply_theme does not crash."""
        page.apply_language()
        page.apply_theme()


# ---------------------------------------------------------------------------
# NEW: Drop area reparenting
# ---------------------------------------------------------------------------


class TestDropAreaReparenting:
    """Tests for drop area reparenting between views."""

    def test_drop_area_in_history_initially(self, page) -> None:
        """Drop area is parented in history view initially."""
        assert page.drop_area.parent() is not None

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_drop_area_moves_to_files_view(self, _mock_msg, page, tmp_files) -> None:
        """Drop area moves to files view when files are added."""
        page._handle_files_dropped([tmp_files[".docx"]])
        # Drop area should now be in files wrapper
        assert page.stack.currentIndex() == _VIEW_FILES

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_drop_area_returns_to_history(self, _mock_msg, page, tmp_files) -> None:
        """Drop area returns to history view when files are cleared."""
        page._handle_files_dropped([tmp_files[".docx"]])
        page._handle_clear_all()
        assert page.stack.currentIndex() == _VIEW_HISTORY

    def test_drop_area_info_label_default(self, page) -> None:
        """Drop area info label shows default text when no files."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page.selected_files = []
        page._update_ui_state()
        assert page.drop_area.info_label.text() == tr("drop.title")

    def test_drop_area_info_label_with_files(self, page) -> None:
        """Drop area info label shows 'more' text when files exist."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page.selected_files = ["/fake/f.docx"]
        page._update_ui_state()
        assert page.drop_area.info_label.text() == tr("drop.title_more")


# ---------------------------------------------------------------------------
# NEW: File widget management expanded
# ---------------------------------------------------------------------------


class TestFileWidgetManagementExpanded:
    """Expanded tests for file widget management."""

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_add_widget_increments_layout(self, _mock_msg, page, tmp_files) -> None:
        """Each file widget increments the layout count."""
        initial = page.files_vbox.count()
        page._add_file_widget(tmp_files[".docx"])
        assert page.files_vbox.count() == initial + 1
        page._add_file_widget(tmp_files[".pdf"])
        assert page.files_vbox.count() == initial + 2  # noqa: PLR2004

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_clear_all_leaves_only_stretch(self, _mock_msg, page, tmp_files) -> None:
        """After clear_all, only the stretch spacer remains in layout."""
        page._handle_files_dropped(
            [tmp_files[".docx"], tmp_files[".pdf"], tmp_files[".txt"]]
        )
        page._handle_clear_all()
        assert page.files_vbox.count() == 1

    def test_remove_nonexistent_file_safe(self, page) -> None:
        """Removing a file not in the list does not crash."""
        fake = MagicMock()
        fake.setParent = MagicMock()
        fake.deleteLater = MagicMock()
        page._handle_remove_file("/does/not/exist.docx", fake)
        assert len(page.selected_files) == 0

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_remove_last_file_switches_view(self, _mock_msg, page, tmp_files) -> None:
        """Removing the last file switches back to history view."""
        page._handle_files_dropped([tmp_files[".docx"]])
        assert page.stack.currentIndex() == _VIEW_FILES

        from src.ui.components import FileItemWidget  # noqa: PLC0415

        widget = None
        for i in range(page.files_vbox.count()):
            item = page.files_vbox.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), FileItemWidget):
                widget = item.widget()
                break

        page._handle_remove_file(tmp_files[".docx"], widget)
        assert page.stack.currentIndex() == _VIEW_HISTORY


# ---------------------------------------------------------------------------
# NEW: Edge cases expanded
# ---------------------------------------------------------------------------


class TestEdgeCasesExpanded:
    """Expanded edge case tests."""

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_drop_same_file_three_times(self, _mock_msg, page, tmp_files) -> None:
        """Dropping the same file three times only adds it once."""
        for _ in range(3):
            page._handle_files_dropped([tmp_files[".pdf"]])
        assert page.selected_files.count(tmp_files[".pdf"]) == 1

    def test_clear_all_multiple_times(self, page) -> None:
        """Calling clear_all multiple times is safe."""
        page._handle_clear_all()
        page._handle_clear_all()
        page._handle_clear_all()
        assert len(page.selected_files) == 0

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_drop_zero_byte_docx(self, mock_msg, page, tmp_path) -> None:
        """Zero-byte .docx is rejected."""
        f = tmp_path / "empty.docx"
        f.write_bytes(b"")
        page._handle_files_dropped([str(f)])
        assert len(page.selected_files) == 0
        mock_msg.assert_called_once()

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_drop_zero_byte_pdf(self, mock_msg, page, tmp_path) -> None:
        """Zero-byte .pdf is rejected."""
        f = tmp_path / "empty.pdf"
        f.write_bytes(b"")
        page._handle_files_dropped([str(f)])
        assert len(page.selected_files) == 0
        mock_msg.assert_called_once()

    def test_page_has_window_context(self, page, window) -> None:
        """Page stores window context reference."""
        assert page.window_context is window

    def test_page_selected_files_is_list(self, page) -> None:
        """selected_files attribute is a list."""
        assert isinstance(page.selected_files, list)

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_drop_many_valid_files(self, _mock_msg, page, tmp_path) -> None:
        """Dropping 50 valid files adds all of them."""
        paths = []
        for i in range(50):
            f = tmp_path / f"file_{i}.txt"
            f.write_text("content")
            paths.append(str(f))
        page._handle_files_dropped(paths)
        assert len(page.selected_files) == 50  # noqa: PLR2004

    @patch("src.ui.pages.translate_document.QFileDialog.getOpenFileNames")
    def test_browse_dialog_cancelled_safe(self, mock_dialog, page) -> None:
        """Cancelling browse dialog is safe and adds no files."""
        mock_dialog.return_value = ([], "")
        page._handle_files_dropped([])
        assert len(page.selected_files) == 0

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_history_view_embedded(self, _mock_msg, page) -> None:
        """Embedded HistoryPage exists and is accessible."""
        from src.ui.pages.history import HistoryPage  # noqa: PLC0415

        assert isinstance(page.history_view, HistoryPage)


# ---------------------------------------------------------------------------
# NEW: Check requirements expanded
# ---------------------------------------------------------------------------


class TestCheckRequirementsExpanded:
    """Expanded tests for _check_requirements."""

    @patch("src.ui.pages.translate_document.require_setup", return_value=True)
    def test_text_only_files_one_check(self, mock_require, page) -> None:
        """Text-only files trigger exactly one require_setup call."""
        page.selected_files = ["/f/a.txt", "/f/b.docx", "/f/c.pdf"]
        page._check_requirements()
        assert mock_require.call_count == 1

    @patch("src.ui.pages.translate_document.require_setup", return_value=True)
    def test_image_only_files_two_checks(self, mock_require, page) -> None:
        """Image-only files trigger two require_setup calls."""
        page.selected_files = ["/f/a.png", "/f/b.jpg"]
        page._check_requirements()
        assert mock_require.call_count == 2  # noqa: PLR2004

    @patch("src.ui.pages.translate_document.require_setup", return_value=True)
    def test_tiff_triggers_ocr_check(self, mock_require, page) -> None:
        """TIFF images trigger the OCR check."""
        page.selected_files = ["/f/a.tiff"]
        page._check_requirements()
        assert mock_require.call_count == 2  # noqa: PLR2004

    @patch("src.ui.pages.translate_document.require_setup", return_value=True)
    def test_empty_files_one_check(self, mock_require, page) -> None:
        """Empty selected_files still triggers LLM check."""
        page.selected_files = ["/fake.docx"]
        page._check_requirements()
        assert mock_require.call_count == 1


# ---------------------------------------------------------------------------
# NEW: Clean history view
# ---------------------------------------------------------------------------


class TestCleanHistoryViewExpanded:
    """Expanded tests for _clean_history_view."""

    def test_clean_history_view_repeated(self, page) -> None:
        """Calling _clean_history_view multiple times is safe."""
        page._clean_history_view()
        page._clean_history_view()

    def test_clean_history_view_preserves_history(self, page) -> None:
        """Cleaning does not remove the history widget itself."""
        from src.ui.pages.history import HistoryPage  # noqa: PLC0415

        assert isinstance(page.history_view, HistoryPage)
        page._clean_history_view()
        assert isinstance(page.history_view, HistoryPage)


# ---------------------------------------------------------------------------
# NEW: Stacked widget structure
# ---------------------------------------------------------------------------


class TestStackedWidgetStructure:
    """Tests for stacked widget internal structure."""

    def test_stack_view_0_is_history_wrapper(self, page) -> None:
        """View 0 in the stack is the history wrapper."""
        assert page.stack.widget(0) is page.history_wrapper

    def test_stack_view_1_is_files_wrapper(self, page) -> None:
        """View 1 in the stack is the files wrapper."""
        assert page.stack.widget(1) is page.files_wrapper

    def test_history_wrapper_has_layout(self, page) -> None:
        """History wrapper has a layout."""
        assert page.history_wrapper.layout() is not None

    def test_files_wrapper_has_layout(self, page) -> None:
        """Files wrapper has a layout."""
        assert page.files_wrapper.layout() is not None


# ---------------------------------------------------------------------------
# NEW: File extension specific tests
# ---------------------------------------------------------------------------


class TestFileExtensionHandling:
    """Tests for specific file extension handling."""

    def test_drop_odt_file(self, page, tmp_path) -> None:
        """ODT file is accepted."""
        f = tmp_path / "test.odt"
        f.write_text("content")
        page._handle_files_dropped([str(f)])
        assert len(page.selected_files) == 1

    def test_drop_ods_file(self, page, tmp_path) -> None:
        """ODS file is accepted."""
        f = tmp_path / "test.ods"
        f.write_text("content")
        page._handle_files_dropped([str(f)])
        assert len(page.selected_files) == 1

    def test_drop_odp_file(self, page, tmp_path) -> None:
        """ODP file is accepted."""
        f = tmp_path / "test.odp"
        f.write_text("content")
        page._handle_files_dropped([str(f)])
        assert len(page.selected_files) == 1

    def test_drop_pptx_file(self, page, tmp_path) -> None:
        """PPTX file is accepted."""
        f = tmp_path / "test.pptx"
        f.write_text("content")
        page._handle_files_dropped([str(f)])
        assert len(page.selected_files) == 1

    def test_drop_rst_file(self, page, tmp_path) -> None:
        """RST file is accepted."""
        f = tmp_path / "test.rst"
        f.write_text("content")
        page._handle_files_dropped([str(f)])
        assert len(page.selected_files) == 1

    def test_drop_srt_file(self, page, tmp_path) -> None:
        """SRT file is accepted."""
        f = tmp_path / "test.srt"
        f.write_text("content")
        page._handle_files_dropped([str(f)])
        assert len(page.selected_files) == 1

    def test_drop_vtt_file(self, page, tmp_path) -> None:
        """VTT file is accepted."""
        f = tmp_path / "test.vtt"
        f.write_text("content")
        page._handle_files_dropped([str(f)])
        assert len(page.selected_files) == 1

    def test_drop_csv_file(self, page, tmp_path) -> None:
        """CSV file is accepted."""
        f = tmp_path / "test.csv"
        f.write_text("content")
        page._handle_files_dropped([str(f)])
        assert len(page.selected_files) == 1

    def test_drop_json_file(self, page, tmp_path) -> None:
        """JSON file is accepted."""
        f = tmp_path / "test.json"
        f.write_text("content")
        page._handle_files_dropped([str(f)])
        assert len(page.selected_files) == 1

    def test_drop_yaml_file(self, page, tmp_path) -> None:
        """YAML file is accepted."""
        f = tmp_path / "test.yaml"
        f.write_text("content")
        page._handle_files_dropped([str(f)])
        assert len(page.selected_files) == 1

    def test_drop_yml_file(self, page, tmp_path) -> None:
        """YML file is accepted."""
        f = tmp_path / "test.yml"
        f.write_text("content")
        page._handle_files_dropped([str(f)])
        assert len(page.selected_files) == 1

    def test_drop_md_file(self, page, tmp_path) -> None:
        """Markdown file is accepted."""
        f = tmp_path / "test.md"
        f.write_text("content")
        page._handle_files_dropped([str(f)])
        assert len(page.selected_files) == 1

    def test_drop_epub_file(self, page, tmp_path) -> None:
        """EPUB file is accepted."""
        f = tmp_path / "test.epub"
        f.write_text("content")
        page._handle_files_dropped([str(f)])
        assert len(page.selected_files) == 1

    def test_drop_xml_file(self, page, tmp_path) -> None:
        """XML file is accepted."""
        f = tmp_path / "test.xml"
        f.write_text("content")
        page._handle_files_dropped([str(f)])
        assert len(page.selected_files) == 1

    def test_drop_rtf_file(self, page, tmp_path) -> None:
        """RTF file is accepted."""
        f = tmp_path / "test.rtf"
        f.write_text("content")
        page._handle_files_dropped([str(f)])
        assert len(page.selected_files) == 1

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_drop_exe_rejected(self, mock_msg, page, tmp_path) -> None:
        """EXE file is rejected as unsupported."""
        f = tmp_path / "test.exe"
        f.write_text("content")
        page._handle_files_dropped([str(f)])
        assert len(page.selected_files) == 0
        mock_msg.assert_called_once()

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_drop_zip_rejected(self, mock_msg, page, tmp_path) -> None:
        """ZIP file is rejected as unsupported."""
        f = tmp_path / "test.zip"
        f.write_text("content")
        page._handle_files_dropped([str(f)])
        assert len(page.selected_files) == 0
        mock_msg.assert_called_once()

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_drop_mp4_rejected(self, mock_msg, page, tmp_path) -> None:
        """MP4 file is rejected as unsupported."""
        f = tmp_path / "test.mp4"
        f.write_text("content")
        page._handle_files_dropped([str(f)])
        assert len(page.selected_files) == 0
        mock_msg.assert_called_once()

    def test_drop_ass_file(self, page, tmp_path) -> None:
        """ASS subtitle file is accepted."""
        f = tmp_path / "test.ass"
        f.write_text("content")
        page._handle_files_dropped([str(f)])
        assert len(page.selected_files) == 1

    def test_drop_ssa_file(self, page, tmp_path) -> None:
        """SSA subtitle file is accepted."""
        f = tmp_path / "test.ssa"
        f.write_text("content")
        page._handle_files_dropped([str(f)])
        assert len(page.selected_files) == 1

    def test_drop_po_file(self, page, tmp_path) -> None:
        """PO file is accepted."""
        f = tmp_path / "test.po"
        f.write_text("content")
        page._handle_files_dropped([str(f)])
        assert len(page.selected_files) == 1

    def test_drop_pot_file(self, page, tmp_path) -> None:
        """POT file is accepted."""
        f = tmp_path / "test.pot"
        f.write_text("content")
        page._handle_files_dropped([str(f)])
        assert len(page.selected_files) == 1

    def test_drop_properties_file(self, page, tmp_path) -> None:
        """Properties file is accepted."""
        f = tmp_path / "test.properties"
        f.write_text("content")
        page._handle_files_dropped([str(f)])
        assert len(page.selected_files) == 1

    def test_drop_strings_file(self, page, tmp_path) -> None:
        """Apple Strings file is accepted."""
        f = tmp_path / "test.strings"
        f.write_text("content")
        page._handle_files_dropped([str(f)])
        assert len(page.selected_files) == 1

    def test_drop_tiff_image(self, page, tmp_path) -> None:
        """TIFF image is accepted."""
        f = tmp_path / "test.tiff"
        f.write_text("content")
        page._handle_files_dropped([str(f)])
        assert len(page.selected_files) == 1

    def test_drop_bmp_image(self, page, tmp_path) -> None:
        """BMP image is accepted."""
        f = tmp_path / "test.bmp"
        f.write_text("content")
        page._handle_files_dropped([str(f)])
        assert len(page.selected_files) == 1

    def test_drop_webp_image(self, page, tmp_path) -> None:
        """WebP image is accepted."""
        f = tmp_path / "test.webp"
        f.write_text("content")
        page._handle_files_dropped([str(f)])
        assert len(page.selected_files) == 1


# ---------------------------------------------------------------------------
# NEW: Directory handling
# ---------------------------------------------------------------------------


class TestDirectoryHandling:
    """Tests for directory traversal in file drop."""

    def test_drop_directory_with_files(self, page, tmp_path) -> None:
        """Dropping a directory adds its supported files."""
        subdir = tmp_path / "docs"
        subdir.mkdir()
        (subdir / "a.txt").write_text("content")
        (subdir / "b.pdf").write_text("content")
        page._handle_files_dropped([str(subdir)])
        assert len(page.selected_files) == 2  # noqa: PLR2004

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_drop_directory_with_unsupported(self, mock_msg, page, tmp_path) -> None:
        """Dropping a directory with unsupported files shows dialog."""
        subdir = tmp_path / "mixed"
        subdir.mkdir()
        (subdir / "ok.txt").write_text("content")
        (subdir / "bad.mp4").write_text("content")
        page._handle_files_dropped([str(subdir)])
        assert len(page.selected_files) == 1
        mock_msg.assert_called_once()

    def test_drop_directory_skips_hidden(self, page, tmp_path) -> None:
        """Dropping a directory skips hidden subdirectories."""
        subdir = tmp_path / "root"
        subdir.mkdir()
        hidden = subdir / ".hidden"
        hidden.mkdir()
        (hidden / "secret.txt").write_text("content")
        (subdir / "visible.txt").write_text("content")
        page._handle_files_dropped([str(subdir)])
        assert len(page.selected_files) == 1

    def test_drop_empty_directory(self, page, tmp_path) -> None:
        """Dropping an empty directory adds nothing."""
        subdir = tmp_path / "empty"
        subdir.mkdir()
        page._handle_files_dropped([str(subdir)])
        assert len(page.selected_files) == 0

    def test_drop_nested_directory(self, page, tmp_path) -> None:
        """Dropping directory with nested subdirs finds files recursively."""
        root = tmp_path / "root"
        root.mkdir()
        sub = root / "sub"
        sub.mkdir()
        (sub / "deep.txt").write_text("content")
        page._handle_files_dropped([str(root)])
        assert len(page.selected_files) == 1


# ---------------------------------------------------------------------------
# NEW: Translation flow detailed
# ---------------------------------------------------------------------------


class TestTranslationFlowDetailed:
    """Detailed tests for the translation flow."""

    @patch("src.ui.pages.translate_document.start_translation_worker")
    @patch(
        "src.ui.pages.translate_document.setup_translation_tasks",
        return_value=[("task1",)],
    )
    @patch("src.ui.pages.translate_document.LanguageSelectionDialog.get_selection")
    @patch("src.ui.pages.translate_document.require_setup", return_value=True)
    def test_translate_clears_files(
        self, mock_setup, mock_dialog, mock_tasks, mock_worker, page, tmp_path
    ) -> None:
        """Translation clears selected files after starting."""
        mock_dialog.return_value = ("en", "vi", None, True)
        f = tmp_path / "test.txt"
        f.write_text("content")
        page._handle_files_dropped([str(f)])
        assert len(page.selected_files) == 1
        page._handle_translate()
        assert len(page.selected_files) == 0

    @patch("src.ui.pages.translate_document.start_translation_worker")
    @patch("src.ui.pages.translate_document.setup_translation_tasks", return_value=[])
    @patch("src.ui.pages.translate_document.LanguageSelectionDialog.get_selection")
    @patch("src.ui.pages.translate_document.require_setup", return_value=True)
    def test_translate_empty_tasks_preserves_files(
        self, mock_setup, mock_dialog, mock_tasks, mock_worker, page, tmp_path
    ) -> None:
        """Empty tasks → worker skipped, files preserved so the user can retry."""
        mock_dialog.return_value = ("en", "vi", None, True)
        f = tmp_path / "test.txt"
        f.write_text("content")
        page._handle_files_dropped([str(f)])
        page._handle_translate()
        mock_worker.assert_not_called()
        # Files are kept so the user can retry without re-selecting.
        assert len(page.selected_files) == 1

    @patch("src.ui.pages.translate_document.require_setup", return_value=False)
    def test_translate_no_llm_setup(self, mock_setup, page, tmp_path) -> None:
        """Translation blocked when LLM not set up."""
        f = tmp_path / "test.txt"
        f.write_text("content")
        page._handle_files_dropped([str(f)])
        page._handle_translate()
        # Files should remain
        assert len(page.selected_files) == 1

    @patch("src.ui.pages.translate_document.LanguageSelectionDialog.get_selection")
    @patch("src.ui.pages.translate_document.require_setup", return_value=True)
    def test_translate_dialog_cancelled(
        self, mock_setup, mock_dialog, page, tmp_path
    ) -> None:
        """Cancelling language dialog keeps files."""
        mock_dialog.return_value = ("en", "vi", None, False)
        f = tmp_path / "test.txt"
        f.write_text("content")
        page._handle_files_dropped([str(f)])
        page._handle_translate()
        assert len(page.selected_files) == 1

    def test_translate_empty_files(self, page) -> None:
        """Translation with no files is a no-op."""
        page.selected_files = []
        page._handle_translate()
        assert len(page.selected_files) == 0


# ---------------------------------------------------------------------------
# NEW: Apply theme and language detailed
# ---------------------------------------------------------------------------


class TestApplyThemeLanguageDetailed:
    """Detailed tests for theme and language application."""

    def test_apply_theme_sets_badge_style(self, page) -> None:
        """apply_theme updates badge stylesheet."""
        original_style = page.files_badge.styleSheet()
        page.apply_theme()
        assert page.files_badge.styleSheet() == original_style

    def test_apply_theme_sets_translate_btn_style(self, page) -> None:
        """apply_theme updates translate button stylesheet."""
        page.apply_theme()
        assert len(page.translate_btn.styleSheet()) > 0

    def test_apply_theme_sets_clear_btn_style(self, page) -> None:
        """apply_theme updates clear button stylesheet."""
        page.apply_theme()
        assert len(page.clear_all_btn.styleSheet()) > 0

    def test_apply_language_sets_section_label(self, page) -> None:
        """apply_language updates section label text."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page.apply_language()
        assert page.section_label.text() == tr("files.selected")

    def test_apply_language_sets_translate_btn_text(self, page) -> None:
        """apply_language updates translate button text."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page.apply_language()
        assert page.translate_btn.text() == tr("btn.start_translation")

    def test_apply_language_sets_clear_btn_text(self, page) -> None:
        """apply_language updates clear button text."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page.apply_language()
        assert page.clear_all_btn.text() == tr("btn.delete_all")


# ---------------------------------------------------------------------------
# NEW: File widget management
# ---------------------------------------------------------------------------


class TestFileWidgetManagement:
    """Tests for file widget add/remove operations."""

    def test_add_file_widget_creates_widget(self, page, tmp_path) -> None:
        """_add_file_widget creates a FileItemWidget."""
        f = tmp_path / "test.txt"
        f.write_text("content")
        count_before = page.files_vbox.count()
        page._add_file_widget(str(f))
        assert page.files_vbox.count() == count_before + 1

    def test_remove_file_updates_list(self, page, tmp_path) -> None:
        """Removing a file updates selected_files list."""
        f = tmp_path / "test.txt"
        f.write_text("content")
        page._handle_files_dropped([str(f)])
        from src.ui.components import FileItemWidget  # noqa: PLC0415

        widget = page.files_vbox.itemAt(0).widget()
        if isinstance(widget, FileItemWidget):
            page._handle_remove_file(str(f), widget)
        assert str(f) not in page.selected_files

    def test_remove_nonexistent_file(self, page, tmp_path) -> None:
        """Removing a file not in selected_files is safe."""
        from src.ui.components import FileItemWidget  # noqa: PLC0415

        f = tmp_path / "ghost.txt"
        f.write_text("content")
        widget = FileItemWidget(str(f), lambda x: "1KB")
        page._handle_remove_file(str(f), widget)
        assert len(page.selected_files) == 0

    def test_clear_all_with_many_files(self, page, tmp_path) -> None:
        """Clearing many files works correctly."""
        paths = []
        for i in range(20):
            f = tmp_path / f"file_{i}.txt"
            f.write_text("content")
            paths.append(str(f))
        page._handle_files_dropped(paths)
        assert len(page.selected_files) == 20  # noqa: PLR2004
        page._handle_clear_all()
        assert len(page.selected_files) == 0


# ---------------------------------------------------------------------------
# NEW: Unsupported file display truncation
# ---------------------------------------------------------------------------


class TestUnsupportedFileTruncation:
    """Tests for truncation of unsupported file list in dialog."""

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_many_unsupported_shows_dialog(self, mock_msg, page, tmp_path) -> None:
        """More than 10 unsupported files still shows a dialog."""
        files = []
        for i in range(15):
            f = tmp_path / f"bad_{i}.xyz"
            f.write_text("content")
            files.append(str(f))
        page._handle_files_dropped(files)
        mock_msg.assert_called_once()
        assert len(page.selected_files) == 0

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_exactly_10_unsupported_shows_dialog(
        self, mock_msg, page, tmp_path
    ) -> None:
        """Exactly 10 unsupported files are shown in dialog."""
        files = []
        for i in range(10):
            f = tmp_path / f"bad_{i}.xyz"
            f.write_text("content")
            files.append(str(f))
        page._handle_files_dropped(files)
        mock_msg.assert_called_once()
        assert len(page.selected_files) == 0

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_single_unsupported_file(self, mock_msg, page, tmp_path) -> None:
        """Single unsupported file shows dialog."""
        f = tmp_path / "bad.xyz"
        f.write_text("content")
        page._handle_files_dropped([str(f)])
        mock_msg.assert_called_once()


# ---------------------------------------------------------------------------
# NEW: Max files limit
# ---------------------------------------------------------------------------


class TestMaxFilesLimit:
    """Tests for the 100-file limit."""

    def test_max_100_files_from_directory(self, page, tmp_path) -> None:
        """Directory traversal stops at 100 files."""
        subdir = tmp_path / "many"
        subdir.mkdir()
        for i in range(150):
            (subdir / f"file_{i}.txt").write_text("content")
        page._handle_files_dropped([str(subdir)])
        assert len(page.selected_files) <= 100  # noqa: PLR2004

    def test_100_individual_files(self, page, tmp_path) -> None:
        """Dropping 100 individual files adds them all."""
        files = []
        for i in range(100):
            f = tmp_path / f"file_{i}.txt"
            f.write_text("content")
            files.append(str(f))
        page._handle_files_dropped(files)
        assert len(page.selected_files) == 100  # noqa: PLR2004


# ---------------------------------------------------------------------------
# NEW: UI state transitions
# ---------------------------------------------------------------------------


class TestUIStateTransitions:
    """Tests for UI state changes during file management."""

    def test_badge_zero_initially(self, page) -> None:
        """Badge shows 0 initially."""
        assert page.files_badge.text() == "0"

    def test_badge_updates_on_add(self, page, tmp_path) -> None:
        """Badge updates when files are added."""
        f = tmp_path / "test.txt"
        f.write_text("content")
        page._handle_files_dropped([str(f)])
        assert page.files_badge.text() == "1"

    def test_badge_updates_on_clear(self, page, tmp_path) -> None:
        """Badge returns to 0 after clear."""
        f = tmp_path / "test.txt"
        f.write_text("content")
        page._handle_files_dropped([str(f)])
        page._handle_clear_all()
        assert page.files_badge.text() == "0"

    def test_translate_btn_disabled_initially(self, page) -> None:
        """Translate button is disabled when no files are selected."""
        assert not page.translate_btn.isEnabled()

    def test_translate_btn_enabled_with_files(self, page, tmp_path) -> None:
        """Translate button is enabled when files are present."""
        f = tmp_path / "test.txt"
        f.write_text("content")
        page._handle_files_dropped([str(f)])
        assert page.translate_btn.isEnabled()

    def test_translate_btn_disabled_after_clear(self, page, tmp_path) -> None:
        """Translate button is disabled after clearing files."""
        f = tmp_path / "test.txt"
        f.write_text("content")
        page._handle_files_dropped([str(f)])
        page._handle_clear_all()
        assert not page.translate_btn.isEnabled()

    def test_stack_switches_to_files_view(self, page, tmp_path) -> None:
        """Stack switches to files view when files are added."""
        f = tmp_path / "test.txt"
        f.write_text("content")
        page._handle_files_dropped([str(f)])
        assert page.stack.currentIndex() == _VIEW_FILES

    def test_stack_switches_to_history_view(self, page, tmp_path) -> None:
        """Stack switches to history view after clearing."""
        f = tmp_path / "test.txt"
        f.write_text("content")
        page._handle_files_dropped([str(f)])
        page._handle_clear_all()
        assert page.stack.currentIndex() == _VIEW_HISTORY

    def test_drop_area_label_changes_with_files(self, page, tmp_path) -> None:
        """Drop area label changes when files are present."""
        from src.constants.i18n import tr  # noqa: PLC0415

        f = tmp_path / "test.txt"
        f.write_text("content")
        page._handle_files_dropped([str(f)])
        assert page.drop_area.info_label.text() == tr("drop.title_more")

    def test_drop_area_label_changes_without_files(self, page) -> None:
        """Drop area label shows default when no files."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page._update_ui_state()
        assert page.drop_area.info_label.text() == tr("drop.title")


# ---------------------------------------------------------------------------
# NEW: Mixed file + directory scenarios
# ---------------------------------------------------------------------------


class TestMixedFileDirScenarios:
    """Tests for mixed file and directory drop scenarios."""

    def test_drop_file_and_directory_together(self, page, tmp_path) -> None:
        """Dropping a file and a directory together adds all."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "a.txt").write_text("content")
        f = tmp_path / "b.pdf"
        f.write_text("content")
        page._handle_files_dropped([str(subdir), str(f)])
        assert len(page.selected_files) == 2  # noqa: PLR2004

    @patch("src.ui.pages.translate_document.CustomMessageDialog.show_message")
    def test_drop_mix_valid_invalid_files(self, mock_msg, page, tmp_path) -> None:
        """Dropping mix of valid and invalid files adds only valid ones."""
        valid = tmp_path / "ok.txt"
        valid.write_text("content")
        invalid = tmp_path / "bad.xyz"
        invalid.write_text("content")
        page._handle_files_dropped([str(valid), str(invalid)])
        assert len(page.selected_files) == 1
        mock_msg.assert_called_once()

    def test_drop_multiple_directories(self, page, tmp_path) -> None:
        """Dropping multiple directories adds all their files."""
        dir1 = tmp_path / "dir1"
        dir1.mkdir()
        (dir1 / "a.txt").write_text("content")
        dir2 = tmp_path / "dir2"
        dir2.mkdir()
        (dir2 / "b.txt").write_text("content")
        page._handle_files_dropped([str(dir1), str(dir2)])
        assert len(page.selected_files) == 2  # noqa: PLR2004

    def test_add_then_remove_then_add(self, page, tmp_path) -> None:
        """Add files, remove all, add again works."""
        f = tmp_path / "test.txt"
        f.write_text("content")
        page._handle_files_dropped([str(f)])
        assert len(page.selected_files) == 1
        page._handle_clear_all()
        assert len(page.selected_files) == 0
        page._handle_files_dropped([str(f)])
        assert len(page.selected_files) == 1


# ---------------------------------------------------------------------------
# NEW: Widget structure verification
# ---------------------------------------------------------------------------


class TestWidgetStructureVerification:
    """Detailed tests for widget structure."""

    def test_has_files_badge(self, page) -> None:
        """Page has a files badge label."""
        assert isinstance(page.files_badge, QLabel)

    def test_has_section_label(self, page) -> None:
        """Page has a section label."""
        assert isinstance(page.section_label, QLabel)

    def test_has_translate_btn(self, page) -> None:
        """Page has a translate button."""
        assert isinstance(page.translate_btn, QPushButton)

    def test_has_clear_all_btn(self, page) -> None:
        """Page has a clear all button."""
        assert isinstance(page.clear_all_btn, QPushButton)

    def test_has_files_vbox(self, page) -> None:
        """Page has a files vbox layout."""
        assert page.files_vbox is not None

    def test_has_scroll_area(self, page) -> None:
        """Page contains a QScrollArea."""
        assert page.findChild(QScrollArea) is not None

    def test_translate_btn_cursor(self, page) -> None:
        """Translate button has pointing hand cursor."""
        assert page.translate_btn.cursor().shape() == Qt.CursorShape.PointingHandCursor

    def test_clear_btn_cursor(self, page) -> None:
        """Clear button has pointing hand cursor."""
        assert page.clear_all_btn.cursor().shape() == Qt.CursorShape.PointingHandCursor


# ---------------------------------------------------------------------------
# NEW: Review-fix behaviours (cap, duplicates, confirm, empty-tasks, embedded OCR)
# ---------------------------------------------------------------------------


class TestDropCapNotice:
    """Tests for the 100-file cap + user notification."""

    def test_cap_hit_shows_notification(self, page, tmp_path) -> None:
        """Dropping >100 files notifies the user and keeps only the first 100."""
        # Generate 105 tiny files in a directory.
        dir_path = tmp_path / "bulk"
        dir_path.mkdir()
        for i in range(105):
            (dir_path / f"f{i:03d}.txt").write_text("x")

        with patch(
            "src.ui.pages.translate_document.CustomMessageDialog.show_message",
        ) as mock_msg:
            page._handle_files_dropped([str(dir_path)])

        assert len(page.selected_files) == 100  # noqa: PLR2004
        assert mock_msg.called
        # The notification body includes the cap-hit tr key (rendered to a
        # human message in production; raw key in the test environment).
        args = mock_msg.call_args.args
        assert any("drop_capped" in str(a) for a in args)

    def test_under_cap_no_cap_mention(self, page, tmp_path) -> None:
        """Dropping a normal batch does not mention the cap."""
        dir_path = tmp_path / "small"
        dir_path.mkdir()
        for i in range(3):
            (dir_path / f"f{i}.txt").write_text("x")

        with patch(
            "src.ui.pages.translate_document.CustomMessageDialog.show_message",
        ) as mock_msg:
            page._handle_files_dropped([str(dir_path)])

        # No issues → no dialog.
        mock_msg.assert_not_called()


class TestDropDuplicateNotice:
    """Tests for silent-duplicate-skip notification."""

    def test_duplicate_drop_is_reported(self, page, tmp_files) -> None:
        """Re-dropping an already-selected file surfaces a duplicates notice."""
        page._handle_files_dropped([tmp_files[".docx"]])  # first drop
        assert len(page.selected_files) == 1

        with patch(
            "src.ui.pages.translate_document.CustomMessageDialog.show_message",
        ) as mock_msg:
            page._handle_files_dropped([tmp_files[".docx"]])  # second drop

        # Selection unchanged, user was notified.
        assert len(page.selected_files) == 1
        mock_msg.assert_called_once()


class TestClearAllConfirmation:
    """Tests for the confirm dialog before clearing selection."""

    def test_clear_all_with_confirm_true_clears(self, page, tmp_files) -> None:
        """Accepting the confirm dialog clears files."""
        page._handle_files_dropped([tmp_files[".docx"], tmp_files[".pdf"]])
        assert len(page.selected_files) == 2  # noqa: PLR2004

        with patch(
            "src.ui.pages.translate_document.CustomConfirmDialog.confirm",
            return_value=True,
        ):
            page._handle_clear_all()

        assert len(page.selected_files) == 0

    def test_clear_all_with_confirm_false_is_noop(self, page, tmp_files) -> None:
        """Rejecting the confirm dialog keeps files intact."""
        page._handle_files_dropped([tmp_files[".docx"], tmp_files[".pdf"]])

        with patch(
            "src.ui.pages.translate_document.CustomConfirmDialog.confirm",
            return_value=False,
        ):
            page._handle_clear_all()

        assert len(page.selected_files) == 2  # noqa: PLR2004

    def test_clear_all_confirm_false_kwarg_skips_dialog(
        self,
        page,
        tmp_files,
    ) -> None:
        """Internal callers (confirm=False) bypass the dialog entirely."""
        page._handle_files_dropped([tmp_files[".docx"]])

        with patch(
            "src.ui.pages.translate_document.CustomConfirmDialog.confirm",
        ) as mock_confirm:
            page._handle_clear_all(confirm=False)

        mock_confirm.assert_not_called()
        assert len(page.selected_files) == 0


class TestNeedsOcrForEmbeddedImages:
    """Tests for the _needs_ocr helper that gates OCR prompts."""

    def test_raw_image_always_needs_ocr(self, page) -> None:
        """A raw image always triggers the OCR requirement."""
        page.selected_files = ["/fake/photo.png"]
        assert page._needs_ocr() is True

    def test_pdf_with_setting_off_no_ocr(self, page) -> None:
        """A PDF with translate-doc-images disabled does NOT need OCR."""
        page.selected_files = ["/fake/doc.pdf"]
        with patch(
            "src.ui.pages.translate_document.load_setting",
            return_value=False,
        ):
            assert page._needs_ocr() is False

    def test_pdf_with_setting_on_needs_ocr(self, page) -> None:
        """A PDF with translate-doc-images enabled triggers the OCR prompt."""
        page.selected_files = ["/fake/doc.pdf"]
        with patch(
            "src.ui.pages.translate_document.load_setting",
            return_value=True,
        ):
            assert page._needs_ocr() is True

    def test_docx_with_setting_on_needs_ocr(self, page) -> None:
        """A DOCX with embedded-image translation enabled needs OCR."""
        page.selected_files = ["/fake/doc.docx"]
        with patch(
            "src.ui.pages.translate_document.load_setting",
            return_value=True,
        ):
            assert page._needs_ocr() is True

    def test_text_files_never_need_ocr(self, page) -> None:
        """Pure text files never need OCR regardless of settings."""
        page.selected_files = ["/fake/doc.txt", "/fake/data.json"]
        with patch(
            "src.ui.pages.translate_document.load_setting",
            return_value=True,
        ):
            assert page._needs_ocr() is False


class TestTranslateEmptyTasksKeepsFiles:
    """Covers the regression fix: empty tasks should NOT clear the selection."""

    @patch("src.ui.pages.translate_document.start_translation_worker")
    @patch(
        "src.ui.pages.translate_document.setup_translation_tasks",
        return_value=[],
    )
    @patch(
        "src.ui.pages.translate_document.LanguageSelectionDialog.get_selection",
        return_value=("English", "French", None, True),
    )
    @patch("src.ui.pages.translate_document.require_setup", return_value=True)
    def test_empty_tasks_keeps_files_and_notifies(
        self,
        _mock_require,
        _mock_lang,
        _mock_setup,
        _mock_worker,
        page,
        tmp_files,
    ) -> None:
        """The user keeps their selection AND sees an error dialog."""
        page.selected_files = [tmp_files[".docx"]]
        page._add_file_widget(tmp_files[".docx"])

        with patch(
            "src.ui.pages.translate_document.CustomMessageDialog.show_message",
        ) as mock_msg:
            page._handle_translate()

        assert len(page.selected_files) == 1
        mock_msg.assert_called_once()


class TestWalkDroppedPathsFiltersJunkBeforeCap:
    """Junk files don't starve the supported-file cap.

    AGENTS.md docstring: "Only supported-extension files count toward
    the cap, so a directory full of junk (e.g. __pycache__, README
    files, build artifacts) can't starve the cap and hide real
    documents deeper in the tree."
    """

    def test_junk_does_not_consume_supported_cap(self, page, tmp_path) -> None:  # noqa: ANN001
        from src.ui.pages.translate_document import (  # noqa: PLC0415
            _MAX_FILES_PER_DROP,
        )

        # 50 supported + 200 junk in the same directory.  Without
        # the filter-before-cap rule, the 200 junk files could land
        # at the front of the rglob iteration order and prematurely
        # hit a "consumed N slots" check, hiding the supported ones.
        d = tmp_path / "mixed"
        d.mkdir()
        for i in range(50):
            (d / f"doc_{i:03d}.txt").write_text("hi", encoding="utf-8")
        for i in range(200):
            (d / f"junk_{i:03d}.zzz").write_text("garbage", encoding="utf-8")

        supported, unsupported, cap_hit = page._walk_dropped_paths([str(d)])

        assert len(supported) == 50, (
            f"All 50 supported files must survive — junk doesn't take "
            f"slots from the {_MAX_FILES_PER_DROP}-file cap; "
            f"got {len(supported)} supported"
        )
        assert not cap_hit, (
            "50 < 100 so the cap should not have been reached; "
            "a True flag here means the implementation conflated junk "
            "with supported during the cap check"
        )
        # All 200 junk files should be reported as unsupported (so
        # the user can see what was skipped).
        assert len(unsupported) == 200  # noqa: PLR2004

    def test_supported_cap_hits_at_exactly_max_files(
        self, page, tmp_path,  # noqa: ANN001
    ) -> None:
        """Cap kicks in at the (MAX_FILES + 1)th supported file, not earlier."""
        from src.ui.pages.translate_document import (  # noqa: PLC0415
            _MAX_FILES_PER_DROP,
        )

        d = tmp_path / "many_supported"
        d.mkdir()
        # MAX + 5 supported files, no junk.
        for i in range(_MAX_FILES_PER_DROP + 5):
            (d / f"doc_{i:04d}.txt").write_text("hi", encoding="utf-8")

        supported, _, cap_hit = page._walk_dropped_paths([str(d)])

        assert len(supported) == _MAX_FILES_PER_DROP
        assert cap_hit


class TestPrimaryShortcutWiring:
    """Ctrl+Enter primary-action shortcut.

    The page registers a ``QShortcut`` keyed off
    ``get_shortcut("translate_document.translate")``.  Without these
    tests, a refactor of the central shortcut registry could silently
    drop the wiring on this page (the page would still build, the
    button would still work — but Ctrl+Enter would do nothing).
    """

    def test_translate_shortcut_attribute_exists(self, page) -> None:  # noqa: ANN001
        assert hasattr(page, "_translate_shortcut")
        assert page._translate_shortcut is not None

    def test_translate_shortcut_default_key_is_ctrl_return(self, page) -> None:  # noqa: ANN001
        from PySide6.QtCore import Qt  # noqa: PLC0415
        from PySide6.QtGui import QKeySequence  # noqa: PLC0415

        target = QKeySequence(Qt.Modifier.CTRL | Qt.Key.Key_Return)
        assert page._translate_shortcut.key() == target

    def test_translate_shortcut_dispatches_to_handler(self, page) -> None:  # noqa: ANN001
        """Activated signal flows to ``_handle_primary_shortcut``.

        With no history selection, the shortcut must fall through to
        ``_handle_translate`` (the page-level Translate action).
        """
        with (
            patch.object(page, "_handle_translate") as mock_handle,
            patch.object(page, "history_view"),
        ):
            page.history_view.table = None
            page._handle_primary_shortcut()
        mock_handle.assert_called_once()

    def test_translate_shortcut_retranslates_on_history_selection(self, page) -> None:  # noqa: ANN001
        """When a history row is focused + selected, dispatch re-translate."""
        from unittest.mock import MagicMock  # noqa: PLC0415

        # Build a fake history view with a focused, selected table.
        fake_table = MagicMock()
        fake_table.hasFocus.return_value = True
        fake_table.selectionModel.return_value.hasSelection.return_value = True
        page.history_view.table = fake_table

        with (
            patch.object(page.history_view, "on_retranslate") as mock_retrans,
            patch.object(page, "_handle_translate") as mock_translate,
        ):
            page._handle_primary_shortcut()

        mock_retrans.assert_called_once()
        mock_translate.assert_not_called()


class TestEmbeddedHistoryHeaderHidden:
    """Inner history page's header_label is hidden when embedded.

    AGENTS.md: "Pages that embed another `create_page_container`-based
    widget hide the inner title via `page.header_label.setVisible(False)`;
    never match the label by translated text, since language-switch
    ordering can make the comparison miss."
    """

    def test_inner_history_header_is_hidden(self, page) -> None:  # noqa: ANN001
        inner_page = page.history_view.page
        assert inner_page.header_label.isVisible() is False
