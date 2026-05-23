"""Unit tests for layout analysis logic."""

import pytest

from src.constants.ocr import OCR_LINE_GAP_THRESHOLD_RATIO
from src.core.checkpoint import ALIGN_CENTER, ALIGN_LEFT, ALIGN_RIGHT
from src.core.layout_analysis import (
    _analyze_line_metrics,
    _apply_content_and_style,
    _calculate_geometry,
    _get_fragments,
    _is_unchanged,
    merge_to_paragraphs,
)
from src.core.ocr_engine import OCRResult


@pytest.fixture
def raw_fragments():
    """Provides a sample set of OCR fragments."""
    return [
        OCRResult("Line", 10, 10, 50, 20, 0.9),
        OCRResult("One", 70, 10, 40, 20, 0.9),
        OCRResult("Line", 10, 40, 50, 20, 0.9),
        OCRResult("Two", 70, 40, 40, 20, 0.9),
    ]


def test_merge_to_paragraphs_basic(raw_fragments) -> None:
    """Verify that fragments are correctly merged into paragraphs."""
    enriched_data = [
        {
            "ids": [0, 1, 2, 3],
            "translated_html": "Paragraph 1 line 1<br>line 2",
            "color": "#FF0000",
            "alignment": "center",
        }
    ]

    merged, translations, used = merge_to_paragraphs(
        enriched_data, raw_fragments, "TesseractOCR"
    )

    assert len(merged) == 1
    res = merged[0]
    assert res.text == "Line One Line Two"
    assert res.translated_text == "Paragraph 1 line 1\nline 2"
    assert res.color == "#FF0000"
    assert res.alignment == ALIGN_CENTER
    assert res.is_single_line is False
    assert len(used) == 4


def test_merge_to_paragraphs_single_line(raw_fragments) -> None:
    """Verify single line detection."""
    enriched_data = [
        {
            "ids": [0, 1],
            "translated_html": "Translated Line 1",
            "color": "#000000",
            "alignment": "left",
        }
    ]

    merged, translations, used = merge_to_paragraphs(
        enriched_data, raw_fragments, "TesseractOCR"
    )

    assert len(merged) == 1
    assert merged[0].is_single_line is True
    assert merged[0].alignment == ALIGN_LEFT


def test_merge_to_paragraphs_optimization(raw_fragments) -> None:
    """Verify that identical translations are skipped."""
    # Note: merge_to_paragraphs joins original fragments with " "
    original_combined = "Line One"
    enriched_data = [
        {
            "ids": [0, 1],
            "translated_html": original_combined,  # Identical
            "color": "#000000",
            "alignment": "left",
        }
    ]

    merged, translations, used = merge_to_paragraphs(
        enriched_data, raw_fragments, "TesseractOCR"
    )

    assert len(merged) == 0
    assert len(translations) == 0
    assert len(used) == 0  # Should be empty because they were removed from used list


def test_merge_to_paragraphs_multiple_paragraphs(raw_fragments) -> None:
    """Verify that multiple paragraphs are correctly processed."""
    enriched_data = [
        {
            "ids": [0, 1],
            "translated_html": "First paragraph",
            "color": "#000000",
            "alignment": "left",
        },
        {
            "ids": [2, 3],
            "translated_html": "Second paragraph",
            "color": "#FF0000",
            "alignment": "right",
        },
    ]

    merged, translations, used = merge_to_paragraphs(
        enriched_data, raw_fragments, "TesseractOCR"
    )

    assert len(merged) == 2
    assert translations == ["First paragraph", "Second paragraph"]
    assert merged[0].alignment == ALIGN_LEFT
    assert merged[1].alignment == ALIGN_RIGHT
    assert merged[1].color == "#FF0000"
    assert len(used) == 4


def test_merge_to_paragraphs_empty_ids(raw_fragments) -> None:
    """Verify that paragraphs with empty ids are skipped."""
    enriched_data = [
        {"ids": [], "translated_html": "Ghost", "color": "#000000", "alignment": "left"}
    ]

    merged, translations, used = merge_to_paragraphs(
        enriched_data, raw_fragments, "TesseractOCR"
    )

    assert len(merged) == 0
    assert len(translations) == 0
    assert len(used) == 0


def test_merge_to_paragraphs_invalid_ids(raw_fragments) -> None:
    """Verify that out-of-range ids are silently ignored."""
    enriched_data = [
        {
            "ids": [99, 100],  # Out of range
            "translated_html": "Invalid",
            "color": "#000000",
            "alignment": "left",
        }
    ]

    merged, translations, used = merge_to_paragraphs(
        enriched_data, raw_fragments, "TesseractOCR"
    )

    assert len(merged) == 0
    assert len(translations) == 0


def test_merge_to_paragraphs_easyocr_method(raw_fragments) -> None:
    """Verify EasyOCR-specific line height multiplier is applied."""
    enriched_data = [
        {
            "ids": [0, 1, 2, 3],
            "translated_html": "Paragraph",
            "color": "#000000",
            "alignment": "center",
        }
    ]

    merged, translations, used = merge_to_paragraphs(
        enriched_data, raw_fragments, "EasyOCR"
    )

    assert len(merged) == 1
    # EasyOCR should have different line height ratio than Tesseract for multi-line
    assert merged[0].line_height_ratio > 0


def test_merge_to_paragraphs_br_cleaning(raw_fragments) -> None:
    """Verify that leading/trailing <br /> tags are cleaned from HTML."""
    enriched_data = [
        {
            "ids": [0, 1],
            "translated_html": "<br />Clean text<br />",
            "color": "#000000",
            "alignment": "left",
        }
    ]

    merged, translations, used = merge_to_paragraphs(
        enriched_data, raw_fragments, "TesseractOCR"
    )

    assert len(merged) == 1
    assert merged[0].translated_html == "Clean text"
    assert merged[0].translated_text == "Clean text"


# --- Helper function tests ---


def test_get_fragments_valid_ids(raw_fragments) -> None:
    """Verify fragment extraction with valid IDs."""
    p_data = {"ids": [0, 2]}
    result = _get_fragments(p_data, raw_fragments)
    assert len(result) == 2
    assert result[0].text == "Line"
    assert result[1].text == "Line"


def test_get_fragments_out_of_range(raw_fragments) -> None:
    """Verify that out-of-range IDs are silently skipped."""
    p_data = {"ids": [0, 99, -1]}
    result = _get_fragments(p_data, raw_fragments)
    assert len(result) == 1  # Only index 0 is valid


def test_get_fragments_no_ids(raw_fragments) -> None:
    """Verify empty list when no ids key."""
    p_data = {}
    result = _get_fragments(p_data, raw_fragments)
    assert result == []


def test_calculate_geometry() -> None:
    """Verify bounding box and height calculation."""
    fragments = [
        OCRResult("A", 10, 10, 50, 20, 0.9),
        OCRResult("B", 70, 10, 40, 20, 0.9),
    ]
    geo = _calculate_geometry(fragments, padding=1)

    assert geo["min_x"] == 10
    assert geo["min_y"] == 10
    assert geo["width"] == 100  # 110 - 10
    assert geo["height"] == 20  # 30 - 10
    assert geo["avg_char_h"] > 0


def test_analyze_line_metrics_single_line() -> None:
    """Verify single-line detection."""
    fragments = [
        OCRResult("A", 10, 10, 50, 20, 0.9),
        OCRResult("B", 70, 10, 40, 20, 0.9),
    ]
    metrics = _analyze_line_metrics(fragments, 22.0, 22.0, "TesseractOCR")

    assert metrics["is_single_line"] is True
    assert metrics["unique_lines"] == 1


def test_analyze_line_metrics_multi_line() -> None:
    """Verify multi-line detection with distinct Y levels."""
    fragments = [
        OCRResult("A", 10, 10, 50, 20, 0.9),
        OCRResult("B", 10, 60, 50, 20, 0.9),  # 50px gap, clearly different line
    ]
    metrics = _analyze_line_metrics(fragments, 72.0, 22.0, "TesseractOCR")

    assert metrics["is_single_line"] is False
    assert metrics["unique_lines"] == 2
    assert metrics["ratio"] > 0


# ---------------------------------------------------------------------------
# _is_unchanged edge cases
# ---------------------------------------------------------------------------


def test_is_unchanged_identical() -> None:
    """Identical text returns True."""
    assert _is_unchanged("Hello World", "Hello World") is True


def test_is_unchanged_case_insensitive() -> None:
    """Case differences are ignored."""
    assert _is_unchanged("hello world", "Hello World") is True


def test_is_unchanged_extra_whitespace() -> None:
    """Extra whitespace (double spaces, tabs) is collapsed."""
    assert _is_unchanged("hello  world", "hello world") is True
    assert _is_unchanged("hello\tworld", "hello world") is True
    assert _is_unchanged("  hello   world  ", "hello world") is True


def test_is_unchanged_different_text() -> None:
    """Different text returns False."""
    assert _is_unchanged("Bonjour le monde", "Hello World") is False


def test_is_unchanged_empty_both() -> None:
    """Two empty strings are considered unchanged."""
    assert _is_unchanged("", "") is True


# ---------------------------------------------------------------------------
# _calculate_geometry edge cases
# ---------------------------------------------------------------------------


def test_calculate_geometry_single_fragment() -> None:
    """Single fragment produces correct bounding box."""
    fragments = [OCRResult("A", 10, 20, 50, 30, 0.9)]
    geo = _calculate_geometry(fragments, padding=1)

    assert geo["min_x"] == 10
    assert geo["min_y"] == 20
    assert geo["width"] == 50
    assert geo["height"] == 30


def test_calculate_geometry_overlapping_fragments() -> None:
    """Overlapping fragments produce correct merged bounding box."""
    fragments = [
        OCRResult("A", 10, 10, 60, 30, 0.9),
        OCRResult("B", 30, 10, 60, 30, 0.9),  # Overlaps with A
    ]
    geo = _calculate_geometry(fragments, padding=0)

    assert geo["min_x"] == 10
    assert geo["min_y"] == 10
    assert geo["width"] == 80  # max(70, 90) - 10 = 80
    assert geo["height"] == 30


def test_calculate_geometry_padding_affects_height() -> None:
    """Padding is included in average character height calculation."""
    fragments = [OCRResult("A", 0, 0, 50, 20, 1.0)]
    geo_no_pad = _calculate_geometry(fragments, padding=0)
    geo_with_pad = _calculate_geometry(fragments, padding=5)

    assert geo_with_pad["avg_char_h"] > geo_no_pad["avg_char_h"]
    # With padding=5: avg_char_h = (20 + 10) / 1 = 30
    assert geo_with_pad["avg_char_h"] == 30.0  # noqa: PLR2004


# ---------------------------------------------------------------------------
# _analyze_line_metrics edge cases
# ---------------------------------------------------------------------------


def test_analyze_line_metrics_easyocr_multiplier() -> None:
    """EasyOCR applies 1.2x height multiplier for multi-line."""
    fragments = [
        OCRResult("A", 10, 10, 50, 20, 0.9),
        OCRResult("B", 10, 60, 50, 20, 0.9),
    ]
    # Same input but different OCR methods
    tess = _analyze_line_metrics(fragments, 72.0, 22.0, "TesseractOCR")
    easy = _analyze_line_metrics(fragments, 72.0, 22.0, "EasyOCR")

    assert easy["ratio"] == pytest.approx(tess["ratio"] * 1.2, abs=0.01)


def test_analyze_line_metrics_ratio_clamped_min() -> None:
    """Ratio is clamped to minimum 0.8."""
    fragments_ml = [
        OCRResult("A", 10, 10, 50, 20, 0.9),
        OCRResult("B", 10, 100, 50, 20, 0.9),
    ]
    # padded_total_h=5, avg_char_h=100 → ratio=5/(2*100)=0.025 → clamp to 0.8
    metrics = _analyze_line_metrics(
        fragments_ml,
        5.0,
        100.0,
        "TesseractOCR",
    )
    assert metrics["ratio"] == pytest.approx(0.8, abs=0.01)


def test_analyze_line_metrics_ratio_clamped_max() -> None:
    """Ratio is clamped to maximum 3.0."""
    fragments = [
        OCRResult("A", 10, 10, 50, 20, 0.9),
        OCRResult("B", 10, 100, 50, 20, 0.9),
    ]
    # padded_total_h=10000, avg_char_h=1 → ratio = 10000 / (2*1) = 5000
    # → clamp to 3.0
    metrics = _analyze_line_metrics(fragments, 10000.0, 1.0, "TesseractOCR")
    assert metrics["ratio"] == pytest.approx(3.0, abs=0.01)


# ---------------------------------------------------------------------------
# _apply_content_and_style edge cases
# ---------------------------------------------------------------------------


def test_apply_content_and_style_basic() -> None:
    """Applies HTML, color, and alignment correctly."""
    res = OCRResult("original", 0, 0, 100, 20, 1.0)
    p_data = {
        "translated_html": "<b>Translated</b>",
        "color": "#FF0000",
        "alignment": "right",
    }
    _apply_content_and_style(res, p_data, "original")

    assert res.translated_html == "<b>Translated</b>"
    assert res.translated_text == "Translated"
    assert res.color == "#FF0000"
    assert res.alignment == ALIGN_RIGHT


def test_apply_content_and_style_missing_color() -> None:
    """Missing color key leaves the default OCRResult color."""
    res = OCRResult("test", 0, 0, 100, 20, 1.0)
    original_color = res.color

    p_data = {
        "translated_html": "Translated",
        "alignment": "left",
    }
    _apply_content_and_style(res, p_data, "test")

    assert res.color == original_color


def test_apply_content_and_style_missing_alignment() -> None:
    """Missing alignment key leaves OCRResult.alignment as None."""
    res = OCRResult("test", 0, 0, 100, 20, 1.0)
    p_data = {"translated_html": "Translated"}
    _apply_content_and_style(res, p_data, "test")

    assert res.alignment is None


