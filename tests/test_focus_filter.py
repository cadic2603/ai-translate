"""Coverage for the application-level focus-clear event filter.

Pins the contract that ``_FocusClearFilter`` (installed once at app
startup via :func:`install_focus_clear_filter`) clears widget focus on
Esc keypresses and on clicks landing outside the currently-focused
widget tree.  Without this, Qt's default leaves the focus rectangle
stuck on the last-clicked button until Tab moves elsewhere — the UX
regression a user reported on the Live Translation toolbar.

Tests exercise the filter via its public methods (``_clear_focus_if_any``,
``_maybe_clear_focus_after_click``) and via ``eventFilter`` directly
rather than driving real focus events through the offscreen platform,
which doesn't simulate window activation reliably enough for
``QApplication.focusWidget()`` to track the deferred state.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestClearFocusIfAny:
    """``_clear_focus_if_any`` (Esc handler) clears the focused widget."""

    def test_clears_focus_when_widget_focused(
        self,
        qapp,  # noqa: ANN001, ARG002
    ) -> None:
        """When app.focusWidget() returns a widget, clearFocus is called on it."""
        from src.ui.focus_filter import _FocusClearFilter  # noqa: PLC0415

        fake_widget = MagicMock()
        with patch(
            "src.ui.focus_filter.QApplication.instance",
        ) as mock_instance:
            mock_instance.return_value.focusWidget.return_value = fake_widget
            _FocusClearFilter._clear_focus_if_any()
        fake_widget.clearFocus.assert_called_once()

    def test_no_op_when_no_widget_focused(
        self,
        qapp,  # noqa: ANN001, ARG002
    ) -> None:
        """When app.focusWidget() returns None, nothing happens (safe no-op)."""
        from src.ui.focus_filter import _FocusClearFilter  # noqa: PLC0415

        with patch(
            "src.ui.focus_filter.QApplication.instance",
        ) as mock_instance:
            mock_instance.return_value.focusWidget.return_value = None
            # Must not raise.
            _FocusClearFilter._clear_focus_if_any()

    def test_no_op_when_no_app_instance(
        self,
        qapp,  # noqa: ANN001, ARG002
    ) -> None:
        """When QApplication.instance() is None, nothing happens.

        Defensive — covers test setups that exit the QApplication
        before deferred callbacks fire.
        """
        from src.ui.focus_filter import _FocusClearFilter  # noqa: PLC0415

        with patch(
            "src.ui.focus_filter.QApplication.instance",
            return_value=None,
        ):
            # Must not raise.
            _FocusClearFilter._clear_focus_if_any()


class TestMaybeClearFocusAfterClick:
    """``_maybe_clear_focus_after_click`` clears focus only on outside clicks."""

    def test_no_op_when_no_widget_focused(
        self,
        qapp,  # noqa: ANN001, ARG002
    ) -> None:
        """If no widget is focused, deferred callback does nothing."""
        from src.ui.focus_filter import _FocusClearFilter  # noqa: PLC0415

        with patch(
            "src.ui.focus_filter.QApplication.instance",
        ) as mock_instance:
            mock_instance.return_value.focusWidget.return_value = None
            _FocusClearFilter._maybe_clear_focus_after_click()  # must not raise

    def test_keeps_focus_when_click_inside_focused_widget(
        self,
        qapp,  # noqa: ANN001, ARG002
    ) -> None:
        """Click target IS the focused widget → focus stays."""
        from src.ui.focus_filter import _FocusClearFilter  # noqa: PLC0415

        focused = MagicMock()
        # Simulate widgetAt() returning the same widget that has focus.
        with patch(
            "src.ui.focus_filter.QApplication.instance",
        ) as mock_instance:
            mock_app = mock_instance.return_value
            mock_app.focusWidget.return_value = focused
            mock_app.widgetAt.return_value = focused
            _FocusClearFilter._maybe_clear_focus_after_click()
        focused.clearFocus.assert_not_called()

    def test_keeps_focus_when_click_inside_descendant(
        self,
        qapp,  # noqa: ANN001, ARG002
    ) -> None:
        """Click target is a descendant of focused widget → focus stays.

        E.g. clicking on the line edit inside a focused composite
        widget (a tag input or styled combo).  The walk-up-the-parent
        chain finds the focused widget and bails.
        """
        from src.ui.focus_filter import _FocusClearFilter  # noqa: PLC0415

        focused = MagicMock(name="focused")
        child = MagicMock(name="child")
        grandchild = MagicMock(name="grandchild")
        # parentWidget chain: grandchild → child → focused → None
        grandchild.parentWidget.return_value = child
        child.parentWidget.return_value = focused
        focused.parentWidget.return_value = None
        with patch(
            "src.ui.focus_filter.QApplication.instance",
        ) as mock_instance:
            mock_app = mock_instance.return_value
            mock_app.focusWidget.return_value = focused
            mock_app.widgetAt.return_value = grandchild
            _FocusClearFilter._maybe_clear_focus_after_click()
        focused.clearFocus.assert_not_called()

    def test_clears_focus_when_click_outside_focused_widget(
        self,
        qapp,  # noqa: ANN001, ARG002
    ) -> None:
        """Click target is NOT in the focused widget's ancestry → focus clears."""
        from src.ui.focus_filter import _FocusClearFilter  # noqa: PLC0415

        focused = MagicMock(name="focused")
        unrelated = MagicMock(name="unrelated")
        unrelated.parentWidget.return_value = None
        with patch(
            "src.ui.focus_filter.QApplication.instance",
        ) as mock_instance:
            mock_app = mock_instance.return_value
            mock_app.focusWidget.return_value = focused
            mock_app.widgetAt.return_value = unrelated
            _FocusClearFilter._maybe_clear_focus_after_click()
        focused.clearFocus.assert_called_once()

    def test_clears_focus_when_click_off_app(
        self,
        qapp,  # noqa: ANN001, ARG002
    ) -> None:
        """Click landed outside any widget (widgetAt → None) → focus clears.

        Standard outside-the-app click — Qt's widgetAt returns None
        when the cursor isn't over an app widget.  We treat that as
        an unambiguous "drop focus" signal.
        """
        from src.ui.focus_filter import _FocusClearFilter  # noqa: PLC0415

        focused = MagicMock(name="focused")
        with patch(
            "src.ui.focus_filter.QApplication.instance",
        ) as mock_instance:
            mock_app = mock_instance.return_value
            mock_app.focusWidget.return_value = focused
            mock_app.widgetAt.return_value = None
            _FocusClearFilter._maybe_clear_focus_after_click()
        focused.clearFocus.assert_called_once()


