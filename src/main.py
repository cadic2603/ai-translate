"""Entry point for the AI Translate application."""

import contextlib
import logging
import sys

# Pre-load pymupdf before LibreOffice UNO can corrupt sys.path.
# UNO's _uno_import hook replaces builtins.__import__ and its pyuno
# initialisation drops virtualenv site-packages from sys.path, making
# pymupdf unfindable later.  Importing here caches it in sys.modules
# so all subsequent `import pymupdf` resolve from cache instantly.
with contextlib.suppress(ImportError):
    import pymupdf  # noqa: F401

from PySide6.QtGui import QFont, QFontDatabase, QIcon
from PySide6.QtWidgets import QApplication

from src.constants import SETTING_THEME, SETTING_UI_LANGUAGE
from src.constants.i18n import _set_initial_language
from src.constants.theme import _set_initial_theme
from src.constants.ui import ASSETS_DIR, FONTS_DIR
from src.core.database import init_db
from src.core.translator import resume_unfinished_translations
from src.ui.window import create_main_window
from src.utils.config_manager import load_setting
from src.utils.path_manager import (
    configure_logging,
    ensure_app_dirs_exist,
    wipe_tts_cache,
)

logger = logging.getLogger("main")

# Font files to load, in order (Regular must be first)
_FONT_FILES = [
    "Roboto-Regular.ttf",
    "Roboto-Bold.ttf",
    "Roboto-Medium.ttf",
    "Roboto-Light.ttf",
    "Roboto-Italic.ttf",
]


def _load_app_font(app: QApplication) -> None:
    """Loads bundled Roboto font and sets it as the application default."""
    for name in _FONT_FILES:
        path = FONTS_DIR / name
        if path.exists():
            font_id = QFontDatabase.addApplicationFont(str(path))
            if font_id < 0:
                logger.warning("Failed to load font: %s", path)
        else:
            logger.warning("Font file not found: %s", path)

    # Set Roboto as the application-wide default font
    font = QFont("Roboto")
    font.setPointSize(10)
    app.setFont(font)


def main() -> None:
    """Initializes and runs the application."""
    # Ensure necessary application directories exist
    ensure_app_dirs_exist()

    # Configure centralized logging
    configure_logging()

    # Each app session starts with a fresh Listen-button TTS cache.
    wipe_tts_cache()

    # Initialize the database
    init_db()

    # Restore the per-(endpoint, model) chat-vs-responses + payload
    # variant caches so the first translation of this session skips
    # the variant probe for already-known models.
    from src.core.llm_engine import _load_persistent_caches  # noqa: PLC0415

    _load_persistent_caches()

    app = QApplication(sys.argv)
    app.setOrganizationName("Google")
    app.setApplicationName("AITranslate")
    # Match the window to its .desktop file so GNOME / KDE / Wayland
    # compositors resolve the dock / taskbar icon from
    # ``ai-translate.desktop`` instead of falling back to a generic glyph.
    # Has no effect on platforms that don't use freedesktop.org integration.
    app.setDesktopFileName("ai-translate")

    # Use Fusion style for consistent cross-platform theming
    app.setStyle("Fusion")

    # Application-level Esc / outside-click focus clearing.  Qt's
    # default leaves the focus rectangle stuck on the last-clicked
    # button until Tab moves elsewhere; this filter restores the
    # standard desktop expectation that Esc and clicks-into-the-void
    # drop focus.  Installed before any windows so dialog edit modes
    # and toolbar buttons all benefit from day one.
    from src.ui.focus_filter import install_focus_clear_filter  # noqa: PLC0415

    install_focus_clear_filter(app)

    # Application-wide window icon: the same SVG drives the desktop
    # window icon, dock / taskbar entry, and (after rasterization) the
    # docs favicon and platform installers.  ``QIcon`` accepts SVG
    # natively in PySide6 6.x.
    app.setWindowIcon(QIcon(str(ASSETS_DIR / "app-icon.svg")))

    # Load bundled Roboto font
    _load_app_font(app)

    # Load persisted theme and language before creating any widgets
    from src.ui.system_theme import (  # noqa: PLC0415
        SystemThemeMonitor,
        detect_system_theme,
    )

    saved_theme = str(load_setting(SETTING_THEME, "auto"))
    system_theme_monitor = SystemThemeMonitor()

    # "Auto" theme tracks OS changes at runtime; explicit themes are applied once
    if saved_theme.lower() == "auto":
        _set_initial_theme(detect_system_theme())
        system_theme_monitor.start()
    else:
        _set_initial_theme(saved_theme.lower())

    saved_language = load_setting(SETTING_UI_LANGUAGE, "en-US")
    _set_initial_language(str(saved_language))

    window = create_main_window()
    # Prevent garbage collection of the theme monitor
    window._system_theme_monitor = system_theme_monitor
    window.show()

    # Startup update check (non-blocking; daemon thread inside UpdateChecker).
    # Silently no-ops when the feature is disabled, the repo coordinate is
    # unset, the 24-hour throttle hasn't elapsed, or the network is down.
    from src.ui.pages.about import _get_version  # noqa: PLC0415
    from src.utils.update_checker import UpdateChecker  # noqa: PLC0415

    update_checker = UpdateChecker()
    if hasattr(window, "_show_update_banner"):
        update_checker.update_available.connect(window._show_update_banner)
    update_checker.check_async(_get_version())
    # Keep a reference so the QObject isn't GC'd before the signal fires.
    window._update_checker = update_checker

    # Resume unfinished tasks
    resume_worker = resume_unfinished_translations()
    # Keep worker reference on the window to prevent GC of the running QThread
    if resume_worker:
        if not hasattr(window, "_workers"):
            window._workers = []
        window._workers.append(resume_worker)

        def safe_remove() -> None:
            """Remove the resume worker from the window's worker list."""
            if hasattr(window, "_workers") and resume_worker in window._workers:
                window._workers.remove(resume_worker)

        resume_worker.finished.connect(safe_remove)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
