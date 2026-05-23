"""Formatting preservation layer for Office documents.

Extracts per-run formatting as inline HTML before LLM translation, then
reconstructs formatted runs afterwards.  Shared by python-docx, python-pptx,
DrawingML/lxml, and ODF/lxml code paths.

Dependency rule: this module only imports stdlib, lxml, and lazy docx/pptx —
it does NOT import ``office_processor``.
"""

import contextlib
import html
import html.parser
import re
import zipfile
from collections.abc import Callable
from typing import NamedTuple

from lxml import etree

logger = __import__("logging").getLogger("office_formatter")


# ── XML namespace constants ──────────────────────────────────────────────

# DrawingML namespace (used in modern comment txBody rich text)
_DRAWINGML_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"

# WordprocessingML namespace (for <w:t> text runs inside text boxes)
_WORDML_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

# ODF namespaces
_ODF_NS = {
    "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
    "draw": "urn:oasis:names:tc:opendocument:xmlns:drawing:1.0",
    "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
    "fo": "urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0",
    "style": "urn:oasis:names:tc:opendocument:xmlns:style:1.0",
    "xlink": "http://www.w3.org/1999/xlink",
}


# ── Core regex patterns and data types ───────────────────────────────────

# Quick-check regex to detect inline HTML formatting tags in translated text.
_FORMATTING_HTML_RE = re.compile(
    r"</?[bius]>|</?su[bp]>|</?span[\s>]|<a[\s>]|</a>", re.IGNORECASE
)

# Regex to strip ALL formatting tags (used for fallback when parsing yields
# no segments — avoids inserting literal HTML tags into the document)
_STRIP_FORMAT_TAGS_RE = re.compile(
    r"</?[bius]>|</?su[bp]>|</?span[^>]*>|<a[^>]*>|</a>", re.IGNORECASE
)

# Outermost-to-innermost wrapping order for inline HTML formatting tags.
_TAG_NESTING_ORDER = ("b", "i", "u", "s", "sup", "sub")

# OOXML hyperlink relationship type
_HYPERLINK_RELTYPE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink"
)

# Pre-computed qualified tag for <w:hyperlink> (avoids repeated qn() calls)
_W_HYPERLINK_TAG = f"{{{_WORDML_NS}}}hyperlink"


class _FormattedSegment(NamedTuple):
    """A text segment with inline formatting flags."""

    text: str
    bold: bool
    italic: bool
    underline: bool
    strike: bool
    superscript: bool = False
    subscript: bool = False
    font_size_pt: float | None = None  # e.g. 14.0; None = use base
    color_hex: str | None = None  # e.g. "#ff0000"; None = use base
    bg_color_hex: str | None = None  # e.g. "#ffff00"; None = no bg
    hyperlink_url: str | None = None  # e.g. "https://..."; None = no link


# Word highlight colour names → hex (ECMA-376 ST_HighlightColor)
_HIGHLIGHT_COLORS: dict[str, str] = {
    "yellow": "#ffff00",
    "green": "#00ff00",
    "cyan": "#00ffff",
    "magenta": "#ff00ff",
    "blue": "#0000ff",
    "red": "#ff0000",
    "darkblue": "#000080",
    "darkcyan": "#008080",
    "darkgreen": "#008000",
    "darkmagenta": "#800080",
    "darkred": "#800000",
    "darkyellow": "#808000",
    "darkgray": "#808080",
    "lightgray": "#c0c0c0",
    "black": "#000000",
    "white": "#ffffff",
}

# Regex to extract font-size, color and background-color from CSS inline style
_SPAN_FONT_SIZE_RE = re.compile(r"font-size:\s*([\d.]+)\s*pt", re.IGNORECASE)
_SPAN_COLOR_RE = re.compile(r"(?<![a-z-])color:\s*(#[0-9a-fA-F]{6})", re.IGNORECASE)
_SPAN_BG_COLOR_RE = re.compile(
    r"background-color:\s*(#[0-9a-fA-F]{6})",
    re.IGNORECASE,
)


# ── Win32COM Word highlight mappings ─────────────────────────────────────

_WD_HIGHLIGHT_INDEX_TO_HEX: dict[int, str] = {
    1: "#000000",  # wdBlack
    2: "#0000ff",  # wdBlue
    3: "#00ffff",  # wdTurquoise
    4: "#00ff00",  # wdBrightGreen
    5: "#ff00ff",  # wdPink
    6: "#ff0000",  # wdRed
    7: "#ffff00",  # wdYellow
    8: "#ffffff",  # wdWhite
    9: "#000080",  # wdDarkBlue
    10: "#008080",  # wdTeal
    11: "#008000",  # wdGreen
    12: "#800080",  # wdViolet
    13: "#800000",  # wdDarkRed
    14: "#808000",  # wdDarkYellow
    15: "#808080",  # wdGray50
    16: "#c0c0c0",  # wdGray25
}
# Reverse: hex → closest highlight index for injection
_HEX_TO_WD_HIGHLIGHT_INDEX: dict[str, int] = {
    v: k for k, v in _WD_HIGHLIGHT_INDEX_TO_HEX.items()
}


# ── PPTX / DrawingML format attribute sets ───────────────────────────────

# DrawingML rPr attributes that encode inline formatting (excluded from base)
_PPTX_FORMAT_ATTRS = frozenset({"b", "i", "u", "strike", "baseline"})
_DRAWINGML_FORMAT_ATTRS = _PPTX_FORMAT_ATTRS  # alias — identical attribute set


# ── Color / style conversion functions ───────────────────────────────────


def _build_span_style(
    font_size_pt: float | None,
    color_hex: str | None,
    bg_color_hex: str | None = None,
) -> str:
    """Builds a CSS inline style string for ``<span>`` wrapping.

    Args:
        font_size_pt: Font size in points, or None to omit.
        color_hex: Hex colour like ``"#ff0000"``, or None to omit.
        bg_color_hex: Background colour like ``"#ffff00"``, or None.

    Returns:
        Style string, e.g. ``"font-size:14pt;color:#ff0000"``.
        Empty string when all are None.
    """
    parts: list[str] = []
    if font_size_pt is not None:
        parts.append(f"font-size:{font_size_pt:g}pt")
    if color_hex is not None:
        parts.append(f"color:{color_hex}")
    if bg_color_hex is not None:
        parts.append(f"background-color:{bg_color_hex}")
    return ";".join(parts)


def _parse_span_style(style: str) -> dict[str, float | str]:
    """Extracts ``font-size``, ``color`` and ``background-color`` from CSS.

    Uses a negative look-behind to avoid matching ``background-color:``
    when reading ``color:``.

    Args:
        style: Raw CSS style string from a ``<span>`` tag.

    Returns:
        dict with optional keys ``"font_size_pt"`` (float),
        ``"color_hex"`` (str), and ``"bg_color_hex"`` (str).
    """
    result: dict[str, float | str] = {}
    m_size = _SPAN_FONT_SIZE_RE.search(style)
    if m_size:
        result["font_size_pt"] = float(m_size.group(1))
    m_color = _SPAN_COLOR_RE.search(style)
    if m_color:
        result["color_hex"] = m_color.group(1).lower()
    m_bg = _SPAN_BG_COLOR_RE.search(style)
    if m_bg:
        result["bg_color_hex"] = m_bg.group(1).lower()
    return result


def _wrap_with_tags(  # noqa: PLR0913
    escaped: str,
    bold: bool,
    italic: bool,
    underline: bool,
    strike: bool,
    font_size_pt: float | None,
    color_hex: str | None,
    *,
    has_size_variation: bool,
    has_color_variation: bool,
    bg_color_hex: str | None = None,
    has_bg_variation: bool = False,
    hyperlink_url: str | None = None,
    superscript: bool = False,
    subscript: bool = False,
) -> str:
    """Wraps escaped text with formatting, ``<span>``, and ``<a>`` tags.

    ``<span>`` is innermost (closest to text),
    ``<b>/<i>/<u>/<s>/<sup>/<sub>`` outside, ``<a>`` outermost (wraps all
    formatting).  ``<span>`` is only emitted when the corresponding
    variation flag is True and the value is not None.

    Args:
        escaped: HTML-escaped text content.
        bold: Bold flag.
        italic: Italic flag.
        underline: Underline flag.
        strike: Strikethrough flag.
        font_size_pt: Font size in points, or None.
        color_hex: Hex colour, or None.
        has_size_variation: True if font sizes vary across the paragraph.
        has_color_variation: True if colours vary across the paragraph.
        bg_color_hex: Background colour hex, or None.
        has_bg_variation: True if bg colours vary across the paragraph.
        hyperlink_url: URL for wrapping in ``<a href="...">``, or None.
        superscript: Superscript flag.
        subscript: Subscript flag.

    Returns:
        HTML string with appropriate wrapping tags.
    """
    # Build span style only for properties that actually vary
    span_size = font_size_pt if has_size_variation else None
    span_color = color_hex if has_color_variation else None
    span_bg = bg_color_hex if has_bg_variation else None
    style = _build_span_style(span_size, span_color, span_bg)

    result = escaped
    if style:
        result = f'<span style="{style}">{result}</span>'

    flags = {
        "b": bold,
        "i": italic,
        "u": underline,
        "s": strike,
        "sup": superscript,
        "sub": subscript,
    }
    for tag in reversed(_TAG_NESTING_ORDER):
        if flags[tag]:
            result = f"<{tag}>{result}</{tag}>"

    # Hyperlink wraps outermost so the LLM sees a single <a> block
    if hyperlink_url:
        result = f'<a href="{html.escape(hyperlink_url, quote=True)}">{result}</a>'

    return result


def _int_to_color_hex(color_int: int) -> str | None:
    """Converts an integer ``0xRRGGBB`` colour to ``"#rrggbb"``.

    Returns None for automatic/unset values (-1 in UNO, or overflow).

    Args:
        color_int: Integer colour value.

    Returns:
        Lowercase hex string like ``"#ff0000"``, or None.
    """
    if color_int < 0 or color_int > 0xFFFFFF:  # noqa: PLR2004
        return None
    return f"#{color_int:06x}"


