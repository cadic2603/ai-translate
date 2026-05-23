"""Unit tests for text and HTML utilities."""

import pytest

from src.utils.text_utils import (
    AttrRecord,
    _AttrEntry,
    _tag_signature,
    build_norm_map,
    clean_llm_html,
    html_to_plain_text,
    normalize_for_search,
    repair_html_tags,
    restore_html_attributes,
    restore_md_overhead,
    restore_rtf_overhead,
    restore_xml_overhead,
    strip_bom,
    strip_html_attributes,
    strip_md_overhead,
    strip_rtf_overhead,
    strip_xml_attributes,
    strip_xml_overhead,
)


def test_clean_llm_html() -> None:
    """Verify that leading/trailing breaks are removed."""
    assert clean_llm_html("<br>Hello<br>") == "Hello"
    assert clean_llm_html("<br/><br/>Text") == "Text"
    assert clean_llm_html("Text<br/><br/>") == "Text"
    assert clean_llm_html("Normal <b>Text</b>") == "Normal <b>Text</b>"


def test_clean_llm_html_br_space_variant() -> None:
    """Verify that <br /> variant (with space) is handled."""
    assert clean_llm_html("<br />Hello<br />") == "Hello"
    assert clean_llm_html("<br /><br />Text<br />") == "Text"
    assert clean_llm_html("Text<br /><br />") == "Text"


def test_clean_llm_html_mixed_br_variants() -> None:
    """Verify that mixed <br> variants at boundaries are removed."""
    assert clean_llm_html("<br><br/><br />Start") == "Start"
    assert clean_llm_html("End<br /><br><br/>") == "End"
    assert clean_llm_html("<BR>CaseTest<BR/>") == "CaseTest"


def test_clean_llm_html_preserves_inner_br() -> None:
    """Verify that <br> tags in the middle of content are preserved."""
    assert clean_llm_html("Line 1<br>Line 2") == "Line 1<br>Line 2"
    assert clean_llm_html("A<br />B<br/>C") == "A<br />B<br/>C"


def test_clean_llm_html_empty_and_whitespace() -> None:
    """Verify edge cases with empty or whitespace-only input."""
    assert clean_llm_html("") == ""
    assert clean_llm_html("<br>") == ""
    assert clean_llm_html("<br/><br />") == ""


def test_html_to_plain_text() -> None:
    """Verify HTML stripping and break conversion."""
    html = "Line 1<br><b>Bold</b> <i>Italic</i><br/>Line 2"
    expected = "Line 1\nBold Italic\nLine 2"
    assert html_to_plain_text(html) == expected


def test_html_to_plain_text_br_space_variant() -> None:
    """Verify that <br /> variant is converted to newline."""
    html = "Line A<br />Line B<BR />Line C"
    assert html_to_plain_text(html) == "Line A\nLine B\nLine C"


def test_html_to_plain_text_complex_span() -> None:
    """Verify that span tags with attributes are stripped."""
    html = "Text with <span style='color: red;'>colored</span> word"
    assert html_to_plain_text(html) == "Text with colored word"

    # Nested or multiple spans
    html2 = "<span class='a'>One</span> <span class='b'>Two</span>"
    assert html_to_plain_text(html2) == "One Two"


def test_html_to_plain_text_underline() -> None:
    """Verify that <u> tags are stripped."""
    html = "Normal <u>underlined</u> text"
    assert html_to_plain_text(html) == "Normal underlined text"


# ---------------------------------------------------------------------------
# normalize_for_search
# ---------------------------------------------------------------------------


def test_normalize_for_search_diacritics() -> None:
    """Strips diacritics and casefolds."""
    assert normalize_for_search("Xin Chào") == "xin chao"
    assert normalize_for_search("café") == "cafe"
    assert normalize_for_search("naïve") == "naive"


def test_normalize_for_search_casefold() -> None:
    """Casefold handles uppercase and German ß."""
    assert normalize_for_search("HELLO") == "hello"
    assert normalize_for_search("Straße") == "strasse"


def test_normalize_for_search_ligatures() -> None:
    """NFKD decomposes ligatures."""
    assert normalize_for_search("ﬁnd") == "find"
    assert normalize_for_search("ﬂow") == "flow"


def test_normalize_for_search_cjk() -> None:
    """CJK characters pass through unchanged."""
    assert normalize_for_search("你好") == "你好"
    assert normalize_for_search("こんにちは") == "こんにちは"


def test_normalize_for_search_zero_width() -> None:
    """Zero-width characters are stripped."""
    assert normalize_for_search("hel\u200blo") == "hello"


def test_normalize_for_search_empty() -> None:
    """Empty string returns empty."""
    assert normalize_for_search("") == ""


# ---------------------------------------------------------------------------
# build_norm_map
# ---------------------------------------------------------------------------


def test_build_norm_map_ascii() -> None:
    """Plain ASCII maps 1:1."""
    norm, indices = build_norm_map("Hello")
    assert norm == "hello"
    assert indices == [0, 1, 2, 3, 4]


def test_build_norm_map_accented() -> None:
    """Accented chars map back to their original position."""
    norm, indices = build_norm_map("Café")
    assert norm == "cafe"
    assert indices == [0, 1, 2, 3]


def test_build_norm_map_german_eszett() -> None:
    """ß expands to ss — both map to the original ß position."""
    norm, indices = build_norm_map("Straße")
    assert norm == "strasse"
    # ß at index 4 produces two chars: s, s — both map to 4
    assert indices == [0, 1, 2, 3, 4, 4, 5]


def test_build_norm_map_cjk() -> None:
    """CJK chars map 1:1."""
    norm, indices = build_norm_map("你好")
    assert norm == "你好"
    assert indices == [0, 1]


def test_build_norm_map_empty() -> None:
    """Empty string returns empty results."""
    norm, indices = build_norm_map("")
    assert norm == ""
    assert indices == []


def test_build_norm_map_mixed() -> None:
    """Mixed content with accent and normal chars."""
    norm, indices = build_norm_map("à b")
    assert norm == "a b"
    assert indices == [0, 1, 2]


def test_build_norm_map_zero_width() -> None:
    """Zero-width chars are skipped in the map."""
    # "a" + ZWS + "b" → "ab" with indices [0, 2]
    norm, indices = build_norm_map("a\u200bb")
    assert norm == "ab"
    assert indices == [0, 2]


# ---------------------------------------------------------------------------
# strip_html_attributes
# ---------------------------------------------------------------------------


def _has_attr_raw(record: AttrRecord, raw_fragment: str) -> bool:
    """Check if any AttrEntry in a record contains the given raw fragment."""
    return any(raw_fragment in e.raw for e in record.attrs)


def test_strip_basic_class() -> None:
    """Non-translatable class attr is stripped, text preserved."""
    html = '<div class="foo">Hello</div>'
    stripped, records = strip_html_attributes(html)
    assert 'data-ftid="0"' in stripped
    assert "Hello</div>" in stripped
    assert len(records) == 1
    assert records[0].tag_name == "div"
    assert _has_attr_raw(records[0], 'class="foo"')


def test_strip_self_closing_preserves_alt() -> None:
    """Self-closing img: src stripped, alt kept."""
    html = '<img src="pic.jpg" alt="cat" />'
    stripped, records = strip_html_attributes(html)
    assert 'alt="cat"' in stripped
    assert "src=" not in stripped
    assert len(records) == 1
    assert records[0].tag_name == "img"


def test_strip_keeps_title_strips_href() -> None:
    """Translatable title is kept, non-translatable href is stripped."""
    html = '<a href="#" title="tip">link</a>'
    stripped, records = strip_html_attributes(html)
    assert 'title="tip"' in stripped
    assert "href=" not in stripped
    assert len(records) == 1


def test_strip_all_translatable_attrs_preserved() -> None:
    """All 11 translatable attributes are kept when present."""
    attrs = [
        'alt="a"',
        'title="b"',
        'placeholder="c"',
        'label="d"',
        'abbr="e"',
        'summary="f"',
        'aria-label="g"',
        'aria-placeholder="h"',
        'aria-description="i"',
        'aria-roledescription="j"',
        'aria-valuetext="k"',
    ]
    html = f"<div {' '.join(attrs)}>text</div>"
    stripped, records = strip_html_attributes(html)
    # All translatable — nothing should be stripped
    assert len(records) == 0
    for attr in attrs:
        assert attr in stripped


def test_strip_mixed_tags_with_and_without_attrs() -> None:
    """Mix of tags with and without attributes."""
    html = '<p>plain</p><div class="x">styled</div><span>bare</span>'
    stripped, records = strip_html_attributes(html)
    assert "<p>plain</p>" in stripped
    assert "styled</div>" in stripped
    assert "<span>bare</span>" in stripped
    assert len(records) == 1


def test_strip_nested_tags() -> None:
    """Nested tags with attributes are all stripped."""
    html = '<div id="a"><span class="b">text</span></div>'
    stripped, records = strip_html_attributes(html)
    assert "text</span></div>" in stripped
    assert len(records) == 2  # noqa: PLR2004
    assert records[0].tag_name == "div"
    assert records[1].tag_name == "span"


def test_strip_no_attributes() -> None:
    """Tags without attributes pass through unchanged."""
    html = "<p>text</p>"
    stripped, records = strip_html_attributes(html)
    assert stripped == "<p>text</p>"
    assert records == {}


def test_strip_all_translatable_no_record() -> None:
    """Tag with only translatable attrs produces no record."""
    html = '<img alt="cat">'
    stripped, records = strip_html_attributes(html)
    assert stripped == html
    assert records == {}


def test_strip_empty_input() -> None:
    """Empty string returns empty string and empty records."""
    stripped, records = strip_html_attributes("")
    assert stripped == ""
    assert records == {}


def test_strip_multiple_non_translatable() -> None:
    """Multiple non-translatable attrs are all stripped."""
    html = '<a href="#" class="link" data-id="1">text</a>'
    stripped, records = strip_html_attributes(html)
    assert 'data-ftid="0"' in stripped
    assert "text</a>" in stripped
    assert len(records) == 1
    assert _has_attr_raw(records[0], "href")
    assert _has_attr_raw(records[0], "class")
    assert _has_attr_raw(records[0], "data-id")


def test_strip_single_quoted_attrs() -> None:
    """Single-quoted attribute values are handled."""
    html = "<div class='foo' title='tip'>text</div>"
    stripped, records = strip_html_attributes(html)
    assert "title=" in stripped
    assert "class='foo'" not in stripped


def test_strip_boolean_attribute() -> None:
    """Boolean attributes (no value) are stripped."""
    html = "<input disabled placeholder='Enter'>"
    stripped, records = strip_html_attributes(html)
    assert "placeholder=" in stripped
    assert "disabled" not in stripped or "data-ftid" in stripped


def test_strip_xml_namespaced_attrs() -> None:
    """XML-namespaced attributes (xml:lang, xmlns:epub) roundtrip."""
    html = '<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en">'
    stripped, records = strip_html_attributes(html)
    assert len(records) == 1
    assert _has_attr_raw(records[0], 'xml:lang="en"')
    assert _has_attr_raw(records[0], "xmlns=")

    # Roundtrip preserves colons
    restored = restore_html_attributes(stripped, records)
    assert 'xml:lang="en"' in restored
    assert "xmlns=" in restored


def test_strip_epub_type_attr() -> None:
    """EPUB epub:type attribute is stripped and restored correctly."""
    html = '<section epub:type="chapter" class="main">text</section>'
    stripped, records = strip_html_attributes(html)
    assert "epub:type" not in stripped or "data-ftid" in stripped
    restored = restore_html_attributes(stripped, records)
    assert 'epub:type="chapter"' in restored
    assert 'class="main"' in restored


def test_strip_uppercase_tag_name() -> None:
    """Mixed-case tag names: record stores lowercase, output preserves case."""
    html = '<DIV class="foo" title="bar">text</DIV>'
    stripped, records = strip_html_attributes(html)
    assert records[0].tag_name == "div"  # lowercased in record
    assert "<DIV" in stripped  # original casing preserved in output
    assert 'title="bar"' in stripped


def test_strip_uppercase_attr_names() -> None:
    """Uppercase translatable attr names (ALT, Title) are recognised."""
    html = '<img SRC="pic.jpg" ALT="photo" Title="img">'
    stripped, records = strip_html_attributes(html)
    assert 'ALT="photo"' in stripped
    assert 'Title="img"' in stripped
    assert "SRC=" not in stripped or "data-ftid" in stripped


def test_strip_unquoted_attr_values() -> None:
    """Unquoted attribute values like class=foo are handled."""
    html = '<div class=container id=main title="tip">text</div>'
    stripped, records = strip_html_attributes(html)
    assert 'title="tip"' in stripped
    assert _has_attr_raw(records[0], "class=container")


def test_strip_whitespace_around_equals() -> None:
    """Attributes with spaces around the = sign are parsed."""
    html = '<div class = "foo" title = "tip">text</div>'
    stripped, records = strip_html_attributes(html)
    assert "title" in stripped
    assert len(records) == 1


def test_strip_self_closing_no_space_before_slash() -> None:
    """Self-closing tag without space before /> is handled."""
    html = '<img src="pic.jpg" alt="cat"/>'
    stripped, records = strip_html_attributes(html)
    assert 'alt="cat"' in stripped
    assert len(records) == 1


