"""Key-value file parsing and serialization utilities.

Supports YAML (.yaml, .yml), Java Properties (.properties), and Apple
Strings (.strings).  Each format has a parse/serialize pair.  The unified
``parse_keyvalue`` / ``serialize_keyvalue`` dispatchers select the correct
pair based on file extension.
"""

import copy
import logging
import re

import yaml

from src.utils.localization_utils import LocalizationEntry
from src.utils.text_utils import strip_bom

logger = logging.getLogger("keyvalue_utils")

# ── Constants ────────────────────────────────────────────────────────

_KEYVALUE_EXTENSIONS: set[str] = {
    ".yaml",
    ".yml",
    ".properties",
    ".strings",
}
_YAML_EXTENSIONS: set[str] = {".yaml", ".yml"}


# ── Helpers ──────────────────────────────────────────────────────────


def is_keyvalue_format(suffix: str) -> bool:
    """Returns True if *suffix* is a supported key-value extension."""
    return suffix in _KEYVALUE_EXTENSIONS


# ── YAML ─────────────────────────────────────────────────────────────


def _extract_yaml_strings(
    data: object,
    path: tuple[str | int, ...] = (),
) -> list[tuple[tuple[str | int, ...], str]]:
    """Recursively extracts string leaf values from a YAML structure.

    Args:
        data: Parsed YAML data (dict, list, or scalar).
        path: Current key path (tuple of keys/indices).

    Returns:
        List of (key_path, string_value) pairs.
    """
    results: list[tuple[tuple[str | int, ...], str]] = []

    if isinstance(data, dict):
        for key, value in data.items():
            results.extend(_extract_yaml_strings(value, (*path, key)))
    elif isinstance(data, list):
        for idx, item in enumerate(data):
            results.extend(_extract_yaml_strings(item, (*path, idx)))
    elif isinstance(data, str) and data.strip():
        results.append((path, data))

    return results


def _inject_yaml_string(
    data: object,
    path: tuple[str | int, ...],
    value: str,
) -> None:
    """Sets a value at a nested path in a YAML structure in-place.

    Args:
        data: Parsed YAML data (dict or list).
        path: Key path to the target leaf.
        value: New string value to set.
    """
    current = data
    for key in path[:-1]:
        current = current[key]  # type: ignore[index]
    current[path[-1]] = value  # type: ignore[index]


def parse_yaml(
    content: str,
) -> tuple[list[LocalizationEntry], object]:
    """Parses a YAML file into localization entries.

    Only string leaf values are extracted.  Numbers, booleans, and
    null values are skipped.

    Args:
        content: Raw YAML file content.

    Returns:
        Tuple of (entries, parsed_data).
    """
    content = strip_bom(content)
    data = yaml.safe_load(content)

    if data is None:
        return [], None

    pairs = _extract_yaml_strings(data)
    entries: list[LocalizationEntry] = []

    for idx, (path, string_val) in enumerate(pairs):
        entries.append(
            LocalizationEntry(
                index=idx,
                msgid=string_val,
                metadata={"path": path},
            ),
        )

    return entries, data


def serialize_yaml(
    entries: list[LocalizationEntry],
    original_data: object,
) -> str:
    """Reconstructs a YAML file with translated values.

    Args:
        entries: Localization entries with translated text.
        original_data: Original parsed YAML structure from ``parse_yaml()``.

    Returns:
        Complete YAML file content.
    """
    data = copy.deepcopy(original_data)

    for entry in entries:
        path = entry.metadata.get("path")
        if path is not None and len(path) > 0:
            _inject_yaml_string(data, path, entry.msgstr)
        elif path is not None:
            # Root scalar string — replace directly
            data = entry.msgstr

    return yaml.safe_dump(
        data,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    )


# ── Properties escape handling ───────────────────────────────────────


