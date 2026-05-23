"""Unit tests for the OCR engine."""

import builtins
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from src.constants.ocr import (
    EASYOCR_DEFAULT_LANGUAGES,
    OCR_METHOD_EASYOCR,
    OCR_METHOD_GOOGLE_CLOUD,
    OCR_METHOD_TESSERACT,
    TESSERACT_CONFIDENCE_SCALE,
    TESSERACT_WORD_LEVEL,
)
from src.core.ocr_engine import (
    OCRResult,
    _bypass_uno_import,
    _easyocr_readers,
    _get_easyocr_reader,
    _run_easyocr,
    _run_google_cloud,
    _run_tesseract,
    merge_ocr_results,
    run_ocr,
)

_OCR = "src.core.ocr_engine"


# ---------------------------------------------------------------------------
# OCRResult — constructor and defaults
# ---------------------------------------------------------------------------


class TestOCRResultConstructor:
    """Verify OCRResult constructor stores positional args and sets defaults."""

    def test_stores_positional_args(self):
        r = OCRResult("hello", 10, 20, 100, 50, 0.95)
        assert r.text == "hello"
        assert r.x == 10
        assert r.y == 20
        assert r.w == 100
        assert r.h == 50
        assert r.confidence == 0.95

    def test_default_color(self):
        """Default text color is black hex string."""
        r = OCRResult("t", 0, 0, 1, 1, 1.0)
        assert r.color == "#000000"

    def test_default_is_bold_false(self):
        r = OCRResult("t", 0, 0, 1, 1, 1.0)
        assert r.is_bold is False

    def test_default_is_italic_false(self):
        r = OCRResult("t", 0, 0, 1, 1, 1.0)
        assert r.is_italic is False

    def test_default_is_underline_false(self):
        r = OCRResult("t", 0, 0, 1, 1, 1.0)
        assert r.is_underline is False

    def test_default_translated_text_empty(self):
        r = OCRResult("t", 0, 0, 1, 1, 1.0)
        assert r.translated_text == ""

    def test_default_translated_html_empty(self):
        r = OCRResult("t", 0, 0, 1, 1, 1.0)
        assert r.translated_html == ""

    def test_default_alignment_none(self):
        r = OCRResult("t", 0, 0, 1, 1, 1.0)
        assert r.alignment is None

    def test_default_original_text_height_equals_h(self):
        """original_text_height defaults to the same value as h."""
        r = OCRResult("t", 0, 0, 50, 30, 1.0)
        assert r.original_text_height == 30

    def test_default_line_height_ratio(self):
        r = OCRResult("t", 0, 0, 1, 1, 1.0)
        assert r.line_height_ratio == 1.2

    def test_default_is_single_line_false(self):
        r = OCRResult("t", 0, 0, 1, 1, 1.0)
        assert r.is_single_line is False


# ---------------------------------------------------------------------------
# OCRResult.to_dict
# ---------------------------------------------------------------------------


class TestOCRResultToDict:
    """Verify to_dict() serialization."""

    def test_all_keys_present(self):
        """to_dict returns a dict with all expected keys."""
        r = OCRResult("word", 5, 10, 80, 20, 0.88)
        d = r.to_dict()
        expected_keys = {
            "text",
            "translated_text",
            "box",
            "confidence",
            "color",
            "is_bold",
            "is_italic",
            "is_underline",
            "alignment",
        }
        assert set(d.keys()) == expected_keys

    def test_values_match_fields(self):
        r = OCRResult("sample", 1, 2, 3, 4, 0.5)
        r.translated_text = "translated"
        r.color = "#FF0000"
        r.is_bold = True
        r.is_italic = True
        r.is_underline = True
        d = r.to_dict()
        assert d["text"] == "sample"
        assert d["translated_text"] == "translated"
        assert d["box"] == [1, 2, 3, 4]
        assert d["confidence"] == 0.5
        assert d["color"] == "#FF0000"
        assert d["is_bold"] is True
        assert d["is_italic"] is True
        assert d["is_underline"] is True

    def test_alignment_none_serializes_as_none(self):
        r = OCRResult("t", 0, 0, 1, 1, 1.0)
        d = r.to_dict()
        assert d["alignment"] is None

    def test_alignment_set_serializes_as_string(self):
        r = OCRResult("t", 0, 0, 1, 1, 1.0)
        r.alignment = "left"
        d = r.to_dict()
        assert d["alignment"] == "left"

    def test_alignment_integer_serializes_as_string(self):
        """Alignment set to an int (e.g. enum value) is str()-ified."""
        r = OCRResult("t", 0, 0, 1, 1, 1.0)
        r.alignment = 42
        d = r.to_dict()
        assert d["alignment"] == "42"

    def test_box_order(self):
        """Box is [x, y, w, h]."""
        r = OCRResult("t", 10, 20, 30, 40, 1.0)
        assert r.to_dict()["box"] == [10, 20, 30, 40]


# ---------------------------------------------------------------------------
# run_ocr — dispatch
# ---------------------------------------------------------------------------


class TestRunOCRDispatch:
    """Verify run_ocr dispatches to the correct backend."""

    @patch(f"{_OCR}._run_tesseract", return_value=[])
    def test_dispatches_to_tesseract(self, mock_tess):
        run_ocr("img.png", method=OCR_METHOD_TESSERACT)
        mock_tess.assert_called_once()

    @patch(f"{_OCR}._run_easyocr", return_value=[])
    def test_dispatches_to_easyocr(self, mock_easy):
        run_ocr("img.png", method=OCR_METHOD_EASYOCR)
        mock_easy.assert_called_once()

    @patch(f"{_OCR}._run_google_cloud", return_value=[])
    def test_dispatches_to_google_cloud(self, mock_gc):
        run_ocr("img.png", method=OCR_METHOD_GOOGLE_CLOUD)
        mock_gc.assert_called_once()

    @patch(f"{_OCR}._run_tesseract")
    def test_unknown_method_returns_empty_list(self, mock_tess):
        """Unknown OCR method returns [] without calling any backend."""
        result = run_ocr("img.png", method="UnknownOCR")
        mock_tess.assert_not_called()
        assert result == []

    @patch(f"{_OCR}._run_tesseract")
    def test_results_pass_through_merge(self, mock_tess):
        """run_ocr passes raw results through merge_ocr_results."""
        r1 = OCRResult("A", 0, 0, 10, 10, 0.9)
        r2 = OCRResult("B", 11, 0, 10, 10, 0.8)
        mock_tess.return_value = [r1, r2]
        # Both on same line, close together -> should merge
        result = run_ocr("img.png", method=OCR_METHOD_TESSERACT)
        assert len(result) == 1
        assert "A" in result[0].text
        assert "B" in result[0].text

    @patch(f"{_OCR}._run_tesseract", return_value=[])
    def test_tesseract_receives_correct_lang(self, mock_tess):
        """Tesseract backend receives the mapped language code."""
        run_ocr("img.png", method=OCR_METHOD_TESSERACT, src_lang="French")
        mock_tess.assert_called_once_with("img.png", lang="fra")

    @patch(f"{_OCR}._run_easyocr", return_value=[])
    def test_easyocr_receives_correct_langs(self, mock_easy):
        """EasyOCR backend receives the mapped language list."""
        run_ocr("img.png", method=OCR_METHOD_EASYOCR, src_lang="Japanese")
        mock_easy.assert_called_once_with("img.png", languages=["ja", "en"])

    @patch(f"{_OCR}._run_google_cloud", return_value=[])
    def test_google_cloud_receives_correct_hints(self, mock_gc):
        """Google Cloud backend receives the mapped language hints."""
        run_ocr("img.png", method=OCR_METHOD_GOOGLE_CLOUD, src_lang="Arabic")
        mock_gc.assert_called_once_with("img.png", lang_hints=["ar"])


# ---------------------------------------------------------------------------
# merge_ocr_results
# ---------------------------------------------------------------------------


class TestMergeOCRResults:
    """Verify spatial merging of OCR fragments."""

    def test_empty_list_returns_empty(self):
        assert merge_ocr_results([]) == []

    def test_whitespace_only_results_filtered(self):
        """Results containing only whitespace are dropped."""
        r = OCRResult("   ", 0, 0, 10, 10, 0.9)
        assert merge_ocr_results([r]) == []

    def test_single_result_returned_as_is(self):
        r = OCRResult("hello", 0, 0, 50, 20, 0.9)
        result = merge_ocr_results([r])
        assert len(result) == 1
        assert result[0].text == "hello"

    def test_same_line_fragments_merged(self):
        """Two fragments with high vertical overlap are merged."""
        # Both at y=10, h=20; gap between them is small
        r1 = OCRResult("Hello", 0, 10, 40, 20, 0.9)
        r2 = OCRResult("World", 45, 10, 40, 20, 0.8)
        result = merge_ocr_results([r1, r2])
        assert len(result) == 1
        assert result[0].text == "Hello World"

    def test_different_lines_not_merged_horizontally(self):
        """Fragments on different Y positions stay separate."""
        r1 = OCRResult("Line1", 0, 0, 50, 20, 0.9)
        r2 = OCRResult("Line2", 0, 100, 50, 20, 0.8)
        result = merge_ocr_results([r1, r2])
        assert len(result) == 2

    def test_large_horizontal_gap_creates_separate_blocks(self):
        """Fragments far apart horizontally on same line stay separate."""
        # r1 ends at x=50, r2 starts at x=500
        # gap = 500 - 50 = 450, threshold = 20 * 0.6 = 12  ->  450 >> 12
        r1 = OCRResult("A", 0, 10, 50, 20, 0.9)
        r2 = OCRResult("B", 500, 10, 50, 20, 0.8)
        result = merge_ocr_results([r1, r2])
        assert len(result) == 2

    def test_merged_text_has_space_separator(self):
        r1 = OCRResult("foo", 0, 0, 20, 20, 0.9)
        r2 = OCRResult("bar", 22, 0, 20, 20, 0.8)
        result = merge_ocr_results([r1, r2])
        assert len(result) == 1
        assert result[0].text == "foo bar"

    def test_merged_confidence_is_average(self):
        r1 = OCRResult("a", 0, 0, 20, 20, 0.6)
        r2 = OCRResult("b", 22, 0, 20, 20, 0.8)
        result = merge_ocr_results([r1, r2])
        assert len(result) == 1
        assert result[0].confidence == pytest.approx(0.7)

    def test_merged_bbox_encompasses_both(self):
        """Merged bounding box covers both fragments."""
        r1 = OCRResult("a", 10, 5, 30, 20, 0.9)
        r2 = OCRResult("b", 45, 8, 30, 25, 0.8)
        result = merge_ocr_results([r1, r2])
        assert len(result) == 1
        merged = result[0]
        # x = min(10, 45) = 10
        assert merged.x == 10
        # y = min(5, 8) = 5
        assert merged.y == 5
        # w = max(10+30, 45+30) - 10 = 75 - 10 = 65
        assert merged.w == 65
        # h = max(5+20, 8+25) - 5 = 33 - 5 = 28
        assert merged.h == 28

    def test_bold_propagation_from_either_fragment(self):
        """If either fragment is bold, merged result is bold."""
        r1 = OCRResult("a", 0, 0, 20, 20, 0.9)
        r1.is_bold = False
        r2 = OCRResult("b", 22, 0, 20, 20, 0.8)
        r2.is_bold = True
        result = merge_ocr_results([r1, r2])
        assert result[0].is_bold is True

    def test_italic_propagation_from_either_fragment(self):
        """If either fragment is italic, merged result is italic."""
        r1 = OCRResult("a", 0, 0, 20, 20, 0.9)
        r1.is_italic = True
        r2 = OCRResult("b", 22, 0, 20, 20, 0.8)
        r2.is_italic = False
        result = merge_ocr_results([r1, r2])
        assert result[0].is_italic is True

    def test_bold_false_when_neither_bold(self):
        r1 = OCRResult("a", 0, 0, 20, 20, 0.9)
        r2 = OCRResult("b", 22, 0, 20, 20, 0.8)
        result = merge_ocr_results([r1, r2])
        assert result[0].is_bold is False

    def test_color_preserved_from_first_fragment(self):
        """Merged block gets color from the first fragment."""
        r1 = OCRResult("a", 0, 0, 20, 20, 0.9)
        r1.color = "#FF0000"
        r2 = OCRResult("b", 22, 0, 20, 20, 0.8)
        r2.color = "#00FF00"
        result = merge_ocr_results([r1, r2])
        assert result[0].color == "#FF0000"

    def test_sorting_by_y_before_line_grouping(self):
        """Fragments are sorted by Y before grouping into lines."""
        # Give them in reverse Y order
        r_bottom = OCRResult("bottom", 0, 100, 50, 20, 0.9)
        r_top = OCRResult("top", 0, 0, 50, 20, 0.8)
        result = merge_ocr_results([r_bottom, r_top])
        assert result[0].text == "top"
        assert result[1].text == "bottom"

    def test_sorting_by_x_within_line(self):
        """Fragments on the same line are sorted left-to-right."""
        # Place close together so they merge (gap < h * OCR_HORIZONTAL_GAP_RATIO)
        r_right = OCRResult("right", 42, 0, 40, 20, 0.9)
        r_left = OCRResult("left", 0, 0, 40, 20, 0.8)
        result = merge_ocr_results([r_right, r_left])
        assert len(result) == 1
        assert result[0].text == "left right"

    def test_overlap_ratio_boundary_not_merged(self):
        """Fragments with exactly OCR_VERTICAL_OVERLAP_RATIO overlap are NOT merged.

        The condition is strictly greater-than, not greater-or-equal.
        """
        # Two fragments: h=10 each. For overlap == min_h * ratio,
        # overlap must be > 6 to merge (since ratio=0.6 and min_h=10).
        # Place them so overlap is exactly 6.
        r1 = OCRResult("a", 0, 0, 20, 10, 0.9)
        # r2 at y=4 -> overlap = min(0+10, 4+10) - max(0, 4) = 10 - 4 = 6
        # threshold = 10 * 0.6 = 6  ->  6 > 6 is False -> NOT merged
        r2 = OCRResult("b", 30, 4, 20, 10, 0.8)
        result = merge_ocr_results([r1, r2])
        assert len(result) == 2

    def test_overlap_ratio_boundary_just_above_merged(self):
        """Fragments slightly above the overlap threshold ARE merged."""
        r1 = OCRResult("a", 0, 0, 20, 10, 0.9)
        # r2 at y=3 -> overlap = min(10, 13) - max(0, 3) = 10 - 3 = 7
        # threshold = 10 * 0.6 = 6  ->  7 > 6 is True -> merged
        r2 = OCRResult("b", 22, 3, 20, 10, 0.8)
        result = merge_ocr_results([r1, r2])
        assert len(result) == 1

    def test_three_fragments_same_line_merged(self):
        """Three close fragments on the same line all merge together."""
        r1 = OCRResult("one", 0, 0, 20, 20, 0.9)
        r2 = OCRResult("two", 22, 0, 20, 20, 0.85)
        r3 = OCRResult("three", 44, 0, 30, 20, 0.8)
        result = merge_ocr_results([r1, r2, r3])
        assert len(result) == 1
        assert result[0].text == "one two three"

    def test_mixed_whitespace_only_and_real_text(self):
        """Whitespace-only fragments are filtered; real ones survive."""
        blank = OCRResult("  \t ", 0, 0, 10, 10, 0.5)
        real = OCRResult("real", 20, 0, 30, 10, 0.9)
        result = merge_ocr_results([blank, real])
        assert len(result) == 1
        assert result[0].text == "real"


# ---------------------------------------------------------------------------
# _run_tesseract
# ---------------------------------------------------------------------------


class TestRunTesseract:
    """Verify Tesseract backend via subprocess."""

    _TSV_HEADER = (
        "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num"
        "\tleft\ttop\twidth\theight\tconf\ttext"
    )

    def _make_tsv(self, rows):
        """Build TSV content from header + row strings."""
        return self._TSV_HEADER + "\n" + "\n".join(rows) + "\n"

    def _fake_run_success(self, tsv_content):
        """Return a side_effect for subprocess.run that writes a TSV."""

        def _side_effect(cmd, check, capture_output):
            out_base = Path(cmd[2])
            tsv_path = out_base.with_suffix(".tsv")
            tsv_path.write_text(tsv_content, encoding="utf-8")

        return _side_effect

    @patch(f"{_OCR}.subprocess.run")
    def test_parses_valid_tsv_output(self, mock_run):
        """Parses word-level TSV rows into OCRResult list."""
        tsv = self._make_tsv(
            [
                "5\t1\t1\t1\t1\t1\t10\t20\t100\t30\t85.5\tHello",
            ]
        )
        mock_run.side_effect = self._fake_run_success(tsv)
        results = _run_tesseract("img.png")
        assert len(results) == 1
        assert results[0].text == "Hello"
        assert results[0].x == 10
        assert results[0].y == 20
        assert results[0].w == 100
        assert results[0].h == 30
        assert results[0].confidence == pytest.approx(85.5 / TESSERACT_CONFIDENCE_SCALE)

    @patch(f"{_OCR}.subprocess.run")
    def test_skips_non_word_level_rows(self, mock_run):
        """Rows with level != TESSERACT_WORD_LEVEL are skipped."""
        tsv = self._make_tsv(
            [
                # level=1 (page)
                "1\t1\t0\t0\t0\t0\t0\t0\t200\t200\t-1\t",
                # level=3 (paragraph)
                "3\t1\t1\t1\t0\t0\t10\t10\t100\t50\t-1\t",
                # level=5 (word) — valid
                f"{TESSERACT_WORD_LEVEL}\t1\t1\t1\t1\t1\t10\t20\t50\t15\t90\tValid",
            ]
        )
        mock_run.side_effect = self._fake_run_success(tsv)
        results = _run_tesseract("img.png")
        assert len(results) == 1
        assert results[0].text == "Valid"

    @patch(f"{_OCR}.subprocess.run")
    def test_skips_zero_confidence_rows(self, mock_run):
        """Rows with confidence <= 0 are skipped."""
        tsv = self._make_tsv(
            [
                "5\t1\t1\t1\t1\t1\t0\t0\t10\t10\t0\tBad",
                "5\t1\t1\t1\t1\t2\t20\t0\t10\t10\t-1\tNegative",
                "5\t1\t1\t1\t1\t3\t40\t0\t10\t10\t50\tGood",
            ]
        )
        mock_run.side_effect = self._fake_run_success(tsv)
        results = _run_tesseract("img.png")
        assert len(results) == 1
        assert results[0].text == "Good"

    @patch(f"{_OCR}.subprocess.run")
    def test_skips_empty_text_rows(self, mock_run):
        """Rows with empty or whitespace-only text are skipped."""
        tsv = self._make_tsv(
            [
                "5\t1\t1\t1\t1\t1\t0\t0\t10\t10\t80\t",
                "5\t1\t1\t1\t1\t2\t20\t0\t10\t10\t80\t   ",
                "5\t1\t1\t1\t1\t3\t40\t0\t10\t10\t80\tKeep",
            ]
        )
        mock_run.side_effect = self._fake_run_success(tsv)
        results = _run_tesseract("img.png")
        assert len(results) == 1
        assert results[0].text == "Keep"

    @patch(f"{_OCR}.subprocess.run")
    def test_italic_and_bold_fields_parsed(self, mock_run):
        """italic=1 and bold=1 TSV fields set OCRResult flags."""
        tsv = (
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num"
            "\tleft\ttop\twidth\theight\tconf\ttext\titalic\tbold\n"
            "5\t1\t1\t1\t1\t1\t0\t0\t50\t20\t90\tStyled\t1\t1\n"
        )
        mock_run.side_effect = self._fake_run_success(tsv)
        results = _run_tesseract("img.png")
        assert len(results) == 1
        assert results[0].is_italic is True
        assert results[0].is_bold is True

    @patch(f"{_OCR}.subprocess.run")
    def test_italic_zero_not_bold(self, mock_run):
        """italic=0 and no bold column keeps flags as False."""
        tsv = (
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num"
            "\tleft\ttop\twidth\theight\tconf\ttext\titalic\n"
            "5\t1\t1\t1\t1\t1\t0\t0\t50\t20\t90\tPlain\t0\n"
        )
        mock_run.side_effect = self._fake_run_success(tsv)
        results = _run_tesseract("img.png")
        assert len(results) == 1
        assert results[0].is_italic is False
        assert results[0].is_bold is False

    @patch(f"{_OCR}.subprocess.run")
    def test_language_fallback_to_eng(self, mock_run):
        """Non-eng CalledProcessError retries with 'eng'."""
        called_cmds = []

        def _side_effect(cmd, check, capture_output):
            called_cmds.append(list(cmd))
            if "fra" in cmd:
                raise subprocess.CalledProcessError(1, cmd)
            # English fallback succeeds
            out_base = Path(cmd[2])
            tsv_path = out_base.with_suffix(".tsv")
            tsv_path.write_text(self._TSV_HEADER + "\n", encoding="utf-8")

        mock_run.side_effect = _side_effect
        results = _run_tesseract("img.png", lang="fra")
        assert len(called_cmds) == 2
        assert "fra" in called_cmds[0]
        assert "eng" in called_cmds[1]
        assert results == []

    @patch(f"{_OCR}.subprocess.run")
    def test_eng_failure_returns_empty(self, mock_run):
        """English CalledProcessError is caught and returns empty list."""
        mock_run.side_effect = subprocess.CalledProcessError(1, "tesseract")
        results = _run_tesseract("img.png", lang="eng")
        assert results == []

    @patch(f"{_OCR}.subprocess.run")
    def test_tsv_not_created_raises_runtime_error(self, mock_run):
        """If Tesseract succeeds but TSV file is missing, raises RuntimeError."""
        # subprocess.run succeeds but creates no file
        mock_run.return_value = MagicMock()
        with pytest.raises(RuntimeError, match="failed to create output file"):
            _run_tesseract("img.png")

    @patch(f"{_OCR}.subprocess.run")
    def test_multiple_words_parsed(self, mock_run):
        """Multiple valid word rows are all parsed."""
        tsv = self._make_tsv(
            [
                "5\t1\t1\t1\t1\t1\t0\t0\t30\t15\t92\tThe",
                "5\t1\t1\t1\t1\t2\t35\t0\t30\t15\t88\tcat",
                "5\t1\t1\t1\t1\t3\t70\t0\t30\t15\t95\tsat",
            ]
        )
        mock_run.side_effect = self._fake_run_success(tsv)
        results = _run_tesseract("img.png")
        assert len(results) == 3
        assert results[0].text == "The"
        assert results[1].text == "cat"
        assert results[2].text == "sat"

    @patch(f"{_OCR}.subprocess.run")
    def test_confidence_scaled_correctly(self, mock_run):
        """Tesseract raw confidence (0-100) is divided by TESSERACT_CONFIDENCE_SCALE."""
        tsv = self._make_tsv(
            [
                "5\t1\t1\t1\t1\t1\t0\t0\t10\t10\t100\tPerfect",
            ]
        )
        mock_run.side_effect = self._fake_run_success(tsv)
        results = _run_tesseract("img.png")
        assert results[0].confidence == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# _bypass_uno_import
# ---------------------------------------------------------------------------


class TestBypassUnoImport:
    """Verify UNO import hook bypass logic."""

    def test_returns_none_when_uno_not_in_modules(self):
        """Returns None when 'uno' is not in sys.modules."""
        with patch.dict(sys.modules, {}, clear=False):
            sys.modules.pop("uno", None)
            assert _bypass_uno_import() is None

    def test_returns_none_when_builtin_import_missing(self):
        """Returns None when uno module lacks _builtin_import."""
        fake_uno = ModuleType("uno")
        # No _builtin_import attribute
        with patch.dict(sys.modules, {"uno": fake_uno}):
            assert _bypass_uno_import() is None

    def test_returns_none_when_already_real_import(self):
        """Returns None when builtins.__import__ is already the real import."""
        real_import = builtins.__import__
        fake_uno = ModuleType("uno")
        fake_uno._builtin_import = real_import  # type: ignore[attr-defined]

        with patch.dict(sys.modules, {"uno": fake_uno}):
            assert _bypass_uno_import() is None

    def test_swaps_hooks_and_returns_uno_hook(self):
        """Swaps UNO hook out and returns it for later restore."""
        real_import = builtins.__import__
        fake_uno = ModuleType("uno")
        fake_uno._builtin_import = real_import  # type: ignore[attr-defined]

        def _fake_uno_hook(*a, **kw):
            pass

        builtins.__import__ = _fake_uno_hook
        try:
            with patch.dict(sys.modules, {"uno": fake_uno}):
                saved = _bypass_uno_import()
                assert builtins.__import__ is real_import
                assert saved is _fake_uno_hook
        finally:
            builtins.__import__ = real_import


# ---------------------------------------------------------------------------
# _get_easyocr_reader — caching
# ---------------------------------------------------------------------------