def _color_hex_to_int(color_hex: str) -> int:
    """Converts ``"#rrggbb"`` to an integer colour value.

    Args:
        color_hex: Hex colour string like ``"#ff0000"``.

    Returns:
        Integer colour value, e.g. 16711680.
    """
    return int(color_hex.lstrip("#"), 16)


def _win32com_color_to_hex(bgr_int: int) -> str | None:
    """Converts a win32com BGR integer (COLORREF) to ``"#rrggbb"``.

    Windows COM APIs store colours in BGR byte order
    (``R + G*256 + B*65536``).

    Args:
        bgr_int: BGR colour integer from ``Font.Color`` or ``Font.Color.RGB``.

    Returns:
        Lowercase hex string like ``"#ff0000"``, or None for negative /
        overflow values.
    """
    if bgr_int < 0 or bgr_int > 0xFFFFFF:  # noqa: PLR2004
        return None
    r = bgr_int & 0xFF
    g = (bgr_int >> 8) & 0xFF
    b = (bgr_int >> 16) & 0xFF
    return f"#{r:02x}{g:02x}{b:02x}"


def _color_hex_to_win32com(color_hex: str) -> int:
    """Converts ``"#rrggbb"`` to a win32com BGR integer (COLORREF).

    Args:
        color_hex: Hex colour string like ``"#ff0000"``.

    Returns:
        BGR integer suitable for ``Font.Color`` or ``Font.Color.RGB``.
    """
    h = color_hex.lstrip("#")
    r = int(h[0:2], 16)
    g = int(h[2:4], 16)
    b = int(h[4:6], 16)
    return r + g * 256 + b * 65536


# ── DOCX run formatting readers ──────────────────────────────────────────


def _read_docx_run_size_pt(run: object) -> float | None:
    """Reads font size in points from a python-docx run.

    python-docx stores ``run.font.size`` in EMU (English Metric Units);
    1 pt = 12700 EMU.  Returns None when size is inherited from style.

    Args:
        run: A python-docx Run object.

    Returns:
        Font size in points, or None.
    """
    emu_per_pt = 12700  # noqa: PLR2004
    try:
        raw = run.font.size
        if raw is None:
            return None
        return float(raw) / emu_per_pt
    except Exception:  # noqa: BLE001
        return None


def _read_docx_run_color_hex(run: object) -> str | None:
    """Reads text colour as ``"#rrggbb"`` from a python-docx run.

    Returns None for theme-only colours (where ``run.font.color.rgb`` is None).

    Args:
        run: A python-docx Run object.

    Returns:
        Lowercase hex colour string, or None.
    """
    try:
        rgb = run.font.color.rgb
        if rgb is None:
            return None
        return f"#{rgb}".lower()
    except Exception:  # noqa: BLE001
        return None


# python-docx WD_COLOR_INDEX int -> hex mapping for font.color_index values.
# Distinct from _WD_HIGHLIGHT_INDEX_TO_HEX which maps Win32COM highlight enums.
_WD_COLOR_INDEX_TO_HEX: dict[int, str] = {
    1: "#000000",  # BLACK
    2: "#0000ff",  # BLUE
    3: "#00ffff",  # TURQUOISE
    4: "#00ff00",  # BRIGHT_GREEN
    5: "#ff00ff",  # PINK
    6: "#ff0000",  # RED
    7: "#ffff00",  # YELLOW
    8: "#ffffff",  # WHITE
    9: "#000080",  # DARK_BLUE
    10: "#008080",  # TEAL
    11: "#008000",  # GREEN
    12: "#800080",  # VIOLET
    13: "#800000",  # DARK_RED
    14: "#808000",  # DARK_YELLOW
    15: "#808080",  # GRAY_50
    16: "#c0c0c0",  # GRAY_25
}


def _read_docx_run_bg_hex(run: object) -> str | None:
    """Reads background/highlight colour as ``"#rrggbb"`` from a run.

    Checks ``<w:shd>`` (arbitrary shading) first, then ``<w:highlight>``
    (predefined Word highlight colours), then falls back to python-docx's
    ``run.font.highlight_color`` API.  Attribute access tries both
    namespaced (``w:val``) and unnamespaced (``val``) forms for
    compatibility with different DOCX producers.

    Args:
        run: A python-docx Run object.

    Returns:
        Lowercase hex colour string, or None if no background.
    """
    from docx.oxml.ns import qn  # noqa: PLC0415

    rpr = run._element.find(qn("w:rPr"))
    if rpr is not None:
        # <w:shd w:fill="FFFF00"/> — arbitrary background colour
        shd = rpr.find(qn("w:shd"))
        if shd is not None:
            fill = shd.get(qn("w:fill")) or shd.get("fill")
            if fill and fill.lower() != "auto":
                return f"#{fill.lower()}"

        # <w:highlight w:val="yellow"/> — predefined highlight colour
        hl = rpr.find(qn("w:highlight"))
        if hl is not None:
            val = hl.get(qn("w:val")) or hl.get("val")
            if val and val.lower() != "none":
                color = _HIGHLIGHT_COLORS.get(val.lower())
                if color:
                    return color

    # Fallback: python-docx high-level API (handles style resolution)
    try:
        hl_idx = run.font.highlight_color
        if hl_idx is not None and int(hl_idx) > 0:
            return _WD_COLOR_INDEX_TO_HEX.get(int(hl_idx))
    except Exception:  # noqa: BLE001
        pass

    return None


def _has_mixed_formatting(para: object) -> bool:
    """Checks whether a paragraph has runs with differing formatting.

    Compares bold, italic, underline, strike, superscript, subscript,
    font size, text colour, and background colour.  Only considers
    text-carrying runs (skips visual-content runs and runs with empty
    text).  Returns False if 0 or 1 text runs remain.

    Args:
        para: A python-docx Paragraph object.

    Returns:
        True if at least two text runs have different formatting.
    """
    sigs: list[
        tuple[
            bool,
            bool,
            bool,
            bool,
            bool,
            bool,
            float | None,
            str | None,
            str | None,
        ]
    ] = []
    for run in para.runs:
        if _run_has_visual_content(run._element):
            continue
        if not run.text:
            continue
        sigs.append(
            (
                bool(run.bold),
                bool(run.italic),
                bool(run.underline),
                bool(run.font.strike if run.font else False),
                bool(run.font.superscript if run.font else False),
                bool(run.font.subscript if run.font else False),
                _read_docx_run_size_pt(run),
                _read_docx_run_color_hex(run),
                _read_docx_run_bg_hex(run),
            )
        )
    if len(sigs) <= 1:
        return False
    return len(set(sigs)) > 1


def _para_has_hyperlinks(para_elem: object) -> bool:
    """Checks if a paragraph XML element contains ``<w:hyperlink>`` children.

    Used to force the HTML extraction/injection path for paragraphs that
    contain hyperlinks, even when all runs share the same formatting.

    Args:
        para_elem: The ``<w:p>`` lxml element (``para._element``).

    Returns:
        True if any direct child is ``<w:hyperlink>``.
    """
    return any(child.tag == _W_HYPERLINK_TAG for child in para_elem)


def _runs_to_html(  # noqa: PLR0912, PLR0914, PLR0915
    para: object,
    hyperlink_rels: dict[str, str] | None = None,
) -> str:
    """Converts a paragraph's runs to inline HTML.

    Iterates ``para._element`` children (not ``para.runs``) so that runs
    inside ``<w:hyperlink>`` wrappers are included.  Hyperlinked runs are
    emitted inside ``<a href="...">`` tags.

    Two-pass: first collects run data to detect size/colour/bg variation,
    then emits HTML with ``<span>`` only when values actually vary.
    Skips visual-content runs.

    Args:
        para: A python-docx Paragraph object.
        hyperlink_rels: Mapping of ``r:id`` → URL for hyperlinks in this
            paragraph, built by ``_resolve_para_hyperlink_rels()``.

    Returns:
        HTML string representing the paragraph's formatted text.
    """
    from docx.oxml.ns import qn  # noqa: PLC0415

    w_r = qn("w:r")
    w_rpr = qn("w:rPr")
    w_t = qn("w:t")
    r_id_attr = qn("r:id")
    w_anchor_attr = qn("w:anchor")

    # Map element → python-docx Run for direct <w:r> children so we
    # can use the full python-docx API (style inheritance) for them.
    run_map = {run._element: run for run in para.runs}

    # Pass 1: collect run data in document order.
    # Each entry: (text, bold, italic, underline, strike, superscript,
    #              subscript, size, color, bg, url)
    run_data: list[
        tuple[
            str,
            bool,
            bool,
            bool,
            bool,
            bool,
            bool,
            float | None,
            str | None,
            str | None,
            str | None,
        ]
    ] = []

    def _collect_run_obj(run: object) -> None:
        """Collects data from a python-docx Run (direct <w:r>)."""
        if _run_has_visual_content(run._element):
            return
        if not run.text:
            return
        run_data.append(
            (
                run.text,
                bool(run.bold),
                bool(run.italic),
                bool(run.underline),
                bool(run.font.strike if run.font else False),
                bool(run.font.superscript if run.font else False),
                bool(run.font.subscript if run.font else False),
                _read_docx_run_size_pt(run),
                _read_docx_run_color_hex(run),
                _read_docx_run_bg_hex(run),
                None,
            )
        )

    def _collect_run_elem(r_elem: object, url: str | None) -> None:
        """Collects data from a raw <w:r> element (inside <w:hyperlink>)."""
        if _run_has_visual_content(r_elem):
            return
        text = "".join(t.text or "" for t in r_elem.findall(w_t))
        if not text:
            return
        rpr = r_elem.find(w_rpr)
        bold, italic, underline, strike, sz, clr, bg = _read_wml_rpr_formatting(rpr)
        sup, sub = _read_wml_rpr_sup_sub(rpr)
        run_data.append(
            (text, bold, italic, underline, strike, sup, sub, sz, clr, bg, url),
        )

    for child in para._element:
        if child.tag == w_r:
            run = run_map.get(child)
            if run:
                _collect_run_obj(run)
        elif child.tag == _W_HYPERLINK_TAG:
            # Resolve hyperlink URL from r:id or w:anchor
            url: str | None = None
            rid = child.get(r_id_attr)
            anchor = child.get(w_anchor_attr)
            if rid and hyperlink_rels:
                url = hyperlink_rels.get(rid)
            elif anchor:
                url = f"#{anchor}"
            for r_elem in child.findall(w_r):
                _collect_run_elem(r_elem, url)

    if not run_data:
        return ""

    # Detect variation — base is always None for safe roundtrip
    sizes = [d[7] for d in run_data]
    colors = [d[8] for d in run_data]
    bgs = [d[9] for d in run_data]
    has_size_variation = len(set(sizes)) > 1
    has_color_variation = len(set(colors)) > 1
    has_bg_variation = len(set(bgs)) > 1
    # base_size/color/bg are always None so every run with an explicit value
    # gets its own <span>.  Using most-common as base loses that value during
    # injection when the first run is not the most-common one.
    base_size = None
    base_color = None
    base_bg = None

    # Pass 2: emit HTML, grouping consecutive runs with the same hyperlink
    parts: list[str] = []
    current_url: str | None = None
    for (
        text,
        bold,
        italic,
        underline,
        strike,
        sup,
        sub,
        sz,
        clr,
        bg,
        url,
    ) in run_data:
        # Manage <a> tag transitions
        if url != current_url:
            if current_url is not None:
                parts.append("</a>")
            if url is not None:
                parts.append(f'<a href="{html.escape(url, quote=True)}">')
            current_url = url
        parts.append(
            _wrap_with_tags(
                html.escape(text),
                bold,
                italic,
                underline,
                strike,
                sz if sz != base_size else None,
                clr if clr != base_color else None,
                has_size_variation=has_size_variation,
                has_color_variation=has_color_variation,
                bg_color_hex=bg if bg != base_bg else None,
                has_bg_variation=has_bg_variation,
                superscript=sup,
                subscript=sub,
            )
        )

    # Close any open <a> tag
    if current_url is not None:
        parts.append("</a>")

    return "".join(parts)