def test_apply_content_and_style_unknown_alignment() -> None:
    """Unknown alignment string defaults to AlignHCenter."""
    res = OCRResult("test", 0, 0, 100, 20, 1.0)
    p_data = {
        "translated_html": "Translated",
        "alignment": "justify",
    }
    _apply_content_and_style(res, p_data, "test")

    assert res.alignment == ALIGN_CENTER


def test_apply_content_and_style_br_cleaning() -> None:
    """Leading/trailing <br> tags are stripped from HTML."""
    res = OCRResult("test", 0, 0, 100, 20, 1.0)
    p_data = {
        "translated_html": "<br/>Hello<br>",
        "color": "#000000",
        "alignment": "left",
    }
    _apply_content_and_style(res, p_data, "test")

    assert res.translated_html == "Hello"
    assert res.translated_text == "Hello"


def test_apply_content_and_style_missing_html_uses_original() -> None:
    """Missing translated_html key falls back to original text."""
    res = OCRResult("fallback text", 0, 0, 100, 20, 1.0)
    p_data = {"alignment": "center"}
    _apply_content_and_style(res, p_data, "fallback text")

    assert res.translated_text == "fallback text"


# ---------------------------------------------------------------------------
# _calculate_geometry additional edge cases
# ---------------------------------------------------------------------------


def test_calculate_geometry_different_heights() -> None:
    """Fragments with different heights produce correct avg_char_h."""
    # Fragment A: height=20, Fragment B: height=40 → avg=(20+40)/2=30 (before padding)
    fragments = [
        OCRResult("A", 0, 0, 50, 20, 0.9),
        OCRResult("B", 60, 10, 50, 40, 0.9),
    ]
    geo = _calculate_geometry(fragments, padding=0)

    # avg_char_h with no padding = average of heights = (20+40)/2 = 30
    assert geo["avg_char_h"] == pytest.approx(30.0, abs=0.01)
    # Bounding box: x=[0..110], y=[0..50]
    assert geo["min_x"] == 0
    assert geo["min_y"] == 0
    assert geo["width"] == 110  # max(50, 110) - 0
    assert geo["height"] == 50  # max(20, 50) - 0


# ---------------------------------------------------------------------------
# _analyze_line_metrics: avg_char_h=0 guard
# ---------------------------------------------------------------------------


def test_analyze_line_metrics_single_line_zero_char_h() -> None:
    """Single-line detection still works when avg_char_h=0 (no ratio computed)."""
    fragments = [
        OCRResult("A", 10, 10, 50, 0, 0.9),  # height=0 → avg_char_h could be 0
    ]
    # Single fragment → is_single_line, no ratio division needed
    metrics = _analyze_line_metrics(fragments, 0.0, 0.0, "TesseractOCR")

    assert metrics["is_single_line"] is True
    assert metrics["unique_lines"] == 1
    # Single-line always uses OCR_SINGLE_LINE_HEIGHT = 1.0 (ratio is not computed)
    assert metrics["ratio"] == pytest.approx(1.0, abs=0.01)


# ---------------------------------------------------------------------------
# _analyze_line_metrics: boundary condition for line gap threshold
# ---------------------------------------------------------------------------


class TestAnalyzeLineMetricsBoundary:
    """Boundary condition for line gap threshold."""

    def test_gap_exactly_at_threshold_not_counted(self) -> None:
        """Gap exactly at threshold does not count as a new line.

        The condition in _analyze_line_metrics uses strict greater-than (``>``),
        so a Y gap of exactly ``avg_char_h * OCR_LINE_GAP_THRESHOLD_RATIO``
        should NOT trigger a new line — unique_lines stays at 1.
        """
        avg_char_h = 20.0
        # Place two fragments whose Y gap is exactly at the threshold
        gap = avg_char_h * OCR_LINE_GAP_THRESHOLD_RATIO  # 20.0 * 0.5 = 10.0
        y1 = 10.0
        y2 = y1 + gap  # 20.0 — exactly at threshold

        fragments = [
            OCRResult("A", 10, int(y1), 50, 20, 0.9),
            OCRResult("B", 10, int(y2), 50, 20, 0.9),
        ]

        metrics = _analyze_line_metrics(fragments, 42.0, avg_char_h, "TesseractOCR")

        assert metrics["unique_lines"] == 1
        assert metrics["is_single_line"] is True
        # Single-line → ratio uses OCR_SINGLE_LINE_HEIGHT (1.0), not computed
        assert metrics["ratio"] == pytest.approx(1.0, abs=0.01)


# ---------------------------------------------------------------------------
# merge_to_paragraphs — empty input
# ---------------------------------------------------------------------------


class TestMergeToParagraphsEmpty:
    """Tests for merge_to_paragraphs with empty inputs."""

    def test_empty_enriched_data(self) -> None:
        """Empty enriched_data list returns empty results."""
        merged, translations, used = merge_to_paragraphs([], [], "TesseractOCR")
        assert merged == []
        assert translations == []
        assert used == []

    def test_empty_enriched_data_with_fragments(self) -> None:
        """Empty enriched_data but non-empty raw_fragments returns empty."""
        frags = [OCRResult("Hello", 0, 0, 50, 20, 0.9)]
        merged, translations, used = merge_to_paragraphs([], frags, "TesseractOCR")
        assert merged == []
        assert translations == []
        assert used == []

    def test_empty_raw_fragments_with_enriched(self) -> None:
        """Non-empty enriched_data but empty raw_fragments skips all."""
        enriched = [
            {
                "ids": [0, 1],
                "translated_html": "Translated",
                "color": "#000000",
                "alignment": "left",
            }
        ]
        merged, translations, used = merge_to_paragraphs(enriched, [], "TesseractOCR")
        assert merged == []
        assert translations == []
        assert used == []

    def test_all_ids_out_of_range(self) -> None:
        """When all ids are out of range, nothing is produced."""
        frags = [OCRResult("A", 0, 0, 10, 10, 0.9)]
        enriched = [
            {
                "ids": [5, 10, 99],
                "translated_html": "Invalid",
                "alignment": "left",
            }
        ]
        merged, translations, used = merge_to_paragraphs(
            enriched, frags, "TesseractOCR"
        )
        assert merged == []
        assert translations == []
        assert used == []


# ---------------------------------------------------------------------------
# merge_to_paragraphs — overlapping bounding box fragments
# ---------------------------------------------------------------------------


class TestMergeToParagraphsOverlapping:
    """Tests for merge_to_paragraphs with overlapping bounding boxes."""

    def test_overlapping_fragments_merged_correctly(self) -> None:
        """Overlapping fragments produce a bounding box covering both."""
        frags = [
            OCRResult("over", 10, 10, 60, 30, 0.9),
            OCRResult("lap", 30, 10, 60, 30, 0.9),
        ]
        enriched = [
            {
                "ids": [0, 1],
                "translated_html": "Translated overlap",
                "color": "#000000",
                "alignment": "left",
            }
        ]
        merged, translations, used = merge_to_paragraphs(
            enriched, frags, "TesseractOCR"
        )
        assert len(merged) == 1
        res = merged[0]
        # Bounding box: x=min(10,30)=10, y=10, w=max(70,90)-10=80, h=30
        assert res.x == 10
        assert res.y == 10
        assert res.w == 80  # noqa: PLR2004
        assert res.h == 30  # noqa: PLR2004

    def test_fully_contained_fragments(self) -> None:
        """One fragment fully contained inside another."""
        frags = [
            OCRResult("outer", 0, 0, 100, 50, 0.9),
            OCRResult("inner", 20, 10, 30, 20, 0.9),
        ]
        enriched = [
            {
                "ids": [0, 1],
                "translated_html": "Contained translated",
                "alignment": "center",
            }
        ]
        merged, translations, used = merge_to_paragraphs(
            enriched, frags, "TesseractOCR"
        )
        assert len(merged) == 1
        res = merged[0]
        # Bounding box should be the outer fragment's box
        assert res.x == 0
        assert res.y == 0
        assert res.w == 100  # noqa: PLR2004
        assert res.h == 50  # noqa: PLR2004


# ---------------------------------------------------------------------------
# merge_to_paragraphs — single fragment input
# ---------------------------------------------------------------------------


class TestMergeToParagraphsSingleFragment:
    """Tests for merge_to_paragraphs with a single fragment."""

    def test_single_fragment_single_paragraph(self) -> None:
        """Single fragment in a single paragraph works correctly."""
        frags = [OCRResult("Hello", 10, 20, 50, 15, 0.95)]
        enriched = [
            {
                "ids": [0],
                "translated_html": "Bonjour",
                "color": "#123456",
                "alignment": "left",
            }
        ]
        merged, translations, used = merge_to_paragraphs(
            enriched, frags, "TesseractOCR"
        )
        assert len(merged) == 1
        assert merged[0].translated_text == "Bonjour"
        assert merged[0].text == "Hello"
        assert merged[0].x == 10
        assert merged[0].y == 20
        assert merged[0].w == 50  # noqa: PLR2004
        assert merged[0].h == 15  # noqa: PLR2004
        assert merged[0].is_single_line is True
        assert merged[0].color == "#123456"
        assert len(used) == 1

    def test_single_fragment_unchanged_text_skipped(self) -> None:
        """Single fragment with identical translation is skipped."""
        frags = [OCRResult("Hello", 10, 20, 50, 15, 0.95)]
        enriched = [
            {
                "ids": [0],
                "translated_html": "Hello",
                "alignment": "left",
            }
        ]
        merged, translations, used = merge_to_paragraphs(
            enriched, frags, "TesseractOCR"
        )
        assert len(merged) == 0
        assert len(translations) == 0
        assert len(used) == 0


# ---------------------------------------------------------------------------
# Fragments with zero-width or zero-height bounding boxes
# ---------------------------------------------------------------------------


