"""Language-related constants for the AI Translate application."""

# Each language entry: (locale_id, label, icon_filename, native_name)
# - locale_id: BCP-47 locale code matching the reference LOCALE_IDS
# - label: English name used in LLM prompts and DB storage
# - icon: flag PNG filename (without .png) in src/ui/assets/flags/
# - native_name: language name in its own script
LANGUAGES: list[tuple[str, str, str, str]] = [
    ("ar", "Arabic", "eg", "اَلْعَرَبِيَّة"),
    ("be", "Belarusian", "by", "беларуская"),
    ("bn", "Bengali", "bd", "বাংলা"),
    ("bg", "Bulgarian", "bg", "български"),
    ("zh-CN", "Chinese (Simplified)", "cn", "中文（简体）"),
    ("zh-TW", "Chinese (Traditional)", "tw", "中文（繁體）"),
    ("hr", "Croatian", "hr", "Hrvatski"),
    ("cs", "Czech", "cz", "Čeština"),
    ("da", "Danish", "dk", "Dansk"),
    ("nl", "Dutch", "nl", "Nederlands"),
    ("en-UK", "English (UK)", "uk", "English (UK)"),
    ("en-US", "English (US)", "us", "English (US)"),
    ("et", "Estonian", "ee", "Eesti"),
    ("fi", "Finnish", "fi", "Suomi"),
    ("fr", "French", "fr", "Français"),
    ("de", "German", "de", "Deutsch"),
    ("el", "Greek", "gr", "Ελληνικά"),
    ("he", "Hebrew", "il", "עברית"),
    ("hi", "Hindi", "in", "हिन्दी"),
    ("hu", "Hungarian", "hu", "Magyar"),
    ("id", "Indonesian", "id", "Bahasa Indonesia"),
    ("it", "Italian", "it", "Italiano"),
    ("ja", "Japanese", "jp", "日本語"),
    ("km", "Khmer", "kh", "ភាសាខ្មែរ"),
    ("ko", "Korean", "kr", "한국어"),
    ("lv", "Latvian", "lv", "Latviešu"),
    ("lt", "Lithuanian", "lt", "Lietuvių"),
    ("ms", "Malay", "my", "Bahasa Melayu"),
    ("mn", "Mongolian", "mn", "Монгол"),
    ("ne", "Nepali", "np", "नेपाली"),
    ("fa", "Persian", "ir", "فارسی"),
    ("pl", "Polish", "pl", "Polski"),
    ("pt-BR", "Portuguese (Brazil)", "br", "Português (Brasil)"),
    ("pt-PT", "Portuguese (Portugal)", "pt", "Português (Portugal)"),
    ("ro", "Romanian", "ro", "Română"),
    ("ru", "Russian", "ru", "Русский"),
    ("sr", "Serbian", "rs", "Cpпcки"),
    ("sk", "Slovak", "sk", "Slovenčina"),
    ("sl", "Slovenian", "si", "Slovenščina"),
    ("es", "Spanish", "es", "Español"),
    ("sv", "Swedish", "se", "Svenska"),
    ("th", "Thai", "th", "แบบไทย"),
    ("tr", "Turkish", "tr", "Türkçe"),
    ("uk", "Ukrainian", "ua", "Yкpaїнcькa"),
    ("vi", "Vietnamese", "vn", "Tiếng Việt"),
]

# Flat list of language labels used in LLM prompts and DB storage
AVAILABLE_LANGUAGES: list[str] = [lang[1] for lang in LANGUAGES]


def iter_languages_sorted_for_ui() -> list[tuple[str, str, str, str]]:
    """Returns ``LANGUAGES`` sorted by the *currently-localized* label.

    Picker populate sites should iterate this rather than ``LANGUAGES``
    directly so a Vietnamese user sees Vietnamese alphabetical order,
    a Japanese user sees gojūon order, etc. — matching how macOS /
    Windows present their localized language pickers.

    Sort key runs through ``normalize_for_search`` so accented forms
    sort with their base letter rather than after Z — Vietnamese
    "Tiếng Đan Mạch" lands between D and E, French "Élève" with E,
    German "Über" with U, etc.  Plain ``casefold`` would push every
    non-ASCII initial to the end of the list (the bug reported by the
    Vietnamese picker that prompted this change).  Ties fall back to
    the English label so the order is deterministic even when two
    locales translate to identical text.
    """
    from src.utils.text_utils import normalize_for_search  # noqa: PLC0415

    return sorted(
        LANGUAGES,
        key=lambda entry: (
            normalize_for_search(format_language_picker_label(entry[1], entry[3])),
            entry[1],
        ),
    )


