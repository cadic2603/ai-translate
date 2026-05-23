"""Image processing utilities for text removal and rendering.

This module handles removal of original text via color-matched solid fills
and rendering of translated text via the TextRenderer module.
"""

import logging
from collections import Counter

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QImage, QPainter

from src.constants.ocr import OCR_METHOD_TESSERACT
from src.core.ocr_engine import OCRResult
from src.core.text_renderer import TextRenderer
from src.utils.ocr_utils import get_ocr_padding

logger = logging.getLogger("image_processor")


def process_image_translation(  # noqa: PLR0913
    image_path: str,
    output_path: str,
    ocr_results: list[OCRResult],
    translations: list[str],
    target_lang: str = "English (US)",
    raw_ocr_results: list[OCRResult] | None = None,
    ocr_method: str = OCR_METHOD_TESSERACT,
) -> bool:
    """Process an image by removing original text and inserting translations.

    Args:
        image_path: Path to the source image file.
        output_path: Path where the translated image will be saved.
        ocr_results: Merged OCR result objects (bounding boxes for rendering).
        translations: Translated strings aligned 1:1 with *ocr_results*.
        target_lang: Target language name for font/script selection.
        raw_ocr_results: Unmerged OCR fragments for text removal (falls back
            to *ocr_results* when ``None``).
        ocr_method: OCR engine identifier controlling padding values.
    """
    if len(ocr_results) != len(translations):
        logger.error("Mismatch between OCR results and translations.")
        return False

    image = QImage(image_path)
    if image.isNull():
        logger.error("Failed to load image: %s", image_path)
        return False

    # Convert indexed/palette images (GIFs, 8-bit PNGs) to ARGB32.
    # WARNING: QPainter silently fails on Format_Indexed8 — do not remove.
    if image.format() not in (
        QImage.Format.Format_ARGB32_Premultiplied,
        QImage.Format.Format_ARGB32,
        QImage.Format.Format_RGB32,
    ):
        image = image.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)

    # 1. Background Reconstruction (Removal)
    _remove_original_text(image, raw_ocr_results or ocr_results, ocr_method)

    # 2. Foreground Reconstruction (Insertion)
    _insert_translated_text(image, ocr_results, translations, target_lang, ocr_method)

    # Force quality=100 for JPEGs to prevent compounding compression
    # artifacts across repeated read/write translation cycles.
    if str(output_path).lower().endswith((".jpg", ".jpeg")):
        return image.save(output_path, quality=100)
    return image.save(output_path)


def _remove_original_text(
    image: QImage,
    fragments: list[OCRResult],
    method: str,
) -> None:
    """Clear original text regions using engine-specific padding.

    Args:
        image: The QImage to paint over (modified in place).
        fragments: OCR result objects with x/y/w/h bounding boxes.
        method: OCR engine identifier for padding lookup.
    """
    padding_remove, _ = get_ocr_padding(method)
    painter = QPainter(image)
    try:
        for res in fragments:
            rect = QRect(
                res.x - padding_remove,
                res.y - padding_remove,
                res.w + (padding_remove * 2),
                res.h + (padding_remove * 2),
            )
            bg_color = _guess_bg_color(image, rect)
            painter.fillRect(rect, bg_color)
    finally:
        painter.end()


def _insert_translated_text(
    image: QImage,
    results: list[OCRResult],
    translations: list[str],
    lang: str,
    method: str,
) -> None:
    """Render translated text onto the image using TextRenderer.

    Args:
        image: The QImage to paint on (modified in place).
        results: Merged OCR result objects with bounding-box geometry.
        translations: Translated strings aligned 1:1 with *results*.
        lang: Target language name for font/script selection.
        method: OCR engine identifier for padding lookup.
    """
    _, padding_insert = get_ocr_padding(method)
    painter = QPainter(image)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        for res, trans in zip(results, translations, strict=True):
            if not trans:
                continue
            rect = QRect(
                res.x - padding_insert,
                res.y - padding_insert,
                res.w + (padding_insert * 2),
                res.h + (padding_insert * 2),
            )
            TextRenderer.render(painter, rect, trans, res, lang)
    finally:
        painter.end()


def _guess_bg_color(image: QImage, rect: QRect) -> QColor:
    """Guesses the background color by sampling pixels around the rectangle.

    Uses a histogram-based Mode (most frequent color) approach to perfectly
    match the surrounding background without blending or averaging artifacts.

    Args:
        image (QImage): Source image.
        rect (QRect): Bounding box of the text to be removed.

    Returns:
        QColor: The most frequent color sampled from the perimeter.
    """
    points = []
    offset = 2

    # Dense sampling every 2 pixels around the perimeter for high accuracy
    step = 2

    # Top and Bottom edges
    for x in range(rect.left(), rect.right() + 1, step):
        points.append(QPoint(x, max(0, rect.top() - offset)))
        points.append(QPoint(x, min(image.height() - 1, rect.bottom() + offset)))

    # Left and Right edges
    for y in range(rect.top(), rect.bottom() + 1, step):
        points.append(QPoint(max(0, rect.left() - offset), y))
        points.append(QPoint(min(image.width() - 1, rect.right() + offset), y))

    if not points:
        return QColor(Qt.GlobalColor.white)

    # Collect QRgb values (ints) for efficient counting
    colors = [
        image.pixel(p)
        for p in points
        if 0 <= p.x() < image.width() and 0 <= p.y() < image.height()
    ]

    if not colors:
        return QColor(Qt.GlobalColor.white)

    # Use Mode (most common color) to preserve sharp boundaries.
    counts = Counter(colors)
    most_common_rgb = counts.most_common(1)[0][0]

    return QColor(most_common_rgb)