def _unescape_properties(text: str) -> str:
    """Unescapes a Java Properties value string."""
    result: list[str] = []
    i = 0
    while i < len(text):
        if text[i] == "\\" and i + 1 < len(text):
            nxt = text[i + 1]
            if nxt == "n":
                result.append("\n")
                i += 2
            elif nxt == "t":
                result.append("\t")
                i += 2
            elif nxt == "\\":
                result.append("\\")
                i += 2
            elif nxt == "u" and i + 5 < len(text):
                # \uXXXX unicode escape
                hex_str = text[i + 2 : i + 6]
                try:
                    result.append(chr(int(hex_str, 16)))
                    i += 6
                except ValueError:
                    result.append(text[i])
                    i += 1
            else:
                # \= \: \<space> or other — unescape to literal
                result.append(nxt)
                i += 2
        else:
            result.append(text[i])
            i += 1
    return "".join(result)


def _escape_properties_value(text: str) -> str:
    """Escapes a string for Java Properties value output."""
    result: list[str] = []
    for ch in text:
        if ch == "\\":
            result.append("\\\\")
        elif ch == "\n":
            result.append("\\n")
        elif ch == "\t":
            result.append("\\t")
        else:
            result.append(ch)
    return "".join(result)


# ── Java Properties ─────────────────────────────────────────────────


def _join_continuation_lines(lines: list[str]) -> list[str]:
    """Joins backslash-continued lines in a Properties file.

    Args:
        lines: Raw lines from the file.

    Returns:
        Logical lines with continuations merged.
    """
    result: list[str] = []
    current = ""
    for line in lines:
        if current:
            # Continuation: strip leading whitespace from the continued line
            current += line.lstrip()
        else:
            current = line

        # Count trailing backslashes to detect continuation
        trail = len(current) - len(current.rstrip("\\"))
        if trail % 2 == 1:
            # Odd trailing backslashes → last one is continuation marker
            current = current[:-1]
        else:
            result.append(current)
            current = ""

    # Handle file ending with continuation
    if current:
        result.append(current)

    return result


def _parse_properties_line(
    line: str,
) -> tuple[str, str, str] | None:
    """Parses a single Properties key-value line.

    Args:
        line: A logical (continuation-joined) line.

    Returns:
        Tuple of (key, separator, value) or None if not a kv line.
    """
    # Find the first unescaped separator (= : or whitespace)
    i = 0
    key_chars: list[str] = []
    while i < len(line):
        ch = line[i]
        if ch == "\\" and i + 1 < len(line):
            # Escaped character in key — keep as-is
            key_chars.append(ch)
            key_chars.append(line[i + 1])
            i += 2
            continue
        if ch in ("=", ":"):
            separator = ch
            value = line[i + 1 :].lstrip()
            return "".join(key_chars), separator, value
        if ch in (" ", "\t"):
            # Whitespace separator — look ahead for = or :
            ws_start = i
            while i < len(line) and line[i] in (" ", "\t"):
                i += 1
            if i < len(line) and line[i] in ("=", ":"):
                separator = line[ws_start : i + 1]
                value = line[i + 1 :].lstrip()
                return "".join(key_chars), separator, value
            # Pure whitespace separator
            separator = line[ws_start:i]
            value = line[i:]
            return "".join(key_chars), separator, value
        key_chars.append(ch)
        i += 1

    # Key with no value
    if key_chars:
        return "".join(key_chars), "=", ""
    return None


