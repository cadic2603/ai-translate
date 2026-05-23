"""Integration tests for DB state transitions via TranslationWorker.

Runs TranslationWorker.run() with real DB and verifies status,
progress, and error_code transitions.  Only the LLM is mocked.
"""

from collections.abc import Callable, Generator
from pathlib import Path

import pytest

from src.constants.errors import (
    ERR_FILE_NOT_FOUND,
    ERR_FILE_PASSWORD_PROTECTED,
    ERR_LLM_QUOTA_EXCEEDED,
    ERR_UNKNOWN,
)
from src.core.config import TranslationConfig
from src.core.database import (
    get_history,
    get_history_entry_status,
    init_db,
    update_history_status,
)
from src.core.translator import (
    TranslationWorker,
    resume_unfinished_translations,
    setup_translation_tasks,
)

# Config that preserves history entries after success (for assertions)
_NO_REMOVE = TranslationConfig(auto_remove_history=False)

# ── Shared fixtures ──────────────────────────────────────────────────


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
    monkeypatch.setattr("time.sleep", lambda _: None)
    monkeypatch.setattr("src.core.translator.stop_soffice", lambda: None)
    yield


@pytest.fixture()
def mock_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[..., list[str]]:
    """Patches translate_text at all import sites."""

    def fake_translate(
        texts: list[str],
        target_lang: str,
        source_lang: str = "",
        **kwargs: object,
    ) -> list[str]:
        return [f"[{target_lang}] {t}" for t in texts]

    monkeypatch.setattr(
        "src.core.llm_engine.translate_text",
        fake_translate,
    )
    monkeypatch.setattr(
        "src.core.text_processor._llm_engine.translate_text",
        fake_translate,
    )
    return fake_translate


# ── Helpers ──────────────────────────────────────────────────────────


def _create_txt(
    tmp_path: Path,
    name: str = "test.txt",
    content: str = "Hello world",
) -> str:
    """Create a .txt file and return its path as string."""
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return str(p)


def _run_worker(
    tasks: list[tuple[object, ...]],
    config: TranslationConfig | None = None,
) -> TranslationWorker:
    """Run TranslationWorker synchronously."""
    TranslationWorker._is_any_worker_running = False
    worker = TranslationWorker(tasks, config=config)
    worker.run()
    return worker


def _get_entry(h_id: int) -> tuple[object, ...] | None:
    """Get full history row by id from get_history()."""
    for row in get_history():
        if row[0] == h_id:
            return row
    return None


# ── Success paths ────────────────────────────────────────────────────


