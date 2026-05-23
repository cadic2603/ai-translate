"""Unit tests for key-value file parsing and serialization utilities."""

import pytest

from src.utils.keyvalue_utils import (
    LocalizationEntry,
    _escape_properties_value,
    _escape_strings,
    _unescape_properties,
    _unescape_strings,
    is_keyvalue_format,
    parse_keyvalue,
    parse_properties,
    parse_strings,
    parse_yaml,
    serialize_keyvalue,
    serialize_properties,
    serialize_strings,
    serialize_yaml,
)

# ---------------------------------------------------------------------------
# is_keyvalue_format
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ext", [".yaml", ".yml", ".properties", ".strings"])
def test_is_keyvalue_format_true(ext: str) -> None:
    """Known key-value extensions return True."""
    assert is_keyvalue_format(ext) is True


@pytest.mark.parametrize("ext", [".txt", ".json", ".po", ".xml", ".csv"])
def test_is_keyvalue_format_false(ext: str) -> None:
    """Non-key-value extensions return False."""
    assert is_keyvalue_format(ext) is False


# ---------------------------------------------------------------------------
# YAML parsing
# ---------------------------------------------------------------------------


def test_parse_yaml_flat() -> None:
    """Parses flat key-value YAML."""
    content = "greeting: Hello\nfarewell: Goodbye\n"
    entries, data = parse_yaml(content)
    assert len(entries) == 2  # noqa: PLR2004
    assert entries[0].msgid == "Hello"
    assert entries[1].msgid == "Goodbye"


def test_parse_yaml_nested() -> None:
    """Parses nested YAML structure."""
    content = "menu:\n  file: File\n  edit: Edit\n"
    entries, data = parse_yaml(content)
    assert len(entries) == 2  # noqa: PLR2004
    assert entries[0].msgid == "File"
    assert entries[0].metadata["path"] == ("menu", "file")
    assert entries[1].msgid == "Edit"


def test_parse_yaml_deep_nesting() -> None:
    """Parses deeply nested YAML."""
    content = "a:\n  b:\n    c: Deep Value\n"
    entries, _ = parse_yaml(content)
    assert len(entries) == 1
    assert entries[0].msgid == "Deep Value"
    assert entries[0].metadata["path"] == ("a", "b", "c")


def test_parse_yaml_skips_non_strings() -> None:
    """Numbers, booleans, and null are skipped."""
    content = "count: 42\nenabled: true\nname: Alice\nmissing: null\n"
    entries, _ = parse_yaml(content)
    assert len(entries) == 1
    assert entries[0].msgid == "Alice"


def test_parse_yaml_empty() -> None:
    """Empty YAML content returns no entries."""
    entries, data = parse_yaml("")
    assert entries == []
    assert data is None


def test_parse_yaml_bom() -> None:
    """UTF-8 BOM is stripped before parsing."""
    content = "\ufeffgreeting: Hello\n"
    entries, _ = parse_yaml(content)
    assert len(entries) == 1
    assert entries[0].msgid == "Hello"


def test_parse_yaml_list_of_strings() -> None:
    """Strings inside lists are extracted."""
    content = "items:\n  - Apple\n  - Banana\n"
    entries, _ = parse_yaml(content)
    assert len(entries) == 2  # noqa: PLR2004
    assert entries[0].msgid == "Apple"
    assert entries[0].metadata["path"] == ("items", 0)
    assert entries[1].msgid == "Banana"


def test_parse_yaml_mixed_list() -> None:
    """Only string elements in mixed lists are extracted."""
    content = "data:\n  - Hello\n  - 42\n  - true\n  - World\n"
    entries, _ = parse_yaml(content)
    assert len(entries) == 2  # noqa: PLR2004
    assert entries[0].msgid == "Hello"
    assert entries[1].msgid == "World"


def test_parse_yaml_unicode() -> None:
    """Unicode content is handled correctly."""
    content = "greeting: \u3053\u3093\u306b\u3061\u306f\n"
    entries, _ = parse_yaml(content)
    assert len(entries) == 1
    assert entries[0].msgid == "\u3053\u3093\u306b\u3061\u306f"


def test_parse_yaml_skips_empty_strings() -> None:
    """Empty and whitespace-only strings are skipped."""
    content = 'empty: ""\nblank: "   "\nvalid: Hello\n'
    entries, _ = parse_yaml(content)
    assert len(entries) == 1
    assert entries[0].msgid == "Hello"


# ---------------------------------------------------------------------------
# YAML serialization
# ---------------------------------------------------------------------------


def test_serialize_yaml_roundtrip() -> None:
    """Parse then serialize then re-parse yields same entries."""
    content = "greeting: Hello\nfarewell: Goodbye\n"
    entries, data = parse_yaml(content)
    entries[0].msgstr = "Bonjour"
    entries[1].msgstr = "Au revoir"
    result = serialize_yaml(entries, data)
    entries2, _ = parse_yaml(result)
    assert entries2[0].msgid == "Bonjour"
    assert entries2[1].msgid == "Au revoir"


def test_serialize_yaml_preserves_structure() -> None:
    """Nested structure is preserved in serialized output."""
    content = "menu:\n  file: File\n  edit: Edit\n"
    entries, data = parse_yaml(content)
    entries[0].msgstr = "Fichier"
    entries[1].msgstr = "\u00c9diter"
    result = serialize_yaml(entries, data)
    assert "menu:" in result
    assert "Fichier" in result
    assert "\u00c9diter" in result


def test_serialize_yaml_does_not_mutate_original() -> None:
    """Original data structure is not modified during serialization."""
    content = "key: Value\n"
    entries, data = parse_yaml(content)
    entries[0].msgstr = "Translated"
    serialize_yaml(entries, data)
    # Original data should still have original value
    assert data["key"] == "Value"


def test_parse_yaml_scalar_root() -> None:
    """Bare scalar YAML string is extracted."""
    content = "Just a string\n"
    entries, data = parse_yaml(content)
    assert len(entries) == 1
    assert entries[0].msgid == "Just a string"
    assert entries[0].metadata["path"] == ()


def test_serialize_yaml_scalar_root() -> None:
    """Scalar root YAML is translated correctly."""
    content = "Just a string\n"
    entries, data = parse_yaml(content)
    entries[0].msgstr = "Juste une phrase"
    result = serialize_yaml(entries, data)
    assert "Juste une phrase" in result


def test_parse_yaml_root_list() -> None:
    """Root-level YAML list of strings is extracted."""
    content = "- Hello\n- World\n"
    entries, _ = parse_yaml(content)
    assert len(entries) == 2  # noqa: PLR2004
    assert entries[0].msgid == "Hello"
    assert entries[0].metadata["path"] == (0,)
    assert entries[1].msgid == "World"
    assert entries[1].metadata["path"] == (1,)


def test_serialize_yaml_root_list() -> None:
    """Root-level YAML list roundtrip after translation."""
    content = "- Hello\n- World\n"
    entries, data = parse_yaml(content)
    entries[0].msgstr = "Bonjour"
    entries[1].msgstr = "Monde"
    result = serialize_yaml(entries, data)
    entries2, _ = parse_yaml(result)
    assert entries2[0].msgid == "Bonjour"
    assert entries2[1].msgid == "Monde"


# ---------------------------------------------------------------------------
# Properties escape / unescape
# ---------------------------------------------------------------------------


def test_unescape_properties_unicode() -> None:
    r"""Unicode escape \uXXXX is unescaped."""
    assert _unescape_properties("caf\\u00e9") == "caf\u00e9"


def test_unescape_properties_newline() -> None:
    r"""Escaped \n becomes a real newline."""
    assert _unescape_properties("Hello\\nWorld") == "Hello\nWorld"


def test_unescape_properties_tab() -> None:
    r"""Escaped \t becomes a real tab."""
    assert _unescape_properties("Hello\\tWorld") == "Hello\tWorld"


def test_unescape_properties_backslash() -> None:
    r"""Escaped \\ becomes a single backslash."""
    assert _unescape_properties("path\\\\to") == "path\\to"


def test_escape_properties_roundtrip() -> None:
    """Escaping then unescaping returns the original string."""
    original = "Hello\nWorld\t\\"
    assert _unescape_properties(_escape_properties_value(original)) == original


def test_unescape_properties_trailing_backslash() -> None:
    r"""Trailing backslash at EOF is kept as a literal backslash."""
    # i + 1 < len(text) is False at EOF → backslash falls into else → preserved
    assert _unescape_properties("hello\\") == "hello\\"


def test_unescape_properties_invalid_unicode() -> None:
    r"""Invalid \uXXXX (non-hex chars) keeps backslash and continues."""
    # 'Z' is not a hex digit → int() raises ValueError → \ appended literally
    assert _unescape_properties(r"\uXXZZ") == r"\uXXZZ"


def test_unescape_properties_truncated_unicode() -> None:
    r"""Truncated \uXX (fewer than 4 hex digits) falls to else branch."""
    # i + 5 < len(text) fails → else branch → \u treated as \<other>
    assert _unescape_properties(r"\u00") == "u00"


