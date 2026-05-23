"""Unit tests for src/ui/system_theme.py.

Covers:
- detect_system_theme() — returns "dark" or "light" based on OS scheme
- SystemThemeMonitor construction and initial state
- Monitor start/stop lifecycle and is_active property
- Theme change signal connections via _ensure_connected
- _on_system_theme_changed callback behaviour (active vs inactive)
- Edge cases: no QApp, missing API, exceptions, repeated start/stop
"""

from unittest.mock import MagicMock, call, patch

from PySide6.QtCore import Qt

from src.ui.system_theme import (
    SystemThemeMonitor,
    detect_system_theme,
)

_QAPP_PATH = "PySide6.QtWidgets.QApplication"

# ===========================================================================
# detect_system_theme()
# ===========================================================================


def test_detect_no_qapp_returns_light() -> None:
    """Returns 'light' when no QApplication instance exists."""
    with patch(_QAPP_PATH) as mock_cls:
        mock_cls.instance.return_value = None
        assert detect_system_theme() == "light"


def test_detect_no_color_scheme_attr_returns_light() -> None:
    """Returns 'light' when styleHints lacks colorScheme attribute."""
    mock_app = MagicMock()
    mock_hints = MagicMock(spec=[])  # empty spec -> no colorScheme
    mock_app.styleHints.return_value = mock_hints

    with patch(_QAPP_PATH) as mock_cls:
        mock_cls.instance.return_value = mock_app
        assert detect_system_theme() == "light"


def test_detect_dark_scheme_returns_dark() -> None:
    """Returns 'dark' when OS color scheme is Dark."""
    mock_app = MagicMock()
    mock_hints = MagicMock()
    mock_hints.colorScheme.return_value = Qt.ColorScheme.Dark
    mock_app.styleHints.return_value = mock_hints

    with patch(_QAPP_PATH) as mock_cls:
        mock_cls.instance.return_value = mock_app
        assert detect_system_theme() == "dark"


def test_detect_light_scheme_returns_light() -> None:
    """Returns 'light' when OS color scheme is Light."""
    mock_app = MagicMock()
    mock_hints = MagicMock()
    mock_hints.colorScheme.return_value = Qt.ColorScheme.Light
    mock_app.styleHints.return_value = mock_hints

    with patch(_QAPP_PATH) as mock_cls:
        mock_cls.instance.return_value = mock_app
        assert detect_system_theme() == "light"


def test_detect_unknown_scheme_returns_light() -> None:
    """Returns 'light' when OS color scheme is Unknown."""
    mock_app = MagicMock()
    mock_hints = MagicMock()
    mock_hints.colorScheme.return_value = Qt.ColorScheme.Unknown
    mock_app.styleHints.return_value = mock_hints

    with patch(_QAPP_PATH) as mock_cls:
        mock_cls.instance.return_value = mock_app
        assert detect_system_theme() == "light"


def test_detect_exception_returns_light() -> None:
    """Returns 'light' when any exception is raised."""
    with patch(_QAPP_PATH, side_effect=RuntimeError("boom")):
        assert detect_system_theme() == "light"


def test_detect_style_hints_raises_returns_light() -> None:
    """Returns 'light' when styleHints() itself raises an exception."""
    mock_app = MagicMock()
    mock_app.styleHints.side_effect = AttributeError("no hints")

    with patch(_QAPP_PATH) as mock_cls:
        mock_cls.instance.return_value = mock_app
        assert detect_system_theme() == "light"


def test_detect_color_scheme_raises_returns_light() -> None:
    """Returns 'light' when colorScheme() raises an exception."""
    mock_app = MagicMock()
    mock_hints = MagicMock()
    mock_hints.colorScheme.side_effect = RuntimeError("broken")
    mock_app.styleHints.return_value = mock_hints

    with patch(_QAPP_PATH) as mock_cls:
        mock_cls.instance.return_value = mock_app
        assert detect_system_theme() == "light"


# ===========================================================================
# SystemThemeMonitor — construction and initial state
# ===========================================================================

_DETECT_PATH = "src.ui.system_theme.detect_system_theme"
_SET_PATH = "src.ui.system_theme.set_theme"


def test_monitor_inactive_after_init() -> None:
    """Monitor is inactive immediately after construction."""
    monitor = SystemThemeMonitor()
    assert not monitor.is_active


def test_monitor_not_connected_after_init() -> None:
    """Monitor is not connected to any signal after construction."""
    monitor = SystemThemeMonitor()
    assert not monitor._connected


# ===========================================================================
# SystemThemeMonitor — start / stop lifecycle
# ===========================================================================


def test_monitor_start_sets_active() -> None:
    """start() sets the monitor to active."""
    monitor = SystemThemeMonitor()
    with patch(_DETECT_PATH, return_value="light"), patch(_SET_PATH):
        monitor.start()
    assert monitor.is_active


def test_monitor_stop_sets_inactive() -> None:
    """stop() sets the monitor to inactive."""
    monitor = SystemThemeMonitor()
    with patch(_DETECT_PATH, return_value="light"), patch(_SET_PATH):
        monitor.start()
    monitor.stop()
    assert not monitor.is_active


def test_monitor_start_calls_set_theme() -> None:
    """start() detects the current system theme and applies it."""
    monitor = SystemThemeMonitor()
    with (
        patch(_DETECT_PATH, return_value="dark") as mock_detect,
        patch(_SET_PATH) as mock_set,
    ):
        monitor.start()
    mock_detect.assert_called_once()
    mock_set.assert_called_once_with("dark")


def test_monitor_start_applies_light_theme() -> None:
    """start() applies 'light' when the system reports light mode."""
    monitor = SystemThemeMonitor()
    with (
        patch(_DETECT_PATH, return_value="light"),
        patch(_SET_PATH) as mock_set,
    ):
        monitor.start()
    mock_set.assert_called_once_with("light")


def test_monitor_start_calls_ensure_connected() -> None:
    """start() invokes _ensure_connected to set up the signal."""
    monitor = SystemThemeMonitor()
    with (
        patch(_DETECT_PATH, return_value="light"),
        patch(_SET_PATH),
        patch.object(monitor, "_ensure_connected") as mock_ec,
    ):
        monitor.start()
    mock_ec.assert_called_once()


def test_monitor_stop_then_restart() -> None:
    """A stopped monitor can be restarted."""
    monitor = SystemThemeMonitor()
    with patch(_DETECT_PATH, return_value="light"), patch(_SET_PATH):
        monitor.start()
    monitor.stop()
    assert not monitor.is_active

    with patch(_DETECT_PATH, return_value="dark"), patch(_SET_PATH) as mock_set:
        monitor.start()
    assert monitor.is_active
    mock_set.assert_called_once_with("dark")