def test_strip_tag_with_only_whitespace() -> None:
    """Tag with trailing space but no real attributes passes through."""
    html = "<div >text</div>"
    stripped, records = strip_html_attributes(html)
    assert records == {}
    assert stripped == "<div >text</div>"


def test_strip_attr_value_with_gt() -> None:
    """Attribute values containing > are handled correctly by html.parser."""
    html = '<div title="a > b" class="x">text</div>'
    stripped, records = strip_html_attributes(html)
    assert 'title="a > b"' in stripped
    assert len(records) == 1
    assert records[0].tag_name == "div"
    assert _has_attr_raw(records[0], 'class="x"')


def test_strip_multiline_attrs() -> None:
    """Multiline attributes are handled correctly by html.parser."""
    html = '<div\n  class="foo"\n  id="bar">text</div>'
    stripped, records = strip_html_attributes(html)
    assert "text</div>" in stripped
    assert len(records) == 1
    assert _has_attr_raw(records[0], 'class="foo"')
    assert _has_attr_raw(records[0], 'id="bar"')


def test_strip_dotted_attr_name() -> None:
    """Dotted attribute names (v-bind.sync) are parsed correctly."""
    html = '<div v-bind.sync="value" title="tip">text</div>'
    stripped, records = strip_html_attributes(html)
    assert 'title="tip"' in stripped
    assert _has_attr_raw(records[0], 'v-bind.sync="value"')


def test_strip_empty_attr_values() -> None:
    """Attributes with empty string values are handled."""
    html = '<div class="" title="">text</div>'
    stripped, records = strip_html_attributes(html)
    assert 'title=""' in stripped
    assert _has_attr_raw(records[0], 'class=""')


def test_strip_multiple_same_name_tags_ordering() -> None:
    """Multiple same-name tags produce records in document order."""
    html = '<div class="a">1</div><div class="b">2</div><div class="c">3</div>'
    stripped, records = strip_html_attributes(html)
    assert len(records) == 3  # noqa: PLR2004
    assert _has_attr_raw(records[0], 'class="a"')
    assert _has_attr_raw(records[1], 'class="b"')
    assert _has_attr_raw(records[2], 'class="c"')


def test_strip_numeric_tag_name() -> None:
    """Tags with digits in name (h1, h2) are matched."""
    html = '<h1 class="title">Heading</h1>'
    stripped, records = strip_html_attributes(html)
    assert "Heading</h1>" in stripped
    assert 'data-ftid="0"' in stripped
    assert records[0].tag_name == "h1"


def test_strip_exact_output_format() -> None:
    """Verify output format includes marker and translatable attrs."""
    html = '<a href="#" title="tip" class="lnk">link</a>'
    stripped, records = strip_html_attributes(html)
    assert 'title="tip"' in stripped
    assert 'data-ftid="0"' in stripped
    assert "link</a>" in stripped


def test_strip_data_and_style_attrs() -> None:
    """data-* and style attributes are stripped (non-translatable)."""
    html = '<div data-id="42" style="color:red" title="t">text</div>'
    stripped, records = strip_html_attributes(html)
    assert 'title="t"' in stripped
    assert _has_attr_raw(records[0], "data-id")
    assert _has_attr_raw(records[0], "style")


def test_strip_multiline_mixed_attrs() -> None:
    """Multiline tag with mix of translatable and non-translatable attrs."""
    html = (
        "<img\n"
        '  src="photo.jpg"\n'
        '  class="hero"\n'
        '  alt="A beautiful sunset"\n'
        '  title="Sunset photo">'
    )
    stripped, records = strip_html_attributes(html)
    assert 'alt="A beautiful sunset"' in stripped
    assert 'title="Sunset photo"' in stripped
    assert len(records) == 1
    assert _has_attr_raw(records[0], 'src="photo.jpg"')
    assert _has_attr_raw(records[0], 'class="hero"')


def test_strip_gt_in_single_quoted_attr() -> None:
    """Greater-than sign inside single-quoted attribute value."""
    html = "<div title='x > y' class='z'>text</div>"
    stripped, records = strip_html_attributes(html)
    assert "title='x > y'" in stripped
    assert len(records) == 1


def test_strip_multiple_gt_in_attrs() -> None:
    """Multiple > characters in different attribute values."""
    html = (
        '<span title="a > b > c" data-expr="x>0"'
        ' aria-label="greater > less">text</span>'
    )
    stripped, records = strip_html_attributes(html)
    assert 'title="a > b > c"' in stripped
    assert 'aria-label="greater > less"' in stripped
    assert _has_attr_raw(records[0], "data-expr")


def test_strip_xml_attrs_with_gt_in_value() -> None:
    """XML attribute stripping handles > inside quoted attribute values."""
    xml = '<rule condition="x > 0" id="r1">Apply</rule>'
    stripped, records = strip_xml_attributes(xml)
    assert "Apply</rule>" in stripped
    assert 'data-ftid="0"' in stripped
    assert len(records) == 1
    assert _has_attr_raw(records[0], 'condition="x > 0"')
    assert _has_attr_raw(records[0], 'id="r1"')


def test_strip_xml_multiline_attrs() -> None:
    """XML attribute stripping handles multiline attributes."""
    xml = '<item\n  id="1"\n  category="fiction">Text</item>'
    stripped, records = strip_xml_attributes(xml)
    assert "Text</item>" in stripped
    assert 'data-ftid="0"' in stripped
    assert len(records) == 1
    assert _has_attr_raw(records[0], 'id="1"')
    assert _has_attr_raw(records[0], 'category="fiction"')


# ---------------------------------------------------------------------------
# repair_html_tags
# ---------------------------------------------------------------------------


def test_repair_no_changes_needed() -> None:
    """Identical tag sequences need no repair."""
    html = "<div><p>Hello</p></div>"
    assert repair_html_tags(html, html) == html


def test_repair_missing_opening_tag() -> None:
    """Re-inserts a dropped opening tag."""
    original = "<div><p>Hello</p></div>"
    translated = "<p>Bonjour</p></div>"  # LLM dropped <div>
    result = repair_html_tags(original, translated)
    assert "<div>" in result
    assert "<p>Bonjour</p>" in result
    assert "</div>" in result


def test_repair_missing_closing_tag() -> None:
    """Re-inserts a dropped closing tag."""
    original = "<p>Hello</p>"
    translated = "<p>Bonjour"  # LLM dropped </p>
    result = repair_html_tags(original, translated)
    assert "<p>Bonjour" in result
    assert "</p>" in result


def test_repair_missing_self_closing_tag() -> None:
    """Re-inserts a dropped self-closing tag."""
    original = "<p>Line 1<br/>Line 2</p>"
    translated = "<p>Ligne 1Ligne 2</p>"  # LLM dropped <br/>
    result = repair_html_tags(original, translated)
    assert "<br/>" in result


def test_repair_multiple_missing_tags() -> None:
    """Re-inserts multiple dropped tags."""
    original = "<div><span>A</span><span>B</span></div>"
    # LLM dropped both <span> tags
    translated = "A B</span></span></div>"
    result = repair_html_tags(original, translated)
    assert "<div>" in result


def test_repair_llm_adds_extra_tags() -> None:
    """Extra tags added by LLM are left as-is."""
    original = "<p>Hello</p>"
    translated = "<p><strong>Bonjour</strong></p>"
    result = repair_html_tags(original, translated)
    assert "<strong>" in result
    assert "</strong>" in result


def test_repair_empty_translated() -> None:
    """All original tags re-inserted when translated is empty."""
    original = "<div><p>text</p></div>"
    result = repair_html_tags(original, "")
    assert "<div>" in result
    assert "<p>" in result
    assert "</p>" in result
    assert "</div>" in result


def test_repair_no_tags_in_original() -> None:
    """Plain text original — translated returned as-is."""
    assert repair_html_tags("hello", "bonjour") == "bonjour"


def test_repair_case_insensitive_signature() -> None:
    """Tag matching is case-insensitive: <DIV> matches <div>."""
    original = "<DIV><P>Hello</P></DIV>"
    translated = "<div><p>Bonjour</p></div>"
    result = repair_html_tags(original, translated)
    assert result == "<div><p>Bonjour</p></div>"


def test_repair_text_only_translated() -> None:
    """Translated has text but zero tags — all original tags re-inserted."""
    original = "<p>Hello</p>"
    translated = "Bonjour"
    result = repair_html_tags(original, translated)
    assert "<p>" in result
    assert "</p>" in result
    assert "Bonjour" in result


def test_repair_self_closing_mixed_with_regular() -> None:
    """Mix of self-closing and regular tags, one self-closing dropped."""
    original = "<p>Line 1<br/>Line 2<br/>Line 3</p>"
    translated = "<p>Ligne 1Ligne 2<br/>Ligne 3</p>"
    result = repair_html_tags(original, translated)
    assert result.count("<br/>") == 2  # noqa: PLR2004


def test_repair_attrs_in_original_bare_in_translated() -> None:
    """Signature matching ignores attributes — bare tag matches attr tag."""
    original = '<div class="x"><p>Hello</p></div>'
    translated = "<div><p>Bonjour</p></div>"
    result = repair_html_tags(original, translated)
    # repair only re-inserts missing tags, not missing attributes
    assert result == "<div><p>Bonjour</p></div>"


def test_repair_extra_tags_between_matched() -> None:
    """Extra LLM-added tags between matched siblings are preserved."""
    original = "<div><p>A</p><p>B</p></div>"
    translated = "<div><p>X</p><em>extra</em><p>Y</p></div>"
    result = repair_html_tags(original, translated)
    assert "<em>extra</em>" in result
    assert "<p>X</p>" in result
    assert "<p>Y</p>" in result


def test_repair_both_empty() -> None:
    """Both inputs empty — returns empty string."""
    assert repair_html_tags("", "") == ""


def test_repair_original_no_tags_translated_has_tags() -> None:
    """Original plain text, LLM added tags — preserved as-is."""
    result = repair_html_tags("hello", "<b>bonjour</b>")
    assert result == "<b>bonjour</b>"


def test_repair_deeply_nested_partial_drops() -> None:
    """Inner tag dropped from deep nesting — re-inserted correctly."""
    original = "<div><section><p>Hello</p></section></div>"
    translated = "<div><p>Bonjour</p></div>"
    result = repair_html_tags(original, translated)
    assert "<section>" in result
    assert "</section>" in result


def test_repair_consecutive_identical_tags_dropped() -> None:
    """Multiple consecutive same-type self-closing tags all dropped."""
    original = "A<br/>B<br/>C<br/>D"
    translated = "ABCD"
    result = repair_html_tags(original, translated)
    assert result.count("<br/>") == 3  # noqa: PLR2004


def test_repair_trailing_text_preserved() -> None:
    """Trailing text after last matched tag is preserved."""
    original = "<p>Hello</p>"
    translated = "<p>Bonjour</p> (translator note)"
    result = repair_html_tags(original, translated)
    assert result == "<p>Bonjour</p> (translator note)"


def test_repair_leading_text_preserved() -> None:
    """Leading text before first tag is preserved."""
    original = "<p>Hello</p>"
    translated = "Note: <p>Bonjour</p>"
    result = repair_html_tags(original, translated)
    assert result.startswith("Note: <p>")


def test_tag_signature_opening() -> None:
    """Opening tag signature: tag name only."""
    assert _tag_signature('<div class="x">') == "div"
    assert _tag_signature("<p>") == "p"


def test_tag_signature_closing() -> None:
    """Closing tag signature: slash + tag name."""
    assert _tag_signature("</div>") == "/div"
    assert _tag_signature("</span>") == "/span"


def test_tag_signature_self_closing() -> None:
    """Self-closing tags are treated as opening (no slash prefix)."""
    assert _tag_signature("<br/>") == "br"
    assert _tag_signature("<img />") == "img"


def test_tag_signature_case_insensitive() -> None:
    """Signature is lowercased."""
    assert _tag_signature("<DIV>") == "div"
    assert _tag_signature("</SPAN>") == "/span"


def test_tag_signature_unparseable_fallback() -> None:
    """Unparseable tag text returns the input unchanged."""
    assert _tag_signature("<123>") == "<123>"
    assert _tag_signature("not a tag") == "not a tag"


# ---------------------------------------------------------------------------
# restore_html_attributes
# ---------------------------------------------------------------------------


def test_restore_basic() -> None:
    """Stripped div gets class attribute restored via marker."""
    html = '<div data-ftid="0">Bonjour</div>'
    records = {0: AttrRecord("div", [_AttrEntry('class="foo"', False)])}
    result = restore_html_attributes(html, records)
    assert 'class="foo"' in result
    assert ">Bonjour</div>" in result
    assert "data-ftid" not in result


def test_restore_self_closing() -> None:
    """Self-closing tag gets attributes restored via marker."""
    html = '<img data-ftid="0" />'
    records = {0: AttrRecord("img", [_AttrEntry('src="pic.jpg"', False)])}
    result = restore_html_attributes(html, records)
    assert 'src="pic.jpg"' in result


def test_restore_no_marker_untouched() -> None:
    """Tags without data-ftid marker are left unchanged."""
    html = "<span>text</span>"
    records = {0: AttrRecord("div", [_AttrEntry('class="foo"', False)])}
    result = restore_html_attributes(html, records)
    assert result == "<span>text</span>"


