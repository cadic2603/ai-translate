"""Tests for the unified font utility module (src/utils/font_utils.py)."""

from __future__ import annotations

from src.utils.font_utils import (
    FAMILY_MONO,
    FAMILY_SANS,
    FAMILY_SERIF,
    SCRIPT_ARABIC,
    SCRIPT_BENGALI,
    SCRIPT_CYRILLIC,
    SCRIPT_DEVANAGARI,
    SCRIPT_EAST_ASIAN,
    SCRIPT_GREEK,
    SCRIPT_HEBREW,
    SCRIPT_KHMER,
    SCRIPT_LATIN,
    SCRIPT_MONGOLIAN,
    SCRIPT_THAI,
    _resolve_font_key,
    classify_generic_family,
    detect_script,
    get_font_for_language,
)

# ── detect_script ─────────────────────────────────────────────────────


class TestDetectScript:
    """Tests for detect_script()."""

    def test_ascii_text(self) -> None:
        assert detect_script("Hello World") == SCRIPT_LATIN

    def test_empty_string(self) -> None:
        assert detect_script("") == SCRIPT_LATIN

    def test_cyrillic(self) -> None:
        assert detect_script("Привет") == SCRIPT_CYRILLIC

    def test_greek(self) -> None:
        assert detect_script("Ελληνικά") == SCRIPT_GREEK

    def test_arabic(self) -> None:
        assert detect_script("مرحبا") == SCRIPT_ARABIC

    def test_hebrew(self) -> None:
        assert detect_script("שלום") == SCRIPT_HEBREW

    def test_devanagari(self) -> None:
        assert detect_script("नमस्ते") == SCRIPT_DEVANAGARI

    def test_bengali(self) -> None:
        assert detect_script("বাংলা") == SCRIPT_BENGALI

    def test_thai(self) -> None:
        assert detect_script("สวัสดี") == SCRIPT_THAI

    def test_khmer(self) -> None:
        assert detect_script("ខ្មែរ") == SCRIPT_KHMER

    def test_mongolian(self) -> None:
        # Traditional Mongolian script character
        assert detect_script("\u1820\u1821") == SCRIPT_MONGOLIAN

    def test_east_asian_cjk(self) -> None:
        assert detect_script("你好") == SCRIPT_EAST_ASIAN

    def test_east_asian_kana(self) -> None:
        assert detect_script("こんにちは") == SCRIPT_EAST_ASIAN

    def test_east_asian_hangul(self) -> None:
        assert detect_script("안녕하세요") == SCRIPT_EAST_ASIAN

    def test_vietnamese_latin(self) -> None:
        # Vietnamese uses Latin Extended Additional — treated as latin
        assert detect_script("Xin chào Việt Nam") == SCRIPT_LATIN

    def test_mixed_latin_then_cjk(self) -> None:
        # First non-Latin script wins
        assert detect_script("Hello 你好") == SCRIPT_EAST_ASIAN

    def test_combining_diacriticals_skipped(self) -> None:
        # Combining marks (U+0300–U+036F) are Latin-compatible
        assert detect_script("e\u0301") == SCRIPT_LATIN

    def test_general_punctuation_skipped(self) -> None:
        # U+2000–U+2BFF general punctuation / symbols
        assert detect_script("Hello\u2014world") == SCRIPT_LATIN

    # Supplementary Unicode ranges
    def test_cjk_extension_b(self) -> None:
        """CJK Extension B character (U+20000+) → east_asian."""
        assert detect_script("\U00020000") == SCRIPT_EAST_ASIAN

    def test_cjk_extension_f(self) -> None:
        """CJK Extension F near upper bound of range → east_asian."""
        assert detect_script("\U0002fa1f") == SCRIPT_EAST_ASIAN

    def test_emoji_outside_ranges(self) -> None:
        """Emoji (e.g. U+1F600) falls outside all _SCRIPT_RANGES → latin fallback."""
        assert detect_script("\U0001f600") == SCRIPT_LATIN

    def test_supplementary_emoji_with_latin(self) -> None:
        """Emoji mixed with ASCII text → latin (emoji not in any range)."""
        assert detect_script("Hello \U0001f60a World") == SCRIPT_LATIN

    def test_private_use_area_skipped(self) -> None:
        """Private-use area (U+E000–U+F8FF) is Latin-compatible → latin."""
        assert detect_script("\ue000\uf8ff") == SCRIPT_LATIN

    # Mixed-script text
    def test_mixed_latin_and_cjk_cjk_first(self) -> None:
        """When CJK appears before Latin, detect east_asian (first non-Latin wins)."""
        assert detect_script("你好 Hello") == SCRIPT_EAST_ASIAN

    def test_mixed_latin_and_cyrillic(self) -> None:
        """Latin prefix with Cyrillic suffix → cyrillic (first non-Latin wins)."""
        assert detect_script("Welcome Привет") == SCRIPT_CYRILLIC

    def test_mixed_latin_and_arabic(self) -> None:
        """Latin prefix with Arabic → arabic."""
        assert detect_script("Hello مرحبا") == SCRIPT_ARABIC

    def test_mixed_cjk_and_cyrillic(self) -> None:
        """CJK before Cyrillic — first non-Latin script wins (east_asian)."""
        assert detect_script("你好 Привет") == SCRIPT_EAST_ASIAN

    def test_only_combining_marks(self) -> None:
        """String of only combining diacritical marks → latin (all skipped)."""
        assert detect_script("\u0301\u0302\u0303") == SCRIPT_LATIN

    def test_hangul_jamo(self) -> None:
        """Hangul Jamo range (U+1100–U+11FF) → east_asian."""
        assert detect_script("\u1100\u1161") == SCRIPT_EAST_ASIAN

    def test_cjk_compatibility_ideographs(self) -> None:
        """CJK Compatibility Ideographs (U+F900–U+FAFF) → east_asian."""
        assert detect_script("\uf900") == SCRIPT_EAST_ASIAN

    def test_arabic_supplement(self) -> None:
        """Arabic Supplement range (U+0750–U+077F) → arabic."""
        assert detect_script("\u0750") == SCRIPT_ARABIC

    def test_arabic_presentation_forms_a(self) -> None:
        """Arabic Presentation Forms-A (U+FB50–U+FDFF) → arabic."""
        assert detect_script("\ufb50") == SCRIPT_ARABIC

    def test_arabic_presentation_forms_b(self) -> None:
        """Arabic Presentation Forms-B (U+FE70–U+FEFF) → arabic."""
        assert detect_script("\ufe70") == SCRIPT_ARABIC

    def test_greek_extended(self) -> None:
        """Greek Extended range (U+1F00–U+1FFF) → greek."""
        assert detect_script("\u1f00") == SCRIPT_GREEK

    def test_digits_and_punctuation_only(self) -> None:
        """Pure ASCII digits and punctuation → latin."""
        assert detect_script("123-456.789!@#") == SCRIPT_LATIN

    def test_latin_extended_additional_vietnamese(self) -> None:
        """Vietnamese-specific characters (U+1E00–U+1EFF) are Latin-compatible."""
        # ệ = U+1EC7
        assert detect_script("\u1ec7") == SCRIPT_LATIN


