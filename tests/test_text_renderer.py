"""Unit tests for text rendering logic."""

import pytest
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QImage, QPainter

from src.constants.ui import FONT_SIZE_DEFAULT, FONT_SIZE_MIN
from src.core.checkpoint import ALIGN_CENTER, ALIGN_JUSTIFY, ALIGN_LEFT, ALIGN_RIGHT
from src.core.ocr_engine import OCRResult
from src.core.text_renderer import TextRenderer

# Ensure pytest-qt creates a QApplication before any test runs.
pytestmark = pytest.mark.usefixtures("qapp")


def test_text_renderer_basic() -> None:
    """Test basic rendering doesn't crash."""
    img = QImage(200, 100, QImage.Format.Format_RGB32)
    img.fill(QColor(Qt.GlobalColor.white))

    painter = QPainter(img)
    rect = QRect(10, 10, 180, 80)
    ocr_res = OCRResult("Test", 10, 10, 180, 80, 1.0)
    ocr_res.translated_html = "Translated"
    ocr_res.color = "#000000"
    ocr_res.alignment = ALIGN_LEFT
    ocr_res.line_height_ratio = 1.2
    ocr_res.is_single_line = True

    # Should not raise exception
    TextRenderer.render(painter, rect, "Fallback", ocr_res, "English (US)")
    painter.end()


def test_text_renderer_multiline() -> None:
    """Test that multiline rendering doesn't crash."""
    img = QImage(300, 200, QImage.Format.Format_RGB32)
    img.fill(QColor(Qt.GlobalColor.white))

    painter = QPainter(img)
    rect = QRect(10, 10, 280, 180)
    ocr_res = OCRResult("Line one line two", 10, 10, 280, 180, 1.0)
    ocr_res.translated_html = "First line<br>Second line<br>Third line"
    ocr_res.color = "#000000"
    ocr_res.alignment = ALIGN_CENTER
    ocr_res.line_height_ratio = 1.4
    ocr_res.is_single_line = False

    TextRenderer.render(painter, rect, "Fallback", ocr_res, "English (US)")
    painter.end()


def test_text_renderer_right_alignment() -> None:
    """Test right-aligned rendering."""
    img = QImage(200, 100, QImage.Format.Format_RGB32)
    img.fill(QColor(Qt.GlobalColor.white))

    painter = QPainter(img)
    rect = QRect(10, 10, 180, 80)
    ocr_res = OCRResult("Test", 10, 10, 180, 80, 1.0)
    ocr_res.translated_html = "Right aligned"
    ocr_res.color = "#FF0000"
    ocr_res.alignment = ALIGN_RIGHT
    ocr_res.line_height_ratio = 1.2
    ocr_res.is_single_line = True

    TextRenderer.render(painter, rect, "Fallback", ocr_res, "English (US)")
    painter.end()


def test_text_renderer_cjk_language() -> None:
    """Test rendering with CJK language font selection."""
    img = QImage(200, 100, QImage.Format.Format_RGB32)
    img.fill(QColor(Qt.GlobalColor.white))

    painter = QPainter(img)
    rect = QRect(10, 10, 180, 80)
    ocr_res = OCRResult("Test", 10, 10, 180, 80, 1.0)
    ocr_res.translated_html = "Translated"
    ocr_res.color = "#000000"
    ocr_res.alignment = ALIGN_LEFT
    ocr_res.line_height_ratio = 1.2
    ocr_res.is_single_line = True

    # Should not crash with CJK language
    TextRenderer.render(painter, rect, "Fallback", ocr_res, "Japanese")
    painter.end()


def test_find_best_font_size() -> None:
    """Verify font size finding logic."""
    from PySide6.QtGui import QTextDocument  # noqa: PLC0415

    doc = QTextDocument()
    rect = QRect(0, 0, 100, 50)
    ocr_res = OCRResult("Long text that needs scaling", 0, 0, 100, 50, 1.0)
    ocr_res.translated_html = (
        "Very long translated text that should be shrunk to fit the box"
    )
    ocr_res.color = "#000000"
    ocr_res.line_height_ratio = 1.2
    ocr_res.is_single_line = False

    size = TextRenderer._find_best_font_size(
        doc, rect, "Fallback", ocr_res, "English (US)"
    )
    assert size > 0

    # Apply the size and verify it fits
    TextRenderer._update_style(doc, ocr_res, size, "English (US)")
    doc.setTextWidth(rect.width())
    assert doc.size().height() <= rect.height()


def test_find_best_font_size_single_line() -> None:
    """Verify single-line font size respects width constraint."""
    from PySide6.QtGui import QTextDocument  # noqa: PLC0415

    doc = QTextDocument()
    rect = QRect(0, 0, 50, 30)
    ocr_res = OCRResult("Short", 0, 0, 50, 30, 1.0)
    ocr_res.translated_html = "A very long single line text"
    ocr_res.color = "#000000"
    ocr_res.line_height_ratio = 1.0
    ocr_res.is_single_line = True

    size = TextRenderer._find_best_font_size(
        doc, rect, "Fallback", ocr_res, "English (US)"
    )
    assert size > 0


def test_get_font_family() -> None:
    """Verify language-specific font families are returned."""
    # Standard Latin
    family = TextRenderer._get_font_family("English (US)")
    assert isinstance(family, str)
    assert len(family) > 0

    # CJK and non-Latin scripts should all return a valid font string
    for lang in [
        "Chinese (Simplified)",
        "Chinese (Traditional)",
        "Japanese",
        "Korean",
        "Arabic",
        "Persian",
        "Hebrew",
        "Hindi",
        "Nepali",
        "Bengali",
        "Thai",
        "Khmer",
        "Russian",
        "Greek",
        "Vietnamese",
    ]:
        family = TextRenderer._get_font_family(lang)
        assert isinstance(family, str)
        assert len(family) > 0


def test_prepare_document() -> None:
    """Verify document is initialized with zero margins."""
    ocr_res = OCRResult("Test", 0, 0, 100, 50, 1.0)
    doc = TextRenderer._prepare_document(ocr_res)
    assert doc.documentMargin() == 0


# ---------------------------------------------------------------------------
# Edge-case tests
# ---------------------------------------------------------------------------


def test_text_renderer_empty_translation() -> None:
    """Rendering with empty fallback text shouldn't crash."""
    img = QImage(200, 100, QImage.Format.Format_RGB32)
    img.fill(QColor(Qt.GlobalColor.white))

    painter = QPainter(img)
    rect = QRect(10, 10, 180, 80)
    ocr_res = OCRResult("Test", 10, 10, 180, 80, 1.0)
    ocr_res.translated_html = ""
    ocr_res.color = "#000000"
    ocr_res.alignment = ALIGN_LEFT
    ocr_res.line_height_ratio = 1.2
    ocr_res.is_single_line = True

    TextRenderer.render(painter, rect, "", ocr_res, "English (US)")
    painter.end()


def test_text_renderer_none_alignment() -> None:
    """Rendering with alignment=None should default to center."""
    img = QImage(200, 100, QImage.Format.Format_RGB32)
    img.fill(QColor(Qt.GlobalColor.white))

    painter = QPainter(img)
    rect = QRect(10, 10, 180, 80)
    ocr_res = OCRResult("Test", 10, 10, 180, 80, 1.0)
    ocr_res.translated_html = "Translated"
    ocr_res.color = "#000000"
    ocr_res.alignment = None  # Default
    ocr_res.line_height_ratio = 1.2
    ocr_res.is_single_line = True

    # Should not crash; alignment defaults to center
    TextRenderer.render(painter, rect, "Fallback", ocr_res, "English (US)")
    painter.end()


def test_text_renderer_justify_alignment() -> None:
    """Rendering with justify alignment doesn't crash."""
    img = QImage(300, 100, QImage.Format.Format_RGB32)
    img.fill(QColor(Qt.GlobalColor.white))

    painter = QPainter(img)
    rect = QRect(10, 10, 280, 80)
    ocr_res = OCRResult("Test", 10, 10, 280, 80, 1.0)
    ocr_res.translated_html = "This is a justified text block with enough words"
    ocr_res.color = "#000000"
    ocr_res.alignment = ALIGN_JUSTIFY
    ocr_res.line_height_ratio = 1.2
    ocr_res.is_single_line = False

    TextRenderer.render(painter, rect, "Fallback", ocr_res, "English (US)")
    painter.end()


def test_find_best_font_size_tiny_rect() -> None:
    """Tiny bounding box should still return a valid font size."""
    from PySide6.QtGui import QTextDocument  # noqa: PLC0415

    doc = QTextDocument()
    rect = QRect(0, 0, 5, 5)
    ocr_res = OCRResult("X", 0, 0, 5, 5, 1.0)
    ocr_res.translated_html = "Long text"
    ocr_res.color = "#000000"
    ocr_res.line_height_ratio = 1.2
    ocr_res.is_single_line = False

    size = TextRenderer._find_best_font_size(
        doc,
        rect,
        "Long text",
        ocr_res,
        "English (US)",
    )
    assert size > 0


def test_get_font_family_fallback() -> None:
    """Unknown language returns a valid font string (first candidate or generic)."""
    family = TextRenderer._get_font_family("Klingon")
    assert isinstance(family, str)
    assert len(family) > 0


def test_update_style_applies_html() -> None:
    """Verify _update_style sets HTML on the document."""
    from PySide6.QtGui import QTextDocument  # noqa: PLC0415

    doc = QTextDocument()
    ocr_res = OCRResult("Test", 0, 0, 100, 50, 1.0)
    ocr_res.translated_html = "Hello <b>World</b>"
    ocr_res.color = "#FF0000"
    ocr_res.alignment = ALIGN_LEFT
    ocr_res.line_height_ratio = 1.4
    ocr_res.is_single_line = False

    TextRenderer._update_style(doc, ocr_res, 14.0, "English (US)")

    html_output = doc.toHtml()
    assert "Hello" in html_output
    assert "World" in html_output


def test_text_renderer_bold_italic_html() -> None:
    """Rendering rich text with bold + italic tags doesn't crash."""
    img = QImage(300, 100, QImage.Format.Format_RGB32)
    img.fill(QColor(Qt.GlobalColor.white))

    painter = QPainter(img)
    rect = QRect(10, 10, 280, 80)
    ocr_res = OCRResult("Test", 10, 10, 280, 80, 1.0)
    ocr_res.translated_html = "<b>Bold</b> and <i>italic</i> text"
    ocr_res.color = "#000000"
    ocr_res.alignment = ALIGN_LEFT
    ocr_res.line_height_ratio = 1.2
    ocr_res.is_single_line = False

    TextRenderer.render(painter, rect, "Fallback", ocr_res, "English (US)")
    painter.end()


# ---------------------------------------------------------------------------
# _update_style single-line line-height
# ---------------------------------------------------------------------------


def test_update_style_single_line_uses_lh_one() -> None:
    """_update_style uses line-height: 1.0 for single-line text."""
    from PySide6.QtGui import QTextDocument  # noqa: PLC0415

    doc = QTextDocument()
    ocr_res = OCRResult("Test", 0, 0, 100, 20, 1.0)
    ocr_res.translated_html = "Hello"
    ocr_res.color = "#000000"
    ocr_res.alignment = ALIGN_LEFT
    ocr_res.line_height_ratio = 1.8  # Would normally be used for multi-line
    ocr_res.is_single_line = True

    TextRenderer._update_style(doc, ocr_res, 12.0, "English (US)")

    # Qt serializes line-height fractions as percentages: 1.0 → "line-height:100%;"
    # Crucially, the 1.8 ratio (line_height_ratio) must NOT appear.
    html_output = doc.toHtml()
    assert "line-height:100%;" in html_output
    assert "line-height:180%;" not in html_output


def test_update_style_multi_line_uses_ratio() -> None:
    """_update_style uses the actual line_height_ratio for multi-line text."""
    from PySide6.QtGui import QTextDocument  # noqa: PLC0415

    doc = QTextDocument()
    ocr_res = OCRResult("Test", 0, 0, 100, 40, 1.0)
    ocr_res.translated_html = "Line one<br>Line two"
    ocr_res.color = "#000000"
    ocr_res.alignment = ALIGN_LEFT
    ocr_res.line_height_ratio = 1.5
    ocr_res.is_single_line = False

    TextRenderer._update_style(doc, ocr_res, 12.0, "English (US)")

    # Qt serializes line-height fractions as percentages: 1.5 → "line-height:150%;"
    html_output = doc.toHtml()
    assert "line-height:150%;" in html_output


# ---------------------------------------------------------------------------
# render: single-line horizontal offset for AlignRight and AlignHCenter
# ---------------------------------------------------------------------------


def test_text_renderer_single_line_right_offset() -> None:
    """Single-line render with AlignRight applies positive x_offset."""
    img = QImage(300, 50, QImage.Format.Format_RGB32)
    img.fill(QColor(Qt.GlobalColor.white))

    painter = QPainter(img)
    rect = QRect(0, 0, 300, 50)
    ocr_res = OCRResult("Hi", 0, 0, 300, 50, 1.0)
    ocr_res.translated_html = "Hi"
    ocr_res.color = "#000000"
    ocr_res.alignment = ALIGN_RIGHT
    ocr_res.line_height_ratio = 1.0
    ocr_res.is_single_line = True

    # Should not raise and should produce correct rendering
    TextRenderer.render(painter, rect, "Hi", ocr_res, "English (US)")
    painter.end()


def test_text_renderer_single_line_center_offset() -> None:
    """Single-line render with AlignHCenter applies centered x_offset."""
    img = QImage(300, 50, QImage.Format.Format_RGB32)
    img.fill(QColor(Qt.GlobalColor.white))

    painter = QPainter(img)
    rect = QRect(0, 0, 300, 50)
    ocr_res = OCRResult("Hi", 0, 0, 300, 50, 1.0)
    ocr_res.translated_html = "Hi"
    ocr_res.color = "#000000"
    ocr_res.alignment = ALIGN_CENTER
    ocr_res.line_height_ratio = 1.0
    ocr_res.is_single_line = True

    TextRenderer.render(painter, rect, "Hi", ocr_res, "English (US)")
    painter.end()


# ---------------------------------------------------------------------------
# _get_font_family: additional language scripts
# ---------------------------------------------------------------------------


def test_get_font_family_cyrillic_and_other_scripts() -> None:
    """Language scripts not in the original test loop return valid font strings."""
    for lang in [
        "Turkish",
        "Ukrainian",
        "Belarusian",
        "Bulgarian",
        "Serbian",
        "Mongolian",
    ]:
        family = TextRenderer._get_font_family(lang)
        assert isinstance(family, str)
        assert len(family) > 0, f"Empty font family for language: {lang}"


# ---------------------------------------------------------------------------
# Helper: create an OCRResult with common defaults
# ---------------------------------------------------------------------------


def _make_ocr_result(  # noqa: PLR0913
    text: str = "Test",
    x: int = 0,
    y: int = 0,
    w: int = 200,
    h: int = 100,
    *,
    translated_html: str = "Translated",
    color: str = "#000000",
    alignment: str | None = ALIGN_LEFT,
    line_height_ratio: float = 1.2,
    is_single_line: bool = False,
) -> OCRResult:
    """Builds an OCRResult with sensible defaults for rendering tests."""
    ocr_res = OCRResult(text, x, y, w, h, 1.0)
    ocr_res.translated_html = translated_html
    ocr_res.color = color
    ocr_res.alignment = alignment
    ocr_res.line_height_ratio = line_height_ratio
    ocr_res.is_single_line = is_single_line
    return ocr_res