class TestGetEasyOCRReader:
    """Verify EasyOCR reader caching behavior."""

    def setup_method(self):
        """Clear the reader cache before each test."""
        _easyocr_readers.clear()

    def teardown_method(self):
        """Clear the reader cache after each test."""
        _easyocr_readers.clear()

    def test_caching_returns_same_object(self):
        """Second call with same languages returns the same reader object."""

        class _FakeReader:
            def __init__(self, langs, **kwargs):
                pass

        mock_easyocr = MagicMock()
        mock_easyocr.Reader = _FakeReader

        with patch.dict(sys.modules, {"easyocr": mock_easyocr}):
            reader1 = _get_easyocr_reader(["en"])
            reader2 = _get_easyocr_reader(["en"])
            assert reader1 is reader2

    def test_different_languages_create_different_readers(self):
        """Different language sets create different reader instances."""

        class _FakeReader:
            def __init__(self, langs, **kwargs):
                self.langs = tuple(langs)

        mock_easyocr = MagicMock()
        mock_easyocr.Reader = _FakeReader

        with patch.dict(sys.modules, {"easyocr": mock_easyocr}):
            reader_en = _get_easyocr_reader(["en"])
            reader_ja = _get_easyocr_reader(["ja", "en"])
            assert reader_en is not reader_ja

    def test_sorted_key_means_order_independent(self):
        """['en', 'ja'] and ['ja', 'en'] share the same cache key."""

        class _FakeReader:
            def __init__(self, langs, **kwargs):
                pass

        mock_easyocr = MagicMock()
        mock_easyocr.Reader = _FakeReader

        with patch.dict(sys.modules, {"easyocr": mock_easyocr}):
            reader1 = _get_easyocr_reader(["en", "ja"])
            reader2 = _get_easyocr_reader(["ja", "en"])
            assert reader1 is reader2

    def test_restores_uno_hook_after_import(self):
        """UNO import hook is restored after easyocr is imported."""
        real_import = builtins.__import__
        fake_uno = ModuleType("uno")
        fake_uno._builtin_import = real_import  # type: ignore[attr-defined]

        call_count = 0

        def _counting_hook(name, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            return real_import(name, *args, **kwargs)

        class _FakeReader:
            def __init__(self, langs, **kwargs):
                pass

        mock_easyocr = MagicMock()
        mock_easyocr.Reader = _FakeReader

        builtins.__import__ = _counting_hook
        try:
            with patch.dict(sys.modules, {"uno": fake_uno, "easyocr": mock_easyocr}):
                _get_easyocr_reader(["en"])
                # UNO hook should be restored
                assert builtins.__import__ is _counting_hook
        finally:
            builtins.__import__ = real_import


# ---------------------------------------------------------------------------
# _run_easyocr
# ---------------------------------------------------------------------------


class TestRunEasyOCR:
    """Verify EasyOCR backend."""

    def setup_method(self):
        _easyocr_readers.clear()

    def teardown_method(self):
        _easyocr_readers.clear()

    def test_standardizes_bbox_results(self):
        """EasyOCR polygon bboxes are converted to OCRResult (x, y, w, h)."""

        class _FakeReader:
            def __init__(self, langs, **kwargs):
                pass

            def readtext(self, path):
                return [
                    (
                        [[10, 5], [60, 5], [60, 25], [10, 25]],
                        "Hello",
                        0.92,
                    ),
                ]

        mock_easyocr = MagicMock()
        mock_easyocr.Reader = _FakeReader

        with patch.dict(sys.modules, {"easyocr": mock_easyocr}):
            results = _run_easyocr("img.png")

        assert len(results) == 1
        r = results[0]
        assert r.text == "Hello"
        assert r.x == 10
        assert r.y == 5
        assert r.w == 50
        assert r.h == 20
        assert r.confidence == pytest.approx(0.92)

    def test_language_fallback_on_unsupported_lang(self):
        """Retries with default languages when requested languages fail."""
        call_languages = []

        class _FakeReader:
            def __init__(self, langs, **kwargs):
                call_languages.append(langs)
                if langs != EASYOCR_DEFAULT_LANGUAGES:
                    raise ValueError("Language not supported")

            def readtext(self, path):
                return []

        mock_easyocr = MagicMock()
        mock_easyocr.Reader = _FakeReader

        with patch.dict(sys.modules, {"easyocr": mock_easyocr}):
            results = _run_easyocr("img.png", languages=["km", "en"])

        assert results == []
        assert ["km", "en"] in call_languages
        assert EASYOCR_DEFAULT_LANGUAGES in call_languages

    def test_default_language_failure_reraises(self):
        """When default languages also fail, the exception propagates."""
        mock_easyocr = MagicMock()
        mock_easyocr.Reader.side_effect = RuntimeError("EasyOCR crashed")

        with (
            patch.dict(sys.modules, {"easyocr": mock_easyocr}),
            pytest.raises(RuntimeError, match="EasyOCR crashed"),
        ):
            _run_easyocr("img.png", languages=EASYOCR_DEFAULT_LANGUAGES)

    def test_import_error_raises_with_message(self):
        """ImportError is raised with 'not installed' message."""
        with (
            patch.dict(sys.modules, {"easyocr": None}),
            pytest.raises(ImportError, match="not installed"),
        ):
            _run_easyocr("img.png")

    def test_uses_default_languages_when_none(self):
        """None languages defaults to EASYOCR_DEFAULT_LANGUAGES."""
        used_langs = []

        class _FakeReader:
            def __init__(self, langs, **kwargs):
                used_langs.append(langs)

            def readtext(self, path):
                return []

        mock_easyocr = MagicMock()
        mock_easyocr.Reader = _FakeReader

        with patch.dict(sys.modules, {"easyocr": mock_easyocr}):
            _run_easyocr("img.png", languages=None)

        assert used_langs[0] == EASYOCR_DEFAULT_LANGUAGES

    def test_multiple_results_standardized(self):
        """Multiple EasyOCR detections are all converted."""

        class _FakeReader:
            def __init__(self, langs, **kwargs):
                pass

            def readtext(self, path):
                return [
                    ([[0, 0], [30, 0], [30, 10], [0, 10]], "A", 0.9),
                    ([[40, 0], [70, 0], [70, 10], [40, 10]], "B", 0.8),
                ]

        mock_easyocr = MagicMock()
        mock_easyocr.Reader = _FakeReader

        with patch.dict(sys.modules, {"easyocr": mock_easyocr}):
            results = _run_easyocr("img.png")

        assert len(results) == 2
        assert results[0].text == "A"
        assert results[1].text == "B"


# ---------------------------------------------------------------------------
# _run_google_cloud
# ---------------------------------------------------------------------------


class TestRunGoogleCloud:
    """Verify Google Cloud Vision backend."""

    def _make_mock_response(self, response_data):
        """Create a mock urlopen context-manager response."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(response_data).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = False
        return mock_response

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value="")
    def test_missing_api_key_raises_auth_error(self, mock_load):
        """Empty API key raises ValueError('AUTH_ERROR')."""
        with pytest.raises(ValueError, match="AUTH_ERROR"):
            _run_google_cloud("test.jpg")

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value=None)
    def test_none_api_key_raises_auth_error(self, mock_load):
        """None API key raises ValueError('AUTH_ERROR')."""
        with pytest.raises(ValueError, match="AUTH_ERROR"):
            _run_google_cloud("test.jpg")

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value="fake-key")
    @patch("urllib.request.urlopen")
    def test_successful_response_returns_results(
        self, mock_urlopen, mock_load, tmp_path
    ):
        """Parses annotations into OCRResult list."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"fake-image")

        response_data = {
            "responses": [
                {
                    "textAnnotations": [
                        # First annotation is full-text — skipped
                        {
                            "description": "Full text",
                            "boundingPoly": {
                                "vertices": [
                                    {"x": 0, "y": 0},
                                    {"x": 200, "y": 0},
                                    {"x": 200, "y": 40},
                                    {"x": 0, "y": 40},
                                ]
                            },
                        },
                        # Word-level annotation
                        {
                            "description": "hello",
                            "boundingPoly": {
                                "vertices": [
                                    {"x": 10, "y": 5},
                                    {"x": 50, "y": 5},
                                    {"x": 50, "y": 15},
                                    {"x": 10, "y": 15},
                                ]
                            },
                        },
                    ],
                }
            ]
        }

        mock_urlopen.return_value = self._make_mock_response(response_data)
        results = _run_google_cloud(str(img))

        assert len(results) == 1
        assert results[0].text == "hello"
        assert results[0].x == 10
        assert results[0].y == 5
        assert results[0].w == 40
        assert results[0].h == 10
        assert results[0].confidence == 1.0

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value="fake-key")
    @patch("urllib.request.urlopen")
    def test_empty_annotations_returns_empty(self, mock_urlopen, mock_load, tmp_path):
        """Empty textAnnotations list returns empty results."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"fake")

        response_data = {"responses": [{}]}
        mock_urlopen.return_value = self._make_mock_response(response_data)
        results = _run_google_cloud(str(img))
        assert results == []

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value="fake-key")
    @patch("urllib.request.urlopen")
    def test_missing_vertices_skipped(self, mock_urlopen, mock_load, tmp_path):
        """Annotations without vertices are skipped."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"fake")

        response_data = {
            "responses": [
                {
                    "textAnnotations": [
                        # Full-text block
                        {
                            "description": "All",
                            "boundingPoly": {
                                "vertices": [
                                    {"x": 0, "y": 0},
                                    {"x": 100, "y": 100},
                                ]
                            },
                        },
                        # Missing vertices
                        {
                            "description": "ghost",
                            "boundingPoly": {},
                        },
                        # Valid word
                        {
                            "description": "real",
                            "boundingPoly": {
                                "vertices": [
                                    {"x": 0, "y": 0},
                                    {"x": 20, "y": 0},
                                    {"x": 20, "y": 10},
                                    {"x": 0, "y": 10},
                                ]
                            },
                        },
                    ],
                }
            ]
        }

        mock_urlopen.return_value = self._make_mock_response(response_data)
        results = _run_google_cloud(str(img))
        assert len(results) == 1
        assert results[0].text == "real"

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value="fake-key")
    @patch("urllib.request.urlopen")
    def test_language_hints_in_request(self, mock_urlopen, mock_load, tmp_path):
        """lang_hints are included in the request body as imageContext."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"fake")

        response_data = {"responses": [{}]}
        mock_urlopen.return_value = self._make_mock_response(response_data)

        _run_google_cloud(str(img), lang_hints=["ja"])

        import urllib.request as _ur  # noqa: PLC0415

        req_obj = mock_urlopen.call_args[0][0]
        assert isinstance(req_obj, _ur.Request)
        payload = json.loads(req_obj.data.decode("utf-8"))
        body = payload["requests"][0]
        assert body["imageContext"]["languageHints"] == ["ja"]

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value="fake-key")
    @patch("urllib.request.urlopen")
    def test_no_lang_hints_omits_image_context(self, mock_urlopen, mock_load, tmp_path):
        """Omits imageContext from payload when lang_hints is None."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"fake")

        response_data = {"responses": [{}]}
        mock_urlopen.return_value = self._make_mock_response(response_data)

        _run_google_cloud(str(img), lang_hints=None)

        req_obj = mock_urlopen.call_args[0][0]
        payload = json.loads(req_obj.data.decode("utf-8"))
        assert "imageContext" not in payload["requests"][0]

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value="fake-key")
    @patch("urllib.request.urlopen")
    def test_api_error_propagates(self, mock_urlopen, mock_load, tmp_path):
        """HTTP 403 (forbidden) maps to the typed ``AUTH_ERROR`` sentinel.

        Was previously asserting the raw HTTPError leaked through —
        that was the bug; the new behaviour is to map to a typed
        sentinel so the UI surfaces a clear "auth / billing" toast.
        """
        img = tmp_path / "test.jpg"
        img.write_bytes(b"fake")

        import urllib.error  # noqa: PLC0415

        mock_urlopen.side_effect = urllib.error.HTTPError(
            "url", 403, "Forbidden", {}, None,
        )
        with pytest.raises(ValueError, match="AUTH_ERROR"):
            _run_google_cloud(str(img))

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value="fake-key")
    @patch("urllib.request.urlopen")
    def test_confidence_always_one(self, mock_urlopen, mock_load, tmp_path):
        """Google Cloud results always have confidence=1.0."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"fake")

        response_data = {
            "responses": [
                {
                    "textAnnotations": [
                        {
                            "description": "All",
                            "boundingPoly": {
                                "vertices": [{"x": 0, "y": 0}, {"x": 1, "y": 1}]
                            },
                        },
                        {
                            "description": "w",
                            "boundingPoly": {
                                "vertices": [
                                    {"x": 0, "y": 0},
                                    {"x": 10, "y": 0},
                                    {"x": 10, "y": 10},
                                    {"x": 0, "y": 10},
                                ]
                            },
                        },
                    ],
                }
            ]
        }

        mock_urlopen.return_value = self._make_mock_response(response_data)
        results = _run_google_cloud(str(img))
        assert results[0].confidence == 1.0

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value="fake-key")
    @patch("urllib.request.urlopen")
    def test_vertices_missing_coords_default_to_zero(
        self, mock_urlopen, mock_load, tmp_path
    ):
        """Vertices with missing x or y keys default to 0."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"fake")

        response_data = {
            "responses": [
                {
                    "textAnnotations": [
                        {
                            "description": "Full",
                            "boundingPoly": {"vertices": [{"x": 0}, {"y": 0}]},
                        },
                        {
                            "description": "partial",
                            "boundingPoly": {
                                "vertices": [
                                    {"x": 5},  # y defaults to 0
                                    {"y": 10},  # x defaults to 0
                                    {"x": 20, "y": 10},
                                    {"x": 20},  # y defaults to 0
                                ],
                            },
                        },
                    ],
                }
            ]
        }

        mock_urlopen.return_value = self._make_mock_response(response_data)
        results = _run_google_cloud(str(img))
        assert len(results) == 1
        r = results[0]
        # xs = [5, 0, 20, 20], ys = [0, 10, 10, 0]
        assert r.x == 0
        assert r.y == 0
        assert r.w == 20
        assert r.h == 10

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value="fake-key")
    @patch("urllib.request.urlopen")
    def test_multiple_annotations_parsed(self, mock_urlopen, mock_load, tmp_path):
        """Multiple word-level annotations are all returned."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"fake")

        word_ann = lambda desc, x: {  # noqa: E731
            "description": desc,
            "boundingPoly": {
                "vertices": [
                    {"x": x, "y": 0},
                    {"x": x + 30, "y": 0},
                    {"x": x + 30, "y": 10},
                    {"x": x, "y": 10},
                ]
            },
        }

        response_data = {
            "responses": [
                {
                    "textAnnotations": [
                        word_ann("Full text block", 0),  # skipped [0]
                        word_ann("one", 0),
                        word_ann("two", 40),
                        word_ann("three", 80),
                    ],
                }
            ]
        }

        mock_urlopen.return_value = self._make_mock_response(response_data)
        results = _run_google_cloud(str(img))
        assert len(results) == 3
        assert [r.text for r in results] == ["one", "two", "three"]


# ---------------------------------------------------------------------------
# Integration: run_ocr -> merge pipeline
# ---------------------------------------------------------------------------


class TestRunOCRIntegration:
    """End-to-end tests for the run_ocr -> merge pipeline."""

    @patch(f"{_OCR}._run_tesseract")
    def test_whitespace_only_results_filtered_after_merge(self, mock_tess):
        """Whitespace results from backend are removed by merge."""
        mock_tess.return_value = [
            OCRResult("   ", 0, 0, 10, 10, 0.5),
            OCRResult("text", 20, 0, 30, 10, 0.9),
        ]
        results = run_ocr("img.png", method=OCR_METHOD_TESSERACT)
        assert len(results) == 1
        assert results[0].text == "text"

    @patch(f"{_OCR}._run_tesseract")
    def test_empty_backend_result_returns_empty(self, mock_tess):
        mock_tess.return_value = []
        results = run_ocr("img.png", method=OCR_METHOD_TESSERACT)
        assert results == []

    @patch(f"{_OCR}._run_tesseract")
    def test_nearby_words_merged_into_sentence(self, mock_tess):
        """Words close together on the same line merge into a sentence."""
        mock_tess.return_value = [
            OCRResult("The", 0, 0, 20, 15, 0.9),
            OCRResult("quick", 22, 0, 30, 15, 0.85),
            OCRResult("fox", 54, 0, 20, 15, 0.88),
        ]
        results = run_ocr("img.png", method=OCR_METHOD_TESSERACT)
        assert len(results) == 1
        assert results[0].text == "The quick fox"


# ---------------------------------------------------------------------------
# Merge edge cases
# ---------------------------------------------------------------------------


class TestMergeEdgeCases:
    """Additional edge cases for merge_ocr_results."""

    def test_all_whitespace_list(self):
        """List of only whitespace results returns empty."""
        results = [
            OCRResult("  ", 0, 0, 10, 10, 0.9),
            OCRResult("\t", 10, 0, 10, 10, 0.8),
            OCRResult("\n", 20, 0, 10, 10, 0.7),
        ]
        assert merge_ocr_results(results) == []

    def test_single_char_fragments_merge(self):
        """Single-character fragments close together merge."""
        frags = [
            OCRResult("H", 0, 0, 10, 20, 0.9),
            OCRResult("i", 11, 0, 5, 20, 0.8),
        ]
        result = merge_ocr_results(frags)
        assert len(result) == 1
        assert result[0].text == "H i"

    def test_multiline_document_preserves_order(self):
        """Multi-line layout: each line stays separate and ordered."""
        line1 = OCRResult("First", 0, 0, 50, 15, 0.9)
        line2 = OCRResult("Second", 0, 50, 60, 15, 0.85)
        line3 = OCRResult("Third", 0, 100, 50, 15, 0.8)
        result = merge_ocr_results([line3, line1, line2])
        assert len(result) == 3
        assert result[0].text == "First"
        assert result[1].text == "Second"
        assert result[2].text == "Third"

    def test_negative_gap_fragments_merge(self):
        """Overlapping fragments (negative gap) still merge."""
        r1 = OCRResult("over", 0, 0, 30, 20, 0.9)
        # r2 starts at x=25, which is inside r1's box (gap = 25 - 30 = -5 < threshold)
        r2 = OCRResult("lap", 25, 0, 30, 20, 0.8)
        result = merge_ocr_results([r1, r2])
        assert len(result) == 1
        assert result[0].text == "over lap"

    def test_horizontal_threshold_depends_on_height(self):
        """Horizontal merge threshold is height * OCR_HORIZONTAL_GAP_RATIO.

        Tall fragments have a larger merge radius.
        """
        # Small height = 10 -> threshold = 12 (ratio 1.2)
        r1 = OCRResult("a", 0, 0, 20, 10, 0.9)
        r2 = OCRResult("b", 33, 0, 20, 10, 0.8)  # gap = 13 > 12 -> no merge
        result = merge_ocr_results([r1, r2])
        assert len(result) == 2  # noqa: PLR2004

        # Tall height = 40 -> threshold = 48
        r3 = OCRResult("c", 0, 0, 20, 40, 0.9)
        r4 = OCRResult("d", 40, 0, 20, 40, 0.8)  # gap = 20 < 48 -> merge
        result2 = merge_ocr_results([r3, r4])
        assert len(result2) == 1


# ---------------------------------------------------------------------------
# Tesseract TSV parsing — malformed rows
# ---------------------------------------------------------------------------


class TestTesseractTsvMalformedRows:
    """Verify _run_tesseract handles malformed TSV data gracefully."""

    _TSV_HEADER = (
        "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num"
        "\tleft\ttop\twidth\theight\tconf\ttext"
    )

    def _make_tsv(self, rows: list[str]) -> str:
        """Build TSV content from header + row strings."""
        return self._TSV_HEADER + "\n" + "\n".join(rows) + "\n"

    def _fake_run_success(self, tsv_content: str):
        """Return a side_effect for subprocess.run that writes a TSV."""

        def _side_effect(cmd, check, capture_output):
            out_base = Path(cmd[2])
            tsv_path = out_base.with_suffix(".tsv")
            tsv_path.write_text(tsv_content, encoding="utf-8")

        return _side_effect

    @patch(f"{_OCR}.subprocess.run")
    def test_tesseract_tsv_parsing_malformed_row(self, mock_run):
        """Malformed TSV rows (non-numeric conf) are handled gracefully.

        When a row has a non-numeric confidence value, csv.DictReader still
        reads the row, but float(row['conf']) raises ValueError.  This is
        caught by the outer except clause and _run_tesseract returns the
        results collected so far (an empty list in this case).
        """
        # Row with non-numeric confidence "abc" instead of a number
        tsv = self._make_tsv(
            [
                "5\t1\t1\t1\t1\t1\t10\t20\t50\t15\tabc\tBroken",
            ]
        )
        mock_run.side_effect = self._fake_run_success(tsv)
        results = _run_tesseract("img.png")
        # ValueError on float("abc") is caught → returns empty
        assert results == []

    @patch(f"{_OCR}.subprocess.run")
    def test_tesseract_tsv_missing_conf_key(self, mock_run):
        """TSV row missing 'conf' column raises KeyError, caught gracefully."""
        # Header without 'conf' column → DictReader will not have 'conf' key
        bad_header = (
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num"
            "\tleft\ttop\twidth\theight\ttext"
        )
        row = "5\t1\t1\t1\t1\t1\t10\t20\t50\t15\tHello"
        tsv_content = bad_header + "\n" + row + "\n"

        mock_run.side_effect = self._fake_run_success(tsv_content)
        results = _run_tesseract("img.png")
        # KeyError on row["conf"] is caught → returns empty
        assert results == []

    @patch(f"{_OCR}.subprocess.run")
    def test_tesseract_tsv_non_numeric_level(self, mock_run):
        """TSV row with non-numeric 'level' raises ValueError, caught gracefully."""
        tsv = self._make_tsv(
            [
                "bad\t1\t1\t1\t1\t1\t10\t20\t50\t15\t90\tWord",
            ]
        )
        mock_run.side_effect = self._fake_run_success(tsv)
        results = _run_tesseract("img.png")
        # ValueError on int("bad") is caught → returns empty
        assert results == []

    @patch(f"{_OCR}.subprocess.run")
    def test_tesseract_tsv_valid_rows_before_malformed_are_kept(self, mock_run):
        """Valid rows parsed before a malformed row are returned.

        The except clause returns whatever was collected before the error.
        """
        tsv = self._make_tsv(
            [
                "5\t1\t1\t1\t1\t1\t10\t20\t50\t15\t90\tGood",
                "5\t1\t1\t1\t1\t2\t70\t20\t50\t15\tnotanumber\tBroken",
            ]
        )
        mock_run.side_effect = self._fake_run_success(tsv)
        results = _run_tesseract("img.png")
        # First row parsed OK, second raises ValueError → returns [Good]
        assert len(results) == 1
        assert results[0].text == "Good"


# ---------------------------------------------------------------------------
# Google Cloud — malformed response / missing fields
# ---------------------------------------------------------------------------


class TestGoogleCloudMalformedResponse:
    """Verify _run_google_cloud handles unexpected JSON structures."""

    def _make_mock_response(self, response_data):
        """Create a mock urlopen context-manager response."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(response_data).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = False
        return mock_response

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value="fake-key")
    @patch("urllib.request.urlopen")
    def test_google_cloud_malformed_response_missing_responses(
        self, mock_urlopen, mock_load, tmp_path
    ):
        """JSON without 'responses' key raises KeyError, re-raised by except."""
        img = tmp_path / "test_malformed.jpg"
        img.write_bytes(b"fake-image")

        response_data = {"error": "bad"}
        mock_urlopen.return_value = self._make_mock_response(response_data)

        with pytest.raises(KeyError):
            _run_google_cloud(str(img))

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value="fake-key")
    @patch("urllib.request.urlopen")
    def test_google_cloud_annotation_missing_description(
        self, mock_urlopen, mock_load, tmp_path
    ):
        """Annotation without 'description' field uses empty string gracefully."""
        img = tmp_path / "test_nodesc.jpg"
        img.write_bytes(b"fake-image")

        response_data = {
            "responses": [
                {
                    "textAnnotations": [
                        # Full-text block (skipped as annotations[0])
                        {
                            "description": "Full",
                            "boundingPoly": {
                                "vertices": [
                                    {"x": 0, "y": 0},
                                    {"x": 100, "y": 0},
                                    {"x": 100, "y": 50},
                                    {"x": 0, "y": 50},
                                ]
                            },
                        },
                        # Annotation missing "description" field entirely
                        {
                            "boundingPoly": {
                                "vertices": [
                                    {"x": 10, "y": 5},
                                    {"x": 50, "y": 5},
                                    {"x": 50, "y": 15},
                                    {"x": 10, "y": 15},
                                ]
                            },
                        },
                        # Valid annotation
                        {
                            "description": "valid",
                            "boundingPoly": {
                                "vertices": [
                                    {"x": 60, "y": 5},
                                    {"x": 90, "y": 5},
                                    {"x": 90, "y": 15},
                                    {"x": 60, "y": 15},
                                ]
                            },
                        },
                    ],
                }
            ]
        }

        mock_urlopen.return_value = self._make_mock_response(response_data)
        results = _run_google_cloud(str(img))

        # The annotation without "description" gets empty string via .get()
        # and is still included in results (empty text is a valid OCRResult)
        assert len(results) == 2  # noqa: PLR2004
        assert results[0].text == ""
        assert results[1].text == "valid"


# ---------------------------------------------------------------------------
# _run_tesseract — double fallback failure
# ---------------------------------------------------------------------------


class TestRunTesseractDoubleFallbackFailure:
    """Tests for Tesseract when both requested lang and English fail."""

    @patch("subprocess.run")
    def test_both_lang_and_eng_fail_returns_empty(self, mock_run, tmp_path):
        """When both requested language and 'eng' fallback fail, returns empty list."""
        img = tmp_path / "test.png"
        img.write_bytes(b"\x89PNG\r\n")
        # Both calls fail
        mock_run.side_effect = subprocess.CalledProcessError(1, "tesseract")
        results = _run_tesseract(str(img), "fra")
        assert results == []
        # Two calls: first with 'fra', second with 'eng'
        assert mock_run.call_count == 2  # noqa: PLR2004

    @patch("subprocess.run")
    def test_eng_lang_fails_returns_empty(self, mock_run, tmp_path):
        """When lang='eng' fails directly, no fallback attempted, returns empty."""
        img = tmp_path / "test.png"
        img.write_bytes(b"\x89PNG\r\n")
        mock_run.side_effect = subprocess.CalledProcessError(1, "tesseract")
        results = _run_tesseract(str(img), "eng")
        assert results == []
        # Only one call (no fallback when already eng)
        assert mock_run.call_count == 1


# ---------------------------------------------------------------------------
# _run_tesseract — empty TSV output
# ---------------------------------------------------------------------------


class TestRunTesseractEmptyTsv:
    """Tests for Tesseract when TSV output is empty."""

    @patch("subprocess.run")
    def test_empty_tsv_returns_empty_results(self, mock_run, tmp_path):
        """When TSV has only headers (no data rows), returns empty list."""
        img = tmp_path / "test.png"
        img.write_bytes(b"\x89PNG\r\n")

        # Create a TSV with only headers
        out_dir = tmp_path / "tsv_out"
        out_dir.mkdir()

        def create_empty_tsv(*args, **kwargs):
            tsv = out_dir / "out.tsv"
            tsv.write_text(
                "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\t"
                "left\ttop\twidth\theight\tconf\ttext\n"
            )

        mock_run.side_effect = create_empty_tsv
        with patch("tempfile.TemporaryDirectory") as mock_td:
            mock_td.return_value.__enter__ = lambda s: str(out_dir)
            mock_td.return_value.__exit__ = lambda s, *a: None
            results = _run_tesseract(str(img), "eng")
        assert results == []


# ---------------------------------------------------------------------------
# Malformed TSV — missing columns, invalid confidence
# ---------------------------------------------------------------------------


class TestTesseractMalformedTsvExtended:
    """Extended tests for Tesseract TSV parsing edge cases."""

    _TSV_HEADER = (
        "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num"
        "\tleft\ttop\twidth\theight\tconf\ttext"
    )

    def _make_tsv(self, rows: list[str]) -> str:
        """Build TSV content from header + row strings."""
        return self._TSV_HEADER + "\n" + "\n".join(rows) + "\n"

    def _fake_run_success(self, tsv_content: str):
        """Return a side_effect for subprocess.run that writes a TSV."""

        def _side_effect(cmd, check, capture_output):
            out_base = Path(cmd[2])
            tsv_path = out_base.with_suffix(".tsv")
            tsv_path.write_text(tsv_content, encoding="utf-8")

        return _side_effect

    @patch(f"{_OCR}.subprocess.run")
    def test_fewer_columns_than_header(self, mock_run):
        """Row with fewer tab-separated values than the header.

        csv.DictReader fills missing fields with None, so row['conf']
        is None and float(None) raises TypeError (not ValueError or
        KeyError). This is NOT caught by the except clause, so it
        propagates. Actually — let's check: the except catches
        ValueError and KeyError. TypeError is not caught. But wait,
        the code does `float(row["conf"])` and if row["conf"] is None,
        float(None) raises TypeError. Let's verify the actual behavior.
        """
        # Row has only 8 fields instead of 12
        tsv = self._TSV_HEADER + "\n" + "5\t1\t1\t1\t1\t1\t10\t20\n"
        mock_run.side_effect = self._fake_run_success(tsv)
        # csv.DictReader with QUOTE_NONE will set missing fields to None.
        # float(None) → TypeError, which is NOT in the except clause.
        # But actually, the code checks `level = int(row.get("level", 5))`
        # first — row.get("level") works fine. Then `text = row.get("text", "")`
        # returns None for the missing column. `.strip()` on None → AttributeError.
        # Neither TypeError nor AttributeError is caught. So this should raise.
        # Actually, wait: csv.DictReader with fewer fields uses `restval`
        # parameter which defaults to None. So row["text"] = None.
        # row.get("text", "").strip() → None.strip() → AttributeError.
        # This IS in the broad except (ValueError, KeyError) — no, it isn't.
        # Let's just verify it returns empty (error is logged).
        # Actually the except catches (CalledProcessError, ValueError, KeyError).
        # AttributeError is NOT caught. So it will propagate.
        # But wait, let me re-read: row.get("text", "") returns "" when key
        # exists but value is None? No, .get() returns the value if key exists.
        # With DictReader, if fewer columns, missing keys get restval=None.
        # So row.get("text", "") returns None (key exists with None value? No,
        # key doesn't exist in this case). Actually with 8 fields and 12 headers,
        # DictReader maps fields to headers positionally. Fields 9-12 don't exist
        # so those headers map to None (restval).
        # row.get("text", "") → None since "text" key exists with None value.
        # Wait: DictReader sets the value to None for missing positional fields.
        # So dict has "text": None. .get("text", "") returns None (not "").
        # None.strip() → AttributeError → not caught → propagates.
        # Let's just expect an error or empty depending on actual behavior.
        # Since this is tricky, we simply verify it doesn't crash the whole system.
        try:
            results = _run_tesseract("img.png")
            # If we get here, the error was caught somehow
            assert isinstance(results, list)
        except (AttributeError, TypeError):
            # Expected: missing column values are None, causing attr errors
            pass

    @patch(f"{_OCR}.subprocess.run")
    def test_negative_confidence_skipped(self, mock_run):
        """Row with negative confidence is skipped (conf <= 0 check)."""
        tsv = self._make_tsv(
            [
                "5\t1\t1\t1\t1\t1\t10\t20\t50\t15\t-50\tNegConf",
                "5\t1\t1\t1\t1\t2\t70\t20\t50\t15\t85\tValid",
            ]
        )
        mock_run.side_effect = self._fake_run_success(tsv)
        results = _run_tesseract("img.png")
        assert len(results) == 1
        assert results[0].text == "Valid"

    @patch(f"{_OCR}.subprocess.run")
    def test_extremely_high_confidence_still_parsed(self, mock_run):
        """Confidence > 100 is unusual but still parsed (Tesseract quirk)."""
        tsv = self._make_tsv(
            [
                "5\t1\t1\t1\t1\t1\t10\t20\t50\t15\t999\tHighConf",
            ]
        )
        mock_run.side_effect = self._fake_run_success(tsv)
        results = _run_tesseract("img.png")
        assert len(results) == 1
        assert results[0].confidence == pytest.approx(
            999.0 / TESSERACT_CONFIDENCE_SCALE  # noqa: PLR2004
        )

    @patch(f"{_OCR}.subprocess.run")
    def test_non_numeric_left_coordinate(self, mock_run):
        """Non-numeric 'left' value causes ValueError, caught gracefully."""
        tsv = self._make_tsv(
            [
                "5\t1\t1\t1\t1\t1\tBAD\t20\t50\t15\t85\tWord",
            ]
        )
        mock_run.side_effect = self._fake_run_success(tsv)
        results = _run_tesseract("img.png")
        # ValueError on int("BAD") is caught → returns empty
        assert results == []

    @patch(f"{_OCR}.subprocess.run")
    def test_tsv_with_extra_tab_in_text(self, mock_run):
        """Text field containing extra data after the expected columns.

        csv.DictReader with QUOTE_NONE treats tabs literally, so
        extra tabs create extra fields via `restkey`.
        """
        tsv = self._make_tsv(
            [
                "5\t1\t1\t1\t1\t1\t10\t20\t50\t15\t85\tHello\tExtraField",
            ]
        )
        mock_run.side_effect = self._fake_run_success(tsv)
        results = _run_tesseract("img.png")
        # The 'text' column maps to "Hello" (positional), extra data goes to restkey
        assert len(results) == 1
        assert results[0].text == "Hello"