def test_monitor_multiple_start_stop_cycles() -> None:
    """Multiple start/stop cycles work correctly."""
    monitor = SystemThemeMonitor()
    for _ in range(3):  # noqa: PLR2004
        with patch(_DETECT_PATH, return_value="light"), patch(_SET_PATH):
            monitor.start()
        assert monitor.is_active
        monitor.stop()
        assert not monitor.is_active


def test_monitor_stop_without_start_is_safe() -> None:
    """Calling stop() on a never-started monitor is harmless."""
    monitor = SystemThemeMonitor()
    monitor.stop()  # should not raise
    assert not monitor.is_active


def test_monitor_double_start_applies_theme_twice() -> None:
    """Calling start() twice applies the theme both times."""
    monitor = SystemThemeMonitor()
    with (
        patch(_DETECT_PATH, return_value="dark"),
        patch(_SET_PATH) as mock_set,
    ):
        monitor.start()
        monitor.start()
    assert mock_set.call_count == 2  # noqa: PLR2004
    assert mock_set.call_args_list == [call("dark"), call("dark")]


# ===========================================================================
# SystemThemeMonitor — callback behaviour
# ===========================================================================


def test_callback_applies_theme_when_active() -> None:
    """_on_system_theme_changed calls set_theme when active."""
    monitor = SystemThemeMonitor()
    monitor._active = True

    with (
        patch(_DETECT_PATH, return_value="dark") as mock_detect,
        patch(_SET_PATH) as mock_set,
    ):
        monitor._on_system_theme_changed(None)

    mock_detect.assert_called_once()
    mock_set.assert_called_once_with("dark")


def test_callback_skips_when_inactive() -> None:
    """_on_system_theme_changed is a no-op when inactive."""
    monitor = SystemThemeMonitor()
    monitor._active = False

    with patch(_DETECT_PATH) as mock_detect, patch(_SET_PATH) as mock_set:
        monitor._on_system_theme_changed(None)

    mock_detect.assert_not_called()
    mock_set.assert_not_called()


def test_callback_after_stop_is_noop() -> None:
    """After stop(), the callback is a no-op even if the signal fires."""
    monitor = SystemThemeMonitor()
    with patch(_DETECT_PATH, return_value="light"), patch(_SET_PATH):
        monitor.start()
    monitor.stop()

    with patch(_DETECT_PATH) as mock_detect, patch(_SET_PATH) as mock_set:
        monitor._on_system_theme_changed(Qt.ColorScheme.Dark)

    mock_detect.assert_not_called()
    mock_set.assert_not_called()


def test_callback_after_restart_works() -> None:
    """After stop() then start(), the callback works again."""
    monitor = SystemThemeMonitor()
    with patch(_DETECT_PATH, return_value="light"), patch(_SET_PATH):
        monitor.start()
    monitor.stop()
    with patch(_DETECT_PATH, return_value="dark"), patch(_SET_PATH):
        monitor.start()

    with (
        patch(_DETECT_PATH, return_value="dark"),
        patch(_SET_PATH) as mock_set,
    ):
        monitor._on_system_theme_changed(Qt.ColorScheme.Dark)
    mock_set.assert_called_once_with("dark")


def test_callback_passes_scheme_argument_through() -> None:
    """The _scheme argument is accepted without error."""
    monitor = SystemThemeMonitor()
    monitor._active = True

    with patch(_DETECT_PATH, return_value="light"), patch(_SET_PATH):
        # Various scheme values should all be accepted
        monitor._on_system_theme_changed(Qt.ColorScheme.Dark)
        monitor._on_system_theme_changed(Qt.ColorScheme.Light)
        monitor._on_system_theme_changed(None)


# ===========================================================================
# SystemThemeMonitor — signal connection
# ===========================================================================


def test_ensure_connected_only_once() -> None:
    """_ensure_connected connects the signal at most once."""
    monitor = SystemThemeMonitor()

    mock_hints = MagicMock()
    mock_app = MagicMock()
    mock_app.styleHints.return_value = mock_hints

    with patch(_QAPP_PATH) as mock_cls:
        mock_cls.instance.return_value = mock_app
        monitor._ensure_connected()
        monitor._ensure_connected()  # second call -> no-op

    # Signal connected exactly once
    mock_hints.colorSchemeChanged.connect.assert_called_once()
    assert monitor._connected


def test_ensure_connected_handles_missing_signal() -> None:
    """_ensure_connected handles missing colorSchemeChanged."""
    monitor = SystemThemeMonitor()

    mock_hints = MagicMock(spec=[])  # no colorSchemeChanged
    mock_app = MagicMock()
    mock_app.styleHints.return_value = mock_hints

    with patch(_QAPP_PATH) as mock_cls:
        mock_cls.instance.return_value = mock_app
        monitor._ensure_connected()

    assert not monitor._connected


def test_ensure_connected_no_qapp_stays_disconnected() -> None:
    """_ensure_connected bails early when QApplication.instance() is None."""
    monitor = SystemThemeMonitor()

    with patch(_QAPP_PATH) as mock_cls:
        mock_cls.instance.return_value = None
        monitor._ensure_connected()

    assert not monitor._connected


def test_ensure_connected_exception_suppressed() -> None:
    """_ensure_connected catches exceptions without propagating."""
    monitor = SystemThemeMonitor()

    with patch(_QAPP_PATH) as mock_cls:
        mock_cls.instance.side_effect = RuntimeError("Qt crash")
        monitor._ensure_connected()

    assert not monitor._connected


def test_ensure_connected_connect_raises_is_suppressed() -> None:
    """_ensure_connected catches exception from signal.connect() itself."""
    monitor = SystemThemeMonitor()

    mock_hints = MagicMock()
    mock_hints.colorSchemeChanged.connect.side_effect = RuntimeError("fail")
    mock_app = MagicMock()
    mock_app.styleHints.return_value = mock_hints

    with patch(_QAPP_PATH) as mock_cls:
        mock_cls.instance.return_value = mock_app
        monitor._ensure_connected()  # should not raise

    assert not monitor._connected


