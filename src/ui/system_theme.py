"""System theme detection and runtime monitoring.

Detects the OS dark/light preference and follows it at runtime via
PySide6's ``colorSchemeChanged`` signal.  The theme engine in
``src/constants/theme.py`` stays PySide6-free — this module bridges
the gap at the UI boundary.
"""

import logging

from src.constants.theme import ThemeName, set_theme

logger = logging.getLogger("system_theme")


def detect_system_theme() -> ThemeName:
    """Returns ``"dark"`` if the OS is in dark mode, otherwise ``"light"``.

    Uses ``QApplication.styleHints().colorScheme()`` (PySide6 6.5+).
    Falls back to ``"light"`` when the API is unavailable, no QApp exists,
    or any exception is raised.
    """
    try:
        from PySide6.QtCore import Qt  # noqa: PLC0415
        from PySide6.QtWidgets import QApplication  # noqa: PLC0415

        app = QApplication.instance()
        if app is None:
            return "light"

        hints = app.styleHints()
        if not hasattr(hints, "colorScheme"):
            return "light"

        scheme = hints.colorScheme()
        if scheme == Qt.ColorScheme.Dark:
            return "dark"
        return "light"
    except Exception:  # noqa: BLE001
        logger.debug(
            "System theme detection failed, defaulting to light.",
            exc_info=True,
        )
        return "light"


class SystemThemeMonitor:
    """Watches for OS theme changes and applies them via ``set_theme()``.

    Usage::

        monitor = SystemThemeMonitor()
        monitor.start()   # begin following the OS theme
        monitor.stop()    # stop following (signal stays connected, callback is no-op)
    """

    def __init__(self) -> None:
        """Initializes the monitor in an inactive state."""
        self._active: bool = False
        self._connected: bool = False

    # -- public API --------------------------------------------------------

    @property
    def is_active(self) -> bool:
        """Whether the monitor is actively following OS theme changes."""
        return self._active

    def start(self) -> None:
        """Activates the monitor and applies the current system theme."""
        self._active = True
        self._ensure_connected()
        set_theme(detect_system_theme())

    def stop(self) -> None:
        """Deactivates the monitor (signal stays connected, callback becomes no-op)."""
        self._active = False

    # -- internals ---------------------------------------------------------

    def _ensure_connected(self) -> None:
        """Lazily connects the ``colorSchemeChanged`` signal (once)."""
        if self._connected:
            return
        try:
            from PySide6.QtWidgets import QApplication  # noqa: PLC0415

            app = QApplication.instance()
            if app is None:
                return

            hints = app.styleHints()
            if not hasattr(hints, "colorSchemeChanged"):
                return

            hints.colorSchemeChanged.connect(self._on_system_theme_changed)
            self._connected = True
        except Exception:  # noqa: BLE001
            logger.debug("Could not connect colorSchemeChanged signal.", exc_info=True)

    def _on_system_theme_changed(self, _scheme: object) -> None:
        """Slot invoked when the OS theme changes."""
        if not self._active:
            return
        set_theme(detect_system_theme())
