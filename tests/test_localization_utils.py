"""Unit tests for localization file parsing and serialization utilities."""

import pytest

from src.utils.localization_utils import (
    LocalizationEntry,
    _escape_po,
    _unescape_po,
    is_localization_format,
    parse_localization,
    parse_po,
    parse_xliff,
    serialize_localization,
    serialize_po,
    serialize_xliff,
)

# ---------------------------------------------------------------------------
# is_localization_format
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ext", [".po", ".pot", ".xliff", ".xlf"])
def test_is_localization_format_true(ext: str) -> None:
    """Known localization extensions return True."""
    assert is_localization_format(ext) is True


@pytest.mark.parametrize("ext", [".txt", ".json", ".srt", ".xml", ".csv"])
def test_is_localization_format_false(ext: str) -> None:
    """Non-localization extensions return False."""
    assert is_localization_format(ext) is False


# ---------------------------------------------------------------------------
# PO escape / unescape
# ---------------------------------------------------------------------------


def test_unescape_po_newline() -> None:
    r"""Escaped \n becomes a real newline."""
    assert _unescape_po(r"Hello\nWorld") == "Hello\nWorld"


def test_unescape_po_tab() -> None:
    r"""Escaped \t becomes a real tab."""
    assert _unescape_po(r"Hello\tWorld") == "Hello\tWorld"


def test_unescape_po_quote() -> None:
    r"""Escaped \" becomes a real quote."""
    assert _unescape_po(r"Say \"hello\"") == 'Say "hello"'


def test_unescape_po_backslash() -> None:
    r"""Escaped \\ becomes a single backslash."""
    assert _unescape_po(r"path\\to\\file") == "path\\to\\file"


def test_escape_po_roundtrip() -> None:
    """Escaping then unescaping returns the original string."""
    original = 'Hello\n"World"\t\\'
    assert _unescape_po(_escape_po(original)) == original


# ---------------------------------------------------------------------------
# PO parsing
# ---------------------------------------------------------------------------


_SAMPLE_PO = """\
# Translation file
msgid ""
msgstr ""
"Content-Type: text/plain; charset=UTF-8\\n"
"Plural-Forms: nplurals=2; plural=(n != 1);\\n"

#: src/login.py:42
#. Greeting message
msgid "Welcome back!"
msgstr "Bon retour !"

#: src/login.py:45
#, fuzzy
msgid "Forgot your password?"
msgstr "Mot de passe oublié ?"
"""


def test_parse_po_basic() -> None:
    """Parses a standard PO file with two entries."""
    entries, header = parse_po(_SAMPLE_PO)
    assert len(header) == 1  # Header block preserved
    assert len(entries) == 2  # noqa: PLR2004
    assert entries[0].msgid == "Welcome back!"
    assert entries[0].msgstr == "Bon retour !"
    assert entries[1].msgid == "Forgot your password?"


def test_parse_po_header_skipped() -> None:
    """Header entry (empty msgid) is not in the entries list."""
    entries, header = parse_po(_SAMPLE_PO)
    for entry in entries:
        assert entry.msgid != ""


def test_parse_po_header_preserved() -> None:
    """Header block is preserved for serialization."""
    _, header = parse_po(_SAMPLE_PO)
    assert len(header) == 1
    assert "Content-Type" in header[0]


def test_parse_po_comments() -> None:
    """Comment lines are stored in metadata."""
    entries, _ = parse_po(_SAMPLE_PO)
    comments = entries[0].metadata["comments"]
    assert any("#: src/login.py:42" in c for c in comments)
    assert any("#." in c for c in comments)


def test_parse_po_fuzzy_flag() -> None:
    """Fuzzy flag is parsed from #, comment."""
    entries, _ = parse_po(_SAMPLE_PO)
    assert "fuzzy" in entries[1].metadata["flags"]


def test_parse_po_empty_msgstr() -> None:
    """POT-style entries with empty msgstr parse correctly."""
    content = 'msgid ""\nmsgstr ""\n\nmsgid "Hello"\nmsgstr ""\n'
    entries, _ = parse_po(content)
    assert len(entries) == 1
    assert entries[0].msgid == "Hello"
    assert entries[0].msgstr == ""


def test_parse_po_multiline_strings() -> None:
    """Multiline quoted strings are concatenated."""
    content = (
        'msgid ""\nmsgstr ""\n\nmsgid ""\n"Hello "\n"World"\nmsgstr "Bonjour Monde"\n'
    )
    entries, _ = parse_po(content)
    assert entries[0].msgid == "Hello World"


def test_parse_po_with_context() -> None:
    """Msgctxt field is parsed as context."""
    content = 'msgid ""\nmsgstr ""\n\nmsgctxt "menu"\nmsgid "File"\nmsgstr "Fichier"\n'
    entries, _ = parse_po(content)
    assert entries[0].context == "menu"
    assert entries[0].msgid == "File"


def test_parse_po_plural_forms() -> None:
    """Plural entries are parsed with msgid_plural and msgstr[N]."""
    content = (
        'msgid ""\nmsgstr ""\n\n'
        'msgid "One item"\n'
        'msgid_plural "%d items"\n'
        'msgstr[0] "Un élément"\n'
        'msgstr[1] "%d éléments"\n'
    )
    entries, _ = parse_po(content)
    assert entries[0].msgid == "One item"
    assert entries[0].metadata["msgid_plural"] == "%d items"
    assert entries[0].metadata["msgstr_plural"][0] == "Un élément"
    assert entries[0].metadata["msgstr_plural"][1] == "%d éléments"


def test_parse_po_escaped_chars() -> None:
    """Escaped characters in strings are unescaped."""
    content = 'msgid ""\nmsgstr ""\n\nmsgid "Line1\\nLine2"\nmsgstr "Ligne1\\nLigne2"\n'
    entries, _ = parse_po(content)
    assert entries[0].msgid == "Line1\nLine2"


def test_parse_po_empty() -> None:
    """Empty content returns no entries."""
    entries, header = parse_po("")
    assert entries == []
    assert header == []


def test_parse_po_bom() -> None:
    """UTF-8 BOM is stripped before parsing."""
    content = '\ufeffmsgid ""\nmsgstr ""\n\nmsgid "Hello"\nmsgstr ""\n'
    entries, _ = parse_po(content)
    assert len(entries) == 1


def test_parse_po_only_header() -> None:
    """File with only a header returns no translatable entries."""
    content = 'msgid ""\nmsgstr ""\n"Content-Type: text/plain\\n"\n'
    entries, header = parse_po(content)
    assert entries == []
    assert len(header) == 1


def test_parse_po_multiple_flags() -> None:
    """Multiple flags on one #, line are all parsed."""
    content = (
        'msgid ""\nmsgstr ""\n\n#, fuzzy, python-format\nmsgid "Hello %s"\nmsgstr ""\n'
    )
    entries, _ = parse_po(content)
    flags = entries[0].metadata["flags"]
    assert "fuzzy" in flags
    assert "python-format" in flags


# ---------------------------------------------------------------------------
# PO serialization
# ---------------------------------------------------------------------------


def test_serialize_po_roundtrip() -> None:
    """Parse then serialize then re-parse yields same entries."""
    entries, header = parse_po(_SAMPLE_PO)
    result = serialize_po(entries, header)
    entries2, _ = parse_po(result)
    assert len(entries2) == len(entries)
    assert entries2[0].msgid == entries[0].msgid
    assert entries2[1].msgid == entries[1].msgid


def test_serialize_po_preserves_header() -> None:
    """Header block appears at the top of the serialized output."""
    entries, header = parse_po(_SAMPLE_PO)
    result = serialize_po(entries, header)
    assert result.startswith("# Translation file")


def test_serialize_po_preserves_comments() -> None:
    """Source reference and extracted comments are preserved."""
    entries, header = parse_po(_SAMPLE_PO)
    result = serialize_po(entries, header)
    assert "#: src/login.py:42" in result
    assert "#. Greeting message" in result


def test_serialize_po_removes_fuzzy() -> None:
    """Fuzzy flag is removed from serialized output."""
    entries, header = parse_po(_SAMPLE_PO)
    result = serialize_po(entries, header)
    assert "#, fuzzy" not in result


def test_serialize_po_preserves_non_fuzzy_flags() -> None:
    """Non-fuzzy flags are preserved even when fuzzy is removed."""
    content = (
        'msgid ""\nmsgstr ""\n\n'
        "#, fuzzy, python-format\n"
        'msgid "Hello %s"\n'
        'msgstr "Bonjour %s"\n'
    )
    entries, header = parse_po(content)
    result = serialize_po(entries, header)
    assert "python-format" in result
    assert "fuzzy" not in result


def test_serialize_po_plural_forms() -> None:
    """Plural msgstr[N] entries are written correctly."""
    entries = [
        LocalizationEntry(
            index=0,
            msgid="One item",
            msgstr="Un élément",
            metadata={
                "comments": [],
                "flags": set(),
                "msgid_plural": "%d items",
                "msgstr_plural": {0: "Un élément", 1: "%d éléments"},
            },
        ),
    ]
    result = serialize_po(entries, [])
    assert 'msgid_plural "%d items"' in result
    assert 'msgstr[0] "Un \\u00e9l\\u00e9ment"' in result or "msgstr[0]" in result
    assert "msgstr[1]" in result


def test_serialize_po_escaping() -> None:
    """Special characters are properly escaped in output."""
    entries = [
        LocalizationEntry(
            index=0,
            msgid='Say "hello"\nworld',
            msgstr='Dire "bonjour"\nmonde',
            metadata={"comments": [], "flags": set()},
        ),
    ]
    result = serialize_po(entries, [])
    assert r"\"hello\"" in result
    assert r"\n" in result


def test_serialize_po_context() -> None:
    """Msgctxt is included in serialized output."""
    entries = [
        LocalizationEntry(
            index=0,
            msgid="File",
            msgstr="Fichier",
            context="menu",
            metadata={"comments": [], "flags": set()},
        ),
    ]
    result = serialize_po(entries, [])
    assert 'msgctxt "menu"' in result


# ---------------------------------------------------------------------------
# XLIFF 1.2 parsing
# ---------------------------------------------------------------------------


_SAMPLE_XLIFF_12 = """\
<?xml version="1.0" encoding="UTF-8"?>
<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2">
  <file source-language="en" target-language="fr" datatype="plaintext">
    <body>
      <trans-unit id="1">
        <source>Hello</source>
        <target>Bonjour</target>
        <note>Greeting</note>
      </trans-unit>
      <trans-unit id="2">
        <source>World</source>
      </trans-unit>
      <trans-unit id="3" translate="no">
        <source>API_KEY</source>
      </trans-unit>
    </body>
  </file>
</xliff>"""


def test_parse_xliff12_basic() -> None:
    """Parses XLIFF 1.2 trans-units correctly."""
    entries, _ = parse_xliff(_SAMPLE_XLIFF_12)
    assert len(entries) == 2  # noqa: PLR2004 — unit 3 is translate="no"
    assert entries[0].msgid == "Hello"
    assert entries[0].msgstr == "Bonjour"
    assert entries[1].msgid == "World"
    assert entries[1].msgstr == ""


def test_parse_xliff12_translate_no() -> None:
    """Units with translate='no' are skipped."""
    entries, _ = parse_xliff(_SAMPLE_XLIFF_12)
    for entry in entries:
        assert entry.msgid != "API_KEY"


def test_parse_xliff12_notes() -> None:
    """Note elements are stored as context."""
    entries, _ = parse_xliff(_SAMPLE_XLIFF_12)
    assert entries[0].context == "Greeting"


def test_parse_xliff12_unit_id() -> None:
    """Unit ID is stored in metadata."""
    entries, _ = parse_xliff(_SAMPLE_XLIFF_12)
    assert entries[0].metadata["unit_id"] == "1"
    assert entries[1].metadata["unit_id"] == "2"


def test_parse_xliff12_missing_target() -> None:
    """Source-only units have empty msgstr."""
    entries, _ = parse_xliff(_SAMPLE_XLIFF_12)
    assert entries[1].msgstr == ""


def test_parse_xliff12_empty() -> None:
    """XLIFF with no trans-units returns empty list."""
    content = (
        '<?xml version="1.0"?>'
        '<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2">'
        "<file><body></body></file></xliff>"
    )
    entries, _ = parse_xliff(content)
    assert entries == []


def test_parse_xliff12_multiple_files() -> None:
    """Trans-units from multiple <file> elements are all extracted."""
    content = (
        '<?xml version="1.0"?>'
        '<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2">'
        "<file><body>"
        '<trans-unit id="1"><source>Hello</source></trans-unit>'
        "</body></file>"
        "<file><body>"
        '<trans-unit id="2"><source>World</source></trans-unit>'
        "</body></file>"
        "</xliff>"
    )
    entries, _ = parse_xliff(content)
    assert len(entries) == 2  # noqa: PLR2004


# ---------------------------------------------------------------------------
# XLIFF 1.2 serialization
# ---------------------------------------------------------------------------


def test_serialize_xliff12_roundtrip() -> None:
    """Parse, translate, serialize, re-parse yields translations."""
    entries, root = parse_xliff(_SAMPLE_XLIFF_12)
    entries[0].msgstr = "Salut"
    entries[1].msgstr = "Monde"
    result = serialize_xliff(entries, root)

    entries2, _ = parse_xliff(result)
    assert entries2[0].msgstr == "Salut"
    assert entries2[1].msgstr == "Monde"


def test_serialize_xliff12_creates_target() -> None:
    """Target element is created when missing."""
    entries, root = parse_xliff(_SAMPLE_XLIFF_12)
    entries[1].msgstr = "Monde"
    result = serialize_xliff(entries, root)
    assert "Monde" in result


def test_serialize_xliff12_preserves_structure() -> None:
    """Non-translatable XML attributes and elements are preserved."""
    entries, root = parse_xliff(_SAMPLE_XLIFF_12)
    result = serialize_xliff(entries, root)
    assert "source-language" in result or "datatype" in result
    assert "translate" in result  # translate="no" unit preserved


def test_serialize_xliff12_sets_state() -> None:
    """Target elements get state='translated'."""
    entries, root = parse_xliff(_SAMPLE_XLIFF_12)
    entries[0].msgstr = "Salut"
    result = serialize_xliff(entries, root)
    assert 'state="translated"' in result


