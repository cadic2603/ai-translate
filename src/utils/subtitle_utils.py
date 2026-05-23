"""Subtitle file parsing and serialization utilities.

Supports SRT, VTT (WebVTT), ASS, and SSA formats.  Each format has a
parse/serialize pair.  The unified ``parse_subtitle`` / ``serialize_subtitle``
dispatchers select the correct pair based on file extension.
"""

import logging
import re
from dataclasses import dataclass, field

from src.utils.text_utils import strip_bom

logger = logging.getLogger("subtitle_utils")

# ── Constants ────────────────────────────────────────────────────────

_SUBTITLE_EXTENSIONS: set[str] = {".srt", ".vtt", ".ass", ".ssa"}

# Regex for ASS/SSA override tags: {\b1}, {\pos(320,240)}, etc.
_ASS_OVERRIDE_TAG_RE = re.compile(r"\{\\[^}]*\}")

# ASS \anN (numpad) and legacy \aN alignment override tags.
_ASS_ALIGN_AN_RE = re.compile(r"\\an([1-9])")
_ASS_ALIGN_LEGACY_RE = re.compile(r"\\a(\d+)")
# V4+ Style row: "Style: Default,Arial,...,<Alignment>,..."  Alignment is
# the 19th comma-separated field (1-indexed) under the canonical Format
# row used by libass, so column index 18 in zero-indexed terms.
_ASS_STYLE_ALIGNMENT_INDEX = 18

# Mirror table for numpad alignment codes (1-9): horizontal anchor flips,
# vertical anchor stays.  5/2/8 (centre column) are unchanged.
_ASS_AN_MIRROR: dict[str, str] = {
    "1": "3", "3": "1",
    "4": "6", "6": "4",
    "7": "9", "9": "7",
}
# Mirror table for legacy SSA \a codes (1=BL, 2=BC, 3=BR, 5=TL, 6=TC, 7=TR,
# 9=ML, 10=MC, 11=MR; +4 for top, +8 for middle).  Same horizontal flip.
_ASS_LEGACY_MIRROR: dict[str, str] = {
    "1": "3", "3": "1",
    "5": "7", "7": "5",
    "9": "11", "11": "9",
}


def mirror_ass_alignment_for_rtl(ass_text: str) -> str:
    r"""Mirrors ASS/SSA alignment codes left↔right for an RTL target.

    Flips both the per-line override tags (``\an1`` ↔ ``\an3`` etc.)
    and the V4+ Style table's ``Alignment`` column.  Centre alignments
    (``\an2/5/8``, legacy ``\a2/6/10``) are untouched.

    The function is a string-level rewrite — it doesn't validate ASS
    structure, so an unrelated ``Style:`` row outside ``[V4+ Styles]``
    won't be touched (the column count would be wrong) but a malformed
    file won't crash either.
    """
    def _flip_an(match: re.Match[str]) -> str:
        digit = match.group(1)
        return r"\an" + _ASS_AN_MIRROR.get(digit, digit)

    def _flip_legacy(match: re.Match[str]) -> str:
        digit = match.group(1)
        return r"\a" + _ASS_LEGACY_MIRROR.get(digit, digit)

    out_lines: list[str] = []
    for line in ass_text.splitlines(keepends=True):
        # Override-tag rewrite applies to any line that may carry tags.
        new_line = _ASS_ALIGN_AN_RE.sub(_flip_an, line)
        new_line = _ASS_ALIGN_LEGACY_RE.sub(_flip_legacy, new_line)
        # Style row: rewrite the Alignment column when the row matches
        # the canonical libass Format (10 fixed fields up to Alignment +
        # 13 trailing fields = 23 columns total).  We only touch rows
        # that look like real Style rows to avoid corrupting anything.
        stripped = new_line.lstrip()
        if stripped.lower().startswith("style:"):
            prefix_len = len(new_line) - len(stripped)
            after_kw = stripped.split(":", 1)[1]
            cols = after_kw.split(",")
            if len(cols) > _ASS_STYLE_ALIGNMENT_INDEX:
                col = cols[_ASS_STYLE_ALIGNMENT_INDEX].strip()
                mirrored = _ASS_AN_MIRROR.get(col)
                if mirrored is not None:
                    cols[_ASS_STYLE_ALIGNMENT_INDEX] = (
                        cols[_ASS_STYLE_ALIGNMENT_INDEX].replace(col, mirrored, 1)
                    )
                    rebuilt = "Style:" + ",".join(cols)
                    new_line = " " * prefix_len + rebuilt
        out_lines.append(new_line)
    return "".join(out_lines)

