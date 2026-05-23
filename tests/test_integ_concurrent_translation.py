"""Integration tests for concurrent / queued document translation.

Tests the DB-poll behaviour of run_translation_pipeline():
- A single pipeline call drains every Pending entry sequentially.
- New tasks queued *while* the pipeline is running are picked up by the
  same worker rather than dropped.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Generator
from pathlib import Path

import pytest

from src.constants.history import (
    STATUS_DONE,
    STATUS_PENDING,
)
from src.core.config import TranslationConfig
from src.core.database import (
    get_history,
    get_history_entry_status,
    init_db,
)
from src.core.translator import (
    run_translation_pipeline,
    setup_translation_tasks,
)

# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def setup_integration_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Generator[None, None, None]:
    """Per-test DB isolation + path redirection."""
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
    monkeypatch.setattr("src.core.translator.stop_soffice", lambda: None)
    yield


@pytest.fixture()
def mock_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[..., list[str]]:
    """Mocks translate_text at every import site."""

    def fake_translate(
        texts: list[str],
        target_lang: str,
        source_lang: str = "",
        **kwargs: object,
    ) -> list[str]:
        return [f"[{target_lang}] {t}" for t in texts]

    monkeypatch.setattr("src.core.llm_engine.translate_text", fake_translate)
    monkeypatch.setattr(
        "src.core.text_processor._llm_engine.translate_text",
        fake_translate,
    )
    return fake_translate


# ── Helpers ──────────────────────────────────────────────────────────


def _create_input(tmp_path: Path, name: str, content: str = "Hello world") -> Path:
    """Creates a tiny .txt file outside the storage tree."""
    inp = tmp_path / name
    inp.write_text(content, encoding="utf-8")
    return inp


# ── Tests ────────────────────────────────────────────────────────────


def test_single_pipeline_drains_three_pending_tasks(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """3 Pending entries → one pipeline call processes all three."""
    files = [
        _create_input(tmp_path, "a.txt", "Alpha text"),
        _create_input(tmp_path, "b.txt", "Beta text"),
        _create_input(tmp_path, "c.txt", "Gamma text"),
    ]
    tasks = setup_translation_tasks([str(f) for f in files], "English (US)", "French")
    assert len(tasks) == 3

    output_dir = tmp_path / "output"
    output_dir.mkdir()
    config = TranslationConfig(
        storage_path=str(output_dir),
        auto_remove_history=False,
    )

    run_translation_pipeline(config=config)

    # All 3 entries finished.
    for h_id, *_ in tasks:
        assert get_history_entry_status(h_id) == STATUS_DONE

    # 3 translated files emitted.
    output_files = list(output_dir.rglob("*.txt"))
    assert len(output_files) == 3
    for out in output_files:
        assert "[French]" in out.read_text(encoding="utf-8")


def test_pipeline_picks_up_tasks_queued_mid_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A task queued while the pipeline is running is picked up by the same call.

    Strategy: wrap translate_text with a hook that, the first time it is
    called, queues a *new* task via setup_translation_tasks() in another
    thread.  The pipeline's DB-poll loop should see the new pending row
    after finishing its first task and process it before exiting.
    """
    initial = [
        _create_input(tmp_path, "first.txt", "First file body"),
    ]
    setup_translation_tasks(
        [str(f) for f in initial],
        "English (US)",
        "French",
    )

    queued_ids: list[int] = []
    queued_lock = threading.Lock()
    queued_event = threading.Event()
    call_count = {"n": 0}

    def fake_translate(
        texts: list[str],
        target_lang: str,
        source_lang: str = "",
        **kwargs: object,
    ) -> list[str]:
        call_count["n"] += 1
        # On the first invocation, queue a new task BEFORE returning.
        # We do this from within the worker's own thread; setup_translation_tasks
        # writes the row synchronously so the next get_unfinished_history()
        # poll will see it.
        with queued_lock:
            if not queued_event.is_set():
                queued_event.set()
                new_file = _create_input(
                    tmp_path,
                    "second.txt",
                    "Second file body queued at runtime",
                )
                tasks2 = setup_translation_tasks(
                    [str(new_file)],
                    "English (US)",
                    "French",
                )
                queued_ids.extend(t[0] for t in tasks2)
        return [f"[{target_lang}] {t}" for t in texts]

    monkeypatch.setattr("src.core.llm_engine.translate_text", fake_translate)
    monkeypatch.setattr(
        "src.core.text_processor._llm_engine.translate_text",
        fake_translate,
    )

    output_dir = tmp_path / "output"
    output_dir.mkdir()
    config = TranslationConfig(
        storage_path=str(output_dir),
        auto_remove_history=False,
    )

    run_translation_pipeline(config=config)

    # The queued task was created and processed by the same pipeline call.
    assert queued_event.is_set()
    assert len(queued_ids) == 1
    queued_id = queued_ids[0]

    # Both tasks reached Done.
    assert get_history_entry_status(queued_id) == STATUS_DONE
    history_rows = get_history()
    statuses = {row[0]: row for row in history_rows}  # row[0] is id
    # Every entry in the DB is now Done.
    for row in history_rows:
        # Schema: row[0]=id, row[8]=status (file_name=1, src=2, target=3, ...)
        # Use a robust check via get_history_entry_status to avoid coupling
        # to column order.
        assert get_history_entry_status(row[0]) == STATUS_DONE
    assert len(statuses) == 2

    # 2 translated outputs.
    output_files = list(output_dir.rglob("*.txt"))
    assert len(output_files) == 2