# ---------------------------------------------------------------------------
# XLIFF 2.0 parsing
# ---------------------------------------------------------------------------


_SAMPLE_XLIFF_20 = """\
<?xml version="1.0" encoding="UTF-8"?>
<xliff xmlns="urn:oasis:names:tc:xliff:document:2.0"
       version="2.0" srcLang="en" trgLang="fr">
  <file id="f1">
    <unit id="u1">
      <segment>
        <source>Hello</source>
        <target>Bonjour</target>
      </segment>
    </unit>
    <unit id="u2">
      <segment>
        <source>World</source>
      </segment>
    </unit>
    <unit id="u3" translate="no">
      <segment>
        <source>DO_NOT_TRANSLATE</source>
      </segment>
    </unit>
  </file>
</xliff>"""


def test_parse_xliff20_basic() -> None:
    """Parses XLIFF 2.0 units correctly."""
    entries, _ = parse_xliff(_SAMPLE_XLIFF_20)
    assert len(entries) == 2  # noqa: PLR2004
    assert entries[0].msgid == "Hello"
    assert entries[0].msgstr == "Bonjour"
    assert entries[1].msgid == "World"


def test_parse_xliff20_translate_no() -> None:
    """Units with translate='no' are skipped."""
    entries, _ = parse_xliff(_SAMPLE_XLIFF_20)
    for entry in entries:
        assert entry.msgid != "DO_NOT_TRANSLATE"


def test_parse_xliff20_missing_target() -> None:
    """Source-only segments have empty msgstr."""
    entries, _ = parse_xliff(_SAMPLE_XLIFF_20)
    assert entries[1].msgstr == ""


def test_parse_xliff20_unit_id() -> None:
    """Unit ID is stored in metadata."""
    entries, _ = parse_xliff(_SAMPLE_XLIFF_20)
    assert entries[0].metadata["unit_id"] == "u1"


def test_parse_xliff20_empty() -> None:
    """XLIFF 2.0 with no units returns empty list."""
    content = (
        '<?xml version="1.0"?>'
        '<xliff xmlns="urn:oasis:names:tc:xliff:document:2.0" version="2.0"'
        ' srcLang="en" trgLang="fr">'
        '<file id="f1"></file></xliff>'
    )
    entries, _ = parse_xliff(content)
    assert entries == []


# ---------------------------------------------------------------------------
# XLIFF 2.0 serialization
# ---------------------------------------------------------------------------


def test_serialize_xliff20_roundtrip() -> None:
    """Parse, translate, serialize, re-parse yields translations."""
    entries, root = parse_xliff(_SAMPLE_XLIFF_20)
    entries[0].msgstr = "Salut"
    entries[1].msgstr = "Monde"
    result = serialize_xliff(entries, root)

    entries2, _ = parse_xliff(result)
    assert entries2[0].msgstr == "Salut"
    assert entries2[1].msgstr == "Monde"


def test_serialize_xliff20_creates_target() -> None:
    """Target element is created when missing in XLIFF 2.0."""
    entries, root = parse_xliff(_SAMPLE_XLIFF_20)
    entries[1].msgstr = "Monde"
    result = serialize_xliff(entries, root)
    assert "Monde" in result


# ---------------------------------------------------------------------------
# Version detection
# ---------------------------------------------------------------------------


def test_xliff_version_detection_12() -> None:
    """XLIFF 1.2 namespace is detected correctly."""
    entries, _ = parse_xliff(_SAMPLE_XLIFF_12)
    # If it parsed trans-units, it detected 1.2
    assert len(entries) == 2  # noqa: PLR2004


def test_xliff_version_detection_20() -> None:
    """XLIFF 2.0 namespace is detected correctly."""
    entries, _ = parse_xliff(_SAMPLE_XLIFF_20)
    # If it parsed units/segments, it detected 2.0
    assert len(entries) == 2  # noqa: PLR2004


# ---------------------------------------------------------------------------
# Unified dispatchers
# ---------------------------------------------------------------------------


def test_parse_localization_po() -> None:
    """parse_localization dispatches to PO parser."""
    entries, _ = parse_localization(_SAMPLE_PO, ".po")
    assert len(entries) == 2  # noqa: PLR2004


def test_parse_localization_pot() -> None:
    """parse_localization dispatches to PO parser for .pot."""
    content = 'msgid ""\nmsgstr ""\n\nmsgid "Hello"\nmsgstr ""\n'
    entries, _ = parse_localization(content, ".pot")
    assert len(entries) == 1


def test_parse_localization_xliff() -> None:
    """parse_localization dispatches to XLIFF parser for .xliff."""
    entries, _ = parse_localization(_SAMPLE_XLIFF_12, ".xliff")
    assert len(entries) == 2  # noqa: PLR2004


def test_parse_localization_xlf() -> None:
    """parse_localization dispatches to XLIFF parser for .xlf."""
    entries, _ = parse_localization(_SAMPLE_XLIFF_20, ".xlf")
    assert len(entries) == 2  # noqa: PLR2004


def test_parse_localization_unsupported() -> None:
    """Unsupported extension raises ValueError."""
    with pytest.raises(ValueError, match="Unsupported localization format"):
        parse_localization("data", ".txt")


def test_serialize_localization_unsupported() -> None:
    """Unsupported extension raises ValueError."""
    with pytest.raises(ValueError, match="Unsupported localization format"):
        serialize_localization([], None, ".txt")


# ---------------------------------------------------------------------------
# XLIFF 1.2 namespace preservation
# ---------------------------------------------------------------------------

_XLIFF_12_SAMPLE = """\
<?xml version='1.0' encoding='UTF-8'?>
<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2">
  <file source-language="en" target-language="vi" datatype="plaintext">
    <body>
      <trans-unit id="1">
        <source>Hello</source>
        <target>Xin chào</target>
      </trans-unit>
    </body>
  </file>
</xliff>
"""


def test_xliff_12_no_ns0_prefix() -> None:
    """Round-trip XLIFF 1.2 output must not contain ns0: namespace prefix."""
    entries, root = parse_xliff(_XLIFF_12_SAMPLE)
    output = serialize_xliff(entries, root)
    assert "ns0:" not in output


# ---------------------------------------------------------------------------
# _detect_xliff_version — fallback to version attribute
# ---------------------------------------------------------------------------


def test_xliff_version_detection_no_namespace_defaults_to_12() -> None:
    """XLIFF without namespace uses version attr, defaulting to 1.2."""
    import xml.etree.ElementTree as ET  # noqa: PLC0415

    from src.utils.localization_utils import _detect_xliff_version  # noqa: PLC0415

    root = ET.fromstring('<xliff version="1.2"><file/></xliff>')
    assert _detect_xliff_version(root) == "1.2"


def test_xliff_version_detection_no_namespace_version_2() -> None:
    """XLIFF without namespace but version='2.0' is detected as 2.0."""
    import xml.etree.ElementTree as ET  # noqa: PLC0415

    from src.utils.localization_utils import _detect_xliff_version  # noqa: PLC0415

    root = ET.fromstring('<xliff version="2.0"><file/></xliff>')
    assert _detect_xliff_version(root) == "2.0"


def test_xliff_version_detection_no_version_attr_defaults_12() -> None:
    """XLIFF without namespace and no version attr defaults to 1.2."""
    import xml.etree.ElementTree as ET  # noqa: PLC0415

    from src.utils.localization_utils import _detect_xliff_version  # noqa: PLC0415

    root = ET.fromstring("<xliff><file/></xliff>")
    assert _detect_xliff_version(root) == "1.2"


# ---------------------------------------------------------------------------
# _parse_xliff_20 — empty source element is skipped
# ---------------------------------------------------------------------------


def test_parse_xliff20_empty_source_skipped() -> None:
    """XLIFF 2.0 segment with empty source text is skipped."""
    xliff = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<xliff xmlns="urn:oasis:names:tc:xliff:document:2.0"'
        ' version="2.0" srcLang="en" trgLang="fr">\n'
        '  <file id="f1">\n'
        '    <unit id="u1">\n'
        "      <segment>\n"
        "        <source></source>\n"
        "      </segment>\n"
        "    </unit>\n"
        '    <unit id="u2">\n'
        "      <segment>\n"
        "        <source>Hello</source>\n"
        "      </segment>\n"
        "    </unit>\n"
        "  </file>\n"
        "</xliff>"
    )
    entries, _ = parse_xliff(xliff)
    assert len(entries) == 1
    assert entries[0].msgid == "Hello"


def test_parse_xliff20_whitespace_only_source_skipped() -> None:
    """XLIFF 2.0 segment with whitespace-only source text is skipped."""
    xliff = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<xliff xmlns="urn:oasis:names:tc:xliff:document:2.0"'
        ' version="2.0" srcLang="en" trgLang="fr">\n'
        '  <file id="f1">\n'
        '    <unit id="u1">\n'
        "      <segment>\n"
        "        <source>   </source>\n"
        "      </segment>\n"
        "    </unit>\n"
        '    <unit id="u2">\n'
        "      <segment>\n"
        "        <source>World</source>\n"
        "      </segment>\n"
        "    </unit>\n"
        "  </file>\n"
        "</xliff>"
    )
    entries, _ = parse_xliff(xliff)
    assert len(entries) == 1
    assert entries[0].msgid == "World"


# ---------------------------------------------------------------------------
# parse_xliff — malformed XML
# ---------------------------------------------------------------------------


def test_parse_xliff_malformed_xml_raises() -> None:
    """Malformed XML raises ET.ParseError (XMLSyntaxError)."""
    import xml.etree.ElementTree as ET  # noqa: PLC0415, N817

    with pytest.raises(ET.ParseError):
        parse_xliff("<xliff><unclosed>")


# ---------------------------------------------------------------------------
# parse_po — msgid_plural without msgstr[N]
# ---------------------------------------------------------------------------


def test_parse_po_plural_without_msgstr_n() -> None:
    """PO entry with msgid_plural but no msgstr[N] still parses."""
    content = (
        '# comment\nmsgid ""\nmsgstr ""\n'
        '"Content-Type: text/plain; charset=UTF-8\\n"\n\n'
        'msgid "apple"\nmsgid_plural "apples"\n'
        'msgstr ""\n'
    )
    entries, _ = parse_po(content)
    # Should parse without crash; exact count may vary
    assert isinstance(entries, list)


# ---------------------------------------------------------------------------
# serialize_po — entry with escaped newlines
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# _parse_po_block — bare continuation line before any keyword
# ---------------------------------------------------------------------------


def test_parse_po_bare_continuation_before_keyword_ignored() -> None:
    """A quoted continuation line before any keyword is silently ignored."""
    content = '"orphan continuation"\n\nmsgid "Hello"\nmsgstr "World"\n'
    entries, _ = parse_po(content)
    # Only one real entry should be parsed
    assert len(entries) == 1
    assert entries[0].msgid == "Hello"


# ---------------------------------------------------------------------------
# parse_po — duplicate empty msgid after header
# ---------------------------------------------------------------------------


def test_parse_po_second_empty_msgid_skipped() -> None:
    """A second entry with empty msgid (after header) is silently skipped."""
    content = (
        'msgid ""\nmsgstr "header"\n\n'
        'msgid ""\nmsgstr "duplicate header"\n\n'
        'msgid "Real"\nmsgstr "Entry"\n'
    )
    entries, header_lines = parse_po(content)
    assert len(header_lines) == 1
    # Only the real entry should survive
    assert len(entries) == 1
    assert entries[0].msgid == "Real"


def test_serialize_po_round_trip_preserves_structure() -> None:
    """PO round-trip (parse → set msgstr → serialize) preserves format."""
    content = (
        '# comment\nmsgid ""\nmsgstr ""\n'
        '"Content-Type: text/plain; charset=UTF-8\\n"\n\n'
        'msgid "greeting"\nmsgstr ""\n'
    )
    entries, structure = parse_po(content)
    # Set translation
    for e in entries:
        if e.msgid == "greeting":
            e.msgstr = "Bonjour"
    result = serialize_po(entries, structure)
    assert 'msgid "greeting"' in result
    assert 'msgstr "Bonjour"' in result


# ---------------------------------------------------------------------------
# _parse_xliff_12 — translate="NO" (uppercase) is case-insensitive
# ---------------------------------------------------------------------------


def test_parse_xliff12_translate_no_uppercase_case_insensitive() -> None:
    """translate='NO' (uppercase) is skipped due to .lower() comparison."""
    xliff = """\
<?xml version="1.0" encoding="UTF-8"?>
<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2">
  <file source-language="en" target-language="fr" datatype="plaintext">
    <body>
      <trans-unit id="1">
        <source>Hello</source>
        <target>Bonjour</target>
      </trans-unit>
      <trans-unit id="2" translate="NO">
        <source>SKIP_ME</source>
      </trans-unit>
    </body>
  </file>
</xliff>"""
    entries, _ = parse_xliff(xliff)
    assert len(entries) == 1
    assert entries[0].msgid == "Hello"
    assert all(e.msgid != "SKIP_ME" for e in entries)


# ---------------------------------------------------------------------------
# PO plural forms — parse and serialize roundtrip
# ---------------------------------------------------------------------------


def test_parse_po_plural_forms_msgstr_indices() -> None:
    """Plural entries with msgstr[0] and msgstr[1] are parsed correctly."""
    content = (
        'msgid ""\nmsgstr ""\n\n'
        'msgid "One file"\n'
        'msgid_plural "%d files"\n'
        'msgstr[0] "Un fichier"\n'
        'msgstr[1] "%d fichiers"\n'
    )
    entries, _ = parse_po(content)
    assert len(entries) == 1
    assert entries[0].msgid == "One file"
    assert entries[0].metadata["msgid_plural"] == "%d files"
    plural_map = entries[0].metadata["msgstr_plural"]
    assert plural_map[0] == "Un fichier"
    assert plural_map[1] == "%d fichiers"

    # Serialize roundtrip
    result = serialize_po(entries, [])
    assert 'msgid_plural "%d files"' in result
    assert "msgstr[0]" in result
    assert "msgstr[1]" in result

    # Re-parse and verify
    entries2, _ = parse_po(result)
    assert entries2[0].metadata["msgstr_plural"][0] == "Un fichier"
    assert entries2[0].metadata["msgstr_plural"][1] == "%d fichiers"