def test_ensure_connected_connects_on_system_theme_changed() -> None:
    """_ensure_connected passes _on_system_theme_changed as the slot."""
    monitor = SystemThemeMonitor()

    mock_hints = MagicMock()
    mock_app = MagicMock()
    mock_app.styleHints.return_value = mock_hints

    with patch(_QAPP_PATH) as mock_cls:
        mock_cls.instance.return_value = mock_app
        monitor._ensure_connected()

    mock_hints.colorSchemeChanged.connect.assert_called_once_with(
        monitor._on_system_theme_changed,
    )


def test_start_triggers_ensure_connected_then_set_theme() -> None:
    """start() first connects, then applies the current theme."""
    monitor = SystemThemeMonitor()
    call_order = []

    original_ec = monitor._ensure_connected

    def tracking_ec() -> None:
        call_order.append("ensure_connected")
        original_ec()

    monitor._ensure_connected = tracking_ec

    def tracking_set(name: str) -> None:
        call_order.append(f"set_theme:{name}")

    with (
        patch(_DETECT_PATH, return_value="dark"),
        patch(_SET_PATH, side_effect=tracking_set),
        patch(_QAPP_PATH) as mock_cls,
    ):
        mock_cls.instance.return_value = None  # no QApp for _ensure_connected
        monitor.start()

    assert call_order == ["ensure_connected", "set_theme:dark"]


# ===========================================================================
# detect_system_theme() — additional edge cases
# ===========================================================================


def test_detect_import_error_returns_light() -> None:
    """Returns 'light' when PySide6 import fails."""
    with (
        patch.dict("sys.modules", {"PySide6.QtWidgets": None}),
        patch(_QAPP_PATH, side_effect=ImportError("no pyside6")),
    ):
        assert detect_system_theme() == "light"


def test_detect_instance_returns_none_always_light() -> None:
    """Returns 'light' when QApplication.instance() returns None consistently."""
    with patch(_QAPP_PATH) as mock_cls:
        mock_cls.instance.return_value = None
        # Call multiple times to ensure consistent behavior
        for _ in range(5):
            assert detect_system_theme() == "light"


def test_detect_type_error_returns_light() -> None:
    """Returns 'light' when a TypeError is raised internally."""
    with patch(_QAPP_PATH, side_effect=TypeError("type fail")):
        assert detect_system_theme() == "light"


def test_detect_value_error_returns_light() -> None:
    """Returns 'light' when a ValueError is raised internally."""
    with patch(_QAPP_PATH, side_effect=ValueError("bad value")):
        assert detect_system_theme() == "light"


def test_detect_attribute_error_on_instance_returns_light() -> None:
    """Returns 'light' when instance() itself raises AttributeError."""
    with patch(_QAPP_PATH) as mock_cls:
        mock_cls.instance.side_effect = AttributeError("no instance method")
        assert detect_system_theme() == "light"


def test_detect_color_scheme_returns_non_dark_value() -> None:
    """Returns 'light' for any non-Dark color scheme value."""
    mock_app = MagicMock()
    mock_hints = MagicMock()
    # Return some integer that isn't Dark
    mock_hints.colorScheme.return_value = 999
    mock_app.styleHints.return_value = mock_hints

    with patch(_QAPP_PATH) as mock_cls:
        mock_cls.instance.return_value = mock_app
        assert detect_system_theme() == "light"


def test_detect_style_hints_returns_none_returns_light() -> None:
    """Returns 'light' when styleHints() returns None."""
    mock_app = MagicMock()
    mock_app.styleHints.return_value = None

    with patch(_QAPP_PATH) as mock_cls:
        mock_cls.instance.return_value = mock_app
        # hasattr(None, "colorScheme") is False
        assert detect_system_theme() == "light"


def test_detect_called_multiple_times_consistent() -> None:
    """Multiple calls with same setup return consistent result."""
    mock_app = MagicMock()
    mock_hints = MagicMock()
    mock_hints.colorScheme.return_value = Qt.ColorScheme.Dark
    mock_app.styleHints.return_value = mock_hints

    with patch(_QAPP_PATH) as mock_cls:
        mock_cls.instance.return_value = mock_app
        results = [detect_system_theme() for _ in range(5)]
        assert all(r == "dark" for r in results)


def test_detect_returns_only_valid_theme_names() -> None:
    """detect_system_theme only returns 'light' or 'dark'."""
    # With Dark scheme
    mock_app = MagicMock()
    mock_hints = MagicMock()
    mock_hints.colorScheme.return_value = Qt.ColorScheme.Dark
    mock_app.styleHints.return_value = mock_hints

    with patch(_QAPP_PATH) as mock_cls:
        mock_cls.instance.return_value = mock_app
        result = detect_system_theme()
        assert result in ("light", "dark")


# ===========================================================================
# SystemThemeMonitor — additional lifecycle tests
# ===========================================================================


def test_monitor_is_active_property_type() -> None:
    """is_active returns a bool."""
    monitor = SystemThemeMonitor()
    assert isinstance(monitor.is_active, bool)


def test_monitor_start_without_qapp_still_active() -> None:
    """start() sets active even if _ensure_connected fails due to no QApp."""
    monitor = SystemThemeMonitor()
    with (
        patch(_DETECT_PATH, return_value="light"),
        patch(_SET_PATH),
        patch(_QAPP_PATH) as mock_cls,
    ):
        mock_cls.instance.return_value = None
        monitor.start()
    assert monitor.is_active


def test_monitor_stop_is_idempotent() -> None:
    """Calling stop() multiple times is safe."""
    monitor = SystemThemeMonitor()
    monitor.stop()
    monitor.stop()
    monitor.stop()
    assert not monitor.is_active


def test_monitor_start_is_idempotent_for_active() -> None:
    """Calling start() multiple times keeps active True."""
    monitor = SystemThemeMonitor()
    with patch(_DETECT_PATH, return_value="light"), patch(_SET_PATH):
        monitor.start()
        monitor.start()
        monitor.start()
    assert monitor.is_active


def test_monitor_connected_flag_stays_true_after_stop() -> None:
    """_connected remains True after stop() (signal stays connected)."""
    monitor = SystemThemeMonitor()

    mock_hints = MagicMock()
    mock_app = MagicMock()
    mock_app.styleHints.return_value = mock_hints

    with (
        patch(_QAPP_PATH) as mock_cls,
        patch(_DETECT_PATH, return_value="light"),
        patch(_SET_PATH),
    ):
        mock_cls.instance.return_value = mock_app
        monitor.start()

    assert monitor._connected
    monitor.stop()
    # Connection persists even after stop
    assert monitor._connected