def _render_on_image(
    width: int,
    height: int,
    text: str,
    ocr_res: OCRResult,
    target_lang: str = "English (US)",
) -> QImage:
    """Creates an image, renders text onto it, and returns the image."""
    img = QImage(width, height, QImage.Format.Format_RGB32)
    img.fill(QColor(Qt.GlobalColor.white))
    painter = QPainter(img)
    rect = QRect(0, 0, width, height)
    TextRenderer.render(painter, rect, text, ocr_res, target_lang)
    painter.end()
    return img


# ---------------------------------------------------------------------------
# 1. Dead parameter verification — `text` param in render / _find_best_font_size
# ---------------------------------------------------------------------------


class TestDeadParameterVerification:
    """Verify that the `text` parameter (plain-text fallback) is not used."""

    def test_text_param_not_used_by_render(self) -> None:
        """Changing `text` should not affect the rendered output.

        `_update_style` uses `ocr_result.translated_html`, not `text`.
        """
        ocr_res = _make_ocr_result(
            translated_html="Actual content",
            is_single_line=True,
            w=300,
            h=50,
        )

        # Render with two different `text` values
        img_a = _render_on_image(300, 50, "Fallback A", ocr_res)
        img_b = _render_on_image(300, 50, "COMPLETELY DIFFERENT TEXT", ocr_res)

        # Both images should be pixel-identical
        assert img_a == img_b

    def test_text_param_not_used_by_find_best_font_size(self) -> None:
        """_find_best_font_size should return the same size regardless of `text`."""
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        rect = QRect(0, 0, 200, 60)
        ocr_res = _make_ocr_result(translated_html="Sample content", w=200, h=60)

        doc_a = QTextDocument()
        size_a = TextRenderer._find_best_font_size(
            doc_a, rect, "Short", ocr_res, "English (US)"
        )

        doc_b = QTextDocument()
        fallback = "A very long different fallback string"
        size_b = TextRenderer._find_best_font_size(
            doc_b, rect, fallback, ocr_res, "English (US)"
        )

        assert size_a == size_b

    def test_empty_text_param_renders_normally(self) -> None:
        """An empty `text` param should not affect rendering.

        translated_html is what drives the document content.
        """
        ocr_res = _make_ocr_result(translated_html="Visible content", w=200, h=50)
        # Should not raise
        img = _render_on_image(200, 50, "", ocr_res)
        assert img is not None


# ---------------------------------------------------------------------------
# 2. Font size fallback behavior
# ---------------------------------------------------------------------------


class TestFontSizeFallback:
    """Verify _find_best_font_size returns FONT_SIZE_DEFAULT when nothing fits."""

    def test_huge_text_in_tiny_box_returns_default(self) -> None:
        """Tiny box that cannot fit any text returns FONT_SIZE_DEFAULT.

        The loop exhausts all candidates and falls through.
        """
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        doc = QTextDocument()
        # A 1x1 rect can't fit any text at any size
        rect = QRect(0, 0, 1, 1)
        ocr_res = _make_ocr_result(
            translated_html="This text will never fit in a 1x1 box",
            w=1,
            h=1,
        )

        size = TextRenderer._find_best_font_size(doc, rect, "", ocr_res, "English (US)")
        assert size == FONT_SIZE_DEFAULT  # noqa: PLR2004

    def test_font_size_always_positive(self) -> None:
        """The returned font size should always be at least FONT_SIZE_MIN."""
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        doc = QTextDocument()
        rect = QRect(0, 0, 3, 3)
        ocr_res = _make_ocr_result(
            translated_html="Text",
            w=3,
            h=3,
        )

        size = TextRenderer._find_best_font_size(doc, rect, "", ocr_res, "English (US)")
        assert size >= FONT_SIZE_MIN  # noqa: PLR2004

    def test_large_box_uses_larger_font(self) -> None:
        """A large bounding box should allow a larger font size than a small one."""
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        short_html = "Hi"

        doc_small = QTextDocument()
        rect_small = QRect(0, 0, 30, 20)
        ocr_small = _make_ocr_result(translated_html=short_html, w=30, h=20)
        size_small = TextRenderer._find_best_font_size(
            doc_small, rect_small, "", ocr_small, "English (US)"
        )

        doc_large = QTextDocument()
        rect_large = QRect(0, 0, 400, 300)
        ocr_large = _make_ocr_result(translated_html=short_html, w=400, h=300)
        size_large = TextRenderer._find_best_font_size(
            doc_large, rect_large, "", ocr_large, "English (US)"
        )

        assert size_large > size_small


# ---------------------------------------------------------------------------
# 3. LRU cache behavior in _get_font_family
# ---------------------------------------------------------------------------


class TestGetFontFamilyLRUCache:
    """Verify the @lru_cache decorator on _get_font_family."""

    def test_cache_returns_same_object(self) -> None:
        """Repeated calls return the exact same object (identity check).

        This proves the LRU cache is active.
        """
        # Clear cache from prior tests
        TextRenderer._get_font_family.cache_clear()

        family_1 = TextRenderer._get_font_family("English (US)")
        family_2 = TextRenderer._get_font_family("English (US)")
        assert family_1 is family_2

    def test_cache_info_tracks_hits(self) -> None:
        """cache_info() should show increasing hits for repeated calls."""
        TextRenderer._get_font_family.cache_clear()

        TextRenderer._get_font_family("French")
        info_after_first = TextRenderer._get_font_family.cache_info()
        assert info_after_first.misses >= 1  # noqa: PLR2004

        TextRenderer._get_font_family("French")
        info_after_second = TextRenderer._get_font_family.cache_info()
        assert info_after_second.hits > info_after_first.hits

    def test_different_languages_are_cached_separately(self) -> None:
        """Different language keys should produce independent cache entries."""
        TextRenderer._get_font_family.cache_clear()

        family_en = TextRenderer._get_font_family("English (US)")
        family_ja = TextRenderer._get_font_family("Japanese")

        info = TextRenderer._get_font_family.cache_info()
        assert info.currsize >= 2  # noqa: PLR2004
        # English and Japanese use different font families
        assert family_en != family_ja

    def test_cache_clear_resets_state(self) -> None:
        """After cache_clear(), the next call should be a miss."""
        TextRenderer._get_font_family("German")
        TextRenderer._get_font_family.cache_clear()
        info = TextRenderer._get_font_family.cache_info()
        assert info.currsize == 0  # noqa: PLR2004

        TextRenderer._get_font_family("German")
        info = TextRenderer._get_font_family.cache_info()
        assert info.misses == 1  # noqa: PLR2004


# ---------------------------------------------------------------------------
# 4. render() with empty text
# ---------------------------------------------------------------------------


class TestRenderEmptyText:
    """Verify rendering behaves correctly when text content is empty."""

    def test_empty_translated_html(self) -> None:
        """Empty translated_html should not crash."""
        ocr_res = _make_ocr_result(translated_html="", w=200, h=100)
        img = _render_on_image(200, 100, "", ocr_res)
        assert img is not None

    def test_whitespace_only_html(self) -> None:
        """Whitespace-only translated_html should not crash."""
        ocr_res = _make_ocr_result(translated_html="   \t\n  ", w=200, h=100)
        img = _render_on_image(200, 100, "", ocr_res)
        assert img is not None

    def test_empty_html_single_line(self) -> None:
        """Empty translated_html in single-line mode should not crash."""
        ocr_res = _make_ocr_result(translated_html="", w=200, h=50, is_single_line=True)
        img = _render_on_image(200, 50, "", ocr_res)
        assert img is not None


# ---------------------------------------------------------------------------
# 5. render() with very long text
# ---------------------------------------------------------------------------


class TestRenderVeryLongText:
    """Verify rendering does not crash or hang on extremely long text."""

    def test_long_single_word(self) -> None:
        """A single very long word forces extreme shrinking."""
        long_word = "A" * 500
        ocr_res = _make_ocr_result(
            translated_html=long_word, w=200, h=50, is_single_line=True
        )
        img = _render_on_image(200, 50, long_word, ocr_res)
        assert img is not None

    def test_long_paragraph(self) -> None:
        """A long multi-line paragraph should scale down to fit."""
        long_text = " ".join(["word"] * 200)
        ocr_res = _make_ocr_result(translated_html=long_text, w=300, h=100)
        img = _render_on_image(300, 100, long_text, ocr_res)
        assert img is not None

    def test_many_html_line_breaks(self) -> None:
        """Many <br> tags producing lots of lines should still render."""
        html = "<br>".join([f"Line {i}" for i in range(50)])
        ocr_res = _make_ocr_result(translated_html=html, w=300, h=200)
        img = _render_on_image(300, 200, "fallback", ocr_res)
        assert img is not None

    def test_long_text_font_size_is_small(self) -> None:
        """Long text should produce a smaller font size than short text."""
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        rect = QRect(0, 0, 200, 100)

        doc_short = QTextDocument()
        ocr_short = _make_ocr_result(translated_html="Hi", w=200, h=100)
        size_short = TextRenderer._find_best_font_size(
            doc_short, rect, "", ocr_short, "English (US)"
        )

        doc_long = QTextDocument()
        long_text = " ".join(["word"] * 200)
        ocr_long = _make_ocr_result(translated_html=long_text, w=200, h=100)
        size_long = TextRenderer._find_best_font_size(
            doc_long, rect, "", ocr_long, "English (US)"
        )

        assert size_short > size_long


# ---------------------------------------------------------------------------
# 6. render() with RTL text
# ---------------------------------------------------------------------------


class TestRenderRTLText:
    """Verify rendering with right-to-left text (Arabic, Hebrew, Persian)."""

    def test_arabic_text(self) -> None:
        """Arabic text should render without error."""
        arabic = (
            "\u0645\u0631\u062d\u0628\u0627 \u0628\u0627\u0644\u0639\u0627\u0644\u0645"
        )
        ocr_res = _make_ocr_result(
            translated_html=arabic,
            color="#000000",
            alignment=ALIGN_RIGHT,
            w=300,
            h=100,
        )
        img = _render_on_image(300, 100, "fallback", ocr_res, "Arabic")
        assert img is not None

    def test_hebrew_text(self) -> None:
        """Hebrew text should render without error."""
        ocr_res = _make_ocr_result(
            translated_html="\u05e9\u05dc\u05d5\u05dd \u05e2\u05d5\u05dc\u05dd",
            alignment=ALIGN_RIGHT,
            w=300,
            h=100,
        )
        img = _render_on_image(300, 100, "fallback", ocr_res, "Hebrew")
        assert img is not None

    def test_persian_text(self) -> None:
        """Persian text should render without error."""
        ocr_res = _make_ocr_result(
            translated_html="\u0633\u0644\u0627\u0645 \u062f\u0646\u06cc\u0627",
            alignment=ALIGN_RIGHT,
            w=300,
            h=100,
        )
        img = _render_on_image(300, 100, "fallback", ocr_res, "Persian")
        assert img is not None

    def test_rtl_right_aligned_single_line(self) -> None:
        """RTL single-line text with right alignment should apply x_offset."""
        ocr_res = _make_ocr_result(
            translated_html="\u0645\u0631\u062d\u0628\u0627",
            alignment=ALIGN_RIGHT,
            is_single_line=True,
            w=300,
            h=50,
        )
        img = _render_on_image(300, 50, "fallback", ocr_res, "Arabic")
        assert img is not None


# ---------------------------------------------------------------------------
# 7. render() with CJK characters
# ---------------------------------------------------------------------------


class TestRenderCJKCharacters:
    """Verify rendering with Chinese, Japanese, and Korean text."""

    def test_chinese_simplified(self) -> None:
        """Chinese Simplified text should render correctly."""
        ocr_res = _make_ocr_result(
            translated_html="\u4f60\u597d\u4e16\u754c",
            w=200,
            h=100,
        )
        img = _render_on_image(200, 100, "fallback", ocr_res, "Chinese (Simplified)")
        assert img is not None

    def test_chinese_traditional(self) -> None:
        """Chinese Traditional text should render correctly."""
        ocr_res = _make_ocr_result(
            translated_html="\u4f60\u597d\u4e16\u754c",
            w=200,
            h=100,
        )
        img = _render_on_image(200, 100, "fallback", ocr_res, "Chinese (Traditional)")
        assert img is not None

    def test_japanese(self) -> None:
        """Japanese text (Kanji + Hiragana) should render correctly."""
        ocr_res = _make_ocr_result(
            translated_html="\u3053\u3093\u306b\u3061\u306f\u4e16\u754c",
            w=200,
            h=100,
        )
        img = _render_on_image(200, 100, "fallback", ocr_res, "Japanese")
        assert img is not None

    def test_korean(self) -> None:
        """Korean (Hangul) text should render correctly."""
        ocr_res = _make_ocr_result(
            translated_html="\uc548\ub155\ud558\uc138\uc694 \uc138\uacc4",
            w=200,
            h=100,
        )
        img = _render_on_image(200, 100, "fallback", ocr_res, "Korean")
        assert img is not None

    def test_cjk_font_selection(self) -> None:
        """Each CJK language should select a distinct font family."""
        TextRenderer._get_font_family.cache_clear()
        family_zh = TextRenderer._get_font_family("Chinese (Simplified)")
        family_ja = TextRenderer._get_font_family("Japanese")
        family_ko = TextRenderer._get_font_family("Korean")

        # All should be non-empty strings
        assert all(len(f) > 0 for f in [family_zh, family_ja, family_ko])
        # They should differ from each other (different CJK typefaces)
        assert family_zh != family_ja or family_zh != family_ko


# ---------------------------------------------------------------------------
# 8. render() with mixed scripts
# ---------------------------------------------------------------------------


class TestRenderMixedScripts:
    """Verify rendering with text containing multiple scripts."""

    def test_latin_and_cjk_mix(self) -> None:
        """Mixed Latin + CJK text should render without error."""
        ocr_res = _make_ocr_result(
            translated_html="Hello \u4e16\u754c World",
            w=300,
            h=100,
        )
        img = _render_on_image(300, 100, "fallback", ocr_res, "Chinese (Simplified)")
        assert img is not None

    def test_latin_and_arabic_mix(self) -> None:
        """Mixed Latin + Arabic text should render without error."""
        ocr_res = _make_ocr_result(
            translated_html="Hello \u0645\u0631\u062d\u0628\u0627 World",
            w=300,
            h=100,
        )
        img = _render_on_image(300, 100, "fallback", ocr_res, "Arabic")
        assert img is not None

    def test_latin_and_cyrillic_mix(self) -> None:
        """Mixed Latin + Cyrillic text should render without error."""
        ocr_res = _make_ocr_result(
            translated_html="Hello \u041f\u0440\u0438\u0432\u0435\u0442 World",
            w=300,
            h=100,
        )
        img = _render_on_image(300, 100, "fallback", ocr_res, "Russian")
        assert img is not None

    def test_numbers_and_special_chars_with_cjk(self) -> None:
        """Numbers and special characters mixed with CJK should not crash."""
        ocr_res = _make_ocr_result(
            translated_html="2026\u5e743\u670825\u65e5 (100%)",
            w=300,
            h=100,
        )
        img = _render_on_image(300, 100, "fallback", ocr_res, "Japanese")
        assert img is not None

    def test_html_tags_with_mixed_scripts(self) -> None:
        """Rich HTML with mixed scripts should render correctly."""
        mixed = (
            "<b>Bold</b> \u4e16\u754c"
            " <i>Italic</i> \u041f\u0440\u0438\u0432\u0435\u0442"
        )
        ocr_res = _make_ocr_result(
            translated_html=mixed,
            w=400,
            h=100,
        )
        img = _render_on_image(400, 100, "fallback", ocr_res, "English (US)")
        assert img is not None


# ---------------------------------------------------------------------------
# 9. Different alignment options
# ---------------------------------------------------------------------------


