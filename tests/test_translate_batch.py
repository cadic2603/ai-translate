"""Unit tests for translate_batch in src/core/llm_engine."""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.core.llm_engine import translate_batch


@pytest.fixture
def _mock_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patches translate_text to return uppercased input."""
    monkeypatch.setattr(
        "src.core.llm_engine.translate_text",
        lambda texts, *a, **kw: [t.upper() for t in texts],
    )


@pytest.fixture
def _mock_batch_size(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sets batch size to 3 for easier testing."""
    monkeypatch.setattr(
        "src.core.llm_engine.TRANSLATION_BATCH_SIZE",
        3,
    )


# ── Basic translation ────────────────────────────────────────


@pytest.mark.usefixtures("_mock_llm", "_mock_batch_size")
def test_translate_batch_basic() -> None:
    """All values are translated when no checkpoint exists."""
    result = translate_batch(["a", "b", "c", "d"], "FR", "")
    assert result == ["A", "B", "C", "D"]


@pytest.mark.usefixtures("_mock_llm")
def test_translate_batch_empty_input() -> None:
    """Empty input returns empty list."""
    result = translate_batch([], "FR", "")
    assert result == []


# ── Cancellation ─────────────────────────────────────────────


@pytest.mark.usefixtures("_mock_llm")
def test_translate_batch_cancel_before_start() -> None:
    """Returns None when cancelled before processing."""
    result = translate_batch(["a"], "FR", "", cancel_check=lambda: True)
    assert result is None


@pytest.mark.usefixtures("_mock_batch_size")
def test_translate_batch_cancel_mid_batch() -> None:
    """Returns None when cancelled between batches."""
    call_count = 0

    def mock_translate(
        texts: list[str],
        *a: Any,  # noqa: ANN401
        **kw: Any,  # noqa: ANN401
    ) -> list[str]:
        return [t.upper() for t in texts]

    def cancel_after_first() -> bool:
        nonlocal call_count
        call_count += 1
        return call_count > 2  # noqa: PLR2004 — cancel after first batch

    with patch("src.core.llm_engine.translate_text", mock_translate):
        result = translate_batch(
            ["a", "b", "c", "d", "e", "f"],
            "FR",
            "",
            cancel_check=cancel_after_first,
        )
    assert result is None


# ── Progress callback ────────────────────────────────────────


@pytest.mark.usefixtures("_mock_llm", "_mock_batch_size")
def test_progress_callback_called() -> None:
    """Progress callback receives increasing percentages."""
    progress_values: list[int] = []
    translate_batch(
        ["a", "b", "c", "d"],
        "FR",
        "",
        progress_callback=progress_values.append,
    )
    assert len(progress_values) >= 1
    assert progress_values[-1] == 100  # noqa: PLR2004


# ── Checkpoint: full cache ───────────────────────────────────


@pytest.mark.usefixtures("_mock_batch_size")
def test_all_cached_returns_immediately(tmp_path: Path) -> None:
    """Returns cached results without calling translate_text."""
    cached = {0: "X", 1: "Y", 2: "Z"}

    with (
        patch("src.core.checkpoint.load_batch_checkpoint", return_value=cached),
        patch("src.core.llm_engine.translate_text") as mock_translate,
    ):
        result = translate_batch(
            ["a", "b", "c"],
            "FR",
            "",
            checkpoint_dir=tmp_path,
        )

    assert result == ["X", "Y", "Z"]
    mock_translate.assert_not_called()


# ── Checkpoint: partial cache within a batch ─────────────────


@pytest.mark.usefixtures("_mock_batch_size")
def test_partial_cache_only_translates_uncached(tmp_path: Path) -> None:
    """Only uncached items within a batch are sent to the LLM."""
    cached = {0: "CACHED_A", 2: "CACHED_C"}
    translated_inputs: list[list[str]] = []

    def mock_translate(
        texts: list[str],
        *a: Any,  # noqa: ANN401
        **kw: Any,  # noqa: ANN401
    ) -> list[str]:
        translated_inputs.append(texts)
        return [t.upper() for t in texts]

    with (
        patch("src.core.checkpoint.load_batch_checkpoint", return_value=cached),
        patch("src.core.llm_engine.translate_text", mock_translate),
        patch("src.core.checkpoint.save_batch_progress"),
    ):
        result = translate_batch(
            ["a", "b", "c"],
            "FR",
            "",
            checkpoint_dir=tmp_path,
        )

    assert result == ["CACHED_A", "B", "CACHED_C"]
    # Only "b" (index 1) should have been sent to the LLM
    assert translated_inputs == [["b"]]


