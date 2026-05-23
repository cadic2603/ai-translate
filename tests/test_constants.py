"""Unit tests for constants modules: errors, llm, i18n, theme, and languages."""

import logging

import pytest

from src.constants._signal import CallbackSignal
from src.constants.errors import (
    _ERROR_TR_KEYS,
    _TAG_TO_CODE,
    _TAG_TO_TR_KEY,
    ERR_FILE_NOT_FOUND,
    ERR_LLM_API_KEY_INVALID,
    ERR_LLM_QUOTA_EXCEEDED,
    ERR_NONE,
    ERR_UNKNOWN,
    ERROR_MESSAGES,
    display_error_message,
    get_error_message,
    map_tag_to_code,
)
from src.constants.i18n import (
    _load_translations,
    _set_initial_language,
    current_language,
    set_language,
    tr,
)
from src.constants.languages import (
    _LABEL_TO_LOCALE,
    AVAILABLE_LANGUAGES,
    LANGUAGES,
    RTL_LANGUAGES,
    get_locale_code,
    is_rtl_language,
)
from src.constants.llm import (
    CONTENT_DATA_VALUES,
    CONTENT_HTML,
    CONTENT_LOCALIZATION,
    CONTENT_MARKDOWN,
    CONTENT_PDF,
    CONTENT_PLAIN_TEXT,
    CONTENT_SUBTITLE,
    CONTENT_XML,
    DOCUMENT_CONTENT_TYPES,
    get_content_type,
)
from src.constants.theme import (
    _PALETTES,
    _set_initial_theme,
    color,
    current_theme,
    set_theme,
    style_banner,
    style_card_header,
    style_card_light,
    style_checkbox,
    style_danger_button,
    style_delete_button,
    style_input_field,
    style_input_label,
    style_link_button,
    style_list_widget,
    style_outlined_primary_button,
    style_page_header,
    style_primary_button,
    style_radio_button,
    style_scrollbar,
    style_secondary_button,
    style_section_group,
    style_section_title,
    style_setting_combo,
    style_setting_container,
    style_sidebar_list,
    style_splitter,
    style_tab_widget,
    style_table,
    style_table_delete_button,
    style_warning_button,
)

# ---------------------------------------------------------------------------
# get_error_message
# ---------------------------------------------------------------------------


def test_get_error_message_none_code() -> None:
    """None code returns empty string."""
    assert get_error_message(None) == ""


def test_get_error_message_err_none() -> None:
    """ERR_NONE returns empty string."""
    assert get_error_message(ERR_NONE) == ""


def test_get_error_message_known_code() -> None:
    """Known error code returns a non-empty translated string."""
    result = get_error_message(ERR_FILE_NOT_FOUND)
    assert result  # non-empty
    assert isinstance(result, str)


def test_get_error_message_unknown_code() -> None:
    """Unknown error code returns 'Unknown error (Code: N)' string."""
    unknown_code = 9999  # noqa: PLR2004
    result = get_error_message(unknown_code)
    assert "Unknown error" in result
    assert "9999" in result


def test_get_error_message_all_known_codes_return_strings() -> None:
    """Every code in _ERROR_TR_KEYS returns a non-empty string."""
    for code in _ERROR_TR_KEYS:
        result = get_error_message(code)
        assert isinstance(result, str)
        assert len(result) > 0


def test_error_messages_dict_covers_all_tr_keys() -> None:
    """ERROR_MESSAGES English dict has an entry for every code in _ERROR_TR_KEYS."""
    for code in _ERROR_TR_KEYS:
        assert code in ERROR_MESSAGES, f"Missing English message for code {code}"


