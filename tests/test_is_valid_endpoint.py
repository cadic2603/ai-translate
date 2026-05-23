"""Tests for the is_valid_endpoint() URL check used by custom LLM providers."""

from __future__ import annotations

import pytest

from src.utils.config_manager import is_valid_endpoint


class TestIsValidEndpoint:
    """Accepts http/https URLs, rejects garbage that used to pass truthiness."""

    @pytest.mark.parametrize(
        "url",
        [
            "http://localhost:8080/v1",
            "https://api.openai.com/v1/chat/completions",
            "https://example.com",
            "http://127.0.0.1",
            "https://inference.example.com/v1/chat/completions?model=gpt-4",
        ],
    )
    def test_accepts_well_formed_urls(self, url: str) -> None:
        assert is_valid_endpoint(url) is True

    @pytest.mark.parametrize(
        "url",
        [
            "",
            "   ",
            "e",
            "not-a-url",
            "localhost:8080",  # missing scheme
            "ftp://example.com",  # wrong scheme
            "file:///tmp/foo",  # wrong scheme
            "https://",  # missing netloc
            "http://",  # missing netloc
            "://missing",  # missing scheme
        ],
    )
    def test_rejects_garbage(self, url: str) -> None:
        assert is_valid_endpoint(url) is False

    def test_trims_whitespace(self) -> None:
        assert is_valid_endpoint("  https://example.com  ") is True

    def test_handles_non_string_gracefully(self) -> None:
        # Settings can surface None or int if the JSON blob is malformed.
        assert is_valid_endpoint(None) is False  # type: ignore[arg-type]