def _language_i18n_key(english_label: str) -> str:
    """English label → ``language.<key>`` i18n suffix.

    Lower-cases and replaces non-alphanumeric runs with a single
    underscore, then strips trailing underscores.  Examples:

    - ``"Japanese"`` → ``"japanese"``
    - ``"Chinese (Simplified)"`` → ``"chinese_simplified"``
    - ``"Portuguese (Brazil)"`` → ``"portuguese_brazil"``
    - ``"English (UK)"`` → ``"english_uk"``

    Kept stable so the keys don't churn when display text is
    refined per locale; tests rely on this mapping.
    """
    out: list[str] = []
    for ch in english_label.lower():
        if ch.isalnum():
            out.append(ch)
        elif out and out[-1] != "_":
            out.append("_")
    return "".join(out).strip("_")


def format_language_picker_label(english_label: str, native_name: str) -> str:
    """Returns the display string for a language in UI pickers.

    Looks up the per-locale translation under ``language.<key>``
    (where ``<key>`` is :func:`_language_i18n_key`) and returns it
    when present.  Falls back to ``"<native> (<English>)"`` when the
    translation is genuinely missing — insurance against future
    drift if a new language is added without updating every locale.
    The double-fallback to plain English when ``native == english``
    stays in place to avoid the silly ``"English (UK) (English (UK))"``
    repeat.

    The DB and LLM prompts continue to use the bare English label;
    this helper only affects what the user sees in pickers.
    """
    # Lazy import to avoid pulling i18n into modules that just want
    # the AVAILABLE_LANGUAGES list.
    from src.constants.i18n import tr  # noqa: PLC0415

    key = f"language.{_language_i18n_key(english_label)}"
    translated = tr(key)
    # ``tr`` falls back to the key itself on miss — distinguishable.
    if translated and translated != key:
        return translated
    if native_name == english_label:
        return english_label
    return f"{native_name} ({english_label})"

# English label → native-name lookup, used by ``localized_language_label``
# so callers that hold only the English DB value (history tables, log
# lines, …) don't have to maintain their own LANGUAGES walk.
_NATIVE_BY_ENGLISH: dict[str, str] = {
    label: native for _locale, label, _icon, native in LANGUAGES
}


def localized_language_label(english_label: str) -> str:
    """Returns the user-facing display string for an English language label.

    Convenience wrapper over :func:`format_language_picker_label` for
    callers that only have the canonical English label (e.g. history
    tables that read it from the DB) — looks the native name up from
    :data:`LANGUAGES` and delegates.

    Empty input passes through unchanged so callers don't have to
    special-case the auto-detect placeholder.  Unknown labels (legacy
    DB entries with typos, removed languages, etc.) fall back to the
    raw English label rather than raise — the history table would
    rather render "Klingon" than blank cell.
    """
    if not english_label:
        return english_label
    native = _NATIVE_BY_ENGLISH.get(english_label, english_label)
    return format_language_picker_label(english_label, native)


# Reverse map: English label → locale code (e.g. "Vietnamese" → "vi")
_LABEL_TO_LOCALE: dict[str, str] = {label: locale for locale, label, _, _ in LANGUAGES}


def get_locale_code(label: str) -> str:
    """Returns the BCP-47 locale code for a language label.

    Falls back to the lowercased label if not found.

    Args:
        label: English language name (e.g. "Vietnamese").

    Returns:
        Locale code string (e.g. "vi").
    """
    return _LABEL_TO_LOCALE.get(label, label.lower())


# Right-to-left language labels.  Used by every output path that emits
# directional markup (PDF dir="rtl", DOCX <w:bidi/>, ODT writing-mode,
# RTF \rtlpar, EPUB page-progression-direction, ASS alignment mirror).
# Single source of truth so adding a new RTL language flips behaviour
# everywhere at once.
RTL_LANGUAGES: frozenset[str] = frozenset({"Arabic", "Hebrew", "Persian"})


def is_rtl_language(label: str) -> bool:
    """Returns True when *label* names a right-to-left language.

    Empty / unknown labels return False — the natural default for
    Latin-script languages and the safe default for the auto-detect
    case where the source language isn't known yet.
    """
    return label in RTL_LANGUAGES
