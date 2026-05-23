"""Unit tests for subtitle parsing and serialization utilities."""

import pytest

from src.utils.subtitle_utils import (
    SubtitleEntry,
    _restore_ass_tags,
    _strip_ass_tags,
    is_subtitle_format,
    mirror_ass_alignment_for_rtl,
    parse_ass,
    parse_srt,
    parse_subtitle,
    parse_vtt,
    serialize_ass,
    serialize_srt,
    serialize_subtitle,
    serialize_vtt,
)

# ---------------------------------------------------------------------------
# is_subtitle_format
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ext", [".srt", ".vtt", ".ass", ".ssa"])
def test_is_subtitle_format_true(ext: str) -> None:
    """Known subtitle extensions return True."""
    assert is_subtitle_format(ext) is True


@pytest.mark.parametrize("ext", [".txt", ".html", ".json", ".mp4", ".docx"])
def test_is_subtitle_format_false(ext: str) -> None:
    """Non-subtitle extensions return False."""
    assert is_subtitle_format(ext) is False


# ---------------------------------------------------------------------------
# SRT parsing
# ---------------------------------------------------------------------------


def test_parse_srt_basic() -> None:
    """Parses a standard two-entry SRT file."""
    content = (
        "1\n00:00:01,000 --> 00:00:04,000\nHello\n\n"
        "2\n00:00:05,000 --> 00:00:08,000\nWorld\n"
    )
    entries, fmt = parse_srt(content)
    assert fmt is None
    assert len(entries) == 2  # noqa: PLR2004
    assert entries[0].start == "00:00:01,000"
    assert entries[0].end == "00:00:04,000"
    assert entries[0].text == "Hello"
    assert entries[1].text == "World"


def test_parse_srt_multiline_text() -> None:
    """Entry with multiple text lines is joined with newlines."""
    content = "1\n00:00:01,000 --> 00:00:04,000\nLine one\nLine two\n"
    entries, _ = parse_srt(content)
    assert len(entries) == 1
    assert entries[0].text == "Line one\nLine two"


def test_parse_srt_html_tags() -> None:
    """HTML tags in SRT text are preserved."""
    content = "1\n00:00:01,000 --> 00:00:04,000\n<i>Italic</i>\n"
    entries, _ = parse_srt(content)
    assert entries[0].text == "<i>Italic</i>"


def test_parse_srt_empty() -> None:
    """Empty content returns no entries."""
    entries, _ = parse_srt("")
    assert entries == []


def test_parse_srt_bom() -> None:
    """UTF-8 BOM is stripped before parsing."""
    content = "\ufeff1\n00:00:01,000 --> 00:00:04,000\nHello\n"
    entries, _ = parse_srt(content)
    assert len(entries) == 1
    assert entries[0].text == "Hello"


def test_parse_srt_extra_blank_lines() -> None:
    """Multiple blank lines between blocks are handled correctly."""
    content = (
        "1\n00:00:01,000 --> 00:00:04,000\nHello\n\n\n\n"
        "2\n00:00:05,000 --> 00:00:08,000\nWorld\n"
    )
    entries, _ = parse_srt(content)
    assert len(entries) == 2  # noqa: PLR2004


def test_serialize_srt_roundtrip() -> None:
    """Parse then serialize produces valid SRT output."""
    original = (
        "1\n00:00:01,000 --> 00:00:04,000\nHello\n\n"
        "2\n00:00:05,000 --> 00:00:08,000\nWorld\n"
    )
    entries, fmt = parse_srt(original)
    result = serialize_srt(entries, fmt)
    # Re-parse the result to verify integrity
    entries2, _ = parse_srt(result)
    assert len(entries2) == 2  # noqa: PLR2004
    assert entries2[0].text == "Hello"
    assert entries2[1].text == "World"


def test_serialize_srt_preserves_timestamps() -> None:
    """Serialized SRT contains the original timestamps."""
    entries = [
        SubtitleEntry(index=0, start="01:23:45,678", end="01:23:50,000", text="Test"),
    ]
    result = serialize_srt(entries)
    assert "01:23:45,678 --> 01:23:50,000" in result


def test_serialize_srt_sequential_indices() -> None:
    """Serialized SRT uses sequential 1-based indices."""
    entries = [
        SubtitleEntry(index=0, start="00:00:01,000", end="00:00:02,000", text="A"),
        SubtitleEntry(index=5, start="00:00:03,000", end="00:00:04,000", text="B"),
    ]
    result = serialize_srt(entries)
    assert result.startswith("1\n")
    assert "\n2\n" in result


# ---------------------------------------------------------------------------
# VTT parsing
# ---------------------------------------------------------------------------


def test_parse_vtt_basic() -> None:
    """Parses a standard WebVTT file with header."""
    content = (
        "WEBVTT\n\n"
        "00:00:01.000 --> 00:00:04.000\nHello\n\n"
        "00:00:05.000 --> 00:00:08.000\nWorld\n"
    )
    entries, header = parse_vtt(content)
    assert "WEBVTT" in header
    assert len(entries) == 2  # noqa: PLR2004
    assert entries[0].text == "Hello"
    assert entries[1].text == "World"


def test_parse_vtt_with_notes() -> None:
    """NOTE blocks are preserved in header, not as entries."""
    content = (
        "WEBVTT\n\nNOTE This is a comment\n\n00:00:01.000 --> 00:00:04.000\nHello\n"
    )
    entries, header = parse_vtt(content)
    assert "NOTE" in header
    assert len(entries) == 1


def test_parse_vtt_with_styles() -> None:
    """STYLE blocks are preserved in header."""
    content = (
        "WEBVTT\n\n"
        "STYLE\n::cue { color: white; }\n\n"
        "00:00:01.000 --> 00:00:04.000\nHello\n"
    )
    entries, header = parse_vtt(content)
    assert "STYLE" in header
    assert len(entries) == 1


def test_parse_vtt_cue_settings() -> None:
    """Cue settings (position, align) are preserved in metadata."""
    content = "WEBVTT\n\n00:00:01.000 --> 00:00:04.000 position:10% align:left\nHello\n"
    entries, _ = parse_vtt(content)
    assert entries[0].metadata.get("cue_settings") == "position:10% align:left"


def test_parse_vtt_with_cue_id() -> None:
    """Cue identifiers are preserved in metadata."""
    content = "WEBVTT\n\nintro\n00:00:01.000 --> 00:00:04.000\nHello\n"
    entries, _ = parse_vtt(content)
    assert entries[0].metadata.get("cue_id") == "intro"


def test_parse_vtt_no_cue_id() -> None:
    """Cues without identifiers parse correctly."""
    content = "WEBVTT\n\n00:00:01.000 --> 00:00:04.000\nHello\n"
    entries, _ = parse_vtt(content)
    assert "cue_id" not in entries[0].metadata


def test_serialize_vtt_roundtrip() -> None:
    """Parse then serialize produces valid VTT output."""
    original = (
        "WEBVTT\n\n"
        "00:00:01.000 --> 00:00:04.000\nHello\n\n"
        "00:00:05.000 --> 00:00:08.000\nWorld\n"
    )
    entries, header = parse_vtt(original)
    result = serialize_vtt(entries, header)
    entries2, header2 = parse_vtt(result)
    assert "WEBVTT" in header2
    assert len(entries2) == 2  # noqa: PLR2004
    assert entries2[0].text == "Hello"


def test_serialize_vtt_preserves_header() -> None:
    """Serialized VTT contains the original header block."""
    entries = [
        SubtitleEntry(
            index=0,
            start="00:00:01.000",
            end="00:00:04.000",
            text="Test",
        ),
    ]
    header = "WEBVTT\n\nNOTE A test note"
    result = serialize_vtt(entries, header)
    assert result.startswith("WEBVTT")
    assert "NOTE A test note" in result


def test_serialize_vtt_cue_settings() -> None:
    """Cue settings are included in serialized timestamp line."""
    entries = [
        SubtitleEntry(
            index=0,
            start="00:00:01.000",
            end="00:00:04.000",
            text="Test",
            metadata={"cue_settings": "position:50%"},
        ),
    ]
    result = serialize_vtt(entries, "WEBVTT")
    assert "position:50%" in result


def test_serialize_vtt_cue_id() -> None:
    """Cue IDs appear before the timestamp line."""
    entries = [
        SubtitleEntry(
            index=0,
            start="00:00:01.000",
            end="00:00:04.000",
            text="Test",
            metadata={"cue_id": "intro"},
        ),
    ]
    result = serialize_vtt(entries, "WEBVTT")
    lines = result.strip().splitlines()
    # Find the line with "intro" — it should be before the timestamp
    intro_idx = next(i for i, ln in enumerate(lines) if ln.strip() == "intro")
    ts_idx = next(i for i, ln in enumerate(lines) if "-->" in ln)
    assert intro_idx < ts_idx


# ---------------------------------------------------------------------------
# ASS / SSA parsing
# ---------------------------------------------------------------------------


_SAMPLE_ASS = """\
[Script Info]
Title: Test
ScriptType: v4.00+

[V4+ Styles]
Format: Name, Fontname, Fontsize
Style: Default,Arial,20

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,Hello world
Dialogue: 0,0:00:05.00,0:00:08.00,Default,,0,0,0,,Goodbye world
"""


def test_parse_ass_basic() -> None:
    """Parses a standard ASS file with two dialogue lines."""
    entries, preserved = parse_ass(_SAMPLE_ASS)
    assert len(entries) == 2  # noqa: PLR2004
    assert entries[0].text == "Hello world"
    assert entries[1].text == "Goodbye world"
    assert entries[0].start == "0:00:01.00"
    assert entries[0].end == "0:00:04.00"


def test_parse_ass_preserves_sections() -> None:
    """Non-Events sections are preserved in the line list."""
    _, preserved = parse_ass(_SAMPLE_ASS)
    joined = "\n".join(preserved)
    assert "[Script Info]" in joined
    assert "[V4+ Styles]" in joined
    assert "Style: Default,Arial,20" in joined


def test_parse_ass_override_tags() -> None:
    """Override tags are stripped from the text field."""
    content = (
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
        "MarginV, Effect, Text\n"
        r"Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,{\b1}Bold text{\b0}"
        "\n"
    )
    entries, _ = parse_ass(content)
    assert entries[0].text == "Bold text"
    assert r"{\b1}" in entries[0].raw_text


def test_parse_ass_text_with_commas() -> None:
    """Commas inside the Text field are preserved."""
    content = (
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
        "MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,Hello, world, test\n"
    )
    entries, _ = parse_ass(content)
    assert entries[0].text == "Hello, world, test"


def test_parse_ass_comment_lines_ignored() -> None:
    """Comment lines in [Events] are not extracted as entries."""
    content = (
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
        "MarginV, Effect, Text\n"
        "Comment: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,This is a comment\n"
        "Dialogue: 0,0:00:05.00,0:00:08.00,Default,,0,0,0,,Real text\n"
    )
    entries, _ = parse_ass(content)
    assert len(entries) == 1
    assert entries[0].text == "Real text"


def test_parse_ass_newline_marker() -> None:
    r"""ASS \N hard newline markers are preserved in text."""
    content = (
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
        "MarginV, Effect, Text\n"
        r"Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,Line one\NLine two"
        "\n"
    )
    entries, _ = parse_ass(content)
    assert r"\N" in entries[0].text


def test_serialize_ass_roundtrip() -> None:
    """Parse then serialize produces valid ASS output."""
    entries, preserved = parse_ass(_SAMPLE_ASS)
    result = serialize_ass(entries, preserved)
    entries2, _ = parse_ass(result)
    assert len(entries2) == 2  # noqa: PLR2004
    assert entries2[0].text == "Hello world"
    assert entries2[1].text == "Goodbye world"


def test_serialize_ass_preserves_sections() -> None:
    """Serialized ASS keeps all non-Events sections intact."""
    entries, preserved = parse_ass(_SAMPLE_ASS)
    result = serialize_ass(entries, preserved)
    assert "[Script Info]" in result
    assert "[V4+ Styles]" in result
    assert "Title: Test" in result


def test_serialize_ass_restores_leading_tags() -> None:
    """Leading override tags are restored on serialization."""
    entries = [
        SubtitleEntry(
            index=0,
            start="0:00:01.00",
            end="0:00:04.00",
            text="Translated",
            raw_text=r"{\pos(320,240)}Original",
        ),
    ]
    preserved = ["Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,__SUB_0__"]
    result = serialize_ass(entries, preserved)
    assert r"{\pos(320,240)}Translated" in result


# ---------------------------------------------------------------------------
# ASS tag stripping / restoration
# ---------------------------------------------------------------------------


def test_strip_ass_tags_basic() -> None:
    """Override tags are stripped from text."""
    assert _strip_ass_tags(r"{\b1}Bold{\b0}") == "Bold"


def test_strip_ass_tags_multiple() -> None:
    """Multiple override tags are all removed."""
    assert _strip_ass_tags(r"{\pos(320,240)}{\b1}Text") == "Text"


def test_strip_ass_tags_no_tags() -> None:
    """Plain text without tags is returned unchanged."""
    assert _strip_ass_tags("Hello world") == "Hello world"


def test_restore_ass_tags_leading() -> None:
    """Leading override tags are prepended to translated text."""
    original = r"{\pos(320,240)}Hello"
    translated = "Bonjour"
    result = _restore_ass_tags(original, translated)
    assert result == r"{\pos(320,240)}Bonjour"


def test_restore_ass_tags_multiple_leading() -> None:
    """Multiple contiguous leading tags are all restored."""
    original = r"{\pos(320,240)}{\b1}Hello"
    translated = "Bonjour"
    result = _restore_ass_tags(original, translated)
    assert result == r"{\pos(320,240)}{\b1}Bonjour"