# ── Inline HTML parser ───────────────────────────────────────────────────


class _InlineHTMLParser(html.parser.HTMLParser):
    """Parses simple inline HTML (<b>, <i>, <u>, <s>, <span>, <a>) into segments."""

    def __init__(self) -> None:
        super().__init__()
        self._tag_stack: list[str] = []
        self._span_style_stack: list[dict[str, float | str]] = []
        self._hyperlink_stack: list[str] = []
        self.segments: list[_FormattedSegment] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Pushes a recognized formatting tag onto the stack."""
        if tag in {"b", "i", "u", "s", "sup", "sub"}:
            self._tag_stack.append(tag)
        elif tag == "span":
            # Parse style attribute for font-size and color
            style = dict(attrs).get("style", "") or ""
            self._span_style_stack.append(_parse_span_style(style))
        elif tag == "a":
            href = dict(attrs).get("href", "") or ""
            self._hyperlink_stack.append(html.unescape(href))

    def handle_endtag(self, tag: str) -> None:
        """Pops the most recent matching tag from the stack."""
        if tag in {"b", "i", "u", "s", "sup", "sub"}:
            # Remove the last occurrence (handles misnested HTML gracefully)
            for idx in range(len(self._tag_stack) - 1, -1, -1):
                if self._tag_stack[idx] == tag:
                    self._tag_stack.pop(idx)
                    break
        elif tag == "span" and self._span_style_stack:
            self._span_style_stack.pop()
        elif tag == "a" and self._hyperlink_stack:
            self._hyperlink_stack.pop()

    def handle_data(self, data: str) -> None:
        """Creates a formatted segment from the current tag stack state."""
        active = set(self._tag_stack)
        # Read font_size_pt / color_hex / bg_color_hex from top of span stack
        span_props = self._span_style_stack[-1] if self._span_style_stack else {}
        hyperlink_url = self._hyperlink_stack[-1] if self._hyperlink_stack else None
        self.segments.append(
            _FormattedSegment(
                text=data,
                bold="b" in active,
                italic="i" in active,
                underline="u" in active,
                strike="s" in active,
                superscript="sup" in active,
                subscript="sub" in active,
                font_size_pt=span_props.get("font_size_pt"),
                color_hex=span_props.get("color_hex"),
                bg_color_hex=span_props.get("bg_color_hex"),
                hyperlink_url=hyperlink_url,
            )
        )


def _parse_html_formatting(html_text: str) -> list[_FormattedSegment]:
    """Parses inline HTML into a list of formatted segments.

    Adjacent segments with identical formatting are merged.

    Args:
        html_text: HTML string with ``<b>/<i>/<u>/<s>`` and ``<span>`` tags.

    Returns:
        List of _FormattedSegment with merged adjacent segments.
    """
    parser = _InlineHTMLParser()
    parser.feed(html_text)

    # Merge adjacent segments with same formatting
    merged: list[_FormattedSegment] = []
    for seg in parser.segments:
        if not seg.text:
            continue
        if (
            merged
            and merged[-1].bold == seg.bold
            and merged[-1].italic == seg.italic
            and merged[-1].underline == seg.underline
            and merged[-1].strike == seg.strike
            and merged[-1].superscript == seg.superscript
            and merged[-1].subscript == seg.subscript
            and merged[-1].font_size_pt == seg.font_size_pt
            and merged[-1].color_hex == seg.color_hex
            and merged[-1].bg_color_hex == seg.bg_color_hex
            and merged[-1].hyperlink_url == seg.hyperlink_url
        ):
            merged[-1] = _FormattedSegment(
                text=merged[-1].text + seg.text,
                bold=seg.bold,
                italic=seg.italic,
                underline=seg.underline,
                strike=seg.strike,
                superscript=seg.superscript,
                subscript=seg.subscript,
                font_size_pt=seg.font_size_pt,
                color_hex=seg.color_hex,
                bg_color_hex=seg.bg_color_hex,
                hyperlink_url=seg.hyperlink_url,
            )
        else:
            merged.append(seg)
    return merged


# ── DOCX rPr setters ────────────────────────────────────────────────────


def _set_rpr_flag(
    rpr: object,
    tag_name: str,
    value: bool,
    qn_fn: Callable[[str], str],
) -> None:
    """Sets or removes a boolean run-property flag (w:b, w:i, w:strike).

    Args:
        rpr: The <w:rPr> lxml element.
        tag_name: The OOXML tag name, e.g. "w:b", "w:i", "w:strike".
        value: True to set the flag, False to remove it.
        qn_fn: The ``qn()`` namespace resolver from python-docx.
    """
    qualified = qn_fn(tag_name)
    existing = rpr.find(qualified)
    if value:
        if existing is None:
            from docx.oxml import OxmlElement  # noqa: PLC0415

            elem = OxmlElement(tag_name)
            rpr.append(elem)
    elif existing is not None:
        rpr.remove(existing)


def _set_rpr_underline(
    rpr: object,
    value: bool,
    qn_fn: Callable[[str], str],
) -> None:
    """Sets or removes the underline run property (w:u with w:val="single").

    Args:
        rpr: The <w:rPr> lxml element.
        value: True to set underline, False to remove it.
        qn_fn: The ``qn()`` namespace resolver from python-docx.
    """
    qualified = qn_fn("w:u")
    existing = rpr.find(qualified)
    if value:
        if existing is None:
            from docx.oxml import OxmlElement  # noqa: PLC0415

            elem = OxmlElement("w:u")
            elem.set(qn_fn("w:val"), "single")
            rpr.append(elem)
        else:
            existing.set(qn_fn("w:val"), "single")
    elif existing is not None:
        rpr.remove(existing)


def _set_rpr_font_size(
    rpr: object,
    size_pt: float,
    qn_fn: Callable[[str], str],
) -> None:
    """Sets ``w:sz`` and ``w:szCs`` in half-points on a ``<w:rPr>``.

    Args:
        rpr: The ``<w:rPr>`` lxml element.
        size_pt: Font size in points (e.g. 14.0 → half-points 28).
        qn_fn: The ``qn()`` namespace resolver from python-docx.
    """
    from docx.oxml import OxmlElement  # noqa: PLC0415

    half_pts = str(int(size_pt * 2))
    for tag in ("w:sz", "w:szCs"):
        qualified = qn_fn(tag)
        existing = rpr.find(qualified)
        if existing is not None:
            existing.set(qn_fn("w:val"), half_pts)
        else:
            elem = OxmlElement(tag)
            elem.set(qn_fn("w:val"), half_pts)
            rpr.append(elem)


def _set_rpr_vert_align(
    rpr: object,
    superscript: bool,
    subscript: bool,
    qn_fn: Callable[[str], str],
) -> None:
    """Sets or removes ``w:vertAlign`` on a ``<w:rPr>`` for sup/subscript.

    ``<w:vertAlign w:val="superscript"/>`` for superscript,
    ``<w:vertAlign w:val="subscript"/>`` for subscript.  Removes the
    element when neither flag is set.

    Args:
        rpr: The ``<w:rPr>`` lxml element.
        superscript: True to set superscript.
        subscript: True to set subscript.
        qn_fn: The ``qn()`` namespace resolver from python-docx.
    """
    qualified = qn_fn("w:vertAlign")
    existing = rpr.find(qualified)
    if superscript or subscript:
        val = "superscript" if superscript else "subscript"
        if existing is not None:
            existing.set(qn_fn("w:val"), val)
        else:
            from docx.oxml import OxmlElement  # noqa: PLC0415

            elem = OxmlElement("w:vertAlign")
            elem.set(qn_fn("w:val"), val)
            rpr.append(elem)
    elif existing is not None:
        rpr.remove(existing)


def _set_rpr_color(
    rpr: object,
    color_hex: str,
    qn_fn: Callable[[str], str],
) -> None:
    """Sets ``w:color`` val on a ``<w:rPr>``.

    Args:
        rpr: The ``<w:rPr>`` lxml element.
        color_hex: Hex colour like ``"#ff0000"``.
        qn_fn: The ``qn()`` namespace resolver from python-docx.
    """
    from docx.oxml import OxmlElement  # noqa: PLC0415

    val = color_hex.lstrip("#").upper()
    qualified = qn_fn("w:color")
    existing = rpr.find(qualified)
    if existing is not None:
        existing.set(qn_fn("w:val"), val)
    else:
        elem = OxmlElement("w:color")
        elem.set(qn_fn("w:val"), val)
        rpr.append(elem)


# ── DOCX run injection ──────────────────────────────────────────────────


def _inject_html_runs(  # noqa: PLR0912, PLR0915
    para: object,
    html_text: str,
    part: object | None = None,
) -> None:
    """Replaces paragraph runs with HTML-formatted segments.

    If no formatting tags are detected, falls back to
    ``_replace_paragraph_text`` to preserve current behaviour.

    Preserves visual-content runs (images, drawings) in-place and
    copies the base formatting (font name, size, colour) from the
    first text-only run into every newly created run.

    Segments with ``hyperlink_url`` are wrapped in ``<w:hyperlink>``
    elements.  Consecutive segments sharing the same URL are grouped
    under a single ``<w:hyperlink>``.

    Args:
        para: A python-docx Paragraph object.
        html_text: Translated text with inline ``<b>/<i>/<u>/<s>/<a>`` tags.
        part: The python-docx ``DocumentPart`` (``para.part``), used to
            create OPC relationships for external hyperlinks.  When
            ``None``, external hyperlinks are silently dropped.
    """
    if not _FORMATTING_HTML_RE.search(html_text):
        _replace_paragraph_text(para, html_text)
        return

    segments = _parse_html_formatting(html_text)
    if not segments:
        # Strip residual tags so literal HTML doesn't appear in the document
        plain = html.unescape(_STRIP_FORMAT_TAGS_RE.sub("", html_text))
        _replace_paragraph_text(para, plain)
        return

    import copy  # noqa: PLC0415

    from docx.oxml import OxmlElement  # noqa: PLC0415
    from docx.oxml.ns import qn  # noqa: PLC0415

    w_r = qn("w:r")

    # Save base rPr from the first text-only run (font, size, colour…).
    # Check both direct <w:r> and runs inside <w:hyperlink>.
    base_rpr = None
    for child in para._element:
        if base_rpr is not None:
            break
        r_elems = [child] if child.tag == w_r else child.findall(w_r)
        for r_elem in r_elems:
            if not _run_has_visual_content(r_elem):
                found = r_elem.find(qn("w:rPr"))
                if found is not None:
                    base_rpr = copy.deepcopy(found)
                break

    # Strip highlight/shading from base so it doesn't spread to all runs
    if base_rpr is not None:
        for tag in ("w:highlight", "w:shd"):
            existing = base_rpr.find(qn(tag))
            if existing is not None:
                base_rpr.remove(existing)

    # Collect visual-content run elements to preserve
    visual_elems: list[object] = []
    for run in para.runs:
        elem = run._element
        if _run_has_visual_content(elem):
            _clear_run_text_only(elem)
            visual_elems.append(elem)

    # Remove all existing <w:r> and <w:hyperlink> elements
    for child in list(para._element):
        if child.tag in (w_r, _W_HYPERLINK_TAG):
            para._element.remove(child)

    # Re-add visual runs at the end — they will be appended after text
    # (original position is not tracked; images appear after text)

    def _build_run(seg: _FormattedSegment) -> object:
        """Creates a ``<w:r>`` element with formatting from *seg*."""
        new_r = OxmlElement("w:r")
        if base_rpr is not None:
            new_rpr = copy.deepcopy(base_rpr)
        else:
            new_rpr = OxmlElement("w:rPr")
        _set_rpr_flag(new_rpr, "w:b", seg.bold, qn)
        _set_rpr_flag(new_rpr, "w:i", seg.italic, qn)
        _set_rpr_flag(new_rpr, "w:strike", seg.strike, qn)
        _set_rpr_underline(new_rpr, seg.underline, qn)
        _set_rpr_vert_align(new_rpr, seg.superscript, seg.subscript, qn)
        if seg.font_size_pt is not None:
            _set_rpr_font_size(new_rpr, seg.font_size_pt, qn)
        if seg.color_hex is not None:
            _set_rpr_color(new_rpr, seg.color_hex, qn)
        if seg.bg_color_hex is not None:
            shd = OxmlElement("w:shd")
            shd.set(qn("w:val"), "clear")
            shd.set(qn("w:color"), "auto")
            shd.set(qn("w:fill"), seg.bg_color_hex.lstrip("#").upper())
            new_rpr.append(shd)
        new_r.append(new_rpr)
        new_t = OxmlElement("w:t")
        new_t.text = seg.text
        new_t.set(qn("xml:space"), "preserve")
        new_r.append(new_t)
        return new_r

    # Group segments by hyperlink and create runs
    current_url: str | None = None
    hyperlink_elem: object | None = None

    for seg in segments:
        new_r = _build_run(seg)

        if seg.hyperlink_url:
            if seg.hyperlink_url != current_url:
                # Start a new <w:hyperlink> group
                hyperlink_elem = OxmlElement("w:hyperlink")
                if seg.hyperlink_url.startswith("#"):
                    # Internal bookmark anchor
                    hyperlink_elem.set(
                        qn("w:anchor"),
                        seg.hyperlink_url[1:],
                    )
                elif part is not None:
                    # External URL — create/reuse OPC relationship
                    r_id = part.relate_to(
                        seg.hyperlink_url,
                        _HYPERLINK_RELTYPE,
                        is_external=True,
                    )
                    hyperlink_elem.set(qn("r:id"), r_id)
                else:
                    # No part available — cannot create relationship
                    hyperlink_elem = None
                if hyperlink_elem is not None:
                    para._element.append(hyperlink_elem)
                current_url = seg.hyperlink_url
            if hyperlink_elem is not None:
                hyperlink_elem.append(new_r)
            else:
                # Fallback: attach as plain run when part is unavailable
                para._element.append(new_r)
        else:
            current_url = None
            hyperlink_elem = None
            para._element.append(new_r)

    # Re-attach visual-content runs
    for v_elem in visual_elems:
        para._element.append(v_elem)


# ── Visual content helpers ───────────────────────────────────────────────

_MC_ALTERNATE_CONTENT = (
    "{http://schemas.openxmlformats.org/markup-compatibility/2006}AlternateContent"
)


def _run_has_visual_content(run_elem: object) -> bool:
    """Checks if a run XML element contains non-text visual content.

    Looks for inline images (<w:drawing>), legacy pictures (<w:pict>),
    OLE objects (<w:object>), and compatibility wrappers
    (<mc:AlternateContent>) that should be preserved during translation.

    Args:
        run_elem: An lxml element representing a <w:r> element.

    Returns:
        bool: True if the run contains visual content.
    """
    from docx.oxml.ns import qn  # noqa: PLC0415

    visual_tags = (
        qn("w:drawing"),
        qn("w:pict"),
        qn("w:object"),
        _MC_ALTERNATE_CONTENT,
    )
    return any(run_elem.find(tag) is not None for tag in visual_tags)


def _clear_run_text_only(run_elem: object) -> None:
    """Removes only <w:t> text elements from a run, preserving visuals.

    Args:
        run_elem: An lxml element representing a <w:r> element.
    """
    from docx.oxml.ns import qn  # noqa: PLC0415

    for t_elem in run_elem.findall(qn("w:t")):
        run_elem.remove(t_elem)


def _replace_paragraph_text(para: object, new_text: str) -> None:
    """Replaces paragraph text while preserving images and drawings.

    Scans each run for visual content (drawings, pictures, OLE objects).
    Text-only runs are used for the replacement; runs containing visuals
    have only their <w:t> elements removed to preserve images.

    Any ``<w:hyperlink>`` children are removed first to prevent text
    duplication (their runs are not in ``para.runs``).

    Args:
        para: A python-docx Paragraph object.
        new_text: The replacement text.
    """
    # Remove <w:hyperlink> wrappers to prevent duplicate text
    for child in list(para._element):
        if child.tag == _W_HYPERLINK_TAG:
            para._element.remove(child)

    if not para.runs:
        # No runs — no inline images possible, safe to set directly
        para.text = new_text
        return

    text_placed = False
    for run in para.runs:
        elem = run._element
        if _run_has_visual_content(elem):
            # Preserve visual content, only strip text
            _clear_run_text_only(elem)
        elif not text_placed:
            # First text-only run receives the translated text
            run.text = new_text
            text_placed = True
        else:
            # Subsequent text-only runs are cleared
            run.text = ""

    if not text_placed:
        # All runs contained visual content — insert a new text run
        import copy  # noqa: PLC0415

        from docx.oxml import OxmlElement  # noqa: PLC0415
        from docx.oxml.ns import qn  # noqa: PLC0415

        new_r = OxmlElement("w:r")

        # Copy formatting from the first run
        first_rpr = para.runs[0]._element.find(qn("w:rPr"))
        if first_rpr is not None:
            new_r.append(copy.deepcopy(first_rpr))

        # Create text element
        new_t = OxmlElement("w:t")
        new_t.text = new_text
        new_t.set(qn("xml:space"), "preserve")
        new_r.append(new_t)

        # Insert before the first run in the paragraph XML
        first_run_elem = para.runs[0]._element
        para._element.insert(
            list(para._element).index(first_run_elem),
            new_r,
        )


# ── PPTX formatting (python-pptx) ───────────────────────────────────────


def _read_pptx_run_formatting(
    run: object,
) -> tuple[bool, bool, bool, bool, bool, bool]:
    """Reads inline formatting flags from a python-pptx run.

    python-pptx exposes bold/italic/underline via ``run.font`` but not
    strikethrough or superscript/subscript — these are read directly from
    the ``<a:rPr>`` XML element.  Superscript uses a positive ``baseline``
    attribute, subscript uses negative.

    Args:
        run: A python-pptx ``_Run`` object.

    Returns:
        Tuple of (bold, italic, underline, strike, superscript, subscript).
    """
    from pptx.oxml.ns import qn  # noqa: PLC0415

    bold = bool(run.font.bold)
    italic = bool(run.font.italic)
    underline = bool(run.font.underline)
    rpr = run._r.find(qn("a:rPr"))
    strike_val = rpr.get("strike") if rpr is not None else None
    strike = strike_val is not None and strike_val != "noStrike"
    # Superscript/subscript via baseline attribute on <a:rPr>
    superscript = False
    subscript = False
    if rpr is not None:
        baseline_val = rpr.get("baseline")
        if baseline_val is not None:
            with contextlib.suppress(ValueError, TypeError):
                baseline_int = int(baseline_val)
                if baseline_int > 0:
                    superscript = True
                elif baseline_int < 0:
                    subscript = True
    return bold, italic, underline, strike, superscript, subscript


def _read_pptx_run_full_formatting(
    run: object,
) -> tuple[
    bool,
    bool,
    bool,
    bool,
    bool,
    bool,
    float | None,
    str | None,
    str | None,
]:
    """Reads formatting flags plus font size, colour and bg from a PPTX run.

    Font size is read from the ``sz`` attribute on ``<a:rPr>`` (hundredths
    of a point, e.g. 1400 → 14.0 pt).  Colour is read from
    ``<a:solidFill>/<a:srgbClr val="...">`` child.  Background colour is
    read from ``<a:highlight>/<a:srgbClr val="...">``.

    Args:
        run: A python-pptx ``_Run`` object.

    Returns:
        (bold, italic, underline, strike, superscript, subscript,
        font_size_pt, color_hex, bg_color_hex).
    """
    from pptx.oxml.ns import qn  # noqa: PLC0415

    bold, italic, underline, strike, superscript, subscript = _read_pptx_run_formatting(
        run
    )

    rpr = run._r.find(qn("a:rPr"))
    # Font size from sz attribute (hundredths of a point)
    font_size_pt: float | None = None
    if rpr is not None:
        sz_val = rpr.get("sz")
        if sz_val is not None:
            with contextlib.suppress(ValueError, TypeError):
                font_size_pt = int(sz_val) / 100.0

    # Colour from <a:solidFill>/<a:srgbClr val="...">
    color_hex: str | None = None
    if rpr is not None:
        solid_fill = rpr.find(qn("a:solidFill"))
        if solid_fill is not None:
            srgb = solid_fill.find(qn("a:srgbClr"))
            if srgb is not None:
                val = srgb.get("val")
                if val:
                    color_hex = f"#{val}".lower()

    # Background colour from <a:highlight>/<a:srgbClr val="...">
    bg_color_hex: str | None = None
    if rpr is not None:
        highlight_el = rpr.find(qn("a:highlight"))
        if highlight_el is not None:
            srgb = highlight_el.find(qn("a:srgbClr"))
            if srgb is not None:
                val = srgb.get("val")
                if val:
                    bg_color_hex = f"#{val}".lower()

    return (
        bold,
        italic,
        underline,
        strike,
        superscript,
        subscript,
        font_size_pt,
        color_hex,
        bg_color_hex,
    )


def _has_pptx_mixed_formatting(para: object) -> bool:
    """Checks whether a PPTX paragraph has runs with differing formatting.

    Compares bold, italic, underline, strike, superscript, subscript,
    font size and colour.  Only considers runs with non-empty text.
    Returns False if 0 or 1 text runs remain.

    Args:
        para: A python-pptx ``_Paragraph`` object.

    Returns:
        True if at least two text runs have different formatting.
    """
    sigs: list[
        tuple[
            bool,
            bool,
            bool,
            bool,
            bool,
            bool,
            float | None,
            str | None,
            str | None,
        ]
    ] = []
    for run in para.runs:
        if not run.text:
            continue
        sigs.append(_read_pptx_run_full_formatting(run))
    if len(sigs) <= 1:
        return False
    return len(set(sigs)) > 1


def _has_pptx_hyperlinks(para: object) -> bool:
    """Checks whether a PPTX paragraph has any runs with hyperlinks.

    Args:
        para: A python-pptx ``_Paragraph`` object.

    Returns:
        True if at least one non-empty run has a hyperlink address.
    """
    for run in para.runs:
        if not run.text:
            continue
        try:
            if run.hyperlink.address:
                return True
        except Exception:  # noqa: BLE001
            continue
    return False


def _pptx_runs_to_html(para: object) -> str:
    """Converts a PPTX paragraph's runs to inline HTML.

    Two-pass: first collects run data to detect size/colour/bg variation,
    then emits HTML with ``<span>`` only when values actually vary.
    Runs with hyperlinks are wrapped in ``<a href="...">`` tags.

    Args:
        para: A python-pptx ``_Paragraph`` object.

    Returns:
        HTML string representing the paragraph's formatted text.
    """
    # Pass 1: collect run data (including hyperlink URL)
    run_data: list[
        tuple[
            str,
            bool,
            bool,
            bool,
            bool,
            bool,
            bool,
            float | None,
            str | None,
            str | None,
            str | None,
        ]
    ] = []
    for run in para.runs:
        if not run.text:
            continue
        b, i, u, s, sup, sub, sz, clr, bg = _read_pptx_run_full_formatting(run)
        url: str | None = None
        with contextlib.suppress(Exception):
            url = run.hyperlink.address
        run_data.append((run.text, b, i, u, s, sup, sub, sz, clr, bg, url))

    if not run_data:
        return ""

    # Detect variation — base is always None for safe roundtrip
    sizes = [d[7] for d in run_data]
    colors = [d[8] for d in run_data]
    bgs = [d[9] for d in run_data]
    has_size_variation = len(set(sizes)) > 1
    has_color_variation = len(set(colors)) > 1
    has_bg_variation = len(set(bgs)) > 1
    base_size = None
    base_color = None
    base_bg = None

    # Pass 2: emit HTML with <a> grouping for consecutive same-URL runs
    parts: list[str] = []
    current_url: str | None = None
    for (
        text,
        bold,
        italic,
        underline,
        strike,
        sup,
        sub,
        sz,
        clr,
        bg,
        url,
    ) in run_data:
        # Close previous <a> if URL changed
        if url != current_url:
            if current_url is not None:
                parts.append("</a>")
            if url is not None:
                parts.append(f'<a href="{html.escape(url, quote=True)}">')
            current_url = url

        parts.append(
            _wrap_with_tags(
                html.escape(text),
                bold,
                italic,
                underline,
                strike,
                sz if sz != base_size else None,
                clr if clr != base_color else None,
                has_size_variation=has_size_variation,
                has_color_variation=has_color_variation,
                bg_color_hex=bg if bg != base_bg else None,
                has_bg_variation=has_bg_variation,
                superscript=sup,
                subscript=sub,
            )
        )
    # Close trailing <a> tag
    if current_url is not None:
        parts.append("</a>")
    return "".join(parts)


def _pptx_plain_fallback(para: object, text: str) -> None:
    """Puts plain text into the first run, clears the rest.

    Args:
        para: A python-pptx ``_Paragraph`` object.
        text: Plain text to inject.
    """
    if para.runs:
        para.runs[0].text = text
        for run in para.runs[1:]:
            run.text = ""
    else:
        para.text = text


def _apply_drawingml_format_attrs(  # noqa: PLR0912
    rpr: object,
    seg: _FormattedSegment,
) -> None:
    """Sets DrawingML formatting attributes on a raw ``<a:rPr>`` lxml element.

    Sets bold/italic/underline/strike attrs, superscript/subscript via
    ``baseline``, plus per-segment font size (``sz``) and text colour
    (``<a:solidFill>/<a:srgbClr>``).  Works with any DrawingML
    ``<a:rPr>`` element — used by both PPTX and XLSX paths.

    Args:
        rpr: The ``<a:rPr>`` lxml element.
        seg: Segment whose formatting flags are applied.
    """
    _fmt_map = {"b": "1", "i": "1", "u": "sng", "strike": "sngStrike"}
    for attr, flag in zip(
        ("b", "i", "u", "strike"),
        (seg.bold, seg.italic, seg.underline, seg.strike),
        strict=True,
    ):
        if flag:
            rpr.set(attr, _fmt_map[attr])

    # Superscript/subscript via baseline attribute
    if seg.superscript:
        rpr.set("baseline", "30000")
    elif seg.subscript:
        rpr.set("baseline", "-25000")

    # Per-run font size (hundredths of a point)
    if seg.font_size_pt is not None:
        rpr.set("sz", str(int(seg.font_size_pt * 100)))

    # Per-run text colour via <a:solidFill>/<a:srgbClr>
    a_srgb_clr_tag = f"{{{_DRAWINGML_NS}}}srgbClr"
    if seg.color_hex is not None:
        a_solid_fill_tag = f"{{{_DRAWINGML_NS}}}solidFill"
        solid_fill = rpr.find(a_solid_fill_tag)
        if solid_fill is None:
            solid_fill = etree.SubElement(rpr, a_solid_fill_tag)
        srgb = solid_fill.find(a_srgb_clr_tag)
        if srgb is None:
            srgb = etree.SubElement(solid_fill, a_srgb_clr_tag)
        srgb.set("val", seg.color_hex.lstrip("#").upper())

    # Per-run background colour via <a:highlight>/<a:srgbClr>
    a_highlight_tag = f"{{{_DRAWINGML_NS}}}highlight"
    if seg.bg_color_hex is not None:
        hl = rpr.find(a_highlight_tag)
        if hl is None:
            hl = etree.SubElement(rpr, a_highlight_tag)
        srgb = hl.find(a_srgb_clr_tag)
        if srgb is None:
            srgb = etree.SubElement(hl, a_srgb_clr_tag)
        srgb.set("val", seg.bg_color_hex.lstrip("#").upper())
    else:
        # Remove existing highlight if segment has no bg
        hl = rpr.find(a_highlight_tag)
        if hl is not None:
            rpr.remove(hl)


def _apply_pptx_format_attrs(rpr: object, seg: _FormattedSegment) -> None:
    """Sets DrawingML formatting attributes on an ``<a:rPr>`` element.

    Thin wrapper around ``_apply_drawingml_format_attrs`` for backward
    compatibility with the PPTX injection path.

    Args:
        rpr: The ``<a:rPr>`` lxml element.
        seg: Segment whose formatting flags are applied.
    """
    _apply_drawingml_format_attrs(rpr, seg)


def _inject_pptx_html_runs(
    para: object,
    html_text: str,
    part: object | None = None,
) -> None:
    """Replaces PPTX paragraph runs with HTML-formatted segments.

    If no formatting tags are detected, falls back to putting all text
    into the first run (current behaviour). Copies base ``<a:rPr>``
    properties (font, size, colour, language) from the first run into
    every newly created run, then sets formatting attributes.

    When ``part`` is provided, segments with ``hyperlink_url`` get an
    ``<a:hlinkClick>`` element created inside ``<a:rPr>`` with a
    relationship ID pointing to the URL.

    Args:
        para: A python-pptx ``_Paragraph`` object.
        html_text: Translated text with inline ``<b>/<i>/<u>/<s>/<a>`` tags.
        part: The slide ``Part`` object for creating hyperlink relationships.
    """
    import copy  # noqa: PLC0415

    from pptx.oxml.ns import qn  # noqa: PLC0415

    # Fallback: no formatting tags → plain text into first run
    if not _FORMATTING_HTML_RE.search(html_text):
        _pptx_plain_fallback(para, html_text)
        return

    segments = _parse_html_formatting(html_text)
    if not segments:
        # Strip residual tags so literal HTML doesn't appear in the document
        plain = html.unescape(_STRIP_FORMAT_TAGS_RE.sub("", html_text))
        _pptx_plain_fallback(para, plain)
        return

    p_elem = para._p  # <a:p> element

    # Save base rPr from the first run (deep copy, strip formatting attrs)
    base_rpr = None
    for run in para.runs:
        rpr = run._r.find(qn("a:rPr"))
        if rpr is not None:
            base_rpr = copy.deepcopy(rpr)
            for attr in _PPTX_FORMAT_ATTRS:
                base_rpr.attrib.pop(attr, None)
            # Also strip any existing <a:hlinkClick> from the base
            for hlink in list(base_rpr.findall(qn("a:hlinkClick"))):
                base_rpr.remove(hlink)
            break

    # Remove all <a:r> elements from <a:p>
    for r_elem in list(p_elem.findall(qn("a:r"))):
        p_elem.remove(r_elem)

    # Create new <a:r> elements for each segment
    for seg in segments:
        new_r = etree.SubElement(p_elem, qn("a:r"))

        # Build rPr: start from base, then apply formatting attrs
        if base_rpr is not None:
            new_rpr = copy.deepcopy(base_rpr)
            new_r.insert(0, new_rpr)
        else:
            new_rpr = etree.SubElement(new_r, qn("a:rPr"))

        _apply_pptx_format_attrs(new_rpr, seg)

        # Add <a:hlinkClick> for hyperlinks
        if seg.hyperlink_url and part is not None:
            r_id = part.relate_to(
                seg.hyperlink_url,
                _HYPERLINK_RELTYPE,
                is_external=True,
            )
            hlink_elem = etree.SubElement(new_rpr, qn("a:hlinkClick"))
            hlink_elem.set(qn("r:id"), r_id)

        # Create <a:t> text element
        new_t = etree.SubElement(new_r, qn("a:t"))
        new_t.text = seg.text
        # Preserve whitespace
        new_t.set(
            "{http://www.w3.org/XML/1998/namespace}space",
            "preserve",
        )


# ── DrawingML per-run formatting (raw lxml) ─────────────────────────────


def _read_drawingml_rpr_formatting(
    rpr_el: object | None,
) -> tuple[bool, bool, bool, bool, bool, bool, float | None, str | None, str | None]:
    """Reads formatting flags from a raw DrawingML ``<a:rPr>`` element.

    Returns a 9-tuple operating on a plain lxml element instead of a
    python-pptx Run object.

    Args:
        rpr_el: The ``<a:rPr>`` lxml element, or None.

    Returns:
        (bold, italic, underline, strike, superscript, subscript,
        font_size_pt, color_hex, bg_color_hex).
    """
    if rpr_el is None:
        return (False, False, False, False, False, False, None, None, None)

    bold = rpr_el.get("b") == "1"
    italic = rpr_el.get("i") == "1"

    u_val = rpr_el.get("u")
    underline = u_val is not None and u_val != "none"

    strike_val = rpr_el.get("strike")
    strike = strike_val is not None and strike_val != "noStrike"

    # Superscript/subscript via baseline attribute (positive=super, negative=sub)
    superscript = False
    subscript = False
    baseline_val = rpr_el.get("baseline")
    if baseline_val is not None:
        with contextlib.suppress(ValueError, TypeError):
            baseline_int = int(baseline_val)
            if baseline_int > 0:
                superscript = True
            elif baseline_int < 0:
                subscript = True

    # Font size from sz attribute (hundredths of a point)
    font_size_pt: float | None = None
    sz_val = rpr_el.get("sz")
    if sz_val is not None:
        with contextlib.suppress(ValueError, TypeError):
            font_size_pt = int(sz_val) / 100.0

    # Colour from <a:solidFill>/<a:srgbClr val="...">
    color_hex: str | None = None
    a_srgb_clr_tag = f"{{{_DRAWINGML_NS}}}srgbClr"
    a_solid_fill_tag = f"{{{_DRAWINGML_NS}}}solidFill"
    solid_fill = rpr_el.find(a_solid_fill_tag)
    if solid_fill is not None:
        srgb = solid_fill.find(a_srgb_clr_tag)
        if srgb is not None:
            val = srgb.get("val")
            if val:
                color_hex = f"#{val}".lower()

    # Background colour from <a:highlight>/<a:srgbClr val="...">
    bg_color_hex: str | None = None
    a_highlight_tag = f"{{{_DRAWINGML_NS}}}highlight"
    highlight_el = rpr_el.find(a_highlight_tag)
    if highlight_el is not None:
        srgb = highlight_el.find(a_srgb_clr_tag)
        if srgb is not None:
            val = srgb.get("val")
            if val:
                bg_color_hex = f"#{val}".lower()

    return (
        bold,
        italic,
        underline,
        strike,
        superscript,
        subscript,
        font_size_pt,
        color_hex,
        bg_color_hex,
    )


def _has_drawingml_mixed_formatting(tx_body_el: object) -> bool:
    """Checks whether a DrawingML ``<a:txBody>`` has runs with varying formatting.

    Only considers ``<a:r>`` elements with non-empty ``<a:t>`` text.
    Returns ``True`` when at least two runs have different formatting
    signatures (bold, italic, underline, strike, font size, colour, bg).

    Args:
        tx_body_el: An lxml element representing ``<a:txBody>``.

    Returns:
        True if at least two text runs have different formatting.
    """
    a_p_tag = f"{{{_DRAWINGML_NS}}}p"
    a_r_tag = f"{{{_DRAWINGML_NS}}}r"
    a_rpr_tag = f"{{{_DRAWINGML_NS}}}rPr"
    a_t_tag = f"{{{_DRAWINGML_NS}}}t"

    sigs: set[
        tuple[
            bool,
            bool,
            bool,
            bool,
            bool,
            bool,
            float | None,
            str | None,
            str | None,
        ]
    ] = set()
    for p_el in tx_body_el.findall(a_p_tag):
        for r_el in p_el.findall(a_r_tag):
            t_el = r_el.find(a_t_tag)
            if t_el is None or not t_el.text:
                continue
            rpr = r_el.find(a_rpr_tag)
            sigs.add(_read_drawingml_rpr_formatting(rpr))
            if len(sigs) > 1:
                return True
    return False


def _has_drawingml_hyperlinks(tx_body_el: object) -> bool:
    """Checks whether a DrawingML ``<a:txBody>`` has any runs with hyperlinks.

    Scans all ``<a:rPr>`` elements for ``<a:hlinkClick>`` children, which
    indicate that the run is part of a hyperlink.

    Args:
        tx_body_el: An lxml element representing ``<a:txBody>``.

    Returns:
        True if at least one ``<a:rPr>`` contains ``<a:hlinkClick>``.
    """
    a_rpr_tag = f"{{{_DRAWINGML_NS}}}rPr"
    a_hlink_tag = f"{{{_DRAWINGML_NS}}}hlinkClick"
    return any(rpr.find(a_hlink_tag) is not None for rpr in tx_body_el.iter(a_rpr_tag))


def _drawingml_to_html(  # noqa: PLR0912, PLR0915
    tx_body_el: object,
    hyperlink_rels: dict[str, str] | None = None,
) -> str:
    r"""Converts a DrawingML ``<a:txBody>`` element's runs to inline HTML.

    Two-pass approach: first collects all run data, detects whether font
    sizes or colours vary across the body, then emits HTML via
    ``_wrap_with_tags``.  Paragraphs are separated by ``'\n'``.

    When *hyperlink_rels* is provided, ``<a:hlinkClick>`` elements inside
    ``<a:rPr>`` are resolved to URLs and consecutive same-URL runs are
    grouped under ``<a href="...">`` tags.

    Args:
        tx_body_el: An lxml element representing ``<a:txBody>``.
        hyperlink_rels: Mapping of relationship IDs to target URLs,
            parsed from the drawing's ``.rels`` file.

    Returns:
        Inline-HTML string, or plain text if no formatting variation.
    """
    a_p_tag = f"{{{_DRAWINGML_NS}}}p"
    a_r_tag = f"{{{_DRAWINGML_NS}}}r"
    a_br_tag = f"{{{_DRAWINGML_NS}}}br"
    a_rpr_tag = f"{{{_DRAWINGML_NS}}}rPr"
    a_t_tag = f"{{{_DRAWINGML_NS}}}t"
    a_hlink_tag = f"{{{_DRAWINGML_NS}}}hlinkClick"
    r_id_attr = (
        "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
    )

    # Pass 1 — collect run data per paragraph (including bg colour + URL)
    all_run_data: list[
        tuple[
            str,
            bool,
            bool,
            bool,
            bool,
            bool,
            bool,
            float | None,
            str | None,
            str | None,
            str | None,
        ]
    ] = []
    para_spans: list[tuple[int, int]] = []

    for p_el in tx_body_el.findall(a_p_tag):
        para_start = len(all_run_data)
        for child in p_el:
            if child.tag == a_br_tag:
                # Preserve <a:br/> as newline within the paragraph
                _br_entry = (
                    "\n",
                    False,
                    False,
                    False,
                    False,
                    False,
                    False,
                    None,
                    None,
                    None,
                    None,
                )
                all_run_data.append(_br_entry)
            elif child.tag == a_r_tag:
                t_el = child.find(a_t_tag)
                if t_el is None or not t_el.text:
                    continue
                rpr = child.find(a_rpr_tag)
                b, i, u, s, sup, sub, sz, clr, bg = _read_drawingml_rpr_formatting(rpr)
                # Check for hyperlink
                url: str | None = None
                if rpr is not None and hyperlink_rels:
                    hlink = rpr.find(a_hlink_tag)
                    if hlink is not None:
                        rid = hlink.get(r_id_attr)
                        if rid and rid in hyperlink_rels:
                            url = hyperlink_rels[rid]
                all_run_data.append((t_el.text, b, i, u, s, sup, sub, sz, clr, bg, url))
        para_spans.append((para_start, len(all_run_data)))

    if not all_run_data:
        return ""

    # Detect variation — base is always None for safe roundtrip
    sizes = [d[7] for d in all_run_data]
    colors = [d[8] for d in all_run_data]
    bgs = [d[9] for d in all_run_data]
    has_size_variation = len(set(sizes)) > 1
    has_color_variation = len(set(colors)) > 1
    has_bg_variation = len(set(bgs)) > 1
    # base_size/color/bg are always None so every run with an explicit value
    # gets its own <span>.  Using most-common as base loses that value during
    # injection when the first run is not the most-common one.
    base_size = None
    base_color = None
    base_bg = None

    # Pass 2 — emit HTML with <a> grouping for consecutive same-URL runs
    para_htmls: list[str] = []
    for start, end in para_spans:
        parts: list[str] = []
        current_url: str | None = None
        for (
            text,
            bold,
            italic,
            underline,
            strike,
            sup,
            sub,
            sz,
            clr,
            bg,
            url,
        ) in all_run_data[start:end]:
            # Manage <a> tag transitions
            if url != current_url:
                if current_url is not None:
                    parts.append("</a>")
                if url is not None:
                    parts.append(f'<a href="{html.escape(url, quote=True)}">')
                current_url = url
            parts.append(
                _wrap_with_tags(
                    html.escape(text),
                    bold,
                    italic,
                    underline,
                    strike,
                    sz if sz != base_size else None,
                    clr if clr != base_color else None,
                    has_size_variation=has_size_variation,
                    has_color_variation=has_color_variation,
                    bg_color_hex=bg if bg != base_bg else None,
                    has_bg_variation=has_bg_variation,
                    superscript=sup,
                    subscript=sub,
                ),
            )
        # Close trailing <a> tag
        if current_url is not None:
            parts.append("</a>")
        if parts:
            para_htmls.append("".join(parts))
    return "\n".join(para_htmls)


# ── WordML rPr formatting (DOCX text boxes via lxml) ────────────────────


def _read_wml_rpr_sup_sub(
    rpr_el: object | None,
) -> tuple[bool, bool]:
    """Reads superscript/subscript from a ``<w:rPr>`` element.

    Checks ``<w:vertAlign w:val="superscript|subscript"/>``.

    Args:
        rpr_el: An lxml element for ``<w:rPr>``, or ``None``.

    Returns:
        (superscript, subscript) booleans.
    """
    if rpr_el is None:
        return (False, False)

    w = _WORDML_NS
    va_el = rpr_el.find(f"{{{w}}}vertAlign")
    if va_el is None:
        return (False, False)
    val = va_el.get(f"{{{w}}}val") or va_el.get("val") or ""
    return (val == "superscript", val == "subscript")


def _read_wml_rpr_formatting(
    rpr_el: object | None,
) -> tuple[bool, bool, bool, bool, float | None, str | None, str | None]:
    """Reads inline formatting from a ``<w:rPr>`` element.

    Parses ``<w:b>``, ``<w:i>``, ``<w:u>``, ``<w:strike>``, ``<w:sz>``
    (half-points → pt), ``<w:color>`` (hex → ``"#rrggbb"``), and background
    colour from ``<w:shd>``/``<w:highlight>``.

    Args:
        rpr_el: An lxml element for ``<w:rPr>``, or ``None``.

    Returns:
        Tuple of (bold, italic, underline, strike, font_size_pt, color_hex,
        bg_color_hex).
    """
    if rpr_el is None:
        return (False, False, False, False, None, None, None)

    w = _WORDML_NS

    def _get_val(el: object, default: str = "") -> str:
        """Gets ``val`` attribute, checking both namespaced and unnamespaced forms."""
        return el.get(f"{{{w}}}val") or el.get("val") or default

    def _elem_is_on(tag_name: str) -> bool:
        """Returns True when the child element is present and not val='0'."""
        el = rpr_el.find(f"{{{w}}}{tag_name}")
        if el is None:
            return False
        val = _get_val(el, "true").lower()
        return val not in ("0", "false")

    bold = _elem_is_on("b")
    italic = _elem_is_on("i")
    # Underline: <w:u w:val="none"/> means off; any other val means on.
    u_el = rpr_el.find(f"{{{w}}}u")
    underline = u_el is not None and _get_val(u_el, "single") != "none"
    strike = _elem_is_on("strike")

    # Font size: <w:sz w:val="28"/> = 14 pt (half-points ÷ 2)
    sz_el = rpr_el.find(f"{{{w}}}sz")
    font_size_pt: float | None = None
    if sz_el is not None:
        sz_val = _get_val(sz_el)
        if sz_val and sz_val.isdigit():
            font_size_pt = int(sz_val) / 2.0

    # Color: <w:color w:val="FF0000"/> — 6-char hex; "auto" means inherit
    color_el = rpr_el.find(f"{{{w}}}color")
    color_hex: str | None = None
    if color_el is not None:
        val = _get_val(color_el, "auto")
        if val and val.lower() != "auto" and len(val) == 6:  # noqa: PLR2004
            color_hex = f"#{val.lower()}"

    # Background: <w:shd w:fill="FFFF00"/> or <w:highlight w:val="yellow"/>
    bg_color_hex: str | None = None
    shd_el = rpr_el.find(f"{{{w}}}shd")
    if shd_el is not None:
        fill = shd_el.get(f"{{{w}}}fill") or shd_el.get("fill") or ""
        if fill and fill.lower() not in ("auto", "") and len(fill) == 6:  # noqa: PLR2004
            bg_color_hex = f"#{fill.lower()}"
    if bg_color_hex is None:
        hl_el = rpr_el.find(f"{{{w}}}highlight")
        if hl_el is not None:
            hl_name = (_get_val(hl_el) or "").lower()
            bg_color_hex = _HIGHLIGHT_COLORS.get(hl_name)

    return (bold, italic, underline, strike, font_size_pt, color_hex, bg_color_hex)


def _parse_docx_char_styles(
    zf: zipfile.ZipFile,
) -> dict[str, tuple[bool, bool, bool, bool, float | None, str | None, str | None]]:
    """Parses character style formatting from ``word/styles.xml``.

    Reads ``<w:style>`` elements with ``w:type="character"`` (or paragraph
    styles that carry ``<w:rPr>``) and extracts their run formatting via
    ``_read_wml_rpr_formatting``.

    Args:
        zf: An open ``ZipFile`` for a ``.docx`` archive.

    Returns:
        Mapping of style ID to
        ``(bold, italic, underline, strike, size, color, bg_color)``.
    """
    if "word/styles.xml" not in zf.namelist():
        return {}

    w = _WORDML_NS
    style_tag = f"{{{w}}}style"
    rpr_tag = f"{{{w}}}rPr"
    root = etree.fromstring(zf.read("word/styles.xml"))
    result: dict[
        str, tuple[bool, bool, bool, bool, float | None, str | None, str | None]
    ] = {}

    for style_el in root.iter(style_tag):
        # Accept character styles and paragraph styles with rPr
        style_id = style_el.get(f"{{{w}}}styleId") or style_el.get("styleId")
        if not style_id:
            continue
        rpr_el = style_el.find(rpr_tag)
        if rpr_el is None:
            continue
        result[style_id] = _read_wml_rpr_formatting(rpr_el)

    return result


# ── ODF text box formatting ─────────────────────────────────────────────


def _read_odf_span_formatting(
    style_map: dict[str, object],
    style_name: str,
) -> tuple[bool, bool, bool, bool, bool, bool, float | None, str | None, str | None]:
    """Reads formatting properties from an ODF text style definition.

    Looks up ``style_name`` in ``style_map`` and reads
    ``<style:text-properties>`` attributes for bold, italic, underline,
    strikethrough, superscript/subscript (via ``style:text-position``),
    font size, colour, and background colour.

    Args:
        style_map: Mapping of style names to ``<style:style>`` elements.
        style_name: The ``text:style-name`` attribute value.

    Returns:
        (bold, italic, underline, strike, superscript, subscript,
        font_size_pt, color_hex, bg_color_hex).
    """
    style_el = style_map.get(style_name)
    if style_el is None:
        return (False, False, False, False, False, False, None, None, None)

    text_props_tag = f"{{{_ODF_NS['style']}}}text-properties"
    text_props = style_el.find(text_props_tag)
    if text_props is None:
        return (False, False, False, False, False, False, None, None, None)

    fo_ns = _ODF_NS["fo"]
    style_ns = _ODF_NS["style"]

    bold = text_props.get(f"{{{fo_ns}}}font-weight") == "bold"
    italic = text_props.get(f"{{{fo_ns}}}font-style") == "italic"

    ul_val = text_props.get(f"{{{style_ns}}}text-underline-style")
    underline = ul_val is not None and ul_val not in ("none", "")

    lt_val = text_props.get(f"{{{style_ns}}}text-line-through-style")
    strike = lt_val is not None and lt_val not in ("none", "")

    # Superscript/subscript via style:text-position (e.g. "super 58%" / "sub 58%")
    superscript = False
    subscript = False
    tp_val = text_props.get(f"{{{style_ns}}}text-position", "")
    if tp_val.startswith("super"):
        superscript = True
    elif tp_val.startswith("sub"):
        subscript = True

    # Font size (e.g. "14pt")
    font_size_pt: float | None = None
    size_val = text_props.get(f"{{{fo_ns}}}font-size")
    if size_val and size_val.endswith("pt"):
        with contextlib.suppress(ValueError):
            font_size_pt = float(size_val[:-2])

    # Colour (e.g. "#ff0000")
    color_hex: str | None = None
    color_val = text_props.get(f"{{{fo_ns}}}color")
    if color_val and color_val.startswith("#") and len(color_val) == 7:  # noqa: PLR2004
        color_hex = color_val.lower()

    # Background colour (e.g. "#ffff00")
    bg_color_hex: str | None = None
    bg_val = text_props.get(f"{{{fo_ns}}}background-color")
    if bg_val and bg_val.startswith("#") and len(bg_val) == 7:  # noqa: PLR2004
        bg_color_hex = bg_val.lower()

    return (
        bold,
        italic,
        underline,
        strike,
        superscript,
        subscript,
        font_size_pt,
        color_hex,
        bg_color_hex,
    )


def _has_odf_text_box_mixed_formatting(
    text_box_el: object,
    style_map: dict[str, object],
    text_p_tag: str,
) -> bool:
    """Checks whether an ODF ``<draw:text-box>`` has spans with varying formatting.

    Collects formatting signatures from direct text (default formatting)
    and ``<text:span>`` children.  Returns ``True`` when at least two
    segments have different formatting, or when any ``<text:a>`` hyperlink
    is present (hyperlinks require HTML round-trip to preserve URLs).

    Args:
        text_box_el: An lxml element for ``<draw:text-box>``.
        style_map: Mapping of style names to style elements.
        text_p_tag: The fully-qualified ``<text:p>`` tag name.

    Returns:
        True if formatting varies within the text box.
    """
    text_span_tag = f"{{{_ODF_NS['text']}}}span"
    text_a_tag = f"{{{_ODF_NS['text']}}}a"
    text_style_attr = f"{{{_ODF_NS['text']}}}style-name"
    default_sig = (False, False, False, False, False, False, None, None, None)

    sigs: set[
        tuple[
            bool,
            bool,
            bool,
            bool,
            bool,
            bool,
            float | None,
            str | None,
            str | None,
        ]
    ] = set()

    for p_el in text_box_el.findall(text_p_tag):
        # Direct text before first child
        if p_el.text and p_el.text.strip():
            sigs.add(default_sig)
        for child in p_el:
            if child.tag == text_a_tag:
                # Hyperlinks always require HTML round-trip
                return True
            if child.tag == text_span_tag:
                child_text = child.text or ""
                tail_text = child.tail or ""
                style_name = child.get(text_style_attr, "")
                if child_text.strip():
                    sigs.add(_read_odf_span_formatting(style_map, style_name))
                # tail text after a span has default formatting
                if tail_text.strip():
                    sigs.add(default_sig)
            elif child.tail and child.tail.strip():
                sigs.add(default_sig)
        if len(sigs) > 1:
            return True
    return False


def _odf_text_box_to_html(  # noqa: PLR0912
    text_box_el: object,
    style_map: dict[str, object],
    text_p_tag: str,
) -> str:
    r"""Converts an ODF text box's content to inline HTML.

    Two-pass approach: collects run data from ``<text:span>`` and
    ``<text:a>`` children and direct text, detects size/colour variation,
    then emits HTML via ``_wrap_with_tags``.  Paragraphs are separated by
    ``'\n'``.  Hyperlinks (``<text:a>``) are preserved as ``<a href>`` tags.

    Args:
        text_box_el: An lxml element for ``<draw:text-box>``.
        style_map: Mapping of style names to style elements.
        text_p_tag: The fully-qualified ``<text:p>`` tag name.

    Returns:
        Inline-HTML string representing the text box content.
    """
    text_span_tag = f"{{{_ODF_NS['text']}}}span"
    text_a_tag = f"{{{_ODF_NS['text']}}}a"
    xlink_href = f"{{{_ODF_NS['xlink']}}}href"
    text_style_attr = f"{{{_ODF_NS['text']}}}style-name"
    default_fmt = (False, False, False, False, False, False, None, None, None)

    # Pass 1 — collect all run data (text, formatting, hyperlink_url)
    # Each tuple: (text, b, i, u, s, sup, sub, size, color, bg, url)
    all_run_data: list[
        tuple[
            str,
            bool,
            bool,
            bool,
            bool,
            bool,
            bool,
            float | None,
            str | None,
            str | None,
            str | None,
        ]
    ] = []
    para_spans: list[tuple[int, int]] = []

    for p_el in text_box_el.findall(text_p_tag):
        para_start = len(all_run_data)
        # Direct text before first child
        if p_el.text and p_el.text.strip():
            b, i, u, s, sup, sub, sz, clr, bg = default_fmt
            all_run_data.append((p_el.text, b, i, u, s, sup, sub, sz, clr, bg, None))
        for child in p_el:
            if child.tag == text_a_tag:
                # ODF hyperlink — extract URL and link text
                url = child.get(xlink_href, "")
                link_text = child.text or ""
                if link_text:
                    b, i, u, s, sup, sub, sz, clr, bg = default_fmt
                    all_run_data.append(
                        (link_text, b, i, u, s, sup, sub, sz, clr, bg, url or None),
                    )
                # tail text after the hyperlink has default formatting
                if child.tail:
                    b, i, u, s, sup, sub, sz, clr, bg = default_fmt
                    all_run_data.append(
                        (child.tail, b, i, u, s, sup, sub, sz, clr, bg, None),
                    )
            elif child.tag == text_span_tag:
                child_text = child.text or ""
                if child_text:
                    style_name = child.get(text_style_attr, "")
                    b, i, u, s, sup, sub, sz, clr, bg = _read_odf_span_formatting(
                        style_map,
                        style_name,
                    )
                    all_run_data.append(
                        (child_text, b, i, u, s, sup, sub, sz, clr, bg, None),
                    )
                # tail text after span = default formatting
                if child.tail:
                    b, i, u, s, sup, sub, sz, clr, bg = default_fmt
                    all_run_data.append(
                        (child.tail, b, i, u, s, sup, sub, sz, clr, bg, None),
                    )
            elif child.tail:
                b, i, u, s, sup, sub, sz, clr, bg = default_fmt
                all_run_data.append(
                    (child.tail, b, i, u, s, sup, sub, sz, clr, bg, None),
                )
        para_spans.append((para_start, len(all_run_data)))

    if not all_run_data:
        return ""

    # Detect size/colour/bg variation — base is always None for safe roundtrip
    sizes = [d[7] for d in all_run_data]
    colors = [d[8] for d in all_run_data]
    bgs = [d[9] for d in all_run_data]
    has_size_variation = len(set(sizes)) > 1
    has_color_variation = len(set(colors)) > 1
    has_bg_variation = len(set(bgs)) > 1
    # base_size/color/bg are always None so every run with an explicit value
    # gets its own <span>.  Using most-common as base loses that value during
    # injection when the first run is not the most-common one.
    base_size = None
    base_color = None
    base_bg = None

    # Pass 2 — emit HTML
    para_htmls: list[str] = []
    for start, end in para_spans:
        parts: list[str] = []
        for (
            text,
            bold,
            italic,
            underline,
            strike,
            sup,
            sub,
            sz,
            clr,
            bg,
            link_url,
        ) in all_run_data[start:end]:
            parts.append(
                _wrap_with_tags(
                    html.escape(text),
                    bold,
                    italic,
                    underline,
                    strike,
                    sz if sz != base_size else None,
                    clr if clr != base_color else None,
                    has_size_variation=has_size_variation,
                    has_color_variation=has_color_variation,
                    bg_color_hex=bg if bg != base_bg else None,
                    has_bg_variation=has_bg_variation,
                    superscript=sup,
                    subscript=sub,
                    hyperlink_url=link_url,
                ),
            )
        if parts:
            para_htmls.append("".join(parts))
    return "\n".join(para_htmls)
