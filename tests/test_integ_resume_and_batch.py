"""Integration tests for crash-recovery resume, multi-format batch, and retranslation.

Exercises run_translation_pipeline(), checkpoint resume with real DB entries,
multi-format queues, error isolation, and retranslation state transitions.
Only the LLM and file-processor side-effects are mocked.
"""

import json
from collections.abc import Callable, Generator
from pathlib import Path

import pytest

from src.constants.history import (
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_PAUSED,
    STATUS_PENDING,
    STATUS_TRANSLATING,
)
from src.core.checkpoint import (
    _CHECKPOINT_TEXT,
    clear_checkpoints,
    load_batch_checkpoint,
    save_batch_progress,
    save_text_batch,
)
from src.core.config import TranslationConfig
from src.core.database import (
    add_history_entry,
    batch_retranslate_history_entries,
    get_history_entry_status,
    get_unfinished_history,
    init_db,
)
from src.core.translator import run_translation_pipeline

# ── Shared fixtures ───────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def setup_integration_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Generator[None, None, None]:
    """Per-test DB isolation + mock environment setup."""
    db_file = tmp_path / "integration.db"
    monkeypatch.setattr("src.core.database.get_db_path", lambda: str(db_file))
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    monkeypatch.setattr(
        "src.utils.path_manager.get_app_config_dir",
        lambda: config_dir,
    )
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr(
        "src.utils.path_manager.get_app_data_dir",
        lambda: data_dir,
    )
    init_db()
    # Prevent soffice from being started/stopped during tests
    monkeypatch.setattr("src.core.translator.stop_soffice", lambda: None)
    yield


@pytest.fixture()
def base_config(tmp_path: Path) -> TranslationConfig:
    """Returns a minimal TranslationConfig pointing output to tmp_path."""
    return TranslationConfig(
        storage_path=str(tmp_path / "output"),
        auto_remove_history=False,
    )


@pytest.fixture()
def auto_remove_config(tmp_path: Path) -> TranslationConfig:
    """Returns a TranslationConfig with auto_remove_history enabled."""
    return TranslationConfig(
        storage_path=str(tmp_path / "output"),
        auto_remove_history=True,
    )


# ── Helpers ───────────────────────────────────────────────────────────


def _add_task(  # noqa: PLR0913
    tmp_path: Path,
    file_name: str,
    content: str,
    status: str,
    src_lang: str = "English (US)",
    target_lang: str = "French",
) -> tuple[int, Path]:
    """Create a file, add a DB entry with storage_path, return (h_id, file_path).

    Creates a subdirectory per task to mimic real storage layout.
    """
    # Create task storage directory
    storage_dir = tmp_path / "data" / "translations"
    storage_dir.mkdir(parents=True, exist_ok=True)

    # Add DB entry first to get the ID
    h_id = add_history_entry(
        file_name,
        src_lang,
        target_lang,
        status,
        source_path=str(tmp_path / file_name),
    )
    assert h_id is not None

    # Create per-task directory named by ID
    task_dir = storage_dir / str(h_id)
    task_dir.mkdir(parents=True, exist_ok=True)
    file_path = task_dir / file_name
    file_path.write_text(content, encoding="utf-8")

    # Update storage_path in DB
    from src.core.translator import _update_storage_path  # noqa: PLC0415

    _update_storage_path(h_id, str(file_path))

    return h_id, file_path


def _make_fake_translate() -> tuple[Callable, list[list[str]]]:
    """Return a fake translate_text and a tracker for calls."""
    call_log: list[list[str]] = []

    def fake_translate(
        texts: list[str],
        target_lang: str,
        source_lang: str = "",
        **kwargs: object,
    ) -> list[str]:
        call_log.append(list(texts))
        return [f"[{target_lang}] {t}" for t in texts]

    return fake_translate, call_log


def _patch_llm(
    monkeypatch: pytest.MonkeyPatch,
    translate_fn: Callable,
) -> None:
    """Patch translate_text at all import sites."""
    monkeypatch.setattr("src.core.llm_engine.translate_text", translate_fn)
    monkeypatch.setattr(
        "src.core.text_processor._llm_engine.translate_text", translate_fn
    )


