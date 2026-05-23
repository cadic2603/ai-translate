"""LLM Engine for translating text using Gemini or custom endpoints."""

import base64
import contextlib
import json
import logging
import os
import re
import tempfile
import threading
import time
from collections.abc import Callable, Generator
from functools import wraps
from pathlib import Path
from typing import Any, NoReturn

# ── UNO-import-hook safeguard ────────────────────────────────────────
# Eagerly cache the SDK trees in ``sys.modules`` BEFORE any LibreOffice
# UNO import hook activates.  UNO's ``_uno_import`` hook drops the
# venv ``site-packages`` from ``sys.path`` and re-runs the import; if
# a lazy ``from google.genai import errors`` inside ``_handle_api_error``
# is the first to trigger the chain
# ``google.genai → types → PIL.Image → defusedxml → xml.etree``, the
# hook poisons it with ``AttributeError: 'NoneType' object has no
# attribute '__dict__'`` mid-error-handling.  Mirrors the
# ``import pymupdf`` safeguard in ``main.py``.  Unused-import
# suppressions are load-bearing.
import google.genai  # noqa: F401, E402
import google.genai.errors  # noqa: F401, E402
import google.genai.types  # noqa: F401, E402
import openai  # noqa: F401, E402

from src.constants.errors import base_error_tag
from src.constants.llm import (
    CJK_CODEPOINT_THRESHOLD,
    CONTENT_DATA_VALUES,
    CONTENT_EPUB,
    CONTENT_HTML,
    CONTENT_LOCALIZATION,
    CONTENT_MARKDOWN,
    CONTENT_PDF,
    CONTENT_PLAIN_TEXT,
    CONTENT_RTF,
    CONTENT_SUBTITLE,
    CONTENT_XML,
    DEFAULT_GEMINI_MODEL,
    GEMINI_VISION_MODEL_KEYWORDS,
    GLOSSARY_HINT_TEMPLATE,
    JSON_ITEM_OVERHEAD,
    LLM_METHOD_CUSTOM,
    LLM_METHOD_GEMINI,
    LLM_REASONING_TIMEOUT,
    LLM_TEMPERATURE,
    LLM_TEXT_TIMEOUT,
    LLM_VISION_TIMEOUT,
    RETRY_BASE_DELAY,
    RETRY_MAX_ATTEMPTS,
    TOKEN_BUDGET,
    TRANSIENT_ERROR_TAGS,
    TRANSLATION_BATCH_SIZE,
    USER_AGENT,
    VISION_UNSUPPORTED_INDICATORS,
)
from src.constants.settings import (
    SETTING_LLM_GEMINI_API_KEY,
    SETTING_LLM_GEMINI_USE_VERTEX,
    SETTING_LLM_LAST_MODEL,
    SETTING_LLM_VERTEX_CREDENTIALS,
    SETTING_LLM_VERTEX_LOCATION,
    SETTING_LLM_VERTEX_PROJECT,
    VERTEX_DEFAULT_LOCATION,
)
from src.utils import config_manager as _config
from src.utils.text_utils import normalize_for_search

logger = logging.getLogger("llm")


def _resolve_provider_model(
    provider: str | None = None,
    model: str | None = None,
) -> tuple[str, str]:
    """Resolves which LLM provider and model to use.

    When both are provided, returns them as-is.  Otherwise falls back
    to ``SETTING_LLM_LAST_MODEL``, then to the first available model.
    """
    if provider and model:
        return (provider, model)

    # Try last-used model from settings
    last = _config.load_setting(SETTING_LLM_LAST_MODEL, "")
    if last:
        return _config.parse_model_id(last)

    # Fall back to first available model
    available = _config.get_available_models()
    if available:
        return available[0]

    return (LLM_METHOD_GEMINI, DEFAULT_GEMINI_MODEL)


# Suffix-based MIME lookup for image files (avoids mimetypes lazy-init I/O)
_IMAGE_MIME: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".webp": "image/webp",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
}

# Regex to strip <think>…</think> blocks from model output (e.g. Gemma,
# Qwen3 reasoning, DeepSeek-R1, GLM-Z1).
_THINK_TAG_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)
# Catches an *unclosed* <think> opener — usually means the model hit
# ``max_tokens`` mid-reasoning before producing the answer.  Without
# this sweep the whole reasoning blob would hit the JSON parser and
# surface as ``INVALID_RESPONSE`` with no hint at the real cause.
_UNCLOSED_THINK_RE = re.compile(r"<think>.*$", re.DOTALL)


def _strip_think_blocks(text: str) -> str:
    """Removes ``<think>...</think>`` blocks (closed and unclosed) from *text*.

    Reasoning models always emit `<think>` as the model's first generated
    token, never embedded in user-facing content, so the over-eager
    "strip from `<think>` to end" sweep is safe in practice — a literal
    `<think>` substring inside a legitimate translation would be
    extraordinarily rare and would already break the JSON parser anyway.

    A non-empty result that started with an unclosed `<think>` is logged
    at WARNING so the user has a breadcrumb when the response was
    truncated mid-reasoning.
    """
    cleaned = _THINK_TAG_RE.sub("", text)
    if "<think>" in cleaned:
        cleaned = _UNCLOSED_THINK_RE.sub("", cleaned)
        logger.warning(
            "Model response contained an unclosed <think> block — "
            "likely truncated by max_tokens before the answer was emitted. "
            "Try a higher max_tokens or a non-reasoning model.",
        )
    return cleaned


def _resolve_custom_config(model: str) -> tuple[str, str, str]:
    """Resolves API key, model name, and endpoint for a Custom provider model.

    Looks up the custom provider that contains the given model name.
    Falls back to the first available custom provider if not found.

    Returns:
        Tuple of (api_key, model, endpoint). All empty if not configured.
    """
    provider = _config.get_custom_provider_for_model(model)
    if not provider:
        # Fallback: use first custom provider with the first model
        providers = _config.load_custom_providers()
        if providers:
            provider = providers[0]
            if not model:
                model = provider.get("models", "").split(",")[0].strip()
    if not provider:
        return ("", model or "", "")
    return (
        provider.get("api_key", ""),
        model or provider.get("models", "").split(",")[0].strip(),
        provider.get("endpoint", ""),
    )


def _strip_think_tags(chunks: Generator[str, None, None]) -> Generator[str, None, None]:
    """Filters out ``<think>…</think>`` blocks from a streaming response.

    Some models (e.g. Gemma 4, Qwen3 reasoning, DeepSeek-R1) prepend
    chain-of-thought reasoning wrapped in think tags.  This generator
    buffers until the closing tag is found (or the stream ends) and
    yields only the non-think content.

    If the stream terminates while still inside a `<think>` block (model
    truncated by ``max_tokens`` mid-reasoning), the buffered reasoning
    is dropped and a WARNING is logged — symmetric with the
    non-streaming ``_strip_think_blocks`` so the user always gets a
    diagnostic pointing at ``max_tokens`` instead of silent empty
    output.
    """
    buf = ""
    inside_think = False
    for chunk in chunks:
        buf += chunk
        while buf:
            if inside_think:
                end = buf.find("</think>")
                if end == -1:
                    # Still inside <think>, consume entire buffer
                    buf = ""
                    break
                # Skip past </think> and any trailing whitespace
                after = end + len("</think>")
                buf = buf[after:].lstrip()
                inside_think = False
            else:
                start = buf.find("<think>")
                if start == -1:
                    # No <think> tag — yield everything, but keep a
                    # small tail in case "<think>" is split across chunks
                    safe = len(buf) - len("<think>") + 1
                    if safe > 0:
                        yield buf[:safe]
                        buf = buf[safe:]
                    break
                # Yield text before <think>, enter think mode
                if start > 0:
                    yield buf[:start]
                buf = buf[start + len("<think>") :]
                inside_think = True
    if inside_think:
        # Stream ended mid-reasoning — buffered tokens are unrenderable
        # think content.  Match the diagnostic message used by
        # ``_strip_think_blocks`` so users see the same advice
        # regardless of streaming vs non-streaming path.
        logger.warning(
            "Streaming response ended inside an unclosed <think> block — "
            "likely truncated by max_tokens before the answer was emitted. "
            "Try a higher max_tokens or a non-reasoning model.",
        )
        return
    # Flush remaining buffer (not inside a think block)
    if buf:
        yield buf


def _guess_image_mime(path: str) -> str:
    """Returns the MIME type for an image path based on its extension."""
    return _IMAGE_MIME.get(Path(path).suffix.lower(), "image/jpeg")


# Regex to strip inline HTML/XML tags for glossary matching.
# Formatting tags (<b>, <span ...>, <a href="...">, etc.) inserted by
# office extractors would otherwise break substring search against
# glossary terms that are plain text.
_STRIP_TAGS_RE = re.compile(r"<[^>]+>")