def test_pipeline_stops_on_global_cancellation(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """is_cancelled=True before any task → pipeline returns immediately."""
    inp = _create_input(tmp_path, "skipme.txt")
    tasks = setup_translation_tasks(
        [str(inp)],
        "English (US)",
        "French",
    )
    assert len(tasks) == 1

    output_dir = tmp_path / "output"
    output_dir.mkdir()
    config = TranslationConfig(
        storage_path=str(output_dir),
        auto_remove_history=False,
    )

    run_translation_pipeline(config=config, is_cancelled=lambda: True)

    # Task remains Pending — the pipeline never started it.
    h_id = tasks[0][0]
    assert get_history_entry_status(h_id) == STATUS_PENDING
    assert list(output_dir.rglob("*.txt")) == []


def test_concurrent_setup_translation_tasks_is_thread_safe(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """5 threads each queue 2 tasks; all 10 entries persist with valid storage."""
    barrier = threading.Barrier(5)
    results: list[list[tuple[int, str, str, str]]] = []
    results_lock = threading.Lock()

    def worker(idx: int) -> None:
        files = [
            _create_input(tmp_path, f"t{idx}_a.txt", f"thread {idx} body a"),
            _create_input(tmp_path, f"t{idx}_b.txt", f"thread {idx} body b"),
        ]
        barrier.wait()
        tasks = setup_translation_tasks(
            [str(f) for f in files],
            "English (US)",
            "French",
        )
        with results_lock:
            results.append(tasks)

    threads = [
        threading.Thread(target=worker, args=(i,), daemon=True) for i in range(5)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5.0)
        assert not t.is_alive()

    flat = [task for batch in results for task in batch]
    assert len(flat) == 10
    # Every ID is unique.
    ids = [t[0] for t in flat]
    assert len(set(ids)) == 10
    # Every storage path exists on disk.
    for _h_id, storage_path, *_ in flat:
        assert Path(storage_path).exists(), f"Missing storage file: {storage_path}"


def test_pipeline_skips_missing_storage_file(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """Storage file deleted between setup and pipeline → entry marked Failed."""
    inp = _create_input(tmp_path, "vanish.txt")
    tasks = setup_translation_tasks(
        [str(inp)],
        "English (US)",
        "French",
    )
    h_id, storage_path, *_ = tasks[0]
    # Simulate filesystem corruption: remove the cloned storage file.
    Path(storage_path).unlink()

    output_dir = tmp_path / "output"
    output_dir.mkdir()
    config = TranslationConfig(
        storage_path=str(output_dir),
        auto_remove_history=False,
    )

    run_translation_pipeline(config=config)

    # Pipeline did not crash; entry is no longer Pending.
    status = get_history_entry_status(h_id)
    assert status != STATUS_PENDING
    assert status != STATUS_DONE  # didn't translate a missing file