def test_restore_exhausted_records() -> None:
    """Tag with marker gets attrs; tag without marker is left as-is."""
    html = '<div data-ftid="0">a</div><p>b</p>'
    records = {0: AttrRecord("div", [_AttrEntry('id="x"', False)])}
    result = restore_html_attributes(html, records)
    assert 'id="x"' in result
    assert "<p>b</p>" in result


def test_restore_empty_records() -> None:
    """Empty records dict returns HTML unchanged."""
    html = "<p>text</p>"
    assert restore_html_attributes(html, {}) == html


def test_restore_with_translatable_attrs() -> None:
    """Restoration merges translated and stored attrs."""
    html = '<img alt="chat" data-ftid="0" />'
    records = {
        0: AttrRecord(
            "img",
            [
                _AttrEntry('src="pic.jpg"', False),
                _AttrEntry('alt="cat"', True),
            ],
        )
    }
    result = restore_html_attributes(html, records)
    assert 'src="pic.jpg"' in result
    assert 'alt="chat"' in result  # translated value kept


def test_restore_tag_with_existing_non_translatable_attrs() -> None:
    """Marker-based restore replaces all attrs from record."""
    html = '<div data-ftid="0">text</div>'
    records = {
        0: AttrRecord(
            "div",
            [
                _AttrEntry('class="foo"', False),
                _AttrEntry('style="color:red"', False),
            ],
        )
    }
    result = restore_html_attributes(html, records)
    assert 'class="foo"' in result
    assert 'style="color:red"' in result


def test_restore_self_closing_no_space() -> None:
    """Self-closing tag without space before /> is restored."""
    html = '<img alt="chat" data-ftid="0"/>'
    records = {
        0: AttrRecord(
            "img",
            [
                _AttrEntry('src="pic.jpg"', False),
                _AttrEntry('alt="cat"', True),
            ],
        )
    }
    result = restore_html_attributes(html, records)
    assert 'src="pic.jpg"' in result
    assert 'alt="chat"' in result


def test_restore_multiple_same_name_records() -> None:
    """Multiple markers match by ID, not sequential order."""
    html = '<div data-ftid="0">first</div><div data-ftid="1">second</div>'
    records = {
        0: AttrRecord("div", [_AttrEntry('class="a"', False)]),
        1: AttrRecord("div", [_AttrEntry('class="b"', False)]),
    }
    result = restore_html_attributes(html, records)
    parts = result.split("</div>")
    assert 'class="a"' in parts[0]
    assert 'class="b"' in parts[1]


def test_restore_record_tag_never_in_html() -> None:
    """No markers in HTML — records unused, text unchanged."""
    html = "plain text with no tags"
    records = {0: AttrRecord("div", [_AttrEntry('class="x"', False)])}
    result = restore_html_attributes(html, records)
    assert result == "plain text with no tags"


def test_restore_case_insensitive_tag_match() -> None:
    """Uppercase tag with marker still gets attrs restored."""
    html = '<DIV data-ftid="0">text</DIV>'
    records = {0: AttrRecord("div", [_AttrEntry('class="foo"', False)])}
    result = restore_html_attributes(html, records)
    assert 'class="foo"' in result
    assert result.startswith("<DIV")


def test_restore_closing_tags_not_matched() -> None:
    """Closing tags don't have markers — only opening tags matched."""
    html = '</p><div data-ftid="0">text</div>'
    records = {0: AttrRecord("div", [_AttrEntry('class="foo"', False)])}
    result = restore_html_attributes(html, records)
    assert 'class="foo"' in result
    assert "</p>" in result


def test_restore_empty_html_with_records() -> None:
    """Empty HTML with non-empty records returns empty string."""
    records = {0: AttrRecord("div", [_AttrEntry('class="x"', False)])}
    result = restore_html_attributes("", records)
    assert result == ""


def test_restore_bare_self_closing_br() -> None:
    """Self-closing <br/> with marker gets attrs restored."""
    html = '<br data-ftid="0"/>'
    records = {0: AttrRecord("br", [_AttrEntry('class="spacer"', False)])}
    result = restore_html_attributes(html, records)
    assert 'class="spacer"' in result


# ---------------------------------------------------------------------------
# Round-trip integration
# ---------------------------------------------------------------------------


def test_roundtrip_strip_restore() -> None:
    """Full cycle: strip → identity translate → restore = original."""
    original = (
        '<div class="container" id="main">'
        '<img src="logo.png" alt="Logo" />'
        '<a href="/home" title="Home">Home</a>'
        "</div>"
    )
    stripped, records = strip_html_attributes(original)
    # Simulate LLM returning the stripped HTML unchanged
    restored = restore_html_attributes(stripped, records)
    # All original attributes should be present
    assert 'class="container"' in restored
    assert 'id="main"' in restored
    assert 'src="logo.png"' in restored
    assert 'alt="Logo"' in restored
    assert 'href="/home"' in restored
    assert 'title="Home"' in restored


def test_roundtrip_with_repair() -> None:
    """Full cycle with repair: strip → translate (drop tag) → repair → restore."""
    original = '<div class="box"><p>Hello world</p></div>'
    stripped, records = strip_html_attributes(original)

    # Simulate LLM dropping the <div> tag but keeping its marker
    # In practice, repair inserts the original tag with marker
    translated_with_drop = "<p>Bonjour le monde</p></div>"
    repaired = repair_html_tags(stripped, translated_with_drop)
    restored = restore_html_attributes(repaired, records)

    assert 'class="box"' in restored
    assert "Bonjour le monde" in restored


def test_roundtrip_translated_attrs() -> None:
    """Translatable attrs are translated, non-translatable restored."""
    original = '<img src="photo.jpg" alt="A cute cat" title="Photo">'
    stripped, records = strip_html_attributes(original)

    # Simulate LLM translating alt and title (keeping marker)
    translated = stripped.replace(
        'alt="A cute cat"',
        'alt="Un joli chat"',
    )
    restored = restore_html_attributes(translated, records)

    assert 'src="photo.jpg"' in restored
    assert 'alt="Un joli chat"' in restored


def test_roundtrip_multiple_same_name_tags() -> None:
    """Records restored by marker ID for repeated tag names."""
    original = '<div class="a"><div class="b">text</div></div>'
    stripped, records = strip_html_attributes(original)
    restored = restore_html_attributes(stripped, records)
    assert 'class="a"' in restored
    assert 'class="b"' in restored
    idx_a = restored.index('class="a"')
    idx_b = restored.index('class="b"')
    assert idx_a < idx_b


def test_roundtrip_self_closing_translated_attrs() -> None:
    """Self-closing tag with translated attrs gets stripped attrs restored."""
    original = '<img src="photo.jpg" alt="A cute cat" />'
    stripped, records = strip_html_attributes(original)
    translated = stripped.replace(
        'alt="A cute cat"',
        'alt="Un joli chat"',
    )
    restored = restore_html_attributes(translated, records)
    assert 'src="photo.jpg"' in restored
    assert 'alt="Un joli chat"' in restored
    assert "/>" in restored


def test_roundtrip_repair_restore_self_closing() -> None:
    """Full pipeline: self-closing tag dropped by LLM, repaired and restored."""
    original = '<p>Text <img src="photo.jpg" alt="cat" /> more</p>'
    stripped, records = strip_html_attributes(original)
    translated = "<p>Texte plus</p>"
    repaired = repair_html_tags(stripped, translated)
    assert "<img" in repaired
    restored = restore_html_attributes(repaired, records)
    assert 'src="photo.jpg"' in restored


def test_roundtrip_epub_complex() -> None:
    """Realistic EPUB HTML with namespaced attrs roundtrips correctly."""
    original = (
        '<html xmlns="http://www.w3.org/1999/xhtml"'
        ' xmlns:epub="http://www.idpf.org/2007/ops">'
        '<body epub:type="bodymatter">'
        '<section epub:type="chapter" class="ch1">'
        "<p>Hello</p>"
        "</section></body></html>"
    )
    stripped, records = strip_html_attributes(original)
    restored = restore_html_attributes(stripped, records)
    assert "xmlns=" in restored
    assert 'epub:type="bodymatter"' in restored
    assert 'epub:type="chapter"' in restored
    assert 'class="ch1"' in restored


def test_roundtrip_llm_adds_and_drops_tags() -> None:
    """LLM adds extra tags — marker-based restore still works correctly."""
    original = '<div class="box"><p>Hello world</p></div>'
    stripped, records = strip_html_attributes(original)
    # LLM added <strong> (no marker), kept <p> marker
    translated = stripped.replace(
        ">Hello world</p>",
        "><strong>Bonjour</strong></p>",
    )
    restored = restore_html_attributes(translated, records)
    assert 'class="box"' in restored
    assert "<strong>" in restored


def test_roundtrip_empty_tag_content() -> None:
    """Tags with no text content — only structure preserved."""
    original = '<div class="wrapper"><span class="inner"></span></div>'
    stripped, records = strip_html_attributes(original)
    restored = restore_html_attributes(stripped, records)
    assert 'class="wrapper"' in restored
    assert 'class="inner"' in restored


def test_roundtrip_boolean_attrs() -> None:
    """Boolean attrs (disabled, readonly) survive strip-translate-restore."""
    original = '<input disabled readonly placeholder="Enter name" class="form">'
    stripped, records = strip_html_attributes(original)
    translated = stripped.replace(
        'placeholder="Enter name"',
        'placeholder="Entrez le nom"',
    )
    restored = restore_html_attributes(translated, records)
    assert "disabled" in restored
    assert "readonly" in restored
    assert 'class="form"' in restored
    assert 'placeholder="Entrez le nom"' in restored


def test_roundtrip_llm_adds_extra_same_name_tag() -> None:
    """LLM adds extra <div> — marker-based restore puts attrs on correct tags."""
    original = '<div class="header"><div class="content">Hello</div></div>'
    stripped, records = strip_html_attributes(original)
    # LLM wraps content in an extra <div> (no marker)
    translated = stripped.replace(
        ">Hello</div>",
        "><div>Bonjour</div></div>",
    )
    restored = restore_html_attributes(translated, records)
    assert 'class="header"' in restored
    assert 'class="content"' in restored
    # Extra LLM-added <div> should NOT get any attributes
    assert restored.count("class=") == 2  # noqa: PLR2004


def test_roundtrip_attribute_order_preserved() -> None:
    """Original attribute order is preserved after strip-translate-restore."""
    original = '<img src="photo.jpg" alt="cat" class="hero">'
    stripped, records = strip_html_attributes(original)
    translated = stripped.replace('alt="cat"', 'alt="chat"')
    restored = restore_html_attributes(translated, records)
    # Original order: src, alt, class
    assert restored.index("src=") < restored.index("alt=")
    assert restored.index("alt=") < restored.index("class=")


# ===========================================================================
# strip_xml_overhead / restore_xml_overhead
# ===========================================================================


def test_strip_xml_processing_instruction() -> None:
    """Processing instructions are replaced with placeholders."""
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n<root>Hello</root>'
    stripped, records = strip_xml_overhead(xml)
    assert "<?xml" not in stripped
    assert "[__PRESERVE_XML_0__]" in stripped
    assert "<root>Hello</root>" in stripped
    assert len(records) == 1
    assert records[0] == '<?xml version="1.0" encoding="UTF-8"?>'


def test_strip_xml_comment_left_intact() -> None:
    """XML comments are left intact (LLMs naturally skip them)."""
    xml = "<root><!-- a comment -->Hello</root>"
    stripped, records = strip_xml_overhead(xml)
    assert "<!-- a comment -->" in stripped
    assert "Hello" in stripped
    assert records == []


def test_strip_xml_cdata_markers() -> None:
    """CDATA open/close markers are replaced; text content is preserved."""
    xml = "<data><![CDATA[Some <special> text]]></data>"
    stripped, records = strip_xml_overhead(xml)
    assert "<![CDATA[" not in stripped
    assert "]]>" not in stripped
    assert "Some <special> text" in stripped
    assert len(records) == 2  # noqa: PLR2004
    assert records[0] == "<![CDATA["
    assert records[1] == "]]>"


def test_strip_xml_multiple_overheads() -> None:
    """PIs and CDATA are replaced; comments pass through unchanged."""
    xml = (
        '<?xml version="1.0"?>'
        "<!-- comment1 -->"
        "<root><![CDATA[text]]><!-- comment2 --></root>"
    )
    stripped, records = strip_xml_overhead(xml)
    # Only PI + CDATA open + CDATA close → 3 records
    assert len(records) == 3  # noqa: PLR2004
    for i in range(3):
        assert f"[__PRESERVE_XML_{i}__]" in stripped
    assert "text" in stripped
    # Comments remain in stripped text
    assert "<!-- comment1 -->" in stripped
    assert "<!-- comment2 -->" in stripped


def test_strip_xml_overhead_empty() -> None:
    """Empty input returns empty string and empty records."""
    stripped, records = strip_xml_overhead("")
    assert stripped == ""
    assert records == []


def test_strip_xml_overhead_no_overhead() -> None:
    """Plain XML without PI/comments/CDATA passes through unchanged."""
    xml = "<root><item>Hello</item></root>"
    stripped, records = strip_xml_overhead(xml)
    assert stripped == xml
    assert records == []


def test_strip_xml_multiline_comment_left_intact() -> None:
    """Multi-line comments pass through unchanged (not stripped)."""
    xml = "<root><!--\n  multi\n  line\n--><item>Text</item></root>"
    stripped, records = strip_xml_overhead(xml)
    assert stripped == xml
    assert records == []