def retry_api_call(
    max_retries: int = RETRY_MAX_ATTEMPTS,
    base_delay: float = RETRY_BASE_DELAY,
) -> Callable[..., Any]:
    """Decorator to retry LLM API calls with exponential backoff on transient errors."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        """Wraps *func* with retry logic for transient LLM errors."""

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
            """Invokes the wrapped function, retrying on transient errors."""
            retries = 0
            while True:
                try:
                    return func(*args, **kwargs)
                except ValueError as e:
                    # Retry only on specific transient/rate-limit errors
                    if str(e) in TRANSIENT_ERROR_TAGS:
                        retries += 1
                        if retries > max_retries:
                            logger.error(
                                "Max retries (%d) reached for %s",
                                max_retries,
                                func.__name__,
                            )
                            raise
                        delay = base_delay * (2 ** (retries - 1))
                        logger.warning(
                            "Transient error '%s' in %s. Retrying %d/%d in %.1fs...",
                            e,
                            func.__name__,
                            retries,
                            max_retries,
                            delay,
                        )
                        time.sleep(delay)
                    else:
                        raise

        return wrapper

    return decorator


def _get_gemini_safety_settings() -> list[dict[str, str]]:
    """Returns Gemini safety settings with all categories set to BLOCK_NONE.

    Returns:
        List of safety setting dicts disabling content filtering so that
        translation of sensitive source material is not blocked.
    """
    return [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_CIVIC_INTEGRITY", "threshold": "BLOCK_NONE"},
    ]


def _build_gemini_client(api_key: str = "") -> Any:  # noqa: ANN401
    """Constructs a ``google.genai.Client`` for Gemini.

    Reads ``llm/gemini_use_vertex`` from settings to decide between the
    public Gemini Developer API (API-key auth) and Google Cloud Vertex
    AI (project + location + ADC, optionally a service-account JSON).
    The same SDK call surface (``client.models.generate_content``) works
    for both — only the constructor differs.

    Auth resolution order for Vertex AI:
    1. Service-account JSON path from ``llm/vertex_credentials`` (if set).
    2. Application Default Credentials — ``gcloud auth application-default
       login``, the ``GOOGLE_APPLICATION_CREDENTIALS`` env var, or GCE
       metadata when running on Google Cloud.

    Raises ``ValueError("AUTH_ERROR")`` when neither path is configured.
    """
    from google import genai  # noqa: PLC0415

    use_vertex = bool(
        _config.load_setting(SETTING_LLM_GEMINI_USE_VERTEX, False),
    )

    if use_vertex:
        project = _config.load_setting(SETTING_LLM_VERTEX_PROJECT, "").strip()
        location = (
            _config.load_setting(
                SETTING_LLM_VERTEX_LOCATION,
                VERTEX_DEFAULT_LOCATION,
            ).strip()
            or VERTEX_DEFAULT_LOCATION
        )
        credentials_path = _config.load_setting(
            SETTING_LLM_VERTEX_CREDENTIALS,
            "",
        ).strip()
        if not project:
            raise ValueError("AUTH_ERROR:Vertex AI")

        credentials = None
        if credentials_path:
            from google.oauth2 import service_account  # noqa: PLC0415

            try:
                credentials = service_account.Credentials.from_service_account_file(
                    credentials_path,
                    scopes=["https://www.googleapis.com/auth/cloud-platform"],
                )
            except (FileNotFoundError, OSError, ValueError) as exc:
                logger.error(
                    "Vertex AI service-account file %s could not be loaded: %s",
                    credentials_path,
                    exc,
                )
                raise ValueError("AUTH_ERROR:Vertex AI") from exc

        return genai.Client(
            vertexai=True,
            project=project,
            location=location,
            credentials=credentials,
        )

    # Developer API path: API key required.
    if not api_key:
        raise ValueError("AUTH_ERROR:Gemini")
    return genai.Client(api_key=api_key)


def _gemini_safety_settings_for_sdk() -> list[Any]:
    """Returns safety settings as ``types.SafetySetting`` objects.

    Same threshold matrix as :func:`_get_gemini_safety_settings` but
    typed for the SDK.
    """
    from google.genai import types  # noqa: PLC0415

    return [
        types.SafetySetting(category=cat, threshold="BLOCK_NONE")
        for cat in (
            "HARM_CATEGORY_HARASSMENT",
            "HARM_CATEGORY_HATE_SPEECH",
            "HARM_CATEGORY_SEXUALLY_EXPLICIT",
            "HARM_CATEGORY_DANGEROUS_CONTENT",
            "HARM_CATEGORY_CIVIC_INTEGRITY",
        )
    ]


def _openai_error_body(e: Any) -> str:  # noqa: ANN401
    """Returns the response body from an openai SDK exception.

    Handles both the typed ``body`` attribute (when the server returned
    JSON the SDK could parse) and the raw ``response.text`` fallback.
    Returns ``""`` when neither is available so callers can still log a
    default message.
    """
    body = getattr(e, "body", None)
    if body is not None:
        try:
            return json.dumps(body)
        except (TypeError, ValueError):
            return str(body)
    response = getattr(e, "response", None)
    if response is not None:
        try:
            return response.text
        except Exception:  # noqa: BLE001 - SDK response shape varies
            return ""
    return ""


def _handle_api_error(  # noqa: PLR0912, PLR0915
    e: Exception,
    provider: str = "Gemini",
    context_name: str = "Standard",
) -> NoReturn:
    """Unified error handler for all LLM API providers.

    Inspects the exception type and raises a ``ValueError`` with an
    error-tag string (e.g. ``"AUTH_ERROR"``, ``"TIMEOUT_ERROR"``), or
    re-raises the original exception if no tag applies.  Recognises
    ``openai.APIError`` (Custom path) and
    ``google.genai.errors.APIError`` (Gemini path).

    Args:
        e: The caught exception.
        provider: Provider name for logging ("Gemini" or "Custom").
        context_name: Context label ("Standard" or "Vision").

    Raises:
        ValueError: With an error-tag string for known HTTP/network errors.
        Exception: Re-raises *e* for unrecognised error types.
    """
    # google-genai SDK exceptions — single APIError class with status code
    # in ``code``; route through the shared HTTP map so the same status
    # produces the same tag string regardless of provider.
    from google.genai import errors as _genai_errors  # noqa: PLC0415

    if isinstance(e, _genai_errors.APIError):
        status = getattr(e, "code", 0) or 0
        message = getattr(e, "message", "") or str(e)
        body_lower = message.lower()
        if any(ind in body_lower for ind in VISION_UNSUPPORTED_INDICATORS):
            logger.error(
                "%s %s vision-not-supported: %s",
                provider,
                context_name,
                message,
            )
            raise ValueError("VISION_NOT_SUPPORTED") from e
        logger.error(
            "%s %s genai error %s: %s",
            provider,
            context_name,
            status,
            message,
        )
        tag = (
            _HTTP_ERROR_MAP.get(int(status), "INVALID_REQUEST")
            if status
            else ("INVALID_REQUEST")
        )
        # Google's quirk (shared by Gemini Developer API and Cloud TTS):
        # an invalid API key returns HTTP 400 with the auth-failure
        # reason in the message — NOT 401/403 like most APIs.  The
        # heuristic ("api" AND "key" both appear in the body) catches
        # every wire-level phrasing across Google ("API key not
        # valid", "API_KEY_INVALID"), OpenAI ("Invalid API key",
        # "incorrect api key", "invalid_api_key"), Anthropic
        # ("invalid x-api-key"), and unknown future variants —
        # without maintaining a fragile substring list.  False-
        # positive risk is small: non-auth 400 bodies rarely mention
        # both words together.
        if tag == "INVALID_REQUEST" and "api" in body_lower and "key" in body_lower:
            tag = "AUTH_ERROR"
        # Append the provider name to AUTH_ERROR so the user-facing
        # toast can say "Invalid Gemini API key" instead of generic
        # "Invalid API key" — knowing WHICH key is bad is critical
        # when the app has 4 separate auth-required keys.
        if tag == "AUTH_ERROR":
            tag = f"AUTH_ERROR:{provider}"
        raise ValueError(tag) from e

    # openai SDK exceptions — checked next so APITimeoutError takes
    # precedence over the generic TimeoutError clause below.
    from openai import (  # noqa: PLC0415
        APIConnectionError,
        APIStatusError,
        APITimeoutError,
        AuthenticationError,
        BadRequestError,
        NotFoundError,
        PermissionDeniedError,
        RateLimitError,
    )

    if isinstance(e, AuthenticationError | PermissionDeniedError):
        body = _openai_error_body(e)
        logger.error(
            "%s %s auth error: %s — Body: %s",
            provider,
            context_name,
            e,
            body,
        )
        raise ValueError(f"AUTH_ERROR:{provider}") from e
    if isinstance(e, RateLimitError):
        body = _openai_error_body(e)
        logger.error(
            "%s %s quota error: %s — Body: %s",
            provider,
            context_name,
            e,
            body,
        )
        raise ValueError("QUOTA_ERROR") from e
    if isinstance(e, NotFoundError):
        body = _openai_error_body(e)
        logger.error(
            "%s %s model not found: %s — Body: %s",
            provider,
            context_name,
            e,
            body,
        )
        raise ValueError("MODEL_NOT_FOUND") from e
    if isinstance(e, BadRequestError):
        body = _openai_error_body(e)
        body_lower = body.lower()
        if any(ind in body_lower for ind in VISION_UNSUPPORTED_INDICATORS):
            raise ValueError("VISION_NOT_SUPPORTED") from e
        # Some OpenAI-compatible providers (including the Gemini
        # Developer API proxy when accessed via the OpenAI shim) and
        # several proxy stacks return HTTP 400 with the auth-failure
        # reason in the body instead of the documented 401/403.
        # Same heuristic as the genai-SDK branch above: if BOTH "api"
        # and "key" appear in the body it's almost certainly an auth
        # failure (non-auth 400s rarely mention both words together).
        if "api" in body_lower and "key" in body_lower:
            logger.error(
                "%s %s auth error (400 with API-key-invalid body): %s — Body: %s",
                provider,
                context_name,
                e,
                body,
            )
            raise ValueError(f"AUTH_ERROR:{provider}") from e
        logger.error(
            "%s %s bad request: %s — Body: %s",
            provider,
            context_name,
            e,
            body,
        )
        raise ValueError("INVALID_REQUEST") from e
    if isinstance(e, APITimeoutError):
        raise ValueError("TIMEOUT_ERROR") from e
    if isinstance(e, APIConnectionError):
        raise ValueError("CONNECTION_ERROR") from e
    if isinstance(e, APIStatusError):
        # Catch-all for any other HTTP status (5xx mostly).
        body = _openai_error_body(e)
        logger.error(
            "%s %s HTTP %d: %s — Body: %s",
            provider,
            context_name,
            e.status_code,
            e,
            body,
        )
        tag = _HTTP_ERROR_MAP.get(e.status_code, "INVALID_REQUEST")
        # Defensive wrap: ``AuthenticationError`` / ``PermissionDeniedError``
        # branches above normally catch 401/403, but a custom-error
        # pipeline or older SDK version could deliver them as
        # ``APIStatusError``.  Mirror the genai-branch's wrap so any
        # AUTH_ERROR raised here also carries the ``:Service`` suffix.
        if tag == "AUTH_ERROR":
            tag = f"AUTH_ERROR:{provider}"
        raise ValueError(tag) from e

    if isinstance(e, TimeoutError):
        raise ValueError("TIMEOUT_ERROR") from e
    if isinstance(e, (json.JSONDecodeError, KeyError, IndexError)):
        logger.error(
            "%s %s invalid response: %s",
            provider,
            context_name,
            e,
        )
        raise ValueError("INVALID_RESPONSE") from e
    logger.error(
        "%s %s translation error: %s",
        provider,
        context_name,
        e,
        exc_info=True,
    )
    raise e


# HTTP status code -> error tag mapping for LLM API responses.
_HTTP_ERROR_MAP: dict[int, str] = {
    400: "INVALID_REQUEST",
    401: "AUTH_ERROR",
    403: "AUTH_ERROR",
    404: "MODEL_NOT_FOUND",
    413: "REQUEST_TOO_LARGE",
    429: "QUOTA_ERROR",
    500: "SERVICE_UNAVAILABLE_ERROR",
    502: "SERVICE_UNAVAILABLE_ERROR",
    503: "SERVICE_UNAVAILABLE_ERROR",
    504: "TIMEOUT_ERROR",
}


def _format_glossary_hint(
    glossary_entries: list[tuple[int, str, str]] | None,
) -> str:
    """Formats glossary entries as a compact hint for vision/image prompts."""
    if not glossary_entries:
        return ""
    entries_str = ", ".join(f"{src} <-> {tgt}" for _, src, tgt in glossary_entries)
    return GLOSSARY_HINT_TEMPLATE.format(entries=entries_str)


def _classify_custom_endpoint(endpoint: str) -> tuple[str | None, str]:
    """Inspects *endpoint* and returns ``(explicit_api, base_url)``.

    *explicit_api* is ``"chat"`` or ``"responses"`` when the user pasted
    a URL that already names the API (i.e. ends with
    ``/chat/completions`` or ``/responses``); ``None`` means the user
    pasted a base URL like ``/v1`` and we should auto-derive both paths.
    *base_url* is always the URL stripped of the leaf API segment so
    callers can append whichever path they need.

    When the user is explicit, the dispatcher honours the choice and
    skips the chat→responses auto-fallback — pasting ``/responses``
    means "this model needs the Responses API, don't probe chat."
    """
    url = endpoint.strip().rstrip("/")
    if url and not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    if url.endswith("/chat/completions"):
        return ("chat", url[: -len("/chat/completions")])
    if url.endswith("/responses"):
        return ("responses", url[: -len("/responses")])
    return (None, url)


# ── Text Translation Prompt Builder ──────────────────────────

# Content-type-specific translation instructions appended to LLM prompts.
_FORMAT_RULES: dict[str, str] = {
    CONTENT_PLAIN_TEXT: (
        " Produce fluent, natural text."
        " Preserve paragraph breaks and whitespace."
        " Do not add formatting or markup."
    ),
    CONTENT_MARKDOWN: (
        " Preserve all Markdown syntax exactly:"
        " headings (#), bold (**), italic (*),"
        " links, code blocks, lists, and tables."
        " Do not translate content inside code blocks."
        " Only translate human-readable text."
        " Preserve any [__PRESERVE_MD_N__] markers exactly as-is."
    ),
    CONTENT_HTML: (
        " Preserve all HTML tags and structure exactly."
        " Only translate visible text content between tags"
        " and translatable attribute values"
        " (alt, title, placeholder, label, aria-label, etc.)."
        " Do not modify or remove any HTML tags."
    ),
    CONTENT_XML: (
        " Preserve all XML tags and structure exactly."
        " Only translate text content between tags."
        " Do not modify or remove any XML tags."
        " Preserve any [__PRESERVE_XML_N__] markers exactly as-is."
    ),
    CONTENT_SUBTITLE: (
        " These are subtitle/dialogue lines from a video."
        " Translate each line naturally as spoken dialogue."
        " Keep translations concise for subtitle display."
        " Preserve any inline HTML tags (<i>, <b>, <u>) exactly."
        " Preserve line breaks within entries."
        " Do not add formatting or tags not present in the original."
    ),
    CONTENT_LOCALIZATION: (
        " These are software UI localization strings."
        " Translate each string independently."
        " Preserve all placeholders exactly as-is:"
        " {name}, {0}, %s, %d, %f, %(name)s, %1$s,"
        " ${var}, {{escaped}}, etc."
        " Keep translations concise and appropriate for UI display."
        " Do not translate or modify placeholder tokens."
    ),
    CONTENT_RTF: (
        " Only translate the readable text."
        " Preserve any [__PRESERVE_RTF_N__] markers exactly as-is"
        " in their original positions relative to the text."
        " Do not add or remove markers."
    ),
    CONTENT_EPUB: (
        " The input is XHTML content from an EPUB book."
        " Preserve all HTML tags and structure exactly."
        " Only translate visible text content between tags"
        " and translatable attribute values"
        " (alt, title, placeholder, label, aria-label, etc.)."
        " Do not modify or remove any HTML tags."
    ),
    CONTENT_DATA_VALUES: (
        " These are isolated data values (e.g. labels,"
        " menu items, short strings)."
        " Translate each independently."
        " Keep translations concise."
    ),
    CONTENT_PDF: (
        " These are text blocks extracted from a PDF document."
        " Translate naturally and fluently."
        " Preserve paragraph structure."
        " If inline HTML tags (<b>, <i>, <sup>, <sub>, <span>) are present,"
        " preserve them exactly. Do not add or remove tags."
    ),
}


def _format_lang_pair(source_lang: str, target_lang: str) -> str:
    """Formats the language direction clause for LLM prompts.

    When *source_lang* is empty the clause omits it so the LLM
    auto-detects the source language.

    Examples:
        >>> _format_lang_pair("", "French")
        'Translate the following into French.'
        >>> _format_lang_pair("English (US)", "French")
        'Translate the following from English (US) to French.'
    """
    if not source_lang:
        return f"Translate the following into {target_lang}."
    return f"Translate the following from {source_lang} to {target_lang}."


def _format_glossary_block(
    glossary_entries: list[tuple[int, str, str]] | None,
) -> str:
    """Formats glossary entries as a structured block for text prompts."""
    if not glossary_entries:
        return ""
    pairs = " | ".join(f"{src} = {tgt}" for _, src, tgt in glossary_entries)
    return f"\nGlossary (use these exact translations): {pairs}."


def _compress_glossary(
    glossary_entries: list[tuple[int, str, str]] | None,
    texts: list[str],
) -> list[tuple[int, str, str]] | None:
    """Filters glossary to only entries relevant to the current batch.

    Uses normalized matching (case-insensitive + accent-insensitive)
    of each glossary entry's source AND target terms against the
    concatenated batch text.  This handles bidirectional translation
    and diacritical variants — e.g., glossary ("Hello", "Xin chào")
    matches text containing "xin chao" (no accents).

    Inline HTML tags (``<b>``, ``<span ...>``, ``<a href="...">``, etc.)
    are stripped before matching so that formatted text like
    ``"<b>hello</b> world"`` still matches the glossary term
    ``"hello world"``.

    Args:
        glossary_entries: Full glossary (id, source_text, target_text).
        texts: The batch of text strings being translated.

    Returns:
        Filtered glossary entries, or None if no matches.
    """
    if not glossary_entries:
        return None
    # Strip HTML/XML tags and normalize for accent/case-insensitive matching
    raw = "\n".join(texts)
    combined = normalize_for_search(_STRIP_TAGS_RE.sub("", raw))
    relevant = [
        entry
        for entry in glossary_entries
        if entry[1].strip()
        and entry[2].strip()
        and (
            normalize_for_search(entry[1]) in combined
            or normalize_for_search(entry[2]) in combined
        )
    ]
    return relevant or None


def _format_context_block(context: list[str] | None) -> str:
    """Formats prior sentences as a reference-only context block.

    Used by Live Translation to give the LLM enough surrounding
    context (~2 sentences) to disambiguate pronouns, topic continuity,
    tone, and elliptical phrasing in the current sentence.  The
    returned block is appended to the system prompt with explicit
    "do not translate" instructions so the model doesn't echo the
    context back in the response.

    Returns an empty string when *context* is empty / None — most
    batch-translation paths (file translation, etc.) don't carry
    conversational context.
    """
    if not context:
        return ""
    # Strip falsy entries — caller may pass a deque that hasn't filled
    # yet, leaving empty strings as placeholders.
    cleaned = [c.strip() for c in context if c and c.strip()]
    if not cleaned:
        return ""
    lines = "\n".join(f"- {c}" for c in cleaned)
    return (
        " Recent prior sentences from the same conversation are listed"
        " below for reference ONLY — they establish topic, tone, and"
        " referents (he/she/it/they) for the current input."
        " DO NOT translate these prior sentences and DO NOT include"
        " them in the response. Only translate items in the Input"
        f" array.\nPrior sentences:\n{lines}\n"
    )


def _build_translation_prompt(
    content_type: str,
    source_lang: str,
    target_lang: str,
    glossary_entries: list[tuple[int, str, str]] | None = None,
    context: list[str] | None = None,
) -> str:
    """Builds a format-specific translation prompt.

    Assembles: role + language pair + format rules + glossary +
    optional conversational context + output format.

    Args:
        content_type: One of the CONTENT_* constants from llm.py.
        source_lang: Source language name, or empty for auto-detect.
        target_lang: Target language name.
        glossary_entries: Optional glossary (id, source, target).
        context: Optional list of prior source-text sentences to
            include as reference-only context (no translation).
            Used by Live Translation for topic / pronoun continuity.

    Returns:
        str: The complete prompt text.
    """
    lang_pair = _format_lang_pair(source_lang, target_lang)
    rules = _FORMAT_RULES.get(
        content_type,
        _FORMAT_RULES[CONTENT_PLAIN_TEXT],
    )
    glossary = _format_glossary_block(glossary_entries)
    context_block = _format_context_block(context)
    # Quality guidance is relevant for prose, not isolated data values
    if content_type == CONTENT_DATA_VALUES:
        quality = ""
    else:
        quality = (
            " Preserve the original tone, style, and context."
            " Ensure the translation reads naturally"
            " to a native speaker."
        )
    output_fmt = (
        ' Respond with only a JSON object: {"results":'
        ' [{"id": <int>, "translated": <string>}, ...]}.'
        " Preserve every ID from the input."
        " Do not include any text outside the JSON."
    )
    return (
        f"You are a professional translator."
        f" {lang_pair}{rules}{quality}{glossary}{context_block}{output_fmt}"
    )


def _build_image_translation_prompt(
    target_lang: str,
    glossary_hint: str,
) -> str:
    """Builds the shared prompt for vision-based image translation."""
    return (
        "You are a professional image translator."
        " I will provide an image and a list of text"
        " fragments detected by OCR with their IDs.\n"
        "**ABSOLUTE MANDATE:** You MUST treat the"
        " provided image as the SINGLE SOURCE OF TRUTH."
        " The OCR text provided is only a rough guide"
        " and likely contains errors, omissions,"
        " or artifacts. Your task is to:\n"
        "1. Visually verify the existence and content"
        " of every text fragment against the image."
        " If the image shows different text than the"
        " OCR, use the image's text. If the OCR text"
        " does not exist in the image, it is a"
        " hallucination and MUST be discarded.\n"
        "2. Determine translatability BASED SOLELY ON"
        " THE IMAGE. Discard any fragment (do not"
        " include its ID and content in the response) if the"
        " image shows it is:\n"
        "   - A number, date, proper name, brand logo,"
        " or UI element that is visually better"
        " left original.\n"
        "   - A non-text element (lines, borders,"
        " symbols, graphical artifacts).\n"
        f"   - A text entirely in {target_lang} or including special characters"
        " do not need to be translated.\n"
        "   - Part of a complex graphic where"
        " replacement would be visually destructive.\n"
        "3. Group valid fragments into logical text"
        " blocks based on the visual layout of the"
        " image. Each block MUST correspond to a"
        " single, natural paragraph as seen visually."
        " **SMART MERGING:** You may merge multiple"
        " detected line blocks if they clearly belong"
        " to the same paragraph. Only merge if they"
        " share the same semantic context, same visual"
        " style, and there are NO borders, dividers,"
        " or separators (except blank lines) between"
        " them. You MUST preserve all line breaks and"
        " blank lines exactly as they appear in the"
        " original image using <br> tags.**\n"
        "4. For each paragraph, provide a combined"
        f" translation into {target_lang}, preserving"
        " the tone, context, and original"
        f" punctuation.{glossary_hint}\n"
        "5. Use HTML-like tags within the"
        " 'translated_html' string to represent mixed"
        " styles: <b> for bold, <i> for italic,"
        ' <u> for underline, <span style="color:'
        ' #RRGGBB"> for specific text colors,'
        " and <br> for line breaks.\n"
        "6. Detect the primary base style from the"
        " image: base color (hex #RRGGBB) and"
        " horizontal alignment"
        " (left, center, or right).\n"
        "7. Return the list of input OCR fragment IDs"
        " that belong to each paragraph.\n\n"
        "Return a JSON object with a 'paragraphs'"
        " array. Each element has: 'ids' (array of"
        " ints), 'translated_html' (string), 'color'"
        " (hex string), 'alignment'"
        " ('left'|'center'|'right')."
        " Let the image be your only guide for truth."
    )


def _estimate_tokens(text: str) -> int:
    """Estimates the number of tokens in a string.

    Latin/Cyrillic scripts average ~1 token per 4 characters.
    CJK characters (U+3000+) are typically 1-2 tokens each, so
    they are counted individually to avoid underestimating
    batches that could exceed the model's output token limit.

    Args:
        text: Input text string.

    Returns:
        int: Estimated token count (minimum 1).
    """
    cjk = sum(1 for c in text if ord(c) > CJK_CODEPOINT_THRESHOLD)
    return max(1, cjk + (len(text) - cjk) // 4)


def _split_by_token_budget(
    texts: list[str],
    budget: int = TOKEN_BUDGET,
) -> list[list[str]]:
    """Groups texts into sub-batches that fit within a token budget.

    Iterates through *texts*, accumulating items into a sub-batch.
    When adding the next item would exceed *budget*, the current
    sub-batch is flushed and a new one is started. A single item
    larger than the budget is kept as its own sub-batch (never split).

    Args:
        texts: List of text strings to group.
        budget: Maximum estimated tokens per sub-batch.

    Returns:
        list[list[str]]: List of sub-batches.
    """
    if not texts:
        return []

    batches: list[list[str]] = []
    current_batch: list[str] = []
    current_tokens = 0

    for text in texts:
        item_tokens = _estimate_tokens(text) + JSON_ITEM_OVERHEAD
        # Flush current batch if adding this item would exceed budget
        if current_batch and current_tokens + item_tokens > budget:
            batches.append(current_batch)
            current_batch = []
            current_tokens = 0
        current_batch.append(text)
        current_tokens += item_tokens

    # Flush remaining items
    if current_batch:
        batches.append(current_batch)

    return batches


# ── Untranslatable Content Filter ─────────────────────────────

# Matches strings that are entirely numbers/symbols/URLs/emails/file paths.
_UNTRANSLATABLE_RE = re.compile(
    r"^("
    r"[\d\s.,;:!?%$€£¥#+\-*/=@^~<>(){}\[\]|\\&_\"']+"  # Numbers/symbols/punctuation
    r"|https?://\S+"  # HTTP(S) URLs
    r"|www\.\S+"  # www URLs
    r"|[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"  # Email addresses
    r"|[A-Za-z]:\\[\S]+"  # Windows file paths
    r"|/(?:usr|etc|var|home|tmp|opt)/[\S]+"  # Unix file paths
    r")$",
    re.DOTALL,
)


def _is_untranslatable(text: str) -> bool:
    """Checks whether a string needs no translation.

    Returns True for pure numbers/symbols, URLs, emails, file paths,
    and empty/whitespace-only strings.  Only matches when the *entire*
    string is untranslatable — mixed content (e.g. "Price: $100") is
    sent to the LLM.

    Args:
        text: Input string to check.

    Returns:
        bool: True if the text should be returned as-is.
    """
    stripped = text.strip()
    if not stripped:
        return True
    return bool(_UNTRANSLATABLE_RE.match(stripped))


# ── Deduplication Helpers ─────────────────────────────────────


def _deduplicate_texts(
    texts: list[str],
) -> tuple[list[str], dict[str, list[int]]]:
    """Removes duplicate strings, returning unique texts and an index map.

    Args:
        texts: Input strings (may contain duplicates).

    Returns:
        Tuple of (unique_texts, dupe_map) where dupe_map maps each
        unique text to the list of original indices it appeared at.
    """
    seen: dict[str, list[int]] = {}
    unique: list[str] = []
    for i, text in enumerate(texts):
        if text in seen:
            seen[text].append(i)
        else:
            seen[text] = [i]
            unique.append(text)
    return unique, seen


def _restore_duplicates(
    unique_translated: list[str],
    unique_texts: list[str],
    dupe_map: dict[str, list[int]],
    original_texts: list[str],
) -> list[str]:
    """Expands deduplicated results back to the original ordering.

    If *unique_translated* is shorter than *unique_texts* (e.g. due to
    mid-way cancellation), only the translated portion is expanded;
    remaining positions retain their original values.

    Args:
        unique_translated: Translated unique texts (same order as unique_texts).
        unique_texts: Original unique texts (keys into dupe_map).
        dupe_map: Maps original text → list of original indices.
        original_texts: The pre-dedup input list; used as fallback so
            untranslated positions keep their original values.

    Returns:
        Full result list with duplicates restored.
    """
    result = list(original_texts)
    for translated, original in zip(
        unique_translated,
        unique_texts,
        strict=False,
    ):
        for idx in dupe_map[original]:
            result[idx] = translated
    return result


def translate_text(  # noqa: PLR0912, PLR0913
    texts: list[str],
    target_lang: str,
    source_lang: str = "",
    progress_callback: Callable[[int], None] | None = None,
    glossary_entries: list[tuple[int, str, str]] | None = None,
    content_type: str = CONTENT_PLAIN_TEXT,
    cancel_check: Callable[[], bool] | None = None,
    *,
    provider: str | None = None,
    model: str | None = None,
    context: list[str] | None = None,
) -> list[str]:
    """Translates text fragments via the configured LLM provider.

    Applies two token-saving optimizations before calling the LLM:

    1. **Filtering** — strings that are purely numeric, URLs, emails,
       file paths, or symbols are returned as-is (no API call).
    2. **Deduplication** — identical strings are translated once and
       the result is copied to all positions where the string appeared.

    Args:
        texts: List of text strings to translate.
        target_lang: Target language name.
        source_lang: Source language name, or empty for auto-detect.
        progress_callback: Called with 0-100 progress percentage.
        glossary_entries: Optional glossary (id, source, target).
        content_type: One of the CONTENT_* constants indicating
            the format of the text being translated.
        cancel_check: Optional callable that returns True when
            the task has been cancelled.  Checked between sub-batches.
        provider: LLM provider name override (e.g. "Gemini").
        model: LLM model name override (e.g. "gemini-3-flash-preview").
        context: Optional list of prior source-language sentences
            included in the system prompt as reference-only context.
            Used by Live Translation for pronoun / topic continuity
            across consecutive sentences.  Not translated; not
            returned in results.

    Returns:
        list[str]: Translated text strings (always same length as
            *texts*).  If cancelled mid-way, untranslated items
            retain their original values.
    """
    if not texts:
        return []

    # --- Phase 1: Filter untranslatable items ---
    translatable_indices: list[int] = []
    result: list[str] = list(texts)  # pre-fill with originals
    for i, text in enumerate(texts):
        if not _is_untranslatable(text):
            translatable_indices.append(i)

    if not translatable_indices:
        # Nothing to translate — all items are untranslatable
        if progress_callback:
            progress_callback(100)
        return result

    translatable_texts = [texts[i] for i in translatable_indices]

    # --- Phase 2: Deduplicate ---
    unique_texts, dupe_map = _deduplicate_texts(translatable_texts)

    # --- Phase 3: Translate unique texts via LLM ---
    resolved_provider, resolved_model = _resolve_provider_model(provider, model)

    if resolved_provider == LLM_METHOD_GEMINI:
        translate_fn = _translate_gemini
    elif resolved_provider == LLM_METHOD_CUSTOM:
        translate_fn = _translate_custom
    else:
        return result

    batches = _split_by_token_budget(unique_texts, TOKEN_BUDGET)
    unique_translated: list[str] = []
    done = 0
    for batch in batches:
        # Check cancellation between sub-batches
        if cancel_check and cancel_check():
            break
        translated_batch = translate_fn(
            batch,
            target_lang,
            source_lang,
            glossary_entries,
            content_type,
            resolved_model,
            context=context,
        )
        unique_translated.extend(translated_batch)
        done += len(batch)
        if progress_callback:
            progress_callback(int((done / len(unique_texts)) * 100))

    # --- Phase 4: Restore duplicates ---
    expanded = _restore_duplicates(
        unique_translated,
        unique_texts,
        dupe_map,
        translatable_texts,
    )

    # --- Phase 5: Map back to original positions ---
    for local_idx, orig_idx in enumerate(translatable_indices):
        if local_idx < len(expanded):
            result[orig_idx] = expanded[local_idx]

    return result


_GEMINI_TRANSLATION_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "results": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "id": {"type": "INTEGER"},
                    "translated": {"type": "STRING"},
                },
                "required": ["id", "translated"],
            },
        },
    },
    "required": ["results"],
}


@retry_api_call()
def _translate_gemini(  # noqa: PLR0913
    texts: list[str],
    target_lang: str,
    source_lang: str,
    glossary_entries: list[tuple[int, str, str]] | None = None,
    content_type: str = CONTENT_PLAIN_TEXT,
    model: str = "",
    *,
    context: list[str] | None = None,
) -> list[str]:
    """Translates text using the Gemini API via the google-genai SDK.

    Sends the prompt + JSON-shaped input list, asks for a JSON-schema
    response, parses the SDK's typed ``response.text`` back into the
    ``{id, translated}`` items the caller's positional list expects.

    *context* (when provided) is woven into the system prompt as
    reference-only prior sentences — used by Live Translation for
    pronoun / topic continuity.
    """
    from google.genai import types  # noqa: PLC0415

    api_key = _config.load_setting(SETTING_LLM_GEMINI_API_KEY, "")
    if not model:
        model = DEFAULT_GEMINI_MODEL

    client = _build_gemini_client(api_key)

    input_data = [{"id": i, "text": t} for i, t in enumerate(texts)]
    compressed_glossary = _compress_glossary(glossary_entries, texts)
    prompt = _build_translation_prompt(
        content_type,
        source_lang,
        target_lang,
        compressed_glossary,
        context,
    )
    input_json = json.dumps(input_data, ensure_ascii=False)
    user_text = f"{prompt}\n\nInput: {input_json}"

    logger.debug("Gemini Standard request (model=%s)", model)
    try:
        response = client.models.generate_content(
            model=model,
            contents=user_text,
            config=types.GenerateContentConfig(
                temperature=LLM_TEMPERATURE,
                response_mime_type="application/json",
                response_schema=_GEMINI_TRANSLATION_SCHEMA,
                safety_settings=_gemini_safety_settings_for_sdk(),
            ),
        )
        text = response.text or ""
        text = _strip_think_blocks(text)
        content_json = json.loads(text)
        mapping = {
            item["id"]: item["translated"]
            for item in content_json.get("results", [])
            if "id" in item
        }
        return [mapping.get(i, t) for i, t in enumerate(texts)]
    except Exception as e:
        _handle_api_error(e, "Gemini", "Standard")


_JSON_OBJECT_FENCE_RE = re.compile(r"\{.*\}", re.DOTALL)

# Per-session cache of which API endpoint each (endpoint, model) pair uses.
# Populated on first successful call so future requests skip the failed
# variant (e.g. chat/completions) and go straight to the working one
# (e.g. responses).  Saves a round-trip per call for every translation
# after the first.
_CUSTOM_API_CACHE: dict[tuple[str, str], str] = {}

# Per-session cache of which chat/completions payload variant (see
# ``_translate_custom_chat``) succeeded for each (endpoint, model) pair.
# Reasoning models (o1/o3/gpt-5.x) reject the rich payload and only
# accept the "minimal" or "no_system_role" variant; without this cache
# every batch re-tries the doomed variants first and pays 2-3 failed
# 400s before landing on the working one.  When a stale cache entry
# stops working (provider config changed), the dispatcher falls through
# to the remaining variants in original order and rewrites the cache on
# the next success.
_CUSTOM_VARIANT_CACHE: dict[tuple[str, str], str] = {}


def _custom_cache_key(endpoint: str, model: str) -> tuple[str, str]:
    """Canonical key for ``_CUSTOM_API_CACHE`` / ``_CUSTOM_VARIANT_CACHE``.

    Routes ``endpoint`` through ``_classify_custom_endpoint`` so cosmetic
    variations (trailing slash, whitespace, missing scheme,
    ``/chat/completions`` vs ``/responses`` vs bare base URL) all collapse
    to the same key — otherwise a user who toggles the URL between
    ``https://api.example.com/v1`` and ``https://api.example.com/v1/`` in
    settings would get two independent cache entries and re-pay the
    variant probe each time.  A genuine endpoint change (different host
    or path prefix) still produces a different key, which is exactly the
    invalidation we want.
    """
    _explicit, base = _classify_custom_endpoint(endpoint)
    return (base, model)


# Persistence schema for ``llm_endpoint_cache.json``.  Survives app
# restarts so CLI / MCP cold starts don't re-pay the variant probe.
# ``|`` joins (endpoint, model) into a string key (JSON has no tuple
# keys); a literal pipe in either field would collide, but neither URLs
# nor model names use it.  Bump ``_CACHE_SCHEMA_VERSION`` whenever the
# layout changes so older / forward files are ignored cleanly.
_CACHE_SCHEMA_VERSION = 1
_CACHE_KEY_SEP = "|"

# Serialises in-process cache mutations + persistence so two MCP daemon
# threads landing on different variants for the same (endpoint, model)
# don't both pass a stale ``!=`` check, both write, and end up with a
# disk file that contradicts the in-memory dict.  Cross-process
# coordination is handled by the read-merge-write pattern in
# ``_persist_caches`` itself, not this lock.  Reentrant so a caller
# can hold the lock across its precheck-and-mutate before invoking
# ``_persist_caches`` (which re-acquires the same lock internally).
_CACHE_LOCK = threading.RLock()


def _decode_cache_payload(
    payload: object,
) -> tuple[dict[tuple[str, str], str], dict[tuple[str, str], str]]:
    """Parses a loaded JSON payload into ``(api_entries, variant_entries)``.

    Silently drops malformed entries so a corrupted file (or one written
    by a different schema version) can't poison the in-memory caches.
    Returns empty dicts when the payload itself is unusable.
    """
    if not isinstance(payload, dict):
        return ({}, {})
    if payload.get("version") != _CACHE_SCHEMA_VERSION:
        return ({}, {})
    api: dict[tuple[str, str], str] = {}
    variant: dict[tuple[str, str], str] = {}
    for raw_key, value in (payload.get("api_cache") or {}).items():
        if not isinstance(raw_key, str) or _CACHE_KEY_SEP not in raw_key:
            continue
        if not isinstance(value, str):
            continue
        endpoint, _, model = raw_key.partition(_CACHE_KEY_SEP)
        api[_custom_cache_key(endpoint, model)] = value
    for raw_key, value in (payload.get("variant_cache") or {}).items():
        if not isinstance(raw_key, str) or _CACHE_KEY_SEP not in raw_key:
            continue
        if not isinstance(value, str):
            continue
        endpoint, _, model = raw_key.partition(_CACHE_KEY_SEP)
        variant[_custom_cache_key(endpoint, model)] = value
    return (api, variant)


def _persist_caches() -> None:
    """Atomically writes both caches to ``get_llm_endpoint_cache_path()``.

    Concurrency-safe in three dimensions:

    * **In-process**: ``_CACHE_LOCK`` serialises mutators so two threads
      can't both pass an ``!=`` precheck and both write conflicting
      values.
    * **Cross-process**: re-reads the on-disk file and *merges* its
      entries underneath ours before writing, so a sibling process
      (e.g. the GUI persisting at the same time the CLI does) never
      loses entries on a dump-and-overwrite.  Our in-memory entries
      take precedence on key collision — the local process is the
      authoritative source for the choices it just observed.
    * **Filesystem**: writes to a unique tmp path
      (``mkstemp`` in the cache dir → process+thread+random suffix) so
      two writers on the same machine never clobber each other's tmp
      file before the rename.  The rename is atomic on POSIX.

    Best-effort: any IO / serialisation failure is logged at WARNING
    and swallowed — the in-memory caches still work, the next session
    just re-pays the probe.  Catches ``OSError`` (filesystem failures)
    and ``(TypeError, ValueError)`` (defensive: a corrupted in-memory
    dict shouldn't crash a translation request).
    """
    from src.utils.path_manager import (  # noqa: PLC0415
        get_llm_endpoint_cache_path,
    )

    cache_path = get_llm_endpoint_cache_path()
    tmp_fd: int | None = None
    tmp_path: Path | None = None
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)

        with _CACHE_LOCK:
            # Read-merge-write: pull the on-disk state first so a
            # sibling process's writes survive our overwrite.  Our
            # in-memory entries win on key collision (we're authoritative
            # for what we just observed succeed).
            disk_api: dict[tuple[str, str], str] = {}
            disk_variant: dict[tuple[str, str], str] = {}
            if cache_path.is_file():
                try:
                    raw = cache_path.read_text(encoding="utf-8")
                    disk_api, disk_variant = _decode_cache_payload(
                        json.loads(raw),
                    )
                except (OSError, json.JSONDecodeError):
                    # Corrupt or unreadable on disk — fall through and
                    # overwrite with our in-memory state, which is
                    # the better source than partial garbage.
                    pass

            merged_api = {**disk_api, **_CUSTOM_API_CACHE}
            merged_variant = {**disk_variant, **_CUSTOM_VARIANT_CACHE}
            payload = {
                "version": _CACHE_SCHEMA_VERSION,
                "api_cache": {
                    f"{ep}{_CACHE_KEY_SEP}{m}": v for (ep, m), v in merged_api.items()
                },
                "variant_cache": {
                    f"{ep}{_CACHE_KEY_SEP}{m}": v
                    for (ep, m), v in merged_variant.items()
                },
            }
            serialized = json.dumps(payload)

            # Unique tmp file per writer so simultaneous persisters
            # don't trample each other's pre-rename file.
            tmp_fd, tmp_name = tempfile.mkstemp(
                prefix=f"{cache_path.name}.",
                suffix=".tmp",
                dir=str(cache_path.parent),
            )
            tmp_path = Path(tmp_name)
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
                tmp_fd = None  # fdopen took ownership
                fh.write(serialized)
            tmp_path.replace(cache_path)
            tmp_path = None  # rename consumed it
    except (OSError, TypeError, ValueError) as exc:
        logger.warning("Failed to persist LLM endpoint cache: %s", exc)
        # Clean up an orphaned tmp file (any failure path before the
        # rename leaves it sitting in the cache dir).
        if tmp_path is not None:
            with contextlib.suppress(OSError):
                tmp_path.unlink()
        if tmp_fd is not None:
            with contextlib.suppress(OSError):
                os.close(tmp_fd)


def _load_persistent_caches() -> None:
    """Populates the in-memory caches from disk on import.

    Best-effort: a missing / malformed / older-schema file leaves both
    caches empty (the next call probes from scratch).  Any successful
    load adds entries via canonical-key reconstruction (in
    ``_decode_cache_payload``) so a stale on-disk key with cosmetic
    differences still collapses with later in-session writes.
    """
    from src.utils.path_manager import (  # noqa: PLC0415
        get_llm_endpoint_cache_path,
    )

    try:
        cache_path = get_llm_endpoint_cache_path()
        if not cache_path.is_file():
            return
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to load LLM endpoint cache: %s", exc)
        return

    api, variant = _decode_cache_payload(payload)
    with _CACHE_LOCK:
        _CUSTOM_API_CACHE.update(api)
        _CUSTOM_VARIANT_CACHE.update(variant)


# NOTE: ``_load_persistent_caches()`` is NOT called automatically on
# import.  Each production entry point (``main.py``, ``cli.py``,
# ``mcp_server.py``) calls it once during bootstrap.  Tests then start
# with empty caches without needing to redirect the on-disk path during
# the brittle pre-fixture collection phase.


def _extract_json_object(content_str: str) -> dict:
    r"""Parses a JSON object out of an LLM response.

    Handles three cases:
    1. Pure JSON — direct ``json.loads``.
    2. JSON wrapped in a ``\`\`\`json`` fence — strip the fence first.
    3. JSON embedded in surrounding prose — extract via balanced-brace regex.

    Raises ``json.JSONDecodeError`` when no parseable object is found.
    """
    stripped = content_str.strip()
    # Strip ```json fences if present.
    if stripped.startswith("```"):
        first_newline = stripped.find("\n")
        if first_newline != -1:
            stripped = stripped[first_newline + 1 :]
        if stripped.endswith("```"):
            stripped = stripped[:-3]
        stripped = stripped.strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        # Fall back to extracting the first balanced { ... } block.
        match = _JSON_OBJECT_FENCE_RE.search(stripped)
        if match is None:
            raise
        return json.loads(match.group(0))


def _parse_translation_results(content_str: str, texts: list[str]) -> list[str]:
    r"""Maps a JSON ``{"results": [...]}`` LLM output back to the input list.

    Handles ``\`\`\`json`` fences via ``_extract_json_object``.  Items
    missing from the response fall back to their original text.
    """
    content_str = _strip_think_blocks(content_str)
    content_json = _extract_json_object(content_str)
    mapping = {
        item["id"]: item["translated"]
        for item in content_json.get("results", [])
        if "id" in item
    }
    return [mapping.get(i, t) for i, t in enumerate(texts)]


def _build_openai_client(api_key: str, endpoint: str) -> Any:  # noqa: ANN401
    """Constructs an ``openai.OpenAI`` client targeting *endpoint*.

    Strips any ``/chat/completions`` or ``/responses`` leaf path so the
    SDK's ``base_url`` is the version-segment root (e.g. ``/v1``); the
    SDK appends the right path per call.  Sends the API key under both
    ``Authorization: Bearer`` (the SDK default) and ``api-key`` (Azure's
    traditional header) so the same client works against OpenAI /
    OpenRouter / vLLM AND Azure OpenAI without per-provider
    configuration.
    """
    from openai import OpenAI  # noqa: PLC0415

    _kind, base = _classify_custom_endpoint(endpoint)
    default_headers: dict[str, str] = {"User-Agent": USER_AGENT}
    if api_key:
        default_headers["api-key"] = api_key
    return OpenAI(
        api_key=api_key or "no-key",
        base_url=base,
        timeout=LLM_TEXT_TIMEOUT,
        default_headers=default_headers,
        max_retries=0,  # We own retry semantics via @retry_api_call.
    )


def _reorder_variants_for_cache_hit(
    variants: list[tuple[str, dict[str, Any]]],
    cache_key: tuple[str, str],
) -> list[tuple[str, dict[str, Any]]]:
    """Returns *variants* with the cached-winner variant moved to position 0.

    Both ``_call_custom_chat_with_fallback`` and ``_translate_custom_chat``
    consult ``_CUSTOM_VARIANT_CACHE`` to put the previously-successful
    variant first; the remaining variants stay in original order so a
    stale cache (provider config changed) still falls through cleanly.
    Returns the input list unchanged when the cache key isn't present
    OR the cached label isn't in this caller's variant list (e.g. a
    label written by the 4-variant translation chain that the 3-variant
    one-shot helper doesn't know about).
    """
    cached_variant = _CUSTOM_VARIANT_CACHE.get(cache_key)
    if not cached_variant:
        return variants
    cached_idx = next(
        (i for i, (label, _) in enumerate(variants) if label == cached_variant),
        -1,
    )
    if cached_idx <= 0:  # not found OR already first → no reorder needed
        return variants
    return [variants[cached_idx]] + [
        v for i, v in enumerate(variants) if i != cached_idx
    ]


def _call_custom_chat_with_fallback(
    client: Any,  # noqa: ANN401
    *,
    model: str,
    endpoint: str,
    messages: list[dict[str, Any]],
    timeout: float | None = None,
) -> str:
    """Sends a one-shot ``chat.completions.create`` with payload fallback.

    Same 3-variant chain as :func:`_translate_custom_chat` minus the
    ``no_system_role`` step (one-shot callers don't have a system role
    that would need merging).  Reuses ``_CUSTOM_VARIANT_CACHE`` so the
    working variant for ``(endpoint, model)`` is shared across every
    custom-chat callsite — translation, vision extract, embedded-image
    translation, and screen translate all converge on the same answer
    after the first discovery.

    Variants tried (in original order, reordered to put a cached hit
    first):

    1. ``temperature`` + ``response_format: json_object`` — the rich
       payload most providers accept.
    2. ``temperature`` only — drops ``response_format`` for providers
       that reject structured-output mode.
    3. ``minimal`` — drops ``temperature`` too — for o1/o3/gpt-5.x and
       other reasoning models that only accept the default ``1``.

    Returns the assistant's content string.  Raises
    ``ValueError("INVALID_REQUEST")`` when every variant returns 400.
    Other exceptions propagate so the caller's ``_handle_api_error``
    wrapper maps them to the standard tag set.
    """
    from openai import BadRequestError  # noqa: PLC0415

    variants: list[tuple[str, dict[str, Any]]] = [
        (
            "json_object+temperature",
            {
                "temperature": LLM_TEMPERATURE,
                "response_format": {"type": "json_object"},
            },
        ),
        ("temperature_only", {"temperature": LLM_TEMPERATURE}),
        ("minimal", {}),
    ]

    variant_cache_key = _custom_cache_key(endpoint, model)
    cached_variant = _CUSTOM_VARIANT_CACHE.get(variant_cache_key)
    variants = _reorder_variants_for_cache_hit(variants, variant_cache_key)

    call_client = (
        client.with_options(timeout=timeout) if timeout is not None else client
    )
    last_body = ""
    for variant_label, kwargs in variants:
        logger.debug("Custom Chat one-shot request (%s)", variant_label)
        try:
            response = call_client.chat.completions.create(
                model=model,
                messages=messages,
                **kwargs,
            )
            content = response.choices[0].message.content or ""
            # Only warn when we landed on a non-richest variant that
            # wasn't the cached pick — the cache-hit path should be
            # silent (otherwise every call spams the same warning).
            is_richest = variant_label == "json_object+temperature"
            is_cache_hit = cached_variant == variant_label
            if not is_richest and not is_cache_hit:
                logger.warning(
                    "Custom provider rejected richer payload; "
                    "succeeded with '%s' fallback (cached for this session)",
                    variant_label,
                )
            with _CACHE_LOCK:
                if _CUSTOM_VARIANT_CACHE.get(variant_cache_key) != variant_label:
                    _CUSTOM_VARIANT_CACHE[variant_cache_key] = variant_label
                    _persist_caches()
            return content
        except BadRequestError as exc:
            last_body = _openai_error_body(exc)
            # Vision-not-supported is a model-capability error — no
            # variant of the payload will fix it.  Surface it immediately
            # so callers (vision extract, image translation, screen
            # translate) get the actionable VISION_NOT_SUPPORTED tag
            # instead of a generic INVALID_REQUEST after three useless
            # round-trips.
            body_lower = last_body.lower()
            if any(ind in body_lower for ind in VISION_UNSUPPORTED_INDICATORS):
                logger.error(
                    "Custom Chat vision-not-supported: %s",
                    last_body,
                )
                raise ValueError("VISION_NOT_SUPPORTED") from exc
            logger.warning(
                "Custom Chat 400 with '%s' payload; trying next variant. Body: %s",
                variant_label,
                last_body,
            )

    logger.error(
        "Custom Chat one-shot exhausted all payload fallbacks; provider "
        "still returned 400. Last body: %s",
        last_body,
    )
    raise ValueError("INVALID_REQUEST")


def _stream_custom_chat_with_fallback(
    client: Any,  # noqa: ANN401
    *,
    model: str,
    endpoint: str,
    messages: list[dict[str, Any]],
    timeout: float | None = None,
) -> Any:  # noqa: ANN401
    """Returns a streaming ``chat.completions.create(stream=True)`` iterator.

    Streaming sibling of :func:`_call_custom_chat_with_fallback`.  The
    400 happens at ``create()`` time — before any chunks yield — so
    we can try payload variants pre-stream.  Once a stream object is
    returned, the caller iterates it normally; chunks already yielded
    can't be rolled back.

    Streaming responses are plain text, so the rich variant
    (``response_format: json_object``) is dropped — only two variants
    apply:

    1. ``temperature_only`` — original payload (what the existing code
       sends).
    2. ``minimal`` — drops ``temperature`` for o1/o3/gpt-5.x reasoning
       models.

    **Reads but does not write** to ``_CUSTOM_VARIANT_CACHE``.  If the
    non-streaming chain already discovered that ``(endpoint, model)``
    needs ``minimal`` (or ``no_system_role``, which implies the
    provider also rejects the rich payload), skip variant 1 and go
    straight to ``minimal``.  Streaming doesn't write back because the
    cache labels reflect non-streaming payload shapes (with
    ``response_format``) that don't apply here — round-tripping a
    streaming-discovered label would corrupt non-streaming choices.

    Other (non-400) errors propagate so the caller's
    ``_handle_api_error`` wrapper maps them to the standard tag set.
    Raises ``ValueError("INVALID_REQUEST")`` when every variant 400s.
    """
    from openai import BadRequestError  # noqa: PLC0415

    # Decide variant order based on shared cache hint.  Labels like
    # ``minimal`` / ``no_system_role`` mean the provider rejected
    # ``temperature: 0.0``; skip the temperature variant for those.
    variants: list[tuple[str, dict[str, Any]]] = [
        ("temperature_only", {"temperature": LLM_TEMPERATURE}),
        ("minimal", {}),
    ]
    cache_hint = _CUSTOM_VARIANT_CACHE.get(_custom_cache_key(endpoint, model))
    if cache_hint in ("minimal", "no_system_role"):
        # Provider rejects temperature; jump straight to the no-
        # temperature variant.  No need to fall back further — if
        # ``minimal`` 400s here too, the cached hint is lying and we
        # let the error surface.
        variants = [("minimal", {})]

    call_client = (
        client.with_options(timeout=timeout) if timeout is not None else client
    )
    last_body = ""
    for variant_label, kwargs in variants:
        logger.debug("Custom Stream request (%s)", variant_label)
        try:
            return call_client.chat.completions.create(
                model=model,
                messages=messages,
                stream=True,
                **kwargs,
            )
        except BadRequestError as exc:
            last_body = _openai_error_body(exc)
            logger.warning(
                "Custom Stream 400 with '%s' payload; trying next variant. Body: %s",
                variant_label,
                last_body,
            )

    logger.error(
        "Custom Stream exhausted all payload fallbacks; provider still "
        "returned 400. Last body: %s",
        last_body,
    )
    raise ValueError("INVALID_REQUEST")


def _translate_custom_chat(  # noqa: PLR0913
    texts: list[str],
    api_key: str,
    model: str,
    endpoint: str,
    system_prompt: str,
    input_json: str,
    *,
    defer_persist: bool = False,
) -> list[str]:
    """Sends a chat/completions request with progressive payload fallback.

    Variants tried in order:
    1. Rich payload (``response_format: json_object`` + ``temperature``).
    2. Without ``response_format`` — for providers that don't honour
       structured-output mode.
    3. Minimal — drops ``temperature`` too — for reasoning models like
       o1/o3 that only accept the default.
    4. Merges the system message into the user role — for deployments
       that reject ``role: system`` entirely.

    Each fallback is logged at WARNING level so pdf_processor's logger
    silencing doesn't hide the diagnostic.  Raises ``INVALID_REQUEST``
    when every variant returns HTTP 400 (a non-400 error short-circuits
    via ``_handle_api_error`` so quota / auth / connection problems
    propagate immediately).

    The first successful variant is cached in ``_CUSTOM_VARIANT_CACHE``
    keyed on ``(endpoint, model)`` so subsequent calls start from it
    instead of re-trying the doomed richer variants.  A cache miss on
    the cached variant (provider config changed) falls through to the
    remaining variants in original order; the cache is rewritten on the
    next success.

    *defer_persist* skips the disk write after the in-memory variant
    cache is updated.  The ambiguous-endpoint dispatcher in
    ``_translate_custom`` sets it so the cold-start case (chat success
    → variant write → return → api-cache write → persist) does ONE
    disk write instead of two.  The lock is still acquired for the
    in-memory mutation; only the ``_persist_caches()`` call is
    deferred.
    """
    from openai import BadRequestError  # noqa: PLC0415

    client = _build_openai_client(api_key, endpoint)
    base_messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Input: {input_json}"},
    ]
    no_system_messages = [
        {"role": "user", "content": f"{system_prompt}\n\nInput: {input_json}"},
    ]
    variants: list[tuple[str, dict]] = [
        (
            "json_object+temperature",
            {
                "messages": base_messages,
                "temperature": LLM_TEMPERATURE,
                "response_format": {"type": "json_object"},
            },
        ),
        (
            "temperature_only",
            {"messages": base_messages, "temperature": LLM_TEMPERATURE},
        ),
        ("minimal", {"messages": base_messages}),
        ("no_system_role", {"messages": no_system_messages}),
    ]

    # Reorder so a previously-successful variant is tried first.  The
    # remaining variants stay in original order as fallbacks in case the
    # cache entry is stale (e.g. the model now accepts the richer payload
    # again, or the provider tightened its schema validation).
    variant_cache_key = _custom_cache_key(endpoint, model)
    cached_variant = _CUSTOM_VARIANT_CACHE.get(variant_cache_key)
    variants = _reorder_variants_for_cache_hit(variants, variant_cache_key)

    last_body = ""
    content_str: str | None = None

    for variant_label, kwargs in variants:
        logger.debug("Custom Chat request (%s)", variant_label)
        try:
            response = client.chat.completions.create(model=model, **kwargs)
            content_str = response.choices[0].message.content or ""
            # Cache the working variant so the next call to the same
            # (endpoint, model) skips the doomed-richer attempts.  Only
            # log the fallback warning when the FIRST variant in the
            # original order ("json_object+temperature") was bypassed —
            # otherwise the cache hit would spam a warning per call.
            is_richest = variant_label == "json_object+temperature"
            is_cache_hit = cached_variant == variant_label
            if not is_richest and not is_cache_hit:
                logger.warning(
                    "Custom provider rejected richer payload; "
                    "succeeded with '%s' fallback (cached for this session)",
                    variant_label,
                )
            with _CACHE_LOCK:
                if _CUSTOM_VARIANT_CACHE.get(variant_cache_key) != variant_label:
                    _CUSTOM_VARIANT_CACHE[variant_cache_key] = variant_label
                    if not defer_persist:
                        _persist_caches()
            break
        except BadRequestError as exc:
            last_body = _openai_error_body(exc)
            logger.warning(
                "Custom Chat 400 with '%s' payload; trying next variant. Body: %s",
                variant_label,
                last_body,
            )
        except Exception as exc:
            _handle_api_error(exc, "Custom", "Chat")

    if content_str is None:
        logger.error(
            "Custom Chat exhausted all payload fallbacks; provider still "
            "returned 400. Last body: %s. "
            "If this model only supports the Responses API (e.g. Azure "
            "GPT-5.x reasoning deployments), change the endpoint to end "
            "in /responses or use a bare base URL like /v1.",
            last_body,
        )
        raise ValueError("INVALID_REQUEST")

    try:
        return _parse_translation_results(content_str, texts)
    except (json.JSONDecodeError, KeyError, IndexError) as exc:
        _handle_api_error(exc, "Custom", "Chat")