# ── classify_generic_family ───────────────────────────────────────────


class TestClassifyGenericFamily:
    """Tests for classify_generic_family()."""

    # Font name classification
    def test_serif_by_name(self) -> None:
        assert classify_generic_family(font_name="Times New Roman") == FAMILY_SERIF

    def test_serif_georgia(self) -> None:
        assert classify_generic_family(font_name="Georgia") == FAMILY_SERIF

    def test_serif_palatino(self) -> None:
        assert classify_generic_family(font_name="Palatino") == FAMILY_SERIF

    def test_serif_cambria(self) -> None:
        assert classify_generic_family(font_name="Cambria") == FAMILY_SERIF

    def test_serif_noto_serif(self) -> None:
        assert classify_generic_family(font_name="Noto Serif") == FAMILY_SERIF

    def test_serif_simsun(self) -> None:
        assert classify_generic_family(font_name="SimSun") == FAMILY_SERIF

    def test_serif_mincho(self) -> None:
        assert classify_generic_family(font_name="MS Mincho") == FAMILY_SERIF

    def test_mono_by_name(self) -> None:
        assert classify_generic_family(font_name="Courier New") == FAMILY_MONO

    def test_mono_consolas(self) -> None:
        assert classify_generic_family(font_name="Consolas") == FAMILY_MONO

    def test_mono_menlo(self) -> None:
        assert classify_generic_family(font_name="Menlo") == FAMILY_MONO

    def test_mono_fira_code(self) -> None:
        assert classify_generic_family(font_name="Fira Code") == FAMILY_MONO

    def test_mono_source_code_pro(self) -> None:
        assert classify_generic_family(font_name="Source Code Pro") == FAMILY_MONO

    def test_sans_arial(self) -> None:
        assert classify_generic_family(font_name="Arial") == FAMILY_SANS

    def test_sans_calibri(self) -> None:
        assert classify_generic_family(font_name="Calibri") == FAMILY_SANS

    def test_sans_helvetica(self) -> None:
        assert classify_generic_family(font_name="Helvetica") == FAMILY_SANS

    def test_sans_default(self) -> None:
        assert classify_generic_family(font_name="UnknownFont") == FAMILY_SANS

    # Font flags classification (PyMuPDF)
    def test_flags_mono(self) -> None:
        assert classify_generic_family(font_flags=8) == FAMILY_MONO  # noqa: PLR2004

    def test_flags_serif(self) -> None:
        assert classify_generic_family(font_flags=4) == FAMILY_SERIF  # noqa: PLR2004

    def test_flags_sans(self) -> None:
        assert classify_generic_family(font_flags=0) == FAMILY_SANS

    def test_flags_mono_with_serif(self) -> None:
        # Mono bit takes precedence over serif bit
        assert classify_generic_family(font_flags=12) == FAMILY_MONO  # noqa: PLR2004

    # Name takes precedence over flags
    def test_name_overrides_flags(self) -> None:
        # Name says serif, flags say sans
        assert (
            classify_generic_family(
                font_name="Times New Roman",
                font_flags=0,
            )
            == FAMILY_SERIF
        )

    def test_name_falls_through_to_flags(self) -> None:
        # Unknown name, flags say serif
        assert (
            classify_generic_family(
                font_name="UnknownFont",
                font_flags=4,  # noqa: PLR2004
            )
            == FAMILY_SERIF
        )

    # No arguments
    def test_no_args(self) -> None:
        assert classify_generic_family() == FAMILY_SANS

    # Empty / whitespace font name
    def test_empty_name(self) -> None:
        assert classify_generic_family(font_name="") == FAMILY_SANS

    def test_whitespace_name(self) -> None:
        assert classify_generic_family(font_name="  ") == FAMILY_SANS

    # Case insensitive
    def test_case_insensitive(self) -> None:
        assert classify_generic_family(font_name="COURIER NEW") == FAMILY_MONO

    # Noto Sans Mono (should be mono, not sans)
    def test_noto_sans_mono(self) -> None:
        assert classify_generic_family(font_name="Noto Sans Mono") == FAMILY_MONO

    # Empty string edge case — falsy value should take the no-name path
    def test_empty_string_with_flags(self) -> None:
        """Empty font_name is falsy; should fall through to font_flags."""
        assert (
            classify_generic_family(font_name="", font_flags=4)  # noqa: PLR2004
            == FAMILY_SERIF
        )

    def test_none_name_with_flags(self) -> None:
        """None font_name falls through to font_flags classification."""
        assert (
            classify_generic_family(font_name=None, font_flags=8)  # noqa: PLR2004
            == FAMILY_MONO
        )

    # PostScript font name regex matching edge cases
    def test_postscript_times_psmt_no_boundary(self) -> None:
        """CamelCase 'TimesNewRomanPSMT' has no word boundary for regex."""
        assert classify_generic_family(font_name="TimesNewRomanPSMT") == FAMILY_SANS

    def test_postscript_times_hyphenated(self) -> None:
        """PostScript 'Times-Roman' — hyphen creates word boundary → serif."""
        assert classify_generic_family(font_name="Times-Roman") == FAMILY_SERIF

    def test_postscript_courier_bold(self) -> None:
        """PostScript-style 'Courier-Bold' should match mono via regex."""
        assert classify_generic_family(font_name="Courier-Bold") == FAMILY_MONO

    def test_postscript_palatino_italic(self) -> None:
        """PostScript name 'Palatino-Italic' should match serif via regex."""
        assert classify_generic_family(font_name="Palatino-Italic") == FAMILY_SERIF

    def test_regex_mono_word_code_hyphenated(self) -> None:
        """'Source-Code-Pro' — 'code' word boundary match → mono."""
        assert classify_generic_family(font_name="Source-Code-Pro") == FAMILY_MONO

    def test_regex_mono_camelcase_no_boundary(self) -> None:
        """CamelCase 'IBMPlexMono' has no word boundary before 'mono'."""
        assert classify_generic_family(font_name="IBMPlexMono") == FAMILY_SANS

    def test_regex_mono_with_space(self) -> None:
        """'IBM Plex Mono' — space creates word boundary → mono."""
        assert classify_generic_family(font_name="IBM Plex Mono") == FAMILY_MONO

    def test_no_false_positive_codec(self) -> None:
        """'Codec Pro' — 'code' followed by 'c' breaks word boundary → sans."""
        result = classify_generic_family(font_name="Codec Pro")
        assert result == FAMILY_SANS

    def test_garamond_hyphenated(self) -> None:
        """PostScript 'Garamond-Regular' — 'garamond' with word boundary → serif."""
        assert classify_generic_family(font_name="Garamond-Regular") == FAMILY_SERIF

    def test_regex_camelcase_no_serif_boundary(self) -> None:
        """CamelCase 'AGaramondPro-Regular' has no boundary before 'garamond'."""
        result = classify_generic_family(font_name="AGaramondPro-Regular")
        # 'agaramondpro-regular': 'garamond' at index 1, preceded by
        # 'a' (word char), so no word boundary → falls to sans-serif
        assert result == FAMILY_SANS


