"""Standardized error codes and messages for the AI Translate application."""

import logging
import sys

from src.constants.i18n import tr

logger = logging.getLogger("errors")

# Error Codes
ERR_NONE = 0
ERR_UNKNOWN = 1
ERR_FILE_NOT_FOUND = 10
ERR_FILE_PASSWORD_PROTECTED = 11
# Originally LLM-only; now the canonical bucket for any AUTH_ERROR tag
# (LLM / OCR / TTS / STT).  The constant name is kept for DB-code
# stability — old history rows still carry value 30.
ERR_LLM_API_KEY_INVALID = 30
ERR_LLM_CONNECTION_FAILED = 31
ERR_LLM_TIMEOUT = 32
ERR_LLM_QUOTA_EXCEEDED = 33
ERR_LLM_INVALID_RESPONSE = 34
ERR_LLM_MODEL_NOT_FOUND = 35
ERR_LLM_REQUEST_TOO_LARGE = 36
ERR_LLM_SERVICE_UNAVAILABLE = 37
ERR_LLM_VISION_NOT_SUPPORTED = 38
ERR_LLM_INVALID_REQUEST = 39
ERR_OCR_ENGINE_NOT_FOUND = 40
ERR_OCR_PROCESS_FAILED = 41
ERR_OCR_NO_TEXT_FOUND = 42
ERR_IMAGE_INVALID = 50
ERR_TEXT_READ_FAILED = 60
ERR_TEXT_WRITE_FAILED = 61
ERR_OFFICE_CONVERTER_NOT_FOUND = 70

# Mapping of error codes to translation keys
_ERROR_TR_KEYS: dict[int, str] = {
    ERR_UNKNOWN: "error_msg.unknown",
    ERR_FILE_NOT_FOUND: "error_msg.file_not_found",
    ERR_FILE_PASSWORD_PROTECTED: "error_msg.file_password_protected",
    ERR_LLM_API_KEY_INVALID: "error_msg.api_key_invalid",
    ERR_LLM_CONNECTION_FAILED: "error_msg.connection_failed",
    ERR_LLM_TIMEOUT: "error_msg.timeout",
    ERR_LLM_QUOTA_EXCEEDED: "error_msg.quota_exceeded",
    ERR_LLM_INVALID_RESPONSE: "error_msg.invalid_response",
    ERR_LLM_MODEL_NOT_FOUND: "error_msg.model_not_found",
    ERR_LLM_REQUEST_TOO_LARGE: "error_msg.request_too_large",
    ERR_LLM_SERVICE_UNAVAILABLE: "error_msg.service_unavailable",
    ERR_LLM_VISION_NOT_SUPPORTED: "error_msg.vision_not_supported",
    ERR_LLM_INVALID_REQUEST: "error_msg.invalid_request",
    ERR_OCR_ENGINE_NOT_FOUND: "error_msg.ocr_not_found",
    ERR_OCR_PROCESS_FAILED: "error_msg.ocr_failed",
    ERR_OCR_NO_TEXT_FOUND: "error_msg.ocr_no_text",
    ERR_IMAGE_INVALID: "error_msg.image_invalid",
    ERR_TEXT_READ_FAILED: "error_msg.text_read_failed",
    ERR_TEXT_WRITE_FAILED: "error_msg.text_write_failed",
    ERR_OFFICE_CONVERTER_NOT_FOUND: (
        "error_msg.office_converter_not_found_win"
        if sys.platform == "win32"
        else "error_msg.office_converter_not_found"
    ),
}

# Mapping of codes to English messages (kept for logging / backward compat)
ERROR_MESSAGES = {
    ERR_NONE: "",
    ERR_UNKNOWN: "An unexpected error occurred.",
    ERR_FILE_NOT_FOUND: (
        "Source file could not be found. It may have been moved or deleted."
    ),
    ERR_FILE_PASSWORD_PROTECTED: (
        "This file is password-protected or encrypted."
        " Please remove the protection before translating."
    ),
    ERR_LLM_API_KEY_INVALID: ("Invalid API key. Please check your settings."),
    ERR_LLM_CONNECTION_FAILED: (
        "Could not connect to the translation server."
        " Please check your internet connection."
    ),
    ERR_LLM_TIMEOUT: "The translation request timed out.",
    ERR_LLM_QUOTA_EXCEEDED: ("LLM quota exceeded. Please try again later."),
    ERR_LLM_INVALID_RESPONSE: (
        "Received an invalid response from the translation server."
    ),
    ERR_LLM_MODEL_NOT_FOUND: (
        "The specified model was not found."
        " Please check the model name in your settings."
    ),
    ERR_LLM_REQUEST_TOO_LARGE: ("The request is too large. Try using a smaller image."),
    ERR_LLM_SERVICE_UNAVAILABLE: (
        "The translation server is currently overloaded"
        " or undergoing maintenance."
        " Please try again in a few moments."
    ),
    ERR_LLM_VISION_NOT_SUPPORTED: (
        "Image translation is not supported by this"
        " model. Please use a vision-capable model"
        " or switch to Gemini."
    ),
    ERR_LLM_INVALID_REQUEST: (
        "The LLM request was rejected."
        " The selected model may not support this operation."
    ),
    ERR_OCR_ENGINE_NOT_FOUND: ("OCR engine is not installed or configured correctly."),
    ERR_OCR_PROCESS_FAILED: "Failed to extract text from image.",
    ERR_OCR_NO_TEXT_FOUND: ("No translatable text was detected in the image."),
    ERR_IMAGE_INVALID: ("The image file is invalid or could not be processed."),
    ERR_TEXT_READ_FAILED: (
        "Could not read the text file."
        " The file may be corrupted or use an unsupported encoding."
    ),
    ERR_TEXT_WRITE_FAILED: (
        "Could not write the translated file."
        " Please check disk space and output directory permissions."
    ),
    ERR_OFFICE_CONVERTER_NOT_FOUND: (
        "No Office backend available. Please install Microsoft Office or LibreOffice."
        if sys.platform == "win32"
        else "No Office backend available. Please install LibreOffice."
    ),
}


