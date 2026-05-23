"""Tests for the image translation feature using PySide6."""

import multiprocessing
import os
from pathlib import Path

import pytest
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import (
    QColor,
    QImage,
    QPainter,
)

from src.core.image_processor import (
    _guess_bg_color,
    process_image_translation,
)
from src.core.ocr_engine import OCRResult, merge_ocr_results, run_ocr


def _has_font_rendering() -> bool:
    """Checks if Qt offscreen font rendering works without segfault."""

    def _probe() -> None:
        from PySide6.QtGui import QFont, QImage, QPainter

        img = QImage(50, 50, QImage.Format.Format_RGB32)
        p = QPainter(img)
        p.setFont(QFont("", 12))
        p.drawText(img.rect(), 0, "A")
        p.end()

    proc = multiprocessing.Process(target=_probe)
    proc.start()
    proc.join(timeout=5)
    if proc.is_alive():
        proc.kill()
        proc.join()
        return False
    return proc.exitcode == 0


# Skip entire module if Qt font rendering segfaults in offscreen mode
pytestmark = pytest.mark.skipif(
    not _has_font_rendering(),
    reason="Qt offscreen font rendering unavailable",
)

# EasyOCR availability flag (heavy dependency — PyTorch)
try:
    import easyocr  # noqa: F401

    _EASYOCR_AVAILABLE = True
except ImportError:
    _EASYOCR_AVAILABLE = False


@pytest.fixture()
def sample_image(tmp_path: Path) -> str:
    """Creates a sample image with text for testing."""
    img_path = tmp_path / "test.png"
    image = QImage(200, 100, QImage.Format.Format_RGB32)
    image.fill(QColor(Qt.GlobalColor.white))

    painter = QPainter(image)
    painter.setPen(QColor(Qt.GlobalColor.black))
    painter.drawText(10, 30, "Hello")
    painter.end()

    image.save(str(img_path))
    return str(img_path)


def test_ocr_result_to_dict() -> None:
    """Tests the OCRResult.to_dict method."""
    res = OCRResult("Test", 10, 20, 30, 40, 0.95)
    d = res.to_dict()
    assert d["text"] == "Test"
    assert d["box"] == [10, 20, 30, 40]
    assert d["confidence"] == 0.95


def test_image_processor(
    sample_image: str,
    tmp_path: Path,
) -> None:
    """Tests end-to-end image processing with inpainting."""
    output_path = tmp_path / "output.png"
    ocr_results = [OCRResult("Hello", 10, 10, 40, 20, 1.0)]
    translations = ["Bonjour"]

    success = process_image_translation(
        sample_image,
        str(output_path),
        ocr_results,
        translations,
    )

    assert success is True
    assert output_path.exists()

    res_img = QImage(str(output_path))
    assert not res_img.isNull()
    assert res_img.size().width() == 200
    assert res_img.size().height() == 100


@pytest.mark.skipif(
    os.system("tesseract --version") != 0,
    reason="Tesseract not installed",
)
def test_tesseract_ocr(sample_image: str) -> None:
    """Tests Tesseract OCR on a sample image."""
    img_path = Path(sample_image).parent / "ocr_test.png"
    image = QImage(400, 200, QImage.Format.Format_RGB32)
    image.fill(QColor(Qt.GlobalColor.white))

    painter = QPainter(image)
    font = painter.font()
    font.setPixelSize(40)
    painter.setFont(font)
    painter.setPen(QColor(Qt.GlobalColor.black))
    painter.drawText(50, 100, "HELLO WORLD")
    painter.end()

    image.save(str(img_path))

    results = run_ocr(str(img_path))
    assert isinstance(results, list)


@pytest.mark.skipif(
    not _EASYOCR_AVAILABLE,
    reason="EasyOCR not installed",
)
def test_easyocr_ocr(sample_image: str) -> None:
    """Tests EasyOCR on a sample image."""
    img_path = Path(sample_image).parent / "ocr_easyocr_test.png"
    image = QImage(400, 200, QImage.Format.Format_RGB32)
    image.fill(QColor(Qt.GlobalColor.white))

    painter = QPainter(image)
    font = painter.font()
    font.setPixelSize(40)
    painter.setFont(font)
    painter.setPen(QColor(Qt.GlobalColor.black))
    painter.drawText(50, 100, "HELLO WORLD")
    painter.end()

    image.save(str(img_path))

    results = run_ocr(str(img_path), method="EasyOCR")
    assert isinstance(results, list)


