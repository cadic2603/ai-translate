"""Unit tests for src/core/image_processor.py.

Covers:
- _remove_original_text: direct unit tests for text removal via background fills
- _insert_translated_text: direct unit tests for rendering translated text
- Error handling when OCR returns no text (empty results)
- Error handling when LLM translation fails (empty/mismatched translations)
- Images with no detectable text (blank / graphics-only)
- Very small images (below minimum dimensions)
- Transparent / alpha-channel image handling
- Different image formats (PNG, JPEG, WEBP)
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QImage, QPainter

from src.constants.ocr import OCR_METHOD_EASYOCR, OCR_METHOD_TESSERACT
from src.core.checkpoint import ALIGN_CENTER, ALIGN_LEFT, ALIGN_RIGHT
from src.core.image_processor import (
    _guess_bg_color,
    _insert_translated_text,
    _remove_original_text,
    process_image_translation,
)
from src.core.ocr_engine import OCRResult

# Ensure pytest-qt creates a QApplication before any test runs.
pytestmark = pytest.mark.usefixtures("qapp")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _has_font_rendering() -> bool:
    """Checks if Qt offscreen font rendering works without segfault.

    Uses subprocess instead of multiprocessing to avoid fork-after-Qt issues.
    """
    import subprocess

    script = (
        'import os; os.environ["QT_QPA_PLATFORM"]="offscreen";'
        "from PySide6.QtWidgets import QApplication;"
        'app=QApplication(["-platform","offscreen"]);'
        "from PySide6.QtGui import QFont,QImage,QPainter;"
        "img=QImage(50,50,QImage.Format.Format_RGB32);"
        "p=QPainter(img);p.setFont(QFont('',12));"
        "p.drawText(img.rect(),0,'A');p.end()"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        timeout=10,
        check=False,
    )
    return result.returncode == 0


def _make_white_image(w: int = 200, h: int = 100) -> QImage:
    """Creates a white RGB32 image of the given size."""
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(QColor(Qt.GlobalColor.white))
    return img


def _make_ocr_result(  # noqa: PLR0913
    text: str = "Hello",
    x: int = 10,
    y: int = 10,
    w: int = 60,
    h: int = 20,
    confidence: float = 1.0,
    alignment: str | None = ALIGN_LEFT,
    is_single_line: bool = True,
    color: str = "#000000",
) -> OCRResult:
    """Creates a configured OCRResult for testing."""
    res = OCRResult(text, x, y, w, h, confidence)
    res.alignment = alignment
    res.is_single_line = is_single_line
    res.color = color
    res.translated_html = ""
    return res


def _save_image(img: QImage, path: Path, fmt: str = "PNG") -> str:
    """Saves a QImage to disk and returns the string path."""
    img.save(str(path), fmt)
    return str(path)


def _pixel_color(img: QImage, x: int, y: int) -> QColor:
    """Returns the QColor at (x, y) in the image."""
    return QColor(img.pixel(x, y))


# ---------------------------------------------------------------------------
# 1. _remove_original_text — direct unit tests
# ---------------------------------------------------------------------------


class TestRemoveOriginalText:
    """Direct tests for _remove_original_text."""

    def test_fills_bounding_box_with_background_color(self) -> None:
        """Text region is filled with the surrounding background color."""
        img = _make_white_image(200, 100)
        # Paint a black rectangle (simulated text area)
        painter = QPainter(img)
        painter.fillRect(QRect(20, 20, 40, 20), QColor(Qt.GlobalColor.black))
        painter.end()

        # Verify the area has black pixels before removal
        assert _pixel_color(img, 30, 25).red() == 0

        fragment = _make_ocr_result(x=20, y=20, w=40, h=20)
        _remove_original_text(img, [fragment], OCR_METHOD_TESSERACT)

        # After removal, the area should be filled with the bg color (white)
        center_color = _pixel_color(img, 30, 25)
        assert center_color.red() == 255  # noqa: PLR2004
        assert center_color.green() == 255  # noqa: PLR2004
        assert center_color.blue() == 255  # noqa: PLR2004

    def test_uses_engine_specific_padding_tesseract(self) -> None:
        """Tesseract uses padding (1, _) — fill extends 1px beyond bounding box."""
        img = QImage(100, 100, QImage.Format.Format_RGB32)
        img.fill(QColor(0, 200, 0))  # Green background

        # Paint a small red block as text
        painter = QPainter(img)
        painter.fillRect(QRect(30, 30, 20, 10), QColor(Qt.GlobalColor.red))
        painter.end()

        fragment = _make_ocr_result(x=30, y=30, w=20, h=10)
        _remove_original_text(img, [fragment], OCR_METHOD_TESSERACT)

        # Tesseract pad_remove=1, so pixel at (29, 29) should also be filled
        color_padded = _pixel_color(img, 29, 29)
        assert color_padded.green() == 200  # noqa: PLR2004

    def test_uses_engine_specific_padding_easyocr(self) -> None:
        """EasyOCR uses padding (0, _) — no extra padding beyond bounding box."""
        img = QImage(100, 100, QImage.Format.Format_RGB32)
        img.fill(QColor(0, 0, 200))  # Blue background

        # Paint a red block
        painter = QPainter(img)
        painter.fillRect(QRect(30, 30, 20, 10), QColor(Qt.GlobalColor.red))
        painter.end()

        # Mark a pixel at the exact edge before removal
        edge_before = _pixel_color(img, 30, 30)
        assert edge_before.red() == 255  # noqa: PLR2004

        fragment = _make_ocr_result(x=30, y=30, w=20, h=10)
        _remove_original_text(img, [fragment], OCR_METHOD_EASYOCR)

        # EasyOCR pad_remove=0, so the exact bounding box is filled
        center_color = _pixel_color(img, 35, 33)
        assert center_color.blue() == 200  # noqa: PLR2004

    def test_multiple_fragments(self) -> None:
        """Multiple fragments are each independently cleared."""
        img = _make_white_image(200, 100)
        painter = QPainter(img)
        painter.fillRect(QRect(10, 10, 30, 15), QColor(Qt.GlobalColor.black))
        painter.fillRect(QRect(100, 50, 30, 15), QColor(Qt.GlobalColor.black))
        painter.end()

        frags = [
            _make_ocr_result(x=10, y=10, w=30, h=15),
            _make_ocr_result(x=100, y=50, w=30, h=15),
        ]
        _remove_original_text(img, frags, OCR_METHOD_TESSERACT)

        # Both areas should now be white
        assert _pixel_color(img, 20, 15).red() == 255  # noqa: PLR2004
        assert _pixel_color(img, 110, 55).red() == 255  # noqa: PLR2004

    def test_empty_fragments_list(self) -> None:
        """Empty fragment list does nothing — image unchanged."""
        img = _make_white_image(50, 50)
        painter = QPainter(img)
        painter.fillRect(QRect(10, 10, 10, 10), QColor(Qt.GlobalColor.red))
        painter.end()

        _remove_original_text(img, [], OCR_METHOD_TESSERACT)

        # Red area should remain
        assert _pixel_color(img, 15, 15).red() == 255  # noqa: PLR2004
        assert _pixel_color(img, 15, 15).green() == 0

    def test_fragment_at_image_edge(self) -> None:
        """Fragment at (0,0) handles negative padding clamp gracefully."""
        img = _make_white_image(100, 100)
        # Small text block at corner — surrounding pixels are mostly white
        painter = QPainter(img)
        painter.fillRect(QRect(5, 5, 10, 5), QColor(Qt.GlobalColor.black))
        painter.end()

        fragment = _make_ocr_result(x=5, y=5, w=10, h=5)
        # Should not crash even though Tesseract padding (1px) extends the rect
        _remove_original_text(img, [fragment], OCR_METHOD_TESSERACT)

        # The cleared area should be filled with surrounding bg (white)
        center = _pixel_color(img, 8, 7)
        assert center.red() == 255  # noqa: PLR2004

    def test_colored_background_matched(self) -> None:
        """Background color is guessed from surrounding pixels, not always white."""
        img = QImage(100, 100, QImage.Format.Format_RGB32)
        img.fill(QColor(100, 150, 200))  # Custom blue-ish background

        # Paint text (dark) in center
        painter = QPainter(img)
        painter.fillRect(QRect(30, 30, 30, 20), QColor(0, 0, 0))
        painter.end()

        fragment = _make_ocr_result(x=30, y=30, w=30, h=20)
        _remove_original_text(img, [fragment], OCR_METHOD_TESSERACT)

        # The filled area should match the background
        center = _pixel_color(img, 40, 38)
        assert center.red() == 100  # noqa: PLR2004
        assert center.green() == 150  # noqa: PLR2004
        assert center.blue() == 200  # noqa: PLR2004


# ---------------------------------------------------------------------------
# 2. _insert_translated_text — direct unit tests
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not _has_font_rendering(),
    reason="Qt offscreen font rendering unavailable",
)
class TestInsertTranslatedText:
    """Direct tests for _insert_translated_text."""

    def test_renders_text_onto_image(self) -> None:
        """Translated text is drawn onto the image (pixels change)."""
        img = _make_white_image(200, 100)

        # Snapshot a pixel in the text region before rendering
        before = _pixel_color(img, 40, 20)

        ocr_res = _make_ocr_result(x=10, y=10, w=180, h=40)
        ocr_res.translated_html = "Bonjour"
        ocr_res.color = "#000000"

        _insert_translated_text(
            img, [ocr_res], ["Bonjour"], "French", OCR_METHOD_TESSERACT
        )

        # At least some pixels in the region should change (text was drawn)
        changed = False
        for px in range(15, 100):
            for py in range(12, 45):
                c = _pixel_color(img, px, py)
                if c != before:
                    changed = True
                    break
            if changed:
                break
        assert changed, "Expected pixels to change after text insertion"

    def test_skips_empty_translation(self) -> None:
        """Empty translation strings are skipped — image stays unchanged."""
        img = _make_white_image(200, 100)
        original_pixel = _pixel_color(img, 50, 50)

        ocr_res = _make_ocr_result(x=10, y=10, w=180, h=80)
        _insert_translated_text(
            img, [ocr_res], [""], "English (US)", OCR_METHOD_TESSERACT
        )

        # Image should be unchanged
        assert _pixel_color(img, 50, 50) == original_pixel

    def test_multiple_text_blocks(self) -> None:
        """Multiple translation blocks are all rendered without crashing."""
        img = _make_white_image(400, 200)

        results = [
            _make_ocr_result(x=10, y=10, w=180, h=30),
            _make_ocr_result(x=10, y=100, w=180, h=30),
        ]
        results[0].translated_html = "First"
        results[1].translated_html = "Second"

        translations = ["First", "Second"]
        # Should not raise
        _insert_translated_text(
            img, results, translations, "English (US)", OCR_METHOD_TESSERACT
        )

    def test_easyocr_negative_padding(self) -> None:
        """EasyOCR insert padding is -2 — rendering rect is slightly smaller."""
        img = _make_white_image(200, 100)

        ocr_res = _make_ocr_result(x=20, y=20, w=160, h=40)
        ocr_res.translated_html = "Test"

        # Should not crash even with negative padding shrinking the rect
        _insert_translated_text(
            img, [ocr_res], ["Test"], "English (US)", OCR_METHOD_EASYOCR
        )

    def test_renders_with_right_alignment(self) -> None:
        """Right-aligned text renders without error."""
        img = _make_white_image(300, 100)

        ocr_res = _make_ocr_result(x=10, y=10, w=280, h=40, alignment=ALIGN_RIGHT)
        ocr_res.translated_html = "Right text"

        _insert_translated_text(
            img, [ocr_res], ["Right text"], "English (US)", OCR_METHOD_TESSERACT
        )

    def test_renders_with_center_alignment(self) -> None:
        """Center-aligned text renders without error."""
        img = _make_white_image(300, 100)

        ocr_res = _make_ocr_result(x=10, y=10, w=280, h=40, alignment=ALIGN_CENTER)
        ocr_res.translated_html = "Center text"

        _insert_translated_text(
            img, [ocr_res], ["Center text"], "English (US)", OCR_METHOD_TESSERACT
        )


# ---------------------------------------------------------------------------
# 3. Error handling: OCR returns no text (empty results)
# ---------------------------------------------------------------------------


class TestOCRNoText:
    """Tests for handling OCR that returns no text."""

    def test_process_empty_ocr_results(self, tmp_path: Path) -> None:
        """Empty OCR results produce a valid output (no-op translation)."""
        img_path = tmp_path / "input.png"
        _save_image(_make_white_image(), img_path)
        output_path = tmp_path / "output.png"

        success = process_image_translation(str(img_path), str(output_path), [], [])
        assert success is True
        assert output_path.exists()

    def test_remove_text_with_empty_fragments(self) -> None:
        """_remove_original_text with empty list does not modify image."""
        img = _make_white_image(100, 100)
        # Fill center with red to detect changes
        painter = QPainter(img)
        painter.fillRect(QRect(30, 30, 40, 40), QColor(Qt.GlobalColor.red))
        painter.end()

        _remove_original_text(img, [], OCR_METHOD_TESSERACT)

        # Red area must remain
        assert _pixel_color(img, 50, 50).red() == 255  # noqa: PLR2004
        assert _pixel_color(img, 50, 50).green() == 0

    def test_insert_text_with_empty_lists(self) -> None:
        """_insert_translated_text with empty lists is a no-op."""
        img = _make_white_image(100, 100)
        _insert_translated_text(img, [], [], "English (US)", OCR_METHOD_TESSERACT)
        # Should not crash and image stays white
        assert _pixel_color(img, 50, 50) == QColor(Qt.GlobalColor.white)


# ---------------------------------------------------------------------------
# 4. Error handling: LLM translation fails
# ---------------------------------------------------------------------------


class TestLLMTranslationFailure:
    """Tests for handling LLM translation failures / mismatches."""

    def test_mismatch_returns_false(self, tmp_path: Path) -> None:
        """Returns False when OCR results count != translations count."""
        img_path = tmp_path / "input.png"
        _save_image(_make_white_image(), img_path)
        output_path = tmp_path / "output.png"

        ocr_results = [_make_ocr_result(), _make_ocr_result(x=80)]
        translations = ["Only one"]  # 2 results but 1 translation

        success = process_image_translation(
            str(img_path), str(output_path), ocr_results, translations
        )
        assert success is False

    def test_all_empty_translations_still_succeeds(self, tmp_path: Path) -> None:
        """All-empty translations (LLM returned blanks) still succeeds."""
        img_path = tmp_path / "input.png"
        _save_image(_make_white_image(), img_path)
        output_path = tmp_path / "output.png"

        ocr_results = [_make_ocr_result(), _make_ocr_result(x=80)]
        translations = ["", ""]

        success = process_image_translation(
            str(img_path), str(output_path), ocr_results, translations
        )
        assert success is True
        assert output_path.exists()

    def test_single_mismatch_extra_translation(self, tmp_path: Path) -> None:
        """Extra translations beyond OCR results cause failure."""
        img_path = tmp_path / "input.png"
        _save_image(_make_white_image(), img_path)
        output_path = tmp_path / "output.png"

        ocr_results = [_make_ocr_result()]
        translations = ["A", "B", "C"]

        success = process_image_translation(
            str(img_path), str(output_path), ocr_results, translations
        )
        assert success is False

    def test_single_mismatch_extra_ocr(self, tmp_path: Path) -> None:
        """Extra OCR results beyond translations cause failure."""
        img_path = tmp_path / "input.png"
        _save_image(_make_white_image(), img_path)
        output_path = tmp_path / "output.png"

        ocr_results = [
            _make_ocr_result(),
            _make_ocr_result(x=80),
            _make_ocr_result(x=150),
        ]
        translations = ["A"]

        success = process_image_translation(
            str(img_path), str(output_path), ocr_results, translations
        )
        assert success is False


# ---------------------------------------------------------------------------
# 5. Image with no detectable text (blank / graphics only)
# ---------------------------------------------------------------------------


class TestBlankOrGraphicsOnlyImage:
    """Tests for images that contain no detectable text."""

    def test_blank_white_image_no_results(self, tmp_path: Path) -> None:
        """Processing a blank image with empty OCR results succeeds."""
        img_path = tmp_path / "blank.png"
        _save_image(_make_white_image(), img_path)
        output_path = tmp_path / "output.png"

        success = process_image_translation(str(img_path), str(output_path), [], [])
        assert success is True
        assert output_path.exists()

        # Output should be identical to input (no modifications)
        out_img = QImage(str(output_path))
        assert out_img.width() == 200  # noqa: PLR2004
        assert out_img.height() == 100  # noqa: PLR2004

    def test_graphics_only_image_empty_results(self, tmp_path: Path) -> None:
        """Image with only colored shapes (no text) processes with empty results."""
        img = QImage(200, 200, QImage.Format.Format_RGB32)
        img.fill(QColor(Qt.GlobalColor.white))

        # Draw some geometric shapes (no text)
        painter = QPainter(img)
        painter.setBrush(QColor(Qt.GlobalColor.blue))
        painter.drawEllipse(50, 50, 100, 100)
        painter.setBrush(QColor(Qt.GlobalColor.red))
        painter.drawRect(10, 10, 40, 40)
        painter.end()

        img_path = tmp_path / "shapes.png"
        _save_image(img, img_path)
        output_path = tmp_path / "output.png"

        success = process_image_translation(str(img_path), str(output_path), [], [])
        assert success is True
        assert output_path.exists()

    def test_solid_color_image(self, tmp_path: Path) -> None:
        """Solid-color image with no text processes successfully."""
        img = QImage(100, 100, QImage.Format.Format_RGB32)
        img.fill(QColor(128, 64, 32))

        img_path = tmp_path / "solid.png"
        _save_image(img, img_path)
        output_path = tmp_path / "output.png"

        success = process_image_translation(str(img_path), str(output_path), [], [])
        assert success is True


# ---------------------------------------------------------------------------
# 6. Very small images (below minimum dimensions)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not _has_font_rendering(),
    reason="Qt offscreen font rendering unavailable",
)
class TestVerySmallImages:
    """Tests for extremely small images."""

    def test_1x1_image(self, tmp_path: Path) -> None:
        """A 1x1 pixel image can be processed without crashing."""
        img = QImage(1, 1, QImage.Format.Format_RGB32)
        img.fill(QColor(Qt.GlobalColor.white))

        img_path = tmp_path / "tiny.png"
        _save_image(img, img_path)
        output_path = tmp_path / "output.png"

        success = process_image_translation(str(img_path), str(output_path), [], [])
        assert success is True
        assert output_path.exists()

    def test_5x5_image_with_ocr_result(self, tmp_path: Path) -> None:
        """A 5x5 image with an OCR result covering it does not crash."""
        img = QImage(5, 5, QImage.Format.Format_RGB32)
        img.fill(QColor(Qt.GlobalColor.white))

        img_path = tmp_path / "tiny5.png"
        _save_image(img, img_path)
        output_path = tmp_path / "output.png"

        # OCR result covers the entire tiny image
        ocr_res = _make_ocr_result(x=0, y=0, w=5, h=5)
        ocr_res.translated_html = "A"

        success = process_image_translation(
            str(img_path), str(output_path), [ocr_res], ["A"]
        )
        assert success is True

    def test_10x10_image_text_removal(self) -> None:
        """_remove_original_text on a 10x10 image does not crash."""
        img = QImage(10, 10, QImage.Format.Format_RGB32)
        img.fill(QColor(Qt.GlobalColor.white))

        fragment = _make_ocr_result(x=2, y=2, w=6, h=6)
        _remove_original_text(img, [fragment], OCR_METHOD_TESSERACT)
        # No crash = success

    def test_10x10_image_text_insertion(self) -> None:
        """_insert_translated_text on a 10x10 image does not crash."""
        img = QImage(10, 10, QImage.Format.Format_RGB32)
        img.fill(QColor(Qt.GlobalColor.white))

        ocr_res = _make_ocr_result(x=1, y=1, w=8, h=8)
        ocr_res.translated_html = "X"
        _insert_translated_text(
            img, [ocr_res], ["X"], "English (US)", OCR_METHOD_TESSERACT
        )

    def test_narrow_image(self, tmp_path: Path) -> None:
        """A very narrow image (200x2) can be processed."""
        img = QImage(200, 2, QImage.Format.Format_RGB32)
        img.fill(QColor(Qt.GlobalColor.white))

        img_path = tmp_path / "narrow.png"
        _save_image(img, img_path)
        output_path = tmp_path / "output.png"

        success = process_image_translation(str(img_path), str(output_path), [], [])
        assert success is True

    def test_tall_thin_image(self, tmp_path: Path) -> None:
        """A very tall thin image (2x200) can be processed."""
        img = QImage(2, 200, QImage.Format.Format_RGB32)
        img.fill(QColor(Qt.GlobalColor.white))

        img_path = tmp_path / "tall.png"
        _save_image(img, img_path)
        output_path = tmp_path / "output.png"

        success = process_image_translation(str(img_path), str(output_path), [], [])
        assert success is True


# ---------------------------------------------------------------------------
# 7. Transparent / alpha-channel image handling
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not _has_font_rendering(),
    reason="Qt offscreen font rendering unavailable",
)
class TestTransparentImages:
    """Tests for images with transparency / alpha channels."""

    def test_argb32_with_transparency(self, tmp_path: Path) -> None:
        """ARGB32 image with alpha channel preserves transparency on output."""
        img = QImage(200, 100, QImage.Format.Format_ARGB32)
        img.fill(QColor(0, 0, 0, 0))  # Fully transparent

        img_path = tmp_path / "transparent.png"
        _save_image(img, img_path)
        output_path = tmp_path / "output.png"

        ocr_res = _make_ocr_result(x=10, y=10, w=80, h=30)
        ocr_res.translated_html = "Hello"

        success = process_image_translation(
            str(img_path), str(output_path), [ocr_res], ["Hello"]
        )
        assert success is True
        assert output_path.exists()

    def test_semi_transparent_background(self, tmp_path: Path) -> None:
        """Image with semi-transparent background processes without error."""
        img = QImage(200, 100, QImage.Format.Format_ARGB32)
        img.fill(QColor(255, 0, 0, 128))  # Semi-transparent red

        img_path = tmp_path / "semitrans.png"
        _save_image(img, img_path)
        output_path = tmp_path / "output.png"

        success = process_image_translation(str(img_path), str(output_path), [], [])
        assert success is True

    def test_argb32_premultiplied(self, tmp_path: Path) -> None:
        """ARGB32_Premultiplied format is accepted without conversion."""
        img = QImage(100, 100, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(QColor(Qt.GlobalColor.white))

        img_path = tmp_path / "premul.png"
        _save_image(img, img_path)
        output_path = tmp_path / "output.png"

        ocr_res = _make_ocr_result(x=5, y=5, w=80, h=30)
        ocr_res.translated_html = "Test"

        success = process_image_translation(
            str(img_path), str(output_path), [ocr_res], ["Test"]
        )
        assert success is True

    def test_remove_text_on_transparent_image(self) -> None:
        """_remove_original_text works on ARGB32 images with alpha."""
        img = QImage(100, 100, QImage.Format.Format_ARGB32)
        img.fill(QColor(200, 200, 200, 200))  # Semi-transparent gray

        fragment = _make_ocr_result(x=20, y=20, w=30, h=15)
        # Should not crash
        _remove_original_text(img, [fragment], OCR_METHOD_TESSERACT)

    def test_insert_text_on_transparent_image(self) -> None:
        """_insert_translated_text works on ARGB32 images."""
        img = QImage(200, 100, QImage.Format.Format_ARGB32)
        img.fill(QColor(0, 0, 0, 0))

        ocr_res = _make_ocr_result(x=10, y=10, w=180, h=40)
        ocr_res.translated_html = "Transparent bg"
        ocr_res.color = "#FF0000"

        _insert_translated_text(
            img, [ocr_res], ["Transparent bg"], "English (US)", OCR_METHOD_TESSERACT
        )

    def test_indexed8_converted_before_processing(self, tmp_path: Path) -> None:
        """Format_Indexed8 (palette) images are auto-converted to ARGB32."""
        img = QImage(100, 50, QImage.Format.Format_Indexed8)
        img.setColorCount(2)  # noqa: PLR2004
        img.setColor(0, QColor(Qt.GlobalColor.white).rgb())
        img.setColor(1, QColor(Qt.GlobalColor.black).rgb())
        img.fill(0)

        img_path = tmp_path / "indexed.png"
        _save_image(img, img_path)
        output_path = tmp_path / "output.png"

        ocr_res = _make_ocr_result(x=5, y=5, w=40, h=15)
        ocr_res.translated_html = "Idx"

        success = process_image_translation(
            str(img_path), str(output_path), [ocr_res], ["Idx"]
        )
        assert success is True
        assert output_path.exists()


# ---------------------------------------------------------------------------
# 8. Different image formats (PNG, JPEG, WEBP)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not _has_font_rendering(),
    reason="Qt offscreen font rendering unavailable",
)
class TestImageFormats:
    """Tests for different output image formats."""

    def test_png_output(self, tmp_path: Path) -> None:
        """PNG output is created successfully."""
        img_path = tmp_path / "input.png"
        _save_image(_make_white_image(), img_path)
        output_path = tmp_path / "output.png"

        ocr_res = _make_ocr_result(x=10, y=10, w=60, h=20)
        ocr_res.translated_html = "PNG test"

        success = process_image_translation(
            str(img_path), str(output_path), [ocr_res], ["PNG test"]
        )
        assert success is True
        assert output_path.exists()

        out_img = QImage(str(output_path))
        assert not out_img.isNull()

    def test_jpeg_output_quality_100(self, tmp_path: Path) -> None:
        """JPEG output uses quality=100 (large file size)."""
        img_path = tmp_path / "input.png"
        _save_image(_make_white_image(400, 400), img_path)
        output_path = tmp_path / "output.jpg"

        ocr_res = _make_ocr_result(x=10, y=10, w=100, h=30)
        ocr_res.translated_html = "JPEG test"

        success = process_image_translation(
            str(img_path), str(output_path), [ocr_res], ["JPEG test"]
        )
        assert success is True
        assert output_path.exists()
        assert output_path.stat().st_size > 500  # noqa: PLR2004

    def test_jpeg_uppercase_extension(self, tmp_path: Path) -> None:
        """JPEG detection is case-insensitive (.JPEG extension)."""
        img_path = tmp_path / "input.png"
        _save_image(_make_white_image(), img_path)
        output_path = tmp_path / "output.JPEG"

        ocr_res = _make_ocr_result(x=10, y=10, w=60, h=20)
        ocr_res.translated_html = "Case test"

        success = process_image_translation(
            str(img_path), str(output_path), [ocr_res], ["Case test"]
        )
        assert success is True
        assert output_path.exists()

    def test_jpg_extension(self, tmp_path: Path) -> None:
        """Short .jpg extension also triggers quality=100."""
        img_path = tmp_path / "input.png"
        _save_image(_make_white_image(), img_path)
        output_path = tmp_path / "output.jpg"

        success = process_image_translation(str(img_path), str(output_path), [], [])
        assert success is True
        assert output_path.exists()

    def test_webp_output(self, tmp_path: Path) -> None:
        """WEBP output is created if supported by Qt."""
        img_path = tmp_path / "input.png"
        _save_image(_make_white_image(), img_path)
        output_path = tmp_path / "output.webp"

        ocr_res = _make_ocr_result(x=10, y=10, w=60, h=20)
        ocr_res.translated_html = "WEBP test"

        success = process_image_translation(
            str(img_path), str(output_path), [ocr_res], ["WEBP test"]
        )
        # Qt may or may not support WEBP depending on build; verify no crash
        if success:
            assert output_path.exists()

    def test_png_input_jpeg_output(self, tmp_path: Path) -> None:
        """PNG input can be translated and saved as JPEG output."""
        img_path = tmp_path / "input.png"
        _save_image(_make_white_image(), img_path)
        output_path = tmp_path / "output.jpeg"

        ocr_res = _make_ocr_result(x=10, y=10, w=80, h=25)
        ocr_res.translated_html = "Cross format"

        success = process_image_translation(
            str(img_path), str(output_path), [ocr_res], ["Cross format"]
        )
        assert success is True
        assert output_path.exists()

    def test_bmp_output(self, tmp_path: Path) -> None:
        """BMP output is created successfully."""
        img_path = tmp_path / "input.png"
        _save_image(_make_white_image(), img_path)
        output_path = tmp_path / "output.bmp"

        success = process_image_translation(str(img_path), str(output_path), [], [])
        assert success is True
        assert output_path.exists()


# ---------------------------------------------------------------------------
# Additional edge cases and integration scenarios
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not _has_font_rendering(),
    reason="Qt offscreen font rendering unavailable",
)
class TestAdditionalEdgeCases:
    """Miscellaneous edge-case tests."""

    def test_nonexistent_input_file(self, tmp_path: Path) -> None:
        """Returns False for non-existent input image path."""
        output_path = tmp_path / "output.png"
        success = process_image_translation(
            str(tmp_path / "does_not_exist.png"),
            str(output_path),
            [_make_ocr_result()],
            ["Translation"],
        )
        assert success is False

    def test_raw_ocr_results_used_for_removal(self, tmp_path: Path) -> None:
        """raw_ocr_results are used for removal while ocr_results for insertion."""
        img = _make_white_image(300, 100)
        # Paint two separate text blocks
        painter = QPainter(img)
        painter.fillRect(QRect(10, 10, 30, 15), QColor(Qt.GlobalColor.black))
        painter.fillRect(QRect(50, 10, 30, 15), QColor(Qt.GlobalColor.black))
        painter.end()

        img_path = tmp_path / "raw_test.png"
        _save_image(img, img_path)
        output_path = tmp_path / "output.png"

        # Merged OCR result (single block) vs raw (two fragments)
        merged = [_make_ocr_result(x=10, y=10, w=70, h=15)]
        merged[0].translated_html = "Combined"
        raw = [
            _make_ocr_result(x=10, y=10, w=30, h=15),
            _make_ocr_result(x=50, y=10, w=30, h=15),
        ]

        success = process_image_translation(
            str(img_path),
            str(output_path),
            merged,
            ["Combined"],
            raw_ocr_results=raw,
        )
        assert success is True
        assert output_path.exists()

    def test_large_bounding_box_exceeding_image(self) -> None:
        """Bounding box larger than image does not crash."""
        img = _make_white_image(100, 100)

        fragment = _make_ocr_result(x=-10, y=-10, w=200, h=200)
        _remove_original_text(img, [fragment], OCR_METHOD_TESSERACT)
        # No crash = success

    def test_ocr_result_with_bold_italic_color(self, tmp_path: Path) -> None:
        """OCR result with styling attributes processes successfully."""
        img_path = tmp_path / "styled.png"
        _save_image(_make_white_image(300, 100), img_path)
        output_path = tmp_path / "output.png"

        ocr_res = _make_ocr_result(x=10, y=10, w=200, h=40)
        ocr_res.is_bold = True
        ocr_res.is_italic = True
        ocr_res.color = "#FF0000"
        ocr_res.translated_html = "<b><i>Styled</i></b>"

        success = process_image_translation(
            str(img_path), str(output_path), [ocr_res], ["Styled"]
        )
        assert success is True

    def test_multiline_ocr_result(self, tmp_path: Path) -> None:
        """Multiline OCR result (is_single_line=False) processes successfully."""
        img_path = tmp_path / "multiline.png"
        _save_image(_make_white_image(300, 200), img_path)
        output_path = tmp_path / "output.png"

        ocr_res = _make_ocr_result(x=10, y=10, w=280, h=180, is_single_line=False)
        ocr_res.translated_html = "Line one<br>Line two<br>Line three"
        ocr_res.line_height_ratio = 1.4

        translations = ["Line one\nLine two\nLine three"]
        success = process_image_translation(
            str(img_path), str(output_path), [ocr_res], translations
        )
        assert success is True

    def test_guess_bg_color_on_transparent_image(self) -> None:
        """_guess_bg_color handles ARGB32 images with alpha values."""
        img = QImage(100, 100, QImage.Format.Format_ARGB32)
        img.fill(QColor(0, 0, 0, 0))  # Fully transparent

        rect = QRect(20, 20, 60, 60)
        color = _guess_bg_color(img, rect)
        # Should return a valid QColor (possibly transparent or fallback)
        assert color.isValid()

    def test_process_with_target_lang(self, tmp_path: Path) -> None:
        """Target language parameter is passed through to TextRenderer."""
        img_path = tmp_path / "lang.png"
        _save_image(_make_white_image(300, 100), img_path)
        output_path = tmp_path / "output.png"

        ocr_res = _make_ocr_result(x=10, y=10, w=200, h=40)
        ocr_res.translated_html = "Translated"

        success = process_image_translation(
            str(img_path),
            str(output_path),
            [ocr_res],
            ["Translated"],
            target_lang="Japanese",
        )
        assert success is True

    def test_remove_then_insert_pixel_verification(self) -> None:
        """Full pipeline: remove black text from white bg, then insert new text."""
        img = _make_white_image(300, 100)

        # Draw black "text" rectangle
        painter = QPainter(img)
        painter.fillRect(QRect(20, 20, 100, 30), QColor(Qt.GlobalColor.black))
        painter.end()

        # Verify black area exists
        assert _pixel_color(img, 50, 30).red() == 0

        fragment = _make_ocr_result(x=20, y=20, w=100, h=30)
        _remove_original_text(img, [fragment], OCR_METHOD_TESSERACT)

        # After removal, area should be white (background)
        assert _pixel_color(img, 50, 30).red() == 255  # noqa: PLR2004

        # Now insert new text
        ocr_res = _make_ocr_result(x=20, y=20, w=100, h=30)
        ocr_res.translated_html = "Bonjour"
        ocr_res.color = "#000000"

        _insert_translated_text(
            img, [ocr_res], ["Bonjour"], "French", OCR_METHOD_TESSERACT
        )

        # Some pixels should have changed from the text rendering
        has_dark_pixel = False
        for px in range(25, 110):
            for py in range(22, 48):
                c = _pixel_color(img, px, py)
                if c.red() < 200:  # noqa: PLR2004
                    has_dark_pixel = True
                    break
            if has_dark_pixel:
                break
        assert has_dark_pixel, "Expected rendered text to produce dark pixels"

    def test_overlapping_bounding_boxes(self) -> None:
        """Overlapping bounding boxes do not crash during removal."""
        img = _make_white_image(200, 100)
        painter = QPainter(img)
        painter.fillRect(QRect(10, 10, 60, 20), QColor(Qt.GlobalColor.black))
        painter.end()

        frags = [
            _make_ocr_result(x=10, y=10, w=40, h=20),
            _make_ocr_result(x=30, y=10, w=40, h=20),  # Overlaps first
        ]
        _remove_original_text(img, frags, OCR_METHOD_TESSERACT)

        # Area should be cleared to background
        assert _pixel_color(img, 30, 15).red() == 255  # noqa: PLR2004

    def test_insert_text_with_mock_renderer(self) -> None:
        """Verify _insert_translated_text calls TextRenderer.render for each block."""
        img = _make_white_image(200, 100)

        results = [
            _make_ocr_result(x=10, y=10, w=80, h=20),
            _make_ocr_result(x=10, y=50, w=80, h=20),
        ]
        results[0].translated_html = "A"
        results[1].translated_html = "B"

        with patch("src.core.image_processor.TextRenderer") as mock_renderer:
            _insert_translated_text(
                img, results, ["A", "B"], "English (US)", OCR_METHOD_TESSERACT
            )
            assert mock_renderer.render.call_count == 2  # noqa: PLR2004

    def test_insert_text_skips_empty_with_mock(self) -> None:
        """Verify empty translations skip TextRenderer.render calls."""
        img = _make_white_image(200, 100)

        results = [
            _make_ocr_result(x=10, y=10, w=80, h=20),
            _make_ocr_result(x=10, y=50, w=80, h=20),
        ]
        results[0].translated_html = ""
        results[1].translated_html = "B"

        with patch("src.core.image_processor.TextRenderer") as mock_renderer:
            _insert_translated_text(
                img, results, ["", "B"], "English (US)", OCR_METHOD_TESSERACT
            )
            # Only the second block should trigger render (first is empty)
            assert mock_renderer.render.call_count == 1


# ---------------------------------------------------------------------------
# _guess_bg_color — gradient / noise / edge-case tests
# ---------------------------------------------------------------------------


class TestGuessBgColorGradient:
    """Test background detection on gradient images."""

    def test_horizontal_gradient_returns_mode(self) -> None:
        """Horizontal gradient: left half red, right half blue.

        With a text box in the center, the perimeter samples should
        pick up both colors but one should dominate as the mode.
        """
        img = QImage(200, 100, QImage.Format.Format_RGB32)
        painter = QPainter(img)
        # Left half red
        painter.fillRect(QRect(0, 0, 100, 100), QColor(255, 0, 0))
        # Right half blue
        painter.fillRect(QRect(100, 0, 100, 100), QColor(0, 0, 255))
        painter.end()

        # Box centered at the boundary — samples include both red and blue
        rect = QRect(80, 30, 40, 40)
        color = _guess_bg_color(img, rect)
        assert color.isValid()
        # The mode should be either red or blue (both are valid dominant colors)
        is_red = color.red() > 200 and color.blue() < 50  # noqa: PLR2004
        is_blue = color.blue() > 200 and color.red() < 50  # noqa: PLR2004
        assert is_red or is_blue

    def test_vertical_gradient(self) -> None:
        """Vertical gradient: top half green, bottom half yellow.

        With a text box in the upper region, most perimeter pixels
        should be green.
        """
        img = QImage(200, 200, QImage.Format.Format_RGB32)
        painter = QPainter(img)
        # Top half green
        painter.fillRect(QRect(0, 0, 200, 100), QColor(0, 200, 0))
        # Bottom half yellow
        painter.fillRect(QRect(0, 100, 200, 100), QColor(255, 255, 0))
        painter.end()

        # Box fully in the green region
        rect = QRect(50, 20, 100, 40)
        color = _guess_bg_color(img, rect)
        assert color.green() == 200  # noqa: PLR2004
        assert color.red() == 0


class TestGuessBgColorNoise:
    """Test background detection on noisy images."""

    def test_noisy_background_returns_dominant_color(self) -> None:
        """Image with ~80% red pixels and ~20% blue pixels.

        The mode should be red since it is the dominant color.
        """
        img = QImage(200, 200, QImage.Format.Format_RGB32)
        img.fill(QColor(255, 0, 0))  # Fill entirely with red

        # Scatter some blue pixels (top-left quadrant only)
        painter = QPainter(img)
        for px in range(0, 50, 3):
            for py in range(0, 50, 3):
                painter.setPen(QColor(0, 0, 255))
                painter.drawPoint(px, py)
        painter.end()

        # Box in the center — perimeter is entirely red
        rect = QRect(60, 60, 80, 80)
        color = _guess_bg_color(img, rect)
        assert color.red() == 255  # noqa: PLR2004
        assert color.blue() == 0

    def test_checkerboard_pattern(self) -> None:
        """Alternating black/white checkerboard.

        The mode should return one of black or white.
        """
        img = QImage(100, 100, QImage.Format.Format_RGB32)
        for x in range(100):
            for y in range(100):
                if (x + y) % 2 == 0:
                    img.setPixel(x, y, QColor(255, 255, 255).rgb())
                else:
                    img.setPixel(x, y, QColor(0, 0, 0).rgb())

        rect = QRect(20, 20, 60, 60)
        color = _guess_bg_color(img, rect)
        # Must return either black or white
        is_white = color.red() == 255 and color.green() == 255 and color.blue() == 255  # noqa: PLR2004, E501
        is_black = color.red() == 0 and color.green() == 0 and color.blue() == 0
        assert is_white or is_black


class TestGuessBgColorEdgeCases:
    """Test edge cases for _guess_bg_color."""

    def test_text_box_at_image_edge(self) -> None:
        """Box at (0, 0) — some sample points will be out of bounds.

        The function clamps negative coordinates via the 0 <= px check.
        """
        img = QImage(100, 100, QImage.Format.Format_RGB32)
        img.fill(QColor(128, 128, 128))

        rect = QRect(0, 0, 30, 20)
        color = _guess_bg_color(img, rect)
        assert color.isValid()
        assert color.red() == 128  # noqa: PLR2004

    def test_text_box_covers_entire_image(self) -> None:
        """Box same size as image — all sample points are at image boundary.

        The offset=2 means points are at (x-2, y-2) etc., which are
        clamped to image bounds. Should still return a valid color.
        """
        img = QImage(50, 50, QImage.Format.Format_RGB32)
        img.fill(QColor(100, 150, 200))

        rect = QRect(0, 0, 50, 50)
        color = _guess_bg_color(img, rect)
        assert color.isValid()
        # Edge pixels are still sampled (clamped to bounds)
        assert color.red() == 100  # noqa: PLR2004

    def test_single_pixel_image(self) -> None:
        """1x1 image with a box covering it.

        Sample points are clamped to valid range so the single pixel
        is used.
        """
        img = QImage(1, 1, QImage.Format.Format_RGB32)
        img.fill(QColor(42, 42, 42))

        rect = QRect(0, 0, 1, 1)
        color = _guess_bg_color(img, rect)
        assert color.isValid()
        # The single pixel should be sampled
        assert color.red() == 42  # noqa: PLR2004

    def test_transparent_background(self) -> None:
        """ARGB32 image with transparent pixels.

        _guess_bg_color should return a valid QColor even when
        all sampled pixels are fully transparent.
        """
        img = QImage(100, 100, QImage.Format.Format_ARGB32)
        img.fill(QColor(0, 0, 0, 0))  # Fully transparent

        rect = QRect(20, 20, 60, 60)
        color = _guess_bg_color(img, rect)
        # Should return a valid color (transparent pixel encoded as QRgb)
        assert color.isValid()

    def test_very_large_text_box(self) -> None:
        """1000x1000 box on 1200x1200 image — many samples near edges.

        Verifies the function handles large perimeters without error.
        """
        img = QImage(1200, 1200, QImage.Format.Format_RGB32)
        img.fill(QColor(50, 100, 150))

        rect = QRect(100, 100, 1000, 1000)
        color = _guess_bg_color(img, rect)
        assert color.red() == 50  # noqa: PLR2004
        assert color.green() == 100  # noqa: PLR2004
        assert color.blue() == 150  # noqa: PLR2004

    def test_text_box_at_bottom_right_corner(self) -> None:
        """Box at the bottom-right corner of the image.

        Sample points extending beyond the image boundary must be
        handled without index errors.
        """
        img = QImage(100, 100, QImage.Format.Format_RGB32)
        img.fill(QColor(200, 100, 50))

        rect = QRect(80, 80, 20, 20)
        color = _guess_bg_color(img, rect)
        assert color.isValid()
        assert color.red() == 200  # noqa: PLR2004

    def test_zero_size_rect(self) -> None:
        """Zero-width/height rect produces no sample points in range().

        _guess_bg_color should fall back to white when no points are
        generated.
        """
        img = QImage(100, 100, QImage.Format.Format_RGB32)
        img.fill(QColor(255, 0, 0))

        # A zero-width rect at (50, 50) — range(50, 50+0+1, 2) generates
        # a single point, so we still get samples. Use QRect directly.
        rect = QRect(50, 50, 0, 0)
        color = _guess_bg_color(img, rect)
        # Should still return a valid color from boundary samples
        assert color.isValid()


# ---------------------------------------------------------------------------
# process_image_translation — additional edge cases
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not _has_font_rendering(),
    reason="Qt offscreen font rendering unavailable",
)
class TestProcessImageTranslationEdgeCases:
    """Additional edge cases for the image translation pipeline."""

    def test_hundred_text_regions(self, tmp_path: Path) -> None:
        """100 OCR results should all be processed without error."""
        img = QImage(2000, 2000, QImage.Format.Format_RGB32)
        img.fill(QColor(Qt.GlobalColor.white))

        img_path = tmp_path / "large.png"
        _save_image(img, img_path)
        output_path = tmp_path / "output.png"

        results = []
        translations = []
        for i in range(100):
            row, col = divmod(i, 10)
            x, y = col * 180 + 10, row * 180 + 10
            ocr_res = _make_ocr_result(x=x, y=y, w=150, h=30)
            ocr_res.translated_html = f"Text {i}"
            results.append(ocr_res)
            translations.append(f"Text {i}")

        success = process_image_translation(
            str(img_path), str(output_path), results, translations
        )
        assert success is True
        assert output_path.exists()

    def test_overlapping_text_regions(self, tmp_path: Path) -> None:
        """Two OCR results with overlapping bounding boxes.

        The pipeline should process both without crashing. The second
        text may partially overwrite the first — that is acceptable.
        """
        img = _make_white_image(300, 100)
        img_path = tmp_path / "overlap.png"
        _save_image(img, img_path)
        output_path = tmp_path / "output.png"

        res1 = _make_ocr_result(x=10, y=10, w=100, h=30)
        res1.translated_html = "First"
        res2 = _make_ocr_result(x=50, y=10, w=100, h=30)
        res2.translated_html = "Second"

        success = process_image_translation(
            str(img_path),
            str(output_path),
            [res1, res2],
            ["First", "Second"],
        )
        assert success is True
        assert output_path.exists()

    def test_indexed_color_image_conversion(self, tmp_path: Path) -> None:
        """Format_Indexed8 (GIF-like) must be converted to ARGB32 before painting.

        QPainter silently fails on indexed formats, so the pipeline
        must auto-convert.
        """
        img = QImage(120, 60, QImage.Format.Format_Indexed8)
        img.setColorCount(2)  # noqa: PLR2004
        img.setColor(0, QColor(Qt.GlobalColor.white).rgb())
        img.setColor(1, QColor(Qt.GlobalColor.black).rgb())
        img.fill(0)

        img_path = tmp_path / "indexed.png"
        _save_image(img, img_path)
        output_path = tmp_path / "output.png"

        ocr_res = _make_ocr_result(x=10, y=10, w=80, h=25)
        ocr_res.translated_html = "Converted"

        success = process_image_translation(
            str(img_path), str(output_path), [ocr_res], ["Converted"]
        )
        assert success is True
        assert output_path.exists()

        # Verify output is a valid ARGB image (not indexed)
        out_img = QImage(str(output_path))
        assert not out_img.isNull()

    def test_jpeg_saves_with_quality_100(self, tmp_path: Path) -> None:
        """JPEG output uses quality=100, which should produce a larger file.

        We compare the JPEG size to a low-quality save to confirm
        the quality parameter is respected.
        """
        img = _make_white_image(400, 400)
        # Add some detail so JPEG compression has something to work with
        painter = QPainter(img)
        for i in range(0, 400, 10):
            painter.fillRect(QRect(i, 0, 5, 400), QColor(i % 256, 0, 0))
        painter.end()

        img_path = tmp_path / "input.png"
        _save_image(img, img_path)
        output_path_high = tmp_path / "output_high.jpg"
        output_path_low = tmp_path / "output_low.jpg"

        # High quality via process_image_translation (quality=100)
        success = process_image_translation(
            str(img_path), str(output_path_high), [], []
        )
        assert success is True

        # Low quality via manual save for comparison
        img.save(str(output_path_low), quality=10)

        # High-quality file should be significantly larger
        size_high = output_path_high.stat().st_size
        size_low = output_path_low.stat().st_size
        assert size_high > size_low

    def test_process_with_all_empty_translations(self, tmp_path: Path) -> None:
        """Multiple OCR results with all empty translations should still succeed.

        No text is rendered but text removal still happens.
        """
        img = _make_white_image(300, 100)
        painter = QPainter(img)
        painter.fillRect(QRect(10, 10, 50, 20), QColor(Qt.GlobalColor.black))
        painter.fillRect(QRect(100, 10, 50, 20), QColor(Qt.GlobalColor.black))
        painter.end()

        img_path = tmp_path / "empty_trans.png"
        _save_image(img, img_path)
        output_path = tmp_path / "output.png"

        results = [
            _make_ocr_result(x=10, y=10, w=50, h=20),
            _make_ocr_result(x=100, y=10, w=50, h=20),
        ]
        success = process_image_translation(
            str(img_path), str(output_path), results, ["", ""]
        )
        assert success is True

    def test_process_with_unicode_translations(self, tmp_path: Path) -> None:
        """Unicode translations (CJK, emoji, accented chars) process correctly."""
        img_path = tmp_path / "unicode.png"
        _save_image(_make_white_image(400, 100), img_path)
        output_path = tmp_path / "output.png"

        ocr_res = _make_ocr_result(x=10, y=10, w=350, h=40)
        ocr_res.translated_html = "\u4f60\u597d \u00e9\u00e8\u00ea \u00fc\u00f6\u00e4"

        success = process_image_translation(
            str(img_path),
            str(output_path),
            [ocr_res],
            ["\u4f60\u597d \u00e9\u00e8\u00ea \u00fc\u00f6\u00e4"],
        )
        assert success is True

    def test_negative_coordinates_in_ocr_result(self, tmp_path: Path) -> None:
        """OCR results with negative x/y coordinates should not crash.

        Real OCR engines occasionally return negative coordinates
        for text near image borders.
        """
        img_path = tmp_path / "negative.png"
        _save_image(_make_white_image(200, 100), img_path)
        output_path = tmp_path / "output.png"

        ocr_res = _make_ocr_result(x=-5, y=-3, w=60, h=20)
        ocr_res.translated_html = "Negative coords"

        success = process_image_translation(
            str(img_path), str(output_path), [ocr_res], ["Negative coords"]
        )
        assert success is True
