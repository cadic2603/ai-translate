"""Unit tests for the main window module (src/ui/window.py).

Covers sidebar creation, main window construction, page navigation
(sidebar click -> correct page shown), theme propagation, language
propagation, keyboard shortcuts, and helper functions.
"""

from __future__ import annotations

from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QEvent
from PySide6.QtGui import QShortcut
from PySide6.QtWidgets import (
    QDialog,
    QListWidget,
    QMainWindow,
    QStackedWidget,
    QWidget,
)
from pytestqt.qtbot import QtBot

from src.ui.window import (
    _SIDEBAR_KEYS,
    PAGE_ABOUT,
    PAGE_DUBBING,
    PAGE_EXTRACT_TEXT,
    PAGE_GLOSSARY,
    PAGE_LIVE,
    PAGE_SETTINGS,
    PAGE_SUBTITLE,
    PAGE_TRANSLATE,
    PAGE_TRANSLATE_TEXT,
    PAGE_VOICE,
    create_sidebar,
)

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------
_MOD = "src.ui.window"

# All page factory patch targets
_PAGE_FACTORIES = {
    f"{_MOD}.create_translate_text_page",
    f"{_MOD}.create_translate_document_page",
    f"{_MOD}.create_subtitle_page",
    f"{_MOD}.create_voice_page",
    f"{_MOD}.create_dubbing_page",
    f"{_MOD}.create_live_page",
    f"{_MOD}.create_extract_text_page",
    f"{_MOD}.create_glossary_page",
    f"{_MOD}.create_settings_page",
    f"{_MOD}.create_about_page",
}

# All DB activity check targets
_DB_ACTIVITY_CHECKS = {
    f"{_MOD}.is_any_translating": lambda: False,
    f"{_MOD}.is_any_extracting": lambda: False,
    f"{_MOD}.is_any_subtitle_generating": lambda: False,
    f"{_MOD}.is_any_voice_generating": lambda: False,
    f"{_MOD}.is_any_dubbing_generating": lambda: False,
}