# ---------------------------------------------------------------------------
# PO flags preserved — reference (#:), comment (#.), flags (#,)
# ---------------------------------------------------------------------------


def test_parse_po_flags_preserved() -> None:
    """Reference, extracted comment, and flag lines are all preserved."""
    content = (
        'msgid ""\nmsgstr ""\n\n'
        "#: src/app.py:100\n"
        "#. Login button label\n"
        "#, python-format\n"
        'msgid "Login %s"\n'
        'msgstr "Connexion %s"\n'
    )
    entries, _ = parse_po(content)
    assert len(entries) == 1
    comments = entries[0].metadata["comments"]
    # Reference preserved
    assert any("#: src/app.py:100" in c for c in comments)
    # Extracted comment preserved
    assert any("#. Login button label" in c for c in comments)
    # Flag preserved
    assert "python-format" in entries[0].metadata["flags"]

    # Serialize and verify comments survive roundtrip
    result = serialize_po(entries, [])
    assert "#: src/app.py:100" in result
    assert "#. Login button label" in result
    assert "python-format" in result


# ---------------------------------------------------------------------------
# XLIFF 2.0 — full roundtrip (parse → modify → serialize → re-parse)
# ---------------------------------------------------------------------------


def test_xliff_20_roundtrip() -> None:
    """XLIFF 2.0 parse → modify translations → serialize → re-parse."""
    xliff_content = """\
<?xml version="1.0" encoding="UTF-8"?>
<xliff xmlns="urn:oasis:names:tc:xliff:document:2.0"
       version="2.0" srcLang="en" trgLang="de">
  <file id="f1">
    <unit id="u1">
      <segment>
        <source>Good morning</source>
        <target>Bonjour</target>
      </segment>
    </unit>
    <unit id="u2">
      <segment>
        <source>Good night</source>
      </segment>
    </unit>
  </file>
</xliff>"""

    # Parse
    entries, root = parse_xliff(xliff_content)
    assert len(entries) == 2  # noqa: PLR2004
    assert entries[0].msgid == "Good morning"
    assert entries[0].msgstr == "Bonjour"
    assert entries[1].msgid == "Good night"
    assert entries[1].msgstr == ""

    # Modify translations
    entries[0].msgstr = "Guten Morgen"
    entries[1].msgstr = "Gute Nacht"

    # Serialize
    result = serialize_xliff(entries, root)
    assert "Guten Morgen" in result
    assert "Gute Nacht" in result

    # Re-parse to verify structural integrity
    entries2, _ = parse_xliff(result)
    assert len(entries2) == 2  # noqa: PLR2004
    assert entries2[0].msgstr == "Guten Morgen"
    assert entries2[1].msgstr == "Gute Nacht"
    # Source text unchanged
    assert entries2[0].msgid == "Good morning"
    assert entries2[1].msgid == "Good night"


# ---------------------------------------------------------------------------
# XLIFF — target element exists but is empty
# ---------------------------------------------------------------------------


def test_parse_xliff_empty_target() -> None:
    """Target element that exists but has empty text yields empty msgstr."""
    xliff = """\
<?xml version="1.0" encoding="UTF-8"?>
<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2">
  <file source-language="en" target-language="fr" datatype="plaintext">
    <body>
      <trans-unit id="t1">
        <source>Hello</source>
        <target></target>
      </trans-unit>
      <trans-unit id="t2">
        <source>World</source>
        <target>   </target>
      </trans-unit>
    </body>
  </file>
</xliff>"""
    entries, _ = parse_xliff(xliff)
    assert len(entries) == 2  # noqa: PLR2004
    # Empty target element → empty msgstr
    assert entries[0].msgstr == ""
    # Whitespace-only target → preserved as-is (not stripped)
    assert entries[1].msgstr == "   "


# ---------------------------------------------------------------------------
# Edge case: PO with msgctxt (context) field — full roundtrip
# ---------------------------------------------------------------------------


def test_parse_po_msgctxt_roundtrip() -> None:
    """PO entry with msgctxt preserves context through parse → serialize → re-parse."""
    content = (
        'msgid ""\nmsgstr ""\n\n'
        'msgctxt "button"\n'
        'msgid "Save"\n'
        'msgstr "Enregistrer"\n\n'
        'msgctxt "menu"\n'
        'msgid "Save"\n'
        'msgstr "Sauvegarder"\n'
    )
    entries, header = parse_po(content)
    assert len(entries) == 2  # noqa: PLR2004
    assert entries[0].context == "button"
    assert entries[0].msgid == "Save"
    assert entries[0].msgstr == "Enregistrer"
    assert entries[1].context == "menu"
    assert entries[1].msgid == "Save"
    assert entries[1].msgstr == "Sauvegarder"

    # Roundtrip
    result = serialize_po(entries, header)
    entries2, _ = parse_po(result)
    assert len(entries2) == 2  # noqa: PLR2004
    assert entries2[0].context == "button"
    assert entries2[1].context == "menu"


# ---------------------------------------------------------------------------
# Edge case: PO with 3 plural forms (msgstr[0], msgstr[1], msgstr[2])
# ---------------------------------------------------------------------------


def test_parse_po_three_plural_forms() -> None:
    """PO entry with 3 plural forms (e.g. Polish) is parsed and serialized correctly."""
    content = (
        'msgid ""\nmsgstr ""\n'
        '"Plural-Forms: nplurals=3; plural=(n==1 ? 0 : n%10>=2 && n%10<=4'
        ' && (n%100<10 || n%100>=20) ? 1 : 2);\\n"\n\n'
        'msgid "One file"\n'
        'msgid_plural "%d files"\n'
        'msgstr[0] "jeden plik"\n'
        'msgstr[1] "%d pliki"\n'
        'msgstr[2] "%d plik\\u00f3w"\n'
    )
    entries, header = parse_po(content)
    assert len(entries) == 1
    plural_map = entries[0].metadata["msgstr_plural"]
    assert plural_map[0] == "jeden plik"
    assert plural_map[1] == "%d pliki"
    # PO escape handling does not process \uXXXX — only \n \t \" \\
    # So \u00f3w stays as the literal string r"\u00f3w"
    assert plural_map[2] == r"%d plik\u00f3w"

    # Serialize and re-parse
    result = serialize_po(entries, header)
    assert "msgstr[0]" in result
    assert "msgstr[1]" in result
    assert "msgstr[2]" in result

    entries2, _ = parse_po(result)
    assert len(entries2[0].metadata["msgstr_plural"]) == 3  # noqa: PLR2004


# ---------------------------------------------------------------------------
# Edge case: PO with obsolete entries (#~ prefix) — verify they're skipped
# ---------------------------------------------------------------------------


def test_parse_po_obsolete_entries_skipped() -> None:
    """PO obsolete entries (prefixed with #~) are treated as comments and skipped."""
    content = (
        'msgid ""\nmsgstr ""\n\n'
        '#~ msgid "Old text"\n'
        '#~ msgstr "Ancien texte"\n\n'
        'msgid "New text"\n'
        'msgstr "Nouveau texte"\n'
    )
    entries, _ = parse_po(content)
    # Obsolete entries start with # so they are treated as comment lines.
    # The block containing only #~ lines has no msgid keyword → skipped.
    assert len(entries) == 1
    assert entries[0].msgid == "New text"
    assert entries[0].msgstr == "Nouveau texte"


# ---------------------------------------------------------------------------
# Edge case: XLIFF with BOM — verify behavior
# ---------------------------------------------------------------------------


def test_parse_xliff_with_bom() -> None:
    """XLIFF content with a UTF-8 BOM is parsed correctly.

    Python's xml.etree.ElementTree.fromstring tolerates BOM in modern
    versions (3.8+), so the parse succeeds and entries are extracted.
    """
    xliff_with_bom = (
        "\ufeff"
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2">\n'
        "  <file><body>\n"
        '    <trans-unit id="1"><source>Hello</source></trans-unit>\n'
        "  </body></file>\n"
        "</xliff>"
    )
    entries, _ = parse_xliff(xliff_with_bom)
    assert len(entries) == 1
    assert entries[0].msgid == "Hello"


# ---------------------------------------------------------------------------
# Edge case: serialize_localization positive path for .po and .xliff
# ---------------------------------------------------------------------------


def test_serialize_localization_po() -> None:
    """serialize_localization dispatches to PO serializer for .po extension."""
    entries, header = parse_po(_SAMPLE_PO)
    entries[0].msgstr = "Translated!"
    result = serialize_localization(entries, header, ".po")
    assert 'msgstr "Translated!"' in result


def test_serialize_localization_pot() -> None:
    """serialize_localization dispatches to PO serializer for .pot extension."""
    content = 'msgid ""\nmsgstr ""\n\nmsgid "Hello"\nmsgstr ""\n'
    entries, header = parse_po(content)
    entries[0].msgstr = "Bonjour"
    result = serialize_localization(entries, header, ".pot")
    assert 'msgstr "Bonjour"' in result


def test_serialize_localization_xliff() -> None:
    """serialize_localization dispatches to XLIFF serializer for .xliff extension."""
    entries, root = parse_xliff(_SAMPLE_XLIFF_12)
    entries[0].msgstr = "Hola"
    result = serialize_localization(entries, root, ".xliff")
    assert "Hola" in result


def test_serialize_localization_xlf() -> None:
    """serialize_localization dispatches to XLIFF serializer for .xlf extension."""
    entries, root = parse_xliff(_SAMPLE_XLIFF_20)
    entries[0].msgstr = "Hola"
    result = serialize_localization(entries, root, ".xlf")
    assert "Hola" in result


# ---------------------------------------------------------------------------
# Edge case: PO multiline msgstr with continuation lines
# ---------------------------------------------------------------------------


def test_parse_po_multiline_msgstr_continuation() -> None:
    """PO entry with multiline msgstr using continuation lines is concatenated."""
    content = (
        'msgid ""\nmsgstr ""\n\n'
        'msgid "greeting"\n'
        'msgstr ""\n'
        '"Hello "\n'
        '"beautiful "\n'
        '"world"\n'
    )
    entries, _ = parse_po(content)
    assert len(entries) == 1
    assert entries[0].msgstr == "Hello beautiful world"


# ---------------------------------------------------------------------------
# NEW: LocalizationEntry creation and defaults
# ---------------------------------------------------------------------------


def test_localization_entry_defaults() -> None:
    """LocalizationEntry has expected defaults for optional fields."""
    entry = LocalizationEntry(index=0, msgid="Hello")
    assert entry.msgstr == ""
    assert entry.context == ""
    assert entry.metadata == {}


def test_localization_entry_with_all_fields() -> None:
    """LocalizationEntry stores all provided fields."""
    entry = LocalizationEntry(
        index=5,
        msgid="Save",
        msgstr="Enregistrer",
        context="menu",
        metadata={"unit_id": "u5"},
    )
    assert entry.index == 5  # noqa: PLR2004
    assert entry.msgid == "Save"
    assert entry.msgstr == "Enregistrer"
    assert entry.context == "menu"
    assert entry.metadata["unit_id"] == "u5"


# ---------------------------------------------------------------------------
# NEW: PO parsing edge cases
# ---------------------------------------------------------------------------


def test_parse_po_unicode_cjk() -> None:
    """PO with CJK text parses correctly."""
    content = (
        'msgid ""\nmsgstr ""\n\n'
        'msgid "\u4f60\u597d"\n'
        'msgstr "\u4f60\u597d\u4e16\u754c"\n'
    )
    entries, _ = parse_po(content)
    assert entries[0].msgid == "\u4f60\u597d"
    assert entries[0].msgstr == "\u4f60\u597d\u4e16\u754c"


def test_parse_po_unicode_arabic() -> None:
    """PO with Arabic text parses correctly."""
    content = (
        'msgid ""\nmsgstr ""\n\n'
        'msgid "\u0645\u0631\u062d\u0628\u0627"\n'
        'msgstr "\u0623\u0647\u0644\u0627"\n'
    )
    entries, _ = parse_po(content)
    assert entries[0].msgid == "\u0645\u0631\u062d\u0628\u0627"


def test_parse_po_multiple_entries() -> None:
    """PO with many entries parses all of them."""
    blocks = ['msgid ""\nmsgstr ""\n']
    for i in range(50):
        blocks.append(f'msgid "Entry {i}"\nmsgstr "Trans {i}"\n')
    content = "\n\n".join(blocks)
    entries, _ = parse_po(content)
    assert len(entries) == 50  # noqa: PLR2004
    assert entries[49].msgid == "Entry 49"
    assert entries[49].msgstr == "Trans 49"


def test_parse_po_entry_with_all_comment_types() -> None:
    """PO entry with translator, extracted, reference, and flag comments."""
    content = (
        'msgid ""\nmsgstr ""\n\n'
        "# Translator comment\n"
        "#. Extracted comment\n"
        "#: file.py:10\n"
        "#, python-format\n"
        'msgid "Hello %s"\n'
        'msgstr ""\n'
    )
    entries, _ = parse_po(content)
    comments = entries[0].metadata["comments"]
    assert any("# Translator" in c for c in comments)
    assert any("#." in c for c in comments)
    assert any("#: file.py:10" in c for c in comments)
    assert "python-format" in entries[0].metadata["flags"]


def test_parse_po_context_with_escapes() -> None:
    """PO msgctxt with escaped characters is unescaped."""
    content = (
        'msgid ""\nmsgstr ""\n\nmsgctxt "menu\\tbar"\nmsgid "File"\nmsgstr "Fichier"\n'
    )
    entries, _ = parse_po(content)
    assert entries[0].context == "menu\tbar"


def test_parse_po_empty_msgstr_is_template() -> None:
    """POT-style entries (all empty msgstr) parse correctly."""
    content = (
        'msgid ""\nmsgstr ""\n\n'
        'msgid "One"\nmsgstr ""\n\n'
        'msgid "Two"\nmsgstr ""\n\n'
        'msgid "Three"\nmsgstr ""\n'
    )
    entries, _ = parse_po(content)
    assert len(entries) == 3  # noqa: PLR2004
    for entry in entries:
        assert entry.msgstr == ""


# ---------------------------------------------------------------------------
# NEW: PO serialization edge cases
# ---------------------------------------------------------------------------