# Regex for SRT/VTT timestamp line: 00:00:01,000 --> 00:00:04,000
_TIMESTAMP_RE = re.compile(r"\d{1,2}:\d{2}:\d{2}[.,]\d{2,3}\s*-->")


# ── Data Model ───────────────────────────────────────────────────────


@dataclass
class SubtitleEntry:
    """A single subtitle cue with timing metadata and translatable text.

    Attributes:
        index: Sequential position (0-based).
        start: Start timestamp as the original raw string.
        end: End timestamp as the original raw string.
        text: Translatable text (override tags stripped for ASS/SSA).
        raw_text: Original text before tag stripping (ASS/SSA only).
        metadata: Format-specific extra data (cue id, cue settings, etc.).
    """

    index: int
    start: str
    end: str
    text: str
    raw_text: str = ""
    metadata: dict[str, str] = field(default_factory=dict)


# ── Helpers ──────────────────────────────────────────────────────────


def is_subtitle_format(suffix: str) -> bool:
    """Returns True if *suffix* is a supported subtitle extension."""
    return suffix in _SUBTITLE_EXTENSIONS


# ── SRT ──────────────────────────────────────────────────────────────


def parse_srt(content: str) -> tuple[list[SubtitleEntry], None]:
    """Parses an SRT file into subtitle entries.

    Args:
        content: Raw SRT file content.

    Returns:
        Tuple of (entries, None).  The second element is always ``None``
        because SRT needs no extra data for serialization.
    """
    content = strip_bom(content)
    # Normalize Windows/Mac line endings to Unix
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    # Strip only leading/trailing newlines, preserving internal whitespace
    content = content.strip("\n")
    # Split on one or more blank lines
    blocks = re.split(r"\n\n+", content)
    entries: list[SubtitleEntry] = []

    entry_idx = 0
    for block in blocks:
        lines = block.strip("\n").splitlines()
        if len(lines) < 2:  # noqa: PLR2004
            continue

        # Find the timestamp line (might be line 0 or line 1)
        ts_line_idx = -1
        for i, line in enumerate(lines):
            if _TIMESTAMP_RE.search(line):
                ts_line_idx = i
                break

        if ts_line_idx < 0:
            continue  # Not a valid cue block

        # Parse timestamp: "start --> end"
        ts_parts = lines[ts_line_idx].split("-->")
        if len(ts_parts) != 2:  # noqa: PLR2004
            continue

        start = ts_parts[0].strip()
        end = ts_parts[1].strip()
        text = "\n".join(lines[ts_line_idx + 1 :])

        if not text.strip():
            continue

        entries.append(
            SubtitleEntry(
                index=entry_idx,
                start=start,
                end=end,
                text=text,
            ),
        )
        entry_idx += 1

    return entries, None


def serialize_srt(entries: list[SubtitleEntry], _format_data: None = None) -> str:
    """Reconstructs an SRT file from subtitle entries.

    Args:
        entries: Subtitle entries with (possibly translated) text.
        _format_data: Unused — present for dispatcher signature consistency.

    Returns:
        Complete SRT file content.
    """
    parts: list[str] = []
    for seq, entry in enumerate(entries, start=1):
        parts.append(
            f"{seq}\n{entry.start} --> {entry.end}\n{entry.text}\n",
        )
    return "\n".join(parts)


# ── VTT (WebVTT) ────────────────────────────────────────────────────


def _is_vtt_header_block(text: str) -> bool:
    """Returns True if *text* is a VTT header/meta block (WEBVTT, NOTE, STYLE)."""
    return (
        text.startswith("WEBVTT") or text.startswith("NOTE") or text.startswith("STYLE")
    )