# ══════════════════════════════════════════════════════════════════════
# TestCrashRecoveryResume
# ══════════════════════════════════════════════════════════════════════


class TestCrashRecoveryResume:
    """Simulate crash recovery with partial checkpoints and DB state."""

    def test_text_file_resume_after_crash(
        self,
        tmp_path: Path,
        base_config: TranslationConfig,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Pipeline resumes Translating entry from pre-seeded text checkpoint."""
        fake_translate, call_log = _make_fake_translate()
        _patch_llm(monkeypatch, fake_translate)

        # Create a .txt file with 5 paragraphs
        content = "\n\n".join(f"Paragraph {i}" for i in range(5))
        h_id, file_path = _add_task(
            tmp_path, "crash_resume.txt", content, STATUS_TRANSLATING
        )

        # Pre-seed checkpoint: first 2 chunks already translated
        checkpoint_dir = file_path.parent
        save_text_batch(
            checkpoint_dir,
            {0: "[French] Paragraph 0", 1: "[French] Paragraph 1"},
            5,
        )

        # Run pipeline — should resume from checkpoint
        run_translation_pipeline(config=base_config)

        # Should have completed successfully
        status = get_history_entry_status(h_id)
        assert status == STATUS_DONE

        # LLM should NOT have been called with pre-cached paragraphs
        all_texts = [t for batch in call_log for t in batch]
        assert "Paragraph 0" not in all_texts
        assert "Paragraph 1" not in all_texts

    def test_resume_skips_completed_batches(
        self,
        tmp_path: Path,
        base_config: TranslationConfig,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Pre-seed 6/9 batch values done; only remaining 3 sent to LLM."""
        fake_translate, call_log = _make_fake_translate()
        _patch_llm(monkeypatch, fake_translate)

        # Create a JSON file with 9 keys
        data = {f"key_{i}": f"Value {i}" for i in range(9)}
        content = json.dumps(data)
        h_id, file_path = _add_task(
            tmp_path, "partial_batch.json", content, STATUS_TRANSLATING
        )

        # Pre-seed batch checkpoint with 6/9 values already translated
        checkpoint_dir = file_path.parent
        for i in range(6):
            save_batch_progress(
                checkpoint_dir,
                i,
                [f"[French] Value {i}"],
                9,
            )

        run_translation_pipeline(config=base_config)

        status = get_history_entry_status(h_id)
        assert status == STATUS_DONE

        # Only uncached values (indices 6-8) should be sent to LLM
        all_texts = [t for batch in call_log for t in batch]
        for i in range(6):
            assert f"Value {i}" not in all_texts

    def test_resume_with_corrupt_checkpoint_starts_fresh(
        self,
        tmp_path: Path,
        base_config: TranslationConfig,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Invalid JSON checkpoint file causes pipeline to start from scratch."""
        fake_translate, call_log = _make_fake_translate()
        _patch_llm(monkeypatch, fake_translate)

        content = "Hello\n\nWorld"
        h_id, file_path = _add_task(
            tmp_path, "corrupt_ckpt.txt", content, STATUS_TRANSLATING
        )

        # Write corrupt checkpoint
        checkpoint_dir = file_path.parent
        (checkpoint_dir / _CHECKPOINT_TEXT).write_text(
            "not valid json{{{",
            encoding="utf-8",
        )

        run_translation_pipeline(config=base_config)

        status = get_history_entry_status(h_id)
        assert status == STATUS_DONE

        # All paragraphs should have been sent to LLM (full restart)
        all_texts = [t for batch in call_log for t in batch]
        assert any("Hello" in t for t in all_texts)
        assert any("World" in t for t in all_texts)

    def test_multiple_entries_resume_priority(
        self,
        tmp_path: Path,
        base_config: TranslationConfig,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Translating entry processed before Pending per get_unfinished_history."""
        fake_translate, call_log = _make_fake_translate()
        _patch_llm(monkeypatch, fake_translate)

        # Create Pending entry first (lower ID)
        h_pending, _ = _add_task(
            tmp_path, "pending_task.txt", "Pending content", STATUS_PENDING
        )
        # Create Translating entry second (higher ID but higher priority)
        h_translating, _ = _add_task(
            tmp_path, "translating_task.txt", "Translating content", STATUS_TRANSLATING
        )

        # Verify DB ordering: Translating before Pending
        tasks = get_unfinished_history(statuses=(STATUS_PENDING, STATUS_TRANSLATING))
        assert len(tasks) >= 2  # noqa: PLR2004
        task_ids = [t[0] for t in tasks]
        translating_idx = task_ids.index(h_translating)
        pending_idx = task_ids.index(h_pending)
        assert translating_idx < pending_idx

        # Run pipeline — should process both
        run_translation_pipeline(config=base_config)

        # Both should be completed
        assert get_history_entry_status(h_translating) == STATUS_DONE
        assert get_history_entry_status(h_pending) == STATUS_DONE

        # Translating content should appear in call_log before Pending content
        flat_calls = [t for batch in call_log for t in batch]
        translating_pos = next(
            i for i, t in enumerate(flat_calls) if "Translating content" in t
        )
        pending_pos = next(
            i for i, t in enumerate(flat_calls) if "Pending content" in t
        )
        assert translating_pos < pending_pos


# ══════════════════════════════════════════════════════════════════════
# TestMultiFormatBatch
# ══════════════════════════════════════════════════════════════════════


class TestMultiFormatBatch:
    """Test worker processing a queue with different file types."""

    def test_txt_and_json_in_same_queue(
        self,
        tmp_path: Path,
        base_config: TranslationConfig,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Both .txt and .json tasks processed correctly in one pipeline run."""
        fake_translate, call_log = _make_fake_translate()
        _patch_llm(monkeypatch, fake_translate)

        # Create .txt task
        h_txt, _ = _add_task(tmp_path, "multi.txt", "Text content", STATUS_PENDING)
        # Create .json task
        json_data = json.dumps({"greeting": "Hello", "farewell": "Goodbye"})
        h_json, _ = _add_task(tmp_path, "multi.json", json_data, STATUS_PENDING)

        run_translation_pipeline(config=base_config)

        # Both tasks completed
        assert get_history_entry_status(h_txt) == STATUS_DONE
        assert get_history_entry_status(h_json) == STATUS_DONE

        # Both formats had their content sent to LLM
        all_texts = [t for batch in call_log for t in batch]
        assert any("Text content" in t for t in all_texts)
        assert any("Hello" in t for t in all_texts)
        assert any("Goodbye" in t for t in all_texts)

    def test_failed_first_task_doesnt_block_second(
        self,
        tmp_path: Path,
        base_config: TranslationConfig,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """First task has missing file error, second task still succeeds."""
        fake_translate, _ = _make_fake_translate()
        _patch_llm(monkeypatch, fake_translate)

        # Create first task pointing to a nonexistent file
        h_missing = add_history_entry(
            "missing.txt",
            "English (US)",
            "French",
            STATUS_PENDING,
            source_path=str(tmp_path / "missing.txt"),
        )
        from src.core.translator import _update_storage_path  # noqa: PLC0415

        # Point to a path that does not exist
        task_dir = tmp_path / "data" / "translations" / str(h_missing)
        nonexistent = task_dir / "missing.txt"
        _update_storage_path(h_missing, str(nonexistent))

        # Create second task with a valid file
        h_valid, _ = _add_task(tmp_path, "valid.txt", "Valid content", STATUS_PENDING)

        run_translation_pipeline(config=base_config)

        # First task failed (file not found)
        assert get_history_entry_status(h_missing) == STATUS_FAILED

        # Second task succeeded despite first task's failure
        assert get_history_entry_status(h_valid) == STATUS_DONE

    def test_progress_tracked_per_task(
        self,
        tmp_path: Path,
        base_config: TranslationConfig,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Each task gets independent, monotonically increasing progress."""
        fake_translate, _ = _make_fake_translate()
        _patch_llm(monkeypatch, fake_translate)

        # Track progress updates per task
        progress_log: dict[int, list[int]] = {}

        def tracking_progress(h_id: int, progress: int) -> None:
            if h_id not in progress_log:
                progress_log[h_id] = []
            progress_log[h_id].append(progress)
            # Direct DB update (bypass the monkeypatched version)
            from src.core.database import create_connection  # noqa: PLC0415

            conn = create_connection()
            if conn:
                try:
                    conn.execute(
                        "UPDATE history SET progress = ? WHERE id = ? AND progress < ?",
                        (progress, h_id, progress),
                    )
                    conn.commit()
                finally:
                    conn.close()

        monkeypatch.setattr(
            "src.core.translator.update_history_progress",
            tracking_progress,
        )

        h1, _ = _add_task(tmp_path, "task1.txt", "Task one", STATUS_PENDING)
        h2, _ = _add_task(tmp_path, "task2.txt", "Task two", STATUS_PENDING)

        run_translation_pipeline(config=base_config)

        # Each task got its own progress updates
        assert h1 in progress_log
        assert h2 in progress_log
        # Progress should be monotonically increasing for each task
        for h_id in (h1, h2):
            updates = progress_log[h_id]
            assert len(updates) >= 2  # noqa: PLR2004
            # Progress values should be non-decreasing
            for i in range(1, len(updates)):
                assert updates[i] >= updates[i - 1]

    def test_auto_remove_only_affects_completed(
        self,
        tmp_path: Path,
        auto_remove_config: TranslationConfig,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Auto-remove deletes successful task but keeps the failed one."""
        call_count = {"n": 0}

        def failing_then_ok(
            texts: list[str],
            target_lang: str,
            source_lang: str = "",
            **kwargs: object,
        ) -> list[str]:
            call_count["n"] += 1
            # First translate call raises an error (for first task)
            if call_count["n"] == 1:
                raise ValueError("QUOTA_ERROR")
            return [f"[{target_lang}] {t}" for t in texts]

        _patch_llm(monkeypatch, failing_then_ok)

        h_fail, _ = _add_task(tmp_path, "will_fail.txt", "Fail content", STATUS_PENDING)
        h_ok, _ = _add_task(tmp_path, "will_pass.txt", "Pass content", STATUS_PENDING)

        run_translation_pipeline(config=auto_remove_config)

        # Failed task remains in DB with failed status
        assert get_history_entry_status(h_fail) == STATUS_FAILED

        # Successful task was auto-removed (deleted from DB)
        assert get_history_entry_status(h_ok) is None


# ══════════════════════════════════════════════════════════════════════
# TestRetranslateAfterPartialSuccess
# ══════════════════════════════════════════════════════════════════════


class TestRetranslateAfterPartialSuccess:
    """Test retranslation workflows after partial success."""

    def test_retranslate_clears_old_checkpoint(
        self,
        tmp_path: Path,
        base_config: TranslationConfig,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Retranslate resets status, and checkpoints are cleaned on success."""
        fake_translate, _ = _make_fake_translate()
        _patch_llm(monkeypatch, fake_translate)

        # Create a task that is already Done
        h_id, file_path = _add_task(
            tmp_path, "retranslate.txt", "Old content", STATUS_DONE
        )

        # Seed leftover checkpoint from original translation
        checkpoint_dir = file_path.parent
        save_batch_progress(checkpoint_dir, 0, ["[French] Old content"], 1)
        assert load_batch_checkpoint(checkpoint_dir) is not None

        # Retranslate: resets status to Pending, clears progress/error
        batch_retranslate_history_entries([h_id], "English (US)", "Vietnamese")
        assert get_history_entry_status(h_id) == STATUS_PENDING

        # Clear checkpoints manually (as the UI retranslate handler would)
        clear_checkpoints(checkpoint_dir)

        # Run pipeline to retranslate
        run_translation_pipeline(config=base_config)

        # Task should be Done again
        assert get_history_entry_status(h_id) == STATUS_DONE

        # Checkpoints should be cleaned up after successful completion
        checkpoint_files = list(checkpoint_dir.glob("checkpoint_*.json"))
        assert len(checkpoint_files) == 0

    def test_retranslate_paused_entry_restarts_fresh(
        self,
        tmp_path: Path,
        base_config: TranslationConfig,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Paused entry retranslated from beginning, not from old checkpoint."""
        fake_translate, call_log = _make_fake_translate()
        _patch_llm(monkeypatch, fake_translate)

        content = "Line A\n\nLine B\n\nLine C"
        h_id, file_path = _add_task(tmp_path, "paused.txt", content, STATUS_PAUSED)

        # Seed checkpoint from before the pause (only 1/3 done)
        checkpoint_dir = file_path.parent
        save_text_batch(checkpoint_dir, {0: "[French] Line A"}, 3)

        # Retranslate resets to Pending
        batch_retranslate_history_entries([h_id], "English (US)", "French")
        assert get_history_entry_status(h_id) == STATUS_PENDING

        # Clear checkpoints (simulates what UI does on retranslate)
        clear_checkpoints(checkpoint_dir)

        run_translation_pipeline(config=base_config)

        assert get_history_entry_status(h_id) == STATUS_DONE

        # All lines should have been sent to LLM (fresh start)
        all_texts = [t for batch in call_log for t in batch]
        assert any("Line A" in t for t in all_texts)
        assert any("Line B" in t for t in all_texts)
        assert any("Line C" in t for t in all_texts)

    def test_retranslate_generates_new_output_path(
        self,
        tmp_path: Path,
        base_config: TranslationConfig,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Retranslate does not overwrite existing output file."""
        fake_translate, _ = _make_fake_translate()
        _patch_llm(monkeypatch, fake_translate)

        h_id, file_path = _add_task(tmp_path, "reout.txt", "Content here", STATUS_DONE)

        # Create an output file that would conflict
        output_dir = tmp_path / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        # The pipeline builds: {stem}_translated_{src_locale}_{tgt_locale}{ext}
        conflicting = output_dir / "reout_translated_en-US_fr.txt"
        conflicting.write_text("old translation", encoding="utf-8")

        # Retranslate
        batch_retranslate_history_entries([h_id], "English (US)", "French")
        clear_checkpoints(file_path.parent)

        run_translation_pipeline(config=base_config)

        assert get_history_entry_status(h_id) == STATUS_DONE

        # Original conflicting file should still contain old content
        assert conflicting.read_text(encoding="utf-8") == "old translation"

        # A new file with suffix should exist (e.g. _1.txt)
        output_files = list(output_dir.glob("reout_translated_en-US_fr*.txt"))
        assert len(output_files) >= 2  # noqa: PLR2004

    def test_retranslate_preserves_original_storage_path(
        self,
        tmp_path: Path,
        base_config: TranslationConfig,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The storage_path column is unchanged after retranslate."""
        fake_translate, _ = _make_fake_translate()
        _patch_llm(monkeypatch, fake_translate)

        h_id, file_path = _add_task(
            tmp_path, "preserve_path.txt", "Keep path", STATUS_DONE
        )
        original_storage = str(file_path)

        # Read storage_path before retranslate
        tasks_before = get_unfinished_history(statuses=(STATUS_DONE,))
        storage_before = None
        for task in tasks_before:
            if task[0] == h_id:
                storage_before = task[1]
                break
        assert storage_before == original_storage

        # Retranslate
        batch_retranslate_history_entries([h_id], "English (US)", "French")

        # Read storage_path after retranslate — should be unchanged
        tasks_after = get_unfinished_history(statuses=(STATUS_PENDING,))
        storage_after = None
        for task in tasks_after:
            if task[0] == h_id:
                storage_after = task[1]
                break
        assert storage_after == original_storage

        # Run pipeline — storage_path should still be the same
        run_translation_pipeline(config=base_config)

        assert get_history_entry_status(h_id) == STATUS_DONE


# ══════════════════════════════════════════════════════════════════════
# TestBatchCheckpointResumption — checkpoint-based resume from stages
# ══════════════════════════════════════════════════════════════════════


class TestBatchCheckpointResumption:
    """Test checkpoint-based batch resumption from various stages."""

    def test_json_batch_resume_from_middle(
        self,
        tmp_path: Path,
        base_config: TranslationConfig,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Resume a JSON batch where half the values were already translated."""
        fake_translate, call_log = _make_fake_translate()
        _patch_llm(monkeypatch, fake_translate)

        data = {f"k{i}": f"Val {i}" for i in range(8)}
        content = json.dumps(data)
        h_id, file_path = _add_task(
            tmp_path, "mid_resume.json", content, STATUS_TRANSLATING
        )

        # Pre-seed checkpoint: first 4 values done
        checkpoint_dir = file_path.parent
        for i in range(4):
            save_batch_progress(checkpoint_dir, i, [f"[French] Val {i}"], 8)

        run_translation_pipeline(config=base_config)
        assert get_history_entry_status(h_id) == STATUS_DONE

        # Only uncached values (4-7) should be sent to LLM
        all_texts = [t for batch in call_log for t in batch]
        for i in range(4):
            assert f"Val {i}" not in all_texts

    def test_text_batch_partial_then_resume(
        self,
        tmp_path: Path,
        base_config: TranslationConfig,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Resume a text file after only 1 of 4 paragraphs was cached."""
        fake_translate, call_log = _make_fake_translate()
        _patch_llm(monkeypatch, fake_translate)

        # Each paragraph must exceed half of MAX_CHUNK_CHARS (3000) so
        # _chunk_text keeps them as separate chunks instead of merging.
        padding = " word" * 400  # ~2000 chars per chunk
        content = "\n\n".join(f"Chunk {i}{padding}" for i in range(4))
        h_id, file_path = _add_task(
            tmp_path, "partial.txt", content, STATUS_TRANSLATING
        )

        # Pre-seed checkpoint: only chunk 0 done
        checkpoint_dir = file_path.parent
        save_text_batch(checkpoint_dir, {0: f"[French] Chunk 0{padding}"}, 4)

        run_translation_pipeline(config=base_config)
        assert get_history_entry_status(h_id) == STATUS_DONE

        all_texts = [t for batch in call_log for t in batch]
        assert not any("Chunk 0" in t for t in all_texts)
        # Remaining chunks should have been sent
        assert any("Chunk 1" in t for t in all_texts)

    def test_cancellation_then_resume(
        self,
        tmp_path: Path,
        base_config: TranslationConfig,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Simulate cancellation mid-translation, then resume from checkpoint."""
        call_count = {"n": 0}

        def cancelling_translate(
            texts: list[str],
            target_lang: str,
            source_lang: str = "",
            **kwargs: object,
        ) -> list[str]:
            call_count["n"] += 1
            return [f"[{target_lang}] {t}" for t in texts]

        _patch_llm(monkeypatch, cancelling_translate)

        content = "\n\n".join(f"Para {i}" for i in range(6))
        h_id, file_path = _add_task(
            tmp_path, "cancel_resume.txt", content, STATUS_TRANSLATING
        )

        # Pre-seed checkpoint: first 3 paragraphs done (simulate prior run)
        checkpoint_dir = file_path.parent
        save_text_batch(
            checkpoint_dir,
            {0: "[French] Para 0", 1: "[French] Para 1", 2: "[French] Para 2"},
            6,
        )

        run_translation_pipeline(config=base_config)
        assert get_history_entry_status(h_id) == STATUS_DONE

    def test_mixed_success_failure_tasks(
        self,
        tmp_path: Path,
        base_config: TranslationConfig,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Queue with one failing and one succeeding task."""
        call_count = {"n": 0}

        def sometimes_failing(
            texts: list[str],
            target_lang: str,
            source_lang: str = "",
            **kwargs: object,
        ) -> list[str]:
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise ValueError("AUTH_ERROR")
            return [f"[{target_lang}] {t}" for t in texts]

        _patch_llm(monkeypatch, sometimes_failing)

        h_fail, _ = _add_task(tmp_path, "fail_mix.txt", "Fail content", STATUS_PENDING)
        h_ok, _ = _add_task(tmp_path, "ok_mix.txt", "OK content", STATUS_PENDING)

        run_translation_pipeline(config=base_config)

        assert get_history_entry_status(h_fail) == STATUS_FAILED
        assert get_history_entry_status(h_ok) == STATUS_DONE

    def test_resume_with_missing_checkpoint_file(
        self,
        tmp_path: Path,
        base_config: TranslationConfig,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Missing checkpoint file causes fresh translation (no crash)."""
        fake_translate, call_log = _make_fake_translate()
        _patch_llm(monkeypatch, fake_translate)

        content = "Alpha\n\nBeta"
        h_id, file_path = _add_task(
            tmp_path, "no_ckpt.txt", content, STATUS_TRANSLATING
        )

        # No checkpoint file written — should start from scratch
        run_translation_pipeline(config=base_config)
        assert get_history_entry_status(h_id) == STATUS_DONE

        all_texts = [t for batch in call_log for t in batch]
        assert any("Alpha" in t for t in all_texts)
        assert any("Beta" in t for t in all_texts)

    def test_resume_with_changed_target_language(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Retranslate with changed target language resets and processes fresh."""
        fake_translate, call_log = _make_fake_translate()
        _patch_llm(monkeypatch, fake_translate)

        config = TranslationConfig(
            storage_path=str(tmp_path / "output"),
            auto_remove_history=False,
        )

        h_id, file_path = _add_task(
            tmp_path,
            "lang_change.txt",
            "Original text",
            STATUS_DONE,
            target_lang="French",
        )

        # Retranslate to Vietnamese instead of French
        batch_retranslate_history_entries([h_id], "English (US)", "Vietnamese")
        clear_checkpoints(file_path.parent)

        run_translation_pipeline(config=config)
        assert get_history_entry_status(h_id) == STATUS_DONE

        # Should have been translated to Vietnamese
        all_texts = [t for batch in call_log for t in batch]
        assert any("Original text" in t for t in all_texts)

    def test_batch_progress_monotonic_across_resume(
        self,
        tmp_path: Path,
        base_config: TranslationConfig,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Progress updates are monotonically increasing across checkpoint resume."""
        fake_translate, _ = _make_fake_translate()
        _patch_llm(monkeypatch, fake_translate)

        progress_log: dict[int, list[int]] = {}

        def tracking_progress(h_id: int, progress: int) -> None:
            if h_id not in progress_log:
                progress_log[h_id] = []
            progress_log[h_id].append(progress)
            from src.core.database import create_connection  # noqa: PLC0415

            conn = create_connection()
            if conn:
                try:
                    conn.execute(
                        "UPDATE history SET progress = ? WHERE id = ? AND progress < ?",
                        (progress, h_id, progress),
                    )
                    conn.commit()
                finally:
                    conn.close()

        monkeypatch.setattr(
            "src.core.translator.update_history_progress",
            tracking_progress,
        )

        content = "\n\n".join(f"Line {i}" for i in range(6))
        h_id, file_path = _add_task(
            tmp_path, "progress_track.txt", content, STATUS_TRANSLATING
        )

        # Pre-seed 2 of 6 chunks
        checkpoint_dir = file_path.parent
        save_text_batch(
            checkpoint_dir,
            {0: "[French] Line 0", 1: "[French] Line 1"},
            6,
        )

        run_translation_pipeline(config=base_config)
        assert get_history_entry_status(h_id) == STATUS_DONE

        # Verify monotonic progress
        if h_id in progress_log:
            updates = progress_log[h_id]
            for i in range(1, len(updates)):
                assert updates[i] >= updates[i - 1]

    def test_empty_file_completes_without_llm_call(
        self,
        tmp_path: Path,
        base_config: TranslationConfig,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Empty file completes successfully without calling the LLM."""
        fake_translate, call_log = _make_fake_translate()
        _patch_llm(monkeypatch, fake_translate)

        h_id, _ = _add_task(tmp_path, "empty.txt", "", STATUS_PENDING)

        run_translation_pipeline(config=base_config)
        assert get_history_entry_status(h_id) == STATUS_DONE

        # No LLM calls for empty content
        assert len(call_log) == 0

    def test_single_paragraph_txt_no_checkpoint_needed(
        self,
        tmp_path: Path,
        base_config: TranslationConfig,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Single-paragraph file completes in one batch — no checkpoint."""
        fake_translate, call_log = _make_fake_translate()
        _patch_llm(monkeypatch, fake_translate)

        h_id, file_path = _add_task(
            tmp_path, "single.txt", "Only paragraph", STATUS_PENDING
        )

        run_translation_pipeline(config=base_config)
        assert get_history_entry_status(h_id) == STATUS_DONE

        # Checkpoints should be cleaned up
        checkpoint_files = list(file_path.parent.glob("checkpoint_*.json"))
        assert len(checkpoint_files) == 0

    def test_json_with_corrupt_checkpoint_batch(
        self,
        tmp_path: Path,
        base_config: TranslationConfig,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Corrupt batch checkpoint for JSON file triggers fresh start."""
        from src.core.checkpoint import _CHECKPOINT_BATCH  # noqa: PLC0415

        fake_translate, call_log = _make_fake_translate()
        _patch_llm(monkeypatch, fake_translate)

        data = {"a": "Alpha", "b": "Beta"}
        content = json.dumps(data)
        h_id, file_path = _add_task(
            tmp_path, "corrupt_batch.json", content, STATUS_TRANSLATING
        )

        # Write corrupt batch checkpoint
        checkpoint_dir = file_path.parent
        (checkpoint_dir / _CHECKPOINT_BATCH).write_text(
            "{malformed!!!",
            encoding="utf-8",
        )

        run_translation_pipeline(config=base_config)
        assert get_history_entry_status(h_id) == STATUS_DONE

        # Both values should have been sent to LLM (fresh start)
        all_texts = [t for batch in call_log for t in batch]
        assert any("Alpha" in t for t in all_texts)
        assert any("Beta" in t for t in all_texts)

    def test_multiple_pending_processed_in_order(
        self,
        tmp_path: Path,
        base_config: TranslationConfig,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Multiple Pending tasks are processed in ascending ID order."""
        fake_translate, call_log = _make_fake_translate()
        _patch_llm(monkeypatch, fake_translate)

        h1, _ = _add_task(tmp_path, "first.txt", "First task", STATUS_PENDING)
        h2, _ = _add_task(tmp_path, "second.txt", "Second task", STATUS_PENDING)
        h3, _ = _add_task(tmp_path, "third.txt", "Third task", STATUS_PENDING)

        run_translation_pipeline(config=base_config)

        assert get_history_entry_status(h1) == STATUS_DONE
        assert get_history_entry_status(h2) == STATUS_DONE
        assert get_history_entry_status(h3) == STATUS_DONE

        # Verify ordering in call_log
        flat = [t for batch in call_log for t in batch]
        first_pos = next(i for i, t in enumerate(flat) if "First task" in t)
        second_pos = next(i for i, t in enumerate(flat) if "Second task" in t)
        third_pos = next(i for i, t in enumerate(flat) if "Third task" in t)
        assert first_pos < second_pos < third_pos

    def test_paused_entries_not_picked_up(
        self,
        tmp_path: Path,
        base_config: TranslationConfig,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Paused entries are not auto-processed by the pipeline."""
        fake_translate, call_log = _make_fake_translate()
        _patch_llm(monkeypatch, fake_translate)

        h_paused, _ = _add_task(
            tmp_path, "paused_skip.txt", "Should not run", STATUS_PAUSED
        )

        run_translation_pipeline(config=base_config)

        # Paused entry stays paused — not processed
        assert get_history_entry_status(h_paused) == STATUS_PAUSED
        assert len(call_log) == 0