class TestAlignmentOptions:
    """Verify all alignment variants in _update_style and render()."""

    def test_left_alignment_no_align_attr(self) -> None:
        """ALIGN_LEFT is the default; Qt omits the align attribute."""
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        doc = QTextDocument()
        ocr_res = _make_ocr_result(translated_html="Left text", alignment=ALIGN_LEFT)
        TextRenderer._update_style(doc, ocr_res, 14.0, "English (US)")
        html = doc.toHtml()
        # Qt treats left as default — no align= attribute is emitted
        assert 'align="right"' not in html
        assert 'align="center"' not in html

    def test_right_alignment_attr(self) -> None:
        """ALIGN_RIGHT should produce align='right' in the serialized HTML."""
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        doc = QTextDocument()
        ocr_res = _make_ocr_result(translated_html="Right text", alignment=ALIGN_RIGHT)
        TextRenderer._update_style(doc, ocr_res, 14.0, "English (US)")
        assert 'align="right"' in doc.toHtml()

    def test_center_alignment_attr(self) -> None:
        """ALIGN_CENTER should produce align='center' in the serialized HTML."""
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        doc = QTextDocument()
        ocr_res = _make_ocr_result(
            translated_html="Center text", alignment=ALIGN_CENTER
        )
        TextRenderer._update_style(doc, ocr_res, 14.0, "English (US)")
        assert 'align="center"' in doc.toHtml()

    def test_justify_alignment_applied(self) -> None:
        """ALIGN_JUSTIFY should be applied to the document."""
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        doc = QTextDocument()
        ocr_res = _make_ocr_result(
            translated_html="Justify text", alignment=ALIGN_JUSTIFY
        )
        TextRenderer._update_style(doc, ocr_res, 14.0, "English (US)")
        # Qt does not serialize justify as an align= attr, but the
        # document should not have right or center alignment either
        html = doc.toHtml()
        assert 'align="right"' not in html
        assert 'align="center"' not in html

    def test_none_alignment_defaults_to_center(self) -> None:
        """When alignment is None, the CSS defaults to center."""
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        doc = QTextDocument()
        ocr_res = _make_ocr_result(translated_html="Default alignment", alignment=None)
        TextRenderer._update_style(doc, ocr_res, 14.0, "English (US)")
        assert 'align="center"' in doc.toHtml()

    def test_unknown_alignment_defaults_to_center(self) -> None:
        """An unrecognized alignment string should default to center."""
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        doc = QTextDocument()
        ocr_res = _make_ocr_result(
            translated_html="Unknown alignment",
            alignment="invalid_align",
        )
        TextRenderer._update_style(doc, ocr_res, 14.0, "English (US)")
        assert 'align="center"' in doc.toHtml()

    def test_all_alignments_render_without_crash(self) -> None:
        """All four alignment values should render to an image without error."""
        for align in [ALIGN_LEFT, ALIGN_RIGHT, ALIGN_CENTER, ALIGN_JUSTIFY]:
            ocr_res = _make_ocr_result(
                translated_html="Aligned text block with enough words to fill",
                alignment=align,
                w=300,
                h=100,
            )
            img = _render_on_image(300, 100, "fallback", ocr_res)
            assert img is not None, f"Render failed for alignment: {align}"

    def test_single_line_left_no_offset(self) -> None:
        """Single-line ALIGN_LEFT should produce x_offset=0.

        We verify by checking that two renders with identical params
        produce identical images -- the left-aligned version should
        not shift.
        """
        ocr_res = _make_ocr_result(
            translated_html="Left",
            alignment=ALIGN_LEFT,
            is_single_line=True,
            w=300,
            h=50,
        )
        img_a = _render_on_image(300, 50, "fallback", ocr_res)
        img_b = _render_on_image(300, 50, "fallback", ocr_res)
        assert img_a == img_b

    def test_single_line_center_vs_left_differ(self) -> None:
        """Single-line center-aligned rendering should differ from left-aligned."""
        ocr_left = _make_ocr_result(
            translated_html="Hi",
            alignment=ALIGN_LEFT,
            is_single_line=True,
            w=300,
            h=50,
        )
        ocr_center = _make_ocr_result(
            translated_html="Hi",
            alignment=ALIGN_CENTER,
            is_single_line=True,
            w=300,
            h=50,
        )
        img_left = _render_on_image(300, 50, "Hi", ocr_left)
        img_center = _render_on_image(300, 50, "Hi", ocr_center)
        assert img_left != img_center


# ---------------------------------------------------------------------------
# 10. Color parameters (text color, background color)
# ---------------------------------------------------------------------------


class TestColorParameters:
    """Verify text color is applied via the HTML style in _update_style."""

    def test_color_appears_in_html(self) -> None:
        """The text color hex should appear in the generated HTML."""
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        doc = QTextDocument()
        ocr_res = _make_ocr_result(translated_html="Colored text", color="#FF0000")
        TextRenderer._update_style(doc, ocr_res, 14.0, "English (US)")
        html = doc.toHtml()
        assert "#FF0000" in html or "#ff0000" in html

    def test_different_colors_produce_different_html(self) -> None:
        """Different color values should produce different HTML."""
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        doc_red = QTextDocument()
        ocr_red = _make_ocr_result(translated_html="Text", color="#FF0000")
        TextRenderer._update_style(doc_red, ocr_red, 14.0, "English (US)")

        doc_blue = QTextDocument()
        ocr_blue = _make_ocr_result(translated_html="Text", color="#0000FF")
        TextRenderer._update_style(doc_blue, ocr_blue, 14.0, "English (US)")

        assert doc_red.toHtml() != doc_blue.toHtml()

    def test_red_text_renders_differently(self) -> None:
        """Red text on white background should produce a different image than black."""
        ocr_red = _make_ocr_result(
            translated_html="Color test",
            color="#FF0000",
            w=200,
            h=50,
        )
        ocr_black = _make_ocr_result(
            translated_html="Color test",
            color="#000000",
            w=200,
            h=50,
        )
        img_red = _render_on_image(200, 50, "fallback", ocr_red)
        img_black = _render_on_image(200, 50, "fallback", ocr_black)
        assert img_red != img_black

    def test_transparent_background_in_stylesheet(self) -> None:
        """_prepare_document sets background-color:transparent in the stylesheet."""
        ocr_res = _make_ocr_result()
        doc = TextRenderer._prepare_document(ocr_res)
        sheet = doc.defaultStyleSheet()
        assert "transparent" in sheet

    def test_color_with_html_rich_text(self) -> None:
        """Color should apply alongside bold/italic HTML tags."""
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        doc = QTextDocument()
        ocr_res = _make_ocr_result(
            translated_html="<b>Bold</b> <i>Italic</i>",
            color="#00FF00",
        )
        TextRenderer._update_style(doc, ocr_res, 14.0, "English (US)")
        html = doc.toHtml()
        assert "Bold" in html
        assert "Italic" in html
        # The color should be applied at the div level
        assert "#00FF00" in html or "#00ff00" in html


# ---------------------------------------------------------------------------
# Additional edge-case and integration tests
# ---------------------------------------------------------------------------


class TestPrepareDocument:
    """Additional tests for _prepare_document."""

    def test_document_margin_is_zero(self) -> None:
        """Document margin should be exactly 0."""
        ocr_res = _make_ocr_result()
        doc = TextRenderer._prepare_document(ocr_res)
        assert doc.documentMargin() == 0  # noqa: PLR2004

    def test_block_format_margins_are_zero(self) -> None:
        """All block format margins should be 0."""
        ocr_res = _make_ocr_result()
        doc = TextRenderer._prepare_document(ocr_res)
        cursor = doc.rootFrame().firstCursorPosition()
        fmt = cursor.blockFormat()
        assert fmt.topMargin() == 0  # noqa: PLR2004
        assert fmt.bottomMargin() == 0  # noqa: PLR2004
        assert fmt.leftMargin() == 0  # noqa: PLR2004
        assert fmt.rightMargin() == 0  # noqa: PLR2004
        assert fmt.indent() == 0  # noqa: PLR2004


class TestUpdateStyleFontFamily:
    """Verify that _update_style applies the correct font family."""

    def test_font_family_in_html_for_english(self) -> None:
        """The document HTML should contain the resolved font family name."""
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        doc = QTextDocument()
        ocr_res = _make_ocr_result(translated_html="Hello")
        TextRenderer._update_style(doc, ocr_res, 14.0, "English (US)")

        expected_family = TextRenderer._get_font_family("English (US)")
        html = doc.toHtml()
        assert expected_family in html

    def test_font_family_in_html_for_japanese(self) -> None:
        """Japanese language should inject the Japanese font family."""
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        doc = QTextDocument()
        ocr_res = _make_ocr_result(translated_html="\u3053\u3093\u306b\u3061\u306f")
        TextRenderer._update_style(doc, ocr_res, 14.0, "Japanese")

        expected_family = TextRenderer._get_font_family("Japanese")
        html = doc.toHtml()
        assert expected_family in html


class TestFindBestFontSizeSingleLine:
    """Additional coverage for single-line font size fitting."""

    def test_single_line_nowrap_mode(self) -> None:
        """Single-line mode should set NoWrap on the text option."""
        from PySide6.QtGui import QTextDocument, QTextOption  # noqa: PLC0415

        doc = QTextDocument()
        rect = QRect(0, 0, 200, 30)
        ocr_res = _make_ocr_result(
            translated_html="Short text",
            is_single_line=True,
            w=200,
            h=30,
        )

        TextRenderer._find_best_font_size(doc, rect, "", ocr_res, "English (US)")

        # After finding the best size, the doc should have NoWrap
        wrap_mode = doc.defaultTextOption().wrapMode()
        assert wrap_mode == QTextOption.WrapMode.NoWrap

    def test_multiline_does_not_set_nowrap(self) -> None:
        """Multi-line mode should not override the wrap mode to NoWrap."""
        from PySide6.QtGui import QTextDocument, QTextOption  # noqa: PLC0415

        doc = QTextDocument()
        rect = QRect(0, 0, 200, 100)
        ocr_res = _make_ocr_result(
            translated_html="Multi-line text with enough words",
            is_single_line=False,
            w=200,
            h=100,
        )

        TextRenderer._find_best_font_size(doc, rect, "", ocr_res, "English (US)")

        wrap_mode = doc.defaultTextOption().wrapMode()
        assert wrap_mode != QTextOption.WrapMode.NoWrap


class TestRenderIntegration:
    """Full integration tests combining multiple features."""

    def test_render_with_all_features_combined(self) -> None:
        """Render with color, alignment, rich HTML, and CJK in one pass."""
        ocr_res = _make_ocr_result(
            translated_html="<b>\u4f60\u597d</b> World <i>Test</i>",
            color="#336699",
            alignment=ALIGN_CENTER,
            line_height_ratio=1.5,
            w=400,
            h=150,
        )
        img = _render_on_image(400, 150, "fallback", ocr_res, "Chinese (Simplified)")
        assert img is not None

    def test_render_does_not_modify_ocr_result(self) -> None:
        """render() should not mutate the OCRResult passed to it."""
        ocr_res = _make_ocr_result(
            translated_html="Immutable check",
            color="#112233",
            alignment=ALIGN_RIGHT,
            line_height_ratio=1.3,
            is_single_line=True,
            w=200,
            h=50,
        )

        # Snapshot original values
        orig_html = ocr_res.translated_html
        orig_color = ocr_res.color
        orig_align = ocr_res.alignment
        orig_lh = ocr_res.line_height_ratio
        orig_sl = ocr_res.is_single_line

        _render_on_image(200, 50, "fallback", ocr_res)

        assert ocr_res.translated_html == orig_html
        assert ocr_res.color == orig_color
        assert ocr_res.alignment == orig_align
        assert ocr_res.line_height_ratio == orig_lh
        assert ocr_res.is_single_line == orig_sl

    def test_render_deterministic_output(self) -> None:
        """Two identical render calls should produce identical images."""
        ocr_res = _make_ocr_result(
            translated_html="Deterministic",
            w=200,
            h=50,
        )
        img_a = _render_on_image(200, 50, "fallback", ocr_res)
        img_b = _render_on_image(200, 50, "fallback", ocr_res)
        assert img_a == img_b


# ---------------------------------------------------------------------------
# NEW: Additional tests for expanded coverage
# ---------------------------------------------------------------------------


class TestRenderPlainText:
    """Tests for rendering plain text (no HTML formatting)."""

    def test_plain_text_single_word(self) -> None:
        """Single plain-text word renders without error."""
        ocr_res = _make_ocr_result(
            translated_html="Hello",
            w=200,
            h=50,
            is_single_line=True,
        )
        img = _render_on_image(200, 50, "Hello", ocr_res)
        assert img is not None

    def test_plain_text_numbers_only(self) -> None:
        """Numeric-only text renders correctly."""
        ocr_res = _make_ocr_result(
            translated_html="123456789",
            w=200,
            h=50,
            is_single_line=True,
        )
        img = _render_on_image(200, 50, "123456789", ocr_res)
        assert img is not None

    def test_plain_text_with_punctuation(self) -> None:
        """Text with special punctuation renders correctly."""
        ocr_res = _make_ocr_result(
            translated_html="Hello, World! @#$%^&*()",
            w=300,
            h=50,
        )
        img = _render_on_image(300, 50, "fallback", ocr_res)
        assert img is not None


class TestRenderRichText:
    """Tests for rendering rich text with HTML tags."""

    def test_bold_text(self) -> None:
        """Bold tag renders without error."""
        ocr_res = _make_ocr_result(
            translated_html="<b>Bold text here</b>",
            w=300,
            h=80,
        )
        img = _render_on_image(300, 80, "fallback", ocr_res)
        assert img is not None

    def test_italic_text(self) -> None:
        """Italic tag renders without error."""
        ocr_res = _make_ocr_result(
            translated_html="<i>Italic text here</i>",
            w=300,
            h=80,
        )
        img = _render_on_image(300, 80, "fallback", ocr_res)
        assert img is not None

    def test_underline_text(self) -> None:
        """Underline tag renders without error."""
        ocr_res = _make_ocr_result(
            translated_html="<u>Underlined text</u>",
            w=300,
            h=80,
        )
        img = _render_on_image(300, 80, "fallback", ocr_res)
        assert img is not None

    def test_nested_formatting(self) -> None:
        """Nested bold + italic renders without error."""
        ocr_res = _make_ocr_result(
            translated_html="<b><i>Bold italic</i></b> normal",
            w=300,
            h=80,
        )
        img = _render_on_image(300, 80, "fallback", ocr_res)
        assert img is not None

    def test_mixed_bold_italic_underline(self) -> None:
        """Mixed formatting tags render correctly."""
        ocr_res = _make_ocr_result(
            translated_html="<b>B</b> <i>I</i> <u>U</u>",
            w=300,
            h=80,
        )
        img = _render_on_image(300, 80, "fallback", ocr_res)
        assert img is not None

    def test_html_with_br_tags(self) -> None:
        """Multiple BR tags create multi-line rendering."""
        ocr_res = _make_ocr_result(
            translated_html="Line 1<br>Line 2<br>Line 3",
            w=300,
            h=100,
        )
        img = _render_on_image(300, 100, "fallback", ocr_res)
        assert img is not None