# ── Checkpoint: short LLM response skips save ───────────────


@pytest.mark.usefixtures("_mock_batch_size")
def test_short_response_does_not_save_checkpoint(tmp_path: Path) -> None:
    """Checkpoint is NOT saved when LLM returns fewer results than expected."""

    def mock_translate(
        texts: list[str],
        *a: Any,  # noqa: ANN401
        **kw: Any,  # noqa: ANN401
    ) -> list[str]:
        # Return only 1 result for 3 inputs
        return ["ONLY_ONE"]

    save_mock = MagicMock()

    with (
        patch("src.core.checkpoint.load_batch_checkpoint", return_value=None),
        patch("src.core.llm_engine.translate_text", mock_translate),
        patch("src.core.checkpoint.save_batch_progress", save_mock),
    ):
        result = translate_batch(
            ["a", "b", "c"],
            "FR",
            "",
            checkpoint_dir=tmp_path,
        )

    # First item translated, rest keep originals as fallback
    assert result == ["ONLY_ONE", "b", "c"]
    # Checkpoint must NOT be saved to avoid persisting untranslated originals
    save_mock.assert_not_called()


@pytest.mark.usefixtures("_mock_batch_size")
def test_full_response_saves_checkpoint(tmp_path: Path) -> None:
    """Checkpoint IS saved when LLM returns all expected results."""

    def mock_translate(
        texts: list[str],
        *a: Any,  # noqa: ANN401
        **kw: Any,  # noqa: ANN401
    ) -> list[str]:
        return [t.upper() for t in texts]

    save_mock = MagicMock()

    with (
        patch("src.core.checkpoint.load_batch_checkpoint", return_value=None),
        patch("src.core.llm_engine.translate_text", mock_translate),
        patch("src.core.checkpoint.save_batch_progress", save_mock),
    ):
        translate_batch(
            ["a", "b", "c"],
            "FR",
            "",
            checkpoint_dir=tmp_path,
        )

    save_mock.assert_called_once()


# ── LLM error propagation ────────────────────────────────────


@pytest.mark.usefixtures("_mock_batch_size")
def test_llm_error_propagates() -> None:
    """ValueError from the LLM propagates through translate_batch."""
    with (
        patch(
            "src.core.llm_engine.translate_text",
            side_effect=ValueError("AUTH_ERROR"),
        ),
        pytest.raises(ValueError, match="AUTH_ERROR"),
    ):
        translate_batch(["a", "b"], "FR", "")


# ── Glossary entries forwarding ──────────────────────────────


@pytest.mark.usefixtures("_mock_batch_size")
def test_glossary_entries_forwarded() -> None:
    """Glossary entries are passed to translate_text."""
    captured_kw: dict[str, Any] = {}

    def mock_translate(
        texts: list[str],
        *a: Any,  # noqa: ANN401
        **kw: Any,  # noqa: ANN401
    ) -> list[str]:
        captured_kw.update(kw)
        return [t.upper() for t in texts]

    glossary = [(1, "hello", "bonjour"), (2, "world", "monde")]

    with patch("src.core.llm_engine.translate_text", mock_translate):
        translate_batch(
            ["hello world"],
            "FR",
            "",
            glossary_entries=glossary,
        )

    assert captured_kw["glossary_entries"] == glossary


# ── Single item ──────────────────────────────────────────────


@pytest.mark.usefixtures("_mock_llm")
def test_translate_batch_single_item() -> None:
    """A single-item list is translated correctly."""
    result = translate_batch(["hello"], "FR", "")
    assert result == ["HELLO"]


# ── Multiple batches ─────────────────────────────────────────