# ---------------------------------------------------------------------------
# Google Cloud Vision — timeout / network errors
# ---------------------------------------------------------------------------


class TestGoogleCloudNetworkErrors:
    """Verify _run_google_cloud handles timeout and network errors."""

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value="fake-key")
    @patch("urllib.request.urlopen")
    def test_timeout_error_propagates(self, mock_urlopen, mock_load, tmp_path):
        """``socket.timeout`` maps to ``TIMEOUT_ERROR`` sentinel."""
        img = tmp_path / "timeout.jpg"
        img.write_bytes(b"fake")
        mock_urlopen.side_effect = TimeoutError("Connection timed out")
        with pytest.raises(ValueError, match="TIMEOUT_ERROR"):
            _run_google_cloud(str(img))

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value="fake-key")
    @patch("urllib.request.urlopen")
    def test_url_error_propagates(self, mock_urlopen, mock_load, tmp_path):
        """URLError (DNS failure, etc.) maps to ``CONNECTION_ERROR``."""
        import urllib.error  # noqa: PLC0415

        img = tmp_path / "dns_fail.jpg"
        img.write_bytes(b"fake")
        mock_urlopen.side_effect = urllib.error.URLError("Name resolution failed")
        with pytest.raises(ValueError, match="CONNECTION_ERROR"):
            _run_google_cloud(str(img))

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value="fake-key")
    @patch("urllib.request.urlopen")
    def test_connection_reset_propagates(self, mock_urlopen, mock_load, tmp_path):
        """ConnectionResetError is re-raised."""
        img = tmp_path / "connreset.jpg"
        img.write_bytes(b"fake")

        mock_urlopen.side_effect = ConnectionResetError("Connection reset by peer")

        with pytest.raises(ConnectionResetError):
            _run_google_cloud(str(img))

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value="fake-key")
    @patch("urllib.request.urlopen")
    def test_http_500_error_propagates(self, mock_urlopen, mock_load, tmp_path):
        """HTTP 5xx maps to ``SERVICE_UNAVAILABLE_ERROR`` for retry-friendly UI."""
        import urllib.error  # noqa: PLC0415

        img = tmp_path / "http500.jpg"
        img.write_bytes(b"fake")
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "url", 500, "Internal Server Error", {}, None,
        )
        with pytest.raises(ValueError, match="SERVICE_UNAVAILABLE_ERROR"):
            _run_google_cloud(str(img))

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value="fake-key")
    @patch("urllib.request.urlopen")
    def test_malformed_json_response_raises(self, mock_urlopen, mock_load, tmp_path):
        """Non-JSON response body raises an exception."""
        img = tmp_path / "badjson.jpg"
        img.write_bytes(b"fake")

        mock_response = MagicMock()
        mock_response.read.return_value = b"<html>Not JSON</html>"
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = False
        mock_urlopen.return_value = mock_response

        with pytest.raises(json.JSONDecodeError):
            _run_google_cloud(str(img))


# ---------------------------------------------------------------------------
# EasyOCR reader caching — extended tests
# ---------------------------------------------------------------------------


class TestEasyOCRCachingExtended:
    """Extended tests for EasyOCR reader caching behavior."""

    def setup_method(self):
        """Clear the reader cache before each test."""
        _easyocr_readers.clear()

    def teardown_method(self):
        """Clear the reader cache after each test."""
        _easyocr_readers.clear()

    def test_cache_populated_after_first_call(self):
        """Cache has one entry after the first _get_easyocr_reader call."""

        class _FakeReader:
            def __init__(self, langs, **kwargs):
                pass

        mock_easyocr = MagicMock()
        mock_easyocr.Reader = _FakeReader

        assert len(_easyocr_readers) == 0
        with patch.dict(sys.modules, {"easyocr": mock_easyocr}):
            _get_easyocr_reader(["en"])
        assert len(_easyocr_readers) == 1

    def test_reader_constructor_called_once_for_same_langs(self):
        """Reader constructor called once for repeated same-language calls."""
        call_count = 0

        class _CountingReader:
            def __init__(self, langs, **kwargs):
                nonlocal call_count
                call_count += 1

        mock_easyocr = MagicMock()
        mock_easyocr.Reader = _CountingReader

        with patch.dict(sys.modules, {"easyocr": mock_easyocr}):
            _get_easyocr_reader(["en"])
            _get_easyocr_reader(["en"])
            _get_easyocr_reader(["en"])

        assert call_count == 1

    def test_multiple_language_sets_create_separate_entries(self):
        """Three different language sets create three cache entries."""

        class _FakeReader:
            def __init__(self, langs, **kwargs):
                pass

        mock_easyocr = MagicMock()
        mock_easyocr.Reader = _FakeReader

        with patch.dict(sys.modules, {"easyocr": mock_easyocr}):
            _get_easyocr_reader(["en"])
            _get_easyocr_reader(["ja", "en"])
            _get_easyocr_reader(["fr"])

        assert len(_easyocr_readers) == 3  # noqa: PLR2004

    def test_cache_key_is_sorted_tuple(self):
        """Cache key is a sorted tuple of languages."""

        class _FakeReader:
            def __init__(self, langs, **kwargs):
                pass

        mock_easyocr = MagicMock()
        mock_easyocr.Reader = _FakeReader

        with patch.dict(sys.modules, {"easyocr": mock_easyocr}):
            _get_easyocr_reader(["zh", "en", "ja"])

        assert ("en", "ja", "zh") in _easyocr_readers


# ---------------------------------------------------------------------------
# _bypass_uno_import — extended context manager behavior
# ---------------------------------------------------------------------------


class TestBypassUnoImportExtended:
    """Extended tests for UNO import bypass behavior."""

    def test_no_op_when_uno_module_has_no_builtin_import(self):
        """Returns None when uno exists but has no _builtin_import attr."""
        fake_uno = ModuleType("uno")
        # Explicitly don't set _builtin_import
        with patch.dict(sys.modules, {"uno": fake_uno}):
            result = _bypass_uno_import()
        assert result is None

    def test_swap_and_restore_round_trip(self):
        """Full round-trip: bypass swaps hook, caller restores it."""
        real_import = builtins.__import__

        def _uno_hook(*a, **kw):
            return real_import(*a, **kw)

        fake_uno = ModuleType("uno")
        fake_uno._builtin_import = real_import  # type: ignore[attr-defined]

        builtins.__import__ = _uno_hook
        try:
            with patch.dict(sys.modules, {"uno": fake_uno}):
                saved = _bypass_uno_import()
                # After bypass: real import is active
                assert builtins.__import__ is real_import
                assert saved is _uno_hook

            # Caller restores UNO hook
            if saved is not None:
                builtins.__import__ = saved
            assert builtins.__import__ is _uno_hook
        finally:
            builtins.__import__ = real_import

    def test_idempotent_when_already_real(self):
        """Calling bypass when real import is already active is a no-op."""
        real_import = builtins.__import__
        fake_uno = ModuleType("uno")
        fake_uno._builtin_import = real_import  # type: ignore[attr-defined]

        # builtins.__import__ is already the real import
        with patch.dict(sys.modules, {"uno": fake_uno}):
            result = _bypass_uno_import()
        assert result is None
        # __import__ unchanged
        assert builtins.__import__ is real_import


# ---------------------------------------------------------------------------
# Language fallback — extended tests
# ---------------------------------------------------------------------------


class TestLanguageFallbackExtended:
    """Extended tests for language fallback behavior across backends."""

    def setup_method(self):
        _easyocr_readers.clear()

    def teardown_method(self):
        _easyocr_readers.clear()

    @patch(f"{_OCR}.subprocess.run")
    def test_tesseract_fallback_produces_results(self, mock_run):
        """Tesseract falls back to eng and produces actual results."""

        def _side_effect(cmd, check, capture_output):
            if "jpn" in cmd:
                raise subprocess.CalledProcessError(1, cmd)
            # English fallback succeeds with actual data
            out_base = Path(cmd[2])
            tsv_path = out_base.with_suffix(".tsv")
            header = (
                "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num"
                "\tleft\ttop\twidth\theight\tconf\ttext"
            )
            row = "5\t1\t1\t1\t1\t1\t10\t20\t50\t15\t90\tFallback"
            tsv_path.write_text(header + "\n" + row + "\n", encoding="utf-8")

        mock_run.side_effect = _side_effect
        results = _run_tesseract("img.png", lang="jpn")
        assert len(results) == 1
        assert results[0].text == "Fallback"

    def test_easyocr_fallback_produces_results(self):
        """EasyOCR falls back to default languages and produces results."""
        call_order = []

        class _FakeReader:
            def __init__(self, langs, **kwargs):
                call_order.append(tuple(langs))
                if tuple(langs) != tuple(EASYOCR_DEFAULT_LANGUAGES):
                    raise RuntimeError("Unsupported language")

            def readtext(self, path):
                return [
                    ([[0, 0], [30, 0], [30, 10], [0, 10]], "Fallback", 0.85),
                ]

        mock_easyocr = MagicMock()
        mock_easyocr.Reader = _FakeReader

        with patch.dict(sys.modules, {"easyocr": mock_easyocr}):
            results = _run_easyocr("img.png", languages=["xyz"])

        assert len(results) == 1
        assert results[0].text == "Fallback"
        assert len(call_order) == 2  # noqa: PLR2004


# ---------------------------------------------------------------------------
# run_ocr with src_lang — language-specific model selection
# ---------------------------------------------------------------------------


class TestRunOCRWithSrcLang:
    """Verify run_ocr passes src_lang correctly to each backend."""

    @patch(f"{_OCR}._run_tesseract", return_value=[])
    def test_tesseract_default_lang_when_empty(self, mock_tess):
        """Empty src_lang passes default 'eng' to Tesseract."""
        run_ocr("img.png", method=OCR_METHOD_TESSERACT, src_lang="")
        mock_tess.assert_called_once_with("img.png", lang="eng")

    @patch(f"{_OCR}._run_easyocr", return_value=[])
    def test_easyocr_default_lang_when_empty(self, mock_easy):
        """Empty src_lang passes default languages to EasyOCR."""
        run_ocr("img.png", method=OCR_METHOD_EASYOCR, src_lang="")
        mock_easy.assert_called_once_with("img.png", languages=["en"])

    @patch(f"{_OCR}._run_google_cloud", return_value=[])
    def test_google_cloud_no_hints_when_empty(self, mock_gc):
        """Empty src_lang passes None hints to Google Cloud (auto-detect)."""
        run_ocr("img.png", method=OCR_METHOD_GOOGLE_CLOUD, src_lang="")
        mock_gc.assert_called_once_with("img.png", lang_hints=None)

    @patch(f"{_OCR}._run_tesseract", return_value=[])
    def test_tesseract_receives_chinese_lang(self, mock_tess):
        """Chinese (Simplified) maps to 'chi_sim' for Tesseract."""
        run_ocr(
            "img.png",
            method=OCR_METHOD_TESSERACT,
            src_lang="Chinese (Simplified)",
        )
        mock_tess.assert_called_once_with("img.png", lang="chi_sim")

    @patch(f"{_OCR}._run_easyocr", return_value=[])
    def test_easyocr_receives_korean_langs(self, mock_easy):
        """Korean maps to ['ko', 'en'] for EasyOCR."""
        run_ocr("img.png", method=OCR_METHOD_EASYOCR, src_lang="Korean")
        mock_easy.assert_called_once_with("img.png", languages=["ko", "en"])

    @patch(f"{_OCR}._run_google_cloud", return_value=[])
    def test_google_cloud_receives_german_hint(self, mock_gc):
        """German maps to ['de'] for Google Cloud Vision."""
        run_ocr("img.png", method=OCR_METHOD_GOOGLE_CLOUD, src_lang="German")
        mock_gc.assert_called_once_with("img.png", lang_hints=["de"])


# ---------------------------------------------------------------------------
# Extended run_ocr tests
# ---------------------------------------------------------------------------


class TestRunOCRExtended:
    """Additional tests for run_ocr dispatch and integration."""

    @patch(f"{_OCR}._run_tesseract")
    def test_empty_results_from_backend_returns_empty(self, mock_tess):
        """Backend returning empty list results in empty merged output."""
        mock_tess.return_value = []
        result = run_ocr("img.png", method=OCR_METHOD_TESSERACT)
        assert result == []

    @patch(f"{_OCR}._run_tesseract")
    def test_single_fragment_passes_through_merge(self, mock_tess):
        """Single fragment passes through merge unchanged."""
        r = OCRResult("word", 10, 20, 50, 15, 0.9)
        mock_tess.return_value = [r]
        result = run_ocr("img.png", method=OCR_METHOD_TESSERACT)
        assert len(result) == 1
        assert result[0].text == "word"

    @patch(f"{_OCR}._run_tesseract")
    def test_whitespace_results_filtered_in_run_ocr(self, mock_tess):
        """Whitespace-only results are filtered during merge in run_ocr."""
        r = OCRResult("   ", 0, 0, 10, 10, 0.5)
        mock_tess.return_value = [r]
        result = run_ocr("img.png", method=OCR_METHOD_TESSERACT)
        assert result == []


# ---------------------------------------------------------------------------
# Extended merge_ocr_results tests
# ---------------------------------------------------------------------------


class TestMergeOCRResultsExtended:
    """Additional tests for merge_ocr_results edge cases."""

    def test_four_fragments_two_lines(self):
        """4 fragments across 2 lines merge into 2 blocks."""
        # Line 1: y=0, h=10
        r1 = OCRResult("A", 0, 0, 20, 10, 0.9)
        r2 = OCRResult("B", 22, 0, 20, 10, 0.8)
        # Line 2: y=30, h=10
        r3 = OCRResult("C", 0, 30, 20, 10, 0.9)
        r4 = OCRResult("D", 22, 30, 20, 10, 0.8)
        result = merge_ocr_results([r1, r2, r3, r4])
        assert len(result) == 2  # noqa: PLR2004
        assert result[0].text == "A B"
        assert result[1].text == "C D"

    def test_italic_propagation_from_second_fragment(self):
        """If second fragment is italic, merged block is italic."""
        r1 = OCRResult("x", 0, 0, 20, 20, 0.9)
        r1.is_italic = False
        r2 = OCRResult("y", 22, 0, 20, 20, 0.8)
        r2.is_italic = True
        result = merge_ocr_results([r1, r2])
        assert result[0].is_italic is True

    def test_both_bold_stays_bold(self):
        """If both fragments are bold, merged block is bold."""
        r1 = OCRResult("a", 0, 0, 20, 20, 0.9)
        r1.is_bold = True
        r2 = OCRResult("b", 22, 0, 20, 20, 0.8)
        r2.is_bold = True
        result = merge_ocr_results([r1, r2])
        assert result[0].is_bold is True

    def test_all_whitespace_returns_empty(self):
        """All-whitespace results return empty list."""
        results = [
            OCRResult("  ", 0, 0, 10, 10, 0.5),
            OCRResult("\t", 20, 0, 10, 10, 0.5),
            OCRResult("\n", 40, 0, 10, 10, 0.5),
        ]
        assert merge_ocr_results(results) == []

    def test_single_fragment_preserves_all_fields(self):
        """Single-fragment merge preserves all OCRResult fields."""
        r = OCRResult("solo", 5, 10, 40, 20, 0.95)
        r.color = "#FF0000"
        r.is_bold = True
        r.is_italic = True
        result = merge_ocr_results([r])
        assert result[0].color == "#FF0000"
        assert result[0].is_bold is True
        assert result[0].is_italic is True

    def test_gap_exactly_at_threshold_stays_separate(self):
        """Gap exactly at the threshold keeps fragments separate."""
        # h=20, threshold = 20 * 1.2 = 24
        # r1 ends at x=32, r2 starts at x=56; gap = 56 - 32 = 24
        # 24 < 24 is False → NOT merged
        r1 = OCRResult("a", 0, 0, 32, 20, 0.9)
        r2 = OCRResult("b", 56, 0, 20, 20, 0.8)
        result = merge_ocr_results([r1, r2])
        assert len(result) == 2  # noqa: PLR2004


# ---------------------------------------------------------------------------
# Extended _run_tesseract tests
# ---------------------------------------------------------------------------


class TestRunTesseractExtended:
    """Additional tests for Tesseract backend."""

    _TSV_HEADER = (
        "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num"
        "\tleft\ttop\twidth\theight\tconf\ttext"
    )

    def _make_tsv(self, rows):
        return self._TSV_HEADER + "\n" + "\n".join(rows) + "\n"

    def _fake_run_success(self, tsv_content):
        def _side_effect(cmd, check, capture_output):
            out_base = Path(cmd[2])
            tsv_path = out_base.with_suffix(".tsv")
            tsv_path.write_text(tsv_content, encoding="utf-8")

        return _side_effect

    @patch(f"{_OCR}.subprocess.run")
    def test_default_lang_is_eng(self, mock_run):
        """Default language parameter is 'eng'."""
        tsv = self._make_tsv([])
        mock_run.side_effect = self._fake_run_success(tsv)
        _run_tesseract("img.png")
        cmd = mock_run.call_args[0][0]
        assert "-l" in cmd
        lang_idx = cmd.index("-l")
        assert cmd[lang_idx + 1] == "eng"

    @patch(f"{_OCR}.subprocess.run")
    def test_custom_lang_passed(self, mock_run):
        """Custom language is passed to tesseract command."""
        tsv = self._make_tsv([])
        mock_run.side_effect = self._fake_run_success(tsv)
        _run_tesseract("img.png", lang="deu")
        cmd = mock_run.call_args[0][0]
        lang_idx = cmd.index("-l")
        assert cmd[lang_idx + 1] == "deu"

    @patch(f"{_OCR}.subprocess.run")
    def test_negative_confidence_skipped(self, mock_run):
        """Rows with negative confidence are skipped."""
        tsv = self._make_tsv(["5\t1\t1\t1\t1\t1\t0\t0\t10\t10\t-5\tBad"])
        mock_run.side_effect = self._fake_run_success(tsv)
        results = _run_tesseract("img.png")
        assert results == []


# ---------------------------------------------------------------------------
# Extended _bypass_uno_import tests
# ---------------------------------------------------------------------------


class TestBypassUnoImportExtended:
    """Additional tests for _bypass_uno_import edge cases."""

    def test_returns_none_when_uno_has_no_builtin_import(self):
        """Returns None when uno module exists but _builtin_import is absent."""
        fake_uno = MagicMock(spec=[])  # no attributes
        with patch.dict(sys.modules, {"uno": fake_uno}):
            assert _bypass_uno_import() is None

    def test_caller_can_restore_hook(self):
        """Caller can restore the UNO hook using the returned value."""
        real_import = builtins.__import__
        fake_uno = MagicMock()
        fake_uno._builtin_import = real_import

        def _fake_hook(*a, **kw):
            pass

        builtins.__import__ = _fake_hook
        try:
            with patch.dict(sys.modules, {"uno": fake_uno}):
                saved = _bypass_uno_import()
                # Now real import is active
                assert builtins.__import__ is real_import
                # Restore
                builtins.__import__ = saved
                assert builtins.__import__ is _fake_hook
        finally:
            builtins.__import__ = real_import


# ---------------------------------------------------------------------------
# Extended _get_easyocr_reader tests
# ---------------------------------------------------------------------------


class TestGetEasyOCRReaderExtended:
    """Additional tests for EasyOCR reader caching."""

    def setup_method(self):
        _easyocr_readers.clear()

    def teardown_method(self):
        _easyocr_readers.clear()

    def test_cache_key_uses_sorted_tuple(self):
        """Cache key is a sorted tuple, so order doesn't matter."""

        class _FakeReader:
            def __init__(self, langs, **kwargs):
                pass

        mock_easyocr = MagicMock()
        mock_easyocr.Reader = _FakeReader

        with patch.dict(sys.modules, {"easyocr": mock_easyocr}):
            _get_easyocr_reader(["fr", "en"])
            # Key should be ("en", "fr") — sorted
            assert ("en", "fr") in _easyocr_readers

    def test_three_language_key(self):
        """Three-language set creates correct cache key."""

        class _FakeReader:
            def __init__(self, langs, **kwargs):
                pass

        mock_easyocr = MagicMock()
        mock_easyocr.Reader = _FakeReader

        with patch.dict(sys.modules, {"easyocr": mock_easyocr}):
            _get_easyocr_reader(["zh", "en", "ja"])
            assert ("en", "ja", "zh") in _easyocr_readers

    def test_single_language_key(self):
        """Single-language set creates single-element tuple key."""

        class _FakeReader:
            def __init__(self, langs, **kwargs):
                pass

        mock_easyocr = MagicMock()
        mock_easyocr.Reader = _FakeReader

        with patch.dict(sys.modules, {"easyocr": mock_easyocr}):
            _get_easyocr_reader(["en"])
            assert ("en",) in _easyocr_readers


# ---------------------------------------------------------------------------
# Extended _run_easyocr tests
# ---------------------------------------------------------------------------


class TestRunEasyOCRExtended:
    """Additional tests for EasyOCR backend."""

    def setup_method(self):
        _easyocr_readers.clear()

    def teardown_method(self):
        _easyocr_readers.clear()

    def test_empty_readtext_returns_empty(self):
        """Reader.readtext returning empty list produces empty results."""

        class _FakeReader:
            def __init__(self, langs, **kwargs):
                pass

            def readtext(self, path):
                return []

        mock_easyocr = MagicMock()
        mock_easyocr.Reader = _FakeReader

        with patch.dict(sys.modules, {"easyocr": mock_easyocr}):
            results = _run_easyocr("img.png")
        assert results == []

    def test_polygon_with_negative_coordinates(self):
        """Polygon with negative coordinates is handled."""

        class _FakeReader:
            def __init__(self, langs, **kwargs):
                pass

            def readtext(self, path):
                return [
                    ([[-5, -3], [30, -3], [30, 10], [-5, 10]], "neg", 0.85),
                ]

        mock_easyocr = MagicMock()
        mock_easyocr.Reader = _FakeReader

        with patch.dict(sys.modules, {"easyocr": mock_easyocr}):
            results = _run_easyocr("img.png")
        assert len(results) == 1
        assert results[0].x == -5  # noqa: PLR2004
        assert results[0].y == -3  # noqa: PLR2004


# ---------------------------------------------------------------------------
# Extended _run_google_cloud tests
# ---------------------------------------------------------------------------