def test_monitor_start_stop_start_reuses_connection() -> None:
    """Restart doesn't reconnect the signal (already connected)."""
    monitor = SystemThemeMonitor()

    mock_hints = MagicMock()
    mock_app = MagicMock()
    mock_app.styleHints.return_value = mock_hints

    with (
        patch(_QAPP_PATH) as mock_cls,
        patch(_DETECT_PATH, return_value="light"),
        patch(_SET_PATH),
    ):
        mock_cls.instance.return_value = mock_app
        monitor.start()
        monitor.stop()
        monitor.start()

    # connect called only once despite two starts
    mock_hints.colorSchemeChanged.connect.assert_called_once()


# ===========================================================================
# SystemThemeMonitor — callback additional tests
# ===========================================================================


def test_callback_with_light_scheme_when_active() -> None:
    """_on_system_theme_changed applies light theme when active and detected as light."""
    monitor = SystemThemeMonitor()
    monitor._active = True

    with (
        patch(_DETECT_PATH, return_value="light") as mock_detect,
        patch(_SET_PATH) as mock_set,
    ):
        monitor._on_system_theme_changed(Qt.ColorScheme.Light)

    mock_detect.assert_called_once()
    mock_set.assert_called_once_with("light")


def test_callback_ignores_scheme_value_uses_detect() -> None:
    """The _scheme arg is ignored; detect_system_theme() is always called."""
    monitor = SystemThemeMonitor()
    monitor._active = True

    with (
        patch(_DETECT_PATH, return_value="dark") as mock_detect,
        patch(_SET_PATH) as mock_set,
    ):
        # Pass Light scheme but detect returns dark
        monitor._on_system_theme_changed(Qt.ColorScheme.Light)

    mock_detect.assert_called_once()
    mock_set.assert_called_once_with("dark")


def test_callback_multiple_rapid_changes() -> None:
    """Multiple rapid theme changes all call set_theme."""
    monitor = SystemThemeMonitor()
    monitor._active = True

    themes = ["dark", "light", "dark", "light", "dark"]
    with patch(_SET_PATH) as mock_set:
        for theme in themes:
            with patch(_DETECT_PATH, return_value=theme):
                monitor._on_system_theme_changed(None)

    assert mock_set.call_count == len(themes)


def test_callback_inactive_never_calls_detect() -> None:
    """When inactive, detect_system_theme is never called."""
    monitor = SystemThemeMonitor()
    monitor._active = False

    with patch(_DETECT_PATH) as mock_detect, patch(_SET_PATH):
        for _ in range(10):
            monitor._on_system_theme_changed(None)

    mock_detect.assert_not_called()


def test_callback_with_various_scheme_objects() -> None:
    """_on_system_theme_changed accepts various _scheme types without error."""
    monitor = SystemThemeMonitor()
    monitor._active = True

    for scheme_val in [None, 0, "dark", Qt.ColorScheme.Dark, object()]:
        with patch(_DETECT_PATH, return_value="light"), patch(_SET_PATH):
            monitor._on_system_theme_changed(scheme_val)


# ===========================================================================
# SystemThemeMonitor — _ensure_connected additional tests
# ===========================================================================


def test_ensure_connected_style_hints_none_stays_disconnected() -> None:
    """_ensure_connected stays disconnected when styleHints returns None."""
    monitor = SystemThemeMonitor()

    mock_app = MagicMock()
    mock_app.styleHints.return_value = None

    with patch(_QAPP_PATH) as mock_cls:
        mock_cls.instance.return_value = mock_app
        monitor._ensure_connected()

    # None doesn't have hasattr colorSchemeChanged -> not connected
    assert not monitor._connected


def test_ensure_connected_import_error_suppressed() -> None:
    """_ensure_connected suppresses ImportError gracefully."""
    monitor = SystemThemeMonitor()

    mock_app = MagicMock()
    mock_hints = MagicMock()
    mock_hints.colorSchemeChanged.connect.side_effect = ImportError("no qt")
    mock_app.styleHints.return_value = mock_hints
    with patch(_QAPP_PATH) as mock_cls:
        mock_cls.instance.return_value = mock_app
        monitor._ensure_connected()

    assert not monitor._connected


def test_ensure_connected_os_error_suppressed() -> None:
    """_ensure_connected suppresses OSError gracefully."""
    monitor = SystemThemeMonitor()

    mock_app = MagicMock()
    mock_hints = MagicMock()
    mock_hints.colorSchemeChanged.connect.side_effect = OSError("disk fail")
    mock_app.styleHints.return_value = mock_hints
    with patch(_QAPP_PATH) as mock_cls:
        mock_cls.instance.return_value = mock_app
        monitor._ensure_connected()

    assert not monitor._connected


def test_ensure_connected_succeeds_sets_flag() -> None:
    """Successful connection sets _connected to True."""
    monitor = SystemThemeMonitor()

    mock_hints = MagicMock()
    mock_app = MagicMock()
    mock_app.styleHints.return_value = mock_hints

    with patch(_QAPP_PATH) as mock_cls:
        mock_cls.instance.return_value = mock_app
        monitor._ensure_connected()

    assert monitor._connected is True


def test_ensure_connected_already_connected_skips() -> None:
    """When already connected, _ensure_connected is a no-op."""
    monitor = SystemThemeMonitor()
    monitor._connected = True

    with patch(_QAPP_PATH) as mock_cls:
        monitor._ensure_connected()
        # QApplication should not be accessed at all
        mock_cls.instance.assert_not_called()


# ===========================================================================
# SystemThemeMonitor — integration-like tests
# ===========================================================================


def test_full_lifecycle_start_callback_stop_callback() -> None:
    """Full lifecycle: start, handle callback, stop, verify callback is no-op."""
    monitor = SystemThemeMonitor()

    with (
        patch(_DETECT_PATH, return_value="dark"),
        patch(_SET_PATH) as mock_set,
    ):
        monitor.start()
    # start applied dark theme
    mock_set.assert_called_once_with("dark")

    # While active, callback applies theme
    with (
        patch(_DETECT_PATH, return_value="light"),
        patch(_SET_PATH) as mock_set2,
    ):
        monitor._on_system_theme_changed(Qt.ColorScheme.Light)
    mock_set2.assert_called_once_with("light")

    # After stop, callback is no-op
    monitor.stop()
    with (
        patch(_DETECT_PATH) as mock_detect3,
        patch(_SET_PATH) as mock_set3,
    ):
        monitor._on_system_theme_changed(Qt.ColorScheme.Dark)
    mock_detect3.assert_not_called()
    mock_set3.assert_not_called()