# ── _resolve_font_key ──────────────────────────────────────────────────


class TestResolveFontKey:
    """Tests for _resolve_font_key()."""

    def test_exact_match(self) -> None:
        assert _resolve_font_key("Japanese") == "japanese"

    def test_chinese_simplified(self) -> None:
        assert _resolve_font_key("Chinese (Simplified)") == "chinese (simplified)"

    def test_cyrillic_language(self) -> None:
        assert _resolve_font_key("Russian") == "cyrillic"

    def test_greek_language(self) -> None:
        assert _resolve_font_key("Greek") == "greek"

    def test_unknown_language(self) -> None:
        assert _resolve_font_key("Klingon") == "default"

    def test_case_insensitive(self) -> None:
        assert _resolve_font_key("KOREAN") == "korean"

    def test_bulgarian_maps_to_cyrillic(self) -> None:
        assert _resolve_font_key("Bulgarian") == "cyrillic"

    def test_substring_match(self) -> None:
        """Substring match: 'chinese' hits 'chinese (simplified)' via `lang in key`."""
        result = _resolve_font_key("chinese")
        assert result.startswith("chinese")


# ── get_font_for_language ─────────────────────────────────────────────


class TestGetFontForLanguage:
    """Tests for get_font_for_language().

    Always returns the first candidate from _FONT_DB for the resolved key.
    """

    def test_japanese_sans(self) -> None:
        assert get_font_for_language("Japanese", FAMILY_SANS) == "Hiragino Sans"

    def test_japanese_serif(self) -> None:
        assert get_font_for_language("Japanese", FAMILY_SERIF) == "Hiragino Mincho ProN"

    def test_japanese_mono(self) -> None:
        assert get_font_for_language("Japanese", FAMILY_MONO) == "Noto Sans Mono CJK JP"

    def test_chinese_simplified_sans(self) -> None:
        result = get_font_for_language("Chinese (Simplified)", FAMILY_SANS)
        assert result == "PingFang SC"

    def test_chinese_traditional_serif(self) -> None:
        result = get_font_for_language("Chinese (Traditional)", FAMILY_SERIF)
        assert result == "Songti TC"

    def test_korean_sans(self) -> None:
        assert get_font_for_language("Korean", FAMILY_SANS) == "Apple SD Gothic Neo"

    def test_russian_sans(self) -> None:
        assert get_font_for_language("Russian", FAMILY_SANS) == "Noto Sans"

    def test_russian_serif(self) -> None:
        assert get_font_for_language("Russian", FAMILY_SERIF) == "Noto Serif"

    def test_arabic_sans(self) -> None:
        assert get_font_for_language("Arabic", FAMILY_SANS) == "Geeza Pro"

    def test_default_sans(self) -> None:
        assert get_font_for_language("Klingon", FAMILY_SANS) == "Noto Sans"

    def test_default_serif(self) -> None:
        assert get_font_for_language("Klingon", FAMILY_SERIF) == "Noto Serif"

    def test_default_mono(self) -> None:
        assert get_font_for_language("Klingon", FAMILY_MONO) == "Noto Sans Mono"

    def test_unknown_generic_family(self) -> None:
        # Unknown family falls back to FAMILY_SANS candidates
        assert get_font_for_language("English", "cursive") == "Noto Sans"

    def test_hindi_sans(self) -> None:
        assert get_font_for_language("Hindi", FAMILY_SANS) == "Mangal"

    def test_hindi_serif(self) -> None:
        assert get_font_for_language("Hindi", FAMILY_SERIF) == "Lohit Devanagari"

    def test_thai_serif(self) -> None:
        assert get_font_for_language("Thai", FAMILY_SERIF) == "Angsana New"

    def test_vietnamese_sans(self) -> None:
        assert get_font_for_language("Vietnamese", FAMILY_SANS) == "Tahoma"

    # Unknown / unusual language labels
    def test_completely_unknown_language(self) -> None:
        """Unknown language falls back to 'default' DB entry."""
        assert get_font_for_language("Esperanto", FAMILY_SANS) == "Noto Sans"

    def test_unknown_language_serif(self) -> None:
        assert get_font_for_language("Esperanto", FAMILY_SERIF) == "Noto Serif"

    def test_unknown_language_mono(self) -> None:
        assert get_font_for_language("Esperanto", FAMILY_MONO) == "Noto Sans Mono"

    def test_empty_language_string(self) -> None:
        """Empty string language → 'default' key (no substring match)."""
        # Empty string can match all keys via `lang in key`, so it hits the
        # first _FONT_DB key in iteration. The result should be a valid font.
        result = get_font_for_language("", FAMILY_SANS)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_persian_uses_arabic_script_fonts(self) -> None:
        """Persian has its own entry with Arabic-script fonts."""
        assert get_font_for_language("Persian", FAMILY_SANS) == "Geeza Pro"

    def test_nepali_uses_devanagari_fonts(self) -> None:
        """Nepali has its own entry with Devanagari fonts."""
        assert get_font_for_language("Nepali", FAMILY_SANS) == "Mangal"

    def test_mongolian_maps_to_cyrillic(self) -> None:
        """Mongolian maps to cyrillic via _LANG_TO_SCRIPT."""
        assert get_font_for_language("Mongolian", FAMILY_SANS) == "Noto Sans"

    def test_serbian_maps_to_cyrillic(self) -> None:
        """Serbian maps to cyrillic via _LANG_TO_SCRIPT."""
        assert get_font_for_language("Serbian", FAMILY_SERIF) == "Noto Serif"

    def test_belarusian_maps_to_cyrillic(self) -> None:
        assert get_font_for_language("Belarusian", FAMILY_SANS) == "Noto Sans"

    def test_ukrainian_maps_to_cyrillic(self) -> None:
        assert get_font_for_language("Ukrainian", FAMILY_MONO) == "Noto Sans Mono"

    def test_turkish_sans(self) -> None:
        assert get_font_for_language("Turkish", FAMILY_SANS) == "Noto Sans"

    def test_chinese_substring_match(self) -> None:
        """Just 'Chinese' matches 'chinese (simplified)' via substring."""
        result = get_font_for_language("Chinese", FAMILY_SANS)
        # Should match a CJK font from one of the Chinese entries
        assert result is not None
        assert isinstance(result, str)