def test_serialize_po_empty_entries_with_header() -> None:
    """PO with header but no entries serializes just the header."""
    header = ['msgid ""\nmsgstr ""\n"Content-Type: text/plain\\n"']
    result = serialize_po([], header)
    assert "Content-Type" in result


def test_serialize_po_entry_with_no_flags_no_comments() -> None:
    """PO entry with empty comments and flags serializes cleanly."""
    entries = [
        LocalizationEntry(
            index=0,
            msgid="Hello",
            msgstr="Bonjour",
            metadata={"comments": [], "flags": set()},
        ),
    ]
    result = serialize_po(entries, [])
    assert 'msgid "Hello"' in result
    assert 'msgstr "Bonjour"' in result
    assert "#," not in result


def test_serialize_po_preserves_multiple_non_fuzzy_flags() -> None:
    """Multiple non-fuzzy flags are all preserved in serialized output."""
    entries = [
        LocalizationEntry(
            index=0,
            msgid="Hello %d",
            msgstr="Bonjour %d",
            metadata={
                "comments": ["#, python-format, c-format"],
                "flags": {"python-format", "c-format"},
            },
        ),
    ]
    result = serialize_po(entries, [])
    assert "python-format" in result
    assert "c-format" in result


def test_serialize_po_escapes_backslash_in_msgid() -> None:
    r"""Backslash in msgid is escaped as \\ in serialized output."""
    entries = [
        LocalizationEntry(
            index=0,
            msgid="path\\file",
            msgstr="chemin\\fichier",
            metadata={"comments": [], "flags": set()},
        ),
    ]
    result = serialize_po(entries, [])
    assert 'msgid "path\\\\file"' in result
    assert 'msgstr "chemin\\\\fichier"' in result


def test_serialize_po_roundtrip_with_context() -> None:
    """PO roundtrip preserves context through parse -> serialize -> re-parse."""
    content = (
        'msgid ""\nmsgstr ""\n\nmsgctxt "dialog"\nmsgid "OK"\nmsgstr "D\'accord"\n'
    )
    entries, header = parse_po(content)
    result = serialize_po(entries, header)
    entries2, _ = parse_po(result)
    assert entries2[0].context == "dialog"
    assert entries2[0].msgid == "OK"


# ---------------------------------------------------------------------------
# NEW: POT parsing (template without translations)
# ---------------------------------------------------------------------------


def test_parse_pot_basic() -> None:
    """POT file via .pot dispatcher has all empty msgstr."""
    content = (
        'msgid ""\nmsgstr ""\n\n'
        'msgid "Submit"\nmsgstr ""\n\n'
        'msgid "Cancel"\nmsgstr ""\n'
    )
    entries, _ = parse_localization(content, ".pot")
    assert len(entries) == 2  # noqa: PLR2004
    assert all(e.msgstr == "" for e in entries)


def test_pot_roundtrip() -> None:
    """POT parse -> translate -> serialize -> re-parse roundtrip."""
    content = 'msgid ""\nmsgstr ""\n\nmsgid "Yes"\nmsgstr ""\n\nmsgid "No"\nmsgstr ""\n'
    entries, header = parse_po(content)
    entries[0].msgstr = "Oui"
    entries[1].msgstr = "Non"
    result = serialize_po(entries, header)
    entries2, _ = parse_po(result)
    assert entries2[0].msgstr == "Oui"
    assert entries2[1].msgstr == "Non"


# ---------------------------------------------------------------------------
# NEW: XLIFF 1.2 additional tests
# ---------------------------------------------------------------------------


def test_parse_xliff12_empty_source_skipped() -> None:
    """XLIFF 1.2 trans-unit with empty source is skipped."""
    content = (
        '<?xml version="1.0"?>'
        '<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2">'
        "<file><body>"
        '<trans-unit id="1"><source></source></trans-unit>'
        '<trans-unit id="2"><source>Hello</source></trans-unit>'
        "</body></file></xliff>"
    )
    entries, _ = parse_xliff(content)
    assert len(entries) == 1
    assert entries[0].msgid == "Hello"


def test_parse_xliff12_whitespace_source_skipped() -> None:
    """XLIFF 1.2 trans-unit with whitespace-only source is skipped."""
    content = (
        '<?xml version="1.0"?>'
        '<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2">'
        "<file><body>"
        '<trans-unit id="1"><source>   </source></trans-unit>'
        '<trans-unit id="2"><source>World</source></trans-unit>'
        "</body></file></xliff>"
    )
    entries, _ = parse_xliff(content)
    assert len(entries) == 1
    assert entries[0].msgid == "World"


def test_parse_xliff12_no_note_element() -> None:
    """XLIFF 1.2 without note elements has empty context."""
    content = (
        '<?xml version="1.0"?>'
        '<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2">'
        "<file><body>"
        '<trans-unit id="1"><source>Hello</source></trans-unit>'
        "</body></file></xliff>"
    )
    entries, _ = parse_xliff(content)
    assert entries[0].context == ""


def test_serialize_xliff12_target_inserted_after_source() -> None:
    """XLIFF 1.2 serialization creates target element after source."""
    content = (
        '<?xml version="1.0"?>'
        '<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2">'
        "<file><body>"
        '<trans-unit id="1"><source>Hello</source></trans-unit>'
        "</body></file></xliff>"
    )
    entries, root = parse_xliff(content)
    entries[0].msgstr = "Bonjour"
    result = serialize_xliff(entries, root)
    # Target should appear in the output
    assert "Bonjour" in result
    # Should have state="translated"
    assert 'state="translated"' in result


def test_xliff12_unicode_content() -> None:
    """XLIFF 1.2 with unicode content parses and serializes correctly."""
    content = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2">'
        "<file><body>"
        '<trans-unit id="1"><source>\u4f60\u597d</source>'
        "<target>\u4f60\u597d\u4e16\u754c</target></trans-unit>"
        "</body></file></xliff>"
    )
    entries, root = parse_xliff(content)
    assert entries[0].msgid == "\u4f60\u597d"
    assert entries[0].msgstr == "\u4f60\u597d\u4e16\u754c"
    result = serialize_xliff(entries, root)
    assert "\u4f60\u597d" in result


# ---------------------------------------------------------------------------
# NEW: XLIFF 2.0 additional tests
# ---------------------------------------------------------------------------


def test_parse_xliff20_multiple_segments_in_unit() -> None:
    """XLIFF 2.0 unit with multiple segments extracts all of them."""
    content = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<xliff xmlns="urn:oasis:names:tc:xliff:document:2.0"'
        ' version="2.0" srcLang="en" trgLang="fr">'
        '<file id="f1">'
        '<unit id="u1">'
        "<segment><source>Sentence one.</source></segment>"
        "<segment><source>Sentence two.</source></segment>"
        "</unit></file></xliff>"
    )
    entries, _ = parse_xliff(content)
    assert len(entries) == 2  # noqa: PLR2004
    assert entries[0].msgid == "Sentence one."
    assert entries[1].msgid == "Sentence two."


def test_parse_xliff20_multiple_units() -> None:
    """XLIFF 2.0 with multiple units extracts all of them."""
    content = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<xliff xmlns="urn:oasis:names:tc:xliff:document:2.0"'
        ' version="2.0" srcLang="en" trgLang="fr">'
        '<file id="f1">'
        '<unit id="u1"><segment><source>First</source></segment></unit>'
        '<unit id="u2"><segment><source>Second</source></segment></unit>'
        '<unit id="u3"><segment><source>Third</source></segment></unit>'
        "</file></xliff>"
    )
    entries, _ = parse_xliff(content)
    assert len(entries) == 3  # noqa: PLR2004


def test_serialize_xliff20_target_inserted() -> None:
    """XLIFF 2.0 serialization inserts target when missing."""
    content = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<xliff xmlns="urn:oasis:names:tc:xliff:document:2.0"'
        ' version="2.0" srcLang="en" trgLang="fr">'
        '<file id="f1">'
        '<unit id="u1"><segment><source>Hello</source></segment></unit>'
        "</file></xliff>"
    )
    entries, root = parse_xliff(content)
    entries[0].msgstr = "Bonjour"
    result = serialize_xliff(entries, root)
    assert "Bonjour" in result


def test_xliff20_unicode_content() -> None:
    """XLIFF 2.0 with unicode content roundtrips correctly."""
    content = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<xliff xmlns="urn:oasis:names:tc:xliff:document:2.0"'
        ' version="2.0" srcLang="en" trgLang="ja">'
        '<file id="f1">'
        '<unit id="u1"><segment>'
        "<source>\u3053\u3093\u306b\u3061\u306f</source>"
        "</segment></unit></file></xliff>"
    )
    entries, root = parse_xliff(content)
    assert entries[0].msgid == "\u3053\u3093\u306b\u3061\u306f"
    entries[0].msgstr = "\u4eca\u65e5\u306f"
    result = serialize_xliff(entries, root)
    assert "\u4eca\u65e5\u306f" in result


def test_xliff20_no_ns0_prefix() -> None:
    """Round-trip XLIFF 2.0 output must not contain ns0: namespace prefix."""
    entries, root = parse_xliff(_SAMPLE_XLIFF_20)
    output = serialize_xliff(entries, root)
    assert "ns0:" not in output


# ---------------------------------------------------------------------------
# NEW: Roundtrip tests for each format
# ---------------------------------------------------------------------------


def test_po_full_roundtrip_with_plurals() -> None:
    """PO full roundtrip with plural forms preserves everything."""
    content = (
        'msgid ""\nmsgstr ""\n\n'
        'msgid "One item"\n'
        'msgid_plural "%d items"\n'
        'msgstr[0] "Un"\n'
        'msgstr[1] "Plusieurs"\n'
    )
    entries, header = parse_po(content)
    result = serialize_po(entries, header)
    entries2, _ = parse_po(result)
    assert entries2[0].msgid == "One item"
    assert entries2[0].metadata["msgid_plural"] == "%d items"
    assert entries2[0].metadata["msgstr_plural"][0] == "Un"
    assert entries2[0].metadata["msgstr_plural"][1] == "Plusieurs"


def test_xliff12_full_roundtrip() -> None:
    """XLIFF 1.2 full roundtrip preserves source, target, and note."""
    entries, root = parse_xliff(_SAMPLE_XLIFF_12)
    entries[0].msgstr = "Hola"
    entries[1].msgstr = "Mundo"
    result = serialize_xliff(entries, root)
    entries2, _ = parse_xliff(result)
    assert entries2[0].msgstr == "Hola"
    assert entries2[1].msgstr == "Mundo"
    assert entries2[0].msgid == "Hello"


# ---------------------------------------------------------------------------
# NEW: Empty translation units
# ---------------------------------------------------------------------------


def test_parse_xliff12_all_translate_no() -> None:
    """XLIFF 1.2 with all translate='no' returns no entries."""
    content = (
        '<?xml version="1.0"?>'
        '<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2">'
        "<file><body>"
        '<trans-unit id="1" translate="no"><source>Skip1</source></trans-unit>'
        '<trans-unit id="2" translate="no"><source>Skip2</source></trans-unit>'
        "</body></file></xliff>"
    )
    entries, _ = parse_xliff(content)
    assert entries == []


def test_parse_xliff20_all_translate_no() -> None:
    """XLIFF 2.0 with all translate='no' returns no entries."""
    content = (
        '<?xml version="1.0"?>'
        '<xliff xmlns="urn:oasis:names:tc:xliff:document:2.0"'
        ' version="2.0" srcLang="en" trgLang="fr">'
        '<file id="f1">'
        '<unit id="u1" translate="no">'
        "<segment><source>Skip</source></segment></unit>"
        "</file></xliff>"
    )
    entries, _ = parse_xliff(content)
    assert entries == []


# ---------------------------------------------------------------------------
# NEW: is_localization_format additional coverage
# ---------------------------------------------------------------------------


def test_is_localization_format_empty_string() -> None:
    """Empty string returns False."""
    assert is_localization_format("") is False


@pytest.mark.parametrize("ext", [".PO", ".POT", ".XLIFF", ".XLF"])
def test_is_localization_format_case_sensitive(ext: str) -> None:
    """is_localization_format is case-sensitive — uppercase returns False."""
    assert is_localization_format(ext) is False


@pytest.mark.parametrize("ext", ["po", "pot", "xliff", "xlf"])
def test_is_localization_format_no_dot(ext: str) -> None:
    """Extension without leading dot returns False."""
    assert is_localization_format(ext) is False


# ---------------------------------------------------------------------------
# NEW: PO escape/unescape edge cases
# ---------------------------------------------------------------------------


def test_unescape_po_unknown_escape() -> None:
    r"""Unknown escape like \r passes through unchanged."""
    assert _unescape_po(r"\r") == r"\r"


def test_escape_po_empty_string() -> None:
    """Escaping an empty string returns empty string."""
    assert _escape_po("") == ""


def test_unescape_po_empty_string() -> None:
    """Unescaping an empty string returns empty string."""
    assert _unescape_po("") == ""


def test_escape_po_all_special_chars() -> None:
    r"""All special characters are escaped correctly."""
    text = 'backslash \\ quote " newline \n tab \t'
    escaped = _escape_po(text)
    assert "\\\\" in escaped
    assert '\\"' in escaped
    assert "\\n" in escaped
    assert "\\t" in escaped
    # Roundtrip
    assert _unescape_po(escaped) == text


# ---------------------------------------------------------------------------
# NEW: XLIFF with nested file structures
# ---------------------------------------------------------------------------


def test_parse_xliff20_multiple_files() -> None:
    """XLIFF 2.0 with multiple file elements extracts all units."""
    content = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<xliff xmlns="urn:oasis:names:tc:xliff:document:2.0"'
        ' version="2.0" srcLang="en" trgLang="fr">'
        '<file id="f1">'
        '<unit id="u1"><segment><source>File1</source></segment></unit>'
        "</file>"
        '<file id="f2">'
        '<unit id="u2"><segment><source>File2</source></segment></unit>'
        "</file></xliff>"
    )
    entries, _ = parse_xliff(content)
    assert len(entries) == 2  # noqa: PLR2004
    texts = {e.msgid for e in entries}
    assert "File1" in texts
    assert "File2" in texts


# ---------------------------------------------------------------------------
# NEW: Malformed file tests
# ---------------------------------------------------------------------------


