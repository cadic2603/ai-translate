"""Lightweight callback signal shared by the theme and i18n engines.

Provides a PySide6-free .connect()/.emit() API so that the constants
layer stays importable without a running Qt event loop.
"""

import contextlib
import logging
from collections.abc import Callable

logger = logging.getLogger("signal")


class CallbackSignal:
    """Minimal publish-subscribe signal with .connect()/.emit() API."""

    def __init__(self) -> None:
        self._callbacks: list[Callable] = []

    def connect(self, callback: Callable) -> None:
        """Registers a callback to be invoked on emit."""
        if callback not in self._callbacks:
            self._callbacks.append(callback)

    def disconnect(self, callback: Callable) -> None:
        """Removes a previously registered callback.

        Tolerant of double-disconnect (callback already removed) so
        that race conditions between widget ``destroyed`` lambdas
        and the conftest's ``_callbacks.clear()`` cleanup don't
        raise ``ValueError`` mid-teardown — which would otherwise
        cascade through pytest as test failures unrelated to the
        actual code under test.
        """
        with contextlib.suppress(ValueError):
            self._callbacks.remove(callback)

    def emit(self, *args: object) -> None:
        """Invokes all registered callbacks with the given arguments.

        Each callback's exception is caught and logged so one broken
        listener can't blackhole the rest of the chain.  Without this
        guard, a single ``TypeError`` mid-emit (e.g. a callback whose
        signature doesn't match the args) silently leaves every later
        listener unfired — the user sees a half-translated UI on
        language switch with no obvious cause.
        """
        for cb in list(self._callbacks):
            try:
                cb(*args)
            except Exception:
                logger.exception("CallbackSignal listener raised; continuing")
