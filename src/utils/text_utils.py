"""Utility functions for text processing and HTML cleaning."""

import html.parser
import re
import unicodedata
from typing import NamedTuple


def strip_bom(text: str) -> str:
    """Strips a leading UTF-8 BOM (U+FEFF) from *text* if present.

    Args:
        text: Input string that may start with a BOM.

    Returns:
        The string without the leading BOM character.
    """
    return text.lstrip("\ufeff")


def clean_llm_html(html: str) -> str:
    """Removes leading/trailing noise tags that interfere with layout.

    Handles all <br> variants: <br>, <br/>, <br />.

    Args:
        html: The raw HTML string from the LLM.

    Returns:
        Cleaned HTML string.
    """
    # Strip leading <br> tags (with optional whitespace between)
    html = re.sub(r"^(\s*<br\s*/?>)+", "", html, flags=re.IGNORECASE)
    # Strip trailing <br> tags
    return re.sub(r"(<br\s*/?>\s*)+$", "", html, flags=re.IGNORECASE)


def html_to_plain_text(html: str) -> str:
    """Converts enriched HTML to plain text for fallback or logging.

    Args:
        html: HTML string with tags like <b>, <i>, <span>, <br>.

    Returns:
        Stripped plain text.
    """
    # Replace all <br> variants with newlines
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)

    # Remove simple formatting tags
    for tag in ["<b>", "</b>", "<i>", "</i>", "<u>", "</u>", "</span>"]:
        text = text.replace(tag, "")

    # Remove complex tags with attributes (like <span style="...">)
    while "<span" in text:
        start = text.find("<span")
        end = text.find(">", start)
        if end != -1:
            text = text[:start] + text[end + 1 :]
        else:
            break

    return text.strip()


# ── Normalized Search Helpers ─────────────────────────────────


# Extended-Latin letters that NFKD does NOT decompose into a base
# letter + combining mark.  Without this map, NFKD-only normalization
# leaves them untouched, so they sort and search as if they were
# beyond Z in the alphabet — Vietnamese "Đan Mạch" lands after
# "Vietnamese", Polish "Łukasz" after "Zofia", Danish "Æbleskiver"
# after "Watermelon", etc.  Mapping each to its base letter (1:1 so
# the position-preserving ``build_norm_map`` invariant survives) makes
# accent-insensitive sort + search work the way users from those
# locales expect.  Multi-char ligatures (Æ→AE, Œ→OE, Þ→Th) are
# collapsed to single base letters here too — searching "aebleskiver"
# matching "Æbleskiver" via "ae" → "a" prefix is acceptable, and the
# 1:1 invariant matters more than perfect typographic expansion.
# Keys are post-casefold (lowercase) since callers always casefold first.
_EXTENDED_LATIN_BASE_MAP: dict[str, str] = {
    "đ": "d",   # Vietnamese, Croatian
    "ł": "l",   # Polish
    "ø": "o",   # Danish, Norwegian, Faroese
    "å": "a",   # Danish, Norwegian, Swedish
    "æ": "a",   # Danish, Norwegian (collapsed from "ae")
    "œ": "o",   # French (collapsed from "oe")
    "þ": "t",   # Icelandic (collapsed from "th")
    "ð": "d",   # Icelandic, Croatian, Faroese
}


def normalize_for_search(text: str) -> str:
    """Normalizes text for accent/case-insensitive search.

    Uses NFKD for compatibility decomposition (ligatures ﬁ→fi,
    CJK width variants), casefold() for locale-aware lowering
    (German ß→ss), strips combining marks (Mn) and invisible
    formatting chars (Cf, e.g. zero-width joiners), then maps
    non-decomposable extended-Latin letters (Đ, Ł, Ø, Å, Æ, Œ, Þ, Ð)
    to their base letter via :data:`_EXTENDED_LATIN_BASE_MAP`.

    Examples: "Xin Chào" → "xin chao", "café" → "cafe",
              "Straße" → "strasse", "Đan Mạch" → "dan mach",
              "Łukasz" → "lukasz".

    Args:
        text: Input string.

    Returns:
        str: Casefolded string with diacritics and invisible chars removed.
    """
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(
        _EXTENDED_LATIN_BASE_MAP.get(c, c)
        for c in decomposed
        if unicodedata.category(c) not in ("Mn", "Cf")
    )