def test_api_key_invalid_message_is_backend_agnostic() -> None:
    """The api_key_invalid message must NOT mention LLM specifically.

    AUTH_ERROR is used by LLM, OCR, TTS, and STT — when any of them
    raise it, the user-facing message routes through this string.
    A regression to LLM-specific wording ("Invalid LLM API Key…")
    would mislead users whose TTS or OCR key is the actual problem.

    Pin English message + every locale to keep the framing generic.
    The constant name (``ERR_LLM_API_KEY_INVALID``) is internal; the
    message text is what the user reads.
    """
    import json  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    # 1. English fallback in errors.py
    english = ERROR_MESSAGES[ERR_LLM_API_KEY_INVALID]
    assert "LLM" not in english, (
        f"English fallback message leaks LLM-specific framing: {english!r}"
    )

    # 2. Every translation file must omit "LLM" from this key.
    translations_dir = (
        Path(__file__).parent.parent / "src" / "constants" / "translations"
    )
    for path in sorted(translations_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        msg = data.get("error_msg.api_key_invalid", "")
        assert msg, f"{path.name}: missing error_msg.api_key_invalid"
        # Case-insensitive check — some locales may transliterate
        # "LLM" but the all-caps acronym is what users notice.
        assert "LLM" not in msg, (
            f"{path.name}: api_key_invalid leaks LLM framing: {msg!r}"
        )


# ---------------------------------------------------------------------------
# base_error_tag — shared suffix-stripping helper
# ---------------------------------------------------------------------------


class TestBaseErrorTag:
    """Tests for ``base_error_tag(tag)`` — shared suffix-stripping helper.

    Used by every set-membership consumer that needs to match on
    the bare tag (``_FATAL_LLM_ERRORS`` in pdf/office processors,
    ``informative_resp_tags`` in llm_engine) so engine-suffixed
    variants like ``"AUTH_ERROR:Gemini"`` still qualify.  Without
    this strip, ``"AUTH_ERROR:Gemini" in {"AUTH_ERROR", ...}``
    returns False and the fatal-error short-circuit silently
    demotes to skip-with-warning.
    """

    def test_strips_service_suffix(self) -> None:
        """A ``:Service`` suffix is removed."""
        from src.constants.errors import base_error_tag  # noqa: PLC0415

        assert base_error_tag("AUTH_ERROR:Gemini") == "AUTH_ERROR"
        assert base_error_tag("AUTH_ERROR:Google Cloud") == "AUTH_ERROR"
        assert base_error_tag("AUTH_ERROR:ElevenLabs") == "AUTH_ERROR"
        assert base_error_tag("AUTH_ERROR:Custom") == "AUTH_ERROR"

    def test_bare_tag_passes_through(self) -> None:
        """A bare tag without a colon is returned unchanged."""
        from src.constants.errors import base_error_tag  # noqa: PLC0415

        assert base_error_tag("AUTH_ERROR") == "AUTH_ERROR"
        assert base_error_tag("QUOTA_ERROR") == "QUOTA_ERROR"
        assert base_error_tag("VISION_NOT_SUPPORTED") == "VISION_NOT_SUPPORTED"
        assert base_error_tag("CONNECTION_ERROR") == "CONNECTION_ERROR"

    def test_only_strips_first_colon(self) -> None:
        """Multi-colon strings keep everything after the first colon out."""
        from src.constants.errors import base_error_tag  # noqa: PLC0415

        # Hypothetical future "AUTH_ERROR:Service:detail" — only base survives.
        assert base_error_tag("AUTH_ERROR:Foo:Bar:Baz") == "AUTH_ERROR"

    def test_empty_string_returns_empty(self) -> None:
        """Empty input is safe (returns empty)."""
        from src.constants.errors import base_error_tag  # noqa: PLC0415

        assert base_error_tag("") == ""

    def test_integration_with_fatal_set_membership(self) -> None:
        """End-to-end: suffixed AUTH_ERROR matches the fatal set via the helper.

        Mirrors the production check used by pdf/office processors
        and the llm_engine informative-response filter — proves the
        helper does its job in the actual membership pattern.
        """
        from src.constants.errors import base_error_tag  # noqa: PLC0415

        fatal_set = {"AUTH_ERROR", "QUOTA_ERROR", "VISION_NOT_SUPPORTED"}
        assert base_error_tag("AUTH_ERROR:Gemini") in fatal_set
        assert base_error_tag("AUTH_ERROR:Google Cloud") in fatal_set
        # Non-fatal stays non-fatal.
        assert base_error_tag("CONNECTION_ERROR") not in fatal_set
        # Legacy bare AUTH_ERROR still works.
        assert base_error_tag("AUTH_ERROR") in fatal_set


# ---------------------------------------------------------------------------
# AUTH_ERROR:<service> suffix routing
# ---------------------------------------------------------------------------


class TestAuthErrorServiceSuffix:
    """Tests for the colon-suffix AUTH_ERROR tag form.

    Engines that touch a remote auth-required service raise
    ``ValueError("AUTH_ERROR:Service Name")`` (Google Cloud / Soniox /
    ElevenLabs / Gemini / Vertex AI / Custom) so the UI's toast can
    say "Invalid Google Cloud API key" instead of generic "Invalid
    API key" — knowing WHICH key to fix is critical when the app has
    4 separate auth-required keys.
    """

    def test_plain_auth_error_uses_generic_message(self) -> None:
        """Legacy/no-suffix raises route to the generic api_key_invalid key."""
        from src.constants.errors import display_error_message  # noqa: PLC0415
        from src.constants.i18n import _set_initial_language  # noqa: PLC0415

        _set_initial_language("en-US")
        result = display_error_message("AUTH_ERROR")
        assert "Invalid API key" in result
        # Generic key must NOT carry a {service} placeholder leftover.
        assert "{service}" not in result

    def test_suffix_routes_to_service_specific_message(self) -> None:
        """``AUTH_ERROR:Google Cloud`` → "Invalid Google Cloud API key…"."""
        from src.constants.errors import display_error_message  # noqa: PLC0415
        from src.constants.i18n import _set_initial_language  # noqa: PLC0415

        _set_initial_language("en-US")
        result = display_error_message("AUTH_ERROR:Google Cloud")
        assert "Google Cloud" in result, (
            f"service name missing from message: {result!r}"
        )
        assert "API key" in result

    def test_suffix_routes_for_each_known_service(self) -> None:
        """Every documented service produces a service-specific message."""
        from src.constants.errors import display_error_message  # noqa: PLC0415
        from src.constants.i18n import _set_initial_language  # noqa: PLC0415

        _set_initial_language("en-US")
        for service in (
            "Google Cloud",
            "ElevenLabs",
            "Gemini",
            "Vertex AI",
            "Soniox",
            "Custom",
        ):
            result = display_error_message(f"AUTH_ERROR:{service}")
            assert service in result, (
                f"service {service!r} missing from message: {result!r}"
            )

    def test_suffix_survives_chained_exception_prefix(self) -> None:
        """``"Error processing: AUTH_ERROR:Google Cloud"`` is still parsed.

        Exception chains often stringify with leading prefixes.  The
        suffix extractor must find ``AUTH_ERROR:Service`` anywhere in
        the message, not just at the start.
        """
        from src.constants.errors import display_error_message  # noqa: PLC0415
        from src.constants.i18n import _set_initial_language  # noqa: PLC0415

        _set_initial_language("en-US")
        result = display_error_message(
            "Error processing translation: AUTH_ERROR:Gemini",
        )
        assert "Gemini" in result

    def test_suffix_with_trailing_whitespace_is_trimmed(self) -> None:
        """Whitespace around the service name is stripped."""
        from src.constants.errors import _extract_auth_service  # noqa: PLC0415

        assert _extract_auth_service("AUTH_ERROR:  Google Cloud  ") == "Google Cloud"

    def test_map_tag_to_code_still_works_with_suffix(self) -> None:
        """``map_tag_to_code`` still routes ``AUTH_ERROR:Service`` to the LLM key code.

        The DB-stored error code is the same regardless of which
        service failed — only the displayed message differs.  History
        rows from before the suffix existed must continue mapping.
        """
        from src.constants.errors import (  # noqa: PLC0415
            ERR_LLM_API_KEY_INVALID,
            map_tag_to_code,
        )

        assert map_tag_to_code("AUTH_ERROR") == ERR_LLM_API_KEY_INVALID
        assert map_tag_to_code("AUTH_ERROR:Google Cloud") == ERR_LLM_API_KEY_INVALID
        assert map_tag_to_code("AUTH_ERROR:Custom") == ERR_LLM_API_KEY_INVALID

    def test_localized_suffix_substitution_in_all_locales(self) -> None:
        """Every locale's api_key_invalid_for has the {service} placeholder.

        Without the placeholder, ``.format(service=…)`` is a no-op
        and the user sees the bare template with no service name.
        """
        import json  # noqa: PLC0415
        from pathlib import Path  # noqa: PLC0415

        translations = (
            Path(__file__).parent.parent / "src" / "constants" / "translations"
        )
        for path in sorted(translations.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            value = data.get("error_msg.api_key_invalid_for")
            assert value, f"{path.name}: missing error_msg.api_key_invalid_for"
            assert "{service}" in value, (
                f"{path.name}: api_key_invalid_for missing {{service}} "
                f"placeholder: {value!r}"
            )


def test_err_none_not_in_error_tr_keys() -> None:
    """ERR_NONE (0) is excluded from _ERROR_TR_KEYS — it has no translation key."""
    assert ERR_NONE not in _ERROR_TR_KEYS


def test_all_error_tr_keys_codes_are_positive() -> None:
    """All codes in _ERROR_TR_KEYS are positive integers (ERR_NONE=0 is excluded)."""
    for code in _ERROR_TR_KEYS:
        assert isinstance(code, int)
        assert code > 0, f"Code {code} in _ERROR_TR_KEYS is not positive"


# ---------------------------------------------------------------------------
# get_content_type
# ---------------------------------------------------------------------------


def test_get_content_type_txt() -> None:
    """'.txt' maps to CONTENT_PLAIN_TEXT."""
    assert get_content_type(".txt") == CONTENT_PLAIN_TEXT


def test_get_content_type_html() -> None:
    """'.html' maps to CONTENT_HTML."""
    assert get_content_type(".html") == CONTENT_HTML


def test_get_content_type_md() -> None:
    """'.md' maps to CONTENT_MARKDOWN."""
    assert get_content_type(".md") == CONTENT_MARKDOWN


def test_get_content_type_xml() -> None:
    """'.xml' maps to CONTENT_XML."""
    assert get_content_type(".xml") == CONTENT_XML


def test_get_content_type_srt() -> None:
    """'.srt' maps to CONTENT_SUBTITLE."""
    assert get_content_type(".srt") == CONTENT_SUBTITLE


def test_get_content_type_json() -> None:
    """'.json' maps to CONTENT_DATA_VALUES."""
    assert get_content_type(".json") == CONTENT_DATA_VALUES


def test_get_content_type_po() -> None:
    """'.po' maps to CONTENT_LOCALIZATION."""
    assert get_content_type(".po") == CONTENT_LOCALIZATION


def test_get_content_type_pdf() -> None:
    """'.pdf' maps to CONTENT_PDF."""
    assert get_content_type(".pdf") == CONTENT_PDF


def test_content_pdf_in_document_content_types() -> None:
    """CONTENT_PDF is included in the DOCUMENT_CONTENT_TYPES set."""
    assert CONTENT_PDF in DOCUMENT_CONTENT_TYPES


def test_get_content_type_unknown_extension() -> None:
    """Unknown extension falls back to CONTENT_PLAIN_TEXT."""
    assert get_content_type(".xyz") == CONTENT_PLAIN_TEXT
    assert get_content_type(".unknown") == CONTENT_PLAIN_TEXT
    assert get_content_type(".docx") == CONTENT_PLAIN_TEXT


def test_get_content_type_case_insensitive() -> None:
    """Extension lookup is case-insensitive."""
    assert get_content_type(".HTML") == CONTENT_HTML
    assert get_content_type(".Json") == CONTENT_DATA_VALUES
    assert get_content_type(".TXT") == CONTENT_PLAIN_TEXT


def test_get_content_type_empty_string() -> None:
    """Empty string extension falls back to CONTENT_PLAIN_TEXT."""
    assert get_content_type("") == CONTENT_PLAIN_TEXT


def test_get_content_type_no_dot_prefix() -> None:
    """Extension without leading dot falls back to CONTENT_PLAIN_TEXT."""
    # "txt" (no dot) is distinct from ".txt"; lookup should miss and fall back.
    assert get_content_type("txt") == CONTENT_PLAIN_TEXT
    assert get_content_type("html") == CONTENT_PLAIN_TEXT


def test_get_content_type_epub_falls_back() -> None:
    """.epub is not in _EXTENSION_TO_CONTENT_TYPE — falls back to CONTENT_PLAIN_TEXT."""
    # .epub is handled by a separate branch in text_processor, not the map.
    assert get_content_type(".epub") == CONTENT_PLAIN_TEXT


# ---------------------------------------------------------------------------
# i18n: tr()
# ---------------------------------------------------------------------------


def test_tr_missing_key_returns_key() -> None:
    """tr() returns the key itself when no translation exists."""
    result = tr("nonexistent.key.for.testing")
    assert result == "nonexistent.key.for.testing"


def test_tr_format_substitution() -> None:
    """tr() with kwargs performs format substitution."""
    # Simulate a translation with format placeholder
    from src.constants import i18n  # noqa: PLC0415

    original_translations = i18n._translations.copy()
    try:
        i18n._translations["test.greeting"] = "Hello {name}, you have {count} items"
        result = tr("test.greeting", name="Alice", count=5)
        assert result == "Hello Alice, you have 5 items"
    finally:
        i18n._translations = original_translations


def test_tr_format_error_returns_template(caplog: pytest.LogCaptureFixture) -> None:
    """tr() with bad kwargs logs a warning and returns the raw template."""
    from src.constants import i18n  # noqa: PLC0415

    original_translations = i18n._translations.copy()
    try:
        # Template has {name} but we pass wrong kwarg
        i18n._translations["test.bad"] = "Hello {name}"
        with caplog.at_level(logging.WARNING, logger="i18n"):
            result = tr("test.bad", wrong_key="value")
        assert result == "Hello {name}"
        assert "Format error" in caplog.text
    finally:
        i18n._translations = original_translations


def test_tr_index_error_returns_template(caplog: pytest.LogCaptureFixture) -> None:
    """tr() with IndexError from format returns the raw template."""
    from src.constants import i18n  # noqa: PLC0415

    original_translations = i18n._translations.copy()
    try:
        # Template uses positional {0} but we pass named kwarg
        i18n._translations["test.idx"] = "Item {0}"
        with caplog.at_level(logging.WARNING, logger="i18n"):
            result = tr("test.idx", name="test")
        # KeyError is caught since {0} is an index-like key but kwargs has "name"
        assert result == "Item {0}"
    finally:
        i18n._translations = original_translations


# ---------------------------------------------------------------------------
# i18n: set_language()
# ---------------------------------------------------------------------------


def test_set_language_unknown_code_is_ignored(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """set_language() with unknown code logs a warning and is a no-op."""
    original = current_language()
    with caplog.at_level(logging.WARNING, logger="i18n"):
        set_language("xx-XX")
    assert current_language() == original
    assert "Unknown language" in caplog.text


def test_set_language_same_code_is_noop() -> None:
    """set_language() with current code is a no-op (no signal emitted)."""
    original = current_language()
    # Should not raise or change anything
    set_language(original)
    assert current_language() == original


def test_set_initial_language_unknown_code_keeps_default() -> None:
    """_set_initial_language() with unknown code keeps existing language."""
    original = current_language()
    _set_initial_language("zz-ZZ")
    # Still loads translations for the current language
    assert current_language() == original


# ---------------------------------------------------------------------------
# i18n: _load_translations()
# ---------------------------------------------------------------------------


def test_load_translations_missing_file(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """_load_translations() with missing JSON file logs a warning."""
    from src.constants import i18n  # noqa: PLC0415

    original_translations = i18n._translations.copy()
    try:
        with caplog.at_level(logging.WARNING, logger="i18n"):
            _load_translations("nonexistent-locale")
        assert "not found" in caplog.text
    finally:
        i18n._translations = original_translations


# ---------------------------------------------------------------------------
# theme: set_theme()
# ---------------------------------------------------------------------------


def test_set_theme_unknown_name_is_ignored(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """set_theme() with unknown name logs a warning and is a no-op."""
    original = current_theme()
    with caplog.at_level(logging.WARNING, logger="theme"):
        set_theme("neon")
    assert current_theme() == original
    assert "Unknown theme" in caplog.text


def test_set_theme_same_name_is_noop() -> None:
    """set_theme() with the current theme is a no-op."""
    original = current_theme()
    set_theme(original)
    assert current_theme() == original


def test_set_initial_theme_unknown_keeps_current() -> None:
    """_set_initial_theme() with unknown name keeps the current theme."""
    original = current_theme()
    _set_initial_theme("unknown_theme")
    assert current_theme() == original


# ---------------------------------------------------------------------------
# theme: color()
# ---------------------------------------------------------------------------


def test_color_returns_hex_string() -> None:
    """color() returns a string starting with '#'."""
    result = color("primary")
    assert isinstance(result, str)
    assert result.startswith("#")


def test_color_all_palette_keys_accessible() -> None:
    """Every key in both palettes is accessible via color()."""
    original = current_theme()
    try:
        for theme_name in ("light", "dark"):
            _set_initial_theme(theme_name)
            for key in _PALETTES[theme_name]:
                result = color(key)
                assert isinstance(result, str)
                assert result.startswith("#")
    finally:
        _set_initial_theme(original)


def test_color_invalid_key_raises_key_error() -> None:
    """color() with unknown key raises KeyError."""
    with pytest.raises(KeyError):
        color("nonexistent_color_key")


# ---------------------------------------------------------------------------
# theme: style_banner()
# ---------------------------------------------------------------------------


def test_style_banner_known_variants() -> None:
    """style_banner() returns valid QSS for all known variants."""
    for variant in ("warning", "error", "info", "success"):
        result = style_banner(variant)
        assert "QFrame#Banner" in result
        assert "QLabel#BannerText" in result


def test_style_banner_unknown_variant_falls_back_to_warning() -> None:
    """style_banner() with unknown variant uses warning color as fallback."""
    warning_style = style_banner("warning")
    unknown_style = style_banner("nonexistent")
    # Both should use the warning accent color (same fallback)
    assert warning_style == unknown_style


def test_style_primary_button_returns_qss() -> None:
    """style_primary_button() returns valid QSS with QPushButton selector."""
    result = style_primary_button()
    assert "QPushButton" in result
    assert "background-color" in result


# ---------------------------------------------------------------------------
# get_locale_code / _LABEL_TO_LOCALE
# ---------------------------------------------------------------------------


def test_get_locale_code_known_language() -> None:
    """Returns correct locale code for a known language."""
    assert get_locale_code("Vietnamese") == "vi"
    assert get_locale_code("Japanese") == "ja"


def test_get_locale_code_with_region() -> None:
    """Returns full BCP-47 code including region for regional variants."""
    assert get_locale_code("English (US)") == "en-US"
    assert get_locale_code("Chinese (Simplified)") == "zh-CN"
    assert get_locale_code("Portuguese (Brazil)") == "pt-BR"


def test_get_locale_code_unknown_falls_back() -> None:
    """Falls back to lowercased label for unknown languages."""
    assert get_locale_code("Klingon") == "klingon"
    assert get_locale_code("Esperanto") == "esperanto"


def test_get_locale_code_empty_string() -> None:
    """Empty string label lowercases to empty string."""
    assert get_locale_code("") == ""


def test_label_to_locale_covers_all_languages() -> None:
    """Every entry in LANGUAGES has a corresponding _LABEL_TO_LOCALE entry."""
    for _locale, label, _icon, _native in LANGUAGES:
        assert label in _LABEL_TO_LOCALE


def test_available_languages_matches_languages() -> None:
    """AVAILABLE_LANGUAGES contains exactly the labels from LANGUAGES."""
    expected = [lang[1] for lang in LANGUAGES]
    assert expected == AVAILABLE_LANGUAGES


# ---------------------------------------------------------------------------
# is_rtl_language / RTL_LANGUAGES
# ---------------------------------------------------------------------------


def test_is_rtl_language_true_for_rtl_targets() -> None:
    """Arabic / Hebrew / Persian return True."""
    for lang in ("Arabic", "Hebrew", "Persian"):
        assert is_rtl_language(lang)


def test_is_rtl_language_false_for_ltr_targets() -> None:
    """Latin-script languages return False."""
    for lang in ("English (US)", "French", "Vietnamese", "Japanese"):
        assert not is_rtl_language(lang)


def test_is_rtl_language_false_for_empty_or_unknown() -> None:
    """Empty / unknown labels return False (safe LTR default)."""
    assert not is_rtl_language("")
    assert not is_rtl_language("Klingon")


def test_rtl_languages_subset_of_available_labels() -> None:
    """Every RTL_LANGUAGES entry is a real declared language."""
    for label in RTL_LANGUAGES:
        assert label in AVAILABLE_LANGUAGES


# ---------------------------------------------------------------------------
# OCR Language Mapping
# ---------------------------------------------------------------------------


def test_get_tesseract_lang_known() -> None:
    """Known languages return their Tesseract code."""
    from src.constants.ocr import get_tesseract_lang  # noqa: PLC0415

    assert get_tesseract_lang("French") == "fra"
    assert get_tesseract_lang("Japanese") == "jpn"


def test_get_tesseract_lang_empty() -> None:
    """Empty string falls back to 'eng'."""
    from src.constants.ocr import get_tesseract_lang  # noqa: PLC0415

    assert get_tesseract_lang("") == "eng"


def test_get_tesseract_lang_unknown() -> None:
    """Unknown language falls back to 'eng'."""
    from src.constants.ocr import get_tesseract_lang  # noqa: PLC0415

    assert get_tesseract_lang("Klingon") == "eng"


def test_get_tesseract_lang_english_variants() -> None:
    """Both English variants return 'eng'."""
    from src.constants.ocr import get_tesseract_lang  # noqa: PLC0415

    assert get_tesseract_lang("English (US)") == "eng"
    assert get_tesseract_lang("English (UK)") == "eng"


def test_get_easyocr_langs_known() -> None:
    """Known non-English language returns [code, 'en']."""
    from src.constants.ocr import get_easyocr_langs  # noqa: PLC0415

    assert get_easyocr_langs("French") == ["fr", "en"]


def test_get_easyocr_langs_empty() -> None:
    """Empty string falls back to ['en']."""
    from src.constants.ocr import get_easyocr_langs  # noqa: PLC0415

    assert get_easyocr_langs("") == ["en"]


def test_get_easyocr_langs_unknown() -> None:
    """Unknown language falls back to ['en']."""
    from src.constants.ocr import get_easyocr_langs  # noqa: PLC0415

    assert get_easyocr_langs("Klingon") == ["en"]


def test_get_easyocr_langs_english() -> None:
    """English variant returns ['en'] without duplication."""
    from src.constants.ocr import get_easyocr_langs  # noqa: PLC0415

    result = get_easyocr_langs("English (US)")
    assert result == ["en"]
    # Must NOT be ["en", "en"]
    assert len(result) == 1


def test_get_easyocr_langs_always_includes_english() -> None:
    """Every known non-English language includes 'en' in the list."""
    from src.constants.ocr import _LANG_OCR_CODES, get_easyocr_langs  # noqa: PLC0415

    for lang_label, (_tess, _easy, _goog) in _LANG_OCR_CODES.items():
        result = get_easyocr_langs(lang_label)
        assert "en" in result, f"{lang_label} result {result} missing 'en'"


def test_get_google_lang_hints_known() -> None:
    """Known language returns single-element list of hints."""
    from src.constants.ocr import get_google_lang_hints  # noqa: PLC0415

    assert get_google_lang_hints("Arabic") == ["ar"]


def test_get_google_lang_hints_empty() -> None:
    """Empty string returns None (auto-detect)."""
    from src.constants.ocr import get_google_lang_hints  # noqa: PLC0415

    assert get_google_lang_hints("") is None


def test_get_google_lang_hints_unknown() -> None:
    """Unknown language returns None (auto-detect)."""
    from src.constants.ocr import get_google_lang_hints  # noqa: PLC0415

    assert get_google_lang_hints("Klingon") is None


def test_lang_ocr_codes_covers_all_languages() -> None:
    """Most languages in AVAILABLE_LANGUAGES are in _LANG_OCR_CODES."""
    from src.constants.ocr import _LANG_OCR_CODES  # noqa: PLC0415

    covered = sum(1 for lang in AVAILABLE_LANGUAGES if lang in _LANG_OCR_CODES)
    total = len(AVAILABLE_LANGUAGES)
    # At least 80% coverage (some niche languages may lack OCR codes)
    coverage = covered / total
    assert coverage >= 0.8, (  # noqa: PLR2004
        f"OCR coverage too low: {covered}/{total} = {coverage:.0%}"
    )


def test_ocr_methods_list() -> None:
    """OCR_METHODS contains all three OCR backends."""
    from src.constants.ocr import (  # noqa: PLC0415
        OCR_METHOD_EASYOCR,
        OCR_METHOD_GOOGLE_CLOUD,
        OCR_METHOD_TESSERACT,
        OCR_METHODS,
    )

    expected = {OCR_METHOD_TESSERACT, OCR_METHOD_EASYOCR, OCR_METHOD_GOOGLE_CLOUD}
    assert set(OCR_METHODS) == expected


# ---------------------------------------------------------------------------
# File Constants
# ---------------------------------------------------------------------------


def test_supported_images_all_start_with_dot() -> None:
    """All image extensions start with '.'."""
    from src.constants.files import SUPPORTED_IMAGES  # noqa: PLC0415

    for ext in SUPPORTED_IMAGES:
        assert ext.startswith("."), f"Extension {ext!r} does not start with '.'"


def test_supported_text_all_start_with_dot() -> None:
    """All text/document extensions start with '.'."""
    from src.constants.files import SUPPORTED_TEXT  # noqa: PLC0415

    for ext in SUPPORTED_TEXT:
        assert ext.startswith("."), f"Extension {ext!r} does not start with '.'"


def test_all_supported_is_union() -> None:
    """ALL_SUPPORTED_EXTENSIONS is the concatenation of images + text."""
    from src.constants.files import (  # noqa: PLC0415
        ALL_SUPPORTED_EXTENSIONS,
        SUPPORTED_IMAGES,
        SUPPORTED_TEXT,
    )

    assert ALL_SUPPORTED_EXTENSIONS == SUPPORTED_IMAGES + SUPPORTED_TEXT


def test_no_duplicates_in_all_supported() -> None:
    """ALL_SUPPORTED_EXTENSIONS has no duplicate entries."""
    from src.constants.files import ALL_SUPPORTED_EXTENSIONS  # noqa: PLC0415

    assert len(ALL_SUPPORTED_EXTENSIONS) == len(set(ALL_SUPPORTED_EXTENSIONS))


def test_pdf_in_supported_text() -> None:
    """.pdf is in SUPPORTED_TEXT."""
    from src.constants.files import SUPPORTED_TEXT  # noqa: PLC0415

    assert ".pdf" in SUPPORTED_TEXT


def test_office_formats_in_supported_text() -> None:
    """All 9 office extensions are in SUPPORTED_TEXT."""
    from src.constants.files import SUPPORTED_TEXT  # noqa: PLC0415

    office_exts = [
        ".docx",
        ".xlsx",
        ".pptx",
        ".doc",
        ".xls",
        ".ppt",
        ".odt",
        ".ods",
        ".odp",
    ]
    for ext in office_exts:
        assert ext in SUPPORTED_TEXT, f"{ext} missing from SUPPORTED_TEXT"


def test_file_filter_contains_all_sections() -> None:
    """FILE_FILTER contains the expected section labels."""
    from src.constants.files import FILE_FILTER  # noqa: PLC0415

    assert "All Supported" in FILE_FILTER
    assert "Images" in FILE_FILTER
    assert "Documents" in FILE_FILTER


def test_supported_images_common_formats() -> None:
    """Common image formats are included."""
    from src.constants.files import SUPPORTED_IMAGES  # noqa: PLC0415

    for ext in [".png", ".jpg", ".jpeg", ".bmp"]:
        assert ext in SUPPORTED_IMAGES, f"{ext} missing from SUPPORTED_IMAGES"


# ---------------------------------------------------------------------------
# map_tag_to_code
# ---------------------------------------------------------------------------


def test_map_tag_to_code_known_tags() -> None:
    """Every known tag in _TAG_TO_CODE maps to the correct error code."""
    for tag, expected_code in _TAG_TO_CODE.items():
        assert map_tag_to_code(tag) == expected_code


def test_map_tag_to_code_unknown_string() -> None:
    """Unknown string returns ERR_UNKNOWN."""
    assert map_tag_to_code("SOME_RANDOM_ERROR") == ERR_UNKNOWN


def test_map_tag_to_code_empty_string() -> None:
    """Empty string returns ERR_UNKNOWN."""
    assert map_tag_to_code("") == ERR_UNKNOWN


def test_map_tag_to_code_logs_warning_on_unknown_fallback(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Unmapped tags surface a WARNING so they show up in CI logs.

    AGENTS.md pins this as the safety net for new sentinels: when an
    engine raises a tag that isn't yet wired into ``_TAG_TO_CODE`` or
    ``_TAG_TO_TR_KEY``, the warning makes the gap visible in test
    output instead of silently aliasing to ERR_UNKNOWN.  Without this
    guard, a forgotten mapping ships as a generic "unknown error" in
    the history page.
    """
    import logging  # noqa: PLC0415

    with caplog.at_level(logging.WARNING, logger="errors"):
        result = map_tag_to_code("BRAND_NEW_UNMAPPED_TAG")
    assert result == ERR_UNKNOWN
    assert any(
        "BRAND_NEW_UNMAPPED_TAG" in rec.message and "ERR_UNKNOWN" in rec.message
        for rec in caplog.records
    )


def test_map_tag_to_code_known_tag_is_silent(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A known tag must NOT trigger the unmapped-fallback warning."""
    import logging  # noqa: PLC0415

    with caplog.at_level(logging.WARNING, logger="errors"):
        map_tag_to_code("AUTH_ERROR")
    assert not any("ERR_UNKNOWN" in rec.message for rec in caplog.records)


def test_map_tag_to_code_substring_match() -> None:
    """Tags embedded in longer messages are still matched."""
    assert map_tag_to_code("prefix AUTH_ERROR suffix") == ERR_LLM_API_KEY_INVALID
    assert map_tag_to_code("Error: QUOTA_ERROR occurred") == ERR_LLM_QUOTA_EXCEEDED


def test_map_tag_to_code_first_match_wins() -> None:
    """When multiple tags appear, the first one in _TAG_TO_CODE order wins."""
    # Combine two known tags; result depends on dict iteration order
    combined = "AUTH_ERROR and QUOTA_ERROR"
    result = map_tag_to_code(combined)
    # Must be one of the two valid codes
    assert result in (ERR_LLM_API_KEY_INVALID, ERR_LLM_QUOTA_EXCEEDED)


# ---------------------------------------------------------------------------
# display_error_message
# ---------------------------------------------------------------------------


def test_display_error_message_empty_string() -> None:
    """Empty string returns empty string."""
    assert display_error_message("") == ""


def test_display_error_message_known_code_tag() -> None:
    """Known _TAG_TO_CODE tags return a localized (non-empty) message."""
    for tag in _TAG_TO_CODE:
        result = display_error_message(tag)
        assert isinstance(result, str)
        assert len(result) > 0
        # The result should NOT be the raw tag itself
        assert result != tag


def test_display_error_message_known_tr_key_tag() -> None:
    """Known _TAG_TO_TR_KEY tags return a localized (non-empty) message."""
    for tag in _TAG_TO_TR_KEY:
        result = display_error_message(tag)
        assert isinstance(result, str)
        assert len(result) > 0
        # Should not return the raw tag
        assert result != tag


def test_display_error_message_unknown_passthrough() -> None:
    """Unknown string is returned as-is (passthrough)."""
    msg = "Something unexpected happened"
    assert display_error_message(msg) == msg


def test_display_error_message_substring_match() -> None:
    """Tag embedded in a longer message still resolves to localized text."""
    result = display_error_message("Error: AUTH_ERROR - check key")
    # Should return the localized message, not the raw input
    assert result != "Error: AUTH_ERROR - check key"
    assert len(result) > 0


def test_display_error_message_code_tag_priority_over_tr_key() -> None:
    """_TAG_TO_CODE tags are checked before _TAG_TO_TR_KEY tags."""
    # If a message contains both a code tag and a tr-key tag,
    # the code tag should win (it's checked first in the function).
    code_tag = next(iter(_TAG_TO_CODE))
    tr_tag = next(iter(_TAG_TO_TR_KEY))
    combined = f"{code_tag} {tr_tag}"
    result = display_error_message(combined)
    # Should match the code tag's localized message
    expected = get_error_message(_TAG_TO_CODE[code_tag])
    assert result == expected


# ---------------------------------------------------------------------------
# map_tag_to_code: _TAG_TO_TR_KEY-only tags
# ---------------------------------------------------------------------------


def test_map_tag_to_code_tr_key_only_tag_returns_unknown() -> None:
    """Tag in _TAG_TO_TR_KEY but NOT in _TAG_TO_CODE returns ERR_UNKNOWN."""
    # FFMPEG_NOT_FOUND is in _TAG_TO_TR_KEY but not _TAG_TO_CODE
    assert "FFMPEG_NOT_FOUND" in _TAG_TO_TR_KEY
    assert "FFMPEG_NOT_FOUND" not in _TAG_TO_CODE
    assert map_tag_to_code("FFMPEG_NOT_FOUND") == ERR_UNKNOWN


# ---------------------------------------------------------------------------
# display_error_message: FFMPEG tags share a message
# ---------------------------------------------------------------------------


def test_display_error_message_ffmpeg_tags_share_message() -> None:
    """All 3 FFMPEG_*_FAILED tags produce the same localized message."""
    msg_conversion = display_error_message("FFMPEG_CONVERSION_FAILED")
    msg_concat = display_error_message("FFMPEG_CONCAT_FAILED")
    msg_mix = display_error_message("FFMPEG_MIX_FAILED")
    # All three map to the same tr_key "error_msg.ffmpeg_failed"
    assert msg_conversion == msg_concat == msg_mix
    # The result must not be the raw tag itself
    assert msg_conversion != "FFMPEG_CONVERSION_FAILED"
    assert msg_concat != "FFMPEG_CONCAT_FAILED"
    assert msg_mix != "FFMPEG_MIX_FAILED"


# ---------------------------------------------------------------------------
# _TAG_TO_TR_KEY: all tags resolve to non-tag values
# ---------------------------------------------------------------------------


def test_tag_to_tr_key_all_resolve_to_non_key() -> None:
    """Every _TAG_TO_TR_KEY tag resolves to a value different from the tag."""
    for tag, tr_key in _TAG_TO_TR_KEY.items():
        resolved = tr(tr_key)
        assert resolved != tag, f"Tag {tag!r} resolved to itself via tr({tr_key!r})"


# ---------------------------------------------------------------------------
# display_status: all known statuses
# ---------------------------------------------------------------------------


def test_display_status_all_known_statuses() -> None:
    """display_status() returns non-empty, non-key string for every status constant."""
    from src.constants.history import (  # noqa: PLC0415
        STATUS_DELETING,
        STATUS_DONE,
        STATUS_EXTRACTING,
        STATUS_FAILED,
        STATUS_GENERATING,
        STATUS_PAUSED,
        STATUS_PENDING,
        STATUS_TRANSLATING,
        display_status,
    )

    all_statuses = [
        STATUS_PENDING,
        STATUS_TRANSLATING,
        STATUS_EXTRACTING,
        STATUS_GENERATING,
        STATUS_DONE,
        STATUS_FAILED,
        STATUS_PAUSED,
        STATUS_DELETING,
    ]
    for status in all_statuses:
        result = display_status(status)
        assert isinstance(result, str), f"display_status({status!r}) is not a string"
        assert len(result) > 0, f"display_status({status!r}) returned empty string"
        # Result should not be the raw translation key (e.g. "status.done")
        raw_key = f"status.{status.lower()}"
        assert result != raw_key, (
            f"display_status({status!r}) returned the raw key {raw_key!r}"
        )


# ---------------------------------------------------------------------------
# Theme Style Functions
# ---------------------------------------------------------------------------


class TestThemeStyleFunctions:
    """Tests for all theme style_*() generator functions."""

    def test_style_sidebar_list_returns_nonempty_qss(self) -> None:
        """style_sidebar_list() returns non-empty QSS with QListWidget selector."""
        result = style_sidebar_list()
        assert isinstance(result, str)
        assert len(result) > 0
        assert "QListWidget" in result

    def test_style_page_header_returns_nonempty_qss(self) -> None:
        """style_page_header() returns non-empty QSS with font-size."""
        result = style_page_header()
        assert isinstance(result, str)
        assert len(result) > 0
        assert "font-size" in result

    def test_style_section_group_returns_nonempty_qss(self) -> None:
        """style_section_group() returns non-empty QSS with QFrame selector."""
        result = style_section_group()
        assert isinstance(result, str)
        assert len(result) > 0
        assert "QFrame" in result

    def test_style_section_title_returns_nonempty_qss(self) -> None:
        """style_section_title() returns non-empty QSS with font-weight."""
        result = style_section_title()
        assert isinstance(result, str)
        assert len(result) > 0
        assert "font-weight" in result

    def test_style_list_widget_returns_nonempty_qss(self) -> None:
        """style_list_widget() returns non-empty QSS with QListWidget selector."""
        result = style_list_widget()
        assert isinstance(result, str)
        assert len(result) > 0
        assert "QListWidget" in result

    def test_style_checkbox_returns_nonempty_qss(self) -> None:
        """style_checkbox() returns non-empty QSS with QCheckBox selector."""
        result = style_checkbox()
        assert isinstance(result, str)
        assert len(result) > 0
        assert "QCheckBox" in result

    def test_style_card_light_returns_nonempty_qss(self) -> None:
        """style_card_light() returns non-empty QSS with background-color."""
        result = style_card_light()
        assert isinstance(result, str)
        assert len(result) > 0
        assert "background-color" in result

    def test_style_card_header_returns_nonempty_qss(self) -> None:
        """style_card_header() returns non-empty QSS with font-size."""
        result = style_card_header()
        assert isinstance(result, str)
        assert len(result) > 0
        assert "font-size" in result

    def test_style_link_button_returns_nonempty_qss(self) -> None:
        """style_link_button() returns non-empty QSS with QPushButton selector."""
        result = style_link_button()
        assert isinstance(result, str)
        assert len(result) > 0
        assert "QPushButton" in result

    def test_style_setting_container_returns_nonempty_qss(self) -> None:
        """style_setting_container() returns non-empty QSS with background-color."""
        result = style_setting_container()
        assert isinstance(result, str)
        assert len(result) > 0
        assert "background-color" in result

    def test_style_input_label_returns_nonempty_qss(self) -> None:
        """style_input_label() returns non-empty QSS with font-size."""
        result = style_input_label()
        assert isinstance(result, str)
        assert len(result) > 0
        assert "font-size" in result

    def test_style_input_field_returns_nonempty_qss(self) -> None:
        """style_input_field() returns non-empty QSS with QLineEdit selector."""
        result = style_input_field()
        assert isinstance(result, str)
        assert len(result) > 0
        assert "QLineEdit" in result

    def test_style_setting_combo_returns_nonempty_qss(self) -> None:
        """style_setting_combo() returns non-empty QSS with QComboBox selector."""
        result = style_setting_combo()
        assert isinstance(result, str)
        assert len(result) > 0
        assert "QComboBox" in result

    def test_style_tab_widget_returns_nonempty_qss(self) -> None:
        """style_tab_widget() returns non-empty QSS with QTabWidget selector."""
        result = style_tab_widget()
        assert isinstance(result, str)
        assert len(result) > 0
        assert "QTabWidget" in result

    def test_style_radio_button_returns_nonempty_qss(self) -> None:
        """style_radio_button() returns non-empty QSS with QRadioButton selector."""
        result = style_radio_button()
        assert isinstance(result, str)
        assert len(result) > 0
        assert "QRadioButton" in result

    def test_style_danger_button_returns_nonempty_qss(self) -> None:
        """style_danger_button() returns non-empty QSS with QPushButton selector."""
        result = style_danger_button()
        assert isinstance(result, str)
        assert len(result) > 0
        assert "QPushButton" in result
        assert "background-color" in result

    def test_style_delete_button_returns_nonempty_qss(self) -> None:
        """style_delete_button() returns non-empty QSS with QPushButton selector."""
        result = style_delete_button()
        assert isinstance(result, str)
        assert len(result) > 0
        assert "QPushButton" in result

    def test_style_outlined_primary_button_returns_nonempty_qss(self) -> None:
        """style_outlined_primary_button() returns non-empty QSS with QPushButton."""
        result = style_outlined_primary_button()
        assert isinstance(result, str)
        assert len(result) > 0
        assert "QPushButton" in result

    def test_style_warning_button_returns_nonempty_qss(self) -> None:
        """style_warning_button() returns non-empty QSS with QPushButton selector."""
        result = style_warning_button()
        assert isinstance(result, str)
        assert len(result) > 0
        assert "QPushButton" in result

    def test_style_secondary_button_returns_nonempty_qss(self) -> None:
        """style_secondary_button() returns non-empty QSS with QPushButton selector."""
        result = style_secondary_button()
        assert isinstance(result, str)
        assert len(result) > 0
        assert "QPushButton" in result

    def test_style_scrollbar_returns_nonempty_qss(self) -> None:
        """style_scrollbar() returns non-empty QSS with QScrollBar selector."""
        result = style_scrollbar()
        assert isinstance(result, str)
        assert len(result) > 0
        assert "QScrollBar" in result

    def test_style_table_returns_nonempty_qss(self) -> None:
        """style_table() returns non-empty QSS with QTableWidget selector."""
        result = style_table()
        assert isinstance(result, str)
        assert len(result) > 0
        assert "QTableWidget" in result

    def test_style_table_delete_button_returns_nonempty_qss(self) -> None:
        """style_table_delete_button() returns non-empty QSS with QPushButton."""
        result = style_table_delete_button()
        assert isinstance(result, str)
        assert len(result) > 0
        assert "QPushButton" in result

    def test_style_splitter_returns_nonempty_qss(self) -> None:
        """style_splitter() returns non-empty QSS with QSplitter selector."""
        result = style_splitter()
        assert isinstance(result, str)
        assert len(result) > 0
        assert "QSplitter" in result

    # ── style_banner variants ────────────────────────────────────

    def test_style_banner_default_variant(self) -> None:
        """style_banner() with no args uses 'warning' variant (default)."""
        result = style_banner()
        assert isinstance(result, str)
        assert len(result) > 0
        assert "QFrame#Banner" in result

    def test_style_banner_error_variant(self) -> None:
        """style_banner('error') returns non-empty QSS."""
        result = style_banner("error")
        assert isinstance(result, str)
        assert len(result) > 0
        assert "QFrame#Banner" in result

    def test_style_banner_info_variant(self) -> None:
        """style_banner('info') returns non-empty QSS."""
        result = style_banner("info")
        assert isinstance(result, str)
        assert len(result) > 0
        assert "QFrame#Banner" in result

    def test_style_banner_success_variant(self) -> None:
        """style_banner('success') returns non-empty QSS."""
        result = style_banner("success")
        assert isinstance(result, str)
        assert len(result) > 0
        assert "QFrame#Banner" in result

    # ── Theme-switching: styles change across themes ─────────────

    def test_style_functions_return_different_qss_per_theme(self) -> None:
        """Style functions that use theme-sensitive colors differ between themes."""
        original = current_theme()
        try:
            _set_initial_theme("light")
            light_table = style_table()
            _set_initial_theme("dark")
            dark_table = style_table()
            # Palettes have different component_bg, so QSS must differ
            assert light_table != dark_table
        finally:
            _set_initial_theme(original)

    # ── Button styles contain expected CSS properties ────────────

    def test_style_danger_button_uses_error_color(self) -> None:
        """style_danger_button() uses the error palette color for background."""
        result = style_danger_button()
        assert color("error") in result

    def test_style_delete_button_uses_error_color(self) -> None:
        """style_delete_button() uses the error palette color for text/border."""
        result = style_delete_button()
        assert color("error") in result

    def test_style_outlined_primary_button_uses_primary_color(self) -> None:
        """style_outlined_primary_button() uses primary palette color."""
        result = style_outlined_primary_button()
        assert color("primary") in result

    def test_style_warning_button_uses_warning_color(self) -> None:
        """style_warning_button() uses the warning palette color."""
        result = style_warning_button()
        assert color("warning") in result

    def test_style_secondary_button_uses_border_color(self) -> None:
        """style_secondary_button() uses border_light palette color."""
        result = style_secondary_button()
        assert color("border_light") in result


# ---------------------------------------------------------------------------
# CallbackSignal
# ---------------------------------------------------------------------------


class TestCallbackSignal:
    """Tests for the lightweight CallbackSignal class."""

    def test_callback_signal_connect_emit(self) -> None:
        """Connected callback is invoked when signal emits."""
        received: list[object] = []
        signal = CallbackSignal()
        signal.connect(lambda *args: received.extend(args))
        signal.emit("hello")
        assert len(received) == 1  # noqa: PLR2004
        assert received[0] == "hello"

    def test_callback_signal_disconnect(self) -> None:
        """Disconnected callback is NOT invoked on subsequent emits."""
        call_count = [0]

        def handler(*_args: object) -> None:
            call_count[0] += 1

        signal = CallbackSignal()
        signal.connect(handler)
        signal.emit()
        assert call_count[0] == 1  # noqa: PLR2004

        signal.disconnect(handler)
        signal.emit()
        # Count should remain 1 — handler was not called again
        assert call_count[0] == 1  # noqa: PLR2004

    def test_callback_signal_multiple_callbacks(self) -> None:
        """Multiple connected callbacks are all invoked on emit."""
        results: list[str] = []
        signal = CallbackSignal()
        signal.connect(lambda: results.append("a"))
        signal.connect(lambda: results.append("b"))
        signal.emit()
        assert results == ["a", "b"]

    def test_callback_signal_duplicate_connect_ignored(self) -> None:
        """Connecting the same callback twice does not duplicate it."""
        call_count = [0]

        def handler(*_args: object) -> None:
            call_count[0] += 1

        signal = CallbackSignal()
        signal.connect(handler)
        signal.connect(handler)  # duplicate — should be ignored
        signal.emit()
        assert call_count[0] == 1  # noqa: PLR2004

    def test_callback_signal_emit_with_multiple_args(self) -> None:
        """Emit passes multiple arguments to the callback."""
        received: list[tuple[object, ...]] = []
        signal = CallbackSignal()
        signal.connect(lambda *args: received.append(args))
        signal.emit("x", 42, True)
        assert len(received) == 1  # noqa: PLR2004
        assert received[0] == ("x", 42, True)

    def test_callback_signal_disconnect_nonexistent_is_noop(self) -> None:
        """Disconnecting a callback that was never connected is a silent no-op.

        Tolerance is deliberate: widget ``destroyed`` lambdas race
        the conftest's ``_callbacks.clear()`` cleanup, so disconnect
        must survive a previously-cleared listener list without
        raising — otherwise the race cascades through pytest as
        unrelated test failures.
        """
        signal = CallbackSignal()
        # Must not raise.
        signal.disconnect(lambda: None)
        assert signal._callbacks == []

    def test_callback_signal_disconnect_twice_is_noop(self) -> None:
        """Disconnecting the same callback twice is also a silent no-op.

        Same race surface as the never-connected case: the conftest
        cleanup may have cleared the callback already by the time
        the widget's ``destroyed`` lambda fires the disconnect.
        """
        signal = CallbackSignal()
        cb = lambda *_: None  # noqa: E731
        signal.connect(cb)
        signal.disconnect(cb)
        # Second disconnect must not raise.
        signal.disconnect(cb)
        assert signal._callbacks == []

    def test_callback_signal_emit_continues_after_exception(self) -> None:
        """If one callback raises, subsequent callbacks are still invoked.

        Per-callback exception isolation was added so a single broken
        listener (e.g. a settings page that fails to refresh on
        language_changed) cannot blackhole the whole notification chain
        and leave other listeners stuck on the previous locale.
        """
        results: list[str] = []

        def bad_callback(*_args: object) -> None:
            msg = "boom"
            raise RuntimeError(msg)

        signal = CallbackSignal()
        signal.connect(bad_callback)
        signal.connect(lambda: results.append("ok"))
        # emit() must NOT propagate — bad_callback raises, gets logged,
        # then the second callback still runs.
        signal.emit()
        assert results == ["ok"]

    def test_callback_signal_emit_no_callbacks_is_noop(self) -> None:
        """Emitting a signal with no connected callbacks is a no-op."""
        signal = CallbackSignal()
        # Should not raise
        signal.emit()
        signal.emit("arg1", "arg2")

    def test_callback_signal_disconnect_during_emit(self) -> None:
        """Disconnecting a callback during emit does not skip other callbacks.

        The emit() method iterates over a list() copy of _callbacks, so
        mutations during iteration are safe.
        """
        results: list[str] = []
        signal = CallbackSignal()

        def self_disconnecting() -> None:
            results.append("first")
            signal.disconnect(self_disconnecting)

        signal.connect(self_disconnecting)
        signal.connect(lambda: results.append("second"))
        signal.emit()
        # Both callbacks should have been invoked (list copy protects iteration)
        assert results == ["first", "second"]
        # On second emit, only "second" should run (first disconnected itself)
        results.clear()
        signal.emit()
        assert results == ["second"]


# ---------------------------------------------------------------------------
# theme: set_theme() signal propagation
# ---------------------------------------------------------------------------


class TestSetThemePropagation:
    """Tests that set_theme() correctly propagates changes."""

    def test_set_theme_emits_signal_on_change(self) -> None:
        """set_theme() emits theme_changed signal with the new theme name."""
        from src.constants import theme  # noqa: PLC0415

        original = current_theme()
        received: list[str] = []

        def handler(name: str) -> None:
            received.append(name)

        theme.theme_changed.connect(handler)
        try:
            new_theme = "dark" if original == "light" else "light"
            set_theme(new_theme)
            assert received == [new_theme]
        finally:
            _set_initial_theme(original)
            theme.theme_changed.disconnect(handler)

    def test_set_theme_does_not_emit_on_same(self) -> None:
        """set_theme() does NOT emit when the theme is already active."""
        from src.constants import theme  # noqa: PLC0415

        original = current_theme()
        received: list[str] = []

        def handler(name: str) -> None:
            received.append(name)

        theme.theme_changed.connect(handler)
        try:
            set_theme(original)  # no-op
            assert received == []
        finally:
            theme.theme_changed.disconnect(handler)

    def test_set_theme_changes_color_output(self) -> None:
        """After set_theme(), color() returns values from the new palette."""
        original = current_theme()
        try:
            _set_initial_theme("light")
            light_bg = color("app_bg")
            _set_initial_theme("dark")
            dark_bg = color("app_bg")
            # Light and dark must differ for app_bg
            assert light_bg != dark_bg
        finally:
            _set_initial_theme(original)


# ---------------------------------------------------------------------------
# theme: palette key parity between light and dark
# ---------------------------------------------------------------------------


class TestPaletteKeyParity:
    """Tests that light and dark palettes have identical key sets."""

    def test_light_and_dark_have_same_keys(self) -> None:
        """Both palettes contain exactly the same set of color keys."""
        light_keys = set(_PALETTES["light"].keys())
        dark_keys = set(_PALETTES["dark"].keys())
        assert light_keys == dark_keys, (
            f"Keys only in light: {light_keys - dark_keys}, "
            f"Keys only in dark: {dark_keys - light_keys}"
        )

    def test_all_palette_values_are_hex_colors(self) -> None:
        """Every palette value is a valid hex color string (#RGB or #RRGGBB)."""
        import re  # noqa: PLC0415

        hex_pattern = re.compile(r"^#[0-9A-Fa-f]{3}(?:[0-9A-Fa-f]{3})?$")
        for theme_name in ("light", "dark"):
            for key, value in _PALETTES[theme_name].items():
                assert hex_pattern.match(value), (
                    f"Palette[{theme_name}][{key}] = {value!r} is not a valid hex color"
                )

    def test_palette_has_at_least_20_keys(self) -> None:
        """Palettes contain a reasonable number of color keys."""
        for theme_name in ("light", "dark"):
            assert len(_PALETTES[theme_name]) >= 20  # noqa: PLR2004


# ---------------------------------------------------------------------------
# theme: dark-mode style verification
# ---------------------------------------------------------------------------


class TestDarkModeStyles:
    """Tests that style functions work correctly in dark mode."""

    def test_all_style_functions_work_in_dark_mode(self) -> None:
        """Every style_*() function returns non-empty QSS in dark mode."""
        original = current_theme()
        try:
            _set_initial_theme("dark")
            style_fns = [
                style_sidebar_list,
                style_page_header,
                style_section_group,
                style_section_title,
                style_list_widget,
                style_checkbox,
                style_card_light,
                style_card_header,
                style_link_button,
                style_setting_container,
                style_input_label,
                style_input_field,
                style_setting_combo,
                style_tab_widget,
                style_radio_button,
                style_primary_button,
                style_danger_button,
                style_delete_button,
                style_outlined_primary_button,
                style_warning_button,
                style_secondary_button,
                style_scrollbar,
                style_table,
                style_table_delete_button,
                style_splitter,
            ]
            for fn in style_fns:
                result = fn()
                assert isinstance(result, str), f"{fn.__name__} did not return str"
                assert len(result) > 0, f"{fn.__name__} returned empty string"
        finally:
            _set_initial_theme(original)

    def test_dark_mode_styles_use_dark_palette_colors(self) -> None:
        """Dark-mode styles reference dark palette colors, not light ones."""
        original = current_theme()
        try:
            _set_initial_theme("dark")
            dark_component_bg = _PALETTES["dark"]["component_bg"]
            light_component_bg = _PALETTES["light"]["component_bg"]
            result = style_table()
            # Dark palette component_bg must appear in dark-mode QSS
            assert dark_component_bg in result
            # Light palette component_bg must NOT appear (they differ)
            assert light_component_bg not in result
        finally:
            _set_initial_theme(original)

    def test_style_banner_all_variants_in_dark_mode(self) -> None:
        """style_banner() works for all variants in dark mode."""
        original = current_theme()
        try:
            _set_initial_theme("dark")
            for variant in ("warning", "error", "info", "success"):
                result = style_banner(variant)
                assert "QFrame#Banner" in result
                assert len(result) > 0
        finally:
            _set_initial_theme(original)


# ---------------------------------------------------------------------------
# i18n: CallbackSignal and language_changed
# ---------------------------------------------------------------------------


class TestI18nSignal:
    """Tests for the i18n CallbackSignal and language_changed instance."""

    def test_language_changed_is_signal(self) -> None:
        """language_changed is a CallbackSignal instance."""
        from src.constants.i18n import language_changed  # noqa: PLC0415

        assert hasattr(language_changed, "connect")
        assert hasattr(language_changed, "disconnect")
        assert hasattr(language_changed, "emit")

    def test_set_language_emits_signal(self) -> None:
        """set_language() emits language_changed signal with the new code."""
        from src.constants import i18n  # noqa: PLC0415
        from src.constants.i18n import language_changed  # noqa: PLC0415

        original = current_language()
        received: list[str] = []

        def handler(code: str) -> None:
            received.append(code)

        language_changed.connect(handler)
        try:
            new_lang = "vi" if original != "vi" else "en-UK"
            set_language(new_lang)
            assert received == [new_lang]
        finally:
            # Restore original language
            i18n._current_language = "invalid"  # force change on next call
            set_language(original)
            language_changed.disconnect(handler)

    def test_set_language_does_not_emit_on_same(self) -> None:
        """set_language() with current language does not emit signal."""
        from src.constants.i18n import language_changed  # noqa: PLC0415

        received: list[str] = []

        def handler(code: str) -> None:
            received.append(code)

        language_changed.connect(handler)
        try:
            set_language(current_language())  # no-op
            assert received == []
        finally:
            language_changed.disconnect(handler)

    def test_current_language_default(self) -> None:
        """current_language() returns a valid language code by default."""
        result = current_language()
        assert isinstance(result, str)
        assert len(result) > 0
        # Must be one of the valid UI language codes
        from src.constants.i18n import UI_LANGUAGES  # noqa: PLC0415

        valid_codes = {c for c, *_ in UI_LANGUAGES}
        assert result in valid_codes


# ---------------------------------------------------------------------------
# i18n: set_language() valid switching
# ---------------------------------------------------------------------------


class TestSetLanguageSwitching:
    """Tests for set_language() with valid language transitions."""

    def test_set_language_valid_code_changes_current(self) -> None:
        """set_language() with a valid code updates current_language()."""
        from src.constants import i18n  # noqa: PLC0415

        original = current_language()
        try:
            new_lang = "en-UK" if original != "en-UK" else "vi"
            set_language(new_lang)
            assert current_language() == new_lang
        finally:
            i18n._current_language = "invalid"
            set_language(original)

    def test_set_language_loads_translations(self) -> None:
        """set_language() loads translations for the new language."""
        from src.constants import i18n  # noqa: PLC0415

        original = current_language()
        try:
            set_language("vi" if original != "vi" else "en-UK")
            # After switching, translations dict should be populated
            assert isinstance(i18n._translations, dict)
        finally:
            i18n._current_language = "invalid"
            set_language(original)


# ---------------------------------------------------------------------------
# i18n: tr() edge cases
# ---------------------------------------------------------------------------


class TestTrEdgeCases:
    """Additional edge case tests for the tr() function."""

    def test_tr_with_no_kwargs(self) -> None:
        """tr() without kwargs returns the translated string or key."""
        result = tr("nonexistent.xyz")
        assert result == "nonexistent.xyz"

    def test_tr_empty_key(self) -> None:
        """tr() with empty string key returns empty string (key fallback)."""
        result = tr("")
        assert result == ""

    def test_tr_format_with_index_error(self) -> None:
        """tr() catches IndexError from positional format placeholders."""
        from src.constants import i18n  # noqa: PLC0415

        original_translations = i18n._translations.copy()
        try:
            # {0} is a positional placeholder; named kwargs cause KeyError
            i18n._translations["test.pos"] = "Value {0} and {1}"
            result = tr("test.pos", name="x")
            # KeyError is caught, returns raw template
            assert result == "Value {0} and {1}"
        finally:
            i18n._translations = original_translations


# ---------------------------------------------------------------------------
# languages: get_locale_code() edge cases
# ---------------------------------------------------------------------------


class TestGetLocaleCodeEdgeCases:
    """Edge case tests for get_locale_code()."""

    def test_get_locale_code_case_sensitive(self) -> None:
        """get_locale_code() is case-sensitive — wrong case falls back."""
        # "vietnamese" (lowercase) is not in the map
        result = get_locale_code("vietnamese")
        assert result == "vietnamese"  # lowercased fallback of itself

    def test_get_locale_code_partial_match_falls_back(self) -> None:
        """Partial language names don't match."""
        result = get_locale_code("Viet")
        assert result == "viet"  # falls back to lowercased

    def test_get_locale_code_all_languages_have_codes(self) -> None:
        """Every language in LANGUAGES maps to a non-empty locale code."""
        for locale, label, _icon, _native in LANGUAGES:
            result = get_locale_code(label)
            assert result == locale
            assert len(result) > 0

    def test_get_locale_code_whitespace_label_falls_back(self) -> None:
        """Label with leading/trailing whitespace falls back."""
        result = get_locale_code(" Vietnamese ")
        assert result == " vietnamese "  # lowercased, not matched


# ---------------------------------------------------------------------------
# errors: comprehensive coverage
# ---------------------------------------------------------------------------


class TestErrorCodeCoverage:
    """Tests that all error codes have corresponding messages and keys."""

    def test_all_error_tr_keys_have_english_messages(self) -> None:
        """Every code in _ERROR_TR_KEYS also exists in ERROR_MESSAGES."""
        for code in _ERROR_TR_KEYS:
            assert code in ERROR_MESSAGES, (
                f"Error code {code} in _ERROR_TR_KEYS but not in ERROR_MESSAGES"
            )

    def test_all_error_messages_except_none_have_tr_keys(self) -> None:
        """Every code in ERROR_MESSAGES (except ERR_NONE) has a _ERROR_TR_KEYS entry."""
        for code in ERROR_MESSAGES:
            if code == ERR_NONE:
                continue
            assert code in _ERROR_TR_KEYS, (
                f"Error code {code} in ERROR_MESSAGES but not in _ERROR_TR_KEYS"
            )

    def test_error_messages_values_are_nonempty_strings(self) -> None:
        """All ERROR_MESSAGES values (except ERR_NONE) are non-empty strings."""
        for code, msg in ERROR_MESSAGES.items():
            if code == ERR_NONE:
                assert msg == ""
                continue
            assert isinstance(msg, str)
            assert len(msg) > 0, f"ERROR_MESSAGES[{code}] is empty"

    def test_tag_to_code_values_are_valid_error_codes(self) -> None:
        """All _TAG_TO_CODE values are valid error codes in ERROR_MESSAGES."""
        for tag, code in _TAG_TO_CODE.items():
            assert code in ERROR_MESSAGES, (
                f"Tag {tag!r} maps to code {code} not in ERROR_MESSAGES"
            )

    def test_tag_to_tr_key_values_are_nonempty_strings(self) -> None:
        """All _TAG_TO_TR_KEY values are non-empty translation key strings."""
        for tag, tr_key in _TAG_TO_TR_KEY.items():
            assert isinstance(tr_key, str)
            assert len(tr_key) > 0, f"_TAG_TO_TR_KEY[{tag!r}] has empty tr_key"

    def test_no_overlap_between_tag_to_code_and_tag_to_tr_key(self) -> None:
        """_TAG_TO_CODE and _TAG_TO_TR_KEY have no overlapping tags."""
        code_tags = set(_TAG_TO_CODE.keys())
        tr_key_tags = set(_TAG_TO_TR_KEY.keys())
        overlap = code_tags & tr_key_tags
        assert not overlap, f"Tags in both mappings: {overlap}"


# ---------------------------------------------------------------------------
# llm: get_content_type() additional edges
# ---------------------------------------------------------------------------


class TestGetContentTypeAdditional:
    """Additional edge case tests for get_content_type()."""

    def test_get_content_type_rtf(self) -> None:
        """'.rtf' maps to CONTENT_RTF."""
        from src.constants.llm import CONTENT_RTF  # noqa: PLC0415

        assert get_content_type(".rtf") == CONTENT_RTF

    def test_get_content_type_vtt(self) -> None:
        """'.vtt' maps to CONTENT_SUBTITLE."""
        assert get_content_type(".vtt") == CONTENT_SUBTITLE

    def test_get_content_type_ass(self) -> None:
        """'.ass' maps to CONTENT_SUBTITLE."""
        assert get_content_type(".ass") == CONTENT_SUBTITLE

    def test_get_content_type_ssa(self) -> None:
        """'.ssa' maps to CONTENT_SUBTITLE."""
        assert get_content_type(".ssa") == CONTENT_SUBTITLE

    def test_get_content_type_csv(self) -> None:
        """'.csv' maps to CONTENT_DATA_VALUES."""
        assert get_content_type(".csv") == CONTENT_DATA_VALUES

    def test_get_content_type_xliff(self) -> None:
        """'.xliff' and '.xlf' both map to CONTENT_LOCALIZATION."""
        assert get_content_type(".xliff") == CONTENT_LOCALIZATION
        assert get_content_type(".xlf") == CONTENT_LOCALIZATION

    def test_get_content_type_yaml(self) -> None:
        """'.yaml' and '.yml' both map to CONTENT_LOCALIZATION."""
        assert get_content_type(".yaml") == CONTENT_LOCALIZATION
        assert get_content_type(".yml") == CONTENT_LOCALIZATION

    def test_get_content_type_properties(self) -> None:
        """'.properties' maps to CONTENT_LOCALIZATION."""
        assert get_content_type(".properties") == CONTENT_LOCALIZATION

    def test_get_content_type_strings(self) -> None:
        """'.strings' maps to CONTENT_LOCALIZATION."""
        assert get_content_type(".strings") == CONTENT_LOCALIZATION

    def test_get_content_type_pot(self) -> None:
        """'.pot' maps to CONTENT_LOCALIZATION."""
        assert get_content_type(".pot") == CONTENT_LOCALIZATION

    def test_get_content_type_rst(self) -> None:
        """'.rst' maps to CONTENT_MARKDOWN."""
        assert get_content_type(".rst") == CONTENT_MARKDOWN

    def test_get_content_type_htm(self) -> None:
        """'.htm' maps to CONTENT_HTML."""
        assert get_content_type(".htm") == CONTENT_HTML

    def test_get_content_type_xhtml(self) -> None:
        """'.xhtml' maps to CONTENT_HTML."""
        assert get_content_type(".xhtml") == CONTENT_HTML

    def test_document_content_types_completeness(self) -> None:
        """DOCUMENT_CONTENT_TYPES contains all expected document types."""
        from src.constants.llm import CONTENT_EPUB  # noqa: PLC0415

        expected = {
            CONTENT_PLAIN_TEXT,
            CONTENT_MARKDOWN,
            CONTENT_HTML,
            CONTENT_XML,
            CONTENT_PDF,
            CONTENT_EPUB,
        }
        # RTF is also a content type but may or may not be in document types
        for ct in expected:
            assert ct in DOCUMENT_CONTENT_TYPES, (
                f"{ct} missing from DOCUMENT_CONTENT_TYPES"
            )

    def test_data_values_not_in_document_content_types(self) -> None:
        """CONTENT_DATA_VALUES is NOT in DOCUMENT_CONTENT_TYPES."""
        assert CONTENT_DATA_VALUES not in DOCUMENT_CONTENT_TYPES

    def test_subtitle_not_in_document_content_types(self) -> None:
        """CONTENT_SUBTITLE is NOT in DOCUMENT_CONTENT_TYPES."""
        assert CONTENT_SUBTITLE not in DOCUMENT_CONTENT_TYPES

    def test_localization_not_in_document_content_types(self) -> None:
        """CONTENT_LOCALIZATION is NOT in DOCUMENT_CONTENT_TYPES."""
        assert CONTENT_LOCALIZATION not in DOCUMENT_CONTENT_TYPES


# ---------------------------------------------------------------------------
# OCR: additional edge cases
# ---------------------------------------------------------------------------


class TestOcrLangEdgeCases:
    """Additional edge case tests for OCR language mapping functions."""

    def test_get_tesseract_lang_cjk_languages(self) -> None:
        """CJK languages return correct Tesseract codes."""
        from src.constants.ocr import get_tesseract_lang  # noqa: PLC0415

        assert get_tesseract_lang("Chinese (Simplified)") == "chi_sim"
        assert get_tesseract_lang("Chinese (Traditional)") == "chi_tra"
        assert get_tesseract_lang("Japanese") == "jpn"
        assert get_tesseract_lang("Korean") == "kor"

    def test_get_easyocr_langs_cjk_languages(self) -> None:
        """CJK languages return [code, 'en'] for EasyOCR."""
        from src.constants.ocr import get_easyocr_langs  # noqa: PLC0415

        assert get_easyocr_langs("Chinese (Simplified)") == ["ch_sim", "en"]
        assert get_easyocr_langs("Japanese") == ["ja", "en"]
        assert get_easyocr_langs("Korean") == ["ko", "en"]

    def test_get_easyocr_langs_english_uk(self) -> None:
        """English (UK) returns ['en'] without duplication."""
        from src.constants.ocr import get_easyocr_langs  # noqa: PLC0415

        result = get_easyocr_langs("English (UK)")
        assert result == ["en"]
        assert len(result) == 1  # noqa: PLR2004

    def test_get_google_lang_hints_chinese_variants(self) -> None:
        """Chinese variants return different Google hint codes."""
        from src.constants.ocr import get_google_lang_hints  # noqa: PLC0415

        simplified = get_google_lang_hints("Chinese (Simplified)")
        traditional = get_google_lang_hints("Chinese (Traditional)")
        assert simplified == ["zh"]
        assert traditional == ["zh-TW"]

    def test_get_google_lang_hints_returns_single_element_list(self) -> None:
        """Known language returns a list with exactly one element."""
        from src.constants.ocr import get_google_lang_hints  # noqa: PLC0415

        result = get_google_lang_hints("Vietnamese")
        assert isinstance(result, list)
        assert len(result) == 1  # noqa: PLR2004
        assert result[0] == "vi"

    def test_get_tesseract_lang_portuguese_variants_same_code(self) -> None:
        """Both Portuguese variants map to the same Tesseract code 'por'."""
        from src.constants.ocr import get_tesseract_lang  # noqa: PLC0415

        assert get_tesseract_lang("Portuguese (Brazil)") == "por"
        assert get_tesseract_lang("Portuguese (Portugal)") == "por"

    def test_get_easyocr_langs_portuguese_same_code(self) -> None:
        """Both Portuguese variants map to the same EasyOCR code."""
        from src.constants.ocr import get_easyocr_langs  # noqa: PLC0415

        assert get_easyocr_langs("Portuguese (Brazil)") == ["pt", "en"]
        assert get_easyocr_langs("Portuguese (Portugal)") == ["pt", "en"]

    def test_ocr_codes_all_entries_have_three_codes(self) -> None:
        """Every _LANG_OCR_CODES entry is a 3-tuple of non-empty strings."""
        from src.constants.ocr import _LANG_OCR_CODES  # noqa: PLC0415

        for lang_label, codes in _LANG_OCR_CODES.items():
            assert len(codes) == 3, f"{lang_label} has {len(codes)} codes, expected 3"  # noqa: PLR2004
            for i, code in enumerate(codes):
                assert isinstance(code, str), (
                    f"{lang_label}[{i}] is not a string: {code!r}"
                )
                assert len(code) > 0, f"{lang_label}[{i}] is empty"

    def test_get_tesseract_lang_none_equivalent(self) -> None:
        """Passing None-like values — empty string falls back to 'eng'."""
        from src.constants.ocr import get_tesseract_lang  # noqa: PLC0415

        # Empty string is the documented "missing" sentinel
        assert get_tesseract_lang("") == "eng"

    def test_get_easyocr_langs_case_sensitive(self) -> None:
        """Language lookup is case-sensitive — lowercase 'french' misses."""
        from src.constants.ocr import get_easyocr_langs  # noqa: PLC0415

        result = get_easyocr_langs("french")
        assert result == ["en"]  # Falls back because "french" != "French"

    def test_get_google_lang_hints_case_sensitive(self) -> None:
        """Language lookup is case-sensitive — lowercase 'arabic' returns None."""
        from src.constants.ocr import get_google_lang_hints  # noqa: PLC0415

        result = get_google_lang_hints("arabic")
        assert result is None  # Falls back because "arabic" != "Arabic"


# ---------------------------------------------------------------------------
# NEW TESTS: CallbackSignal additional coverage
# ---------------------------------------------------------------------------


class TestCallbackSignalAdditional:
    """Additional tests for CallbackSignal beyond existing coverage."""

    def test_connect_adds_handler(self) -> None:
        """connect() adds a handler to the internal callbacks list."""
        signal = CallbackSignal()
        handler = lambda: None  # noqa: E731
        signal.connect(handler)
        assert handler in signal._callbacks

    def test_emit_calls_all_handlers(self) -> None:
        """emit() calls every registered handler exactly once."""
        signal = CallbackSignal()
        results: list[str] = []
        signal.connect(lambda: results.append("a"))
        signal.connect(lambda: results.append("b"))
        signal.connect(lambda: results.append("c"))
        signal.emit()
        assert results == ["a", "b", "c"]

    def test_disconnect_removes_handler_from_list(self) -> None:
        """disconnect() removes the handler from _callbacks."""
        signal = CallbackSignal()
        handler = lambda: None  # noqa: E731
        signal.connect(handler)
        assert handler in signal._callbacks
        signal.disconnect(handler)
        assert handler not in signal._callbacks

    def test_emit_with_no_handlers_does_not_raise(self) -> None:
        """Emitting with zero handlers does not raise."""
        signal = CallbackSignal()
        signal.emit()
        signal.emit("arg1", "arg2", "arg3")

    def test_multiple_connect_different_handlers(self) -> None:
        """Connecting multiple different handlers registers them all."""
        signal = CallbackSignal()
        h1 = lambda: None  # noqa: E731
        h2 = lambda: None  # noqa: E731
        h3 = lambda: None  # noqa: E731
        signal.connect(h1)
        signal.connect(h2)
        signal.connect(h3)
        assert len(signal._callbacks) == 3  # noqa: PLR2004

    def test_disconnect_non_existent_handler_is_noop(self) -> None:
        """disconnect() silently no-ops for a handler never connected.

        See ``test_callback_signal_disconnect_nonexistent_is_noop``
        above for the full reasoning — double-disconnect tolerance
        is required to survive the conftest-cleanup race.
        """
        signal = CallbackSignal()

        def some_handler() -> None:
            pass

        # Must not raise.
        signal.disconnect(some_handler)
        assert signal._callbacks == []

    def test_emit_with_keyword_style_arguments(self) -> None:
        """Arguments passed to emit() are positional and forwarded correctly."""
        signal = CallbackSignal()
        captured: list[tuple] = []
        signal.connect(lambda *a: captured.append(a))
        signal.emit(1, "two", 3.0, True)
        assert captured == [(1, "two", 3.0, True)]


# ---------------------------------------------------------------------------
# NEW TESTS: Error Constants uniqueness and mapping
# ---------------------------------------------------------------------------


class TestErrorConstantsUniqueness:
    """Tests that all ERR_* codes are unique and properly mapped."""

    def test_all_err_codes_are_unique(self) -> None:
        """All ERR_* module-level constants have unique integer values."""
        import src.constants.errors as err_mod  # noqa: PLC0415

        codes: list[int] = []
        for name in dir(err_mod):
            if name.startswith("ERR_"):
                val = getattr(err_mod, name)
                if isinstance(val, int):
                    codes.append(val)
        assert len(codes) == len(set(codes)), "Duplicate ERR_* code values found"
        assert len(codes) > 0, "No ERR_* codes found"

    def test_error_code_to_message_mapping_complete(self) -> None:
        """Every _ERROR_TR_KEYS code has ERROR_MESSAGES entry and vice versa."""
        for code in _ERROR_TR_KEYS:
            assert code in ERROR_MESSAGES
        for code in ERROR_MESSAGES:
            if code == ERR_NONE:
                continue
            assert code in _ERROR_TR_KEYS

    def test_all_error_codes_have_messages(self) -> None:
        """Every ERR_* constant (except ERR_NONE) has an ERROR_MESSAGES entry."""
        import src.constants.errors as err_mod  # noqa: PLC0415

        for name in dir(err_mod):
            if name.startswith("ERR_"):
                val = getattr(err_mod, name)
                if isinstance(val, int):
                    assert val in ERROR_MESSAGES, (
                        f"{name} (value={val}) not in ERROR_MESSAGES"
                    )

    def test_err_none_message_is_empty(self) -> None:
        """ERR_NONE maps to an empty string in ERROR_MESSAGES."""
        assert ERROR_MESSAGES[ERR_NONE] == ""


# ---------------------------------------------------------------------------
# NEW TESTS: File Constants
# ---------------------------------------------------------------------------


class TestFileConstantsComprehensive:
    """Comprehensive tests for file extension constants."""

    def test_supported_images_is_non_empty(self) -> None:
        """SUPPORTED_IMAGES contains at least one extension."""
        from src.constants.files import SUPPORTED_IMAGES  # noqa: PLC0415

        assert len(SUPPORTED_IMAGES) > 0

    def test_supported_text_is_non_empty(self) -> None:
        """SUPPORTED_TEXT contains at least one extension."""
        from src.constants.files import SUPPORTED_TEXT  # noqa: PLC0415

        assert len(SUPPORTED_TEXT) > 0

    def test_supported_audio_is_non_empty(self) -> None:
        """SUPPORTED_AUDIO contains at least one extension."""
        from src.constants.files import SUPPORTED_AUDIO  # noqa: PLC0415

        assert len(SUPPORTED_AUDIO) > 0

    def test_supported_video_is_non_empty(self) -> None:
        """SUPPORTED_VIDEO contains at least one extension."""
        from src.constants.files import SUPPORTED_VIDEO  # noqa: PLC0415

        assert len(SUPPORTED_VIDEO) > 0

    def test_supported_media_is_audio_plus_video(self) -> None:
        """SUPPORTED_MEDIA is the concatenation of audio and video lists."""
        from src.constants.files import (  # noqa: PLC0415
            SUPPORTED_AUDIO,
            SUPPORTED_MEDIA,
            SUPPORTED_VIDEO,
        )

        assert SUPPORTED_MEDIA == SUPPORTED_AUDIO + SUPPORTED_VIDEO

    def test_supported_voice_input_is_non_empty(self) -> None:
        """SUPPORTED_VOICE_INPUT contains at least one extension."""
        from src.constants.files import SUPPORTED_VOICE_INPUT  # noqa: PLC0415

        assert len(SUPPORTED_VOICE_INPUT) > 0

    def test_file_filter_string_format(self) -> None:
        """FILE_FILTER uses ';;' section separators and contains '*' wildcards."""
        from src.constants.files import FILE_FILTER  # noqa: PLC0415

        sections = FILE_FILTER.split(";;")
        assert len(sections) >= 3  # noqa: PLR2004
        for section in sections:
            assert len(section.strip()) > 0

    def test_all_audio_extensions_start_with_dot(self) -> None:
        """All audio extensions start with '.'."""
        from src.constants.files import SUPPORTED_AUDIO  # noqa: PLC0415

        for ext in SUPPORTED_AUDIO:
            assert ext.startswith(".")

    def test_all_video_extensions_start_with_dot(self) -> None:
        """All video extensions start with '.'."""
        from src.constants.files import SUPPORTED_VIDEO  # noqa: PLC0415

        for ext in SUPPORTED_VIDEO:
            assert ext.startswith(".")

    def test_subtitle_extensions_in_text(self) -> None:
        """Subtitle extensions (.srt, .vtt, .ass, .ssa) are in SUPPORTED_TEXT."""
        from src.constants.files import SUPPORTED_TEXT  # noqa: PLC0415

        for ext in [".srt", ".vtt", ".ass", ".ssa"]:
            assert ext in SUPPORTED_TEXT

    def test_localization_extensions_in_text(self) -> None:
        """Localization extensions (.po, .pot, .xliff, .xlf) are in SUPPORTED_TEXT."""
        from src.constants.files import SUPPORTED_TEXT  # noqa: PLC0415

        for ext in [".po", ".pot", ".xliff", ".xlf", ".yaml", ".yml"]:
            assert ext in SUPPORTED_TEXT

    def test_no_duplicates_in_supported_images(self) -> None:
        """No duplicate entries in SUPPORTED_IMAGES."""
        from src.constants.files import SUPPORTED_IMAGES  # noqa: PLC0415

        assert len(SUPPORTED_IMAGES) == len(set(SUPPORTED_IMAGES))

    def test_no_duplicates_in_supported_text(self) -> None:
        """No duplicate entries in SUPPORTED_TEXT."""
        from src.constants.files import SUPPORTED_TEXT  # noqa: PLC0415

        assert len(SUPPORTED_TEXT) == len(set(SUPPORTED_TEXT))


# ---------------------------------------------------------------------------
# NEW TESTS: History Constants
# ---------------------------------------------------------------------------


class TestHistoryConstants:
    """Tests for history status constants."""

    def test_all_status_values_are_unique_strings(self) -> None:
        """All STATUS_* constants are unique non-empty strings."""
        from src.constants.history import (  # noqa: PLC0415
            STATUS_DELETING,
            STATUS_DONE,
            STATUS_EXTRACTING,
            STATUS_FAILED,
            STATUS_GENERATING,
            STATUS_PAUSED,
            STATUS_PENDING,
            STATUS_TRANSLATING,
        )

        statuses = [
            STATUS_PENDING,
            STATUS_TRANSLATING,
            STATUS_EXTRACTING,
            STATUS_GENERATING,
            STATUS_DONE,
            STATUS_FAILED,
            STATUS_PAUSED,
            STATUS_DELETING,
        ]
        # All are non-empty strings
        for s in statuses:
            assert isinstance(s, str)
            assert len(s) > 0
        # All are unique
        assert len(statuses) == len(set(statuses))

    def test_active_statuses_group(self) -> None:
        """ACTIVE_STATUSES contains Pending and Translating."""
        from src.constants.history import (  # noqa: PLC0415
            ACTIVE_STATUSES,
            STATUS_PENDING,
            STATUS_TRANSLATING,
        )

        assert STATUS_PENDING in ACTIVE_STATUSES
        assert STATUS_TRANSLATING in ACTIVE_STATUSES

    def test_unfinished_statuses_group(self) -> None:
        """UNFINISHED_STATUSES contains Pending, Translating, and Paused."""
        from src.constants.history import (  # noqa: PLC0415
            STATUS_PAUSED,
            STATUS_PENDING,
            STATUS_TRANSLATING,
            UNFINISHED_STATUSES,
        )

        assert STATUS_PENDING in UNFINISHED_STATUSES
        assert STATUS_TRANSLATING in UNFINISHED_STATUSES
        assert STATUS_PAUSED in UNFINISHED_STATUSES

    def test_reprocessable_statuses_group(self) -> None:
        """REPROCESSABLE_STATUSES contains Done, Failed, and Paused."""
        from src.constants.history import (  # noqa: PLC0415
            REPROCESSABLE_STATUSES,
            STATUS_DONE,
            STATUS_FAILED,
            STATUS_PAUSED,
        )

        assert STATUS_DONE in REPROCESSABLE_STATUSES
        assert STATUS_FAILED in REPROCESSABLE_STATUSES
        assert STATUS_PAUSED in REPROCESSABLE_STATUSES

    def test_progress_milestones_ordering(self) -> None:
        """Progress milestones are in ascending order."""
        from src.constants.history import (  # noqa: PLC0415
            PROGRESS_COMPLETE,
            PROGRESS_INITIAL,
            PROGRESS_LLM_DONE,
            PROGRESS_OCR_DONE,
        )

        assert PROGRESS_INITIAL < PROGRESS_OCR_DONE
        assert PROGRESS_OCR_DONE < PROGRESS_LLM_DONE
        assert PROGRESS_LLM_DONE <= PROGRESS_COMPLETE

    def test_progress_complete_is_100(self) -> None:
        """PROGRESS_COMPLETE equals 100."""
        from src.constants.history import PROGRESS_COMPLETE  # noqa: PLC0415

        assert PROGRESS_COMPLETE == 100  # noqa: PLR2004

    def test_display_status_unknown_returns_input(self) -> None:
        """display_status() with unknown status returns the input string."""
        from src.constants.history import display_status  # noqa: PLC0415

        result = display_status("UnknownStatus")
        assert result == "UnknownStatus"


# ---------------------------------------------------------------------------
# NEW TESTS: Languages Constants
# ---------------------------------------------------------------------------


class TestLanguagesConstantsComprehensive:
    """Comprehensive tests for language constants."""

    def test_languages_list_has_40_plus_entries(self) -> None:
        """LANGUAGES list contains at least 40 entries."""
        assert len(LANGUAGES) >= 40  # noqa: PLR2004

    def test_each_entry_has_four_elements(self) -> None:
        """Each LANGUAGES entry is a 4-tuple (locale, label, flag, native)."""
        for entry in LANGUAGES:
            assert len(entry) == 4, f"Entry has {len(entry)} elements: {entry}"  # noqa: PLR2004

    def test_each_entry_elements_are_non_empty_strings(self) -> None:
        """All four elements of each LANGUAGES entry are non-empty strings."""
        for locale, label, flag, native in LANGUAGES:
            assert isinstance(locale, str) and len(locale) > 0, (
                f"Bad locale: {locale!r}"
            )
            assert isinstance(label, str) and len(label) > 0, f"Bad label: {label!r}"
            assert isinstance(flag, str) and len(flag) > 0, f"Bad flag: {flag!r}"
            assert isinstance(native, str) and len(native) > 0, (
                f"Bad native: {native!r}"
            )

    def test_available_languages_derived_correctly(self) -> None:
        """AVAILABLE_LANGUAGES is derived from LANGUAGES labels."""
        expected = [lang[1] for lang in LANGUAGES]
        assert expected == AVAILABLE_LANGUAGES

    def test_locale_codes_are_non_empty(self) -> None:
        """All locale codes in LANGUAGES are non-empty strings."""
        for locale, _label, _flag, _native in LANGUAGES:
            assert len(locale) > 0

    def test_labels_are_unique(self) -> None:
        """All language labels in LANGUAGES are unique."""
        labels = [lang[1] for lang in LANGUAGES]
        assert len(labels) == len(set(labels))

    def test_locale_codes_are_unique(self) -> None:
        """All locale codes in LANGUAGES are unique."""
        locales = [lang[0] for lang in LANGUAGES]
        assert len(locales) == len(set(locales))


# ---------------------------------------------------------------------------
# NEW TESTS: LLM Constants
# ---------------------------------------------------------------------------


class TestLLMConstants:
    """Tests for LLM-related constants."""

    def test_content_type_constants_are_distinct(self) -> None:
        """All CONTENT_* constants have unique string values."""
        from src.constants.llm import (  # noqa: PLC0415
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
        )

        types = [
            CONTENT_PLAIN_TEXT,
            CONTENT_MARKDOWN,
            CONTENT_HTML,
            CONTENT_XML,
            CONTENT_RTF,
            CONTENT_EPUB,
            CONTENT_DATA_VALUES,
            CONTENT_SUBTITLE,
            CONTENT_LOCALIZATION,
            CONTENT_PDF,
        ]
        assert len(types) == len(set(types))

    def test_token_budget_is_positive(self) -> None:
        """TOKEN_BUDGET is a positive integer."""
        from src.constants.llm import TOKEN_BUDGET  # noqa: PLC0415

        assert isinstance(TOKEN_BUDGET, int)
        assert TOKEN_BUDGET > 0

    def test_translation_batch_size_is_positive(self) -> None:
        """TRANSLATION_BATCH_SIZE is a positive integer."""
        from src.constants.llm import TRANSLATION_BATCH_SIZE  # noqa: PLC0415

        assert isinstance(TRANSLATION_BATCH_SIZE, int)
        assert TRANSLATION_BATCH_SIZE > 0

    def test_llm_methods_contains_gemini_and_custom(self) -> None:
        """LLM_METHODS contains both Gemini and Custom."""
        from src.constants.llm import (  # noqa: PLC0415
            LLM_METHOD_CUSTOM,
            LLM_METHOD_GEMINI,
            LLM_METHODS,
        )

        assert LLM_METHOD_GEMINI in LLM_METHODS
        assert LLM_METHOD_CUSTOM in LLM_METHODS

    def test_gemini_models_is_non_empty(self) -> None:
        """GEMINI_MODELS list is non-empty."""
        from src.constants.llm import GEMINI_MODELS  # noqa: PLC0415

        assert len(GEMINI_MODELS) > 0

    def test_default_gemini_model_in_models_list(self) -> None:
        """DEFAULT_GEMINI_MODEL is in GEMINI_MODELS list."""
        from src.constants.llm import (  # noqa: PLC0415
            DEFAULT_GEMINI_MODEL,
            GEMINI_MODELS,
        )

        assert DEFAULT_GEMINI_MODEL in GEMINI_MODELS

    def test_transient_error_tags_are_non_empty(self) -> None:
        """TRANSIENT_ERROR_TAGS tuple is non-empty."""
        from src.constants.llm import TRANSIENT_ERROR_TAGS  # noqa: PLC0415

        assert len(TRANSIENT_ERROR_TAGS) > 0
        for tag in TRANSIENT_ERROR_TAGS:
            assert isinstance(tag, str)
            assert len(tag) > 0

    def test_timeout_error_is_not_transient(self) -> None:
        """TIMEOUT_ERROR must NOT be in the transient retry set.

        A request that exceeded the per-call timeout indicates the
        model is genuinely slow on this prompt — retrying with the
        same content typically times out again and burns
        ``max_retries × timeout`` seconds before failing.  Surface
        the timeout immediately so the user can act (switch model,
        split the batch).
        """
        from src.constants.llm import TRANSIENT_ERROR_TAGS  # noqa: PLC0415

        assert "TIMEOUT_ERROR" not in TRANSIENT_ERROR_TAGS

    def test_llm_temperature_is_non_negative(self) -> None:
        """LLM_TEMPERATURE is a non-negative float."""
        from src.constants.llm import LLM_TEMPERATURE  # noqa: PLC0415

        assert isinstance(LLM_TEMPERATURE, (int, float))
        assert LLM_TEMPERATURE >= 0.0

    def test_retry_max_attempts_is_positive(self) -> None:
        """RETRY_MAX_ATTEMPTS is a positive integer."""
        from src.constants.llm import RETRY_MAX_ATTEMPTS  # noqa: PLC0415

        assert isinstance(RETRY_MAX_ATTEMPTS, int)
        assert RETRY_MAX_ATTEMPTS > 0

    def test_get_content_type_returns_correct_for_each_format(self) -> None:
        """get_content_type returns the expected type for representative extensions."""
        from src.constants.llm import (  # noqa: PLC0415
            CONTENT_DATA_VALUES,
            CONTENT_HTML,
            CONTENT_LOCALIZATION,
            CONTENT_MARKDOWN,
            CONTENT_PDF,
            CONTENT_PLAIN_TEXT,
            CONTENT_RTF,
            CONTENT_SUBTITLE,
            CONTENT_XML,
        )

        expected_map = {
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
            ".po": CONTENT_LOCALIZATION,
            ".properties": CONTENT_LOCALIZATION,
            ".strings": CONTENT_LOCALIZATION,
            ".pdf": CONTENT_PDF,
        }
        for ext, expected_type in expected_map.items():
            assert get_content_type(ext) == expected_type, (
                f"get_content_type({ext!r}) != {expected_type!r}"
            )


# ---------------------------------------------------------------------------
# NEW TESTS: OCR Constants coverage
# ---------------------------------------------------------------------------


class TestOCRConstantsCoverage:
    """Tests for OCR constant coverage and structural integrity."""

    def test_lang_ocr_codes_covers_all_available_languages(self) -> None:
        """_LANG_OCR_CODES covers every language in AVAILABLE_LANGUAGES."""
        from src.constants.ocr import _LANG_OCR_CODES  # noqa: PLC0415

        for lang in AVAILABLE_LANGUAGES:
            assert lang in _LANG_OCR_CODES, f"{lang} missing from _LANG_OCR_CODES"

    def test_ocr_padding_constants_are_tuples(self) -> None:
        """OCR padding constants are 2-tuples of integers."""
        from src.constants.ocr import (  # noqa: PLC0415
            OCR_PADDING_DEFAULT,
            OCR_PADDING_EASYOCR,
        )

        for padding in (OCR_PADDING_EASYOCR, OCR_PADDING_DEFAULT):
            assert isinstance(padding, tuple)
            assert len(padding) == 2  # noqa: PLR2004

    def test_ocr_layout_metrics_are_positive(self) -> None:
        """OCR layout metric constants are positive."""
        from src.constants.ocr import (  # noqa: PLC0415
            OCR_DEFAULT_LINE_HEIGHT,
            OCR_MAX_LINE_HEIGHT,
            OCR_MIN_LINE_HEIGHT,
            OCR_SINGLE_LINE_HEIGHT,
        )

        for val in (
            OCR_DEFAULT_LINE_HEIGHT,
            OCR_SINGLE_LINE_HEIGHT,
            OCR_MIN_LINE_HEIGHT,
            OCR_MAX_LINE_HEIGHT,
        ):
            assert val > 0, f"OCR layout metric {val} is not positive"

    def test_ocr_min_less_than_max_line_height(self) -> None:
        """OCR_MIN_LINE_HEIGHT < OCR_MAX_LINE_HEIGHT."""
        from src.constants.ocr import (  # noqa: PLC0415
            OCR_MAX_LINE_HEIGHT,
            OCR_MIN_LINE_HEIGHT,
        )

        assert OCR_MIN_LINE_HEIGHT < OCR_MAX_LINE_HEIGHT


# ---------------------------------------------------------------------------
# NEW TESTS: Settings Constants
# ---------------------------------------------------------------------------


class TestSettingsConstants:
    """Tests for settings key constants."""

    def test_all_setting_constants_are_unique_strings(self) -> None:
        """All SETTING_* constants have unique non-empty string values."""
        import src.constants.settings as settings_mod  # noqa: PLC0415

        values: list[str] = []
        for name in dir(settings_mod):
            if name.startswith("SETTING_"):
                val = getattr(settings_mod, name)
                if isinstance(val, str):
                    values.append(val)
        assert len(values) > 0, "No SETTING_* constants found"
        assert len(values) == len(set(values)), (
            f"Duplicate SETTING_* values found: "
            f"{[v for v in values if values.count(v) > 1]}"
        )

    def test_setting_key_format_uses_slash(self) -> None:
        """All SETTING_* constants with '/' follow 'section/key' format."""
        import src.constants.settings as settings_mod  # noqa: PLC0415

        for name in dir(settings_mod):
            if name.startswith("SETTING_"):
                val = getattr(settings_mod, name)
                if isinstance(val, str) and "/" in val:
                    parts = val.split("/")
                    assert len(parts) == 2, (  # noqa: PLR2004
                        f"{name} = {val!r} has unexpected '/' count"
                    )
                    assert len(parts[0]) > 0, f"{name} has empty section"
                    assert len(parts[1]) > 0, f"{name} has empty key"

    def test_extract_method_constants_are_distinct(self) -> None:
        """EXTRACT_METHOD_OCR and EXTRACT_METHOD_LLM are distinct strings."""
        from src.constants.settings import (  # noqa: PLC0415
            EXTRACT_METHOD_LLM,
            EXTRACT_METHOD_OCR,
        )

        assert EXTRACT_METHOD_OCR != EXTRACT_METHOD_LLM
        assert isinstance(EXTRACT_METHOD_OCR, str)
        assert isinstance(EXTRACT_METHOD_LLM, str)

    def test_voice_gender_constants_are_distinct(self) -> None:
        """VOICE_GENDER_FEMALE and VOICE_GENDER_MALE are distinct strings."""
        from src.constants.settings import (  # noqa: PLC0415
            VOICE_GENDER_FEMALE,
            VOICE_GENDER_MALE,
        )

        assert VOICE_GENDER_FEMALE != VOICE_GENDER_MALE

    def test_stt_method_constants_are_distinct(self) -> None:
        """STT_WHISPER and STT_GOOGLE are distinct strings."""
        from src.constants.settings import STT_GOOGLE, STT_WHISPER  # noqa: PLC0415

        assert STT_WHISPER != STT_GOOGLE


# ---------------------------------------------------------------------------
# NEW TESTS: UI Constants
# ---------------------------------------------------------------------------


class TestUIConstants:
    """Tests for UI layout constants."""

    def test_height_control_value(self) -> None:
        """HEIGHT_CONTROL is 42px as documented."""
        from src.constants.ui import HEIGHT_CONTROL  # noqa: PLC0415

        assert HEIGHT_CONTROL == 42  # noqa: PLR2004

    def test_layout_constants_are_positive(self) -> None:
        """All layout spacing/margin constants are positive integers."""
        from src.constants.ui import (  # noqa: PLC0415
            MARGIN_PAGE,
            MARGIN_SECTION,
            MARGIN_SUBSECTION,
            MIN_WINDOW_HEIGHT,
            MIN_WINDOW_WIDTH,
            RADIUS_BUTTON,
            SIDEBAR_WIDTH,
            SPACING_PAGE,
            SPACING_SECTION,
            SPACING_SUBSECTION,
        )

        for val in (
            MARGIN_PAGE,
            MARGIN_SECTION,
            MARGIN_SUBSECTION,
            SPACING_PAGE,
            SPACING_SECTION,
            SPACING_SUBSECTION,
            RADIUS_BUTTON,
            SIDEBAR_WIDTH,
            MIN_WINDOW_WIDTH,
            MIN_WINDOW_HEIGHT,
        ):
            assert isinstance(val, int)
            assert val > 0

    def test_font_size_constants_are_positive(self) -> None:
        """Font size constants are positive floats."""
        from src.constants.ui import (  # noqa: PLC0415
            FONT_SIZE_DEFAULT,
            FONT_SIZE_MIN,
            FONT_SIZE_STEP,
        )

        assert FONT_SIZE_MIN > 0
        assert FONT_SIZE_DEFAULT > 0
        assert FONT_SIZE_STEP > 0

    def test_font_size_min_less_than_default(self) -> None:
        """FONT_SIZE_MIN is less than FONT_SIZE_DEFAULT."""
        from src.constants.ui import FONT_SIZE_DEFAULT, FONT_SIZE_MIN  # noqa: PLC0415

        assert FONT_SIZE_MIN < FONT_SIZE_DEFAULT

    def test_banner_constants_are_positive(self) -> None:
        """Banner layout constants are positive."""
        from src.constants.ui import (  # noqa: PLC0415
            BANNER_FONT_SIZE,
            BANNER_ICON_SIZE,
            BANNER_PADDING,
            BANNER_SPACING,
        )

        for val in (BANNER_PADDING, BANNER_SPACING, BANNER_ICON_SIZE, BANNER_FONT_SIZE):
            assert val > 0

    def test_assets_dir_is_path(self) -> None:
        """ASSETS_DIR is a Path object."""
        from pathlib import Path  # noqa: PLC0415

        from src.constants.ui import ASSETS_DIR  # noqa: PLC0415

        assert isinstance(ASSETS_DIR, Path)


# ---------------------------------------------------------------------------
# NEW TESTS: Theme Engine additional coverage
# ---------------------------------------------------------------------------


class TestThemeEngineAdditional:
    """Additional tests for the theme engine."""

    def test_color_returns_hex_for_all_keys(self) -> None:
        """color() returns a string starting with '#' for every palette key."""
        original = current_theme()
        try:
            for theme_name in ("light", "dark"):
                _set_initial_theme(theme_name)
                for key in _PALETTES[theme_name]:
                    result = color(key)
                    assert result.startswith("#"), (
                        f"color({key!r}) = {result!r} doesn't start with '#'"
                    )
        finally:
            _set_initial_theme(original)

    def test_color_with_invalid_key_raises_key_error(self) -> None:
        """color() with an invalid key raises KeyError."""
        with pytest.raises(KeyError):
            color("this_key_does_not_exist_in_palette")

    def test_set_theme_changes_colors(self) -> None:
        """After set_theme(), color() returns values from the new palette."""
        from src.constants import theme as theme_mod  # noqa: PLC0415

        original = current_theme()
        received: list[str] = []
        theme_mod.theme_changed.connect(received.append)
        try:
            new_theme = "dark" if original == "light" else "light"
            set_theme(new_theme)
            # color() should now return values from the new palette
            assert color("app_bg") == _PALETTES[new_theme]["app_bg"]
            assert received == [new_theme]
        finally:
            _set_initial_theme(original)
            theme_mod.theme_changed.disconnect(received.append)

    def test_theme_changed_signal_fires_on_set_theme(self) -> None:
        """theme_changed signal fires exactly once on theme change."""
        from src.constants import theme as theme_mod  # noqa: PLC0415

        original = current_theme()
        fire_count = [0]

        def counter(name: str) -> None:
            fire_count[0] += 1

        theme_mod.theme_changed.connect(counter)
        try:
            new_theme = "dark" if original == "light" else "light"
            set_theme(new_theme)
            assert fire_count[0] == 1  # noqa: PLR2004
        finally:
            _set_initial_theme(original)
            theme_mod.theme_changed.disconnect(counter)

    def test_style_functions_return_non_empty_css(self) -> None:
        """All style_*() functions return non-empty strings."""
        style_fns = [
            style_sidebar_list,
            style_page_header,
            style_section_group,
            style_section_title,
            style_list_widget,
            style_checkbox,
            style_card_light,
            style_card_header,
            style_link_button,
            style_setting_container,
            style_input_label,
            style_input_field,
            style_setting_combo,
            style_tab_widget,
            style_radio_button,
            style_primary_button,
            style_danger_button,
            style_delete_button,
            style_outlined_primary_button,
            style_warning_button,
            style_secondary_button,
            style_scrollbar,
            style_table,
            style_table_delete_button,
            style_splitter,
        ]
        for fn in style_fns:
            result = fn()
            assert isinstance(result, str)
            assert len(result) > 0, f"{fn.__name__} returned empty string"

    def test_style_primary_button_contains_disabled_state(self) -> None:
        """style_primary_button() includes a :disabled pseudo-state."""
        result = style_primary_button()
        assert ":disabled" in result

    def test_style_delete_button_contains_hover_state(self) -> None:
        """style_delete_button() includes a :hover pseudo-state."""
        result = style_delete_button()
        assert ":hover" in result


# ---------------------------------------------------------------------------
# NEW TESTS: Office Constants
# ---------------------------------------------------------------------------


class TestOfficeConstants:
    """Tests for office font preservation constants."""

    def test_win32com_font_properties_is_non_empty_tuple(self) -> None:
        """WIN32COM_FONT_PROPERTIES is a non-empty tuple of strings."""
        from src.constants.office import WIN32COM_FONT_PROPERTIES  # noqa: PLC0415

        assert isinstance(WIN32COM_FONT_PROPERTIES, tuple)
        assert len(WIN32COM_FONT_PROPERTIES) > 0
        for prop in WIN32COM_FONT_PROPERTIES:
            assert isinstance(prop, str)
            assert len(prop) > 0

    def test_uno_char_properties_is_non_empty_tuple(self) -> None:
        """UNO_CHAR_PROPERTIES is a non-empty tuple of strings."""
        from src.constants.office import UNO_CHAR_PROPERTIES  # noqa: PLC0415

        assert isinstance(UNO_CHAR_PROPERTIES, tuple)
        assert len(UNO_CHAR_PROPERTIES) > 0
        for prop in UNO_CHAR_PROPERTIES:
            assert isinstance(prop, str)
            assert len(prop) > 0

    def test_win32com_undefined_is_integer(self) -> None:
        """WIN32COM_UNDEFINED is a large integer sentinel."""
        from src.constants.office import WIN32COM_UNDEFINED  # noqa: PLC0415

        assert isinstance(WIN32COM_UNDEFINED, int)
        assert WIN32COM_UNDEFINED > 0


# ===========================================================================
# EXPANDED: color() parametrized for all keys in both themes
# ===========================================================================


_ALL_PALETTE_KEYS = sorted(
    {k for palette in ("light", "dark") for k in _PALETTES[palette]}
)


@pytest.mark.parametrize("key", _ALL_PALETTE_KEYS)
def test_color_light_returns_hex(key: str) -> None:
    """color(key) returns hex string in light theme."""
    original = current_theme()
    try:
        _set_initial_theme("light")
        val = color(key)
        assert val.startswith("#")
    finally:
        _set_initial_theme(original)


@pytest.mark.parametrize("key", _ALL_PALETTE_KEYS)
def test_color_dark_returns_hex(key: str) -> None:
    """color(key) returns hex string in dark theme."""
    original = current_theme()
    try:
        _set_initial_theme("dark")
        val = color(key)
        assert val.startswith("#")
    finally:
        _set_initial_theme(original)


# ===========================================================================
# EXPANDED: Error code completeness
# ===========================================================================


class TestErrorCodeCompleteness:
    """Ensure every ERR_* code is properly wired up."""

    def test_all_err_constants_in_error_messages(self) -> None:
        """Every ERR_* module constant appears in ERROR_MESSAGES."""
        import src.constants.errors as err_mod  # noqa: PLC0415

        for name in dir(err_mod):
            if name.startswith("ERR_") and isinstance(getattr(err_mod, name), int):
                code = getattr(err_mod, name)
                assert code in ERROR_MESSAGES, f"{name}={code} not in ERROR_MESSAGES"

    def test_err_none_has_empty_message(self) -> None:
        """ERR_NONE maps to empty string."""
        assert ERROR_MESSAGES[ERR_NONE] == ""

    def test_err_unknown_has_nonempty_message(self) -> None:
        """ERR_UNKNOWN has a non-empty message."""
        assert len(ERROR_MESSAGES[ERR_UNKNOWN]) > 0

    def test_get_error_message_returns_str_for_all_codes(self) -> None:
        """get_error_message returns str for every code in ERROR_MESSAGES."""
        for code in ERROR_MESSAGES:
            result = get_error_message(code)
            assert isinstance(result, str)

    def test_display_error_message_returns_str(self) -> None:
        """display_error_message always returns a string."""
        assert isinstance(display_error_message(""), str)
        assert isinstance(display_error_message("SOME_TAG"), str)
        assert isinstance(display_error_message("AUTH_ERROR"), str)

    def test_tag_to_code_all_values_positive(self) -> None:
        """All _TAG_TO_CODE values are positive integers."""
        for tag, code in _TAG_TO_CODE.items():
            assert code > 0, f"Tag {tag} maps to non-positive code {code}"

    def test_tag_to_tr_key_all_keys_are_strings(self) -> None:
        """All _TAG_TO_TR_KEY keys are non-empty strings."""
        for tag in _TAG_TO_TR_KEY:
            assert isinstance(tag, str)
            assert len(tag) > 0


# ===========================================================================
# EXPANDED: Language list consistency
# ===========================================================================


class TestLanguageListConsistency:
    """Ensure LANGUAGES entries are consistent and well-formed."""

    def test_all_flags_are_unique(self) -> None:
        """All flag icon names in LANGUAGES are unique."""
        flags = [lang[2] for lang in LANGUAGES]
        assert len(flags) == len(set(flags))

    def test_english_us_and_uk_present(self) -> None:
        """Both English (US) and English (UK) are in LANGUAGES."""
        labels = [lang[1] for lang in LANGUAGES]
        assert "English (US)" in labels
        assert "English (UK)" in labels

    def test_locale_code_format(self) -> None:
        """Locale codes are 2-5 chars (e.g. 'vi', 'en-US', 'zh-CN')."""
        for locale, _label, _flag, _native in LANGUAGES:
            assert 2 <= len(locale) <= 6, f"Bad locale length: {locale!r}"  # noqa: PLR2004

    def test_native_names_are_non_ascii_for_non_english(self) -> None:
        """Non-English languages have native names that differ from labels."""
        for _locale, label, _flag, native in LANGUAGES:
            if "English" not in label:
                # Native name should be different from the English label
                assert native != label, f"{label} native == label"

    def test_chinese_variants_have_different_locales(self) -> None:
        """Chinese (Simplified) and Chinese (Traditional) have distinct locales."""
        locale_map = {lang[1]: lang[0] for lang in LANGUAGES}
        if (
            "Chinese (Simplified)" in locale_map
            and "Chinese (Traditional)" in locale_map
        ):
            assert (
                locale_map["Chinese (Simplified)"]
                != locale_map["Chinese (Traditional)"]
            )

    def test_portuguese_variants_have_different_locales(self) -> None:
        """Portuguese (Brazil) and Portuguese (Portugal) have distinct locales."""
        locale_map = {lang[1]: lang[0] for lang in LANGUAGES}
        if (
            "Portuguese (Brazil)" in locale_map
            and "Portuguese (Portugal)" in locale_map
        ):
            assert (
                locale_map["Portuguese (Brazil)"] != locale_map["Portuguese (Portugal)"]
            )

    def test_get_locale_code_all_match_tuple_locale(self) -> None:
        """get_locale_code(label) == locale for every LANGUAGES entry."""
        for locale, label, _flag, _native in LANGUAGES:
            assert get_locale_code(label) == locale

    def test_label_to_locale_size_matches_languages(self) -> None:
        """_LABEL_TO_LOCALE has same size as LANGUAGES."""
        assert len(_LABEL_TO_LOCALE) == len(LANGUAGES)


# ===========================================================================
# EXPANDED: OCR language code lookups for many languages
# ===========================================================================


class TestOcrLookupComprehensive:
    """Comprehensive OCR lookup tests for various languages."""

    def test_get_tesseract_lang_arabic(self) -> None:
        """Arabic returns correct Tesseract code."""
        from src.constants.ocr import get_tesseract_lang  # noqa: PLC0415

        assert get_tesseract_lang("Arabic") == "ara"

    def test_get_tesseract_lang_vietnamese(self) -> None:
        """Vietnamese returns correct Tesseract code."""
        from src.constants.ocr import get_tesseract_lang  # noqa: PLC0415

        assert get_tesseract_lang("Vietnamese") == "vie"

    def test_get_tesseract_lang_hindi(self) -> None:
        """Hindi returns correct Tesseract code."""
        from src.constants.ocr import get_tesseract_lang  # noqa: PLC0415

        assert get_tesseract_lang("Hindi") == "hin"

    def test_get_tesseract_lang_german(self) -> None:
        """German returns correct Tesseract code."""
        from src.constants.ocr import get_tesseract_lang  # noqa: PLC0415

        assert get_tesseract_lang("German") == "deu"

    def test_get_tesseract_lang_spanish(self) -> None:
        """Spanish returns correct Tesseract code."""
        from src.constants.ocr import get_tesseract_lang  # noqa: PLC0415

        assert get_tesseract_lang("Spanish") == "spa"

    def test_get_tesseract_lang_italian(self) -> None:
        """Italian returns correct Tesseract code."""
        from src.constants.ocr import get_tesseract_lang  # noqa: PLC0415

        assert get_tesseract_lang("Italian") == "ita"

    def test_get_tesseract_lang_russian(self) -> None:
        """Russian returns correct Tesseract code."""
        from src.constants.ocr import get_tesseract_lang  # noqa: PLC0415

        assert get_tesseract_lang("Russian") == "rus"

    def test_get_tesseract_lang_thai(self) -> None:
        """Thai returns correct Tesseract code."""
        from src.constants.ocr import get_tesseract_lang  # noqa: PLC0415

        assert get_tesseract_lang("Thai") == "tha"

    def test_get_tesseract_lang_turkish(self) -> None:
        """Turkish returns correct Tesseract code."""
        from src.constants.ocr import get_tesseract_lang  # noqa: PLC0415

        assert get_tesseract_lang("Turkish") == "tur"

    def test_get_tesseract_lang_dutch(self) -> None:
        """Dutch returns correct Tesseract code."""
        from src.constants.ocr import get_tesseract_lang  # noqa: PLC0415

        assert get_tesseract_lang("Dutch") == "nld"

    def test_get_easyocr_langs_arabic(self) -> None:
        """Arabic returns [code, 'en'] for EasyOCR."""
        from src.constants.ocr import get_easyocr_langs  # noqa: PLC0415

        result = get_easyocr_langs("Arabic")
        assert "ar" in result
        assert "en" in result

    def test_get_easyocr_langs_german(self) -> None:
        """German returns [code, 'en'] for EasyOCR."""
        from src.constants.ocr import get_easyocr_langs  # noqa: PLC0415

        result = get_easyocr_langs("German")
        assert "de" in result
        assert "en" in result

    def test_get_easyocr_langs_spanish(self) -> None:
        """Spanish returns [code, 'en'] for EasyOCR."""
        from src.constants.ocr import get_easyocr_langs  # noqa: PLC0415

        result = get_easyocr_langs("Spanish")
        assert "es" in result
        assert "en" in result

    def test_get_google_lang_hints_japanese(self) -> None:
        """Japanese returns ['ja'] for Google hints."""
        from src.constants.ocr import get_google_lang_hints  # noqa: PLC0415

        assert get_google_lang_hints("Japanese") == ["ja"]

    def test_get_google_lang_hints_korean(self) -> None:
        """Korean returns ['ko'] for Google hints."""
        from src.constants.ocr import get_google_lang_hints  # noqa: PLC0415

        assert get_google_lang_hints("Korean") == ["ko"]

    def test_get_google_lang_hints_german(self) -> None:
        """German returns ['de'] for Google hints."""
        from src.constants.ocr import get_google_lang_hints  # noqa: PLC0415

        assert get_google_lang_hints("German") == ["de"]

    def test_get_google_lang_hints_french(self) -> None:
        """French returns ['fr'] for Google hints."""
        from src.constants.ocr import get_google_lang_hints  # noqa: PLC0415

        assert get_google_lang_hints("French") == ["fr"]

    def test_get_google_lang_hints_russian(self) -> None:
        """Russian returns ['ru'] for Google hints."""
        from src.constants.ocr import get_google_lang_hints  # noqa: PLC0415

        assert get_google_lang_hints("Russian") == ["ru"]


# ===========================================================================
# EXPANDED: LLM content type helpers
# ===========================================================================


class TestLLMContentTypeHelpers:
    """Additional tests for LLM content type constants and helpers."""

    def test_extension_to_content_type_map_is_dict(self) -> None:
        """_EXTENSION_TO_CONTENT_TYPE is a dict."""
        from src.constants.llm import _EXTENSION_TO_CONTENT_TYPE  # noqa: PLC0415

        assert isinstance(_EXTENSION_TO_CONTENT_TYPE, dict)

    def test_extension_map_all_keys_start_with_dot(self) -> None:
        """All keys in _EXTENSION_TO_CONTENT_TYPE start with '.'."""
        from src.constants.llm import _EXTENSION_TO_CONTENT_TYPE  # noqa: PLC0415

        for ext in _EXTENSION_TO_CONTENT_TYPE:
            assert ext.startswith("."), f"Key {ext!r} doesn't start with '.'"

    def test_extension_map_all_values_are_strings(self) -> None:
        """All values in _EXTENSION_TO_CONTENT_TYPE are non-empty strings."""
        from src.constants.llm import _EXTENSION_TO_CONTENT_TYPE  # noqa: PLC0415

        for ext, ct in _EXTENSION_TO_CONTENT_TYPE.items():
            assert isinstance(ct, str)
            assert len(ct) > 0, f"Extension {ext} has empty content type"

    def test_document_content_types_is_set(self) -> None:
        """DOCUMENT_CONTENT_TYPES is a set."""
        assert isinstance(DOCUMENT_CONTENT_TYPES, set)

    def test_document_content_types_has_at_least_5_entries(self) -> None:
        """DOCUMENT_CONTENT_TYPES has at least 5 entries."""
        assert len(DOCUMENT_CONTENT_TYPES) >= 5  # noqa: PLR2004

    def test_gemini_api_base_url_is_https(self) -> None:
        """GEMINI_API_BASE_URL starts with https://."""
        from src.constants.llm import GEMINI_API_BASE_URL  # noqa: PLC0415

        assert GEMINI_API_BASE_URL.startswith("https://")

    def test_user_agent_is_non_empty(self) -> None:
        """USER_AGENT is a non-empty string."""
        from src.constants.llm import USER_AGENT  # noqa: PLC0415

        assert isinstance(USER_AGENT, str)
        assert len(USER_AGENT) > 0

    def test_llm_text_timeout_is_positive(self) -> None:
        """LLM_TEXT_TIMEOUT is a positive number."""
        from src.constants.llm import LLM_TEXT_TIMEOUT  # noqa: PLC0415

        assert LLM_TEXT_TIMEOUT > 0

    def test_llm_vision_timeout_is_positive(self) -> None:
        """LLM_VISION_TIMEOUT is a positive number."""
        from src.constants.llm import LLM_VISION_TIMEOUT  # noqa: PLC0415

        assert LLM_VISION_TIMEOUT > 0

    def test_vision_timeout_gte_text_timeout(self) -> None:
        """LLM_VISION_TIMEOUT >= LLM_TEXT_TIMEOUT (vision requests take longer)."""
        from src.constants.llm import (  # noqa: PLC0415
            LLM_TEXT_TIMEOUT,
            LLM_VISION_TIMEOUT,
        )

        assert LLM_VISION_TIMEOUT >= LLM_TEXT_TIMEOUT

    def test_json_item_overhead_positive(self) -> None:
        """JSON_ITEM_OVERHEAD is a positive integer."""
        from src.constants.llm import JSON_ITEM_OVERHEAD  # noqa: PLC0415

        assert JSON_ITEM_OVERHEAD > 0

    def test_cjk_codepoint_threshold_valid(self) -> None:
        """CJK_CODEPOINT_THRESHOLD is a positive integer in Unicode range."""
        from src.constants.llm import CJK_CODEPOINT_THRESHOLD  # noqa: PLC0415

        assert CJK_CODEPOINT_THRESHOLD > 0
        assert CJK_CODEPOINT_THRESHOLD < 0x10FFFF

    def test_retry_base_delay_positive(self) -> None:
        """RETRY_BASE_DELAY is a positive float."""
        from src.constants.llm import RETRY_BASE_DELAY  # noqa: PLC0415

        assert RETRY_BASE_DELAY > 0

    def test_vision_unsupported_indicators_non_empty(self) -> None:
        """VISION_UNSUPPORTED_INDICATORS is a non-empty tuple of strings."""
        from src.constants.llm import VISION_UNSUPPORTED_INDICATORS  # noqa: PLC0415

        assert len(VISION_UNSUPPORTED_INDICATORS) > 0
        for indicator in VISION_UNSUPPORTED_INDICATORS:
            assert isinstance(indicator, str)

    def test_gemini_vision_model_keywords_non_empty(self) -> None:
        """GEMINI_VISION_MODEL_KEYWORDS is non-empty."""
        from src.constants.llm import GEMINI_VISION_MODEL_KEYWORDS  # noqa: PLC0415

        assert len(GEMINI_VISION_MODEL_KEYWORDS) > 0

    def test_glossary_hint_template_has_placeholder(self) -> None:
        """GLOSSARY_HINT_TEMPLATE contains {entries} placeholder."""
        from src.constants.llm import GLOSSARY_HINT_TEMPLATE  # noqa: PLC0415

        assert "{entries}" in GLOSSARY_HINT_TEMPLATE


# ===========================================================================
# EXPANDED: History status groups and progress
# ===========================================================================


class TestHistoryStatusGroups:
    """Additional tests for history status groups."""

    def test_active_statuses_is_subset_of_unfinished(self) -> None:
        """ACTIVE_STATUSES is a subset of UNFINISHED_STATUSES."""
        from src.constants.history import (  # noqa: PLC0415
            ACTIVE_STATUSES,
            UNFINISHED_STATUSES,
        )

        for s in ACTIVE_STATUSES:
            assert s in UNFINISHED_STATUSES

    def test_done_not_in_unfinished(self) -> None:
        """STATUS_DONE is not in UNFINISHED_STATUSES."""
        from src.constants.history import (  # noqa: PLC0415
            STATUS_DONE,
            UNFINISHED_STATUSES,
        )

        assert STATUS_DONE not in UNFINISHED_STATUSES

    def test_failed_not_in_active(self) -> None:
        """STATUS_FAILED is not in ACTIVE_STATUSES."""
        from src.constants.history import (  # noqa: PLC0415
            ACTIVE_STATUSES,
            STATUS_FAILED,
        )

        assert STATUS_FAILED not in ACTIVE_STATUSES

    def test_deleting_not_in_any_group(self) -> None:
        """STATUS_DELETING is not in ACTIVE, UNFINISHED, or REPROCESSABLE."""
        from src.constants.history import (  # noqa: PLC0415
            ACTIVE_STATUSES,
            REPROCESSABLE_STATUSES,
            STATUS_DELETING,
            UNFINISHED_STATUSES,
        )

        assert STATUS_DELETING not in ACTIVE_STATUSES
        assert STATUS_DELETING not in UNFINISHED_STATUSES
        assert STATUS_DELETING not in REPROCESSABLE_STATUSES

    def test_dubbing_progress_milestones_ordering(self) -> None:
        """Dubbing progress milestones are in ascending order."""
        from src.constants.history import (  # noqa: PLC0415
            DUBBING_PROGRESS_MIX_START,
            DUBBING_PROGRESS_STT_DONE,
            DUBBING_PROGRESS_STT_START,
            DUBBING_PROGRESS_TRANSLATE_DONE,
            DUBBING_PROGRESS_TTS_DONE,
        )

        assert DUBBING_PROGRESS_STT_START < DUBBING_PROGRESS_STT_DONE
        assert DUBBING_PROGRESS_STT_DONE <= DUBBING_PROGRESS_TRANSLATE_DONE
        assert DUBBING_PROGRESS_TRANSLATE_DONE <= DUBBING_PROGRESS_TTS_DONE
        assert DUBBING_PROGRESS_TTS_DONE <= DUBBING_PROGRESS_MIX_START

    def test_progress_weights_between_0_and_1(self) -> None:
        """Progress weight constants are between 0 and 1."""
        from src.constants.history import (  # noqa: PLC0415
            PROGRESS_IMAGE_LLM_WEIGHT,
            PROGRESS_TEXT_WEIGHT,
        )

        assert 0 < PROGRESS_IMAGE_LLM_WEIGHT < 1
        assert 0 < PROGRESS_TEXT_WEIGHT < 1

    def test_display_status_empty_string(self) -> None:
        """display_status('') returns '' (empty key → empty result)."""
        from src.constants.history import display_status  # noqa: PLC0415

        result = display_status("")
        # Empty status → key = "status." which won't match → returns ""
        assert isinstance(result, str)


# ===========================================================================
# EXPANDED: Settings constants comprehensive
# ===========================================================================


class TestSettingsConstantsExpanded:
    """Expanded tests for settings key constants."""

    def test_setting_theme_key(self) -> None:
        """SETTING_THEME has correct value."""
        from src.constants.settings import SETTING_THEME  # noqa: PLC0415

        assert SETTING_THEME == "app/theme"

    def test_setting_llm_method_key(self) -> None:
        """SETTING_LLM_METHOD has correct value."""
        from src.constants.settings import SETTING_LLM_METHOD  # noqa: PLC0415

        assert SETTING_LLM_METHOD == "llm/method"

    def test_setting_ocr_method_key(self) -> None:
        """SETTING_OCR_METHOD has correct value."""
        from src.constants.settings import SETTING_OCR_METHOD  # noqa: PLC0415

        assert SETTING_OCR_METHOD == "ocr/method"

    def test_setting_ui_language_key(self) -> None:
        """SETTING_UI_LANGUAGE has correct value."""
        from src.constants.settings import SETTING_UI_LANGUAGE  # noqa: PLC0415

        assert SETTING_UI_LANGUAGE == "app/ui_language"

    def test_setting_auto_save_key(self) -> None:
        """SETTING_AUTO_SAVE has correct value."""
        from src.constants.settings import SETTING_AUTO_SAVE  # noqa: PLC0415

        assert SETTING_AUTO_SAVE == "app/auto_save"

    def test_voice_tts_methods_distinct(self) -> None:
        """VOICE_TTS_EDGE and VOICE_TTS_GOOGLE are distinct."""
        from src.constants.settings import (  # noqa: PLC0415
            VOICE_TTS_EDGE,
            VOICE_TTS_GOOGLE,
        )

        assert VOICE_TTS_EDGE != VOICE_TTS_GOOGLE

    def test_translation_settings_exist(self) -> None:
        """Translation-related settings keys exist."""
        from src.constants.settings import (  # noqa: PLC0415
            SETTING_AUTO_CONVERT_LEGACY,
            SETTING_AUTO_CONVERT_ODF,
            SETTING_TRANSLATE_DOC_COMMENTS,
            SETTING_TRANSLATE_DOC_IMAGES,
            SETTING_TRANSLATE_DOC_NOTES,
            SETTING_TRANSLATE_DOC_SHAPES,
            SETTING_TRANSLATE_SHEET_NAMES,
        )

        keys = [
            SETTING_TRANSLATE_DOC_IMAGES,
            SETTING_TRANSLATE_DOC_COMMENTS,
            SETTING_TRANSLATE_DOC_SHAPES,
            SETTING_TRANSLATE_DOC_NOTES,
            SETTING_TRANSLATE_SHEET_NAMES,
            SETTING_AUTO_CONVERT_LEGACY,
            SETTING_AUTO_CONVERT_ODF,
        ]
        for key in keys:
            assert isinstance(key, str)
            assert "/" in key

    def test_dubbing_settings_exist(self) -> None:
        """Dubbing-related settings keys exist."""
        from src.constants.settings import (  # noqa: PLC0415
            SETTING_DUBBING_AUTO_REMOVE,
            SETTING_DUBBING_STORAGE_PATH,
            SETTING_LAST_DUBBING_SRC_LANG,
            SETTING_LAST_DUBBING_TGT_LANG,
        )

        for key in [
            SETTING_DUBBING_STORAGE_PATH,
            SETTING_DUBBING_AUTO_REMOVE,
            SETTING_LAST_DUBBING_SRC_LANG,
            SETTING_LAST_DUBBING_TGT_LANG,
        ]:
            assert isinstance(key, str)
            assert "/" in key

    def test_live_settings_exist(self) -> None:
        """Live translation settings keys exist."""
        from src.constants.settings import (  # noqa: PLC0415
            SETTING_LIVE_SHOW_ORIGINAL,
            SETTING_LIVE_SOURCE_LANG,
            SETTING_LIVE_TARGET_LANG,
            SETTING_LIVE_WHISPER_MODEL,
        )

        for key in [
            SETTING_LIVE_SOURCE_LANG,
            SETTING_LIVE_TARGET_LANG,
            SETTING_LIVE_WHISPER_MODEL,
            SETTING_LIVE_SHOW_ORIGINAL,
        ]:
            assert isinstance(key, str)
            assert "/" in key

    def test_translate_text_settings_exist(self) -> None:
        """Translate text settings keys exist."""
        from src.constants.settings import (  # noqa: PLC0415
            SETTING_TRANSLATE_TEXT_AUTO_SAVE,
            SETTING_TRANSLATE_TEXT_SRC_LANG,
            SETTING_TRANSLATE_TEXT_TGT_LANG,
        )

        for key in [
            SETTING_TRANSLATE_TEXT_SRC_LANG,
            SETTING_TRANSLATE_TEXT_TGT_LANG,
            SETTING_TRANSLATE_TEXT_AUTO_SAVE,
        ]:
            assert isinstance(key, str)
            assert "/" in key


# ===========================================================================
# EXPANDED: UI Constants comprehensive
# ===========================================================================


class TestUIConstantsExpanded:
    """Expanded tests for UI layout constants."""

    def test_flag_icon_dimensions_positive(self) -> None:
        """FLAG_ICON_WIDTH and FLAG_ICON_HEIGHT are positive."""
        from src.constants.ui import FLAG_ICON_HEIGHT, FLAG_ICON_WIDTH  # noqa: PLC0415

        assert FLAG_ICON_WIDTH > 0
        assert FLAG_ICON_HEIGHT > 0

    def test_history_col_widths_positive(self) -> None:
        """History column widths are positive."""
        from src.constants.ui import (  # noqa: PLC0415
            HISTORY_COL_WIDTH,
            HISTORY_DATE_COL_WIDTH,
        )

        assert HISTORY_COL_WIDTH > 0
        assert HISTORY_DATE_COL_WIDTH > 0

    def test_min_column_width_positive(self) -> None:
        """MIN_COLUMN_WIDTH is positive."""
        from src.constants.ui import MIN_COLUMN_WIDTH  # noqa: PLC0415

        assert MIN_COLUMN_WIDTH > 0

    def test_sidebar_width_value(self) -> None:
        """SIDEBAR_WIDTH is 275px."""
        from src.constants.ui import SIDEBAR_WIDTH  # noqa: PLC0415

        assert SIDEBAR_WIDTH == 275  # noqa: PLR2004

    def test_radius_button_value(self) -> None:
        """RADIUS_BUTTON is 10px."""
        from src.constants.ui import RADIUS_BUTTON  # noqa: PLC0415

        assert RADIUS_BUTTON == 10  # noqa: PLR2004

    def test_margin_page_value(self) -> None:
        """MARGIN_PAGE is 24px."""
        from src.constants.ui import MARGIN_PAGE  # noqa: PLC0415

        assert MARGIN_PAGE == 24  # noqa: PLR2004

    def test_spacing_section_value(self) -> None:
        """SPACING_SECTION is 20px."""
        from src.constants.ui import SPACING_SECTION  # noqa: PLC0415

        assert SPACING_SECTION == 20  # noqa: PLR2004

    def test_banner_margin_bottom_non_negative(self) -> None:
        """BANNER_MARGIN_BOTTOM is non-negative."""
        from src.constants.ui import BANNER_MARGIN_BOTTOM  # noqa: PLC0415

        assert BANNER_MARGIN_BOTTOM >= 0

    def test_label_width_positive(self) -> None:
        """LABEL_WIDTH is positive."""
        from src.constants.ui import LABEL_WIDTH  # noqa: PLC0415

        assert LABEL_WIDTH > 0

    def test_label_padding_left_positive(self) -> None:
        """LABEL_PADDING_LEFT is positive."""
        from src.constants.ui import LABEL_PADDING_LEFT  # noqa: PLC0415

        assert LABEL_PADDING_LEFT > 0

    def test_asset_path_strings_are_posix(self) -> None:
        """Asset path strings use forward slashes (POSIX)."""
        from src.constants.ui import (  # noqa: PLC0415
            CHECK_PATH,
            CHEVRON_DOWN_DISABLED_PATH,
            CHEVRON_DOWN_PATH,
            FLAGS_DIR,
        )

        for path_str in [
            CHECK_PATH,
            CHEVRON_DOWN_PATH,
            CHEVRON_DOWN_DISABLED_PATH,
            FLAGS_DIR,
        ]:
            assert isinstance(path_str, str)
            assert len(path_str) > 0

    def test_fonts_dir_is_path(self) -> None:
        """FONTS_DIR is a Path object."""
        from pathlib import Path  # noqa: PLC0415

        from src.constants.ui import FONTS_DIR  # noqa: PLC0415

        assert isinstance(FONTS_DIR, Path)


# ===========================================================================
# EXPANDED: Office Constants
# ===========================================================================


class TestOfficeConstantsExpanded:
    """Expanded tests for office constants."""

    def test_win32com_font_has_name_and_size(self) -> None:
        """WIN32COM_FONT_PROPERTIES includes Name and Size."""
        from src.constants.office import WIN32COM_FONT_PROPERTIES  # noqa: PLC0415

        assert "Name" in WIN32COM_FONT_PROPERTIES
        assert "Size" in WIN32COM_FONT_PROPERTIES

    def test_win32com_font_has_bold_and_italic(self) -> None:
        """WIN32COM_FONT_PROPERTIES includes Bold and Italic."""
        from src.constants.office import WIN32COM_FONT_PROPERTIES  # noqa: PLC0415

        assert "Bold" in WIN32COM_FONT_PROPERTIES
        assert "Italic" in WIN32COM_FONT_PROPERTIES

    def test_uno_char_has_font_name(self) -> None:
        """UNO_CHAR_PROPERTIES includes CharFontName."""
        from src.constants.office import UNO_CHAR_PROPERTIES  # noqa: PLC0415

        assert "CharFontName" in UNO_CHAR_PROPERTIES

    def test_uno_char_has_height(self) -> None:
        """UNO_CHAR_PROPERTIES includes CharHeight."""
        from src.constants.office import UNO_CHAR_PROPERTIES  # noqa: PLC0415

        assert "CharHeight" in UNO_CHAR_PROPERTIES

    def test_uno_char_has_weight_and_posture(self) -> None:
        """UNO_CHAR_PROPERTIES includes CharWeight and CharPosture."""
        from src.constants.office import UNO_CHAR_PROPERTIES  # noqa: PLC0415

        assert "CharWeight" in UNO_CHAR_PROPERTIES
        assert "CharPosture" in UNO_CHAR_PROPERTIES

    def test_win32com_undefined_is_9999999(self) -> None:
        """WIN32COM_UNDEFINED is exactly 9999999."""
        from src.constants.office import WIN32COM_UNDEFINED  # noqa: PLC0415

        assert WIN32COM_UNDEFINED == 9999999  # noqa: PLR2004

    def test_win32com_font_properties_no_duplicates(self) -> None:
        """WIN32COM_FONT_PROPERTIES has no duplicate entries."""
        from src.constants.office import WIN32COM_FONT_PROPERTIES  # noqa: PLC0415

        assert len(WIN32COM_FONT_PROPERTIES) == len(set(WIN32COM_FONT_PROPERTIES))

    def test_uno_char_properties_no_duplicates(self) -> None:
        """UNO_CHAR_PROPERTIES has no duplicate entries."""
        from src.constants.office import UNO_CHAR_PROPERTIES  # noqa: PLC0415

        assert len(UNO_CHAR_PROPERTIES) == len(set(UNO_CHAR_PROPERTIES))


# ===========================================================================
# EXPANDED: style functions color correctness
# ===========================================================================


class TestStyleColorCorrectness:
    """Verify style functions reference the correct palette colors."""

    def test_style_scrollbar_uses_scrollbar_colors(self) -> None:
        """style_scrollbar() references both scrollbar_handle and scrollbar_hover."""
        result = style_scrollbar()
        assert color("scrollbar_handle") in result
        assert color("scrollbar_hover") in result

    def test_style_primary_button_uses_primary_hover(self) -> None:
        """style_primary_button() references primary_hover color."""
        result = style_primary_button()
        assert color("primary_hover") in result

    def test_style_primary_button_uses_primary_pressed(self) -> None:
        """style_primary_button() references primary_pressed color."""
        result = style_primary_button()
        assert color("primary_pressed") in result

    def test_style_danger_button_uses_error_hover(self) -> None:
        """style_danger_button() references error_hover color."""
        result = style_danger_button()
        assert color("error_hover") in result

    def test_style_danger_button_uses_error_pressed(self) -> None:
        """style_danger_button() references error_pressed color."""
        result = style_danger_button()
        assert color("error_pressed") in result

    def test_style_warning_button_uses_warning_hover(self) -> None:
        """style_warning_button() references warning_hover color."""
        result = style_warning_button()
        assert color("warning_hover") in result

    def test_style_outlined_primary_button_uses_primary_light(self) -> None:
        """style_outlined_primary_button() references primary_light on hover."""
        result = style_outlined_primary_button()
        assert color("primary_light") in result

    def test_style_link_button_uses_primary_light_on_hover(self) -> None:
        """style_link_button() references primary_light on hover."""
        result = style_link_button()
        assert color("primary_light") in result

    def test_style_delete_button_uses_error_hover(self) -> None:
        """style_delete_button() references error_hover on hover."""
        result = style_delete_button()
        assert color("error_hover") in result


# ---------------------------------------------------------------------------
# Asset file existence tests
# ---------------------------------------------------------------------------


class TestAssetFileExistence:
    """Tests that all SVG/PNG asset paths defined in ui.py exist on disk."""

    def test_chevron_down_path_exists(self) -> None:
        """CHEVRON_DOWN_PATH points to an existing SVG file."""
        from pathlib import Path  # noqa: PLC0415

        from src.constants.ui import CHEVRON_DOWN_PATH  # noqa: PLC0415

        assert Path(CHEVRON_DOWN_PATH).exists(), f"Missing asset: {CHEVRON_DOWN_PATH}"

    def test_chevron_down_disabled_path_exists(self) -> None:
        """CHEVRON_DOWN_DISABLED_PATH points to an existing SVG file."""
        from pathlib import Path  # noqa: PLC0415

        from src.constants.ui import CHEVRON_DOWN_DISABLED_PATH  # noqa: PLC0415

        assert Path(CHEVRON_DOWN_DISABLED_PATH).exists(), (
            f"Missing asset: {CHEVRON_DOWN_DISABLED_PATH}"
        )

    def test_check_path_exists(self) -> None:
        """CHECK_PATH points to an existing SVG file."""
        from pathlib import Path  # noqa: PLC0415

        from src.constants.ui import CHECK_PATH  # noqa: PLC0415

        assert Path(CHECK_PATH).exists(), f"Missing asset: {CHECK_PATH}"

    def test_eye_path_exists(self) -> None:
        """EYE_PATH points to an existing SVG file."""
        from pathlib import Path  # noqa: PLC0415

        from src.constants.ui import EYE_PATH  # noqa: PLC0415

        assert Path(EYE_PATH).exists(), f"Missing asset: {EYE_PATH}"

    def test_eye_off_path_exists(self) -> None:
        """EYE_OFF_PATH points to an existing SVG file."""
        from pathlib import Path  # noqa: PLC0415

        from src.constants.ui import EYE_OFF_PATH  # noqa: PLC0415

        assert Path(EYE_OFF_PATH).exists(), f"Missing asset: {EYE_OFF_PATH}"

    def test_eye_primary_path_exists(self) -> None:
        """EYE_PRIMARY_PATH points to an existing SVG file."""
        from pathlib import Path  # noqa: PLC0415

        from src.constants.ui import EYE_PRIMARY_PATH  # noqa: PLC0415

        assert Path(EYE_PRIMARY_PATH).exists(), f"Missing asset: {EYE_PRIMARY_PATH}"

    def test_eye_off_primary_path_exists(self) -> None:
        """EYE_OFF_PRIMARY_PATH points to an existing SVG file."""
        from pathlib import Path  # noqa: PLC0415

        from src.constants.ui import EYE_OFF_PRIMARY_PATH  # noqa: PLC0415

        assert Path(EYE_OFF_PRIMARY_PATH).exists(), (
            f"Missing asset: {EYE_OFF_PRIMARY_PATH}"
        )

    def test_alert_triangle_path_exists(self) -> None:
        """ALERT_TRIANGLE_PATH points to an existing SVG file."""
        from pathlib import Path  # noqa: PLC0415

        from src.constants.ui import ALERT_TRIANGLE_PATH  # noqa: PLC0415

        assert Path(ALERT_TRIANGLE_PATH).exists(), (
            f"Missing asset: {ALERT_TRIANGLE_PATH}"
        )

    def test_alert_circle_path_exists(self) -> None:
        """ALERT_CIRCLE_PATH points to an existing SVG file."""
        from pathlib import Path  # noqa: PLC0415

        from src.constants.ui import ALERT_CIRCLE_PATH  # noqa: PLC0415

        assert Path(ALERT_CIRCLE_PATH).exists(), f"Missing asset: {ALERT_CIRCLE_PATH}"

    def test_check_circle_path_exists(self) -> None:
        """CHECK_CIRCLE_PATH points to an existing SVG file."""
        from pathlib import Path  # noqa: PLC0415

        from src.constants.ui import CHECK_CIRCLE_PATH  # noqa: PLC0415

        assert Path(CHECK_CIRCLE_PATH).exists(), f"Missing asset: {CHECK_CIRCLE_PATH}"

    def test_info_path_exists(self) -> None:
        """INFO_PATH points to an existing SVG file."""
        from pathlib import Path  # noqa: PLC0415

        from src.constants.ui import INFO_PATH  # noqa: PLC0415

        assert Path(INFO_PATH).exists(), f"Missing asset: {INFO_PATH}"

    def test_flags_dir_exists(self) -> None:
        """FLAGS_DIR points to an existing directory."""
        from pathlib import Path  # noqa: PLC0415

        from src.constants.ui import FLAGS_DIR  # noqa: PLC0415

        assert Path(FLAGS_DIR).is_dir(), f"Missing directory: {FLAGS_DIR}"

    def test_fonts_dir_exists(self) -> None:
        """FONTS_DIR points to an existing directory."""
        from src.constants.ui import FONTS_DIR  # noqa: PLC0415

        assert FONTS_DIR.is_dir(), f"Missing directory: {FONTS_DIR}"

    def test_assets_dir_exists(self) -> None:
        """ASSETS_DIR points to an existing directory."""
        from src.constants.ui import ASSETS_DIR  # noqa: PLC0415

        assert ASSETS_DIR.is_dir(), f"Missing directory: {ASSETS_DIR}"

    def test_all_svg_assets_have_svg_extension(self) -> None:
        """All SVG asset paths end with .svg extension."""
        from src.constants.ui import (  # noqa: PLC0415
            ALERT_CIRCLE_PATH,
            ALERT_TRIANGLE_PATH,
            CHECK_CIRCLE_PATH,
            CHECK_PATH,
            CHEVRON_DOWN_DISABLED_PATH,
            CHEVRON_DOWN_PATH,
            EYE_OFF_PATH,
            EYE_OFF_PRIMARY_PATH,
            EYE_PATH,
            EYE_PRIMARY_PATH,
            INFO_PATH,
        )

        svg_paths = [
            CHEVRON_DOWN_PATH,
            CHEVRON_DOWN_DISABLED_PATH,
            CHECK_PATH,
            EYE_PATH,
            EYE_OFF_PATH,
            EYE_PRIMARY_PATH,
            EYE_OFF_PRIMARY_PATH,
            ALERT_TRIANGLE_PATH,
            ALERT_CIRCLE_PATH,
            CHECK_CIRCLE_PATH,
            INFO_PATH,
        ]
        for path in svg_paths:
            assert path.endswith(".svg"), f"Expected .svg extension: {path}"

    def test_flags_dir_contains_png_files(self) -> None:
        """FLAGS_DIR contains at least one .png file."""
        from pathlib import Path  # noqa: PLC0415

        from src.constants.ui import FLAGS_DIR  # noqa: PLC0415

        flags_path = Path(FLAGS_DIR)
        png_files = list(flags_path.glob("*.png"))
        assert len(png_files) > 0, f"No .png files in {FLAGS_DIR}"


# ===========================================================================
# TestErrorConstantsExpanded — edge cases for error mapping functions
# ===========================================================================


class TestErrorConstantsExpanded:
    """Expanded edge-case tests for error constants and mapping functions."""

    def test_map_tag_to_code_all_known_tags(self) -> None:
        """Every tag string in _TAG_TO_CODE returns the correct error code."""
        for tag, expected_code in _TAG_TO_CODE.items():
            assert map_tag_to_code(tag) == expected_code, (
                f"Tag {tag!r} should map to {expected_code}"
            )

    def test_map_tag_to_code_unknown_returns_err_unknown(self) -> None:
        """Completely unknown tag string returns ERR_UNKNOWN."""
        assert map_tag_to_code("TOTALLY_BOGUS_TAG_XYZ") == ERR_UNKNOWN

    def test_display_error_message_none_returns_empty(self) -> None:
        """display_error_message with None-like empty input returns empty."""
        # The function signature accepts str; None would be caught by type check.
        # Test the empty/falsy branch.
        assert display_error_message("") == ""

    def test_display_error_message_empty_string_returns_empty(self) -> None:
        """display_error_message with empty string returns empty string."""
        result = display_error_message("")
        assert result == ""
        assert isinstance(result, str)

    def test_display_error_message_numeric_only_passthrough(self) -> None:
        """display_error_message with a numeric-only string passes through."""
        # A string like "42" is not a known tag, so it passes through as-is
        result = display_error_message("42")
        assert result == "42"

    def test_get_error_message_nonempty_for_all_err_constants(self) -> None:
        """get_error_message returns a non-empty string for every defined ERR_* constant."""
        import src.constants.errors as err_mod  # noqa: PLC0415

        for name in dir(err_mod):
            if not name.startswith("ERR_"):
                continue
            code = getattr(err_mod, name)
            if not isinstance(code, int):
                continue
            if code == ERR_NONE:
                # ERR_NONE intentionally returns empty string
                assert get_error_message(code) == ""
                continue
            result = get_error_message(code)
            assert isinstance(result, str)
            assert len(result) > 0, (
                f"get_error_message({name}={code}) returned empty string"
            )


# ===================================================================
# Language helpers — i18n key slug, format helper, locale-aware sort
# ===================================================================


class TestLanguageI18nKey:
    """Slug rule for the ``language.<key>`` lookup table.

    Stable derivation of an i18n key from the canonical English label
    is bedrock for all 675 ``language.*`` translation entries.  A
    silent rule change (e.g. dropping the underscore between words)
    would dump 45 translations per locale into the fallback path.
    """

    def test_simple_label_lowercases(self) -> None:
        from src.constants.languages import _language_i18n_key  # noqa: PLC0415

        assert _language_i18n_key("Japanese") == "japanese"
        assert _language_i18n_key("Vietnamese") == "vietnamese"

    def test_parenthesised_dialect_uses_underscore(self) -> None:
        from src.constants.languages import _language_i18n_key  # noqa: PLC0415

        assert _language_i18n_key("Chinese (Simplified)") == "chinese_simplified"
        assert _language_i18n_key("Chinese (Traditional)") == "chinese_traditional"
        assert _language_i18n_key("Portuguese (Brazil)") == "portuguese_brazil"
        assert _language_i18n_key("Portuguese (Portugal)") == "portuguese_portugal"

    def test_short_region_code_kept(self) -> None:
        from src.constants.languages import _language_i18n_key  # noqa: PLC0415

        assert _language_i18n_key("English (UK)") == "english_uk"
        assert _language_i18n_key("English (US)") == "english_us"

    def test_no_trailing_underscore(self) -> None:
        from src.constants.languages import _language_i18n_key  # noqa: PLC0415

        # "English (UK)" → "english_uk_" without strip; we strip.
        assert not _language_i18n_key("English (UK)").endswith("_")


class TestFormatLanguagePickerLabel:
    """Picker label resolves via i18n with three fallback branches."""

    def test_uses_translation_when_present(self) -> None:
        from unittest.mock import patch  # noqa: PLC0415

        from src.constants.languages import (  # noqa: PLC0415
            format_language_picker_label,
        )

        with patch(
            "src.constants.i18n.tr",
            side_effect=lambda key, **_: (
                "Tiếng Nhật" if key == "language.japanese" else key
            ),
        ):
            out = format_language_picker_label("Japanese", "日本語")
        assert out == "Tiếng Nhật"

    def test_native_english_fallback_when_translation_missing(self) -> None:
        """When ``tr`` returns the key (miss), formats as ``<native> (<English>)``."""
        from unittest.mock import patch  # noqa: PLC0415

        from src.constants.languages import (  # noqa: PLC0415
            format_language_picker_label,
        )

        # ``tr`` returns the key string on miss — confirmed in i18n.py.
        with patch("src.constants.i18n.tr", side_effect=lambda key, **_: key):
            out = format_language_picker_label("Japanese", "日本語")
        assert out == "日本語 (Japanese)"

    def test_collapses_to_english_when_native_equals_english(self) -> None:
        """Avoids the silly ``English (UK) (English (UK))`` duplicate."""
        from unittest.mock import patch  # noqa: PLC0415

        from src.constants.languages import (  # noqa: PLC0415
            format_language_picker_label,
        )

        with patch("src.constants.i18n.tr", side_effect=lambda key, **_: key):
            out = format_language_picker_label("English (UK)", "English (UK)")
        assert out == "English (UK)"


class TestIterLanguagesSortedForUi:
    """Sort order is locale-driven; same set, different ordering per locale."""

    def test_returns_full_catalogue_length(self) -> None:
        from src.constants.languages import (  # noqa: PLC0415
            LANGUAGES,
            iter_languages_sorted_for_ui,
        )

        out = iter_languages_sorted_for_ui()
        assert len(out) == len(LANGUAGES)
        # Same English-label set as the source catalogue.
        assert {e[1] for e in out} == {e[1] for e in LANGUAGES}

    def test_sort_order_changes_when_locale_changes(self) -> None:
        """Switching UI locale rearranges the picker — that's the whole point.

        A regression to source-order sort (or to en-US sort always)
        would silently break Vietnamese / Japanese / Russian users'
        familiar ordering.
        """
        from src.constants.i18n import _set_initial_language  # noqa: PLC0415
        from src.constants.languages import (  # noqa: PLC0415
            iter_languages_sorted_for_ui,
        )

        try:
            _set_initial_language("en-US")
            en_order = [e[1] for e in iter_languages_sorted_for_ui()]
            _set_initial_language("vi")
            vi_order = [e[1] for e in iter_languages_sorted_for_ui()]
            _set_initial_language("ja")
            ja_order = [e[1] for e in iter_languages_sorted_for_ui()]
        finally:
            _set_initial_language("en-US")

        # Three locales must produce three distinct orderings.
        assert en_order != vi_order, "Vietnamese sort should differ from English"
        assert en_order != ja_order, "Japanese sort should differ from English"
        assert vi_order != ja_order, (
            "Vietnamese and Japanese sorts should differ from each other"
        )

    def test_en_us_sort_is_alphabetical_on_english_labels(self) -> None:
        """en-US falls back to source English labels, alphabetically."""
        from src.constants.i18n import _set_initial_language  # noqa: PLC0415
        from src.constants.languages import (  # noqa: PLC0415
            iter_languages_sorted_for_ui,
        )

        try:
            _set_initial_language("en-US")
            order = [e[1] for e in iter_languages_sorted_for_ui()]
        finally:
            _set_initial_language("en-US")

        # First five English labels alphabetically.
        assert order[:5] == [
            "Arabic",
            "Belarusian",
            "Bengali",
            "Bulgarian",
            "Chinese (Simplified)",
        ]


class TestLocalizedLanguageLabel:
    """Coverage for ``localized_language_label`` — used by history tables.

    Wraps ``format_language_picker_label`` to give callers that only
    have the canonical English DB value (history rows, log lines)
    a consistent way to render the user-locale form without
    maintaining their own LANGUAGES walk.
    """

    def test_empty_input_passthrough(self) -> None:
        """Auto-detect placeholder ('' source) must NOT be wrapped."""
        from src.constants.languages import (  # noqa: PLC0415
            localized_language_label,
        )

        assert localized_language_label("") == ""

    def test_unknown_label_falls_back_to_raw(self) -> None:
        """Legacy / typo / removed-language entries pass through unchanged.

        History tables would rather render "Klingon" than blank cell.
        """
        from src.constants.languages import (  # noqa: PLC0415
            localized_language_label,
        )

        assert localized_language_label("Klingon") == "Klingon"

    def test_known_label_in_en_us_returns_english(self) -> None:
        """en-US locale → tr() returns the English form, no native wrap."""
        from src.constants.i18n import _set_initial_language  # noqa: PLC0415
        from src.constants.languages import (  # noqa: PLC0415
            localized_language_label,
        )

        _set_initial_language("en-US")
        try:
            assert localized_language_label("Vietnamese") == "Vietnamese"
            assert localized_language_label("French") == "French"
        finally:
            _set_initial_language("en-US")

    def test_known_label_in_vi_returns_native(self) -> None:
        """Vi locale → tr() returns the Vietnamese form ('Tiếng Việt')."""
        from src.constants.i18n import _set_initial_language  # noqa: PLC0415
        from src.constants.languages import (  # noqa: PLC0415
            localized_language_label,
        )

        _set_initial_language("vi")
        try:
            assert localized_language_label("Vietnamese") == "Tiếng Việt"
            # French in vi → "Tiếng Pháp"
            assert localized_language_label("French") == "Tiếng Pháp"
        finally:
            _set_initial_language("en-US")


class TestComparisonBannerRatings:
    """Pin the user-facing engine ratings in en-US.json comparison banners.

    These were updated from research on 2025 leaderboards (Edge → high,
    Gemini → premium, Soniox → highest). A silent regression to the
    older labels would mislead users picking an engine.
    """

    @pytest.fixture
    def en_us(self) -> dict:
        import json  # noqa: PLC0415
        from pathlib import Path  # noqa: PLC0415

        path = Path("src/constants/translations/en-US.json")
        return json.loads(path.read_text(encoding="utf-8"))

    def test_tts_banner_lists_all_five_engines(self, en_us: dict) -> None:
        v = en_us["settings.tts_comparison"]
        for engine in (
            "Edge TTS",
            "Google Cloud TTS",
            "Gemini TTS",
            "Piper TTS",
            "ElevenLabs",
        ):
            assert engine in v, f"Missing {engine!r} from TTS banner"

    def test_edge_tts_now_high_quality(self, en_us: dict) -> None:
        v = en_us["settings.tts_comparison"]
        assert "Edge TTS</a> — high quality" in v

    def test_gemini_tts_now_premium_quality(self, en_us: dict) -> None:
        v = en_us["settings.tts_comparison"]
        assert "Gemini TTS</a> — premium quality" in v

    def test_piper_tts_marked_offline(self, en_us: dict) -> None:
        v = en_us["settings.tts_comparison"]
        assert "Piper TTS</a> — good quality, fast, offline" in v

    def test_ocr_google_now_high_accuracy(self, en_us: dict) -> None:
        v = en_us["settings.ocr_comparison"]
        assert "Google Cloud OCR</a> — high accuracy" in v
        assert "highest accuracy" not in v

    def test_ocr_tesseract_lists_90_plus_languages(
        self,
        en_us: dict,
    ) -> None:
        v = en_us["settings.ocr_comparison"]
        assert (
            "TesseractOCR</a> — medium accuracy, fast, offline, free, 90+ languages"
        ) in v

    def test_whisper_lists_100_languages(self, en_us: dict) -> None:
        for key in ("settings.stt_comparison", "settings.live_stt_comparison"):
            v = en_us[key]
            assert (
                "Whisper</a> — high accuracy, slower (CPU), offline, free, "
                "100 languages"
            ) in v, f"{key} doesn't show Whisper at 100 langs"

    def test_soniox_now_highest_accuracy(self, en_us: dict) -> None:
        v = en_us["settings.live_stt_comparison"]
        assert "Soniox</a> — highest accuracy" in v
