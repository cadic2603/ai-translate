"""Localization file parsing and serialization utilities.

Supports PO/POT (GNU Gettext) and XLIFF/XLF (OASIS, versions 1.2 and 2.0).
Each format has a parse/serialize pair.  The unified ``parse_localization``
/ ``serialize_localization`` dispatchers select the correct pair based on
file extension.
"""

import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any

from src.utils.text_utils import strip_bom

logger = logging.getLogger("localization_utils")

# ── Constants ────────────────────────────────────────────────────────

_LOCALIZATION_EXTENSIONS: set[str] = {".po", ".pot", ".xliff", ".xlf"}
_PO_EXTENSIONS: set[str] = {".po", ".pot"}
_XLIFF_EXTENSIONS: set[str] = {".xliff", ".xlf"}

_XLIFF_NS_12 = "urn:oasis:names:tc:xliff:document:1.2"
_XLIFF_NS_20 = "urn:oasis:names:tc:xliff:document:2.0"

# PO keyword regex: matches msgid, msgstr, msgctxt, msgid_plural, msgstr[N]
_PO_KEYWORD_RE = re.compile(
    r'^(msgctxt|msgid_plural|msgid|msgstr(?:\[\d+\])?)\s+"(.*)"$',
)

# Continuation line: a bare quoted string
_PO_CONTINUATION_RE = re.compile(r'^"(.*)"$')


# ── Data Model ───────────────────────────────────────────────────────


@dataclass
class LocalizationEntry:
    """A single translatable localization string.

    Attributes:
        index: Sequential position (0-based).
        msgid: Source text (the string to translate).
        msgstr: Current translation (may be empty).
        context: Optional disambiguation context.
        metadata: Format-specific extra data (comments, flags, plurals, etc.).
    """

    index: int
    msgid: str
    msgstr: str = ""
    context: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


# ── Helpers ──────────────────────────────────────────────────────────


def is_localization_format(suffix: str) -> bool:
    """Returns True if *suffix* is a supported localization extension."""
    return suffix in _LOCALIZATION_EXTENSIONS


# ── PO escape handling ───────────────────────────────────────────────

_PO_UNESCAPE_MAP: dict[str, str] = {
    "\\n": "\n",
    "\\t": "\t",
    '\\"': '"',
    "\\\\": "\\",
}

_PO_ESCAPE_MAP: dict[str, str] = {
    "\\": "\\\\",
    '"': '\\"',
    "\n": "\\n",
    "\t": "\\t",
}


def _unescape_po(text: str) -> str:
    """Unescapes PO/Gettext C-style escape sequences."""
    result: list[str] = []
    i = 0
    while i < len(text):
        if text[i] == "\\" and i + 1 < len(text):
            pair = text[i : i + 2]
            if pair in _PO_UNESCAPE_MAP:
                result.append(_PO_UNESCAPE_MAP[pair])
                i += 2
                continue
        result.append(text[i])
        i += 1
    return "".join(result)


def _escape_po(text: str) -> str:
    """Escapes a string for PO/Gettext output."""
    result: list[str] = []
    for ch in text:
        if ch in _PO_ESCAPE_MAP:
            result.append(_PO_ESCAPE_MAP[ch])
        else:
            result.append(ch)
    return "".join(result)


# ── PO / POT ────────────────────────────────────────────────────────


def _parse_po_block(
    lines: list[str],
) -> tuple[list[str], dict[str, str]]:
    """Parses a single PO block into comments and keyword values.

    Args:
        lines: Raw text lines of a single PO block.

    Returns:
        Tuple of (comments, keywords) where comments is a list of
        ``#``-prefixed lines and keywords maps PO directives to their
        unescaped string values.
    """
    comments: list[str] = []
    keywords: dict[str, str] = {}
    current_keyword: str = ""

    for line in lines:
        if line.startswith("#"):
            comments.append(line)
        elif kw_match := _PO_KEYWORD_RE.match(line):
            current_keyword = kw_match.group(1)
            keywords[current_keyword] = _unescape_po(kw_match.group(2))
        elif (cont_match := _PO_CONTINUATION_RE.match(line)) and current_keyword:
            keywords[current_keyword] += _unescape_po(cont_match.group(1))

    return comments, keywords