def test_parse_po_block_without_msgid_skipped() -> None:
    """PO block with msgstr but no msgid is skipped."""
    content = 'msgid ""\nmsgstr ""\n\nmsgstr "orphan"\n\nmsgid "Real"\nmsgstr ""\n'
    entries, _ = parse_po(content)
    assert len(entries) == 1
    assert entries[0].msgid == "Real"


def test_parse_po_only_comments_no_entries() -> None:
    """PO file with only comment blocks returns no entries."""
    content = "# Just a comment\n# Another comment\n"
    entries, header = parse_po(content)
    assert entries == []


# ---------------------------------------------------------------------------
# EXPANDED: PO escape/unescape edge cases
# ---------------------------------------------------------------------------


def test_unescape_po_consecutive_escapes() -> None:
    r"""Multiple consecutive escape sequences are all unescaped."""
    assert _unescape_po(r"\n\t\\\"") == '\n\t\\"'


def test_unescape_po_only_backslash_at_end() -> None:
    r"""Trailing backslash without following char is preserved."""
    assert _unescape_po("text\\") == "text\\"


def test_escape_po_plain_text() -> None:
    """Plain text without special chars is returned unchanged."""
    assert _escape_po("Hello World") == "Hello World"


def test_unescape_po_no_escapes() -> None:
    """Text without escape sequences is returned unchanged."""
    assert _unescape_po("Hello World") == "Hello World"


def test_escape_unescape_po_tab_only() -> None:
    r"""Tab character roundtrips through escape/unescape."""
    assert _unescape_po(_escape_po("\t")) == "\t"


def test_escape_unescape_po_newline_only() -> None:
    r"""Newline character roundtrips through escape/unescape."""
    assert _unescape_po(_escape_po("\n")) == "\n"


def test_escape_unescape_po_quote_only() -> None:
    r"""Quote character roundtrips through escape/unescape."""
    assert _unescape_po(_escape_po('"')) == '"'


def test_escape_unescape_po_complex_string() -> None:
    r"""Complex string with all special chars roundtrips correctly."""
    original = 'Line1\nLine2\t"Quoted"\\'
    assert _unescape_po(_escape_po(original)) == original


# ---------------------------------------------------------------------------
# EXPANDED: PO parsing edge cases
# ---------------------------------------------------------------------------


def test_parse_po_windows_line_endings() -> None:
    r"""PO with \r\n line endings still parses."""
    content = 'msgid ""\r\nmsgstr ""\r\n\r\nmsgid "Hello"\r\nmsgstr "World"\r\n'
    entries, _ = parse_po(content)
    assert len(entries) >= 1
    assert any(e.msgid == "Hello" for e in entries)


def test_parse_po_very_long_msgid() -> None:
    """PO with very long msgid parses correctly."""
    long_text = "A" * 5000
    content = f'msgid ""\nmsgstr ""\n\nmsgid "{long_text}"\nmsgstr "Translated"\n'
    entries, _ = parse_po(content)
    assert len(entries) == 1
    assert entries[0].msgid == long_text


def test_parse_po_multiline_msgid_three_parts() -> None:
    """PO multiline msgid with three continuation lines."""
    content = (
        'msgid ""\nmsgstr ""\n\n'
        'msgid ""\n"Part one "\n"Part two "\n"Part three"\n'
        'msgstr "Translation"\n'
    )
    entries, _ = parse_po(content)
    assert entries[0].msgid == "Part one Part two Part three"


def test_parse_po_msgstr_multiline() -> None:
    """PO multiline msgstr with continuation lines."""
    content = (
        'msgid ""\nmsgstr ""\n\nmsgid "Source"\nmsgstr ""\n"Translated "\n"text"\n'
    )
    entries, _ = parse_po(content)
    assert entries[0].msgstr == "Translated text"


def test_parse_po_special_chars_in_msgid() -> None:
    """PO with special characters in msgid are preserved via escape/unescape."""
    content = 'msgid ""\nmsgstr ""\n\nmsgid "Hello\\nWorld\\t\\"Quoted\\""\nmsgstr ""\n'
    entries, _ = parse_po(content)
    assert entries[0].msgid == 'Hello\nWorld\t"Quoted"'


def test_parse_po_context_and_plural_combined() -> None:
    """PO entry with both msgctxt and plural forms."""
    content = (
        'msgid ""\nmsgstr ""\n\n'
        'msgctxt "shopping"\n'
        'msgid "item"\n'
        'msgid_plural "items"\n'
        'msgstr[0] "article"\n'
        'msgstr[1] "articles"\n'
    )
    entries, _ = parse_po(content)
    assert entries[0].context == "shopping"
    assert entries[0].metadata["msgid_plural"] == "items"
    assert entries[0].metadata["msgstr_plural"][0] == "article"


def test_parse_po_empty_context() -> None:
    """PO entry with empty msgctxt."""
    content = 'msgid ""\nmsgstr ""\n\nmsgctxt ""\nmsgid "Hello"\nmsgstr "Bonjour"\n'
    entries, _ = parse_po(content)
    assert entries[0].context == ""


def test_parse_po_multiple_flag_lines() -> None:
    """PO entry with multiple #, comment lines collects all flags."""
    content = (
        'msgid ""\nmsgstr ""\n\n'
        "#, python-format\n"
        "#, c-format\n"
        'msgid "Hello"\nmsgstr ""\n'
    )
    entries, _ = parse_po(content)
    flags = entries[0].metadata["flags"]
    assert "python-format" in flags
    assert "c-format" in flags


def test_parse_po_150_entries() -> None:
    """PO with 150 entries parses all of them."""
    blocks = ['msgid ""\nmsgstr ""\n']
    for i in range(150):
        blocks.append(f'msgid "Entry {i}"\nmsgstr "Trans {i}"\n')
    content = "\n\n".join(blocks)
    entries, _ = parse_po(content)
    assert len(entries) == 150  # noqa: PLR2004


# ---------------------------------------------------------------------------
# EXPANDED: PO serialization edge cases
# ---------------------------------------------------------------------------


def test_serialize_po_empty_header_and_entries() -> None:
    """PO with no header and no entries produces minimal output."""
    result = serialize_po([], [])
    assert result.strip() == ""


def test_serialize_po_tab_in_msgstr() -> None:
    r"""Tab character in msgstr is escaped as \t."""
    entries = [
        LocalizationEntry(
            index=0,
            msgid="Hello",
            msgstr="Hello\tWorld",
            metadata={"comments": [], "flags": set()},
        ),
    ]
    result = serialize_po(entries, [])
    assert "\\t" in result


def test_serialize_po_newline_in_msgstr() -> None:
    r"""Newline in msgstr is escaped as \n."""
    entries = [
        LocalizationEntry(
            index=0,
            msgid="Hello",
            msgstr="Hello\nWorld",
            metadata={"comments": [], "flags": set()},
        ),
    ]
    result = serialize_po(entries, [])
    assert "\\n" in result


def test_serialize_po_quote_in_msgstr() -> None:
    r"""Quote in msgstr is escaped as \"."""
    entries = [
        LocalizationEntry(
            index=0,
            msgid="Hello",
            msgstr='Say "hi"',
            metadata={"comments": [], "flags": set()},
        ),
    ]
    result = serialize_po(entries, [])
    assert '\\"hi\\"' in result


def test_serialize_po_only_fuzzy_flag_removed() -> None:
    """When fuzzy is the only flag, the entire #, line is dropped."""
    entries = [
        LocalizationEntry(
            index=0,
            msgid="Hello",
            msgstr="Bonjour",
            metadata={"comments": ["#, fuzzy"], "flags": {"fuzzy"}},
        ),
    ]
    result = serialize_po(entries, [])
    assert "#," not in result


def test_serialize_po_plural_three_forms() -> None:
    """PO with three plural forms serializes correctly."""
    entries = [
        LocalizationEntry(
            index=0,
            msgid="item",
            msgstr="",
            metadata={
                "comments": [],
                "flags": set(),
                "msgid_plural": "items",
                "msgstr_plural": {0: "one", 1: "few", 2: "many"},
            },
        ),
    ]
    result = serialize_po(entries, [])
    assert "msgstr[0]" in result
    assert "msgstr[1]" in result
    assert "msgstr[2]" in result


def test_serialize_po_roundtrip_150_entries() -> None:
    """PO roundtrip with 150 entries preserves all."""
    blocks = ['msgid ""\nmsgstr ""\n']
    for i in range(150):
        blocks.append(f'msgid "Key{i}"\nmsgstr "Val{i}"\n')
    content = "\n\n".join(blocks)
    entries, header = parse_po(content)
    result = serialize_po(entries, header)
    entries2, _ = parse_po(result)
    assert len(entries2) == 150  # noqa: PLR2004
    assert entries2[149].msgid == "Key149"


# ---------------------------------------------------------------------------
# EXPANDED: XLIFF 1.2 edge cases
# ---------------------------------------------------------------------------


def test_parse_xliff12_no_source_element() -> None:
    """XLIFF 1.2 trans-unit without source element is skipped."""
    content = (
        '<?xml version="1.0"?>'
        '<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2">'
        "<file><body>"
        '<trans-unit id="1"><target>No source</target></trans-unit>'
        '<trans-unit id="2"><source>Has source</source></trans-unit>'
        "</body></file></xliff>"
    )
    entries, _ = parse_xliff(content)
    assert len(entries) == 1
    assert entries[0].msgid == "Has source"


def test_parse_xliff12_target_none_text() -> None:
    """XLIFF 1.2 with target element but None text yields empty msgstr."""
    content = (
        '<?xml version="1.0"?>'
        '<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2">'
        "<file><body>"
        '<trans-unit id="1"><source>Hello</source><target/></trans-unit>'
        "</body></file></xliff>"
    )
    entries, _ = parse_xliff(content)
    assert len(entries) == 1
    assert entries[0].msgstr == ""


def test_parse_xliff12_translate_yes_explicit() -> None:
    """XLIFF 1.2 with explicit translate='yes' is parsed."""
    content = (
        '<?xml version="1.0"?>'
        '<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2">'
        "<file><body>"
        '<trans-unit id="1" translate="yes"><source>Hello</source></trans-unit>'
        "</body></file></xliff>"
    )
    entries, _ = parse_xliff(content)
    assert len(entries) == 1


def test_parse_xliff12_many_trans_units() -> None:
    """XLIFF 1.2 with 50 trans-units parses all."""
    units = "".join(
        f'<trans-unit id="{i}"><source>Item {i}</source></trans-unit>'
        for i in range(50)
    )
    content = (
        '<?xml version="1.0"?>'
        '<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2">'
        f"<file><body>{units}</body></file></xliff>"
    )
    entries, _ = parse_xliff(content)
    assert len(entries) == 50  # noqa: PLR2004


def test_serialize_xliff12_roundtrip_many() -> None:
    """XLIFF 1.2 roundtrip with many entries preserves all."""
    units = "".join(
        f'<trans-unit id="{i}"><source>Src {i}</source></trans-unit>' for i in range(20)
    )
    content = (
        '<?xml version="1.0"?>'
        '<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2">'
        f"<file><body>{units}</body></file></xliff>"
    )
    entries, root = parse_xliff(content)
    for e in entries:
        e.msgstr = f"Tgt {e.metadata['unit_id']}"
    result = serialize_xliff(entries, root)
    entries2, _ = parse_xliff(result)
    assert len(entries2) == 20  # noqa: PLR2004
    assert entries2[0].msgstr == "Tgt 0"


def test_serialize_xliff12_special_chars_in_translation() -> None:
    """XLIFF 1.2 serialization handles special XML characters in translations."""
    content = (
        '<?xml version="1.0"?>'
        '<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2">'
        "<file><body>"
        '<trans-unit id="1"><source>Hello</source></trans-unit>'
        "</body></file></xliff>"
    )
    entries, root = parse_xliff(content)
    entries[0].msgstr = "1 < 2 & 3 > 0"
    result = serialize_xliff(entries, root)
    # Re-parse should work without XML errors
    entries2, _ = parse_xliff(result)
    assert entries2[0].msgstr == "1 < 2 & 3 > 0"


# ---------------------------------------------------------------------------
# EXPANDED: XLIFF 2.0 edge cases
# ---------------------------------------------------------------------------


def test_parse_xliff20_no_segment() -> None:
    """XLIFF 2.0 unit without segment has no entries."""
    content = (
        '<?xml version="1.0"?>'
        '<xliff xmlns="urn:oasis:names:tc:xliff:document:2.0"'
        ' version="2.0" srcLang="en" trgLang="fr">'
        '<file id="f1">'
        '<unit id="u1"></unit>'
        "</file></xliff>"
    )
    entries, _ = parse_xliff(content)
    assert entries == []


def test_parse_xliff20_translate_yes_explicit() -> None:
    """XLIFF 2.0 with explicit translate='yes' is parsed."""
    content = (
        '<?xml version="1.0"?>'
        '<xliff xmlns="urn:oasis:names:tc:xliff:document:2.0"'
        ' version="2.0" srcLang="en" trgLang="fr">'
        '<file id="f1">'
        '<unit id="u1" translate="yes">'
        "<segment><source>Hello</source></segment>"
        "</unit></file></xliff>"
    )
    entries, _ = parse_xliff(content)
    assert len(entries) == 1


def test_parse_xliff20_target_self_closing() -> None:
    """XLIFF 2.0 with self-closing target element yields empty msgstr."""
    content = (
        '<?xml version="1.0"?>'
        '<xliff xmlns="urn:oasis:names:tc:xliff:document:2.0"'
        ' version="2.0" srcLang="en" trgLang="fr">'
        '<file id="f1">'
        '<unit id="u1"><segment>'
        "<source>Hello</source><target/>"
        "</segment></unit></file></xliff>"
    )
    entries, _ = parse_xliff(content)
    assert entries[0].msgstr == ""


def test_serialize_xliff20_special_chars() -> None:
    """XLIFF 2.0 handles special XML characters in translations."""
    content = (
        '<?xml version="1.0"?>'
        '<xliff xmlns="urn:oasis:names:tc:xliff:document:2.0"'
        ' version="2.0" srcLang="en" trgLang="fr">'
        '<file id="f1">'
        '<unit id="u1"><segment><source>Hello</source></segment></unit>'
        "</file></xliff>"
    )
    entries, root = parse_xliff(content)
    entries[0].msgstr = '<b>Bold</b> & "quoted"'
    result = serialize_xliff(entries, root)
    entries2, _ = parse_xliff(result)
    assert entries2[0].msgstr == '<b>Bold</b> & "quoted"'


