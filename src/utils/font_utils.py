"""Unified font family handling across all file types (image, office, PDF).

Implements a hybrid font selection strategy:
1. Determine the generic family (serif / sans-serif / monospace) from the
   source font name or PDF font flags.
2. Select a concrete font that supports the target language **and** belongs
   to the same generic family.
3. Fall back to the generic CSS family name when no concrete match is found.

This module is PySide6-free — it works headlessly for CLI / MCP / REST usage.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Generic family constants
# ---------------------------------------------------------------------------
FAMILY_SERIF = "serif"
FAMILY_SANS = "sans-serif"
FAMILY_MONO = "monospace"

# ---------------------------------------------------------------------------
# Script family constants (returned by detect_script)
# ---------------------------------------------------------------------------
SCRIPT_LATIN = "latin"
SCRIPT_CYRILLIC = "cyrillic"
SCRIPT_GREEK = "greek"
SCRIPT_ARABIC = "arabic"
SCRIPT_HEBREW = "hebrew"
SCRIPT_DEVANAGARI = "devanagari"
SCRIPT_BENGALI = "bengali"
SCRIPT_THAI = "thai"
SCRIPT_KHMER = "khmer"
SCRIPT_MONGOLIAN = "mongolian"
SCRIPT_EAST_ASIAN = "east_asian"

# ---------------------------------------------------------------------------
# Unicode range → script mapping.  Ranges that map to ``None`` are
# treated as Latin-compatible (combining marks, general punctuation, etc.).
# First match wins.
# ---------------------------------------------------------------------------
_SCRIPT_RANGES: tuple[tuple[int, int, str | None], ...] = (
    # Latin-compatible ranges (skip)
    (0x0300, 0x036F, None),  # Combining diacritical marks
    (0x1E00, 0x1EFF, None),  # Latin Extended Additional (Vietnamese, etc.)
    (0x2000, 0x2BFF, None),  # General punctuation / symbols
    (0xE000, 0xF8FF, None),  # Private-use area
    # Named script families
    (0x0370, 0x03FF, SCRIPT_GREEK),
    (0x1F00, 0x1FFF, SCRIPT_GREEK),  # Greek Extended
    (0x0400, 0x052F, SCRIPT_CYRILLIC),
    (0x0590, 0x05FF, SCRIPT_HEBREW),
    (0x0600, 0x06FF, SCRIPT_ARABIC),
    (0x0750, 0x077F, SCRIPT_ARABIC),  # Arabic Supplement
    (0x08A0, 0x08FF, SCRIPT_ARABIC),  # Arabic Extended-A
    (0xFB50, 0xFDFF, SCRIPT_ARABIC),  # Arabic Presentation Forms-A
    (0xFE70, 0xFEFF, SCRIPT_ARABIC),  # Arabic Presentation Forms-B
    (0x0900, 0x097F, SCRIPT_DEVANAGARI),
    (0x0980, 0x09FF, SCRIPT_BENGALI),
    (0x0E00, 0x0E7F, SCRIPT_THAI),
    (0x1780, 0x17FF, SCRIPT_KHMER),
    (0x1800, 0x18AF, SCRIPT_MONGOLIAN),
    # East Asian: CJK, Kana, Hangul
    (0x1100, 0x11FF, SCRIPT_EAST_ASIAN),  # Hangul Jamo
    (0x3000, 0x9FFF, SCRIPT_EAST_ASIAN),  # CJK Symbols + Kana + CJK Unified
    (0xAC00, 0xD7AF, SCRIPT_EAST_ASIAN),  # Hangul Syllables
    (0xF900, 0xFAFF, SCRIPT_EAST_ASIAN),  # CJK Compatibility Ideographs
    (0x20000, 0x2FA1F, SCRIPT_EAST_ASIAN),  # CJK Extension B–F
)


def detect_script(text: str) -> str:
    """Detects the dominant non-Latin script family from *text*.

    Scans characters until a non-Latin script is identified.  Returns
    ``"latin"`` for ASCII / Latin-only text (including extended Latin
    for Vietnamese, Turkish, etc.).

    Args:
        text: The text to analyse.

    Returns:
        A script family identifier (e.g. ``"latin"``, ``"cyrillic"``).
    """
    _latin_upper = 0x02FF
    for ch in text:
        cp = ord(ch)
        if cp <= _latin_upper:
            continue
        for lo, hi, family in _SCRIPT_RANGES:
            if lo <= cp <= hi:
                if family is not None:
                    return family
                break
    return SCRIPT_LATIN


# ---------------------------------------------------------------------------
# Generic-family classification from font name
# ---------------------------------------------------------------------------

# Well-known serif font name patterns
_SERIF_NAMES: set[str] = {
    "times",
    "times new roman",
    "georgia",
    "garamond",
    "palatino",
    "book antiqua",
    "cambria",
    "constantia",
    "didot",
    "minion",
    "caslon",
    "baskerville",
    "century",
    "bookman",
    "batang",
    "songti",
    "hiragino mincho",
    "noto serif",
    "dejavu serif",
    "liberation serif",
    "pt serif",
    "source serif",
    "droid serif",
    "lohit",
    # CJK serif
    "simsun",
    "nsimsun",
    "mingliu",
    "ms mincho",
    "yu mincho",
    "hiragino mincho pron",
    "songti sc",
    "songti tc",
    "noto serif cjk",
}

# Well-known monospace font name patterns
_MONO_NAMES: set[str] = {
    "courier",
    "courier new",
    "consolas",
    "menlo",
    "monaco",
    "andale mono",
    "lucida console",
    "dejavu sans mono",
    "liberation mono",
    "ubuntu mono",
    "fira code",
    "fira mono",
    "source code pro",
    "jetbrains mono",
    "cascadia code",
    "cascadia mono",
    "noto sans mono",
    "droid sans mono",
    "sf mono",
    "inconsolata",
    "hack",
    "iosevka",
}

# Regex for partial matching (e.g. "TimesNewRomanPSMT" → serif)
_SERIF_RE = re.compile(
    r"(?i)\b(?:times|georgia|garamond|palatino|cambria|constantia"
    r"|didot|baskerville|century|bookman|batang|simsun|songti"
    r"|mincho|mingliu|noto\s*serif|liberation\s*serif|pt\s*serif"
    r"|source\s*serif|droid\s*serif)\b",
)
_MONO_RE = re.compile(
    r"(?i)\b(?:courier|consolas|menlo|monaco|mono|code)\b",
)


def classify_generic_family(  # noqa: PLR0911
    *,
    font_name: str | None = None,
    font_flags: int | None = None,
) -> str:
    """Determines the generic CSS family from a source font.

    Uses two inputs (either or both may be provided):
    - ``font_name``: The font's family name (e.g. "Times New Roman").
    - ``font_flags``: PyMuPDF font flags (bit 3 = mono, bit 2 = serif).

    When both are provided, ``font_name`` takes precedence since it's
    more specific than PyMuPDF's coarse 2-bit classification.

    Args:
        font_name: The source font family name.
        font_flags: PyMuPDF span font flags.

    Returns:
        One of ``"serif"``, ``"sans-serif"``, or ``"monospace"``.
    """
    # 1. Try font name classification (more specific)
    if font_name:
        lower = font_name.lower().strip()
        if lower in _MONO_NAMES or _MONO_RE.search(lower):
            return FAMILY_MONO
        if lower in _SERIF_NAMES or _SERIF_RE.search(lower):
            return FAMILY_SERIF
        # Most UI / document fonts default to sans-serif when not
        # explicitly serif or monospace.
        # But if we also have font_flags, fall through to let flags decide.
        if font_flags is None:
            return FAMILY_SANS

    # 2. Fall back to PyMuPDF font flags
    if font_flags is not None:
        if font_flags & 8:
            return FAMILY_MONO
        if font_flags & 4:
            return FAMILY_SERIF
        return FAMILY_SANS

    # 3. Default
    return FAMILY_SANS


# ---------------------------------------------------------------------------
# Per-language, per-family font database
# ---------------------------------------------------------------------------

# Maps (script_or_language, generic_family) → list of concrete font names,
# ordered from most preferred to least.  The first installed font wins.
#
# "script_or_language" keys:
#   - Script-level keys (e.g. "east_asian") provide broad fallback.
#   - Language-level keys (e.g. "chinese (simplified)") override when the
#     target language is known.
#   - Special key "default" for Latin and any unrecognized language.
_FONT_DB: dict[str, dict[str, list[str]]] = {
    # -- East Asian: Chinese Simplified ------------------------------------
    "chinese (simplified)": {
        FAMILY_SANS: [
            "PingFang SC",
            "Heiti SC",
            "Microsoft YaHei",
            "SimHei",
            "Noto Sans CJK SC",
            "Droid Sans Fallback",
        ],
        FAMILY_SERIF: [
            "Songti SC",
            "SimSun",
            "NSimSun",
            "Noto Serif CJK SC",
        ],
        FAMILY_MONO: [
            "Noto Sans Mono CJK SC",
            "SimSun",
        ],
    },
    # -- East Asian: Chinese Traditional -----------------------------------
    "chinese (traditional)": {
        FAMILY_SANS: [
            "PingFang TC",
            "Heiti TC",
            "Microsoft JhengHei",
            "Noto Sans CJK TC",
            "Droid Sans Fallback",
        ],
        FAMILY_SERIF: [
            "Songti TC",
            "MingLiU",
            "Noto Serif CJK TC",
        ],
        FAMILY_MONO: [
            "Noto Sans Mono CJK TC",
            "MingLiU",
        ],
    },
    # -- East Asian: Japanese ----------------------------------------------
    "japanese": {
        FAMILY_SANS: [
            "Hiragino Sans",
            "Hiragino Kaku Gothic ProN",
            "Meiryo",
            "MS Gothic",
            "Noto Sans CJK JP",
            "TakaoPGothic",
        ],
        FAMILY_SERIF: [
            "Hiragino Mincho ProN",
            "MS Mincho",
            "Yu Mincho",
            "Noto Serif CJK JP",
        ],
        FAMILY_MONO: [
            "Noto Sans Mono CJK JP",
            "MS Gothic",
        ],
    },
    # -- East Asian: Korean ------------------------------------------------
    "korean": {
        FAMILY_SANS: [
            "Apple SD Gothic Neo",
            "Malgun Gothic",
            "Gulim",
            "Noto Sans CJK KR",
            "NanumGothic",
        ],
        FAMILY_SERIF: [
            "Batang",
            "NanumMyeongjo",
            "Noto Serif CJK KR",
        ],
        FAMILY_MONO: [
            "Noto Sans Mono CJK KR",
            "NanumGothicCoding",
        ],
    },
    # -- Devanagari --------------------------------------------------------
    "hindi": {
        FAMILY_SANS: [
            "Mangal",
            "Lohit Devanagari",
            "Noto Sans Devanagari",
        ],
        FAMILY_SERIF: [
            "Lohit Devanagari",
            "Noto Serif Devanagari",
        ],
        FAMILY_MONO: [
            "Noto Sans Devanagari",
        ],
    },
    "nepali": {
        FAMILY_SANS: [
            "Mangal",
            "Lohit Devanagari",
            "Noto Sans Devanagari",
        ],
        FAMILY_SERIF: [
            "Lohit Devanagari",
            "Noto Serif Devanagari",
        ],
        FAMILY_MONO: [
            "Noto Sans Devanagari",
        ],
    },
    # -- Arabic script -----------------------------------------------------
    "arabic": {
        FAMILY_SANS: [
            "Geeza Pro",
            "Traditional Arabic",
            "Simplified Arabic",
            "Noto Sans Arabic",
            "Noto Naskh Arabic",
        ],
        FAMILY_SERIF: [
            "Traditional Arabic",
            "Noto Naskh Arabic",
            "Noto Serif Arabic",
        ],
        FAMILY_MONO: [
            "Noto Sans Arabic",
        ],
    },
    "persian": {
        FAMILY_SANS: [
            "Geeza Pro",
            "Traditional Arabic",
            "B Nazanin",
            "Noto Sans Arabic",
            "Noto Naskh Arabic",
        ],
        FAMILY_SERIF: [
            "Traditional Arabic",
            "B Nazanin",
            "Noto Naskh Arabic",
            "Noto Serif Arabic",
        ],
        FAMILY_MONO: [
            "Noto Sans Arabic",
        ],
    },
    # -- Hebrew ------------------------------------------------------------
    "hebrew": {
        FAMILY_SANS: [
            "David",
            "Miriam",
            "Noto Sans Hebrew",
        ],
        FAMILY_SERIF: [
            "David",
            "Noto Serif Hebrew",
        ],
        FAMILY_MONO: [
            "Noto Sans Hebrew",
        ],
    },
    # -- Bengali -----------------------------------------------------------
    "bengali": {
        FAMILY_SANS: [
            "Vrinda",
            "Lohit Bengali",
            "Noto Sans Bengali",
        ],
        FAMILY_SERIF: [
            "Lohit Bengali",
            "Noto Serif Bengali",
        ],
        FAMILY_MONO: [
            "Noto Sans Bengali",
        ],
    },
    # -- Thai --------------------------------------------------------------
    "thai": {
        FAMILY_SANS: [
            "Thonburi",
            "Sukhumvit Set",
            "Leelawadee",
            "Noto Sans Thai",
        ],
        FAMILY_SERIF: [
            "Angsana New",
            "Noto Serif Thai",
        ],
        FAMILY_MONO: [
            "Noto Sans Thai",
        ],
    },
    # -- Khmer -------------------------------------------------------------
    "khmer": {
        FAMILY_SANS: [
            "Khmer OS",
            "Khmer OS System",
            "Noto Sans Khmer",
        ],
        FAMILY_SERIF: [
            "Noto Serif Khmer",
        ],
        FAMILY_MONO: [
            "Noto Sans Khmer",
        ],
    },
    # -- Cyrillic languages ------------------------------------------------
    "cyrillic": {
        FAMILY_SANS: ["Noto Sans", "DejaVu Sans"],
        FAMILY_SERIF: ["Noto Serif", "DejaVu Serif"],
        FAMILY_MONO: ["Noto Sans Mono", "DejaVu Sans Mono"],
    },
    # -- Greek -------------------------------------------------------------
    "greek": {
        FAMILY_SANS: ["Noto Sans", "DejaVu Sans"],
        FAMILY_SERIF: ["Noto Serif", "DejaVu Serif"],
        FAMILY_MONO: ["Noto Sans Mono", "DejaVu Sans Mono"],
    },
    # -- Latin with extended diacritics ------------------------------------
    "vietnamese": {
        FAMILY_SANS: ["Tahoma", "Noto Sans"],
        FAMILY_SERIF: ["Noto Serif", "DejaVu Serif"],
        FAMILY_MONO: ["Noto Sans Mono", "DejaVu Sans Mono"],
    },
    "turkish": {
        FAMILY_SANS: ["Noto Sans", "DejaVu Sans"],
        FAMILY_SERIF: ["Noto Serif", "DejaVu Serif"],
        FAMILY_MONO: ["Noto Sans Mono", "DejaVu Sans Mono"],
    },
    # -- Default (Latin / unknown) -----------------------------------------
    "default": {
        FAMILY_SANS: ["Noto Sans", "DejaVu Sans", "Liberation Sans"],
        FAMILY_SERIF: ["Noto Serif", "DejaVu Serif", "Liberation Serif"],
        FAMILY_MONO: [
            "Noto Sans Mono",
            "DejaVu Sans Mono",
            "Liberation Mono",
        ],
    },
}

# Language name → script key for Cyrillic / Greek languages that share
# the same font set.
_LANG_TO_SCRIPT: dict[str, str] = {
    "russian": "cyrillic",
    "ukrainian": "cyrillic",
    "belarusian": "cyrillic",
    "bulgarian": "cyrillic",
    "serbian": "cyrillic",
    "mongolian": "cyrillic",
    "greek": "greek",
}


def _resolve_font_key(target_lang: str) -> str:
    """Resolve the target language to a _FONT_DB key.

    Tries exact match, then ``_LANG_TO_SCRIPT`` mapping, then substring
    match against _FONT_DB keys, and finally ``"default"``.
    """
    lang = target_lang.lower()

    # Exact match
    if lang in _FONT_DB:
        return lang

    # Explicit language → script mapping
    if lang in _LANG_TO_SCRIPT:
        return _LANG_TO_SCRIPT[lang]

    # Substring match (e.g. "chinese" in "chinese (simplified)")
    for key in _FONT_DB:
        if key in lang or lang in key:
            return key

    return "default"


def get_font_for_language(
    target_lang: str,
    generic_family: str = FAMILY_SANS,
) -> str:
    """Selects the best concrete font for a target language and generic family.

    Returns the first candidate from ``_FONT_DB`` for the resolved
    language/script key.  Falls back to the generic CSS family name
    when no candidates exist.

    Args:
        target_lang: Target language name (e.g. "Japanese", "Vietnamese").
        generic_family: One of ``"serif"``, ``"sans-serif"``, ``"monospace"``.

    Returns:
        A concrete font family name or a generic CSS family name.
    """
    key = _resolve_font_key(target_lang)
    entry = _FONT_DB.get(key, _FONT_DB["default"])
    candidates = entry.get(generic_family, entry.get(FAMILY_SANS, []))

    if candidates:
        return candidates[0]

    return generic_family