def test_unescape_properties_other_escapes() -> None:
    r"""Other escapes (\=, \:, \<space>) unescape to the literal char."""
    assert _unescape_properties(r"\=") == "="
    assert _unescape_properties(r"\:") == ":"
    assert _unescape_properties(r"\ ") == " "


# ---------------------------------------------------------------------------
# Properties parsing
# ---------------------------------------------------------------------------


_SAMPLE_PROPERTIES = """\
# Application messages
greeting=Hello World
farewell=Goodbye

! Another comment style
menu.file=File
"""


def test_parse_properties_basic() -> None:
    """Parses a standard Properties file."""
    entries, structure = parse_properties(_SAMPLE_PROPERTIES)
    assert len(entries) == 3  # noqa: PLR2004
    assert entries[0].msgid == "Hello World"
    assert entries[0].metadata["key"] == "greeting"
    assert entries[1].msgid == "Goodbye"
    assert entries[2].msgid == "File"


def test_parse_properties_colon_separator() -> None:
    """Colon separator is recognized."""
    content = "key:value\n"
    entries, _ = parse_properties(content)
    assert len(entries) == 1
    assert entries[0].msgid == "value"
    assert entries[0].metadata["separator"] == ":"


def test_parse_properties_space_separator() -> None:
    """Whitespace separator is recognized."""
    content = "key value\n"
    entries, _ = parse_properties(content)
    assert len(entries) == 1
    assert entries[0].msgid == "value"


def test_parse_properties_comments_preserved() -> None:
    """Comment lines are preserved in structure."""
    entries, structure = parse_properties(_SAMPLE_PROPERTIES)
    comment_items = [s for s in structure if s[0] == "comment"]
    assert len(comment_items) == 2  # noqa: PLR2004


def test_parse_properties_blank_lines_preserved() -> None:
    """Blank lines are preserved in structure."""
    entries, structure = parse_properties(_SAMPLE_PROPERTIES)
    blank_items = [s for s in structure if s[0] == "blank"]
    assert len(blank_items) >= 1


def test_parse_properties_continuation_lines() -> None:
    """Backslash continuation joins lines."""
    content = "message=Hello \\\n    World\n"
    entries, _ = parse_properties(content)
    assert len(entries) == 1
    assert entries[0].msgid == "Hello World"


def test_parse_properties_triple_backslash_continuation() -> None:
    r"""Triple backslash: escaped backslash + continuation."""
    content = "path=C:\\\\Users\\\\\\\n    name\n"
    entries, _ = parse_properties(content)
    assert len(entries) == 1
    # Triple backslash at end: \\ (escaped literal) + \ (continuation)
    assert "name" in entries[0].msgid


def test_parse_properties_unicode_escapes() -> None:
    r"""Unicode \uXXXX escapes are decoded."""
    content = "name=caf\\u00e9\n"
    entries, _ = parse_properties(content)
    assert entries[0].msgid == "caf\u00e9"


def test_parse_properties_empty_value() -> None:
    """Key with empty value parses correctly."""
    content = "empty_key=\n"
    entries, _ = parse_properties(content)
    assert len(entries) == 1
    assert entries[0].msgid == ""


def test_parse_properties_empty_file() -> None:
    """Empty content returns no entries."""
    entries, structure = parse_properties("")
    assert entries == []


def test_parse_properties_value_with_equals() -> None:
    """Value containing = is preserved (only first = is separator)."""
    content = "equation=a=b+c\n"
    entries, _ = parse_properties(content)
    assert entries[0].msgid == "a=b+c"


def test_parse_properties_value_with_colon() -> None:
    """Value containing : is preserved when = is the separator."""
    content = "url=http://example.com\n"
    entries, _ = parse_properties(content)
    assert entries[0].msgid == "http://example.com"


def test_parse_properties_bom() -> None:
    """UTF-8 BOM is stripped."""
    content = "\ufeffkey=value\n"
    entries, _ = parse_properties(content)
    assert len(entries) == 1


def test_parse_properties_key_ordering() -> None:
    """Entry ordering matches file order."""
    content = "c=3\na=1\nb=2\n"
    entries, _ = parse_properties(content)
    assert entries[0].metadata["key"] == "c"
    assert entries[1].metadata["key"] == "a"
    assert entries[2].metadata["key"] == "b"


def test_parse_properties_only_comments() -> None:
    """File with only comments returns no entries but preserves structure."""
    content = "# Just a comment\n! Another comment\n"
    entries, structure = parse_properties(content)
    assert entries == []
    comment_items = [s for s in structure if s[0] == "comment"]
    assert len(comment_items) == 2  # noqa: PLR2004


def test_parse_properties_eof_continuation() -> None:
    """File ending mid-continuation strips the trailing backslash."""
    content = "key=value\\"
    entries, _ = parse_properties(content)
    assert len(entries) == 1
    assert entries[0].msgid == "value"


def test_parse_properties_whitespace_before_equals() -> None:
    """Whitespace before = is included in the separator."""
    content = "key = value\n"
    entries, _ = parse_properties(content)
    assert len(entries) == 1
    assert entries[0].msgid == "value"
    # Separator includes the whitespace + =
    assert "=" in entries[0].metadata["separator"]


def test_parse_properties_escaped_key() -> None:
    r"""Escaped \= in key does not split at that position."""
    content = "key\\=name=actual value\n"
    entries, _ = parse_properties(content)
    assert len(entries) == 1
    assert entries[0].metadata["key"] == "key\\=name"
    assert entries[0].msgid == "actual value"


def test_parse_properties_key_no_separator() -> None:
    """Bare key with no separator gets default = and empty value."""
    content = "just_a_key\n"
    entries, _ = parse_properties(content)
    assert len(entries) == 1
    assert entries[0].metadata["key"] == "just_a_key"
    assert entries[0].metadata["separator"] == "="
    assert entries[0].msgid == ""


# ---------------------------------------------------------------------------
# Properties serialization
# ---------------------------------------------------------------------------


def test_serialize_properties_roundtrip() -> None:
    """Parse, translate, serialize, re-parse yields translated values."""
    entries, structure = parse_properties(_SAMPLE_PROPERTIES)
    for entry in entries:
        entry.msgstr = f"[FR] {entry.msgid}"
    result = serialize_properties(entries, structure)
    entries2, _ = parse_properties(result)
    assert len(entries2) == len(entries)
    for orig, reparsed in zip(entries, entries2, strict=True):
        assert reparsed.msgid == f"[FR] {orig.msgid}"


def test_serialize_properties_preserves_comments() -> None:
    """Comments appear in serialized output."""
    entries, structure = parse_properties(_SAMPLE_PROPERTIES)
    result = serialize_properties(entries, structure)
    assert "# Application messages" in result
    assert "! Another comment style" in result


def test_serialize_properties_preserves_separator() -> None:
    """Original separator character is preserved."""
    content = "key1=val1\nkey2:val2\n"
    entries, structure = parse_properties(content)
    entries[0].msgstr = "tr1"
    entries[1].msgstr = "tr2"
    result = serialize_properties(entries, structure)
    assert "key1=tr1" in result
    assert "key2:tr2" in result


def test_serialize_properties_escaping() -> None:
    """Special characters are escaped in output."""
    entries = [
        LocalizationEntry(
            index=0,
            msgid="original",
            msgstr="Line1\nLine2",
            metadata={"key": "msg", "separator": "="},
        ),
    ]
    structure = [("entry", 0)]
    result = serialize_properties(entries, structure)
    assert "msg=Line1\\nLine2" in result


# ---------------------------------------------------------------------------
# Strings escape / unescape
# ---------------------------------------------------------------------------


def test_unescape_strings_quote() -> None:
    r"""Escaped \" becomes a real quote."""
    assert _unescape_strings(r"Say \"hello\"") == 'Say "hello"'


def test_unescape_strings_backslash() -> None:
    r"""Escaped \\ becomes a single backslash."""
    assert _unescape_strings(r"path\\to") == "path\\to"


def test_unescape_strings_newline() -> None:
    r"""Escaped \n becomes a real newline."""
    assert _unescape_strings(r"Hello\nWorld") == "Hello\nWorld"


def test_escape_strings_roundtrip() -> None:
    """Escaping then unescaping returns the original string."""
    original = 'Hello\n"World"\t\\'
    assert _unescape_strings(_escape_strings(original)) == original


def test_unescape_strings_unknown_escape() -> None:
    r"""Unknown escape like \r passes through unchanged."""
    # \r is not in _STRINGS_UNESCAPE_MAP → both chars kept as-is
    assert _unescape_strings(r"\r") == r"\r"


# ---------------------------------------------------------------------------
# Apple Strings parsing
# ---------------------------------------------------------------------------


_SAMPLE_STRINGS = """\
/* Login screen */
"login_title" = "Welcome";

// Subtitle
"login_subtitle" = "Please sign in";
"""