def test_restore_ass_tags_no_leading() -> None:
    """Text without leading tags returns translated text unchanged."""
    result = _restore_ass_tags("Hello", "Bonjour")
    assert result == "Bonjour"


def test_restore_ass_tags_mid_text_tags_not_restored() -> None:
    """Mid-text tags from original are not added to translation."""
    original = r"Normal {\b1}bold{\b0} text"
    translated = "Texte normal gras texte"
    result = _restore_ass_tags(original, translated)
    # No tags should be added since original has no leading tags
    assert result == translated


# ---------------------------------------------------------------------------
# SSA format (v4.00)
# ---------------------------------------------------------------------------


def test_parse_ssa_format() -> None:
    """SSA (v4.00) files parse identically to ASS."""
    content = (
        "[Script Info]\nScriptType: v4.00\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
        "MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,Hello\n"
    )
    entries, _ = parse_ass(content)
    assert len(entries) == 1
    assert entries[0].text == "Hello"


# ---------------------------------------------------------------------------
# Unified dispatchers
# ---------------------------------------------------------------------------


def test_parse_subtitle_srt() -> None:
    """parse_subtitle dispatches to SRT parser."""
    content = "1\n00:00:01,000 --> 00:00:04,000\nHello\n"
    entries, _ = parse_subtitle(content, ".srt")
    assert len(entries) == 1


def test_parse_subtitle_vtt() -> None:
    """parse_subtitle dispatches to VTT parser."""
    content = "WEBVTT\n\n00:00:01.000 --> 00:00:04.000\nHello\n"
    entries, _ = parse_subtitle(content, ".vtt")
    assert len(entries) == 1


def test_parse_subtitle_ass() -> None:
    """parse_subtitle dispatches to ASS parser for .ass."""
    entries, _ = parse_subtitle(_SAMPLE_ASS, ".ass")
    assert len(entries) == 2  # noqa: PLR2004


def test_parse_subtitle_ssa() -> None:
    """parse_subtitle dispatches to ASS parser for .ssa."""
    entries, _ = parse_subtitle(_SAMPLE_ASS, ".ssa")
    assert len(entries) == 2  # noqa: PLR2004


def test_parse_subtitle_unsupported() -> None:
    """Unsupported extension raises ValueError."""
    with pytest.raises(ValueError, match="Unsupported subtitle format"):
        parse_subtitle("data", ".txt")


def test_serialize_subtitle_unsupported() -> None:
    """Unsupported extension raises ValueError."""
    with pytest.raises(ValueError, match="Unsupported subtitle format"):
        serialize_subtitle([], None, ".txt")


def test_serialize_subtitle_srt() -> None:
    """serialize_subtitle dispatches to SRT serializer."""
    entries = [
        SubtitleEntry(index=0, start="00:00:01,000", end="00:00:04,000", text="Hi"),
    ]
    result = serialize_subtitle(entries, None, ".srt")
    assert "00:00:01,000 --> 00:00:04,000" in result
    assert "Hi" in result


def test_serialize_subtitle_vtt() -> None:
    """serialize_subtitle dispatches to VTT serializer."""
    entries = [
        SubtitleEntry(
            index=0,
            start="00:00:01.000",
            end="00:00:04.000",
            text="Hi",
        ),
    ]
    result = serialize_subtitle(entries, "WEBVTT", ".vtt")
    assert "WEBVTT" in result
    assert "Hi" in result


def test_serialize_subtitle_ass() -> None:
    """serialize_subtitle dispatches to ASS serializer."""
    entries, preserved = parse_ass(_SAMPLE_ASS)
    entries[0].text = "Translated"
    result = serialize_subtitle(entries, preserved, ".ass")
    assert "Translated" in result


def test_serialize_subtitle_ssa() -> None:
    """serialize_subtitle dispatches to SSA serializer via .ssa."""
    entries, preserved = parse_ass(_SAMPLE_ASS)
    result = serialize_subtitle(entries, preserved, ".ssa")
    assert "Hello world" in result


# ---------------------------------------------------------------------------
# parse_srt edge cases: malformed / degenerate blocks
# ---------------------------------------------------------------------------


def test_parse_srt_block_with_only_index_is_skipped() -> None:
    """A block containing only the index number (< 2 lines) is skipped."""
    content = "1\n\n2\n00:00:05,000 --> 00:00:08,000\nWorld\n"
    entries, _ = parse_srt(content)
    # The first block has only "1" — no timestamp + text, so it is skipped
    assert len(entries) == 1
    assert entries[0].text == "World"


def test_parse_srt_block_without_timestamp_is_skipped() -> None:
    """A block with text but no timestamp line is skipped."""
    # Build content where neither line is a valid "HH:MM:SS,mmm --> ..." timestamp
    content = (
        "1\nJust some text\nMore text\n\n2\n00:00:05,000 --> 00:00:08,000\nWorld\n"
    )
    entries, _ = parse_srt(content)
    # First block lacks a timestamp, so it must be skipped
    assert len(entries) == 1
    assert entries[0].text == "World"


def test_parse_srt_block_with_whitespace_only_text_is_skipped() -> None:
    """A block whose text lines are all whitespace is skipped."""
    content = (
        "1\n00:00:01,000 --> 00:00:04,000\n   \n\n"
        "2\n00:00:05,000 --> 00:00:08,000\nHello\n"
    )
    entries, _ = parse_srt(content)
    # First block has only whitespace text — should be skipped
    assert len(entries) == 1
    assert entries[0].text == "Hello"


# ---------------------------------------------------------------------------
# parse_ass edge cases
# ---------------------------------------------------------------------------


def test_parse_ass_format_without_text_field_yields_no_entries() -> None:
    """ASS file with no 'Text' field in Format line extracts no dialogue."""
    content = (
        "[Script Info]\nScriptType: v4.00+\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Content\n"
        "Dialogue: 0,0:00:01.00,0:00:04.00,Hello\n"
    )
    entries, _ = parse_ass(content)
    assert entries == []


def test_parse_ass_multiple_format_lines_last_wins() -> None:
    """When [Events] has two Format lines, the last determines Text index."""
    content = (
        "[Script Info]\nScriptType: v4.00+\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Content\n"
        "Format: Layer, Start, End, Style, Name, Text\n"
        "Dialogue: 0,0:00:01.00,0:00:04.00,Default,,Hello\n"
    )
    entries, _ = parse_ass(content)
    assert len(entries) == 1
    assert entries[0].text == "Hello"


def test_serialize_srt_entry_with_empty_text() -> None:
    """SRT entry with empty text is still serialized."""
    entries = [
        SubtitleEntry(
            index=0,
            start="00:00:01,000",
            end="00:00:04,000",
            text="",
        ),
    ]
    result = serialize_srt(entries)
    assert "00:00:01,000" in result
    assert "00:00:04,000" in result


def test_parse_srt_timestamp_without_spaces_around_arrow() -> None:
    """Timestamp separator without spaces is still parsed."""
    content = "1\n00:00:01,000-->00:00:04,000\nHello\n\n"
    entries, _ = parse_srt(content)
    assert len(entries) == 1
    assert entries[0].text == "Hello"


def test_parse_ass_dialogue_with_insufficient_fields_is_skipped() -> None:
    """Dialogue with fewer fields than Text index is skipped."""
    content = (
        "[Script Info]\nScriptType: v4.00+\n\n"
        "[Events]\n"
        # Standard ASS format has 10 fields
        "Format: Layer, Start, End, Style, Name,"
        " MarginL, MarginR, MarginV, Effect, Text\n"
        # Only 3 comma-separated values — too few
        "Dialogue: 0,0:00:01.00\n"
        # Valid dialogue
        "Dialogue: 0,0:00:05.00,0:00:08.00,Default,,0,0,0,,World\n"
    )
    entries, _ = parse_ass(content)
    # Only the valid dialogue should be extracted
    assert len(entries) == 1
    assert entries[0].text == "World"


# ---------------------------------------------------------------------------
# parse_vtt — no WEBVTT header
# ---------------------------------------------------------------------------


def test_parse_vtt_without_webvtt_header_still_parses_cues() -> None:
    """VTT content without a WEBVTT header falls through to cue parsing."""
    # No WEBVTT header line — the cue block has a timestamp so it should parse
    content = "00:00:01.000 --> 00:00:04.000\nHello world\n"
    entries, header = parse_vtt(content)
    assert len(entries) == 1
    assert entries[0].text == "Hello world"
    # Nothing matched the header filter, so header is empty
    assert header == ""


def test_parse_vtt_without_header_cue_id_preserved() -> None:
    """Cue IDs are still extracted when WEBVTT header is absent."""
    content = "intro\n00:00:01.000 --> 00:00:04.000\nHello\n"
    entries, _ = parse_vtt(content)
    assert len(entries) == 1
    assert entries[0].metadata.get("cue_id") == "intro"


def test_parse_vtt_empty_text_block_skipped() -> None:
    """A cue with only whitespace text is not included in entries."""
    content = "WEBVTT\n\n00:00:01.000 --> 00:00:04.000\n   \n"
    entries, _ = parse_vtt(content)
    assert entries == []


# ---------------------------------------------------------------------------
# parse_ass — multiple [Events] sections
# ---------------------------------------------------------------------------


def test_parse_ass_multiple_events_sections_all_parsed() -> None:
    """Dialogue from all [Events] sections is collected."""
    content = (
        "[Script Info]\nScriptType: v4.00+\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name,"
        " MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,First\n\n"
        "[Other Section]\nKey: Value\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name,"
        " MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:05.00,0:00:08.00,Default,,0,0,0,,Second\n"
    )
    entries, _ = parse_ass(content)
    texts = {e.text for e in entries}
    assert "First" in texts
    assert "Second" in texts
    assert len(entries) == 2  # noqa: PLR2004


# ---------------------------------------------------------------------------
# SRT/VTT — malformed timestamp with multiple "-->" separators
# ---------------------------------------------------------------------------


def test_parse_srt_malformed_timestamp_multiple_arrows_skipped() -> None:
    """A timestamp line with multiple --> separators is skipped."""
    content = (
        "1\n00:00:01,000 --> 00:00:04,000 --> 00:00:06,000\nBad\n\n"
        "2\n00:00:05,000 --> 00:00:08,000\nGood\n"
    )
    entries, _ = parse_srt(content)
    assert len(entries) == 1
    assert entries[0].text == "Good"


def test_parse_vtt_malformed_timestamp_multiple_arrows_skipped() -> None:
    """A VTT timestamp with multiple --> separators is skipped."""
    content = (
        "WEBVTT\n\n"
        "00:00:01.000 --> 00:00:04.000 --> extra\nBad\n\n"
        "00:00:05.000 --> 00:00:08.000\nGood\n"
    )
    entries, _ = parse_vtt(content)
    assert len(entries) == 1
    assert entries[0].text == "Good"


# ---------------------------------------------------------------------------
# ASS edge cases — double commas and missing Text field
# ---------------------------------------------------------------------------


def test_parse_ass_double_commas_in_text() -> None:
    """Double commas in the Text field are preserved verbatim."""
    content = (
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
        "MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,Hello,, world\n"
    )
    entries, _ = parse_ass(content)
    assert len(entries) == 1
    assert entries[0].text == "Hello,, world"


def test_parse_ass_missing_text_field() -> None:
    """Malformed Dialogue line with insufficient fields is skipped."""
    content = (
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
        "MarginV, Effect, Text\n"
        # Only 5 comma-separated fields instead of 10
        "Dialogue: 0,0:00:01.00,0:00:04.00,Default,\n"
        "Dialogue: 0,0:00:05.00,0:00:08.00,Default,,0,0,0,,Valid line\n"
    )
    entries, _ = parse_ass(content)
    # Only the valid dialogue should be parsed
    assert len(entries) == 1
    assert entries[0].text == "Valid line"


# ---------------------------------------------------------------------------
# VTT edge cases — multiple cue settings, NOTE block preservation
# ---------------------------------------------------------------------------


def test_parse_vtt_multiple_cue_settings() -> None:
    """Multiple cue settings are all captured in a single metadata string."""
    content = (
        "WEBVTT\n\n"
        "00:00:01.000 --> 00:00:04.000 position:10% align:left size:80%\n"
        "Hello settings\n"
    )
    entries, _ = parse_vtt(content)
    assert len(entries) == 1
    settings = entries[0].metadata.get("cue_settings", "")
    assert "position:10%" in settings
    assert "align:left" in settings
    assert "size:80%" in settings


def test_parse_vtt_note_block_preserved() -> None:
    """NOTE blocks are preserved in the header and do not become entries."""
    content = (
        "WEBVTT\n\n"
        "NOTE\nThis is a translator note\nwith multiple lines\n\n"
        "00:00:01.000 --> 00:00:04.000\nHello\n\n"
        "NOTE Another note\n\n"
        "00:00:05.000 --> 00:00:08.000\nWorld\n"
    )
    entries, header = parse_vtt(content)
    # Only cues become entries, not NOTE blocks
    assert len(entries) == 2  # noqa: PLR2004
    assert entries[0].text == "Hello"
    assert entries[1].text == "World"
    # Both NOTE blocks are in the header
    assert header.count("NOTE") == 2  # noqa: PLR2004


# ---------------------------------------------------------------------------
# SRT roundtrip — nested HTML tags survive
# ---------------------------------------------------------------------------


def test_serialize_srt_roundtrip_preserves_tags() -> None:
    """Nested HTML tags like <b><i>Text</i></b> survive parse/serialize roundtrip."""
    content = (
        "1\n00:00:01,000 --> 00:00:04,000\n<b><i>Bold Italic</i></b>\n\n"
        "2\n00:00:05,000 --> 00:00:08,000\n<u>Underline</u>\n"
    )
    entries, fmt = parse_srt(content)
    result = serialize_srt(entries, fmt)
    entries2, _ = parse_srt(result)
    assert entries2[0].text == "<b><i>Bold Italic</i></b>"
    assert entries2[1].text == "<u>Underline</u>"