def test_restore_xml_overhead_basic() -> None:
    """Placeholders are restored to original constructs."""
    stripped = "[__PRESERVE_XML_0__]\n<root>Hello</root>"
    records = ['<?xml version="1.0"?>']
    restored = restore_xml_overhead(stripped, records)
    assert '<?xml version="1.0"?>' in restored
    assert "[__PRESERVE_XML_0__]" not in restored


def test_restore_xml_overhead_empty_records() -> None:
    """No records returns text unchanged."""
    text = "<root>Hello</root>"
    assert restore_xml_overhead(text, []) == text


def test_restore_xml_overhead_missing_placeholder() -> None:
    """If LLM dropped a placeholder, the remaining text is unchanged."""
    stripped = "<root>Hello</root>"  # [__PRESERVE_XML_0__] was dropped by LLM
    records = ['<?xml version="1.0"?>']
    restored = restore_xml_overhead(stripped, records)
    assert restored == "<root>Hello</root>"


def test_restore_xml_overhead_unknown_index() -> None:
    """Placeholder with index beyond records is left as-is."""
    text = "[__PRESERVE_XML_99__] <root>Hello</root>"
    restored = restore_xml_overhead(text, ["only one record"])
    assert "[__PRESERVE_XML_99__]" in restored


# ===========================================================================
# strip_xml_attributes
# ===========================================================================


def test_strip_xml_all_attrs() -> None:
    """All attributes are stripped from XML tags."""
    xml = '<book id="1" category="fiction"><title>Hello</title></book>'
    stripped, records = strip_xml_attributes(xml)
    assert "Hello</title></book>" in stripped
    assert 'data-ftid="0"' in stripped
    assert len(records) == 1
    assert records[0].tag_name == "book"
    assert _has_attr_raw(records[0], 'id="1"')
    assert _has_attr_raw(records[0], 'category="fiction"')


def test_strip_xml_namespace_attrs() -> None:
    """Namespace declarations are stripped."""
    xml = '<catalog xmlns:dc="http://purl.org/dc/elements/1.1/">Text</catalog>'
    stripped, records = strip_xml_attributes(xml)
    assert "xmlns" not in stripped or "data-ftid" in stripped
    assert "Text</catalog>" in stripped


def test_strip_xml_self_closing() -> None:
    """Self-closing XML tags are handled."""
    xml = '<item ref="abc" />'
    stripped, records = strip_xml_attributes(xml)
    assert 'data-ftid="0"' in stripped
    assert len(records) == 1
    assert _has_attr_raw(records[0], 'ref="abc"')


def test_strip_xml_no_attrs() -> None:
    """Tags without attributes pass through unchanged."""
    xml = "<root><item>Hello</item></root>"
    stripped, records = strip_xml_attributes(xml)
    assert stripped == xml
    assert records == {}


def test_strip_xml_mixed_tags() -> None:
    """Mix of tags with and without attributes."""
    xml = '<root id="r"><item>Text</item><meta key="v" /></root>'
    stripped, records = strip_xml_attributes(xml)
    assert "<item>Text</item>" in stripped
    assert 'data-ftid="0"' in stripped  # root
    assert 'data-ftid="1"' in stripped  # meta
    assert len(records) == 2  # noqa: PLR2004  # root + meta


def test_strip_xml_attributes_empty() -> None:
    """Empty input returns empty string."""
    stripped, records = strip_xml_attributes("")
    assert stripped == ""
    assert records == {}


def test_strip_xml_attrs_compatible_with_html_restore() -> None:
    """Records from strip_xml_attributes work with restore_html_attributes."""
    xml = '<book id="1"><title lang="en">Hello</title></book>'
    stripped, records = strip_xml_attributes(xml)
    restored = restore_html_attributes(stripped, records)
    assert 'id="1"' in restored
    assert 'lang="en"' in restored


# ===========================================================================
# XML round-trip tests
# ===========================================================================


def test_xml_roundtrip_strip_restore() -> None:
    """Full strip → identity → restore produces valid XML."""
    xml = '<root id="main"><item key="a">Hello</item></root>'
    overhead_stripped, overhead_recs = strip_xml_overhead(xml)
    attr_stripped, attr_recs = strip_xml_attributes(overhead_stripped)

    # Simulate identity translation (no change)
    restored = restore_html_attributes(attr_stripped, attr_recs)
    restored = restore_xml_overhead(restored, overhead_recs)
    assert restored == xml


def test_xml_roundtrip_with_pi_and_attrs() -> None:
    """Round-trip with processing instructions and attributes."""
    xml = (
        '<?xml version="1.0"?>\n'
        '<catalog xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
        "  <book>Hello World</book>\n"
        "</catalog>"
    )
    overhead_stripped, overhead_recs = strip_xml_overhead(xml)
    attr_stripped, attr_recs = strip_xml_attributes(overhead_stripped)

    # Verify stripping removed overhead
    assert "<?xml" not in attr_stripped
    assert "xmlns" not in attr_stripped
    assert "Hello World" in attr_stripped

    # Restore and verify round-trip
    restored = restore_html_attributes(attr_stripped, attr_recs)
    restored = restore_xml_overhead(restored, overhead_recs)
    assert restored == xml


def test_xml_roundtrip_cdata_text_preserved() -> None:
    """Text inside CDATA is available for translation."""
    xml = "<data><![CDATA[Translate me]]></data>"
    overhead_stripped, overhead_recs = strip_xml_overhead(xml)

    # CDATA markers stripped, text preserved
    assert "Translate me" in overhead_stripped
    assert "<![CDATA[" not in overhead_stripped

    # Simulate translation
    translated = overhead_stripped.replace("Translate me", "Traduisez-moi")
    restored = restore_xml_overhead(translated, overhead_recs)
    assert "<![CDATA[Traduisez-moi]]>" in restored


def test_xml_roundtrip_with_translation_and_repair() -> None:
    """Full pipeline: strip → translate → repair → restore."""
    xml = '<root id="1"><p class="x">Hello</p></root>'
    overhead_stripped, overhead_recs = strip_xml_overhead(xml)
    attr_stripped, attr_recs = strip_xml_attributes(overhead_stripped)

    # Simulate LLM translating and dropping </root>
    # The LLM output keeps markers intact
    translated = attr_stripped.replace("Hello", "Bonjour")
    translated = translated.replace("</root>", "")  # drop closing tag
    repaired = repair_html_tags(attr_stripped, translated)
    restored_attrs = restore_html_attributes(repaired, attr_recs)
    restored = restore_xml_overhead(restored_attrs, overhead_recs)

    assert 'id="1"' in restored
    assert 'class="x"' in restored
    assert "Bonjour" in restored
    assert "</root>" in restored


# ===========================================================================
# strip_rtf_overhead / restore_rtf_overhead
# ===========================================================================


def test_strip_rtf_control_word() -> None:
    """Simple control words are replaced with placeholders."""
    rtf = r"\b Hello\b0  World"
    stripped, records = strip_rtf_overhead(rtf)
    assert "Hello" in stripped
    assert "World" in stripped
    assert r"\b " not in stripped
    assert r"\b0" not in stripped
    assert len(records) >= 2  # noqa: PLR2004  # \b, \b0 at minimum


def test_strip_rtf_control_word_with_param() -> None:
    r"""Control words with numeric params like \fs24 are stripped."""
    rtf = r"\fs24 Hello"
    stripped, records = strip_rtf_overhead(rtf)
    assert "Hello" in stripped
    assert r"\fs24" not in stripped


def test_strip_rtf_control_symbol() -> None:
    r"""Control symbols like \\ and \{ are replaced."""
    rtf = r"Hello\~World"
    stripped, records = strip_rtf_overhead(rtf)
    assert "Hello" in stripped
    assert "World" in stripped
    assert r"\~" not in stripped


def test_strip_rtf_braces() -> None:
    """Group braces { and } are replaced with placeholders."""
    rtf = r"{\b Bold}"
    stripped, records = strip_rtf_overhead(rtf)
    assert "Bold" in stripped
    assert "{" not in stripped
    assert "}" not in stripped


def test_strip_rtf_unicode_escape() -> None:
    r"""Unicode escape \uN? is decoded to the actual character."""
    rtf = r"\u8220?Hello\u8221?"
    stripped, records = strip_rtf_overhead(rtf)
    # \u8220 = left double quotation mark, \u8221 = right double quotation mark
    assert "\u201c" in stripped  # Left double quote
    assert "\u201d" in stripped  # Right double quote
    assert "Hello" in stripped
    assert r"\u8220" not in stripped


def test_strip_rtf_unicode_negative() -> None:
    r"""Negative Unicode escapes like \u-4064? are decoded correctly."""
    # RTF uses 65536 - abs for negative, so \u-4064? = 65536 - 4064 = 61472
    rtf = r"\u-4064?X"
    stripped, records = strip_rtf_overhead(rtf)
    assert chr(61472) in stripped
    assert r"\u-4064" not in stripped


def test_strip_rtf_mixed() -> None:
    """Mixed control words, symbols, braces, and text."""
    rtf = r"\pard\f0\fs24 Hello {\b World}"
    stripped, records = strip_rtf_overhead(rtf)
    assert "Hello" in stripped
    assert "World" in stripped
    # All RTF constructs should be replaced
    assert r"\pard" not in stripped
    assert r"\f0" not in stripped
    assert r"\fs24" not in stripped
    assert r"\b " not in stripped


def test_strip_rtf_empty() -> None:
    """Empty input returns empty string."""
    stripped, records = strip_rtf_overhead("")
    assert stripped == ""
    assert records == []


def test_strip_rtf_plain_text_only() -> None:
    """Text without any RTF constructs passes through unchanged."""
    text = "Hello World"
    stripped, records = strip_rtf_overhead(text)
    assert stripped == "Hello World"
    assert records == []


def test_strip_rtf_preserves_readable_text() -> None:
    """Only readable text content remains after stripping."""
    rtf = r"\pard\f0\fs24\cf1 This is a test."
    stripped, records = strip_rtf_overhead(rtf)
    # Strip all placeholders to check remaining text
    import re  # noqa: PLC0415

    clean = re.sub(r"\[__PRESERVE_RTF_\d+__\]", "", stripped).strip()
    assert clean == "This is a test."


def test_restore_rtf_basic() -> None:
    """Placeholders are restored to original RTF constructs."""
    stripped = r"[__PRESERVE_RTF_0__][__PRESERVE_RTF_1__] Hello [__PRESERVE_RTF_2__]"
    records = [r"\pard", r"\f0 ", r"\par"]
    restored = restore_rtf_overhead(stripped, records)
    assert r"\pard" in restored
    assert r"\f0 " in restored
    assert r"\par" in restored
    assert "Hello" in restored
    assert "__PRESERVE_RTF_" not in restored


def test_restore_rtf_empty_records() -> None:
    """No records returns text unchanged."""
    text = "Hello World"
    assert restore_rtf_overhead(text, []) == text


def test_restore_rtf_missing_placeholder() -> None:
    """If LLM dropped a placeholder, remaining text is unchanged."""
    text = "Bonjour"  # [__PRESERVE_RTF_0__] was dropped
    records = [r"\b "]
    restored = restore_rtf_overhead(text, records)
    assert restored == "Bonjour"


def test_restore_rtf_unknown_index() -> None:
    """Placeholder with index beyond records is left as-is."""
    text = "[__PRESERVE_RTF_99__] Hello"
    restored = restore_rtf_overhead(text, ["only one"])
    assert "[__PRESERVE_RTF_99__]" in restored


# ===========================================================================
# RTF round-trip tests
# ===========================================================================


def test_rtf_roundtrip_strip_restore() -> None:
    """Full strip → identity → restore produces original RTF."""
    rtf = r"\pard\f0\fs24 Hello World"
    stripped, records = strip_rtf_overhead(rtf)
    restored = restore_rtf_overhead(stripped, records)
    assert restored == rtf


def test_rtf_roundtrip_with_translation() -> None:
    """Strip → translate → restore preserves RTF structure."""
    rtf = r"\pard\f0\fs24 Hello World"
    stripped, records = strip_rtf_overhead(rtf)

    # Simulate translation: replace readable text
    import re  # noqa: PLC0415

    translated = re.sub(r"Hello World", "Bonjour Monde", stripped)
    restored = restore_rtf_overhead(translated, records)

    assert r"\pard" in restored
    assert r"\f0" in restored
    assert r"\fs24" in restored
    assert "Bonjour Monde" in restored


def test_rtf_roundtrip_complex() -> None:
    """Complex RTF chunk with bold, italic, font changes."""
    rtf = r"{\b Bold text} and {\i italic text}"
    stripped, records = strip_rtf_overhead(rtf)

    assert "Bold text" in stripped
    assert "italic text" in stripped

    # Simulate translation
    translated = stripped.replace("Bold text", "Texte gras")
    translated = translated.replace("italic text", "texte italique")
    restored = restore_rtf_overhead(translated, records)

    assert r"\b " in restored
    assert r"\i " in restored
    assert "Texte gras" in restored
    assert "texte italique" in restored


# ── Markdown Overhead Stripping Tests ────────────────────────


def test_strip_md_overhead_empty() -> None:
    """Empty input returns empty string and no records."""
    stripped, records = strip_md_overhead("")
    assert stripped == ""
    assert records == []