def _translate_custom_responses(  # noqa: PLR0913
    texts: list[str],
    api_key: str,
    model: str,
    endpoint: str,
    system_prompt: str,
    input_json: str,
) -> list[str]:
    """Sends a Responses-API request to the same Custom endpoint.

    Required for Azure GPT-5.x reasoning deployments and any other
    model where ``capabilities.chat_completion`` is False.  Body shape
    differs from chat/completions: the system prompt goes in the
    ``instructions`` field and the user message in ``input``.  Uses
    the SDK's ``client.responses.create`` and reads ``output_text``,
    falling back to walking ``output[*]`` if the SDK didn't synthesise
    the convenience field (older / preview shapes).
    """
    client = _build_openai_client(api_key, endpoint)
    logger.debug("Custom Responses request (model=%s)", model)
    try:
        # Use the reasoning-friendly timeout for Responses-API calls
        # via the SDK's per-call ``with_options`` chaining — the client
        # itself was built with the standard text timeout, but
        # Responses-only models (o1, o3, gpt-5.x-pro, …) routinely
        # take minutes to respond because the full reasoning trace
        # happens server-side before the final answer streams back.
        response = client.with_options(
            timeout=LLM_REASONING_TIMEOUT,
        ).responses.create(
            model=model,
            instructions=system_prompt,
            input=f"Input: {input_json}",
        )
    except Exception as exc:
        _handle_api_error(exc, "Custom", "Responses")

    try:
        # SDK's convenience accessor: concatenated text across message items.
        content_str = response.output_text or ""
        if not content_str:
            # Walk the structured output as a fallback for unusual shapes.
            for item in response.output or []:
                if getattr(item, "type", None) != "message":
                    continue
                for content in getattr(item, "content", []) or []:
                    text = getattr(content, "text", None)
                    if text:
                        content_str = text
                        break
                if content_str:
                    break
        if not content_str:
            raise KeyError("no output_text found in Responses payload")
        return _parse_translation_results(content_str, texts)
    except (json.JSONDecodeError, KeyError, IndexError, AttributeError) as exc:
        _handle_api_error(exc, "Custom", "Responses")


