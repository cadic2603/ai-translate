"""Tests for history page widget construction and basic attributes.

Covers widget creation, attribute presence, and theme/language application
for the five history-related page modules:
- DubbingHistoryPage
- ExtractionHistoryPage
- SubtitleHistoryPage
- VoiceHistoryPage
- TranslateDocumentPage (embeds HistoryPage)
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from PySide6.QtWidgets import (
    QLineEdit,
    QMainWindow,
    QPushButton,
    QTableWidget,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def _mock_dubbing_db():
    """Mocks database calls used by DubbingHistoryPage during construction."""
    with (
        patch(
            "src.ui.pages.dubbing_history.get_dubbing_fingerprint",
            return_value=None,
        ),
        patch(
            "src.ui.pages.dubbing_history.get_dubbing_history",
            return_value=[],
        ),
    ):
        yield


@pytest.fixture()
def _mock_extraction_db():
    """Mocks database calls used by ExtractionHistoryPage during construction."""
    with (
        patch(
            "src.ui.pages.extraction_history.get_extraction_fingerprint",
            return_value=None,
        ),
        patch(
            "src.ui.pages.extraction_history.get_extraction_history",
            return_value=[],
        ),
    ):
        yield


@pytest.fixture()
def _mock_subtitle_db():
    """Mocks database calls used by SubtitleHistoryPage during construction."""
    with (
        patch(
            "src.ui.pages.subtitle_history.get_subtitle_fingerprint",
            return_value=None,
        ),
        patch(
            "src.ui.pages.subtitle_history.get_subtitle_history",
            return_value=[],
        ),
    ):
        yield


@pytest.fixture()
def _mock_voice_db():
    """Mocks database calls used by VoiceHistoryPage during construction."""
    with (
        patch(
            "src.ui.pages.voice_history.get_voice_fingerprint",
            return_value=None,
        ),
        patch(
            "src.ui.pages.voice_history.get_voice_history",
            return_value=[],
        ),
    ):
        yield


@pytest.fixture()
def _mock_history_db():
    """Mocks database calls used by HistoryPage (embedded in TranslateDocumentPage)."""
    with (
        patch(
            "src.ui.pages.history.get_history_fingerprint",
            return_value=None,
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


# ===================================================================
# TestDubbingHistoryPage
# ===================================================================


@pytest.mark.usefixtures("_mock_dubbing_db")
class TestDubbingHistoryPage:
    """Tests for DubbingHistoryPage widget construction and attributes."""

    def _create_page(self, qtbot):  # noqa: ANN001, ANN202
        """Helper to create a DubbingHistoryPage widget."""
        from src.ui.pages.dubbing_history import DubbingHistoryPage  # noqa: PLC0415

        page = DubbingHistoryPage()
        qtbot.addWidget(page)
        return page

    def test_construction(self, qtbot) -> None:  # noqa: ANN001
        """DubbingHistoryPage is created without error."""
        page = self._create_page(qtbot)
        assert page is not None

    def test_has_table(self, qtbot) -> None:  # noqa: ANN001
        """Page has a QTableWidget for displaying history."""
        page = self._create_page(qtbot)
        assert hasattr(page, "table")
        assert isinstance(page.table, QTableWidget)

    def test_has_search_input(self, qtbot) -> None:  # noqa: ANN001
        """Page has a QLineEdit for search filtering."""
        page = self._create_page(qtbot)
        assert hasattr(page, "search_input")
        assert isinstance(page.search_input, QLineEdit)

    def test_has_action_buttons(self, qtbot) -> None:  # noqa: ANN001
        """Page has expected action buttons."""
        page = self._create_page(qtbot)
        assert hasattr(page, "open_btn")
        assert isinstance(page.open_btn, QPushButton)
        assert hasattr(page, "pause_btn")
        assert isinstance(page.pause_btn, QPushButton)
        assert hasattr(page, "continue_btn")
        assert isinstance(page.continue_btn, QPushButton)
        assert hasattr(page, "re_dub_btn")
        assert isinstance(page.re_dub_btn, QPushButton)
        assert hasattr(page, "delete_btn")
        assert isinstance(page.delete_btn, QPushButton)

    def test_table_column_count(self, qtbot) -> None:  # noqa: ANN001
        """Table has 5 columns: name, size, status, progress, date."""
        page = self._create_page(qtbot)
        assert page.table.columnCount() == 5  # noqa: PLR2004

    def test_apply_theme_no_error(self, qtbot) -> None:  # noqa: ANN001
        """apply_theme() runs without raising."""
        page = self._create_page(qtbot)
        page.apply_theme()

    def test_apply_language_no_error(self, qtbot) -> None:  # noqa: ANN001
        """apply_language() runs without raising."""
        page = self._create_page(qtbot)
        page.apply_language()

    def test_error_frame_hidden_initially(self, qtbot) -> None:  # noqa: ANN001
        """Error banner is hidden at construction time."""
        page = self._create_page(qtbot)
        assert hasattr(page, "error_frame")
        assert not page.error_frame.isVisible()

    def test_buttons_disabled_initially(self, qtbot) -> None:  # noqa: ANN001
        """Action buttons start disabled (no selection)."""
        page = self._create_page(qtbot)
        assert not page.open_btn.isEnabled()
        assert not page.pause_btn.isEnabled()
        assert not page.delete_btn.isEnabled()


# ===================================================================
# TestExtractionHistoryPage
# ===================================================================


@pytest.mark.usefixtures("_mock_extraction_db")
class TestExtractionHistoryPage:
    """Tests for ExtractionHistoryPage widget construction and attributes."""

    def _create_page(self, qtbot):  # noqa: ANN001, ANN202
        """Helper to create an ExtractionHistoryPage widget."""
        from src.ui.pages.extraction_history import (  # noqa: PLC0415
            ExtractionHistoryPage,
        )

        page = ExtractionHistoryPage()
        qtbot.addWidget(page)
        return page

    def test_construction(self, qtbot) -> None:  # noqa: ANN001
        """ExtractionHistoryPage is created without error."""
        page = self._create_page(qtbot)
        assert page is not None

    def test_has_table(self, qtbot) -> None:  # noqa: ANN001
        """Page has a QTableWidget for displaying history."""
        page = self._create_page(qtbot)
        assert hasattr(page, "table")
        assert isinstance(page.table, QTableWidget)

    def test_has_search_input(self, qtbot) -> None:  # noqa: ANN001
        """Page has a QLineEdit for search filtering."""
        page = self._create_page(qtbot)
        assert hasattr(page, "search_input")
        assert isinstance(page.search_input, QLineEdit)

    def test_has_action_buttons(self, qtbot) -> None:  # noqa: ANN001
        """Page has expected action buttons (open, re-extract, delete)."""
        page = self._create_page(qtbot)
        assert hasattr(page, "open_btn")
        assert isinstance(page.open_btn, QPushButton)
        assert hasattr(page, "re_extract_btn")
        assert isinstance(page.re_extract_btn, QPushButton)
        assert hasattr(page, "delete_btn")
        assert isinstance(page.delete_btn, QPushButton)

    def test_table_column_count(self, qtbot) -> None:  # noqa: ANN001
        """Table has the expected number of columns (4: name, size, status, date)."""
        page = self._create_page(qtbot)
        assert page.table.columnCount() == 4  # noqa: PLR2004

    def test_apply_theme_no_error(self, qtbot) -> None:  # noqa: ANN001
        """apply_theme() runs without raising."""
        page = self._create_page(qtbot)
        page.apply_theme()

    def test_apply_language_no_error(self, qtbot) -> None:  # noqa: ANN001
        """apply_language() runs without raising."""
        page = self._create_page(qtbot)
        page.apply_language()

    def test_error_frame_hidden_initially(self, qtbot) -> None:  # noqa: ANN001
        """Error banner is hidden at construction time."""
        page = self._create_page(qtbot)
        assert hasattr(page, "error_frame")
        assert not page.error_frame.isVisible()

    def test_buttons_disabled_initially(self, qtbot) -> None:  # noqa: ANN001
        """Action buttons start disabled (no selection)."""
        page = self._create_page(qtbot)
        assert not page.open_btn.isEnabled()
        assert not page.re_extract_btn.isEnabled()
        assert not page.delete_btn.isEnabled()


# ===================================================================
# TestSubtitleHistoryPage
# ===================================================================


@pytest.mark.usefixtures("_mock_subtitle_db")
class TestSubtitleHistoryPage:
    """Tests for SubtitleHistoryPage widget construction and attributes."""

    def _create_page(self, qtbot):  # noqa: ANN001, ANN202
        """Helper to create a SubtitleHistoryPage widget."""
        from src.ui.pages.subtitle_history import SubtitleHistoryPage  # noqa: PLC0415

        page = SubtitleHistoryPage()
        qtbot.addWidget(page)
        return page

    def test_construction(self, qtbot) -> None:  # noqa: ANN001
        """SubtitleHistoryPage is created without error."""
        page = self._create_page(qtbot)
        assert page is not None

    def test_has_table(self, qtbot) -> None:  # noqa: ANN001
        """Page has a QTableWidget for displaying history."""
        page = self._create_page(qtbot)
        assert hasattr(page, "table")
        assert isinstance(page.table, QTableWidget)

    def test_has_search_input(self, qtbot) -> None:  # noqa: ANN001
        """Page has a QLineEdit for search filtering."""
        page = self._create_page(qtbot)
        assert hasattr(page, "search_input")
        assert isinstance(page.search_input, QLineEdit)

    def test_has_action_buttons(self, qtbot) -> None:  # noqa: ANN001
        """Page has expected action buttons (open, re-generate, delete)."""
        page = self._create_page(qtbot)
        assert hasattr(page, "open_btn")
        assert isinstance(page.open_btn, QPushButton)
        assert hasattr(page, "re_generate_btn")
        assert isinstance(page.re_generate_btn, QPushButton)
        assert hasattr(page, "delete_btn")
        assert isinstance(page.delete_btn, QPushButton)

    def test_table_column_count(self, qtbot) -> None:  # noqa: ANN001
        """Table has the expected number of columns (4: name, size, status, date)."""
        page = self._create_page(qtbot)
        assert page.table.columnCount() == 4  # noqa: PLR2004

    def test_apply_theme_no_error(self, qtbot) -> None:  # noqa: ANN001
        """apply_theme() runs without raising."""
        page = self._create_page(qtbot)
        page.apply_theme()

    def test_apply_language_no_error(self, qtbot) -> None:  # noqa: ANN001
        """apply_language() runs without raising."""
        page = self._create_page(qtbot)
        page.apply_language()

    def test_error_frame_hidden_initially(self, qtbot) -> None:  # noqa: ANN001
        """Error banner is hidden at construction time."""
        page = self._create_page(qtbot)
        assert hasattr(page, "error_frame")
        assert not page.error_frame.isVisible()

    def test_buttons_disabled_initially(self, qtbot) -> None:  # noqa: ANN001
        """Action buttons start disabled (no selection)."""
        page = self._create_page(qtbot)
        assert not page.open_btn.isEnabled()
        assert not page.re_generate_btn.isEnabled()
        assert not page.delete_btn.isEnabled()


# ===================================================================
# TestVoiceHistoryPage
# ===================================================================


@pytest.mark.usefixtures("_mock_voice_db")
class TestVoiceHistoryPage:
    """Tests for VoiceHistoryPage widget construction and attributes."""

    def _create_page(self, qtbot):  # noqa: ANN001, ANN202
        """Helper to create a VoiceHistoryPage widget."""
        from src.ui.pages.voice_history import VoiceHistoryPage  # noqa: PLC0415

        page = VoiceHistoryPage()
        qtbot.addWidget(page)
        return page

    def test_construction(self, qtbot) -> None:  # noqa: ANN001
        """VoiceHistoryPage is created without error."""
        page = self._create_page(qtbot)
        assert page is not None

    def test_has_table(self, qtbot) -> None:  # noqa: ANN001
        """Page has a QTableWidget for displaying history."""
        page = self._create_page(qtbot)
        assert hasattr(page, "table")
        assert isinstance(page.table, QTableWidget)

    def test_has_search_input(self, qtbot) -> None:  # noqa: ANN001
        """Page has a QLineEdit for search filtering."""
        page = self._create_page(qtbot)
        assert hasattr(page, "search_input")
        assert isinstance(page.search_input, QLineEdit)

    def test_has_action_buttons(self, qtbot) -> None:  # noqa: ANN001
        """Page has expected action buttons (open, re-generate, delete)."""
        page = self._create_page(qtbot)
        assert hasattr(page, "open_btn")
        assert isinstance(page.open_btn, QPushButton)
        assert hasattr(page, "re_generate_btn")
        assert isinstance(page.re_generate_btn, QPushButton)
        assert hasattr(page, "delete_btn")
        assert isinstance(page.delete_btn, QPushButton)

    def test_table_column_count(self, qtbot) -> None:  # noqa: ANN001
        """Table has the expected number of columns (4: name, size, status, date)."""
        page = self._create_page(qtbot)
        assert page.table.columnCount() == 4  # noqa: PLR2004

    def test_apply_theme_no_error(self, qtbot) -> None:  # noqa: ANN001
        """apply_theme() runs without raising."""
        page = self._create_page(qtbot)
        page.apply_theme()

    def test_apply_language_no_error(self, qtbot) -> None:  # noqa: ANN001
        """apply_language() runs without raising."""
        page = self._create_page(qtbot)
        page.apply_language()

    def test_error_frame_hidden_initially(self, qtbot) -> None:  # noqa: ANN001
        """Error banner is hidden at construction time."""
        page = self._create_page(qtbot)
        assert hasattr(page, "error_frame")
        assert not page.error_frame.isVisible()

    def test_buttons_disabled_initially(self, qtbot) -> None:  # noqa: ANN001
        """Action buttons start disabled (no selection)."""
        page = self._create_page(qtbot)
        assert not page.open_btn.isEnabled()
        assert not page.re_generate_btn.isEnabled()
        assert not page.delete_btn.isEnabled()


# ===================================================================
# TestTranslateDocumentPage
# ===================================================================


@pytest.mark.usefixtures("_mock_history_db")
class TestTranslateDocumentPage:
    """Tests for TranslateDocumentPage widget construction and attributes."""

    def _create_page(self, qtbot):  # noqa: ANN001, ANN202
        """Helper to create a TranslateDocumentPage widget."""
        from src.ui.pages.translate_document import (  # noqa: PLC0415
            TranslateDocumentPage,
        )

        window = QMainWindow()
        qtbot.addWidget(window)
        page = TranslateDocumentPage(window)
        qtbot.addWidget(page)
        return page

    def test_construction(self, qtbot) -> None:  # noqa: ANN001
        """TranslateDocumentPage is created without error."""
        page = self._create_page(qtbot)
        assert page is not None

    def test_has_stack_widget(self, qtbot) -> None:  # noqa: ANN001
        """Page has a QStackedWidget for switching between views."""
        page = self._create_page(qtbot)
        assert hasattr(page, "stack")

    def test_has_drop_area(self, qtbot) -> None:  # noqa: ANN001
        """Page has a FileDropWidget for file selection."""
        page = self._create_page(qtbot)
        assert hasattr(page, "drop_area")

    def test_has_history_view(self, qtbot) -> None:  # noqa: ANN001
        """Page embeds a HistoryPage for displaying translation history."""
        page = self._create_page(qtbot)
        assert hasattr(page, "history_view")

    def test_has_translate_button(self, qtbot) -> None:  # noqa: ANN001
        """Page has a translate button."""
        page = self._create_page(qtbot)
        assert hasattr(page, "translate_btn")
        assert isinstance(page.translate_btn, QPushButton)

    def test_has_clear_all_button(self, qtbot) -> None:  # noqa: ANN001
        """Page has a clear-all button."""
        page = self._create_page(qtbot)
        assert hasattr(page, "clear_all_btn")
        assert isinstance(page.clear_all_btn, QPushButton)

    def test_selected_files_empty_initially(self, qtbot) -> None:  # noqa: ANN001
        """No files are selected at construction time."""
        page = self._create_page(qtbot)
        assert page.selected_files == []

    def test_factory_function(self, qtbot) -> None:  # noqa: ANN001
        """create_translate_document_page() returns a valid widget."""
        from src.ui.pages.translate_document import (  # noqa: PLC0415
            create_translate_document_page,
        )

        window = QMainWindow()
        qtbot.addWidget(window)
        page = create_translate_document_page(window)
        qtbot.addWidget(page)
        assert page is not None

    def test_apply_theme_no_error(self, qtbot) -> None:  # noqa: ANN001
        """apply_theme() runs without raising."""
        page = self._create_page(qtbot)
        page.apply_theme()

    def test_apply_language_no_error(self, qtbot) -> None:  # noqa: ANN001
        """apply_language() runs without raising."""
        page = self._create_page(qtbot)
        page.apply_language()