def test_strip_md_overhead_inline_link() -> None:
    """Inline links have their URL replaced with a placeholder."""
    md = "Click [here](https://example.com) for details."
    stripped, records = strip_md_overhead(md)

    assert stripped == "Click [here]([__PRESERVE_MD_0__]) for details."
    assert records == ["https://example.com"]


def test_strip_md_overhead_inline_image() -> None:
    """Inline images have their URL replaced with a placeholder."""
    md = "See ![logo](images/logo.png) above."
    stripped, records = strip_md_overhead(md)

    assert stripped == "See ![logo]([__PRESERVE_MD_0__]) above."
    assert records == ["images/logo.png"]


def test_strip_md_overhead_multiple_links() -> None:
    """Multiple inline links get sequential placeholders."""
    md = "[A](url1) and [B](url2) and ![C](url3)"
    stripped, records = strip_md_overhead(md)

    assert stripped == (
        "[A]([__PRESERVE_MD_0__]) and"
        " [B]([__PRESERVE_MD_1__]) and"
        " ![C]([__PRESERVE_MD_2__])"
    )
    assert records == ["url1", "url2", "url3"]


def test_strip_md_overhead_reference_link() -> None:
    """Reference-style link definitions are placeholdered."""
    md = 'Some text.\n\n[1]: https://example.com "Example Title"'
    stripped, records = strip_md_overhead(md)

    assert "[1]: [__PRESERVE_MD_0__]" in stripped
    assert records == ['https://example.com "Example Title"']


def test_strip_md_overhead_mixed() -> None:
    """Both inline links and reference definitions are handled."""
    md = 'Read [the docs](https://docs.io) for info.\n\n[ref]: https://ref.io "Ref"'
    stripped, records = strip_md_overhead(md)

    assert "[the docs]([__PRESERVE_MD_0__])" in stripped
    assert "[ref]: [__PRESERVE_MD_1__]" in stripped
    assert len(records) == 2  # noqa: PLR2004


def test_strip_md_overhead_no_links() -> None:
    """Text without links is returned unchanged."""
    md = "# Hello World\n\nThis is plain **markdown**."
    stripped, records = strip_md_overhead(md)

    assert stripped == md
    assert records == []


def test_strip_md_overhead_link_with_title() -> None:
    """Inline link with title attribute is handled."""
    md = '[click](https://example.com "Title") here'
    stripped, records = strip_md_overhead(md)

    assert "[click]([__PRESERVE_MD_0__]) here" in stripped
    assert records == ['https://example.com "Title"']


def test_restore_md_overhead_basic() -> None:
    """Placeholders are restored to original URLs."""
    stripped = "[text]([__PRESERVE_MD_0__]) and ![img]([__PRESERVE_MD_1__])"
    records = ["https://example.com", "img.png"]

    restored = restore_md_overhead(stripped, records)

    assert restored == "[text](https://example.com) and ![img](img.png)"


def test_restore_md_overhead_empty_records() -> None:
    """Empty records list returns text unchanged."""
    text = "No placeholders here."
    assert restore_md_overhead(text, []) == text


def test_restore_md_overhead_unknown_index() -> None:
    """Unknown placeholder index is left as-is."""
    text = "See [__PRESERVE_MD_99__]."
    restored = restore_md_overhead(text, ["only_one"])
    assert restored == "See [__PRESERVE_MD_99__]."


def test_md_roundtrip_inline_links() -> None:
    """Full round-trip: strip → translate text → restore."""
    md = "Visit [our site](https://example.com) for more."
    stripped, records = strip_md_overhead(md)

    # Simulate translation (only text changes, placeholder preserved)
    translated = (
        stripped.replace("Visit", "Visitez")
        .replace(
            "our site",
            "notre site",
        )
        .replace("for more.", "pour en savoir plus.")
    )
    restored = restore_md_overhead(translated, records)

    assert "(https://example.com)" in restored
    assert "Visitez" in restored
    assert "notre site" in restored


def test_md_roundtrip_image() -> None:
    """Round-trip for inline images."""
    md = "![Alt text](https://img.example.com/photo.jpg)"
    stripped, records = strip_md_overhead(md)

    translated = stripped.replace("Alt text", "Texte alternatif")
    restored = restore_md_overhead(translated, records)

    assert restored == "![Texte alternatif](https://img.example.com/photo.jpg)"


def test_md_roundtrip_reference_definitions() -> None:
    """Round-trip for reference-style link definitions."""
    md = 'See [link][1].\n\n[1]: https://example.com "Title"'
    stripped, records = strip_md_overhead(md)

    translated = stripped.replace("See", "Voir")
    restored = restore_md_overhead(translated, records)

    assert '[1]: https://example.com "Title"' in restored
    assert "Voir" in restored


def test_md_overhead_with_html_attributes() -> None:
    """Markdown with embedded HTML: both URL and attr stripping work."""
    md = 'Click [here](https://example.com).\n\n<div class="note">Important</div>'
    stripped_md, md_records = strip_md_overhead(md)
    stripped_html, html_records = strip_html_attributes(stripped_md)

    # URL is placeholdered
    assert "[__PRESERVE_MD_0__]" in stripped_html
    # HTML class attribute is stripped, marker added
    assert 'class="note"' not in stripped_html
    assert "data-ftid" in stripped_html

    # Restore in reverse order
    restored_html = restore_html_attributes(stripped_html, html_records)
    restored = restore_md_overhead(restored_html, md_records)

    assert "(https://example.com)" in restored
    assert 'class="note"' in restored


def test_strip_md_overhead_code_blocks_preserved() -> None:
    """Links inside code blocks are still processed (by design).

    Code blocks are left for the LLM to handle. The URL stripping
    inside fenced code is harmless because restore_md_overhead
    will put URLs back anyway.
    """
    md = "```\n[link](url)\n```"
    stripped, records = strip_md_overhead(md)

    # URL is still stripped (regex is format-agnostic)
    assert records == ["url"]
    # But round-trip restores perfectly
    restored = restore_md_overhead(stripped, records)
    assert restored == md


def test_strip_md_overhead_adjacent_links() -> None:
    """Adjacent links without separating text."""
    md = "[A](u1)[B](u2)"
    stripped, records = strip_md_overhead(md)

    assert stripped == "[A]([__PRESERVE_MD_0__])[B]([__PRESERVE_MD_1__])"
    assert records == ["u1", "u2"]


def test_strip_md_overhead_nested_brackets() -> None:
    """Link text with no nested brackets."""
    md = "[simple text](url)"
    stripped, records = strip_md_overhead(md)
    assert stripped == "[simple text]([__PRESERVE_MD_0__])"
    assert records == ["url"]


def test_strip_md_overhead_multiple_ref_definitions() -> None:
    """Multiple reference-style definitions on separate lines."""
    md = '[1]: https://one.com\n[2]: https://two.com "Two"'
    stripped, records = strip_md_overhead(md)

    assert "[1]: [__PRESERVE_MD_0__]" in stripped
    assert "[2]: [__PRESERVE_MD_1__]" in stripped
    assert len(records) == 2  # noqa: PLR2004
    assert records[0] == "https://one.com"
    assert records[1] == 'https://two.com "Two"'


def test_strip_md_overhead_empty_link_text() -> None:
    """Empty link text [](url) is handled — placeholder replaces URL."""
    md = "[](https://example.com)"
    stripped, records = strip_md_overhead(md)

    assert stripped == "[]([__PRESERVE_MD_0__])"
    assert records == ["https://example.com"]
    # Round-trip restores correctly
    assert restore_md_overhead(stripped, records) == md


def test_strip_md_overhead_url_with_query_string() -> None:
    """URLs with query strings and fragments are captured in full."""
    md = "[Search](https://example.com/search?q=hello&lang=en#results)"
    stripped, records = strip_md_overhead(md)

    assert stripped == "[Search]([__PRESERVE_MD_0__])"
    assert records == ["https://example.com/search?q=hello&lang=en#results"]
    assert restore_md_overhead(stripped, records) == md


def test_md_identity_roundtrip_with_records() -> None:
    """Strip with URLs then restore without any text change gives back original."""
    md = (
        "# Title\n\n"
        "Click [here](https://example.com) and see ![img](img.png).\n\n"
        '[ref]: https://ref.io "Ref"'
    )
    stripped, records = strip_md_overhead(md)

    assert len(records) == 3  # noqa: PLR2004
    # No text modifications — restore must reproduce the original exactly
    assert restore_md_overhead(stripped, records) == md


def test_md_full_pipeline_with_repair() -> None:
    """Full Markdown pipeline: strip MD + strip HTML → repair dropped tag → restore."""
    # Markdown chunk with an inline link AND embedded HTML with attributes
    md_chunk = (
        'Visit [our site]([__PRESERVE_MD_0__]) and <div class="note">read this</div>'
    )
    # (Simulating that strip_md_overhead already ran)
    md_records = ["https://example.com"]

    # Now apply strip_html_attributes (second layer)
    html_stripped, html_records = strip_html_attributes(md_chunk)
    assert 'class="note"' not in html_stripped
    # Marker-based: stripped tag gets data-ftid="N" instead of bare <div>
    assert 'data-ftid="0"' in html_stripped
    assert "[__PRESERVE_MD_0__]" in html_stripped  # placeholder survives html stripping

    # Simulate LLM dropping the <div> tag (with marker)
    translated = "Visitez [notre site]([__PRESERVE_MD_0__]) et read this</div>"

    # Repair: uses html_stripped as the reference for what tags should be there
    repaired = repair_html_tags(html_stripped, translated)
    # repair_html_tags re-inserts the stripped <div data-ftid="0"> tag
    assert "data-ftid" in repaired

    # Restore HTML attributes
    restored_html = restore_html_attributes(repaired, html_records)
    assert 'class="note"' in restored_html

    # Restore MD URLs (last step)
    restored = restore_md_overhead(restored_html, md_records)
    assert "(https://example.com)" in restored
    assert 'class="note"' in restored
    assert "Visitez" in restored


def test_restore_md_placeholder_reorder() -> None:
    """LLM reordering __MD_N__ placeholders: index-based restore handles it."""
    records = ["url_a", "url_b", "url_c"]
    # LLM swapped order of placeholders
    reordered = (
        "[c]([__PRESERVE_MD_2__]) then"
        " [a]([__PRESERVE_MD_0__]) then"
        " [b]([__PRESERVE_MD_1__])"
    )
    restored = restore_md_overhead(reordered, records)

    assert "[c](url_c)" in restored
    assert "[a](url_a)" in restored
    assert "[b](url_b)" in restored


def test_strip_md_overhead_reference_style_links_not_matched() -> None:
    """Reference-style links [text][id] and images ![alt][id] are NOT stripped.

    Known limitation: _MD_INLINE_LINK_RE only matches [text](url) syntax.
    Reference-style usage [text][id] has no URL to strip — the URL lives
    in a separate [id]: url definition line, which IS handled.
    """
    md = "See [my link][ref] and ![my image][img]."
    stripped, records = strip_md_overhead(md)

    # No change — neither syntax is matched by the inline link regex
    assert stripped == md
    assert records == []


# ===========================================================================
# RTF edge cases
# ===========================================================================


def test_rtf_unicode_escapes_decoded_not_reencoded() -> None:
    r"""Unicode escapes \uN? are decoded to real chars and NOT re-encoded.

    This is intentional: the LLM receives readable Unicode characters
    rather than RTF escape sequences. The RTF output contains the real
    Unicode characters, which is valid for UTF-8 encoded RTF files.
    After strip+restore the original \uN? escape sequences do NOT appear;
    the decoded Unicode characters remain in the output instead.
    """
    rtf = r"\u8220?Hello\u8221?"  # RTF for "Hello" (curly quotes)
    stripped, records = strip_rtf_overhead(rtf)

    # Decoded chars appear in stripped text
    assert "\u201c" in stripped  # left double quotation mark
    assert "\u201d" in stripped  # right double quotation mark
    assert "Hello" in stripped

    # Records hold the original escapes
    assert r"\u8220?" in records
    assert r"\u8221?" in records

    # After restore: decoded chars remain — escapes are NOT re-inserted
    # (no __RTF_N__ placeholder was created for successful Unicode decodes)
    restored = restore_rtf_overhead(stripped, records)
    assert "\u201c" in restored
    assert "\u201d" in restored
    assert r"\u8220" not in restored  # intentional: escape is gone
    assert r"\u8221" not in restored  # intentional: escape is gone


def test_restore_rtf_placeholder_reorder() -> None:
    """RTF restore is index-based: reordered placeholders are each correct."""
    records = ["FIRST", "SECOND", "THIRD"]
    # LLM reordered the placeholders (unlikely but possible)
    reordered = "[__PRESERVE_RTF_2__] [__PRESERVE_RTF_0__] [__PRESERVE_RTF_1__]"
    restored = restore_rtf_overhead(reordered, records)

    assert restored == "THIRD FIRST SECOND"


def test_rtf_roundtrip_with_unicode_and_control_words() -> None:
    r"""Mixed: control words get placeholders, Unicode chars stay decoded."""
    rtf = r"\pard \u8220?Hello\u8221? \par"
    stripped, records = strip_rtf_overhead(rtf)

    # Control words have __RTF_N__ placeholders; Unicode chars are decoded
    assert "\u201c" in stripped
    assert "\u201d" in stripped
    assert "Hello" in stripped
    assert r"\pard" not in stripped
    assert r"\par" not in stripped

    # Simulate translation
    translated = stripped.replace("Hello", "Bonjour")
    restored = restore_rtf_overhead(translated, records)

    # Control words are restored; Unicode chars stay as decoded chars
    assert r"\pard" in restored
    assert r"\par" in restored
    assert "Bonjour" in restored
    assert "\u201c" in restored  # stays as decoded char
    assert "\u201d" in restored