# Worker class targets
_WORKER_CLASSES = [
    f"{_MOD}.TranslationWorker",
    f"{_MOD}._ExtractionWorker",
    f"{_MOD}._SubtitleWorker",
    f"{_MOD}._VoiceWorker",
    f"{_MOD}._DubbingWorker",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_widget(*_args: object, **_kwargs: object) -> QWidget:
    """Factory that creates a fresh QWidget (safe to call after QApp init)."""
    return QWidget()


def _make_themed_widget(*_args: object, **_kwargs: object) -> QWidget:
    """Factory that creates a widget with apply_theme and apply_language."""
    w = QWidget()
    w.apply_theme = MagicMock()
    w.apply_language = MagicMock()
    return w


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def main_window(qtbot):
    """Creates a main window with all page factories mocked.

    Forces the window wide (1400 px) so the sidebar starts in its
    expanded state (`SIDEBAR_WIDTH = 275`).  ``create_main_window``
    calls ``showMaximized()`` last, but the offscreen Qt platform
    sometimes reports a screen size below the collapse threshold
    (1100 px), which would auto-shrink the sidebar to
    ``SIDEBAR_COLLAPSED_WIDTH = 80`` and break tests that assert the
    expanded width.  Explicit ``resize`` + ``processEvents`` makes the
    resize hysteresis fire before any assertion runs.
    """
    worker_mock = MagicMock()
    worker_mock.is_busy.return_value = False

    with ExitStack() as stack:
        # Patch page factories
        for target in _PAGE_FACTORIES:
            stack.enter_context(patch(target, side_effect=_make_widget))
        # Patch DB activity checks
        for target, replacement in _DB_ACTIVITY_CHECKS.items():
            stack.enter_context(patch(target, side_effect=replacement))
        # Patch worker classes
        for target in _WORKER_CLASSES:
            stack.enter_context(patch(target, worker_mock))

        from PySide6.QtWidgets import QApplication  # noqa: PLC0415

        from src.ui.window import create_main_window  # noqa: PLC0415

        window = create_main_window()
        qtbot.addWidget(window)

        # Pin geometry above the sidebar-expand hysteresis threshold so
        # tests see the expanded sidebar regardless of the offscreen
        # platform's reported screen size.  ``window.resize(...)`` alone
        # is unreliable under ``--forked`` because the platform's
        # initial smaller size may have already collapsed the sidebar
        # via a resize event before our resize fires, and an unshown
        # window may swallow the follow-up event entirely.  Synthesising
        # the ``QResizeEvent`` and dispatching it directly to
        # ``window.resizeEvent`` mirrors what ``_trigger_resize`` does
        # in the tests and works deterministically in both plain and
        # forked runs.
        from PySide6.QtCore import QSize  # noqa: PLC0415
        from PySide6.QtGui import QResizeEvent  # noqa: PLC0415

        window.resize(1400, 900)
        window.resizeEvent(QResizeEvent(QSize(1400, 900), window.size()))
        app = QApplication.instance()
        if app is not None:
            app.processEvents()

        yield window


# ===================================================================
# Sidebar Creation
# ===================================================================


class TestCreateSidebar:
    """Tests for create_sidebar function."""

    def test_returns_widget_with_nav_list(self, qtbot: QtBot) -> None:
        """create_sidebar() returns a QWidget with a QListWidget."""
        stacked = QStackedWidget()
        qtbot.addWidget(stacked)
        sidebar = create_sidebar(stacked)
        qtbot.addWidget(sidebar)

        nav_list = sidebar.findChild(QListWidget, "sidebar")
        assert nav_list is not None

    def test_item_count_matches_sidebar_keys(self, qtbot: QtBot) -> None:
        """Sidebar nav list has exactly one item per _SIDEBAR_KEYS entry."""
        stacked = QStackedWidget()
        qtbot.addWidget(stacked)
        sidebar = create_sidebar(stacked)
        qtbot.addWidget(sidebar)

        nav_list = sidebar.findChild(QListWidget, "sidebar")
        assert nav_list.count() == len(_SIDEBAR_KEYS)  # noqa: PLR2004

    def test_ten_sidebar_items(self, qtbot: QtBot) -> None:
        """Sidebar has exactly 10 items."""
        stacked = QStackedWidget()
        qtbot.addWidget(stacked)
        sidebar = create_sidebar(stacked)
        qtbot.addWidget(sidebar)

        nav_list = sidebar.findChild(QListWidget, "sidebar")
        assert nav_list.count() == 10  # noqa: PLR2004

    def test_sidebar_initial_selection_is_first(self, qtbot: QtBot) -> None:
        """Sidebar starts with the first item selected."""
        stacked = QStackedWidget()
        qtbot.addWidget(stacked)
        sidebar = create_sidebar(stacked)
        qtbot.addWidget(sidebar)

        nav_list = sidebar.findChild(QListWidget, "sidebar")
        assert nav_list.currentRow() == 0

    def test_sidebar_controls_stacked_widget(self, qtbot: QtBot) -> None:
        """Changing sidebar row updates the stacked widget index."""
        stacked = QStackedWidget()
        for _ in range(10):
            stacked.addWidget(QWidget())
        qtbot.addWidget(stacked)

        sidebar = create_sidebar(stacked)
        qtbot.addWidget(sidebar)

        nav_list = sidebar.findChild(QListWidget, "sidebar")
        nav_list.setCurrentRow(3)
        assert stacked.currentIndex() == 3  # noqa: PLR2004

    def test_sidebar_items_have_text(self, qtbot: QtBot) -> None:
        """All sidebar items have non-empty text."""
        stacked = QStackedWidget()
        qtbot.addWidget(stacked)
        sidebar = create_sidebar(stacked)
        qtbot.addWidget(sidebar)

        nav_list = sidebar.findChild(QListWidget, "sidebar")
        for i in range(nav_list.count()):
            assert nav_list.item(i).text()


# ===================================================================
# Main Window Construction
# ===================================================================


class TestMainWindowConstruction:
    """Tests for create_main_window function."""

    def test_returns_qmainwindow(self, main_window) -> None:  # noqa: ANN001
        """create_main_window() returns a QMainWindow instance."""
        assert isinstance(main_window, QMainWindow)

    def test_has_sidebar(self, main_window) -> None:  # noqa: ANN001
        """Main window contains a sidebar nav list."""
        nav_list = main_window.findChild(QListWidget, "sidebar")
        assert nav_list is not None

    def test_sidebar_has_all_items(self, main_window) -> None:  # noqa: ANN001
        """Sidebar nav list has the expected number of items."""
        nav_list = main_window.findChild(QListWidget, "sidebar")
        assert nav_list.count() == len(_SIDEBAR_KEYS)  # noqa: PLR2004

    def test_has_stacked_widget(self, main_window) -> None:  # noqa: ANN001
        """Main window contains a QStackedWidget for page content."""
        stacked = main_window.findChild(QStackedWidget)
        assert stacked is not None

    def test_stacked_widget_has_ten_pages(self, main_window) -> None:  # noqa: ANN001
        """Stacked widget has 10 pages."""
        stacked = main_window.findChild(QStackedWidget)
        assert stacked.count() == 10  # noqa: PLR2004

    def test_window_has_title(self, main_window) -> None:  # noqa: ANN001
        """Main window has a non-empty title."""
        assert main_window.windowTitle()

    def test_has_switch_to_page(self, main_window) -> None:  # noqa: ANN001
        """Main window has switch_to_page helper."""
        assert hasattr(main_window, "switch_to_page")
        assert callable(main_window.switch_to_page)

    def test_has_navigate_to_settings_tab(self, main_window) -> None:  # noqa: ANN001
        """Main window has navigate_to_settings_tab helper."""
        assert hasattr(main_window, "navigate_to_settings_tab")
        assert callable(main_window.navigate_to_settings_tab)


# ===================================================================
# Page Navigation
# ===================================================================


class TestPageNavigation:
    """Tests that sidebar clicks navigate to the correct page."""

    def test_sidebar_click_switches_page(self, main_window) -> None:  # noqa: ANN001
        """Clicking a sidebar item switches the stacked widget."""
        nav_list = main_window.findChild(QListWidget, "sidebar")
        stacked = main_window.findChild(QStackedWidget)

        nav_list.setCurrentRow(PAGE_SETTINGS)
        assert stacked.currentIndex() == PAGE_SETTINGS

    def test_navigate_all_pages(self, main_window) -> None:  # noqa: ANN001
        """Each sidebar item index maps to the correct stacked page index."""
        nav_list = main_window.findChild(QListWidget, "sidebar")
        stacked = main_window.findChild(QStackedWidget)

        pages = [
            PAGE_TRANSLATE_TEXT,
            PAGE_TRANSLATE,
            PAGE_SUBTITLE,
            PAGE_VOICE,
            PAGE_DUBBING,
            PAGE_LIVE,
            PAGE_EXTRACT_TEXT,
            PAGE_GLOSSARY,
            PAGE_SETTINGS,
            PAGE_ABOUT,
        ]
        for idx in pages:
            nav_list.setCurrentRow(idx)
            assert stacked.currentIndex() == idx

    def test_switch_to_page_helper(self, main_window) -> None:  # noqa: ANN001
        """switch_to_page() programmatically changes the active page."""
        nav_list = main_window.findChild(QListWidget, "sidebar")
        stacked = main_window.findChild(QStackedWidget)

        main_window.switch_to_page(PAGE_GLOSSARY)
        assert nav_list.currentRow() == PAGE_GLOSSARY
        assert stacked.currentIndex() == PAGE_GLOSSARY

    def test_switch_to_page_updates_sidebar_selection(
        self,
        main_window,  # noqa: ANN001
    ) -> None:
        """switch_to_page() updates the sidebar selection to match."""
        nav_list = main_window.findChild(QListWidget, "sidebar")

        main_window.switch_to_page(PAGE_ABOUT)
        assert nav_list.currentRow() == PAGE_ABOUT

        main_window.switch_to_page(PAGE_TRANSLATE_TEXT)
        assert nav_list.currentRow() == PAGE_TRANSLATE_TEXT


# ===================================================================
# Theme Propagation
# ===================================================================


class TestThemePropagation:
    """Tests that theme changes propagate to child widgets."""

    def test_theme_change_calls_apply_theme(self, qtbot: QtBot) -> None:
        """Theme change propagates apply_theme to child pages."""
        worker_mock = MagicMock()
        worker_mock.is_busy.return_value = False

        with ExitStack() as stack:
            for target in _PAGE_FACTORIES:
                stack.enter_context(
                    patch(target, side_effect=_make_themed_widget),
                )
            for target, replacement in _DB_ACTIVITY_CHECKS.items():
                stack.enter_context(patch(target, side_effect=replacement))
            for target in _WORKER_CLASSES:
                stack.enter_context(patch(target, worker_mock))

            from src.ui.window import create_main_window  # noqa: PLC0415

            window = create_main_window()
            qtbot.addWidget(window)

            # Trigger theme change
            from src.constants import theme_changed  # noqa: PLC0415

            theme_changed.emit("dark")

            # At least one child with apply_theme should have been called
            themed_children = [
                c
                for c in window.findChildren(QWidget)
                if hasattr(c, "apply_theme") and callable(c.apply_theme)
            ]
            called = [
                c
                for c in themed_children
                if isinstance(c.apply_theme, MagicMock) and c.apply_theme.call_count > 0
            ]
            assert len(called) > 0


# ===================================================================
# Language Propagation
# ===================================================================


class TestLanguagePropagation:
    """Tests that language changes propagate to child widgets."""

    def test_language_change_calls_apply_language(self, qtbot: QtBot) -> None:
        """Language change propagates apply_language to child pages."""
        worker_mock = MagicMock()
        worker_mock.is_busy.return_value = False

        with ExitStack() as stack:
            for target in _PAGE_FACTORIES:
                stack.enter_context(
                    patch(target, side_effect=_make_themed_widget),
                )
            for target, replacement in _DB_ACTIVITY_CHECKS.items():
                stack.enter_context(patch(target, side_effect=replacement))
            for target in _WORKER_CLASSES:
                stack.enter_context(patch(target, worker_mock))

            from src.ui.window import create_main_window  # noqa: PLC0415

            window = create_main_window()
            qtbot.addWidget(window)

            # Trigger language change
            from src.constants import language_changed  # noqa: PLC0415

            language_changed.emit("vi")

            # At least one child with apply_language should have been called
            lang_children = [
                c
                for c in window.findChildren(QWidget)
                if hasattr(c, "apply_language") and callable(c.apply_language)
            ]
            called = [
                c
                for c in lang_children
                if isinstance(c.apply_language, MagicMock)
                and c.apply_language.call_count > 0
            ]
            assert len(called) > 0

    def test_language_change_updates_sidebar_items(self, qtbot: QtBot) -> None:
        """Language change updates sidebar item texts."""
        worker_mock = MagicMock()
        worker_mock.is_busy.return_value = False

        with ExitStack() as stack:
            for target in _PAGE_FACTORIES:
                stack.enter_context(
                    patch(target, side_effect=_make_widget),
                )
            for target, replacement in _DB_ACTIVITY_CHECKS.items():
                stack.enter_context(patch(target, side_effect=replacement))
            for target in _WORKER_CLASSES:
                stack.enter_context(patch(target, worker_mock))

            from src.ui.window import create_main_window  # noqa: PLC0415

            window = create_main_window()
            qtbot.addWidget(window)

            nav_list = window.findChild(QListWidget, "sidebar")
            # All sidebar items should have non-empty text after language change
            from src.constants import language_changed  # noqa: PLC0415

            language_changed.emit("en-US")

            for i in range(nav_list.count()):
                assert nav_list.item(i).text()

    def test_language_change_updates_window_title(self, qtbot: QtBot) -> None:
        """Language change updates the window title."""
        worker_mock = MagicMock()
        worker_mock.is_busy.return_value = False

        with ExitStack() as stack:
            for target in _PAGE_FACTORIES:
                stack.enter_context(
                    patch(target, side_effect=_make_widget),
                )
            for target, replacement in _DB_ACTIVITY_CHECKS.items():
                stack.enter_context(patch(target, side_effect=replacement))
            for target in _WORKER_CLASSES:
                stack.enter_context(patch(target, worker_mock))

            from src.ui.window import create_main_window  # noqa: PLC0415

            window = create_main_window()
            qtbot.addWidget(window)

            from src.constants import language_changed  # noqa: PLC0415

            language_changed.emit("en-US")

            assert window.windowTitle()


# ===================================================================
# Page Index Constants
# ===================================================================


class TestPageIndexConstants:
    """Tests that page index constants are correctly defined."""

    def test_page_indices_are_sequential(self) -> None:
        """Page index constants are 0 through 9."""
        assert PAGE_TRANSLATE_TEXT == 0
        assert PAGE_TRANSLATE == 1
        assert PAGE_SUBTITLE == 2  # noqa: PLR2004
        assert PAGE_VOICE == 3  # noqa: PLR2004
        assert PAGE_DUBBING == 4  # noqa: PLR2004
        assert PAGE_LIVE == 5  # noqa: PLR2004
        assert PAGE_EXTRACT_TEXT == 6  # noqa: PLR2004
        assert PAGE_GLOSSARY == 7  # noqa: PLR2004
        assert PAGE_SETTINGS == 8  # noqa: PLR2004
        assert PAGE_ABOUT == 9  # noqa: PLR2004

    def test_sidebar_keys_count_matches_pages(self) -> None:
        """Number of sidebar keys matches the number of page constants."""
        assert len(_SIDEBAR_KEYS) == 10  # noqa: PLR2004


# ===================================================================
# Navigate to Settings Tab
# ===================================================================


class TestNavigateToSettingsTab:
    """Tests for navigate_to_settings_tab helper."""

    def test_navigate_to_settings_switches_to_settings_page(
        self,
        main_window,  # noqa: ANN001
    ) -> None:
        """navigate_to_settings_tab switches to the Settings page."""
        stacked = main_window.findChild(QStackedWidget)

        # Start on a different page
        main_window.switch_to_page(PAGE_TRANSLATE_TEXT)
        assert stacked.currentIndex() == PAGE_TRANSLATE_TEXT

        main_window.navigate_to_settings_tab(0)
        nav_list = main_window.findChild(QListWidget, "sidebar")
        assert nav_list.currentRow() == PAGE_SETTINGS


# ===================================================================
# Switch To Page — exhaustive
# ===================================================================


class TestSwitchToPage:
    """Exhaustive tests for the switch_to_page helper."""

    @pytest.mark.parametrize(
        "page_index",
        [
            PAGE_TRANSLATE_TEXT,
            PAGE_TRANSLATE,
            PAGE_SUBTITLE,
            PAGE_VOICE,
            PAGE_DUBBING,
            PAGE_LIVE,
            PAGE_EXTRACT_TEXT,
            PAGE_GLOSSARY,
            PAGE_SETTINGS,
            PAGE_ABOUT,
        ],
    )
    def test_switch_to_each_page(
        self,
        main_window,  # noqa: ANN001
        page_index: int,
    ) -> None:
        """switch_to_page navigates to every valid page index."""
        stacked = main_window.findChild(QStackedWidget)
        main_window.switch_to_page(page_index)
        assert stacked.currentIndex() == page_index

    def test_switch_to_same_page_is_noop(
        self,
        main_window,  # noqa: ANN001
    ) -> None:
        """Switching to the current page doesn't raise or change state."""
        stacked = main_window.findChild(QStackedWidget)
        main_window.switch_to_page(PAGE_GLOSSARY)
        assert stacked.currentIndex() == PAGE_GLOSSARY
        # Switch again — should stay the same without error
        main_window.switch_to_page(PAGE_GLOSSARY)
        assert stacked.currentIndex() == PAGE_GLOSSARY

    def test_switch_to_page_out_of_range(
        self,
        main_window,  # noqa: ANN001
    ) -> None:
        """switch_to_page with out-of-range index doesn't crash."""
        stacked = main_window.findChild(QStackedWidget)
        original = stacked.currentIndex()
        # QListWidget.setCurrentRow(-1) deselects; just verify no crash
        main_window.switch_to_page(99)
        # Current index remains unchanged or goes to -1 (deselected)
        assert stacked.currentIndex() in (original, -1)

    def test_switch_to_page_negative_index(
        self,
        main_window,  # noqa: ANN001
    ) -> None:
        """switch_to_page with negative index doesn't crash."""
        main_window.switch_to_page(PAGE_ABOUT)
        main_window.switch_to_page(-1)
        # Just verify no crash occurred

    def test_switch_to_page_syncs_sidebar_and_stacked(
        self,
        main_window,  # noqa: ANN001
    ) -> None:
        """switch_to_page keeps sidebar row and stacked index in sync."""
        nav_list = main_window.findChild(QListWidget, "sidebar")
        stacked = main_window.findChild(QStackedWidget)

        for idx in [PAGE_LIVE, PAGE_VOICE, PAGE_TRANSLATE_TEXT]:
            main_window.switch_to_page(idx)
            assert nav_list.currentRow() == idx
            assert stacked.currentIndex() == idx


# ===================================================================
# Navigate to Settings Tab — extended
# ===================================================================


class TestNavigateToSettingsTabExtended:
    """Extended tests for navigate_to_settings_tab."""

    def test_navigate_to_settings_tab_calls_switch_to_tab(
        self,
        qtbot: QtBot,
    ) -> None:
        """navigate_to_settings_tab calls switch_to_tab on settings page."""
        worker_mock = MagicMock()
        worker_mock.is_busy.return_value = False

        settings_widget = QWidget()
        settings_widget.switch_to_tab = MagicMock()

        def _settings_factory(*_a: object, **_kw: object) -> QWidget:
            return settings_widget

        with ExitStack() as stack:
            for target in _PAGE_FACTORIES:
                if "settings" in target:
                    stack.enter_context(patch(target, side_effect=_settings_factory))
                else:
                    stack.enter_context(patch(target, side_effect=_make_widget))
            for target, replacement in _DB_ACTIVITY_CHECKS.items():
                stack.enter_context(patch(target, side_effect=replacement))
            for target in _WORKER_CLASSES:
                stack.enter_context(patch(target, worker_mock))

            from src.ui.window import create_main_window  # noqa: PLC0415

            window = create_main_window()
            qtbot.addWidget(window)

            window.navigate_to_settings_tab(3)
            settings_widget.switch_to_tab.assert_called_once_with(3)

    @pytest.mark.parametrize("tab_index", [0, 1, 2, 3, 4, 5, 6, 7, 8, 9])
    def test_navigate_to_settings_tab_indices(
        self,
        main_window,  # noqa: ANN001
        tab_index: int,
    ) -> None:
        """navigate_to_settings_tab works for tab indices 0-9."""
        # The mock settings widget won't have switch_to_tab, so hasattr
        # check skips the call — just verify it navigates without crash.
        stacked = main_window.findChild(QStackedWidget)
        main_window.navigate_to_settings_tab(tab_index)
        assert stacked.currentIndex() == PAGE_SETTINGS

    def test_navigate_to_settings_tab_updates_sidebar(
        self,
        main_window,  # noqa: ANN001
    ) -> None:
        """navigate_to_settings_tab updates sidebar selection to Settings."""
        main_window.switch_to_page(PAGE_TRANSLATE_TEXT)
        main_window.navigate_to_settings_tab(2)

        nav_list = main_window.findChild(QListWidget, "sidebar")
        assert nav_list.currentRow() == PAGE_SETTINGS

    def test_navigate_to_settings_when_already_on_settings(
        self,
        main_window,  # noqa: ANN001
    ) -> None:
        """navigate_to_settings_tab from Settings page doesn't crash."""
        main_window.switch_to_page(PAGE_SETTINGS)
        main_window.navigate_to_settings_tab(0)

        stacked = main_window.findChild(QStackedWidget)
        assert stacked.currentIndex() == PAGE_SETTINGS

    def test_navigate_without_switch_to_tab_attr(
        self,
        main_window,  # noqa: ANN001
    ) -> None:
        """navigate_to_settings_tab handles page without switch_to_tab."""
        stacked = main_window.findChild(QStackedWidget)
        settings_page = stacked.widget(PAGE_SETTINGS)
        # Verify the mock page lacks switch_to_tab (default _make_widget)
        assert not hasattr(settings_page, "switch_to_tab")
        # Should not raise
        main_window.navigate_to_settings_tab(5)


# ===================================================================
# Sidebar Styling
# ===================================================================


class TestSidebarStyling:
    """Tests for sidebar visual properties."""

    def test_sidebar_has_correct_cursor(self, qtbot: QtBot) -> None:
        """Sidebar nav list has PointingHandCursor."""
        from PySide6.QtCore import Qt  # noqa: PLC0415

        stacked = QStackedWidget()
        qtbot.addWidget(stacked)
        sidebar = create_sidebar(stacked)
        qtbot.addWidget(sidebar)

        nav_list = sidebar.findChild(QListWidget, "sidebar")
        assert nav_list.cursor().shape() == Qt.CursorShape.PointingHandCursor

    def test_sidebar_has_correct_width(self, qtbot: QtBot) -> None:
        """Sidebar container has fixed width matching SIDEBAR_WIDTH."""
        from src.constants import SIDEBAR_WIDTH  # noqa: PLC0415

        stacked = QStackedWidget()
        qtbot.addWidget(stacked)
        sidebar = create_sidebar(stacked)
        qtbot.addWidget(sidebar)

        assert sidebar.maximumWidth() == SIDEBAR_WIDTH
        assert sidebar.minimumWidth() == SIDEBAR_WIDTH

    def test_sidebar_nav_list_object_name(self, qtbot: QtBot) -> None:
        """Sidebar nav list has objectName 'sidebar'."""
        stacked = QStackedWidget()
        qtbot.addWidget(stacked)
        sidebar = create_sidebar(stacked)
        qtbot.addWidget(sidebar)

        nav_list = sidebar.findChild(QListWidget, "sidebar")
        assert nav_list.objectName() == "sidebar"

    def test_sidebar_has_stylesheet(self, qtbot: QtBot) -> None:
        """Sidebar container has a non-empty stylesheet."""
        stacked = QStackedWidget()
        qtbot.addWidget(stacked)
        sidebar = create_sidebar(stacked)
        qtbot.addWidget(sidebar)

        assert sidebar.styleSheet()


# ===================================================================
# Keyboard Shortcuts
# ===================================================================


class TestKeyboardShortcuts:
    """Tests for keyboard shortcuts registered on the main window."""

    def test_ctrl_q_shortcut_exists(
        self,
        main_window,  # noqa: ANN001
    ) -> None:
        """Main window has a Ctrl+Q shortcut."""
        shortcuts = main_window.findChildren(QShortcut)
        keys = [s.key().toString() for s in shortcuts]
        assert "Ctrl+Q" in keys

    def test_ctrl_o_shortcut_exists(
        self,
        main_window,  # noqa: ANN001
    ) -> None:
        """Main window has a Ctrl+O shortcut for browse."""
        shortcuts = main_window.findChildren(QShortcut)
        keys = [s.key().toString() for s in shortcuts]
        assert "Ctrl+O" in keys

    def test_refresh_shortcut_removed(
        self,
        main_window,  # noqa: ANN001
    ) -> None:
        """Ctrl+R is no longer wired on the window (freed up for glossary rename)."""
        shortcuts = main_window.findChildren(QShortcut)
        keys = [s.key().toString() for s in shortcuts]
        assert "Ctrl+R" not in keys

    def test_delete_shortcut_exists(
        self,
        main_window,  # noqa: ANN001
    ) -> None:
        """Main window has a Delete shortcut."""
        shortcuts = main_window.findChildren(QShortcut)
        keys = [s.key().toString() for s in shortcuts]
        assert "Del" in keys or "Delete" in keys

    def test_no_fkey_sidebar_shortcuts(
        self,
        main_window,  # noqa: ANN001
    ) -> None:
        """Main window must not hardcode F1..F11 to sidebar navigation.

        F-keys collide with universal OS conventions (F1=Help,
        F5=Refresh, F11=Fullscreen).  Function-key bindings belong in
        the user-editable shortcut registry where conflict detection
        applies; this test guards against re-introducing a silent
        hardcoded grab on the main window.
        """
        shortcuts = main_window.findChildren(QShortcut)
        keys = [s.key().toString() for s in shortcuts]
        for n in range(1, 12):
            assert f"F{n}" not in keys, (
                f"F{n} must not be wired on the main window — bind "
                "F-keys through the shortcut registry instead."
            )


# ===================================================================
# Window Attributes
# ===================================================================


class TestWindowAttributes:
    """Tests for main window structural attributes."""

    def test_window_has_minimum_size(
        self,
        main_window,  # noqa: ANN001
    ) -> None:
        """Main window has minimum size matching constants."""
        from src.constants import MIN_WINDOW_HEIGHT, MIN_WINDOW_WIDTH  # noqa: PLC0415

        assert main_window.minimumWidth() == MIN_WINDOW_WIDTH
        assert main_window.minimumHeight() == MIN_WINDOW_HEIGHT

    def test_window_has_central_widget(
        self,
        main_window,  # noqa: ANN001
    ) -> None:
        """Main window has a central widget."""
        assert main_window.centralWidget() is not None

    def test_window_has_scrollbar_stylesheet(
        self,
        main_window,  # noqa: ANN001
    ) -> None:
        """Main window has a non-empty stylesheet (scrollbar styles)."""
        assert main_window.styleSheet()

    def test_stacked_widget_has_stylesheet(
        self,
        main_window,  # noqa: ANN001
    ) -> None:
        """Stacked widget has background and text color stylesheet."""
        stacked = main_window.findChild(QStackedWidget)
        assert "background-color" in stacked.styleSheet()
        assert "color" in stacked.styleSheet()

    def test_switch_to_page_is_callable(
        self,
        main_window,  # noqa: ANN001
    ) -> None:
        """switch_to_page attribute is callable."""
        assert callable(main_window.switch_to_page)

    def test_navigate_to_settings_tab_is_callable(
        self,
        main_window,  # noqa: ANN001
    ) -> None:
        """navigate_to_settings_tab attribute is callable."""
        assert callable(main_window.navigate_to_settings_tab)


# ===================================================================
# Multiple Theme / Language Changes
# ===================================================================


class TestMultipleThemeLanguageChanges:
    """Tests for rapid successive theme and language changes."""

    def test_rapid_theme_changes_no_crash(self, qtbot: QtBot) -> None:
        """Multiple rapid theme changes don't crash."""
        worker_mock = MagicMock()
        worker_mock.is_busy.return_value = False

        with ExitStack() as stack:
            for target in _PAGE_FACTORIES:
                stack.enter_context(
                    patch(target, side_effect=_make_themed_widget),
                )
            for target, replacement in _DB_ACTIVITY_CHECKS.items():
                stack.enter_context(patch(target, side_effect=replacement))
            for target in _WORKER_CLASSES:
                stack.enter_context(patch(target, worker_mock))

            from src.ui.window import create_main_window  # noqa: PLC0415

            window = create_main_window()
            qtbot.addWidget(window)

            from src.constants import theme_changed  # noqa: PLC0415

            for name in ["dark", "light", "dark", "light", "dark"]:
                theme_changed.emit(name)

            # Window should still be functional
            assert window.windowTitle()

    def test_rapid_language_changes_no_crash(self, qtbot: QtBot) -> None:
        """Multiple rapid language changes don't crash."""
        worker_mock = MagicMock()
        worker_mock.is_busy.return_value = False

        with ExitStack() as stack:
            for target in _PAGE_FACTORIES:
                stack.enter_context(
                    patch(target, side_effect=_make_themed_widget),
                )
            for target, replacement in _DB_ACTIVITY_CHECKS.items():
                stack.enter_context(patch(target, side_effect=replacement))
            for target in _WORKER_CLASSES:
                stack.enter_context(patch(target, worker_mock))

            from src.ui.window import create_main_window  # noqa: PLC0415

            window = create_main_window()
            qtbot.addWidget(window)

            from src.constants import language_changed  # noqa: PLC0415

            for code in ["en-US", "vi", "en-UK", "en-US", "vi"]:
                language_changed.emit(code)

            assert window.windowTitle()
            nav_list = window.findChild(QListWidget, "sidebar")
            for i in range(nav_list.count()):
                assert nav_list.item(i).text()

    def test_theme_then_language_sequence(self, qtbot: QtBot) -> None:
        """Theme change followed by language change works correctly."""
        worker_mock = MagicMock()
        worker_mock.is_busy.return_value = False

        with ExitStack() as stack:
            for target in _PAGE_FACTORIES:
                stack.enter_context(
                    patch(target, side_effect=_make_themed_widget),
                )
            for target, replacement in _DB_ACTIVITY_CHECKS.items():
                stack.enter_context(patch(target, side_effect=replacement))
            for target in _WORKER_CLASSES:
                stack.enter_context(patch(target, worker_mock))

            from src.ui.window import create_main_window  # noqa: PLC0415

            window = create_main_window()
            qtbot.addWidget(window)

            from src.constants import language_changed, theme_changed  # noqa: PLC0415

            theme_changed.emit("dark")
            language_changed.emit("vi")
            theme_changed.emit("light")
            language_changed.emit("en-US")

            assert window.windowTitle()

    def test_language_then_theme_sequence(self, qtbot: QtBot) -> None:
        """Language change followed by theme change works correctly."""
        worker_mock = MagicMock()
        worker_mock.is_busy.return_value = False

        with ExitStack() as stack:
            for target in _PAGE_FACTORIES:
                stack.enter_context(
                    patch(target, side_effect=_make_themed_widget),
                )
            for target, replacement in _DB_ACTIVITY_CHECKS.items():
                stack.enter_context(patch(target, side_effect=replacement))
            for target in _WORKER_CLASSES:
                stack.enter_context(patch(target, worker_mock))

            from src.ui.window import create_main_window  # noqa: PLC0415

            window = create_main_window()
            qtbot.addWidget(window)

            from src.constants import language_changed, theme_changed  # noqa: PLC0415

            language_changed.emit("en-US")
            theme_changed.emit("dark")

            # Verify both propagated
            themed_children = [
                c
                for c in window.findChildren(QWidget)
                if hasattr(c, "apply_theme") and isinstance(c.apply_theme, MagicMock)
            ]
            for child in themed_children:
                assert child.apply_theme.call_count >= 1


# ===================================================================
# Spinner / Status Timer
# ===================================================================


class TestSpinnerTimer:
    """Tests for the sidebar spinner animation timer."""

    def test_status_timer_exists(
        self,
        main_window,  # noqa: ANN001
    ) -> None:
        """Main window has a QTimer for sidebar status updates."""
        from PySide6.QtCore import QTimer  # noqa: PLC0415

        timers = main_window.findChildren(QTimer)
        assert len(timers) > 0

    def test_status_timer_is_active(
        self,
        main_window,  # noqa: ANN001
    ) -> None:
        """The status timer is actively running."""
        from PySide6.QtCore import QTimer  # noqa: PLC0415

        timers = main_window.findChildren(QTimer)
        active_timers = [t for t in timers if t.isActive()]
        assert len(active_timers) > 0

    def test_status_timer_interval(
        self,
        main_window,  # noqa: ANN001
    ) -> None:
        """The status timer has 100ms interval."""
        from PySide6.QtCore import QTimer  # noqa: PLC0415

        timers = main_window.findChildren(QTimer)
        intervals = [t.interval() for t in timers if t.isActive()]
        assert 100 in intervals  # noqa: PLR2004

    def test_sidebar_no_spinner_when_idle(
        self,
        main_window,  # noqa: ANN001
    ) -> None:
        """Sidebar items have no spinner frames when workers are idle."""
        nav_list = main_window.findChild(QListWidget, "sidebar")
        spinner_frames = {"⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"}
        for i in range(nav_list.count()):
            text = nav_list.item(i).text()
            for frame in spinner_frames:
                assert frame not in text


# ===================================================================
# Change Event — Modal Dialog Raising
# ===================================================================


class TestChangeEvent:
    """Tests for the custom changeEvent that raises modal dialogs."""

    def test_change_event_is_overridden(
        self,
        main_window,  # noqa: ANN001
    ) -> None:
        """Main window has an overridden changeEvent."""
        assert hasattr(main_window, "changeEvent")
        assert callable(main_window.changeEvent)

    def test_change_event_non_activation_no_crash(
        self,
        main_window,  # noqa: ANN001
    ) -> None:
        """Non-activation change events are handled without crash."""
        event = QEvent(QEvent.Type.FontChange)
        main_window.changeEvent(event)
        # Should not raise

    def test_change_event_activation_without_modal(
        self,
        main_window,  # noqa: ANN001
    ) -> None:
        """Activation change without modal dialog doesn't crash."""
        event = QEvent(QEvent.Type.ActivationChange)
        with (
            patch.object(type(main_window), "isActiveWindow", return_value=True),
            patch(
                f"{_MOD}.QApplication.activeModalWidget",
                return_value=None,
            ),
        ):
            main_window.changeEvent(event)

    def test_change_event_activation_with_modal_dialog(
        self,
        main_window,  # noqa: ANN001
    ) -> None:
        """Activation change with modal dialog calls raise_ and activateWindow."""
        mock_dialog = MagicMock(spec=QDialog)
        event = QEvent(QEvent.Type.ActivationChange)

        with (
            patch.object(type(main_window), "isActiveWindow", return_value=True),
            patch(
                f"{_MOD}.QApplication.activeModalWidget",
                return_value=mock_dialog,
            ),
        ):
            main_window.changeEvent(event)
            mock_dialog.raise_.assert_called_once()
            mock_dialog.activateWindow.assert_called_once()


# ===================================================================
# Sidebar Controls Stacked Widget — extended
# ===================================================================


class TestSidebarStackedSync:
    """Extended tests for sidebar-stacked widget synchronization."""

    def test_sidebar_row_change_updates_stacked(
        self,
        main_window,  # noqa: ANN001
    ) -> None:
        """Changing sidebar row directly updates stacked widget."""
        nav_list = main_window.findChild(QListWidget, "sidebar")
        stacked = main_window.findChild(QStackedWidget)

        for idx in [PAGE_ABOUT, PAGE_LIVE, PAGE_TRANSLATE]:
            nav_list.setCurrentRow(idx)
            assert stacked.currentIndex() == idx

    def test_stacked_widget_pages_are_widgets(
        self,
        main_window,  # noqa: ANN001
    ) -> None:
        """All 10 stacked widget pages are QWidget instances."""
        stacked = main_window.findChild(QStackedWidget)
        for i in range(stacked.count()):
            assert isinstance(stacked.widget(i), QWidget)

    def test_sidebar_selection_preserved_after_page_interaction(
        self,
        main_window,  # noqa: ANN001
    ) -> None:
        """Sidebar selection stays consistent after multiple switches."""
        nav_list = main_window.findChild(QListWidget, "sidebar")

        main_window.switch_to_page(PAGE_DUBBING)
        main_window.switch_to_page(PAGE_VOICE)
        main_window.switch_to_page(PAGE_EXTRACT_TEXT)

        assert nav_list.currentRow() == PAGE_EXTRACT_TEXT


# ===================================================================
# Sidebar Container Layout
# ===================================================================


class TestSidebarContainerLayout:
    """Tests for sidebar container layout properties."""

    def test_sidebar_layout_no_margins(self, qtbot: QtBot) -> None:
        """Sidebar container layout has zero margins."""
        stacked = QStackedWidget()
        qtbot.addWidget(stacked)
        sidebar = create_sidebar(stacked)
        qtbot.addWidget(sidebar)

        layout = sidebar.layout()
        margins = layout.contentsMargins()
        assert margins.left() == 0
        assert margins.right() == 0
        assert margins.top() == 0
        assert margins.bottom() == 0

    def test_sidebar_layout_no_spacing(self, qtbot: QtBot) -> None:
        """Sidebar container layout has zero spacing."""
        stacked = QStackedWidget()
        qtbot.addWidget(stacked)
        sidebar = create_sidebar(stacked)
        qtbot.addWidget(sidebar)

        layout = sidebar.layout()
        assert layout.spacing() == 0

    def test_sidebar_nav_list_has_stylesheet(self, qtbot: QtBot) -> None:
        """Sidebar nav list has a non-empty stylesheet."""
        stacked = QStackedWidget()
        qtbot.addWidget(stacked)
        sidebar = create_sidebar(stacked)
        qtbot.addWidget(sidebar)

        nav_list = sidebar.findChild(QListWidget, "sidebar")
        assert nav_list.styleSheet()


# ===================================================================
# Main Window Layout
# ===================================================================


class TestMainWindowLayout:
    """Tests for main window layout structure."""

    def test_central_widget_layout_no_margins(
        self,
        main_window,  # noqa: ANN001
    ) -> None:
        """Central widget layout has zero margins."""
        layout = main_window.centralWidget().layout()
        margins = layout.contentsMargins()
        assert margins.left() == 0
        assert margins.right() == 0
        assert margins.top() == 0
        assert margins.bottom() == 0

    def test_central_widget_layout_no_spacing(
        self,
        main_window,  # noqa: ANN001
    ) -> None:
        """Central widget layout has zero spacing."""
        layout = main_window.centralWidget().layout()
        assert layout.spacing() == 0


# ===================================================================
# NEW: Page navigation — all sidebar items
# ===================================================================


class TestPageNavigationAllItems:
    """Tests for navigating to every page via sidebar."""

    @pytest.mark.parametrize(
        "page_index, key",
        list(enumerate(_SIDEBAR_KEYS)),
    )
    def test_sidebar_item_navigates_to_page(
        self,
        main_window,  # noqa: ANN001
        page_index: int,
        key: str,
    ) -> None:
        """Each sidebar item navigates to the corresponding page."""
        nav_list = main_window.findChild(QListWidget, "sidebar")
        stacked = main_window.findChild(QStackedWidget)
        nav_list.setCurrentRow(page_index)
        assert stacked.currentIndex() == page_index

    def test_navigate_forward_through_all_pages(
        self,
        main_window,  # noqa: ANN001
    ) -> None:
        """Navigating forward through all pages in order works."""
        stacked = main_window.findChild(QStackedWidget)
        for i in range(10):
            main_window.switch_to_page(i)
            assert stacked.currentIndex() == i

    def test_navigate_backward_through_all_pages(
        self,
        main_window,  # noqa: ANN001
    ) -> None:
        """Navigating backward through all pages in order works."""
        stacked = main_window.findChild(QStackedWidget)
        for i in range(9, -1, -1):
            main_window.switch_to_page(i)
            assert stacked.currentIndex() == i

    def test_navigate_random_order(
        self,
        main_window,  # noqa: ANN001
    ) -> None:
        """Navigating pages in random order works correctly."""
        stacked = main_window.findChild(QStackedWidget)
        order = [
            PAGE_ABOUT,
            PAGE_TRANSLATE_TEXT,
            PAGE_GLOSSARY,
            PAGE_LIVE,
            PAGE_SUBTITLE,
            PAGE_DUBBING,
            PAGE_SETTINGS,
            PAGE_VOICE,
            PAGE_EXTRACT_TEXT,
            PAGE_TRANSLATE,
        ]
        for idx in order:
            main_window.switch_to_page(idx)
            assert stacked.currentIndex() == idx


# ===================================================================
# NEW: Theme switching — light/dark
# ===================================================================


class TestThemeSwitchingExpanded:
    """Expanded tests for theme switching."""

    def test_dark_theme_change(self, qtbot: QtBot) -> None:
        """Dark theme change does not crash."""
        worker_mock = MagicMock()
        worker_mock.is_busy.return_value = False
        with ExitStack() as stack:
            for target in _PAGE_FACTORIES:
                stack.enter_context(patch(target, side_effect=_make_themed_widget))
            for target, replacement in _DB_ACTIVITY_CHECKS.items():
                stack.enter_context(patch(target, side_effect=replacement))
            for target in _WORKER_CLASSES:
                stack.enter_context(patch(target, worker_mock))
            from src.ui.window import create_main_window  # noqa: PLC0415

            window = create_main_window()
            qtbot.addWidget(window)
            from src.constants import theme_changed  # noqa: PLC0415

            theme_changed.emit("dark")
            assert window.windowTitle()

    def test_light_theme_change(self, qtbot: QtBot) -> None:
        """Light theme change does not crash."""
        worker_mock = MagicMock()
        worker_mock.is_busy.return_value = False
        with ExitStack() as stack:
            for target in _PAGE_FACTORIES:
                stack.enter_context(patch(target, side_effect=_make_themed_widget))
            for target, replacement in _DB_ACTIVITY_CHECKS.items():
                stack.enter_context(patch(target, side_effect=replacement))
            for target in _WORKER_CLASSES:
                stack.enter_context(patch(target, worker_mock))
            from src.ui.window import create_main_window  # noqa: PLC0415

            window = create_main_window()
            qtbot.addWidget(window)
            from src.constants import theme_changed  # noqa: PLC0415

            theme_changed.emit("light")
            assert window.windowTitle()

    def test_theme_updates_sidebar_background(self, qtbot: QtBot) -> None:
        """Theme change updates sidebar background style."""
        worker_mock = MagicMock()
        worker_mock.is_busy.return_value = False
        with ExitStack() as stack:
            for target in _PAGE_FACTORIES:
                stack.enter_context(patch(target, side_effect=_make_widget))
            for target, replacement in _DB_ACTIVITY_CHECKS.items():
                stack.enter_context(patch(target, side_effect=replacement))
            for target in _WORKER_CLASSES:
                stack.enter_context(patch(target, worker_mock))
            from src.ui.window import create_main_window  # noqa: PLC0415

            window = create_main_window()
            qtbot.addWidget(window)
            from src.constants import theme_changed  # noqa: PLC0415

            theme_changed.emit("dark")
            # Sidebar should have updated stylesheet
            nav_list = window.findChild(QListWidget, "sidebar")
            assert nav_list.styleSheet()

    def test_theme_updates_stacked_widget_style(self, qtbot: QtBot) -> None:
        """Theme change updates stacked widget stylesheet."""
        worker_mock = MagicMock()
        worker_mock.is_busy.return_value = False
        with ExitStack() as stack:
            for target in _PAGE_FACTORIES:
                stack.enter_context(patch(target, side_effect=_make_widget))
            for target, replacement in _DB_ACTIVITY_CHECKS.items():
                stack.enter_context(patch(target, side_effect=replacement))
            for target in _WORKER_CLASSES:
                stack.enter_context(patch(target, worker_mock))
            from src.ui.window import create_main_window  # noqa: PLC0415

            window = create_main_window()
            qtbot.addWidget(window)
            stacked = window.findChild(QStackedWidget)
            from src.constants import theme_changed  # noqa: PLC0415

            theme_changed.emit("dark")
            assert "background-color" in stacked.styleSheet()

    def test_theme_updates_window_stylesheet(self, qtbot: QtBot) -> None:
        """Theme change updates window-level scrollbar stylesheet."""
        worker_mock = MagicMock()
        worker_mock.is_busy.return_value = False
        with ExitStack() as stack:
            for target in _PAGE_FACTORIES:
                stack.enter_context(patch(target, side_effect=_make_widget))
            for target, replacement in _DB_ACTIVITY_CHECKS.items():
                stack.enter_context(patch(target, side_effect=replacement))
            for target in _WORKER_CLASSES:
                stack.enter_context(patch(target, worker_mock))
            from src.ui.window import create_main_window  # noqa: PLC0415

            window = create_main_window()
            qtbot.addWidget(window)
            from src.constants import theme_changed  # noqa: PLC0415

            theme_changed.emit("light")
            assert window.styleSheet()


# ===================================================================
# NEW: Language switching — multiple languages
# ===================================================================


class TestLanguageSwitchingExpanded:
    """Expanded tests for language switching."""

    @pytest.mark.parametrize("lang_code", ["en-US", "vi", "en-UK"])
    def test_language_change_for_each_locale(
        self, qtbot: QtBot, lang_code: str
    ) -> None:
        """Language change for each supported locale does not crash."""
        worker_mock = MagicMock()
        worker_mock.is_busy.return_value = False
        with ExitStack() as stack:
            for target in _PAGE_FACTORIES:
                stack.enter_context(patch(target, side_effect=_make_widget))
            for target, replacement in _DB_ACTIVITY_CHECKS.items():
                stack.enter_context(patch(target, side_effect=replacement))
            for target in _WORKER_CLASSES:
                stack.enter_context(patch(target, worker_mock))
            from src.ui.window import create_main_window  # noqa: PLC0415

            window = create_main_window()
            qtbot.addWidget(window)
            from src.constants import language_changed  # noqa: PLC0415

            language_changed.emit(lang_code)
            assert window.windowTitle()
            nav_list = window.findChild(QListWidget, "sidebar")
            for i in range(nav_list.count()):
                assert nav_list.item(i).text()

    def test_language_change_preserves_current_page(self, qtbot: QtBot) -> None:
        """Language change does not alter the currently selected page."""
        worker_mock = MagicMock()
        worker_mock.is_busy.return_value = False
        with ExitStack() as stack:
            for target in _PAGE_FACTORIES:
                stack.enter_context(patch(target, side_effect=_make_widget))
            for target, replacement in _DB_ACTIVITY_CHECKS.items():
                stack.enter_context(patch(target, side_effect=replacement))
            for target in _WORKER_CLASSES:
                stack.enter_context(patch(target, worker_mock))
            from src.ui.window import create_main_window  # noqa: PLC0415

            window = create_main_window()
            qtbot.addWidget(window)
            window.switch_to_page(PAGE_GLOSSARY)
            stacked = window.findChild(QStackedWidget)
            from src.constants import language_changed  # noqa: PLC0415

            language_changed.emit("vi")
            assert stacked.currentIndex() == PAGE_GLOSSARY

    def test_language_change_updates_all_sidebar_items(self, qtbot: QtBot) -> None:
        """All sidebar items have text after language change."""
        worker_mock = MagicMock()
        worker_mock.is_busy.return_value = False
        with ExitStack() as stack:
            for target in _PAGE_FACTORIES:
                stack.enter_context(patch(target, side_effect=_make_widget))
            for target, replacement in _DB_ACTIVITY_CHECKS.items():
                stack.enter_context(patch(target, side_effect=replacement))
            for target in _WORKER_CLASSES:
                stack.enter_context(patch(target, worker_mock))
            from src.ui.window import create_main_window  # noqa: PLC0415

            window = create_main_window()
            qtbot.addWidget(window)
            nav_list = window.findChild(QListWidget, "sidebar")
            from src.constants import language_changed  # noqa: PLC0415

            language_changed.emit("vi")
            for i in range(nav_list.count()):
                assert nav_list.item(i).text() != ""


# ===================================================================
# NEW: Keyboard shortcuts expanded
# ===================================================================


class TestKeyboardShortcutsExpanded:
    """Expanded tests for keyboard shortcuts."""

    def test_refresh_shortcut_gone(
        self,
        main_window,  # noqa: ANN001
    ) -> None:
        """Window no longer owns Ctrl+R — it's now a glossary page shortcut."""
        shortcuts = main_window.findChildren(QShortcut)
        matches = [s for s in shortcuts if s.key().toString() == "Ctrl+R"]
        assert matches == []


# ===================================================================
# NEW: Window resize and structure
# ===================================================================


class TestWindowStructure:
    """Tests for window structural properties."""

    def test_window_minimum_width(self, main_window) -> None:  # noqa: ANN001
        """Window has minimum width set."""
        assert main_window.minimumWidth() > 0

    def test_window_minimum_height(self, main_window) -> None:  # noqa: ANN001
        """Window has minimum height set."""
        assert main_window.minimumHeight() > 0

    def test_sidebar_fixed_width(self, main_window) -> None:  # noqa: ANN001
        """Sidebar has fixed width."""
        from src.constants import SIDEBAR_WIDTH  # noqa: PLC0415

        nav_list = main_window.findChild(QListWidget, "sidebar")
        sidebar = nav_list.parent()
        assert sidebar.minimumWidth() == SIDEBAR_WIDTH
        assert sidebar.maximumWidth() == SIDEBAR_WIDTH

    def test_stacked_widget_children_are_widgets(
        self,
        main_window,  # noqa: ANN001
    ) -> None:
        """All stacked widget children are QWidget instances."""
        stacked = main_window.findChild(QStackedWidget)
        for i in range(stacked.count()):
            assert isinstance(stacked.widget(i), QWidget)

    def test_window_central_widget_has_layout(
        self,
        main_window,  # noqa: ANN001
    ) -> None:
        """Central widget has a layout."""
        assert main_window.centralWidget().layout() is not None

    def test_window_central_widget_layout_count(
        self,
        main_window,  # noqa: ANN001
    ) -> None:
        """Central widget layout has 2 children (sidebar + stacked)."""
        layout = main_window.centralWidget().layout()
        assert layout.count() == 2  # noqa: PLR2004


# ===================================================================
# NEW: Switch to page edge cases
# ===================================================================


class TestSwitchToPageEdgeCases:
    """Edge cases for switch_to_page."""

    def test_switch_to_page_zero(self, main_window) -> None:  # noqa: ANN001
        """Switching to page 0 works."""
        main_window.switch_to_page(0)
        stacked = main_window.findChild(QStackedWidget)
        assert stacked.currentIndex() == 0

    def test_switch_to_last_page(self, main_window) -> None:  # noqa: ANN001
        """Switching to the last page (About) works."""
        main_window.switch_to_page(PAGE_ABOUT)
        stacked = main_window.findChild(QStackedWidget)
        assert stacked.currentIndex() == PAGE_ABOUT

    def test_switch_preserves_sidebar_sync(self, main_window) -> None:  # noqa: ANN001
        """switch_to_page keeps sidebar in sync after multiple switches."""
        nav_list = main_window.findChild(QListWidget, "sidebar")
        for idx in [3, 7, 1, 9, 0, 5]:
            main_window.switch_to_page(idx)
            assert nav_list.currentRow() == idx

    def test_switch_to_page_rapidly(self, main_window) -> None:  # noqa: ANN001
        """Rapidly switching pages does not crash."""
        stacked = main_window.findChild(QStackedWidget)
        for _ in range(50):
            for i in range(10):
                main_window.switch_to_page(i)
        assert stacked.currentIndex() in range(10)


# ===================================================================
# NEW: Spinner timer configuration
# ===================================================================


class TestSpinnerTimerExpanded:
    """Expanded tests for spinner timer."""

    def test_timer_interval_100ms(self, main_window) -> None:  # noqa: ANN001
        """Status timer runs at 100ms interval."""
        from PySide6.QtCore import QTimer  # noqa: PLC0415

        timers = main_window.findChildren(QTimer)
        intervals = [t.interval() for t in timers if t.isActive()]
        assert 100 in intervals  # noqa: PLR2004

    def test_timer_is_running(self, main_window) -> None:  # noqa: ANN001
        """At least one timer is actively running."""
        from PySide6.QtCore import QTimer  # noqa: PLC0415

        timers = main_window.findChildren(QTimer)
        active = [t for t in timers if t.isActive()]
        assert len(active) > 0

    def test_no_spinner_in_sidebar_when_idle(self, main_window) -> None:  # noqa: ANN001
        """No spinner characters in sidebar when all workers are idle."""
        nav_list = main_window.findChild(QListWidget, "sidebar")
        spinner_chars = {"⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"}
        for i in range(nav_list.count()):
            text = nav_list.item(i).text()
            assert not any(c in text for c in spinner_chars)


# ===================================================================
# NEW: Change event expanded
# ===================================================================


class TestChangeEventExpanded:
    """Expanded tests for changeEvent handling."""

    def test_change_event_resize(self, main_window) -> None:  # noqa: ANN001
        """Resize change event is handled without crash."""
        event = QEvent(QEvent.Type.Resize)
        main_window.changeEvent(event)

    def test_change_event_language_change(self, main_window) -> None:  # noqa: ANN001
        """LanguageChange event is handled without crash."""
        event = QEvent(QEvent.Type.LanguageChange)
        main_window.changeEvent(event)

    def test_change_event_window_state(self, main_window) -> None:  # noqa: ANN001
        """WindowStateChange event is handled without crash."""
        event = QEvent(QEvent.Type.WindowStateChange)
        main_window.changeEvent(event)

    def test_activation_when_not_active_window(self, main_window) -> None:  # noqa: ANN001
        """ActivationChange when window is not active does not raise dialog."""
        event = QEvent(QEvent.Type.ActivationChange)
        with patch.object(type(main_window), "isActiveWindow", return_value=False):
            main_window.changeEvent(event)

    def test_activation_with_non_dialog_modal(self, main_window) -> None:  # noqa: ANN001
        """ActivationChange with non-QDialog modal widget is handled."""
        event = QEvent(QEvent.Type.ActivationChange)
        with (
            patch.object(type(main_window), "isActiveWindow", return_value=True),
            patch(
                f"{_MOD}.QApplication.activeModalWidget",
                return_value=QWidget(),
            ),
        ):
            main_window.changeEvent(event)


# ===================================================================
# NEW: Sidebar keys validation
# ===================================================================


class TestSidebarKeysValidation:
    """Tests validating sidebar keys."""

    def test_sidebar_keys_count(self) -> None:
        """There are exactly 10 sidebar keys."""
        assert len(_SIDEBAR_KEYS) == 10  # noqa: PLR2004

    def test_sidebar_keys_are_strings(self) -> None:
        """All sidebar keys are strings."""
        for key in _SIDEBAR_KEYS:
            assert isinstance(key, str)

    def test_sidebar_keys_start_with_sidebar(self) -> None:
        """All sidebar keys start with 'sidebar.'."""
        for key in _SIDEBAR_KEYS:
            assert key.startswith("sidebar.")

    def test_sidebar_keys_are_unique(self) -> None:
        """All sidebar keys are unique."""
        assert len(set(_SIDEBAR_KEYS)) == len(_SIDEBAR_KEYS)

    def test_expected_sidebar_keys_present(self) -> None:
        """Expected sidebar keys are present."""
        expected = {
            "sidebar.translate_text",
            "sidebar.translate_document",
            "sidebar.generate_subtitle",
            "sidebar.generate_voice",
            "sidebar.dubbing",
            "sidebar.live",
            "sidebar.extract_text",
            "sidebar.glossary",
            "sidebar.settings",
            "sidebar.about",
        }
        assert set(_SIDEBAR_KEYS) == expected


# ===================================================================
# NEW: Navigate to settings tab extended
# ===================================================================


class TestNavigateSettingsTabExpanded:
    """Additional tests for navigate_to_settings_tab."""

    @pytest.mark.parametrize("tab_idx", range(10))
    def test_navigate_to_settings_tab_all(
        self,
        main_window,
        tab_idx,  # noqa: ANN001
    ) -> None:
        """navigate_to_settings_tab works for all tab indices."""
        stacked = main_window.findChild(QStackedWidget)
        main_window.navigate_to_settings_tab(tab_idx)
        assert stacked.currentIndex() == PAGE_SETTINGS

    def test_navigate_settings_from_every_page(
        self,
        main_window,  # noqa: ANN001
    ) -> None:
        """navigate_to_settings_tab works from every starting page."""
        stacked = main_window.findChild(QStackedWidget)
        for start_page in range(10):
            main_window.switch_to_page(start_page)
            main_window.navigate_to_settings_tab(0)
            assert stacked.currentIndex() == PAGE_SETTINGS


# ===================================================================
# NEW: Window title and dimensions
# ===================================================================


class TestWindowTitleAndDimensions:
    """Tests for window title and size constraints."""

    def test_window_has_title(self, main_window) -> None:  # noqa: ANN001
        """Window has a non-empty title."""
        assert len(main_window.windowTitle()) > 0

    def test_window_minimum_width(self, main_window) -> None:  # noqa: ANN001
        """Window has a minimum width."""
        assert main_window.minimumWidth() > 0

    def test_window_minimum_height(self, main_window) -> None:  # noqa: ANN001
        """Window has a minimum height."""
        assert main_window.minimumHeight() > 0

    def test_window_is_qmainwindow(self, main_window) -> None:  # noqa: ANN001
        """Window is a QMainWindow instance."""
        assert isinstance(main_window, QMainWindow)

    def test_window_has_central_widget(self, main_window) -> None:  # noqa: ANN001
        """Window has a central widget."""
        assert main_window.centralWidget() is not None


# ===================================================================
# NEW: Stacked widget page count
# ===================================================================


class TestStackedWidgetPageCount:
    """Tests for stacked widget structure."""

    def test_stacked_has_ten_pages(self, main_window) -> None:  # noqa: ANN001
        """Stacked widget contains exactly 10 pages."""
        stacked = main_window.findChild(QStackedWidget)
        assert stacked.count() == 10  # noqa: PLR2004

    def test_all_page_widgets_are_qwidgets(self, main_window) -> None:  # noqa: ANN001
        """All pages in stacked widget are QWidget instances."""
        stacked = main_window.findChild(QStackedWidget)
        for i in range(stacked.count()):
            assert isinstance(stacked.widget(i), QWidget)

    def test_initial_page_is_translate_text(self, main_window) -> None:  # noqa: ANN001
        """Initial page is Translate Text (index 0)."""
        nav_list = main_window.findChild(QListWidget, "sidebar")
        assert nav_list.currentRow() == PAGE_TRANSLATE_TEXT

    def test_sidebar_selection_matches_stacked(self, main_window) -> None:  # noqa: ANN001
        """Sidebar selection matches stacked widget index."""
        stacked = main_window.findChild(QStackedWidget)
        nav_list = main_window.findChild(QListWidget, "sidebar")
        for i in range(10):
            nav_list.setCurrentRow(i)
            assert stacked.currentIndex() == i


# ===================================================================
# Sidebar spinner status animation
# ===================================================================


class TestUpdateSidebarStatus:
    """Tests for the update_sidebar_status spinner animation."""

    def test_spinner_shown_when_busy_and_active(self, qtbot: QtBot) -> None:
        """Sidebar item shows spinner when is_busy and is_active are both True."""
        worker_mock = MagicMock()
        worker_mock.is_busy.return_value = True

        # Make the translation worker report busy, and DB report active
        busy_activity_checks = {
            f"{_MOD}.is_any_translating": lambda: True,
            f"{_MOD}.is_any_extracting": lambda: False,
            f"{_MOD}.is_any_subtitle_generating": lambda: False,
            f"{_MOD}.is_any_voice_generating": lambda: False,
            f"{_MOD}.is_any_dubbing_generating": lambda: False,
        }

        with ExitStack() as stack:
            for target in _PAGE_FACTORIES:
                stack.enter_context(patch(target, side_effect=_make_widget))
            for target, replacement in busy_activity_checks.items():
                stack.enter_context(patch(target, side_effect=replacement))
            for target in _WORKER_CLASSES:
                stack.enter_context(patch(target, worker_mock))

            from PySide6.QtWidgets import QApplication  # noqa: PLC0415

            from src.ui.window import create_main_window  # noqa: PLC0415

            window = create_main_window()
            qtbot.addWidget(window)

            # Spinner-suffix rendering is gated on the sidebar being
            # *expanded* (no horizontal room when collapsed).  Force a
            # wide geometry so the offscreen platform's reported screen
            # size — which can be below the 1100 px collapse threshold —
            # doesn't auto-collapse the sidebar.  Plain ``window.resize``
            # is unreliable under ``--forked`` (the unshown window may
            # swallow the resize event); synthesising and dispatching a
            # ``QResizeEvent`` directly to ``window.resizeEvent`` makes
            # the expand-hysteresis branch fire deterministically.
            from PySide6.QtCore import QSize  # noqa: PLC0415
            from PySide6.QtGui import QResizeEvent  # noqa: PLC0415

            window.resize(1400, 900)
            window.resizeEvent(QResizeEvent(QSize(1400, 900), window.size()))
            QApplication.instance().processEvents()

            nav_list = window.findChild(QListWidget, "sidebar")

            # Find the QTimer for status updates and trigger its callback
            from PySide6.QtCore import QTimer  # noqa: PLC0415

            timers = window.findChildren(QTimer)
            # Fire every 100ms timer — there can be more than one (sidebar
            # status + any idle spinners on child pages, e.g. Screen Live);
            # the sidebar one is the target, others are harmless no-ops.
            for timer in timers:
                if timer.interval() == 100:  # noqa: PLR2004
                    timer.timeout.emit()

            # PAGE_TRANSLATE (index 1) should contain a spinner character
            translate_item = nav_list.item(PAGE_TRANSLATE)
            spinner_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
            text = translate_item.text()
            assert any(frame in text for frame in spinner_frames), (
                f"Expected spinner in '{text}'"
            )

    def test_spinner_removed_when_not_busy(self, qtbot: QtBot) -> None:
        """Sidebar item spinner is removed when is_busy returns False."""
        worker_mock = MagicMock()
        worker_mock.is_busy.return_value = False

        with ExitStack() as stack:
            for target in _PAGE_FACTORIES:
                stack.enter_context(patch(target, side_effect=_make_widget))
            for target, replacement in _DB_ACTIVITY_CHECKS.items():
                stack.enter_context(patch(target, side_effect=replacement))
            for target in _WORKER_CLASSES:
                stack.enter_context(patch(target, worker_mock))

            from src.ui.window import create_main_window  # noqa: PLC0415

            window = create_main_window()
            qtbot.addWidget(window)

            nav_list = window.findChild(QListWidget, "sidebar")

            # Trigger the status timer
            from PySide6.QtCore import QTimer  # noqa: PLC0415

            timers = window.findChildren(QTimer)
            for timer in timers:
                if timer.interval() == 100:  # noqa: PLR2004
                    timer.timeout.emit()
                    break

            # No sidebar items should contain spinner characters
            spinner_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
            for i in range(nav_list.count()):
                text = nav_list.item(i).text()
                assert not any(frame in text for frame in spinner_frames), (
                    f"Unexpected spinner in item {i}: '{text}'"
                )

    def test_spinner_not_shown_when_busy_but_not_active(self, qtbot: QtBot) -> None:
        """Spinner is hidden when worker is busy but DB reports no active tasks."""
        worker_mock = MagicMock()
        worker_mock.is_busy.return_value = True

        # Worker is busy but DB reports no active tasks (e.g. paused)
        with ExitStack() as stack:
            for target in _PAGE_FACTORIES:
                stack.enter_context(patch(target, side_effect=_make_widget))
            for target, _replacement in _DB_ACTIVITY_CHECKS.items():
                # All DB checks return False (no active tasks)
                stack.enter_context(patch(target, return_value=False))
            for target in _WORKER_CLASSES:
                stack.enter_context(patch(target, worker_mock))

            from src.ui.window import create_main_window  # noqa: PLC0415

            window = create_main_window()
            qtbot.addWidget(window)

            nav_list = window.findChild(QListWidget, "sidebar")

            from PySide6.QtCore import QTimer  # noqa: PLC0415

            timers = window.findChildren(QTimer)
            for timer in timers:
                if timer.interval() == 100:  # noqa: PLR2004
                    timer.timeout.emit()
                    break

            # No spinner should appear since DB has no active tasks
            spinner_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
            for i in range(nav_list.count()):
                text = nav_list.item(i).text()
                assert not any(frame in text for frame in spinner_frames), (
                    f"Unexpected spinner in item {i}: '{text}'"
                )


# ===================================================================
# Keyboard Shortcuts — Ctrl+O / F5 / Delete handlers
# ===================================================================


class TestKeyboardShortcutHandlers:
    """Tests for shortcut trigger helpers (Ctrl+O, F5, Delete)."""

    @staticmethod
    def _activate_shortcut(window: QMainWindow, key_seq: str) -> None:
        """Finds the QShortcut with *key_seq* and emits its activated signal."""
        from PySide6.QtGui import QKeySequence  # noqa: PLC0415

        target = QKeySequence(key_seq)
        for sc in window.findChildren(QShortcut):
            if sc.key() == target:
                sc.activated.emit()
                return
        pytest.fail(f"Shortcut {key_seq!r} not found on window")

    def test_ctrl_o_emits_files_dropped_on_active_page(
        self,
        qtbot: QtBot,
    ) -> None:
        """Ctrl+O triggers FileDropWidget.files_dropped on the active page."""
        from src.ui.components import FileDropWidget  # noqa: PLC0415

        drop_emitted: list = []

        # Build a page that contains a FileDropWidget child.
        def _page_with_drop(*_a: object, **_kw: object) -> QWidget:
            page = QWidget()
            # Minimal FileDropWidget; the real class accepts these kwargs.
            drop = FileDropWidget(parent=page)
            drop.files_dropped.connect(drop_emitted.append)
            return page

        worker_mock = MagicMock()
        worker_mock.is_busy.return_value = False

        with ExitStack() as stack:
            for target in _PAGE_FACTORIES:
                # Use the drop-enabled page for the Translate page specifically.
                if "translate_document" in target:
                    stack.enter_context(patch(target, side_effect=_page_with_drop))
                else:
                    stack.enter_context(patch(target, side_effect=_make_widget))
            for target, replacement in _DB_ACTIVITY_CHECKS.items():
                stack.enter_context(patch(target, side_effect=replacement))
            for target in _WORKER_CLASSES:
                stack.enter_context(patch(target, worker_mock))

            from src.ui.window import create_main_window  # noqa: PLC0415

            window = create_main_window()
            qtbot.addWidget(window)
            window.switch_to_page(PAGE_TRANSLATE)

            self._activate_shortcut(window, "Ctrl+O")

            assert drop_emitted == [[]], (
                f"Expected one [[]] emission from files_dropped, got {drop_emitted}"
            )

    def test_delete_calls_on_delete_selected_on_child_with_method(
        self,
        main_window,  # noqa: ANN001
    ) -> None:
        """Delete key invokes on_delete_selected on the first matching child."""
        stacked = main_window.findChild(QStackedWidget)
        current = stacked.currentWidget()

        child = QWidget(current)
        child.on_delete_selected = MagicMock()

        self._activate_shortcut(main_window, "Delete")
        child.on_delete_selected.assert_called_once_with()

    def test_pause_shortcut_calls_on_pause(
        self,
        main_window,  # noqa: ANN001
    ) -> None:
        """Ctrl+P invokes ``on_pause`` on the active page (or matching child)."""
        stacked = main_window.findChild(QStackedWidget)
        current = stacked.currentWidget()

        child = QWidget(current)
        child.on_pause = MagicMock()

        self._activate_shortcut(main_window, "Ctrl+P")
        child.on_pause.assert_called_once_with()

    def test_continue_shortcut_calls_on_continue(
        self,
        main_window,  # noqa: ANN001
    ) -> None:
        """Ctrl+G invokes ``on_continue`` on the active page (or matching child)."""
        stacked = main_window.findChild(QStackedWidget)
        current = stacked.currentWidget()

        child = QWidget(current)
        child.on_continue = MagicMock()

        self._activate_shortcut(main_window, "Ctrl+G")
        child.on_continue.assert_called_once_with()

    def test_pause_continue_silent_noop_when_no_handler(
        self,
        main_window,  # noqa: ANN001
    ) -> None:
        """Pages without ``on_pause`` / ``on_continue`` quietly ignore the keys."""
        # Active page has no queue-control methods — must not raise.
        self._activate_shortcut(main_window, "Ctrl+P")
        self._activate_shortcut(main_window, "Ctrl+G")

    def test_delete_is_suppressed_when_text_input_focused(
        self,
        main_window,  # noqa: ANN001
    ) -> None:
        """Delete is NOT forwarded to the page when a QLineEdit has focus."""
        from PySide6.QtWidgets import QApplication, QLineEdit  # noqa: PLC0415

        stacked = main_window.findChild(QStackedWidget)
        current = stacked.currentWidget()

        child = QWidget(current)
        child.on_delete_selected = MagicMock()

        line = QLineEdit(main_window)
        main_window.show()
        line.setFocus()
        QApplication.processEvents()
        # Force the focus via the fake (offscreen QApplication may not focus).
        with patch.object(QApplication, "focusWidget", return_value=line):
            self._activate_shortcut(main_window, "Delete")
        child.on_delete_selected.assert_not_called()


# ===================================================================
# Sidebar collapse / expand — hysteresis on resize
# ===================================================================


class TestSplitSidebarLabel:
    """Tests for the _split_sidebar_label helper."""

    def test_split_emoji_then_text(self) -> None:
        """Standard '<emoji> <text>' splits at the first space."""
        from src.ui.window import _split_sidebar_label  # noqa: PLC0415

        emoji, full = _split_sidebar_label("\U0001f310 Translate Text")
        assert emoji == "\U0001f310"
        assert full == "\U0001f310 Translate Text"

    def test_no_space_returns_label_for_both(self) -> None:
        """A label with no space is treated as emoji-only (defensive fallback)."""
        from src.ui.window import _split_sidebar_label  # noqa: PLC0415

        emoji, full = _split_sidebar_label("Settings")
        assert emoji == "Settings"
        assert full == "Settings"

    def test_strips_leading_whitespace(self) -> None:
        """Leading whitespace is stripped before splitting."""
        from src.ui.window import _split_sidebar_label  # noqa: PLC0415

        emoji, full = _split_sidebar_label("   \U0001f4be Voice")
        assert emoji == "\U0001f4be"
        assert full == "\U0001f4be Voice"

    def test_empty_string(self) -> None:
        """Empty input returns empty strings."""
        from src.ui.window import _split_sidebar_label  # noqa: PLC0415

        assert _split_sidebar_label("") == ("", "")


class TestSidebarCollapse:
    """Tests for the resize-driven sidebar collapse / expand with hysteresis."""

    @staticmethod
    def _trigger_resize(window, width: int, height: int = 800) -> None:
        """Synthesizes a QResizeEvent and dispatches via window.resizeEvent."""
        from PySide6.QtCore import QSize  # noqa: PLC0415
        from PySide6.QtGui import QResizeEvent  # noqa: PLC0415

        old = window.size()
        event = QResizeEvent(QSize(width, height), old)
        window.resizeEvent(event)

    def test_collapses_below_collapse_threshold(self, main_window) -> None:  # noqa: ANN001
        """Width < SIDEBAR_COLLAPSE_THRESHOLD collapses the sidebar."""
        from src.constants import (  # noqa: PLC0415
            SIDEBAR_COLLAPSE_THRESHOLD,
            SIDEBAR_COLLAPSED_WIDTH,
        )

        nav_list = main_window.findChild(QListWidget, "sidebar")
        sidebar = nav_list.parent()

        self._trigger_resize(main_window, SIDEBAR_COLLAPSE_THRESHOLD - 1)

        assert sidebar.maximumWidth() == SIDEBAR_COLLAPSED_WIDTH
        assert sidebar.minimumWidth() == SIDEBAR_COLLAPSED_WIDTH

    def test_collapsed_items_show_emoji_only_text(
        self,
        main_window,  # noqa: ANN001
    ) -> None:
        """Collapsed items render the emoji-prefix-only text (no tooltip used).

        Without translations loaded, ``tr()`` returns the raw key (e.g.
        "sidebar.translate_text") which has no leading emoji.  The
        ``_split_sidebar_label`` defensive fallback then echoes the
        full text, so we only check that the collapsed text is
        non-empty — the tooltip path was removed app-wide.
        """
        from src.constants import SIDEBAR_COLLAPSE_THRESHOLD  # noqa: PLC0415

        nav_list = main_window.findChild(QListWidget, "sidebar")

        self._trigger_resize(main_window, SIDEBAR_COLLAPSE_THRESHOLD - 100)

        for i in range(nav_list.count()):
            item = nav_list.item(i)
            assert item.text(), f"item {i} has empty text when collapsed"

    def test_collapsed_emoji_split_when_label_has_emoji(self, qtbot: QtBot) -> None:
        """When the label carries an emoji prefix, collapsed text equals the emoji."""
        from src.constants import SIDEBAR_COLLAPSE_THRESHOLD  # noqa: PLC0415

        worker_mock = MagicMock()
        worker_mock.is_busy.return_value = False

        with ExitStack() as stack:
            for target in _PAGE_FACTORIES:
                stack.enter_context(patch(target, side_effect=_make_widget))
            for target, replacement in _DB_ACTIVITY_CHECKS.items():
                stack.enter_context(patch(target, side_effect=replacement))
            for target in _WORKER_CLASSES:
                stack.enter_context(patch(target, worker_mock))
            # Patch tr() inside the window module so labels arrive with emojis.
            stack.enter_context(
                patch(
                    f"{_MOD}.tr",
                    side_effect=lambda k, **_kw: (
                        "\U0001f310 Translate Text"
                        if k == "sidebar.translate_text"
                        else "\U0001f4c4 Translate Document"
                        if k == "sidebar.translate_document"
                        else f"\U0001f4be {k}"
                    ),
                ),
            )

            from src.ui.window import create_main_window  # noqa: PLC0415

            window = create_main_window()
            qtbot.addWidget(window)
            nav_list = window.findChild(QListWidget, "sidebar")

            from PySide6.QtCore import QSize  # noqa: PLC0415
            from PySide6.QtGui import QResizeEvent  # noqa: PLC0415

            window.resizeEvent(
                QResizeEvent(
                    QSize(SIDEBAR_COLLAPSE_THRESHOLD - 100, 800),
                    window.size(),
                ),
            )

            # First item — explicit emoji label.
            first = nav_list.item(0)
            assert first.text() == "\U0001f310"
            second = nav_list.item(1)
            assert second.text() == "\U0001f4c4"

    def test_expands_above_expand_threshold(self, main_window) -> None:  # noqa: ANN001
        """Width > SIDEBAR_EXPAND_THRESHOLD restores the sidebar."""
        from src.constants import (  # noqa: PLC0415
            SIDEBAR_COLLAPSE_THRESHOLD,
            SIDEBAR_EXPAND_THRESHOLD,
            SIDEBAR_WIDTH,
        )

        nav_list = main_window.findChild(QListWidget, "sidebar")
        sidebar = nav_list.parent()

        # Collapse first
        self._trigger_resize(main_window, SIDEBAR_COLLAPSE_THRESHOLD - 50)
        # Then re-expand
        self._trigger_resize(main_window, SIDEBAR_EXPAND_THRESHOLD + 50)

        assert sidebar.maximumWidth() == SIDEBAR_WIDTH
        assert sidebar.minimumWidth() == SIDEBAR_WIDTH

    def test_hysteresis_preserves_collapsed_state(
        self,
        main_window,  # noqa: ANN001
    ) -> None:
        """Width between thresholds preserves the current state (no flap)."""
        from src.constants import (  # noqa: PLC0415
            SIDEBAR_COLLAPSE_THRESHOLD,
            SIDEBAR_COLLAPSED_WIDTH,
            SIDEBAR_EXPAND_THRESHOLD,
        )

        nav_list = main_window.findChild(QListWidget, "sidebar")
        sidebar = nav_list.parent()

        # Collapse
        self._trigger_resize(main_window, SIDEBAR_COLLAPSE_THRESHOLD - 50)
        assert sidebar.maximumWidth() == SIDEBAR_COLLAPSED_WIDTH

        # Resize between thresholds — collapse-state must NOT flip.
        midpoint = (SIDEBAR_COLLAPSE_THRESHOLD + SIDEBAR_EXPAND_THRESHOLD) // 2
        self._trigger_resize(main_window, midpoint)
        assert sidebar.maximumWidth() == SIDEBAR_COLLAPSED_WIDTH

    def test_hysteresis_preserves_expanded_state(
        self,
        main_window,  # noqa: ANN001
    ) -> None:
        """Width between thresholds doesn't collapse an expanded sidebar."""
        from src.constants import (  # noqa: PLC0415
            SIDEBAR_COLLAPSE_THRESHOLD,
            SIDEBAR_EXPAND_THRESHOLD,
            SIDEBAR_WIDTH,
        )

        nav_list = main_window.findChild(QListWidget, "sidebar")
        sidebar = nav_list.parent()

        # Resize to mid-zone from a default expanded state.
        midpoint = (SIDEBAR_COLLAPSE_THRESHOLD + SIDEBAR_EXPAND_THRESHOLD) // 2
        self._trigger_resize(main_window, midpoint)
        # Sidebar stays expanded (default initial state).
        assert sidebar.maximumWidth() == SIDEBAR_WIDTH

    def test_collapsed_spinner_suffix_dropped(self, qtbot: QtBot) -> None:
        """While collapsed, spinner frame is NOT appended (no horizontal room)."""
        from src.constants import (  # noqa: PLC0415
            SIDEBAR_COLLAPSE_THRESHOLD,
        )

        worker_mock = MagicMock()
        worker_mock.is_busy.return_value = True

        # Translation page (index 1) is busy AND DB reports active.
        busy_checks = {
            f"{_MOD}.is_any_translating": lambda: True,
            f"{_MOD}.is_any_extracting": lambda: False,
            f"{_MOD}.is_any_subtitle_generating": lambda: False,
            f"{_MOD}.is_any_voice_generating": lambda: False,
            f"{_MOD}.is_any_dubbing_generating": lambda: False,
        }

        with ExitStack() as stack:
            for target in _PAGE_FACTORIES:
                stack.enter_context(patch(target, side_effect=_make_widget))
            for target, replacement in busy_checks.items():
                stack.enter_context(patch(target, side_effect=replacement))
            for target in _WORKER_CLASSES:
                stack.enter_context(patch(target, worker_mock))

            from src.ui.window import (  # noqa: PLC0415
                PAGE_TRANSLATE,
                create_main_window,
            )

            window = create_main_window()
            qtbot.addWidget(window)
            nav_list = window.findChild(QListWidget, "sidebar")

            # Collapse first.
            from PySide6.QtCore import QSize  # noqa: PLC0415
            from PySide6.QtGui import QResizeEvent  # noqa: PLC0415

            event = QResizeEvent(
                QSize(SIDEBAR_COLLAPSE_THRESHOLD - 100, 800),
                window.size(),
            )
            window.resizeEvent(event)

            # Now fire the spinner timer.
            from PySide6.QtCore import QTimer  # noqa: PLC0415

            for timer in window.findChildren(QTimer):
                if timer.interval() == 100:  # noqa: PLR2004
                    timer.timeout.emit()

            spinner_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
            translate_item = nav_list.item(PAGE_TRANSLATE)
            text = translate_item.text()
            # Collapsed view shows emoji only — spinner frame must NOT appear.
            for frame in spinner_frames:
                assert frame not in text, (
                    f"spinner frame {frame!r} leaked into collapsed text {text!r}"
                )

    def test_language_switch_updates_emoji_when_collapsed(
        self,
        main_window,  # noqa: ANN001
    ) -> None:
        """Language change refreshes collapsed sidebar items.

        Pins the contract that the language re-emit re-renders
        sidebar items in collapsed mode (text stays non-empty
        after the emit).  Tooltips were removed app-wide; the
        only visible cue is the item text.
        """
        from src.constants import (  # noqa: PLC0415
            SIDEBAR_COLLAPSE_THRESHOLD,
            language_changed,
        )

        nav_list = main_window.findChild(QListWidget, "sidebar")
        self._trigger_resize(main_window, SIDEBAR_COLLAPSE_THRESHOLD - 50)

        language_changed.emit("vi")

        for i in range(nav_list.count()):
            assert nav_list.item(i).text(), (
                f"item {i} lost text after lang change"
            )


class TestSpinnerHiddenWhenWorkerBusyButDbIdle:
    """Spinner stays off when worker.is_busy()=True but DB has no active rows."""

    def test_spinner_hidden_translate_document(self, qtbot: QtBot) -> None:
        """TranslationWorker.is_busy()=True + is_any_translating()=False → no spinner."""
        worker_mock = MagicMock()
        worker_mock.is_busy.return_value = True

        # All DB activity checks return False — nothing to translate.
        all_idle = {
            f"{_MOD}.is_any_translating": lambda: False,
            f"{_MOD}.is_any_extracting": lambda: False,
            f"{_MOD}.is_any_subtitle_generating": lambda: False,
            f"{_MOD}.is_any_voice_generating": lambda: False,
            f"{_MOD}.is_any_dubbing_generating": lambda: False,
        }

        with ExitStack() as stack:
            for target in _PAGE_FACTORIES:
                stack.enter_context(patch(target, side_effect=_make_widget))
            for target, replacement in all_idle.items():
                stack.enter_context(patch(target, side_effect=replacement))
            for target in _WORKER_CLASSES:
                stack.enter_context(patch(target, worker_mock))

            from src.ui.window import (  # noqa: PLC0415
                PAGE_TRANSLATE,
                create_main_window,
            )

            window = create_main_window()
            qtbot.addWidget(window)
            nav_list = window.findChild(QListWidget, "sidebar")

            from PySide6.QtCore import QTimer  # noqa: PLC0415

            for timer in window.findChildren(QTimer):
                if timer.interval() == 100:  # noqa: PLR2004
                    timer.timeout.emit()

            translate_item = nav_list.item(PAGE_TRANSLATE)
            text = translate_item.text()
            spinner_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
            for frame in spinner_frames:
                assert frame not in text, (
                    f"spinner showed up despite is_any_translating()=False: {text!r}"
                )


class TestUpdateBanner:
    """``window._show_update_banner`` reveals + populates the update banner.

    The banner is hidden at boot; ``UpdateChecker.update_available``
    fires when the GitHub release feed reports a newer version, and
    ``main.py`` connects that signal to this exposed callable.  Pin
    the contract that calling the slot (a) flips an initially-hidden
    banner to visible and (b) writes the templated text to its label
    — not just an empty show().  Without this guard, a regression
    that breaks the closure (e.g. the wrong label captured) would
    silently surface an empty blue banner.
    """

    def test_show_update_banner_exists(
        self, main_window,  # noqa: ANN001
    ) -> None:
        """The slot is exposed on the main window after construction."""
        assert hasattr(main_window, "_show_update_banner")
        assert callable(main_window._show_update_banner)

    def test_show_update_banner_writes_label_and_reveals(
        self, main_window,  # noqa: ANN001
    ) -> None:
        """Calling the slot writes the localised template to a label.

        Also toggles its parent banner from hidden to visible.
        Loads en-US translations explicitly so the formatted output
        contains the substituted URL — under the offscreen test setup
        i18n may not be initialised by default, in which case the
        ``app.update_available`` template stays as the key string and
        the URL substitution would silently no-op.
        """
        from PySide6.QtWidgets import QLabel  # noqa: PLC0415

        from src.constants.i18n import _set_initial_language  # noqa: PLC0415

        # ``set_language`` short-circuits when the requested code equals
        # the current one (default = en-US), so it can't force a load
        # in tests.  ``_set_initial_language`` always loads.
        _set_initial_language("en-US")

        # Snapshot the visible state of every QLabel before the call.
        labels_before = {
            id(lbl): lbl.isVisible()
            for lbl in main_window.findChildren(QLabel)
        }

        main_window._show_update_banner("9.9.9", "https://example.com/release")

        # The label that received the substituted text must contain
        # the URL — proves both the template lookup and the format
        # substitution ran.
        url_labels = [
            lbl for lbl in main_window.findChildren(QLabel)
            if "https://example.com/release" in lbl.text()
        ]
        assert url_labels, (
            "no QLabel contains the URL — show_update_banner closure "
            "didn't reach update_label.setText()"
        )

        # The owning banner widget (label's parent) must now be
        # visible — pin the setVisible(True) flip.
        banner = url_labels[0].parent()
        assert banner.isVisible(), (
            "update banner stayed hidden after _show_update_banner fired"
        )
        # Sanity: the banner specifically went from hidden → visible
        # (it wasn't already visible from some other code path).
        assert labels_before.get(id(url_labels[0]), True) is False, (
            "label was already visible before the slot fired — test setup leak"
        )
