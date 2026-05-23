"""OCR-related constants for the AI Translate application."""

from __future__ import annotations

import logging

logger = logging.getLogger("ocr")

# OCR backend method identifiers
OCR_METHOD_GOOGLE_CLOUD = "Google Cloud OCR"
OCR_METHOD_TESSERACT = "TesseractOCR"
OCR_METHOD_EASYOCR = "EasyOCR"

OCR_METHODS = [
    OCR_METHOD_TESSERACT,
    OCR_METHOD_EASYOCR,
    OCR_METHOD_GOOGLE_CLOUD,
]


def resolve_ocr_method(label: str) -> str | None:
    """Resolves an OCR method label to its canonical identifier.

    Accepts the canonical form (e.g. "TesseractOCR") or a friendlier
    lowercase spelling (e.g. "tesseract", "google cloud"). Matching is
    case-insensitive and ignores whitespace / the "OCR" suffix.

    Args:
        label: User-provided OCR method string.

    Returns:
        The canonical identifier from :data:`OCR_METHODS`, or ``None`` when
        ``label`` is empty or does not match any known method.
    """
    if not label:
        return None
    target = label.lower().replace(" ", "").replace("ocr", "")
    for canonical in OCR_METHODS:
        if canonical.lower() == label.lower():
            return canonical
        normalized = canonical.lower().replace(" ", "").replace("ocr", "")
        if normalized == target:
            return canonical
    return None


# Layout Metrics
OCR_LINE_GAP_THRESHOLD_RATIO = 0.5  # Max gap ratio before new paragraph
OCR_DEFAULT_LINE_HEIGHT = 1.2  # Default line-height multiplier for rendered text
OCR_SINGLE_LINE_HEIGHT = 1.0  # Line-height multiplier for single-line blocks
OCR_MIN_LINE_HEIGHT = 0.8  # Minimum allowed line-height multiplier
OCR_MAX_LINE_HEIGHT = 3.0  # Maximum allowed line-height multiplier
OCR_EASYOCR_HEIGHT_MULTIPLIER = 1.2  # EasyOCR bbox height scale

# Maximum pixels a single-line text block may overflow its bounding box
# during font-size fitting. Overflow direction follows alignment:
#   Left  → right edge only,  Right → left edge only,
#   Center → split evenly on both sides.
OCR_SINGLE_LINE_TOLERANCE_PX = 3.0

# Merge thresholds for grouping OCR fragments into sentences
# Vertical: fragments need this much overlap (relative to shorter height)
# to be considered the same line. Higher = stricter.
OCR_VERTICAL_OVERLAP_RATIO = 0.6
# Horizontal: gap must be smaller than this ratio of line height to merge
# into the same sentence. Higher = more aggressive merging.
OCR_HORIZONTAL_GAP_RATIO = 1.2

# Tesseract-specific
TESSERACT_WORD_LEVEL = 5
TESSERACT_CONFIDENCE_SCALE = 100.0

# EasyOCR-specific
EASYOCR_DEFAULT_LANGUAGES = ["en"]

# Google Cloud Vision
GOOGLE_CLOUD_OCR_TIMEOUT = 30
# Cloud Vision documents TWO independent size limits for inline
# (base64-embedded) requests via ``images:annotate``:
#
# 1. **Raw image** capped at 20 MB (Cloud Vision quotas page).
# 2. **JSON request body** capped at 10 MB — and base64 encoding adds
#    ~33 % overhead, so a 7.5 MB raw file already produces a ~10 MB
#    request payload that hits limit #2 first.  Going up to the 20 MB
#    raw limit would only work via the GCS-URI input path (``image.
#    source``) which we don't implement.
#
# 7 MB pre-flight cap keeps us comfortably below the 10 MB JSON limit
# (7 × 1.34 ≈ 9.4 MB encoded) so users get our typed ``IMAGE_TOO_LARGE``
# sentinel with a clear "downscale first" message instead of the
# server-side HTTP 400 with the opaque "Request payload size exceeds
# the limit" body.
GOOGLE_CLOUD_OCR_MAX_BYTES = 7 * 1024 * 1024

# Engine Padding Defaults (remove px from bounds, add px for render)
OCR_PADDING_EASYOCR = (0, -2)  # EasyOCR: no removal, shrink render by 2px
OCR_PADDING_DEFAULT = (1, 1)  # Default: remove 1px from bounds, add 1px for render

