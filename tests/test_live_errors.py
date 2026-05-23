"""Unit tests for ``src.core.live_errors``.

Pure-function tests — no Qt, no fixtures, no async event loop. Each
test pins a single branch of one classifier so a regression points
straight at the cause.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.core.live_errors import (
    STT_AUTH_INVALID,
    STT_BILLING_REQUIRED,
    STT_CONNECTION_LOST,
    STT_IDLE_TIMEOUT,
    STT_INVALID_REQUEST,
    STT_LANGUAGE_NOT_SUPPORTED,
    STT_MODEL_NOT_FOUND,
    STT_QUOTA_EXCEEDED,
    STT_SERVICE_UNAVAILABLE,
    STT_TIMEOUT,
    STT_UNKNOWN,
    classify_soniox_event,
    classify_soniox_exception,
)

# ---------------------------------------------------------------------------
# classify_soniox_event
# ---------------------------------------------------------------------------


class TestClassifySonioxEvent:
    """Soniox transmits errors as JSON ``error_code`` payloads, not WS close codes."""

    def test_no_error_code_returns_none(self) -> None:
        """A regular transcript token (no error_code) classifies as None."""
        assert classify_soniox_event({"tokens": [{"text": "hi"}]}) is None

    def test_401_maps_to_auth_invalid(self) -> None:
        """A 401 payload maps to STT_AUTH_INVALID."""
        evt = {"error_code": 401, "error_message": "Invalid API key"}
        assert classify_soniox_event(evt) == STT_AUTH_INVALID

    def test_402_maps_to_billing_required(self) -> None:
        """A 402 payload maps to STT_BILLING_REQUIRED."""
        evt = {"error_code": 402, "error_message": "Project balance exhausted"}
        assert classify_soniox_event(evt) == STT_BILLING_REQUIRED

    def test_408_maps_to_idle_timeout(self) -> None:
        """A 408 payload (no audio sent in time) maps to STT_IDLE_TIMEOUT."""
        evt = {"error_code": 408, "error_message": "No audio data received"}
        assert classify_soniox_event(evt) == STT_IDLE_TIMEOUT

    def test_429_maps_to_quota_exceeded(self) -> None:
        """A 429 payload maps to STT_QUOTA_EXCEEDED."""
        evt = {"error_code": 429, "error_message": "Too many requests"}
        assert classify_soniox_event(evt) == STT_QUOTA_EXCEEDED

    def test_500_maps_to_service_unavailable(self) -> None:
        """A 500 payload maps to STT_SERVICE_UNAVAILABLE."""
        evt = {"error_code": 500, "error_message": "Internal server error"}
        assert classify_soniox_event(evt) == STT_SERVICE_UNAVAILABLE

    def test_503_maps_to_service_unavailable(self) -> None:
        """A 503 payload also maps to STT_SERVICE_UNAVAILABLE."""
        evt = {"error_code": 503, "error_message": "Service unavailable"}
        assert classify_soniox_event(evt) == STT_SERVICE_UNAVAILABLE

    def test_400_with_model_message_maps_to_model_not_found(self) -> None:
        """400 with 'model' in error_message → STT_MODEL_NOT_FOUND."""
        evt = {"error_code": 400, "error_message": "Invalid model specified."}
        assert classify_soniox_event(evt) == STT_MODEL_NOT_FOUND

    def test_400_with_language_message_maps_to_language_not_supported(self) -> None:
        """400 with 'language' in error_message → STT_LANGUAGE_NOT_SUPPORTED."""
        evt = {"error_code": 400, "error_message": "Unsupported language: xyz"}
        assert classify_soniox_event(evt) == STT_LANGUAGE_NOT_SUPPORTED

    def test_400_with_other_message_maps_to_invalid_request(self) -> None:
        """400 with a generic message → STT_INVALID_REQUEST."""
        evt = {"error_code": 400, "error_message": "Malformed config JSON"}
        assert classify_soniox_event(evt) == STT_INVALID_REQUEST

    def test_unknown_code_maps_to_unknown(self) -> None:
        """An unmapped error code falls back to STT_UNKNOWN."""
        evt = {"error_code": 999, "error_message": "Future error"}
        assert classify_soniox_event(evt) == STT_UNKNOWN

    def test_missing_error_message_doesnt_crash(self) -> None:
        """error_message is optional — None must not crash the classifier."""
        evt = {"error_code": 400}
        # No 'model' / 'language' substrings → falls through to INVALID_REQUEST.
        assert classify_soniox_event(evt) == STT_INVALID_REQUEST


# ---------------------------------------------------------------------------
# classify_soniox_exception
# ---------------------------------------------------------------------------


class TestClassifySonioxException:
    """Transport-level exceptions when no error_code JSON arrived."""

    def test_connection_closed_ok_returns_none(self) -> None:
        """Code 1000 / graceful end → None (caller should not toast)."""
        from websockets.exceptions import ConnectionClosedOK

        exc = ConnectionClosedOK(MagicMock(), MagicMock(), True)  # noqa: FBT003
        assert classify_soniox_exception(exc) is None

    def test_connection_closed_error_maps_to_connection_lost(self) -> None:
        """Abnormal close (no Soniox-custom code) → STT_CONNECTION_LOST."""
        from websockets.exceptions import ConnectionClosedError

        exc = ConnectionClosedError(MagicMock(), MagicMock(), True)  # noqa: FBT003
        # The ``code`` attribute on the mocked rcvd/sent frames defaults
        # to a MagicMock (not in our custom-code table), so the
        # classifier falls through to the generic CONNECTION_LOST path.
        assert classify_soniox_exception(exc) == STT_CONNECTION_LOST

    def _make_closed_error(self, code: int, reason: str = ""):  # noqa: ANN202
        """Builds a ConnectionClosedError that exposes the given close code.

        The ``code`` property on ``ConnectionClosedError`` is read-only
        and derives from the underlying ``Close`` frame, so we need a
        real ``Close`` object — patching the property would mask the
        real-world surface we're testing.
        """
        from websockets.exceptions import ConnectionClosedError  # noqa: PLC0415
        from websockets.frames import Close  # noqa: PLC0415

        frame = Close(code, reason)
        return ConnectionClosedError(frame, None, None)

    def test_close_code_4001_maps_to_auth_invalid(self) -> None:
        """Soniox custom code 4001 → STT_AUTH_INVALID.

        Reference: ~/my-translator/src/js/soniox.js — the JS client
        treats 4001 / 4003 as invalid / forbidden API key.  Soniox
        sends these on connect handshake failure when the token /
        billing check fires BEFORE any error JSON could be sent.
        Without this mapping, the user sees "connection lost" for
        a bad key instead of "API key is invalid."
        """
        exc = self._make_closed_error(4001, "auth")
        assert classify_soniox_exception(exc) == "STT_AUTH_INVALID"

    def test_close_code_4003_maps_to_auth_invalid(self) -> None:
        """Soniox custom code 4003 → STT_AUTH_INVALID (forbidden)."""
        exc = self._make_closed_error(4003, "forbidden")
        assert classify_soniox_exception(exc) == "STT_AUTH_INVALID"

    def test_close_code_4002_maps_to_billing_required(self) -> None:
        """Soniox custom code 4002 → STT_BILLING_REQUIRED.

        Surfaces "subscription issue" instead of "connection lost"
        when the user's billing lapses or their plan doesn't cover
        the requested model.
        """
        exc = self._make_closed_error(4002, "billing")
        assert classify_soniox_exception(exc) == "STT_BILLING_REQUIRED"

    def test_close_code_4029_maps_to_quota_exceeded(self) -> None:
        """Soniox custom code 4029 → STT_QUOTA_EXCEEDED (rate limit)."""
        exc = self._make_closed_error(4029, "rate limit")
        assert classify_soniox_exception(exc) == "STT_QUOTA_EXCEEDED"

    def test_invalid_status_maps_to_connection_lost(self) -> None:
        """Soniox auths in body — handshake non-101 = network appliance, not auth."""
        try:
            from websockets.exceptions import InvalidStatus
        except ImportError:  # pragma: no cover - older websockets
            pytest.skip("websockets.InvalidStatus not available")
        response = SimpleNamespace(status_code=502)
        exc = InvalidStatus(response)  # type: ignore[arg-type]
        assert classify_soniox_exception(exc) == STT_CONNECTION_LOST

    def test_asyncio_timeout_maps_to_timeout(self) -> None:
        """Asyncio timeout → STT_TIMEOUT."""
        assert classify_soniox_exception(TimeoutError()) == STT_TIMEOUT

    def test_oserror_maps_to_connection_lost(self) -> None:
        """DNS failure / connection refused (raw OSError) → STT_CONNECTION_LOST."""
        assert classify_soniox_exception(OSError("DNS failed")) == STT_CONNECTION_LOST

    def test_unknown_exception_maps_to_unknown(self) -> None:
        """A non-network exception → STT_UNKNOWN (logged separately by caller)."""
        assert classify_soniox_exception(ValueError("unexpected")) == STT_UNKNOWN


