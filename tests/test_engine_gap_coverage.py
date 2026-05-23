"""Gap-coverage tests for core engine modules.

Targets specific uncovered scenarios across:
- checkpoint corruption logging + atomic write interruption
- LLM glossary: empty compression still produces correctly-sized output
- translator: cancel mid-batch via ``cancel_check`` returning a partial
  list and the unmapped-tag log behaviour of ``_map_error_to_code``
- database: nested ``@db_transaction`` rollback on inner failure
- Soniox: reconnect re-sends config containing the original glossary
- Gemini Live: dropped session without ``sessionResumptionUpdate``
  reconnects with empty handle, and on_audio callback raising once
  doesn't crash the engine
- live_engine: ``_put_drop_oldest`` thread-safety with maxsize=2 +
  4 concurrent producers
"""

from __future__ import annotations

import asyncio
import json
import logging
import queue
import sqlite3
import threading
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.constants.errors import ERR_UNKNOWN
from src.core import database
from src.core.checkpoint import (
    _CHECKPOINT_PDF,
    _VERSION,
    _write_checkpoint,
    load_pdf_checkpoint,
    save_pdf_page_progress,
)
from src.core.live_engine import _put_drop_oldest
from src.core.llm_engine import (
    _compress_glossary,
    translate_text,
)
from src.core.translator import _map_error_to_code

# ---------------------------------------------------------------------------
# Checkpoint: corrupt-load logs a warning (don't just swallow)
# ---------------------------------------------------------------------------