@retry_api_call()
def _translate_custom(  # noqa: PLR0913
    texts: list[str],
    target_lang: str,
    source_lang: str,
    glossary_entries: list[tuple[int, str, str]] | None = None,
    content_type: str = CONTENT_PLAIN_TEXT,
    model: str = "",
    *,
    context: list[str] | None = None,
) -> list[str]:
    """Translates text via an OpenAI-compatible custom endpoint.

    Dispatches to ``chat/completions`` first; if that returns
    ``INVALID_REQUEST`` after exhausting payload fallbacks, retries on
    the ``responses`` endpoint (required by Azure GPT-5.x reasoning
    models and any model whose ``capabilities.chat_completion`` is
    False).  The successful API choice is cached in
    ``_CUSTOM_API_CACHE`` per ``(endpoint, model)`` so subsequent calls
    skip the doomed chat attempt entirely.

    *context* (when provided) is woven into the system prompt as
    reference-only prior sentences — used by Live Translation for
    pronoun / topic continuity.
    """
    api_key, model, endpoint = _resolve_custom_config(model)
    if not endpoint or not model:
        raise ValueError("AUTH_ERROR:Custom")

    input_data = [{"id": i, "text": t} for i, t in enumerate(texts)]
    compressed_glossary = _compress_glossary(glossary_entries, texts)
    system_prompt = _build_translation_prompt(
        content_type,
        source_lang,
        target_lang,
        compressed_glossary,
        context,
    )
    input_json = json.dumps(input_data, ensure_ascii=False)

    # Honour an explicit endpoint path: ``/chat/completions`` or
    # ``/responses`` means "I know what API this model wants" — go
    # straight there without probing the other one.  A bare base URL
    # (no leaf path) opts in to the chat→responses auto-fallback.
    explicit_api, _ = _classify_custom_endpoint(endpoint)
    if explicit_api == "responses":
        return _translate_custom_responses(
            texts,
            api_key,
            model,
            endpoint,
            system_prompt,
            input_json,
        )
    if explicit_api == "chat":
        return _translate_custom_chat(
            texts,
            api_key,
            model,
            endpoint,
            system_prompt,
            input_json,
        )

    # Ambiguous endpoint — use the per-session cache to skip the wrong
    # API after the first probe.  Canonical key collapses cosmetic URL
    # variations (trailing slash, scheme, /chat/completions vs
    # /responses leaf) so the same logical endpoint hits one entry.
    cache_key = _custom_cache_key(endpoint, model)
    cached_api = _CUSTOM_API_CACHE.get(cache_key)

    if cached_api == "responses":
        return _translate_custom_responses(
            texts,
            api_key,
            model,
            endpoint,
            system_prompt,
            input_json,
        )

    # Snapshot the variant cache *before* invoking the chat helper so
    # we can detect whether the deferred chat mutation actually changed
    # state.  Without this we'd either over-persist (every call, even
    # cache hits) or under-persist (chat mutated but we miss it because
    # the api-cache value was already "chat").
    with _CACHE_LOCK:
        variant_before = _CUSTOM_VARIANT_CACHE.get(cache_key)

    try:
        # ``defer_persist=True`` lets the chat helper update the variant
        # cache in-memory without its own disk write; the post-call
        # block below does a single ``_persist_caches()`` covering both
        # the variant write (if any) and the api-cache write (if any).
        # Saves a round-trip on every cold start; cache-hit calls write
        # zero times.
        result = _translate_custom_chat(
            texts,
            api_key,
            model,
            endpoint,
            system_prompt,
            input_json,
            defer_persist=True,
        )
        with _CACHE_LOCK:
            api_changed = _CUSTOM_API_CACHE.get(cache_key) != "chat"
            if api_changed:
                _CUSTOM_API_CACHE[cache_key] = "chat"
            variant_changed = _CUSTOM_VARIANT_CACHE.get(cache_key) != variant_before
            if api_changed or variant_changed:
                _persist_caches()
        return result
    except ValueError as chat_err:
        # Only fall back when the failure looks like the wrong endpoint
        # for this model (every payload variant rejected).  Genuine
        # quota / auth / connection errors propagate immediately.
        if str(chat_err) != "INVALID_REQUEST":
            raise
        logger.warning(
            "Custom Chat exhausted for model %r; trying Responses API",
            model,
        )
        try:
            result = _translate_custom_responses(
                texts,
                api_key,
                model,
                endpoint,
                system_prompt,
                input_json,
            )
        except ValueError as resp_err:
            # Both APIs failed.  Surface the more *actionable* error:
            # if Responses raised a transient / network failure
            # (TIMEOUT_ERROR, CONNECTION_ERROR, SERVICE_UNAVAILABLE_ERROR,
            # QUOTA_ERROR, AUTH_ERROR), the user's real problem is the
            # network / quota / credentials — not "the chat payload was
            # rejected" (a benign signal that the model just needs the
            # Responses API).  Fall back to the chat error only when
            # Responses also returned a generic INVALID_REQUEST or
            # similar non-diagnostic failure.  Match on the BASE tag
            # (strip the optional ``:Service`` suffix the engine
            # appends for AUTH_ERROR) so the suffixed variant
            # ``"AUTH_ERROR:Custom"`` still qualifies as informative.
            informative_resp_tags = {
                "TIMEOUT_ERROR",
                "CONNECTION_ERROR",
                "SERVICE_UNAVAILABLE_ERROR",
                "QUOTA_ERROR",
                "AUTH_ERROR",
                "MODEL_NOT_FOUND",
                "REQUEST_TOO_LARGE",
            }
            logger.error(
                "Custom Responses also failed for model %r: %s",
                model,
                resp_err,
            )
            if base_error_tag(str(resp_err)) in informative_resp_tags:
                raise resp_err from chat_err
            raise chat_err from resp_err
        with _CACHE_LOCK:
            if _CUSTOM_API_CACHE.get(cache_key) != "responses":
                _CUSTOM_API_CACHE[cache_key] = "responses"
                _persist_caches()
        logger.warning(
            "Custom provider for model %r is Responses-API only; "
            "future calls will skip chat/completions",
            model,
        )
        return result


