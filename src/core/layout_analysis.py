"""Layout analysis and geometric reconstruction for OCR results.

This module handles the mathematical grouping of text fragments into coherent
paragraphs, including line height estimation and bounding box calculation.
"""

from typing import Any

from src.constants.ocr import (
    OCR_DEFAULT_LINE_HEIGHT,
    OCR_EASYOCR_HEIGHT_MULTIPLIER,
    OCR_LINE_GAP_THRESHOLD_RATIO,
    OCR_MAX_LINE_HEIGHT,
    OCR_METHOD_EASYOCR,
    OCR_MIN_LINE_HEIGHT,
    OCR_SINGLE_LINE_HEIGHT,
)
from src.core.ocr_engine import OCRResult
from src.utils.ocr_utils import get_ocr_padding
from src.utils.text_utils import clean_llm_html, html_to_plain_text


def merge_to_paragraphs(
    enriched_data: list[dict[str, Any]], raw_fragments: list[OCRResult], ocr_method: str
) -> tuple[list[OCRResult], list[str], list[OCRResult]]:
    """Maps LLM-grouped fragments into paragraph-level OCRResult objects.

    Args:
        enriched_data: List of paragraph data dicts from the LLM.
        raw_fragments: List of original OCRResult objects (words/lines).
        ocr_method: The OCR engine used (affects padding/tolerances).

    Returns:
        tuple: (final_merged_results, translation_strings, used_fragments)
    """
    final_results = []
    translations = []
    confirmed_fragments = []

    # We only need the padding insert value here for character height estimation
    _, padding_insert = get_ocr_padding(ocr_method)

    for p_data in enriched_data:
        # 1. Retrieve fragments associated with this paragraph
        fragments = _get_fragments(p_data, raw_fragments)
        if not fragments:
            continue

        confirmed_fragments.extend(fragments)

        # 2. Calculate paragraph bounding box and average height
        geo = _calculate_geometry(fragments, padding_insert)

        # 3. Analyze internal line structure and spacing proportions
        line_metrics = _analyze_line_metrics(
            fragments, geo["padded_total_h"], geo["avg_char_h"], ocr_method
        )

        # 4. Build the merged OCRResult object
        original_text = " ".join([f.text for f in fragments])
        res = OCRResult(
            original_text, geo["min_x"], geo["min_y"], geo["width"], geo["height"], 1.0
        )

        # Apply visual metrics
        res.original_text_height = int(geo["avg_char_h"])
        res.line_height_ratio = line_metrics["ratio"]
        res.is_single_line = line_metrics["is_single_line"]

        # 5. Apply translated content and visual styling
        _apply_content_and_style(res, p_data, original_text)

        # 6. Skip when the LLM returned the original text unchanged
        # (collapses redundant whitespace before comparing)
        if _is_unchanged(res.translated_text, original_text):
            # Release fragments so they are NOT cleared from the background
            for f in fragments:
                if f in confirmed_fragments:
                    confirmed_fragments.remove(f)
            continue

        translations.append(res.translated_text)
        final_results.append(res)

    return final_results, translations, confirmed_fragments


def _is_unchanged(translated: str, original: str) -> bool:
    """Checks if the translated text is identical to the original.

    Collapses runs of whitespace into a single space so that minor
    spacing differences (e.g. double spaces) are ignored, while
    genuinely different word boundaries are preserved.

    Args:
        translated: The translated plain text from the LLM.
        original: The space-joined original OCR text.

    Returns:
        bool: True if the translation is effectively unchanged.
    """
    return " ".join(translated.split()).lower() == " ".join(original.split()).lower()


def _get_fragments(
    p_data: dict[str, Any], raw_fragments: list[OCRResult]
) -> list[OCRResult]:
    """Extracts valid OCR fragments based on indices provided by the LLM.

    Args:
        p_data: Dictionary containing paragraph metadata.
        raw_fragments: List of all available OCR fragments.

    Returns:
        list[OCRResult]: The subset of fragments for this paragraph.
    """
    ids = p_data.get("ids", [])
    return [raw_fragments[i] for i in ids if 0 <= i < len(raw_fragments)]


