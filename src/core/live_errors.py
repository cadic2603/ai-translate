"""Error classification for the Soniox cloud Live STT backend.

Maps the heterogeneous error shapes Soniox emits (WebSocket close
codes, JSON ``error_code`` payloads, ``websockets`` library
exceptions, OS network errors) onto a small enum of categories the UI
can render through :func:`src.constants.errors.display_error_message`
as friendly localised text.

**Why a separate module:** the engine module dispatches through here
so the classification logic stays pure-Python (no Qt, no async, no
side effects) and unit-testable in isolation. The historical "raw
``str(exc)`` into the status pill" path was unhelpful — a category
like ``STT_AUTH_INVALID`` maps cleanly to *"API key is invalid.
Please check Settings."*.

**Critical Soniox subtlety:** the API key lives in the *first JSON
message body*, not the HTTP headers, so the WebSocket handshake always
returns HTTP 101 even with a bad key. Auth failures arrive as a JSON
``{"error_code": 401, …}`` payload, then the connection closes
normally. The engine MUST inspect every received frame for
``error_code`` BEFORE classifying transport-level exceptions —
otherwise a bad key looks like a clean shutdown.
"""

from __future__ import annotations

import asyncio
from typing import Any, Final

# ---------------------------------------------------------------------------
# Categories (string constants, not enum — they double as i18n tag keys
# resolved through ``src.constants.errors.display_error_message``)
# ---------------------------------------------------------------------------

STT_AUTH_INVALID: Final = "STT_AUTH_INVALID"
"""Bad / missing API key. User fix: check Settings."""

STT_AUTH_FORBIDDEN: Final = "STT_AUTH_FORBIDDEN"
"""Key valid but lacks access (Live API not enabled, region locked,
project not whitelisted). User fix: enable Live API in console."""

STT_BILLING_REQUIRED: Final = "STT_BILLING_REQUIRED"
"""Soniox 402. User fix: upgrade plan."""

STT_QUOTA_EXCEEDED: Final = "STT_QUOTA_EXCEEDED"
"""Rate limit / quota hit. User fix: wait or upgrade plan."""

STT_MODEL_NOT_FOUND: Final = "STT_MODEL_NOT_FOUND"
"""Invalid model id (Soniox 400 ``Invalid model``).
User fix: pick a different model."""

STT_LANGUAGE_NOT_SUPPORTED: Final = "STT_LANGUAGE_NOT_SUPPORTED"
"""Invalid language hint. User fix: pick a supported language or
switch to Whisper."""

STT_INVALID_REQUEST: Final = "STT_INVALID_REQUEST"
"""Programmer error — malformed config payload. User fix: report the bug."""

STT_IDLE_TIMEOUT: Final = "STT_IDLE_TIMEOUT"
"""Soniox 408 — no audio received within the API's idle window.
User fix: check microphone permission / audio source."""

STT_CONNECTION_LOST: Final = "STT_CONNECTION_LOST"
"""Network drop, abnormal close, DNS failure mid-stream. User fix:
check connection; engine may auto-reconnect."""

STT_SESSION_EXPIRED: Final = "STT_SESSION_EXPIRED"
"""Server-initiated session-time-limit close. User fix: press Start
again (or wait for auto-reconnect)."""

STT_SERVICE_UNAVAILABLE: Final = "STT_SERVICE_UNAVAILABLE"
"""5xx from upstream. User fix: try again shortly."""

STT_TIMEOUT: Final = "STT_TIMEOUT"
"""Server response deadline exceeded. User fix: try again."""

STT_UNKNOWN: Final = "STT_UNKNOWN"
"""Fall-through — log the raw exception, show generic error to user."""


# ---------------------------------------------------------------------------
# Soniox classifiers
# ---------------------------------------------------------------------------

# Documented Soniox error codes. Source:
# https://soniox.com/docs/speech-to-text/api-reference/websocket-api
_SONIOX_BAD_REQUEST: Final = 400
_SONIOX_CODE_MAP: Final[dict[int, str]] = {
    _SONIOX_BAD_REQUEST: STT_INVALID_REQUEST,  # refined for model/language sub-cases
    401: STT_AUTH_INVALID,
    402: STT_BILLING_REQUIRED,
    408: STT_IDLE_TIMEOUT,
    429: STT_QUOTA_EXCEEDED,
    500: STT_SERVICE_UNAVAILABLE,
    503: STT_SERVICE_UNAVAILABLE,
}