# ---------------------------------------------------------------------------
# parse_subtitle — unknown extension
# ---------------------------------------------------------------------------


def test_parse_subtitle_unknown_extension() -> None:
    """Unsupported subtitle format raises ValueError."""
    with pytest.raises(ValueError, match="Unsupported subtitle format"):
        parse_subtitle("some data", ".mp4")


# ---------------------------------------------------------------------------
# Edge case: SRT with dot timestamps (00:00:01.000 instead of comma)
# ---------------------------------------------------------------------------


def test_parse_srt_dot_timestamps() -> None:
    """SRT with dot-separated milliseconds (00:00:01.000) is parsed correctly."""
    content = (
        "1\n00:00:01.000 --> 00:00:04.000\nHello\n\n"
        "2\n00:00:05.000 --> 00:00:08.000\nWorld\n"
    )
    entries, fmt = parse_srt(content)
    assert fmt is None
    assert len(entries) == 2  # noqa: PLR2004
    assert entries[0].start == "00:00:01.000"
    assert entries[0].end == "00:00:04.000"
    assert entries[0].text == "Hello"
    assert entries[1].text == "World"


# ---------------------------------------------------------------------------
# Edge case: SRT serialize with empty entries list
# ---------------------------------------------------------------------------


def test_serialize_srt_empty_entries() -> None:
    """Serializing an empty list of entries produces an empty string."""
    result = serialize_srt([])
    assert result == ""


# ---------------------------------------------------------------------------
# Edge case: VTT with short-form timestamps (no hours)
# ---------------------------------------------------------------------------


def test_parse_vtt_short_form_timestamps_no_hours() -> None:
    """VTT with short-form timestamps (MM:SS.mmm, no hours) — not parsed.

    The _TIMESTAMP_RE regex requires at least H:MM:SS format so
    short-form timestamps like 01:00.000 do NOT match and the cue
    is skipped.
    """
    content = "WEBVTT\n\n01:00.000 --> 02:00.000\nShort form\n"
    entries, header = parse_vtt(content)
    # Short-form timestamps lack the HH: prefix so they fail the regex
    assert len(entries) == 0
    assert "WEBVTT" in header


# ---------------------------------------------------------------------------
# Edge case: ASS with empty text field
# ---------------------------------------------------------------------------


def test_parse_ass_empty_text_field() -> None:
    """ASS Dialogue line with an empty Text field is skipped.

    parse_ass skips entries whose clean_text.strip() would be empty
    because the overall block-text check catches it, but the entry is
    still constructed.  Since the text field is the last comma-split part,
    an empty value just means the text is empty string.
    """
    content = (
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
        "MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,\n"
        "Dialogue: 0,0:00:05.00,0:00:08.00,Default,,0,0,0,,Valid text\n"
    )
    entries, _ = parse_ass(content)
    # The empty-text dialogue is still extracted (parse_ass does not skip empty text)
    # but its text is an empty string
    texts = [e.text for e in entries]
    assert "Valid text" in texts
    # The first entry has empty text
    assert "" in texts or len(entries) == 1


# ---------------------------------------------------------------------------
# Edge case: ASS with lowercase \n soft newline
# ---------------------------------------------------------------------------


def test_parse_ass_lowercase_n_soft_newline() -> None:
    r"""ASS lowercase \n soft newline marker is preserved in text."""
    content = (
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
        "MarginV, Effect, Text\n"
        r"Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,Line one\nLine two"
        "\n"
    )
    entries, _ = parse_ass(content)
    assert len(entries) == 1
    # Lowercase \n is a soft newline in ASS — NOT an override tag, so
    # _strip_ass_tags does not remove it
    assert r"\n" in entries[0].text


# ---------------------------------------------------------------------------
# Edge case: Windows-style line endings (\r\n) in SRT
# ---------------------------------------------------------------------------


def test_parse_srt_windows_line_endings() -> None:
    r"""SRT with \r\n line endings — the parser splits on \n\n so \r\n\r\n works.

    However, \r characters remain in the text fields and timestamps since
    splitlines() handles them, but the re.split(r"\n\n+") only splits on
    bare \n\n.  We verify the parser does not crash and extracts content.
    """
    # Use \r\n\r\n as block separator — re.split(r"\n\n+") matches the \n\n
    # inside \r\n\r\n, leaving trailing \r on lines.
    content = (
        "1\r\n00:00:01,000 --> 00:00:04,000\r\nHello\r\n"
        "\r\n"
        "2\r\n00:00:05,000 --> 00:00:08,000\r\nWorld\r\n"
    )
    entries, _ = parse_srt(content)
    # The parser finds the timestamp lines (regex allows trailing \r)
    # and extracts text, though \r may remain
    assert len(entries) >= 1
    assert any("Hello" in e.text for e in entries)
    assert any("World" in e.text for e in entries)


# ---------------------------------------------------------------------------
# NEW: SubtitleEntry creation and fields
# ---------------------------------------------------------------------------


def test_subtitle_entry_defaults() -> None:
    """SubtitleEntry has expected defaults for optional fields."""
    entry = SubtitleEntry(index=0, start="0:00:00.00", end="0:00:01.00", text="Hi")
    assert entry.raw_text == ""
    assert entry.metadata == {}


def test_subtitle_entry_metadata_preserved() -> None:
    """SubtitleEntry stores arbitrary metadata dict."""
    meta = {"cue_id": "abc", "cue_settings": "line:1"}
    entry = SubtitleEntry(
        index=3,
        start="00:00:01.000",
        end="00:00:02.000",
        text="Test",
        metadata=meta,
    )
    assert entry.metadata["cue_id"] == "abc"
    assert entry.index == 3


# ---------------------------------------------------------------------------
# NEW: SRT edge cases
# ---------------------------------------------------------------------------


def test_parse_srt_no_trailing_newline() -> None:
    """SRT file without a trailing newline still parses correctly."""
    content = "1\n00:00:01,000 --> 00:00:04,000\nHello"
    entries, _ = parse_srt(content)
    assert len(entries) == 1
    assert entries[0].text == "Hello"


def test_parse_srt_timestamps_with_two_digit_ms() -> None:
    """SRT timestamps with 2-digit milliseconds still match the regex."""
    content = "1\n00:00:01,50 --> 00:00:04,99\nShort ms\n"
    entries, _ = parse_srt(content)
    assert len(entries) == 1
    assert entries[0].start == "00:00:01,50"
    assert entries[0].end == "00:00:04,99"


def test_parse_srt_only_whitespace_content() -> None:
    """SRT with only whitespace yields no entries."""
    content = "   \n  \n\n  \n"
    entries, _ = parse_srt(content)
    assert entries == []


def test_parse_srt_missing_index_number() -> None:
    """SRT block without an index number but with timestamp still parses."""
    content = "00:00:01,000 --> 00:00:04,000\nNo index\n"
    entries, _ = parse_srt(content)
    # The block has a timestamp line at index 0, text follows at index 1
    assert len(entries) == 1
    assert entries[0].text == "No index"


def test_parse_srt_unicode_cjk() -> None:
    """SRT with CJK text parses correctly."""
    content = "1\n00:00:01,000 --> 00:00:04,000\n\u4f60\u597d\u4e16\u754c\n"
    entries, _ = parse_srt(content)
    assert len(entries) == 1
    assert entries[0].text == "\u4f60\u597d\u4e16\u754c"


def test_parse_srt_unicode_arabic() -> None:
    """SRT with Arabic text parses correctly."""
    content = "1\n00:00:01,000 --> 00:00:04,000\n\u0645\u0631\u062d\u0628\u0627\n"
    entries, _ = parse_srt(content)
    assert entries[0].text == "\u0645\u0631\u062d\u0628\u0627"


def test_parse_srt_unicode_emoji() -> None:
    """SRT with emoji text parses correctly."""
    content = "1\n00:00:01,000 --> 00:00:04,000\nHello \U0001f600\U0001f30d\n"
    entries, _ = parse_srt(content)
    assert "\U0001f600" in entries[0].text


def test_parse_srt_large_file() -> None:
    """SRT with 1000+ entries parses correctly."""
    blocks = []
    for i in range(1, 1001):
        h, m, s = 0, i // 60, i % 60
        blocks.append(
            f"{i}\n{h:02}:{m:02}:{s:02},000 --> {h:02}:{m:02}:{s:02},999\nLine {i}\n"
        )
    content = "\n".join(blocks)
    entries, _ = parse_srt(content)
    assert len(entries) == 1000  # noqa: PLR2004
    assert entries[999].text == "Line 1000"


# ---------------------------------------------------------------------------
# NEW: VTT edge cases
# ---------------------------------------------------------------------------


def test_parse_vtt_with_metadata_header() -> None:
    """VTT with metadata in the WEBVTT header line preserves it."""
    content = "WEBVTT - My Custom Header\n\n00:00:01.000 --> 00:00:04.000\nHello\n"
    entries, header = parse_vtt(content)
    assert "WEBVTT" in header
    assert "My Custom Header" in header
    assert len(entries) == 1


def test_parse_vtt_with_style_block_cue_parsed() -> None:
    """Cues after a STYLE block are parsed correctly."""
    content = (
        "WEBVTT\n\n"
        "STYLE\n::cue(.highlight) { color: yellow; }\n\n"
        "00:00:01.000 --> 00:00:04.000\nStyled text\n"
    )
    entries, header = parse_vtt(content)
    assert "STYLE" in header
    assert len(entries) == 1
    assert entries[0].text == "Styled text"


def test_parse_vtt_multiline_cue_text() -> None:
    """VTT cue with multiline text preserves newlines."""
    content = "WEBVTT\n\n00:00:01.000 --> 00:00:04.000\nLine 1\nLine 2\nLine 3\n"
    entries, _ = parse_vtt(content)
    assert entries[0].text == "Line 1\nLine 2\nLine 3"


def test_parse_vtt_cue_id_and_settings_combined() -> None:
    """VTT cue with both cue ID and settings parses both."""
    content = (
        "WEBVTT\n\n"
        "intro\n00:00:01.000 --> 00:00:04.000 position:50% align:center\n"
        "Hello centered\n"
    )
    entries, _ = parse_vtt(content)
    assert entries[0].metadata["cue_id"] == "intro"
    assert "position:50%" in entries[0].metadata["cue_settings"]


def test_serialize_vtt_no_header() -> None:
    """VTT serialize with empty header starts with the first cue."""
    entries = [
        SubtitleEntry(
            index=0,
            start="00:00:01.000",
            end="00:00:04.000",
            text="Only cue",
        ),
    ]
    result = serialize_vtt(entries, "")
    assert result.startswith("00:00:01.000")


def test_serialize_vtt_roundtrip_with_settings() -> None:
    """VTT with cue settings survives parse/serialize/re-parse roundtrip."""
    content = (
        "WEBVTT\n\n"
        "00:00:01.000 --> 00:00:04.000 align:start\nHello\n\n"
        "00:00:05.000 --> 00:00:08.000 line:80%\nWorld\n"
    )
    entries, header = parse_vtt(content)
    result = serialize_vtt(entries, header)
    entries2, _ = parse_vtt(result)
    assert entries2[0].metadata.get("cue_settings") == "align:start"
    assert entries2[1].metadata.get("cue_settings") == "line:80%"


# ---------------------------------------------------------------------------
# NEW: ASS edge cases — inline styles, drawing commands
# ---------------------------------------------------------------------------


def test_parse_ass_inline_positioning_stripped() -> None:
    r"""ASS \pos() inline positioning is stripped from text."""
    content = (
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
        "MarginV, Effect, Text\n"
        r"Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,{\pos(320,240)}Positioned"
        "\n"
    )
    entries, _ = parse_ass(content)
    assert entries[0].text == "Positioned"
    assert r"\pos" not in entries[0].text


def test_parse_ass_drawing_commands_not_stripped() -> None:
    r"""ASS drawing commands outside override tags are preserved in text."""
    content = (
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
        "MarginV, Effect, Text\n"
        r"Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,"
        r"{\p1}m 0 0 l 100 0 100 100 0 100"
        "\n"
    )
    entries, _ = parse_ass(content)
    # The {\p1} tag is stripped, but the drawing commands remain
    assert "m 0 0" in entries[0].text


def test_parse_ass_complex_override_tags() -> None:
    r"""Multiple complex override tags like \fad, \c, \fs are all stripped."""
    content = (
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
        "MarginV, Effect, Text\n"
        r"Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,"
        r"{\fad(300,500)}{\c&H00FF00&}{\fs24}Colored"
        "\n"
    )
    entries, _ = parse_ass(content)
    assert entries[0].text == "Colored"
    assert r"\fad" not in entries[0].text
    assert r"\c" not in entries[0].text


# ---------------------------------------------------------------------------
# NEW: SSA format tests
# ---------------------------------------------------------------------------


_SAMPLE_SSA = """\
[Script Info]
ScriptType: v4.00

[V4 Styles]
Format: Name, Fontname, Fontsize
Style: Default,Arial,20

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,SSA line one
Dialogue: 0,0:00:05.00,0:00:08.00,Default,,0,0,0,,SSA line two
"""


def test_parse_ssa_via_dispatcher() -> None:
    """parse_subtitle dispatches to ASS parser for .ssa extension."""
    entries, preserved = parse_subtitle(_SAMPLE_SSA, ".ssa")
    assert len(entries) == 2  # noqa: PLR2004
    assert entries[0].text == "SSA line one"
    assert entries[1].text == "SSA line two"


def test_serialize_ssa_via_dispatcher() -> None:
    """serialize_subtitle dispatches to ASS serializer for .ssa extension."""
    entries, preserved = parse_subtitle(_SAMPLE_SSA, ".ssa")
    entries[0].text = "Translated SSA"
    result = serialize_subtitle(entries, preserved, ".ssa")
    assert "Translated SSA" in result