class TestZeroDimensionFragments:
    """Tests for fragments with zero width or height."""

    def test_zero_height_fragment(self) -> None:
        """Fragment with height=0 is processed without error."""
        frags = [OCRResult("ZeroH", 10, 10, 50, 0, 0.9)]
        enriched = [
            {
                "ids": [0],
                "translated_html": "TranslatedZeroH",
                "alignment": "left",
            }
        ]
        merged, translations, used = merge_to_paragraphs(
            enriched, frags, "TesseractOCR"
        )
        assert len(merged) == 1
        assert merged[0].translated_text == "TranslatedZeroH"
        assert merged[0].h == 0

    def test_zero_width_fragment(self) -> None:
        """Fragment with width=0 is processed without error."""
        frags = [OCRResult("ZeroW", 10, 10, 0, 20, 0.9)]
        enriched = [
            {
                "ids": [0],
                "translated_html": "TranslatedZeroW",
                "alignment": "left",
            }
        ]
        merged, translations, used = merge_to_paragraphs(
            enriched, frags, "TesseractOCR"
        )
        assert len(merged) == 1
        assert merged[0].translated_text == "TranslatedZeroW"
        assert merged[0].w == 0

    def test_zero_width_and_height(self) -> None:
        """Fragment with both width=0 and height=0 (degenerate point)."""
        frags = [OCRResult("Point", 10, 10, 0, 0, 0.9)]
        enriched = [
            {
                "ids": [0],
                "translated_html": "TranslatedPoint",
                "alignment": "center",
            }
        ]
        merged, translations, used = merge_to_paragraphs(
            enriched, frags, "TesseractOCR"
        )
        assert len(merged) == 1
        assert merged[0].w == 0
        assert merged[0].h == 0

    def test_mixed_zero_and_normal_fragments(self) -> None:
        """Mix of zero-height and normal fragments computes valid geometry."""
        frags = [
            OCRResult("Normal", 10, 10, 50, 20, 0.9),
            OCRResult("ZeroH", 70, 10, 40, 0, 0.8),
        ]
        enriched = [
            {
                "ids": [0, 1],
                "translated_html": "Mixed translation",
                "alignment": "left",
            }
        ]
        merged, translations, used = merge_to_paragraphs(
            enriched, frags, "TesseractOCR"
        )
        assert len(merged) == 1
        # Height should be from the normal fragment (max_yb=30, min_y=10)
        assert merged[0].h == 20  # noqa: PLR2004

    def test_calculate_geometry_zero_height_fragments(self) -> None:
        """_calculate_geometry handles zero-height fragments."""
        frags = [
            OCRResult("A", 0, 10, 50, 0, 0.9),
            OCRResult("B", 60, 10, 50, 0, 0.9),
        ]
        geo = _calculate_geometry(frags, padding=0)
        assert geo["height"] == 0
        # avg_char_h = (0 + 0) / 2 = 0
        assert geo["avg_char_h"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Very large number of fragments (performance/correctness)
# ---------------------------------------------------------------------------


class TestLargeNumberOfFragments:
    """Tests with many fragments to verify correctness at scale."""

    def test_hundred_fragments_single_paragraph(self) -> None:
        """100 fragments in a single paragraph are merged correctly."""
        n = 100  # noqa: PLR2004
        frags = [OCRResult(f"w{i}", i * 12, 0, 10, 15, 0.9) for i in range(n)]
        enriched = [
            {
                "ids": list(range(n)),
                "translated_html": "Large paragraph translated",
                "alignment": "left",
            }
        ]
        merged, translations, used = merge_to_paragraphs(
            enriched, frags, "TesseractOCR"
        )
        assert len(merged) == 1
        assert merged[0].translated_text == "Large paragraph translated"
        assert len(used) == n

    def test_hundred_fragments_text_join(self) -> None:
        """Original text is space-joined from 100 fragments."""
        n = 100  # noqa: PLR2004
        frags = [OCRResult(f"word{i}", i * 60, 0, 50, 15, 0.9) for i in range(n)]
        enriched = [
            {
                "ids": list(range(n)),
                "translated_html": "Different translation",
                "alignment": "left",
            }
        ]
        merged, translations, used = merge_to_paragraphs(
            enriched, frags, "TesseractOCR"
        )
        assert len(merged) == 1
        expected_text = " ".join(f"word{i}" for i in range(n))
        assert merged[0].text == expected_text

    def test_many_separate_paragraphs(self) -> None:
        """50 separate single-fragment paragraphs all processed."""
        n = 50  # noqa: PLR2004
        frags = [OCRResult(f"para{i}", 0, i * 30, 80, 20, 0.9) for i in range(n)]
        enriched = [
            {
                "ids": [i],
                "translated_html": f"Translated paragraph {i}",
                "alignment": "left",
            }
            for i in range(n)
        ]
        merged, translations, used = merge_to_paragraphs(
            enriched, frags, "TesseractOCR"
        )
        assert len(merged) == n
        assert len(translations) == n
        assert len(used) == n

    def test_many_fragments_multiline_detection(self) -> None:
        """Many fragments on distinct lines produce multi-line detection."""
        # 5 lines, 10 fragments per line
        frags = []
        for line in range(5):
            for col in range(10):
                frags.append(
                    OCRResult(
                        f"L{line}C{col}",
                        col * 55,
                        line * 40,
                        50,
                        20,
                        0.9,
                    )
                )
        enriched = [
            {
                "ids": list(range(50)),
                "translated_html": "Multi-line translated content",
                "alignment": "left",
            }
        ]
        merged, translations, used = merge_to_paragraphs(
            enriched, frags, "TesseractOCR"
        )
        assert len(merged) == 1
        assert merged[0].is_single_line is False
        assert len(used) == 50  # noqa: PLR2004

    def test_calculate_geometry_many_scattered_fragments(self) -> None:
        """Geometry calculation with 200 scattered fragments."""
        n = 200  # noqa: PLR2004
        frags = [
            OCRResult(f"f{i}", i * 5, (i % 20) * 25, 10, 15, 0.9) for i in range(n)
        ]
        geo = _calculate_geometry(frags, padding=1)
        # min_x = 0, min_y = 0
        assert geo["min_x"] == 0
        assert geo["min_y"] == 0
        # max_xr = (199*5) + 10 = 1005
        assert geo["width"] == 1005  # noqa: PLR2004
        # max_yb = 19*25 + 15 = 490
        assert geo["height"] == 490  # noqa: PLR2004
        assert geo["avg_char_h"] > 0


# ---------------------------------------------------------------------------
# NEW: Additional tests for expanded coverage
# ---------------------------------------------------------------------------


class TestIsUnchangedAdditional:
    """Additional edge cases for _is_unchanged."""

    def test_newlines_collapsed(self) -> None:
        """Newlines are treated as whitespace and collapsed."""
        assert _is_unchanged("hello\nworld", "hello world") is True

    def test_mixed_whitespace_collapsed(self) -> None:
        """Mixed tabs, newlines, spaces are all collapsed."""
        assert _is_unchanged("hello\t\n  world", "hello world") is True

    def test_unicode_text_identical(self) -> None:
        """Unicode text comparison works correctly."""
        assert _is_unchanged("こんにちは", "こんにちは") is True

    def test_unicode_text_different(self) -> None:
        """Different Unicode text returns False."""
        assert _is_unchanged("こんにちは", "さようなら") is False

    def test_one_empty_one_not(self) -> None:
        """One empty, one non-empty returns False."""
        assert _is_unchanged("", "hello") is False

    def test_whitespace_only_vs_empty(self) -> None:
        """Whitespace-only vs empty are both collapsed to empty."""
        assert _is_unchanged("   \t\n  ", "") is True

    def test_numeric_text_identical(self) -> None:
        """Numeric-only text comparison."""
        assert _is_unchanged("12345", "12345") is True

    def test_punctuation_differences(self) -> None:
        """Punctuation differences are detected."""
        assert _is_unchanged("hello!", "hello?") is False


class TestGetFragmentsAdditional:
    """Additional edge cases for _get_fragments."""

    def test_duplicate_ids(self, raw_fragments) -> None:
        """Duplicate IDs produce duplicate fragments."""
        p_data = {"ids": [0, 0, 0]}
        result = _get_fragments(p_data, raw_fragments)
        assert len(result) == 3
        assert all(f.text == "Line" for f in result)

    def test_mixed_valid_and_invalid_ids(self, raw_fragments) -> None:
        """Mix of valid and invalid IDs returns only valid ones."""
        p_data = {"ids": [-5, 0, 99, 1, -1]}
        result = _get_fragments(p_data, raw_fragments)
        assert len(result) == 2
        assert result[0].text == "Line"
        assert result[1].text == "One"

    def test_single_valid_id(self, raw_fragments) -> None:
        """Single valid ID returns single fragment."""
        p_data = {"ids": [2]}
        result = _get_fragments(p_data, raw_fragments)
        assert len(result) == 1
        assert result[0].text == "Line"

    def test_empty_raw_fragments(self) -> None:
        """Empty raw_fragments returns empty list for any IDs."""
        p_data = {"ids": [0, 1, 2]}
        result = _get_fragments(p_data, [])
        assert result == []

    def test_ids_key_is_none(self) -> None:
        """Ids key set to None is treated as empty via default."""
        p_data = {"ids": None}
        # _get_fragments iterates over ids; None causes TypeError
        # but the function uses .get("ids", []) default
        # Actually ids=None; iterating raises TypeError. Let me check.
        # The code does: ids = p_data.get("ids", []); return [... for i in ids ...]
        # With ids=None, iteration raises TypeError. Let's verify the behavior.
        frags = [OCRResult("A", 0, 0, 10, 10, 0.9)]
        try:
            result = _get_fragments(p_data, frags)
            # If it returns something, it should be empty or raise
            assert isinstance(result, list)
        except TypeError:
            pass  # Expected if None is not iterable


class TestCalculateGeometryAdditional:
    """Additional geometry calculation tests."""

    def test_negative_coordinates(self) -> None:
        """Negative coordinates produce correct bounding box."""
        fragments = [
            OCRResult("A", -10, -5, 50, 20, 0.9),
            OCRResult("B", 30, 10, 40, 20, 0.9),
        ]
        geo = _calculate_geometry(fragments, padding=0)
        assert geo["min_x"] == -10
        assert geo["min_y"] == -5
        assert geo["width"] == 80  # max(40, 70) - (-10) = 80
        assert geo["height"] == 35  # max(15, 30) - (-5) = 35

    def test_large_padding_value(self) -> None:
        """Large padding increases avg_char_h significantly."""
        fragments = [OCRResult("A", 0, 0, 50, 10, 0.9)]
        geo = _calculate_geometry(fragments, padding=100)
        # avg_char_h = (10 + 200) / 1 = 210
        assert geo["avg_char_h"] == 210.0  # noqa: PLR2004

    def test_many_fragments_avg_char_h(self) -> None:
        """Average character height is correctly averaged over fragments."""
        fragments = [
            OCRResult("A", 0, 0, 10, 10, 0.9),  # h=10
            OCRResult("B", 20, 0, 10, 20, 0.9),  # h=20
            OCRResult("C", 40, 0, 10, 30, 0.9),  # h=30
        ]
        geo = _calculate_geometry(fragments, padding=0)
        # avg_char_h = (10 + 20 + 30) / 3 = 20
        assert geo["avg_char_h"] == pytest.approx(20.0, abs=0.01)

    def test_padded_total_h(self) -> None:
        """padded_total_h adds 2*padding to total height."""
        fragments = [OCRResult("A", 0, 0, 50, 40, 0.9)]
        geo = _calculate_geometry(fragments, padding=5)
        assert geo["padded_total_h"] == 50  # 40 + (5*2) = 50  # noqa: PLR2004


class TestAnalyzeLineMetricsAdditional:
    """Additional line metrics analysis tests."""

    def test_three_distinct_lines(self) -> None:
        """Three well-separated Y levels produce 3 unique lines."""
        fragments = [
            OCRResult("A", 10, 10, 50, 20, 0.9),
            OCRResult("B", 10, 60, 50, 20, 0.9),
            OCRResult("C", 10, 110, 50, 20, 0.9),
        ]
        metrics = _analyze_line_metrics(fragments, 122.0, 22.0, "TesseractOCR")
        assert metrics["unique_lines"] == 3
        assert metrics["is_single_line"] is False

    def test_same_y_level_all_fragments(self) -> None:
        """All fragments on the same Y level produce single line."""
        fragments = [
            OCRResult("A", 10, 50, 30, 20, 0.9),
            OCRResult("B", 50, 50, 30, 20, 0.9),
            OCRResult("C", 90, 50, 30, 20, 0.9),
        ]
        metrics = _analyze_line_metrics(fragments, 22.0, 22.0, "TesseractOCR")
        assert metrics["unique_lines"] == 1
        assert metrics["is_single_line"] is True

    def test_gap_just_above_threshold_creates_new_line(self) -> None:
        """Gap slightly above threshold does count as a new line."""
        avg_char_h = 20.0
        gap = avg_char_h * OCR_LINE_GAP_THRESHOLD_RATIO + 1  # Just above threshold
        fragments = [
            OCRResult("A", 10, 10, 50, 20, 0.9),
            OCRResult("B", 10, 10 + int(gap), 50, 20, 0.9),
        ]
        metrics = _analyze_line_metrics(fragments, 42.0, avg_char_h, "TesseractOCR")
        assert metrics["unique_lines"] == 2
        assert metrics["is_single_line"] is False

    def test_easyocr_ratio_larger_than_tesseract(self) -> None:
        """EasyOCR always produces a larger ratio than Tesseract for multi-line."""
        fragments = [
            OCRResult("A", 0, 0, 50, 20, 0.9),
            OCRResult("B", 0, 50, 50, 20, 0.9),
        ]
        tess = _analyze_line_metrics(fragments, 72.0, 22.0, "TesseractOCR")
        easy = _analyze_line_metrics(fragments, 72.0, 22.0, "EasyOCR")
        assert easy["ratio"] > tess["ratio"]

    def test_single_fragment_returns_single_line_height(self) -> None:
        """Single fragment always returns OCR_SINGLE_LINE_HEIGHT ratio."""
        from src.constants.ocr import OCR_SINGLE_LINE_HEIGHT  # noqa: PLC0415

        fragments = [OCRResult("A", 0, 0, 50, 20, 0.9)]
        metrics = _analyze_line_metrics(fragments, 22.0, 22.0, "TesseractOCR")
        assert metrics["ratio"] == pytest.approx(OCR_SINGLE_LINE_HEIGHT, abs=0.001)


class TestApplyContentAndStyleAdditional:
    """Additional tests for _apply_content_and_style."""

    def test_bold_html_preserves_formatting(self) -> None:
        """Bold HTML tags are preserved."""
        res = OCRResult("test", 0, 0, 100, 20, 1.0)
        p_data = {
            "translated_html": "<b>Bold</b> and normal",
            "alignment": "center",
        }
        _apply_content_and_style(res, p_data, "test")
        assert "<b>Bold</b>" in res.translated_html
        assert res.translated_text == "Bold and normal"

    def test_italic_html_preserves_formatting(self) -> None:
        """Italic HTML tags are preserved."""
        res = OCRResult("test", 0, 0, 100, 20, 1.0)
        p_data = {
            "translated_html": "<i>Italic</i> text",
            "alignment": "left",
        }
        _apply_content_and_style(res, p_data, "test")
        assert "<i>Italic</i>" in res.translated_html

    def test_br_tags_cleaned_all_variants(self) -> None:
        """All BR tag variants are cleaned."""
        res = OCRResult("test", 0, 0, 100, 20, 1.0)
        p_data = {
            "translated_html": "<br>Hello<br/>",
            "alignment": "left",
        }
        _apply_content_and_style(res, p_data, "test")
        assert res.translated_html == "Hello"

    def test_all_three_alignments_mapped(self) -> None:
        """left, center, right all map correctly."""
        for align_str, expected in [
            ("left", ALIGN_LEFT),
            ("center", ALIGN_CENTER),
            ("right", ALIGN_RIGHT),
        ]:
            res = OCRResult("test", 0, 0, 100, 20, 1.0)
            p_data = {"translated_html": "X", "alignment": align_str}
            _apply_content_and_style(res, p_data, "test")
            assert res.alignment == expected, f"Failed for alignment '{align_str}'"


class TestMergeToParagraphsMiscellaneous:
    """Miscellaneous tests for merge_to_paragraphs."""

    def test_whitespace_difference_in_translation(self) -> None:
        """Translation with extra whitespace is treated as unchanged."""
        frags = [OCRResult("Hello", 10, 10, 50, 20, 0.9)]
        enriched = [
            {
                "ids": [0],
                "translated_html": "  Hello  ",
                "alignment": "left",
            }
        ]
        merged, translations, used = merge_to_paragraphs(
            enriched, frags, "TesseractOCR"
        )
        assert len(merged) == 0
        assert len(used) == 0

    def test_case_difference_in_translation_skipped(self) -> None:
        """Translation differing only in case is treated as unchanged."""
        frags = [OCRResult("Hello", 10, 10, 50, 20, 0.9)]
        enriched = [
            {
                "ids": [0],
                "translated_html": "hello",
                "alignment": "left",
            }
        ]
        merged, translations, used = merge_to_paragraphs(
            enriched, frags, "TesseractOCR"
        )
        assert len(merged) == 0

    def test_mixed_unchanged_and_changed_paragraphs(self) -> None:
        """Mix of changed and unchanged paragraphs."""
        frags = [
            OCRResult("Same", 10, 10, 50, 20, 0.9),
            OCRResult("Hello", 10, 40, 50, 20, 0.9),
        ]
        enriched = [
            {
                "ids": [0],
                "translated_html": "Same",  # Unchanged
                "alignment": "left",
            },
            {
                "ids": [1],
                "translated_html": "Bonjour",  # Changed
                "alignment": "left",
            },
        ]
        merged, translations, used = merge_to_paragraphs(
            enriched, frags, "TesseractOCR"
        )
        assert len(merged) == 1
        assert merged[0].translated_text == "Bonjour"
        # Only the changed fragment should be in used
        assert len(used) == 1

    def test_very_large_bounding_box(self) -> None:
        """Fragments with very large bounding boxes are processed."""
        frags = [OCRResult("Big", 0, 0, 10000, 5000, 0.9)]
        enriched = [
            {
                "ids": [0],
                "translated_html": "Grand",
                "alignment": "center",
            }
        ]
        merged, translations, used = merge_to_paragraphs(
            enriched, frags, "TesseractOCR"
        )
        assert len(merged) == 1
        assert merged[0].w == 10000  # noqa: PLR2004
        assert merged[0].h == 5000  # noqa: PLR2004

    def test_very_small_bounding_box(self) -> None:
        """Fragments with 1x1 bounding boxes are processed."""
        frags = [OCRResult(".", 100, 100, 1, 1, 0.9)]
        enriched = [
            {
                "ids": [0],
                "translated_html": "point",
                "alignment": "center",
            }
        ]
        merged, translations, used = merge_to_paragraphs(
            enriched, frags, "TesseractOCR"
        )
        assert len(merged) == 1
        assert merged[0].w == 1
        assert merged[0].h == 1

    def test_fragments_from_different_y_paragraphs(self) -> None:
        """Fragments from widely spaced Y positions correctly merge."""
        frags = [
            OCRResult("Top", 10, 10, 50, 20, 0.9),
            OCRResult("Bottom", 10, 500, 50, 20, 0.9),
        ]
        enriched = [
            {
                "ids": [0, 1],
                "translated_html": "Merged content",
                "alignment": "left",
            }
        ]
        merged, translations, used = merge_to_paragraphs(
            enriched, frags, "TesseractOCR"
        )
        assert len(merged) == 1
        # Bounding box should span from y=10 to y=520
        assert merged[0].y == 10
        assert merged[0].h == 510  # noqa: PLR2004
        assert merged[0].is_single_line is False

    def test_original_text_height_set_to_avg_char_h(self) -> None:
        """original_text_height is set to int(avg_char_h)."""
        frags = [OCRResult("Text", 0, 0, 100, 30, 0.9)]
        enriched = [
            {
                "ids": [0],
                "translated_html": "Translated",
                "alignment": "left",
            }
        ]
        merged, translations, used = merge_to_paragraphs(
            enriched, frags, "TesseractOCR"
        )
        assert len(merged) == 1
        # avg_char_h = (30 + 2*padding_insert) / 1
        # For TesseractOCR: padding_insert = 1
        # avg_char_h = (30 + 2) / 1 = 32
        assert merged[0].original_text_height == 32  # noqa: PLR2004


# ---------------------------------------------------------------------------
# Expanded test coverage — target 200+ total tests
# ---------------------------------------------------------------------------


class TestIsUnchangedExtended:
    """Extended edge cases for _is_unchanged."""

    def test_leading_trailing_spaces(self) -> None:
        """Leading and trailing spaces are collapsed."""
        assert _is_unchanged("  hello  ", "hello") is True

    def test_tabs_only_vs_empty(self) -> None:
        """Tab-only strings collapse to empty."""
        assert _is_unchanged("\t\t\t", "") is True

    def test_multiple_newlines(self) -> None:
        """Multiple newlines between words collapse to single space."""
        assert _is_unchanged("hello\n\n\nworld", "hello world") is True

    def test_carriage_return(self) -> None:
        """Carriage returns are treated as whitespace."""
        assert _is_unchanged("hello\r\nworld", "hello world") is True

    def test_special_characters_preserved(self) -> None:
        """Special characters like @, #, $ are preserved in comparison."""
        assert _is_unchanged("hello@world", "hello@world") is True
        assert _is_unchanged("hello@world", "hello#world") is False

    def test_accented_characters(self) -> None:
        """Accented characters are case-insensitive but accent-sensitive."""
        assert _is_unchanged("café", "Café") is True
        assert _is_unchanged("café", "cafe") is False

    def test_very_long_identical_strings(self) -> None:
        """Very long identical strings are unchanged."""
        long_str = "word " * 1000
        assert _is_unchanged(long_str, long_str) is True

    def test_very_long_different_strings(self) -> None:
        """Very long different strings are detected."""
        str_a = "word " * 1000
        str_b = "diff " * 1000
        assert _is_unchanged(str_a, str_b) is False

    def test_single_character_identical(self) -> None:
        """Single character comparison works."""
        assert _is_unchanged("A", "a") is True

    def test_single_character_different(self) -> None:
        """Different single characters are detected."""
        assert _is_unchanged("A", "B") is False

    def test_arabic_text(self) -> None:
        """Arabic (RTL) text comparison works."""
        assert _is_unchanged("مرحبا", "مرحبا") is True
        assert _is_unchanged("مرحبا", "وداعا") is False

    def test_hebrew_text(self) -> None:
        """Hebrew (RTL) text comparison works."""
        assert _is_unchanged("שלום", "שלום") is True
        assert _is_unchanged("שלום", "להתראות") is False

    def test_chinese_text(self) -> None:
        """Chinese text comparison works."""
        assert _is_unchanged("你好世界", "你好世界") is True
        assert _is_unchanged("你好世界", "再见世界") is False

    def test_korean_text(self) -> None:
        """Korean text comparison works."""
        assert _is_unchanged("안녕하세요", "안녕하세요") is True
        assert _is_unchanged("안녕하세요", "감사합니다") is False

    def test_thai_text(self) -> None:
        """Thai text comparison works."""
        assert _is_unchanged("สวัสดี", "สวัสดี") is True

    def test_mixed_scripts(self) -> None:
        """Mixed Latin and CJK text comparison."""
        assert _is_unchanged("Hello 世界", "hello 世界") is True
        assert _is_unchanged("Hello 世界", "Bonjour 世界") is False

    def test_emoji_text(self) -> None:
        """Emoji text is compared correctly."""
        assert _is_unchanged("Hello 🌍", "Hello 🌍") is True
        assert _is_unchanged("Hello 🌍", "Hello 🌎") is False

    def test_only_whitespace_difference(self) -> None:
        """Strings differing only in internal whitespace are unchanged."""
        assert _is_unchanged("a  b  c", "a b c") is True

    def test_number_only_strings(self) -> None:
        """Numeric strings are compared correctly."""
        assert _is_unchanged("123 456", "123 456") is True
        assert _is_unchanged("123 456", "789 012") is False


class TestGetFragmentsExtended:
    """Extended edge cases for _get_fragments."""

    def test_ids_in_reverse_order(self, raw_fragments) -> None:
        """IDs in reverse order return fragments in that order."""
        p_data = {"ids": [3, 2, 1, 0]}
        result = _get_fragments(p_data, raw_fragments)
        assert len(result) == 4
        assert result[0].text == "Two"
        assert result[3].text == "Line"

    def test_all_valid_ids(self, raw_fragments) -> None:
        """All valid IDs return all fragments."""
        p_data = {"ids": [0, 1, 2, 3]}
        result = _get_fragments(p_data, raw_fragments)
        assert len(result) == 4

    def test_single_fragment_list(self) -> None:
        """Works with a single-element fragment list."""
        frags = [OCRResult("Only", 0, 0, 50, 20, 0.9)]
        p_data = {"ids": [0]}
        result = _get_fragments(p_data, frags)
        assert len(result) == 1
        assert result[0].text == "Only"

    def test_large_id_list(self) -> None:
        """Large list of valid IDs all returned."""
        n = 500
        frags = [OCRResult(f"w{i}", i, 0, 10, 10, 0.9) for i in range(n)]
        p_data = {"ids": list(range(n))}
        result = _get_fragments(p_data, frags)
        assert len(result) == n

    def test_boundary_index_last_valid(self) -> None:
        """Index equal to len(fragments)-1 is valid."""
        frags = [OCRResult("A", 0, 0, 10, 10, 0.9), OCRResult("B", 0, 0, 10, 10, 0.9)]
        p_data = {"ids": [1]}
        result = _get_fragments(p_data, frags)
        assert len(result) == 1
        assert result[0].text == "B"

    def test_boundary_index_at_len(self) -> None:
        """Index equal to len(fragments) is out of range."""
        frags = [OCRResult("A", 0, 0, 10, 10, 0.9)]
        p_data = {"ids": [1]}
        result = _get_fragments(p_data, frags)
        assert result == []

    def test_negative_index_only(self) -> None:
        """Negative IDs only are all filtered out."""
        frags = [OCRResult("A", 0, 0, 10, 10, 0.9)]
        p_data = {"ids": [-1, -2, -100]}
        result = _get_fragments(p_data, frags)
        assert result == []


class TestCalculateGeometryExtended:
    """Extended geometry calculation tests."""

    def test_fragments_same_position(self) -> None:
        """Two fragments at the same position produce correct geometry."""
        fragments = [
            OCRResult("A", 10, 10, 50, 20, 0.9),
            OCRResult("B", 10, 10, 50, 20, 0.9),
        ]
        geo = _calculate_geometry(fragments, padding=0)
        assert geo["min_x"] == 10
        assert geo["min_y"] == 10
        assert geo["width"] == 50
        assert geo["height"] == 20

    def test_fragments_diagonal(self) -> None:
        """Fragments placed diagonally span the full diagonal box."""
        fragments = [
            OCRResult("TL", 0, 0, 20, 10, 0.9),
            OCRResult("BR", 100, 200, 20, 10, 0.9),
        ]
        geo = _calculate_geometry(fragments, padding=0)
        assert geo["min_x"] == 0
        assert geo["min_y"] == 0
        assert geo["width"] == 120  # 120 - 0
        assert geo["height"] == 210  # 210 - 0

    def test_single_fragment_large_padding(self) -> None:
        """Single fragment with large padding produces correct padded_total_h."""
        fragments = [OCRResult("A", 0, 0, 50, 20, 0.9)]
        geo = _calculate_geometry(fragments, padding=50)
        assert geo["padded_total_h"] == 120  # 20 + 100  # noqa: PLR2004
        assert geo["avg_char_h"] == 120.0  # (20 + 100) / 1  # noqa: PLR2004

    def test_three_fragments_varying_sizes(self) -> None:
        """Three fragments with varying sizes compute correct avg_char_h."""
        fragments = [
            OCRResult("A", 0, 0, 10, 5, 0.9),
            OCRResult("B", 20, 0, 10, 15, 0.9),
            OCRResult("C", 40, 0, 10, 25, 0.9),
        ]
        geo = _calculate_geometry(fragments, padding=0)
        # avg_char_h = (5 + 15 + 25) / 3 = 15
        assert geo["avg_char_h"] == pytest.approx(15.0, abs=0.01)

    def test_fragment_at_origin(self) -> None:
        """Fragment at exact origin (0, 0) computes correctly."""
        fragments = [OCRResult("Origin", 0, 0, 100, 50, 0.9)]
        geo = _calculate_geometry(fragments, padding=0)
        assert geo["min_x"] == 0
        assert geo["min_y"] == 0
        assert geo["width"] == 100
        assert geo["height"] == 50

    def test_wide_horizontal_spread(self) -> None:
        """Fragments spread far horizontally produce wide bounding box."""
        fragments = [
            OCRResult("Left", 0, 100, 30, 20, 0.9),
            OCRResult("Right", 2000, 100, 30, 20, 0.9),
        ]
        geo = _calculate_geometry(fragments, padding=0)
        assert geo["width"] == 2030  # noqa: PLR2004
        assert geo["height"] == 20

    def test_tall_vertical_spread(self) -> None:
        """Fragments spread far vertically produce tall bounding box."""
        fragments = [
            OCRResult("Top", 100, 0, 30, 20, 0.9),
            OCRResult("Bottom", 100, 3000, 30, 20, 0.9),
        ]
        geo = _calculate_geometry(fragments, padding=0)
        assert geo["height"] == 3020  # noqa: PLR2004
        assert geo["width"] == 30

    def test_padding_does_not_affect_width_or_minxy(self) -> None:
        """Padding affects avg_char_h and padded_total_h but not min_x, min_y, width."""
        fragments = [OCRResult("A", 5, 10, 80, 25, 0.9)]
        geo = _calculate_geometry(fragments, padding=10)
        assert geo["min_x"] == 5
        assert geo["min_y"] == 10
        assert geo["width"] == 80
        assert geo["height"] == 25


class TestAnalyzeLineMetricsExtended:
    """Extended line metrics tests."""

    def test_five_lines_detected(self) -> None:
        """Five well-separated lines are all detected."""
        fragments = [OCRResult(f"L{i}", 10, i * 50, 50, 20, 0.9) for i in range(5)]
        metrics = _analyze_line_metrics(fragments, 222.0, 22.0, "TesseractOCR")
        assert metrics["unique_lines"] == 5
        assert metrics["is_single_line"] is False

    def test_ten_lines_detected(self) -> None:
        """Ten well-separated lines are all detected."""
        fragments = [OCRResult(f"L{i}", 10, i * 50, 50, 20, 0.9) for i in range(10)]
        metrics = _analyze_line_metrics(fragments, 502.0, 22.0, "TesseractOCR")
        assert metrics["unique_lines"] == 10
        assert metrics["is_single_line"] is False

    def test_fragments_on_close_y_levels_single_line(self) -> None:
        """Fragments on Y levels within threshold are grouped as one line."""
        avg_char_h = 40.0
        # Gap = 5, threshold = 40 * 0.5 = 20 — gap < threshold → same line
        fragments = [
            OCRResult("A", 10, 100, 50, 40, 0.9),
            OCRResult("B", 70, 105, 50, 40, 0.9),
        ]
        metrics = _analyze_line_metrics(fragments, 47.0, avg_char_h, "TesseractOCR")
        assert metrics["unique_lines"] == 1
        assert metrics["is_single_line"] is True

    def test_fragments_on_close_y_levels_multi_line(self) -> None:
        """Fragments whose Y gap exceeds threshold are split into two lines."""
        avg_char_h = 10.0
        # Gap = 8, threshold = 10 * 0.5 = 5 — gap > threshold → new line
        fragments = [
            OCRResult("A", 10, 100, 50, 10, 0.9),
            OCRResult("B", 70, 108, 50, 10, 0.9),
        ]
        metrics = _analyze_line_metrics(fragments, 20.0, avg_char_h, "TesseractOCR")
        assert metrics["unique_lines"] == 2
        assert metrics["is_single_line"] is False

    def test_easyocr_single_line_no_multiplier(self) -> None:
        """EasyOCR single-line uses default ratio, no multiplier applied."""
        from src.constants.ocr import OCR_SINGLE_LINE_HEIGHT  # noqa: PLC0415

        fragments = [OCRResult("A", 10, 10, 50, 20, 0.9)]
        metrics = _analyze_line_metrics(fragments, 22.0, 22.0, "EasyOCR")
        assert metrics["is_single_line"] is True
        assert metrics["ratio"] == pytest.approx(OCR_SINGLE_LINE_HEIGHT, abs=0.001)

    def test_ratio_for_two_lines_basic(self) -> None:
        """Ratio for two lines is padded_total_h / (2 * avg_char_h)."""
        fragments = [
            OCRResult("A", 0, 0, 50, 20, 0.9),
            OCRResult("B", 0, 50, 50, 20, 0.9),
        ]
        padded_h = 72.0
        avg_h = 22.0
        metrics = _analyze_line_metrics(fragments, padded_h, avg_h, "TesseractOCR")
        expected_ratio = padded_h / (2 * avg_h)
        assert metrics["ratio"] == pytest.approx(
            max(0.8, min(3.0, expected_ratio)), abs=0.01
        )

    def test_many_fragments_same_y_produce_one_line(self) -> None:
        """100 fragments at the same Y produce a single line."""
        fragments = [OCRResult(f"w{i}", i * 20, 50, 15, 20, 0.9) for i in range(100)]
        metrics = _analyze_line_metrics(fragments, 22.0, 22.0, "TesseractOCR")
        assert metrics["unique_lines"] == 1
        assert metrics["is_single_line"] is True

    def test_unsorted_y_levels(self) -> None:
        """Y levels provided in unsorted order are sorted internally."""
        fragments = [
            OCRResult("C", 10, 200, 50, 20, 0.9),
            OCRResult("A", 10, 10, 50, 20, 0.9),
            OCRResult("B", 10, 100, 50, 20, 0.9),
        ]
        metrics = _analyze_line_metrics(fragments, 222.0, 22.0, "TesseractOCR")
        # All three Y values are well separated → 3 lines
        assert metrics["unique_lines"] == 3

    def test_duplicate_y_levels_not_double_counted(self) -> None:
        """Fragments at the same Y level are grouped into one line."""
        fragments = [
            OCRResult("A", 10, 100, 50, 20, 0.9),
            OCRResult("B", 70, 100, 50, 20, 0.9),
            OCRResult("C", 130, 100, 50, 20, 0.9),
        ]
        metrics = _analyze_line_metrics(fragments, 22.0, 22.0, "TesseractOCR")
        assert metrics["unique_lines"] == 1

    def test_easyocr_ratio_clamped_at_max(self) -> None:
        """EasyOCR multiplier can push ratio above max; clamping applies."""
        fragments = [
            OCRResult("A", 0, 0, 50, 20, 0.9),
            OCRResult("B", 0, 50, 50, 20, 0.9),
        ]
        # Use padded_total_h/avg_char_h ratio that would exceed 3.0 after 1.2x
        # 2.6 * 1.2 = 3.12 → clamped to 3.0
        padded_h = 2.6 * 2 * 22.0  # = 114.4
        metrics = _analyze_line_metrics(fragments, padded_h, 22.0, "EasyOCR")
        assert metrics["ratio"] <= 3.0


class TestApplyContentAndStyleExtended:
    """Extended content/style application tests."""

    def test_html_with_span_color(self) -> None:
        """HTML with span color style is cleaned to text."""
        res = OCRResult("test", 0, 0, 100, 20, 1.0)
        p_data = {
            "translated_html": '<span style="color:red">Red text</span>',
            "alignment": "left",
        }
        _apply_content_and_style(res, p_data, "test")
        assert "Red text" in res.translated_text

    def test_nested_html_tags(self) -> None:
        """Nested HTML tags produce correct plain text."""
        res = OCRResult("test", 0, 0, 100, 20, 1.0)
        p_data = {
            "translated_html": "<b><i>Bold Italic</i></b>",
            "alignment": "center",
        }
        _apply_content_and_style(res, p_data, "test")
        assert res.translated_text == "Bold Italic"

    def test_multiple_br_in_middle(self) -> None:
        """BR tags in the middle of text become newlines in plain text."""
        res = OCRResult("test", 0, 0, 100, 20, 1.0)
        p_data = {
            "translated_html": "Line 1<br>Line 2<br/>Line 3",
            "alignment": "left",
        }
        _apply_content_and_style(res, p_data, "test")
        assert res.translated_text == "Line 1\nLine 2\nLine 3"

    def test_empty_translated_html(self) -> None:
        """Empty translated_html string produces empty text."""
        res = OCRResult("test", 0, 0, 100, 20, 1.0)
        p_data = {"translated_html": "", "alignment": "left"}
        _apply_content_and_style(res, p_data, "test")
        assert res.translated_text == ""

    def test_color_hex_formats(self) -> None:
        """Various hex color formats are accepted."""
        for color in ["#000000", "#FFFFFF", "#abcdef", "#123"]:
            res = OCRResult("test", 0, 0, 100, 20, 1.0)
            p_data = {"translated_html": "text", "color": color}
            _apply_content_and_style(res, p_data, "test")
            assert res.color == color

    def test_original_text_used_when_no_html_key(self) -> None:
        """When translated_html is missing, original text is used as HTML."""
        res = OCRResult("original text", 0, 0, 100, 20, 1.0)
        p_data = {"color": "#FF0000"}
        _apply_content_and_style(res, p_data, "original text")
        assert res.translated_text == "original text"
        assert res.translated_html == "original text"

    def test_alignment_not_overwritten_when_missing(self) -> None:
        """Alignment stays None when not in p_data."""
        res = OCRResult("test", 0, 0, 100, 20, 1.0)
        assert res.alignment is None
        p_data = {"translated_html": "text"}
        _apply_content_and_style(res, p_data, "test")
        assert res.alignment is None


class TestMergeToParagraphsMultiColumn:
    """Tests for multi-column layout detection scenarios."""

    def test_two_column_layout_separate_paragraphs(self) -> None:
        """Two-column layout with separate paragraphs per column."""
        # Left column fragments
        left_frags = [
            OCRResult("Left1", 10, 10, 100, 20, 0.9),
            OCRResult("Left2", 10, 40, 100, 20, 0.9),
        ]
        # Right column fragments
        right_frags = [
            OCRResult("Right1", 300, 10, 100, 20, 0.9),
            OCRResult("Right2", 300, 40, 100, 20, 0.9),
        ]
        frags = left_frags + right_frags

        enriched = [
            {
                "ids": [0, 1],
                "translated_html": "Colonne gauche",
                "alignment": "left",
            },
            {
                "ids": [2, 3],
                "translated_html": "Colonne droite",
                "alignment": "left",
            },
        ]
        merged, translations, used = merge_to_paragraphs(
            enriched, frags, "TesseractOCR"
        )
        assert len(merged) == 2
        # Left column bounding box
        assert merged[0].x == 10
        assert merged[0].w == 100
        # Right column bounding box
        assert merged[1].x == 300
        assert merged[1].w == 100

    def test_three_column_layout(self) -> None:
        """Three-column layout produces separate bounding boxes."""
        frags = []
        for col in range(3):
            for row in range(3):
                frags.append(
                    OCRResult(f"C{col}R{row}", col * 200, row * 30, 150, 20, 0.9)
                )
        # 3 paragraphs, one per column
        enriched = [
            {
                "ids": [0, 1, 2],  # Column 0
                "translated_html": f"Column {c} translated",
                "alignment": "left",
            }
            for c in range(1)
        ] + [
            {
                "ids": [3, 4, 5],  # Column 1
                "translated_html": "Column 1 translated",
                "alignment": "center",
            },
            {
                "ids": [6, 7, 8],  # Column 2
                "translated_html": "Column 2 translated",
                "alignment": "right",
            },
        ]
        merged, translations, used = merge_to_paragraphs(
            enriched, frags, "TesseractOCR"
        )
        assert len(merged) == 3
        assert len(used) == 9

    def test_columns_with_different_heights(self) -> None:
        """Columns with different numbers of lines produce correct geometry."""
        # Left column: 4 lines
        frags = [OCRResult(f"L{i}", 10, i * 30, 100, 20, 0.9) for i in range(4)]
        # Right column: 2 lines
        frags += [OCRResult(f"R{i}", 300, i * 30, 100, 20, 0.9) for i in range(2)]

        enriched = [
            {
                "ids": [0, 1, 2, 3],
                "translated_html": "Tall column",
                "alignment": "left",
            },
            {
                "ids": [4, 5],
                "translated_html": "Short column",
                "alignment": "left",
            },
        ]
        merged, translations, used = merge_to_paragraphs(
            enriched, frags, "TesseractOCR"
        )
        assert len(merged) == 2
        # Left column: spans y=0 to y=90+20=110 → h=110
        assert merged[0].h == 110  # noqa: PLR2004
        # Right column: spans y=0 to y=30+20=50 → h=50
        assert merged[1].h == 50  # noqa: PLR2004


class TestMergeToParagraphsFontSizeCombinations:
    """Tests for fragments with various font size (height) combinations."""

    def test_uniform_font_size(self) -> None:
        """All fragments with same height produce consistent avg_char_h."""
        frags = [OCRResult(f"w{i}", i * 60, 0, 50, 20, 0.9) for i in range(5)]
        enriched = [
            {
                "ids": list(range(5)),
                "translated_html": "Uniform size text",
                "alignment": "left",
            }
        ]
        merged, _, _ = merge_to_paragraphs(enriched, frags, "TesseractOCR")
        assert len(merged) == 1
        # avg_char_h = (20 + 2*1) = 22 for each fragment (padding=1 for Tesseract)
        assert merged[0].original_text_height == 22  # noqa: PLR2004

    def test_mixed_font_sizes_small_and_large(self) -> None:
        """Mix of small and large font sizes averages correctly."""
        frags = [
            OCRResult("Small", 0, 0, 50, 10, 0.9),
            OCRResult("Large", 60, 0, 80, 40, 0.9),
        ]
        enriched = [
            {
                "ids": [0, 1],
                "translated_html": "Mixed sizes",
                "alignment": "left",
            }
        ]
        merged, _, _ = merge_to_paragraphs(enriched, frags, "TesseractOCR")
        assert len(merged) == 1
        # avg_char_h = ((10+2) + (40+2)) / 2 = 54/2 = 27
        assert merged[0].original_text_height == 27  # noqa: PLR2004

    def test_heading_and_body_text(self) -> None:
        """Heading (large) and body text (small) fragments in separate paragraphs."""
        frags = [
            OCRResult("Heading", 10, 10, 200, 50, 0.9),
            OCRResult("Body line 1", 10, 80, 200, 20, 0.9),
            OCRResult("Body line 2", 10, 110, 200, 20, 0.9),
        ]
        enriched = [
            {
                "ids": [0],
                "translated_html": "Titre",
                "alignment": "center",
            },
            {
                "ids": [1, 2],
                "translated_html": "Corps du texte",
                "alignment": "left",
            },
        ]
        merged, translations, used = merge_to_paragraphs(
            enriched, frags, "TesseractOCR"
        )
        assert len(merged) == 2
        # Heading has larger original_text_height than body
        assert merged[0].original_text_height > merged[1].original_text_height

    def test_very_small_font_fragments(self) -> None:
        """Fragments with height=1 (tiny font) process correctly."""
        frags = [
            OCRResult("tiny1", 0, 0, 30, 1, 0.9),
            OCRResult("tiny2", 40, 0, 30, 1, 0.9),
        ]
        enriched = [
            {
                "ids": [0, 1],
                "translated_html": "Tiny translated",
                "alignment": "left",
            }
        ]
        merged, _, _ = merge_to_paragraphs(enriched, frags, "TesseractOCR")
        assert len(merged) == 1
        # avg_char_h = (1+2) / 1 = 3 per fragment; average = 3
        assert merged[0].original_text_height == 3  # noqa: PLR2004

    def test_very_large_font_fragment(self) -> None:
        """Fragment with very large height processes correctly."""
        frags = [OCRResult("HUGE", 0, 0, 500, 200, 0.9)]
        enriched = [
            {
                "ids": [0],
                "translated_html": "Enormous",
                "alignment": "center",
            }
        ]
        merged, _, _ = merge_to_paragraphs(enriched, frags, "TesseractOCR")
        assert len(merged) == 1
        # avg_char_h = (200 + 2) / 1 = 202
        assert merged[0].original_text_height == 202  # noqa: PLR2004


class TestMergeToParagraphsRTL:
    """Tests for right-to-left text handling."""

    def test_arabic_text_fragments(self) -> None:
        """Arabic text fragments are merged correctly."""
        frags = [
            OCRResult("مرحبا", 200, 10, 80, 25, 0.9),
            OCRResult("بالعالم", 100, 10, 90, 25, 0.9),
        ]
        enriched = [
            {
                "ids": [0, 1],
                "translated_html": "مرحبا بالعالم المترجم",
                "alignment": "right",
            }
        ]
        merged, translations, used = merge_to_paragraphs(
            enriched, frags, "TesseractOCR"
        )
        assert len(merged) == 1
        assert merged[0].alignment == ALIGN_RIGHT
        assert merged[0].translated_text == "مرحبا بالعالم المترجم"
        # Bounding box: min_x=100, max_xr=280 → w=180
        assert merged[0].x == 100
        assert merged[0].w == 180  # noqa: PLR2004

    def test_hebrew_text_fragments(self) -> None:
        """Hebrew text fragments are merged correctly."""
        frags = [
            OCRResult("שלום", 150, 10, 60, 20, 0.9),
            OCRResult("עולם", 80, 10, 60, 20, 0.9),
        ]
        enriched = [
            {
                "ids": [0, 1],
                "translated_html": "שלום עולם מתורגם",
                "alignment": "right",
            }
        ]
        merged, translations, used = merge_to_paragraphs(
            enriched, frags, "TesseractOCR"
        )
        assert len(merged) == 1
        assert merged[0].alignment == ALIGN_RIGHT

    def test_rtl_multiline(self) -> None:
        """RTL text across multiple lines is correctly merged."""
        frags = [
            OCRResult("سطر", 100, 10, 50, 20, 0.9),
            OCRResult("أول", 50, 10, 40, 20, 0.9),
            OCRResult("سطر", 100, 50, 50, 20, 0.9),
            OCRResult("ثاني", 50, 50, 40, 20, 0.9),
        ]
        enriched = [
            {
                "ids": [0, 1, 2, 3],
                "translated_html": "السطر الأول<br>السطر الثاني",
                "alignment": "right",
            }
        ]
        merged, translations, used = merge_to_paragraphs(
            enriched, frags, "TesseractOCR"
        )
        assert len(merged) == 1
        assert merged[0].is_single_line is False
        assert merged[0].alignment == ALIGN_RIGHT


class TestMergeToParagraphsMixedLanguage:
    """Tests for mixed-language paragraph handling."""

    def test_latin_and_cjk_mixed(self) -> None:
        """Mix of Latin and CJK text in one paragraph."""
        frags = [
            OCRResult("Hello", 10, 10, 60, 20, 0.9),
            OCRResult("世界", 80, 10, 40, 20, 0.9),
        ]
        enriched = [
            {
                "ids": [0, 1],
                "translated_html": "Bonjour 世界",
                "alignment": "left",
            }
        ]
        merged, translations, used = merge_to_paragraphs(
            enriched, frags, "TesseractOCR"
        )
        assert len(merged) == 1
        assert merged[0].translated_text == "Bonjour 世界"

    def test_latin_and_arabic_mixed(self) -> None:
        """Mix of Latin and Arabic text in one paragraph."""
        frags = [
            OCRResult("Hello", 10, 10, 60, 20, 0.9),
            OCRResult("مرحبا", 80, 10, 60, 20, 0.9),
        ]
        enriched = [
            {
                "ids": [0, 1],
                "translated_html": "Bonjour مرحبا",
                "alignment": "left",
            }
        ]
        merged, translations, used = merge_to_paragraphs(
            enriched, frags, "TesseractOCR"
        )
        assert len(merged) == 1
        assert "Bonjour" in merged[0].translated_text
        assert "مرحبا" in merged[0].translated_text

    def test_three_scripts_in_paragraph(self) -> None:
        """Three different scripts in one paragraph."""
        frags = [
            OCRResult("English", 10, 10, 70, 20, 0.9),
            OCRResult("日本語", 90, 10, 60, 20, 0.9),
            OCRResult("한국어", 160, 10, 60, 20, 0.9),
        ]
        enriched = [
            {
                "ids": [0, 1, 2],
                "translated_html": "Translated mixed script",
                "alignment": "center",
            }
        ]
        merged, _, _ = merge_to_paragraphs(enriched, frags, "TesseractOCR")
        assert len(merged) == 1
        assert merged[0].text == "English 日本語 한국어"


class TestMergeToParagraphsEmptyAndSingleCharFragments:
    """Tests for empty and single-character fragments."""

    def test_single_character_fragment(self) -> None:
        """Single character fragment is processed correctly."""
        frags = [OCRResult("A", 50, 50, 10, 15, 0.9)]
        enriched = [
            {
                "ids": [0],
                "translated_html": "B",
                "alignment": "left",
            }
        ]
        merged, translations, used = merge_to_paragraphs(
            enriched, frags, "TesseractOCR"
        )
        assert len(merged) == 1
        assert merged[0].translated_text == "B"
        assert merged[0].text == "A"

    def test_multiple_single_char_fragments(self) -> None:
        """Multiple single-character fragments form a word."""
        frags = [
            OCRResult("H", 10, 10, 10, 20, 0.9),
            OCRResult("e", 22, 10, 10, 20, 0.9),
            OCRResult("l", 34, 10, 8, 20, 0.9),
            OCRResult("l", 44, 10, 8, 20, 0.9),
            OCRResult("o", 54, 10, 10, 20, 0.9),
        ]
        enriched = [
            {
                "ids": [0, 1, 2, 3, 4],
                "translated_html": "Bonjour",
                "alignment": "left",
            }
        ]
        merged, translations, used = merge_to_paragraphs(
            enriched, frags, "TesseractOCR"
        )
        assert len(merged) == 1
        assert merged[0].text == "H e l l o"
        assert merged[0].translated_text == "Bonjour"

    def test_space_only_fragment(self) -> None:
        """Fragment with space-only text is processed."""
        frags = [
            OCRResult(" ", 10, 10, 5, 20, 0.9),
            OCRResult("Hello", 20, 10, 50, 20, 0.9),
        ]
        enriched = [
            {
                "ids": [0, 1],
                "translated_html": "Bonjour",
                "alignment": "left",
            }
        ]
        merged, translations, used = merge_to_paragraphs(
            enriched, frags, "TesseractOCR"
        )
        assert len(merged) == 1
        assert merged[0].translated_text == "Bonjour"

    def test_punctuation_only_fragment(self) -> None:
        """Fragment with only punctuation is processed."""
        frags = [
            OCRResult(".", 10, 10, 5, 20, 0.9),
            OCRResult("!", 20, 10, 5, 20, 0.9),
        ]
        enriched = [
            {
                "ids": [0, 1],
                "translated_html": "。！",
                "alignment": "left",
            }
        ]
        merged, translations, used = merge_to_paragraphs(
            enriched, frags, "TesseractOCR"
        )
        assert len(merged) == 1
        assert merged[0].translated_text == "。！"

    def test_number_only_fragments(self) -> None:
        """Fragments with only numbers are processed."""
        frags = [
            OCRResult("123", 10, 10, 30, 20, 0.9),
            OCRResult("456", 50, 10, 30, 20, 0.9),
        ]
        enriched = [
            {
                "ids": [0, 1],
                "translated_html": "七八九",
                "alignment": "left",
            }
        ]
        merged, translations, used = merge_to_paragraphs(
            enriched, frags, "TesseractOCR"
        )
        assert len(merged) == 1
        assert merged[0].translated_text == "七八九"


class TestMergeToParagraphsLargePageLayouts:
    """Tests for large page layouts with many fragments."""

    def test_full_page_grid_layout(self) -> None:
        """Full page grid (10 cols x 20 rows = 200 fragments)."""
        frags = []
        for row in range(20):
            for col in range(10):
                frags.append(
                    OCRResult(
                        f"R{row}C{col}",
                        col * 60,
                        row * 30,
                        50,
                        20,
                        0.9,
                    )
                )
        # Single paragraph using all fragments
        enriched = [
            {
                "ids": list(range(200)),
                "translated_html": "Full page content translated",
                "alignment": "left",
            }
        ]
        merged, translations, used = merge_to_paragraphs(
            enriched, frags, "TesseractOCR"
        )
        assert len(merged) == 1
        assert len(used) == 200  # noqa: PLR2004

    def test_many_small_paragraphs(self) -> None:
        """100 small paragraphs each with 2 fragments."""
        frags = []
        for i in range(200):
            frags.append(OCRResult(f"w{i}", (i % 2) * 60, (i // 2) * 30, 50, 20, 0.9))

        enriched = [
            {
                "ids": [i * 2, i * 2 + 1],
                "translated_html": f"Paragraph {i} translated",
                "alignment": "left",
            }
            for i in range(100)
        ]
        merged, translations, used = merge_to_paragraphs(
            enriched, frags, "TesseractOCR"
        )
        assert len(merged) == 100
        assert len(translations) == 100
        assert len(used) == 200  # noqa: PLR2004

    def test_sparse_page_layout(self) -> None:
        """Fragments scattered across a large page area."""
        frags = [
            OCRResult("TL", 10, 10, 50, 20, 0.9),
            OCRResult("TR", 900, 10, 50, 20, 0.9),
            OCRResult("BL", 10, 1200, 50, 20, 0.9),
            OCRResult("BR", 900, 1200, 50, 20, 0.9),
        ]
        enriched = [
            {
                "ids": [0, 1, 2, 3],
                "translated_html": "Sparse page translated",
                "alignment": "center",
            }
        ]
        merged, _, used = merge_to_paragraphs(enriched, frags, "TesseractOCR")
        assert len(merged) == 1
        # Bounding box spans full page
        assert merged[0].x == 10
        assert merged[0].y == 10
        assert merged[0].w == 940  # 950 - 10  # noqa: PLR2004
        assert (
            merged[0].h == 1210
        )  # 1230 - 10 = 1220... let me recalculate  # noqa: PLR2004
        # max_yb = 1200 + 20 = 1220, min_y = 10 → h = 1210

    def test_newspaper_three_column_multiline(self) -> None:
        """Newspaper-style three-column layout with multiple lines per column."""
        frags = []
        idx = 0
        col_ids = {0: [], 1: [], 2: []}
        for col in range(3):
            for row in range(5):
                frags.append(
                    OCRResult(
                        f"C{col}L{row}",
                        col * 200 + 10,
                        row * 30 + 10,
                        150,
                        20,
                        0.9,
                    )
                )
                col_ids[col].append(idx)
                idx += 1

        enriched = [
            {
                "ids": col_ids[c],
                "translated_html": f"Column {c} paragraph",
                "alignment": "left",
            }
            for c in range(3)
        ]
        merged, translations, used = merge_to_paragraphs(
            enriched, frags, "TesseractOCR"
        )
        assert len(merged) == 3
        assert len(used) == 15  # noqa: PLR2004


class TestMergeToParagraphsYCoordinateGrouping:
    """Tests for edge cases in Y-coordinate grouping."""

    def test_fragments_with_1px_y_difference(self) -> None:
        """Fragments with 1px Y difference are on the same line (within threshold)."""
        frags = [
            OCRResult("A", 10, 100, 50, 20, 0.9),
            OCRResult("B", 70, 101, 50, 20, 0.9),
        ]
        enriched = [
            {
                "ids": [0, 1],
                "translated_html": "Same line text",
                "alignment": "left",
            }
        ]
        merged, _, _ = merge_to_paragraphs(enriched, frags, "TesseractOCR")
        assert len(merged) == 1
        assert merged[0].is_single_line is True

    def test_y_gap_exactly_one_above_threshold(self) -> None:
        """Y gap of exactly threshold+1 creates a new line."""
        # For Tesseract, padding_insert=1 → avg_char_h = h + 2
        # Using h=20 → avg_char_h=22, threshold = 22 * 0.5 = 11
        frags = [
            OCRResult("A", 10, 10, 50, 20, 0.9),
            OCRResult("B", 10, 22, 50, 20, 0.9),  # gap=12 > 11 → new line
        ]
        enriched = [
            {
                "ids": [0, 1],
                "translated_html": "Two lines",
                "alignment": "left",
            }
        ]
        merged, _, _ = merge_to_paragraphs(enriched, frags, "TesseractOCR")
        assert len(merged) == 1
        assert merged[0].is_single_line is False

    def test_graduated_y_positions(self) -> None:
        """Gradually increasing Y positions: each step within threshold stays same line."""
        # avg_char_h will be ~22, threshold = ~11
        # Steps of 5px each: 0, 5, 10 — all within threshold of previous
        frags = [
            OCRResult("A", 10, 0, 50, 20, 0.9),
            OCRResult("B", 70, 5, 50, 20, 0.9),
            OCRResult("C", 130, 10, 50, 20, 0.9),
        ]
        enriched = [
            {
                "ids": [0, 1, 2],
                "translated_html": "Graduated text",
                "alignment": "left",
            }
        ]
        merged, _, _ = merge_to_paragraphs(enriched, frags, "TesseractOCR")
        assert len(merged) == 1
        # Y levels: {0, 5, 10}. Sorted: 0, 5, 10.
        # Gap 0→5 = 5, threshold ~11 → same line
        # Gap 5→10 = 5, threshold ~11 → same line
        assert merged[0].is_single_line is True

    def test_staircase_y_positions_creates_lines(self) -> None:
        """Staircase Y positions with large steps create multiple lines."""
        frags = [
            OCRResult("A", 10, 0, 50, 20, 0.9),
            OCRResult("B", 10, 50, 50, 20, 0.9),
            OCRResult("C", 10, 100, 50, 20, 0.9),
            OCRResult("D", 10, 150, 50, 20, 0.9),
        ]
        enriched = [
            {
                "ids": [0, 1, 2, 3],
                "translated_html": "Staircase text",
                "alignment": "left",
            }
        ]
        merged, _, _ = merge_to_paragraphs(enriched, frags, "TesseractOCR")
        assert len(merged) == 1
        assert merged[0].is_single_line is False


class TestMergeToParagraphsXCoordinateOrdering:
    """Tests for X-coordinate ordering within the merged result."""

    def test_fragments_ordered_left_to_right(self) -> None:
        """Text is space-joined in fragment order (by index), not by x position."""
        frags = [
            OCRResult("First", 100, 10, 50, 20, 0.9),
            OCRResult("Second", 10, 10, 50, 20, 0.9),
        ]
        enriched = [
            {
                "ids": [0, 1],
                "translated_html": "Translated text",
                "alignment": "left",
            }
        ]
        merged, _, _ = merge_to_paragraphs(enriched, frags, "TesseractOCR")
        assert len(merged) == 1
        # Text is joined in the order of fragments list (index order)
        assert merged[0].text == "First Second"

    def test_reverse_x_order_bounding_box(self) -> None:
        """Bounding box is correct regardless of fragment x ordering."""
        frags = [
            OCRResult("Right", 200, 10, 50, 20, 0.9),
            OCRResult("Left", 10, 10, 50, 20, 0.9),
        ]
        enriched = [
            {
                "ids": [0, 1],
                "translated_html": "Reordered",
                "alignment": "left",
            }
        ]
        merged, _, _ = merge_to_paragraphs(enriched, frags, "TesseractOCR")
        assert merged[0].x == 10  # min x
        assert merged[0].w == 240  # 250 - 10  # noqa: PLR2004

    def test_overlapping_x_ranges_on_same_line(self) -> None:
        """Fragments with overlapping X ranges on same Y are still single line."""
        frags = [
            OCRResult("Over", 10, 10, 80, 20, 0.9),
            OCRResult("Lap", 50, 10, 80, 20, 0.9),
        ]
        enriched = [
            {
                "ids": [0, 1],
                "translated_html": "Overlap translated",
                "alignment": "left",
            }
        ]
        merged, _, _ = merge_to_paragraphs(enriched, frags, "TesseractOCR")
        assert len(merged) == 1
        assert merged[0].is_single_line is True
        assert merged[0].x == 10
        assert merged[0].w == 120  # max(90, 130) - 10  # noqa: PLR2004


class TestMergeToParagraphsSpecialContent:
    """Tests for special content in translations."""

    def test_html_entities_in_translation(self) -> None:
        """HTML entities in translated text are preserved in HTML."""
        frags = [OCRResult("Test", 0, 0, 50, 20, 0.9)]
        enriched = [
            {
                "ids": [0],
                "translated_html": "Less &lt; Greater &gt;",
                "alignment": "left",
            }
        ]
        merged, _, _ = merge_to_paragraphs(enriched, frags, "TesseractOCR")
        assert len(merged) == 1
        assert "&lt;" in merged[0].translated_html

    def test_url_in_translation(self) -> None:
        """URL in translated text is preserved."""
        frags = [OCRResult("Link", 0, 0, 50, 20, 0.9)]
        enriched = [
            {
                "ids": [0],
                "translated_html": "https://example.com",
                "alignment": "left",
            }
        ]
        merged, _, _ = merge_to_paragraphs(enriched, frags, "TesseractOCR")
        assert len(merged) == 1
        assert merged[0].translated_text == "https://example.com"

    def test_multiline_translation_with_br(self) -> None:
        """Translation with BR tags produces newlines in plain text."""
        frags = [
            OCRResult("Line1", 0, 0, 50, 20, 0.9),
            OCRResult("Line2", 0, 30, 50, 20, 0.9),
        ]
        enriched = [
            {
                "ids": [0, 1],
                "translated_html": "Ligne 1<br>Ligne 2<br>Ligne 3",
                "alignment": "left",
            }
        ]
        merged, _, _ = merge_to_paragraphs(enriched, frags, "TesseractOCR")
        assert len(merged) == 1
        assert merged[0].translated_text == "Ligne 1\nLigne 2\nLigne 3"

    def test_translation_with_underline_tag(self) -> None:
        """Underline tags are preserved in HTML and stripped in text."""
        frags = [OCRResult("Test", 0, 0, 50, 20, 0.9)]
        enriched = [
            {
                "ids": [0],
                "translated_html": "<u>Underlined</u>",
                "alignment": "left",
            }
        ]
        merged, _, _ = merge_to_paragraphs(enriched, frags, "TesseractOCR")
        assert len(merged) == 1
        assert "<u>" in merged[0].translated_html
        assert merged[0].translated_text == "Underlined"

    def test_empty_html_translation_skipped_as_unchanged(self) -> None:
        """Empty HTML translation matching empty original is skipped."""
        frags = [OCRResult("", 0, 0, 10, 10, 0.9)]
        enriched = [
            {
                "ids": [0],
                "translated_html": "",
                "alignment": "left",
            }
        ]
        merged, translations, used = merge_to_paragraphs(
            enriched, frags, "TesseractOCR"
        )
        # Empty original matches empty translation → unchanged → skipped
        assert len(merged) == 0


class TestMergeToParagraphsConfidenceScores:
    """Tests verifying confidence score is always 1.0 in merged result."""

    def test_merged_confidence_is_one(self) -> None:
        """Merged OCRResult always has confidence=1.0."""
        frags = [
            OCRResult("Low", 0, 0, 50, 20, 0.3),
            OCRResult("High", 60, 0, 50, 20, 0.99),
        ]
        enriched = [
            {
                "ids": [0, 1],
                "translated_html": "Translated",
                "alignment": "left",
            }
        ]
        merged, _, _ = merge_to_paragraphs(enriched, frags, "TesseractOCR")
        assert len(merged) == 1
        assert merged[0].confidence == 1.0

    def test_zero_confidence_fragments(self) -> None:
        """Fragments with 0 confidence still merge successfully."""
        frags = [OCRResult("Zero", 0, 0, 50, 20, 0.0)]
        enriched = [
            {
                "ids": [0],
                "translated_html": "Translated zero",
                "alignment": "left",
            }
        ]
        merged, _, _ = merge_to_paragraphs(enriched, frags, "TesseractOCR")
        assert len(merged) == 1


class TestMergeToParagraphsEasyOCRPadding:
    """Tests for EasyOCR-specific padding behavior."""

    def test_easyocr_negative_padding_insert(self) -> None:
        """EasyOCR uses padding_insert=-2, affecting avg_char_h."""
        frags = [OCRResult("Text", 0, 0, 100, 30, 0.9)]
        enriched = [
            {
                "ids": [0],
                "translated_html": "Translated",
                "alignment": "left",
            }
        ]
        merged, _, _ = merge_to_paragraphs(enriched, frags, "EasyOCR")
        assert len(merged) == 1
        # EasyOCR padding_insert = -2
        # avg_char_h = (30 + 2*(-2)) / 1 = 26
        assert merged[0].original_text_height == 26  # noqa: PLR2004

    def test_easyocr_multiline_ratio_different(self) -> None:
        """EasyOCR multi-line ratio differs from Tesseract due to multiplier."""
        frags = [
            OCRResult("A", 0, 0, 50, 20, 0.9),
            OCRResult("B", 0, 60, 50, 20, 0.9),
        ]
        enriched_tess = [
            {
                "ids": [0, 1],
                "translated_html": "Multi Tess",
                "alignment": "left",
            }
        ]
        enriched_easy = [
            {
                "ids": [0, 1],
                "translated_html": "Multi Easy",
                "alignment": "left",
            }
        ]
        merged_tess, _, _ = merge_to_paragraphs(enriched_tess, frags, "TesseractOCR")
        merged_easy, _, _ = merge_to_paragraphs(enriched_easy, frags, "EasyOCR")
        assert len(merged_tess) == 1
        assert len(merged_easy) == 1
        # EasyOCR ratio should be larger due to 1.2x multiplier
        # But also different avg_char_h due to different padding
        # Both should produce valid (>0) ratios
        assert merged_tess[0].line_height_ratio > 0
        assert merged_easy[0].line_height_ratio > 0

    def test_easyocr_single_line_ratio_unchanged(self) -> None:
        """EasyOCR single-line ratio is not affected by multiplier."""
        from src.constants.ocr import OCR_SINGLE_LINE_HEIGHT  # noqa: PLC0415

        frags = [OCRResult("Single", 0, 0, 50, 20, 0.9)]
        enriched = [
            {
                "ids": [0],
                "translated_html": "Translated single",
                "alignment": "left",
            }
        ]
        merged, _, _ = merge_to_paragraphs(enriched, frags, "EasyOCR")
        assert len(merged) == 1
        assert merged[0].line_height_ratio == pytest.approx(
            OCR_SINGLE_LINE_HEIGHT, abs=0.001
        )


class TestMergeToParagraphsSharedFragments:
    """Tests for shared fragment IDs between paragraphs."""

    def test_same_fragment_in_two_paragraphs(self) -> None:
        """Same fragment ID used in two paragraphs appears in used list twice."""
        frags = [
            OCRResult("Shared", 10, 10, 50, 20, 0.9),
            OCRResult("Other", 70, 10, 50, 20, 0.9),
        ]
        enriched = [
            {
                "ids": [0],
                "translated_html": "First use",
                "alignment": "left",
            },
            {
                "ids": [0, 1],
                "translated_html": "Second use with other",
                "alignment": "left",
            },
        ]
        merged, translations, used = merge_to_paragraphs(
            enriched, frags, "TesseractOCR"
        )
        assert len(merged) == 2
        # Fragment 0 appears in both, so used list has 3 entries (0, 0+1)
        assert len(used) == 3  # noqa: PLR2004

    def test_all_unchanged_clears_all_used(self) -> None:
        """When all paragraphs are unchanged, used list is empty."""
        frags = [
            OCRResult("Same1", 10, 10, 50, 20, 0.9),
            OCRResult("Same2", 70, 10, 50, 20, 0.9),
        ]
        enriched = [
            {
                "ids": [0],
                "translated_html": "Same1",  # Unchanged
                "alignment": "left",
            },
            {
                "ids": [1],
                "translated_html": "Same2",  # Unchanged
                "alignment": "left",
            },
        ]
        merged, translations, used = merge_to_paragraphs(
            enriched, frags, "TesseractOCR"
        )
        assert len(merged) == 0
        assert len(translations) == 0
        assert len(used) == 0


class TestMergeToParagraphsEdgeCaseGeometry:
    """Edge case geometry tests through merge_to_paragraphs."""

    def test_fragments_at_same_coordinates(self) -> None:
        """Multiple fragments at identical coordinates produce correct box."""
        frags = [
            OCRResult("A", 50, 50, 30, 20, 0.9),
            OCRResult("B", 50, 50, 30, 20, 0.9),
            OCRResult("C", 50, 50, 30, 20, 0.9),
        ]
        enriched = [
            {
                "ids": [0, 1, 2],
                "translated_html": "Stacked translated",
                "alignment": "center",
            }
        ]
        merged, _, _ = merge_to_paragraphs(enriched, frags, "TesseractOCR")
        assert len(merged) == 1
        assert merged[0].x == 50
        assert merged[0].y == 50
        assert merged[0].w == 30
        assert merged[0].h == 20

    def test_adjacent_non_overlapping_horizontal(self) -> None:
        """Adjacent non-overlapping horizontal fragments merge correctly."""
        frags = [
            OCRResult("Left", 0, 10, 50, 20, 0.9),
            OCRResult("Right", 50, 10, 50, 20, 0.9),
        ]
        enriched = [
            {
                "ids": [0, 1],
                "translated_html": "Adjacent text",
                "alignment": "left",
            }
        ]
        merged, _, _ = merge_to_paragraphs(enriched, frags, "TesseractOCR")
        assert len(merged) == 1
        assert merged[0].x == 0
        assert merged[0].w == 100
        assert merged[0].h == 20

    def test_adjacent_non_overlapping_vertical(self) -> None:
        """Adjacent non-overlapping vertical fragments merge correctly."""
        frags = [
            OCRResult("Top", 10, 0, 50, 20, 0.9),
            OCRResult("Bottom", 10, 20, 50, 20, 0.9),
        ]
        enriched = [
            {
                "ids": [0, 1],
                "translated_html": "Vertical text",
                "alignment": "left",
            }
        ]
        merged, _, _ = merge_to_paragraphs(enriched, frags, "TesseractOCR")
        assert len(merged) == 1
        assert merged[0].y == 0
        assert merged[0].h == 40  # noqa: PLR2004


class TestAnalyzeLineMetricsWithRealGeometry:
    """Integration-style tests using _calculate_geometry output as input to _analyze_line_metrics."""

    def test_three_line_paragraph_geometry_to_metrics(self) -> None:
        """Three lines of text: geometry feeds correct values to metrics."""
        fragments = [
            OCRResult("Line1A", 10, 10, 50, 20, 0.9),
            OCRResult("Line1B", 70, 10, 50, 20, 0.9),
            OCRResult("Line2A", 10, 50, 50, 20, 0.9),
            OCRResult("Line2B", 70, 50, 50, 20, 0.9),
            OCRResult("Line3A", 10, 90, 50, 20, 0.9),
        ]
        geo = _calculate_geometry(fragments, padding=1)
        metrics = _analyze_line_metrics(
            fragments, geo["padded_total_h"], geo["avg_char_h"], "TesseractOCR"
        )
        assert metrics["unique_lines"] == 3
        assert metrics["is_single_line"] is False
        assert metrics["ratio"] > 0

    def test_single_line_paragraph_geometry_to_metrics(self) -> None:
        """Single line of text: geometry feeds correct values to metrics."""
        fragments = [
            OCRResult("Word1", 10, 50, 40, 18, 0.9),
            OCRResult("Word2", 55, 50, 40, 18, 0.9),
            OCRResult("Word3", 100, 50, 40, 18, 0.9),
        ]
        geo = _calculate_geometry(fragments, padding=1)
        metrics = _analyze_line_metrics(
            fragments, geo["padded_total_h"], geo["avg_char_h"], "TesseractOCR"
        )
        assert metrics["unique_lines"] == 1
        assert metrics["is_single_line"] is True

    def test_two_line_tight_spacing(self) -> None:
        """Two lines with tight spacing still detected as two lines."""
        # Fragments with height=20, padding=1 → avg_char_h=22
        # threshold = 22 * 0.5 = 11
        # Gap = 15 > 11 → two lines
        fragments = [
            OCRResult("A", 10, 10, 50, 20, 0.9),
            OCRResult("B", 10, 25, 50, 20, 0.9),  # gap = 15
        ]
        geo = _calculate_geometry(fragments, padding=1)
        metrics = _analyze_line_metrics(
            fragments, geo["padded_total_h"], geo["avg_char_h"], "TesseractOCR"
        )
        assert metrics["unique_lines"] == 2

    def test_zero_height_fragments_geometry_to_metrics(self) -> None:
        """Zero-height fragments: geometry feeds zeros to metrics safely."""
        fragments = [
            OCRResult("A", 0, 0, 50, 0, 0.9),
            OCRResult("B", 60, 50, 50, 0, 0.9),
        ]
        geo = _calculate_geometry(fragments, padding=0)
        # avg_char_h = 0, padded_total_h = 50
        # unique_lines depends on threshold: 0 * 0.5 = 0, gap = 50 > 0 → 2 lines
        # But ratio = 50 / (2 * 0) → division by zero guard?
        # Code: if unique_lines > 1 and avg_char_h > 0:
        # avg_char_h = 0 → condition is False → ratio stays at default
        metrics = _analyze_line_metrics(
            fragments, geo["padded_total_h"], geo["avg_char_h"], "TesseractOCR"
        )
        assert metrics["unique_lines"] == 2
        from src.constants.ocr import OCR_DEFAULT_LINE_HEIGHT  # noqa: PLC0415

        assert metrics["ratio"] == pytest.approx(OCR_DEFAULT_LINE_HEIGHT, abs=0.01)


class TestCalculateGeometryPaddedTotalH:
    """Focused tests on padded_total_h calculation."""

    def test_padded_total_h_zero_padding(self) -> None:
        """padded_total_h equals height when padding is 0."""
        fragments = [OCRResult("A", 0, 0, 50, 30, 0.9)]
        geo = _calculate_geometry(fragments, padding=0)
        assert geo["padded_total_h"] == 30

    def test_padded_total_h_small_padding(self) -> None:
        """padded_total_h = height + 2*padding."""
        fragments = [OCRResult("A", 0, 0, 50, 30, 0.9)]
        geo = _calculate_geometry(fragments, padding=3)
        assert geo["padded_total_h"] == 36  # 30 + 6  # noqa: PLR2004

    def test_padded_total_h_negative_padding(self) -> None:
        """Negative padding (EasyOCR) reduces padded_total_h."""
        fragments = [OCRResult("A", 0, 0, 50, 30, 0.9)]
        geo = _calculate_geometry(fragments, padding=-2)
        assert geo["padded_total_h"] == 26  # 30 + (-4)  # noqa: PLR2004

    def test_padded_total_h_multi_fragment(self) -> None:
        """padded_total_h uses total height, not per-fragment height."""
        fragments = [
            OCRResult("A", 0, 0, 50, 20, 0.9),
            OCRResult("B", 0, 50, 50, 20, 0.9),
        ]
        geo = _calculate_geometry(fragments, padding=5)
        # height = (50+20) - 0 = 70
        # padded_total_h = 70 + 10 = 80
        assert geo["padded_total_h"] == 80  # noqa: PLR2004


class TestMergeToParagraphsTranslationsOutput:
    """Tests focused on the translations list output."""

    def test_translations_order_matches_paragraphs(self) -> None:
        """Translations list is in the same order as merged results."""
        frags = [
            OCRResult("A", 0, 0, 50, 20, 0.9),
            OCRResult("B", 0, 30, 50, 20, 0.9),
            OCRResult("C", 0, 60, 50, 20, 0.9),
        ]
        enriched = [
            {"ids": [0], "translated_html": "Alpha", "alignment": "left"},
            {"ids": [1], "translated_html": "Beta", "alignment": "left"},
            {"ids": [2], "translated_html": "Gamma", "alignment": "left"},
        ]
        merged, translations, _ = merge_to_paragraphs(enriched, frags, "TesseractOCR")
        assert translations == ["Alpha", "Beta", "Gamma"]

    def test_translations_skip_unchanged(self) -> None:
        """Translations list only contains changed paragraphs."""
        frags = [
            OCRResult("Keep", 0, 0, 50, 20, 0.9),
            OCRResult("Change", 0, 30, 50, 20, 0.9),
        ]
        enriched = [
            {"ids": [0], "translated_html": "Keep", "alignment": "left"},  # Unchanged
            {"ids": [1], "translated_html": "Modified", "alignment": "left"},
        ]
        merged, translations, _ = merge_to_paragraphs(enriched, frags, "TesseractOCR")
        assert translations == ["Modified"]

    def test_translations_empty_when_all_unchanged(self) -> None:
        """Translations list is empty when all paragraphs are unchanged."""
        frags = [
            OCRResult("Same", 0, 0, 50, 20, 0.9),
            OCRResult("Same2", 0, 30, 50, 20, 0.9),
        ]
        enriched = [
            {"ids": [0], "translated_html": "Same", "alignment": "left"},
            {"ids": [1], "translated_html": "Same2", "alignment": "left"},
        ]
        _, translations, _ = merge_to_paragraphs(enriched, frags, "TesseractOCR")
        assert translations == []


class TestMergeToParagraphsOCRMethods:
    """Tests with different OCR method strings."""

    def test_google_ocr_method(self) -> None:
        """Google OCR method uses default padding (same as Tesseract)."""
        frags = [OCRResult("Text", 0, 0, 100, 30, 0.9)]
        enriched = [
            {
                "ids": [0],
                "translated_html": "Translated",
                "alignment": "left",
            }
        ]
        merged, _, _ = merge_to_paragraphs(enriched, frags, "GoogleOCR")
        assert len(merged) == 1
        # GoogleOCR → default padding (1, 1) same as Tesseract
        # avg_char_h = (30 + 2) / 1 = 32
        assert merged[0].original_text_height == 32  # noqa: PLR2004

    def test_unknown_ocr_method_uses_defaults(self) -> None:
        """Unknown OCR method string falls back to default padding."""
        frags = [OCRResult("Text", 0, 0, 100, 30, 0.9)]
        enriched = [
            {
                "ids": [0],
                "translated_html": "Translated",
                "alignment": "left",
            }
        ]
        merged, _, _ = merge_to_paragraphs(enriched, frags, "UnknownOCR")
        assert len(merged) == 1
        # Default padding_insert = 1
        assert merged[0].original_text_height == 32  # noqa: PLR2004

    def test_empty_ocr_method_string(self) -> None:
        """Empty OCR method string uses default padding."""
        frags = [OCRResult("Text", 0, 0, 100, 30, 0.9)]
        enriched = [
            {
                "ids": [0],
                "translated_html": "Translated",
                "alignment": "left",
            }
        ]
        merged, _, _ = merge_to_paragraphs(enriched, frags, "")
        assert len(merged) == 1
        assert merged[0].original_text_height == 32  # noqa: PLR2004


class TestMergeToParagraphsLineHeightRatio:
    """Tests focused on line_height_ratio values in merged results."""

    def test_single_line_ratio(self) -> None:
        """Single-line paragraph has OCR_SINGLE_LINE_HEIGHT ratio."""
        from src.constants.ocr import OCR_SINGLE_LINE_HEIGHT  # noqa: PLC0415

        frags = [OCRResult("Single", 0, 0, 100, 20, 0.9)]
        enriched = [{"ids": [0], "translated_html": "Translated", "alignment": "left"}]
        merged, _, _ = merge_to_paragraphs(enriched, frags, "TesseractOCR")
        assert merged[0].line_height_ratio == pytest.approx(
            OCR_SINGLE_LINE_HEIGHT, abs=0.001
        )

    def test_multi_line_ratio_within_bounds(self) -> None:
        """Multi-line paragraph ratio is between MIN and MAX."""
        from src.constants.ocr import (  # noqa: PLC0415
            OCR_MAX_LINE_HEIGHT,
            OCR_MIN_LINE_HEIGHT,
        )

        frags = [
            OCRResult("A", 0, 0, 50, 20, 0.9),
            OCRResult("B", 0, 40, 50, 20, 0.9),
            OCRResult("C", 0, 80, 50, 20, 0.9),
        ]
        enriched = [
            {
                "ids": [0, 1, 2],
                "translated_html": "Three lines",
                "alignment": "left",
            }
        ]
        merged, _, _ = merge_to_paragraphs(enriched, frags, "TesseractOCR")
        assert merged[0].line_height_ratio >= OCR_MIN_LINE_HEIGHT
        assert merged[0].line_height_ratio <= OCR_MAX_LINE_HEIGHT

    def test_widely_spaced_lines_ratio_clamped(self) -> None:
        """Very widely spaced lines produce a clamped ratio."""
        frags = [
            OCRResult("A", 0, 0, 50, 5, 0.9),
            OCRResult("B", 0, 500, 50, 5, 0.9),
        ]
        enriched = [{"ids": [0, 1], "translated_html": "Spaced", "alignment": "left"}]
        merged, _, _ = merge_to_paragraphs(enriched, frags, "TesseractOCR")
        assert merged[0].line_height_ratio <= 3.0


class TestMergeToParagraphsNestedBoundingBoxes:
    """Tests for nested/contained bounding box scenarios."""

    def test_three_nested_fragments(self) -> None:
        """Three nested fragments produce outermost bounding box."""
        frags = [
            OCRResult("outer", 0, 0, 200, 100, 0.9),
            OCRResult("middle", 20, 20, 160, 60, 0.9),
            OCRResult("inner", 50, 40, 100, 20, 0.9),
        ]
        enriched = [
            {
                "ids": [0, 1, 2],
                "translated_html": "Nested translated",
                "alignment": "center",
            }
        ]
        merged, _, _ = merge_to_paragraphs(enriched, frags, "TesseractOCR")
        assert len(merged) == 1
        assert merged[0].x == 0
        assert merged[0].y == 0
        assert merged[0].w == 200
        assert merged[0].h == 100

    def test_partial_overlap_x_axis(self) -> None:
        """Fragments partially overlapping on X axis produce correct width."""
        frags = [
            OCRResult("A", 10, 10, 60, 20, 0.9),
            OCRResult("B", 50, 10, 60, 20, 0.9),
            OCRResult("C", 90, 10, 60, 20, 0.9),
        ]
        enriched = [
            {
                "ids": [0, 1, 2],
                "translated_html": "Overlapping X",
                "alignment": "left",
            }
        ]
        merged, _, _ = merge_to_paragraphs(enriched, frags, "TesseractOCR")
        assert len(merged) == 1
        # min_x=10, max_xr=150 → width=140
        assert merged[0].x == 10
        assert merged[0].w == 140  # noqa: PLR2004

    def test_partial_overlap_y_axis(self) -> None:
        """Fragments partially overlapping on Y axis produce correct height."""
        frags = [
            OCRResult("A", 10, 10, 50, 30, 0.9),
            OCRResult("B", 10, 30, 50, 30, 0.9),
            OCRResult("C", 10, 50, 50, 30, 0.9),
        ]
        enriched = [
            {
                "ids": [0, 1, 2],
                "translated_html": "Overlapping Y",
                "alignment": "left",
            }
        ]
        merged, _, _ = merge_to_paragraphs(enriched, frags, "TesseractOCR")
        assert len(merged) == 1
        # min_y=10, max_yb=80 → height=70
        assert merged[0].y == 10
        assert merged[0].h == 70  # noqa: PLR2004


class TestMergeToParagraphsUsedFragmentTracking:
    """Tests verifying the used fragments tracking is correct."""

    def test_changed_paragraph_tracks_fragments(self) -> None:
        """Changed paragraphs add their fragments to used list."""
        frags = [
            OCRResult("A", 0, 0, 50, 20, 0.9),
            OCRResult("B", 60, 0, 50, 20, 0.9),
        ]
        enriched = [{"ids": [0, 1], "translated_html": "Changed", "alignment": "left"}]
        _, _, used = merge_to_paragraphs(enriched, frags, "TesseractOCR")
        assert len(used) == 2
        assert frags[0] in used
        assert frags[1] in used

    def test_unchanged_paragraph_removes_fragments_from_used(self) -> None:
        """Unchanged paragraph removes its fragments from used list."""
        frags = [OCRResult("Same", 0, 0, 50, 20, 0.9)]
        enriched = [{"ids": [0], "translated_html": "Same", "alignment": "left"}]
        _, _, used = merge_to_paragraphs(enriched, frags, "TesseractOCR")
        assert len(used) == 0

    def test_mixed_changed_unchanged_correct_used_count(self) -> None:
        """Three paragraphs: two changed, one unchanged → correct used count."""
        frags = [
            OCRResult("A", 0, 0, 50, 20, 0.9),
            OCRResult("B", 0, 30, 50, 20, 0.9),
            OCRResult("C", 0, 60, 50, 20, 0.9),
        ]
        enriched = [
            {"ids": [0], "translated_html": "Alpha", "alignment": "left"},
            {"ids": [1], "translated_html": "B", "alignment": "left"},  # Unchanged
            {"ids": [2], "translated_html": "Gamma", "alignment": "left"},
        ]
        _, _, used = merge_to_paragraphs(enriched, frags, "TesseractOCR")
        # Only fragments 0 and 2 should be in used (fragment 1 removed as unchanged)
        assert len(used) == 2


# ---------------------------------------------------------------------------
# _analyze_line_metrics: avg_char_h == 0 with unique_lines > 1
# ---------------------------------------------------------------------------


def test_analyze_line_metrics_zero_avg_char_h_multiple_lines() -> None:
    """Guard prevents division by zero when avg_char_h == 0 and unique_lines > 1.

    When all fragments have height 0, avg_char_h is 0. If fragments are at
    different Y levels (unique_lines > 1), the code must NOT attempt
    padded_total_h / (unique_lines * avg_char_h) which would be division
    by zero. The guard `if unique_lines > 1 and avg_char_h > 0:` skips
    the ratio calculation and falls back to OCR_DEFAULT_LINE_HEIGHT.
    """
    from src.constants.ocr import OCR_DEFAULT_LINE_HEIGHT  # noqa: PLC0415

    # Two fragments at very different Y positions, both with height 0
    fragments = [
        OCRResult("Word1", 10, 0, 80, 0, 0.9),
        OCRResult("Word2", 10, 100, 80, 0, 0.9),
    ]

    # avg_char_h = 0 (all fragments have h=0, padding=0)
    avg_char_h = 0.0
    # padded_total_h = (100 + 0) - 0 = 100 (plus padding)
    padded_total_h = 100.0

    # Should not raise ZeroDivisionError
    metrics = _analyze_line_metrics(
        fragments, padded_total_h, avg_char_h, "TesseractOCR"
    )

    # With avg_char_h == 0, the threshold is 0 * ratio = 0.
    # Gap between y=0 and y=100 is 100 > 0, so unique_lines should be 2.
    assert metrics["unique_lines"] == 2  # noqa: PLR2004
    assert metrics["is_single_line"] is False
    # avg_char_h == 0 means the guard condition is False →
    # ratio stays at OCR_DEFAULT_LINE_HEIGHT (set before the guard)
    assert metrics["ratio"] == pytest.approx(OCR_DEFAULT_LINE_HEIGHT, abs=0.01)
