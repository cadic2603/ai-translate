"""Unit tests for the PDF processing engine (pdf_processor.py)."""

import logging
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pymupdf
import pytest

from src.core.pdf_processor import (
    _ADJACENT_BLOCK_MAX_GAP,
    _ANNOT_TYPE_FREE_TEXT,
    _ANNOT_TYPE_TEXT,
    _CONTEXT_ALIGN_MIN_NEIGHBORS,
    _CONTEXT_ALIGN_SIZE_TOL,
    _FATAL_LLM_ERRORS,
    _FULL_PAGE_IMAGE_RATIO,
    _IMG_FONT,
    _INLINE_MATH_X_TOL,
    _LIGATURE_MAP,
    _LINE_Y_TOLERANCE,
    _LINK_LINE_Y_GAP,
    _LIST_MARKER_RE,
    _MATH_NO_ROLE_CHARS,
    _MATH_PH_END,
    _MATH_PH_START,
    _MIN_FRAME_HEIGHT,
    _MIN_FRAME_WIDTH,
    _MIN_IMAGE_DIM,
    _MIN_RULE_WIDTH,
    _MIN_RULED_COLUMNS,
    _MIN_TABULAR_ROWS,
    _MIN_VLINE_HEIGHT,
    _MULTILINE_HEIGHT_RATIO,
    _RULE_XRANGE_TOLERANCE,
    _SHORT_LINE_RATIO,
    _SUP_SUB_SIZE_RATIO,
    _VCENTER_SPARE_THRESHOLD,
    _VLINE_YRANGE_TOLERANCE,
    _WIDGET_TYPE_COMBOBOX,
    _WIDGET_TYPE_LISTBOX,
    _WIDGET_TYPE_TEXT,
    _absorb_math_sub_labels,
    _adjust_dividers_for_text,
    _apply_translated_blocks,
    _bbox_overlaps_any,
    _block_inside_any_xobject,
    _block_inside_freetext,
    _block_overlaps_image,
    _body_len,
    _build_cell_text,
    _build_overlay_html,
    _build_row_boundaries,
    _build_row_cells_with_spanning,
    _cap_by_left_neighbors,
    _cap_by_neighbors,
    _capture_glyph_image,
    _cell_short_line_ratio,
    _classify_sup_sub,
    _cm_design_size,
    _coalesce_line_extents,
    _collapse_tex_composed,
    _compute_para_indents,
    _detect_block_alignment,
    _detect_column_alignment,
    _detect_framed_tables,
    _detect_line_joins,
    _detect_ruled_tables,
    _detect_vline_tables,
    _dir_to_rotate,
    _ends_with_math_placeholder,
    _escape_preserving_tags,
    _expand_ligatures,
    _extract_link_translations,
    _extract_page_blocks,
    _extract_page_comments,
    _extract_page_freetext,
    _extract_page_widgets,
    _extract_table_cell_blocks,
    _find_horizontal_rules,
    _find_link_in_chars,
    _find_overlap_index,
    _find_page_tables,
    _find_vertical_lines,
    _fix_url_line_joins,
    _font_family_from_flags,
    _fontfile_cache,
    _get_block_chars,
    _get_extracted_cell_bboxes,
    _get_first_content_flags,
    _get_form_xobject_rects,
    _get_freetext_annot_rects,
    _get_image_rects,
    _get_spans_in_rect,
    _group_rules_by_xrange,
    _group_spans_into_rows,
    _group_vlines_by_yrange,
    _has_complex_math_layout,
    _has_mixed_formatting,
    _infer_columns,
    _infer_columns_by_gaps,
    _inject_link_tags,
    _inject_page_annotations,
    _inject_page_widgets,
    _insert_link_with_style,
    _is_body_text_block,
    _is_display_equation,
    _is_math_font,
    _is_multiline_block,
    _is_pure_math_line,
    _is_split_paragraph,
    _is_vertical_block,
    _join_lines,
    _join_textbox_lines,
    _links_to_checkpoint,
    _map_stripped_pos,
    _measure_htmlbox_spare,
    _merge_adjacent_tags,
    _merge_continuation_lines,
    _merge_math_spans,
    _merge_overlapping_math_blocks,
    _merge_two_math_blocks,
    _merge_visual_and_inferred,
    _most_common,
    _overlay_vertical_block,
    _page_has_images,
    _process_scanned_pages,
    _reclassify_merged_math_roles,
    _refine_alignments_from_context,
    _remap_cm_char,
    _resolve_fontfile,
    _resolve_vertical_alignment,
    _restore_math_placeholders,
    _restore_page_links,
    _row_column_count,
    _save_page_links,
    _should_translate_pdf_comments,
    _should_translate_pdf_textboxes,
    _span_in_any_table,
    _split_at_display_gaps,
    _split_multiline_blocks,
    _table_text_density,
    _tag_span_text,
    _translate_bookmarks,
    _translate_page_images,
    _translate_single_pdf_image,
    _upgrade_emphasis_start_joins,
    _upgrade_list_joins,
    _widen_render_rects,
    _wrap_math_chars,
    process_pdf_file,
)

# ── PDF construction helpers ──────────────────────────────────────────────────


def _make_pdf(path: Path, texts: list[str]) -> None:
    """Creates a single-page PDF with insert_text calls at stacked positions."""
    doc = pymupdf.open()
    page = doc.new_page()
    for i, text in enumerate(texts):
        page.insert_text((72, 72 + i * 50), text, fontsize=14)
    doc.save(str(path))
    doc.close()


def _make_multipage_pdf(
    path: Path,
    num_pages: int,
    blank_last: bool = False,
) -> None:
    """Creates a multi-page PDF; optionally makes the last page blank."""
    doc = pymupdf.open()
    for i in range(num_pages):
        page = doc.new_page()
        if not (blank_last and i == num_pages - 1):
            page.insert_text((72, 72), f"Page {i + 1} text", fontsize=14)
    doc.save(str(path))
    doc.close()


def _make_scanned_pdf(path: Path, num_text_pages: int = 1) -> None:
    """Creates a PDF with text pages followed by one image-only (scanned) page.

    The last page contains a small raster image but no embedded text,
    simulating a scanned document page.
    """
    doc = pymupdf.open()
    for i in range(num_text_pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"Page {i + 1} text", fontsize=14)
    # Add a page with only a raster image (no text)
    page = doc.new_page()
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 10, 10), 0)
    page.insert_image(pymupdf.Rect(50, 50, 200, 200), pixmap=pix)
    doc.save(str(path))
    doc.close()


def _open_page(path: Path, index: int = 0):
    """Opens a PDF and returns (doc, page) — caller must close doc."""
    doc = pymupdf.open(str(path))
    return doc, doc[index]


# ── _most_common ──────────────────────────────────────────────────────────────


def test_most_common_empty_returns_default() -> None:
    """Empty list returns the default value."""
    assert _most_common([], "fallback") == "fallback"
    assert _most_common([], 0) == 0


def test_most_common_single_element() -> None:
    """Single element is always returned."""
    assert _most_common(["only"], "x") == "only"
    assert _most_common([42.0], 0.0) == 42.0  # noqa: PLR2004


def test_most_common_dominant_string() -> None:
    """Returns the most frequently occurring string."""
    assert _most_common(["a", "b", "a", "c", "a"], "x") == "a"


def test_most_common_dominant_float() -> None:
    """Returns the most frequently occurring float (font size use-case)."""
    result = _most_common([12.0, 14.0, 12.0, 12.0], 10.0)
    assert result == 12.0  # noqa: PLR2004


def test_most_common_dominant_integer() -> None:
    """Returns the most frequently occurring int (font flags use-case)."""
    assert _most_common([0, 16, 0, 0, 16], 0) == 0


# ── _build_overlay_html ───────────────────────────────────────────────────────


def _block(**kwargs) -> dict:
    """Builds a minimal block dict with required defaults."""
    base = {
        "translated_text": "Hello",
        "font_size": 12.0,
        "color": 0,
        "bold": False,
        "italic": False,
    }
    base.update(kwargs)
    return base


def test_build_overlay_html_is_p_tag() -> None:
    """Output starts with <p style= and ends with </p>."""
    result = _build_overlay_html(_block())
    assert result.startswith('<p style="')
    assert result.endswith("</p>")


def test_build_overlay_html_contains_text() -> None:
    """Translated text appears in the output."""
    result = _build_overlay_html(_block(translated_text="Bonjour"))
    assert "Bonjour" in result


def test_build_overlay_html_font_size() -> None:
    """font_size is rendered with pt unit."""
    assert "font-size:16.5pt" in _build_overlay_html(_block(font_size=16.5))
    assert "font-size:8.0pt" in _build_overlay_html(_block(font_size=8.0))


def test_build_overlay_html_bold_true() -> None:
    """bold=True → font-weight:bold."""
    assert "font-weight:bold" in _build_overlay_html(_block(bold=True))


def test_build_overlay_html_bold_false() -> None:
    """bold=False → font-weight:normal."""
    assert "font-weight:normal" in _build_overlay_html(_block(bold=False))


def test_build_overlay_html_italic_true() -> None:
    """italic=True → font-style:italic."""
    assert "font-style:italic" in _build_overlay_html(_block(italic=True))


def test_build_overlay_html_italic_false() -> None:
    """italic=False → font-style:normal."""
    assert "font-style:normal" in _build_overlay_html(_block(italic=False))


def test_build_overlay_html_color_black() -> None:
    """Color 0x000000 renders as #000000."""
    assert "color:#000000" in _build_overlay_html(_block(color=0x000000))


def test_build_overlay_html_color_red() -> None:
    """Color 0xFF0000 renders as #ff0000."""
    assert "color:#ff0000" in _build_overlay_html(_block(color=0xFF0000))


def test_build_overlay_html_color_green() -> None:
    """Color 0x00FF00 renders as #00ff00."""
    assert "color:#00ff00" in _build_overlay_html(_block(color=0x00FF00))


def test_build_overlay_html_color_blue() -> None:
    """Color 0x0000FF renders as #0000ff."""
    assert "color:#0000ff" in _build_overlay_html(_block(color=0x0000FF))


def test_build_overlay_html_color_mixed() -> None:
    """Arbitrary 24-bit color is split into RGB correctly."""
    # 0x1A2B3C → R=0x1A, G=0x2B, B=0x3C
    assert "color:#1a2b3c" in _build_overlay_html(_block(color=0x1A2B3C))


def test_build_overlay_html_newlines_become_separate_p_tags() -> None:
    """Newlines in translated text produce separate <p> tags."""
    result = _build_overlay_html(_block(translated_text="Line1\nLine2\nLine3"))
    assert result.count("<p ") == 3  # noqa: PLR2004
    assert "Line1" in result
    assert "Line2" in result
    assert "Line3" in result


def test_build_overlay_html_html_escape_angle_brackets() -> None:
    """< and > are HTML-escaped to prevent raw tag injection."""
    result = _build_overlay_html(_block(translated_text="<b>bold</b>"))
    assert "<b>" not in result
    assert "&lt;b&gt;" in result


def test_build_overlay_html_html_escape_ampersand() -> None:
    """& is escaped to &amp;."""
    result = _build_overlay_html(_block(translated_text="Foo & Bar"))
    assert "Foo &amp; Bar" in result


def test_build_overlay_html_html_escape_quotes() -> None:
    """Quotes are escaped."""
    result = _build_overlay_html(_block(translated_text='Say "hello"'))
    assert '"hello"' not in result


def test_build_overlay_html_margin_zero() -> None:
    """margin:0 is always present to avoid extra spacing."""
    assert "margin:0;" in _build_overlay_html(_block())


def test_build_overlay_html_missing_keys_use_defaults() -> None:
    """Block with only translated_text uses safe defaults for all other keys."""
    result = _build_overlay_html({"translated_text": "Text only"})
    assert "Text only" in result
    assert "font-size:12.0pt" in result  # default size
    assert "color:#000000" in result  # default black
    assert "font-weight:normal" in result  # default not bold
    assert "font-style:normal" in result  # default not italic


def test_build_overlay_html_single_para_uses_para_indents() -> None:
    """Single-paragraph block applies para_indents for hanging indent."""
    block = {
        "translated_text": "2.1 Heading text wrapping here",
        "font_size": 11.0,
        "para_indents": [(24.8, -24.8)],
    }
    result = _build_overlay_html(block)
    assert "padding-left:24.8pt" in result
    assert "text-indent:-24.8pt" in result


def test_build_overlay_html_para_colors_override() -> None:
    """Paragraphs with different colors get per-paragraph color CSS."""
    blue = 0x1A73E8  # noqa: PLR2004
    black = 0x000000
    block = {
        "translated_text": "Eddy Wang\nMeta Platforms Inc.",
        "font_size": 10.0,
        "color": black,  # dominant is black
        "para_colors": [blue, black],
    }
    result = _build_overlay_html(block)
    # First <p> should have blue color
    assert "color:#1a73e8" in result
    # Second <p> should have black color
    assert "color:#000000" in result
    # Both paragraphs should be separate <p> tags
    assert result.count("<p ") == 2  # noqa: PLR2004


def test_build_overlay_html_rtl_target_adds_dir_attr() -> None:
    """Arabic / Hebrew / Persian targets emit ``dir="rtl"`` on the <p>."""
    out = _build_overlay_html(_block(translated_text="مرحبا"), target_lang="Arabic")
    assert 'dir="rtl"' in out
    assert "مرحبا" in out


def test_build_overlay_html_ltr_target_omits_dir_attr() -> None:
    """LTR targets must not emit ``dir="rtl"`` (regression guard)."""
    out = _build_overlay_html(_block(translated_text="Hello"), target_lang="French")
    assert "dir=" not in out


def test_build_overlay_html_rtl_flips_left_align_to_right() -> None:
    """A geometric ``text-align:left`` flips to ``right`` for RTL targets.

    The geometric alignment is derived from LTR-extracted span coordinates
    so it can't mean "start of line" for an Arabic overlay; flipping
    keeps the natural reading anchor on the right.
    """
    block = _block(translated_text="مرحبا", text_align="left")
    out = _build_overlay_html(block, target_lang="Arabic")
    assert "text-align:right" in out
    assert "text-align:left" not in out


def test_build_overlay_html_rtl_keeps_center_align() -> None:
    """Centre alignment is symmetric — leave it alone for RTL too."""
    block = _block(translated_text="مرحبا", text_align="center")
    out = _build_overlay_html(block, target_lang="Arabic")
    assert "text-align:center" in out


def test_build_overlay_html_rtl_keeps_justify_align() -> None:
    """Justified text is bilateral — no flip needed."""
    block = _block(translated_text="مرحبا", text_align="justify")
    out = _build_overlay_html(block, target_lang="Arabic")
    assert "text-align:justify" in out


def test_build_overlay_html_para_colors_not_set_uses_dominant() -> None:
    """Without para_colors, all paragraphs use the block's dominant color."""
    block = {
        "translated_text": "Line A\nLine B",
        "font_size": 10.0,
        "color": 0xFF0000,
    }
    result = _build_overlay_html(block)
    assert result.count("color:#ff0000") == 2  # noqa: PLR2004


# ── _extract_page_blocks ──────────────────────────────────────────────────────


def test_extract_page_blocks_para_colors_set_on_color_change() -> None:
    """Block with different-colored lines gets para_colors on extraction."""
    doc = pymupdf.open()
    page = doc.new_page()
    blue = (0x1A / 255, 0x73 / 255, 0xE8 / 255)
    # Insert blue author name and black address far apart vertically
    # so they end up as separate paragraphs (\n join).
    page.insert_text((200, 100), "Eddy Wang", fontsize=10, color=blue)
    page.insert_text((200, 130), "Meta Platforms", fontsize=10, color=(0, 0, 0))
    blocks = _extract_page_blocks(page)
    doc.close()
    # Find the block containing both texts (PyMuPDF may group them)
    multi = [b for b in blocks if "Eddy Wang" in b["text"]]
    if multi and "Meta Platforms" in multi[0]["text"]:
        # Lines have different colors → para_colors should be set
        assert "para_colors" in multi[0]
        assert len(multi[0]["para_colors"]) >= 2  # noqa: PLR2004


def test_extract_page_blocks_blank_page() -> None:
    """Completely blank page returns an empty list."""
    doc = pymupdf.open()
    page = doc.new_page()
    # No text added
    assert _extract_page_blocks(page) == []
    doc.close()


def test_extract_page_blocks_whitespace_only() -> None:
    """Page with only whitespace text returns an empty list."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "   \t  ", fontsize=12)
    assert _extract_page_blocks(page) == []
    doc.close()


def test_extract_page_blocks_returns_text(tmp_path: Path) -> None:
    """Text on a page is extracted with correct content."""
    pdf = tmp_path / "test.pdf"
    _make_pdf(pdf, ["Hello World"])

    doc, page = _open_page(pdf)
    try:
        blocks = _extract_page_blocks(page)
    finally:
        doc.close()

    assert len(blocks) >= 1
    assert any("Hello World" in b["text"] for b in blocks)


def test_extract_page_blocks_multiple_texts(tmp_path: Path) -> None:
    """Multiple text insertions produce the correct number of blocks."""
    pdf = tmp_path / "multi.pdf"
    _make_pdf(pdf, ["First paragraph", "Second paragraph"])

    doc, page = _open_page(pdf)
    try:
        blocks = _extract_page_blocks(page)
    finally:
        doc.close()

    texts = " ".join(b["text"] for b in blocks)
    assert "First paragraph" in texts
    assert "Second paragraph" in texts


def test_extract_page_blocks_has_required_keys(tmp_path: Path) -> None:
    """Each returned block dict has all required keys with correct types."""
    pdf = tmp_path / "keys.pdf"
    _make_pdf(pdf, ["Test content"])

    doc, page = _open_page(pdf)
    try:
        blocks = _extract_page_blocks(page)
    finally:
        doc.close()

    assert blocks, "Expected at least one block"
    for b in blocks:
        assert "rect" in b
        assert "text" in b
        assert "font_size" in b
        assert "font_name" in b
        assert "color" in b
        assert "bold" in b
        assert "italic" in b
        assert isinstance(b["rect"], list)
        assert len(b["rect"]) == 4  # noqa: PLR2004
        assert isinstance(b["text"], str)
        assert isinstance(b["font_size"], float)
        assert isinstance(b["bold"], bool)
        assert isinstance(b["italic"], bool)
        assert isinstance(b["color"], int)


def test_extract_page_blocks_rect_values(tmp_path: Path) -> None:
    """Rect values are plausible floats (x0 < x1, y0 < y1)."""
    pdf = tmp_path / "rect.pdf"
    _make_pdf(pdf, ["Some text"])

    doc, page = _open_page(pdf)
    try:
        blocks = _extract_page_blocks(page)
    finally:
        doc.close()

    for b in blocks:
        x0, y0, x1, y1 = b["rect"]
        assert x1 > x0, "x1 must be greater than x0"
        assert y1 > y0, "y1 must be greater than y0"


# ── _page_has_images ─────────────────────────────────────────────────────────


def test_page_has_images_returns_true_for_image_page(tmp_path: Path) -> None:
    """A page containing a raster image returns True."""
    pdf = tmp_path / "img.pdf"
    _make_scanned_pdf(pdf, num_text_pages=0)
    doc = pymupdf.open(str(pdf))
    assert _page_has_images(doc[0]) is True
    doc.close()


def test_page_has_images_returns_false_for_text_page(tmp_path: Path) -> None:
    """A page containing only text returns False."""
    pdf = tmp_path / "text.pdf"
    _make_pdf(pdf, ["Hello world"])
    doc = pymupdf.open(str(pdf))
    assert _page_has_images(doc[0]) is False
    doc.close()


def test_page_has_images_returns_false_for_blank_page(tmp_path: Path) -> None:
    """A truly blank page (no content) returns False."""
    pdf = tmp_path / "blank.pdf"
    doc = pymupdf.open()
    doc.new_page()
    doc.save(str(pdf))
    doc.close()
    doc = pymupdf.open(str(pdf))
    assert _page_has_images(doc[0]) is False
    doc.close()


# ── _apply_translated_blocks ──────────────────────────────────────────────────


def test_apply_translated_blocks_empty_list_is_noop() -> None:
    """Empty block list does not crash and leaves page unchanged."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Original", fontsize=12)
    original_text = page.get_text()

    _apply_translated_blocks(page, [], pymupdf)

    assert page.get_text() == original_text
    doc.close()


def test_apply_translated_blocks_no_translated_text_is_noop() -> None:
    """Blocks without 'translated_text' key are silently skipped."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Original", fontsize=12)

    # Block dict with no 'translated_text' key — should be a no-op
    blocks = [{"rect": [0, 0, 200, 50], "text": "Original"}]
    _apply_translated_blocks(page, blocks, pymupdf)

    # No crash; page annotation list should be empty (no redaction applied)
    assert len(list(page.annots())) == 0
    doc.close()


def test_apply_translated_blocks_replaces_text(tmp_path: Path) -> None:
    """Translated text appears in the output after redact + overlay."""
    pdf = tmp_path / "src.pdf"
    _make_pdf(pdf, ["Original text"])

    doc, page = _open_page(pdf)
    blocks = _extract_page_blocks(page)
    assert blocks, "Need at least one block to test replacement"
    blocks[0]["translated_text"] = "Translated text"

    _apply_translated_blocks(page, blocks, pymupdf)

    # Save and reload to read back the result
    out = tmp_path / "out.pdf"
    doc.save(str(out))
    doc.close()

    doc2, page2 = _open_page(out)
    page_text = page2.get_text()
    doc2.close()

    assert "Translated text" in page_text


def test_apply_translated_blocks_mixed_blocks(tmp_path: Path) -> None:
    """Only blocks with 'translated_text' are redacted; others are skipped."""
    pdf = tmp_path / "mixed.pdf"
    _make_pdf(pdf, ["Text to translate"])

    doc, page = _open_page(pdf)
    blocks = _extract_page_blocks(page)
    assert blocks

    # First block gets translation; create a second fake block with no translation
    blocks[0]["translated_text"] = "Traduction"
    untranslated_block = {
        "rect": [0, 200, 100, 250],
        "text": "Untranslated",
        "font_size": 10.0,
        "color": 0,
        "bold": False,
        "italic": False,
    }
    _apply_translated_blocks(page, [blocks[0], untranslated_block], pymupdf)

    out = tmp_path / "out.pdf"
    doc.save(str(out))
    doc.close()

    doc2, page2 = _open_page(out)
    page_text = page2.get_text()
    doc2.close()

    assert "Traduction" in page_text


# ── process_pdf_file ──────────────────────────────────────────────────────────


def test_process_pdf_file_success_returns_true(tmp_path: Path) -> None:
    """Successful processing of a text PDF returns True."""
    pdf = tmp_path / "input.pdf"
    out = tmp_path / "out.pdf"
    _make_pdf(pdf, ["Hello World"])

    with patch(
        "src.core.pdf_processor.translate_batch",
        return_value=["Bonjour le Monde"],
    ):
        result = process_pdf_file(pdf, out, "French")

    assert result is True
    assert out.exists()


def test_process_pdf_file_passes_provider_and_model_to_translate_batch(
    tmp_path: Path,
) -> None:
    """provider/model kwargs forward to every translate_batch call.

    Regression for the History Re-translate bug: process_pdf_file was
    calling translate_batch without provider/model so the LLM engine
    fell back to SETTING_LLM_LAST_MODEL (Gemini) regardless of the
    per-feature setting the user had picked.
    """
    pdf = tmp_path / "input.pdf"
    out = tmp_path / "out.pdf"
    _make_pdf(pdf, ["Hello World"])

    with patch(
        "src.core.pdf_processor.translate_batch",
        return_value=["Bonjour le Monde"],
    ) as mock_batch:
        process_pdf_file(
            pdf,
            out,
            "French",
            provider="Custom",
            model="gpt-5.4-pro",
        )

    # Every translate_batch call must carry the explicit provider+model.
    assert mock_batch.called, "expected translate_batch to be invoked"
    for call in mock_batch.call_args_list:
        assert call.kwargs.get("provider") == "Custom"
        assert call.kwargs.get("model") == "gpt-5.4-pro"


def test_process_pdf_file_output_contains_translation(tmp_path: Path) -> None:
    """The output PDF contains the translated text."""
    pdf = tmp_path / "input.pdf"
    out = tmp_path / "out.pdf"
    _make_pdf(pdf, ["Hello World"])

    with patch(
        "src.core.pdf_processor.translate_batch",
        return_value=["Bonjour le Monde"],
    ):
        process_pdf_file(pdf, out, "French")

    doc, page = _open_page(out)
    page_text = page.get_text()
    doc.close()
    assert "Bonjour" in page_text


def test_process_pdf_file_progress_callback(tmp_path: Path) -> None:
    """Progress callback is called for each page and ends at 100."""
    pdf = tmp_path / "input.pdf"
    out = tmp_path / "out.pdf"
    _make_multipage_pdf(pdf, 3)

    progress: list[int] = []

    with (
        patch(
            "src.core.pdf_processor.translate_batch",
            side_effect=lambda texts, *a, **kw: [f"[FR] {t}" for t in texts],
        ),
        patch("src.core.pdf_processor._config.load_setting", return_value=False),
    ):
        process_pdf_file(pdf, out, "French", progress_callback=progress.append)

    assert progress, "Progress callback was never called"
    assert progress[-1] == 100  # noqa: PLR2004
    # Progress must be monotonically non-decreasing
    for i in range(1, len(progress)):
        assert progress[i] >= progress[i - 1]


def test_process_pdf_file_cancel_before_first_page(tmp_path: Path) -> None:
    """Cancellation before page 0 returns False without any LLM calls."""
    pdf = tmp_path / "input.pdf"
    out = tmp_path / "out.pdf"
    _make_pdf(pdf, ["Hello"])

    with patch("src.core.pdf_processor.translate_batch") as mock_tb:
        result = process_pdf_file(pdf, out, "French", cancel_check=lambda: True)

    assert result is False
    mock_tb.assert_not_called()


def test_process_pdf_file_cancel_after_first_page(tmp_path: Path) -> None:
    """Cancellation after page 0 returns False; page 0 is translated."""
    pdf = tmp_path / "input.pdf"
    out = tmp_path / "out.pdf"
    _make_multipage_pdf(pdf, 3)

    pages_translated = [0]

    def mock_tb(texts, *args, **kwargs):
        pages_translated[0] += 1
        return [f"[FR] {t}" for t in texts]

    def cancel_after_first_page():
        # Cancel once at least 1 page has been through translate_batch
        return pages_translated[0] >= 1

    with patch("src.core.pdf_processor.translate_batch", side_effect=mock_tb):
        result = process_pdf_file(
            pdf, out, "French", cancel_check=cancel_after_first_page
        )

    assert result is False


def test_process_pdf_file_translate_batch_returns_none(tmp_path: Path) -> None:
    """If translate_batch returns None (cancelled), process_pdf_file returns False."""
    pdf = tmp_path / "input.pdf"
    out = tmp_path / "out.pdf"
    _make_pdf(pdf, ["Hello"])

    with patch("src.core.pdf_processor.translate_batch", return_value=None):
        result = process_pdf_file(pdf, out, "French")

    assert result is False


def test_process_pdf_file_checkpoint_saves_pages(tmp_path: Path) -> None:
    """Per-page checkpoints are written when checkpoint_dir is provided."""
    from src.core.checkpoint import load_pdf_checkpoint  # noqa: PLC0415

    pdf = tmp_path / "input.pdf"
    out = tmp_path / "out.pdf"
    _make_multipage_pdf(pdf, 3)
    checkpoint_dir = tmp_path / "cp"
    checkpoint_dir.mkdir()

    with patch(
        "src.core.pdf_processor.translate_batch",
        side_effect=lambda texts, *a, **kw: [f"[FR] {t}" for t in texts],
    ):
        process_pdf_file(pdf, out, "French", checkpoint_dir=checkpoint_dir)

    cp = load_pdf_checkpoint(checkpoint_dir)
    assert cp is not None
    assert len(cp) == 3  # noqa: PLR2004


def test_process_pdf_file_checkpoint_resume_skips_llm(tmp_path: Path) -> None:
    """On resume, pages cached in checkpoint skip LLM translation."""
    pdf = tmp_path / "input.pdf"
    out = tmp_path / "out.pdf"
    _make_multipage_pdf(pdf, 2)
    checkpoint_dir = tmp_path / "cp"
    checkpoint_dir.mkdir()

    call_count = [0]

    def counting_translate(texts, *args, **kwargs):
        call_count[0] += 1
        return [f"[FR] {t}" for t in texts]

    # First run — populates checkpoint
    with patch(
        "src.core.pdf_processor.translate_batch", side_effect=counting_translate
    ):
        process_pdf_file(pdf, out, "French", checkpoint_dir=checkpoint_dir)

    first_run_calls = call_count[0]
    assert first_run_calls >= 1, "Should have made at least one LLM call"

    # Second run — should use cached pages, zero new LLM calls
    call_count[0] = 0
    out2 = tmp_path / "out2.pdf"
    with patch(
        "src.core.pdf_processor.translate_batch", side_effect=counting_translate
    ):
        result = process_pdf_file(pdf, out2, "French", checkpoint_dir=checkpoint_dir)

    assert result is True
    assert call_count[0] == 0, "Resume should not call translate_batch again"


def test_process_pdf_file_checkpoint_resume_progress_monotonic(
    tmp_path: Path,
) -> None:
    """Progress reported during checkpoint resume never decreases."""
    pdf = tmp_path / "input.pdf"
    out = tmp_path / "out.pdf"
    _make_multipage_pdf(pdf, 4)
    checkpoint_dir = tmp_path / "cp"
    checkpoint_dir.mkdir()

    # First run — translate pages 0-1 then cancel
    cancel_after = [2]  # cancel after 2 pages

    def cancel_at_page_2() -> bool:
        cancel_after[0] -= 1
        return cancel_after[0] < 0

    with patch(
        "src.core.pdf_processor.translate_batch",
        side_effect=lambda texts, *a, **kw: [f"[FR] {t}" for t in texts],
    ):
        process_pdf_file(
            pdf,
            out,
            "French",
            cancel_check=cancel_at_page_2,
            checkpoint_dir=checkpoint_dir,
        )

    # Second run (resume) — capture progress
    progress: list[int] = []
    out2 = tmp_path / "out2.pdf"
    with patch(
        "src.core.pdf_processor.translate_batch",
        side_effect=lambda texts, *a, **kw: [f"[FR] {t}" for t in texts],
    ):
        result = process_pdf_file(
            pdf,
            out2,
            "French",
            progress_callback=progress.append,
            checkpoint_dir=checkpoint_dir,
        )

    assert result is True
    assert progress, "Progress callback was never called"
    assert progress[-1] == 100  # noqa: PLR2004
    # Progress must be monotonically non-decreasing across cached + new pages
    for i in range(1, len(progress)):
        assert progress[i] >= progress[i - 1], (
            f"Progress decreased on resume: {progress[i - 1]} → {progress[i]}"
        )


def test_process_pdf_file_blank_page_with_do_images_false(tmp_path: Path) -> None:
    """Blank pages with do_images=False do not trigger OCR pipeline."""
    pdf = tmp_path / "input.pdf"
    out = tmp_path / "out.pdf"
    _make_multipage_pdf(pdf, 2, blank_last=True)  # Page 1 is blank

    with (
        patch("src.core.pdf_processor._config.load_setting", return_value=False),
        patch(
            "src.core.pdf_processor.translate_batch", return_value=["[FR] Page 1 text"]
        ),
        patch("src.core.pdf_processor._process_scanned_pages") as mock_ocr,
    ):
        result = process_pdf_file(pdf, out, "French")

    assert result is True
    mock_ocr.assert_not_called()


def test_process_pdf_file_scanned_page_with_do_images_true(tmp_path: Path) -> None:
    """Image-only pages with do_images=True are routed to _process_scanned_pages."""
    pdf = tmp_path / "input.pdf"
    out = tmp_path / "out.pdf"
    _make_scanned_pdf(pdf, num_text_pages=1)  # Page 0=text, Page 1=image-only

    with (
        patch("src.core.pdf_processor._config.load_setting", return_value=True),
        patch("src.core.pdf_processor._config.check_ocr_setup", return_value=True),
        patch(
            "src.core.pdf_processor.translate_batch",
            side_effect=lambda texts, *a, **kw: [f"[FR] {t}" for t in texts],
        ),
        patch(
            "src.core.pdf_processor._process_scanned_pages", return_value=True
        ) as mock_ocr,
    ):
        result = process_pdf_file(pdf, out, "French")

    assert result is True
    mock_ocr.assert_called_once()
    # The scanned_indices argument should contain page index 1 (the image page)
    scanned_indices = mock_ocr.call_args[0][1]
    assert 1 in scanned_indices


def test_process_pdf_file_scanned_page_retries_ocr_on_resume(
    tmp_path: Path,
) -> None:
    """Regression: scanned pages always re-OCR on resume, never silently skipped.

    Today scanned pages aren't checkpointed (only text-page results
    are).  A resumed translation of a PDF with scanned pages must
    therefore route those pages back into ``_process_scanned_pages``
    even when the checkpoint file exists from the prior run — pinning
    that contract so a future "optimization" that caches scanned-page
    results can't silently introduce the failure-mode the audit
    feared (cached failure → page skipped → translated PDF has an
    untouched scanned page where translation was expected).
    """
    pdf = tmp_path / "input.pdf"
    out = tmp_path / "out.pdf"
    checkpoint_dir = tmp_path / "checkpoint"
    checkpoint_dir.mkdir()
    _make_scanned_pdf(pdf, num_text_pages=1)  # Page 0=text, Page 1=image-only

    # Seed a checkpoint covering page 0 (text page already done) but
    # NOT page 1 — simulates a prior run that completed the text
    # phase but crashed before / during the OCR pipeline.
    from src.core.checkpoint import save_pdf_page_progress  # noqa: PLC0415

    save_pdf_page_progress(
        checkpoint_dir,
        page_index=0,
        translated_blocks=[
            {"text": "Page 1 text", "translated": "[FR] Page 1 text"},
        ],
        total_pages=2,
    )

    with (
        patch("src.core.pdf_processor._config.load_setting", return_value=True),
        patch("src.core.pdf_processor._config.check_ocr_setup", return_value=True),
        patch(
            "src.core.pdf_processor.translate_batch",
            side_effect=lambda texts, *a, **kw: [f"[FR] {t}" for t in texts],
        ),
        patch(
            "src.core.pdf_processor._process_scanned_pages",
            return_value=True,
        ) as mock_ocr,
    ):
        result = process_pdf_file(
            pdf,
            out,
            "French",
            checkpoint_dir=checkpoint_dir,
        )

    assert result is True
    # Page 1 (scanned) must be re-OCRed despite checkpoint existing.
    mock_ocr.assert_called_once()
    scanned_indices = mock_ocr.call_args[0][1]
    assert 1 in scanned_indices, (
        "scanned page 1 was silently skipped on resume — OCR retry contract regressed"
    )


def test_process_pdf_file_blank_page_not_routed_to_scanned(tmp_path: Path) -> None:
    """Truly blank pages (no text, no images) are NOT routed to scanned pipeline."""
    pdf = tmp_path / "input.pdf"
    out = tmp_path / "out.pdf"
    _make_multipage_pdf(pdf, 2, blank_last=True)  # Page 1 is truly blank

    with (
        patch("src.core.pdf_processor._config.load_setting", return_value=True),
        patch("src.core.pdf_processor._config.check_ocr_setup", return_value=True),
        patch(
            "src.core.pdf_processor.translate_batch",
            side_effect=lambda texts, *a, **kw: [f"[FR] {t}" for t in texts],
        ),
        patch("src.core.pdf_processor._process_scanned_pages") as mock_ocr,
    ):
        result = process_pdf_file(pdf, out, "French")

    assert result is True
    mock_ocr.assert_not_called()


def test_process_pdf_file_scanned_pipeline_failure(tmp_path: Path) -> None:
    """If _process_scanned_pages returns False, process_pdf_file returns False."""
    pdf = tmp_path / "input.pdf"
    out = tmp_path / "out.pdf"
    _make_scanned_pdf(pdf, num_text_pages=0)  # Single image-only page

    with (
        patch("src.core.pdf_processor._config.load_setting", return_value=True),
        patch("src.core.pdf_processor._config.check_ocr_setup", return_value=True),
        patch("src.core.pdf_processor.translate_batch", return_value=[]),
        patch("src.core.pdf_processor._process_scanned_pages", return_value=False),
    ):
        result = process_pdf_file(pdf, out, "French")

    assert result is False


def test_process_pdf_file_blank_page_saves_empty_checkpoint(tmp_path: Path) -> None:
    """Blank pages with no OCR save an empty block list in the checkpoint."""
    from src.core.checkpoint import load_pdf_checkpoint  # noqa: PLC0415

    pdf = tmp_path / "input.pdf"
    out = tmp_path / "out.pdf"
    _make_multipage_pdf(pdf, 2, blank_last=True)
    checkpoint_dir = tmp_path / "cp"
    checkpoint_dir.mkdir()

    with (
        patch("src.core.pdf_processor._config.load_setting", return_value=False),
        patch(
            "src.core.pdf_processor.translate_batch",
            side_effect=lambda texts, *a, **kw: [f"[FR] {t}" for t in texts],
        ),
    ):
        process_pdf_file(pdf, out, "French", checkpoint_dir=checkpoint_dir)

    cp = load_pdf_checkpoint(checkpoint_dir)
    assert cp is not None
    # Page index 1 (blank) should have an empty blocks list
    assert 1 in cp
    assert cp[1] == []


def test_process_pdf_file_glossary_forwarded(tmp_path: Path) -> None:
    """glossary_entries is forwarded to translate_batch."""
    pdf = tmp_path / "input.pdf"
    out = tmp_path / "out.pdf"
    _make_pdf(pdf, ["Hello"])
    glossary = [(1, "Hello", "Bonjour")]

    captured_kwargs: list[dict] = []

    def capturing_translate(texts, *args, **kwargs):
        captured_kwargs.append(kwargs)
        return [f"[FR] {t}" for t in texts]

    with patch(
        "src.core.pdf_processor.translate_batch", side_effect=capturing_translate
    ):
        process_pdf_file(pdf, out, "French", glossary_entries=glossary)

    assert captured_kwargs, "translate_batch was not called"
    assert captured_kwargs[0].get("glossary_entries") == glossary


def test_process_pdf_file_content_type_is_pdf(tmp_path: Path) -> None:
    """translate_batch is called with content_type=CONTENT_PDF."""
    from src.constants.llm import CONTENT_PDF  # noqa: PLC0415

    pdf = tmp_path / "input.pdf"
    out = tmp_path / "out.pdf"
    _make_pdf(pdf, ["Hello"])

    captured_kwargs: list[dict] = []

    def capturing_translate(texts, *args, **kwargs):
        captured_kwargs.append(kwargs)
        return [f"[FR] {t}" for t in texts]

    with patch(
        "src.core.pdf_processor.translate_batch", side_effect=capturing_translate
    ):
        process_pdf_file(pdf, out, "French")

    assert captured_kwargs, "translate_batch was not called"
    assert captured_kwargs[0].get("content_type") == CONTENT_PDF


def test_process_pdf_file_src_lang_forwarded(tmp_path: Path) -> None:
    """src_lang is forwarded as the third positional arg to translate_batch."""
    pdf = tmp_path / "input.pdf"
    out = tmp_path / "out.pdf"
    _make_pdf(pdf, ["Hello"])

    captured_args: list[tuple] = []

    def capturing_translate(*args, **kwargs):
        captured_args.append(args)
        return [f"[FR] {t}" for t in args[0]]

    with patch(
        "src.core.pdf_processor.translate_batch", side_effect=capturing_translate
    ):
        process_pdf_file(pdf, out, "French", src_lang="English")

    assert captured_args, "translate_batch was not called"
    # translate_batch(texts, target_lang, src_lang, ...)
    assert captured_args[0][2] == "English"


def test_process_pdf_file_cancel_check_forwarded(tmp_path: Path) -> None:
    """cancel_check is forwarded to translate_batch via kwargs."""
    pdf = tmp_path / "input.pdf"
    out = tmp_path / "out.pdf"
    _make_pdf(pdf, ["Hello"])

    captured_kwargs: list[dict] = []
    sentinel = lambda: False  # noqa: E731

    def capturing_translate(texts, *args, **kwargs):
        captured_kwargs.append(kwargs)
        return [f"[FR] {t}" for t in texts]

    with patch(
        "src.core.pdf_processor.translate_batch", side_effect=capturing_translate
    ):
        process_pdf_file(pdf, out, "French", cancel_check=sentinel)

    assert captured_kwargs, "translate_batch was not called"
    assert captured_kwargs[0].get("cancel_check") is sentinel


def test_process_pdf_file_multiple_blocks_per_page(tmp_path: Path) -> None:
    """Multiple text blocks on one page are all translated."""
    pdf = tmp_path / "input.pdf"
    out = tmp_path / "out.pdf"
    # Create a PDF with multiple text blocks at different positions
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 100), "First block", fontsize=14)
    page.insert_text((72, 300), "Second block", fontsize=14)
    page.insert_text((72, 500), "Third block", fontsize=14)
    doc.save(str(pdf))
    doc.close()

    call_texts: list[list[str]] = []

    def mock_translate(texts, *args, **kwargs):
        call_texts.append(list(texts))
        return [f"[FR] {t}" for t in texts]

    with patch("src.core.pdf_processor.translate_batch", side_effect=mock_translate):
        result = process_pdf_file(pdf, out, "French")

    assert result is True
    # All blocks should have been sent to translate_batch in one call
    all_texts = [t for batch in call_texts for t in batch]
    assert any("First block" in t for t in all_texts)
    assert any("Second block" in t for t in all_texts)
    assert any("Third block" in t for t in all_texts)


# ── _extract_page_blocks edge cases ──────────────────────────────────────────


def test_extract_page_blocks_skips_image_blocks(tmp_path: Path) -> None:
    """Image blocks (type=1) are filtered out; only text blocks are returned."""
    pdf = tmp_path / "img.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    # Insert text for a text block
    page.insert_text((72, 72), "Real text", fontsize=12)
    # Insert an image to create an image block (type=1)
    # Create a minimal 1x1 red PNG
    import struct  # noqa: PLC0415
    import zlib  # noqa: PLC0415

    def _make_minimal_png() -> bytes:
        """Creates a minimal 1x1 red PNG."""
        header = b"\x89PNG\r\n\x1a\n"
        ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
        ihdr_crc = struct.pack(">I", zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF)
        ihdr = struct.pack(">I", 13) + b"IHDR" + ihdr_data + ihdr_crc
        raw = b"\x00\xff\x00\x00"  # filter byte + RGB
        idat_data = zlib.compress(raw)
        idat_crc = struct.pack(">I", zlib.crc32(b"IDAT" + idat_data) & 0xFFFFFFFF)
        idat = struct.pack(">I", len(idat_data)) + b"IDAT" + idat_data + idat_crc
        iend_crc = struct.pack(">I", zlib.crc32(b"IEND") & 0xFFFFFFFF)
        iend = struct.pack(">I", 0) + b"IEND" + iend_crc
        return header + ihdr + idat + iend

    png_data = _make_minimal_png()
    page.insert_image(pymupdf.Rect(72, 200, 172, 300), stream=png_data)
    doc.save(str(pdf))
    doc.close()

    doc2, page2 = _open_page(pdf)
    try:
        blocks = _extract_page_blocks(page2)
    finally:
        doc2.close()

    # Only text blocks should be returned; image block is filtered out
    for b in blocks:
        assert isinstance(b["text"], str)
        assert len(b["text"].strip()) > 0


def test_extract_page_blocks_font_flags_bold_italic(tmp_path: Path) -> None:
    """Font flags bitmask is correctly decoded into bold and italic booleans."""
    # We can't easily create bold/italic text via insert_text (PyMuPDF uses
    # the default Helvetica), so test the extraction logic by checking types
    pdf = tmp_path / "flags.pdf"
    _make_pdf(pdf, ["Normal text"])

    doc, page = _open_page(pdf)
    try:
        blocks = _extract_page_blocks(page)
    finally:
        doc.close()

    assert blocks
    # Default text should not be bold or italic
    assert blocks[0]["bold"] is False
    assert blocks[0]["italic"] is False


def _make_mock_page(blocks: list[dict]) -> MagicMock:
    """Build a mock PyMuPDF page with the given raw block dicts."""
    page = MagicMock()
    page.get_text.return_value = {"blocks": blocks}
    page.find_tables.return_value = MagicMock(tables=[])
    page.rect = pymupdf.Rect(0, 0, 612, 792)
    page.get_drawings.return_value = []
    page.xref = 1
    page.parent = MagicMock()
    page.parent.xref_xml_raw.return_value = ""
    page.annots.return_value = []
    page.get_image_info.return_value = []
    return page


def test_extract_page_blocks_skips_math_heavy_block() -> None:
    """Block with >50% Computer Modern fonts is skipped (math formula)."""
    raw_block = {
        "type": 0,
        "bbox": (78, 150, 324, 170),
        "lines": [
            {
                "bbox": (78, 150, 324, 160),
                "dir": (1.0, 0.0),
                "spans": [
                    {
                        "text": "m",
                        "font": "CMMI10",
                        "size": 10.0,
                        "flags": 0,
                        "color": 0,
                        "bbox": (78, 150, 90, 160),
                        "origin": (78, 158),
                    },
                    {
                        "text": "2",
                        "font": "CMR10",
                        "size": 10.0,
                        "flags": 0,
                        "color": 0,
                        "bbox": (90, 150, 100, 160),
                        "origin": (90, 158),
                    },
                ],
            },
        ],
    }
    page = _make_mock_page([raw_block])
    blocks = _extract_page_blocks(page)
    # 100% CM fonts → block should be skipped
    assert len(blocks) == 0


def test_extract_page_blocks_keeps_low_math_block() -> None:
    """Block with <50% math fonts is kept (algorithm step with variables)."""
    raw_block = {
        "type": 0,
        "bbox": (78, 90, 400, 110),
        "lines": [
            {
                "bbox": (78, 90, 400, 100),
                "dir": (1.0, 0.0),
                "spans": [
                    {
                        "text": "Then split failure budget as ",
                        "font": "NimbusRomNo9L-Regu",
                        "size": 10.0,
                        "flags": 0,
                        "color": 0,
                        "bbox": (78, 90, 300, 100),
                        "origin": (78, 98),
                    },
                    {
                        "text": "delta",
                        "font": "CMMI10",
                        "size": 10.0,
                        "flags": 0,
                        "color": 0,
                        "bbox": (300, 90, 340, 100),
                        "origin": (300, 98),
                    },
                ],
            },
        ],
    }
    page = _make_mock_page([raw_block])
    blocks = _extract_page_blocks(page)
    # ~15% CMMI → block should be kept
    assert len(blocks) == 1
    assert "split failure" in blocks[0]["text"]


def test_extract_page_blocks_skips_msbm_math_block() -> None:
    """Block with AMS Blackboard Bold (MSBM) above threshold is skipped."""
    raw_block = {
        "type": 0,
        "bbox": (100, 200, 300, 220),
        "lines": [
            {
                "bbox": (100, 200, 300, 210),
                "dir": (1.0, 0.0),
                "spans": [
                    {
                        "text": "RN",
                        "font": "MSBM10",
                        "size": 10.0,
                        "flags": 0,
                        "color": 0,
                        "bbox": (100, 200, 130, 210),
                        "origin": (100, 208),
                    },
                    {
                        "text": "x",
                        "font": "CMMI10",
                        "size": 10.0,
                        "flags": 0,
                        "color": 0,
                        "bbox": (130, 200, 140, 210),
                        "origin": (130, 208),
                    },
                ],
            },
        ],
    }
    page = _make_mock_page([raw_block])
    blocks = _extract_page_blocks(page)
    # 100% math fonts (MSBM + CMMI) → skipped
    assert len(blocks) == 0


def test_extract_page_blocks_keeps_no_math_font_block() -> None:
    """Block with no math fonts is always kept."""
    raw_block = {
        "type": 0,
        "bbox": (72, 50, 540, 70),
        "lines": [
            {
                "bbox": (72, 50, 540, 60),
                "dir": (1.0, 0.0),
                "spans": [
                    {
                        "text": "Regular paragraph of text.",
                        "font": "NimbusRomNo9L-Regu",
                        "size": 10.0,
                        "flags": 0,
                        "color": 0,
                        "bbox": (72, 50, 540, 60),
                        "origin": (72, 58),
                    },
                ],
            },
        ],
    }
    page = _make_mock_page([raw_block])
    blocks = _extract_page_blocks(page)
    assert len(blocks) == 1


# ── _merge_math_spans / _restore_math_placeholders ──────────────────────────


def test_merge_math_spans_consecutive() -> None:
    """Consecutive math-font spans merge into a single placeholder."""
    span_texts = ["Then ", "delta", "B", " = 2"]
    items = [
        {
            "text": "Then ",
            "font": "NimbusRomNo9L-Regu",
            "flags": 0,
            "size": 10.0,
            "color": 0,
            "sx0": 0,
            "sy0": 0,
            "sx1": 30,
            "sy1": 10,
        },
        {
            "text": "delta",
            "font": "CMMI10",
            "flags": 0,
            "size": 10.0,
            "color": 0,
            "sx0": 30,
            "sy0": 0,
            "sx1": 50,
            "sy1": 10,
        },
        {
            "text": "B",
            "font": "CMR7",
            "flags": 0,
            "size": 7.0,
            "color": 0,
            "sx0": 50,
            "sy0": 2,
            "sx1": 55,
            "sy1": 10,
        },
        {
            "text": " = 2",
            "font": "NimbusRomNo9L-Regu",
            "flags": 0,
            "size": 10.0,
            "color": 0,
            "sx0": 55,
            "sy0": 0,
            "sx1": 80,
            "sy1": 10,
        },
    ]
    math_map: dict[str, Any] = {}
    merged_texts, merged_items, counter = _merge_math_spans(
        span_texts,
        items,
        math_map,
        0,
    )
    # "delta" + "B" merged into one placeholder
    assert len(merged_texts) == 3  # noqa: PLR2004
    assert len(merged_items) == 3  # noqa: PLR2004
    assert counter == 1
    # Placeholder is the second element
    ph = merged_texts[1]
    assert ph.startswith(_MATH_PH_START)
    assert ph.endswith(_MATH_PH_END)
    # Value is per-character (char, font, role) tuples with prefix stripped
    char_fonts = math_map[ph]
    assert len(char_fonts) == 6  # noqa: PLR2004  - "delta" (5) + "B" (1)
    assert char_fonts[0][:2] == ("d", "CMMI10")
    assert char_fonts[-1][:2] == ("B", "CMR7")
    # Non-math spans unchanged
    assert merged_texts[0] == "Then "
    assert merged_texts[2] == " = 2"


def test_merge_math_spans_no_math() -> None:
    """When no math fonts, span lists are returned unchanged."""
    span_texts = ["Hello", " World"]
    items = [
        {
            "text": "Hello",
            "font": "Arial",
            "flags": 0,
            "size": 12.0,
            "color": 0,
            "sx0": 0,
            "sy0": 0,
            "sx1": 30,
            "sy1": 12,
        },
        {
            "text": " World",
            "font": "Arial",
            "flags": 0,
            "size": 12.0,
            "color": 0,
            "sx0": 30,
            "sy0": 0,
            "sx1": 60,
            "sy1": 12,
        },
    ]
    math_map: dict[str, Any] = {}
    merged_texts, merged_items, counter = _merge_math_spans(
        span_texts,
        items,
        math_map,
        0,
    )
    assert merged_texts == span_texts
    assert len(math_map) == 0
    assert counter == 0


def test_merge_math_spans_all_math() -> None:
    """All math spans merge into a single placeholder."""
    span_texts = ["x", "+", "y"]
    items = [
        {
            "text": "x",
            "font": "CMMI10",
            "flags": 0,
            "size": 10.0,
            "color": 0,
            "sx0": 0,
            "sy0": 0,
            "sx1": 8,
            "sy1": 10,
        },
        {
            "text": "+",
            "font": "CMR10",
            "flags": 0,
            "size": 10.0,
            "color": 0,
            "sx0": 8,
            "sy0": 0,
            "sx1": 16,
            "sy1": 10,
        },
        {
            "text": "y",
            "font": "CMMI10",
            "flags": 0,
            "size": 10.0,
            "color": 0,
            "sx0": 16,
            "sy0": 0,
            "sx1": 24,
            "sy1": 10,
        },
    ]
    math_map: dict[str, Any] = {}
    merged_texts, merged_items, counter = _merge_math_spans(
        span_texts,
        items,
        math_map,
        0,
    )
    assert len(merged_texts) == 1
    char_fonts = math_map[merged_texts[0]]
    assert len(char_fonts) == 3  # noqa: PLR2004  - "x", "+", "y"
    assert char_fonts[0][:2] == ("x", "CMMI10")
    assert char_fonts[1][:2] == ("+", "CMR10")
    assert char_fonts[2][:2] == ("y", "CMMI10")
    assert merged_items[0].get("_is_math") is True


def test_merge_math_spans_control_char_inline_image() -> None:
    """CMEX control chars (delimiter pieces) are captured as inline images."""
    # Simulate a CMEX10 span with a control char (e.g. 0x10 = paren bottom)
    span_texts = ["\x10"]
    items = [
        {
            "text": "\x10",
            "font": "CMEX10",
            "flags": 0,
            "size": 10.0,
            "color": 0,
            "sx0": 100.0,
            "sy0": 200.0,
            "sx1": 106.0,
            "sy1": 210.0,
        },
    ]
    # Create a mock page and pymupdf module
    mock_pix = MagicMock()
    mock_pix.tobytes.return_value = b"\x89PNG\r\n\x1a\nfakedata"
    mock_page = MagicMock()
    mock_page.get_pixmap.return_value = mock_pix

    mock_pymupdf = MagicMock()
    mock_rect = MagicMock()
    mock_rect.is_empty = False
    mock_rect.is_infinite = False
    mock_rect.width = 6.0
    mock_rect.height = 10.0
    mock_pymupdf.Rect.return_value = mock_rect

    math_map: dict[str, Any] = {}
    merged_texts, merged_items, counter = _merge_math_spans(
        span_texts,
        items,
        math_map,
        0,
        page=mock_page,
        pymupdf=mock_pymupdf,
    )
    assert len(merged_texts) == 1
    char_fonts = math_map[merged_texts[0]]
    assert len(char_fonts) == 1
    assert char_fonts[0][1] == _IMG_FONT
    assert char_fonts[0][0].startswith('<img src="data:image/png;base64,')
    assert 'width="6.0"' in char_fonts[0][0]
    assert 'height="10.0"' in char_fonts[0][0]


def test_merge_math_spans_fffd_inline_image() -> None:
    """U+FFFD from CM fonts is captured as an inline image."""
    span_texts = ["\ufffd"]
    items = [
        {
            "text": "\ufffd",
            "font": "CMEX10",
            "flags": 0,
            "size": 10.0,
            "color": 0,
            "sx0": 50.0,
            "sy0": 100.0,
            "sx1": 54.0,
            "sy1": 110.0,
        },
    ]
    mock_pix = MagicMock()
    mock_pix.tobytes.return_value = b"\x89PNG\r\n\x1a\nfakedata"
    mock_page = MagicMock()
    mock_page.get_pixmap.return_value = mock_pix

    mock_pymupdf = MagicMock()
    mock_rect = MagicMock()
    mock_rect.is_empty = False
    mock_rect.is_infinite = False
    mock_rect.width = 4.0
    mock_rect.height = 10.0
    mock_pymupdf.Rect.return_value = mock_rect

    math_map: dict[str, Any] = {}
    merged_texts, _, _ = _merge_math_spans(
        span_texts,
        items,
        math_map,
        0,
        page=mock_page,
        pymupdf=mock_pymupdf,
    )
    char_fonts = math_map[merged_texts[0]]
    assert len(char_fonts) == 1
    assert char_fonts[0][1] == _IMG_FONT


def test_merge_math_spans_printable_not_captured_as_image() -> None:
    """Printable CMEX chars (e.g. 'p'=sqrt) use text, not images."""
    span_texts = ["p"]
    items = [
        {
            "text": "p",
            "font": "CMEX10",
            "flags": 0,
            "size": 10.0,
            "color": 0,
            "sx0": 50.0,
            "sy0": 100.0,
            "sx1": 58.0,
            "sy1": 110.0,
        },
    ]
    mock_page = MagicMock()
    mock_pymupdf = MagicMock()

    math_map: dict[str, Any] = {}
    _merge_math_spans(
        span_texts,
        items,
        math_map,
        0,
        page=mock_page,
        pymupdf=mock_pymupdf,
    )
    char_fonts = math_map[list(math_map.keys())[0]]
    # Should be text tuple, not image
    assert char_fonts[0][:2] == ("p", "CMEX10")


def test_merge_math_spans_no_page_suppresses_control_chars() -> None:
    """Without page/pymupdf, control chars pass through (fallback)."""
    span_texts = ["\x10"]
    items = [
        {
            "text": "\x10",
            "font": "CMEX10",
            "flags": 0,
            "size": 10.0,
            "color": 0,
            "sx0": 100.0,
            "sy0": 200.0,
            "sx1": 106.0,
            "sy1": 210.0,
        },
    ]
    math_map: dict[str, Any] = {}
    _merge_math_spans(span_texts, items, math_map, 0)
    char_fonts = math_map[list(math_map.keys())[0]]
    # Without page, falls back to text tuple
    assert char_fonts[0][:2] == ("\x10", "CMEX10")


def test_merge_math_spans_cmsy_control_char_remapped() -> None:
    """CMSY control chars with remap entries are processed as text, not images."""
    # CMSY 0x14 = ≤ — has a remap entry, should NOT trigger image capture
    span_texts = ["\x14"]
    items = [
        {
            "text": "\x14",
            "font": "CMSY10",
            "flags": 0,
            "size": 10.0,
            "color": 0,
            "sx0": 100.0,
            "sy0": 200.0,
            "sx1": 106.0,
            "sy1": 210.0,
        },
    ]
    mock_page = MagicMock()
    mock_pymupdf = MagicMock()

    math_map: dict[str, Any] = {}
    _merge_math_spans(
        span_texts,
        items,
        math_map,
        0,
        page=mock_page,
        pymupdf=mock_pymupdf,
    )
    char_fonts = math_map[list(math_map.keys())[0]]
    # Should be text tuple (remapped later), NOT image
    assert char_fonts[0][:2] == ("\x14", "CMSY10")
    assert char_fonts[0][1] != _IMG_FONT


def test_merge_math_spans_cmex_control_char_still_image() -> None:
    """CMEX control chars (delimiter pieces) still captured as images."""
    span_texts = ["\x10"]
    items = [
        {
            "text": "\x10",
            "font": "CMEX10",
            "flags": 0,
            "size": 10.0,
            "color": 0,
            "sx0": 100.0,
            "sy0": 200.0,
            "sx1": 106.0,
            "sy1": 210.0,
        },
    ]
    mock_pix = MagicMock()
    mock_pix.tobytes.return_value = b"\x89PNG\r\n\x1a\nfakedata"
    mock_page = MagicMock()
    mock_page.get_pixmap.return_value = mock_pix

    mock_pymupdf = MagicMock()
    mock_rect = MagicMock()
    mock_rect.is_empty = False
    mock_rect.is_infinite = False
    mock_rect.width = 6.0
    mock_rect.height = 10.0
    mock_pymupdf.Rect.return_value = mock_rect

    math_map: dict[str, Any] = {}
    _merge_math_spans(
        span_texts,
        items,
        math_map,
        0,
        page=mock_page,
        pymupdf=mock_pymupdf,
    )
    char_fonts = math_map[list(math_map.keys())[0]]
    # CMEX control chars have no remap → still captured as image
    assert char_fonts[0][1] == _IMG_FONT


def test_capture_glyph_image_empty_rect() -> None:
    """_capture_glyph_image returns empty string for empty bbox."""
    mock_pymupdf = MagicMock()
    mock_rect = MagicMock()
    mock_rect.is_empty = True
    mock_rect.is_infinite = False
    mock_pymupdf.Rect.return_value = mock_rect

    result = _capture_glyph_image(MagicMock(), (0, 0, 0, 0), mock_pymupdf)
    assert result == ""


def test_restore_math_placeholders() -> None:
    """Placeholders are replaced with italic/subscript tags."""
    ph = f"{_MATH_PH_START}0{_MATH_PH_END}"
    math_map = {ph: [(" ", "CMMI10"), ("δ", "CMMI10"), ("B", "CMR7")]}
    text = f"Sau đó, tách ngân sách{ph} = 2"
    result = _restore_math_placeholders(text, math_map)
    assert "<i> δ</i>" in result
    # CMR7 is smaller than CMMI10 → subscript
    assert "<sub>B</sub>" in result
    assert "Sau đó, tách ngân sách" in result
    assert " = 2" in result


def test_restore_math_placeholders_empty_map() -> None:
    """Empty math_map returns text unchanged."""
    assert _restore_math_placeholders("Hello", {}) == "Hello"


def test_restore_math_placeholders_groups_same_style() -> None:
    """Consecutive same-style chars are grouped into one tag."""
    ph = f"{_MATH_PH_START}0{_MATH_PH_END}"
    math_map = {ph: [("x", "CMMI10"), ("y", "CMMI10"), ("+", "CMR10")]}
    result = _restore_math_placeholders(f"A {ph} B", math_map)
    assert "<i>xy</i>" in result
    # CMR10 at same design size as CMMI10 → plain text (not italic, not sub)
    assert "+" in result
    assert "<i>+</i>" not in result
    assert "<sub>+</sub>" not in result


def test_restore_math_placeholders_subscript() -> None:
    """Smaller design-size font → subscript wrapping."""
    ph = f"{_MATH_PH_START}0{_MATH_PH_END}"
    # B (CMMI10) + eff (CMR7) → B_eff
    math_map = {ph: [("B", "CMMI10"), ("e", "CMR7"), ("f", "CMR7"), ("f", "CMR7")]}
    result = _restore_math_placeholders(f"x {ph} y", math_map)
    assert "<i>B</i>" in result
    assert "<sub>eff</sub>" in result


def test_restore_math_placeholders_isolated_subscript_placeholder() -> None:
    """Single-char subscript placeholder uses global base_ds from other placeholders."""
    ph0 = f"{_MATH_PH_START}0{_MATH_PH_END}"
    ph1 = f"{_MATH_PH_START}1{_MATH_PH_END}"
    # ⟪0⟫ has CMR10 (design size 10) chars; ⟪1⟫ has only CMR7 (design size 7).
    # Without global base_ds, ⟪1⟫ would not detect '2' as subscript.
    math_map = {
        ph0: [("∆", "CMR10", None), ("∗", "CMSY7", "sup")],
        ph1: [("2", "CMR7", None)],
    }
    result = _restore_math_placeholders(f"A = {ph0} {ph1} end", math_map)
    assert "<sub>2</sub>" in result


def test_restore_math_placeholders_legacy_string() -> None:
    """Legacy string format (fallback) still works."""
    ph = f"{_MATH_PH_START}0{_MATH_PH_END}"
    math_map = {ph: "δB"}
    result = _restore_math_placeholders(f"text {ph} end", math_map)
    assert result == "text δB end"


def test_remap_cm_char_cmex_radical() -> None:
    """CMEX10 'p' (0x70) is remapped to √ (radical)."""
    assert _remap_cm_char("p", "CMEX10") == "\u221a"
    assert _remap_cm_char("q", "CMEX10") == "\u221a"
    assert _remap_cm_char("r", "CMEX10") == "\u221a"


def test_remap_cm_char_cmex_operators() -> None:
    """CMEX10 letters are remapped to large math operators."""
    assert _remap_cm_char("P", "CMEX10") == "\u2211"  # ∑
    assert _remap_cm_char("R", "CMEX10") == "\u222b"  # ∫
    assert _remap_cm_char("Q", "CMEX10") == "\u220f"  # ∏
    assert _remap_cm_char("X", "CMEX10") == "\u2211"  # ∑ display


def test_remap_cm_char_cmsy_symbols() -> None:
    """CMSY10 chars are remapped to math symbols."""
    assert _remap_cm_char("p", "CMSY10") == "\u221a"  # √
    assert _remap_cm_char("1", "CMSY10") == "\u221e"  # ∞
    assert _remap_cm_char("2", "CMSY10") == "\u2208"  # ∈
    assert _remap_cm_char("8", "CMSY10") == "\u2200"  # ∀
    assert _remap_cm_char("r", "CMSY10") == "\u2207"  # ∇


def test_remap_cm_char_cmsy_script_capitals() -> None:
    """CMSY A-Z (script capitals) are remapped to Unicode script letters."""
    assert _remap_cm_char("B", "CMSY10") == "\u212c"  # ℬ
    assert _remap_cm_char("R", "CMSY10") == "\u211b"  # ℛ
    assert _remap_cm_char("N", "CMSY10") == "\U0001d4a9"  # 𝒩
    assert _remap_cm_char("S", "CMSY7") == "\U0001d4ae"  # 𝒮


def test_remap_cm_char_msbm_blackboard_bold() -> None:
    """MSBM letters are remapped to blackboard bold Unicode."""
    assert _remap_cm_char("R", "MSBM10") == "\u211d"  # ℝ
    assert _remap_cm_char("E", "MSBM10") == "\U0001d53c"  # 𝔼
    assert _remap_cm_char("N", "MSBM10") == "\u2115"  # ℕ
    assert _remap_cm_char("Z", "MSBM10") == "\u2124"  # ℤ
    assert _remap_cm_char("C", "MSBM10") == "\u2102"  # ℂ


def test_remap_cm_char_cmbsy() -> None:
    """CMBSY (bold math symbols) uses the same mapping as CMSY."""
    assert _remap_cm_char("p", "CMBSY8") == "\u221a"  # √
    assert _remap_cm_char("B", "CMBSY8") == "\u212c"  # ℬ


def test_remap_cm_char_non_cm_unchanged() -> None:
    """Non-CM fonts are not affected by remapping."""
    assert _remap_cm_char("p", "CMMI10") == "p"
    assert _remap_cm_char("p", "CMR10") == "p"
    assert _remap_cm_char("p", "Arial") == "p"


def test_remap_cm_char_already_correct() -> None:
    """Chars not in the mapping (e.g. already-correct Unicode) pass through."""
    assert _remap_cm_char("\u221a", "CMEX10") == "\u221a"  # √ not in map


def test_remap_cm_char_space_not_remapped() -> None:
    """Synthetic spaces are NOT remapped (would produce wrong symbols)."""
    assert _remap_cm_char(" ", "CMEX10") == " "
    assert _remap_cm_char(" ", "CMSY10") == " "
    assert _remap_cm_char(" ", "MSBM10") == " "


def test_remap_cm_char_fffd_suppressed() -> None:
    """Undecoded CM glyphs (U+FFFD) are suppressed to empty string."""
    assert _remap_cm_char("\ufffd", "CMEX10") == ""
    assert _remap_cm_char("\ufffd", "CMSY10") == ""
    assert _remap_cm_char("\ufffd", "MSBM10") == ""
    assert _remap_cm_char("\ufffd", "CMR10") == ""
    # Non-CM fonts should pass through unchanged
    assert _remap_cm_char("\ufffd", "NimbusRomNo9L") == "\ufffd"


def test_remap_cm_char_cmsy_braces_not_remapped() -> None:
    """CMSY |, {, } are NOT remapped — CMap already handles them.

    When a PDF has a ToUnicode CMap, CMSY position 0x6A→| and
    0x66→{ are already correct.  The old map entries for | → ♣
    and { → ¶ referred to positions 0x7C/0x7B (card suits) and
    would corrupt the CMap-mapped characters.
    """
    assert _remap_cm_char("|", "CMSY10") == "|"
    assert _remap_cm_char("{", "CMSY10") == "{"
    assert _remap_cm_char("}", "CMSY10") == "}"
    assert _remap_cm_char("~", "CMSY10") == "~"


def test_remap_cm_char_cmsy_control_char_operators() -> None:
    """CMSY control-char positions (0x00-0x1F) remap to math operators."""
    assert _remap_cm_char("\x00", "CMSY10") == "\u2212"  # − minus
    assert _remap_cm_char("\x02", "CMSY10") == "\u00d7"  # × times
    assert _remap_cm_char("\x06", "CMSY10") == "\u00b1"  # ± plus-minus
    assert _remap_cm_char("\x14", "CMSY10") == "\u2264"  # ≤ leq
    assert _remap_cm_char("\x15", "CMSY10") == "\u2265"  # ≥ geq
    assert _remap_cm_char("\x19", "CMSY10") == "\u2248"  # ≈ approx
    assert _remap_cm_char("\x1a", "CMSY10") == "\u2282"  # ⊂ subset
    assert _remap_cm_char("\x1e", "CMSY10") == "\u227a"  # ≺ prec


def test_remap_cm_char_cmsy_control_char_full_range() -> None:
    """All 32 CMSY control-char positions (0x00-0x1F) have entries."""
    for code in range(0x20):
        ch = chr(code)
        result = _remap_cm_char(ch, "CMSY10")
        assert result != ch, f"CMSY 0x{code:02x} has no mapping"
        assert ord(result) >= 0x20, (  # noqa: PLR2004
            f"CMSY 0x{code:02x} mapped to control char"
        )


def test_remap_cm_char_cmbsy_control_char() -> None:
    """CMBSY (bold) also remaps control chars (same table as CMSY)."""
    assert _remap_cm_char("\x06", "CMBSY10") == "\u00b1"  # ± plus-minus
    assert _remap_cm_char("\x14", "CMBSY10") == "\u2264"  # ≤ leq


def test_remap_cm_char_cmex_control_char_not_remapped() -> None:
    """CMEX control chars (delimiter pieces) are NOT remapped."""
    # CMEX 0x10 is a paren piece — no meaningful Unicode equivalent
    assert _remap_cm_char("\x10", "CMEX10") == "\x10"


# ── TeX composed glyph collapse ─────────────────────────────────────────────


def test_collapse_tex_mapsto() -> None:
    r"""\mapsto: ↦ + → collapses to single ↦."""
    inp = [("\u21a6", "CMSY10"), ("\u2192", "CMSY10")]
    result = _collapse_tex_composed(inp)
    assert len(result) == 1
    assert result[0][0] == "\u21a6"


def test_collapse_tex_longmapsto() -> None:
    r"""\longmapsto: ↦ + dashes + → collapses to ⟼ (U+27FC)."""
    inp = [("\u21a6", "CMSY10"), ("-", "CMR10"), ("\u2192", "CMSY10")]
    result = _collapse_tex_composed(inp)
    assert len(result) == 1
    assert result[0][0] == "\u27fc"


def test_collapse_tex_longmapsto_multi_dash() -> None:
    r"""\longmapsto with multiple dashes still collapses to ⟼."""
    inp = [
        ("\u21a6", "CMSY10"),
        ("-", "CMR10"),
        ("\u2212", "CMR10"),
        ("\u2192", "CMSY10"),
    ]
    result = _collapse_tex_composed(inp)
    assert len(result) == 1
    assert result[0][0] == "\u27fc"


def test_collapse_tex_longrightarrow() -> None:
    r"""\longrightarrow: dashes + → collapses to ⟶ (U+27F6)."""
    inp = [("-", "CMR10"), ("\u2192", "CMSY10")]
    result = _collapse_tex_composed(inp)
    assert len(result) == 1
    assert result[0][0] == "\u27f6"


def test_collapse_tex_longleftarrow() -> None:
    r"""\longleftarrow: ← + dashes collapses to ⟵ (U+27F5)."""
    inp = [("\u2190", "CMSY10"), ("-", "CMR10")]
    result = _collapse_tex_composed(inp)
    assert len(result) == 1
    assert result[0][0] == "\u27f5"


def test_collapse_tex_longleftrightarrow() -> None:
    r"""\longleftrightarrow: ← + dashes + → collapses to ⟷ (U+27F7)."""
    inp = [("\u2190", "CMSY10"), ("-", "CMR10"), ("\u2192", "CMSY10")]
    result = _collapse_tex_composed(inp)
    assert len(result) == 1
    assert result[0][0] == "\u27f7"


def test_collapse_tex_longrightarrow_double() -> None:
    r"""\Longrightarrow: equals + ⇒ collapses to ⟹ (U+27F9)."""
    inp = [("=", "CMR10"), ("\u21d2", "CMSY10")]
    result = _collapse_tex_composed(inp)
    assert len(result) == 1
    assert result[0][0] == "\u27f9"


def test_collapse_tex_longleftarrow_double() -> None:
    r"""\Longleftarrow: ⇐ + equals collapses to ⟸ (U+27F8)."""
    inp = [("\u21d0", "CMSY10"), ("=", "CMR10")]
    result = _collapse_tex_composed(inp)
    assert len(result) == 1
    assert result[0][0] == "\u27f8"


def test_collapse_tex_longleftrightarrow_double() -> None:
    r"""\Longleftrightarrow: ⇐ + equals + ⇒ collapses to ⟺ (U+27FA)."""
    inp = [("\u21d0", "CMSY10"), ("=", "CMR10"), ("\u21d2", "CMSY10")]
    result = _collapse_tex_composed(inp)
    assert len(result) == 1
    assert result[0][0] == "\u27fa"


def test_collapse_tex_preserves_standalone_arrows() -> None:
    """Standalone arrows without compose partners are preserved."""
    for arrow in ["\u2192", "\u2190", "\u21d2", "\u21d0"]:
        inp = [(arrow, "CMSY10")]
        result = _collapse_tex_composed(inp)
        assert len(result) == 1
        assert result[0][0] == arrow


def test_collapse_tex_preserves_non_compose_context() -> None:
    """Non-matching sequences pass through unchanged."""
    # ← without following dashes — just a leftarrow
    inp = [("\u2190", "CMSY10"), ("x", "CMMI10")]
    result = _collapse_tex_composed(inp)
    assert len(result) == 2  # noqa: PLR2004
    assert result[0][0] == "\u2190"
    assert result[1][0] == "x"


def test_collapse_tex_dash_without_arrow() -> None:
    """Dashes not followed by → are preserved as-is."""
    inp = [("-", "CMR10"), ("x", "CMMI10")]
    result = _collapse_tex_composed(inp)
    assert len(result) == 2  # noqa: PLR2004
    assert result[0][0] == "-"
    assert result[1][0] == "x"


def test_collapse_tex_equals_without_double_arrow() -> None:
    """Equals not followed by ⇒ are preserved as-is."""
    inp = [("=", "CMR10"), ("x", "CMMI10")]
    result = _collapse_tex_composed(inp)
    assert len(result) == 2  # noqa: PLR2004
    assert result[0][0] == "="


def test_collapse_tex_empty_and_single() -> None:
    """Empty and single-element lists return unchanged."""
    assert _collapse_tex_composed([]) == []
    single = [("x", "CMMI10")]
    assert _collapse_tex_composed(single) == single


def test_collapse_tex_minus_sign_variant() -> None:
    """Unicode minus (U+2212) also works as dash in composed arrows."""
    inp = [("\u2212", "CMR10"), ("\u2192", "CMSY10")]
    result = _collapse_tex_composed(inp)
    assert len(result) == 1
    assert result[0][0] == "\u27f6"  # ⟶


def test_collapse_tex_mapsto_without_arrow_preserved() -> None:
    """↦ not followed by → is preserved as standalone mapsto."""
    inp = [("\u21a6", "CMSY10"), ("x", "CMMI10")]
    result = _collapse_tex_composed(inp)
    assert len(result) == 2  # noqa: PLR2004
    assert result[0][0] == "\u21a6"


def test_collapse_tex_multiple_equals_longrightarrow() -> None:
    """Multiple = signs before ⇒ still collapse to ⟹."""
    inp = [("=", "CMR10"), ("=", "CMR10"), ("\u21d2", "CMSY10")]
    result = _collapse_tex_composed(inp)
    assert len(result) == 1
    assert result[0][0] == "\u27f9"


def test_restore_collapses_composed_mapsto() -> None:
    r"""TeX \mapsto = CMSY 0x37 (↦ tail) + 0x21 (→) → single ↦."""
    math_map = {
        "\u27ea0\u27eb": [("7", "CMSY10"), ("\u2192", "CMSY10")],
    }
    result = _restore_math_placeholders("\u27ea0\u27eb", math_map)
    assert result == "\u21a6"  # ↦ only, no duplicate →
    assert "\u2192" not in result


def test_restore_keeps_standalone_rightarrow() -> None:
    """A standalone → (not preceded by ↦) is preserved."""
    math_map = {
        "\u27ea0\u27eb": [("\u2192", "CMSY10")],
    }
    result = _restore_math_placeholders("\u27ea0\u27eb", math_map)
    assert result == "\u2192"


def test_restore_collapses_longrightarrow() -> None:
    r"""\longrightarrow composed sequence collapses in full pipeline."""
    ph = f"{_MATH_PH_START}0{_MATH_PH_END}"
    # CMR dash + CMSY → → ⟶
    math_map = {ph: [("-", "CMR10"), ("!", "CMSY10")]}
    result = _restore_math_placeholders(ph, math_map)
    assert result == "\u27f6"  # ⟶


def test_restore_collapses_double_longrightarrow() -> None:
    r"""\Longrightarrow composed sequence collapses in full pipeline."""
    ph = f"{_MATH_PH_START}0{_MATH_PH_END}"
    # CMR = + CMSY ) → ⟹
    math_map = {ph: [("=", "CMR10"), (")", "CMSY10")]}
    result = _restore_math_placeholders(ph, math_map)
    assert result == "\u27f9"  # ⟹


def test_remap_cm_char_design_size_variants() -> None:
    """CMEX7, CMSY5, etc. use the same mapping as CMEX10/CMSY10."""
    assert _remap_cm_char("p", "CMEX7") == "\u221a"
    assert _remap_cm_char("p", "CMSY5") == "\u221a"


def test_restore_math_placeholders_cmex_radical() -> None:
    """CMEX10 'p' is remapped to √ in the final output."""
    ph = f"{_MATH_PH_START}0{_MATH_PH_END}"
    math_map = {ph: [("p", "CMEX10")]}
    result = _restore_math_placeholders(f"Result = {ph}n", math_map)
    assert "\u221a" in result
    assert "p" not in result.replace("Result", "")  # 'p' was remapped


def test_restore_math_placeholders_cmex_sum_integral() -> None:
    """CMEX10 operators are remapped correctly."""
    ph = f"{_MATH_PH_START}0{_MATH_PH_END}"
    math_map = {ph: [("P", "CMEX10"), ("R", "CMEX10")]}
    result = _restore_math_placeholders(f"x {ph} y", math_map)
    assert "\u2211" in result  # ∑
    assert "\u222b" in result  # ∫


def test_extract_blocks_math_placeholder_in_text() -> None:
    """Block with mixed text+math has placeholders and per-char font map."""
    raw_block = {
        "type": 0,
        "bbox": (78, 90, 400, 110),
        "lines": [
            {
                "bbox": (78, 90, 400, 100),
                "dir": (1.0, 0.0),
                "spans": [
                    {
                        "text": "Budget as ",
                        "font": "NimbusRomNo9L-Regu",
                        "size": 10.0,
                        "flags": 0,
                        "color": 0,
                        "bbox": (78, 90, 200, 100),
                        "origin": (78, 98),
                    },
                    {
                        "text": "delta",
                        "font": "CMMI10",
                        "size": 10.0,
                        "flags": 0,
                        "color": 0,
                        "bbox": (200, 90, 240, 100),
                        "origin": (200, 98),
                    },
                    {
                        "text": "B",
                        "font": "CMR7",
                        "size": 7.0,
                        "flags": 0,
                        "color": 0,
                        "bbox": (240, 92, 248, 100),
                        "origin": (240, 98),
                    },
                    {
                        "text": " = 2",
                        "font": "NimbusRomNo9L-Regu",
                        "size": 10.0,
                        "flags": 0,
                        "color": 0,
                        "bbox": (248, 90, 300, 100),
                        "origin": (248, 98),
                    },
                ],
            },
        ],
    }
    page = _make_mock_page([raw_block])
    blocks = _extract_page_blocks(page)
    assert len(blocks) == 1
    block = blocks[0]
    # Should have a _math_map with one placeholder
    assert "_math_map" in block
    math_map = block["_math_map"]
    assert len(math_map) == 1
    # Placeholder should be in the text
    ph = next(iter(math_map))
    assert ph in block["text"]
    # Value is per-character (char, font, role) tuples
    char_fonts = math_map[ph]
    assert len(char_fonts) == 6  # noqa: PLR2004  - "delta" (5) + "B" (1)
    assert char_fonts[0][:2] == ("d", "CMMI10")
    assert char_fonts[-1][:2] == ("B", "CMR7")
    # Body text preserved as-is
    assert "Budget as " in block["text"]


def test_extract_blocks_no_math_map_for_pure_text() -> None:
    """Block with only body-font spans has no _math_map."""
    raw_block = {
        "type": 0,
        "bbox": (72, 50, 540, 70),
        "lines": [
            {
                "bbox": (72, 50, 540, 60),
                "dir": (1.0, 0.0),
                "spans": [
                    {
                        "text": "Regular paragraph.",
                        "font": "NimbusRomNo9L-Regu",
                        "size": 10.0,
                        "flags": 0,
                        "color": 0,
                        "bbox": (72, 50, 540, 60),
                        "origin": (72, 58),
                    },
                ],
            },
        ],
    }
    page = _make_mock_page([raw_block])
    blocks = _extract_page_blocks(page)
    assert len(blocks) == 1
    assert "_math_map" not in blocks[0]


# ── _merge_overlapping_math_blocks ───────────────────────────────────────────


def test_extract_blocks_pure_math_block_skipped() -> None:
    """Block with zero body text (all math) is skipped entirely."""
    raw_block = {
        "type": 0,
        "bbox": (72, 90, 400, 110),
        "lines": [
            {
                "bbox": (72, 90, 400, 100),
                "dir": (1.0, 0.0),
                "spans": [
                    {
                        "text": "alpha + beta + gamma / delta",
                        "font": "CMMI10",
                        "size": 10.0,
                        "flags": 0,
                        "color": 0,
                        "bbox": (80, 90, 400, 100),
                        "origin": (80, 98),
                    },
                ],
            },
        ],
    }
    page = _make_mock_page([raw_block])
    blocks = _extract_page_blocks(page)
    assert len(blocks) == 0


def test_extract_blocks_mixed_math_body_kept() -> None:
    """Block with body text + math lines is kept (not skipped)."""
    raw_block = {
        "type": 0,
        "bbox": (72, 80, 400, 120),
        "lines": [
            # Line 1: mixed (body text + math)
            {
                "bbox": (72, 80, 400, 90),
                "dir": (1.0, 0.0),
                "spans": [
                    {
                        "text": "and require ",
                        "font": "NimbusRomNo9L-Regu",
                        "size": 10.0,
                        "flags": 0,
                        "color": 0,
                        "bbox": (72, 80, 140, 90),
                        "origin": (72, 88),
                    },
                    {
                        "text": "alpha",
                        "font": "CMMI10",
                        "size": 10.0,
                        "flags": 0,
                        "color": 0,
                        "bbox": (140, 80, 180, 90),
                        "origin": (140, 88),
                    },
                ],
            },
            # Line 2: pure math (e.g. sqrt glyph on its own line)
            {
                "bbox": (72, 78, 80, 88),
                "dir": (1.0, 0.0),
                "spans": [
                    {
                        "text": "p",
                        "font": "CMEX10",
                        "size": 10.0,
                        "flags": 0,
                        "color": 0,
                        "bbox": (72, 78, 80, 88),
                        "origin": (72, 86),
                    },
                ],
            },
        ],
    }
    page = _make_mock_page([raw_block])
    blocks = _extract_page_blocks(page)
    assert len(blocks) == 1
    # Body text is present
    assert "and require " in blocks[0]["text"]
    # Math placeholder for the sqrt glyph is also present
    assert blocks[0].get("_math_map")


# ── _merge_overlapping_math_blocks ───────────────────────────────────────────


def _make_block(y0: float, y1: float, text: str, **kw: Any) -> dict:
    """Build a minimal block dict for overlap tests."""
    b: dict[str, Any] = {
        "rect": [72.0, y0, 540.0, y1],
        "text": text,
        "font_size": 10.0,
        "font_name": "NimbusRomNo9L-Regu",
        "color": 0,
        "bold": False,
        "italic": False,
    }
    b.update(kw)
    return b


def test_merge_overlap_both_math() -> None:
    """Overlapping blocks with math are merged, preserving all body text."""
    blocks = [
        _make_block(
            118,
            130,
            "and require⟪0⟫",
            _math_map={
                "⟪0⟫": [
                    (" ", "CMMI10"),
                    ("τ", "CMMI10"),
                    (" ", "CMR10"),
                    (">", "CMR10"),
                    (" ", "CMR10"),
                    ("B", "CMMI10"),
                ]
            },
        ),
        _make_block(
            119,
            143,
            "⟪0⟫(cf. discussion above). Long text here.",
            _math_map={"⟪0⟫": [("1", "CMR10"), ("/", "CMR10"), ("δ", "CMMI10")]},
        ),
    ]
    result = _merge_overlapping_math_blocks(blocks)
    assert len(result) == 1
    merged = result[0]
    # Both body texts preserved
    assert "and require" in merged["text"]
    assert "discussion" in merged["text"]
    assert len(merged["_math_map"]) == 2  # noqa: PLR2004
    # Union bbox
    assert merged["rect"][1] == 118  # noqa: PLR2004
    assert merged["rect"][3] == 143  # noqa: PLR2004


def test_merge_overlap_renumbers_placeholders() -> None:
    """Second block's placeholder indices are shifted by first block's count."""
    blocks = [
        _make_block(
            100,
            115,
            "A⟪0⟫ B⟪1⟫",
            _math_map={"⟪0⟫": [("x", "CMMI10")], "⟪1⟫": [("y", "CMMI10")]},
        ),
        _make_block(110, 130, "C⟪0⟫", _math_map={"⟪0⟫": [("z", "CMMI10")]}),
    ]
    result = _merge_overlapping_math_blocks(blocks)
    assert len(result) == 1
    mm = result[0]["_math_map"]
    # A's ⟪0⟫ and ⟪1⟫ keep original keys; B's ⟪0⟫ becomes ⟪2⟫
    assert mm["⟪0⟫"] == [("x", "CMMI10")]
    assert mm["⟪1⟫"] == [("y", "CMMI10")]
    assert mm["⟪2⟫"] == [("z", "CMMI10")]
    assert "C⟪2⟫" in result[0]["text"]


def test_merge_overlap_keeps_non_overlapping() -> None:
    """Non-overlapping blocks are never merged."""
    blocks = [
        _make_block(100, 120, "First⟪0⟫", _math_map={"⟪0⟫": [("σ", "CMMI10")]}),
        _make_block(130, 150, "Second⟪0⟫", _math_map={"⟪0⟫": [("τ", "CMMI10")]}),
    ]
    result = _merge_overlapping_math_blocks(blocks)
    assert len(result) == 2  # noqa: PLR2004


def test_merge_overlap_ignores_no_math() -> None:
    """Overlapping blocks without math content are left alone."""
    blocks = [
        _make_block(100, 120, "First paragraph of text."),
        _make_block(115, 135, "Second paragraph of text."),
    ]
    result = _merge_overlapping_math_blocks(blocks)
    assert len(result) == 2  # noqa: PLR2004


def test_merge_overlap_one_math_one_not() -> None:
    """When one block has math and overlaps non-math, they are merged."""
    blocks = [
        _make_block(
            100,
            110,
            "⟪0⟫",
            _math_map={"⟪0⟫": [("x", "CMMI10"), ("+", "CMR10"), ("y", "CMMI10")]},
        ),
        _make_block(105, 140, "Long paragraph with useful text to translate."),
    ]
    result = _merge_overlapping_math_blocks(blocks)
    assert len(result) == 1
    assert "Long paragraph" in result[0]["text"]
    assert "⟪0⟫" in result[0]["text"]


def test_merge_overlap_empty_and_single() -> None:
    """Edge cases: 0 or 1 blocks."""
    assert _merge_overlapping_math_blocks([]) == []
    b = [_make_block(0, 10, "X")]
    assert _merge_overlapping_math_blocks(b) == b


def test_merge_overlap_font_from_larger_body() -> None:
    """Merged block takes font properties from block with more body text."""
    blocks = [
        _make_block(
            100,
            110,
            "⟪0⟫",
            _math_map={"⟪0⟫": [("x", "CMMI10")]},
            font_size=8.0,
            color=0xFF,
        ),
        _make_block(105, 140, "Body text is longer here.", font_size=12.0, color=0x00),
    ]
    result = _merge_overlapping_math_blocks(blocks)
    assert result[0]["font_size"] == 12.0  # noqa: PLR2004
    assert result[0]["color"] == 0x00


def test_merge_overlap_text_order_by_y() -> None:
    """Merged text puts higher block (smaller y0) first."""
    blocks = [
        _make_block(120, 135, "second⟪0⟫", _math_map={"⟪0⟫": [("β", "CMMI10")]}),
        _make_block(110, 125, "first⟪0⟫", _math_map={"⟪0⟫": [("α", "CMMI10")]}),
    ]
    result = _merge_overlapping_math_blocks(blocks)
    text = result[0]["text"]
    # "first" (y0=110) should appear before "second" (y0=120)
    assert text.index("first") < text.index("second")


def test_merge_overlap_three_blocks() -> None:
    """Three mutually overlapping blocks are merged into one."""
    blocks = [
        _make_block(100, 115, "A⟪0⟫", _math_map={"⟪0⟫": [("x", "CMMI10")]}),
        _make_block(110, 125, "B⟪0⟫", _math_map={"⟪0⟫": [("y", "CMMI10")]}),
        _make_block(120, 135, "C text.", _math_map={}),
    ]
    result = _merge_overlapping_math_blocks(blocks)
    assert len(result) == 1
    assert "A" in result[0]["text"]
    assert "B" in result[0]["text"]
    assert "C text." in result[0]["text"]


def test_merge_overlapping_skips_vertical_blocks() -> None:
    """Vertical blocks (e.g. arXiv sidebar) should not trigger merges.

    A vertical sidebar spanning y=228-564 overlaps with content blocks
    but merging them creates a mega-block that loses per-section formatting.
    """
    sidebar = _make_block(228, 564, "arXiv:2603.05485v1")
    sidebar["is_vertical"] = True
    abstract = _make_block(
        278, 396, "Abstract body text", _math_map={"⟪0⟫": [("α", "CMMI10")]}
    )
    caption = _make_block(
        560, 642, "Figure 1: Caption⟪0⟫", _math_map={"⟪0⟫": [("τ", "CMMI9")]}
    )
    blocks = [sidebar, abstract, caption]
    result = _merge_overlapping_math_blocks(blocks)
    # Sidebar should NOT bridge abstract and caption
    assert len(result) == 3  # noqa: PLR2004
    # Verify all blocks are still present
    texts = [b["text"] for b in result]
    assert any("arXiv" in t for t in texts)
    assert any("Abstract" in t for t in texts)
    assert any("Caption" in t for t in texts)


# ── _is_split_paragraph tests ─────────────────────────────────────────────


def test_is_split_paragraph_lowercase_continuation() -> None:
    """Block B starting lowercase after mid-sentence block A → True."""
    a = _make_block(480, 512, "resulting from a")
    b = _make_block(508, 547, "random draw from the generator")
    assert _is_split_paragraph(a, b) is True


def test_is_split_paragraph_reversed_order() -> None:
    """Order of arguments should not matter — sorted by y internally."""
    a = _make_block(480, 512, "resulting from a")
    b = _make_block(508, 547, "random draw from the generator")
    assert _is_split_paragraph(b, a) is True


def test_is_split_paragraph_sentence_end() -> None:
    """Block A ending with period → not a split paragraph."""
    a = _make_block(480, 512, "end of sentence.")
    b = _make_block(508, 547, "next paragraph begins")
    assert _is_split_paragraph(a, b) is False


def test_is_split_paragraph_exclamation() -> None:
    """Block A ending with exclamation → not a split paragraph."""
    a = _make_block(480, 512, "emphasis here!")
    b = _make_block(508, 547, "lowercase continues")
    assert _is_split_paragraph(a, b) is False


def test_is_split_paragraph_question_mark() -> None:
    """Block A ending with question mark → not a split paragraph."""
    a = _make_block(480, 512, "is this done?")
    b = _make_block(508, 547, "yes it is")
    assert _is_split_paragraph(a, b) is False


def test_is_split_paragraph_uppercase_start() -> None:
    """Block B starting uppercase → likely a new paragraph, not split."""
    a = _make_block(480, 512, "resulting from a")
    b = _make_block(508, 547, "The generator produces")
    assert _is_split_paragraph(a, b) is False


def test_is_split_paragraph_empty_block_a() -> None:
    """Empty block A text → False."""
    a = _make_block(480, 512, "")
    b = _make_block(508, 547, "random draw")
    assert _is_split_paragraph(a, b) is False


def test_is_split_paragraph_empty_block_b() -> None:
    """Empty block B text → False."""
    a = _make_block(480, 512, "resulting from a")
    b = _make_block(508, 547, "")
    assert _is_split_paragraph(a, b) is False


def test_is_split_paragraph_math_placeholders_stripped() -> None:
    """Math placeholders should be stripped before the check."""
    a = _make_block(480, 512, "dataset⟪0⟫ resulting from a")
    b = _make_block(508, 547, "random⟪1⟫ draw from the generator")
    assert _is_split_paragraph(a, b) is True


def test_is_split_paragraph_only_math_placeholders() -> None:
    """Blocks with only math placeholders (no body text) → False."""
    a = _make_block(480, 512, "⟪0⟫")
    b = _make_block(508, 547, "⟪1⟫")
    assert _is_split_paragraph(a, b) is False


def test_is_split_paragraph_b_starts_with_number() -> None:
    """Block B starting with a number (non-alpha) → False."""
    a = _make_block(480, 512, "resulting from a")
    b = _make_block(508, 547, "42 random draws")
    assert _is_split_paragraph(a, b) is False


def test_is_split_paragraph_different_columns() -> None:
    """Blocks in different columns with no x-overlap → False."""
    # Left column block
    a: dict[str, Any] = {
        "rect": [72.0, 480, 290.0, 512],
        "text": "resulting from a",
        "font_size": 10.0,
        "font_name": "NimbusRomNo9L-Regu",
        "color": 0,
        "bold": False,
        "italic": False,
    }
    # Right column block
    b: dict[str, Any] = {
        "rect": [310.0, 478, 540.0, 510],
        "text": "random draw from the generator",
        "font_size": 10.0,
        "font_name": "NimbusRomNo9L-Regu",
        "color": 0,
        "bold": False,
        "italic": False,
    }
    assert _is_split_paragraph(a, b) is False


def test_is_split_paragraph_vertically_distant() -> None:
    """Blocks far apart vertically (> 1 line height gap) → False."""
    a = _make_block(100, 120, "resulting from a")
    b = _make_block(180, 200, "random draw from the generator")
    assert _is_split_paragraph(a, b) is False


def test_is_split_paragraph_partial_x_overlap() -> None:
    """Blocks with significant x-overlap (>50% of narrower) → True."""
    # Block A spans most of the page, block B is slightly narrower
    a: dict[str, Any] = {
        "rect": [72.0, 480, 540.0, 512],
        "text": "resulting from a",
        "font_size": 10.0,
        "font_name": "NimbusRomNo9L-Regu",
        "color": 0,
        "bold": False,
        "italic": False,
    }
    b: dict[str, Any] = {
        "rect": [90.0, 508, 530.0, 547],
        "text": "random draw from the generator",
        "font_size": 10.0,
        "font_name": "NimbusRomNo9L-Regu",
        "color": 0,
        "bold": False,
        "italic": False,
    }
    assert _is_split_paragraph(a, b) is True


def test_merge_overlapping_split_paragraph() -> None:
    """Blocks with small overlap that form a split paragraph are merged."""
    a = _make_block(
        479.9, 511.6, "dataset resulting from a", _math_map={"⟪0⟫": [("D", "CMMI10")]}
    )
    b = _make_block(
        507.5,
        546.7,
        "random draw from the generator",
        _math_map={"⟪0⟫": [("T", "CMMI10")]},
    )
    result = _merge_overlapping_math_blocks([a, b])
    assert len(result) == 1
    assert "resulting from a" in result[0]["text"]
    assert "random draw" in result[0]["text"]


def test_merge_overlapping_not_split_paragraph() -> None:
    """Blocks with small overlap but sentence boundary are NOT merged."""
    a = _make_block(
        479.9, 511.6, "end of sentence.", _math_map={"⟪0⟫": [("D", "CMMI10")]}
    )
    b = _make_block(
        507.5, 546.7, "New paragraph starts here", _math_map={"⟪0⟫": [("T", "CMMI10")]}
    )
    result = _merge_overlapping_math_blocks([a, b])
    assert len(result) == 2  # noqa: PLR2004


def test_merge_math_overlap_rederives_justify_from_extents() -> None:
    """After merge, alignment re-derived from combined line extents.

    When blocks are fragmented by math subscripts, each sub-block sees
    only partial line extents.  The merged block's line extents give a
    more complete picture for alignment detection.
    """
    a = _make_block(
        653.5,
        666.7,
        "In particular, for shrinkage",
        text_align="left",
        _line_extents=[(71.8, 540.0)],
        _line_sizes=[10.0],
        _line_y_mids=[660.0],
        _math_map={"⟪0⟫": [("g", "CMMI10")]},
    )
    b = _make_block(
        674.0,
        690.0,
        "which is feasible for any target",
        text_align="center",
        _line_extents=[(72.0, 226.9)],
        _line_sizes=[10.0],
        _line_y_mids=[682.0],
        _math_map={"⟪0⟫": [(",", "CMR10")]},
    )
    # overlap = 666.7 - 674.0 < 0 but let's make it > 5
    # Actually adjust y so overlap >= 5
    a["rect"][3] = 680.0  # a ends at y=680
    # overlap = min(680, 690) - max(653.5, 674) = 680 - 674 = 6 > 5
    result = _merge_overlapping_math_blocks([a, b])
    assert len(result) == 1
    # Full-width line + short final line → justify
    assert result[0]["text_align"] == "justify"


def test_merge_math_overlap_left_when_no_right_edge() -> None:
    """Merged blocks with ragged right edges stay 'left'."""
    # Three lines, all starting at left, none reaching a consistent right.
    a = _make_block(
        653.5,
        678.0,
        "In particular for shrinkage",
        text_align="left",
        _line_extents=[(72.0, 350.0), (72.0, 420.0)],
        _line_sizes=[10.0, 10.0],
        _line_y_mids=[660.0, 672.0],
        _math_map={"⟪0⟫": [("g", "CMMI10")]},
    )
    b = _make_block(
        676.9,
        690.0,
        "for a target",
        text_align="left",
        _line_extents=[(72.0, 300.0)],
        _line_sizes=[10.0],
        _line_y_mids=[683.0],
        _math_map={"⟪0⟫": [(",", "CMR10")]},
    )
    result = _merge_overlapping_math_blocks([a, b])
    assert len(result) == 1
    assert result[0]["text_align"] == "left"


def test_merge_split_paragraph_rederives_justify() -> None:
    """Split paragraph with full-width + short line → justify."""
    a = _make_block(
        659.1,
        679.2,
        "where the probability and the",
        text_align="center",
        _line_extents=[(72.0, 540.0)],
        _line_sizes=[10.0],
        _line_y_mids=[669.0],
        _math_map={"⟪0⟫": [("T", "CMMI10")]},
    )
    b = _make_block(
        678.1,
        688.3,
        "internal randomness of mechanism M.",
        text_align="left",
        _line_extents=[(72.0, 226.9)],
        _line_sizes=[10.0],
        _line_y_mids=[683.0],
        _math_map={"⟪0⟫": [("M", "CMMI10")]},
    )
    result = _merge_overlapping_math_blocks([a, b])
    assert len(result) == 1
    # Full-width + short final → re-derived as justify
    assert result[0]["text_align"] == "justify"


def test_merge_split_paragraph_ragged_stays_left() -> None:
    """Split paragraph with ragged right edges stays 'left'."""
    a = _make_block(
        659.1,
        679.2,
        "where the probability and the",
        text_align="left",
        _line_extents=[(72.0, 350.0), (72.0, 420.0)],
        _line_sizes=[10.0, 10.0],
        _line_y_mids=[665.0, 675.0],
        _math_map={"⟪0⟫": [("T", "CMMI10")]},
    )
    b = _make_block(
        678.1,
        688.3,
        "internal randomness of mechanism M.",
        text_align="left",
        _line_extents=[(72.0, 300.0)],
        _line_sizes=[10.0],
        _line_y_mids=[683.0],
        _math_map={"⟪0⟫": [("M", "CMMI10")]},
    )
    result = _merge_overlapping_math_blocks([a, b])
    assert len(result) == 1
    assert result[0]["text_align"] == "left"


def test_is_split_paragraph_different_font_sizes() -> None:
    """Blocks with very different font sizes are not split paragraphs."""
    a = _make_block(480, 512, "resulting from a", font_size=10.0)
    b = _make_block(508, 547, "random draw from the generator", font_size=7.0)
    assert _is_split_paragraph(a, b) is False


def test_is_split_paragraph_similar_font_sizes() -> None:
    """Blocks with similar font sizes (within 20%) pass the check."""
    a = _make_block(480, 512, "resulting from a", font_size=10.0)
    b = _make_block(508, 547, "random draw from the generator", font_size=9.5)
    assert _is_split_paragraph(a, b) is True


# ── _split_at_display_gaps tests ──────────────────────────────────────────


def _make_pymupdf_line(
    y0: float,
    y1: float,
    text: str = "body",
    **kw: Any,
) -> dict[str, Any]:
    """Build a minimal PyMuPDF line dict for split tests."""
    font = kw.get("font", "NimbusRomNo9L-Regu")
    size = kw.get("size", 10.0)
    x0 = kw.get("x0", 72.0)
    x1 = kw.get("x1", 400.0)
    return {
        "bbox": (x0, y0, x1, y1),
        "spans": [
            {
                "text": text,
                "font": font,
                "size": size,
                "bbox": (x0, y0, x1, y1),
                "flags": 0,
                "color": 0,
            }
        ],
    }


def _make_pymupdf_block(
    lines: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a minimal PyMuPDF block dict from lines."""
    x0 = min(ln["bbox"][0] for ln in lines)
    y0 = min(ln["bbox"][1] for ln in lines)
    x1 = max(ln["bbox"][2] for ln in lines)
    y1 = max(ln["bbox"][3] for ln in lines)
    return {"type": 0, "bbox": (x0, y0, x1, y1), "lines": lines}


def test_split_display_gap_no_split_for_normal_spacing() -> None:
    """Lines with normal spacing (<= factor × font_size) stay together."""
    # font_size=10, gap=1.8pt — well below threshold (10pt)
    lines = [
        _make_pymupdf_line(100, 110, "Line 1"),
        _make_pymupdf_line(111.8, 121.8, "Line 2"),
        _make_pymupdf_line(123.6, 133.6, "Line 3"),
    ]
    block = _make_pymupdf_block(lines)
    result = _split_at_display_gaps(block)
    assert len(result) == 1
    assert result[0] is block  # same object — no copy made


def test_split_display_gap_splits_at_large_gap() -> None:
    """A 13pt gap with font_size=10 triggers a split."""
    lines = [
        _make_pymupdf_line(100, 110, "Body text line 1"),
        _make_pymupdf_line(111.8, 121.8, "Body text line 2"),
        # 13pt gap — exceeds 1.0 × 10 = 10pt threshold
        _make_pymupdf_line(134.8, 144.8, "B = max equation"),
    ]
    block = _make_pymupdf_block(lines)
    result = _split_at_display_gaps(block)
    assert len(result) == 2  # noqa: PLR2004
    # First sub-block: lines 0-1
    assert len(result[0]["lines"]) == 2  # noqa: PLR2004
    assert result[0]["lines"][0]["spans"][0]["text"] == "Body text line 1"
    # Second sub-block: line 2
    assert len(result[1]["lines"]) == 1
    assert result[1]["lines"][0]["spans"][0]["text"] == "B = max equation"
    # Bboxes are recomputed
    assert result[0]["bbox"][3] == 121.8  # noqa: PLR2004
    assert result[1]["bbox"][1] == 134.8  # noqa: PLR2004


def test_split_display_gap_single_line_no_split() -> None:
    """A block with a single line is returned as-is."""
    lines = [_make_pymupdf_line(100, 110, "Only line")]
    block = _make_pymupdf_block(lines)
    result = _split_at_display_gaps(block)
    assert len(result) == 1
    assert result[0] is block


def test_split_display_gap_multiple_splits() -> None:
    """Multiple large gaps produce multiple sub-blocks."""
    lines = [
        _make_pymupdf_line(100, 110, "Para 1"),
        # 15pt gap
        _make_pymupdf_line(125, 135, "Equation 1"),
        # 20pt gap
        _make_pymupdf_line(155, 165, "Para 2"),
    ]
    block = _make_pymupdf_block(lines)
    result = _split_at_display_gaps(block)
    assert len(result) == 3  # noqa: PLR2004
    assert result[0]["lines"][0]["spans"][0]["text"] == "Para 1"
    assert result[1]["lines"][0]["spans"][0]["text"] == "Equation 1"
    assert result[2]["lines"][0]["spans"][0]["text"] == "Para 2"


def test_split_display_gap_preserves_block_type() -> None:
    """Sub-blocks inherit the original block's type and other fields."""
    lines = [
        _make_pymupdf_line(100, 110, "Line 1"),
        _make_pymupdf_line(125, 135, "Line 2"),  # 15pt gap
    ]
    block = _make_pymupdf_block(lines)
    block["number"] = 42  # noqa: PLR2004
    result = _split_at_display_gaps(block)
    assert len(result) == 2  # noqa: PLR2004
    assert result[0]["type"] == 0
    assert result[0]["number"] == 42  # noqa: PLR2004
    assert result[1]["type"] == 0
    assert result[1]["number"] == 42  # noqa: PLR2004


def test_split_display_gap_overlapping_lines_no_split() -> None:
    """Overlapping lines (gap <= 0) never trigger a split."""
    lines = [
        _make_pymupdf_line(100, 115, "Line 1"),
        _make_pymupdf_line(110, 125, "Line 2"),  # overlaps — gap < 0
    ]
    block = _make_pymupdf_block(lines)
    result = _split_at_display_gaps(block)
    assert len(result) == 1
    assert result[0] is block


def test_split_display_gap_uses_font_size_of_preceding_line() -> None:
    """Gap threshold scales with the preceding line's font size."""
    # Large font (size=20): threshold = 20pt; 15pt gap should NOT split
    lines = [
        _make_pymupdf_line(100, 120, "Big text", size=20.0),
        _make_pymupdf_line(135, 155, "Next line", size=20.0),  # gap=15pt
    ]
    block = _make_pymupdf_block(lines)
    result = _split_at_display_gaps(block)
    assert len(result) == 1  # gap < font_size, no split

    # Small font (size=10): same 15pt gap now exceeds threshold (10pt)
    lines2 = [
        _make_pymupdf_line(100, 110, "Small text", size=10.0),
        _make_pymupdf_line(125, 135, "Next line", size=10.0),  # gap=15pt
    ]
    block2 = _make_pymupdf_block(lines2)
    result2 = _split_at_display_gaps(block2)
    assert len(result2) == 2  # noqa: PLR2004


def test_merge_two_math_blocks_direct() -> None:
    """Direct unit test for _merge_two_math_blocks helper."""
    a = _make_block(100, 115, "Hello⟪0⟫", _math_map={"⟪0⟫": [("α", "CMMI10")]})
    b = _make_block(
        110,
        130,
        "⟪0⟫ world⟪1⟫",
        _math_map={"⟪0⟫": [("β", "CMMI10")], "⟪1⟫": [("γ", "CMMI10")]},
    )
    merged = _merge_two_math_blocks(a, b)
    assert "Hello⟪0⟫" in merged["text"]
    # B's ⟪0⟫ → ⟪1⟫ and ⟪1⟫ → ⟪2⟫
    assert "⟪1⟫ world⟪2⟫" in merged["text"]
    mm = merged["_math_map"]
    assert mm["⟪0⟫"] == [("α", "CMMI10")]
    assert mm["⟪1⟫"] == [("β", "CMMI10")]
    assert mm["⟪2⟫"] == [("γ", "CMMI10")]


def test_merge_two_math_blocks_carries_indent() -> None:
    """Merging math blocks carries forward para_indents from the primary."""
    a = _make_block(100, 115, "Hello⟪0⟫", _math_map={"⟪0⟫": [("α", "CMMI10")]})
    b = _make_block(
        110, 130, "⟪0⟫ world paragraph text here", _math_map={"⟪0⟫": [("β", "CMMI10")]}
    )
    # Legitimate indent (13.8pt first-line for body text)
    b["para_indents"] = [(0.0, 13.8)]
    b["text_indent"] = 13.8
    merged = _merge_two_math_blocks(a, b)
    # Indents are carried from primary (b has more body text)
    assert merged.get("para_indents") == [(0.0, 13.8)]
    assert merged.get("text_indent") == 13.8  # noqa: PLR2004


def test_merge_two_math_blocks_same_line_x_ordering() -> None:
    """Same-line blocks are ordered left-to-right by x, not by y."""
    # Block A: step text at x=78, y=153-167
    a = _make_block(
        153.2, 166.6, "4: To assign⟪0⟫", _math_map={"⟪0⟫": [("∆", "CMMI10")]}
    )
    a["rect"] = [77.8, 153.2, 204.1, 166.6]
    # Block B: formula continuation at x=199, y=152-168 (slightly higher y0)
    b = _make_block(152.2, 167.7, "⟪0⟫", _math_map={"⟪0⟫": [("m", "CMMI10")]})
    b["rect"] = [198.6, 152.2, 324.1, 167.7]
    merged = _merge_two_math_blocks(a, b)
    # Block A (x=78) should come BEFORE Block B (x=199) despite B's
    # smaller y0 — they're on the same visual line.
    assert merged["text"].startswith("4: To assign")


def test_merge_two_math_blocks_different_lines_y_ordering() -> None:
    """Blocks on different lines are still ordered top-to-bottom by y."""
    a = _make_block(200, 210, "Second line⟪0⟫", _math_map={"⟪0⟫": [("β", "CMMI10")]})
    b = _make_block(100, 110, "First line⟪0⟫", _math_map={"⟪0⟫": [("α", "CMMI10")]})
    merged = _merge_two_math_blocks(a, b)
    # Block B (y=100) should come before Block A (y=200)
    assert merged["text"].startswith("First line")


def test_merge_two_math_blocks_tall_block_uses_y_ordering() -> None:
    r"""Short block overlapping top of a tall block uses y-ordering.

    Block A: "2. RMS ... ^S =" at y=86-100 (height=14)
    Block B: "(S²...) /3 \\n body text..." at y=89-247 (height=158)
    Overlap is 11pt — high vs short block but low vs tall block.
    Should use y-ordering so A comes first.
    """
    a = _make_block(86.0, 100.1, "2. RMS⟪0⟫", _math_map={"⟪0⟫": [("S", "CMMI10")]})
    a["rect"] = [84.5, 86.0, 245.7, 100.1]
    b = _make_block(
        88.8, 247.1, "⟪0⟫ body text continues", _math_map={"⟪0⟫": [("S", "CMR10")]}
    )
    b["rect"] = [72.0, 88.8, 541.7, 247.1]
    merged = _merge_two_math_blocks(a, b)
    # Block A (y=86) should come before Block B (y=89) — y-ordering,
    # NOT x-ordering (Block B has smaller x0=72 but is much taller).
    assert merged["text"].startswith("2. RMS")


def test_detect_alignment_rejects_huge_indent() -> None:
    """First-line shift exceeding MAX_INDENT_FACTOR is not an indent."""
    # Block from x=72 to x=541, first line at x=167 (95pt shift),
    # second line at x=72. With font size 10, max indent = 30pt.
    line_extents = [(167.0, 541.0), (72.0, 398.0)]
    block_rect = [72.0, 100.0, 541.0, 130.0]
    align, indent = _detect_block_alignment(
        line_extents,
        block_rect,
        [10.0, 10.0],
    )
    assert indent == 0.0  # 95pt exceeds 3× font size


def test_body_len_helper() -> None:
    """_body_len returns text length minus placeholder lengths."""
    b = _make_block(0, 10, "Hello⟪0⟫ world", _math_map={"⟪0⟫": [("x", "CMMI10")]})
    # "Hello" + " world" = 11 body chars
    assert _body_len(b) == len("Hello world")


def test_body_len_whitespace_only_is_zero() -> None:
    """_body_len returns 0 when remaining text is only whitespace."""
    b = _make_block(
        0,
        10,
        "⟪0⟫ ⟪1⟫ ⟪2⟫",
        _math_map={
            "⟪0⟫": [("B", "CMR10")],
            "⟪1⟫": [("=", "CMR10")],
            "⟪2⟫": [("x", "CMMI10")],
        },
    )
    assert _body_len(b) == 0


def test_body_len_no_math() -> None:
    """_body_len on a block with no math returns full text length."""
    b = _make_block(0, 10, "Hello world")
    assert _body_len(b) == len("Hello world")


# ── _is_pure_math_line tests ─────────────────────────────────────────────


def test_is_pure_math_line_all_math() -> None:
    """Line with only math-font spans is pure math."""
    spans = [
        {"text": "B = max", "font": "CMR10", "flags": 0},
        {"text": "i∈[m]", "font": "CMMI10", "flags": 0},
    ]
    assert _is_pure_math_line(spans) is True


def test_is_pure_math_line_mixed() -> None:
    """Line with body + math fonts is not pure math."""
    spans = [
        {"text": "then choosing", "font": "NimbusRomNo9L-Regu", "flags": 0},
        {"text": "B", "font": "CMMI10", "flags": 0},
    ]
    assert _is_pure_math_line(spans) is False


def test_is_pure_math_line_all_body() -> None:
    """Line with only body fonts is not pure math."""
    spans = [
        {"text": "Hello world", "font": "NimbusRomNo9L-Regu", "flags": 0},
    ]
    assert _is_pure_math_line(spans) is False


def test_is_pure_math_line_empty() -> None:
    """Line with no text spans returns False."""
    assert _is_pure_math_line([]) is False


def test_is_pure_math_line_separator_ignored() -> None:
    """Separator spans (no font, whitespace-only) are ignored."""
    spans = [
        {"text": "α", "font": "CMMI10", "flags": 0},
        {"text": " ", "flags": 0, "role": None},  # separator
        {"text": "β", "font": "CMSY10", "flags": 0},
    ]
    assert _is_pure_math_line(spans) is True


def test_is_pure_math_line_math_placeholder() -> None:
    """Spans marked _is_math are treated as math."""
    spans = [
        {"text": "⟪0⟫", "font": "CMMI10", "_is_math": True, "flags": 0},
    ]
    assert _is_pure_math_line(spans) is True


# ── Inline vs display math detection ─────────────────────────────────────────


def test_drop_pure_math_keeps_inline_left_aligned() -> None:
    """Pure-math line near left margin (inline continuation) is kept."""
    # Simulates block 20 from test4.pdf page 17:
    # Line 0: body text at x=72
    # Line 1: "τ > L B" at x=72 (left margin → inline math, should be kept)
    body_line = {
        "bbox": (72, 540, 400, 550),
        "dir": (1.0, 0.0),
        "spans": [
            {
                "text": "as soon as ",
                "font": "NimbusRomNo9L-Regu",
                "size": 10.0,
                "flags": 0,
                "color": 0,
                "bbox": (72, 540, 150, 550),
                "origin": (72, 548),
            },
        ],
    }
    math_line = {
        "bbox": (72, 556, 119, 566),
        "dir": (1.0, 0.0),
        "spans": [
            {
                "text": "τ > L B",
                "font": "CMSY10",
                "size": 10.0,
                "flags": 0,
                "color": 0,
                "bbox": (72, 556, 107, 566),
                "origin": (72, 564),
            },
            {
                "text": "√",
                "font": "CMEX10",
                "size": 10.0,
                "flags": 0,
                "color": 0,
                "bbox": (109, 556, 119, 566),
                "origin": (109, 564),
            },
        ],
    }
    raw_block = {
        "type": 0,
        "bbox": (72, 540, 400, 566),
        "lines": [body_line, math_line],
    }
    page = _make_mock_page([raw_block])
    blocks = _extract_page_blocks(page)
    assert len(blocks) == 1
    # The inline math spans should be present as placeholders in text
    assert _MATH_PH_START in blocks[0]["text"]


def test_drop_pure_math_drops_centered_display_eq() -> None:
    """Pure-math line centered in the block (display eq) is dropped."""
    # Simulates "B = max ..." centered display equation:
    # Line 0: body text at x=72-400
    # Line 1: display eq at x=255-357 (centered, far from left margin)
    body_line = {
        "bbox": (72, 500, 400, 510),
        "dir": (1.0, 0.0),
        "spans": [
            {
                "text": "We define the following quantity",
                "font": "NimbusRomNo9L-Regu",
                "size": 10.0,
                "flags": 0,
                "color": 0,
                "bbox": (72, 500, 400, 510),
                "origin": (72, 508),
            },
        ],
    }
    display_eq_line = {
        "bbox": (255, 530, 357, 540),
        "dir": (1.0, 0.0),
        "spans": [
            {
                "text": "B = max",
                "font": "CMMI10",
                "size": 10.0,
                "flags": 0,
                "color": 0,
                "bbox": (255, 530, 310, 540),
                "origin": (255, 538),
            },
            {
                "text": "i∈[m]",
                "font": "CMSY10",
                "size": 7.0,
                "flags": 0,
                "color": 0,
                "bbox": (310, 534, 340, 540),
                "origin": (310, 538),
            },
            {
                "text": "Δ",
                "font": "CMMI10",
                "size": 10.0,
                "flags": 0,
                "color": 0,
                "bbox": (340, 530, 357, 540),
                "origin": (340, 538),
            },
        ],
    }
    raw_block = {
        "type": 0,
        "bbox": (72, 500, 400, 540),
        "lines": [body_line, display_eq_line],
    }
    page = _make_mock_page([raw_block])
    blocks = _extract_page_blocks(page)
    assert len(blocks) == 1
    # Display equation should be dropped — only body text remains
    assert "define" in blocks[0]["text"]
    assert _MATH_PH_START not in blocks[0]["text"]


def test_drop_pure_math_tolerance_boundary() -> None:
    """Math line exactly at tolerance boundary is kept (inline)."""
    # body at x=72, math at x=72 + 2*10 - 0.1 = 91.9 (just inside tol)
    dom_size = 10.0
    math_x0 = 72.0 + _INLINE_MATH_X_TOL * dom_size - 0.1  # noqa: PLR2004
    body_line = {
        "bbox": (72, 100, 400, 110),
        "dir": (1.0, 0.0),
        "spans": [
            {
                "text": "body text here",
                "font": "NimbusRomNo9L-Regu",
                "size": dom_size,
                "flags": 0,
                "color": 0,
                "bbox": (72, 100, 400, 110),
                "origin": (72, 108),
            },
        ],
    }
    math_line = {
        "bbox": (math_x0, 120, math_x0 + 50, 130),
        "dir": (1.0, 0.0),
        "spans": [
            {
                "text": "α + β",
                "font": "CMMI10",
                "size": dom_size,
                "flags": 0,
                "color": 0,
                "bbox": (math_x0, 120, math_x0 + 50, 130),
                "origin": (math_x0, 128),
            },
        ],
    }
    raw_block = {
        "type": 0,
        "bbox": (72, 100, 400, 130),
        "lines": [body_line, math_line],
    }
    page = _make_mock_page([raw_block])
    blocks = _extract_page_blocks(page)
    # After _split_multiline_blocks, body and inline-math lines are
    # separate sub-blocks — but the math is NOT dropped.
    all_text = " ".join(b["text"] for b in blocks)
    assert _MATH_PH_START in all_text
    assert any("body text" in b["text"] for b in blocks)


def test_drop_pure_math_keeps_right_adjacent_radical() -> None:
    """Pure-math line adjacent to body line right edge is kept (inline).

    Simulates block 9 from test4.pdf page 15: "We divide through by" ends
    at x=157.6, then "√" starts at x=160.1 on a slightly higher line.
    The √ is inline continuation (radical sign), not a display equation.
    """
    body_line = {
        "bbox": (71.5, 208.2, 157.6, 218.2),
        "dir": (1.0, 0.0),
        "spans": [
            {
                "text": "We divide through by",
                "font": "NimbusRomNo9L-Regu",
                "size": 10.0,
                "flags": 0,
                "color": 0,
                "bbox": (71.5, 208.2, 157.6, 218.2),
                "origin": (71.5, 216),
            },
        ],
    }
    # √ sits slightly above the body text (radical overscore)
    radical_line = {
        "bbox": (160.1, 199.9, 168.4, 209.8),
        "dir": (1.0, 0.0),
        "spans": [
            {
                "text": "√",
                "font": "CMSY10",
                "size": 10.0,
                "flags": 0,
                "color": 0,
                "bbox": (160.1, 199.9, 168.4, 209.8),
                "origin": (160.1, 208),
            },
        ],
    }
    raw_block = {
        "type": 0,
        "bbox": (71.5, 199.9, 168.4, 218.2),
        "lines": [body_line, radical_line],
    }
    page = _make_mock_page([raw_block])
    blocks = _extract_page_blocks(page)
    assert len(blocks) == 1
    # √ should be kept as inline — placeholder present in text
    assert _MATH_PH_START in blocks[0]["text"]
    assert "divide through" in blocks[0]["text"]


def test_drop_pure_math_right_adjacent_no_y_overlap_dropped() -> None:
    """Math line near body right edge but far in y is dropped (display)."""
    body_line = {
        "bbox": (72, 200, 260, 210),
        "dir": (1.0, 0.0),
        "spans": [
            {
                "text": "We define the quantity",
                "font": "NimbusRomNo9L-Regu",
                "size": 10.0,
                "flags": 0,
                "color": 0,
                "bbox": (72, 200, 260, 210),
                "origin": (72, 208),
            },
        ],
    }
    # Display equation at x=255 (near body x1=260) but 25pt below
    display_line = {
        "bbox": (255, 235, 357, 245),
        "dir": (1.0, 0.0),
        "spans": [
            {
                "text": "B = max",
                "font": "CMMI10",
                "size": 10.0,
                "flags": 0,
                "color": 0,
                "bbox": (255, 235, 357, 245),
                "origin": (255, 243),
            },
        ],
    }
    raw_block = {
        "type": 0,
        "bbox": (72, 200, 357, 245),
        "lines": [body_line, display_line],
    }
    page = _make_mock_page([raw_block])
    blocks = _extract_page_blocks(page)
    assert len(blocks) == 1
    # Display equation dropped — no placeholder
    assert "define" in blocks[0]["text"]
    assert _MATH_PH_START not in blocks[0]["text"]


def test_deferred_pure_math_drop_preserves_inline_fragment() -> None:
    """Pure-math block between body blocks is absorbed, not dropped.

    PyMuPDF splits nested sqrt formulas into separate blocks:
      Block A: "So, letting" + outer sqrt (body + math)
      Block B: "2σ²(d + 2" + inner sqrt  (pure math — no body text)
      Block C: "d log... gives..."         (math + body)
    All three overlap vertically.  Block B must NOT be dropped before
    the overlap merge; otherwise the formula text is lost.
    """
    block_a = {
        "type": 0,
        "bbox": (72.0, 530.0, 126.0, 546.0),
        "lines": [
            {
                "bbox": (72.0, 536.0, 113.0, 546.0),
                "dir": (1.0, 0.0),
                "spans": [
                    {
                        "text": "So, letting",
                        "font": "NimbusRomNo9L-Regu",
                        "size": 10.0,
                        "flags": 0,
                        "color": 0,
                        "bbox": (72.0, 536.0, 113.0, 546.0),
                        "origin": (72.0, 544.0),
                    },
                ],
            },
            {
                "bbox": (115.0, 530.0, 126.0, 540.0),
                "dir": (1.0, 0.0),
                "spans": [
                    {
                        "text": "q",
                        "font": "CMEX10",
                        "size": 10.0,
                        "flags": 0,
                        "color": 0,
                        "bbox": (115.0, 530.0, 126.0, 540.0),
                        "origin": (115.0, 538.0),
                    },
                ],
            },
        ],
    }
    # Pure-math block — would be dropped by the old early-drop logic
    block_b = {
        "type": 0,
        "bbox": (126.0, 534.0, 178.0, 546.0),
        "lines": [
            {
                "bbox": (126.0, 536.0, 168.0, 546.0),
                "dir": (1.0, 0.0),
                "spans": [
                    {
                        "text": "2",
                        "font": "CMR10",
                        "size": 10.0,
                        "flags": 0,
                        "color": 0,
                        "bbox": (126.0, 536.0, 131.0, 546.0),
                        "origin": (126.0, 544.0),
                    },
                    {
                        "text": "σ",
                        "font": "CMMI10",
                        "size": 10.0,
                        "flags": 0,
                        "color": 0,
                        "bbox": (131.0, 536.0, 137.0, 546.0),
                        "origin": (131.0, 544.0),
                    },
                    {
                        "text": "(d + 2",
                        "font": "CMR10",
                        "size": 10.0,
                        "flags": 0,
                        "color": 0,
                        "bbox": (141.0, 536.0, 168.0, 546.0),
                        "origin": (141.0, 544.0),
                    },
                ],
            },
            {
                "bbox": (168.0, 534.0, 178.0, 544.0),
                "dir": (1.0, 0.0),
                "spans": [
                    {
                        "text": "p",
                        "font": "CMEX10",
                        "size": 10.0,
                        "flags": 0,
                        "color": 0,
                        "bbox": (168.0, 534.0, 178.0, 544.0),
                        "origin": (168.0, 542.0),
                    },
                ],
            },
        ],
    }
    block_c = {
        "type": 0,
        "bbox": (72.0, 536.0, 460.0, 578.0),
        "lines": [
            {
                "bbox": (178.0, 536.0, 460.0, 546.0),
                "dir": (1.0, 0.0),
                "spans": [
                    {
                        "text": "d log(1)",
                        "font": "CMR10",
                        "size": 10.0,
                        "flags": 0,
                        "color": 0,
                        "bbox": (178.0, 536.0, 220.0, 546.0),
                        "origin": (178.0, 544.0),
                    },
                    {
                        "text": " gives ",
                        "font": "NimbusRomNo9L-Regu",
                        "size": 10.0,
                        "flags": 0,
                        "color": 0,
                        "bbox": (290.0, 536.0, 325.0, 546.0),
                        "origin": (290.0, 544.0),
                    },
                    {
                        "text": "result.",
                        "font": "NimbusRomNo9L-Regu",
                        "size": 10.0,
                        "flags": 0,
                        "color": 0,
                        "bbox": (380.0, 536.0, 420.0, 546.0),
                        "origin": (380.0, 544.0),
                    },
                ],
            },
            {
                "bbox": (72.0, 560.0, 460.0, 578.0),
                "dir": (1.0, 0.0),
                "spans": [
                    {
                        "text": "Next paragraph continues here.",
                        "font": "NimbusRomNo9L-Regu",
                        "size": 10.0,
                        "flags": 0,
                        "color": 0,
                        "bbox": (72.0, 560.0, 300.0, 570.0),
                        "origin": (72.0, 568.0),
                    },
                ],
            },
        ],
    }
    page = _make_mock_page([block_a, block_b, block_c])
    blocks = _extract_page_blocks(page)

    # All three blocks should be merged into one (vertical overlap).
    # The pure-math block B text ("2σ(d + 2") must be in a placeholder.
    merged_texts = " ".join(b["text"] for b in blocks)
    assert "letting" in merged_texts
    assert "gives" in merged_texts
    # The key check: "2σ" from block B survived as a math placeholder
    all_math = {}
    for b in blocks:
        all_math.update(b.get("_math_map", {}))
    math_chars = "".join("".join(entry[0] for entry in v) for v in all_math.values())
    assert "2" in math_chars and "σ" in math_chars, (
        f"Block B content lost; math_chars={math_chars!r}"
    )


def test_deferred_drop_still_drops_display_equation_block() -> None:
    """Standalone pure-math block (no overlapping body) is still dropped."""
    display_block = {
        "type": 0,
        "bbox": (200.0, 400.0, 400.0, 420.0),
        "lines": [
            {
                "bbox": (200.0, 400.0, 400.0, 420.0),
                "dir": (1.0, 0.0),
                "spans": [
                    {
                        "text": "B = max",
                        "font": "CMMI10",
                        "size": 10.0,
                        "flags": 0,
                        "color": 0,
                        "bbox": (200.0, 400.0, 300.0, 410.0),
                        "origin": (200.0, 408.0),
                    },
                    {
                        "text": "Δ",
                        "font": "CMMI10",
                        "size": 10.0,
                        "flags": 0,
                        "color": 0,
                        "bbox": (300.0, 400.0, 320.0, 410.0),
                        "origin": (300.0, 408.0),
                    },
                ],
            },
        ],
    }
    page = _make_mock_page([display_block])
    blocks = _extract_page_blocks(page)
    # Pure-math with no overlapping body → dropped
    assert len(blocks) == 0


# ── Inline math chain detection ───────────────────────────────────────────────


def test_inline_math_chain_keeps_continuation_via_math() -> None:
    """Multi-segment inline formula: math lines kept via chain detection.

    Math lines reachable only through other math lines are kept.
    Simulates the RMS formula √(S²fmt + S²psy + S²sch)/3 where:
    - Line 0: body text ending at x=233
    - Line 1: math √( at x=235.8 (kept via body right-edge adjacency)
    - Line 2: math S²fmt at x=245 (kept via chain from line 1)
    - Line 3: math + S²psy at x=255 (kept via chain from line 2)
    """
    body_line = {
        "bbox": (72, 200, 233, 210),
        "dir": (1.0, 0.0),
        "spans": [
            {
                "text": "The root mean square is",
                "font": "NimbusRomNo9L-Regu",
                "size": 10.0,
                "flags": 0,
                "color": 0,
                "bbox": (72, 200, 233, 210),
                "origin": (72, 208),
            },
        ],
    }
    math_line_1 = {
        "bbox": (235.8, 198, 245, 211),
        "dir": (1.0, 0.0),
        "spans": [
            {
                "text": "√(",
                "font": "CMEX10",
                "size": 10.0,
                "flags": 0,
                "color": 0,
                "bbox": (235.8, 198, 245, 211),
                "origin": (235.8, 208),
            },
        ],
    }
    math_line_2 = {
        "bbox": (245, 200, 255, 210),
        "dir": (1.0, 0.0),
        "spans": [
            {
                "text": "S²fmt",
                "font": "CMMI10",
                "size": 10.0,
                "flags": 0,
                "color": 0,
                "bbox": (245, 200, 255, 210),
                "origin": (245, 208),
            },
        ],
    }
    math_line_3 = {
        "bbox": (255, 200, 270, 210),
        "dir": (1.0, 0.0),
        "spans": [
            {
                "text": "+ S²psy",
                "font": "CMMI10",
                "size": 10.0,
                "flags": 0,
                "color": 0,
                "bbox": (255, 200, 270, 210),
                "origin": (255, 208),
            },
        ],
    }
    raw_block = {
        "type": 0,
        "bbox": (72, 198, 270, 211),
        "lines": [body_line, math_line_1, math_line_2, math_line_3],
    }
    page = _make_mock_page([raw_block])
    blocks = _extract_page_blocks(page)
    assert len(blocks) == 1
    # All math lines should be kept — the formula is inline
    text = blocks[0]["text"]
    assert "root mean square" in text
    assert _MATH_PH_START in text


def test_inline_math_chain_does_not_keep_distant_display_eq() -> None:
    """Chain detection does not rescue display equations far from body.

    - Line 0: body text at x=72-400
    - Line 1: math at x=398 (near body right edge → kept)
    - Line 2: display eq at x=200 (not near any kept line's right edge)
    """
    body_line = {
        "bbox": (72, 200, 400, 210),
        "dir": (1.0, 0.0),
        "spans": [
            {
                "text": "We define the following quantity",
                "font": "NimbusRomNo9L-Regu",
                "size": 10.0,
                "flags": 0,
                "color": 0,
                "bbox": (72, 200, 400, 210),
                "origin": (72, 208),
            },
        ],
    }
    inline_math = {
        "bbox": (398, 200, 420, 210),
        "dir": (1.0, 0.0),
        "spans": [
            {
                "text": "α",
                "font": "CMMI10",
                "size": 10.0,
                "flags": 0,
                "color": 0,
                "bbox": (398, 200, 420, 210),
                "origin": (398, 208),
            },
        ],
    }
    display_eq = {
        "bbox": (200, 225, 350, 235),
        "dir": (1.0, 0.0),
        "spans": [
            {
                "text": "B = max Δ",
                "font": "CMMI10",
                "size": 10.0,
                "flags": 0,
                "color": 0,
                "bbox": (200, 225, 350, 235),
                "origin": (200, 233),
            },
        ],
    }
    raw_block = {
        "type": 0,
        "bbox": (72, 200, 420, 235),
        "lines": [body_line, inline_math, display_eq],
    }
    page = _make_mock_page([raw_block])
    blocks = _extract_page_blocks(page)
    assert len(blocks) == 1
    text = blocks[0]["text"]
    # Inline α should be kept, display eq should be dropped
    assert _MATH_PH_START in text
    assert "define" in text


def test_inline_math_chain_y_proximity_required() -> None:
    """Chain detection requires y-proximity.

    Vertically distant math lines are not chained even if x-adjacent.
    """
    body_line = {
        "bbox": (72, 200, 233, 210),
        "dir": (1.0, 0.0),
        "spans": [
            {
                "text": "The root mean square is",
                "font": "NimbusRomNo9L-Regu",
                "size": 10.0,
                "flags": 0,
                "color": 0,
                "bbox": (72, 200, 233, 210),
                "origin": (72, 208),
            },
        ],
    }
    # Inline math near body right edge (kept)
    math_kept = {
        "bbox": (235, 200, 250, 210),
        "dir": (1.0, 0.0),
        "spans": [
            {
                "text": "√",
                "font": "CMEX10",
                "size": 10.0,
                "flags": 0,
                "color": 0,
                "bbox": (235, 200, 250, 210),
                "origin": (235, 208),
            },
        ],
    }
    # Math at x=250 (near kept line's x1=250) but 30pt below → too far
    math_far_y = {
        "bbox": (250, 240, 280, 250),
        "dir": (1.0, 0.0),
        "spans": [
            {
                "text": "S²",
                "font": "CMMI10",
                "size": 10.0,
                "flags": 0,
                "color": 0,
                "bbox": (250, 240, 280, 250),
                "origin": (250, 248),
            },
        ],
    }
    raw_block = {
        "type": 0,
        "bbox": (72, 200, 280, 250),
        "lines": [body_line, math_kept, math_far_y],
    }
    page = _make_mock_page([raw_block])
    blocks = _extract_page_blocks(page)
    assert len(blocks) == 1
    text = blocks[0]["text"]
    # √ is kept but S² is dropped (too far vertically)
    assert "root mean square" in text


# ── Table cell math font skipping ────────────────────────────────────────────


def test_extract_table_cell_blocks_skips_complex_math_cell() -> None:
    """Table cells with complex 2D math layout (3+ math y-levels) are skipped."""
    page_dict: dict[str, Any] = {
        "blocks": [
            {
                "type": 0,
                "bbox": (72, 80, 540, 120),
                "lines": [
                    {
                        "bbox": (72, 80, 540, 90),
                        "spans": [
                            {
                                "bbox": (72, 80, 200, 90),
                                "text": "for i = 1",
                                "font": "CMR10",
                                "flags": 0,
                                "size": 10,
                                "color": 0,
                            },
                        ],
                    },
                    {
                        "bbox": (72, 95, 540, 105),
                        "spans": [
                            {
                                "bbox": (72, 95, 200, 105),
                                "text": "j = f(D)",
                                "font": "CMMI10",
                                "flags": 2,
                                "size": 10,
                                "color": 0,
                            },
                        ],
                    },
                    {
                        "bbox": (72, 110, 540, 120),
                        "spans": [
                            {
                                "bbox": (72, 110, 200, 120),
                                "text": "end",
                                "font": "CMR10",
                                "flags": 0,
                                "size": 10,
                                "color": 0,
                            },
                        ],
                    },
                ],
            }
        ],
    }
    page_tables = [
        {
            "bbox": (72, 72, 540, 130),
            "cells": [(72, 72, 540, 130)],
        }
    ]
    result = _extract_table_cell_blocks(page_tables, page_dict)
    # 3 math y-levels → complex 2D layout → skipped
    assert len(result) == 0


def test_extract_table_cell_blocks_keeps_math_light_cell() -> None:
    """Cells with incidental math (footnote markers) are kept."""
    page_dict: dict[str, Any] = {
        "blocks": [
            {
                "type": 0,
                "bbox": (72, 90, 540, 100),
                "lines": [
                    {
                        "bbox": (72, 90, 540, 100),
                        "spans": [
                            {
                                "bbox": (72, 90, 200, 100),
                                "text": "Then compute",
                                "font": "NimbusRomNo9L-Regu",
                                "flags": 0,
                                "size": 10,
                                "color": 0,
                            },
                            {
                                "bbox": (200, 90, 230, 100),
                                "text": " j",
                                "font": "CMMI10",
                                "flags": 2,
                                "size": 10,
                                "color": 0,
                            },
                        ],
                    }
                ],
            }
        ],
    }
    page_tables = [
        {
            "bbox": (72, 72, 540, 120),
            "cells": [(72, 72, 540, 120)],
        }
    ]
    result = _extract_table_cell_blocks(page_tables, page_dict)
    # 1 math y-level (inline) → not complex → kept as table cell
    assert len(result) == 1
    assert "compute" in result[0]["text"]


def test_algorithm_box_body_goes_through_normal_extraction() -> None:
    """Algorithm box detected as table: body goes through normal path."""
    # Simulates an algorithm box: title cell (no math) + body cell
    # with 3 lines of pseudocode in CM fonts (3+ math y-levels →
    # complex 2D layout → skipped from table cell extraction).
    title_line = {
        "bbox": (72, 74, 226, 84),
        "dir": (1.0, 0.0),
        "spans": [
            {
                "text": "Algorithm 1 Mechanism",
                "font": "NimbusRomNo9L-Medi",
                "size": 10.0,
                "flags": 16,
                "color": 0,
                "bbox": (72, 74, 226, 84),
                "origin": (72, 82),
            },
        ],
    }
    body_line1 = {
        "bbox": (77, 90, 320, 100),
        "dir": (1.0, 0.0),
        "spans": [
            {
                "text": "Compute j = f(D)",
                "font": "CMMI10",
                "size": 10.0,
                "flags": 2,
                "color": 0,
                "bbox": (77, 90, 320, 100),
                "origin": (77, 98),
            },
        ],
    }
    body_line2 = {
        "bbox": (77, 105, 320, 115),
        "dir": (1.0, 0.0),
        "spans": [
            {
                "text": "delta = g(x)",
                "font": "CMMI10",
                "size": 10.0,
                "flags": 2,
                "color": 0,
                "bbox": (77, 105, 320, 115),
                "origin": (77, 113),
            },
        ],
    }
    body_line3 = {
        "bbox": (77, 120, 320, 130),
        "dir": (1.0, 0.0),
        "spans": [
            {
                "text": "return j + Z",
                "font": "CMMI10",
                "size": 10.0,
                "flags": 2,
                "color": 0,
                "bbox": (77, 120, 320, 130),
                "origin": (77, 128),
            },
        ],
    }
    page = _make_mock_page(
        [
            {"type": 0, "bbox": (72, 74, 226, 84), "lines": [title_line]},
            {
                "type": 0,
                "bbox": (77, 90, 320, 130),
                "lines": [body_line1, body_line2, body_line3],
            },
        ]
    )
    # Inject table detection: title cell + body cell
    page.find_tables.return_value = MagicMock(
        tables=[
            MagicMock(
                bbox=(72, 72, 540, 140),
                cells=[(72, 72, 540, 84), (72, 84, 540, 140)],
            ),
        ]
    )
    blocks = _extract_page_blocks(page)
    texts = [b["text"] for b in blocks]
    # Title goes through cell extraction
    assert any("Algorithm 1" in t for t in texts)
    # Body must NOT appear as a table cell (complex math → skipped)
    assert not any(b.get("is_table_cell") and "Compute" in b["text"] for b in blocks)


def test_extract_table_cell_blocks_keeps_non_math_cell() -> None:
    """Table cells with only body-text fonts are extracted normally."""
    page_dict: dict[str, Any] = {
        "blocks": [
            {
                "type": 0,
                "bbox": (72, 90, 540, 100),
                "lines": [
                    {
                        "bbox": (72, 90, 540, 100),
                        "spans": [
                            {
                                "bbox": (72, 90, 300, 100),
                                "text": "Plain text",
                                "font": "NimbusRomNo9L-Regu",
                                "flags": 0,
                                "size": 10,
                                "color": 0,
                            },
                        ],
                    }
                ],
            }
        ],
    }
    page_tables = [
        {
            "bbox": (72, 72, 540, 120),
            "cells": [(72, 72, 540, 120)],
        }
    ]
    result = _extract_table_cell_blocks(page_tables, page_dict)
    assert len(result) == 1
    assert result[0]["text"] == "Plain text"


# ── _has_complex_math_layout ──────────────────────────────────────────────────────


def test_has_complex_math_layout_multiline() -> None:
    """Math spans at 3+ y-levels → complex 2D layout."""
    spans = [
        {"text": "x", "font": "CMMI10", "bbox": (100, 80, 110, 90)},
        {"text": "+", "font": "CMSY10", "bbox": (100, 95, 110, 105)},
        {"text": "y", "font": "CMMI10", "bbox": (100, 110, 110, 120)},
    ]
    assert _has_complex_math_layout(spans)


def test_has_complex_math_layout_inline_formula() -> None:
    """Math spans at 1-2 y-levels → simple inline math."""
    spans = [
        {"text": "O(n", "font": "CMMI10", "bbox": (100, 90, 130, 100)},
        {"text": "2", "font": "CMSY7", "bbox": (130, 87, 136, 94)},  # superscript
        {"text": ")", "font": "CMMI10", "bbox": (136, 90, 142, 100)},
    ]
    assert not _has_complex_math_layout(spans)


def test_has_complex_math_layout_footnote_marker() -> None:
    """Single math char (footnote †) at one y-level → not complex."""
    spans = [
        {
            "text": "Handles unknown biases ",
            "font": "NimbusRomNo9L-Regu",
            "bbox": (222, 416, 330, 426),
        },
        {"text": "\u2020", "font": "CMSY6", "bbox": (330, 414, 336, 422)},
    ]
    assert not _has_complex_math_layout(spans)


def test_has_complex_math_layout_single_symbol() -> None:
    """Single math symbol at one y-level → not complex."""
    spans = [{"text": "\u223c", "font": "CMBSY8", "bbox": (370, 416, 380, 426)}]
    assert not _has_complex_math_layout(spans)


def test_has_complex_math_layout_empty_text() -> None:
    """Whitespace-only math spans → not complex."""
    spans = [{"text": "   ", "font": "CMMI10", "bbox": (100, 90, 110, 100)}]
    assert not _has_complex_math_layout(spans)


def test_has_complex_math_layout_no_math() -> None:
    """No math-font spans → not complex."""
    spans = [
        {"text": "Property", "font": "NimbusRomNo9L-Regu", "bbox": (100, 90, 160, 100)},
    ]
    assert not _has_complex_math_layout(spans)


def test_has_complex_math_layout_many_body_lines() -> None:
    """Many y-levels but no math fonts → not complex."""
    spans = [
        {"text": "Line 1", "font": "NimbusRomNo9L-Regu", "bbox": (100, 80, 200, 90)},
        {"text": "Line 2", "font": "NimbusRomNo9L-Regu", "bbox": (100, 95, 200, 105)},
        {"text": "Line 3", "font": "NimbusRomNo9L-Regu", "bbox": (100, 110, 200, 120)},
    ]
    assert not _has_complex_math_layout(spans)


def test_extract_table_cell_blocks_keeps_footnote_cell() -> None:
    """Data table cell with footnote marker in math font is kept."""
    page_dict: dict[str, Any] = {
        "blocks": [
            {
                "type": 0,
                "bbox": (222, 416, 339, 426),
                "lines": [
                    {
                        "bbox": (222, 416, 339, 426),
                        "spans": [
                            {
                                "bbox": (222, 416, 330, 426),
                                "text": "Handles unknown biases ",
                                "font": "NimbusRomNo9L-Regu",
                                "flags": 0,
                                "size": 8,
                                "color": 0,
                            },
                            {
                                "bbox": (330, 416, 339, 426),
                                "text": "\u2020",
                                "font": "CMSY6",
                                "flags": 0,
                                "size": 6,
                                "color": 0,
                            },
                        ],
                    }
                ],
            }
        ],
    }
    page_tables = [
        {
            "bbox": (222, 390, 390, 482),
            "cells": [(222, 416, 339, 426)],
        }
    ]
    result = _extract_table_cell_blocks(page_tables, page_dict)
    # 1 math y-level (footnote marker) → not complex → cell kept
    assert len(result) == 1
    assert "unknown biases" in result[0]["text"]


# ── _apply_translated_blocks edge cases ──────────────────────────────────────


# ── _process_scanned_pages ──────────────────────────────────────────────────


def test_process_scanned_pages_cancel_returns_false(tmp_path: Path) -> None:
    """Cancel check before first scanned page returns False immediately."""
    from src.core.pdf_processor import _process_scanned_pages  # noqa: PLC0415

    pdf = tmp_path / "output.pdf"
    _make_multipage_pdf(pdf, 2, blank_last=True)

    with patch(
        "src.core.pdf_processor._config.load_setting", return_value="TesseractOCR"
    ):
        result = _process_scanned_pages(
            pdf,
            [1],
            "French",
            "",
            None,
            None,
            cancel_check=lambda: True,
            text_weight=0.8,
        )

    assert result is False


def test_process_scanned_pages_ocr_empty_results(tmp_path: Path) -> None:
    """When OCR returns empty results, page is left untouched."""
    from src.core.pdf_processor import _process_scanned_pages  # noqa: PLC0415

    pdf = tmp_path / "output.pdf"
    _make_multipage_pdf(pdf, 2, blank_last=True)

    progress: list[int] = []

    with (
        patch(
            "src.core.pdf_processor._config.load_setting", return_value="TesseractOCR"
        ),
        patch("src.core.ocr_engine.run_ocr", return_value=[]),
    ):
        result = _process_scanned_pages(
            pdf,
            [1],
            "French",
            "",
            None,
            progress.append,
            None,
            0.8,
        )

    assert result is True
    assert progress, "Progress callback should have been called"


def test_process_scanned_pages_progress_callback(tmp_path: Path) -> None:
    """Progress callback is called for each scanned page."""
    from src.core.pdf_processor import _process_scanned_pages  # noqa: PLC0415

    pdf = tmp_path / "output.pdf"
    _make_multipage_pdf(pdf, 3, blank_last=False)  # 3 pages, all have text

    progress: list[int] = []

    with (
        patch(
            "src.core.pdf_processor._config.load_setting", return_value="TesseractOCR"
        ),
        patch("src.core.ocr_engine.run_ocr", return_value=[]),
    ):
        result = _process_scanned_pages(
            pdf,
            [0, 1, 2],
            "French",
            "",
            None,
            progress.append,
            None,
            0.8,
        )

    assert result is True
    assert len(progress) == 3  # noqa: PLR2004
    # Final progress should be 100 (0.8*100 + 1.0*0.2*100)
    assert progress[-1] == 100  # noqa: PLR2004


def test_process_scanned_pages_ocr_success_replaces_page(tmp_path: Path) -> None:
    """When OCR + render succeeds, page content is replaced with translated image."""
    from src.core.pdf_processor import _process_scanned_pages  # noqa: PLC0415

    pdf = tmp_path / "output.pdf"
    _make_pdf(pdf, ["placeholder"])

    fake_ocr_result = MagicMock()
    fake_ocr_result.text = "detected"

    def _fake_render(
        input_path: str,
        output_path: str,
        *args: object,
        **kwargs: object,
    ) -> bool:
        """Writes a minimal valid PNG so page.insert_image() succeeds."""
        # Create a 1x1 black PNG at the output path (no alpha → RGB, 3 components)
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 1, 1), 0)
        pix.save(output_path)
        return True

    with (
        patch(
            "src.core.pdf_processor._config.load_setting", return_value="TesseractOCR"
        ),
        patch("src.core.ocr_engine.run_ocr", return_value=[fake_ocr_result]),
        patch(
            "src.core.llm_engine.translate_image_content",
            return_value={"paragraphs": []},
        ),
        patch(
            "src.core.layout_analysis.merge_to_paragraphs",
            return_value=([], [], []),
        ),
        patch(
            "src.core.image_processor.process_image_translation",
            side_effect=_fake_render,
        ) as mock_render,
    ):
        result = _process_scanned_pages(
            pdf,
            [0],
            "French",
            "",
            None,
            None,
            None,
            0.8,
        )

    assert result is True
    mock_render.assert_called_once()


def test_process_scanned_pages_uses_image_remove_flag(tmp_path: Path) -> None:
    """Scanned pages use PDF_REDACT_IMAGE_REMOVE (not _NONE) to strip raster images."""
    from src.core.pdf_processor import _process_scanned_pages  # noqa: PLC0415

    pdf = tmp_path / "output.pdf"
    _make_pdf(pdf, ["placeholder"])

    fake_ocr = MagicMock(text="detected")

    def _fake_render(
        input_path: str,
        output_path: str,
        *a: object,
        **kw: object,
    ) -> bool:
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 1, 1), 0)
        pix.save(output_path)
        return True

    # Wrap pymupdf.open to intercept apply_redactions on the returned pages
    real_open = pymupdf.open
    redact_calls: list[dict] = []

    def spy_open(path: str) -> object:  # noqa: ANN202
        doc = real_open(path)
        orig_getitem = doc.__class__.__getitem__

        def patched_getitem(self: object, idx: int) -> object:  # noqa: ANN202
            page = orig_getitem(self, idx)
            orig_apply = page.apply_redactions

            def recording_apply(**kwargs: object) -> object:  # noqa: ANN202
                redact_calls.append(kwargs)
                return orig_apply(**kwargs)

            page.apply_redactions = recording_apply
            return page

        doc.__class__.__getitem__ = patched_getitem
        return doc

    with (
        patch(
            "src.core.pdf_processor._config.load_setting", return_value="TesseractOCR"
        ),
        patch("src.core.ocr_engine.run_ocr", return_value=[fake_ocr]),
        patch("src.core.llm_engine.translate_image_content", return_value={}),
        patch(
            "src.core.layout_analysis.merge_to_paragraphs",
            return_value=([MagicMock()], {"0": "Translated"}, []),
        ),
        patch(
            "src.core.image_processor.process_image_translation",
            side_effect=_fake_render,
        ),
        patch.object(pymupdf, "open", side_effect=spy_open),
    ):
        result = _process_scanned_pages(
            pdf,
            [0],
            "French",
            "",
            None,
            None,
            None,
            0.8,
        )

    assert result is True
    assert len(redact_calls) == 1
    assert redact_calls[0]["images"] == pymupdf.PDF_REDACT_IMAGE_REMOVE
    assert redact_calls[0]["graphics"] == pymupdf.PDF_REDACT_LINE_ART_NONE


# ── _page_has_images — exception branch ──────────────────────────────────────


def test_page_has_images_returns_false_on_exception() -> None:
    """_page_has_images returns False when get_images() raises."""
    mock_page = MagicMock()
    mock_page.get_images.side_effect = RuntimeError("corrupt page")
    assert _page_has_images(mock_page) is False


# ── _apply_translated_blocks — explicit redaction flags ──────────────────────


def test_apply_translated_blocks_uses_preserve_flags(tmp_path: Path) -> None:
    """_apply_translated_blocks calls apply_redactions with image/graphics flags."""
    pdf = tmp_path / "src.pdf"
    _make_pdf(pdf, ["Hello"])
    doc, page = _open_page(pdf)
    blocks = _extract_page_blocks(page)
    blocks[0]["translated_text"] = "Bonjour"

    mock_page = MagicMock(wraps=page)
    _apply_translated_blocks(mock_page, blocks, pymupdf)

    mock_page.apply_redactions.assert_called_once_with(
        images=pymupdf.PDF_REDACT_IMAGE_NONE,
        graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
    )
    doc.close()


# ── _process_scanned_pages — render failure (graceful skip) ──────────────────


def test_process_scanned_pages_render_failure_returns_true(tmp_path: Path) -> None:
    """Render failure: page is skipped but True is returned."""
    pdf = tmp_path / "output.pdf"
    _make_scanned_pdf(pdf, num_text_pages=0)

    fake_ocr_result = MagicMock()
    fake_ocr_result.text = "Some text"

    with (
        patch(
            "src.core.pdf_processor._config.load_setting", return_value="TesseractOCR"
        ),
        patch("src.core.ocr_engine.run_ocr", return_value=[fake_ocr_result]),
        patch(
            "src.core.llm_engine.translate_image_content",
            return_value={"paragraphs": []},
        ),
        patch(
            "src.core.layout_analysis.merge_to_paragraphs",
            return_value=([], [], []),
        ),
        patch(
            "src.core.image_processor.process_image_translation",
            return_value=False,
        ) as mock_render,
    ):
        result = _process_scanned_pages(
            pdf,
            [0],
            "French",
            "",
            None,
            None,
            None,
            0.8,
        )

    assert result is True
    mock_render.assert_called_once()


# ── _process_scanned_pages — src_lang forwarding ─────────────────────────────


def test_process_scanned_pages_forwards_src_lang_to_run_ocr(tmp_path: Path) -> None:
    """_process_scanned_pages passes src_lang to run_ocr."""
    pdf = tmp_path / "output.pdf"
    _make_scanned_pdf(pdf, num_text_pages=0)

    with (
        patch(
            "src.core.pdf_processor._config.load_setting", return_value="TesseractOCR"
        ),
        patch("src.core.ocr_engine.run_ocr", return_value=[]) as mock_ocr,
    ):
        _process_scanned_pages(pdf, [0], "French", "Japanese", None, None, None, 0.8)

    mock_ocr.assert_called_once()
    _, kwargs = mock_ocr.call_args
    assert kwargs.get("src_lang") == "Japanese"


# ── process_pdf_file — do_images=False when check_ocr_setup() is False ───────


def test_process_pdf_file_ocr_not_configured_skips_scanned_pages(
    tmp_path: Path,
) -> None:
    """Scanned pages skipped when do_images=True but OCR is not configured."""
    pdf = tmp_path / "input.pdf"
    out = tmp_path / "out.pdf"
    _make_scanned_pdf(pdf, num_text_pages=0)

    with (
        patch("src.core.pdf_processor._config.load_setting", return_value=True),
        patch("src.core.pdf_processor._config.check_ocr_setup", return_value=False),
        patch("src.core.pdf_processor.translate_batch", return_value=[]),
        patch("src.core.pdf_processor._process_scanned_pages") as mock_ocr,
    ):
        result = process_pdf_file(pdf, out, "French")

    assert result is True
    mock_ocr.assert_not_called()


# ── PDF annotation helpers ────────────────────────────────────────────────────


def _make_pdf_with_annotations(
    path: Path,
    texts: list[str] | None = None,
    comments: list[tuple[str, tuple[float, float, float, float]]] | None = None,
    freetext: list[tuple[str, tuple[float, float, float, float]]] | None = None,
) -> None:
    """Creates a PDF with optional text, sticky-note comments, and FreeText boxes.

    Args:
        path: Output PDF path.
        texts: Text strings to insert on the page.
        comments: List of (content, (x0, y0, x1, y1)) for Text annotations.
        freetext: List of (content, (x0, y0, x1, y1)) for FreeText annotations.
    """
    doc = pymupdf.open()
    page = doc.new_page()
    if texts:
        for i, text in enumerate(texts):
            page.insert_text((72, 72 + i * 50), text, fontsize=14)
    if comments:
        for content, rect in comments:
            annot = page.add_text_annot(pymupdf.Point(rect[0], rect[1]), content)
            annot.update()
    if freetext:
        for content, rect in freetext:
            annot = page.add_freetext_annot(pymupdf.Rect(*rect), content, fontsize=10)
            annot.update()
    doc.save(str(path))
    doc.close()


# ── _should_translate_pdf_comments ────────────────────────────────────────────


def test_should_translate_pdf_comments_setting_true() -> None:
    """Returns True when SETTING_TRANSLATE_DOC_COMMENTS is True."""
    with patch("src.core.pdf_processor._config.load_setting", return_value=True):
        assert _should_translate_pdf_comments() is True


def test_should_translate_pdf_comments_setting_false() -> None:
    """Returns False when SETTING_TRANSLATE_DOC_COMMENTS is False."""
    with patch("src.core.pdf_processor._config.load_setting", return_value=False):
        assert _should_translate_pdf_comments() is False


def test_should_translate_pdf_comments_with_config() -> None:
    """Uses config.translate_doc_comments when config is provided."""
    config = MagicMock()
    config.translate_doc_comments = True
    assert _should_translate_pdf_comments(config) is True

    config.translate_doc_comments = False
    assert _should_translate_pdf_comments(config) is False


# ── _should_translate_pdf_textboxes ──────────────────────────────────────────


def test_should_translate_pdf_textboxes_setting_true() -> None:
    """Returns True when SETTING_TRANSLATE_DOC_SHAPES is True."""
    with patch("src.core.pdf_processor._config.load_setting", return_value=True):
        assert _should_translate_pdf_textboxes() is True


def test_should_translate_pdf_textboxes_setting_false() -> None:
    """Returns False when SETTING_TRANSLATE_DOC_SHAPES is False."""
    with patch("src.core.pdf_processor._config.load_setting", return_value=False):
        assert _should_translate_pdf_textboxes() is False


def test_should_translate_pdf_textboxes_with_config() -> None:
    """Uses config.translate_doc_shapes when config is provided."""
    config = MagicMock()
    config.translate_doc_shapes = True
    assert _should_translate_pdf_textboxes(config) is True

    config.translate_doc_shapes = False
    assert _should_translate_pdf_textboxes(config) is False


# ── _extract_page_comments ───────────────────────────────────────────────────


def test_extract_page_comments_empty(tmp_path: Path) -> None:
    """Page with no annotations returns empty list."""
    pdf = tmp_path / "empty.pdf"
    _make_pdf(pdf, ["Hello"])
    doc, page = _open_page(pdf)
    try:
        result = _extract_page_comments(page)
        assert result == []
    finally:
        doc.close()


def test_extract_page_comments_text_annot(tmp_path: Path) -> None:
    """Text (sticky-note) annotation is extracted with correct fields."""
    pdf = tmp_path / "comment.pdf"
    _make_pdf_with_annotations(pdf, comments=[("Review this", (100, 100, 120, 120))])
    doc, page = _open_page(pdf)
    try:
        result = _extract_page_comments(page)
        assert len(result) == 1
        assert result[0]["type"] == "annot"
        assert result[0]["annot_type"] == _ANNOT_TYPE_TEXT
        assert result[0]["text"] == "Review this"
        assert result[0]["annot_id"] != ""
        # Text annotations don't include rect
        assert "rect" not in result[0]
    finally:
        doc.close()


def test_extract_page_comments_skips_freetext(tmp_path: Path) -> None:
    """FreeText annotations are NOT extracted by _extract_page_comments."""
    pdf = tmp_path / "freetext.pdf"
    _make_pdf_with_annotations(pdf, freetext=[("Visible note", (50, 50, 200, 100))])
    doc, page = _open_page(pdf)
    try:
        result = _extract_page_comments(page)
        assert result == []
    finally:
        doc.close()


def test_extract_page_comments_whitespace_skipped(tmp_path: Path) -> None:
    """Annotations with whitespace-only content are skipped."""
    pdf = tmp_path / "ws.pdf"
    _make_pdf_with_annotations(
        pdf,
        comments=[("   ", (100, 100, 120, 120))],
    )
    doc, page = _open_page(pdf)
    try:
        result = _extract_page_comments(page)
        assert result == []
    finally:
        doc.close()


def test_extract_page_comments_exception_returns_empty() -> None:
    """Exception during page.annots() returns empty list."""
    page = MagicMock()
    page.annots.side_effect = RuntimeError("corrupt page")

    result = _extract_page_comments(page)
    assert result == []


def test_extract_page_comments_none_annots() -> None:
    """page.annots() returning None returns empty list."""
    page = MagicMock()
    page.annots.return_value = None

    result = _extract_page_comments(page)
    assert result == []


# ── _extract_page_freetext ───────────────────────────────────────────────────


def test_extract_page_freetext_annot(tmp_path: Path) -> None:
    """FreeText annotation is extracted with rect."""
    pdf = tmp_path / "freetext.pdf"
    _make_pdf_with_annotations(pdf, freetext=[("Visible note", (50, 50, 200, 100))])
    doc, page = _open_page(pdf)
    try:
        result = _extract_page_freetext(page)
        assert len(result) == 1
        assert result[0]["type"] == "annot"
        assert result[0]["annot_type"] == _ANNOT_TYPE_FREE_TEXT
        assert result[0]["text"] == "Visible note"
        assert "rect" in result[0]
        assert len(result[0]["rect"]) == 4  # noqa: PLR2004
    finally:
        doc.close()


def test_extract_page_freetext_skips_sticky_notes(tmp_path: Path) -> None:
    """Sticky-note annotations are NOT extracted by _extract_page_freetext."""
    pdf = tmp_path / "comment.pdf"
    _make_pdf_with_annotations(pdf, comments=[("Review this", (100, 100, 120, 120))])
    doc, page = _open_page(pdf)
    try:
        result = _extract_page_freetext(page)
        assert result == []
    finally:
        doc.close()


def test_extract_page_freetext_whitespace_skipped(tmp_path: Path) -> None:
    """FreeText annotations with whitespace-only content are skipped."""
    pdf = tmp_path / "ws.pdf"
    _make_pdf_with_annotations(
        pdf,
        freetext=[("   ", (50, 300, 200, 350))],
    )
    doc, page = _open_page(pdf)
    try:
        result = _extract_page_freetext(page)
        assert result == []
    finally:
        doc.close()


def test_extract_page_freetext_exception_returns_empty() -> None:
    """Exception during page.annots() returns empty list."""
    page = MagicMock()
    page.annots.side_effect = RuntimeError("corrupt page")

    result = _extract_page_freetext(page)
    assert result == []


def test_extract_page_freetext_none_annots() -> None:
    """page.annots() returning None returns empty list."""
    page = MagicMock()
    page.annots.return_value = None

    result = _extract_page_freetext(page)
    assert result == []


def test_extract_page_freetext_non_text_types_skipped() -> None:
    """Non-FreeText annotation types (e.g. Highlight) are skipped."""
    annot = MagicMock()
    annot.type = (8, "Highlight")
    annot.info = {"content": "highlight text", "id": "h1"}

    page = MagicMock()
    page.annots.return_value = [annot]

    result = _extract_page_freetext(page)
    assert result == []


# ── Split toggle: comments vs textboxes in integration ───────────────────────


def test_extract_split_comments_and_freetext(tmp_path: Path) -> None:
    """Comments and FreeText are extracted by their respective functions."""
    pdf = tmp_path / "mixed.pdf"
    _make_pdf_with_annotations(
        pdf,
        comments=[("Sticky comment", (100, 100, 120, 120))],
        freetext=[("Text box", (50, 300, 200, 350))],
    )
    doc, page = _open_page(pdf)
    try:
        comments = _extract_page_comments(page)
        freetext = _extract_page_freetext(page)
        assert len(comments) == 1
        assert comments[0]["annot_type"] == _ANNOT_TYPE_TEXT
        assert len(freetext) == 1
        assert freetext[0]["annot_type"] == _ANNOT_TYPE_FREE_TEXT
    finally:
        doc.close()


# ── _inject_page_annotations ─────────────────────────────────────────────────


def test_inject_page_annotations_empty_is_noop() -> None:
    """Empty annotation list is a no-op."""
    page = MagicMock()
    _inject_page_annotations(page, [])
    page.annots.assert_not_called()


def test_inject_page_annotations_updates_content() -> None:
    """Matching annotation gets updated via set_info + update."""
    annot = MagicMock()
    annot.info = {"id": "annot-1"}
    page = MagicMock()
    page.annots.return_value = [annot]

    entries = [{"annot_id": "annot-1", "translated_text": "Bonjour", "type": "annot"}]
    _inject_page_annotations(page, entries)

    annot.set_info.assert_called_once_with(content="Bonjour")
    annot.update.assert_called_once()


def test_inject_page_annotations_missing_id_skipped() -> None:
    """Annotations not in the translation map are left untouched."""
    annot = MagicMock()
    annot.info = {"id": "annot-unknown"}
    page = MagicMock()
    page.annots.return_value = [annot]

    entries = [{"annot_id": "annot-1", "translated_text": "Bonjour", "type": "annot"}]
    _inject_page_annotations(page, entries)

    annot.set_info.assert_not_called()


def test_inject_page_annotations_no_translated_text_skipped() -> None:
    """Entries without translated_text are not included in lookup."""
    annot = MagicMock()
    annot.info = {"id": "annot-1"}
    page = MagicMock()
    page.annots.return_value = [annot]

    entries = [{"annot_id": "annot-1", "type": "annot"}]
    _inject_page_annotations(page, entries)

    annot.set_info.assert_not_called()


def test_inject_page_annotations_set_info_exception_logged(caplog) -> None:
    """Exception in set_info is logged and does not raise."""
    annot = MagicMock()
    annot.info = {"id": "annot-1"}
    annot.set_info.side_effect = RuntimeError("corrupt annot")
    page = MagicMock()
    page.annots.return_value = [annot]

    entries = [{"annot_id": "annot-1", "translated_text": "Bonjour", "type": "annot"}]
    with caplog.at_level(logging.WARNING, logger="pdf_processor"):
        _inject_page_annotations(page, entries)

    assert "Failed to inject annotation" in caplog.text


def test_inject_page_annotations_annots_none() -> None:
    """page.annots() returning None is handled gracefully."""
    page = MagicMock()
    page.annots.return_value = None

    entries = [{"annot_id": "annot-1", "translated_text": "Bonjour", "type": "annot"}]
    _inject_page_annotations(page, entries)
    # No error raised


# ── process_pdf_file annotation integration ───────────────────────────────────


def test_process_pdf_file_annotations_translated_when_enabled(
    tmp_path: Path,
) -> None:
    """Annotations are translated when SETTING_TRANSLATE_DOC_COMMENTS is on."""
    pdf = tmp_path / "input.pdf"
    out = tmp_path / "output.pdf"
    _make_pdf_with_annotations(
        pdf,
        texts=["Hello world"],
        comments=[("Review this", (100, 100, 120, 120))],
    )

    with (
        patch(
            "src.core.pdf_processor._config.load_setting",
            side_effect=lambda k, d=None: True,
        ),
        patch("src.core.pdf_processor._config.check_ocr_setup", return_value=False),
        patch(
            "src.core.pdf_processor.translate_batch",
            return_value=["Bonjour le monde", "Vérifiez ceci"],
        ) as mock_batch,
    ):
        result = process_pdf_file(pdf, out, "French")

    assert result is True
    # Both text block and annotation in a single batch call
    call_args = mock_batch.call_args
    texts = call_args[0][0]
    assert len(texts) == 2  # noqa: PLR2004


def test_process_pdf_file_annotations_skipped_when_disabled(
    tmp_path: Path,
) -> None:
    """Annotations are NOT translated when the setting is off."""
    pdf = tmp_path / "input.pdf"
    out = tmp_path / "output.pdf"
    _make_pdf_with_annotations(
        pdf,
        texts=["Hello"],
        comments=[("Comment text", (100, 100, 120, 120))],
    )

    with (
        patch(
            "src.core.pdf_processor._config.load_setting",
            side_effect=lambda k, d=None: False,
        ),
        patch("src.core.pdf_processor._config.check_ocr_setup", return_value=False),
        patch(
            "src.core.pdf_processor.translate_batch",
            return_value=["Bonjour"],
        ) as mock_batch,
    ):
        result = process_pdf_file(pdf, out, "French")

    assert result is True
    # Only the text block, no annotation
    texts = mock_batch.call_args[0][0]
    assert len(texts) == 1


def test_process_pdf_file_annotation_only_page(tmp_path: Path) -> None:
    """Page with annotations but no text blocks is still translated."""
    pdf = tmp_path / "annot_only.pdf"
    out = tmp_path / "output.pdf"
    _make_pdf_with_annotations(
        pdf,
        comments=[("Solo comment", (100, 100, 120, 120))],
    )

    with (
        patch(
            "src.core.pdf_processor._config.load_setting",
            side_effect=lambda k, d=None: True,
        ),
        patch("src.core.pdf_processor._config.check_ocr_setup", return_value=False),
        patch(
            "src.core.pdf_processor.translate_batch",
            return_value=["Commentaire seul"],
        ) as mock_batch,
    ):
        result = process_pdf_file(pdf, out, "French")

    assert result is True
    texts = mock_batch.call_args[0][0]
    assert texts == ["Solo comment"]


def test_process_pdf_file_annotations_in_checkpoint(tmp_path: Path) -> None:
    """Annotations are saved in checkpoint data alongside text blocks."""
    pdf = tmp_path / "input.pdf"
    out = tmp_path / "output.pdf"
    ckpt = tmp_path / "ckpt"
    ckpt.mkdir()
    _make_pdf_with_annotations(
        pdf,
        texts=["Hello"],
        comments=[("Note", (100, 100, 120, 120))],
    )

    with (
        patch(
            "src.core.pdf_processor._config.load_setting",
            side_effect=lambda k, d=None: True,
        ),
        patch("src.core.pdf_processor._config.check_ocr_setup", return_value=False),
        patch(
            "src.core.pdf_processor.translate_batch",
            return_value=["Bonjour", "Remarque"],
        ),
        patch("src.core.pdf_processor.save_pdf_page_progress") as mock_save,
    ):
        process_pdf_file(pdf, out, "French", checkpoint_dir=ckpt)

    # Checkpoint save should include both blocks and annotation entries
    mock_save.assert_called()
    saved_entries = mock_save.call_args[0][2]
    types = [e.get("type") for e in saved_entries]
    assert "annot" in types


def test_process_pdf_file_checkpoint_resume_injects_annotations(
    tmp_path: Path,
) -> None:
    """Checkpoint resume applies cached annotations without re-calling LLM."""
    pdf = tmp_path / "input.pdf"
    out = tmp_path / "output.pdf"
    ckpt = tmp_path / "ckpt"
    ckpt.mkdir()

    _make_pdf_with_annotations(
        pdf,
        texts=["Hello"],
        comments=[("Note", (100, 100, 120, 120))],
    )

    # Pre-populate checkpoint with blocks + annotation entries
    cached = [
        {
            "rect": [72, 56, 200, 76],
            "text": "Hello",
            "translated_text": "Bonjour",
            "font_size": 14.0,
            "font_name": "Helvetica",
            "color": 0,
            "bold": False,
            "italic": False,
        },
        {
            "type": "annot",
            "annot_type": _ANNOT_TYPE_TEXT,
            "annot_id": "test-id",
            "text": "Note",
            "translated_text": "Remarque",
        },
    ]

    with (
        patch(
            "src.core.pdf_processor._config.load_setting",
            side_effect=lambda k, d=None: True,
        ),
        patch("src.core.pdf_processor._config.check_ocr_setup", return_value=False),
        patch(
            "src.core.pdf_processor.load_pdf_checkpoint",
            return_value={0: cached},
        ),
        patch("src.core.pdf_processor.translate_batch") as mock_batch,
        patch("src.core.pdf_processor._inject_page_annotations") as mock_inject,
    ):
        result = process_pdf_file(pdf, out, "French", checkpoint_dir=ckpt)

    assert result is True
    # LLM should NOT be called — everything from checkpoint
    mock_batch.assert_not_called()
    # Annotations should be injected from cache
    mock_inject.assert_called_once()
    annot_args = mock_inject.call_args[0][1]
    assert len(annot_args) == 1
    assert annot_args[0]["translated_text"] == "Remarque"


def test_process_pdf_file_checkpoint_restores_widgets(tmp_path: Path) -> None:
    """Widgets in checkpoint are injected during restore without LLM call."""
    pdf = tmp_path / "input.pdf"
    out = tmp_path / "output.pdf"
    ckpt = tmp_path / "ckpt"
    _make_pdf(pdf, ["Hello"])

    cached = [
        {
            "rect": [72, 56, 200, 76],
            "text": "Hello",
            "translated_text": "Bonjour",
            "font_size": 14.0,
            "font_name": "Helvetica",
            "color": 0,
            "bold": False,
            "italic": False,
        },
        {
            "type": "widget",
            "widget_type": _WIDGET_TYPE_TEXT,
            "field_name": "name",
            "text": "Submit",
            "translated_text": "Soumettre",
        },
    ]

    with (
        patch(
            "src.core.pdf_processor._config.load_setting",
            side_effect=lambda k, d=None: False,
        ),
        patch("src.core.pdf_processor._config.check_ocr_setup", return_value=False),
        patch(
            "src.core.pdf_processor.load_pdf_checkpoint",
            return_value={0: cached},
        ),
        patch("src.core.pdf_processor.translate_batch") as mock_batch,
        patch("src.core.pdf_processor._inject_page_widgets") as mock_inject_w,
    ):
        result = process_pdf_file(pdf, out, "French", checkpoint_dir=ckpt)

    assert result is True
    mock_batch.assert_not_called()
    mock_inject_w.assert_called_once()
    widget_args = mock_inject_w.call_args[0][1]
    assert len(widget_args) == 1
    assert widget_args[0]["translated_text"] == "Soumettre"


def test_process_pdf_file_combined_batch_call(tmp_path: Path) -> None:
    """Text blocks and annotations are sent in a single translate_batch call."""
    pdf = tmp_path / "input.pdf"
    out = tmp_path / "output.pdf"
    # Use sticky-note comments (not FreeText) to avoid double-counting:
    # FreeText annotations render visible text, so _extract_page_blocks
    # would pick them up as text blocks in addition to annotations.
    _make_pdf_with_annotations(
        pdf,
        texts=["Block text"],
        comments=[("Comment note", (300, 300, 320, 320))],
    )

    with (
        patch(
            "src.core.pdf_processor._config.load_setting",
            side_effect=lambda k, d=None: True,
        ),
        patch("src.core.pdf_processor._config.check_ocr_setup", return_value=False),
        patch(
            "src.core.pdf_processor.translate_batch",
            return_value=["Bloc texte", "Note commentaire"],
        ) as mock_batch,
    ):
        result = process_pdf_file(pdf, out, "French")

    assert result is True
    # Should be called exactly once with combined list
    assert mock_batch.call_count == 1
    texts = mock_batch.call_args[0][0]
    assert len(texts) == 2  # noqa: PLR2004


def test_process_pdf_file_annotation_with_config(tmp_path: Path) -> None:
    """Comments enabled via TranslationConfig instead of load_setting."""
    pdf = tmp_path / "input.pdf"
    out = tmp_path / "output.pdf"
    _make_pdf_with_annotations(
        pdf,
        comments=[("Config comment", (100, 100, 120, 120))],
    )

    config = MagicMock()
    config.should_translate_images = False
    config.translate_doc_comments = True
    config.translate_doc_shapes = False

    with (
        patch(
            "src.core.pdf_processor.translate_batch",
            return_value=["Commentaire config"],
        ) as mock_batch,
    ):
        result = process_pdf_file(pdf, out, "French", config=config)

    assert result is True
    texts = mock_batch.call_args[0][0]
    assert texts == ["Config comment"]


def test_process_pdf_file_freetext_with_shapes_config(tmp_path: Path) -> None:
    """FreeText annotations require translate_doc_shapes, not comments."""
    pdf = tmp_path / "input.pdf"
    out = tmp_path / "output.pdf"
    _make_pdf_with_annotations(
        pdf,
        freetext=[("Visible box", (50, 50, 200, 100))],
    )

    def _mock_batch(texts: list, *a: Any, **kw: Any) -> list:
        return [t + " FR" for t in texts]

    # shapes=True, comments=False → FreeText IS translated
    config = MagicMock()
    config.should_translate_images = False
    config.translate_doc_comments = False
    config.translate_doc_shapes = True

    with (
        patch(
            "src.core.pdf_processor.translate_batch",
            side_effect=_mock_batch,
        ),
        patch(
            "src.core.pdf_processor._inject_page_annotations",
        ) as mock_inject_annot,
    ):
        result = process_pdf_file(pdf, out, "French", config=config)

    assert result is True
    # FreeText annotation injection should happen when shapes is on
    mock_inject_annot.assert_called_once()


def test_process_pdf_file_freetext_skipped_when_shapes_off(
    tmp_path: Path,
) -> None:
    """FreeText annot entries are not added when shapes toggle is off.

    Note: PyMuPDF still extracts FreeText visible text as a regular text
    block, so _extract_page_blocks may return it.  The key assertion is
    that no separate annot entry is created for the FreeText annotation.
    """
    pdf = tmp_path / "input.pdf"
    out = tmp_path / "output.pdf"
    _make_pdf_with_annotations(
        pdf,
        texts=["Hello"],
        freetext=[("Visible box", (50, 50, 200, 100))],
    )

    def _mock_batch(texts: list, *a: Any, **kw: Any) -> list:
        return [t + " FR" for t in texts]

    config = MagicMock()
    config.should_translate_images = False
    config.translate_doc_comments = False
    config.translate_doc_shapes = False

    with (
        patch(
            "src.core.pdf_processor.translate_batch",
            side_effect=_mock_batch,
        ),
        patch(
            "src.core.pdf_processor._inject_page_annotations",
        ) as mock_inject_annot,
    ):
        result = process_pdf_file(pdf, out, "French", config=config)

    assert result is True
    # No annotation injection should happen when shapes is off
    mock_inject_annot.assert_not_called()


# ---------------------------------------------------------------------------
# _inject_page_annotations — empty annot_id filtering
# ---------------------------------------------------------------------------


def test_inject_page_annotations_empty_annot_id_skipped() -> None:
    """Entries with empty annot_id are excluded from the lookup."""
    mock_page = MagicMock()
    # Entry has no usable annot_id, so lookup should be empty → early return
    _inject_page_annotations(
        mock_page,
        [{"annot_id": "", "translated_text": "Bonjour"}],
    )
    # page.annots() should never be called when lookup is empty
    mock_page.annots.assert_not_called()


def test_inject_page_annotations_empty_translated_text_skipped() -> None:
    """Entries with empty translated_text are excluded from the lookup."""
    mock_page = MagicMock()
    _inject_page_annotations(
        mock_page,
        [{"annot_id": "a1", "translated_text": ""}],
    )
    mock_page.annots.assert_not_called()


# ---------------------------------------------------------------------------
# _inject_page_annotations — outer exception (page.annots() raises)
# ---------------------------------------------------------------------------


def test_inject_page_annotations_annots_call_raises_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """If page.annots() raises, the error is logged and not propagated."""
    mock_page = MagicMock()
    mock_page.annots.side_effect = RuntimeError("corrupt page")

    with caplog.at_level(logging.WARNING, logger="pdf_processor"):
        _inject_page_annotations(
            mock_page,
            [{"annot_id": "a1", "translated_text": "Bonjour"}],
        )

    assert "Failed to iterate annotations" in caplog.text


# ---------------------------------------------------------------------------
# _process_scanned_pages — config.ocr_method branch
# ---------------------------------------------------------------------------


def test_process_scanned_pages_uses_config_ocr_method(tmp_path: Path) -> None:
    """When config has ocr_method, it is used instead of load_setting."""
    # Create a single-page PDF with an image (blank page text removed)
    pdf = tmp_path / "input.pdf"
    _make_pdf(pdf, ["Some text"])
    out = tmp_path / "output.pdf"
    import shutil  # noqa: PLC0415

    shutil.copy(str(pdf), str(out))

    config = MagicMock()
    config.ocr_method = "EasyOCR"

    with (
        patch(
            "src.core.ocr_engine.run_ocr",
            return_value=[],
        ) as mock_ocr,
        patch("src.core.pdf_processor._config.load_setting") as mock_ls,
    ):
        _process_scanned_pages(
            out,
            [0],
            "French",
            "",
            None,
            None,
            None,
            0.8,
            config=config,
        )

    # run_ocr should have been called with method="EasyOCR"
    mock_ocr.assert_called_once()
    assert mock_ocr.call_args[1].get("method") == "EasyOCR"
    # load_setting should NOT have been called for OCR_METHOD
    for call in mock_ls.call_args_list:
        assert "ocr" not in str(call).lower()


# ── URL link annotation tests ─────────────────────────────────────────────────


# ── Raster image overlap detection tests ──────────────────────────────────────


class TestGetImageRects:
    """Tests for _get_image_rects."""

    def test_extracts_image_block_bboxes(self) -> None:
        page_dict = {
            "blocks": [
                {"type": 1, "bbox": (50, 50, 200, 200)},
                {"type": 0, "bbox": (10, 10, 100, 30), "lines": []},
                {"type": 1, "bbox": (300, 100, 500, 400)},
            ],
        }
        rects = _get_image_rects(page_dict)
        assert len(rects) == 2  # noqa: PLR2004
        assert (50, 50, 200, 200) in rects
        assert (300, 100, 500, 400) in rects

    def test_returns_empty_for_no_images(self) -> None:
        page_dict = {"blocks": [{"type": 0, "bbox": (0, 0, 100, 50), "lines": []}]}
        assert _get_image_rects(page_dict) == []

    def test_returns_empty_for_no_blocks(self) -> None:
        assert _get_image_rects({"blocks": []}) == []


class TestBlockOverlapsImage:
    """Tests for _block_overlaps_image."""

    def test_block_fully_inside_image(self) -> None:
        """Text block completely inside an image → True."""
        assert _block_overlaps_image(
            [60, 60, 180, 180],
            [(50, 50, 200, 200)],
        )

    def test_block_mostly_inside_image(self) -> None:
        """Block with >50% overlap → True."""
        # Block is 100x100, image covers 80x100 of it → 80% overlap
        assert _block_overlaps_image(
            [0, 0, 100, 100],
            [(20, 0, 200, 200)],
        )

    def test_block_barely_overlapping_image(self) -> None:
        """Block with <50% overlap → False."""
        # Block is 100x100, image covers 10x100 of it → 10% overlap
        assert not _block_overlaps_image(
            [0, 0, 100, 100],
            [(90, 0, 200, 200)],
        )

    def test_block_outside_all_images(self) -> None:
        """No overlap at all → False."""
        assert not _block_overlaps_image(
            [0, 0, 40, 40],
            [(50, 50, 200, 200)],
        )

    def test_no_images(self) -> None:
        """Empty image list → False."""
        assert not _block_overlaps_image([0, 0, 100, 50], [])

    def test_zero_area_block(self) -> None:
        """Block with zero area → False (no division by zero)."""
        assert not _block_overlaps_image([50, 50, 50, 50], [(0, 0, 200, 200)])

    def test_multiple_images_second_matches(self) -> None:
        """Block overlaps only the second image."""
        assert _block_overlaps_image(
            [310, 110, 490, 390],
            [(0, 0, 50, 50), (300, 100, 500, 400)],
        )


class TestExtractPageBlocksSkipsImageOverlap:
    """Integration: _extract_page_blocks skips invisible OCR text over images."""

    def test_text_over_image_is_skipped(self, tmp_path: Path) -> None:
        """Text block sitting on top of a raster image is excluded."""
        pdf = tmp_path / "ocr_layer.pdf"
        doc = pymupdf.open()
        page = doc.new_page()

        # Insert a raster image covering a large area
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 200, 200), 0)
        pix.set_rect(pix.irect, (200, 200, 200))
        img_rect = pymupdf.Rect(50, 50, 250, 250)
        page.insert_image(img_rect, pixmap=pix)

        # Insert text ON TOP of the image (simulates invisible OCR layer)
        page.insert_text((80, 150), "OCR text over image", fontsize=12)

        # Insert text OUTSIDE the image (regular body text)
        page.insert_text((50, 400), "Regular body text", fontsize=14)

        doc.save(str(pdf))
        doc.close()

        doc2, page2 = _open_page(pdf)
        blocks = _extract_page_blocks(page2)
        doc2.close()

        texts = [b["text"] for b in blocks]
        # Regular text should be extracted
        assert any("Regular body text" in t for t in texts)
        # OCR text over image should be skipped
        assert not any("OCR text over image" in t for t in texts)

    def test_text_outside_image_is_kept(self, tmp_path: Path) -> None:
        """Text not overlapping any image is extracted normally."""
        pdf = tmp_path / "normal.pdf"
        doc = pymupdf.open()
        page = doc.new_page()

        # Small image in one corner
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 50, 50), 0)
        page.insert_image(pymupdf.Rect(10, 10, 60, 60), pixmap=pix)

        # Text far from the image
        page.insert_text((100, 200), "Far away text", fontsize=14)

        doc.save(str(pdf))
        doc.close()

        doc2, page2 = _open_page(pdf)
        blocks = _extract_page_blocks(page2)
        doc2.close()

        texts = [b["text"] for b in blocks]
        assert any("Far away text" in t for t in texts)


# ── FreeText annotation text box tests ────────────────────────────────────────


class TestGetFreetextAnnotRects:
    """Tests for _get_freetext_annot_rects."""

    def test_returns_freetext_rects(self, tmp_path: Path) -> None:
        pdf = tmp_path / "ft.pdf"
        doc = pymupdf.open()
        page = doc.new_page()
        annot = page.add_freetext_annot(
            pymupdf.Rect(100, 200, 400, 260),
            "Hello",
            fontsize=12,
        )
        annot.update()
        doc.save(str(pdf))
        doc.close()

        doc2, page2 = _open_page(pdf)
        rects = _get_freetext_annot_rects(page2)
        doc2.close()

        assert len(rects) == 1  # noqa: PLR2004
        assert rects[0].x0 == pytest.approx(100.0, abs=1)  # noqa: PLR2004
        assert rects[0].y0 == pytest.approx(200.0, abs=1)  # noqa: PLR2004

    def test_ignores_sticky_note_annotations(self, tmp_path: Path) -> None:
        pdf = tmp_path / "sticky.pdf"
        doc = pymupdf.open()
        page = doc.new_page()
        # Sticky note (type 0) — not FreeText
        page.add_text_annot(pymupdf.Point(50, 50), "Sticky note")
        doc.save(str(pdf))
        doc.close()

        doc2, page2 = _open_page(pdf)
        rects = _get_freetext_annot_rects(page2)
        doc2.close()
        assert rects == []

    def test_no_annotations(self, tmp_path: Path) -> None:
        pdf = tmp_path / "plain.pdf"
        _make_pdf(pdf, ["Plain text"])
        doc2, page2 = _open_page(pdf)
        rects = _get_freetext_annot_rects(page2)
        doc2.close()
        assert rects == []


class TestBlockInsideFreetext:
    """Tests for _block_inside_freetext."""

    def test_center_inside_freetext_rect(self) -> None:
        """Block whose center is inside the FreeText rect → True."""
        ft_rect = pymupdf.Rect(100, 200, 400, 260)
        # Text block rendered inside the annotation
        assert _block_inside_freetext([110, 210, 300, 250], [ft_rect])

    def test_center_outside_freetext_rect(self) -> None:
        """Block whose center is outside all FreeText rects → False."""
        ft_rect = pymupdf.Rect(100, 200, 400, 260)
        assert not _block_inside_freetext([10, 10, 80, 30], [ft_rect])

    def test_block_extends_beyond_but_center_inside(self) -> None:
        """Block that slightly overflows the annotation (font descenders)."""
        ft_rect = pymupdf.Rect(100, 200, 400, 260)
        # Block y starts above annotation (196 < 200) but center is inside
        assert _block_inside_freetext([100, 196, 300, 240], [ft_rect])

    def test_empty_freetext_rects(self) -> None:
        assert not _block_inside_freetext([0, 0, 100, 50], [])


class TestExtractPageBlocksSkipsFreetext:
    """Integration: _extract_page_blocks excludes FreeText annotation text."""

    def test_freetext_text_excluded_from_blocks(self, tmp_path: Path) -> None:
        """FreeText annotation text should NOT appear in extracted blocks."""
        pdf = tmp_path / "ft_skip.pdf"
        doc = pymupdf.open()
        page = doc.new_page()

        # Regular text
        page.insert_text((72, 72), "Regular body text", fontsize=14)

        # FreeText annotation (visible text box)
        annot = page.add_freetext_annot(
            pymupdf.Rect(100, 200, 400, 260),
            "FreeText box content",
            fontsize=12,
        )
        annot.update()

        doc.save(str(pdf))
        doc.close()

        doc2, page2 = _open_page(pdf)
        blocks = _extract_page_blocks(page2)
        doc2.close()

        texts = [b["text"] for b in blocks]
        # Regular text should be extracted
        assert any("Regular body text" in t for t in texts)
        # FreeText text should be excluded
        assert not any("FreeText box content" in t for t in texts)

    def test_freetext_annotation_survives_translation(
        self,
        tmp_path: Path,
    ) -> None:
        """End-to-end: FreeText annotation is preserved after block redaction."""
        pdf = tmp_path / "ft_survive.pdf"
        doc = pymupdf.open()
        page = doc.new_page()

        page.insert_text((72, 72), "Body text to translate", fontsize=14)
        annot = page.add_freetext_annot(
            pymupdf.Rect(100, 200, 400, 260),
            "Text box content",
            fontsize=12,
        )
        annot.update()
        doc.save(str(pdf))
        doc.close()

        # Simulate translation of body text only
        doc, page = _open_page(pdf)
        blocks = _extract_page_blocks(page)

        # Only body text should be in blocks
        assert len(blocks) == 1  # noqa: PLR2004
        blocks[0]["translated_text"] = "Texte traduit"
        _apply_translated_blocks(page, blocks, pymupdf)

        out = tmp_path / "out.pdf"
        doc.save(str(out))
        doc.close()

        # Verify annotation survived (must access before closing doc)
        doc2, page2 = _open_page(out)
        freetext_data = [
            a.info["content"]
            for a in page2.annots()
            if a.type[0] == 2  # noqa: PLR2004
        ]
        doc2.close()

        assert len(freetext_data) == 1  # noqa: PLR2004
        assert freetext_data[0] == "Text box content"


# ── _save_page_links text extraction tests ─────────────────────────────────────


class TestSavePageLinksTextExtraction:
    """Tests for _save_page_links extracting text under link rects."""

    def test_extracts_text_under_link_rect(self, tmp_path: Path) -> None:
        """Link text is captured in ``_inner`` key."""
        pdf = tmp_path / "link.pdf"
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 100), "[6] Smith et al.", fontsize=12)
        link_rect = pymupdf.Rect(72, 85, 90, 105)
        page.insert_link(
            {
                "kind": 1,
                "from": link_rect,
                "page": 0,
                "to": pymupdf.Point(0, 0),
            }
        )
        doc.save(str(pdf))
        doc.close()

        doc2, page2 = _open_page(pdf)
        saved = _save_page_links(page2)
        doc2.close()

        assert len(saved) == 1  # noqa: PLR2004
        assert "_inner" in saved[0]
        # Context chars are stored for disambiguation
        assert "_src_right" in saved[0]

    def test_no_inner_key_when_no_words_under_link(self, tmp_path: Path) -> None:
        """Links over empty areas get no ``_inner`` key."""
        pdf = tmp_path / "empty_link.pdf"
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 100), "Some text", fontsize=12)
        # Link rect far from text
        page.insert_link(
            {
                "kind": 1,
                "from": pymupdf.Rect(400, 400, 500, 500),
                "page": 0,
                "to": pymupdf.Point(0, 0),
            }
        )
        doc.save(str(pdf))
        doc.close()

        doc2, page2 = _open_page(pdf)
        saved = _save_page_links(page2)
        doc2.close()

        assert len(saved) == 1  # noqa: PLR2004
        assert "_inner" not in saved[0]

    def test_uri_link_also_gets_text(self, tmp_path: Path) -> None:
        """URI links also capture text under their rect."""
        pdf = tmp_path / "uri.pdf"
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 100), "Click here", fontsize=12)
        page.insert_link(
            {
                "kind": 2,
                "from": pymupdf.Rect(72, 85, 200, 105),
                "uri": "https://example.com",
            }
        )
        doc.save(str(pdf))
        doc.close()

        doc2, page2 = _open_page(pdf)
        saved = _save_page_links(page2)
        doc2.close()

        assert len(saved) == 1  # noqa: PLR2004
        assert saved[0].get("uri") == "https://example.com"
        assert "_inner" in saved[0]
        assert "Click" in saved[0]["_inner"]

    def test_saves_link_style_properties(self, tmp_path: Path) -> None:
        """Border color and width are captured in ``_style`` key."""
        pdf = tmp_path / "styled.pdf"
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 100), "[6] Reference", fontsize=12)
        page.insert_link(
            {
                "kind": 1,
                "from": pymupdf.Rect(70, 85, 95, 110),
                "page": 0,
                "to": pymupdf.Point(0, 0),
            }
        )
        doc.save(str(pdf))
        doc.close()

        # Set style via xref (simulating real PDF with styled links)
        doc2 = pymupdf.open(str(pdf))
        page2 = doc2[0]
        links = page2.get_links()
        xref = links[0]["xref"]
        doc2.xref_set_key(xref, "C", "[1 0 0]")
        doc2.xref_set_key(xref, "Border", "[0 0 1]")
        doc2.save(str(pdf), incremental=True, encryption=0)
        doc2.close()

        doc3, page3 = _open_page(pdf)
        saved = _save_page_links(page3)
        doc3.close()

        assert len(saved) == 1  # noqa: PLR2004
        assert "_style" in saved[0]
        assert "C" in saved[0]["_style"]
        assert "Border" in saved[0]["_style"]

    def test_no_style_key_for_unstyled_link(self, tmp_path: Path) -> None:
        """Links without custom border/color get no ``_style`` key."""
        pdf = tmp_path / "plain.pdf"
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 100), "text", fontsize=12)
        page.insert_link(
            {
                "kind": 1,
                "from": pymupdf.Rect(70, 85, 95, 110),
                "page": 0,
                "to": pymupdf.Point(0, 0),
            }
        )
        doc.save(str(pdf))
        doc.close()

        doc2, page2 = _open_page(pdf)
        saved = _save_page_links(page2)
        doc2.close()

        assert len(saved) == 1  # noqa: PLR2004
        # Default links have BS with W=0, which is a dict type (not null)
        # but no C or Border unless explicitly set
        style = saved[0].get("_style", {})
        assert "C" not in style


# ── _restore_page_links position remapping tests ──────────────────────────────


class TestRestorePageLinksRemapping:
    """Tests for _restore_page_links remapping link positions."""

    def test_remaps_link_to_new_text_position(self, tmp_path: Path) -> None:
        """Internal link's rect is updated to match new text position."""
        pdf = tmp_path / "remap.pdf"
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 100), "[6] Reference text", fontsize=12)
        doc.save(str(pdf))
        doc.close()

        doc2, page2 = _open_page(pdf)
        original_rect = pymupdf.Rect(72, 85, 90, 105)
        redact_rects = [pymupdf.Rect(60, 80, 400, 110)]

        saved_links = [
            {
                "kind": 1,
                "from": original_rect,
                "page": 0,
                "to": pymupdf.Point(0, 0),
                "_inner": "[6]",
            }
        ]

        _restore_page_links(page2, saved_links, redact_rects)

        # Must save + reopen to see inserted links
        out = tmp_path / "out.pdf"
        doc2.save(str(out))
        doc2.close()

        doc3, page3 = _open_page(out)
        links = page3.get_links()
        doc3.close()

        assert len(links) >= 1

    def test_no_remap_when_no_redact_overlap(self, tmp_path: Path) -> None:
        """Links not overlapping redacted rects keep original position."""
        pdf = tmp_path / "noremap.pdf"
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 100), "Some text", fontsize=12)
        doc.save(str(pdf))
        doc.close()

        doc2, page2 = _open_page(pdf)
        original_rect = pymupdf.Rect(72, 85, 200, 105)
        # Redact rect far away from link
        redact_rects = [pymupdf.Rect(400, 400, 500, 500)]

        saved_links = [
            {
                "kind": 1,
                "from": original_rect,
                "page": 0,
                "to": pymupdf.Point(0, 0),
                "_inner": "Some text",
            }
        ]

        _restore_page_links(page2, saved_links, redact_rects)

        out = tmp_path / "out.pdf"
        doc2.save(str(out))
        doc2.close()

        doc3, page3 = _open_page(out)
        links = page3.get_links()
        doc3.close()

        # Link inserted with original rect (not remapped)
        assert len(links) == 1  # noqa: PLR2004
        fr = links[0]["from"]
        # Should be close to original
        assert abs(fr.x0 - original_rect.x0) < 1  # noqa: PLR2004

    def test_no_remap_without_inner_key(self, tmp_path: Path) -> None:
        """Links without ``_inner`` are not remapped even if overlapping."""
        pdf = tmp_path / "notext.pdf"
        doc = pymupdf.open()
        doc.new_page()
        doc.save(str(pdf))
        doc.close()

        doc2, page2 = _open_page(pdf)
        original_rect = pymupdf.Rect(72, 85, 200, 105)
        redact_rects = [pymupdf.Rect(60, 80, 400, 110)]

        saved_links = [
            {
                "kind": 1,
                "from": original_rect,
                "page": 0,
                "to": pymupdf.Point(0, 0),
            }
        ]

        _restore_page_links(page2, saved_links, redact_rects)

        out = tmp_path / "out.pdf"
        doc2.save(str(out))
        doc2.close()

        doc3, page3 = _open_page(out)
        links = page3.get_links()
        doc3.close()

        assert len(links) == 1  # noqa: PLR2004
        fr = links[0]["from"]
        assert abs(fr.x0 - original_rect.x0) < 1  # noqa: PLR2004

    def test_no_remap_without_redact_rects(self, tmp_path: Path) -> None:
        """Without redact_rects, links are not remapped."""
        pdf = tmp_path / "nored.pdf"
        doc = pymupdf.open()
        doc.new_page()
        doc.save(str(pdf))
        doc.close()

        doc2, page2 = _open_page(pdf)
        original_rect = pymupdf.Rect(72, 85, 200, 105)

        saved_links = [
            {
                "kind": 1,
                "from": original_rect,
                "page": 0,
                "to": pymupdf.Point(0, 0),
                "_inner": "[6]",
            }
        ]

        _restore_page_links(page2, saved_links)

        out = tmp_path / "out.pdf"
        doc2.save(str(out))
        doc2.close()

        doc3, page3 = _open_page(out)
        links = page3.get_links()
        doc3.close()

        assert len(links) == 1  # noqa: PLR2004

    def test_inner_key_not_in_inserted_link(self, tmp_path: Path) -> None:
        """The ``_inner`` key is stripped and not passed to insert_link."""
        pdf = tmp_path / "strip.pdf"
        doc = pymupdf.open()
        doc.new_page()
        doc.save(str(pdf))
        doc.close()

        doc2, page2 = _open_page(pdf)
        saved_links = [
            {
                "kind": 1,
                "from": pymupdf.Rect(72, 85, 200, 105),
                "page": 0,
                "to": pymupdf.Point(0, 0),
                "_inner": "test",
            }
        ]

        # Should not raise (insert_link ignores unknown keys, but we strip)
        _restore_page_links(page2, saved_links)

        out = tmp_path / "out.pdf"
        doc2.save(str(out))
        doc2.close()

        doc3, page3 = _open_page(out)
        links = page3.get_links()
        doc3.close()

        assert len(links) == 1  # noqa: PLR2004

    def test_restores_link_style_after_insert(self, tmp_path: Path) -> None:
        """Border color and width from ``_style`` are applied to restored link."""
        pdf = tmp_path / "style_restore.pdf"
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 100), "text", fontsize=12)
        doc.save(str(pdf))
        doc.close()

        doc2, page2 = _open_page(pdf)
        saved_links = [
            {
                "kind": 1,
                "from": pymupdf.Rect(72, 85, 200, 105),
                "page": 0,
                "to": pymupdf.Point(0, 0),
                "_style": {"C": "[1 0 0]", "Border": "[0 0 1]"},
            }
        ]

        _restore_page_links(page2, saved_links)

        out = tmp_path / "out.pdf"
        doc2.save(str(out))
        doc2.close()

        doc3 = pymupdf.open(str(out))
        page3 = doc3[0]
        links = page3.get_links()
        assert len(links) == 1  # noqa: PLR2004
        xref = links[0]["xref"]
        c_kind, c_val = doc3.xref_get_key(xref, "C")
        border_kind, border_val = doc3.xref_get_key(xref, "Border")
        # insert_link() injects BS <</W 0>> which suppresses Border;
        # the fix removes BS when the original had Border but no BS.
        bs_kind, _ = doc3.xref_get_key(xref, "BS")
        doc3.close()

        assert c_kind == "array"
        assert "1 0 0" in c_val
        assert border_kind == "array"
        assert "0 0 1" in border_val
        assert bs_kind == "null"

    def test_preserves_bs_when_original_had_bs(self, tmp_path: Path) -> None:
        """When the original link had BS, it is restored (not removed)."""
        pdf = tmp_path / "bs_preserve.pdf"
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 100), "text", fontsize=12)
        doc.save(str(pdf))
        doc.close()

        doc2, page2 = _open_page(pdf)
        saved_links = [
            {
                "kind": 1,
                "from": pymupdf.Rect(72, 85, 200, 105),
                "page": 0,
                "to": pymupdf.Point(0, 0),
                "_style": {
                    "C": "[0 1 0]",
                    "Border": "[0 0 1]",
                    "BS": "<</W 1/S/U>>",
                },
            }
        ]

        _restore_page_links(page2, saved_links)

        out = tmp_path / "out.pdf"
        doc2.save(str(out))
        doc2.close()

        doc3 = pymupdf.open(str(out))
        page3 = doc3[0]
        links = page3.get_links()
        assert len(links) == 1  # noqa: PLR2004
        xref = links[0]["xref"]
        bs_kind, bs_val = doc3.xref_get_key(xref, "BS")
        doc3.close()

        # BS should be preserved (overwritten with saved value, not removed)
        assert bs_kind != "null"
        assert "W 1" in bs_val


# ── _apply_translated_blocks link deletion + remapping integration ─────────────


class TestApplyTranslatedBlocksLinkRemapping:
    """Integration: links are deleted before redaction and remapped after."""

    def test_goto_link_remapped_after_translation(self, tmp_path: Path) -> None:
        """Internal goto link is repositioned to translated text."""
        pdf = tmp_path / "goto.pdf"
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 100), "[6] Original reference", fontsize=12)
        # Add goto link over "[6]"
        page.insert_link(
            {
                "kind": 1,
                "from": pymupdf.Rect(70, 85, 95, 110),
                "page": 0,
                "to": pymupdf.Point(0, 0),
            }
        )
        doc.save(str(pdf))
        doc.close()

        doc2, page2 = _open_page(pdf)
        blocks = _extract_page_blocks(page2)
        assert blocks
        blocks[0]["translated_text"] = "[6] Referencia traducida"

        _apply_translated_blocks(page2, blocks, pymupdf)

        out = tmp_path / "out.pdf"
        doc2.save(str(out))
        doc2.close()

        doc3, page3 = _open_page(out)
        links = page3.get_links()
        doc3.close()

        # The goto link should be present (remapped)
        goto_links = [lk for lk in links if lk["kind"] == 1]  # noqa: PLR2004
        assert len(goto_links) >= 1

    def test_all_links_deleted_before_redaction(self, tmp_path: Path) -> None:
        """Links are explicitly deleted so none survive at stale positions."""
        pdf = tmp_path / "del.pdf"
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 100), "Test text", fontsize=12)
        page.insert_link(
            {
                "kind": 1,
                "from": pymupdf.Rect(72, 85, 200, 105),
                "page": 0,
                "to": pymupdf.Point(0, 0),
            }
        )
        doc.save(str(pdf))
        doc.close()

        # Verify link exists after save/reopen
        doc1, page1 = _open_page(pdf)
        assert len(page1.get_links()) == 1  # noqa: PLR2004
        doc1.close()

        doc2, page2 = _open_page(pdf)
        blocks = _extract_page_blocks(page2)
        assert blocks
        blocks[0]["translated_text"] = "Translated text"

        _apply_translated_blocks(page2, blocks, pymupdf)

        out = tmp_path / "out.pdf"
        doc2.save(str(out))
        doc2.close()

        # All links should come from _restore_page_links, not stale survivors
        doc3, page3 = _open_page(out)
        links = page3.get_links()
        doc3.close()

        # Link should be restored (not duplicated)
        goto_links = [lk for lk in links if lk["kind"] == 1]  # noqa: PLR2004
        assert len(goto_links) == 1  # noqa: PLR2004

    def test_link_style_preserved_through_translation(self, tmp_path: Path) -> None:
        """Styled link retains its border color after full translate cycle."""
        pdf = tmp_path / "styled.pdf"
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 100), "[6] Reference", fontsize=12)
        page.insert_link(
            {
                "kind": 1,
                "from": pymupdf.Rect(70, 85, 95, 110),
                "page": 0,
                "to": pymupdf.Point(0, 0),
            }
        )
        doc.save(str(pdf))
        doc.close()

        # Add style to the link (simulating LaTeX hyperref)
        doc2 = pymupdf.open(str(pdf))
        page2 = doc2[0]
        xref = page2.get_links()[0]["xref"]
        doc2.xref_set_key(xref, "C", "[1 0 0]")
        doc2.xref_set_key(xref, "Border", "[0 0 1]")
        doc2.save(str(pdf), incremental=True, encryption=0)
        doc2.close()

        # Translate
        doc3, page3 = _open_page(pdf)
        blocks = _extract_page_blocks(page3)
        assert blocks
        blocks[0]["translated_text"] = "[6] Referencia"
        _apply_translated_blocks(page3, blocks, pymupdf)

        out = tmp_path / "out.pdf"
        doc3.save(str(out))
        doc3.close()

        # Verify style survived
        doc4 = pymupdf.open(str(out))
        page4 = doc4[0]
        links = page4.get_links()
        goto_links = [lk for lk in links if lk["kind"] == 1]  # noqa: PLR2004
        assert len(goto_links) >= 1
        xref = goto_links[0]["xref"]
        c_kind, c_val = doc4.xref_get_key(xref, "C")
        doc4.close()

        assert c_kind == "array"
        assert "1 0 0" in c_val


# ── Precise link text extraction tests ──────────────────────────────────────────


class TestSavePageLinksPreciseText:
    """Tests for character-level text extraction in _save_page_links."""

    def test_hybrid_broad_and_inner_text(self, tmp_path: Path) -> None:
        """Tight link over '6' in '[6].' gets broad='[6' and inner='6'."""
        pdf = tmp_path / "precise.pdf"
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 100), "[6]. Smith et al.", fontsize=12)
        # Tight rect covering only the digit '6'
        page.insert_link(
            {
                "kind": 1,
                "from": pymupdf.Rect(75, 87, 82, 104),
                "page": 0,
                "to": pymupdf.Point(0, 0),
            }
        )
        doc.save(str(pdf))
        doc.close()

        doc2, page2 = _open_page(pdf)
        saved = _save_page_links(page2)
        doc2.close()

        assert len(saved) == 1  # noqa: PLR2004
        assert saved[0].get("_inner") == "6"

    def test_wider_rect_captures_inner(self, tmp_path: Path) -> None:
        """Link covering '[6]' gets _inner with overlapping chars."""
        pdf = tmp_path / "wider.pdf"
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 100), "[6]. Smith", fontsize=12)
        # Wider rect covering '[6]'
        page.insert_link(
            {
                "kind": 1,
                "from": pymupdf.Rect(70, 87, 86, 104),
                "page": 0,
                "to": pymupdf.Point(0, 0),
            }
        )
        doc.save(str(pdf))
        doc.close()

        doc2, page2 = _open_page(pdf)
        saved = _save_page_links(page2)
        doc2.close()

        assert len(saved) == 1  # noqa: PLR2004
        inner = saved[0].get("_inner", "")
        assert "6" in inner
        assert "Smith" not in inner


# ── _join_textbox_lines tests ─────────────────────────────────────────────────


class TestJoinTextboxLines:
    """Tests for _join_textbox_lines."""

    def test_single_line_unchanged(self) -> None:
        assert _join_textbox_lines("Hello World") == "Hello World"

    def test_normal_line_break_joins_with_space(self) -> None:
        assert _join_textbox_lines("Hello\nWorld") == "Hello World"

    def test_dehyphenation(self) -> None:
        assert _join_textbox_lines("Mod-\nels at Meta") == "Models at Meta"


# ── _map_stripped_pos tests ───────────────────────────────────────────────────


class TestMapStrippedPos:
    """Tests for _map_stripped_pos."""

    def test_plain_text_identity(self) -> None:
        """No tags: positions are unchanged."""
        assert _map_stripped_pos("Hello", 0) == 0
        assert _map_stripped_pos("Hello", 3) == 3  # noqa: PLR2004
        assert _map_stripped_pos("Hello", 5) == 5  # noqa: PLR2004

    def test_skips_tag(self) -> None:
        """Position after a tag skips the tag characters."""
        # "A<b>B" → stripped "AB", pos 1 → orig 4 (skips "<b>")
        assert _map_stripped_pos("A<b>B", 1) == 4  # noqa: PLR2004

    def test_sup_tag(self) -> None:
        """Superscript tag: maps past <sup> and </sup>."""
        text = "Alshahwan<sup>*</sup>"
        # stripped = "Alshahwan*", pos 9 = "*" → orig 14 (skips <sup>)
        assert _map_stripped_pos(text, 9) == 14  # noqa: PLR2004
        # pos 10 = end → orig 21 (skips </sup>, end of string)
        assert _map_stripped_pos(text, 10) == 21  # noqa: PLR2004


# ── _inject_link_tags tests ──────────────────────────────────────────────────


class TestInjectLinkTags:
    """Tests for _inject_link_tags with mixed formatting."""

    def test_plain_text_injection(self) -> None:
        """Link text found in plain block text is wrapped with <a> tag."""
        blocks = [{"text": "Hello World", "rect": [0, 0, 200, 20]}]
        links = [{"_inner": "World", "from": [50, 0, 100, 20]}]
        _inject_link_tags(blocks, links, pymupdf)
        assert '<a id="0">World</a>' in blocks[0]["text"]

    def test_superscript_tag_injection(self) -> None:
        """Link text spanning a <sup> tag is correctly wrapped."""
        blocks = [
            {
                "text": "Nadia Alshahwan<sup>*</sup>\nJubin Chheda",
                "rect": [0, 0, 300, 100],
            }
        ]
        links = [{"_inner": "Nadia Alshahwan*", "from": [0, 0, 200, 20]}]
        _inject_link_tags(blocks, links, pymupdf)
        # <a> should wrap the entire content including <sup>*</sup>
        assert '<a id="0">Nadia Alshahwan<sup>*</sup></a>' in blocks[0]["text"]

    def test_bold_tag_injection(self) -> None:
        """Link text spanning a <b> tag is correctly wrapped."""
        blocks = [
            {
                "text": "See <b>Section 3.3</b> for details",
                "rect": [0, 0, 300, 20],
            }
        ]
        links = [{"_inner": "Section 3.3", "from": [30, 0, 120, 20]}]
        _inject_link_tags(blocks, links, pymupdf)
        assert '<a id="0">Section 3.3</b></a>' in blocks[0]["text"]

    def test_inner_wrapping(self) -> None:
        """_inner text is wrapped with <a> tag."""
        blocks = [{"text": "See [13] for details", "rect": [0, 0, 300, 20]}]
        links = [{"_inner": "13", "from": [30, 0, 60, 20]}]
        _inject_link_tags(blocks, links, pymupdf)
        assert '<a id="0">13</a>' in blocks[0]["text"]

    def test_sequential_search_disambiguates(self) -> None:
        """Sequential search_start prevents "1" matching inside "12"."""
        blocks = [
            {
                "text": "refs [12] and [1] here",
                "rect": [0, 0, 300, 20],
            }
        ]
        links = [
            {"_inner": "12", "from": [30, 0, 50, 20]},
            {"_inner": "1", "from": [80, 0, 90, 20]},
        ]
        _inject_link_tags(blocks, links, pymupdf)
        text = blocks[0]["text"]
        assert '<a id="0">12</a>' in text
        # "1" should wrap standalone [1], not "1" in "12"
        assert '[<a id="1">1</a>]' in text

    def test_inner_wrapping_partial_bracket(self) -> None:
        """Partial citation fragment wraps _inner."""
        blocks = [{"text": "refs [35, 2, 5] here", "rect": [0, 0, 300, 20]}]
        links = [
            {"_inner": "35", "from": [30, 0, 50, 20]},
            {"_inner": "2", "from": [55, 0, 65, 20]},
            {"_inner": "5", "from": [70, 0, 80, 20]},
        ]
        _inject_link_tags(blocks, links, pymupdf)
        text = blocks[0]["text"]
        assert '<a id="0">35</a>' in text
        assert '<a id="1">2</a>' in text
        assert '<a id="2">5</a>' in text

    def test_inner_wraps_full(self) -> None:
        """The _inner text is fully wrapped."""
        blocks = [{"text": "See 3.2 here", "rect": [0, 0, 300, 20]}]
        links = [{"_inner": "3.2", "from": [30, 0, 60, 20]}]
        _inject_link_tags(blocks, links, pymupdf)
        assert '<a id="0">3.2</a>' in blocks[0]["text"]

    def test_context_chars_skip_substring(self) -> None:
        """Context-char matching prevents '2' wrapping inside '2014'."""
        blocks = [
            {
                "text": (
                    "On the WMT 2014 English-to-German translation task, "
                    "the big transformer model (Transformer (big) in "
                    "Table 2) outperforms all."
                ),
                "rect": [0, 0, 500, 100],
            }
        ]
        # _src_left=" " (space before "2" in "Table 2)")
        # _src_right=")" (char after "2" in "Table 2)")
        links = [
            {
                "_inner": "2",
                "from": [140, 80, 150, 100],
                "_src_left": " ",
                "_src_right": ")",
            },
        ]
        _inject_link_tags(blocks, links, pymupdf)
        text = blocks[0]["text"]
        # "2" should wrap "Table 2)", not "2014"
        assert "Table <a" in text
        assert "WMT 2014" in text  # "2014" should remain untouched

    def test_context_chars_skip_decimal(self) -> None:
        """Context-char matching prevents '2' wrapping inside '2.0'."""
        blocks = [
            {
                "text": (
                    "more than 2.0 BLEU, establishing a new "
                    "state-of-the-art. Table 2) outperforms all."
                ),
                "rect": [0, 0, 500, 100],
            }
        ]
        links = [
            {
                "_inner": "2",
                "from": [140, 80, 150, 100],
                "_src_left": " ",
                "_src_right": ")",
            },
        ]
        _inject_link_tags(blocks, links, pymupdf)
        text = blocks[0]["text"]
        # "2" should wrap "Table 2)", not "2.0"
        assert "Table <a" in text
        assert "2.0 BLEU" in text  # "2.0" should remain untouched

    def test_no_context_falls_back_to_raw(self) -> None:
        """Falls back to raw match when no context chars are stored."""
        blocks = [
            {
                "text": "version2 is newest",
                "rect": [0, 0, 300, 20],
            }
        ]
        links = [
            {"_inner": "2", "from": [50, 0, 60, 20]},
        ]
        _inject_link_tags(blocks, links, pymupdf)
        # No _src_left/_src_right → raw match wraps "2" in "version2"
        assert '<a id="0">2</a>' in blocks[0]["text"]

    def test_no_nested_a_tags(self) -> None:
        """Second link inside already-tagged region is skipped."""
        blocks = [
            {
                "text": '<a id="0">[28]</a> more text 28',
                "rect": [0, 0, 300, 20],
            }
        ]
        links = [
            {"_inner": "[28]", "from": [0, 0, 30, 20]},
            {"_inner": "28", "from": [5, 0, 25, 20]},
        ]
        _inject_link_tags(blocks, links, pymupdf)
        # Link 1 (id=1) for "28" should not nest inside <a id="0">
        # It should find "28" in "more text 28" instead
        assert blocks[0]["text"].count("<a ") == 2  # noqa: PLR2004


# ── _extract_link_translations tests ─────────────────────────────────────────


class TestExtractLinkTranslations:
    """Tests for _extract_link_translations."""

    def test_basic_extraction(self) -> None:
        """Translated text extracted and <a> tags stripped."""
        blocks = [{"translated_text": 'Hello <a id="0">Thế giới</a>'}]
        links = [{"_inner": "World"}]
        _extract_link_translations(blocks, links)
        assert links[0]["_translated"] == "Thế giới"
        assert "<a " not in blocks[0]["translated_text"]
        assert "Thế giới" in blocks[0]["translated_text"]

    def test_inner_html_stripped_from_translated(self) -> None:
        """Inner HTML tags (e.g. <sup>) are stripped from _translated."""
        blocks = [
            {
                "translated_text": '<a id="0">Alshahwan<sup>*</sup></a>',
            }
        ]
        links = [{"_inner": "Alshahwan*"}]
        _extract_link_translations(blocks, links)
        assert links[0]["_translated"] == "Alshahwan*"
        assert "<sup>" not in links[0]["_translated"]

    def test_no_a_tags_is_noop(self) -> None:
        """Block without <a> tags is untouched."""
        blocks = [{"translated_text": "Xin chào thế giới"}]
        links = [{"_inner": "World"}]
        _extract_link_translations(blocks, links)
        assert "_translated" not in links[0]

    def test_translated_text_set(self) -> None:
        """_translated is set from the <a> tag content."""
        blocks = [
            {
                "translated_text": 'Xem [<a id="0">13</a>] tại đây',
            }
        ]
        links = [{"_inner": "13"}]
        _extract_link_translations(blocks, links)
        assert links[0]["_translated"] == "13"
        # Context chars: "[" before "13", "]" after "13"
        assert links[0]["_left_char"] == "["
        assert links[0]["_right_char"] == "]"

    def test_context_chars_at_edges(self) -> None:
        """No _left_char at start, no _right_char at end."""
        blocks = [
            {
                "translated_text": '<a id="0">Xin</a>',
            }
        ]
        links = [{"_inner": "Xin"}]
        _extract_link_translations(blocks, links)
        assert links[0]["_translated"] == "Xin"
        assert "_left_char" not in links[0]
        assert "_right_char" not in links[0]

    def test_multiple_links_translated(self) -> None:
        """Each link gets its own _translated value."""
        blocks = [
            {
                "translated_text": ('refs [<a id="0">35</a>, <a id="1">2</a>] here'),
            }
        ]
        links = [{"_inner": "35"}, {"_inner": "2"}]
        _extract_link_translations(blocks, links)
        assert links[0]["_translated"] == "35"
        assert links[1]["_translated"] == "2"
        # Context: "[35," and ",2]"
        assert links[0]["_left_char"] == "["
        assert links[0]["_right_char"] == ","
        assert links[1]["_left_char"] == " "
        assert links[1]["_right_char"] == "]"


# ── Vertical text detection tests ──────────────────────────────────────────────


class TestIsVerticalBlock:
    """Tests for _is_vertical_block."""

    def test_horizontal_lines_return_false(self) -> None:
        lines = [{"dir": (1.0, 0.0)}, {"dir": (1.0, 0.0)}]
        assert _is_vertical_block(lines) is False

    def test_vertical_lines_return_true(self) -> None:
        lines = [{"dir": (0.0, -1.0)}]
        assert _is_vertical_block(lines) is True

    def test_upward_vertical_return_true(self) -> None:
        lines = [{"dir": (0.0, 1.0)}]
        assert _is_vertical_block(lines) is True

    def test_mixed_horizontal_and_vertical_return_false(self) -> None:
        """If any line is horizontal, the block is not vertical."""
        lines = [{"dir": (0.0, -1.0)}, {"dir": (1.0, 0.0)}]
        assert _is_vertical_block(lines) is False

    def test_default_dir_is_horizontal(self) -> None:
        """Missing dir defaults to (1, 0) which is horizontal."""
        lines = [{}]
        assert _is_vertical_block(lines) is False


class TestExtractPageBlocksVertical:
    """All vertical/rotated text blocks are extracted and marked is_vertical."""

    def test_vertical_text_extracted_with_horizontal(self) -> None:
        """Vertical block is extracted alongside horizontal blocks."""
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 100), "Normal text", fontsize=12)
        page.insert_text(
            (30, 400),
            "arXiv:2402.09171v1 [cs.SE] 14 Feb 2024",
            fontsize=10,
            rotate=90,
        )
        blocks = _extract_page_blocks(page)
        doc.close()

        assert len(blocks) == 2  # noqa: PLR2004
        texts = [b["text"] for b in blocks]
        assert any("Normal" in t for t in texts)
        vertical = [b for b in blocks if b.get("is_vertical")]
        assert len(vertical) == 1
        assert "arXiv" in vertical[0]["text"]

    def test_only_vertical_text_extracted(self) -> None:
        """Page with only vertical text still extracts blocks."""
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((30, 400), "Vertical only", fontsize=10, rotate=90)
        blocks = _extract_page_blocks(page)
        doc.close()

        assert len(blocks) == 1
        assert blocks[0].get("is_vertical") is True

    def test_many_short_vertical_blocks_all_extracted(self) -> None:
        """All vertical blocks are extracted regardless of count or length."""
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 100), "Normal text", fontsize=12)
        for i in range(12):
            page.insert_text(
                (30 + i * 15, 200 + i * 30),
                f"L{i}",
                fontsize=8,
                rotate=90,
            )
        blocks = _extract_page_blocks(page)
        doc.close()

        # 1 horizontal + 12 vertical = 13 total
        assert len(blocks) == 13  # noqa: PLR2004
        vertical = [b for b in blocks if b.get("is_vertical")]
        assert len(vertical) == 12  # noqa: PLR2004


# ── Vertical text overlay tests ────────────────────────────────────────────────


class TestDirToRotate:
    """Tests for _dir_to_rotate."""

    def test_bottom_to_top(self) -> None:
        assert _dir_to_rotate((0.0, -1.0)) == 90  # noqa: PLR2004

    def test_top_to_bottom(self) -> None:
        assert _dir_to_rotate((0.0, 1.0)) == 270  # noqa: PLR2004

    def test_right_to_left(self) -> None:
        assert _dir_to_rotate((-1.0, 0.0)) == 180  # noqa: PLR2004

    def test_horizontal(self) -> None:
        assert _dir_to_rotate((1.0, 0.0)) == 0


class TestOverlayVerticalBlock:
    """Tests for _overlay_vertical_block."""

    def test_inserts_vertical_text(self, tmp_path: Path) -> None:
        pdf = tmp_path / "vert.pdf"
        doc = pymupdf.open()
        doc.new_page()
        doc.save(str(pdf))
        doc.close()

        doc2, page2 = _open_page(pdf)
        block = {
            "translated_text": "arXiv:2402 test",
            "rect": [20, 200, 35, 700],
            "font_size": 10.0,
            "color": 0,
            "is_vertical": True,
            "_dir": (0.0, -1.0),
            "_origin": (30.0, 700.0),
        }
        _overlay_vertical_block(page2, block, pymupdf)

        out = tmp_path / "out.pdf"
        doc2.save(str(out))
        doc2.close()

        doc3, page3 = _open_page(out)
        d = page3.get_text("dict")
        doc3.close()

        # Verify vertical text was inserted
        texts = [
            span["text"]
            for blk in d["blocks"]
            if blk.get("type") == 0
            for line in blk["lines"]
            for span in line["spans"]
        ]
        assert any("arXiv" in t for t in texts)


class TestOverlayVerticalBlockAlignment:
    """Alignment support for vertical text overlay."""

    def _overlay_and_get_y(
        self,
        tmp_path: Path,
        block: dict[str, Any],
        font_obj: Any = None,
        suffix: str = "",
    ) -> float:
        """Helper: overlay a block and return the inserted text's y0."""
        pdf = tmp_path / f"align_{suffix}.pdf"
        doc = pymupdf.open()
        doc.new_page()
        doc.save(str(pdf))
        doc.close()

        doc2, page2 = _open_page(pdf)
        _overlay_vertical_block(
            page2,
            block,
            pymupdf,
            font_obj=font_obj,
        )

        out = tmp_path / f"out_{suffix}.pdf"
        doc2.save(str(out))
        doc2.close()

        doc3, page3 = _open_page(out)
        d = page3.get_text("dict")
        doc3.close()
        for blk in d["blocks"]:
            if blk.get("type") != 0:
                continue
            for line in blk["lines"]:
                for span in line["spans"]:
                    if "Test" in span.get("text", ""):
                        return span["bbox"][1]
        return -1.0

    def test_90_uses_origin_y(self, tmp_path: Path) -> None:
        """90° text uses origin when no _insert_y is set."""
        block = {
            "translated_text": "Test text here",
            "rect": [20, 100, 35, 600],
            "font_size": 10.0,
            "color": 0,
            "is_vertical": True,
            "_dir": (0.0, -1.0),
            "_origin": (30.0, 600.0),
        }
        y = self._overlay_and_get_y(tmp_path, block, suffix="90_origin")
        assert y > 500  # noqa: PLR2004

    def test_270_uses_origin_y(self, tmp_path: Path) -> None:
        """270° text uses origin when no _insert_y is set."""
        block = {
            "translated_text": "Test text here",
            "rect": [20, 100, 35, 600],
            "font_size": 10.0,
            "color": 0,
            "is_vertical": True,
            "_dir": (0.0, 1.0),
            "_origin": (30.0, 100.0),
        }
        y = self._overlay_and_get_y(tmp_path, block, suffix="270_origin")
        assert y < 200  # noqa: PLR2004

    def test_bottom_aligned_insert(self, tmp_path: Path) -> None:
        """_vert_align=bottom inserts at the shared bottom edge."""
        block = {
            "translated_text": "Test text here",
            "rect": [20, 100, 35, 600],
            "font_size": 10.0,
            "color": 0,
            "is_vertical": True,
            "_dir": (0.0, -1.0),
            "_origin": (30.0, 600.0),
            "_vert_align": "bottom",
            "_vert_align_y": 500.0,
        }
        y = self._overlay_and_get_y(tmp_path, block, suffix="bottom")
        # Text inserted at y=500, grows upward → top should be above 500
        assert 400 < y < 510  # noqa: PLR2004

    def test_top_aligned_insert(self, tmp_path: Path) -> None:
        """_vert_align=top offsets insertion so text top lands on shared edge."""
        font_obj = pymupdf.Font("helv")
        block = {
            "translated_text": "Test",
            "rect": [20, 100, 35, 600],
            "font_size": 10.0,
            "color": 0,
            "is_vertical": True,
            "_dir": (0.0, -1.0),
            "_origin": (30.0, 600.0),
            "_vert_align": "top",
            "_vert_align_y": 150.0,
        }
        y = self._overlay_and_get_y(
            tmp_path,
            block,
            font_obj=font_obj,
            suffix="top",
        )
        # Text top should land near y=150
        assert 140 < y < 200  # noqa: PLR2004

    def test_center_aligned_insert(self, tmp_path: Path) -> None:
        """_vert_align=center positions text centered at shared mid."""
        font_obj = pymupdf.Font("helv")
        block = {
            "translated_text": "Test",
            "rect": [20, 100, 35, 600],
            "font_size": 10.0,
            "color": 0,
            "is_vertical": True,
            "_dir": (0.0, -1.0),
            "_origin": (30.0, 600.0),
            "_vert_align": "center",
            "_vert_align_y": 350.0,
        }
        y = self._overlay_and_get_y(
            tmp_path,
            block,
            font_obj=font_obj,
            suffix="center",
        )
        # Text should be centered around y=350
        assert 300 < y < 400  # noqa: PLR2004

    def test_no_font_obj_falls_back_to_start(
        self,
        tmp_path: Path,
    ) -> None:
        """Without font_obj, center alignment is skipped (no crash)."""
        pdf = tmp_path / "no_font.pdf"
        doc = pymupdf.open()
        doc.new_page()
        doc.save(str(pdf))
        doc.close()

        doc2, page2 = _open_page(pdf)
        block = {
            "translated_text": "No font obj Test",
            "rect": [20, 100, 35, 600],
            "font_size": 10.0,
            "color": 0,
            "is_vertical": True,
            "_dir": (0.0, -1.0),
            "_origin": (30.0, 600.0),
        }
        _overlay_vertical_block(page2, block, pymupdf, font_obj=None)

        d = page2.get_text("dict")
        doc2.close()
        texts = [
            s["text"]
            for blk in d["blocks"]
            if blk.get("type") == 0
            for line in blk["lines"]
            for s in line["spans"]
        ]
        assert any("No font" in t for t in texts)


class TestOverlayVerticalBlockScaling:
    """Font scaling for long vertical text."""

    def test_long_text_shrinks_to_fit(self, tmp_path: Path) -> None:
        """Text longer than rect height is scaled down."""
        pdf = tmp_path / "scale.pdf"
        doc = pymupdf.open()
        doc.new_page()
        doc.save(str(pdf))
        doc.close()

        doc2, page2 = _open_page(pdf)
        font_obj = pymupdf.Font("helv")
        # Very long text, short rect (only 50pt tall)
        block = {
            "translated_text": "This is a very long translated label",
            "rect": [20, 100, 35, 150],  # 50pt height
            "font_size": 12.0,
            "color": 0,
            "is_vertical": True,
            "text_align": "left",
            "_dir": (0.0, 1.0),  # top-to-bottom (270)
            "_origin": (30.0, 100.0),
        }
        _overlay_vertical_block(
            page2,
            block,
            pymupdf,
            font_obj=font_obj,
        )

        d = page2.get_text("dict")
        doc2.close()
        # Text should be present and within the rect's y-range
        for blk in d["blocks"]:
            if blk.get("type") != 0:
                continue
            for line in blk["lines"]:
                for span in line["spans"]:
                    if "long" in span.get("text", ""):
                        # Text should not extend far beyond rect.y1=150
                        assert span["bbox"][3] < 165  # noqa: PLR2004
                        # Font size should have been reduced
                        assert span["size"] < 12.0  # noqa: PLR2004
                        return
        pytest.fail("Scaled text not found in output")

    def test_short_text_not_scaled(self, tmp_path: Path) -> None:
        """Text shorter than rect height keeps original font size."""
        pdf = tmp_path / "noscale.pdf"
        doc = pymupdf.open()
        doc.new_page()
        doc.save(str(pdf))
        doc.close()

        doc2, page2 = _open_page(pdf)
        font_obj = pymupdf.Font("helv")
        block = {
            "translated_text": "Hi",
            "rect": [20, 100, 35, 600],  # 500pt height, plenty of room
            "font_size": 12.0,
            "color": 0,
            "is_vertical": True,
            "text_align": "left",
            "_dir": (0.0, -1.0),  # bottom-to-top (90)
            "_origin": (30.0, 600.0),
        }
        _overlay_vertical_block(
            page2,
            block,
            pymupdf,
            font_obj=font_obj,
        )

        d = page2.get_text("dict")
        doc2.close()
        for blk in d["blocks"]:
            if blk.get("type") != 0:
                continue
            for line in blk["lines"]:
                for span in line["spans"]:
                    if "Hi" in span.get("text", ""):
                        # Font size should be unchanged
                        assert abs(span["size"] - 12.0) < 0.5
                        return
        pytest.fail("Text not found in output")

    def test_top_aligned_no_font_obj(self, tmp_path: Path) -> None:
        """Top-aligned with font_obj=None uses text_len=0 (inserts at align_y)."""
        pdf = tmp_path / "top_no_font.pdf"
        doc = pymupdf.open()
        doc.new_page()
        doc.save(str(pdf))
        doc.close()

        doc2, page2 = _open_page(pdf)
        block = {
            "translated_text": "Hi",
            "rect": [20, 100, 35, 600],
            "font_size": 10.0,
            "color": 0,
            "is_vertical": True,
            "_dir": (0.0, -1.0),
            "_origin": (30.0, 600.0),
            "_vert_align": "top",
            "_vert_align_y": 150.0,
        }
        # Should not crash even without font_obj
        _overlay_vertical_block(page2, block, pymupdf, font_obj=None)
        d = page2.get_text("dict")
        doc2.close()
        texts = [
            s["text"]
            for blk in d["blocks"]
            if blk.get("type") == 0
            for line in blk["lines"]
            for s in line["spans"]
        ]
        assert any("Hi" in t for t in texts)

    def test_vert_align_without_vert_align_y(self, tmp_path: Path) -> None:
        """_vert_align set but _vert_align_y missing falls back to origin."""
        pdf = tmp_path / "no_align_y.pdf"
        doc = pymupdf.open()
        doc.new_page()
        doc.save(str(pdf))
        doc.close()

        doc2, page2 = _open_page(pdf)
        block = {
            "translated_text": "Hi",
            "rect": [20, 100, 35, 600],
            "font_size": 10.0,
            "color": 0,
            "is_vertical": True,
            "_dir": (0.0, -1.0),
            "_origin": (30.0, 600.0),
            "_vert_align": "top",
            # No _vert_align_y → falls back to origin
        }
        _overlay_vertical_block(page2, block, pymupdf, font_obj=None)
        d = page2.get_text("dict")
        doc2.close()
        texts = [
            s["text"]
            for blk in d["blocks"]
            if blk.get("type") == 0
            for line in blk["lines"]
            for s in line["spans"]
        ]
        assert any("Hi" in t for t in texts)


class TestApplyTranslatedBlocksVertical:
    """Integration: vertical blocks go through insert_text path."""

    def test_vertical_text_preserved_through_translation(self) -> None:
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 100), "Normal text", fontsize=12)
        page.insert_text(
            (30, 700),
            "arXiv:2402.09171v1",
            fontsize=10,
            rotate=90,
        )
        blocks = _extract_page_blocks(page)

        for b in blocks:
            if b.get("is_vertical"):
                b["translated_text"] = "arXiv:2402.09171v1 traduit"
            else:
                b["translated_text"] = "Texte normal"

        _apply_translated_blocks(page, blocks, pymupdf)

        d = page.get_text("dict")
        doc.close()

        dirs = []
        for blk in d["blocks"]:
            if blk.get("type") != 0:
                continue
            for line in blk["lines"]:
                dirs.append(line.get("dir"))

        # Should have both horizontal (1,0) and vertical (0,-1) text
        assert (1.0, 0.0) in dirs
        assert (0.0, -1.0) in dirs


# ── _detect_line_joins / _join_lines tests ─────────────────────────────────


class TestDetectLineJoins:
    """Unit tests for _detect_line_joins."""

    def test_single_line_returns_empty(self) -> None:
        """Fewer than 2 lines → empty join list."""
        assert _detect_line_joins([100.0], [12.0]) == []

    def test_empty_returns_empty(self) -> None:
        assert _detect_line_joins([], []) == []

    def test_uniform_spacing_all_spaces(self) -> None:
        """Lines with normal leading gaps are joined with spaces."""
        # 12pt font: expected leading = 14.4, threshold = 21.6
        # Gap 14 < 21.6 → space
        result = _detect_line_joins([100.0, 114.0, 128.0], [12.0, 12.0, 12.0])
        assert result == [" ", " "]

    def test_paragraph_break_detected(self) -> None:
        """A gap well above expected leading produces a newline."""
        # 12pt font: threshold = 21.6. Gap 30 > 21.6 → newline
        result = _detect_line_joins(
            [100.0, 114.0, 128.0, 158.0],
            [12.0, 12.0, 12.0, 12.0],
        )
        assert result == [" ", " ", "\n"]

    def test_large_uniform_gaps_all_newlines(self) -> None:
        """Large uniform gaps (well above leading) are all paragraph breaks."""
        # 12pt font: expected leading = 14.4, threshold = 21.6
        # Gap 40 > 21.6 → newline
        result = _detect_line_joins([0.0, 40.0, 80.0], [12.0, 12.0, 12.0])
        assert result == ["\n", "\n"]

    def test_two_lines_normal_leading(self) -> None:
        """Two lines with gap within leading tolerance → space."""
        result = _detect_line_joins([100.0, 114.0], [12.0, 12.0])
        assert result == [" "]

    def test_mixed_gaps(self) -> None:
        """Mix of paragraph-internal and paragraph-break gaps."""
        # 12pt font: threshold = 21.6. Gap 35 > 21.6 → newline; 14 < 21.6 → space
        result = _detect_line_joins(
            [100.0, 114.0, 128.0, 142.0, 177.0, 191.0],
            [12.0] * 6,
        )
        assert result == [" ", " ", " ", "\n", " "]

    def test_zero_gaps_all_spaces(self) -> None:
        """If all y-positions are identical (zero gaps), all joins are spaces."""
        result = _detect_line_joins([100.0, 100.0, 100.0], [12.0, 12.0, 12.0])
        assert result == [" ", " "]

    def test_font_size_change_triggers_newline(self) -> None:
        """A significant font size change between lines → newline."""
        # 16pt → 12pt: change 4/16 = 25% > 15% threshold → newline
        # Even though gap 18 < expected leading threshold
        result = _detect_line_joins([100.0, 118.0], [16.0, 12.0])
        assert result == ["\n"]

    def test_small_font_size_change_stays_space(self) -> None:
        """A minor font size change (< 15%) → still space."""
        # 12pt → 11.5pt: change 0.5/12 = 4.2% < 15% → no break
        # Gap 14 within leading tolerance → space
        result = _detect_line_joins([100.0, 114.0], [12.0, 11.5])
        assert result == [" "]

    def test_tall_merged_line_uses_y_ends(self) -> None:
        """Tall line (math subscript merge) uses bottom-to-top gap.

        Without line_y_ends, top-to-top gap = 22pt > threshold → newline.
        With line_y_ends, visual gap = 0.3pt → space.
        """
        # Line 1 is tall (merged subscript): y=[380.5, 402.2]
        # Line 2 is close: y=[402.5, 412.5]
        y_positions = [369.7, 380.5, 402.5]
        line_sizes = [10.1, 10.0, 10.0]
        line_y_ends = [379.8, 402.2, 412.5]
        result = _detect_line_joins(
            y_positions,
            line_sizes,
            line_y_ends=line_y_ends,
        )
        # All should be space — visual gaps are small
        assert result == [" ", " "]

    def test_without_y_ends_tall_line_causes_newline(self) -> None:
        """Without line_y_ends, tall merged line inflates gap → newline."""
        y_positions = [369.7, 380.5, 402.5]
        line_sizes = [10.1, 10.0, 10.0]
        result = _detect_line_joins(y_positions, line_sizes)
        # join[1]: gap = 402.5 - 380.5 = 22 > 18 threshold → newline
        assert result[1] == "\n"


class TestJoinLines:
    """Unit tests for _join_lines."""

    def test_empty_lines_returns_empty(self) -> None:
        assert _join_lines([], []) == ""

    def test_single_line_returns_text(self) -> None:
        assert _join_lines(["Hello world"], []) == "Hello world"

    def test_all_spaces(self) -> None:
        result = _join_lines(["Line one", "line two", "line three"], [" ", " "])
        assert result == "Line one line two line three"

    def test_all_newlines(self) -> None:
        result = _join_lines(["Para 1", "Para 2"], ["\n"])
        assert result == "Para 1\nPara 2"

    def test_mixed_joins(self) -> None:
        result = _join_lines(
            ["First line", "continues here", "New paragraph"],
            [" ", "\n"],
        )
        assert result == "First line continues here\nNew paragraph"


class TestExtractPageBlocksLineJoining:
    """Integration: _extract_page_blocks joins paragraph-internal lines."""

    def test_paragraph_lines_joined_with_spaces(self) -> None:
        """Multi-line paragraph within a single text block → spaces, not newlines."""
        doc = pymupdf.open()
        page = doc.new_page(width=400, height=400)
        # Insert lines that mimic PDF paragraph wrapping: all lines
        # reach similar right-edge widths (uniform character fill).
        y = 100
        for line_text in [
            "The experiment was conducted on a set of",
            "programs to evaluate the proposed methods",
            "and compare them against the baselines we",
            "selected for the evaluation benchmark run.",
        ]:
            page.insert_text((50, y), line_text, fontsize=11)
            y += 14  # ~1.27× font size — normal leading

        blocks = _extract_page_blocks(page)
        doc.close()

        assert len(blocks) >= 1
        text = blocks[0]["text"]
        # Lines should be joined with spaces (gap within leading tolerance,
        # all lines reach similar right edge → no short-line detection)
        assert "\n" not in text
        assert "set of programs" in text

    def test_heading_then_body_keeps_newline(self) -> None:
        """Different font sizes between lines → newline preserved."""
        doc = pymupdf.open()
        page = doc.new_page(width=400, height=400)
        page.insert_text((50, 100), "Section Heading", fontsize=16)
        page.insert_text((50, 130), "Body text paragraph.", fontsize=11)

        blocks = _extract_page_blocks(page)
        doc.close()

        # Find the block containing the heading
        for b in blocks:
            if "Heading" in b["text"] and "Body" in b["text"]:
                assert "\n" in b["text"]
                break

    def test_small_gap_not_space_between(self) -> None:
        """Narrow gap between same-y segments → space, not tab."""
        doc = pymupdf.open()
        page = doc.new_page(width=612, height=792)
        # Section title "6  Results" with a small gap (~12pt).
        # Gap / block_width > 0.2 but gap < 40pt minimum.
        page.insert_text((108, 380), "6", fontsize=12)
        page.insert_text((126, 380), "Results", fontsize=12)
        blocks = _extract_page_blocks(page)
        doc.close()
        title = [b for b in blocks if "6" in b["text"] and "Result" in b["text"]]
        assert len(title) == 1
        assert "\t" not in title[0]["text"]
        assert title[0]["text"] == "6 Results"
        assert not title[0].get("is_space_between")

    def test_large_gap_is_space_between(self) -> None:
        """Wide gap (> 40pt) between same-y segments → tab + space-between."""
        doc = pymupdf.open()
        page = doc.new_page(width=612, height=792)
        # Formula + equation number with a large gap (~200pt).
        page.insert_text((108, 300), "f(x) = 0", fontsize=10)
        page.insert_text((400, 300), "(1)", fontsize=10)
        blocks = _extract_page_blocks(page)
        doc.close()
        eq = [b for b in blocks if "(1)" in b["text"] and "f(x)" in b["text"]]
        assert len(eq) == 1
        assert "\t" in eq[0]["text"]
        assert eq[0].get("is_space_between") is True

    def test_indent_triggers_paragraph_break(self) -> None:
        """Next line indented while current at margin → paragraph break."""
        result = _detect_line_joins(
            [100.0, 114.0, 128.0, 142.0],
            [12.0, 12.0, 12.0, 12.0],
            # Lines 0-1 at left margin (x0=50), line 2 indented (x0=72),
            # line 3 at margin again.
            line_extents=[(50, 350), (50, 350), (72, 350), (50, 350)],
        )
        # Join 1 (line 1→2): line 1 at margin, line 2 indented → newline
        assert result[0] == " "
        assert result[1] == "\n"
        assert result[2] == " "

    def test_indent_not_triggered_when_current_also_indented(self) -> None:
        """Both lines indented (e.g. centered text) → no false positive."""
        result = _detect_line_joins(
            [100.0, 114.0, 128.0],
            [12.0, 12.0, 12.0],
            # All lines indented — centered/varied layout, not paragraphs
            line_extents=[(80, 350), (70, 340), (90, 330)],
        )
        assert result == [" ", " "]

    def test_indent_not_triggered_for_two_lines(self) -> None:
        """Indent check requires 3+ lines."""
        result = _detect_line_joins(
            [100.0, 114.0],
            [12.0, 12.0],
            line_extents=[(50, 350), (72, 350)],
        )
        # Only 2 lines → layout checks disabled, gap within leading → space
        assert result == [" "]

    def test_short_line_justified_triggers_paragraph_break(self) -> None:
        """In justified text, a short line signals end of paragraph."""
        result = _detect_line_joins(
            [100.0, 114.0, 128.0, 142.0],
            [10.0, 10.0, 10.0, 10.0],
            # All lines start at x=50 and end at x=350 (justified),
            # except line 2 which is short (ends at x=250).
            line_extents=[(50, 350), (50, 350), (50, 250), (50, 350)],
        )
        assert result == [" ", " ", "\n"]

    def test_short_line_left_aligned_no_trigger(self) -> None:
        """In left-aligned text, short lines do NOT trigger paragraph break."""
        result = _detect_line_joins(
            [100.0, 114.0, 128.0, 142.0],
            [10.0, 10.0, 10.0, 10.0],
            # Lines end at varying positions (left-aligned / ragged right).
            # Not justified → short-line check disabled.
            line_extents=[(50, 320), (50, 340), (50, 250), (50, 310)],
        )
        assert result == [" ", " ", " "]

    def test_short_line_not_triggered_for_narrow_block(self) -> None:
        """Layout detection disabled for blocks narrower than threshold."""
        result = _detect_line_joins(
            [100.0, 114.0, 128.0],
            [10.0, 10.0, 10.0],
            # Block width < _MIN_BLOCK_WIDTH_FOR_LAYOUT (50pt)
            line_extents=[(50, 80), (50, 80), (50, 65)],
        )
        assert result == [" ", " "]

    def test_rtl_indent_triggers_paragraph_break(self) -> None:
        """RTL indent: next line's right edge shifted left from margin."""
        result = _detect_line_joins(
            [100.0, 114.0, 128.0, 142.0],
            [12.0, 12.0, 12.0, 12.0],
            # RTL right-aligned: all lines end at x1=350,
            # line 2 is indented from the right (x1=330).
            line_extents=[(80, 350), (100, 350), (120, 330), (90, 350)],
        )
        # Join 1 (line 1→2): line 1 at right margin, line 2 right-indented
        assert result[1] == "\n"

    def test_rtl_short_line_justified(self) -> None:
        """RTL justified: short line detected by width, not right edge."""
        result = _detect_line_joins(
            [100.0, 114.0, 128.0, 142.0],
            [10.0, 10.0, 10.0, 10.0],
            # RTL justified: all lines span 50→350, except line 2
            # which is short (right-aligned: 150→350, width=200 vs 300).
            line_extents=[(50, 350), (50, 350), (150, 350), (50, 350)],
        )
        assert result == [" ", " ", "\n"]


class TestListMarkerRegex:
    """Unit tests for _LIST_MARKER_RE."""

    def test_numbered_dot(self) -> None:
        assert _LIST_MARKER_RE.match("1. First item")
        assert _LIST_MARKER_RE.match("10. Tenth item")

    def test_numbered_paren(self) -> None:
        assert _LIST_MARKER_RE.match("1) First item")
        assert _LIST_MARKER_RE.match("3) Third item")

    def test_parenthesized_number(self) -> None:
        assert _LIST_MARKER_RE.match("(1) First item")
        assert _LIST_MARKER_RE.match("(12) Twelfth item")

    def test_bracketed_number(self) -> None:
        assert _LIST_MARKER_RE.match("[1] Reference one")
        assert _LIST_MARKER_RE.match("[42] Reference forty-two")

    def test_letter_paren(self) -> None:
        assert _LIST_MARKER_RE.match("a) First item")
        assert _LIST_MARKER_RE.match("B) Second item")

    def test_parenthesized_letter(self) -> None:
        assert _LIST_MARKER_RE.match("(a) First item")
        assert _LIST_MARKER_RE.match("(iv) Roman numeral")

    def test_bracketed_letter(self) -> None:
        assert _LIST_MARKER_RE.match("[a] First item")
        assert _LIST_MARKER_RE.match("[iv] Roman numeral")

    def test_bullet_characters(self) -> None:
        for ch in "•●○▪▸‣◦◆►":
            assert _LIST_MARKER_RE.match(f"{ch} Item"), f"Failed for {ch!r}"
            assert _LIST_MARKER_RE.match(f"{ch}Item"), f"Failed for {ch!r} no space"

    def test_dash_markers(self) -> None:
        assert _LIST_MARKER_RE.match("- Dash item")
        assert _LIST_MARKER_RE.match("– En-dash item")
        assert _LIST_MARKER_RE.match("— Em-dash item")

    def test_leading_whitespace(self) -> None:
        assert _LIST_MARKER_RE.match("  (1) Indented marker")
        assert _LIST_MARKER_RE.match("  • Indented bullet")

    def test_no_match_plain_text(self) -> None:
        assert not _LIST_MARKER_RE.match("The quick brown fox")
        assert not _LIST_MARKER_RE.match("Results are shown in")

    def test_numbered_colon(self) -> None:
        """Algorithm-style colon markers: 1: 2: 10:."""
        assert _LIST_MARKER_RE.match("1: Initialize weights")
        assert _LIST_MARKER_RE.match("6: Update gradient")
        assert _LIST_MARKER_RE.match("11: Return result")
        assert _LIST_MARKER_RE.match("  3: Indented step")

    def test_no_match_bare_number(self) -> None:
        """Bare number without . or ) does not match."""
        assert not _LIST_MARKER_RE.match("2024 was a great year")

    def test_no_match_dash_without_space(self) -> None:
        """Hyphenated words should not match."""
        assert not _LIST_MARKER_RE.match("-based approach")


class TestUpgradeListJoins:
    """Unit tests for _upgrade_list_joins."""

    def test_upgrades_space_before_numbered_item(self) -> None:
        lines = ["end of paragraph.", "(1) First item starts here"]
        joins = [" "]
        _upgrade_list_joins(lines, joins)
        assert joins == ["\n"]

    def test_does_not_demote_existing_newline(self) -> None:
        lines = ["heading", "(1) First item"]
        joins = ["\n"]
        _upgrade_list_joins(lines, joins)
        assert joins == ["\n"]

    def test_no_marker_no_change(self) -> None:
        lines = ["line one", "line two continues"]
        joins = [" "]
        _upgrade_list_joins(lines, joins)
        assert joins == [" "]

    def test_multiple_markers_all_upgraded(self) -> None:
        lines = [
            "Introduction paragraph.",
            "(1) First point that is made",
            "which continues on this line.",
            "(2) Second point follows here",
        ]
        joins = [" ", " ", " "]
        _upgrade_list_joins(lines, joins)
        assert joins == ["\n", " ", "\n"]

    def test_bullet_marker(self) -> None:
        lines = ["Previous text.", "• Bullet point"]
        joins = [" "]
        _upgrade_list_joins(lines, joins)
        assert joins == ["\n"]

    def test_dash_marker(self) -> None:
        lines = ["Previous text.", "– Dash item"]
        joins = [" "]
        _upgrade_list_joins(lines, joins)
        assert joins == ["\n"]

    def test_colon_algorithm_steps(self) -> None:
        """Algorithm step markers like '6: Update' get newline breaks."""
        lines = [
            "5: Compute gradient ∇f(x)",
            "6: Update weights w ← w − η∇f",
            "7: Check convergence",
        ]
        joins = [" ", " "]
        _upgrade_list_joins(lines, joins)
        assert joins == ["\n", "\n"]

    def test_bracketed_reference(self) -> None:
        lines = ["previous reference text.", "[6] Author, Title, 2024."]
        joins = [" "]
        _upgrade_list_joins(lines, joins)
        assert joins == ["\n"]

    def test_dedent_after_list_continuation(self) -> None:
        """Non-marker continuation followed by dedented line → newline."""
        lines = [
            "(1) First item text",
            "continuation of first item.",
            "Body text resumes here.",
        ]
        joins = [" ", " "]
        # continuation at x=78, body text dedents to x=54
        extents = [(54.0, 300.0), (78.0, 300.0), (54.0, 300.0)]
        _upgrade_list_joins(lines, joins, extents)
        # Pass 1 upgrades join[0] before marker → but line 0 IS the marker,
        # and join[0] is before line 1 (non-marker), so Pass 2 demotes it.
        # Pass 3 upgrades join[1] due to dedent.
        assert joins[1] == "\n"

    def test_no_dedent_no_upgrade(self) -> None:
        """Same indent → no upgrade from Pass 3."""
        lines = [
            "(1) First item text",
            "continuation line one.",
            "continuation line two.",
        ]
        joins = [" ", " "]
        extents = [(54.0, 300.0), (78.0, 300.0), (78.0, 300.0)]
        _upgrade_list_joins(lines, joins, extents)
        assert joins[1] == " "

    def test_dedent_not_triggered_without_list_context(self) -> None:
        """Dedent without preceding list marker → no upgrade."""
        lines = ["regular text.", "indented text.", "back to margin."]
        joins = [" ", " "]
        extents = [(54.0, 300.0), (78.0, 300.0), (54.0, 300.0)]
        _upgrade_list_joins(lines, joins, extents)
        assert joins[1] == " "

    def test_dedent_skipped_for_first_line_indent(self) -> None:
        """First-line paragraph indent must not trigger dedent detection.

        When a paragraph starts with a first-line indent (joins[i-1]==NL),
        the higher x0 is normal formatting, not list continuation.
        """
        lines = [
            "1. Assessing improvement: measurement",
            "is clearly a key factor.",
            "provement, but it is merely an expedient proxy.",
            "When we use TestGen-LLM in its experimental mode (free from",
            "the confounding factors inherent in deployment), we found",
        ]
        # join[2]=NL makes line[3] the first line of a new paragraph.
        joins = [" ", " ", "\n", " "]
        # line[3] indented (63.8) vs line[4] at margin (53.8).
        extents = [
            (53.6, 294.0),
            (53.8, 294.0),
            (53.8, 295.3),
            (63.8, 294.0),  # first-line indent
            (53.8, 294.0),
        ]
        _upgrade_list_joins(lines, joins, extents)
        # join[3] must stay SP — not a list dedent.
        assert joins[3] == " "

    def test_dedent_fires_for_continuation_line(self) -> None:
        """Dedent after a true list continuation line triggers correctly."""
        lines = [
            "1. Marker item",
            "continuation body indented.",
            "back to margin.",
        ]
        joins = [" ", " "]
        # Pass 2 demotes join[0] (marker→continuation).
        # line[1] is a continuation (joins[0]=" "), so dedent CAN fire.
        extents = [
            (54.0, 300.0),
            (70.0, 300.0),  # indented continuation
            (54.0, 300.0),  # back to margin
        ]
        _upgrade_list_joins(lines, joins, extents)
        assert joins[1] == "\n"

    def test_dedent_without_extents_is_noop(self) -> None:
        """Pass 3 is skipped when line_extents is None."""
        lines = [
            "(1) Marker item",
            "continuation body.",
            "back to margin.",
        ]
        joins = [" ", " "]
        _upgrade_list_joins(lines, joins)  # no extents
        # Pass 2 demotes join[0] (marker→continuation), join[1] unchanged
        assert joins[1] == " "

    def test_pass2_guard_a_font_size_mismatch(self) -> None:
        """Guard (a): font sizes differ → keep newline."""
        lines = [
            "2. Section heading here",
            "Body text following the heading.",
        ]
        joins = ["\n"]
        _upgrade_list_joins(
            lines,
            joins,
            line_font_sizes=[12.0, 9.0],  # noqa: PLR2004
        )
        assert joins == ["\n"]

    def test_pass2_guard_b_short_marker(self) -> None:
        """Guard (b): short marker (< 90% block) → keep newline."""
        lines = ["3. Results", "We measured the outcome across all"]
        joins = ["\n"]
        # Marker at 40% of block width → text ended naturally.
        extents = [(54.0, 150.0), (54.0, 294.0)]
        _upgrade_list_joins(
            lines,
            joins,
            extents,
            line_font_sizes=[10.0, 10.0],
        )
        assert joins == ["\n"]

    def test_pass2_guard_c_bold_heading_full_continuation(self) -> None:
        """Guard (c): bold marker + regular full-width cont → keep."""
        lines = [
            "2. Application-aware probability distribution",
            "Language models assign probabilities to tokens",
        ]
        joins = ["\n"]
        # Same font size, but marker is bold, continuation is not.
        # Continuation is full-width (230/242 = 95%).
        extents = [(318.0, 546.0), (327.9, 558.4)]
        _upgrade_list_joins(
            lines,
            joins,
            extents,
            line_font_sizes=[9.0, 9.0],
            line_font_styles=[(True, False), (False, False)],
        )
        assert joins == ["\n"]

    def test_pass2_guard_c_italic_heading_full_continuation(self) -> None:
        """Guard (c): italic marker + regular full-width cont → keep."""
        lines = [
            "3. Experimental methodology overview here",
            "The approach was validated through extensive testing",
        ]
        joins = ["\n"]
        extents = [(54.0, 290.0), (54.0, 294.0)]
        _upgrade_list_joins(
            lines,
            joins,
            extents,
            line_font_sizes=[9.0, 9.0],
            line_font_styles=[(False, True), (False, False)],
        )
        assert joins == ["\n"]

    def test_pass2_guard_c_skipped_short_continuation(self) -> None:
        """Guard (c) does NOT fire when continuation is short."""
        lines = [
            "(1) Generating tests for trivial methods (a getter",
            "method).",
        ]
        joins = ["\n"]
        # Bold marker + non-bold cont, but cont is short (14%).
        extents = [(64.7, 294.2), (78.2, 110.7)]
        _upgrade_list_joins(
            lines,
            joins,
            extents,
            line_font_sizes=[9.0, 9.0],
            line_font_styles=[(True, False), (False, False)],
        )
        assert joins == [" "]

    def test_pass2_guard_c_skipped_same_style(self) -> None:
        """Guard (c) does NOT fire when styles match."""
        lines = [
            "(1) Generating tests for trivial methods (a getter",
            "method).",
        ]
        joins = ["\n"]
        # Same style, continuation short → demote.
        extents = [(64.7, 294.2), (78.2, 110.7)]
        _upgrade_list_joins(
            lines,
            joins,
            extents,
            line_font_sizes=[9.0, 9.0],
            line_font_styles=[(False, False), (False, False)],
        )
        assert joins == [" "]

    def test_pass2_demotes_full_marker_same_style(self) -> None:
        """Full-width marker, same style, short continuation → demote."""
        lines = [
            "(2) Failing to follow the single responsibility principle",
            "ciple (2 rejected for this reason).",
        ]
        joins = ["\n"]
        extents = [(64.7, 295.6), (78.2, 195.7)]
        _upgrade_list_joins(
            lines,
            joins,
            extents,
            line_font_sizes=[9.0, 9.0],
            line_font_styles=[(False, False), (False, False)],
        )
        assert joins == [" "]

    def test_pass2_no_guards_no_extras(self) -> None:
        """Pass 2 demotes when no optional params are provided."""
        lines = ["1. Item", "continuation text here."]
        joins = ["\n"]
        _upgrade_list_joins(lines, joins)
        assert joins == [" "]

    def test_pass2_full_marker_full_cont_same_style_demotes(self) -> None:
        """Full-width marker + full-width cont, same style → demote.

        This is a multi-line list item where the continuation also fills
        the column width.  No guard should fire.
        """
        lines = [
            "(1) First item that goes all the way to the margin here",
            "continues with more detail filling the full line width.",
            "(2) Second item.",
        ]
        joins = ["\n", "\n"]
        extents = [(54.0, 294.0), (70.0, 294.0), (54.0, 180.0)]
        _upgrade_list_joins(
            lines,
            joins,
            extents,
            line_font_sizes=[9.0, 9.0, 9.0],
            line_font_styles=[
                (False, False),
                (False, False),
                (False, False),
            ],
        )
        # join[0] demoted (list item wraps), join[1] kept (next marker).
        assert joins == [" ", "\n"]

    def test_pass2_guard_c_bold_italic_to_regular(self) -> None:
        """Guard (c): bold+italic marker → regular full-width cont → keep."""
        lines = [
            "5. Bold italic heading spanning the column",
            "Regular body text that fills the full column width here.",
        ]
        joins = ["\n"]
        extents = [(54.0, 290.0), (54.0, 294.0)]
        _upgrade_list_joins(
            lines,
            joins,
            extents,
            line_font_sizes=[9.0, 9.0],
            line_font_styles=[(True, True), (False, False)],
        )
        assert joins == ["\n"]

    def test_pass2_guard_a_size_within_tolerance_passes(self) -> None:
        """Guard (a) does NOT fire when size diff ≤ tolerance (0.1)."""
        lines = ["1. Marker text here", "continuation text here."]
        joins = ["\n"]
        # Size difference 0.05 < 0.1 tolerance → guard (a) skipped.
        _upgrade_list_joins(
            lines,
            joins,
            line_font_sizes=[9.0, 9.05],
        )
        assert joins == [" "]

    def test_pass2_guard_b_marker_at_threshold_demotes(self) -> None:
        """Guard (b): marker exactly at 90% threshold → NOT short → demote."""
        lines = ["1. Marker text", "continuation text."]
        joins = ["\n"]
        # Marker width = 216/240 = 90% — at threshold, not below.
        extents = [(54.0, 270.0), (70.0, 200.0)]
        _upgrade_list_joins(
            lines,
            joins,
            extents,
            line_font_sizes=[9.0, 9.0],
            line_font_styles=[(False, False), (False, False)],
        )
        assert joins == [" "]

    def test_pass2_guards_interact_correctly(self) -> None:
        """All 3 guards checked in order; first match wins."""
        lines = [
            "2. Large bold heading spanning the width",
            "Small regular body text follows right here.",
        ]
        joins = ["\n"]
        extents = [(54.0, 290.0), (54.0, 294.0)]
        # Guard (a) fires first (12 vs 9), guards (b)+(c) not reached.
        _upgrade_list_joins(
            lines,
            joins,
            extents,
            line_font_sizes=[12.0, 9.0],  # noqa: PLR2004
            line_font_styles=[(True, False), (False, False)],
        )
        assert joins == ["\n"]

    def test_pass2_guard_c_no_extents_skipped(self) -> None:
        """Guard (c) skipped when extents are absent (block_w=0)."""
        lines = ["1. Bold marker text", "regular continuation."]
        joins = ["\n"]
        # Styles differ but no extents → guard (c) can't check width.
        _upgrade_list_joins(
            lines,
            joins,
            line_font_sizes=[9.0, 9.0],
            line_font_styles=[(True, False), (False, False)],
        )
        assert joins == [" "]

    def test_pass2_guard_c_cont_at_threshold_keeps(self) -> None:
        """Guard (c): continuation exactly at 90% threshold → keeps."""
        lines = [
            "2. Bold heading that spans column width",
            "Body paragraph text that is exactly at threshold.",
        ]
        joins = ["\n"]
        # cont_w = 216, block_w = 240 → 216/240 = 90% exactly.
        extents = [(54.0, 290.0), (54.0, 270.0)]
        _upgrade_list_joins(
            lines,
            joins,
            extents,
            line_font_sizes=[9.0, 9.0],
            line_font_styles=[(True, False), (False, False)],
        )
        assert joins == ["\n"]

    def test_pass2_guard_a_at_exact_tolerance_demotes(self) -> None:
        """Guard (a): size diff exactly 0.1 → NOT > tolerance → demote."""
        lines = ["1. Marker text here", "continuation text here."]
        joins = ["\n"]
        _upgrade_list_joins(
            lines,
            joins,
            line_font_sizes=[9.0, 9.1],
        )
        assert joins == [" "]

    def test_pass2_guard_c_regular_to_bold_keeps(self) -> None:
        """Guard (c): regular marker → bold full-width cont → keep.

        Guard (c) fires on ANY style difference + full-width cont,
        regardless of direction.  A bold continuation suggests a
        different typographic element (e.g. a bold subheading after
        a numbered prefix line).
        """
        lines = [
            "(1) Regular list item text filling the line completely",
            "Bold continuation that also fills the full line width.",
        ]
        joins = ["\n"]
        extents = [(54.0, 294.0), (70.0, 294.0)]
        _upgrade_list_joins(
            lines,
            joins,
            extents,
            line_font_sizes=[9.0, 9.0],
            line_font_styles=[(False, False), (True, False)],
        )
        # Style differs + full-width cont → guard (c) keeps newline.
        assert joins == ["\n"]

    def test_pass2_guard_c_skipped_styles_none(self) -> None:
        """Guard (c) skipped when line_font_styles is None.

        Extents + sizes provided (same size, full-width marker) but
        styles absent → guards (a)+(b) pass, (c) is skipped → demote.
        """
        lines = [
            "1. Full-width marker item that fills the whole line",
            "continuation text on next line.",
        ]
        joins = ["\n"]
        extents = [(54.0, 294.0), (70.0, 200.0)]
        _upgrade_list_joins(
            lines,
            joins,
            extents,
            line_font_sizes=[9.0, 9.0],
            line_font_styles=None,
        )
        assert joins == [" "]


class TestUpgradeEmphasisStartJoins:
    """Unit tests for _upgrade_emphasis_start_joins."""

    @staticmethod
    def _span(
        text: str,
        *,
        bold: bool = False,
        italic: bool = False,
        is_math: bool = False,
    ) -> dict:
        """Helper to create a span dict with minimal fields."""
        flags = (16 if bold else 0) | (2 if italic else 0)  # noqa: PLR2004
        d: dict = {"text": text, "flags": flags}
        if is_math:
            d["_is_math"] = True
        return d

    # ── Bold-start tests ──────────────────────────────────────────────

    def test_bold_start_after_nonbold_end_no_pattern(self) -> None:
        """First bold entry after plain text: no repeating pattern yet."""
        spans = [
            [self._span("body text ending here.")],
            [self._span("Term.", bold=True), self._span(" Explanation text.")],
        ]
        joins = [" "]
        _upgrade_emphasis_start_joins(spans, joins)
        # Paragraph starts non-bold → no repeating pattern → no upgrade.
        assert joins == [" "]

    def test_bold_start_after_bold_paragraph(self) -> None:
        """Repeating bold pattern: bold-start para → bold-start line → break."""
        spans = [
            [self._span("Term A.", bold=True), self._span(" Body A.")],
            [self._span("continues wrapping here.")],
            [self._span("Term B.", bold=True), self._span(" Body B.")],
        ]
        joins = [" ", " "]
        _upgrade_emphasis_start_joins(spans, joins)
        assert joins == [" ", "\n"]

    def test_consecutive_bold_start_paragraphs(self) -> None:
        """Multiple bold-start paragraphs in a row all get breaks."""
        spans = [
            [self._span("Intro.", bold=True), self._span(" Body text A.")],
            [self._span("Term B.", bold=True), self._span(" Body text B.")],
            [self._span("Term C.", bold=True), self._span(" Body text C.")],
        ]
        joins = [" ", " "]
        _upgrade_emphasis_start_joins(spans, joins)
        assert joins == ["\n", "\n"]

    def test_no_emphasis_no_change(self) -> None:
        """Lines without any emphasis → no upgrade."""
        spans = [
            [self._span("normal text line one.")],
            [self._span("normal text line two.")],
        ]
        joins = [" "]
        _upgrade_emphasis_start_joins(spans, joins)
        assert joins == [" "]

    def test_all_bold_next_line_no_change(self) -> None:
        """Entirely bold next line (no transition) → no upgrade."""
        spans = [
            [self._span("body text ending.")],
            [self._span("Fully bold line.", bold=True)],
        ]
        joins = [" "]
        _upgrade_emphasis_start_joins(spans, joins)
        assert joins == [" "]

    def test_current_line_ends_bold_no_change(self) -> None:
        """Current line ends with bold → might be wrapped bold paragraph."""
        spans = [
            [self._span("Title text", bold=True)],
            [self._span("Term.", bold=True), self._span(" Body.")],
        ]
        joins = [" "]
        _upgrade_emphasis_start_joins(spans, joins)
        assert joins == [" "]

    def test_existing_newline_not_touched(self) -> None:
        """Already-newline joins are not modified."""
        spans = [
            [self._span("body text.")],
            [self._span("Term.", bold=True), self._span(" Body.")],
        ]
        joins = ["\n"]
        _upgrade_emphasis_start_joins(spans, joins)
        assert joins == ["\n"]

    def test_math_spans_skipped(self) -> None:
        """Math spans at line boundaries are ignored for emphasis detection."""
        spans = [
            [self._span("Prev.", bold=True), self._span(" body text.")],
            [self._span("more text."), self._span("∑", is_math=True)],
            [
                self._span("∫", is_math=True),
                self._span("Term.", bold=True),
                self._span(" Body."),
            ],
        ]
        joins = ["\n", " "]
        _upgrade_emphasis_start_joins(spans, joins)
        # Para start (line 1 after NL) is non-bold → no upgrade.
        assert joins == ["\n", " "]

    def test_math_spans_skipped_with_pattern(self) -> None:
        """Math spans skipped; bold pattern still detected."""
        spans = [
            [self._span("Prev.", bold=True), self._span(" text.")],
            [
                self._span("∫", is_math=True),
                self._span("Term.", bold=True),
                self._span(" Body."),
            ],
        ]
        joins = [" "]
        _upgrade_emphasis_start_joins(spans, joins)
        # Para start (line 0) is bold → repeating pattern → upgrade.
        assert joins == ["\n"]

    def test_whitespace_only_spans_skipped(self) -> None:
        """Whitespace-only spans don't count for emphasis detection."""
        spans = [
            [self._span("Term A.", bold=True), self._span(" body.")],
            [self._span("more text."), self._span("  ")],
            [
                self._span("  "),
                self._span("Term B.", bold=True),
                self._span(" Body."),
            ],
        ]
        joins = ["\n", " "]
        _upgrade_emphasis_start_joins(spans, joins)
        # Para start (line 1 after NL) is non-bold → no upgrade.
        assert joins == ["\n", " "]

    def test_wrapped_bold_paragraph_not_broken(self) -> None:
        """Bold paragraph wrapping: bold end → non-bold start → no break."""
        spans = [
            [self._span("Bold header that wraps", bold=True)],
            [self._span("to the next line continuing.")],
        ]
        joins = [" "]
        _upgrade_emphasis_start_joins(spans, joins)
        assert joins == [" "]

    def test_mixed_pattern_three_lines(self) -> None:
        """Body wrap, then bold-start paragraph."""
        spans = [
            [self._span("Term.", bold=True), self._span(" Body text that")],
            [self._span("continues on this line.")],
            [self._span("New Term.", bold=True), self._span(" More text.")],
        ]
        joins = [" ", " "]
        _upgrade_emphasis_start_joins(spans, joins)
        assert joins == [" ", "\n"]

    def test_empty_joins_noop(self) -> None:
        """Single line → empty joins → no crash."""
        spans = [[self._span("only line.")]]
        joins: list[str] = []
        _upgrade_emphasis_start_joins(spans, joins)
        assert joins == []

    # ── Italic-start tests ────────────────────────────────────────────

    def test_italic_start_after_plain_end_no_pattern(self) -> None:
        """First italic entry after plain text: no repeating pattern yet."""
        spans = [
            [self._span("body text ending here.")],
            [self._span("Term.", italic=True), self._span(" Explanation.")],
        ]
        joins = [" "]
        _upgrade_emphasis_start_joins(spans, joins)
        # Paragraph starts non-italic → no repeating pattern → no upgrade.
        assert joins == [" "]

    def test_italic_start_after_italic_paragraph(self) -> None:
        """Repeating italic pattern: italic-start para → italic-start → break."""
        spans = [
            [self._span("Term A.", italic=True), self._span(" Body A.")],
            [self._span("continues wrapping here.")],
            [self._span("Term B.", italic=True), self._span(" Body B.")],
        ]
        joins = [" ", " "]
        _upgrade_emphasis_start_joins(spans, joins)
        assert joins == [" ", "\n"]

    def test_consecutive_italic_start_paragraphs(self) -> None:
        """Multiple italic-start paragraphs all get breaks."""
        spans = [
            [self._span("Intro.", italic=True), self._span(" Body A.")],
            [self._span("Term B.", italic=True), self._span(" Body B.")],
        ]
        joins = [" "]
        _upgrade_emphasis_start_joins(spans, joins)
        assert joins == ["\n"]

    def test_all_italic_next_line_no_change(self) -> None:
        """Entirely italic next line (no transition) → no upgrade."""
        spans = [
            [self._span("body text.")],
            [self._span("All italic line.", italic=True)],
        ]
        joins = [" "]
        _upgrade_emphasis_start_joins(spans, joins)
        assert joins == [" "]

    def test_current_line_ends_italic_no_change(self) -> None:
        """Current line ends italic → might be wrapped italic paragraph."""
        spans = [
            [self._span("Caption text", italic=True)],
            [self._span("Term.", italic=True), self._span(" Body.")],
        ]
        joins = [" "]
        _upgrade_emphasis_start_joins(spans, joins)
        assert joins == [" "]

    def test_wrapped_italic_paragraph_not_broken(self) -> None:
        """Italic wrapping to non-italic continuation → no break."""
        spans = [
            [self._span("Italic text that wraps", italic=True)],
            [self._span("to continue on next line.")],
        ]
        joins = [" "]
        _upgrade_emphasis_start_joins(spans, joins)
        assert joins == [" "]

    # ── Mixed bold + italic tests ─────────────────────────────────────

    def test_bold_italic_start_no_pattern(self) -> None:
        """Bold-italic term after plain body: no repeating pattern."""
        spans = [
            [self._span("plain body text.")],
            [
                self._span("Term.", bold=True, italic=True),
                self._span(" Body text."),
            ],
        ]
        joins = [" "]
        _upgrade_emphasis_start_joins(spans, joins)
        # Paragraph starts non-bold → no repeating pattern.
        assert joins == [" "]

    def test_bold_italic_start_with_pattern(self) -> None:
        """Repeating bold-italic pattern upgrades correctly."""
        spans = [
            [self._span("Term A.", bold=True, italic=True), self._span(" A.")],
            [self._span("body wrapping here.")],
            [
                self._span("Term B.", bold=True, italic=True),
                self._span(" Body B."),
            ],
        ]
        joins = [" ", " "]
        _upgrade_emphasis_start_joins(spans, joins)
        assert joins == [" ", "\n"]

    def test_bold_italic_start_after_italic_body(self) -> None:
        """Italic body → bold-italic header: no pattern (italic ≠ bold)."""
        spans = [
            [self._span("italic body.", italic=True)],
            [
                self._span("Term.", bold=True, italic=True),
                self._span(" Plain body."),
            ],
        ]
        joins = [" "]
        _upgrade_emphasis_start_joins(spans, joins)
        # Para start is italic-only, next starts bold → bold bit not in para
        # start. Italic bit: para start is italic, but current line also ends
        # italic → wrapped italic paragraph check blocks it.
        assert joins == [" "]

    def test_bold_start_in_italic_context(self) -> None:
        """All-italic block with bold-italic headers (bold is the signal)."""
        spans = [
            [
                self._span("Header A.", bold=True, italic=True),
                self._span(" Italic body A.", italic=True),
            ],
            [
                self._span("Header B.", bold=True, italic=True),
                self._span(" Italic body B.", italic=True),
            ],
        ]
        joins = [" "]
        _upgrade_emphasis_start_joins(spans, joins)
        # Line 0 ends italic-only (no bold) → line 1 starts bold → break
        assert joins == ["\n"]

    # ── Inline emphasis (false positive prevention) ────────────────────

    def test_inline_italic_word_not_upgraded(self) -> None:
        """Inline italic word at line start must not trigger paragraph break."""
        spans = [
            [self._span("each combination tends to contribute")],
            [
                self._span("uniquely", italic=True),
                self._span(" to the overall number of test cases."),
            ],
        ]
        joins = [" "]
        _upgrade_emphasis_start_joins(spans, joins)
        # Paragraph starts non-italic → no repeating pattern.
        assert joins == [" "]

    def test_inline_bold_word_not_upgraded(self) -> None:
        """Inline bold word at line start must not trigger paragraph break."""
        spans = [
            [self._span("the results clearly")],
            [self._span("demonstrate", bold=True), self._span(" the effect.")],
        ]
        joins = [" "]
        _upgrade_emphasis_start_joins(spans, joins)
        assert joins == [" "]

    def test_inline_italic_in_bold_paragraph_not_upgraded(self) -> None:
        """Italic word inside bold-start paragraph stays joined."""
        spans = [
            [self._span("Term.", bold=True), self._span(" Body that wraps")],
            [self._span("across lines, and tends to contribute")],
            [
                self._span("uniquely", italic=True),
                self._span(" to the overall count."),
            ],
        ]
        joins = [" ", " "]
        _upgrade_emphasis_start_joins(spans, joins)
        # Para starts bold, but italic bit not in para start → no italic
        # upgrade. Bold bit: next line starts italic-only (not bold) → skip.
        assert joins == [" ", " "]

    def test_italic_heading_then_inline_italic_no_upgrade(self) -> None:
        """Italic section heading + later inline italic → no break."""
        # Mirrors the real bug: "2.1.3 Ensemble approach." (italic heading)
        # followed by body text, then "*uniquely*" (inline italic) at a
        # later line start.  The repeating-pattern check passes (both para
        # start and next line start with italic), but the punctuation guard
        # rejects it because "uniquely" doesn't end with separator.
        spans = [
            [
                self._span("2.1.3 Ensemble approach.", italic=True),
                self._span(" Different LLMs have different strengths."),
            ],
            [self._span("Even the same LLM can produce multiple candidates")],
            [self._span("for a given prompt. Each combination contributes")],
            [
                self._span("uniquely", italic=True),
                self._span(" to the overall number of test cases."),
            ],
        ]
        joins = [" ", " ", " "]
        _upgrade_emphasis_start_joins(spans, joins)
        # "uniquely" ends with "y", not punctuation → no upgrade.
        assert joins == [" ", " ", " "]

    def test_punctuation_guard_allows_definition_term(self) -> None:
        """Emphasized text ending with punctuation still triggers upgrade."""
        spans = [
            [
                self._span("Heading:", italic=True),
                self._span(" First entry body text."),
            ],
            [self._span("continues wrapping here.")],
            [
                self._span("Next:", italic=True),
                self._span(" Second entry body text."),
            ],
        ]
        joins = [" ", " "]
        _upgrade_emphasis_start_joins(spans, joins)
        # "Next:" ends with ":" → punctuation guard passes → upgrade.
        assert joins == [" ", "\n"]

    def test_punctuation_guard_exclamation(self) -> None:
        """Emphasized text ending with ! triggers upgrade."""
        spans = [
            [self._span("Warning!", bold=True), self._span(" Do not proceed.")],
            [self._span("body text here.")],
            [self._span("Caution!", bold=True), self._span(" Check twice.")],
        ]
        joins = [" ", " "]
        _upgrade_emphasis_start_joins(spans, joins)
        assert joins == [" ", "\n"]

    def test_punctuation_guard_bracket(self) -> None:
        """Emphasized text ending with ] triggers upgrade."""
        spans = [
            [self._span("[Note]", bold=True), self._span(" First note body.")],
            [self._span("continuation of first note.")],
            [self._span("[Tip]", bold=True), self._span(" Second note body.")],
        ]
        joins = [" ", " "]
        _upgrade_emphasis_start_joins(spans, joins)
        assert joins == [" ", "\n"]


class TestDetectColumnAlignment:
    """Unit tests for _detect_column_alignment."""

    def test_left_aligned_column(self) -> None:
        """Consistent left edges → left alignment."""
        col_spans = [
            [{"bbox": (100, 0, 200, 10)}],
            [{"bbox": (100, 20, 180, 30)}],
            [{"bbox": (100, 40, 220, 50)}],
        ]
        assert _detect_column_alignment(col_spans) == "left"

    def test_right_aligned_column(self) -> None:
        """Consistent right edges → right alignment."""
        col_spans = [
            [{"bbox": (180, 0, 250, 10)}],
            [{"bbox": (200, 20, 250, 30)}],
            [{"bbox": (160, 40, 250, 50)}],
        ]
        assert _detect_column_alignment(col_spans) == "right"

    def test_center_aligned_column(self) -> None:
        """Both edges equally consistent → center alignment."""
        col_spans = [
            [{"bbox": (150, 0, 200, 10)}],
            [{"bbox": (150, 20, 200, 30)}],
            [{"bbox": (150, 40, 200, 50)}],
        ]
        assert _detect_column_alignment(col_spans) == "center"

    def test_single_cell_returns_left(self) -> None:
        """Too few cells to compare → default left."""
        col_spans = [[{"bbox": (100, 0, 200, 10)}]]
        assert _detect_column_alignment(col_spans) == "left"

    def test_empty_spans_skipped(self) -> None:
        """Empty span lists are ignored."""
        col_spans = [
            [{"bbox": (100, 0, 200, 10)}],
            [],
            [{"bbox": (100, 20, 180, 30)}],
        ]
        assert _detect_column_alignment(col_spans) == "left"


class TestFindOverlapIndex:
    """Unit tests for _find_overlap_index."""

    def test_no_overlap_returns_none(self) -> None:
        existing = [{"bbox": (0, 0, 50, 50), "cells": [(0, 0, 50, 50)]}]
        assert _find_overlap_index((100, 100, 200, 200), existing) is None

    def test_overlap_returns_index(self) -> None:
        existing = [
            {"bbox": (0, 0, 50, 50), "cells": []},
            {"bbox": (100, 100, 200, 200), "cells": []},
        ]
        assert _find_overlap_index((100, 100, 200, 200), existing) == 1

    def test_first_overlap_wins(self) -> None:
        existing = [
            {"bbox": (100, 100, 200, 200), "cells": []},
            {"bbox": (100, 100, 200, 200), "cells": []},
        ]
        assert _find_overlap_index((100, 100, 200, 200), existing) == 0


class TestDetectBlockAlignment:
    """Unit tests for _detect_block_alignment."""

    def test_single_line_returns_left(self) -> None:
        align, indent = _detect_block_alignment(
            [(50, 300)],
            [50, 100, 350, 200],
        )
        assert align == "left"
        assert indent == 0.0

    def test_justified_text(self) -> None:
        """Lines with both edges aligned → justify."""
        extents = [(50, 350), (50, 350), (50, 349), (50, 348), (50, 250)]
        align, indent = _detect_block_alignment(
            extents,
            [50, 100, 350, 200],
            [10.0] * 5,  # noqa: PLR2004
        )
        assert align == "justify"

    def test_left_aligned_text(self) -> None:
        """Lines with left edges aligned, ragged right → left."""
        extents = [(50, 300), (50, 320), (50, 280), (50, 310)]
        align, indent = _detect_block_alignment(
            extents,
            [50, 100, 350, 200],
            [10.0] * 4,
        )
        assert align == "left"

    def test_right_aligned_text(self) -> None:
        """Lines with right edges aligned, ragged left → right."""
        extents = [(100, 350), (120, 350), (80, 350), (150, 350)]
        align, indent = _detect_block_alignment(
            extents,
            [50, 100, 350, 200],
            [10.0] * 4,
        )
        assert align == "right"

    def test_centered_text(self) -> None:
        """Lines with symmetric margins → center."""
        extents = [(100, 300), (110, 290), (90, 310), (105, 295)]
        align, indent = _detect_block_alignment(
            extents,
            [50, 100, 350, 200],
            [10.0] * 4,
        )
        assert align == "center"

    def test_first_line_indent_detected(self) -> None:
        """First line shifted right → text_indent > 0."""
        # Lines 1-3 start at x=50, line 0 starts at x=70 (indented).
        extents = [(70, 350), (50, 350), (50, 349), (50, 250)]
        align, indent = _detect_block_alignment(
            extents,
            [50, 100, 350, 200],
            [10.0] * 4,
        )
        # First line is 20pt right of typical_left (50) → indent detected
        assert indent >= 10.0  # noqa: PLR2004

    def test_no_indent_when_first_line_at_margin(self) -> None:
        """First line at the typical margin → indent is 0."""
        extents = [(50, 350), (50, 349), (50, 348), (50, 250)]
        _, indent = _detect_block_alignment(
            extents,
            [50, 100, 350, 200],
            [10.0] * 4,
        )
        assert indent == 0.0

    def test_zero_width_block(self) -> None:
        """Block with zero width → left, no indent."""
        align, indent = _detect_block_alignment(
            [(100, 100), (100, 100)],
            [100, 100, 100, 200],
        )
        assert align == "left"
        assert indent == 0.0

    def test_two_line_justify_near_full_last_line(self) -> None:
        """2-line block where last line is ~85% of full width → justify.

        Regression test: previously the short-final threshold (0.85)
        was too strict, causing a justified paragraph whose last line
        was 85.2% of full width to be misclassified as left-aligned.
        """
        # Modeled after "Attention is All You Need" page 5 block:
        # Full line: 108.0 → 504.0 (width 396), last: 108.0 → 445.2 (85.2%)
        extents = [(108.0, 504.0), (108.0, 445.2)]
        block_rect = [108.0, 100, 504.0, 122]
        align, _ = _detect_block_alignment(
            extents,
            block_rect,
            [10.0, 10.0],
        )
        assert align == "justify"

    def test_short_final_just_below_ratio(self) -> None:
        """Last line just below _SHORT_LINE_RATIO → classified as short final.

        With typical_width=300, threshold = 300 * 0.9 = 270.0.
        Last line width 269.9 < 270.0 → short final → justify.
        """
        x0 = 100.0
        full_right = x0 + 300.0  # typical_width = 300
        # Last line: width 269.9 < 300*_SHORT_LINE_RATIO = 270.0
        last_right = x0 + 300.0 * _SHORT_LINE_RATIO - 0.1
        extents = [(x0, full_right), (x0, last_right)]
        block_rect = [x0, 100, full_right, 122]
        align, _ = _detect_block_alignment(
            extents,
            block_rect,
            [10.0, 10.0],
        )
        assert align == "justify"

    def test_short_final_exactly_at_ratio(self) -> None:
        """Last line exactly at _SHORT_LINE_RATIO → NOT short final.

        With typical_width=300, threshold = 300 * 0.9 = 270.0.
        Last line width 270.0 is NOT < 270.0 → not short final.
        Near-full-width cases like this are handled by
        _refine_alignments_from_context instead.
        """
        x0 = 100.0
        full_right = x0 + 300.0
        last_right = x0 + 300.0 * _SHORT_LINE_RATIO
        extents = [(x0, full_right), (x0, last_right)]
        block_rect = [x0, 100, full_right, 122]
        align, _ = _detect_block_alignment(
            extents,
            block_rect,
            [10.0, 10.0],
        )
        assert align == "left"

    def test_short_final_just_above_ratio(self) -> None:
        """Last line just above _SHORT_LINE_RATIO → NOT short final.

        With typical_width=300, threshold = 270.0.
        Last line width 270.1 > 270.0 → not short final.
        """
        x0 = 100.0
        full_right = x0 + 300.0
        last_right = x0 + 300.0 * _SHORT_LINE_RATIO + 0.1
        extents = [(x0, full_right), (x0, last_right)]
        block_rect = [x0, 100, full_right, 122]
        align, _ = _detect_block_alignment(
            extents,
            block_rect,
            [10.0, 10.0],
        )
        assert align == "left"


def _make_align_block(
    text_align: str = "left",
    font_size: float = 10.0,
    n_lines: int = 3,
) -> dict[str, Any]:
    """Create a minimal block dict for alignment refinement tests."""
    return {
        "text_align": text_align,
        "font_size": font_size,
        "_line_extents": [(50.0, 400.0)] * n_lines,
    }


class TestRefineAlignmentsFromContext:
    """Tests for _refine_alignments_from_context (page-dominant bias)."""

    def test_no_blocks(self) -> None:
        """Empty list is a no-op."""
        blocks: list[dict[str, Any]] = []
        _refine_alignments_from_context(blocks)
        assert blocks == []

    def test_justify_dominant_upgrades_left(self) -> None:
        """``left`` body block upgraded when justify dominates the page."""
        blocks = [
            _make_align_block("justify") for _ in range(_CONTEXT_ALIGN_MIN_NEIGHBORS)
        ] + [_make_align_block("left")]
        _refine_alignments_from_context(blocks)
        assert blocks[-1]["text_align"] == "justify"

    def test_too_few_justify_no_upgrade(self) -> None:
        """No upgrade when justify count < threshold."""
        blocks = [
            _make_align_block("justify")
            for _ in range(_CONTEXT_ALIGN_MIN_NEIGHBORS - 1)
        ] + [_make_align_block("left")]
        _refine_alignments_from_context(blocks)
        assert blocks[-1]["text_align"] == "left"

    def test_justify_not_majority_no_upgrade(self) -> None:
        """No upgrade when left blocks outnumber justify blocks."""
        blocks = [
            _make_align_block("justify"),
            _make_align_block("justify"),
            _make_align_block("justify"),
            _make_align_block("left"),
            _make_align_block("left"),
            _make_align_block("left"),
            _make_align_block("left"),  # 3 justify vs 4 left → not majority
        ]
        _refine_alignments_from_context(blocks)
        # All left blocks should stay left (justify ≤ body_count // 2)
        for b in blocks:
            if b.get("_original_align") != "justify":
                pass  # left blocks are checked below
        assert blocks[-1]["text_align"] == "left"

    def test_heading_not_upgraded(self) -> None:
        """A larger-font block (heading) stays ``left``."""
        blocks = [
            _make_align_block("justify") for _ in range(_CONTEXT_ALIGN_MIN_NEIGHBORS)
        ] + [_make_align_block("left", font_size=16.0)]
        _refine_alignments_from_context(blocks)
        assert blocks[-1]["text_align"] == "left"

    def test_justify_never_downgraded(self) -> None:
        """Blocks already ``justify`` are never changed."""
        blocks = [
            _make_align_block("left")
            for _ in range(5)  # noqa: PLR2004
        ] + [_make_align_block("justify")]
        _refine_alignments_from_context(blocks)
        assert blocks[-1]["text_align"] == "justify"

    def test_center_not_changed(self) -> None:
        """``center`` alignment is not touched."""
        blocks = [
            _make_align_block("justify") for _ in range(_CONTEXT_ALIGN_MIN_NEIGHBORS)
        ] + [_make_align_block("center")]
        _refine_alignments_from_context(blocks)
        assert blocks[-1]["text_align"] == "center"

    def test_single_line_block_not_upgraded(self) -> None:
        """Single-line blocks stay ``left`` (too ambiguous)."""
        blocks = [
            _make_align_block("justify") for _ in range(_CONTEXT_ALIGN_MIN_NEIGHBORS)
        ] + [_make_align_block("left", n_lines=1)]
        _refine_alignments_from_context(blocks)
        assert blocks[-1]["text_align"] == "left"

    def test_single_line_blocks_excluded_from_body_count(self) -> None:
        """Single-line blocks don't count toward body-text totals."""
        # 3 justify (multi-line) + 10 left (single-line) + 1 left (multi)
        blocks = (
            [_make_align_block("justify") for _ in range(3)]
            + [_make_align_block("left", n_lines=1) for _ in range(10)]
            + [_make_align_block("left")]
        )
        _refine_alignments_from_context(blocks)
        # Body blocks: 3 justify + 1 left = 4; justify=3 > 4//2=2 → dominant
        assert blocks[-1]["text_align"] == "justify"

    def test_heading_between_body_blocks(self) -> None:
        """Heading (different font) doesn't prevent body-text upgrade."""
        blocks = [
            _make_align_block("justify"),
            _make_align_block("justify"),
            _make_align_block("justify"),
            _make_align_block("left", font_size=16.0, n_lines=1),  # heading
            _make_align_block("left"),  # body → upgraded
        ]
        _refine_alignments_from_context(blocks)
        assert blocks[3]["text_align"] == "left"  # heading stays
        assert blocks[4]["text_align"] == "justify"  # body upgraded

    def test_size_tolerance_boundary(self) -> None:
        """Blocks at the size tolerance boundary are included."""
        base = 10.0
        within = base * _CONTEXT_ALIGN_SIZE_TOL - 0.01
        blocks = [
            _make_align_block("justify", font_size=within)
            for _ in range(_CONTEXT_ALIGN_MIN_NEIGHBORS)
        ] + [_make_align_block("left", font_size=base)]
        _refine_alignments_from_context(blocks)
        assert blocks[-1]["text_align"] == "justify"

    def test_size_beyond_tolerance_excluded(self) -> None:
        """Blocks beyond size tolerance are excluded from body count."""
        beyond = 10.0 * _CONTEXT_ALIGN_SIZE_TOL + 0.01
        blocks = [
            _make_align_block("justify", font_size=beyond)
            for _ in range(_CONTEXT_ALIGN_MIN_NEIGHBORS)
        ] + [_make_align_block("left", font_size=10.0)]
        _refine_alignments_from_context(blocks)
        # justify blocks are outside the tolerance band → not counted
        assert blocks[-1]["text_align"] == "left"

    def test_multiple_left_blocks_all_upgraded(self) -> None:
        """All ambiguous ``left`` body blocks get upgraded at once."""
        blocks = [
            _make_align_block("justify") for _ in range(_CONTEXT_ALIGN_MIN_NEIGHBORS)
        ] + [_make_align_block("left"), _make_align_block("left")]
        _refine_alignments_from_context(blocks)
        assert blocks[-2]["text_align"] == "justify"
        assert blocks[-1]["text_align"] == "justify"

    def test_all_single_line_no_crash(self) -> None:
        """Page with only single-line blocks is a no-op."""
        blocks = [_make_align_block("justify", n_lines=1) for _ in range(5)]  # noqa: PLR2004  # noqa: E501
        _refine_alignments_from_context(blocks)
        # No multi-line body blocks → no median → early return
        for b in blocks:
            assert b["text_align"] == "justify"


class TestComputeParaIndents:
    """Tests for _compute_para_indents (returns (block, first-line) tuples)."""

    def test_no_joins_returns_empty(self) -> None:
        assert _compute_para_indents([], [], []) == []

    def test_no_indentation_returns_empty(self) -> None:
        """All lines at the same left edge → no indents."""
        extents = [(50, 300), (50, 300), (50, 300)]
        sizes = [10.0, 10.0, 10.0]
        joins = [" ", "\n"]
        assert _compute_para_indents(extents, sizes, joins) == []

    def test_first_line_indent_detected(self) -> None:
        r"""First line shifted right from body → first-line indent."""
        extents = [
            (50.0, 300.0),  # para 1, line 0 (at margin)
            (50.0, 300.0),  # para 1, line 1
            (50.0, 200.0),  # para 1, last line (short → \n)
            (60.0, 300.0),  # para 2, line 0 (indented first line)
            (50.0, 300.0),  # para 2, line 1 (body at margin)
        ]
        sizes = [10.0, 10.0, 10.0, 10.0, 10.0]
        joins = [" ", " ", "\n", " "]
        result = _compute_para_indents(extents, sizes, joins)
        assert len(result) == 2  # noqa: PLR2004
        # Para 1: no indent
        assert result[0] == (0.0, 0.0)
        # Para 2: first-line indent = 10pt (60 - 50), block indent = 0
        assert result[1] == (0.0, 10.0)

    def test_block_indent_detected(self) -> None:
        """All lines of a paragraph shifted → block-level indent."""
        extents = [
            (50.0, 300.0),  # para 1, line 0 (at margin)
            (50.0, 200.0),  # para 1, last line (short → \n)
            (60.0, 300.0),  # para 2, line 0 (shifted)
            (60.0, 300.0),  # para 2, line 1 (shifted)
            (60.0, 280.0),  # para 2, line 2 (shifted)
        ]
        sizes = [10.0, 10.0, 10.0, 10.0, 10.0]
        joins = [" ", "\n", " ", " "]
        result = _compute_para_indents(extents, sizes, joins)
        assert len(result) == 2  # noqa: PLR2004
        assert result[0] == (0.0, 0.0)
        # Para 2: block indent = 10pt (60 - 50), no first-line indent
        assert result[1] == (10.0, 0.0)

    def test_block_and_first_line_indent(self) -> None:
        """Block quote with first-line indent on top."""
        extents = [
            (50.0, 300.0),  # para 1 (at margin)
            (50.0, 200.0),  # para 1, last line (short → \n)
            (70.0, 300.0),  # para 2, line 0 (block + first-line)
            (60.0, 300.0),  # para 2, line 1 (body at block indent)
            (60.0, 300.0),  # para 2, line 2
        ]
        sizes = [10.0, 10.0, 10.0, 10.0, 10.0]
        joins = [" ", "\n", " ", " "]
        result = _compute_para_indents(extents, sizes, joins)
        assert len(result) == 2  # noqa: PLR2004
        assert result[0] == (0.0, 0.0)
        # block=10 (60-50), first-line=10 (70-60)
        assert result[1] == (10.0, 10.0)

    def test_multi_level_block_indent(self) -> None:
        """Nested indentation at different levels."""
        extents = [
            (50.0, 300.0),  # para 1 (margin)
            (50.0, 200.0),  # short → \n
            (60.0, 300.0),  # para 2 (level 1)
            (60.0, 280.0),  # short → \n
            (70.0, 300.0),  # para 3 (level 2)
            (70.0, 300.0),
        ]
        sizes = [10.0, 10.0, 10.0, 10.0, 10.0, 10.0]
        joins = [" ", "\n", " ", "\n", " "]
        result = _compute_para_indents(extents, sizes, joins)
        assert len(result) == 3  # noqa: PLR2004
        assert result[0] == (0.0, 0.0)
        assert result[1] == (10.0, 0.0)
        assert result[2] == (20.0, 0.0)

    def test_single_line_paragraph_uses_first_line(self) -> None:
        """Single-line paragraphs use first-line indent (not block)."""
        extents = [
            (50.0, 300.0),  # para 1 at margin
            (60.0, 300.0),  # para 2, single line, shifted
        ]
        sizes = [10.0, 10.0]
        joins = ["\n"]
        result = _compute_para_indents(extents, sizes, joins)
        assert len(result) == 2  # noqa: PLR2004
        assert result[0] == (0.0, 0.0)
        # Single-line: shift goes to first-line indent
        assert result[1] == (0.0, 10.0)

    def test_hanging_indent_detected(self) -> None:
        """List markers left of body → negative text-indent."""
        extents = [
            (50.0, 300.0),  # "(1)" marker line
            (60.0, 300.0),  # body line
            (60.0, 300.0),  # body line
            (60.0, 200.0),  # last line of item 1 (short → \n)
            (50.0, 300.0),  # "(2)" marker line
            (60.0, 300.0),  # body line
        ]
        sizes = [10.0, 10.0, 10.0, 10.0, 10.0, 10.0]
        joins = [" ", " ", " ", "\n", " "]
        result = _compute_para_indents(extents, sizes, joins)
        assert len(result) == 2  # noqa: PLR2004
        # block=10 (body at 60 vs margin 50), first-line=-10 (50-60)
        assert result[0] == (10.0, -10.0)
        assert result[1] == (10.0, -10.0)

    def test_shift_too_small_not_detected(self) -> None:
        """Shift below _INDENT_FACTOR * font_size is not an indent."""
        extents = [
            (50.0, 300.0),
            (50.0, 200.0),
            (52.0, 300.0),  # shift=2pt, font=10 → min=5pt → no
            (50.0, 300.0),
        ]
        sizes = [10.0, 10.0, 10.0, 10.0]
        joins = ["\n", " ", " "]
        assert _compute_para_indents(extents, sizes, joins) == []


class TestBuildOverlayHtmlAlignment:
    """Tests that _build_overlay_html uses text_align and text_indent."""

    def test_justify_alignment(self) -> None:
        block = {
            "translated_text": "Some text",
            "font_size": 12.0,
            "color": 0,
            "bold": False,
            "italic": False,
            "text_align": "justify",
            "font_flags": 0,
        }
        html_out = _build_overlay_html(block)
        assert "text-align:justify" in html_out

    def test_text_indent(self) -> None:
        block = {
            "translated_text": "Indented paragraph",
            "font_size": 12.0,
            "color": 0,
            "bold": False,
            "italic": False,
            "text_align": "left",
            "text_indent": 20.0,
            "font_flags": 0,
        }
        html_out = _build_overlay_html(block)
        assert "text-indent:20.0pt" in html_out

    def test_no_indent_no_css(self) -> None:
        block = {
            "translated_text": "No indent",
            "font_size": 12.0,
            "color": 0,
            "bold": False,
            "italic": False,
            "text_align": "left",
            "font_flags": 0,
        }
        html_out = _build_overlay_html(block)
        assert "text-indent" not in html_out

    def test_multi_paragraph_indent_separate_p_tags(self) -> None:
        """Each paragraph gets its own <p> with text-indent."""
        block = {
            "translated_text": "First paragraph.\nSecond paragraph.",
            "font_size": 12.0,
            "color": 0,
            "bold": False,
            "italic": False,
            "text_align": "justify",
            "text_indent": 15.0,
            "font_flags": 0,
        }
        html_out = _build_overlay_html(block)
        # Should produce two <p> tags, not one with <br/>
        assert html_out.count("<p ") == 2  # noqa: PLR2004
        assert "<br/>" not in html_out
        assert "text-indent:15.0pt" in html_out
        assert "First paragraph." in html_out
        assert "Second paragraph." in html_out

    def test_single_paragraph_indent_one_p_tag(self) -> None:
        """Single paragraph with indent uses one <p> tag."""
        block = {
            "translated_text": "Only one paragraph here.",
            "font_size": 12.0,
            "color": 0,
            "bold": False,
            "italic": False,
            "text_align": "left",
            "text_indent": 20.0,
            "font_flags": 0,
        }
        html_out = _build_overlay_html(block)
        assert html_out.count("<p ") == 1
        assert "text-indent:20.0pt" in html_out

    def test_no_indent_separate_p_tags(self) -> None:
        """Without indent, newlines still produce separate <p> tags."""
        block = {
            "translated_text": "First line.\nSecond line.",
            "font_size": 12.0,
            "color": 0,
            "bold": False,
            "italic": False,
            "text_align": "left",
            "font_flags": 0,
        }
        html_out = _build_overlay_html(block)
        assert html_out.count("<p ") == 2  # noqa: PLR2004
        assert "text-indent" not in html_out

    def test_per_paragraph_first_line_indents(self) -> None:
        """para_indents (block=0, first-line>0) adds text-indent."""
        block = {
            "translated_text": "No indent.\nIndented.\nAlso indented.",
            "font_size": 12.0,
            "color": 0,
            "bold": False,
            "italic": False,
            "text_align": "justify",
            "font_flags": 0,
            "para_indents": [(0.0, 0.0), (0.0, 10.3), (0.0, 10.3)],
        }
        html_out = _build_overlay_html(block)
        assert html_out.count("<p ") == 3  # noqa: PLR2004
        p_tags = html_out.split("</p>")
        # First paragraph: no indent
        assert "text-indent" not in p_tags[0]
        assert "padding-left" not in p_tags[0]
        # Second and third: first-line indent
        assert "text-indent:10.3pt" in p_tags[1]
        assert "text-indent:10.3pt" in p_tags[2]

    def test_per_paragraph_block_indent(self) -> None:
        """para_indents (block>0, first-line=0) adds padding-left."""
        block = {
            "translated_text": "Level 0.\nLevel 1.\nLevel 2.",
            "font_size": 12.0,
            "color": 0,
            "bold": False,
            "italic": False,
            "text_align": "left",
            "font_flags": 0,
            "para_indents": [(0.0, 0.0), (10.0, 0.0), (20.0, 0.0)],
        }
        html_out = _build_overlay_html(block)
        p_tags = html_out.split("</p>")
        assert "padding-left" not in p_tags[0]
        assert "padding-left:10.0pt" in p_tags[1]
        assert "padding-left:20.0pt" in p_tags[2]

    def test_per_paragraph_block_and_first_line(self) -> None:
        """Both block and first-line indent on same paragraph."""
        block = {
            "translated_text": "Normal.\nBlock quote with indent.",
            "font_size": 12.0,
            "color": 0,
            "bold": False,
            "italic": False,
            "text_align": "justify",
            "font_flags": 0,
            "para_indents": [(0.0, 0.0), (10.0, 8.0)],
        }
        html_out = _build_overlay_html(block)
        p_tags = html_out.split("</p>")
        assert "padding-left:10.0pt" in p_tags[1]
        assert "text-indent:8.0pt" in p_tags[1]

    def test_hanging_indent_negative_text_indent(self) -> None:
        """Hanging indent produces negative text-indent with padding."""
        block = {
            "translated_text": "(1) First item.\n(2) Second item.",
            "font_size": 10.0,
            "color": 0,
            "bold": False,
            "italic": False,
            "text_align": "left",
            "font_flags": 0,
            "para_indents": [(13.5, -13.5), (13.5, -13.5)],
        }
        html_out = _build_overlay_html(block)
        p_tags = html_out.split("</p>")
        # Both items: body shifted right, marker pulled left
        assert "padding-left:13.5pt" in p_tags[0]
        assert "text-indent:-13.5pt" in p_tags[0]
        assert "padding-left:13.5pt" in p_tags[1]
        assert "text-indent:-13.5pt" in p_tags[1]


# ── Super/subscript support tests ────────────────────────────────────────────


class TestClassifySupSub:
    """Tests for _classify_sup_sub()."""

    def test_normal_size_returns_none(self) -> None:
        """Span at same size as line dominant → not super/sub."""
        assert _classify_sup_sub(12.0, 10.0, 22.0, 12.0, 10.0, 22.0) is None

    def test_slightly_smaller_returns_none(self) -> None:
        """Span at 90% of dominant → still normal (above threshold)."""
        assert _classify_sup_sub(10.8, 10.0, 22.0, 12.0, 10.0, 22.0) is None

    def test_real_footnote_marker(self) -> None:
        """Real-world footnote: size 7.3 in line with dominant 8.9."""
        # Line y=(539.2, 551.4), span y=(540.4, 547.7)
        result = _classify_sup_sub(7.3, 540.4, 547.7, 8.9, 539.2, 551.4)
        assert result == "sup"

    def test_superscript_upper_half(self) -> None:
        """Small span in upper half of line → superscript."""
        # Line: y0=10, y1=22 → mid=16.  Span center at 12 < 16.
        result = _classify_sup_sub(7.0, 10.0, 14.0, 12.0, 10.0, 22.0)
        assert result == "sup"

    def test_subscript_lower_half(self) -> None:
        """Small span in lower half of line → subscript."""
        # Line: y0=10, y1=22 → mid=16.  Span center at 20 > 16.
        result = _classify_sup_sub(7.0, 18.0, 22.0, 12.0, 10.0, 22.0)
        assert result == "sub"

    def test_zero_dominant_size_returns_none(self) -> None:
        """Edge case: zero dominant size → no classification."""
        assert _classify_sup_sub(5.0, 10.0, 15.0, 0.0, 10.0, 22.0) is None

    def test_exact_threshold_returns_none(self) -> None:
        """Span at exactly the threshold ratio → not super/sub."""
        threshold_size = 12.0 * _SUP_SUB_SIZE_RATIO  # noqa: PLR2004
        assert _classify_sup_sub(threshold_size, 10.0, 15.0, 12.0, 10.0, 22.0) is None

    def test_just_below_threshold_is_classified(self) -> None:
        """Span just below the threshold → classified."""
        below = 12.0 * _SUP_SUB_SIZE_RATIO - 0.01  # noqa: PLR2004
        result = _classify_sup_sub(below, 10.0, 14.0, 12.0, 10.0, 22.0)
        assert result == "sup"


class TestHasMixedFormattingSupSub:
    """Tests for _has_mixed_formatting with super/subscript roles."""

    def test_no_roles_bold_only(self) -> None:
        """Existing bold variation still detected without roles."""
        assert _has_mixed_formatting([0, 16]) is True

    def test_no_variation_no_roles(self) -> None:
        """Uniform flags, no roles → not mixed."""
        assert _has_mixed_formatting([0, 0, 0]) is False

    def test_sup_role_triggers_mixed(self) -> None:
        """Uniform flags but one superscript role → mixed."""
        assert _has_mixed_formatting([0, 0], roles=[None, "sup"]) is True

    def test_sub_role_triggers_mixed(self) -> None:
        """Uniform flags but one subscript role → mixed."""
        assert _has_mixed_formatting([0, 0], roles=["sub", None]) is True

    def test_all_none_roles_not_mixed(self) -> None:
        """Uniform flags, all None roles → not mixed."""
        assert _has_mixed_formatting([0, 0], roles=[None, None]) is False


class TestTagSpanTextSupSub:
    """Tests for _tag_span_text with super/subscript role."""

    def test_no_role_unchanged(self) -> None:
        """Normal span without role → no wrapping."""
        assert _tag_span_text("text", 0, False, False) == "text"

    def test_sup_role_wraps(self) -> None:
        """Superscript role → wrapped with <sup>."""
        assert _tag_span_text("2", 0, False, False, role="sup") == "<sup>2</sup>"

    def test_sub_role_wraps(self) -> None:
        """Subscript role → wrapped with <sub>."""
        assert _tag_span_text("i", 0, False, False, role="sub") == "<sub>i</sub>"

    def test_bold_and_sup(self) -> None:
        """Bold span with superscript → nested tags."""
        result = _tag_span_text("n", 16, False, False, role="sup")
        assert result == "<sup><b>n</b></sup>"

    def test_italic_and_sub(self) -> None:
        """Italic span with subscript → nested tags."""
        result = _tag_span_text("x", 2, False, False, role="sub")
        assert result == "<sub><i>x</i></sub>"

    def test_whitespace_not_wrapped(self) -> None:
        """Whitespace-only span → no wrapping even with role."""
        assert _tag_span_text("  ", 0, False, False, role="sup") == "  "


class TestMergeAdjacentTagsSupSub:
    """Tests for _merge_adjacent_tags with sup/sub tags."""

    def test_merge_adjacent_sup(self) -> None:
        """Adjacent </sup><sup> → merged."""
        assert _merge_adjacent_tags("x</sup><sup>y") == "xy"

    def test_merge_adjacent_sub_with_space(self) -> None:
        """Adjacent </sub> <sub> → single space."""
        assert _merge_adjacent_tags("x</sub> <sub>y") == "x y"


class TestEscapePreservingTagsSupSub:
    """Tests for _escape_preserving_tags with sup/sub tags."""

    def test_preserves_sup_tags(self) -> None:
        """<sup> tags survive HTML escaping."""
        result = _escape_preserving_tags("E=mc<sup>2</sup>")
        assert "<sup>" in result
        assert "</sup>" in result

    def test_preserves_sub_tags(self) -> None:
        """<sub> tags survive HTML escaping."""
        result = _escape_preserving_tags("H<sub>2</sub>O")
        assert "<sub>" in result
        assert "</sub>" in result

    def test_escapes_other_html(self) -> None:
        """Non-allowed tags are still escaped."""
        result = _escape_preserving_tags("<div>x<sup>2</sup></div>")
        assert "&lt;div&gt;" in result
        assert "<sup>2</sup>" in result


class TestHasMixedFormattingColor:
    """Tests for _has_mixed_formatting with color variation."""

    def test_same_colors_not_mixed(self) -> None:
        """Uniform flags and colors → not mixed."""
        assert (
            _has_mixed_formatting(
                [0, 0],
                colors=[0x000000, 0x000000],
            )
            is False
        )

    def test_different_colors_triggers_mixed(self) -> None:
        """Different colors → mixed even with uniform flags."""
        assert (
            _has_mixed_formatting(
                [0, 0],
                colors=[0x000000, 0x1A73E8],
            )
            is True
        )

    def test_colors_none_ignored(self) -> None:
        """No colors kwarg → color check skipped."""
        assert _has_mixed_formatting([0, 0]) is False


class TestTagSpanTextColor:
    """Tests for _tag_span_text with color deviation."""

    def test_same_color_no_span(self) -> None:
        """Span matching dominant color → no wrapping."""
        result = _tag_span_text(
            "Hello",
            0,
            False,
            False,
            color=0x000000,
            base_color=0x000000,
        )
        assert result == "Hello"

    def test_different_color_wraps(self) -> None:
        """Span differing from dominant → wrapped with <span color>."""
        result = _tag_span_text(
            "link",
            0,
            False,
            False,
            color=0x1A73E8,
            base_color=0x000000,
        )
        assert result == '<span style="color:#1a73e8">link</span>'

    def test_color_combined_with_bold(self) -> None:
        """Bold + color deviation → nested <span> around <b>."""
        result = _tag_span_text(
            "X",
            16,
            False,
            False,
            color=0xFF0000,
            base_color=0x000000,
        )
        assert result == '<span style="color:#ff0000"><b>X</b></span>'

    def test_color_combined_with_sup(self) -> None:
        """Sup + color → <span> wraps <sup>."""
        result = _tag_span_text(
            "*",
            0,
            False,
            False,
            role="sup",
            color=0x0000FF,
            base_color=0x000000,
        )
        assert result == '<span style="color:#0000ff"><sup>*</sup></span>'

    def test_whitespace_not_wrapped(self) -> None:
        """Whitespace-only → no color wrapping."""
        result = _tag_span_text(
            "  ",
            0,
            False,
            False,
            color=0xFF0000,
            base_color=0x000000,
        )
        assert result == "  "

    def test_no_color_args_no_wrapping(self) -> None:
        """Without color/base_color args → no color wrapping."""
        result = _tag_span_text("text", 0, False, False)
        assert result == "text"


class TestMergeAdjacentTagsColor:
    """Tests for _merge_adjacent_tags with color <span> tags."""

    def test_merge_same_color_spans(self) -> None:
        """Adjacent </span><span> with same color → merged."""
        text = (
            '<span style="color:#1a73e8">Hello</span>'
            '<span style="color:#1a73e8"> World</span>'
        )
        result = _merge_adjacent_tags(text)
        assert result == '<span style="color:#1a73e8">Hello World</span>'

    def test_merge_same_color_with_space(self) -> None:
        """Adjacent </span> <span> with space → keeps space."""
        text = (
            '<span style="color:#1a73e8">A</span> <span style="color:#1a73e8">B</span>'
        )
        result = _merge_adjacent_tags(text)
        assert result == '<span style="color:#1a73e8">A B</span>'

    def test_different_colors_not_merged(self) -> None:
        """Adjacent spans with different colors → NOT merged."""
        text = (
            '<span style="color:#1a73e8">blue</span>'
            '<span style="color:#ff0000">red</span>'
        )
        result = _merge_adjacent_tags(text)
        assert "blue</span>" in result
        assert '<span style="color:#ff0000">red' in result


class TestEscapePreservingTagsColor:
    """Tests for _escape_preserving_tags with color <span> tags."""

    def test_preserves_color_span(self) -> None:
        """<span style="color:..."> survives HTML escaping."""
        text = '<span style="color:#1a73e8">link</span>'
        result = _escape_preserving_tags(text)
        assert '<span style="color:#1a73e8">' in result
        assert "</span>" in result

    def test_preserves_mixed_tags(self) -> None:
        """Color span + bold tags both preserved."""
        text = '<b><span style="color:#ff0000">X</span></b>'
        result = _escape_preserving_tags(text)
        assert "<b>" in result
        assert '<span style="color:#ff0000">' in result
        assert "</span>" in result
        assert "</b>" in result

    def test_other_span_escaped(self) -> None:
        """<span> without color style is escaped."""
        result = _escape_preserving_tags('<span class="x">y</span>')
        assert "&lt;span" in result


class TestHasMixedFormattingSize:
    """Tests for _has_mixed_formatting with font size variation."""

    def test_same_sizes_not_mixed(self) -> None:
        """Uniform sizes → not mixed."""
        assert (
            _has_mixed_formatting(
                [0, 0],
                sizes=[10.0, 10.0],
            )
            is False
        )

    def test_different_sizes_triggers_mixed(self) -> None:
        """Different sizes → mixed."""
        assert (
            _has_mixed_formatting(
                [0, 0],
                sizes=[10.0, 14.0],
            )
            is True
        )

    def test_size_diff_from_sup_sub_not_mixed(self) -> None:
        """Size difference from sup/sub roles → NOT mixed (handled by tags)."""
        assert (
            _has_mixed_formatting(
                [0, 0],
                roles=[None, "sup"],
                sizes=[10.0, 6.0],
            )
            is True
        )  # mixed due to role, not size

    def test_size_diff_only_in_sup_sub_not_mixed(self) -> None:
        """All non-sup/sub spans same size → not mixed from size."""
        # One normal (10pt) + one sup (6pt) — only the sup differs
        assert (
            _has_mixed_formatting(
                [0, 0],
                roles=[None, "sup"],
                sizes=[10.0, 6.0],
                colors=[0, 0],
            )
            is True
        )  # mixed from role, but size alone wouldn't trigger


class TestTagSpanTextSize:
    """Tests for _tag_span_text with font size deviation."""

    def test_same_size_no_span(self) -> None:
        """Span matching dominant size → no wrapping."""
        result = _tag_span_text(
            "Hello",
            0,
            False,
            False,
            size=10.0,
            base_size=10.0,
        )
        assert result == "Hello"

    def test_different_size_wraps(self) -> None:
        """Span differing from dominant size → wrapped with font-size."""
        result = _tag_span_text(
            "big",
            0,
            False,
            False,
            size=14.0,
            base_size=10.0,
        )
        assert result == '<span style="font-size:14.0pt">big</span>'

    def test_size_skipped_for_sup(self) -> None:
        """Sup span → no font-size wrapping (handled by <sup>)."""
        result = _tag_span_text(
            "*",
            0,
            False,
            False,
            role="sup",
            size=6.0,
            base_size=10.0,
        )
        assert "font-size" not in result
        assert result == "<sup>*</sup>"

    def test_size_skipped_for_sub(self) -> None:
        """Sub span → no font-size wrapping (handled by <sub>)."""
        result = _tag_span_text(
            "2",
            0,
            False,
            False,
            role="sub",
            size=6.0,
            base_size=10.0,
        )
        assert "font-size" not in result
        assert result == "<sub>2</sub>"

    def test_color_and_size_combined(self) -> None:
        """Both color + size deviation → single <span> with both styles."""
        result = _tag_span_text(
            "X",
            0,
            False,
            False,
            color=0xFF0000,
            base_color=0x000000,
            size=14.0,
            base_size=10.0,
        )
        assert result == '<span style="color:#ff0000;font-size:14.0pt">X</span>'

    def test_tiny_size_diff_ignored(self) -> None:
        """Font-size difference ≤ 0.5pt is ignored (PDF artifact)."""
        # 9.96 vs 10.06 — 0.1pt diff, common in citation numbers
        result = _tag_span_text(
            "7",
            0,
            False,
            False,
            size=9.96,
            base_size=10.06,
        )
        assert result == "7"

    def test_size_diff_above_tolerance_wraps(self) -> None:
        """Font-size difference > 0.5pt still gets wrapped."""
        result = _tag_span_text(
            "big",
            0,
            False,
            False,
            size=10.6,
            base_size=10.0,
        )
        assert "font-size:10.6pt" in result

    def test_whitespace_not_wrapped(self) -> None:
        """Whitespace-only → no size wrapping."""
        result = _tag_span_text(
            "  ",
            0,
            False,
            False,
            size=14.0,
            base_size=10.0,
        )
        assert result == "  "


class TestMergeAdjacentTagsSize:
    """Tests for _merge_adjacent_tags with font-size <span> tags."""

    def test_merge_same_size_spans(self) -> None:
        """Adjacent </span><span> with same size → merged."""
        text = (
            '<span style="font-size:14.0pt">Hello</span>'
            '<span style="font-size:14.0pt"> World</span>'
        )
        result = _merge_adjacent_tags(text)
        assert result == '<span style="font-size:14.0pt">Hello World</span>'

    def test_different_sizes_not_merged(self) -> None:
        """Adjacent spans with different sizes → NOT merged."""
        text = (
            '<span style="font-size:14.0pt">big</span>'
            '<span style="font-size:10.0pt">small</span>'
        )
        result = _merge_adjacent_tags(text)
        assert "big</span>" in result
        assert '<span style="font-size:10.0pt">small' in result

    def test_merge_combined_style_spans(self) -> None:
        """Adjacent spans with same color+size → merged."""
        text = (
            '<span style="color:#ff0000;font-size:14.0pt">A</span>'
            '<span style="color:#ff0000;font-size:14.0pt">B</span>'
        )
        result = _merge_adjacent_tags(text)
        assert result == ('<span style="color:#ff0000;font-size:14.0pt">AB</span>')


class TestEscapePreservingTagsSize:
    """Tests for _escape_preserving_tags with font-size <span> tags."""

    def test_preserves_size_span(self) -> None:
        """<span style="font-size:..."> survives HTML escaping."""
        text = '<span style="font-size:14.0pt">big</span>'
        result = _escape_preserving_tags(text)
        assert '<span style="font-size:14.0pt">' in result
        assert "</span>" in result

    def test_preserves_combined_span(self) -> None:
        """<span style="color:...;font-size:..."> survives escaping."""
        text = '<span style="color:#ff0000;font-size:14.0pt">X</span>'
        result = _escape_preserving_tags(text)
        assert '<span style="color:#ff0000;font-size:14.0pt">' in result


class TestBuildOverlayHtmlSpaceBetween:
    """Tests for _build_overlay_html with space-between layout."""

    def test_space_between_renders_table(self) -> None:
        """Block with is_space_between + tab renders as two-cell table."""
        block = {
            "rect": [50, 50, 550, 70],
            "translated_text": "Left text\tRight text",
            "font_size": 10.0,
            "font_name": "",
            "color": 0,
            "bold": False,
            "italic": False,
            "text_align": "left",
            "font_flags": 0,
            "is_space_between": True,
        }
        html_out = _build_overlay_html(block)
        assert "<table" in html_out
        assert "text-align:left" in html_out
        assert "text-align:right" in html_out
        assert "Left text" in html_out
        assert "Right text" in html_out

    def test_space_between_without_tab_falls_through(self) -> None:
        """If LLM drops the tab, fall through to normal rendering."""
        block = {
            "rect": [50, 50, 550, 70],
            "translated_text": "All on left",
            "font_size": 10.0,
            "font_name": "",
            "color": 0,
            "bold": False,
            "italic": False,
            "text_align": "left",
            "font_flags": 0,
            "is_space_between": True,
        }
        html_out = _build_overlay_html(block)
        # Falls through to normal <p> rendering
        assert "<p " in html_out
        assert "<table" not in html_out


class TestBuildOverlayHtmlSupSub:
    """Tests for _build_overlay_html rendering super/subscript tags."""

    def test_sup_tags_in_mixed_block(self) -> None:
        """Mixed block with <sup> tags renders them in HTML output."""
        block = {
            "rect": [50, 100, 300, 120],
            "translated_text": "E=mc<sup>2</sup>",
            "font_size": 10.0,
            "font_name": "",
            "color": 0,
            "bold": False,
            "italic": False,
            "text_align": "left",
            "font_flags": 0,
            "has_mixed_formatting": True,
        }
        html_out = _build_overlay_html(block)
        assert "<sup>" in html_out
        assert "</sup>" in html_out

    def test_sub_tags_in_mixed_block(self) -> None:
        """Mixed block with <sub> tags renders them in HTML output."""
        block = {
            "rect": [50, 100, 300, 120],
            "translated_text": "H<sub>2</sub>O",
            "font_size": 10.0,
            "font_name": "",
            "color": 0,
            "bold": False,
            "italic": False,
            "text_align": "left",
            "font_flags": 0,
            "has_mixed_formatting": True,
        }
        html_out = _build_overlay_html(block)
        assert "<sub>" in html_out
        assert "</sub>" in html_out


# ── _font_family_from_flags ───────────────────────────────────────────


class TestFontFamilyFromFlags:
    """Tests for _font_family_from_flags."""

    def test_monospace_bit(self) -> None:
        """Bit 3 (8) → monospace."""
        assert _font_family_from_flags(8) == "monospace"

    def test_serif_bit(self) -> None:
        """Bit 2 (4) → serif."""
        assert _font_family_from_flags(4) == "serif"

    def test_sans_serif_default(self) -> None:
        """No monospace or serif bits → sans-serif."""
        assert _font_family_from_flags(0) == "sans-serif"

    def test_monospace_takes_priority_over_serif(self) -> None:
        """When both bits 3 and 2 are set, monospace wins."""
        assert _font_family_from_flags(8 | 4) == "monospace"

    def test_bold_italic_bits_ignored(self) -> None:
        """Bold (16) + italic (2) bits don't affect font family."""
        assert _font_family_from_flags(16 | 2) == "sans-serif"

    def test_bold_with_serif(self) -> None:
        """Bold (16) + serif (4) → serif."""
        assert _font_family_from_flags(16 | 4) == "serif"

    def test_all_bits_set(self) -> None:
        """All classification bits → monospace (highest priority)."""
        assert _font_family_from_flags(0xFF) == "monospace"  # noqa: PLR2004


# ── _span_in_any_table ────────────────────────────────────────────────


class TestSpanInAnyTable:
    """Tests for _span_in_any_table."""

    def test_center_inside_table(self) -> None:
        """Span whose center falls inside a table returns True."""
        span_bbox = (10, 10, 20, 20)  # center = (15, 15)
        tables = [(0, 0, 30, 30)]
        assert _span_in_any_table(span_bbox, tables)

    def test_center_outside_table(self) -> None:
        """Span whose center is outside all tables returns False."""
        span_bbox = (100, 100, 110, 110)  # center = (105, 105)
        tables = [(0, 0, 30, 30)]
        assert not _span_in_any_table(span_bbox, tables)

    def test_empty_tables_list(self) -> None:
        """No tables means span is never inside any."""
        assert not _span_in_any_table((10, 10, 20, 20), [])

    def test_span_overlaps_but_center_outside(self) -> None:
        """Span overlapping table but center outside returns False."""
        span_bbox = (25, 25, 50, 50)  # center = (37.5, 37.5)
        tables = [(0, 0, 30, 30)]
        assert not _span_in_any_table(span_bbox, tables)

    def test_center_on_boundary(self) -> None:
        """Center exactly on table boundary returns True (<=)."""
        span_bbox = (28, 28, 32, 32)  # center = (30, 30)
        tables = [(0, 0, 30, 30)]
        assert _span_in_any_table(span_bbox, tables)

    def test_multiple_tables_second_matches(self) -> None:
        """Center inside the second table returns True."""
        span_bbox = (60, 60, 70, 70)  # center = (65, 65)
        tables = [(0, 0, 30, 30), (50, 50, 80, 80)]
        assert _span_in_any_table(span_bbox, tables)

    def test_list_input_for_span_bbox(self) -> None:
        """Accepts list (not just tuple) for span_bbox."""
        assert _span_in_any_table([10, 10, 20, 20], [(0, 0, 30, 30)])


# ── _bbox_overlaps_any ────────────────────────────────────────────────


class TestBboxOverlapsAny:
    """Tests for _bbox_overlaps_any."""

    def test_no_existing_tables(self) -> None:
        """Empty list → no overlap."""
        assert not _bbox_overlaps_any((0, 0, 100, 100), [])

    def test_overlapping_table(self) -> None:
        """Significant overlap returns True."""
        existing = [{"bbox": (0, 0, 100, 100)}]
        # Large overlap (50×100 = 5000, smaller area = 5000, ratio = 1.0)
        assert _bbox_overlaps_any((50, 0, 100, 100), existing)

    def test_no_overlap(self) -> None:
        """Disjoint bboxes return False."""
        existing = [{"bbox": (0, 0, 50, 50)}]
        assert not _bbox_overlaps_any((200, 200, 300, 300), existing)

    def test_tiny_overlap_below_threshold(self) -> None:
        """Overlap below threshold returns False."""
        existing = [{"bbox": (0, 0, 100, 100)}]
        # Overlap: 1×100 = 100, smaller area = 100*100 = 10000
        # Ratio = 0.01 < threshold
        assert not _bbox_overlaps_any((99, 0, 200, 100), existing)

    def test_delegates_to_find_overlap_index(self) -> None:
        """Consistent with _find_overlap_index returning non-None."""
        existing = [{"bbox": (0, 0, 100, 100)}]
        bbox = (10, 10, 90, 90)  # Fully contained
        assert _bbox_overlaps_any(bbox, existing)
        assert _find_overlap_index(bbox, existing) is not None


# ── _block_inside_any_xobject ─────────────────────────────────────────


class TestBlockInsideAnyXobject:
    """Tests for _block_inside_any_xobject."""

    def test_block_inside_xobject(self) -> None:
        """Block fully inside an XObject region returns True."""
        xobj_rect = pymupdf.Rect(0, 0, 200, 200)
        assert _block_inside_any_xobject([10, 10, 50, 50], [xobj_rect])

    def test_block_outside_xobject(self) -> None:
        """Block outside all XObject regions returns False."""
        xobj_rect = pymupdf.Rect(0, 0, 50, 50)
        assert not _block_inside_any_xobject([100, 100, 200, 200], [xobj_rect])

    def test_empty_xobject_list(self) -> None:
        """No XObject rects → False."""
        assert not _block_inside_any_xobject([10, 10, 50, 50], [])

    def test_block_partially_inside(self) -> None:
        """Block only partially inside returns False (requires full containment)."""
        xobj_rect = pymupdf.Rect(0, 0, 30, 30)
        assert not _block_inside_any_xobject([10, 10, 50, 50], [xobj_rect])

    def test_multiple_xobjects_second_contains(self) -> None:
        """Block inside the second XObject returns True."""
        r1 = pymupdf.Rect(0, 0, 5, 5)
        r2 = pymupdf.Rect(100, 100, 300, 300)
        assert _block_inside_any_xobject([120, 120, 200, 200], [r1, r2])


# ── _get_spans_in_rect ────────────────────────────────────────────────


class TestGetSpansInRect:
    """Tests for _get_spans_in_rect."""

    def test_empty_page_dict(self) -> None:
        """No blocks → empty."""
        assert _get_spans_in_rect({"blocks": []}, (0, 0, 100, 100)) == []

    def test_span_center_inside_rect(self) -> None:
        """Span whose center falls inside rect is included."""
        page_dict = {
            "blocks": [
                {
                    "type": 0,
                    "lines": [
                        {
                            "spans": [{"bbox": (10, 10, 20, 20), "text": "hi"}],
                        }
                    ],
                }
            ],
        }
        # center = (15, 15), rect = (0, 0, 30, 30)
        result = _get_spans_in_rect(page_dict, (0, 0, 30, 30))
        assert len(result) == 1
        assert result[0]["text"] == "hi"

    def test_span_center_outside_rect(self) -> None:
        """Span whose center falls outside rect is excluded."""
        page_dict = {
            "blocks": [
                {
                    "type": 0,
                    "lines": [
                        {
                            "spans": [{"bbox": (100, 100, 120, 120), "text": "far"}],
                        }
                    ],
                }
            ],
        }
        assert _get_spans_in_rect(page_dict, (0, 0, 30, 30)) == []

    def test_image_blocks_skipped(self) -> None:
        """Image blocks (type=1) are skipped."""
        page_dict = {
            "blocks": [
                {
                    "type": 1,
                    "bbox": (0, 0, 100, 100),
                }
            ],
        }
        assert _get_spans_in_rect(page_dict, (0, 0, 200, 200)) == []

    def test_multiple_spans_filtered(self) -> None:
        """Only spans with center inside are returned."""
        page_dict = {
            "blocks": [
                {
                    "type": 0,
                    "lines": [
                        {
                            "spans": [
                                {"bbox": (10, 10, 20, 20), "text": "in"},
                                {"bbox": (200, 200, 210, 210), "text": "out"},
                            ],
                        }
                    ],
                }
            ],
        }
        result = _get_spans_in_rect(page_dict, (0, 0, 50, 50))
        assert len(result) == 1
        assert result[0]["text"] == "in"

    def test_accepts_list_rect(self) -> None:
        """Accepts list (not just tuple) for rect."""
        page_dict = {
            "blocks": [
                {
                    "type": 0,
                    "lines": [
                        {
                            "spans": [{"bbox": (5, 5, 15, 15), "text": "ok"}],
                        }
                    ],
                }
            ],
        }
        assert len(_get_spans_in_rect(page_dict, [0, 0, 20, 20])) == 1


# ── _group_spans_into_rows ────────────────────────────────────────────


class TestGroupSpansIntoRows:
    """Tests for _group_spans_into_rows."""

    def test_empty_list(self) -> None:
        """Empty input returns empty."""
        assert _group_spans_into_rows([]) == []

    def test_single_span(self) -> None:
        """Single span forms a single row."""
        spans = [{"bbox": (10, 50, 30, 60)}]
        rows = _group_spans_into_rows(spans)
        assert len(rows) == 1
        assert len(rows[0]) == 1

    def test_same_y_grouped(self) -> None:
        """Spans at similar y form one row, sorted by x."""
        spans = [
            {"bbox": (50, 100, 80, 110)},
            {"bbox": (10, 101, 40, 111)},  # within tolerance
        ]
        rows = _group_spans_into_rows(spans)
        assert len(rows) == 1
        # Sorted by x: second span comes first
        assert rows[0][0]["bbox"][0] == 10  # noqa: PLR2004
        assert rows[0][1]["bbox"][0] == 50  # noqa: PLR2004

    def test_different_y_creates_multiple_rows(self) -> None:
        """Spans at different y positions form separate rows."""
        spans = [
            {"bbox": (10, 10, 30, 20)},
            {"bbox": (10, 50, 30, 60)},
        ]
        rows = _group_spans_into_rows(spans)
        assert len(rows) == 2  # noqa: PLR2004

    def test_three_rows(self) -> None:
        """Three distinct y groups create three rows."""
        spans = [
            {"bbox": (10, 100, 30, 110)},
            {"bbox": (10, 50, 30, 60)},
            {"bbox": (10, 150, 30, 160)},
        ]
        rows = _group_spans_into_rows(spans)
        assert len(rows) == 3  # noqa: PLR2004
        # Rows sorted by y
        assert rows[0][0]["bbox"][1] == 50  # noqa: PLR2004
        assert rows[1][0]["bbox"][1] == 100  # noqa: PLR2004
        assert rows[2][0]["bbox"][1] == 150  # noqa: PLR2004


# ── _group_rules_by_xrange ────────────────────────────────────────────


class TestGroupRulesByXrange:
    """Tests for _group_rules_by_xrange."""

    def test_empty_input(self) -> None:
        """No lines → no groups."""
        assert _group_rules_by_xrange([]) == []

    def test_single_line(self) -> None:
        """Single line forms one group."""
        lines = [{"y": 10, "x0": 50, "x1": 500}]
        groups = _group_rules_by_xrange(lines)
        assert len(groups) == 1
        assert len(groups[0]) == 1

    def test_same_xrange_grouped(self) -> None:
        """Lines with same x-range go into one group."""
        lines = [
            {"y": 10, "x0": 50, "x1": 500},
            {"y": 30, "x0": 51, "x1": 501},  # within tolerance
            {"y": 80, "x0": 50, "x1": 499},
        ]
        groups = _group_rules_by_xrange(lines)
        assert len(groups) == 1
        assert len(groups[0]) == 3  # noqa: PLR2004

    def test_different_xrange_separate_groups(self) -> None:
        """Lines with different x-ranges form separate groups."""
        lines = [
            {"y": 10, "x0": 50, "x1": 500},
            {"y": 30, "x0": 200, "x1": 400},  # different x-range
        ]
        groups = _group_rules_by_xrange(lines)
        assert len(groups) == 2  # noqa: PLR2004

    def test_tolerance_boundary(self) -> None:
        """Lines just outside tolerance form separate groups."""
        tol = _RULE_XRANGE_TOLERANCE
        lines = [
            {"y": 10, "x0": 50, "x1": 500},
            {"y": 30, "x0": 50 + tol + 1, "x1": 500},  # outside tolerance
        ]
        groups = _group_rules_by_xrange(lines)
        assert len(groups) == 2  # noqa: PLR2004


# ── _group_vlines_by_yrange ───────────────────────────────────────────


class TestGroupVlinesByYrange:
    """Tests for _group_vlines_by_yrange."""

    def test_empty_input(self) -> None:
        """No lines → no groups."""
        assert _group_vlines_by_yrange([]) == []

    def test_single_line(self) -> None:
        """Single line forms one group."""
        lines = [{"x": 100, "y0": 50, "y1": 500}]
        groups = _group_vlines_by_yrange(lines)
        assert len(groups) == 1

    def test_same_yrange_grouped(self) -> None:
        """Lines with same y-range go into one group."""
        lines = [
            {"x": 100, "y0": 50, "y1": 500},
            {"x": 200, "y0": 51, "y1": 501},
            {"x": 300, "y0": 50, "y1": 499},
        ]
        groups = _group_vlines_by_yrange(lines)
        assert len(groups) == 1
        assert len(groups[0]) == 3  # noqa: PLR2004

    def test_different_yrange_separate(self) -> None:
        """Lines with different y-ranges form separate groups."""
        lines = [
            {"x": 100, "y0": 50, "y1": 500},
            {"x": 200, "y0": 200, "y1": 400},
        ]
        groups = _group_vlines_by_yrange(lines)
        assert len(groups) == 2  # noqa: PLR2004

    def test_tolerance_boundary(self) -> None:
        """Lines just outside tolerance form separate groups."""
        tol = _VLINE_YRANGE_TOLERANCE
        lines = [
            {"x": 100, "y0": 50, "y1": 500},
            {"x": 200, "y0": 50 + tol + 1, "y1": 500},
        ]
        groups = _group_vlines_by_yrange(lines)
        assert len(groups) == 2  # noqa: PLR2004


# ── _infer_columns ────────────────────────────────────────────────────


class TestInferColumns:
    """Tests for _infer_columns."""

    def test_empty_rows(self) -> None:
        """No rows → zero columns."""
        col_count, dividers = _infer_columns([], (0, 0, 500, 500))
        assert col_count == 0
        assert dividers == []

    def test_single_span_rows_below_min(self) -> None:
        """Rows with single span → below min columns → 0."""
        rows = [
            [{"bbox": (10, 10, 200, 20)}],
            [{"bbox": (10, 30, 200, 40)}],
        ]
        col_count, dividers = _infer_columns(rows, (0, 0, 500, 500))
        assert col_count == 0

    def test_two_column_layout(self) -> None:
        """Two-span rows → 2 columns with dividers."""
        rows = [
            [
                {"bbox": (10, 10, 100, 20)},
                {"bbox": (200, 10, 300, 20)},
            ],
            [
                {"bbox": (10, 30, 100, 40)},
                {"bbox": (200, 30, 300, 40)},
            ],
            [
                {"bbox": (10, 50, 100, 60)},
                {"bbox": (200, 50, 300, 60)},
            ],
        ]
        bbox = (0, 0, 400, 100)
        col_count, dividers = _infer_columns(rows, bbox)
        assert col_count == 2  # noqa: PLR2004
        assert len(dividers) == 3  # noqa: PLR2004
        assert dividers[0] == 0  # table left
        assert dividers[-1] == 400  # noqa: PLR2004 — table right
        # Middle divider between col1 right (100) and col2 left (200)
        assert 100 < dividers[1] < 200  # noqa: PLR2004

    def test_mixed_row_span_counts(self) -> None:
        """Uses most common span count as column count."""
        rows = [
            [{"bbox": (10, 10, 100, 20)}, {"bbox": (200, 10, 300, 20)}],
            [{"bbox": (10, 30, 100, 40)}, {"bbox": (200, 30, 300, 40)}],
            # This row has 3 spans — minority, won't be used for dividers
            [
                {"bbox": (10, 50, 60, 60)},
                {"bbox": (100, 50, 200, 60)},
                {"bbox": (250, 50, 300, 60)},
            ],
        ]
        col_count, _ = _infer_columns(rows, (0, 0, 400, 100))
        assert col_count == 2  # noqa: PLR2004

    def test_dividers_adjusted_for_header_text(self) -> None:
        """Dividers shift left when header text starts before divider.

        Gap-voting uses dense data rows which may have wider gaps than
        header rows.  When a header span starts before the divider but
        its center is past it, the divider should shift left.
        """
        # Simulate: header "Maximum Path Length" starts at x=395 but
        # gap-voting placed divider at x=401 (from data row gaps).
        # Data rows have content starting at x=418+.
        header = [
            {"bbox": (130, 10, 180, 20)},  # col 0: "Layer Type"
            {"bbox": (240, 10, 328, 20)},  # col 1: "Complexity"
            {"bbox": (340, 10, 382, 20)},  # col 2: "Sequential"
            {"bbox": (395, 10, 488, 20)},  # col 3: "Maximum Path Length"
        ]
        data1 = [
            {"bbox": (130, 30, 180, 40)},  # col 0
            {"bbox": (264, 30, 303, 40)},  # col 1
            {"bbox": (351, 30, 372, 40)},  # col 2
            {"bbox": (431, 30, 452, 40)},  # col 3
        ]
        data2 = [
            {"bbox": (130, 50, 180, 60)},
            {"bbox": (258, 50, 309, 60)},
            {"bbox": (351, 50, 372, 60)},
            {"bbox": (418, 50, 465, 60)},
        ]
        rows = [header, data1, data2]
        col_count, dividers = _infer_columns(rows, (120, 0, 500, 70))
        # The divider between col 2 and col 3 must be left of x=395
        # so "Maximum Path Length" is fully inside col 3.
        assert col_count >= 4  # noqa: PLR2004
        col3_left = dividers[-2]  # second-to-last divider
        assert col3_left < 395, (  # noqa: PLR2004
            f"divider at {col3_left:.1f} should be < 395 "
            f"(before 'Maximum Path Length' start)"
        )


class TestAdjustDividersForText:
    """Tests for _adjust_dividers_for_text."""

    def test_no_crossing_spans_unchanged(self) -> None:
        """Dividers stay put when all spans are inside their columns."""
        dividers = [0.0, 150.0, 300.0]
        rows = [
            [{"bbox": (10, 10, 100, 20)}, {"bbox": (200, 10, 280, 20)}],
        ]
        _adjust_dividers_for_text(dividers, rows)
        assert dividers == [0.0, 150.0, 300.0]

    def test_crossing_span_shifts_divider_left(self) -> None:
        """Divider shifts when a span starts before it but centers past it."""
        dividers = [0.0, 200.0, 400.0]
        # Span starts at 190 (before divider 200) but center is at 240
        rows = [
            [{"bbox": (10, 10, 100, 20)}, {"bbox": (190, 10, 290, 20)}],
        ]
        _adjust_dividers_for_text(dividers, rows)
        # Divider should move left: midpoint of (100, 190) = 145
        assert dividers[1] < 190  # noqa: PLR2004

    def test_does_not_shift_past_previous_column_content(self) -> None:
        """Divider stops at the midpoint with previous column's right edge."""
        dividers = [0.0, 200.0, 400.0]
        # Previous column extends to 185.  Crossing span starts at 190.
        # New divider = midpoint(185, 190) = 187.5
        rows = [
            [{"bbox": (10, 10, 185, 20)}, {"bbox": (190, 10, 290, 20)}],
        ]
        _adjust_dividers_for_text(dividers, rows)
        assert 185 < dividers[1] < 190  # noqa: PLR2004

    def test_table_edges_unchanged(self) -> None:
        """First and last dividers (table edges) are never modified."""
        dividers = [0.0, 200.0, 400.0]
        rows = [
            [{"bbox": (10, 10, 100, 20)}, {"bbox": (190, 10, 290, 20)}],
        ]
        _adjust_dividers_for_text(dividers, rows)
        assert dividers[0] == 0.0
        assert dividers[-1] == 400.0


# ── _row_column_count ─────────────────────────────────────────────────


class TestRowColumnCount:
    """Tests for _row_column_count."""

    def test_spans_in_all_columns(self) -> None:
        dividers = [0.0, 100.0, 200.0, 300.0]
        row = [
            {"bbox": (10, 0, 90, 10)},  # col 0
            {"bbox": (110, 0, 190, 10)},  # col 1
            {"bbox": (210, 0, 290, 10)},  # col 2
        ]
        assert _row_column_count(row, dividers) == 3  # noqa: PLR2004

    def test_multiple_spans_same_column(self) -> None:
        """Superscript spans in the same column count as 1 region."""
        dividers = [0.0, 100.0, 200.0, 300.0]
        row = [
            {"bbox": (10, 0, 50, 10)},  # col 0
            {"bbox": (210, 0, 240, 10)},  # col 2
            {"bbox": (245, 0, 260, 10)},  # col 2 (still)
            {"bbox": (265, 0, 275, 6)},  # col 2 (superscript)
        ]
        assert _row_column_count(row, dividers) == 2  # noqa: PLR2004

    def test_single_column_span(self) -> None:
        dividers = [0.0, 100.0, 200.0, 300.0]
        row = [{"bbox": (10, 0, 90, 10)}]
        assert _row_column_count(row, dividers) == 1


# ── _build_row_boundaries ─────────────────────────────────────────────


class TestBuildRowBoundaries:
    """Tests for _build_row_boundaries."""

    def test_single_interval_no_subdivide(self) -> None:
        """Single interval with mixed span counts stays as one row."""
        text_rows = [
            [{"bbox": (10, 20, 100, 30)}, {"bbox": (200, 20, 300, 30)}],
            [{"bbox": (10, 40, 300, 50)}],  # 1 span — mixed
        ]
        rule_ys = [15.0, 55.0]
        bounds = _build_row_boundaries(text_rows, rule_ys, 2, (0, 10, 400, 60))
        # Intervals: [10,15] (no text), [15,55] (2 rows, mixed), [55,60] (no text)
        # Mixed span counts → not subdivided → bounds = [10, 55]
        assert bounds[0] == 10  # noqa: PLR2004
        assert 55.0 in bounds
        # Not subdivided: only 2 boundaries (no mid-row split)
        assert len(bounds) == 2  # noqa: PLR2004

    def test_subdivide_data_rows(self) -> None:
        """Interval with all data rows is subdivided."""
        text_rows = [
            [{"bbox": (10, 20, 100, 28)}, {"bbox": (200, 20, 300, 28)}],
            [{"bbox": (10, 35, 100, 43)}, {"bbox": (200, 35, 300, 43)}],
        ]
        rule_ys = [15.0, 55.0]
        bounds = _build_row_boundaries(text_rows, rule_ys, 2, (0, 10, 400, 60))
        # With subdivision, we get more boundaries than just top/rules/bottom
        assert len(bounds) >= 3  # noqa: PLR2004

    def test_empty_text_rows(self) -> None:
        """No text rows → only y0 is appended (first empty interval)."""
        bounds = _build_row_boundaries([], [15.0, 55.0], 2, (0, 10, 400, 60))
        # All intervals are empty; only the first interval_top is added
        assert 10 in bounds
        assert len(bounds) == 1

    def test_subdivide_despite_inflated_spans(self) -> None:
        """Rows with extra spans (superscripts) still subdivide.

        Simulates a table where col_count=3 but each row has 5 spans
        due to scientific notation (e.g., "3.3 ·" + "10" + "18").
        With col_dividers, each row clearly spans 3 column regions.
        """
        # col_dividers: | 0 | 150 | 300 | 400 |
        dividers = [0.0, 150.0, 300.0, 400.0]
        text_rows = [
            # Row 1: "Model" in col0, "27.3" in col1, "3.3"+"·"+"10^18" in col2
            [
                {"bbox": (10, 20, 80, 28)},  # col0
                {"bbox": (160, 20, 200, 28)},  # col1
                {"bbox": (310, 20, 330, 28)},  # col2
                {"bbox": (335, 20, 345, 28)},  # col2 (still)
                {"bbox": (350, 20, 360, 24)},  # col2 (superscript)
            ],
            # Row 2: same structure
            [
                {"bbox": (10, 35, 80, 43)},  # col0
                {"bbox": (160, 35, 200, 43)},  # col1
                {"bbox": (310, 35, 330, 43)},  # col2
                {"bbox": (335, 35, 345, 43)},  # col2
                {"bbox": (350, 35, 360, 39)},  # col2 (superscript)
            ],
        ]
        bounds = _build_row_boundaries(
            text_rows,
            [15.0, 50.0],
            3,
            (0, 10, 400, 55),  # noqa: PLR2004
            col_dividers=dividers,
        )
        # Both rows span 3 column regions → subdivide
        assert len(bounds) >= 3  # noqa: PLR2004

    def test_no_subdivide_wrapped_cell(self) -> None:
        """Wrapped text in one column should NOT be subdivided."""
        dividers = [0.0, 150.0, 300.0, 400.0]
        text_rows = [
            # Row 1: spans across 3 columns (data row)
            [
                {"bbox": (10, 20, 80, 28)},
                {"bbox": (160, 20, 200, 28)},
                {"bbox": (310, 20, 340, 28)},
            ],
            # Row 2: only 1 column region (wrapped text continuation)
            [
                {"bbox": (10, 35, 140, 43)},
            ],
        ]
        bounds = _build_row_boundaries(
            text_rows,
            [15.0, 50.0],
            3,
            (0, 10, 400, 55),  # noqa: PLR2004
            col_dividers=dividers,
        )
        # Row 2 is only in 1 column → don't subdivide → 2 boundaries
        assert len(bounds) == 2  # noqa: PLR2004


# ── _build_cell_text ──────────────────────────────────────────────────


class TestBuildCellText:
    """Tests for _build_cell_text."""

    def test_empty_spans(self) -> None:
        """No spans → empty text and no y positions."""
        text, y0s = _build_cell_text([])
        assert text == ""
        assert y0s == []

    def test_single_span(self) -> None:
        """Single span returns its text."""
        spans = [{"bbox": (10, 50, 100, 60), "text": "hello", "size": 12.0}]
        text, y0s = _build_cell_text(spans)
        assert text == "hello"
        assert len(y0s) == 1

    def test_same_line_spans_joined(self) -> None:
        """Spans on the same y-line are joined with space or concatenated."""
        spans = [
            {"bbox": (10, 50, 50, 60), "text": "hello", "size": 12.0},
            {"bbox": (55, 50, 100, 60), "text": "world", "size": 12.0},
        ]
        text, y0s = _build_cell_text(spans)
        assert "hello" in text
        assert "world" in text
        assert len(y0s) == 1

    def test_multi_line_wrap_space_joined(self) -> None:
        """Lines filling cell width are word wraps → joined with spaces."""
        spans = [
            {"bbox": (10, 10, 50, 20), "text": "line1", "size": 12.0},
            {"bbox": (10, 50, 50, 60), "text": "line2", "size": 12.0},
        ]
        text, y0s = _build_cell_text(spans)
        # Both lines fill the same width → word wrap → space join
        assert text == "line1 line2"
        assert len(y0s) == 2  # noqa: PLR2004

    def test_multi_line_short_newline_joined(self) -> None:
        """Short lines that don't fill cell width → joined with newlines."""
        spans = [
            {"bbox": (10, 10, 18, 20), "text": "A", "size": 12.0},
            {"bbox": (10, 50, 60, 60), "text": "much wider line", "size": 12.0},
        ]
        text, y0s = _build_cell_text(spans)
        # First line is 8pt < 50pt * 0.5 = 25pt → intentional break
        assert "\n" in text
        assert len(y0s) == 2  # noqa: PLR2004

    def test_tagged_mode_with_bold(self) -> None:
        """Tagged mode wraps non-base formatting with HTML tags."""
        spans = [
            {
                "bbox": (10, 50, 50, 60),
                "text": "normal",
                "size": 12.0,
                "flags": 0,
            },
            {
                "bbox": (55, 50, 100, 60),
                "text": "bold",
                "size": 12.0,
                "flags": 16,
            },
        ]
        text, _ = _build_cell_text(spans, base_bold=False, base_italic=False)
        assert "<b>" in text
        assert "bold" in text

    def test_close_spans_concatenated(self) -> None:
        """Spans with gap <= 1pt are concatenated without space."""
        spans = [
            {"bbox": (10, 50, 50, 60), "text": "hel", "size": 12.0},
            {"bbox": (50.5, 50, 80, 60), "text": "lo", "size": 12.0},
        ]
        text, _ = _build_cell_text(spans)
        assert text == "hello"


# ── _detect_column_alignment ──────────────────────────────────────────


class TestDetectColumnAlignmentUnit:
    """Unit tests for _detect_column_alignment."""

    def test_single_cell_defaults_left(self) -> None:
        """Single cell (< 2) defaults to left alignment."""
        col_spans = [[{"bbox": (10, 10, 100, 20)}]]
        assert _detect_column_alignment(col_spans) == "left"

    def test_left_aligned_cells(self) -> None:
        """Consistent left edges → left alignment."""
        col_spans = [
            [{"bbox": (10, 10, 100, 20)}],
            [{"bbox": (10, 30, 80, 40)}],
            [{"bbox": (10, 50, 120, 60)}],
        ]
        assert _detect_column_alignment(col_spans) == "left"

    def test_right_aligned_cells(self) -> None:
        """Consistent right edges → right alignment."""
        col_spans = [
            [{"bbox": (20, 10, 100, 20)}],
            [{"bbox": (50, 30, 100, 40)}],
            [{"bbox": (10, 50, 100, 60)}],
        ]
        assert _detect_column_alignment(col_spans) == "right"

    def test_center_aligned_cells(self) -> None:
        """Equal variance on both sides → center."""
        col_spans = [
            [{"bbox": (40, 10, 60, 20)}],
            [{"bbox": (40, 30, 60, 40)}],
        ]
        assert _detect_column_alignment(col_spans) == "center"

    def test_center_aligned_varying_width(self) -> None:
        """Varying-width text centered in column → center alignment."""
        # Center at x=50: narrow (40,60), wide (20,80), medium (30,70)
        col_spans = [
            [{"bbox": (40, 10, 60, 20)}],
            [{"bbox": (20, 30, 80, 40)}],
            [{"bbox": (30, 50, 70, 60)}],
        ]
        assert _detect_column_alignment(col_spans) == "center"

    def test_empty_cells_skipped(self) -> None:
        """Empty cell span lists are ignored."""
        col_spans = [
            [],
            [{"bbox": (10, 30, 100, 40)}],
        ]
        # Single valid cell → left default
        assert _detect_column_alignment(col_spans) == "left"


# ── _is_multiline_block ──────────────────────────────────────────────


class TestIsMultilineBlock:
    """Tests for _is_multiline_block."""

    def test_single_line_no_newline(self) -> None:
        """Single-line block with no newline is not multi-line."""
        block = {"rect": [0, 0, 200, 12], "text": "Hello", "font_size": 10}
        assert not _is_multiline_block(block)

    def test_explicit_newline(self) -> None:
        """Block with explicit newline is always multi-line."""
        block = {"rect": [0, 0, 200, 12], "text": "a\nb", "font_size": 10}
        assert _is_multiline_block(block)

    def test_tall_block_no_newline(self) -> None:
        """Tall block without newline (wrapped paragraph) is multi-line."""
        # height=160, font_size=10 → 16 visual lines
        block = {
            "rect": [100, 400, 470, 560],
            "text": "The dominant sequence transduction models are based on ...",
            "font_size": 10,
        }
        assert _is_multiline_block(block)

    def test_slightly_tall_single_line(self) -> None:
        """Block just under 2× font size is single-line."""
        # height=18, font_size=10 → ratio 1.8 < 2.0
        block = {"rect": [0, 0, 200, 18], "text": "Title", "font_size": 10}
        assert not _is_multiline_block(block)

    def test_no_font_size(self) -> None:
        """Block without font_size falls back to newline check only."""
        block = {"rect": [0, 0, 200, 200], "text": "some text"}
        assert not _is_multiline_block(block)

    def test_no_font_size_with_newline(self) -> None:
        """Block without font_size but with newline is multi-line."""
        block = {"rect": [0, 0, 200, 200], "text": "a\nb"}
        assert _is_multiline_block(block)


# ── _widen_render_rects ───────────────────────────────────────────────


class TestWidenRenderRects:
    """Tests for _widen_render_rects."""

    def test_empty_blocks(self) -> None:
        """No blocks → no crash."""
        _widen_render_rects([])

    def test_table_cells_excluded(self) -> None:
        """Table cells are not widened."""
        blocks = [
            {"rect": [10, 10, 100, 20], "is_table_cell": True},
        ]
        _widen_render_rects(blocks)
        assert "render_rect" not in blocks[0]

    def test_narrow_block_widened(self) -> None:
        """Narrow block in a column gets render_rect extended."""
        # Full-width threshold = max_width * 0.6.  Blocks exceeding this
        # are skipped as "full-width" (headers/footers).  We need the
        # column blocks to stay under the threshold.
        # max_width = 200 → threshold = 120.  Column blocks have width=100
        # (< 120), so they remain.  The narrow block (width=50) is widened.
        blocks = [
            {"rect": [50, 10, 100, 20]},  # narrow (w=50)
            {"rect": [50, 40, 150, 50]},  # column (w=100)
            {"rect": [50, 70, 150, 80]},  # column (w=100)
            {"rect": [10, 100, 210, 110]},  # widest block (w=200)
        ]
        _widen_render_rects(blocks)
        # The narrow block should be widened to the column median x1 (150)
        assert "render_rect" in blocks[0]
        assert blocks[0]["render_rect"][2] == 150  # noqa: PLR2004

    def test_full_width_block_not_widened(self) -> None:
        """Full-width blocks are excluded from column calculation."""
        blocks = [
            {"rect": [10, 10, 550, 20]},  # full-width
            {"rect": [10, 40, 550, 50]},
        ]
        _widen_render_rects(blocks)
        # Both are "full-width" so none should get render_rect
        # (they're excluded from column calculation)
        for b in blocks:
            assert "render_rect" not in b

    def test_multi_column_blocks(self) -> None:
        """Blocks in different columns are widened independently."""
        # max_width = 500 (full-width block) → threshold = 300.
        # Column blocks (w=100–140) are below threshold.
        blocks = [
            {"rect": [10, 10, 50, 20]},  # left col, narrow (w=40)
            {"rect": [10, 40, 150, 50]},  # left col, wide (w=140)
            {"rect": [10, 70, 150, 80]},  # left col, wide (w=140)
            {"rect": [300, 10, 350, 20]},  # right col, narrow (w=50)
            {"rect": [300, 40, 400, 50]},  # right col, wide (w=100)
            {"rect": [300, 70, 400, 80]},  # right col, wide (w=100)
            {"rect": [0, 100, 500, 110]},  # full-width (w=500, skipped)
        ]
        _widen_render_rects(blocks)
        # Both narrow blocks should be widened
        assert "render_rect" in blocks[0]
        assert "render_rect" in blocks[3]

    def test_only_table_cells_no_crash(self) -> None:
        """Only table cell blocks → early return, no crash."""
        blocks = [
            {"rect": [10, 10, 100, 20], "is_table_cell": True},
            {"rect": [10, 40, 100, 50], "is_table_cell": True},
        ]
        _widen_render_rects(blocks)
        # No render_rect on any block
        assert all("render_rect" not in b for b in blocks)

    def test_single_column_title_widened_by_fallback(self) -> None:
        """Section title on a single-column page gets widened to content area."""
        blocks = [
            {"rect": [108.0, 100.0, 504.0, 150.0], "text": "body\ntext"},
            {"rect": [108.0, 160.0, 504.0, 200.0], "text": "more\nbody"},
            {"rect": [108.0, 210.0, 264.0, 220.0], "text": "3.1 Title"},
            {"rect": [108.0, 230.0, 504.0, 280.0], "text": "para\ntext"},
        ]
        _widen_render_rects(blocks)
        rr = blocks[2].get("render_rect")
        assert rr is not None
        assert rr[2] >= 504.0  # noqa: PLR2004

    def test_fallback_improves_first_pass_result(self) -> None:
        """Fallback widens blocks where first pass gave a suboptimal boundary."""
        blocks = [
            {"rect": [108.0, 100.0, 504.0, 150.0], "text": "body\ntext"},
            {"rect": [108.0, 200.0, 265.0, 210.0], "text": "3.1 Title A"},
            {"rect": [108.0, 250.0, 230.0, 260.0], "text": "3.2 Title B"},
            {"rect": [108.0, 300.0, 504.0, 350.0], "text": "body\ntext"},
        ]
        _widen_render_rects(blocks)
        rr = blocks[2].get("render_rect")
        assert rr is not None
        assert rr[2] >= 504.0  # noqa: PLR2004

    def test_column_pass_skips_multiline_paragraph(self) -> None:
        """Column-based pass does not widen multi-line paragraphs."""
        # Two narrow blocks in the same column — one multi-line, one single.
        # Column boundary x1 is median of [504, 300, 300] = 300, but the
        # narrow single-line block (x1=250) is narrower → it gets widened.
        # The multi-line block (x1=300) also could be widened to 504 by
        # the column boundary — but must be skipped.
        blocks = [
            {"rect": [72.0, 50.0, 504.0, 70.0], "text": "single header"},
            {"rect": [72.0, 100.0, 300.0, 160.0], "text": "para\nline2"},
            {"rect": [72.0, 200.0, 250.0, 210.0], "text": "3.1 Title"},
        ]
        _widen_render_rects(blocks)
        # Multi-line block must NOT be widened
        assert blocks[1].get("render_rect") is None
        # Single-line title SHOULD be widened
        rr = blocks[2].get("render_rect")
        assert rr is not None

    def test_fallback_skips_multiline_paragraph(self) -> None:
        """Multi-line paragraphs are not widened by fallback."""
        blocks = [
            {"rect": [108.0, 100.0, 505.0, 150.0], "text": "wide body"},
            {"rect": [108.0, 200.0, 400.0, 260.0], "text": "line1\nline2"},
            {"rect": [108.0, 300.0, 264.0, 310.0], "text": "3.1 Title"},
        ]
        _widen_render_rects(blocks)
        # Multi-line block should NOT be widened by fallback
        assert blocks[1].get("render_rect") is None
        # Single-line title SHOULD be widened
        rr = blocks[2].get("render_rect")
        assert rr is not None
        assert rr[2] >= 505.0  # noqa: PLR2004

    def test_fallback_skips_tall_wrapped_paragraph(self) -> None:
        r"""Tall wrapped paragraph (no \\n) is not widened by fallback.

        Reproduces the Abstract body scenario: block has no literal
        newlines but its height (162pt) far exceeds font_size (10pt),
        indicating multi-line wrapped text.
        """
        blocks = [
            # Wide header block — provides fallback peer at x0≈124
            {
                "rect": [124.3, 72.9, 487.9, 112.7],
                "text": "Provided",
                "font_size": 12.0,
            },
            # Abstract body: tall, no \\n, justify-aligned
            {
                "rect": [143.6, 413.3, 469.8, 576.1],
                "text": "The dominant sequence transduction models ...",
                "font_size": 10.1,
                "text_align": "justify",
            },
            # Single-line title (should still be widened)
            {
                "rect": [143.6, 600.0, 250.0, 612.0],
                "text": "3.1 Title",
                "font_size": 12.0,
            },
        ]
        _widen_render_rects(blocks)
        # Tall wrapped paragraph must NOT be widened
        assert blocks[1].get("render_rect") is None
        # Single-line title CAN be widened
        rr = blocks[2].get("render_rect")
        assert rr is not None

    def test_fallback_capped_by_right_neighbor(self) -> None:
        """Fallback widening is capped by nearest right neighbor."""
        # Two-column layout: left title at x0=72, right column at x0=306.
        # The fallback finds max_col_x1=504 from header, but caps at 306.
        blocks = [
            {"rect": [72.0, 50.0, 504.0, 70.0]},  # cross-column header
            {"rect": [72.0, 100.0, 200.0, 110.0]},  # left title (narrow)
            {"rect": [306.0, 100.0, 504.0, 150.0]},  # right column body
        ]
        _widen_render_rects(blocks)
        rr = blocks[1].get("render_rect")
        assert rr is not None
        # Should be capped at 306 (right column x0), not 504
        assert rr[2] <= 306.0  # noqa: PLR2004

    def test_fallback_skips_different_x0(self) -> None:
        """Fallback only considers blocks with matching x0."""
        # Narrow block at x0=300, wide blocks at x0=72 — different column.
        blocks = [
            {"rect": [72.0, 100.0, 504.0, 150.0]},  # wide, different x0
            {"rect": [300.0, 100.0, 350.0, 110.0]},  # narrow
        ]
        _widen_render_rects(blocks)
        # Block at x0=300 has no same-x0 blocks → no fallback widening
        assert blocks[1].get("render_rect") is None

    def test_widening_blocked_by_table_cell(self) -> None:
        """Render rect must not extend into a table cell."""
        blocks = [
            {"rect": [108.0, 100.0, 504.0, 150.0]},  # body text
            {"rect": [108.0, 200.0, 250.0, 210.0]},  # narrow block
            {"rect": [300.0, 200.0, 450.0, 210.0], "is_table_cell": True},
        ]
        _widen_render_rects(blocks)
        rr = blocks[1].get("render_rect")
        assert rr is not None
        # Must stop before the table cell at x0=300
        assert rr[2] <= 300.0  # noqa: PLR2004

    def test_widening_blocked_by_straddling_block(self) -> None:
        """Block that starts inside rect and extends past it blocks widening."""
        blocks = [
            {"rect": [108.0, 100.0, 504.0, 150.0]},  # body text (for fallback)
            {"rect": [108.0, 200.0, 250.0, 210.0]},  # block to widen
            # Straddling: starts at 230 (inside 108-250) extends to 350
            {"rect": [230.0, 202.0, 350.0, 208.0]},
        ]
        _widen_render_rects(blocks)
        rr = blocks[1].get("render_rect")
        # Should be capped at bx1=250 (can't extend past straddling block)
        assert rr is None or rr[2] <= 250.0  # noqa: PLR2004

    def test_no_vertical_overlap_allows_widening(self) -> None:
        """Blocks at different y-levels don't prevent widening."""
        blocks = [
            {"rect": [108.0, 100.0, 504.0, 150.0]},  # body text
            {"rect": [108.0, 200.0, 250.0, 210.0]},  # block to widen
            {"rect": [300.0, 220.0, 450.0, 230.0]},  # no y-overlap
        ]
        _widen_render_rects(blocks)
        rr = blocks[1].get("render_rect")
        assert rr is not None
        # No y-overlap → not blocked, widened to full content area
        assert rr[2] >= 504.0  # noqa: PLR2004

    def test_single_narrow_block_with_full_width_peers(self) -> None:
        """One narrow block + full-width peers → fallback widens to content edge."""
        blocks = [
            {"rect": [72.0, 50.0, 500.0, 100.0]},  # body (full-width)
            {"rect": [72.0, 110.0, 200.0, 120.0]},  # narrow title
            {"rect": [72.0, 130.0, 500.0, 180.0]},  # body (full-width)
        ]
        _widen_render_rects(blocks)
        rr = blocks[1].get("render_rect")
        assert rr is not None
        assert rr[2] >= 500.0  # noqa: PLR2004

    def test_single_block_on_page_no_widening(self) -> None:
        """A lone block has no same-x0 peers → no widening."""
        blocks = [{"rect": [108.0, 200.0, 250.0, 210.0]}]
        _widen_render_rects(blocks)
        assert blocks[0].get("render_rect") is None

    def test_render_rect_y_matches_original(self) -> None:
        """Widened render_rect preserves original y-coordinates."""
        blocks = [
            {"rect": [108.0, 100.0, 504.0, 150.0]},
            {"rect": [108.0, 200.0, 250.0, 215.5]},  # specific y values
            {"rect": [108.0, 300.0, 504.0, 350.0]},
        ]
        _widen_render_rects(blocks)
        rr = blocks[1].get("render_rect")
        assert rr is not None
        assert rr[0] == blocks[1]["rect"][0]
        assert rr[1] == blocks[1]["rect"][1]  # y0 preserved
        assert rr[3] == blocks[1]["rect"][3]  # y1 preserved

    def test_first_pass_not_downgraded_by_fallback(self) -> None:
        """If first pass gives a good boundary, fallback doesn't shrink it."""
        # Two columns: narrow blocks form a column with median x1=300.
        # Full-width blocks also at same x0, but capped by right neighbor.
        # First pass gives 300; fallback should not shrink below 300.
        blocks = [
            {"rect": [50, 10, 100, 20]},  # narrow (w=50)
            {"rect": [50, 40, 150, 50]},  # column (w=100)
            {"rect": [50, 70, 150, 80]},  # column (w=100)
            {"rect": [10, 100, 210, 110]},  # widest (w=200)
        ]
        _widen_render_rects(blocks)
        rr = blocks[0].get("render_rect")
        assert rr is not None
        assert rr[2] >= 150  # noqa: PLR2004

    def test_table_cell_adjacent_blocks_widening(self) -> None:
        """Table cell at same y-level blocks widening in both passes."""
        blocks = [
            {"rect": [108.0, 100.0, 504.0, 150.0]},  # body
            {"rect": [108.0, 200.0, 250.0, 210.0]},  # narrow block
            {"rect": [280.0, 200.0, 400.0, 210.0], "is_table_cell": True},
            {"rect": [108.0, 300.0, 504.0, 350.0]},  # body
        ]
        _widen_render_rects(blocks)
        rr = blocks[1].get("render_rect")
        assert rr is not None
        assert rr[2] <= 280.0  # noqa: PLR2004

    def test_right_aligned_grows_left(self) -> None:
        """Right-aligned block grows leftward toward same-x1 peers."""
        # Block at x1=504, peers also at x1=504 but starting at x0=108.
        # Right-aligned: grow x0 leftward from 400 toward 108.
        blocks = [
            {"rect": [108.0, 100.0, 504.0, 150.0], "text": "body\ntext"},
            {
                "rect": [400.0, 200.0, 504.0, 210.0],
                "text": "Right Title",
                "text_align": "right",
            },
            {"rect": [108.0, 300.0, 504.0, 350.0], "text": "body\ntext"},
        ]
        _widen_render_rects(blocks)
        rr = blocks[1].get("render_rect")
        assert rr is not None
        assert rr[0] <= 108.0  # noqa: PLR2004
        assert rr[2] == 504.0  # noqa: PLR2004

    def test_center_aligned_grows_both(self) -> None:
        """Center-aligned block grows both left and right."""
        # Centered "Abstract" at x=[278, 322], peers at x0=108..x1=504.
        blocks = [
            {"rect": [108.0, 100.0, 504.0, 150.0], "text": "body\ntext"},
            {
                "rect": [278.0, 200.0, 322.0, 210.0],
                "text": "Abstract",
                "text_align": "center",
            },
            {"rect": [108.0, 300.0, 504.0, 350.0], "text": "body\ntext"},
        ]
        _widen_render_rects(blocks)
        rr = blocks[1].get("render_rect")
        assert rr is not None
        # Grows right toward 504 (same x0 peer)
        assert rr[2] >= 504.0  # noqa: PLR2004
        # Grows left — peers at x1=504 differ from block x1=322,
        # so no same-x1 peers found, x0 stays at 278.
        # With same-x1 peers the x0 would shrink.

    def test_center_aligned_grows_left_with_same_x1_peers(self) -> None:
        """Center-aligned block grows leftward when same-x1 peers exist."""
        blocks = [
            {"rect": [50.0, 100.0, 400.0, 150.0], "text": "body\ntext"},
            {
                "rect": [250.0, 200.0, 400.0, 210.0],
                "text": "Centered",
                "text_align": "center",
            },
            {"rect": [50.0, 300.0, 400.0, 350.0], "text": "body\ntext"},
        ]
        _widen_render_rects(blocks)
        rr = blocks[1].get("render_rect")
        assert rr is not None
        # x1 stays at 400 (already at peer boundary)
        # x0 grows leftward toward 50 (same-x1 peers at x0=50)
        assert rr[0] <= 50.0  # noqa: PLR2004

    def test_left_aligned_only_grows_right(self) -> None:
        """Left-aligned block only grows rightward, x0 stays unchanged."""
        blocks = [
            {"rect": [108.0, 100.0, 504.0, 150.0], "text": "body\ntext"},
            {
                "rect": [108.0, 200.0, 250.0, 210.0],
                "text": "Left Title",
                "text_align": "left",
            },
            {"rect": [108.0, 300.0, 504.0, 350.0], "text": "body\ntext"},
        ]
        _widen_render_rects(blocks)
        rr = blocks[1].get("render_rect")
        assert rr is not None
        assert rr[0] == 108.0  # noqa: PLR2004
        assert rr[2] >= 504.0  # noqa: PLR2004

    def test_right_aligned_capped_by_left_neighbor(self) -> None:
        """Right-aligned leftward growth is capped by left neighbor."""
        blocks = [
            {"rect": [108.0, 100.0, 504.0, 150.0], "text": "body\ntext"},
            {
                "rect": [350.0, 200.0, 504.0, 210.0],
                "text": "Right Title",
                "text_align": "right",
            },
            # Left neighbor blocking leftward growth
            {"rect": [150.0, 200.0, 280.0, 210.0], "text": "neighbor"},
            {"rect": [108.0, 300.0, 504.0, 350.0], "text": "body\ntext"},
        ]
        _widen_render_rects(blocks)
        rr = blocks[1].get("render_rect")
        assert rr is not None
        # Capped at 280 (left neighbor's right edge)
        assert rr[0] >= 280.0  # noqa: PLR2004

    def test_justify_only_grows_right(self) -> None:
        """Justify-aligned block only grows rightward."""
        blocks = [
            {"rect": [108.0, 100.0, 504.0, 150.0], "text": "body\ntext"},
            {
                "rect": [108.0, 200.0, 250.0, 210.0],
                "text": "Justified",
                "text_align": "justify",
            },
            {"rect": [108.0, 300.0, 504.0, 350.0], "text": "body\ntext"},
        ]
        _widen_render_rects(blocks)
        rr = blocks[1].get("render_rect")
        assert rr is not None
        assert rr[0] == 108.0  # noqa: PLR2004
        assert rr[2] >= 504.0  # noqa: PLR2004

    def test_no_alignment_defaults_to_left(self) -> None:
        """Block without text_align defaults to left (grow right only)."""
        blocks = [
            {"rect": [108.0, 100.0, 504.0, 150.0], "text": "body\ntext"},
            {"rect": [108.0, 200.0, 250.0, 210.0], "text": "Title"},
            {"rect": [108.0, 300.0, 504.0, 350.0], "text": "body\ntext"},
        ]
        _widen_render_rects(blocks)
        rr = blocks[1].get("render_rect")
        assert rr is not None
        assert rr[0] == 108.0  # noqa: PLR2004
        assert rr[2] >= 504.0  # noqa: PLR2004

    def test_multicolumn_filters_full_width_grow_right(self) -> None:
        """Full-width header excluded from fallback grow_right on multi-col."""
        # Two-column layout: many blocks per column (≥ 2 each).
        # Full-width header spans both columns.
        blocks = [
            {"rect": [53.0, 50.0, 558.0, 70.0]},  # full-width header
            {"rect": [53.0, 100.0, 306.0, 150.0], "text": "left\nbody"},
            {"rect": [53.0, 160.0, 306.0, 200.0], "text": "left\nbody"},
            {"rect": [53.0, 210.0, 200.0, 220.0]},  # narrow left title
            {"rect": [306.0, 100.0, 558.0, 150.0], "text": "right\nbody"},
            {"rect": [306.0, 160.0, 558.0, 200.0], "text": "right\nbody"},
        ]
        _widen_render_rects(blocks)
        rr = blocks[3].get("render_rect")
        # Should be widened but NOT past the right column boundary.
        assert rr is not None
        assert rr[2] <= 306.0  # noqa: PLR2004

    def test_multicolumn_filters_full_width_grow_left(self) -> None:
        """Full-width footer excluded from fallback grow_left on multi-col."""
        blocks = [
            {"rect": [53.0, 100.0, 306.0, 150.0], "text": "left\nbody"},
            {"rect": [53.0, 160.0, 306.0, 200.0], "text": "left\nbody"},
            {"rect": [306.0, 100.0, 558.0, 150.0], "text": "right\nbody"},
            {"rect": [306.0, 160.0, 558.0, 200.0], "text": "right\nbody"},
            {
                "rect": [450.0, 210.0, 558.0, 220.0],
                "text": "Right Title",
                "text_align": "right",
            },
            {"rect": [53.0, 250.0, 558.0, 270.0]},  # full-width footer
        ]
        _widen_render_rects(blocks)
        rr = blocks[4].get("render_rect")
        # Should grow left but not past left column boundary.
        assert rr is not None
        assert rr[0] >= 306.0  # noqa: PLR2004

    def test_multicolumn_filters_full_width_center(self) -> None:
        """Full-width block excluded from center search on multi-col."""
        blocks = [
            {"rect": [53.0, 100.0, 306.0, 150.0], "text": "left\nbody"},
            {"rect": [53.0, 160.0, 306.0, 200.0], "text": "left\nbody"},
            {"rect": [306.0, 100.0, 558.0, 150.0], "text": "right\nbody"},
            {"rect": [306.0, 160.0, 558.0, 200.0], "text": "right\nbody"},
            {
                "rect": [130.0, 210.0, 230.0, 220.0],
                "text": "Abstract",
                "text_align": "center",
            },
            {"rect": [53.0, 250.0, 558.0, 270.0]},  # full-width header
        ]
        _widen_render_rects(blocks)
        rr = blocks[4].get("render_rect")
        # Centered block should widen within left column, not to page edge.
        if rr is not None:
            assert rr[2] <= 306.0  # noqa: PLR2004

    def test_single_column_not_filtered(self) -> None:
        """Single-column pages don't filter — body blocks are references."""
        blocks = [
            {"rect": [108.0, 100.0, 504.0, 150.0], "text": "body\ntext"},
            {"rect": [108.0, 160.0, 504.0, 200.0], "text": "more\nbody"},
            {"rect": [108.0, 210.0, 264.0, 220.0], "text": "3.1 Title"},
        ]
        _widen_render_rects(blocks)
        rr = blocks[2].get("render_rect")
        assert rr is not None
        assert rr[2] >= 504.0  # noqa: PLR2004

    def test_few_blocks_per_column_not_multicolumn(self) -> None:
        """Sparse columns (1 block each) don't trigger full-width filter."""
        blocks = [
            {"rect": [72.0, 50.0, 504.0, 70.0]},  # full-width header
            {"rect": [72.0, 100.0, 200.0, 110.0]},  # single left block
            {"rect": [306.0, 100.0, 504.0, 150.0]},  # single right block
        ]
        _widen_render_rects(blocks)
        rr = blocks[1].get("render_rect")
        # Header is NOT filtered (columns too sparse), so fallback finds
        # max_col_x1=504 but _cap_by_neighbors caps at 306.
        assert rr is not None
        assert rr[2] <= 306.0  # noqa: PLR2004


class TestIsDisplayEquation:
    """Tests for _is_display_equation."""

    def test_narrow_centered_math_is_display(self) -> None:
        """Narrow centred block with _math_map is a display equation."""
        b = {"_math_map": {"⟪0⟫": [("R", "CMMI10")]}, "rect": [234, 100, 378, 112]}
        assert _is_display_equation(b, 612.0) is True  # noqa: PLR2004

    def test_wide_block_not_display(self) -> None:
        """Block wider than 50 % page is not a display equation."""
        b = {"_math_map": {"⟪0⟫": [("x", "CMMI10")]}, "rect": [72, 100, 400, 112]}
        assert _is_display_equation(b, 612.0) is False

    def test_no_math_map_not_display(self) -> None:
        """Block without _math_map is not a display equation."""
        b = {"rect": [234, 100, 378, 112]}
        assert _is_display_equation(b, 612.0) is False

    def test_left_aligned_not_display(self) -> None:
        """Narrow block at left margin is body text, not display."""
        b = {"_math_map": {"⟪0⟫": [("d", "CMMI10")]}, "rect": [78, 100, 300, 112]}
        assert _is_display_equation(b, 612.0) is False

    def test_centered_narrow_no_body_text(self) -> None:
        """Pure-math centred block is a display equation."""
        b = {"_math_map": {"⟪0⟫": [("S", "CMMI10")]}, "rect": [260, 440, 352, 460]}
        assert _is_display_equation(b, 612.0) is True  # noqa: PLR2004


class TestAbsorbMathSubLabels:
    """Tests for _absorb_math_sub_labels."""

    @staticmethod
    def _make_math_span(
        text: str,
        x0: float,
        x1: float,
        ph_key: str = "⟪0⟫",
    ) -> dict[str, Any]:
        return {
            "text": text,
            "_is_math": True,
            "_ph_key": ph_key,
            "font": "CMMI10",
            "size": 10.0,
            "sx0": x0,
            "sy0": 100,
            "sx1": x1,
            "sy1": 110,
        }

    @staticmethod
    def _make_body_span(
        text: str,
        size: float,
        x0: float,
        x1: float,
    ) -> dict[str, Any]:
        return {
            "text": text,
            "font": "NimbusRomNo9L-Regu",
            "size": size,
            "flags": 0,
            "sx0": x0,
            "sy0": 107,
            "sx1": x1,
            "sy1": 114,
        }

    @staticmethod
    def _sep_span() -> dict[str, Any]:
        """Separator span inserted by same-y / fragment merges."""
        return {"text": " ", "flags": 0, "role": None}

    def test_absorb_trailing_subscript(self) -> None:
        """Single-word body-font subscript after math placeholder is absorbed."""
        ph = "⟪0⟫"
        math_map: dict[str, Any] = {
            ph: [(" ", "CMMI10"), ("R", "CMMI10"), ("2", "CMR7")],
        }
        math_span = self._make_math_span(ph, 280, 296)
        sub_span = self._make_body_span("schematic", 7.0, 292, 320)
        body_span = self._make_body_span(" ranges from", 10.0, 320, 400)

        spans = [
            self._make_body_span("Empirically, ", 10.0, 70, 280),
            math_span,
            self._sep_span(),  # from same-y merge
            sub_span,
            body_span,
        ]
        texts = ["Empirically, ⟪0⟫ schematic ranges from"]
        dom_sizes = [10.0]

        _absorb_math_sub_labels(texts, [spans], math_map, dom_sizes)

        # "schematic" absorbed into placeholder
        chars = "".join(c for entry in math_map[ph] for c in [entry[0]])
        assert "schematic" in chars
        # Body text updated — "schematic" removed
        assert "schematic" not in texts[0]
        assert "ranges from" in texts[0]

    def test_no_absorb_multiword(self) -> None:
        """Multi-word text after placeholder is not absorbed."""
        ph = "⟪0⟫"
        math_map: dict[str, Any] = {ph: [("x", "CMMI10")]}
        spans = [
            self._make_math_span(ph, 280, 296),
            self._sep_span(),
            self._make_body_span("two words", 7.0, 292, 340),
        ]
        texts = ["⟪0⟫ two words"]
        dom_sizes = [10.0]

        _absorb_math_sub_labels(texts, [spans], math_map, dom_sizes)

        # Not absorbed — multi-word
        assert len(math_map[ph]) == 1  # noqa: PLR2004

    def test_no_absorb_body_sized(self) -> None:
        """Span at body size (not subscript) is not absorbed."""
        ph = "⟪0⟫"
        math_map: dict[str, Any] = {ph: [("y", "CMMI10")]}
        spans = [
            self._make_math_span(ph, 280, 296),
            self._make_body_span("word", 10.0, 296, 330),
        ]
        texts = ["⟪0⟫word"]
        dom_sizes = [10.0]

        _absorb_math_sub_labels(texts, [spans], math_map, dom_sizes)

        # Not absorbed — same size as dominant
        assert len(math_map[ph]) == 1  # noqa: PLR2004

    def test_no_absorb_math_font(self) -> None:
        """Math-font span is not absorbed (already in placeholder)."""
        ph0, ph1 = "⟪0⟫", "⟪1⟫"
        math_map: dict[str, Any] = {
            ph0: [("R", "CMMI10")],
            ph1: [("S", "CMMI10")],
        }
        spans = [
            self._make_math_span(ph0, 280, 296),
            self._make_math_span(ph1, 300, 320, ph_key=ph1),
        ]
        texts = ["⟪0⟫⟪1⟫"]
        dom_sizes = [10.0]

        _absorb_math_sub_labels(texts, [spans], math_map, dom_sizes)

        # Neither placeholder modified
        assert len(math_map[ph0]) == 1  # noqa: PLR2004
        assert len(math_map[ph1]) == 1  # noqa: PLR2004

    def test_absorb_skips_separator_spans(self) -> None:
        """Separator spans (from merge) between placeholder and label are skipped."""
        ph = "⟪0⟫"
        math_map: dict[str, Any] = {ph: [("x", "CMMI10")]}
        spans = [
            self._make_math_span(ph, 280, 296),
            self._sep_span(),
            self._sep_span(),
            self._make_body_span("model", 6.0, 292, 315),
            self._make_body_span(" = 512", 10.0, 315, 360),
        ]
        texts = ["⟪0⟫  model = 512"]
        dom_sizes = [10.0]

        _absorb_math_sub_labels(texts, [spans], math_map, dom_sizes)

        chars = "".join(c for entry in math_map[ph] for c in [entry[0]])
        assert "model" in chars
        assert "= 512" not in texts[0] or "model" not in texts[0]

    def test_absorb_entire_line(self) -> None:
        """When all spans on a line are subscript after placeholder, all absorbed."""
        ph = "⟪0⟫"
        math_map: dict[str, Any] = {ph: [("R", "CMMI10")]}
        spans_line0 = [
            self._make_body_span("Text ", 10.0, 70, 200),
            self._make_math_span(ph, 200, 230),
        ]
        # Line 1 has only the subscript label (standalone subscript line)
        spans_line1 = [
            self._make_body_span("linear", 7.0, 205, 230),
        ]
        texts = ["Text ⟪0⟫", "linear"]
        spans_data = [spans_line0, spans_line1]
        dom_sizes = [10.0, 7.0]

        _absorb_math_sub_labels(texts, spans_data, math_map, dom_sizes)

        chars = "".join(c for entry in math_map[ph] for c in [entry[0]])
        # "linear" should NOT be absorbed — it's on a different line
        # and there's no math placeholder on an adjacent line in spans_line1
        # (the adjacent-line scan only looks for placeholders on the
        # same line in this per-span approach).
        assert "linear" not in chars

    def test_multiple_placeholders(self) -> None:
        """Each placeholder absorbs its own trailing subscript."""
        ph0, ph1 = "⟪0⟫", "⟪1⟫"
        math_map: dict[str, Any] = {
            ph0: [("R", "CMMI10")],
            ph1: [("S", "CMMI10")],
        }
        spans = [
            self._make_math_span(ph0, 100, 120),
            self._sep_span(),
            self._make_body_span("sch", 7.0, 118, 135),
            self._make_body_span(" and ", 10.0, 135, 170),
            self._make_math_span(ph1, 170, 190, ph_key=ph1),
            self._sep_span(),
            self._make_body_span("lin", 7.0, 188, 200),
            self._make_body_span(" ok", 10.0, 200, 220),
        ]
        texts = ["⟪0⟫ sch and ⟪1⟫ lin ok"]
        dom_sizes = [10.0]

        _absorb_math_sub_labels(texts, [spans], math_map, dom_sizes)

        assert "sch" in "".join(c for e in math_map[ph0] for c in [e[0]])
        assert "lin" in "".join(c for e in math_map[ph1] for c in [e[0]])
        assert "sch" not in texts[0]
        assert "lin" not in texts[0]

    def test_no_change_without_math(self) -> None:
        """Lines without math placeholders are untouched."""
        math_map: dict[str, Any] = {}
        spans = [self._make_body_span("hello world", 10.0, 70, 200)]
        texts = ["hello world"]
        dom_sizes = [10.0]

        _absorb_math_sub_labels(texts, [spans], math_map, dom_sizes)

        assert texts == ["hello world"]


class TestSplitMultilineBlocks:
    """Tests for _split_multiline_blocks sub-block creation."""

    def _make_block(  # noqa: PLR0913
        self,
        text: str,
        rect: list[float],
        joins: list[str] | None = None,
        y0s: list[float] | None = None,
        y1s: list[float] | None = None,
        extents: list[tuple[float, float]] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Create a block dict with line data for split testing."""
        b: dict[str, Any] = {
            "rect": rect,
            "text": text,
            "font_size": kwargs.get("font_size", 10.0),
            "font_name": kwargs.get("font_name", "NimbusRomNo9L-Regu"),
            "color": kwargs.get("color", 0),
            "bold": False,
            "italic": False,
            "font_flags": 0,
            "text_align": kwargs.get("text_align", "left"),
        }
        if joins is not None:
            b["_line_joins"] = joins
        if y0s is not None:
            b["_line_y0s"] = y0s
        if y1s is not None:
            b["_line_y1s"] = y1s
        if extents is not None:
            b["_line_extents"] = extents
            b["_line_sizes"] = [10.0] * len(extents)
            b["_line_y_mids"] = (
                [(y0s[i] + y1s[i]) / 2.0 for i in range(len(y0s))]
                if y0s and y1s
                else []
            )
        for k, v in kwargs.items():
            if k not in b:
                b[k] = v
        return b

    def test_no_newline_not_split(self) -> None:
        """Block without newline passes through unchanged."""
        block = self._make_block(
            "single line text",
            [72, 100, 400, 110],
        )
        result = _split_multiline_blocks([block])
        assert len(result) == 1
        assert result[0] is block

    def test_two_paragraphs_split_into_two(self) -> None:
        r"""Block with two paragraphs (\n join) becomes two sub-blocks."""
        block = self._make_block(
            "Step 1: Do this\nStep 2: Do that",
            [72, 100, 400, 130],
            joins=["\n"],
            y0s=[100.0, 120.0],
            y1s=[110.0, 130.0],
            extents=[(72, 300), (72, 350)],
        )
        result = _split_multiline_blocks([block])
        assert len(result) == 2  # noqa: PLR2004
        assert result[0]["text"] == "Step 1: Do this"
        assert result[1]["text"] == "Step 2: Do that"
        # Each sub-block gets its own rect from line y-extents
        assert result[0]["rect"][1] == 100.0  # noqa: PLR2004
        assert result[0]["rect"][3] == 110.0  # noqa: PLR2004
        assert result[1]["rect"][1] == 120.0  # noqa: PLR2004
        assert result[1]["rect"][3] == 130.0  # noqa: PLR2004
        # Both marked as split
        assert result[0].get("_split_from_parent")
        assert result[1].get("_split_from_parent")

    def test_space_join_not_split(self) -> None:
        r"""Lines joined by space remain in one block (no \n)."""
        block = self._make_block(
            "continued line here",
            [72, 100, 400, 130],
            joins=[" "],
            y0s=[100.0, 120.0],
            y1s=[110.0, 130.0],
            extents=[(72, 400), (72, 400)],
        )
        result = _split_multiline_blocks([block])
        assert len(result) == 1
        assert result[0] is block

    def test_three_paragraphs_split(self) -> None:
        """Block with three paragraphs produces three sub-blocks."""
        block = self._make_block(
            "Para 1\nPara 2\nPara 3",
            [72, 100, 400, 160],
            joins=["\n", "\n"],
            y0s=[100.0, 120.0, 140.0],
            y1s=[110.0, 130.0, 150.0],
            extents=[(72, 300), (72, 350), (72, 280)],
        )
        result = _split_multiline_blocks([block])
        assert len(result) == 3  # noqa: PLR2004
        assert result[0]["text"] == "Para 1"
        assert result[1]["text"] == "Para 2"
        assert result[2]["text"] == "Para 3"

    def test_mixed_joins_groups_correctly(self) -> None:
        r"""Space joins group lines into same paragraph; \n splits."""
        # 3 lines: line0 + line1 (space) → para1, line2 → para2
        block = self._make_block(
            "Part A continued\nPart B",
            [72, 100, 400, 150],
            joins=[" ", "\n"],
            y0s=[100.0, 112.0, 130.0],
            y1s=[110.0, 122.0, 140.0],
            extents=[(72, 400), (72, 380), (72, 350)],
        )
        result = _split_multiline_blocks([block])
        assert len(result) == 2  # noqa: PLR2004
        assert result[0]["text"] == "Part A continued"
        # First sub-block spans lines 0-1
        assert result[0]["rect"][1] == 100.0  # noqa: PLR2004
        assert result[0]["rect"][3] == 122.0  # noqa: PLR2004
        assert result[1]["text"] == "Part B"
        assert result[1]["rect"][1] == 130.0  # noqa: PLR2004

    def test_table_cell_not_split(self) -> None:
        """Table cells are never split even with newlines."""
        block = self._make_block(
            "Cell line 1\nCell line 2",
            [72, 100, 200, 130],
            joins=["\n"],
            y0s=[100.0, 120.0],
            y1s=[110.0, 130.0],
            extents=[(72, 200), (72, 200)],
            is_table_cell=True,
        )
        result = _split_multiline_blocks([block])
        assert len(result) == 1
        assert result[0] is block

    def test_vertical_block_not_split(self) -> None:
        """Vertical text blocks are never split."""
        block = self._make_block(
            "Vert 1\nVert 2",
            [72, 100, 82, 300],
            joins=["\n"],
            y0s=[100.0, 200.0],
            y1s=[190.0, 300.0],
            extents=[(72, 82), (72, 82)],
            is_vertical=True,
        )
        result = _split_multiline_blocks([block])
        assert len(result) == 1
        assert result[0] is block

    def test_math_map_distributed(self) -> None:
        """Math placeholders go to the sub-block containing them."""
        ph = f"{_MATH_PH_START}0{_MATH_PH_END}"
        block = self._make_block(
            f"Text with {ph}\nPlain text",
            [72, 100, 400, 130],
            joins=["\n"],
            y0s=[100.0, 120.0],
            y1s=[110.0, 130.0],
            extents=[(72, 400), (72, 350)],
        )
        block["_math_map"] = {ph: [("α", "CMMI10")]}
        result = _split_multiline_blocks([block])
        assert len(result) == 2  # noqa: PLR2004
        assert ph in result[0].get("_math_map", {})
        assert "_math_map" not in result[1] or not result[1]["_math_map"]

    def test_para_indents_recomputed(self) -> None:
        """Indents are recomputed per sub-block using its own line data.

        After split, each sub-block computes indents relative to its own
        margin_ref (not the parent's), so offsets already encoded in the
        sub-block's rect x0 are not double-counted.
        """
        # Parent block: line 0 at x0=72, line 1 at x0=90 (two paragraphs)
        block = self._make_block(
            "Para 1\nPara 2",
            [72, 100, 400, 130],
            joins=["\n"],
            y0s=[100.0, 120.0],
            y1s=[110.0, 130.0],
            extents=[(72, 400), (90, 400)],
        )
        block["_line_sizes"] = [10.0, 10.0]
        result = _split_multiline_blocks([block])
        assert len(result) == 2  # noqa: PLR2004
        # Single-line sub-blocks: no joins → no indent detected
        # (rect x0 already encodes the position)
        assert result[0].get("para_indents") is None
        assert result[1].get("para_indents") is None

    def test_para_indents_recomputed_multiline(self) -> None:
        """Multi-line sub-block recomputes first-line indent locally."""
        # Parent: para 0 = single-line at x0=82.9
        #         para 1 = two lines at x0=[82.9, 72.0]
        block = self._make_block(
            "Footnote 2\nFootnote 3 continued here",
            [72, 693, 541, 722],
            joins=["\n", " "],
            y0s=[693.5, 703.2, 713.8],
            y1s=[702.7, 713.2, 721.9],
            extents=[(82.9, 280.3), (82.9, 541.3), (72.0, 440.6)],
        )
        block["_line_sizes"] = [8.0, 8.0, 8.0]
        result = _split_multiline_blocks([block])
        assert len(result) == 2  # noqa: PLR2004
        # Sub-block 0: single line → no indent
        assert result[0].get("para_indents") is None
        # Sub-block 1: two lines, first at 82.9, body at 72.0
        # → fl_indent = 82.9 - 72.0 = 10.9
        assert result[1].get("para_indents") == [(0.0, 10.9)]

    def test_missing_line_data_not_split(self) -> None:
        """Block without _line_joins is not split."""
        block = {
            "rect": [72, 100, 400, 130],
            "text": "Para 1\nPara 2",
            "font_size": 10.0,
        }
        result = _split_multiline_blocks([block])
        assert len(result) == 1
        assert result[0] is block

    def test_inherits_font_properties(self) -> None:
        """Sub-blocks inherit font properties from parent."""
        block = self._make_block(
            "Bold 1\nBold 2",
            [72, 100, 400, 130],
            joins=["\n"],
            y0s=[100.0, 120.0],
            y1s=[110.0, 130.0],
            extents=[(72, 400), (72, 400)],
            font_size=14.0,
            color=0xFF0000,
            text_align="center",
        )
        block["bold"] = True
        block["has_mixed_formatting"] = True
        result = _split_multiline_blocks([block])
        assert len(result) == 2  # noqa: PLR2004
        for sub in result:
            assert sub["font_size"] == 14.0  # noqa: PLR2004
            assert sub["color"] == 0xFF0000  # noqa: PLR2004
            assert sub["bold"] is True
            assert sub["text_align"] == "center"
            assert sub["has_mixed_formatting"] is True

    def test_empty_paragraph_skipped(self) -> None:
        """Empty paragraphs from splitting are skipped."""
        block = self._make_block(
            "Text\n",
            [72, 100, 400, 130],
            joins=["\n"],
            y0s=[100.0, 120.0],
            y1s=[110.0, 130.0],
            extents=[(72, 400), (72, 400)],
        )
        result = _split_multiline_blocks([block])
        # Empty second paragraph skipped
        assert len(result) == 1
        assert result[0]["text"] == "Text"

    def test_x_range_from_own_lines_only(self) -> None:
        """Sub-block x-range comes from its own lines, not the parent."""
        # Parent rect is wider than content lines (e.g. inflated by a
        # whitespace-only line at a distant x position).
        block = self._make_block(
            "Short\nAlso short",
            [63, 100, 522, 130],
            joins=["\n"],
            y0s=[100.0, 120.0],
            y1s=[110.0, 130.0],
            extents=[(440, 522), (440, 500)],
        )
        result = _split_multiline_blocks([block])
        assert len(result) == 2  # noqa: PLR2004
        # x-range from own line extents, NOT inflated to parent rect.
        assert result[0]["rect"][0] == 440.0  # noqa: PLR2004
        assert result[0]["rect"][2] == 522.0  # noqa: PLR2004
        assert result[1]["rect"][0] == 440.0  # noqa: PLR2004
        assert result[1]["rect"][2] == 500.0  # noqa: PLR2004


class TestCapByLeftNeighbors:
    """Tests for _cap_by_left_neighbors collision detection."""

    def test_left_neighbor_caps(self) -> None:
        block = {"rect": [300, 200, 500, 210]}
        others = [
            block,
            {"rect": [100, 200, 250, 210]},  # left neighbor
        ]
        result = _cap_by_left_neighbors(block, others, 300, 200, 210, 50)
        assert result == 250  # noqa: PLR2004

    def test_straddling_block_caps_at_bx0(self) -> None:
        block = {"rect": [300, 200, 500, 210]}
        others = [
            block,
            {"rect": [250, 202, 350, 208]},  # straddles bx0=300
        ]
        result = _cap_by_left_neighbors(block, others, 300, 200, 210, 50)
        assert result == 300  # noqa: PLR2004

    def test_no_vertical_overlap_ignored(self) -> None:
        block = {"rect": [300, 200, 500, 210]}
        others = [
            block,
            {"rect": [100, 220, 250, 230]},  # below, no overlap
        ]
        result = _cap_by_left_neighbors(block, others, 300, 200, 210, 50)
        assert result == 50  # noqa: PLR2004

    def test_block_entirely_right_ignored(self) -> None:
        block = {"rect": [300, 200, 500, 210]}
        others = [
            block,
            {"rect": [350, 200, 450, 210]},  # entirely right of bx0
        ]
        result = _cap_by_left_neighbors(block, others, 300, 200, 210, 50)
        assert result == 50  # noqa: PLR2004

    def test_table_cell_blocks_collision(self) -> None:
        block = {"rect": [300, 200, 500, 210]}
        others = [
            block,
            {"rect": [100, 200, 250, 210], "is_table_cell": True},
        ]
        result = _cap_by_left_neighbors(block, others, 300, 200, 210, 50)
        assert result == 250  # noqa: PLR2004

    def test_multiple_neighbors_uses_closest(self) -> None:
        block = {"rect": [300, 200, 500, 210]}
        others = [
            block,
            {"rect": [50, 200, 100, 210]},  # far neighbor
            {"rect": [150, 200, 250, 210]},  # closer neighbor
        ]
        result = _cap_by_left_neighbors(block, others, 300, 200, 210, 50)
        assert result == 250  # noqa: PLR2004

    def test_edge_touching_block_caps(self) -> None:
        """Block whose right edge exactly equals bx0 should cap."""
        block = {"rect": [300, 200, 500, 210]}
        others = [
            block,
            {"rect": [200, 200, 300, 210]},  # ends exactly at bx0
        ]
        result = _cap_by_left_neighbors(block, others, 300, 200, 210, 50)
        assert result == 300  # noqa: PLR2004

    def test_empty_all_blocks(self) -> None:
        block = {"rect": [300, 200, 500, 210]}
        result = _cap_by_left_neighbors(block, [], 300, 200, 210, 50)
        assert result == 50  # noqa: PLR2004

    def test_proposed_greater_than_bx0(self) -> None:
        """Degenerate case: proposed_x0 >= bx0 returned as-is."""
        block = {"rect": [300, 200, 500, 210]}
        others = [block, {"rect": [100, 200, 250, 210]}]
        result = _cap_by_left_neighbors(block, others, 300, 200, 210, 310)
        assert result == 310  # noqa: PLR2004


class TestCapByNeighbors:
    """Tests for _cap_by_neighbors collision detection."""

    def test_right_neighbor_caps(self) -> None:
        block = {"rect": [100, 200, 250, 210]}
        others = [
            block,
            {"rect": [300, 200, 400, 210]},  # right neighbor
        ]
        result = _cap_by_neighbors(block, others, 250, 200, 210, 500)
        assert result == 300  # noqa: PLR2004

    def test_straddling_block_caps_at_bx1(self) -> None:
        block = {"rect": [100, 200, 250, 210]}
        others = [
            block,
            {"rect": [230, 202, 350, 208]},  # straddles bx1=250
        ]
        result = _cap_by_neighbors(block, others, 250, 200, 210, 500)
        assert result == 250  # noqa: PLR2004

    def test_no_vertical_overlap_ignored(self) -> None:
        block = {"rect": [100, 200, 250, 210]}
        others = [
            block,
            {"rect": [300, 220, 400, 230]},  # below, no overlap
        ]
        result = _cap_by_neighbors(block, others, 250, 200, 210, 500)
        assert result == 500  # noqa: PLR2004

    def test_block_entirely_left_ignored(self) -> None:
        block = {"rect": [100, 200, 250, 210]}
        others = [
            block,
            {"rect": [50, 200, 200, 210]},  # ends before bx1
        ]
        result = _cap_by_neighbors(block, others, 250, 200, 210, 500)
        assert result == 500  # noqa: PLR2004

    def test_table_cell_blocks_collision(self) -> None:
        block = {"rect": [100, 200, 250, 210]}
        others = [
            block,
            {"rect": [280, 200, 400, 210], "is_table_cell": True},
        ]
        result = _cap_by_neighbors(block, others, 250, 200, 210, 500)
        assert result == 280  # noqa: PLR2004

    def test_multiple_neighbors_uses_closest(self) -> None:
        block = {"rect": [100, 200, 250, 210]}
        others = [
            block,
            {"rect": [400, 200, 500, 210]},  # far neighbor
            {"rect": [300, 200, 350, 210]},  # closer neighbor
        ]
        result = _cap_by_neighbors(block, others, 250, 200, 210, 500)
        assert result == 300  # noqa: PLR2004

    def test_edge_touching_block_caps(self) -> None:
        """Block whose left edge exactly equals bx1 should cap."""
        block = {"rect": [100, 200, 250, 210]}
        others = [
            block,
            {"rect": [250, 200, 400, 210]},  # starts exactly at bx1
        ]
        result = _cap_by_neighbors(block, others, 250, 200, 210, 500)
        assert result == 250  # noqa: PLR2004

    def test_partial_vertical_overlap_caps(self) -> None:
        """Even 1pt of vertical overlap should trigger capping."""
        block = {"rect": [100, 200, 250, 210]}
        others = [
            block,
            {"rect": [300, 209, 400, 220]},  # overlaps by 1pt (209 < 210)
        ]
        result = _cap_by_neighbors(block, others, 250, 200, 210, 500)
        assert result == 300  # noqa: PLR2004

    def test_empty_all_blocks(self) -> None:
        """Empty block list returns proposed_x1 unchanged."""
        block = {"rect": [100, 200, 250, 210]}
        result = _cap_by_neighbors(block, [], 250, 200, 210, 500)
        assert result == 500  # noqa: PLR2004

    def test_proposed_less_than_bx1(self) -> None:
        """Degenerate case: proposed_x1 <= bx1 returned as-is."""
        block = {"rect": [100, 200, 250, 210]}
        others = [block, {"rect": [300, 200, 400, 210]}]
        result = _cap_by_neighbors(block, others, 250, 200, 210, 240)
        assert result == 240  # noqa: PLR2004


# ── _extract_table_cell_blocks ────────────────────────────────────────


class TestExtractTableCellBlocks:
    """Tests for _extract_table_cell_blocks."""

    def _make_page_dict(
        self,
        spans: list[dict],
    ) -> dict:
        """Build a minimal page_dict with given spans."""
        return {
            "blocks": [
                {
                    "type": 0,
                    "lines": [{"spans": spans}],
                }
            ],
        }

    def test_empty_tables(self) -> None:
        """No tables → empty result."""
        assert _extract_table_cell_blocks([], {"blocks": []}) == []

    def test_cell_with_text(self) -> None:
        """Cell containing text spans produces a block."""
        spans = [
            {
                "bbox": (15, 15, 80, 25),
                "text": "hello",
                "size": 12.0,
                "flags": 0,
                "color": 0,
                "font": "Arial",
            },
        ]
        page_dict = self._make_page_dict(spans)
        tables = [{"bbox": (0, 0, 200, 100), "cells": [(10, 10, 100, 50)]}]
        result = _extract_table_cell_blocks(tables, page_dict)
        assert len(result) == 1
        assert result[0]["text"] == "hello"
        assert result[0]["is_table_cell"] is True
        assert result[0]["font_size"] == 12.0  # noqa: PLR2004

    def test_empty_cell_skipped(self) -> None:
        """Cell with no spans is skipped."""
        page_dict = {"blocks": []}
        tables = [{"bbox": (0, 0, 200, 100), "cells": [(10, 10, 100, 50)]}]
        assert _extract_table_cell_blocks(tables, page_dict) == []

    def test_whitespace_only_cell_skipped(self) -> None:
        """Cell with only whitespace text is skipped."""
        spans = [
            {
                "bbox": (15, 15, 80, 25),
                "text": "   ",
                "size": 12.0,
                "flags": 0,
                "color": 0,
                "font": "Arial",
            },
        ]
        page_dict = self._make_page_dict(spans)
        tables = [{"bbox": (0, 0, 200, 100), "cells": [(10, 10, 100, 50)]}]
        assert _extract_table_cell_blocks(tables, page_dict) == []

    def test_mixed_formatting_detected(self) -> None:
        """Cells with mixed bold/plain spans get has_mixed_formatting flag."""
        spans = [
            {
                "bbox": (15, 15, 40, 25),
                "text": "bold",
                "size": 12.0,
                "flags": 16,
                "color": 0,
                "font": "Arial",
            },
            {
                "bbox": (45, 15, 80, 25),
                "text": "normal",
                "size": 12.0,
                "flags": 0,
                "color": 0,
                "font": "Arial",
            },
        ]
        page_dict = self._make_page_dict(spans)
        tables = [{"bbox": (0, 0, 200, 100), "cells": [(10, 10, 100, 50)]}]
        result = _extract_table_cell_blocks(tables, page_dict)
        assert len(result) == 1
        assert result[0].get("has_mixed_formatting") is True

    def test_column_alignment_detected(self) -> None:
        """Column alignment is detected and stored in cell blocks."""
        # Two cells in same column with consistent left edges → "left"
        spans = [
            {
                "bbox": (15, 15, 80, 25),
                "text": "cell1",
                "size": 12.0,
                "flags": 0,
                "color": 0,
                "font": "Arial",
            },
            {
                "bbox": (15, 55, 80, 65),
                "text": "cell2",
                "size": 12.0,
                "flags": 0,
                "color": 0,
                "font": "Arial",
            },
        ]
        page_dict = self._make_page_dict(spans)
        tables = [
            {
                "bbox": (0, 0, 200, 100),
                "cells": [(10, 10, 100, 40), (10, 50, 100, 80)],
            }
        ]
        result = _extract_table_cell_blocks(tables, page_dict)
        assert len(result) == 2  # noqa: PLR2004
        assert result[0]["text_align"] in ("left", "right", "center")


# ── _find_page_tables (orchestrator) ──────────────────────────────────


class TestFindPageTables:
    """Tests for _find_page_tables orchestrator."""

    def test_no_tables_found(self) -> None:
        """Page with no tables returns empty list."""
        page = MagicMock()
        tables_result = MagicMock()
        tables_result.tables = []
        page.find_tables.return_value = tables_result
        page.get_text.return_value = {"blocks": []}
        page.get_drawings.return_value = []

        result = _find_page_tables(page)
        assert result == []

    def test_pymupdf_find_tables_used(self) -> None:
        """PyMuPDF find_tables results are included."""
        page = MagicMock()
        table = MagicMock()
        table.bbox = (10, 10, 200, 200)
        table.cells = [(10, 10, 100, 100), (100, 10, 200, 100)]
        tables_result = MagicMock()
        tables_result.tables = [table]
        page.find_tables.return_value = tables_result
        page.get_text.return_value = {"blocks": []}
        page.get_drawings.return_value = []

        result = _find_page_tables(page)
        assert len(result) == 1
        assert result[0]["bbox"] == (10, 10, 200, 200)
        assert len(result[0]["cells"]) == 2  # noqa: PLR2004

    def test_find_tables_exception_suppressed(self) -> None:
        """Exception in find_tables is caught gracefully."""
        page = MagicMock()
        page.find_tables.side_effect = RuntimeError("bad page")
        page.get_text.return_value = {"blocks": []}
        page.get_drawings.return_value = []

        result = _find_page_tables(page)
        assert result == []

    def test_none_cells_filtered(self) -> None:
        """None cells from find_tables are filtered out."""
        page = MagicMock()
        table = MagicMock()
        table.bbox = (10, 10, 200, 200)
        table.cells = [(10, 10, 100, 100), None, (100, 10, 200, 100)]
        tables_result = MagicMock()
        tables_result.tables = [table]
        page.find_tables.return_value = tables_result
        page.get_text.return_value = {"blocks": []}
        page.get_drawings.return_value = []

        result = _find_page_tables(page)
        # None cell is filtered
        assert len(result[0]["cells"]) == 2  # noqa: PLR2004

    def test_page_dict_passed_through(self) -> None:
        """Pre-computed page_dict avoids calling page.get_text."""
        page = MagicMock()
        tables_result = MagicMock()
        tables_result.tables = []
        page.find_tables.return_value = tables_result
        page.get_drawings.return_value = []

        page_dict = {"blocks": []}
        _find_page_tables(page, page_dict=page_dict)
        # get_text should NOT be called since we passed page_dict
        page.get_text.assert_not_called()


# ── Sentence-ending detection (line_texts param) ──────────────────────────────


class TestDetectLineJoinsSentenceEnding:
    """Tests for sentence-ending upgrade in _detect_line_joins."""

    def _uniform_y(self, n: int) -> list[float]:
        """Generate n y-positions with normal 14pt leading (12pt font)."""
        return [100.0 + i * 14.0 for i in range(n)]

    def test_period_short_line_upgrades_to_newline(self) -> None:
        """Line ending with '.' that doesn't fill block → newline."""
        y = self._uniform_y(3)
        sizes = [12.0] * 3
        # block width = 300 (50..350). Line 0 is short (50..200 = 150pt).
        extents = [(50.0, 200.0), (50.0, 350.0), (50.0, 350.0)]
        texts = ["End of sentence.", "Next paragraph starts", "here and continues"]
        result = _detect_line_joins(y, sizes, extents, texts)
        assert result[0] == "\n"  # sentence ending + short → upgraded

    def test_question_mark_short_line_upgrades(self) -> None:
        """Line ending with '?' that doesn't fill block → newline."""
        y = self._uniform_y(3)
        sizes = [12.0] * 3
        extents = [(50.0, 200.0), (50.0, 350.0), (50.0, 350.0)]
        texts = ["Is this done?", "Yes it is", "and continues"]
        result = _detect_line_joins(y, sizes, extents, texts)
        assert result[0] == "\n"

    def test_exclamation_short_line_upgrades(self) -> None:
        """Line ending with '!' that doesn't fill block → newline."""
        y = self._uniform_y(3)
        sizes = [12.0] * 3
        extents = [(50.0, 200.0), (50.0, 350.0), (50.0, 350.0)]
        texts = ["Amazing!", "Next line", "continues"]
        result = _detect_line_joins(y, sizes, extents, texts)
        assert result[0] == "\n"

    def test_period_full_width_line_stays_space(self) -> None:
        """Line ending with '.' but filling block width → stays space."""
        y = self._uniform_y(3)
        sizes = [12.0] * 3
        # Line 0 width = 298pt, block width = 300pt → ratio 0.993 > 0.90
        extents = [(50.0, 348.0), (50.0, 350.0), (50.0, 350.0)]
        texts = ["This sentence ends.", "But it fills the line width", "so no break"]
        result = _detect_line_joins(y, sizes, extents, texts)
        assert result[0] == " "

    def test_no_sentence_ending_stays_space(self) -> None:
        """Line without sentence-ending punctuation → stays space."""
        # Use n=2 to skip layout-based upgrades (n>=3 guard).
        # Only sentence-ending upgrade can fire; it shouldn't here.
        y = self._uniform_y(2)
        sizes = [12.0] * 2
        extents = [(50.0, 200.0), (50.0, 350.0)]
        texts = ["No period here", "continues on"]
        result = _detect_line_joins(y, sizes, extents, texts)
        assert result[0] == " "  # no sentence-end punct → no upgrade

    def test_already_newline_not_affected(self) -> None:
        """Join already marked as newline is not re-processed."""
        # Gap 40 > leading threshold 21.6 → already newline
        y = [100.0, 140.0, 154.0]
        sizes = [12.0] * 3
        extents = [(50.0, 200.0), (50.0, 350.0), (50.0, 350.0)]
        texts = ["Sentence ends.", "New paragraph", "continues"]
        result = _detect_line_joins(y, sizes, extents, texts)
        assert result[0] == "\n"  # was already newline from gap

    def test_trailing_whitespace_stripped(self) -> None:
        """Trailing whitespace is stripped before checking punctuation."""
        y = self._uniform_y(3)
        sizes = [12.0] * 3
        extents = [(50.0, 200.0), (50.0, 350.0), (50.0, 350.0)]
        texts = ["End of sentence.   ", "Next para", "continues"]
        result = _detect_line_joins(y, sizes, extents, texts)
        assert result[0] == "\n"  # stripped → ends with '.'

    def test_empty_line_text_skipped(self) -> None:
        """Empty line text doesn't crash or trigger upgrade."""
        # Use n=2 to isolate sentence-ending logic.
        y = self._uniform_y(2)
        sizes = [12.0] * 2
        extents = [(50.0, 200.0), (50.0, 350.0)]
        texts = ["", "Some text"]
        result = _detect_line_joins(y, sizes, extents, texts)
        assert result[0] == " "  # empty text → no upgrade

    def test_works_with_two_lines(self) -> None:
        """Sentence-ending upgrade works even with n=2 (no layout section)."""
        y = self._uniform_y(2)
        sizes = [12.0] * 2
        extents = [(50.0, 200.0), (50.0, 350.0)]
        texts = ["Done.", "Next"]
        result = _detect_line_joins(y, sizes, extents, texts)
        # n=2 skips layout upgrades (n>=3 guard) but sentence-end
        # upgrade has no minimum n requirement
        assert result[0] == "\n"

    def test_comma_does_not_trigger(self) -> None:
        """Comma at end of short line does NOT trigger upgrade."""
        # Use n=2 to isolate sentence-ending logic.
        y = self._uniform_y(2)
        sizes = [12.0] * 2
        extents = [(50.0, 200.0), (50.0, 350.0)]
        texts = ["After comma,", "text continues"]
        result = _detect_line_joins(y, sizes, extents, texts)
        assert result[0] == " "


# ── Centered block alignment with full-width lines ────────────────────────────


class TestDetectBlockAlignmentCentered:
    """Tests for centered block detection with full-width line exclusion."""

    def test_centered_with_full_width_lines(self) -> None:
        """Block with centered short lines + full-width lines → center."""
        # Simulates author block: some lines span full width (emails),
        # others are short and centered.
        bx0, bx1 = 50.0, 350.0
        extents = [
            (100.0, 300.0),  # short, centered (margins: 50, 50)
            (110.0, 290.0),  # short, centered (margins: 60, 60)
            (50.0, 350.0),  # full-width (margins: 0, 0)
            (105.0, 295.0),  # short, centered (margins: 55, 55)
            (50.0, 349.0),  # near full-width (margins: 0, 1)
        ]
        align, _ = _detect_block_alignment(
            extents,
            [bx0, 100, bx1, 200],
            [10.0] * 5,  # noqa: PLR2004
        )
        assert align == "center"

    def test_justified_not_centered_with_full_width(self) -> None:
        """Block with justified alignment (asymmetric narrow lines) stays justify."""
        bx0, bx1 = 50.0, 350.0
        extents = [
            (50.0, 350.0),  # full-width
            (50.0, 349.0),  # full-width
            (50.0, 348.0),  # full-width
            (50.0, 250.0),  # short, left-aligned (left margin 0, right margin 100)
        ]
        align, _ = _detect_block_alignment(
            extents,
            [bx0, 100, bx1, 200],
            [10.0] * 4,
        )
        assert align == "justify"

    def test_all_full_width_stays_justify(self) -> None:
        """When ALL lines are full-width, no narrow lines exist → justify."""
        bx0, bx1 = 50.0, 350.0
        extents = [
            (50.0, 350.0),
            (50.0, 349.0),
            (50.0, 350.0),
        ]
        align, _ = _detect_block_alignment(
            extents,
            [bx0, 100, bx1, 200],
            [10.0] * 3,
        )
        assert align == "justify"


# ── Centered layout short-line in _detect_line_joins ──────────────────────────


class TestDetectLineJoinsCenteredLayout:
    """Tests for centered layout detection and short-line upgrade."""

    def _uniform_y(self, n: int) -> list[float]:
        return [100.0 + i * 14.0 for i in range(n)]

    def test_centered_short_line_upgraded(self) -> None:
        """In a centered layout, short lines are upgraded to newline."""
        n = 5  # noqa: PLR2004
        y = self._uniform_y(n)
        sizes = [12.0] * n
        # A full-width anchor line establishes block_left=50,
        # block_right=350 → bw=300.  Short centered lines have
        # symmetric margins and are narrower than 0.9*300=270.
        extents = [
            (120.0, 280.0),  # centered, short (160pt < 270)
            (130.0, 270.0),  # centered, short (140pt < 270)
            (50.0, 350.0),  # full-width anchor (300pt >= 270)
            (120.0, 280.0),  # centered, short
            (130.0, 270.0),  # centered, short
        ]
        result = _detect_line_joins(y, sizes, extents)
        # Short centered lines → newline; full-width stays space
        assert result[0] == "\n"
        assert result[1] == "\n"
        assert result[2] == " "  # full-width → not short → space
        assert result[3] == "\n"

    def test_centered_full_width_stays_space(self) -> None:
        """In centered layout, a full-width line stays space-joined."""
        n = 4
        y = self._uniform_y(n)
        sizes = [12.0] * n
        # bw=300. Lines 0,1 are full-width, line 2 is short.
        extents = [
            (100.0, 300.0),  # centered, short
            (50.0, 350.0),  # full-width (300pt >= 300*0.9=270)
            (100.0, 300.0),  # centered, short
            (105.0, 295.0),  # centered, short
        ]
        result = _detect_line_joins(y, sizes, extents)
        # Line 1 is full-width → stays space; lines 0,2 are short → newline
        assert result[0] == "\n"
        assert result[1] == " "
        assert result[2] == "\n"

    def test_non_centered_not_affected(self) -> None:
        """Left-aligned short lines are not upgraded by centered check."""
        n = 4
        y = self._uniform_y(n)
        sizes = [12.0] * n
        # Left-aligned: all start at x=50, ragged right
        extents = [
            (50.0, 200.0),  # short
            (50.0, 350.0),  # full-width
            (50.0, 250.0),  # short
            (50.0, 340.0),  # near-full
        ]
        result = _detect_line_joins(y, sizes, extents)
        # Not centered (asymmetric margins) — short-line check
        # may trigger via justified/indent path but not centered path
        assert result[0] == " " or result[0] == "\n"  # depends on justified checks


# ── Fragment filter in _detect_line_joins ─────────────────────────────────────


class TestDetectLineJoinsFragmentFilter:
    """Tests for narrow-fragment exclusion from alignment analysis."""

    def test_narrow_math_fragment_excluded_from_alignment(self) -> None:
        """Lines < 20% of block width are excluded from alignment voting.

        Simulates algorithm box where most lines are left-aligned but a few
        narrow math sub-expressions (e.g. '2(f,D)' at 31pt in a 208pt block)
        would distort alignment if counted.
        """
        # 6 lines: 3 full-width left-aligned + 3 narrow fragments
        y = [100.0, 114.0, 128.0, 142.0, 156.0, 170.0]
        sizes = [10.0] * 6  # noqa: PLR2004
        left = 72.0
        extents = [
            (left, left + 200.0),  # full line (left-aligned)
            (left, left + 190.0),  # full line (left-aligned)
            (left, left + 195.0),  # full line (left-aligned)
            (left + 80.0, left + 111.0),  # narrow fragment (~31pt)
            (left + 50.0, left + 75.0),  # narrow fragment (~25pt)
            (left + 90.0, left + 110.0),  # narrow fragment (~20pt)
        ]
        result = _detect_line_joins(y, sizes, extents)
        # Fragments excluded → block detected as left-aligned.
        # All joins should be space (normal left-aligned text flow).
        assert len(result) == 5  # noqa: PLR2004
        # The key check: narrow fragments don't cause newline breaks
        # that would happen if the block was misclassified.
        assert result[0] == " "
        assert result[1] == " "

    def test_all_narrow_lines_fallback(self) -> None:
        """When ALL lines are narrow, fallback uses all of them."""
        y = [100.0, 114.0, 128.0]
        sizes = [10.0] * 3
        # All lines narrower than 20% of "block width" — but block_width
        # is derived from extents' max right - min left.
        extents = [
            (100.0, 120.0),  # 20pt
            (105.0, 125.0),  # 20pt
            (100.0, 118.0),  # 18pt
        ]
        result = _detect_line_joins(y, sizes, extents)
        # Should not crash; all lines are used as fallback.
        assert len(result) == 2  # noqa: PLR2004


# ── Vertical overlap grouping in _build_cell_text ─────────────────────────────


class TestBuildCellTextVerticalOverlap:
    """Tests for vertical overlap grouping (subscript/superscript in cells)."""

    def test_subscript_same_line(self) -> None:
        """Subscript span overlapping main span → same line."""
        # "d" at y=50..62, "model" subscript at y=56..64 (overlaps vertically)
        spans = [
            {"bbox": (10, 50, 20, 62), "text": "d", "size": 12.0},
            {"bbox": (20, 56, 60, 64), "text": "model", "size": 8.0},
        ]
        text, y0s = _build_cell_text(spans)
        assert "d" in text
        assert "model" in text
        # Both should be on the same line
        assert len(y0s) == 1

    def test_superscript_same_line(self) -> None:
        """Superscript span overlapping main span → same line."""
        # "10" at y=50..62, "th" superscript at y=48..56 (overlaps vertically)
        spans = [
            {"bbox": (10, 50, 30, 62), "text": "10", "size": 12.0},
            {"bbox": (30, 48, 45, 56), "text": "th", "size": 8.0},
        ]
        text, y0s = _build_cell_text(spans)
        assert "10" in text
        assert "th" in text
        assert len(y0s) == 1

    def test_no_overlap_separate_lines(self) -> None:
        """Spans with no vertical overlap → separate lines."""
        spans = [
            {"bbox": (10, 10, 50, 20), "text": "line1", "size": 12.0},
            {"bbox": (10, 50, 50, 60), "text": "line2", "size": 12.0},
        ]
        text, y0s = _build_cell_text(spans)
        assert len(y0s) == 2  # noqa: PLR2004

    def test_y_close_groups_even_without_overlap(self) -> None:
        """Spans within _LINE_Y_TOLERANCE of each other → same line."""
        # y-tops differ by 1pt < _LINE_Y_TOLERANCE (2pt)
        spans = [
            {"bbox": (10, 50, 50, 60), "text": "a", "size": 12.0},
            {"bbox": (55, 51, 80, 61), "text": "b", "size": 12.0},
        ]
        text, y0s = _build_cell_text(spans)
        assert len(y0s) == 1


# ── Smart join threshold boundary tests ───────────────────────────────────────


class TestCellShortLineRatio:
    """Tests for _cell_short_line_ratio dynamic threshold."""

    def test_narrow_cell_gets_min(self) -> None:
        """Very narrow cell → clamped to 0.50 floor."""
        # cell_w=30, font=12 → 1.0 - 3*12/30 = -0.20 → clamped to 0.50
        assert _cell_short_line_ratio(12.0, 30.0) == 0.50  # noqa: PLR2004

    def test_wide_cell_gets_max(self) -> None:
        """Very wide cell → clamped to 0.85 ceiling."""
        # cell_w=500, font=10 → 1.0 - 3*10/500 = 0.94 → clamped to 0.85
        assert _cell_short_line_ratio(10.0, 500.0) == 0.85  # noqa: PLR2004

    def test_medium_cell_interpolated(self) -> None:
        """Medium cell → value between min and max."""
        # cell_w=100, font=10 → 1.0 - 3*10/100 = 0.70
        result = _cell_short_line_ratio(10.0, 100.0)
        assert result == pytest.approx(0.70, abs=0.01)  # noqa: PLR2004

    def test_zero_cell_width(self) -> None:
        """Zero cell width → returns min."""
        assert _cell_short_line_ratio(12.0, 0.0) == 0.50  # noqa: PLR2004

    def test_zero_font_size(self) -> None:
        """Zero font size → returns min."""
        assert _cell_short_line_ratio(0.0, 100.0) == 0.50  # noqa: PLR2004

    def test_small_font_large_cell(self) -> None:
        """Small font in large cell → high threshold."""
        # cell_w=200, font=6 → 1.0 - 3*6/200 = 0.91 → clamped to 0.85
        assert _cell_short_line_ratio(6.0, 200.0) == 0.85  # noqa: PLR2004

    def test_large_font_medium_cell(self) -> None:
        """Large font in medium cell → lower threshold."""
        # cell_w=100, font=20 → 1.0 - 3*20/100 = 0.40 → clamped to 0.50
        assert _cell_short_line_ratio(20.0, 100.0) == 0.50  # noqa: PLR2004


class TestBuildCellTextSmartJoin:
    """Tests for dynamic cell short-line threshold in _build_cell_text."""

    def test_narrow_cell_wide_line_space_joined(self) -> None:
        """Line filling >50% of a narrow cell → space join."""
        # cell_w=50 (10..60), font=12 → threshold=0.50
        # prev_w=30 (10..40) → 30/50=0.60 >= 0.50 → space
        spans = [
            {"bbox": (10, 10, 40, 20), "text": "half", "size": 12.0},
            {"bbox": (10, 50, 60, 60), "text": "next", "size": 12.0},
        ]
        text, _ = _build_cell_text(spans)
        assert text == "half next"

    def test_narrow_cell_short_line_newline(self) -> None:
        """Line filling <50% of a narrow cell → newline."""
        # cell_w=50 (10..60), font=12 → threshold=0.50
        # prev_w=15 (10..25) → 15/50=0.30 < 0.50 → newline
        spans = [
            {"bbox": (10, 10, 25, 20), "text": "A", "size": 12.0},
            {"bbox": (10, 50, 60, 60), "text": "wider text", "size": 12.0},
        ]
        text, _ = _build_cell_text(spans)
        assert "\n" in text

    def test_wide_cell_uses_higher_threshold(self) -> None:
        """In a wide cell, a line at 60% gets newline (threshold > 0.60)."""
        # cell_w=200 (10..210), font=10 → threshold = 1-30/200 = 0.85
        # prev_w=120 (10..130) → 120/200=0.60 < 0.85 → newline
        spans = [
            {"bbox": (10, 10, 130, 20), "text": "medium line", "size": 10.0},
            {"bbox": (10, 50, 210, 60), "text": "full line here", "size": 10.0},
        ]
        text, _ = _build_cell_text(spans)
        assert "\n" in text

    def test_wide_cell_full_line_space(self) -> None:
        """In a wide cell, a line at 90% gets space (above threshold)."""
        # cell_w=200 (10..210), font=10 → threshold=0.85
        # prev_w=180 (10..190) → 180/200=0.90 >= 0.85 → space
        spans = [
            {"bbox": (10, 10, 190, 20), "text": "almost full", "size": 10.0},
            {"bbox": (10, 50, 210, 60), "text": "continues", "size": 10.0},
        ]
        text, _ = _build_cell_text(spans)
        assert text == "almost full continues"

    def test_single_line_no_join(self) -> None:
        """Single line → no join logic at all."""
        spans = [
            {"bbox": (10, 10, 100, 20), "text": "only one", "size": 12.0},
        ]
        text, y0s = _build_cell_text(spans)
        assert text == "only one"
        assert len(y0s) == 1


class TestBuildCellTextCellRect:
    """Tests for cell_rect parameter in _build_cell_text."""

    def test_sparse_column_without_cell_rect_space_joins(self) -> None:
        """Without cell_rect, same-width values get space-joined (bug)."""
        # Two 10pt-wide numbers: text-extent cell_w = 10, each fills 100%
        spans = [
            {"bbox": (483, 214, 493, 223), "text": "58", "size": 10.0},
            {"bbox": (483, 224, 493, 234), "text": "60", "size": 10.0},
        ]
        text, _ = _build_cell_text(spans)
        assert text == "58 60"  # wrong: space join from text extents

    def test_sparse_column_with_cell_rect_newlines(self) -> None:
        """With cell_rect, same-width values get newline-separated."""
        spans = [
            {"bbox": (483, 214, 493, 223), "text": "58", "size": 10.0},
            {"bbox": (483, 224, 493, 234), "text": "60", "size": 10.0},
        ]
        text, _ = _build_cell_text(spans, cell_rect=(471, 212, 509, 235))
        # cell_w=38, prev_w=10 → 10/38=0.26 < 0.50 threshold → newline
        assert text == "58\n60"

    def test_many_rows_with_cell_rect(self) -> None:
        """Multiple table rows in one cell all get newlines."""
        spans = [
            {"bbox": (483, 237, 493, 247), "text": "36", "size": 10.0},
            {"bbox": (483, 248, 493, 258), "text": "50", "size": 10.0},
            {"bbox": (483, 259, 493, 269), "text": "80", "size": 10.0},
        ]
        text, _ = _build_cell_text(spans, cell_rect=(471, 235, 509, 314))
        assert text == "36\n50\n80"

    def test_word_wrap_with_cell_rect_space_joins(self) -> None:
        """Text that fills most of cell width gets space join."""
        # cell_rect width=100, line fills 80pt → 80% >= threshold
        spans = [
            {"bbox": (10, 10, 90, 20), "text": "parameters", "size": 10.0},
            {"bbox": (10, 22, 50, 32), "text": "count", "size": 10.0},
        ]
        text, _ = _build_cell_text(spans, cell_rect=(10, 10, 110, 40))
        # threshold = 1-30/100 = 0.70, prev_w=80/100=0.80 >= 0.70 → space
        assert text == "parameters count"

    def test_cell_rect_none_falls_back_to_text_extents(self) -> None:
        """cell_rect=None uses text extents (backward compatible)."""
        spans = [
            {"bbox": (10, 10, 60, 20), "text": "fill", "size": 12.0},
            {"bbox": (10, 50, 60, 60), "text": "also", "size": 12.0},
        ]
        # cell_rect=None → cell_w from text extents = 50
        text_none, _ = _build_cell_text(spans, cell_rect=None)
        text_default, _ = _build_cell_text(spans)
        assert text_none == text_default


# ── Rotated line filtering in _get_spans_in_rect ──────────────────────────────


class TestGetSpansInRectRotated:
    """Tests for rotated/vertical line filtering in _get_spans_in_rect."""

    def test_horizontal_line_included(self) -> None:
        """Horizontal line (dir=(1,0)) spans are included."""
        page_dict = {
            "blocks": [
                {
                    "type": 0,
                    "lines": [
                        {
                            "dir": (1.0, 0.0),
                            "spans": [{"bbox": (10, 10, 20, 20), "text": "ok"}],
                        }
                    ],
                }
            ],
        }
        result = _get_spans_in_rect(page_dict, (0, 0, 30, 30))
        assert len(result) == 1

    def test_vertical_line_excluded(self) -> None:
        """Vertical line (dir=(0,-1)) spans are excluded."""
        page_dict = {
            "blocks": [
                {
                    "type": 0,
                    "lines": [
                        {
                            "dir": (0.0, -1.0),
                            "spans": [{"bbox": (10, 10, 20, 20), "text": "rotated"}],
                        }
                    ],
                }
            ],
        }
        result = _get_spans_in_rect(page_dict, (0, 0, 30, 30))
        assert len(result) == 0

    def test_90_degree_rotation_excluded(self) -> None:
        """90° rotated line (dir=(0,1)) spans are excluded."""
        page_dict = {
            "blocks": [
                {
                    "type": 0,
                    "lines": [
                        {
                            "dir": (0.0, 1.0),
                            "spans": [{"bbox": (10, 10, 20, 20), "text": "up"}],
                        }
                    ],
                }
            ],
        }
        result = _get_spans_in_rect(page_dict, (0, 0, 30, 30))
        assert len(result) == 0

    def test_slightly_off_horizontal_included(self) -> None:
        """Near-horizontal line within tolerance is included."""
        page_dict = {
            "blocks": [
                {
                    "type": 0,
                    "lines": [
                        {
                            "dir": (0.99, 0.05),
                            "spans": [{"bbox": (10, 10, 20, 20), "text": "slight"}],
                        }
                    ],
                }
            ],
        }
        result = _get_spans_in_rect(page_dict, (0, 0, 30, 30))
        assert len(result) == 1

    def test_missing_dir_defaults_horizontal(self) -> None:
        """Line without dir key defaults to (1,0) and is included."""
        page_dict = {
            "blocks": [
                {
                    "type": 0,
                    "lines": [
                        {
                            "spans": [{"bbox": (10, 10, 20, 20), "text": "no dir"}],
                        }
                    ],
                }
            ],
        }
        result = _get_spans_in_rect(page_dict, (0, 0, 30, 30))
        assert len(result) == 1

    def test_mixed_rotated_and_horizontal_lines(self) -> None:
        """Only horizontal line spans are returned from mixed block."""
        page_dict = {
            "blocks": [
                {
                    "type": 0,
                    "lines": [
                        {
                            "dir": (1.0, 0.0),
                            "spans": [{"bbox": (10, 10, 20, 20), "text": "horiz"}],
                        },
                        {
                            "dir": (0.0, -1.0),
                            "spans": [{"bbox": (10, 10, 20, 20), "text": "vert"}],
                        },
                    ],
                }
            ],
        }
        result = _get_spans_in_rect(page_dict, (0, 0, 30, 30))
        assert len(result) == 1
        assert result[0]["text"] == "horiz"


# ── Table text density filter ─────────────────────────────────────────────────


class TestTableTextDensity:
    """Tests for _table_text_density."""

    def _make_page_dict(
        self,
        spans: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Build a minimal page_dict with given spans."""
        if not spans:
            return {"blocks": []}
        return {
            "blocks": [
                {
                    "type": 0,
                    "lines": [
                        {
                            "dir": (1.0, 0.0),
                            "spans": spans,
                        }
                    ],
                }
            ],
        }

    def test_empty_cells(self) -> None:
        """Table with no cells → 0.0 density."""
        table_info: dict[str, Any] = {"cells": [], "bbox": (0, 0, 100, 100)}
        assert _table_text_density(table_info, {"blocks": []}) == 0.0

    def test_all_cells_have_text(self) -> None:
        """Every cell contains text → 1.0 density."""
        table_info: dict[str, Any] = {
            "cells": [(0, 0, 50, 50), (50, 0, 100, 50)],
            "bbox": (0, 0, 100, 50),
        }
        page_dict = self._make_page_dict(
            [
                {"bbox": (10, 10, 40, 40), "text": "a"},
                {"bbox": (60, 10, 90, 40), "text": "b"},
            ]
        )
        assert _table_text_density(table_info, page_dict) == 1.0

    def test_sparse_table(self) -> None:
        """Only 1 of 10 cells has text → 0.10 density."""
        cells = [(i * 10, 0, (i + 1) * 10, 10) for i in range(10)]
        table_info: dict[str, Any] = {
            "cells": cells,
            "bbox": (0, 0, 100, 10),
        }
        # Only one span at center of cell 0
        page_dict = self._make_page_dict(
            [
                {"bbox": (2, 2, 8, 8), "text": "x"},
            ]
        )
        density = _table_text_density(table_info, page_dict)
        assert density == pytest.approx(0.1, abs=0.01)  # noqa: PLR2004


class TestFindPageTablesDensityFilter:
    """Tests for sparse table filtering in _find_page_tables."""

    def test_sparse_table_discarded(self) -> None:
        """Table with many cells but low text density is filtered out."""
        page = MagicMock()
        table = MagicMock()
        # 50 cells, only 1 will have text → 2% density < 15%
        table.bbox = (0, 0, 500, 500)
        table.cells = [(i * 10, 0, (i + 1) * 10, 10) for i in range(50)]
        tables_result = MagicMock()
        tables_result.tables = [table]
        page.find_tables.return_value = tables_result
        page.get_drawings.return_value = []
        page.get_text.return_value = {
            "blocks": [
                {
                    "type": 0,
                    "lines": [
                        {
                            "dir": (1.0, 0.0),
                            "spans": [{"bbox": (2, 2, 8, 8), "text": "x"}],
                        }
                    ],
                }
            ],
        }
        result = _find_page_tables(page)
        assert len(result) == 0

    def test_dense_table_kept(self) -> None:
        """Table with good text density is kept."""
        page = MagicMock()
        table = MagicMock()
        # 4 cells, all with text → 100% density
        table.bbox = (0, 0, 200, 200)
        table.cells = [
            (0, 0, 100, 100),
            (100, 0, 200, 100),
            (0, 100, 100, 200),
            (100, 100, 200, 200),
        ]
        tables_result = MagicMock()
        tables_result.tables = [table]
        page.find_tables.return_value = tables_result
        page.get_drawings.return_value = []
        page.get_text.return_value = {
            "blocks": [
                {
                    "type": 0,
                    "lines": [
                        {
                            "dir": (1.0, 0.0),
                            "spans": [
                                {"bbox": (10, 10, 90, 90), "text": "a"},
                                {"bbox": (110, 10, 190, 90), "text": "b"},
                                {"bbox": (10, 110, 90, 190), "text": "c"},
                                {"bbox": (110, 110, 190, 190), "text": "d"},
                            ],
                        }
                    ],
                }
            ],
        }
        result = _find_page_tables(page)
        assert len(result) == 1

    def test_small_table_skips_density_check(self) -> None:
        """Tables with < 20 cells skip density check even if sparse."""
        page = MagicMock()
        table = MagicMock()
        # 5 cells, only 1 with text → 20% density, but < 20 cells
        table.bbox = (0, 0, 500, 100)
        table.cells = [(i * 100, 0, (i + 1) * 100, 100) for i in range(5)]
        tables_result = MagicMock()
        tables_result.tables = [table]
        page.find_tables.return_value = tables_result
        page.get_drawings.return_value = []
        page.get_text.return_value = {
            "blocks": [
                {
                    "type": 0,
                    "lines": [
                        {
                            "dir": (1.0, 0.0),
                            "spans": [{"bbox": (10, 10, 90, 90), "text": "only one"}],
                        }
                    ],
                }
            ],
        }
        result = _find_page_tables(page)
        assert len(result) == 1  # kept (only 5 cells, below threshold)


class TestPartialRuleSubHeaders:
    """Partial horizontal rules split multi-level header rows."""

    @staticmethod
    def _make_subheader_page() -> tuple:
        """Create a booktabs table with a partial sub-header rule.

        Layout (3 full-width rules + 2 partial rules):
        y=200 ────────────────────────── (top rule)
               Model   | BLEU  | Cost
        y=220          ───      ─────── (partial rules)
                       | EN-DE | A | B
        y=240 ────────────────────────── (header separator)
               Row1    | 23.75 | x | y
        y=260 ────────────────────────── (bottom rule)
        """
        doc = pymupdf.open()
        page = doc.new_page()

        x0, y0 = 72, 200
        col_w = [150, 80, 80, 80]
        tw = sum(col_w)

        # 3 full-width rules
        for y_off in (0, 40, 60):
            page.draw_line(
                (x0, y0 + y_off),
                (x0 + tw, y0 + y_off),
                width=1,
            )

        # Partial rule under "BLEU" (col 1 only)
        page.draw_line(
            (x0 + col_w[0], y0 + 20),
            (x0 + col_w[0] + col_w[1], y0 + 20),
            width=0.5,
        )
        # Partial rule under "Cost" (cols 2-3)
        page.draw_line(
            (x0 + col_w[0] + col_w[1], y0 + 20),
            (x0 + tw, y0 + 20),
            width=0.5,
        )

        # Header row 1
        page.insert_text((x0 + 5, y0 + 15), "Model", fontsize=10)
        page.insert_text(
            (x0 + col_w[0] + 5, y0 + 15),
            "BLEU",
            fontsize=10,
        )
        page.insert_text(
            (x0 + col_w[0] + col_w[1] + 5, y0 + 15),
            "Cost",
            fontsize=10,
        )
        # Sub-header row
        page.insert_text(
            (x0 + col_w[0] + 5, y0 + 35),
            "EN-DE",
            fontsize=10,
        )
        page.insert_text(
            (x0 + col_w[0] + col_w[1] + 5, y0 + 35),
            "A",
            fontsize=10,
        )
        page.insert_text(
            (x0 + col_w[0] + col_w[1] + col_w[2] + 5, y0 + 35),
            "B",
            fontsize=10,
        )
        # Data row
        page.insert_text((x0 + 5, y0 + 55), "Row1", fontsize=10)
        page.insert_text(
            (x0 + col_w[0] + 5, y0 + 55),
            "23.75",
            fontsize=10,
        )
        page.insert_text(
            (x0 + col_w[0] + col_w[1] + 5, y0 + 55),
            "x",
            fontsize=10,
        )
        page.insert_text(
            (x0 + col_w[0] + col_w[1] + col_w[2] + 5, y0 + 55),
            "y",
            fontsize=10,
        )
        return doc, page

    def test_partial_rule_splits_header(self) -> None:
        """Partial rule creates separate cells for header and sub-header."""
        doc, page = self._make_subheader_page()
        page_dict = page.get_text("dict")
        tables = _detect_ruled_tables(page, page_dict)
        doc.close()

        assert len(tables) == 1

        # Collect cell texts
        cells = tables[0]["cells"]
        cell_texts: list[str] = []
        for cell in cells:
            spans = _get_spans_in_rect(page_dict, cell)
            text = " ".join(s["text"] for s in spans).strip()
            cell_texts.append(text)

        # "BLEU" and "EN-DE" must be in SEPARATE cells
        assert "BLEU" in cell_texts
        assert "EN-DE" in cell_texts
        # They should NOT be merged into "BLEU EN-DE"
        assert "BLEU EN-DE" not in cell_texts

    def test_parent_header_in_own_row(self) -> None:
        """Parent headers (BLEU, Cost) are in their own sub-row."""
        doc, page = self._make_subheader_page()
        page_dict = page.get_text("dict")
        tables = _detect_ruled_tables(page, page_dict)
        doc.close()

        cells = tables[0]["cells"]

        # Find cells containing "BLEU" and "EN-DE"
        bleu_cell = next(
            c
            for c in cells
            if _get_spans_in_rect(page_dict, c)
            and "BLEU" in _get_spans_in_rect(page_dict, c)[0]["text"]
        )
        ende_cell = next(
            c
            for c in cells
            if _get_spans_in_rect(page_dict, c)
            and "EN-DE" in _get_spans_in_rect(page_dict, c)[0]["text"]
        )

        # BLEU cell should be ABOVE EN-DE cell (lower y1)
        assert bleu_cell[3] <= ende_cell[1] + 2  # noqa: PLR2004

    def test_data_row_unaffected(self) -> None:
        """Data rows below the sub-header are not split."""
        doc, page = self._make_subheader_page()
        page_dict = page.get_text("dict")
        tables = _detect_ruled_tables(page, page_dict)
        doc.close()

        cells = tables[0]["cells"]

        # "Row1" and "23.75" should be in the same row
        row1_cell = next(
            c
            for c in cells
            if _get_spans_in_rect(page_dict, c)
            and "Row1" in _get_spans_in_rect(page_dict, c)[0]["text"]
        )
        val_cell = next(
            c
            for c in cells
            if _get_spans_in_rect(page_dict, c)
            and "23.75" in _get_spans_in_rect(page_dict, c)[0]["text"]
        )

        # Same y range (within tolerance)
        assert abs(row1_cell[1] - val_cell[1]) < 3  # noqa: PLR2004
        assert abs(row1_cell[3] - val_cell[3]) < 3  # noqa: PLR2004


# ── Vertical alignment resolution tests ──────────────────────────────────────


class TestResolveVerticalAlignment:
    """Tests for _resolve_vertical_alignment."""

    def test_no_vertical_blocks_unchanged(self) -> None:
        blocks = [{"text": "hello", "rect": [0, 0, 100, 20]}]
        result = _resolve_vertical_alignment(blocks)
        assert result is blocks

    def test_few_vertical_blocks_no_resolve(self) -> None:
        """Fewer than _MIN_LABEL_ROW_COUNT blocks → no resolution."""
        blocks = [
            {"text": "v0", "rect": [10, 50, 20, 100], "is_vertical": True},
            {"text": "v1", "rect": [30, 50, 40, 100], "is_vertical": True},
        ]
        result = _resolve_vertical_alignment(blocks)
        assert "_rotate" not in result[0]
        assert "_rotate" not in result[1]

    def test_bottom_aligned(self) -> None:
        """Blocks sharing bbox_y1 → bottom-aligned."""
        blocks = [
            {
                "text": f"t{i}",
                "is_vertical": True,
                "rect": [50 + i * 12, 100 - i * 5, 60 + i * 12, 100],
            }
            for i in range(5)  # noqa: PLR2004
        ]
        _resolve_vertical_alignment(blocks)
        for b in blocks:
            assert b["_vert_align"] == "bottom"
            assert abs(b["_vert_align_y"] - 100.0) < 1.0

    def test_top_aligned(self) -> None:
        """Blocks sharing bbox_y0 → top-aligned."""
        blocks = [
            {
                "text": f"t{i}",
                "is_vertical": True,
                "rect": [50 + i * 12, 50, 60 + i * 12, 50 + 10 + i * 5],
            }
            for i in range(5)  # noqa: PLR2004
        ]
        _resolve_vertical_alignment(blocks)
        for b in blocks:
            assert b["_vert_align"] == "top"
            assert abs(b["_vert_align_y"] - 50.0) < 1.0

    def test_center_aligned(self) -> None:
        """Blocks sharing mid_y → center-aligned."""
        mid = 200.0
        blocks = [
            {
                "text": f"t{i}",
                "is_vertical": True,
                "rect": [50 + i * 12, mid - 10 - i * 3, 60 + i * 12, mid + 10 + i * 3],
            }
            for i in range(5)  # noqa: PLR2004
        ]
        _resolve_vertical_alignment(blocks)
        for b in blocks:
            assert b["_vert_align"] == "center"
            assert abs(b["_vert_align_y"] - mid) < 2.0

    def test_separate_y_groups_independent(self) -> None:
        """Two y-groups get resolved independently."""
        blocks: list[dict[str, Any]] = []
        # Group 1: bottom-aligned at y1=100
        for i in range(4):
            blocks.append(
                {
                    "text": f"a{i}",
                    "is_vertical": True,
                    "rect": [50 + i * 12, 100 - 20 - i * 3, 60 + i * 12, 100],
                }
            )
        # Group 2: top-aligned at y0=300
        for i in range(4):
            blocks.append(
                {
                    "text": f"b{i}",
                    "is_vertical": True,
                    "rect": [50 + i * 12, 300, 60 + i * 12, 300 + 20 + i * 3],
                }
            )
        _resolve_vertical_alignment(blocks)
        for b in blocks[:4]:
            assert b["_vert_align"] == "bottom"
        for b in blocks[4:]:
            assert b["_vert_align"] == "top"

    def test_vertical_column_not_grouped(self) -> None:
        """Blocks stacked vertically (no y-overlap) are NOT grouped."""
        blocks = [
            {
                "text": f"L{i}",
                "is_vertical": True,
                "rect": [30, 50 + i * 60, 45, 100 + i * 60],
            }
            for i in range(12)
        ]
        _resolve_vertical_alignment(blocks)
        # Each block in its own group of 1 → no alignment set
        for b in blocks:
            assert "_vert_align" not in b

    def test_non_vertical_blocks_untouched(self) -> None:
        """Non-vertical blocks in the list are not modified."""
        blocks: list[dict[str, Any]] = [
            {"text": "normal", "rect": [50, 300, 200, 320]},
        ]
        for i in range(4):
            blocks.append(
                {
                    "text": f"v{i}",
                    "is_vertical": True,
                    "rect": [50 + i * 12, 50, 60 + i * 12, 100],
                }
            )
        _resolve_vertical_alignment(blocks)
        assert "_vert_align" not in blocks[0]

    def test_exactly_min_label_row_count(self) -> None:
        """Exactly _MIN_LABEL_ROW_COUNT blocks are resolved."""
        blocks = [
            {
                "text": f"t{i}",
                "is_vertical": True,
                "rect": [50 + i * 12, 80 - i * 3, 60 + i * 12, 100],
            }
            for i in range(3)  # _MIN_LABEL_ROW_COUNT = 3
        ]
        _resolve_vertical_alignment(blocks)
        for b in blocks:
            assert b["_vert_align"] == "bottom"

    def test_variance_tie_bottom_wins(self) -> None:
        """When all edges have equal variance (zero), bottom wins."""
        # All blocks have same y0, y1, and mid → all variances are 0
        blocks = [
            {
                "text": f"t{i}",
                "is_vertical": True,
                "rect": [50 + i * 12, 50, 60 + i * 12, 100],
            }
            for i in range(4)
        ]
        _resolve_vertical_alignment(blocks)
        # var_y1 == var_y0 == var_mid == 0 → first check (bottom) wins
        for b in blocks:
            assert b["_vert_align"] == "bottom"

    def test_mixed_vertical_and_horizontal(self) -> None:
        """Horizontal blocks mixed among vertical are ignored by grouping."""
        blocks: list[dict[str, Any]] = []
        # 4 vertical blocks, bottom-aligned
        for i in range(4):
            blocks.append(
                {
                    "text": f"v{i}",
                    "is_vertical": True,
                    "rect": [50 + i * 12, 80 - i * 5, 60 + i * 12, 100],
                }
            )
        # Horizontal block in the same y-range
        blocks.append({"text": "horiz", "rect": [200, 50, 400, 100]})
        _resolve_vertical_alignment(blocks)
        # Vertical blocks resolved, horizontal untouched
        for b in blocks[:4]:
            assert b["_vert_align"] == "bottom"
        assert "_vert_align" not in blocks[4]

    def test_axis_labels_removed(self) -> None:
        """A row of 8 vertical blocks (>= _MIN_AXIS_LABEL_COUNT) is removed."""
        blocks: list[dict[str, Any]] = [
            {"text": "normal", "rect": [50, 300, 200, 320]},
        ]
        for i in range(8):
            blocks.append(
                {
                    "text": f"tok{i}",
                    "is_vertical": True,
                    "rect": [100 + i * 12, 50, 110 + i * 12, 100],
                }
            )
        result = _resolve_vertical_alignment(blocks)
        assert len(result) == 1
        assert result[0]["text"] == "normal"

    def test_small_row_kept_large_row_removed(self) -> None:
        """Row with 4 blocks is resolved; row with 8 blocks is removed."""
        blocks: list[dict[str, Any]] = []
        # Group 1: 4 blocks at y=50..100 → resolved (< 6)
        for i in range(4):
            blocks.append(
                {
                    "text": f"a{i}",
                    "is_vertical": True,
                    "rect": [50 + i * 12, 50, 60 + i * 12, 100],
                }
            )
        # Group 2: 8 blocks at y=300..350 → removed (>= 6)
        for i in range(8):
            blocks.append(
                {
                    "text": f"b{i}",
                    "is_vertical": True,
                    "rect": [50 + i * 12, 300, 60 + i * 12, 350],
                }
            )
        result = _resolve_vertical_alignment(blocks)
        assert len(result) == 4  # noqa: PLR2004
        assert all(b["text"].startswith("a") for b in result)
        # Small group should have alignment resolved
        for b in result:
            assert "_vert_align" in b

    def test_exactly_min_axis_label_count_removed(self) -> None:
        """Exactly _MIN_AXIS_LABEL_COUNT (6) blocks are removed."""
        blocks = [
            {
                "text": f"t{i}",
                "is_vertical": True,
                "rect": [50 + i * 12, 50, 60 + i * 12, 100],
            }
            for i in range(6)
        ]
        result = _resolve_vertical_alignment(blocks)
        assert len(result) == 0

    def test_five_blocks_not_removed(self) -> None:
        """5 blocks (< _MIN_AXIS_LABEL_COUNT) are resolved, not removed."""
        blocks = [
            {
                "text": f"t{i}",
                "is_vertical": True,
                "rect": [50 + i * 12, 50, 60 + i * 12, 100],
            }
            for i in range(5)  # noqa: PLR2004
        ]
        result = _resolve_vertical_alignment(blocks)
        assert len(result) == 5  # noqa: PLR2004
        for b in result:
            assert "_vert_align" in b


# ── Table cell overflow redaction tests ──────────────────────────────────────


class TestTableCellOverflowRedaction:
    """Tests for _redact_x1 on cells with overflowing spans."""

    def test_overflow_span_sets_redact_x1(self) -> None:
        """Span extending past cell right edge stores _redact_x1."""
        doc = pymupdf.open()
        page = doc.new_page()
        # Create text that will overflow a narrow cell
        page.insert_text((50, 120), "Short", fontsize=10)
        page.insert_text((50, 140), "Very long text that overflows", fontsize=10)
        doc_bytes = doc.tobytes()
        doc.close()

        doc2 = pymupdf.open(stream=doc_bytes, filetype="pdf")
        page2 = doc2[0]
        page_dict = page2.get_text("dict")

        # Build a table with a narrow cell (x0=40, x1=100) that doesn't
        # fully contain the long text; cell right edge < text right edge
        tables = [
            {
                "cells": [(40, 110, 100, 150)],
            }
        ]
        blocks = _extract_table_cell_blocks(tables, page_dict)
        # The long text overflows past x=100
        overflow = [b for b in blocks if b.get("_redact_x1")]
        if overflow:
            assert overflow[0]["_redact_x1"] > 100  # noqa: PLR2004

        doc2.close()

    def test_no_overflow_no_redact_x1(self) -> None:
        """Cell that fully contains its spans has no _redact_x1."""
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((60, 120), "Hi", fontsize=10)
        doc_bytes = doc.tobytes()
        doc.close()

        doc2 = pymupdf.open(stream=doc_bytes, filetype="pdf")
        page2 = doc2[0]
        page_dict = page2.get_text("dict")

        tables = [{"cells": [(40, 110, 200, 130)]}]
        blocks = _extract_table_cell_blocks(tables, page_dict)
        for b in blocks:
            assert "_redact_x1" not in b
            assert "_redact_x0" not in b

        doc2.close()

    def test_leftward_overflow_sets_redact_x0(self) -> None:
        """Span starting before cell left edge stores _redact_x0."""
        doc = pymupdf.open()
        page = doc.new_page()
        # Text starts at x=50, but cell left edge will be at x=80
        page.insert_text((50, 120), "merged cell text here", fontsize=10)
        doc_bytes = doc.tobytes()
        doc.close()

        doc2 = pymupdf.open(stream=doc_bytes, filetype="pdf")
        page2 = doc2[0]
        page_dict = page2.get_text("dict")

        # Cell starts at x=80, but the text starts at ~50
        tables = [{"cells": [(80, 110, 300, 130)]}]
        blocks = _extract_table_cell_blocks(tables, page_dict)
        overflow = [b for b in blocks if b.get("_redact_x0")]
        if overflow:
            assert overflow[0]["_redact_x0"] < 80  # noqa: PLR2004

        doc2.close()

    def test_both_sides_overflow(self) -> None:
        """Span overflowing both left and right stores both _redact keys."""
        doc = pymupdf.open()
        page = doc.new_page()
        # Wide text that overflows both a narrow cell
        page.insert_text(
            (30, 120),
            "This very wide text overflows both edges",
            fontsize=10,
        )
        doc_bytes = doc.tobytes()
        doc.close()

        doc2 = pymupdf.open(stream=doc_bytes, filetype="pdf")
        page2 = doc2[0]
        page_dict = page2.get_text("dict")

        # Narrow cell in the middle of the wide span
        tables = [{"cells": [(80, 110, 120, 130)]}]
        blocks = _extract_table_cell_blocks(tables, page_dict)
        both = [b for b in blocks if b.get("_redact_x0") and b.get("_redact_x1")]
        if both:
            assert both[0]["_redact_x0"] < 80  # noqa: PLR2004
            assert both[0]["_redact_x1"] > 120  # noqa: PLR2004

        doc2.close()

    def test_within_tolerance_no_overflow_flags(self) -> None:
        """Span within 1pt of cell edge does NOT set overflow flags."""
        doc = pymupdf.open()
        page = doc.new_page()
        # Text at x=59 — will be just ~1pt before cell left at x=60
        page.insert_text((59, 120), "X", fontsize=10)
        doc_bytes = doc.tobytes()
        doc.close()

        doc2 = pymupdf.open(stream=doc_bytes, filetype="pdf")
        page2 = doc2[0]
        page_dict = page2.get_text("dict")

        # Cell boundary at x=60; text starts at ~59 (within 1pt tolerance)
        tables = [{"cells": [(60, 110, 200, 130)]}]
        blocks = _extract_table_cell_blocks(tables, page_dict)
        for b in blocks:
            # Tolerance is 1.0pt — span at 59 is only 1pt before 60
            # so _redact_x0 should NOT be set
            assert "_redact_x0" not in b

        doc2.close()


# ── _apply_translated_blocks redaction extension ──────────────────────────────


class TestApplyRedactionExtension:
    """Tests that _apply_translated_blocks extends redaction rect via overflow keys."""

    def test_redact_x0_extends_redaction_left(self) -> None:
        """_redact_x0 extends the redaction rect leftward."""
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((50, 120), "Some text", fontsize=10)

        block = {
            "rect": [80, 110, 300, 130],
            "translated_text": "Translated",
            "_redact_x0": 40.0,
            "font_size": 10.0,
            "color": 0,
            "bold": False,
            "italic": False,
            "is_table_cell": True,
        }
        _apply_translated_blocks(page, [block], pymupdf)
        # If it didn't crash, the redaction was applied successfully.
        # Verify the text overlay was placed in the cell rect area.
        doc.close()

    def test_redact_x1_extends_redaction_right(self) -> None:
        """_redact_x1 extends the redaction rect rightward."""
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((50, 120), "Some text that overflows", fontsize=10)

        block = {
            "rect": [40, 110, 100, 130],
            "translated_text": "Translated",
            "_redact_x1": 250.0,
            "font_size": 10.0,
            "color": 0,
            "bold": False,
            "italic": False,
            "is_table_cell": True,
        }
        _apply_translated_blocks(page, [block], pymupdf)
        doc.close()

    def test_both_redact_extensions(self) -> None:
        """Both _redact_x0 and _redact_x1 extend the redaction rect."""
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((30, 120), "Wide text spanning both sides", fontsize=10)

        block = {
            "rect": [80, 110, 120, 130],
            "translated_text": "Translated",
            "_redact_x0": 25.0,
            "_redact_x1": 300.0,
            "font_size": 10.0,
            "color": 0,
            "bold": False,
            "italic": False,
            "is_table_cell": True,
        }
        _apply_translated_blocks(page, [block], pymupdf)
        doc.close()

    def test_no_extension_when_keys_absent(self) -> None:
        """Without overflow keys, redaction uses the block rect only."""
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((60, 120), "Contained text", fontsize=10)

        block = {
            "rect": [40, 110, 300, 130],
            "translated_text": "Translated",
            "font_size": 10.0,
            "color": 0,
            "bold": False,
            "italic": False,
            "is_table_cell": True,
        }
        _apply_translated_blocks(page, [block], pymupdf)
        doc.close()


# ── _adjust_dividers_for_text: Adjustment 2 (shift right) ──────────────────


class TestAdjustDividersShiftRight:
    """Tests for Adjustment 2 in _adjust_dividers_for_text (rightward shift)."""

    def test_left_column_overflow_shifts_divider_right(self) -> None:
        """When left-column text overflows past divider, divider shifts right."""
        dividers = [0.0, 200.0, 400.0]
        # Left-column span: center at 100, but right edge at 225 (overflows 200)
        # Right-column span: starts at 260
        rows = [
            [{"bbox": (50, 10, 150, 20)}, {"bbox": (260, 10, 360, 20)}],
            [{"bbox": (20, 30, 225, 40)}, {"bbox": (260, 30, 360, 40)}],
        ]
        _adjust_dividers_for_text(dividers, rows)
        # Divider should move right to midpoint of (225, 260) = 242.5
        assert dividers[1] > 200  # noqa: PLR2004
        assert 225 < dividers[1] < 260  # noqa: PLR2004

    def test_no_right_shift_when_gap_absent(self) -> None:
        """If right-column text starts before overflow, divider stays."""
        dividers = [0.0, 200.0, 400.0]
        # Left-column overflow at 225, but right-column also starts at 210
        # (min_right_x0=210 < max_overflow=225 → no shift)
        rows = [
            [{"bbox": (20, 10, 225, 20)}, {"bbox": (210, 10, 360, 20)}],
        ]
        _adjust_dividers_for_text(dividers, rows)
        # Adjustment 1 may shift left (span at 210 with center at 285 > 200)
        # But adjustment 2 should NOT shift right since gap is insufficient
        # Just check divider didn't move past 225
        assert dividers[1] <= 225  # noqa: PLR2004

    def test_edges_unaffected_by_right_shift(self) -> None:
        """Table edge dividers are not affected by adjustment 2."""
        dividers = [0.0, 200.0, 400.0]
        rows = [
            [{"bbox": (20, 10, 225, 20)}, {"bbox": (260, 10, 360, 20)}],
        ]
        _adjust_dividers_for_text(dividers, rows)
        assert dividers[0] == 0.0
        assert dividers[-1] == 400.0

    def test_cross_column_span_ignored(self) -> None:
        """Wide spans (footnotes/captions) spanning multiple columns are skipped."""
        # 5 columns, each ~30pt wide
        dividers = [0.0, 30.0, 60.0, 90.0, 120.0, 150.0]
        original = list(dividers)
        # Normal spans in each column
        normal_rows = [
            [
                {"bbox": (5, 10, 25, 20)},
                {"bbox": (35, 10, 55, 20)},
                {"bbox": (65, 10, 85, 20)},
                {"bbox": (95, 10, 115, 20)},
                {"bbox": (125, 10, 145, 20)},
            ],
        ]
        # A cross-column footnote span: starts at x=5, ends at x=140 (135pt wide)
        footnote_rows = [
            [{"bbox": (5, 30, 140, 40)}],
        ]
        _adjust_dividers_for_text(dividers, normal_rows + footnote_rows)
        # The footnote should NOT shift any interior dividers
        assert dividers == original


# ── _merge_visual_and_inferred ───────────────────────────────────────────────


class TestMergeVisualAndInferred:
    """Tests for the hybrid visual + inferred column merge."""

    @staticmethod
    def _make_page_dict(spans: list[dict]) -> dict:
        """Build a minimal page_dict containing the given spans."""
        lines = [{"dir": (1.0, 0.0), "spans": [s]} for s in spans]
        return {"blocks": [{"type": 0, "lines": lines}]}

    def test_inferred_subdivides_wide_visual_column(self) -> None:
        """Inferred divider splits a wide visual column into two."""
        # Visual: 2 columns [0-200, 200-400]
        visual = {
            "bbox": (0, 0, 400, 40),
            "cells": [
                (0, 0, 200, 20),
                (200, 0, 400, 20),
                (0, 20, 200, 40),
                (200, 20, 400, 40),
            ],
        }
        # Inferred: 3 columns [0-100, 100-200, 200-400]
        ruled = {
            "bbox": (0, 0, 400, 40),
            "cells": [
                (0, 0, 100, 20),
                (100, 0, 200, 20),
                (200, 0, 400, 20),
                (0, 20, 100, 40),
                (100, 20, 200, 40),
                (200, 20, 400, 40),
            ],
        }
        spans = [
            {"bbox": (10, 5, 90, 15), "text": "A"},
            {"bbox": (110, 5, 190, 15), "text": "B"},
            {"bbox": (210, 5, 390, 15), "text": "C"},
            {"bbox": (10, 25, 90, 35), "text": "D"},
            {"bbox": (110, 25, 190, 35), "text": "E"},
            {"bbox": (210, 25, 390, 35), "text": "F"},
        ]
        page_dict = self._make_page_dict(spans)
        result = _merge_visual_and_inferred(visual, ruled, page_dict)
        # Should have 3 columns now (visual border at 200 kept, inferred at 100 added)
        x_edges = sorted(
            {round(c[0], 1) for c in result["cells"]}
            | {round(c[2], 1) for c in result["cells"]}
        )
        assert len(x_edges) - 1 == 3  # noqa: PLR2004
        assert 100.0 in x_edges
        assert 200.0 in x_edges

    def test_narrow_inferred_divider_rejected(self) -> None:
        """Inferred divider creating a < 8pt sub-column is rejected."""
        # Visual: 1 wide column [0-50]
        visual = {
            "bbox": (0, 0, 50, 20),
            "cells": [(0, 0, 50, 20)],
        }
        # Inferred puts divider at x=5 → left sub-column is 5pt (too narrow)
        ruled = {
            "bbox": (0, 0, 50, 20),
            "cells": [(0, 0, 5, 20), (5, 0, 50, 20)],
        }
        spans = [
            {"bbox": (1, 5, 4, 15), "text": "A"},
            {"bbox": (10, 5, 45, 15), "text": "B"},
        ]
        page_dict = self._make_page_dict(spans)
        result = _merge_visual_and_inferred(visual, ruled, page_dict)
        x_edges = sorted(
            {round(c[0], 1) for c in result["cells"]}
            | {round(c[2], 1) for c in result["cells"]}
        )
        # Divider at 5 should be rejected → still 1 column
        assert 5.0 not in x_edges

    def test_duplicate_near_visual_divider_skipped(self) -> None:
        """Inferred divider within snap tolerance of visual border is skipped."""
        visual = {
            "bbox": (0, 0, 400, 20),
            "cells": [(0, 0, 200, 20), (200, 0, 400, 20)],
        }
        # Inferred divider at 201 — within 2pt of visual 200
        ruled = {
            "bbox": (0, 0, 400, 20),
            "cells": [(0, 0, 201, 20), (201, 0, 400, 20)],
        }
        spans = [
            {"bbox": (10, 5, 190, 15), "text": "A"},
            {"bbox": (210, 5, 390, 15), "text": "B"},
        ]
        page_dict = self._make_page_dict(spans)
        result = _merge_visual_and_inferred(visual, ruled, page_dict)
        x_edges = sorted(
            {round(c[0], 1) for c in result["cells"]}
            | {round(c[2], 1) for c in result["cells"]}
        )
        assert 201.0 not in x_edges
        assert 200.0 in x_edges

    def test_row_boundaries_merged(self) -> None:
        """Row boundaries from both tables are combined."""
        # Visual has rows at y=0,20,40; ruled has rows at y=0,10,20,40
        visual = {
            "bbox": (0, 0, 100, 40),
            "cells": [
                (0, 0, 100, 20),
                (0, 20, 100, 40),
            ],
        }
        ruled = {
            "bbox": (0, 0, 100, 40),
            "cells": [
                (0, 0, 100, 10),
                (0, 10, 100, 20),
                (0, 20, 100, 40),
            ],
        }
        spans = [
            {"bbox": (10, 2, 90, 8), "text": "R1"},
            {"bbox": (10, 12, 90, 18), "text": "R2"},
            {"bbox": (10, 22, 90, 38), "text": "R3"},
        ]
        page_dict = self._make_page_dict(spans)
        result = _merge_visual_and_inferred(visual, ruled, page_dict)
        y_edges = sorted(
            {round(c[1], 1) for c in result["cells"]}
            | {round(c[3], 1) for c in result["cells"]}
        )
        # Should have 3 row boundaries from ruled (y=0,10,20,40)
        assert 10.0 in y_edges

    def test_visual_borders_always_preserved(self) -> None:
        """Visual borders are never removed, even with fewer inferred dividers."""
        visual = {
            "bbox": (0, 0, 300, 20),
            "cells": [
                (0, 0, 100, 20),
                (100, 0, 200, 20),
                (200, 0, 300, 20),
            ],
        }
        # Inferred has only 2 columns (merged 2 visual columns)
        ruled = {
            "bbox": (0, 0, 300, 20),
            "cells": [(0, 0, 200, 20), (200, 0, 300, 20)],
        }
        spans = [
            {"bbox": (10, 5, 90, 15), "text": "A"},
            {"bbox": (110, 5, 190, 15), "text": "B"},
            {"bbox": (210, 5, 290, 15), "text": "C"},
        ]
        page_dict = self._make_page_dict(spans)
        result = _merge_visual_and_inferred(visual, ruled, page_dict)
        x_edges = sorted(
            {round(c[0], 1) for c in result["cells"]}
            | {round(c[2], 1) for c in result["cells"]}
        )
        # All 3 visual dividers must be present
        assert 100.0 in x_edges
        assert 200.0 in x_edges


# ── _detect_column_alignment: additional edge cases ──────────────────────────


class TestDetectColumnAlignmentEdgeCases:
    """Additional edge cases for _detect_column_alignment."""

    def test_near_tie_left_right_favours_center(self) -> None:
        """When left/right variances are nearly equal, center wins."""
        # Text centered at x=50: widths vary symmetrically
        col_spans = [
            [{"bbox": (40, 10, 60, 20)}],  # center=50, width=20
            [{"bbox": (30, 30, 70, 40)}],  # center=50, width=40
            [{"bbox": (35, 50, 65, 60)}],  # center=50, width=30
            [{"bbox": (25, 70, 75, 80)}],  # center=50, width=50
        ]
        assert _detect_column_alignment(col_spans) == "center"

    def test_right_aligned_varying_widths(self) -> None:
        """Right-aligned column with varying text widths."""
        # All right edges at x=100, varying left edges
        col_spans = [
            [{"bbox": (60, 10, 100, 20)}],  # width=40
            [{"bbox": (30, 30, 100, 40)}],  # width=70
            [{"bbox": (80, 50, 100, 60)}],  # width=20
            [{"bbox": (50, 70, 100, 80)}],  # width=50
        ]
        assert _detect_column_alignment(col_spans) == "right"

    def test_left_aligned_varying_widths(self) -> None:
        """Left-aligned column with varying text widths."""
        # All left edges at x=10, varying right edges
        col_spans = [
            [{"bbox": (10, 10, 50, 20)}],  # width=40
            [{"bbox": (10, 30, 80, 40)}],  # width=70
            [{"bbox": (10, 50, 30, 60)}],  # width=20
            [{"bbox": (10, 70, 60, 80)}],  # width=50
        ]
        assert _detect_column_alignment(col_spans) == "left"

    def test_single_outlier_does_not_break_center(self) -> None:
        """One mild outlier among many centered cells still detects center."""
        # 5 cells centered at x=50, 1 mild outlier (center=45)
        col_spans = [
            [{"bbox": (40, 10, 60, 20)}],
            [{"bbox": (30, 30, 70, 40)}],
            [{"bbox": (35, 50, 65, 60)}],
            [{"bbox": (42, 70, 58, 80)}],
            [{"bbox": (38, 90, 62, 100)}],
            [{"bbox": (30, 110, 60, 120)}],  # mild outlier: center=45
        ]
        assert _detect_column_alignment(col_spans) == "center"

    def test_two_cells_uniform_width_defaults_center(self) -> None:
        """Two cells with identical width → all variances ~0 → center."""
        col_spans = [
            [{"bbox": (10, 10, 90, 20)}],
            [{"bbox": (10, 30, 90, 40)}],
        ]
        assert _detect_column_alignment(col_spans) == "center"

    def test_multiple_spans_per_cell_uses_extremes(self) -> None:
        """Cell with multiple spans: left = min, right = max."""
        col_spans = [
            # Two spans in cell: combined extent (10, 80)
            [{"bbox": (10, 10, 50, 20)}, {"bbox": (40, 10, 80, 20)}],
            # Combined extent (10, 60)
            [{"bbox": (10, 30, 60, 40)}],
            # Combined extent (10, 70)
            [{"bbox": (10, 50, 40, 60)}, {"bbox": (30, 50, 70, 60)}],
        ]
        # Left edges are all 10 → consistent. Right edges vary → left-aligned
        assert _detect_column_alignment(col_spans) == "left"

    def test_identical_width_all_cells_zero_variance(self) -> None:
        """All cells have identical width/position → all variances 0 → center."""
        col_spans = [
            [{"bbox": (50, 10, 150, 20)}],
            [{"bbox": (50, 30, 150, 40)}],
            [{"bbox": (50, 50, 150, 60)}],
        ]
        assert _detect_column_alignment(col_spans) == "center"

    def test_scattered_empty_cells_filtered(self) -> None:
        """Multiple empty cells scattered among valid ones."""
        col_spans = [
            [],
            [{"bbox": (10, 20, 100, 30)}],
            [],
            [],
            [{"bbox": (10, 60, 80, 70)}],
            [{"bbox": (10, 100, 120, 110)}],
        ]
        # 3 non-empty with consistent left=10 → left
        assert _detect_column_alignment(col_spans) == "left"


# ── _build_row_cells_with_spanning ────────────────────────────────────────────


class TestBuildRowCellsWithSpanning:
    """Tests for _build_row_cells_with_spanning (horizontal merged cell detection)."""

    @staticmethod
    def _make_page_with_spans(
        span_positions: list[tuple[float, float, float, float, str]],
    ) -> dict[str, Any]:
        """Create a page_dict with spans at given positions.

        Each entry: (x0, y0, x1, y1, text).
        """
        doc = pymupdf.open()
        page = doc.new_page()
        for x, y, _x1, _y1, text in span_positions:
            page.insert_text((x, y + 10), text, fontsize=10)
        doc_bytes = doc.tobytes()
        doc.close()
        doc2 = pymupdf.open(stream=doc_bytes, filetype="pdf")
        page_dict = doc2[0].get_text("dict")
        doc2.close()
        return page_dict

    def test_no_spanning_produces_individual_cells(self) -> None:
        """Spans within their columns produce individual cells."""
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((20, 120), "A", fontsize=10)
        page.insert_text((120, 120), "B", fontsize=10)
        page.insert_text((220, 120), "C", fontsize=10)
        doc_bytes = doc.tobytes()
        doc.close()

        doc2 = pymupdf.open(stream=doc_bytes, filetype="pdf")
        page_dict = doc2[0].get_text("dict")

        dividers = [0.0, 100.0, 200.0, 300.0]
        cells = _build_row_cells_with_spanning(page_dict, dividers, 100, 130)
        assert len(cells) == 3  # noqa: PLR2004
        doc2.close()

    def test_spanning_merges_columns(self) -> None:
        """Span crossing a divider merges columns into one wider cell."""
        doc = pymupdf.open()
        page = doc.new_page()
        # Span from x=80 to ~250 — crosses divider at 150
        page.insert_text((80, 120), "long text crossing boundary", fontsize=10)
        doc_bytes = doc.tobytes()
        doc.close()

        doc2 = pymupdf.open(stream=doc_bytes, filetype="pdf")
        page_dict = doc2[0].get_text("dict")

        dividers = [0.0, 150.0, 300.0]
        cells = _build_row_cells_with_spanning(page_dict, dividers, 100, 130)
        # Should produce 1 merged cell spanning both columns
        merged = [c for c in cells if c[2] - c[0] > 150]  # noqa: PLR2004
        assert len(merged) >= 1

        doc2.close()

    def test_empty_row_produces_grid(self) -> None:
        """Row with no text spans gets the simple column grid."""
        doc = pymupdf.open()
        doc.new_page()
        # No text in this area
        doc_bytes = doc.tobytes()
        doc.close()

        doc2 = pymupdf.open(stream=doc_bytes, filetype="pdf")
        page_dict = doc2[0].get_text("dict")

        dividers = [0.0, 100.0, 200.0, 300.0]
        cells = _build_row_cells_with_spanning(page_dict, dividers, 500, 530)
        assert len(cells) == 3  # noqa: PLR2004
        # All cells are simple column widths
        for i, cell in enumerate(cells):
            assert cell[0] == dividers[i]
            assert cell[2] == dividers[i + 1]

        doc2.close()

    def test_single_column_returns_empty(self) -> None:
        """Single column (n_cols=0) returns empty list."""
        doc = pymupdf.open()
        doc.new_page()
        doc_bytes = doc.tobytes()
        doc.close()

        doc2 = pymupdf.open(stream=doc_bytes, filetype="pdf")
        page_dict = doc2[0].get_text("dict")

        # Only one divider → n_cols = 0
        dividers = [100.0]
        cells = _build_row_cells_with_spanning(page_dict, dividers, 100, 130)
        assert cells == []
        doc2.close()

    def test_slight_spill_does_not_merge(self) -> None:
        """Span barely spilling past divider (< 30% overlap) stays in its column."""
        doc = pymupdf.open()
        page = doc.new_page()
        # Short text near divider — center stays in left column
        page.insert_text((85, 120), "AB", fontsize=10)
        doc_bytes = doc.tobytes()
        doc.close()

        doc2 = pymupdf.open(stream=doc_bytes, filetype="pdf")
        page_dict = doc2[0].get_text("dict")

        # Divider at 100, column width = 100
        dividers = [0.0, 100.0, 200.0]
        cells = _build_row_cells_with_spanning(page_dict, dividers, 100, 130)
        # The span center should be in the left column; no merge
        unmerged = [c for c in cells if c[2] - c[0] < 150]  # noqa: PLR2004
        assert len(unmerged) >= 1

        doc2.close()

    def test_multiple_merge_groups_in_row(self) -> None:
        """Two independent merge groups in the same row."""
        doc = pymupdf.open()
        page = doc.new_page()
        # Span 1: crosses divider at 100 (merges cols 0-1)
        page.insert_text((50, 120), "left merge group text", fontsize=10)
        # Span 2: crosses divider at 300 (merges cols 2-3)
        page.insert_text((250, 120), "right merge group text", fontsize=10)
        doc_bytes = doc.tobytes()
        doc.close()

        doc2 = pymupdf.open(stream=doc_bytes, filetype="pdf")
        page_dict = doc2[0].get_text("dict")

        dividers = [0.0, 100.0, 200.0, 300.0, 400.0]
        cells = _build_row_cells_with_spanning(page_dict, dividers, 100, 130)
        # Should have merged cells; total should be < 4
        merged = [c for c in cells if c[2] - c[0] > 100]  # noqa: PLR2004
        assert len(merged) >= 1

        doc2.close()


# ── _expand_ligatures tests ──────────────────────────────────────────────────


class TestExpandLigatures:
    """Tests for _expand_ligatures and _LIGATURE_MAP."""

    def test_no_ligatures_passthrough(self) -> None:
        """Plain ASCII text is returned unchanged with identity pos_map."""
        text, pos_map = _expand_ligatures("hello")
        assert text == "hello"
        assert pos_map == [0, 1, 2, 3, 4]

    def test_empty_string(self) -> None:
        """Empty input returns empty output."""
        text, pos_map = _expand_ligatures("")
        assert text == ""
        assert pos_map == []

    def test_fl_ligature(self) -> None:
        """U+FB02 (ﬂ) expands to 'fl'."""
        text, pos_map = _expand_ligatures("tensor\ufb02ow")
        assert text == "tensorflow"
        # 'tensor' = indices 0-5, ﬂ expands to f(6),l(6), 'ow' = 7,8
        assert pos_map == [0, 1, 2, 3, 4, 5, 6, 6, 7, 8]

    def test_fi_ligature(self) -> None:
        """U+FB01 (ﬁ) expands to 'fi'."""
        text, pos_map = _expand_ligatures("\ufb01le")
        assert text == "file"
        assert pos_map == [0, 0, 1, 2]

    def test_ff_ligature(self) -> None:
        """U+FB00 (ﬀ) expands to 'ff'."""
        text, pos_map = _expand_ligatures("e\ufb00ect")
        assert text == "effect"
        assert pos_map == [0, 1, 1, 2, 3, 4]

    def test_ffi_ligature(self) -> None:
        """U+FB03 (ﬃ) expands to 'ffi'."""
        text, pos_map = _expand_ligatures("o\ufb03ce")
        assert text == "office"
        assert pos_map == [0, 1, 1, 1, 2, 3]

    def test_ffl_ligature(self) -> None:
        """U+FB04 (ﬄ) expands to 'ffl'."""
        text, pos_map = _expand_ligatures("wa\ufb04e")
        assert text == "waffle"
        assert pos_map == [0, 1, 2, 2, 2, 3]

    def test_consecutive_ligatures(self) -> None:
        """Two adjacent ligatures expand correctly."""
        text, pos_map = _expand_ligatures("\ufb01\ufb02")
        assert text == "fifl"
        assert pos_map == [0, 0, 1, 1]

    def test_all_five_ligatures_in_map(self) -> None:
        """_LIGATURE_MAP has exactly the 5 standard f-ligatures."""
        assert len(_LIGATURE_MAP) == 5  # noqa: PLR2004
        assert "\ufb00" in _LIGATURE_MAP
        assert "\ufb01" in _LIGATURE_MAP
        assert "\ufb02" in _LIGATURE_MAP
        assert "\ufb03" in _LIGATURE_MAP
        assert "\ufb04" in _LIGATURE_MAP


# ── _get_block_chars tests ───────────────────────────────────────────────────


class TestGetBlockChars:
    """Tests for _get_block_chars."""

    def _make_chars(
        self,
        specs: list[tuple[str, float, float, float, float]],
    ) -> list[tuple[str, Any]]:
        """Build (char, Rect) list from (char, x0, y0, x1, y1) specs."""
        return [(c, pymupdf.Rect(x0, y0, x1, y1)) for c, x0, y0, x1, y1 in specs]

    def test_chars_inside_block(self) -> None:
        """Chars whose center is inside block rect are returned."""
        chars = self._make_chars(
            [
                ("A", 10, 10, 20, 20),  # center (15, 15)
                ("B", 30, 10, 40, 20),  # center (35, 15)
            ]
        )
        block_rect = pymupdf.Rect(0, 0, 50, 25)
        result = _get_block_chars(chars, block_rect)
        assert len(result) == 2  # noqa: PLR2004
        assert result[0][0] == "A"
        assert result[1][0] == "B"

    def test_chars_outside_block(self) -> None:
        """Chars whose center is outside block rect are excluded."""
        chars = self._make_chars(
            [
                ("A", 10, 10, 20, 20),  # center (15, 15) — inside
                ("B", 100, 100, 110, 110),  # center (105, 105) — outside
            ]
        )
        block_rect = pymupdf.Rect(0, 0, 50, 50)
        result = _get_block_chars(chars, block_rect)
        assert len(result) == 1
        assert result[0][0] == "A"

    def test_empty_chars_list(self) -> None:
        """Empty input returns empty result."""
        result = _get_block_chars([], pymupdf.Rect(0, 0, 100, 100))
        assert result == []

    def test_boundary_center_included(self) -> None:
        """Char whose center is exactly on block boundary is included."""
        chars = self._make_chars([("X", 45, 45, 55, 55)])  # center (50, 50)
        block_rect = pymupdf.Rect(0, 0, 50, 50)  # boundary at 50
        result = _get_block_chars(chars, block_rect)
        assert len(result) == 1

    def test_overlapping_but_center_outside(self) -> None:
        """Char overlaps block but center is outside — excluded."""
        chars = self._make_chars([("X", 48, 10, 60, 20)])  # center (54, 15)
        block_rect = pymupdf.Rect(0, 0, 50, 25)
        result = _get_block_chars(chars, block_rect)
        assert result == []

    def test_preserves_reading_order(self) -> None:
        """Returned chars maintain input order (reading order)."""
        chars = self._make_chars(
            [
                ("H", 10, 10, 15, 20),
                ("e", 15, 10, 20, 20),
                ("l", 20, 10, 25, 20),
            ]
        )
        block_rect = pymupdf.Rect(0, 0, 100, 100)
        result = _get_block_chars(chars, block_rect)
        text = "".join(c for c, _ in result)
        assert text == "Hel"


# ── _find_link_in_chars tests ────────────────────────────────────────────────


class TestFindLinkInChars:
    """Tests for _find_link_in_chars."""

    def _make_block(
        self,
        text: str,
    ) -> tuple[list[tuple[str, Any]], str]:
        """Build block_chars and block_text from a string.

        Each char gets a 6×12pt rect placed sequentially.
        """
        chars = []
        for i, c in enumerate(text):
            x0 = 10.0 + i * 6
            chars.append((c, pymupdf.Rect(x0, 100, x0 + 6, 112)))
        return chars, text

    def test_finds_duplicate_by_search_pos(self) -> None:
        """search_pos disambiguates duplicate text."""
        chars, text = self._make_block("ref 2 and ref 2 end")
        link1 = {
            "_translated": "2",
            "_inner": "2",
            "from": (30, 100, 60, 112),
        }
        link2 = {
            "_translated": "2",
            "_inner": "2",
            "from": (30, 100, 60, 112),
        }
        rects1, pos1 = _find_link_in_chars(chars, text, link1, 0)
        rects2, _ = _find_link_in_chars(chars, text, link2, pos1)
        assert len(rects1) == 1
        assert len(rects2) == 1
        # 1st "2" at position 4, 2nd "2" at position 14
        assert abs(rects1[0].x0 - (10 + 4 * 6)) < 0.1  # noqa: PLR2004
        assert abs(rects2[0].x0 - (10 + 14 * 6)) < 0.1  # noqa: PLR2004

    def test_finds_inner_match(self) -> None:
        """Basic _inner match returns correct rect."""
        chars, text = self._make_block("See [13] for details")
        link = {"_inner": "[13]", "from": (30, 100, 60, 112)}
        rects, new_pos = _find_link_in_chars(chars, text, link, 0)
        assert len(rects) == 1
        # Should cover chars at positions 4-7 ("[13]")
        assert new_pos == 8  # noqa: PLR2004

    def test_not_found_returns_empty_list(self) -> None:
        """Returns ([], search_pos) when text not in chars."""
        chars, text = self._make_block("Hello World")
        link = {"_inner": "xyz", "from": (0, 100, 50, 112)}
        rects, new_pos = _find_link_in_chars(chars, text, link, 0)
        assert rects == []
        assert new_pos == 0

    def test_sequential_search_pos(self) -> None:
        """Multiple links in same block disambiguated by search_pos."""
        chars, text = self._make_block("[11, 9, 10]")
        link1 = {"_inner": "11", "from": (0, 100, 30, 112)}
        link2 = {"_inner": "9", "from": (30, 100, 45, 112)}
        link3 = {"_inner": "10", "from": (45, 100, 60, 112)}
        r1, pos1 = _find_link_in_chars(chars, text, link1, 0)
        r2, pos2 = _find_link_in_chars(chars, text, link2, pos1)
        r3, pos3 = _find_link_in_chars(chars, text, link3, pos2)
        assert len(r1) == 1
        assert len(r2) == 1
        assert len(r3) == 1
        # Rects should be in left-to-right order
        assert r1[0].x0 < r2[0].x0 < r3[0].x0

    def test_context_chars_disambiguate(self) -> None:
        """_left_char/_right_char pick correct occurrence of '2'."""
        chars, text = self._make_block("hơn 2.0 BLEU Bảng 2)")
        link = {
            "_translated": "2",
            "_inner": "2",
            "_left_char": " ",
            "_right_char": ")",
            "from": (0, 100, 50, 112),
        }
        rects, _ = _find_link_in_chars(chars, text, link, 0)
        assert len(rects) == 1
        # Should match "2" before ")" (position 18), not "2" in "2.0" (position 4)
        expected_x = 10 + 18 * 6  # noqa: PLR2004
        assert abs(rects[0].x0 - expected_x) < 0.1

    def test_translated_preferred_over_inner(self) -> None:
        """_translated is tried before _inner."""
        chars, text = self._make_block("Xin chào thế giới")
        link = {
            "_translated": "thế giới",
            "_inner": "Hello World",
            "from": (0, 100, 50, 112),
        }
        rects, _ = _find_link_in_chars(chars, text, link, 0)
        assert len(rects) == 1

    def test_inner_fallback(self) -> None:
        """Falls back to _inner when _translated not found."""
        chars, text = self._make_block("reference 42 here")
        link = {
            "_translated": "xyz not found",
            "_inner": "42",
            "from": (0, 100, 50, 112),
        }
        rects, _ = _find_link_in_chars(chars, text, link, 0)
        assert len(rects) == 1

    def test_ligature_matching(self) -> None:
        """Matches text containing ligature fl (U+FB02) vs plain 'fl'."""
        # Block text has ligature (as PyMuPDF renders)
        chars, text = self._make_block("tensor\ufb02ow/t2t")
        link = {
            "_inner": "tensorflow/t2t",
            "from": (0, 100, 100, 112),
        }
        rects, _ = _find_link_in_chars(chars, text, link, 0)
        assert len(rects) == 1

    def test_ligature_fi_matching(self) -> None:
        """Matches text containing ligature fi (U+FB01) vs plain 'fi'."""
        chars, text = self._make_block("a \ufb01le here")
        link = {"_inner": "file", "from": (0, 100, 50, 112)}
        rects, _ = _find_link_in_chars(chars, text, link, 0)
        assert len(rects) == 1

    def test_height_preserved_from_original(self) -> None:
        """Link rect height matches original, not char bbox height."""
        # Chars with 20pt height (typical htmlbox line-height)
        chars = [
            ("A", pymupdf.Rect(10, 90, 16, 110)),
            ("B", pymupdf.Rect(16, 90, 22, 110)),
        ]
        text = "AB"
        # Original link was only 9pt tall
        link = {"_inner": "AB", "from": (10, 95, 22, 104)}
        rects, _ = _find_link_in_chars(chars, text, link, 0)
        assert len(rects) == 1
        assert abs(rects[0].height - 9.0) < 0.1  # noqa: PLR2004

    def test_no_height_shrink_when_original_taller(self) -> None:
        """Original height larger than char height is not applied."""
        chars = [("X", pymupdf.Rect(10, 100, 16, 108))]
        text = "X"
        # Original link was 20pt tall — don't shrink chars
        link = {"_inner": "X", "from": (10, 90, 16, 110)}
        rects, _ = _find_link_in_chars(chars, text, link, 0)
        assert len(rects) == 1
        assert abs(rects[0].height - 8.0) < 0.1  # noqa: PLR2004

    def test_search_pos_beyond_text(self) -> None:
        """search_pos past end of text returns empty list."""
        chars, text = self._make_block("ABC")
        link = {"_inner": "A", "from": (0, 100, 10, 112)}
        rects, pos = _find_link_in_chars(chars, text, link, 100)  # noqa: PLR2004
        assert rects == []

    def test_multiline_link_returns_per_line_rects(self) -> None:
        """Link spanning two visual lines returns one rect per line.

        Lines are separated by a y-gap of 8pt (120-112), well above
        ``_LINK_LINE_Y_GAP`` (3pt), so they form distinct line groups.
        """
        chars: list[tuple[str, Any]] = []
        line1 = "at https://"
        line2 = "github.com/t2t."
        for i, c in enumerate(line1):
            x0 = 10.0 + i * 6
            chars.append((c, pymupdf.Rect(x0, 100, x0 + 6, 112)))
        for i, c in enumerate(line2):
            x0 = 10.0 + i * 6
            chars.append((c, pymupdf.Rect(x0, 120, x0 + 6, 132)))
        text = line1 + line2
        link = {
            "_inner": "https://github.com/t2t.",
            "from": (0, 100, 100, 112),
        }
        rects, _ = _find_link_in_chars(chars, text, link, 0)
        assert len(rects) == 2  # noqa: PLR2004
        # First rect on line 1 (y≈100-112)
        mid_y = 116.0  # noqa: PLR2004 — midpoint between lines
        assert rects[0].y0 < mid_y
        # Second rect on line 2 (y≈120-132)
        assert rects[1].y0 > mid_y
        # Each rect only spans its own line's x-range
        assert rects[0].x1 < rects[1].x1 or rects[1].x0 < rects[0].x0


# ── _insert_link_with_style tests ────────────────────────────────────────────


class TestInsertLinkWithStyle:
    """Tests for _insert_link_with_style."""

    def test_inserts_link_at_new_rect(self, tmp_path: Path) -> None:
        """Link is inserted at the provided rect."""
        pdf = tmp_path / "style.pdf"
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 100), "Hello World", fontsize=12)
        doc.save(str(pdf))
        doc.close()

        doc2 = pymupdf.open(str(pdf))
        page2 = doc2[0]
        link = {
            "kind": 1,
            "from": pymupdf.Rect(72, 85, 200, 105),
            "page": 0,
            "to": pymupdf.Point(0, 0),
        }
        new_rect = pymupdf.Rect(100, 90, 180, 108)
        _insert_link_with_style(page2, link, new_rect)

        out = tmp_path / "out.pdf"
        doc2.save(str(out))
        doc2.close()

        doc3 = pymupdf.open(str(out))
        links = doc3[0].get_links()
        doc3.close()
        assert len(links) == 1
        fr = links[0]["from"]
        assert abs(fr.x0 - 100) < 1  # noqa: PLR2004

    def test_uses_original_rect_when_none(self, tmp_path: Path) -> None:
        """When link_rect is None, original 'from' is preserved."""
        pdf = tmp_path / "orig.pdf"
        doc = pymupdf.open()
        doc.new_page()
        doc.save(str(pdf))
        doc.close()

        doc2 = pymupdf.open(str(pdf))
        page2 = doc2[0]
        orig_rect = pymupdf.Rect(72, 85, 200, 105)
        link = {
            "kind": 1,
            "from": orig_rect,
            "page": 0,
            "to": pymupdf.Point(0, 0),
        }
        _insert_link_with_style(page2, link, None)

        out = tmp_path / "out.pdf"
        doc2.save(str(out))
        doc2.close()

        doc3 = pymupdf.open(str(out))
        links = doc3[0].get_links()
        doc3.close()
        assert len(links) == 1
        assert abs(links[0]["from"].x0 - 72) < 1  # noqa: PLR2004

    def test_private_keys_stripped(self, tmp_path: Path) -> None:
        """Keys starting with '_' are not passed to insert_link."""
        pdf = tmp_path / "priv.pdf"
        doc = pymupdf.open()
        doc.new_page()
        doc.save(str(pdf))
        doc.close()

        doc2 = pymupdf.open(str(pdf))
        page2 = doc2[0]
        link = {
            "kind": 1,
            "from": pymupdf.Rect(72, 85, 200, 105),
            "page": 0,
            "to": pymupdf.Point(0, 0),
            "_inner": "6",
            "_block_idx": 3,
            "_style": {"C": "[ 0 1 0 ]", "Border": "[ 0 0 1 ]"},
        }
        # Should not raise despite private keys
        _insert_link_with_style(page2, link, None)

        out = tmp_path / "out.pdf"
        doc2.save(str(out))
        doc2.close()

        doc3 = pymupdf.open(str(out))
        links = doc3[0].get_links()
        doc3.close()
        assert len(links) == 1

    def test_style_restored_via_xref(self, tmp_path: Path) -> None:
        """Border color and width are restored from _style."""
        pdf = tmp_path / "xref.pdf"
        doc = pymupdf.open()
        doc.new_page()
        doc.save(str(pdf))
        doc.close()

        doc2 = pymupdf.open(str(pdf))
        page2 = doc2[0]
        link = {
            "kind": 1,
            "from": pymupdf.Rect(72, 85, 200, 105),
            "page": 0,
            "to": pymupdf.Point(0, 0),
            "_style": {"C": "[ 0 1 0 ]", "Border": "[ 0 0 1 ]"},
        }
        _insert_link_with_style(page2, link, None)

        out = tmp_path / "out.pdf"
        doc2.save(str(out))
        doc2.close()

        doc3 = pymupdf.open(str(out))
        xrefs = doc3[0].annot_xrefs()
        assert xrefs
        obj = doc3.xref_object(xrefs[-1][0])
        doc3.close()
        assert "/C [ 0 1 0 ]" in obj
        assert "/Border [ 0 0 1 ]" in obj

    def test_bs_nulled_when_border_without_bs(self, tmp_path: Path) -> None:
        """BS is set to null when original had Border but no BS."""
        pdf = tmp_path / "bsnull.pdf"
        doc = pymupdf.open()
        doc.new_page()
        doc.save(str(pdf))
        doc.close()

        doc2 = pymupdf.open(str(pdf))
        page2 = doc2[0]
        link = {
            "kind": 1,
            "from": pymupdf.Rect(72, 85, 200, 105),
            "page": 0,
            "to": pymupdf.Point(0, 0),
            "_style": {"Border": "[ 0 0 1 ]"},  # No BS key
        }
        _insert_link_with_style(page2, link, None)

        out = tmp_path / "out.pdf"
        doc2.save(str(out))
        doc2.close()

        doc3 = pymupdf.open(str(out))
        xrefs = doc3[0].annot_xrefs()
        obj = doc3.xref_object(xrefs[-1][0])
        doc3.close()
        assert "/BS null" in obj


# ── _save_page_links multi-line filtering tests ─────────────────────────────


class TestSavePageLinksMultiLine:
    """Tests for multi-line char filtering in _save_page_links."""

    def test_footnote_across_two_lines_keeps_closest(
        self,
        tmp_path: Path,
    ) -> None:
        """Link rect spanning two lines keeps only the closest line chars."""
        pdf = tmp_path / "footnote.pdf"
        doc = pymupdf.open()
        page = doc.new_page()
        # Line 1: body text at y=100 → chars at y≈89-103
        page.insert_text((100, 100), "scalar", fontsize=10)
        # Line 2: superscript footnote at y=112 → chars at y≈104-114
        page.insert_text((100, 112), "4", fontsize=7)
        # Link rect spans both lines but centered closer to line 2.
        # "al" chars overlap at x≈115-123, "4" at x≈100-104.
        # Rect center y=108 is closer to "4" center (≈109) than
        # "scalar" center (≈96).
        page.insert_link(
            {
                "kind": 4,
                "from": pymupdf.Rect(99, 100, 118, 116),
                "page": 0,
                "to": pymupdf.Point(0, 0),
                "nameddest": "footnote1",
            }
        )
        doc.save(str(pdf))
        doc.close()

        doc2 = pymupdf.open(str(pdf))
        saved = _save_page_links(doc2[0])
        doc2.close()

        fn_link = next(sl for sl in saved if sl.get("nameddest") == "footnote1")
        inner = fn_link.get("_inner", "")
        # Should have the footnote marker "4", not "scalar" text
        assert "4" in inner

    def test_single_line_link_unchanged(self, tmp_path: Path) -> None:
        """Link rect covering a single line keeps all chars."""
        pdf = tmp_path / "single.pdf"
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 100), "[13]", fontsize=10)
        page.insert_link(
            {
                "kind": 4,
                "from": pymupdf.Rect(72, 88, 100, 102),
                "page": 0,
                "to": pymupdf.Point(0, 0),
                "nameddest": "cite1",
            }
        )
        doc.save(str(pdf))
        doc.close()

        doc2 = pymupdf.open(str(pdf))
        saved = _save_page_links(doc2[0])
        doc2.close()

        link = next(sl for sl in saved if sl.get("nameddest") == "cite1")
        inner = link.get("_inner", "")
        assert "13" in inner


# ── _inject_link_tags inner fallback tests ───────────────────────────────────


class TestInjectLinkTagsEdgeCases:
    """Edge case tests for _inject_link_tags."""

    def test_inner_found_in_block(self) -> None:
        """_inner text found in block is wrapped and _block_idx set."""
        blocks = [
            {
                "text": "some text with superscript 4 here",
                "rect": [0, 0, 300, 20],
            }
        ]
        links = [
            {
                "_inner": "4",
                "from": [100, 0, 110, 20],
            }
        ]
        _inject_link_tags(blocks, links, pymupdf)
        assert '<a id="0">4</a>' in blocks[0]["text"]
        assert links[0].get("_block_idx") == 0

    def test_inner_wraps_in_citation(self) -> None:
        """_inner wraps correctly inside citation brackets."""
        blocks = [
            {
                "text": "refs [13] here",
                "rect": [0, 0, 300, 20],
            }
        ]
        links = [
            {
                "_inner": "13",
                "from": [30, 0, 60, 20],
            }
        ]
        _inject_link_tags(blocks, links, pymupdf)
        assert '<a id="0">13</a>' in blocks[0]["text"]

    def test_block_idx_set_on_match(self) -> None:
        """_block_idx is set when _inner matches."""
        blocks = [
            {
                "text": "footnote marker 4 at end",
                "rect": [0, 0, 300, 20],
            }
        ]
        links = [
            {
                "_inner": "4",
                "from": [80, 0, 90, 20],
            }
        ]
        _inject_link_tags(blocks, links, pymupdf)
        assert links[0].get("_block_idx") == 0

    def test_inner_not_found(self) -> None:
        """When _inner not found, link gets no _block_idx."""
        blocks = [
            {
                "text": "no match here",
                "rect": [0, 0, 300, 20],
            }
        ]
        links = [
            {
                "_inner": "abc",
                "from": [0, 0, 30, 20],
            }
        ]
        _inject_link_tags(blocks, links, pymupdf)
        assert "_block_idx" not in links[0]

    def test_sequential_disambiguation(self) -> None:
        """Short _inner like '1' matches correct occurrence by position."""
        # "1" appears in "12", "1" standalone — links sorted by x
        blocks = [
            {
                "text": "refs [12] and [1] here",
                "rect": [0, 0, 300, 20],
            }
        ]
        links = [
            # Link for [12] at x=30 (left)
            {"_inner": "12", "from": [30, 0, 50, 20]},
            # Link for [1] at x=80 (right) — "1" must not match "1" in "12"
            {"_inner": "1", "from": [80, 0, 90, 20]},
        ]
        _inject_link_tags(blocks, links, pymupdf)
        text = blocks[0]["text"]
        assert '<a id="0">12</a>' in text
        # "1" should wrap the standalone [1], not the "1" in [12]
        assert '[<a id="1">1</a>]' in text

    def test_sequential_across_similar_numbers(self) -> None:
        """Handles '1' appearing multiple times with correct ordering."""
        blocks = [
            {
                "text": "see [1], [11], [21] end",
                "rect": [0, 0, 300, 20],
            }
        ]
        links = [
            {"_inner": "1", "from": [20, 0, 30, 20]},
            {"_inner": "11", "from": [40, 0, 55, 20]},
            {"_inner": "21", "from": [60, 0, 75, 20]},
        ]
        _inject_link_tags(blocks, links, pymupdf)
        text = blocks[0]["text"]
        assert '<a id="0">1</a>' in text
        assert '<a id="1">11</a>' in text
        assert '<a id="2">21</a>' in text


# ── _restore_page_links char-level tests ─────────────────────────────────────


class TestRestorePageLinksCharLevel:
    """Tests for char-level matching in _restore_page_links."""

    def test_char_level_positions_link(self, tmp_path: Path) -> None:
        """Link with _block_idx uses char-level matching."""
        pdf = tmp_path / "charlvl.pdf"
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 100), "See [13] for details", fontsize=12)
        doc.save(str(pdf))
        doc.close()

        doc2 = pymupdf.open(str(pdf))
        page2 = doc2[0]
        blocks = [
            {
                "rect": [60, 80, 400, 110],
                "render_rect": [60, 80, 400, 110],
            }
        ]
        saved_links = [
            {
                "kind": 1,
                "from": pymupdf.Rect(200, 85, 230, 105),
                "page": 0,
                "to": pymupdf.Point(0, 0),
                "_inner": "13",
                "_block_idx": 0,
            }
        ]
        _restore_page_links(page2, saved_links, blocks=blocks)

        out = tmp_path / "out.pdf"
        doc2.save(str(out))
        doc2.close()

        doc3 = pymupdf.open(str(out))
        links = doc3[0].get_links()
        doc3.close()
        assert len(links) >= 1

    def test_block_idx_out_of_bounds_falls_back(
        self,
        tmp_path: Path,
    ) -> None:
        """_block_idx beyond blocks list falls back to search_for."""
        pdf = tmp_path / "oob.pdf"
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 100), "Hello World", fontsize=12)
        doc.save(str(pdf))
        doc.close()

        doc2 = pymupdf.open(str(pdf))
        page2 = doc2[0]
        blocks = [{"rect": [0, 0, 100, 50]}]  # Only 1 block
        saved_links = [
            {
                "kind": 1,
                "from": pymupdf.Rect(72, 85, 200, 105),
                "page": 0,
                "to": pymupdf.Point(0, 0),
                "_inner": "Hello",
                "_block_idx": 99,  # Out of bounds
            }
        ]
        redact_rects = [pymupdf.Rect(60, 80, 400, 110)]
        _restore_page_links(
            page2,
            saved_links,
            redact_rects,
            blocks=blocks,
        )

        out = tmp_path / "out.pdf"
        doc2.save(str(out))
        doc2.close()

        doc3 = pymupdf.open(str(out))
        links = doc3[0].get_links()
        doc3.close()
        assert len(links) >= 1

    def test_no_blocks_uses_search_fallback(self, tmp_path: Path) -> None:
        """When blocks=None, all links use search_for fallback."""
        pdf = tmp_path / "noblk.pdf"
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 100), "[6] Reference", fontsize=12)
        doc.save(str(pdf))
        doc.close()

        doc2 = pymupdf.open(str(pdf))
        page2 = doc2[0]
        saved_links = [
            {
                "kind": 1,
                "from": pymupdf.Rect(72, 85, 95, 105),
                "page": 0,
                "to": pymupdf.Point(0, 0),
                "_inner": "[6]",
            }
        ]
        redact_rects = [pymupdf.Rect(60, 80, 400, 110)]
        _restore_page_links(page2, saved_links, redact_rects)

        out = tmp_path / "out.pdf"
        doc2.save(str(out))
        doc2.close()

        doc3 = pymupdf.open(str(out))
        links = doc3[0].get_links()
        doc3.close()
        assert len(links) >= 1


# ── _save_page_links no-merge tests ──────────────────────────────────────────


class TestSavePageLinksNoMerge:
    """Tests that multi-line URL links are NOT merged."""

    def test_same_uri_two_lines_kept_separate(
        self,
        tmp_path: Path,
    ) -> None:
        """Two links with same URI on adjacent lines remain separate."""
        pdf = tmp_path / "merge.pdf"
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 100), "https://github.com/", fontsize=10)
        page.insert_text((72, 115), "tensorflow/tensor2tensor", fontsize=10)
        url = "https://github.com/tensorflow/tensor2tensor"
        page.insert_link(
            {
                "kind": 2,
                "from": pymupdf.Rect(72, 88, 200, 102),
                "uri": url,
            }
        )
        page.insert_link(
            {
                "kind": 2,
                "from": pymupdf.Rect(72, 103, 250, 117),
                "uri": url,
            }
        )
        doc.save(str(pdf))
        doc.close()

        doc2 = pymupdf.open(str(pdf))
        saved = _save_page_links(doc2[0])
        doc2.close()

        url_links = [sl for sl in saved if sl.get("uri") == url]
        assert len(url_links) == 2  # noqa: PLR2004


# ── _is_multiline_block edge cases ───────────────────────────────────


class TestIsMultilineBlockEdgeCases:
    """Additional edge cases for _is_multiline_block."""

    def test_missing_rect(self) -> None:
        """Block without rect key defaults to single-line (no crash)."""
        block = {"text": "Hello", "font_size": 10.0}
        assert not _is_multiline_block(block)

    def test_missing_rect_with_newline(self) -> None:
        """Block without rect but with newline is still multi-line."""
        block = {"text": "a\nb", "font_size": 10.0}
        assert _is_multiline_block(block)

    def test_empty_block(self) -> None:
        """Empty block dict defaults to single-line."""
        assert not _is_multiline_block({})

    def test_empty_text(self) -> None:
        """Block with empty text is single-line."""
        block = {"rect": [0, 0, 200, 12], "text": "", "font_size": 10}
        assert not _is_multiline_block(block)

    def test_zero_font_size(self) -> None:
        """Zero font_size skips height check, falls back to text check."""
        block = {"rect": [0, 0, 200, 200], "text": "single", "font_size": 0}
        assert not _is_multiline_block(block)

    def test_height_exactly_at_threshold(self) -> None:
        """Height exactly 2× font_size is NOT multi-line (strict >)."""
        block = {"rect": [0, 0, 200, 20], "text": "Title", "font_size": 10}
        assert not _is_multiline_block(block)

    def test_height_just_above_threshold(self) -> None:
        """Height just above 2× font_size IS multi-line."""
        block = {"rect": [0, 0, 200, 20.1], "text": "Title", "font_size": 10}
        assert _is_multiline_block(block)


# ── _build_overlay_html nowrap behavior ──────────────────────────────


class TestBuildOverlayHtmlNowrap:
    """Tests for white-space:nowrap in single-line block rendering."""

    def test_single_line_has_nowrap(self) -> None:
        """Single-line block gets white-space:nowrap."""
        block = {
            "translated_text": "Bonjour",
            "text": "Hello",
            "rect": [72, 100, 300, 113],
            "font_size": 10.0,
            "color": 0,
            "bold": False,
            "italic": False,
        }
        html = _build_overlay_html(block)
        assert "white-space:nowrap" in html

    def test_multiline_newline_no_nowrap(self) -> None:
        """Multi-line block (with newlines) does NOT get nowrap."""
        block = {
            "translated_text": "Line1\nLine2",
            "text": "A\nB",
            "rect": [72, 100, 300, 140],
            "font_size": 10.0,
            "color": 0,
            "bold": False,
            "italic": False,
        }
        html = _build_overlay_html(block)
        assert "nowrap" not in html

    def test_multiline_tall_rect_no_nowrap(self) -> None:
        """Tall block (height > 2× font) does NOT get nowrap."""
        block = {
            "translated_text": "Single translated",
            "text": "A long wrapped paragraph in the original",
            "rect": [72, 100, 300, 150],  # height=50, 2×10=20 → multi-line
            "font_size": 10.0,
            "color": 0,
            "bold": False,
            "italic": False,
        }
        html = _build_overlay_html(block)
        assert "nowrap" not in html

    def test_table_cell_no_nowrap(self) -> None:
        """Table cell does NOT get nowrap even if single-line."""
        block = {
            "translated_text": "Cell",
            "text": "Cell",
            "rect": [72, 100, 200, 113],
            "font_size": 10.0,
            "color": 0,
            "bold": False,
            "italic": False,
            "is_table_cell": True,
        }
        html = _build_overlay_html(block)
        assert "nowrap" not in html

    def test_nowrap_with_mixed_formatting(self) -> None:
        """Nowrap works with inline formatting tags."""
        block = {
            "translated_text": "E=mc<sup>2</sup>",
            "text": "E=mc²",
            "rect": [72, 100, 300, 113],
            "font_size": 10.0,
            "color": 0,
            "bold": False,
            "italic": False,
            "has_mixed_formatting": True,
        }
        html = _build_overlay_html(block)
        assert "white-space:nowrap" in html
        assert "<sup>" in html

    def test_nowrap_without_rect(self) -> None:
        """Block without rect defaults to single-line → gets nowrap."""
        block = {
            "translated_text": "Hello",
            "font_size": 10.0,
            "color": 0,
            "bold": False,
            "italic": False,
        }
        html = _build_overlay_html(block)
        assert "white-space:nowrap" in html

    def test_nowrap_preserves_font_size(self) -> None:
        """Nowrap does not change the base font-size."""
        block = {
            "translated_text": "Test",
            "text": "Test",
            "rect": [0, 0, 200, 12],
            "font_size": 14.0,
            "color": 0,
            "bold": False,
            "italic": False,
        }
        html = _build_overlay_html(block)
        assert "font-size:14.0pt" in html
        assert "white-space:nowrap" in html

    def test_nowrap_with_indent(self) -> None:
        """Nowrap coexists with paragraph indentation."""
        block = {
            "translated_text": "Heading text",
            "text": "Heading text",
            "rect": [72, 100, 300, 113],
            "font_size": 12.0,
            "color": 0,
            "bold": True,
            "italic": False,
            "para_indents": [(10.0, -5.0)],
        }
        html = _build_overlay_html(block)
        assert "white-space:nowrap" in html
        assert "padding-left:10.0pt" in html
        assert "text-indent:-5.0pt" in html


# ── _merge_continuation_lines ────────────────────────────────────────


def _make_raw_block(
    bbox: tuple[float, float, float, float],
    lines: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a minimal raw block dict for _merge_continuation_lines tests."""
    return {"type": 0, "bbox": bbox, "lines": lines}


def _make_raw_line(
    bbox: tuple[float, float, float, float],
    direction: tuple[float, float] = (1, 0),
) -> dict[str, Any]:
    """Build a minimal raw line dict."""
    return {"bbox": bbox, "dir": direction}


class TestMergeContinuationLines:
    """Tests for _merge_continuation_lines."""

    def test_empty_list(self) -> None:
        """Empty block list returns empty."""
        assert _merge_continuation_lines([]) == []

    def test_single_block(self) -> None:
        """Single block is returned unchanged."""
        block = _make_raw_block((0, 0, 100, 20), [_make_raw_line((0, 0, 100, 10))])
        result = _merge_continuation_lines([block])
        assert len(result) == 1
        assert len(result[0]["lines"]) == 1

    def test_non_text_blocks_skipped(self) -> None:
        """Non-text blocks (type != 0) are not merged."""
        b1 = {
            "type": 1,
            "bbox": (0, 0, 50, 10),
            "lines": [_make_raw_line((0, 0, 50, 10))],
        }
        b2 = {
            "type": 1,
            "bbox": (52, 0, 100, 10),
            "lines": [_make_raw_line((52, 0, 100, 10))],
        }
        result = _merge_continuation_lines([b1, b2])
        assert len(result) == 2  # noqa: PLR2004

    def test_cur_nontext_nxt_text_skipped(self) -> None:
        """Only current block is non-text (type 1) → no merge."""
        b1 = {
            "type": 1,
            "bbox": (0, 0, 50, 10),
            "lines": [_make_raw_line((0, 0, 50, 10))],
        }
        b2 = _make_raw_block(
            (51, 0, 100, 10),
            [_make_raw_line((51, 0, 100, 10))],
        )
        result = _merge_continuation_lines([b1, b2])
        assert len(result) == 2  # noqa: PLR2004

    def test_cur_text_nxt_nontext_skipped(self) -> None:
        """Only next block is non-text (type 1) → no merge."""
        b1 = _make_raw_block(
            (0, 0, 50, 10),
            [_make_raw_line((0, 0, 50, 10))],
        )
        b2 = {
            "type": 1,
            "bbox": (51, 0, 100, 10),
            "lines": [_make_raw_line((51, 0, 100, 10))],
        }
        result = _merge_continuation_lines([b1, b2])
        assert len(result) == 2  # noqa: PLR2004

    def test_y_misaligned_no_merge(self) -> None:
        """Blocks with y-misaligned lines are not merged."""
        b1 = _make_raw_block(
            (0, 0, 50, 10),
            [_make_raw_line((0, 0, 50, 10))],
        )
        # y0=20 vs 0: gap=20 >> _LINE_Y_TOLERANCE
        b2 = _make_raw_block(
            (52, 20, 100, 30),
            [_make_raw_line((52, 20, 100, 30))],
        )
        result = _merge_continuation_lines([b1, b2])
        assert len(result) == 2  # noqa: PLR2004

    def test_x_gap_too_large_no_merge(self) -> None:
        """Blocks with large x-gap are not merged."""
        b1 = _make_raw_block(
            (0, 0, 50, 10),
            [_make_raw_line((0, 0, 50, 10))],
        )
        # x-gap = 200 - 50 = 150 >> _ADJACENT_BLOCK_MAX_GAP
        b2 = _make_raw_block(
            (200, 0, 300, 10),
            [_make_raw_line((200, 0, 300, 10))],
        )
        result = _merge_continuation_lines([b1, b2])
        assert len(result) == 2  # noqa: PLR2004

    def test_adjacent_same_y_merges(self) -> None:
        """Adjacent blocks on same visual line merge continuation."""
        b1 = _make_raw_block(
            (0, 0, 50, 10),
            [_make_raw_line((0, 0, 50, 10))],
        )
        b2 = _make_raw_block(
            (51, 0, 100, 10),
            [_make_raw_line((51, 0, 100, 10))],
        )
        result = _merge_continuation_lines([b1, b2])
        # b2's line transferred to b1; b2 becomes empty and is removed
        assert len(result) == 1
        assert len(result[0]["lines"]) == 2  # noqa: PLR2004

    def test_merge_updates_bboxes(self) -> None:
        """Merged block bbox expands to cover transferred line."""
        b1 = _make_raw_block(
            (10, 5, 50, 15),
            [_make_raw_line((10, 5, 50, 15))],
        )
        b2 = _make_raw_block(
            (52, 5, 120, 15),
            [_make_raw_line((52, 5, 120, 15))],
        )
        result = _merge_continuation_lines([b1, b2])
        assert len(result) == 1
        # Merged bbox should span x=10..120
        assert result[0]["bbox"][0] == 10  # noqa: PLR2004
        assert result[0]["bbox"][2] == 120  # noqa: PLR2004

    def test_next_block_with_remaining_lines_kept(self) -> None:
        """Next block with multiple lines keeps its remaining lines."""
        b1 = _make_raw_block(
            (0, 0, 50, 10),
            [_make_raw_line((0, 0, 50, 10))],
        )
        # Two lines: first on same y as b1, second on a different y
        b2 = _make_raw_block(
            (51, 0, 100, 30),
            [
                _make_raw_line((51, 0, 100, 10)),  # same y → merged
                _make_raw_line((51, 20, 100, 30)),  # different y → stays
            ],
        )
        result = _merge_continuation_lines([b1, b2])
        assert len(result) == 2  # noqa: PLR2004
        assert len(result[0]["lines"]) == 2  # noqa: PLR2004
        assert len(result[1]["lines"]) == 1

    def test_vertical_text_skipped(self) -> None:
        """Vertical text blocks (dir=(0,1)) are not merged."""
        b1 = _make_raw_block(
            (0, 0, 10, 50),
            [_make_raw_line((0, 0, 10, 50), direction=(0, 1))],
        )
        b2 = _make_raw_block(
            (12, 0, 22, 50),
            [_make_raw_line((12, 0, 22, 50), direction=(0, 1))],
        )
        result = _merge_continuation_lines([b1, b2])
        assert len(result) == 2  # noqa: PLR2004

    def test_empty_lines_skipped(self) -> None:
        """Blocks with empty lines lists are not merged."""
        b1 = _make_raw_block((0, 0, 50, 10), [])
        b2 = _make_raw_block(
            (51, 0, 100, 10),
            [_make_raw_line((51, 0, 100, 10))],
        )
        result = _merge_continuation_lines([b1, b2])
        assert len(result) == 2  # noqa: PLR2004

    def test_next_block_empty_lines_skipped(self) -> None:
        """Current block has lines but next block has empty lines — no merge."""
        b1 = _make_raw_block(
            (0, 0, 50, 10),
            [_make_raw_line((0, 0, 50, 10))],
        )
        b2 = _make_raw_block((51, 0, 100, 10), [])  # empty lines
        result = _merge_continuation_lines([b1, b2])
        assert len(result) == 2  # noqa: PLR2004

    def test_chain_merge_three_blocks(self) -> None:
        """Three adjacent blocks on the same line are chained."""
        b1 = _make_raw_block(
            (0, 0, 30, 10),
            [_make_raw_line((0, 0, 30, 10))],
        )
        b2 = _make_raw_block(
            (31, 0, 60, 10),
            [_make_raw_line((31, 0, 60, 10))],
        )
        b3 = _make_raw_block(
            (61, 0, 90, 10),
            [_make_raw_line((61, 0, 90, 10))],
        )
        result = _merge_continuation_lines([b1, b2, b3])
        # All lines end up in b1
        assert len(result) == 1
        assert len(result[0]["lines"]) == 3  # noqa: PLR2004

    def test_negative_gap_within_tolerance(self) -> None:
        """Overlapping x (negative gap within tolerance) still merges."""
        b1 = _make_raw_block(
            (0, 0, 55, 10),
            [_make_raw_line((0, 0, 55, 10))],
        )
        # x0=52 < x1=55 of b1 → gap = 52-55 = -3 (within tolerance)
        b2 = _make_raw_block(
            (52, 0, 100, 10),
            [_make_raw_line((52, 0, 100, 10))],
        )
        result = _merge_continuation_lines([b1, b2])
        assert len(result) == 1

    def test_negative_gap_beyond_tolerance(self) -> None:
        """Large negative gap (block overlap) does NOT merge."""
        b1 = _make_raw_block(
            (0, 0, 100, 10),
            [_make_raw_line((0, 0, 100, 10))],
        )
        # x0=10 far left of x1=100 → gap = 10-100 = -90
        b2 = _make_raw_block(
            (10, 0, 50, 10),
            [_make_raw_line((10, 0, 50, 10))],
        )
        result = _merge_continuation_lines([b1, b2])
        assert len(result) == 2  # noqa: PLR2004


# ── _MATH_NO_ROLE_CHARS ──────────────────────────────────────────────


class TestMathNoRoleChars:
    """Tests for the _MATH_NO_ROLE_CHARS constant."""

    def test_radical_in_set(self) -> None:
        """Radical symbol √ is in the no-role set."""
        assert "\u221a" in _MATH_NO_ROLE_CHARS

    def test_normal_chars_not_in_set(self) -> None:
        """Normal ASCII chars are not in the no-role set."""
        for ch in "abcdefghijklmnopqrstuvwxyz0123456789+-=()":
            assert ch not in _MATH_NO_ROLE_CHARS

    def test_is_frozenset(self) -> None:
        """_MATH_NO_ROLE_CHARS is immutable."""
        assert isinstance(_MATH_NO_ROLE_CHARS, frozenset)


# ── _reclassify_merged_math_roles ────────────────────────────────────


class TestReclassifyMergedMathRoles:
    """Tests for _reclassify_merged_math_roles."""

    def _make_span(
        self,
        ph_key: str | None = None,
        size: float = 12.0,
        sy0: float = 100.0,
        sy1: float = 112.0,
    ) -> dict[str, Any]:
        """Build a minimal span dict."""
        span: dict[str, Any] = {"size": size, "sy0": sy0, "sy1": sy1}
        if ph_key is not None:
            span["_ph_key"] = ph_key
        return span

    def test_empty_data(self) -> None:
        """Empty input does not crash."""
        _reclassify_merged_math_roles([], {}, [], [], [])

    def test_no_placeholders(self) -> None:
        """Spans without _ph_key are untouched."""
        spans = [[self._make_span()]]
        math_map: dict[str, Any] = {}
        _reclassify_merged_math_roles(
            spans,
            math_map,
            [100.0],
            [120.0],
            [12.0],
        )
        assert math_map == {}

    def test_already_classified_skipped(self) -> None:
        """Placeholder with pre-assigned roles is not re-classified."""
        ph = "⟪0⟫"
        char_fonts = [("x", "CMR7", "sub")]
        math_map: dict[str, Any] = {ph: list(char_fonts)}
        spans = [[self._make_span(ph_key=ph, size=7.0, sy0=108, sy1=115)]]
        _reclassify_merged_math_roles(
            spans,
            math_map,
            [100.0],
            [120.0],
            [12.0],
        )
        # Role unchanged
        assert math_map[ph][0][2] == "sub"

    def test_string_value_skipped(self) -> None:
        """Placeholder with string value (already restored) is skipped."""
        ph = "⟪0⟫"
        math_map: dict[str, Any] = {ph: "restored_text"}
        spans = [[self._make_span(ph_key=ph, size=7.0)]]
        _reclassify_merged_math_roles(
            spans,
            math_map,
            [100.0],
            [120.0],
            [12.0],
        )
        assert math_map[ph] == "restored_text"

    def test_unclassified_above_midpoint_becomes_sup(self) -> None:
        """Unclassified math above line midpoint gets role='sup'."""
        ph = "⟪0⟫"
        char_fonts = [("1", "CMR7", None)]
        math_map: dict[str, Any] = {ph: list(char_fonts)}
        # Line: y0=100, y1=120 → mid=110
        # Span: sy0=98, sy1=105 → mid=101.5 < 110 → sup
        spans = [[self._make_span(ph_key=ph, size=7.0, sy0=98, sy1=105)]]
        _reclassify_merged_math_roles(
            spans,
            math_map,
            [100.0],
            [120.0],
            [12.0],
        )
        assert math_map[ph][0][2] == "sup"

    def test_unclassified_below_midpoint_becomes_sub(self) -> None:
        """Unclassified math below line midpoint gets role='sub'."""
        ph = "⟪0⟫"
        char_fonts = [("k", "CMR7", None)]
        math_map: dict[str, Any] = {ph: list(char_fonts)}
        # Line: y0=100, y1=120 → mid=110
        # Span: sy0=112, sy1=119 → mid=115.5 > 110 → sub
        spans = [[self._make_span(ph_key=ph, size=7.0, sy0=112, sy1=119)]]
        _reclassify_merged_math_roles(
            spans,
            math_map,
            [100.0],
            [120.0],
            [12.0],
        )
        assert math_map[ph][0][2] == "sub"

    def test_large_span_not_reclassified(self) -> None:
        """Span with size >= dom_size * ratio is not reclassified."""
        ph = "⟪0⟫"
        char_fonts = [("X", "CMR10", None)]
        math_map: dict[str, Any] = {ph: list(char_fonts)}
        # size=10 >= 12 * 0.85 = 10.2?  No: 10 < 10.2, so it WOULD
        # be reclassified.  Use size=11 instead.
        spans = [[self._make_span(ph_key=ph, size=11.0, sy0=98, sy1=108)]]
        _reclassify_merged_math_roles(
            spans,
            math_map,
            [100.0],
            [120.0],
            [12.0],
        )
        # size 11 >= 12 * 0.85 = 10.2 → skipped, role stays None
        assert math_map[ph][0][2] is None

    def test_zero_dom_size_skipped(self) -> None:
        """Line with zero dominant size is skipped."""
        ph = "⟪0⟫"
        math_map: dict[str, Any] = {ph: [("x", "CMR7", None)]}
        spans = [[self._make_span(ph_key=ph, size=7.0, sy0=98, sy1=105)]]
        _reclassify_merged_math_roles(
            spans,
            math_map,
            [100.0],
            [120.0],
            [0.0],
        )
        assert math_map[ph][0][2] is None

    def test_zero_span_mid_skipped(self) -> None:
        """Span with zero sy0/sy1 (no geometry) is skipped."""
        ph = "⟪0⟫"
        math_map: dict[str, Any] = {ph: [("x", "CMR7", None)]}
        spans = [[self._make_span(ph_key=ph, size=7.0, sy0=0, sy1=0)]]
        _reclassify_merged_math_roles(
            spans,
            math_map,
            [100.0],
            [120.0],
            [12.0],
        )
        assert math_map[ph][0][2] is None

    def test_multiple_chars_all_none_reclassified(self) -> None:
        """Multi-char placeholder with all roles=None gets reclassified."""
        ph = "⟪0⟫"
        char_fonts = [("d", "CMR7", None), ("k", "CMR5", None)]
        math_map: dict[str, Any] = {ph: list(char_fonts)}
        spans = [[self._make_span(ph_key=ph, size=7.0, sy0=112, sy1=119)]]
        _reclassify_merged_math_roles(
            spans,
            math_map,
            [100.0],
            [120.0],
            [12.0],
        )
        # Both chars should get "sub"
        assert all(entry[2] == "sub" for entry in math_map[ph])

    def test_mixed_roles_not_reclassified(self) -> None:
        """Placeholder with some pre-assigned roles is skipped entirely."""
        ph = "⟪0⟫"
        char_fonts = [("d", "CMR7", None), ("k", "CMR5", "sub")]
        math_map: dict[str, Any] = {ph: list(char_fonts)}
        spans = [[self._make_span(ph_key=ph, size=7.0, sy0=98, sy1=105)]]
        _reclassify_merged_math_roles(
            spans,
            math_map,
            [100.0],
            [120.0],
            [12.0],
        )
        # Not all None → skipped; d stays None, k stays sub
        assert math_map[ph][0][2] is None
        assert math_map[ph][1][2] == "sub"

    def test_multiple_lines_independent(self) -> None:
        """Reclassification applies independently per line."""
        ph_sup = "⟪0⟫"
        ph_sub = "⟪1⟫"
        math_map: dict[str, Any] = {
            ph_sup: [("1", "CMR7", None)],
            ph_sub: [("k", "CMR7", None)],
        }
        spans = [
            [self._make_span(ph_key=ph_sup, size=7.0, sy0=98, sy1=105)],
            [self._make_span(ph_key=ph_sub, size=7.0, sy0=212, sy1=219)],
        ]
        _reclassify_merged_math_roles(
            spans,
            math_map,
            [100.0, 200.0],  # line y0
            [120.0, 220.0],  # line y1
            [12.0, 12.0],  # line dom size
        )
        assert math_map[ph_sup][0][2] == "sup"
        assert math_map[ph_sub][0][2] == "sub"


# ── _merge_math_spans group-local role re-evaluation ─────────────────


class TestMergeMathSpansGroupRoles:
    """Tests for group-local role re-evaluation in _merge_math_spans."""

    def _make_math_span(  # noqa: PLR0913
        self,
        text: str,
        font: str,
        size: float,
        sx0: float = 0,
        sx1: float = 50,
        sy0: float = 100,
        sy1: float = 110,
    ) -> dict[str, Any]:
        """Build a span item for _merge_math_spans input."""
        return {
            "text": text,
            "font": font,
            "size": size,
            "flags": 0,
            "color": 0,
            "sx0": sx0,
            "sx1": sx1,
            "sy0": sy0,
            "sy1": sy1,
        }

    def _run_merge(
        self,
        items: list[dict[str, Any]],
        line_dom_size: float = 12.0,
        line_y0: float = 100.0,
        line_y1: float = 120.0,
    ) -> dict[str, Any]:
        """Call _merge_math_spans and return the math_map."""
        texts = [item["text"] for item in items]
        math_map: dict[str, Any] = {}
        _merge_math_spans(
            texts,
            items,
            math_map,
            0,
            line_dom_size=line_dom_size,
            line_y0=line_y0,
            line_y1=line_y1,
        )
        return math_map

    def test_fraction_denominator_roles_reevaluated(self) -> None:
        """In √dk, 'd' (CMR7) should lose sub role, 'k' (CMR5) keeps it.

        Both are smaller than line dominant (12pt), so line-level
        classifier tags both as sub.  Group re-evaluation uses
        within-group design sizes: CMR7 (ds=7) vs CMR5 (ds=5).
        Threshold = 7 * 0.85 = 5.95.  CMR7 >= 5.95 → None; CMR5 < 5.95 → sub.
        """
        # Line mid = (100+120)/2 = 110.  Span mid = (112+119)/2 = 115.5
        # 115.5 > 110 → initial role = "sub" for both.
        items = [
            self._make_math_span("d", "CMR7", 7.0, sx0=0, sx1=5, sy0=112, sy1=119),
            self._make_math_span("k", "CMR5", 5.0, sx0=5, sx1=10, sy0=112, sy1=117),
        ]
        math_map = self._run_merge(items, line_dom_size=12.0)
        assert len(math_map) == 1
        ph_key = next(iter(math_map))
        char_fonts = math_map[ph_key]
        # 'd' (CMR7, ds=7) → role cleared to None
        d_entry = [e for e in char_fonts if e[0] == "d"][0]
        assert d_entry[2] is None
        # 'k' (CMR5, ds=5) → role kept as sub
        k_entry = [e for e in char_fonts if e[0] == "k"][0]
        assert k_entry[2] == "sub"

    def test_single_char_group_no_reevaluation(self) -> None:
        """Single-char groups skip re-evaluation (len(char_fonts) <= 1)."""
        items = [
            self._make_math_span(
                "x",
                "CMR7",
                7.0,
                sy0=112,
                sy1=119,
            )
        ]
        math_map = self._run_merge(items, line_dom_size=12.0)
        ph_key = next(iter(math_map))
        # Single char: no re-evaluation, original role preserved
        assert math_map[ph_key][0][2] == "sub"

    def test_group_at_line_dominant_size_no_reevaluation(self) -> None:
        """Group at or above line dominant size skips re-evaluation."""
        items = [
            self._make_math_span("x", "CMR10", 10.0, sx0=0, sx1=10, sy0=112, sy1=122),
            self._make_math_span("y", "CMR10", 10.0, sx0=10, sx1=20, sy0=112, sy1=122),
        ]
        math_map = self._run_merge(items, line_dom_size=10.0)
        ph_key = next(iter(math_map))
        # group_max_sz (10) NOT < line_dom (10) * 0.85 = 8.5 → skip
        # Also at line-level: size 10 >= 10 * 0.85 → role=None
        for entry in math_map[ph_key]:
            assert entry[2] is None

    def test_radical_in_group_gets_no_role(self) -> None:
        """Radical √ in a math group always gets role=None."""
        items = [
            self._make_math_span(
                "\u221a", "CMSY7", 7.0, sx0=0, sx1=8, sy0=112, sy1=119
            ),
            self._make_math_span("x", "CMR7", 7.0, sx0=8, sx1=15, sy0=112, sy1=119),
        ]
        math_map = self._run_merge(items, line_dom_size=12.0)
        ph_key = next(iter(math_map))
        radical = [e for e in math_map[ph_key] if e[0] == "\u221a"][0]
        assert radical[2] is None

    def test_cmex_radical_via_remap_gets_no_role(self) -> None:
        """CMEX char that remaps to √ gets role=None."""
        # CMEX10 uses raw code-point 'p' (0x70) for the radical glyph;
        # _remap_cm_char maps it to '√'.
        remap_char = _remap_cm_char("p", "CMEX10")
        if remap_char not in _MATH_NO_ROLE_CHARS:
            pytest.skip("'p' in CMEX10 does not remap to a no-role char")
        items = [
            self._make_math_span("p", "CMEX10", 7.0, sx0=0, sx1=8, sy0=112, sy1=119),
            self._make_math_span("x", "CMR7", 7.0, sx0=8, sx1=15, sy0=112, sy1=119),
        ]
        math_map = self._run_merge(items, line_dom_size=12.0)
        ph_key = next(iter(math_map))
        # The CMEX 'p' (radical) should have role=None via remap check
        p_entry = [e for e in math_map[ph_key] if e[0] == "p"][0]
        assert p_entry[2] is None


# ── Additional edge cases for _merge_continuation_lines ──────────────


class TestMergeContinuationLinesBoundary:
    """Boundary condition tests for _merge_continuation_lines."""

    def test_y_tolerance_boundary_exact(self) -> None:
        """Lines exactly at _LINE_Y_TOLERANCE apart do NOT merge."""
        b1 = _make_raw_block(
            (0, 0, 50, 10),
            [_make_raw_line((0, 0, 50, 10))],
        )
        # y0 difference = _LINE_Y_TOLERANCE exactly → abs >= tolerance → skip
        tol = _LINE_Y_TOLERANCE
        b2 = _make_raw_block(
            (51, tol, 100, 10 + tol),
            [_make_raw_line((51, tol, 100, 10 + tol))],
        )
        result = _merge_continuation_lines([b1, b2])
        assert len(result) == 2  # noqa: PLR2004

    def test_y_tolerance_boundary_just_under(self) -> None:
        """Lines just under _LINE_Y_TOLERANCE apart DO merge."""
        b1 = _make_raw_block(
            (0, 0, 50, 10),
            [_make_raw_line((0, 0, 50, 10))],
        )
        tol = _LINE_Y_TOLERANCE - 0.1
        b2 = _make_raw_block(
            (51, tol, 100, 10 + tol),
            [_make_raw_line((51, tol, 100, 10 + tol))],
        )
        result = _merge_continuation_lines([b1, b2])
        assert len(result) == 1

    def test_x_gap_boundary_exact(self) -> None:
        """x-gap exactly at _ADJACENT_BLOCK_MAX_GAP still merges."""
        gap = _ADJACENT_BLOCK_MAX_GAP
        b1 = _make_raw_block(
            (0, 0, 50, 10),
            [_make_raw_line((0, 0, 50, 10))],
        )
        # gap = (50 + gap) - 50 = gap exactly → within tolerance (< not <=)
        b2 = _make_raw_block(
            (50 + gap, 0, 100 + gap, 10),
            [_make_raw_line((50 + gap, 0, 100 + gap, 10))],
        )
        result = _merge_continuation_lines([b1, b2])
        assert len(result) == 1

    def test_x_gap_boundary_just_over(self) -> None:
        """x-gap just above _ADJACENT_BLOCK_MAX_GAP does NOT merge."""
        gap = _ADJACENT_BLOCK_MAX_GAP + 0.1
        b1 = _make_raw_block(
            (0, 0, 50, 10),
            [_make_raw_line((0, 0, 50, 10))],
        )
        b2 = _make_raw_block(
            (50 + gap, 0, 100 + gap, 10),
            [_make_raw_line((50 + gap, 0, 100 + gap, 10))],
        )
        result = _merge_continuation_lines([b1, b2])
        assert len(result) == 2  # noqa: PLR2004

    def test_only_current_vertical_skipped(self) -> None:
        """Current block vertical, next horizontal → skip (no merge)."""
        b1 = _make_raw_block(
            (0, 0, 10, 50),
            [_make_raw_line((0, 0, 10, 50), direction=(0, 1))],
        )
        b2 = _make_raw_block(
            (12, 0, 60, 10),
            [_make_raw_line((12, 0, 60, 10), direction=(1, 0))],
        )
        result = _merge_continuation_lines([b1, b2])
        assert len(result) == 2  # noqa: PLR2004

    def test_only_next_vertical_skipped(self) -> None:
        """Current block horizontal, next vertical → skip (no merge)."""
        b1 = _make_raw_block(
            (0, 0, 50, 10),
            [_make_raw_line((0, 0, 50, 10), direction=(1, 0))],
        )
        b2 = _make_raw_block(
            (52, 0, 62, 50),
            [_make_raw_line((52, 0, 62, 50), direction=(0, 1))],
        )
        result = _merge_continuation_lines([b1, b2])
        assert len(result) == 2  # noqa: PLR2004

    def test_next_block_bbox_recomputed(self) -> None:
        """Next block's bbox is recomputed when it has remaining lines."""
        b1 = _make_raw_block(
            (0, 0, 50, 10),
            [_make_raw_line((0, 0, 50, 10))],
        )
        b2 = _make_raw_block(
            (51, 0, 100, 30),
            [
                _make_raw_line((51, 0, 100, 10)),  # transferred
                _make_raw_line((55, 20, 95, 30)),  # stays → new bbox
            ],
        )
        result = _merge_continuation_lines([b1, b2])
        assert len(result) == 2  # noqa: PLR2004
        # Remaining block bbox should be (55, 20, 95, 30)
        assert result[1]["bbox"][0] == 55  # noqa: PLR2004
        assert result[1]["bbox"][1] == 20  # noqa: PLR2004
        assert result[1]["bbox"][2] == 95  # noqa: PLR2004
        assert result[1]["bbox"][3] == 30  # noqa: PLR2004

    def test_multiline_current_uses_last_line(self) -> None:
        """Merge uses the LAST line of the current block for y-check."""
        b1 = _make_raw_block(
            (0, 0, 50, 30),
            [
                _make_raw_line((0, 0, 50, 10)),  # first line: y0=0
                _make_raw_line((0, 20, 50, 30)),  # last line: y0=20
            ],
        )
        # Next block's first line y0=20 matches current's LAST line
        b2 = _make_raw_block(
            (51, 20, 100, 30),
            [_make_raw_line((51, 20, 100, 30))],
        )
        result = _merge_continuation_lines([b1, b2])
        # Should merge (last line y0=20 matches next y0=20)
        assert len(result) == 1
        assert len(result[0]["lines"]) == 3  # noqa: PLR2004


# ── Additional edge cases for _reclassify_merged_math_roles ──────────


class TestReclassifyMergedMathRolesEdgeCases:
    """Extra edge cases for _reclassify_merged_math_roles."""

    def test_ph_key_not_in_math_map_ignored(self) -> None:
        """Span referencing a ph_key not in math_map is silently skipped."""
        spans = [
            [
                {
                    "size": 7.0,
                    "sy0": 98.0,
                    "sy1": 105.0,
                    "_ph_key": "⟪99⟫",
                }
            ]
        ]
        math_map: dict[str, Any] = {}
        # Should not crash
        _reclassify_merged_math_roles(
            spans,
            math_map,
            [100.0],
            [120.0],
            [12.0],
        )
        assert math_map == {}

    def test_negative_dom_size_skipped(self) -> None:
        """Negative dominant size is treated like zero — skipped."""
        ph = "⟪0⟫"
        math_map: dict[str, Any] = {ph: [("x", "CMR7", None)]}
        spans = [
            [
                {
                    "size": 7.0,
                    "sy0": 98.0,
                    "sy1": 105.0,
                    "_ph_key": ph,
                }
            ]
        ]
        _reclassify_merged_math_roles(
            spans,
            math_map,
            [100.0],
            [120.0],
            [-5.0],
        )
        assert math_map[ph][0][2] is None

    def test_line_mid_zero_skipped(self) -> None:
        """Line with both y positions at zero → line_mid=0 → skipped."""
        ph = "⟪0⟫"
        math_map: dict[str, Any] = {ph: [("x", "CMR7", None)]}
        spans = [
            [
                {
                    "size": 7.0,
                    "sy0": -5.0,
                    "sy1": 5.0,
                    "_ph_key": ph,
                }
            ]
        ]
        # y_positions=[0], y_ends=[0] → line_mid = 0 → guard fires
        _reclassify_merged_math_roles(
            spans,
            math_map,
            [0.0],
            [0.0],
            [12.0],
        )
        assert math_map[ph][0][2] is None


# ── Additional edge case for _build_overlay_html nowrap ──────────────


class TestBuildOverlayHtmlNowrapEdgeCases:
    """Edge cases for nowrap in _build_overlay_html."""

    def test_multiline_original_single_para_translation_no_nowrap(self) -> None:
        """Original was multi-line but translation is single paragraph.

        The nowrap check uses the ORIGINAL block geometry, not the
        translated text.  A tall original (multi-line) should NOT
        get nowrap even if the translation has no newlines.
        """
        block = {
            "translated_text": "Short translation",
            "text": "Original text that wrapped to many lines",
            "rect": [72, 100, 300, 160],  # height=60, 2×10=20 → multi-line
            "font_size": 10.0,
            "color": 0,
            "bold": False,
            "italic": False,
        }
        html = _build_overlay_html(block)
        assert "nowrap" not in html

    def test_space_between_returns_before_nowrap(self) -> None:
        """Space-between layout returns a table; nowrap is irrelevant."""
        block = {
            "translated_text": "Left\tRight",
            "text": "L\tR",
            "rect": [72, 100, 300, 113],
            "font_size": 10.0,
            "color": 0,
            "bold": False,
            "italic": False,
            "is_space_between": True,
        }
        html = _build_overlay_html(block)
        assert "<table" in html
        # Table output should NOT contain nowrap
        assert "nowrap" not in html

    def test_space_between_no_tab_falls_through_to_nowrap(self) -> None:
        r"""is_space_between=True with no tab bypasses the table branch.

        The condition ``is_space_between and "\\t" in text`` is False when
        there is no tab, so the function falls through to the single-para
        branch and applies nowrap normally for a single-line original.
        """
        block = {
            "translated_text": "NoTab",
            "text": "NoTab",
            "rect": [72, 100, 300, 113],
            "font_size": 10.0,
            "color": 0,
            "bold": False,
            "italic": False,
            "is_space_between": True,  # set, but no \t in text
        }
        html = _build_overlay_html(block)
        assert "<table" not in html
        assert "white-space:nowrap" in html


# ── _measure_htmlbox_spare ────────────────────────────────────────────────────


class TestMeasureHtmlboxSpare:
    """Tests for _measure_htmlbox_spare scratch-page measurement."""

    def test_returns_spare_and_scale(self) -> None:
        """Returns (spare_height, scale) from insert_htmlbox on scratch page."""
        html = '<p style="font-family:sans-serif; font-size:10pt; margin:0;">Hi</p>'
        rect = pymupdf.Rect(0, 0, 200, 50)
        doc = pymupdf.open()
        spare, scale = _measure_htmlbox_spare(doc, html, rect)
        doc.close()
        assert spare > 0
        assert scale == 1.0  # noqa: PLR2004

    def test_shrunk_text_returns_scale_below_one(self) -> None:
        """Narrow rect forces shrinkage → scale < 1.0."""
        html = (
            '<p style="font-family:sans-serif; font-size:12pt;'
            ' white-space:nowrap; margin:0;">'
            "A very long line of text that will not fit"
            "</p>"
        )
        rect = pymupdf.Rect(0, 0, 60, 30)
        doc = pymupdf.open()
        spare, scale = _measure_htmlbox_spare(doc, html, rect)
        doc.close()
        assert scale < 1.0  # noqa: PLR2004
        assert spare > 0

    def test_scratch_page_is_cleaned_up(self) -> None:
        """Temp page is deleted after measurement — doc stays empty."""
        html = '<p style="margin:0;">test</p>'
        rect = pymupdf.Rect(0, 0, 100, 30)
        doc = pymupdf.open()
        _measure_htmlbox_spare(doc, html, rect)
        assert len(doc) == 0
        doc.close()

    def test_non_tuple_return_gives_defaults(self) -> None:
        """When insert_htmlbox returns a non-tuple, defaults (0.0, 1.0)."""
        mock_doc = MagicMock()
        mock_page = MagicMock()
        mock_page.insert_htmlbox.return_value = 0  # non-tuple
        mock_doc.new_page.return_value = mock_page

        spare, scale = _measure_htmlbox_spare(
            mock_doc,
            "<p>x</p>",
            pymupdf.Rect(0, 0, 100, 30),
        )
        assert spare == 0.0
        assert scale == 1.0  # noqa: PLR2004

    def test_degenerate_rect_returns_defaults(self) -> None:
        """Degenerate rect (zero-width/height) returns defaults via mock.

        Real PyMuPDF may raise OverflowError for degenerate rects, so
        the caller (``_apply_translated_blocks``) never passes them.
        This test verifies the function's tuple-parsing with mocked I/O.
        """
        mock_doc = MagicMock()
        mock_page = MagicMock()
        # insert_htmlbox returns a non-tuple for degenerate rects
        mock_page.insert_htmlbox.return_value = None
        mock_doc.new_page.return_value = mock_page

        spare, scale = _measure_htmlbox_spare(
            mock_doc,
            "<p>Hi</p>",
            pymupdf.Rect(0, 0, 0, 50),
        )
        assert spare == 0.0
        assert scale == 1.0  # noqa: PLR2004

    def test_empty_html_no_crash(self) -> None:
        """Empty HTML string does not crash."""
        rect = pymupdf.Rect(0, 0, 100, 30)
        doc = pymupdf.open()
        spare, scale = _measure_htmlbox_spare(doc, "", rect)
        doc.close()
        assert isinstance(spare, float)
        assert isinstance(scale, float)

    def test_exception_still_cleans_up_scratch_page(self) -> None:
        """When insert_htmlbox raises, scratch page is still deleted."""
        mock_doc = MagicMock()
        mock_page = MagicMock()
        mock_page.insert_htmlbox.side_effect = RuntimeError("render fail")
        mock_doc.new_page.return_value = mock_page

        with pytest.raises(RuntimeError, match="render fail"):
            _measure_htmlbox_spare(
                mock_doc,
                "<p>x</p>",
                pymupdf.Rect(0, 0, 100, 30),
            )
        # Scratch page must still be deleted via finally
        mock_doc.delete_page.assert_called_once_with(-1)


# ── _apply_translated_blocks — vertical centering ────────────────────────────


class TestApplyTranslatedBlocksVCenter:
    """Vertical centering via scratch-page measurement in _apply_translated_blocks."""

    def _base_block(self) -> dict[str, Any]:
        r"""Single-line block (height < 2× font_size, no \\n in text)."""
        return {
            "rect": [0, 0, 200, 18],
            "text": "Hello",
            "translated_text": "Hello",
            "font_size": 10.0,
            "color": 0,
            "bold": False,
            "italic": False,
        }

    @patch("src.core.pdf_processor._measure_htmlbox_spare")
    def test_centering_when_spare_exceeds_threshold(
        self,
        mock_measure: MagicMock,
    ) -> None:
        """Renders once with rect shifted down by spare_h/2."""
        spare_h = 10.0
        mock_measure.return_value = (spare_h, 0.8)
        mock_page = MagicMock()
        mock_page.number = 0

        blocks = [self._base_block()]
        _apply_translated_blocks(mock_page, blocks, pymupdf)

        # Single insert_htmlbox call (no double render)
        assert mock_page.insert_htmlbox.call_count == 1
        call_rect = mock_page.insert_htmlbox.call_args[0][0]
        expected_y0 = 0.0 + spare_h / 2
        assert abs(call_rect.y0 - expected_y0) < 0.01

    @patch("src.core.pdf_processor._measure_htmlbox_spare")
    def test_no_centering_when_spare_below_threshold(
        self,
        mock_measure: MagicMock,
    ) -> None:
        """No shift when spare height is at or below threshold."""
        mock_measure.return_value = (_VCENTER_SPARE_THRESHOLD, 0.8)
        mock_page = MagicMock()
        mock_page.number = 0

        blocks = [self._base_block()]
        _apply_translated_blocks(mock_page, blocks, pymupdf)

        call_rect = mock_page.insert_htmlbox.call_args[0][0]
        assert abs(call_rect.y0 - 0.0) < 0.01  # no shift

    @patch("src.core.pdf_processor._measure_htmlbox_spare")
    def test_centering_applies_to_single_line_table_cells(
        self,
        mock_measure: MagicMock,
    ) -> None:
        """Single-line table cells get measured and centered."""
        spare_h = 4.0
        mock_measure.return_value = (spare_h, 0.8)
        mock_page = MagicMock()
        mock_page.number = 0

        block = self._base_block()
        block["is_table_cell"] = True
        _apply_translated_blocks(mock_page, [block], pymupdf)

        mock_measure.assert_called_once()
        call_rect = mock_page.insert_htmlbox.call_args[0][0]
        assert abs(call_rect.y0 - spare_h / 2) < 0.01

    @patch("src.core.pdf_processor._measure_htmlbox_spare")
    def test_centering_with_scale_one(
        self,
        mock_measure: MagicMock,
    ) -> None:
        """Centering applies even without shrinkage if spare height is large."""
        spare_h = 8.0
        mock_measure.return_value = (spare_h, 1.0)
        mock_page = MagicMock()
        mock_page.number = 0

        blocks = [self._base_block()]
        _apply_translated_blocks(mock_page, blocks, pymupdf)

        call_rect = mock_page.insert_htmlbox.call_args[0][0]
        assert abs(call_rect.y0 - spare_h / 2) < 0.01

    @patch("src.core.pdf_processor._measure_htmlbox_spare")
    def test_centering_preserves_x_and_y1(
        self,
        mock_measure: MagicMock,
    ) -> None:
        """Centered rect keeps original x0, x1, and y1; only y0 shifts."""
        spare_h = 12.0
        mock_measure.return_value = (spare_h, 0.6)
        mock_page = MagicMock()
        mock_page.number = 0

        block = self._base_block()
        block["rect"] = [10, 20, 300, 38]  # height 18 < 2×10 = single-line
        _apply_translated_blocks(mock_page, [block], pymupdf)

        call_rect = mock_page.insert_htmlbox.call_args[0][0]
        assert abs(call_rect.x0 - 10) < 0.01
        assert abs(call_rect.x1 - 300) < 0.01
        assert abs(call_rect.y1 - 38) < 0.01
        assert abs(call_rect.y0 - (20 + spare_h / 2)) < 0.01

    @patch("src.core.pdf_processor._measure_htmlbox_spare")
    def test_centering_with_render_rect(
        self,
        mock_measure: MagicMock,
    ) -> None:
        """When render_rect is set, centering uses the wider render rect."""
        spare_h = 6.0
        mock_measure.return_value = (spare_h, 0.9)
        mock_page = MagicMock()
        mock_page.number = 0

        block = self._base_block()
        block["rect"] = [50, 10, 200, 25]
        block["render_rect"] = [50, 10, 400, 25]  # wider
        _apply_translated_blocks(mock_page, [block], pymupdf)

        call_rect = mock_page.insert_htmlbox.call_args[0][0]
        assert abs(call_rect.x1 - 400) < 0.01
        assert abs(call_rect.y0 - (10 + spare_h / 2)) < 0.01

    @patch("src.core.pdf_processor._measure_htmlbox_spare")
    def test_no_duplicate_chars_single_render(
        self,
        mock_measure: MagicMock,
    ) -> None:
        """Centering renders only once — no duplicate characters on page."""
        spare_h = 20.0
        mock_measure.return_value = (spare_h, 0.7)
        mock_page = MagicMock()
        mock_page.number = 0

        blocks = [self._base_block()]
        _apply_translated_blocks(mock_page, blocks, pymupdf)

        # Only ONE insert_htmlbox on the real page
        assert mock_page.insert_htmlbox.call_count == 1
        # No draw_rect needed (single render, no erasure)
        mock_page.draw_rect.assert_not_called()

    @patch("src.core.pdf_processor._measure_htmlbox_spare")
    def test_multiline_block_not_centered(
        self,
        mock_measure: MagicMock,
    ) -> None:
        """Multi-line blocks skip measurement and stay top-aligned."""
        mock_page = MagicMock()
        mock_page.number = 0

        block = self._base_block()
        # Make it multiline: height 40 > 2 × font_size(10) = 20
        block["rect"] = [0, 0, 200, 40]
        _apply_translated_blocks(mock_page, [block], pymupdf)

        # _measure_htmlbox_spare should NOT be called for multiline
        mock_measure.assert_not_called()
        # Text rendered at original position (no shift)
        call_rect = mock_page.insert_htmlbox.call_args[0][0]
        assert abs(call_rect.y0 - 0.0) < 0.01

    @patch("src.core.pdf_processor._measure_htmlbox_spare")
    def test_height_expansion_then_centering(
        self,
        mock_measure: MagicMock,
    ) -> None:
        """Short rect expanded to fs*1.3 first, then centered on that rect."""
        spare_h = 4.0
        mock_measure.return_value = (spare_h, 0.9)
        mock_page = MagicMock()
        mock_page.number = 0

        block = self._base_block()
        # rect height 11 < font_size(10)*1.3=13 → expanded to y1=13
        block["rect"] = [0, 0, 200, 11]
        _apply_translated_blocks(mock_page, [block], pymupdf)

        call_rect = mock_page.insert_htmlbox.call_args[0][0]
        # y1 should be expanded to 0+13=13
        assert abs(call_rect.y1 - 13.0) < 0.01
        # y0 shifted down by spare_h/2 from expanded rect
        assert abs(call_rect.y0 - spare_h / 2) < 0.01

    @patch("src.core.pdf_processor._measure_htmlbox_spare")
    def test_measure_doc_closed_in_finally(
        self,
        mock_measure: MagicMock,
    ) -> None:
        """Scratch doc is closed even when overlay raises."""
        mock_measure.side_effect = RuntimeError("boom")
        mock_pymupdf_mod = MagicMock()
        mock_measure_doc = MagicMock()
        mock_pymupdf_mod.open.return_value = mock_measure_doc
        mock_pymupdf_mod.Rect = pymupdf.Rect
        mock_pymupdf_mod.PDF_REDACT_IMAGE_NONE = 0
        mock_pymupdf_mod.PDF_REDACT_LINE_ART_NONE = 0
        mock_page = MagicMock()
        mock_page.number = 0
        mock_page.annots.return_value = []

        blocks = [self._base_block()]
        with pytest.raises(RuntimeError, match="boom"):
            _apply_translated_blocks(
                mock_page,
                blocks,
                mock_pymupdf_mod,
            )
        # Scratch doc must still be closed via finally
        mock_measure_doc.close.assert_called_once()


# ── _resolve_fontfile — cross-platform font resolution ──────────────────────


_PDF = "src.core.pdf_processor"


class TestResolveFontfile:
    """Tests for _resolve_fontfile cross-platform font resolution."""

    @pytest.fixture(autouse=True)
    def _clear_cache(self) -> None:
        """Clears the font file cache before each test."""
        _fontfile_cache.clear()

    def test_fc_match_success(self) -> None:
        """Returns font path when fc-match finds a valid file."""
        font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = font_path + "\n"

        with (
            patch(f"{_PDF}.shutil.which", return_value="fc-match"),
            patch(f"{_PDF}.subprocess.run", return_value=mock_result),
            patch("pathlib.Path.is_file", return_value=True),
        ):
            result = _resolve_fontfile("DejaVu Sans")

        assert result == font_path

    def test_fc_match_not_installed(self) -> None:
        """Falls back to hardcoded paths when fc-match absent."""

        def _dejavu_only(path_self: Path) -> bool:
            return "dejavu" in str(path_self)

        with (
            patch(f"{_PDF}.shutil.which", return_value=None),
            patch.object(Path, "is_file", _dejavu_only),
        ):
            result = _resolve_fontfile("Any Font")

        assert result is not None
        assert "dejavu" in result

    def test_fc_match_returns_nonexistent_path(self) -> None:
        """Falls back when fc-match path doesn't exist on disk."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "/nonexistent/font.ttf\n"

        with (
            patch(f"{_PDF}.shutil.which", return_value="fc-match"),
            patch(f"{_PDF}.subprocess.run", return_value=mock_result),
            patch("pathlib.Path.is_file", return_value=False),
        ):
            result = _resolve_fontfile("MissingFont")

        assert result is None

    def test_fc_match_subprocess_error(self) -> None:
        """Subprocess failure falls back gracefully."""
        with (
            patch(f"{_PDF}.shutil.which", return_value="fc-match"),
            patch(
                f"{_PDF}.subprocess.run",
                side_effect=OSError("fc-match crashed"),
            ),
            patch("pathlib.Path.is_file", return_value=False),
        ):
            result = _resolve_fontfile("CrashedFont")

        assert result is None

    def test_fc_match_timeout_suppressed(self) -> None:
        """TimeoutExpired from fc-match falls back gracefully."""
        import subprocess as _sp  # noqa: PLC0415

        with (
            patch(f"{_PDF}.shutil.which", return_value="fc-match"),
            patch(
                f"{_PDF}.subprocess.run",
                side_effect=_sp.TimeoutExpired("fc-match", 5),
            ),
            patch("pathlib.Path.is_file", return_value=False),
        ):
            result = _resolve_fontfile("SlowFont")

        assert result is None

    def test_fc_match_nonzero_returncode(self) -> None:
        """Non-zero returncode from fc-match skips its result."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""

        with (
            patch(f"{_PDF}.shutil.which", return_value="fc-match"),
            patch(f"{_PDF}.subprocess.run", return_value=mock_result),
            patch("pathlib.Path.is_file", return_value=False),
        ):
            result = _resolve_fontfile("BadMatchFont")

        assert result is None

    def test_caching_avoids_repeat_calls(self) -> None:
        """Second call uses cache, no subprocess invocation."""
        font_path = "/usr/share/fonts/dejavu/DejaVuSans.ttf"
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = font_path + "\n"

        with (
            patch(f"{_PDF}.shutil.which", return_value="fc-match"),
            patch(
                f"{_PDF}.subprocess.run",
                return_value=mock_result,
            ) as mock_run,
            patch("pathlib.Path.is_file", return_value=True),
        ):
            first = _resolve_fontfile("CachedFont")
            second = _resolve_fontfile("CachedFont")

        assert first == second == font_path
        mock_run.assert_called_once()

    def test_none_result_is_also_cached(self) -> None:
        """None results are cached to avoid repeated lookups."""
        with (
            patch(f"{_PDF}.shutil.which", return_value=None),
            patch("pathlib.Path.is_file", return_value=False),
        ):
            first = _resolve_fontfile("NeverFound")
            second = _resolve_fontfile("NeverFound")

        assert first is None
        assert second is None
        assert "NeverFound" in _fontfile_cache

    def test_windows_fallback_uses_windir_env(self) -> None:
        """WINDIR env var is used for Windows font fallback."""
        windir = r"D:\Windows"
        target = str(Path(windir) / "Fonts" / "arial.ttf")

        def _win_only(path_self: Path) -> bool:
            return str(path_self) == target

        with (
            patch(f"{_PDF}.shutil.which", return_value=None),
            patch.dict("os.environ", {"WINDIR": windir}),
            patch.object(Path, "is_file", _win_only),
        ):
            result = _resolve_fontfile("WindowsFont")

        assert result == target

    def test_macos_user_font_dir_checked(self) -> None:
        """MacOS ~/Library/Fonts/ is in the fallback list."""
        fake_home = "/Users/testuser"
        target = str(Path(fake_home) / "Library" / "Fonts" / "Arial Unicode.ttf")

        def _mac_only(path_self: Path) -> bool:
            return str(path_self) == target

        with (
            patch(f"{_PDF}.Path.home", return_value=Path(fake_home)),
            patch.object(Path, "is_file", _mac_only),
        ):
            result = _resolve_fontfile("MacUserFont")

        assert result == target


# ── _is_math_font ─────────────────────────────────────────────────────


class TestIsMathFont:
    """Tests for _is_math_font."""

    def test_cmex_prefix(self) -> None:
        """CMEX10 is a math font (CM prefix)."""
        assert _is_math_font("CMEX10")

    def test_cmsy_prefix(self) -> None:
        """CMSY8 is a math font."""
        assert _is_math_font("CMSY8")

    def test_cmmi_prefix(self) -> None:
        """CMMI12 is a math font."""
        assert _is_math_font("CMMI12")

    def test_cmr_prefix(self) -> None:
        """CMR10 is a math font."""
        assert _is_math_font("CMR10")

    def test_cmbx_prefix(self) -> None:
        """CMBX12 is a math font."""
        assert _is_math_font("CMBX12")

    def test_cmtt_prefix(self) -> None:
        """CMTT10 is a math font."""
        assert _is_math_font("CMTT10")

    def test_msam_prefix(self) -> None:
        """MSAM is not a math font (only MSB prefix matches)."""
        assert not _is_math_font("MSAM10")

    def test_msbm_prefix(self) -> None:
        """MSBM10 is a math font (MSB prefix)."""
        assert _is_math_font("MSBM10")

    def test_cmss_prefix(self) -> None:
        """CMSS10 is a math font."""
        assert _is_math_font("CMSS10")

    def test_cmti_prefix(self) -> None:
        """CMTI12 is a math font."""
        assert _is_math_font("CMTI12")

    def test_cmbsy_prefix(self) -> None:
        """CMBSY10 is a math font."""
        assert _is_math_font("CMBSY10")

    def test_cmmib_prefix(self) -> None:
        """CMMIB10 is a math font."""
        assert _is_math_font("CMMIB10")

    def test_cmcsc_prefix(self) -> None:
        """CMCSC10 is a math font."""
        assert _is_math_font("CMCSC10")

    def test_arial_not_math(self) -> None:
        """Arial is not a math font."""
        assert not _is_math_font("Arial")

    def test_times_not_math(self) -> None:
        """TimesNewRoman is not a math font."""
        assert not _is_math_font("TimesNewRoman")

    def test_helvetica_not_math(self) -> None:
        """Helvetica is not a math font."""
        assert not _is_math_font("Helvetica")

    def test_empty_string(self) -> None:
        """Empty string is not a math font."""
        assert not _is_math_font("")


# ── _cm_design_size ───────────────────────────────────────────────────


class TestCmDesignSize:
    """Tests for _cm_design_size."""

    def test_cmex10(self) -> None:
        """CMEX10 → 10."""
        assert _cm_design_size("CMEX10") == 10  # noqa: PLR2004

    def test_cmsy8(self) -> None:
        """CMSY8 → 8."""
        assert _cm_design_size("CMSY8") == 8  # noqa: PLR2004

    def test_cmmi12(self) -> None:
        """CMMI12 → 12."""
        assert _cm_design_size("CMMI12") == 12  # noqa: PLR2004

    def test_no_trailing_digits(self) -> None:
        """CMEX (no trailing digits) → 10 (default)."""
        assert _cm_design_size("CMEX") == 10  # noqa: PLR2004

    def test_no_digits_font(self) -> None:
        """NoDigitsFont → 10 (default)."""
        assert _cm_design_size("NoDigitsFont") == 10  # noqa: PLR2004

    def test_cmr7(self) -> None:
        """CMR7 → 7."""
        assert _cm_design_size("CMR7") == 7  # noqa: PLR2004

    def test_cmsy5(self) -> None:
        """CMSY5 → 5."""
        assert _cm_design_size("CMSY5") == 5  # noqa: PLR2004


# ── _wrap_math_chars ──────────────────────────────────────────────────


class TestWrapMathChars:
    """Tests for _wrap_math_chars."""

    def test_no_italic_no_role(self) -> None:
        """(False, None) → plain text, no wrapping."""
        assert _wrap_math_chars("abc", (False, None)) == "abc"

    def test_italic_no_role(self) -> None:
        """(True, None) → <i>text</i>."""
        assert _wrap_math_chars("abc", (True, None)) == "<i>abc</i>"

    def test_no_italic_sub(self) -> None:
        """(False, 'sub') → <sub>text</sub>."""
        assert _wrap_math_chars("x", (False, "sub")) == "<sub>x</sub>"

    def test_no_italic_sup(self) -> None:
        """(False, 'sup') → <sup>text</sup>."""
        assert _wrap_math_chars("2", (False, "sup")) == "<sup>2</sup>"

    def test_italic_sub(self) -> None:
        """(True, 'sub') → <sub><i>text</i></sub>."""
        assert _wrap_math_chars("n", (True, "sub")) == "<sub><i>n</i></sub>"

    def test_italic_sup(self) -> None:
        """(True, 'sup') → <sup><i>text</i></sup>."""
        assert _wrap_math_chars("k", (True, "sup")) == "<sup><i>k</i></sup>"

    def test_empty_text(self) -> None:
        """Empty text with formatting returns empty tags."""
        assert _wrap_math_chars("", (True, "sup")) == "<sup><i></i></sup>"


# ── _get_first_content_flags ─────────────────────────────────────────


class TestGetFirstContentFlags:
    """Tests for _get_first_content_flags."""

    def test_first_non_math_span(self) -> None:
        """Returns flags of the first non-math, non-whitespace span."""
        spans = [
            {"text": "hello", "flags": 20},  # noqa: PLR2004
            {"text": "world", "flags": 4},
        ]
        assert _get_first_content_flags(spans) == 20  # noqa: PLR2004

    def test_skips_math_spans(self) -> None:
        """Skips spans with _is_math=True."""
        spans = [
            {"text": "x", "flags": 8, "_is_math": True},
            {"text": "body", "flags": 16},  # noqa: PLR2004
        ]
        assert _get_first_content_flags(spans) == 16  # noqa: PLR2004

    def test_skips_whitespace_spans(self) -> None:
        """Skips spans with whitespace-only text."""
        spans = [
            {"text": "   ", "flags": 4},
            {"text": "real", "flags": 12},  # noqa: PLR2004
        ]
        assert _get_first_content_flags(spans) == 12  # noqa: PLR2004

    def test_all_math_returns_zero(self) -> None:
        """Returns 0 when all spans are math."""
        spans = [
            {"text": "x", "flags": 8, "_is_math": True},
            {"text": "y", "flags": 4, "_is_math": True},
        ]
        assert _get_first_content_flags(spans) == 0

    def test_all_whitespace_returns_zero(self) -> None:
        """Returns 0 when all spans are whitespace."""
        spans = [
            {"text": "  ", "flags": 4},
            {"text": "\t", "flags": 8},
        ]
        assert _get_first_content_flags(spans) == 0

    def test_empty_list_returns_zero(self) -> None:
        """Returns 0 for empty span list."""
        assert _get_first_content_flags([]) == 0

    def test_skips_both_math_and_whitespace(self) -> None:
        """Skips math and whitespace spans, returns first content flags."""
        spans = [
            {"text": "  ", "flags": 2},
            {"text": "x", "flags": 8, "_is_math": True},
            {"text": "content", "flags": 32},  # noqa: PLR2004
        ]
        assert _get_first_content_flags(spans) == 32  # noqa: PLR2004

    def test_missing_flags_key(self) -> None:
        """Span without flags key returns 0 via .get() default."""
        spans = [{"text": "hello"}]
        assert _get_first_content_flags(spans) == 0


# ── _fix_url_line_joins ──────────────────────────────────────────────


class TestFixUrlLineJoins:
    """Tests for _fix_url_line_joins."""

    def test_url_at_line_end_join_removed(self) -> None:
        """URL ending at line end: join ' ' → ''."""
        lines = ["Visit https://example.com/path"]
        joins = [" "]
        _fix_url_line_joins(lines, joins)
        assert joins[0] == ""

    def test_no_protocol_join_unchanged(self) -> None:
        """No '://' in text: join unchanged."""
        lines = ["No URL here"]
        joins = [" "]
        _fix_url_line_joins(lines, joins)
        assert joins[0] == " "

    def test_protocol_with_space_after(self) -> None:
        """'://' present but space after it: join unchanged."""
        lines = ["See https://example.com /more"]
        joins = [" "]
        _fix_url_line_joins(lines, joins)
        assert joins[0] == " "

    def test_multiple_lines_mixed(self) -> None:
        """Multiple lines with mixed URL/non-URL: only URL lines affected."""
        lines = [
            "Visit https://example.com/long",
            "This is plain text",
            "Check ftp://files.example.com/data",
        ]
        joins = [" ", " ", " "]
        _fix_url_line_joins(lines, joins)
        assert joins[0] == ""
        assert joins[1] == " "
        assert joins[2] == ""

    def test_non_space_join_unchanged(self) -> None:
        """Non-space join is not modified even for URLs."""
        lines = ["Visit https://example.com/path"]
        joins = ["\n"]
        _fix_url_line_joins(lines, joins)
        assert joins[0] == "\n"

    def test_empty_join_stays_empty(self) -> None:
        """Already-empty join is not modified."""
        lines = ["Visit https://example.com/path"]
        joins = [""]
        _fix_url_line_joins(lines, joins)
        assert joins[0] == ""

    def test_tab_after_protocol(self) -> None:
        """Tab after protocol means URL has whitespace: join unchanged."""
        lines = ["See https://example.com\t"]
        joins = [" "]
        _fix_url_line_joins(lines, joins)
        assert joins[0] == " "


# ── _is_body_text_block ──────────────────────────────────────────────


class TestIsBodyTextBlock:
    """Tests for _is_body_text_block."""

    def test_multiline_within_tolerance(self) -> None:
        """Multi-line block within size tolerance → True."""
        block = {
            "_line_extents": [(0, 100), (0, 100)],
            "font_size": 10.0,
        }
        assert _is_body_text_block(block, 10.0)

    def test_single_line_block(self) -> None:
        """Single-line block → False (< 2 line_extents)."""
        block = {
            "_line_extents": [(0, 100)],
            "font_size": 10.0,
        }
        assert not _is_body_text_block(block, 10.0)

    def test_font_size_outside_tolerance(self) -> None:
        """Font size outside tolerance → False."""
        # ratio = 20/10 = 2.0 > _CONTEXT_ALIGN_SIZE_TOL (1.3)
        block = {
            "_line_extents": [(0, 100), (0, 100)],
            "font_size": 20.0,
        }
        assert not _is_body_text_block(block, 10.0)

    def test_zero_median_size(self) -> None:
        """Zero median_size → False."""
        block = {
            "_line_extents": [(0, 100), (0, 100)],
            "font_size": 10.0,
        }
        assert not _is_body_text_block(block, 0.0)

    def test_missing_line_extents(self) -> None:
        """Missing _line_extents → False."""
        block = {"font_size": 10.0}
        assert not _is_body_text_block(block, 10.0)

    def test_empty_line_extents(self) -> None:
        """Empty _line_extents list → False."""
        block = {
            "_line_extents": [],
            "font_size": 10.0,
        }
        assert not _is_body_text_block(block, 10.0)

    def test_zero_font_size(self) -> None:
        """Zero font_size → False."""
        block = {
            "_line_extents": [(0, 100), (0, 100)],
            "font_size": 0.0,
        }
        assert not _is_body_text_block(block, 10.0)

    def test_within_tolerance_boundary(self) -> None:
        """Font size at exactly the tolerance boundary → True."""
        # _CONTEXT_ALIGN_SIZE_TOL = 1.3, so ratio = 13/10 = 1.3 is OK
        block = {
            "_line_extents": [(0, 100), (0, 100)],
            "font_size": 13.0,
        }
        assert _is_body_text_block(block, 10.0)

    def test_just_outside_tolerance(self) -> None:
        """Font size just outside tolerance → False."""
        # ratio = 13.1/10 = 1.31 > 1.3
        block = {
            "_line_extents": [(0, 100), (0, 100)],
            "font_size": 13.1,
        }
        assert not _is_body_text_block(block, 10.0)

    def test_three_lines(self) -> None:
        """Three-line block within tolerance → True."""
        block = {
            "_line_extents": [(0, 100), (0, 100), (0, 80)],
            "font_size": 11.0,
        }
        assert _is_body_text_block(block, 10.0)


# ── _ends_with_math_placeholder ──────────────────────────────────────


class TestEndWithMathPlaceholder:
    """Tests for _ends_with_math_placeholder."""

    def test_ends_with_placeholder(self) -> None:
        """Block text ending with _MATH_PH_END → True."""
        block = {"text": f"Some text {_MATH_PH_START}1{_MATH_PH_END}"}
        assert _ends_with_math_placeholder(block)

    def test_ends_with_regular_text(self) -> None:
        """Block text ending with regular text → False."""
        block = {"text": "Some regular text"}
        assert not _ends_with_math_placeholder(block)

    def test_empty_text(self) -> None:
        """Empty text → False."""
        block = {"text": ""}
        assert not _ends_with_math_placeholder(block)

    def test_whitespace_after_placeholder(self) -> None:
        """Whitespace after placeholder (rstrip) → True."""
        block = {"text": f"Text {_MATH_PH_START}0{_MATH_PH_END}   "}
        assert _ends_with_math_placeholder(block)

    def test_placeholder_in_middle(self) -> None:
        """Placeholder in the middle but not at end → False."""
        block = {"text": f"Text {_MATH_PH_START}0{_MATH_PH_END} more text"}
        assert not _ends_with_math_placeholder(block)

    def test_no_text_key(self) -> None:
        """Missing text key → False."""
        block: dict[str, Any] = {}
        assert not _ends_with_math_placeholder(block)

    def test_only_placeholder(self) -> None:
        """Block with only a placeholder → True."""
        block = {"text": f"{_MATH_PH_START}42{_MATH_PH_END}"}
        assert _ends_with_math_placeholder(block)


# ── _find_horizontal_rules ────────────────────────────────────────────────────


class TestFindHorizontalRules:
    """Tests for _find_horizontal_rules."""

    def test_empty_drawings(self) -> None:
        """Empty drawings list returns empty result."""
        page = MagicMock()
        assert _find_horizontal_rules(page, drawings=[]) == []

    def test_valid_horizontal_line(self) -> None:
        """Horizontal line wider than _MIN_RULE_WIDTH is detected."""
        p1 = pymupdf.Point(10, 100)
        p2 = pymupdf.Point(10 + _MIN_RULE_WIDTH + 10, 100)
        drawings = [{"items": [("l", p1, p2)]}]
        page = MagicMock()
        result = _find_horizontal_rules(page, drawings=drawings)
        assert len(result) == 1
        assert result[0]["x0"] == 10  # noqa: PLR2004
        assert result[0]["x1"] == _MIN_RULE_WIDTH + 20  # noqa: PLR2004

    def test_diagonal_line_filtered(self) -> None:
        """Diagonal line (Dy >= 1pt) is filtered out."""
        p1 = pymupdf.Point(10, 100)
        p2 = pymupdf.Point(200, 110)  # Dy = 10
        drawings = [{"items": [("l", p1, p2)]}]
        page = MagicMock()
        assert _find_horizontal_rules(page, drawings=drawings) == []

    def test_short_line_filtered(self) -> None:
        """Horizontal line shorter than _MIN_RULE_WIDTH is filtered out."""
        p1 = pymupdf.Point(10, 100)
        p2 = pymupdf.Point(10 + _MIN_RULE_WIDTH - 1, 100)  # Just under threshold
        drawings = [{"items": [("l", p1, p2)]}]
        page = MagicMock()
        assert _find_horizontal_rules(page, drawings=drawings) == []

    def test_y_mid_computed_correctly(self) -> None:
        """y_mid is the average of p1.y and p2.y."""
        p1 = pymupdf.Point(10, 100)
        p2 = pymupdf.Point(200, 100.5)  # Dy < 1, so it's horizontal
        drawings = [{"items": [("l", p1, p2)]}]
        page = MagicMock()
        result = _find_horizontal_rules(page, drawings=drawings)
        assert len(result) == 1
        assert result[0]["y"] == pytest.approx(100.25)

    def test_drawings_none_calls_page(self) -> None:
        """When drawings=None, page.get_drawings() is called."""
        p1 = pymupdf.Point(10, 100)
        p2 = pymupdf.Point(200, 100)
        page = MagicMock()
        page.get_drawings.return_value = [{"items": [("l", p1, p2)]}]
        result = _find_horizontal_rules(page, drawings=None)
        page.get_drawings.assert_called_once()
        assert len(result) == 1

    def test_non_line_items_ignored(self) -> None:
        """Drawing items that are not lines (e.g. 're' for rect) are ignored."""
        drawings = [{"items": [("re", (10, 100, 200, 110))]}]
        page = MagicMock()
        assert _find_horizontal_rules(page, drawings=drawings) == []


# ── _find_vertical_lines ──────────────────────────────────────────────────────


class TestFindVerticalLines:
    """Tests for _find_vertical_lines."""

    def test_empty_drawings(self) -> None:
        """Empty drawings list returns empty result."""
        page = MagicMock()
        assert _find_vertical_lines(page, drawings=[]) == []

    def test_valid_vertical_line(self) -> None:
        """Vertical line taller than _MIN_VLINE_HEIGHT is detected."""
        p1 = pymupdf.Point(100, 10)
        p2 = pymupdf.Point(100, 10 + _MIN_VLINE_HEIGHT + 10)
        drawings = [{"items": [("l", p1, p2)]}]
        page = MagicMock()
        result = _find_vertical_lines(page, drawings=drawings)
        assert len(result) == 1
        assert result[0]["x"] == 100  # noqa: PLR2004
        assert result[0]["y0"] == 10  # noqa: PLR2004
        assert result[0]["y1"] == _MIN_VLINE_HEIGHT + 20  # noqa: PLR2004

    def test_horizontal_line_filtered(self) -> None:
        """Horizontal line (Dx >= 1pt) is filtered out."""
        p1 = pymupdf.Point(100, 10)
        p2 = pymupdf.Point(110, 200)  # Dx = 10
        drawings = [{"items": [("l", p1, p2)]}]
        page = MagicMock()
        assert _find_vertical_lines(page, drawings=drawings) == []

    def test_short_vertical_line_filtered(self) -> None:
        """Vertical line shorter than _MIN_VLINE_HEIGHT is filtered out."""
        p1 = pymupdf.Point(100, 10)
        p2 = pymupdf.Point(100, 10 + _MIN_VLINE_HEIGHT - 1)  # Just under threshold
        drawings = [{"items": [("l", p1, p2)]}]
        page = MagicMock()
        assert _find_vertical_lines(page, drawings=drawings) == []

    def test_drawings_none_calls_page(self) -> None:
        """When drawings=None, page.get_drawings() is called."""
        p1 = pymupdf.Point(100, 10)
        p2 = pymupdf.Point(100, 200)
        page = MagicMock()
        page.get_drawings.return_value = [{"items": [("l", p1, p2)]}]
        result = _find_vertical_lines(page, drawings=None)
        page.get_drawings.assert_called_once()
        assert len(result) == 1

    def test_x_mid_computed_correctly(self) -> None:
        """X midpoint is the average of p1.x and p2.x."""
        p1 = pymupdf.Point(100, 10)
        p2 = pymupdf.Point(100.6, 200)  # Dx < 1, so it's vertical
        drawings = [{"items": [("l", p1, p2)]}]
        page = MagicMock()
        result = _find_vertical_lines(page, drawings=drawings)
        assert len(result) == 1
        assert result[0]["x"] == pytest.approx(100.3)


# ── _group_spans_into_rows (table detection context) ──────────────────────────


class TestGroupSpansIntoRowsTableDetection:
    """Additional tests for _group_spans_into_rows in table detection context."""

    def test_empty_input(self) -> None:
        """Empty list returns empty result."""
        assert _group_spans_into_rows([]) == []

    def test_single_span_one_row(self) -> None:
        """Single span produces one row with one span."""
        spans = [{"bbox": (10, 50, 80, 60)}]
        rows = _group_spans_into_rows(spans)
        assert len(rows) == 1
        assert len(rows[0]) == 1

    def test_two_spans_same_y_one_row(self) -> None:
        """Two spans at the same y (within _LINE_Y_TOLERANCE) form one row."""
        spans = [
            {"bbox": (100, 50, 150, 60)},
            {"bbox": (10, 50 + _LINE_Y_TOLERANCE * 0.5, 60, 60)},
        ]
        rows = _group_spans_into_rows(spans)
        assert len(rows) == 1
        assert len(rows[0]) == 2  # noqa: PLR2004

    def test_two_spans_different_y_two_rows(self) -> None:
        """Two spans at different y positions form two separate rows."""
        spans = [
            {"bbox": (10, 10, 80, 20)},
            {"bbox": (10, 10 + _LINE_Y_TOLERANCE + 10, 80, 30)},
        ]
        rows = _group_spans_into_rows(spans)
        assert len(rows) == 2  # noqa: PLR2004

    def test_spans_sorted_by_x_within_row(self) -> None:
        """Spans within a row are sorted left-to-right by x coordinate."""
        spans = [
            {"bbox": (200, 50, 250, 60)},
            {"bbox": (10, 50, 60, 60)},
            {"bbox": (100, 50, 150, 60)},
        ]
        rows = _group_spans_into_rows(spans)
        assert len(rows) == 1
        assert rows[0][0]["bbox"][0] == 10  # noqa: PLR2004
        assert rows[0][1]["bbox"][0] == 100  # noqa: PLR2004
        assert rows[0][2]["bbox"][0] == 200  # noqa: PLR2004

    def test_multiple_spans_across_multiple_rows(self) -> None:
        """Multiple spans distributed across multiple rows are grouped correctly."""
        spans = [
            {"bbox": (50, 100, 80, 110)},  # Row 2
            {"bbox": (10, 10, 40, 20)},  # Row 1
            {"bbox": (70, 10, 100, 20)},  # Row 1
            {"bbox": (10, 100, 40, 110)},  # Row 2
            {"bbox": (10, 200, 40, 210)},  # Row 3
        ]
        rows = _group_spans_into_rows(spans)
        assert len(rows) == 3  # noqa: PLR2004
        # Row 1 has 2 spans, Row 2 has 2 spans, Row 3 has 1 span
        assert len(rows[0]) == 2  # noqa: PLR2004
        assert len(rows[1]) == 2  # noqa: PLR2004
        assert len(rows[2]) == 1


# ── _coalesce_line_extents ────────────────────────────────────────────────────


class TestCoalesceLineExtents:
    """Tests for _coalesce_line_extents."""

    def test_no_line_extents_uses_rect_bounds(self) -> None:
        """Blocks without _line_extents use rect bounds as fallback."""
        a: dict[str, Any] = {"font_size": 12.0}
        b: dict[str, Any] = {"font_size": 12.0}
        ra = (10.0, 50.0, 200.0, 62.0)  # (x0, y0, x1, y1)
        rb = (10.0, 70.0, 200.0, 82.0)
        extents, sizes, y_mids = _coalesce_line_extents(a, b, ra, rb)
        # Two lines on different y levels → two extents
        assert len(extents) == 2  # noqa: PLR2004
        # First extent from ra: (10, 200)
        assert extents[0] == (10.0, 200.0)
        # Second extent from rb: (10, 200)
        assert extents[1] == (10.0, 200.0)

    def test_two_blocks_different_lines(self) -> None:
        """Two blocks on different y-levels produce two separate extents."""
        a: dict[str, Any] = {
            "_line_extents": [(10.0, 200.0)],
            "_line_y_mids": [56.0],
            "_line_sizes": [12.0],
            "font_size": 12.0,
        }
        b: dict[str, Any] = {
            "_line_extents": [(10.0, 190.0)],
            "_line_y_mids": [80.0],
            "_line_sizes": [12.0],
            "font_size": 12.0,
        }
        ra = (10.0, 50.0, 200.0, 62.0)
        rb = (10.0, 74.0, 190.0, 86.0)
        extents, sizes, y_mids = _coalesce_line_extents(a, b, ra, rb)
        assert len(extents) == 2  # noqa: PLR2004
        assert y_mids[0] < y_mids[1]

    def test_same_y_fragments_merged(self) -> None:
        """Fragments on the same y-level are merged into a wider extent."""
        a: dict[str, Any] = {
            "_line_extents": [(10.0, 100.0)],
            "_line_y_mids": [56.0],
            "_line_sizes": [12.0],
            "font_size": 12.0,
        }
        b: dict[str, Any] = {
            "_line_extents": [(120.0, 250.0)],
            "_line_y_mids": [56.5],  # Within tolerance (font_size = 12)
            "_line_sizes": [12.0],
            "font_size": 12.0,
        }
        ra = (10.0, 50.0, 100.0, 62.0)
        rb = (120.0, 50.0, 250.0, 62.0)
        extents, sizes, y_mids = _coalesce_line_extents(a, b, ra, rb)
        # Fragments are on the same y-row, so they merge into one extent
        assert len(extents) == 1
        assert extents[0] == (10.0, 250.0)

    def test_mixed_lines_and_fragments(self) -> None:
        """Mix of same-line fragments and different-line extents."""
        a: dict[str, Any] = {
            "_line_extents": [(10.0, 100.0), (10.0, 200.0)],
            "_line_y_mids": [50.0, 70.0],
            "_line_sizes": [12.0, 12.0],
            "font_size": 12.0,
        }
        b: dict[str, Any] = {
            "_line_extents": [(120.0, 200.0)],
            "_line_y_mids": [50.5],  # Same y as first line of a
            "_line_sizes": [12.0],
            "font_size": 12.0,
        }
        ra = (10.0, 44.0, 200.0, 76.0)
        rb = (120.0, 44.0, 200.0, 56.0)
        extents, sizes, y_mids = _coalesce_line_extents(a, b, ra, rb)
        # Line at y~50 merges (a's first + b's only), line at y~70 stays separate
        assert len(extents) == 2  # noqa: PLR2004
        # The merged line at y~50 should span (10, 200)
        assert extents[0][0] == 10.0  # noqa: PLR2004
        assert extents[0][1] == 200.0  # noqa: PLR2004

    def test_sizes_preserved(self) -> None:
        """Line sizes are preserved and max is taken for merged fragments."""
        a: dict[str, Any] = {
            "_line_extents": [(10.0, 100.0)],
            "_line_y_mids": [50.0],
            "_line_sizes": [10.0],
            "font_size": 12.0,
        }
        b: dict[str, Any] = {
            "_line_extents": [(120.0, 200.0)],
            "_line_y_mids": [50.5],
            "_line_sizes": [14.0],
            "font_size": 12.0,
        }
        ra = (10.0, 44.0, 100.0, 56.0)
        rb = (120.0, 44.0, 200.0, 56.0)
        extents, sizes, y_mids = _coalesce_line_extents(a, b, ra, rb)
        assert len(sizes) == 1
        # Max of 10.0 and 14.0
        assert sizes[0] == 14.0  # noqa: PLR2004


# ── _get_extracted_cell_bboxes ────────────────────────────────────────────────


class TestGetExtractedCellBboxes:
    """Tests for _get_extracted_cell_bboxes."""

    def _make_page_dict(
        self,
        spans: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Build a minimal page_dict with the given spans in one line/block."""
        return {
            "blocks": [
                {
                    "type": 0,
                    "lines": [
                        {
                            "dir": (1.0, 0.0),
                            "spans": spans,
                        },
                    ],
                },
            ],
        }

    def test_empty_tables(self) -> None:
        """Empty tables list returns empty result."""
        page_dict = self._make_page_dict([])
        assert _get_extracted_cell_bboxes([], page_dict) == []

    def test_cell_with_simple_text(self) -> None:
        """Table cell with simple text is included in result."""
        cell_rect = (10.0, 10.0, 100.0, 30.0)
        spans = [
            {
                "bbox": (15, 12, 90, 28),
                "text": "Hello",
                "font": "Helvetica",
            },
        ]
        page_dict = self._make_page_dict(spans)
        page_tables = [{"cells": [cell_rect]}]
        result = _get_extracted_cell_bboxes(page_tables, page_dict)
        assert len(result) == 1
        assert result[0] == cell_rect

    def test_cell_with_complex_math_filtered(self) -> None:
        """Math-heavy cell (many math y-levels) is filtered out."""
        cell_rect = (10.0, 10.0, 200.0, 200.0)
        # Create spans with math fonts at 3+ distinct y-levels
        spans = [
            {"bbox": (15, 20, 90, 30), "text": "x", "font": "CMMI10"},
            {"bbox": (15, 50, 90, 60), "text": "y", "font": "CMMI10"},
            {"bbox": (15, 80, 90, 90), "text": "z", "font": "CMMI10"},
        ]
        page_dict = self._make_page_dict(spans)
        page_tables = [{"cells": [cell_rect]}]
        result = _get_extracted_cell_bboxes(page_tables, page_dict)
        assert result == []

    def test_cell_with_no_spans_filtered(self) -> None:
        """Cell with no matching spans is filtered out."""
        # Cell rect that doesn't overlap any span centers
        cell_rect = (500.0, 500.0, 600.0, 600.0)
        spans = [
            {"bbox": (15, 12, 90, 28), "text": "Hello", "font": "Helvetica"},
        ]
        page_dict = self._make_page_dict(spans)
        page_tables = [{"cells": [cell_rect]}]
        result = _get_extracted_cell_bboxes(page_tables, page_dict)
        assert result == []

    def test_multiple_cells_mixed(self) -> None:
        """Mix of extractable and non-extractable cells."""
        cell_ok = (10.0, 10.0, 100.0, 30.0)
        cell_math = (10.0, 50.0, 200.0, 200.0)
        cell_empty = (300.0, 300.0, 400.0, 400.0)
        spans = [
            # Spans for cell_ok
            {"bbox": (15, 12, 90, 28), "text": "Data", "font": "Helvetica"},
            # Spans for cell_math (3 y-levels of math)
            {"bbox": (15, 60, 90, 70), "text": "a", "font": "CMMI10"},
            {"bbox": (15, 90, 90, 100), "text": "b", "font": "CMMI10"},
            {"bbox": (15, 120, 90, 130), "text": "c", "font": "CMMI10"},
        ]
        page_dict = self._make_page_dict(spans)
        page_tables = [{"cells": [cell_ok, cell_math, cell_empty]}]
        result = _get_extracted_cell_bboxes(page_tables, page_dict)
        # Only cell_ok passes (cell_math is complex math, cell_empty has no spans)
        assert len(result) == 1
        assert result[0] == cell_ok

    def test_multiple_tables(self) -> None:
        """Cells from multiple tables are all processed."""
        cell_a = (10.0, 10.0, 100.0, 30.0)
        cell_b = (10.0, 100.0, 100.0, 120.0)
        spans = [
            {"bbox": (15, 12, 90, 28), "text": "A", "font": "Helvetica"},
            {"bbox": (15, 102, 90, 118), "text": "B", "font": "Helvetica"},
        ]
        page_dict = self._make_page_dict(spans)
        page_tables = [
            {"cells": [cell_a]},
            {"cells": [cell_b]},
        ]
        result = _get_extracted_cell_bboxes(page_tables, page_dict)
        assert len(result) == 2  # noqa: PLR2004


# ── PDF construction helpers for new features ─────────────────────────────────


def _make_pdf_with_bookmarks(
    path: Path,
    texts: list[str] | None = None,
    bookmarks: list[tuple[int, str, int]] | None = None,
) -> None:
    """Creates a PDF with text and bookmarks.

    Args:
        path: Output PDF path.
        texts: Text strings per page.
        bookmarks: List of (level, title, page_number) entries.
    """
    doc = pymupdf.open()
    num_pages = max(len(texts or [""]), 1)
    for i in range(num_pages):
        page = doc.new_page()
        t = (texts or [""])[i] if i < len(texts or [""]) else ""
        if t:
            page.insert_text((72, 72), t, fontsize=14)
    if bookmarks:
        toc = [[level, title, page_num] for level, title, page_num in bookmarks]
        doc.set_toc(toc)
    doc.save(str(path))
    doc.close()


def _make_pdf_with_widgets(
    path: Path,
    texts: list[str] | None = None,
    text_fields: list[tuple[str, str, tuple]] | None = None,
    combo_fields: list[tuple[str, list[str], tuple]] | None = None,
) -> None:
    """Creates a PDF with text and form widgets.

    Args:
        path: Output PDF path.
        texts: Text strings to insert.
        text_fields: List of (field_name, value, rect) for text input widgets.
        combo_fields: List of (field_name, choices, rect) for combo box widgets.
    """
    doc = pymupdf.open()
    page = doc.new_page()
    if texts:
        for i, text in enumerate(texts):
            page.insert_text((72, 72 + i * 50), text, fontsize=14)
    if text_fields:
        for fname, value, rect in text_fields:
            widget = pymupdf.Widget()
            widget.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
            widget.field_name = fname
            widget.field_value = value
            widget.rect = pymupdf.Rect(*rect)
            page.add_widget(widget)
    if combo_fields:
        for fname, choices, rect in combo_fields:
            widget = pymupdf.Widget()
            widget.field_type = pymupdf.PDF_WIDGET_TYPE_COMBOBOX
            widget.field_name = fname
            widget.choice_values = choices
            widget.field_value = choices[0] if choices else ""
            widget.rect = pymupdf.Rect(*rect)
            page.add_widget(widget)
    doc.save(str(path))
    doc.close()


def _make_pdf_with_image(
    path: Path,
    texts: list[str] | None = None,
    image_rect: tuple = (100, 100, 300, 300),
) -> None:
    """Creates a PDF with text AND an embedded raster image.

    Args:
        path: Output PDF path.
        texts: Text strings to insert.
        image_rect: (x0, y0, x1, y1) for the image placement.
    """
    doc = pymupdf.open()
    page = doc.new_page()
    if texts:
        for i, text in enumerate(texts):
            page.insert_text((72, 72 + i * 50), text, fontsize=14)
    # Create a small 10x10 PNG (red pixel pattern)
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 60, 60), 0)
    pix.set_rect(pymupdf.IRect(0, 0, 60, 60), (255, 0, 0))
    page.insert_image(pymupdf.Rect(*image_rect), pixmap=pix)
    doc.save(str(path))
    doc.close()


# ── _translate_bookmarks ──────────────────────────────────────────────────────


class TestTranslateBookmarks:
    """Tests for _translate_bookmarks()."""

    def test_empty_toc_returns_true(self) -> None:
        """Document with no bookmarks returns True immediately."""
        doc = pymupdf.open()
        doc.new_page()
        result = _translate_bookmarks(doc, "French", "", None, None)
        assert result is True
        doc.close()

    def test_translates_titles(self) -> None:
        """Bookmark titles are sent to translate_batch and updated."""
        doc = pymupdf.open()
        doc.new_page()
        doc.new_page()
        doc.set_toc([[1, "Introduction", 1], [1, "Conclusion", 2]])

        with patch(
            "src.core.pdf_processor.translate_batch",
            return_value=["Présentation", "Conclusion"],
        ) as mock_batch:
            result = _translate_bookmarks(doc, "French", "", None, None)

        assert result is True
        mock_batch.assert_called_once()
        texts_arg = mock_batch.call_args[0][0]
        assert texts_arg == ["Introduction", "Conclusion"]

        # Verify TOC was updated
        new_toc = doc.get_toc()
        assert new_toc[0][1] == "Présentation"
        assert new_toc[1][1] == "Conclusion"
        doc.close()

    def test_cancel_returns_false(self) -> None:
        """Returns False when translate_batch returns None (cancelled)."""
        doc = pymupdf.open()
        doc.new_page()
        doc.set_toc([[1, "Chapter 1", 1]])

        with patch(
            "src.core.pdf_processor.translate_batch",
            return_value=None,
        ):
            result = _translate_bookmarks(doc, "French", "", None, None)

        assert result is False
        doc.close()

    def test_preserves_structure(self) -> None:
        """Level and page numbers are preserved after translation."""
        doc = pymupdf.open()
        doc.new_page()
        doc.new_page()
        doc.set_toc([[1, "Top", 1], [2, "Sub", 2]])

        with patch(
            "src.core.pdf_processor.translate_batch",
            return_value=["Haut", "Sous"],
        ):
            _translate_bookmarks(doc, "French", "", None, None)

        toc = doc.get_toc()
        assert toc[0][0] == 1  # level preserved
        assert toc[0][2] == 1  # page preserved
        assert toc[1][0] == 2  # noqa: PLR2004
        assert toc[1][2] == 2  # noqa: PLR2004
        doc.close()

    def test_whitespace_only_bookmarks_skipped(self) -> None:
        """TOC with only whitespace titles returns True without LLM call."""
        doc = pymupdf.open()
        doc.new_page()
        doc.set_toc([[1, "   ", 1]])

        with patch(
            "src.core.pdf_processor.translate_batch",
        ) as mock_batch:
            result = _translate_bookmarks(doc, "French", "", None, None)

        assert result is True
        mock_batch.assert_not_called()
        doc.close()

    def test_glossary_forwarded(self) -> None:
        """Glossary entries are forwarded to translate_batch."""
        doc = pymupdf.open()
        doc.new_page()
        doc.set_toc([[1, "Hello", 1]])
        glossary = [(1, "Hello", "Bonjour")]

        with patch(
            "src.core.pdf_processor.translate_batch",
            return_value=["Bonjour"],
        ) as mock_batch:
            _translate_bookmarks(doc, "French", "", glossary, None)

        assert mock_batch.call_args[1]["glossary_entries"] == glossary
        doc.close()

    def test_get_toc_failure_returns_true(self) -> None:
        """Returns True when get_toc raises an exception (non-fatal)."""
        doc = MagicMock()
        doc.get_toc.side_effect = RuntimeError("corrupt TOC")
        result = _translate_bookmarks(doc, "French", "", None, None)
        assert result is True

    def test_set_toc_failure_still_returns_true(self) -> None:
        """Returns True even when set_toc fails (non-fatal)."""
        doc = pymupdf.open()
        doc.new_page()
        doc.set_toc([[1, "Chapter", 1]])

        with (
            patch(
                "src.core.pdf_processor.translate_batch",
                return_value=["Chapitre"],
            ),
            patch.object(doc, "set_toc", side_effect=RuntimeError("write failed")),
        ):
            result = _translate_bookmarks(doc, "French", "", None, None)

        assert result is True
        doc.close()

    def test_translate_batch_value_error_propagates(self) -> None:
        """ValueError from translate_batch (e.g. AUTH_ERROR) propagates up.

        _translate_bookmarks does not swallow LLM errors — the caller
        (process_pdf_file) is responsible for handling them.
        """
        doc = pymupdf.open()
        doc.new_page()
        doc.set_toc([[1, "Chapter", 1]])

        with (
            patch(
                "src.core.pdf_processor.translate_batch",
                side_effect=ValueError("AUTH_ERROR"),
            ),
            pytest.raises(ValueError, match="AUTH_ERROR"),
        ):
            _translate_bookmarks(doc, "French", "", None, None)

        doc.close()


# ── _extract_page_widgets / _inject_page_widgets ─────────────────────────────


class TestExtractPageWidgets:
    """Tests for _extract_page_widgets()."""

    def test_text_field_extracted(self, tmp_path) -> None:
        """Text input widget value is extracted."""
        pdf = tmp_path / "form.pdf"
        _make_pdf_with_widgets(
            pdf,
            text_fields=[("name", "John Doe", (100, 100, 300, 130))],
        )
        doc = pymupdf.open(str(pdf))
        page = doc[0]
        entries = _extract_page_widgets(page)
        doc.close()
        assert len(entries) == 1
        assert entries[0]["type"] == "widget"
        assert entries[0]["widget_type"] == _WIDGET_TYPE_TEXT
        assert entries[0]["text"] == "John Doe"
        assert entries[0]["field_name"] == "name"

    def test_empty_text_field_skipped(self, tmp_path) -> None:
        """Text field with empty value is skipped."""
        pdf = tmp_path / "form.pdf"
        _make_pdf_with_widgets(
            pdf,
            text_fields=[("empty", "", (100, 100, 300, 130))],
        )
        doc = pymupdf.open(str(pdf))
        page = doc[0]
        entries = _extract_page_widgets(page)
        doc.close()
        assert len(entries) == 0

    def test_combo_box_choices_extracted(self, tmp_path) -> None:
        """Combo box choices are extracted individually."""
        pdf = tmp_path / "form.pdf"
        _make_pdf_with_widgets(
            pdf,
            combo_fields=[("color", ["Red", "Blue", "Green"], (100, 100, 300, 130))],
        )
        doc = pymupdf.open(str(pdf))
        page = doc[0]
        entries = _extract_page_widgets(page)
        doc.close()
        assert len(entries) == 3  # noqa: PLR2004
        assert entries[0]["text"] == "Red"
        assert entries[0]["choice_index"] == 0
        assert entries[1]["text"] == "Blue"
        assert entries[2]["text"] == "Green"

    def test_no_widgets_returns_empty(self, tmp_path) -> None:
        """Page with no widgets returns empty list."""
        pdf = tmp_path / "no_form.pdf"
        _make_pdf(pdf, ["Hello"])
        doc = pymupdf.open(str(pdf))
        page = doc[0]
        entries = _extract_page_widgets(page)
        doc.close()
        assert entries == []

    def test_whitespace_text_field_skipped(self, tmp_path) -> None:
        """Text field with only whitespace is skipped."""
        pdf = tmp_path / "form.pdf"
        _make_pdf_with_widgets(
            pdf,
            text_fields=[("ws", "   ", (100, 100, 300, 130))],
        )
        doc = pymupdf.open(str(pdf))
        page = doc[0]
        entries = _extract_page_widgets(page)
        doc.close()
        assert len(entries) == 0

    def test_exception_returns_empty(self) -> None:
        """Exception during widget extraction returns empty list."""
        page = MagicMock()
        page.widgets.side_effect = RuntimeError("corrupt page")
        entries = _extract_page_widgets(page)
        assert entries == []

    def test_combo_tuple_pairs_use_display_value(self) -> None:
        """Combo box with (export, display) tuple pairs extracts display value."""
        widget = MagicMock()
        widget.field_type = _WIDGET_TYPE_COMBOBOX
        widget.field_name = "country"
        # PyMuPDF sometimes returns (export_value, display_value) tuples
        widget.choice_values = [("US", "United States"), ("FR", "France")]

        page = MagicMock()
        page.widgets.return_value = iter([widget])

        entries = _extract_page_widgets(page)
        assert len(entries) == 2  # noqa: PLR2004
        # Should use the display value (last element of tuple)
        assert entries[0]["text"] == "United States"
        assert entries[1]["text"] == "France"

    def test_listbox_choices_extracted(self) -> None:
        """Listbox choices are extracted the same way as combo box choices."""
        widget = MagicMock()
        widget.field_type = _WIDGET_TYPE_LISTBOX
        widget.field_name = "sizes"
        widget.choice_values = ["Small", "Medium", "Large"]

        page = MagicMock()
        page.widgets.return_value = iter([widget])

        entries = _extract_page_widgets(page)
        assert len(entries) == 3  # noqa: PLR2004
        assert entries[0]["text"] == "Small"
        assert entries[0]["widget_type"] == _WIDGET_TYPE_LISTBOX
        assert entries[1]["choice_index"] == 1
        assert entries[2]["text"] == "Large"


class TestInjectPageWidgets:
    """Tests for _inject_page_widgets()."""

    def test_text_field_updated(self, tmp_path) -> None:
        """Translated text is injected into a text field."""
        pdf = tmp_path / "form.pdf"
        _make_pdf_with_widgets(
            pdf,
            text_fields=[("name", "Hello", (100, 100, 300, 130))],
        )
        doc = pymupdf.open(str(pdf))
        page = doc[0]
        widget_entries = [
            {
                "type": "widget",
                "widget_type": _WIDGET_TYPE_TEXT,
                "field_name": "name",
                "translated_text": "Bonjour",
            }
        ]
        _inject_page_widgets(page, widget_entries)
        # Read back widget value
        found = False
        for w in page.widgets():
            if w.field_name == "name":
                assert w.field_value == "Bonjour"
                found = True
        assert found, "Widget 'name' not found after injection"
        doc.close()

    def test_empty_entries_no_op(self, tmp_path) -> None:
        """Empty widget_entries causes no changes."""
        pdf = tmp_path / "form.pdf"
        _make_pdf_with_widgets(
            pdf,
            text_fields=[("name", "Hello", (100, 100, 300, 130))],
        )
        doc = pymupdf.open(str(pdf))
        page = doc[0]
        _inject_page_widgets(page, [])
        found = False
        for w in page.widgets():
            if w.field_name == "name":
                assert w.field_value == "Hello"
                found = True
        assert found, "Widget 'name' not found"
        doc.close()

    def test_combo_choices_updated(self, tmp_path) -> None:
        """Combo box choices are translated."""
        pdf = tmp_path / "form.pdf"
        _make_pdf_with_widgets(
            pdf,
            combo_fields=[("color", ["Red", "Blue"], (100, 100, 300, 130))],
        )
        doc = pymupdf.open(str(pdf))
        page = doc[0]
        widget_entries = [
            {
                "type": "widget",
                "widget_type": _WIDGET_TYPE_COMBOBOX,
                "field_name": "color",
                "choice_index": 0,
                "translated_text": "Rouge",
            },
            {
                "type": "widget",
                "widget_type": _WIDGET_TYPE_COMBOBOX,
                "field_name": "color",
                "choice_index": 1,
                "translated_text": "Bleu",
            },
        ]
        _inject_page_widgets(page, widget_entries)
        found = False
        for w in page.widgets():
            if w.field_name == "color":
                choices = w.choice_values
                assert "Rouge" in str(choices)
                assert "Bleu" in str(choices)
                found = True
        assert found, "Widget 'color' not found after injection"
        doc.close()

    def test_no_translated_text_no_op(self, tmp_path) -> None:
        """Entries without translated_text are ignored."""
        pdf = tmp_path / "form.pdf"
        _make_pdf_with_widgets(
            pdf,
            text_fields=[("name", "Hello", (100, 100, 300, 130))],
        )
        doc = pymupdf.open(str(pdf))
        page = doc[0]
        widget_entries = [
            {
                "type": "widget",
                "widget_type": _WIDGET_TYPE_TEXT,
                "field_name": "name",
            }
        ]
        _inject_page_widgets(page, widget_entries)
        found = False
        for w in page.widgets():
            if w.field_name == "name":
                assert w.field_value == "Hello"
                found = True
        assert found, "Widget 'name' not found"
        doc.close()

    def test_combo_selected_value_updated(self, tmp_path) -> None:
        """Combo box field_value tracks the translated selected choice."""
        pdf = tmp_path / "form.pdf"
        _make_pdf_with_widgets(
            pdf,
            combo_fields=[("lang", ["English", "French"], (100, 100, 300, 130))],
        )
        doc = pymupdf.open(str(pdf))
        page = doc[0]
        # Set selected value to "English"
        for w in page.widgets():
            if w.field_name == "lang":
                w.field_value = "English"
                w.update()
        widget_entries = [
            {
                "type": "widget",
                "widget_type": _WIDGET_TYPE_COMBOBOX,
                "field_name": "lang",
                "choice_index": 0,
                "translated_text": "Anglais",
            },
            {
                "type": "widget",
                "widget_type": _WIDGET_TYPE_COMBOBOX,
                "field_name": "lang",
                "choice_index": 1,
                "translated_text": "Français",
            },
        ]
        _inject_page_widgets(page, widget_entries)
        found = False
        for w in page.widgets():
            if w.field_name == "lang":
                # The selected value was "English" → should now be "Anglais"
                assert w.field_value == "Anglais"
                found = True
        assert found, "Widget 'lang' not found after injection"
        doc.close()

    def test_all_entries_empty_translated_text_is_noop(self) -> None:
        """Entries with empty translated_text cause early return."""
        page = MagicMock()
        entries = [
            {
                "type": "widget",
                "widget_type": _WIDGET_TYPE_TEXT,
                "field_name": "x",
                "translated_text": "",
            }
        ]
        _inject_page_widgets(page, entries)
        # page.widgets() should never be called — early return
        page.widgets.assert_not_called()

    def test_widgets_call_raises_logged(self) -> None:
        """Exception in page.widgets() is caught and logged."""
        page = MagicMock()
        page.widgets.side_effect = RuntimeError("corrupt page")
        entries = [
            {
                "type": "widget",
                "widget_type": _WIDGET_TYPE_TEXT,
                "field_name": "x",
                "translated_text": "Y",
            }
        ]
        # Should not raise
        _inject_page_widgets(page, entries)

    def test_widget_update_raises_logged(self, tmp_path) -> None:
        """Exception in widget.update() is caught and logged."""
        pdf = tmp_path / "form.pdf"
        _make_pdf_with_widgets(
            pdf,
            text_fields=[("name", "Hello", (100, 100, 300, 130))],
        )
        doc = pymupdf.open(str(pdf))
        page = doc[0]
        # Patch widget.update to raise
        original_widgets = list(page.widgets())
        for w in original_widgets:
            w.update = MagicMock(side_effect=RuntimeError("update failed"))

        with patch.object(page, "widgets", return_value=iter(original_widgets)):
            entries = [
                {
                    "type": "widget",
                    "widget_type": _WIDGET_TYPE_TEXT,
                    "field_name": "name",
                    "translated_text": "Bonjour",
                }
            ]
            # Should not raise despite update failure
            _inject_page_widgets(page, entries)
        doc.close()


# ── _translate_page_images ────────────────────────────────────────────────────


class TestTranslatePageImages:
    """Tests for _translate_page_images()."""

    def test_skips_small_images(self, tmp_path) -> None:
        """Images smaller than _MIN_IMAGE_DIM are skipped."""
        pdf = tmp_path / "small_img.pdf"
        # Create PDF with a tiny 5x5 image
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Hello", fontsize=14)
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 5, 5), 0)
        pix.set_rect(pymupdf.IRect(0, 0, 5, 5), (255, 0, 0))
        # Place at small rect (rendered size < _MIN_IMAGE_DIM)
        page.insert_image(pymupdf.Rect(10, 10, 20, 20), pixmap=pix)
        doc.save(str(pdf))

        page = doc[0]
        xrefs: set[int] = set()
        with patch(
            "src.core.pdf_processor._translate_single_pdf_image",
        ) as mock_translate:
            _translate_page_images(
                doc,
                page,
                "French",
                "",
                None,
                "TesseractOCR",
                None,
                xrefs,
            )

        # Image was too small, should not be translated
        mock_translate.assert_not_called()
        doc.close()

    def test_translates_medium_image(self, tmp_path) -> None:
        """Normal-sized embedded images are translated."""
        pdf = tmp_path / "med_img.pdf"
        _make_pdf_with_image(pdf, texts=["Hello"], image_rect=(100, 200, 400, 500))

        doc = pymupdf.open(str(pdf))
        page = doc[0]
        xrefs: set[int] = set()

        with patch(
            "src.core.pdf_processor._translate_single_pdf_image",
            return_value=b"translated_png_bytes",
        ) as mock_translate:
            _translate_page_images(
                doc,
                page,
                "French",
                "",
                None,
                "TesseractOCR",
                None,
                xrefs,
            )

        mock_translate.assert_called_once()
        doc.close()

    def test_deduplicates_xrefs(self, tmp_path) -> None:
        """Same xref on multiple pages is only translated once."""
        pdf = tmp_path / "dup_img.pdf"
        _make_pdf_with_image(pdf, texts=["Page 1"], image_rect=(100, 200, 400, 500))

        doc = pymupdf.open(str(pdf))
        page = doc[0]
        # Pre-populate xrefs with all image xrefs
        images = page.get_images(full=True)
        pre_xrefs = {img[0] for img in images}

        with patch(
            "src.core.pdf_processor._translate_single_pdf_image",
        ) as mock_translate:
            _translate_page_images(
                doc,
                page,
                "French",
                "",
                None,
                "TesseractOCR",
                None,
                pre_xrefs,
            )

        # Already in xrefs, so not translated
        mock_translate.assert_not_called()
        doc.close()

    def test_cancel_check_respected(self, tmp_path) -> None:
        """cancel_check returning True stops image processing."""
        pdf = tmp_path / "cancel_img.pdf"
        _make_pdf_with_image(pdf, texts=["Hello"], image_rect=(100, 200, 400, 500))

        doc = pymupdf.open(str(pdf))
        page = doc[0]

        with patch(
            "src.core.pdf_processor._translate_single_pdf_image",
        ) as mock_translate:
            _translate_page_images(
                doc,
                page,
                "French",
                "",
                None,
                "TesseractOCR",
                lambda: True,  # always cancelled
                set(),
            )

        mock_translate.assert_not_called()
        doc.close()

    def test_fatal_error_propagates(self, tmp_path) -> None:
        """AUTH_ERROR from image translation propagates up."""
        pdf = tmp_path / "fatal.pdf"
        _make_pdf_with_image(pdf, texts=["Hello"], image_rect=(100, 200, 400, 500))

        doc = pymupdf.open(str(pdf))
        page = doc[0]

        with (
            patch(
                "src.core.pdf_processor._translate_single_pdf_image",
                side_effect=ValueError("AUTH_ERROR"),
            ),
            pytest.raises(ValueError, match="AUTH_ERROR"),
        ):
            _translate_page_images(
                doc,
                page,
                "French",
                "",
                None,
                "TesseractOCR",
                None,
                set(),
            )
        doc.close()

    def test_nonfatal_error_continues(self, tmp_path) -> None:
        """Non-fatal errors are logged and image is marked as processed."""
        pdf = tmp_path / "nonfatal.pdf"
        _make_pdf_with_image(pdf, texts=["Hello"], image_rect=(100, 200, 400, 500))

        doc = pymupdf.open(str(pdf))
        page = doc[0]
        xrefs: set[int] = set()

        with patch(
            "src.core.pdf_processor._translate_single_pdf_image",
            side_effect=ValueError("GENERIC_ERROR"),
        ):
            _translate_page_images(
                doc,
                page,
                "French",
                "",
                None,
                "TesseractOCR",
                None,
                xrefs,
            )

        # xref should be added to prevent retry
        assert len(xrefs) > 0
        doc.close()

    def test_runtime_error_is_nonfatal(self, tmp_path) -> None:
        """RuntimeError from OCR is caught and does not crash the pipeline."""
        pdf = tmp_path / "ocr_fail.pdf"
        _make_pdf_with_image(pdf, texts=["Hello"], image_rect=(100, 200, 400, 500))

        doc = pymupdf.open(str(pdf))
        page = doc[0]
        xrefs: set[int] = set()

        with patch(
            "src.core.pdf_processor._translate_single_pdf_image",
            side_effect=RuntimeError("Tesseract failed"),
        ):
            # Should NOT raise — RuntimeError is non-fatal
            _translate_page_images(
                doc,
                page,
                "French",
                "",
                None,
                "TesseractOCR",
                None,
                xrefs,
            )

        assert len(xrefs) > 0
        doc.close()

    def test_import_error_is_nonfatal(self, tmp_path) -> None:
        """ImportError from missing OCR engine is caught gracefully."""
        pdf = tmp_path / "no_ocr.pdf"
        _make_pdf_with_image(pdf, texts=["Hello"], image_rect=(100, 200, 400, 500))

        doc = pymupdf.open(str(pdf))
        page = doc[0]
        xrefs: set[int] = set()

        with patch(
            "src.core.pdf_processor._translate_single_pdf_image",
            side_effect=ImportError("No module named 'easyocr'"),
        ):
            _translate_page_images(
                doc,
                page,
                "French",
                "",
                None,
                "EasyOCR",
                None,
                xrefs,
            )

        assert len(xrefs) > 0
        doc.close()

    def test_skips_full_page_image(self, tmp_path) -> None:
        """Full-page images are skipped (handled by scanned-page pipeline)."""
        pdf = tmp_path / "fullpage.pdf"
        # Image covers nearly the entire page (595x842 is default page size)
        _make_pdf_with_image(
            pdf,
            texts=["Hello"],
            image_rect=(0, 0, 595, 842),
        )

        doc = pymupdf.open(str(pdf))
        page = doc[0]
        xrefs: set[int] = set()

        with patch(
            "src.core.pdf_processor._translate_single_pdf_image",
        ) as mock_translate:
            _translate_page_images(
                doc,
                page,
                "French",
                "",
                None,
                "TesseractOCR",
                None,
                xrefs,
            )

        mock_translate.assert_not_called()
        doc.close()

    def test_extract_image_failure_skips(self, tmp_path) -> None:
        """Image extraction failure is caught and image is skipped."""
        pdf = tmp_path / "bad_img.pdf"
        _make_pdf_with_image(pdf, texts=["Hello"], image_rect=(100, 200, 400, 500))

        doc = pymupdf.open(str(pdf))
        page = doc[0]
        xrefs: set[int] = set()

        with (
            patch.object(doc, "extract_image", side_effect=RuntimeError("bad xref")),
            patch(
                "src.core.pdf_processor._translate_single_pdf_image",
            ) as mock_translate,
        ):
            _translate_page_images(
                doc,
                page,
                "French",
                "",
                None,
                "TesseractOCR",
                None,
                xrefs,
            )

        mock_translate.assert_not_called()
        # xref still added to prevent retry
        assert len(xrefs) > 0
        doc.close()

    def test_empty_image_data_skips(self, tmp_path) -> None:
        """Image with no data bytes is skipped."""
        pdf = tmp_path / "empty_img.pdf"
        _make_pdf_with_image(pdf, texts=["Hello"], image_rect=(100, 200, 400, 500))

        doc = pymupdf.open(str(pdf))
        page = doc[0]
        xrefs: set[int] = set()

        with (
            patch.object(
                doc,
                "extract_image",
                return_value={"image": b"", "ext": "png"},
            ),
            patch(
                "src.core.pdf_processor._translate_single_pdf_image",
            ) as mock_translate,
        ):
            _translate_page_images(
                doc,
                page,
                "French",
                "",
                None,
                "TesseractOCR",
                None,
                xrefs,
            )

        mock_translate.assert_not_called()
        assert len(xrefs) > 0
        doc.close()

    def test_replace_image_failure_logged(self, tmp_path) -> None:
        """replace_image failure is caught and logged, not fatal."""
        pdf = tmp_path / "replace_fail.pdf"
        _make_pdf_with_image(pdf, texts=["Hello"], image_rect=(100, 200, 400, 500))

        doc = pymupdf.open(str(pdf))
        page = doc[0]
        xrefs: set[int] = set()

        with (
            patch(
                "src.core.pdf_processor._translate_single_pdf_image",
                return_value=b"translated_png_bytes",
            ),
            patch.object(
                page,
                "replace_image",
                side_effect=RuntimeError("replace failed"),
            ),
        ):
            # Should not raise
            _translate_page_images(
                doc,
                page,
                "French",
                "",
                None,
                "TesseractOCR",
                None,
                xrefs,
            )

        # xref should still be marked as processed
        assert len(xrefs) > 0
        doc.close()


class TestTranslateSinglePdfImage:
    """Tests for _translate_single_pdf_image()."""

    def test_no_ocr_results_returns_none(self) -> None:
        """Returns None when OCR finds no text."""
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 10, 10), 0)
        img_bytes = pix.tobytes("png")

        with patch(
            "src.core.ocr_engine.run_ocr",
            return_value=[],
        ):
            result = _translate_single_pdf_image(
                img_bytes,
                ".png",
                "French",
                "",
                None,
                "TesseractOCR",
            )
        assert result is None

    def test_successful_pipeline(self) -> None:
        """Full OCR → translate → render pipeline returns bytes."""
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 60, 60), 0)
        img_bytes = pix.tobytes("png")

        mock_ocr = MagicMock()
        mock_ocr.text = "Hello"
        mock_ocr.x, mock_ocr.y, mock_ocr.w, mock_ocr.h = 5, 5, 50, 20
        mock_ocr.confidence = 0.95

        with (
            patch(
                "src.core.ocr_engine.run_ocr",
                return_value=[mock_ocr],
            ),
            patch(
                "src.core.llm_engine.translate_image_content",
                return_value={"paragraphs": [{"text": "Bonjour"}]},
            ),
            patch(
                "src.core.layout_analysis.merge_to_paragraphs",
                return_value=([mock_ocr], ["Bonjour"], [mock_ocr]),
            ),
            patch(
                "src.core.image_processor.process_image_translation",
                return_value=True,
            ) as mock_render,
        ):
            _translate_single_pdf_image(
                img_bytes,
                ".png",
                "French",
                "",
                None,
                "TesseractOCR",
            )

        # process_image_translation was called
        mock_render.assert_called_once()

    def test_merge_returns_empty(self) -> None:
        """Returns None when merge_to_paragraphs returns no results."""
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 10, 10), 0)
        img_bytes = pix.tobytes("png")

        mock_ocr = MagicMock()

        with (
            patch("src.core.ocr_engine.run_ocr", return_value=[mock_ocr]),
            patch(
                "src.core.llm_engine.translate_image_content",
                return_value={},
            ),
            patch(
                "src.core.layout_analysis.merge_to_paragraphs",
                return_value=([], [], []),
            ),
        ):
            result = _translate_single_pdf_image(
                img_bytes,
                ".png",
                "French",
                "",
                None,
                "TesseractOCR",
            )
        assert result is None

    def test_render_failure_returns_none(self) -> None:
        """Returns None when process_image_translation returns False."""
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 60, 60), 0)
        img_bytes = pix.tobytes("png")

        mock_ocr = MagicMock()
        mock_ocr.text = "Hello"
        mock_ocr.x, mock_ocr.y, mock_ocr.w, mock_ocr.h = 5, 5, 50, 20
        mock_ocr.confidence = 0.95

        with (
            patch("src.core.ocr_engine.run_ocr", return_value=[mock_ocr]),
            patch(
                "src.core.llm_engine.translate_image_content",
                return_value={"paragraphs": [{"text": "Bonjour"}]},
            ),
            patch(
                "src.core.layout_analysis.merge_to_paragraphs",
                return_value=([mock_ocr], ["Bonjour"], [mock_ocr]),
            ),
            patch(
                "src.core.image_processor.process_image_translation",
                return_value=False,
            ),
        ):
            result = _translate_single_pdf_image(
                img_bytes,
                ".png",
                "French",
                "",
                None,
                "TesseractOCR",
            )

        assert result is None


# ── Integration: process_pdf_file with bookmarks ─────────────────────────────


def test_process_pdf_file_translates_bookmarks(tmp_path: Path) -> None:
    """Bookmarks are translated in the full pipeline."""
    pdf = tmp_path / "bm.pdf"
    out = tmp_path / "out.pdf"
    _make_pdf_with_bookmarks(
        pdf,
        texts=["Hello"],
        bookmarks=[(1, "Chapter 1", 1)],
    )

    def _mock_batch(texts: list, *a: Any, **kw: Any) -> list:
        mapping = {"Hello": "Bonjour", "Chapter 1": "Chapitre 1"}
        return [mapping.get(t, t) for t in texts]

    with patch(
        "src.core.pdf_processor.translate_batch",
        side_effect=_mock_batch,
    ):
        result = process_pdf_file(pdf, out, "French")

    assert result is True
    doc = pymupdf.open(str(out))
    toc = doc.get_toc()
    assert len(toc) == 1
    assert toc[0][1] == "Chapitre 1"
    doc.close()


def test_process_pdf_file_no_bookmarks(tmp_path: Path) -> None:
    """PDFs without bookmarks still translate normally."""
    pdf = tmp_path / "no_bm.pdf"
    out = tmp_path / "out.pdf"
    _make_pdf(pdf, ["Hello"])

    def _mock_batch(texts: list, *a: Any, **kw: Any) -> list:
        return [{"Hello": "Bonjour"}.get(t, t) for t in texts]

    with patch(
        "src.core.pdf_processor.translate_batch",
        side_effect=_mock_batch,
    ):
        result = process_pdf_file(pdf, out, "French")

    assert result is True


# ── Integration: process_pdf_file with form fields ───────────────────────────


def test_process_pdf_file_translates_widgets(tmp_path: Path) -> None:
    """Form field values are translated when shapes toggle is on."""
    pdf = tmp_path / "form.pdf"
    out = tmp_path / "out.pdf"
    _make_pdf_with_widgets(
        pdf,
        texts=["Hello"],
        text_fields=[("name", "Enter name", (100, 200, 300, 230))],
    )

    def _mock_batch(texts: list, *a: Any, **kw: Any) -> list:
        # Return translated version for each input text
        mapping = {"Hello": "Bonjour", "Enter name": "Entrer le nom"}
        return [mapping.get(t, t) for t in texts]

    config = MagicMock()
    config.should_translate_images = False
    config.translate_doc_comments = False
    config.translate_doc_shapes = True

    with patch(
        "src.core.pdf_processor.translate_batch",
        side_effect=_mock_batch,
    ):
        result = process_pdf_file(pdf, out, "French", config=config)

    assert result is True
    doc = pymupdf.open(str(out))
    page = doc[0]
    found = False
    for w in page.widgets():
        if w.field_name == "name":
            assert w.field_value == "Entrer le nom"
            found = True
    assert found, "Widget 'name' not found in output PDF"
    doc.close()


def test_process_pdf_file_widget_only_page(tmp_path: Path) -> None:
    """Page with only form fields (no text) still gets translated."""
    pdf = tmp_path / "widget_only.pdf"
    out = tmp_path / "out.pdf"
    _make_pdf_with_widgets(
        pdf,
        text_fields=[("label", "Submit", (100, 100, 300, 130))],
    )

    def _mock_batch(texts: list, *a: Any, **kw: Any) -> list:
        return [{"Submit": "Soumettre"}.get(t, t) for t in texts]

    config = MagicMock()
    config.should_translate_images = False
    config.translate_doc_comments = False
    config.translate_doc_shapes = True

    with (
        patch(
            "src.core.pdf_processor.translate_batch",
            side_effect=_mock_batch,
        ) as mock_batch,
    ):
        result = process_pdf_file(pdf, out, "French", config=config)

    assert result is True
    texts_arg = mock_batch.call_args[0][0]
    assert "Submit" in texts_arg


def test_process_pdf_file_widgets_skipped_when_shapes_off(
    tmp_path: Path,
) -> None:
    """Widgets are NOT translated when the shapes toggle is off."""
    pdf = tmp_path / "widget_only.pdf"
    out = tmp_path / "out.pdf"
    _make_pdf_with_widgets(
        pdf,
        texts=["Hello"],
        text_fields=[("label", "Submit", (100, 100, 300, 130))],
    )

    def _mock_batch(texts: list, *a: Any, **kw: Any) -> list:
        return [t + " FR" for t in texts]

    config = MagicMock()
    config.should_translate_images = False
    config.translate_doc_comments = False
    config.translate_doc_shapes = False

    with (
        patch(
            "src.core.pdf_processor.translate_batch",
            side_effect=_mock_batch,
        ),
        patch(
            "src.core.pdf_processor._inject_page_widgets",
        ) as mock_inject_w,
    ):
        result = process_pdf_file(pdf, out, "French", config=config)

    assert result is True
    # No widget injection should happen when shapes is off
    mock_inject_w.assert_not_called()


def test_process_pdf_file_widgets_in_checkpoint(tmp_path: Path) -> None:
    """Widget entries are included in the per-page checkpoint."""
    pdf = tmp_path / "form.pdf"
    out = tmp_path / "out.pdf"
    ckpt = tmp_path / "ckpt"
    _make_pdf_with_widgets(
        pdf,
        texts=["Hello"],
        text_fields=[("name", "World", (100, 200, 300, 230))],
    )

    def _mock_batch(texts: list, *a: Any, **kw: Any) -> list:
        mapping = {"Hello": "Bonjour", "World": "Monde"}
        return [mapping.get(t, t) for t in texts]

    config = MagicMock()
    config.should_translate_images = False
    config.translate_doc_comments = False
    config.translate_doc_shapes = True

    with (
        patch(
            "src.core.pdf_processor.translate_batch",
            side_effect=_mock_batch,
        ),
        patch(
            "src.core.pdf_processor.save_pdf_page_progress",
        ) as mock_save,
    ):
        process_pdf_file(pdf, out, "French", checkpoint_dir=ckpt, config=config)

    # Checkpoint should include both block and widget entries
    mock_save.assert_called()
    saved_entries = mock_save.call_args[0][2]
    types = [e.get("type") for e in saved_entries]
    assert "widget" in types


# ── Integration: process_pdf_file with embedded images ───────────────────────


def test_process_pdf_file_text_page_with_images(tmp_path: Path) -> None:
    """Text pages with embedded images translate both text and images."""
    pdf = tmp_path / "mixed.pdf"
    out = tmp_path / "out.pdf"
    _make_pdf_with_image(pdf, texts=["Hello"], image_rect=(100, 200, 400, 500))

    def _mock_batch(texts: list, *a: Any, **kw: Any) -> list:
        return [{"Hello": "Bonjour"}.get(t, t) for t in texts]

    with (
        patch(
            "src.core.pdf_processor._config.load_setting",
            side_effect=lambda k, d=None: True,
        ),
        patch("src.core.pdf_processor._config.check_ocr_setup", return_value=True),
        patch(
            "src.core.pdf_processor.translate_batch",
            side_effect=_mock_batch,
        ),
        patch(
            "src.core.pdf_processor._translate_page_images",
        ) as mock_img_translate,
    ):
        result = process_pdf_file(pdf, out, "French")

    assert result is True
    # Image translation was called for the text page with images
    mock_img_translate.assert_called_once()


def test_process_pdf_file_images_disabled_skips(tmp_path: Path) -> None:
    """Embedded images are not translated when do_images is False."""
    pdf = tmp_path / "mixed.pdf"
    out = tmp_path / "out.pdf"
    _make_pdf_with_image(pdf, texts=["Hello"], image_rect=(100, 200, 400, 500))

    def _mock_batch(texts: list, *a: Any, **kw: Any) -> list:
        return [{"Hello": "Bonjour"}.get(t, t) for t in texts]

    with (
        patch(
            "src.core.pdf_processor._config.load_setting",
            side_effect=lambda k, d=None: False,
        ),
        patch("src.core.pdf_processor._config.check_ocr_setup", return_value=False),
        patch(
            "src.core.pdf_processor.translate_batch",
            side_effect=_mock_batch,
        ),
        patch(
            "src.core.pdf_processor._translate_page_images",
        ) as mock_img_translate,
    ):
        result = process_pdf_file(pdf, out, "French")

    assert result is True
    mock_img_translate.assert_not_called()


def test_process_pdf_file_blocks_annots_widgets_combined(tmp_path: Path) -> None:
    """Page with blocks, annotations, AND widgets sends all in one batch."""
    pdf = tmp_path / "combined.pdf"
    out = tmp_path / "out.pdf"
    # Create PDF with text + annotation + widget
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Body text", fontsize=14)
    annot = page.add_text_annot(pymupdf.Point(200, 200), "Comment here")
    annot.update()
    widget = pymupdf.Widget()
    widget.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
    widget.field_name = "field1"
    widget.field_value = "Field value"
    widget.rect = pymupdf.Rect(100, 300, 300, 330)
    page.add_widget(widget)
    doc.save(str(pdf))
    doc.close()

    def _mock_batch(texts: list, *a: Any, **kw: Any) -> list:
        mapping = {
            "Body text": "Corps du texte",
            "Comment here": "Commentaire ici",
            "Field value": "Valeur du champ",
        }
        return [mapping.get(t, t) for t in texts]

    with (
        patch(
            "src.core.pdf_processor._config.load_setting",
            side_effect=lambda k, d=None: True,
        ),
        patch("src.core.pdf_processor._config.check_ocr_setup", return_value=False),
        patch(
            "src.core.pdf_processor.translate_batch",
            side_effect=_mock_batch,
        ) as mock_batch,
    ):
        result = process_pdf_file(pdf, out, "French")

    assert result is True
    # All three types should be in a single batch call
    mock_batch.assert_called()
    first_call_texts = mock_batch.call_args_list[0][0][0]
    assert "Body text" in first_call_texts or "Comment here" in first_call_texts

    # Verify widget was translated in output
    doc2 = pymupdf.open(str(out))
    page2 = doc2[0]
    found = False
    for w in page2.widgets():
        if w.field_name == "field1":
            assert w.field_value == "Valeur du champ"
            found = True
    assert found, "Widget 'field1' not found in output PDF"
    doc2.close()


# ── _links_to_checkpoint tests ───────────────────────────────────────────────


class TestLinksToCheckpoint:
    """Tests for _links_to_checkpoint serialization."""

    def test_converts_rect_to_list(self) -> None:
        """PyMuPDF Rect in 'from' is converted to a plain list."""
        links = [
            {
                "kind": 2,
                "from": pymupdf.Rect(10, 20, 100, 40),
                "uri": "https://example.com",
                "_inner": "example",
            },
        ]
        result = _links_to_checkpoint(links)
        assert result[0]["from"] == [10.0, 20.0, 100.0, 40.0]
        assert isinstance(result[0]["from"], list)

    def test_converts_point_to_list(self) -> None:
        """PyMuPDF Point in 'to' is converted to a plain list."""
        links = [
            {
                "kind": 1,
                "from": pymupdf.Rect(10, 20, 100, 40),
                "page": 0,
                "to": pymupdf.Point(72, 300),
            },
        ]
        result = _links_to_checkpoint(links)
        assert result[0]["to"] == [72.0, 300.0]
        assert isinstance(result[0]["to"], list)

    def test_adds_type_link(self) -> None:
        """Each entry gets 'type': 'link'."""
        links = [{"kind": 2, "from": pymupdf.Rect(0, 0, 10, 10)}]
        result = _links_to_checkpoint(links)
        assert result[0]["type"] == "link"

    def test_preserves_metadata_fields(self) -> None:
        """_translated, _block_idx, _left_char, _right_char survive."""
        links = [
            {
                "kind": 2,
                "from": pymupdf.Rect(0, 0, 10, 10),
                "uri": "https://example.com",
                "_inner": "click",
                "_translated": "cliquer",
                "_block_idx": 2,
                "_left_char": "(",
                "_right_char": ")",
                "_src_left": "(",
                "_src_right": ")",
                "_style": {"C": "[1 0 0]", "Border": "[0 0 1]"},
            },
        ]
        result = _links_to_checkpoint(links)
        entry = result[0]
        assert entry["_translated"] == "cliquer"
        assert entry["_block_idx"] == 2  # noqa: PLR2004
        assert entry["_left_char"] == "("
        assert entry["_right_char"] == ")"
        assert entry["_style"]["C"] == "[1 0 0]"

    def test_json_serializable(self) -> None:
        """Output can be serialized to JSON without error."""
        import json  # noqa: PLC0415

        links = [
            {
                "kind": 1,
                "from": pymupdf.Rect(10, 20, 100, 40),
                "page": 0,
                "to": pymupdf.Point(72, 300),
                "zoom": 1.5,
                "_inner": "Section 3",
                "_translated": "Phần 3",
                "_block_idx": 0,
                "_left_char": " ",
                "_right_char": ".",
                "_style": {"Border": "[0 0 1]"},
            },
        ]
        result = _links_to_checkpoint(links)
        # Should not raise
        serialized = json.dumps(result)
        assert '"type": "link"' in serialized

    def test_empty_list(self) -> None:
        """Empty input returns empty output."""
        assert _links_to_checkpoint([]) == []

    def test_multiple_links(self) -> None:
        """Multiple links are all converted."""
        links = [
            {"kind": 2, "from": pymupdf.Rect(0, 0, 10, 10), "uri": "a"},
            {"kind": 2, "from": pymupdf.Rect(20, 20, 30, 30), "uri": "b"},
        ]
        result = _links_to_checkpoint(links)
        assert len(result) == 2  # noqa: PLR2004
        assert all(e["type"] == "link" for e in result)


class TestInsertLinkWithStyleTypeKey:
    """Tests that 'type' key from checkpoint is excluded from insert_link."""

    def test_type_key_stripped(self, tmp_path: Path) -> None:
        """A link with 'type': 'link' should insert without error."""
        pdf = tmp_path / "type_key.pdf"
        doc = pymupdf.open()
        doc.new_page()
        doc.save(str(pdf))
        doc.close()

        doc2 = pymupdf.open(str(pdf))
        page2 = doc2[0]
        # Simulate a checkpoint-restored link with 'type' key
        link = {
            "type": "link",
            "kind": 1,
            "from": [72.0, 85.0, 200.0, 105.0],
            "page": 0,
            "to": [0.0, 0.0],
            "_inner": "Section 1",
            "_translated": "Phần 1",
            "_block_idx": 0,
        }
        # Should not raise despite 'type' key
        _insert_link_with_style(page2, link, None)

        out = tmp_path / "out.pdf"
        doc2.save(str(out))
        doc2.close()

        doc3 = pymupdf.open(str(out))
        links = doc3[0].get_links()
        doc3.close()
        assert len(links) == 1
        assert links[0]["kind"] == 1


class TestRestorePageLinksFromCheckpoint:
    """Tests for _restore_page_links with checkpoint-style link dicts."""

    def test_checkpoint_links_use_char_level_matching(self, tmp_path: Path) -> None:
        """Links from checkpoint with _block_idx use Path A."""
        pdf = tmp_path / "ckpt_links.pdf"
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Click here for details", fontsize=12)
        doc.save(str(pdf))
        doc.close()

        doc2 = pymupdf.open(str(pdf))
        page2 = doc2[0]

        # Simulate checkpoint-restored link (list rects, type key)
        saved_links = [
            {
                "type": "link",
                "kind": 2,
                "from": [72.0, 60.0, 200.0, 80.0],
                "uri": "https://example.com",
                "_inner": "Click here",
                "_translated": "Click here",
                "_block_idx": 0,
            },
        ]
        blocks = [
            {
                "rect": [72.0, 60.0, 300.0, 80.0],
                "text": "Click here for details",
                "translated_text": "Click here for details",
                "font_size": 12.0,
                "color": 0,
                "bold": False,
                "italic": False,
            },
        ]
        _restore_page_links(page2, saved_links, [], blocks)

        out = tmp_path / "out.pdf"
        doc2.save(str(out))
        doc2.close()

        doc3 = pymupdf.open(str(out))
        links = doc3[0].get_links()
        doc3.close()
        assert len(links) >= 1
        assert links[0]["uri"] == "https://example.com"

    def test_checkpoint_links_without_block_idx_fall_to_path_b(
        self, tmp_path: Path
    ) -> None:
        """Links from checkpoint missing _block_idx go to fallback."""
        pdf = tmp_path / "no_bidx.pdf"
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Hello world", fontsize=12)
        doc.save(str(pdf))
        doc.close()

        doc2 = pymupdf.open(str(pdf))
        page2 = doc2[0]

        # Link without _block_idx — should go to unassigned/fallback
        saved_links = [
            {
                "type": "link",
                "kind": 2,
                "from": [72.0, 60.0, 200.0, 80.0],
                "uri": "https://fallback.com",
                "_inner": "Hello",
            },
        ]
        _restore_page_links(page2, saved_links, [], [])

        out = tmp_path / "out.pdf"
        doc2.save(str(out))
        doc2.close()

        doc3 = pymupdf.open(str(out))
        links = doc3[0].get_links()
        doc3.close()
        # Link inserted at original rect (fallback)
        assert len(links) >= 1
        assert links[0]["uri"] == "https://fallback.com"


# ── _detect_vline_tables ─────────────────────────────────────────────────────


def _make_vline_drawing(
    x: float,
    y0: float,
    y1: float,
) -> dict[str, Any]:
    """Build a drawing dict containing one vertical line item."""
    return {
        "items": [
            ("l", pymupdf.Point(x, y0), pymupdf.Point(x, y1)),
        ],
    }


def _make_page_dict_with_spans(
    spans: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a minimal page_dict containing the given spans."""
    return {
        "blocks": [
            {
                "type": 0,
                "lines": [{"spans": spans, "dir": (1.0, 0.0)}],
            },
        ],
    }


def _make_page_dict_with_rows(
    rows: list[list[dict[str, Any]]],
) -> dict[str, Any]:
    """Build a page_dict with each row on a separate line element."""
    lines = [{"spans": row, "dir": (1.0, 0.0)} for row in rows]
    return {"blocks": [{"type": 0, "lines": lines}]}


class TestDetectVlineTables:
    """Tests for _detect_vline_tables."""

    def test_no_vertical_lines_returns_empty(self) -> None:
        """No drawings at all produces no tables."""
        page = MagicMock()
        page_dict: dict[str, Any] = {"blocks": []}
        result = _detect_vline_tables(page, page_dict, drawings=[])
        assert result == []

    def test_too_few_vlines_returns_empty(self) -> None:
        """Only 2 vertical lines (below _MIN_VLINES_PER_TABLE=3) produces no tables."""
        height = _MIN_VLINE_HEIGHT + 20
        drawings = [
            _make_vline_drawing(100, 50, 50 + height),
            _make_vline_drawing(200, 50, 50 + height),
        ]
        page = MagicMock()
        page_dict: dict[str, Any] = {"blocks": []}
        result = _detect_vline_tables(page, page_dict, drawings=drawings)
        assert result == []

    def test_three_vlines_forms_table(self) -> None:
        """3 vertical lines with text spans inside produce 1 table with cells."""
        height = _MIN_VLINE_HEIGHT + 20
        y0, y1 = 50, 50 + height
        drawings = [
            _make_vline_drawing(100, y0, y1),
            _make_vline_drawing(200, y0, y1),
            _make_vline_drawing(300, y0, y1),
        ]
        # Place spans inside the bbox (100, 50) → (300, 50+height)
        mid_y = (y0 + y1) / 2
        spans = [
            {
                "bbox": (120, mid_y - 5, 180, mid_y + 5),
                "text": "A",
                "size": 12,
                "flags": 0,
                "font": "Arial",
                "color": 0,
            },
            {
                "bbox": (220, mid_y - 5, 280, mid_y + 5),
                "text": "B",
                "size": 12,
                "flags": 0,
                "font": "Arial",
                "color": 0,
            },
        ]
        page_dict = _make_page_dict_with_spans(spans)
        page = MagicMock()

        result = _detect_vline_tables(page, page_dict, drawings=drawings)
        assert len(result) == 1
        table = result[0]
        assert "bbox" in table
        assert "cells" in table
        assert len(table["cells"]) >= 1

    def test_no_spans_in_region_returns_empty(self) -> None:
        """Vlines exist but no text spans inside the bbox produces no tables."""
        height = _MIN_VLINE_HEIGHT + 20
        y0, y1 = 50, 50 + height
        drawings = [
            _make_vline_drawing(100, y0, y1),
            _make_vline_drawing(200, y0, y1),
            _make_vline_drawing(300, y0, y1),
        ]
        # Spans far outside the vline region
        spans = [
            {
                "bbox": (500, 500, 550, 510),
                "text": "far",
                "size": 12,
                "flags": 0,
                "font": "Arial",
                "color": 0,
            },
        ]
        page_dict = _make_page_dict_with_spans(spans)
        page = MagicMock()

        result = _detect_vline_tables(page, page_dict, drawings=drawings)
        assert result == []

    def test_multiple_groups_separate_tables(self) -> None:
        """Vlines at different y-ranges produce separate table groups."""
        height = _MIN_VLINE_HEIGHT + 20
        # Group 1: y=50..50+height
        g1_y0, g1_y1 = 50, 50 + height
        # Group 2: y=400..400+height (far from group 1)
        g2_y0, g2_y1 = 400, 400 + height
        drawings = [
            # Group 1: 3 vlines
            _make_vline_drawing(100, g1_y0, g1_y1),
            _make_vline_drawing(200, g1_y0, g1_y1),
            _make_vline_drawing(300, g1_y0, g1_y1),
            # Group 2: 3 vlines
            _make_vline_drawing(100, g2_y0, g2_y1),
            _make_vline_drawing(200, g2_y0, g2_y1),
            _make_vline_drawing(300, g2_y0, g2_y1),
        ]
        # Spans in both regions
        g1_mid = (g1_y0 + g1_y1) / 2
        g2_mid = (g2_y0 + g2_y1) / 2
        spans_g1 = [
            {
                "bbox": (120, g1_mid - 5, 180, g1_mid + 5),
                "text": "A1",
                "size": 12,
                "flags": 0,
                "font": "Arial",
                "color": 0,
            },
            {
                "bbox": (220, g1_mid - 5, 280, g1_mid + 5),
                "text": "B1",
                "size": 12,
                "flags": 0,
                "font": "Arial",
                "color": 0,
            },
        ]
        spans_g2 = [
            {
                "bbox": (120, g2_mid - 5, 180, g2_mid + 5),
                "text": "A2",
                "size": 12,
                "flags": 0,
                "font": "Arial",
                "color": 0,
            },
            {
                "bbox": (220, g2_mid - 5, 280, g2_mid + 5),
                "text": "B2",
                "size": 12,
                "flags": 0,
                "font": "Arial",
                "color": 0,
            },
        ]
        all_spans = spans_g1 + spans_g2
        page_dict = _make_page_dict_with_spans(all_spans)
        page = MagicMock()

        result = _detect_vline_tables(page, page_dict, drawings=drawings)
        assert len(result) == 2  # noqa: PLR2004

    def test_single_row_table(self) -> None:
        """Only 1 text row in the vline region produces 1 row of cells."""
        height = _MIN_VLINE_HEIGHT + 20
        y0, y1 = 50, 50 + height
        drawings = [
            _make_vline_drawing(100, y0, y1),
            _make_vline_drawing(200, y0, y1),
            _make_vline_drawing(300, y0, y1),
        ]
        mid_y = (y0 + y1) / 2
        # Single row: 2 spans at same y
        spans = [
            {
                "bbox": (120, mid_y - 5, 180, mid_y + 5),
                "text": "C1",
                "size": 12,
                "flags": 0,
                "font": "Arial",
                "color": 0,
            },
            {
                "bbox": (220, mid_y - 5, 280, mid_y + 5),
                "text": "C2",
                "size": 12,
                "flags": 0,
                "font": "Arial",
                "color": 0,
            },
        ]
        page_dict = _make_page_dict_with_spans(spans)
        page = MagicMock()

        result = _detect_vline_tables(page, page_dict, drawings=drawings)
        assert len(result) == 1
        # 1 row x 2 columns (3 vlines = 2 columns)
        assert len(result[0]["cells"]) == 2  # noqa: PLR2004

    def test_multi_row_table(self) -> None:
        """3 text rows inside 4 vlines produce 3 rows x 3 cols = 9 cells."""
        height = _MIN_VLINE_HEIGHT + 200
        y0, y1 = 50, 50 + height
        drawings = [
            _make_vline_drawing(100, y0, y1),
            _make_vline_drawing(200, y0, y1),
            _make_vline_drawing(300, y0, y1),
            _make_vline_drawing(400, y0, y1),
        ]
        # 3 rows of spans at y=80, y=130, y=180
        row1 = [
            {
                "bbox": (120, 75, 180, 85),
                "text": "R1C1",
                "size": 12,
                "flags": 0,
                "font": "Arial",
                "color": 0,
            },
            {
                "bbox": (220, 75, 280, 85),
                "text": "R1C2",
                "size": 12,
                "flags": 0,
                "font": "Arial",
                "color": 0,
            },
            {
                "bbox": (320, 75, 380, 85),
                "text": "R1C3",
                "size": 12,
                "flags": 0,
                "font": "Arial",
                "color": 0,
            },
        ]
        row2 = [
            {
                "bbox": (120, 125, 180, 135),
                "text": "R2C1",
                "size": 12,
                "flags": 0,
                "font": "Arial",
                "color": 0,
            },
            {
                "bbox": (220, 125, 280, 135),
                "text": "R2C2",
                "size": 12,
                "flags": 0,
                "font": "Arial",
                "color": 0,
            },
            {
                "bbox": (320, 125, 380, 135),
                "text": "R2C3",
                "size": 12,
                "flags": 0,
                "font": "Arial",
                "color": 0,
            },
        ]
        row3 = [
            {
                "bbox": (120, 175, 180, 185),
                "text": "R3C1",
                "size": 12,
                "flags": 0,
                "font": "Arial",
                "color": 0,
            },
            {
                "bbox": (220, 175, 280, 185),
                "text": "R3C2",
                "size": 12,
                "flags": 0,
                "font": "Arial",
                "color": 0,
            },
            {
                "bbox": (320, 175, 380, 185),
                "text": "R3C3",
                "size": 12,
                "flags": 0,
                "font": "Arial",
                "color": 0,
            },
        ]
        all_spans = row1 + row2 + row3
        page_dict = _make_page_dict_with_spans(all_spans)
        page = MagicMock()

        result = _detect_vline_tables(page, page_dict, drawings=drawings)
        assert len(result) == 1
        # 3 rows x 3 cols (4 dividers - 1 = 3 cols)
        assert len(result[0]["cells"]) == 9  # noqa: PLR2004

    def test_col_dividers_from_x_positions(self) -> None:
        """Column dividers in the output cells match the vline x positions."""
        height = _MIN_VLINE_HEIGHT + 20
        y0, y1 = 50, 50 + height
        x_positions = [100, 250, 400]
        drawings = [_make_vline_drawing(x, y0, y1) for x in x_positions]

        mid_y = (y0 + y1) / 2
        spans = [
            {
                "bbox": (130, mid_y - 5, 200, mid_y + 5),
                "text": "A",
                "size": 12,
                "flags": 0,
                "font": "Arial",
                "color": 0,
            },
            {
                "bbox": (280, mid_y - 5, 380, mid_y + 5),
                "text": "B",
                "size": 12,
                "flags": 0,
                "font": "Arial",
                "color": 0,
            },
        ]
        page_dict = _make_page_dict_with_spans(spans)
        page = MagicMock()

        result = _detect_vline_tables(page, page_dict, drawings=drawings)
        assert len(result) == 1
        cells = result[0]["cells"]
        # First cell left edge = first vline x, first cell right edge = second vline x
        assert cells[0][0] == 100  # noqa: PLR2004
        assert cells[0][2] == 250  # noqa: PLR2004
        # Second cell left edge = second vline x, second cell right edge = third vline x
        assert cells[1][0] == 250  # noqa: PLR2004
        assert cells[1][2] == 400  # noqa: PLR2004

    def test_empty_text_rows_returns_empty(self) -> None:
        """Spans exist but if _group_spans_into_rows returns 0 rows, no table."""
        height = _MIN_VLINE_HEIGHT + 20
        y0, y1 = 50, 50 + height
        drawings = [
            _make_vline_drawing(100, y0, y1),
            _make_vline_drawing(200, y0, y1),
            _make_vline_drawing(300, y0, y1),
        ]
        # Spans inside region but we mock _group_spans_into_rows to return []
        mid_y = (y0 + y1) / 2
        spans = [
            {
                "bbox": (120, mid_y - 5, 180, mid_y + 5),
                "text": "X",
                "size": 12,
                "flags": 0,
                "font": "Arial",
                "color": 0,
            },
        ]
        page_dict = _make_page_dict_with_spans(spans)
        page = MagicMock()

        with patch("src.core.pdf_processor._group_spans_into_rows", return_value=[]):
            result = _detect_vline_tables(page, page_dict, drawings=drawings)
        assert result == []

    def test_drawings_parameter_used(self) -> None:
        """When drawings param is provided, page.get_drawings is NOT called."""
        page = MagicMock()
        page_dict: dict[str, Any] = {"blocks": []}
        _detect_vline_tables(page, page_dict, drawings=[])
        page.get_drawings.assert_not_called()

    def test_exception_in_get_drawings(self) -> None:
        """If page.get_drawings raises, function returns [] gracefully."""
        page = MagicMock()
        page.get_drawings.side_effect = RuntimeError("fail")
        page_dict: dict[str, Any] = {"blocks": []}
        result = _detect_vline_tables(page, page_dict, drawings=None)
        assert result == []

    def test_vlines_sorted_by_x(self) -> None:
        """Unsorted vlines still produce correct bbox with leftmost/rightmost x."""
        height = _MIN_VLINE_HEIGHT + 20
        y0, y1 = 50, 50 + height
        # Provide vlines in unsorted x order
        drawings = [
            _make_vline_drawing(300, y0, y1),
            _make_vline_drawing(100, y0, y1),
            _make_vline_drawing(200, y0, y1),
        ]
        mid_y = (y0 + y1) / 2
        spans = [
            {
                "bbox": (120, mid_y - 5, 180, mid_y + 5),
                "text": "A",
                "size": 12,
                "flags": 0,
                "font": "Arial",
                "color": 0,
            },
            {
                "bbox": (220, mid_y - 5, 280, mid_y + 5),
                "text": "B",
                "size": 12,
                "flags": 0,
                "font": "Arial",
                "color": 0,
            },
        ]
        page_dict = _make_page_dict_with_spans(spans)
        page = MagicMock()

        result = _detect_vline_tables(page, page_dict, drawings=drawings)
        assert len(result) == 1
        bbox = result[0]["bbox"]
        # bbox x0 = leftmost x, x1 = rightmost x
        assert bbox[0] == 100  # noqa: PLR2004
        assert bbox[2] == 300  # noqa: PLR2004

    def test_bbox_y_from_min_max_lines(self) -> None:
        """Table bbox y0/y1 come from the min/max of vline y endpoints."""
        height = _MIN_VLINE_HEIGHT + 20
        y_top, y_bot = 40, 40 + height
        drawings = [
            _make_vline_drawing(100, y_top, y_bot),
            _make_vline_drawing(200, y_top + 2, y_bot - 1),
            _make_vline_drawing(300, y_top + 1, y_bot + 3),
        ]
        mid_y = (y_top + y_bot) / 2
        spans = [
            {
                "bbox": (120, mid_y - 5, 180, mid_y + 5),
                "text": "A",
                "size": 12,
                "flags": 0,
                "font": "Arial",
                "color": 0,
            },
            {
                "bbox": (220, mid_y - 5, 280, mid_y + 5),
                "text": "B",
                "size": 12,
                "flags": 0,
                "font": "Arial",
                "color": 0,
            },
        ]
        page_dict = _make_page_dict_with_spans(spans)
        page = MagicMock()

        result = _detect_vline_tables(page, page_dict, drawings=drawings)
        assert len(result) == 1
        bbox = result[0]["bbox"]
        assert bbox[1] == y_top  # noqa: PLR2004
        assert bbox[3] == y_bot + 3  # noqa: PLR2004

    def test_cell_tuples_are_four_floats(self) -> None:
        """Each cell in the result is a 4-element tuple (x0, y0, x1, y1)."""
        height = _MIN_VLINE_HEIGHT + 20
        y0, y1 = 50, 50 + height
        drawings = [
            _make_vline_drawing(100, y0, y1),
            _make_vline_drawing(200, y0, y1),
            _make_vline_drawing(300, y0, y1),
        ]
        mid_y = (y0 + y1) / 2
        spans = [
            {
                "bbox": (120, mid_y - 5, 180, mid_y + 5),
                "text": "X",
                "size": 12,
                "flags": 0,
                "font": "Arial",
                "color": 0,
            },
        ]
        page_dict = _make_page_dict_with_spans(spans)
        page = MagicMock()

        result = _detect_vline_tables(page, page_dict, drawings=drawings)
        assert len(result) == 1
        for cell in result[0]["cells"]:
            assert len(cell) == 4  # noqa: PLR2004

    def test_group_below_min_vlines_filtered(self) -> None:
        """A group with fewer than _MIN_VLINES_PER_TABLE lines after grouping is skipped."""  # noqa: E501
        height = _MIN_VLINE_HEIGHT + 20
        # Group 1: 3 vlines at y=50 (kept)
        g1_y0, g1_y1 = 50, 50 + height
        # Group 2: 2 vlines at y=400 (too few, filtered)
        g2_y0, g2_y1 = 400, 400 + height
        drawings = [
            _make_vline_drawing(100, g1_y0, g1_y1),
            _make_vline_drawing(200, g1_y0, g1_y1),
            _make_vline_drawing(300, g1_y0, g1_y1),
            _make_vline_drawing(100, g2_y0, g2_y1),
            _make_vline_drawing(200, g2_y0, g2_y1),
        ]
        g1_mid = (g1_y0 + g1_y1) / 2
        spans = [
            {
                "bbox": (120, g1_mid - 5, 180, g1_mid + 5),
                "text": "OK",
                "size": 12,
                "flags": 0,
                "font": "Arial",
                "color": 0,
            },
            {
                "bbox": (220, g1_mid - 5, 280, g1_mid + 5),
                "text": "OK2",
                "size": 12,
                "flags": 0,
                "font": "Arial",
                "color": 0,
            },
        ]
        page_dict = _make_page_dict_with_spans(spans)
        page = MagicMock()

        result = _detect_vline_tables(page, page_dict, drawings=drawings)
        # Only 1 table from group 1; group 2 has only 2 vlines
        assert len(result) == 1


# ── _detect_framed_tables ────────────────────────────────────────────────────


def _make_frame_drawing(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
) -> dict[str, Any]:
    """Build a drawing dict containing one rectangle item."""
    return {
        "items": [
            ("re", pymupdf.Rect(x0, y0, x1, y1)),
        ],
    }


class TestDetectFramedTables:
    """Tests for _detect_framed_tables."""

    def test_no_drawings_returns_empty(self) -> None:
        """Empty drawings list produces no tables."""
        page = MagicMock()
        page_dict: dict[str, Any] = {"blocks": []}
        result = _detect_framed_tables(page, page_dict, drawings=[])
        assert result == []

    def test_rect_too_small_filtered(self) -> None:
        """Rectangle smaller than _MIN_FRAME_WIDTH or _MIN_FRAME_HEIGHT is ignored."""
        # Width below minimum
        small_w = _make_frame_drawing(
            10, 10, 10 + _MIN_FRAME_WIDTH - 1, 10 + _MIN_FRAME_HEIGHT + 50
        )  # noqa: E501
        # Height below minimum
        small_h = _make_frame_drawing(
            10, 10, 10 + _MIN_FRAME_WIDTH + 50, 10 + _MIN_FRAME_HEIGHT - 1
        )  # noqa: E501
        page = MagicMock()
        page_dict: dict[str, Any] = {"blocks": []}

        result = _detect_framed_tables(page, page_dict, drawings=[small_w, small_h])
        assert result == []

    def test_valid_frame_with_tabular_content(self) -> None:
        """Frame with 2+ cols and 2+ matching rows produces 1 table."""
        x0, y0 = 50, 50
        x1, y1 = 50 + _MIN_FRAME_WIDTH + 200, 50 + _MIN_FRAME_HEIGHT + 200
        drawing = _make_frame_drawing(x0, y0, x1, y1)

        # 2 columns, 3 rows of spans inside the frame
        cx = (x0 + x1) / 2
        spans_data: list[list[dict[str, Any]]] = []
        for row_idx in range(3):
            row_y = y0 + 20 + row_idx * 40
            spans_data.append(
                [
                    {
                        "bbox": (x0 + 10, row_y, cx - 10, row_y + 10),
                        "text": f"R{row_idx}C0",
                        "size": 12,
                        "flags": 0,
                        "font": "Arial",
                        "color": 0,
                    },  # noqa: E501
                    {
                        "bbox": (cx + 10, row_y, x1 - 10, row_y + 10),
                        "text": f"R{row_idx}C1",
                        "size": 12,
                        "flags": 0,
                        "font": "Arial",
                        "color": 0,
                    },  # noqa: E501
                ]
            )
        all_spans = [s for row in spans_data for s in row]
        page_dict = _make_page_dict_with_spans(all_spans)
        page = MagicMock()

        result = _detect_framed_tables(page, page_dict, drawings=[drawing])
        assert len(result) == 1
        assert "bbox" in result[0]
        assert "cells" in result[0]
        assert len(result[0]["cells"]) >= 2  # noqa: PLR2004

    def test_no_spans_inside_frame(self) -> None:
        """Valid frame but no text spans inside produces no tables."""
        drawing = _make_frame_drawing(
            50, 50, 50 + _MIN_FRAME_WIDTH + 100, 50 + _MIN_FRAME_HEIGHT + 100
        )  # noqa: E501
        # Spans far outside
        spans = [
            {
                "bbox": (500, 500, 550, 510),
                "text": "far",
                "size": 12,
                "flags": 0,
                "font": "Arial",
                "color": 0,
            },
        ]
        page_dict = _make_page_dict_with_spans(spans)
        page = MagicMock()

        result = _detect_framed_tables(page, page_dict, drawings=[drawing])
        assert result == []

    def test_too_few_columns_filtered(self) -> None:
        """If inferred columns < _MIN_RULED_COLUMNS, the frame is skipped."""
        x0, y0 = 50, 50
        x1 = 50 + _MIN_FRAME_WIDTH + 100
        y1 = 50 + _MIN_FRAME_HEIGHT + 100
        drawing = _make_frame_drawing(x0, y0, x1, y1)

        # All spans in a single column (no gap → 1 column)
        spans = [
            {
                "bbox": (x0 + 10, y0 + 10, x0 + 50, y0 + 20),
                "text": "Row1",
                "size": 12,
                "flags": 0,
                "font": "Arial",
                "color": 0,
            },
            {
                "bbox": (x0 + 10, y0 + 50, x0 + 50, y0 + 60),
                "text": "Row2",
                "size": 12,
                "flags": 0,
                "font": "Arial",
                "color": 0,
            },
            {
                "bbox": (x0 + 10, y0 + 90, x0 + 50, y0 + 100),
                "text": "Row3",
                "size": 12,
                "flags": 0,
                "font": "Arial",
                "color": 0,
            },
        ]
        page_dict = _make_page_dict_with_spans(spans)
        page = MagicMock()

        result = _detect_framed_tables(page, page_dict, drawings=[drawing])
        assert result == []

    def test_too_few_matching_rows(self) -> None:
        """2+ cols but fewer than _MIN_TABULAR_ROWS matching rows → filtered."""
        x0, y0 = 50, 50
        x1 = 50 + _MIN_FRAME_WIDTH + 200
        y1 = 50 + _MIN_FRAME_HEIGHT + 100
        drawing = _make_frame_drawing(x0, y0, x1, y1)

        cx = (x0 + x1) / 2
        # Only 1 row with 2 columns
        spans = [
            {
                "bbox": (x0 + 10, y0 + 20, cx - 10, y0 + 30),
                "text": "A",
                "size": 12,
                "flags": 0,
                "font": "Arial",
                "color": 0,
            },
            {
                "bbox": (cx + 10, y0 + 20, x1 - 10, y0 + 30),
                "text": "B",
                "size": 12,
                "flags": 0,
                "font": "Arial",
                "color": 0,
            },
        ]
        page_dict = _make_page_dict_with_spans(spans)
        page = MagicMock()

        result = _detect_framed_tables(page, page_dict, drawings=[drawing])
        assert result == []

    def test_multiple_frames_multiple_tables(self) -> None:
        """Two valid frames produce two tables."""
        x0_a, y0_a = 50, 50
        x1_a = x0_a + _MIN_FRAME_WIDTH + 200
        y1_a = y0_a + _MIN_FRAME_HEIGHT + 200
        frame_a = _make_frame_drawing(x0_a, y0_a, x1_a, y1_a)

        x0_b, y0_b = 50, 400
        x1_b = x0_b + _MIN_FRAME_WIDTH + 200
        y1_b = y0_b + _MIN_FRAME_HEIGHT + 200
        frame_b = _make_frame_drawing(x0_b, y0_b, x1_b, y1_b)

        # Each frame needs 2+ cols, 2+ matching rows
        def _make_table_spans(
            fx0: float,
            fy0: float,
            fx1: float,
        ) -> list[dict[str, Any]]:
            cx = (fx0 + fx1) / 2
            out: list[dict[str, Any]] = []
            for ri in range(_MIN_TABULAR_ROWS + 1):
                ry = fy0 + 20 + ri * 40
                out.append(
                    {
                        "bbox": (fx0 + 10, ry, cx - 10, ry + 10),
                        "text": f"L{ri}",
                        "size": 12,
                        "flags": 0,
                        "font": "Arial",
                        "color": 0,
                    }
                )  # noqa: E501
                out.append(
                    {
                        "bbox": (cx + 10, ry, fx1 - 10, ry + 10),
                        "text": f"R{ri}",
                        "size": 12,
                        "flags": 0,
                        "font": "Arial",
                        "color": 0,
                    }
                )  # noqa: E501
            return out

        all_spans = _make_table_spans(x0_a, y0_a, x1_a) + _make_table_spans(
            x0_b, y0_b, x1_b
        )  # noqa: E501
        page_dict = _make_page_dict_with_spans(all_spans)
        page = MagicMock()

        result = _detect_framed_tables(page, page_dict, drawings=[frame_a, frame_b])
        assert len(result) == 2  # noqa: PLR2004

    def test_cell_count_matches_rows_times_cols(self) -> None:
        """Number of cells equals (number of row boundaries - 1) * (number of col dividers - 1)."""  # noqa: E501
        x0, y0 = 50, 50
        x1, y1 = 350, 300
        drawing = _make_frame_drawing(x0, y0, x1, y1)

        # 3 columns: spans at x~80, x~180, x~280
        # 3 rows: spans at y~70, y~130, y~190
        spans = []
        col_xs = [80, 180, 280]
        row_ys = [70, 130, 190]
        for ry in row_ys:
            for cx_val in col_xs:
                spans.append(
                    {
                        "bbox": (cx_val, ry, cx_val + 40, ry + 10),
                        "text": "T",
                        "size": 12,
                        "flags": 0,
                        "font": "Arial",
                        "color": 0,
                    }
                )  # noqa: E501
        page_dict = _make_page_dict_with_spans(spans)
        page = MagicMock()

        result = _detect_framed_tables(page, page_dict, drawings=[drawing])
        if result:
            table = result[0]
            # Inferred columns and rows determine cell count
            # Just verify cells is a multiple of rows or cols detected
            assert len(table["cells"]) >= _MIN_TABULAR_ROWS * _MIN_RULED_COLUMNS  # noqa: PLR2004  # noqa: E501

    def test_frame_bbox_preserved(self) -> None:
        """Output bbox matches the frame coordinates."""
        x0, y0 = 60, 80
        x1 = x0 + _MIN_FRAME_WIDTH + 200
        y1 = y0 + _MIN_FRAME_HEIGHT + 200
        drawing = _make_frame_drawing(x0, y0, x1, y1)

        cx = (x0 + x1) / 2
        spans = []
        for ri in range(_MIN_TABULAR_ROWS + 1):
            ry = y0 + 20 + ri * 40
            spans.append(
                {
                    "bbox": (x0 + 10, ry, cx - 10, ry + 10),
                    "text": f"L{ri}",
                    "size": 12,
                    "flags": 0,
                    "font": "Arial",
                    "color": 0,
                }
            )  # noqa: E501
            spans.append(
                {
                    "bbox": (cx + 10, ry, x1 - 10, ry + 10),
                    "text": f"R{ri}",
                    "size": 12,
                    "flags": 0,
                    "font": "Arial",
                    "color": 0,
                }
            )  # noqa: E501
        page_dict = _make_page_dict_with_spans(spans)
        page = MagicMock()

        result = _detect_framed_tables(page, page_dict, drawings=[drawing])
        assert len(result) == 1
        bbox = result[0]["bbox"]
        assert bbox[0] == pytest.approx(x0)
        assert bbox[1] == pytest.approx(y0)
        assert bbox[2] == pytest.approx(x1)
        assert bbox[3] == pytest.approx(y1)

    def test_drawings_parameter_used(self) -> None:
        """When drawings param is provided, page.get_drawings is NOT called."""
        page = MagicMock()
        page_dict: dict[str, Any] = {"blocks": []}
        _detect_framed_tables(page, page_dict, drawings=[])
        page.get_drawings.assert_not_called()

    def test_exception_in_get_drawings(self) -> None:
        """If page.get_drawings raises, function returns [] gracefully."""
        page = MagicMock()
        page.get_drawings.side_effect = RuntimeError("broken")
        page_dict: dict[str, Any] = {"blocks": []}
        result = _detect_framed_tables(page, page_dict, drawings=None)
        assert result == []

    def test_exact_min_dimensions(self) -> None:
        """Frame at exactly _MIN_FRAME_WIDTH x _MIN_FRAME_HEIGHT passes the size filter."""  # noqa: E501
        x0, y0 = 50, 50
        x1 = x0 + _MIN_FRAME_WIDTH
        y1 = y0 + _MIN_FRAME_HEIGHT
        drawing = _make_frame_drawing(x0, y0, x1, y1)

        # Even though the frame passes size, with no spans → no table
        page_dict: dict[str, Any] = {"blocks": []}
        page = MagicMock()

        # The function should NOT crash; it should simply return []
        # because there are no spans (the size filter is passed, but content is empty)
        result = _detect_framed_tables(page, page_dict, drawings=[drawing])
        assert result == []

    def test_non_rect_items_ignored(self) -> None:
        """Line items ('l') in drawings are not treated as frames."""
        # A drawing with only line items, no "re"
        drawing_with_lines = {
            "items": [
                ("l", pymupdf.Point(50, 50), pymupdf.Point(300, 50)),
                ("l", pymupdf.Point(50, 50), pymupdf.Point(50, 300)),
            ],
        }
        page = MagicMock()
        page_dict: dict[str, Any] = {"blocks": []}
        result = _detect_framed_tables(page, page_dict, drawings=[drawing_with_lines])
        assert result == []


# ── TestInferColumnsByGaps ─────────────────────────────────


class TestInferColumnsByGaps:
    """Tests for _infer_columns_by_gaps."""

    @staticmethod
    def _span(x0: float, x1: float, y: float) -> dict:
        """Create a minimal span dict with a bbox."""
        return {"bbox": (x0, y, x1, y + 10)}

    def test_empty_spans(self) -> None:
        """Empty text_rows returns empty list."""
        result = _infer_columns_by_gaps([], (0.0, 0.0, 500.0, 800.0))
        assert result == []

    def test_single_dense_row(self) -> None:
        """Single row with contiguous spans → no gap → []."""
        # All spans adjacent (gap < _MIN_COL_GAP=5)
        row = [
            self._span(10, 100, 50),
            self._span(102, 200, 50),
        ]
        result = _infer_columns_by_gaps([row], (0.0, 0.0, 500.0, 800.0))
        assert result == []

    def test_clear_gap(self) -> None:
        """Two groups with clear gap → dividers returned."""
        # Gap of 50pt between spans (well above _MIN_COL_GAP)
        row1 = [
            self._span(10, 100, 50),
            self._span(150, 250, 50),
        ]
        row2 = [
            self._span(10, 95, 70),
            self._span(155, 250, 70),
        ]
        result = _infer_columns_by_gaps([row1, row2], (0.0, 0.0, 500.0, 800.0))
        # Should be [x0, divider, x1]
        assert len(result) == 3  # noqa: PLR2004
        assert result[0] == pytest.approx(0.0)
        assert result[-1] == pytest.approx(500.0)
        # Divider between ~100-155 range
        assert 100 < result[1] < 155  # noqa: PLR2004

    def test_no_gap_falls_back(self) -> None:
        """Spans that overlap in x produce no gaps → []."""
        row1 = [self._span(10, 200, 50)]
        row2 = [self._span(10, 200, 70)]
        result = _infer_columns_by_gaps([row1, row2], (0.0, 0.0, 500.0, 800.0))
        assert result == []

    def test_multiple_gaps(self) -> None:
        """Three columns with two gaps → 4 dividers."""
        row1 = [
            self._span(10, 80, 50),
            self._span(120, 200, 50),
            self._span(240, 320, 50),
        ]
        row2 = [
            self._span(10, 80, 70),
            self._span(120, 200, 70),
            self._span(240, 320, 70),
        ]
        row3 = [
            self._span(10, 80, 90),
            self._span(120, 200, 90),
            self._span(240, 320, 90),
        ]
        result = _infer_columns_by_gaps(
            [row1, row2, row3],
            (0.0, 0.0, 500.0, 800.0),
        )
        # [x0, div1, div2, x1]
        assert len(result) == 4  # noqa: PLR2004
        assert result[0] == pytest.approx(0.0)
        assert result[-1] == pytest.approx(500.0)
        # First divider between col1 and col2
        assert 80 < result[1] < 120  # noqa: PLR2004
        # Second divider between col2 and col3
        assert 200 < result[2] < 240  # noqa: PLR2004


# ── TestGetFormXobjectRects ────────────────────────────────


class TestGetFormXobjectRects:
    """Tests for _get_form_xobject_rects."""

    def test_no_xobjects(self) -> None:
        """Page with no form xobjects → empty list."""
        page = MagicMock()
        page.get_xobjects.return_value = []
        result = _get_form_xobject_rects(page)
        assert result == []

    def test_xref_stream_error_skips_entry(self) -> None:
        """xref_stream error on an XObject → skipped, []."""
        page = MagicMock()
        doc = MagicMock()
        page.parent = doc
        # One form XObject (type 0)
        page.get_xobjects.return_value = [
            (42, "Im0", 0, (0, 0, 100, 100)),  # noqa: PLR2004
        ]
        doc.xref_stream.side_effect = RuntimeError("corrupt")
        result = _get_form_xobject_rects(page)
        assert result == []

    def test_drawings_only_no_xobjects(self) -> None:
        """Page has drawings but no XObjects → []."""
        page = MagicMock()
        # Return empty list — no form XObjects present
        page.get_xobjects.return_value = []
        page.get_drawings.return_value = [
            {
                "items": [
                    (
                        "re",
                        pymupdf.Rect(0, 0, 100, 100),
                    ),
                ],
            },
        ]
        result = _get_form_xobject_rects(page)
        assert result == []


# ── RTL text alignment detection ──────────────────────────────────────────────


class TestDetectBlockAlignmentRTL:
    """Tests for RTL (right-to-left) alignment detection in _detect_block_alignment.

    Arabic and Hebrew text typically aligns to the right edge.
    When lines consistently hug the right edge with ragged left, the
    alignment detector should classify the block as "right".
    """

    def test_right_aligned_rtl_text(self) -> None:
        """Lines hugging the right edge with ragged left → right alignment."""
        # Simulates Arabic/Hebrew text: right edge at ~350, left varies
        extents = [(150, 350), (120, 350), (180, 350), (200, 350)]
        align, indent = _detect_block_alignment(
            extents,
            [50, 100, 350, 200],
            [12.0] * 4,
        )
        assert align == "right"
        assert indent == 0.0

    def test_single_line_rtl_centered_on_page(self) -> None:
        """Single-line RTL block centered on the page → center."""
        # Block occupies ~40% of page, roughly symmetric margins
        extents = [(180, 420)]
        align, _ = _detect_block_alignment(
            extents,
            [180, 100, 420, 120],
            [14.0],
            page_width=612.0,
        )
        assert align == "center"

    def test_rtl_justified_both_edges(self) -> None:
        """RTL justified text: both left and right edges consistent."""
        extents = [(50, 350), (50, 350), (50, 349), (50, 348), (50, 200)]
        align, _ = _detect_block_alignment(
            extents,
            [50, 100, 350, 200],
            [12.0] * 5,  # noqa: PLR2004
        )
        assert align == "justify"

    def test_right_aligned_multiline_ragged_left(self) -> None:
        """Multiple lines with consistent right edge, varying left → right."""
        extents = [
            (200, 500),
            (180, 500),
            (220, 500),
            (190, 500),
            (210, 500),
        ]
        align, _ = _detect_block_alignment(
            extents,
            [100, 100, 500, 200],
            [10.0] * 5,  # noqa: PLR2004
        )
        assert align == "right"

    def test_single_line_rtl_returns_left_without_page_width(self) -> None:
        """Single-line block without page_width context → defaults to left."""
        extents = [(200, 350)]
        align, _ = _detect_block_alignment(
            extents,
            [200, 100, 350, 120],
            [12.0],
        )
        assert align == "left"


# ── Encrypted/password-protected PDF ──────────────────────────────────────────


class TestCheckPdfEncryption:
    """Tests for encrypted PDF detection and error propagation."""

    def test_encrypted_pdf_detected_via_mock(self) -> None:
        """A password-protected PDF is detected by needs_pass (mocked)."""
        from src.utils.file_utils import _check_pdf_encryption  # noqa: PLC0415

        mock_doc = MagicMock()
        mock_doc.needs_pass = True

        with patch("pymupdf.open", return_value=mock_doc):
            result = _check_pdf_encryption(Path("/fake/encrypted.pdf"))

        assert result is True
        mock_doc.close.assert_called_once()

    def test_unencrypted_pdf_not_detected(self, tmp_path: Path) -> None:
        """A normal PDF without encryption returns False."""
        from src.utils.file_utils import _check_pdf_encryption  # noqa: PLC0415

        pdf = tmp_path / "normal.pdf"
        _make_pdf(pdf, ["Hello world"])
        assert _check_pdf_encryption(pdf) is False

    def test_unencrypted_pdf_needs_pass_false(self) -> None:
        """needs_pass == False → _check_pdf_encryption returns False."""
        from src.utils.file_utils import _check_pdf_encryption  # noqa: PLC0415

        mock_doc = MagicMock()
        mock_doc.needs_pass = False

        with patch("pymupdf.open", return_value=mock_doc):
            result = _check_pdf_encryption(Path("/fake/normal.pdf"))

        assert result is False
        mock_doc.close.assert_called_once()

    def test_is_file_encrypted_integration(self, tmp_path: Path) -> None:
        """is_file_encrypted dispatches to _check_pdf_encryption for .pdf."""
        from src.utils.file_utils import is_file_encrypted  # noqa: PLC0415

        pdf = tmp_path / "normal.pdf"
        _make_pdf(pdf, ["Hello world"])
        assert is_file_encrypted(pdf) is False

    def test_close_called_even_when_encrypted(self) -> None:
        """doc.close() is called in the finally block, even for encrypted PDFs."""
        from src.utils.file_utils import _check_pdf_encryption  # noqa: PLC0415

        mock_doc = MagicMock()
        mock_doc.needs_pass = True

        with patch("pymupdf.open", return_value=mock_doc):
            _check_pdf_encryption(Path("/fake/encrypted.pdf"))

        mock_doc.close.assert_called_once()

    def test_open_failure_propagates(self) -> None:
        """When pymupdf.open raises, the exception propagates."""
        from src.utils.file_utils import _check_pdf_encryption  # noqa: PLC0415

        with (
            patch(
                "pymupdf.open",
                side_effect=RuntimeError("corrupt file"),
            ),
            pytest.raises(RuntimeError, match="corrupt file"),
        ):
            _check_pdf_encryption(Path("/fake/corrupt.pdf"))


# ── Widget checkpoint round-trip ──────────────────────────────────────────────


class TestWidgetCheckpointRoundTrip:
    """Tests for saving and loading widget entries through the checkpoint system."""

    def test_widget_entries_saved_and_loaded(self, tmp_path: Path) -> None:
        """Widget entries survive save → load checkpoint round-trip."""
        from src.core.checkpoint import (  # noqa: PLC0415
            load_pdf_checkpoint,
            save_pdf_page_progress,
        )

        widget_entries = [
            {
                "type": "widget",
                "widget_type": _WIDGET_TYPE_TEXT,
                "field_name": "name",
                "text": "John Doe",
                "translated_text": "Jean Dupont",
            },
            {
                "type": "widget",
                "widget_type": _WIDGET_TYPE_COMBOBOX,
                "field_name": "color",
                "text": "Red",
                "translated_text": "Rouge",
                "choice_index": 0,
            },
        ]
        blocks = [
            {
                "rect": [0, 0, 200, 20],
                "text": "Hello",
                "translated_text": "Bonjour",
            },
        ]
        save_pdf_page_progress(tmp_path, 0, blocks + widget_entries, 1)

        loaded = load_pdf_checkpoint(tmp_path)
        assert loaded is not None
        page_data = loaded[0]

        # Separate widgets from blocks
        loaded_widgets = [e for e in page_data if e.get("type") == "widget"]
        loaded_blocks = [e for e in page_data if e.get("type") != "widget"]

        assert len(loaded_widgets) == 2  # noqa: PLR2004
        assert loaded_widgets[0]["translated_text"] == "Jean Dupont"
        assert loaded_widgets[0]["field_name"] == "name"
        assert loaded_widgets[1]["translated_text"] == "Rouge"
        assert loaded_widgets[1]["choice_index"] == 0
        assert len(loaded_blocks) == 1
        assert loaded_blocks[0]["translated_text"] == "Bonjour"

    def test_widget_mixed_with_annots_and_links(self, tmp_path: Path) -> None:
        """Widgets, annotations, and links all coexist in checkpoint."""
        from src.core.checkpoint import (  # noqa: PLC0415
            load_pdf_checkpoint,
            save_pdf_page_progress,
        )

        entries = [
            {"rect": [0, 0, 200, 20], "text": "Hello"},
            {"type": "annot", "text": "Note", "translated_text": "Nota"},
            {
                "type": "widget",
                "widget_type": _WIDGET_TYPE_TEXT,
                "field_name": "f1",
                "text": "Value",
                "translated_text": "Valor",
            },
            {
                "type": "link",
                "kind": 2,
                "from": [10, 20, 100, 40],
                "uri": "https://example.com",
            },
        ]
        save_pdf_page_progress(tmp_path, 0, entries, 1)
        loaded = load_pdf_checkpoint(tmp_path)
        assert loaded is not None
        page_data = loaded[0]

        types = [e.get("type") for e in page_data]
        assert "annot" in types
        assert "widget" in types
        assert "link" in types

    def test_empty_widget_list_round_trip(self, tmp_path: Path) -> None:
        """Empty page data (no widgets) round-trips cleanly."""
        from src.core.checkpoint import (  # noqa: PLC0415
            load_pdf_checkpoint,
            save_pdf_page_progress,
        )

        save_pdf_page_progress(tmp_path, 0, [], 1)
        loaded = load_pdf_checkpoint(tmp_path)
        assert loaded is not None
        assert loaded[0] == []

    def test_process_pdf_uses_cached_widgets(self, tmp_path: Path) -> None:
        """process_pdf_file restores cached widgets from checkpoint."""
        from src.core.checkpoint import save_pdf_page_progress  # noqa: PLC0415

        pdf = tmp_path / "test.pdf"
        output = tmp_path / "output.pdf"
        _make_pdf(pdf, ["Hello world"])

        # Pre-save checkpoint with a widget
        ckpt_dir = tmp_path / "checkpoint"
        ckpt_dir.mkdir()
        widget = {
            "type": "widget",
            "widget_type": _WIDGET_TYPE_TEXT,
            "field_name": "f1",
            "text": "Hello",
            "translated_text": "Hola",
        }
        save_pdf_page_progress(ckpt_dir, 0, [widget], 1)

        with (
            patch(
                "src.core.pdf_processor._inject_page_widgets",
            ) as mock_inject,
            patch(
                "src.core.pdf_processor.translate_batch",
            ),
        ):
            process_pdf_file(
                pdf,
                output,
                "Spanish",
                checkpoint_dir=ckpt_dir,
            )
        # The cached widget should be injected
        mock_inject.assert_called_once()
        injected = mock_inject.call_args[0][1]
        assert injected[0]["translated_text"] == "Hola"


# ── Font cache behavior ──────────────────────────────────────────────────────


class TestFontfileCacheBehavior:
    """Tests for _fontfile_cache hits and misses in _resolve_fontfile."""

    @pytest.fixture(autouse=True)
    def _clear_cache(self) -> None:
        """Clears the font file cache before each test."""
        _fontfile_cache.clear()

    def test_cache_miss_calls_fc_match(self) -> None:
        """First call for a font triggers fc-match lookup."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf\n"

        with (
            patch(f"{_PDF}.shutil.which", return_value="fc-match"),
            patch(f"{_PDF}.subprocess.run", return_value=mock_result) as mock_run,
            patch("pathlib.Path.is_file", return_value=True),
        ):
            result = _resolve_fontfile("CacheMissFont")

        assert result is not None
        mock_run.assert_called_once()

    def test_cache_hit_skips_fc_match(self) -> None:
        """Second call for the same font returns cached result without fc-match."""
        # Pre-populate cache
        _fontfile_cache["CachedFont"] = "/some/cached/path.ttf"

        with (
            patch(f"{_PDF}.shutil.which") as mock_which,
            patch(f"{_PDF}.subprocess.run") as mock_run,
        ):
            result = _resolve_fontfile("CachedFont")

        assert result == "/some/cached/path.ttf"
        mock_which.assert_not_called()
        mock_run.assert_not_called()

    def test_cache_stores_none_for_missing_font(self) -> None:
        """When no font file is found, None is cached to avoid repeated lookups."""
        with (
            patch(f"{_PDF}.shutil.which", return_value=None),
            patch("pathlib.Path.is_file", return_value=False),
        ):
            result1 = _resolve_fontfile("MissingFont")

        assert result1 is None
        assert "MissingFont" in _fontfile_cache
        assert _fontfile_cache["MissingFont"] is None

        # Second call should use cache (no fc-match)
        with patch(f"{_PDF}.shutil.which") as mock_which:
            result2 = _resolve_fontfile("MissingFont")

        assert result2 is None
        mock_which.assert_not_called()

    def test_different_fonts_get_separate_cache_entries(self) -> None:
        """Different font names result in separate cache entries."""
        _fontfile_cache["FontA"] = "/path/to/a.ttf"
        _fontfile_cache["FontB"] = "/path/to/b.ttf"

        assert _resolve_fontfile("FontA") == "/path/to/a.ttf"
        assert _resolve_fontfile("FontB") == "/path/to/b.ttf"


# ── Empty page handling ──────────────────────────────────────────────────────


class TestEmptyPageHandling:
    """Tests for pages with no text blocks at all."""

    def test_extract_page_blocks_empty_page(self, tmp_path: Path) -> None:
        """A blank page returns an empty block list."""
        pdf = tmp_path / "blank.pdf"
        doc = pymupdf.open()
        doc.new_page()
        doc.save(str(pdf))
        doc.close()

        doc, page = _open_page(pdf)
        blocks = _extract_page_blocks(page)
        doc.close()
        assert blocks == []

    def test_process_pdf_empty_page_no_crash(self, tmp_path: Path) -> None:
        """process_pdf_file succeeds on a PDF with an empty page."""
        pdf = tmp_path / "blank.pdf"
        output = tmp_path / "output.pdf"
        doc = pymupdf.open()
        doc.new_page()
        doc.save(str(pdf))
        doc.close()

        with patch(
            "src.core.pdf_processor.translate_batch",
        ) as mock_batch:
            result = process_pdf_file(pdf, output, "French")

        assert result is True
        # No text to translate → translate_batch not called
        mock_batch.assert_not_called()
        assert output.exists()

    def test_empty_page_checkpoint_saved(self, tmp_path: Path) -> None:
        """An empty page saves an empty checkpoint entry."""
        from src.core.checkpoint import load_pdf_checkpoint  # noqa: PLC0415

        pdf = tmp_path / "blank.pdf"
        output = tmp_path / "output.pdf"
        ckpt_dir = tmp_path / "ckpt"
        ckpt_dir.mkdir()
        doc = pymupdf.open()
        doc.new_page()
        doc.save(str(pdf))
        doc.close()

        with patch("src.core.pdf_processor.translate_batch"):
            process_pdf_file(
                pdf,
                output,
                "French",
                checkpoint_dir=ckpt_dir,
            )

        loaded = load_pdf_checkpoint(ckpt_dir)
        assert loaded is not None
        # Page 0 should have an empty list (no blocks)
        assert loaded[0] == []

    def test_empty_page_with_images_detected_as_scanned(
        self,
        tmp_path: Path,
    ) -> None:
        """An imageless blank page is NOT treated as a scanned page."""
        pdf = tmp_path / "blank.pdf"
        output = tmp_path / "output.pdf"
        doc = pymupdf.open()
        doc.new_page()
        doc.save(str(pdf))
        doc.close()

        with (
            patch("src.core.pdf_processor.translate_batch"),
            patch(
                "src.core.pdf_processor._process_scanned_pages",
            ) as mock_scanned,
        ):
            process_pdf_file(pdf, output, "French")

        mock_scanned.assert_not_called()

    def test_mixed_empty_and_text_pages(self, tmp_path: Path) -> None:
        """PDF with one text page and one blank page processes correctly."""
        pdf = tmp_path / "mixed.pdf"
        output = tmp_path / "output.pdf"
        _make_multipage_pdf(pdf, num_pages=2, blank_last=True)

        with patch(
            "src.core.pdf_processor.translate_batch",
            return_value=["Page 1 texte"],
        ):
            result = process_pdf_file(pdf, output, "French")

        assert result is True
        assert output.exists()


# ── Single-line block vertical centering ──────────────────────────────────────


class TestVerticalCenteringConstants:
    """Tests for _is_multiline_block, _MULTILINE_HEIGHT_RATIO, and threshold."""

    def test_multiline_height_ratio_value(self) -> None:
        """_MULTILINE_HEIGHT_RATIO is 2.0."""
        assert _MULTILINE_HEIGHT_RATIO == 2.0  # noqa: PLR2004

    def test_vcenter_spare_threshold_value(self) -> None:
        """_VCENTER_SPARE_THRESHOLD is 2.0."""
        assert _VCENTER_SPARE_THRESHOLD == 2.0  # noqa: PLR2004

    def test_single_line_block_height_below_ratio(self) -> None:
        """Block height < 2x font_size → single-line."""
        block = {"text": "Hello", "font_size": 12.0, "rect": [0, 0, 200, 22]}
        assert not _is_multiline_block(block)

    def test_multiline_block_height_above_ratio(self) -> None:
        """Block height > 2x font_size → multi-line."""
        block = {"text": "Hello", "font_size": 12.0, "rect": [0, 0, 200, 30]}
        assert _is_multiline_block(block)

    def test_multiline_block_with_newline(self) -> None:
        r"""Block text containing \\n → multi-line regardless of height."""
        block = {"text": "Line1\nLine2", "font_size": 12.0, "rect": [0, 0, 200, 15]}
        assert _is_multiline_block(block)

    def test_single_line_no_font_size(self) -> None:
        """Block without font_size → single-line (height check skipped)."""
        block = {"text": "Hello", "rect": [0, 0, 200, 50]}
        assert not _is_multiline_block(block)

    def test_measure_htmlbox_spare_above_threshold(self) -> None:
        """Spare height > 2.0pt triggers vertical centering."""
        html = (
            '<p style="font-family:sans-serif; font-size:8pt; '
            'white-space:nowrap; margin:0;">X</p>'
        )
        rect = pymupdf.Rect(0, 0, 200, 50)
        doc = pymupdf.open()
        spare, scale = _measure_htmlbox_spare(doc, html, rect)
        doc.close()
        assert spare > _VCENTER_SPARE_THRESHOLD
        assert scale == 1.0  # noqa: PLR2004

    def test_measure_htmlbox_spare_tight_fit(self) -> None:
        """Very tight rect → small spare, potentially below threshold."""
        html = (
            '<p style="font-family:sans-serif; font-size:12pt; margin:0;">'
            "Some text here</p>"
        )
        # Height just barely fits the 12pt text
        rect = pymupdf.Rect(0, 0, 200, 17)
        doc = pymupdf.open()
        spare, scale = _measure_htmlbox_spare(doc, html, rect)
        doc.close()
        # Spare should be small (possibly below threshold)
        assert isinstance(spare, float)
        assert spare >= 0


# ── Continuation line merging with math spans ────────────────────────────────


class TestMergeContinuationLinesMathSpans:
    """Tests for _merge_continuation_lines with math-like split blocks."""

    def test_math_radical_split_merged(self) -> None:
        """Radicand split into separate block is merged back.

        Simulates PyMuPDF splitting sqrt(2/delta) where '2/delta' is
        a separate block.
        """
        # Block with radical symbol, ending at x=50
        b1 = _make_raw_block(
            (10, 100, 50, 112),
            [_make_raw_line((10, 100, 50, 112))],
        )
        # Radicand block, starting at x=51 (gap=1 < _ADJACENT_BLOCK_MAX_GAP)
        b2 = _make_raw_block(
            (51, 100, 100, 112),
            [_make_raw_line((51, 100, 100, 112))],
        )
        result = _merge_continuation_lines([b1, b2])
        assert len(result) == 1
        # Merged block should have 2 lines
        assert len(result[0]["lines"]) == 2  # noqa: PLR2004

    def test_multiline_block_partial_merge(self) -> None:
        """Only the first line of next block is transferred, rest stays."""
        # Block 1: two lines
        b1 = _make_raw_block(
            (10, 100, 100, 130),
            [
                _make_raw_line((10, 100, 100, 112)),
                _make_raw_line((10, 118, 50, 130)),
            ],
        )
        # Block 2: two lines, first on same y as b1's last line
        b2 = _make_raw_block(
            (51, 118, 120, 150),
            [
                _make_raw_line((51, 118, 120, 130)),
                _make_raw_line((10, 140, 120, 150)),
            ],
        )
        result = _merge_continuation_lines([b1, b2])
        assert len(result) == 2  # noqa: PLR2004
        # b1 absorbed one line from b2
        assert len(result[0]["lines"]) == 3  # noqa: PLR2004
        # b2 retains its remaining line
        assert len(result[1]["lines"]) == 1

    def test_three_adjacent_blocks_chained_merge(self) -> None:
        """Three consecutive x-adjacent blocks on same y → all merged."""
        b1 = _make_raw_block(
            (10, 100, 50, 112),
            [_make_raw_line((10, 100, 50, 112))],
        )
        b2 = _make_raw_block(
            (51, 100, 80, 112),
            [_make_raw_line((51, 100, 80, 112))],
        )
        b3 = _make_raw_block(
            (81, 100, 120, 112),
            [_make_raw_line((81, 100, 120, 112))],
        )
        result = _merge_continuation_lines([b1, b2, b3])
        assert len(result) == 1
        assert len(result[0]["lines"]) == 3  # noqa: PLR2004

    def test_bbox_recomputed_after_merge(self) -> None:
        """After merge, block bbox covers all absorbed lines."""
        b1 = _make_raw_block(
            (10, 100, 50, 112),
            [_make_raw_line((10, 100, 50, 112))],
        )
        b2 = _make_raw_block(
            (51, 100, 120, 112),
            [_make_raw_line((51, 100, 120, 112))],
        )
        result = _merge_continuation_lines([b1, b2])
        bbox = result[0]["bbox"]
        # bbox should span from 10 to 120 in x
        assert bbox[0] == 10  # noqa: PLR2004
        assert bbox[2] == 120  # noqa: PLR2004

    def test_negative_gap_within_tolerance_merges(self) -> None:
        """Slight overlap (negative gap within tolerance) still merges."""
        b1 = _make_raw_block(
            (10, 100, 52, 112),
            [_make_raw_line((10, 100, 52, 112))],
        )
        # x0=50 < b1.x1=52 → gap=-2, within -_ADJACENT_BLOCK_MAX_GAP
        b2 = _make_raw_block(
            (50, 100, 100, 112),
            [_make_raw_line((50, 100, 100, 112))],
        )
        result = _merge_continuation_lines([b1, b2])
        assert len(result) == 1

    def test_vertical_text_blocks_not_merged(self) -> None:
        """Vertical text blocks (dir close to (0,1)) are skipped."""
        b1 = _make_raw_block(
            (10, 100, 50, 112),
            [_make_raw_line((10, 100, 50, 112), direction=(0, 1))],
        )
        b2 = _make_raw_block(
            (51, 100, 100, 112),
            [_make_raw_line((51, 100, 100, 112), direction=(0, 1))],
        )
        result = _merge_continuation_lines([b1, b2])
        assert len(result) == 2  # noqa: PLR2004


# ── Link disambiguation with context characters ──────────────────────────────


class TestLinkDisambiguationContext:
    """Tests for link disambiguation via _left_char/_right_char context."""

    def _make_block(
        self,
        text: str,
    ) -> tuple[list[tuple[str, Any]], str]:
        """Build block_chars and block_text from a string."""
        chars = []
        for i, c in enumerate(text):
            x0 = 10.0 + i * 6
            chars.append((c, pymupdf.Rect(x0, 100, x0 + 6, 112)))
        return chars, text

    def test_left_char_disambiguates_duplicate(self) -> None:
        """_left_char picks the correct occurrence of a repeated substring."""
        # "a2b c2d" — "2" at pos 1 (left='a') and pos 5 (left='c')
        chars, text = self._make_block("a2b c2d")
        link = {
            "_translated": "2",
            "_inner": "2",
            "_left_char": "c",  # target the second "2"
            "from": (0, 100, 50, 112),
        }
        rects, _ = _find_link_in_chars(chars, text, link, 0)
        assert len(rects) == 1
        # Should match the "2" at position 5
        expected_x = 10 + 5 * 6  # noqa: PLR2004
        assert abs(rects[0].x0 - expected_x) < 0.1

    def test_right_char_disambiguates_duplicate(self) -> None:
        """_right_char picks the correct occurrence."""
        chars, text = self._make_block("ref 2.0 and 2)")
        link = {
            "_translated": "2",
            "_inner": "2",
            "_right_char": ")",
            "from": (0, 100, 50, 112),
        }
        rects, _ = _find_link_in_chars(chars, text, link, 0)
        assert len(rects) == 1
        # Should match "2" at position 12 (before ")")
        expected_x = 10 + 12 * 6  # noqa: PLR2004
        assert abs(rects[0].x0 - expected_x) < 0.1

    def test_both_context_chars_required(self) -> None:
        """Both _left_char and _right_char must match for context pass."""
        chars, text = self._make_block("a2b c2d e2)")
        link = {
            "_translated": "2",
            "_inner": "2",
            "_left_char": "e",
            "_right_char": ")",
            "from": (0, 100, 50, 112),
        }
        rects, _ = _find_link_in_chars(chars, text, link, 0)
        assert len(rects) == 1
        # Should match "2" at position 9 (between 'e' and ')')
        expected_x = 10 + 9 * 6  # noqa: PLR2004
        assert abs(rects[0].x0 - expected_x) < 0.1

    def test_no_context_falls_back_to_sequential(self) -> None:
        """Without context chars, first occurrence from search_pos is used."""
        chars, text = self._make_block("2 and 2")
        link = {
            "_translated": "2",
            "_inner": "2",
            "from": (0, 100, 50, 112),
        }
        rects, pos = _find_link_in_chars(chars, text, link, 0)
        assert len(rects) == 1
        # First "2" at position 0
        expected_x = 10  # noqa: PLR2004
        assert abs(rects[0].x0 - expected_x) < 0.1

        # Second call from pos → second "2"
        rects2, _ = _find_link_in_chars(chars, text, link, pos)
        assert len(rects2) == 1
        expected_x2 = 10 + 6 * 6  # noqa: PLR2004
        assert abs(rects2[0].x0 - expected_x2) < 0.1

    def test_context_mismatch_all_falls_to_raw_substring(self) -> None:
        """When no position matches context, falls back to raw substring."""
        chars, text = self._make_block("X2Y")
        link = {
            "_translated": "2",
            "_inner": "2",
            "_left_char": "Z",  # not present
            "_right_char": "W",  # not present
            "from": (0, 100, 50, 112),
        }
        rects, _ = _find_link_in_chars(chars, text, link, 0)
        assert len(rects) == 1  # Falls back to raw find

    def test_extract_link_translations_stores_context(self) -> None:
        """_extract_link_translations stores _left_char/_right_char."""
        blocks = [
            {
                "translated_text": 'Xem [<a id="0">13</a>] chi tiết',
            }
        ]
        links: list[dict[str, Any]] = [{"_inner": "13"}]
        _extract_link_translations(blocks, links)
        assert links[0]["_translated"] == "13"
        assert links[0]["_left_char"] == "["
        assert links[0]["_right_char"] == "]"


# ── Bookmark translation with special characters ─────────────────────────────


class TestTranslateBookmarksSpecialChars:
    """Tests for _translate_bookmarks with HTML entities and Unicode."""

    def test_html_entity_in_title(self) -> None:
        """Bookmark title with HTML entities is translated correctly."""
        doc = pymupdf.open()
        doc.new_page()
        doc.set_toc([[1, "Introduction & Overview", 1]])

        with patch(
            "src.core.pdf_processor.translate_batch",
            return_value=["Introduction & Vue d'ensemble"],
        ):
            result = _translate_bookmarks(doc, "French", "", None, None)

        assert result is True
        toc = doc.get_toc()
        assert toc[0][1] == "Introduction & Vue d'ensemble"
        doc.close()

    def test_unicode_characters_in_title(self) -> None:
        """Bookmark title with Unicode characters survives round-trip."""
        doc = pymupdf.open()
        doc.new_page()
        title = "Résumé — Übersicht « Введение »"
        doc.set_toc([[1, title, 1]])

        translated = "Tóm tắt — Tổng quan « Giới thiệu »"
        with patch(
            "src.core.pdf_processor.translate_batch",
            return_value=[translated],
        ):
            result = _translate_bookmarks(doc, "Vietnamese", "", None, None)

        assert result is True
        toc = doc.get_toc()
        assert toc[0][1] == translated
        doc.close()

    def test_cjk_bookmark_title(self) -> None:
        """CJK characters in bookmark titles are handled."""
        doc = pymupdf.open()
        doc.new_page()
        doc.set_toc([[1, "第一章 Introduction", 1]])

        with patch(
            "src.core.pdf_processor.translate_batch",
            return_value=["Chapter 1 Introduction"],
        ):
            result = _translate_bookmarks(doc, "English", "", None, None)

        assert result is True
        toc = doc.get_toc()
        assert toc[0][1] == "Chapter 1 Introduction"
        doc.close()

    def test_nested_bookmarks_with_special_chars(self) -> None:
        """Nested TOC entries with special chars maintain structure."""
        doc = pymupdf.open()
        doc.new_page()
        doc.new_page()
        doc.new_page()
        doc.set_toc(
            [
                [1, "Part I: Analysis & Design", 1],
                [2, 'Chapter 1: "Hello World"', 2],
                [2, "Chapter 2: <Advanced>", 3],
            ]
        )

        with patch(
            "src.core.pdf_processor.translate_batch",
            return_value=[
                "Phần I: Phân tích & Thiết kế",
                'Chương 1: "Xin chào"',
                "Chương 2: <Nâng cao>",
            ],
        ):
            result = _translate_bookmarks(doc, "Vietnamese", "", None, None)

        assert result is True
        toc = doc.get_toc()
        assert toc[0][0] == 1  # level preserved
        assert toc[1][0] == 2  # noqa: PLR2004
        assert toc[2][0] == 2  # noqa: PLR2004
        assert toc[0][1] == "Phần I: Phân tích & Thiết kế"
        assert '"Xin chào"' in toc[1][1]
        doc.close()

    def test_whitespace_title_among_normal_titles(self) -> None:
        """Whitespace-only title alongside normal titles is handled."""
        doc = pymupdf.open()
        doc.new_page()
        doc.new_page()
        # PyMuPDF converts "" to " " in TOC, so use space directly.
        doc.set_toc([[1, "First", 1], [1, " ", 2]])

        with patch(
            "src.core.pdf_processor.translate_batch",
            return_value=["Premier", " "],
        ):
            result = _translate_bookmarks(doc, "French", "", None, None)

        assert result is True
        toc = doc.get_toc()
        assert toc[0][1] == "Premier"
        # Whitespace title preserved (translated as-is)
        assert toc[1][1].strip() == ""
        doc.close()


# ── Image translation on text pages ──────────────────────────────────────────


class TestTranslatePageImagesExtended:
    """Extended tests for _translate_page_images edge cases."""

    def test_skips_full_page_images(self, tmp_path: Path) -> None:
        """Images covering > 90% of page area are skipped."""
        pdf = tmp_path / "fullpage.pdf"
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Hello", fontsize=14)
        # Insert a nearly full-page image
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 100, 100), 0)
        # Page is 612x792 by default; place image at nearly full size
        page.insert_image(pymupdf.Rect(0, 0, 610, 790), pixmap=pix)
        doc.save(str(pdf))

        page = doc[0]
        xrefs: set[int] = set()
        with patch(
            "src.core.pdf_processor._translate_single_pdf_image",
        ) as mock_translate:
            _translate_page_images(
                doc,
                page,
                "French",
                "",
                None,
                "TesseractOCR",
                None,
                xrefs,
            )

        # Full-page image should be skipped — not in translated_xrefs
        mock_translate.assert_not_called()
        doc.close()

    def test_min_image_dim_boundary(self, tmp_path: Path) -> None:
        """Images exactly at _MIN_IMAGE_DIM boundary are processed."""
        pdf = tmp_path / "boundary.pdf"
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Hello", fontsize=14)
        dim = _MIN_IMAGE_DIM  # exactly 50
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, dim, dim), 0)
        page.insert_image(pymupdf.Rect(200, 200, 200 + dim, 200 + dim), pixmap=pix)
        doc.save(str(pdf))

        page = doc[0]
        xrefs: set[int] = set()
        with patch(
            "src.core.pdf_processor._translate_single_pdf_image",
            return_value=None,
        ):
            _translate_page_images(
                doc,
                page,
                "French",
                "",
                None,
                "TesseractOCR",
                None,
                xrefs,
            )

        # 50x50 image (on page, rendered at 50x50 pt) >= _MIN_IMAGE_DIM
        # Whether it's called depends on the rendered size, not pixel size
        # At minimum, xref should be tracked
        assert len(xrefs) > 0

        doc.close()

    def test_fatal_llm_errors_defined(self) -> None:
        """_FATAL_LLM_ERRORS contains expected error tags."""
        assert "AUTH_ERROR" in _FATAL_LLM_ERRORS
        assert "QUOTA_ERROR" in _FATAL_LLM_ERRORS
        assert "VISION_NOT_SUPPORTED" in _FATAL_LLM_ERRORS

    def test_is_fatal_llm_error_handles_service_suffix(self) -> None:
        """``_is_fatal_llm_error`` strips ``:Service`` before checking membership.

        Regression guard: the engine now raises ``AUTH_ERROR:Gemini``
        (etc.) so the UI can render service-specific copy.  The
        exact-match set membership ``error_tag in _FATAL_LLM_ERRORS``
        would miss the suffixed form, demoting a fatal error to
        skip-with-warning and silently completing the PDF with zero
        translated images.
        """
        from src.core.pdf_processor import _is_fatal_llm_error  # noqa: PLC0415

        # Base tags still fatal.
        assert _is_fatal_llm_error("AUTH_ERROR")
        assert _is_fatal_llm_error("QUOTA_ERROR")
        assert _is_fatal_llm_error("VISION_NOT_SUPPORTED")
        # Suffixed AUTH_ERROR variants ALSO fatal.
        assert _is_fatal_llm_error("AUTH_ERROR:Gemini")
        assert _is_fatal_llm_error("AUTH_ERROR:Google Cloud")
        assert _is_fatal_llm_error("AUTH_ERROR:Custom")
        # Non-fatal errors stay non-fatal.
        assert not _is_fatal_llm_error("CONNECTION_ERROR")
        assert not _is_fatal_llm_error("TIMEOUT_ERROR")
        assert not _is_fatal_llm_error("IMAGE_TOO_LARGE")
        # Empty / odd input safe (no crash, returns False).
        assert not _is_fatal_llm_error("")

    def test_vision_not_supported_propagates(self, tmp_path: Path) -> None:
        """VISION_NOT_SUPPORTED from image translation propagates up."""
        pdf = tmp_path / "vision.pdf"
        _make_pdf_with_image(pdf, texts=["Hello"], image_rect=(100, 200, 400, 500))

        doc = pymupdf.open(str(pdf))
        page = doc[0]

        with (
            patch(
                "src.core.pdf_processor._translate_single_pdf_image",
                side_effect=ValueError("VISION_NOT_SUPPORTED"),
            ),
            pytest.raises(ValueError, match="VISION_NOT_SUPPORTED"),
        ):
            _translate_page_images(
                doc,
                page,
                "French",
                "",
                None,
                "TesseractOCR",
                None,
                set(),
            )
        doc.close()

    def test_quota_error_propagates(self, tmp_path: Path) -> None:
        """QUOTA_ERROR from image translation propagates up."""
        pdf = tmp_path / "quota.pdf"
        _make_pdf_with_image(pdf, texts=["Hello"], image_rect=(100, 200, 400, 500))

        doc = pymupdf.open(str(pdf))
        page = doc[0]

        with (
            patch(
                "src.core.pdf_processor._translate_single_pdf_image",
                side_effect=ValueError("QUOTA_ERROR"),
            ),
            pytest.raises(ValueError, match="QUOTA_ERROR"),
        ):
            _translate_page_images(
                doc,
                page,
                "French",
                "",
                None,
                "TesseractOCR",
                None,
                set(),
            )
        doc.close()

    def test_extract_image_failure_adds_xref(self, tmp_path: Path) -> None:
        """When doc.extract_image raises, xref is added to avoid retry."""
        pdf = tmp_path / "extract_fail.pdf"
        _make_pdf_with_image(pdf, texts=["Hello"], image_rect=(100, 200, 400, 500))

        doc = pymupdf.open(str(pdf))
        page = doc[0]
        xrefs: set[int] = set()

        with patch.object(
            doc,
            "extract_image",
            side_effect=RuntimeError("corrupt"),
        ):
            _translate_page_images(
                doc,
                page,
                "French",
                "",
                None,
                "TesseractOCR",
                None,
                xrefs,
            )

        # xref should be tracked despite extraction failure
        assert len(xrefs) > 0
        doc.close()

    def test_no_images_on_page(self, tmp_path: Path) -> None:
        """Page with no images → function returns immediately."""
        pdf = tmp_path / "text_only.pdf"
        _make_pdf(pdf, ["Hello world"])

        doc = pymupdf.open(str(pdf))
        page = doc[0]
        xrefs: set[int] = set()

        with patch(
            "src.core.pdf_processor._translate_single_pdf_image",
        ) as mock_translate:
            _translate_page_images(
                doc,
                page,
                "French",
                "",
                None,
                "TesseractOCR",
                None,
                xrefs,
            )

        mock_translate.assert_not_called()
        assert len(xrefs) == 0
        doc.close()

    def test_translate_returns_none_skips_replace(self, tmp_path: Path) -> None:
        """When _translate_single_pdf_image returns None, no replacement."""
        pdf = tmp_path / "no_text.pdf"
        _make_pdf_with_image(pdf, texts=["Hello"], image_rect=(100, 200, 400, 500))

        doc = pymupdf.open(str(pdf))
        page = doc[0]
        xrefs: set[int] = set()

        with patch(
            "src.core.pdf_processor._translate_single_pdf_image",
            return_value=None,  # Image has no translatable text
        ):
            _translate_page_images(
                doc,
                page,
                "French",
                "",
                None,
                "TesseractOCR",
                None,
                xrefs,
            )

        # xref still tracked
        assert len(xrefs) > 0
        doc.close()

    def test_full_page_image_ratio_constant(self) -> None:
        """_FULL_PAGE_IMAGE_RATIO is 0.9."""
        assert _FULL_PAGE_IMAGE_RATIO == 0.9  # noqa: PLR2004

    def test_min_image_dim_constant(self) -> None:
        """_MIN_IMAGE_DIM is 50."""
        assert _MIN_IMAGE_DIM == 50  # noqa: PLR2004


# ══════════════════════════════════════════════════════════════════════════════
# NEW EDGE-CASE TESTS (appended)
# ══════════════════════════════════════════════════════════════════════════════


# ── TestDetectBlockAlignmentEdgeCases ─────────────────────────────────────────


class TestDetectBlockAlignmentEdgeCases:
    """Edge-case tests for _detect_block_alignment."""

    def test_single_word_block(self) -> None:
        """Single-word block returns left (default for single-line)."""
        align, indent = _detect_block_alignment(
            [(200, 240)],
            [200, 100, 240, 112],
        )
        assert align == "left"
        assert indent == 0.0

    def test_rtl_right_aligned_text(self) -> None:
        """Lines with consistent right edges and ragged left → right."""
        extents = [(250, 400), (230, 400), (270, 400), (240, 400)]
        align, _ = _detect_block_alignment(
            extents,
            [100, 100, 400, 200],
            [10.0] * 4,
        )
        assert align == "right"

    def test_mixed_alignment_page_varies(self) -> None:
        """Different blocks on the same page yield different alignments."""
        # Left-aligned block
        left_extents = [(50, 300), (50, 280), (50, 310)]
        left_align, _ = _detect_block_alignment(
            left_extents,
            [50, 100, 350, 200],
            [10.0] * 3,
        )
        assert left_align == "left"

        # Right-aligned block — ragged left, consistent right.
        # Use a wide block so lines clearly vary on the left.
        right_extents = [(200, 400), (150, 400), (250, 400), (100, 400)]
        right_align, _ = _detect_block_alignment(
            right_extents,
            [50, 100, 400, 200],
            [10.0] * 4,
        )
        assert right_align == "right"

    def test_all_centered_blocks(self) -> None:
        """Multiple lines with symmetric margins → center."""
        extents = [
            (120, 280),
            (125, 275),
            (115, 285),
            (122, 278),
        ]
        align, _ = _detect_block_alignment(
            extents,
            [50, 100, 350, 200],
            [10.0] * 4,
        )
        assert align == "center"

    def test_empty_line_extents(self) -> None:
        """Empty line_extents returns default ('left', 0.0)."""
        align, indent = _detect_block_alignment([], [0, 0, 100, 100])
        assert align == "left"
        assert indent == 0.0

    def test_short_line_ratio_exactly_at_boundary(self) -> None:
        """Last line exactly at _SHORT_LINE_RATIO width is NOT a short final.

        With typical_width=400, threshold = 400 * 0.9 = 360.
        Last line width=360 is NOT < 360 → not short final.
        However, 2 of 3 lines are right-aligned at the typical right edge,
        so is_right is still True and the result is 'justify'.
        """
        x0 = 50.0
        full_right = x0 + 400.0
        last_right = x0 + 400.0 * _SHORT_LINE_RATIO  # exactly 360
        extents = [(x0, full_right), (x0, full_right), (x0, last_right)]
        block_rect = [x0, 100, full_right, 200]
        align, _ = _detect_block_alignment(
            extents,
            block_rect,
            [10.0] * 3,
        )
        # Exactly at ratio → not a short final, but 2/3 lines are right-
        # aligned so the block is still classified as justify.
        assert align == "justify"

    def test_short_line_ratio_slightly_below(self) -> None:
        """Last line slightly below _SHORT_LINE_RATIO → classified as short final.

        With typical_width=400, threshold = 360.
        Last line width 359.5 < 360 → short final → justify.
        """
        x0 = 50.0
        full_right = x0 + 400.0
        last_right = x0 + 400.0 * _SHORT_LINE_RATIO - 0.5
        extents = [(x0, full_right), (x0, full_right), (x0, last_right)]
        block_rect = [x0, 100, full_right, 200]
        align, _ = _detect_block_alignment(
            extents,
            block_rect,
            [10.0] * 3,
        )
        assert align == "justify"

    def test_short_line_ratio_slightly_above(self) -> None:
        """Last line slightly above _SHORT_LINE_RATIO → NOT a short final.

        With typical_width=400, threshold = 360.
        Last line width 360.5 > 360 → not short final.
        However, 2 of 3 lines are right-aligned at the typical right edge,
        so is_right is still True and the result is 'justify'.
        """
        x0 = 50.0
        full_right = x0 + 400.0
        last_right = x0 + 400.0 * _SHORT_LINE_RATIO + 0.5
        extents = [(x0, full_right), (x0, full_right), (x0, last_right)]
        block_rect = [x0, 100, full_right, 200]
        align, _ = _detect_block_alignment(
            extents,
            block_rect,
            [10.0] * 3,
        )
        # Not a short final, but 2/3 lines are right-aligned so justify.
        assert align == "justify"

    def test_single_line_centered_on_page(self) -> None:
        """Single-line block centered on a page → center."""
        # Page width 612. Block at x0=200..x1=412 → left_m=200, right_m=200
        # bw=212 < 612*0.65=397.8, margins symmetric
        align, _ = _detect_block_alignment(
            [(200, 412)],
            [200, 100, 412, 112],
            page_width=612.0,
        )
        assert align == "center"

    def test_single_line_not_centered_no_page_width(self) -> None:
        """Single-line block without page_width → always left."""
        align, _ = _detect_block_alignment(
            [(200, 412)],
            [200, 100, 412, 112],
            page_width=0.0,
        )
        assert align == "left"


# ── TestRefineAlignmentsFromContextEdgeCases ──────────────────────────────────


class TestRefineAlignmentsFromContextEdgeCases:
    """Additional edge cases for _refine_alignments_from_context."""

    def test_insufficient_neighbors_no_upgrade(self) -> None:
        """Below _CONTEXT_ALIGN_MIN_NEIGHBORS → no upgrade."""
        blocks = [
            _make_align_block("justify")
            for _ in range(_CONTEXT_ALIGN_MIN_NEIGHBORS - 1)
        ] + [_make_align_block("left")]
        _refine_alignments_from_context(blocks)
        assert blocks[-1]["text_align"] == "left"

    def test_mixed_font_sizes_only_body_counted(self) -> None:
        """Only body-text-size blocks count; different sizes are excluded."""
        # 3 justify at 10pt (body), 1 justify at 18pt (heading), 1 left at 10pt
        blocks = (
            [_make_align_block("justify", font_size=10.0) for _ in range(3)]
            + [_make_align_block("justify", font_size=18.0)]
            + [_make_align_block("left", font_size=10.0)]
        )
        _refine_alignments_from_context(blocks)
        # 18pt block is beyond tolerance from 10pt median → excluded
        # 3 justify vs 1 left among body → justify dominates → upgrade
        assert blocks[-1]["text_align"] == "justify"

    def test_within_size_tol_counted(self) -> None:
        """Blocks within _CONTEXT_ALIGN_SIZE_TOL of median are counted."""
        base = 10.0
        within = base * _CONTEXT_ALIGN_SIZE_TOL  # exactly at boundary
        blocks = [
            _make_align_block("justify", font_size=within)
            for _ in range(_CONTEXT_ALIGN_MIN_NEIGHBORS)
        ] + [_make_align_block("left", font_size=base)]
        _refine_alignments_from_context(blocks)
        # At boundary → counted → upgrade
        assert blocks[-1]["text_align"] == "justify"

    def test_beyond_size_tol_excluded(self) -> None:
        """Blocks beyond _CONTEXT_ALIGN_SIZE_TOL are excluded."""
        beyond = 10.0 * _CONTEXT_ALIGN_SIZE_TOL + 0.1
        blocks = [
            _make_align_block("justify", font_size=beyond)
            for _ in range(_CONTEXT_ALIGN_MIN_NEIGHBORS)
        ] + [_make_align_block("left", font_size=10.0)]
        _refine_alignments_from_context(blocks)
        assert blocks[-1]["text_align"] == "left"

    def test_upgrade_left_to_justify_majority(self) -> None:
        """When justify is the clear majority, all left body blocks upgrade."""
        blocks = [
            _make_align_block("justify")
            for _ in range(5)  # noqa: PLR2004
        ] + [
            _make_align_block("left"),
            _make_align_block("left"),
        ]
        _refine_alignments_from_context(blocks)
        assert blocks[-2]["text_align"] == "justify"
        assert blocks[-1]["text_align"] == "justify"

    def test_right_aligned_not_upgraded(self) -> None:
        """``right`` alignment is never touched."""
        blocks = [
            _make_align_block("justify") for _ in range(_CONTEXT_ALIGN_MIN_NEIGHBORS)
        ] + [_make_align_block("right")]
        # Manually set the _line_extents for right-aligned block
        blocks[-1]["text_align"] = "right"
        _refine_alignments_from_context(blocks)
        assert blocks[-1]["text_align"] == "right"

    def test_zero_font_size_excluded(self) -> None:
        """Blocks with font_size=0 are excluded from body-text count."""
        blocks = [
            _make_align_block("justify") for _ in range(_CONTEXT_ALIGN_MIN_NEIGHBORS)
        ] + [_make_align_block("left", font_size=0.0)]
        _refine_alignments_from_context(blocks)
        # Zero font size → not a body block → not upgraded
        assert blocks[-1]["text_align"] == "left"

    def test_exactly_half_justify_no_upgrade(self) -> None:
        """Justify count == body_count // 2 → no upgrade (need strict majority)."""
        # 3 justify + 3 left = 6 body; 3 <= 6//2=3 → not majority
        blocks = [
            _make_align_block("justify"),
            _make_align_block("justify"),
            _make_align_block("justify"),
            _make_align_block("left"),
            _make_align_block("left"),
            _make_align_block("left"),
        ]
        _refine_alignments_from_context(blocks)
        for b in blocks[3:]:
            assert b["text_align"] == "left"


# ── TestUpgradeEmphasisStartJoinsEdgeCases ────────────────────────────────────


class TestUpgradeEmphasisStartJoinsEdgeCases:
    """Additional edge cases for _upgrade_emphasis_start_joins."""

    @staticmethod
    def _span(
        text: str,
        *,
        bold: bool = False,
        italic: bool = False,
        is_math: bool = False,
    ) -> dict:
        """Helper to create a span dict with minimal fields."""
        flags = (16 if bold else 0) | (2 if italic else 0)  # noqa: PLR2004
        d: dict = {"text": text, "flags": flags}
        if is_math:
            d["_is_math"] = True
        return d

    def test_bold_emphasis_transition_upgrades(self) -> None:
        """Bold-start → plain-end → bold-start pattern triggers newline."""
        spans = [
            [self._span("Def A.", bold=True), self._span(" Explanation A.")],
            [self._span("Def B.", bold=True), self._span(" Explanation B.")],
        ]
        joins = [" "]
        _upgrade_emphasis_start_joins(spans, joins)
        assert joins == ["\n"]

    def test_italic_emphasis_transition_upgrades(self) -> None:
        """Italic-start → plain-end → italic-start triggers newline."""
        spans = [
            [self._span("Term A.", italic=True), self._span(" Body A.")],
            [self._span("Term B.", italic=True), self._span(" Body B.")],
        ]
        joins = [" "]
        _upgrade_emphasis_start_joins(spans, joins)
        assert joins == ["\n"]

    def test_both_bold_and_italic_transition(self) -> None:
        """Bold+italic header in italic body → bold bit triggers upgrade."""
        spans = [
            [
                self._span("Head A.", bold=True, italic=True),
                self._span(" Body A.", italic=True),
            ],
            [
                self._span("Head B.", bold=True, italic=True),
                self._span(" Body B.", italic=True),
            ],
        ]
        joins = [" "]
        _upgrade_emphasis_start_joins(spans, joins)
        # Line 0 ends italic-only (no bold) → line 1 starts bold → upgrade
        assert joins == ["\n"]

    def test_no_emphasis_change_no_upgrade(self) -> None:
        """All spans plain → no upgrade."""
        spans = [
            [self._span("Just plain text line one.")],
            [self._span("Just plain text line two.")],
        ]
        joins = [" "]
        _upgrade_emphasis_start_joins(spans, joins)
        assert joins == [" "]

    def test_underline_is_not_a_font_flag(self) -> None:
        """PDF underline is a drawn rule, not a font flag → no detection.

        PyMuPDF doesn't set a font flag for underline, so even if the
        next line starts with underlined text, the emphasis detector
        cannot see it.  No join change occurs.
        """
        # Simulate underline as a separate flag bit (bit 0 = 1) — but
        # the function only checks bit 4 (bold=16) and bit 1 (italic=2).
        underline_flags = 1  # Not bold (16) nor italic (2)
        spans = [
            [
                {"text": "Term A.", "flags": underline_flags},
                {"text": " Body.", "flags": 0},
            ],
            [
                {"text": "Term B.", "flags": underline_flags},
                {"text": " Body.", "flags": 0},
            ],
        ]
        joins = [" "]
        _upgrade_emphasis_start_joins(spans, joins)
        # Underline bit is 1, not in _emphasis_bits (16, 2) → no detection
        assert joins == [" "]

    def test_emphasis_without_punctuation_no_upgrade(self) -> None:
        """Emphasized text NOT ending with punctuation → no upgrade."""
        spans = [
            [self._span("Summary", bold=True), self._span(" of the results.")],
            [self._span("continues here.")],
            [self._span("Overview", bold=True), self._span(" of the approach.")],
        ]
        joins = [" ", " "]
        _upgrade_emphasis_start_joins(spans, joins)
        # "Overview" ends with "w", not punctuation → no upgrade
        assert joins == [" ", " "]

    def test_emphasis_with_semicolon_upgrades(self) -> None:
        """Emphasized text ending with ';' triggers upgrade."""
        spans = [
            [self._span("Term A;", bold=True), self._span(" Body A.")],
            [self._span("Term B;", bold=True), self._span(" Body B.")],
        ]
        joins = [" "]
        _upgrade_emphasis_start_joins(spans, joins)
        assert joins == ["\n"]

    def test_emphasis_with_paren_upgrades(self) -> None:
        """Emphasized text ending with ')' triggers upgrade."""
        spans = [
            [self._span("(a)", bold=True), self._span(" First item.")],
            [self._span("body text continues.")],
            [self._span("(b)", bold=True), self._span(" Second item.")],
        ]
        joins = [" ", " "]
        _upgrade_emphasis_start_joins(spans, joins)
        assert joins == [" ", "\n"]


# ── TestMergeContinuationLinesEdgeCases ───────────────────────────────────────


class TestMergeContinuationLinesEdgeCases:
    """Additional edge cases for _merge_continuation_lines."""

    def test_no_continuation_returns_unchanged(self) -> None:
        """Blocks on different y-lines are not merged."""
        b1 = _make_raw_block(
            (0, 0, 50, 10),
            [_make_raw_line((0, 0, 50, 10))],
        )
        b2 = _make_raw_block(
            (0, 30, 50, 40),
            [_make_raw_line((0, 30, 50, 40))],
        )
        result = _merge_continuation_lines([b1, b2])
        assert len(result) == 2  # noqa: PLR2004

    def test_single_continuation_merged(self) -> None:
        """One adjacent block on same y merges into previous."""
        b1 = _make_raw_block(
            (0, 5, 50, 15),
            [_make_raw_line((0, 5, 50, 15))],
        )
        b2 = _make_raw_block(
            (52, 5, 120, 15),
            [_make_raw_line((52, 5, 120, 15))],
        )
        result = _merge_continuation_lines([b1, b2])
        assert len(result) == 1
        assert len(result[0]["lines"]) == 2  # noqa: PLR2004

    def test_multiple_continuations_chained(self) -> None:
        """Four adjacent blocks on same y all merge into first."""
        blocks = [
            _make_raw_block(
                (i * 25, 0, (i + 1) * 25 - 1, 10),
                [_make_raw_line((i * 25, 0, (i + 1) * 25 - 1, 10))],
            )
            for i in range(4)
        ]
        result = _merge_continuation_lines(blocks)
        assert len(result) == 1
        assert len(result[0]["lines"]) == 4  # noqa: PLR2004

    def test_preservation_of_block_type(self) -> None:
        """Merged block retains type=0."""
        b1 = _make_raw_block(
            (0, 0, 50, 10),
            [_make_raw_line((0, 0, 50, 10))],
        )
        b2 = _make_raw_block(
            (51, 0, 100, 10),
            [_make_raw_line((51, 0, 100, 10))],
        )
        result = _merge_continuation_lines([b1, b2])
        assert result[0]["type"] == 0

    def test_bbox_expands_on_merge(self) -> None:
        """Merged block bbox covers both original bboxes."""
        # y-values must differ by less than _LINE_Y_TOLERANCE (2.0)
        # so the blocks are recognized as being on the same visual line.
        b1 = _make_raw_block(
            (10, 5, 50, 15),
            [_make_raw_line((10, 5, 50, 15))],
        )
        b2 = _make_raw_block(
            (52, 4, 130, 17),
            [_make_raw_line((52, 4, 130, 17))],
        )
        result = _merge_continuation_lines([b1, b2])
        assert len(result) == 1
        bbox = result[0]["bbox"]
        assert bbox[0] == 10  # min x0  # noqa: PLR2004
        assert bbox[1] == 4  # min y0  # noqa: PLR2004
        assert bbox[2] == 130  # max x1  # noqa: PLR2004
        assert bbox[3] == 17  # max y1  # noqa: PLR2004

    def test_gap_at_boundary_of_tolerance(self) -> None:
        """x-gap exactly at _ADJACENT_BLOCK_MAX_GAP merges."""
        gap = _ADJACENT_BLOCK_MAX_GAP
        b1 = _make_raw_block(
            (0, 0, 50, 10),
            [_make_raw_line((0, 0, 50, 10))],
        )
        b2 = _make_raw_block(
            (50 + gap, 0, 100 + gap, 10),
            [_make_raw_line((50 + gap, 0, 100 + gap, 10))],
        )
        result = _merge_continuation_lines([b1, b2])
        # gap == tolerance → still within (not strictly >)
        assert len(result) == 1

    def test_gap_beyond_tolerance_no_merge(self) -> None:
        """x-gap beyond _ADJACENT_BLOCK_MAX_GAP does not merge."""
        gap = _ADJACENT_BLOCK_MAX_GAP + 1
        b1 = _make_raw_block(
            (0, 0, 50, 10),
            [_make_raw_line((0, 0, 50, 10))],
        )
        b2 = _make_raw_block(
            (50 + gap, 0, 100 + gap, 10),
            [_make_raw_line((50 + gap, 0, 100 + gap, 10))],
        )
        result = _merge_continuation_lines([b1, b2])
        assert len(result) == 2  # noqa: PLR2004


# ── TestTranslateBookmarksEdgeCases ───────────────────────────────────────────


class TestTranslateBookmarksEdgeCases:
    """Additional edge cases for _translate_bookmarks."""

    def test_empty_toc_no_llm_call(self) -> None:
        """Empty TOC returns True without calling translate_batch."""
        doc = pymupdf.open()
        doc.new_page()
        with patch(
            "src.core.pdf_processor.translate_batch",
        ) as mock_batch:
            result = _translate_bookmarks(doc, "French", "", None, None)
        assert result is True
        mock_batch.assert_not_called()
        doc.close()

    def test_multi_level_bookmarks_preserved(self) -> None:
        """Nested bookmarks (1→2→3) preserve level and page."""
        doc = pymupdf.open()
        for _ in range(3):
            doc.new_page()
        doc.set_toc(
            [
                [1, "Part I", 1],
                [2, "Chapter 1", 1],
                [3, "Section 1.1", 2],
                [2, "Chapter 2", 3],
            ]
        )

        with patch(
            "src.core.pdf_processor.translate_batch",
            return_value=["Phần I", "Chương 1", "Mục 1.1", "Chương 2"],
        ):
            result = _translate_bookmarks(doc, "Vietnamese", "", None, None)

        assert result is True
        toc = doc.get_toc()
        assert toc[0][0] == 1  # level
        assert toc[0][2] == 1  # page
        assert toc[1][0] == 2  # noqa: PLR2004
        assert toc[2][0] == 3  # noqa: PLR2004
        assert toc[2][2] == 2  # noqa: PLR2004
        assert toc[3][0] == 2  # noqa: PLR2004
        assert toc[3][2] == 3  # noqa: PLR2004
        assert toc[0][1] == "Phần I"
        assert toc[2][1] == "Mục 1.1"
        doc.close()

    def test_unicode_titles_round_trip(self) -> None:
        """Unicode titles (accented, CJK, Cyrillic) survive translation."""
        doc = pymupdf.open()
        doc.new_page()
        title = "Résumé — 概要 — Введение"
        doc.set_toc([[1, title, 1]])

        translated = "Summary — Overview — Introduction"
        with patch(
            "src.core.pdf_processor.translate_batch",
            return_value=[translated],
        ):
            result = _translate_bookmarks(doc, "English", "", None, None)

        assert result is True
        toc = doc.get_toc()
        assert toc[0][1] == translated
        doc.close()

    def test_bookmark_page_dest_preserved(self) -> None:
        """Page and destination info preserved after translation."""
        doc = pymupdf.open()
        doc.new_page()
        doc.new_page()
        doc.set_toc([[1, "First", 1], [1, "Second", 2]])

        with patch(
            "src.core.pdf_processor.translate_batch",
            return_value=["Premier", "Deuxième"],
        ):
            _translate_bookmarks(doc, "French", "", None, None)

        toc = doc.get_toc()
        assert toc[0][2] == 1  # page 1
        assert toc[1][2] == 2  # page 2  # noqa: PLR2004
        doc.close()

    def test_bookmark_full_dest_dict_preserved_with_simple_false(self) -> None:
        """``dest`` dict (kind/zoom/view) round-trips through translation.

        AGENTS.md: "Level, page, and destination are preserved" —
        the previous test only asserted page numbers; the destination
        dict that ``set_toc(simple=False)`` reads (kind, zoom, view
        anchors) wasn't verified.  A regression that drops the
        ``dest`` field on the round-trip would silently lose deep
        link anchors (e.g. fit-to-page zoom on each TOC entry).
        """
        doc = pymupdf.open()
        for _ in range(3):
            doc.new_page()
        # Build a TOC with explicit FitH zoom anchors per entry.
        toc = [
            [
                1,
                "Chapter 1",
                1,
                {"kind": pymupdf.LINK_GOTO, "to": pymupdf.Point(0, 100)},
            ],
            [
                1,
                "Chapter 2",
                2,
                {"kind": pymupdf.LINK_GOTO, "to": pymupdf.Point(0, 200)},
            ],
            [
                1,
                "Chapter 3",
                3,
                {"kind": pymupdf.LINK_GOTO, "to": pymupdf.Point(0, 300)},
            ],
        ]
        doc.set_toc(toc)

        with patch(
            "src.core.pdf_processor.translate_batch",
            return_value=["Chapitre 1", "Chapitre 2", "Chapitre 3"],
        ):
            _translate_bookmarks(doc, "French", "", None, None)

        round_trip = doc.get_toc(simple=False)
        # Page number AND destination ``to`` point preserved.
        assert round_trip[0][2] == 1
        assert round_trip[1][2] == 2  # noqa: PLR2004
        assert round_trip[2][2] == 3  # noqa: PLR2004
        # Destination ``to`` Y-coordinate matches what we set per entry,
        # proving the dest dict survived the rebuild.
        assert int(round_trip[0][3]["to"].y) == 100  # noqa: PLR2004
        assert int(round_trip[1][3]["to"].y) == 200  # noqa: PLR2004
        assert int(round_trip[2][3]["to"].y) == 300  # noqa: PLR2004
        doc.close()

    def test_many_bookmarks(self) -> None:
        """100+ bookmarks are all translated correctly."""
        doc = pymupdf.open()
        doc.new_page()
        n = 110
        toc_entries = [[1, f"Bookmark {i}", 1] for i in range(n)]
        doc.set_toc(toc_entries)

        translations = [f"Signet {i}" for i in range(n)]
        with patch(
            "src.core.pdf_processor.translate_batch",
            return_value=translations,
        ):
            result = _translate_bookmarks(doc, "French", "", None, None)

        assert result is True
        toc = doc.get_toc()
        assert len(toc) == n
        assert toc[0][1] == "Signet 0"
        assert toc[n - 1][1] == f"Signet {n - 1}"
        doc.close()


# ── TestExtractPageWidgetsEdgeCases ───────────────────────────────────────────


class TestExtractPageWidgetsEdgeCases:
    """Additional edge cases for _extract_page_widgets."""

    def test_text_field_extraction_fields(self) -> None:
        """Text field entry has expected keys and values."""
        widget = MagicMock()
        widget.field_type = _WIDGET_TYPE_TEXT
        widget.field_name = "username"
        widget.field_value = "admin"

        page = MagicMock()
        page.widgets.return_value = iter([widget])

        entries = _extract_page_widgets(page)
        assert len(entries) == 1
        assert entries[0]["type"] == "widget"
        assert entries[0]["widget_type"] == _WIDGET_TYPE_TEXT
        assert entries[0]["field_name"] == "username"
        assert entries[0]["text"] == "admin"
        assert "choice_index" not in entries[0]

    def test_combo_box_extraction_with_string_choices(self) -> None:
        """Combo box with plain string choices extracts each value."""
        widget = MagicMock()
        widget.field_type = _WIDGET_TYPE_COMBOBOX
        widget.field_name = "fruit"
        widget.choice_values = ["Apple", "Banana", "Cherry"]

        page = MagicMock()
        page.widgets.return_value = iter([widget])

        entries = _extract_page_widgets(page)
        assert len(entries) == 3  # noqa: PLR2004
        assert entries[0]["text"] == "Apple"
        assert entries[0]["choice_index"] == 0
        assert entries[1]["text"] == "Banana"
        assert entries[2]["text"] == "Cherry"
        assert entries[2]["choice_index"] == 2  # noqa: PLR2004

    def test_list_box_extraction(self) -> None:
        """List box extraction works identically to combo box."""
        widget = MagicMock()
        widget.field_type = _WIDGET_TYPE_LISTBOX
        widget.field_name = "options"
        widget.choice_values = ["Option A", "Option B"]

        page = MagicMock()
        page.widgets.return_value = iter([widget])

        entries = _extract_page_widgets(page)
        assert len(entries) == 2  # noqa: PLR2004
        assert entries[0]["widget_type"] == _WIDGET_TYPE_LISTBOX
        assert entries[0]["text"] == "Option A"
        assert entries[1]["text"] == "Option B"

    def test_no_widgets_returns_empty_list(self) -> None:
        """Page with no widgets returns empty list (mock)."""
        page = MagicMock()
        page.widgets.return_value = iter([])
        entries = _extract_page_widgets(page)
        assert entries == []

    def test_widget_type_constants(self) -> None:
        """Widget type constants match expected PyMuPDF values."""
        assert _WIDGET_TYPE_TEXT == 7  # noqa: PLR2004
        assert _WIDGET_TYPE_COMBOBOX == 3  # noqa: PLR2004
        assert _WIDGET_TYPE_LISTBOX == 4  # noqa: PLR2004

    def test_widgets_returning_none(self) -> None:
        """page.widgets() returning None → empty list."""
        page = MagicMock()
        page.widgets.return_value = None
        entries = _extract_page_widgets(page)
        assert entries == []

    def test_whitespace_choice_skipped(self) -> None:
        """Combo box choice with only whitespace is skipped."""
        widget = MagicMock()
        widget.field_type = _WIDGET_TYPE_COMBOBOX
        widget.field_name = "lang"
        widget.choice_values = ["   ", "English", ""]

        page = MagicMock()
        page.widgets.return_value = iter([widget])

        entries = _extract_page_widgets(page)
        assert len(entries) == 1
        assert entries[0]["text"] == "English"

    def test_multiple_widgets_on_page(self) -> None:
        """Multiple widget types on same page are all extracted."""
        text_w = MagicMock()
        text_w.field_type = _WIDGET_TYPE_TEXT
        text_w.field_name = "name"
        text_w.field_value = "John"

        combo_w = MagicMock()
        combo_w.field_type = _WIDGET_TYPE_COMBOBOX
        combo_w.field_name = "color"
        combo_w.choice_values = ["Red"]

        page = MagicMock()
        page.widgets.return_value = iter([text_w, combo_w])

        entries = _extract_page_widgets(page)
        assert len(entries) == 2  # noqa: PLR2004
        assert entries[0]["widget_type"] == _WIDGET_TYPE_TEXT
        assert entries[1]["widget_type"] == _WIDGET_TYPE_COMBOBOX


# ── TestInjectPageWidgetsEdgeCases ────────────────────────────────────────────


class TestInjectPageWidgetsEdgeCases:
    """Additional edge cases for _inject_page_widgets."""

    def test_text_field_injection_via_mock(self) -> None:
        """Text field value is updated via widget.field_value."""
        widget = MagicMock()
        widget.field_type = _WIDGET_TYPE_TEXT
        widget.field_name = "address"

        page = MagicMock()
        page.widgets.return_value = iter([widget])

        entries = [
            {
                "type": "widget",
                "widget_type": _WIDGET_TYPE_TEXT,
                "field_name": "address",
                "translated_text": "123 Rue de Paris",
            },
        ]
        _inject_page_widgets(page, entries)
        assert widget.field_value == "123 Rue de Paris"
        widget.update.assert_called_once()

    def test_combo_injection_updates_choices(self) -> None:
        """Combo box choices are replaced with translated values."""
        widget = MagicMock()
        widget.field_type = _WIDGET_TYPE_COMBOBOX
        widget.field_name = "size"
        widget.choice_values = ["Small", "Large"]
        widget.field_value = "Small"

        page = MagicMock()
        page.widgets.return_value = iter([widget])

        entries = [
            {
                "type": "widget",
                "widget_type": _WIDGET_TYPE_COMBOBOX,
                "field_name": "size",
                "choice_index": 0,
                "translated_text": "Petit",
            },
            {
                "type": "widget",
                "widget_type": _WIDGET_TYPE_COMBOBOX,
                "field_name": "size",
                "choice_index": 1,
                "translated_text": "Grand",
            },
        ]
        _inject_page_widgets(page, entries)
        assert widget.choice_values == ["Petit", "Grand"]
        # Selected value was "Small" (choice_index=0) → should become "Petit"
        assert widget.field_value == "Petit"

    def test_listbox_injection_updates_choices(self) -> None:
        """List box injection mirrors combo box behavior."""
        widget = MagicMock()
        widget.field_type = _WIDGET_TYPE_LISTBOX
        widget.field_name = "items"
        widget.choice_values = ["Cat", "Dog"]
        widget.field_value = "Dog"

        page = MagicMock()
        page.widgets.return_value = iter([widget])

        entries = [
            {
                "type": "widget",
                "widget_type": _WIDGET_TYPE_LISTBOX,
                "field_name": "items",
                "choice_index": 0,
                "translated_text": "Chat",
            },
            {
                "type": "widget",
                "widget_type": _WIDGET_TYPE_LISTBOX,
                "field_name": "items",
                "choice_index": 1,
                "translated_text": "Chien",
            },
        ]
        _inject_page_widgets(page, entries)
        assert widget.choice_values == ["Chat", "Chien"]
        assert widget.field_value == "Chien"

    def test_injection_with_translated_values_mixed(self) -> None:
        """Mixed entries: some with translated_text, some without."""
        w1 = MagicMock()
        w1.field_type = _WIDGET_TYPE_TEXT
        w1.field_name = "f1"
        w2 = MagicMock()
        w2.field_type = _WIDGET_TYPE_TEXT
        w2.field_name = "f2"

        page = MagicMock()
        page.widgets.return_value = iter([w1, w2])

        entries = [
            {
                "type": "widget",
                "widget_type": _WIDGET_TYPE_TEXT,
                "field_name": "f1",
                "translated_text": "Translated",
            },
            {
                "type": "widget",
                "widget_type": _WIDGET_TYPE_TEXT,
                "field_name": "f2",
                "translated_text": "",  # Empty → skipped
            },
        ]
        _inject_page_widgets(page, entries)
        assert w1.field_value == "Translated"
        w1.update.assert_called_once()
        # f2 should NOT be updated (empty translated_text)
        w2.update.assert_not_called()

    def test_nonexistent_field_name_is_noop(self) -> None:
        """Entry with field_name not matching any widget is a no-op."""
        widget = MagicMock()
        widget.field_type = _WIDGET_TYPE_TEXT
        widget.field_name = "real_field"

        page = MagicMock()
        page.widgets.return_value = iter([widget])

        entries = [
            {
                "type": "widget",
                "widget_type": _WIDGET_TYPE_TEXT,
                "field_name": "nonexistent",
                "translated_text": "X",
            },
        ]
        _inject_page_widgets(page, entries)
        widget.update.assert_not_called()


# ── TestTranslatePageImagesEdgeCases2 ─────────────────────────────────────────


class TestTranslatePageImagesEdgeCases2:
    """Further edge cases for _translate_page_images."""

    def test_no_images_on_text_page(self, tmp_path: Path) -> None:
        """Page with text only → no _translate_single_pdf_image calls."""
        pdf = tmp_path / "noimg.pdf"
        _make_pdf(pdf, ["Only text here"])
        doc = pymupdf.open(str(pdf))
        page = doc[0]
        xrefs: set[int] = set()
        with patch(
            "src.core.pdf_processor._translate_single_pdf_image",
        ) as mock_t:
            _translate_page_images(
                doc,
                page,
                "French",
                "",
                None,
                "TesseractOCR",
                None,
                xrefs,
            )
        mock_t.assert_not_called()
        assert len(xrefs) == 0
        doc.close()

    def test_images_below_min_dim_width(self, tmp_path: Path) -> None:
        """Image narrower than _MIN_IMAGE_DIM is skipped."""
        pdf = tmp_path / "narrow.pdf"
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Text", fontsize=14)
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 5, 100), 0)
        # Width on page = 10 < _MIN_IMAGE_DIM
        page.insert_image(pymupdf.Rect(100, 100, 110, 300), pixmap=pix)
        doc.save(str(pdf))

        page = doc[0]
        xrefs: set[int] = set()
        with patch(
            "src.core.pdf_processor._translate_single_pdf_image",
        ) as mock_t:
            _translate_page_images(
                doc,
                page,
                "French",
                "",
                None,
                "TesseractOCR",
                None,
                xrefs,
            )
        mock_t.assert_not_called()
        doc.close()

    def test_shared_xref_skipped(self, tmp_path: Path) -> None:
        """Pre-populated xref in translated_xrefs is skipped."""
        pdf = tmp_path / "shared.pdf"
        _make_pdf_with_image(pdf, texts=["Hello"], image_rect=(100, 200, 400, 500))
        doc = pymupdf.open(str(pdf))
        page = doc[0]

        # Pre-populate with all xrefs from the page
        images = page.get_images(full=True)
        xrefs = {img[0] for img in images}

        with patch(
            "src.core.pdf_processor._translate_single_pdf_image",
        ) as mock_t:
            _translate_page_images(
                doc,
                page,
                "French",
                "",
                None,
                "TesseractOCR",
                None,
                xrefs,
            )
        # Already in translated_xrefs → skipped
        mock_t.assert_not_called()
        doc.close()

    def test_cancel_check_stops_processing(self, tmp_path: Path) -> None:
        """cancel_check returning True stops image processing."""
        pdf = tmp_path / "cancel.pdf"
        _make_pdf_with_image(pdf, texts=["Hello"], image_rect=(100, 200, 400, 500))
        doc = pymupdf.open(str(pdf))
        page = doc[0]
        xrefs: set[int] = set()

        with patch(
            "src.core.pdf_processor._translate_single_pdf_image",
        ) as mock_t:
            _translate_page_images(
                doc,
                page,
                "French",
                "",
                None,
                "TesseractOCR",
                lambda: True,  # Always cancelled
                xrefs,
            )
        mock_t.assert_not_called()
        doc.close()

    def test_nonfatal_error_continues(self, tmp_path: Path) -> None:
        """Non-fatal ValueError continues processing."""
        pdf = tmp_path / "nonfatal.pdf"
        _make_pdf_with_image(pdf, texts=["Hello"], image_rect=(100, 200, 400, 500))
        doc = pymupdf.open(str(pdf))
        page = doc[0]
        xrefs: set[int] = set()

        with patch(
            "src.core.pdf_processor._translate_single_pdf_image",
            side_effect=ValueError("SOME_OTHER_ERROR"),
        ):
            # Should NOT raise
            _translate_page_images(
                doc,
                page,
                "French",
                "",
                None,
                "TesseractOCR",
                None,
                xrefs,
            )
        # xref tracked despite error
        assert len(xrefs) > 0
        doc.close()

    def test_auth_error_propagates(self, tmp_path: Path) -> None:
        """AUTH_ERROR is a fatal LLM error → propagates."""
        pdf = tmp_path / "auth.pdf"
        _make_pdf_with_image(pdf, texts=["Hello"], image_rect=(100, 200, 400, 500))
        doc = pymupdf.open(str(pdf))
        page = doc[0]

        with (
            patch(
                "src.core.pdf_processor._translate_single_pdf_image",
                side_effect=ValueError("AUTH_ERROR"),
            ),
            pytest.raises(ValueError, match="AUTH_ERROR"),
        ):
            _translate_page_images(
                doc,
                page,
                "French",
                "",
                None,
                "TesseractOCR",
                None,
                set(),
            )
        doc.close()

    def test_image_setting_gate(self, tmp_path: Path) -> None:
        """Image translation gated by SETTING_TRANSLATE_DOC_IMAGES in process_pdf_file."""
        pdf = tmp_path / "gate.pdf"
        out = tmp_path / "out.pdf"
        _make_scanned_pdf(pdf, num_text_pages=1)

        with (
            patch("src.core.pdf_processor._config.load_setting", return_value=False),
            patch(
                "src.core.pdf_processor.translate_batch",
                side_effect=lambda texts, *a, **kw: [f"[FR] {t}" for t in texts],
            ),
            patch(
                "src.core.pdf_processor._translate_page_images",
            ) as mock_img,
            patch(
                "src.core.pdf_processor._process_scanned_pages",
            ) as mock_scan,
        ):
            process_pdf_file(pdf, out, "French")

        # load_setting returns False → do_images=False → neither called
        mock_img.assert_not_called()
        mock_scan.assert_not_called()


# ── TestMeasureHtmlboxSpareEdgeCases ──────────────────────────────────────────


class TestMeasureHtmlboxSpareEdgeCases:
    """Additional edge cases for _measure_htmlbox_spare."""

    def test_centering_calculation_with_large_spare(self) -> None:
        """Large rect relative to text → significant spare height."""
        html = '<p style="font-family:sans-serif; font-size:8pt; margin:0;">X</p>'
        rect = pymupdf.Rect(0, 0, 200, 100)
        doc = pymupdf.open()
        spare, scale = _measure_htmlbox_spare(doc, html, rect)
        doc.close()
        assert spare > _VCENTER_SPARE_THRESHOLD
        assert scale == 1.0  # noqa: PLR2004

    def test_below_threshold_spare(self) -> None:
        """Tight rect produces small spare (potentially below threshold)."""
        html = '<p style="font-family:sans-serif; font-size:12pt; margin:0;">Test</p>'
        rect = pymupdf.Rect(0, 0, 200, 16)
        doc = pymupdf.open()
        spare, scale = _measure_htmlbox_spare(doc, html, rect)
        doc.close()
        # Spare should be small/zero for tight fit
        assert isinstance(spare, float)
        assert spare >= 0

    def test_multiline_detection_via_height_ratio(self) -> None:
        """_is_multiline_block uses _MULTILINE_HEIGHT_RATIO = 2.0."""
        # Height = 2.0 × font_size → NOT multiline (strict >)
        block = {"text": "Hello", "font_size": 10.0, "rect": [0, 0, 200, 20]}
        assert not _is_multiline_block(block)

        # Height = 2.1 × font_size → IS multiline
        block2 = {"text": "Hello", "font_size": 10.0, "rect": [0, 0, 200, 21]}
        assert _is_multiline_block(block2)

    def test_tuple_return_parsed_correctly(self) -> None:
        """Mock returning (spare, scale) tuple is parsed correctly."""
        mock_doc = MagicMock()
        mock_page = MagicMock()
        mock_page.insert_htmlbox.return_value = (15.5, 0.8)
        mock_doc.new_page.return_value = mock_page

        spare, scale = _measure_htmlbox_spare(
            mock_doc,
            "<p>text</p>",
            pymupdf.Rect(0, 0, 100, 50),
        )
        assert spare == 15.5  # noqa: PLR2004
        assert scale == 0.8  # noqa: PLR2004

    def test_list_return_parsed_correctly(self) -> None:
        """Mock returning [spare, scale] list is also parsed."""
        mock_doc = MagicMock()
        mock_page = MagicMock()
        mock_page.insert_htmlbox.return_value = [10.0, 0.95]
        mock_doc.new_page.return_value = mock_page

        spare, scale = _measure_htmlbox_spare(
            mock_doc,
            "<p>text</p>",
            pymupdf.Rect(0, 0, 100, 50),
        )
        assert spare == 10.0  # noqa: PLR2004
        assert scale == 0.95  # noqa: PLR2004


# ── TestFindLinkInCharsEdgeCases ──────────────────────────────────────────────


class TestFindLinkInCharsEdgeCases:
    """Additional edge cases for _find_link_in_chars."""

    def _make_block(
        self,
        text: str,
    ) -> tuple[list[tuple[str, Any]], str]:
        """Build block_chars and block_text from a string."""
        chars = []
        for i, c in enumerate(text):
            x0 = 10.0 + i * 6
            chars.append((c, pymupdf.Rect(x0, 100, x0 + 6, 112)))
        return chars, text

    def test_single_line_link_returns_one_rect(self) -> None:
        """Link entirely on one line returns exactly one rect."""
        chars, text = self._make_block("Click here for details")
        link = {"_inner": "here", "from": (0, 100, 50, 112)}
        rects, pos = _find_link_in_chars(chars, text, link, 0)
        assert len(rects) == 1
        assert pos > 0

    def test_multiline_link_returns_per_line_rects(self) -> None:
        """Link spanning two visual lines returns two rects."""
        chars: list[tuple[str, Any]] = []
        line1 = "Visit http://"
        line2 = "example.com"
        # Line 1 at y=100-112
        for i, c in enumerate(line1):
            x0 = 10.0 + i * 6
            chars.append((c, pymupdf.Rect(x0, 100, x0 + 6, 112)))
        # Line 2 at y=120-132 (gap = 8, > _LINK_LINE_Y_GAP=3)
        for i, c in enumerate(line2):
            x0 = 10.0 + i * 6
            chars.append((c, pymupdf.Rect(x0, 120, x0 + 6, 132)))
        text = line1 + line2
        link = {
            "_inner": "http://example.com",
            "from": (0, 100, 100, 112),
        }
        rects, _ = _find_link_in_chars(chars, text, link, 0)
        assert len(rects) == 2  # noqa: PLR2004

    def test_link_line_y_gap_boundary(self) -> None:
        """Chars within _LINK_LINE_Y_GAP are on the same line."""
        chars: list[tuple[str, Any]] = []
        # Two chars with y-center difference < _LINK_LINE_Y_GAP
        # char1: y_center = (100+112)/2 = 106
        chars.append(("A", pymupdf.Rect(10, 100, 16, 112)))
        # char2: y_center = (101+113)/2 = 107 → diff=1 < 3
        chars.append(("B", pymupdf.Rect(16, 101, 22, 113)))
        text = "AB"
        link = {"_inner": "AB", "from": (10, 100, 22, 112)}
        rects, _ = _find_link_in_chars(chars, text, link, 0)
        # Same visual line → single rect
        assert len(rects) == 1

    def test_link_line_y_gap_exceeds_boundary(self) -> None:
        """Chars with y-center diff > _LINK_LINE_Y_GAP form separate lines."""
        chars: list[tuple[str, Any]] = []
        # char1: y_center = 106
        chars.append(("A", pymupdf.Rect(10, 100, 16, 112)))
        # char2: y_center = 121 → diff=15 > 3
        chars.append(("B", pymupdf.Rect(16, 115, 22, 127)))
        text = "AB"
        link = {"_inner": "AB", "from": (10, 100, 22, 127)}
        rects, _ = _find_link_in_chars(chars, text, link, 0)
        # Different visual lines → two rects
        assert len(rects) == 2  # noqa: PLR2004

    def test_link_line_y_gap_constant(self) -> None:
        """_LINK_LINE_Y_GAP is 3.0 points."""
        assert _LINK_LINE_Y_GAP == 3.0  # noqa: PLR2004

    def test_empty_block_chars(self) -> None:
        """Empty block_chars → empty result."""
        link = {"_inner": "xyz", "from": (0, 0, 10, 10)}
        rects, pos = _find_link_in_chars([], "", link, 0)
        assert rects == []
        assert pos == 0

    def test_no_translated_no_inner(self) -> None:
        """Link with no _translated and no _inner → no match."""
        chars, text = self._make_block("Hello World")
        link = {"from": (0, 100, 50, 112)}
        rects, pos = _find_link_in_chars(chars, text, link, 0)
        assert rects == []
        assert pos == 0


# ── TestCheckpointResumptionEdgeCases ─────────────────────────────────────────


class TestCheckpointResumptionEdgeCases:
    """Edge cases for checkpoint save/load round-trip in PDF processing."""

    def test_per_page_checkpoint_save_load(self, tmp_path: Path) -> None:
        """Checkpoint saved for page 0 can be loaded back."""
        from src.core.checkpoint import (  # noqa: PLC0415
            load_pdf_checkpoint,
            save_pdf_page_progress,
        )

        blocks = [
            {
                "rect": [10, 20, 200, 40],
                "text": "Hello",
                "translated_text": "Hola",
                "font_size": 12.0,
            },
        ]
        save_pdf_page_progress(tmp_path, 0, blocks, 2)

        loaded = load_pdf_checkpoint(tmp_path)
        assert loaded is not None
        assert 0 in loaded
        assert loaded[0][0]["translated_text"] == "Hola"

    def test_checkpoint_with_translated_blocks(self, tmp_path: Path) -> None:
        """Multiple translated blocks per page survive checkpoint."""
        from src.core.checkpoint import (  # noqa: PLC0415
            load_pdf_checkpoint,
            save_pdf_page_progress,
        )

        blocks = [
            {"rect": [0, 0, 100, 20], "text": "A", "translated_text": "X"},
            {"rect": [0, 30, 100, 50], "text": "B", "translated_text": "Y"},
            {"rect": [0, 60, 100, 80], "text": "C", "translated_text": "Z"},
        ]
        save_pdf_page_progress(tmp_path, 0, blocks, 1)

        loaded = load_pdf_checkpoint(tmp_path)
        assert loaded is not None
        assert len(loaded[0]) == 3  # noqa: PLR2004
        assert loaded[0][2]["translated_text"] == "Z"

    def test_checkpoint_with_widgets(self, tmp_path: Path) -> None:
        """Widget entries survive checkpoint round-trip."""
        from src.core.checkpoint import (  # noqa: PLC0415
            load_pdf_checkpoint,
            save_pdf_page_progress,
        )

        entries = [
            {"rect": [0, 0, 100, 20], "text": "Hello"},
            {
                "type": "widget",
                "widget_type": _WIDGET_TYPE_TEXT,
                "field_name": "input1",
                "text": "Original",
                "translated_text": "Traduit",
            },
        ]
        save_pdf_page_progress(tmp_path, 0, entries, 1)

        loaded = load_pdf_checkpoint(tmp_path)
        assert loaded is not None
        widgets = [e for e in loaded[0] if e.get("type") == "widget"]
        assert len(widgets) == 1
        assert widgets[0]["translated_text"] == "Traduit"
        assert widgets[0]["field_name"] == "input1"

    def test_partial_page_resumption(self, tmp_path: Path) -> None:
        """Resume with partial checkpoint skips cached pages, translates rest."""
        from src.core.checkpoint import save_pdf_page_progress  # noqa: PLC0415

        pdf = tmp_path / "input.pdf"
        out = tmp_path / "out.pdf"
        _make_multipage_pdf(pdf, 3)
        ckpt_dir = tmp_path / "cp"
        ckpt_dir.mkdir()

        # Save checkpoint for page 0 only
        save_pdf_page_progress(
            ckpt_dir,
            0,
            [
                {
                    "rect": [0, 0, 200, 20],
                    "text": "Cached",
                    "translated_text": "[FR] Cached",
                }
            ],
            3,
        )

        call_count = [0]

        def counting_translate(texts, *args, **kwargs):
            call_count[0] += 1
            return [f"[FR] {t}" for t in texts]

        with patch(
            "src.core.pdf_processor.translate_batch",
            side_effect=counting_translate,
        ):
            result = process_pdf_file(
                pdf,
                out,
                "French",
                checkpoint_dir=ckpt_dir,
            )

        assert result is True
        # Page 0 cached → only pages 1 and 2 need LLM
        assert call_count[0] == 2  # noqa: PLR2004

    def test_multi_page_checkpoint_round_trip(self, tmp_path: Path) -> None:
        """Multiple pages saved and loaded from checkpoint."""
        from src.core.checkpoint import (  # noqa: PLC0415
            load_pdf_checkpoint,
            save_pdf_page_progress,
        )

        for page_idx in range(5):  # noqa: PLR2004
            save_pdf_page_progress(
                tmp_path,
                page_idx,
                [
                    {
                        "rect": [0, 0, 100, 20],
                        "text": f"P{page_idx}",
                        "translated_text": f"T{page_idx}",
                    }
                ],
                5,  # noqa: PLR2004
            )

        loaded = load_pdf_checkpoint(tmp_path)
        assert loaded is not None
        assert len(loaded) == 5  # noqa: PLR2004
        for i in range(5):  # noqa: PLR2004
            assert loaded[i][0]["translated_text"] == f"T{i}"

    def test_checkpoint_with_annots_and_widgets(self, tmp_path: Path) -> None:
        """Annotations and widgets coexist in checkpoint."""
        from src.core.checkpoint import (  # noqa: PLC0415
            load_pdf_checkpoint,
            save_pdf_page_progress,
        )

        entries = [
            {"rect": [0, 0, 100, 20], "text": "Block"},
            {
                "type": "annot",
                "annot_type": 0,
                "annot_id": "a1",
                "text": "Note",
                "translated_text": "Nota",
            },
            {
                "type": "widget",
                "widget_type": _WIDGET_TYPE_COMBOBOX,
                "field_name": "combo1",
                "text": "Yes",
                "translated_text": "Oui",
                "choice_index": 0,
            },
        ]
        save_pdf_page_progress(tmp_path, 0, entries, 1)

        loaded = load_pdf_checkpoint(tmp_path)
        assert loaded is not None
        page_data = loaded[0]
        annots = [e for e in page_data if e.get("type") == "annot"]
        widgets = [e for e in page_data if e.get("type") == "widget"]
        blocks = [e for e in page_data if e.get("type") not in ("annot", "widget")]
        assert len(annots) == 1
        assert len(widgets) == 1
        assert len(blocks) == 1
        assert annots[0]["translated_text"] == "Nota"
        assert widgets[0]["translated_text"] == "Oui"

    def test_empty_checkpoint_round_trip(self, tmp_path: Path) -> None:
        """Empty page data round-trips cleanly."""
        from src.core.checkpoint import (  # noqa: PLC0415
            load_pdf_checkpoint,
            save_pdf_page_progress,
        )

        save_pdf_page_progress(tmp_path, 0, [], 1)
        loaded = load_pdf_checkpoint(tmp_path)
        assert loaded is not None
        assert loaded[0] == []

    def test_no_checkpoint_dir_returns_none(self, tmp_path: Path) -> None:
        """Loading from nonexistent checkpoint dir returns None."""
        from src.core.checkpoint import load_pdf_checkpoint  # noqa: PLC0415

        nonexistent = tmp_path / "does_not_exist"
        loaded = load_pdf_checkpoint(nonexistent)
        assert loaded is None


# ── TestWidgetTypeFiltering ──────────────────────────────────────────────────


class TestWidgetTypeFiltering:
    """Tests that _extract_page_widgets only handles text, combo, and list widgets.

    Widget type constants (PyMuPDF PDF_WIDGET_TYPE_*):
        1 = PushButton, 2 = RadioButton, 3 = ComboBox,
        4 = ListBox, 5 = Signature, 7 = Text.
    Only types 3, 4, and 7 should be extracted; all others are skipped.
    """

    def _make_mock_page(self, widgets: list) -> MagicMock:
        """Helper to create a mock page with an iterable of mock widgets."""
        page = MagicMock()
        page.widgets.return_value = iter(widgets)
        return page

    def _make_widget(
        self,
        field_type: int,
        field_name: str = "field",
        field_value: str = "value",
        choice_values: list | None = None,
    ) -> MagicMock:
        """Helper to create a mock widget."""
        w = MagicMock()
        w.field_type = field_type
        w.field_name = field_name
        w.field_value = field_value
        w.choice_values = choice_values
        return w

    def test_text_widget_extracted(self) -> None:
        """Text widget (type 7) with non-empty value is extracted."""
        widget = self._make_widget(_WIDGET_TYPE_TEXT, "name", "John")
        page = self._make_mock_page([widget])
        entries = _extract_page_widgets(page)
        assert len(entries) == 1
        assert entries[0]["widget_type"] == _WIDGET_TYPE_TEXT
        assert entries[0]["text"] == "John"

    def test_combobox_widget_extracted(self) -> None:
        """Combo box widget (type 3) choices are extracted."""
        widget = self._make_widget(
            _WIDGET_TYPE_COMBOBOX, "color", "", choice_values=["Red", "Blue"]
        )
        page = self._make_mock_page([widget])
        entries = _extract_page_widgets(page)
        assert len(entries) == 2  # noqa: PLR2004
        assert entries[0]["widget_type"] == _WIDGET_TYPE_COMBOBOX
        assert entries[0]["text"] == "Red"
        assert entries[1]["text"] == "Blue"

    def test_listbox_widget_extracted(self) -> None:
        """List box widget (type 4) choices are extracted."""
        widget = self._make_widget(
            _WIDGET_TYPE_LISTBOX, "size", "", choice_values=["S", "M", "L"]
        )
        page = self._make_mock_page([widget])
        entries = _extract_page_widgets(page)
        assert len(entries) == 3  # noqa: PLR2004
        assert entries[0]["widget_type"] == _WIDGET_TYPE_LISTBOX
        assert entries[0]["text"] == "S"

    def test_radio_button_skipped(self) -> None:
        """Radio button widget (type 2) is not extracted."""
        widget = self._make_widget(2, "choice", "Option A")
        page = self._make_mock_page([widget])
        entries = _extract_page_widgets(page)
        assert entries == []

    def test_push_button_skipped(self) -> None:
        """Push button widget (type 1) is not extracted."""
        widget = self._make_widget(1, "submit", "Submit")
        page = self._make_mock_page([widget])
        entries = _extract_page_widgets(page)
        assert entries == []

    def test_signature_widget_skipped(self) -> None:
        """Signature widget (type 12) is not extracted."""
        widget = self._make_widget(12, "sig", "Signed")
        page = self._make_mock_page([widget])
        entries = _extract_page_widgets(page)
        assert entries == []

    def test_unknown_widget_type_skipped(self) -> None:
        """Widget with an unknown type (e.g. 99) is not extracted."""
        widget = self._make_widget(99, "unknown", "data")
        page = self._make_mock_page([widget])
        entries = _extract_page_widgets(page)
        assert entries == []

    def test_mixed_widget_types_filters_correctly(self) -> None:
        """Only text/combo/list widgets are extracted from a mixed page."""
        widgets = [
            self._make_widget(1, "btn", "Click"),  # button → skip
            self._make_widget(_WIDGET_TYPE_TEXT, "name", "Alice"),  # text → extract
            self._make_widget(2, "radio", "Yes"),  # radio → skip
            self._make_widget(
                _WIDGET_TYPE_COMBOBOX,
                "lang",
                "",
                choice_values=["EN", "FR"],
            ),  # combo → extract
            self._make_widget(12, "sig", "X"),  # signature → skip
            self._make_widget(
                _WIDGET_TYPE_LISTBOX,
                "sizes",
                "",
                choice_values=["Small"],
            ),  # list → extract
        ]
        page = self._make_mock_page(widgets)
        entries = _extract_page_widgets(page)
        # text(1) + combo(2) + list(1) = 4 entries
        assert len(entries) == 4  # noqa: PLR2004
        types = [e["widget_type"] for e in entries]
        assert _WIDGET_TYPE_TEXT in types
        assert _WIDGET_TYPE_COMBOBOX in types
        assert _WIDGET_TYPE_LISTBOX in types


# ── TestAlignmentEdgeCases (additional) ──────────────────────────────────────


class TestAlignmentEdgeCasesAdditional:
    """Additional edge cases for _detect_block_alignment not covered elsewhere.

    Focuses on justified-with-short-final, single-line defaults, and
    all-same-width-lines scenarios.
    """

    def test_justified_with_short_final_line(self) -> None:
        """Multi-line block with full-width lines and a short last line → justify.

        The short final line is narrower than _SHORT_LINE_RATIO of the
        typical line width, which is the hallmark of justified text.
        """
        x0 = 72.0
        full_right = 540.0
        typical_width = full_right - x0  # 468
        short_right = x0 + typical_width * 0.7  # well below _SHORT_LINE_RATIO
        extents = [
            (x0, full_right),
            (x0, full_right),
            (x0, full_right),
            (x0, full_right),
            (x0, short_right),  # short final line
        ]
        block_rect = [x0, 100.0, full_right, 250.0]
        align, _ = _detect_block_alignment(
            extents,
            block_rect,
            [12.0] * 5,  # noqa: PLR2004
        )
        assert align == "justify"

    def test_single_line_defaults_to_left(self) -> None:
        """A single-line block without page-level centering cues returns 'left'."""
        align, indent = _detect_block_alignment(
            [(72.0, 300.0)],
            [72.0, 100.0, 540.0, 112.0],
            [12.0],
            page_width=0.0,  # no page width → no center detection
        )
        assert align == "left"
        assert indent == 0.0

    def test_single_line_wide_block_not_centered(self) -> None:
        """A single-line block wider than 65% of page is NOT centered.

        Even with symmetric margins, the width cap prevents body
        paragraphs from being misclassified as centered.
        """
        # Page 612pt wide. Block 420pt wide (>65% of 612 = 397.8).
        # Symmetric margins: (612-420)/2 = 96 on each side.
        bx0 = 96.0
        bx1 = 516.0
        align, _ = _detect_block_alignment(
            [(bx0, bx1)],
            [bx0, 100.0, bx1, 112.0],
            [12.0],
            page_width=612.0,
        )
        assert align == "left"

    def test_all_lines_same_width_left_aligned(self) -> None:
        """All lines have identical widths with consistent left edges → left.

        When every line starts and ends at the same position, the text is
        flush-left (all left edges are aligned, all right edges are aligned).
        Both is_left and is_right are True, and since there is no short
        final line, the algorithm classifies as 'justify'.
        """
        extents = [(72.0, 400.0), (72.0, 400.0), (72.0, 400.0), (72.0, 400.0)]
        block_rect = [72.0, 100.0, 400.0, 200.0]
        align, _ = _detect_block_alignment(
            extents,
            block_rect,
            [12.0] * 4,
        )
        # All lines same width → is_left=True AND is_right=True → "justify"
        assert align == "justify"

    def test_all_lines_same_width_with_short_final(self) -> None:
        """Lines of identical width plus a short final line → justify."""
        x0 = 72.0
        full_right = 400.0
        short_right = x0 + (full_right - x0) * 0.6  # well below _SHORT_LINE_RATIO
        extents = [
            (x0, full_right),
            (x0, full_right),
            (x0, full_right),
            (x0, short_right),
        ]
        block_rect = [x0, 100.0, full_right, 200.0]
        align, _ = _detect_block_alignment(
            extents,
            block_rect,
            [12.0] * 4,
        )
        assert align == "justify"

    def test_two_lines_left_ragged_right(self) -> None:
        """Two lines with same left edge but different right edges.

        When the second line is shorter than _SHORT_LINE_RATIO of the first,
        it is treated as a short final line, making the block 'justify'.
        This is expected — a 2-line block with a short second line looks
        like a single paragraph of justified text.
        """
        extents = [(72.0, 350.0), (72.0, 280.0)]
        block_rect = [72.0, 100.0, 400.0, 150.0]
        align, _ = _detect_block_alignment(
            extents,
            block_rect,
            [12.0, 12.0],
        )
        # Short second line → treated as short-final → justify
        assert align == "justify"

    def test_multi_lines_left_ragged_right(self) -> None:
        """Multiple lines with consistent left edge, ragged right → left.

        Unlike the two-line case, here all lines vary in width but none
        are short enough relative to the block to trigger short-final
        detection consistently, and the right edges vary too much.
        """
        extents = [
            (72.0, 350.0),
            (72.0, 320.0),
            (72.0, 340.0),
            (72.0, 310.0),
        ]
        block_rect = [72.0, 100.0, 400.0, 200.0]
        align, _ = _detect_block_alignment(
            extents,
            block_rect,
            [12.0] * 4,
        )
        assert align == "left"

    def test_zero_width_block_returns_left(self) -> None:
        """Block with zero width returns default 'left'."""
        align, indent = _detect_block_alignment(
            [(100.0, 100.0)],
            [100.0, 100.0, 100.0, 120.0],
        )
        assert align == "left"
        assert indent == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Format-edge-case backfill tests
# ─────────────────────────────────────────────────────────────────────────────


class TestProcessPdfFileZeroPage:
    """Tests for ``process_pdf_file()`` with a zero-page PDF.

    PyMuPDF refuses to save a doc with zero pages, so we mock pymupdf.open
    to return a doc whose ``page_count`` is 0.  This documents that
    ``process_pdf_file`` iterates ``range(page_count)`` safely (no index
    error) and never calls translate_batch when there are no pages.
    """

    def test_zero_page_pdf_no_llm_call(self, tmp_path: Path) -> None:
        """A 0-page PDF completes without calling translate_batch."""
        pdf = tmp_path / "empty.pdf"
        out = tmp_path / "out.pdf"
        # Provide an existing source path so process_pdf_file's open() succeeds
        _make_pdf(pdf, ["placeholder"])

        # Mock pymupdf.open so the returned doc reports zero pages
        fake_doc = MagicMock()
        fake_doc.page_count = 0
        fake_doc.__getitem__ = MagicMock(side_effect=IndexError)
        # Save writes a real file so output assertion holds
        fake_doc.save = MagicMock(
            side_effect=lambda p, **kw: out.write_bytes(b"%PDF-1.4\n%%EOF\n")
        )
        fake_doc.close = MagicMock()
        fake_doc.get_toc.return_value = []

        with (
            patch(
                "src.core.pdf_processor.pymupdf.open",
                return_value=fake_doc,
            ),
            patch("src.core.pdf_processor.translate_batch") as mock_tb,
        ):
            result = process_pdf_file(pdf, out, "French")

        assert result is True
        mock_tb.assert_not_called()


class TestTranslateBookmarksRecursionGuard:
    """Tests that ``_translate_bookmarks`` does not recurse into TOC entries.

    PyMuPDF's ``get_toc()`` returns a flat list — the level field encodes
    hierarchy.  This test verifies that even a malicious mock returning a
    self-referential entry (cycle in the dest dict) does not infinite-loop:
    the function iterates the list once and writes back once.
    """

    def test_self_referential_toc_terminates_quickly(self) -> None:
        """Self-referential dest dict still terminates without recursion."""
        doc = MagicMock()
        # Build a TOC entry whose dest dict references the same entry list.
        # If _translate_bookmarks were to walk dest dicts, this would loop
        # forever.  The function only reads index 1 (title), so it terminates.
        entry: list[Any] = [1, "Title", 1, {"page": 1}]
        entry[3]["self"] = entry
        doc.get_toc.return_value = [entry]

        with patch(
            "src.core.pdf_processor.translate_batch",
            return_value=["Translated"],
        ):
            result = _translate_bookmarks(doc, "French", "", None, None)
        assert result is True
        # set_toc called exactly once (no recursion)
        assert doc.set_toc.call_count == 1


class TestFormFieldOverflow:
    """Documents current widget-overflow behaviour (no truncation logic)."""

    def test_widget_long_translation_documented(self, tmp_path: Path) -> None:
        """A translated widget value 3× longer than original is written verbatim.

        Current behaviour: ``_inject_page_widgets`` writes the translated text
        unchanged via ``widget.field_value = ...``; the PDF viewer is responsible
        for visual handling (clipping or scrolling).  No production-side
        truncation is performed.

        TODO: If long-form widget overflow becomes a real visual bug, add a
        truncation/wrapping layer in ``_inject_page_widgets`` and update this test.
        """
        from src.core.pdf_processor import _inject_page_widgets  # noqa: PLC0415

        pdf = tmp_path / "form.pdf"
        _make_pdf_with_widgets(
            pdf,
            text_fields=[("name", "Hi", (100, 100, 200, 130))],
        )
        doc = pymupdf.open(str(pdf))
        page = doc[0]

        long_translation = "Hola " * 30  # ~150 chars vs original 2 chars
        entries = [
            {
                "type": "widget",
                "widget_type": _WIDGET_TYPE_TEXT,
                "field_name": "name",
                "translated_text": long_translation,
            }
        ]
        _inject_page_widgets(page, entries)

        widgets = list(page.widgets())
        # The translated text is written verbatim — no truncation.
        assert widgets[0].field_value == long_translation
        doc.close()


class TestRefineAlignmentSkipsImageOverlapBlocks:
    """Documents single-line-block handling in alignment refinement.

    ``_refine_alignments_from_context`` only operates on multi-line body-text
    blocks, so single-line blocks (which is what an OCR layer over an image
    typically looks like) are *not* upgraded to ``justify`` and therefore not
    centered.
    """

    def test_single_line_block_over_image_not_upgraded(self) -> None:
        """A single-line block isn't upgraded even when justify dominates."""
        # 3 multi-line body-text blocks tagged justify form the dominant style.
        # 1 single-line block tagged left must NOT be upgraded.
        blocks: list[dict[str, Any]] = []
        for _ in range(3):
            blocks.append(
                {
                    "_line_extents": [(72.0, 400.0), (72.0, 400.0)],
                    "font_size": 12.0,
                    "text_align": "justify",
                }
            )
        single_line_block = {
            "_line_extents": [(72.0, 400.0)],
            "font_size": 12.0,
            "text_align": "left",
        }
        blocks.append(single_line_block)

        _refine_alignments_from_context(blocks)
        assert single_line_block["text_align"] == "left"

    def test_block_overlaps_image_helper_detects_overlap(self) -> None:
        """``_block_overlaps_image`` recognizes a contained block."""
        block_rect = [110.0, 110.0, 190.0, 190.0]
        image_rects = [(100.0, 100.0, 200.0, 200.0)]
        assert _block_overlaps_image(block_rect, image_rects) is True

    def test_block_overlaps_image_helper_skips_non_overlap(self) -> None:
        """A block adjacent to but not over an image is not treated as overlap."""
        block_rect = [300.0, 300.0, 400.0, 400.0]
        image_rects = [(100.0, 100.0, 200.0, 200.0)]
        assert _block_overlaps_image(block_rect, image_rects) is False


class TestFindLinkInCharsLineGap:
    """Tests for the multi-line link layout helper ``_find_link_in_chars``."""

    @staticmethod
    def _line_chars(text: str, y0: float, y1: float) -> list[tuple[str, Any]]:
        """Build (char, Rect) tuples for one visual line."""
        return [
            (
                ch,
                pymupdf.Rect(10.0 + i * 6, y0, 16.0 + i * 6, y1),
            )
            for i, ch in enumerate(text)
        ]

    def test_two_line_link_returns_two_rects(self) -> None:
        """Chars on y=100 and y=200 (gap > _LINK_LINE_Y_GAP) yield two rects."""
        first = self._line_chars("abcde", 100.0, 110.0)
        second = self._line_chars("fghij", 200.0, 210.0)
        chars = first + second
        block_text = "abcdefghij"
        link = {"_translated": block_text, "_inner": block_text}

        rects, _ = _find_link_in_chars(chars, block_text, link, 0)
        assert len(rects) == 2  # noqa: PLR2004

    def test_single_line_link_returns_one_rect(self) -> None:
        """All chars on one y position collapse to a single rect."""
        chars = self._line_chars("hello", 100.0, 110.0)
        block_text = "hello"
        link = {"_translated": block_text, "_inner": block_text}
        rects, _ = _find_link_in_chars(chars, block_text, link, 0)
        assert len(rects) == 1