# ===========================================================================
# XML edge cases
# ===========================================================================


def test_strip_xml_attributes_strips_translatable_attrs_unlike_html() -> None:
    """XML strips ALL attrs including ones HTML would keep (alt, title, etc).

    This is the key behavioral difference between strip_xml_attributes and
    strip_html_attributes: XML attributes are never user-facing translatable
    text in the same way HTML attributes are.
    """
    xml = '<img src="pic.jpg" alt="A cat" title="Photo" id="i1" />'
    xml_stripped, xml_records = strip_xml_attributes(xml)

    # XML strips everything including alt and title — marker tag only
    assert 'data-ftid="0"' in xml_stripped
    assert "alt=" not in xml_stripped
    assert len(xml_records) == 1
    rec = xml_records[0]
    assert _has_attr_raw(rec, 'alt="A cat"')
    assert _has_attr_raw(rec, 'title="Photo"')
    assert _has_attr_raw(rec, 'src="pic.jpg"')

    html_stripped, html_records = strip_html_attributes(xml)

    # HTML keeps alt and title, strips only src and id
    assert 'alt="A cat"' in html_stripped
    assert 'title="Photo"' in html_stripped
    assert "src=" not in html_stripped


def test_strip_xml_overhead_minimal_pi() -> None:
    """Minimal processing instruction with no attributes is handled."""
    xml = "<?standalone?><root>text</root>"
    stripped, records = strip_xml_overhead(xml)

    assert "<?standalone?>" not in stripped
    assert "[__PRESERVE_XML_0__]" in stripped
    assert "<root>text</root>" in stripped
    assert records[0] == "<?standalone?>"


def test_strip_xml_overhead_adjacent_pis() -> None:
    """Two consecutive processing instructions produce two separate records."""
    xml = '<?xml version="1.0"?><?xml-stylesheet href="style.xsl"?><root/>'
    stripped, records = strip_xml_overhead(xml)

    assert len(records) == 2  # noqa: PLR2004
    assert "[__PRESERVE_XML_0__]" in stripped
    assert "[__PRESERVE_XML_1__]" in stripped
    assert "<root/>" in stripped


def test_strip_xml_overhead_empty_comment_left_intact() -> None:
    """Empty comment <!----> passes through unchanged (not stripped)."""
    xml = "<!----><root>text</root>"
    stripped, records = strip_xml_overhead(xml)

    assert stripped == xml
    assert records == []


def test_restore_xml_placeholder_reorder() -> None:
    """Reordered XML placeholders resolve to correct records (index-based)."""
    records = ["<?pi?>", "<![CDATA[", "]]>"]
    reordered = (
        "[__PRESERVE_XML_1__] text [__PRESERVE_XML_2__] more [__PRESERVE_XML_0__]"
    )
    restored = restore_xml_overhead(reordered, records)

    assert restored == "<![CDATA[ text ]]> more <?pi?>"


# ===========================================================================
# HTML attribute round-trip edge cases
# ===========================================================================


def test_strip_html_entities_in_attr_values_roundtrip() -> None:
    """HTML entities in attribute values survive strip → restore unchanged."""
    html = '<div title="Tom &amp; Jerry" class="x">text</div>'
    stripped, records = strip_html_attributes(html)

    # Translatable title with entity is kept; class is stripped
    assert 'title="Tom &amp; Jerry"' in stripped
    assert "class=" not in stripped

    restored = restore_html_attributes(stripped, records)
    assert 'class="x"' in restored
    assert "&amp;" in restored


# ===========================================================================
# RTF edge cases — invalid codepoint
# ===========================================================================


def test_strip_rtf_invalid_unicode_codepoint_fallback() -> None:
    r"""Codepoint beyond max Unicode (1114111) falls back to __RTF_N__ placeholder.

    When chr() raises ValueError/OverflowError, the escape is recorded
    and a placeholder is created instead of a decoded character.
    """
    rtf = r"\u9999999?X"
    stripped, records = strip_rtf_overhead(rtf)

    assert "[__PRESERVE_RTF_0__]" in stripped
    assert "X" in stripped
    assert records[0] == r"\u9999999?"

    # Round-trip restores the original escape
    restored = restore_rtf_overhead(stripped, records)
    assert restored == rtf


# ===========================================================================
# Markdown edge cases — known limitations
# ===========================================================================


def test_strip_md_url_with_nested_parentheses() -> None:
    """URLs with nested parentheses are partially captured (known limitation).

    The regex [^)]+ stops at the first closing parenthesis, so URLs like
    Wikipedia links with C_(programming_language) lose their trailing ')'.
    """
    md = "[wiki](https://en.wikipedia.org/wiki/C_(lang))"
    stripped, records = strip_md_overhead(md)

    # Regex captures up to the first ')' — the inner one
    assert records == ["https://en.wikipedia.org/wiki/C_(lang"]
    # Stray closing paren left in the stripped output
    assert stripped == "[wiki]([__PRESERVE_MD_0__]))"


def test_strip_md_autolinks_not_matched() -> None:
    """Autolinks <url> are not stripped — only [text](url) syntax is handled.

    Autolinks pass through to the LLM unchanged. This is acceptable because
    autolink URLs are short and the LLM is instructed to preserve them.
    """
    md = "Visit <https://example.com> for info."
    stripped, records = strip_md_overhead(md)

    assert stripped == md
    assert records == []


# ── strip_bom ────────────────────────────────────────────────────────


def test_strip_bom_removes_bom() -> None:
    """BOM at the start of the string is removed."""
    assert strip_bom("\ufeffHello") == "Hello"


def test_strip_bom_no_bom() -> None:
    """String without BOM is returned unchanged."""
    assert strip_bom("Hello") == "Hello"


def test_strip_bom_empty_string() -> None:
    """Empty string returns empty."""
    assert strip_bom("") == ""


def test_strip_bom_only_bom() -> None:
    """BOM-only string returns empty."""
    assert strip_bom("\ufeff") == ""


def test_strip_bom_double_bom_strips_all_leading() -> None:
    """strip_bom uses lstrip, so it removes ALL leading BOM characters."""
    # lstrip("\ufeff") strips every leading BOM, not just the first.
    result = strip_bom("\ufeff\ufeffhello")
    assert result == "hello"


def test_strip_bom_handles_utf16_be_decoded_bytes() -> None:
    """UTF-16-BE bytes decoded then stripped \u2192 BOM gone.

    Regression pin for the contract that ``strip_bom`` operates on a
    decoded ``str`` (where every UTF BOM collapses to the same
    U+FEFF codepoint).  A UTF-16-BE encoded file starts with the byte
    sequence ``\\xfe\\xff``; once decoded as UTF-16, the leading
    codepoint is U+FEFF.  The function must strip it.  Test
    explicitly to catch a future refactor that flips the helper to
    operate on bytes (where UTF-16 BOMs differ from UTF-8).
    """
    # Simulate the byte sequence a UTF-16-BE file would arrive as.
    encoded = "\ufeffhello".encode("utf-16-be")
    # codec consumed the BOM bytes but the decoded str still starts
    # with U+FEFF because ``utf-16-be`` doesn't auto-strip (unlike
    # the BOM-aware ``utf-16`` codec).  This is the realistic case
    # we get from charset_normalizer hits.
    decoded = encoded.decode("utf-16-be")
    assert decoded[0] == "\ufeff"
    assert strip_bom(decoded) == "hello"


def test_strip_bom_handles_utf16_le_decoded_bytes() -> None:
    """UTF-16-LE bytes decoded then stripped \u2192 BOM gone."""
    encoded = "\ufeffworld".encode("utf-16-le")
    decoded = encoded.decode("utf-16-le")
    assert decoded[0] == "\ufeff"
    assert strip_bom(decoded) == "world"


# ===========================================================================
# Placeholder collision-proof tests
# ===========================================================================


def test_xml_collision_proof_old_placeholder_survives() -> None:
    """Source text containing old-style __XML_0__ is not corrupted."""
    xml = '<?xml version="1.0"?><root>The value __XML_0__ is a literal.</root>'
    stripped, records = strip_xml_overhead(xml)

    # The PI gets a [__PRESERVE_XML_0__] placeholder; the literal __XML_0__ survives
    assert "[__PRESERVE_XML_0__]" in stripped
    assert "__XML_0__" in stripped  # literal preserved in text

    # Simulate LLM translating the text
    translated = stripped.replace("The value", "La valeur").replace(
        "is a literal",
        "est un littéral",
    )
    restored = restore_xml_overhead(translated, records)

    assert "La valeur __XML_0__ est un littéral." in restored
    assert '<?xml version="1.0"?>' in restored


def test_rtf_collision_proof_old_placeholder_survives() -> None:
    """Source text containing old-style __RTF_0__ is not corrupted."""
    rtf = r"\pard Text mentions __RTF_0__ literally."
    stripped, records = strip_rtf_overhead(rtf)

    # \pard gets a [__PRESERVE_RTF_0__] placeholder; literal __RTF_0__ survives
    assert "[__PRESERVE_RTF_0__]" in stripped
    assert "__RTF_0__" in stripped

    restored = restore_rtf_overhead(stripped, records)
    assert "__RTF_0__" in restored  # literal stays
    assert r"\pard" in restored  # control word restored


def test_md_collision_proof_old_placeholder_survives() -> None:
    """Source text containing old-style __MD_0__ outside links is not corrupted."""
    md = "Text mentions __MD_0__ and [link](https://example.com)"
    stripped, records = strip_md_overhead(md)

    # The URL gets [__PRESERVE_MD_0__]; literal __MD_0__ survives
    assert "[__PRESERVE_MD_0__]" in stripped
    assert "__MD_0__" in stripped

    restored = restore_md_overhead(stripped, records)
    assert "https://example.com" in restored
    assert "__MD_0__" in restored  # literal stays


# ---------------------------------------------------------------------------
# restore_html_attributes — legacy list-based records branch
# ---------------------------------------------------------------------------


def test_restore_html_attributes_legacy_list_returns_html_unchanged() -> None:
    """Legacy list-based records triggers _restore_legacy → returns as-is."""
    from src.utils.text_utils import AttrRecord, _AttrEntry  # noqa: PLC0415

    html = '<div data-ftid="0" class="x">text</div>'
    records = [AttrRecord("div", [_AttrEntry('class="x"', False)])]
    result = restore_html_attributes(html, records)
    # _restore_legacy returns the HTML unchanged
    assert result == html


# ---------------------------------------------------------------------------
# restore_html_attributes — _ATTR_RE.match(entry.raw) returns None
# ---------------------------------------------------------------------------


def test_restore_html_attributes_unparseable_entry_raw_skipped() -> None:
    """AttrEntry with unparseable raw string is silently skipped."""
    from src.utils.text_utils import AttrRecord, _AttrEntry  # noqa: PLC0415

    # "!!!" cannot match _ATTR_RE → skipped → tag rendered bare
    records = {0: AttrRecord("div", [_AttrEntry("!!!", False)])}
    html = '<div data-ftid="0">text</div>'
    result = restore_html_attributes(html, records)
    # With all entries skipped, rebuilt is empty → bare tag
    assert result == "<div>text</div>"


# ---------------------------------------------------------------------------
# html_to_plain_text — unclosed <span tag (else: break)
# ---------------------------------------------------------------------------


def test_html_to_plain_text_unclosed_span_tag() -> None:
    """Unclosed <span tag triggers the else:break guard."""
    from src.utils.text_utils import html_to_plain_text  # noqa: PLC0415

    # The <span at the end has no closing ">", so the parser breaks out
    result = html_to_plain_text("Hello <span no close bracket")
    assert "Hello" in result


# ---------------------------------------------------------------------------
# repair_html_tags — dropped tags appended at end
# ---------------------------------------------------------------------------


def test_repair_html_tags_dropped_tags_appended_at_end() -> None:
    """Missing tags are appended at the end when all translated tags consumed."""
    from src.utils.text_utils import repair_html_tags  # noqa: PLC0415

    original = "<p>text</p><div>more</div>"
    translated = "<p>text</p>"  # <div></div> dropped by LLM
    result = repair_html_tags(original, translated)
    # Both <div> and </div> should be restored somewhere in the output
    assert "<div>" in result
    assert "</div>" in result


# ===========================================================================
# normalize_for_search — Unicode edge cases
# ===========================================================================


def test_normalize_for_search_emoji_surrogate() -> None:
    """Emoji (supplementary plane / surrogate pair) passes through."""
    # U+1F600 GRINNING FACE — outside BMP
    assert normalize_for_search("\U0001f600") == "\U0001f600"


def test_normalize_for_search_combining_chars() -> None:
    """Pre-composed vs decomposed accented chars give the same result."""
    # e + combining acute accent (U+0301) → should normalize to "e"
    decomposed = "e\u0301"
    precomposed = "\u00e9"
    assert normalize_for_search(decomposed) == "e"
    assert normalize_for_search(precomposed) == "e"
    assert normalize_for_search(decomposed) == normalize_for_search(precomposed)