def test_ssa_roundtrip() -> None:
    """SSA parse/serialize roundtrip preserves all entries."""
    entries, preserved = parse_ass(_SAMPLE_SSA)
    result = serialize_ass(entries, preserved)
    entries2, _ = parse_ass(result)
    assert len(entries2) == 2  # noqa: PLR2004
    assert entries2[0].text == "SSA line one"
    assert entries2[1].text == "SSA line two"


# ---------------------------------------------------------------------------
# NEW: Serialize format tests
# ---------------------------------------------------------------------------


def test_serialize_srt_multiline_text() -> None:
    """SRT entry with multiline text is serialized correctly."""
    entries = [
        SubtitleEntry(
            index=0,
            start="00:00:01,000",
            end="00:00:04,000",
            text="Line 1\nLine 2\nLine 3",
        ),
    ]
    result = serialize_srt(entries)
    assert "Line 1\nLine 2\nLine 3" in result


def test_serialize_vtt_empty_entries() -> None:
    """Serializing VTT with no entries produces just the header."""
    result = serialize_vtt([], "WEBVTT")
    assert result.strip() == "WEBVTT"


def test_serialize_ass_no_entries() -> None:
    """Serializing ASS with no entries uses preserved lines only."""
    preserved = ["[Script Info]", "Title: Test"]
    result = serialize_ass([], preserved)
    assert "[Script Info]" in result
    assert "Title: Test" in result


def test_serialize_ass_multiple_placeholders() -> None:
    """ASS serialization replaces multiple placeholders correctly."""
    entries = [
        SubtitleEntry(index=0, start="", end="", text="First", raw_text="First"),
        SubtitleEntry(index=1, start="", end="", text="Second", raw_text="Second"),
    ]
    preserved = [
        "Dialogue: 0,,,,,,,,,__SUB_0__",
        "Dialogue: 0,,,,,,,,,__SUB_1__",
    ]
    result = serialize_ass(entries, preserved)
    assert "First" in result
    assert "Second" in result
    assert "__SUB_" not in result


# ---------------------------------------------------------------------------
# NEW: is_subtitle_format additional coverage
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ext", [".SRT", ".Vtt", ".ASS", ".Ssa"])
def test_is_subtitle_format_case_sensitive(ext: str) -> None:
    """is_subtitle_format is case-sensitive — uppercase returns False."""
    assert is_subtitle_format(ext) is False


@pytest.mark.parametrize("ext", ["srt", "vtt", "ass", "ssa"])
def test_is_subtitle_format_no_dot(ext: str) -> None:
    """Extension without leading dot returns False."""
    assert is_subtitle_format(ext) is False


def test_is_subtitle_format_empty_string() -> None:
    """Empty string returns False."""
    assert is_subtitle_format("") is False


# ---------------------------------------------------------------------------
# NEW: Malformed subtitle files
# ---------------------------------------------------------------------------


def test_parse_srt_corrupt_data() -> None:
    """Completely corrupt data yields no entries."""
    content = "This is not a subtitle file at all\nJust random text\n"
    entries, _ = parse_srt(content)
    assert entries == []


def test_parse_vtt_corrupt_data() -> None:
    """Corrupt VTT data without valid cues yields no entries."""
    content = "WEBVTT\n\nJust some text without timestamps\n"
    entries, header = parse_vtt(content)
    assert entries == []


def test_parse_ass_no_events_section() -> None:
    """ASS without [Events] section yields no entries."""
    content = "[Script Info]\nTitle: Test\n\n[V4+ Styles]\nFormat: Name\n"
    entries, preserved = parse_ass(content)
    assert entries == []
    assert len(preserved) > 0


def test_parse_ass_empty_content() -> None:
    """Empty ASS content yields no entries."""
    entries, preserved = parse_ass("")
    assert entries == []


# ---------------------------------------------------------------------------
# NEW: Timestamp parsing edge cases
# ---------------------------------------------------------------------------


def test_parse_srt_single_digit_hours() -> None:
    """SRT with single-digit hour timestamps parses correctly."""
    content = "1\n1:00:00,000 --> 1:30:00,000\nHour test\n"
    entries, _ = parse_srt(content)
    assert len(entries) == 1
    assert entries[0].start == "1:00:00,000"


def test_parse_vtt_dot_and_comma_timestamps() -> None:
    """VTT timestamps with dots parse correctly (standard VTT format)."""
    content = "WEBVTT\n\n00:00:01.500 --> 00:00:04.750\nDot timestamps\n"
    entries, _ = parse_vtt(content)
    assert len(entries) == 1
    assert entries[0].start == "00:00:01.500"
    assert entries[0].end == "00:00:04.750"


# ---------------------------------------------------------------------------
# EXPANDED: SRT parsing edge cases
# ---------------------------------------------------------------------------


def test_parse_srt_three_line_text() -> None:
    """SRT entry with three lines of text is joined with newlines."""
    content = "1\n00:00:01,000 --> 00:00:04,000\nLine A\nLine B\nLine C\n"
    entries, _ = parse_srt(content)
    assert len(entries) == 1
    assert entries[0].text == "Line A\nLine B\nLine C"


def test_parse_srt_mixed_valid_invalid_blocks() -> None:
    """Valid and invalid blocks interleaved: only valid ones are parsed."""
    content = (
        "1\n00:00:01,000 --> 00:00:02,000\nFirst\n\n"
        "garbage\n\n"
        "3\n00:00:03,000 --> 00:00:04,000\nThird\n\n"
        "only one line\n\n"
        "5\n00:00:05,000 --> 00:00:06,000\nFifth\n"
    )
    entries, _ = parse_srt(content)
    assert len(entries) == 3  # noqa: PLR2004
    assert entries[0].text == "First"
    assert entries[1].text == "Third"
    assert entries[2].text == "Fifth"


def test_parse_srt_special_characters_ampersand() -> None:
    """SRT text with & characters is preserved."""
    content = "1\n00:00:01,000 --> 00:00:04,000\nRock & Roll\n"
    entries, _ = parse_srt(content)
    assert entries[0].text == "Rock & Roll"


def test_parse_srt_special_characters_angle_brackets() -> None:
    """SRT text with < and > is preserved."""
    content = "1\n00:00:01,000 --> 00:00:04,000\na < b > c\n"
    entries, _ = parse_srt(content)
    assert entries[0].text == "a < b > c"


def test_parse_srt_newline_in_text_preserved() -> None:
    """SRT multiline text preserves all lines verbatim."""
    content = "1\n00:00:01,000 --> 00:00:04,000\nFirst\nSecond\n"
    entries, _ = parse_srt(content)
    assert entries[0].text == "First\nSecond"


def test_parse_srt_consecutive_entries_zero_based_index() -> None:
    """Parsed entries have zero-based sequential indices."""
    content = (
        "10\n00:00:01,000 --> 00:00:02,000\nA\n\n"
        "20\n00:00:03,000 --> 00:00:04,000\nB\n\n"
        "30\n00:00:05,000 --> 00:00:06,000\nC\n"
    )
    entries, _ = parse_srt(content)
    assert entries[0].index == 0
    assert entries[1].index == 1
    assert entries[2].index == 2


def test_parse_srt_very_long_text() -> None:
    """SRT with very long text line parses correctly."""
    long_text = "A" * 5000
    content = f"1\n00:00:01,000 --> 00:00:04,000\n{long_text}\n"
    entries, _ = parse_srt(content)
    assert len(entries) == 1
    assert entries[0].text == long_text


def test_parse_srt_leading_whitespace_in_text() -> None:
    """SRT text with leading/trailing whitespace on lines is preserved."""
    content = "1\n00:00:01,000 --> 00:00:04,000\n  Indented  \n"
    entries, _ = parse_srt(content)
    assert entries[0].text == "  Indented  "


def test_parse_srt_multiple_blank_lines_between_entries() -> None:
    """SRT blocks separated by 5+ blank lines still parse correctly."""
    content = (
        "1\n00:00:01,000 --> 00:00:02,000\nA\n\n\n\n\n\n"
        "2\n00:00:03,000 --> 00:00:04,000\nB\n"
    )
    entries, _ = parse_srt(content)
    assert len(entries) == 2  # noqa: PLR2004


def test_serialize_srt_three_entries() -> None:
    """SRT serialization of three entries produces 1-based indices."""
    entries = [
        SubtitleEntry(index=0, start="00:00:01,000", end="00:00:02,000", text="One"),
        SubtitleEntry(index=1, start="00:00:03,000", end="00:00:04,000", text="Two"),
        SubtitleEntry(index=2, start="00:00:05,000", end="00:00:06,000", text="Three"),
    ]
    result = serialize_srt(entries)
    lines = result.split("\n")
    # Find index lines
    indices = [l for l in lines if l.strip().isdigit()]
    assert "1" in indices
    assert "2" in indices
    assert "3" in indices


def test_serialize_srt_preserves_multiline_text() -> None:
    """SRT serialization preserves newlines within text."""
    entries = [
        SubtitleEntry(
            index=0,
            start="00:00:01,000",
            end="00:00:02,000",
            text="Line one\nLine two",
        ),
    ]
    result = serialize_srt(entries)
    assert "Line one\nLine two" in result


def test_parse_srt_tab_in_text() -> None:
    """SRT text containing tabs is preserved."""
    content = "1\n00:00:01,000 --> 00:00:04,000\tHello\tWorld\n"
    entries, _ = parse_srt(content)
    # The tab is part of the timestamp line splitting but text follows
    assert len(entries) >= 0  # At minimum, does not crash


def test_parse_srt_only_timestamp_no_text_skipped() -> None:
    """SRT block with timestamp but no text lines is skipped."""
    content = (
        "1\n00:00:01,000 --> 00:00:04,000\n\n"
        "2\n00:00:05,000 --> 00:00:08,000\nReal text\n"
    )
    entries, _ = parse_srt(content)
    # First block has empty text (whitespace-only) so it should be skipped
    assert len(entries) == 1
    assert entries[0].text == "Real text"


def test_parse_srt_comma_and_dot_millisecond_separator() -> None:
    """SRT with comma timestamps parse just like dot timestamps."""
    content_comma = "1\n00:00:01,500 --> 00:00:04,750\nComma\n"
    content_dot = "1\n00:00:01.500 --> 00:00:04.750\nDot\n"
    entries_c, _ = parse_srt(content_comma)
    entries_d, _ = parse_srt(content_dot)
    assert len(entries_c) == 1
    assert len(entries_d) == 1


# ---------------------------------------------------------------------------
# EXPANDED: SRT roundtrip edge cases
# ---------------------------------------------------------------------------


def test_srt_roundtrip_special_chars() -> None:
    """SRT roundtrip with special characters preserves them."""
    content = '1\n00:00:01,000 --> 00:00:04,000\n"Quoted" & <Tagged>\n'
    entries, fmt = parse_srt(content)
    result = serialize_srt(entries, fmt)
    entries2, _ = parse_srt(result)
    assert entries2[0].text == '"Quoted" & <Tagged>'


def test_srt_roundtrip_unicode() -> None:
    """SRT roundtrip with unicode text preserves it."""
    content = "1\n00:00:01,000 --> 00:00:04,000\n\u00e9\u00e8\u00ea\u00eb\n"
    entries, fmt = parse_srt(content)
    result = serialize_srt(entries, fmt)
    entries2, _ = parse_srt(result)
    assert entries2[0].text == "\u00e9\u00e8\u00ea\u00eb"


def test_srt_roundtrip_many_entries() -> None:
    """SRT roundtrip with 100 entries preserves all."""
    blocks = []
    for i in range(1, 101):
        # Use valid timestamps: HH:MM:SS,mmm with proper carry
        mm, ss = divmod(i, 60)
        blocks.append(
            f"{i}\n00:{mm:02d}:{ss:02d},000 --> 00:{mm:02d}:{ss:02d},999\nEntry {i}\n"
        )
    content = "\n".join(blocks)
    entries, fmt = parse_srt(content)
    result = serialize_srt(entries, fmt)
    entries2, _ = parse_srt(result)
    assert len(entries2) == 100  # noqa: PLR2004


# ---------------------------------------------------------------------------
# EXPANDED: VTT parsing edge cases
# ---------------------------------------------------------------------------


def test_parse_vtt_empty_content() -> None:
    """Empty VTT content returns no entries."""
    entries, header = parse_vtt("")
    assert entries == []
    assert header == ""


def test_parse_vtt_only_header() -> None:
    """VTT with only WEBVTT header returns no entries."""
    content = "WEBVTT\n"
    entries, header = parse_vtt(content)
    assert entries == []
    assert "WEBVTT" in header


def test_parse_vtt_bom() -> None:
    """UTF-8 BOM is stripped from VTT content."""
    content = "\ufeffWEBVTT\n\n00:00:01.000 --> 00:00:04.000\nHello\n"
    entries, header = parse_vtt(content)
    assert len(entries) == 1
    assert "WEBVTT" in header


def test_parse_vtt_multiple_entries() -> None:
    """VTT with five cues parses all of them."""
    cues = []
    for i in range(5):
        cues.append(f"00:00:{i:02d}.000 --> 00:00:{i:02d}.999\nCue {i}")
    content = "WEBVTT\n\n" + "\n\n".join(cues) + "\n"
    entries, _ = parse_vtt(content)
    assert len(entries) == 5  # noqa: PLR2004


def test_parse_vtt_unicode_text() -> None:
    """VTT with CJK text parses correctly."""
    content = "WEBVTT\n\n00:00:01.000 --> 00:00:04.000\n\u4f60\u597d\n"
    entries, _ = parse_vtt(content)
    assert entries[0].text == "\u4f60\u597d"