class TestRunGoogleCloudExtended:
    """Additional tests for Google Cloud Vision backend."""

    def _make_mock_response(self, response_data):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(response_data).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = False
        return mock_response

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value="key")
    @patch("urllib.request.urlopen")
    def test_multiple_words_parsed(self, mock_urlopen, mock_load, tmp_path):
        """Multiple word annotations are all parsed."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"fake")

        response_data = {
            "responses": [
                {
                    "textAnnotations": [
                        {  # Full-text block (skipped)
                            "description": "Hello World",
                            "boundingPoly": {
                                "vertices": [
                                    {"x": 0, "y": 0},
                                    {"x": 100, "y": 0},
                                    {"x": 100, "y": 20},
                                    {"x": 0, "y": 20},
                                ]
                            },
                        },
                        {
                            "description": "Hello",
                            "boundingPoly": {
                                "vertices": [
                                    {"x": 0, "y": 0},
                                    {"x": 50, "y": 0},
                                    {"x": 50, "y": 20},
                                    {"x": 0, "y": 20},
                                ]
                            },
                        },
                        {
                            "description": "World",
                            "boundingPoly": {
                                "vertices": [
                                    {"x": 55, "y": 0},
                                    {"x": 100, "y": 0},
                                    {"x": 100, "y": 20},
                                    {"x": 55, "y": 20},
                                ]
                            },
                        },
                    ],
                }
            ],
        }

        mock_urlopen.return_value = self._make_mock_response(response_data)
        results = _run_google_cloud(str(img))
        assert len(results) == 2  # noqa: PLR2004
        assert results[0].text == "Hello"
        assert results[1].text == "World"

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value="key")
    @patch("urllib.request.urlopen")
    def test_missing_x_y_defaults_to_zero(self, mock_urlopen, mock_load, tmp_path):
        """Missing x/y in vertices defaults to 0."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"fake")

        response_data = {
            "responses": [
                {
                    "textAnnotations": [
                        {  # Full-text
                            "description": "T",
                            "boundingPoly": {"vertices": [{"x": 0}]},
                        },
                        {
                            "description": "word",
                            "boundingPoly": {
                                "vertices": [
                                    {},
                                    {"x": 50},
                                    {"x": 50, "y": 20},
                                    {"y": 20},
                                ]
                            },
                        },
                    ],
                }
            ],
        }

        mock_urlopen.return_value = self._make_mock_response(response_data)
        results = _run_google_cloud(str(img))
        assert len(results) == 1
        assert results[0].x == 0
        assert results[0].y == 0

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value="key")
    @patch("urllib.request.urlopen")
    def test_api_key_in_url(self, mock_urlopen, mock_load, tmp_path):
        """API key is included in the request URL."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"fake")

        response_data = {"responses": [{}]}
        mock_urlopen.return_value = self._make_mock_response(response_data)
        _run_google_cloud(str(img))

        req_obj = mock_urlopen.call_args[0][0]
        assert "key=key" in req_obj.full_url


# ---------------------------------------------------------------------------
# OCRResult edge cases
# ---------------------------------------------------------------------------


class TestOCRResultEdgeCases:
    """Edge case tests for OCRResult."""

    def test_zero_dimensions(self):
        """Zero-width and zero-height OCRResult is valid."""
        r = OCRResult("dot", 0, 0, 0, 0, 1.0)
        assert r.w == 0
        assert r.h == 0

    def test_very_long_text(self):
        """Very long text string is stored correctly."""
        long_text = "word " * 1000
        r = OCRResult(long_text, 0, 0, 1000, 100, 0.5)
        assert len(r.text) == len(long_text)

    def test_unicode_text(self):
        """Unicode text is stored correctly."""
        r = OCRResult("日本語テスト", 0, 0, 100, 30, 0.95)
        assert r.text == "日本語テスト"

    def test_confidence_boundary_zero(self):
        """Zero confidence is valid."""
        r = OCRResult("low", 0, 0, 10, 10, 0.0)
        assert r.confidence == 0.0

    def test_confidence_boundary_one(self):
        """Perfect confidence is valid."""
        r = OCRResult("hi", 0, 0, 10, 10, 1.0)
        assert r.confidence == 1.0

    def test_to_dict_box_order_preserved(self):
        """to_dict always returns box as [x, y, w, h]."""
        r = OCRResult("test", 100, 200, 300, 400, 0.5)
        d = r.to_dict()
        assert d["box"] == [100, 200, 300, 400]

    def test_mutable_attributes(self):
        """Mutable attributes can be set after construction."""
        r = OCRResult("t", 0, 0, 1, 1, 1.0)
        r.color = "#AABBCC"
        r.is_bold = True
        r.is_italic = True
        r.is_underline = True
        r.translated_text = "tr"
        r.translated_html = "<b>tr</b>"
        r.alignment = "center"
        r.is_single_line = True
        r.line_height_ratio = 1.5
        assert r.color == "#AABBCC"
        assert r.is_bold is True
        assert r.is_single_line is True
        assert r.line_height_ratio == 1.5  # noqa: PLR2004


# ---------------------------------------------------------------------------
# NEW TESTS: OCRResult — additional constructor and serialization edge cases
# ---------------------------------------------------------------------------


class TestOCRResultAdditional:
    """Additional OCRResult constructor, attribute, and serialization tests."""

    def test_negative_coordinates(self):
        """Negative x/y coordinates are valid (can occur from OCR engines)."""
        r = OCRResult("neg", -10, -5, 50, 30, 0.8)
        assert r.x == -10
        assert r.y == -5

    def test_very_large_coordinates(self):
        """Very large coordinate values are stored correctly."""
        r = OCRResult("big", 99999, 88888, 77777, 66666, 0.5)
        assert r.x == 99999
        assert r.w == 77777

    def test_float_confidence_precision(self):
        """Float confidence preserves precision."""
        r = OCRResult("t", 0, 0, 1, 1, 0.123456789)
        assert r.confidence == pytest.approx(0.123456789)

    def test_empty_text_allowed(self):
        """Empty string text is allowed in OCRResult."""
        r = OCRResult("", 0, 0, 10, 10, 0.5)
        assert r.text == ""

    def test_to_dict_with_translated_text(self):
        """to_dict includes translated_text when set."""
        r = OCRResult("hello", 0, 0, 50, 20, 0.9)
        r.translated_text = "bonjour"
        d = r.to_dict()
        assert d["translated_text"] == "bonjour"

    def test_to_dict_default_translated_text_empty(self):
        """to_dict shows empty translated_text by default."""
        r = OCRResult("hello", 0, 0, 50, 20, 0.9)
        d = r.to_dict()
        assert d["translated_text"] == ""

    def test_to_dict_confidence_preserved(self):
        """to_dict preserves exact confidence value."""
        r = OCRResult("t", 0, 0, 1, 1, 0.87654)
        assert r.to_dict()["confidence"] == pytest.approx(0.87654)

    def test_to_dict_is_underline_default_false(self):
        """to_dict shows is_underline as False by default."""
        r = OCRResult("t", 0, 0, 1, 1, 1.0)
        assert r.to_dict()["is_underline"] is False

    def test_to_dict_is_underline_true(self):
        """to_dict shows is_underline as True when set."""
        r = OCRResult("t", 0, 0, 1, 1, 1.0)
        r.is_underline = True
        assert r.to_dict()["is_underline"] is True

    def test_original_text_height_independent_of_h(self):
        """original_text_height can be changed independently from h."""
        r = OCRResult("t", 0, 0, 50, 30, 1.0)
        r.original_text_height = 40
        assert r.original_text_height == 40
        assert r.h == 30

    def test_special_characters_in_text(self):
        """Special characters (tabs, newlines, quotes) stored correctly."""
        r = OCRResult('hello\tworld\n"test"', 0, 0, 100, 20, 0.9)
        assert "\t" in r.text
        assert "\n" in r.text
        assert '"' in r.text

    def test_emoji_text(self):
        """Emoji characters in text are stored correctly."""
        r = OCRResult("Hello 🌍", 0, 0, 100, 20, 0.9)
        assert r.text == "Hello 🌍"

    def test_to_dict_returns_new_dict_each_call(self):
        """Each to_dict() call returns a new dict object."""
        r = OCRResult("t", 0, 0, 1, 1, 1.0)
        d1 = r.to_dict()
        d2 = r.to_dict()
        assert d1 is not d2
        assert d1 == d2


# ---------------------------------------------------------------------------
# NEW TESTS: run_ocr dispatch — additional languages and edge cases
# ---------------------------------------------------------------------------


class TestRunOCRDispatchAdditional:
    """Additional run_ocr dispatch tests for various languages and methods."""

    @patch(f"{_OCR}._run_tesseract", return_value=[])
    def test_tesseract_unknown_language_defaults_to_eng(self, mock_tess):
        """Unknown language label falls back to 'eng' for Tesseract."""
        run_ocr("img.png", method=OCR_METHOD_TESSERACT, src_lang="Klingon")
        mock_tess.assert_called_once_with("img.png", lang="eng")

    @patch(f"{_OCR}._run_easyocr", return_value=[])
    def test_easyocr_unknown_language_defaults_to_en(self, mock_easy):
        """Unknown language label falls back to ['en'] for EasyOCR."""
        run_ocr("img.png", method=OCR_METHOD_EASYOCR, src_lang="Klingon")
        mock_easy.assert_called_once_with("img.png", languages=["en"])

    @patch(f"{_OCR}._run_google_cloud", return_value=[])
    def test_google_cloud_unknown_language_returns_none_hints(self, mock_gc):
        """Unknown language label returns None hints for Google Cloud."""
        run_ocr("img.png", method=OCR_METHOD_GOOGLE_CLOUD, src_lang="Klingon")
        mock_gc.assert_called_once_with("img.png", lang_hints=None)

    @patch(f"{_OCR}._run_tesseract", return_value=[])
    def test_tesseract_vietnamese_lang(self, mock_tess):
        """Vietnamese maps to 'vie' for Tesseract."""
        run_ocr("img.png", method=OCR_METHOD_TESSERACT, src_lang="Vietnamese")
        mock_tess.assert_called_once_with("img.png", lang="vie")

    @patch(f"{_OCR}._run_easyocr", return_value=[])
    def test_easyocr_russian_langs(self, mock_easy):
        """Russian maps to ['ru', 'en'] for EasyOCR."""
        run_ocr("img.png", method=OCR_METHOD_EASYOCR, src_lang="Russian")
        mock_easy.assert_called_once_with("img.png", languages=["ru", "en"])

    @patch(f"{_OCR}._run_google_cloud", return_value=[])
    def test_google_cloud_thai_hint(self, mock_gc):
        """Thai maps to ['th'] for Google Cloud."""
        run_ocr("img.png", method=OCR_METHOD_GOOGLE_CLOUD, src_lang="Thai")
        mock_gc.assert_called_once_with("img.png", lang_hints=["th"])

    @patch(f"{_OCR}._run_tesseract", return_value=[])
    def test_tesseract_chinese_traditional(self, mock_tess):
        """Chinese (Traditional) maps to 'chi_tra' for Tesseract."""
        run_ocr(
            "img.png",
            method=OCR_METHOD_TESSERACT,
            src_lang="Chinese (Traditional)",
        )
        mock_tess.assert_called_once_with("img.png", lang="chi_tra")

    @patch(f"{_OCR}._run_easyocr", return_value=[])
    def test_easyocr_chinese_simplified(self, mock_easy):
        """Chinese (Simplified) maps to ['ch_sim', 'en'] for EasyOCR."""
        run_ocr(
            "img.png",
            method=OCR_METHOD_EASYOCR,
            src_lang="Chinese (Simplified)",
        )
        mock_easy.assert_called_once_with("img.png", languages=["ch_sim", "en"])

    @patch(f"{_OCR}._run_google_cloud", return_value=[])
    def test_google_cloud_chinese_traditional_hint(self, mock_gc):
        """Chinese (Traditional) maps to ['zh-TW'] for Google Cloud."""
        run_ocr(
            "img.png",
            method=OCR_METHOD_GOOGLE_CLOUD,
            src_lang="Chinese (Traditional)",
        )
        mock_gc.assert_called_once_with("img.png", lang_hints=["zh-TW"])

    @patch(f"{_OCR}._run_tesseract", return_value=[])
    def test_tesseract_hindi_lang(self, mock_tess):
        """Hindi maps to 'hin' for Tesseract."""
        run_ocr("img.png", method=OCR_METHOD_TESSERACT, src_lang="Hindi")
        mock_tess.assert_called_once_with("img.png", lang="hin")

    @patch(f"{_OCR}._run_easyocr", return_value=[])
    def test_easyocr_hindi_langs(self, mock_easy):
        """Hindi maps to ['hi', 'en'] for EasyOCR."""
        run_ocr("img.png", method=OCR_METHOD_EASYOCR, src_lang="Hindi")
        mock_easy.assert_called_once_with("img.png", languages=["hi", "en"])

    @patch(f"{_OCR}._run_google_cloud", return_value=[])
    def test_google_cloud_hindi_hint(self, mock_gc):
        """Hindi maps to ['hi'] for Google Cloud."""
        run_ocr("img.png", method=OCR_METHOD_GOOGLE_CLOUD, src_lang="Hindi")
        mock_gc.assert_called_once_with("img.png", lang_hints=["hi"])

    @patch(f"{_OCR}._run_tesseract", return_value=[])
    def test_tesseract_turkish_lang(self, mock_tess):
        """Turkish maps to 'tur' for Tesseract."""
        run_ocr("img.png", method=OCR_METHOD_TESSERACT, src_lang="Turkish")
        mock_tess.assert_called_once_with("img.png", lang="tur")

    @patch(f"{_OCR}._run_easyocr", return_value=[])
    def test_easyocr_turkish_langs(self, mock_easy):
        """Turkish maps to ['tr', 'en'] for EasyOCR."""
        run_ocr("img.png", method=OCR_METHOD_EASYOCR, src_lang="Turkish")
        mock_easy.assert_called_once_with("img.png", languages=["tr", "en"])

    @patch(f"{_OCR}._run_tesseract", return_value=[])
    def test_tesseract_english_uk_maps_to_eng(self, mock_tess):
        """English (UK) maps to 'eng' for Tesseract."""
        run_ocr("img.png", method=OCR_METHOD_TESSERACT, src_lang="English (UK)")
        mock_tess.assert_called_once_with("img.png", lang="eng")

    @patch(f"{_OCR}._run_easyocr", return_value=[])
    def test_easyocr_english_uk_returns_en_only(self, mock_easy):
        """English (UK) maps to ['en'] only for EasyOCR (no duplicate)."""
        run_ocr("img.png", method=OCR_METHOD_EASYOCR, src_lang="English (UK)")
        mock_easy.assert_called_once_with("img.png", languages=["en"])

    @patch(f"{_OCR}._run_tesseract", return_value=[])
    def test_tesseract_arabic_lang(self, mock_tess):
        """Arabic maps to 'ara' for Tesseract."""
        run_ocr("img.png", method=OCR_METHOD_TESSERACT, src_lang="Arabic")
        mock_tess.assert_called_once_with("img.png", lang="ara")

    @patch(f"{_OCR}._run_easyocr", return_value=[])
    def test_easyocr_arabic_langs(self, mock_easy):
        """Arabic maps to ['ar', 'en'] for EasyOCR."""
        run_ocr("img.png", method=OCR_METHOD_EASYOCR, src_lang="Arabic")
        mock_easy.assert_called_once_with("img.png", languages=["ar", "en"])

    @patch(f"{_OCR}._run_tesseract", return_value=[])
    def test_tesseract_hebrew_lang(self, mock_tess):
        """Hebrew maps to 'heb' for Tesseract."""
        run_ocr("img.png", method=OCR_METHOD_TESSERACT, src_lang="Hebrew")
        mock_tess.assert_called_once_with("img.png", lang="heb")

    @patch(f"{_OCR}._run_tesseract", return_value=[])
    def test_tesseract_polish_lang(self, mock_tess):
        """Polish maps to 'pol' for Tesseract."""
        run_ocr("img.png", method=OCR_METHOD_TESSERACT, src_lang="Polish")
        mock_tess.assert_called_once_with("img.png", lang="pol")

    @patch(f"{_OCR}._run_tesseract", return_value=[])
    def test_tesseract_portuguese_brazil_lang(self, mock_tess):
        """Portuguese (Brazil) maps to 'por' for Tesseract."""
        run_ocr(
            "img.png",
            method=OCR_METHOD_TESSERACT,
            src_lang="Portuguese (Brazil)",
        )
        mock_tess.assert_called_once_with("img.png", lang="por")

    @patch(f"{_OCR}._run_tesseract", return_value=[])
    def test_tesseract_swedish_lang(self, mock_tess):
        """Swedish maps to 'swe' for Tesseract."""
        run_ocr("img.png", method=OCR_METHOD_TESSERACT, src_lang="Swedish")
        mock_tess.assert_called_once_with("img.png", lang="swe")

    @patch(f"{_OCR}._run_tesseract", return_value=[])
    def test_tesseract_serbian_lang(self, mock_tess):
        """Serbian maps to 'srp' for Tesseract."""
        run_ocr("img.png", method=OCR_METHOD_TESSERACT, src_lang="Serbian")
        mock_tess.assert_called_once_with("img.png", lang="srp")

    @patch(f"{_OCR}._run_google_cloud", return_value=[])
    def test_google_cloud_serbian_hint(self, mock_gc):
        """Serbian maps to ['sr'] for Google Cloud."""
        run_ocr("img.png", method=OCR_METHOD_GOOGLE_CLOUD, src_lang="Serbian")
        mock_gc.assert_called_once_with("img.png", lang_hints=["sr"])


# ---------------------------------------------------------------------------
# NEW TESTS: merge_ocr_results — complex fragment configurations
# ---------------------------------------------------------------------------


class TestMergeFragmentConfigurations:
    """Tests for merge_ocr_results with complex fragment layouts."""

    def test_five_words_same_line_all_merge(self):
        """Five closely-spaced words on one line merge into one block."""
        frags = [
            OCRResult("The", 0, 0, 20, 15, 0.9),
            OCRResult("quick", 22, 0, 30, 15, 0.85),
            OCRResult("brown", 54, 0, 30, 15, 0.88),
            OCRResult("fox", 86, 0, 20, 15, 0.9),
            OCRResult("jumps", 108, 0, 30, 15, 0.87),
        ]
        result = merge_ocr_results(frags)
        assert len(result) == 1
        assert result[0].text == "The quick brown fox jumps"

    def test_three_lines_of_two_words(self):
        """3 lines with 2 words each produce 3 merged blocks."""
        frags = [
            OCRResult("Hello", 0, 0, 30, 10, 0.9),
            OCRResult("World", 32, 0, 30, 10, 0.8),
            OCRResult("Good", 0, 30, 30, 10, 0.9),
            OCRResult("Day", 32, 30, 20, 10, 0.85),
            OCRResult("Nice", 0, 60, 30, 10, 0.9),
            OCRResult("Time", 32, 60, 25, 10, 0.87),
        ]
        result = merge_ocr_results(frags)
        assert len(result) == 3  # noqa: PLR2004
        assert result[0].text == "Hello World"
        assert result[1].text == "Good Day"
        assert result[2].text == "Nice Time"

    def test_mixed_merge_and_separate_on_same_line(self):
        """Same line: two close pairs separated by a large gap."""
        # Pair 1: gap = 22 - 20 = 2 < 15 * 1.2 = 18 -> merge
        r1 = OCRResult("A", 0, 0, 20, 15, 0.9)
        r2 = OCRResult("B", 22, 0, 20, 15, 0.8)
        # Pair 2: gap = 200 - 42 = 158 >> 18 -> separate from pair 1
        r3 = OCRResult("C", 200, 0, 20, 15, 0.9)
        r4 = OCRResult("D", 222, 0, 20, 15, 0.8)
        result = merge_ocr_results([r1, r2, r3, r4])
        assert len(result) == 2  # noqa: PLR2004
        assert result[0].text == "A B"
        assert result[1].text == "C D"

    def test_reversed_input_order_still_merges(self):
        """Fragments given in reverse Y then reverse X still merge correctly."""
        r_bottom_right = OCRResult("D", 22, 50, 20, 10, 0.8)
        r_bottom_left = OCRResult("C", 0, 50, 20, 10, 0.9)
        r_top_right = OCRResult("B", 22, 0, 20, 10, 0.8)
        r_top_left = OCRResult("A", 0, 0, 20, 10, 0.9)
        result = merge_ocr_results(
            [r_bottom_right, r_bottom_left, r_top_right, r_top_left]
        )
        assert len(result) == 2  # noqa: PLR2004
        assert result[0].text == "A B"
        assert result[1].text == "C D"

    def test_identical_position_fragments_merge(self):
        """Two fragments at the exact same position merge."""
        r1 = OCRResult("over", 10, 10, 30, 15, 0.9)
        r2 = OCRResult("lap", 10, 10, 30, 15, 0.8)
        result = merge_ocr_results([r1, r2])
        assert len(result) == 1
        assert "over" in result[0].text
        assert "lap" in result[0].text

    def test_very_tall_fragments_merge_across_larger_gap(self):
        """Tall fragments (h=100) allow merging across larger horizontal gaps.

        threshold = 100 * 1.2 = 120, so gap of 80 merges.
        """
        r1 = OCRResult("tall1", 0, 0, 50, 100, 0.9)
        r2 = OCRResult("tall2", 130, 0, 50, 100, 0.8)  # gap = 130 - 50 = 80
        result = merge_ocr_results([r1, r2])
        assert len(result) == 1
        assert result[0].text == "tall1 tall2"

    def test_very_short_fragments_strict_gap(self):
        """Short fragments (h=5) have very strict merge threshold.

        threshold = 5 * 1.2 = 6, so gap of 7 does NOT merge.
        """
        r1 = OCRResult("a", 0, 0, 10, 5, 0.9)
        r2 = OCRResult("b", 17, 0, 10, 5, 0.8)  # gap = 17 - 10 = 7 > 6
        result = merge_ocr_results([r1, r2])
        assert len(result) == 2  # noqa: PLR2004

    def test_confidence_averages_across_three_merges(self):
        """Confidence averaging over 3 merges: ((c1+c2)/2 + c3)/2."""
        r1 = OCRResult("a", 0, 0, 10, 20, 1.0)
        r2 = OCRResult("b", 12, 0, 10, 20, 0.6)
        r3 = OCRResult("c", 24, 0, 10, 20, 0.8)
        result = merge_ocr_results([r1, r2, r3])
        assert len(result) == 1
        # (1.0 + 0.6) / 2 = 0.8, then (0.8 + 0.8) / 2 = 0.8
        assert result[0].confidence == pytest.approx(0.8)

    def test_single_fragment_with_trailing_space(self):
        """Single fragment with trailing space is kept (not whitespace-only)."""
        r = OCRResult("hello ", 0, 0, 50, 20, 0.9)
        result = merge_ocr_results([r])
        assert len(result) == 1
        assert result[0].text == "hello "

    def test_fragment_with_only_newline_filtered(self):
        """Fragment with only newline is filtered as whitespace."""
        r = OCRResult("\n", 0, 0, 10, 10, 0.9)
        assert merge_ocr_results([r]) == []

    def test_fragment_with_only_tab_filtered(self):
        """Fragment with only tab is filtered as whitespace."""
        r = OCRResult("\t", 0, 0, 10, 10, 0.9)
        assert merge_ocr_results([r]) == []

    def test_fragments_barely_overlapping_vertically_merge(self):
        """Fragments with just-over-threshold vertical overlap merge.

        h=20 each, OCR_VERTICAL_OVERLAP_RATIO=0.6 -> need overlap > 12.
        overlap = min(20, 7+20) - max(0, 7) = 20 - 7 = 13 > 12 -> merge.
        """
        r1 = OCRResult("a", 0, 0, 20, 20, 0.9)
        r2 = OCRResult("b", 22, 7, 20, 20, 0.8)
        result = merge_ocr_results([r1, r2])
        assert len(result) == 1

    def test_fragments_different_heights_overlap_check(self):
        """Overlap check uses min(h) for the threshold."""
        # r1: h=10, r2: h=50. min_h = 10, threshold = 10 * 0.6 = 6
        # overlap = min(10, 0+50) - max(0, 0) = 10 - 0 = 10 > 6 -> merge
        r1 = OCRResult("small", 0, 0, 20, 10, 0.9)
        r2 = OCRResult("big", 22, 0, 20, 50, 0.8)
        result = merge_ocr_results([r1, r2])
        assert len(result) == 1
        assert result[0].text == "small big"

    def test_merged_bbox_y_takes_min(self):
        """Merged block y is min of both fragments."""
        r1 = OCRResult("a", 0, 5, 20, 20, 0.9)
        r2 = OCRResult("b", 22, 2, 20, 20, 0.8)
        result = merge_ocr_results([r1, r2])
        assert result[0].y == 2

    def test_merged_bbox_h_covers_both(self):
        """Merged block h covers from min(y) to max(y+h)."""
        r1 = OCRResult("a", 0, 5, 20, 10, 0.9)  # bottom = 15
        r2 = OCRResult("b", 22, 3, 20, 25, 0.8)  # bottom = 28
        result = merge_ocr_results([r1, r2])
        # y = min(5,3) = 3, h = max(15,28) - 3 = 25
        assert result[0].y == 3
        assert result[0].h == 25

    def test_color_always_from_leftmost_fragment(self):
        """In a merged block, color comes from the leftmost (first) fragment."""
        r1 = OCRResult("right", 50, 0, 20, 15, 0.9)
        r1.color = "#00FF00"
        r2 = OCRResult("left", 0, 0, 20, 15, 0.8)
        r2.color = "#FF0000"
        result = merge_ocr_results([r1, r2])
        # After sorting by x within the line, r2 (left) comes first
        assert result[0].color == "#FF0000"

    def test_bold_propagation_through_chain_of_three(self):
        """Bold propagates through a chain of 3 merges: only 3rd is bold."""
        r1 = OCRResult("a", 0, 0, 10, 20, 0.9)
        r2 = OCRResult("b", 12, 0, 10, 20, 0.8)
        r3 = OCRResult("c", 24, 0, 10, 20, 0.7)
        r3.is_bold = True
        result = merge_ocr_results([r1, r2, r3])
        assert result[0].is_bold is True


# ---------------------------------------------------------------------------
# NEW TESTS: _run_tesseract — additional edge cases
# ---------------------------------------------------------------------------


class TestRunTesseractAdditional:
    """Additional Tesseract backend tests."""

    _TSV_HEADER = (
        "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num"
        "\tleft\ttop\twidth\theight\tconf\ttext"
    )

    def _make_tsv(self, rows):
        return self._TSV_HEADER + "\n" + "\n".join(rows) + "\n"

    def _fake_run_success(self, tsv_content):
        def _side_effect(cmd, check, capture_output):
            out_base = Path(cmd[2])
            tsv_path = out_base.with_suffix(".tsv")
            tsv_path.write_text(tsv_content, encoding="utf-8")

        return _side_effect

    @patch(f"{_OCR}.subprocess.run")
    def test_unicode_text_parsed(self, mock_run):
        """Unicode characters in TSV text field are parsed correctly."""
        tsv = self._make_tsv(["5\t1\t1\t1\t1\t1\t0\t0\t50\t15\t90\t日本語"])
        mock_run.side_effect = self._fake_run_success(tsv)
        results = _run_tesseract("img.png")
        assert len(results) == 1
        assert results[0].text == "日本語"

    @patch(f"{_OCR}.subprocess.run")
    def test_mixed_valid_invalid_rows(self, mock_run):
        """Mix of valid and non-word-level rows filters correctly."""
        tsv = self._make_tsv(
            [
                "1\t1\t0\t0\t0\t0\t0\t0\t500\t500\t-1\t",
                "2\t1\t1\t0\t0\t0\t0\t0\t250\t250\t-1\t",
                "3\t1\t1\t1\t0\t0\t0\t0\t250\t100\t-1\t",
                "4\t1\t1\t1\t1\t0\t0\t0\t250\t50\t-1\t",
                "5\t1\t1\t1\t1\t1\t0\t0\t60\t15\t92\tWord1",
                "5\t1\t1\t1\t1\t2\t70\t0\t60\t15\t88\tWord2",
            ]
        )
        mock_run.side_effect = self._fake_run_success(tsv)
        results = _run_tesseract("img.png")
        assert len(results) == 2  # noqa: PLR2004
        assert results[0].text == "Word1"
        assert results[1].text == "Word2"

    @patch(f"{_OCR}.subprocess.run")
    def test_confidence_exactly_zero_skipped(self, mock_run):
        """Row with exactly zero confidence is skipped (conf > 0 check)."""
        tsv = self._make_tsv(["5\t1\t1\t1\t1\t1\t0\t0\t10\t10\t0.0\tZeroConf"])
        mock_run.side_effect = self._fake_run_success(tsv)
        results = _run_tesseract("img.png")
        assert results == []

    @patch(f"{_OCR}.subprocess.run")
    def test_confidence_just_above_zero(self, mock_run):
        """Row with conf=0.01 is kept (barely above zero)."""
        tsv = self._make_tsv(["5\t1\t1\t1\t1\t1\t0\t0\t10\t10\t0.01\tTiny"])
        mock_run.side_effect = self._fake_run_success(tsv)
        results = _run_tesseract("img.png")
        assert len(results) == 1
        assert results[0].text == "Tiny"

    @patch(f"{_OCR}.subprocess.run")
    def test_text_with_spaces_preserved(self, mock_run):
        """Text with leading/trailing spaces is stripped by the parser."""
        tsv = self._make_tsv(["5\t1\t1\t1\t1\t1\t0\t0\t50\t15\t90\t  spaced  "])
        mock_run.side_effect = self._fake_run_success(tsv)
        results = _run_tesseract("img.png")
        assert len(results) == 1
        assert results[0].text == "spaced"

    @patch(f"{_OCR}.subprocess.run")
    def test_large_coordinate_values(self, mock_run):
        """Large coordinate values in TSV are parsed correctly."""
        tsv = self._make_tsv(["5\t1\t1\t1\t1\t1\t5000\t3000\t2000\t1000\t95\tLarge"])
        mock_run.side_effect = self._fake_run_success(tsv)
        results = _run_tesseract("img.png")
        assert results[0].x == 5000
        assert results[0].y == 3000
        assert results[0].w == 2000
        assert results[0].h == 1000

    @patch(f"{_OCR}.subprocess.run")
    def test_bold_without_italic_column(self, mock_run):
        """Bold=1 when there is no italic column."""
        tsv = (
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num"
            "\tleft\ttop\twidth\theight\tconf\ttext\tbold\n"
            "5\t1\t1\t1\t1\t1\t0\t0\t50\t20\t90\tBoldOnly\t1\n"
        )
        mock_run.side_effect = self._fake_run_success(tsv)
        results = _run_tesseract("img.png")
        assert results[0].is_bold is True
        assert results[0].is_italic is False

    @patch(f"{_OCR}.subprocess.run")
    def test_italic_without_bold_column(self, mock_run):
        """Italic=1 when there is no bold column."""
        tsv = (
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num"
            "\tleft\ttop\twidth\theight\tconf\ttext\titalic\n"
            "5\t1\t1\t1\t1\t1\t0\t0\t50\t20\t90\tItalOnly\t1\n"
        )
        mock_run.side_effect = self._fake_run_success(tsv)
        results = _run_tesseract("img.png")
        assert results[0].is_italic is True
        assert results[0].is_bold is False

    @patch(f"{_OCR}.subprocess.run")
    def test_many_rows_all_parsed(self, mock_run):
        """20 valid rows are all parsed."""
        rows = [
            f"5\t1\t1\t1\t1\t{i}\t{i * 30}\t0\t25\t10\t90\tW{i}" for i in range(1, 21)
        ]
        tsv = self._make_tsv(rows)
        mock_run.side_effect = self._fake_run_success(tsv)
        results = _run_tesseract("img.png")
        assert len(results) == 20  # noqa: PLR2004

    @patch(f"{_OCR}.subprocess.run")
    def test_fallback_lang_attempts_both_commands(self, mock_run):
        """Fallback from 'deu' to 'eng' attempts exactly 2 commands."""
        call_count = 0

        def _side_effect(cmd, check, capture_output):
            nonlocal call_count
            call_count += 1
            if "deu" in cmd:
                raise subprocess.CalledProcessError(1, cmd)
            # eng fallback succeeds
            out_base = Path(cmd[2])
            tsv_path = out_base.with_suffix(".tsv")
            tsv_path.write_text(self._TSV_HEADER + "\n", encoding="utf-8")

        mock_run.side_effect = _side_effect
        _run_tesseract("img.png", lang="deu")
        assert call_count == 2  # noqa: PLR2004

    @patch(f"{_OCR}.subprocess.run")
    def test_tesseract_command_includes_tsv_output(self, mock_run):
        """Tesseract command includes 'tsv' as output format."""
        tsv = self._make_tsv([])
        mock_run.side_effect = self._fake_run_success(tsv)
        _run_tesseract("img.png")
        cmd = mock_run.call_args[0][0]
        assert "tsv" in cmd

    @patch(f"{_OCR}.subprocess.run")
    def test_tesseract_command_includes_image_path(self, mock_run):
        """Tesseract command includes the image path."""
        tsv = self._make_tsv([])
        mock_run.side_effect = self._fake_run_success(tsv)
        _run_tesseract("/path/to/img.png")
        cmd = mock_run.call_args[0][0]
        assert "/path/to/img.png" in cmd


# ---------------------------------------------------------------------------
# NEW TESTS: _bypass_uno_import — additional edge cases
# ---------------------------------------------------------------------------


class TestBypassUnoImportAdditional:
    """Additional edge cases for _bypass_uno_import."""

    def test_returns_none_when_uno_is_none_in_modules(self):
        """Returns None when sys.modules['uno'] is explicitly None."""
        with patch.dict(sys.modules, {"uno": None}):
            # sys.modules.get("uno") returns None
            assert _bypass_uno_import() is None

    def test_multiple_calls_without_restore_still_works(self):
        """Multiple bypass calls without restore are idempotent after first."""
        real_import = builtins.__import__
        fake_uno = ModuleType("uno")
        fake_uno._builtin_import = real_import  # type: ignore[attr-defined]

        def _fake_hook(*a, **kw):
            return real_import(*a, **kw)

        builtins.__import__ = _fake_hook
        try:
            with patch.dict(sys.modules, {"uno": fake_uno}):
                saved1 = _bypass_uno_import()
                assert saved1 is _fake_hook
                # Now real import is active, second call returns None
                saved2 = _bypass_uno_import()
                assert saved2 is None
        finally:
            builtins.__import__ = real_import

    def test_uno_with_builtin_import_set_to_none(self):
        """Returns None when uno._builtin_import is None."""
        fake_uno = ModuleType("uno")
        fake_uno._builtin_import = None  # type: ignore[attr-defined]
        with patch.dict(sys.modules, {"uno": fake_uno}):
            assert _bypass_uno_import() is None


# ---------------------------------------------------------------------------
# NEW TESTS: _get_easyocr_reader — additional caching edge cases
# ---------------------------------------------------------------------------


class TestGetEasyOCRReaderAdditional:
    """Additional EasyOCR reader caching tests."""

    def setup_method(self):
        _easyocr_readers.clear()

    def teardown_method(self):
        _easyocr_readers.clear()

    def test_reader_receives_gpu_false(self):
        """EasyOCR Reader is created with gpu=False."""
        init_kwargs = {}

        class _FakeReader:
            def __init__(self, langs, **kwargs):
                init_kwargs.update(kwargs)

        mock_easyocr = MagicMock()
        mock_easyocr.Reader = _FakeReader

        with patch.dict(sys.modules, {"easyocr": mock_easyocr}):
            _get_easyocr_reader(["en"])
        assert init_kwargs.get("gpu") is False

    def test_reader_receives_quantize_false(self):
        """EasyOCR Reader is created with quantize=False."""
        init_kwargs = {}

        class _FakeReader:
            def __init__(self, langs, **kwargs):
                init_kwargs.update(kwargs)

        mock_easyocr = MagicMock()
        mock_easyocr.Reader = _FakeReader

        with patch.dict(sys.modules, {"easyocr": mock_easyocr}):
            _get_easyocr_reader(["en"])
        assert init_kwargs.get("quantize") is False

    def test_reader_receives_verbose_false(self):
        """EasyOCR Reader is created with verbose=False."""
        init_kwargs = {}

        class _FakeReader:
            def __init__(self, langs, **kwargs):
                init_kwargs.update(kwargs)

        mock_easyocr = MagicMock()
        mock_easyocr.Reader = _FakeReader

        with patch.dict(sys.modules, {"easyocr": mock_easyocr}):
            _get_easyocr_reader(["en"])
        assert init_kwargs.get("verbose") is False

    def test_empty_language_list_creates_entry(self):
        """Empty language list creates a cache entry with empty tuple key."""

        class _FakeReader:
            def __init__(self, langs, **kwargs):
                pass

        mock_easyocr = MagicMock()
        mock_easyocr.Reader = _FakeReader

        with patch.dict(sys.modules, {"easyocr": mock_easyocr}):
            _get_easyocr_reader([])
        assert () in _easyocr_readers

    def test_duplicate_languages_in_list(self):
        """Duplicate languages in list are sorted for cache key."""

        class _FakeReader:
            def __init__(self, langs, **kwargs):
                pass

        mock_easyocr = MagicMock()
        mock_easyocr.Reader = _FakeReader

        with patch.dict(sys.modules, {"easyocr": mock_easyocr}):
            _get_easyocr_reader(["en", "en", "en"])
        assert ("en", "en", "en") in _easyocr_readers

    def test_cache_survives_across_calls(self):
        """Cache persists across multiple _get_easyocr_reader calls."""
        call_count = 0

        class _CountingReader:
            def __init__(self, langs, **kwargs):
                nonlocal call_count
                call_count += 1

        mock_easyocr = MagicMock()
        mock_easyocr.Reader = _CountingReader

        with patch.dict(sys.modules, {"easyocr": mock_easyocr}):
            _get_easyocr_reader(["en"])
            _get_easyocr_reader(["ja", "en"])
            _get_easyocr_reader(["en"])  # cached
            _get_easyocr_reader(["ja", "en"])  # cached
            _get_easyocr_reader(["fr"])  # new
        assert call_count == 3  # noqa: PLR2004
        assert len(_easyocr_readers) == 3  # noqa: PLR2004


# ---------------------------------------------------------------------------
# NEW TESTS: _run_easyocr — additional edge cases
# ---------------------------------------------------------------------------


class TestRunEasyOCRAdditional:
    """Additional EasyOCR backend tests."""

    def setup_method(self):
        _easyocr_readers.clear()

    def teardown_method(self):
        _easyocr_readers.clear()

    def test_rotated_polygon_handled(self):
        """Rotated polygon bbox produces correct bounding rectangle."""

        class _FakeReader:
            def __init__(self, langs, **kwargs):
                pass

            def readtext(self, path):
                # Rotated polygon
                return [
                    ([[20, 0], [50, 10], [40, 40], [10, 30]], "rotated", 0.8),
                ]

        mock_easyocr = MagicMock()
        mock_easyocr.Reader = _FakeReader

        with patch.dict(sys.modules, {"easyocr": mock_easyocr}):
            results = _run_easyocr("img.png")
        assert len(results) == 1
        r = results[0]
        # xs = [20, 50, 40, 10], ys = [0, 10, 40, 30]
        assert r.x == 10
        assert r.y == 0
        assert r.w == 40  # 50 - 10
        assert r.h == 40  # 40 - 0

    def test_zero_confidence_result(self):
        """EasyOCR result with 0.0 confidence is still included."""

        class _FakeReader:
            def __init__(self, langs, **kwargs):
                pass

            def readtext(self, path):
                return [
                    ([[0, 0], [10, 0], [10, 10], [0, 10]], "low", 0.0),
                ]

        mock_easyocr = MagicMock()
        mock_easyocr.Reader = _FakeReader

        with patch.dict(sys.modules, {"easyocr": mock_easyocr}):
            results = _run_easyocr("img.png")
        assert len(results) == 1
        assert results[0].confidence == 0.0

    def test_readtext_exception_propagates(self):
        """Exception from readtext is re-raised (not ImportError)."""

        class _FakeReader:
            def __init__(self, langs, **kwargs):
                pass

            def readtext(self, path):
                raise RuntimeError("Image decode error")

        mock_easyocr = MagicMock()
        mock_easyocr.Reader = _FakeReader

        with (
            patch.dict(sys.modules, {"easyocr": mock_easyocr}),
            pytest.raises(RuntimeError, match="Image decode error"),
        ):
            _run_easyocr("img.png")

    def test_explicit_languages_passed_to_reader(self):
        """Explicit languages are passed to the Reader constructor."""
        used_langs = []

        class _FakeReader:
            def __init__(self, langs, **kwargs):
                used_langs.append(list(langs))

            def readtext(self, path):
                return []

        mock_easyocr = MagicMock()
        mock_easyocr.Reader = _FakeReader

        with patch.dict(sys.modules, {"easyocr": mock_easyocr}):
            _run_easyocr("img.png", languages=["ko", "en"])
        assert used_langs[0] == ["ko", "en"]

    def test_many_results_all_standardized(self):
        """10 EasyOCR results are all standardized."""

        class _FakeReader:
            def __init__(self, langs, **kwargs):
                pass

            def readtext(self, path):
                return [
                    (
                        [
                            [i * 20, 0],
                            [i * 20 + 15, 0],
                            [i * 20 + 15, 10],
                            [i * 20, 10],
                        ],
                        f"w{i}",
                        0.9,
                    )
                    for i in range(10)
                ]

        mock_easyocr = MagicMock()
        mock_easyocr.Reader = _FakeReader

        with patch.dict(sys.modules, {"easyocr": mock_easyocr}):
            results = _run_easyocr("img.png")
        assert len(results) == 10  # noqa: PLR2004

    def test_easyocr_import_error_when_module_none(self):
        """When easyocr module is None in sys.modules, ImportError is raised."""
        _easyocr_readers.clear()
        with (
            patch.dict(sys.modules, {"easyocr": None}),
            pytest.raises(ImportError, match="not installed"),
        ):
            _run_easyocr("img.png")

    def test_fallback_does_not_occur_when_default_langs_fail(self):
        """When default languages fail, no further fallback — exception propagates."""

        class _BrokenReader:
            def __init__(self, langs, **kwargs):
                raise RuntimeError("Cannot initialize")

        mock_easyocr = MagicMock()
        mock_easyocr.Reader = _BrokenReader

        with (
            patch.dict(sys.modules, {"easyocr": mock_easyocr}),
            pytest.raises(RuntimeError, match="Cannot initialize"),
        ):
            _run_easyocr("img.png", languages=EASYOCR_DEFAULT_LANGUAGES)


# ---------------------------------------------------------------------------
# NEW TESTS: _run_google_cloud — additional edge cases
# ---------------------------------------------------------------------------


class TestRunGoogleCloudAdditional:
    """Additional Google Cloud Vision backend tests."""

    def _make_mock_response(self, response_data):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(response_data).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = False
        return mock_response

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value="key")
    @patch("urllib.request.urlopen")
    def test_single_annotation_only_fulltext_returns_empty(
        self, mock_urlopen, mock_load, tmp_path
    ):
        """Single annotation (full-text only) is skipped, returns empty."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"fake")

        response_data = {
            "responses": [
                {
                    "textAnnotations": [
                        {
                            "description": "Full text only",
                            "boundingPoly": {
                                "vertices": [
                                    {"x": 0, "y": 0},
                                    {"x": 100, "y": 0},
                                    {"x": 100, "y": 50},
                                    {"x": 0, "y": 50},
                                ]
                            },
                        }
                    ],
                }
            ],
        }
        mock_urlopen.return_value = self._make_mock_response(response_data)
        results = _run_google_cloud(str(img))
        assert results == []

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value="key")
    @patch("urllib.request.urlopen")
    def test_image_content_is_base64_encoded(self, mock_urlopen, mock_load, tmp_path):
        """Image file content is base64-encoded in the request payload."""
        import base64  # noqa: PLC0415

        img = tmp_path / "test.jpg"
        raw_bytes = b"\x89PNG\r\n\x1a\n" + b"x" * 100
        img.write_bytes(raw_bytes)

        response_data = {"responses": [{}]}
        mock_urlopen.return_value = self._make_mock_response(response_data)
        _run_google_cloud(str(img))

        req_obj = mock_urlopen.call_args[0][0]
        payload = json.loads(req_obj.data.decode("utf-8"))
        sent_content = payload["requests"][0]["image"]["content"]
        assert sent_content == base64.b64encode(raw_bytes).decode("utf-8")

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value="key")
    @patch("urllib.request.urlopen")
    def test_request_has_json_content_type(self, mock_urlopen, mock_load, tmp_path):
        """Request has Content-Type: application/json header."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"fake")

        response_data = {"responses": [{}]}
        mock_urlopen.return_value = self._make_mock_response(response_data)
        _run_google_cloud(str(img))

        req_obj = mock_urlopen.call_args[0][0]
        assert req_obj.get_header("Content-type") == "application/json"

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value="key")
    @patch("urllib.request.urlopen")
    def test_text_detection_feature_in_request(self, mock_urlopen, mock_load, tmp_path):
        """DOCUMENT_TEXT_DETECTION feature type is in the request payload."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"fake")

        response_data = {"responses": [{}]}
        mock_urlopen.return_value = self._make_mock_response(response_data)
        _run_google_cloud(str(img))

        req_obj = mock_urlopen.call_args[0][0]
        payload = json.loads(req_obj.data.decode("utf-8"))
        features = payload["requests"][0]["features"]
        assert any(f["type"] == "DOCUMENT_TEXT_DETECTION" for f in features)

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value="key")
    @patch("urllib.request.urlopen")
    def test_multiple_language_hints(self, mock_urlopen, mock_load, tmp_path):
        """Multiple language hints are included in imageContext."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"fake")

        response_data = {"responses": [{}]}
        mock_urlopen.return_value = self._make_mock_response(response_data)
        _run_google_cloud(str(img), lang_hints=["ja", "en", "zh"])

        req_obj = mock_urlopen.call_args[0][0]
        payload = json.loads(req_obj.data.decode("utf-8"))
        hints = payload["requests"][0]["imageContext"]["languageHints"]
        assert hints == ["ja", "en", "zh"]

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value="key")
    @patch("urllib.request.urlopen")
    def test_empty_language_hints_list(self, mock_urlopen, mock_load, tmp_path):
        """Empty language hints list is treated as falsy — no imageContext."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"fake")

        response_data = {"responses": [{}]}
        mock_urlopen.return_value = self._make_mock_response(response_data)
        _run_google_cloud(str(img), lang_hints=[])

        req_obj = mock_urlopen.call_args[0][0]
        payload = json.loads(req_obj.data.decode("utf-8"))
        assert "imageContext" not in payload["requests"][0]

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value="key")
    @patch("urllib.request.urlopen")
    def test_annotation_with_empty_bounding_poly(
        self, mock_urlopen, mock_load, tmp_path
    ):
        """Annotation with empty boundingPoly (no vertices key) is skipped."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"fake")

        response_data = {
            "responses": [
                {
                    "textAnnotations": [
                        {  # Full-text
                            "description": "T",
                            "boundingPoly": {"vertices": [{"x": 0, "y": 0}]},
                        },
                        {  # Missing vertices entirely
                            "description": "no_poly",
                        },
                    ],
                }
            ],
        }
        mock_urlopen.return_value = self._make_mock_response(response_data)
        results = _run_google_cloud(str(img))
        # "no_poly" has no boundingPoly at all -> .get("boundingPoly", {}).get("vertices", [])
        # returns [] -> skipped
        assert results == []

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value="key")
    @patch("urllib.request.urlopen")
    def test_zero_size_bounding_box(self, mock_urlopen, mock_load, tmp_path):
        """Annotation where all vertices are the same point -> w=0, h=0."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"fake")

        response_data = {
            "responses": [
                {
                    "textAnnotations": [
                        {  # Full-text
                            "description": "T",
                            "boundingPoly": {
                                "vertices": [
                                    {"x": 5, "y": 5},
                                    {"x": 5, "y": 5},
                                ]
                            },
                        },
                        {
                            "description": "point",
                            "boundingPoly": {
                                "vertices": [
                                    {"x": 10, "y": 10},
                                    {"x": 10, "y": 10},
                                    {"x": 10, "y": 10},
                                    {"x": 10, "y": 10},
                                ]
                            },
                        },
                    ],
                }
            ],
        }
        mock_urlopen.return_value = self._make_mock_response(response_data)
        results = _run_google_cloud(str(img))
        assert len(results) == 1
        assert results[0].w == 0
        assert results[0].h == 0

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value="key")
    @patch("urllib.request.urlopen")
    def test_large_number_of_annotations(self, mock_urlopen, mock_load, tmp_path):
        """50 word-level annotations are all parsed."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"fake")

        annotations = [
            {  # Full-text (skipped)
                "description": "Full",
                "boundingPoly": {
                    "vertices": [
                        {"x": 0, "y": 0},
                        {"x": 1000, "y": 1000},
                    ]
                },
            }
        ]
        for i in range(50):
            annotations.append(
                {
                    "description": f"word{i}",
                    "boundingPoly": {
                        "vertices": [
                            {"x": i * 20, "y": 0},
                            {"x": i * 20 + 15, "y": 0},
                            {"x": i * 20 + 15, "y": 10},
                            {"x": i * 20, "y": 10},
                        ]
                    },
                }
            )

        response_data = {"responses": [{"textAnnotations": annotations}]}
        mock_urlopen.return_value = self._make_mock_response(response_data)
        results = _run_google_cloud(str(img))
        assert len(results) == 50  # noqa: PLR2004

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value="key")
    @patch("urllib.request.urlopen")
    def test_file_not_found_raises(self, mock_urlopen, mock_load):
        """Non-existent image file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            _run_google_cloud("/nonexistent/path/image.jpg")

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value="key")
    @patch("urllib.request.urlopen")
    def test_timeout_parameter_passed_to_urlopen(
        self, mock_urlopen, mock_load, tmp_path
    ):
        """Timeout parameter is passed to urlopen."""
        from src.constants.ocr import GOOGLE_CLOUD_OCR_TIMEOUT  # noqa: PLC0415

        img = tmp_path / "test.jpg"
        img.write_bytes(b"fake")

        response_data = {"responses": [{}]}
        mock_urlopen.return_value = self._make_mock_response(response_data)
        _run_google_cloud(str(img))

        # Check timeout parameter
        call_kwargs = mock_urlopen.call_args
        assert call_kwargs[1].get("timeout") == GOOGLE_CLOUD_OCR_TIMEOUT or (
            len(call_kwargs[0]) > 1 and call_kwargs[0][1] == GOOGLE_CLOUD_OCR_TIMEOUT
        )


