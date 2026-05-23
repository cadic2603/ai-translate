"""Tests for OpenAI-compatible Custom LLM provider."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest
from openai import (
    APIStatusError,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
)

from src.constants.llm import (
    CONTENT_DATA_VALUES,
    CONTENT_HTML,
    CONTENT_MARKDOWN,
    CONTENT_PLAIN_TEXT,
    CONTENT_RTF,
    CONTENT_XML,
    get_content_type,
)
from src.core.llm_engine import (
    _build_image_translation_prompt,
    _build_translation_prompt,
    _format_glossary_block,
    _format_glossary_hint,
    _format_lang_pair,
    translate_image_content,
    translate_text,
)

# --- Fixtures ---

CUSTOM_SETTINGS = {
    "llm/method": "Custom",
    "llm/custom_api_key": "sk-test-key",
    "llm/custom_model": "gpt-4o",
    "llm/custom_endpoint": "https://api.openai.com/v1",
}


def _mock_load_setting(
    overrides: dict | None = None,
) -> object:
    """Returns a load_setting mock with optional overrides."""
    settings = {**CUSTOM_SETTINGS, **(overrides or {})}
    return lambda key, default="": settings.get(key, default)


def _make_sdk_chat_response(content: dict) -> SimpleNamespace:
    """Builds a fake openai chat.completions response with JSON-encoded content."""
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=json.dumps(content)),
            ),
        ],
    )


def _sdk_http_error(  # noqa: PLR0911
    status: int,
    message: str = "Unsupported",
) -> Exception:
    """Builds the openai SDK exception that maps to *status*."""
    request = httpx.Request("POST", "https://test/v1/chat/completions")
    body = {"error": {"message": message}}
    response = httpx.Response(status, request=request, json=body)
    if status == 400:
        return BadRequestError(message=message, response=response, body=body)
    if status == 401:
        return AuthenticationError(message=message, response=response, body=body)
    if status == 403:
        return PermissionDeniedError(message=message, response=response, body=body)
    if status == 404:
        return NotFoundError(message=message, response=response, body=body)
    if status == 429:
        return RateLimitError(message=message, response=response, body=body)
    return APIStatusError(message=message, response=response, body=body)


def _make_sdk_client(
    *,
    chat_response: SimpleNamespace | None = None,
    chat_error: Exception | None = None,
) -> MagicMock:
    """Returns a mock openai.OpenAI client."""
    client = MagicMock()
    # Reflect the mock back from ``with_options`` so callers like
    # ``client.with_options(timeout=...).responses.create(...)`` reach
    # the configured ``client.responses.create``.
    client.with_options.return_value = client
    if chat_error is not None:
        client.chat.completions.create.side_effect = chat_error
    elif chat_response is not None:
        client.chat.completions.create.return_value = chat_response
    return client


# --- Text Translation ---


@patch("src.core.llm_engine._build_openai_client")
@patch("src.core.llm_engine._config.load_setting")
def test_translate_custom_text_success(
    mock_load: MagicMock,
    mock_build_client: MagicMock,
) -> None:
    """Successful text translation via Custom provider."""
    mock_load.side_effect = _mock_load_setting()
    mock_build_client.return_value = _make_sdk_client(
        chat_response=_make_sdk_chat_response(
            {
                "results": [
                    {"id": 0, "translated": "Bonjour"},
                    {"id": 1, "translated": "Le monde"},
                ],
            },
        ),
    )

    result = translate_text(
        ["Hello", "World"],
        "French",
        "English (US)",
        content_type=CONTENT_DATA_VALUES,
    )
    assert result == ["Bonjour", "Le monde"]


@patch("src.core.llm_engine._config.load_setting")
def test_translate_custom_text_auth_error_no_key(
    mock_load: MagicMock,
) -> None:
    """Raises AUTH_ERROR when API key is empty."""
    mock_load.side_effect = _mock_load_setting(
        {"llm/custom_api_key": ""},
    )
    with pytest.raises(ValueError, match="AUTH_ERROR"):
        translate_text(["Hello"], "French")


@patch("src.core.llm_engine._config.load_setting")
def test_translate_custom_text_auth_error_no_endpoint(
    mock_load: MagicMock,
) -> None:
    """Raises AUTH_ERROR when endpoint is empty."""
    mock_load.side_effect = _mock_load_setting(
        {"llm/custom_endpoint": ""},
    )
    with pytest.raises(ValueError, match="AUTH_ERROR"):
        translate_text(["Hello"], "French")


@patch("src.core.llm_engine._config.load_setting")
def test_translate_custom_text_auth_error_no_model(
    mock_load: MagicMock,
) -> None:
    """Raises AUTH_ERROR when model is empty."""
    mock_load.side_effect = _mock_load_setting(
        {"llm/custom_model": ""},
    )
    with pytest.raises(ValueError, match="AUTH_ERROR"):
        translate_text(["Hello"], "French")


@patch("src.core.llm_engine._build_openai_client")
@patch("src.core.llm_engine._config.load_setting")
def test_translate_custom_text_http_429(
    mock_load: MagicMock,
    mock_build_client: MagicMock,
) -> None:
    """Maps HTTP 429 to QUOTA_ERROR."""
    mock_load.side_effect = _mock_load_setting()
    mock_build_client.return_value = _make_sdk_client(chat_error=_sdk_http_error(429))
    with pytest.raises(ValueError, match="QUOTA_ERROR"):
        translate_text(["Hello"], "French")


@patch("src.core.llm_engine._build_openai_client")
@patch("src.core.llm_engine._config.load_setting")
def test_translate_custom_text_http_401(
    mock_load: MagicMock,
    mock_build_client: MagicMock,
) -> None:
    """Maps HTTP 401 to AUTH_ERROR."""
    mock_load.side_effect = _mock_load_setting()
    mock_build_client.return_value = _make_sdk_client(chat_error=_sdk_http_error(401))
    with pytest.raises(ValueError, match="AUTH_ERROR"):
        translate_text(["Hello"], "French")


@patch("src.core.llm_engine._build_openai_client")
@patch("src.core.llm_engine._config.load_setting")
def test_translate_custom_text_http_404(
    mock_load: MagicMock,
    mock_build_client: MagicMock,
) -> None:
    """Maps HTTP 404 to MODEL_NOT_FOUND."""
    mock_load.side_effect = _mock_load_setting()
    mock_build_client.return_value = _make_sdk_client(
        chat_error=_sdk_http_error(404, "model not found"),
    )
    with pytest.raises(
        ValueError,
        match="MODEL_NOT_FOUND",
    ):
        translate_text(["Hello"], "French")


@patch("src.core.llm_engine._build_openai_client")
@patch("src.core.llm_engine._config.load_setting")
def test_translate_custom_text_http_413(
    mock_load: MagicMock,
    mock_build_client: MagicMock,
) -> None:
    """Maps HTTP 413 to REQUEST_TOO_LARGE."""
    mock_load.side_effect = _mock_load_setting()
    mock_build_client.return_value = _make_sdk_client(chat_error=_sdk_http_error(413))
    with pytest.raises(
        ValueError,
        match="REQUEST_TOO_LARGE",
    ):
        translate_text(["Hello"], "French")


@patch("src.core.llm_engine.time.sleep")
@patch("src.core.llm_engine._build_openai_client")
@patch("src.core.llm_engine._config.load_setting")
def test_translate_custom_text_http_500(
    mock_load: MagicMock,
    mock_build_client: MagicMock,
    _mock_sleep: MagicMock,
) -> None:
    """Maps HTTP 500 to SERVICE_UNAVAILABLE_ERROR."""
    mock_load.side_effect = _mock_load_setting()
    mock_build_client.return_value = _make_sdk_client(chat_error=_sdk_http_error(500))
    with pytest.raises(
        ValueError,
        match="SERVICE_UNAVAILABLE_ERROR",
    ):
        translate_text(["Hello"], "French")


# --- Image Translation ---


@patch("src.core.llm_engine._build_openai_client")
@patch("src.core.llm_engine._config.load_setting")
def test_translate_custom_image_success(
    mock_load: MagicMock,
    mock_build_client: MagicMock,
    tmp_path: object,
) -> None:
    """Successful image translation via Custom vision API."""
    mock_load.side_effect = _mock_load_setting()
    paragraphs = [
        {
            "ids": [0],
            "translated_html": "Bonjour",
            "color": "#000",
            "alignment": "left",
        }
    ]
    mock_build_client.return_value = _make_sdk_client(
        chat_response=_make_sdk_chat_response({"paragraphs": paragraphs}),
    )

    img_path = tmp_path / "test.jpg"
    img_path.write_bytes(b"\xff\xd8\xff\xe0")

    ocr_result = MagicMock()
    ocr_result.text = "Hello"
    result = translate_image_content(
        str(img_path),
        [ocr_result],
        "French",
        "English (US)",
    )
    assert result == paragraphs


@patch("src.core.llm_engine._build_openai_client")
@patch("src.core.llm_engine._config.load_setting")
def test_translate_custom_image_vision_not_supported(
    mock_load: MagicMock,
    mock_build_client: MagicMock,
    tmp_path: object,
) -> None:
    """Detects vision-unsupported, raises VISION_NOT_SUPPORTED."""
    mock_load.side_effect = _mock_load_setting()
    mock_build_client.return_value = _make_sdk_client(
        chat_error=_sdk_http_error(400, "This model does not support image inputs"),
    )

    img_path = tmp_path / "test.jpg"
    img_path.write_bytes(b"\xff\xd8\xff\xe0")

    ocr_result = MagicMock()
    ocr_result.text = "Hello"
    with pytest.raises(
        ValueError,
        match="VISION_NOT_SUPPORTED",
    ):
        translate_image_content(
            str(img_path),
            [ocr_result],
            "French",
            "English (US)",
        )


# --- Config Validation ---


def test_check_llm_setup_custom_requires_all_fields() -> None:
    """Custom provider requires endpoint AND model (API key is optional)."""
    from src.utils.config_manager import check_llm_setup  # noqa: PLC0415

    # All fields present -> True
    with patch(
        "src.utils.config_manager.load_setting",
        side_effect=_mock_load_setting(),
    ):
        assert check_llm_setup() is True

    # Missing endpoint -> False
    with patch(
        "src.utils.config_manager.load_setting",
        side_effect=_mock_load_setting(
            {"llm/custom_endpoint": ""},
        ),
    ):
        assert check_llm_setup() is False

    # Missing model -> False
    with patch(
        "src.utils.config_manager.load_setting",
        side_effect=_mock_load_setting(
            {"llm/custom_model": ""},
        ),
    ):
        assert check_llm_setup() is False

    # Missing API key -> True (custom endpoints may be keyless / local)
    with patch(
        "src.utils.config_manager.load_setting",
        side_effect=_mock_load_setting(
            {"llm/custom_api_key": ""},
        ),
    ):
        assert check_llm_setup() is True


# --- Prompt Builder Tests ---


def test_build_prompt_plain_text() -> None:
    """Plain text prompt should not mention HTML/XML/RTF."""
    prompt = _build_translation_prompt(
        CONTENT_PLAIN_TEXT,
        "English",
        "French",
    )
    assert "HTML" not in prompt
    assert "XML" not in prompt
    assert "RTF" not in prompt
    assert "Markdown" not in prompt
    assert "fluent" in prompt
    assert "whitespace" in prompt


def test_build_prompt_markdown() -> None:
    """Markdown prompt should mention Markdown syntax keywords."""
    prompt = _build_translation_prompt(
        CONTENT_MARKDOWN,
        "English",
        "French",
    )
    assert "Markdown" in prompt
    assert "headings" in prompt
    assert "code blocks" in prompt
    assert "[__PRESERVE_MD_N__]" in prompt
    assert "HTML" not in prompt


def test_build_prompt_html() -> None:
    """HTML prompt should mention tags and translatable attribute values."""
    prompt = _build_translation_prompt(
        CONTENT_HTML,
        "English",
        "French",
    )
    assert "HTML" in prompt
    assert "tags" in prompt
    assert "attribute values" in prompt
    assert "Markdown" not in prompt
    assert "RTF" not in prompt


def test_build_prompt_auto_lang() -> None:
    """Empty source language (auto-detect) should not appear in the prompt."""
    prompt = _build_translation_prompt(
        CONTENT_PLAIN_TEXT,
        "",
        "Vietnamese",
    )
    assert "Vietnamese" in prompt
    assert "into Vietnamese" in prompt


def test_build_prompt_explicit_lang() -> None:
    """Explicit source language should appear as 'from X to Y'."""
    prompt = _build_translation_prompt(
        CONTENT_PLAIN_TEXT,
        "English",
        "French",
    )
    assert "from English" in prompt
    assert "to French" in prompt


def test_build_prompt_with_glossary() -> None:
    """Glossary entries should appear in the prompt."""
    entries = [
        (1, "apple", "pomme"),
        (2, "car", "voiture"),
    ]
    prompt = _build_translation_prompt(
        CONTENT_PLAIN_TEXT,
        "English",
        "French",
        entries,
    )
    assert "Glossary" in prompt
    assert "apple = pomme" in prompt
    assert "car = voiture" in prompt


def test_build_prompt_without_glossary() -> None:
    """No glossary should not add glossary block."""
    prompt = _build_translation_prompt(
        CONTENT_PLAIN_TEXT,
        "English",
        "French",
    )
    assert "Glossary" not in prompt


def test_format_lang_pair_auto() -> None:
    """Empty source (auto-detect) should produce 'into target' phrasing."""
    result = _format_lang_pair("", "Japanese")
    assert result == "Translate the following into Japanese."


def test_format_lang_pair_explicit() -> None:
    """Explicit source should produce 'from X to Y' phrasing."""
    result = _format_lang_pair("English", "French")
    assert "from English" in result
    assert "to French" in result


def test_format_glossary_block_empty() -> None:
    """Empty glossary returns empty string."""
    assert _format_glossary_block(None) == ""
    assert _format_glossary_block([]) == ""


def test_format_glossary_block_entries() -> None:
    """Glossary block uses '=' separator and '|' delimiter."""
    entries = [(1, "hello", "xin chào"), (2, "world", "thế giới")]
    result = _format_glossary_block(entries)
    assert "hello = xin chào" in result
    assert "world = thế giới" in result
    assert "|" in result


def test_format_glossary_hint_empty() -> None:
    """Empty glossary hint returns empty string."""
    assert _format_glossary_hint(None) == ""
    assert _format_glossary_hint([]) == ""


def test_format_glossary_hint_entries() -> None:
    """Glossary hint uses '<->' separator for image prompts."""
    entries = [(1, "hello", "xin chào"), (2, "world", "thế giới")]
    result = _format_glossary_hint(entries)
    assert "hello <-> xin chào" in result
    assert "world <-> thế giới" in result
    assert "glossary" in result.lower()


def test_format_glossary_hint_single_entry() -> None:
    """Single-entry glossary still formats correctly."""
    result = _format_glossary_hint([(1, "cat", "mèo")])
    assert "cat <-> mèo" in result
    assert "," not in result.split("glossary")[-1].split("cat")[0]


def test_build_prompt_preserves_tone_and_context() -> None:
    """Prose prompts should instruct tone/context preservation."""
    for ctype in (
        CONTENT_PLAIN_TEXT,
        CONTENT_MARKDOWN,
        CONTENT_HTML,
        CONTENT_XML,
        CONTENT_RTF,
    ):
        prompt = _build_translation_prompt(
            ctype,
            "English",
            "French",
        )
        assert "tone" in prompt, f"{ctype} missing tone"
        assert "context" in prompt, f"{ctype} missing context"
        assert "naturally" in prompt, f"{ctype} missing naturally"


def test_build_prompt_data_values_no_tone() -> None:
    """Data values prompt should not include tone/context guidance."""
    prompt = _build_translation_prompt(
        CONTENT_DATA_VALUES,
        "English",
        "French",
    )
    assert "tone" not in prompt
    assert "concise" in prompt


def test_get_content_type_mapping() -> None:
    """File extensions map to correct content types."""
    assert get_content_type(".txt") == CONTENT_PLAIN_TEXT
    assert get_content_type(".md") == CONTENT_MARKDOWN
    assert get_content_type(".html") == CONTENT_HTML
    assert get_content_type(".htm") == CONTENT_HTML
    assert get_content_type(".xml") == CONTENT_XML
    assert get_content_type(".rtf") == CONTENT_RTF
    assert get_content_type(".json") == CONTENT_DATA_VALUES
    assert get_content_type(".csv") == CONTENT_DATA_VALUES
    # Unknown extension defaults to plain_text
    assert get_content_type(".xyz") == CONTENT_PLAIN_TEXT


# --- Image Translation Prompt Tests ---


def test_image_prompt_contains_target_language() -> None:
    """Target language must appear in the image prompt."""
    prompt = _build_image_translation_prompt("Vietnamese", "")
    assert "Vietnamese" in prompt


def test_image_prompt_contains_glossary_hint() -> None:
    """Glossary hint is embedded in the image prompt."""
    hint = "\nGlossary: hello <-> xin chào"
    prompt = _build_image_translation_prompt("French", hint)
    assert "hello <-> xin chào" in prompt


def test_image_prompt_requires_json_output() -> None:
    """Image prompt instructs the LLM to return JSON with 'paragraphs'."""
    prompt = _build_image_translation_prompt("Korean", "")
    assert "paragraphs" in prompt
    assert "JSON" in prompt


def test_image_prompt_mentions_ocr_and_image() -> None:
    """Image prompt references OCR fragments and the source image."""
    prompt = _build_image_translation_prompt("Spanish", "")
    assert "OCR" in prompt
    assert "image" in prompt.lower()


def test_image_prompt_mentions_html_tags() -> None:
    """Image prompt instructs the use of HTML tags for styling."""
    prompt = _build_image_translation_prompt("German", "")
    assert "<b>" in prompt
    assert "<i>" in prompt
    assert "<br>" in prompt


def test_image_prompt_empty_glossary() -> None:
    """Empty glossary string does not add spurious text."""
    prompt = _build_image_translation_prompt("Japanese", "")
    assert "Glossary" not in prompt


# --- Glossary Formatting Edge Cases ---


def test_format_glossary_block_single_entry() -> None:
    """Single entry produces no pipe separator."""
    entries = [(1, "cat", "mèo")]
    result = _format_glossary_block(entries)
    assert "cat = mèo" in result
    assert "|" not in result


def test_format_glossary_block_pipe_in_term() -> None:
    """Entry containing pipe char does not break formatting."""
    entries = [(1, "A|B", "C|D")]
    result = _format_glossary_block(entries)
    assert "A|B = C|D" in result


def test_format_glossary_block_equals_in_term() -> None:
    """Entry containing equals char is still formatted correctly."""
    entries = [(1, "x=1", "x bằng 1")]
    result = _format_glossary_block(entries)
    # The output uses " = " as separator, so the entry's "=" is embedded
    assert "x=1 = x bằng 1" in result


def test_format_glossary_block_many_entries() -> None:
    """Multiple entries are joined with pipe separators."""
    entries = [(i, f"src{i}", f"tgt{i}") for i in range(5)]
    result = _format_glossary_block(entries)
    assert result.count("|") == 4  # noqa: PLR2004
    for i in range(5):
        assert f"src{i} = tgt{i}" in result


def test_format_glossary_block_unicode_entries() -> None:
    """Entries with full Unicode are preserved in output."""
    entries = [
        (1, "Straße", "Street"),
        (2, "日本語", "Japanese"),
    ]
    result = _format_glossary_block(entries)
    assert "Straße = Street" in result
    assert "日本語 = Japanese" in result


def test_format_glossary_hint_pipe_in_term() -> None:
    """Entry containing special chars in hint format."""
    entries = [(1, "A|B", "C<->D")]
    result = _format_glossary_hint(entries)
    assert "A|B <-> C<->D" in result


def test_format_glossary_hint_many_entries() -> None:
    """Multiple entries are comma-separated in hint."""
    entries = [(i, f"s{i}", f"t{i}") for i in range(4)]
    result = _format_glossary_hint(entries)
    # Entries are joined with ", "
    assert result.count("<->") == 4  # noqa: PLR2004
    for i in range(4):
        assert f"s{i} <-> t{i}" in result


def test_format_glossary_hint_unicode() -> None:
    """Unicode entries are preserved in hint output."""
    entries = [(1, "café", "quán cà phê")]
    result = _format_glossary_hint(entries)
    assert "café <-> quán cà phê" in result


# --- Content Type Mapping Edge Cases ---


def test_get_content_type_case_insensitive() -> None:
    """get_content_type handles uppercase extensions."""
    assert get_content_type(".TXT") == CONTENT_PLAIN_TEXT
    assert get_content_type(".HTML") == CONTENT_HTML
    assert get_content_type(".MD") == CONTENT_MARKDOWN


def test_get_content_type_epub_not_in_mapping() -> None:
    """EPUB is not in the extension mapping (handled separately)."""
    # .epub is processed by _process_epub, not _process_plain
    result = get_content_type(".epub")
    assert result == CONTENT_PLAIN_TEXT  # falls back to default


def test_get_content_type_all_known_extensions() -> None:
    """All file extensions in the mapping resolve correctly."""
    from src.constants.llm import CONTENT_RTF, CONTENT_XML  # noqa: PLC0415

    assert get_content_type(".txt") == CONTENT_PLAIN_TEXT
    assert get_content_type(".md") == CONTENT_MARKDOWN
    assert get_content_type(".html") == CONTENT_HTML
    assert get_content_type(".htm") == CONTENT_HTML
    assert get_content_type(".xml") == CONTENT_XML
    assert get_content_type(".rtf") == CONTENT_RTF
    assert get_content_type(".json") == CONTENT_DATA_VALUES
    assert get_content_type(".csv") == CONTENT_DATA_VALUES


# --- Prompt Builder Edge Cases ---


def test_build_prompt_xml_preserves_structure() -> None:
    """XML prompt instructs preserving all XML structure."""
    from src.constants.llm import CONTENT_XML  # noqa: PLC0415

    prompt = _build_translation_prompt(
        CONTENT_XML,
        "English",
        "French",
    )
    assert "XML" in prompt
    assert "tags" in prompt
    assert "[__PRESERVE_XML_N__]" in prompt


def test_build_prompt_rtf_preserves_control_words() -> None:
    """RTF prompt instructs preserving RTF control words."""
    from src.constants.llm import CONTENT_RTF  # noqa: PLC0415

    prompt = _build_translation_prompt(
        CONTENT_RTF,
        "English",
        "French",
    )
    assert "RTF" in prompt
    assert "[__PRESERVE_RTF_N__]" in prompt


def test_build_prompt_epub_mentions_xhtml() -> None:
    """EPUB prompt mentions XHTML/HTML tags."""
    from src.constants.llm import CONTENT_EPUB  # noqa: PLC0415

    prompt = _build_translation_prompt(
        CONTENT_EPUB,
        "English",
        "French",
    )
    assert "XHTML" in prompt or "HTML" in prompt
    assert "tags" in prompt


def test_build_prompt_unknown_type_falls_back() -> None:
    """Unknown content type falls back to plain text rules."""
    prompt = _build_translation_prompt(
        "unknown_type",
        "English",
        "French",
    )
    assert "fluent" in prompt
    assert "whitespace" in prompt


def test_build_prompt_json_output_required() -> None:
    """All content types require JSON output format."""
    for ctype in (
        CONTENT_PLAIN_TEXT,
        CONTENT_MARKDOWN,
        CONTENT_HTML,
        CONTENT_DATA_VALUES,
    ):
        prompt = _build_translation_prompt(
            ctype,
            "English",
            "French",
        )
        assert "JSON" in prompt
        assert "results" in prompt


# ---------------------------------------------------------------------------
# translate_text: early-exit and optimization paths
# ---------------------------------------------------------------------------


def test_translate_text_empty_input() -> None:
    """Empty list returns empty list immediately without any LLM call."""
    result = translate_text([], "French")
    assert result == []


@patch("src.core.llm_engine._build_openai_client")
@patch("src.core.llm_engine._config.load_setting")
def test_translate_text_all_untranslatable(
    mock_load: MagicMock,
    mock_build_client: MagicMock,
) -> None:
    """Items that are all-untranslatable return as-is without calling the LLM."""
    mock_load.side_effect = _mock_load_setting()
    texts = ["12345", "https://example.com", "user@mail.com"]

    result = translate_text(texts, "French")

    assert result == texts
    mock_build_client.assert_not_called()


@patch("src.core.llm_engine._build_openai_client")
@patch("src.core.llm_engine._config.load_setting")
def test_translate_text_cancel_check(
    mock_load: MagicMock,
    mock_build_client: MagicMock,
) -> None:
    """cancel_check=True prevents LLM call and returns original texts."""
    mock_load.side_effect = _mock_load_setting()

    result = translate_text(
        ["Hello", "World"],
        "French",
        cancel_check=lambda: True,
    )

    # LLM not called
    mock_build_client.assert_not_called()
    # Originals returned unchanged
    assert result == ["Hello", "World"]


@patch("src.core.llm_engine._build_openai_client")
@patch("src.core.llm_engine._config.load_setting")
def test_translate_text_deduplicates_input(
    mock_load: MagicMock,
    mock_build_client: MagicMock,
) -> None:
    """Duplicate texts are translated once; result is copied to all positions."""
    mock_load.side_effect = _mock_load_setting()
    client = _make_sdk_client(
        chat_response=_make_sdk_chat_response(
            {
                "results": [
                    {"id": 0, "translated": "Bonjour"},
                    {"id": 1, "translated": "Le monde"},
                ],
            },
        ),
    )
    mock_build_client.return_value = client

    result = translate_text(
        ["Hello", "World", "Hello"],  # "Hello" appears at index 0 and 2
        "French",
        content_type=CONTENT_DATA_VALUES,
    )

    assert result[0] == "Bonjour"  # first "Hello"
    assert result[1] == "Le monde"  # "World"
    assert result[2] == "Bonjour"  # second "Hello" (deduplicated)
    # Only one chat call made (2 unique items fit in one batch)
    assert client.chat.completions.create.call_count == 1


# ---------------------------------------------------------------------------
# Additional HTTP error code coverage
# ---------------------------------------------------------------------------


@patch("src.core.llm_engine._build_openai_client")
@patch("src.core.llm_engine._config.load_setting")
def test_translate_custom_text_http_400(
    mock_load: MagicMock,
    mock_build_client: MagicMock,
) -> None:
    """Maps HTTP 400 (non-vision body) to INVALID_REQUEST.

    The chat path retries through 4 payload variants; each one returns 400, so
    the dispatcher then probes /responses, which also returns 400, and finally
    raises INVALID_REQUEST.
    """
    mock_load.side_effect = _mock_load_setting()
    client = _make_sdk_client(chat_error=_sdk_http_error(400, "bad request"))
    client.responses.create.side_effect = _sdk_http_error(400, "bad request")
    mock_build_client.return_value = client
    with pytest.raises(ValueError, match="INVALID_REQUEST"):
        translate_text(["Hello"], "French")


@patch("src.core.llm_engine._build_openai_client")
@patch("src.core.llm_engine._config.load_setting")
def test_translate_custom_text_http_403(
    mock_load: MagicMock,
    mock_build_client: MagicMock,
) -> None:
    """Maps HTTP 403 to AUTH_ERROR."""
    mock_load.side_effect = _mock_load_setting()
    mock_build_client.return_value = _make_sdk_client(chat_error=_sdk_http_error(403))
    with pytest.raises(ValueError, match="AUTH_ERROR"):
        translate_text(["Hello"], "French")


@patch("src.core.llm_engine.time.sleep")
@patch("src.core.llm_engine._build_openai_client")
@patch("src.core.llm_engine._config.load_setting")
def test_translate_custom_text_http_502(
    mock_load: MagicMock,
    mock_build_client: MagicMock,
    _mock_sleep: MagicMock,
) -> None:
    """Maps HTTP 502 to SERVICE_UNAVAILABLE_ERROR."""
    mock_load.side_effect = _mock_load_setting()
    mock_build_client.return_value = _make_sdk_client(chat_error=_sdk_http_error(502))
    with pytest.raises(ValueError, match="SERVICE_UNAVAILABLE_ERROR"):
        translate_text(["Hello"], "French")


@patch("src.core.llm_engine.time.sleep")
@patch("src.core.llm_engine._build_openai_client")
@patch("src.core.llm_engine._config.load_setting")
def test_translate_custom_text_http_503(
    mock_load: MagicMock,
    mock_build_client: MagicMock,
    _mock_sleep: MagicMock,
) -> None:
    """Maps HTTP 503 to SERVICE_UNAVAILABLE_ERROR."""
    mock_load.side_effect = _mock_load_setting()
    mock_build_client.return_value = _make_sdk_client(chat_error=_sdk_http_error(503))
    with pytest.raises(ValueError, match="SERVICE_UNAVAILABLE_ERROR"):
        translate_text(["Hello"], "French")


@patch("src.core.llm_engine.time.sleep")
@patch("src.core.llm_engine._build_openai_client")
@patch("src.core.llm_engine._config.load_setting")
def test_translate_custom_text_http_504(
    mock_load: MagicMock,
    mock_build_client: MagicMock,
    _mock_sleep: MagicMock,
) -> None:
    """Maps HTTP 504 to TIMEOUT_ERROR."""
    mock_load.side_effect = _mock_load_setting()
    mock_build_client.return_value = _make_sdk_client(chat_error=_sdk_http_error(504))
    with pytest.raises(ValueError, match="TIMEOUT_ERROR"):
        translate_text(["Hello"], "French")