def get_error_message(code: int | None) -> str:
    """Returns the localized message corresponding to an error code."""
    if code is None or code == ERR_NONE:
        return ""
    key = _ERROR_TR_KEYS.get(code)
    if key:
        return tr(key)
    return f"Unknown error (Code: {code})"


# Tag string → error code lookup (shared with translator.py)
_TAG_TO_CODE: dict[str, int] = {
    "AUTH_ERROR": ERR_LLM_API_KEY_INVALID,
    "MODEL_NOT_FOUND": ERR_LLM_MODEL_NOT_FOUND,
    "REQUEST_TOO_LARGE": ERR_LLM_REQUEST_TOO_LARGE,
    "QUOTA_ERROR": ERR_LLM_QUOTA_EXCEEDED,
    "SERVICE_UNAVAILABLE_ERROR": ERR_LLM_SERVICE_UNAVAILABLE,
    "TIMEOUT_ERROR": ERR_LLM_TIMEOUT,
    "INVALID_RESPONSE": ERR_LLM_INVALID_RESPONSE,
    "CONNECTION_ERROR": ERR_LLM_CONNECTION_FAILED,
    "VISION_NOT_SUPPORTED": ERR_LLM_VISION_NOT_SUPPORTED,
    "INVALID_REQUEST": ERR_LLM_INVALID_REQUEST,
    "PASSWORD_PROTECTED": ERR_FILE_PASSWORD_PROTECTED,
    "TEXT_READ_ERROR": ERR_TEXT_READ_FAILED,
    "TEXT_WRITE_ERROR": ERR_TEXT_WRITE_FAILED,
    "OFFICE_CONVERTER_NOT_FOUND": ERR_OFFICE_CONVERTER_NOT_FOUND,
}

# Tag string → translation key for tags without an error code
_TAG_TO_TR_KEY: dict[str, str] = {
    "FFMPEG_NOT_FOUND": "error_msg.ffmpeg_not_found",
    "FFMPEG_CONVERSION_FAILED": "error_msg.ffmpeg_failed",
    "FFMPEG_CONCAT_FAILED": "error_msg.ffmpeg_failed",
    "FFMPEG_MIX_FAILED": "error_msg.ffmpeg_failed",
    "SPEECH_API_ERROR": "error_msg.speech_api_failed",
    "AUDIO_TOO_LARGE": "error_msg.audio_too_large",
    # Cloud Vision OCR rejects images > 20 MB; raised pre-flight by
    # ``_run_google_cloud`` in ``src/core/ocr_engine.py`` so the
    # user gets a clear "image too large" toast instead of an
    # opaque 400 from the API.
    "IMAGE_TOO_LARGE": "error_msg.image_too_large",
    "TTS_API_ERROR": "error_msg.tts_api_failed",
    "EMPTY_TEXT": "error_msg.empty_text",
    "CANCELLED": "error_msg.cancelled",
    # Piper offline TTS — voice files are downloaded on demand via
    # Settings → Voice → Piper.  Synthesis with an uninstalled voice
    # raises this so the UI can point the user back to the panel.
    "PIPER_VOICE_NOT_INSTALLED": "error_msg.piper_voice_not_installed",
    "PIPER_DOWNLOAD_FAILED": "error_msg.piper_download_failed",
    # Cloud STT (Soniox, Gemini Live) error categories — emitted by
    # ``src.core.live_errors.classify_*`` and resolved here to friendly
    # localised text.  Keep in sync with that module's ``STT_*`` constants.
    "STT_AUTH_INVALID": "error_msg.stt_auth_invalid",
    "STT_AUTH_FORBIDDEN": "error_msg.stt_auth_forbidden",
    "STT_BILLING_REQUIRED": "error_msg.stt_billing_required",
    "STT_QUOTA_EXCEEDED": "error_msg.stt_quota_exceeded",
    "STT_MODEL_NOT_FOUND": "error_msg.stt_model_not_found",
    "STT_LANGUAGE_NOT_SUPPORTED": "error_msg.stt_language_not_supported",
    "STT_INVALID_REQUEST": "error_msg.stt_invalid_request",
    # TTS-specific 400 (mirrors STT_INVALID_REQUEST).  Surfaced by
    # ``speech_engine._synthesize_chunk`` when Google TTS returns an
    # HTTP 400 that isn't an API_KEY_INVALID (which gets routed to
    # AUTH_ERROR instead).  Most common cause: unsupported language
    # code falling through ``_TTS_LANG_MAP`` to a code Google
    # doesn't ship a voice for.
    "TTS_INVALID_REQUEST": "error_msg.tts_invalid_request",
    "STT_IDLE_TIMEOUT": "error_msg.stt_idle_timeout",
    "STT_CONNECTION_LOST": "error_msg.stt_connection_lost",
    "STT_SESSION_EXPIRED": "error_msg.stt_session_expired",
    "STT_SERVICE_UNAVAILABLE": "error_msg.stt_service_unavailable",
    "STT_TIMEOUT": "error_msg.stt_timeout",
    "STT_UNKNOWN": "error_msg.stt_unknown",
}