def parse_properties(
    content: str,
) -> tuple[list[LocalizationEntry], list[tuple[str, object]]]:
    """Parses a Java Properties file into localization entries.

    Preserves comments, blank lines, and key ordering via a structure
    list that records the sequence of elements.

    Args:
        content: Raw Properties file content.

    Returns:
        Tuple of (entries, structure) where structure is a list of
        ``("comment", text)``, ``("blank", "")``, or ``("entry", index)``
        tuples.
    """
    content = strip_bom(content)
    raw_lines = content.splitlines()
    lines = _join_continuation_lines(raw_lines)

    entries: list[LocalizationEntry] = []
    structure: list[tuple[str, object]] = []
    entry_idx = 0

    for line in lines:
        # Blank line
        if not line.strip():
            structure.append(("blank", ""))
            continue

        # Comment line
        stripped = line.lstrip()
        if stripped.startswith("#") or stripped.startswith("!"):
            structure.append(("comment", line))
            continue

        # Key-value line
        parsed = _parse_properties_line(line)
        if parsed is None:
            continue

        key, separator, raw_value = parsed
        value = _unescape_properties(raw_value)

        entries.append(
            LocalizationEntry(
                index=entry_idx,
                msgid=value,
                metadata={
                    "key": key,
                    "separator": separator,
                },
            ),
        )
        structure.append(("entry", entry_idx))
        entry_idx += 1

    return entries, structure


def serialize_properties(
    entries: list[LocalizationEntry],
    structure: list[tuple[str, object]],
) -> str:
    """Reconstructs a Java Properties file from entries and structure.

    Args:
        entries: Localization entries with translated text.
        structure: Structure list from ``parse_properties()``.

    Returns:
        Complete Properties file content.
    """
    # Build index lookup
    entry_map: dict[int, LocalizationEntry] = {e.index: e for e in entries}
    parts: list[str] = []

    for kind, data in structure:
        if kind == "blank":
            parts.append("")
        elif kind == "comment":
            parts.append(str(data))
        elif kind == "entry":
            entry = entry_map[int(data)]  # type: ignore[arg-type]
            key = entry.metadata["key"]
            separator = entry.metadata["separator"]
            escaped_val = _escape_properties_value(entry.msgstr)
            parts.append(f"{key}{separator}{escaped_val}")

    return "\n".join(parts) + "\n"


# ── Apple Strings escape handling ────────────────────────────────────


_STRINGS_UNESCAPE_MAP: dict[str, str] = {
    '\\"': '"',
    "\\\\": "\\",
    "\\n": "\n",
    "\\t": "\t",
}


def _unescape_strings(text: str) -> str:
    """Unescapes an Apple Strings value."""
    result: list[str] = []
    i = 0
    while i < len(text):
        if text[i] == "\\" and i + 1 < len(text):
            pair = text[i : i + 2]
            if pair in _STRINGS_UNESCAPE_MAP:
                result.append(_STRINGS_UNESCAPE_MAP[pair])
                i += 2
                continue
        result.append(text[i])
        i += 1
    return "".join(result)


def _escape_strings(text: str) -> str:
    """Escapes a string for Apple Strings output."""
    result: list[str] = []
    for ch in text:
        if ch == "\\":
            result.append("\\\\")
        elif ch == '"':
            result.append('\\"')
        elif ch == "\n":
            result.append("\\n")
        elif ch == "\t":
            result.append("\\t")
        else:
            result.append(ch)
    return "".join(result)


# ── Apple Strings (.strings) ────────────────────────────────────────

# Matches: "key" = "value";
_STRINGS_ENTRY_RE = re.compile(
    r'"((?:[^"\\]|\\.)*)"\s*=\s*"((?:[^"\\]|\\.)*)"\s*;',
)