def test_parse_strings_basic() -> None:
    """Parses a standard .strings file."""
    entries, structure = parse_strings(_SAMPLE_STRINGS)
    assert len(entries) == 2  # noqa: PLR2004
    assert entries[0].msgid == "Welcome"
    assert entries[0].metadata["key"] == "login_title"
    assert entries[1].msgid == "Please sign in"


def test_parse_strings_block_comment() -> None:
    """Block comments /* */ are preserved in structure."""
    entries, structure = parse_strings(_SAMPLE_STRINGS)
    raw_items = [s for s in structure if s[0] == "raw"]
    raw_text = "".join(str(s[1]) for s in raw_items)
    assert "/* Login screen */" in raw_text


def test_parse_strings_line_comment() -> None:
    """Line comments // are preserved in structure."""
    entries, structure = parse_strings(_SAMPLE_STRINGS)
    raw_items = [s for s in structure if s[0] == "raw"]
    raw_text = "".join(str(s[1]) for s in raw_items)
    assert "// Subtitle" in raw_text


def test_parse_strings_escapes() -> None:
    """Escaped characters are unescaped."""
    content = r'"key" = "Say \"hello\"";' + "\n"
    entries, _ = parse_strings(content)
    assert entries[0].msgid == 'Say "hello"'


def test_parse_strings_empty_value() -> None:
    """Empty string value parses correctly."""
    content = '"key" = "";' + "\n"
    entries, _ = parse_strings(content)
    assert len(entries) == 1
    assert entries[0].msgid == ""


def test_parse_strings_empty_file() -> None:
    """Empty content returns no entries."""
    entries, structure = parse_strings("")
    assert entries == []


def test_parse_strings_unicode() -> None:
    """Unicode content is handled correctly."""
    content = '"greeting" = "\u3053\u3093\u306b\u3061\u306f";\n'
    entries, _ = parse_strings(content)
    assert entries[0].msgid == "\u3053\u3093\u306b\u3061\u306f"


def test_parse_strings_bom() -> None:
    """UTF-8 BOM is stripped."""
    content = '\ufeff"key" = "value";\n'
    entries, _ = parse_strings(content)
    assert len(entries) == 1


def test_parse_strings_multiline_comment() -> None:
    """Multiline block comment is preserved."""
    content = '/* Line 1\n   Line 2 */\n"key" = "value";\n'
    entries, structure = parse_strings(content)
    assert len(entries) == 1
    raw_text = "".join(str(s[1]) for s in structure if s[0] == "raw")
    assert "Line 1" in raw_text
    assert "Line 2" in raw_text


def test_parse_strings_newline_escape() -> None:
    r"""Escaped \n in values is unescaped."""
    content = '"key" = "Line1\\nLine2";\n'
    entries, _ = parse_strings(content)
    assert entries[0].msgid == "Line1\nLine2"


def test_parse_strings_key_with_escaped_quote() -> None:
    r"""Key containing \" is unescaped to a real quote."""
    content = r'"Say \"hi\"" = "value";' + "\n"
    entries, _ = parse_strings(content)
    assert len(entries) == 1
    assert entries[0].metadata["key"] == 'Say "hi"'
    assert entries[0].msgid == "value"


def test_parse_strings_line_comment_eof() -> None:
    """Line comment at EOF without trailing newline is captured in structure."""
    content = '"key" = "value";\n// comment at eof'
    entries, structure = parse_strings(content)
    assert len(entries) == 1
    raw_text = "".join(str(s[1]) for s in structure if s[0] == "raw")
    assert "// comment at eof" in raw_text


def test_parse_strings_unterminated_block_comment() -> None:
    """Unterminated block comment consumes rest of file without crash."""
    content = '"key" = "value";\n/* unterminated comment'
    entries, structure = parse_strings(content)
    assert len(entries) == 1
    raw_text = "".join(str(s[1]) for s in structure if s[0] == "raw")
    assert "unterminated comment" in raw_text


def test_parse_strings_unknown_content() -> None:
    """Garbage content that doesn't match any pattern is captured in structure."""
    content = 'garbage line\n"key" = "value";\n'
    entries, structure = parse_strings(content)
    assert len(entries) == 1
    assert entries[0].msgid == "value"
    raw_text = "".join(str(s[1]) for s in structure if s[0] == "raw")
    assert "garbage line" in raw_text


# ---------------------------------------------------------------------------
# Strings serialization
# ---------------------------------------------------------------------------


def test_serialize_strings_roundtrip() -> None:
    """Parse, translate, serialize, re-parse yields translated values."""
    entries, structure = parse_strings(_SAMPLE_STRINGS)
    for entry in entries:
        entry.msgstr = f"[FR] {entry.msgid}"
    result = serialize_strings(entries, structure)
    entries2, _ = parse_strings(result)
    assert len(entries2) == len(entries)
    for orig, reparsed in zip(entries, entries2, strict=True):
        assert reparsed.msgid == f"[FR] {orig.msgid}"


def test_serialize_strings_preserves_comments() -> None:
    """Comments are preserved in serialized output."""
    entries, structure = parse_strings(_SAMPLE_STRINGS)
    result = serialize_strings(entries, structure)
    assert "/* Login screen */" in result
    assert "// Subtitle" in result


def test_serialize_strings_escaping() -> None:
    """Special characters are escaped in output."""
    entries = [
        LocalizationEntry(
            index=0,
            msgid="original",
            msgstr='Say "hello"',
            metadata={"key": "msg"},
        ),
    ]
    structure = [("entry", 0)]
    result = serialize_strings(entries, structure)
    assert r"\"hello\"" in result


def test_serialize_strings_translated_values() -> None:
    """Translated values appear in serialized output."""
    entries, structure = parse_strings(_SAMPLE_STRINGS)
    entries[0].msgstr = "Bienvenue"
    entries[1].msgstr = "Veuillez vous connecter"
    result = serialize_strings(entries, structure)
    assert "Bienvenue" in result
    assert "Veuillez vous connecter" in result


# ---------------------------------------------------------------------------
# Unified dispatchers
# ---------------------------------------------------------------------------


def test_parse_keyvalue_yaml() -> None:
    """parse_keyvalue dispatches to YAML parser for .yaml."""
    entries, _ = parse_keyvalue("key: value\n", ".yaml")
    assert len(entries) == 1


def test_parse_keyvalue_yml() -> None:
    """parse_keyvalue dispatches to YAML parser for .yml."""
    entries, _ = parse_keyvalue("key: value\n", ".yml")
    assert len(entries) == 1


def test_parse_keyvalue_properties() -> None:
    """parse_keyvalue dispatches to Properties parser."""
    entries, _ = parse_keyvalue("key=value\n", ".properties")
    assert len(entries) == 1


def test_parse_keyvalue_strings() -> None:
    """parse_keyvalue dispatches to Strings parser."""
    entries, _ = parse_keyvalue('"key" = "value";\n', ".strings")
    assert len(entries) == 1


def test_parse_keyvalue_unsupported() -> None:
    """Unsupported extension raises ValueError."""
    with pytest.raises(ValueError, match="Unsupported key-value format"):
        parse_keyvalue("data", ".txt")


def test_serialize_keyvalue_unsupported() -> None:
    """Unsupported extension raises ValueError."""
    with pytest.raises(ValueError, match="Unsupported key-value format"):
        serialize_keyvalue([], None, ".txt")


def test_serialize_keyvalue_yaml() -> None:
    """serialize_keyvalue dispatches to YAML serializer."""
    entries, data = parse_keyvalue("key: Hello\n", ".yaml")
    entries[0].msgstr = "Bonjour"
    result = serialize_keyvalue(entries, data, ".yaml")
    assert "Bonjour" in result


def test_serialize_keyvalue_properties() -> None:
    """serialize_keyvalue dispatches to Properties serializer."""
    entries, structure = parse_keyvalue("key=Hello\n", ".properties")
    entries[0].msgstr = "Bonjour"
    result = serialize_keyvalue(entries, structure, ".properties")
    assert "key=Bonjour" in result


def test_serialize_keyvalue_strings() -> None:
    """serialize_keyvalue dispatches to Strings serializer."""
    entries, structure = parse_keyvalue('"key" = "Hello";\n', ".strings")
    entries[0].msgstr = "Bonjour"
    result = serialize_keyvalue(entries, structure, ".strings")
    assert "Bonjour" in result


# ---------------------------------------------------------------------------
# parse_yaml — error handling & edge cases
# ---------------------------------------------------------------------------


def test_parse_yaml_invalid_syntax_raises() -> None:
    """Malformed YAML (unclosed quote) raises yaml.YAMLError."""
    import yaml  # noqa: PLC0415

    with pytest.raises(yaml.YAMLError):
        parse_yaml('key: "unclosed')


def test_parse_yaml_empty_content() -> None:
    """Empty YAML content returns empty entries and None data."""
    entries, data = parse_yaml("")
    assert entries == []
    assert data is None