@pytest.mark.usefixtures("_mock_batch_size")
def test_translate_batch_multi_batch_boundary() -> None:
    """Items spanning multiple batches are all translated."""

    def mock_translate(
        texts: list[str],
        *a: Any,  # noqa: ANN401
        **kw: Any,  # noqa: ANN401
    ) -> list[str]:
        return [t.upper() for t in texts]

    with patch("src.core.llm_engine.translate_text", mock_translate):
        # batch_size=3, so 7 items → 3 batches (3+3+1)
        result = translate_batch(
            ["a", "b", "c", "d", "e", "f", "g"],
            "FR",
            "",
        )

    assert result == ["A", "B", "C", "D", "E", "F", "G"]


# ── No checkpoint dir ────────────────────────────────────────


@pytest.mark.usefixtures("_mock_llm", "_mock_batch_size")
def test_translate_batch_no_checkpoint_dir() -> None:
    """Without checkpoint_dir, all values are translated without caching."""
    result = translate_batch(
        ["hello", "world"],
        "FR",
        "",
        checkpoint_dir=None,
    )
    assert result == ["HELLO", "WORLD"]


# ── All cached triggers 100% progress ────────────────────────


@pytest.mark.usefixtures("_mock_batch_size")
def test_all_cached_triggers_progress_100(tmp_path: Path) -> None:
    """When all values are cached, progress callback receives 100."""
    cached = {0: "X", 1: "Y"}
    progress_values: list[int] = []

    with (
        patch(
            "src.core.checkpoint.load_batch_checkpoint",
            return_value=cached,
        ),
        patch("src.core.llm_engine.translate_text") as mock_t,
    ):
        translate_batch(
            ["a", "b"],
            "FR",
            "",
            progress_callback=progress_values.append,
            checkpoint_dir=tmp_path,
        )

    assert progress_values == [100]
    mock_t.assert_not_called()


# ── content_type is always CONTENT_DATA_VALUES ────────────────


@pytest.mark.usefixtures("_mock_batch_size")
def test_content_type_is_data_values() -> None:
    """translate_batch always uses CONTENT_DATA_VALUES content type."""
    captured_kw: dict[str, Any] = {}

    def mock_translate(
        texts: list[str],
        *a: Any,  # noqa: ANN401
        **kw: Any,  # noqa: ANN401
    ) -> list[str]:
        captured_kw.update(kw)
        return [t.upper() for t in texts]

    with patch("src.core.llm_engine.translate_text", mock_translate):
        translate_batch(["hello"], "FR", "")

    from src.constants.llm import CONTENT_DATA_VALUES  # noqa: PLC0415

    assert captured_kw["content_type"] == CONTENT_DATA_VALUES


# ── Unicode values ────────────────────────────────────────────


@pytest.mark.usefixtures("_mock_llm")
def test_translate_batch_unicode_values() -> None:
    """Unicode values (CJK, accented) are translated correctly."""
    result = translate_batch(["café", "Straße", "你好"], "FR", "")
    assert result == ["CAFÉ", "STRASSE", "你好"]


# ── Partial cache across batch boundary ──────────────────────


@pytest.mark.usefixtures("_mock_batch_size")
def test_partial_cache_spans_batches(tmp_path: Path) -> None:
    """Partial cache spanning multiple batches handles correctly."""
    # batch_size=3, 6 items → 2 batches. Cache item 4 (in second batch).
    cached = {4: "CACHED_E"}

    def mock_translate(
        texts: list[str],
        *a: Any,  # noqa: ANN401
        **kw: Any,  # noqa: ANN401
    ) -> list[str]:
        return [t.upper() for t in texts]

    with (
        patch(
            "src.core.checkpoint.load_batch_checkpoint",
            return_value=cached,
        ),
        patch("src.core.llm_engine.translate_text", mock_translate),
        patch("src.core.checkpoint.save_batch_progress"),
    ):
        result = translate_batch(
            ["a", "b", "c", "d", "e", "f"],
            "FR",
            "",
            checkpoint_dir=tmp_path,
        )

    assert result is not None
    assert result[4] == "CACHED_E"
    # Others should be translated
    assert result[0] == "A"
    assert result[5] == "F"


# ── Glossary None / empty forwarding ─────────────────────────