# ── Integration: PDF font selection ───────────────────────────────────


class TestPdfFontIntegration:
    """Verify _font_family_from_flags delegates to classify_generic_family."""

    def test_mono_flags(self) -> None:
        from src.core.pdf_processor import _font_family_from_flags  # noqa: PLC0415

        assert _font_family_from_flags(8) == FAMILY_MONO  # noqa: PLR2004

    def test_serif_flags(self) -> None:
        from src.core.pdf_processor import _font_family_from_flags  # noqa: PLC0415

        assert _font_family_from_flags(4) == FAMILY_SERIF  # noqa: PLR2004

    def test_sans_flags(self) -> None:
        from src.core.pdf_processor import _font_family_from_flags  # noqa: PLC0415

        assert _font_family_from_flags(0) == FAMILY_SANS


# ---------------------------------------------------------------------------
# NEW: Additional tests for expanded coverage
# ---------------------------------------------------------------------------


class TestDetectScriptAdditional:
    """Additional tests for detect_script()."""

    def test_single_latin_char(self) -> None:
        """Single Latin character returns latin."""
        assert detect_script("A") == SCRIPT_LATIN

    def test_single_cyrillic_char(self) -> None:
        """Single Cyrillic character returns cyrillic."""
        assert detect_script("\u0410") == SCRIPT_CYRILLIC  # А

    def test_single_arabic_char(self) -> None:
        """Single Arabic character returns arabic."""
        assert detect_script("\u0627") == SCRIPT_ARABIC  # ا

    def test_single_hebrew_char(self) -> None:
        """Single Hebrew character returns hebrew."""
        assert detect_script("\u05d0") == SCRIPT_HEBREW  # א

    def test_single_devanagari_char(self) -> None:
        """Single Devanagari character returns devanagari."""
        assert detect_script("\u0905") == SCRIPT_DEVANAGARI  # अ

    def test_single_thai_char(self) -> None:
        """Single Thai character returns thai."""
        assert detect_script("\u0e01") == SCRIPT_THAI  # ก

    def test_single_bengali_char(self) -> None:
        """Single Bengali character returns bengali."""
        assert detect_script("\u0985") == SCRIPT_BENGALI  # অ

    def test_single_khmer_char(self) -> None:
        """Single Khmer character returns khmer."""
        assert detect_script("\u1780") == SCRIPT_KHMER  # ក

    def test_space_only(self) -> None:
        """Space-only text returns latin (no non-Latin chars)."""
        assert detect_script("   ") == SCRIPT_LATIN

    def test_tab_and_newline_only(self) -> None:
        """Tab/newline only returns latin."""
        assert detect_script("\t\n\r") == SCRIPT_LATIN

    def test_numbers_only(self) -> None:
        """Numbers-only text returns latin."""
        assert detect_script("1234567890") == SCRIPT_LATIN

    def test_ascii_punctuation_only(self) -> None:
        """ASCII punctuation returns latin."""
        assert detect_script("!@#$%^&*()") == SCRIPT_LATIN

    def test_mixed_arabic_hebrew_arabic_wins(self) -> None:
        """Arabic before Hebrew: Arabic wins (first non-Latin)."""
        assert detect_script("\u0627\u05d0") == SCRIPT_ARABIC

    def test_mixed_devanagari_thai_devanagari_wins(self) -> None:
        """Devanagari before Thai: Devanagari wins."""
        assert detect_script("\u0905\u0e01") == SCRIPT_DEVANAGARI

    def test_hangul_syllable_block(self) -> None:
        """Hangul syllable block (AC00-D7AF) detected as east_asian."""
        assert detect_script("\uac00") == SCRIPT_EAST_ASIAN  # 가

    def test_cjk_symbols(self) -> None:
        """CJK symbols range (3000-303F) detected as east_asian."""
        assert detect_script("\u3001") == SCRIPT_EAST_ASIAN  # 、

    def test_katakana(self) -> None:
        """Katakana characters detected as east_asian."""
        assert detect_script("\u30a2") == SCRIPT_EAST_ASIAN  # ア

    def test_arabic_extended_a(self) -> None:
        """Arabic Extended-A range (08A0-08FF) detected as arabic."""
        assert detect_script("\u08a0") == SCRIPT_ARABIC

    def test_emoji_with_cjk_returns_east_asian(self) -> None:
        """Emoji followed by CJK: CJK is first non-Latin script."""
        # Emoji (U+1F600) falls outside all ranges, so it's skipped
        # CJK char is the first matched non-Latin
        assert detect_script("\U0001f600\u4e00") == SCRIPT_EAST_ASIAN

    def test_long_latin_text_with_late_cyrillic(self) -> None:
        """Long Latin text with Cyrillic at the end: Cyrillic detected."""
        text = "a" * 100 + "\u0410"
        assert detect_script(text) == SCRIPT_CYRILLIC