def map_tag_to_code(msg: str) -> int:
    """Maps an error tag string to a standardized error code.

    Args:
        msg: The exception message string (may contain a tag prefix).

    Returns:
        int: The corresponding error code, or ERR_UNKNOWN if unrecognized.
    """
    for tag, code in _TAG_TO_CODE.items():
        if tag in msg:
            return code
    logger.warning("Unknown error tag '%s' mapped to ERR_UNKNOWN", msg)
    return ERR_UNKNOWN


def base_error_tag(tag: str) -> str:
    """Returns the base error tag, stripping any ``:Service`` suffix.

    The engine appends a service-name suffix to AUTH_ERROR raises
    (``"AUTH_ERROR:Gemini"`` etc.) so the UI can render service-aware
    messages.  Set-membership consumers — fatal-error checks in the
    PDF / Office image processors, the LLM dispatcher's
    informative-response filter, etc. — need the BASE tag for their
    exact-match comparisons; without this strip they'd silently miss
    every suffixed AUTH_ERROR and demote fatal errors to skip-with-
    warning.

    Args:
        tag: The raw tag string, with or without a ``:Service`` suffix.

    Returns:
        The portion of ``tag`` before the first colon (or the whole
        tag if no colon present).
    """
    return tag.split(":", 1)[0]


def _extract_auth_service(raw_msg: str) -> str:
    """Extracts the service-name suffix from an ``AUTH_ERROR:Service`` tag.

    Engines that touch a remote auth-required service raise
    ``ValueError("AUTH_ERROR:Service Name")`` to surface WHICH key the
    user must fix (Google Cloud / Soniox / ElevenLabs / Gemini / a
    user-named Custom provider).  Without the suffix, the user sees
    "Invalid API key" with no hint which Settings tab to open.

    Returns the service name if a suffix is present, otherwise empty
    string (legacy raises that didn't pass a service).  Strips
    surrounding whitespace so callers can write
    ``f"AUTH_ERROR:{name}"`` without trimming themselves.
    """
    # Match ``AUTH_ERROR:`` at the start of the message OR after any
    # leading prefix (an exception chain may stringify as
    # "Error processing: AUTH_ERROR:Google Cloud").  The service name
    # runs to end-of-string or the first newline.
    import re  # noqa: PLC0415

    m = re.search(r"AUTH_ERROR:([^\n]+)", raw_msg)
    if not m:
        return ""
    return m.group(1).strip()


def display_error_message(raw_msg: str) -> str:
    """Converts a raw error tag string to a localized user-friendly message.

    Checks against known tag strings (e.g. "MODEL_NOT_FOUND", "AUTH_ERROR")
    and returns a localized message. If the raw message doesn't match any
    known tag, it is returned as-is (it may already be localized).

    Args:
        raw_msg: The raw error message (tag string or already-localized text).

    Returns:
        str: A user-friendly, localized error message.
    """
    if not raw_msg:
        return ""

    # AUTH_ERROR carries an optional ``:Service Name`` suffix so the
    # user sees "Invalid Google Cloud API key" instead of the generic
    # "Invalid API key" — knowing WHICH key is bad is critical when
    # the app has 4 separate auth-required keys (LLM, OCR, TTS, STT).
    # Check this BEFORE the generic substring loop because the
    # service-aware path needs the suffix that the loop would
    # otherwise discard.
    if "AUTH_ERROR" in raw_msg:
        service = _extract_auth_service(raw_msg)
        if service:
            return tr("error_msg.api_key_invalid_for", service=service)
        # No suffix — legacy raise path or a callsite that genuinely
        # doesn't know the service.  Fall through to the generic key.
        return get_error_message(ERR_LLM_API_KEY_INVALID)

    # Check tag → error code → localized message
    for tag, code in _TAG_TO_CODE.items():
        if tag in raw_msg:
            return get_error_message(code)

    # Check tag → direct translation key
    for tag, tr_key in _TAG_TO_TR_KEY.items():
        if tag in raw_msg:
            return tr(tr_key)

    # Not a known tag — return as-is (may already be localized)
    return raw_msg