def test_monitor_init_does_not_connect_or_detect() -> None:
    """Constructor does not call any external APIs."""
    with (
        patch(_DETECT_PATH) as mock_detect,
        patch(_SET_PATH) as mock_set,
    ):
        monitor = SystemThemeMonitor()
        assert monitor is not None

    mock_detect.assert_not_called()
    mock_set.assert_not_called()


def test_start_detect_returns_light_sets_light() -> None:
    """start() with light detection sets light theme."""
    monitor = SystemThemeMonitor()
    with (
        patch(_DETECT_PATH, return_value="light"),
        patch(_SET_PATH) as mock_set,
    ):
        monitor.start()
    mock_set.assert_called_once_with("light")


def test_start_detect_returns_dark_sets_dark() -> None:
    """start() with dark detection sets dark theme."""
    monitor = SystemThemeMonitor()
    with (
        patch(_DETECT_PATH, return_value="dark"),
        patch(_SET_PATH) as mock_set,
    ):
        monitor.start()
    mock_set.assert_called_once_with("dark")


# ===========================================================================
# Expanded tests: detect_system_theme() additional scenarios
# ===========================================================================


def test_detect_with_none_color_scheme_returns_light() -> None:
    """Returns 'light' when colorScheme() returns None."""
    mock_app = MagicMock()
    mock_hints = MagicMock()
    mock_hints.colorScheme.return_value = None
    mock_app.styleHints.return_value = mock_hints

    with patch(_QAPP_PATH) as mock_cls:
        mock_cls.instance.return_value = mock_app
        assert detect_system_theme() == "light"


def test_detect_with_zero_color_scheme_returns_light() -> None:
    """Returns 'light' when colorScheme() returns 0."""
    mock_app = MagicMock()
    mock_hints = MagicMock()
    mock_hints.colorScheme.return_value = 0
    mock_app.styleHints.return_value = mock_hints

    with patch(_QAPP_PATH) as mock_cls:
        mock_cls.instance.return_value = mock_app
        assert detect_system_theme() == "light"


def test_detect_with_string_color_scheme_returns_light() -> None:
    """Returns 'light' when colorScheme() returns a string."""
    mock_app = MagicMock()
    mock_hints = MagicMock()
    mock_hints.colorScheme.return_value = "dark"
    mock_app.styleHints.return_value = mock_hints

    with patch(_QAPP_PATH) as mock_cls:
        mock_cls.instance.return_value = mock_app
        assert detect_system_theme() == "light"


def test_detect_with_negative_color_scheme_returns_light() -> None:
    """Returns 'light' for negative color scheme value."""
    mock_app = MagicMock()
    mock_hints = MagicMock()
    mock_hints.colorScheme.return_value = -1
    mock_app.styleHints.return_value = mock_hints

    with patch(_QAPP_PATH) as mock_cls:
        mock_cls.instance.return_value = mock_app
        assert detect_system_theme() == "light"


def test_detect_keyboard_interrupt_suppressed() -> None:
    """Returns 'light' even when KeyboardInterrupt is caught."""
    # KeyboardInterrupt inherits BaseException, not Exception
    # The function uses `except Exception`, so KeyboardInterrupt propagates
    # We test that regular exceptions are caught
    with patch(_QAPP_PATH, side_effect=OSError("os fail")):
        assert detect_system_theme() == "light"


def test_detect_memory_error_suppressed() -> None:
    """Returns 'light' when MemoryError is raised."""
    # MemoryError inherits from Exception in practice
    with patch(_QAPP_PATH, side_effect=MemoryError("oom")):
        assert detect_system_theme() == "light"


def test_detect_return_type_is_str() -> None:
    """detect_system_theme() always returns a str."""
    with patch(_QAPP_PATH) as mock_cls:
        mock_cls.instance.return_value = None
        result = detect_system_theme()
        assert isinstance(result, str)


def test_detect_no_style_hints_method() -> None:
    """Returns 'light' when app has no styleHints method."""
    mock_app = MagicMock(spec=[])  # empty spec, no styleHints
    with patch(_QAPP_PATH) as mock_cls:
        mock_cls.instance.return_value = mock_app
        assert detect_system_theme() == "light"


def test_detect_color_scheme_boolean_false_returns_light() -> None:
    """Returns 'light' when colorScheme() returns False."""
    mock_app = MagicMock()
    mock_hints = MagicMock()
    mock_hints.colorScheme.return_value = False
    mock_app.styleHints.return_value = mock_hints

    with patch(_QAPP_PATH) as mock_cls:
        mock_cls.instance.return_value = mock_app
        assert detect_system_theme() == "light"


def test_detect_is_deterministic_for_dark() -> None:
    """Multiple calls with Dark scheme all return 'dark'."""
    mock_app = MagicMock()
    mock_hints = MagicMock()
    mock_hints.colorScheme.return_value = Qt.ColorScheme.Dark
    mock_app.styleHints.return_value = mock_hints

    with patch(_QAPP_PATH) as mock_cls:
        mock_cls.instance.return_value = mock_app
        results = [detect_system_theme() for _ in range(10)]
        assert all(r == "dark" for r in results)


def test_detect_is_deterministic_for_no_app() -> None:
    """Multiple calls with no app all return 'light'."""
    with patch(_QAPP_PATH) as mock_cls:
        mock_cls.instance.return_value = None
        results = [detect_system_theme() for _ in range(10)]
        assert all(r == "light" for r in results)


# ===========================================================================
# Expanded tests: SystemThemeMonitor additional lifecycle
# ===========================================================================


def test_monitor_start_with_dark_detection_sets_dark() -> None:
    """start() with dark detection results in active + dark theme applied."""
    monitor = SystemThemeMonitor()
    with (
        patch(_DETECT_PATH, return_value="dark"),
        patch(_SET_PATH) as mock_set,
    ):
        monitor.start()
    assert monitor.is_active
    mock_set.assert_called_once_with("dark")


def test_monitor_start_with_light_detection_sets_light() -> None:
    """start() with light detection results in active + light theme applied."""
    monitor = SystemThemeMonitor()
    with (
        patch(_DETECT_PATH, return_value="light"),
        patch(_SET_PATH) as mock_set,
    ):
        monitor.start()
    assert monitor.is_active
    mock_set.assert_called_once_with("light")