def build_norm_map(text: str) -> tuple[str, list[int]]:
    """Builds a normalized string with a position map back to the original.

    Each character in the original text is casefolded and NFKD-decomposed,
    then combining marks (Mn) and invisible chars (Cf) are stripped, and
    extended-Latin letters (Đ, Ł, Ø, …) are mapped to their base letter
    via :data:`_EXTENDED_LATIN_BASE_MAP`.  The resulting characters are
    collected along with the index of the original character that produced
    them — the map only contains 1:1 substitutions, so the position
    alignment survives.

    This is used by the HighlightDelegate to find match spans in
    normalized text and map them back to the correct original-text
    positions for highlighting.

    Example::

        build_norm_map("Café")  → ("cafe", [0, 1, 2, 3])
        build_norm_map("Straße") → ("strasse", [0, 1, 2, 3, 4, 4, 5])
        #  ß casefolds to "ss" — both map back to original index 4.

    Args:
        text: Original (un-normalized) string.

    Returns:
        Tuple of (normalized_text, orig_indices) where
        ``orig_indices[i]`` is the index in *text* that produced
        the *i*-th character of *normalized_text*.
    """
    result_chars: list[str] = []
    orig_indices: list[int] = []
    for orig_idx, char in enumerate(text):
        decomposed = unicodedata.normalize("NFKD", char.casefold())
        for dc in decomposed:
            if unicodedata.category(dc) not in ("Mn", "Cf"):
                result_chars.append(_EXTENDED_LATIN_BASE_MAP.get(dc, dc))
                orig_indices.append(orig_idx)
    return "".join(result_chars), orig_indices


# ── HTML Attribute Stripping for Token Optimization ──────────


# Attributes whose values contain user-facing translatable text.
# Based on WHATWG HTML spec, XLIFF HTML profile, and WAI-ARIA.
_TRANSLATABLE_ATTRS = frozenset(
    {
        # HTML spec translatable attributes
        "alt",  # img, area, input — alternative text
        "title",  # all elements — tooltip text
        "placeholder",  # input, textarea — placeholder hint
        "label",  # optgroup, option, track — user-facing label
        "abbr",  # th — abbreviated header text
        "summary",  # table — table description (deprecated but used)
        # WAI-ARIA translatable attributes
        "aria-label",  # any — accessibility label
        "aria-placeholder",  # any — accessibility placeholder
        "aria-description",  # any — longer accessibility description
        "aria-roledescription",  # any — custom role name
        "aria-valuetext",  # range widgets — human-readable value
    }
)


# Marker attribute name used to identify tags during restoration.
_FTID_ATTR = "data-ftid"

# Regex to find data-ftid="N" in a tag for restoration.
_FTID_RE = re.compile(r'\s*data-ftid="(\d+)"')


class _AttrEntry(NamedTuple):
    """A single attribute with its translatable flag."""

    raw: str  # e.g. 'class="foo"' or 'alt="cat"'
    translatable: bool  # True if in _TRANSLATABLE_ATTRS


class AttrRecord(NamedTuple):
    """Stores all original attributes for a single tag, in order."""

    tag_name: str
    attrs: list[_AttrEntry]  # all attrs in original document order


# Matches an opening (or self-closing) HTML/XML tag that has at least one attribute.
# Group 1: tag name, Group 2: attributes string, Group 3: optional self-close slash.
# The attribute portion uses (?:[^>"']|"[^"]*"|'[^']*')* to correctly skip
# over > characters inside quoted attribute values.
_TAG_WITH_ATTRS_RE = re.compile(
    r"<([a-zA-Z][a-zA-Z0-9]*)"  # tag name
    r"(\s(?:[^>\"']|\"[^\"]*\"|'[^']*')*?)"  # attributes (handles > in quoted values)
    r"(\s*/?)>",  # optional self-close
    re.DOTALL,
)

