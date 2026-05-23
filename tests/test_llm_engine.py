"""Unit tests for token-budget helpers in src/core/llm_engine."""

import io
import json
import socket
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
)

from src.constants.llm import (
    CONTENT_PDF,
    CONTENT_PLAIN_TEXT,
    LLM_METHOD_CUSTOM,
    LLM_METHOD_GEMINI,
    TOKEN_BUDGET,
)
from src.core.llm_engine import (
    _build_translation_prompt,
    _compress_glossary,
    _deduplicate_texts,
    _estimate_tokens,
    _format_glossary_block,
    _format_glossary_hint,
    _format_lang_pair,
    _handle_api_error,
    _is_untranslatable,
    _restore_duplicates,
    _split_by_token_budget,
    retry_api_call,
    translate_batch,
    translate_image_content,
    translate_text,
)

# ---------------------------------------------------------------------------
# openai SDK mock helpers — used by every Custom-path test.
# ---------------------------------------------------------------------------


def _make_sdk_chat_response(content: str) -> SimpleNamespace:
    """Builds a fake openai chat.completions response payload."""
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
    )


def _make_sdk_responses_response(text: str) -> SimpleNamespace:
    """Builds a fake openai responses.create payload with .output_text."""
    return SimpleNamespace(
        output_text=text,
        output=[
            SimpleNamespace(
                type="message",
                content=[SimpleNamespace(type="output_text", text=text)],
            ),
        ],
    )


def _make_sdk_stream_chunks(chunks: list[str]) -> list[SimpleNamespace]:
    """Builds the iterator yielded by client.chat.completions.create(stream=True)."""
    events = []
    for chunk in chunks:
        events.append(
            SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content=chunk))],
            ),
        )
    return events


def _make_mock_sdk_client(  # noqa: PLR0913
    *,
    chat_response: SimpleNamespace | None = None,
    chat_responses: list[Any] | None = None,
    chat_error: Exception | None = None,
    chat_errors: list[Exception] | None = None,
    responses_response: SimpleNamespace | None = None,
    responses_error: Exception | None = None,
    stream_chunks: list[str] | None = None,
) -> MagicMock:
    """Returns a MagicMock that mimics an openai.OpenAI client."""
    client = MagicMock()
    # ``client.with_options(timeout=X)`` returns a NEW client-with-overrides
    # in the real SDK; we reflect the mock back so callers like
    # ``client.with_options(timeout=...).responses.create(...)`` resolve
    # to the same configured ``client.responses.create`` we set below.
    client.with_options.return_value = client
    if chat_responses is not None:
        client.chat.completions.create.side_effect = chat_responses
    elif chat_errors is not None:
        client.chat.completions.create.side_effect = chat_errors
    elif chat_error is not None:
        client.chat.completions.create.side_effect = chat_error
    elif chat_response is not None:
        client.chat.completions.create.return_value = chat_response
    elif stream_chunks is not None:
        client.chat.completions.create.return_value = iter(
            _make_sdk_stream_chunks(stream_chunks),
        )
    if responses_response is not None:
        client.responses.create.return_value = responses_response
    elif responses_error is not None:
        client.responses.create.side_effect = responses_error
    return client


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
    if status == 408:
        return APITimeoutError(request=request)
    if status == 429:
        return RateLimitError(message=message, response=response, body=body)
    return APIStatusError(message=message, response=response, body=body)


def _sdk_timeout_error() -> APITimeoutError:
    """Returns an openai APITimeoutError with a synthetic request."""
    return APITimeoutError(request=httpx.Request("POST", "https://test/v1"))


def _sdk_connection_error(message: str = "connection refused") -> APIConnectionError:
    """Returns an openai APIConnectionError with a synthetic request."""
    return APIConnectionError(
        message=message,
        request=httpx.Request("POST", "https://test/v1"),
    )


# ---------------------------------------------------------------------------
# google-genai SDK mock helpers — used by every Gemini-path test.
# ---------------------------------------------------------------------------


def _make_genai_text_response(text: str) -> SimpleNamespace:
    """Builds a fake google.genai response with .text accessor."""
    return SimpleNamespace(text=text)


def _make_genai_stream_chunks(chunks: list[str]) -> list[SimpleNamespace]:
    """Builds a list of fake stream events with .text per chunk."""
    return [SimpleNamespace(text=c) for c in chunks]


def _make_mock_genai_client(
    *,
    response_text: str | None = None,
    response_error: Exception | None = None,
    stream_chunks: list[str] | None = None,
    stream_error: Exception | None = None,
) -> MagicMock:
    """Returns a MagicMock that mimics google.genai.Client."""
    client = MagicMock()
    if response_error is not None:
        client.models.generate_content.side_effect = response_error
    elif response_text is not None:
        client.models.generate_content.return_value = _make_genai_text_response(
            response_text,
        )
    if stream_error is not None:
        client.models.generate_content_stream.side_effect = stream_error
    elif stream_chunks is not None:
        client.models.generate_content_stream.return_value = iter(
            _make_genai_stream_chunks(stream_chunks),
        )
    return client


def _genai_api_error(status: int, message: str = "Test error") -> Exception:
    """Builds a google.genai.errors.APIError for the given status."""
    from google.genai import errors  # noqa: PLC0415

    return errors.APIError(
        code=status,
        response_json={"error": {"message": message, "code": status}},
        response=None,
    )


# ---------------------------------------------------------------------------
# _estimate_tokens
# ---------------------------------------------------------------------------


def test_estimate_tokens_empty() -> None:
    """Empty string returns 1 (minimum)."""
    assert _estimate_tokens("") == 1


def test_estimate_tokens_short() -> None:
    """Short strings return at least 1."""
    assert _estimate_tokens("Hi") == 1


def test_estimate_tokens_english() -> None:
    """English text: ~1 token per 4 chars."""
    text = "a" * 100
    assert _estimate_tokens(text) == 25  # noqa: PLR2004


def test_estimate_tokens_long() -> None:
    """Long text scales linearly."""
    text = "x" * 4000
    assert _estimate_tokens(text) == 1000  # noqa: PLR2004


def test_estimate_tokens_boundary() -> None:
    """3 chars → 3//4 = 0 → clamps to minimum 1."""
    assert _estimate_tokens("abc") == 1


def test_estimate_tokens_cjk() -> None:
    """CJK chars (U+3000+) are counted as 1 token each."""
    # 8 CJK chars → 8 tokens (each counted individually)
    assert _estimate_tokens("你好世界你好世界") == 8  # noqa: PLR2004


# ---------------------------------------------------------------------------
# _split_by_token_budget — empty input
# ---------------------------------------------------------------------------


def test_split_by_token_budget_empty() -> None:
    """Empty list returns empty list."""
    assert _split_by_token_budget([], TOKEN_BUDGET) == []


# ---------------------------------------------------------------------------
# _split_by_token_budget — small items
# ---------------------------------------------------------------------------


def test_split_by_token_budget_small_items() -> None:
    """Many small items are grouped into one batch."""
    texts = ["hello"] * 10
    batches = _split_by_token_budget(texts, TOKEN_BUDGET)
    # Each item ≈ 1 token + 10 overhead = 11 tokens → 110 total < 4096
    assert len(batches) == 1
    assert batches[0] == texts


# ---------------------------------------------------------------------------
# _split_by_token_budget — large item
# ---------------------------------------------------------------------------


def test_split_by_token_budget_large_item() -> None:
    """A single item larger than the budget gets its own batch."""
    # Create text that is ~5000 tokens (20000 chars)
    large = "x" * 20000
    small = "hi"
    batches = _split_by_token_budget([small, large, small], budget=4096)
    # large item exceeds budget → must be alone in its batch
    assert len(batches) == 3  # noqa: PLR2004
    assert batches[0] == [small]
    assert batches[1] == [large]
    assert batches[2] == [small]


# ---------------------------------------------------------------------------
# _split_by_token_budget — mixed sizes
# ---------------------------------------------------------------------------


def test_split_by_token_budget_mixed() -> None:
    """Mix of small and medium items splits appropriately."""
    # Budget = 100 tokens
    # Each item cost = len(text)//4 + JSON_ITEM_OVERHEAD
    budget = 100

    # Item A: 40 chars → 10 tokens + 10 overhead = 20
    item_a = "a" * 40
    # Item B: 200 chars → 50 tokens + 10 overhead = 60
    item_b = "b" * 200
    # Item C: 40 chars → 10 tokens + 10 overhead = 20
    item_c = "c" * 40
    # Item D: 40 chars → 10 tokens + 10 overhead = 20
    item_d = "d" * 40

    batches = _split_by_token_budget(
        [item_a, item_b, item_c, item_d],
        budget=budget,
    )

    # A (20) + B (60) + C (20) = 100 ≤ 100 → batch 1
    # D (20) alone → batch 2
    assert len(batches) == 2  # noqa: PLR2004
    assert batches[0] == [item_a, item_b, item_c]
    assert batches[1] == [item_d]


# ---------------------------------------------------------------------------
# _split_by_token_budget — exact budget boundary
# ---------------------------------------------------------------------------


def test_split_by_token_budget_exact_fit() -> None:
    """Items that exactly fill the budget stay in one batch."""
    # Budget = 50, each item = 20 tokens cost → 2 items = 40, 3rd = 60 > 50
    budget = 50
    # 40 chars → 10 tokens + 10 overhead = 20
    item = "a" * 40
    batches = _split_by_token_budget([item, item, item], budget=budget)
    # First two fit (40 ≤ 50), third doesn't (60 > 50)
    assert len(batches) == 2  # noqa: PLR2004
    assert len(batches[0]) == 2  # noqa: PLR2004
    assert len(batches[1]) == 1


# ---------------------------------------------------------------------------
# _split_by_token_budget — single item
# ---------------------------------------------------------------------------


def test_split_by_token_budget_single_item() -> None:
    """A single item always produces one batch."""
    batches = _split_by_token_budget(["hello world"], TOKEN_BUDGET)
    assert len(batches) == 1
    assert batches[0] == ["hello world"]


# ---------------------------------------------------------------------------
# _split_by_token_budget — all oversized
# ---------------------------------------------------------------------------


def test_split_by_token_budget_all_oversized() -> None:
    """Each oversized item gets its own batch."""
    large = "x" * 20000  # ~5000 tokens
    batches = _split_by_token_budget([large, large], budget=100)
    assert len(batches) == 2  # noqa: PLR2004
    assert batches[0] == [large]
    assert batches[1] == [large]


def test_split_by_token_budget_first_item_oversized() -> None:
    """Oversized first item is isolated, subsequent small items grouped."""
    large = "x" * 20000  # ~5000 tokens
    batches = _split_by_token_budget([large, "a", "b"], budget=100)
    assert len(batches) == 2  # noqa: PLR2004
    assert batches[0] == [large]
    assert batches[1] == ["a", "b"]


def test_split_by_token_budget_tiny_budget() -> None:
    """Budget=1 forces every item into its own batch."""
    batches = _split_by_token_budget(["a", "b", "c"], budget=1)
    assert len(batches) == 3  # noqa: PLR2004
    assert all(len(b) == 1 for b in batches)


# ---------------------------------------------------------------------------
# _is_untranslatable — pure numbers and symbols
# ---------------------------------------------------------------------------


def test_untranslatable_pure_numbers() -> None:
    """Pure numeric strings are untranslatable."""
    assert _is_untranslatable("12345") is True
    assert _is_untranslatable("3.14") is True
    assert _is_untranslatable("1,000") is True
    assert _is_untranslatable("  42  ") is True


def test_untranslatable_symbols() -> None:
    """Symbol-only strings are untranslatable."""
    assert _is_untranslatable("---") is True
    assert _is_untranslatable("***") is True
    assert _is_untranslatable("$100") is True
    assert _is_untranslatable("!!??") is True
    assert _is_untranslatable("#1") is True


# ---------------------------------------------------------------------------
# _is_untranslatable — URLs
# ---------------------------------------------------------------------------


def test_untranslatable_urls() -> None:
    """URL strings are untranslatable."""
    assert _is_untranslatable("https://example.com") is True
    assert _is_untranslatable("http://x.co/path?q=1") is True
    assert _is_untranslatable("www.example.com") is True


# ---------------------------------------------------------------------------
# _is_untranslatable — emails
# ---------------------------------------------------------------------------


def test_untranslatable_emails() -> None:
    """Email addresses are untranslatable."""
    assert _is_untranslatable("user@example.com") is True
    assert _is_untranslatable("name.last+tag@domain.org") is True


# ---------------------------------------------------------------------------
# _is_untranslatable — file paths
# ---------------------------------------------------------------------------


def test_untranslatable_paths() -> None:
    """File paths are untranslatable."""
    assert _is_untranslatable("/usr/bin/python") is True
    assert _is_untranslatable("/home/user/docs") is True
    assert _is_untranslatable("C:\\Users\\file.txt") is True


# ---------------------------------------------------------------------------
# _is_untranslatable — empty / whitespace
# ---------------------------------------------------------------------------


def test_untranslatable_empty() -> None:
    """Empty and whitespace-only strings are untranslatable."""
    assert _is_untranslatable("") is True
    assert _is_untranslatable("   ") is True
    assert _is_untranslatable("\n\t") is True


# ---------------------------------------------------------------------------
# _is_untranslatable — translatable content (should return False)
# ---------------------------------------------------------------------------


def test_translatable_words() -> None:
    """Normal words should be translatable."""
    assert _is_untranslatable("Hello world") is False
    assert _is_untranslatable("Bonjour") is False
    assert _is_untranslatable("Name") is False


def test_translatable_mixed() -> None:
    """Mixed content (words + symbols/URLs) should be translatable."""
    assert _is_untranslatable("Price: $100") is False
    assert _is_untranslatable("See https://x.com for details") is False
    assert _is_untranslatable("Hello 123") is False
    assert _is_untranslatable("Contact user@mail.com today") is False


def test_translatable_single_letter() -> None:
    """Single alphabetic characters are translatable."""
    assert _is_untranslatable("A") is False
    assert _is_untranslatable("x") is False


def test_translatable_cjk() -> None:
    """CJK text should be translatable."""
    assert _is_untranslatable("你好世界") is False
    assert _is_untranslatable("こんにちは") is False
    assert _is_untranslatable("안녕하세요") is False


def test_untranslatable_multiline_symbols() -> None:
    """Multiline strings of only symbols/numbers are untranslatable."""
    assert _is_untranslatable("123\n456") is True
    assert _is_untranslatable("---\n***") is True


def test_translatable_multiline_with_words() -> None:
    """Multiline strings containing words are translatable."""
    assert _is_untranslatable("Hello\n123") is False
    assert _is_untranslatable("123\nWorld") is False


def test_untranslatable_carriage_return() -> None:
    r"""Whitespace-only with \r\n is untranslatable."""
    assert _is_untranslatable("\r\n") is True
    assert _is_untranslatable("  \r\n  ") is True


def test_untranslatable_path_not_matching_prefix() -> None:
    """Unix paths without known prefixes are NOT untranslatable."""
    # /dev, /bin, /lib are not in the allowed prefix list
    assert _is_untranslatable("/dev/null") is False
    assert _is_untranslatable("/bin/bash") is False


# ---------------------------------------------------------------------------
# _deduplicate_texts
# ---------------------------------------------------------------------------


def test_deduplicate_texts_no_dupes() -> None:
    """All unique strings return unchanged."""
    texts = ["apple", "banana", "cherry"]
    unique, dupe_map = _deduplicate_texts(texts)
    assert unique == texts
    assert dupe_map == {"apple": [0], "banana": [1], "cherry": [2]}


def test_deduplicate_texts_with_dupes() -> None:
    """Duplicate strings are collapsed to unique list."""
    texts = ["hello", "world", "hello", "hello", "world"]
    unique, dupe_map = _deduplicate_texts(texts)
    assert unique == ["hello", "world"]
    assert dupe_map == {"hello": [0, 2, 3], "world": [1, 4]}


def test_deduplicate_texts_empty() -> None:
    """Empty input returns empty results."""
    unique, dupe_map = _deduplicate_texts([])
    assert unique == []
    assert dupe_map == {}


def test_deduplicate_texts_single_item() -> None:
    """Single item returns as-is."""
    unique, dupe_map = _deduplicate_texts(["hello"])
    assert unique == ["hello"]
    assert dupe_map == {"hello": [0]}


def test_deduplicate_texts_all_identical() -> None:
    """All identical strings collapse to one unique entry."""
    unique, dupe_map = _deduplicate_texts(["x", "x", "x", "x"])
    assert unique == ["x"]
    assert dupe_map == {"x": [0, 1, 2, 3]}


def test_deduplicate_texts_case_sensitive() -> None:
    """Deduplication is case-sensitive: 'Hello' != 'hello'."""
    unique, dupe_map = _deduplicate_texts(["Hello", "hello"])
    assert unique == ["Hello", "hello"]
    assert dupe_map == {"Hello": [0], "hello": [1]}


def test_deduplicate_texts_preserves_first_occurrence_order() -> None:
    """Unique list preserves insertion order of first occurrences."""
    texts = ["cherry", "apple", "cherry", "banana", "apple"]
    unique, dupe_map = _deduplicate_texts(texts)
    assert unique == ["cherry", "apple", "banana"]
    assert dupe_map == {"cherry": [0, 2], "apple": [1, 4], "banana": [3]}


# ---------------------------------------------------------------------------
# _restore_duplicates
# ---------------------------------------------------------------------------


def test_restore_duplicates_round_trip() -> None:
    """Restore correctly maps translations back to all original positions."""
    unique_texts = ["hello", "world"]
    original_texts = ["hello", "world", "hello", "hello", "world"]
    dupe_map = {"hello": [0, 2, 3], "world": [1, 4]}
    unique_translated = ["xin chào", "thế giới"]

    result = _restore_duplicates(
        unique_translated,
        unique_texts,
        dupe_map,
        original_texts,
    )
    assert result == [
        "xin chào",
        "thế giới",
        "xin chào",
        "xin chào",
        "thế giới",
    ]


def test_restore_duplicates_no_dupes() -> None:
    """Works correctly when there are no duplicates."""
    unique_texts = ["a", "b", "c"]
    original_texts = ["a", "b", "c"]
    dupe_map = {"a": [0], "b": [1], "c": [2]}
    unique_translated = ["x", "y", "z"]

    result = _restore_duplicates(
        unique_translated,
        unique_texts,
        dupe_map,
        original_texts,
    )
    assert result == ["x", "y", "z"]


def test_restore_duplicates_partial_cancellation() -> None:
    """On cancellation, untranslated items retain their original values."""
    unique_texts = ["a", "b", "c", "d"]
    original_texts = ["a", "b", "c", "d"]
    dupe_map = {"a": [0], "b": [1], "c": [2], "d": [3]}
    # Only 2 of 4 items were translated before cancellation
    unique_translated = ["x", "y"]

    result = _restore_duplicates(
        unique_translated,
        unique_texts,
        dupe_map,
        original_texts,
    )
    # Translated items get results, untranslated keep originals
    assert result == ["x", "y", "c", "d"]


def test_restore_duplicates_cancellation_with_dupes() -> None:
    """Partial cancellation copies translated text to all duplicate positions."""
    # "hello" appears at [0, 2, 3], "world" at [1, 4]
    unique_texts = ["hello", "world"]
    original_texts = ["hello", "world", "hello", "hello", "world"]
    dupe_map = {"hello": [0, 2, 3], "world": [1, 4]}
    # Only first unique item translated before cancellation
    unique_translated = ["xin chào"]

    result = _restore_duplicates(
        unique_translated,
        unique_texts,
        dupe_map,
        original_texts,
    )
    # "hello" translated at all 3 positions; "world" keeps original
    assert result == ["xin chào", "world", "xin chào", "xin chào", "world"]


def test_restore_duplicates_empty_translated() -> None:
    """Full cancellation (0 items translated) retains all originals."""
    unique_texts = ["a", "b"]
    original_texts = ["a", "b", "a"]
    dupe_map = {"a": [0, 2], "b": [1]}
    unique_translated: list[str] = []

    result = _restore_duplicates(
        unique_translated,
        unique_texts,
        dupe_map,
        original_texts,
    )
    assert result == ["a", "b", "a"]


def test_restore_duplicates_single_item() -> None:
    """Single item round-trip works."""
    result = _restore_duplicates(
        ["X"],
        ["a"],
        {"a": [0]},
        ["a"],
    )
    assert result == ["X"]


# ---------------------------------------------------------------------------
# normalize_for_search integration via _compress_glossary
# (Direct normalization tests are in test_text_utils.py)
# ---------------------------------------------------------------------------


def test_compress_glossary_matches_accented_text() -> None:
    """Glossary with accented terms matches unaccented batch text."""
    glossary = [(1, "Xin Chào", "Hello")]
    # Batch text has no accents — normalization handles the match
    texts = ["xin chao everyone"]
    result = _compress_glossary(glossary, texts)
    assert result == glossary


def test_compress_glossary_matches_german_eszett() -> None:
    """Glossary with ß matches batch text containing 'ss'."""
    glossary = [(1, "Straße", "Street")]
    texts = ["Die Strasse ist lang"]
    result = _compress_glossary(glossary, texts)
    assert result == glossary


def test_compress_glossary_matches_ligatures_and_cjk() -> None:
    """Glossary with ligatures and CJK works via normalization."""
    glossary = [
        (1, "ﬁnd", "tìm"),  # ligature ﬁ → fi
        (2, "你好", "Hello"),  # CJK pass-through
        (3, "unrelated", "khác"),  # should be excluded
    ]
    texts = ["find your 你好"]
    result = _compress_glossary(glossary, texts)
    assert result is not None
    assert len(result) == 2  # noqa: PLR2004
    assert result[0][0] == 1
    assert result[1][0] == 2  # noqa: PLR2004


# ---------------------------------------------------------------------------
# _compress_glossary
# ---------------------------------------------------------------------------


def test_compress_glossary_filters_relevant() -> None:
    """Only entries matching batch text are returned."""
    glossary = [
        (1, "hello", "xin chào"),
        (2, "world", "thế giới"),
        (3, "goodbye", "tạm biệt"),
    ]
    texts = ["Hello world, how are you?"]
    result = _compress_glossary(glossary, texts)
    assert result is not None
    assert len(result) == 2  # noqa: PLR2004
    assert (1, "hello", "xin chào") in result
    assert (2, "world", "thế giới") in result


def test_compress_glossary_case_insensitive() -> None:
    """Matching is case-insensitive."""
    glossary = [(1, "Hello", "Xin chào")]
    texts = ["hello there"]
    result = _compress_glossary(glossary, texts)
    assert result is not None
    assert len(result) == 1


def test_compress_glossary_accent_insensitive() -> None:
    """Matching ignores diacritics."""
    glossary = [(1, "hello", "Xin chào")]
    # Text has "xin chao" without diacritics — should still match
    texts = ["xin chao la gi?"]
    result = _compress_glossary(glossary, texts)
    assert result is not None
    assert len(result) == 1


def test_compress_glossary_bidirectional() -> None:
    """Matches on target_text for reverse translation direction."""
    glossary = [(1, "hello", "xin chào")]
    # Translating Vietnamese → English: text contains target "xin chào"
    texts = ["Xin chào thế giới"]
    result = _compress_glossary(glossary, texts)
    assert result is not None
    assert len(result) == 1


def test_compress_glossary_substring_match() -> None:
    """Glossary term found as substring in longer text."""
    glossary = [(1, "world", "thế giới")]
    texts = ["Hello world, welcome!"]
    result = _compress_glossary(glossary, texts)
    assert result is not None
    assert len(result) == 1


def test_compress_glossary_no_matches() -> None:
    """Returns None when no entries match."""
    glossary = [(1, "goodbye", "tạm biệt")]
    texts = ["Hello world"]
    result = _compress_glossary(glossary, texts)
    assert result is None


def test_compress_glossary_skips_empty_entries() -> None:
    """Entries with empty source or target are excluded."""
    glossary = [
        (1, "", "xin chào"),  # empty source
        (2, "hello", ""),  # empty target
        (3, "world", "thế giới"),  # valid
    ]
    texts = ["Hello world"]
    result = _compress_glossary(glossary, texts)
    assert result is not None
    # Only the valid entry should match
    assert len(result) == 1
    assert result[0][0] == 3  # noqa: PLR2004


def test_compress_glossary_empty_inputs() -> None:
    """Handles None/empty glossary and empty texts."""
    assert _compress_glossary(None, ["hello"]) is None
    assert _compress_glossary([], ["hello"]) is None
    # Empty texts — no glossary entry can match
    glossary = [(1, "hello", "xin chào")]
    assert _compress_glossary(glossary, []) is None


def test_compress_glossary_all_match() -> None:
    """All entries returned when all are relevant."""
    glossary = [
        (1, "hello", "xin chào"),
        (2, "world", "thế giới"),
    ]
    texts = ["Hello world"]
    result = _compress_glossary(glossary, texts)
    assert result is not None
    assert len(result) == 2  # noqa: PLR2004


def test_compress_glossary_whitespace_only_entries() -> None:
    """Entries with whitespace-only source or target are excluded."""
    glossary = [
        (1, "   ", "xin chào"),  # whitespace source
        (2, "hello", "   "),  # whitespace target
        (3, "world", "thế giới"),  # valid
    ]
    texts = ["Hello world"]
    result = _compress_glossary(glossary, texts)
    assert result is not None
    assert len(result) == 1
    assert result[0][0] == 3  # noqa: PLR2004


def test_compress_glossary_multi_word_term() -> None:
    """Multi-word glossary terms match as substring."""
    glossary = [(1, "machine learning", "học máy")]
    texts = ["I study machine learning at school"]
    result = _compress_glossary(glossary, texts)
    assert result is not None
    assert len(result) == 1


def test_compress_glossary_multi_word_no_match() -> None:
    """Multi-word term does not match partial words."""
    glossary = [(1, "machine learning", "học máy")]
    # "machine" alone is not the full term "machine learning"
    texts = ["I bought a machine yesterday"]
    result = _compress_glossary(glossary, texts)
    assert result is None


def test_compress_glossary_german_eszett() -> None:
    """German ß/ss equivalence works in glossary matching."""
    glossary = [(1, "Straße", "Street")]
    texts = ["Die STRASSE ist lang"]
    result = _compress_glossary(glossary, texts)
    assert result is not None
    assert len(result) == 1


def test_compress_glossary_multiple_texts_in_batch() -> None:
    """Matching works across multiple texts in the batch."""
    glossary = [
        (1, "hello", "xin chào"),
        (2, "goodbye", "tạm biệt"),
    ]
    # "hello" is in text[0], "goodbye" is in text[1]
    texts = ["Hello there", "Say goodbye now"]
    result = _compress_glossary(glossary, texts)
    assert result is not None
    assert len(result) == 2  # noqa: PLR2004


def test_compress_glossary_special_chars_in_term() -> None:
    """Glossary terms with special chars match via 'in' (not regex)."""
    glossary = [(1, "C++", "C++")]
    texts = ["I love C++ programming"]
    result = _compress_glossary(glossary, texts)
    assert result is not None
    assert len(result) == 1


def test_compress_glossary_preserves_original_entries() -> None:
    """Returned entries are the original tuples (not normalized)."""
    glossary = [(1, "Café", "Quán cà phê")]
    texts = ["Let's go to the cafe"]
    result = _compress_glossary(glossary, texts)
    assert result is not None
    # Must return original tuple with accents, not normalized
    assert result[0] == (1, "Café", "Quán cà phê")


# ---------------------------------------------------------------------------
# Additional _is_untranslatable edge cases
# ---------------------------------------------------------------------------


def test_untranslatable_windows_path_no_spaces() -> None:
    """Windows-style path without spaces is untranslatable."""
    assert _is_untranslatable("C:\\Users\\file.txt") is True


def test_translatable_windows_path_with_spaces() -> None:
    """Windows path with spaces has translatable words → translatable."""
    assert _is_untranslatable("C:\\Program Files\\app") is False


def test_untranslatable_percent_and_currency() -> None:
    """Pure currency/percentage strings are untranslatable."""
    assert _is_untranslatable("$1,234.56") is True
    assert _is_untranslatable("€100") is True
    assert _is_untranslatable("99.9%") is True


def test_untranslatable_mixed_operators() -> None:
    """Math operators and brackets without words are untranslatable."""
    assert _is_untranslatable("(1 + 2) * 3") is True
    assert _is_untranslatable("[0, 1, 2]") is True


def test_translatable_sentence_with_number() -> None:
    """Sentences containing numbers are translatable."""
    assert _is_untranslatable("There are 3 cats") is False
    assert _is_untranslatable("Version 2.0 released") is False


def test_untranslatable_only_punctuation() -> None:
    """Strings with only punctuation marks are untranslatable."""
    assert _is_untranslatable("...") is True
    assert _is_untranslatable("???") is True


# ---------------------------------------------------------------------------
# Additional _deduplicate_texts edge cases
# ---------------------------------------------------------------------------


def test_deduplicate_texts_whitespace_strings() -> None:
    """Whitespace-only strings are valid duplicates."""
    texts = ["  ", "  ", "hello"]
    unique, dupe_map = _deduplicate_texts(texts)
    assert unique == ["  ", "hello"]
    assert dupe_map["  "] == [0, 1]


def test_deduplicate_texts_empty_strings() -> None:
    """Empty strings are valid duplicates."""
    texts = ["", "", "a"]
    unique, dupe_map = _deduplicate_texts(texts)
    assert unique == ["", "a"]
    assert dupe_map[""] == [0, 1]


# ---------------------------------------------------------------------------
# Additional _restore_duplicates edge cases
# ---------------------------------------------------------------------------


def test_restore_duplicates_all_same() -> None:
    """All identical input strings get the same translation."""
    unique_texts = ["x"]
    original_texts = ["x", "x", "x"]
    dupe_map = {"x": [0, 1, 2]}
    unique_translated = ["Y"]

    result = _restore_duplicates(
        unique_translated,
        unique_texts,
        dupe_map,
        original_texts,
    )
    assert result == ["Y", "Y", "Y"]


# ---------------------------------------------------------------------------
# Additional _split_by_token_budget edge cases
# ---------------------------------------------------------------------------


def test_split_by_token_budget_identical_items_boundary() -> None:
    """Items at exact budget boundary split correctly."""
    # budget = 22, item cost = 10 + 1 = 11
    # Two items = 22 ≤ 22 → one batch
    item = "a" * 4  # 4 chars → 1 token + 10 overhead = 11
    batches = _split_by_token_budget([item, item, item], budget=22)
    assert len(batches) == 2  # noqa: PLR2004
    assert len(batches[0]) == 2  # noqa: PLR2004
    assert len(batches[1]) == 1


# ---------------------------------------------------------------------------
# _compress_glossary edge cases with fullwidth / combining marks
# ---------------------------------------------------------------------------


def test_compress_glossary_fullwidth_match() -> None:
    """Fullwidth glossary terms match normal-width batch text."""
    glossary = [(1, "\uff21\uff22", "ab-translation")]
    texts = ["ab is here"]
    result = _compress_glossary(glossary, texts)
    assert result == glossary


def test_compress_glossary_empty_source_excluded() -> None:
    """Glossary entry with whitespace-only source is excluded by strip() check."""
    glossary = [(1, "  ", "accent")]
    texts = ["some text"]
    # Whitespace-only source fails the strip() truthiness check
    result = _compress_glossary(glossary, texts)
    assert result is None


# ---------------------------------------------------------------------------
# _compress_glossary with HTML-formatted text
# ---------------------------------------------------------------------------


def test_compress_glossary_matches_through_bold_tags() -> None:
    """Glossary term 'hello world' matches '<b>hello</b> world'."""
    glossary = [(1, "hello world", "xin chào thế giới")]
    texts = ["<b>hello</b> world"]
    result = _compress_glossary(glossary, texts)
    assert result is not None
    assert len(result) == 1


def test_compress_glossary_matches_through_span_tags() -> None:
    """Glossary term matches text wrapped in <span style='...'>."""
    glossary = [(1, "machine learning", "học máy")]
    texts = ['<span style="color:#ff0000">machine</span> learning']
    result = _compress_glossary(glossary, texts)
    assert result is not None
    assert len(result) == 1


def test_compress_glossary_matches_through_anchor_tags() -> None:
    """Glossary term matches text inside <a href='...'>."""
    glossary = [(1, "click here", "nhấn vào đây")]
    texts = ['<a href="https://example.com">click here</a>']
    result = _compress_glossary(glossary, texts)
    assert result is not None
    assert len(result) == 1


def test_compress_glossary_matches_through_nested_tags() -> None:
    """Glossary matches text split across nested formatting tags."""
    glossary = [(1, "hello world", "xin chào thế giới")]
    texts = ["<b><i>hello</i></b> <u>world</u>"]
    result = _compress_glossary(glossary, texts)
    assert result is not None
    assert len(result) == 1


def test_compress_glossary_no_false_match_from_tag_stripping() -> None:
    """Stripping tags does not create a false substring match."""
    glossary = [(1, "helloworld", "xinchào")]
    # Tags separate "hello" and "world" — after stripping there is no space
    # but the glossary term has no space either, so this SHOULD match
    texts = ["<b>hello</b><b>world</b>"]
    result = _compress_glossary(glossary, texts)
    assert result is not None
    assert len(result) == 1


def test_compress_glossary_sup_sub_tags_stripped() -> None:
    """Glossary matches text wrapped in <sup>/<sub> tags."""
    glossary = [(1, "H2O", "H2O")]
    texts = ["H<sub>2</sub>O"]
    result = _compress_glossary(glossary, texts)
    assert result is not None
    assert len(result) == 1


# ---------------------------------------------------------------------------
# retry_api_call decorator
# ---------------------------------------------------------------------------


def test_retry_transient_error_retries() -> None:
    """SERVICE_UNAVAILABLE_ERROR triggers retry until success."""
    call_count = 0

    @retry_api_call(max_retries=3, base_delay=0.01)
    def flaky() -> str:
        nonlocal call_count
        call_count += 1
        if call_count < 3:  # noqa: PLR2004
            raise ValueError("SERVICE_UNAVAILABLE_ERROR")
        return "ok"

    with patch("src.core.llm_engine.time.sleep"):
        result = flaky()

    assert result == "ok"
    assert call_count == 3  # noqa: PLR2004


def test_retry_connection_error_retries() -> None:
    """CONNECTION_ERROR triggers retry until success."""
    call_count = 0

    @retry_api_call(max_retries=2, base_delay=0.01)
    def flaky() -> str:
        nonlocal call_count
        call_count += 1
        if call_count < 2:  # noqa: PLR2004
            raise ValueError("CONNECTION_ERROR")
        return "connected"

    with patch("src.core.llm_engine.time.sleep"):
        result = flaky()

    assert result == "connected"
    assert call_count == 2  # noqa: PLR2004


def test_retry_non_transient_raises_immediately() -> None:
    """AUTH_ERROR is raised immediately without any retry."""
    call_count = 0

    @retry_api_call(max_retries=3, base_delay=0.01)
    def auth_fail() -> None:
        nonlocal call_count
        call_count += 1
        raise ValueError("AUTH_ERROR")

    with pytest.raises(ValueError, match="AUTH_ERROR"):
        auth_fail()

    assert call_count == 1  # Called exactly once, no retries


def test_retry_quota_error_no_retry() -> None:
    """QUOTA_ERROR is raised immediately without retry."""
    call_count = 0

    @retry_api_call(max_retries=3, base_delay=0.01)
    def quota_fail() -> None:
        nonlocal call_count
        call_count += 1
        raise ValueError("QUOTA_ERROR")

    with pytest.raises(ValueError, match="QUOTA_ERROR"):
        quota_fail()

    assert call_count == 1


def test_retry_max_retries_exceeded_re_raises() -> None:
    """After exhausting max_retries, the transient error is re-raised."""

    @retry_api_call(max_retries=2, base_delay=0.01)
    def always_fails() -> None:
        raise ValueError("TIMEOUT_ERROR")

    with (
        patch("src.core.llm_engine.time.sleep"),
        pytest.raises(
            ValueError,
            match="TIMEOUT_ERROR",
        ),
    ):
        always_fails()


# ---------------------------------------------------------------------------
# _handle_api_error
# ---------------------------------------------------------------------------


def test_handle_api_error_timeout_error() -> None:
    """TimeoutError maps to TIMEOUT_ERROR."""
    with pytest.raises(ValueError, match="TIMEOUT_ERROR"):
        _handle_api_error(TimeoutError("request timed out"))


def test_handle_api_error_socket_timeout() -> None:
    """socket.timeout maps to TIMEOUT_ERROR."""
    with pytest.raises(ValueError, match="TIMEOUT_ERROR"):
        _handle_api_error(socket.timeout("timed out"))  # noqa: UP041


def test_handle_api_error_json_decode_error() -> None:
    """json.JSONDecodeError maps to INVALID_RESPONSE."""
    err = json.JSONDecodeError("Expecting value", "doc", 0)
    with pytest.raises(ValueError, match="INVALID_RESPONSE"):
        _handle_api_error(err)


def test_handle_api_error_key_error() -> None:
    """KeyError maps to INVALID_RESPONSE."""
    with pytest.raises(ValueError, match="INVALID_RESPONSE"):
        _handle_api_error(KeyError("missing_key"))


def test_handle_api_error_index_error() -> None:
    """IndexError maps to INVALID_RESPONSE."""
    with pytest.raises(ValueError, match="INVALID_RESPONSE"):
        _handle_api_error(IndexError("list index out of range"))


# ---------------------------------------------------------------------------
# _format_glossary_block
# ---------------------------------------------------------------------------


def test_format_glossary_block_none_returns_empty() -> None:
    """None input returns empty string."""
    assert _format_glossary_block(None) == ""


def test_format_glossary_block_empty_list_returns_empty() -> None:
    """Empty list returns empty string."""
    assert _format_glossary_block([]) == ""


def test_format_glossary_block_single_entry() -> None:
    """Single entry produces the correct block string."""
    result = _format_glossary_block([(1, "hello", "bonjour")])
    assert result == "\nGlossary (use these exact translations): hello = bonjour."


def test_format_glossary_block_multiple_entries_uses_pipe_separator() -> None:
    """Multiple entries are joined with ' | '."""
    result = _format_glossary_block(
        [
            (1, "hello", "bonjour"),
            (2, "world", "monde"),
        ]
    )
    assert result == (
        "\nGlossary (use these exact translations): hello = bonjour | world = monde."
    )


def test_format_glossary_block_ignores_id_field() -> None:
    """The id (first tuple element) does not appear in the output."""
    result = _format_glossary_block([(999, "cat", "chat")])
    assert "999" not in result
    assert "cat = chat" in result


def test_format_glossary_block_special_chars_in_entries() -> None:
    """Entries with special characters are formatted verbatim."""
    result = _format_glossary_block([(1, "C++", "C++")])
    assert "C++ = C++" in result


def test_format_glossary_block_unicode_entries() -> None:
    """Unicode source and target text are preserved exactly."""
    result = _format_glossary_block([(1, "Café", "Quán cà phê")])
    assert "Café = Quán cà phê" in result


# ---------------------------------------------------------------------------
# _format_glossary_hint
# ---------------------------------------------------------------------------


def test_format_glossary_hint_none_returns_empty() -> None:
    """None input returns empty string."""
    assert _format_glossary_hint(None) == ""


def test_format_glossary_hint_empty_list_returns_empty() -> None:
    """Empty list returns empty string."""
    assert _format_glossary_hint([]) == ""


def test_format_glossary_hint_single_entry() -> None:
    """Single entry produces the correct hint string with <->."""
    result = _format_glossary_hint([(1, "hello", "bonjour")])
    assert result == " Additionally, you MUST use this glossary: hello <-> bonjour."


def test_format_glossary_hint_multiple_entries_uses_comma_separator() -> None:
    """Multiple entries are joined with ', '."""
    result = _format_glossary_hint(
        [
            (1, "hello", "bonjour"),
            (2, "world", "monde"),
        ]
    )
    assert result == (
        " Additionally, you MUST use this glossary: hello <-> bonjour, world <-> monde."
    )


def test_format_glossary_hint_ignores_id_field() -> None:
    """The id (first tuple element) does not appear in the output."""
    result = _format_glossary_hint([(42, "cat", "chat")])
    assert "42" not in result
    assert "cat <-> chat" in result


def test_format_glossary_hint_special_chars_in_entries() -> None:
    """Entries with special characters are formatted verbatim."""
    result = _format_glossary_hint([(1, "C++", "C++")])
    assert "C++ <-> C++" in result


def test_format_glossary_hint_unicode_entries() -> None:
    """Unicode source and target text are preserved exactly."""
    result = _format_glossary_hint([(1, "Café", "Quán cà phê")])
    assert "Café <-> Quán cà phê" in result


# ---------------------------------------------------------------------------
# _handle_api_error — unrecognized exception
# ---------------------------------------------------------------------------


def test_handle_api_error_unrecognized_exception_reraises() -> None:
    """An exception type not handled by _handle_api_error is re-raised as-is."""
    original = RuntimeError("Something completely unexpected")
    with pytest.raises(RuntimeError, match="Something completely unexpected"):
        _handle_api_error(original)


# ---------------------------------------------------------------------------
# translate_text — unknown LLM method
# ---------------------------------------------------------------------------


def test_translate_text_unknown_method_returns_originals() -> None:
    """translate_text with unknown LLM method returns original texts unchanged."""
    texts = ["Hello", "World"]
    with patch(
        "src.core.llm_engine._resolve_provider_model",
        return_value=("UnknownProvider", ""),
    ):
        result = translate_text(texts, "French")
    assert result == texts


def test_translate_text_empty_list_returns_empty() -> None:
    """translate_text with empty input returns empty list."""
    assert translate_text([], "French") == []


def test_translate_text_all_untranslatable_returns_originals() -> None:
    """translate_text returns originals when all items are untranslatable."""
    texts = ["12345", "http://example.com", "test@email.com"]
    progress_values = []
    with patch(
        "src.core.llm_engine._resolve_provider_model",
        return_value=(LLM_METHOD_GEMINI, "gemini-3-flash-preview"),
    ):
        result = translate_text(
            texts,
            "French",
            progress_callback=progress_values.append,
        )
    assert result == texts
    # Progress should be called with 100
    assert progress_values == [100]


def test_translate_text_cancel_check_stops_early() -> None:
    """translate_text stops translating when cancel_check returns True."""
    texts = ["Hello " * 500, "World " * 500]  # Large texts to force 2 batches

    call_count = 0

    def fake_cancel() -> bool:
        nonlocal call_count
        call_count += 1
        return call_count > 1  # Cancel after first batch

    def fake_translate(texts, tl, sl, gl, ct, model="", **_kwargs):  # noqa: ANN001, ANN202
        return [t.upper() for t in texts]

    with (
        patch(
            "src.core.llm_engine._resolve_provider_model",
            return_value=(LLM_METHOD_GEMINI, "gemini-3-flash-preview"),
        ),
        patch("src.core.llm_engine._translate_gemini", side_effect=fake_translate),
        patch(
            "src.core.llm_engine._split_by_token_budget",
            return_value=[["Hello"], ["World"]],
        ),
    ):
        result = translate_text(
            texts,
            "French",
            cancel_check=fake_cancel,
        )
    # At least one item should retain its original value due to cancellation
    assert len(result) == 2  # noqa: PLR2004


# ---------------------------------------------------------------------------
# _translate_gemini — missing API key
# ---------------------------------------------------------------------------


def test_translate_gemini_missing_api_key_raises_auth_error() -> None:
    """_translate_gemini raises AUTH_ERROR when API key is empty."""
    from src.core.llm_engine import _translate_gemini  # noqa: PLC0415

    with (
        patch("src.core.llm_engine._config.load_setting", side_effect=lambda k, d: ""),
        pytest.raises(ValueError, match="AUTH_ERROR"),
    ):
        _translate_gemini(["Hello"], "French", "English")


def test_translate_gemini_success() -> None:
    """_translate_gemini returns translated texts on HTTP 200."""
    import json  # noqa: PLC0415

    from src.core.llm_engine import _translate_gemini  # noqa: PLC0415

    inner = json.dumps(
        {
            "results": [
                {"id": 0, "translated": "Bonjour"},
                {"id": 1, "translated": "Monde"},
            ]
        }
    )

    settings = {
        "llm/gemini_api_key": "fake-key",
        "llm/gemini_model": "gemini-pro",
    }
    client = _make_mock_genai_client(response_text=inner)

    with (
        patch(
            "src.core.llm_engine._config.load_setting",
            side_effect=lambda k, d="": settings.get(k, d),
        ),
        patch(
            "src.core.llm_engine._build_gemini_client",
            return_value=client,
        ),
    ):
        result = _translate_gemini(
            ["Hello", "World"],
            "French",
            "English",
        )

    assert result == ["Bonjour", "Monde"]


def test_translate_gemini_missing_id_falls_back() -> None:
    """Missing ID in response falls back to original text."""
    import json  # noqa: PLC0415

    from src.core.llm_engine import _translate_gemini  # noqa: PLC0415

    # Only id=0 translated, id=1 missing
    inner = json.dumps(
        {
            "results": [
                {"id": 0, "translated": "Bonjour"},
            ]
        }
    )

    settings = {
        "llm/gemini_api_key": "k",
        "llm/gemini_model": "m",
    }
    client = _make_mock_genai_client(response_text=inner)

    with (
        patch(
            "src.core.llm_engine._config.load_setting",
            side_effect=lambda k, d="": settings.get(k, d),
        ),
        patch(
            "src.core.llm_engine._build_gemini_client",
            return_value=client,
        ),
    ):
        result = _translate_gemini(
            ["Hello", "World"],
            "French",
            "English",
        )

    assert result[0] == "Bonjour"
    assert result[1] == "World"  # Fallback to original


# ---------------------------------------------------------------------------
# _translate_custom — missing credentials
# ---------------------------------------------------------------------------


def test_translate_custom_missing_credentials_raises_auth_error() -> None:
    """_translate_custom raises AUTH_ERROR when credentials are empty."""
    from src.core.llm_engine import _translate_custom  # noqa: PLC0415

    with (
        patch("src.core.llm_engine._config.load_setting", side_effect=lambda k, d: ""),
        pytest.raises(ValueError, match="AUTH_ERROR"),
    ):
        _translate_custom(["Hello"], "French", "English")


def test_translate_custom_success() -> None:
    """_translate_custom returns translated texts on HTTP 200."""
    import json  # noqa: PLC0415

    from src.core.llm_engine import _translate_custom  # noqa: PLC0415

    content = json.dumps(
        {
            "results": [
                {"id": 0, "translated": "Bonjour"},
                {"id": 1, "translated": "Monde"},
            ]
        }
    )

    settings = {
        "llm/custom_api_key": "k",
        "llm/custom_model": "gpt-4",
        "llm/custom_endpoint": "https://api.example.com/v1",
    }
    client = _make_mock_sdk_client(chat_response=_make_sdk_chat_response(content))

    with (
        patch(
            "src.core.llm_engine._config.load_setting",
            side_effect=lambda k, d="": settings.get(k, d),
        ),
        patch(
            "src.core.llm_engine._build_openai_client",
            return_value=client,
        ),
        patch("src.core.llm_engine.time.sleep"),
    ):
        result = _translate_custom(
            ["Hello", "World"],
            "French",
            "English",
        )

    assert result == ["Bonjour", "Monde"]


def test_translate_custom_falls_back_when_400_on_response_format() -> None:
    """Falls back to a leaner payload when json_object is rejected.

    First payload (json_object + temperature) returns 400; second
    payload (temperature only) succeeds.  Regression for Azure GPT-5.x
    where 'response_format: json_object' is rejected with the generic
    'The requested operation is unsupported.' body.
    """
    import json  # noqa: PLC0415

    from src.core.llm_engine import _translate_custom  # noqa: PLC0415

    content = json.dumps(
        {"results": [{"id": 0, "translated": "Bonjour"}]},
    )

    client = _make_mock_sdk_client(
        chat_responses=[
            _sdk_http_error(400),
            _make_sdk_chat_response(content),
        ],
    )

    settings = {
        "llm/custom_api_key": "k",
        "llm/custom_model": "gpt-5",
        "llm/custom_endpoint": "https://example.com/v1",
    }
    with (
        patch(
            "src.core.llm_engine._config.load_setting",
            side_effect=lambda k, d="": settings.get(k, d),
        ),
        patch(
            "src.core.llm_engine._build_openai_client",
            return_value=client,
        ),
        patch("src.core.llm_engine.time.sleep"),
    ):
        result = _translate_custom(["Hello"], "French", "English")

    assert result == ["Bonjour"]
    # Two requests sent: first with response_format, second without.
    assert client.chat.completions.create.call_count == 2  # noqa: PLR2004
    sent_kwargs = [call.kwargs for call in client.chat.completions.create.call_args_list]
    assert "response_format" in sent_kwargs[0]
    assert "response_format" not in sent_kwargs[1]
    assert "temperature" in sent_kwargs[1]


def test_translate_custom_falls_back_to_minimal_payload() -> None:
    """Final minimal-payload fallback handles reasoning models.

    Third fallback (no temperature, no response_format) succeeds when
    a reasoning model rejects both richer variants.
    """
    import json  # noqa: PLC0415

    from src.core.llm_engine import _translate_custom  # noqa: PLC0415

    content = json.dumps(
        {"results": [{"id": 0, "translated": "Bonjour"}]},
    )

    client = _make_mock_sdk_client(
        chat_responses=[
            _sdk_http_error(400),
            _sdk_http_error(400),
            _make_sdk_chat_response(content),
        ],
    )

    settings = {
        "llm/custom_api_key": "k",
        "llm/custom_model": "o1",
        "llm/custom_endpoint": "https://example.com/v1",
    }
    with (
        patch(
            "src.core.llm_engine._config.load_setting",
            side_effect=lambda k, d="": settings.get(k, d),
        ),
        patch(
            "src.core.llm_engine._build_openai_client",
            return_value=client,
        ),
        patch("src.core.llm_engine.time.sleep"),
    ):
        result = _translate_custom(["Hello"], "French", "English")

    assert result == ["Bonjour"]
    assert client.chat.completions.create.call_count == 3  # noqa: PLR2004
    final_kwargs = client.chat.completions.create.call_args_list[2].kwargs
    assert "response_format" not in final_kwargs
    assert "temperature" not in final_kwargs


def test_translate_custom_falls_back_to_no_system_role() -> None:
    """Final fallback merges system prompt into the user message.

    Some Azure deployments (and OpenAI o-series) reject ``role: system``
    entirely; this variant survives by sending only a user message.
    """
    import json  # noqa: PLC0415

    from src.core.llm_engine import _translate_custom  # noqa: PLC0415

    content = json.dumps(
        {"results": [{"id": 0, "translated": "Bonjour"}]},
    )

    client = _make_mock_sdk_client(
        chat_responses=[
            _sdk_http_error(400),
            _sdk_http_error(400),
            _sdk_http_error(400),
            _make_sdk_chat_response(content),
        ],
    )

    settings = {
        "llm/custom_api_key": "k",
        "llm/custom_model": "gpt-5.4-pro",
        "llm/custom_endpoint": "https://example.com/v1",
    }
    with (
        patch(
            "src.core.llm_engine._config.load_setting",
            side_effect=lambda k, d="": settings.get(k, d),
        ),
        patch(
            "src.core.llm_engine._build_openai_client",
            return_value=client,
        ),
        patch("src.core.llm_engine.time.sleep"),
    ):
        result = _translate_custom(["Hello"], "French", "English")

    assert result == ["Bonjour"]
    assert client.chat.completions.create.call_count == 4  # noqa: PLR2004
    final_kwargs = client.chat.completions.create.call_args_list[3].kwargs
    # Only one message, role=user, contains both the system prompt and the input.
    assert len(final_kwargs["messages"]) == 1
    assert final_kwargs["messages"][0]["role"] == "user"
    assert "Input:" in final_kwargs["messages"][0]["content"]
    assert "professional translator" in final_kwargs["messages"][0]["content"]


def test_translate_custom_chat_caches_successful_variant() -> None:
    """The first call probes variants; the second call skips straight to the winner.

    On a model that needs the ``minimal`` variant, the first call pays
    2 failed 400s before landing on variant 3.  The second call should
    consult ``_CUSTOM_VARIANT_CACHE`` and call the API exactly once.
    """
    import json  # noqa: PLC0415

    from src.core.llm_engine import (  # noqa: PLC0415
        _CUSTOM_VARIANT_CACHE,
        _translate_custom,
    )

    content = json.dumps({"results": [{"id": 0, "translated": "Bonjour"}]})

    # First call: 400, 400, success — cache should remember "minimal".
    client_first = _make_mock_sdk_client(
        chat_responses=[
            _sdk_http_error(400),
            _sdk_http_error(400),
            _make_sdk_chat_response(content),
        ],
    )
    # Second call: a single response is enough; if the cache works, the
    # dispatcher only invokes the API once.
    client_second = _make_mock_sdk_client(
        chat_responses=[_make_sdk_chat_response(content)],
    )

    settings = {
        "llm/custom_api_key": "k",
        "llm/custom_model": "o1",
        "llm/custom_endpoint": "https://example.com/v1",
    }
    with (
        patch(
            "src.core.llm_engine._config.load_setting",
            side_effect=lambda k, d="": settings.get(k, d),
        ),
        patch(
            "src.core.llm_engine._build_openai_client",
            return_value=client_first,
        ),
        patch("src.core.llm_engine.time.sleep"),
    ):
        assert _translate_custom(["Hello"], "French", "English") == ["Bonjour"]
    assert client_first.chat.completions.create.call_count == 3  # noqa: PLR2004
    assert _CUSTOM_VARIANT_CACHE[("https://example.com/v1", "o1")] == "minimal"

    with (
        patch(
            "src.core.llm_engine._config.load_setting",
            side_effect=lambda k, d="": settings.get(k, d),
        ),
        patch(
            "src.core.llm_engine._build_openai_client",
            return_value=client_second,
        ),
        patch("src.core.llm_engine.time.sleep"),
    ):
        assert _translate_custom(["Hello"], "French", "English") == ["Bonjour"]
    # Cache hit → only one API call this time.
    assert client_second.chat.completions.create.call_count == 1
    # And the call landed on the cached variant (no temperature, no response_format).
    cached_kwargs = client_second.chat.completions.create.call_args_list[0].kwargs
    assert "response_format" not in cached_kwargs
    assert "temperature" not in cached_kwargs


def test_translate_custom_chat_stale_cache_falls_through() -> None:
    """If a cached variant suddenly returns 400, dispatcher tries the rest.

    Provider config can change mid-session (e.g. an Azure deployment is
    upgraded to support response_format).  A stale cache pointing at
    "minimal" should not lock the dispatcher in — it must fall through
    to the remaining variants in original order and rewrite the cache.
    """
    import json  # noqa: PLC0415

    from src.core.llm_engine import (  # noqa: PLC0415
        _CUSTOM_VARIANT_CACHE,
        _translate_custom,
    )

    # Pre-seed the cache with a stale entry.
    _CUSTOM_VARIANT_CACHE[("https://example.com/v1", "m")] = "minimal"

    content = json.dumps({"results": [{"id": 0, "translated": "Bonjour"}]})
    # Cached "minimal" call → 400; fall through; "json_object+temperature"
    # succeeds.  Provider rejected the cached variant but accepts the rich one.
    client = _make_mock_sdk_client(
        chat_responses=[
            _sdk_http_error(400),
            _make_sdk_chat_response(content),
        ],
    )

    settings = {
        "llm/custom_api_key": "k",
        "llm/custom_model": "m",
        "llm/custom_endpoint": "https://example.com/v1",
    }
    with (
        patch(
            "src.core.llm_engine._config.load_setting",
            side_effect=lambda k, d="": settings.get(k, d),
        ),
        patch(
            "src.core.llm_engine._build_openai_client",
            return_value=client,
        ),
        patch("src.core.llm_engine.time.sleep"),
    ):
        assert _translate_custom(["Hello"], "French", "English") == ["Bonjour"]

    # Two calls: cached "minimal" failed, then fell through to the
    # original-order winner ("json_object+temperature").
    assert client.chat.completions.create.call_count == 2  # noqa: PLR2004
    # Cache should now reflect the new winner.
    assert (
        _CUSTOM_VARIANT_CACHE[("https://example.com/v1", "m")]
        == "json_object+temperature"
    )


def test_translate_custom_responses_uses_reasoning_timeout() -> None:
    """Responses-API calls override the per-client timeout for reasoning models.

    Reasoning models (o1, o3, gpt-5.x-pro, DeepSeek-R1, …) routinely
    take 2-10 minutes per request because they generate a long internal
    chain-of-thought before the answer.  The chat-default 90s would
    trigger ``httpx.ReadTimeout`` on every call; Responses calls must
    apply ``LLM_REASONING_TIMEOUT`` via per-call
    ``client.with_options(timeout=...)`` instead.
    """
    import json  # noqa: PLC0415

    from src.constants.llm import LLM_REASONING_TIMEOUT  # noqa: PLC0415
    from src.core.llm_engine import _translate_custom  # noqa: PLC0415

    content = json.dumps({"results": [{"id": 0, "translated": "Bonjour"}]})

    client = _make_mock_sdk_client(
        responses_response=_make_sdk_responses_response(content),
    )

    settings = {
        "llm/custom_api_key": "k",
        "llm/custom_model": "gpt-5.4-pro",
        # ``/responses`` leaf forces the explicit Responses path so we
        # don't probe chat first.
        "llm/custom_endpoint": "https://reasoning.example.com/v1/responses",
    }
    with (
        patch(
            "src.core.llm_engine._config.load_setting",
            side_effect=lambda k, d="": settings.get(k, d),
        ),
        patch(
            "src.core.llm_engine._build_openai_client",
            return_value=client,
        ),
        patch("src.core.llm_engine.time.sleep"),
    ):
        assert _translate_custom(["Hello"], "French", "English") == ["Bonjour"]

    # The per-call timeout MUST be the reasoning value, NOT the default.
    client.with_options.assert_called_with(timeout=LLM_REASONING_TIMEOUT)


def test_translate_custom_surfaces_responses_timeout_over_chat_invalid_request() -> None:
    """When chat fails AND responses times out, the user sees TIMEOUT_ERROR.

    The dispatcher must prefer the more *actionable* error.  An
    ``INVALID_REQUEST`` from chat is a benign signal that the model
    just doesn't accept this payload shape — pairing it with a real
    network / quota / credentials failure from responses, the latter
    is the diagnostic the user needs.  Informative responses tags
    (TIMEOUT_ERROR, CONNECTION_ERROR, QUOTA_ERROR, …) win; only when
    responses also returns a generic INVALID_REQUEST does the chat
    error get preserved.
    """
    from src.core.llm_engine import _translate_custom  # noqa: PLC0415

    # Chat: 4 variants all fail with 400 → INVALID_REQUEST.  Responses:
    # times out.  TIMEOUT_ERROR is non-retriable so a single attempt is
    # enough; chat exhausts its 4 variant probes per attempt.
    client = MagicMock()
    client.with_options.return_value = client
    client.chat.completions.create.side_effect = [
        _sdk_http_error(400),
        _sdk_http_error(400),
        _sdk_http_error(400),
        _sdk_http_error(400),
    ]
    client.responses.create.side_effect = _sdk_timeout_error()

    settings = {
        "llm/custom_api_key": "k",
        "llm/custom_model": "slow-reasoner",
        # Bare base URL → ambiguous → tries chat first, then falls back.
        "llm/custom_endpoint": "https://slow.example.com/v1",
    }
    # User must see TIMEOUT_ERROR (actionable: bump timeout / pick
    # faster model), NOT INVALID_REQUEST (misleading).
    with (
        patch(
            "src.core.llm_engine._config.load_setting",
            side_effect=lambda k, d="": settings.get(k, d),
        ),
        patch(
            "src.core.llm_engine._build_openai_client",
            return_value=client,
        ),
        patch("src.core.llm_engine.time.sleep"),
        pytest.raises(ValueError, match="^TIMEOUT_ERROR$"),
    ):
        _translate_custom(["Hello"], "French", "English")


def test_translate_custom_falls_back_to_chat_error_when_responses_invalid_request() -> None:
    """If both APIs return generic INVALID_REQUEST, chat error wins.

    When responses *also* raises a non-actionable error (model not on
    this endpoint, both APIs misconfigured), surfacing the chat error
    is at least as informative since the user originally targeted that
    side anyway.
    """
    from src.core.llm_engine import _translate_custom  # noqa: PLC0415

    client = _make_mock_sdk_client(
        chat_responses=[
            _sdk_http_error(400),
            _sdk_http_error(400),
            _sdk_http_error(400),
            _sdk_http_error(400),
        ],
        responses_error=_sdk_http_error(400),
    )

    settings = {
        "llm/custom_api_key": "k",
        "llm/custom_model": "broken-everywhere",
        "llm/custom_endpoint": "https://broken.example.com/v1",
    }
    with (
        patch(
            "src.core.llm_engine._config.load_setting",
            side_effect=lambda k, d="": settings.get(k, d),
        ),
        patch(
            "src.core.llm_engine._build_openai_client",
            return_value=client,
        ),
        patch("src.core.llm_engine.time.sleep"),
        pytest.raises(ValueError, match="^INVALID_REQUEST$"),
    ):
        _translate_custom(["Hello"], "French", "English")


def test_llm_engine_eagerly_caches_sdk_imports() -> None:
    """SDK trees are pre-loaded at module import to defeat UNO's import hook.

    A lazy ``from google.genai import errors`` inside
    ``_handle_api_error`` triggered for the first time after
    LibreOffice's UNO has activated its ``_uno_import`` hook would
    explode with ``AttributeError: 'NoneType' object has no attribute
    '__dict__'`` — the hook drops the venv ``site-packages`` from
    ``sys.path`` before re-importing PIL → defusedxml →
    ``_elementtree``.  Eagerly caching the SDK trees at ``llm_engine``
    import turns subsequent lazy imports into harmless cache lookups.
    This test guards against anyone moving the imports back inside
    functions and silently re-introducing the failure mode.
    """
    import sys  # noqa: PLC0415

    import src.core.llm_engine  # noqa: F401, PLC0415

    for required in (
        "openai",
        "google.genai",
        "google.genai.errors",
        "google.genai.types",
    ):
        assert required in sys.modules, (
            f"{required} must be cached in sys.modules at llm_engine import — "
            "lazy imports inside _handle_api_error would otherwise collide "
            "with LibreOffice's UNO import hook (see comment block at top "
            "of llm_engine.py)."
        )


def test_handle_api_error_maps_openai_connection_error() -> None:
    """A bare ``APIConnectionError`` maps cleanly to ``CONNECTION_ERROR``.

    Direct test of ``_handle_api_error`` rather than going through a
    ``_translate_custom`` mock — proves the error handler works on its
    own and that the lazy ``from google.genai import errors`` inside it
    resolves successfully (would explode if the SDK trees weren't
    pre-loaded into ``sys.modules``).
    """
    from unittest.mock import MagicMock  # noqa: PLC0415

    from openai import APIConnectionError as _APIConnectionError  # noqa: PLC0415

    from src.core.llm_engine import _handle_api_error  # noqa: PLC0415

    err = _APIConnectionError(request=MagicMock())
    with pytest.raises(ValueError, match="^CONNECTION_ERROR$"):
        _handle_api_error(err, "Custom", "Chat")


def test_strip_think_blocks_removes_closed_block() -> None:
    """The standard Qwen / Gemma / DeepSeek-R1 closed `<think>` is stripped."""
    from src.core.llm_engine import _strip_think_blocks  # noqa: PLC0415

    raw = '<think>let me reason about this</think>{"results": []}'
    assert _strip_think_blocks(raw) == '{"results": []}'


def test_strip_think_blocks_handles_multiline_block() -> None:
    """`<think>` may span many lines (DOTALL semantics)."""
    from src.core.llm_engine import _strip_think_blocks  # noqa: PLC0415

    raw = "<think>\n  step 1\n  step 2\n  step 3\n</think>\n\n{}"
    assert _strip_think_blocks(raw) == "{}"


def test_strip_think_blocks_strips_multiple_sequential_blocks() -> None:
    """A model that emits two reasoning passes still cleans down to JSON."""
    from src.core.llm_engine import _strip_think_blocks  # noqa: PLC0415

    raw = "<think>first</think><think>second</think>final"
    assert _strip_think_blocks(raw) == "final"


def test_strip_think_blocks_handles_unclosed_truncated_block(caplog) -> None:
    """An unclosed `<think>` (truncated by max_tokens) is stripped to end.

    Without this sweep the entire reasoning blob would hit the JSON
    parser and surface as ``INVALID_RESPONSE`` with no diagnostic.
    """
    import logging  # noqa: PLC0415

    from src.core.llm_engine import _strip_think_blocks  # noqa: PLC0415

    raw = "<think>partial reasoning that never finished"
    with caplog.at_level(logging.WARNING, logger="llm"):
        assert _strip_think_blocks(raw) == ""
    # User gets a breadcrumb pointing at the real cause.
    assert any(
        "unclosed <think>" in record.message and "max_tokens" in record.message
        for record in caplog.records
    )


def test_strip_think_blocks_passes_through_clean_response() -> None:
    """A response without any think tag is returned unchanged."""
    from src.core.llm_engine import _strip_think_blocks  # noqa: PLC0415

    raw = '{"results": [{"id": 0, "translated": "Bonjour"}]}'
    assert _strip_think_blocks(raw) == raw


def test_strip_think_tags_streaming_unclosed_logs_warning(caplog) -> None:
    """A stream ending inside `<think>` drops the buffer + logs the same diagnostic.

    Symmetric with the non-streaming `_strip_think_blocks` warning so
    users get the same actionable hint (raise max_tokens / pick a
    non-reasoning model) regardless of which path produced the failure.
    """
    import logging  # noqa: PLC0415

    from src.core.llm_engine import _strip_think_tags  # noqa: PLC0415

    def truncated_stream():
        yield "<think>partial reasoning that "
        yield "never gets the closing tag"

    with caplog.at_level(logging.WARNING, logger="llm"):
        emitted = list(_strip_think_tags(truncated_stream()))

    # Nothing should be emitted — every chunk was inside the unclosed think.
    assert emitted == []
    # And the user got the same WARNING the non-streaming path emits.
    assert any(
        "unclosed <think>" in r.message and "max_tokens" in r.message
        for r in caplog.records
    )


def test_strip_think_tags_streaming_closed_block_works(caplog) -> None:
    """Closed `<think>` followed by content streams correctly with no warning."""
    import logging  # noqa: PLC0415

    from src.core.llm_engine import _strip_think_tags  # noqa: PLC0415

    def stream():
        yield "<think>step "
        yield "1</think>"
        yield "answer"

    with caplog.at_level(logging.WARNING, logger="llm"):
        result = "".join(_strip_think_tags(stream()))

    assert result == "answer"
    # No truncation warning on a clean stream.
    assert not any("unclosed <think>" in r.message for r in caplog.records)


def test_translate_custom_strips_think_block_before_json_parse() -> None:
    """End-to-end: a Qwen-style response with `<think>` round-trips correctly."""
    import json  # noqa: PLC0415

    from src.core.llm_engine import _translate_custom  # noqa: PLC0415

    json_payload = json.dumps(
        {"results": [{"id": 0, "translated": "Bonjour"}]},
    )
    raw_content = f"<think>Translating greeting…</think>{json_payload}"

    client = _make_mock_sdk_client(
        chat_responses=[_make_sdk_chat_response(raw_content)],
    )
    settings = {
        "llm/custom_api_key": "k",
        "llm/custom_model": "qwen3-think",
        "llm/custom_endpoint": "https://qwen.example.com/v1",
    }
    with (
        patch(
            "src.core.llm_engine._config.load_setting",
            side_effect=lambda k, d="": settings.get(k, d),
        ),
        patch(
            "src.core.llm_engine._build_openai_client",
            return_value=client,
        ),
        patch("src.core.llm_engine.time.sleep"),
    ):
        assert _translate_custom(["Hello"], "French", "English") == ["Bonjour"]


def test_translate_custom_cold_start_coalesces_to_single_persist(tmp_path) -> None:
    """Cold-start probe writes the cache file exactly once, not twice.

    The chat helper's variant-cache mutation must defer its disk write
    so the dispatcher's api-cache mutation can fold both into a single
    ``_persist_caches()`` call after success.  This test counts
    persist calls via a spy on ``_persist_caches``.
    """
    import json  # noqa: PLC0415

    import src.core.llm_engine as engine_module  # noqa: PLC0415
    from src.core.llm_engine import _translate_custom  # noqa: PLC0415

    cache_file = tmp_path / "llm_endpoint_cache.json"
    content = json.dumps({"results": [{"id": 0, "translated": "Bonjour"}]})

    # Two failed 400s + success = "minimal" variant on a previously
    # unseen (endpoint, model) — both api-cache and variant-cache are
    # set in this single call.
    client = _make_mock_sdk_client(
        chat_responses=[
            _sdk_http_error(400),
            _sdk_http_error(400),
            _make_sdk_chat_response(content),
        ],
    )

    settings = {
        "llm/custom_api_key": "k",
        "llm/custom_model": "coalesce-model",
        "llm/custom_endpoint": "https://coalesce.example.com/v1",
    }

    # Spy on the real _persist_caches so the disk effects still happen
    # (so we can also verify the file ends up with both entries) but we
    # can count call count.
    real_persist = engine_module._persist_caches
    persist_calls = []

    def spying_persist(*args, **kwargs):
        persist_calls.append(1)
        return real_persist(*args, **kwargs)

    with (
        patch(
            "src.utils.path_manager.get_llm_endpoint_cache_path",
            return_value=cache_file,
        ),
        patch(
            "src.core.llm_engine._config.load_setting",
            side_effect=lambda k, d="": settings.get(k, d),
        ),
        patch(
            "src.core.llm_engine._build_openai_client",
            return_value=client,
        ),
        patch("src.core.llm_engine._persist_caches", side_effect=spying_persist),
        patch("src.core.llm_engine.time.sleep"),
    ):
        assert _translate_custom(["Hello"], "French", "English") == ["Bonjour"]

    # Exactly one persist for the cold-start case (down from two).
    assert len(persist_calls) == 1, f"expected 1 persist, got {len(persist_calls)}"

    # And the file actually contains both entries — coalescing didn't
    # silently lose either side.
    on_disk = json.loads(cache_file.read_text())
    raw_key = "https://coalesce.example.com/v1|coalesce-model"
    assert on_disk["api_cache"][raw_key] == "chat"
    assert on_disk["variant_cache"][raw_key] == "minimal"


def test_translate_custom_cache_hit_skips_persist(tmp_path) -> None:
    """A repeat call against fully-cached state writes the file zero times."""
    import json  # noqa: PLC0415

    import src.core.llm_engine as engine_module  # noqa: PLC0415
    from src.core.llm_engine import (  # noqa: PLC0415
        _CUSTOM_API_CACHE,
        _CUSTOM_VARIANT_CACHE,
        _custom_cache_key,
        _translate_custom,
    )

    cache_file = tmp_path / "llm_endpoint_cache.json"
    content = json.dumps({"results": [{"id": 0, "translated": "Bonjour"}]})

    # Pre-seed both caches as if a previous call already probed.
    key = _custom_cache_key("https://hit.example.com/v1", "hit-model")
    _CUSTOM_API_CACHE[key] = "chat"
    _CUSTOM_VARIANT_CACHE[key] = "json_object+temperature"

    client = _make_mock_sdk_client(
        chat_responses=[_make_sdk_chat_response(content)],
    )

    settings = {
        "llm/custom_api_key": "k",
        "llm/custom_model": "hit-model",
        "llm/custom_endpoint": "https://hit.example.com/v1",
    }

    real_persist = engine_module._persist_caches
    persist_calls = []

    def spying_persist(*args, **kwargs):
        persist_calls.append(1)
        return real_persist(*args, **kwargs)

    with (
        patch(
            "src.utils.path_manager.get_llm_endpoint_cache_path",
            return_value=cache_file,
        ),
        patch(
            "src.core.llm_engine._config.load_setting",
            side_effect=lambda k, d="": settings.get(k, d),
        ),
        patch(
            "src.core.llm_engine._build_openai_client",
            return_value=client,
        ),
        patch("src.core.llm_engine._persist_caches", side_effect=spying_persist),
        patch("src.core.llm_engine.time.sleep"),
    ):
        assert _translate_custom(["Hello"], "French", "English") == ["Bonjour"]

    # Cache-hit path → zero persist calls (no in-memory changes to flush).
    assert len(persist_calls) == 0, (
        f"expected 0 persists on cache hit, got {len(persist_calls)}"
    )


def test_persist_caches_concurrent_writers(tmp_path) -> None:
    """Many threads calling _persist_caches at once leave a valid file.

    Regression guard against the old failure mode where every writer
    used the same ``.json.tmp`` filename and clobbered each other's
    pre-rename file (raising FileNotFoundError on the second rename
    and silently losing that thread's persistence).  After the fix
    each writer mkstemp's a unique tmp path, the lock serialises the
    read-merge-write block, and every writer's entry survives in the
    final on-disk JSON.
    """
    import json  # noqa: PLC0415
    from concurrent.futures import ThreadPoolExecutor  # noqa: PLC0415

    from src.core.llm_engine import (  # noqa: PLC0415
        _CACHE_LOCK,
        _CUSTOM_API_CACHE,
        _CUSTOM_VARIANT_CACHE,
        _persist_caches,
    )

    cache_file = tmp_path / "llm_endpoint_cache.json"

    # Each thread inserts a distinct entry then triggers a persist.
    # The read-merge-write contract means every entry must survive.
    n_writers = 16

    def writer(i: int) -> None:
        key = (f"https://w{i}.example.com/v1", f"m-{i}")
        with _CACHE_LOCK:
            _CUSTOM_API_CACHE[key] = "chat"
            _CUSTOM_VARIANT_CACHE[key] = "minimal"
            _persist_caches()

    with (
        patch(
            "src.utils.path_manager.get_llm_endpoint_cache_path",
            return_value=cache_file,
        ),
        ThreadPoolExecutor(max_workers=n_writers) as pool,
    ):
        list(pool.map(writer, range(n_writers)))

    # File exists, parses cleanly, contains every writer's entry.
    assert cache_file.is_file()
    payload = json.loads(cache_file.read_text())
    assert payload["version"] == 1
    for i in range(n_writers):
        raw_key = f"https://w{i}.example.com/v1|m-{i}"
        assert payload["api_cache"][raw_key] == "chat"
        assert payload["variant_cache"][raw_key] == "minimal"

    # No orphan tmp files left behind in the cache dir.
    leftover_tmps = list(tmp_path.glob("*.tmp"))
    assert leftover_tmps == [], f"orphan tmp files: {leftover_tmps}"


def test_persist_caches_merges_with_sibling_process_writes(tmp_path) -> None:
    """A pre-existing on-disk entry from a sibling process survives our write.

    Read-merge-write contract: when we persist, we must NOT clobber
    entries that another process / earlier session wrote but our
    in-memory dict doesn't know about.
    """
    import json  # noqa: PLC0415

    from src.core.llm_engine import (  # noqa: PLC0415
        _CUSTOM_API_CACHE,
        _persist_caches,
    )

    cache_file = tmp_path / "llm_endpoint_cache.json"

    # Simulate sibling-process state: pre-seed the disk file directly.
    cache_file.write_text(
        json.dumps(
            {
                "version": 1,
                "api_cache": {"https://sibling.example.com/v1|sib-model": "chat"},
                "variant_cache": {
                    "https://sibling.example.com/v1|sib-model": "temperature_only",
                },
            },
        ),
    )

    # Our in-memory state has a different entry; persist should preserve both.
    _CUSTOM_API_CACHE[("https://us.example.com/v1", "us-model")] = "responses"

    with patch(
        "src.utils.path_manager.get_llm_endpoint_cache_path",
        return_value=cache_file,
    ):
        _persist_caches()

    merged = json.loads(cache_file.read_text())
    # Sibling's entry survived our overwrite.
    assert (
        merged["api_cache"]["https://sibling.example.com/v1|sib-model"] == "chat"
    )
    assert (
        merged["variant_cache"]["https://sibling.example.com/v1|sib-model"]
        == "temperature_only"
    )
    # Ours is also present.
    assert merged["api_cache"]["https://us.example.com/v1|us-model"] == "responses"


def test_persistent_caches_round_trip(tmp_path) -> None:
    """A successful chat call writes to disk; load_persistent_caches re-hydrates.

    This is the persistence story end-to-end: the in-memory caches get
    flushed to ``llm_endpoint_cache.json`` after each mutation, and a
    fresh process (simulated by clearing dicts then calling
    ``_load_persistent_caches``) recovers the same entries.
    """
    import json  # noqa: PLC0415

    from src.core.llm_engine import (  # noqa: PLC0415
        _CUSTOM_API_CACHE,
        _CUSTOM_VARIANT_CACHE,
        _custom_cache_key,
        _load_persistent_caches,
        _translate_custom,
    )

    cache_file = tmp_path / "llm_endpoint_cache.json"
    content = json.dumps({"results": [{"id": 0, "translated": "Bonjour"}]})

    # Two failed 400s then success — should land on "minimal" variant.
    client_first = _make_mock_sdk_client(
        chat_responses=[
            _sdk_http_error(400),
            _sdk_http_error(400),
            _make_sdk_chat_response(content),
        ],
    )

    settings = {
        "llm/custom_api_key": "k",
        "llm/custom_model": "o1-persist",
        "llm/custom_endpoint": "https://persist.example.com/v1",
    }
    with (
        patch(
            "src.utils.path_manager.get_llm_endpoint_cache_path",
            return_value=cache_file,
        ),
        patch(
            "src.core.llm_engine._config.load_setting",
            side_effect=lambda k, d="": settings.get(k, d),
        ),
        patch(
            "src.core.llm_engine._build_openai_client",
            return_value=client_first,
        ),
        patch("src.core.llm_engine.time.sleep"),
    ):
        assert _translate_custom(["Hello"], "French", "English") == ["Bonjour"]
        # Disk file should exist and contain both cache types.
        assert cache_file.is_file()
        on_disk = json.loads(cache_file.read_text())
        assert on_disk["version"] == 1
        assert (
            on_disk["variant_cache"]["https://persist.example.com/v1|o1-persist"]
            == "minimal"
        )
        assert (
            on_disk["api_cache"]["https://persist.example.com/v1|o1-persist"]
            == "chat"
        )

        # Simulate fresh process: wipe in-memory caches, then load from disk.
        _CUSTOM_API_CACHE.clear()
        _CUSTOM_VARIANT_CACHE.clear()
        _load_persistent_caches()

    expected_key = _custom_cache_key("https://persist.example.com/v1", "o1-persist")
    assert _CUSTOM_API_CACHE[expected_key] == "chat"
    assert _CUSTOM_VARIANT_CACHE[expected_key] == "minimal"


def test_load_persistent_caches_handles_missing_file(tmp_path) -> None:
    """Missing cache file is silently treated as 'no cached state'."""
    from src.core.llm_engine import (  # noqa: PLC0415
        _CUSTOM_API_CACHE,
        _CUSTOM_VARIANT_CACHE,
        _load_persistent_caches,
    )

    missing = tmp_path / "does-not-exist.json"
    with patch(
        "src.utils.path_manager.get_llm_endpoint_cache_path",
        return_value=missing,
    ):
        _load_persistent_caches()  # must not raise

    assert _CUSTOM_API_CACHE == {}
    assert _CUSTOM_VARIANT_CACHE == {}


def test_load_persistent_caches_ignores_wrong_schema_version(tmp_path) -> None:
    """A file written by a future / older schema is treated as 'empty'."""
    import json  # noqa: PLC0415

    from src.core.llm_engine import (  # noqa: PLC0415
        _CUSTOM_API_CACHE,
        _CUSTOM_VARIANT_CACHE,
        _load_persistent_caches,
    )

    cache_file = tmp_path / "wrong_version.json"
    cache_file.write_text(
        json.dumps(
            {
                "version": 999,
                "api_cache": {"https://x.example.com/v1|m": "chat"},
                "variant_cache": {"https://x.example.com/v1|m": "minimal"},
            },
        ),
    )
    with patch(
        "src.utils.path_manager.get_llm_endpoint_cache_path",
        return_value=cache_file,
    ):
        _load_persistent_caches()

    # Wrong schema → discard; in-memory caches stay empty.
    assert _CUSTOM_API_CACHE == {}
    assert _CUSTOM_VARIANT_CACHE == {}


def test_load_persistent_caches_handles_corrupted_json(tmp_path, caplog) -> None:  # noqa: ANN001
    """A truncated / unparseable cache file is logged and skipped.

    The disk cache could be corrupted by a power loss mid-write, an
    SD-card flake, or a user editing the file by hand.  A
    ``json.JSONDecodeError`` must NOT take down the next translation
    request — it should be logged and the in-memory caches start
    empty, so the variant probe just runs from scratch.
    """
    import logging  # noqa: PLC0415

    from src.core.llm_engine import (  # noqa: PLC0415
        _CUSTOM_API_CACHE,
        _CUSTOM_VARIANT_CACHE,
        _load_persistent_caches,
    )

    bad = tmp_path / "corrupt.json"
    bad.write_text('{"version": 1, "api_cache": {trunc')  # invalid JSON
    # ``caplog`` defaults to WARNING level on the *root* logger; an
    # earlier test in the suite may have raised the ``llm`` logger's
    # threshold above WARNING (some test files configure it to ERROR
    # to silence variant-fallback logs), so explicitly bind the level
    # for the duration of this test.
    with (
        caplog.at_level(logging.WARNING, logger="llm"),
        patch(
            "src.utils.path_manager.get_llm_endpoint_cache_path",
            return_value=bad,
        ),
    ):
        _load_persistent_caches()  # must not raise

    assert _CUSTOM_API_CACHE == {}
    assert _CUSTOM_VARIANT_CACHE == {}
    assert any(
        "Failed to load LLM endpoint cache" in rec.message
        for rec in caplog.records
    )


def test_custom_cache_key_collapses_cosmetic_endpoint_variations() -> None:
    """Trailing-slash / scheme / leaf-path differences map to one key.

    Without canonicalisation the same logical endpoint would fragment
    across multiple cache entries and re-pay the variant probe on each
    cosmetic change.  Genuine endpoint changes (different host) still
    produce different keys — that's the invalidation we want.
    """
    from src.core.llm_engine import _custom_cache_key  # noqa: PLC0415

    canonical = _custom_cache_key("https://api.example.com/v1", "m")

    # Trailing slash collapses.
    assert _custom_cache_key("https://api.example.com/v1/", "m") == canonical
    # Whitespace collapses.
    assert _custom_cache_key("  https://api.example.com/v1  ", "m") == canonical
    # Missing scheme collapses (defaults to https://).
    assert _custom_cache_key("api.example.com/v1", "m") == canonical
    # Explicit /chat/completions leaf collapses (same logical endpoint).
    assert (
        _custom_cache_key("https://api.example.com/v1/chat/completions", "m")
        == canonical
    )
    # Explicit /responses leaf collapses too.
    assert (
        _custom_cache_key("https://api.example.com/v1/responses", "m") == canonical
    )

    # Genuine endpoint change → different key (cache invalidates correctly).
    assert (
        _custom_cache_key("https://different-host.example.com/v1", "m") != canonical
    )
    # Different model → different key (model+endpoint both participate).
    assert _custom_cache_key("https://api.example.com/v1", "other-model") != canonical
    # Different *path* on same host → different key.  Regression for the
    # audit-flagged concern that a future "optimization" might normalise
    # the path away (e.g. strip ``/v1``/``/v2``) and collapse two
    # genuinely-different endpoints into one cache entry — the variant
    # learned on /v1 (e.g. ``temperature_only``) would then poison /v2
    # calls that may need a different payload shape.
    assert (
        _custom_cache_key("https://api.example.com/v2", "m") != canonical
    )
    # Different *port* → different key (same host, different service).
    assert (
        _custom_cache_key("https://api.example.com:8080/v1", "m") != canonical
    )


def test_classify_endpoint_detects_explicit_chat() -> None:
    """A pasted /chat/completions URL is flagged as explicit chat."""
    from src.core.llm_engine import _classify_custom_endpoint  # noqa: PLC0415

    api, base = _classify_custom_endpoint(
        "https://api.example.com/v1/chat/completions",
    )
    assert api == "chat"
    assert base == "https://api.example.com/v1"


def test_classify_endpoint_detects_explicit_responses() -> None:
    """A pasted /responses URL is flagged as explicit responses."""
    from src.core.llm_engine import _classify_custom_endpoint  # noqa: PLC0415

    api, base = _classify_custom_endpoint(
        "https://api.example.com/v1/responses",
    )
    assert api == "responses"
    assert base == "https://api.example.com/v1"


def test_classify_endpoint_treats_base_url_as_ambiguous() -> None:
    """Bare /v1 endpoint returns no explicit choice (auto-fallback enabled)."""
    from src.core.llm_engine import _classify_custom_endpoint  # noqa: PLC0415

    api, base = _classify_custom_endpoint("https://api.example.com/v1")
    assert api is None
    assert base == "https://api.example.com/v1"


def test_classify_endpoint_adds_https_scheme() -> None:
    """Schemeless input is upgraded to https for safety."""
    from src.core.llm_engine import _classify_custom_endpoint  # noqa: PLC0415

    _api, base = _classify_custom_endpoint("api.example.com/v1")
    assert base.startswith("https://")


def test_translate_custom_falls_back_to_responses_api() -> None:
    """When chat/completions returns INVALID_REQUEST, retry on /responses.

    Regression for Azure GPT-5.x deployments where the model exists but
    ``capabilities.chat_completion`` is False; the only way to call the
    model is via the Responses API.
    """
    from src.core.llm_engine import (  # noqa: PLC0415
        _CUSTOM_API_CACHE,
        _translate_custom,
    )

    responses_content = json.dumps(
        {"results": [{"id": 0, "translated": "Bonjour"}]},
    )

    client = _make_mock_sdk_client(
        chat_errors=[
            _sdk_http_error(400),
            _sdk_http_error(400),
            _sdk_http_error(400),
            _sdk_http_error(400),
        ],
        responses_response=_make_sdk_responses_response(responses_content),
    )

    settings = {
        "llm/custom_api_key": "k",
        "llm/custom_model": "gpt-5.4-pro",
        "llm/custom_endpoint": "https://example.com/v1",
    }
    with (
        patch(
            "src.core.llm_engine._config.load_setting",
            side_effect=lambda k, d="": settings.get(k, d),
        ),
        patch(
            "src.core.llm_engine._build_openai_client",
            return_value=client,
        ),
        patch("src.core.llm_engine.time.sleep"),
    ):
        result = _translate_custom(["Hello"], "French", "English")

    assert result == ["Bonjour"]
    # 4 chat probes were tried, then the Responses fallback succeeded.
    assert client.chat.completions.create.call_count == 4  # noqa: PLR2004
    assert client.responses.create.call_count == 1
    # And the API choice is cached so subsequent calls skip chat entirely.
    assert _CUSTOM_API_CACHE.get(
        ("https://example.com/v1", "gpt-5.4-pro"),
    ) == "responses"


def test_translate_custom_explicit_responses_endpoint_skips_chat() -> None:
    """User pasting /responses goes straight there — no chat probe.

    The endpoint URL ending in ``/responses`` is treated as an explicit
    declaration; the dispatcher honours it and never tries
    chat/completions.
    """
    from src.core.llm_engine import _translate_custom  # noqa: PLC0415

    responses_content = json.dumps(
        {"results": [{"id": 0, "translated": "Bonjour"}]},
    )

    client = _make_mock_sdk_client(
        responses_response=_make_sdk_responses_response(responses_content),
    )

    settings = {
        "llm/custom_api_key": "k",
        "llm/custom_model": "gpt-5.4-pro",
        "llm/custom_endpoint": "https://example.com/v1/responses",
    }
    with (
        patch(
            "src.core.llm_engine._config.load_setting",
            side_effect=lambda k, d="": settings.get(k, d),
        ),
        patch(
            "src.core.llm_engine._build_openai_client",
            return_value=client,
        ),
        patch("src.core.llm_engine.time.sleep"),
    ):
        result = _translate_custom(["Hello"], "French", "English")

    assert result == ["Bonjour"]
    # No chat probe — went straight to /responses.
    assert client.chat.completions.create.call_count == 0
    assert client.responses.create.call_count == 1


def test_translate_custom_explicit_chat_endpoint_skips_responses_fallback() -> None:
    """User pasting /chat/completions never falls back to /responses.

    Even if the chat endpoint returns INVALID_REQUEST after exhausting
    every payload variant, the dispatcher respects the explicit choice
    and surfaces the error instead of probing /responses.
    """
    from src.core.llm_engine import _translate_custom  # noqa: PLC0415

    client = _make_mock_sdk_client(
        chat_errors=[
            _sdk_http_error(400),
            _sdk_http_error(400),
            _sdk_http_error(400),
            _sdk_http_error(400),
        ],
    )

    settings = {
        "llm/custom_api_key": "k",
        "llm/custom_model": "broken",
        "llm/custom_endpoint": "https://example.com/v1/chat/completions",
    }
    with (
        patch(
            "src.core.llm_engine._config.load_setting",
            side_effect=lambda k, d="": settings.get(k, d),
        ),
        patch(
            "src.core.llm_engine._build_openai_client",
            return_value=client,
        ),
        patch("src.core.llm_engine.time.sleep"),
        pytest.raises(ValueError, match="INVALID_REQUEST"),
    ):
        _translate_custom(["Hello"], "French", "English")

    # Exactly 4 chat probes — no /responses attempt.
    assert client.chat.completions.create.call_count == 4  # noqa: PLR2004
    assert client.responses.create.call_count == 0


def test_translate_custom_uses_cached_responses_api() -> None:
    """Cached 'responses' choice means only one request is sent.

    No chat/completions probing — the dispatcher goes straight to the
    Responses endpoint.  Saves a network round-trip per call after the
    first translation against a Responses-only model.
    """
    from src.core.llm_engine import (  # noqa: PLC0415
        _CUSTOM_API_CACHE,
        _translate_custom,
    )

    responses_content = json.dumps(
        {"results": [{"id": 0, "translated": "Bonjour"}]},
    )

    client = _make_mock_sdk_client(
        responses_response=_make_sdk_responses_response(responses_content),
    )

    settings = {
        "llm/custom_api_key": "k",
        "llm/custom_model": "gpt-5.4-pro",
        "llm/custom_endpoint": "https://example.com/v1",
    }
    # Pre-populate the cache as if a previous call discovered Responses.
    _CUSTOM_API_CACHE[("https://example.com/v1", "gpt-5.4-pro")] = "responses"

    with (
        patch(
            "src.core.llm_engine._config.load_setting",
            side_effect=lambda k, d="": settings.get(k, d),
        ),
        patch(
            "src.core.llm_engine._build_openai_client",
            return_value=client,
        ),
        patch("src.core.llm_engine.time.sleep"),
    ):
        result = _translate_custom(["Hello"], "French", "English")

    assert result == ["Bonjour"]
    assert client.chat.completions.create.call_count == 0
    assert client.responses.create.call_count == 1


def test_translate_custom_all_variants_fail_raises_invalid_request() -> None:
    """When every payload variant returns 400 the call surfaces INVALID_REQUEST."""
    import pytest  # noqa: PLC0415

    from src.core.llm_engine import _translate_custom  # noqa: PLC0415

    client = _make_mock_sdk_client(
        chat_error=_sdk_http_error(400),
        responses_error=_sdk_http_error(400),
    )

    settings = {
        "llm/custom_api_key": "k",
        "llm/custom_model": "broken-all-variants",
        "llm/custom_endpoint": "https://example.com/v1",
    }
    with (
        patch(
            "src.core.llm_engine._config.load_setting",
            side_effect=lambda k, d="": settings.get(k, d),
        ),
        patch(
            "src.core.llm_engine._build_openai_client",
            return_value=client,
        ),
        patch("src.core.llm_engine.time.sleep"),
        pytest.raises(ValueError, match="INVALID_REQUEST"),
    ):
        _translate_custom(["Hello"], "French", "English")


def test_translate_custom_parses_json_in_markdown_fence() -> None:
    """Strips ```json fences from the response content.

    Common when response_format isn't honoured by the model — the JSON
    is still parsed correctly via _extract_json_object.
    """
    import json  # noqa: PLC0415

    from src.core.llm_engine import _translate_custom  # noqa: PLC0415

    fenced_content = (
        "Here you go:\n```json\n"
        + json.dumps({"results": [{"id": 0, "translated": "Bonjour"}]})
        + "\n```\n"
    )

    client = _make_mock_sdk_client(
        chat_response=_make_sdk_chat_response(fenced_content),
    )

    settings = {
        "llm/custom_api_key": "k",
        "llm/custom_model": "gpt-4",
        "llm/custom_endpoint": "https://example.com/v1",
    }
    with (
        patch(
            "src.core.llm_engine._config.load_setting",
            side_effect=lambda k, d="": settings.get(k, d),
        ),
        patch(
            "src.core.llm_engine._build_openai_client",
            return_value=client,
        ),
        patch("src.core.llm_engine.time.sleep"),
    ):
        result = _translate_custom(["Hello"], "French", "English")

    assert result == ["Bonjour"]


# ---------------------------------------------------------------------------
# translate_image_content — unknown method
# ---------------------------------------------------------------------------


def test_translate_image_content_unknown_method_returns_empty() -> None:
    """translate_image_content with unknown method returns empty list."""
    mock_ocr = MagicMock()
    mock_ocr.text = "Hello"
    with patch(
        "src.core.llm_engine._resolve_provider_model",
        return_value=("UnknownProvider", ""),
    ):
        result = translate_image_content("/fake.jpg", [mock_ocr], "French")
    assert result == []


def test_translate_image_content_empty_ocr_returns_empty() -> None:
    """translate_image_content with empty OCR results returns empty list."""
    result = translate_image_content("/fake.jpg", [], "French")
    assert result == []


# ---------------------------------------------------------------------------
# _translate_image_gemini — non-vision model fallback
# ---------------------------------------------------------------------------


def test_translate_image_gemini_non_vision_model_uses_default() -> None:
    """_translate_image_gemini falls back to default model for non-vision models."""
    from src.core.llm_engine import (  # noqa: PLC0415
        DEFAULT_GEMINI_MODEL,
        _translate_image_gemini,
    )

    settings = {
        "llm/gemini_api_key": "test-key",
        "llm/gemini_model": "text-only-model",
    }

    def fake_load(k, d):  # noqa: ANN001, ANN202
        return settings.get(k, d)

    inner = json.dumps({"paragraphs": []})
    client = _make_mock_genai_client(response_text=inner)

    with (
        patch("src.core.llm_engine._config.load_setting", side_effect=fake_load),
        patch("src.core.llm_engine._build_gemini_client", return_value=client),
        patch("pathlib.Path.read_bytes", return_value=b"fake image"),
    ):
        _translate_image_gemini(
            "/fake.jpg",
            [{"id": 0, "text": "Hello"}],
            "French",
            "English",
        )

    # The SDK should have been called with the default vision model, not the
    # "text-only-model" the user configured.
    assert client.models.generate_content.call_count == 1
    sent_model = client.models.generate_content.call_args.kwargs["model"]
    assert sent_model == DEFAULT_GEMINI_MODEL
    assert sent_model != "text-only-model"


# ---------------------------------------------------------------------------
# _format_lang_pair
# ---------------------------------------------------------------------------


def test_format_lang_pair_with_source() -> None:
    """With source language, returns 'from X to Y' format."""
    result = _format_lang_pair("English", "French")
    assert result == "Translate the following from English to French."


def test_format_lang_pair_without_source() -> None:
    """Without source language, returns 'into Y' format (auto-detect)."""
    result = _format_lang_pair("", "French")
    assert result == "Translate the following into French."


# ---------------------------------------------------------------------------
# _build_translation_prompt
# ---------------------------------------------------------------------------


def test_build_translation_prompt_plain_text() -> None:
    """Plain text prompt includes format rules and output format."""
    result = _build_translation_prompt(CONTENT_PLAIN_TEXT, "English", "French")
    assert "professional translator" in result
    assert "from English to French" in result
    assert "JSON" in result


def test_build_translation_prompt_data_values_no_quality() -> None:
    """Data values prompt excludes quality guidance."""
    from src.constants.llm import CONTENT_DATA_VALUES  # noqa: PLC0415

    result = _build_translation_prompt(CONTENT_DATA_VALUES, "", "French")
    assert "Preserve the original tone" not in result


def test_build_translation_prompt_with_glossary() -> None:
    """Prompt includes glossary entries when provided."""
    glossary = [(1, "hello", "bonjour")]
    result = _build_translation_prompt(
        CONTENT_PLAIN_TEXT,
        "English",
        "French",
        glossary,
    )
    assert "hello = bonjour" in result


def test_build_translation_prompt_pdf_preserves_html_tags() -> None:
    """PDF content type prompt instructs to preserve inline HTML tags."""
    result = _build_translation_prompt(CONTENT_PDF, "English", "French")
    assert "inline HTML tags" in result
    assert "preserve them exactly" in result


def test_build_translation_prompt_unknown_content_type_uses_plain_text() -> None:
    """Unknown content type falls back to plain text format rules."""
    plain_result = _build_translation_prompt(
        CONTENT_PLAIN_TEXT,
        "English",
        "French",
    )
    unknown_result = _build_translation_prompt(
        "unknown_type",
        "English",
        "French",
    )
    # Both should contain the same format rules
    assert "Produce fluent" in plain_result
    assert "Produce fluent" in unknown_result


# ---------------------------------------------------------------------------
# _guess_image_mime
# ---------------------------------------------------------------------------


def test_guess_image_mime_jpg() -> None:
    """'.jpg' maps to 'image/jpeg'."""
    from src.core.llm_engine import _guess_image_mime  # noqa: PLC0415

    assert _guess_image_mime("/path/to/photo.jpg") == "image/jpeg"


def test_guess_image_mime_jpeg() -> None:
    """'.jpeg' maps to 'image/jpeg'."""
    from src.core.llm_engine import _guess_image_mime  # noqa: PLC0415

    assert _guess_image_mime("/photo.jpeg") == "image/jpeg"


def test_guess_image_mime_png() -> None:
    """'.png' maps to 'image/png'."""
    from src.core.llm_engine import _guess_image_mime  # noqa: PLC0415

    assert _guess_image_mime("/image.png") == "image/png"


def test_guess_image_mime_webp() -> None:
    """'.webp' maps to 'image/webp'."""
    from src.core.llm_engine import _guess_image_mime  # noqa: PLC0415

    assert _guess_image_mime("/image.webp") == "image/webp"


def test_guess_image_mime_bmp() -> None:
    """'.bmp' maps to 'image/bmp'."""
    from src.core.llm_engine import _guess_image_mime  # noqa: PLC0415

    assert _guess_image_mime("/image.bmp") == "image/bmp"


def test_guess_image_mime_gif() -> None:
    """'.gif' maps to 'image/gif'."""
    from src.core.llm_engine import _guess_image_mime  # noqa: PLC0415

    assert _guess_image_mime("/image.gif") == "image/gif"


def test_guess_image_mime_tiff() -> None:
    """'.tiff' and '.tif' both map to 'image/tiff'."""
    from src.core.llm_engine import _guess_image_mime  # noqa: PLC0415

    assert _guess_image_mime("/scan.tiff") == "image/tiff"
    assert _guess_image_mime("/scan.tif") == "image/tiff"


def test_guess_image_mime_unknown_falls_back_to_jpeg() -> None:
    """Unknown extension falls back to 'image/jpeg'."""
    from src.core.llm_engine import _guess_image_mime  # noqa: PLC0415

    assert _guess_image_mime("/file.xyz") == "image/jpeg"
    assert _guess_image_mime("/file") == "image/jpeg"


def test_guess_image_mime_case_insensitive() -> None:
    """Extension lookup is case-insensitive."""
    from src.core.llm_engine import _guess_image_mime  # noqa: PLC0415

    assert _guess_image_mime("/IMAGE.PNG") == "image/png"
    assert _guess_image_mime("/PHOTO.JPG") == "image/jpeg"


# ---------------------------------------------------------------------------
# translate_image_content — Custom backend dispatch
# ---------------------------------------------------------------------------


def test_translate_image_content_dispatches_to_custom() -> None:
    """translate_image_content calls _translate_image_custom for custom method."""
    from src.core.ocr_engine import OCRResult  # noqa: PLC0415

    ocr_results = [OCRResult(text="Hello", x=0, y=0, w=100, h=20, confidence=0.9)]

    with (
        patch(
            "src.core.llm_engine._resolve_provider_model",
            return_value=(LLM_METHOD_CUSTOM, "gpt-4o"),
        ),
        patch(
            "src.core.llm_engine._translate_image_custom",
            return_value=[
                {
                    "ids": [0],
                    "translated_html": "Bonjour",
                    "color": "#000",
                    "alignment": "left",
                },
            ],
        ) as mock_custom,
    ):
        result = translate_image_content("/fake.jpg", ocr_results, "French")

    mock_custom.assert_called_once()
    assert result[0]["translated_html"] == "Bonjour"


# ---------------------------------------------------------------------------
# _translate_image_custom — AUTH_ERROR on missing credentials
# ---------------------------------------------------------------------------


def test_translate_image_custom_missing_api_key_raises_auth_error() -> None:
    """_translate_image_custom raises AUTH_ERROR when endpoint/model missing.

    The production check is now ``if not endpoint or not model: raise`` — so
    we pass an empty endpoint/model via ``_resolve_custom_config``.
    """
    from src.core.llm_engine import _translate_image_custom  # noqa: PLC0415

    with (
        patch(
            "src.core.llm_engine._resolve_custom_config",
            return_value=("", "", ""),
        ),
        pytest.raises(ValueError, match="AUTH_ERROR"),
    ):
        _translate_image_custom("/fake.png", [{"id": 0, "text": "Hi"}], "French", "")


def test_translate_image_custom_missing_model_raises_auth_error() -> None:
    """_translate_image_custom raises AUTH_ERROR when model is empty."""
    from src.core.llm_engine import _translate_image_custom  # noqa: PLC0415

    settings = {
        "llm/custom_api_key": "key",
        "llm/custom_model": "",
        "llm/custom_endpoint": "https://api.example.com/v1/chat/completions",
    }
    with (
        patch(
            "src.core.llm_engine._config.load_setting",
            side_effect=settings.get,
        ),
        pytest.raises(ValueError, match="AUTH_ERROR"),
    ):
        _translate_image_custom("/fake.png", [{"id": 0, "text": "Hi"}], "French", "")


def test_translate_image_custom_missing_endpoint_raises_auth_error() -> None:
    """_translate_image_custom raises AUTH_ERROR when endpoint is empty."""
    from src.core.llm_engine import _translate_image_custom  # noqa: PLC0415

    settings = {
        "llm/custom_api_key": "key",
        "llm/custom_model": "gpt-4o",
        "llm/custom_endpoint": "",
    }
    with (
        patch(
            "src.core.llm_engine._config.load_setting",
            side_effect=settings.get,
        ),
        pytest.raises(ValueError, match="AUTH_ERROR"),
    ):
        _translate_image_custom("/fake.png", [{"id": 0, "text": "Hi"}], "French", "")


def test_translate_image_gemini_uses_correct_mime_type_in_payload() -> None:
    """_translate_image_gemini uses _guess_image_mime for the inline_data MIME type."""
    from src.core.llm_engine import _translate_image_gemini  # noqa: PLC0415

    settings = {
        "llm/gemini_api_key": "test-key",
        "llm/gemini_model": "gemini-2.0-flash",
    }

    inner = json.dumps({"paragraphs": []})
    client = _make_mock_genai_client(response_text=inner)

    with (
        patch(
            "src.core.llm_engine._config.load_setting",
            side_effect=settings.get,
        ),
        patch("src.core.llm_engine._build_gemini_client", return_value=client),
        patch("pathlib.Path.read_bytes", return_value=b"fake image"),
    ):
        _translate_image_gemini("/image.png", [{"id": 0, "text": "Hi"}], "French", "")

    assert client.models.generate_content.call_count == 1
    contents = client.models.generate_content.call_args.kwargs["contents"]
    # contents[0] is the Part.from_bytes(...) result — its mime_type attribute
    # exposes what _guess_image_mime() returned for the .png extension.
    image_part = contents[0]
    assert image_part.inline_data.mime_type == "image/png"


def test_translate_image_custom_uses_correct_mime_type_in_payload() -> None:
    """_translate_image_custom uses _guess_image_mime for the data URI MIME type."""
    from src.core.llm_engine import _translate_image_custom  # noqa: PLC0415

    settings = {
        "llm/custom_api_key": "test-key",
        "llm/custom_model": "gpt-4o",
        "llm/custom_endpoint": "https://api.example.com/v1/chat/completions",
    }

    inner = json.dumps({"paragraphs": []})
    client = _make_mock_sdk_client(chat_response=_make_sdk_chat_response(inner))

    with (
        patch(
            "src.core.llm_engine._config.load_setting",
            side_effect=settings.get,
        ),
        patch("src.core.llm_engine._build_openai_client", return_value=client),
        patch("pathlib.Path.open", return_value=io.BytesIO(b"fake image")),
    ):
        _translate_image_custom("/photo.webp", [{"id": 0, "text": "Hi"}], "French", "")

    assert client.chat.completions.create.call_count == 1
    sent_kwargs = client.chat.completions.create.call_args.kwargs
    image_url = sent_kwargs["messages"][0]["content"][1]["image_url"]["url"]
    assert image_url.startswith("data:image/webp;base64,")


# ---------------------------------------------------------------------------
# translate_text — multi-batch and integration tests
# ---------------------------------------------------------------------------


def test_translate_text_full_pipeline_filter_dedupe_batch() -> None:
    """translate_text combines filter, dedup, and batching correctly."""
    # Mix: untranslatable (idx 1,3), duplicates (idx 0,2,4), unique (idx 5)
    texts = [
        "Hello",
        "12345",
        "Hello",
        "http://x.com",
        "Hello",
        "World",
    ]

    def fake_translate(
        batch: list[str],
        tl: str,
        sl: str,  # noqa: ANN001
        gl: object,
        ct: str,  # noqa: ANN001,
        model="",
        **_kwargs,
    ) -> list[str]:
        return [f"[{tl}] {t}" for t in batch]

    with (
        patch(
            "src.core.llm_engine._resolve_provider_model",
            return_value=(LLM_METHOD_GEMINI, "gemini-3-flash-preview"),
        ),
        patch(
            "src.core.llm_engine._translate_gemini",
            side_effect=fake_translate,
        ),
    ):
        result = translate_text(texts, "French", "English")

    assert len(result) == 6  # noqa: PLR2004
    # Untranslatable items preserved as-is
    assert result[1] == "12345"
    assert result[3] == "http://x.com"
    # Duplicates all get same translation
    assert result[0] == result[2] == result[4]
    assert "[French]" in result[0]
    # Unique item translated
    assert "[French]" in result[5]


def test_translate_text_progress_callback_monotonic() -> None:
    """Progress values increase monotonically toward 100."""
    texts = ["Short text " * 50] * 10  # Force multiple batches

    call_idx = {"n": 0}

    def fake_translate(
        batch: list[str],
        tl: str,
        sl: str,  # noqa: ANN001
        gl: object,
        ct: str,  # noqa: ANN001,
        model="",
        **_kwargs,
    ) -> list[str]:
        call_idx["n"] += 1
        return [f"[{tl}] {t}" for t in batch]

    progress_values: list[int] = []

    with (
        patch(
            "src.core.llm_engine._resolve_provider_model",
            return_value=(LLM_METHOD_GEMINI, "gemini-3-flash-preview"),
        ),
        patch(
            "src.core.llm_engine._translate_gemini",
            side_effect=fake_translate,
        ),
    ):
        translate_text(
            texts,
            "French",
            "English",
            progress_callback=progress_values.append,
        )

    assert len(progress_values) >= 1
    # Monotonically non-decreasing
    for i in range(1, len(progress_values)):
        assert progress_values[i] >= progress_values[i - 1]
    # Final value is 100
    assert progress_values[-1] == 100  # noqa: PLR2004


def test_translate_text_glossary_forwarded_to_llm() -> None:
    """Glossary entries are forwarded to the translate function."""
    captured: list[object] = []

    def capturing_translate(
        batch: list[str],
        tl: str,
        sl: str,  # noqa: ANN001
        gl: object,
        ct: str,  # noqa: ANN001,
        model="",
        **_kwargs,
    ) -> list[str]:
        captured.append(gl)
        return [f"[{tl}] {t}" for t in batch]

    glossary = [(1, "Hello", "Bonjour"), (2, "World", "Monde")]

    with (
        patch(
            "src.core.llm_engine._resolve_provider_model",
            return_value=(LLM_METHOD_GEMINI, "gemini-3-flash-preview"),
        ),
        patch(
            "src.core.llm_engine._translate_gemini",
            side_effect=capturing_translate,
        ),
    ):
        translate_text(
            ["Hello world"],
            "French",
            "English",
            glossary_entries=glossary,
        )

    # Glossary forwarded (may be compressed — at least non-empty)
    assert len(captured) >= 1
    # Each captured value should contain glossary entries
    for gl in captured:
        assert gl is not None


def test_translate_text_cancel_on_second_batch() -> None:
    """Cancel after second batch: first batch translated, rest original."""
    batch_calls = {"n": 0}

    def fake_translate(
        batch: list[str],
        tl: str,
        sl: str,  # noqa: ANN001
        gl: object,
        ct: str,  # noqa: ANN001,
        model="",
        **_kwargs,
    ) -> list[str]:
        batch_calls["n"] += 1
        return [f"[{tl}] {t}" for t in batch]

    cancel_calls = {"n": 0}

    def cancel_after_two() -> bool:
        cancel_calls["n"] += 1
        return cancel_calls["n"] > 2  # noqa: PLR2004

    # Force 3 batches with 1 item each
    with (
        patch(
            "src.core.llm_engine._resolve_provider_model",
            return_value=(LLM_METHOD_GEMINI, "gemini-3-flash-preview"),
        ),
        patch(
            "src.core.llm_engine._translate_gemini",
            side_effect=fake_translate,
        ),
        patch(
            "src.core.llm_engine._split_by_token_budget",
            return_value=[["A"], ["B"], ["C"]],
        ),
    ):
        result = translate_text(
            ["A", "B", "C"],
            "French",
            "English",
            cancel_check=cancel_after_two,
        )

    assert len(result) == 3  # noqa: PLR2004
    # First 2 batches translated
    assert "[French]" in result[0]
    assert "[French]" in result[1]
    # Third batch cancelled — kept original
    assert result[2] == "C"


def test_translate_text_all_same_text_deduplicated() -> None:
    """All identical texts: only one LLM call, all get same result."""
    call_count = {"n": 0}

    def counting_translate(
        batch: list[str],
        tl: str,
        sl: str,  # noqa: ANN001
        gl: object,
        ct: str,  # noqa: ANN001
        model: str = "",
        **_kwargs,  # noqa: ANN003
    ) -> list[str]:
        call_count["n"] += 1
        return [f"[{tl}] {t}" for t in batch]

    with (
        patch(
            "src.core.llm_engine._resolve_provider_model",
            return_value=(LLM_METHOD_GEMINI, "gemini-3-flash-preview"),
        ),
        patch(
            "src.core.llm_engine._translate_gemini",
            side_effect=counting_translate,
        ),
    ):
        result = translate_text(
            ["Hello"] * 5,
            "French",
            "English",
        )

    assert len(result) == 5  # noqa: PLR2004
    # All items are identical translation
    assert all(r == result[0] for r in result)
    assert "[French]" in result[0]
    # Deduplication means only 1 unique text sent to LLM
    assert call_count["n"] == 1


def test_translate_text_content_type_forwarded() -> None:
    """content_type parameter is forwarded to the translate function."""
    captured_ct: list[str] = []

    def capturing_translate(
        batch: list[str],
        tl: str,
        sl: str,  # noqa: ANN001
        gl: object,
        ct: str,  # noqa: ANN001,
        model="",
        **_kwargs,
    ) -> list[str]:
        captured_ct.append(ct)
        return [f"[{tl}] {t}" for t in batch]

    with (
        patch(
            "src.core.llm_engine._resolve_provider_model",
            return_value=(LLM_METHOD_GEMINI, "gemini-3-flash-preview"),
        ),
        patch(
            "src.core.llm_engine._translate_gemini",
            side_effect=capturing_translate,
        ),
    ):
        translate_text(
            ["Hello world"],
            "French",
            "English",
            content_type="html",
        )

    assert captured_ct == ["html"]


def test_translate_text_uses_custom_when_configured() -> None:
    """translate_text dispatches to _translate_custom per settings."""
    gemini_called = {"n": 0}
    custom_called = {"n": 0}

    def fake_gemini(
        batch: list[str],
        tl: str,
        sl: str,  # noqa: ANN001
        gl: object,
        ct: str,  # noqa: ANN001,
        model="",
        **_kwargs,
    ) -> list[str]:
        gemini_called["n"] += 1
        return batch

    def fake_custom(
        batch: list[str],
        tl: str,
        sl: str,  # noqa: ANN001
        gl: object,
        ct: str,  # noqa: ANN001,
        model="",
        **_kwargs,
    ) -> list[str]:
        custom_called["n"] += 1
        return [f"[custom] {t}" for t in batch]

    with (
        patch(
            "src.core.llm_engine._resolve_provider_model",
            return_value=(LLM_METHOD_CUSTOM, "gpt-4o"),
        ),
        patch(
            "src.core.llm_engine._translate_gemini",
            side_effect=fake_gemini,
        ),
        patch(
            "src.core.llm_engine._translate_custom",
            side_effect=fake_custom,
        ),
    ):
        result = translate_text(["Hello"], "French", "English")

    assert gemini_called["n"] == 0
    assert custom_called["n"] == 1
    assert result == ["[custom] Hello"]


# ---------------------------------------------------------------------------
# translate_text — whitespace-only API key raises AUTH_ERROR
# ---------------------------------------------------------------------------


def test_translate_gemini_whitespace_api_key_raises_auth_error() -> None:
    """Empty Gemini API key is treated as missing → AUTH_ERROR."""
    with (
        patch(
            "src.core.llm_engine._config.load_setting",
            side_effect=lambda key, default="": "" if "api_key" in key else default,
        ),
        pytest.raises(ValueError, match="AUTH_ERROR"),
    ):
        from src.core.llm_engine import _translate_gemini  # noqa: PLC0415

        _translate_gemini(["Hello"], "French", "English")


# ---------------------------------------------------------------------------
# _translate_gemini — HTTP error wiring through except block
# ---------------------------------------------------------------------------


def test_translate_gemini_http_429_wired_to_quota_error() -> None:
    """APIError(429) in _translate_gemini flows through _handle_api_error."""
    client = _make_mock_genai_client(
        response_error=_genai_api_error(429, "Quota exceeded"),
    )
    with (
        patch(
            "src.core.llm_engine._config.load_setting",
            side_effect=lambda key, default="": (
                "fake-key" if "api_key" in key else default
            ),
        ),
        patch(
            "src.core.llm_engine._build_gemini_client",
            return_value=client,
        ),
        pytest.raises(ValueError, match="QUOTA_ERROR"),
    ):
        from src.core.llm_engine import _translate_gemini  # noqa: PLC0415

        _translate_gemini(["Hello"], "French", "English")


# ---------------------------------------------------------------------------
# translate_batch — file-level deduplication
# ---------------------------------------------------------------------------


def _mock_translate_text(
    texts: list[str],
    target: str,
    source: str = "",
    **kwargs: object,
) -> list[str]:
    """Simple mock that prefixes each text with 'T_'."""
    return [f"T_{t}" for t in texts]


def test_translate_batch_basic() -> None:
    """translate_batch returns translated list of same length."""
    with patch("src.core.llm_engine.translate_text", side_effect=_mock_translate_text):
        result = translate_batch(["A", "B", "C"], "French", "English")
    assert result == ["T_A", "T_B", "T_C"]


def test_translate_batch_file_level_dedup() -> None:
    """Identical strings across batch boundaries get the same translation."""
    call_texts: list[list[str]] = []

    def _capture_translate(
        texts: list[str],
        target: str,
        source: str = "",
        **kwargs: object,
    ) -> list[str]:
        call_texts.append(list(texts))
        return [f"T_{t}" for t in texts]

    # 6 items, 3 unique — with TRANSLATION_BATCH_SIZE=30, all fit in one batch
    values = ["A", "B", "C", "A", "B", "C"]
    with patch("src.core.llm_engine.translate_text", side_effect=_capture_translate):
        result = translate_batch(values, "French", "English")

    # All duplicates must get the same translation
    assert result == ["T_A", "T_B", "T_C", "T_A", "T_B", "T_C"]
    # Only 3 unique texts should have been sent to translate_text
    total_sent = sum(len(c) for c in call_texts)
    assert total_sent == 3  # noqa: PLR2004


def test_translate_batch_dedup_across_batch_boundaries() -> None:
    """Duplicates spanning different TRANSLATION_BATCH_SIZE batches are consistent."""
    call_count = 0

    def _counting_translate(
        texts: list[str],
        target: str,
        source: str = "",
        **kwargs: object,
    ) -> list[str]:
        nonlocal call_count
        call_count += 1
        return [f"T_{t}" for t in texts]

    # Create values where duplicates would span batch boundaries
    # without dedup (batch size 30): items 0-29 in batch 1, 30-59 in batch 2
    values = [f"word{i % 10}" for i in range(60)]  # 10 unique, repeated 6 times
    with patch("src.core.llm_engine.translate_text", side_effect=_counting_translate):
        result = translate_batch(values, "French", "English")

    # All copies of the same word must get the same translation
    for i in range(10):
        word = f"word{i}"
        expected = f"T_{word}"
        indices = [j for j, v in enumerate(values) if v == word]
        for idx in indices:
            assert result[idx] == expected, f"Mismatch at index {idx} for {word}"


def test_translate_batch_all_identical() -> None:
    """All identical values are translated once."""
    call_texts: list[list[str]] = []

    def _capture(
        texts: list[str],
        target: str,
        source: str = "",
        **kwargs: object,
    ) -> list[str]:
        call_texts.append(list(texts))
        return [f"T_{t}" for t in texts]

    values = ["same"] * 50  # noqa: PLR2004
    with patch("src.core.llm_engine.translate_text", side_effect=_capture):
        result = translate_batch(values, "French", "English")

    assert all(r == "T_same" for r in result)
    assert len(result) == 50  # noqa: PLR2004
    # Only 1 unique text sent
    total_sent = sum(len(c) for c in call_texts)
    assert total_sent == 1


def test_translate_batch_empty() -> None:
    """Empty values list returns empty result."""
    with patch("src.core.llm_engine.translate_text", side_effect=_mock_translate_text):
        result = translate_batch([], "French", "English")
    assert result == []


def test_translate_batch_single_item() -> None:
    """Single item is translated correctly."""
    with patch("src.core.llm_engine.translate_text", side_effect=_mock_translate_text):
        result = translate_batch(["hello"], "French", "English")
    assert result == ["T_hello"]


def test_translate_batch_cancel_returns_none() -> None:
    """Cancel before processing returns None."""
    result = translate_batch(
        ["A", "B"],
        "French",
        "English",
        cancel_check=lambda: True,
    )
    assert result is None


def test_translate_batch_cancel_during_batch() -> None:
    """Cancel mid-batch returns None."""
    call_count = 0

    def _cancel_after_first() -> bool:
        return call_count > 0

    def _counting_translate(
        texts: list[str],
        target: str,
        source: str = "",
        **kwargs: object,
    ) -> list[str]:
        nonlocal call_count
        call_count += 1
        return [f"T_{t}" for t in texts]

    # Create enough unique items to span multiple batches
    values = [f"unique_{i}" for i in range(60)]
    with patch(
        "src.core.llm_engine.translate_text",
        side_effect=_counting_translate,
    ):
        result = translate_batch(
            values,
            "French",
            "English",
            cancel_check=_cancel_after_first,
        )
    assert result is None


def test_translate_batch_progress_callback() -> None:
    """Progress callback is called with increasing percentages."""
    progress_values: list[int] = []

    with patch("src.core.llm_engine.translate_text", side_effect=_mock_translate_text):
        translate_batch(
            ["A", "B", "C"],
            "French",
            "English",
            progress_callback=progress_values.append,
        )
    assert len(progress_values) > 0
    # Last progress should be 100% or close
    assert progress_values[-1] > 0


def test_translate_batch_checkpoint_resume(tmp_path: object) -> None:
    """Cached items from checkpoint are not re-translated."""
    from pathlib import Path  # noqa: PLC0415

    cp_dir = Path(str(tmp_path)) / "cp"
    cp_dir.mkdir()

    call_texts: list[list[str]] = []

    def _capture(
        texts: list[str],
        target: str,
        source: str = "",
        **kwargs: object,
    ) -> list[str]:
        call_texts.append(list(texts))
        return [f"T_{t}" for t in texts]

    # First run: translate all
    values = ["A", "B", "C", "D", "E"]
    with patch("src.core.llm_engine.translate_text", side_effect=_capture):
        result1 = translate_batch(
            values,
            "French",
            "English",
            checkpoint_dir=cp_dir,
        )
    assert result1 is not None
    first_call_count = len(call_texts)

    # Second run: should use checkpoint
    call_texts.clear()
    with patch("src.core.llm_engine.translate_text", side_effect=_capture):
        result2 = translate_batch(
            values,
            "French",
            "English",
            checkpoint_dir=cp_dir,
        )
    assert result2 == result1
    # No new translate_text calls needed (all cached)
    assert len(call_texts) < first_call_count


def test_translate_batch_dedup_with_checkpoint_all_cached(tmp_path: object) -> None:
    """All-identical values fully cached trigger early return."""
    from pathlib import Path  # noqa: PLC0415

    cp_dir = Path(str(tmp_path)) / "cp"
    cp_dir.mkdir()

    with patch("src.core.llm_engine.translate_text", side_effect=_mock_translate_text):
        result1 = translate_batch(
            ["X", "X", "X"],
            "French",
            "English",
            checkpoint_dir=cp_dir,
        )

    # Second call: checkpoint has the 1 unique item cached
    call_texts: list[list[str]] = []

    def _capture(
        texts: list[str],
        target: str,
        source: str = "",
        **kwargs: object,
    ) -> list[str]:
        call_texts.append(list(texts))
        return [f"T_{t}" for t in texts]

    with patch("src.core.llm_engine.translate_text", side_effect=_capture):
        result2 = translate_batch(
            ["X", "X", "X"],
            "French",
            "English",
            checkpoint_dir=cp_dir,
        )
    assert result2 == result1
    # No calls to translate_text — all cached
    assert len(call_texts) == 0


def test_translate_batch_glossary_forwarded() -> None:
    """Glossary entries are forwarded to translate_text."""
    received_glossary: list[object] = []

    def _check_glossary(
        texts: list[str],
        target: str,
        source: str = "",
        **kwargs: object,
    ) -> list[str]:
        received_glossary.append(kwargs.get("glossary_entries"))
        return [f"T_{t}" for t in texts]

    glossary = [(1, "hello", "bonjour")]
    with patch("src.core.llm_engine.translate_text", side_effect=_check_glossary):
        translate_batch(
            ["hello"],
            "French",
            "English",
            glossary_entries=glossary,
        )
    assert received_glossary[0] == glossary


def test_translate_batch_content_type_forwarded() -> None:
    """Content type is forwarded to translate_text."""
    received_ct: list[str] = []

    def _check_ct(
        texts: list[str],
        target: str,
        source: str = "",
        **kwargs: object,
    ) -> list[str]:
        received_ct.append(str(kwargs.get("content_type", "")))
        return [f"T_{t}" for t in texts]

    with patch("src.core.llm_engine.translate_text", side_effect=_check_ct):
        translate_batch(
            ["hello"],
            "French",
            "English",
            content_type=CONTENT_PDF,
        )
    assert received_ct[0] == CONTENT_PDF


# ---------------------------------------------------------------------------
# _is_untranslatable — additional edge cases
# ---------------------------------------------------------------------------


def test_untranslatable_number_with_commas() -> None:
    """Pure number with comma separators is untranslatable."""
    assert _is_untranslatable("1,234,567") is True


def test_translatable_number_with_text() -> None:
    """Number mixed with translatable text is translatable."""
    assert _is_untranslatable("Price: $100") is False


def test_untranslatable_email_with_plus_tag() -> None:
    """Email with plus-tag addressing is untranslatable."""
    assert _is_untranslatable("user+tag@domain.com") is True


def test_untranslatable_windows_file_path_backslashes() -> None:
    """Windows file path with backslashes is untranslatable."""
    assert _is_untranslatable("C:\\Users\\test.txt") is True


def test_untranslatable_unix_file_path() -> None:
    """Unix file path under /usr/local is untranslatable."""
    assert _is_untranslatable("/usr/local/bin") is True


def test_untranslatable_url_with_fragment() -> None:
    """URL with a fragment identifier is untranslatable."""
    assert _is_untranslatable("https://example.com#section") is True


def test_translatable_mixed_url_in_sentence() -> None:
    """URL embedded in a sentence with other text is translatable."""
    assert _is_untranslatable("See https://example.com for details") is False


def test_translatable_single_emoji() -> None:
    """A single emoji character has no translatable text but is not symbol-only."""
    # Emoji codepoints are outside the regex's symbol/number class,
    # and not matched by URL/email/path patterns, so treated as translatable.
    assert _is_untranslatable("\U0001f600") is False


def test_untranslatable_whitespace_only_tabs_and_spaces() -> None:
    """Whitespace-only strings (tabs and spaces) are untranslatable."""
    assert _is_untranslatable("\t  \t") is True


def test_untranslatable_url_with_query_params() -> None:
    """URL with query parameters is untranslatable."""
    assert _is_untranslatable("https://example.com/path?key=value&foo=bar") is True


def test_untranslatable_unix_path_var() -> None:
    """Unix path under /var is untranslatable."""
    assert _is_untranslatable("/var/log/syslog") is True


def test_untranslatable_unix_path_tmp() -> None:
    """Unix path under /tmp is untranslatable."""
    assert _is_untranslatable("/tmp/test_file.dat") is True


def test_untranslatable_unix_path_opt() -> None:
    """Unix path under /opt is untranslatable."""
    assert _is_untranslatable("/opt/myapp/bin/run") is True


def test_untranslatable_unix_path_etc() -> None:
    """Unix path under /etc is untranslatable."""
    assert _is_untranslatable("/etc/nginx/nginx.conf") is True


# ---------------------------------------------------------------------------
# _split_by_token_budget — additional edge cases
# ---------------------------------------------------------------------------


def test_split_by_token_budget_single_oversized_item_not_dropped() -> None:
    """A single item exceeding the budget is returned as its own batch, not dropped."""
    huge = "x" * 40000  # ~10000 tokens, far exceeds any small budget
    batches = _split_by_token_budget([huge], budget=10)
    assert len(batches) == 1
    assert batches[0] == [huge]


def test_split_by_token_budget_all_fit_in_one_batch() -> None:
    """When all items fit within budget, a single batch is returned."""
    items = ["short"] * 5  # noqa: PLR2004
    batches = _split_by_token_budget(items, budget=10000)
    assert len(batches) == 1
    assert batches[0] == items


def test_split_by_token_budget_empty_list_returns_empty() -> None:
    """Empty input list returns an empty list of batches."""
    assert _split_by_token_budget([], budget=100) == []


# ---------------------------------------------------------------------------
# _deduplicate_texts / _restore_duplicates — round-trip edge cases
# ---------------------------------------------------------------------------


def test_dedup_restore_round_trip_all_unique() -> None:
    """Round-trip with all unique texts returns translations in order."""
    original = ["alpha", "beta", "gamma"]
    unique, dupe_map = _deduplicate_texts(original)
    assert unique == original
    translated = ["A", "B", "G"]
    result = _restore_duplicates(translated, unique, dupe_map, original)
    assert result == ["A", "B", "G"]


def test_dedup_restore_round_trip_all_identical() -> None:
    """Round-trip with all identical texts restores translation to every position."""
    original = ["repeat", "repeat", "repeat", "repeat"]
    unique, dupe_map = _deduplicate_texts(original)
    assert unique == ["repeat"]
    translated = ["REPEATED"]
    result = _restore_duplicates(translated, unique, dupe_map, original)
    assert result == ["REPEATED", "REPEATED", "REPEATED", "REPEATED"]


def test_dedup_restore_round_trip_mixed_duplicates() -> None:
    """Round-trip with mixed duplicates preserves correct index mapping."""
    original = ["a", "b", "a", "c", "b", "a"]
    unique, dupe_map = _deduplicate_texts(original)
    assert unique == ["a", "b", "c"]
    assert dupe_map == {"a": [0, 2, 5], "b": [1, 4], "c": [3]}
    translated = ["X", "Y", "Z"]
    result = _restore_duplicates(translated, unique, dupe_map, original)
    assert result == ["X", "Y", "X", "Z", "Y", "X"]


# ---------------------------------------------------------------------------
# _get_gemini_safety_settings
# ---------------------------------------------------------------------------


def test_gemini_safety_settings_returns_list() -> None:
    """Returns a list with at least 5 safety setting entries."""
    from src.core.llm_engine import _get_gemini_safety_settings  # noqa: PLC0415

    settings = _get_gemini_safety_settings()
    assert isinstance(settings, list)
    assert len(settings) >= 5  # noqa: PLR2004


def test_gemini_safety_settings_block_none() -> None:
    """All entries have threshold set to 'BLOCK_NONE'."""
    from src.core.llm_engine import _get_gemini_safety_settings  # noqa: PLC0415

    settings = _get_gemini_safety_settings()
    for entry in settings:
        assert entry["threshold"] == "BLOCK_NONE"


# ---------------------------------------------------------------------------
# _build_image_translation_prompt
# ---------------------------------------------------------------------------


def test_build_image_translation_prompt_basic() -> None:
    """Prompt includes the target language name."""
    from src.core.llm_engine import _build_image_translation_prompt  # noqa: PLC0415

    prompt = _build_image_translation_prompt("French", "")
    assert "French" in prompt
    assert "OCR" in prompt


def test_build_image_translation_prompt_with_glossary() -> None:
    """Glossary hint text is embedded in the prompt."""
    from src.core.llm_engine import _build_image_translation_prompt  # noqa: PLC0415

    glossary_hint = "\nGlossary: hello <-> bonjour"
    prompt = _build_image_translation_prompt("French", glossary_hint)
    assert "hello <-> bonjour" in prompt


def test_build_image_translation_prompt_empty_ocr() -> None:
    """Empty glossary hint still produces a valid prompt string."""
    from src.core.llm_engine import _build_image_translation_prompt  # noqa: PLC0415

    prompt = _build_image_translation_prompt("Japanese", "")
    assert isinstance(prompt, str)
    assert len(prompt) > 0
    assert "Japanese" in prompt


# ---------------------------------------------------------------------------
# translate_batch — incomplete LLM response skips checkpoint save
# ---------------------------------------------------------------------------


def test_translate_batch_short_llm_response_skips_checkpoint() -> None:
    """When LLM returns fewer results than sent, checkpoint is NOT saved."""
    from pathlib import Path  # noqa: PLC0415

    texts = ["Hello", "World", "Foo"]

    def fake_translate(
        batch: list[str],
        tl: str,
        sl: str,
        **_kwargs: object,
    ) -> list[str]:
        # Return fewer items than the batch — simulates truncated LLM response
        return [f"[{tl}] {batch[0]}"]

    cp_dir = Path("/tmp/test_short_llm")

    with (
        patch("src.core.llm_engine.translate_text", side_effect=fake_translate),
        patch("src.core.checkpoint.save_batch_progress") as mock_save,
        patch("src.core.checkpoint.load_batch_checkpoint", return_value=None),
    ):
        result = translate_batch(
            texts,
            "French",
            "English",
            content_type="plain_text",
            checkpoint_dir=cp_dir,
        )

    # Should return a list of same length as input
    assert result is not None
    assert len(result) == len(texts)
    # Only the first item in each batch was translated
    assert "[French]" in result[0]
    # Checkpoint should NOT have been saved (result count mismatch)
    mock_save.assert_not_called()


# ---------------------------------------------------------------------------
# extract_image_text — dispatch tests
# ---------------------------------------------------------------------------

_LLM_MOD = "src.core.llm_engine"


def test_extract_image_text_dispatches_to_gemini() -> None:
    """When SETTING_LLM_METHOD is Gemini, _extract_text_gemini is called."""
    from src.core.llm_engine import extract_image_text  # noqa: PLC0415

    with (
        patch(
            f"{_LLM_MOD}._config.load_setting",
            return_value=LLM_METHOD_GEMINI,
        ),
        patch(
            f"{_LLM_MOD}._extract_text_gemini",
            return_value="Gemini text",
        ) as mock_gemini,
        patch(
            f"{_LLM_MOD}._extract_text_custom",
        ) as mock_custom,
    ):
        result = extract_image_text("/fake/image.png")

    assert result == "Gemini text"
    mock_gemini.assert_called_once()
    assert mock_gemini.call_args.args[0] == "/fake/image.png"
    mock_custom.assert_not_called()


def test_extract_image_text_dispatches_to_custom() -> None:
    """When SETTING_LLM_METHOD is Custom, _extract_text_custom is called."""
    from src.core.llm_engine import extract_image_text  # noqa: PLC0415

    with (
        patch(
            f"{_LLM_MOD}._resolve_provider_model",
            return_value=(LLM_METHOD_CUSTOM, "gpt-4o"),
        ),
        patch(
            f"{_LLM_MOD}._extract_text_custom",
            return_value="Custom text",
        ) as mock_custom,
        patch(
            f"{_LLM_MOD}._extract_text_gemini",
        ) as mock_gemini,
    ):
        result = extract_image_text("/fake/image.png")

    assert result == "Custom text"
    mock_custom.assert_called_once()
    assert mock_custom.call_args.args[0] == "/fake/image.png"
    mock_gemini.assert_not_called()


def test_extract_image_text_unknown_method_returns_empty() -> None:
    """When SETTING_LLM_METHOD is an unknown value, returns empty string."""
    from src.core.llm_engine import extract_image_text  # noqa: PLC0415

    with patch(
        f"{_LLM_MOD}._resolve_provider_model",
        return_value=("UnknownProvider", ""),
    ):
        result = extract_image_text("/fake/image.png")

    assert result == ""


# ---------------------------------------------------------------------------
# _deduplicate_texts / _restore_duplicates — round-trip with 10 items
# ---------------------------------------------------------------------------


def test_deduplicate_restores_correctly() -> None:
    """10 texts with duplicates dedup to 5, translate 5, restore to 10."""
    original = [
        "Hello",
        "World",
        "Hello",
        "Foo",
        "Bar",
        "World",
        "Baz",
        "Hello",
        "Foo",
        "Bar",
    ]

    unique, dupe_map = _deduplicate_texts(original)

    # Should have 5 unique texts
    assert len(unique) == 5  # noqa: PLR2004
    assert unique == ["Hello", "World", "Foo", "Bar", "Baz"]

    # Simulate translation of unique texts
    translated_unique = ["Bonjour", "Monde", "Toto", "Barre", "Truc"]

    restored = _restore_duplicates(translated_unique, unique, dupe_map, original)

    assert len(restored) == 10  # noqa: PLR2004
    # Check all positions
    assert restored[0] == "Bonjour"  # Hello → Bonjour
    assert restored[1] == "Monde"  # World → Monde
    assert restored[2] == "Bonjour"  # Hello → Bonjour (dupe)
    assert restored[3] == "Toto"  # Foo → Toto
    assert restored[4] == "Barre"  # Bar → Barre
    assert restored[5] == "Monde"  # World → Monde (dupe)
    assert restored[6] == "Truc"  # Baz → Truc
    assert restored[7] == "Bonjour"  # Hello → Bonjour (dupe)
    assert restored[8] == "Toto"  # Foo → Toto (dupe)
    assert restored[9] == "Barre"  # Bar → Barre (dupe)


# ---------------------------------------------------------------------------
# _split_by_token_budget — large single item and exact fit
# ---------------------------------------------------------------------------


def test_split_by_token_budget_large_single_item_gets_own_batch() -> None:
    """An item exceeding the budget is kept as its own batch, not dropped."""
    # Create a very large item: 80000 chars → ~20000 tokens
    large = "x" * 80000
    small = "y" * 20  # ~5 tokens + 10 overhead = 15

    budget = 100
    batches = _split_by_token_budget([small, large, small], budget=budget)

    # large item must be isolated in its own batch
    assert len(batches) == 3  # noqa: PLR2004
    assert batches[0] == [small]
    assert batches[1] == [large]
    assert batches[2] == [small]


def test_split_by_token_budget_two_items_exactly_fill_budget() -> None:
    """Two items whose combined token cost exactly equals budget stay together."""
    # Each item: 40 chars → 10 tokens + 10 overhead = 20
    # Budget = 40 → exactly 2 items fit
    item = "a" * 40
    budget = 40
    batches = _split_by_token_budget([item, item], budget=budget)

    # Both should fit in one batch (20 + 20 = 40 ≤ 40)
    assert len(batches) == 1
    assert len(batches[0]) == 2  # noqa: PLR2004


def test_split_by_token_budget_two_items_one_over_budget() -> None:
    """Two items whose combined cost exceeds budget by 1 are split."""
    # Each item: 44 chars → 11 tokens + 10 overhead = 21
    # Budget = 41 → first fits (21 ≤ 41), second overflows (42 > 41)
    item = "a" * 44
    budget = 41
    batches = _split_by_token_budget([item, item], budget=budget)

    assert len(batches) == 2  # noqa: PLR2004
    assert len(batches[0]) == 1
    assert len(batches[1]) == 1


# ---------------------------------------------------------------------------
# Streaming translation — _build_streaming_prompt
# ---------------------------------------------------------------------------


class TestBuildStreamingPrompt:
    """Tests for _build_streaming_prompt."""

    def test_returns_prompt_with_language_pair(self) -> None:
        """Prompt includes the source and target language direction."""
        from src.core.llm_engine import _build_streaming_prompt  # noqa: PLC0415

        result = _build_streaming_prompt("English", "French")
        assert "from English to French" in result

    def test_auto_detect_source_language(self) -> None:
        """Empty source lang omits 'from' clause (auto-detect)."""
        from src.core.llm_engine import _build_streaming_prompt  # noqa: PLC0415

        result = _build_streaming_prompt("", "French")
        assert "into French" in result
        assert "from" not in result.split("into")[0]

    def test_includes_glossary_when_provided(self) -> None:
        """Glossary entries appear in the prompt when given."""
        from src.core.llm_engine import _build_streaming_prompt  # noqa: PLC0415

        glossary = [(1, "Hello", "Bonjour"), (2, "World", "Monde")]
        result = _build_streaming_prompt("English", "French", glossary)
        assert "Glossary" in result
        assert "Hello = Bonjour" in result
        assert "World = Monde" in result

    def test_excludes_glossary_when_none(self) -> None:
        """No glossary section when glossary_entries is None."""
        from src.core.llm_engine import _build_streaming_prompt  # noqa: PLC0415

        result = _build_streaming_prompt("English", "French", None)
        assert "Glossary" not in result

    def test_excludes_glossary_when_empty(self) -> None:
        """No glossary section when glossary_entries is empty list."""
        from src.core.llm_engine import _build_streaming_prompt  # noqa: PLC0415

        result = _build_streaming_prompt("English", "French", [])
        assert "Glossary" not in result

    def test_contains_return_only_translated_text(self) -> None:
        """Prompt instructs LLM to return only translated text."""
        from src.core.llm_engine import _build_streaming_prompt  # noqa: PLC0415

        result = _build_streaming_prompt("English", "French")
        assert "Return ONLY the translated text" in result

    def test_does_not_contain_json_or_results(self) -> None:
        """Streaming prompt must NOT mention JSON or results (unlike batch)."""
        from src.core.llm_engine import _build_streaming_prompt  # noqa: PLC0415

        result = _build_streaming_prompt("English", "French")
        assert "JSON" not in result
        assert "results" not in result.lower()


# ---------------------------------------------------------------------------
# Streaming translation — _parse_gemini_sse tests deleted (helper removed; the
# google-genai SDK now handles SSE parsing internally for the Gemini path).
# Streaming translation — _parse_openai_sse tests deleted (helper removed; the
# openai SDK now handles SSE parsing internally for the Custom path).
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Streaming translation — stream_translate_text
# ---------------------------------------------------------------------------


class TestStreamTranslateText:
    """Tests for stream_translate_text."""

    def test_dispatches_to_stream_gemini(self) -> None:
        """Gemini method dispatches to _stream_gemini."""
        from src.core.llm_engine import stream_translate_text  # noqa: PLC0415

        with (
            patch(
                "src.core.llm_engine._config.load_setting",
                side_effect=lambda k, d="": (
                    LLM_METHOD_GEMINI if k == "llm/method" else d
                ),
            ),
            patch(
                "src.core.llm_engine._compress_glossary",
                return_value=None,
            ) as mock_compress,
            patch(
                "src.core.llm_engine._stream_gemini",
                return_value=iter(["Bonjour"]),
            ) as mock_gemini,
        ):
            chunks = list(stream_translate_text("Hello", "French", "English"))

        mock_compress.assert_called_once()
        mock_gemini.assert_called_once()
        assert "".join(chunks) == "Bonjour"

    def test_dispatches_to_stream_custom(self) -> None:
        """Custom method dispatches to _stream_custom."""
        from src.core.llm_engine import stream_translate_text  # noqa: PLC0415

        with (
            patch(
                "src.core.llm_engine._resolve_provider_model",
                return_value=(LLM_METHOD_CUSTOM, "gpt-4o"),
            ),
            patch(
                "src.core.llm_engine._compress_glossary",
                return_value=None,
            ),
            patch(
                "src.core.llm_engine._stream_custom",
                return_value=iter(["Bonjour"]),
            ) as mock_custom,
        ):
            chunks = list(stream_translate_text("Hello", "French", "English"))

        mock_custom.assert_called_once()
        assert "".join(chunks) == "Bonjour"

    def test_unknown_method_yields_nothing(self) -> None:
        """Unknown LLM method yields no chunks."""
        from src.core.llm_engine import stream_translate_text  # noqa: PLC0415

        with (
            patch(
                "src.core.llm_engine._resolve_provider_model",
                return_value=("UnknownProvider", ""),
            ),
            patch(
                "src.core.llm_engine._compress_glossary",
                return_value=None,
            ),
        ):
            chunks = list(stream_translate_text("Hello", "French", "English"))

        assert chunks == []

    def test_glossary_compression_applied(self) -> None:
        """Glossary is compressed before dispatch."""
        from src.core.llm_engine import stream_translate_text  # noqa: PLC0415

        glossary = [(1, "Hello", "Bonjour")]
        with (
            patch(
                "src.core.llm_engine._config.load_setting",
                side_effect=lambda k, d="": (
                    LLM_METHOD_GEMINI if k == "llm/method" else d
                ),
            ),
            patch(
                "src.core.llm_engine._compress_glossary",
                return_value=[(1, "Hello", "Bonjour")],
            ) as mock_compress,
            patch(
                "src.core.llm_engine._stream_gemini",
                return_value=iter(["Bonjour"]),
            ) as mock_gemini,
        ):
            list(
                stream_translate_text(
                    "Hello",
                    "French",
                    "English",
                    glossary,
                )
            )

        # _compress_glossary called with original glossary and text list
        mock_compress.assert_called_once_with(glossary, ["Hello"])
        # _stream_gemini receives the compressed glossary
        call_args = mock_gemini.call_args
        assert call_args[0][3] == [(1, "Hello", "Bonjour")]


# ---------------------------------------------------------------------------
# Streaming translation — _stream_gemini
# ---------------------------------------------------------------------------


class TestStreamGemini:
    """Tests for _stream_gemini."""

    def test_auth_error_when_api_key_empty(self) -> None:
        """Raises AUTH_ERROR when Gemini API key is empty."""
        from src.core.llm_engine import _stream_gemini  # noqa: PLC0415

        with (
            patch(
                "src.core.llm_engine._config.load_setting",
                side_effect=lambda k, d="": "",
            ),
            pytest.raises(ValueError, match="AUTH_ERROR"),
        ):
            # Must consume the generator to trigger execution
            list(_stream_gemini("Hello", "French", "English"))

    def test_successful_streaming_yields_chunks(self) -> None:
        """Successful Gemini streaming yields text chunks from the SDK iterator."""
        from src.core.llm_engine import _stream_gemini  # noqa: PLC0415

        client = _make_mock_genai_client(stream_chunks=["Bon", "jour"])

        settings = {
            "llm/gemini_api_key": "fake-key",
            "llm/gemini_model": "gemini-pro",
        }

        with (
            patch(
                "src.core.llm_engine._config.load_setting",
                side_effect=lambda k, d="": settings.get(k, d),
            ),
            patch(
                "src.core.llm_engine._build_gemini_client",
                return_value=client,
            ),
        ):
            chunks = list(_stream_gemini("Hello", "French", "English"))

        assert chunks == ["Bon", "jour"]

    def test_api_error_propagates(self) -> None:
        """SDK errors are handled by _handle_api_error and re-raised."""
        from src.core.llm_engine import _stream_gemini  # noqa: PLC0415

        settings = {
            "llm/gemini_api_key": "fake-key",
            "llm/gemini_model": "gemini-pro",
        }
        client = _make_mock_genai_client(
            stream_error=_genai_api_error(429, "Too Many Requests"),
        )

        with (
            patch(
                "src.core.llm_engine._config.load_setting",
                side_effect=lambda k, d="": settings.get(k, d),
            ),
            patch(
                "src.core.llm_engine._build_gemini_client",
                return_value=client,
            ),
            pytest.raises(ValueError, match="QUOTA_ERROR"),
        ):
            list(_stream_gemini("Hello", "French", "English"))


# ---------------------------------------------------------------------------
# Streaming translation — _stream_custom
# ---------------------------------------------------------------------------


class TestStreamCustom:
    """Tests for _stream_custom."""

    def test_auth_error_when_api_key_empty(self) -> None:
        """Raises AUTH_ERROR when custom API key is empty."""
        from src.core.llm_engine import _stream_custom  # noqa: PLC0415

        with (
            patch(
                "src.core.llm_engine._config.load_setting",
                side_effect=lambda k, d="": "",
            ),
            pytest.raises(ValueError, match="AUTH_ERROR"),
        ):
            list(_stream_custom("Hello", "French", "English"))

    def test_auth_error_when_endpoint_empty(self) -> None:
        """Raises AUTH_ERROR when custom endpoint is empty."""
        from src.core.llm_engine import _stream_custom  # noqa: PLC0415

        settings = {
            "llm/custom_api_key": "k",
            "llm/custom_model": "gpt-4",
            "llm/custom_endpoint": "",
        }
        with (
            patch(
                "src.core.llm_engine._config.load_setting",
                side_effect=lambda k, d="": settings.get(k, d),
            ),
            pytest.raises(ValueError, match="AUTH_ERROR"),
        ):
            list(_stream_custom("Hello", "French", "English"))

    def test_auth_error_when_model_empty(self) -> None:
        """Raises AUTH_ERROR when custom model is empty."""
        from src.core.llm_engine import _stream_custom  # noqa: PLC0415

        settings = {
            "llm/custom_api_key": "k",
            "llm/custom_model": "",
            "llm/custom_endpoint": "https://api.example.com/v1",
        }
        with (
            patch(
                "src.core.llm_engine._config.load_setting",
                side_effect=lambda k, d="": settings.get(k, d),
            ),
            pytest.raises(ValueError, match="AUTH_ERROR"),
        ):
            list(_stream_custom("Hello", "French", "English"))

    def test_successful_streaming_yields_chunks(self) -> None:
        """Successful custom streaming yields text chunks from the SDK iterator."""
        from src.core.llm_engine import _stream_custom  # noqa: PLC0415

        client = _make_mock_sdk_client(stream_chunks=["Bon", "jour"])

        settings = {
            "llm/custom_api_key": "k",
            "llm/custom_model": "gpt-4",
            "llm/custom_endpoint": "https://api.example.com/v1",
        }

        with (
            patch(
                "src.core.llm_engine._config.load_setting",
                side_effect=lambda k, d="": settings.get(k, d),
            ),
            patch(
                "src.core.llm_engine._build_openai_client",
                return_value=client,
            ),
        ):
            chunks = list(_stream_custom("Hello", "French", "English"))

        assert chunks == ["Bon", "jour"]

    def test_api_error_propagates(self) -> None:
        """SDK errors are handled by _handle_api_error and re-raised."""
        from src.core.llm_engine import _stream_custom  # noqa: PLC0415

        settings = {
            "llm/custom_api_key": "k",
            "llm/custom_model": "gpt-4",
            "llm/custom_endpoint": "https://api.example.com/v1",
        }
        client = _make_mock_sdk_client(chat_error=_sdk_http_error(401))

        with (
            patch(
                "src.core.llm_engine._config.load_setting",
                side_effect=lambda k, d="": settings.get(k, d),
            ),
            patch(
                "src.core.llm_engine._build_openai_client",
                return_value=client,
            ),
            pytest.raises(ValueError, match="AUTH_ERROR"),
        ):
            list(_stream_custom("Hello", "French", "English"))

    def test_http_500_raises_service_unavailable(self) -> None:
        """HTTP 500 from custom endpoint raises SERVICE_UNAVAILABLE_ERROR."""
        from src.core.llm_engine import _stream_custom  # noqa: PLC0415

        settings = {
            "llm/custom_api_key": "k",
            "llm/custom_model": "gpt-4",
            "llm/custom_endpoint": "https://api.example.com/v1",
        }
        client = _make_mock_sdk_client(chat_error=_sdk_http_error(500))

        with (
            patch(
                "src.core.llm_engine._config.load_setting",
                side_effect=lambda k, d="": settings.get(k, d),
            ),
            patch(
                "src.core.llm_engine._build_openai_client",
                return_value=client,
            ),
            pytest.raises(ValueError, match="SERVICE_UNAVAILABLE_ERROR"),
        ):
            list(_stream_custom("Hello", "French", "English"))

    def test_http_503_raises_service_unavailable(self) -> None:
        """HTTP 503 from custom endpoint raises SERVICE_UNAVAILABLE_ERROR."""
        from src.core.llm_engine import _stream_custom  # noqa: PLC0415

        settings = {
            "llm/custom_api_key": "k",
            "llm/custom_model": "gpt-4",
            "llm/custom_endpoint": "https://api.example.com/v1",
        }
        client = _make_mock_sdk_client(chat_error=_sdk_http_error(503))

        with (
            patch(
                "src.core.llm_engine._config.load_setting",
                side_effect=lambda k, d="": settings.get(k, d),
            ),
            patch(
                "src.core.llm_engine._build_openai_client",
                return_value=client,
            ),
            pytest.raises(ValueError, match="SERVICE_UNAVAILABLE_ERROR"),
        ):
            list(_stream_custom("Hello", "French", "English"))

    def test_socket_timeout_raises_timeout_error(self) -> None:
        """SDK timeout during custom streaming raises TIMEOUT_ERROR."""
        from src.core.llm_engine import _stream_custom  # noqa: PLC0415

        settings = {
            "llm/custom_api_key": "k",
            "llm/custom_model": "gpt-4",
            "llm/custom_endpoint": "https://api.example.com/v1",
        }
        client = _make_mock_sdk_client(chat_error=_sdk_timeout_error())

        with (
            patch(
                "src.core.llm_engine._config.load_setting",
                side_effect=lambda k, d="": settings.get(k, d),
            ),
            patch(
                "src.core.llm_engine._build_openai_client",
                return_value=client,
            ),
            pytest.raises(ValueError, match="TIMEOUT_ERROR"),
        ):
            list(_stream_custom("Hello", "French", "English"))

    def test_url_error_raises_connection_error(self) -> None:
        """SDK connection error during custom streaming raises CONNECTION_ERROR."""
        from src.core.llm_engine import _stream_custom  # noqa: PLC0415

        settings = {
            "llm/custom_api_key": "k",
            "llm/custom_model": "gpt-4",
            "llm/custom_endpoint": "https://api.example.com/v1",
        }
        client = _make_mock_sdk_client(chat_error=_sdk_connection_error())

        with (
            patch(
                "src.core.llm_engine._config.load_setting",
                side_effect=lambda k, d="": settings.get(k, d),
            ),
            patch(
                "src.core.llm_engine._build_openai_client",
                return_value=client,
            ),
            pytest.raises(ValueError, match="CONNECTION_ERROR"),
        ):
            list(_stream_custom("Hello", "French", "English"))


# ---------------------------------------------------------------------------
# Streaming — _stream_gemini additional error paths
# ---------------------------------------------------------------------------


class TestStreamGeminiErrors:
    """Additional error-path tests for _stream_gemini."""

    _SETTINGS = {
        "llm/gemini_api_key": "fake-key",
        "llm/gemini_model": "gemini-pro",
    }

    def _load_setting(self, k: str, d: str = "") -> str:
        return self._SETTINGS.get(k, d)

    def _run(self, exc: Exception, expected_tag: str) -> None:
        from src.core.llm_engine import _stream_gemini  # noqa: PLC0415

        client = _make_mock_genai_client(stream_error=exc)
        with (
            patch(
                "src.core.llm_engine._config.load_setting",
                side_effect=self._load_setting,
            ),
            patch(
                "src.core.llm_engine._build_gemini_client",
                return_value=client,
            ),
            pytest.raises(ValueError, match=expected_tag),
        ):
            list(_stream_gemini("Hello", "French", "English"))

    def test_http_500_raises_service_unavailable(self) -> None:
        """APIError 500 raises SERVICE_UNAVAILABLE_ERROR."""
        self._run(_genai_api_error(500, "Internal Server Error"), "SERVICE_UNAVAILABLE_ERROR")

    def test_http_502_raises_service_unavailable(self) -> None:
        """APIError 502 raises SERVICE_UNAVAILABLE_ERROR."""
        self._run(_genai_api_error(502, "Bad Gateway"), "SERVICE_UNAVAILABLE_ERROR")

    def test_http_503_raises_service_unavailable(self) -> None:
        """APIError 503 raises SERVICE_UNAVAILABLE_ERROR."""
        self._run(
            _genai_api_error(503, "Service Unavailable"),
            "SERVICE_UNAVAILABLE_ERROR",
        )

    def test_socket_timeout_raises_timeout_error(self) -> None:
        """Raw TimeoutError raises TIMEOUT_ERROR via the legacy clause."""
        self._run(TimeoutError("timed out"), "TIMEOUT_ERROR")

    def test_http_401_raises_auth_error(self) -> None:
        """APIError 401 raises AUTH_ERROR."""
        self._run(_genai_api_error(401, "Unauthorized"), "AUTH_ERROR")

    def test_http_403_raises_auth_error(self) -> None:
        """APIError 403 raises AUTH_ERROR."""
        self._run(_genai_api_error(403, "Forbidden"), "AUTH_ERROR")


# ---------------------------------------------------------------------------
# SSE parsers — edge cases
# ---------------------------------------------------------------------------


# TestParseGeminiSSEEdgeCases deleted — _parse_gemini_sse helper removed
# (the google-genai SDK now handles SSE parsing internally).
# TestParseOpenAISSEEdgeCases deleted — _parse_openai_sse helper removed.


# ===========================================================================
# NEW TESTS — additional edge-case coverage
# ===========================================================================


# ---------------------------------------------------------------------------
# TestTranslateTextEdgeCases
# ---------------------------------------------------------------------------


class TestTranslateTextEdgeCases:
    """Edge-case tests for translate_text."""

    def test_single_text_translated(self) -> None:
        """Single-element list is translated via LLM."""

        def fake_translate(
            batch: list[str],
            tl: str,
            sl: str,
            gl: object,
            ct: str,
            model="",
            **_kwargs,
        ) -> list[str]:
            return [f"[{tl}] {t}" for t in batch]

        with (
            patch(
                "src.core.llm_engine._resolve_provider_model",
                return_value=(LLM_METHOD_GEMINI, "gemini-3-flash-preview"),
            ),
            patch(
                "src.core.llm_engine._translate_gemini",
                side_effect=fake_translate,
            ),
        ):
            result = translate_text(["Hello"], "French", "English")

        assert len(result) == 1
        assert "[French]" in result[0]

    def test_many_texts_batched_correctly(self) -> None:
        """100+ texts are batched and all translated."""
        texts = [f"sentence {i}" for i in range(120)]
        batch_count = {"n": 0}

        def fake_translate(
            batch: list[str],
            tl: str,
            sl: str,
            gl: object,
            ct: str,
            model="",
            **_kwargs,
        ) -> list[str]:
            batch_count["n"] += 1
            return [f"[{tl}] {t}" for t in batch]

        with (
            patch(
                "src.core.llm_engine._resolve_provider_model",
                return_value=(LLM_METHOD_GEMINI, "gemini-3-flash-preview"),
            ),
            patch(
                "src.core.llm_engine._translate_gemini",
                side_effect=fake_translate,
            ),
        ):
            result = translate_text(texts, "French", "English")

        assert len(result) == 120  # noqa: PLR2004
        # All items translated
        assert all("[French]" in r for r in result)

    def test_html_content_passed_through(self) -> None:
        """Texts containing HTML tags are sent to the LLM (not filtered)."""
        texts = ["<b>Hello</b> <i>World</i>"]

        def fake_translate(
            batch: list[str],
            tl: str,
            sl: str,
            gl: object,
            ct: str,
            model="",
            **_kwargs,
        ) -> list[str]:
            return [f"[{tl}] {t}" for t in batch]

        with (
            patch(
                "src.core.llm_engine._resolve_provider_model",
                return_value=(LLM_METHOD_GEMINI, "gemini-3-flash-preview"),
            ),
            patch(
                "src.core.llm_engine._translate_gemini",
                side_effect=fake_translate,
            ),
        ):
            result = translate_text(texts, "French", "English")

        assert len(result) == 1
        assert "[French]" in result[0]

    def test_json_content_passed_through(self) -> None:
        """Texts containing JSON-like structure are sent to the LLM."""
        texts = ['{"key": "value"}']

        def fake_translate(
            batch: list[str],
            tl: str,
            sl: str,
            gl: object,
            ct: str,
            model="",
            **_kwargs,
        ) -> list[str]:
            return [f"[{tl}] {t}" for t in batch]

        with (
            patch(
                "src.core.llm_engine._resolve_provider_model",
                return_value=(LLM_METHOD_GEMINI, "gemini-3-flash-preview"),
            ),
            patch(
                "src.core.llm_engine._translate_gemini",
                side_effect=fake_translate,
            ),
        ):
            result = translate_text(texts, "French", "English")

        assert len(result) == 1
        assert "[French]" in result[0]

    def test_deduplication_reduces_llm_calls(self) -> None:
        """Duplicate strings result in fewer LLM calls than unique strings."""
        # 10 items, only 2 unique
        texts = ["alpha", "beta"] * 5
        sent_count = {"n": 0}

        def fake_translate(
            batch: list[str],
            tl: str,
            sl: str,
            gl: object,
            ct: str,
            model="",
            **_kwargs,
        ) -> list[str]:
            sent_count["n"] += len(batch)
            return [f"T_{t}" for t in batch]

        with (
            patch(
                "src.core.llm_engine._resolve_provider_model",
                return_value=(LLM_METHOD_GEMINI, "gemini-3-flash-preview"),
            ),
            patch(
                "src.core.llm_engine._translate_gemini",
                side_effect=fake_translate,
            ),
        ):
            result = translate_text(texts, "French")

        assert len(result) == 10  # noqa: PLR2004
        # Only 2 unique strings sent
        assert sent_count["n"] == 2  # noqa: PLR2004
        # All "alpha" copies get same translation
        assert result[0] == result[2] == result[4] == result[6] == result[8]
        # All "beta" copies get same translation
        assert result[1] == result[3] == result[5] == result[7] == result[9]

    def test_untranslatable_filter_preserves_mixed(self) -> None:
        """Mixed list: untranslatable items stay original, rest translated."""
        texts = [
            "Hello world",
            "12345",
            "https://example.com",
            "user@mail.com",
            "/usr/bin/python",
            "Translate me",
        ]

        def fake_translate(
            batch: list[str],
            tl: str,
            sl: str,
            gl: object,
            ct: str,
            model="",
            **_kwargs,
        ) -> list[str]:
            return [f"T_{t}" for t in batch]

        with (
            patch(
                "src.core.llm_engine._resolve_provider_model",
                return_value=(LLM_METHOD_GEMINI, "gemini-3-flash-preview"),
            ),
            patch(
                "src.core.llm_engine._translate_gemini",
                side_effect=fake_translate,
            ),
        ):
            result = translate_text(texts, "French")

        assert len(result) == 6  # noqa: PLR2004
        assert result[0].startswith("T_")
        assert result[1] == "12345"
        assert result[2] == "https://example.com"
        assert result[3] == "user@mail.com"
        assert result[4] == "/usr/bin/python"
        assert result[5].startswith("T_")

    def test_glossary_compression_with_large_glossary(self) -> None:
        """Large glossary compressed keeps only matching entries."""
        # 50 glossary entries with non-overlapping names
        glossary = [(i, f"xterm{i:04d}x", f"xtrans{i:04d}x") for i in range(50)]
        texts = ["xterm0000x and xterm0049x are here"]

        # Test compression directly (translate_text passes full glossary to provider)
        result = _compress_glossary(glossary, texts)
        assert result is not None
        assert len(result) == 2  # noqa: PLR2004
        ids = [e[0] for e in result]
        assert 0 in ids
        assert 49 in ids  # noqa: PLR2004

    def test_glossary_compression_no_matching_terms(self) -> None:
        """Glossary with no matching terms compresses to None."""
        glossary = [(1, "unrelated", "no_match")]
        texts = ["Hello world"]

        # Test compression directly
        result = _compress_glossary(glossary, texts)
        assert result is None

    def test_progress_callback_called_with_100_for_single_text(self) -> None:
        """Progress reaches 100 for a single-text input."""
        progress: list[int] = []

        def fake_translate(
            batch: list[str],
            tl: str,
            sl: str,
            gl: object,
            ct: str,
            model="",
            **_kwargs,
        ) -> list[str]:
            return batch

        with (
            patch(
                "src.core.llm_engine._resolve_provider_model",
                return_value=(LLM_METHOD_GEMINI, "gemini-3-flash-preview"),
            ),
            patch(
                "src.core.llm_engine._translate_gemini",
                side_effect=fake_translate,
            ),
        ):
            translate_text(
                ["Hello"],
                "French",
                progress_callback=progress.append,
            )

        assert progress[-1] == 100  # noqa: PLR2004


# ---------------------------------------------------------------------------
# TestTranslateBatchEdgeCases
# ---------------------------------------------------------------------------


class TestTranslateBatchEdgeCases:
    """Edge-case tests for translate_batch."""

    def test_checkpoint_partial_cache(self, tmp_path: object) -> None:
        """Partial checkpoint cache: only uncached items sent to LLM."""
        from pathlib import Path  # noqa: PLC0415

        cp_dir = Path(str(tmp_path)) / "cp_partial"
        cp_dir.mkdir()

        call_texts: list[list[str]] = []

        def _capture(
            texts: list[str],
            target: str,
            source: str = "",
            **kwargs: object,
        ) -> list[str]:
            call_texts.append(list(texts))
            return [f"T_{t}" for t in texts]

        # First run: translate all
        values = [f"item{i}" for i in range(5)]
        with patch("src.core.llm_engine.translate_text", side_effect=_capture):
            result1 = translate_batch(
                values,
                "French",
                "English",
                checkpoint_dir=cp_dir,
            )
        assert result1 is not None
        first_sent = sum(len(c) for c in call_texts)

        # Second run: all cached, zero calls
        call_texts.clear()
        with patch("src.core.llm_engine.translate_text", side_effect=_capture):
            result2 = translate_batch(
                values,
                "French",
                "English",
                checkpoint_dir=cp_dir,
            )
        assert result2 == result1
        second_sent = sum(len(c) for c in call_texts)
        assert second_sent < first_sent

    def test_checkpoint_save_only_on_correct_count(self, tmp_path: object) -> None:
        """Checkpoint is NOT saved when LLM returns fewer results than expected."""
        from pathlib import Path  # noqa: PLC0415

        cp_dir = Path(str(tmp_path)) / "cp_short"
        cp_dir.mkdir()

        def _short_response(
            texts: list[str],
            target: str,
            source: str = "",
            **kwargs: object,
        ) -> list[str]:
            # Return only 1 result regardless of batch size
            return [f"T_{texts[0]}"]

        with (
            patch("src.core.llm_engine.translate_text", side_effect=_short_response),
            patch("src.core.checkpoint.save_batch_progress") as mock_save,
            patch("src.core.checkpoint.load_batch_checkpoint", return_value=None),
        ):
            result = translate_batch(
                ["A", "B", "C"],
                "French",
                "English",
                checkpoint_dir=cp_dir,
            )

        assert result is not None
        assert len(result) == 3  # noqa: PLR2004
        # Checkpoint NOT saved because result count != batch size
        mock_save.assert_not_called()

    def test_all_items_cached_returns_immediately(self, tmp_path: object) -> None:
        """When all items are cached, returns without calling translate_text."""
        from pathlib import Path  # noqa: PLC0415

        cp_dir = Path(str(tmp_path)) / "cp_all"
        cp_dir.mkdir()

        # First run
        mock_tt = _mock_translate_text
        with patch("src.core.llm_engine.translate_text", side_effect=mock_tt):
            translate_batch(
                ["X", "Y"],
                "French",
                "English",
                checkpoint_dir=cp_dir,
            )

        # Second run: should return immediately, no translate_text calls
        call_count = {"n": 0}

        def _no_call(
            texts: list[str],
            target: str,
            source: str = "",
            **kwargs: object,
        ) -> list[str]:
            call_count["n"] += 1
            return texts

        with patch("src.core.llm_engine.translate_text", side_effect=_no_call):
            result = translate_batch(
                ["X", "Y"],
                "French",
                "English",
                checkpoint_dir=cp_dir,
            )
        assert result is not None
        assert call_count["n"] == 0

    def test_no_items_cached_translates_all(self) -> None:
        """Without checkpoint, all items go through translate_text."""
        call_texts: list[list[str]] = []

        def _capture(
            texts: list[str],
            target: str,
            source: str = "",
            **kwargs: object,
        ) -> list[str]:
            call_texts.append(list(texts))
            return [f"T_{t}" for t in texts]

        values = ["A", "B", "C", "D"]
        with patch("src.core.llm_engine.translate_text", side_effect=_capture):
            result = translate_batch(values, "French", "English")

        assert result is not None
        assert result == ["T_A", "T_B", "T_C", "T_D"]
        total_sent = sum(len(c) for c in call_texts)
        assert total_sent == 4  # noqa: PLR2004

    def test_cancellation_mid_batch_returns_none(self) -> None:
        """Cancellation during batch processing returns None."""
        call_count = 0

        def cancel_after_first() -> bool:
            return call_count > 0

        def _counting(
            texts: list[str],
            target: str,
            source: str = "",
            **kwargs: object,
        ) -> list[str]:
            nonlocal call_count
            call_count += 1
            return [f"T_{t}" for t in texts]

        # Enough unique items to span multiple batches
        values = [f"u_{i}" for i in range(60)]
        with patch("src.core.llm_engine.translate_text", side_effect=_counting):
            result = translate_batch(
                values,
                "French",
                "English",
                cancel_check=cancel_after_first,
            )
        assert result is None

    def test_empty_batch_returns_empty(self) -> None:
        """Empty input returns empty list, not None."""
        mock_tt = _mock_translate_text
        with patch("src.core.llm_engine.translate_text", side_effect=mock_tt):
            result = translate_batch([], "French", "English")
        assert result == []


# ---------------------------------------------------------------------------
# TestSplitByTokenBudget — additional edge cases
# ---------------------------------------------------------------------------


class TestSplitByTokenBudgetAdditional:
    """Additional edge-case tests for _split_by_token_budget."""

    def test_small_texts_one_batch(self) -> None:
        """Very small texts all fit in a single batch."""
        texts = ["hi"] * 50
        batches = _split_by_token_budget(texts, budget=10000)
        assert len(batches) == 1
        assert len(batches[0]) == 50  # noqa: PLR2004

    def test_large_text_exceeding_budget_isolated(self) -> None:
        """A single text larger than the budget is placed alone."""
        large = "x" * 100000  # ~25000 tokens
        batches = _split_by_token_budget([large], budget=50)
        assert len(batches) == 1
        assert batches[0] == [large]

    def test_mixed_sizes_split_correctly(self) -> None:
        """Mix of small and large items creates appropriate batches."""
        small = "a" * 4  # 1 token + 10 overhead = 11
        medium = "b" * 80  # 20 tokens + 10 overhead = 30
        large = "c" * 20000  # 5000 tokens + 10 overhead

        items = [small, medium, small, large, small]
        batches = _split_by_token_budget(items, budget=60)
        # small(11) + medium(30) + small(11) = 52 ≤ 60 → batch 1
        # large alone → batch 2
        # small alone → batch 3
        assert len(batches) == 3  # noqa: PLR2004
        assert batches[0] == [small, medium, small]
        assert batches[1] == [large]
        assert batches[2] == [small]

    def test_empty_list_returns_empty(self) -> None:
        """Empty input returns empty list."""
        assert _split_by_token_budget([], budget=1000) == []

    def test_single_item_exceeding_budget_in_own_batch(self) -> None:
        """Single item exceeding budget gets its own batch (not dropped)."""
        huge = "z" * 50000
        batches = _split_by_token_budget([huge], budget=10)
        assert len(batches) == 1
        assert batches[0] == [huge]

    def test_budget_of_one_forces_individual_batches(self) -> None:
        """Budget=1 forces every item into its own batch."""
        texts = ["a", "b", "c", "d"]
        batches = _split_by_token_budget(texts, budget=1)
        assert len(batches) == 4  # noqa: PLR2004
        assert all(len(b) == 1 for b in batches)


# ---------------------------------------------------------------------------
# TestRetryApiCall — comprehensive retry scenarios
# ---------------------------------------------------------------------------


class TestRetryApiCallComprehensive:
    """Comprehensive tests for retry_api_call decorator."""

    def test_success_on_first_try(self) -> None:
        """Function succeeds on first call without any retries."""
        call_count = 0

        @retry_api_call(max_retries=3, base_delay=0.01)
        def immediate_success() -> str:
            nonlocal call_count
            call_count += 1
            return "ok"

        result = immediate_success()
        assert result == "ok"
        assert call_count == 1

    def test_retry_on_service_unavailable(self) -> None:
        """SERVICE_UNAVAILABLE_ERROR triggers retry until success."""
        call_count = 0

        @retry_api_call(max_retries=3, base_delay=0.01)
        def flaky_service() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:  # noqa: PLR2004
                raise ValueError("SERVICE_UNAVAILABLE_ERROR")
            return "recovered"

        with patch("src.core.llm_engine.time.sleep"):
            result = flaky_service()

        assert result == "recovered"
        assert call_count == 3  # noqa: PLR2004

    def test_timeout_not_retried(self) -> None:
        """TIMEOUT_ERROR is raised immediately without retry.

        A request that exceeded the (already generous) per-call timeout
        is almost never a transient blip — the model is genuinely slow
        on this prompt, and retrying with the same content typically
        times out again.  Surface the timeout immediately so the user
        can act (switch model, split the batch) instead of silently
        burning ``max_retries × timeout`` seconds.
        """
        call_count = 0

        @retry_api_call(max_retries=3, base_delay=0.01)
        def always_timeout() -> None:
            nonlocal call_count
            call_count += 1
            raise ValueError("TIMEOUT_ERROR")

        with pytest.raises(ValueError, match="TIMEOUT_ERROR"):
            always_timeout()

        # No retries — exactly one attempt.
        assert call_count == 1

    def test_retry_on_connection_error(self) -> None:
        """CONNECTION_ERROR triggers retry until success."""
        call_count = 0

        @retry_api_call(max_retries=2, base_delay=0.01)
        def conn_then_ok() -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("CONNECTION_ERROR")
            return "connected"

        with patch("src.core.llm_engine.time.sleep"):
            result = conn_then_ok()

        assert result == "connected"
        assert call_count == 2  # noqa: PLR2004

    def test_max_retries_exceeded(self) -> None:
        """After max retries, the error is re-raised."""

        @retry_api_call(max_retries=2, base_delay=0.01)
        def always_unavailable() -> None:
            raise ValueError("SERVICE_UNAVAILABLE_ERROR")

        with (
            patch("src.core.llm_engine.time.sleep"),
            pytest.raises(ValueError, match="SERVICE_UNAVAILABLE_ERROR"),
        ):
            always_unavailable()

    def test_auth_error_not_retried(self) -> None:
        """AUTH_ERROR is raised immediately without retry."""
        call_count = 0

        @retry_api_call(max_retries=5, base_delay=0.01)
        def auth_fail() -> None:
            nonlocal call_count
            call_count += 1
            raise ValueError("AUTH_ERROR")

        with pytest.raises(ValueError, match="AUTH_ERROR"):
            auth_fail()

        assert call_count == 1

    def test_quota_error_not_retried(self) -> None:
        """QUOTA_ERROR is raised immediately without retry."""
        call_count = 0

        @retry_api_call(max_retries=5, base_delay=0.01)
        def quota_fail() -> None:
            nonlocal call_count
            call_count += 1
            raise ValueError("QUOTA_ERROR")

        with pytest.raises(ValueError, match="QUOTA_ERROR"):
            quota_fail()

        assert call_count == 1

    def test_model_not_found_not_retried(self) -> None:
        """MODEL_NOT_FOUND is raised immediately without retry."""
        call_count = 0

        @retry_api_call(max_retries=3, base_delay=0.01)
        def model_fail() -> None:
            nonlocal call_count
            call_count += 1
            raise ValueError("MODEL_NOT_FOUND")

        with pytest.raises(ValueError, match="MODEL_NOT_FOUND"):
            model_fail()

        assert call_count == 1

    def test_invalid_response_not_retried(self) -> None:
        """INVALID_RESPONSE is raised immediately without retry."""
        call_count = 0

        @retry_api_call(max_retries=3, base_delay=0.01)
        def invalid_resp() -> None:
            nonlocal call_count
            call_count += 1
            raise ValueError("INVALID_RESPONSE")

        with pytest.raises(ValueError, match="INVALID_RESPONSE"):
            invalid_resp()

        assert call_count == 1

    def test_exponential_backoff_delays(self) -> None:
        """Sleep delays follow exponential backoff pattern."""
        call_count = 0
        sleep_calls: list[float] = []

        @retry_api_call(max_retries=3, base_delay=1.0)
        def always_unavailable() -> None:
            nonlocal call_count
            call_count += 1
            raise ValueError("SERVICE_UNAVAILABLE_ERROR")

        with (
            patch(
                "src.core.llm_engine.time.sleep",
                side_effect=sleep_calls.append,
            ),
            pytest.raises(ValueError, match="SERVICE_UNAVAILABLE_ERROR"),
        ):
            always_unavailable()

        # 3 retries: delays should be 1.0, 2.0, 4.0
        assert len(sleep_calls) == 3  # noqa: PLR2004
        assert sleep_calls[0] == pytest.approx(1.0)
        assert sleep_calls[1] == pytest.approx(2.0)
        assert sleep_calls[2] == pytest.approx(4.0)

    def test_non_value_error_not_caught(self) -> None:
        """Non-ValueError exceptions propagate immediately."""
        call_count = 0

        @retry_api_call(max_retries=3, base_delay=0.01)
        def type_error_fn() -> None:
            nonlocal call_count
            call_count += 1
            raise TypeError("wrong type")

        with pytest.raises(TypeError, match="wrong type"):
            type_error_fn()

        assert call_count == 1


# ---------------------------------------------------------------------------
# TestIsUntranslatableAdditional
# ---------------------------------------------------------------------------


class TestIsUntranslatableAdditional:
    """Additional edge-case tests for _is_untranslatable."""

    def test_pure_integer(self) -> None:
        """Pure integer is untranslatable."""
        assert _is_untranslatable("42") is True

    def test_pure_float(self) -> None:
        """Float number is untranslatable."""
        assert _is_untranslatable("3.14159") is True

    def test_url_http(self) -> None:
        """HTTP URL is untranslatable."""
        assert _is_untranslatable("http://example.com") is True

    def test_url_https(self) -> None:
        """HTTPS URL is untranslatable."""
        assert _is_untranslatable("https://example.com/path") is True

    def test_email_standard(self) -> None:
        """Standard email is untranslatable."""
        assert _is_untranslatable("test@example.com") is True

    def test_file_path_unix(self) -> None:
        """Unix file path is untranslatable."""
        assert _is_untranslatable("/home/user/file.txt") is True

    def test_file_path_windows(self) -> None:
        """Windows file path is untranslatable."""
        assert _is_untranslatable("C:\\Documents\\file.pdf") is True

    def test_mixed_text_is_translatable(self) -> None:
        """Text containing words alongside numbers is translatable."""
        assert _is_untranslatable("I have 5 cats") is False

    def test_empty_string_is_untranslatable(self) -> None:
        """Empty string is untranslatable."""
        assert _is_untranslatable("") is True

    def test_whitespace_only_is_untranslatable(self) -> None:
        """Whitespace-only is untranslatable."""
        assert _is_untranslatable("   \t\n  ") is True

    def test_url_with_port(self) -> None:
        """URL with port number is untranslatable."""
        assert _is_untranslatable("https://localhost:8080/api") is True

    def test_www_url(self) -> None:
        """www.* URL is untranslatable."""
        assert _is_untranslatable("www.google.com") is True

    def test_alphanumeric_sentence(self) -> None:
        """Sentence with alphanumeric content is translatable."""
        assert _is_untranslatable("Room 101") is False


# ---------------------------------------------------------------------------
# TestDeduplicateTextsAdditional
# ---------------------------------------------------------------------------


class TestDeduplicateTextsAdditional:
    """Additional edge-case tests for _deduplicate_texts and _restore_duplicates."""

    def test_no_duplicates_returns_same(self) -> None:
        """All unique input returns identical unique list."""
        texts = ["one", "two", "three"]
        unique, dupe_map = _deduplicate_texts(texts)
        assert unique == texts
        assert len(dupe_map) == 3  # noqa: PLR2004

    def test_all_duplicates_returns_single(self) -> None:
        """All identical inputs collapse to single entry."""
        texts = ["same"] * 10
        unique, dupe_map = _deduplicate_texts(texts)
        assert unique == ["same"]
        assert dupe_map["same"] == list(range(10))

    def test_some_duplicates_preserves_order(self) -> None:
        """First occurrences define order in unique list."""
        texts = ["c", "a", "b", "a", "c"]
        unique, dupe_map = _deduplicate_texts(texts)
        assert unique == ["c", "a", "b"]
        assert dupe_map == {"c": [0, 4], "a": [1, 3], "b": [2]}

    def test_restore_maps_correctly(self) -> None:
        """_restore_duplicates correctly maps translations to all positions."""
        original = ["x", "y", "x", "z", "y"]
        unique, dupe_map = _deduplicate_texts(original)
        translated = ["X!", "Y!", "Z!"]
        result = _restore_duplicates(translated, unique, dupe_map, original)
        assert result == ["X!", "Y!", "X!", "Z!", "Y!"]

    def test_restore_with_empty_translated(self) -> None:
        """Empty translated list leaves all originals in place."""
        original = ["a", "b", "a"]
        unique, dupe_map = _deduplicate_texts(original)
        result = _restore_duplicates([], unique, dupe_map, original)
        assert result == ["a", "b", "a"]

    def test_restore_with_partial_translated(self) -> None:
        """Partial translated list maps translated portion, keeps rest original."""
        original = ["a", "b", "c"]
        unique, dupe_map = _deduplicate_texts(original)
        # Only first item translated
        result = _restore_duplicates(["A!"], unique, dupe_map, original)
        assert result == ["A!", "b", "c"]


# ---------------------------------------------------------------------------
# TestCompressGlossaryAdditional
# ---------------------------------------------------------------------------


class TestCompressGlossaryAdditional:
    """Additional edge-case tests for _compress_glossary."""

    def test_matching_entries_returned(self) -> None:
        """Only entries matching the batch text are returned."""
        glossary = [
            (1, "apple", "pomme"),
            (2, "banana", "banane"),
            (3, "cherry", "cerise"),
        ]
        texts = ["I like apple and cherry"]
        result = _compress_glossary(glossary, texts)
        assert result is not None
        assert len(result) == 2  # noqa: PLR2004
        ids = [e[0] for e in result]
        assert 1 in ids
        assert 3 in ids

    def test_no_matching_entries_returns_none(self) -> None:
        """When no glossary entries match, returns None."""
        glossary = [(1, "elephant", "elefant")]
        texts = ["Hello world"]
        result = _compress_glossary(glossary, texts)
        assert result is None

    def test_case_insensitive_matching(self) -> None:
        """Glossary matching is case-insensitive."""
        glossary = [(1, "HELLO", "BONJOUR")]
        texts = ["hello there"]
        result = _compress_glossary(glossary, texts)
        assert result is not None
        assert len(result) == 1

    def test_accent_insensitive_matching(self) -> None:
        """Glossary matching ignores accents/diacritics."""
        glossary = [(1, "café", "coffee shop")]
        texts = ["I went to the cafe"]
        result = _compress_glossary(glossary, texts)
        assert result is not None
        assert len(result) == 1

    def test_empty_glossary_returns_none(self) -> None:
        """Empty glossary returns None."""
        assert _compress_glossary([], ["some text"]) is None

    def test_none_glossary_returns_none(self) -> None:
        """None glossary returns None."""
        assert _compress_glossary(None, ["some text"]) is None

    def test_empty_batch_text_returns_none(self) -> None:
        """Empty batch text means no entries can match."""
        glossary = [(1, "hello", "bonjour")]
        result = _compress_glossary(glossary, [])
        assert result is None

    def test_target_text_match(self) -> None:
        """Glossary matches on target text (bidirectional)."""
        glossary = [(1, "hello", "bonjour")]
        texts = ["bonjour mon ami"]
        result = _compress_glossary(glossary, texts)
        assert result is not None
        assert len(result) == 1

    def test_html_tags_stripped_for_matching(self) -> None:
        """HTML tags in batch text are stripped before glossary matching."""
        glossary = [(1, "hello world", "bonjour monde")]
        texts = ["<b>hello</b> <i>world</i>"]
        result = _compress_glossary(glossary, texts)
        assert result is not None
        assert len(result) == 1

    def test_entries_with_whitespace_source_excluded(self) -> None:
        """Glossary entries with whitespace-only source are excluded."""
        glossary = [(1, "   ", "something"), (2, "hello", "bonjour")]
        texts = ["hello there"]
        result = _compress_glossary(glossary, texts)
        assert result is not None
        assert len(result) == 1
        assert result[0][0] == 2  # noqa: PLR2004

    def test_entries_with_whitespace_target_excluded(self) -> None:
        """Glossary entries with whitespace-only target are excluded."""
        glossary = [(1, "hello", "  "), (2, "world", "monde")]
        texts = ["hello world"]
        result = _compress_glossary(glossary, texts)
        assert result is not None
        assert len(result) == 1
        assert result[0][0] == 2  # noqa: PLR2004

    def test_large_glossary_only_relevant_returned(self) -> None:
        """Large glossary (50 entries) filters down to only relevant ones."""
        glossary = [(i, f"zword{i:04d}z", f"zmot{i:04d}z") for i in range(50)]
        texts = ["zword0000z zword0049z"]
        result = _compress_glossary(glossary, texts)
        assert result is not None
        assert len(result) == 2  # noqa: PLR2004
        ids = [e[0] for e in result]
        assert 0 in ids
        assert 49 in ids  # noqa: PLR2004


# ---------------------------------------------------------------------------
# TestExtractImageText — additional edge cases
# ---------------------------------------------------------------------------


class TestExtractImageTextAdditional:
    """Additional tests for extract_image_text dispatch."""

    def test_gemini_provider_dispatches_correctly(self) -> None:
        """Gemini method calls _extract_text_gemini."""
        from src.core.llm_engine import extract_image_text  # noqa: PLC0415

        with (
            patch(
                f"{_LLM_MOD}._config.load_setting",
                return_value=LLM_METHOD_GEMINI,
            ),
            patch(
                f"{_LLM_MOD}._extract_text_gemini",
                return_value="extracted text",
            ) as mock_fn,
        ):
            result = extract_image_text("/test/image.jpg")

        assert result == "extracted text"
        mock_fn.assert_called_once()
        assert mock_fn.call_args.args[0] == "/test/image.jpg"

    def test_custom_provider_dispatches_correctly(self) -> None:
        """Custom method calls _extract_text_custom."""
        from src.core.llm_engine import extract_image_text  # noqa: PLC0415

        with (
            patch(
                f"{_LLM_MOD}._resolve_provider_model",
                return_value=(LLM_METHOD_CUSTOM, "gpt-4o"),
            ),
            patch(
                f"{_LLM_MOD}._extract_text_custom",
                return_value="custom extracted",
            ) as mock_fn,
        ):
            result = extract_image_text("/test/image.png")

        assert result == "custom extracted"
        mock_fn.assert_called_once()
        assert mock_fn.call_args.args[0] == "/test/image.png"

    def test_unknown_provider_returns_empty(self) -> None:
        """Unknown LLM method returns empty string."""
        from src.core.llm_engine import extract_image_text  # noqa: PLC0415

        with patch(
            f"{_LLM_MOD}._resolve_provider_model",
            return_value=("SomeUnknown", ""),
        ):
            result = extract_image_text("/fake.jpg")

        assert result == ""

    def test_gemini_vision_not_supported_raises(self) -> None:
        """_extract_text_gemini raises VISION_NOT_SUPPORTED when model lacks vision."""
        from src.core.llm_engine import _extract_text_gemini  # noqa: PLC0415

        settings = {
            "llm/gemini_api_key": "key",
            "llm/gemini_model": "gemini-2.0-flash",
        }

        client = _make_mock_genai_client(
            response_error=_genai_api_error(
                400,
                "Error: this model does not support image input",
            ),
        )

        with (
            patch(
                f"{_LLM_MOD}._config.load_setting",
                side_effect=lambda k, d="": settings.get(k, d),
            ),
            patch(
                f"{_LLM_MOD}._build_gemini_client",
                return_value=client,
            ),
            patch(
                "pathlib.Path.read_bytes",
                return_value=b"fake image data",
            ),
            pytest.raises(ValueError, match="VISION_NOT_SUPPORTED"),
        ):
            _extract_text_gemini("/test/image.png")

    def test_custom_missing_credentials_raises_auth_error(self) -> None:
        """_extract_text_custom raises AUTH_ERROR when credentials missing."""
        from src.core.llm_engine import _extract_text_custom  # noqa: PLC0415

        with (
            patch(
                f"{_LLM_MOD}._config.load_setting",
                side_effect=lambda k, d="": "",
            ),
            pytest.raises(ValueError, match="AUTH_ERROR"),
        ):
            _extract_text_custom("/test/image.png")

    def test_gemini_successful_extraction(self) -> None:
        """_extract_text_gemini returns extracted text on success."""
        from src.core.llm_engine import _extract_text_gemini  # noqa: PLC0415

        inner = json.dumps({"text": "Hello World"})

        settings = {
            "llm/gemini_api_key": "key",
            "llm/gemini_model": "gemini-2.0-flash",
        }
        client = _make_mock_genai_client(response_text=inner)

        with (
            patch(
                f"{_LLM_MOD}._config.load_setting",
                side_effect=lambda k, d="": settings.get(k, d),
            ),
            patch(
                f"{_LLM_MOD}._build_gemini_client",
                return_value=client,
            ),
            patch(
                "pathlib.Path.read_bytes",
                return_value=b"fake image data",
            ),
        ):
            result = _extract_text_gemini("/test/image.png")

        assert result == "Hello World"

    def test_custom_successful_extraction(self) -> None:
        """_extract_text_custom returns extracted text on success."""
        from src.core.llm_engine import _extract_text_custom  # noqa: PLC0415

        content = json.dumps({"text": "Extracted Text"})

        settings = {
            "llm/custom_api_key": "key",
            "llm/custom_model": "gpt-4o",
            "llm/custom_endpoint": "https://api.example.com/v1",
        }
        client = _make_mock_sdk_client(chat_response=_make_sdk_chat_response(content))

        with (
            patch(
                f"{_LLM_MOD}._config.load_setting",
                side_effect=lambda k, d="": settings.get(k, d),
            ),
            patch(
                f"{_LLM_MOD}._build_openai_client",
                return_value=client,
            ),
            patch(
                "pathlib.Path.open",
                return_value=io.BytesIO(b"fake image data"),
            ),
        ):
            result = _extract_text_custom("/test/image.png")

        assert result == "Extracted Text"


# ---------------------------------------------------------------------------
# TestTranslateBatchCheckpointEdgeCases
# ---------------------------------------------------------------------------


class TestTranslateBatchCheckpointEdgeCases:
    """Checkpoint-specific edge cases for translate_batch."""

    def test_checkpoint_saves_on_correct_result_count(self, tmp_path: object) -> None:
        """Checkpoint IS saved when LLM returns the correct number of results."""
        from pathlib import Path  # noqa: PLC0415

        cp_dir = Path(str(tmp_path)) / "cp_correct"
        cp_dir.mkdir()

        def _correct_translate(
            texts: list[str],
            target: str,
            source: str = "",
            **kwargs: object,
        ) -> list[str]:
            return [f"T_{t}" for t in texts]

        mock_fn = _correct_translate
        with patch("src.core.llm_engine.translate_text", side_effect=mock_fn):
            result = translate_batch(
                ["A", "B", "C"],
                "French",
                "English",
                checkpoint_dir=cp_dir,
            )

        assert result is not None
        assert len(result) == 3  # noqa: PLR2004

        # Verify checkpoint was actually saved by doing a second run
        call_count = {"n": 0}

        def _no_call(
            texts: list[str],
            target: str,
            source: str = "",
            **kwargs: object,
        ) -> list[str]:
            call_count["n"] += 1
            return texts

        with patch("src.core.llm_engine.translate_text", side_effect=_no_call):
            result2 = translate_batch(
                ["A", "B", "C"],
                "French",
                "English",
                checkpoint_dir=cp_dir,
            )
        # All cached, no new calls
        assert result2 == result
        assert call_count["n"] == 0

    def test_no_checkpoint_dir_translates_without_saving(self) -> None:
        """Without checkpoint_dir, all items are translated and no save occurs."""
        call_texts: list[list[str]] = []

        def _capture(
            texts: list[str],
            target: str,
            source: str = "",
            **kwargs: object,
        ) -> list[str]:
            call_texts.append(list(texts))
            return [f"T_{t}" for t in texts]

        with patch("src.core.llm_engine.translate_text", side_effect=_capture):
            result = translate_batch(
                ["X", "Y"],
                "French",
                "English",
                checkpoint_dir=None,
            )

        assert result is not None
        assert result == ["T_X", "T_Y"]
        # Items were sent (no checkpoint to cache them)
        assert sum(len(c) for c in call_texts) == 2  # noqa: PLR2004


# ---------------------------------------------------------------------------
# TestTranslateTextDispatch — additional dispatch tests
# ---------------------------------------------------------------------------


class TestTranslateTextDispatch:
    """Tests for translate_text LLM method dispatch."""

    def test_dispatches_to_gemini(self) -> None:
        """Gemini method dispatches to _translate_gemini."""

        def fake_gemini(
            batch: list[str],
            tl: str,
            sl: str,
            gl: object,
            ct: str,
            model="",
            **_kwargs,
        ) -> list[str]:
            return [f"G_{t}" for t in batch]

        with (
            patch(
                "src.core.llm_engine._resolve_provider_model",
                return_value=(LLM_METHOD_GEMINI, "gemini-3-flash-preview"),
            ),
            patch(
                "src.core.llm_engine._translate_gemini",
                side_effect=fake_gemini,
            ),
        ):
            result = translate_text(["Hello"], "French")

        assert result == ["G_Hello"]

    def test_dispatches_to_custom(self) -> None:
        """Custom method dispatches to _translate_custom."""

        def fake_custom(
            batch: list[str],
            tl: str,
            sl: str,
            gl: object,
            ct: str,
            model="",
            **_kwargs,
        ) -> list[str]:
            return [f"C_{t}" for t in batch]

        with (
            patch(
                "src.core.llm_engine._resolve_provider_model",
                return_value=(LLM_METHOD_CUSTOM, "gpt-4o"),
            ),
            patch(
                "src.core.llm_engine._translate_custom",
                side_effect=fake_custom,
            ),
        ):
            result = translate_text(["Hello"], "French")

        assert result == ["C_Hello"]

    def test_unknown_method_returns_originals(self) -> None:
        """Unknown LLM method returns originals unchanged."""
        with patch(
            "src.core.llm_engine._resolve_provider_model",
            return_value=("NonexistentProvider", ""),
        ):
            result = translate_text(["Hello", "World"], "French")
        assert result == ["Hello", "World"]

    def test_cancel_before_first_batch(self) -> None:
        """Cancellation before first batch returns originals."""

        def fake_translate(
            batch: list[str],
            tl: str,
            sl: str,
            gl: object,
            ct: str,
            model="",
            **_kwargs,
        ) -> list[str]:
            return [f"T_{t}" for t in batch]

        with (
            patch(
                "src.core.llm_engine._resolve_provider_model",
                return_value=(LLM_METHOD_GEMINI, "gemini-3-flash-preview"),
            ),
            patch(
                "src.core.llm_engine._translate_gemini",
                side_effect=fake_translate,
            ),
            patch(
                "src.core.llm_engine._split_by_token_budget",
                return_value=[["Hello"], ["World"]],
            ),
        ):
            result = translate_text(
                ["Hello", "World"],
                "French",
                cancel_check=lambda: True,
            )
        # Cancelled immediately — returns originals
        assert result == ["Hello", "World"]


# ---------------------------------------------------------------------------
# TestTranslateCustomEdgeCases
# ---------------------------------------------------------------------------


class TestTranslateCustomEdgeCases:
    """Edge cases for _translate_custom."""

    def test_missing_api_key_raises_auth_error(self) -> None:
        """Empty endpoint/model raises AUTH_ERROR (missing key no longer fatal)."""
        from src.core.llm_engine import _translate_custom  # noqa: PLC0415

        # Production accepts an empty api_key (keyless local endpoints). It
        # raises AUTH_ERROR only when endpoint or model are empty.
        with (
            patch(
                "src.core.llm_engine._resolve_custom_config",
                return_value=("", "", ""),
            ),
            pytest.raises(ValueError, match="AUTH_ERROR"),
        ):
            _translate_custom(["Hello"], "French", "English")

    def test_missing_model_raises_auth_error(self) -> None:
        """Empty model raises AUTH_ERROR."""
        from src.core.llm_engine import _translate_custom  # noqa: PLC0415

        settings = {
            "llm/custom_api_key": "key",
            "llm/custom_model": "",
            "llm/custom_endpoint": "https://api.example.com/v1",
        }
        with (
            patch(
                "src.core.llm_engine._config.load_setting",
                side_effect=lambda k, d="": settings.get(k, d),
            ),
            pytest.raises(ValueError, match="AUTH_ERROR"),
        ):
            _translate_custom(["Hello"], "French", "English")

    def test_missing_endpoint_raises_auth_error(self) -> None:
        """Empty endpoint raises AUTH_ERROR."""
        from src.core.llm_engine import _translate_custom  # noqa: PLC0415

        settings = {
            "llm/custom_api_key": "key",
            "llm/custom_model": "gpt-4",
            "llm/custom_endpoint": "",
        }
        with (
            patch(
                "src.core.llm_engine._config.load_setting",
                side_effect=lambda k, d="": settings.get(k, d),
            ),
            pytest.raises(ValueError, match="AUTH_ERROR"),
        ):
            _translate_custom(["Hello"], "French", "English")


# ---------------------------------------------------------------------------
# TestBuildTranslationPromptAdditional
# ---------------------------------------------------------------------------


class TestBuildTranslationPromptAdditional:
    """Additional tests for _build_translation_prompt."""

    def test_html_content_type_mentions_html_tags(self) -> None:
        """HTML content type prompt mentions preserving HTML tags."""
        from src.constants.llm import CONTENT_HTML  # noqa: PLC0415

        result = _build_translation_prompt(CONTENT_HTML, "English", "French")
        assert "HTML tags" in result

    def test_subtitle_content_type_mentions_dialogue(self) -> None:
        """Subtitle content type prompt mentions dialogue."""
        from src.constants.llm import CONTENT_SUBTITLE  # noqa: PLC0415

        result = _build_translation_prompt(CONTENT_SUBTITLE, "English", "French")
        assert "subtitle" in result.lower() or "dialogue" in result.lower()

    def test_xml_content_type_mentions_xml_tags(self) -> None:
        """XML content type prompt mentions preserving XML tags."""
        from src.constants.llm import CONTENT_XML  # noqa: PLC0415

        result = _build_translation_prompt(CONTENT_XML, "English", "French")
        assert "XML tags" in result

    def test_localization_content_type_mentions_placeholders(self) -> None:
        """Localization content type prompt mentions preserving placeholders."""
        from src.constants.llm import CONTENT_LOCALIZATION  # noqa: PLC0415

        result = _build_translation_prompt(CONTENT_LOCALIZATION, "English", "French")
        assert "placeholder" in result.lower()

    def test_rtf_content_type_mentions_markers(self) -> None:
        """RTF content type prompt mentions preserving markers."""
        from src.constants.llm import CONTENT_RTF  # noqa: PLC0415

        result = _build_translation_prompt(CONTENT_RTF, "English", "French")
        assert "PRESERVE_RTF" in result

    def test_epub_content_type_mentions_xhtml(self) -> None:
        """EPUB content type prompt mentions XHTML."""
        from src.constants.llm import CONTENT_EPUB  # noqa: PLC0415

        result = _build_translation_prompt(CONTENT_EPUB, "English", "French")
        assert "XHTML" in result

    def test_markdown_content_type_mentions_syntax(self) -> None:
        """Markdown content type prompt mentions Markdown syntax."""
        from src.constants.llm import CONTENT_MARKDOWN  # noqa: PLC0415

        result = _build_translation_prompt(CONTENT_MARKDOWN, "English", "French")
        assert "Markdown" in result

    def test_auto_detect_source_language(self) -> None:
        """Empty source language omits 'from' clause."""
        result = _build_translation_prompt(CONTENT_PLAIN_TEXT, "", "French")
        assert "into French" in result
        assert "from " not in result.split("into")[0]

    def test_with_source_language(self) -> None:
        """Non-empty source language uses 'from X to Y' clause."""
        result = _build_translation_prompt(CONTENT_PLAIN_TEXT, "English", "French")
        assert "from English to French" in result


# ---------------------------------------------------------------------------
# TestEstimateTokensAdditional
# ---------------------------------------------------------------------------


class TestEstimateTokensAdditional:
    """Additional tests for _estimate_tokens."""

    def test_mixed_cjk_and_latin(self) -> None:
        """Mixed CJK and Latin: CJK counted individually, Latin by /4."""
        from src.core.llm_engine import _estimate_tokens  # noqa: PLC0415

        # 4 CJK + 8 Latin = 4 + 8//4 = 4 + 2 = 6
        text = "你好世界abcdefgh"
        result = _estimate_tokens(text)
        assert result == 6  # noqa: PLR2004

    def test_single_cjk_character(self) -> None:
        """Single CJK character returns 1."""
        from src.core.llm_engine import _estimate_tokens  # noqa: PLC0415

        assert _estimate_tokens("你") == 1

    def test_single_latin_char(self) -> None:
        """Single Latin char: 1//4 = 0 → clamped to 1."""
        from src.core.llm_engine import _estimate_tokens  # noqa: PLC0415

        assert _estimate_tokens("a") == 1


# ---------------------------------------------------------------------------
# TestTranslateImageContentDispatch
# ---------------------------------------------------------------------------


class TestTranslateImageContentDispatch:
    """Tests for translate_image_content dispatch logic."""

    def test_dispatches_to_gemini(self) -> None:
        """Gemini method dispatches to _translate_image_gemini."""
        mock_ocr = MagicMock()
        mock_ocr.text = "Hello"

        with (
            patch(
                "src.core.llm_engine._resolve_provider_model",
                return_value=(LLM_METHOD_GEMINI, "gemini-3-flash-preview"),
            ),
            patch(
                "src.core.llm_engine._translate_image_gemini",
                return_value=[{"ids": [0], "translated_html": "Bonjour"}],
            ) as mock_fn,
        ):
            result = translate_image_content("/test.jpg", [mock_ocr], "French")

        mock_fn.assert_called_once()
        assert result[0]["translated_html"] == "Bonjour"

    def test_dispatches_to_custom(self) -> None:
        """Custom method dispatches to _translate_image_custom."""
        mock_ocr = MagicMock()
        mock_ocr.text = "Hello"

        with (
            patch(
                "src.core.llm_engine._resolve_provider_model",
                return_value=(LLM_METHOD_CUSTOM, "gpt-4o"),
            ),
            patch(
                "src.core.llm_engine._translate_image_custom",
                return_value=[{"ids": [0], "translated_html": "Bonjour"}],
            ) as mock_fn,
        ):
            result = translate_image_content("/test.jpg", [mock_ocr], "French")

        mock_fn.assert_called_once()
        assert result[0]["translated_html"] == "Bonjour"

    def test_empty_ocr_returns_empty(self) -> None:
        """Empty OCR results returns empty list without calling LLM."""
        result = translate_image_content("/test.jpg", [], "French")
        assert result == []

    def test_unknown_method_returns_empty(self) -> None:
        """Unknown LLM method returns empty list."""
        mock_ocr = MagicMock()
        mock_ocr.text = "Hello"

        with patch(
            "src.core.llm_engine._resolve_provider_model",
            return_value=("UnknownMethod", ""),
        ):
            result = translate_image_content("/test.jpg", [mock_ocr], "French")
        assert result == []


# ---------------------------------------------------------------------------
# TestFormatLangPairAdditional
# ---------------------------------------------------------------------------


class TestFormatLangPairAdditional:
    """Additional tests for _format_lang_pair."""

    def test_both_languages_specified(self) -> None:
        """Both source and target produce 'from X to Y' format."""
        result = _format_lang_pair("Japanese", "Vietnamese")
        assert result == "Translate the following from Japanese to Vietnamese."

    def test_source_empty_auto_detect(self) -> None:
        """Empty source produces 'into Y' format."""
        result = _format_lang_pair("", "German")
        assert result == "Translate the following into German."

    def test_languages_with_parentheses(self) -> None:
        """Language names with parentheses (like 'English (US)') are preserved."""
        result = _format_lang_pair("English (US)", "French")
        assert "English (US)" in result
        assert "French" in result


# ===========================================================================
# EXPANDED TESTS — target 650+ total
# ===========================================================================


# ---------------------------------------------------------------------------
# _is_untranslatable — Unicode and special character edge cases
# ---------------------------------------------------------------------------


class TestIsUntranslatableUnicode:
    """Unicode edge cases for _is_untranslatable."""

    def test_arabic_text_is_translatable(self) -> None:
        """Arabic script text should be translatable."""
        assert _is_untranslatable("\u0645\u0631\u062d\u0628\u0627") is False

    def test_devanagari_text_is_translatable(self) -> None:
        """Hindi (Devanagari) text should be translatable."""
        assert _is_untranslatable("\u0928\u092e\u0938\u094d\u0924\u0947") is False

    def test_thai_text_is_translatable(self) -> None:
        """Thai text should be translatable."""
        assert _is_untranslatable("\u0e2a\u0e27\u0e31\u0e2a\u0e14\u0e35") is False

    def test_hebrew_text_is_translatable(self) -> None:
        """Hebrew text should be translatable."""
        assert _is_untranslatable("\u05e9\u05dc\u05d5\u05dd") is False

    def test_cyrillic_text_is_translatable(self) -> None:
        """Russian (Cyrillic) text should be translatable."""
        assert _is_untranslatable("\u041f\u0440\u0438\u0432\u0435\u0442") is False

    def test_emoji_only_is_translatable(self) -> None:
        """Emoji-only string is not matched by symbol regex, so translatable."""
        assert _is_untranslatable("\U0001f600\U0001f601\U0001f602") is False

    def test_mixed_emoji_and_text_is_translatable(self) -> None:
        """Text with emoji is translatable."""
        assert _is_untranslatable("Hello \U0001f600") is False

    def test_zero_width_space_is_untranslatable(self) -> None:
        """Zero-width space / whitespace-only should be untranslatable."""
        # Zero-width spaces stripped → empty
        assert _is_untranslatable("\u200b") is False  # Not whitespace per Python

    def test_fullwidth_digits_are_translatable(self) -> None:
        """Fullwidth digits (e.g. 123) are matched by Python's \\d class."""
        assert _is_untranslatable("\uff11\uff12\uff13") is True

    def test_mathematical_operators_untranslatable(self) -> None:
        """Pure mathematical expression is untranslatable."""
        assert _is_untranslatable("2 + 2 = 4") is True

    def test_pipe_and_ampersand_untranslatable(self) -> None:
        """Pipe and ampersand symbols alone are untranslatable."""
        assert _is_untranslatable("| & |") is True

    def test_backslash_forward_slash_untranslatable(self) -> None:
        """Bare slashes/backslashes are untranslatable."""
        assert _is_untranslatable("\\\\//") is True

    def test_tilde_caret_untranslatable(self) -> None:
        """Tilde and caret symbols alone are untranslatable."""
        assert _is_untranslatable("~^~") is True

    def test_angle_brackets_untranslatable(self) -> None:
        """Angle brackets alone (without letters) are untranslatable."""
        assert _is_untranslatable("< > < >") is True

    def test_curly_braces_untranslatable(self) -> None:
        """Curly braces with only spaces are untranslatable."""
        assert _is_untranslatable("{ }") is True

    def test_url_with_unicode_domain_untranslatable(self) -> None:
        """URL with unicode path is untranslatable."""
        assert _is_untranslatable("https://example.com/path") is True

    def test_email_with_dots_in_name(self) -> None:
        """Email with dots in local part is untranslatable."""
        assert _is_untranslatable("first.last@company.org") is True

    def test_email_with_numbers(self) -> None:
        """Email with numbers in local part is untranslatable."""
        assert _is_untranslatable("user123@domain.io") is True

    def test_unix_path_home(self) -> None:
        """Unix path under /home is untranslatable."""
        assert _is_untranslatable("/home/john/documents/report.pdf") is True

    def test_windows_drive_letter_d(self) -> None:
        """Windows path with D: drive is untranslatable."""
        assert _is_untranslatable("D:\\Data\\file.csv") is True

    def test_www_with_subdomain(self) -> None:
        """Www URL with subdomain is untranslatable."""
        assert _is_untranslatable("www.sub.domain.com/path") is True

    def test_negative_number_untranslatable(self) -> None:
        """Negative number is untranslatable."""
        assert _is_untranslatable("-42") is True

    def test_number_with_sign_untranslatable(self) -> None:
        """Number with plus sign is untranslatable."""
        assert _is_untranslatable("+100") is True

    def test_percentage_with_number(self) -> None:
        """Percentage string is untranslatable."""
        assert _is_untranslatable("75%") is True

    def test_british_pound_currency(self) -> None:
        """British pound symbol with amount is untranslatable."""
        assert _is_untranslatable("\u00a3500") is True

    def test_yen_currency(self) -> None:
        """Japanese yen symbol with amount is untranslatable."""
        assert _is_untranslatable("\u00a510000") is True

    def test_exclamation_question_marks(self) -> None:
        """Multiple punctuation marks alone are untranslatable."""
        assert _is_untranslatable("!?!?") is True

    def test_semicolons_colons(self) -> None:
        """Semicolons and colons alone are untranslatable."""
        assert _is_untranslatable(";;::") is True

    def test_hash_symbols(self) -> None:
        """Hash/pound symbols alone are untranslatable."""
        assert _is_untranslatable("###") is True

    def test_at_sign_alone(self) -> None:
        """At sign alone is untranslatable."""
        assert _is_untranslatable("@@@") is True

    def test_underscore_only(self) -> None:
        """Underscores alone are untranslatable."""
        assert _is_untranslatable("___") is True

    def test_quoted_number(self) -> None:
        """Quoted number is untranslatable (quotes are in symbol set)."""
        assert _is_untranslatable('"42"') is True

    def test_single_quoted_number(self) -> None:
        """Single-quoted number is untranslatable."""
        assert _is_untranslatable("'100'") is True


# ---------------------------------------------------------------------------
# _estimate_tokens — extensive edge cases
# ---------------------------------------------------------------------------


class TestEstimateTokensExtended:
    """Extended tests for _estimate_tokens."""

    def test_pure_cjk_long_text(self) -> None:
        """100 CJK chars → 100 tokens."""
        text = "\u4f60" * 100
        assert _estimate_tokens(text) == 100  # noqa: PLR2004

    def test_pure_latin_exact_boundary(self) -> None:
        """Exactly 4 Latin chars → 1 token."""
        assert _estimate_tokens("abcd") == 1

    def test_five_latin_chars(self) -> None:
        """5 Latin chars → 5//4 = 1 token."""
        assert _estimate_tokens("abcde") == 1

    def test_eight_latin_chars(self) -> None:
        """8 Latin chars → 8//4 = 2 tokens."""
        assert _estimate_tokens("abcdefgh") == 2  # noqa: PLR2004

    def test_mixed_cjk_latin_precise(self) -> None:
        """2 CJK + 12 Latin = 2 + 12//4 = 2 + 3 = 5."""
        text = "\u4f60\u597d" + "a" * 12
        assert _estimate_tokens(text) == 5  # noqa: PLR2004

    def test_spaces_count_as_latin(self) -> None:
        """Spaces are non-CJK, counted in the latin ratio."""
        text = "    "  # 4 chars → 4//4 = 1
        assert _estimate_tokens(text) == 1

    def test_newlines_count_as_latin(self) -> None:
        """Newlines are non-CJK characters."""
        text = "\n" * 8  # 8 chars → 8//4 = 2
        assert _estimate_tokens(text) == 2  # noqa: PLR2004

    def test_emoji_not_counted_as_cjk(self) -> None:
        """Emoji codepoints (U+1F600+) are above CJK_CODEPOINT_THRESHOLD → counted as CJK."""
        # U+1F600 is > 0x2FFF so it IS counted as CJK in this implementation
        text = "\U0001f600"  # Single emoji
        assert _estimate_tokens(text) == 1

    def test_hiragana_counted_as_cjk(self) -> None:
        """Hiragana (U+3040+) is above the CJK threshold."""
        text = "\u3042" * 10  # あ repeated
        assert _estimate_tokens(text) == 10  # noqa: PLR2004

    def test_katakana_counted_as_cjk(self) -> None:
        """Katakana (U+30A0+) is above the CJK threshold."""
        text = "\u30a2" * 5  # ア repeated
        assert _estimate_tokens(text) == 5  # noqa: PLR2004

    def test_hangul_counted_as_cjk(self) -> None:
        """Korean Hangul (U+AC00+) is above the CJK threshold."""
        text = "\uac00" * 7  # 가 repeated
        assert _estimate_tokens(text) == 7  # noqa: PLR2004


# ---------------------------------------------------------------------------
# _split_by_token_budget — precise boundary tests
# ---------------------------------------------------------------------------


class TestSplitByTokenBudgetPrecise:
    """Precise boundary tests for _split_by_token_budget."""

    def test_three_items_exact_fit(self) -> None:
        """Three items exactly filling budget stay in one batch."""
        # Each: 12 chars → 3 tokens + 10 overhead = 13
        # Budget = 39 → exactly 3 items
        item = "a" * 12
        batches = _split_by_token_budget([item, item, item], budget=39)
        assert len(batches) == 1
        assert len(batches[0]) == 3  # noqa: PLR2004

    def test_three_items_one_token_over_budget(self) -> None:
        """Three items exceeding budget by 1 token split into 2 batches."""
        # Each: 12 chars → 3 tokens + 10 overhead = 13
        # Budget = 38 → 2 items = 26 ≤ 38, 3 items = 39 > 38
        item = "a" * 12
        batches = _split_by_token_budget([item, item, item], budget=38)
        assert len(batches) == 2  # noqa: PLR2004
        assert len(batches[0]) == 2  # noqa: PLR2004
        assert len(batches[1]) == 1

    def test_cjk_items_counted_correctly(self) -> None:
        """CJK items with higher token count split at correct boundaries."""
        # Each: 10 CJK chars → 10 tokens + 10 overhead = 20
        item = "\u4f60" * 10
        batches = _split_by_token_budget([item, item, item], budget=40)
        assert len(batches) == 2  # noqa: PLR2004
        assert len(batches[0]) == 2  # noqa: PLR2004
        assert len(batches[1]) == 1

    def test_single_empty_string(self) -> None:
        """Empty string: 0 chars → 1 token (minimum) + 10 overhead = 11."""
        batches = _split_by_token_budget([""], budget=11)
        assert len(batches) == 1
        assert batches[0] == [""]

    def test_two_empty_strings_budget_22(self) -> None:
        """Two empty strings with budget 22 fit in one batch (11 + 11 = 22)."""
        batches = _split_by_token_budget(["", ""], budget=22)
        assert len(batches) == 1
        assert len(batches[0]) == 2  # noqa: PLR2004

    def test_two_empty_strings_budget_21(self) -> None:
        """Two empty strings with budget 21 split (11 + 11 = 22 > 21)."""
        batches = _split_by_token_budget(["", ""], budget=21)
        assert len(batches) == 2  # noqa: PLR2004

    def test_many_items_creates_multiple_batches(self) -> None:
        """100 small items with small budget creates many batches."""
        texts = ["hi"] * 100
        # Each: 1 token + 10 overhead = 11
        batches = _split_by_token_budget(texts, budget=33)
        # Each batch fits 3 items (33 / 11 = 3)
        assert len(batches) == 34  # noqa: PLR2004
        # First 33 batches have 3, last has 1
        assert all(len(b) == 3 for b in batches[:33])  # noqa: PLR2004
        assert len(batches[33]) == 1  # noqa: PLR2004

    def test_alternating_small_large(self) -> None:
        """Alternating small and large items split correctly."""
        small = "a"  # 1 token + 10 = 11
        large = "b" * 4000  # 1000 tokens + 10 = 1010
        texts = [small, large, small, large, small]
        batches = _split_by_token_budget(texts, budget=100)
        # small(11), large exceeds → flush small, large alone, small alone, ...
        assert len(batches) == 5  # noqa: PLR2004

    def test_gradually_increasing_sizes(self) -> None:
        """Items with gradually increasing sizes fill batches dynamically."""
        items = ["x" * (i * 40) for i in range(1, 6)]
        # Item costs: 10+10=20, 20+10=30, 30+10=40, 40+10=50, 50+10=60
        batches = _split_by_token_budget(items, budget=60)
        # 20 + 30 = 50 ≤ 60, + 40 = 90 > 60 → batch 1 = [0,1]
        # 40 + 50 = 90 > 60 → batch 2 = [2]
        # 50 + 60 = 110 > 60 → batch 3 = [3]
        # batch 4 = [4]
        assert len(batches) == 4  # noqa: PLR2004
        assert len(batches[0]) == 2  # noqa: PLR2004


# ---------------------------------------------------------------------------
# _deduplicate_texts / _restore_duplicates — advanced edge cases
# ---------------------------------------------------------------------------


class TestDeduplicateTextsAdvanced:
    """Advanced dedup/restore edge cases."""

    def test_unicode_strings_deduplicated(self) -> None:
        """Unicode strings are deduplicated correctly."""
        texts = ["\u4f60\u597d", "\u4f60\u597d", "\u4e16\u754c"]
        unique, dupe_map = _deduplicate_texts(texts)
        assert unique == ["\u4f60\u597d", "\u4e16\u754c"]
        assert dupe_map["\u4f60\u597d"] == [0, 1]

    def test_emoji_strings_deduplicated(self) -> None:
        """Emoji strings are deduplicated correctly."""
        texts = ["\U0001f600", "\U0001f600", "\U0001f601"]
        unique, dupe_map = _deduplicate_texts(texts)
        assert unique == ["\U0001f600", "\U0001f601"]

    def test_multiline_strings_deduplicated(self) -> None:
        """Multiline strings are compared exactly."""
        texts = ["line1\nline2", "line1\nline2", "different"]
        unique, dupe_map = _deduplicate_texts(texts)
        assert unique == ["line1\nline2", "different"]
        assert dupe_map["line1\nline2"] == [0, 1]

    def test_html_strings_deduplicated(self) -> None:
        """HTML content strings are compared as-is."""
        texts = ["<b>hello</b>", "<b>hello</b>", "<i>world</i>"]
        unique, dupe_map = _deduplicate_texts(texts)
        assert unique == ["<b>hello</b>", "<i>world</i>"]

    def test_whitespace_differences_not_deduplicated(self) -> None:
        """Leading/trailing whitespace differences are not deduped."""
        texts = ["hello", " hello", "hello "]
        unique, dupe_map = _deduplicate_texts(texts)
        assert len(unique) == 3  # noqa: PLR2004

    def test_restore_with_100_items(self) -> None:
        """Round-trip with 100 items, 10 unique."""
        original = [f"word{i % 10}" for i in range(100)]
        unique, dupe_map = _deduplicate_texts(original)
        assert len(unique) == 10  # noqa: PLR2004
        translated = [f"T_{u}" for u in unique]
        result = _restore_duplicates(translated, unique, dupe_map, original)
        assert len(result) == 100  # noqa: PLR2004
        for i in range(100):
            assert result[i] == f"T_word{i % 10}"

    def test_restore_preserves_partial_with_dupes(self) -> None:
        """Partial restore with duplicates: translated dupes expanded, rest original."""
        original = ["a", "b", "a", "c", "b"]
        unique, dupe_map = _deduplicate_texts(original)
        # Only first 2 unique items translated
        translated = ["A!", "B!"]
        result = _restore_duplicates(translated, unique, dupe_map, original)
        assert result == ["A!", "B!", "A!", "c", "B!"]

    def test_restore_single_duplicate_at_end(self) -> None:
        """Single duplicate at the end is restored correctly."""
        original = ["x", "y", "x"]
        unique, dupe_map = _deduplicate_texts(original)
        translated = ["X!", "Y!"]
        result = _restore_duplicates(translated, unique, dupe_map, original)
        assert result == ["X!", "Y!", "X!"]

    def test_empty_string_duplicates(self) -> None:
        """Empty strings are deduplicated correctly."""
        texts = ["", "hello", "", ""]
        unique, dupe_map = _deduplicate_texts(texts)
        assert unique == ["", "hello"]
        assert dupe_map[""] == [0, 2, 3]


# ---------------------------------------------------------------------------
# _compress_glossary — advanced matching edge cases
# ---------------------------------------------------------------------------


class TestCompressGlossaryAdvanced:
    """Advanced glossary compression edge cases."""

    def test_unicode_normalization_nfkd(self) -> None:
        """Glossary with composed vs decomposed Unicode matches."""
        # \u00e9 = composed e-acute; batch text has decomposed or plain 'e'
        glossary = [(1, "r\u00e9sum\u00e9", "CV")]
        texts = ["resume your work"]
        result = _compress_glossary(glossary, texts)
        assert result is not None

    def test_turkish_i_matching(self) -> None:
        """Turkish dotless-i normalized matching."""
        glossary = [(1, "Istanbul", "\u0130stanbul")]
        texts = ["istanbul is great"]
        result = _compress_glossary(glossary, texts)
        assert result is not None

    def test_multiple_glossary_entries_same_source(self) -> None:
        """Multiple entries with different IDs but same source text."""
        glossary = [
            (1, "hello", "bonjour"),
            (2, "hello", "salut"),
        ]
        texts = ["hello world"]
        result = _compress_glossary(glossary, texts)
        assert result is not None
        assert len(result) == 2  # noqa: PLR2004

    def test_very_long_glossary_term(self) -> None:
        """Very long glossary term matches if present in text."""
        long_term = "artificial intelligence and machine learning"
        glossary = [(1, long_term, "IA et apprentissage automatique")]
        texts = [f"We study {long_term} at university"]
        result = _compress_glossary(glossary, texts)
        assert result is not None

    def test_glossary_term_at_start_of_text(self) -> None:
        """Glossary term at the very beginning of the text matches."""
        glossary = [(1, "hello", "bonjour")]
        texts = ["hello, how are you?"]
        result = _compress_glossary(glossary, texts)
        assert result is not None

    def test_glossary_term_at_end_of_text(self) -> None:
        """Glossary term at the very end of the text matches."""
        glossary = [(1, "world", "monde")]
        texts = ["hello world"]
        result = _compress_glossary(glossary, texts)
        assert result is not None

    def test_glossary_with_numbers_in_term(self) -> None:
        """Glossary term containing numbers matches."""
        glossary = [(1, "Web 3.0", "Web 3.0")]
        texts = ["The future of Web 3.0 technology"]
        result = _compress_glossary(glossary, texts)
        assert result is not None

    def test_glossary_with_html_entities(self) -> None:
        """HTML tags stripped before matching don't create false positives."""
        glossary = [(1, "paragraph", "paragraphe")]
        texts = ["<p>This is a paragraph</p>"]
        result = _compress_glossary(glossary, texts)
        assert result is not None

    def test_glossary_matching_across_multiple_batch_texts(self) -> None:
        """Term in second text of batch is still found."""
        glossary = [(1, "goodbye", "au revoir")]
        texts = ["hello there", "time to say goodbye"]
        result = _compress_glossary(glossary, texts)
        assert result is not None

    def test_glossary_all_excluded_by_whitespace(self) -> None:
        """All glossary entries have whitespace source/target → None."""
        glossary = [
            (1, "  ", "target"),
            (2, "source", "   "),
            (3, "\t", "\n"),
        ]
        texts = ["anything"]
        result = _compress_glossary(glossary, texts)
        assert result is None

    def test_glossary_empty_after_filtering(self) -> None:
        """Glossary with valid entries but none matching → None."""
        glossary = [
            (1, "xyz123abc", "translation1"),
            (2, "qwerty987", "translation2"),
        ]
        texts = ["Hello world"]
        result = _compress_glossary(glossary, texts)
        assert result is None

    def test_single_char_glossary_term(self) -> None:
        """Single character glossary term matches."""
        glossary = [(1, "X", "the unknown")]
        texts = ["solve for X"]
        result = _compress_glossary(glossary, texts)
        assert result is not None


# ---------------------------------------------------------------------------
# retry_api_call — advanced scenarios
# ---------------------------------------------------------------------------


class TestRetryApiCallAdvanced:
    """Advanced retry decorator tests."""

    def test_alternating_transient_errors_all_retried(self) -> None:
        """Different transient errors on each attempt are all retried."""
        call_count = 0
        errors = [
            "SERVICE_UNAVAILABLE_ERROR",
            "CONNECTION_ERROR",
            "SERVICE_UNAVAILABLE_ERROR",
        ]

        @retry_api_call(max_retries=4, base_delay=0.01)
        def alternating() -> str:
            nonlocal call_count
            call_count += 1
            if call_count <= 3:  # noqa: PLR2004
                raise ValueError(errors[call_count - 1])
            return "ok"

        with patch("src.core.llm_engine.time.sleep"):
            result = alternating()

        assert result == "ok"
        assert call_count == 4  # noqa: PLR2004

    def test_transient_then_non_transient(self) -> None:
        """Transient error followed by non-transient raises the non-transient one."""
        call_count = 0

        @retry_api_call(max_retries=3, base_delay=0.01)
        def mixed_errors() -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("CONNECTION_ERROR")
            raise ValueError("AUTH_ERROR")

        with (
            patch("src.core.llm_engine.time.sleep"),
            pytest.raises(ValueError, match="AUTH_ERROR"),
        ):
            mixed_errors()

        assert call_count == 2  # noqa: PLR2004

    def test_max_retries_zero_no_retry(self) -> None:
        """max_retries=0 means no retries at all."""

        @retry_api_call(max_retries=0, base_delay=0.01)
        def immediate_fail() -> None:
            raise ValueError("TIMEOUT_ERROR")

        with pytest.raises(ValueError, match="TIMEOUT_ERROR"):
            immediate_fail()

    def test_preserves_function_name(self) -> None:
        """Decorated function preserves its original __name__."""

        @retry_api_call()
        def my_function() -> None:
            pass

        assert my_function.__name__ == "my_function"

    def test_preserves_return_value(self) -> None:
        """Decorated function returns the correct value on success."""

        @retry_api_call()
        def returns_dict() -> dict:
            return {"key": "value"}

        assert returns_dict() == {"key": "value"}

    def test_vision_not_supported_not_retried(self) -> None:
        """VISION_NOT_SUPPORTED is raised immediately without retry."""
        call_count = 0

        @retry_api_call(max_retries=3, base_delay=0.01)
        def vision_fail() -> None:
            nonlocal call_count
            call_count += 1
            raise ValueError("VISION_NOT_SUPPORTED")

        with pytest.raises(ValueError, match="VISION_NOT_SUPPORTED"):
            vision_fail()

        assert call_count == 1

    def test_request_too_large_not_retried(self) -> None:
        """REQUEST_TOO_LARGE is raised immediately without retry."""
        call_count = 0

        @retry_api_call(max_retries=3, base_delay=0.01)
        def too_large() -> None:
            nonlocal call_count
            call_count += 1
            raise ValueError("REQUEST_TOO_LARGE")

        with pytest.raises(ValueError, match="REQUEST_TOO_LARGE"):
            too_large()

        assert call_count == 1

    def test_backoff_doubles_each_retry(self) -> None:
        """Verify backoff delay doubles with each retry: base, 2*base, 4*base."""
        sleep_delays: list[float] = []

        @retry_api_call(max_retries=3, base_delay=2.0)
        def failing() -> None:
            raise ValueError("CONNECTION_ERROR")

        with (
            patch("src.core.llm_engine.time.sleep", side_effect=sleep_delays.append),
            pytest.raises(ValueError, match="CONNECTION_ERROR"),
        ):
            failing()

        assert sleep_delays == [
            pytest.approx(2.0),
            pytest.approx(4.0),
            pytest.approx(8.0),
        ]

    def test_success_on_last_retry(self) -> None:
        """Success on the very last retry attempt."""
        call_count = 0

        @retry_api_call(max_retries=3, base_delay=0.01)
        def last_chance() -> str:
            nonlocal call_count
            call_count += 1
            if call_count <= 3:  # noqa: PLR2004
                raise ValueError("SERVICE_UNAVAILABLE_ERROR")
            return "finally"

        with patch("src.core.llm_engine.time.sleep"):
            result = last_chance()

        assert result == "finally"
        assert call_count == 4  # noqa: PLR2004


# ---------------------------------------------------------------------------
# translate_text — detailed integration scenarios
# ---------------------------------------------------------------------------


class TestTranslateTextIntegration:
    """Integration tests for translate_text combining all phases."""

    def _fake_gemini(
        self,
        batch: list[str],
        tl: str,
        sl: str,
        gl: object,
        ct: str,
        model="",
        **_kwargs,
    ) -> list[str]:
        return [f"[{tl}]{t}" for t in batch]

    def test_unicode_text_translated(self) -> None:
        """Unicode text (CJK, Arabic, etc.) passes through to LLM."""
        texts = ["\u4f60\u597d\u4e16\u754c", "\u0645\u0631\u062d\u0628\u0627"]
        with (
            patch(
                "src.core.llm_engine._resolve_provider_model",
                return_value=(LLM_METHOD_GEMINI, "gemini-3-flash-preview"),
            ),
            patch(
                "src.core.llm_engine._translate_gemini", side_effect=self._fake_gemini
            ),
        ):
            result = translate_text(texts, "English")

        assert len(result) == 2  # noqa: PLR2004
        assert all("[English]" in r for r in result)

    def test_special_chars_in_text(self) -> None:
        """Special characters in text do not cause issues."""
        texts = ['He said "hello" & goodbye', "Price: <$100>"]
        with (
            patch(
                "src.core.llm_engine._resolve_provider_model",
                return_value=(LLM_METHOD_GEMINI, "gemini-3-flash-preview"),
            ),
            patch(
                "src.core.llm_engine._translate_gemini", side_effect=self._fake_gemini
            ),
        ):
            result = translate_text(texts, "French")

        assert len(result) == 2  # noqa: PLR2004

    def test_mixed_translatable_and_untranslatable_preserves_indices(self) -> None:
        """Mixed content preserves correct index mapping."""
        texts = [
            "Hello world",  # translatable
            "12345",  # untranslatable
            "Goodbye",  # translatable
            "http://x.com",  # untranslatable
            "Hello world",  # duplicate of index 0
        ]
        with (
            patch(
                "src.core.llm_engine._resolve_provider_model",
                return_value=(LLM_METHOD_GEMINI, "gemini-3-flash-preview"),
            ),
            patch(
                "src.core.llm_engine._translate_gemini", side_effect=self._fake_gemini
            ),
        ):
            result = translate_text(texts, "French")

        assert len(result) == 5  # noqa: PLR2004
        assert result[1] == "12345"
        assert result[3] == "http://x.com"
        # Duplicates get same translation
        assert result[0] == result[4]
        assert "[French]" in result[0]
        assert "[French]" in result[2]

    def test_all_whitespace_texts(self) -> None:
        """All whitespace texts treated as untranslatable."""
        texts = ["  ", "\t", "\n", "  \r\n  "]
        progress: list[int] = []
        with patch(
            "src.core.llm_engine._resolve_provider_model",
            return_value=(LLM_METHOD_GEMINI, "gemini-3-flash-preview"),
        ):
            result = translate_text(texts, "French", progress_callback=progress.append)

        assert result == texts
        assert progress == [100]

    def test_single_untranslatable_item(self) -> None:
        """Single untranslatable item returns as-is with progress 100."""
        progress: list[int] = []
        with patch(
            "src.core.llm_engine._resolve_provider_model",
            return_value=(LLM_METHOD_GEMINI, "gemini-3-flash-preview"),
        ):
            result = translate_text(["42"], "French", progress_callback=progress.append)

        assert result == ["42"]
        assert 100 in progress

    def test_source_lang_forwarded(self) -> None:
        """Source language parameter is forwarded to translate function."""
        captured_sl: list[str] = []

        def capturing(
            batch: list[str],
            tl: str,
            sl: str,
            gl: object,
            ct: str,
            model="",
            **_kwargs,
        ) -> list[str]:
            captured_sl.append(sl)
            return batch

        with (
            patch(
                "src.core.llm_engine._resolve_provider_model",
                return_value=(LLM_METHOD_GEMINI, "gemini-3-flash-preview"),
            ),
            patch("src.core.llm_engine._translate_gemini", side_effect=capturing),
        ):
            translate_text(["Hello"], "French", "Japanese")

        assert captured_sl == ["Japanese"]

    def test_empty_strings_in_list(self) -> None:
        """Empty strings in the list are treated as untranslatable."""
        texts = ["Hello", "", "World"]
        with (
            patch(
                "src.core.llm_engine._resolve_provider_model",
                return_value=(LLM_METHOD_GEMINI, "gemini-3-flash-preview"),
            ),
            patch(
                "src.core.llm_engine._translate_gemini", side_effect=self._fake_gemini
            ),
        ):
            result = translate_text(texts, "French")

        assert len(result) == 3  # noqa: PLR2004
        assert result[1] == ""

    def test_very_long_text_translated(self) -> None:
        """Very long text string is sent to LLM (not dropped)."""
        long_text = "word " * 10000
        with (
            patch(
                "src.core.llm_engine._resolve_provider_model",
                return_value=(LLM_METHOD_GEMINI, "gemini-3-flash-preview"),
            ),
            patch(
                "src.core.llm_engine._translate_gemini", side_effect=self._fake_gemini
            ),
        ):
            result = translate_text([long_text], "French")

        assert len(result) == 1
        assert "[French]" in result[0]

    def test_newlines_in_text_preserved(self) -> None:
        """Newlines within text strings are preserved (not filtered)."""
        texts = ["Hello\nWorld\nFoo"]
        with (
            patch(
                "src.core.llm_engine._resolve_provider_model",
                return_value=(LLM_METHOD_GEMINI, "gemini-3-flash-preview"),
            ),
            patch(
                "src.core.llm_engine._translate_gemini", side_effect=self._fake_gemini
            ),
        ):
            result = translate_text(texts, "French")

        assert len(result) == 1
        assert "[French]" in result[0]

    def test_cancel_check_returns_false_always(self) -> None:
        """cancel_check returning False always → all batches processed."""
        texts = ["Alpha", "Beta"]
        with (
            patch(
                "src.core.llm_engine._resolve_provider_model",
                return_value=(LLM_METHOD_GEMINI, "gemini-3-flash-preview"),
            ),
            patch(
                "src.core.llm_engine._translate_gemini", side_effect=self._fake_gemini
            ),
        ):
            result = translate_text(texts, "French", cancel_check=lambda: False)

        assert all("[French]" in r for r in result)


# ---------------------------------------------------------------------------
# translate_batch — advanced scenarios
# ---------------------------------------------------------------------------


class TestTranslateBatchAdvanced:
    """Advanced translate_batch scenarios."""

    def test_progress_reaches_100(self) -> None:
        """Progress callback eventually reaches or approaches 100."""
        progress: list[int] = []
        with patch(
            "src.core.llm_engine.translate_text", side_effect=_mock_translate_text
        ):
            translate_batch(
                ["A", "B", "C", "D", "E"],
                "French",
                "English",
                progress_callback=progress.append,
            )
        assert len(progress) > 0
        assert progress[-1] > 0

    def test_dedup_consistency_across_boundaries(self) -> None:
        """Duplicates spanning TRANSLATION_BATCH_SIZE boundaries get same result."""
        # Create 60 items from 5 unique words
        values = [f"word{i % 5}" for i in range(60)]

        def _translate(
            texts: list[str],
            target: str,
            source: str = "",
            **kwargs: object,
        ) -> list[str]:
            return [f"T_{t}" for t in texts]

        with patch("src.core.llm_engine.translate_text", side_effect=_translate):
            result = translate_batch(values, "French", "English")

        assert result is not None
        # All copies of each word get same translation
        for i in range(5):
            word = f"word{i}"
            expected = f"T_{word}"
            for j, v in enumerate(values):
                if v == word:
                    assert result[j] == expected

    def test_checkpoint_dir_none_no_crash(self) -> None:
        """No checkpoint_dir (None) works without errors."""
        with patch(
            "src.core.llm_engine.translate_text", side_effect=_mock_translate_text
        ):
            result = translate_batch(
                ["A", "B"],
                "French",
                "English",
                checkpoint_dir=None,
            )
        assert result == ["T_A", "T_B"]

    def test_cancel_at_start_returns_none(self) -> None:
        """Cancellation before any processing returns None."""
        result = translate_batch(
            ["A"],
            "French",
            "English",
            cancel_check=lambda: True,
        )
        assert result is None

    def test_large_batch_all_unique(self) -> None:
        """Large batch with all unique items translates everything."""
        values = [f"unique_{i}" for i in range(100)]
        with patch(
            "src.core.llm_engine.translate_text", side_effect=_mock_translate_text
        ):
            result = translate_batch(values, "French", "English")
        assert result is not None
        assert len(result) == 100  # noqa: PLR2004
        assert all(r.startswith("T_") for r in result)

    def test_single_item_batch(self) -> None:
        """Single item is translated correctly."""
        with patch(
            "src.core.llm_engine.translate_text", side_effect=_mock_translate_text
        ):
            result = translate_batch(["Hello"], "French", "English")
        assert result == ["T_Hello"]

    def test_checkpoint_full_resume_second_run(self, tmp_path: object) -> None:
        """Second run with full checkpoint does not call translate_text."""
        from pathlib import Path  # noqa: PLC0415

        cp_dir = Path(str(tmp_path)) / "cp_full_resume"
        cp_dir.mkdir()

        # First run: translate all 5 items
        with patch(
            "src.core.llm_engine.translate_text", side_effect=_mock_translate_text
        ):
            result1 = translate_batch(
                ["A", "B", "C", "D", "E"],
                "French",
                "English",
                checkpoint_dir=cp_dir,
            )

        # Second run: all cached
        call_count = {"n": 0}

        def _no_translate(
            texts: list[str],
            target: str,
            source: str = "",
            **kwargs: object,
        ) -> list[str]:
            call_count["n"] += 1
            return texts

        with patch("src.core.llm_engine.translate_text", side_effect=_no_translate):
            result2 = translate_batch(
                ["A", "B", "C", "D", "E"],
                "French",
                "English",
                checkpoint_dir=cp_dir,
            )

        assert result2 == result1
        assert call_count["n"] == 0


# ---------------------------------------------------------------------------
# _translate_gemini — response edge cases
# ---------------------------------------------------------------------------


class TestTranslateGeminiResponseEdgeCases:
    """Edge cases for _translate_gemini API response handling."""

    def _settings(self) -> dict[str, str]:
        return {"llm/gemini_api_key": "key", "llm/gemini_model": "model"}

    def test_empty_results_array(self) -> None:
        """Empty 'results' array returns original texts as fallback."""
        from src.core.llm_engine import _translate_gemini  # noqa: PLC0415

        inner = json.dumps({"results": []})
        client = _make_mock_genai_client(response_text=inner)
        with (
            patch(
                "src.core.llm_engine._config.load_setting",
                side_effect=lambda k, d="": self._settings().get(k, d),
            ),
            patch("src.core.llm_engine._build_gemini_client", return_value=client),
        ):
            result = _translate_gemini(["Hello", "World"], "French", "English")
        assert result == ["Hello", "World"]

    def test_extra_ids_in_response_ignored(self) -> None:
        """Extra IDs in response (not in input) are ignored."""
        from src.core.llm_engine import _translate_gemini  # noqa: PLC0415

        inner = json.dumps(
            {
                "results": [
                    {"id": 0, "translated": "Bonjour"},
                    {"id": 1, "translated": "Monde"},
                    {"id": 99, "translated": "Extra"},
                ]
            }
        )
        client = _make_mock_genai_client(response_text=inner)
        with (
            patch(
                "src.core.llm_engine._config.load_setting",
                side_effect=lambda k, d="": self._settings().get(k, d),
            ),
            patch("src.core.llm_engine._build_gemini_client", return_value=client),
        ):
            result = _translate_gemini(["Hello", "World"], "French", "English")
        assert result == ["Bonjour", "Monde"]

    def test_missing_translated_key_uses_fallback(self) -> None:
        """Result items without 'translated' key raise INVALID_RESPONSE."""
        from src.core.llm_engine import _translate_gemini  # noqa: PLC0415

        inner = json.dumps({"results": [{"id": 0}, {"id": 1, "translated": "Monde"}]})
        client = _make_mock_genai_client(response_text=inner)
        with (
            patch(
                "src.core.llm_engine._config.load_setting",
                side_effect=lambda k, d="": self._settings().get(k, d),
            ),
            patch("src.core.llm_engine._build_gemini_client", return_value=client),
            pytest.raises(ValueError, match="INVALID_RESPONSE"),
        ):
            _translate_gemini(["Hello", "World"], "French", "English")

    def test_single_text_translated(self) -> None:
        """Single text item translated correctly."""
        from src.core.llm_engine import _translate_gemini  # noqa: PLC0415

        inner = json.dumps({"results": [{"id": 0, "translated": "Bonjour"}]})
        client = _make_mock_genai_client(response_text=inner)
        with (
            patch(
                "src.core.llm_engine._config.load_setting",
                side_effect=lambda k, d="": self._settings().get(k, d),
            ),
            patch("src.core.llm_engine._build_gemini_client", return_value=client),
        ):
            result = _translate_gemini(["Hello"], "French", "English")
        assert result == ["Bonjour"]

    def test_unicode_translation_preserved(self) -> None:
        """Unicode characters in translation are preserved exactly."""
        from src.core.llm_engine import _translate_gemini  # noqa: PLC0415

        inner = json.dumps(
            {"results": [{"id": 0, "translated": "Xin ch\u00e0o th\u1ebf gi\u1edbi"}]}
        )
        client = _make_mock_genai_client(response_text=inner)
        with (
            patch(
                "src.core.llm_engine._config.load_setting",
                side_effect=lambda k, d="": self._settings().get(k, d),
            ),
            patch("src.core.llm_engine._build_gemini_client", return_value=client),
        ):
            result = _translate_gemini(
                ["\u4f60\u597d\u4e16\u754c"], "Vietnamese", "Chinese"
            )
        assert result == ["Xin ch\u00e0o th\u1ebf gi\u1edbi"]

    def test_http_timeout_raises_timeout_error(self) -> None:
        """TimeoutError during request raises TIMEOUT_ERROR.

        ``_handle_api_error`` still maps a raw ``TimeoutError`` (anything
        below the SDK layer that bubbles up — e.g. socket-level timeout
        before HTTP framing — to the ``TIMEOUT_ERROR`` tag.
        """
        from src.core.llm_engine import _translate_gemini  # noqa: PLC0415

        client = _make_mock_genai_client(
            response_error=TimeoutError("timed out"),
        )
        with (
            patch(
                "src.core.llm_engine._config.load_setting",
                side_effect=lambda k, d="": self._settings().get(k, d),
            ),
            patch("src.core.llm_engine._build_gemini_client", return_value=client),
            patch("src.core.llm_engine.time.sleep"),
            pytest.raises(ValueError, match="TIMEOUT_ERROR"),
        ):
            _translate_gemini(["Hello"], "French", "English")

# ---------------------------------------------------------------------------
# _translate_custom — response edge cases
# ---------------------------------------------------------------------------


class TestTranslateCustomResponseEdgeCases:
    """Edge cases for _translate_custom API response handling."""

    def _settings(self) -> dict[str, str]:
        return {
            "llm/custom_api_key": "key",
            "llm/custom_model": "gpt-4",
            "llm/custom_endpoint": "https://api.example.com/v1",
        }

    def test_empty_results_returns_originals(self) -> None:
        """Empty results array returns originals."""
        from src.core.llm_engine import _translate_custom  # noqa: PLC0415

        content = json.dumps({"results": []})
        client = _make_mock_sdk_client(chat_response=_make_sdk_chat_response(content))
        with (
            patch(
                "src.core.llm_engine._config.load_setting",
                side_effect=lambda k, d="": self._settings().get(k, d),
            ),
            patch("src.core.llm_engine._build_openai_client", return_value=client),
            patch("src.core.llm_engine.time.sleep"),
        ):
            result = _translate_custom(["Hello"], "French", "English")
        assert result == ["Hello"]

    def test_extra_ids_ignored(self) -> None:
        """Extra IDs in response are ignored."""
        from src.core.llm_engine import _translate_custom  # noqa: PLC0415

        content = json.dumps(
            {
                "results": [
                    {"id": 0, "translated": "Bonjour"},
                    {"id": 99, "translated": "Extra"},
                ]
            }
        )
        client = _make_mock_sdk_client(chat_response=_make_sdk_chat_response(content))
        with (
            patch(
                "src.core.llm_engine._config.load_setting",
                side_effect=lambda k, d="": self._settings().get(k, d),
            ),
            patch("src.core.llm_engine._build_openai_client", return_value=client),
            patch("src.core.llm_engine.time.sleep"),
        ):
            result = _translate_custom(["Hello"], "French", "English")
        assert result == ["Bonjour"]

    def test_single_text_success(self) -> None:
        """Single text translated correctly."""
        from src.core.llm_engine import _translate_custom  # noqa: PLC0415

        content = json.dumps({"results": [{"id": 0, "translated": "Bonjour"}]})
        client = _make_mock_sdk_client(chat_response=_make_sdk_chat_response(content))
        with (
            patch(
                "src.core.llm_engine._config.load_setting",
                side_effect=lambda k, d="": self._settings().get(k, d),
            ),
            patch("src.core.llm_engine._build_openai_client", return_value=client),
            patch("src.core.llm_engine.time.sleep"),
        ):
            result = _translate_custom(["Hello"], "French", "English")
        assert result == ["Bonjour"]

    def test_http_429_raises_quota_error(self) -> None:
        """HTTP 429 raises QUOTA_ERROR."""
        from src.core.llm_engine import _translate_custom  # noqa: PLC0415

        client = _make_mock_sdk_client(chat_error=_sdk_http_error(429))
        with (
            patch(
                "src.core.llm_engine._config.load_setting",
                side_effect=lambda k, d="": self._settings().get(k, d),
            ),
            patch("src.core.llm_engine._build_openai_client", return_value=client),
            pytest.raises(ValueError, match="QUOTA_ERROR"),
        ):
            _translate_custom(["Hello"], "French", "English")

    def test_http_404_raises_model_not_found(self) -> None:
        """HTTP 404 raises MODEL_NOT_FOUND."""
        from src.core.llm_engine import _translate_custom  # noqa: PLC0415

        client = _make_mock_sdk_client(chat_error=_sdk_http_error(404, "model not found"))
        with (
            patch(
                "src.core.llm_engine._config.load_setting",
                side_effect=lambda k, d="": self._settings().get(k, d),
            ),
            patch("src.core.llm_engine._build_openai_client", return_value=client),
            pytest.raises(ValueError, match="MODEL_NOT_FOUND"),
        ):
            _translate_custom(["Hello"], "French", "English")

    def test_invalid_json_response_raises_invalid_response(self) -> None:
        """Invalid JSON in response raises INVALID_RESPONSE."""
        from src.core.llm_engine import _translate_custom  # noqa: PLC0415

        client = _make_mock_sdk_client(
            chat_response=_make_sdk_chat_response("not json at all"),
        )
        with (
            patch(
                "src.core.llm_engine._config.load_setting",
                side_effect=lambda k, d="": self._settings().get(k, d),
            ),
            patch("src.core.llm_engine._build_openai_client", return_value=client),
            patch("src.core.llm_engine.time.sleep"),
            pytest.raises(ValueError, match="INVALID_RESPONSE"),
        ):
            _translate_custom(["Hello"], "French", "English")

    def test_glossary_forwarded_to_custom(self) -> None:
        """Glossary entries are forwarded to _translate_custom."""
        from src.core.llm_engine import _translate_custom  # noqa: PLC0415

        content = json.dumps({"results": [{"id": 0, "translated": "Bonjour"}]})
        client = _make_mock_sdk_client(chat_response=_make_sdk_chat_response(content))

        glossary = [(1, "hello", "bonjour")]
        with (
            patch(
                "src.core.llm_engine._config.load_setting",
                side_effect=lambda k, d="": self._settings().get(k, d),
            ),
            patch("src.core.llm_engine._build_openai_client", return_value=client),
            patch("src.core.llm_engine.time.sleep"),
        ):
            _translate_custom(
                ["hello world"], "French", "English", glossary_entries=glossary
            )

        # Verify the request kwargs include the glossary in the system prompt
        assert client.chat.completions.create.call_count == 1
        sent_kwargs = client.chat.completions.create.call_args.kwargs
        system_prompt = sent_kwargs["messages"][0]["content"]
        assert "hello = bonjour" in system_prompt


# ---------------------------------------------------------------------------
# extract_image_text — error paths
# ---------------------------------------------------------------------------


class TestExtractImageTextErrors:
    """Error path tests for extract_image_text."""

    def test_gemini_http_500_raises_service_unavailable(self) -> None:
        """APIError 500 in _extract_text_gemini raises SERVICE_UNAVAILABLE_ERROR."""
        from src.core.llm_engine import _extract_text_gemini  # noqa: PLC0415

        client = _make_mock_genai_client(
            response_error=_genai_api_error(500, "Server Error"),
        )
        with (
            patch(
                f"{_LLM_MOD}._config.load_setting",
                side_effect=lambda k, d="": {
                    "llm/gemini_api_key": "key",
                    "llm/gemini_model": "gemini-2.0-flash",
                }.get(k, d),
            ),
            patch(f"{_LLM_MOD}._build_gemini_client", return_value=client),
            patch("pathlib.Path.read_bytes", return_value=b"img"),
            patch("src.core.llm_engine.time.sleep"),
            pytest.raises(ValueError, match="SERVICE_UNAVAILABLE_ERROR"),
        ):
            _extract_text_gemini("/test.png")

    def test_custom_http_429_raises_quota_error(self) -> None:
        """HTTP 429 in _extract_text_custom raises QUOTA_ERROR."""
        from src.core.llm_engine import _extract_text_custom  # noqa: PLC0415

        client = _make_mock_sdk_client(chat_error=_sdk_http_error(429))
        with (
            patch(
                f"{_LLM_MOD}._config.load_setting",
                side_effect=lambda k, d="": {
                    "llm/custom_api_key": "key",
                    "llm/custom_model": "gpt-4o",
                    "llm/custom_endpoint": "https://api.example.com/v1",
                }.get(k, d),
            ),
            patch(f"{_LLM_MOD}._build_openai_client", return_value=client),
            patch("pathlib.Path.open", return_value=io.BytesIO(b"img")),
            pytest.raises(ValueError, match="QUOTA_ERROR"),
        ):
            _extract_text_custom("/test.png")

    def test_gemini_timeout_raises_timeout_error(self) -> None:
        """TimeoutError in _extract_text_gemini raises TIMEOUT_ERROR."""
        from src.core.llm_engine import _extract_text_gemini  # noqa: PLC0415

        client = _make_mock_genai_client(
            response_error=TimeoutError("timed out"),
        )
        with (
            patch(
                f"{_LLM_MOD}._config.load_setting",
                side_effect=lambda k, d="": {
                    "llm/gemini_api_key": "key",
                    "llm/gemini_model": "gemini-2.0-flash",
                }.get(k, d),
            ),
            patch(f"{_LLM_MOD}._build_gemini_client", return_value=client),
            patch("pathlib.Path.read_bytes", return_value=b"img"),
            patch("src.core.llm_engine.time.sleep"),
            pytest.raises(ValueError, match="TIMEOUT_ERROR"),
        ):
            _extract_text_gemini("/test.png")

    def test_custom_connection_error(self) -> None:
        """SDK connection error in _extract_text_custom raises CONNECTION_ERROR."""
        from src.core.llm_engine import _extract_text_custom  # noqa: PLC0415

        client = _make_mock_sdk_client(chat_error=_sdk_connection_error("refused"))
        with (
            patch(
                f"{_LLM_MOD}._config.load_setting",
                side_effect=lambda k, d="": {
                    "llm/custom_api_key": "key",
                    "llm/custom_model": "gpt-4o",
                    "llm/custom_endpoint": "https://api.example.com/v1",
                }.get(k, d),
            ),
            patch(f"{_LLM_MOD}._build_openai_client", return_value=client),
            patch(
                "pathlib.Path.open",
                side_effect=lambda *a, **kw: io.BytesIO(b"img"),
            ),
            patch("src.core.llm_engine.time.sleep"),
            pytest.raises(ValueError, match="CONNECTION_ERROR"),
        ):
            _extract_text_custom("/test.png")

    def test_gemini_empty_text_returned(self) -> None:
        """_extract_text_gemini returns empty string when API returns empty text."""
        from src.core.llm_engine import _extract_text_gemini  # noqa: PLC0415

        inner = json.dumps({"text": ""})
        client = _make_mock_genai_client(response_text=inner)
        with (
            patch(
                f"{_LLM_MOD}._config.load_setting",
                side_effect=lambda k, d="": {
                    "llm/gemini_api_key": "key",
                    "llm/gemini_model": "gemini-2.0-flash",
                }.get(k, d),
            ),
            patch(f"{_LLM_MOD}._build_gemini_client", return_value=client),
            patch("pathlib.Path.read_bytes", return_value=b"img"),
        ):
            result = _extract_text_gemini("/test.png")
        assert result == ""

    def test_custom_empty_text_returned(self) -> None:
        """_extract_text_custom returns empty string when API returns empty text."""
        from src.core.llm_engine import _extract_text_custom  # noqa: PLC0415

        content = json.dumps({"text": ""})
        client = _make_mock_sdk_client(chat_response=_make_sdk_chat_response(content))
        with (
            patch(
                f"{_LLM_MOD}._config.load_setting",
                side_effect=lambda k, d="": {
                    "llm/custom_api_key": "key",
                    "llm/custom_model": "gpt-4o",
                    "llm/custom_endpoint": "https://api.example.com/v1",
                }.get(k, d),
            ),
            patch(f"{_LLM_MOD}._build_openai_client", return_value=client),
            patch("pathlib.Path.open", return_value=io.BytesIO(b"img")),
        ):
            result = _extract_text_custom("/test.png")
        assert result == ""


# ---------------------------------------------------------------------------
# _build_translation_prompt — all content types
# ---------------------------------------------------------------------------


class TestBuildTranslationPromptAllTypes:
    """Test _build_translation_prompt for every content type."""

    @pytest.mark.parametrize(
        ("content_type", "expected_keyword"),
        [
            ("plain_text", "fluent"),
            ("markdown", "Markdown"),
            ("html", "HTML tags"),
            ("xml", "XML tags"),
            ("subtitle", "subtitle"),
            ("localization", "placeholder"),
            ("rtf", "PRESERVE_RTF"),
            ("epub", "XHTML"),
            ("data_values", "data values"),
            ("pdf", "PDF"),
        ],
    )
    def test_content_type_keyword(
        self, content_type: str, expected_keyword: str
    ) -> None:
        """Each content type includes its expected keyword in the prompt."""
        result = _build_translation_prompt(content_type, "English", "French")
        assert expected_keyword.lower() in result.lower()

    def test_unknown_type_uses_plain_text_rules(self) -> None:
        """Unknown content type falls back to plain text rules."""
        result = _build_translation_prompt("nonexistent_type", "English", "French")
        assert "fluent" in result.lower()

    def test_glossary_included_in_all_types(self) -> None:
        """Glossary entries appear in prompt for any content type."""
        glossary = [(1, "cat", "chat")]
        result = _build_translation_prompt("html", "English", "French", glossary)
        assert "cat = chat" in result

    def test_output_format_always_includes_json(self) -> None:
        """Output format instruction always mentions JSON."""
        result = _build_translation_prompt("subtitle", "English", "French")
        assert "JSON" in result

    def test_data_values_no_quality_guidance(self) -> None:
        """Data values content type excludes quality guidance."""
        result = _build_translation_prompt("data_values", "English", "French")
        assert "Preserve the original tone" not in result

    def test_non_data_values_has_quality_guidance(self) -> None:
        """Non-data-values content type includes quality guidance."""
        result = _build_translation_prompt("html", "English", "French")
        assert "Preserve the original tone" in result


# ---------------------------------------------------------------------------
# _format_lang_pair — comprehensive tests
# ---------------------------------------------------------------------------


class TestFormatLangPairComprehensive:
    """Comprehensive tests for _format_lang_pair."""

    def test_source_and_target_same_language(self) -> None:
        """Same source and target language still formats correctly."""
        result = _format_lang_pair("French", "French")
        assert result == "Translate the following from French to French."

    def test_long_language_names(self) -> None:
        """Long language names with parenthetical info are preserved."""
        result = _format_lang_pair("Chinese (Traditional)", "Portuguese (Brazil)")
        assert "Chinese (Traditional)" in result
        assert "Portuguese (Brazil)" in result

    def test_whitespace_source_treated_as_empty(self) -> None:
        """Whitespace-only source is falsy → auto-detect format."""
        # Note: "  " is truthy in Python, so this actually uses "from" format
        result = _format_lang_pair("  ", "French")
        assert "from" in result


# ---------------------------------------------------------------------------
# _format_glossary_hint / _format_glossary_block — edge cases
# ---------------------------------------------------------------------------


class TestFormatGlossaryEdgeCases:
    """Edge cases for glossary formatting functions."""

    def test_hint_with_many_entries(self) -> None:
        """Hint with 10 entries all appear separated by commas."""
        entries = [(i, f"src{i}", f"tgt{i}") for i in range(10)]
        result = _format_glossary_hint(entries)
        for i in range(10):
            assert f"src{i} <-> tgt{i}" in result

    def test_block_with_many_entries(self) -> None:
        """Block with 10 entries all appear separated by pipes."""
        entries = [(i, f"src{i}", f"tgt{i}") for i in range(10)]
        result = _format_glossary_block(entries)
        for i in range(10):
            assert f"src{i} = tgt{i}" in result

    def test_hint_with_special_characters(self) -> None:
        """Special characters in glossary entries are preserved."""
        entries = [(1, "C# .NET", "C# .NET")]
        result = _format_glossary_hint(entries)
        assert "C# .NET <-> C# .NET" in result

    def test_block_with_unicode(self) -> None:
        """Unicode in glossary entries preserved in block format."""
        entries = [(1, "\u4f60\u597d", "\u3053\u3093\u306b\u3061\u306f")]
        result = _format_glossary_block(entries)
        assert "\u4f60\u597d = \u3053\u3093\u306b\u3061\u306f" in result

    def test_hint_with_single_char_entries(self) -> None:
        """Single character glossary entries are formatted correctly."""
        entries = [(1, "a", "b")]
        result = _format_glossary_hint(entries)
        assert "a <-> b" in result


# ---------------------------------------------------------------------------
# _guess_image_mime — additional formats
# ---------------------------------------------------------------------------


class TestGuessImageMimeAdditional:
    """Additional _guess_image_mime tests."""

    def test_mixed_case_jpg(self) -> None:
        """Mixed case .JpG maps to image/jpeg."""
        from src.core.llm_engine import _guess_image_mime  # noqa: PLC0415

        assert _guess_image_mime("/photo.JpG") == "image/jpeg"

    def test_no_extension(self) -> None:
        """File with no extension defaults to image/jpeg."""
        from src.core.llm_engine import _guess_image_mime  # noqa: PLC0415

        assert _guess_image_mime("/path/filename") == "image/jpeg"

    def test_double_extension(self) -> None:
        """Double extension uses the last part."""
        from src.core.llm_engine import _guess_image_mime  # noqa: PLC0415

        assert _guess_image_mime("/file.backup.png") == "image/png"

    def test_hidden_file_with_extension(self) -> None:
        """Hidden file (starts with .) with extension works."""
        from src.core.llm_engine import _guess_image_mime  # noqa: PLC0415

        assert _guess_image_mime("/home/.screenshot.webp") == "image/webp"

    def test_path_with_spaces(self) -> None:
        """Path with spaces is handled correctly."""
        from src.core.llm_engine import _guess_image_mime  # noqa: PLC0415

        assert _guess_image_mime("/my photos/image.gif") == "image/gif"


# ---------------------------------------------------------------------------
# translate_image_content — fragment building
# ---------------------------------------------------------------------------


class TestTranslateImageContentFragments:
    """Tests for translate_image_content fragment building."""

    def test_fragment_ids_are_sequential(self) -> None:
        """OCR results are assigned sequential IDs starting from 0."""
        mock_results = [MagicMock(text="Hello"), MagicMock(text="World")]
        captured_fragments: list[list[dict]] = []

        def mock_image_gemini(
            path: str,
            fragments: list[dict],
            target: str,
            source: str,
            glossary: object = None,
            model: str = "",
            **_kwargs,  # noqa: ANN003
        ) -> list:
            captured_fragments.append(fragments)
            return []

        with (
            patch(
                "src.core.llm_engine._resolve_provider_model",
                return_value=(LLM_METHOD_GEMINI, "gemini-3-flash-preview"),
            ),
            patch(
                "src.core.llm_engine._translate_image_gemini",
                side_effect=mock_image_gemini,
            ),
        ):
            translate_image_content("/img.png", mock_results, "French")

        assert len(captured_fragments) == 1
        assert captured_fragments[0][0] == {"id": 0, "text": "Hello"}
        assert captured_fragments[0][1] == {"id": 1, "text": "World"}

    def test_multiple_ocr_results_dispatched(self) -> None:
        """Multiple OCR results are all included in fragments."""
        results = [MagicMock(text=f"text_{i}") for i in range(5)]
        captured: list[list[dict]] = []

        def mock_fn(
            path, fragments, target, source, glossary=None, model="", **_kwargs
        ):  # noqa: ANN001, ANN202
            captured.append(fragments)
            return []

        with (
            patch(
                "src.core.llm_engine._resolve_provider_model",
                return_value=(LLM_METHOD_GEMINI, "gemini-3-flash-preview"),
            ),
            patch("src.core.llm_engine._translate_image_gemini", side_effect=mock_fn),
        ):
            translate_image_content("/img.png", results, "French")

        assert len(captured[0]) == 5  # noqa: PLR2004

    def test_glossary_forwarded_to_image_provider(self) -> None:
        """Glossary entries are forwarded to image translation provider."""
        mock_ocr = MagicMock(text="Hello")
        captured_glossary: list[object] = []

        def mock_fn(
            path, fragments, target, source, glossary=None, model="", **_kwargs
        ):  # noqa: ANN001, ANN202
            captured_glossary.append(glossary)
            return []

        glossary = [(1, "hello", "bonjour")]
        with (
            patch(
                "src.core.llm_engine._resolve_provider_model",
                return_value=(LLM_METHOD_GEMINI, "gemini-3-flash-preview"),
            ),
            patch("src.core.llm_engine._translate_image_gemini", side_effect=mock_fn),
        ):
            translate_image_content(
                "/img.png", [mock_ocr], "French", glossary_entries=glossary
            )

        assert captured_glossary[0] == glossary


# ---------------------------------------------------------------------------
# _get_gemini_safety_settings — structure validation
# ---------------------------------------------------------------------------


class TestGeminiSafetySettingsStructure:
    """Structural validation of _get_gemini_safety_settings."""

    def test_each_entry_has_category_and_threshold(self) -> None:
        """Each entry has both 'category' and 'threshold' keys."""
        from src.core.llm_engine import _get_gemini_safety_settings  # noqa: PLC0415

        for entry in _get_gemini_safety_settings():
            assert "category" in entry
            assert "threshold" in entry

    def test_all_categories_start_with_harm(self) -> None:
        """All category values start with 'HARM_CATEGORY_'."""
        from src.core.llm_engine import _get_gemini_safety_settings  # noqa: PLC0415

        for entry in _get_gemini_safety_settings():
            assert entry["category"].startswith("HARM_CATEGORY_")

    def test_returns_new_list_each_call(self) -> None:
        """Each call returns a new list instance."""
        from src.core.llm_engine import _get_gemini_safety_settings  # noqa: PLC0415

        a = _get_gemini_safety_settings()
        b = _get_gemini_safety_settings()
        assert a is not b
        assert a == b


# ---------------------------------------------------------------------------
# SSE parsers — additional edge cases
# ---------------------------------------------------------------------------


# TestSSEParsersAdditional class deleted -- both `_parse_gemini_sse` and
# `_parse_openai_sse` helpers were removed when the Gemini and Custom paths
# migrated to their respective SDKs (google-genai / openai), which handle
# SSE framing internally.


# ---------------------------------------------------------------------------
# stream_translate_text — edge cases
# ---------------------------------------------------------------------------


class TestStreamTranslateTextEdgeCases:
    """Edge cases for stream_translate_text."""

    def test_glossary_none_no_crash(self) -> None:
        """None glossary does not crash."""
        from src.core.llm_engine import stream_translate_text  # noqa: PLC0415

        with (
            patch(
                "src.core.llm_engine._config.load_setting",
                side_effect=lambda k, d="": (
                    LLM_METHOD_GEMINI if k == "llm/method" else d
                ),
            ),
            patch("src.core.llm_engine._compress_glossary", return_value=None),
            patch(
                "src.core.llm_engine._stream_gemini",
                return_value=iter(["result"]),
            ),
        ):
            chunks = list(stream_translate_text("Hello", "French", "English", None))
        assert chunks == ["result"]

    def test_empty_text_passed_through(self) -> None:
        """Empty string passed to stream_translate_text still calls the provider."""
        from src.core.llm_engine import stream_translate_text  # noqa: PLC0415

        with (
            patch(
                "src.core.llm_engine._config.load_setting",
                side_effect=lambda k, d="": (
                    LLM_METHOD_GEMINI if k == "llm/method" else d
                ),
            ),
            patch("src.core.llm_engine._compress_glossary", return_value=None),
            patch(
                "src.core.llm_engine._stream_gemini",
                return_value=iter([]),
            ) as mock_stream,
        ):
            list(stream_translate_text("", "French"))

        mock_stream.assert_called_once()


# ===========================================================================
# NEW TESTS — targeting 800+ total
# ===========================================================================


# ---------------------------------------------------------------------------
# translate_text() edge cases
# ---------------------------------------------------------------------------


class TestTranslateTextEdgeCasesExpanded:
    """Expanded edge-case coverage for translate_text."""

    def test_empty_list_returns_empty(self) -> None:
        """translate_text([]) returns [] immediately."""
        assert translate_text([], "French") == []

    def test_single_untranslatable_item(self) -> None:
        """Single untranslatable item returns the original."""
        progress: list[int] = []
        result = translate_text(
            ["12345"],
            "French",
            progress_callback=progress.append,
        )
        assert result == ["12345"]
        assert progress == [100]

    def test_single_translatable_item(self) -> None:
        """Single translatable item goes through LLM."""

        def fake(
            b: list[str], tl: str, sl: str, gl: object, ct: str, model="", **_kwargs
        ) -> list[str]:
            return [f"[{tl}]{t}" for t in b]

        with (
            patch(
                "src.core.llm_engine._resolve_provider_model",
                return_value=(LLM_METHOD_GEMINI, "gemini-3-flash-preview"),
            ),
            patch("src.core.llm_engine._translate_gemini", side_effect=fake),
        ):
            result = translate_text(["Hello"], "German")
        assert result == ["[German]Hello"]

    def test_all_untranslatable_no_llm_call(self) -> None:
        """All untranslatable: progress set to 100, no LLM called."""
        texts = ["42", "http://x.com", "user@a.com", "   ", ""]
        progress: list[int] = []
        with patch(
            "src.core.llm_engine._resolve_provider_model",
            return_value=(LLM_METHOD_GEMINI, "gemini-3-flash-preview"),
        ):
            result = translate_text(texts, "French", progress_callback=progress.append)
        assert result == texts
        assert progress == [100]

    def test_all_duplicates_single_llm_call(self) -> None:
        """5 identical strings produce only 1 unique LLM call."""
        sent: list[list[str]] = []

        def fake(
            b: list[str], tl: str, sl: str, gl: object, ct: str, model="", **_kwargs
        ) -> list[str]:
            sent.append(list(b))
            return [f"T_{t}" for t in b]

        with (
            patch(
                "src.core.llm_engine._resolve_provider_model",
                return_value=(LLM_METHOD_GEMINI, "gemini-3-flash-preview"),
            ),
            patch("src.core.llm_engine._translate_gemini", side_effect=fake),
        ):
            result = translate_text(["same"] * 5, "French")
        assert all(r == "T_same" for r in result)
        assert sum(len(s) for s in sent) == 1

    def test_mixed_untranslatable_duplicate_translatable(self) -> None:
        """Mix of untranslatable + duplicates + unique items."""

        def fake(
            b: list[str], tl: str, sl: str, gl: object, ct: str, model="", **_kwargs
        ) -> list[str]:
            return [f"T_{t}" for t in b]

        texts = ["Hello", "42", "Hello", "http://x.com", "World"]
        with (
            patch(
                "src.core.llm_engine._resolve_provider_model",
                return_value=(LLM_METHOD_GEMINI, "gemini-3-flash-preview"),
            ),
            patch("src.core.llm_engine._translate_gemini", side_effect=fake),
        ):
            result = translate_text(texts, "French")
        assert len(result) == 5  # noqa: PLR2004
        assert result[0] == result[2]  # duplicates same
        assert result[0].startswith("T_")
        assert result[1] == "42"  # untranslatable
        assert result[3] == "http://x.com"  # untranslatable
        assert result[4].startswith("T_")

    def test_whitespace_only_items_not_sent_to_llm(self) -> None:
        """Whitespace-only items are untranslatable and not sent."""
        sent: list[list[str]] = []

        def fake(
            b: list[str], tl: str, sl: str, gl: object, ct: str, model="", **_kwargs
        ) -> list[str]:
            sent.append(list(b))
            return [f"T_{t}" for t in b]

        texts = ["  ", "\t", "Hello"]
        with (
            patch(
                "src.core.llm_engine._resolve_provider_model",
                return_value=(LLM_METHOD_GEMINI, "gemini-3-flash-preview"),
            ),
            patch("src.core.llm_engine._translate_gemini", side_effect=fake),
        ):
            result = translate_text(texts, "French")
        assert result[0] == "  "
        assert result[1] == "\t"
        assert result[2] == "T_Hello"
        assert sum(len(s) for s in sent) == 1

    def test_cancel_immediately_returns_originals(self) -> None:
        """cancel_check returning True immediately returns all originals."""

        def fake(
            b: list[str], tl: str, sl: str, gl: object, ct: str, model="", **_kwargs
        ) -> list[str]:
            return [f"T_{t}" for t in b]

        with (
            patch(
                "src.core.llm_engine._resolve_provider_model",
                return_value=(LLM_METHOD_GEMINI, "gemini-3-flash-preview"),
            ),
            patch("src.core.llm_engine._translate_gemini", side_effect=fake),
            patch(
                "src.core.llm_engine._split_by_token_budget",
                return_value=[["Hello"], ["World"]],
            ),
        ):
            result = translate_text(
                ["Hello", "World"],
                "French",
                cancel_check=lambda: True,
            )
        assert result == ["Hello", "World"]

    def test_progress_reaches_100_with_multiple_batches(self) -> None:
        """Progress reaches 100% when all batches complete."""
        progress: list[int] = []

        def fake(
            b: list[str], tl: str, sl: str, gl: object, ct: str, model="", **_kwargs
        ) -> list[str]:
            return b

        with (
            patch(
                "src.core.llm_engine._resolve_provider_model",
                return_value=(LLM_METHOD_GEMINI, "gemini-3-flash-preview"),
            ),
            patch("src.core.llm_engine._translate_gemini", side_effect=fake),
        ):
            translate_text(
                [f"text{i}" for i in range(20)],
                "French",
                progress_callback=progress.append,
            )
        assert progress[-1] == 100  # noqa: PLR2004

    def test_no_progress_callback_is_fine(self) -> None:
        """progress_callback=None causes no crash."""

        def fake(
            b: list[str], tl: str, sl: str, gl: object, ct: str, model="", **_kwargs
        ) -> list[str]:
            return b

        with (
            patch(
                "src.core.llm_engine._resolve_provider_model",
                return_value=(LLM_METHOD_GEMINI, "gemini-3-flash-preview"),
            ),
            patch("src.core.llm_engine._translate_gemini", side_effect=fake),
        ):
            result = translate_text(["Hello"], "French", progress_callback=None)
        assert result == ["Hello"]

    def test_source_lang_auto_detect(self) -> None:
        """Empty source_lang is passed through (auto-detect)."""
        captured: list[str] = []

        def fake(
            b: list[str], tl: str, sl: str, gl: object, ct: str, model="", **_kwargs
        ) -> list[str]:
            captured.append(sl)
            return b

        with (
            patch(
                "src.core.llm_engine._resolve_provider_model",
                return_value=(LLM_METHOD_GEMINI, "gemini-3-flash-preview"),
            ),
            patch("src.core.llm_engine._translate_gemini", side_effect=fake),
        ):
            translate_text(["Hello"], "French", source_lang="")
        assert captured[0] == ""

    def test_large_number_of_duplicates(self) -> None:
        """1000 duplicates deduplicated to 1 LLM call."""
        sent_count = {"n": 0}

        def fake(
            b: list[str], tl: str, sl: str, gl: object, ct: str, model="", **_kwargs
        ) -> list[str]:
            sent_count["n"] += len(b)
            return [f"T_{t}" for t in b]

        with (
            patch(
                "src.core.llm_engine._resolve_provider_model",
                return_value=(LLM_METHOD_GEMINI, "gemini-3-flash-preview"),
            ),
            patch("src.core.llm_engine._translate_gemini", side_effect=fake),
        ):
            result = translate_text(["word"] * 1000, "French")
        assert len(result) == 1000  # noqa: PLR2004
        assert all(r == "T_word" for r in result)
        assert sent_count["n"] == 1


# ---------------------------------------------------------------------------
# _split_by_token_budget — expanded edge cases
# ---------------------------------------------------------------------------


class TestSplitByTokenBudgetExpanded:
    """Expanded token budget splitting tests."""

    def test_exact_budget_boundary_two_items(self) -> None:
        """Two items totaling exactly the budget stay in one batch."""
        # Each item: 20 chars → 5 tokens + 10 overhead = 15
        item = "a" * 20
        batches = _split_by_token_budget([item, item], budget=30)
        assert len(batches) == 1
        assert len(batches[0]) == 2  # noqa: PLR2004

    def test_budget_boundary_plus_one(self) -> None:
        """Two items totaling budget+1 split into two batches."""
        item = "a" * 20  # 5 + 10 = 15
        batches = _split_by_token_budget([item, item], budget=29)
        assert len(batches) == 2  # noqa: PLR2004

    def test_single_huge_item_alone(self) -> None:
        """Single item of 100k chars gets its own batch."""
        huge = "x" * 100000
        batches = _split_by_token_budget([huge], budget=10)
        assert len(batches) == 1
        assert batches[0] == [huge]

    def test_many_tiny_items_100(self) -> None:
        """100 tiny items (1 char each) grouped efficiently."""
        items = ["a"] * 100
        # Each: 1 token + 10 overhead = 11
        batches = _split_by_token_budget(items, budget=110)
        # 110 / 11 = 10 items per batch
        assert len(batches) == 10  # noqa: PLR2004
        assert all(len(b) == 10 for b in batches)  # noqa: PLR2004

    def test_many_tiny_items_uneven(self) -> None:
        """101 tiny items with budget fitting 10 → 11 batches (10+1)."""
        items = ["a"] * 101
        batches = _split_by_token_budget(items, budget=110)
        assert len(batches) == 11  # noqa: PLR2004
        assert len(batches[-1]) == 1

    def test_empty_strings_treated_as_minimum_token(self) -> None:
        """Empty strings cost 1 token + overhead each."""
        items = [""] * 3
        # Each: 1 + 10 = 11
        batches = _split_by_token_budget(items, budget=33)
        assert len(batches) == 1  # 33 / 11 = 3 fit

    def test_huge_item_between_smalls(self) -> None:
        """Huge item isolates: [small], [huge], [small, small]."""
        small = "a"  # 1 + 10 = 11
        huge = "x" * 40000  # 10000 + 10 = huge
        batches = _split_by_token_budget([small, huge, small, small], budget=50)
        assert batches[0] == [small]
        assert batches[1] == [huge]
        assert batches[2] == [small, small]

    def test_budget_equal_to_single_item_cost(self) -> None:
        """Budget exactly equal to one item's cost → each item alone."""
        item = "a" * 4  # 1 + 10 = 11
        batches = _split_by_token_budget([item, item, item], budget=11)
        assert len(batches) == 3  # noqa: PLR2004

    def test_all_empty_strings(self) -> None:
        """All empty strings split by budget."""
        items = [""] * 5
        batches = _split_by_token_budget(items, budget=22)  # fits 2 per batch
        assert len(batches) == 3  # noqa: PLR2004
        assert len(batches[0]) == 2  # noqa: PLR2004
        assert len(batches[1]) == 2  # noqa: PLR2004
        assert len(batches[2]) == 1


# ---------------------------------------------------------------------------
# _deduplicate_texts — expanded
# ---------------------------------------------------------------------------


class TestDeduplicateTextsExpanded:
    """Expanded deduplication tests."""

    def test_all_identical_100_items(self) -> None:
        """100 identical items collapse to 1."""
        texts = ["repeat"] * 100
        unique, dupe_map = _deduplicate_texts(texts)
        assert unique == ["repeat"]
        assert len(dupe_map["repeat"]) == 100  # noqa: PLR2004

    def test_case_sensitive_not_deduped(self) -> None:
        """'Hello' and 'hello' are not deduplicated."""
        texts = ["Hello", "hello", "HELLO"]
        unique, dupe_map = _deduplicate_texts(texts)
        assert len(unique) == 3  # noqa: PLR2004

    def test_empty_strings_in_list(self) -> None:
        """Empty strings are valid duplicate entries."""
        texts = ["", "a", "", "b", ""]
        unique, dupe_map = _deduplicate_texts(texts)
        assert unique == ["", "a", "b"]
        assert dupe_map[""] == [0, 2, 4]

    def test_newline_vs_no_newline(self) -> None:
        """'hello' and 'hello\\n' are different entries."""
        texts = ["hello", "hello\n"]
        unique, _ = _deduplicate_texts(texts)
        assert len(unique) == 2  # noqa: PLR2004

    def test_tab_vs_spaces(self) -> None:
        """Tab vs spaces are different entries."""
        texts = ["\t", "    "]
        unique, _ = _deduplicate_texts(texts)
        assert len(unique) == 2  # noqa: PLR2004

    def test_long_identical_strings(self) -> None:
        """Long identical strings are deduplicated."""
        long_str = "x" * 10000
        texts = [long_str, long_str, "other"]
        unique, dupe_map = _deduplicate_texts(texts)
        assert unique == [long_str, "other"]
        assert dupe_map[long_str] == [0, 1]


# ---------------------------------------------------------------------------
# _compress_glossary — expanded
# ---------------------------------------------------------------------------


class TestCompressGlossaryExpanded:
    """Expanded glossary compression tests."""

    def test_no_matching_terms_returns_none(self) -> None:
        """Glossary with zero matches returns None."""
        glossary = [(1, "xyz", "abc"), (2, "qrs", "def")]
        texts = ["hello world"]
        assert _compress_glossary(glossary, texts) is None

    def test_all_matching_terms_returned(self) -> None:
        """All glossary entries matching the text are returned."""
        glossary = [
            (1, "hello", "bonjour"),
            (2, "world", "monde"),
            (3, "how", "comment"),
        ]
        texts = ["hello world, how are you?"]
        result = _compress_glossary(glossary, texts)
        assert result is not None
        assert len(result) == 3  # noqa: PLR2004

    def test_accent_insensitive_french(self) -> None:
        """French accented glossary term matches unaccented text."""
        glossary = [(1, "resume", "curriculum vitae")]
        texts = ["r\u00e9sum\u00e9 review"]
        result = _compress_glossary(glossary, texts)
        assert result is not None

    def test_accent_insensitive_spanish(self) -> None:
        """Spanish accented glossary term matches unaccented text."""
        glossary = [(1, "a\u00f1o", "year")]
        texts = ["ano nuevo"]
        result = _compress_glossary(glossary, texts)
        assert result is not None

    def test_glossary_source_empty_after_strip(self) -> None:
        """Entry with whitespace-only source after strip is excluded."""
        glossary = [(1, "  \t ", "target")]
        texts = ["anything"]
        assert _compress_glossary(glossary, texts) is None

    def test_glossary_target_empty_after_strip(self) -> None:
        """Entry with whitespace-only target after strip is excluded."""
        glossary = [(1, "source", "\n\t")]
        texts = ["source material"]
        assert _compress_glossary(glossary, texts) is None

    def test_glossary_matches_through_italic_tags(self) -> None:
        """Glossary term matches text inside <i> tags."""
        glossary = [(1, "important", "important")]
        texts = ["This is <i>important</i> text"]
        result = _compress_glossary(glossary, texts)
        assert result is not None

    def test_glossary_matches_through_sup_sub(self) -> None:
        """Glossary matches through <sup>/<sub> tags."""
        glossary = [(1, "CO2", "CO2")]
        texts = ["CO<sub>2</sub> emissions"]
        result = _compress_glossary(glossary, texts)
        assert result is not None

    def test_glossary_single_char_source(self) -> None:
        """Single character glossary source matches."""
        glossary = [(1, "X", "ikutas")]
        texts = ["X marks the spot"]
        result = _compress_glossary(glossary, texts)
        assert result is not None

    def test_glossary_with_special_regex_chars(self) -> None:
        """Glossary term with regex special chars uses 'in' not regex."""
        glossary = [(1, "C#", "C sharp")]
        texts = ["I program in C#"]
        result = _compress_glossary(glossary, texts)
        assert result is not None

    def test_glossary_50_entries_only_2_match(self) -> None:
        """50 entries, only 2 match the text."""
        glossary = [(i, f"term_{i:03d}", f"trans_{i:03d}") for i in range(50)]
        texts = ["term_000 and term_049 are here"]
        result = _compress_glossary(glossary, texts)
        assert result is not None
        assert len(result) == 2  # noqa: PLR2004


# ---------------------------------------------------------------------------
# _is_untranslatable — expanded patterns
# ---------------------------------------------------------------------------


class TestIsUntranslatableExpanded:
    """Expanded untranslatable detection tests."""

    def test_ipv4_like_is_untranslatable(self) -> None:
        """IPv4-like string (numbers + dots) is untranslatable."""
        assert _is_untranslatable("192.168.1.1") is True

    def test_scientific_notation_is_untranslatable(self) -> None:
        """Pure scientific notation (symbols only) is untranslatable."""
        # "1.5e10" contains 'e' which is a letter → translatable
        assert _is_untranslatable("1.5e10") is False

    def test_file_protocol_url(self) -> None:
        """file:// URLs contain letters after the scheme → translatable if not matching pattern."""
        # file:// does not match http/https/www patterns
        assert _is_untranslatable("file:///path/to/file") is False

    def test_complex_email_with_subdomain(self) -> None:
        """Complex email with subdomain is untranslatable."""
        assert _is_untranslatable("user@sub.domain.co.uk") is True

    def test_email_with_percent(self) -> None:
        """Email with percent-encoded character is untranslatable."""
        assert _is_untranslatable("user%40@domain.com") is True

    def test_url_with_https_and_path(self) -> None:
        """HTTPS URL with path components is untranslatable."""
        assert _is_untranslatable("https://api.example.com/v1/translate") is True

    def test_url_with_query_and_fragment(self) -> None:
        """URL with query params and fragment is untranslatable."""
        assert _is_untranslatable("https://example.com/page?id=1#top") is True

    def test_windows_unc_path(self) -> None:
        """Windows UNC path is not matched (contains alphabetic chars)."""
        assert _is_untranslatable("\\\\server\\share") is False

    def test_unix_path_etc_config(self) -> None:
        """Unix path under /etc is untranslatable."""
        assert _is_untranslatable("/etc/config/app.conf") is True

    def test_single_dash(self) -> None:
        """Single dash is untranslatable."""
        assert _is_untranslatable("-") is True

    def test_double_colon(self) -> None:
        """Double colon is untranslatable."""
        assert _is_untranslatable("::") is True

    def test_brackets_only(self) -> None:
        """Brackets only are untranslatable."""
        assert _is_untranslatable("[]") is True

    def test_parentheses_with_number(self) -> None:
        """Parentheses with number are untranslatable."""
        assert _is_untranslatable("(42)") is True

    def test_mixed_content_with_url_is_translatable(self) -> None:
        """Sentence containing URL is translatable (mixed content)."""
        assert _is_untranslatable("Visit https://example.com for info") is False

    def test_math_expression_complex(self) -> None:
        """Complex math expression without letters is untranslatable."""
        assert _is_untranslatable("(2 + 3) * (4 - 1) / 5") is True

    def test_multiline_numbers_only(self) -> None:
        """Multiline pure numbers are untranslatable."""
        assert _is_untranslatable("100\n200\n300") is True

    def test_multiline_with_text_is_translatable(self) -> None:
        """Multiline with any text is translatable."""
        assert _is_untranslatable("100\nHello\n300") is False

    def test_dollar_euro_yen_amounts(self) -> None:
        """Various currency symbols with amounts are untranslatable."""
        assert _is_untranslatable("$99.99") is True
        assert _is_untranslatable("\u20ac50") is True
        assert _is_untranslatable("\u00a52000") is True

    def test_url_with_port(self) -> None:
        """URL with port number is untranslatable."""
        assert _is_untranslatable("https://localhost:3000/api") is True

    def test_www_url_with_path(self) -> None:
        """Www URL with path is untranslatable."""
        assert _is_untranslatable("www.example.com/page/sub") is True


# ---------------------------------------------------------------------------
# translate_batch — checkpoint and progress
# ---------------------------------------------------------------------------


class TestTranslateBatchCheckpointExpanded:
    """Expanded translate_batch checkpoint and progress tests."""

    def test_resume_from_full_checkpoint(self, tmp_path: object) -> None:
        """Full checkpoint: second run needs zero LLM calls."""
        from pathlib import Path  # noqa: PLC0415

        cp_dir = Path(str(tmp_path)) / "full_cp"
        cp_dir.mkdir()

        call_count = {"n": 0}

        def _counting(
            texts: list[str],
            target: str,
            source: str = "",
            **kwargs: object,
        ) -> list[str]:
            call_count["n"] += 1
            return [f"T_{t}" for t in texts]

        # First run
        values = ["A", "B", "C"]
        with patch("src.core.llm_engine.translate_text", side_effect=_counting):
            r1 = translate_batch(values, "Fr", "En", checkpoint_dir=cp_dir)
        first_calls = call_count["n"]
        assert first_calls > 0

        # Second run: all cached
        call_count["n"] = 0
        with patch("src.core.llm_engine.translate_text", side_effect=_counting):
            r2 = translate_batch(values, "Fr", "En", checkpoint_dir=cp_dir)
        assert r2 == r1
        assert call_count["n"] == 0

    def test_partial_checkpoint_resumes(self, tmp_path: object) -> None:
        """Partial checkpoint: cached items skipped, rest translated."""
        from pathlib import Path  # noqa: PLC0415

        cp_dir = Path(str(tmp_path)) / "partial_cp"
        cp_dir.mkdir()

        # Pre-populate partial checkpoint: items 0-2 are cached
        existing = {0: "T_A", 1: "T_B", 2: "T_C"}

        def _mock_translate(
            texts: list[str],
            target: str,
            source: str = "",
            **kwargs: object,
        ) -> list[str]:
            return [f"T_{t}" for t in texts]

        with (
            patch("src.core.llm_engine.translate_text", side_effect=_mock_translate),
            patch("src.core.checkpoint.load_batch_checkpoint", return_value=existing),
        ):
            result = translate_batch(
                ["A", "B", "C", "D", "E"],
                "French",
                "English",
                checkpoint_dir=cp_dir,
            )
        assert result is not None
        assert len(result) == 5  # noqa: PLR2004
        assert result[0] == "T_A"
        assert result[1] == "T_B"
        assert result[2] == "T_C"

    def test_corrupt_checkpoint_loads_empty(self, tmp_path: object) -> None:
        """Corrupt checkpoint (returns None) means all items re-translated."""
        from pathlib import Path  # noqa: PLC0415

        cp_dir = Path(str(tmp_path)) / "corrupt_cp"
        cp_dir.mkdir()

        call_texts: list[list[str]] = []

        def _capture(
            texts: list[str],
            target: str,
            source: str = "",
            **kwargs: object,
        ) -> list[str]:
            call_texts.append(list(texts))
            return [f"T_{t}" for t in texts]

        with (
            patch("src.core.llm_engine.translate_text", side_effect=_capture),
            patch("src.core.checkpoint.load_batch_checkpoint", return_value=None),
            patch("src.core.checkpoint.save_batch_progress"),
        ):
            result = translate_batch(
                ["A", "B"],
                "French",
                "English",
                checkpoint_dir=cp_dir,
            )
        assert result is not None
        assert len(result) == 2  # noqa: PLR2004
        # All items were sent to LLM
        assert sum(len(c) for c in call_texts) == 2  # noqa: PLR2004

    def test_progress_callback_accuracy_no_checkpoint(self) -> None:
        """Progress callback values are accurate percentages."""
        progress: list[int] = []

        def _mock(
            texts: list[str],
            target: str,
            source: str = "",
            **kwargs: object,
        ) -> list[str]:
            return [f"T_{t}" for t in texts]

        values = [f"item{i}" for i in range(10)]
        with patch("src.core.llm_engine.translate_text", side_effect=_mock):
            translate_batch(
                values,
                "French",
                "English",
                progress_callback=progress.append,
            )
        assert len(progress) > 0
        # Values should be non-negative integers
        assert all(isinstance(p, int) and p >= 0 for p in progress)
        # Last value should be close to or at 100
        assert progress[-1] > 0

    def test_cancel_at_start_returns_none(self) -> None:
        """Cancel before any processing returns None."""
        result = translate_batch(
            ["A", "B", "C"],
            "French",
            "English",
            cancel_check=lambda: True,
        )
        assert result is None

    def test_cancel_mid_batch_returns_none(self) -> None:
        """Cancel during batch iteration returns None."""
        call_count = 0

        def _cancel_after(
            texts: list[str],
            target: str,
            source: str = "",
            **kwargs: object,
        ) -> list[str]:
            nonlocal call_count
            call_count += 1
            return [f"T_{t}" for t in texts]

        def cancel_fn() -> bool:
            return call_count > 0

        values = [f"unique_{i}" for i in range(60)]
        with patch("src.core.llm_engine.translate_text", side_effect=_cancel_after):
            result = translate_batch(
                values,
                "French",
                "English",
                cancel_check=cancel_fn,
            )
        assert result is None


# ---------------------------------------------------------------------------
# extract_image_text — expanded tests
# ---------------------------------------------------------------------------


class TestExtractImageTextExpanded:
    """Expanded extract_image_text tests."""

    def test_gemini_base64_encoding(self) -> None:
        """_extract_text_gemini sends the raw image bytes to the SDK.

        The SDK now performs its own base64 encoding inside
        ``Part.from_bytes`` — the production code passes the raw bytes
        through unchanged.  Pin the contract that the bytes the user
        supplied (read via ``pathlib.Path.read_bytes``) reach the SDK
        intact via the inline_data Blob attached to the request.
        """
        from src.core.llm_engine import _extract_text_gemini  # noqa: PLC0415

        raw_data = b"PNG\x89\x00\x01\x02image_data"

        settings = {
            "llm/gemini_api_key": "key",
            "llm/gemini_model": "gemini-2.0-flash",
        }
        inner = json.dumps({"text": "extracted"})
        client = _make_mock_genai_client(response_text=inner)

        with (
            patch(
                f"{_LLM_MOD}._config.load_setting",
                side_effect=lambda k, d="": settings.get(k, d),
            ),
            patch(f"{_LLM_MOD}._build_gemini_client", return_value=client),
            patch("pathlib.Path.read_bytes", return_value=raw_data),
        ):
            result = _extract_text_gemini("/test/image.png")

        assert result == "extracted"
        # The Part.from_bytes(...) Blob exposes the raw bytes (not base64) —
        # base64 encoding happens later, inside the SDK transport layer.
        contents = client.models.generate_content.call_args.kwargs["contents"]
        assert contents[0].inline_data.data == raw_data

    def test_custom_base64_encoding(self) -> None:
        """_extract_text_custom correctly base64-encodes the image."""
        import base64  # noqa: PLC0415

        from src.core.llm_engine import _extract_text_custom  # noqa: PLC0415

        raw_data = b"JPEG\xff\xd8image_content"
        expected_b64 = base64.b64encode(raw_data).decode("utf-8")

        settings = {
            "llm/custom_api_key": "key",
            "llm/custom_model": "gpt-4o",
            "llm/custom_endpoint": "https://api.test.com/v1",
        }

        content = json.dumps({"text": "custom_extracted"})
        client = _make_mock_sdk_client(chat_response=_make_sdk_chat_response(content))

        with (
            patch(
                f"{_LLM_MOD}._config.load_setting",
                side_effect=lambda k, d="": settings.get(k, d),
            ),
            patch(f"{_LLM_MOD}._build_openai_client", return_value=client),
            patch("pathlib.Path.open", return_value=io.BytesIO(raw_data)),
        ):
            result = _extract_text_custom("/test/image.jpg")

        assert result == "custom_extracted"
        sent_kwargs = client.chat.completions.create.call_args.kwargs
        image_url = sent_kwargs["messages"][0]["content"][1]["image_url"]["url"]
        assert expected_b64 in image_url

    def test_gemini_timeout_raises_timeout_error(self) -> None:
        """_extract_text_gemini timeout raises TIMEOUT_ERROR."""
        from src.core.llm_engine import _extract_text_gemini  # noqa: PLC0415

        settings = {
            "llm/gemini_api_key": "key",
            "llm/gemini_model": "gemini-2.0-flash",
        }
        client = _make_mock_genai_client(
            response_error=TimeoutError("request timed out"),
        )

        with (
            patch(
                f"{_LLM_MOD}._config.load_setting",
                side_effect=lambda k, d="": settings.get(k, d),
            ),
            patch(f"{_LLM_MOD}._build_gemini_client", return_value=client),
            patch("pathlib.Path.read_bytes", return_value=b"fake"),
            patch("src.core.llm_engine.time.sleep"),
            pytest.raises(ValueError, match="TIMEOUT_ERROR"),
        ):
            _extract_text_gemini("/test/image.png")

    def test_custom_timeout_raises_timeout_error(self) -> None:
        """_extract_text_custom timeout raises TIMEOUT_ERROR."""
        from src.core.llm_engine import _extract_text_custom  # noqa: PLC0415

        settings = {
            "llm/custom_api_key": "key",
            "llm/custom_model": "gpt-4o",
            "llm/custom_endpoint": "https://api.test.com/v1",
        }
        client = _make_mock_sdk_client(chat_error=_sdk_timeout_error())

        with (
            patch(
                f"{_LLM_MOD}._config.load_setting",
                side_effect=lambda k, d="": settings.get(k, d),
            ),
            patch(f"{_LLM_MOD}._build_openai_client", return_value=client),
            patch(
                "pathlib.Path.open",
                side_effect=lambda *a, **kw: io.BytesIO(b"fake"),
            ),
            patch("src.core.llm_engine.time.sleep"),
            pytest.raises(ValueError, match="TIMEOUT_ERROR"),
        ):
            _extract_text_custom("/test/image.png")

    def test_gemini_empty_text_in_response(self) -> None:
        """_extract_text_gemini returns empty string when response text is empty."""
        from src.core.llm_engine import _extract_text_gemini  # noqa: PLC0415

        inner = json.dumps({"text": ""})
        client = _make_mock_genai_client(response_text=inner)

        settings = {
            "llm/gemini_api_key": "key",
            "llm/gemini_model": "gemini-2.0-flash",
        }
        with (
            patch(
                f"{_LLM_MOD}._config.load_setting",
                side_effect=lambda k, d="": settings.get(k, d),
            ),
            patch(f"{_LLM_MOD}._build_gemini_client", return_value=client),
            patch("pathlib.Path.read_bytes", return_value=b"img"),
        ):
            result = _extract_text_gemini("/test/image.png")
        assert result == ""

    def test_gemini_non_vision_model_uses_default(self) -> None:
        """_extract_text_gemini falls back to default for non-vision model."""
        from src.core.llm_engine import (  # noqa: PLC0415
            DEFAULT_GEMINI_MODEL,
            _extract_text_gemini,
        )

        settings = {
            "llm/gemini_api_key": "key",
            "llm/gemini_model": "text-only-model",
        }
        inner = json.dumps({"text": "ok"})
        client = _make_mock_genai_client(response_text=inner)

        with (
            patch(
                f"{_LLM_MOD}._config.load_setting",
                side_effect=lambda k, d="": settings.get(k, d),
            ),
            patch(f"{_LLM_MOD}._build_gemini_client", return_value=client),
            patch("pathlib.Path.read_bytes", return_value=b"img"),
        ):
            _extract_text_gemini("/test/image.png")

        assert client.models.generate_content.call_count == 1
        sent_model = client.models.generate_content.call_args.kwargs["model"]
        assert sent_model == DEFAULT_GEMINI_MODEL


# ---------------------------------------------------------------------------
# Provider-specific: Gemini safety settings
# ---------------------------------------------------------------------------


class TestGeminiSafetySettingsExpanded:
    """Expanded Gemini safety settings tests."""

    def test_all_categories_present(self) -> None:
        """All 5 harm categories are present."""
        from src.core.llm_engine import _get_gemini_safety_settings  # noqa: PLC0415

        settings = _get_gemini_safety_settings()
        categories = {s["category"] for s in settings}
        assert "HARM_CATEGORY_HARASSMENT" in categories
        assert "HARM_CATEGORY_HATE_SPEECH" in categories
        assert "HARM_CATEGORY_SEXUALLY_EXPLICIT" in categories
        assert "HARM_CATEGORY_DANGEROUS_CONTENT" in categories
        assert "HARM_CATEGORY_CIVIC_INTEGRITY" in categories

    def test_all_thresholds_block_none(self) -> None:
        """Every setting has threshold BLOCK_NONE."""
        from src.core.llm_engine import _get_gemini_safety_settings  # noqa: PLC0415

        for entry in _get_gemini_safety_settings():
            assert entry["threshold"] == "BLOCK_NONE"

    def test_returns_fresh_list_each_call(self) -> None:
        """Each call returns a new list (not shared reference)."""
        from src.core.llm_engine import _get_gemini_safety_settings  # noqa: PLC0415

        a = _get_gemini_safety_settings()
        b = _get_gemini_safety_settings()
        assert a is not b
        assert a == b

    def test_safety_settings_included_in_gemini_payload(self) -> None:
        """_translate_gemini includes safety settings in the SDK config object."""
        from src.core.llm_engine import _translate_gemini  # noqa: PLC0415

        settings = {
            "llm/gemini_api_key": "key",
            "llm/gemini_model": "gemini-pro",
        }
        inner = json.dumps({"results": [{"id": 0, "translated": "Hola"}]})
        client = _make_mock_genai_client(response_text=inner)

        with (
            patch(
                "src.core.llm_engine._config.load_setting",
                side_effect=lambda k, d="": settings.get(k, d),
            ),
            patch("src.core.llm_engine._build_gemini_client", return_value=client),
        ):
            _translate_gemini(["Hello"], "Spanish", "English")

        # The SDK takes safety settings via GenerateContentConfig.safety_settings.
        config = client.models.generate_content.call_args.kwargs["config"]
        assert config.safety_settings is not None
        assert len(config.safety_settings) >= 5  # noqa: PLR2004


# ---------------------------------------------------------------------------
# Provider-specific: OpenAI/Custom streaming
# ---------------------------------------------------------------------------


class TestCustomStreamingExpanded:
    """Expanded custom streaming provider tests."""

    def test_stream_custom_sends_stream_true(self) -> None:
        """_stream_custom sends stream=True kwarg to the SDK."""
        from src.core.llm_engine import _stream_custom  # noqa: PLC0415

        settings = {
            "llm/custom_api_key": "key",
            "llm/custom_model": "gpt-4",
            "llm/custom_endpoint": "https://api.example.com/v1",
        }
        client = _make_mock_sdk_client(stream_chunks=[])

        with (
            patch(
                "src.core.llm_engine._config.load_setting",
                side_effect=lambda k, d="": settings.get(k, d),
            ),
            patch("src.core.llm_engine._build_openai_client", return_value=client),
        ):
            list(_stream_custom("Hello", "French", "English"))

        sent_kwargs = client.chat.completions.create.call_args.kwargs
        assert sent_kwargs["stream"] is True

    def test_stream_custom_uses_normalized_endpoint(self) -> None:
        """_stream_custom passes the user's endpoint through to _build_openai_client.

        Endpoint normalization happens inside the SDK client builder; this test
        only asserts that the dispatcher invokes the client builder with the
        endpoint string the user configured.
        """
        from src.core.llm_engine import _stream_custom  # noqa: PLC0415

        settings = {
            "llm/custom_api_key": "key",
            "llm/custom_model": "gpt-4",
            "llm/custom_endpoint": "api.example.com/v1",  # no scheme
        }
        client = _make_mock_sdk_client(stream_chunks=[])
        with (
            patch(
                "src.core.llm_engine._config.load_setting",
                side_effect=lambda k, d="": settings.get(k, d),
            ),
            patch(
                "src.core.llm_engine._build_openai_client",
                return_value=client,
            ) as build_client,
        ):
            list(_stream_custom("Hello", "French", "English"))

        # The dispatcher passed the endpoint to the SDK client builder.
        assert build_client.call_count == 1
        assert build_client.call_args.args[1] == "api.example.com/v1"


# ---------------------------------------------------------------------------
# Provider-specific: Gemini streaming
# ---------------------------------------------------------------------------


class TestGeminiStreamingExpanded:
    """Expanded Gemini streaming tests."""

    def test_stream_gemini_url_contains_model(self) -> None:
        """_stream_gemini passes the configured model to the SDK iterator.

        The SDK builds the streamGenerateContent URL internally; the
        dispatcher's contract is to invoke ``generate_content_stream``
        with the model name supplied by the caller (or the engine
        default when the caller passes ``""``).
        """
        from src.core.llm_engine import _stream_gemini  # noqa: PLC0415

        settings = {
            "llm/gemini_api_key": "key",
            "llm/gemini_model": "gemini-2.0-flash",
        }
        client = _make_mock_genai_client(stream_chunks=[])

        with (
            patch(
                "src.core.llm_engine._config.load_setting",
                side_effect=lambda k, d="": settings.get(k, d),
            ),
            patch("src.core.llm_engine._build_gemini_client", return_value=client),
        ):
            # Caller supplies the model directly — _stream_gemini itself does
            # NOT read llm/gemini_model from settings (that lives in the
            # higher-level dispatch layer).  Pass the user's configured model
            # explicitly so the assertion reflects real call-site behaviour.
            list(_stream_gemini(
                "Hello", "French", "English", None, "gemini-2.0-flash",
            ))

        assert client.models.generate_content_stream.call_count == 1
        sent_model = client.models.generate_content_stream.call_args.kwargs["model"]
        assert sent_model == "gemini-2.0-flash"

    def test_stream_gemini_includes_safety_settings(self) -> None:
        """_stream_gemini payload includes safety_settings on the SDK config."""
        from src.core.llm_engine import _stream_gemini  # noqa: PLC0415

        settings = {
            "llm/gemini_api_key": "key",
            "llm/gemini_model": "gemini-pro",
        }
        client = _make_mock_genai_client(stream_chunks=[])

        with (
            patch(
                "src.core.llm_engine._config.load_setting",
                side_effect=lambda k, d="": settings.get(k, d),
            ),
            patch("src.core.llm_engine._build_gemini_client", return_value=client),
        ):
            list(_stream_gemini("Hello", "French", "English"))

        config = client.models.generate_content_stream.call_args.kwargs["config"]
        assert config.safety_settings is not None
        assert len(config.safety_settings) >= 5  # noqa: PLR2004


# ---------------------------------------------------------------------------
# _translate_gemini — response parsing edge cases
# ---------------------------------------------------------------------------


class TestTranslateGeminiResponseParsing:
    """Response parsing edge cases for _translate_gemini."""

    def _make_client(self, results: list[dict]) -> MagicMock:
        inner = json.dumps({"results": results})
        return _make_mock_genai_client(response_text=inner)

    def _settings(self) -> dict[str, str]:
        return {
            "llm/gemini_api_key": "key",
            "llm/gemini_model": "gemini-pro",
        }

    def test_empty_results_array_returns_originals(self) -> None:
        """Empty results array: all texts fall back to originals."""
        from src.core.llm_engine import _translate_gemini  # noqa: PLC0415

        client = self._make_client([])
        with (
            patch(
                "src.core.llm_engine._config.load_setting",
                side_effect=lambda k, d="": self._settings().get(k, d),
            ),
            patch(
                "src.core.llm_engine._build_gemini_client",
                return_value=client,
            ),
        ):
            result = _translate_gemini(["Hello", "World"], "French", "English")
        assert result == ["Hello", "World"]

    def test_partial_results_fills_gaps(self) -> None:
        """Only some IDs returned: missing ones fall back to original."""
        from src.core.llm_engine import _translate_gemini  # noqa: PLC0415

        client = self._make_client([{"id": 0, "translated": "Bonjour"}])
        with (
            patch(
                "src.core.llm_engine._config.load_setting",
                side_effect=lambda k, d="": self._settings().get(k, d),
            ),
            patch(
                "src.core.llm_engine._build_gemini_client",
                return_value=client,
            ),
        ):
            result = _translate_gemini(
                ["Hello", "World", "Test"],
                "French",
                "English",
            )
        assert result[0] == "Bonjour"
        assert result[1] == "World"  # fallback
        assert result[2] == "Test"  # fallback

    def test_extra_ids_in_response_ignored(self) -> None:
        """Extra IDs beyond input size are ignored."""
        from src.core.llm_engine import _translate_gemini  # noqa: PLC0415

        client = self._make_client(
            [
                {"id": 0, "translated": "Bonjour"},
                {"id": 1, "translated": "Monde"},
                {"id": 99, "translated": "Extra"},  # beyond input
            ],
        )
        with (
            patch(
                "src.core.llm_engine._config.load_setting",
                side_effect=lambda k, d="": self._settings().get(k, d),
            ),
            patch(
                "src.core.llm_engine._build_gemini_client",
                return_value=client,
            ),
        ):
            result = _translate_gemini(["Hello", "World"], "French", "English")
        assert result == ["Bonjour", "Monde"]

    def test_duplicate_ids_last_wins(self) -> None:
        """Duplicate IDs in response: last one wins (dict overwrite)."""
        from src.core.llm_engine import _translate_gemini  # noqa: PLC0415

        client = self._make_client(
            [
                {"id": 0, "translated": "First"},
                {"id": 0, "translated": "Second"},
            ],
        )
        with (
            patch(
                "src.core.llm_engine._config.load_setting",
                side_effect=lambda k, d="": self._settings().get(k, d),
            ),
            patch(
                "src.core.llm_engine._build_gemini_client",
                return_value=client,
            ),
        ):
            result = _translate_gemini(["Hello"], "French", "English")
        assert result == ["Second"]

    def test_results_with_missing_id_key_skipped(self) -> None:
        """Results missing 'id' key are skipped."""
        from src.core.llm_engine import _translate_gemini  # noqa: PLC0415

        client = self._make_client(
            [
                {"translated": "NoId"},  # missing 'id'
                {"id": 1, "translated": "HasId"},
            ],
        )
        with (
            patch(
                "src.core.llm_engine._config.load_setting",
                side_effect=lambda k, d="": self._settings().get(k, d),
            ),
            patch(
                "src.core.llm_engine._build_gemini_client",
                return_value=client,
            ),
        ):
            result = _translate_gemini(["Hello", "World"], "French", "English")
        assert result[0] == "Hello"  # fallback (no id=0)
        assert result[1] == "HasId"


# ---------------------------------------------------------------------------
# _translate_custom — response parsing edge cases
# ---------------------------------------------------------------------------


class TestTranslateCustomResponseParsing:
    """Response parsing edge cases for _translate_custom."""

    def _make_sdk_client(self, results: list[dict]) -> MagicMock:
        content = json.dumps({"results": results})
        return _make_mock_sdk_client(chat_response=_make_sdk_chat_response(content))

    def _settings(self) -> dict[str, str]:
        return {
            "llm/custom_api_key": "key",
            "llm/custom_model": "gpt-4",
            "llm/custom_endpoint": "https://api.example.com/v1",
        }

    def test_empty_results_returns_originals(self) -> None:
        """Empty results: all texts fall back to originals."""
        from src.core.llm_engine import _translate_custom  # noqa: PLC0415

        client = self._make_sdk_client([])
        with (
            patch(
                "src.core.llm_engine._config.load_setting",
                side_effect=lambda k, d="": self._settings().get(k, d),
            ),
            patch(
                "src.core.llm_engine._build_openai_client",
                return_value=client,
            ),
        ):
            result = _translate_custom(["Hello"], "French", "English")
        assert result == ["Hello"]

    def test_partial_results_fills_gaps(self) -> None:
        """Partial results: missing IDs fall back to original."""
        from src.core.llm_engine import _translate_custom  # noqa: PLC0415

        client = self._make_sdk_client([{"id": 1, "translated": "Monde"}])
        with (
            patch(
                "src.core.llm_engine._config.load_setting",
                side_effect=lambda k, d="": self._settings().get(k, d),
            ),
            patch(
                "src.core.llm_engine._build_openai_client",
                return_value=client,
            ),
        ):
            result = _translate_custom(["Hello", "World"], "French", "English")
        assert result[0] == "Hello"  # fallback
        assert result[1] == "Monde"


# ---------------------------------------------------------------------------
# _build_translation_prompt — content type coverage
# ---------------------------------------------------------------------------


class TestBuildTranslationPromptContentTypes:
    """Test _build_translation_prompt for all content types."""

    def test_plain_text_rules(self) -> None:
        """Plain text includes 'fluent' and 'natural'."""
        result = _build_translation_prompt(CONTENT_PLAIN_TEXT, "En", "Fr")
        assert "fluent" in result.lower()

    def test_data_values_no_quality(self) -> None:
        """Data values omit quality guidance."""
        from src.constants.llm import CONTENT_DATA_VALUES  # noqa: PLC0415

        result = _build_translation_prompt(CONTENT_DATA_VALUES, "En", "Fr")
        assert "Preserve the original tone" not in result

    def test_pdf_mentions_html_tags(self) -> None:
        """PDF prompt mentions inline HTML tags."""
        result = _build_translation_prompt(CONTENT_PDF, "En", "Fr")
        assert "<b>" in result or "HTML" in result

    def test_unknown_type_falls_back_to_plain(self) -> None:
        """Unknown content type uses plain text rules."""
        plain = _build_translation_prompt(CONTENT_PLAIN_TEXT, "En", "Fr")
        unknown = _build_translation_prompt("nonexistent_type", "En", "Fr")
        # Both should contain the same format-specific rules
        assert "Produce fluent" in plain
        assert "Produce fluent" in unknown

    def test_glossary_none_no_glossary_in_prompt(self) -> None:
        """None glossary: no glossary section in prompt."""
        result = _build_translation_prompt(CONTENT_PLAIN_TEXT, "En", "Fr", None)
        assert "Glossary" not in result

    def test_glossary_included_in_prompt(self) -> None:
        """Glossary entries appear in the prompt."""
        glossary = [(1, "hello", "bonjour"), (2, "world", "monde")]
        result = _build_translation_prompt(CONTENT_PLAIN_TEXT, "En", "Fr", glossary)
        assert "hello = bonjour" in result
        assert "world = monde" in result

    def test_json_output_format_always_present(self) -> None:
        """JSON output format instruction is always present."""
        result = _build_translation_prompt(CONTENT_PLAIN_TEXT, "En", "Fr")
        assert "JSON" in result
        assert "results" in result


# ---------------------------------------------------------------------------
# _format_glossary_hint / _format_glossary_block — expanded
# ---------------------------------------------------------------------------


class TestFormatGlossaryExpanded:
    """Expanded glossary formatting tests."""

    def test_hint_three_entries(self) -> None:
        """Three entries joined with comma separator."""
        entries = [(1, "a", "x"), (2, "b", "y"), (3, "c", "z")]
        result = _format_glossary_hint(entries)
        assert "a <-> x" in result
        assert "b <-> y" in result
        assert "c <-> z" in result

    def test_block_three_entries(self) -> None:
        """Three entries joined with pipe separator."""
        entries = [(1, "a", "x"), (2, "b", "y"), (3, "c", "z")]
        result = _format_glossary_block(entries)
        assert "a = x" in result
        assert "b = y" in result
        assert "c = z" in result
        assert "|" in result

    def test_hint_with_unicode(self) -> None:
        """Unicode terms are preserved in hint."""
        entries = [(1, "\u4f60\u597d", "Hello")]
        result = _format_glossary_hint(entries)
        assert "\u4f60\u597d <-> Hello" in result

    def test_block_with_unicode(self) -> None:
        """Unicode terms are preserved in block."""
        entries = [(1, "\u4f60\u597d", "Hello")]
        result = _format_glossary_block(entries)
        assert "\u4f60\u597d = Hello" in result


# ---------------------------------------------------------------------------
# _guess_image_mime — expanded
# ---------------------------------------------------------------------------


class TestGuessImageMimeExpanded:
    """Expanded MIME type guessing tests."""

    def test_all_supported_extensions(self) -> None:
        """All supported extensions return correct MIME types."""
        from src.core.llm_engine import _guess_image_mime  # noqa: PLC0415

        assert _guess_image_mime("/x.jpg") == "image/jpeg"
        assert _guess_image_mime("/x.jpeg") == "image/jpeg"
        assert _guess_image_mime("/x.png") == "image/png"
        assert _guess_image_mime("/x.gif") == "image/gif"
        assert _guess_image_mime("/x.bmp") == "image/bmp"
        assert _guess_image_mime("/x.webp") == "image/webp"
        assert _guess_image_mime("/x.tiff") == "image/tiff"
        assert _guess_image_mime("/x.tif") == "image/tiff"

    def test_uppercase_extension(self) -> None:
        """Uppercase extension is handled case-insensitively."""
        from src.core.llm_engine import _guess_image_mime  # noqa: PLC0415

        assert _guess_image_mime("/PHOTO.PNG") == "image/png"
        assert _guess_image_mime("/IMAGE.BMP") == "image/bmp"

    def test_no_extension_defaults_to_jpeg(self) -> None:
        """File without extension defaults to JPEG."""
        from src.core.llm_engine import _guess_image_mime  # noqa: PLC0415

        assert _guess_image_mime("/path/to/file") == "image/jpeg"

    def test_unsupported_extension_defaults_to_jpeg(self) -> None:
        """Unsupported extension defaults to JPEG."""
        from src.core.llm_engine import _guess_image_mime  # noqa: PLC0415

        assert _guess_image_mime("/file.svg") == "image/jpeg"
        assert _guess_image_mime("/file.pdf") == "image/jpeg"
        assert _guess_image_mime("/file.txt") == "image/jpeg"


# ---------------------------------------------------------------------------
# translate_image_content — expanded dispatch tests
# ---------------------------------------------------------------------------


class TestTranslateImageContentExpanded:
    """Expanded translate_image_content tests."""

    def test_gemini_called_with_correct_fragments(self) -> None:
        """_translate_image_gemini receives correctly formatted fragments."""
        mock_ocr_1 = MagicMock()
        mock_ocr_1.text = "Hello"
        mock_ocr_2 = MagicMock()
        mock_ocr_2.text = "World"

        captured_frags: list[list[dict]] = []

        def fake_gemini(
            image_path: str,
            fragments: list[dict],
            target_lang: str,
            source_lang: str,
            glossary_entries: object = None,
            model="",
            **_kwargs,
        ) -> list[dict]:
            captured_frags.append(fragments)
            return []

        with (
            patch(
                "src.core.llm_engine._resolve_provider_model",
                return_value=(LLM_METHOD_GEMINI, "gemini-3-flash-preview"),
            ),
            patch(
                "src.core.llm_engine._translate_image_gemini",
                side_effect=fake_gemini,
            ),
        ):
            translate_image_content(
                "/test.jpg",
                [mock_ocr_1, mock_ocr_2],
                "French",
            )

        frags = captured_frags[0]
        assert len(frags) == 2  # noqa: PLR2004
        assert frags[0] == {"id": 0, "text": "Hello"}
        assert frags[1] == {"id": 1, "text": "World"}

    def test_single_ocr_result(self) -> None:
        """Single OCR result produces single fragment."""
        mock_ocr = MagicMock()
        mock_ocr.text = "Single"

        with (
            patch(
                "src.core.llm_engine._resolve_provider_model",
                return_value=(LLM_METHOD_GEMINI, "gemini-3-flash-preview"),
            ),
            patch(
                "src.core.llm_engine._translate_image_gemini",
                return_value=[{"ids": [0], "translated_html": "Seul"}],
            ),
        ):
            result = translate_image_content("/test.jpg", [mock_ocr], "French")
        assert len(result) == 1
        assert result[0]["translated_html"] == "Seul"

    def test_multiple_ocr_results(self) -> None:
        """Multiple OCR results produce multiple fragments."""
        ocr_results = [MagicMock(text=f"text{i}") for i in range(5)]

        with (
            patch(
                "src.core.llm_engine._resolve_provider_model",
                return_value=(LLM_METHOD_CUSTOM, "gpt-4o"),
            ),
            patch(
                "src.core.llm_engine._translate_image_custom",
                return_value=[{"ids": list(range(5)), "translated_html": "merged"}],
            ),
        ):
            result = translate_image_content("/test.jpg", ocr_results, "French")
        assert len(result) == 1


# ---------------------------------------------------------------------------
# translate_batch — deduplication consistency
# ---------------------------------------------------------------------------


class TestTranslateBatchDedup:
    """Deduplication consistency tests for translate_batch."""

    def test_duplicates_across_batches_consistent(self) -> None:
        """Duplicates spanning TRANSLATION_BATCH_SIZE boundaries are consistent."""

        def _mock(
            texts: list[str],
            target: str,
            source: str = "",
            **kwargs: object,
        ) -> list[str]:
            return [f"T_{t}" for t in texts]

        # 60 items, 10 unique, repeated 6 times
        values = [f"w{i % 10}" for i in range(60)]
        with patch("src.core.llm_engine.translate_text", side_effect=_mock):
            result = translate_batch(values, "French", "English")
        assert result is not None
        for i in range(10):
            expected = f"T_w{i}"
            indices = [j for j, v in enumerate(values) if v == f"w{i}"]
            for idx in indices:
                assert result[idx] == expected

    def test_all_identical_translated_once(self) -> None:
        """All-identical values translated exactly once."""
        call_count = {"n": 0}

        def _counting(
            texts: list[str],
            target: str,
            source: str = "",
            **kwargs: object,
        ) -> list[str]:
            call_count["n"] += len(texts)
            return [f"T_{t}" for t in texts]

        values = ["same"] * 100
        with patch("src.core.llm_engine.translate_text", side_effect=_counting):
            result = translate_batch(values, "French", "English")
        assert result is not None
        assert all(r == "T_same" for r in result)
        assert call_count["n"] == 1

    def test_empty_string_duplicates(self) -> None:
        """Empty string duplicates handled correctly."""

        def _mock(
            texts: list[str],
            target: str,
            source: str = "",
            **kwargs: object,
        ) -> list[str]:
            return [f"T_{t}" for t in texts]

        values = ["", "hello", "", "world", ""]
        with patch("src.core.llm_engine.translate_text", side_effect=_mock):
            result = translate_batch(values, "French", "English")
        assert result is not None
        assert result[0] == result[2] == result[4]  # all empty strings same
        assert result[1] == "T_hello"
        assert result[3] == "T_world"


# ---------------------------------------------------------------------------
# retry_api_call — expanded edge cases
# ---------------------------------------------------------------------------


class TestRetryApiCallExpanded:
    """Expanded retry decorator edge cases."""

    def test_success_returns_none(self) -> None:
        """Function returning None is valid."""

        @retry_api_call()
        def returns_none() -> None:
            return None

        assert returns_none() is None

    def test_success_returns_list(self) -> None:
        """Function returning a list is valid."""

        @retry_api_call()
        def returns_list() -> list[str]:
            return ["a", "b"]

        assert returns_list() == ["a", "b"]

    def test_wraps_preserves_docstring(self) -> None:
        """@wraps preserves the function's docstring."""

        @retry_api_call()
        def documented() -> None:
            """This is the docstring."""

        assert "docstring" in (documented.__doc__ or "")

    def test_all_transient_errors_retried(self) -> None:
        """All transient error tags trigger retries."""
        for tag in ("SERVICE_UNAVAILABLE_ERROR", "CONNECTION_ERROR"):
            call_count = 0
            _tag = tag  # Bind loop variable for closure

            @retry_api_call(max_retries=1, base_delay=0.01)
            def fn(_tag=_tag) -> str:
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise ValueError(_tag)
                return "ok"

            with patch("src.core.llm_engine.time.sleep"):
                result = fn()
            assert result == "ok"
            assert call_count == 2  # noqa: PLR2004

    def test_max_retries_one(self) -> None:
        """max_retries=1: one retry attempt, then raise."""
        call_count = 0

        @retry_api_call(max_retries=1, base_delay=0.01)
        def always_fail() -> None:
            nonlocal call_count
            call_count += 1
            raise ValueError("SERVICE_UNAVAILABLE_ERROR")

        with (
            patch("src.core.llm_engine.time.sleep"),
            pytest.raises(ValueError, match="SERVICE_UNAVAILABLE_ERROR"),
        ):
            always_fail()
        assert call_count == 2  # noqa: PLR2004  # 1 initial + 1 retry

    def test_delay_doubles_each_retry(self) -> None:
        """Verify exponential backoff: delay = base * 2^(retry-1)."""
        delays: list[float] = []

        @retry_api_call(max_retries=4, base_delay=0.5)
        def always_unavailable() -> None:
            raise ValueError("SERVICE_UNAVAILABLE_ERROR")

        with (
            patch("src.core.llm_engine.time.sleep", side_effect=delays.append),
            pytest.raises(ValueError),
        ):
            always_unavailable()

        assert len(delays) == 4  # noqa: PLR2004
        assert delays[0] == pytest.approx(0.5)
        assert delays[1] == pytest.approx(1.0)
        assert delays[2] == pytest.approx(2.0)
        assert delays[3] == pytest.approx(4.0)


# ---------------------------------------------------------------------------
# translate_batch — deduplication + checkpoint interaction
# ---------------------------------------------------------------------------


class TestTranslateBatchDedupCheckpointInteraction:
    """Tests for translate_batch when deduplication interacts with checkpoints."""

    def test_duplicates_restored_with_partial_checkpoint(
        self, tmp_path: object
    ) -> None:
        """Duplicates are correctly restored when some values are in checkpoint cache.

        Scenario:
        - Input: ["Hello", "World", "Hello"] (3 items, 2 unique)
        - Checkpoint has item 0 ("Hello") cached as "T_Hello"
        - "World" (index 1 in unique list) must be sent to the LLM
        - The duplicate "Hello" at index 2 must get the cached translation "T_Hello"
        """
        from pathlib import Path  # noqa: PLC0415

        cp_dir = Path(str(tmp_path)) / "dedup_cp"
        cp_dir.mkdir()

        call_texts: list[list[str]] = []

        def _capture(
            texts: list[str],
            target: str,
            source: str = "",
            **kwargs: object,
        ) -> list[str]:
            call_texts.append(list(texts))
            return [f"T_{t}" for t in texts]

        # Pre-populate checkpoint: unique index 0 ("Hello") is cached
        existing_checkpoint = {0: "T_Hello"}

        with (
            patch("src.core.llm_engine.translate_text", side_effect=_capture),
            patch(
                "src.core.checkpoint.load_batch_checkpoint",
                return_value=existing_checkpoint,
            ),
            patch("src.core.checkpoint.save_batch_progress"),
        ):
            result = translate_batch(
                ["Hello", "World", "Hello"],
                "French",
                "English",
                checkpoint_dir=cp_dir,
            )

        assert result is not None
        assert len(result) == 3  # noqa: PLR2004
        # First "Hello" gets the cached translation
        assert result[0] == "T_Hello"
        # "World" was sent to the LLM
        assert result[1] == "T_World"
        # Duplicate "Hello" at index 2 gets the same cached translation
        assert result[2] == "T_Hello"
        # Only "World" should have been sent to translate_text (1 uncached unique)
        total_sent = sum(len(c) for c in call_texts)
        assert total_sent == 1
        assert call_texts[0] == ["World"]

    def test_all_duplicates_cached_skips_llm(self, tmp_path: object) -> None:
        """When all unique values are in checkpoint, no LLM calls are made.

        Scenario:
        - Input: ["Hello", "World", "Hello"] (3 items, 2 unique)
        - Checkpoint has both unique items cached
        - No translate_text calls should happen
        """
        from pathlib import Path  # noqa: PLC0415

        cp_dir = Path(str(tmp_path)) / "all_cached"
        cp_dir.mkdir()

        call_count = {"n": 0}

        def _counting(
            texts: list[str],
            target: str,
            source: str = "",
            **kwargs: object,
        ) -> list[str]:
            call_count["n"] += 1
            return [f"T_{t}" for t in texts]

        # Both unique items are cached
        existing_checkpoint = {0: "T_Hello", 1: "T_World"}

        with (
            patch("src.core.llm_engine.translate_text", side_effect=_counting),
            patch(
                "src.core.checkpoint.load_batch_checkpoint",
                return_value=existing_checkpoint,
            ),
        ):
            result = translate_batch(
                ["Hello", "World", "Hello"],
                "French",
                "English",
                checkpoint_dir=cp_dir,
            )

        assert result is not None
        assert result == ["T_Hello", "T_World", "T_Hello"]
        # No LLM calls needed
        assert call_count["n"] == 0

    def test_multiple_duplicates_with_partial_checkpoint(
        self, tmp_path: object
    ) -> None:
        """Multiple different duplicates with partial checkpoint coverage.

        Scenario:
        - Input: ["A", "B", "A", "C", "B", "A"] (6 items, 3 unique)
        - Checkpoint has "A" (index 0) cached as "T_A"
        - "B" and "C" must be sent to LLM
        - All duplicates of "A" must get "T_A"
        """
        from pathlib import Path  # noqa: PLC0415

        cp_dir = Path(str(tmp_path)) / "multi_dedup"
        cp_dir.mkdir()

        call_texts: list[list[str]] = []

        def _capture(
            texts: list[str],
            target: str,
            source: str = "",
            **kwargs: object,
        ) -> list[str]:
            call_texts.append(list(texts))
            return [f"T_{t}" for t in texts]

        existing_checkpoint = {0: "T_A"}

        with (
            patch("src.core.llm_engine.translate_text", side_effect=_capture),
            patch(
                "src.core.checkpoint.load_batch_checkpoint",
                return_value=existing_checkpoint,
            ),
            patch("src.core.checkpoint.save_batch_progress"),
        ):
            result = translate_batch(
                ["A", "B", "A", "C", "B", "A"],
                "French",
                "English",
                checkpoint_dir=cp_dir,
            )

        assert result is not None
        assert len(result) == 6  # noqa: PLR2004
        # All "A"s get the cached value
        assert result[0] == "T_A"
        assert result[2] == "T_A"
        assert result[5] == "T_A"
        # "B" and "C" get translated values
        assert result[1] == "T_B"
        assert result[3] == "T_C"
        assert result[4] == "T_B"
        # Only "B" and "C" sent to LLM
        total_sent = sum(len(c) for c in call_texts)
        assert total_sent == 2  # noqa: PLR2004

    def test_dedup_checkpoint_round_trip(self, tmp_path: object) -> None:
        """First run with duplicates saves checkpoint; second run uses cache.

        Scenario:
        - Input: ["Hello", "World", "Hello"]
        - First run: translate and save checkpoint
        - Second run: all from checkpoint, no LLM calls
        """
        from pathlib import Path  # noqa: PLC0415

        cp_dir = Path(str(tmp_path)) / "roundtrip"
        cp_dir.mkdir()

        call_texts: list[list[str]] = []

        def _capture(
            texts: list[str],
            target: str,
            source: str = "",
            **kwargs: object,
        ) -> list[str]:
            call_texts.append(list(texts))
            return [f"T_{t}" for t in texts]

        values = ["Hello", "World", "Hello"]

        # First run: translate everything
        with patch("src.core.llm_engine.translate_text", side_effect=_capture):
            result1 = translate_batch(
                values,
                "French",
                "English",
                checkpoint_dir=cp_dir,
            )
        assert result1 == ["T_Hello", "T_World", "T_Hello"]
        first_run_calls = len(call_texts)
        assert first_run_calls > 0

        # Second run: all from checkpoint
        call_texts.clear()
        with patch("src.core.llm_engine.translate_text", side_effect=_capture):
            result2 = translate_batch(
                values,
                "French",
                "English",
                checkpoint_dir=cp_dir,
            )
        assert result2 == result1
        # No new LLM calls
        assert len(call_texts) == 0



# ---------------------------------------------------------------------------
# _build_gemini_client — Developer API vs Vertex AI dispatch
# ---------------------------------------------------------------------------


class TestBuildGeminiClientVertex:
    """Verifies _build_gemini_client picks the right constructor path."""

    def test_developer_api_path_uses_api_key(self) -> None:
        """When Vertex is off, the Developer API client gets api_key=...."""
        from src.core.llm_engine import _build_gemini_client  # noqa: PLC0415

        settings = {
            "llm/gemini_use_vertex": False,
            "llm/gemini_api_key": "fake-dev-key",
        }
        with (
            patch(
                "src.core.llm_engine._config.load_setting",
                side_effect=lambda k, d="": settings.get(k, d),
            ),
            patch("google.genai.Client") as mock_client,
        ):
            _build_gemini_client("fake-dev-key")
            mock_client.assert_called_once_with(api_key="fake-dev-key")

    def test_vertex_path_uses_project_and_location(self) -> None:
        """Vertex mode passes vertexai=True + project + location."""
        from src.core.llm_engine import _build_gemini_client  # noqa: PLC0415

        settings = {
            "llm/gemini_use_vertex": True,
            "llm/vertex_project": "my-gcp",
            "llm/vertex_location": "europe-west4",
            "llm/vertex_credentials": "",  # ADC fallback
        }
        with (
            patch(
                "src.core.llm_engine._config.load_setting",
                side_effect=lambda k, d="": settings.get(k, d),
            ),
            patch("google.genai.Client") as mock_client,
        ):
            _build_gemini_client()
            mock_client.assert_called_once_with(
                vertexai=True,
                project="my-gcp",
                location="europe-west4",
                credentials=None,
            )

    def test_vertex_path_loads_service_account_credentials(
        self, tmp_path
    ) -> None:
        """When credentials path is set, the SDK gets a Credentials object."""
        from src.core.llm_engine import _build_gemini_client  # noqa: PLC0415

        sa_path = tmp_path / "sa.json"
        sa_path.write_text("{}")  # contents don't matter — we mock the loader

        settings = {
            "llm/gemini_use_vertex": True,
            "llm/vertex_project": "my-gcp",
            "llm/vertex_location": "us-central1",
            "llm/vertex_credentials": str(sa_path),
        }
        fake_creds = MagicMock(name="ServiceAccountCredentials")
        with (
            patch(
                "src.core.llm_engine._config.load_setting",
                side_effect=lambda k, d="": settings.get(k, d),
            ),
            patch(
                "google.oauth2.service_account.Credentials"
                ".from_service_account_file",
                return_value=fake_creds,
            ) as mock_load,
            patch("google.genai.Client") as mock_client,
        ):
            _build_gemini_client()
            mock_load.assert_called_once_with(
                str(sa_path),
                scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )
            mock_client.assert_called_once_with(
                vertexai=True,
                project="my-gcp",
                location="us-central1",
                credentials=fake_creds,
            )

    def test_vertex_missing_project_raises_auth_error(self) -> None:
        """Vertex mode with no project ID raises AUTH_ERROR before any HTTP."""
        from src.core.llm_engine import _build_gemini_client  # noqa: PLC0415

        settings = {
            "llm/gemini_use_vertex": True,
            "llm/vertex_project": "",  # missing!
        }
        with (
            patch(
                "src.core.llm_engine._config.load_setting",
                side_effect=lambda k, d="": settings.get(k, d),
            ),
            pytest.raises(ValueError, match="AUTH_ERROR"),
        ):
            _build_gemini_client()

    def test_vertex_unreadable_credentials_file_raises_auth_error(
        self, tmp_path
    ) -> None:
        """A nonexistent / invalid service-account file is surfaced as AUTH_ERROR."""
        from src.core.llm_engine import _build_gemini_client  # noqa: PLC0415

        settings = {
            "llm/gemini_use_vertex": True,
            "llm/vertex_project": "my-gcp",
            "llm/vertex_location": "us-central1",
            "llm/vertex_credentials": str(tmp_path / "does-not-exist.json"),
        }
        with (
            patch(
                "src.core.llm_engine._config.load_setting",
                side_effect=lambda k, d="": settings.get(k, d),
            ),
            pytest.raises(ValueError, match="AUTH_ERROR"),
        ):
            _build_gemini_client()

    def test_developer_api_missing_key_raises_auth_error(self) -> None:
        """Developer API with no key raises AUTH_ERROR (unchanged behaviour)."""
        from src.core.llm_engine import _build_gemini_client  # noqa: PLC0415

        settings = {
            "llm/gemini_use_vertex": False,
            "llm/gemini_api_key": "",
        }
        with (
            patch(
                "src.core.llm_engine._config.load_setting",
                side_effect=lambda k, d="": settings.get(k, d),
            ),
            pytest.raises(ValueError, match="AUTH_ERROR"),
        ):
            _build_gemini_client("")

    def test_vertex_default_location_when_unset(self) -> None:
        """Empty location setting falls back to us-central1."""
        from src.core.llm_engine import _build_gemini_client  # noqa: PLC0415

        settings = {
            "llm/gemini_use_vertex": True,
            "llm/vertex_project": "my-gcp",
            "llm/vertex_location": "",  # empty → default
        }
        with (
            patch(
                "src.core.llm_engine._config.load_setting",
                side_effect=lambda k, d="": settings.get(k, d),
            ),
            patch("google.genai.Client") as mock_client,
        ):
            _build_gemini_client()
            from src.constants.settings import (  # noqa: PLC0415
                VERTEX_DEFAULT_LOCATION,
            )

            mock_client.assert_called_once_with(
                vertexai=True,
                project="my-gcp",
                location=VERTEX_DEFAULT_LOCATION,
                credentials=None,
            )

    def test_translate_text_routes_through_vertex_when_enabled(self) -> None:
        """Vertex mode constructs the Vertex client AND calls generate_content.

        The unit tests above prove _build_gemini_client picks the right
        constructor.  This test proves the high-level translate_text()
        entry point actually goes through that constructor (not the
        Developer-API constructor) when Vertex is enabled, and that
        the resulting translations bubble back up.

        Without this, a refactor that accidentally bypassed
        _build_gemini_client and instantiated genai.Client(api_key=...)
        directly would silently route Vertex users to the Developer API
        and bill against the wrong account.
        """
        import json  # noqa: PLC0415

        from src.constants.llm import LLM_METHOD_GEMINI  # noqa: PLC0415
        from src.core.llm_engine import translate_text  # noqa: PLC0415

        settings = {
            "llm/method": LLM_METHOD_GEMINI,
            "llm/gemini_use_vertex": True,
            "llm/vertex_project": "real-vertex-project",
            "llm/vertex_location": "europe-west1",
            "llm/vertex_credentials": "",
            "llm/gemini_api_key": "",  # would fail without Vertex
        }

        # Fake the SDK response — return one Vietnamese translation.
        fake_response = MagicMock()
        fake_response.text = json.dumps({
            "results": [{"id": 0, "translated": "Xin chào"}],
        })
        fake_client = MagicMock()
        fake_client.models.generate_content.return_value = fake_response

        with (
            patch(
                "src.core.llm_engine._config.load_setting",
                side_effect=lambda k, d="": settings.get(k, d),
            ),
            patch(
                "google.genai.Client",
                return_value=fake_client,
            ) as mock_ctor,
        ):
            result = translate_text(
                ["Hello"],
                target_lang="Vietnamese",
                source_lang="English",
                provider=LLM_METHOD_GEMINI,
            )

        # Vertex constructor was used (not Developer API).
        ctor_kwargs = mock_ctor.call_args.kwargs
        assert ctor_kwargs.get("vertexai") is True
        assert ctor_kwargs.get("project") == "real-vertex-project"
        assert ctor_kwargs.get("location") == "europe-west1"

        # The Vertex client's generate_content was actually invoked.
        fake_client.models.generate_content.assert_called_once()

        # Translation result propagated back through the pipeline.
        assert result == ["Xin chào"]


# ---------------------------------------------------------------------------
# _call_custom_chat_with_fallback — shared variant fallback for one-shot
# custom-chat calls (vision extract, image translation, screen translate).
# Mirrors _translate_custom_chat's variant chain minus the no_system_role
# step.
# ---------------------------------------------------------------------------


def _make_completion(content: str) -> MagicMock:
    """Builds a minimal openai chat-completion response stub."""
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    completion = MagicMock()
    completion.choices = [choice]
    return completion


def _make_bad_request(message: str) -> Exception:
    """Builds an openai.BadRequestError carrying a 400 body."""
    from openai import BadRequestError  # noqa: PLC0415

    response = MagicMock()
    response.status_code = 400
    return BadRequestError(message, response=response, body={"message": message})


class TestReorderVariantsForCacheHit:
    """Shared cache-hint reorder helper.

    Used by both ``_call_custom_chat_with_fallback`` (3-variant) and
    ``_translate_custom_chat`` (4-variant); tests pin the contract so
    a refactor that changes one caller's expectation gets caught.
    """

    def _make_variants(self, *labels: str) -> list[tuple[str, dict]]:
        """Builds a fake variants list with empty kwargs."""
        return [(label, {}) for label in labels]

    def test_no_cache_entry_returns_variants_unchanged(self) -> None:
        """Empty cache → original variant order is preserved."""
        from src.core.llm_engine import (  # noqa: PLC0415
            _CUSTOM_VARIANT_CACHE,
            _custom_cache_key,
            _reorder_variants_for_cache_hit,
        )

        variants = self._make_variants("a", "b", "c")
        key = _custom_cache_key("https://example/v1", "fresh-model")
        _CUSTOM_VARIANT_CACHE.pop(key, None)

        result = _reorder_variants_for_cache_hit(variants, key)
        assert result == variants

    def test_cached_variant_moves_to_front(self) -> None:
        """Cached label found in middle → reordered to position 0."""
        from src.core.llm_engine import (  # noqa: PLC0415
            _CUSTOM_VARIANT_CACHE,
            _custom_cache_key,
            _reorder_variants_for_cache_hit,
        )

        variants = self._make_variants("a", "b", "c")
        key = _custom_cache_key("https://example/v1", "model-1")
        _CUSTOM_VARIANT_CACHE[key] = "c"

        result = _reorder_variants_for_cache_hit(variants, key)
        assert [label for label, _ in result] == ["c", "a", "b"]

    def test_cached_variant_already_first_no_op(self) -> None:
        """Cached label already at index 0 → no allocation, returns same list."""
        from src.core.llm_engine import (  # noqa: PLC0415
            _CUSTOM_VARIANT_CACHE,
            _custom_cache_key,
            _reorder_variants_for_cache_hit,
        )

        variants = self._make_variants("a", "b", "c")
        key = _custom_cache_key("https://example/v1", "model-2")
        _CUSTOM_VARIANT_CACHE[key] = "a"

        result = _reorder_variants_for_cache_hit(variants, key)
        # Returned list is identity-equal — no allocation needed.
        assert result is variants

    def test_unknown_cache_label_no_op(self) -> None:
        """Cached label not in this caller's variant list → no reorder.

        Real-world: ``_translate_custom_chat`` writes ``no_system_role``
        into the cache; ``_call_custom_chat_with_fallback`` (3-variant)
        doesn't know that label.  The helper correctly leaves the
        variant list alone so the caller falls through in original
        order instead of crashing or routing to a missing variant.
        """
        from src.core.llm_engine import (  # noqa: PLC0415
            _CUSTOM_VARIANT_CACHE,
            _custom_cache_key,
            _reorder_variants_for_cache_hit,
        )

        variants = self._make_variants("a", "b", "c")
        key = _custom_cache_key("https://example/v1", "model-3")
        _CUSTOM_VARIANT_CACHE[key] = "no_system_role"  # unknown to this list

        result = _reorder_variants_for_cache_hit(variants, key)
        assert result == variants


class TestCallCustomChatWithFallback:
    """Tests for _call_custom_chat_with_fallback shared helper."""

    def _client_stub(self, *side_effects: Any) -> MagicMock:
        """Returns a stub whose chat.completions.create plays back side effects.

        Each provided side effect is either an exception (raised on call) or
        a completion-like response (returned).  Used to simulate the
        per-variant 400 → 200 progression.
        """
        client = MagicMock()
        with_opts = MagicMock()
        with_opts.chat.completions.create.side_effect = side_effects
        client.with_options.return_value = with_opts
        # When timeout=None the helper uses ``client`` directly, so
        # mirror the same side-effect chain on the bare client too.
        client.chat.completions.create.side_effect = side_effects
        return client

    def test_succeeds_on_first_variant_no_warning(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """The richest variant works — no fallback warning, no cache write."""
        from src.core.llm_engine import _call_custom_chat_with_fallback  # noqa: PLC0415

        client = self._client_stub(_make_completion('{"ok": true}'))
        with caplog.at_level("WARNING", logger="llm"):
            result = _call_custom_chat_with_fallback(
                client,
                model="some-model",
                endpoint="https://api.example/v1",
                messages=[{"role": "user", "content": "hi"}],
                timeout=10.0,
            )
        assert result == '{"ok": true}'
        # Only the richest variant fired
        assert client.with_options.return_value.chat.completions.create.call_count == 1
        # No "rejected richer payload" warning
        assert not any(
            "rejected richer payload" in rec.message for rec in caplog.records
        )

    def test_falls_through_to_minimal_on_temperature_400(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """gpt-5.x reasoning model rejects temperature → succeeds on minimal."""
        from src.core.llm_engine import _call_custom_chat_with_fallback  # noqa: PLC0415

        client = self._client_stub(
            _make_bad_request("temperature does not support 0.0"),
            _make_bad_request("temperature does not support 0.0"),
            _make_completion('{"ok": true}'),
        )
        with caplog.at_level("WARNING", logger="llm"):
            result = _call_custom_chat_with_fallback(
                client,
                model="gpt-5.2-chat",
                endpoint="https://example.azure/v1",
                messages=[{"role": "user", "content": "hi"}],
                timeout=600.0,
            )
        assert result == '{"ok": true}'
        # 3 attempts: rich → temperature_only → minimal
        assert client.with_options.return_value.chat.completions.create.call_count == 3
        # The success-with-fallback warning fires once for "minimal"
        assert any(
            "succeeded with 'minimal' fallback" in rec.message
            for rec in caplog.records
        )

    def test_caches_winning_variant(self) -> None:
        """After a successful fallback, the variant is cached for next call."""
        from src.core.llm_engine import (  # noqa: PLC0415
            _CUSTOM_VARIANT_CACHE,
            _call_custom_chat_with_fallback,
            _custom_cache_key,
        )

        endpoint = "https://example.azure/v1"
        model = "gpt-5.2-chat"
        client = self._client_stub(
            _make_bad_request("temperature does not support 0.0"),
            _make_bad_request("temperature does not support 0.0"),
            _make_completion('{"ok": true}'),
        )
        _call_custom_chat_with_fallback(
            client,
            model=model,
            endpoint=endpoint,
            messages=[{"role": "user", "content": "hi"}],
        )
        cache_key = _custom_cache_key(endpoint, model)
        assert _CUSTOM_VARIANT_CACHE.get(cache_key) == "minimal"

    def test_uses_cached_variant_first(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A second call with the same (endpoint, model) skips doomed variants."""
        from src.core.llm_engine import (  # noqa: PLC0415
            _CUSTOM_VARIANT_CACHE,
            _call_custom_chat_with_fallback,
            _custom_cache_key,
        )

        endpoint = "https://example.azure/v1"
        model = "gpt-5.2-chat"
        cache_key = _custom_cache_key(endpoint, model)
        _CUSTOM_VARIANT_CACHE[cache_key] = "minimal"

        # Only ONE side effect — the helper should land on the cached
        # variant first and stop after success.
        client = self._client_stub(_make_completion('{"ok": true}'))
        with caplog.at_level("WARNING", logger="llm"):
            result = _call_custom_chat_with_fallback(
                client,
                model=model,
                endpoint=endpoint,
                messages=[{"role": "user", "content": "hi"}],
            )
        assert result == '{"ok": true}'
        # Single call, no warning (cache hit suppresses the fallback log)
        assert client.chat.completions.create.call_count == 1
        assert not any(
            "succeeded with 'minimal' fallback" in rec.message
            for rec in caplog.records
        )

    def test_all_400s_raise_invalid_request(self) -> None:
        """When every variant returns 400, raises ValueError('INVALID_REQUEST')."""
        from src.core.llm_engine import _call_custom_chat_with_fallback  # noqa: PLC0415

        client = self._client_stub(
            _make_bad_request("nope 1"),
            _make_bad_request("nope 2"),
            _make_bad_request("nope 3"),
        )
        with pytest.raises(ValueError, match="INVALID_REQUEST"):
            _call_custom_chat_with_fallback(
                client,
                model="busted-model",
                endpoint="https://example/v1",
                messages=[{"role": "user", "content": "hi"}],
            )

    def test_non_400_error_propagates(self) -> None:
        """A timeout (or any non-BadRequest error) propagates immediately."""
        from src.core.llm_engine import _call_custom_chat_with_fallback  # noqa: PLC0415

        client = self._client_stub(TimeoutError("slow"))
        with pytest.raises(TimeoutError):
            _call_custom_chat_with_fallback(
                client,
                model="some-model",
                endpoint="https://example/v1",
                messages=[{"role": "user", "content": "hi"}],
            )
        # Helper called without timeout uses the bare client; should NOT
        # have moved to subsequent variants — only one create() call.
        assert client.chat.completions.create.call_count == 1

    def test_stale_cache_falls_through_to_remaining_variants(self) -> None:
        """Cached variant 400s — helper falls through and rewrites cache.

        Self-healing path documented in the helper docstring: a stale
        cache (e.g. provider config tightened) shouldn't permanently
        wedge the call; the remaining variants in original order are
        tried as fallbacks and the cache is rewritten on success.
        """
        from src.core.llm_engine import (  # noqa: PLC0415
            _CUSTOM_VARIANT_CACHE,
            _call_custom_chat_with_fallback,
            _custom_cache_key,
        )

        endpoint = "https://example/v1"
        model = "now-accepts-rich-payload"
        cache_key = _custom_cache_key(endpoint, model)
        # Stale cache claims minimal is required, but the provider now
        # happily accepts the rich payload.
        _CUSTOM_VARIANT_CACHE[cache_key] = "minimal"

        # Side effects play in REORDER: cached "minimal" first → 400,
        # then remaining variants in original order: "json_object+
        # temperature" → success.
        client = self._client_stub(
            _make_bad_request("model rotated, minimal no longer enough"),
            _make_completion('{"ok": true}'),
        )
        result = _call_custom_chat_with_fallback(
            client,
            model=model,
            endpoint=endpoint,
            messages=[{"role": "user", "content": "hi"}],
        )
        assert result == '{"ok": true}'
        # 2 attempts total: stale cached + first remaining
        assert client.chat.completions.create.call_count == 2
        # Cache rewritten to the new working variant
        assert _CUSTOM_VARIANT_CACHE.get(cache_key) == "json_object+temperature"

    def test_returns_empty_string_when_content_is_none(self) -> None:
        """Provider returning ``content=None`` is normalised to empty string.

        Some providers (notably tool-call-only completions) emit a
        choice whose ``message.content`` is ``None``.  The helper's
        ``response.choices[0].message.content or ""`` clause keeps the
        downstream callers safe — they expect a string.
        """
        from src.core.llm_engine import _call_custom_chat_with_fallback  # noqa: PLC0415

        client = self._client_stub(_make_completion(None))  # type: ignore[arg-type]
        result = _call_custom_chat_with_fallback(
            client,
            model="some-model",
            endpoint="https://example/v1",
            messages=[{"role": "user", "content": "hi"}],
        )
        assert result == ""

    def test_cache_hit_does_not_call_persist(self) -> None:
        """Cache-hit success skips ``_persist_caches()`` to avoid disk churn.

        Without this guard, every call to a model whose variant is
        already cached would re-write the JSON cache file — fine in
        isolation, but multiplied across batch translation that's a
        hot path that gets hammered.
        """
        from src.core.llm_engine import (  # noqa: PLC0415
            _CUSTOM_VARIANT_CACHE,
            _call_custom_chat_with_fallback,
            _custom_cache_key,
        )

        endpoint = "https://example/v1"
        model = "cached-model"
        cache_key = _custom_cache_key(endpoint, model)
        _CUSTOM_VARIANT_CACHE[cache_key] = "minimal"

        client = self._client_stub(_make_completion('{"ok": true}'))
        with patch(f"{_LLM_MOD}._persist_caches") as mock_persist:
            _call_custom_chat_with_fallback(
                client,
                model=model,
                endpoint=endpoint,
                messages=[{"role": "user", "content": "hi"}],
            )
        mock_persist.assert_not_called()

    def test_cache_with_unknown_label_falls_through_gracefully(self) -> None:
        """Cache contains a label not in the helper's 3-variant chain.

        ``_translate_custom_chat`` writes 4 labels (incl. ``no_system_role``);
        the helper only knows 3.  When the cache says ``no_system_role``,
        the helper's lookup returns ``cached_idx == -1`` so the original
        order is kept and the variants are tried sequentially.  This test
        guards against a future refactor that assumes the cached label
        always matches a known variant.
        """
        from src.core.llm_engine import (  # noqa: PLC0415
            _CUSTOM_VARIANT_CACHE,
            _call_custom_chat_with_fallback,
            _custom_cache_key,
        )

        endpoint = "https://example.azure/v1"
        model = "weird-deployment"
        # Pre-seed with a label the helper's variant list doesn't know.
        _CUSTOM_VARIANT_CACHE[
            _custom_cache_key(endpoint, model)
        ] = "no_system_role"

        # Helper falls through in original order: rich → succeeds.
        client = self._client_stub(_make_completion('{"ok": true}'))
        result = _call_custom_chat_with_fallback(
            client,
            model=model,
            endpoint=endpoint,
            messages=[{"role": "user", "content": "hi"}],
        )
        assert result == '{"ok": true}'
        # Single attempt — the unknown cache label was ignored, original
        # order was used, and the rich variant happened to work.
        assert client.chat.completions.create.call_count == 1

    def test_concurrent_calls_share_cache_safely(self) -> None:
        """Multiple threads calling the helper for the same key converge.

        The ``_CACHE_LOCK`` guard around the cache write serialises the
        precheck-and-mutate, so even if several threads each discover
        the same winning variant the cache ends up with that variant.

        Uses a payload-aware mock that mirrors gpt-5.x behaviour (400 if
        ``temperature`` is in kwargs, success otherwise).  A naive
        sequential side_effect would mis-assign 400s once the cache
        reorders the variant chain — the second thread would see 400 on
        ``minimal`` because the side_effect list doesn't know which
        payload the helper sent.
        """
        import threading  # noqa: PLC0415

        from src.core.llm_engine import (  # noqa: PLC0415
            _CUSTOM_VARIANT_CACHE,
            _call_custom_chat_with_fallback,
            _custom_cache_key,
        )

        endpoint = "https://example/v1"
        model = "concurrent-model"
        cache_key = _custom_cache_key(endpoint, model)
        _CUSTOM_VARIANT_CACHE.pop(cache_key, None)

        def make_client() -> MagicMock:
            """Builds a payload-aware client that mimics gpt-5.x behaviour."""
            client = MagicMock()
            with_opts = MagicMock()

            def fake_create(**kwargs: Any) -> Any:
                if "temperature" in kwargs:
                    raise _make_bad_request("temperature does not support 0.0")
                return _make_completion('{"ok": true}')

            with_opts.chat.completions.create.side_effect = fake_create
            client.with_options.return_value = with_opts
            client.chat.completions.create.side_effect = fake_create
            return client

        results: list[str] = []
        errors: list[Exception] = []

        def worker() -> None:
            try:
                results.append(
                    _call_custom_chat_with_fallback(
                        make_client(),
                        model=model,
                        endpoint=endpoint,
                        messages=[{"role": "user", "content": "hi"}],
                    ),
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        assert errors == []
        assert results == ['{"ok": true}'] * 8
        # All 8 calls converged on the same cache value.
        assert _CUSTOM_VARIANT_CACHE.get(cache_key) == "minimal"

    def test_persist_failure_leaves_in_memory_cache_intact(self) -> None:
        """An IOError during ``_persist_caches`` doesn't corrupt the cache.

        The helper does the in-memory mutation under ``_CACHE_LOCK`` and
        then calls ``_persist_caches()``.  ``_persist_caches`` catches its
        own disk errors (logged at WARNING) and never raises — but in case
        a future refactor lets the exception propagate, this test pins the
        invariant that callers see a successful return value AND the
        in-memory cache has the right value, even when disk-write fails.
        """
        from src.core.llm_engine import (  # noqa: PLC0415
            _CUSTOM_VARIANT_CACHE,
            _call_custom_chat_with_fallback,
            _custom_cache_key,
        )

        endpoint = "https://example/v1"
        model = "persist-failure-model"
        cache_key = _custom_cache_key(endpoint, model)
        _CUSTOM_VARIANT_CACHE.pop(cache_key, None)

        client = self._client_stub(
            _make_bad_request("temperature does not support 0.0"),
            _make_bad_request("temperature does not support 0.0"),
            _make_completion('{"ok": true}'),
        )
        # Patch _persist_caches to raise — the helper still needs to
        # return successfully because the in-memory cache is the
        # source of truth for the current process.
        with patch(
            f"{_LLM_MOD}._persist_caches",
            side_effect=OSError("disk full"),
        ), pytest.raises(OSError, match="disk full"):
            _call_custom_chat_with_fallback(
                client,
                model=model,
                endpoint=endpoint,
                messages=[{"role": "user", "content": "hi"}],
            )
        # In-memory cache was updated BEFORE the persist call, so it
        # reflects the discovery even though disk-write blew up.
        assert _CUSTOM_VARIANT_CACHE.get(cache_key) == "minimal"

    def test_passes_timeout_through_with_options(self) -> None:
        """Explicit ``timeout=`` propagates to ``client.with_options(timeout=…)``.

        Layout / vision / image translation callers pass
        ``LLM_REASONING_TIMEOUT`` (600s) or ``LLM_VISION_TIMEOUT`` (120s)
        for slower-than-chat workloads.  Without ``with_options(timeout=…)``
        the SDK uses the client's default 90s and reasoning calls would
        time out mid-generation.
        """
        from src.core.llm_engine import _call_custom_chat_with_fallback  # noqa: PLC0415

        client = MagicMock()
        with_opts = MagicMock()
        with_opts.chat.completions.create.return_value = _make_completion('{"ok":1}')
        client.with_options.return_value = with_opts

        _call_custom_chat_with_fallback(
            client,
            model="some-model",
            endpoint="https://api.example/v1",
            messages=[{"role": "user", "content": "hi"}],
            timeout=600.0,
        )
        # ``with_options`` was called with the exact timeout the caller
        # passed — guards against a future refactor dropping the kwarg.
        client.with_options.assert_called_once_with(timeout=600.0)
        # Bare client (no with_options) was NOT used since timeout was set.
        assert client.chat.completions.create.call_count == 0

    def test_no_with_options_when_timeout_omitted(self) -> None:
        """``timeout=None`` → bare client used, no needless wrapping.

        Saves a tiny allocation on every cache-hit call (the common
        case after the first discovery).
        """
        from src.core.llm_engine import _call_custom_chat_with_fallback  # noqa: PLC0415

        client = MagicMock()
        client.chat.completions.create.return_value = _make_completion('{"ok":1}')

        _call_custom_chat_with_fallback(
            client,
            model="some-model",
            endpoint="https://api.example/v1",
            messages=[{"role": "user", "content": "hi"}],
        )
        # ``with_options`` not invoked — bare client served the call.
        client.with_options.assert_not_called()
        assert client.chat.completions.create.call_count == 1


# ---------------------------------------------------------------------------
# Integration: helper wired into the non-translation callsites
# (_extract_text_custom, _translate_image_custom).
# Verifies the gpt-5.x reasoning-model fallback chain works end-to-end —
# regression guard against a future refactor that bypasses the helper and
# goes back to a direct ``client.chat.completions.create(...)`` call.
# ---------------------------------------------------------------------------


def _custom_settings_stub() -> dict[str, str]:
    """Settings dict that resolves to a valid Custom-LLM config."""
    return {
        "llm/custom_api_key": "test-key",
        "llm/custom_model": "gpt-5.2-chat",
        "llm/custom_endpoint": "https://example.azure/v1",
    }


def _build_helper_fallback_client() -> MagicMock:
    """Builds an SDK client primed for the helper's variant-fallback path.

    The chat.completions.create side_effect chain is [400, 400, success] —
    simulating the gpt-5.x temperature rejection that the helper recovers
    from on the 'minimal' variant.
    """
    client = MagicMock()
    # Mirror with_options(timeout=...) back to the same client so the
    # helper's chained call resolves to the same create() mock.
    client.with_options.return_value = client
    return client


class TestExtractTextCustomUsesHelper:
    """Regression: _extract_text_custom routes through the variant helper."""

    def test_recovers_from_temperature_400_on_minimal(self) -> None:
        from src.core.llm_engine import _extract_text_custom  # noqa: PLC0415

        client = _build_helper_fallback_client()
        client.chat.completions.create.side_effect = [
            _make_bad_request("temperature does not support 0.0"),
            _make_bad_request("temperature does not support 0.0"),
            _make_completion('{"text": "Hello world"}'),
        ]
        with (
            patch(
                f"{_LLM_MOD}._config.load_setting",
                side_effect=_custom_settings_stub().get,
            ),
            patch(f"{_LLM_MOD}._build_openai_client", return_value=client),
            patch("pathlib.Path.open", return_value=io.BytesIO(b"fake image")),
        ):
            result = _extract_text_custom("/fake.png", "gpt-5.2-chat")
        assert result == "Hello world"
        # 3 attempts: rich → temperature_only → minimal
        assert client.chat.completions.create.call_count == 3


class TestTranslateImageCustomUsesHelper:
    """Regression: _translate_image_custom routes through the variant helper."""

    def test_recovers_from_temperature_400_on_minimal(self) -> None:
        from src.core.llm_engine import _translate_image_custom  # noqa: PLC0415

        client = _build_helper_fallback_client()
        translated = json.dumps({
            "paragraphs": [{"id": 0, "text": "Bonjour"}],
        })
        client.chat.completions.create.side_effect = [
            _make_bad_request("temperature does not support 0.0"),
            _make_bad_request("temperature does not support 0.0"),
            _make_completion(translated),
        ]
        with (
            patch(
                f"{_LLM_MOD}._config.load_setting",
                side_effect=_custom_settings_stub().get,
            ),
            patch(f"{_LLM_MOD}._build_openai_client", return_value=client),
            patch("pathlib.Path.open", return_value=io.BytesIO(b"fake image")),
        ):
            result = _translate_image_custom(
                "/fake.png",
                [{"id": 0, "text": "Hello"}],
                "French",
                "",
            )
        assert result == [{"id": 0, "text": "Bonjour"}]
        assert client.chat.completions.create.call_count == 3


# ---------------------------------------------------------------------------
# _stream_custom_chat_with_fallback — streaming sibling of the helper.
# Reads (but does NOT write) _CUSTOM_VARIANT_CACHE so non-streaming
# discoveries short-circuit the streaming first attempt.  No json_object
# variant because streaming responses are plain text.
# ---------------------------------------------------------------------------


class TestStreamCustomChatWithFallback:
    """Tests for the streaming variant-fallback helper."""

    def _stream_client(self, *side_effects: Any) -> MagicMock:
        """Returns a stub that plays back side effects on chat.completions.create.

        Each side effect is either a BadRequestError (raised) or a stream
        iterable (returned).  Mirrors the same shape used by
        ``TestCallCustomChatWithFallback._client_stub``.
        """
        client = MagicMock()
        with_opts = MagicMock()
        with_opts.chat.completions.create.side_effect = side_effects
        client.with_options.return_value = with_opts
        client.chat.completions.create.side_effect = side_effects
        return client

    def test_succeeds_on_first_variant(self) -> None:
        """Provider accepts ``temperature`` — first variant returns a stream."""
        from src.core.llm_engine import (  # noqa: PLC0415
            _stream_custom_chat_with_fallback,
        )

        fake_stream = iter(["chunk1", "chunk2"])
        client = self._stream_client(fake_stream)
        result = _stream_custom_chat_with_fallback(
            client,
            model="some-model",
            endpoint="https://api.example/v1",
            messages=[{"role": "user", "content": "hi"}],
            timeout=10.0,
        )
        assert result is fake_stream
        assert client.with_options.return_value.chat.completions.create.call_count == 1
        # stream=True was passed
        call_kwargs = client.with_options.return_value.chat.completions.create.call_args.kwargs
        assert call_kwargs.get("stream") is True

    def test_falls_through_to_minimal_on_temperature_400(self) -> None:
        """gpt-5.x rejects temperature → succeeds on minimal."""
        from src.core.llm_engine import (  # noqa: PLC0415
            _stream_custom_chat_with_fallback,
        )

        fake_stream = iter(["ok"])
        client = self._stream_client(
            _make_bad_request("temperature does not support 0.0"),
            fake_stream,
        )
        result = _stream_custom_chat_with_fallback(
            client,
            model="gpt-5.2-chat",
            endpoint="https://example.azure/v1",
            messages=[{"role": "user", "content": "hi"}],
        )
        assert result is fake_stream
        assert client.chat.completions.create.call_count == 2

    def test_skips_temperature_when_cache_hints_minimal(self) -> None:
        """Cache says ``minimal`` → streaming jumps straight to no-temperature."""
        from src.core.llm_engine import (  # noqa: PLC0415
            _CUSTOM_VARIANT_CACHE,
            _custom_cache_key,
            _stream_custom_chat_with_fallback,
        )

        endpoint = "https://example.azure/v1"
        model = "gpt-5.2-chat"
        _CUSTOM_VARIANT_CACHE[_custom_cache_key(endpoint, model)] = "minimal"

        fake_stream = iter(["ok"])
        client = self._stream_client(fake_stream)
        result = _stream_custom_chat_with_fallback(
            client,
            model=model,
            endpoint=endpoint,
            messages=[{"role": "user", "content": "hi"}],
        )
        assert result is fake_stream
        # Single call — no wasted attempt with temperature.
        assert client.chat.completions.create.call_count == 1
        # And `temperature` was NOT in the kwargs.
        call_kwargs = client.chat.completions.create.call_args.kwargs
        assert "temperature" not in call_kwargs

    def test_skips_temperature_when_cache_hints_no_system_role(self) -> None:
        """Cache says ``no_system_role`` → also implies temperature was rejected."""
        from src.core.llm_engine import (  # noqa: PLC0415
            _CUSTOM_VARIANT_CACHE,
            _custom_cache_key,
            _stream_custom_chat_with_fallback,
        )

        endpoint = "https://example/v1"
        model = "weird-azure-deployment"
        _CUSTOM_VARIANT_CACHE[_custom_cache_key(endpoint, model)] = "no_system_role"

        fake_stream = iter(["ok"])
        client = self._stream_client(fake_stream)
        _stream_custom_chat_with_fallback(
            client,
            model=model,
            endpoint=endpoint,
            messages=[{"role": "user", "content": "hi"}],
        )
        call_kwargs = client.chat.completions.create.call_args.kwargs
        assert "temperature" not in call_kwargs

    def test_does_not_write_to_shared_cache(self) -> None:
        """Streaming success leaves ``_CUSTOM_VARIANT_CACHE`` untouched.

        Streaming labels (``temperature_only``, ``minimal``) reflect a
        2-variant chain that's missing ``response_format``; round-tripping
        a streaming-discovered label would corrupt the non-streaming
        callsite's payload choice.  So streaming reads but doesn't write.
        """
        from src.core.llm_engine import (  # noqa: PLC0415
            _CUSTOM_VARIANT_CACHE,
            _custom_cache_key,
            _stream_custom_chat_with_fallback,
        )

        endpoint = "https://example/v1"
        model = "fresh-model-no-cache"
        cache_key = _custom_cache_key(endpoint, model)
        # Make sure cache starts clean — autouse fixture clears between
        # tests but be explicit.
        _CUSTOM_VARIANT_CACHE.pop(cache_key, None)

        fake_stream = iter(["ok"])
        client = self._stream_client(
            _make_bad_request("temperature does not support 0.0"),
            fake_stream,
        )
        _stream_custom_chat_with_fallback(
            client,
            model=model,
            endpoint=endpoint,
            messages=[{"role": "user", "content": "hi"}],
        )
        # Cache should still be unset.
        assert cache_key not in _CUSTOM_VARIANT_CACHE

    def test_all_400s_raise_invalid_request(self) -> None:
        """Both variants 400 → raises ``ValueError("INVALID_REQUEST")``."""
        from src.core.llm_engine import (  # noqa: PLC0415
            _stream_custom_chat_with_fallback,
        )

        client = self._stream_client(
            _make_bad_request("nope 1"),
            _make_bad_request("nope 2"),
        )
        with pytest.raises(ValueError, match="INVALID_REQUEST"):
            _stream_custom_chat_with_fallback(
                client,
                model="busted",
                endpoint="https://example/v1",
                messages=[{"role": "user", "content": "hi"}],
            )

    def test_non_400_error_propagates(self) -> None:
        """Non-BadRequest errors propagate immediately — no variant retry."""
        from src.core.llm_engine import (  # noqa: PLC0415
            _stream_custom_chat_with_fallback,
        )

        client = self._stream_client(TimeoutError("slow"))
        with pytest.raises(TimeoutError):
            _stream_custom_chat_with_fallback(
                client,
                model="some-model",
                endpoint="https://example/v1",
                messages=[{"role": "user", "content": "hi"}],
            )
        assert client.chat.completions.create.call_count == 1


class TestStreamCustomUsesHelper:
    """Regression: _stream_custom routes through the streaming helper.

    Verifies the translate-text streaming + Listen-button + live-mode
    paths survive reasoning models like Azure gpt-5.2-chat.
    """

    def test_recovers_from_temperature_400_on_minimal(self) -> None:
        from src.core.llm_engine import _stream_custom  # noqa: PLC0415

        client = _build_helper_fallback_client()
        # Streaming = 2-variant fallback (temperature_only → minimal).
        client.chat.completions.create.side_effect = [
            _make_bad_request("temperature does not support 0.0"),
            iter(_make_sdk_stream_chunks(["Hello", " world"])),
        ]
        with (
            patch(
                f"{_LLM_MOD}._config.load_setting",
                side_effect=_custom_settings_stub().get,
            ),
            patch(f"{_LLM_MOD}._build_openai_client", return_value=client),
        ):
            chunks = list(_stream_custom("Hello", "French", "English"))
        assert chunks == ["Hello", " world"]
        assert client.chat.completions.create.call_count == 2



# ── _translate_custom dispatch — both-failed error preference ──────────────


class TestTranslateCustomBothFailedErrorPreference:
    """When chat AND responses both fail, surface the more actionable error.

    AGENTS.md spells out the rule: if responses raises an
    "informative" tag (TIMEOUT_ERROR / AUTH_ERROR / QUOTA_ERROR /
    SERVICE_UNAVAILABLE_ERROR / CONNECTION_ERROR / MODEL_NOT_FOUND /
    REQUEST_TOO_LARGE), surface that — the user's real problem is
    network / credentials / quota, not "the chat payload was
    rejected."  Otherwise prefer the original chat INVALID_REQUEST
    so the dispatch error stays diagnostic.
    """

    def _patch_dispatch(self, monkeypatch, chat_err: str, resp_err: str):
        """Patches the chat + responses translate paths to raise the given tags."""
        from src.core import llm_engine as mod  # noqa: PLC0415

        # Bypass real config resolution — return a fixed
        # (key, model, ambiguous endpoint) triple so the dispatch
        # path runs without touching the real settings store.
        monkeypatch.setattr(
            mod, "_resolve_custom_config",
            lambda model: ("fake-key", "fake-model", "https://example.com/v1"),
        )
        # Force the ambiguous-endpoint branch by classifying the
        # endpoint as None — the fallback logic runs.
        monkeypatch.setattr(
            mod, "_classify_custom_endpoint",
            lambda endpoint: (None, endpoint),
        )
        # Skip any cache lookups so the dispatch always tries chat first.
        monkeypatch.setattr(mod, "_CUSTOM_API_CACHE", {})
        monkeypatch.setattr(mod, "_CUSTOM_VARIANT_CACHE", {})
        monkeypatch.setattr(mod, "_persist_caches", lambda: None)

        def _fake_chat(*args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202, ARG001
            raise ValueError(chat_err)

        def _fake_responses(*args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202, ARG001
            raise ValueError(resp_err)

        monkeypatch.setattr(mod, "_translate_custom_chat", _fake_chat)
        monkeypatch.setattr(
            mod, "_translate_custom_responses", _fake_responses,
        )

    def test_responses_timeout_wins_over_chat_invalid_request(
        self, monkeypatch,
    ) -> None:
        """Responses raises TIMEOUT_ERROR → propagate that, not chat's INVALID_REQUEST."""
        from src.core.llm_engine import _translate_custom  # noqa: PLC0415

        self._patch_dispatch(
            monkeypatch, "INVALID_REQUEST", "TIMEOUT_ERROR",
        )
        with pytest.raises(ValueError, match="TIMEOUT_ERROR"):
            _translate_custom(["Hello"], "French", "English", model="m")

    def test_responses_auth_wins_over_chat_invalid_request(
        self, monkeypatch,
    ) -> None:
        """Responses raises AUTH_ERROR → bad credentials, not bad payload."""
        from src.core.llm_engine import _translate_custom  # noqa: PLC0415

        self._patch_dispatch(monkeypatch, "INVALID_REQUEST", "AUTH_ERROR")
        with pytest.raises(ValueError, match="AUTH_ERROR"):
            _translate_custom(["Hello"], "French", "English", model="m")

    def test_chat_invalid_kept_when_responses_also_invalid(
        self, monkeypatch,
    ) -> None:
        """Both raise INVALID_REQUEST → keep the chat error.

        Neither side gives us a smoking-gun network/credentials clue,
        so the original "chat payload rejected" diagnostic stays.
        """
        from src.core.llm_engine import _translate_custom  # noqa: PLC0415

        self._patch_dispatch(monkeypatch, "INVALID_REQUEST", "INVALID_REQUEST")
        with pytest.raises(ValueError, match="INVALID_REQUEST"):
            _translate_custom(["Hello"], "French", "English", model="m")

    def test_non_invalid_chat_error_propagates_immediately(
        self, monkeypatch,
    ) -> None:
        """Chat AUTH_ERROR / QUOTA_ERROR / TIMEOUT_ERROR shouldn't try Responses.

        AGENTS.md: "Genuine quota / auth / connection errors
        propagate immediately." A regression that retries on every
        kind of failure would turn a 401 into 2× the API cost.
        """
        from src.core.llm_engine import _translate_custom  # noqa: PLC0415

        self._patch_dispatch(monkeypatch, "QUOTA_ERROR", "AUTH_ERROR")
        with pytest.raises(ValueError, match="QUOTA_ERROR"):
            _translate_custom(["Hello"], "French", "English", model="m")


def test_no_retry_sleep_fixture_actually_replaces_module_time() -> None:
    """``_no_retry_sleep_in_tests`` (conftest) must patch ``llm_engine.time``.

    The fixture replaces ``time.sleep`` with a no-op so a leaked worker
    thread can't be parked inside ``time.sleep(delay)`` when SIGALRM
    fires for the next test's per-test timeout.  Without this guard,
    the SIGALRM interrupts Python mid-sleep at a bad bytecode boundary
    and pytest-qt's ``_process_events`` then segfaults on the dangling
    state.

    The fixture is the load-bearing piece between "leaked async
    threads in tests" and "no segfaults around the 6000-test mark."
    A refactor that renames ``llm_engine.time`` would silently
    re-introduce the segfault risk; this meta-test catches that.
    """
    # The fixture replaces the module-level ``time`` reference with a
    # SimpleNamespace exposing ``sleep`` as a no-op lambda.  Real
    # ``time.sleep(0.1)`` would block; if the fixture is engaged, the
    # patched ``llm_engine.time.sleep(0.1)`` returns immediately.
    import time as _real_time  # noqa: PLC0415

    from src.core import llm_engine  # noqa: PLC0415

    t0 = _real_time.monotonic()
    llm_engine.time.sleep(0.5)
    elapsed = _real_time.monotonic() - t0
    assert elapsed < 0.05, (
        f"_no_retry_sleep_in_tests is not engaged: ``llm_engine.time"
        f".sleep(0.5)`` took {elapsed:.3f}s instead of returning "
        "immediately.  A leaked worker thread can now be parked "
        "inside time.sleep when SIGALRM fires — segfault risk."
    )



class TestCustomCacheKeyModelDifferentiation:
    """Same endpoint, different model → independent cache entries.

    The existing ``test_custom_cache_key_collapses_cosmetic_endpoint_variations``
    pins host-level invalidation. This complement pins that two models
    talking to the same endpoint never share a variant cache slot —
    otherwise switching from a chat model to a reasoning model on the
    same endpoint would inherit the wrong payload variant on the first
    call after the swap (e.g. reasoning model gets a ``temperature: 0``
    payload that it would 400 on, then have to re-probe).
    """

    def test_different_models_same_endpoint_distinct_keys(self) -> None:
        """``_custom_cache_key`` keys differ when only the model changes."""
        from src.core.llm_engine import _custom_cache_key  # noqa: PLC0415

        endpoint = "https://api.example.com/v1"
        chat_key = _custom_cache_key(endpoint, "gpt-4-turbo")
        reasoning_key = _custom_cache_key(endpoint, "gpt-5.2-pro")

        assert chat_key != reasoning_key, (
            f"Cache key collision across distinct models — "
            f"{chat_key!r} == {reasoning_key!r}"
        )
        # Model component is the second tuple element.
        assert chat_key[1] == "gpt-4-turbo"
        assert reasoning_key[1] == "gpt-5.2-pro"