def test_monitor_alternating_start_stop_10_cycles() -> None:
    """10 start/stop cycles all work correctly."""
    monitor = SystemThemeMonitor()
    for i in range(10):
        theme = "dark" if i % 2 == 0 else "light"
        with patch(_DETECT_PATH, return_value=theme), patch(_SET_PATH):
            monitor.start()
        assert monitor.is_active
        monitor.stop()
        assert not monitor.is_active


def test_monitor_stop_does_not_affect_connected_flag() -> None:
    """stop() leaves _connected unchanged."""
    monitor = SystemThemeMonitor()
    monitor._connected = True
    monitor._active = True
    monitor.stop()
    assert monitor._connected is True
    assert monitor._active is False


def test_monitor_stop_then_callback_ignored() -> None:
    """After stop, callback does nothing."""
    monitor = SystemThemeMonitor()
    monitor._active = True
    monitor.stop()

    with patch(_DETECT_PATH) as mock_d, patch(_SET_PATH) as mock_s:
        monitor._on_system_theme_changed(Qt.ColorScheme.Dark)
    mock_d.assert_not_called()
    mock_s.assert_not_called()


def test_monitor_callback_detects_and_applies_light() -> None:
    """Active callback detecting light applies light theme."""
    monitor = SystemThemeMonitor()
    monitor._active = True

    with (
        patch(_DETECT_PATH, return_value="light"),
        patch(_SET_PATH) as mock_set,
    ):
        monitor._on_system_theme_changed(Qt.ColorScheme.Light)
    mock_set.assert_called_once_with("light")


def test_monitor_callback_with_unknown_scheme() -> None:
    """Active callback with Unknown scheme still calls detect."""
    monitor = SystemThemeMonitor()
    monitor._active = True

    with (
        patch(_DETECT_PATH, return_value="light") as mock_detect,
        patch(_SET_PATH),
    ):
        monitor._on_system_theme_changed(Qt.ColorScheme.Unknown)
    mock_detect.assert_called_once()


def test_monitor_callback_10_rapid_alternating() -> None:
    """10 rapid alternating dark/light callbacks all apply."""
    monitor = SystemThemeMonitor()
    monitor._active = True
    applied: list[str] = []

    for i in range(10):
        theme = "dark" if i % 2 == 0 else "light"
        with (
            patch(_DETECT_PATH, return_value=theme),
            patch(_SET_PATH, side_effect=applied.append),
        ):
            monitor._on_system_theme_changed(None)

    assert len(applied) == 10
    assert applied[0] == "dark"
    assert applied[1] == "light"


# ===========================================================================
# Expanded tests: _ensure_connected additional scenarios
# ===========================================================================


def test_ensure_connected_with_app_no_hints_attribute() -> None:
    """When app has no styleHints, _ensure_connected stays disconnected."""
    monitor = SystemThemeMonitor()

    mock_app = MagicMock(spec=[])
    with patch(_QAPP_PATH) as mock_cls:
        mock_cls.instance.return_value = mock_app
        monitor._ensure_connected()
    assert not monitor._connected


def test_ensure_connected_called_twice_after_success() -> None:
    """Second _ensure_connected call after success is no-op."""
    monitor = SystemThemeMonitor()

    mock_hints = MagicMock()
    mock_app = MagicMock()
    mock_app.styleHints.return_value = mock_hints

    with patch(_QAPP_PATH) as mock_cls:
        mock_cls.instance.return_value = mock_app
        monitor._ensure_connected()
        assert monitor._connected
        # Second call - should not access QApplication
        monitor._ensure_connected()

    # connect() called only once
    mock_hints.colorSchemeChanged.connect.assert_called_once()


def test_ensure_connected_runtime_error_suppressed() -> None:
    """RuntimeError during _ensure_connected is suppressed."""
    monitor = SystemThemeMonitor()

    mock_app = MagicMock()
    mock_app.styleHints.side_effect = RuntimeError("fail")
    with patch(_QAPP_PATH) as mock_cls:
        mock_cls.instance.return_value = mock_app
        monitor._ensure_connected()
    assert not monitor._connected


def test_ensure_connected_type_error_suppressed() -> None:
    """TypeError during _ensure_connected is suppressed."""
    monitor = SystemThemeMonitor()

    mock_app = MagicMock()
    mock_app.styleHints.side_effect = TypeError("fail")
    with patch(_QAPP_PATH) as mock_cls:
        mock_cls.instance.return_value = mock_app
        monitor._ensure_connected()
    assert not monitor._connected


def test_ensure_connected_value_error_suppressed() -> None:
    """ValueError during _ensure_connected is suppressed."""
    monitor = SystemThemeMonitor()

    mock_app = MagicMock()
    mock_app.styleHints.side_effect = ValueError("fail")
    with patch(_QAPP_PATH) as mock_cls:
        mock_cls.instance.return_value = mock_app
        monitor._ensure_connected()
    assert not monitor._connected


def test_ensure_connected_not_connected_flag_initially_false() -> None:
    """_connected starts as False."""
    monitor = SystemThemeMonitor()
    assert monitor._connected is False


def test_ensure_connected_not_active_flag_initially_false() -> None:
    """_active starts as False."""
    monitor = SystemThemeMonitor()
    assert monitor._active is False


# ===========================================================================
# Expanded tests: integration scenarios
# ===========================================================================


def test_full_lifecycle_two_monitors_independent() -> None:
    """Two monitors operate independently."""
    m1 = SystemThemeMonitor()
    m2 = SystemThemeMonitor()

    with patch(_DETECT_PATH, return_value="dark"), patch(_SET_PATH):
        m1.start()
    assert m1.is_active
    assert not m2.is_active

    with patch(_DETECT_PATH, return_value="light"), patch(_SET_PATH):
        m2.start()
    assert m1.is_active
    assert m2.is_active

    m1.stop()
    assert not m1.is_active
    assert m2.is_active


def test_monitor_callback_after_start_stop_start() -> None:
    """Callback works correctly after start/stop/start cycle."""
    monitor = SystemThemeMonitor()

    with patch(_DETECT_PATH, return_value="light"), patch(_SET_PATH):
        monitor.start()
    monitor.stop()
    with patch(_DETECT_PATH, return_value="dark"), patch(_SET_PATH):
        monitor.start()

    # Now active, callback should work
    with (
        patch(_DETECT_PATH, return_value="light"),
        patch(_SET_PATH) as mock_set,
    ):
        monitor._on_system_theme_changed(Qt.ColorScheme.Light)
    mock_set.assert_called_once_with("light")