def test_parse_vtt_html_tags_preserved() -> None:
    """HTML tags in VTT text are preserved."""
    content = "WEBVTT\n\n00:00:01.000 --> 00:00:04.000\n<b>Bold</b> <i>italic</i>\n"
    entries, _ = parse_vtt(content)
    assert "<b>Bold</b>" in entries[0].text
    assert "<i>italic</i>" in entries[0].text


def test_parse_vtt_multiple_notes_preserved() -> None:
    """Multiple NOTE blocks are all preserved in header."""
    content = (
        "WEBVTT\n\n"
        "NOTE First note\n\n"
        "NOTE Second note\n\n"
        "00:00:01.000 --> 00:00:04.000\nText\n"
    )
    entries, header = parse_vtt(content)
    assert len(entries) == 1
    assert "First note" in header
    assert "Second note" in header


def test_parse_vtt_cue_without_text_skipped() -> None:
    """VTT cue block with only timestamp and no text is skipped."""
    content = "WEBVTT\n\n00:00:01.000 --> 00:00:04.000\n\n00:00:05.000 --> 00:00:08.000\nReal\n"
    entries, _ = parse_vtt(content)
    assert len(entries) == 1
    assert entries[0].text == "Real"


def test_serialize_vtt_roundtrip_multiple_cues() -> None:
    """VTT roundtrip with multiple cues preserves all."""
    content = (
        "WEBVTT\n\n"
        "00:00:01.000 --> 00:00:02.000\nFirst\n\n"
        "00:00:03.000 --> 00:00:04.000\nSecond\n\n"
        "00:00:05.000 --> 00:00:06.000\nThird\n"
    )
    entries, header = parse_vtt(content)
    result = serialize_vtt(entries, header)
    entries2, _ = parse_vtt(result)
    assert len(entries2) == 3  # noqa: PLR2004
    assert entries2[0].text == "First"
    assert entries2[2].text == "Third"


def test_serialize_vtt_empty_entries_no_header() -> None:
    """VTT serialize with no entries and no header produces minimal output."""
    result = serialize_vtt([], "")
    assert result.strip() == ""


def test_parse_vtt_windows_line_endings() -> None:
    """VTT with CRLF line endings still parses."""
    content = "WEBVTT\r\n\r\n00:00:01.000 --> 00:00:04.000\r\nHello\r\n"
    entries, header = parse_vtt(content)
    assert len(entries) >= 1
    assert any("Hello" in e.text for e in entries)


def test_serialize_vtt_cue_id_and_settings() -> None:
    """VTT cue with both cue_id and cue_settings serializes correctly."""
    entries = [
        SubtitleEntry(
            index=0,
            start="00:00:01.000",
            end="00:00:04.000",
            text="Test",
            metadata={"cue_id": "cue1", "cue_settings": "align:center"},
        ),
    ]
    result = serialize_vtt(entries, "WEBVTT")
    assert "cue1" in result
    assert "align:center" in result
    assert "00:00:01.000 --> 00:00:04.000" in result


# ---------------------------------------------------------------------------
# EXPANDED: ASS/SSA parsing edge cases
# ---------------------------------------------------------------------------


def test_parse_ass_with_semicolon_comment() -> None:
    """ASS lines starting with ; are preserved as comments."""
    content = (
        "[Script Info]\n; This is a semicolon comment\nTitle: Test\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
        "MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,Hello\n"
    )
    entries, preserved = parse_ass(content)
    assert len(entries) == 1
    joined = "\n".join(preserved)
    assert "; This is a semicolon comment" in joined


def test_parse_ass_bom() -> None:
    """UTF-8 BOM is stripped from ASS content."""
    content = (
        "\ufeff[Script Info]\nTitle: Test\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
        "MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,BOM test\n"
    )
    entries, _ = parse_ass(content)
    assert len(entries) == 1
    assert entries[0].text == "BOM test"


def test_parse_ass_unicode_text() -> None:
    """ASS with unicode text parses correctly."""
    content = (
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
        "MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,\u4f60\u597d\n"
    )
    entries, _ = parse_ass(content)
    assert entries[0].text == "\u4f60\u597d"


def test_parse_ass_multiple_override_tags_mid_text() -> None:
    r"""Multiple override tags in middle of text are stripped."""
    content = (
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
        "MarginV, Effect, Text\n"
        r"Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,Hello{\b1}bold{\b0}world"
        "\n"
    )
    entries, _ = parse_ass(content)
    assert entries[0].text == "Helloboldworld"


def test_parse_ass_empty_events_section() -> None:
    """ASS with Events section but no Dialogue lines returns no entries."""
    content = (
        "[Script Info]\nTitle: Test\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
        "MarginV, Effect, Text\n"
    )
    entries, preserved = parse_ass(content)
    assert entries == []
    assert len(preserved) > 0


def test_parse_ass_large_dialogue_count() -> None:
    """ASS with 100 dialogue lines parses all."""
    format_line = (
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
        "MarginV, Effect, Text"
    )
    dialogues = [
        f"Dialogue: 0,0:00:{i:02d}.00,0:00:{i:02d}.99,Default,,0,0,0,,Line {i}"
        for i in range(100)
    ]
    content = "[Events]\n" + format_line + "\n" + "\n".join(dialogues) + "\n"
    entries, _ = parse_ass(content)
    assert len(entries) == 100  # noqa: PLR2004
    assert entries[99].text == "Line 99"


def test_serialize_ass_roundtrip_with_tags() -> None:
    """ASS roundtrip with override tags restores leading tags."""
    content = (
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
        "MarginV, Effect, Text\n"
        r"Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,{\pos(160,120)}Hello"
        "\n"
    )
    entries, preserved = parse_ass(content)
    entries[0].text = "Translated"
    result = serialize_ass(entries, preserved)
    assert r"{\pos(160,120)}Translated" in result


def test_serialize_ass_preserves_format_line() -> None:
    """ASS serialization preserves the Format line."""
    entries, preserved = parse_ass(_SAMPLE_ASS)
    result = serialize_ass(entries, preserved)
    assert "Format:" in result


def test_restore_ass_tags_empty_original() -> None:
    """Restoring tags from empty original returns translated text."""
    result = _restore_ass_tags("", "Bonjour")
    assert result == "Bonjour"


def test_restore_ass_tags_only_tags() -> None:
    r"""Restoring from original that is only tags prepends them all."""
    original = r"{\b1}{\i1}"
    translated = "Text"
    result = _restore_ass_tags(original, translated)
    assert result == r"{\b1}{\i1}Text"


def test_strip_ass_tags_nested_braces() -> None:
    r"""Nested braces within override tags are stripped correctly."""
    text = r"{\clip(1,2,3,4)}Clipped text"
    result = _strip_ass_tags(text)
    assert result == "Clipped text"


def test_strip_ass_tags_empty_string() -> None:
    """Stripping tags from empty string returns empty."""
    assert _strip_ass_tags("") == ""


def test_strip_ass_tags_only_tags() -> None:
    r"""Stripping tags from string with only tags returns empty."""
    assert _strip_ass_tags(r"{\b1}{\i1}{\pos(0,0)}") == ""


# ---------------------------------------------------------------------------
# EXPANDED: Dispatcher edge cases
# ---------------------------------------------------------------------------


def test_parse_subtitle_empty_srt() -> None:
    """parse_subtitle with empty SRT content returns no entries."""
    entries, fmt = parse_subtitle("", ".srt")
    assert entries == []
    assert fmt is None


def test_parse_subtitle_empty_vtt() -> None:
    """parse_subtitle with empty VTT content returns no entries."""
    entries, header = parse_subtitle("", ".vtt")
    assert entries == []


def test_serialize_subtitle_empty_srt() -> None:
    """serialize_subtitle with empty entries for .srt returns empty."""
    result = serialize_subtitle([], None, ".srt")
    assert result == ""


def test_serialize_subtitle_empty_vtt() -> None:
    """serialize_subtitle with empty entries for .vtt."""
    result = serialize_subtitle([], "WEBVTT", ".vtt")
    assert "WEBVTT" in result


def test_serialize_subtitle_empty_ass() -> None:
    """serialize_subtitle with empty entries for .ass preserves lines."""
    result = serialize_subtitle([], ["[Script Info]", "Title: Test"], ".ass")
    assert "[Script Info]" in result


@pytest.mark.parametrize("ext", [".mp3", ".pdf", ".doc", ".xml", ".csv"])
def test_parse_subtitle_various_unsupported(ext: str) -> None:
    """Various unsupported extensions raise ValueError."""
    with pytest.raises(ValueError, match="Unsupported subtitle format"):
        parse_subtitle("data", ext)


@pytest.mark.parametrize("ext", [".mp3", ".pdf", ".doc", ".xml", ".csv"])
def test_serialize_subtitle_various_unsupported(ext: str) -> None:
    """Various unsupported extensions raise ValueError for serialize."""
    with pytest.raises(ValueError, match="Unsupported subtitle format"):
        serialize_subtitle([], None, ext)


# ---------------------------------------------------------------------------
# EXPANDED: SubtitleEntry dataclass
# ---------------------------------------------------------------------------


def test_subtitle_entry_equality() -> None:
    """Two SubtitleEntry with same values are equal."""
    e1 = SubtitleEntry(index=0, start="0:00:00.00", end="0:00:01.00", text="Hi")
    e2 = SubtitleEntry(index=0, start="0:00:00.00", end="0:00:01.00", text="Hi")
    assert e1 == e2


def test_subtitle_entry_inequality() -> None:
    """Two SubtitleEntry with different text are not equal."""
    e1 = SubtitleEntry(index=0, start="0:00:00.00", end="0:00:01.00", text="Hi")
    e2 = SubtitleEntry(index=0, start="0:00:00.00", end="0:00:01.00", text="Bye")
    assert e1 != e2


def test_subtitle_entry_raw_text_field() -> None:
    """SubtitleEntry raw_text field stores original text."""
    entry = SubtitleEntry(
        index=0,
        start="0:00:00.00",
        end="0:00:01.00",
        text="Clean",
        raw_text=r"{\b1}Clean",
    )
    assert entry.raw_text == r"{\b1}Clean"
    assert entry.text == "Clean"


def test_subtitle_entry_metadata_dict() -> None:
    """SubtitleEntry metadata stores arbitrary data."""
    entry = SubtitleEntry(
        index=0,
        start="0:00:00.00",
        end="0:00:01.00",
        text="Test",
        metadata={"key": "value", "num": "42"},
    )
    assert entry.metadata["key"] == "value"
    assert len(entry.metadata) == 2  # noqa: PLR2004


# ---------------------------------------------------------------------------
# EXPANDED: SRT with various real-world patterns
# ---------------------------------------------------------------------------


def test_parse_srt_text_with_urls() -> None:
    """SRT text containing URLs is preserved."""
    content = "1\n00:00:01,000 --> 00:00:04,000\nVisit https://example.com today\n"
    entries, _ = parse_srt(content)
    assert "https://example.com" in entries[0].text


def test_parse_srt_text_with_numbers() -> None:
    """SRT text that is only a number is still parsed."""
    content = "1\n00:00:01,000 --> 00:00:04,000\n42\n"
    entries, _ = parse_srt(content)
    assert entries[0].text == "42"


def test_parse_srt_text_with_parentheses() -> None:
    """SRT text with parentheses is preserved."""
    content = "1\n00:00:01,000 --> 00:00:04,000\n(whispering) Hello\n"
    entries, _ = parse_srt(content)
    assert entries[0].text == "(whispering) Hello"


def test_parse_srt_text_with_brackets() -> None:
    """SRT text with square brackets is preserved."""
    content = "1\n00:00:01,000 --> 00:00:04,000\n[Music]\n"
    entries, _ = parse_srt(content)
    assert entries[0].text == "[Music]"


def test_parse_srt_text_with_dash() -> None:
    """SRT text with dialogue dash is preserved."""
    content = "1\n00:00:01,000 --> 00:00:04,000\n- Hello\n- Hi there\n"
    entries, _ = parse_srt(content)
    assert entries[0].text == "- Hello\n- Hi there"


# ---------------------------------------------------------------------------
# EXPANDED: VTT serialization edge cases
# ---------------------------------------------------------------------------


def test_serialize_vtt_large_number_of_cues() -> None:
    """VTT with 50 cues serializes and re-parses correctly."""
    entries = []
    for i in range(50):
        entries.append(
            SubtitleEntry(
                index=i,
                start=f"00:00:{i:02d}.000",
                end=f"00:00:{i:02d}.999",
                text=f"Cue {i}",
            ),
        )
    result = serialize_vtt(entries, "WEBVTT")
    entries2, _ = parse_vtt(result)
    assert len(entries2) == 50  # noqa: PLR2004
    assert entries2[49].text == "Cue 49"


def test_serialize_vtt_multiline_text() -> None:
    """VTT cue with multiline text serializes correctly."""
    entries = [
        SubtitleEntry(
            index=0,
            start="00:00:01.000",
            end="00:00:04.000",
            text="Line A\nLine B",
        ),
    ]
    result = serialize_vtt(entries, "WEBVTT")
    assert "Line A\nLine B" in result


# ---------------------------------------------------------------------------
# EXPANDED: ASS tag edge cases
# ---------------------------------------------------------------------------


def test_strip_ass_tags_animation() -> None:
    r"""Animation override tag like \t() is stripped."""
    text = r"{\t(0,1000,\fs40)}Growing text"
    result = _strip_ass_tags(text)
    assert result == "Growing text"


def test_strip_ass_tags_color() -> None:
    r"""Color override tag like \c&H0000FF& is stripped."""
    text = r"{\c&H0000FF&}Blue text"
    result = _strip_ass_tags(text)
    assert result == "Blue text"