class TestClassifyGenericFamilyAdditional:
    """Additional tests for classify_generic_family()."""

    def test_serif_garamond(self) -> None:
        assert classify_generic_family(font_name="Garamond") == FAMILY_SERIF

    def test_serif_book_antiqua(self) -> None:
        assert classify_generic_family(font_name="Book Antiqua") == FAMILY_SERIF

    def test_serif_constantia(self) -> None:
        assert classify_generic_family(font_name="Constantia") == FAMILY_SERIF

    def test_serif_didot(self) -> None:
        assert classify_generic_family(font_name="Didot") == FAMILY_SERIF

    def test_serif_baskerville(self) -> None:
        assert classify_generic_family(font_name="Baskerville") == FAMILY_SERIF

    def test_serif_liberation_serif(self) -> None:
        assert classify_generic_family(font_name="Liberation Serif") == FAMILY_SERIF

    def test_serif_dejavu_serif(self) -> None:
        assert classify_generic_family(font_name="DejaVu Serif") == FAMILY_SERIF

    def test_serif_pt_serif(self) -> None:
        assert classify_generic_family(font_name="PT Serif") == FAMILY_SERIF

    def test_mono_monaco(self) -> None:
        assert classify_generic_family(font_name="Monaco") == FAMILY_MONO

    def test_mono_lucida_console(self) -> None:
        assert classify_generic_family(font_name="Lucida Console") == FAMILY_MONO

    def test_mono_dejavu_sans_mono(self) -> None:
        assert classify_generic_family(font_name="DejaVu Sans Mono") == FAMILY_MONO

    def test_mono_ubuntu_mono(self) -> None:
        assert classify_generic_family(font_name="Ubuntu Mono") == FAMILY_MONO

    def test_mono_cascadia_code(self) -> None:
        assert classify_generic_family(font_name="Cascadia Code") == FAMILY_MONO

    def test_mono_jetbrains_mono(self) -> None:
        assert classify_generic_family(font_name="JetBrains Mono") == FAMILY_MONO

    def test_mono_hack(self) -> None:
        assert classify_generic_family(font_name="Hack") == FAMILY_MONO

    def test_sans_segoe_ui(self) -> None:
        """Segoe UI is not in serif or mono sets -> sans-serif."""
        assert classify_generic_family(font_name="Segoe UI") == FAMILY_SANS

    def test_sans_roboto(self) -> None:
        """Roboto is not in serif or mono sets -> sans-serif."""
        assert classify_generic_family(font_name="Roboto") == FAMILY_SANS

    def test_font_flags_both_mono_and_serif_bits(self) -> None:
        """Mono bit (8) takes precedence over serif bit (4): flags=12."""
        assert classify_generic_family(font_flags=12) == FAMILY_MONO  # noqa: PLR2004

    def test_font_flags_high_bits_only_serif(self) -> None:
        """Flags with only serif bit set among high bits."""
        assert classify_generic_family(font_flags=4) == FAMILY_SERIF  # noqa: PLR2004

    def test_font_flags_other_bits_set(self) -> None:
        """Flags with bits other than 4 and 8 set: sans-serif."""
        # e.g. bit 0 (bold) and bit 1 (italic) but not 4 or 8
        assert classify_generic_family(font_flags=3) == FAMILY_SANS  # noqa: PLR2004

    def test_name_with_leading_trailing_spaces(self) -> None:
        """Font name with leading/trailing spaces is trimmed."""
        assert classify_generic_family(font_name="  Courier New  ") == FAMILY_MONO