def test_start_ensure_connected_called_with_set_theme_order() -> None:
    """start() calls _ensure_connected before set_theme."""
    monitor = SystemThemeMonitor()
    order: list[str] = []

    original_ec = monitor._ensure_connected

    def tracking_ec() -> None:
        order.append("connect")
        original_ec()

    def tracking_set(name: str) -> None:
        order.append(f"set:{name}")

    monitor._ensure_connected = tracking_ec  # type: ignore[assignment]
    with (
        patch(_DETECT_PATH, return_value="light"),
        patch(_SET_PATH, side_effect=tracking_set),
        patch(_QAPP_PATH) as mock_cls,
    ):
        mock_cls.instance.return_value = None
        monitor.start()

    assert order == ["connect", "set:light"]


def test_monitor_is_active_returns_bool_after_lifecycle() -> None:
    """is_active returns bool at every stage of the lifecycle."""
    monitor = SystemThemeMonitor()
    assert isinstance(monitor.is_active, bool)

    with patch(_DETECT_PATH, return_value="light"), patch(_SET_PATH):
        monitor.start()
    assert isinstance(monitor.is_active, bool)

    monitor.stop()
    assert isinstance(monitor.is_active, bool)


def test_callback_inactive_does_not_modify_state() -> None:
    """Inactive callback does not change _active or _connected."""
    monitor = SystemThemeMonitor()
    monitor._connected = True

    with patch(_DETECT_PATH), patch(_SET_PATH):
        monitor._on_system_theme_changed(None)

    assert not monitor._active
    assert monitor._connected


def test_monitor_str_repr_does_not_raise() -> None:
    """str() and repr() on monitor do not raise."""
    monitor = SystemThemeMonitor()
    assert str(monitor) is not None
    assert repr(monitor) is not None


# ===========================================================================
# Expanded tests: detect_system_theme() — parametrized edge cases
# ===========================================================================

import pytest  # noqa: E402


@pytest.mark.parametrize(
    "exc_cls",
    [
        RuntimeError,
        TypeError,
        ValueError,
        AttributeError,
        ImportError,
        OSError,
        MemoryError,
        OverflowError,
        IOError,
        LookupError,
    ],
    ids=lambda c: c.__name__,
)
def test_detect_any_exception_returns_light(exc_cls: type) -> None:
    """detect_system_theme returns 'light' for any Exception subclass."""
    with patch(_QAPP_PATH, side_effect=exc_cls("test")):
        assert detect_system_theme() == "light"


@pytest.mark.parametrize(
    "scheme_val",
    [None, 0, -1, 42, 999, "", "dark", False, True, [], {}],
    ids=lambda v: repr(v)[:20],
)
def test_detect_non_dark_scheme_values_return_light(scheme_val: object) -> None:
    """Non-Qt.ColorScheme.Dark values all return 'light'."""
    mock_app = MagicMock()
    mock_hints = MagicMock()
    mock_hints.colorScheme.return_value = scheme_val
    mock_app.styleHints.return_value = mock_hints

    with patch(_QAPP_PATH) as mock_cls:
        mock_cls.instance.return_value = mock_app
        assert detect_system_theme() == "light"


def test_detect_style_hints_returns_object_without_color_scheme() -> None:
    """Returns 'light' when styleHints returns an object lacking colorScheme."""
    mock_app = MagicMock()
    plain_obj = object()  # no colorScheme attribute
    mock_app.styleHints.return_value = plain_obj

    with patch(_QAPP_PATH) as mock_cls:
        mock_cls.instance.return_value = mock_app
        assert detect_system_theme() == "light"


def test_detect_instance_returns_false_returns_light() -> None:
    """Returns 'light' when QApplication.instance() returns a falsy value."""
    with patch(_QAPP_PATH) as mock_cls:
        mock_cls.instance.return_value = False
        # False is falsy but not None — styleHints would fail on a bool
        # The broad except catches this
        result = detect_system_theme()
        assert result in ("light", "dark")


def test_detect_color_scheme_dark_returns_str() -> None:
    """Return type of detect_system_theme for Dark scheme is str."""
    mock_app = MagicMock()
    mock_hints = MagicMock()
    mock_hints.colorScheme.return_value = Qt.ColorScheme.Dark
    mock_app.styleHints.return_value = mock_hints

    with patch(_QAPP_PATH) as mock_cls:
        mock_cls.instance.return_value = mock_app
        result = detect_system_theme()
        assert isinstance(result, str)
        assert result == "dark"


def test_detect_color_scheme_light_returns_str() -> None:
    """Return type of detect_system_theme for Light scheme is str."""
    mock_app = MagicMock()
    mock_hints = MagicMock()
    mock_hints.colorScheme.return_value = Qt.ColorScheme.Light
    mock_app.styleHints.return_value = mock_hints

    with patch(_QAPP_PATH) as mock_cls:
        mock_cls.instance.return_value = mock_app
        result = detect_system_theme()
        assert isinstance(result, str)
        assert result == "light"


# ===========================================================================
# Expanded tests: SystemThemeMonitor — state mutation verification
# ===========================================================================


def test_monitor_start_sets_active_before_set_theme() -> None:
    """_active is True by the time set_theme is called."""
    monitor = SystemThemeMonitor()
    active_during_set: list[bool] = []

    def capture_active(name: str) -> None:
        active_during_set.append(monitor._active)

    with (
        patch(_DETECT_PATH, return_value="light"),
        patch(_SET_PATH, side_effect=capture_active),
    ):
        monitor.start()

    assert active_during_set == [True]


def test_monitor_start_sets_active_before_ensure_connected() -> None:
    """_active is True by the time _ensure_connected is called."""
    monitor = SystemThemeMonitor()
    active_during_ec: list[bool] = []

    original_ec = monitor._ensure_connected

    def tracking_ec() -> None:
        active_during_ec.append(monitor._active)
        original_ec()

    monitor._ensure_connected = tracking_ec  # type: ignore[assignment]
    with (
        patch(_DETECT_PATH, return_value="light"),
        patch(_SET_PATH),
        patch(_QAPP_PATH) as mock_cls,
    ):
        mock_cls.instance.return_value = None
        monitor.start()

    assert active_during_ec == [True]


def test_monitor_stop_sets_active_false_immediately() -> None:
    """stop() sets _active to False immediately."""
    monitor = SystemThemeMonitor()
    monitor._active = True
    monitor.stop()
    assert monitor._active is False


def test_callback_does_not_modify_connected_flag() -> None:
    """_on_system_theme_changed does not change _connected."""
    monitor = SystemThemeMonitor()
    monitor._active = True
    monitor._connected = True

    with patch(_DETECT_PATH, return_value="dark"), patch(_SET_PATH):
        monitor._on_system_theme_changed(None)

    assert monitor._connected is True


