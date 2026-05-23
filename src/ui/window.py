"""Main window layout and navigation for the AI Translate application."""

import logging
from collections.abc import Callable

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QKeySequence, QResizeEvent, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from src.constants import (
    MIN_WINDOW_HEIGHT,
    MIN_WINDOW_WIDTH,
    SIDEBAR_COLLAPSE_THRESHOLD,
    SIDEBAR_COLLAPSED_WIDTH,
    SIDEBAR_EXPAND_THRESHOLD,
    SIDEBAR_WIDTH,
    SPINNER_FRAMES,
    SPINNER_INTERVAL_MS,
    color,
    language_changed,
    style_scrollbar,
    style_sidebar_list,
    theme_changed,
    tr,
)
from src.core.database import (
    is_any_dubbing_generating,
    is_any_extracting,
    is_any_subtitle_generating,
    is_any_translating,
    is_any_voice_generating,
)
from src.core.translator import TranslationWorker
from src.ui.components import create_banner
from src.ui.pages.about import create_about_page
from src.ui.pages.dubbing import _DubbingWorker, create_dubbing_page
from src.ui.pages.extract_text import _ExtractionWorker, create_extract_text_page
from src.ui.pages.glossary import create_glossary_page
from src.ui.pages.live import create_live_page
from src.ui.pages.settings import create_settings_page
from src.ui.pages.subtitle import _SubtitleWorker, create_subtitle_page
from src.ui.pages.translate_document import create_translate_document_page
from src.ui.pages.translate_text import (
    _TextTranslationWorker,
    create_translate_text_page,
)
from src.ui.pages.voice import _VoiceWorker, create_voice_page

logger = logging.getLogger("window")

# Page indices for the stacked widget
PAGE_TRANSLATE_TEXT = 0
PAGE_TRANSLATE = 1
PAGE_SUBTITLE = 2
PAGE_VOICE = 3
PAGE_DUBBING = 4
PAGE_LIVE = 5
PAGE_EXTRACT_TEXT = 6
PAGE_GLOSSARY = 7
PAGE_SETTINGS = 8
PAGE_ABOUT = 9


def _split_sidebar_label(label: str) -> tuple[str, str]:
    """Splits a sidebar label into ``(emoji, full)``.

    The convention in ``translations/*.json`` is ``"<emoji> <text>"``,
    e.g. ``"🌐 Translate Text"`` — the emoji portion runs from the start
    up to the first ASCII space.  When no space exists the whole label
    is treated as the emoji (defensive fallback for translations that
    might omit the prefix).
    """
    stripped = label.lstrip()
    space_at = stripped.find(" ")
    if space_at < 0:
        return stripped, stripped
    return stripped[:space_at], stripped


# Sidebar item keys for i18n
_SIDEBAR_KEYS = [
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
]


def create_sidebar(stacked_widget: QStackedWidget) -> QWidget:
    """Creates the sidebar container and navigation list.

    Args:
        stacked_widget: The content area widget to control.

    Returns:
        QWidget: The sidebar container widget.
    """
    container = QWidget()
    container.setFixedWidth(SIDEBAR_WIDTH)
    container.setStyleSheet(f"background-color: {color('sidebar_bg')};")
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)

    nav_list = QListWidget()
    nav_list.setObjectName("sidebar")
    nav_list.setCursor(Qt.CursorShape.PointingHandCursor)
    nav_list.setStyleSheet(style_sidebar_list())

    for key in _SIDEBAR_KEYS:
        nav_list.addItem(QListWidgetItem(tr(key)))

    nav_list.currentRowChanged.connect(stacked_widget.setCurrentIndex)
    nav_list.setCurrentRow(0)

    layout.addWidget(nav_list)
    return container