# Matches a single HTML attribute: name="value", name='value', or name (boolean).
# Supports XML-namespaced attrs like xml:lang, xmlns:epub, epub:type.
_ATTR_RE = re.compile(
    r"""([a-zA-Z][a-zA-Z0-9\-:.]*)"""  # attribute name (incl. colon for XML ns)
    r"""(?:\s*=\s*"""  # = sign
    r"""(?:"([^"]*)"|'([^']*)'|"""  # quoted value
    r"""(\S+)))?""",  # unquoted value
)


class _AttrStripper(html.parser.HTMLParser):
    """HTMLParser subclass that strips non-translatable attributes.

    Uses ``get_starttag_text()`` to obtain the raw tag text (preserving
    original formatting, entities, quoting) and then applies ``_ATTR_RE``
    to classify individual attributes into keep/strip groups.

    Each tag that has attributes stripped receives a ``data-ftid="N"``
    marker so that :func:`restore_html_attributes` can match tags by
    ID instead of sequential order — robust against LLM tag mutations.

    All original attributes are stored in document order so that
    restoration can reconstruct the original attribute sequence.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self._pieces: list[str] = []
        self.records: dict[int, AttrRecord] = {}
        self._next_id = 0
        self._last_offset = 0
        self._source = ""

    def _emit_raw(self, end_offset: int) -> None:
        """Emit raw source text up to *end_offset*."""
        if end_offset > self._last_offset:
            self._pieces.append(
                self._source[self._last_offset : end_offset],
            )
            self._last_offset = end_offset

    def _process_start_tag(self, tag: str) -> None:  # noqa: PLR0912
        """Classify attributes in the current start tag, emit rebuilt tag."""
        raw_tag = self.get_starttag_text()
        if raw_tag is None:
            return

        # Find where this tag starts in the source
        tail = self._source[self._last_offset :]
        tag_end = self._last_offset + tail.index(raw_tag) + len(raw_tag)

        # Emit any content before this tag
        tag_start = tag_end - len(raw_tag)
        self._emit_raw(tag_start)

        # Extract the attributes portion from the raw tag text
        inner = raw_tag[1:]  # strip leading <
        if inner.endswith("/>"):
            close_slash = " /"
            inner = inner[:-2]  # strip />
        elif inner.endswith(">"):
            close_slash = ""
            inner = inner[:-1]  # strip >
        else:
            self._pieces.append(raw_tag)
            self._last_offset = tag_end
            return

        # Split tag name from attributes
        name_end = 0
        while name_end < len(inner) and not inner[name_end].isspace():
            name_end += 1
        tag_name_orig = inner[:name_end]
        attrs_str = inner[name_end:]

        # Parse individual attributes with _ATTR_RE
        all_entries: list[_AttrEntry] = []
        keep_parts: list[str] = []
        has_strip = False

        for attr_match in _ATTR_RE.finditer(attrs_str):
            attr_name = attr_match.group(1)
            full_attr = attr_match.group(0).strip()
            is_trans = attr_name.lower() in _TRANSLATABLE_ATTRS
            all_entries.append(_AttrEntry(full_attr, is_trans))
            if is_trans:
                keep_parts.append(full_attr)
            else:
                has_strip = True

        if not has_strip:
            # Nothing to strip — emit original tag unchanged
            self._pieces.append(raw_tag)
        else:
            # Record all attrs in order, keyed by marker ID
            ftid = self._next_id
            self._next_id += 1
            self.records[ftid] = AttrRecord(
                tag.lower(),
                all_entries,
            )

            # Rebuild tag: translatable attrs + marker
            parts = keep_parts + [f'{_FTID_ATTR}="{ftid}"']
            attrs_out = " ".join(parts)
            self._pieces.append(
                f"<{tag_name_orig} {attrs_out}{close_slash}>",
            )

        self._last_offset = tag_end

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        """Process an opening tag."""
        self._process_start_tag(tag)

    def handle_startendtag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        """Process a self-closing tag (e.g. <br/>, <img ... />)."""
        self._process_start_tag(tag)

    def feed_and_collect(self, source: str) -> str:
        """Feed source HTML and return the stripped result."""
        self._source = source
        self._last_offset = 0
        self._pieces = []
        self.records = {}
        self._next_id = 0
        self.feed(source)
        # Emit any trailing content after the last tag
        self._emit_raw(len(source))
        return "".join(self._pieces)


def strip_html_attributes(
    html_text: str,
) -> tuple[str, dict[int, AttrRecord]]:
    """Strips non-translatable attributes from HTML tags.

    Keeps translatable attributes (alt, title, placeholder, aria-label,
    etc.) in the tag for the LLM to translate.  Strips all other
    attributes, records them for later restoration, and adds a
    ``data-ftid="N"`` marker to each modified tag.

    Uses ``html.parser.HTMLParser`` for robust tag boundary detection,
    which correctly handles ``>`` inside quoted attribute values and
    multiline attributes.

    Args:
        html_text: Raw HTML string.

    Returns:
        Tuple of (stripped_html, attr_records) where attr_records is a
        dict mapping marker ID → AttrRecord.
    """
    if not html_text:
        return "", {}

    parser = _AttrStripper()
    stripped = parser.feed_and_collect(html_text)
    return stripped, parser.records


# Matches an opening (or self-closing) HTML tag that contains a
# data-ftid attribute.  Used by restore_html_attributes() to find
# tags that need attribute restoration.
# Group 1: tag name.
# Group 2: the full attribute/content portion between tag name and >.
_TAGGED_RE = re.compile(
    r"<([a-zA-Z][a-zA-Z0-9]*)"
    r"((?:\s(?:[^>\"']|\"[^\"]*\"|'[^']*')*?)?)"
    r"(\s*/?)>",
    re.DOTALL,
)


def restore_html_attributes(
    html_text: str,
    records: dict[int, AttrRecord] | list[AttrRecord],
) -> str:
    """Re-injects stripped attributes into translated HTML.

    Finds tags with ``data-ftid="N"`` markers, looks up the
    corresponding :class:`AttrRecord`, and rebuilds the tag with
    all original attributes in their original order.  Translated
    (translatable) attribute values are taken from the LLM output;
    non-translatable values are taken from the stored record.

    Args:
        html_text: Translated HTML (with markers from stripping).
        records: Attribute records — dict keyed by marker ID.

    Returns:
        HTML with original attributes restored and markers removed.
    """
    if not records:
        return html_text

    def _restore_tag(m: re.Match) -> str:
        """Rebuild a single tag with its original attributes restored."""
        full_tag = m.group(0)
        tag_name = m.group(1)
        attrs_part = m.group(2)
        close_slash = m.group(3)

        # Check for data-ftid marker
        ftid_match = _FTID_RE.search(attrs_part)
        if ftid_match is None:
            return full_tag

        ftid = int(ftid_match.group(1))
        if ftid not in records:
            return full_tag

        record = records[ftid]

        # Parse current attrs from the translated tag (excluding marker)
        clean_attrs = _FTID_RE.sub("", attrs_part)
        translated_vals: dict[str, str] = {}
        for am in _ATTR_RE.finditer(clean_attrs):
            aname = am.group(1).lower()
            translated_vals[aname] = am.group(0).strip()

        # Rebuild attrs in original order, merging translated values
        rebuilt: list[str] = []
        for entry in record.attrs:
            # Extract attr name from the stored raw string
            am = _ATTR_RE.match(entry.raw)
            if not am:
                continue
            aname = am.group(1).lower()
            if entry.translatable and aname in translated_vals:
                # Use translated value from LLM output
                rebuilt.append(translated_vals[aname])
            else:
                # Use original stored value
                rebuilt.append(entry.raw)

        if rebuilt:
            attrs_str = " ".join(rebuilt)
            return f"<{tag_name} {attrs_str}{close_slash}>"
        return f"<{tag_name}{close_slash}>"

    return _TAGGED_RE.sub(_restore_tag, html_text)


class _TagInfo(NamedTuple):
    """Stores a tag's text, signature, and position in the string."""

    tag: str  # Full tag text, e.g. '<div class="x">' or "</p>"
    signature: str  # Tag name + type for matching, e.g. "div" or "/div"
    start: int  # Start position in the original string
    end: int  # End position in the original string