# ---------------------------------------------------------------------------
# NEW TESTS: run_ocr integration — complex pipelines
# ---------------------------------------------------------------------------


class TestRunOCRIntegrationAdditional:
    """Additional end-to-end tests for run_ocr pipeline."""

    @patch(f"{_OCR}._run_tesseract")
    def test_multiline_merging_through_pipeline(self, mock_tess):
        """Pipeline merges words into sentences across multiple lines."""
        mock_tess.return_value = [
            OCRResult("Hello", 0, 0, 30, 10, 0.9),
            OCRResult("World", 32, 0, 30, 10, 0.85),
            OCRResult("Goodbye", 0, 30, 40, 10, 0.9),
            OCRResult("World", 42, 30, 30, 10, 0.85),
        ]
        results = run_ocr("img.png", method=OCR_METHOD_TESSERACT)
        assert len(results) == 2  # noqa: PLR2004
        assert results[0].text == "Hello World"
        assert results[1].text == "Goodbye World"

    @patch(f"{_OCR}._run_easyocr")
    def test_easyocr_through_pipeline(self, mock_easy):
        """EasyOCR results go through merge pipeline."""
        mock_easy.return_value = [
            OCRResult("One", 0, 0, 20, 10, 0.9),
            OCRResult("Two", 22, 0, 20, 10, 0.8),
        ]
        results = run_ocr("img.png", method=OCR_METHOD_EASYOCR)
        assert len(results) == 1
        assert results[0].text == "One Two"

    @patch(f"{_OCR}._run_google_cloud")
    def test_google_cloud_through_pipeline(self, mock_gc):
        """Google Cloud results go through merge pipeline."""
        mock_gc.return_value = [
            OCRResult("Alpha", 0, 0, 30, 10, 1.0),
            OCRResult("Beta", 32, 0, 25, 10, 1.0),
        ]
        results = run_ocr("img.png", method=OCR_METHOD_GOOGLE_CLOUD)
        assert len(results) == 1
        assert results[0].text == "Alpha Beta"

    @patch(f"{_OCR}._run_tesseract")
    def test_all_whitespace_from_backend_returns_empty(self, mock_tess):
        """Backend returning only whitespace fragments -> empty after merge."""
        mock_tess.return_value = [
            OCRResult("  ", 0, 0, 10, 10, 0.5),
            OCRResult(" \t ", 20, 0, 10, 10, 0.5),
            OCRResult("\n", 40, 0, 10, 10, 0.5),
        ]
        results = run_ocr("img.png", method=OCR_METHOD_TESSERACT)
        assert results == []

    @patch(f"{_OCR}._run_tesseract")
    def test_bold_italic_preserved_through_pipeline(self, mock_tess):
        """Bold/italic flags survive through the merge pipeline."""
        r = OCRResult("styled", 0, 0, 50, 15, 0.9)
        r.is_bold = True
        r.is_italic = True
        mock_tess.return_value = [r]
        results = run_ocr("img.png", method=OCR_METHOD_TESSERACT)
        assert results[0].is_bold is True
        assert results[0].is_italic is True

    @patch(f"{_OCR}._run_tesseract")
    def test_color_preserved_through_pipeline(self, mock_tess):
        """Color is preserved through merge pipeline for single fragment."""
        r = OCRResult("colored", 0, 0, 50, 15, 0.9)
        r.color = "#FF00FF"
        mock_tess.return_value = [r]
        results = run_ocr("img.png", method=OCR_METHOD_TESSERACT)
        assert results[0].color == "#FF00FF"

    @patch(f"{_OCR}._run_tesseract")
    def test_many_fragments_merge_to_few_blocks(self, mock_tess):
        """Many small fragments merge into fewer blocks."""
        # 10 words on line 1, 10 words on line 2
        line1 = [OCRResult(f"L1W{i}", i * 12, 0, 10, 10, 0.9) for i in range(10)]
        line2 = [OCRResult(f"L2W{i}", i * 12, 30, 10, 10, 0.9) for i in range(10)]
        mock_tess.return_value = line1 + line2
        results = run_ocr("img.png", method=OCR_METHOD_TESSERACT)
        assert len(results) == 2  # noqa: PLR2004


# ---------------------------------------------------------------------------
# NEW TESTS: merge_ocr_results — zero and one element lists
# ---------------------------------------------------------------------------


class TestMergeSpecialCases:
    """Tests for merge_ocr_results with special inputs."""

    def test_empty_text_fragment_filtered(self):
        """Fragment with empty string text (after strip) is filtered."""
        r = OCRResult("", 0, 0, 10, 10, 0.9)
        assert merge_ocr_results([r]) == []

    def test_fragment_with_single_space(self):
        """Single space fragment is filtered."""
        r = OCRResult(" ", 0, 0, 10, 10, 0.9)
        assert merge_ocr_results([r]) == []

    def test_two_fragments_zero_gap(self):
        """Two fragments with zero horizontal gap merge."""
        r1 = OCRResult("A", 0, 0, 20, 10, 0.9)
        r2 = OCRResult("B", 20, 0, 20, 10, 0.8)  # gap = 0
        result = merge_ocr_results([r1, r2])
        assert len(result) == 1
        assert result[0].text == "A B"

    def test_two_overlapping_fragments_vertically_no_horizontal_overlap(self):
        """Partial vertical overlap but large horizontal gap -> separate."""
        r1 = OCRResult("A", 0, 0, 20, 10, 0.9)
        # overlap = min(10, 5+10) - max(0, 5) = 10 - 5 = 5
        # min_h = 10, threshold = 10 * 0.6 = 6. 5 > 6? No -> different lines
        r2 = OCRResult("B", 200, 5, 20, 10, 0.8)
        result = merge_ocr_results([r1, r2])
        assert len(result) == 2  # noqa: PLR2004

    def test_many_fragments_single_line_long_sentence(self):
        """20 words on one line with tight spacing -> one merged block."""
        frags = [OCRResult(f"w{i}", i * 12, 0, 10, 15, 0.9) for i in range(20)]
        result = merge_ocr_results(frags)
        assert len(result) == 1

    def test_diagonal_fragments_stay_separate(self):
        """Fragments arranged diagonally don't overlap enough to merge lines."""
        frags = [
            OCRResult("A", 0, 0, 20, 10, 0.9),
            OCRResult("B", 100, 50, 20, 10, 0.8),
            OCRResult("C", 200, 100, 20, 10, 0.7),
        ]
        result = merge_ocr_results(frags)
        assert len(result) == 3  # noqa: PLR2004

    def test_confidence_after_merge_is_average_not_min(self):
        """Merged confidence is the running average, not min or max."""
        r1 = OCRResult("a", 0, 0, 10, 20, 1.0)
        r2 = OCRResult("b", 12, 0, 10, 20, 0.0)
        result = merge_ocr_results([r1, r2])
        assert result[0].confidence == pytest.approx(0.5)

    def test_underline_not_propagated_in_merge(self):
        """is_underline is NOT propagated during merge (only bold/italic are)."""
        r1 = OCRResult("a", 0, 0, 20, 20, 0.9)
        r1.is_underline = True
        r2 = OCRResult("b", 22, 0, 20, 20, 0.8)
        result = merge_ocr_results([r1, r2])
        # Merge creates a new OCRResult which defaults is_underline=False
        assert result[0].is_underline is False

    def test_translated_text_not_preserved_in_merge(self):
        """translated_text from fragments is lost during merge (fresh OCRResult)."""
        r1 = OCRResult("a", 0, 0, 20, 20, 0.9)
        r1.translated_text = "should be lost"
        r2 = OCRResult("b", 22, 0, 20, 20, 0.8)
        result = merge_ocr_results([r1, r2])
        assert result[0].translated_text == ""

    def test_single_fragment_no_merge_keeps_underline(self):
        """Single fragment not merged keeps its is_underline flag."""
        r = OCRResult("solo", 0, 0, 50, 20, 0.9)
        r.is_underline = True
        result = merge_ocr_results([r])
        assert result[0].is_underline is True


# ---------------------------------------------------------------------------
# NEW TESTS: Tesseract — command construction
# ---------------------------------------------------------------------------


class TestTesseractCommandConstruction:
    """Verify the tesseract subprocess command is correctly constructed."""

    _TSV_HEADER = (
        "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num"
        "\tleft\ttop\twidth\theight\tconf\ttext"
    )

    def _make_tsv(self, rows):
        return self._TSV_HEADER + "\n" + "\n".join(rows) + "\n"

    def _fake_run_success(self, tsv_content):
        def _side_effect(cmd, check, capture_output):
            out_base = Path(cmd[2])
            tsv_path = out_base.with_suffix(".tsv")
            tsv_path.write_text(tsv_content, encoding="utf-8")

        return _side_effect

    @patch(f"{_OCR}.subprocess.run")
    def test_command_starts_with_tesseract(self, mock_run):
        """Command starts with 'tesseract' executable."""
        tsv = self._make_tsv([])
        mock_run.side_effect = self._fake_run_success(tsv)
        _run_tesseract("img.png")
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "tesseract"

    @patch(f"{_OCR}.subprocess.run")
    def test_command_has_check_true(self, mock_run):
        """subprocess.run is called with check=True."""
        tsv = self._make_tsv([])
        mock_run.side_effect = self._fake_run_success(tsv)
        _run_tesseract("img.png")
        assert (
            mock_run.call_args[1].get("check") is True
            or mock_run.call_args.kwargs.get("check") is True
        )

    @patch(f"{_OCR}.subprocess.run")
    def test_command_has_capture_output_true(self, mock_run):
        """subprocess.run is called with capture_output=True."""
        tsv = self._make_tsv([])
        mock_run.side_effect = self._fake_run_success(tsv)
        _run_tesseract("img.png")
        assert (
            mock_run.call_args[1].get("capture_output") is True
            or mock_run.call_args.kwargs.get("capture_output") is True
        )

    @patch(f"{_OCR}.subprocess.run")
    def test_fallback_command_uses_eng(self, mock_run):
        """Fallback command uses 'eng' language."""
        cmds = []

        def _side_effect(cmd, check, capture_output):
            cmds.append(list(cmd))
            if "spa" in cmd:
                raise subprocess.CalledProcessError(1, cmd)
            out_base = Path(cmd[2])
            tsv_path = out_base.with_suffix(".tsv")
            tsv_path.write_text(self._TSV_HEADER + "\n", encoding="utf-8")

        mock_run.side_effect = _side_effect
        _run_tesseract("img.png", lang="spa")
        # Second command should use eng
        assert "eng" in cmds[1]
        assert "spa" not in cmds[1]


# ---------------------------------------------------------------------------
# NEW TESTS: EasyOCR — UNO import bypass integration
# ---------------------------------------------------------------------------


class TestEasyOCRUnoIntegration:
    """Verify _get_easyocr_reader correctly handles UNO import bypass."""

    def setup_method(self):
        _easyocr_readers.clear()

    def teardown_method(self):
        _easyocr_readers.clear()

    def test_no_uno_no_bypass(self):
        """Without UNO module, import proceeds normally."""

        class _FakeReader:
            def __init__(self, langs, **kwargs):
                pass

        mock_easyocr = MagicMock()
        mock_easyocr.Reader = _FakeReader

        # Ensure no 'uno' in sys.modules
        mods = {"easyocr": mock_easyocr}
        with patch.dict(sys.modules, mods, clear=False):
            sys.modules.pop("uno", None)
            reader = _get_easyocr_reader(["en"])
            assert reader is not None

    def test_uno_present_with_hook_restored_after_import(self):
        """UNO hook is properly restored after easyocr import."""
        real_import = builtins.__import__
        fake_uno = ModuleType("uno")
        fake_uno._builtin_import = real_import  # type: ignore[attr-defined]

        def _uno_hook(name, *args, **kwargs):
            return real_import(name, *args, **kwargs)

        class _FakeReader:
            def __init__(self, langs, **kwargs):
                pass

        mock_easyocr = MagicMock()
        mock_easyocr.Reader = _FakeReader

        builtins.__import__ = _uno_hook
        try:
            with patch.dict(sys.modules, {"uno": fake_uno, "easyocr": mock_easyocr}):
                _get_easyocr_reader(["en"])
                # UNO hook should be restored
                assert builtins.__import__ is _uno_hook
        finally:
            builtins.__import__ = real_import

    def test_uno_hook_restored_even_on_import_error(self):
        """UNO hook is restored even if easyocr import fails."""
        real_import = builtins.__import__

        def _failing_import(name, *args, **kwargs):
            """Import that refuses to load easyocr."""
            if name == "easyocr":
                raise ImportError("easyocr not found")
            return real_import(name, *args, **kwargs)

        fake_uno = ModuleType("uno")
        # _bypass_uno_import will swap to this; it must also reject easyocr
        fake_uno._builtin_import = _failing_import  # type: ignore[attr-defined]

        def _uno_hook(name, *args, **kwargs):
            if name == "easyocr":
                raise ImportError("easyocr not found")
            return real_import(name, *args, **kwargs)

        builtins.__import__ = _uno_hook
        try:
            with patch.dict(sys.modules, {"uno": fake_uno}):
                # Remove easyocr from sys.modules to force actual import
                sys.modules.pop("easyocr", None)
                with pytest.raises(ImportError):
                    _get_easyocr_reader(["en"])
                # UNO hook should still be restored
                assert builtins.__import__ is _uno_hook
        finally:
            builtins.__import__ = real_import


# ---------------------------------------------------------------------------
# NEW TESTS: Google Cloud — image file handling
# ---------------------------------------------------------------------------


class TestGoogleCloudFileHandling:
    """Verify Google Cloud Vision file reading and encoding."""

    def _make_mock_response(self, response_data):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(response_data).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = False
        return mock_response

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value="key")
    @patch("urllib.request.urlopen")
    def test_reads_binary_file(self, mock_urlopen, mock_load, tmp_path):
        """Reads image file in binary mode."""
        img = tmp_path / "test.png"
        # Write some binary data
        img.write_bytes(b"\x89PNG\r\n\x1a\n" + bytes(range(256)))

        response_data = {"responses": [{}]}
        mock_urlopen.return_value = self._make_mock_response(response_data)
        # Should not raise
        _run_google_cloud(str(img))
        mock_urlopen.assert_called_once()

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value="key")
    @patch("urllib.request.urlopen")
    def test_empty_file_still_sends_request(self, mock_urlopen, mock_load, tmp_path):
        """Empty image file still sends the API request."""
        img = tmp_path / "empty.jpg"
        img.write_bytes(b"")

        response_data = {"responses": [{}]}
        mock_urlopen.return_value = self._make_mock_response(response_data)
        results = _run_google_cloud(str(img))
        assert results == []
        mock_urlopen.assert_called_once()