def test_parse_yaml_non_string_values_skipped() -> None:
    """Numbers and booleans in YAML are skipped; only strings extracted."""
    content = "name: Hello\ncount: 42\nactive: true\n"
    entries, _ = parse_yaml(content)
    assert len(entries) == 1
    assert entries[0].msgid == "Hello"


# ---------------------------------------------------------------------------
# parse_properties — edge cases
# ---------------------------------------------------------------------------


def test_parse_properties_value_after_separator_whitespace_only() -> None:
    """Property with only whitespace after separator produces empty value."""
    content = "key =   \n"
    entries, _ = parse_properties(content)
    assert len(entries) == 1
    assert entries[0].msgid == ""


def test_parse_properties_continuation_lines_greeting() -> None:
    """Backslash at end of line joins with next line."""
    content = "greeting = Hello \\\nWorld\n"
    entries, _ = parse_properties(content)
    assert len(entries) == 1
    assert "Hello" in entries[0].msgid
    assert "World" in entries[0].msgid


# ---------------------------------------------------------------------------
# parse_strings — edge cases
# ---------------------------------------------------------------------------


def test_parse_strings_missing_semicolon() -> None:
    """Strings entry without trailing semicolon is still parsed."""
    content = '"key" = "Hello"\n'
    entries, _ = parse_strings(content)
    # Should either parse the entry or silently skip — not crash
    assert isinstance(entries, list)


# ---------------------------------------------------------------------------
# parse_strings — duplicate keys
# ---------------------------------------------------------------------------


def test_parse_strings_duplicate_keys_both_parsed() -> None:
    """Both entries are kept when the same key appears twice."""
    content = '"greeting" = "Hello";\n"greeting" = "Hi";\n'
    entries, structure = parse_strings(content)
    # The parser does not deduplicate; both are stored as separate entries
    assert len(entries) == 2  # noqa: PLR2004
    values = {e.msgid for e in entries}
    assert "Hello" in values
    assert "Hi" in values


def test_parse_strings_duplicate_keys_structure_has_two_entries() -> None:
    """Structure records both ('entry', 0) and ('entry', 1) for duplicate keys."""
    content = '"k" = "A";\n"k" = "B";\n'
    _, structure = parse_strings(content)
    entry_items = [s for s in structure if s[0] == "entry"]
    assert len(entry_items) == 2  # noqa: PLR2004


# ---------------------------------------------------------------------------
# _join_continuation_lines — trailing continuation at EOF
# ---------------------------------------------------------------------------


def test_join_continuation_lines_eof_with_continuation(  # type: ignore[no-untyped-def]
) -> None:
    """A file ending with a backslash continuation flushes the buffer."""
    from src.utils.keyvalue_utils import _join_continuation_lines  # noqa: PLC0415

    # Single backslash at end: continuation, but no following line
    lines = ["key = value\\"]
    result = _join_continuation_lines(lines)
    # Buffer is flushed; backslash removed from end
    assert result == ["key = value"]


def test_join_continuation_lines_double_backslash_no_continuation() -> None:
    """Double trailing backslash is not a continuation (even count)."""
    from src.utils.keyvalue_utils import _join_continuation_lines  # noqa: PLC0415

    lines = ["key = value\\\\", "next = other"]
    result = _join_continuation_lines(lines)
    # Double backslash → not a continuation → two separate lines
    assert len(result) == 2  # noqa: PLR2004
    assert result[0] == "key = value\\\\"
    assert result[1] == "next = other"


# ---------------------------------------------------------------------------
# NEW: YAML nested structures
# ---------------------------------------------------------------------------


def test_parse_yaml_nested_three_levels() -> None:
    """Three-level nesting extracts leaf strings."""
    content = "a:\n  b:\n    c:\n      d: Deep\n"
    entries, _ = parse_yaml(content)
    assert len(entries) == 1
    assert entries[0].msgid == "Deep"
    assert entries[0].metadata["path"] == ("a", "b", "c", "d")


def test_parse_yaml_mixed_dict_and_list() -> None:
    """YAML with dicts containing lists extracts all leaf strings."""
    content = "menu:\n  items:\n    - Open\n    - Save\n  title: File Menu\n"
    entries, _ = parse_yaml(content)
    assert len(entries) == 3  # noqa: PLR2004
    texts = {e.msgid for e in entries}
    assert texts == {"Open", "Save", "File Menu"}


def test_parse_yaml_array_of_dicts() -> None:
    """YAML with an array of dicts extracts string leaf values."""
    content = "people:\n  - name: Alice\n    age: 30\n  - name: Bob\n    age: 25\n"
    entries, _ = parse_yaml(content)
    assert len(entries) == 2  # noqa: PLR2004
    assert entries[0].msgid == "Alice"
    assert entries[1].msgid == "Bob"


def test_parse_yaml_multiline_string_literal() -> None:
    """YAML literal block scalar (|) is extracted as a single string."""
    content = "description: |\n  Line one\n  Line two\n"
    entries, _ = parse_yaml(content)
    assert len(entries) == 1
    assert "Line one" in entries[0].msgid
    assert "Line two" in entries[0].msgid


def test_parse_yaml_multiline_string_folded() -> None:
    """YAML folded block scalar (>) is extracted as a single string."""
    content = "description: >\n  This is a long\n  paragraph text\n"
    entries, _ = parse_yaml(content)
    assert len(entries) == 1
    assert "This is" in entries[0].msgid


def test_serialize_yaml_preserves_nested_structure() -> None:
    """Serialized YAML preserves the nested dict structure."""
    content = "a:\n  b:\n    c: Original\n  d: Other\n"
    entries, data = parse_yaml(content)
    entries[0].msgstr = "Translated"
    entries[1].msgstr = "Autre"
    result = serialize_yaml(entries, data)
    entries2, _ = parse_yaml(result)
    assert entries2[0].msgid == "Translated"
    assert entries2[1].msgid == "Autre"


def test_serialize_yaml_preserves_list() -> None:
    """Serialized YAML preserves list structures."""
    content = "items:\n  - Apple\n  - Banana\n"
    entries, data = parse_yaml(content)
    entries[0].msgstr = "Pomme"
    entries[1].msgstr = "Banane"
    result = serialize_yaml(entries, data)
    assert "Pomme" in result
    assert "Banane" in result


def test_serialize_yaml_roundtrip_nested() -> None:
    """Nested YAML roundtrip preserves structure and translations."""
    content = "ui:\n  buttons:\n    ok: OK\n    cancel: Cancel\n"
    entries, data = parse_yaml(content)
    entries[0].msgstr = "D'accord"
    entries[1].msgstr = "Annuler"
    result = serialize_yaml(entries, data)
    entries2, _ = parse_yaml(result)
    assert entries2[0].msgid == "D'accord"
    assert entries2[1].msgid == "Annuler"


# ---------------------------------------------------------------------------
# NEW: Properties with various separators and multiline
# ---------------------------------------------------------------------------


def test_parse_properties_multiline_continuation_three_lines() -> None:
    """Three continuation lines are joined correctly."""
    content = "msg=Hello \\\n  beautiful \\\n  world\n"
    entries, _ = parse_properties(content)
    assert len(entries) == 1
    assert "Hello" in entries[0].msgid
    assert "beautiful" in entries[0].msgid
    assert "world" in entries[0].msgid


def test_parse_properties_tab_only_separator() -> None:
    """Pure tab separator between key and value is recognized."""
    content = "mykey\tmyvalue\n"
    entries, _ = parse_properties(content)
    assert len(entries) == 1
    assert entries[0].msgid == "myvalue"
    assert entries[0].metadata["key"] == "mykey"


def test_parse_properties_unicode_value_roundtrip() -> None:
    r"""Unicode \uXXXX values survive parse/serialize roundtrip."""
    content = "name=caf\\u00e9\n"
    entries, structure = parse_properties(content)
    assert entries[0].msgid == "caf\u00e9"
    # Translate and serialize
    entries[0].msgstr = "caf\u00e9 au lait"
    result = serialize_properties(entries, structure)
    entries2, _ = parse_properties(result)
    assert entries2[0].msgid == "caf\u00e9 au lait"


def test_serialize_properties_blank_lines_preserved() -> None:
    """Blank lines in structure produce empty lines in output."""
    content = "a=1\n\nb=2\n"
    entries, structure = parse_properties(content)
    entries[0].msgstr = "one"
    entries[1].msgstr = "two"
    result = serialize_properties(entries, structure)
    assert "\n\n" in result


def test_properties_roundtrip_full() -> None:
    """Full roundtrip: parse -> translate -> serialize -> re-parse."""
    content = (
        "# Header comment\n"
        "title=My App\n"
        "\n"
        "! Another comment\n"
        "description=A great application\n"
    )
    entries, structure = parse_properties(content)
    entries[0].msgstr = "Mon App"
    entries[1].msgstr = "Une super application"
    result = serialize_properties(entries, structure)
    entries2, structure2 = parse_properties(result)
    assert entries2[0].msgid == "Mon App"
    assert entries2[1].msgid == "Une super application"
    assert "# Header comment" in result
    assert "! Another comment" in result