# Matches any HTML/XML tag (opening, closing, self-closing).
# Supports namespaced (ns:tag), hyphenated (my-tag), and underscored names.
_ANY_TAG_RE = re.compile(r"</?[a-zA-Z][a-zA-Z0-9:._-]*[^>]*?>")

# Extracts the tag name and closing slash from a tag string.
# Captures the full name including namespace prefixes and hyphens.
_TAG_NAME_RE = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9:._-]*)")


def _tag_signature(tag_text: str) -> str:
    """Extracts a tag signature for matching: name + type.

    Opening tags like '<div class="x">' → "div".
    Closing tags like '</div>' → "/div".
    Self-closing tags like '<br/>' → "br" (treated as opening).

    Args:
        tag_text: Full tag string.

    Returns:
        Signature string for comparison.
    """
    m = _TAG_NAME_RE.match(tag_text)
    if not m:
        return tag_text
    slash = m.group(1)  # "/" for closing tags, "" for opening
    name = m.group(2).lower()
    return f"{slash}{name}"


def repair_html_tags(original: str, translated: str) -> str:
    """Re-inserts tags that the LLM dropped from the translated HTML.

    Uses greedy two-pointer alignment between the original and
    translated tag sequences. Tags are matched by name and type
    (opening/closing), not by full text — so attribute changes
    from LLM translation don't cause false mismatches.

    Any tag present in the original but missing from the translated
    output is re-inserted at the corresponding position.
    Tags that the LLM added (not in original) are left as-is.

    Args:
        original: The attribute-stripped HTML sent to the LLM.
        translated: The LLM's translated response.

    Returns:
        Translated HTML with missing tags re-inserted.
    """
    orig_tags = [
        _TagInfo(m.group(), _tag_signature(m.group()), m.start(), m.end())
        for m in _ANY_TAG_RE.finditer(original)
    ]
    trans_tags = [
        _TagInfo(m.group(), _tag_signature(m.group()), m.start(), m.end())
        for m in _ANY_TAG_RE.finditer(translated)
    ]

    if not orig_tags:
        return translated

    # Two-pointer alignment with look-ahead
    i = 0  # pointer into orig_tags
    j = 0  # pointer into trans_tags

    # Build result by collecting pieces of translated text with insertions
    pieces: list[str] = []
    last_pos = 0  # last consumed position in translated

    while i < len(orig_tags):
        # Look ahead in translated tags for a match
        found_k: int | None = None
        for k in range(j, len(trans_tags)):
            if orig_tags[i].signature == trans_tags[k].signature:
                found_k = k
                break

        if found_k is not None:
            # Match found — include everything up to and including it
            # (any extra LLM tags between j and found_k are kept)
            pieces.append(translated[last_pos : trans_tags[found_k].end])
            last_pos = trans_tags[found_k].end
            j = found_k + 1
            i += 1
        else:
            # Tag was dropped — insert the original tag
            if j < len(trans_tags):
                pieces.append(translated[last_pos : trans_tags[j].start])
                last_pos = trans_tags[j].start
            else:
                pieces.append(translated[last_pos:])
                last_pos = len(translated)
            pieces.append(orig_tags[i].tag)
            i += 1

    # Append any remaining translated content
    if last_pos < len(translated):
        pieces.append(translated[last_pos:])

    return "".join(pieces)