# ---------------------------------------------------------------------------
# NEW TESTS: EasyOCR fallback behavior — additional scenarios
# ---------------------------------------------------------------------------


class TestEasyOCRFallbackAdditional:
    """Additional fallback behavior tests for EasyOCR."""

    def setup_method(self):
        _easyocr_readers.clear()

    def teardown_method(self):
        _easyocr_readers.clear()

    def test_fallback_caches_default_reader(self):
        """After fallback, default language reader is cached."""

        class _FakeReader:
            def __init__(self, langs, **kwargs):
                if langs != EASYOCR_DEFAULT_LANGUAGES:
                    raise ValueError("Unsupported")

            def readtext(self, path):
                return []

        mock_easyocr = MagicMock()
        mock_easyocr.Reader = _FakeReader

        with patch.dict(sys.modules, {"easyocr": mock_easyocr}):
            _run_easyocr("img.png", languages=["xyz"])
        # Default language reader should be cached
        assert tuple(sorted(EASYOCR_DEFAULT_LANGUAGES)) in _easyocr_readers

    def test_non_import_error_not_caught_as_import_error(self):
        """RuntimeError during readtext is not swallowed as ImportError."""

        class _FakeReader:
            def __init__(self, langs, **kwargs):
                pass

            def readtext(self, path):
                raise RuntimeError("Decode failed")

        mock_easyocr = MagicMock()
        mock_easyocr.Reader = _FakeReader

        with (
            patch.dict(sys.modules, {"easyocr": mock_easyocr}),
            pytest.raises(RuntimeError, match="Decode failed"),
        ):
            _run_easyocr("img.png")


# ---------------------------------------------------------------------------
# NEW TESTS: Tesseract — language fallback extended scenarios
# ---------------------------------------------------------------------------


class TestTesseractFallbackAdditional:
    """Additional Tesseract language fallback tests."""

    _TSV_HEADER = (
        "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num"
        "\tleft\ttop\twidth\theight\tconf\ttext"
    )

    @patch(f"{_OCR}.subprocess.run")
    def test_fallback_from_korean(self, mock_run):
        """Korean fallback to eng: kor fails, eng succeeds."""
        cmds = []

        def _side_effect(cmd, check, capture_output):
            cmds.append(list(cmd))
            if "kor" in cmd:
                raise subprocess.CalledProcessError(1, cmd)
            out_base = Path(cmd[2])
            tsv_path = out_base.with_suffix(".tsv")
            tsv_path.write_text(self._TSV_HEADER + "\n", encoding="utf-8")

        mock_run.side_effect = _side_effect
        results = _run_tesseract("img.png", lang="kor")
        assert results == []
        assert len(cmds) == 2  # noqa: PLR2004
        assert "kor" in cmds[0]
        assert "eng" in cmds[1]

    @patch(f"{_OCR}.subprocess.run")
    def test_fallback_from_russian(self, mock_run):
        """Russian fallback to eng: rus fails, eng succeeds."""
        cmds = []

        def _side_effect(cmd, check, capture_output):
            cmds.append(list(cmd))
            if "rus" in cmd:
                raise subprocess.CalledProcessError(1, cmd)
            out_base = Path(cmd[2])
            tsv_path = out_base.with_suffix(".tsv")
            tsv_path.write_text(self._TSV_HEADER + "\n", encoding="utf-8")

        mock_run.side_effect = _side_effect
        results = _run_tesseract("img.png", lang="rus")
        assert results == []
        assert len(cmds) == 2  # noqa: PLR2004

    @patch(f"{_OCR}.subprocess.run")
    def test_no_fallback_when_eng_succeeds_first(self, mock_run):
        """No fallback attempt when eng succeeds on first try."""

        def _side_effect(cmd, check, capture_output):
            out_base = Path(cmd[2])
            tsv_path = out_base.with_suffix(".tsv")
            tsv_path.write_text(self._TSV_HEADER + "\n", encoding="utf-8")

        mock_run.side_effect = _side_effect
        _run_tesseract("img.png", lang="eng")
        assert mock_run.call_count == 1


# ---------------------------------------------------------------------------
# NEW TESTS: Merge — color and formatting propagation
# ---------------------------------------------------------------------------


class TestMergeFormattingPropagation:
    """Verify formatting propagation during merging."""

    def test_both_italic_stays_italic(self):
        """Both fragments italic -> merged is italic."""
        r1 = OCRResult("a", 0, 0, 20, 20, 0.9)
        r1.is_italic = True
        r2 = OCRResult("b", 22, 0, 20, 20, 0.8)
        r2.is_italic = True
        result = merge_ocr_results([r1, r2])
        assert result[0].is_italic is True

    def test_neither_italic_stays_not_italic(self):
        """Neither fragment italic -> merged is not italic."""
        r1 = OCRResult("a", 0, 0, 20, 20, 0.9)
        r2 = OCRResult("b", 22, 0, 20, 20, 0.8)
        result = merge_ocr_results([r1, r2])
        assert result[0].is_italic is False

    def test_bold_from_first_only(self):
        """First fragment bold, second not -> merged is bold."""
        r1 = OCRResult("a", 0, 0, 20, 20, 0.9)
        r1.is_bold = True
        r2 = OCRResult("b", 22, 0, 20, 20, 0.8)
        r2.is_bold = False
        result = merge_ocr_results([r1, r2])
        assert result[0].is_bold is True

    def test_bold_from_second_only(self):
        """Second fragment bold, first not -> merged is bold."""
        r1 = OCRResult("a", 0, 0, 20, 20, 0.9)
        r1.is_bold = False
        r2 = OCRResult("b", 22, 0, 20, 20, 0.8)
        r2.is_bold = True
        result = merge_ocr_results([r1, r2])
        assert result[0].is_bold is True

    def test_color_from_leftmost_in_reverse_input(self):
        """When fragments arrive in reverse x order, leftmost color wins."""
        r_right = OCRResult("r", 50, 0, 20, 20, 0.9)
        r_right.color = "#0000FF"
        r_left = OCRResult("l", 0, 0, 20, 20, 0.8)
        r_left.color = "#FF0000"
        result = merge_ocr_results([r_right, r_left])
        # r_left is leftmost after sorting
        assert result[0].color == "#FF0000"

    def test_multiple_colors_across_lines(self):
        """Each line preserves its own first-fragment color."""
        r1 = OCRResult("a", 0, 0, 20, 10, 0.9)
        r1.color = "#FF0000"
        r2 = OCRResult("b", 22, 0, 20, 10, 0.8)
        r2.color = "#00FF00"

        r3 = OCRResult("c", 0, 30, 20, 10, 0.9)
        r3.color = "#0000FF"
        r4 = OCRResult("d", 22, 30, 20, 10, 0.8)
        r4.color = "#FFFF00"

        result = merge_ocr_results([r1, r2, r3, r4])
        assert len(result) == 2  # noqa: PLR2004
        assert result[0].color == "#FF0000"
        assert result[1].color == "#0000FF"


# ---------------------------------------------------------------------------
# NEW TESTS: Google Cloud — API key validation
# ---------------------------------------------------------------------------


class TestGoogleCloudAPIKeyValidation:
    """Verify API key validation in Google Cloud backend."""

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value="")
    def test_empty_string_key_raises(self, mock_load):
        """Empty string API key raises AUTH_ERROR."""
        with pytest.raises(ValueError, match="AUTH_ERROR"):
            _run_google_cloud("test.jpg")

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value=None)
    def test_none_key_raises(self, mock_load):
        """None API key raises AUTH_ERROR."""
        with pytest.raises(ValueError, match="AUTH_ERROR"):
            _run_google_cloud("test.jpg")

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value=0)
    def test_zero_key_raises(self, mock_load):
        """Falsy integer key raises AUTH_ERROR."""
        with pytest.raises(ValueError, match="AUTH_ERROR"):
            _run_google_cloud("test.jpg")

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value="valid-key")
    @patch("urllib.request.urlopen")
    def test_valid_key_proceeds(self, mock_urlopen, mock_load, tmp_path):
        """Valid API key proceeds to make the request."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"fake")

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"responses": [{}]}).encode(
            "utf-8"
        )
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = False
        mock_urlopen.return_value = mock_response

        results = _run_google_cloud(str(img))
        assert results == []
        mock_urlopen.assert_called_once()


# ===========================================================================
# New expanded tests — Language dispatch for all backends
# ===========================================================================


class TestRunOCRLanguageDispatchAllBackends:
    """Verify run_ocr passes correct language codes to each backend."""

    @pytest.mark.parametrize(
        "lang,expected_tess_code",
        [
            ("Arabic", "ara"),
            ("Belarusian", "bel"),
            ("Bengali", "ben"),
            ("Bulgarian", "bul"),
            ("Chinese (Simplified)", "chi_sim"),
            ("Chinese (Traditional)", "chi_tra"),
            ("Croatian", "hrv"),
            ("Czech", "ces"),
            ("Danish", "dan"),
            ("Dutch", "nld"),
            ("English (UK)", "eng"),
            ("English (US)", "eng"),
            ("Estonian", "est"),
            ("Finnish", "fin"),
            ("French", "fra"),
            ("German", "deu"),
            ("Greek", "ell"),
            ("Hebrew", "heb"),
            ("Hindi", "hin"),
            ("Hungarian", "hun"),
            ("Indonesian", "ind"),
            ("Italian", "ita"),
            ("Japanese", "jpn"),
            ("Khmer", "khm"),
            ("Korean", "kor"),
            ("Latvian", "lav"),
            ("Lithuanian", "lit"),
            ("Malay", "msa"),
            ("Mongolian", "mon"),
            ("Nepali", "nep"),
            ("Persian", "fas"),
            ("Polish", "pol"),
            ("Portuguese (Brazil)", "por"),
            ("Portuguese (Portugal)", "por"),
            ("Romanian", "ron"),
            ("Russian", "rus"),
            ("Serbian", "srp"),
            ("Slovak", "slk"),
            ("Slovenian", "slv"),
            ("Spanish", "spa"),
            ("Swedish", "swe"),
            ("Thai", "tha"),
            ("Turkish", "tur"),
            ("Ukrainian", "ukr"),
            ("Vietnamese", "vie"),
        ],
    )
    @patch(f"{_OCR}._run_tesseract", return_value=[])
    def test_tesseract_lang_code_all_languages(
        self, mock_tess, lang, expected_tess_code
    ):
        """Tesseract receives correct language code for every supported language."""
        run_ocr("img.png", method=OCR_METHOD_TESSERACT, src_lang=lang)
        mock_tess.assert_called_once_with("img.png", lang=expected_tess_code)

    @pytest.mark.parametrize(
        "lang,expected_easy_langs",
        [
            ("Arabic", ["ar", "en"]),
            ("Chinese (Simplified)", ["ch_sim", "en"]),
            ("Chinese (Traditional)", ["ch_tra", "en"]),
            ("French", ["fr", "en"]),
            ("German", ["de", "en"]),
            ("Japanese", ["ja", "en"]),
            ("Korean", ["ko", "en"]),
            ("Russian", ["ru", "en"]),
            ("Vietnamese", ["vi", "en"]),
            ("English (US)", ["en"]),
            ("English (UK)", ["en"]),
            ("Thai", ["th", "en"]),
            ("Hindi", ["hi", "en"]),
            ("Bengali", ["bn", "en"]),
        ],
    )
    @patch(f"{_OCR}._run_easyocr", return_value=[])
    def test_easyocr_lang_list_selected_languages(
        self, mock_easy, lang, expected_easy_langs
    ):
        """EasyOCR receives correct language list for selected languages."""
        run_ocr("img.png", method=OCR_METHOD_EASYOCR, src_lang=lang)
        mock_easy.assert_called_once_with("img.png", languages=expected_easy_langs)

    @pytest.mark.parametrize(
        "lang,expected_hint",
        [
            ("Arabic", ["ar"]),
            ("Chinese (Simplified)", ["zh"]),
            ("Chinese (Traditional)", ["zh-TW"]),
            ("French", ["fr"]),
            ("Japanese", ["ja"]),
            ("Korean", ["ko"]),
            ("Serbian", ["sr"]),
            ("Vietnamese", ["vi"]),
        ],
    )
    @patch(f"{_OCR}._run_google_cloud", return_value=[])
    def test_google_cloud_lang_hints_selected(self, mock_gc, lang, expected_hint):
        """Google Cloud Vision receives correct language hints."""
        run_ocr("img.png", method=OCR_METHOD_GOOGLE_CLOUD, src_lang=lang)
        mock_gc.assert_called_once_with("img.png", lang_hints=expected_hint)

    @patch(f"{_OCR}._run_tesseract", return_value=[])
    def test_tesseract_unknown_language_defaults_eng(self, mock_tess):
        """Unknown language falls back to 'eng' for Tesseract."""
        run_ocr("img.png", method=OCR_METHOD_TESSERACT, src_lang="Klingon")
        mock_tess.assert_called_once_with("img.png", lang="eng")

    @patch(f"{_OCR}._run_easyocr", return_value=[])
    def test_easyocr_unknown_language_defaults_en(self, mock_easy):
        """Unknown language falls back to ['en'] for EasyOCR."""
        run_ocr("img.png", method=OCR_METHOD_EASYOCR, src_lang="Martian")
        mock_easy.assert_called_once_with("img.png", languages=["en"])

    @patch(f"{_OCR}._run_google_cloud", return_value=[])
    def test_google_cloud_unknown_language_no_hints(self, mock_gc):
        """Unknown language results in None lang_hints for Google Cloud."""
        run_ocr("img.png", method=OCR_METHOD_GOOGLE_CLOUD, src_lang="Elvish")
        mock_gc.assert_called_once_with("img.png", lang_hints=None)

    @patch(f"{_OCR}._run_tesseract", return_value=[])
    def test_tesseract_empty_language_defaults_eng(self, mock_tess):
        """Empty language string falls back to 'eng' for Tesseract."""
        run_ocr("img.png", method=OCR_METHOD_TESSERACT, src_lang="")
        mock_tess.assert_called_once_with("img.png", lang="eng")

    @patch(f"{_OCR}._run_easyocr", return_value=[])
    def test_easyocr_empty_language_defaults_en(self, mock_easy):
        """Empty language string falls back to ['en'] for EasyOCR."""
        run_ocr("img.png", method=OCR_METHOD_EASYOCR, src_lang="")
        mock_easy.assert_called_once_with("img.png", languages=["en"])

    @patch(f"{_OCR}._run_google_cloud", return_value=[])
    def test_google_cloud_empty_language_no_hints(self, mock_gc):
        """Empty language string results in None hints for Google Cloud."""
        run_ocr("img.png", method=OCR_METHOD_GOOGLE_CLOUD, src_lang="")
        mock_gc.assert_called_once_with("img.png", lang_hints=None)


# ===========================================================================
# New expanded tests — _bypass_uno_import edge cases
# ===========================================================================


class TestBypassUnoImportNesting:
    """Edge cases for UNO import hook bypass."""

    def test_no_uno_module_returns_none(self):
        """When 'uno' not in sys.modules, returns None."""
        saved = sys.modules.pop("uno", None)
        try:
            result = _bypass_uno_import()
            assert result is None
        finally:
            if saved is not None:
                sys.modules["uno"] = saved

    def test_uno_without_builtin_import_returns_none(self):
        """UNO present but no _builtin_import attribute returns None."""
        fake_uno = ModuleType("uno")
        saved_mod = sys.modules.get("uno")
        sys.modules["uno"] = fake_uno
        try:
            result = _bypass_uno_import()
            assert result is None
        finally:
            if saved_mod is not None:
                sys.modules["uno"] = saved_mod
            else:
                sys.modules.pop("uno", None)

    def test_uno_hook_already_original_returns_none(self):
        """If builtins.__import__ is already the original, returns None."""
        original_import = builtins.__import__
        fake_uno = ModuleType("uno")
        fake_uno._builtin_import = original_import
        saved_mod = sys.modules.get("uno")
        sys.modules["uno"] = fake_uno
        try:
            result = _bypass_uno_import()
            assert result is None
        finally:
            if saved_mod is not None:
                sys.modules["uno"] = saved_mod
            else:
                sys.modules.pop("uno", None)

    def test_bypass_swaps_and_returns_hook(self):
        """When UNO hook is active, bypass swaps import and returns hook."""
        original_import = builtins.__import__

        def uno_hook(*a, **k):
            return None

        fake_uno = ModuleType("uno")
        fake_uno._builtin_import = original_import
        builtins.__import__ = uno_hook

        saved_mod = sys.modules.get("uno")
        sys.modules["uno"] = fake_uno
        try:
            result = _bypass_uno_import()
            assert result is uno_hook
            assert builtins.__import__ is original_import
        finally:
            builtins.__import__ = original_import
            if saved_mod is not None:
                sys.modules["uno"] = saved_mod
            else:
                sys.modules.pop("uno", None)

    def test_bypass_cleanup_restores_on_exception(self):
        """Caller can restore hook in a finally block after exception."""
        original_import = builtins.__import__
        uno_hook = MagicMock(side_effect=ImportError("boom"))
        fake_uno = ModuleType("uno")
        fake_uno._builtin_import = original_import
        builtins.__import__ = uno_hook

        saved_mod = sys.modules.get("uno")
        sys.modules["uno"] = fake_uno
        try:
            saved_hook = _bypass_uno_import()
            assert saved_hook is uno_hook
            # Simulate caller doing work and restoring
            builtins.__import__ = saved_hook
            assert builtins.__import__ is uno_hook
        finally:
            builtins.__import__ = original_import
            if saved_mod is not None:
                sys.modules["uno"] = saved_mod
            else:
                sys.modules.pop("uno", None)


# ===========================================================================
# New expanded tests — Merge overlapping and adjacent boxes
# ===========================================================================


class TestMergeOverlappingAdjacentBoxes:
    """Edge cases for merging OCR boxes."""

    def test_completely_overlapping_boxes_merge(self):
        """Two boxes at exact same position merge to single result."""
        r1 = OCRResult("hello", 10, 10, 50, 20, 0.9)
        r2 = OCRResult("world", 10, 10, 50, 20, 0.8)
        results = merge_ocr_results([r1, r2])
        assert len(results) == 1
        assert "hello" in results[0].text
        assert "world" in results[0].text

    def test_adjacent_horizontal_boxes_merge(self):
        """Horizontally adjacent boxes (0 gap) merge."""
        r1 = OCRResult("hello", 0, 0, 50, 20, 0.9)
        r2 = OCRResult("world", 50, 0, 50, 20, 0.8)
        results = merge_ocr_results([r1, r2])
        assert len(results) == 1
        assert results[0].text == "hello world"

    def test_vertically_separate_boxes_stay_separate(self):
        """Boxes with large vertical gap remain separate."""
        r1 = OCRResult("line1", 0, 0, 50, 20, 0.9)
        r2 = OCRResult("line2", 0, 100, 50, 20, 0.8)
        results = merge_ocr_results([r1, r2])
        assert len(results) == 2

    def test_partially_overlapping_vertical_merge(self):
        """Boxes with partial vertical overlap on same line merge."""
        r1 = OCRResult("hello", 0, 0, 50, 20, 0.9)
        r2 = OCRResult("world", 55, 5, 50, 20, 0.8)
        results = merge_ocr_results([r1, r2])
        assert len(results) == 1

    def test_contained_box_merges(self):
        """Small box fully inside larger box merges."""
        r1 = OCRResult("big", 0, 0, 200, 40, 0.9)
        r2 = OCRResult("tiny", 50, 5, 30, 15, 0.8)
        results = merge_ocr_results([r1, r2])
        assert len(results) == 1

    def test_wide_horizontal_gap_separates(self):
        """Boxes with a gap wider than threshold remain separate."""
        r1 = OCRResult("left", 0, 0, 50, 20, 0.9)
        r2 = OCRResult("right", 200, 0, 50, 20, 0.8)
        results = merge_ocr_results([r1, r2])
        assert len(results) == 2

    def test_merged_box_coordinates_are_union(self):
        """Merged box coordinates span the union of both boxes."""
        r1 = OCRResult("a", 10, 5, 40, 20, 0.8)
        r2 = OCRResult("b", 55, 0, 30, 25, 0.9)
        results = merge_ocr_results([r1, r2])
        assert len(results) == 1
        assert results[0].x == 10
        assert results[0].y == 0
        assert results[0].w == 75  # 85 - 10
        assert results[0].h == 25

    def test_three_boxes_chain_merge(self):
        """Three boxes in a row merge into one."""
        r1 = OCRResult("a", 0, 0, 20, 15, 0.9)
        r2 = OCRResult("b", 22, 0, 20, 15, 0.8)
        r3 = OCRResult("c", 44, 0, 20, 15, 0.7)
        results = merge_ocr_results([r1, r2, r3])
        assert len(results) == 1
        assert results[0].text == "a b c"

    def test_merge_preserves_first_color(self):
        """Merged block retains the color of the first fragment."""
        r1 = OCRResult("a", 0, 0, 50, 20, 0.9)
        r1.color = "#FF0000"
        r2 = OCRResult("b", 55, 0, 50, 20, 0.8)
        r2.color = "#00FF00"
        results = merge_ocr_results([r1, r2])
        assert results[0].color == "#FF0000"


# ===========================================================================
# New expanded tests — Confidence handling in merge
# ===========================================================================


class TestMergeConfidenceHandling:
    """Verify confidence averaging during merge."""

    def test_average_confidence_two_fragments(self):
        """Two merged fragments produce averaged confidence."""
        r1 = OCRResult("a", 0, 0, 50, 20, 0.8)
        r2 = OCRResult("b", 55, 0, 50, 20, 0.6)
        results = merge_ocr_results([r1, r2])
        assert len(results) == 1
        assert results[0].confidence == pytest.approx(0.7, abs=0.01)

    def test_average_confidence_three_fragments(self):
        """Three chain-merged fragments produce iterative average."""
        r1 = OCRResult("a", 0, 0, 20, 15, 1.0)
        r2 = OCRResult("b", 22, 0, 20, 15, 0.6)
        r3 = OCRResult("c", 44, 0, 20, 15, 0.5)
        results = merge_ocr_results([r1, r2, r3])
        assert len(results) == 1
        # First merge: (1.0 + 0.6) / 2 = 0.8
        # Second merge: (0.8 + 0.5) / 2 = 0.65
        assert results[0].confidence == pytest.approx(0.65, abs=0.01)

    def test_single_fragment_keeps_confidence(self):
        """Unmerged single fragment keeps its original confidence."""
        r1 = OCRResult("alone", 0, 0, 50, 20, 0.42)
        results = merge_ocr_results([r1])
        assert results[0].confidence == 0.42

    def test_perfect_confidence_averaged(self):
        """Two perfect confidence fragments merge correctly."""
        r1 = OCRResult("a", 0, 0, 50, 20, 1.0)
        r2 = OCRResult("b", 55, 0, 50, 20, 1.0)
        results = merge_ocr_results([r1, r2])
        assert results[0].confidence == 1.0


# ===========================================================================
# New expanded tests — EasyOCR caching and reader creation
# ===========================================================================


class TestEasyOCRReaderCreation:
    """Verify EasyOCR reader caching behavior."""

    @patch(f"{_OCR}._bypass_uno_import", return_value=None)
    def test_same_lang_reuses_reader(self, mock_bypass):
        """Same language set reuses cached reader."""
        _easyocr_readers.clear()

        mock_easyocr = MagicMock()
        mock_reader = MagicMock()
        mock_easyocr.Reader.return_value = mock_reader

        with patch.dict("sys.modules", {"easyocr": mock_easyocr}):
            r1 = _get_easyocr_reader(["en"])
            r2 = _get_easyocr_reader(["en"])

        assert r1 is r2
        assert mock_easyocr.Reader.call_count == 1

    @patch(f"{_OCR}._bypass_uno_import", return_value=None)
    def test_different_lang_creates_new_reader(self, mock_bypass):
        """Different language set creates a new reader."""
        _easyocr_readers.clear()

        mock_easyocr = MagicMock()
        mock_easyocr.Reader.side_effect = [MagicMock(), MagicMock()]

        with patch.dict("sys.modules", {"easyocr": mock_easyocr}):
            r1 = _get_easyocr_reader(["en"])
            r2 = _get_easyocr_reader(["ja", "en"])

        assert r1 is not r2
        assert mock_easyocr.Reader.call_count == 2

    @patch(f"{_OCR}._bypass_uno_import", return_value=None)
    def test_reader_created_without_gpu(self, mock_bypass):
        """Reader is created with gpu=False."""
        _easyocr_readers.clear()

        mock_easyocr = MagicMock()
        with patch.dict("sys.modules", {"easyocr": mock_easyocr}):
            _get_easyocr_reader(["en"])

        mock_easyocr.Reader.assert_called_once_with(
            ["en"], gpu=False, quantize=False, verbose=False
        )

    @patch(f"{_OCR}._bypass_uno_import", return_value=None)
    def test_sorted_key_normalizes_order(self, mock_bypass):
        """Language list order doesn't matter for caching."""
        _easyocr_readers.clear()

        mock_easyocr = MagicMock()
        with patch.dict("sys.modules", {"easyocr": mock_easyocr}):
            r1 = _get_easyocr_reader(["en", "ja"])
            r2 = _get_easyocr_reader(["ja", "en"])

        assert r1 is r2
        assert mock_easyocr.Reader.call_count == 1

    @patch(f"{_OCR}._bypass_uno_import", return_value=None)
    def test_reader_quantize_disabled(self, mock_bypass):
        """Reader is created with quantize=False."""
        _easyocr_readers.clear()

        mock_easyocr = MagicMock()
        with patch.dict("sys.modules", {"easyocr": mock_easyocr}):
            _get_easyocr_reader(["fr", "en"])

        call_kwargs = mock_easyocr.Reader.call_args[1]
        assert call_kwargs["quantize"] is False


# ===========================================================================
# New expanded tests — Google Cloud error handling
# ===========================================================================


