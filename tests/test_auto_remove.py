"""Unit tests for auto-remove history feature."""

from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch

import pytest

from src.constants import (
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_PAUSED,
    STATUS_PENDING,
    STATUS_TRANSLATING,
)
from src.core.config import TranslationConfig
from src.core.database import (
    add_history_entry,
    get_history,
    get_history_entry_status,
    init_db,
    update_history_status,
)
from src.core.translator import TranslationWorker, _pipeline_finalize


@pytest.fixture
def setup_test_db(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Generator[None, None, None]:
    """Initializes a clean database in a temporary directory before each test."""
    db_file = tmp_path / "test_translator_auto_remove.db"
    monkeypatch.setattr("src.core.database.get_db_path", lambda: str(db_file))

    # Isolate config dir so load_setting reads from a clean path
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    monkeypatch.setattr("src.utils.path_manager.get_app_config_dir", lambda: config_dir)

    init_db()
    yield


@patch("src.core.translator.translate_file", return_value=True)
def test_translation_worker_auto_remove(
    mock_translate: object,
    setup_test_db: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Verify that TranslationWorker removes history entry and directory."""
    # 1. Build config with auto-remove enabled
    config = TranslationConfig(auto_remove_history=True)

    # 2. Add a pending task with a real-looking path in a "translations" dir
    trans_dir = tmp_path / "translations" / "task1"
    trans_dir.mkdir(parents=True)
    file_path = trans_dir / "test_FR.txt"
    file_path.write_text("translated content")

    add_history_entry(
        "test.txt",
        "English (US)",
        "French",
        STATUS_PENDING,
        storage_path=str(file_path),
    )
    assert len(get_history()) == 1
    assert trans_dir.exists()

    # 3. Run worker with explicit config
    worker = TranslationWorker([], config=config)
    TranslationWorker._is_any_worker_running = False
    worker.run()

    # 4. Verify history is empty and directory is deleted
    assert len(get_history()) == 0
    assert not trans_dir.exists()


@patch("src.core.translator.translate_file", return_value=True)
def test_translation_worker_no_auto_remove(
    mock_translate: object,
    setup_test_db: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Verify that TranslationWorker keeps history entry when setting is disabled."""
    # 1. Build config with auto-remove disabled
    config = TranslationConfig(auto_remove_history=False)

    # 2. Add a pending task with a real file
    file_path = tmp_path / "test.txt"
    file_path.write_text("content")

    add_history_entry(
        "test.txt",
        "English (US)",
        "French",
        STATUS_PENDING,
        storage_path=str(file_path),
    )
    assert len(get_history()) == 1

    # 3. Run worker with explicit config
    worker = TranslationWorker([], config=config)
    TranslationWorker._is_any_worker_running = False
    worker.run()

    # 4. Verify history is NOT empty and status is "Done"
    history = get_history()
    assert len(history) == 1
    assert history[0][4] == "Done"


@patch("src.core.translator.translate_file", return_value=True)
def test_translation_worker_default_behavior(
    mock_translate: object,
    setup_test_db: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Verify that TranslationWorker preserves history entry by default.

    Default ``TranslationConfig`` now has ``auto_remove_history=False``
    (matches the 4 sibling page-level features — Voice / Subtitle /
    Dubbing / Extract Text — all default False).  History entries
    persist after a successful translation unless the user opts in
    via the Settings checkbox.
    """
    config = TranslationConfig()
    assert config.auto_remove_history is False  # contract assertion

    task_dir = tmp_path / "tasks" / "1"
    task_dir.mkdir(parents=True)
    file_path = task_dir / "test.txt"
    file_path.write_text("content")

    add_history_entry(
        "test.txt",
        "English (US)",
        "French",
        STATUS_PENDING,
        storage_path=str(file_path),
    )
    assert len(get_history()) == 1

    worker = TranslationWorker([], config=config)
    TranslationWorker._is_any_worker_running = False
    worker.run()

    # Default config preserves the entry — the user can still see it
    # in the history table after the translation completes.
    assert len(get_history()) == 1


# --- _pipeline_finalize edge cases ---


@patch("src.core.translator.translate_file", side_effect=ValueError("AUTH_ERROR"))
def test_finalize_failed_task_not_removed_with_auto_remove(
    mock_translate: object,
    setup_test_db: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Failed task is NOT deleted even when auto-remove is enabled."""
    config = TranslationConfig(auto_remove_history=True)

    file_path = tmp_path / "fail.txt"
    file_path.write_text("content")

    add_history_entry(
        "fail.txt",
        "EN",
        "FR",
        STATUS_PENDING,
        storage_path=str(file_path),
    )

    worker = TranslationWorker([], config=config)
    TranslationWorker._is_any_worker_running = False
    worker.run()

    # Entry should still exist with Failed status
    history = get_history()
    assert len(history) == 1
    assert history[0][4] == STATUS_FAILED


def test_finalize_already_done_is_noop(
    setup_test_db: None,
    tmp_path: Path,
) -> None:
    """Calling _pipeline_finalize on an already-Done entry is a no-op."""
    config = TranslationConfig(auto_remove_history=False)

    h_id = add_history_entry(
        "done.txt",
        "EN",
        "FR",
        STATUS_DONE,
        storage_path="/tmp/fake/done.txt",
    )

    # Directly call _pipeline_finalize on a Done entry
    _pipeline_finalize(h_id, config)

    # Entry should remain untouched with Done status
    assert get_history_entry_status(h_id) == STATUS_DONE
    assert len(get_history()) == 1


def test_finalize_paused_is_noop(
    setup_test_db: None,
    tmp_path: Path,
) -> None:
    """Calling _pipeline_finalize on a Paused entry is a no-op."""
    config = TranslationConfig(auto_remove_history=False)

    h_id = add_history_entry(
        "paused.txt",
        "EN",
        "FR",
        STATUS_PAUSED,
        storage_path="/tmp/fake/paused.txt",
    )

    _pipeline_finalize(h_id, config)

    # Paused entry should remain untouched
    assert get_history_entry_status(h_id) == STATUS_PAUSED


def test_finalize_failed_with_auto_remove_off_keeps_entry(
    setup_test_db: None,
    tmp_path: Path,
) -> None:
    """Failed task stays as Failed when auto-remove is off."""
    config = TranslationConfig(auto_remove_history=False)

    h_id = add_history_entry(
        "failed.txt",
        "EN",
        "FR",
        STATUS_TRANSLATING,
        storage_path="/tmp/fake/failed.txt",
    )
    update_history_status(h_id, STATUS_FAILED, error_code=30)

    _pipeline_finalize(h_id, config)

    # Failed status should be preserved (not changed to Done)
    assert get_history_entry_status(h_id) == STATUS_FAILED