# ── XML Overhead & Attribute Stripping for Token Optimization ─


# Matches XML processing instructions and CDATA open/close markers.
# Comments (<!-- ... -->) are left intact — LLMs naturally skip them.
_XML_OVERHEAD_RE = re.compile(
    r"(<\?[^?]*\?+(?:[^>?][^?]*\?+)*>)"  # processing instruction
    r"|(<!\[CDATA\[)"  # CDATA open marker
    r"|(\]\]>)",  # CDATA close marker
)

# Matches [__PRESERVE_XML_N__] placeholders for restoration.
_XML_PLACEHOLDER_RE = re.compile(r"\[__PRESERVE_XML_(\d+)__\]")


def strip_xml_overhead(xml: str) -> tuple[str, list[str]]:
    """Strips processing instructions and CDATA markers from XML.

    Replaces each non-translatable construct with a bracketed placeholder
    ``[__PRESERVE_XML_N__]`` so the LLM only sees translatable text and
    tag structure.  Comments (``<!-- ... -->``) are left intact — LLMs
    naturally skip them.  CDATA text content is preserved — only the
    ``<![CDATA[`` and ``]]>`` markers are replaced.

    Args:
        xml: Raw XML string.

    Returns:
        Tuple of (stripped_xml, records) where ``records[N]`` is the
        original text that ``[__PRESERVE_XML_N__]`` replaces.
    """
    if not xml:
        return "", []

    records: list[str] = []

    def _replace(m: re.Match) -> str:
        """Replace a matched XML construct with a numbered placeholder."""
        idx = len(records)
        records.append(m.group(0))
        return f"[__PRESERVE_XML_{idx}__]"

    stripped = _XML_OVERHEAD_RE.sub(_replace, xml)
    return stripped, records