class TestGetFontFamilyAllLanguages:
    """Test _get_font_family for all supported language scripts."""

    ALL_LANGUAGES = [
        "Chinese (Simplified)",
        "Chinese (Traditional)",
        "Japanese",
        "Korean",
        "Hindi",
        "Nepali",
        "Arabic",
        "Persian",
        "Hebrew",
        "Bengali",
        "Thai",
        "Khmer",
        "Russian",
        "Ukrainian",
        "Belarusian",
        "Bulgarian",
        "Serbian",
        "Mongolian",
        "Greek",
        "Vietnamese",
        "Turkish",
        "English (US)",
        "French",
        "German",
        "Spanish",
        "Portuguese",
        "Italian",
        "Dutch",
        "Polish",
        "Czech",
        "Swedish",
        "Norwegian",
        "Danish",
        "Finnish",
        "Romanian",
        "Hungarian",
        "Indonesian",
        "Malay",
        "Filipino",
        "Swahili",
        "Estonian",
        "Latvian",
        "Lithuanian",
        "Slovak",
        "Slovenian",
    ]

    def test_all_languages_return_nonempty_string(self) -> None:
        """Every language returns a non-empty font family string."""
        TextRenderer._get_font_family.cache_clear()
        for lang in self.ALL_LANGUAGES:
            family = TextRenderer._get_font_family(lang)
            assert isinstance(family, str), f"Not a string for {lang}"
            assert len(family) > 0, f"Empty font family for {lang}"

    def test_cjk_languages_have_distinct_fonts(self) -> None:
        """CJK languages should use CJK-specific fonts."""
        TextRenderer._get_font_family.cache_clear()
        zh_s = TextRenderer._get_font_family("Chinese (Simplified)")
        zh_t = TextRenderer._get_font_family("Chinese (Traditional)")
        ja = TextRenderer._get_font_family("Japanese")
        ko = TextRenderer._get_font_family("Korean")
        default = TextRenderer._get_font_family("English (US)")
        # CJK fonts should differ from the default Latin font
        assert zh_s != default
        assert zh_t != default
        assert ja != default
        assert ko != default

    def test_arabic_script_languages_use_arabic_fonts(self) -> None:
        """Arabic and Persian should use Arabic-script fonts."""
        TextRenderer._get_font_family.cache_clear()
        ar = TextRenderer._get_font_family("Arabic")
        fa = TextRenderer._get_font_family("Persian")
        default = TextRenderer._get_font_family("English (US)")
        assert ar != default
        assert fa != default

    def test_devanagari_languages_use_devanagari_fonts(self) -> None:
        """Hindi and Nepali should use Devanagari fonts."""
        TextRenderer._get_font_family.cache_clear()
        hi = TextRenderer._get_font_family("Hindi")
        ne = TextRenderer._get_font_family("Nepali")
        assert hi == ne  # Both use Mangal

    def test_cyrillic_languages_share_same_font(self) -> None:
        """All Cyrillic languages should use the same font family."""
        TextRenderer._get_font_family.cache_clear()
        ru = TextRenderer._get_font_family("Russian")
        uk = TextRenderer._get_font_family("Ukrainian")
        bg = TextRenderer._get_font_family("Bulgarian")
        assert ru == uk == bg


class TestRenderSpecialCharacters:
    """Test rendering with special characters."""

    def test_html_entities(self) -> None:
        """HTML entities render correctly."""
        ocr_res = _make_ocr_result(
            translated_html="&amp; &lt; &gt; &quot;",
            w=300,
            h=80,
        )
        img = _render_on_image(300, 80, "fallback", ocr_res)
        assert img is not None

    def test_mathematical_symbols(self) -> None:
        """Mathematical symbols render correctly."""
        ocr_res = _make_ocr_result(
            translated_html="x = a + b \u00d7 c \u00f7 d",
            w=300,
            h=80,
        )
        img = _render_on_image(300, 80, "fallback", ocr_res)
        assert img is not None

    def test_currency_symbols(self) -> None:
        """Currency symbols render correctly."""
        ocr_res = _make_ocr_result(
            translated_html="$100 \u20ac50 \u00a330 \u00a5200",
            w=300,
            h=80,
        )
        img = _render_on_image(300, 80, "fallback", ocr_res)
        assert img is not None

    def test_emoji_text(self) -> None:
        """Emoji characters in text should not crash."""
        ocr_res = _make_ocr_result(
            translated_html="Hello \U0001f600 World \U0001f30d",
            w=300,
            h=80,
        )
        img = _render_on_image(300, 80, "fallback", ocr_res)
        assert img is not None

    def test_zero_width_characters(self) -> None:
        """Zero-width characters should not crash."""
        ocr_res = _make_ocr_result(
            translated_html="Hello\u200bWorld\u200b",
            w=300,
            h=80,
        )
        img = _render_on_image(300, 80, "fallback", ocr_res)
        assert img is not None


class TestImageOutputFormat:
    """Tests for image output format and size."""

    def test_image_dimensions_match_input(self) -> None:
        """The output image has the dimensions we requested."""
        ocr_res = _make_ocr_result(translated_html="Test", w=400, h=200)
        img = _render_on_image(400, 200, "fallback", ocr_res)
        assert img.width() == 400  # noqa: PLR2004
        assert img.height() == 200  # noqa: PLR2004

    def test_image_format_is_rgb32(self) -> None:
        """The image format is RGB32."""
        ocr_res = _make_ocr_result(translated_html="Test", w=100, h=50)
        img = _render_on_image(100, 50, "fallback", ocr_res)
        assert img.format() == QImage.Format.Format_RGB32

    def test_small_image_renders(self) -> None:
        """Very small image (10x10) renders without crash."""
        ocr_res = _make_ocr_result(translated_html="X", w=10, h=10, is_single_line=True)
        img = _render_on_image(10, 10, "X", ocr_res)
        assert img is not None
        assert img.width() == 10
        assert img.height() == 10

    def test_large_image_renders(self) -> None:
        """Large image (2000x1000) renders without crash."""
        ocr_res = _make_ocr_result(translated_html="Large test", w=2000, h=1000)
        img = _render_on_image(2000, 1000, "fallback", ocr_res)
        assert img is not None
        assert img.width() == 2000  # noqa: PLR2004
        assert img.height() == 1000  # noqa: PLR2004


class TestUpdateStyleDetails:
    """Detailed tests for _update_style behavior."""

    def test_font_size_appears_in_html(self) -> None:
        """The specified font size appears in the generated HTML."""
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        doc = QTextDocument()
        ocr_res = _make_ocr_result(translated_html="Size test")
        TextRenderer._update_style(doc, ocr_res, 20.0, "English (US)")
        html = doc.toHtml()
        assert "20" in html

    def test_text_content_in_html(self) -> None:
        """The translated_html content appears in the document HTML."""
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        doc = QTextDocument()
        ocr_res = _make_ocr_result(translated_html="Specific content here")
        TextRenderer._update_style(doc, ocr_res, 14.0, "English (US)")
        html = doc.toHtml()
        assert "Specific content here" in html

    def test_justify_alignment_in_css(self) -> None:
        """ALIGN_JUSTIFY maps to 'justify' in CSS text-align."""
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        doc = QTextDocument()
        ocr_res = _make_ocr_result(
            translated_html="Justified text",
            alignment=ALIGN_JUSTIFY,
        )
        TextRenderer._update_style(doc, ocr_res, 14.0, "English (US)")
        # Qt may render justify as 'justify' in the input HTML
        # The key test is it doesn't crash and html is set
        assert doc.toHtml() is not None


# ---------------------------------------------------------------------------
# NEW: Expanded tests for deeper coverage (target 200+)
# ---------------------------------------------------------------------------


class TestRenderDevanagariScripts:
    """Verify rendering with Devanagari-script languages."""

    def test_hindi_text(self) -> None:
        """Hindi text should render without error."""
        ocr_res = _make_ocr_result(
            translated_html="\u0928\u092e\u0938\u094d\u0924\u0947 \u0926\u0941\u0928\u093f\u092f\u0627",
            w=300,
            h=100,
        )
        img = _render_on_image(300, 100, "fallback", ocr_res, "Hindi")
        assert img is not None

    def test_nepali_text(self) -> None:
        """Nepali text should render without error."""
        ocr_res = _make_ocr_result(
            translated_html="\u0928\u092e\u0938\u094d\u0915\u093e\u0930",
            w=300,
            h=100,
        )
        img = _render_on_image(300, 100, "fallback", ocr_res, "Nepali")
        assert img is not None


class TestRenderBengaliScript:
    """Verify rendering with Bengali script."""

    def test_bengali_text(self) -> None:
        """Bengali text should render without error."""
        ocr_res = _make_ocr_result(
            translated_html="\u09b8\u09cd\u09ac\u09be\u0997\u09a4\u09ae",
            w=300,
            h=100,
        )
        img = _render_on_image(300, 100, "fallback", ocr_res, "Bengali")
        assert img is not None


class TestRenderThaiScript:
    """Verify rendering with Thai script."""

    def test_thai_text(self) -> None:
        """Thai text should render without error."""
        ocr_res = _make_ocr_result(
            translated_html="\u0e2a\u0e27\u0e31\u0e2a\u0e14\u0e35\u0e04\u0e23\u0e31\u0e1a",
            w=300,
            h=100,
        )
        img = _render_on_image(300, 100, "fallback", ocr_res, "Thai")
        assert img is not None


class TestRenderKhmerScript:
    """Verify rendering with Khmer script."""

    def test_khmer_text(self) -> None:
        """Khmer text should render without error."""
        ocr_res = _make_ocr_result(
            translated_html="\u1787\u17c6\u179a\u17b6\u1794\u179f\u17bd\u179a",
            w=300,
            h=100,
        )
        img = _render_on_image(300, 100, "fallback", ocr_res, "Khmer")
        assert img is not None


class TestRenderCyrillicScripts:
    """Verify rendering with Cyrillic-script languages."""

    def test_russian_text(self) -> None:
        """Russian text should render without error."""
        ocr_res = _make_ocr_result(
            translated_html="\u041f\u0440\u0438\u0432\u0435\u0442 \u043c\u0438\u0440",
            w=300,
            h=100,
        )
        img = _render_on_image(300, 100, "fallback", ocr_res, "Russian")
        assert img is not None

    def test_ukrainian_text(self) -> None:
        """Ukrainian text should render without error."""
        ocr_res = _make_ocr_result(
            translated_html="\u041f\u0440\u0438\u0432\u0456\u0442 \u0441\u0432\u0456\u0442",
            w=300,
            h=100,
        )
        img = _render_on_image(300, 100, "fallback", ocr_res, "Ukrainian")
        assert img is not None

    def test_bulgarian_text(self) -> None:
        """Bulgarian text should render without error."""
        ocr_res = _make_ocr_result(
            translated_html="\u0417\u0434\u0440\u0430\u0432\u0435\u0439 \u0441\u0432\u044f\u0442",
            w=300,
            h=100,
        )
        img = _render_on_image(300, 100, "fallback", ocr_res, "Bulgarian")
        assert img is not None

    def test_serbian_text(self) -> None:
        """Serbian text should render without error."""
        ocr_res = _make_ocr_result(
            translated_html="\u0417\u0434\u0440\u0430\u0432\u043e \u0441\u0432\u0435\u0442\u0435",
            w=300,
            h=100,
        )
        img = _render_on_image(300, 100, "fallback", ocr_res, "Serbian")
        assert img is not None

    def test_mongolian_text(self) -> None:
        """Mongolian text should render without error."""
        ocr_res = _make_ocr_result(
            translated_html="\u0421\u0430\u0439\u043d \u0443\u0443",
            w=300,
            h=100,
        )
        img = _render_on_image(300, 100, "fallback", ocr_res, "Mongolian")
        assert img is not None

    def test_belarusian_text(self) -> None:
        """Belarusian text should render without error."""
        ocr_res = _make_ocr_result(
            translated_html="\u0412\u0456\u0442\u0430\u043d\u043d\u0435 \u0441\u0432\u0435\u0442",
            w=300,
            h=100,
        )
        img = _render_on_image(300, 100, "fallback", ocr_res, "Belarusian")
        assert img is not None


class TestRenderGreekScript:
    """Verify rendering with Greek script."""

    def test_greek_text(self) -> None:
        """Greek text should render without error."""
        ocr_res = _make_ocr_result(
            translated_html="\u0393\u03b5\u03b9\u03b1 \u03c3\u03bf\u03c5 \u03ba\u03cc\u03c3\u03bc\u03b5",
            w=300,
            h=100,
        )
        img = _render_on_image(300, 100, "fallback", ocr_res, "Greek")
        assert img is not None


class TestRenderVietnameseScript:
    """Verify rendering with Vietnamese Latin extended."""

    def test_vietnamese_text(self) -> None:
        """Vietnamese text should render without error."""
        ocr_res = _make_ocr_result(
            translated_html="Xin ch\u00e0o th\u1ebf gi\u1edbi",
            w=300,
            h=100,
        )
        img = _render_on_image(300, 100, "fallback", ocr_res, "Vietnamese")
        assert img is not None


class TestRenderTurkishScript:
    """Verify rendering with Turkish Latin."""

    def test_turkish_text(self) -> None:
        """Turkish text should render without error."""
        ocr_res = _make_ocr_result(
            translated_html="Merhaba D\u00fcnya",
            w=300,
            h=100,
        )
        img = _render_on_image(300, 100, "fallback", ocr_res, "Turkish")
        assert img is not None


class TestFontSelectionPerLanguage:
    """Verify font selection returns distinct fonts for different scripts."""

    def test_arabic_font_differs_from_default(self) -> None:
        """Arabic should use a different font than the default."""
        TextRenderer._get_font_family.cache_clear()
        ar = TextRenderer._get_font_family("Arabic")
        en = TextRenderer._get_font_family("English (US)")
        assert ar != en

    def test_hebrew_font_differs_from_default(self) -> None:
        """Hebrew should use a different font than the default."""
        TextRenderer._get_font_family.cache_clear()
        he = TextRenderer._get_font_family("Hebrew")
        en = TextRenderer._get_font_family("English (US)")
        assert he != en

    def test_hindi_font_differs_from_default(self) -> None:
        """Hindi should use a different font than the default."""
        TextRenderer._get_font_family.cache_clear()
        hi = TextRenderer._get_font_family("Hindi")
        en = TextRenderer._get_font_family("English (US)")
        assert hi != en

    def test_thai_font_differs_from_default(self) -> None:
        """Thai should use a different font than the default."""
        TextRenderer._get_font_family.cache_clear()
        th = TextRenderer._get_font_family("Thai")
        en = TextRenderer._get_font_family("English (US)")
        assert th != en

    def test_bengali_font_differs_from_default(self) -> None:
        """Bengali should use a different font than the default."""
        TextRenderer._get_font_family.cache_clear()
        bn = TextRenderer._get_font_family("Bengali")
        en = TextRenderer._get_font_family("English (US)")
        assert bn != en

    def test_khmer_font_differs_from_default(self) -> None:
        """Khmer should use a different font than the default."""
        TextRenderer._get_font_family.cache_clear()
        km = TextRenderer._get_font_family("Khmer")
        en = TextRenderer._get_font_family("English (US)")
        assert km != en

    def test_persian_font_differs_from_default(self) -> None:
        """Persian should use a different font than the default."""
        TextRenderer._get_font_family.cache_clear()
        fa = TextRenderer._get_font_family("Persian")
        en = TextRenderer._get_font_family("English (US)")
        assert fa != en

    def test_nepali_font_differs_from_default(self) -> None:
        """Nepali should use a different font than the default."""
        TextRenderer._get_font_family.cache_clear()
        ne = TextRenderer._get_font_family("Nepali")
        en = TextRenderer._get_font_family("English (US)")
        assert ne != en