def create_main_window() -> QMainWindow:  # noqa: PLR0915
    """Creates and configures the main application window with a sidebar.

    Returns:
        QMainWindow: The configured main window instance.
    """
    window = QMainWindow()
    window.setWindowTitle(tr("app.title"))
    window.setMinimumSize(MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT)
    window.setStyleSheet(style_scrollbar())

    central_widget = QWidget()
    window.setCentralWidget(central_widget)

    # Outer vertical layout lets the update-available banner (hidden by
    # default, shown by UpdateChecker) sit above the sidebar + content row.
    outer_layout = QVBoxLayout(central_widget)
    outer_layout.setContentsMargins(0, 0, 0, 0)
    outer_layout.setSpacing(0)

    body_widget = QWidget()
    main_layout = QHBoxLayout(body_widget)
    main_layout.setContentsMargins(0, 0, 0, 0)
    main_layout.setSpacing(0)

    # Content Area — 10 pages
    stacked_widget = QStackedWidget()
    stacked_widget.setStyleSheet(
        f"background-color: {color('app_bg')}; color: {color('text_primary')};"
    )
    stacked_widget.addWidget(create_translate_text_page(window))
    stacked_widget.addWidget(create_translate_document_page(window))
    stacked_widget.addWidget(create_subtitle_page(window))
    stacked_widget.addWidget(create_voice_page(window))
    stacked_widget.addWidget(create_dubbing_page(window))
    stacked_widget.addWidget(create_live_page(window))
    stacked_widget.addWidget(create_extract_text_page(window))
    stacked_widget.addWidget(create_glossary_page())
    stacked_widget.addWidget(create_settings_page())
    stacked_widget.addWidget(create_about_page())

    # Sidebar
    sidebar = create_sidebar(stacked_widget)
    nav_list = sidebar.findChild(QListWidget, "sidebar")

    # Spinner animation on sidebar items while workers are active.
    # Frames/interval are shared with in-page buttons via src.constants.ui.
    spinner_frames = SPINNER_FRAMES
    spinner_index = 0

    # (page_index, sidebar_key, is_busy_fn, is_any_active_fn)
    # Translate Text has no DB-backed task queue, so the same class-level
    # busy flag drives both checks.
    _spinner_configs: list[tuple[int, str, Callable[[], bool], Callable[[], bool]]] = [
        (
            PAGE_TRANSLATE_TEXT,
            "sidebar.translate_text",
            _TextTranslationWorker.is_busy,
            _TextTranslationWorker.is_busy,
        ),
        (
            PAGE_TRANSLATE,
            "sidebar.translate_document",
            TranslationWorker.is_busy,
            is_any_translating,
        ),
        (
            PAGE_EXTRACT_TEXT,
            "sidebar.extract_text",
            _ExtractionWorker.is_busy,
            is_any_extracting,
        ),
        (
            PAGE_SUBTITLE,
            "sidebar.generate_subtitle",
            _SubtitleWorker.is_busy,
            is_any_subtitle_generating,
        ),
        (
            PAGE_VOICE,
            "sidebar.generate_voice",
            _VoiceWorker.is_busy,
            is_any_voice_generating,
        ),
        (
            PAGE_DUBBING,
            "sidebar.dubbing",
            _DubbingWorker.is_busy,
            is_any_dubbing_generating,
        ),
    ]

    # Collapse state: True when the window is narrow enough that the
    # sidebar shrinks to icon-only.  Toggled from ``resizeEvent`` with
    # hysteresis so dragging the window edge near the threshold doesn't
    # flap.  Module-level closure variable instead of an attribute so
    # it's not visible to per-page code.
    collapsed = [False]

    def _render_item(item: QListWidgetItem, key: str, suffix: str = "") -> None:
        """Sets an item's text honouring the collapsed state.

        *suffix* is appended after the full label (used for the spinner
        frame); the emoji-only collapsed view drops it because there's
        no horizontal room.
        """
        full = tr(key)
        emoji, _ = _split_sidebar_label(full)
        if collapsed[0]:
            item.setText(emoji)
        else:
            item.setText(f"{full}  {suffix}" if suffix else full)

    def update_sidebar_status() -> None:
        """Animates spinner icons on sidebar items with active background workers."""
        nonlocal spinner_index
        any_busy = False
        for page_idx, key, is_busy_fn, is_active_fn in _spinner_configs:
            item = nav_list.item(page_idx)
            # Show spinner only when worker is active AND DB has active tasks.
            # This ensures the spinner hides immediately on pause even if
            # the worker thread is still winding down.
            if is_busy_fn() and is_active_fn():
                frame = spinner_frames[spinner_index % len(spinner_frames)]
                _render_item(item, key, suffix=frame)
                any_busy = True
            else:
                _render_item(item, key)
        if any_busy:
            spinner_index += 1

    def _refresh_all_items() -> None:
        """Re-renders every sidebar item — used on collapse / language change."""
        for i, key in enumerate(_SIDEBAR_KEYS):
            item = nav_list.item(i)
            if item is not None:
                _render_item(item, key)

    status_timer = QTimer(window)
    status_timer.timeout.connect(update_sidebar_status)
    status_timer.start(SPINNER_INTERVAL_MS)

    # Navigation helpers attached to the window instance
    def switch_to_page(index: int) -> None:
        """Navigates the sidebar and content area to the given page index."""
        if nav_list:
            nav_list.setCurrentRow(index)

    def navigate_to_settings_tab(tab_index: int) -> None:
        """Switches to the Settings page and activates a specific tab."""
        nav_list.setCurrentRow(PAGE_SETTINGS)
        settings_page = stacked_widget.widget(PAGE_SETTINGS)
        if hasattr(settings_page, "switch_to_tab"):
            settings_page.switch_to_tab(tab_index)

    window.switch_to_page = switch_to_page
    window.navigate_to_settings_tab = navigate_to_settings_tab

    # ── Keyboard shortcuts ────────────────────────────────────────────

    # Global shortcuts. Keys come from the central registry so the Settings
    # → Shortcuts tab can rebind them without a restart.
    from src.constants.shortcuts import (  # noqa: PLC0415
        get_shortcut,
        shortcuts_changed,
    )

    quit_sc = QShortcut(QKeySequence(get_shortcut("app.quit")), window)
    quit_sc.activated.connect(QApplication.quit)

    # Browse/open files on active page
    def _trigger_browse() -> None:
        """Opens the file browse dialog on the active page's FileDropWidget."""
        current = stacked_widget.currentWidget()
        if current:
            # Find the FileDropWidget and trigger its click (browse)
            from src.ui.components import FileDropWidget  # noqa: PLC0415

            drop = current.findChild(FileDropWidget)
            if drop:
                drop.files_dropped.emit([])

    browse_sc = QShortcut(QKeySequence(get_shortcut("app.browse_files")), window)
    browse_sc.activated.connect(_trigger_browse)

    # F-keys are intentionally not hardcoded here.  They collide with
    # universal OS conventions (F1=Help, F5=Refresh, F11=Fullscreen),
    # so any function-key binding goes through the user-editable
    # shortcut registry where the capture UI accepts F1–F35 with full
    # conflict detection.

    # Delete — Delete selected history items on active page
    # Guarded to avoid intercepting Delete key in text inputs
    def _trigger_delete() -> None:
        """Deletes selected history items unless a text input has focus."""
        from PySide6.QtWidgets import (  # noqa: PLC0415
            QLineEdit,
            QPlainTextEdit,
            QTextEdit,
        )

        focused = QApplication.focusWidget()
        if isinstance(focused, (QLineEdit, QTextEdit, QPlainTextEdit)):
            return  # Let the text widget handle the key

        current = stacked_widget.currentWidget()
        if current is None:
            return
        # Check the page itself first so pages can own the delete dispatch
        # (e.g. Glossary, which routes between set-list and entries-table
        # based on focus), then fall back to the first eligible child.
        if hasattr(current, "on_delete_selected"):
            current.on_delete_selected()
            return
        for child in current.findChildren(QWidget):
            if hasattr(child, "on_delete_selected"):
                child.on_delete_selected()
                return

    delete_sc = QShortcut(QKeySequence(get_shortcut("common.delete_selected")), window)
    delete_sc.activated.connect(_trigger_delete)

    # Pause / Continue — dispatch to the active page's queue control
    # methods if present.  Pages that don't manage a queue (Translate
    # Text, Live, Settings, etc.) silently no-op.
    def _trigger_queue_action(method_name: str) -> None:
        """Calls ``method_name`` on the active page if defined.

        Falls back to the first child widget that defines the method
        when the page itself doesn't.  Silent no-op when nothing
        matches.  Suppressed while a text-entry widget owns focus so
        ``Ctrl+P`` (Pause) doesn't steal the keystroke from a
        ``QLineEdit`` / ``QTextEdit`` the user is typing into — same
        guard used by the Delete dispatch above.
        """
        from PySide6.QtWidgets import (  # noqa: PLC0415
            QLineEdit,
            QPlainTextEdit,
            QTextEdit,
        )

        focused = QApplication.focusWidget()
        if isinstance(focused, (QLineEdit, QTextEdit, QPlainTextEdit)):
            return

        current = stacked_widget.currentWidget()
        if current is None:
            return
        if hasattr(current, method_name):
            getattr(current, method_name)()
            return
        for child in current.findChildren(QWidget):
            if hasattr(child, method_name):
                getattr(child, method_name)()
                return

    pause_sc = QShortcut(QKeySequence(get_shortcut("common.pause")), window)
    pause_sc.activated.connect(lambda: _trigger_queue_action("on_pause"))

    continue_sc = QShortcut(QKeySequence(get_shortcut("common.continue")), window)
    continue_sc.activated.connect(lambda: _trigger_queue_action("on_continue"))

    def _sync_global_shortcuts() -> None:
        quit_sc.setKey(QKeySequence(get_shortcut("app.quit")))
        browse_sc.setKey(QKeySequence(get_shortcut("app.browse_files")))
        delete_sc.setKey(QKeySequence(get_shortcut("common.delete_selected")))
        pause_sc.setKey(QKeySequence(get_shortcut("common.pause")))
        continue_sc.setKey(QKeySequence(get_shortcut("common.continue")))

    shortcuts_changed.connect(_sync_global_shortcuts)

    # Theme switching: re-apply all window-level styles and propagate
    def on_theme_changed(_name: str) -> None:
        """Re-applies all styles when the theme changes."""
        window.setStyleSheet(style_scrollbar())
        stacked_widget.setStyleSheet(
            f"background-color: {color('app_bg')}; color: {color('text_primary')};"
        )
        sidebar.setStyleSheet(f"background-color: {color('sidebar_bg')};")
        nav_list.setStyleSheet(style_sidebar_list())

        # Propagate to all children with apply_theme()
        for child in window.findChildren(QWidget):
            if hasattr(child, "apply_theme"):
                child.apply_theme()

    theme_changed.connect(on_theme_changed)

    # Language switching: re-apply all text and propagate
    def on_language_changed(_code: str) -> None:
        """Re-applies all translatable text when the language changes."""
        window.setWindowTitle(tr("app.title"))

        # Update sidebar item texts (collapse-aware)
        _refresh_all_items()

        # Propagate to all children with apply_language().  Each callback
        # is isolated in its own try/except — one broken binding (wrong
        # arity, stale closure on a deleted widget, raised exception)
        # MUST NOT abort propagation to the remaining widgets, otherwise
        # everything iterated after the failing entry stays in the old
        # locale.  The exception is logged so the bad binding still
        # surfaces during development.
        for child in window.findChildren(QWidget):
            if not hasattr(child, "apply_language"):
                continue
            try:
                child.apply_language()
            except Exception:  # noqa: BLE001
                logger.exception(
                    "apply_language failed on %s; continuing propagation",
                    type(child).__name__,
                )

    language_changed.connect(on_language_changed)

    # ── Sidebar collapse / expand on window resize ────────────────────
    # Using hysteresis (collapse < 1100, expand > 1180) so dragging the
    # window edge near a single threshold doesn't flap the layout.
    def _set_collapsed(value: bool) -> None:
        if collapsed[0] == value:
            return
        collapsed[0] = value
        sidebar.setFixedWidth(
            SIDEBAR_COLLAPSED_WIDTH if value else SIDEBAR_WIDTH,
        )
        _refresh_all_items()

    _original_resize = window.resizeEvent

    def _resize_event(event: QResizeEvent) -> None:
        """Toggles the sidebar's collapsed state based on window width."""
        width = event.size().width()
        if not collapsed[0] and width < SIDEBAR_COLLAPSE_THRESHOLD:
            _set_collapsed(True)
        elif collapsed[0] and width > SIDEBAR_EXPAND_THRESHOLD:
            _set_collapsed(False)
        _original_resize(event)

    window.resizeEvent = _resize_event

    # Raise any open modal dialog when the main window is activated,
    # preventing dialogs from being hidden behind the main window.
    _original_change_event = window.changeEvent

    def _change_event(event: QEvent) -> None:
        """Raises modal dialogs above the main window on activation."""
        if event.type() == QEvent.Type.ActivationChange and window.isActiveWindow():
            active_modal = QApplication.activeModalWidget()
            if isinstance(active_modal, QDialog):
                active_modal.raise_()
                active_modal.activateWindow()
        _original_change_event(event)

    window.changeEvent = _change_event

    main_layout.addWidget(sidebar)
    main_layout.addWidget(stacked_widget)

    # Update banner — hidden until UpdateChecker signals a new release.
    # rich_text=True lets us embed an <a href> link directly into the text.
    update_banner, update_label = create_banner(
        "",
        variant="info",
        rich_text=True,
    )
    update_banner.setVisible(False)
    outer_layout.addWidget(update_banner)
    outer_layout.addWidget(body_widget, 1)

    def show_update_banner(version: str, url: str) -> None:
        """Slot: show the banner when a newer release is detected."""
        update_label.setText(
            tr("app.update_available", version=version, url=url),
        )
        update_banner.setVisible(True)

    window._show_update_banner = show_update_banner

    window.showMaximized()
    return window