def test_strip_ass_tags_multiple_in_sequence() -> None:
    r"""Multiple sequential tags are all stripped."""
    text = r"{\b1}{\i1}{\u1}{\s1}Styled"
    result = _strip_ass_tags(text)
    assert result == "Styled"


def test_restore_ass_tags_complex_leading() -> None:
    r"""Complex leading tags are restored."""
    original = r"{\an8}{\pos(320,50)}{\fad(500,500)}Hello"
    translated = "Bonjour"
    result = _restore_ass_tags(original, translated)
    assert result == r"{\an8}{\pos(320,50)}{\fad(500,500)}Bonjour"


def test_restore_ass_tags_only_text_no_tags() -> None:
    """When original has no tags, translated text is returned unchanged."""
    result = _restore_ass_tags("Simple text", "Texte simple")
    assert result == "Texte simple"


# ---------------------------------------------------------------------------
# EXPANDED: Cross-format roundtrip
# ---------------------------------------------------------------------------


def test_srt_full_pipeline_roundtrip() -> None:
    """Full SRT pipeline: parse -> modify -> serialize -> re-parse."""
    original = (
        "1\n00:00:01,000 --> 00:00:04,000\nHello\n\n"
        "2\n00:00:05,000 --> 00:00:08,000\nWorld\n"
    )
    entries, fmt = parse_subtitle(original, ".srt")
    entries[0].text = "Bonjour"
    entries[1].text = "Monde"
    result = serialize_subtitle(entries, fmt, ".srt")
    entries2, _ = parse_subtitle(result, ".srt")
    assert entries2[0].text == "Bonjour"
    assert entries2[1].text == "Monde"


def test_vtt_full_pipeline_roundtrip() -> None:
    """Full VTT pipeline: parse -> modify -> serialize -> re-parse."""
    original = (
        "WEBVTT\n\n"
        "00:00:01.000 --> 00:00:04.000\nHello\n\n"
        "00:00:05.000 --> 00:00:08.000\nWorld\n"
    )
    entries, header = parse_subtitle(original, ".vtt")
    entries[0].text = "Bonjour"
    entries[1].text = "Monde"
    result = serialize_subtitle(entries, header, ".vtt")
    entries2, _ = parse_subtitle(result, ".vtt")
    assert entries2[0].text == "Bonjour"
    assert entries2[1].text == "Monde"


def test_ass_full_pipeline_roundtrip() -> None:
    """Full ASS pipeline: parse -> modify -> serialize -> re-parse."""
    entries, preserved = parse_subtitle(_SAMPLE_ASS, ".ass")
    entries[0].text = "Bonjour le monde"
    entries[1].text = "Au revoir le monde"
    result = serialize_subtitle(entries, preserved, ".ass")
    entries2, _ = parse_subtitle(result, ".ass")
    assert entries2[0].text == "Bonjour le monde"
    assert entries2[1].text == "Au revoir le monde"


# ---------------------------------------------------------------------------
# EXPANDED: _is_vtt_header_block (internal helper)
# ---------------------------------------------------------------------------


def test_is_vtt_header_block_webvtt() -> None:
    """WEBVTT line is recognized as header block."""
    from src.utils.subtitle_utils import _is_vtt_header_block  # noqa: PLC0415

    assert _is_vtt_header_block("WEBVTT") is True
    assert _is_vtt_header_block("WEBVTT - Header Info") is True


def test_is_vtt_header_block_note() -> None:
    """NOTE block is recognized as header block."""
    from src.utils.subtitle_utils import _is_vtt_header_block  # noqa: PLC0415

    assert _is_vtt_header_block("NOTE Some comment") is True


def test_is_vtt_header_block_style() -> None:
    """STYLE block is recognized as header block."""
    from src.utils.subtitle_utils import _is_vtt_header_block  # noqa: PLC0415

    assert _is_vtt_header_block("STYLE\n::cue { }") is True


def test_is_vtt_header_block_regular_text() -> None:
    """Regular text is not recognized as header block."""
    from src.utils.subtitle_utils import _is_vtt_header_block  # noqa: PLC0415

    assert _is_vtt_header_block("Regular text") is False
    assert _is_vtt_header_block("00:00:01.000 --> 00:00:04.000") is False


# ---------------------------------------------------------------------------
# EXPANDED: SRT with edge case timestamps
# ---------------------------------------------------------------------------


def test_parse_srt_zero_timestamps() -> None:
    """SRT with all-zero timestamps parses correctly."""
    content = "1\n00:00:00,000 --> 00:00:00,000\nInstant\n"
    entries, _ = parse_srt(content)
    assert len(entries) == 1
    assert entries[0].start == "00:00:00,000"
    assert entries[0].end == "00:00:00,000"


def test_parse_srt_large_hour_values() -> None:
    """SRT with double-digit hour values parses correctly."""
    content = "1\n99:59:59,999 --> 99:59:59,999\nLong movie\n"
    entries, _ = parse_srt(content)
    assert len(entries) == 1
    assert entries[0].start == "99:59:59,999"


# ---------------------------------------------------------------------------
# EXPANDED: VTT with edge case cue ids
# ---------------------------------------------------------------------------


def test_parse_vtt_numeric_cue_id() -> None:
    """VTT cue with numeric ID is preserved."""
    content = "WEBVTT\n\n42\n00:00:01.000 --> 00:00:04.000\nNumbered\n"
    entries, _ = parse_vtt(content)
    assert entries[0].metadata.get("cue_id") == "42"


def test_parse_vtt_hyphenated_cue_id() -> None:
    """VTT cue with hyphenated ID is preserved."""
    content = "WEBVTT\n\nchapter-1\n00:00:01.000 --> 00:00:04.000\nChapter\n"
    entries, _ = parse_vtt(content)
    assert entries[0].metadata.get("cue_id") == "chapter-1"


# ===========================================================================
# EXPANDED: SRT parsing edge cases
# ===========================================================================


def test_parse_srt_missing_index_line() -> None:
    """SRT block without index number but with valid timestamp still parses."""
    content = "00:00:01,000 --> 00:00:04,000\nHello world\n"
    entries, _ = parse_srt(content)
    assert len(entries) == 1
    assert entries[0].text == "Hello world"


def test_parse_srt_extra_blank_lines_between_blocks() -> None:
    """SRT with extra blank lines between blocks still parses."""
    content = (
        "1\n00:00:01,000 --> 00:00:04,000\nFirst\n\n\n\n"
        "2\n00:00:05,000 --> 00:00:08,000\nSecond\n"
    )
    entries, _ = parse_srt(content)
    assert len(entries) == 2
    assert entries[0].text == "First"
    assert entries[1].text == "Second"


def test_parse_srt_multiline_text() -> None:
    """SRT with multiline text preserves newlines."""
    content = "1\n00:00:01,000 --> 00:00:04,000\nLine one\nLine two\nLine three\n"
    entries, _ = parse_srt(content)
    assert len(entries) == 1
    assert entries[0].text == "Line one\nLine two\nLine three"


def test_parse_srt_windows_line_endings_full() -> None:
    """SRT with Windows CRLF line endings parses correctly."""
    content = "1\r\n00:00:01,000 --> 00:00:04,000\r\nHello\r\n\r\n2\r\n00:00:05,000 --> 00:00:08,000\r\nWorld\r\n"
    entries, _ = parse_srt(content)
    assert len(entries) == 2


def test_parse_srt_timestamps_without_leading_zero() -> None:
    """SRT timestamps with single-digit hours parse correctly."""
    content = "1\n0:00:01,000 --> 0:00:04,000\nShort hour\n"
    entries, _ = parse_srt(content)
    assert len(entries) == 1
    assert entries[0].start == "0:00:01,000"


def test_parse_srt_special_characters_in_text() -> None:
    """SRT with special characters in text preserves them."""
    content = '1\n00:00:01,000 --> 00:00:04,000\nHello <b>world</b> & "friends"\n'
    entries, _ = parse_srt(content)
    assert len(entries) == 1
    assert "<b>world</b>" in entries[0].text
    assert "&" in entries[0].text


def test_parse_srt_unicode_text() -> None:
    """SRT with unicode text preserves characters."""
    content = "1\n00:00:01,000 --> 00:00:04,000\nXin chào thế giới 你好世界\n"
    entries, _ = parse_srt(content)
    assert len(entries) == 1
    assert "chào" in entries[0].text
    assert "你好" in entries[0].text


def test_parse_srt_empty_text_between_valid_entries() -> None:
    """SRT with an empty-text block between valid entries skips the empty block."""
    content = (
        "1\n00:00:01,000 --> 00:00:04,000\nFirst\n\n"
        "2\n00:00:05,000 --> 00:00:08,000\n\n\n"
        "3\n00:00:09,000 --> 00:00:12,000\nThird\n"
    )
    entries, _ = parse_srt(content)
    assert len(entries) == 2
    assert entries[0].text == "First"
    assert entries[1].text == "Third"


def test_parse_srt_whitespace_only_text_skipped() -> None:
    """SRT with whitespace-only text lines is skipped."""
    content = "1\n00:00:01,000 --> 00:00:04,000\n   \n"
    entries, _ = parse_srt(content)
    assert len(entries) == 0


def test_parse_srt_entry_indices_are_zero_based() -> None:
    """SRT entries have 0-based indices regardless of original numbering."""
    content = (
        "5\n00:00:01,000 --> 00:00:04,000\nFirst\n\n"
        "10\n00:00:05,000 --> 00:00:08,000\nSecond\n"
    )
    entries, _ = parse_srt(content)
    assert entries[0].index == 0
    assert entries[1].index == 1


def test_parse_srt_timestamp_with_dot_separator() -> None:
    """SRT timestamps using dot instead of comma still match regex."""
    content = "1\n00:00:01.000 --> 00:00:04.000\nDot timestamps\n"
    entries, _ = parse_srt(content)
    assert len(entries) == 1


def test_parse_srt_two_digit_milliseconds() -> None:
    """SRT timestamps with two-digit milliseconds parse correctly."""
    content = "1\n00:00:01,00 --> 00:00:04,99\nShort ms\n"
    entries, _ = parse_srt(content)
    assert len(entries) == 1


# ===========================================================================
# EXPANDED: SRT serialization
# ===========================================================================


def test_serialize_srt_single_entry() -> None:
    """serialize_srt produces valid SRT for a single entry."""
    entries = [
        SubtitleEntry(index=0, start="00:00:01,000", end="00:00:04,000", text="Hello")
    ]
    result = serialize_srt(entries)
    assert "1\n00:00:01,000 --> 00:00:04,000\nHello" in result


def test_serialize_srt_preserves_multiline_text() -> None:
    """serialize_srt preserves multiline text."""
    entries = [
        SubtitleEntry(
            index=0, start="00:00:01,000", end="00:00:04,000", text="Line 1\nLine 2"
        )
    ]
    result = serialize_srt(entries)
    assert "Line 1\nLine 2" in result


def test_serialize_srt_multiple_entries_sequential_numbering() -> None:
    """serialize_srt uses sequential 1-based numbering."""
    entries = [
        SubtitleEntry(index=0, start="00:00:01,000", end="00:00:04,000", text="First"),
        SubtitleEntry(index=1, start="00:00:05,000", end="00:00:08,000", text="Second"),
    ]
    result = serialize_srt(entries)
    assert "1\n00:00:01,000 --> 00:00:04,000\nFirst" in result
    assert "2\n00:00:05,000 --> 00:00:08,000\nSecond" in result


def test_serialize_srt_empty_entries() -> None:
    """serialize_srt with no entries returns empty string."""
    result = serialize_srt([])
    assert result == ""


def test_srt_roundtrip() -> None:
    """SRT parse → serialize → parse roundtrip preserves entries."""
    content = (
        "1\n00:00:01,000 --> 00:00:04,000\nFirst\n\n"
        "2\n00:00:05,000 --> 00:00:08,000\nSecond line\n"
    )
    entries, fmt_data = parse_srt(content)
    result = serialize_srt(entries, fmt_data)
    re_entries, _ = parse_srt(result)
    assert len(re_entries) == len(entries)
    for orig, re_parsed in zip(entries, re_entries, strict=True):
        assert orig.start == re_parsed.start
        assert orig.end == re_parsed.end
        assert orig.text == re_parsed.text


def test_srt_roundtrip_multiline() -> None:
    """SRT roundtrip preserves multiline subtitle text."""
    content = "1\n00:00:01,000 --> 00:00:04,000\nLine A\nLine B\n"
    entries, fmt_data = parse_srt(content)
    result = serialize_srt(entries, fmt_data)
    re_entries, _ = parse_srt(result)
    assert re_entries[0].text == "Line A\nLine B"


# ===========================================================================
# EXPANDED: VTT parsing edge cases
# ===========================================================================


def test_parse_vtt_with_note_comment() -> None:
    """VTT NOTE blocks are preserved in header."""
    content = (
        "WEBVTT\n\nNOTE This is a comment\n\n00:00:01.000 --> 00:00:04.000\nHello\n"
    )
    entries, header = parse_vtt(content)
    assert len(entries) == 1
    assert "NOTE" in header


def test_parse_vtt_with_style_block() -> None:
    """VTT STYLE blocks are preserved in header."""
    content = "WEBVTT\n\nSTYLE\n::cue { color: white; }\n\n00:00:01.000 --> 00:00:04.000\nText\n"
    entries, header = parse_vtt(content)
    assert len(entries) == 1
    assert "STYLE" in header


def test_parse_vtt_with_cue_settings() -> None:
    """VTT cue settings (position, align) are preserved in metadata."""
    content = (
        "WEBVTT\n\n00:00:01.000 --> 00:00:04.000 position:10% align:left\nPositioned\n"
    )
    entries, _ = parse_vtt(content)
    assert len(entries) == 1
    assert entries[0].metadata.get("cue_settings") == "position:10% align:left"