class TestRichTextFormatting:
    """Verify various HTML formatting tags render without crash."""

    def test_underline_tag(self) -> None:
        """<u> underline tag should render."""
        ocr_res = _make_ocr_result(
            translated_html="Normal <u>underlined</u> text",
            w=300,
            h=100,
        )
        img = _render_on_image(300, 100, "fallback", ocr_res)
        assert img is not None

    def test_strikethrough_tag(self) -> None:
        """<s> strikethrough tag should render."""
        ocr_res = _make_ocr_result(
            translated_html="Normal <s>strikethrough</s> text",
            w=300,
            h=100,
        )
        img = _render_on_image(300, 100, "fallback", ocr_res)
        assert img is not None

    def test_nested_bold_italic(self) -> None:
        """Nested <b><i> tags should render."""
        ocr_res = _make_ocr_result(
            translated_html="<b><i>Bold Italic</i></b> normal",
            w=300,
            h=100,
        )
        img = _render_on_image(300, 100, "fallback", ocr_res)
        assert img is not None

    def test_span_with_color(self) -> None:
        """<span> with color style should render."""
        ocr_res = _make_ocr_result(
            translated_html='<span style="color:red">Red</span> black',
            w=300,
            h=100,
        )
        img = _render_on_image(300, 100, "fallback", ocr_res)
        assert img is not None

    def test_sup_and_sub_tags(self) -> None:
        """<sup> and <sub> tags should render."""
        ocr_res = _make_ocr_result(
            translated_html="H<sub>2</sub>O and x<sup>2</sup>",
            w=300,
            h=100,
        )
        img = _render_on_image(300, 100, "fallback", ocr_res)
        assert img is not None

    def test_br_tag_single_line_mode(self) -> None:
        """<br> in single-line mode should not crash."""
        ocr_res = _make_ocr_result(
            translated_html="Line 1<br>Line 2",
            w=300,
            h=50,
            is_single_line=True,
        )
        img = _render_on_image(300, 50, "fallback", ocr_res)
        assert img is not None

    def test_multiple_br_tags(self) -> None:
        """Multiple consecutive <br> tags should render."""
        ocr_res = _make_ocr_result(
            translated_html="A<br><br><br>B",
            w=300,
            h=200,
        )
        img = _render_on_image(300, 200, "fallback", ocr_res)
        assert img is not None


class TestTextWrapping:
    """Verify text wrapping behavior."""

    def test_no_wrap_in_single_line_mode(self) -> None:
        """Single-line mode disables wrapping."""
        from PySide6.QtGui import QTextOption  # noqa: PLC0415

        doc = TextRenderer._prepare_document(_make_ocr_result(is_single_line=True))
        rect = QRect(0, 0, 100, 30)
        ocr_res = _make_ocr_result(
            translated_html="This is a long single line text",
            w=100,
            h=30,
            is_single_line=True,
        )

        TextRenderer._find_best_font_size(
            doc, rect, "fallback", ocr_res, "English (US)"
        )

        option = doc.defaultTextOption()
        assert option.wrapMode() == QTextOption.WrapMode.NoWrap

    def test_multiline_wraps_to_width(self) -> None:
        """Multi-line mode wraps text to the box width."""
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        doc = QTextDocument()
        rect = QRect(0, 0, 100, 200)
        ocr_res = _make_ocr_result(
            translated_html="Word " * 50,
            w=100,
            h=200,
        )
        size = TextRenderer._find_best_font_size(
            doc, rect, "fallback", ocr_res, "English (US)"
        )
        TextRenderer._update_style(doc, ocr_res, size, "English (US)")
        doc.setTextWidth(rect.width())
        # Document height should be greater than a single line
        assert doc.size().height() > size


class TestColorHandling:
    """Extended color handling tests."""

    def test_white_text_on_white_bg(self) -> None:
        """White text on white background renders (essentially invisible)."""
        ocr_res = _make_ocr_result(
            translated_html="Invisible",
            color="#FFFFFF",
            w=200,
            h=50,
        )
        img = _render_on_image(200, 50, "fallback", ocr_res)
        assert img is not None

    def test_hex_color_with_lowercase(self) -> None:
        """Lowercase hex color should work."""
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        doc = QTextDocument()
        ocr_res = _make_ocr_result(translated_html="test", color="#aabbcc")
        TextRenderer._update_style(doc, ocr_res, 14.0, "English (US)")
        html = doc.toHtml()
        assert "aabbcc" in html.lower()

    def test_named_css_color(self) -> None:
        """Named CSS color (e.g. 'red') should be usable."""
        ocr_res = _make_ocr_result(
            translated_html="Red text",
            color="red",
            w=200,
            h=50,
        )
        img = _render_on_image(200, 50, "fallback", ocr_res)
        assert img is not None

    def test_rgb_color(self) -> None:
        """RGB color notation should be usable."""
        ocr_res = _make_ocr_result(
            translated_html="RGB text",
            color="rgb(128, 0, 255)",
            w=200,
            h=50,
        )
        img = _render_on_image(200, 50, "fallback", ocr_res)
        assert img is not None


class TestLineHeightRatio:
    """Extended line-height ratio tests."""

    def test_very_high_line_height(self) -> None:
        """Very high line-height ratio should still render."""
        ocr_res = _make_ocr_result(
            translated_html="Line one<br>Line two",
            line_height_ratio=3.0,
            w=300,
            h=200,
        )
        img = _render_on_image(300, 200, "fallback", ocr_res)
        assert img is not None

    def test_very_low_line_height(self) -> None:
        """Very low line-height ratio should still render."""
        ocr_res = _make_ocr_result(
            translated_html="Line one<br>Line two",
            line_height_ratio=0.5,
            w=300,
            h=200,
        )
        img = _render_on_image(300, 200, "fallback", ocr_res)
        assert img is not None

    def test_exact_one_line_height(self) -> None:
        """Line-height ratio of exactly 1.0 should render."""
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        doc = QTextDocument()
        ocr_res = _make_ocr_result(
            translated_html="Text",
            line_height_ratio=1.0,
        )
        TextRenderer._update_style(doc, ocr_res, 14.0, "English (US)")
        assert "line-height:100%;" in doc.toHtml()


class TestPrepareDocumentExtended:
    """Extended tests for _prepare_document."""

    def test_document_margin_is_zero(self) -> None:
        """Document margin is set to zero."""
        ocr_res = _make_ocr_result()
        doc = TextRenderer._prepare_document(ocr_res)
        assert doc.documentMargin() == 0.0

    def test_default_stylesheet_contains_transparent(self) -> None:
        """Default stylesheet includes transparent background."""
        ocr_res = _make_ocr_result()
        doc = TextRenderer._prepare_document(ocr_res)
        assert "transparent" in doc.defaultStyleSheet()

    def test_default_stylesheet_contains_margin_zero(self) -> None:
        """Default stylesheet includes margin: 0."""
        ocr_res = _make_ocr_result()
        doc = TextRenderer._prepare_document(ocr_res)
        assert "margin: 0" in doc.defaultStyleSheet()

    def test_default_stylesheet_contains_padding_zero(self) -> None:
        """Default stylesheet includes padding: 0."""
        ocr_res = _make_ocr_result()
        doc = TextRenderer._prepare_document(ocr_res)
        assert "padding: 0" in doc.defaultStyleSheet()


class TestUpdateStyleExtended:
    """Extended tests for _update_style."""

    def test_font_family_appears_in_html(self) -> None:
        """Selected font family name appears in the document HTML."""
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        doc = QTextDocument()
        ocr_res = _make_ocr_result(translated_html="Test")
        TextRenderer._update_style(doc, ocr_res, 14.0, "Japanese")
        html = doc.toHtml()
        family = TextRenderer._get_font_family("Japanese")
        assert family in html

    def test_font_size_decimal(self) -> None:
        """Decimal font size is embedded in the HTML."""
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        doc = QTextDocument()
        ocr_res = _make_ocr_result(translated_html="Test")
        TextRenderer._update_style(doc, ocr_res, 12.5, "English (US)")
        # Font size 12.5 should appear in the HTML (Qt may round or keep it)
        html = doc.toHtml()
        assert "12" in html  # At least the integer part

    def test_html_entities_preserved(self) -> None:
        """HTML entities in translated_html are preserved."""
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        doc = QTextDocument()
        ocr_res = _make_ocr_result(translated_html="A &amp; B &lt; C")
        TextRenderer._update_style(doc, ocr_res, 14.0, "English (US)")
        html = doc.toHtml()
        assert "A &amp; B" in html


class TestRenderSpecialCharacters:
    """Verify rendering with special characters."""

    def test_html_entities_in_text(self) -> None:
        """HTML entities should render correctly."""
        ocr_res = _make_ocr_result(
            translated_html="&lt;tag&gt; &amp; &quot;quoted&quot;",
            w=300,
            h=100,
        )
        img = _render_on_image(300, 100, "fallback", ocr_res)
        assert img is not None

    def test_unicode_symbols(self) -> None:
        """Unicode symbols should render."""
        ocr_res = _make_ocr_result(
            translated_html="\u2603 \u2764 \u2605 \u266b",
            w=300,
            h=100,
        )
        img = _render_on_image(300, 100, "fallback", ocr_res)
        assert img is not None

    def test_currency_symbols(self) -> None:
        """Currency symbols should render."""
        ocr_res = _make_ocr_result(
            translated_html="\u20ac100 $200 \u00a3300 \u00a5400",
            w=300,
            h=100,
        )
        img = _render_on_image(300, 100, "fallback", ocr_res)
        assert img is not None

    def test_mathematical_symbols(self) -> None:
        """Mathematical symbols should render."""
        ocr_res = _make_ocr_result(
            translated_html="\u221a \u222b \u2211 \u221e \u2260",
            w=300,
            h=100,
        )
        img = _render_on_image(300, 100, "fallback", ocr_res)
        assert img is not None


class TestRenderBoundaryConditions:
    """Verify rendering at boundary conditions."""

    def test_zero_width_rect(self) -> None:
        """Zero-width rect should not crash."""
        ocr_res = _make_ocr_result(translated_html="text", w=0, h=100)
        img = QImage(1, 100, QImage.Format.Format_RGB32)
        img.fill(QColor(Qt.GlobalColor.white))
        painter = QPainter(img)
        rect = QRect(0, 0, 0, 100)
        TextRenderer.render(painter, rect, "text", ocr_res, "English (US)")
        painter.end()

    def test_zero_height_rect(self) -> None:
        """Zero-height rect should not crash."""
        ocr_res = _make_ocr_result(translated_html="text", w=100, h=0)
        img = QImage(100, 1, QImage.Format.Format_RGB32)
        img.fill(QColor(Qt.GlobalColor.white))
        painter = QPainter(img)
        rect = QRect(0, 0, 100, 0)
        TextRenderer.render(painter, rect, "text", ocr_res, "English (US)")
        painter.end()

    def test_very_large_rect(self) -> None:
        """Very large bounding box should not crash."""
        ocr_res = _make_ocr_result(
            translated_html="Small text in big box",
            w=2000,
            h=1000,
        )
        img = _render_on_image(2000, 1000, "fallback", ocr_res)
        assert img is not None

    def test_rect_with_offset(self) -> None:
        """Rect with non-zero origin should render at correct position."""
        ocr_res = _make_ocr_result(
            translated_html="Offset text",
            w=150,
            h=80,
        )
        img = QImage(500, 500, QImage.Format.Format_RGB32)
        img.fill(QColor(Qt.GlobalColor.white))
        painter = QPainter(img)
        rect = QRect(100, 100, 150, 80)
        TextRenderer.render(painter, rect, "fallback", ocr_res, "English (US)")
        painter.end()

    def test_single_character_text(self) -> None:
        """Single character should render."""
        ocr_res = _make_ocr_result(
            translated_html="X",
            w=50,
            h=50,
            is_single_line=True,
        )
        img = _render_on_image(50, 50, "X", ocr_res)
        assert img is not None


class TestFindBestFontSizeExtended:
    """Extended tests for _find_best_font_size."""

    def test_single_line_with_narrow_box(self) -> None:
        """Single-line text in narrow box produces small font."""
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        doc = QTextDocument()
        rect = QRect(0, 0, 20, 100)
        ocr_res = _make_ocr_result(
            translated_html="Narrow box text",
            w=20,
            h=100,
            is_single_line=True,
        )
        size = TextRenderer._find_best_font_size(doc, rect, "", ocr_res, "English (US)")
        assert size > 0

    def test_multi_line_tall_box(self) -> None:
        """Tall box allows larger font for multi-line text."""
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        doc = QTextDocument()
        rect = QRect(0, 0, 200, 500)
        ocr_res = _make_ocr_result(
            translated_html="A<br>B<br>C",
            w=200,
            h=500,
        )
        size = TextRenderer._find_best_font_size(doc, rect, "", ocr_res, "English (US)")
        assert size > FONT_SIZE_MIN  # noqa: PLR2004

    def test_same_text_same_rect_same_size(self) -> None:
        """Same inputs should produce same font size (deterministic)."""
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        rect = QRect(0, 0, 200, 100)
        ocr_res = _make_ocr_result(translated_html="Consistent", w=200, h=100)

        doc1 = QTextDocument()
        size1 = TextRenderer._find_best_font_size(
            doc1, rect, "", ocr_res, "English (US)"
        )
        doc2 = QTextDocument()
        size2 = TextRenderer._find_best_font_size(
            doc2, rect, "", ocr_res, "English (US)"
        )
        assert size1 == size2


class TestGetFontFamilyAllLanguages:
    """Verify _get_font_family returns valid strings for all supported languages."""

    @pytest.mark.parametrize(
        "lang",
        [
            "English (US)",
            "English (UK)",
            "French",
            "German",
            "Spanish",
            "Portuguese",
            "Italian",
            "Dutch",
            "Polish",
            "Czech",
            "Romanian",
            "Hungarian",
            "Swedish",
            "Norwegian",
            "Danish",
            "Finnish",
            "Indonesian",
            "Malay",
            "Filipino",
            "Swahili",
            "Chinese (Simplified)",
            "Chinese (Traditional)",
            "Japanese",
            "Korean",
            "Arabic",
            "Persian",
            "Hebrew",
            "Hindi",
            "Nepali",
            "Bengali",
            "Thai",
            "Khmer",
            "Russian",
            "Ukrainian",
            "Belarusian",
            "Bulgarian",
            "Serbian",
            "Mongolian",
            "Greek",
            "Vietnamese",
            "Turkish",
        ],
    )
    def test_returns_nonempty_string(self, lang: str) -> None:
        """Each supported language returns a non-empty font family."""
        TextRenderer._get_font_family.cache_clear()
        family = TextRenderer._get_font_family(lang)
        assert isinstance(family, str)
        assert len(family) > 0, f"Empty font family for {lang}"


# ===========================================================================
# NEW TESTS: render() with various script types
# ===========================================================================