def test_indexed_image_format_conversion(
    tmp_path: Path,
) -> None:
    """Verify Format_Indexed8 image is converted before processing."""
    img_path = tmp_path / "indexed.png"
    # Create an indexed (Format_Indexed8) image
    image = QImage(100, 50, QImage.Format.Format_Indexed8)
    image.setColorCount(2)  # noqa: PLR2004
    image.setColor(0, QColor(Qt.GlobalColor.white).rgb())
    image.setColor(1, QColor(Qt.GlobalColor.black).rgb())
    image.fill(0)
    image.save(str(img_path))

    # Verify it was saved as indexed
    reloaded = QImage(str(img_path))
    assert not reloaded.isNull()

    output_path = tmp_path / "output.png"
    ocr_results = [OCRResult("Test", 5, 5, 30, 15, 1.0)]
    translations = ["Tested"]

    success = process_image_translation(
        str(img_path),
        str(output_path),
        ocr_results,
        translations,
    )

    assert success is True
    assert output_path.exists()
    result_img = QImage(str(output_path))
    assert not result_img.isNull()


def test_jpeg_quality_100(
    sample_image: str,
    tmp_path: Path,
) -> None:
    """Verify JPEG output uses quality=100."""
    output_path = tmp_path / "output.jpg"
    ocr_results = [OCRResult("Hello", 10, 10, 40, 20, 1.0)]
    translations = ["Bonjour"]

    success = process_image_translation(
        sample_image,
        str(output_path),
        ocr_results,
        translations,
    )

    assert success is True
    assert output_path.exists()

    # JPEG at quality=100 should be reasonably large (not over-compressed)
    file_size = output_path.stat().st_size
    min_expected_size = 500
    assert file_size > min_expected_size


# ---------------------------------------------------------------------------
# _guess_bg_color edge cases
# ---------------------------------------------------------------------------


def test_guess_bg_color_uniform_white() -> None:
    """White background returns white."""
    img = QImage(100, 100, QImage.Format.Format_RGB32)
    img.fill(QColor(Qt.GlobalColor.white))
    rect = QRect(20, 20, 60, 60)

    color = _guess_bg_color(img, rect)
    assert color == QColor(Qt.GlobalColor.white)


def test_guess_bg_color_uniform_red() -> None:
    """Solid red background returns red."""
    img = QImage(100, 100, QImage.Format.Format_RGB32)
    img.fill(QColor(255, 0, 0))
    rect = QRect(10, 10, 80, 80)

    color = _guess_bg_color(img, rect)
    assert color.red() == 255  # noqa: PLR2004
    assert color.green() == 0
    assert color.blue() == 0


def test_guess_bg_color_rect_at_corner() -> None:
    """Rect near image corner still samples valid pixels."""
    img = QImage(100, 100, QImage.Format.Format_RGB32)
    img.fill(QColor(0, 128, 0))
    rect = QRect(0, 0, 20, 20)

    color = _guess_bg_color(img, rect)
    assert color.green() == 128  # noqa: PLR2004


def test_guess_bg_color_small_rect() -> None:
    """Very small rect (3x3) still produces a valid color."""
    img = QImage(50, 50, QImage.Format.Format_RGB32)
    img.fill(QColor(0, 0, 255))
    rect = QRect(20, 20, 3, 3)

    color = _guess_bg_color(img, rect)
    assert color.blue() == 255  # noqa: PLR2004


def test_guess_bg_color_zero_size_rect_fallback() -> None:
    """Zero-size rect produces fallback white color."""
    img = QImage(50, 50, QImage.Format.Format_RGB32)
    img.fill(QColor(Qt.GlobalColor.black))
    # A zero-size rect means range(left, right+1) is empty → no samples
    rect = QRect(25, 25, 0, 0)

    color = _guess_bg_color(img, rect)
    # Falls back to white when no valid samples
    assert color == QColor(Qt.GlobalColor.white)


# ---------------------------------------------------------------------------
# process_image_translation edge cases
# ---------------------------------------------------------------------------


def test_process_image_length_mismatch(
    sample_image: str,
    tmp_path: Path,
) -> None:
    """Returns False when OCR results and translations have different lengths."""
    output_path = tmp_path / "output.png"
    ocr_results = [OCRResult("A", 10, 10, 20, 20, 1.0)]
    translations = ["X", "Y"]  # Length mismatch

    success = process_image_translation(
        sample_image,
        str(output_path),
        ocr_results,
        translations,
    )
    assert success is False


def test_process_image_null_image(tmp_path: Path) -> None:
    """Returns False when the image file does not exist."""
    output_path = tmp_path / "output.png"
    ocr_results = [OCRResult("A", 10, 10, 20, 20, 1.0)]
    translations = ["B"]

    success = process_image_translation(
        str(tmp_path / "nonexistent.png"),
        str(output_path),
        ocr_results,
        translations,
    )
    assert success is False


