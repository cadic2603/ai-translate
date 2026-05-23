"""LLM-related constants for the AI Translate application."""

# LLM provider method identifiers
LLM_METHOD_GEMINI = "Gemini"
LLM_METHOD_CUSTOM = "Custom"

LLM_METHODS = [LLM_METHOD_GEMINI, LLM_METHOD_CUSTOM]

# Available Gemini model names and default selection
GEMINI_MODELS = [
    "gemini-3-flash-preview",
    "gemini-3.1-pro-preview",
    "gemini-3.1-flash-lite-preview",
    "gemma-4-31b-it",
    "gemma-4-26b-a4b-it",
]

DEFAULT_GEMINI_MODEL = "gemini-3-flash-preview"

# Number of strings sent to the LLM in a single API call for
# batch-oriented formats (JSON values, CSV cells, office cells).
# Used by translate_batch() for checkpoint granularity.
TRANSLATION_BATCH_SIZE = 30

# Max estimated tokens of text content per LLM API call.
# Conservative value safe for models with 16K+ context windows.
# Accounts for ~400 tokens of prompt/schema overhead and
# roughly equal output size (translation ≈ input length).
TOKEN_BUDGET = 4096

# Estimated token overhead per JSON item wrapper:
# {"id": N, "text": "..."} ≈ 10 tokens.
JSON_ITEM_OVERHEAD = 10

# Unicode code-point threshold for CJK-heavy scripts.
# Characters above this value (U+3000+: CJK Symbols, Hiragana,
# Katakana, CJK Unified Ideographs, Hangul, etc.) are counted as
# 1 token each instead of the Latin 1:4 ratio, giving more accurate
# token estimates for Asian languages.
CJK_CODEPOINT_THRESHOLD = 0x2FFF

# ── API & Networking ──────────────────────────────────────────

# Gemini API base URL (append "v1beta/models/{model}:generateContent")
GEMINI_API_BASE_URL = "https://generativelanguage.googleapis.com/"

# User-Agent sent with all LLM API requests (Gemini and Custom)
USER_AGENT = "Mozilla/5.0 (AITranslate Desktop App)"

# Default retry parameters for the @retry_api_call decorator
RETRY_MAX_ATTEMPTS = 3
RETRY_BASE_DELAY = 3.0

# Timeouts (seconds) for LLM API requests
LLM_TEXT_TIMEOUT = 90
LLM_VISION_TIMEOUT = 120
# Reasoning models (o1, o3, gpt-5.x-pro, DeepSeek-R1, Qwen3 reasoning,
# etc.) routinely take 2-10 minutes per request because they generate
# a long internal chain-of-thought before producing the answer.
# Used per-call via ``client.with_options(timeout=...)`` on every
# Responses-API request, since the Responses API is the canonical
# interface for these models (chat/completions either rejects them
# outright or strips the reasoning).  10 minutes covers the slowest
# observed responses on Azure GPT-5.x-pro deployments while still
# bounding wedged TCP connections.
LLM_REASONING_TIMEOUT = 600

# Generation temperature for all LLM requests (translation + extraction)
LLM_TEMPERATURE = 0.0

# Error tags that the retry decorator treats as transient (eligible for retry).
# ``TIMEOUT_ERROR`` is intentionally NOT here: a request that exceeded the
# (already generous) per-call timeout indicates the model is genuinely slow on
# this prompt — retrying with the same content typically times out again and
# silently burns 3×(timeout) seconds before surfacing the failure.  Surface the
# timeout immediately so the user can act (switch model, split the batch).
TRANSIENT_ERROR_TAGS: tuple[str, ...] = (
    "SERVICE_UNAVAILABLE_ERROR",
    "CONNECTION_ERROR",
)

# Substrings in HTTP error bodies that indicate vision/multimodal is unsupported
VISION_UNSUPPORTED_INDICATORS: tuple[str, ...] = (
    "does not support image",
    "image_url",
    "not support vision",
    "not a multimodal model",
    "not support multimodal",
)


# Model-name substrings that indicate Gemini vision-capable models
GEMINI_VISION_MODEL_KEYWORDS: tuple[str, ...] = ("flash", "pro", "gemma")

# Template for appending glossary entries to vision/image prompts
GLOSSARY_HINT_TEMPLATE = " Additionally, you MUST use this glossary: {entries}."

# ── Content Types for Translation Prompts ─────────────────────
# Format of source text, used in LLM prompt construction to guide
# the model on how to parse and preserve structure during translation.

CONTENT_PLAIN_TEXT = "plain_text"
CONTENT_MARKDOWN = "markdown"
CONTENT_HTML = "html"
CONTENT_XML = "xml"
CONTENT_RTF = "rtf"
CONTENT_EPUB = "epub"
CONTENT_DATA_VALUES = "data_values"
CONTENT_SUBTITLE = "subtitle"
CONTENT_LOCALIZATION = "localization"
CONTENT_PDF = "pdf"

# File extension → content_type mapping
_EXTENSION_TO_CONTENT_TYPE: dict[str, str] = {
    ".txt": CONTENT_PLAIN_TEXT,
    ".md": CONTENT_MARKDOWN,
    ".rst": CONTENT_MARKDOWN,
    ".html": CONTENT_HTML,
    ".htm": CONTENT_HTML,
    ".xhtml": CONTENT_HTML,
    ".xml": CONTENT_XML,
    ".rtf": CONTENT_RTF,
    ".json": CONTENT_DATA_VALUES,
    ".csv": CONTENT_DATA_VALUES,
    ".srt": CONTENT_SUBTITLE,
    ".vtt": CONTENT_SUBTITLE,
    ".ass": CONTENT_SUBTITLE,
    ".ssa": CONTENT_SUBTITLE,
    ".po": CONTENT_LOCALIZATION,
    ".pot": CONTENT_LOCALIZATION,
    ".xliff": CONTENT_LOCALIZATION,
    ".xlf": CONTENT_LOCALIZATION,
    ".yaml": CONTENT_LOCALIZATION,
    ".yml": CONTENT_LOCALIZATION,
    ".properties": CONTENT_LOCALIZATION,
    ".strings": CONTENT_LOCALIZATION,
    ".pdf": CONTENT_PDF,
}

# Content types representing structural documents (as opposed to data values).
DOCUMENT_CONTENT_TYPES: set[str] = {
    CONTENT_PLAIN_TEXT,
    CONTENT_MARKDOWN,
    CONTENT_HTML,
    CONTENT_XML,
    CONTENT_RTF,
    CONTENT_EPUB,
    CONTENT_PDF,
}


def get_content_type(extension: str) -> str:
    """Returns the content_type for a file extension.

    Unknown extensions fall back to ``CONTENT_PLAIN_TEXT``.

    Args:
        extension: Lowercase file extension (e.g. ".txt").

    Returns:
        str: The matching content type constant.
    """
    return _EXTENSION_TO_CONTENT_TYPE.get(
        extension.lower(),
        CONTENT_PLAIN_TEXT,
    )