# ── Streaming Translation ─────────────────────────────────────────────────


def _build_streaming_prompt(
    source_lang: str,
    target_lang: str,
    glossary_entries: list[tuple[int, str, str]] | None = None,
    context: list[str] | None = None,
) -> str:
    """Builds a plain-text translation prompt for streaming (no JSON).

    *context* (when provided) is a list of prior source-language
    sentences included as reference-only context for pronoun / topic
    continuity.  Used by Live Translation streaming.
    """
    lang_pair = _format_lang_pair(source_lang, target_lang)
    glossary = _format_glossary_block(glossary_entries)
    context_block = _format_context_block(context)
    quality = (
        " Preserve the original tone, style, and context."
        " Ensure the translation reads naturally to a native speaker."
    )
    output_fmt = " Return ONLY the translated text. No explanations or markup."
    return (
        f"You are a professional translator."
        f" {lang_pair}{quality}{glossary}{context_block}{output_fmt}"
    )


def stream_translate_text(  # noqa: PLR0913
    text: str,
    target_lang: str,
    source_lang: str = "",
    glossary_entries: list[tuple[int, str, str]] | None = None,
    *,
    provider: str | None = None,
    model: str | None = None,
    context: list[str] | None = None,
) -> Generator[str, None, None]:
    """Streams translated text chunks from the configured LLM provider.

    *context* (when provided) is a list of prior source-language
    sentences fed to the LLM as reference-only context for pronoun /
    topic continuity (used by Live Translation streaming).

    Yields:
        str: Partial text chunks as they arrive from the API.
    """
    compressed_glossary = _compress_glossary(glossary_entries, [text])
    resolved_provider, resolved_model = _resolve_provider_model(provider, model)
    if resolved_provider == LLM_METHOD_GEMINI:
        yield from _strip_think_tags(
            _stream_gemini(
                text,
                target_lang,
                source_lang,
                compressed_glossary,
                resolved_model,
                context=context,
            )
        )
    elif resolved_provider == LLM_METHOD_CUSTOM:
        yield from _strip_think_tags(
            _stream_custom(
                text,
                target_lang,
                source_lang,
                compressed_glossary,
                resolved_model,
                context=context,
            )
        )