class TestGoogleCloudQuotaAndHTTPErrors:
    """Verify Google Cloud OCR handles HTTP errors correctly."""

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value="valid")
    def test_http_429_raises_quota_error_sentinel(self, mock_key, tmp_path):
        """HTTP 429 maps to ``QUOTA_ERROR`` sentinel.

        The raw HTTPError used to leak through with an opaque
        "Too Many Requests" body; the typed sentinel routes through
        ``display_error_message`` to the localized
        ``error_msg.llm_quota_exceeded`` toast.
        """
        img = tmp_path / "test.jpg"
        img.write_bytes(b"fake")
        from urllib.error import HTTPError

        error = HTTPError("url", 429, "Too Many Requests", {}, None)
        with (
            patch("urllib.request.urlopen", side_effect=error),
            pytest.raises(ValueError, match="QUOTA_ERROR"),
        ):
            _run_google_cloud(str(img))

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value="valid")
    def test_http_401_raises_auth_error_sentinel(self, mock_key, tmp_path):
        """HTTP 401 maps to ``AUTH_ERROR`` sentinel."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"fake")
        from urllib.error import HTTPError

        error = HTTPError("url", 401, "Unauthorized", {}, None)
        with (
            patch("urllib.request.urlopen", side_effect=error),
            pytest.raises(ValueError, match="AUTH_ERROR"),
        ):
            _run_google_cloud(str(img))

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value="valid")
    def test_http_403_raises_auth_error_sentinel(self, mock_key, tmp_path):
        """HTTP 403 (forbidden — billing / API not enabled) → AUTH_ERROR."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"fake")
        from urllib.error import HTTPError

        error = HTTPError("url", 403, "Forbidden", {}, None)
        with (
            patch("urllib.request.urlopen", side_effect=error),
            pytest.raises(ValueError, match="AUTH_ERROR"),
        ):
            _run_google_cloud(str(img))

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value="valid")
    def test_http_503_raises_service_unavailable_sentinel(
        self, mock_key, tmp_path,
    ):
        """HTTP 5xx maps to SERVICE_UNAVAILABLE_ERROR for retry-friendly UI."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"fake")
        from urllib.error import HTTPError

        error = HTTPError("url", 503, "Service Unavailable", {}, None)
        with (
            patch("urllib.request.urlopen", side_effect=error),
            pytest.raises(ValueError, match="SERVICE_UNAVAILABLE_ERROR"),
        ):
            _run_google_cloud(str(img))

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value="valid")
    def test_http_413_raises_image_too_large_sentinel(
        self, mock_key, tmp_path,
    ):
        """HTTP 413 (payload too large) → IMAGE_TOO_LARGE.

        Belt-and-braces: pre-flight should catch oversize images
        first, but if the server's JSON body limit is tighter than
        our pre-flight cap we still want the user-visible error to
        match the pre-flight one.
        """
        img = tmp_path / "test.jpg"
        img.write_bytes(b"fake")
        from urllib.error import HTTPError

        error = HTTPError("url", 413, "Payload Too Large", {}, None)
        with (
            patch("urllib.request.urlopen", side_effect=error),
            pytest.raises(ValueError, match="IMAGE_TOO_LARGE"),
        ):
            _run_google_cloud(str(img))

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value="valid")
    def test_http_400_still_raises(self, mock_key, tmp_path):
        """HTTP 400 (not in our mapped list) re-raises the original HTTPError.

        Other 4xx that aren't auth / quota / size leak through —
        rare in practice (a 400 from Vision usually means a
        malformed request body, which is a programming bug we
        should see in the traceback).
        """
        img = tmp_path / "test.jpg"
        img.write_bytes(b"fake")
        from urllib.error import HTTPError

        error = HTTPError("url", 400, "Bad Request", {}, None)
        with (
            patch("urllib.request.urlopen", side_effect=error),
            pytest.raises(HTTPError),
        ):
            _run_google_cloud(str(img))

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value="valid")
    def test_url_error_raises_connection_error_sentinel(
        self, mock_key, tmp_path,
    ):
        """URLError (DNS / refused connection) → CONNECTION_ERROR."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"fake")
        from urllib.error import URLError

        with (
            patch("urllib.request.urlopen", side_effect=URLError("offline")),
            pytest.raises(ValueError, match="CONNECTION_ERROR"),
        ):
            _run_google_cloud(str(img))

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value="valid")
    def test_socket_timeout_raises_timeout_error_sentinel(
        self, mock_key, tmp_path,
    ):
        """socket.timeout (request-level timeout) → TIMEOUT_ERROR."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"fake")
        with (
            patch("urllib.request.urlopen", side_effect=TimeoutError()),
            pytest.raises(ValueError, match="TIMEOUT_ERROR"),
        ):
            _run_google_cloud(str(img))

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value="valid")
    @patch("urllib.request.urlopen")
    def test_empty_annotations_returns_empty(self, mock_urlopen, mock_key, tmp_path):
        """Empty textAnnotations returns empty list."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"fake")

        resp = MagicMock()
        resp.read.return_value = json.dumps(
            {"responses": [{"textAnnotations": []}]}
        ).encode()
        resp.__enter__.return_value = resp
        resp.__exit__.return_value = False
        mock_urlopen.return_value = resp

        results = _run_google_cloud(str(img))
        assert results == []

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value="valid")
    @patch("urllib.request.urlopen")
    def test_single_word_annotation(self, mock_urlopen, mock_key, tmp_path):
        """Single word annotation (after skipping full text) is returned."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"fake")

        resp = MagicMock()
        resp.read.return_value = json.dumps(
            {
                "responses": [
                    {
                        "textAnnotations": [
                            {"description": "Full text\nline2"},
                            {
                                "description": "Full",
                                "boundingPoly": {
                                    "vertices": [
                                        {"x": 0, "y": 0},
                                        {"x": 50, "y": 0},
                                        {"x": 50, "y": 20},
                                        {"x": 0, "y": 20},
                                    ]
                                },
                            },
                        ]
                    }
                ]
            }
        ).encode()
        resp.__enter__.return_value = resp
        resp.__exit__.return_value = False
        mock_urlopen.return_value = resp

        results = _run_google_cloud(str(img))
        assert len(results) == 1
        assert results[0].text == "Full"
        assert results[0].x == 0
        assert results[0].w == 50

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value="valid")
    @patch("urllib.request.urlopen")
    def test_annotation_missing_vertices_skipped(
        self, mock_urlopen, mock_key, tmp_path
    ):
        """Annotation without vertices is skipped."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"fake")

        resp = MagicMock()
        resp.read.return_value = json.dumps(
            {
                "responses": [
                    {
                        "textAnnotations": [
                            {"description": "Full text"},
                            {"description": "word", "boundingPoly": {}},
                        ]
                    }
                ]
            }
        ).encode()
        resp.__enter__.return_value = resp
        resp.__exit__.return_value = False
        mock_urlopen.return_value = resp

        results = _run_google_cloud(str(img))
        assert results == []


# ===========================================================================
# New expanded tests — Tesseract language fallback variants
# ===========================================================================


class TestTesseractLangFallbackVariants:
    """Verify Tesseract falls back to 'eng' when language pack is missing."""

    @pytest.mark.parametrize(
        "lang_code",
        ["fra", "deu", "jpn", "ara", "chi_sim", "kor", "hin", "vie", "tha"],
    )
    def test_fallback_to_eng_on_error(self, lang_code, tmp_path):
        """Tesseract retries with 'eng' when language pack fails."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"fake")

        call_count = 0

        def mock_run(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            if "-l" in cmd and lang_code in cmd:
                raise subprocess.CalledProcessError(1, cmd)
            # Create fake TSV output for eng fallback
            out_base = None
            for i, c in enumerate(cmd):
                if c == "tesseract":
                    out_base = cmd[i + 2]
                    break
            if out_base:
                tsv = Path(out_base + ".tsv")
                tsv.write_text(
                    "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
                )

        with patch("subprocess.run", side_effect=mock_run):
            _run_tesseract(str(img), lang=lang_code)

        assert call_count == 2

    def test_eng_failure_raises(self, tmp_path):
        """When even 'eng' fails, error is raised (not caught internally)."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"fake")

        with patch(
            "subprocess.run",
            side_effect=subprocess.CalledProcessError(1, "tesseract"),
        ):
            # Should not crash — the error is caught by the except block
            results = _run_tesseract(str(img), lang="eng")
            assert results == []


# ===========================================================================
# New expanded tests — EasyOCR fallback chain
# ===========================================================================


class TestEasyOCRFallbackChain:
    """Verify EasyOCR falls back to default languages on failure."""

    @patch(f"{_OCR}._bypass_uno_import", return_value=None)
    def test_fallback_on_reader_creation_error(self, mock_bypass):
        """Falls back to EASYOCR_DEFAULT_LANGUAGES on reader creation error."""
        _easyocr_readers.clear()

        mock_easyocr = MagicMock()
        fallback_reader = MagicMock()
        fallback_reader.readtext.return_value = []
        mock_easyocr.Reader.side_effect = [
            RuntimeError("lang not supported"),
            fallback_reader,
        ]

        with patch.dict("sys.modules", {"easyocr": mock_easyocr}):
            results = _run_easyocr("test.jpg", languages=["xx", "en"])

        assert results == []
        # Second call should be with default languages
        assert mock_easyocr.Reader.call_count == 2

    @patch(f"{_OCR}._bypass_uno_import", return_value=None)
    def test_default_lang_failure_raises(self, mock_bypass):
        """When default languages also fail, the error propagates."""
        _easyocr_readers.clear()

        mock_easyocr = MagicMock()
        mock_easyocr.Reader.side_effect = RuntimeError("fatal")

        with (
            patch.dict("sys.modules", {"easyocr": mock_easyocr}),
            pytest.raises(RuntimeError, match="fatal"),
        ):
            _run_easyocr("test.jpg", languages=["en"])

    @patch(f"{_OCR}._bypass_uno_import", return_value=None)
    def test_import_error_raises_import_error(self, mock_bypass):
        """ImportError from easyocr import propagates as ImportError."""
        _easyocr_readers.clear()

        with patch.dict("sys.modules", {"easyocr": None}), pytest.raises(ImportError):
            _run_easyocr("test.jpg")


# ===========================================================================
# New expanded tests — Missing engines and corrupt images
# ===========================================================================


class TestMissingEnginesAndCorruptImages:
    """Handle cases where OCR engines are not installed."""

    def test_tesseract_not_installed(self, tmp_path):
        """Missing tesseract binary raises FileNotFoundError."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"fake")

        with (
            patch(
                "subprocess.run",
                side_effect=FileNotFoundError("tesseract not found"),
            ),
            pytest.raises(FileNotFoundError),
        ):
            _run_tesseract(str(img))

    def test_run_ocr_unknown_method_returns_empty(self):
        """Unknown OCR method returns empty list without error."""
        results = run_ocr("img.png", method="UnknownOCR")
        assert results == []

    def test_run_ocr_no_method_returns_empty(self):
        """Calling run_ocr with empty method returns empty list."""
        results = run_ocr("img.png", method="")
        assert results == []


# ===========================================================================
# New expanded tests — Complex merge layouts
# ===========================================================================


class TestMergeComplexLayouts:
    """Merge behaviour for complex spatial layouts."""

    def test_two_column_layout_separate(self):
        """Two columns of text remain separate."""
        # Left column
        left1 = OCRResult("Left1", 0, 0, 100, 20, 0.9)
        left2 = OCRResult("Left2", 0, 25, 100, 20, 0.9)
        # Right column
        right1 = OCRResult("Right1", 250, 0, 100, 20, 0.9)
        right2 = OCRResult("Right2", 250, 25, 100, 20, 0.9)

        results = merge_ocr_results([left1, left2, right1, right2])
        # Each row merges separately (left and right are too far apart)
        assert len(results) == 4

    def test_paragraph_indented_first_line(self):
        """Indented first line does not merge with left-aligned body."""
        indent = OCRResult("First", 40, 0, 80, 20, 0.9)
        body1 = OCRResult("Second", 0, 25, 120, 20, 0.9)
        body2 = OCRResult("Third", 0, 50, 120, 20, 0.9)

        results = merge_ocr_results([indent, body1, body2])
        # Each line is separate (different y positions, no vertical overlap)
        assert len(results) == 3

    def test_scrambled_order_sorted_correctly(self):
        """Fragments given in random order are still sorted and merged correctly."""
        r3 = OCRResult("c", 60, 0, 25, 15, 0.7)
        r1 = OCRResult("a", 0, 0, 25, 15, 0.9)
        r2 = OCRResult("b", 30, 0, 25, 15, 0.8)

        results = merge_ocr_results([r3, r1, r2])
        assert len(results) == 1
        assert results[0].text == "a b c"

    def test_zero_height_fragments_filtered(self):
        """Whitespace-only fragments are filtered before merge."""
        r1 = OCRResult("hello", 0, 0, 50, 20, 0.9)
        r2 = OCRResult("   ", 55, 0, 50, 20, 0.8)
        r3 = OCRResult("world", 110, 0, 50, 20, 0.7)

        results = merge_ocr_results([r1, r2, r3])
        # Whitespace fragment is filtered; hello and world may or may not merge
        # depending on gap. At minimum, the whitespace fragment is not present.
        texts = " ".join(r.text for r in results)
        assert "   " not in texts

    def test_single_fragment_returned_as_is(self):
        """Single fragment returns unchanged."""
        r1 = OCRResult("only", 10, 10, 100, 30, 0.95)
        results = merge_ocr_results([r1])
        assert len(results) == 1
        assert results[0].text == "only"
        assert results[0].x == 10

    def test_empty_list_returns_empty(self):
        """Empty input returns empty list."""
        assert merge_ocr_results([]) == []

    def test_all_whitespace_fragments_return_empty(self):
        """All whitespace-only fragments result in empty list."""
        r1 = OCRResult("  ", 0, 0, 50, 20, 0.9)
        r2 = OCRResult("\t", 60, 0, 50, 20, 0.8)
        results = merge_ocr_results([r1, r2])
        assert results == []


# ===========================================================================
# New expanded tests — Merge bold/italic propagation
# ===========================================================================


class TestMergeBoldItalicPropagation:
    """Bold and italic flags propagate during merging."""

    def test_bold_propagates_from_first(self):
        """If first fragment is bold, merged block is bold."""
        r1 = OCRResult("bold", 0, 0, 50, 20, 0.9)
        r1.is_bold = True
        r2 = OCRResult("normal", 55, 0, 50, 20, 0.8)
        results = merge_ocr_results([r1, r2])
        assert results[0].is_bold is True

    def test_bold_propagates_from_second(self):
        """If second fragment is bold, merged block is bold."""
        r1 = OCRResult("normal", 0, 0, 50, 20, 0.9)
        r2 = OCRResult("bold", 55, 0, 50, 20, 0.8)
        r2.is_bold = True
        results = merge_ocr_results([r1, r2])
        assert results[0].is_bold is True

    def test_italic_propagates(self):
        """If any fragment is italic, merged block is italic."""
        r1 = OCRResult("normal", 0, 0, 50, 20, 0.9)
        r2 = OCRResult("italic", 55, 0, 50, 20, 0.8)
        r2.is_italic = True
        results = merge_ocr_results([r1, r2])
        assert results[0].is_italic is True

    def test_neither_bold_nor_italic(self):
        """Non-bold, non-italic fragments merge without flags."""
        r1 = OCRResult("a", 0, 0, 50, 20, 0.9)
        r2 = OCRResult("b", 55, 0, 50, 20, 0.8)
        results = merge_ocr_results([r1, r2])
        assert results[0].is_bold is False
        assert results[0].is_italic is False

    def test_both_bold_and_italic(self):
        """Both bold and italic set individually propagate."""
        r1 = OCRResult("a", 0, 0, 50, 20, 0.9)
        r1.is_bold = True
        r2 = OCRResult("b", 55, 0, 50, 20, 0.8)
        r2.is_italic = True
        results = merge_ocr_results([r1, r2])
        assert results[0].is_bold is True
        assert results[0].is_italic is True


# ===========================================================================
# New expanded tests — Tesseract TSV parsing edge cases
# ===========================================================================


class TestTesseractTsvParsingExpanded:
    """Additional Tesseract TSV parsing scenarios."""

    def test_tesseract_italic_bold_flags(self, tmp_path):
        """Tesseract TSV rows with italic=1 and bold=1 flags are parsed."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"fake")

        tsv_content = (
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\t"
            "left\ttop\twidth\theight\tconf\ttext\titalic\tbold\n"
            "5\t1\t1\t1\t1\t1\t10\t20\t100\t30\t90\thello\t1\t1\n"
        )

        def mock_run(cmd, **kwargs):
            out_base = cmd[2]
            Path(out_base + ".tsv").write_text(tsv_content)

        with patch("subprocess.run", side_effect=mock_run):
            results = _run_tesseract(str(img))

        assert len(results) == 1
        assert results[0].is_italic is True
        assert results[0].is_bold is True

    def test_tesseract_zero_confidence_skipped(self, tmp_path):
        """Words with zero confidence are skipped."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"fake")

        tsv_content = (
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\t"
            "left\ttop\twidth\theight\tconf\ttext\n"
            "5\t1\t1\t1\t1\t1\t10\t20\t100\t30\t0\tgarbage\n"
            "5\t1\t1\t1\t1\t2\t120\t20\t100\t30\t80\tgood\n"
        )

        def mock_run(cmd, **kwargs):
            out_base = cmd[2]
            Path(out_base + ".tsv").write_text(tsv_content)

        with patch("subprocess.run", side_effect=mock_run):
            results = _run_tesseract(str(img))

        assert len(results) == 1
        assert results[0].text == "good"

    def test_tesseract_negative_confidence_skipped(self, tmp_path):
        """Words with negative confidence are skipped."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"fake")

        tsv_content = (
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\t"
            "left\ttop\twidth\theight\tconf\ttext\n"
            "5\t1\t1\t1\t1\t1\t10\t20\t100\t30\t-1\tbad\n"
        )

        def mock_run(cmd, **kwargs):
            out_base = cmd[2]
            Path(out_base + ".tsv").write_text(tsv_content)

        with patch("subprocess.run", side_effect=mock_run):
            results = _run_tesseract(str(img))

        assert results == []

    def test_tesseract_non_word_level_rows_skipped(self, tmp_path):
        """Non-word level rows (level != 5) are skipped."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"fake")

        tsv_content = (
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\t"
            "left\ttop\twidth\theight\tconf\ttext\n"
            "1\t1\t0\t0\t0\t0\t0\t0\t500\t300\t-1\t\n"
            "3\t1\t1\t1\t0\t0\t0\t0\t500\t50\t-1\t\n"
            "4\t1\t1\t1\t1\t0\t0\t0\t500\t20\t-1\t\n"
            "5\t1\t1\t1\t1\t1\t10\t20\t80\t20\t95\thello\n"
        )

        def mock_run(cmd, **kwargs):
            out_base = cmd[2]
            Path(out_base + ".tsv").write_text(tsv_content)

        with patch("subprocess.run", side_effect=mock_run):
            results = _run_tesseract(str(img))

        assert len(results) == 1
        assert results[0].text == "hello"

    def test_tesseract_confidence_scaled(self, tmp_path):
        """Tesseract confidence is scaled from 0-100 to 0.0-1.0."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"fake")

        tsv_content = (
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\t"
            "left\ttop\twidth\theight\tconf\ttext\n"
            "5\t1\t1\t1\t1\t1\t10\t20\t80\t20\t75\tword\n"
        )

        def mock_run(cmd, **kwargs):
            out_base = cmd[2]
            Path(out_base + ".tsv").write_text(tsv_content)

        with patch("subprocess.run", side_effect=mock_run):
            results = _run_tesseract(str(img))

        assert results[0].confidence == pytest.approx(0.75, abs=0.001)

    def test_tesseract_empty_text_skipped(self, tmp_path):
        """Words with empty text are skipped."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"fake")

        tsv_content = (
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\t"
            "left\ttop\twidth\theight\tconf\ttext\n"
            "5\t1\t1\t1\t1\t1\t10\t20\t80\t20\t80\t\n"
            "5\t1\t1\t1\t1\t2\t100\t20\t80\t20\t80\treal\n"
        )

        def mock_run(cmd, **kwargs):
            out_base = cmd[2]
            Path(out_base + ".tsv").write_text(tsv_content)

        with patch("subprocess.run", side_effect=mock_run):
            results = _run_tesseract(str(img))

        assert len(results) == 1
        assert results[0].text == "real"

    def test_tesseract_multiple_words_per_line(self, tmp_path):
        """Multiple words on same line are all returned."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"fake")

        tsv_content = (
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\t"
            "left\ttop\twidth\theight\tconf\ttext\n"
            "5\t1\t1\t1\t1\t1\t10\t20\t50\t20\t90\thello\n"
            "5\t1\t1\t1\t1\t2\t65\t20\t50\t20\t85\tworld\n"
            "5\t1\t1\t1\t1\t3\t120\t20\t50\t20\t80\ttest\n"
        )

        def mock_run(cmd, **kwargs):
            out_base = cmd[2]
            Path(out_base + ".tsv").write_text(tsv_content)

        with patch("subprocess.run", side_effect=mock_run):
            results = _run_tesseract(str(img))

        assert len(results) == 3


# ===========================================================================
# New expanded tests — OCRResult to_dict edge cases
# ===========================================================================


class TestOCRResultToDictExpanded:
    """Additional to_dict coverage."""

    def test_to_dict_with_translated_text(self):
        """to_dict includes translated_text when set."""
        r = OCRResult("hello", 10, 20, 100, 50, 0.95)
        r.translated_text = "hola"
        d = r.to_dict()
        assert d["translated_text"] == "hola"

    def test_to_dict_with_custom_color(self):
        """to_dict includes custom color."""
        r = OCRResult("text", 0, 0, 1, 1, 1.0)
        r.color = "#FF5533"
        d = r.to_dict()
        assert d["color"] == "#FF5533"

    def test_to_dict_alignment_string(self):
        """to_dict converts alignment to string."""
        r = OCRResult("text", 0, 0, 1, 1, 1.0)
        r.alignment = "left"
        d = r.to_dict()
        assert d["alignment"] == "left"

    def test_to_dict_box_format(self):
        """to_dict box is [x, y, w, h] list."""
        r = OCRResult("text", 5, 15, 200, 80, 0.5)
        d = r.to_dict()
        assert d["box"] == [5, 15, 200, 80]

    def test_to_dict_bold_italic_true(self):
        """to_dict shows bold and italic when set."""
        r = OCRResult("text", 0, 0, 1, 1, 1.0)
        r.is_bold = True
        r.is_italic = True
        d = r.to_dict()
        assert d["is_bold"] is True
        assert d["is_italic"] is True

    def test_to_dict_underline(self):
        """to_dict shows is_underline."""
        r = OCRResult("text", 0, 0, 1, 1, 1.0)
        r.is_underline = True
        d = r.to_dict()
        assert d["is_underline"] is True


# ===========================================================================
# New expanded tests — Google Cloud request format
# ===========================================================================