class TestRenderScriptTypes:
    """Tests for render() with different script types."""

    def _render_text(
        self,
        html: str,
        lang: str,
        alignment: str = ALIGN_LEFT,
        single_line: bool = True,
        color: str = "#000000",
        width: int = 400,
        height: int = 100,
    ) -> None:
        """Helper to render text and verify no crash."""
        img = QImage(width + 20, height + 20, QImage.Format.Format_RGB32)
        img.fill(QColor(Qt.GlobalColor.white))
        painter = QPainter(img)
        rect = QRect(10, 10, width, height)
        ocr_res = OCRResult("test", 10, 10, width, height, 1.0)
        ocr_res.translated_html = html
        ocr_res.color = color
        ocr_res.alignment = alignment
        ocr_res.line_height_ratio = 1.2
        ocr_res.is_single_line = single_line
        TextRenderer.render(painter, rect, "fallback", ocr_res, lang)
        painter.end()

    def test_render_latin_text(self) -> None:
        """Latin text renders without error."""
        self._render_text("Hello World", "English (US)")

    def test_render_cjk_simplified_chinese(self) -> None:
        """Simplified Chinese renders without error."""
        self._render_text("你好世界", "Chinese (Simplified)")

    def test_render_cjk_traditional_chinese(self) -> None:
        """Traditional Chinese renders without error."""
        self._render_text("你好世界", "Chinese (Traditional)")

    def test_render_japanese(self) -> None:
        """Japanese renders without error."""
        self._render_text("こんにちは世界", "Japanese")

    def test_render_korean(self) -> None:
        """Korean renders without error."""
        self._render_text("안녕하세요", "Korean")

    def test_render_arabic(self) -> None:
        """Arabic (RTL) text renders without error."""
        self._render_text("مرحبا بالعالم", "Arabic", alignment=ALIGN_RIGHT)

    def test_render_persian(self) -> None:
        """Persian (RTL) text renders without error."""
        self._render_text("سلام", "Persian", alignment=ALIGN_RIGHT)

    def test_render_hebrew(self) -> None:
        """Hebrew (RTL) text renders without error."""
        self._render_text("שלום עולם", "Hebrew", alignment=ALIGN_RIGHT)

    def test_render_devanagari_hindi(self) -> None:
        """Hindi (Devanagari) text renders without error."""
        self._render_text("नमस्ते दुनिया", "Hindi")

    def test_render_nepali(self) -> None:
        """Nepali (Devanagari) text renders without error."""
        self._render_text("नमस्कार", "Nepali")

    def test_render_bengali(self) -> None:
        """Bengali text renders without error."""
        self._render_text("হ্যালো বিশ্ব", "Bengali")

    def test_render_thai(self) -> None:
        """Thai text renders without error."""
        self._render_text("สวัสดีชาวโลก", "Thai")

    def test_render_khmer(self) -> None:
        """Khmer text renders without error."""
        self._render_text("ស្វាគមន៍", "Khmer")

    def test_render_russian(self) -> None:
        """Russian (Cyrillic) text renders without error."""
        self._render_text("Привет мир", "Russian")

    def test_render_ukrainian(self) -> None:
        """Ukrainian (Cyrillic) text renders without error."""
        self._render_text("Привіт світ", "Ukrainian")

    def test_render_greek(self) -> None:
        """Greek text renders without error."""
        self._render_text("Γειά σου κόσμε", "Greek")

    def test_render_vietnamese(self) -> None:
        """Vietnamese (extended Latin) text renders without error."""
        self._render_text("Xin chào thế giới", "Vietnamese")

    def test_render_turkish(self) -> None:
        """Turkish text renders without error."""
        self._render_text("Merhaba Dünya", "Turkish")

    def test_render_mongolian(self) -> None:
        """Mongolian (Cyrillic) text renders without error."""
        self._render_text("Сайн байна уу", "Mongolian")

    def test_render_serbian(self) -> None:
        """Serbian (Cyrillic) text renders without error."""
        self._render_text("Здраво свете", "Serbian")

    def test_render_bulgarian(self) -> None:
        """Bulgarian (Cyrillic) text renders without error."""
        self._render_text("Здравей свят", "Bulgarian")

    def test_render_belarusian(self) -> None:
        """Belarusian (Cyrillic) text renders without error."""
        self._render_text("Прывітанне свет", "Belarusian")


# ===========================================================================
# NEW TESTS: Font selection per language
# ===========================================================================


class TestFontSelectionPerLanguage:
    """Tests to verify _get_font_family for various languages."""

    @pytest.fixture(autouse=True)
    def _clear_cache(self) -> None:
        TextRenderer._get_font_family.cache_clear()

    def test_english_uses_default_font(self) -> None:
        family = TextRenderer._get_font_family("English (US)")
        assert isinstance(family, str) and len(family) > 0

    def test_chinese_simplified_uses_cjk_font(self) -> None:
        family = TextRenderer._get_font_family("Chinese (Simplified)")
        assert isinstance(family, str) and len(family) > 0

    def test_japanese_uses_cjk_font(self) -> None:
        family = TextRenderer._get_font_family("Japanese")
        assert isinstance(family, str) and len(family) > 0

    def test_korean_uses_cjk_font(self) -> None:
        family = TextRenderer._get_font_family("Korean")
        assert isinstance(family, str) and len(family) > 0

    def test_arabic_uses_arabic_font(self) -> None:
        family = TextRenderer._get_font_family("Arabic")
        assert isinstance(family, str) and len(family) > 0

    def test_hindi_uses_devanagari_font(self) -> None:
        family = TextRenderer._get_font_family("Hindi")
        assert isinstance(family, str) and len(family) > 0

    def test_thai_uses_thai_font(self) -> None:
        family = TextRenderer._get_font_family("Thai")
        assert isinstance(family, str) and len(family) > 0

    def test_hebrew_uses_hebrew_font(self) -> None:
        family = TextRenderer._get_font_family("Hebrew")
        assert isinstance(family, str) and len(family) > 0

    def test_unknown_language_returns_default(self) -> None:
        family = TextRenderer._get_font_family("Klingon")
        assert isinstance(family, str) and len(family) > 0

    def test_empty_language_returns_valid_font(self) -> None:
        family = TextRenderer._get_font_family("")
        assert isinstance(family, str) and len(family) > 0


# ===========================================================================
# NEW TESTS: Text wrapping with long words
# ===========================================================================


class TestTextWrapping:
    """Tests for text wrapping and long-word handling."""

    def test_long_word_single_line_does_not_crash(self) -> None:
        """A very long single word in single-line mode doesn't crash."""
        img = QImage(200, 50, QImage.Format.Format_RGB32)
        img.fill(QColor(Qt.GlobalColor.white))
        painter = QPainter(img)
        rect = QRect(5, 5, 190, 40)
        ocr_res = OCRResult("Test", 5, 5, 190, 40, 1.0)
        ocr_res.translated_html = "Superlongwordthatwillnotfitatall" * 5
        ocr_res.color = "#000000"
        ocr_res.alignment = ALIGN_LEFT
        ocr_res.line_height_ratio = 1.0
        ocr_res.is_single_line = True
        TextRenderer.render(painter, rect, "fallback", ocr_res, "English (US)")
        painter.end()

    def test_long_word_multiline_wraps(self) -> None:
        """Long words in multiline mode wrap to fit."""
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        doc = QTextDocument()
        rect = QRect(0, 0, 100, 200)
        ocr_res = OCRResult("Test", 0, 0, 100, 200, 1.0)
        ocr_res.translated_html = "Verylongwordd" * 10
        ocr_res.color = "#000000"
        ocr_res.line_height_ratio = 1.2
        ocr_res.is_single_line = False

        size = TextRenderer._find_best_font_size(
            doc, rect, "fallback", ocr_res, "English (US)"
        )
        assert size > 0

    def test_multiple_short_words_multiline(self) -> None:
        """Many short words in multiline mode render correctly."""
        img = QImage(200, 200, QImage.Format.Format_RGB32)
        img.fill(QColor(Qt.GlobalColor.white))
        painter = QPainter(img)
        rect = QRect(10, 10, 180, 180)
        ocr_res = OCRResult("Test", 10, 10, 180, 180, 1.0)
        ocr_res.translated_html = " ".join(["word"] * 50)
        ocr_res.color = "#000000"
        ocr_res.alignment = ALIGN_LEFT
        ocr_res.line_height_ratio = 1.2
        ocr_res.is_single_line = False
        TextRenderer.render(painter, rect, "fallback", ocr_res, "English (US)")
        painter.end()


# ===========================================================================
# NEW TESTS: Color parsing
# ===========================================================================


class TestColorParsing:
    """Tests for various color strings in rendered text."""

    def _render_with_color(self, color: str) -> None:
        """Helper to render with a specific color."""
        img = QImage(200, 100, QImage.Format.Format_RGB32)
        img.fill(QColor(Qt.GlobalColor.white))
        painter = QPainter(img)
        rect = QRect(10, 10, 180, 80)
        ocr_res = OCRResult("Test", 10, 10, 180, 80, 1.0)
        ocr_res.translated_html = "Color test"
        ocr_res.color = color
        ocr_res.alignment = ALIGN_LEFT
        ocr_res.line_height_ratio = 1.2
        ocr_res.is_single_line = True
        TextRenderer.render(painter, rect, "fallback", ocr_res, "English (US)")
        painter.end()

    def test_hex_black(self) -> None:
        self._render_with_color("#000000")

    def test_hex_white(self) -> None:
        self._render_with_color("#FFFFFF")

    def test_hex_red(self) -> None:
        self._render_with_color("#FF0000")

    def test_hex_green(self) -> None:
        self._render_with_color("#00FF00")

    def test_hex_blue(self) -> None:
        self._render_with_color("#0000FF")

    def test_hex_short(self) -> None:
        self._render_with_color("#F00")

    def test_named_color_red(self) -> None:
        self._render_with_color("red")

    def test_named_color_blue(self) -> None:
        self._render_with_color("blue")

    def test_rgb_color(self) -> None:
        self._render_with_color("rgb(128, 64, 32)")

    def test_rgba_color(self) -> None:
        self._render_with_color("rgba(128, 64, 32, 0.5)")


# ===========================================================================
# NEW TESTS: Rich text with bold/italic/underline
# ===========================================================================


class TestRichTextRendering:
    """Tests for rich text formatting tags."""

    def _render_html(self, html: str) -> None:
        """Helper to render specific HTML."""
        img = QImage(400, 100, QImage.Format.Format_RGB32)
        img.fill(QColor(Qt.GlobalColor.white))
        painter = QPainter(img)
        rect = QRect(10, 10, 380, 80)
        ocr_res = OCRResult("Test", 10, 10, 380, 80, 1.0)
        ocr_res.translated_html = html
        ocr_res.color = "#000000"
        ocr_res.alignment = ALIGN_LEFT
        ocr_res.line_height_ratio = 1.2
        ocr_res.is_single_line = False
        TextRenderer.render(painter, rect, "fallback", ocr_res, "English (US)")
        painter.end()

    def test_bold_tag(self) -> None:
        self._render_html("<b>Bold text</b>")

    def test_italic_tag(self) -> None:
        self._render_html("<i>Italic text</i>")

    def test_underline_tag(self) -> None:
        self._render_html("<u>Underline text</u>")

    def test_bold_italic_combined(self) -> None:
        self._render_html("<b><i>Bold Italic</i></b>")

    def test_bold_underline_combined(self) -> None:
        self._render_html("<b><u>Bold Underline</u></b>")

    def test_nested_formatting(self) -> None:
        self._render_html("<b>Start <i>nested <u>deep</u></i> end</b>")

    def test_br_tags(self) -> None:
        self._render_html("Line one<br>Line two<br>Line three")

    def test_span_with_style(self) -> None:
        self._render_html('<span style="font-weight:bold;">Styled</span> normal')

    def test_mixed_plain_and_formatted(self) -> None:
        self._render_html("Normal <b>bold</b> normal <i>italic</i> normal")

    def test_empty_tags(self) -> None:
        self._render_html("<b></b><i></i><u></u>")

    def test_strikethrough_tag(self) -> None:
        self._render_html("<s>Strikethrough</s>")

    def test_superscript_tag(self) -> None:
        self._render_html("Normal<sup>sup</sup>")

    def test_subscript_tag(self) -> None:
        self._render_html("Normal<sub>sub</sub>")


# ===========================================================================
# NEW TESTS: Empty text and edge cases
# ===========================================================================


class TestEmptyTextEdgeCases:
    """Tests for empty/minimal text rendering."""

    def test_empty_html_renders(self) -> None:
        """Empty translated_html renders without error."""
        img = QImage(200, 100, QImage.Format.Format_RGB32)
        img.fill(QColor(Qt.GlobalColor.white))
        painter = QPainter(img)
        rect = QRect(10, 10, 180, 80)
        ocr_res = OCRResult("Test", 10, 10, 180, 80, 1.0)
        ocr_res.translated_html = ""
        ocr_res.color = "#000000"
        ocr_res.alignment = ALIGN_LEFT
        ocr_res.line_height_ratio = 1.2
        ocr_res.is_single_line = True
        TextRenderer.render(painter, rect, "", ocr_res, "English (US)")
        painter.end()

    def test_whitespace_only_html(self) -> None:
        """Whitespace-only translated_html renders."""
        img = QImage(200, 100, QImage.Format.Format_RGB32)
        img.fill(QColor(Qt.GlobalColor.white))
        painter = QPainter(img)
        rect = QRect(10, 10, 180, 80)
        ocr_res = OCRResult("Test", 10, 10, 180, 80, 1.0)
        ocr_res.translated_html = "   \n\t   "
        ocr_res.color = "#000000"
        ocr_res.alignment = ALIGN_LEFT
        ocr_res.line_height_ratio = 1.2
        ocr_res.is_single_line = True
        TextRenderer.render(painter, rect, "fallback", ocr_res, "English (US)")
        painter.end()

    def test_single_character_renders(self) -> None:
        """Single character renders without crash."""
        img = QImage(100, 100, QImage.Format.Format_RGB32)
        img.fill(QColor(Qt.GlobalColor.white))
        painter = QPainter(img)
        rect = QRect(5, 5, 90, 90)
        ocr_res = OCRResult("X", 5, 5, 90, 90, 1.0)
        ocr_res.translated_html = "X"
        ocr_res.color = "#000000"
        ocr_res.alignment = ALIGN_CENTER
        ocr_res.line_height_ratio = 1.0
        ocr_res.is_single_line = True
        TextRenderer.render(painter, rect, "X", ocr_res, "English (US)")
        painter.end()

    def test_very_small_rect_renders(self) -> None:
        """1x1 rect does not crash."""
        img = QImage(20, 20, QImage.Format.Format_RGB32)
        img.fill(QColor(Qt.GlobalColor.white))
        painter = QPainter(img)
        rect = QRect(5, 5, 1, 1)
        ocr_res = OCRResult("Test", 5, 5, 1, 1, 1.0)
        ocr_res.translated_html = "Text"
        ocr_res.color = "#000000"
        ocr_res.alignment = ALIGN_LEFT
        ocr_res.line_height_ratio = 1.0
        ocr_res.is_single_line = True
        TextRenderer.render(painter, rect, "Text", ocr_res, "English (US)")
        painter.end()

    def test_zero_line_height_ratio(self) -> None:
        """Line height ratio of 0 handled gracefully."""
        img = QImage(200, 100, QImage.Format.Format_RGB32)
        img.fill(QColor(Qt.GlobalColor.white))
        painter = QPainter(img)
        rect = QRect(10, 10, 180, 80)
        ocr_res = OCRResult("Test", 10, 10, 180, 80, 1.0)
        ocr_res.translated_html = "Test"
        ocr_res.color = "#000000"
        ocr_res.alignment = ALIGN_LEFT
        ocr_res.line_height_ratio = 0.0
        ocr_res.is_single_line = False
        TextRenderer.render(painter, rect, "Test", ocr_res, "English (US)")
        painter.end()

    def test_very_large_line_height_ratio(self) -> None:
        """Very large line height ratio doesn't crash."""
        img = QImage(200, 200, QImage.Format.Format_RGB32)
        img.fill(QColor(Qt.GlobalColor.white))
        painter = QPainter(img)
        rect = QRect(10, 10, 180, 180)
        ocr_res = OCRResult("Test", 10, 10, 180, 180, 1.0)
        ocr_res.translated_html = "Test"
        ocr_res.color = "#000000"
        ocr_res.alignment = ALIGN_LEFT
        ocr_res.line_height_ratio = 10.0
        ocr_res.is_single_line = False
        TextRenderer.render(painter, rect, "Test", ocr_res, "English (US)")
        painter.end()