def _stream_gemini(  # noqa: PLR0913
    text: str,
    target_lang: str,
    source_lang: str,
    glossary_entries: list[tuple[int, str, str]] | None = None,
    model: str = "",
    *,
    context: list[str] | None = None,
) -> Generator[str, None, None]:
    """Streams translation from Gemini via the google-genai SDK iterator.

    The SDK's ``generate_content_stream`` returns chunks with a
    ``.text`` accessor that already filters out ``thought`` parts and
    handles SSE framing internally.
    """
    from google.genai import types  # noqa: PLC0415

    api_key = _config.load_setting(SETTING_LLM_GEMINI_API_KEY, "")
    if not model:
        model = DEFAULT_GEMINI_MODEL

    client = _build_gemini_client(api_key)
    prompt = _build_streaming_prompt(
        source_lang,
        target_lang,
        glossary_entries,
        context,
    )
    user_text = f"{prompt}\n\n{text}"

    try:
        for chunk in client.models.generate_content_stream(
            model=model,
            contents=user_text,
            config=types.GenerateContentConfig(
                temperature=LLM_TEMPERATURE,
                safety_settings=_gemini_safety_settings_for_sdk(),
            ),
        ):
            chunk_text = chunk.text
            if chunk_text:
                yield chunk_text
    except Exception as e:
        _handle_api_error(e, "Gemini", "Stream")