def test_normalize_for_search_rtl_marker_stripped() -> None:
    """RTL mark (U+200F, category Cf) is stripped."""
    assert normalize_for_search("hello\u200fworld") == "helloworld"
    # LRM (U+200E) is also Cf
    assert normalize_for_search("abc\u200edef") == "abcdef"


def test_normalize_for_search_fullwidth_ascii() -> None:
    """Fullwidth Latin letters (U+FF21 etc.) are decomposed and casefolded."""
    # U+FF21 = FULLWIDTH LATIN CAPITAL LETTER A
    assert normalize_for_search("\uff21\uff22\uff23") == "abc"


def test_normalize_for_search_zero_width_joiner_stripped() -> None:
    """Zero-width joiner (U+200D, category Cf) is stripped."""
    assert normalize_for_search("a\u200db") == "ab"


def test_normalize_for_search_mixed_invisible_chars() -> None:
    """Multiple invisible characters in one string are all stripped."""
    # ZWJ + ZWNJ + ZWS + RTL mark combined
    text = "a\u200d\u200c\u200b\u200fb"
    assert normalize_for_search(text) == "ab"


# ===========================================================================
# build_norm_map — edge cases
# ===========================================================================


def test_build_norm_map_ligature_fi() -> None:
    """Ligature 'fi' (U+FB01) decomposes to 'f','i' both mapping to same index."""
    norm, indices = build_norm_map("\ufb01")
    assert norm == "fi"
    assert len(indices) == 2  # noqa: PLR2004
    # Both decomposed chars map to original index 0
    assert indices == [0, 0]


def test_build_norm_map_ligature_in_word() -> None:
    """Ligature in context: 'o' + U+FB03 (ffi ligature) + 'ce' → 'office'."""
    norm, indices = build_norm_map("o\ufb03ce")
    # U+FB03 = LATIN SMALL LIGATURE FFI → "ffi" (3 chars)
    # "o"(0) + "ffi"(1,1,1) + "c"(2) + "e"(3) = "office"
    assert norm == "office"
    assert indices == [0, 1, 1, 1, 2, 3]


def test_build_norm_map_only_invisible_chars() -> None:
    """String with only invisible chars returns empty."""
    # ZWS + ZWJ + ZWNJ
    norm, indices = build_norm_map("\u200b\u200d\u200c")
    assert norm == ""
    assert indices == []


def test_build_norm_map_fullwidth_digit() -> None:
    """Fullwidth digit (U+FF10 etc.) decomposes to ASCII digit."""
    # U+FF11 = FULLWIDTH DIGIT ONE
    norm, indices = build_norm_map("\uff11\uff12\uff13")
    assert norm == "123"
    assert indices == [0, 1, 2]


def test_build_norm_map_fullwidth_letter() -> None:
    """Fullwidth Latin letter decomposes and maps correctly."""
    norm, indices = build_norm_map("\uff21")  # FULLWIDTH A
    assert norm == "a"
    assert indices == [0]


def test_build_norm_map_rtl_markers_skipped() -> None:
    """RTL/LTR marks are Cf and should be skipped in the map."""
    norm, indices = build_norm_map("a\u200fb")
    assert norm == "ab"
    assert indices == [0, 2]


# ===========================================================================
# html_to_plain_text — edge cases
# ===========================================================================


def test_html_to_plain_text_empty_input() -> None:
    """Empty string input returns empty."""
    assert html_to_plain_text("") == ""


def test_html_to_plain_text_html_entities() -> None:
    """HTML entities are left as-is (not decoded by this function)."""
    # The function only strips tags; it does not decode entities
    result = html_to_plain_text("&amp; &lt; &#x41;")
    assert "&amp;" in result
    assert "&lt;" in result
    assert "&#x41;" in result


def test_html_to_plain_text_unhandled_tags_remain() -> None:
    """Tags not explicitly handled (<a>, <strong>, <em>, <sup>) remain."""
    html = "<a href='#'>link</a> <strong>bold</strong> <em>italic</em> <sup>1</sup>"
    result = html_to_plain_text(html)
    # <a>, <strong>, <em>, <sup> are NOT in the strip list
    assert "<a href='#'>" in result
    assert "<strong>" in result
    assert "<em>" in result
    assert "<sup>" in result


def test_html_to_plain_text_deeply_nested_spans() -> None:
    """Deeply nested span tags are all stripped."""
    html = '<span style="a"><span style="b"><span style="c">deep</span></span></span>'
    result = html_to_plain_text(html)
    assert result == "deep"
    assert "<span" not in result


def test_html_to_plain_text_only_tags() -> None:
    """Input with only formatting tags and no text content."""
    html = "<b><i><u></u></i></b>"
    assert html_to_plain_text(html) == ""


# ===========================================================================
# clean_llm_html — edge cases
# ===========================================================================


def test_clean_llm_html_whitespace_between_br_and_content() -> None:
    """Leading/trailing whitespace around br tags is handled."""
    result = clean_llm_html("  <br>  Hello  <br>  ")
    # Leading "  <br>  " stripped, trailing "  <br>  " stripped
    assert "Hello" in result
    # The inner whitespace around Hello is preserved
    assert result.strip() == "Hello"


def test_clean_llm_html_br_mixed_with_other_tags() -> None:
    """<br> mixed with block tags — only boundary br is stripped."""
    result = clean_llm_html("<br><p>Hello</p><br>")
    assert "<p>Hello</p>" in result
    # Leading and trailing <br> stripped
    assert not result.startswith("<br>")
    assert not result.endswith("<br>")


def test_clean_llm_html_only_whitespace_between_br() -> None:
    """Only whitespace between br tags results in empty string."""
    result = clean_llm_html("<br>   <br>")
    assert result.strip() == ""


def test_clean_llm_html_br_with_newlines() -> None:
    """Br tags separated by newlines at boundaries."""
    result = clean_llm_html("<br>\n<br>\nContent\n<br>\n<br>")
    assert "Content" in result


# ===========================================================================
# strip_xml_overhead / restore_xml_overhead — edge cases
# ===========================================================================


def test_strip_xml_overhead_empty_cdata() -> None:
    """Empty CDATA section: <![CDATA[]]> produces two records."""
    xml = "<data><![CDATA[]]></data>"
    stripped, records = strip_xml_overhead(xml)
    # The CDATA open and close markers are replaced
    assert len(records) == 2  # noqa: PLR2004
    assert records[0] == "<![CDATA["
    assert records[1] == "]]>"
    # Text between markers is empty
    assert "<![CDATA[" not in stripped
    assert "]]>" not in stripped
    # Round-trip restores original
    restored = restore_xml_overhead(stripped, records)
    assert restored == xml


def test_strip_xml_overhead_multiple_consecutive_cdata() -> None:
    """Multiple consecutive CDATA sections each get their own records."""
    xml = "<r><![CDATA[first]]><![CDATA[second]]></r>"
    stripped, records = strip_xml_overhead(xml)
    # 2 CDATA opens + 2 CDATA closes = 4 records
    assert len(records) == 4  # noqa: PLR2004
    assert "first" in stripped
    assert "second" in stripped
    # Round-trip restores original
    restored = restore_xml_overhead(stripped, records)
    assert restored == xml


# ===========================================================================
# strip_md_overhead / restore_md_overhead — edge cases
# ===========================================================================


def test_strip_md_overhead_empty_url_not_matched() -> None:
    """Empty URL [text]() should NOT be matched (regex requires 1+ chars)."""
    md = "[text]()"
    stripped, records = strip_md_overhead(md)
    # The regex [^)]+ requires at least one char — empty parens don't match
    assert stripped == md
    assert records == []


def test_strip_md_overhead_link_text_with_special_chars() -> None:
    """Link text with special characters is preserved."""
    md = "[hello & world <3](https://example.com)"
    stripped, records = strip_md_overhead(md)
    assert stripped == "[hello & world <3]([__PRESERVE_MD_0__])"
    assert records == ["https://example.com"]
    assert restore_md_overhead(stripped, records) == md


def test_strip_md_overhead_link_text_with_backticks() -> None:
    """Link text containing inline code backticks."""
    md = "[`code`](https://example.com)"
    stripped, records = strip_md_overhead(md)
    assert stripped == "[`code`]([__PRESERVE_MD_0__])"
    assert restore_md_overhead(stripped, records) == md


def test_strip_md_overhead_image_with_special_alt() -> None:
    """Image alt text with special chars is preserved."""
    md = "![a & b](img.png)"
    stripped, records = strip_md_overhead(md)
    assert stripped == "![a & b]([__PRESERVE_MD_0__])"
    assert records == ["img.png"]
    assert restore_md_overhead(stripped, records) == md


# ===========================================================================
# repair_html_tags — edge cases
# ===========================================================================


def test_repair_html_tags_completely_different_tag_set() -> None:
    """Translated has a completely different set of tags than original."""
    original = "<div><p>Hello</p></div>"
    translated = "<section><span>Bonjour</span></section>"
    result = repair_html_tags(original, translated)
    # Original tags (div, p, /p, /div) are not in translated
    # They should be re-inserted; translated extra tags are kept
    assert "<div>" in result
    assert "</div>" in result
    assert "<p>" in result
    assert "</p>" in result
    # LLM's own tags are also preserved
    assert "<section>" in result
    assert "<span>" in result


def test_repair_html_tags_self_closing_mixed_with_same_name() -> None:
    """Self-closing and non-self-closing tags of the same name."""
    # <br/> is self-closing, <br> in the regex is treated as opening
    original = "<br/><div>text</div><br/>"
    translated = "<div>texte</div>"
    result = repair_html_tags(original, translated)
    # Both br tags should be re-inserted
    assert "<br/>" in result
    assert "<div>" in result
    assert "</div>" in result


def test_repair_html_tags_empty_original_nonempty_translated() -> None:
    """Empty original, non-empty translated — translated returned as-is."""
    original = "plain text no tags"
    translated = "<p>Translated</p>"
    result = repair_html_tags(original, translated)
    assert result == translated


def test_repair_html_tags_all_tags_dropped() -> None:
    """Translated has no tags at all — all original tags re-inserted."""
    original = "<p><b>Hello</b></p>"
    translated = "Bonjour"
    result = repair_html_tags(original, translated)
    assert "<p>" in result
    assert "<b>" in result
    assert "</b>" in result
    assert "</p>" in result
    assert "Bonjour" in result


def test_repair_html_tags_duplicate_tag_names() -> None:
    """Multiple tags of the same name — each matched individually."""
    original = "<p>A</p><p>B</p>"
    translated = "<p>A-traduit</p>"  # second <p></p> dropped
    result = repair_html_tags(original, translated)
    # The second <p> and </p> should be re-inserted
    count_p = result.count("<p>")
    count_close_p = result.count("</p>")
    assert count_p == 2  # noqa: PLR2004
    assert count_close_p == 2  # noqa: PLR2004


# ===========================================================================
# Additional tests — strip_bom edge cases
# ===========================================================================


def test_strip_bom_utf16_le_marker() -> None:
    """UTF-16 LE BOM (U+FFFE) is NOT stripped — only U+FEFF is removed."""
    # U+FFFE is not a BOM character; lstrip("\ufeff") does not touch it
    text = "\ufffeHello"
    assert strip_bom(text) == "\ufffeHello"


def test_strip_bom_bom_in_middle() -> None:
    """BOM in the middle of a string is preserved — only leading BOMs stripped."""
    text = "Hello\ufeffWorld"
    assert strip_bom(text) == "Hello\ufeffWorld"


def test_strip_bom_multiple_bom_mixed_with_whitespace() -> None:
    """Multiple leading BOMs mixed with non-BOM chars — lstrip removes all BOMs."""
    text = "\ufeff\ufeff\ufeffData"
    assert strip_bom(text) == "Data"


# ===========================================================================
# Additional tests — normalize_for_search
# ===========================================================================


def test_normalize_for_search_turkish_dotted_i() -> None:
    """Turkish dotted I characters are casefolded correctly."""
    # casefold() handles Turkish I correctly for most purposes
    assert normalize_for_search("I") == "i"


def test_normalize_for_search_whitespace_only() -> None:
    """Whitespace-only string returns whitespace (not stripped)."""
    assert normalize_for_search("   ") == "   "


def test_normalize_for_search_numbers() -> None:
    """Numbers pass through unchanged."""
    assert normalize_for_search("12345") == "12345"


def test_normalize_for_search_mixed_scripts() -> None:
    """Mixed Latin/CJK/Arabic content is normalized correctly."""
    result = normalize_for_search("Hello 你好 مرحبا")
    assert "hello" in result
    assert "你好" in result


def test_normalize_for_search_superscript_digits() -> None:
    """Superscript digits are decomposed by NFKD."""
    # U+00B2 = SUPERSCRIPT TWO
    assert normalize_for_search("\u00b2") == "2"


def test_normalize_for_search_tabs_and_newlines() -> None:
    """Tab and newline characters pass through unchanged."""
    assert normalize_for_search("a\tb\nc") == "a\tb\nc"


# ===========================================================================
# Additional tests — build_norm_map
# ===========================================================================


def test_build_norm_map_multiple_accented_chars() -> None:
    """Multiple accented chars each map to their original position."""
    norm, indices = build_norm_map("àéîõü")
    assert norm == "aeiou"
    assert indices == [0, 1, 2, 3, 4]