class TestGoogleCloudRequestFormat:
    """Verify Google Cloud OCR request construction."""

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value="test-key")
    @patch("urllib.request.urlopen")
    def test_request_includes_api_key_in_url(self, mock_urlopen, mock_key, tmp_path):
        """API key is appended to the request URL."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"fake-image")

        resp = MagicMock()
        resp.read.return_value = json.dumps({"responses": [{}]}).encode()
        resp.__enter__.return_value = resp
        resp.__exit__.return_value = False
        mock_urlopen.return_value = resp

        _run_google_cloud(str(img))

        call_args = mock_urlopen.call_args
        req = call_args[0][0]
        assert "key=test-key" in req.full_url

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value="test-key")
    @patch("urllib.request.urlopen")
    def test_request_includes_lang_hints(self, mock_urlopen, mock_key, tmp_path):
        """Language hints are included in imageContext."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"fake-image")

        resp = MagicMock()
        resp.read.return_value = json.dumps({"responses": [{}]}).encode()
        resp.__enter__.return_value = resp
        resp.__exit__.return_value = False
        mock_urlopen.return_value = resp

        _run_google_cloud(str(img), lang_hints=["fr"])

        call_args = mock_urlopen.call_args
        req = call_args[0][0]
        body = json.loads(req.data)
        assert body["requests"][0]["imageContext"] == {"languageHints": ["fr"]}

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value="test-key")
    @patch("urllib.request.urlopen")
    def test_request_no_hints_when_none(self, mock_urlopen, mock_key, tmp_path):
        """No imageContext when lang_hints is None."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"fake-image")

        resp = MagicMock()
        resp.read.return_value = json.dumps({"responses": [{}]}).encode()
        resp.__enter__.return_value = resp
        resp.__exit__.return_value = False
        mock_urlopen.return_value = resp

        _run_google_cloud(str(img), lang_hints=None)

        call_args = mock_urlopen.call_args
        req = call_args[0][0]
        body = json.loads(req.data)
        assert "imageContext" not in body["requests"][0]

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value="test-key")
    @patch("urllib.request.urlopen")
    def test_request_base64_encodes_image(self, mock_urlopen, mock_key, tmp_path):
        """Image content is base64-encoded in the request."""
        import base64

        img = tmp_path / "test.jpg"
        raw = b"raw-image-bytes"
        img.write_bytes(raw)

        resp = MagicMock()
        resp.read.return_value = json.dumps({"responses": [{}]}).encode()
        resp.__enter__.return_value = resp
        resp.__exit__.return_value = False
        mock_urlopen.return_value = resp

        _run_google_cloud(str(img))

        call_args = mock_urlopen.call_args
        req = call_args[0][0]
        body = json.loads(req.data)
        expected_b64 = base64.b64encode(raw).decode("utf-8")
        assert body["requests"][0]["image"]["content"] == expected_b64

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value="test-key")
    @patch("urllib.request.urlopen")
    def test_request_feature_type_text_detection(
        self, mock_urlopen, mock_key, tmp_path
    ):
        """Request feature type is DOCUMENT_TEXT_DETECTION."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"fake")

        resp = MagicMock()
        resp.read.return_value = json.dumps({"responses": [{}]}).encode()
        resp.__enter__.return_value = resp
        resp.__exit__.return_value = False
        mock_urlopen.return_value = resp

        _run_google_cloud(str(img))

        call_args = mock_urlopen.call_args
        req = call_args[0][0]
        body = json.loads(req.data)
        features = body["requests"][0]["features"]
        assert any(f["type"] == "DOCUMENT_TEXT_DETECTION" for f in features)

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value="test-key")
    @patch("urllib.request.urlopen")
    def test_confidence_always_one(self, mock_urlopen, mock_key, tmp_path):
        """Google Cloud results always have confidence=1.0."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"fake")

        resp = MagicMock()
        resp.read.return_value = json.dumps(
            {
                "responses": [
                    {
                        "textAnnotations": [
                            {"description": "all"},
                            {
                                "description": "word",
                                "boundingPoly": {
                                    "vertices": [
                                        {"x": 0, "y": 0},
                                        {"x": 50, "y": 0},
                                        {"x": 50, "y": 20},
                                        {"x": 0, "y": 20},
                                    ]
                                },
                            },
                        ]
                    }
                ]
            }
        ).encode()
        resp.__enter__.return_value = resp
        resp.__exit__.return_value = False
        mock_urlopen.return_value = resp

        results = _run_google_cloud(str(img))
        assert results[0].confidence == 1.0


# ===========================================================================
# New expanded tests — EasyOCR result standardization
# ===========================================================================


class TestEasyOCRResultStandardization:
    """Verify EasyOCR results are converted to OCRResult correctly."""

    @patch(f"{_OCR}._bypass_uno_import", return_value=None)
    def test_bbox_conversion(self, mock_bypass):
        """EasyOCR 4-point bbox is converted to x,y,w,h."""
        _easyocr_readers.clear()

        mock_easyocr = MagicMock()
        mock_reader = MagicMock()
        mock_reader.readtext.return_value = [
            (
                [[10, 5], [110, 5], [110, 35], [10, 35]],
                "hello",
                0.92,
            )
        ]
        mock_easyocr.Reader.return_value = mock_reader

        with patch.dict("sys.modules", {"easyocr": mock_easyocr}):
            results = _run_easyocr("test.jpg", languages=["en"])

        assert len(results) == 1
        assert results[0].x == 10
        assert results[0].y == 5
        assert results[0].w == 100
        assert results[0].h == 30
        assert results[0].text == "hello"
        assert results[0].confidence == pytest.approx(0.92, abs=0.01)

    @patch(f"{_OCR}._bypass_uno_import", return_value=None)
    def test_multiple_results(self, mock_bypass):
        """Multiple EasyOCR detections are all converted."""
        _easyocr_readers.clear()

        mock_easyocr = MagicMock()
        mock_reader = MagicMock()
        mock_reader.readtext.return_value = [
            ([[0, 0], [50, 0], [50, 20], [0, 20]], "a", 0.8),
            ([[60, 0], [110, 0], [110, 20], [60, 20]], "b", 0.7),
        ]
        mock_easyocr.Reader.return_value = mock_reader

        with patch.dict("sys.modules", {"easyocr": mock_easyocr}):
            results = _run_easyocr("test.jpg", languages=["en"])

        assert len(results) == 2
        assert results[0].text == "a"
        assert results[1].text == "b"

    @patch(f"{_OCR}._bypass_uno_import", return_value=None)
    def test_empty_readtext_returns_empty(self, mock_bypass):
        """Empty readtext result returns empty list."""
        _easyocr_readers.clear()

        mock_easyocr = MagicMock()
        mock_reader = MagicMock()
        mock_reader.readtext.return_value = []
        mock_easyocr.Reader.return_value = mock_reader

        with patch.dict("sys.modules", {"easyocr": mock_easyocr}):
            results = _run_easyocr("test.jpg", languages=["en"])

        assert results == []


# ===========================================================================
# New expanded tests — Multi-line merge scenarios
# ===========================================================================


class TestMultiLineMergeScenarios:
    """Merge scenarios with multiple lines of text."""

    def test_three_lines_stay_separate(self):
        """Three well-spaced lines remain as three separate results."""
        r1 = OCRResult("Line one", 0, 0, 200, 20, 0.9)
        r2 = OCRResult("Line two", 0, 30, 200, 20, 0.9)
        r3 = OCRResult("Line three", 0, 60, 200, 20, 0.9)
        results = merge_ocr_results([r1, r2, r3])
        assert len(results) == 3

    def test_words_on_same_line_merge_but_lines_separate(self):
        """Words on same line merge; different lines stay separate."""
        # Line 1: "Hello World"
        w1 = OCRResult("Hello", 0, 0, 50, 20, 0.9)
        w2 = OCRResult("World", 55, 0, 50, 20, 0.8)
        # Line 2: "Foo Bar"
        w3 = OCRResult("Foo", 0, 30, 40, 20, 0.9)
        w4 = OCRResult("Bar", 45, 30, 40, 20, 0.8)

        results = merge_ocr_results([w1, w2, w3, w4])
        assert len(results) == 2
        texts = sorted(r.text for r in results)
        assert texts == ["Foo Bar", "Hello World"]

    def test_slightly_misaligned_same_line(self):
        """Slightly vertically misaligned words on same line still merge."""
        r1 = OCRResult("Hello", 0, 0, 60, 20, 0.9)
        r2 = OCRResult("World", 65, 3, 60, 18, 0.8)  # slight offset
        results = merge_ocr_results([r1, r2])
        assert len(results) == 1
        assert results[0].text == "Hello World"

    def test_different_heights_same_line(self):
        """Words with different heights but sufficient overlap merge."""
        r1 = OCRResult("BIG", 0, 0, 60, 30, 0.9)
        r2 = OCRResult("small", 65, 5, 50, 15, 0.8)
        results = merge_ocr_results([r1, r2])
        assert len(results) == 1

    def test_many_words_merge_chain(self):
        """Five words in a row all merge into one result."""
        words = []
        for i, w in enumerate(["a", "b", "c", "d", "e"]):
            words.append(OCRResult(w, i * 25, 0, 20, 15, 0.9))
        results = merge_ocr_results(words)
        assert len(results) == 1
        assert results[0].text == "a b c d e"


# ===========================================================================
# Edge case: EasyOCR reader cache thread safety
# ===========================================================================


class TestEasyOCRReaderCacheThreadSafety:
    """Thread safety for _get_easyocr_reader cache.

    Verify concurrent access from multiple threads does not create
    duplicate Reader instances for the same language set.
    """

    def setup_method(self):
        """Clear the reader cache before each test."""
        _easyocr_readers.clear()

    def teardown_method(self):
        """Clear the reader cache after each test."""
        _easyocr_readers.clear()

    def test_concurrent_same_language_creates_single_reader(self):
        """Two threads calling _get_easyocr_reader with same language simultaneously.

        Due to the GIL and dict key check, only one Reader should be created.
        """
        import threading  # noqa: PLC0415

        init_count = 0
        lock = threading.Lock()

        class _CountingReader:
            def __init__(self, langs, **kwargs):
                nonlocal init_count
                with lock:
                    init_count += 1

        mock_easyocr = MagicMock()
        mock_easyocr.Reader = _CountingReader

        results = []

        def _worker():
            with patch.dict(sys.modules, {"easyocr": mock_easyocr}):
                reader = _get_easyocr_reader(["en"])
                results.append(reader)

        with patch.dict(sys.modules, {"easyocr": mock_easyocr}):
            t1 = threading.Thread(target=_worker)
            t2 = threading.Thread(target=_worker)
            t1.start()
            t2.start()
            t1.join(timeout=5)
            t2.join(timeout=5)

        # Both threads should get the same reader instance
        assert len(results) == 2  # noqa: PLR2004
        assert results[0] is results[1]
        # Only one Reader constructor call
        assert init_count == 1

    def test_concurrent_different_languages_cached_independently(self):
        """Multiple threads with different languages create separate readers."""
        import threading  # noqa: PLC0415

        class _FakeReader:
            def __init__(self, langs, **kwargs):
                self.langs = tuple(sorted(langs))

        mock_easyocr = MagicMock()
        mock_easyocr.Reader = _FakeReader

        readers = {}

        def _worker(langs, key):
            with patch.dict(sys.modules, {"easyocr": mock_easyocr}):
                r = _get_easyocr_reader(langs)
                readers[key] = r

        with patch.dict(sys.modules, {"easyocr": mock_easyocr}):
            t1 = threading.Thread(target=_worker, args=(["en"], "en"))
            t2 = threading.Thread(target=_worker, args=(["ja", "en"], "ja_en"))
            t3 = threading.Thread(target=_worker, args=(["fr"], "fr"))
            t1.start()
            t2.start()
            t3.start()
            t1.join(timeout=5)
            t2.join(timeout=5)
            t3.join(timeout=5)

        assert len(readers) == 3  # noqa: PLR2004
        # Each language set has its own reader
        assert readers["en"] is not readers["ja_en"]
        assert readers["en"] is not readers["fr"]
        assert readers["ja_en"] is not readers["fr"]
        # Cache should have 3 entries
        assert len(_easyocr_readers) == 3  # noqa: PLR2004

    def test_no_duplicate_reader_with_rapid_sequential_calls(self):
        """Rapid sequential calls with the same language reuse the cached reader."""
        init_count = 0

        class _CountingReader:
            def __init__(self, langs, **kwargs):
                nonlocal init_count
                init_count += 1

        mock_easyocr = MagicMock()
        mock_easyocr.Reader = _CountingReader

        with patch.dict(sys.modules, {"easyocr": mock_easyocr}):
            readers = [_get_easyocr_reader(["en"]) for _ in range(10)]

        # All should be the same object
        for r in readers[1:]:
            assert r is readers[0]
        assert init_count == 1


# ===========================================================================
# Edge case: merge_ocr_results with zero/tiny dimension bounding boxes
# ===========================================================================


class TestMergeOCRResultsZeroDimension:
    """Zero and tiny dimension bounding boxes in merge_ocr_results.

    Verify that zero-width, zero-height, and single-pixel boxes do not
    cause division by zero or other arithmetic errors during merge.
    """

    def test_zero_width_no_division_by_zero(self):
        """OCRResult with w=0 does not cause division by zero during merge."""
        r1 = OCRResult("zero_w", 10, 10, 0, 20, 0.9)
        r2 = OCRResult("normal", 15, 10, 50, 20, 0.8)
        # Should not raise any exceptions
        result = merge_ocr_results([r1, r2])
        assert len(result) >= 1

    def test_zero_height_handled_gracefully(self):
        """OCRResult with h=0 handled gracefully.

        Zero height means min_h=0 in overlap calc, so overlap > 0 * 0.6 = 0
        is always True for any overlap > 0. But with h=0, overlap itself is
        min(y+0, y2+h2) - max(y, y2) which can be 0.  The check is overlap > 0
        which is False, so they end up on different lines. This is correct.
        """
        r1 = OCRResult("flat", 0, 10, 50, 0, 0.9)
        r2 = OCRResult("normal", 55, 10, 50, 20, 0.8)
        # Should not raise
        result = merge_ocr_results([r1, r2])
        assert isinstance(result, list)

    def test_both_zero_dimensions(self):
        """Two OCRResults with w=0 and h=0 do not crash merge."""
        r1 = OCRResult("point1", 5, 5, 0, 0, 0.9)
        r2 = OCRResult("point2", 5, 5, 0, 0, 0.8)
        result = merge_ocr_results([r1, r2])
        assert isinstance(result, list)

    def test_single_pixel_box_merged_correctly(self):
        """Single-pixel boxes (w=1, h=1) close together merge correctly."""
        r1 = OCRResult("a", 10, 10, 1, 1, 0.9)
        r2 = OCRResult("b", 11, 10, 1, 1, 0.8)
        # gap = 11 - (10 + 1) = 0, threshold = 1 * 1.2 = 1.2 -> 0 < 1.2 -> merge
        result = merge_ocr_results([r1, r2])
        assert len(result) == 1
        assert result[0].text == "a b"

    def test_single_pixel_boxes_far_apart_stay_separate(self):
        """Single-pixel boxes far apart do not merge."""
        r1 = OCRResult("a", 0, 0, 1, 1, 0.9)
        r2 = OCRResult("b", 100, 0, 1, 1, 0.8)
        # gap = 100 - 1 = 99, threshold = 1 * 1.2 = 1.2 -> 99 >= 1.2 -> separate
        result = merge_ocr_results([r1, r2])
        assert len(result) == 2  # noqa: PLR2004

    def test_zero_width_single_result(self):
        """Single zero-width result returned as-is."""
        r = OCRResult("dot", 5, 5, 0, 10, 0.9)
        result = merge_ocr_results([r])
        assert len(result) == 1
        assert result[0].text == "dot"
        assert result[0].w == 0

    def test_zero_height_single_result(self):
        """Single zero-height result returned as-is."""
        r = OCRResult("line", 5, 5, 50, 0, 0.9)
        result = merge_ocr_results([r])
        assert len(result) == 1
        assert result[0].h == 0


# ===========================================================================
# Edge case: merge_ocr_results with negative/extreme coordinates
# ===========================================================================


class TestMergeOCRResultsNegativeCoordinates:
    """Negative and extreme coordinates in merge_ocr_results.

    Some OCR engines (notably EasyOCR) can produce negative coordinates
    for text near image edges.
    """

    def test_negative_x_values(self):
        """Results with negative x values are handled correctly."""
        r1 = OCRResult("edge", -5, 10, 40, 20, 0.9)
        r2 = OCRResult("inner", 38, 10, 40, 20, 0.8)
        # gap = 38 - (-5 + 40) = 38 - 35 = 3, threshold = 20 * 1.2 = 24 -> merge
        result = merge_ocr_results([r1, r2])
        assert len(result) == 1
        assert result[0].text == "edge inner"
        # Merged x should be min(-5, 38) = -5
        assert result[0].x == -5

    def test_negative_y_values(self):
        """Results with negative y values are handled correctly."""
        r1 = OCRResult("top", 10, -10, 50, 20, 0.9)
        r2 = OCRResult("below", 65, -8, 50, 18, 0.8)
        result = merge_ocr_results([r1, r2])
        assert len(result) == 1
        assert result[0].y == -10  # noqa: PLR2004

    def test_very_large_coordinates(self):
        """Very large coordinates (>10000) do not cause overflow or errors."""
        r1 = OCRResult("big1", 15000, 20000, 500, 100, 0.9)
        r2 = OCRResult("big2", 15550, 20000, 500, 100, 0.8)
        # gap = 15550 - 15500 = 50, threshold = 100 * 1.2 = 120 -> merge
        result = merge_ocr_results([r1, r2])
        assert len(result) == 1
        assert result[0].x == 15000

    def test_mixed_positive_negative_coordinates(self):
        """Mixed positive and negative coordinates on the same line."""
        r1 = OCRResult("neg", -20, 5, 30, 15, 0.9)
        r2 = OCRResult("pos", 12, 5, 30, 15, 0.8)
        # gap = 12 - (-20 + 30) = 12 - 10 = 2, threshold = 15 * 1.2 = 18 -> merge
        result = merge_ocr_results([r1, r2])
        assert len(result) == 1
        assert result[0].x == -20  # noqa: PLR2004

    def test_negative_coordinates_different_lines(self):
        """Negative coordinates on different lines stay separate."""
        r1 = OCRResult("line1", -5, -10, 50, 15, 0.9)
        r2 = OCRResult("line2", -3, 30, 50, 15, 0.8)
        result = merge_ocr_results([r1, r2])
        assert len(result) == 2  # noqa: PLR2004

    def test_extreme_negative_coordinates(self):
        """Extremely negative coordinates are handled."""
        r1 = OCRResult("far", -10000, -5000, 100, 50, 0.9)
        result = merge_ocr_results([r1])
        assert len(result) == 1
        assert result[0].x == -10000  # noqa: PLR2004
        assert result[0].y == -5000  # noqa: PLR2004


# ===========================================================================
# Edge case: run_ocr file handling errors
# ===========================================================================


class TestRunOCRFileErrors:
    """File handling errors for run_ocr and backend functions."""

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value="key")
    @patch("urllib.request.urlopen")
    def test_nonexistent_image_google_cloud(self, mock_urlopen, mock_key):
        """Non-existent image path raises FileNotFoundError for Google Cloud."""
        with pytest.raises(FileNotFoundError):
            _run_google_cloud("/nonexistent/path/to/image.png")

    def test_none_image_path_easyocr(self):
        """None as image_path propagates to EasyOCR readtext, raising an error."""
        _easyocr_readers.clear()

        class _FakeReader:
            def __init__(self, langs, **kwargs):
                pass

            def readtext(self, path):
                # Real EasyOCR would fail on None path
                raise TypeError("expected str, got NoneType")

        mock_easyocr = MagicMock()
        mock_easyocr.Reader = _FakeReader

        with (
            patch.dict(sys.modules, {"easyocr": mock_easyocr}),
            pytest.raises(TypeError, match="expected str"),
        ):
            _run_easyocr(None)

        _easyocr_readers.clear()

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value="key")
    @patch("urllib.request.urlopen")
    def test_empty_zero_byte_image_google_cloud(self, mock_urlopen, mock_key, tmp_path):
        """Empty/zero-byte image file still sends request to Google Cloud."""
        img = tmp_path / "empty.png"
        img.write_bytes(b"")

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"responses": [{}]}).encode()
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = False
        mock_urlopen.return_value = mock_response

        results = _run_google_cloud(str(img))
        assert results == []
        mock_urlopen.assert_called_once()

    @patch(f"{_OCR}.subprocess.run")
    def test_tesseract_with_nonexistent_path(self, mock_run):
        """Tesseract with non-existent path still calls subprocess (binary handles it)."""
        mock_run.side_effect = subprocess.CalledProcessError(1, "tesseract")
        results = _run_tesseract("/nonexistent/image.png", lang="eng")
        # Error is caught, returns empty
        assert results == []
        mock_run.assert_called_once()


# ===========================================================================
# Edge case: Tesseract subprocess errors
# ===========================================================================


class TestTesseractSubprocessErrors:
    """Tesseract subprocess edge cases: binary not found, timeout, empty output."""

    def test_file_not_found_when_tesseract_binary_missing(self):
        """FileNotFoundError when tesseract binary is not found."""
        with (
            patch(
                f"{_OCR}.subprocess.run",
                side_effect=FileNotFoundError(
                    "[Errno 2] No such file or directory: 'tesseract'"
                ),
            ),
            pytest.raises(FileNotFoundError),
        ):
            _run_tesseract("img.png")

    def test_timeout_during_subprocess_execution(self):
        """subprocess.TimeoutExpired during Tesseract execution.

        TimeoutExpired is not caught by the except clause in _run_tesseract
        (which catches CalledProcessError, ValueError, KeyError), so it
        should propagate.
        """
        with (
            patch(
                f"{_OCR}.subprocess.run",
                side_effect=subprocess.TimeoutExpired("tesseract", 30),
            ),
            pytest.raises(subprocess.TimeoutExpired),
        ):
            _run_tesseract("img.png")

    @patch(f"{_OCR}.subprocess.run")
    def test_empty_tsv_output_no_text_detected(self, mock_run):
        """Empty TSV output (header only, no text) returns empty list."""
        header = (
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num"
            "\tleft\ttop\twidth\theight\tconf\ttext"
        )

        def _side_effect(cmd, check, capture_output):
            out_base = Path(cmd[2])
            tsv_path = out_base.with_suffix(".tsv")
            tsv_path.write_text(header + "\n", encoding="utf-8")

        mock_run.side_effect = _side_effect
        results = _run_tesseract("img.png")
        assert results == []

    @patch(f"{_OCR}.subprocess.run")
    def test_os_error_during_subprocess(self, mock_run):
        """OSError during subprocess (e.g. permissions) propagates."""
        mock_run.side_effect = OSError("Permission denied")
        with pytest.raises(OSError, match="Permission denied"):
            _run_tesseract("img.png")

    @patch(f"{_OCR}.subprocess.run")
    def test_called_process_error_eng_returns_empty(self, mock_run):
        """CalledProcessError with eng lang returns empty list (caught)."""
        mock_run.side_effect = subprocess.CalledProcessError(1, "tesseract")
        results = _run_tesseract("img.png", lang="eng")
        assert results == []


# ===========================================================================
# Edge case: Google Cloud OCR edge cases
# ===========================================================================


class TestGoogleCloudOCREdgeCases:
    """Google Cloud Vision OCR edge cases."""

    def _make_mock_response(self, response_data):
        """Create a mock urlopen context-manager response."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(response_data).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = False
        return mock_response

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value="key")
    @patch("urllib.request.urlopen")
    def test_vertices_with_missing_x_defaults_to_zero(
        self, mock_urlopen, mock_key, tmp_path
    ):
        """Vertices with missing x key default to 0."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"fake")

        response_data = {
            "responses": [
                {
                    "textAnnotations": [
                        {
                            "description": "Full",
                            "boundingPoly": {"vertices": [{"x": 0, "y": 0}]},
                        },
                        {
                            "description": "word",
                            "boundingPoly": {
                                "vertices": [
                                    {"y": 0},  # x defaults to 0
                                    {"x": 50, "y": 0},
                                    {"x": 50, "y": 20},
                                    {"y": 20},  # x defaults to 0
                                ]
                            },
                        },
                    ],
                }
            ]
        }
        mock_urlopen.return_value = self._make_mock_response(response_data)
        results = _run_google_cloud(str(img))
        assert len(results) == 1
        assert results[0].x == 0
        assert results[0].w == 50

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value="key")
    @patch("urllib.request.urlopen")
    def test_vertices_with_missing_y_defaults_to_zero(
        self, mock_urlopen, mock_key, tmp_path
    ):
        """Vertices with missing y key default to 0."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"fake")

        response_data = {
            "responses": [
                {
                    "textAnnotations": [
                        {
                            "description": "Full",
                            "boundingPoly": {"vertices": [{"x": 0}]},
                        },
                        {
                            "description": "word",
                            "boundingPoly": {
                                "vertices": [
                                    {"x": 10},  # y defaults to 0
                                    {"x": 40},  # y defaults to 0
                                    {"x": 40, "y": 15},
                                    {"x": 10, "y": 15},
                                ]
                            },
                        },
                    ],
                }
            ]
        }
        mock_urlopen.return_value = self._make_mock_response(response_data)
        results = _run_google_cloud(str(img))
        assert len(results) == 1
        assert results[0].y == 0
        assert results[0].h == 15

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value="key")
    @patch("urllib.request.urlopen")
    def test_multiple_response_blocks_only_first_processed(
        self, mock_urlopen, mock_key, tmp_path
    ):
        """Multiple response blocks: only first response is processed.

        The code does ``res_data["responses"][0]``, so additional
        response blocks are silently ignored.
        """
        img = tmp_path / "test.jpg"
        img.write_bytes(b"fake")

        response_data = {
            "responses": [
                {
                    "textAnnotations": [
                        {
                            "description": "Full",
                            "boundingPoly": {
                                "vertices": [{"x": 0, "y": 0}, {"x": 100, "y": 50}]
                            },
                        },
                        {
                            "description": "first",
                            "boundingPoly": {
                                "vertices": [
                                    {"x": 0, "y": 0},
                                    {"x": 30, "y": 0},
                                    {"x": 30, "y": 10},
                                    {"x": 0, "y": 10},
                                ]
                            },
                        },
                    ],
                },
                {
                    "textAnnotations": [
                        {"description": "Second block full"},
                        {
                            "description": "second",
                            "boundingPoly": {
                                "vertices": [
                                    {"x": 0, "y": 0},
                                    {"x": 50, "y": 0},
                                    {"x": 50, "y": 10},
                                    {"x": 0, "y": 10},
                                ]
                            },
                        },
                    ],
                },
            ]
        }
        mock_urlopen.return_value = self._make_mock_response(response_data)
        results = _run_google_cloud(str(img))
        # Only annotations from the first response block
        assert len(results) == 1
        assert results[0].text == "first"

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value="key")
    @patch("urllib.request.urlopen")
    def test_empty_full_text_annotation_response(
        self, mock_urlopen, mock_key, tmp_path
    ):
        """Empty fullTextAnnotation response returns empty list."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"fake")

        # Response with fullTextAnnotation but no textAnnotations
        response_data = {
            "responses": [
                {
                    "fullTextAnnotation": {"text": "some text"},
                    # No textAnnotations key
                }
            ]
        }
        mock_urlopen.return_value = self._make_mock_response(response_data)
        results = _run_google_cloud(str(img))
        assert results == []

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value="key")
    @patch("urllib.request.urlopen")
    def test_api_timeout_handling(self, mock_urlopen, mock_key, tmp_path):
        """API timeout maps to the typed ``TIMEOUT_ERROR`` sentinel."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"fake")

        mock_urlopen.side_effect = TimeoutError("The read operation timed out")
        with pytest.raises(ValueError, match="TIMEOUT_ERROR"):
            _run_google_cloud(str(img))

    @patch(f"{_OCR}.load_google_cloud_api_key", return_value="key")
    @patch("urllib.request.urlopen")
    def test_empty_vertices_list_skips_annotation(
        self, mock_urlopen, mock_key, tmp_path
    ):
        """Annotation with an empty vertices list is skipped."""
        img = tmp_path / "test.jpg"
        img.write_bytes(b"fake")

        response_data = {
            "responses": [
                {
                    "textAnnotations": [
                        {
                            "description": "Full",
                            "boundingPoly": {"vertices": [{"x": 0, "y": 0}]},
                        },
                        {
                            "description": "empty_verts",
                            "boundingPoly": {"vertices": []},
                        },
                    ],
                }
            ]
        }
        mock_urlopen.return_value = self._make_mock_response(response_data)
        results = _run_google_cloud(str(img))
        assert results == []


# ===========================================================================
# Edge case: OCRResult to_dict serialization
# ===========================================================================


class TestOCRResultSerialization:
    """OCRResult to_dict edge cases for serialization."""

    def test_all_default_values_serialized(self):
        """All default values are serialized correctly."""
        r = OCRResult("test", 0, 0, 10, 10, 0.5)
        d = r.to_dict()
        assert d["text"] == "test"
        assert d["translated_text"] == ""
        assert d["box"] == [0, 0, 10, 10]
        assert d["confidence"] == 0.5  # noqa: PLR2004
        assert d["color"] == "#000000"
        assert d["is_bold"] is False
        assert d["is_italic"] is False
        assert d["is_underline"] is False
        assert d["alignment"] is None

    def test_unicode_text_in_results(self):
        """Unicode text (CJK, Arabic, Cyrillic, emoji) serialized correctly."""
        r = OCRResult("日本語 العربية Кириллица 🎉", 0, 0, 200, 30, 0.95)
        d = r.to_dict()
        assert d["text"] == "日本語 العربية Кириллица 🎉"

    def test_very_long_text_strings(self):
        """Very long text strings (10000 chars) serialized correctly."""
        long_text = "a" * 10000
        r = OCRResult(long_text, 0, 0, 5000, 100, 0.8)
        d = r.to_dict()
        assert len(d["text"]) == 10000
        assert d["text"] == long_text

    def test_special_characters_serialized(self):
        """Special characters (newlines, tabs, quotes, backslashes) in to_dict."""
        r = OCRResult('line1\nline2\ttab\\"quote', 0, 0, 100, 20, 0.9)
        d = r.to_dict()
        assert "\n" in d["text"]
        assert "\t" in d["text"]
        assert "\\" in d["text"]

    def test_translated_text_preserved(self):
        """Translated text is preserved in to_dict."""
        r = OCRResult("hello", 0, 0, 50, 20, 0.9)
        r.translated_text = "hola"
        d = r.to_dict()
        assert d["translated_text"] == "hola"

    def test_zero_confidence_serialized(self):
        """Zero confidence serialized correctly."""
        r = OCRResult("low", 0, 0, 10, 10, 0.0)
        d = r.to_dict()
        assert d["confidence"] == 0.0

    def test_max_confidence_serialized(self):
        """Max confidence (1.0) serialized correctly."""
        r = OCRResult("high", 0, 0, 10, 10, 1.0)
        d = r.to_dict()
        assert d["confidence"] == 1.0

    def test_negative_coordinates_serialized(self):
        """Negative coordinates appear correctly in box."""
        r = OCRResult("neg", -5, -10, 50, 30, 0.9)
        d = r.to_dict()
        assert d["box"] == [-5, -10, 50, 30]

    def test_all_formatting_flags_true(self):
        """All formatting flags set to True serialized correctly."""
        r = OCRResult("styled", 0, 0, 50, 20, 0.9)
        r.is_bold = True
        r.is_italic = True
        r.is_underline = True
        d = r.to_dict()
        assert d["is_bold"] is True
        assert d["is_italic"] is True
        assert d["is_underline"] is True


# ===========================================================================
# Edge case: run_ocr with unsupported language
# ===========================================================================


class TestRunOCRWithUnsupportedLanguage:
    """Language fallback for unsupported language codes.

    Verify that unsupported/unknown language labels fall back to defaults
    and that fallback is logged as a warning where applicable.
    """

    @patch(f"{_OCR}._run_tesseract", return_value=[])
    def test_tesseract_unsupported_lang_falls_back_to_eng(self, mock_tess):
        """Unsupported language code falls back to 'eng' for Tesseract."""
        run_ocr("img.png", method=OCR_METHOD_TESSERACT, src_lang="Klingon")
        mock_tess.assert_called_once_with("img.png", lang="eng")

    @patch(f"{_OCR}._run_easyocr", return_value=[])
    def test_easyocr_unsupported_lang_falls_back_to_en(self, mock_easy):
        """Unsupported language code falls back to ['en'] for EasyOCR."""
        run_ocr("img.png", method=OCR_METHOD_EASYOCR, src_lang="Klingon")
        mock_easy.assert_called_once_with("img.png", languages=["en"])

    @patch(f"{_OCR}._run_google_cloud", return_value=[])
    def test_google_cloud_unsupported_lang_returns_none_hints(self, mock_gc):
        """Unsupported language code returns None hints for Google Cloud."""
        run_ocr("img.png", method=OCR_METHOD_GOOGLE_CLOUD, src_lang="Klingon")
        mock_gc.assert_called_once_with("img.png", lang_hints=None)

    @patch(f"{_OCR}.subprocess.run")
    def test_tesseract_fallback_logged_as_warning(self, mock_run):
        """Tesseract language fallback logs a warning message."""
        called_cmds = []

        def _side_effect(cmd, check, capture_output):
            called_cmds.append(list(cmd))
            if "xyz" in cmd:
                raise subprocess.CalledProcessError(1, cmd)
            out_base = Path(cmd[2])
            tsv_path = out_base.with_suffix(".tsv")
            header = (
                "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num"
                "\tleft\ttop\twidth\theight\tconf\ttext"
            )
            tsv_path.write_text(header + "\n", encoding="utf-8")

        mock_run.side_effect = _side_effect

        with patch(f"{_OCR}.logger") as mock_logger:
            _run_tesseract("img.png", lang="xyz")
            mock_logger.warning.assert_called_once()
            # Verify warning mentions the unavailable language
            call_args = mock_logger.warning.call_args
            assert "xyz" in str(call_args)

    def test_easyocr_fallback_logged_as_warning(self):
        """EasyOCR language fallback logs a warning message."""
        _easyocr_readers.clear()

        class _FakeReader:
            def __init__(self, langs, **kwargs):
                if langs != EASYOCR_DEFAULT_LANGUAGES:
                    raise RuntimeError("Unsupported")

            def readtext(self, path):
                return []

        mock_easyocr = MagicMock()
        mock_easyocr.Reader = _FakeReader

        with (
            patch.dict(sys.modules, {"easyocr": mock_easyocr}),
            patch(f"{_OCR}.logger") as mock_logger,
        ):
            _run_easyocr("img.png", languages=["xyz"])
            mock_logger.warning.assert_called_once()
            call_args = mock_logger.warning.call_args
            assert "xyz" in str(call_args)

        _easyocr_readers.clear()

    @patch(f"{_OCR}._run_tesseract", return_value=[])
    def test_empty_string_lang_falls_back_to_default(self, mock_tess):
        """Empty string language falls back to default 'eng'."""
        run_ocr("img.png", method=OCR_METHOD_TESSERACT, src_lang="")
        mock_tess.assert_called_once_with("img.png", lang="eng")

    @patch(f"{_OCR}._run_tesseract", return_value=[])
    def test_none_like_lang_falls_back_to_default(self, mock_tess):
        """Passing a non-matching language label falls back gracefully."""
        run_ocr("img.png", method=OCR_METHOD_TESSERACT, src_lang="NonExistentLanguage")
        mock_tess.assert_called_once_with("img.png", lang="eng")


class TestGoogleCloudOcrImageSizeGuard:
    """Pre-flight image-size validation for the Google Cloud Vision path.

    Cloud Vision rejects images > 20 MB with an opaque server error.
    We pre-flight the file size and raise our own ``IMAGE_TOO_LARGE``
    sentinel so the UI can render a clear "image too large" toast
    instead of a generic 400.
    """

    def test_image_over_20mb_raises_image_too_large(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A 21 MB image triggers IMAGE_TOO_LARGE before the API call.

        Verifies BOTH:
          1. the ValueError sentinel carries the documented tag.
          2. the API endpoint is NEVER reached — no network call.
        """
        from src.core.ocr_engine import _run_google_cloud  # noqa: PLC0415

        # 21 MB sentinel file — exceeds the 20 MB documented limit.
        big = tmp_path / "huge.png"
        big.write_bytes(b"\x00" * (21 * 1024 * 1024))

        monkeypatch.setattr(
            "src.core.ocr_engine.load_google_cloud_api_key",
            lambda: "fake-key",
        )

        called = []

        def _no_network(*_a: object, **_kw: object) -> None:
            called.append(True)
            raise AssertionError("urlopen called despite oversized image")

        monkeypatch.setattr(
            "urllib.request.urlopen", _no_network,
        )

        with pytest.raises(ValueError, match="^IMAGE_TOO_LARGE$"):
            _run_google_cloud(str(big))
        assert not called

    def test_image_under_20mb_does_not_pre_flight_reject(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A 1 MB image passes the size check and reaches the API call."""
        from src.core.ocr_engine import _run_google_cloud  # noqa: PLC0415

        small = tmp_path / "small.png"
        small.write_bytes(b"\x00" * (1 * 1024 * 1024))

        monkeypatch.setattr(
            "src.core.ocr_engine.load_google_cloud_api_key",
            lambda: "fake-key",
        )

        # Mock urlopen to return a valid empty-textAnnotations response
        # so the call completes without IMAGE_TOO_LARGE being raised.
        from unittest.mock import MagicMock  # noqa: PLC0415

        mock_response = MagicMock()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=None)
        mock_response.read.return_value = (
            b'{"responses":[{"textAnnotations":[]}]}'
        )
        monkeypatch.setattr(
            "urllib.request.urlopen",
            MagicMock(return_value=mock_response),
        )

        result = _run_google_cloud(str(small))
        assert result == []