def _stream_custom(  # noqa: PLR0913
    text: str,
    target_lang: str,
    source_lang: str,
    glossary_entries: list[tuple[int, str, str]] | None = None,
    model: str = "",
    *,
    context: list[str] | None = None,
) -> Generator[str, None, None]:
    """Streams translation from an OpenAI-compatible endpoint via the SDK.

    Uses ``client.chat.completions.create(stream=True)`` and yields
    ``delta.content`` strings.  The SDK iterator handles SSE framing,
    keep-alives and the ``[DONE]`` sentinel internally.
    """
    api_key, model, endpoint = _resolve_custom_config(model)
    if not endpoint or not model:
        raise ValueError("AUTH_ERROR:Custom")

    prompt = _build_streaming_prompt(
        source_lang,
        target_lang,
        glossary_entries,
        context,
    )
    client = _build_openai_client(api_key, endpoint)
    try:
        stream = _stream_custom_chat_with_fallback(
            client,
            model=model,
            endpoint=endpoint,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": text},
            ],
        )
        for event in stream:
            if not event.choices:
                continue
            delta = event.choices[0].delta
            chunk = getattr(delta, "content", None)
            if chunk:
                yield chunk
    except Exception as e:
        _handle_api_error(e, "Custom", "Stream")


def translate_image_content(  # noqa: PLR0913
    image_path: str,
    ocr_results: list[Any],
    target_lang: str,
    source_lang: str = "",
    progress_callback: Callable[[int], None] | None = None,
    glossary_entries: list[tuple[int, str, str]] | None = None,
    *,
    provider: str | None = None,
    model: str | None = None,
) -> list[dict[str, Any]]:
    """Translates image content by dispatching to the configured LLM provider.

    Note: *progress_callback* is accepted for API compatibility but is
    not yet forwarded to the downstream provider functions.
    """
    if not ocr_results:
        return []
    resolved_provider, resolved_model = _resolve_provider_model(provider, model)
    fragments = [{"id": i, "text": res.text} for i, res in enumerate(ocr_results)]

    if resolved_provider == LLM_METHOD_GEMINI:
        return _translate_image_gemini(
            image_path,
            fragments,
            target_lang,
            source_lang,
            glossary_entries,
            resolved_model,
        )
    if resolved_provider == LLM_METHOD_CUSTOM:
        return _translate_image_custom(
            image_path,
            fragments,
            target_lang,
            source_lang,
            glossary_entries,
            resolved_model,
        )
    return []


_GEMINI_IMAGE_TRANSLATION_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "paragraphs": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "ids": {"type": "ARRAY", "items": {"type": "INTEGER"}},
                    "translated_html": {"type": "STRING"},
                    "color": {"type": "STRING"},
                    "alignment": {
                        "type": "STRING",
                        "enum": ["left", "center", "right"],
                    },
                },
                "required": ["ids", "translated_html", "color", "alignment"],
            },
        },
    },
    "required": ["paragraphs"],
}