def test_glossary_entries_none_forwarded() -> None:
    """glossary_entries=None is forwarded to translate_text as None."""
    captured_kw: dict[str, Any] = {}

    def mock_translate(
        texts: list[str],
        *a: Any,  # noqa: ANN401
        **kw: Any,  # noqa: ANN401
    ) -> list[str]:
        captured_kw.update(kw)
        return [t.upper() for t in texts]

    with patch("src.core.llm_engine.translate_text", mock_translate):
        translate_batch(["hello"], "FR", "", glossary_entries=None)

    assert "glossary_entries" in captured_kw
    assert captured_kw["glossary_entries"] is None


def test_glossary_entries_empty_list_forwarded() -> None:
    """glossary_entries=[] is forwarded to translate_text as an empty list."""
    captured_kw: dict[str, Any] = {}

    def mock_translate(
        texts: list[str],
        *a: Any,  # noqa: ANN401
        **kw: Any,  # noqa: ANN401
    ) -> list[str]:
        captured_kw.update(kw)
        return [t.upper() for t in texts]

    with patch("src.core.llm_engine.translate_text", mock_translate):
        translate_batch(["hello"], "FR", "", glossary_entries=[])

    assert "glossary_entries" in captured_kw
    assert captured_kw["glossary_entries"] == []


# ── Batch where all items within one batch are cached ────────────────────────


@pytest.mark.usefixtures("_mock_batch_size")
def test_batch_with_all_items_cached_skips_translate(tmp_path: Path) -> None:
    """Within a single batch, if all items are cached translate_text is not called.

    Scenario: 6 items (2 batches of 3). Items 0,1,2 are all cached.
    Only the second batch (3,4,5) requires translation.
    """
    # Only items in first batch are cached
    cached = {0: "CACHED_A", 1: "CACHED_B", 2: "CACHED_C"}
    translate_calls: list[list[str]] = []

    def mock_translate(
        texts: list[str],
        *a: Any,  # noqa: ANN401
        **kw: Any,  # noqa: ANN401
    ) -> list[str]:
        translate_calls.append(texts)
        return [t.upper() for t in texts]

    with (
        patch("src.core.checkpoint.load_batch_checkpoint", return_value=cached),
        patch("src.core.llm_engine.translate_text", mock_translate),
        patch("src.core.checkpoint.save_batch_progress"),
    ):
        result = translate_batch(
            ["a", "b", "c", "d", "e", "f"],
            "FR",
            "",
            checkpoint_dir=tmp_path,
        )

    # First batch: all cached → translate_text NOT called for items 0-2
    # Second batch: none cached → translate_text called for items 3-5
    assert translate_calls == [["d", "e", "f"]]
    assert result == ["CACHED_A", "CACHED_B", "CACHED_C", "D", "E", "F"]


# ── LLM returns MORE results than uncached items ─────────────────────────────


@pytest.mark.usefixtures("_mock_batch_size")
def test_llm_extra_results_only_maps_expected_count(tmp_path: Path) -> None:
    """When LLM returns more results than uncached items, only expected count is used.

    The result_idx < len(result) guard ensures we never read past the
    uncached_indices boundary, so extra results are silently ignored.
    """
    # Items 0 and 2 are cached; only item 1 is uncached → 1 item sent to LLM
    cached = {0: "CACHED_A", 2: "CACHED_C"}

    def mock_translate(
        texts: list[str],
        *a: Any,  # noqa: ANN401
        **kw: Any,  # noqa: ANN401
    ) -> list[str]:
        # Return 3 results even though only 1 item was sent
        return ["TRANSLATED_B", "EXTRA_1", "EXTRA_2"]

    with (
        patch("src.core.checkpoint.load_batch_checkpoint", return_value=cached),
        patch("src.core.llm_engine.translate_text", mock_translate),
        patch("src.core.checkpoint.save_batch_progress"),
    ):
        result = translate_batch(
            ["a", "b", "c"],
            "FR",
            "",
            checkpoint_dir=tmp_path,
        )

    # Only the first result maps to item 1; extras are ignored
    assert result == ["CACHED_A", "TRANSLATED_B", "CACHED_C"]


# ── Progress is 100 at the end of last batch ─────────────────────────────────