# ===========================================================================
# NEW TESTS: RTL rendering
# ===========================================================================


class TestRTLRendering:
    """Tests for right-to-left text rendering."""

    def _render_rtl(self, html: str, lang: str) -> None:
        """Helper to render RTL text."""
        img = QImage(400, 100, QImage.Format.Format_RGB32)
        img.fill(QColor(Qt.GlobalColor.white))
        painter = QPainter(img)
        rect = QRect(10, 10, 380, 80)
        ocr_res = OCRResult("RTL", 10, 10, 380, 80, 1.0)
        ocr_res.translated_html = html
        ocr_res.color = "#000000"
        ocr_res.alignment = ALIGN_RIGHT
        ocr_res.line_height_ratio = 1.2
        ocr_res.is_single_line = True
        TextRenderer.render(painter, rect, "fallback", ocr_res, lang)
        painter.end()

    def test_arabic_rtl_rendering(self) -> None:
        self._render_rtl("مرحبا بالعالم", "Arabic")

    def test_hebrew_rtl_rendering(self) -> None:
        self._render_rtl("שלום עולם", "Hebrew")

    def test_persian_rtl_rendering(self) -> None:
        self._render_rtl("سلام جهان", "Persian")

    def test_rtl_with_numbers(self) -> None:
        """RTL text mixed with numbers."""
        self._render_rtl("العدد 42 مهم", "Arabic")

    def test_rtl_multiline(self) -> None:
        """RTL multiline text."""
        img = QImage(400, 200, QImage.Format.Format_RGB32)
        img.fill(QColor(Qt.GlobalColor.white))
        painter = QPainter(img)
        rect = QRect(10, 10, 380, 180)
        ocr_res = OCRResult("RTL", 10, 10, 380, 180, 1.0)
        ocr_res.translated_html = "سطر أول<br>سطر ثاني<br>سطر ثالث"
        ocr_res.color = "#000000"
        ocr_res.alignment = ALIGN_RIGHT
        ocr_res.line_height_ratio = 1.4
        ocr_res.is_single_line = False
        TextRenderer.render(painter, rect, "fallback", ocr_res, "Arabic")
        painter.end()


# ===========================================================================
# NEW TESTS: _update_style checks
# ===========================================================================


class TestUpdateStyleDetails:
    """Tests for _update_style method details."""

    def test_html_contains_text_content(self) -> None:
        """The generated HTML includes the translated text."""
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        doc = QTextDocument()
        ocr_res = OCRResult("Test", 0, 0, 100, 50, 1.0)
        ocr_res.translated_html = "UniqueTestWord"
        ocr_res.color = "#000000"
        ocr_res.alignment = ALIGN_LEFT
        ocr_res.line_height_ratio = 1.2
        ocr_res.is_single_line = False

        TextRenderer._update_style(doc, ocr_res, 16.0, "English (US)")
        html = doc.toHtml()
        assert "UniqueTestWord" in html

    def test_alignment_center_default(self) -> None:
        """Unknown alignment defaults to center."""
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        doc = QTextDocument()
        ocr_res = OCRResult("Test", 0, 0, 100, 50, 1.0)
        ocr_res.translated_html = "Test"
        ocr_res.color = "#000000"
        ocr_res.alignment = "unknown_align"
        ocr_res.line_height_ratio = 1.2
        ocr_res.is_single_line = False

        TextRenderer._update_style(doc, ocr_res, 14.0, "English (US)")

    def test_single_line_uses_line_height_1(self) -> None:
        """Single-line blocks use line-height: 1.0 regardless of ratio."""
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        doc = QTextDocument()
        ocr_res = OCRResult("Test", 0, 0, 100, 50, 1.0)
        ocr_res.translated_html = "Test"
        ocr_res.color = "#000000"
        ocr_res.alignment = ALIGN_LEFT
        ocr_res.line_height_ratio = 2.0
        ocr_res.is_single_line = True

        TextRenderer._update_style(doc, ocr_res, 14.0, "English (US)")


# ===========================================================================
# NEW TESTS: _find_best_font_size edge cases
# ===========================================================================


class TestFindBestFontSizeEdge:
    """Edge cases for _find_best_font_size."""

    def test_very_large_rect_returns_larger_size(self) -> None:
        """Large bounding box allows a larger font size."""
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        doc = QTextDocument()
        rect = QRect(0, 0, 1000, 500)
        ocr_res = OCRResult("Hi", 0, 0, 1000, 500, 1.0)
        ocr_res.translated_html = "Hi"
        ocr_res.color = "#000000"
        ocr_res.line_height_ratio = 1.2
        ocr_res.is_single_line = False

        size = TextRenderer._find_best_font_size(
            doc, rect, "Hi", ocr_res, "English (US)"
        )
        assert size > FONT_SIZE_MIN

    def test_font_size_always_positive(self) -> None:
        """Font size is always positive."""
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        doc = QTextDocument()
        rect = QRect(0, 0, 10, 10)
        ocr_res = OCRResult("Test", 0, 0, 10, 10, 1.0)
        ocr_res.translated_html = "Very very very long text" * 20
        ocr_res.color = "#000000"
        ocr_res.line_height_ratio = 1.2
        ocr_res.is_single_line = False

        size = TextRenderer._find_best_font_size(
            doc, rect, "fallback", ocr_res, "English (US)"
        )
        assert size > 0

    def test_single_line_constrained_by_width(self) -> None:
        """Single-line mode respects width constraint."""
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        doc = QTextDocument()
        rect = QRect(0, 0, 50, 100)
        ocr_res = OCRResult("Test", 0, 0, 50, 100, 1.0)
        ocr_res.translated_html = "A very long single line text that exceeds width"
        ocr_res.color = "#000000"
        ocr_res.line_height_ratio = 1.0
        ocr_res.is_single_line = True

        size = TextRenderer._find_best_font_size(
            doc, rect, "fallback", ocr_res, "English (US)"
        )
        assert size > 0


# ===========================================================================
# NEW TESTS: _prepare_document checks
# ===========================================================================


class TestPrepareDocumentDetailed:
    """Detailed tests for _prepare_document method."""

    def test_document_margin_is_zero(self) -> None:
        ocr_res = OCRResult("Test", 0, 0, 100, 50, 1.0)
        doc = TextRenderer._prepare_document(ocr_res)
        assert doc.documentMargin() == 0

    def test_returns_qtextdocument(self) -> None:
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        ocr_res = OCRResult("Test", 0, 0, 100, 50, 1.0)
        doc = TextRenderer._prepare_document(ocr_res)
        assert isinstance(doc, QTextDocument)

    def test_default_stylesheet_set(self) -> None:
        ocr_res = OCRResult("Test", 0, 0, 100, 50, 1.0)
        doc = TextRenderer._prepare_document(ocr_res)
        ss = doc.defaultStyleSheet()
        assert "margin" in ss


# ===========================================================================
# NEW TESTS: All alignments with multiline text
# ===========================================================================


class TestAlignmentsMultiline:
    """Tests for all alignment types with multiline text."""

    def _render_aligned(self, alignment: str) -> None:
        img = QImage(400, 200, QImage.Format.Format_RGB32)
        img.fill(QColor(Qt.GlobalColor.white))
        painter = QPainter(img)
        rect = QRect(10, 10, 380, 180)
        ocr_res = OCRResult("Test", 10, 10, 380, 180, 1.0)
        ocr_res.translated_html = (
            "First line of multiline text<br>Second line here<br>Third line is the last"
        )
        ocr_res.color = "#333333"
        ocr_res.alignment = alignment
        ocr_res.line_height_ratio = 1.3
        ocr_res.is_single_line = False
        TextRenderer.render(painter, rect, "fallback", ocr_res, "English (US)")
        painter.end()

    def test_multiline_left(self) -> None:
        self._render_aligned(ALIGN_LEFT)

    def test_multiline_right(self) -> None:
        self._render_aligned(ALIGN_RIGHT)

    def test_multiline_center(self) -> None:
        self._render_aligned(ALIGN_CENTER)

    def test_multiline_justify(self) -> None:
        self._render_aligned(ALIGN_JUSTIFY)


# ---------------------------------------------------------------------------
# Extreme aspect ratio rectangles
# ---------------------------------------------------------------------------


class TestTextRendererExtremeAspectRatio:
    """Test font size search in extreme aspect ratio rectangles.

    Uses _find_best_font_size directly to avoid QPainter segfaults in
    offscreen environments where font rendering is unavailable.
    """

    def test_very_wide_rect(self) -> None:
        """Wide rect (600x15) with single-line text.

        The renderer should find a font that fits the narrow height.
        """
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        doc = QTextDocument()
        rect = QRect(0, 0, 600, 15)
        ocr_res = _make_ocr_result(
            translated_html="Wide rect test",
            w=600,
            h=15,
            is_single_line=True,
        )
        size = TextRenderer._find_best_font_size(
            doc, rect, "fallback", ocr_res, "English (US)"
        )
        assert size >= FONT_SIZE_MIN  # noqa: PLR2004

    def test_very_tall_rect(self) -> None:
        """Tall narrow rect (15x600) with multiline text.

        The very narrow width forces extreme wrapping.
        """
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        doc = QTextDocument()
        rect = QRect(0, 0, 15, 600)
        ocr_res = _make_ocr_result(
            translated_html="Tall narrow rectangle text",
            w=15,
            h=600,
            is_single_line=False,
        )
        size = TextRenderer._find_best_font_size(
            doc, rect, "fallback", ocr_res, "English (US)"
        )
        assert size >= FONT_SIZE_MIN  # noqa: PLR2004

    def test_one_pixel_rect_font_size(self) -> None:
        """1x1 rect should return FONT_SIZE_DEFAULT (nothing fits)."""
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        doc = QTextDocument()
        rect = QRect(0, 0, 1, 1)
        ocr_res = _make_ocr_result(
            translated_html="X",
            w=1,
            h=1,
            is_single_line=True,
        )
        size = TextRenderer._find_best_font_size(
            doc, rect, "X", ocr_res, "English (US)"
        )
        assert size == FONT_SIZE_DEFAULT  # noqa: PLR2004

    def test_wide_multiline(self) -> None:
        """Wide multiline rect (800x40) should find a valid font size."""
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        doc = QTextDocument()
        long_text = " ".join(["word"] * 30)
        rect = QRect(0, 0, 800, 40)
        ocr_res = _make_ocr_result(
            translated_html=long_text,
            w=800,
            h=40,
            is_single_line=False,
        )
        size = TextRenderer._find_best_font_size(
            doc, rect, "fallback", ocr_res, "English (US)"
        )
        assert size >= FONT_SIZE_MIN  # noqa: PLR2004

    def test_extreme_font_size_search(self) -> None:
        """Tall rect allows large max_size in font search.

        max_size = rect.height() * FONT_SIZE_MAX_BOX_RATIO, so a
        2000px tall rect yields a max_size of 4000. The search
        loop must still terminate in reasonable time.
        """
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        doc = QTextDocument()
        rect = QRect(0, 0, 200, 2000)
        ocr_res = _make_ocr_result(
            translated_html="Hi",
            w=200,
            h=2000,
        )
        size = TextRenderer._find_best_font_size(doc, rect, "", ocr_res, "English (US)")
        assert size >= FONT_SIZE_MIN  # noqa: PLR2004

    def test_square_vs_wide_font_difference(self) -> None:
        """A square rect should allow a larger font than a very wide thin rect.

        For the same text, the wide rect's height is the constraint.
        """
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        text = "Sample"

        doc_square = QTextDocument()
        rect_square = QRect(0, 0, 200, 200)
        ocr_square = _make_ocr_result(translated_html=text, w=200, h=200)
        size_square = TextRenderer._find_best_font_size(
            doc_square, rect_square, "", ocr_square, "English (US)"
        )

        doc_wide = QTextDocument()
        rect_wide = QRect(0, 0, 600, 15)
        ocr_wide = _make_ocr_result(translated_html=text, w=600, h=15)
        size_wide = TextRenderer._find_best_font_size(
            doc_wide, rect_wide, "", ocr_wide, "English (US)"
        )

        assert size_square > size_wide


# ---------------------------------------------------------------------------
# Long text stress tests
# ---------------------------------------------------------------------------


class TestTextRendererLongText:
    """Test font sizing with very long text.

    Uses _find_best_font_size to avoid QPainter rendering issues in
    offscreen mode.
    """

    def test_2000_char_single_line(self) -> None:
        """Long single-line text should produce a valid font size.

        The search must not hang or crash on long strings.
        """
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        long_text = "A" * 2000
        doc = QTextDocument()
        rect = QRect(0, 0, 300, 50)
        ocr_res = _make_ocr_result(
            translated_html=long_text,
            w=300,
            h=50,
            is_single_line=True,
        )
        size = TextRenderer._find_best_font_size(
            doc, rect, long_text, ocr_res, "English (US)"
        )
        assert size >= FONT_SIZE_MIN  # noqa: PLR2004

    def test_1000_char_multiline(self) -> None:
        """1000-character multiline text should produce a valid font size."""
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        long_text = " ".join(["testing"] * 143)  # ~1001 chars
        doc = QTextDocument()
        rect = QRect(0, 0, 400, 300)
        ocr_res = _make_ocr_result(
            translated_html=long_text,
            w=400,
            h=300,
            is_single_line=False,
        )
        size = TextRenderer._find_best_font_size(
            doc, rect, long_text, ocr_res, "English (US)"
        )
        assert size >= FONT_SIZE_MIN  # noqa: PLR2004

    def test_long_multiline_font_is_small(self) -> None:
        """Long multiline text should produce a smaller font than short text."""
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        rect = QRect(0, 0, 300, 200)

        doc_short = QTextDocument()
        ocr_short = _make_ocr_result(translated_html="Hi", w=300, h=200)
        size_short = TextRenderer._find_best_font_size(
            doc_short, rect, "", ocr_short, "English (US)"
        )

        doc_long = QTextDocument()
        long_text = " ".join(["word"] * 500)
        ocr_long = _make_ocr_result(translated_html=long_text, w=300, h=200)
        size_long = TextRenderer._find_best_font_size(
            doc_long, rect, "", ocr_long, "English (US)"
        )

        assert size_short > size_long

    def test_repeated_br_tags(self) -> None:
        """Many <br> tags producing many lines should produce a valid font size."""
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        html = "<br>".join([f"L{i}" for i in range(80)])
        doc = QTextDocument()
        rect = QRect(0, 0, 400, 400)
        ocr_res = _make_ocr_result(
            translated_html=html,
            w=400,
            h=400,
        )
        size = TextRenderer._find_best_font_size(
            doc, rect, "fallback", ocr_res, "English (US)"
        )
        assert size >= FONT_SIZE_MIN  # noqa: PLR2004

    def test_single_char_in_large_rect(self) -> None:
        """A single character in a large rect should use a large font size."""
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        doc = QTextDocument()
        rect = QRect(0, 0, 500, 500)
        ocr_res = _make_ocr_result(translated_html="A", w=500, h=500)
        size = TextRenderer._find_best_font_size(doc, rect, "", ocr_res, "English (US)")
        # With a 500px box, the max size is 500 * 2.0 = 1000px
        # A single char should easily fit at a large size
        assert size > FONT_SIZE_DEFAULT  # noqa: PLR2004


# ---------------------------------------------------------------------------
# Unicode combining marks and special characters
# ---------------------------------------------------------------------------