def classify_soniox_event(event: dict[str, Any]) -> str | None:
    """Inspects a parsed JSON message for an ``error_code`` field.

    Soniox transmits errors as payload integers, not WebSocket close
    codes — so this MUST be called on every received frame before any
    transport-level exception classification runs.

    Args:
        event: A parsed JSON message from the Soniox WebSocket.

    Returns:
        A category string from this module, or ``None`` if the message
        carries no ``error_code`` (i.e. it's a regular transcript token).
    """
    code = event.get("error_code")
    if code is None:
        return None
    msg = (event.get("error_message") or "").lower()
    # Refine 400 — the docs lump several distinct user-fixable causes
    # under "Bad Request"; the human-readable ``error_message`` is the
    # only signal we have to disambiguate them.
    if code == _SONIOX_BAD_REQUEST:
        if "model" in msg:
            return STT_MODEL_NOT_FOUND
        if "language" in msg:
            return STT_LANGUAGE_NOT_SUPPORTED
        return STT_INVALID_REQUEST
    return _SONIOX_CODE_MAP.get(code, STT_UNKNOWN)


def classify_soniox_exception(exc: BaseException) -> str | None:  # noqa: PLR0911
    """Classifies a transport-level exception when no error JSON arrived.

    Only call this AFTER ``classify_soniox_event`` returned ``None`` for
    every received frame in the session — otherwise a documented
    application error gets misreported as a network drop.

    Returns ``None`` for ``ConnectionClosedOK`` to signal "graceful end
    of stream, not an error" so the caller can skip the toast.
    """
    # Lazy import — websockets is heavyweight and not needed for the
    # JSON-payload path that handles 95% of real failures.
    from websockets.exceptions import (  # noqa: PLC0415
        ConnectionClosedError,
        ConnectionClosedOK,
        InvalidHandshake,
    )

    if isinstance(exc, ConnectionClosedOK):
        return None  # graceful end of stream — not an error
    if isinstance(exc, ConnectionClosedError):
        # Soniox uses custom WebSocket close codes when the server
        # tears the session down WITHOUT a JSON error payload
        # (typically during the initial handshake — bad API key,
        # billing, rate limit on connect).  The reference JS client
        # at ~/my-translator/src/js/soniox.js maps:
        #   4001 / 4003 → invalid / forbidden API key
        #   4002        → billing / subscription issue
        #   4029        → rate limit
        # Plain 1006 stays as "connection lost" (network drop).
        code = getattr(exc, "code", None)
        if code in (4001, 4003):
            return STT_AUTH_INVALID
        if code == 4002:  # noqa: PLR2004
            return STT_BILLING_REQUIRED
        if code == 4029:  # noqa: PLR2004
            return STT_QUOTA_EXCEEDED
        return STT_CONNECTION_LOST
    if _is_invalid_status(exc):
        # Soniox auths in the body, so a non-101 here is almost
        # certainly a network appliance / proxy interfering, not auth.
        return STT_CONNECTION_LOST
    if isinstance(exc, InvalidHandshake):
        return STT_CONNECTION_LOST
    if isinstance(exc, asyncio.TimeoutError):
        return STT_TIMEOUT
    if isinstance(exc, OSError):
        # DNS failure, connection refused — websockets surfaces these
        # raw because they happen before the library sees them.
        return STT_CONNECTION_LOST
    return STT_UNKNOWN


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _is_invalid_status(exc: BaseException) -> bool:
    """Returns True when ``exc`` is either ``websockets`` invalid-status class.

    ``websockets`` 13.x renamed ``InvalidStatusCode`` (legacy) to
    ``InvalidStatus`` (modern); both ship side-by-side for back-compat.
    Importing both inside this helper keeps the lazy-import pattern
    consistent and avoids a hard dependency on either name shape at
    module load.
    """
    from websockets.exceptions import (  # noqa: PLC0415
        InvalidStatus,
    )

    if isinstance(exc, InvalidStatus):
        return True
    try:
        from websockets.exceptions import (  # noqa: PLC0415
            InvalidStatusCode,
        )
    except ImportError:
        return False
    return isinstance(exc, InvalidStatusCode)


def _extract_status_code(exc: BaseException) -> int | None:
    """Pulls an HTTP status from either the modern or legacy exception shape."""
    if not _is_invalid_status(exc):
        return None
    # Modern: ``exc.response.status_code`` (websockets >= 13).
    response = getattr(exc, "response", None)
    if response is not None:
        status = getattr(response, "status_code", None)
        if status is not None:
            try:
                return int(status)
            except (TypeError, ValueError):
                pass
    # Legacy: ``exc.status_code`` directly.
    status = getattr(exc, "status_code", None)
    if status is not None:
        try:
            return int(status)
        except (TypeError, ValueError):
            return None
    return None