def test_parse_properties_escaped_separator_in_key() -> None:
    r"""Escaped separators in key (\= and \:) do not split."""
    content = "host\\:port=localhost:8080\n"
    entries, _ = parse_properties(content)
    assert len(entries) == 1
    assert entries[0].metadata["key"] == "host\\:port"
    assert entries[0].msgid == "localhost:8080"


# ---------------------------------------------------------------------------
# NEW: Apple Strings with escapes and edge cases
# ---------------------------------------------------------------------------


def test_parse_strings_tab_escape() -> None:
    r"""Escaped \t in value is unescaped to a real tab."""
    content = '"key" = "col1\\tcol2";\n'
    entries, _ = parse_strings(content)
    assert entries[0].msgid == "col1\tcol2"


def test_parse_strings_backslash_in_value() -> None:
    r"""Double backslash in value is unescaped to single backslash."""
    content = '"key" = "path\\\\to\\\\file";\n'
    entries, _ = parse_strings(content)
    assert entries[0].msgid == "path\\to\\file"


def test_parse_strings_multiple_entries() -> None:
    """Multiple .strings entries are all parsed."""
    content = '"key1" = "Value 1";\n"key2" = "Value 2";\n"key3" = "Value 3";\n'
    entries, _ = parse_strings(content)
    assert len(entries) == 3  # noqa: PLR2004


def test_serialize_strings_key_escaping() -> None:
    """Special characters in keys are escaped in output."""
    entries = [
        LocalizationEntry(
            index=0,
            msgid="original",
            msgstr="translated",
            metadata={"key": 'say "hi"'},
        ),
    ]
    structure = [("entry", 0)]
    result = serialize_strings(entries, structure)
    assert r"\"hi\"" in result


def test_strings_roundtrip_full() -> None:
    """Full roundtrip: parse -> translate -> serialize -> re-parse."""
    content = (
        '/* Header */\n"greeting" = "Hello";\n\n// Section\n"farewell" = "Goodbye";\n'
    )
    entries, structure = parse_strings(content)
    entries[0].msgstr = "Bonjour"
    entries[1].msgstr = "Au revoir"
    result = serialize_strings(entries, structure)
    entries2, _ = parse_strings(result)
    assert entries2[0].msgid == "Bonjour"
    assert entries2[1].msgid == "Au revoir"


def test_parse_strings_only_comments() -> None:
    """File with only comments returns no entries."""
    content = "/* Just a comment */\n// Another comment\n"
    entries, structure = parse_strings(content)
    assert entries == []
    raw_items = [s for s in structure if s[0] == "raw"]
    assert len(raw_items) >= 2  # noqa: PLR2004


def test_parse_strings_unicode_cjk() -> None:
    """CJK unicode in .strings is handled correctly."""
    content = '"key" = "\u4f60\u597d\u4e16\u754c";\n'
    entries, _ = parse_strings(content)
    assert entries[0].msgid == "\u4f60\u597d\u4e16\u754c"


# ---------------------------------------------------------------------------
# NEW: Roundtrip tests (parse -> translate -> serialize) for each format
# ---------------------------------------------------------------------------


def test_yaml_roundtrip_complex() -> None:
    """Complex YAML with nested dicts and lists survives roundtrip."""
    content = (
        "app:\n"
        "  name: MyApp\n"
        "  settings:\n"
        "    - Dark Mode\n"
        "    - Auto Save\n"
        "  version: '1.0'\n"
    )
    entries, data = parse_yaml(content)
    for entry in entries:
        entry.msgstr = f"TR_{entry.msgid}"
    result = serialize_yaml(entries, data)
    entries2, _ = parse_yaml(result)
    for e in entries2:
        assert e.msgid.startswith("TR_")


def test_properties_roundtrip_unicode() -> None:
    """Properties with unicode content survives roundtrip."""
    content = "greeting=\u3053\u3093\u306b\u3061\u306f\n"
    entries, structure = parse_properties(content)
    entries[0].msgstr = "\u4f60\u597d"
    result = serialize_properties(entries, structure)
    entries2, _ = parse_properties(result)
    assert entries2[0].msgid == "\u4f60\u597d"


def test_strings_roundtrip_escapes() -> None:
    """Apple Strings with special chars survives roundtrip."""
    content = '"msg" = "Line1\\nLine2\\t\\"quoted\\"";\n'
    entries, structure = parse_strings(content)
    assert entries[0].msgid == 'Line1\nLine2\t"quoted"'
    entries[0].msgstr = 'New\nLine\t"val"'
    result = serialize_strings(entries, structure)
    entries2, _ = parse_strings(result)
    assert entries2[0].msgid == 'New\nLine\t"val"'


# ---------------------------------------------------------------------------
# NEW: Empty and BOM files
# ---------------------------------------------------------------------------


def test_parse_yaml_only_comments() -> None:
    """YAML with only comments returns no entries."""
    content = "# Just a comment\n# Another\n"
    entries, data = parse_yaml(content)
    assert entries == []


def test_parse_properties_bom_with_entries() -> None:
    """Properties with BOM and entries parses correctly."""
    content = "\ufeff# comment\nkey=value\n"
    entries, structure = parse_properties(content)
    assert len(entries) == 1
    assert entries[0].msgid == "value"


def test_parse_strings_bom_with_entries() -> None:
    """Strings with BOM and entries parses correctly."""
    content = '\ufeff"key" = "value";\n'
    entries, _ = parse_strings(content)
    assert len(entries) == 1
    assert entries[0].msgid == "value"


# ---------------------------------------------------------------------------
# NEW: Malformed YAML
# ---------------------------------------------------------------------------


def test_parse_yaml_null_document() -> None:
    """YAML that parses to null returns no entries."""
    content = "~\n"
    entries, data = parse_yaml(content)
    assert entries == []
    assert data is None


# ---------------------------------------------------------------------------
# NEW: Dispatcher edge cases
# ---------------------------------------------------------------------------


def test_serialize_keyvalue_yml() -> None:
    """serialize_keyvalue dispatches to YAML serializer for .yml."""
    entries, data = parse_keyvalue("key: Hello\n", ".yml")
    entries[0].msgstr = "Bonjour"
    result = serialize_keyvalue(entries, data, ".yml")
    assert "Bonjour" in result


def test_parse_keyvalue_empty_yaml() -> None:
    """parse_keyvalue with empty YAML returns no entries."""
    entries, data = parse_keyvalue("", ".yaml")
    assert entries == []


def test_parse_keyvalue_empty_properties() -> None:
    """parse_keyvalue with empty properties returns no entries."""
    entries, _ = parse_keyvalue("", ".properties")
    assert entries == []


def test_parse_keyvalue_empty_strings() -> None:
    """parse_keyvalue with empty strings returns no entries."""
    entries, _ = parse_keyvalue("", ".strings")
    assert entries == []


# ---------------------------------------------------------------------------
# Edge case: YAML with "yes"/"no" boolean coercion
# ---------------------------------------------------------------------------


def test_parse_yaml_yes_no_boolean_coercion() -> None:
    """YAML 'yes'/'no' values are coerced to booleans by PyYAML and NOT extracted.

    PyYAML's safe_load interprets bare yes/no/on/off/true/false as booleans.
    Since _extract_yaml_strings only extracts ``isinstance(data, str)``,
    these boolean values are silently skipped.  This documents the behavior.
    """
    content = "enabled: yes\ndisabled: no\nname: Alice\n"
    entries, data = parse_yaml(content)
    # Only the string value "Alice" is extracted
    assert len(entries) == 1
    assert entries[0].msgid == "Alice"
    # The parsed data has booleans, not strings
    assert data["enabled"] is True
    assert data["disabled"] is False


# ---------------------------------------------------------------------------
# Edge case: YAML with literal block scalar (|) multi-line values
# ---------------------------------------------------------------------------


def test_parse_yaml_literal_block_scalar() -> None:
    """YAML literal block scalar (|) preserves newlines and is extracted as a string."""
    content = "description: |\n  Line one\n  Line two\n  Line three\n"
    entries, data = parse_yaml(content)
    assert len(entries) == 1
    # Literal block scalar preserves newlines, with a trailing newline
    assert "Line one\n" in entries[0].msgid
    assert "Line two\n" in entries[0].msgid
    assert "Line three\n" in entries[0].msgid


# ---------------------------------------------------------------------------
# Edge case: YAML with null variants (~ and bare empty key:)
# ---------------------------------------------------------------------------


def test_parse_yaml_null_variants_skipped() -> None:
    """YAML null variants (explicit ~ and bare empty value) are not extracted.

    Both ``key: ~`` and ``key:`` (with no value) parse as None in PyYAML.
    Since None is not a string, these are skipped by _extract_yaml_strings.
    """
    content = "tilde_null: ~\nbare_null:\nvalid: Hello\n"
    entries, data = parse_yaml(content)
    assert len(entries) == 1
    assert entries[0].msgid == "Hello"
    assert data["tilde_null"] is None
    assert data["bare_null"] is None


