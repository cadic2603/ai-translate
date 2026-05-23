"""Text rendering engine with advanced typography and layout handling.

This module encapsulates the complexity of rendering translated text onto
images, including dynamic font scaling, alignment-aware positioning,
and rich text formatting using QTextDocument.
"""

from functools import lru_cache

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import (
    QPainter,
    QTextBlockFormat,
    QTextDocument,
    QTextOption,
)

from src.constants.ocr import OCR_SINGLE_LINE_TOLERANCE_PX
from src.constants.ui import (
    FONT_SIZE_DEFAULT,
    FONT_SIZE_MAX_BOX_RATIO,
    FONT_SIZE_MIN,
    FONT_SIZE_STEP,
)
from src.core.checkpoint import ALIGN_CENTER, ALIGN_JUSTIFY, ALIGN_LEFT, ALIGN_RIGHT
from src.core.ocr_engine import OCRResult


class TextRenderer:
    """Handles the layout and drawing of text blocks with dynamic scaling."""

    @staticmethod
    def render(
        painter: QPainter,
        rect: QRect,
        text: str,
        ocr_result: OCRResult,
        target_lang: str,
    ) -> None:
        """Renders a single text block with automatic font scaling and alignment.

        Args:
            painter: The active QPainter instance.
            rect: The bounding box to draw within.
            text: The plain text (fallback if HTML is missing).
            ocr_result: OCR result containing metadata (alignment, single-line status).
            target_lang: The target language for font selection.
        """
        doc = TextRenderer._prepare_document(ocr_result)

        # 1. Search for optimal font size based on constraints
        best_size = TextRenderer._find_best_font_size(
            doc, rect, text, ocr_result, target_lang
        )

        # 2. Finalize document layout with selected size
        TextRenderer._update_style(doc, ocr_result, best_size, target_lang)

        # Use idealWidth for manual offset if single line
        doc_w = doc.idealWidth() if ocr_result.is_single_line else rect.width()
        doc.setTextWidth(doc_w)

        # 3. Anchoring and Drawing
        # Vertical centering calculation
        y_offset = (rect.height() - doc.size().height()) / 2

        # Horizontal alignment offset manual calculation for single lines
        x_offset = 0.0
        if ocr_result.is_single_line:
            if ocr_result.alignment == ALIGN_RIGHT:
                x_offset = rect.width() - doc_w
            elif ocr_result.alignment == ALIGN_CENTER:
                x_offset = (rect.width() - doc_w) / 2
            # ALIGN_LEFT (default) stays at 0.0, allowing growth to the right

        painter.save()
        painter.translate(rect.left() + x_offset, rect.top() + y_offset)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        doc.drawContents(painter)
        painter.restore()

    @staticmethod
    def _find_best_font_size(
        doc: QTextDocument, rect: QRect, text: str, ocr_res: OCRResult, target_lang: str
    ) -> float:
        """Iteratively shrinks font size until the text fits the bounding box.

        Args:
            doc: The QTextDocument used for measurement.
            rect: The target bounding box.
            text: Plain text fallback.
            ocr_res: OCR metadata.
            target_lang: Language name.

        Returns:
            float: The optimal font size in pixels.
        """
        min_size, best_size = FONT_SIZE_MIN, FONT_SIZE_DEFAULT
        max_size = max(min_size + 1, rect.height() * FONT_SIZE_MAX_BOX_RATIO)

        # Configure wrapping constraints
        if ocr_res.is_single_line:
            option = doc.defaultTextOption()
            option.setWrapMode(QTextOption.WrapMode.NoWrap)
            doc.setDefaultTextOption(option)

        # Precise searching using defined steps
        num_steps = int((max_size - min_size) / FONT_SIZE_STEP)

        for i in range(num_steps, -1, -1):
            size = min_size + (i * FONT_SIZE_STEP)
            TextRenderer._update_style(doc, ocr_res, size, target_lang)

            # Measurement depends on wrapping mode
            if ocr_res.is_single_line:
                doc.setTextWidth(-1)  # Measure true unconstrained width
                current_w = doc.idealWidth()
            else:
                doc.setTextWidth(rect.width())
                current_w = doc.size().width()

            current_h = doc.size().height()

            # Allow single-line text to overflow the box by a small margin.
            # Left/right: all overflow goes to one side.
            # Center: overflow splits evenly on both sides.
            tolerance = OCR_SINGLE_LINE_TOLERANCE_PX if ocr_res.is_single_line else 0.0
            fits_height = current_h <= (rect.height() + tolerance)
            fits_width = not ocr_res.is_single_line or current_w <= (
                rect.width() + tolerance
            )

            if fits_height and fits_width:
                return size

        return best_size

    @staticmethod
    def _prepare_document(ocr_result: OCRResult) -> QTextDocument:
        """Initializes a QTextDocument with strict resets.

        Args:
            ocr_result: Base OCR metadata.

        Returns:
            QTextDocument: A clean document instance.
        """
        doc = QTextDocument()
        doc.setDocumentMargin(0)

        # Eliminate all default block margins to ensure pixel-perfect alignment
        fmt = QTextBlockFormat()
        for margin in ["Top", "Bottom", "Left", "Right"]:
            getattr(fmt, f"set{margin}Margin")(0)
        fmt.setIndent(0)

        cursor = doc.rootFrame().firstCursorPosition()
        cursor.setBlockFormat(fmt)

        # Base CSS reset for internal tags
        doc.setDefaultStyleSheet(
            "body, p, div, span {"
            " margin: 0; padding: 0;"
            " background-color: transparent; }"
        )
        return doc

    @staticmethod
    def _update_style(
        doc: QTextDocument, ocr_res: OCRResult, font_size: float, target_lang: str
    ) -> None:
        """Applies dynamic font styles and alignment to the document via HTML.

        Args:
            doc: Target document.
            ocr_res: OCR metadata.
            font_size: Calculated font size.
            target_lang: Language for font family selection.
        """
        font_family = TextRenderer._get_font_family(target_lang)

        # Map string alignment constants to CSS text-align values
        align_map = {
            ALIGN_LEFT: "left",
            ALIGN_RIGHT: "right",
            ALIGN_JUSTIFY: "justify",
        }
        align_str = align_map.get(ocr_res.alignment, "center")

        # Single-line text needs no inter-line spacing; use 1.0 to maximize font size
        effective_lh = 1.0 if ocr_res.is_single_line else ocr_res.line_height_ratio

        html = f"""
        <div style="color: {ocr_res.color}; font-family: '{font_family}';
                    font-size: {font_size}px; line-height: {effective_lh};
                    text-align: {align_str};">
            {ocr_res.translated_html}
        </div>
        """
        doc.setHtml(html)

    @staticmethod
    @lru_cache(maxsize=64)
    def _get_font_family(target_lang: str) -> str:
        """Selects a concrete font family for the target language.

        Delegates to the shared font utility in ``src/utils/font_utils.py``
        which returns the first candidate from the per-language font
        database for the sans-serif family.

        Args:
            target_lang: Name of the target language.

        Returns:
            str: The name of the preferred font family.
        """
        from src.utils.font_utils import (  # noqa: PLC0415
            FAMILY_SANS,
            get_font_for_language,
        )

        return get_font_for_language(target_lang, FAMILY_SANS)