class TestGetFontForLanguageAdditional:
    """Additional tests for get_font_for_language()."""

    def test_chinese_simplified_serif(self) -> None:
        assert (
            get_font_for_language("Chinese (Simplified)", FAMILY_SERIF) == "Songti SC"
        )

    def test_chinese_simplified_mono(self) -> None:
        result = get_font_for_language("Chinese (Simplified)", FAMILY_MONO)
        assert result == "Noto Sans Mono CJK SC"

    def test_chinese_traditional_sans(self) -> None:
        result = get_font_for_language("Chinese (Traditional)", FAMILY_SANS)
        assert result == "PingFang TC"

    def test_chinese_traditional_mono(self) -> None:
        result = get_font_for_language("Chinese (Traditional)", FAMILY_MONO)
        assert result == "Noto Sans Mono CJK TC"

    def test_japanese_sans(self) -> None:
        assert get_font_for_language("Japanese", FAMILY_SANS) == "Hiragino Sans"

    def test_korean_serif(self) -> None:
        assert get_font_for_language("Korean", FAMILY_SERIF) == "Batang"

    def test_korean_mono(self) -> None:
        result = get_font_for_language("Korean", FAMILY_MONO)
        assert result == "Noto Sans Mono CJK KR"

    def test_hindi_mono(self) -> None:
        assert get_font_for_language("Hindi", FAMILY_MONO) == "Noto Sans Devanagari"

    def test_nepali_serif(self) -> None:
        assert get_font_for_language("Nepali", FAMILY_SERIF) == "Lohit Devanagari"

    def test_arabic_serif(self) -> None:
        assert get_font_for_language("Arabic", FAMILY_SERIF) == "Traditional Arabic"

    def test_arabic_mono(self) -> None:
        assert get_font_for_language("Arabic", FAMILY_MONO) == "Noto Sans Arabic"

    def test_persian_serif(self) -> None:
        assert get_font_for_language("Persian", FAMILY_SERIF) == "Traditional Arabic"

    def test_hebrew_sans(self) -> None:
        assert get_font_for_language("Hebrew", FAMILY_SANS) == "David"

    def test_hebrew_serif(self) -> None:
        assert get_font_for_language("Hebrew", FAMILY_SERIF) == "David"

    def test_hebrew_mono(self) -> None:
        assert get_font_for_language("Hebrew", FAMILY_MONO) == "Noto Sans Hebrew"

    def test_bengali_sans(self) -> None:
        assert get_font_for_language("Bengali", FAMILY_SANS) == "Vrinda"

    def test_bengali_serif(self) -> None:
        assert get_font_for_language("Bengali", FAMILY_SERIF) == "Lohit Bengali"

    def test_thai_sans(self) -> None:
        assert get_font_for_language("Thai", FAMILY_SANS) == "Thonburi"

    def test_thai_mono(self) -> None:
        assert get_font_for_language("Thai", FAMILY_MONO) == "Noto Sans Thai"

    def test_khmer_sans(self) -> None:
        assert get_font_for_language("Khmer", FAMILY_SANS) == "Khmer OS"

    def test_khmer_serif(self) -> None:
        assert get_font_for_language("Khmer", FAMILY_SERIF) == "Noto Serif Khmer"

    def test_greek_sans(self) -> None:
        assert get_font_for_language("Greek", FAMILY_SANS) == "Noto Sans"

    def test_greek_serif(self) -> None:
        assert get_font_for_language("Greek", FAMILY_SERIF) == "Noto Serif"

    def test_vietnamese_serif(self) -> None:
        assert get_font_for_language("Vietnamese", FAMILY_SERIF) == "Noto Serif"

    def test_turkish_serif(self) -> None:
        assert get_font_for_language("Turkish", FAMILY_SERIF) == "Noto Serif"

    def test_turkish_mono(self) -> None:
        assert get_font_for_language("Turkish", FAMILY_MONO) == "Noto Sans Mono"