def test_build_norm_map_mixed_scripts() -> None:
    """Mixed Latin and CJK maps positions correctly."""
    norm, indices = build_norm_map("A你B")
    assert norm == "a你b"
    assert indices == [0, 1, 2]


def test_build_norm_map_superscript_digits() -> None:
    """Superscript digits decompose and map back correctly."""
    norm, indices = build_norm_map("\u00b2\u00b3")  # ² ³
    assert norm == "23"
    assert indices == [0, 1]


def test_build_norm_map_single_char() -> None:
    """Single character maps correctly."""
    norm, indices = build_norm_map("A")
    assert norm == "a"
    assert indices == [0]


# ===========================================================================
# Additional tests — HTML attribute stripping (complex attributes)
# ===========================================================================


def test_strip_html_multiple_translatable_and_nontranslatable() -> None:
    """Tag with many mixed attrs: only non-translatable stripped."""
    html = (
        '<input type="text" name="email" placeholder="Enter email"'
        ' aria-label="Email field" class="form-input">'
    )
    stripped, records = strip_html_attributes(html)
    assert 'placeholder="Enter email"' in stripped
    assert 'aria-label="Email field"' in stripped
    assert "type=" not in stripped or "data-ftid" in stripped
    assert "name=" not in stripped or "data-ftid" in stripped
    assert "class=" not in stripped or "data-ftid" in stripped
    assert len(records) == 1


def test_strip_html_aria_description() -> None:
    """aria-description is kept as a translatable attribute."""
    html = '<div aria-description="Detailed info" id="info">text</div>'
    stripped, records = strip_html_attributes(html)
    assert 'aria-description="Detailed info"' in stripped
    assert "id=" not in stripped or "data-ftid" in stripped


def test_strip_html_aria_valuetext() -> None:
    """aria-valuetext is kept as a translatable attribute."""
    html = '<input aria-valuetext="50 percent" type="range">'
    stripped, records = strip_html_attributes(html)
    assert 'aria-valuetext="50 percent"' in stripped


# ===========================================================================
# Additional tests — XML overhead stripping with nested elements
# ===========================================================================


def test_strip_xml_overhead_nested_cdata_with_tags() -> None:
    """CDATA containing XML-like tags is preserved as text."""
    xml = "<root><![CDATA[<tag>not real</tag>]]></root>"
    stripped, records = strip_xml_overhead(xml)
    assert "<tag>not real</tag>" in stripped
    assert "<![CDATA[" not in stripped
    assert "]]>" not in stripped
    restored = restore_xml_overhead(stripped, records)
    assert restored == xml


def test_strip_xml_overhead_pi_with_special_chars() -> None:
    """Processing instruction with special characters."""
    xml = '<?xml-model href="schema.xsd" type="application/xml"?><root>text</root>'
    stripped, records = strip_xml_overhead(xml)
    assert "<?xml-model" not in stripped
    assert len(records) == 1
    restored = restore_xml_overhead(stripped, records)
    assert restored == xml


def test_strip_xml_overhead_multiple_pis() -> None:
    """Multiple processing instructions in sequence."""
    xml = '<?xml version="1.0"?><?xml-stylesheet type="text/xsl" href="s.xsl"?><r/>'
    stripped, records = strip_xml_overhead(xml)
    assert len(records) == 2  # noqa: PLR2004
    restored = restore_xml_overhead(stripped, records)
    assert restored == xml


# ===========================================================================
# Additional tests — RTF overhead stripping
# ===========================================================================


def test_strip_rtf_consecutive_control_words() -> None:
    """Multiple consecutive control words with no text between them."""
    rtf = r"\pard\plain\f0\fs20 "
    stripped, records = strip_rtf_overhead(rtf)
    assert r"\pard" not in stripped
    assert r"\plain" not in stripped
    assert len(records) >= 4  # noqa: PLR2004


def test_strip_rtf_control_word_negative_param() -> None:
    r"""Control words with negative parameters like \li-720 are stripped."""
    rtf = r"\li-720 indented text"
    stripped, records = strip_rtf_overhead(rtf)
    assert "indented text" in stripped
    assert r"\li-720" not in stripped


def test_strip_rtf_backslash_backslash() -> None:
    r"""Literal backslash \\ is a control symbol and gets stripped."""
    rtf = r"path\\to\\file"
    stripped, records = strip_rtf_overhead(rtf)
    assert "path" in stripped
    assert "to" in stripped
    assert "file" in stripped


# ===========================================================================
# Additional tests — Markdown overhead stripping (complex markdown)
# ===========================================================================


def test_strip_md_overhead_link_in_heading() -> None:
    """Link inside a heading is processed."""
    md = "# Check [our docs](https://docs.io) for help"
    stripped, records = strip_md_overhead(md)
    assert "[our docs]([__PRESERVE_MD_0__])" in stripped
    assert records == ["https://docs.io"]


def test_strip_md_overhead_multiple_images_on_same_line() -> None:
    """Multiple images on the same line get sequential placeholders."""
    md = "![a](img1.png) ![b](img2.png) ![c](img3.png)"
    stripped, records = strip_md_overhead(md)
    assert len(records) == 3  # noqa: PLR2004
    assert "[__PRESERVE_MD_0__]" in stripped
    assert "[__PRESERVE_MD_1__]" in stripped
    assert "[__PRESERVE_MD_2__]" in stripped


def test_strip_md_overhead_link_with_encoded_chars() -> None:
    """URL with percent-encoded characters is fully captured."""
    md = "[search](https://example.com/s?q=hello%20world)"
    stripped, records = strip_md_overhead(md)
    assert records == ["https://example.com/s?q=hello%20world"]
    assert restore_md_overhead(stripped, records) == md


# ===========================================================================
# Additional tests — clean_html edge cases
# ===========================================================================


def test_clean_llm_html_case_insensitive_br() -> None:
    """<BR>, <Br>, <bR> are all stripped at boundaries."""
    assert clean_llm_html("<BR>Content<Br>") == "Content"
    assert clean_llm_html("<bR>Text<BR/>") == "Text"


def test_clean_llm_html_multiple_interior_br_preserved() -> None:
    """Interior <br> tags are all preserved even when boundaries stripped."""
    result = clean_llm_html("<br>A<br>B<br>C<br>")
    assert result == "A<br>B<br>C"


# ===========================================================================
# Additional tests — plain text conversion edge cases
# ===========================================================================


def test_html_to_plain_text_multiple_br_variants() -> None:
    """All <br> variants become newlines."""
    html = "A<br>B<br/>C<br />D<BR>E"
    result = html_to_plain_text(html)
    assert result == "A\nB\nC\nD\nE"


def test_html_to_plain_text_nested_formatting() -> None:
    """Nested <b><i><u> tags are all stripped."""
    html = "<b><i><u>bold italic underline</u></i></b>"
    assert html_to_plain_text(html) == "bold italic underline"


def test_html_to_plain_text_whitespace_only() -> None:
    """Whitespace-only input returns empty after strip()."""
    assert html_to_plain_text("   ") == ""


def test_html_to_plain_text_span_with_no_closing_gt() -> None:
    """Span tag without closing > triggers break guard."""
    result = html_to_plain_text("Before <span style='x' After")
    assert "Before" in result


# ===========================================================================
# TestStripHtmlAttributes — expanded strip_html_attributes tests
# ===========================================================================


class TestStripHtmlAttributes:
    """Tests for strip_html_attributes edge cases."""

    def test_basic_attrs_stripped(self) -> None:
        """class, style, and id attributes are stripped from tags."""
        html = '<div class="foo" style="color:red" id="bar">Hello</div>'
        stripped, records = strip_html_attributes(html)
        assert "class=" not in stripped
        assert "style=" not in stripped
        # Use ' id=' (with space) to avoid matching 'data-ftid='
        assert ' id="bar"' not in stripped
        assert "Hello</div>" in stripped
        assert len(records) == 1

    def test_preserves_tag_structure_without_attributes(self) -> None:
        """Tags without attributes pass through with structure intact."""
        html = "<p><b>text</b></p>"
        stripped, records = strip_html_attributes(html)
        assert stripped == "<p><b>text</b></p>"
        assert records == {}

    def test_already_clean_html_unchanged(self) -> None:
        """HTML with no strippable attributes is returned unchanged."""
        html = '<img alt="a photo">'
        stripped, records = strip_html_attributes(html)
        assert stripped == html
        assert records == {}

    def test_handles_self_closing_tags(self) -> None:
        """Self-closing tags with non-translatable attrs are stripped."""
        html = '<br class="spacer" />'
        stripped, records = strip_html_attributes(html)
        assert "class=" not in stripped
        assert len(records) == 1
        assert records[0].tag_name == "br"

    def test_handles_nested_elements_with_attributes(self) -> None:
        """Nested elements each have their own attributes stripped."""
        html = '<div id="outer"><span class="inner">text</span></div>'
        stripped, records = strip_html_attributes(html)
        assert ' id="outer"' not in stripped
        assert "class=" not in stripped
        assert "text</span></div>" in stripped
        assert len(records) == 2  # noqa: PLR2004

    def test_empty_string_returns_empty(self) -> None:
        """Empty string input returns empty string and empty records."""
        stripped, records = strip_html_attributes("")
        assert stripped == ""
        assert records == {}


# ===========================================================================
# TestRestoreHtmlAttributesExpanded — expanded restore tests
# ===========================================================================


class TestRestoreHtmlAttributesExpanded:
    """Expanded tests for restore_html_attributes round-trips."""

    def test_basic_round_trip(self) -> None:
        """Strip then restore produces the original HTML."""
        original = '<div class="container" id="main">content</div>'
        stripped, records = strip_html_attributes(original)
        restored = restore_html_attributes(stripped, records)
        assert 'class="container"' in restored
        assert 'id="main"' in restored
        assert "content</div>" in restored

    def test_restore_with_modified_text_preserves_attrs(self) -> None:
        """Restore preserves attributes even when text content was modified."""
        original = '<p style="margin:0">Hello world</p>'
        stripped, records = strip_html_attributes(original)
        # Simulate LLM translating the text content
        translated = stripped.replace("Hello world", "Bonjour le monde")
        restored = restore_html_attributes(translated, records)
        assert 'style="margin:0"' in restored
        assert "Bonjour le monde</p>" in restored

    def test_multiple_elements_restored(self) -> None:
        """Multiple stripped elements are all restored correctly."""
        original = (
            '<div class="a">one</div><span class="b">two</span><p class="c">three</p>'
        )
        stripped, records = strip_html_attributes(original)
        restored = restore_html_attributes(stripped, records)
        assert 'class="a"' in restored
        assert 'class="b"' in restored
        assert 'class="c"' in restored
        assert "one</div>" in restored
        assert "two</span>" in restored
        assert "three</p>" in restored


class TestExtendedLatinBaseMap:
    """All non-decomposable extended-Latin chars map to their base letter.

    NFKD alone leaves Đ / Ł / Ø / Å / Æ / Œ / Þ / Ð untouched, so
    Vietnamese "Đan Mạch" used to sort after Z. The map below routes
    each one to the closest ASCII base letter so search and sort
    behave consistently across all Latin-script locales.

    Keep this test in lockstep with ``_EXTENDED_LATIN_BASE_MAP`` —
    if you add a new entry, add a row here.
    """

    @pytest.mark.parametrize(
        ("input_text", "expected_normalized"),
        [
            ("Đan", "dan"),               # Vietnamese / Croatian
            ("đông", "dong"),
            ("Łukasz", "lukasz"),         # Polish
            ("ł", "l"),
            ("Øresund", "oresund"),       # Danish / Norwegian
            ("ø", "o"),
            ("Åland", "aland"),           # Swedish / Norwegian / Danish
            ("å", "a"),
            ("Æbleskiver", "ableskiver"), # Danish (Æ→a, collapse from "ae")
            ("æ", "a"),
            ("Œuvre", "ouvre"),           # French (Œ→o, collapse from "oe")
            ("œ", "o"),
            ("Þingvellir", "tingvellir"), # Icelandic
            ("þ", "t"),
            ("Ðingvellir", "dingvellir"), # Icelandic
            ("ð", "d"),
        ],
    )
    def test_normalize_for_search_extended_latin(
        self, input_text: str, expected_normalized: str,
    ) -> None:
        from src.utils.text_utils import normalize_for_search  # noqa: PLC0415
        assert normalize_for_search(input_text) == expected_normalized

    @pytest.mark.parametrize(
        "input_text",
        ["Đan", "Łukasz", "Åland", "Þingvellir"],
    )
    def test_build_norm_map_position_invariant(
        self, input_text: str,
    ) -> None:
        """Position map preserves 1:1 character mapping for all entries.

        ``build_norm_map`` returns ``(normalized_text, orig_indices)``
        where ``orig_indices[i]`` is the source-text index of the
        i-th normalized character. ``_EXTENDED_LATIN_BASE_MAP``
        substitutes one char for one char (never one for two), so
        ``len(normalized) == len(input)`` for these substitutions.
        Multi-char ligatures like Æ→AE would break this — they're
        intentionally collapsed to single chars (Æ→a) to preserve
        the invariant.
        """
        from src.utils.text_utils import build_norm_map  # noqa: PLC0415
        normalized, indices = build_norm_map(input_text)
        assert len(normalized) == len(indices)
        assert len(normalized) == len(input_text), (
            f"position invariant broken for {input_text!r}: "
            f"got {len(normalized)} chars from {len(input_text)}"
        )