def test_parse_xliff20_many_units() -> None:
    """XLIFF 2.0 with 50 units parses all."""
    units = "".join(
        f'<unit id="u{i}"><segment><source>Src {i}</source></segment></unit>'
        for i in range(50)
    )
    content = (
        '<?xml version="1.0"?>'
        '<xliff xmlns="urn:oasis:names:tc:xliff:document:2.0"'
        ' version="2.0" srcLang="en" trgLang="fr">'
        f'<file id="f1">{units}</file></xliff>'
    )
    entries, _ = parse_xliff(content)
    assert len(entries) == 50  # noqa: PLR2004


# ---------------------------------------------------------------------------
# EXPANDED: Dispatcher additional cases
# ---------------------------------------------------------------------------


def test_parse_localization_po_empty() -> None:
    """parse_localization with empty PO content returns no entries."""
    entries, header = parse_localization("", ".po")
    assert entries == []


def test_serialize_localization_po_roundtrip() -> None:
    """serialize_localization .po roundtrip works."""
    content = 'msgid ""\nmsgstr ""\n\nmsgid "Hello"\nmsgstr "Bonjour"\n'
    entries, header = parse_localization(content, ".po")
    entries[0].msgstr = "Salut"
    result = serialize_localization(entries, header, ".po")
    entries2, _ = parse_localization(result, ".po")
    assert entries2[0].msgstr == "Salut"


def test_serialize_localization_pot_roundtrip() -> None:
    """serialize_localization .pot roundtrip works."""
    content = 'msgid ""\nmsgstr ""\n\nmsgid "Yes"\nmsgstr ""\n'
    entries, header = parse_localization(content, ".pot")
    entries[0].msgstr = "Oui"
    result = serialize_localization(entries, header, ".pot")
    entries2, _ = parse_localization(result, ".pot")
    assert entries2[0].msgstr == "Oui"


def test_serialize_localization_xlf_roundtrip() -> None:
    """serialize_localization .xlf roundtrip works."""
    entries, root = parse_localization(_SAMPLE_XLIFF_20, ".xlf")
    entries[0].msgstr = "Hola"
    result = serialize_localization(entries, root, ".xlf")
    entries2, _ = parse_localization(result, ".xlf")
    assert entries2[0].msgstr == "Hola"


# ---------------------------------------------------------------------------
# EXPANDED: LocalizationEntry edge cases
# ---------------------------------------------------------------------------


def test_localization_entry_equality() -> None:
    """Two LocalizationEntry with same values are equal."""
    e1 = LocalizationEntry(index=0, msgid="Hello", msgstr="Bonjour")
    e2 = LocalizationEntry(index=0, msgid="Hello", msgstr="Bonjour")
    assert e1 == e2


def test_localization_entry_inequality() -> None:
    """Two LocalizationEntry with different msgid are not equal."""
    e1 = LocalizationEntry(index=0, msgid="Hello")
    e2 = LocalizationEntry(index=0, msgid="Goodbye")
    assert e1 != e2


def test_localization_entry_metadata_is_independent() -> None:
    """Two entries don't share the same default dict."""
    e1 = LocalizationEntry(index=0, msgid="A")
    e2 = LocalizationEntry(index=1, msgid="B")
    e1.metadata["key"] = "val"
    assert "key" not in e2.metadata


# ---------------------------------------------------------------------------
# EXPANDED: PO with edge-case comment patterns
# ---------------------------------------------------------------------------


def test_parse_po_translator_comment_preserved() -> None:
    """Translator comment (# ...) is preserved in metadata."""
    content = (
        'msgid ""\nmsgstr ""\n\n'
        "# This is a translator note\n"
        'msgid "Hi"\nmsgstr "Salut"\n'
    )
    entries, _ = parse_po(content)
    comments = entries[0].metadata["comments"]
    assert any("translator note" in c for c in comments)


def test_parse_po_previous_msgid_comment() -> None:
    """Previous msgid comment (#| msgid) is preserved as comment."""
    content = (
        'msgid ""\nmsgstr ""\n\n#| msgid "Old text"\nmsgid "New text"\nmsgstr ""\n'
    )
    entries, _ = parse_po(content)
    comments = entries[0].metadata["comments"]
    assert any("#|" in c for c in comments)


def test_parse_po_no_header_block() -> None:
    """PO file without header block still parses entries."""
    content = 'msgid "Direct"\nmsgstr "Directe"\n'
    entries, header = parse_po(content)
    assert len(entries) == 1
    assert entries[0].msgid == "Direct"
    assert header == []


# ---------------------------------------------------------------------------
# EXPANDED: XLIFF version detection edge cases
# ---------------------------------------------------------------------------


def test_xliff_version_detection_version_21() -> None:
    """XLIFF with version='2.1' is detected as 2.0 (starts with '2')."""
    import xml.etree.ElementTree as ET  # noqa: PLC0415

    from src.utils.localization_utils import _detect_xliff_version  # noqa: PLC0415

    root = ET.fromstring('<xliff version="2.1"><file/></xliff>')
    assert _detect_xliff_version(root) == "2.0"


def test_xliff_version_detection_version_10() -> None:
    """XLIFF with version='1.0' is detected as 1.2 (not starting with '2')."""
    import xml.etree.ElementTree as ET  # noqa: PLC0415

    from src.utils.localization_utils import _detect_xliff_version  # noqa: PLC0415

    root = ET.fromstring('<xliff version="1.0"><file/></xliff>')
    assert _detect_xliff_version(root) == "1.2"


# ---------------------------------------------------------------------------
# EXPANDED: is_localization_format additional
# ---------------------------------------------------------------------------


def test_is_localization_format_with_double_dot() -> None:
    """Extension with double dot returns False."""
    assert is_localization_format("..po") is False


def test_is_localization_format_none_like() -> None:
    """Various non-string-like values: ensure basic strings work."""
    assert is_localization_format(".po") is True
    assert is_localization_format(".pot") is True
    assert is_localization_format(".xliff") is True
    assert is_localization_format(".xlf") is True


# ---------------------------------------------------------------------------
# EXPANDED: Malformed XML edge cases
# ---------------------------------------------------------------------------


def test_parse_xliff_empty_document() -> None:
    """XLIFF with only root element but no files returns no entries."""
    content = (
        '<?xml version="1.0"?>'
        '<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2">'
        "</xliff>"
    )
    entries, _ = parse_xliff(content)
    assert entries == []


def test_parse_xliff_whitespace_document() -> None:
    """XLIFF with whitespace-only content raises parse error."""
    import xml.etree.ElementTree as ET  # noqa: PLC0415, N817

    with pytest.raises(ET.ParseError):
        parse_xliff("   ")


def test_parse_xliff_empty_string_raises() -> None:
    """XLIFF with empty string raises parse error."""
    import xml.etree.ElementTree as ET  # noqa: PLC0415, N817

    with pytest.raises(ET.ParseError):
        parse_xliff("")


# ===========================================================================
# EXPANDED: PO parsing edge cases
# ===========================================================================


def test_parse_po_with_context() -> None:
    """PO entry with msgctxt is parsed with context."""
    content = 'msgid ""\nmsgstr ""\n\nmsgctxt "menu"\nmsgid "File"\nmsgstr "Fichier"\n'
    entries, _ = parse_po(content)
    assert len(entries) == 1
    assert entries[0].context == "menu"
    assert entries[0].msgid == "File"
    assert entries[0].msgstr == "Fichier"


def test_parse_po_with_plural_forms() -> None:
    """PO entry with msgid_plural and msgstr[N] is parsed correctly."""
    content = (
        'msgid ""\nmsgstr ""\n\n'
        'msgid "file"\n'
        'msgid_plural "files"\n'
        'msgstr[0] "fichier"\n'
        'msgstr[1] "fichiers"\n'
    )
    entries, _ = parse_po(content)
    assert len(entries) == 1
    assert entries[0].metadata.get("msgid_plural") == "files"
    assert entries[0].metadata["msgstr_plural"] == {0: "fichier", 1: "fichiers"}


def test_parse_po_with_multiline_msgstr() -> None:
    """PO entry with multiline msgstr is concatenated."""
    content = 'msgid ""\nmsgstr ""\n\nmsgid "greeting"\nmsgstr "Hello "\n"World"\n'
    entries, _ = parse_po(content)
    assert len(entries) == 1
    assert entries[0].msgstr == "Hello World"


def test_parse_po_with_multiline_msgid() -> None:
    """PO entry with multiline msgid is concatenated."""
    content = (
        'msgid ""\nmsgstr ""\n\nmsgid "Hello "\n"World"\nmsgstr "Bonjour le Monde"\n'
    )
    entries, _ = parse_po(content)
    assert len(entries) == 1
    assert entries[0].msgid == "Hello World"


def test_parse_po_preserves_header() -> None:
    """PO header (empty msgid entry) is preserved."""
    content = (
        "# Header comment\n"
        'msgid ""\n'
        'msgstr "Content-Type: text/plain\\n"\n'
        "\n"
        'msgid "hello"\n'
        'msgstr "bonjour"\n'
    )
    entries, header = parse_po(content)
    assert len(entries) == 1
    assert len(header) == 1
    assert "Content-Type" in header[0]


def test_parse_po_with_translator_comment() -> None:
    """PO entry with translator comments preserves them."""
    content = (
        'msgid ""\nmsgstr ""\n\n'
        "# This is a translator comment\n"
        'msgid "save"\n'
        'msgstr "sauvegarder"\n'
    )
    entries, _ = parse_po(content)
    assert len(entries) == 1
    comments = entries[0].metadata.get("comments", [])
    assert any("translator comment" in c for c in comments)


def test_parse_po_with_flags() -> None:
    """PO entry with flags (e.g., fuzzy) preserves them."""
    content = 'msgid ""\nmsgstr ""\n\n#, fuzzy\nmsgid "cancel"\nmsgstr "annuler"\n'
    entries, _ = parse_po(content)
    assert len(entries) == 1
    flags = entries[0].metadata.get("flags", set())
    assert "fuzzy" in flags


def test_parse_po_with_multiple_flags() -> None:
    """PO entry with multiple flags preserves all of them."""
    content = (
        'msgid ""\nmsgstr ""\n\n'
        "#, fuzzy, python-format\n"
        'msgid "count: %d"\n'
        'msgstr "nombre: %d"\n'
    )
    entries, _ = parse_po(content)
    flags = entries[0].metadata.get("flags", set())
    assert "fuzzy" in flags
    assert "python-format" in flags


def test_parse_po_empty_content() -> None:
    """PO with empty content returns empty lists."""
    entries, header = parse_po("")
    assert entries == []
    assert header == []


def test_parse_po_only_header() -> None:
    """PO with only header returns empty entries."""
    content = 'msgid ""\nmsgstr "Content-Type: text/plain\\n"\n'
    entries, header = parse_po(content)
    assert entries == []
    assert len(header) == 1


def test_parse_po_escape_sequences() -> None:
    """PO entry with escape sequences is unescaped correctly."""
    content = 'msgid ""\nmsgstr ""\n\nmsgid "line1\\nline2"\nmsgstr "ligne1\\nligne2"\n'
    entries, _ = parse_po(content)
    assert entries[0].msgid == "line1\nline2"
    assert entries[0].msgstr == "ligne1\nligne2"


def test_parse_po_escaped_quotes() -> None:
    """PO entry with escaped quotes is unescaped correctly."""
    content = (
        'msgid ""\nmsgstr ""\n\nmsgid "Say \\"Hello\\""\nmsgstr "Dire \\"Bonjour\\""\n'
    )
    entries, _ = parse_po(content)
    assert entries[0].msgid == 'Say "Hello"'
    assert entries[0].msgstr == 'Dire "Bonjour"'


def test_parse_po_escaped_backslash() -> None:
    """PO entry with escaped backslash is unescaped correctly."""
    content = (
        'msgid ""\nmsgstr ""\n\n'
        'msgid "path\\\\to\\\\file"\n'
        'msgstr "chemin\\\\vers\\\\fichier"\n'
    )
    entries, _ = parse_po(content)
    assert entries[0].msgid == "path\\to\\file"
    assert entries[0].msgstr == "chemin\\vers\\fichier"


def test_parse_po_tab_escape() -> None:
    """PO entry with tab escape sequence."""
    content = (
        'msgid ""\nmsgstr ""\n\nmsgid "col1\\tcol2"\nmsgstr "colonne1\\tcolonne2"\n'
    )
    entries, _ = parse_po(content)
    assert entries[0].msgid == "col1\tcol2"


def test_parse_po_multiple_entries() -> None:
    """PO with multiple entries parses all."""
    content = (
        'msgid ""\nmsgstr ""\n\n'
        'msgid "hello"\nmsgstr "bonjour"\n\n'
        'msgid "goodbye"\nmsgstr "au revoir"\n\n'
        'msgid "thanks"\nmsgstr "merci"\n'
    )
    entries, _ = parse_po(content)
    assert len(entries) == 3
    assert entries[0].msgid == "hello"
    assert entries[1].msgid == "goodbye"
    assert entries[2].msgid == "thanks"


def test_parse_po_entries_are_zero_indexed() -> None:
    """PO entries have 0-based indices."""
    content = 'msgid ""\nmsgstr ""\n\nmsgid "a"\nmsgstr "A"\n\nmsgid "b"\nmsgstr "B"\n'
    entries, _ = parse_po(content)
    assert entries[0].index == 0
    assert entries[1].index == 1


def test_parse_po_with_bom() -> None:
    """PO with UTF-8 BOM parses correctly."""
    content = '\ufeffmsgid ""\nmsgstr ""\n\nmsgid "hello"\nmsgstr "bonjour"\n'
    entries, _ = parse_po(content)
    assert len(entries) == 1


# ===========================================================================
# EXPANDED: PO serialization edge cases
# ===========================================================================


def test_serialize_po_single_entry() -> None:
    """serialize_po produces valid PO for a single entry."""
    entries = [LocalizationEntry(index=0, msgid="hello", msgstr="bonjour")]
    result = serialize_po(entries, [])
    assert 'msgid "hello"' in result
    assert 'msgstr "bonjour"' in result