def restore_xml_overhead(xml: str, records: list[str]) -> str:
    """Re-injects XML processing instructions and CDATA markers.

    Replaces ``[__PRESERVE_XML_N__]`` placeholders back with the original
    content stored in *records*.

    Args:
        xml: Translated XML containing ``[__PRESERVE_XML_N__]`` placeholders.
        records: List of original constructs from :func:`strip_xml_overhead`.

    Returns:
        XML with original non-translatable constructs restored.
    """
    if not records:
        return xml

    def _restore(m: re.Match) -> str:
        """Replace an XML placeholder with its original construct."""
        idx = int(m.group(1))
        if idx < len(records):
            return records[idx]
        return m.group(0)  # Unknown index — leave placeholder as-is

    return _XML_PLACEHOLDER_RE.sub(_restore, xml)


def strip_xml_attributes(
    xml: str,
) -> tuple[str, dict[int, AttrRecord]]:
    """Strips ALL attributes from XML tags.

    Unlike :func:`strip_html_attributes` which keeps translatable
    attributes (alt, title, etc.), XML attributes are almost never
    translatable so everything is stripped.  Each modified tag receives
    a ``data-ftid="N"`` marker for robust restoration.

    Args:
        xml: XML string (with overhead already stripped, if desired).

    Returns:
        Tuple of (stripped_xml, attr_records) where attr_records is a
        dict mapping marker ID → AttrRecord.
    """
    if not xml:
        return "", {}

    records: dict[int, AttrRecord] = {}
    next_id = 0

    def _replace_tag(m: re.Match) -> str:
        """Strip all attributes from a tag and insert a marker for restoration."""
        nonlocal next_id
        tag_name = m.group(1)
        attrs_str = m.group(2)
        close_slash = m.group(3)

        # Collect all attributes — strip everything (none translatable)
        all_entries: list[_AttrEntry] = []
        for attr_match in _ATTR_RE.finditer(attrs_str):
            full_attr = attr_match.group(0).strip()
            if full_attr:
                all_entries.append(_AttrEntry(full_attr, False))

        # Nothing to strip — return original tag unchanged
        if not all_entries:
            return m.group(0)

        ftid = next_id
        next_id += 1
        records[ftid] = AttrRecord(tag_name.lower(), all_entries)
        marker = f' {_FTID_ATTR}="{ftid}"'
        return f"<{tag_name}{marker}{close_slash}>"

    stripped = _TAG_WITH_ATTRS_RE.sub(_replace_tag, xml)
    return stripped, records