def _extract_po_flags(comments: list[str]) -> set[str]:
    """Extracts PO flags from ``#,`` comment lines."""
    flags: set[str] = set()
    for comment in comments:
        if comment.startswith("#,"):
            flag_str = comment[2:].strip()
            flags.update(f.strip() for f in flag_str.split(","))
    return flags


def parse_po(content: str) -> tuple[list[LocalizationEntry], list[str]]:
    """Parses a PO/POT file into localization entries.

    The header entry (first entry with empty ``msgid``) is preserved
    verbatim in *header_lines* and excluded from the returned entries.

    Args:
        content: Raw PO/POT file content.

    Returns:
        Tuple of (entries, header_lines).
    """
    content = strip_bom(content)
    blocks = re.split(r"\n\n+", content.strip())

    header_lines: list[str] = []
    entries: list[LocalizationEntry] = []
    entry_idx = 0

    for block in blocks:
        lines = block.strip().splitlines()
        if not lines:
            continue

        # Delegate line-level parsing to helper
        comments, keywords = _parse_po_block(lines)

        # Must have at least msgid
        if "msgid" not in keywords:
            continue

        msgid = keywords.get("msgid", "")

        # Header entry: msgid is empty
        if not msgid and not entries and not header_lines:
            header_lines = [block]
            continue

        # Skip entries with empty msgid (shouldn't happen after header)
        if not msgid:
            continue

        # Build metadata
        flags = _extract_po_flags(comments)
        meta: dict[str, Any] = {
            "comments": comments,
            "flags": flags,
        }

        # Handle plural forms
        if "msgid_plural" in keywords:
            meta["msgid_plural"] = keywords["msgid_plural"]
            # Collect msgstr[N] entries
            msgstr_plural: dict[int, str] = {}
            for key, value in keywords.items():
                if key.startswith("msgstr["):
                    idx_str = key[7:-1]  # Extract N from msgstr[N]
                    msgstr_plural[int(idx_str)] = value
            meta["msgstr_plural"] = msgstr_plural

        msgctxt = keywords.get("msgctxt", "")
        msgstr = keywords.get("msgstr", "")

        entries.append(
            LocalizationEntry(
                index=entry_idx,
                msgid=msgid,
                msgstr=msgstr,
                context=msgctxt,
                metadata=meta,
            ),
        )
        entry_idx += 1

    return entries, header_lines


def serialize_po(
    entries: list[LocalizationEntry],
    header_lines: list[str],
) -> str:
    """Reconstructs a PO file from entries and the original header.

    Args:
        entries: Localization entries with translated text.
        header_lines: Original header block (preserved verbatim).

    Returns:
        Complete PO file content.
    """
    parts: list[str] = []

    # Write header first
    if header_lines:
        parts.extend(header_lines)

    for entry in entries:
        block_lines: list[str] = []

        # Restore comments (remove fuzzy flag since we have a new translation)
        comments: list[str] = entry.metadata.get("comments", [])
        flags: set[str] = entry.metadata.get("flags", set()).copy()
        flags.discard("fuzzy")

        for comment in comments:
            if comment.startswith("#,"):
                # Rebuild flags line without fuzzy
                if flags:
                    block_lines.append(f"#, {', '.join(sorted(flags))}")
                # Skip original #, line (replaced above or dropped)
            else:
                block_lines.append(comment)

        # msgctxt
        if entry.context:
            block_lines.append(f'msgctxt "{_escape_po(entry.context)}"')

        # msgid
        block_lines.append(f'msgid "{_escape_po(entry.msgid)}"')

        # Plural forms
        if "msgid_plural" in entry.metadata:
            block_lines.append(
                f'msgid_plural "{_escape_po(entry.metadata["msgid_plural"])}"',
            )
            msgstr_plural: dict[int, str] = entry.metadata.get(
                "msgstr_plural",
                {},
            )
            # Write msgstr[0], msgstr[1], ...
            max_idx = max(msgstr_plural.keys()) if msgstr_plural else 1
            for i in range(max_idx + 1):
                val = msgstr_plural.get(i, "")
                block_lines.append(f'msgstr[{i}] "{_escape_po(val)}"')
        else:
            # Regular singular msgstr
            block_lines.append(f'msgstr "{_escape_po(entry.msgstr)}"')

        parts.append("\n".join(block_lines))

    return "\n\n".join(parts) + "\n"