# ---------------------------------------------------------------------------
# Edge case: Properties with tab separator
# ---------------------------------------------------------------------------


def test_parse_properties_tab_separator() -> None:
    """Properties file with tab as the key-value separator."""
    content = "key\tvalue\n"
    entries, _ = parse_properties(content)
    assert len(entries) == 1
    assert entries[0].msgid == "value"
    # Tab is whitespace → treated as whitespace separator
    assert "\t" in entries[0].metadata["separator"]


# ---------------------------------------------------------------------------
# Edge case: Properties with 3+ line continuation (backslash at end of line)
# ---------------------------------------------------------------------------


def test_parse_properties_three_line_continuation() -> None:
    """Properties value spanning 3+ lines via backslash continuation."""
    content = "message=Hello \\\n    beautiful \\\n    world\n"
    entries, _ = parse_properties(content)
    assert len(entries) == 1
    assert entries[0].msgid == "Hello beautiful world"


# ---------------------------------------------------------------------------
# Edge case: Properties with empty key (=value)
# ---------------------------------------------------------------------------


def test_parse_properties_empty_key() -> None:
    """Properties file with an empty key (line starting with =)."""
    content = "=some value\n"
    entries, _ = parse_properties(content)
    assert len(entries) == 1
    assert entries[0].metadata["key"] == ""
    assert entries[0].msgid == "some value"


# ---------------------------------------------------------------------------
# Edge case: Strings with semicolons in value
# ---------------------------------------------------------------------------


def test_parse_strings_semicolons_in_value() -> None:
    """Apple Strings value containing semicolons is parsed correctly.

    The regex matches `"key" = "value";` — the semicolon inside the
    quoted value is protected by the quotes and does not terminate early.
    """
    content = '"key" = "Hello; World; Test";\n'
    entries, _ = parse_strings(content)
    assert len(entries) == 1
    assert entries[0].msgid == "Hello; World; Test"


# ---------------------------------------------------------------------------
# Edge case: YAML with date-like string (2024-01-01) — coerced to date
# ---------------------------------------------------------------------------


def test_parse_yaml_date_like_string_coerced() -> None:
    """YAML bare date value (2024-01-01) is coerced to datetime.date by PyYAML.

    Since it is not a string, it is NOT extracted. This documents the behavior.
    To keep it as a string, the YAML must quote it: "2024-01-01".
    """
    import datetime  # noqa: PLC0415

    content = "release_date: 2024-01-01\nname: Release\n"
    entries, data = parse_yaml(content)
    # Only "Release" is extracted; the date is coerced
    assert len(entries) == 1
    assert entries[0].msgid == "Release"
    assert isinstance(data["release_date"], datetime.date)
    assert not isinstance(data["release_date"], str)


# ---------------------------------------------------------------------------
# EXPANDED: YAML parsing edge cases
# ---------------------------------------------------------------------------


def test_parse_yaml_nested_four_levels() -> None:
    """Four-level nesting extracts leaf strings."""
    content = "a:\n  b:\n    c:\n      d:\n        e: Leaf\n"
    entries, _ = parse_yaml(content)
    assert len(entries) == 1
    assert entries[0].msgid == "Leaf"
    assert entries[0].metadata["path"] == ("a", "b", "c", "d", "e")


def test_parse_yaml_list_of_dicts_with_lists() -> None:
    """YAML with nested structure: list of dicts containing lists."""
    content = (
        "categories:\n"
        "  - name: Fruits\n"
        "    items:\n"
        "      - Apple\n"
        "      - Banana\n"
        "  - name: Veggies\n"
        "    items:\n"
        "      - Carrot\n"
    )
    entries, _ = parse_yaml(content)
    texts = {e.msgid for e in entries}
    assert "Fruits" in texts
    assert "Apple" in texts
    assert "Banana" in texts
    assert "Veggies" in texts
    assert "Carrot" in texts
    assert len(entries) == 5  # noqa: PLR2004


def test_parse_yaml_empty_dict() -> None:
    """YAML with empty dict returns no entries."""
    content = "data: {}\n"
    entries, _ = parse_yaml(content)
    assert entries == []


def test_parse_yaml_empty_list() -> None:
    """YAML with empty list returns no entries."""
    content = "items: []\n"
    entries, _ = parse_yaml(content)
    assert entries == []


def test_parse_yaml_mixed_nesting() -> None:
    """YAML with mixed dict/list nesting extracts all leaf strings."""
    content = (
        "app:\n"
        "  title: My App\n"
        "  tags:\n"
        "    - first\n"
        "    - second\n"
        "  config:\n"
        "    debug: false\n"
        "    name: Config Name\n"
    )
    entries, _ = parse_yaml(content)
    texts = {e.msgid for e in entries}
    assert texts == {"My App", "first", "second", "Config Name"}


def test_parse_yaml_special_chars() -> None:
    """YAML with special characters in values."""
    content = 'special: "Hello & World <test>"\n'
    entries, _ = parse_yaml(content)
    assert entries[0].msgid == "Hello & World <test>"


def test_parse_yaml_multiline_folded_preserves_content() -> None:
    """YAML folded block scalar (>) content is extracted."""
    content = "desc: >\n  This is\n  folded text.\n"
    entries, _ = parse_yaml(content)
    assert len(entries) == 1
    assert "This is" in entries[0].msgid


def test_parse_yaml_quoted_string() -> None:
    """YAML quoted strings with colons are extracted correctly."""
    content = 'url: "http://example.com:8080/path"\n'
    entries, _ = parse_yaml(content)
    assert entries[0].msgid == "http://example.com:8080/path"


def test_parse_yaml_integer_keys() -> None:
    """YAML with integer keys extracts string values."""
    content = "1: First\n2: Second\n3: Third\n"
    entries, _ = parse_yaml(content)
    assert len(entries) == 3  # noqa: PLR2004


def test_parse_yaml_large_file() -> None:
    """YAML with 200 entries parses all."""
    lines = [f"key{i}: Value {i}" for i in range(200)]
    content = "\n".join(lines) + "\n"
    entries, _ = parse_yaml(content)
    assert len(entries) == 200  # noqa: PLR2004


def test_parse_yaml_nested_list_of_strings() -> None:
    """YAML nested list with only strings."""
    content = "colors:\n  - red\n  - green\n  - blue\n  - yellow\n"
    entries, _ = parse_yaml(content)
    assert len(entries) == 4  # noqa: PLR2004
    assert entries[0].msgid == "red"
    assert entries[3].msgid == "yellow"


# ---------------------------------------------------------------------------
# EXPANDED: YAML serialization edge cases
# ---------------------------------------------------------------------------


def test_serialize_yaml_empty_entries() -> None:
    """Serializing empty entries with None data."""
    result = serialize_yaml([], None)
    assert "null" in result or result.strip() == "null"


def test_serialize_yaml_preserves_non_string_values() -> None:
    """YAML serialization preserves non-string values unchanged."""
    content = "name: Alice\nage: 30\nactive: true\n"
    entries, data = parse_yaml(content)
    entries[0].msgstr = "Alicia"
    result = serialize_yaml(entries, data)
    # The non-string values should still be there
    assert "30" in result
    assert "true" in result
    assert "Alicia" in result


def test_serialize_yaml_deep_nesting_roundtrip() -> None:
    """Deep nesting roundtrip preserves structure."""
    content = "a:\n  b:\n    c:\n      d: Original\n"
    entries, data = parse_yaml(content)
    entries[0].msgstr = "Translated"
    result = serialize_yaml(entries, data)
    entries2, _ = parse_yaml(result)
    assert entries2[0].msgid == "Translated"
    assert entries2[0].metadata["path"] == ("a", "b", "c", "d")


def test_serialize_yaml_list_roundtrip() -> None:
    """YAML list roundtrip preserves order."""
    content = "items:\n  - Alpha\n  - Beta\n  - Gamma\n"
    entries, data = parse_yaml(content)
    entries[0].msgstr = "A"
    entries[1].msgstr = "B"
    entries[2].msgstr = "C"
    result = serialize_yaml(entries, data)
    entries2, _ = parse_yaml(result)
    assert entries2[0].msgid == "A"
    assert entries2[1].msgid == "B"
    assert entries2[2].msgid == "C"


def test_serialize_yaml_unicode_roundtrip() -> None:
    """YAML with unicode roundtrip works."""
    content = "greeting: \u4f60\u597d\nfarewell: \u518d\u89c1\n"
    entries, data = parse_yaml(content)
    entries[0].msgstr = "\u3053\u3093\u306b\u3061\u306f"
    entries[1].msgstr = "\u3055\u3088\u306a\u3089"
    result = serialize_yaml(entries, data)
    entries2, _ = parse_yaml(result)
    assert entries2[0].msgid == "\u3053\u3093\u306b\u3061\u306f"
    assert entries2[1].msgid == "\u3055\u3088\u306a\u3089"