def parse_vtt(content: str) -> tuple[list[SubtitleEntry], str]:
    """Parses a WebVTT file into subtitle entries.

    Preserves the WEBVTT header, NOTE comments, and STYLE blocks in
    *header* so they can be restored during serialization.

    Args:
        content: Raw VTT file content.

    Returns:
        Tuple of (entries, header).  *header* includes everything
        before the first cue (WEBVTT line, NOTEs, STYLEs).
    """
    content = strip_bom(content)
    # Normalize Windows/Mac line endings to Unix
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n\n+", content.strip())

    header_parts: list[str] = []
    entries: list[SubtitleEntry] = []
    cue_idx = 0

    for block in blocks:
        stripped = block.strip()

        # WEBVTT header, NOTE comments, STYLE blocks → preserve
        if _is_vtt_header_block(stripped):
            header_parts.append(stripped)
            continue

        # Cue block: optional id, timestamp line (with optional settings), text
        lines = stripped.splitlines()
        if not lines:
            continue

        # Determine which line has the timestamp
        ts_line_idx = -1
        for i, line in enumerate(lines):
            if _TIMESTAMP_RE.search(line):
                ts_line_idx = i
                break

        if ts_line_idx < 0:
            # Not a cue — preserve as header material
            header_parts.append(stripped)
            continue

        # Optional cue identifier (line before timestamp)
        cue_id = ""
        if ts_line_idx > 0:
            cue_id = lines[0].strip()

        # Parse timestamp + optional settings
        ts_line = lines[ts_line_idx]
        ts_parts = ts_line.split("-->")
        if len(ts_parts) != 2:  # noqa: PLR2004
            continue

        start = ts_parts[0].strip()
        # End timestamp may be followed by cue settings
        end_and_settings = ts_parts[1].strip()
        # Split: first token is end timestamp, rest are settings
        end_tokens = end_and_settings.split(None, 1)
        end_ts = end_tokens[0] if end_tokens else end_and_settings
        cue_settings = end_tokens[1] if len(end_tokens) > 1 else ""

        text = "\n".join(lines[ts_line_idx + 1 :])
        if not text.strip():
            continue

        meta: dict[str, str] = {}
        if cue_id:
            meta["cue_id"] = cue_id
        if cue_settings:
            meta["cue_settings"] = cue_settings

        entries.append(
            SubtitleEntry(
                index=cue_idx,
                start=start,
                end=end_ts,
                text=text,
                metadata=meta,
            ),
        )
        cue_idx += 1

    header = "\n\n".join(header_parts)
    return entries, header


def serialize_vtt(
    entries: list[SubtitleEntry],
    header: str = "",
) -> str:
    """Reconstructs a WebVTT file from entries and the original header.

    Args:
        entries: Subtitle entries with (possibly translated) text.
        header: Original WEBVTT header block (with NOTEs/STYLEs).

    Returns:
        Complete VTT file content.
    """
    parts: list[str] = []
    if header:
        parts.append(header)

    for entry in entries:
        cue_id = entry.metadata.get("cue_id", "")
        cue_settings = entry.metadata.get("cue_settings", "")

        ts_line = f"{entry.start} --> {entry.end}"
        if cue_settings:
            ts_line += f" {cue_settings}"

        if cue_id:
            parts.append(f"{cue_id}\n{ts_line}\n{entry.text}")
        else:
            parts.append(f"{ts_line}\n{entry.text}")

    return "\n\n".join(parts) + "\n"


# ── ASS / SSA ────────────────────────────────────────────────────────


def _strip_ass_tags(text: str) -> str:
    r"""Strips ASS/SSA override tags, preserving visible text.

    Tags like ``{\b1}``, ``{\i1}``, ``{\pos(320,240)}`` are removed.

    Args:
        text: Raw ASS dialogue text.

    Returns:
        Text with override tags removed.
    """
    return _ASS_OVERRIDE_TAG_RE.sub("", text)


def _restore_ass_tags(original: str, translated: str) -> str:
    """Restores leading ASS override tags from *original* onto *translated*.

    Mid-text tags cannot be reliably repositioned after translation, so
    only contiguous leading tags are restored.

    Args:
        original: Original text with override tags.
        translated: Translated text without tags.

    Returns:
        Translated text prefixed with the original's leading tags.
    """
    # Collect all leading override tags
    leading_tags: list[str] = []
    pos = 0
    while pos < len(original):
        m = _ASS_OVERRIDE_TAG_RE.match(original, pos)
        if m:
            leading_tags.append(m.group())
            pos = m.end()
        else:
            break

    if not leading_tags:
        return translated
    return "".join(leading_tags) + translated