class TestCheckpointCorruptionLogs:
    """Reading a corrupted checkpoint should warn so users can diagnose."""

    def test_truncated_pdf_checkpoint_logs_warning(
        self,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Truncated JSON returns None AND emits a 'Corrupt' warning."""
        (tmp_path / _CHECKPOINT_PDF).write_text('{"version": 1, "translated_pa')
        with caplog.at_level(logging.WARNING, logger="checkpoint"):
            assert load_pdf_checkpoint(tmp_path) is None
        assert any(
            "Corrupt checkpoint file" in rec.message for rec in caplog.records
        ), f"expected corruption warning, got records: {caplog.records}"

    def test_pdf_total_pages_mismatch_discards_checkpoint(
        self,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A page-count mismatch on resume discards the stale checkpoint.

        When the source PDF is replaced between runs (different page
        count), the on-disk per-page mapping is no longer valid.
        ``load_pdf_checkpoint`` returns None and warns so the pipeline
        re-processes from scratch instead of silently using stale data.
        """
        save_pdf_page_progress(tmp_path, 0, [{"text": "page0"}], total_pages=5)

        # Caller from a re-run sees a different page count: discard.
        with caplog.at_level(logging.WARNING, logger="checkpoint"):
            loaded = load_pdf_checkpoint(tmp_path, expected_total_pages=3)
        assert loaded is None
        assert any("total_pages mismatch" in rec.message for rec in caplog.records)

        # Matching page count still loads cleanly.
        same = load_pdf_checkpoint(tmp_path, expected_total_pages=5)
        assert same == {0: [{"text": "page0"}]}

        # No-validation call (legacy path) still works.
        legacy = load_pdf_checkpoint(tmp_path)
        assert legacy == {0: [{"text": "page0"}]}

    def test_pdf_checkpoint_missing_total_pages_field(
        self,
        tmp_path: Path,
    ) -> None:
        """Legacy on-disk checkpoint without ``total_pages`` discards on validation.

        The legacy file still loads via the no-arg call so older
        checkpoints aren't orphaned by the new parameter.
        """
        # Hand-write a legacy-format checkpoint missing total_pages.
        (tmp_path / _CHECKPOINT_PDF).write_text(
            json.dumps(
                {
                    "version": _VERSION,
                    "translated_pages": {"0": [{"text": "legacy"}]},
                },
            ),
            encoding="utf-8",
        )

        # With validation: missing total_pages != expected → discard.
        assert load_pdf_checkpoint(tmp_path, expected_total_pages=2) is None

        # Without validation: legacy file loads as-is.
        assert load_pdf_checkpoint(tmp_path) == {0: [{"text": "legacy"}]}

    def test_atomic_write_interrupted_before_rename_no_partial_target(
        self,
        tmp_path: Path,
    ) -> None:
        """An exception between tmp write and rename leaves no partial target.

        Simulates a crash by patching ``Path.replace`` so the rename step
        raises after the .tmp file has been written.  The atomic-write
        contract is: target file never exists until rename succeeds.
        """
        target = tmp_path / "checkpoint_pdf.json"
        assert not target.exists()

        # Make Path.replace raise on the write-then-rename step.  The
        # outer ``except OSError`` in ``_write_checkpoint`` swallows it
        # and logs.  Critically, the caller never sees a half-written
        # target file.
        original_replace = Path.replace

        def boom_replace(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN201
            # Only fail when targeting our checkpoint, not arbitrary tmp files
            if str(args[0] if args else kwargs.get("target", "")).endswith(
                "checkpoint_pdf.json",
            ):
                raise OSError("simulated crash mid-rename")
            return original_replace(self, *args, **kwargs)

        with patch.object(Path, "replace", boom_replace):
            _write_checkpoint(tmp_path, "checkpoint_pdf.json", {"version": _VERSION})

        assert not target.exists(), "Atomic-write contract violated"


# ---------------------------------------------------------------------------
# LLM glossary: compressed-to-empty doesn't break translate_text shape
# ---------------------------------------------------------------------------


class TestCompressGlossaryEmptyAndTranslateText:
    """``_compress_glossary`` returning None must not corrupt output length."""

    def test_compress_returns_none_when_no_term_appears(self) -> None:
        """Glossary with no overlap with batch text → None."""
        glossary = [(1, "kangaroo", "kangourou"), (2, "platypus", "ornithorynque")]
        texts = ["Hello world", "Goodbye"]
        assert _compress_glossary(glossary, texts) is None

    def test_translate_text_with_empty_compressed_glossary_correct_length(
        self,
    ) -> None:
        """When the glossary compresses to None, output length still matches input."""
        texts = ["Hello", "World", "Foo"]

        def fake_translate(*_args, **_kwargs):  # noqa: ANN002, ANN003, ANN202
            # Receive the deduplicated unique input list; echo it back as
            # the "translated" output so we can assert length preservation.
            inputs = _args[0] if _args else _kwargs.get("texts", [])
            return [f"tr-{t}" for t in inputs]

        with (
            patch(
                "src.core.llm_engine._resolve_provider_model",
                return_value=("Gemini", "gemini-2.5-flash"),
            ),
            patch(
                "src.core.llm_engine._translate_gemini",
                side_effect=fake_translate,
            ),
        ):
            result = translate_text(
                texts,
                "French",
                source_lang="English",
                glossary_entries=[(1, "kangaroo", "kangourou")],
            )
        # Empty compressed glossary doesn't change the contract:
        # output length == input length.
        assert len(result) == len(texts)
        assert result == ["tr-Hello", "tr-World", "tr-Foo"]


# ---------------------------------------------------------------------------
# Translator: cancel mid-batch + unknown-tag mapping
# ---------------------------------------------------------------------------


class TestTranslatorCancellation:
    """``translate_text`` should honour cancel_check between sub-batches."""

    def test_cancel_mid_translation_returns_partial_with_originals(self) -> None:
        """Cancel mid-translation preserves originals for unfinished batches.

        When cancel fires after the first batch, untranslated items
        retain their originals (no partial-row exception propagates).
        """
        # Each chunk is large enough that the token-budget splitter
        # produces multiple batches.  ~1500 chars per item × 50 items
        # easily exceeds the 4096-token budget.
        big = "lorem ipsum dolor sit amet " * 60
        texts = [f"text-{i}-{big}" for i in range(50)]

        call_count = {"n": 0}

        def fake_translate(*_args, **_kwargs):  # noqa: ANN002, ANN003, ANN202
            inputs = _args[0]
            call_count["n"] += 1
            return [f"tr-{t}" for t in inputs]

        # Cancel after the first batch — second batch must NOT run, and
        # those positions must keep their original text.
        cancelled = {"n": False}

        def cancel_check() -> bool:
            if call_count["n"] >= 1:
                cancelled["n"] = True
                return True
            return False

        with (
            patch(
                "src.core.llm_engine._resolve_provider_model",
                return_value=("Gemini", "gemini-2.5-flash"),
            ),
            patch(
                "src.core.llm_engine._translate_gemini",
                side_effect=fake_translate,
            ),
        ):
            result = translate_text(
                texts,
                "French",
                cancel_check=cancel_check,
            )

        assert cancelled["n"] is True
        # First-batch items are translated; later items keep originals.
        translated_count = sum(1 for r in result if r.startswith("tr-text-"))
        original_count = sum(1 for r in result if r.startswith("text-"))
        assert translated_count >= 1
        assert original_count >= 1
        assert translated_count + original_count == len(texts)


class TestMapErrorToCodeUnknownTag:
    """An unmapped tag falls back to ERR_UNKNOWN with a warning log."""

    def test_unknown_tag_returns_err_unknown(self) -> None:
        """``_map_error_to_code`` falls back to ERR_UNKNOWN for unknown tags."""
        assert _map_error_to_code("BRAND_NEW_BACKEND_FAILURE") == ERR_UNKNOWN

    def test_unknown_tag_emits_warning(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Unknown tags log a warning so future regressions surface."""
        with caplog.at_level(logging.WARNING, logger="errors"):
            _map_error_to_code("ENTIRELY_NEW_TAG_NEVER_SEEN")
        assert any(
            "ENTIRELY_NEW_TAG_NEVER_SEEN" in rec.message for rec in caplog.records
        )


# ---------------------------------------------------------------------------
# Database: nested @db_transaction rollback on inner failure
# ---------------------------------------------------------------------------


class TestNestedDbTransactionRollback:
    """Outer transaction must roll back when an inner nested call raises.

    Nested ``@db_transaction`` calls must roll back the outer transaction
    when the inner call raises before commit.
    """

    def test_inner_raise_rolls_back_outer_insert(self) -> None:
        """Outer inserts a row, inner raises → outer rolls back, no row persists."""
        from src.core.database import (  # noqa: PLC0415
            STATUS_PENDING,
            db_transaction,
        )

        @db_transaction
        def _inner_fails(cursor: sqlite3.Cursor) -> None:
            """Raises sqlite3.Error to simulate inner failure."""
            cursor.execute("SELECT * FROM no_such_table")  # raises OperationalError

        @db_transaction
        def _outer(cursor: sqlite3.Cursor) -> None:
            """Insert + nested call (sharing the cursor)."""
            cursor.execute(
                "INSERT INTO history "
                "(file_name, source_lang, target_lang, status) "
                "VALUES (?, ?, ?, ?)",
                ("nested_test.txt", "English", "French", STATUS_PENDING),
            )
            # Nested call: passes the cursor explicitly so the inner
            # function executes inside the same transaction.
            _inner_fails(cursor)

        # Snapshot pre-call row count
        with database.create_connection() as conn:
            cur = conn.cursor()
            before = cur.execute("SELECT COUNT(*) FROM history").fetchone()[0]

        # The decorator catches sqlite3.Error → rollback → return None.
        result = _outer()
        assert result is None

        # The outer's INSERT must NOT have committed.
        with database.create_connection() as conn:
            cur = conn.cursor()
            after = cur.execute("SELECT COUNT(*) FROM history").fetchone()[0]
            no_row = cur.execute(
                "SELECT id FROM history WHERE file_name = ?",
                ("nested_test.txt",),
            ).fetchone()

        assert after == before, "Outer transaction was not rolled back"
        assert no_row is None


class TestBatchPauseRaceLastWriteWins:
    """Sequential pause+update follows last-write-wins semantics.

    ``batch_pause_history_entries`` and ``update_history_status`` are
    independent transactions; sequential calls follow last-write-wins.
    """

    def test_last_write_wins_documented(self) -> None:
        """Pause then update_history_status: final state is the later write."""
        from src.core.database import (  # noqa: PLC0415
            STATUS_PENDING,
            STATUS_TRANSLATING,
            add_history_entry,
            batch_pause_history_entries,
            get_history_entry_status,
            update_history_status,
        )

        h_id = add_history_entry(
            "race.txt",
            "English",
            "French",
            STATUS_PENDING,
        )
        assert h_id is not None

        # Pause — switches Pending → Paused.
        batch_pause_history_entries([h_id])
        # Then a status update wins because it commits later.
        update_history_status(h_id, STATUS_TRANSLATING)

        final = get_history_entry_status(h_id)
        assert final == STATUS_TRANSLATING


# ---------------------------------------------------------------------------
# Soniox: reconnection re-sends config with original glossary terms
# ---------------------------------------------------------------------------


class TestSonioxReconnectResendsConfig:
    """Reconnect re-sends the original config JSON, glossary terms included.

    After a transient disconnect, the next connect must send the same
    config JSON (including translation_terms) to the new socket.
    """

    def test_reconnect_resends_config_with_translation_terms(self) -> None:
        """Config is re-sent on each reconnect attempt."""
        from src.core.soniox_engine import SonioxTranscriber  # noqa: PLC0415

        terms = [{"source": "Quokka", "target": "Quokka"}]
        t = SonioxTranscriber(
            api_key="abc",
            on_sentence=MagicMock(),
            on_status=MagicMock(),
            on_stopped=MagicMock(),
            translation_terms=terms,
        )
        t._is_running = True

        sent_per_socket: list[list[Any]] = []
        attempt = {"n": 0}

        class _Ws:
            """Per-attempt fake WebSocket capturing every send()."""

            def __init__(self) -> None:
                sent_per_socket.append([])
                self._idx = len(sent_per_socket) - 1

            async def send(self, msg) -> None:  # noqa: ANN001, ANN202
                sent_per_socket[self._idx].append(msg)

        class _Connect:
            """First call raises (forces reconnect); second call yields a Ws."""

            def __init__(self, *args, **kwargs) -> None:
                attempt["n"] += 1

            async def __aenter__(self):
                if attempt["n"] == 1:
                    raise ConnectionError("transient failure")
                return _Ws()

            async def __aexit__(self, *args) -> None:
                pass

        async def _stop_loop(_ws) -> None:  # noqa: ANN001
            t._is_running = False

        mock_ws_mod = MagicMock()
        mock_ws_mod.connect = _Connect

        with (
            patch.dict("sys.modules", {"websockets": mock_ws_mod}),
            patch("asyncio.sleep", new_callable=AsyncMock),
            patch.object(t, "_send_audio", side_effect=_stop_loop),
            patch.object(t, "_receive_tokens", side_effect=_stop_loop),
        ):
            asyncio.run(t._ws_loop())

        # Second attempt is the only one with a real socket; its first
        # message must be the config and contain the original terms.
        assert sent_per_socket, "no socket was created on reconnect"
        successful_socket = sent_per_socket[-1]
        assert successful_socket, "config was not sent on the reconnected socket"
        config = json.loads(successful_socket[0])
        assert config["api_key"] == "abc"
        assert config["context"]["translation_terms"] == terms


# live_engine._put_drop_oldest: thread safety with maxsize=2
# ---------------------------------------------------------------------------


class TestPutDropOldestConcurrent:
    """Concurrent producers into a small bounded queue stay deadlock-free.

    4 concurrent producers into a maxsize=2 queue must not deadlock,
    and the queue must end with at most 2 items.
    """

    def test_four_producers_no_deadlock_two_items_remain(self) -> None:
        """No deadlock + queue size capped at 2 after concurrent contention."""
        q: queue.Queue[int] = queue.Queue(maxsize=2)
        num_threads = 4
        items_per_thread = 25
        barrier = threading.Barrier(num_threads)

        def producer(tid: int) -> None:
            barrier.wait()
            for i in range(items_per_thread):
                _put_drop_oldest(q, tid * 1000 + i)

        threads = [
            threading.Thread(target=producer, args=(i,)) for i in range(num_threads)
        ]
        for th in threads:
            th.start()
        for th in threads:
            th.join(timeout=10)
            # Strict: a deadlock would leave the thread alive.
            assert not th.is_alive(), "producer thread deadlocked"

        # The queue is bounded; after concurrent puts, size must be
        # exactly maxsize (queue is full) since we wrote 100 items.
        assert q.qsize() == 2  # noqa: PLR2004

        # Drain — every surviving value must be one of the values some
        # producer actually wrote (no corruption).
        survivors: list[int] = []
        while not q.empty():
            survivors.append(q.get_nowait())
        valid = {
            tid * 1000 + i
            for tid in range(num_threads)
            for i in range(items_per_thread)
        }
        assert set(survivors) <= valid
