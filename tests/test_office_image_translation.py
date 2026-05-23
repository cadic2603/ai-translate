"""Focused tests for _translate_single_image from office_processor.

Separated from test_office_processor.py (which requires docx/openpyxl/pptx)
so these can run without those heavy dependencies.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.core.office_processor import _translate_single_image


def test_translate_single_image_forwards_src_lang_to_run_ocr() -> None:
    """_translate_single_image passes src_lang through to run_ocr."""
    fake_ocr = MagicMock(text="Hello", x=0, y=0, w=100, h=20, confidence=0.9)

    with (
        patch(
            "src.core.ocr_engine.run_ocr",
            return_value=[fake_ocr],
        ) as mock_ocr,
        patch(
            "src.core.llm_engine.translate_image_content",
            return_value=[
                {
                    "ids": [0],
                    "translated_html": "Bonjour",
                    "color": "#000",
                    "alignment": "left",
                }
            ],
        ),
        patch(
            "src.core.layout_analysis.merge_to_paragraphs",
            return_value=([], {}, []),
        ),
    ):
        # merged_results is empty → returns None before rendering
        result = _translate_single_image(
            b"fake png bytes",
            "image/png",
            "French",
            "English",
            glossary_entries=None,
            ocr_method="TesseractOCR",
        )

    assert result is None  # No merged results → None
    mock_ocr.assert_called_once()
    # Verify src_lang="English" was forwarded to run_ocr
    _, kwargs = mock_ocr.call_args
    assert kwargs["src_lang"] == "English"


def test_translate_single_image_unsupported_content_type_returns_none() -> None:
    """_translate_single_image returns None for unsupported MIME types."""
    result = _translate_single_image(
        b"data",
        "application/pdf",
        "French",
        "English",
        glossary_entries=None,
        ocr_method="TesseractOCR",
    )
    assert result is None


def test_translate_single_image_empty_ocr_returns_none() -> None:
    """Empty OCR results (no text detected) → returns None."""
    with patch(
        "src.core.ocr_engine.run_ocr",
        return_value=[],
    ):
        result = _translate_single_image(
            b"fake png bytes",
            "image/png",
            "French",
            "English",
            glossary_entries=None,
            ocr_method="TesseractOCR",
        )
    assert result is None


def test_translate_single_image_valueerror_propagates() -> None:
    """Fatal LLM errors (ValueError) propagate to the caller."""
    fake_ocr = MagicMock(text="Hi", x=0, y=0, w=50, h=20, confidence=0.9)
    with (
        patch("src.core.ocr_engine.run_ocr", return_value=[fake_ocr]),
        patch(
            "src.core.llm_engine.translate_image_content",
            side_effect=ValueError("AUTH_ERROR"),
        ),
        pytest.raises(ValueError, match="AUTH_ERROR"),
    ):
        _translate_single_image(
            b"fake png bytes",
            "image/png",
            "French",
            "English",
            glossary_entries=None,
            ocr_method="TesseractOCR",
        )


def test_translate_single_image_render_failure_returns_none() -> None:
    """process_image_translation returning False → returns None."""
    fake_ocr = MagicMock(text="Hi", x=0, y=0, w=50, h=20, confidence=0.9)
    fake_merged = MagicMock()

    with (
        patch("src.core.ocr_engine.run_ocr", return_value=[fake_ocr]),
        patch(
            "src.core.llm_engine.translate_image_content",
            return_value=[
                {
                    "ids": [0],
                    "translated_html": "Salut",
                    "color": "#000",
                    "alignment": "left",
                }
            ],
        ),
        patch(
            "src.core.layout_analysis.merge_to_paragraphs",
            return_value=([fake_merged], ["Salut"], [fake_ocr]),
        ),
        patch(
            "src.core.image_processor.process_image_translation",
            return_value=False,
        ),
    ):
        result = _translate_single_image(
            b"fake png bytes",
            "image/png",
            "French",
            "English",
            glossary_entries=None,
            ocr_method="TesseractOCR",
        )
    assert result is None


def test_translate_single_image_glossary_forwarded() -> None:
    """Glossary entries are forwarded to translate_image_content."""
    fake_ocr = MagicMock(text="Hi", x=0, y=0, w=50, h=20, confidence=0.9)
    glossary = [(1, "Hi", "Salut")]

    with (
        patch("src.core.ocr_engine.run_ocr", return_value=[fake_ocr]),
        patch(
            "src.core.llm_engine.translate_image_content",
            return_value=[],
        ) as mock_llm,
        patch(
            "src.core.layout_analysis.merge_to_paragraphs",
            return_value=([], [], []),
        ),
    ):
        _translate_single_image(
            b"fake png bytes",
            "image/png",
            "French",
            "English",
            glossary_entries=glossary,
            ocr_method="TesseractOCR",
        )

    _, kwargs = mock_llm.call_args
    assert kwargs["glossary_entries"] == glossary