def parse_ass(content: str) -> tuple[list[SubtitleEntry], list[str]]:
    """Parses an ASS/SSA file into subtitle entries.

    Only ``Dialogue:`` lines in the ``[Events]`` section are treated as
    translatable.  All other content (sections, comments, styles) is
    preserved verbatim in *preserved_lines* for later serialization.

    Args:
        content: Raw ASS/SSA file content.

    Returns:
        Tuple of (entries, preserved_lines).  Dialogue text positions
        in *preserved_lines* are replaced with ``__SUB_N__`` placeholders
        where *N* is the entry index.
    """
    content = strip_bom(content)
    lines = content.splitlines()
    preserved: list[str] = []
    entries: list[SubtitleEntry] = []
    in_events = False
    format_fields: list[str] = []
    text_field_idx = -1
    entry_idx = 0

    for line in lines:
        stripped = line.strip()

        # Detect section headers
        if stripped.startswith("[") and stripped.endswith("]"):
            in_events = stripped.lower() == "[events]"
            preserved.append(line)
            continue

        # Inside [Events]: look for Format and Dialogue lines
        if in_events:
            if stripped.lower().startswith("format:"):
                # Parse field names to find the Text field position
                fields_part = stripped.split(":", 1)[1]
                format_fields = [f.strip() for f in fields_part.split(",")]
                text_field_idx = next(
                    (i for i, f in enumerate(format_fields) if f.lower() == "text"),
                    -1,
                )
                preserved.append(line)
                continue

            if stripped.startswith("Dialogue:") and text_field_idx >= 0:
                # Split on commas up to (text_field_idx) times to keep
                # commas inside the Text field intact
                after_prefix = stripped.split(":", 1)[1]
                parts = after_prefix.split(",", text_field_idx)

                if len(parts) > text_field_idx:
                    raw_text = parts[text_field_idx].strip()
                    clean_text = _strip_ass_tags(raw_text)

                    # Build the prefix (everything before the text field)
                    prefix = ",".join(parts[:text_field_idx])
                    placeholder = f"__SUB_{entry_idx}__"
                    preserved.append(f"Dialogue:{prefix},{placeholder}")

                    # Parse timestamps from the fixed fields
                    # Standard ASS Format: Layer, Start, End, Style, Name,
                    # MarginL, MarginR, MarginV, Effect, Text
                    field_values = parts[:text_field_idx]
                    start_ts = field_values[1].strip() if len(field_values) > 1 else ""
                    end_ts = (
                        field_values[2].strip()  # noqa: PLR2004
                        if len(field_values) > 2  # noqa: PLR2004
                        else ""
                    )

                    entries.append(
                        SubtitleEntry(
                            index=entry_idx,
                            start=start_ts,
                            end=end_ts,
                            text=clean_text,
                            raw_text=raw_text,
                        ),
                    )
                    entry_idx += 1
                    continue

        # Everything else: preserve verbatim
        preserved.append(line)

    return entries, preserved


def serialize_ass(
    entries: list[SubtitleEntry],
    preserved_lines: list[str],
) -> str:
    """Reconstructs an ASS/SSA file by injecting translated text.

    Replaces ``__SUB_N__`` placeholders in *preserved_lines* with the
    translated text for each entry, restoring any leading override tags
    from the original.

    Args:
        entries: Subtitle entries with translated text.
        preserved_lines: Lines with placeholders from ``parse_ass()``.

    Returns:
        Complete ASS/SSA file content.
    """
    # Build a lookup: placeholder → translated text with tags restored
    replacements: dict[str, str] = {}
    for entry in entries:
        placeholder = f"__SUB_{entry.index}__"
        restored = _restore_ass_tags(entry.raw_text, entry.text)
        replacements[placeholder] = restored

    result_lines: list[str] = []
    for line in preserved_lines:
        resolved = line
        for placeholder, text in replacements.items():
            if placeholder in resolved:
                resolved = resolved.replace(placeholder, text)
        result_lines.append(resolved)

    return "\n".join(result_lines) + "\n"


# ── Unified Dispatchers ─────────────────────────────────────────────


def parse_subtitle(
    content: str,
    suffix: str,
) -> tuple[list[SubtitleEntry], object]:
    """Dispatches to the format-specific subtitle parser.

    Args:
        content: Raw file content.
        suffix: Lowercase file extension (e.g. ``".srt"``).

    Returns:
        Tuple of (entries, format_data) where *format_data* is
        whatever the format-specific serializer needs.

    Raises:
        ValueError: If the extension is not a supported subtitle format.
    """
    if suffix == ".srt":
        return parse_srt(content)
    if suffix == ".vtt":
        return parse_vtt(content)
    if suffix in (".ass", ".ssa"):
        return parse_ass(content)
    msg = f"Unsupported subtitle format: {suffix}"
    raise ValueError(msg)


def serialize_subtitle(
    entries: list[SubtitleEntry],
    format_data: object,
    suffix: str,
) -> str:
    """Dispatches to the format-specific subtitle serializer.

    Args:
        entries: Subtitle entries with translated text.
        format_data: Format-specific data from ``parse_subtitle()``.
        suffix: Lowercase file extension.

    Returns:
        Complete file content.

    Raises:
        ValueError: If the extension is not a supported subtitle format.
    """
    if suffix == ".srt":
        return serialize_srt(entries, format_data)
    if suffix == ".vtt":
        return serialize_vtt(entries, format_data)
    if suffix in (".ass", ".ssa"):
        return serialize_ass(entries, format_data)
    msg = f"Unsupported subtitle format: {suffix}"
    raise ValueError(msg)