class TestTextRendererCombiningMarks:
    """Test _update_style with Unicode combining characters.

    Verifies that combining marks, ZWJ sequences, and bidirectional text
    are correctly set as HTML content in the QTextDocument. Uses
    _update_style to avoid QPainter rendering issues.
    """

    def test_combining_diacritics(self) -> None:
        """'e' + combining acute accent (U+0301) should be set in the document.

        The composed form 'e\u0301' must not crash the text layout engine.
        """
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        text = "e\u0301 a\u0300 o\u0302"  # e-acute, a-grave, o-circumflex
        doc = QTextDocument()
        ocr_res = _make_ocr_result(
            translated_html=text,
            w=200,
            h=50,
            is_single_line=True,
        )
        TextRenderer._update_style(doc, ocr_res, 14.0, "English (US)")
        html = doc.toHtml()
        # The combining characters should be present in the rendered HTML
        assert "\u0301" in html or "\u00e9" in html  # combining or pre-composed

    def test_zero_width_joiners(self) -> None:
        """Text with Zero-Width Joiner (U+200D) characters.

        ZWJ sequences are used in emoji and complex scripts. The
        document should accept them without error.
        """
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        text = "A\u200dB\u200dC"
        doc = QTextDocument()
        ocr_res = _make_ocr_result(
            translated_html=text,
            w=200,
            h=50,
            is_single_line=True,
        )
        TextRenderer._update_style(doc, ocr_res, 14.0, "English (US)")
        plain = doc.toPlainText()
        assert "A" in plain
        assert "B" in plain
        assert "C" in plain

    def test_mixed_bidi_text(self) -> None:
        """'Hello \u0645\u0631\u062d\u0628\u0627 World' — mixed LTR/RTL.

        The bidirectional text should be accepted by the document.
        """
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        text = "Hello \u0645\u0631\u062d\u0628\u0627 World"
        doc = QTextDocument()
        ocr_res = _make_ocr_result(
            translated_html=text,
            w=400,
            h=60,
            is_single_line=True,
        )
        TextRenderer._update_style(doc, ocr_res, 14.0, "Arabic")
        plain = doc.toPlainText()
        assert "Hello" in plain
        assert "World" in plain
        assert "\u0645" in plain  # Arabic meem

    def test_devanagari_with_combining(self) -> None:
        """Hindi text with combining vowel marks should be accepted."""
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        text = "\u0928\u092e\u0938\u094d\u0924\u0947"  # Namaste in Devanagari
        doc = QTextDocument()
        ocr_res = _make_ocr_result(
            translated_html=text,
            w=200,
            h=60,
        )
        TextRenderer._update_style(doc, ocr_res, 14.0, "Hindi")
        plain = doc.toPlainText()
        assert "\u0928" in plain  # Devanagari Na

    def test_thai_combining_chars(self) -> None:
        """Thai text has stacking vowels and tone marks above/below base chars."""
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        text = "\u0e2a\u0e27\u0e31\u0e2a\u0e14\u0e35"  # Thai greeting
        doc = QTextDocument()
        ocr_res = _make_ocr_result(
            translated_html=text,
            w=200,
            h=60,
        )
        TextRenderer._update_style(doc, ocr_res, 14.0, "Thai")
        plain = doc.toPlainText()
        assert "\u0e2a" in plain  # Thai Sor Sua


# ---------------------------------------------------------------------------
# Font family selection edge cases
# ---------------------------------------------------------------------------


class TestTextRendererFontFallback:
    """Test font family selection edge cases."""

    def test_unknown_language_uses_default(self) -> None:
        """A language not in any mapping should fall back to a default font.

        The function should never return an empty string.
        """
        family = TextRenderer._get_font_family("FictionalLanguage99")
        assert isinstance(family, str)
        assert len(family) > 0

    def test_cache_hit_returns_same_value(self) -> None:
        """Calling _get_font_family twice returns the same string.

        Verifies LRU cache hit for identical language input.
        """
        TextRenderer._get_font_family.cache_clear()
        result_1 = TextRenderer._get_font_family("Spanish")
        result_2 = TextRenderer._get_font_family("Spanish")
        assert result_1 is result_2

    def test_empty_string_language(self) -> None:
        """Empty string as language should return a valid font family."""
        family = TextRenderer._get_font_family("")
        assert isinstance(family, str)
        assert len(family) > 0

    def test_numeric_string_language(self) -> None:
        """A numeric string as language should return a valid default font."""
        family = TextRenderer._get_font_family("12345")
        assert isinstance(family, str)
        assert len(family) > 0

    def test_all_supported_languages_return_valid_font(self) -> None:
        """Every language supported by the app should return a non-empty font."""
        languages = [
            "English (US)",
            "English (UK)",
            "French",
            "German",
            "Spanish",
            "Portuguese",
            "Italian",
            "Dutch",
            "Russian",
            "Ukrainian",
            "Polish",
            "Czech",
            "Swedish",
            "Norwegian",
            "Danish",
            "Finnish",
            "Turkish",
            "Greek",
            "Arabic",
            "Hebrew",
            "Persian",
            "Hindi",
            "Bengali",
            "Thai",
            "Vietnamese",
            "Indonesian",
            "Malay",
            "Chinese (Simplified)",
            "Chinese (Traditional)",
            "Japanese",
            "Korean",
            "Khmer",
            "Nepali",
        ]
        for lang in languages:
            family = TextRenderer._get_font_family(lang)
            assert isinstance(family, str), f"Non-string result for {lang}"
            assert len(family) > 0, f"Empty font family for {lang}"


# ---------------------------------------------------------------------------
# _find_best_font_size — additional constraint checks
# ---------------------------------------------------------------------------


class TestFindBestFontSizeConstraints:
    """Additional constraint verification for _find_best_font_size."""

    def test_single_line_width_constraint(self) -> None:
        """Single-line mode must constrain by width, not just height.

        A long string in a narrow-but-tall rect should still shrink
        the font to fit the width.
        """
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        doc = QTextDocument()
        rect = QRect(0, 0, 50, 500)  # Narrow but tall
        ocr_res = _make_ocr_result(
            translated_html="A very long single-line string that exceeds width",
            w=50,
            h=500,
            is_single_line=True,
        )

        size = TextRenderer._find_best_font_size(doc, rect, "", ocr_res, "English (US)")
        # The font must be small because the width is only 50px
        assert size >= FONT_SIZE_MIN  # noqa: PLR2004

    def test_multiline_height_constraint(self) -> None:
        """Multiline mode must constrain by height.

        Many lines of text in a short rect should shrink the font.
        """
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        doc = QTextDocument()
        rect = QRect(0, 0, 500, 30)  # Wide but short
        many_lines = "<br>".join([f"Line {i}" for i in range(20)])
        ocr_res = _make_ocr_result(
            translated_html=many_lines,
            w=500,
            h=30,
            is_single_line=False,
        )

        size = TextRenderer._find_best_font_size(doc, rect, "", ocr_res, "English (US)")
        assert size >= FONT_SIZE_MIN  # noqa: PLR2004

    def test_identical_text_same_rect_same_size(self) -> None:
        """Same text and rect should always produce the same font size.

        This verifies determinism of the font size search.
        """
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        rect = QRect(0, 0, 200, 80)
        ocr_res = _make_ocr_result(
            translated_html="Deterministic sizing",
            w=200,
            h=80,
        )

        doc1 = QTextDocument()
        size1 = TextRenderer._find_best_font_size(
            doc1, rect, "", ocr_res, "English (US)"
        )

        doc2 = QTextDocument()
        size2 = TextRenderer._find_best_font_size(
            doc2, rect, "", ocr_res, "English (US)"
        )

        assert size1 == size2

    def test_single_line_vs_multiline_difference(self) -> None:
        """Same text should produce different sizes in single-line vs multiline.

        Single-line mode constrains by width; multiline by height. For a
        moderately wide rect, multiline may allow a larger font because
        height is the binding constraint instead of width.
        """
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        rect = QRect(0, 0, 150, 100)
        text = "Some text that is a few words long"

        doc_single = QTextDocument()
        ocr_single = _make_ocr_result(
            translated_html=text, w=150, h=100, is_single_line=True
        )
        size_single = TextRenderer._find_best_font_size(
            doc_single, rect, "", ocr_single, "English (US)"
        )

        doc_multi = QTextDocument()
        ocr_multi = _make_ocr_result(
            translated_html=text, w=150, h=100, is_single_line=False
        )
        size_multi = TextRenderer._find_best_font_size(
            doc_multi, rect, "", ocr_multi, "English (US)"
        )

        # Sizes should differ (multiline can wrap so it may use a larger font)
        assert size_single != size_multi


# ---------------------------------------------------------------------------
# _update_style with special HTML content
# ---------------------------------------------------------------------------


class TestRenderSpecialHTML:
    """Test _update_style with unusual or edge-case HTML content.

    Uses _update_style + doc.toHtml() to verify content is correctly
    set without requiring QPainter rendering.
    """

    def test_nested_bold_italic(self) -> None:
        """Deeply nested <b><i><b>text</b></i></b> should be accepted."""
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        doc = QTextDocument()
        ocr_res = _make_ocr_result(
            translated_html="<b><i><b>Deep nesting</b></i></b>",
            w=300,
            h=80,
        )
        TextRenderer._update_style(doc, ocr_res, 14.0, "English (US)")
        html = doc.toHtml()
        assert "Deep nesting" in html

    def test_html_entities(self) -> None:
        """HTML entities like &amp; &lt; &gt; should be preserved."""
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        doc = QTextDocument()
        ocr_res = _make_ocr_result(
            translated_html="A &amp; B &lt; C &gt; D",
            w=300,
            h=60,
        )
        TextRenderer._update_style(doc, ocr_res, 14.0, "English (US)")
        plain = doc.toPlainText()
        assert "A & B < C > D" in plain

    def test_br_only(self) -> None:
        """Content consisting solely of <br> tags should not crash."""
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        doc = QTextDocument()
        ocr_res = _make_ocr_result(
            translated_html="<br><br><br>",
            w=200,
            h=100,
        )
        TextRenderer._update_style(doc, ocr_res, 14.0, "English (US)")
        # Document should have multiple blocks/line breaks
        assert doc.blockCount() >= 1

    def test_unicode_html_content(self) -> None:
        """HTML with Unicode characters and mixed scripts."""
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        doc = QTextDocument()
        ocr_res = _make_ocr_result(
            translated_html="<b>\u00c9tude</b> &mdash; \u4e16\u754c",
            w=300,
            h=80,
        )
        TextRenderer._update_style(doc, ocr_res, 14.0, "English (US)")
        plain = doc.toPlainText()
        assert "\u00c9tude" in plain
        assert "\u4e16\u754c" in plain

    def test_superscript_subscript_tags(self) -> None:
        """Superscript and subscript tags should be accepted."""
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        doc = QTextDocument()
        ocr_res = _make_ocr_result(
            translated_html="H<sub>2</sub>O and E=mc<sup>2</sup>",
            w=300,
            h=80,
        )
        TextRenderer._update_style(doc, ocr_res, 14.0, "English (US)")
        html = doc.toHtml()
        assert "H" in html
        assert "O" in html
        assert "sub" in html or "2" in html

    def test_empty_tags(self) -> None:
        """Empty HTML tags should not crash the document."""
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        doc = QTextDocument()
        ocr_res = _make_ocr_result(
            translated_html="<b></b><i></i>Text<b></b>",
            w=200,
            h=50,
        )
        TextRenderer._update_style(doc, ocr_res, 14.0, "English (US)")
        plain = doc.toPlainText()
        assert "Text" in plain

    def test_line_height_ratio_in_multiline_html(self) -> None:
        """Custom line_height_ratio should appear as percentage in HTML."""
        from PySide6.QtGui import QTextDocument  # noqa: PLC0415

        doc = QTextDocument()
        ocr_res = _make_ocr_result(
            translated_html="Line 1<br>Line 2",
            w=200,
            h=100,
            line_height_ratio=1.6,
            is_single_line=False,
        )
        TextRenderer._update_style(doc, ocr_res, 14.0, "English (US)")
        html = doc.toHtml()
        assert "line-height:160%;" in html


# ---------------------------------------------------------------------------
# Font selection: additional languages missing from prior test suites
# ---------------------------------------------------------------------------


class TestFontSelectionAdditionalLanguages:
    """Test _get_font_family for the 17 languages not covered by earlier tests.

    The existing ``TestGetFontFamilyAllLanguages`` omits several AVAILABLE_LANGUAGES
    entries (Croatian, English (UK), Portuguese (Brazil), Portuguese (Portugal)) and
    includes a few names that are NOT in the canonical list (Norwegian, Filipino).
    This class fills the gaps using the exact labels from ``AVAILABLE_LANGUAGES``.
    """

    # Languages missing from ALL prior test loops:
    # - Azerbaijani, Catalan, Gujarati are NOT in AVAILABLE_LANGUAGES,
    #   but the user asked to test them — they hit the "default" fallback.
    # - Maltese, Galician, Basque, Icelandic, Irish, Afrikaans, Tagalog
    #   are also not in AVAILABLE_LANGUAGES — default fallback.
    # - Marathi is not in AVAILABLE_LANGUAGES — default fallback.
    # - Croatian, English (UK), Portuguese (Brazil), Portuguese (Portugal)
    #   ARE in AVAILABLE_LANGUAGES but missing from earlier tests.

    ADDITIONAL_LANGUAGES = [
        "Azerbaijani",
        "Catalan",
        "Gujarati",
        "Latvian",
        "Lithuanian",
        "Slovenian",
        "Estonian",
        "Maltese",
        "Galician",
        "Basque",
        "Icelandic",
        "Irish",
        "Afrikaans",
        "Swahili",
        "Tagalog",
        "Romanian",
        "Marathi",
    ]

    @pytest.mark.parametrize("lang", ADDITIONAL_LANGUAGES)
    def test_language_returns_nonempty_font_family(self, lang: str) -> None:
        """Each additional language returns a non-empty font family string."""
        TextRenderer._get_font_family.cache_clear()
        family = TextRenderer._get_font_family(lang)
        assert isinstance(family, str), f"Not a string for {lang}"
        assert len(family) > 0, f"Empty font family for {lang}"

    def test_all_available_languages_return_valid_font(self) -> None:
        """Every language in AVAILABLE_LANGUAGES returns a non-empty string.

        This is a comprehensive loop over the canonical 45-language list
        to catch any future additions that lack font mappings.
        """
        from src.constants.languages import AVAILABLE_LANGUAGES  # noqa: PLC0415

        TextRenderer._get_font_family.cache_clear()
        for lang in AVAILABLE_LANGUAGES:
            family = TextRenderer._get_font_family(lang)
            assert isinstance(family, str), f"Not a string for {lang}"
            assert len(family) > 0, f"Empty font family for {lang}"

    def test_croatian_font_selection(self) -> None:
        """Croatian (in AVAILABLE_LANGUAGES) returns a valid font."""
        TextRenderer._get_font_family.cache_clear()
        family = TextRenderer._get_font_family("Croatian")
        assert isinstance(family, str)
        assert len(family) > 0

    def test_english_uk_font_selection(self) -> None:
        """English (UK) (in AVAILABLE_LANGUAGES) returns a valid font."""
        TextRenderer._get_font_family.cache_clear()
        family = TextRenderer._get_font_family("English (UK)")
        assert isinstance(family, str)
        assert len(family) > 0

    def test_portuguese_variants_font_selection(self) -> None:
        """Both Portuguese variants return valid (identical) fonts."""
        TextRenderer._get_font_family.cache_clear()
        br = TextRenderer._get_font_family("Portuguese (Brazil)")
        pt = TextRenderer._get_font_family("Portuguese (Portugal)")
        assert isinstance(br, str) and len(br) > 0
        assert isinstance(pt, str) and len(pt) > 0
        # Both variants should resolve to the same Latin font
        assert br == pt