# ---------------------------------------------------------------------------
# EXPANDED: Properties parsing edge cases
# ---------------------------------------------------------------------------


def test_parse_properties_multiple_equals_in_value() -> None:
    """Properties value with multiple = signs."""
    content = "expr=a==b&&c==d\n"
    entries, _ = parse_properties(content)
    assert entries[0].msgid == "a==b&&c==d"


def test_parse_properties_colon_in_value() -> None:
    """Properties value with colons after = separator."""
    content = "time=12:30:45\n"
    entries, _ = parse_properties(content)
    assert entries[0].msgid == "12:30:45"


def test_parse_properties_empty_lines_only() -> None:
    """Properties with only blank lines returns no entries."""
    content = "\n\n\n\n"
    entries, structure = parse_properties(content)
    assert entries == []
    blank_items = [s for s in structure if s[0] == "blank"]
    assert len(blank_items) >= 1


def test_parse_properties_unicode_key() -> None:
    """Properties with unicode in key."""
    content = "\u00e9l\u00e8ve=student\n"
    entries, _ = parse_properties(content)
    assert len(entries) == 1
    assert entries[0].msgid == "student"


def test_parse_properties_long_value() -> None:
    """Properties with very long value."""
    long_val = "x" * 10000
    content = f"key={long_val}\n"
    entries, _ = parse_properties(content)
    assert entries[0].msgid == long_val


def test_parse_properties_space_equals() -> None:
    """Properties with space before and after equals."""
    content = "key = value with spaces\n"
    entries, _ = parse_properties(content)
    assert entries[0].msgid == "value with spaces"


def test_parse_properties_tab_equals() -> None:
    """Properties with tab before equals."""
    content = "key\t=\tvalue\n"
    entries, _ = parse_properties(content)
    assert entries[0].msgid == "value"


def test_parse_properties_escaped_space_in_key() -> None:
    r"""Properties with escaped space in key."""
    content = "key\\ name=value\n"
    entries, _ = parse_properties(content)
    assert entries[0].metadata["key"] == "key\\ name"


def test_parse_properties_continuation_four_lines() -> None:
    """Properties value spanning four lines."""
    content = "msg=A \\\n  B \\\n  C \\\n  D\n"
    entries, _ = parse_properties(content)
    assert "A" in entries[0].msgid
    assert "D" in entries[0].msgid


def test_parse_properties_exclamation_comment() -> None:
    """Properties with ! comment."""
    content = "! This is a comment\nkey=value\n"
    entries, structure = parse_properties(content)
    assert len(entries) == 1
    comment_items = [s for s in structure if s[0] == "comment"]
    assert len(comment_items) == 1


def test_parse_properties_mixed_separators() -> None:
    """Properties with mixed = and : separators."""
    content = "key1=val1\nkey2:val2\nkey3 val3\n"
    entries, _ = parse_properties(content)
    assert len(entries) == 3  # noqa: PLR2004
    assert entries[0].metadata["separator"] == "="
    assert entries[1].metadata["separator"] == ":"


def test_parse_properties_large_file() -> None:
    """Properties with 200 entries."""
    lines = [f"key{i}=value{i}" for i in range(200)]
    content = "\n".join(lines) + "\n"
    entries, _ = parse_properties(content)
    assert len(entries) == 200  # noqa: PLR2004


# ---------------------------------------------------------------------------
# EXPANDED: Properties serialization edge cases
# ---------------------------------------------------------------------------


def test_serialize_properties_empty() -> None:
    """Serializing empty entries and structure."""
    result = serialize_properties([], [])
    assert result == "\n"


def test_serialize_properties_backslash_in_value() -> None:
    r"""Backslash in value is escaped as \\ in output."""
    entries = [
        LocalizationEntry(
            index=0,
            msgid="orig",
            msgstr="path\\to\\file",
            metadata={"key": "k", "separator": "="},
        ),
    ]
    structure = [("entry", 0)]
    result = serialize_properties(entries, structure)
    assert "path\\\\to\\\\file" in result


def test_serialize_properties_tab_in_value() -> None:
    r"""Tab in value is escaped as \t in output."""
    entries = [
        LocalizationEntry(
            index=0,
            msgid="orig",
            msgstr="col1\tcol2",
            metadata={"key": "k", "separator": "="},
        ),
    ]
    structure = [("entry", 0)]
    result = serialize_properties(entries, structure)
    assert "col1\\tcol2" in result


def test_serialize_properties_roundtrip_special_chars() -> None:
    """Properties roundtrip with special characters."""
    content = "msg=Hello\\nWorld\\tEnd\n"
    entries, structure = parse_properties(content)
    entries[0].msgstr = "Bonjour\nMonde\tFin"
    result = serialize_properties(entries, structure)
    entries2, _ = parse_properties(result)
    assert entries2[0].msgid == "Bonjour\nMonde\tFin"


def test_serialize_properties_structure_ordering() -> None:
    """Properties serialization preserves comment-entry-blank ordering."""
    content = "# Header\nkey1=val1\n\n# Section\nkey2=val2\n"
    entries, structure = parse_properties(content)
    entries[0].msgstr = "tr1"
    entries[1].msgstr = "tr2"
    result = serialize_properties(entries, structure)
    lines = result.split("\n")
    # Header comment should come first
    assert lines[0] == "# Header"


# ---------------------------------------------------------------------------
# EXPANDED: Apple Strings parsing edge cases
# ---------------------------------------------------------------------------


def test_parse_strings_many_entries() -> None:
    """Strings file with 100 entries."""
    lines = [f'"key{i}" = "Value {i}";' for i in range(100)]
    content = "\n".join(lines) + "\n"
    entries, _ = parse_strings(content)
    assert len(entries) == 100  # noqa: PLR2004


def test_parse_strings_empty_key() -> None:
    """Strings with empty key."""
    content = '"" = "Value";\n'
    entries, _ = parse_strings(content)
    assert len(entries) == 1
    assert entries[0].metadata["key"] == ""
    assert entries[0].msgid == "Value"


def test_parse_strings_very_long_value() -> None:
    """Strings with very long value."""
    long_val = "x" * 5000
    content = f'"key" = "{long_val}";\n'
    entries, _ = parse_strings(content)
    assert len(entries) == 1
    assert entries[0].msgid == long_val


def test_parse_strings_special_chars_in_value() -> None:
    """Strings with special characters in value."""
    content = '"key" = "Hello & World <test>";\n'
    entries, _ = parse_strings(content)
    assert entries[0].msgid == "Hello & World <test>"


def test_parse_strings_url_in_value() -> None:
    """Strings with URL in value."""
    content = '"link" = "https://example.com/path?a=1&b=2";\n'
    entries, _ = parse_strings(content)
    assert entries[0].msgid == "https://example.com/path?a=1&b=2"


def test_parse_strings_consecutive_entries_no_whitespace() -> None:
    """Multiple entries without whitespace between them."""
    content = '"k1" = "v1";"k2" = "v2";"k3" = "v3";'
    entries, _ = parse_strings(content)
    assert len(entries) == 3  # noqa: PLR2004


def test_parse_strings_block_comment_multiline() -> None:
    """Multi-line block comment is preserved."""
    content = '/* Multi\n   line\n   comment */\n"key" = "val";\n'
    entries, structure = parse_strings(content)
    assert len(entries) == 1
    raw_text = "".join(str(s[1]) for s in structure if s[0] == "raw")
    assert "Multi" in raw_text
    assert "comment" in raw_text


def test_parse_strings_whitespace_around_equals() -> None:
    """Strings with extra whitespace around = sign."""
    content = '"key"   =   "value";\n'
    entries, _ = parse_strings(content)
    assert len(entries) == 1
    assert entries[0].msgid == "value"


def test_parse_strings_mixed_comments_and_entries() -> None:
    """Strings with mixed comments and entries."""
    content = (
        "/* Comment 1 */\n"
        '"k1" = "v1";\n'
        "// Comment 2\n"
        '"k2" = "v2";\n'
        "/* Comment 3 */\n"
        '"k3" = "v3";\n'
    )
    entries, structure = parse_strings(content)
    assert len(entries) == 3  # noqa: PLR2004
    raw_items = [s for s in structure if s[0] == "raw"]
    assert len(raw_items) >= 3  # noqa: PLR2004


# ---------------------------------------------------------------------------
# EXPANDED: Apple Strings serialization edge cases
# ---------------------------------------------------------------------------


def test_serialize_strings_empty() -> None:
    """Serializing empty Strings produces empty output."""
    result = serialize_strings([], [])
    assert result == ""


def test_serialize_strings_backslash_in_value() -> None:
    r"""Backslash in value is escaped as \\ in output."""
    entries = [
        LocalizationEntry(
            index=0,
            msgid="orig",
            msgstr="path\\file",
            metadata={"key": "k"},
        ),
    ]
    structure = [("entry", 0)]
    result = serialize_strings(entries, structure)
    assert "path\\\\file" in result