def parse_strings(
    content: str,
) -> tuple[list[LocalizationEntry], list[tuple[str, object]]]:
    """Parses an Apple Strings file into localization entries.

    Preserves comments and blank lines via a structure list.

    Args:
        content: Raw .strings file content.

    Returns:
        Tuple of (entries, structure).
    """
    content = strip_bom(content)

    entries: list[LocalizationEntry] = []
    structure: list[tuple[str, object]] = []
    entry_idx = 0

    pos = 0
    length = len(content)

    while pos < length:
        # Skip whitespace
        if content[pos] in (" ", "\t", "\r", "\n"):
            # Collect consecutive blank lines/whitespace
            ws_start = pos
            while pos < length and content[pos] in (" ", "\t", "\r", "\n"):
                pos += 1
            ws_text = content[ws_start:pos]
            # Only record if it contains newlines (meaningful whitespace)
            if "\n" in ws_text:
                structure.append(("raw", ws_text))
            continue

        # Block comment /* ... */
        if pos + 1 < length and content[pos : pos + 2] == "/*":
            end = content.find("*/", pos + 2)
            if end == -1:
                # Unterminated comment — take rest of file
                structure.append(("raw", content[pos:]))
                break
            structure.append(("raw", content[pos : end + 2]))
            pos = end + 2
            continue

        # Line comment // ...
        if pos + 1 < length and content[pos : pos + 2] == "//":
            end = content.find("\n", pos)
            if end == -1:
                structure.append(("raw", content[pos:]))
                break
            structure.append(("raw", content[pos : end + 1]))
            pos = end + 1
            continue

        # Try to match a "key" = "value"; entry
        match = _STRINGS_ENTRY_RE.match(content, pos)
        if match:
            raw_key = match.group(1)
            raw_value = match.group(2)
            key = _unescape_strings(raw_key)
            value = _unescape_strings(raw_value)

            entries.append(
                LocalizationEntry(
                    index=entry_idx,
                    msgid=value,
                    metadata={"key": key},
                ),
            )
            structure.append(("entry", entry_idx))
            entry_idx += 1
            pos = match.end()
            continue

        # Unknown content — skip to next line
        end = content.find("\n", pos)
        if end == -1:
            structure.append(("raw", content[pos:]))
            break
        structure.append(("raw", content[pos : end + 1]))
        pos = end + 1

    return entries, structure


def serialize_strings(
    entries: list[LocalizationEntry],
    structure: list[tuple[str, object]],
) -> str:
    """Reconstructs an Apple Strings file from entries and structure.

    Args:
        entries: Localization entries with translated text.
        structure: Structure list from ``parse_strings()``.

    Returns:
        Complete .strings file content.
    """
    entry_map: dict[int, LocalizationEntry] = {e.index: e for e in entries}
    parts: list[str] = []

    for kind, data in structure:
        if kind == "raw":
            parts.append(str(data))
        elif kind == "entry":
            entry = entry_map[int(data)]  # type: ignore[arg-type]
            key = _escape_strings(entry.metadata["key"])
            value = _escape_strings(entry.msgstr)
            parts.append(f'"{key}" = "{value}";')

    return "".join(parts)


# ── Unified Dispatchers ─────────────────────────────────────────────


def parse_keyvalue(
    content: str,
    suffix: str,
) -> tuple[list[LocalizationEntry], object]:
    """Dispatches to the format-specific key-value parser.

    Args:
        content: Raw file content.
        suffix: Lowercase file extension (e.g. ``".yaml"``).

    Returns:
        Tuple of (entries, format_data).

    Raises:
        ValueError: If the extension is not a supported key-value format.
    """
    if suffix in _YAML_EXTENSIONS:
        return parse_yaml(content)
    if suffix == ".properties":
        return parse_properties(content)
    if suffix == ".strings":
        return parse_strings(content)
    msg = f"Unsupported key-value format: {suffix}"
    raise ValueError(msg)


def serialize_keyvalue(
    entries: list[LocalizationEntry],
    format_data: object,
    suffix: str,
) -> str:
    """Dispatches to the format-specific key-value serializer.

    Args:
        entries: Localization entries with translated text.
        format_data: Format-specific data from ``parse_keyvalue()``.
        suffix: Lowercase file extension.

    Returns:
        Complete file content.

    Raises:
        ValueError: If the extension is not a supported key-value format.
    """
    if suffix in _YAML_EXTENSIONS:
        return serialize_yaml(entries, format_data)
    if suffix == ".properties":
        return serialize_properties(entries, format_data)
    if suffix == ".strings":
        return serialize_strings(entries, format_data)
    msg = f"Unsupported key-value format: {suffix}"
    raise ValueError(msg)