def _calculate_geometry(fragments: list[OCRResult], padding: int) -> dict[str, Any]:
    """Calculates the merged bounding box and estimated character height.

    Args:
        fragments: The fragments to analyze.
        padding: The visual padding to include in height calculations.

    Returns:
        dict: Geographic and height metrics.
    """
    min_x = min(f.x for f in fragments)
    min_y = min(f.y for f in fragments)
    max_xr = max(f.x + f.w for f in fragments)
    max_yb = max(f.y + f.h for f in fragments)

    width = max_xr - min_x
    height = max_yb - min_y

    # Calculate average character height including padding
    avg_char_h = sum(f.h + (padding * 2) for f in fragments) / len(fragments)

    return {
        "min_x": min_x,
        "min_y": min_y,
        "width": width,
        "height": height,
        "avg_char_h": avg_char_h,
        "padded_total_h": height + (padding * 2),
    }


def _analyze_line_metrics(
    fragments: list[OCRResult],
    padded_total_h: float,
    avg_char_h: float,
    ocr_method: str,
) -> dict[str, Any]:
    """Estimates line count and spacing ratio using spatial distribution.

    Args:
        fragments: The fragments to analyze.
        padded_total_h: The total height of the paragraph including padding.
        avg_char_h: The estimated height of a single character.
        ocr_method: The OCR engine name.

    Returns:
        dict: Metrics for lines and line-height ratio.
    """
    y_levels = sorted({f.y for f in fragments})

    unique_lines = 1
    if y_levels:
        last_y = y_levels[0]
        for y in y_levels[1:]:
            # Use threshold-based grouping to count visual lines
            if y - last_y > (avg_char_h * OCR_LINE_GAP_THRESHOLD_RATIO):
                unique_lines += 1
                last_y = y

    # Spacing proportions calculation
    ratio = OCR_SINGLE_LINE_HEIGHT if unique_lines == 1 else OCR_DEFAULT_LINE_HEIGHT
    if unique_lines > 1 and avg_char_h > 0:
        ratio = padded_total_h / (unique_lines * avg_char_h)
        if OCR_METHOD_EASYOCR in ocr_method:
            ratio *= OCR_EASYOCR_HEIGHT_MULTIPLIER

        # Clamp to avoid rendering artifacts
        ratio = max(OCR_MIN_LINE_HEIGHT, min(OCR_MAX_LINE_HEIGHT, ratio))

    return {
        "unique_lines": unique_lines,
        "is_single_line": (unique_lines == 1),
        "ratio": ratio,
    }


def _apply_content_and_style(
    res: OCRResult, p_data: dict[str, Any], original_text: str
) -> None:
    """Applies translated content and visual styles from LLM enrichment.

    Args:
        res: The OCRResult object to update.
        p_data: The enrichment data.
        original_text: The original source text.
    """
    # HTML Cleaning and Text Conversion
    html_raw = p_data.get("translated_html", original_text)
    res.translated_html = clean_llm_html(html_raw)
    res.translated_text = html_to_plain_text(res.translated_html)

    # Text Color (hex string)
    if "color" in p_data:
        res.color = p_data["color"]

    # Horizontal Alignment (string constant)
    if "alignment" in p_data:
        from src.core.checkpoint import (  # noqa: PLC0415
            ALIGN_CENTER,
            ALIGN_LEFT,
            ALIGN_RIGHT,
        )

        alignment_map = {
            "left": ALIGN_LEFT,
            "center": ALIGN_CENTER,
            "right": ALIGN_RIGHT,
        }
        res.alignment = alignment_map.get(p_data["alignment"], ALIGN_CENTER)