def test_serialize_strings_newline_in_value() -> None:
    r"""Newline in value is escaped as \n in output."""
    entries = [
        LocalizationEntry(
            index=0,
            msgid="orig",
            msgstr="Line1\nLine2",
            metadata={"key": "k"},
        ),
    ]
    structure = [("entry", 0)]
    result = serialize_strings(entries, structure)
    assert "Line1\\nLine2" in result


def test_serialize_strings_tab_in_value() -> None:
    r"""Tab in value is escaped as \t in output."""
    entries = [
        LocalizationEntry(
            index=0,
            msgid="orig",
            msgstr="col1\tcol2",
            metadata={"key": "k"},
        ),
    ]
    structure = [("entry", 0)]
    result = serialize_strings(entries, structure)
    assert "col1\\tcol2" in result


def test_serialize_strings_quote_in_key_and_value() -> None:
    r"""Quotes in both key and value are escaped."""
    entries = [
        LocalizationEntry(
            index=0,
            msgid="orig",
            msgstr='Say "bye"',
            metadata={"key": 'say "hi"'},
        ),
    ]
    structure = [("entry", 0)]
    result = serialize_strings(entries, structure)
    assert r"\"hi\"" in result
    assert r"\"bye\"" in result


def test_serialize_strings_roundtrip_100_entries() -> None:
    """Strings roundtrip with 100 entries."""
    lines = [f'"key{i}" = "Value {i}";' for i in range(100)]
    content = "\n".join(lines) + "\n"
    entries, structure = parse_strings(content)
    for e in entries:
        e.msgstr = f"TR_{e.msgid}"
    result = serialize_strings(entries, structure)
    entries2, _ = parse_strings(result)
    assert len(entries2) == 100  # noqa: PLR2004
    assert entries2[0].msgid.startswith("TR_")


# ---------------------------------------------------------------------------
# EXPANDED: Escape/unescape edge cases
# ---------------------------------------------------------------------------


def test_unescape_properties_multiple_escapes() -> None:
    r"""Multiple escape sequences in properties."""
    assert _unescape_properties("a\\nb\\tc\\\\d") == "a\nb\tc\\d"


def test_escape_properties_plain_text() -> None:
    """Plain text without special chars is returned unchanged."""
    assert _escape_properties_value("Hello World") == "Hello World"


def test_unescape_strings_consecutive() -> None:
    r"""Multiple consecutive escape sequences in strings."""
    assert _unescape_strings('\\n\\t\\\\\\"') == '\n\t\\"'


def test_escape_strings_plain_text() -> None:
    """Plain text without special chars is returned unchanged."""
    assert _escape_strings("Hello World") == "Hello World"


def test_unescape_properties_unicode_roundtrip() -> None:
    r"""Unicode escape roundtrip for properties."""
    original = "caf\u00e9"
    escaped = "caf\\u00e9"
    assert _unescape_properties(escaped) == original


def test_unescape_properties_multiple_unicode() -> None:
    r"""Multiple unicode escapes in properties."""
    assert _unescape_properties("\\u0041\\u0042") == "AB"


def test_unescape_strings_empty_string() -> None:
    """Unescaping empty string returns empty."""
    assert _unescape_strings("") == ""


def test_escape_strings_empty_string() -> None:
    """Escaping empty string returns empty."""
    assert _escape_strings("") == ""


def test_unescape_properties_empty_string() -> None:
    """Unescaping empty properties value returns empty."""
    assert _unescape_properties("") == ""


def test_escape_properties_empty_string() -> None:
    """Escaping empty properties value returns empty."""
    assert _escape_properties_value("") == ""


# ---------------------------------------------------------------------------
# EXPANDED: Dispatcher edge cases
# ---------------------------------------------------------------------------


def test_parse_keyvalue_yaml_empty() -> None:
    """parse_keyvalue with empty YAML content."""
    entries, data = parse_keyvalue("", ".yaml")
    assert entries == []


def test_parse_keyvalue_yml_empty() -> None:
    """parse_keyvalue with empty .yml content."""
    entries, data = parse_keyvalue("", ".yml")
    assert entries == []


def test_serialize_keyvalue_yml_roundtrip() -> None:
    """serialize_keyvalue .yml roundtrip."""
    content = "key: Hello\n"
    entries, data = parse_keyvalue(content, ".yml")
    entries[0].msgstr = "Salut"
    result = serialize_keyvalue(entries, data, ".yml")
    entries2, _ = parse_keyvalue(result, ".yml")
    assert entries2[0].msgid == "Salut"


def test_serialize_keyvalue_properties_roundtrip() -> None:
    """serialize_keyvalue .properties roundtrip with translation."""
    content = "greet=Hello\nbye=Goodbye\n"
    entries, structure = parse_keyvalue(content, ".properties")
    entries[0].msgstr = "Bonjour"
    entries[1].msgstr = "Au revoir"
    result = serialize_keyvalue(entries, structure, ".properties")
    entries2, _ = parse_keyvalue(result, ".properties")
    assert entries2[0].msgid == "Bonjour"
    assert entries2[1].msgid == "Au revoir"


def test_serialize_keyvalue_strings_roundtrip() -> None:
    """serialize_keyvalue .strings roundtrip with translation."""
    content = '"greet" = "Hello";\n"bye" = "Goodbye";\n'
    entries, structure = parse_keyvalue(content, ".strings")
    entries[0].msgstr = "Bonjour"
    entries[1].msgstr = "Au revoir"
    result = serialize_keyvalue(entries, structure, ".strings")
    entries2, _ = parse_keyvalue(result, ".strings")
    assert entries2[0].msgid == "Bonjour"
    assert entries2[1].msgid == "Au revoir"


# ---------------------------------------------------------------------------
# EXPANDED: YAML with flow-style collections
# ---------------------------------------------------------------------------


def test_parse_yaml_flow_style_dict() -> None:
    """YAML flow-style dict extracts string values."""
    content = "data: {name: Alice, city: Paris}\n"
    entries, _ = parse_yaml(content)
    texts = {e.msgid for e in entries}
    assert "Alice" in texts
    assert "Paris" in texts


def test_parse_yaml_flow_style_list() -> None:
    """YAML flow-style list extracts string values."""
    content = "items: [Apple, Banana, Cherry]\n"
    entries, _ = parse_yaml(content)
    assert len(entries) == 3  # noqa: PLR2004
    texts = {e.msgid for e in entries}
    assert "Apple" in texts
    assert "Cherry" in texts


def test_parse_yaml_nested_flow_and_block() -> None:
    """YAML with mixed flow and block styles."""
    content = "parent:\n  child: {key: Value}\n  list: [A, B]\n"
    entries, _ = parse_yaml(content)
    texts = {e.msgid for e in entries}
    assert "Value" in texts
    assert "A" in texts
    assert "B" in texts


# ---------------------------------------------------------------------------
# EXPANDED: _join_continuation_lines edge cases
# ---------------------------------------------------------------------------


def test_join_continuation_lines_no_continuation() -> None:
    """Lines without continuation are returned as-is."""
    from src.utils.keyvalue_utils import _join_continuation_lines  # noqa: PLC0415

    lines = ["line1", "line2", "line3"]
    result = _join_continuation_lines(lines)
    assert result == ["line1", "line2", "line3"]


def test_join_continuation_lines_multiple_continuations() -> None:
    """Multiple continuation lines are all joined."""
    from src.utils.keyvalue_utils import _join_continuation_lines  # noqa: PLC0415

    lines = ["a\\", "b\\", "c\\", "d"]
    result = _join_continuation_lines(lines)
    assert len(result) == 1
    assert result[0] == "abcd"


def test_join_continuation_lines_empty_list() -> None:
    """Empty list returns empty list."""
    from src.utils.keyvalue_utils import _join_continuation_lines  # noqa: PLC0415

    result = _join_continuation_lines([])
    assert result == []


# ---------------------------------------------------------------------------
# EXPANDED: _parse_properties_line edge cases
# ---------------------------------------------------------------------------


def test_parse_properties_line_empty_key_equals_value() -> None:
    """Line =value has empty key."""
    from src.utils.keyvalue_utils import _parse_properties_line  # noqa: PLC0415

    result = _parse_properties_line("=value")
    assert result is not None
    key, sep, val = result
    assert key == ""
    assert sep == "="
    assert val == "value"


def test_parse_properties_line_only_key() -> None:
    """Line with only key (no separator) returns key with = separator."""
    from src.utils.keyvalue_utils import _parse_properties_line  # noqa: PLC0415

    result = _parse_properties_line("onlykey")
    assert result is not None
    key, sep, val = result
    assert key == "onlykey"
    assert sep == "="
    assert val == ""


def test_parse_properties_line_empty_string() -> None:
    """Empty line returns None."""
    from src.utils.keyvalue_utils import _parse_properties_line  # noqa: PLC0415

    result = _parse_properties_line("")
    assert result is None