# ── XLIFF ────────────────────────────────────────────────────────────


def _detect_xliff_version(root: ET.Element) -> str:
    """Detects XLIFF version from the root element.

    Args:
        root: Parsed XML root element.

    Returns:
        ``"1.2"`` or ``"2.0"``.
    """
    # Check namespace in tag
    tag = root.tag
    if _XLIFF_NS_20 in tag:
        return "2.0"
    if _XLIFF_NS_12 in tag:
        return "1.2"
    # Fall back to version attribute
    version = root.get("version", "1.2")
    return "2.0" if version.startswith("2") else "1.2"


def _parse_xliff_12(
    root: ET.Element,
) -> list[LocalizationEntry]:
    """Parses XLIFF 1.2 trans-units into entries."""
    ns = {"x": _XLIFF_NS_12}
    entries: list[LocalizationEntry] = []
    entry_idx = 0

    for tu in root.iter(f"{{{_XLIFF_NS_12}}}trans-unit"):
        # Skip non-translatable units
        if tu.get("translate", "yes").lower() == "no":
            continue

        source_elem = tu.find("x:source", ns)
        if source_elem is None or not (source_elem.text or "").strip():
            continue

        target_elem = tu.find("x:target", ns)
        note_elem = tu.find("x:note", ns)

        msgid = source_elem.text or ""
        msgstr = (target_elem.text or "") if target_elem is not None else ""
        context = (note_elem.text or "") if note_elem is not None else ""

        meta: dict[str, Any] = {
            "unit_id": tu.get("id", ""),
        }

        entries.append(
            LocalizationEntry(
                index=entry_idx,
                msgid=msgid,
                msgstr=msgstr,
                context=context,
                metadata=meta,
            ),
        )
        entry_idx += 1

    return entries


def _inject_xliff_12(
    root: ET.Element,
    translations: dict[str, str],
) -> None:
    """Injects translations into XLIFF 1.2 tree in-place."""
    ns = {"x": _XLIFF_NS_12}

    for tu in root.iter(f"{{{_XLIFF_NS_12}}}trans-unit"):
        if tu.get("translate", "yes").lower() == "no":
            continue

        unit_id = tu.get("id", "")
        if unit_id not in translations:
            continue

        target_elem = tu.find("x:target", ns)
        if target_elem is None:
            # Create <target> element after <source>
            source_elem = tu.find("x:source", ns)
            target_elem = ET.SubElement(tu, f"{{{_XLIFF_NS_12}}}target")
            if source_elem is not None:
                # Insert after source
                children = list(tu)
                src_idx = children.index(source_elem)
                tu.remove(target_elem)
                tu.insert(src_idx + 1, target_elem)

        target_elem.text = translations[unit_id]
        target_elem.set("state", "translated")


def _parse_xliff_20(
    root: ET.Element,
) -> list[LocalizationEntry]:
    """Parses XLIFF 2.0 units/segments into entries."""
    entries: list[LocalizationEntry] = []
    entry_idx = 0

    for unit in root.iter(f"{{{_XLIFF_NS_20}}}unit"):
        # Skip non-translatable units
        if unit.get("translate", "yes").lower() == "no":
            continue

        unit_id = unit.get("id", "")

        for segment in unit.iter(f"{{{_XLIFF_NS_20}}}segment"):
            source_elem = segment.find(f"{{{_XLIFF_NS_20}}}source")
            if source_elem is None or not (source_elem.text or "").strip():
                continue

            target_elem = segment.find(f"{{{_XLIFF_NS_20}}}target")

            msgid = source_elem.text or ""
            msgstr = (target_elem.text or "") if target_elem is not None else ""

            meta: dict[str, Any] = {
                "unit_id": unit_id,
            }

            entries.append(
                LocalizationEntry(
                    index=entry_idx,
                    msgid=msgid,
                    msgstr=msgstr,
                    metadata=meta,
                ),
            )
            entry_idx += 1

    return entries