@pytest.mark.usefixtures("_mock_llm", "_mock_batch_size")
def test_progress_ends_at_100() -> None:
    """The final progress callback value is always 100 (last batch at 100%)."""
    progress_values: list[int] = []
    # 4 items, batch_size=3 → 2 batches: end/total = 3/4 = 75%, 4/4 = 100%
    translate_batch(
        ["a", "b", "c", "d"],
        "FR",
        "",
        progress_callback=progress_values.append,
    )
    assert progress_values[-1] == 100  # noqa: PLR2004


# ── content_type parameter is forwarded correctly ─────────────────────────────


@pytest.mark.usefixtures("_mock_batch_size")
def test_custom_content_type_forwarded() -> None:
    """A non-default content_type is forwarded to translate_text."""
    from src.constants.llm import CONTENT_LOCALIZATION  # noqa: PLC0415

    captured_kw: dict[str, Any] = {}

    def mock_translate(
        texts: list[str],
        *a: Any,  # noqa: ANN401
        **kw: Any,  # noqa: ANN401
    ) -> list[str]:
        captured_kw.update(kw)
        return [t.upper() for t in texts]

    with patch("src.core.llm_engine.translate_text", mock_translate):
        translate_batch(
            ["hello"],
            "FR",
            "",
            content_type=CONTENT_LOCALIZATION,
        )

    assert captured_kw["content_type"] == CONTENT_LOCALIZATION


# ── provider/model thread-through ──────────────────────────────────────────


def test_translate_batch_propagates_provider_and_model_to_each_call(
    tmp_path,
) -> None:
    """``translate_batch(..., provider=, model=)`` must reach every per-batch call.

    AGENTS.md: "every output path (PDF, Office, EPUB, text, MCP)
    must thread these kwargs through; dropping them silently routes
    to the global default model."  This test pins the contract by
    capturing every ``translate_text`` invocation and asserting the
    resolved (provider, model) pair shows up in each one.
    """
    from unittest.mock import patch  # noqa: PLC0415

    from src.core.llm_engine import translate_batch  # noqa: PLC0415

    # Build enough strings to span 2-3 batches so we verify the
    # threading happens for *every* batch, not just the first.
    values = [f"text-{i}" for i in range(50)]

    captured: list[dict] = []

    def _fake_translate_text(
        texts, target_lang, src_lang="", **kwargs,
    ):  # noqa: ANN001, ANN003, ANN202, ARG001
        captured.append({
            "provider": kwargs.get("provider"),
            "model": kwargs.get("model"),
            "n_texts": len(texts),
        })
        return [f"[{t}]" for t in texts]

    with patch(
        "src.core.llm_engine.translate_text",
        side_effect=_fake_translate_text,
    ):
        result = translate_batch(
            values,
            "French",
            "English",
            checkpoint_dir=None,
            provider="Custom",
            model="azure/gpt-5.2-chat",
        )

    assert result is not None
    assert captured, "translate_text was never called"
    # Every per-batch call must carry the user-pinned provider+model.
    for call in captured:
        assert call["provider"] == "Custom", (
            f"provider missing/wrong in batch call: {call}"
        )
        assert call["model"] == "azure/gpt-5.2-chat", (
            f"model missing/wrong in batch call: {call}"
        )


def test_translate_batch_passes_none_when_no_provider_model_set() -> None:
    """When the caller doesn't override, ``provider``/``model`` stay None.

    The engine then falls back to whatever ``load_setting`` resolves
    for the global default — same behaviour as before the per-feature
    model setting was added.
    """
    from unittest.mock import patch  # noqa: PLC0415

    from src.core.llm_engine import translate_batch  # noqa: PLC0415

    captured_kwargs: dict = {}

    def _fake_translate_text(
        texts, target_lang, src_lang="", **kwargs,
    ):  # noqa: ANN001, ANN003, ANN202, ARG001
        captured_kwargs.update(kwargs)
        return [f"[{t}]" for t in texts]

    with patch(
        "src.core.llm_engine.translate_text",
        side_effect=_fake_translate_text,
    ):
        translate_batch(
            ["hello", "world"],
            "French",
            "English",
            checkpoint_dir=None,
        )

    assert captured_kwargs.get("provider") is None
    assert captured_kwargs.get("model") is None