def test_pending_to_done(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """Success + auto_remove=False → status='Done', progress=100."""
    file_path = _create_txt(tmp_path)
    tasks = setup_translation_tasks([file_path], "English (US)", "French")
    h_id = tasks[0][0]

    _run_worker(tasks, config=_NO_REMOVE)

    assert get_history_entry_status(h_id) == "Done"
    row = _get_entry(h_id)
    assert row[5] == 100  # noqa: PLR2004  (progress column)


def test_auto_remove_deletes_entry(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """Success + auto_remove=True → entry deleted from DB."""
    file_path = _create_txt(tmp_path)
    tasks = setup_translation_tasks([file_path], "English (US)", "French")
    h_id = tasks[0][0]

    _run_worker(tasks, config=TranslationConfig(auto_remove_history=True))

    assert get_history_entry_status(h_id) is None  # Deleted
    assert len(get_history()) == 0


def test_progress_reaches_100(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """Successful text translation → final progress=100."""
    file_path = _create_txt(tmp_path)
    tasks = setup_translation_tasks([file_path], "English (US)", "French")
    h_id = tasks[0][0]

    _run_worker(tasks, config=_NO_REMOVE)

    row = _get_entry(h_id)
    assert row[5] == 100  # noqa: PLR2004


def test_multiple_queued_tasks(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """3 .txt files → all 3 status='Done'."""
    paths = [_create_txt(tmp_path, f"file{i}.txt", f"Content {i}") for i in range(3)]
    tasks = setup_translation_tasks(paths, "English (US)", "French")
    assert len(tasks) == 3  # noqa: PLR2004

    _run_worker(tasks, config=_NO_REMOVE)

    for h_id, *_ in tasks:
        assert get_history_entry_status(h_id) == "Done"


# ── Failure paths ────────────────────────────────────────────────────


def test_pending_to_failed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM raises QUOTA_ERROR → status='Failed', correct error_code."""

    def quota_error_translate(
        texts: list[str],
        target_lang: str,
        source_lang: str = "",
        **kwargs: object,
    ) -> list[str]:
        raise ValueError("QUOTA_ERROR")

    monkeypatch.setattr(
        "src.core.llm_engine.translate_text",
        quota_error_translate,
    )
    monkeypatch.setattr(
        "src.core.text_processor._llm_engine.translate_text",
        quota_error_translate,
    )

    file_path = _create_txt(tmp_path)
    tasks = setup_translation_tasks([file_path], "English (US)", "French")
    h_id = tasks[0][0]

    _run_worker(tasks)

    assert get_history_entry_status(h_id) == "Failed"
    row = _get_entry(h_id)
    assert row[9] == ERR_LLM_QUOTA_EXCEEDED  # error_code column


def test_file_not_found(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """Storage path points to deleted file → ERR_FILE_NOT_FOUND."""
    file_path = _create_txt(tmp_path)
    tasks = setup_translation_tasks([file_path], "English (US)", "French")
    h_id = tasks[0][0]
    storage_path = tasks[0][1]

    # Delete the cloned file before running
    Path(storage_path).unlink()

    _run_worker(tasks, config=_NO_REMOVE)

    assert get_history_entry_status(h_id) == "Failed"
    row = _get_entry(h_id)
    assert row[9] == ERR_FILE_NOT_FOUND


def test_encrypted_file_detected(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """File with OLE2 magic bytes in .docx → ERR_FILE_PASSWORD_PROTECTED."""
    # Create a .docx that starts with OLE2 magic (encrypted)
    ole2_magic = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
    docx_path = tmp_path / "encrypted.docx"
    docx_path.write_bytes(ole2_magic + b"\x00" * 100)

    tasks = setup_translation_tasks([str(docx_path)], "English (US)", "French")
    h_id = tasks[0][0]

    _run_worker(tasks, config=_NO_REMOVE)

    assert get_history_entry_status(h_id) == "Failed"
    row = _get_entry(h_id)
    assert row[9] == ERR_FILE_PASSWORD_PROTECTED


def test_unsupported_extension(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """.xyz file → ERR_UNKNOWN."""
    xyz = tmp_path / "data.xyz"
    xyz.write_text("unknown format", encoding="utf-8")

    tasks = setup_translation_tasks([str(xyz)], "English (US)", "French")
    h_id = tasks[0][0]

    _run_worker(tasks, config=_NO_REMOVE)

    assert get_history_entry_status(h_id) == "Failed"
    row = _get_entry(h_id)
    assert row[9] == ERR_UNKNOWN


# ── Dynamic behavior ─────────────────────────────────────────────────


def test_worker_polls_db_dynamically(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """Add task B to DB while task A processes → both completed."""
    # Task A
    file_a = _create_txt(tmp_path, "a.txt", "Task A content")
    tasks_a = setup_translation_tasks([file_a], "English (US)", "French")
    h_id_a = tasks_a[0][0]

    # Task B — created directly in DB (simulates queuing during processing)
    file_b = _create_txt(tmp_path, "b.txt", "Task B content")
    tasks_b = setup_translation_tasks([file_b], "English (US)", "French")
    h_id_b = tasks_b[0][0]

    # Worker receives only task A but should discover B from DB polling
    _run_worker(tasks_a, config=_NO_REMOVE)

    assert get_history_entry_status(h_id_a) == "Done"
    assert get_history_entry_status(h_id_b) == "Done"


def test_no_glossary_sets(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """Translate with no glossary sets → succeeds with empty glossary."""
    file_path = _create_txt(tmp_path)
    tasks = setup_translation_tasks([file_path], "English (US)", "French")
    h_id = tasks[0][0]

    _run_worker(tasks, config=_NO_REMOVE)

    assert get_history_entry_status(h_id) == "Done"


def test_resume_unfinished_on_startup(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """DB has Pending entry → resume_unfinished_translations processes it."""
    file_path = _create_txt(tmp_path)
    tasks = setup_translation_tasks([file_path], "English (US)", "French")
    h_id = tasks[0][0]

    # Verify it's pending
    assert get_history_entry_status(h_id) == "Pending"

    # Resume should start a worker
    TranslationWorker._is_any_worker_running = False
    worker = resume_unfinished_translations(config=_NO_REMOVE)
    assert worker is not None
    worker.wait()

    assert get_history_entry_status(h_id) == "Done"


def test_failed_retranslate_resets_to_pending(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Failed entry after batch_retranslate → status='Pending', progress=0."""
    from src.core.database import batch_retranslate_history_entries  # noqa: PLC0415

    # Create a task that fails
    def error_translate(
        texts: list[str],
        target_lang: str,
        source_lang: str = "",
        **kwargs: object,
    ) -> list[str]:
        raise ValueError("QUOTA_ERROR")

    monkeypatch.setattr("src.core.llm_engine.translate_text", error_translate)
    monkeypatch.setattr(
        "src.core.text_processor._llm_engine.translate_text", error_translate
    )

    file_path = _create_txt(tmp_path)
    tasks = setup_translation_tasks([file_path], "English (US)", "French")
    h_id = tasks[0][0]
    _run_worker(tasks)

    assert get_history_entry_status(h_id) == "Failed"

    # Simulate user clicking "Retranslate"
    batch_retranslate_history_entries([h_id], "English (US)", "French")
    assert get_history_entry_status(h_id) == "Pending"
    row = _get_entry(h_id)
    assert row[5] == 0  # progress reset to 0


def test_paused_not_resumed_on_startup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DB has only Paused entries → resume returns None."""
    file_path = _create_txt(tmp_path)
    tasks = setup_translation_tasks([file_path], "English (US)", "French")
    h_id = tasks[0][0]

    # Manually set to Paused
    update_history_status(h_id, "Paused")

    # Resume with default statuses (Pending, Translating) → should not find it
    TranslationWorker._is_any_worker_running = False
    worker = resume_unfinished_translations(
        statuses=("Pending", "Translating"),
    )
    assert worker is None