def test_serialize_po_with_header() -> None:
    """serialize_po includes header block."""
    header = ['msgid ""\nmsgstr "Content-Type: text/plain\\n"']
    entries = [LocalizationEntry(index=0, msgid="test", msgstr="test_tr")]
    result = serialize_po(entries, header)
    assert "Content-Type" in result


def test_serialize_po_with_context() -> None:
    """serialize_po includes context line."""
    entries = [
        LocalizationEntry(index=0, msgid="File", msgstr="Fichier", context="menu")
    ]
    result = serialize_po(entries, [])
    assert 'msgctxt "menu"' in result


def test_serialize_po_with_plural() -> None:
    """serialize_po produces plural msgstr[N] entries."""
    entries = [
        LocalizationEntry(
            index=0,
            msgid="file",
            msgstr="",
            metadata={
                "msgid_plural": "files",
                "msgstr_plural": {0: "fichier", 1: "fichiers"},
                "comments": [],
                "flags": set(),
            },
        )
    ]
    result = serialize_po(entries, [])
    assert 'msgid_plural "files"' in result
    assert 'msgstr[0] "fichier"' in result
    assert 'msgstr[1] "fichiers"' in result


def test_serialize_po_removes_fuzzy_flag() -> None:
    """serialize_po removes fuzzy flag from output."""
    entries = [
        LocalizationEntry(
            index=0,
            msgid="test",
            msgstr="test_tr",
            metadata={"comments": ["#, fuzzy"], "flags": {"fuzzy"}},
        )
    ]
    result = serialize_po(entries, [])
    assert "fuzzy" not in result


def test_serialize_po_preserves_non_fuzzy_flags() -> None:
    """serialize_po preserves non-fuzzy flags."""
    entries = [
        LocalizationEntry(
            index=0,
            msgid="count: %d",
            msgstr="nombre: %d",
            metadata={
                "comments": ["#, fuzzy, python-format"],
                "flags": {"fuzzy", "python-format"},
            },
        )
    ]
    result = serialize_po(entries, [])
    assert "python-format" in result
    assert "fuzzy" not in result


def test_serialize_po_escapes_special_chars() -> None:
    """serialize_po properly escapes special characters."""
    entries = [LocalizationEntry(index=0, msgid='Say "Hello"', msgstr='Dire "Bonjour"')]
    result = serialize_po(entries, [])
    assert r"\"Hello\"" in result


def test_serialize_po_empty_entries() -> None:
    """serialize_po with no entries and no header returns just newline."""
    result = serialize_po([], [])
    assert result.endswith("\n")


def test_po_roundtrip() -> None:
    """PO parse → serialize → parse roundtrip preserves entries."""
    content = (
        'msgid ""\nmsgstr ""\n\n'
        'msgid "hello"\nmsgstr "bonjour"\n\n'
        'msgid "goodbye"\nmsgstr "au revoir"\n'
    )
    entries, header = parse_po(content)
    result = serialize_po(entries, header)
    re_entries, _ = parse_po(result)
    assert len(re_entries) == len(entries)
    for orig, re_parsed in zip(entries, re_entries, strict=True):
        assert orig.msgid == re_parsed.msgid
        assert orig.msgstr == re_parsed.msgstr


def test_po_roundtrip_with_context() -> None:
    """PO roundtrip preserves context."""
    content = 'msgid ""\nmsgstr ""\n\nmsgctxt "menu"\nmsgid "File"\nmsgstr "Fichier"\n'
    entries, header = parse_po(content)
    result = serialize_po(entries, header)
    re_entries, _ = parse_po(result)
    assert re_entries[0].context == "menu"


def test_po_roundtrip_with_plurals() -> None:
    """PO roundtrip preserves plural forms."""
    content = (
        'msgid ""\nmsgstr ""\n\n'
        'msgid "file"\nmsgid_plural "files"\n'
        'msgstr[0] "fichier"\nmsgstr[1] "fichiers"\n'
    )
    entries, header = parse_po(content)
    result = serialize_po(entries, header)
    re_entries, _ = parse_po(result)
    assert re_entries[0].metadata["msgid_plural"] == "files"
    assert re_entries[0].metadata["msgstr_plural"][0] == "fichier"


# ===========================================================================
# EXPANDED: PO escape/unescape edge cases
# ===========================================================================


def test_unescape_po_empty_string() -> None:
    """_unescape_po with empty string returns empty."""
    from src.utils.localization_utils import _unescape_po  # noqa: PLC0415

    assert _unescape_po("") == ""


def test_unescape_po_no_escapes() -> None:
    """_unescape_po with no escape sequences returns unchanged."""
    from src.utils.localization_utils import _unescape_po  # noqa: PLC0415

    assert _unescape_po("Hello world") == "Hello world"


def test_unescape_po_newline() -> None:
    """_unescape_po handles \\n."""
    from src.utils.localization_utils import _unescape_po  # noqa: PLC0415

    assert _unescape_po("line1\\nline2") == "line1\nline2"


def test_unescape_po_tab() -> None:
    """_unescape_po handles \\t."""
    from src.utils.localization_utils import _unescape_po  # noqa: PLC0415

    assert _unescape_po("col1\\tcol2") == "col1\tcol2"


def test_unescape_po_quote() -> None:
    """_unescape_po handles escaped quotes."""
    from src.utils.localization_utils import _unescape_po  # noqa: PLC0415

    assert _unescape_po('say \\"hi\\"') == 'say "hi"'


def test_unescape_po_backslash() -> None:
    """_unescape_po handles escaped backslash."""
    from src.utils.localization_utils import _unescape_po  # noqa: PLC0415

    assert _unescape_po("path\\\\file") == "path\\file"


def test_escape_po_empty_string() -> None:
    """_escape_po with empty string returns empty."""
    from src.utils.localization_utils import _escape_po  # noqa: PLC0415

    assert _escape_po("") == ""


def test_escape_po_newline() -> None:
    """_escape_po escapes newlines."""
    from src.utils.localization_utils import _escape_po  # noqa: PLC0415

    assert _escape_po("line1\nline2") == "line1\\nline2"


def test_escape_po_quote() -> None:
    """_escape_po escapes quotes."""
    from src.utils.localization_utils import _escape_po  # noqa: PLC0415

    assert _escape_po('say "hi"') == 'say \\"hi\\"'


def test_escape_po_roundtrip() -> None:
    """PO escape → unescape roundtrip preserves text."""
    from src.utils.localization_utils import _escape_po, _unescape_po  # noqa: PLC0415

    original = 'Hello "World"\nNew line\ttab\\'
    assert _unescape_po(_escape_po(original)) == original


# ===========================================================================
# EXPANDED: XLIFF 1.2 parsing edge cases
# ===========================================================================


def test_parse_xliff_12_single_trans_unit() -> None:
    """XLIFF 1.2 with single trans-unit parses correctly."""
    content = (
        '<?xml version="1.0"?>'
        '<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2">'
        '<file source-language="en" target-language="fr">'
        "<body>"
        '<trans-unit id="1"><source>Hello</source><target>Bonjour</target></trans-unit>'
        "</body></file></xliff>"
    )
    entries, _ = parse_xliff(content)
    assert len(entries) == 1
    assert entries[0].msgid == "Hello"
    assert entries[0].msgstr == "Bonjour"


def test_parse_xliff_12_multiple_trans_units() -> None:
    """XLIFF 1.2 with multiple trans-units parses all."""
    content = (
        '<?xml version="1.0"?>'
        '<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2">'
        '<file source-language="en"><body>'
        '<trans-unit id="1"><source>Hello</source><target>Bonjour</target></trans-unit>'
        '<trans-unit id="2"><source>World</source><target>Monde</target></trans-unit>'
        "</body></file></xliff>"
    )
    entries, _ = parse_xliff(content)
    assert len(entries) == 2
    assert entries[0].msgid == "Hello"
    assert entries[1].msgid == "World"


def test_parse_xliff_12_skip_non_translatable() -> None:
    """XLIFF 1.2 skips translate='no' units."""
    content = (
        '<?xml version="1.0"?>'
        '<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2">'
        '<file source-language="en"><body>'
        '<trans-unit id="1" translate="no"><source>Skip me</source></trans-unit>'
        '<trans-unit id="2"><source>Keep me</source></trans-unit>'
        "</body></file></xliff>"
    )
    entries, _ = parse_xliff(content)
    assert len(entries) == 1
    assert entries[0].msgid == "Keep me"


def test_parse_xliff_12_with_note() -> None:
    """XLIFF 1.2 trans-unit with note parses context."""
    content = (
        '<?xml version="1.0"?>'
        '<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2">'
        '<file source-language="en"><body>'
        '<trans-unit id="1"><source>Hello</source><target>Bonjour</target>'
        "<note>Greeting context</note></trans-unit>"
        "</body></file></xliff>"
    )
    entries, _ = parse_xliff(content)
    assert entries[0].context == "Greeting context"


def test_parse_xliff_12_without_target() -> None:
    """XLIFF 1.2 trans-unit without target has empty msgstr."""
    content = (
        '<?xml version="1.0"?>'
        '<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2">'
        '<file source-language="en"><body>'
        '<trans-unit id="1"><source>Hello</source></trans-unit>'
        "</body></file></xliff>"
    )
    entries, _ = parse_xliff(content)
    assert entries[0].msgstr == ""


def test_parse_xliff_12_unit_id_in_metadata() -> None:
    """XLIFF 1.2 preserves unit ID in metadata."""
    content = (
        '<?xml version="1.0"?>'
        '<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2">'
        '<file source-language="en"><body>'
        '<trans-unit id="btn.save"><source>Save</source></trans-unit>'
        "</body></file></xliff>"
    )
    entries, _ = parse_xliff(content)
    assert entries[0].metadata["unit_id"] == "btn.save"


def test_parse_xliff_12_empty_source_skipped() -> None:
    """XLIFF 1.2 skips trans-units with empty source."""
    content = (
        '<?xml version="1.0"?>'
        '<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2">'
        '<file source-language="en"><body>'
        '<trans-unit id="1"><source></source></trans-unit>'
        '<trans-unit id="2"><source>Valid</source></trans-unit>'
        "</body></file></xliff>"
    )
    entries, _ = parse_xliff(content)
    assert len(entries) == 1
    assert entries[0].msgid == "Valid"


def test_parse_xliff_12_multiple_files() -> None:
    """XLIFF 1.2 with multiple <file> elements parses all trans-units."""
    content = (
        '<?xml version="1.0"?>'
        '<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2">'
        '<file source-language="en"><body>'
        '<trans-unit id="1"><source>First</source></trans-unit>'
        "</body></file>"
        '<file source-language="en"><body>'
        '<trans-unit id="2"><source>Second</source></trans-unit>'
        "</body></file></xliff>"
    )
    entries, _ = parse_xliff(content)
    assert len(entries) == 2


# ===========================================================================
# EXPANDED: XLIFF 2.0 parsing edge cases
# ===========================================================================


def test_parse_xliff_20_single_unit() -> None:
    """XLIFF 2.0 with single unit parses correctly."""
    content = (
        '<?xml version="1.0"?>'
        '<xliff version="2.0" xmlns="urn:oasis:names:tc:xliff:document:2.0" srcLang="en" trgLang="fr">'
        '<file id="f1"><unit id="1"><segment>'
        "<source>Hello</source><target>Bonjour</target>"
        "</segment></unit></file></xliff>"
    )
    entries, _ = parse_xliff(content)
    assert len(entries) == 1
    assert entries[0].msgid == "Hello"
    assert entries[0].msgstr == "Bonjour"


def test_parse_xliff_20_multiple_units() -> None:
    """XLIFF 2.0 with multiple units parses all."""
    content = (
        '<?xml version="1.0"?>'
        '<xliff version="2.0" xmlns="urn:oasis:names:tc:xliff:document:2.0" srcLang="en">'
        '<file id="f1">'
        '<unit id="1"><segment><source>Hello</source></segment></unit>'
        '<unit id="2"><segment><source>World</source></segment></unit>'
        "</file></xliff>"
    )
    entries, _ = parse_xliff(content)
    assert len(entries) == 2


def test_parse_xliff_20_skip_non_translatable() -> None:
    """XLIFF 2.0 skips translate='no' units."""
    content = (
        '<?xml version="1.0"?>'
        '<xliff version="2.0" xmlns="urn:oasis:names:tc:xliff:document:2.0" srcLang="en">'
        '<file id="f1">'
        '<unit id="1" translate="no"><segment><source>Skip</source></segment></unit>'
        '<unit id="2"><segment><source>Keep</source></segment></unit>'
        "</file></xliff>"
    )
    entries, _ = parse_xliff(content)
    assert len(entries) == 1
    assert entries[0].msgid == "Keep"


def test_parse_xliff_20_without_target() -> None:
    """XLIFF 2.0 unit without target has empty msgstr."""
    content = (
        '<?xml version="1.0"?>'
        '<xliff version="2.0" xmlns="urn:oasis:names:tc:xliff:document:2.0" srcLang="en">'
        '<file id="f1"><unit id="1"><segment>'
        "<source>Hello</source>"
        "</segment></unit></file></xliff>"
    )
    entries, _ = parse_xliff(content)
    assert entries[0].msgstr == ""


def test_parse_xliff_20_unit_id_in_metadata() -> None:
    """XLIFF 2.0 preserves unit ID in metadata."""
    content = (
        '<?xml version="1.0"?>'
        '<xliff version="2.0" xmlns="urn:oasis:names:tc:xliff:document:2.0" srcLang="en">'
        '<file id="f1"><unit id="msg.greeting"><segment>'
        "<source>Hello</source>"
        "</segment></unit></file></xliff>"
    )
    entries, _ = parse_xliff(content)
    assert entries[0].metadata["unit_id"] == "msg.greeting"


def test_parse_xliff_20_empty_source_skipped() -> None:
    """XLIFF 2.0 skips segments with empty source."""
    content = (
        '<?xml version="1.0"?>'
        '<xliff version="2.0" xmlns="urn:oasis:names:tc:xliff:document:2.0" srcLang="en">'
        '<file id="f1">'
        '<unit id="1"><segment><source></source></segment></unit>'
        '<unit id="2"><segment><source>Valid</source></segment></unit>'
        "</file></xliff>"
    )
    entries, _ = parse_xliff(content)
    assert len(entries) == 1
    assert entries[0].msgid == "Valid"


