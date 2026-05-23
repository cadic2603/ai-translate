"""Centralized internationalization engine for UI strings.

Provides a tr() accessor, a language-change signal, and JSON-based
translation loading.  Mirrors the theme engine pattern in theme.py.
"""

import json
import logging
from pathlib import Path

from src.constants._signal import CallbackSignal

logger = logging.getLogger("i18n")

# ── Available UI Languages ──────────────────────────────────────
# Each entry: (locale_id, display_name, flag_icon_filename)
# locale_id matches the translation JSON filename in
# ``src/constants/translations/{locale_id}.json``.  The display_name
# is rendered as-is in the picker, in its own native script — that's
# the convention readers expect (Wikipedia, GitHub i18n, etc.).
# Adding a locale here only registers it; a stub JSON file (a copy
# of en-US.json so unknown keys fall back to readable English instead
# of raw key strings) must also exist or ``_load_translations`` will
# log a warning and leave the dict empty.
UI_LANGUAGES: list[tuple[str, str, str]] = [
    ("en-US", "English (US)", "us"),
    ("en-UK", "English (UK)", "uk"),
    ("fr", "Français", "fr"),
    ("es", "Español", "es"),
    ("de", "Deutsch", "de"),
    ("it", "Italiano", "it"),
    ("pl", "Polski", "pl"),
    ("pt-BR", "Português (Brasil)", "br"),
    ("pt-PT", "Português (Portugal)", "pt"),
    ("ru", "Русский", "ru"),
    # ``eg.png`` is the closest Arabic flag in the bundled icon set
    # (Egyptian flag) — Arabic doesn't have a single "flag" of its
    # own and Egypt is a common stand-in in app pickers.
    ("ar", "العربية", "eg"),
    ("hi", "हिन्दी", "in"),
    ("id", "Bahasa Indonesia", "id"),
    ("th", "ไทย", "th"),
    ("tr", "Türkçe", "tr"),
    ("vi", "Tiếng Việt", "vn"),
    ("zh-CN", "中文（简体）", "cn"),
    ("zh-TW", "中文（繁體）", "tw"),
    ("ja", "日本語", "jp"),
    ("ko", "한국어", "kr"),
]

# ── Translation Data ────────────────────────────────────────────

_TRANSLATIONS_DIR = Path(__file__).parent / "translations"

_current_language: str = "en-US"
_translations: dict[str, str] = {}

# ── Language Signal ─────────────────────────────────────────────

language_changed = CallbackSignal()


# ── Public API ──────────────────────────────────────────────────


def current_language() -> str:
    """Returns the code of the currently active UI language."""
    return _current_language


def set_language(code: str) -> None:
    """Switches the active UI language and emits the changed signal."""
    global _current_language  # noqa: PLW0603
    valid_codes = {c for c, *_ in UI_LANGUAGES}
    if code not in valid_codes:
        logger.warning("Unknown language '%s', ignoring.", code)
        return
    if code == _current_language:
        return
    _current_language = code
    _load_translations(code)
    language_changed.emit(code)


def _set_initial_language(code: str) -> None:
    """Sets the language at startup without emitting a signal."""
    global _current_language  # noqa: PLW0603
    valid_codes = {c for c, *_ in UI_LANGUAGES}
    if code in valid_codes:
        _current_language = code
    _load_translations(_current_language)


def tr(key: str, **kwargs: object) -> str:
    """Returns the translated string for *key* in the current language.

    Supports Python format syntax: ``tr("msg", count=5)`` replaces
    ``{count}`` in the translated template.  Falls back to *key* itself
    when no translation is found.
    """
    template = _translations.get(key, key)
    if kwargs:
        try:
            return template.format(**kwargs)
        except (KeyError, IndexError):
            logger.warning("Format error for key '%s': %s", key, kwargs)
            return template
    return template


# ── Internal Helpers ────────────────────────────────────────────


def _load_translations(code: str) -> None:
    """Reads the JSON translation file for *code* into module state."""
    global _translations  # noqa: PLW0603
    json_path = _TRANSLATIONS_DIR / f"{code}.json"
    if not json_path.exists():
        logger.warning("Translation file not found: %s", json_path)
        _translations = {}
        return
    try:
        with json_path.open(encoding="utf-8") as fh:
            _translations = json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Failed to load translations from %s: %s", json_path, exc)
        _translations = {}
