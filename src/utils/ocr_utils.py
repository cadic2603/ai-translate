"""Utility functions for OCR engine handling and spatial adjustments."""

from src.constants.ocr import (
    OCR_METHOD_EASYOCR,
    OCR_PADDING_DEFAULT,
    OCR_PADDING_EASYOCR,
)


def get_ocr_padding(method: str) -> tuple[int, int]:
    """Returns the (removal, insertion) padding values for a given OCR method.

    Args:
        method (str): The OCR method name.

    Returns:
        tuple[int, int]: (padding_remove, padding_insert)
    """
    if method == OCR_METHOD_EASYOCR:
        return OCR_PADDING_EASYOCR

    return OCR_PADDING_DEFAULT