class TestEventFilterDispatch:
    """``eventFilter`` schedules the right deferred callback per event type."""

    def test_esc_keypress_schedules_clear_focus(
        self,
        qapp,  # noqa: ANN001
    ) -> None:
        """Esc keypress → schedules ``_clear_focus_if_any`` via QTimer.singleShot."""
        from PySide6.QtCore import QEvent, Qt  # noqa: PLC0415
        from PySide6.QtGui import QKeyEvent  # noqa: PLC0415

        from src.ui.focus_filter import _FocusClearFilter  # noqa: PLC0415

        fltr = _FocusClearFilter(qapp)
        ev = QKeyEvent(
            QEvent.Type.KeyPress,
            Qt.Key.Key_Escape,
            Qt.KeyboardModifier.NoModifier,
        )
        with patch(
            "src.ui.focus_filter.QTimer.singleShot",
        ) as mock_timer:
            consumed = fltr.eventFilter(qapp, ev)
        assert consumed is False, "eventFilter must never swallow events"
        mock_timer.assert_called_once()
        args = mock_timer.call_args[0]
        assert args[0] == 0  # 0ms delay
        # Second arg is the deferred callable — must be _clear_focus_if_any
        assert args[1] == fltr._clear_focus_if_any

    def test_non_esc_keypress_does_not_schedule(
        self,
        qapp,  # noqa: ANN001
    ) -> None:
        """Non-Esc key → no QTimer.singleShot call."""
        from PySide6.QtCore import QEvent, Qt  # noqa: PLC0415
        from PySide6.QtGui import QKeyEvent  # noqa: PLC0415

        from src.ui.focus_filter import _FocusClearFilter  # noqa: PLC0415

        fltr = _FocusClearFilter(qapp)
        ev = QKeyEvent(
            QEvent.Type.KeyPress,
            Qt.Key.Key_Space,
            Qt.KeyboardModifier.NoModifier,
        )
        with patch(
            "src.ui.focus_filter.QTimer.singleShot",
        ) as mock_timer:
            fltr.eventFilter(qapp, ev)
        mock_timer.assert_not_called()

    def test_mouse_press_schedules_outside_click_check(
        self,
        qapp,  # noqa: ANN001
    ) -> None:
        """Mouse press → schedules ``_maybe_clear_focus_after_click``."""
        from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: PLC0415
        from PySide6.QtGui import QMouseEvent  # noqa: PLC0415

        from src.ui.focus_filter import _FocusClearFilter  # noqa: PLC0415

        fltr = _FocusClearFilter(qapp)
        # Use the non-deprecated 6-arg overload (localPos + globalPos
        # both as QPointF) — the 5-arg form taking a single QPoint is
        # marked deprecated in PySide6 6.10 and trips
        # ``-W error::DeprecationWarning`` runs.
        ev = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(0, 0),
            QPointF(0, 0),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        with patch(
            "src.ui.focus_filter.QTimer.singleShot",
        ) as mock_timer:
            fltr.eventFilter(qapp, ev)
        mock_timer.assert_called_once()
        args = mock_timer.call_args[0]
        assert args[1] == fltr._maybe_clear_focus_after_click


class TestInstallFocusClearFilter:
    """``install_focus_clear_filter`` wires the filter to QApplication."""

    def test_returns_filter_instance(self, qapp) -> None:  # noqa: ANN001
        """The function returns the filter so callers can keep a ref if needed."""
        from src.ui.focus_filter import (  # noqa: PLC0415
            _FocusClearFilter,
            install_focus_clear_filter,
        )

        fltr = install_focus_clear_filter(qapp)
        try:
            assert isinstance(fltr, _FocusClearFilter)
        finally:
            qapp.removeEventFilter(fltr)
            if hasattr(qapp, "_focus_clear_filter"):
                del qapp._focus_clear_filter

    def test_stashes_strong_reference_on_qapplication(
        self,
        qapp,  # noqa: ANN001
    ) -> None:
        """Strong-ref stash prevents Python GC from collecting the filter.

        Qt's ``installEventFilter`` only holds a weak reference;
        without the stash, the GC would collect the filter mid-session
        and Esc / outside-click would silently stop working.
        """
        from src.ui.focus_filter import install_focus_clear_filter  # noqa: PLC0415

        fltr = install_focus_clear_filter(qapp)
        try:
            assert getattr(qapp, "_focus_clear_filter", None) is fltr
        finally:
            qapp.removeEventFilter(fltr)
            if hasattr(qapp, "_focus_clear_filter"):
                del qapp._focus_clear_filter