class TestScriptAwareFontConsistency:
    """Verify script-aware font selection consistency across calls."""

    def test_same_language_returns_same_font(self) -> None:
        """Repeated calls for same language return same font."""
        f1 = get_font_for_language("Japanese", FAMILY_SANS)
        f2 = get_font_for_language("Japanese", FAMILY_SANS)
        assert f1 == f2

    def test_cyrillic_languages_all_same_font(self) -> None:
        """All Cyrillic languages return the same font for same family."""
        langs = [
            "Russian",
            "Ukrainian",
            "Belarusian",
            "Bulgarian",
            "Serbian",
            "Mongolian",
        ]
        fonts = [get_font_for_language(lang, FAMILY_SANS) for lang in langs]
        assert len(set(fonts)) == 1  # All the same

    def test_different_families_for_same_language(self) -> None:
        """Different generic families produce different fonts for Japanese."""
        sans = get_font_for_language("Japanese", FAMILY_SANS)
        serif = get_font_for_language("Japanese", FAMILY_SERIF)
        mono = get_font_for_language("Japanese", FAMILY_MONO)
        assert sans != serif  # Hiragino Sans != Hiragino Mincho ProN
        assert serif != mono  # Hiragino Mincho ProN != Noto Sans Mono CJK JP

    def test_default_family_parameter(self) -> None:
        """Default generic_family parameter is FAMILY_SANS."""
        result = get_font_for_language("Japanese")
        assert result == get_font_for_language("Japanese", FAMILY_SANS)