# ---------------------------------------------------------------------------
# Language code mappings for OCR backends
# Maps app language label → (Tesseract code, EasyOCR code, Google Cloud hint)
# ---------------------------------------------------------------------------
_LANG_OCR_CODES: dict[str, tuple[str, str, str]] = {
    "Arabic": ("ara", "ar", "ar"),
    "Belarusian": ("bel", "be", "be"),
    "Bengali": ("ben", "bn", "bn"),
    "Bulgarian": ("bul", "bg", "bg"),
    "Chinese (Simplified)": ("chi_sim", "ch_sim", "zh"),
    "Chinese (Traditional)": ("chi_tra", "ch_tra", "zh-TW"),
    "Croatian": ("hrv", "hr", "hr"),
    "Czech": ("ces", "cs", "cs"),
    "Danish": ("dan", "da", "da"),
    "Dutch": ("nld", "nl", "nl"),
    "English (UK)": ("eng", "en", "en"),
    "English (US)": ("eng", "en", "en"),
    "Estonian": ("est", "et", "et"),
    "Finnish": ("fin", "fi", "fi"),
    "French": ("fra", "fr", "fr"),
    "German": ("deu", "de", "de"),
    "Greek": ("ell", "el", "el"),
    "Hebrew": ("heb", "he", "he"),
    "Hindi": ("hin", "hi", "hi"),
    "Hungarian": ("hun", "hu", "hu"),
    "Indonesian": ("ind", "id", "id"),
    "Italian": ("ita", "it", "it"),
    "Japanese": ("jpn", "ja", "ja"),
    "Khmer": ("khm", "km", "km"),
    "Korean": ("kor", "ko", "ko"),
    "Latvian": ("lav", "lv", "lv"),
    "Lithuanian": ("lit", "lt", "lt"),
    "Malay": ("msa", "ms", "ms"),
    "Mongolian": ("mon", "mn", "mn"),
    "Nepali": ("nep", "ne", "ne"),
    "Persian": ("fas", "fa", "fa"),
    "Polish": ("pol", "pl", "pl"),
    "Portuguese (Brazil)": ("por", "pt", "pt"),
    "Portuguese (Portugal)": ("por", "pt", "pt"),
    "Romanian": ("ron", "ro", "ro"),
    "Russian": ("rus", "ru", "ru"),
    "Serbian": ("srp", "rs", "sr"),
    "Slovak": ("slk", "sk", "sk"),
    "Slovenian": ("slv", "sl", "sl"),
    "Spanish": ("spa", "es", "es"),
    "Swedish": ("swe", "sv", "sv"),
    "Thai": ("tha", "th", "th"),
    "Turkish": ("tur", "tr", "tr"),
    "Ukrainian": ("ukr", "uk", "uk"),
    "Vietnamese": ("vie", "vi", "vi"),
}


def get_tesseract_lang(src_lang: str) -> str:
    """Returns the Tesseract language code for the given app language label.

    Falls back to ``"eng"`` for unknown or empty labels.

    Args:
        src_lang: App language label (e.g. ``"French"``).

    Returns:
        Tesseract language code (e.g. ``"fra"``).
    """
    if not src_lang:
        return "eng"
    entry = _LANG_OCR_CODES.get(src_lang)
    return entry[0] if entry else "eng"


def get_easyocr_langs(src_lang: str) -> list[str]:
    """Returns the EasyOCR language list for the given app language label.

    Always includes ``"en"`` so that mixed-language content is handled.
    Falls back to ``["en"]`` for unknown or empty labels.

    Args:
        src_lang: App language label (e.g. ``"Japanese"``).

    Returns:
        List of EasyOCR language codes (e.g. ``["ja", "en"]``).
    """
    if not src_lang:
        return ["en"]
    entry = _LANG_OCR_CODES.get(src_lang)
    if not entry or entry[1] == "en":
        return ["en"]
    return [entry[1], "en"]


def get_google_lang_hints(src_lang: str) -> list[str] | None:
    """Returns Google Cloud Vision language hints for the given label.

    Returns ``None`` for unknown or empty labels (auto-detect).

    Args:
        src_lang: App language label (e.g. ``"Arabic"``).

    Returns:
        Single-element list of BCP-47 hint codes, or ``None``.
    """
    if not src_lang:
        return None
    entry = _LANG_OCR_CODES.get(src_lang)
    return [entry[2]] if entry else None