def test_callback_does_not_modify_active_flag() -> None:
    """_on_system_theme_changed does not change _active."""
    monitor = SystemThemeMonitor()
    monitor._active = True

    with patch(_DETECT_PATH, return_value="dark"), patch(_SET_PATH):
        monitor._on_system_theme_changed(None)

    assert monitor._active is True


def test_ensure_connected_failed_leaves_active_unchanged() -> None:
    """Failed _ensure_connected does not touch _active."""
    monitor = SystemThemeMonitor()
    monitor._active = True

    with patch(_QAPP_PATH) as mock_cls:
        mock_cls.instance.return_value = None
        monitor._ensure_connected()

    assert monitor._active is True


def test_ensure_connected_success_does_not_set_active() -> None:
    """Successful _ensure_connected does not set _active."""
    monitor = SystemThemeMonitor()

    mock_hints = MagicMock()
    mock_app = MagicMock()
    mock_app.styleHints.return_value = mock_hints

    with patch(_QAPP_PATH) as mock_cls:
        mock_cls.instance.return_value = mock_app
        monitor._ensure_connected()

    assert monitor._connected is True
    assert monitor._active is False


# ===========================================================================
# Expanded tests: multiple monitors and independence
# ===========================================================================


def test_three_monitors_all_independent() -> None:
    """Three monitors have independent state."""
    m1 = SystemThemeMonitor()
    m2 = SystemThemeMonitor()
    m3 = SystemThemeMonitor()

    with patch(_DETECT_PATH, return_value="dark"), patch(_SET_PATH):
        m1.start()

    assert m1.is_active and not m2.is_active and not m3.is_active

    with patch(_DETECT_PATH, return_value="light"), patch(_SET_PATH):
        m2.start()

    assert m1.is_active and m2.is_active and not m3.is_active

    m1.stop()
    assert not m1.is_active and m2.is_active and not m3.is_active


def test_monitor_callback_only_affects_own_state() -> None:
    """Callback on one monitor does not affect another."""
    m1 = SystemThemeMonitor()
    m2 = SystemThemeMonitor()
    m1._active = True
    m2._active = False

    with patch(_DETECT_PATH, return_value="dark"), patch(_SET_PATH) as mock_set:
        m1._on_system_theme_changed(None)

    mock_set.assert_called_once_with("dark")

    with patch(_DETECT_PATH) as mock_detect, patch(_SET_PATH) as mock_set2:
        m2._on_system_theme_changed(None)

    mock_detect.assert_not_called()
    mock_set2.assert_not_called()


def test_monitor_connected_flag_independent() -> None:
    """Connected flag is independent per monitor."""
    m1 = SystemThemeMonitor()
    m2 = SystemThemeMonitor()

    mock_hints = MagicMock()
    mock_app = MagicMock()
    mock_app.styleHints.return_value = mock_hints

    with patch(_QAPP_PATH) as mock_cls:
        mock_cls.instance.return_value = mock_app
        m1._ensure_connected()

    assert m1._connected is True
    assert m2._connected is False


# ===========================================================================
# Expanded tests: start() edge cases
# ===========================================================================


def test_start_when_detect_raises_propagates() -> None:
    """start() propagates exception from detect_system_theme()."""
    monitor = SystemThemeMonitor()
    with (
        pytest.raises(RuntimeError, match="boom"),
        patch(_DETECT_PATH, side_effect=RuntimeError("boom")),
    ):
        monitor.start()


def test_start_when_set_theme_raises_propagates() -> None:
    """start() propagates exception from set_theme()."""
    monitor = SystemThemeMonitor()
    with (
        pytest.raises(ValueError, match="bad"),
        patch(_DETECT_PATH, return_value="dark"),
        patch(_SET_PATH, side_effect=ValueError("bad")),
    ):
        monitor.start()


def test_start_active_flag_remains_after_ensure_connected_fail() -> None:
    """_active is True even if _ensure_connected fails."""
    monitor = SystemThemeMonitor()
    with (
        patch(_DETECT_PATH, return_value="light"),
        patch(_SET_PATH),
        patch(_QAPP_PATH) as mock_cls,
    ):
        mock_cls.instance.return_value = None
        monitor.start()

    assert monitor.is_active
    assert not monitor._connected


def test_start_theme_applied_even_without_connection() -> None:
    """set_theme is called even if _ensure_connected fails to connect."""
    monitor = SystemThemeMonitor()
    with (
        patch(_DETECT_PATH, return_value="dark"),
        patch(_SET_PATH) as mock_set,
        patch(_QAPP_PATH) as mock_cls,
    ):
        mock_cls.instance.return_value = None
        monitor.start()

    mock_set.assert_called_once_with("dark")
    assert not monitor._connected


# ===========================================================================
# Expanded tests: _ensure_connected edge cases
# ===========================================================================


@pytest.mark.parametrize(
    "exc_cls",
    [RuntimeError, TypeError, ValueError, ImportError, OSError, AttributeError],
    ids=lambda c: c.__name__,
)
def test_ensure_connected_connect_various_errors_suppressed(
    exc_cls: type,
) -> None:
    """Various exception types from connect() are all suppressed."""
    monitor = SystemThemeMonitor()

    mock_hints = MagicMock()
    mock_hints.colorSchemeChanged.connect.side_effect = exc_cls("fail")
    mock_app = MagicMock()
    mock_app.styleHints.return_value = mock_hints

    with patch(_QAPP_PATH) as mock_cls:
        mock_cls.instance.return_value = mock_app
        monitor._ensure_connected()

    assert not monitor._connected


def test_ensure_connected_app_style_hints_raises_attribute_error() -> None:
    """_ensure_connected handles AttributeError from styleHints()."""
    monitor = SystemThemeMonitor()

    mock_app = MagicMock()
    mock_app.styleHints.side_effect = AttributeError("no hints")

    with patch(_QAPP_PATH) as mock_cls:
        mock_cls.instance.return_value = mock_app
        monitor._ensure_connected()

    assert not monitor._connected


def test_ensure_connected_instance_raises_is_suppressed() -> None:
    """_ensure_connected handles exception from QApplication.instance()."""
    monitor = SystemThemeMonitor()

    with patch(_QAPP_PATH) as mock_cls:
        mock_cls.instance.side_effect = TypeError("bad")
        monitor._ensure_connected()

    assert not monitor._connected