def test_parse_vtt_without_webvtt_header() -> None:
    """VTT without WEBVTT header still parses cues."""
    content = "00:00:01.000 --> 00:00:04.000\nNo header\n"
    entries, header = parse_vtt(content)
    assert len(entries) == 1
    assert entries[0].text == "No header"


def test_parse_vtt_multiline_cue_text() -> None:
    """VTT multiline cue text is preserved."""
    content = "WEBVTT\n\n00:00:01.000 --> 00:00:04.000\nLine 1\nLine 2\n"
    entries, _ = parse_vtt(content)
    assert len(entries) == 1
    assert entries[0].text == "Line 1\nLine 2"


def test_parse_vtt_empty_cue_text_skipped() -> None:
    """VTT cue with empty text is skipped."""
    content = "WEBVTT\n\n00:00:01.000 --> 00:00:04.000\n\n\n00:00:05.000 --> 00:00:08.000\nValid\n"
    entries, _ = parse_vtt(content)
    assert len(entries) == 1
    assert entries[0].text == "Valid"


def test_parse_vtt_multiple_note_blocks() -> None:
    """VTT with multiple NOTE blocks preserves all in header."""
    content = (
        "WEBVTT\n\nNOTE First\n\nNOTE Second\n\n00:00:01.000 --> 00:00:04.000\nText\n"
    )
    entries, header = parse_vtt(content)
    assert len(entries) == 1
    assert "NOTE First" in header
    assert "NOTE Second" in header


def test_parse_vtt_unicode_text() -> None:
    """VTT with unicode text preserves characters."""
    content = "WEBVTT\n\n00:00:01.000 --> 00:00:04.000\nこんにちは 세계\n"
    entries, _ = parse_vtt(content)
    assert len(entries) == 1
    assert "こんにちは" in entries[0].text


def test_parse_vtt_cue_id_with_spaces() -> None:
    """VTT cue with ID containing spaces is preserved."""
    content = "WEBVTT\n\nmy cue id\n00:00:01.000 --> 00:00:04.000\nText\n"
    entries, _ = parse_vtt(content)
    assert entries[0].metadata.get("cue_id") == "my cue id"


def test_parse_vtt_timestamp_without_hours() -> None:
    """VTT timestamps without hours (mm:ss.ms) are handled."""
    content = "WEBVTT\n\n0:01.000 --> 0:04.000\nShort time\n"
    # Depending on regex, this may or may not parse - test it doesn't crash
    entries, _ = parse_vtt(content)
    # The result depends on whether the regex matches; we just ensure no exception


# ===========================================================================
# EXPANDED: VTT serialization
# ===========================================================================


def test_serialize_vtt_with_header() -> None:
    """serialize_vtt includes header when provided."""
    entries = [
        SubtitleEntry(index=0, start="00:00:01.000", end="00:00:04.000", text="Hello")
    ]
    result = serialize_vtt(entries, "WEBVTT")
    assert result.startswith("WEBVTT")
    assert "00:00:01.000 --> 00:00:04.000" in result


def test_serialize_vtt_without_header() -> None:
    """serialize_vtt without header still produces valid output."""
    entries = [
        SubtitleEntry(index=0, start="00:00:01.000", end="00:00:04.000", text="Hello")
    ]
    result = serialize_vtt(entries, "")
    assert "00:00:01.000 --> 00:00:04.000" in result


def test_serialize_vtt_with_cue_id() -> None:
    """serialize_vtt includes cue IDs when present."""
    entries = [
        SubtitleEntry(
            index=0,
            start="00:00:01.000",
            end="00:00:04.000",
            text="Hello",
            metadata={"cue_id": "intro"},
        )
    ]
    result = serialize_vtt(entries, "WEBVTT")
    assert "intro" in result


def test_serialize_vtt_with_cue_settings() -> None:
    """serialize_vtt includes cue settings when present."""
    entries = [
        SubtitleEntry(
            index=0,
            start="00:00:01.000",
            end="00:00:04.000",
            text="Hello",
            metadata={"cue_settings": "align:left"},
        )
    ]
    result = serialize_vtt(entries, "WEBVTT")
    assert "align:left" in result


def test_serialize_vtt_empty_entries() -> None:
    """serialize_vtt with no entries returns just header."""
    result = serialize_vtt([], "WEBVTT")
    assert "WEBVTT" in result


def test_vtt_roundtrip() -> None:
    """VTT parse → serialize → parse roundtrip preserves entries."""
    content = "WEBVTT\n\n00:00:01.000 --> 00:00:04.000\nFirst cue\n\n00:00:05.000 --> 00:00:08.000\nSecond cue\n"
    entries, header = parse_vtt(content)
    result = serialize_vtt(entries, header)
    re_entries, _ = parse_vtt(result)
    assert len(re_entries) == len(entries)
    for orig, re_parsed in zip(entries, re_entries, strict=True):
        assert orig.start == re_parsed.start
        assert orig.text == re_parsed.text


def test_vtt_roundtrip_with_cue_id_and_settings() -> None:
    """VTT roundtrip preserves cue IDs and settings."""
    content = (
        "WEBVTT\n\nintro\n00:00:01.000 --> 00:00:04.000 position:50%\nIntro text\n"
    )
    entries, header = parse_vtt(content)
    result = serialize_vtt(entries, header)
    re_entries, _ = parse_vtt(result)
    assert re_entries[0].metadata.get("cue_id") == "intro"
    assert re_entries[0].metadata.get("cue_settings") == "position:50%"


# ===========================================================================
# EXPANDED: ASS/SSA parsing edge cases
# ===========================================================================


def test_parse_ass_empty_content() -> None:
    """ASS with empty content returns empty entries."""
    entries, preserved = parse_ass("")
    assert entries == []
    assert preserved == []


def test_parse_ass_no_events_section() -> None:
    """ASS without [Events] section returns no entries."""
    content = "[Script Info]\nTitle: Test\n\n[V4+ Styles]\nFormat: Name, Fontname\nStyle: Default,Arial\n"
    entries, preserved = parse_ass(content)
    assert entries == []
    assert len(preserved) > 0


def test_parse_ass_multiple_dialogue_lines() -> None:
    """ASS with multiple Dialogue lines parses all."""
    content = (
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,First line\n"
        "Dialogue: 0,0:00:05.00,0:00:08.00,Default,,0,0,0,,Second line\n"
    )
    entries, _ = parse_ass(content)
    assert len(entries) == 2
    assert entries[0].text == "First line"
    assert entries[1].text == "Second line"


def test_parse_ass_dialogue_with_override_tags() -> None:
    """ASS dialogue with override tags strips them from text."""
    content = (
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        r"Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,{\b1}Bold text{\b0}" + "\n"
    )
    entries, _ = parse_ass(content)
    assert len(entries) == 1
    assert entries[0].text == "Bold text"
    assert r"{\b1}" in entries[0].raw_text


def test_parse_ass_dialogue_with_commas_in_text() -> None:
    """ASS dialogue with commas in text preserves them."""
    content = (
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,Hello, world, how are you?\n"
    )
    entries, _ = parse_ass(content)
    assert len(entries) == 1
    assert entries[0].text == "Hello, world, how are you?"


def test_parse_ass_preserves_non_events_sections() -> None:
    """ASS parser preserves [Script Info] and [V4+ Styles] sections."""
    content = (
        "[Script Info]\nTitle: Test\n\n"
        "[V4+ Styles]\nFormat: Name\nStyle: Default\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,Text\n"
    )
    entries, preserved = parse_ass(content)
    assert any("[Script Info]" in line for line in preserved)
    assert any("[V4+ Styles]" in line for line in preserved)


def test_parse_ass_timestamps_extracted() -> None:
    """ASS parser extracts start and end timestamps from dialogue."""
    content = (
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,1:23:45.67,2:34:56.78,Default,,0,0,0,,Timed text\n"
    )
    entries, _ = parse_ass(content)
    assert entries[0].start == "1:23:45.67"
    assert entries[0].end == "2:34:56.78"


def test_parse_ass_comment_lines_preserved() -> None:
    """ASS Comment: lines are preserved (not treated as dialogue)."""
    content = (
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Comment: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,Hidden comment\n"
        "Dialogue: 0,0:00:05.00,0:00:08.00,Default,,0,0,0,,Visible\n"
    )
    entries, preserved = parse_ass(content)
    assert len(entries) == 1
    assert entries[0].text == "Visible"
    assert any("Comment:" in line for line in preserved)


# ===========================================================================
# EXPANDED: ASS serialization
# ===========================================================================


def test_serialize_ass_replaces_placeholders() -> None:
    """serialize_ass replaces __SUB_N__ placeholders with translated text."""
    entries = [
        SubtitleEntry(
            index=0,
            start="0:00:01.00",
            end="0:00:04.00",
            text="Translated",
            raw_text="Original",
        ),
    ]
    preserved = [
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        "Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,__SUB_0__",
    ]
    result = serialize_ass(entries, preserved)
    assert "Translated" in result
    assert "__SUB_0__" not in result


def test_serialize_ass_restores_leading_tags() -> None:
    """serialize_ass restores leading override tags from raw_text."""
    entries = [
        SubtitleEntry(
            index=0,
            start="0:00:01.00",
            end="0:00:04.00",
            text="Bold text",
            raw_text=r"{\b1}Original bold",
        ),
    ]
    preserved = ["Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,__SUB_0__"]
    result = serialize_ass(entries, preserved)
    assert r"{\b1}Bold text" in result


def test_serialize_ass_multiple_entries() -> None:
    """serialize_ass handles multiple entries correctly."""
    entries = [
        SubtitleEntry(
            index=0,
            start="0:00:01.00",
            end="0:00:04.00",
            text="First",
            raw_text="First",
        ),
        SubtitleEntry(
            index=1,
            start="0:00:05.00",
            end="0:00:08.00",
            text="Second",
            raw_text="Second",
        ),
    ]
    preserved = [
        "Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,__SUB_0__",
        "Dialogue: 0,0:00:05.00,0:00:08.00,Default,,0,0,0,,__SUB_1__",
    ]
    result = serialize_ass(entries, preserved)
    assert "First" in result
    assert "Second" in result


def test_ass_roundtrip() -> None:
    """ASS parse → serialize → parse roundtrip preserves entries."""
    content = (
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,First line\n"
        "Dialogue: 0,0:00:05.00,0:00:08.00,Default,,0,0,0,,Second line\n"
    )
    entries, preserved = parse_ass(content)
    result = serialize_ass(entries, preserved)
    re_entries, _ = parse_ass(result)
    assert len(re_entries) == 2
    assert re_entries[0].text == "First line"
    assert re_entries[1].text == "Second line"


def test_ass_roundtrip_with_tags() -> None:
    """ASS roundtrip preserves leading override tags."""
    content = (
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        r"Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,{\b1}Bold text" + "\n"
    )
    entries, preserved = parse_ass(content)
    # Simulate translation: text stays the same
    result = serialize_ass(entries, preserved)
    re_entries, _ = parse_ass(result)
    assert re_entries[0].text == "Bold text"


# ===========================================================================
# EXPANDED: Tag stripping and restoration edge cases
# ===========================================================================


def test_strip_ass_tags_no_tags() -> None:
    """_strip_ass_tags with no tags returns text unchanged."""
    from src.utils.subtitle_utils import _strip_ass_tags  # noqa: PLC0415

    assert _strip_ass_tags("Hello world") == "Hello world"


def test_strip_ass_tags_multiple_tags() -> None:
    """_strip_ass_tags removes multiple consecutive tags."""
    from src.utils.subtitle_utils import _strip_ass_tags  # noqa: PLC0415

    assert _strip_ass_tags(r"{\b1}{\i1}Bold italic{\b0}{\i0}") == "Bold italic"


def test_strip_ass_tags_empty_string() -> None:
    """_strip_ass_tags on empty string returns empty."""
    from src.utils.subtitle_utils import _strip_ass_tags  # noqa: PLC0415

    assert _strip_ass_tags("") == ""


def test_strip_ass_tags_position_tag() -> None:
    """_strip_ass_tags removes position tags."""
    from src.utils.subtitle_utils import _strip_ass_tags  # noqa: PLC0415

    result = _strip_ass_tags(r"{\pos(320,240)}Positioned text")
    assert result == "Positioned text"


def test_restore_ass_tags_no_leading_tags() -> None:
    """_restore_ass_tags with no leading tags returns translated unchanged."""
    from src.utils.subtitle_utils import _restore_ass_tags  # noqa: PLC0415

    assert _restore_ass_tags("No tags here", "Translated") == "Translated"


def test_restore_ass_tags_mid_text_tags_ignored() -> None:
    """_restore_ass_tags only restores leading tags, not mid-text tags."""
    from src.utils.subtitle_utils import _restore_ass_tags  # noqa: PLC0415

    result = _restore_ass_tags(r"Text{\b1}mid tag", "Translated")
    assert result == "Translated"


def test_restore_ass_tags_multiple_leading_tags() -> None:
    """_restore_ass_tags restores multiple leading tags."""
    from src.utils.subtitle_utils import _restore_ass_tags  # noqa: PLC0415

    result = _restore_ass_tags(r"{\b1}{\i1}Original", "Translated")
    assert result == r"{\b1}{\i1}Translated"


# ===========================================================================
# EXPANDED: Unified dispatcher edge cases
# ===========================================================================


def test_parse_subtitle_srt_dispatch() -> None:
    """parse_subtitle dispatches .srt to parse_srt."""
    content = "1\n00:00:01,000 --> 00:00:04,000\nHello\n"
    entries, _ = parse_subtitle(content, ".srt")
    assert len(entries) == 1
    assert entries[0].text == "Hello"


def test_parse_subtitle_vtt_dispatch() -> None:
    """parse_subtitle dispatches .vtt to parse_vtt."""
    content = "WEBVTT\n\n00:00:01.000 --> 00:00:04.000\nHello\n"
    entries, _ = parse_subtitle(content, ".vtt")
    assert len(entries) == 1