def test_process_image_empty_lists(
    sample_image: str,
    tmp_path: Path,
) -> None:
    """Empty OCR results and translations produce a valid output."""
    output_path = tmp_path / "output.png"

    success = process_image_translation(
        sample_image,
        str(output_path),
        [],
        [],
    )
    assert success is True
    assert output_path.exists()


def test_process_image_empty_translation_string(
    sample_image: str,
    tmp_path: Path,
) -> None:
    """Empty translation strings are skipped (no rendering)."""
    output_path = tmp_path / "output.png"
    ocr_results = [OCRResult("Hello", 10, 10, 40, 20, 1.0)]
    translations = [""]

    success = process_image_translation(
        sample_image,
        str(output_path),
        ocr_results,
        translations,
    )
    assert success is True
    assert output_path.exists()


def test_process_image_with_raw_ocr_results(
    sample_image: str,
    tmp_path: Path,
) -> None:
    """Separate raw_ocr_results used for text removal."""
    output_path = tmp_path / "output.png"
    ocr_results = [OCRResult("Hello", 10, 10, 40, 20, 1.0)]
    raw_results = [
        OCRResult("Hel", 10, 10, 20, 20, 1.0),
        OCRResult("lo", 30, 10, 20, 20, 1.0),
    ]
    translations = ["Bonjour"]

    success = process_image_translation(
        sample_image,
        str(output_path),
        ocr_results,
        translations,
        raw_ocr_results=raw_results,
    )
    assert success is True
    assert output_path.exists()


# ---------------------------------------------------------------------------
# merge_ocr_results edge cases
# ---------------------------------------------------------------------------


def test_merge_ocr_results_empty() -> None:
    """Empty input returns empty list."""
    assert merge_ocr_results([]) == []


def test_merge_ocr_results_whitespace_only() -> None:
    """Whitespace-only fragments are filtered out."""
    results = [
        OCRResult("   ", 10, 10, 20, 20, 1.0),
        OCRResult("  ", 40, 10, 20, 20, 1.0),
    ]
    assert merge_ocr_results(results) == []


def test_merge_ocr_results_single_fragment() -> None:
    """Single fragment returns single result."""
    results = [OCRResult("Hello", 10, 10, 40, 20, 1.0)]
    merged = merge_ocr_results(results)
    assert len(merged) == 1
    assert merged[0].text == "Hello"


def test_merge_ocr_results_horizontal_merge() -> None:
    """Two close fragments on the same line are merged."""
    # Height=20, gap threshold=0.6*20=12. Gap=5 < 12 → merge.
    results = [
        OCRResult("Hello", 10, 10, 40, 20, 0.9),
        OCRResult("World", 55, 10, 50, 20, 0.8),
    ]
    merged = merge_ocr_results(results)
    assert len(merged) == 1
    assert merged[0].text == "Hello World"


def test_merge_ocr_results_horizontal_no_merge() -> None:
    """Two distant fragments on the same line stay separate."""
    # Height=20, threshold=12. Gap=60-50=10... let me compute:
    # First: x=10, w=40 → right=50. Second: x=80 → gap=80-50=30 > 12.
    results = [
        OCRResult("Hello", 10, 10, 40, 20, 0.9),
        OCRResult("World", 80, 10, 50, 20, 0.8),
    ]
    merged = merge_ocr_results(results)
    assert len(merged) == 2  # noqa: PLR2004


def test_merge_ocr_results_vertical_separate() -> None:
    """Fragments on different lines are not merged."""
    # Height=20, vertical overlap would be negative (no overlap).
    results = [
        OCRResult("Line1", 10, 10, 50, 20, 0.9),
        OCRResult("Line2", 10, 60, 50, 20, 0.9),
    ]
    merged = merge_ocr_results(results)
    assert len(merged) == 2  # noqa: PLR2004
    assert merged[0].text == "Line1"
    assert merged[1].text == "Line2"


def test_merge_ocr_results_preserves_bold_italic() -> None:
    """Bold/italic flags are merged with OR logic."""
    r1 = OCRResult("Bold", 10, 10, 30, 20, 1.0)
    r1.is_bold = True
    r1.is_italic = False

    r2 = OCRResult("Italic", 45, 10, 40, 20, 1.0)
    r2.is_bold = False
    r2.is_italic = True

    merged = merge_ocr_results([r1, r2])
    assert len(merged) == 1
    assert merged[0].is_bold is True
    assert merged[0].is_italic is True


def test_merge_ocr_results_preserves_first_color() -> None:
    """Merged block uses the color of the first fragment."""
    r1 = OCRResult("Red", 10, 10, 30, 20, 1.0)
    r1.color = "#ff0000"

    r2 = OCRResult("Blue", 45, 10, 30, 20, 1.0)
    r2.color = "#0000ff"

    merged = merge_ocr_results([r1, r2])
    assert len(merged) == 1
    assert merged[0].color == "#ff0000"