@retry_api_call()
def _translate_image_gemini(  # noqa: PLR0913
    image_path: str,
    fragments: list[dict[str, Any]],
    target_lang: str,
    source_lang: str,
    glossary_entries: list[tuple[int, str, str]] | None = None,
    model: str = "",
) -> list[dict[str, Any]]:
    """Translates OCR text fragments on an image via the google-genai SDK.

    Args:
        image_path: Path to the source image file.
        fragments: OCR fragment dicts, each with at least an ``"text"`` key.
        target_lang: Target language name (e.g. "Vietnamese").
        source_lang: Source language name (e.g. "English").
        glossary_entries: Optional glossary for terminology enforcement.
        model: Gemini model name.

    Returns:
        List of paragraph dicts with ``ids``, ``translated_html``,
        ``color``, and ``alignment`` keys.
    """
    from google.genai import types  # noqa: PLC0415

    api_key = _config.load_setting(SETTING_LLM_GEMINI_API_KEY, "")
    if not model:
        model = DEFAULT_GEMINI_MODEL
    if not any(kw in model.lower() for kw in GEMINI_VISION_MODEL_KEYWORDS):
        model = DEFAULT_GEMINI_MODEL

    client = _build_gemini_client(api_key)

    image_bytes = Path(image_path).read_bytes()
    frag_texts = [f["text"] for f in fragments]
    compressed_glossary = _compress_glossary(glossary_entries, frag_texts)
    glossary_hint = _format_glossary_hint(compressed_glossary)
    prompt = _build_image_translation_prompt(target_lang, glossary_hint)
    frag_json = json.dumps(fragments, ensure_ascii=False)
    user_text = f"{prompt}\n\nInput Fragments: {frag_json}"

    logger.debug("Gemini Vision request (model=%s)", model)
    try:
        response = client.models.generate_content(
            model=model,
            contents=[
                types.Part.from_bytes(
                    data=image_bytes,
                    mime_type=_guess_image_mime(image_path),
                ),
                user_text,
            ],
            config=types.GenerateContentConfig(
                temperature=LLM_TEMPERATURE,
                response_mime_type="application/json",
                response_schema=_GEMINI_IMAGE_TRANSLATION_SCHEMA,
                safety_settings=_gemini_safety_settings_for_sdk(),
            ),
        )
        text = response.text or ""
        text = _strip_think_blocks(text)
        content_json = json.loads(text)
        return content_json.get("paragraphs", [])
    except Exception as e:
        _handle_api_error(e, "Gemini", "Vision")


@retry_api_call()
def _translate_image_custom(  # noqa: PLR0913
    image_path: str,
    fragments: list[dict[str, Any]],
    target_lang: str,
    source_lang: str,
    glossary_entries: list[tuple[int, str, str]] | None = None,
    model: str = "",
) -> list[dict[str, Any]]:
    """Translates image content using an OpenAI-compatible vision API.

    Args:
        image_path: Path to the source image file.
        fragments: OCR fragment dicts, each with at least a ``"text"`` key.
        target_lang: Target language name (e.g. "Vietnamese").
        source_lang: Source language name (e.g. "English").
        glossary_entries: Optional glossary for terminology enforcement.
        model: Custom model name.

    Returns:
        List of paragraph dicts with ``ids``, ``translated_html``,
        ``color``, and ``alignment`` keys.
    """
    api_key, model, endpoint = _resolve_custom_config(model)
    if not endpoint or not model:
        raise ValueError("AUTH_ERROR:Custom")

    image_data = base64.b64encode(Path(image_path).read_bytes()).decode("utf-8")

    mime_type = _guess_image_mime(image_path)
    frag_texts = [f["text"] for f in fragments]
    compressed_glossary = _compress_glossary(glossary_entries, frag_texts)
    glossary_hint = _format_glossary_hint(compressed_glossary)
    prompt = _build_image_translation_prompt(target_lang, glossary_hint)
    frag_json = json.dumps(fragments, ensure_ascii=False)
    user_text = f"{prompt}\n\nInput Fragments: {frag_json}"
    image_url = f"data:{mime_type};base64,{image_data}"

    client = _build_openai_client(api_key, endpoint)
    logger.debug("Custom Vision request (model=%s)", model)
    try:
        content_str = _call_custom_chat_with_fallback(
            client,
            model=model,
            endpoint=endpoint,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        {
                            "type": "image_url",
                            "image_url": {"url": image_url},
                        },
                    ],
                },
            ],
            timeout=LLM_VISION_TIMEOUT,
        )
        content_str = _strip_think_blocks(content_str)
        content_json = json.loads(content_str)
        return content_json.get("paragraphs", [])
    except Exception as e:
        _handle_api_error(e, "Custom", "Vision")


# ── Image Text Extraction (LLM Vision) ───────────────────────


# System prompt for LLM-based text extraction from images (vision API).
_EXTRACT_TEXT_PROMPT = (
    "You are a professional text extraction assistant."
    " Extract ALL visible text from this image exactly as it appears."
    " Preserve the original reading order (top to bottom, left to right)."
    " Separate distinct text blocks with newlines."
    " Do NOT translate — return the original text as-is."
    " Do NOT add commentary, labels, or descriptions."
    " If no text is visible, return an empty string."
    '\n\nReturn ONLY a JSON object: {"text": "<extracted text>"}'
)


@retry_api_call()
def _extract_text_gemini(image_path: str, model: str = "") -> str:
    """Extracts text from an image using the Gemini Vision API."""
    from google.genai import types  # noqa: PLC0415

    api_key = _config.load_setting(SETTING_LLM_GEMINI_API_KEY, "")
    if not model:
        model = DEFAULT_GEMINI_MODEL
    if not any(kw in model.lower() for kw in GEMINI_VISION_MODEL_KEYWORDS):
        model = DEFAULT_GEMINI_MODEL

    client = _build_gemini_client(api_key)
    image_bytes = Path(image_path).read_bytes()

    logger.debug("Gemini text extraction request for %s", image_path)
    try:
        response = client.models.generate_content(
            model=model,
            contents=[
                types.Part.from_bytes(
                    data=image_bytes,
                    mime_type=_guess_image_mime(image_path),
                ),
                _EXTRACT_TEXT_PROMPT,
            ],
            config=types.GenerateContentConfig(
                temperature=LLM_TEMPERATURE,
                response_mime_type="application/json",
                response_schema={
                    "type": "OBJECT",
                    "properties": {"text": {"type": "STRING"}},
                    "required": ["text"],
                },
                safety_settings=_gemini_safety_settings_for_sdk(),
            ),
        )
        text = response.text or ""
        text = _strip_think_blocks(text)
        return json.loads(text).get("text", "")
    except Exception as e:
        _handle_api_error(e, "Gemini", "Vision")


@retry_api_call()
def _extract_text_custom(image_path: str, model: str = "") -> str:
    """Extracts text from an image using an OpenAI-compatible vision API."""
    api_key, model, endpoint = _resolve_custom_config(model)
    if not endpoint or not model:
        raise ValueError("AUTH_ERROR:Custom")

    image_data = base64.b64encode(Path(image_path).read_bytes()).decode("utf-8")

    mime_type = _guess_image_mime(image_path)
    image_url = f"data:{mime_type};base64,{image_data}"

    client = _build_openai_client(api_key, endpoint)
    logger.debug("Custom text extraction request for %s", image_path)
    try:
        content_str = _call_custom_chat_with_fallback(
            client,
            model=model,
            endpoint=endpoint,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _EXTRACT_TEXT_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {"url": image_url},
                        },
                    ],
                },
            ],
            timeout=LLM_VISION_TIMEOUT,
        )
        content_str = _strip_think_blocks(content_str)
        return json.loads(content_str).get("text", "")
    except Exception as e:
        _handle_api_error(e, "Custom", "Vision")


def extract_image_text(
    image_path: str,
    *,
    provider: str | None = None,
    model: str | None = None,
) -> str:
    """Extracts text from an image using the configured LLM vision provider.

    Args:
        image_path: Path to the image file.
        provider: LLM provider name override.
        model: LLM model name override.

    Returns:
        Extracted text as a string.
    """
    resolved_provider, resolved_model = _resolve_provider_model(provider, model)
    if resolved_provider == LLM_METHOD_GEMINI:
        return _extract_text_gemini(image_path, resolved_model)
    if resolved_provider == LLM_METHOD_CUSTOM:
        return _extract_text_custom(image_path, resolved_model)
    return ""


# ── Batch Translation Helper ─────────────────────────────────


def translate_batch(  # noqa: PLR0913, PLR0912
    values: list[str],
    target_lang: str,
    src_lang: str,
    progress_callback: Callable[[int], None] | None = None,
    glossary_entries: list[tuple[int, str, str]] | None = None,
    cancel_check: Callable[[], bool] | None = None,
    checkpoint_dir: Path | None = None,
    content_type: str = CONTENT_DATA_VALUES,
    *,
    provider: str | None = None,
    model: str | None = None,
    context: list[str] | None = None,
) -> list[str] | None:
    """Translates a flat list of strings in batches.

    Applies file-level deduplication before batching so identical strings
    are translated only once — ensuring consistent translations regardless
    of which batch a duplicate falls into.

    Processes unique values in groups of ``TRANSLATION_BATCH_SIZE``.  On
    resume, previously-translated batches are loaded from the checkpoint
    and skipped.  If *checkpoint_dir* is ``None``, no caching is
    performed and every batch is sent to the LLM.

    Args:
        values: Strings to translate.
        target_lang: Target language name.
        src_lang: Source language name, or empty for auto-detect.
        progress_callback: Called with 0-100 percentage after each batch.
        glossary_entries: Optional glossary for the LLM.
        cancel_check: Returns ``True`` when the task has been cancelled.
        checkpoint_dir: Directory for saving/loading batch checkpoints.
        content_type: LLM content type hint (default ``CONTENT_DATA_VALUES``).
        provider: LLM provider name override.
        model: LLM model name override.
        context: Optional list of prior source-language sentences fed
            to the LLM as reference-only context (Live Translation
            uses this for pronoun / topic continuity).

    Returns:
        Translated strings, or ``None`` if the task was cancelled.
    """
    from src.core.checkpoint import (  # noqa: PLC0415
        load_batch_checkpoint,
        save_batch_progress,
    )

    if cancel_check and cancel_check():
        return None

    total = len(values)

    # --- File-level deduplication ---
    # Collapse identical strings so each is translated exactly once.
    # This guarantees consistent results across batches.
    unique_texts, dupe_map = _deduplicate_texts(values)

    unique_total = len(unique_texts)

    # Load previously-translated values from checkpoint
    existing: dict[int, str] = {}
    if checkpoint_dir:
        existing = load_batch_checkpoint(checkpoint_dir) or {}

    # If all unique values are cached, restore and return immediately
    if len(existing) >= unique_total:
        if progress_callback:
            progress_callback(100)
        unique_result = [existing.get(i, unique_texts[i]) for i in range(unique_total)]
        return _restore_duplicates(
            unique_result,
            unique_texts,
            dupe_map,
            values,
        )

    # Process unique values in batches
    translated_unique: list[str] = list(unique_texts)  # originals as fallback
    for start in range(0, unique_total, TRANSLATION_BATCH_SIZE):
        if cancel_check and cancel_check():
            return None

        end = min(start + TRANSLATION_BATCH_SIZE, unique_total)

        # Find items in this batch that are NOT cached
        uncached_indices = [i for i in range(start, end) if i not in existing]

        # Populate cached items immediately
        for i in range(start, end):
            if i in existing:
                translated_unique[i] = existing[i]

        if uncached_indices:
            uncached_values = [unique_texts[i] for i in uncached_indices]
            result = translate_text(
                uncached_values,
                target_lang,
                src_lang,
                glossary_entries=glossary_entries,
                content_type=content_type,
                provider=provider,
                model=model,
                context=context,
            )

            # Map results back to their indices in unique list
            for result_idx, original_idx in enumerate(uncached_indices):
                if result_idx < len(result):
                    translated_unique[original_idx] = result[result_idx]

            # Only save checkpoint when all uncached items received results.
            # A short LLM response would leave untranslated originals in
            # the slice; skipping the save lets those items retry on resume.
            if checkpoint_dir and len(result) == len(uncached_indices):
                save_batch_progress(
                    checkpoint_dir,
                    start,
                    translated_unique[start:end],
                    unique_total,
                )

        if progress_callback:
            progress_callback(int((end / total) * 100))

    # Expand unique translations back to all original positions
    return _restore_duplicates(
        translated_unique,
        unique_texts,
        dupe_map,
        values,
    )