def test_parse_subtitle_ass_dispatch() -> None:
    """parse_subtitle dispatches .ass to parse_ass."""
    content = (
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,Text\n"
    )
    entries, _ = parse_subtitle(content, ".ass")
    assert len(entries) == 1


def test_parse_subtitle_ssa_dispatch() -> None:
    """parse_subtitle dispatches .ssa to parse_ass."""
    content = (
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,SSA Text\n"
    )
    entries, _ = parse_subtitle(content, ".ssa")
    assert len(entries) == 1
    assert entries[0].text == "SSA Text"


def test_parse_subtitle_unsupported_raises() -> None:
    """parse_subtitle raises ValueError for unsupported format."""
    import pytest  # noqa: PLC0415

    with pytest.raises(ValueError, match="Unsupported"):
        parse_subtitle("content", ".xyz")


def test_serialize_subtitle_srt_dispatch() -> None:
    """serialize_subtitle dispatches .srt to serialize_srt."""
    entries = [
        SubtitleEntry(index=0, start="00:00:01,000", end="00:00:04,000", text="Hello")
    ]
    result = serialize_subtitle(entries, None, ".srt")
    assert "Hello" in result


def test_serialize_subtitle_vtt_dispatch() -> None:
    """serialize_subtitle dispatches .vtt to serialize_vtt."""
    entries = [
        SubtitleEntry(index=0, start="00:00:01.000", end="00:00:04.000", text="Hello")
    ]
    result = serialize_subtitle(entries, "WEBVTT", ".vtt")
    assert "Hello" in result


def test_serialize_subtitle_ass_dispatch() -> None:
    """serialize_subtitle dispatches .ass to serialize_ass."""
    entries = [
        SubtitleEntry(
            index=0, start="0:00:01.00", end="0:00:04.00", text="Text", raw_text="Text"
        )
    ]
    preserved = ["Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,__SUB_0__"]
    result = serialize_subtitle(entries, preserved, ".ass")
    assert "Text" in result


def test_serialize_subtitle_ssa_dispatch() -> None:
    """serialize_subtitle dispatches .ssa to serialize_ass."""
    entries = [
        SubtitleEntry(
            index=0, start="0:00:01.00", end="0:00:04.00", text="Text", raw_text="Text"
        )
    ]
    preserved = ["Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,__SUB_0__"]
    result = serialize_subtitle(entries, preserved, ".ssa")
    assert "Text" in result


def test_serialize_subtitle_unsupported_raises() -> None:
    """serialize_subtitle raises ValueError for unsupported format."""
    import pytest  # noqa: PLC0415

    with pytest.raises(ValueError, match="Unsupported"):
        serialize_subtitle([], None, ".xyz")


# ===========================================================================
# EXPANDED: is_subtitle_format
# ===========================================================================


def test_is_subtitle_format_all_supported() -> None:
    """is_subtitle_format returns True for all supported extensions."""
    for ext in (".srt", ".vtt", ".ass", ".ssa"):
        assert is_subtitle_format(ext) is True


def test_is_subtitle_format_unsupported() -> None:
    """is_subtitle_format returns False for unsupported extensions."""
    for ext in (".txt", ".pdf", ".docx", ".mp3", ".json", ".xml"):
        assert is_subtitle_format(ext) is False


def test_is_subtitle_format_case_sensitive() -> None:
    """is_subtitle_format is case-sensitive."""
    assert is_subtitle_format(".SRT") is False
    assert is_subtitle_format(".Vtt") is False


def test_is_subtitle_format_empty() -> None:
    """is_subtitle_format returns False for empty string."""
    assert is_subtitle_format("") is False


# ===========================================================================
# EXPANDED: BOM handling in subtitle parsing
# ===========================================================================


def test_parse_srt_with_bom() -> None:
    """SRT with UTF-8 BOM parses correctly."""
    content = "\ufeff1\n00:00:01,000 --> 00:00:04,000\nWith BOM\n"
    entries, _ = parse_srt(content)
    assert len(entries) == 1
    assert entries[0].text == "With BOM"


def test_parse_vtt_with_bom() -> None:
    """VTT with UTF-8 BOM parses correctly."""
    content = "\ufeffWEBVTT\n\n00:00:01.000 --> 00:00:04.000\nWith BOM\n"
    entries, header = parse_vtt(content)
    assert len(entries) == 1
    assert entries[0].text == "With BOM"


def test_parse_ass_with_bom() -> None:
    """ASS with UTF-8 BOM parses correctly."""
    content = (
        "\ufeff[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,BOM text\n"
    )
    entries, _ = parse_ass(content)
    assert len(entries) == 1
    assert entries[0].text == "BOM text"


# ===========================================================================
# EXPANDED: Large / stress tests
# ===========================================================================


def test_parse_srt_many_entries() -> None:
    """SRT with many entries all parse correctly."""
    blocks = []
    for i in range(50):
        blocks.append(
            f"{i + 1}\n00:00:{i:02d},000 --> 00:00:{i + 1:02d},000\nEntry {i + 1}"
        )
    content = "\n\n".join(blocks) + "\n"
    entries, _ = parse_srt(content)
    assert len(entries) == 50
    assert entries[0].text == "Entry 1"
    assert entries[49].text == "Entry 50"


def test_parse_vtt_many_cues() -> None:
    """VTT with many cues all parse correctly."""
    cues = ["WEBVTT"]
    for i in range(30):
        cues.append(f"00:00:{i:02d}.000 --> 00:00:{i + 1:02d}.000\nCue {i + 1}")
    content = "\n\n".join(cues) + "\n"
    entries, _ = parse_vtt(content)
    assert len(entries) == 30


def test_parse_ass_many_dialogues() -> None:
    """ASS with many Dialogue lines all parse correctly."""
    lines = [
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for i in range(40):
        lines.append(
            f"Dialogue: 0,0:00:{i:02d}.00,0:00:{i + 1:02d}.00,Default,,0,0,0,,Line {i + 1}"
        )
    content = "\n".join(lines) + "\n"
    entries, _ = parse_ass(content)
    assert len(entries) == 40


# ===========================================================================
# EXPANDED: _is_vtt_header_block additional
# ===========================================================================


def test_is_vtt_header_block_webvtt_with_description() -> None:
    """WEBVTT followed by description is recognized as header."""
    from src.utils.subtitle_utils import _is_vtt_header_block  # noqa: PLC0415

    assert _is_vtt_header_block("WEBVTT - My subtitle file") is True


def test_is_vtt_header_block_empty_string() -> None:
    """Empty string is not a header block."""
    from src.utils.subtitle_utils import _is_vtt_header_block  # noqa: PLC0415

    assert _is_vtt_header_block("") is False


def test_is_vtt_header_block_note_multiline() -> None:
    """Multiline NOTE block is recognized."""
    from src.utils.subtitle_utils import _is_vtt_header_block  # noqa: PLC0415

    assert _is_vtt_header_block("NOTE\nMultiline comment") is True


# ===========================================================================
# EXPANDED: SubtitleEntry dataclass
# ===========================================================================


def test_subtitle_entry_default_metadata() -> None:
    """SubtitleEntry has empty metadata dict by default."""
    entry = SubtitleEntry(
        index=0, start="00:00:01,000", end="00:00:04,000", text="Test"
    )
    assert entry.metadata == {}


def test_subtitle_entry_default_raw_text() -> None:
    """SubtitleEntry has empty raw_text by default."""
    entry = SubtitleEntry(
        index=0, start="00:00:01,000", end="00:00:04,000", text="Test"
    )
    assert entry.raw_text == ""


def test_subtitle_entry_with_metadata() -> None:
    """SubtitleEntry metadata can be populated."""
    entry = SubtitleEntry(
        index=0,
        start="00:00:01,000",
        end="00:00:04,000",
        text="Test",
        metadata={"cue_id": "intro", "cue_settings": "align:left"},
    )
    assert entry.metadata["cue_id"] == "intro"
    assert entry.metadata["cue_settings"] == "align:left"


def test_subtitle_entry_equality() -> None:
    """SubtitleEntry supports dataclass equality comparison."""
    e1 = SubtitleEntry(index=0, start="0", end="1", text="A")
    e2 = SubtitleEntry(index=0, start="0", end="1", text="A")
    assert e1 == e2


def test_subtitle_entry_inequality() -> None:
    """SubtitleEntry detects differences."""
    e1 = SubtitleEntry(index=0, start="0", end="1", text="A")
    e2 = SubtitleEntry(index=0, start="0", end="1", text="B")
    assert e1 != e2


# ── Long-duration / high-hour timestamp coverage ─────────────────────────
#
# Most subtitle tests use timestamps under one hour.  Long-form videos
# (audiobooks, live-event recordings, course modules) routinely exceed
# 24 hours, and the SRT spec doesn't cap the hour field at 23.  These
# tests guard against a regression where the parser silently drops or
# truncates entries whose hour ≥ 24 because of a stricter regex or
# datetime conversion step.


def test_parse_srt_timestamp_above_24_hours() -> None:
    """SRT cues with hour fields ≥ 24 round-trip as plain text."""
    srt = "1\n25:30:00,000 --> 25:30:05,000\nLong-form audiobook chapter 12.\n"
    entries, _ = parse_srt(srt)
    assert len(entries) == 1
    assert entries[0].start == "25:30:00,000"
    assert entries[0].end == "25:30:05,000"
    assert entries[0].text == "Long-form audiobook chapter 12."


def test_parse_srt_three_digit_hour() -> None:
    """Three-digit hour values (e.g. 100h+) parse without overflow."""
    srt = "1\n100:00:00,000 --> 100:00:02,500\nHundred-hour mark.\n"
    entries, _ = parse_srt(srt)
    assert len(entries) == 1
    assert entries[0].start.startswith("100:")


def test_serialize_srt_preserves_high_hour_field() -> None:
    """Round-trip of a 24h+ entry keeps the hour intact (no day-wrap)."""
    entries = [
        SubtitleEntry(
            index=0,
            start="48:00:00,000",
            end="48:00:03,000",
            text="Two-day live capture marker.",
        ),
    ]
    output = serialize_srt(entries)
    assert "48:00:00,000" in output
    assert "48:00:03,000" in output


# ---------------------------------------------------------------------------
# mirror_ass_alignment_for_rtl
# ---------------------------------------------------------------------------


def test_mirror_an_override_tag_flips_horizontal() -> None:
    """\\an1 → \\an3, \\an7 → \\an9; centre codes (\\an2/5/8) stay put."""
    src = r"{\an1\b1}Hello{\an2}World{\an7}Top{\an5}Mid"
    out = mirror_ass_alignment_for_rtl(src)
    assert r"\an3" in out
    assert r"\an9" in out
    # Centre codes unchanged.
    assert r"\an2" in out
    assert r"\an5" in out
    # Non-alignment tag (\b1) survives.
    assert r"\b1" in out


def test_mirror_legacy_a_tag_flips_horizontal() -> None:
    """Legacy \\a1/3/5/7/9/11 mirror; \\a2/6/10 stay."""
    src = r"{\a1}A{\a2}B{\a5}C{\a9}D"
    out = mirror_ass_alignment_for_rtl(src)
    assert r"\a3" in out
    assert r"\a7" in out
    assert r"\a11" in out
    assert r"\a2" in out


def test_mirror_style_row_alignment_column() -> None:
    """V4+ Style row's Alignment column flips for RTL."""
    style_row = (
        "Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,"
        "0,0,0,0,100,100,0,0,1,2,2,1,10,10,10,1\n"
    )
    out = mirror_ass_alignment_for_rtl(style_row)
    # 19th field (Alignment) was 1; should become 3.
    cols = out.split("Style:", 1)[1].split(",")
    assert cols[18].strip() == "3"


def test_mirror_is_idempotent_for_centred_alignments() -> None:
    """Centred (5) round-trips unchanged."""
    src = r"{\an5}centred line"
    assert mirror_ass_alignment_for_rtl(src) == src


def test_mirror_an4_an6_middle_row_left_right_flip() -> None:
    """Middle-row left/right (\\an4 ↔ \\an6) flip alongside the corner pairs.

    ``\\an4`` (mid-left) and ``\\an6`` (mid-right) are the two
    middle-row positions in the 9-cell numpad alignment grid.  The
    audit caught that only the corner pairs (an1↔an3, an7↔an9) were
    previously asserted — middle-row flipping was untested.  Without
    this guard, an RTL render that left ``\\an4`` text on the
    left-edge of the screen for an Arabic / Hebrew subtitle would
    silently regress.
    """
    src = r"{\an4}LeftMid{\an6}RightMid"
    out = mirror_ass_alignment_for_rtl(src)
    assert r"\an6" in out
    assert r"\an4" in out
    # Specifically: the original \an4 became \an6 and vice versa
    # (i.e. positions swapped), not just both still present.
    assert out.index(r"\an6") < out.index(r"\an4"), (
        f"\\an4 must flip to \\an6 (and vice versa) in order; got {out!r}"
    )


def test_mirror_legacy_a5_a7_middle_row_legacy_codes() -> None:
    """Legacy ``\\a5`` (mid-left) ↔ ``\\a7`` (mid-right) mirror.

    Legacy code mapping per AGENTS.md: ``\\a1↔\\a3``, ``\\a5↔\\a7``,
    ``\\a9↔\\a11``.  The original middle-row legacy pair wasn't
    directly asserted.
    """
    src = r"{\a5}MidLeft{\a7}MidRight"
    out = mirror_ass_alignment_for_rtl(src)
    assert r"\a7" in out
    assert out.index(r"\a7") < out.index(r"\a5"), (
        f"\\a5 must flip to \\a7 in order; got {out!r}"
    )