# ── RTF Overhead Stripping for Token Optimization ────────────


# Matches RTF non-text constructs in order of specificity:
# 1) Unicode escape  \uN? (most specific — must precede generic control word)
# 2) Control word    \keyword[-]N[space]
# 3) Control symbol  \<non-alpha>
# 4) Group braces    { or }
_RTF_OVERHEAD_RE = re.compile(
    r"(\\u-?\d+[ ]?.)"  # Unicode escape + ANSI fallback char
    r"|(\\[a-zA-Z]+-?\d* ?)"  # Control word with optional param + space
    r"|(\\[^a-zA-Z\r\n])"  # Control symbol
    r"|([{}])",  # Group braces
)

# Matches [__PRESERVE_RTF_N__] placeholders for restoration.
_RTF_PLACEHOLDER_RE = re.compile(r"\[__PRESERVE_RTF_(\d+)__\]")


def strip_rtf_overhead(rtf: str) -> tuple[str, list[str]]:
    r"""Strips RTF control words, symbols, braces, and Unicode escapes.

    Replaces each non-text construct with a bracketed placeholder
    ``[__PRESERVE_RTF_N__]``.  Unicode escapes (``\uN?``) are decoded
    to the actual Unicode character in the stripped text so the LLM can
    read them; the original escape is still recorded for round-trip
    fidelity.

    Args:
        rtf: RTF text chunk (already split by ``\par``).

    Returns:
        Tuple of (stripped_text, records) where ``records[N]`` is the
        original RTF construct that ``[__PRESERVE_RTF_N__]`` replaces.
    """
    if not rtf:
        return "", []

    records: list[str] = []

    def _replace(m: re.Match) -> str:
        """Replace a matched RTF construct with a placeholder or decoded character."""
        # Group 1: Unicode escape \uN?  — decode to real character
        if m.group(1) is not None:
            idx = len(records)
            records.append(m.group(1))
            # Extract the codepoint and convert to character
            escape = m.group(1)
            # Parse \u<number><fallback_char>
            num_str = escape[2:]  # strip leading "\u"
            code = 0
            i = 0
            # Handle optional negative sign
            neg = False
            if i < len(num_str) and num_str[i] == "-":
                neg = True
                i += 1
            while i < len(num_str) and num_str[i].isdigit():
                code = code * 10 + int(num_str[i])
                i += 1
            if neg:
                code = 65536 - code  # RTF negative = 65536 - abs
            try:
                return chr(code)
            except (ValueError, OverflowError):
                return f"[__PRESERVE_RTF_{idx}__]"

        # Groups 2-4: control word, control symbol, brace
        idx = len(records)
        records.append(m.group(0))
        return f"[__PRESERVE_RTF_{idx}__]"

    stripped = _RTF_OVERHEAD_RE.sub(_replace, rtf)
    return stripped, records


def restore_rtf_overhead(text: str, records: list[str]) -> str:
    """Re-injects RTF control words and symbols from placeholders.

    Replaces ``[__PRESERVE_RTF_N__]`` placeholders back with the original
    RTF constructs stored in *records*.

    Args:
        text: Translated text containing ``[__PRESERVE_RTF_N__]`` placeholders.
        records: List of original RTF constructs from :func:`strip_rtf_overhead`.

    Returns:
        RTF text with original control sequences restored.
    """
    if not records:
        return text

    def _restore(m: re.Match) -> str:
        """Replace an RTF placeholder with its original construct."""
        idx = int(m.group(1))
        if idx < len(records):
            return records[idx]
        return m.group(0)  # Unknown index — leave placeholder as-is

    return _RTF_PLACEHOLDER_RE.sub(_restore, text)