def _inject_xliff_20(
    root: ET.Element,
    translations: dict[str, str],
) -> None:
    """Injects translations into XLIFF 2.0 tree in-place."""
    for unit in root.iter(f"{{{_XLIFF_NS_20}}}unit"):
        if unit.get("translate", "yes").lower() == "no":
            continue

        unit_id = unit.get("id", "")
        if unit_id not in translations:
            continue

        for segment in unit.iter(f"{{{_XLIFF_NS_20}}}segment"):
            source_elem = segment.find(f"{{{_XLIFF_NS_20}}}source")
            if source_elem is None or not (source_elem.text or "").strip():
                continue

            target_elem = segment.find(f"{{{_XLIFF_NS_20}}}target")
            if target_elem is None:
                target_elem = ET.SubElement(
                    segment,
                    f"{{{_XLIFF_NS_20}}}target",
                )
                # Insert after source
                children = list(segment)
                src_idx = children.index(source_elem)
                segment.remove(target_elem)
                segment.insert(src_idx + 1, target_elem)

            target_elem.text = translations[unit_id]


def parse_xliff(content: str) -> tuple[list[LocalizationEntry], ET.Element]:
    """Parses an XLIFF file (1.2 or 2.0) into localization entries.

    Args:
        content: Raw XLIFF file content.

    Returns:
        Tuple of (entries, root_element).  The root element is the
        parsed XML tree that will be modified in-place for serialization.
    """
    root = ET.fromstring(content)
    version = _detect_xliff_version(root)

    # Register only the matching namespace to avoid ns0: prefix in output.
    # Registering both would cause the second to overwrite the first,
    # corrupting the non-matching version with ns0: prefixes.
    if version == "2.0":
        ET.register_namespace("", _XLIFF_NS_20)
    else:
        ET.register_namespace("", _XLIFF_NS_12)

    entries = _parse_xliff_20(root) if version == "2.0" else _parse_xliff_12(root)

    return entries, root


def serialize_xliff(
    entries: list[LocalizationEntry],
    root: ET.Element,
) -> str:
    """Reconstructs an XLIFF file by injecting translations into the tree.

    Args:
        entries: Localization entries with translated text.
        root: Parsed XML root element from ``parse_xliff()``.

    Returns:
        Complete XLIFF file content.
    """
    # Build translation lookup: unit_id → translated text
    translations: dict[str, str] = {}
    for entry in entries:
        unit_id = entry.metadata.get("unit_id", "")
        if unit_id:
            translations[unit_id] = entry.msgstr

    version = _detect_xliff_version(root)
    if version == "2.0":
        _inject_xliff_20(root, translations)
    else:
        _inject_xliff_12(root, translations)

    return ET.tostring(root, encoding="unicode", xml_declaration=True) + "\n"


# ── Unified Dispatchers ─────────────────────────────────────────────


def parse_localization(
    content: str,
    suffix: str,
) -> tuple[list[LocalizationEntry], object]:
    """Dispatches to the format-specific localization parser.

    Args:
        content: Raw file content.
        suffix: Lowercase file extension (e.g. ``".po"``).

    Returns:
        Tuple of (entries, format_data) where *format_data* is
        whatever the format-specific serializer needs.

    Raises:
        ValueError: If the extension is not a supported localization format.
    """
    if suffix in _PO_EXTENSIONS:
        return parse_po(content)
    if suffix in _XLIFF_EXTENSIONS:
        return parse_xliff(content)
    msg = f"Unsupported localization format: {suffix}"
    raise ValueError(msg)


def serialize_localization(
    entries: list[LocalizationEntry],
    format_data: object,
    suffix: str,
) -> str:
    """Dispatches to the format-specific localization serializer.

    Args:
        entries: Localization entries with translated text.
        format_data: Format-specific data from ``parse_localization()``.
        suffix: Lowercase file extension.

    Returns:
        Complete file content.

    Raises:
        ValueError: If the extension is not a supported localization format.
    """
    if suffix in _PO_EXTENSIONS:
        return serialize_po(entries, format_data)
    if suffix in _XLIFF_EXTENSIONS:
        return serialize_xliff(entries, format_data)
    msg = f"Unsupported localization format: {suffix}"
    raise ValueError(msg)