class TestResolveFontKeyAdditional:
    """Additional tests for _resolve_font_key()."""

    def test_hindi_exact_match(self) -> None:
        assert _resolve_font_key("Hindi") == "hindi"

    def test_arabic_exact_match(self) -> None:
        assert _resolve_font_key("Arabic") == "arabic"

    def test_persian_exact_match(self) -> None:
        assert _resolve_font_key("Persian") == "persian"

    def test_thai_exact_match(self) -> None:
        assert _resolve_font_key("Thai") == "thai"

    def test_khmer_exact_match(self) -> None:
        assert _resolve_font_key("Khmer") == "khmer"

    def test_bengali_exact_match(self) -> None:
        assert _resolve_font_key("Bengali") == "bengali"

    def test_nepali_exact_match(self) -> None:
        assert _resolve_font_key("Nepali") == "nepali"

    def test_vietnamese_exact_match(self) -> None:
        assert _resolve_font_key("Vietnamese") == "vietnamese"

    def test_mongolian_maps_to_cyrillic(self) -> None:
        assert _resolve_font_key("Mongolian") == "cyrillic"

    def test_ukrainian_maps_to_cyrillic(self) -> None:
        assert _resolve_font_key("Ukrainian") == "cyrillic"

    def test_belarusian_maps_to_cyrillic(self) -> None:
        assert _resolve_font_key("Belarusian") == "cyrillic"

    def test_serbian_maps_to_cyrillic(self) -> None:
        assert _resolve_font_key("Serbian") == "cyrillic"

    def test_completely_unknown_returns_default(self) -> None:
        assert _resolve_font_key("Martian") == "default"

    def test_mixed_case_works(self) -> None:
        assert _resolve_font_key("JAPANESE") == "japanese"

    def test_default_key_for_english(self) -> None:
        """English doesn't match any _FONT_DB key exactly but 'default' via fallback."""
        # 'english' is not in _FONT_DB and not in _LANG_TO_SCRIPT
        # No substring match either (no key contains 'english')
        result = _resolve_font_key("English")
        assert result == "default"


class TestDetectScriptWithMixedScripts:
    """Test detect_script with text containing multiple scripts."""

    def test_cyrillic_then_arabic(self) -> None:
        """Cyrillic appears first: cyrillic wins."""
        assert detect_script("\u0410\u0627") == SCRIPT_CYRILLIC

    def test_greek_then_cyrillic(self) -> None:
        """Greek appears first: greek wins."""
        assert detect_script("\u0391\u0410") == SCRIPT_GREEK

    def test_devanagari_then_bengali(self) -> None:
        """Devanagari appears first: devanagari wins."""
        assert detect_script("\u0905\u0985") == SCRIPT_DEVANAGARI

    def test_latin_with_all_scripts_at_end(self) -> None:
        """Latin text with CJK at the end: east_asian wins."""
        text = "Hello World 123 " + "\u4e00"
        assert detect_script(text) == SCRIPT_EAST_ASIAN

    def test_only_latin_extended(self) -> None:
        """Latin Extended characters are treated as latin."""
        # U+00C0 to U+00FF are Latin-1 Supplement (accented chars)
        text = "\u00c0\u00e9\u00f1\u00fc"
        assert detect_script(text) == SCRIPT_LATIN


class TestGetFontForLanguageEdgeCases:
    """Edge cases for get_font_for_language."""

    def test_case_insensitive_matching(self) -> None:
        """Language matching is case-insensitive."""
        assert get_font_for_language("japanese") == get_font_for_language("Japanese")

    def test_whitespace_in_language_name(self) -> None:
        """Whitespace in language name does not match any key normally."""
        result = get_font_for_language(" Japanese ")
        # ' japanese ' won't exact-match; substring matching may or may not find it
        assert isinstance(result, str)
        assert len(result) > 0

    def test_numeric_language_falls_to_default(self) -> None:
        """Numeric string falls back to default."""
        result = get_font_for_language("12345", FAMILY_SANS)
        assert result == "Noto Sans"

    def test_empty_language_returns_valid_font(self) -> None:
        """Empty string returns a valid font (may match first DB key via substring)."""
        result = get_font_for_language("", FAMILY_SANS)
        assert isinstance(result, str)
        assert len(result) > 0