# ── Markdown Overhead Stripping for Token Optimization ────────


# Matches inline links [text](url) and images ![alt](url).
# Group 1: leading "!" for images (or empty for links).
# Group 2: bracket text (link text or alt text).
# Group 3: URL (everything inside the parentheses).
_MD_INLINE_LINK_RE = re.compile(
    r"(!?)"  # optional "!" for images
    r"\[([^\]]*)\]"  # bracket text
    r"\(([^)]+)\)",  # URL in parentheses
)

# Matches reference-style link definitions: [id]: url "optional title"
# Group 1: reference id.
# Group 2: URL and optional title (everything after ": ").
_MD_REF_LINK_RE = re.compile(
    r"^(\[[^\]]+\]):\s+(.+)$",
    re.MULTILINE,
)

# Matches [__PRESERVE_MD_N__] placeholders for restoration.
_MD_PLACEHOLDER_RE = re.compile(r"\[__PRESERVE_MD_(\d+)__\]")


def strip_md_overhead(md: str) -> tuple[str, list[str]]:
    """Strips URLs from Markdown links/images and reference definitions.

    Replaces each URL with a bracketed placeholder
    ``[__PRESERVE_MD_N__]`` so the LLM only sees translatable text.
    The caller should chain :func:`strip_html_attributes` afterwards
    to handle embedded HTML.

    Handles:
    - Inline links: ``[text](url)`` → ``[text]([__PRESERVE_MD_N__])``
    - Inline images: ``![alt](url)`` → ``![alt]([__PRESERVE_MD_N__])``
    - Reference definitions: ``[id]: url`` → ``[id]: [__PRESERVE_MD_N__]``

    Args:
        md: Raw Markdown string.

    Returns:
        Tuple of (stripped_md, records) where ``records[N]`` is the
        original URL/content that ``[__PRESERVE_MD_N__]`` replaces.
    """
    if not md:
        return "", []

    records: list[str] = []

    def _replace_inline(m: re.Match) -> str:
        """Replace inline link/image URL with placeholder."""
        bang = m.group(1)  # "!" for images, "" for links
        bracket_text = m.group(2)
        url = m.group(3)
        idx = len(records)
        records.append(url)
        return f"{bang}[{bracket_text}]([__PRESERVE_MD_{idx}__])"

    def _replace_ref(m: re.Match) -> str:
        """Replace reference-style link definition URL with placeholder."""
        ref_id = m.group(1)
        url_and_title = m.group(2)
        idx = len(records)
        records.append(url_and_title)
        return f"{ref_id}: [__PRESERVE_MD_{idx}__]"

    # Strip inline links/images first, then reference definitions
    stripped = _MD_INLINE_LINK_RE.sub(_replace_inline, md)
    stripped = _MD_REF_LINK_RE.sub(_replace_ref, stripped)

    return stripped, records


def restore_md_overhead(md: str, records: list[str]) -> str:
    """Re-injects Markdown URLs from placeholders.

    Replaces ``[__PRESERVE_MD_N__]`` placeholders back with the original
    URLs stored in *records*.

    Args:
        md: Translated Markdown containing ``[__PRESERVE_MD_N__]`` placeholders.
        records: List of original URLs from :func:`strip_md_overhead`.

    Returns:
        Markdown with original URLs restored.
    """
    if not records:
        return md

    def _restore(m: re.Match) -> str:
        """Replace a Markdown placeholder with its original URL."""
        idx = int(m.group(1))
        if idx < len(records):
            return records[idx]
        return m.group(0)  # Unknown index — leave placeholder as-is

    return _MD_PLACEHOLDER_RE.sub(_restore, md)