# ===========================================================================
# EXPANDED: XLIFF serialization and injection
# ===========================================================================


def test_serialize_xliff_12_injects_translation() -> None:
    """serialize_xliff injects translations into XLIFF 1.2."""
    content = (
        '<?xml version="1.0"?>'
        '<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2">'
        '<file source-language="en"><body>'
        '<trans-unit id="1"><source>Hello</source></trans-unit>'
        "</body></file></xliff>"
    )
    entries, root = parse_xliff(content)
    entries[0].msgstr = "Bonjour"
    result = serialize_xliff(entries, root)
    assert "Bonjour" in result


def test_serialize_xliff_20_injects_translation() -> None:
    """serialize_xliff injects translations into XLIFF 2.0."""
    content = (
        '<?xml version="1.0"?>'
        '<xliff version="2.0" xmlns="urn:oasis:names:tc:xliff:document:2.0" srcLang="en">'
        '<file id="f1"><unit id="1"><segment>'
        "<source>Hello</source>"
        "</segment></unit></file></xliff>"
    )
    entries, root = parse_xliff(content)
    entries[0].msgstr = "Bonjour"
    result = serialize_xliff(entries, root)
    assert "Bonjour" in result


def test_xliff_12_roundtrip() -> None:
    """XLIFF 1.2 parse → modify → serialize roundtrip."""
    content = (
        '<?xml version="1.0"?>'
        '<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2">'
        '<file source-language="en"><body>'
        '<trans-unit id="1"><source>Hello</source><target>Old</target></trans-unit>'
        "</body></file></xliff>"
    )
    entries, root = parse_xliff(content)
    entries[0].msgstr = "New translation"
    result = serialize_xliff(entries, root)
    assert "New translation" in result
    # Re-parse to verify
    re_entries, _ = parse_xliff(result)
    assert re_entries[0].msgstr == "New translation"


def test_xliff_20_roundtrip() -> None:
    """XLIFF 2.0 parse → modify → serialize roundtrip."""
    content = (
        '<?xml version="1.0"?>'
        '<xliff version="2.0" xmlns="urn:oasis:names:tc:xliff:document:2.0" srcLang="en">'
        '<file id="f1"><unit id="1"><segment>'
        "<source>Hello</source><target>Old</target>"
        "</segment></unit></file></xliff>"
    )
    entries, root = parse_xliff(content)
    entries[0].msgstr = "New translation"
    result = serialize_xliff(entries, root)
    re_entries, _ = parse_xliff(result)
    assert re_entries[0].msgstr == "New translation"


# ===========================================================================
# EXPANDED: XLIFF version detection
# ===========================================================================


def test_detect_xliff_version_12_from_namespace() -> None:
    """_detect_xliff_version detects 1.2 from namespace."""
    import xml.etree.ElementTree as ET  # noqa: PLC0415

    from src.utils.localization_utils import _detect_xliff_version  # noqa: PLC0415

    root = ET.fromstring(
        '<xliff xmlns="urn:oasis:names:tc:xliff:document:1.2" version="1.2"/>'
    )
    assert _detect_xliff_version(root) == "1.2"


def test_detect_xliff_version_20_from_namespace() -> None:
    """_detect_xliff_version detects 2.0 from namespace."""
    import xml.etree.ElementTree as ET  # noqa: PLC0415

    from src.utils.localization_utils import _detect_xliff_version  # noqa: PLC0415

    root = ET.fromstring(
        '<xliff xmlns="urn:oasis:names:tc:xliff:document:2.0" version="2.0"/>'
    )
    assert _detect_xliff_version(root) == "2.0"


def test_detect_xliff_version_from_attribute() -> None:
    """_detect_xliff_version falls back to version attribute."""
    import xml.etree.ElementTree as ET  # noqa: PLC0415

    from src.utils.localization_utils import _detect_xliff_version  # noqa: PLC0415

    root = ET.fromstring('<xliff version="2.1"/>')
    assert _detect_xliff_version(root) == "2.0"


def test_detect_xliff_version_default() -> None:
    """_detect_xliff_version defaults to 1.2 when no info available."""
    import xml.etree.ElementTree as ET  # noqa: PLC0415

    from src.utils.localization_utils import _detect_xliff_version  # noqa: PLC0415

    root = ET.fromstring("<xliff/>")
    assert _detect_xliff_version(root) == "1.2"


# ===========================================================================
# EXPANDED: Unified dispatcher edge cases
# ===========================================================================


def test_parse_localization_po_dispatch() -> None:
    """parse_localization dispatches .po to parse_po."""
    content = 'msgid ""\nmsgstr ""\n\nmsgid "hello"\nmsgstr "bonjour"\n'
    entries, _ = parse_localization(content, ".po")
    assert len(entries) == 1


def test_parse_localization_pot_dispatch() -> None:
    """parse_localization dispatches .pot to parse_po."""
    content = 'msgid ""\nmsgstr ""\n\nmsgid "hello"\nmsgstr ""\n'
    entries, _ = parse_localization(content, ".pot")
    assert len(entries) == 1


def test_parse_localization_xliff_dispatch() -> None:
    """parse_localization dispatches .xliff to parse_xliff."""
    content = (
        '<?xml version="1.0"?>'
        '<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2">'
        '<file source-language="en"><body>'
        '<trans-unit id="1"><source>Hello</source></trans-unit>'
        "</body></file></xliff>"
    )
    entries, _ = parse_localization(content, ".xliff")
    assert len(entries) == 1


def test_parse_localization_xlf_dispatch() -> None:
    """parse_localization dispatches .xlf to parse_xliff."""
    content = (
        '<?xml version="1.0"?>'
        '<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2">'
        '<file source-language="en"><body>'
        '<trans-unit id="1"><source>Hi</source></trans-unit>'
        "</body></file></xliff>"
    )
    entries, _ = parse_localization(content, ".xlf")
    assert len(entries) == 1


def test_parse_localization_unsupported_raises() -> None:
    """parse_localization raises ValueError for unsupported format."""
    with pytest.raises(ValueError, match="Unsupported"):
        parse_localization("content", ".xyz")


def test_serialize_localization_po_dispatch() -> None:
    """serialize_localization dispatches .po to serialize_po."""
    entries = [LocalizationEntry(index=0, msgid="hello", msgstr="bonjour")]
    result = serialize_localization(entries, [], ".po")
    assert "hello" in result


def test_serialize_localization_pot_dispatch() -> None:
    """serialize_localization dispatches .pot to serialize_po."""
    entries = [LocalizationEntry(index=0, msgid="hello", msgstr="")]
    result = serialize_localization(entries, [], ".pot")
    assert "hello" in result


def test_serialize_localization_xliff_dispatch() -> None:
    """serialize_localization dispatches .xliff to serialize_xliff."""
    content = (
        '<?xml version="1.0"?>'
        '<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2">'
        '<file source-language="en"><body>'
        '<trans-unit id="1"><source>Hello</source></trans-unit>'
        "</body></file></xliff>"
    )
    entries, root = parse_xliff(content)
    result = serialize_localization(entries, root, ".xliff")
    assert "Hello" in result


def test_serialize_localization_unsupported_raises() -> None:
    """serialize_localization raises ValueError for unsupported format."""
    with pytest.raises(ValueError, match="Unsupported"):
        serialize_localization([], None, ".xyz")


# ===========================================================================
# EXPANDED: is_localization_format additional
# ===========================================================================


def test_is_localization_format_all_supported() -> None:
    """is_localization_format returns True for all supported extensions."""
    for ext in (".po", ".pot", ".xliff", ".xlf"):
        assert is_localization_format(ext) is True


def test_is_localization_format_unsupported_variants() -> None:
    """is_localization_format returns False for unsupported extensions."""
    for ext in (".txt", ".json", ".xml", ".csv", ".srt", ".vtt"):
        assert is_localization_format(ext) is False


def test_is_localization_format_case_sensitive() -> None:
    """is_localization_format is case-sensitive."""
    assert is_localization_format(".PO") is False
    assert is_localization_format(".XLIFF") is False


def test_is_localization_format_empty() -> None:
    """is_localization_format returns False for empty string."""
    assert is_localization_format("") is False


# ===========================================================================
# EXPANDED: LocalizationEntry dataclass
# ===========================================================================


def test_localization_entry_defaults() -> None:
    """LocalizationEntry has correct default values."""
    entry = LocalizationEntry(index=0, msgid="test")
    assert entry.msgstr == ""
    assert entry.context == ""
    assert entry.metadata == {}


def test_localization_entry_with_all_fields() -> None:
    """LocalizationEntry can be constructed with all fields."""
    entry = LocalizationEntry(
        index=5,
        msgid="hello",
        msgstr="bonjour",
        context="greeting",
        metadata={"unit_id": "1"},
    )
    assert entry.index == 5
    assert entry.msgid == "hello"
    assert entry.msgstr == "bonjour"
    assert entry.context == "greeting"
    assert entry.metadata["unit_id"] == "1"


def test_localization_entry_equality() -> None:
    """LocalizationEntry supports equality comparison."""
    e1 = LocalizationEntry(index=0, msgid="a", msgstr="b")
    e2 = LocalizationEntry(index=0, msgid="a", msgstr="b")
    assert e1 == e2


def test_localization_entry_inequality() -> None:
    """LocalizationEntry detects differences."""
    e1 = LocalizationEntry(index=0, msgid="a", msgstr="b")
    e2 = LocalizationEntry(index=0, msgid="a", msgstr="c")
    assert e1 != e2


# ===========================================================================
# EXPANDED: _extract_po_flags edge cases
# ===========================================================================


def test_extract_po_flags_empty_comments() -> None:
    """_extract_po_flags with no comments returns empty set."""
    from src.utils.localization_utils import _extract_po_flags  # noqa: PLC0415

    assert _extract_po_flags([]) == set()


def test_extract_po_flags_no_flag_comments() -> None:
    """_extract_po_flags ignores non-flag comments."""
    from src.utils.localization_utils import _extract_po_flags  # noqa: PLC0415

    assert _extract_po_flags(["# translator comment", "#. reference"]) == set()


def test_extract_po_flags_single_flag() -> None:
    """_extract_po_flags extracts single flag."""
    from src.utils.localization_utils import _extract_po_flags  # noqa: PLC0415

    assert _extract_po_flags(["#, fuzzy"]) == {"fuzzy"}


def test_extract_po_flags_multiple_flags() -> None:
    """_extract_po_flags extracts multiple flags."""
    from src.utils.localization_utils import _extract_po_flags  # noqa: PLC0415

    flags = _extract_po_flags(["#, fuzzy, python-format, c-format"])
    assert flags == {"fuzzy", "python-format", "c-format"}


# ===========================================================================
# EXPANDED: _parse_po_block edge cases
# ===========================================================================


def test_parse_po_block_empty_lines() -> None:
    """_parse_po_block with empty list returns empty."""
    from src.utils.localization_utils import _parse_po_block  # noqa: PLC0415

    comments, keywords = _parse_po_block([])
    assert comments == []
    assert keywords == {}


def test_parse_po_block_comments_only() -> None:
    """_parse_po_block with only comments returns comments."""
    from src.utils.localization_utils import _parse_po_block  # noqa: PLC0415

    comments, keywords = _parse_po_block(["# comment 1", "# comment 2"])
    assert len(comments) == 2
    assert keywords == {}


def test_parse_po_block_msgid_and_msgstr() -> None:
    """_parse_po_block parses basic msgid/msgstr."""
    from src.utils.localization_utils import _parse_po_block  # noqa: PLC0415

    comments, keywords = _parse_po_block(
        [
            'msgid "hello"',
            'msgstr "bonjour"',
        ]
    )
    assert keywords["msgid"] == "hello"
    assert keywords["msgstr"] == "bonjour"


def test_parse_po_block_continuation_lines() -> None:
    """_parse_po_block handles continuation lines."""
    from src.utils.localization_utils import _parse_po_block  # noqa: PLC0415

    comments, keywords = _parse_po_block(
        [
            'msgid "hello "',
            '"world"',
            'msgstr "bonjour"',
        ]
    )
    assert keywords["msgid"] == "hello world"


# ---------------------------------------------------------------------------
# serialize_po with empty msgstr_plural dict
# ---------------------------------------------------------------------------


def test_serialize_po_with_empty_msgstr_plural_dict() -> None:
    """serialize_po handles empty msgstr_plural dict without crashing.

    When an entry has ``msgid_plural`` in metadata but ``msgstr_plural``
    is an empty dict ``{}``, a naive ``max({}.keys())`` would raise
    ValueError. The code guards against this with
    ``max(msgstr_plural.keys()) if msgstr_plural else 1``, so it
    falls back to max_idx=1 and writes msgstr[0] "" and msgstr[1] "".
    """
    entries = [
        LocalizationEntry(
            index=0,
            msgid="One item",
            msgstr="",
            metadata={
                "comments": [],
                "flags": set(),
                "msgid_plural": "%d items",
                "msgstr_plural": {},
            },
        ),
    ]
    # Should NOT raise ValueError from max({}.keys())
    result = serialize_po(entries, [])

    # Verify the output contains the plural forms with empty translations
    assert 'msgid "One item"' in result
    assert 'msgid_plural "%d items"' in result
    assert 'msgstr[0] ""' in result
    assert 'msgstr[1] ""' in result


def test_serialize_po_with_missing_msgstr_plural_key() -> None:
    """serialize_po handles missing msgstr_plural key entirely.

    When metadata has ``msgid_plural`` but no ``msgstr_plural`` key at all,
    the code uses ``.get("msgstr_plural", {})`` which returns an empty dict.
    Same safe path as the empty dict case.
    """
    entries = [
        LocalizationEntry(
            index=0,
            msgid="One file",
            msgstr="",
            metadata={
                "comments": [],
                "flags": set(),
                "msgid_plural": "%d files",
                # Note: no "msgstr_plural" key
            },
        ),
    ]
    result = serialize_po(entries, [])

    assert 'msgid_plural "%d files"' in result
    assert 'msgstr[0] ""' in result
    assert 'msgstr[1] ""' in result
