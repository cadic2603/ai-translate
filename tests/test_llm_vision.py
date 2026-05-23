"""Tests for LLM vision-based image translation (Rich Text Mode)."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.core.llm_engine import translate_image_content
from src.core.ocr_engine import OCRResult


@pytest.fixture
def mock_ocr_results():
    return [OCRResult("Bold word and normal", 10, 10, 200, 30, 0.9)]


def _make_genai_text_response(text: str) -> SimpleNamespace:
    """Builds a fake google.genai response with .text accessor."""
    return SimpleNamespace(text=text)


def _make_mock_genai_client(*, response_text: str) -> MagicMock:
    """Returns a MagicMock that mimics google.genai.Client for vision tests."""
    client = MagicMock()
    client.models.generate_content.return_value = _make_genai_text_response(
        response_text,
    )
    return client


@patch("src.core.llm_engine._config.load_setting")
@patch("src.core.llm_engine._build_gemini_client")
def test_translate_image_content_rich_text(
    mock_build_client,
    mock_load_setting,
    mock_ocr_results,
    tmp_path,
):
    # Setup mocks
    mock_load_setting.side_effect = lambda key, default=None: {
        "llm/method": "Gemini",
        "llm/gemini_api_key": "fake-key",
        "llm/gemini_model": "gemini-2.5-flash",
    }.get(key, default)

    paragraphs = [
        {
            "ids": [0],
            "translated_html": "Mot <b>gras</b> et normal",
            "color": "#000000",
            "alignment": "left",
        }
    ]

    inner = json.dumps({"paragraphs": paragraphs})
    mock_build_client.return_value = _make_mock_genai_client(response_text=inner)

    image_path = tmp_path / "test.jpg"
    image_path.write_bytes(b"fake image data")

    results = translate_image_content(str(image_path), mock_ocr_results, "French")

    assert len(results) == 1
    assert "<b>gras</b>" in results[0]["translated_html"]


@patch("src.core.llm_engine._config.load_setting")
@patch("src.core.llm_engine._build_gemini_client")
def test_translate_image_content_mixed_colors(
    mock_build_client,
    mock_load_setting,
    mock_ocr_results,
    tmp_path,
):
    # Setup mocks
    mock_load_setting.side_effect = lambda key, default=None: {
        "llm/method": "Gemini",
        "llm/gemini_api_key": "fake-key",
        "llm/gemini_model": "gemini-2.5-flash",
    }.get(key, default)

    paragraphs = [
        {
            "ids": [0],
            "translated_html": 'Text with <span style="color: #FF0000">red</span> word',
            "color": "#000000",
            "alignment": "left",
        }
    ]

    inner = json.dumps({"paragraphs": paragraphs})
    mock_build_client.return_value = _make_mock_genai_client(response_text=inner)

    image_path = tmp_path / "test_color.jpg"
    image_path.write_bytes(b"fake image data")

    results = translate_image_content(str(image_path), [mock_ocr_results[0]], "French")

    assert len(results) == 1
    assert 'span style="color: #FF0000"' in results[0]["translated_html"]


def test_translate_image_content_empty_ocr_results(tmp_path) -> None:
    """Empty OCR results list returns [] without any API call."""
    image_path = tmp_path / "test.jpg"
    image_path.write_bytes(b"fake image data")

    results = translate_image_content(str(image_path), [], "French")

    assert results == []


@patch("src.core.llm_engine._config.load_setting")
@patch("src.core.llm_engine._build_openai_client")
def test_translate_image_content_custom_provider(
    mock_build_client,
    mock_load_setting,
    mock_ocr_results,
    tmp_path,
) -> None:
    """Custom (OpenAI-compatible) provider returns paragraphs correctly."""
    mock_load_setting.side_effect = lambda key, default=None: {
        "llm/method": "Custom",
        "llm/custom_api_key": "fake-custom-key",
        "llm/custom_model": "gpt-4o",
        "llm/custom_endpoint": "https://api.openai.com/v1",
    }.get(key, default)

    paragraphs = [
        {
            "ids": [0],
            "translated_html": "Bonjour le monde",
            "color": "#000000",
            "alignment": "left",
        }
    ]

    # SDK returns ChatCompletion → choices[0].message.content
    content = json.dumps({"paragraphs": paragraphs})
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
    )
    # Vision callsite wraps the client via ``client.with_options(timeout=...)``
    # — return the same mock so the chained .chat.completions.create still
    # hits our scripted return_value.
    mock_client.with_options.return_value = mock_client
    mock_build_client.return_value = mock_client

    image_path = tmp_path / "test.png"
    image_path.write_bytes(b"fake image data")

    results = translate_image_content(str(image_path), mock_ocr_results, "French")

    assert len(results) == 1
    assert results[0]["translated_html"] == "Bonjour le monde"


@patch("src.core.llm_engine._config.load_setting")
def test_translate_image_content_custom_auth_error(
    mock_load_setting,
    mock_ocr_results,
    tmp_path,
) -> None:
    """Custom provider raises AUTH_ERROR when credentials are missing."""
    mock_load_setting.side_effect = lambda key, default=None: {
        "llm/method": "Custom",
        "llm/custom_api_key": "",  # empty
        "llm/custom_model": "",
        "llm/custom_endpoint": "",
    }.get(key, default)

    image_path = tmp_path / "test.png"
    image_path.write_bytes(b"fake image data")

    with pytest.raises(ValueError, match="AUTH_ERROR"):
        translate_image_content(str(image_path), mock_ocr_results, "French")


@patch("src.core.llm_engine._resolve_provider_model")
def test_translate_image_content_unknown_provider(
    mock_resolve,
    mock_ocr_results,
    tmp_path,
) -> None:
    """Unknown LLM provider returns empty list."""
    mock_resolve.return_value = ("SomeFutureLLM", "")

    image_path = tmp_path / "test.jpg"
    image_path.write_bytes(b"fake image data")

    results = translate_image_content(str(image_path), mock_ocr_results, "French")

    assert results == []
