"""Application-level event filter that clears focus on Esc / outside-click.

Standard desktop UX expectation:

- Pressing **Esc** drops focus from whatever widget currently has it
  (a button stuck with a focus rectangle, a text input the user wants
  to bail out of, etc.).
- **Clicking on a non-focusable area** (page background, label, group
  divider) drops focus from any currently-focused widget.

Qt's default leaves the focus rectangle stuck on the last-clicked
button until ``Tab`` moves elsewhere — uncomfortable for keyboard +
mouse users on a long-running session.  This filter installs a
single ``QObject`` on ``QApplication.instance()`` that watches every
event and intercepts the two cases above.

Trade-off: we use ``QTimer.singleShot(0, ...)`` to defer the focus
inspection until **after** Qt has had a chance to process the click /
keypress and update focus naturally.  Without the defer, the filter
runs *before* Qt transfers focus to a click-target widget, so we'd
incorrectly clear focus on a button click that should have just moved
focus to that button.  The deferred check sees the post-Qt state and
only clears focus when Qt didn't already move it.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication


class _FocusClearFilter(QObject):
    """Singleton event filter that powers the Esc / outside-click clearing.

    Installed once at app startup via :func:`install_focus_clear_filter`.
    The filter never swallows events — it only schedules a deferred
    ``clearFocus()`` call, so contextual handlers (dialog Esc-to-close,
    edit-mode Esc-to-cancel, click-to-focus on text fields) keep
    working unchanged.
    """

    def eventFilter(  # noqa: N802 (Qt naming convention)
        self,
        obj: QObject,  # noqa: ARG002
        event: QEvent,
    ) -> bool:
        """Routes Esc keypresses and mouse-button presses to the deferred handler."""
        et = event.type()
        if et == QEvent.Type.KeyPress and getattr(event, "key", None) is not None:
            # Defer so dialogs' Esc handlers (close, cancel edit, etc.)
            # fire first; we only clear if focus is still where it was.
            if event.key() == Qt.Key.Key_Escape:
                QTimer.singleShot(0, self._clear_focus_if_any)
        elif et == QEvent.Type.MouseButtonPress:
            # Defer so Qt's normal click-focus transfer (clicking on a
            # focusable widget moves focus to it) lands first; we only
            # clear when focus is stuck on a widget the user clicked
            # away from.
            QTimer.singleShot(0, self._maybe_clear_focus_after_click)
        return False  # never swallow

    @staticmethod
    def _clear_focus_if_any() -> None:
        """Removes focus from whatever widget currently holds it (Esc path).

        Run as a deferred callback so it sees the post-Qt focus state
        — if a dialog's Esc handler closed the dialog, the deleted
        widget has already lost focus by the time this runs and the
        method is a no-op.
        """
        app = QApplication.instance()
        if app is None:
            return
        fw = app.focusWidget()
        if fw is not None:
            fw.clearFocus()

    @staticmethod
    def _maybe_clear_focus_after_click() -> None:
        """Clears focus when the click landed outside the focused widget tree.

        By the time this deferred callback runs, Qt has already
        processed the click and transferred focus naturally if the
        click target was focusable.  So:

        - If the click landed inside the still-focused widget (or any
          of its descendants), do nothing — the widget legitimately
          owns the click.
        - If Qt already moved focus to a different focusable target,
          ``app.focusWidget()`` returns the NEW target and the
          ancestor check naturally returns true (it IS the click
          target), so again we do nothing.
        - Otherwise (click hit a non-focusable widget like a label or
          page background), focus is stuck on the original widget and
          we clear it.
        """
        app = QApplication.instance()
        if app is None:
            return
        fw = app.focusWidget()
        if fw is None:
            return
        target = app.widgetAt(QCursor.pos())
        # Walk up the click target's ancestry — if it lands on the
        # focused widget, the click is "inside" the focused area.
        widget = target
        while widget is not None:
            if widget is fw:
                return
            widget = widget.parentWidget()
        fw.clearFocus()


def install_focus_clear_filter(app: QApplication) -> _FocusClearFilter:
    """Installs the focus-clear event filter on *app*.

    Called once at application startup.  Stashes the filter instance
    on the QApplication via a private attribute so Python's GC
    doesn't collect it (Qt only holds a weak reference through
    ``installEventFilter``).
    """
    fltr = _FocusClearFilter(app)
    app.installEventFilter(fltr)
    app._focus_clear_filter = fltr  # noqa: SLF001 (keep alive)
    return fltr