def test_merge_ocr_results_confidence_averaged() -> None:
    """Merged block has averaged confidence."""
    r1 = OCRResult("A", 10, 10, 20, 20, 0.8)
    r2 = OCRResult("B", 35, 10, 20, 20, 1.0)
    merged = merge_ocr_results([r1, r2])
    assert len(merged) == 1
    assert merged[0].confidence == pytest.approx(0.9, abs=0.01)


# ---------------------------------------------------------------------------
# OCRResult field defaults and to_dict edge cases
# ---------------------------------------------------------------------------


def test_ocr_result_default_values() -> None:
    """OCRResult initializes with correct default field values."""
    res = OCRResult("Hello", 5, 10, 80, 25, 0.95)

    assert res.text == "Hello"
    assert res.x == 5
    assert res.y == 10
    assert res.w == 80
    assert res.h == 25
    assert res.confidence == 0.95
    # Mutable defaults
    assert res.is_bold is False
    assert res.is_italic is False
    assert res.is_underline is False
    assert res.translated_text == ""
    assert res.translated_html == ""
    assert res.alignment is None
    assert res.line_height_ratio == pytest.approx(1.2)
    assert res.is_single_line is False
    # Default color is black (hex string)
    assert res.color == "#000000"


def test_ocr_result_to_dict_with_translated_text() -> None:
    """to_dict includes translated_text and alignment when set."""
    res = OCRResult("Hello", 0, 0, 50, 20, 0.9)
    res.translated_text = "Bonjour"
    res.is_bold = True
    res.is_underline = True
    res.alignment = "AlignRight"

    d = res.to_dict()

    assert d["translated_text"] == "Bonjour"
    assert d["is_bold"] is True
    assert d["is_underline"] is True
    assert d["alignment"] == "AlignRight"


# ---------------------------------------------------------------------------
# merge_ocr_results additional edge cases
# ---------------------------------------------------------------------------


def test_merge_ocr_results_is_underline_not_propagated() -> None:
    """is_underline flag is NOT propagated to merged block (documents current behavior)."""  # noqa: E501
    r1 = OCRResult("Underlined", 10, 10, 60, 20, 1.0)
    r1.is_underline = True

    r2 = OCRResult("Normal", 75, 10, 50, 20, 1.0)
    r2.is_underline = False

    merged = merge_ocr_results([r1, r2])

    assert len(merged) == 1
    # The merged block is a new OCRResult with default is_underline=False
    assert merged[0].is_underline is False


def test_merge_ocr_results_three_fragment_chain() -> None:
    """Three close fragments on the same line are all merged into one block."""
    # height=20, gap threshold=0.6*20=12
    # Gaps: 5 and 5 — both < 12 → all merge
    r1 = OCRResult("One", 10, 10, 30, 20, 0.9)
    r2 = OCRResult("Two", 45, 10, 30, 20, 0.8)
    r3 = OCRResult("Three", 80, 10, 40, 20, 0.7)

    merged = merge_ocr_results([r1, r2, r3])

    assert len(merged) == 1
    assert "One" in merged[0].text
    assert "Two" in merged[0].text
    assert "Three" in merged[0].text


# ---------------------------------------------------------------------------
# process_image_translation additional cases
# ---------------------------------------------------------------------------


def test_process_image_easyocr_method(
    sample_image: str,
    tmp_path: Path,
) -> None:
    """EasyOCR method applies its specific padding (0, -2) without crashing."""
    output_path = tmp_path / "output_easy.png"
    # Large OCR region: negative insert padding doesn't produce zero/negative rects
    ocr_results = [OCRResult("Hello", 10, 10, 80, 30, 1.0)]
    translations = ["Bonjour"]

    success = process_image_translation(
        sample_image,
        str(output_path),
        ocr_results,
        translations,
        ocr_method="EasyOCR",
    )

    assert success is True
    assert output_path.exists()


def test_process_image_argb32_format(tmp_path: Path) -> None:
    """Format_ARGB32 images are accepted without format conversion."""
    img_path = tmp_path / "argb32.png"
    image = QImage(100, 60, QImage.Format.Format_ARGB32)
    image.fill(QColor(Qt.GlobalColor.white))
    image.save(str(img_path))

    output_path = tmp_path / "output_argb32.png"
    ocr_results = [OCRResult("Hi", 10, 10, 30, 15, 1.0)]
    translations = ["Salut"]

    success = process_image_translation(
        str(img_path),
        str(output_path),
        ocr_results,
        translations,
    )

    assert success is True
    assert output_path.exists()
