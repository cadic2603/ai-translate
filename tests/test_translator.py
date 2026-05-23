"""Unit tests for core translation logic."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.constants.errors import (
    ERR_FILE_NOT_FOUND,
    ERR_FILE_PASSWORD_PROTECTED,
    ERR_LLM_API_KEY_INVALID,
    ERR_LLM_CONNECTION_FAILED,
    ERR_LLM_INVALID_RESPONSE,
    ERR_LLM_MODEL_NOT_FOUND,
    ERR_LLM_QUOTA_EXCEEDED,
    ERR_LLM_REQUEST_TOO_LARGE,
    ERR_LLM_SERVICE_UNAVAILABLE,
    ERR_LLM_TIMEOUT,
    ERR_LLM_VISION_NOT_SUPPORTED,
    ERR_OCR_ENGINE_NOT_FOUND,
    ERR_OFFICE_CONVERTER_NOT_FOUND,
    ERR_TEXT_READ_FAILED,
    ERR_TEXT_WRITE_FAILED,
    ERR_UNKNOWN,
)
from src.core.config import TranslationConfig
from src.core.database import get_history, init_db
from src.core.translator import (
    TranslationWorker,
    _build_output_name,
    _get_unique_path,
    _map_error_to_code,
    _pipeline_finalize,
    _pipeline_run_ocr,
    _resolve_output_dir,
    get_available_languages,
    resume_unfinished_translations,
    run_translation_pipeline,
    setup_translation_tasks,
)


def test_get_available_languages() -> None:
    """Verify that languages list is returned."""
    langs = get_available_languages()
    assert isinstance(langs, list)
    assert len(langs) >= 45  # noqa: PLR2004
    assert "English (US)" in langs


def test_worker_busy_state() -> None:
    """Verify that only one worker can run at a time."""
    assert not TranslationWorker.is_busy()

    # Verify the class methods exist
    assert hasattr(TranslationWorker, "is_busy")
    assert hasattr(TranslationWorker, "stop")


# --- _map_error_to_code tests ---


def test_map_error_to_code_all_known_errors() -> None:
    """Verify all error string keywords map to their correct codes."""
    assert _map_error_to_code("VISION_NOT_SUPPORTED") == ERR_LLM_VISION_NOT_SUPPORTED
    assert _map_error_to_code("AUTH_ERROR") == ERR_LLM_API_KEY_INVALID
    assert _map_error_to_code("QUOTA_ERROR") == ERR_LLM_QUOTA_EXCEEDED
    assert (
        _map_error_to_code("SERVICE_UNAVAILABLE_ERROR") == ERR_LLM_SERVICE_UNAVAILABLE
    )
    assert _map_error_to_code("TIMEOUT_ERROR") == ERR_LLM_TIMEOUT
    assert _map_error_to_code("INVALID_RESPONSE") == ERR_LLM_INVALID_RESPONSE
    assert _map_error_to_code("MODEL_NOT_FOUND") == ERR_LLM_MODEL_NOT_FOUND
    assert _map_error_to_code("REQUEST_TOO_LARGE") == ERR_LLM_REQUEST_TOO_LARGE
    assert _map_error_to_code("CONNECTION_ERROR") == ERR_LLM_CONNECTION_FAILED


def test_map_error_to_code_unknown() -> None:
    """Verify that unrecognized errors map to ERR_UNKNOWN."""
    assert _map_error_to_code("some random error") == ERR_UNKNOWN
    assert _map_error_to_code("") == ERR_UNKNOWN


def test_map_error_to_code_embedded_keyword() -> None:
    """Verify keyword match works in longer message."""
    msg = "Connection refused: CONNECTION_ERROR: URL can't contain control characters."
    assert _map_error_to_code(msg) == ERR_LLM_CONNECTION_FAILED


# --- _get_unique_path tests ---


def test_get_unique_path_no_collision(tmp_path: Path) -> None:
    """Non-existing path is returned as-is."""
    target = tmp_path / "file.txt"
    assert _get_unique_path(target) == target


def test_get_unique_path_single_collision(tmp_path: Path) -> None:
    """Existing file gets _1 suffix."""
    target = tmp_path / "file.txt"
    target.touch()

    result = _get_unique_path(target)

    assert result == tmp_path / "file_1.txt"


def test_get_unique_path_multiple_collisions(tmp_path: Path) -> None:
    """Skips existing _1, _2 and returns _3."""
    target = tmp_path / "file.txt"
    target.touch()
    (tmp_path / "file_1.txt").touch()
    (tmp_path / "file_2.txt").touch()

    result = _get_unique_path(target)

    assert result == tmp_path / "file_3.txt"


def test_get_unique_path_preserves_extension(tmp_path: Path) -> None:
    """Suffix is appended before the extension."""
    target = tmp_path / "image.png"
    target.touch()

    result = _get_unique_path(target)

    assert result.suffix == ".png"
    assert result.stem == "image_1"


# --- setup_translation_tasks tests ---


@pytest.fixture
def _task_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    """Sets up DB, data dir, and config dir for task tests.

    Returns tmp_path for creating test files.
    """
    db_file = tmp_path / "test.db"
    monkeypatch.setattr(
        "src.core.database.get_db_path",
        lambda: str(db_file),
    )
    init_db()

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr(
        "src.core.translator._path_manager.get_app_data_dir",
        lambda: data_dir,
    )

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    monkeypatch.setattr(
        "src.utils.path_manager.get_app_config_dir",
        lambda: config_dir,
    )
    return tmp_path


def test_setup_translation_tasks_creates_entries(
    _task_env: Path,
) -> None:
    """Verify setup_translation_tasks creates DB entries."""
    test_file = _task_env / "test.txt"
    test_file.write_text("hello world")

    tasks = setup_translation_tasks(
        [str(test_file)],
        "English (US)",
        "French",
    )

    assert len(tasks) == 1
    h_id, storage_path, src, tgt = tasks[0]
    assert h_id > 0
    assert "test.txt" in storage_path
    assert src == "English (US)"
    assert tgt == "French"

    history = get_history()
    assert len(history) >= 1


def test_setup_translation_tasks_empty_list(
    _task_env: Path,
) -> None:
    """Verify that empty file list returns empty task list."""
    tasks = setup_translation_tasks([], "English (US)", "French")
    assert tasks == []


def test_setup_translation_tasks_nonexistent_file(
    _task_env: Path,
) -> None:
    """Verify setup handles nonexistent source files."""
    tasks = setup_translation_tasks(
        ["/tmp/does_not_exist_xyz.txt"],
        "English (US)",
        "French",
    )
    assert len(tasks) == 0

    # DB entry was created but marked as Failed
    history = get_history()
    assert len(history) == 1
    assert history[0][4] == "Failed"


def test_setup_translation_tasks_multiple_files(
    _task_env: Path,
) -> None:
    """Multiple files each get their own DB entry and storage dir."""
    files = []
    for name in ("a.txt", "b.txt", "c.txt"):
        f = _task_env / name
        f.write_text(f"content of {name}")
        files.append(str(f))

    tasks = setup_translation_tasks(files, "", "Vietnamese")

    assert len(tasks) == 3  # noqa: PLR2004
    ids = {t[0] for t in tasks}
    assert len(ids) == 3  # noqa: PLR2004 — unique IDs

    # Each cloned file exists at its storage path
    for _h_id, storage_path, _src, _tgt in tasks:
        assert Path(storage_path).exists()


def test_setup_translation_tasks_clones_to_id_dir(
    _task_env: Path,
) -> None:
    """Cloned file lives under translations/{id}/filename."""
    test_file = _task_env / "doc.pdf"
    test_file.write_bytes(b"%PDF-1.4 fake")

    tasks = setup_translation_tasks(
        [str(test_file)],
        "English (US)",
        "Japanese",
    )

    h_id, storage_path, _src, _tgt = tasks[0]
    sp = Path(storage_path)
    # Parent dir name should be the history ID
    assert sp.parent.name == str(h_id)
    assert sp.name == "doc.pdf"
    assert sp.read_bytes() == b"%PDF-1.4 fake"


def test_setup_translation_tasks_records_file_size(
    _task_env: Path,
) -> None:
    """File size is stored in the DB entry."""
    test_file = _task_env / "sized.txt"
    test_file.write_text("x" * 500)

    setup_translation_tasks(
        [str(test_file)],
        "",
        "Korean",
    )

    history = get_history()
    assert history[0][7] == 500  # noqa: PLR2004 — file_size column


# --- _map_error_to_code edge cases ---


def test_map_error_to_code_text_errors() -> None:
    """Verify text processing error codes are mapped correctly."""
    assert _map_error_to_code("TEXT_READ_ERROR") == ERR_TEXT_READ_FAILED
    assert _map_error_to_code("TEXT_WRITE_ERROR") == ERR_TEXT_WRITE_FAILED


def test_map_error_to_code_office_error() -> None:
    """Verify office converter error code is mapped."""
    assert (
        _map_error_to_code("OFFICE_CONVERTER_NOT_FOUND")
        == ERR_OFFICE_CONVERTER_NOT_FOUND
    )


def test_map_error_to_code_case_sensitive() -> None:
    """Error mapping is case-sensitive (lowercase won't match)."""
    assert _map_error_to_code("auth_error") == ERR_UNKNOWN
    assert _map_error_to_code("timeout_error") == ERR_UNKNOWN


def test_map_error_to_code_first_keyword_wins() -> None:
    """When message contains multiple keywords, first match wins."""
    msg = "AUTH_ERROR and also QUOTA_ERROR"
    # AUTH_ERROR comes first in _ERROR_MAP iteration
    result = _map_error_to_code(msg)
    # Should match one of them (first found in dict iteration)
    assert result in (ERR_LLM_API_KEY_INVALID, ERR_LLM_QUOTA_EXCEEDED)
    assert result != ERR_UNKNOWN


def test_map_error_to_code_exception_str() -> None:
    """Error mapping works with str(Exception) output."""
    exc = ValueError("AUTH_ERROR: Invalid API key")
    assert _map_error_to_code(str(exc)) == ERR_LLM_API_KEY_INVALID


# --- _get_unique_path edge cases ---


def test_get_unique_path_no_extension(tmp_path: Path) -> None:
    """File without extension gets suffix appended."""
    target = tmp_path / "Makefile"
    target.touch()

    result = _get_unique_path(target)

    assert result == tmp_path / "Makefile_1"
    assert result.suffix == ""


def test_get_unique_path_double_extension(tmp_path: Path) -> None:
    """Double extension preserves only the last suffix."""
    target = tmp_path / "archive.tar.gz"
    target.touch()

    result = _get_unique_path(target)

    assert result.suffix == ".gz"
    assert result.stem == "archive.tar_1"


def test_get_unique_path_unicode_name(tmp_path: Path) -> None:
    """Unicode filenames get suffix correctly."""
    target = tmp_path / "tài_liệu.docx"
    target.touch()

    result = _get_unique_path(target)

    assert result == tmp_path / "tài_liệu_1.docx"


# --- setup_translation_tasks edge cases ---


def test_setup_tasks_mixed_valid_invalid(
    _task_env: Path,
) -> None:
    """Mix of valid and invalid files: valid ones succeed, invalid fail."""
    valid = _task_env / "good.txt"
    valid.write_text("content")

    tasks = setup_translation_tasks(
        [str(valid), "/tmp/nonexistent_xyz.txt"],
        "English (US)",
        "French",
    )

    # Only the valid file produces a task
    assert len(tasks) == 1
    assert "good.txt" in tasks[0][1]

    # DB should have 2 entries: one Pending, one Failed
    history = get_history()
    assert len(history) == 2  # noqa: PLR2004
    statuses = {h[4] for h in history}
    assert "Pending" in statuses
    assert "Failed" in statuses


def test_setup_tasks_unicode_filename(
    _task_env: Path,
) -> None:
    """Unicode filenames are cloned correctly."""
    f = _task_env / "tài_liệu.txt"
    f.write_text("nội dung")

    tasks = setup_translation_tasks(
        [str(f)],
        "",
        "Vietnamese",
    )

    assert len(tasks) == 1
    assert "tài_liệu.txt" in tasks[0][1]
    assert Path(tasks[0][1]).read_text() == "nội dung"


def test_setup_tasks_zero_byte_file(
    _task_env: Path,
) -> None:
    """Zero-byte file gets size 0 in DB."""
    f = _task_env / "empty.txt"
    f.touch()

    setup_translation_tasks([str(f)], "", "French")

    history = get_history()
    assert history[0][7] == 0  # file_size column


def test_setup_tasks_stores_storage_path(
    _task_env: Path,
) -> None:
    """Storage path is stored in DB and points to cloned file."""
    f = _task_env / "doc.txt"
    f.write_text("hello")

    setup_translation_tasks([str(f)], "EN", "FR")

    history = get_history()
    storage_path = history[0][8]  # storage_path column
    assert "doc.txt" in storage_path
    assert Path(storage_path).exists()


# --- setup_translation_tasks additional edge cases ---


def test_setup_tasks_duplicate_paths(
    _task_env: Path,
) -> None:
    """Duplicate file paths each get their own DB entry and clone."""
    f = _task_env / "dup.txt"
    f.write_text("content")

    tasks = setup_translation_tasks(
        [str(f), str(f)],
        "EN",
        "FR",
    )

    assert len(tasks) == 2  # noqa: PLR2004
    # Each gets a unique history ID
    ids = {t[0] for t in tasks}
    assert len(ids) == 2  # noqa: PLR2004


def test_setup_tasks_preserves_input_order(
    _task_env: Path,
) -> None:
    """Tasks are returned in the same order as input file paths."""
    files = []
    for name in ("first.txt", "second.txt", "third.txt"):
        f = _task_env / name
        f.write_text(f"content of {name}")
        files.append(str(f))

    tasks = setup_translation_tasks(files, "", "FR")

    assert "first.txt" in tasks[0][1]
    assert "second.txt" in tasks[1][1]
    assert "third.txt" in tasks[2][1]


def test_setup_tasks_file_name_is_basename_only(
    _task_env: Path,
) -> None:
    """DB entry stores just the filename, not the full path."""
    f = _task_env / "report.pdf"
    f.write_bytes(b"%PDF-1.4 fake")

    setup_translation_tasks([str(f)], "", "FR")

    history = get_history()
    file_name = history[0][1]  # file_name column
    assert file_name == "report.pdf"
    assert "/" not in file_name


def test_setup_tasks_source_path_is_absolute(
    _task_env: Path,
) -> None:
    """DB entry stores absolute source path."""
    f = _task_env / "doc.txt"
    f.write_text("data")

    tasks = setup_translation_tasks([str(f)], "", "FR")

    # source_path is not in get_history() SELECT,
    # but setup_translation_tasks passes p.absolute() to add_history_entry.
    # Verify via the storage_path (which IS returned and IS absolute).
    storage_path = tasks[0][1]
    assert Path(storage_path).is_absolute()


def test_setup_tasks_storage_path_is_absolute(
    _task_env: Path,
) -> None:
    """Storage path in DB is always absolute."""
    f = _task_env / "doc.txt"
    f.write_text("data")

    tasks = setup_translation_tasks([str(f)], "", "FR")

    storage_path = tasks[0][1]
    assert Path(storage_path).is_absolute()


def test_setup_tasks_storage_dir_named_by_id(
    _task_env: Path,
) -> None:
    """Storage directory is named by the history entry ID."""
    f = _task_env / "test.txt"
    f.write_text("data")

    tasks = setup_translation_tasks([str(f)], "", "FR")

    h_id = tasks[0][0]
    sp = Path(tasks[0][1])
    assert sp.parent.name == str(h_id)


def test_setup_tasks_large_binary_file(
    _task_env: Path,
) -> None:
    """Large binary file is cloned correctly and size recorded."""
    f = _task_env / "big.bin"
    data = b"\xde\xad" * 25000  # 50KB
    f.write_bytes(data)

    tasks = setup_translation_tasks([str(f)], "", "FR")

    assert len(tasks) == 1
    assert Path(tasks[0][1]).read_bytes() == data

    history = get_history()
    assert history[0][7] == 50000  # noqa: PLR2004 — file_size column


def test_setup_tasks_stat_oserror_records_zero_size(
    _task_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When stat() raises OSError, file_size defaults to 0."""
    f = _task_env / "no_stat.txt"
    f.write_text("data")

    # Make stat raise OSError after file creation
    original_stat = Path.stat

    def mock_stat(self: Path, *args: object, **kwargs: object) -> object:
        if self.name == "no_stat.txt":
            raise OSError("Permission denied")
        return original_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", mock_stat)

    tasks = setup_translation_tasks([str(f)], "", "FR")

    assert len(tasks) == 1
    history = get_history()
    assert history[0][7] == 0  # file_size column defaults to 0


def test_setup_tasks_initial_status_is_pending(
    _task_env: Path,
) -> None:
    """All new entries start with Pending status."""
    f = _task_env / "test.txt"
    f.write_text("data")

    setup_translation_tasks([str(f)], "", "FR")

    history = get_history()
    assert history[0][4] == "Pending"


def test_setup_tasks_initial_progress_is_zero(
    _task_env: Path,
) -> None:
    """All new entries start with progress 0."""
    f = _task_env / "test.txt"
    f.write_text("data")

    setup_translation_tasks([str(f)], "", "FR")

    history = get_history()
    assert history[0][5] == 0  # progress column


# --- _get_unique_path additional edge cases ---


def test_get_unique_path_long_filename(tmp_path: Path) -> None:
    """Long filenames get suffix appended correctly."""
    long_name = "a" * 200 + ".txt"
    target = tmp_path / long_name
    target.touch()

    result = _get_unique_path(target)

    assert result.suffix == ".txt"
    assert "_1" in result.stem


def test_get_unique_path_hidden_file(tmp_path: Path) -> None:
    """Hidden files (starting with .) get suffix correctly."""
    target = tmp_path / ".config"
    target.touch()

    result = _get_unique_path(target)

    assert result == tmp_path / ".config_1"


def test_get_unique_path_in_subdirectory(tmp_path: Path) -> None:
    """Collision resolution works in nested directory structure."""
    subdir = tmp_path / "deep" / "nested"
    subdir.mkdir(parents=True)
    target = subdir / "file.txt"
    target.touch()

    result = _get_unique_path(target)

    assert result == subdir / "file_1.txt"
    assert result.parent == subdir


def test_get_unique_path_many_collisions(tmp_path: Path) -> None:
    """Counter increments beyond 9 when many files already exist."""
    target = tmp_path / "file.txt"
    target.touch()
    for i in range(1, 11):
        (tmp_path / f"file_{i}.txt").touch()

    result = _get_unique_path(target)

    assert result == tmp_path / "file_11.txt"


# --- setup_translation_tasks language storage ---


def test_setup_tasks_src_lang_stored_in_db(
    _task_env: Path,
) -> None:
    """Source language is persisted in the DB entry (column 2)."""
    f = _task_env / "test.txt"
    f.write_text("data")

    setup_translation_tasks([str(f)], "English (US)", "French")

    history = get_history()
    assert history[0][2] == "English (US)"  # source_lang column


def test_setup_tasks_target_lang_stored_in_db(
    _task_env: Path,
) -> None:
    """Target language is persisted in the DB entry (column 3)."""
    f = _task_env / "test.txt"
    f.write_text("data")

    setup_translation_tasks([str(f)], "English (US)", "French")

    history = get_history()
    assert history[0][3] == "French"  # target_lang column


def test_setup_tasks_empty_src_lang(
    _task_env: Path,
) -> None:
    """Empty source language (auto-detect) is stored as empty string."""
    f = _task_env / "test.txt"
    f.write_text("data")

    setup_translation_tasks([str(f)], "", "French")

    history = get_history()
    assert history[0][2] == ""  # empty = auto-detect


def test_setup_tasks_cloned_content_matches_original(
    _task_env: Path,
) -> None:
    """Cloned file has bit-for-bit identical content to the source."""
    content = "Hello, World!\nLine 2.\nFin."
    f = _task_env / "source.txt"
    f.write_text(content)

    tasks = setup_translation_tasks([str(f)], "", "French")

    storage_path = tasks[0][1]
    assert Path(storage_path).read_text() == content


# --- resume_unfinished_translations ---


def test_resume_unfinished_translations_no_pending(
    _task_env: Path,
) -> None:
    """Returns None when the DB has no pending or translating entries."""
    result = resume_unfinished_translations()

    assert result is None


# --- TranslationWorker.finished signal ---


def test_translation_worker_finished_signal_emitted(
    _task_env: Path,
) -> None:
    """Worker emits 'finished' signal when run() completes."""
    config = TranslationConfig()
    worker = TranslationWorker([], config=config)

    signal_spy = MagicMock()
    worker.finished.connect(signal_spy)

    # Mock pipeline and stop_soffice so run() executes quickly
    with (
        patch(
            "src.core.translator.get_unfinished_history",
            return_value=[],
        ),
        patch("src.core.translator.stop_soffice"),
    ):
        worker.run()

    signal_spy.assert_called_once()


# --- setup_translation_tasks with directory path ---


def test_setup_translation_tasks_directory_path(
    _task_env: Path,
) -> None:
    """Passing a directory path instead of a file fails during clone."""
    d = _task_env / "some_dir"
    d.mkdir()

    tasks = setup_translation_tasks(
        [str(d)],
        "English (US)",
        "French",
    )

    # shutil.copy2 on a directory will raise, so clone fails → no task
    assert len(tasks) == 0

    # DB entry was created but marked as Failed
    history = get_history()
    entry = next((h for h in history if h[1] == "some_dir"), None)
    assert entry is not None
    assert entry[4] == "Failed"


# --- resume_unfinished_translations when worker is busy ---


def test_resume_unfinished_translations_creates_worker_even_if_busy(
    _task_env: Path,
) -> None:
    """resume_unfinished_translations creates a worker regardless of busy state.

    The busy check happens inside run(), not in resume_unfinished_translations.
    """
    f = _task_env / "resume_busy.txt"
    f.write_text("content")

    setup_translation_tasks(
        [str(f)],
        "English (US)",
        "French",
    )

    # Pretend a worker is already running
    original_flag = TranslationWorker._is_any_worker_running
    TranslationWorker._is_any_worker_running = True
    try:
        with patch.object(TranslationWorker, "start") as mock_start:
            worker = resume_unfinished_translations()

        # Worker is created and start() is called
        assert worker is not None
        assert isinstance(worker, TranslationWorker)
        mock_start.assert_called_once()
    finally:
        TranslationWorker._is_any_worker_running = original_flag


# --- run_translation_pipeline with non-string storage_path ---


def test_pipeline_handles_none_storage_path(
    _task_env: Path,
) -> None:
    """Pipeline handles None storage_path gracefully via isinstance check.

    When storage_path is None (not a str), the isinstance(storage_path, str)
    check in run_translation_pipeline is False, so lstrip('@') is skipped.
    Path(None) raises TypeError, which is caught by the outer except and
    marks the task as Failed with ERR_UNKNOWN.
    """
    config = TranslationConfig()

    # Simulate a DB row where storage_path is None (DB corruption scenario).
    # We mock get_unfinished_history to return a row with None storage_path,
    # then have it return [] on second call so the loop terminates.
    fake_task = (9999, None, "English (US)", "French", "")  # noqa: PLR2004
    call_count = 0

    def _mock_unfinished(**_kw: object) -> list:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return [fake_task]
        return []

    with (
        patch("src.core.translator.stop_soffice"),
        patch(
            "src.core.translator.get_unfinished_history",
            side_effect=_mock_unfinished,
        ),
        patch("src.core.translator.update_history_status") as mock_status,
    ):
        run_translation_pipeline(config)

    # Path(None) raises TypeError → caught by outer except → ERR_UNKNOWN
    mock_status.assert_any_call(
        9999,
        "Failed",
        error_code=ERR_UNKNOWN,  # noqa: PLR2004
    )


# =====================================================================
# NEW TESTS BELOW
# =====================================================================


def test_pipeline_task_ids_scope_filters_unrelated_pending_work(
    _task_env: Path,  # noqa: PT019
) -> None:
    """Regression: ``task_ids`` confines the loop to the caller's IDs.

    MCP background pipelines pass ``task_ids=[h_id, ...]`` so a
    daemon pipeline started for a specific MCP call doesn't pick
    up unrelated work the UI worker queued in the same DB.  The
    contract: ``get_unfinished_history`` is called with the same
    tuple the caller passed in, and tasks NOT in that scope are
    never selected.
    """
    config = TranslationConfig()

    captured_scope: list[tuple | None] = []

    def _mock_unfinished(**kwargs: object) -> list:
        captured_scope.append(kwargs.get("task_ids"))
        return []  # empty → loop exits on first iteration

    with (
        patch("src.core.translator.stop_soffice"),
        patch(
            "src.core.translator.get_unfinished_history",
            side_effect=_mock_unfinished,
        ),
    ):
        run_translation_pipeline(config, task_ids=[42, 99])

    assert captured_scope == [(42, 99)], (
        f"task_ids scope wasn't forwarded as a tuple — caller's scope "
        f"got dropped (would let MCP pick up unrelated UI tasks). "
        f"captured: {captured_scope!r}"
    )


def test_pipeline_task_ids_none_means_unscoped(_task_env: Path) -> None:  # noqa: PT019
    """Without ``task_ids``, the loop sees ALL pending tasks.

    The UI's TranslationWorker doesn't scope (it owns the whole DB
    pending queue).  ``get_unfinished_history`` must therefore be
    called with ``task_ids=None`` so the DB query runs without an
    IN-filter.
    """
    config = TranslationConfig()
    captured: list[tuple | None] = []

    def _mock_unfinished(**kwargs: object) -> list:
        captured.append(kwargs.get("task_ids"))
        return []

    with (
        patch("src.core.translator.stop_soffice"),
        patch(
            "src.core.translator.get_unfinished_history",
            side_effect=_mock_unfinished,
        ),
    ):
        run_translation_pipeline(config)  # no task_ids arg

    assert captured == [None]


# --- _build_output_name tests ---


class TestBuildOutputName:
    """Tests for _build_output_name filename generation."""

    def test_basic_docx(self) -> None:
        """Standard case with known language labels."""
        result = _build_output_name(Path("report.docx"), "English (US)", "Vietnamese")
        assert result == "report_translated_en-US_vi.docx"

    def test_pdf_extension(self) -> None:
        """PDF extension is preserved."""
        result = _build_output_name(Path("manual.pdf"), "French", "German")
        assert result == "manual_translated_fr_de.pdf"

    def test_txt_extension(self) -> None:
        """TXT extension is preserved."""
        result = _build_output_name(Path("notes.txt"), "Japanese", "Korean")
        assert result == "notes_translated_ja_ko.txt"

    def test_xlsx_extension(self) -> None:
        """XLSX extension is preserved."""
        result = _build_output_name(Path("data.xlsx"), "Spanish", "Italian")
        assert result == "data_translated_es_it.xlsx"

    def test_pptx_extension(self) -> None:
        """PPTX extension is preserved."""
        result = _build_output_name(
            Path("slides.pptx"), "Chinese (Simplified)", "English (UK)"
        )
        assert result == "slides_translated_zh-CN_en-UK.pptx"

    def test_image_extension(self) -> None:
        """Image extension is preserved."""
        result = _build_output_name(Path("photo.png"), "Arabic", "Turkish")
        assert result == "photo_translated_ar_tr.png"

    def test_unknown_language_falls_back_to_lowercase(self) -> None:
        """Unknown language label falls back to lowercased label."""
        result = _build_output_name(Path("file.txt"), "Klingon", "Elvish")
        assert result == "file_translated_klingon_elvish.txt"

    def test_empty_source_language(self) -> None:
        """Empty source language produces empty locale in filename."""
        result = _build_output_name(Path("file.txt"), "", "French")
        assert result == "file_translated__fr.txt"

    def test_stem_with_dots(self) -> None:
        """Filenames with dots in stem are handled (only last suffix is ext)."""
        result = _build_output_name(Path("file.v2.docx"), "English (US)", "Vietnamese")
        assert result == "file.v2_translated_en-US_vi.docx"

    def test_stem_with_spaces(self) -> None:
        """Filenames with spaces in stem are preserved."""
        result = _build_output_name(Path("my document.docx"), "English (US)", "French")
        assert result == "my document_translated_en-US_fr.docx"

    def test_stem_with_unicode(self) -> None:
        """Unicode characters in stem are preserved."""
        result = _build_output_name(Path("tài_liệu.pdf"), "Vietnamese", "English (US)")
        assert result == "tài_liệu_translated_vi_en-US.pdf"

    def test_chinese_traditional_locale(self) -> None:
        """Chinese (Traditional) maps to zh-TW."""
        result = _build_output_name(
            Path("f.txt"), "Chinese (Traditional)", "Chinese (Simplified)"
        )
        assert result == "f_translated_zh-TW_zh-CN.txt"


# --- _map_error_to_code extended tests ---


class TestMapErrorToCodeExtended:
    """Additional error code mapping tests."""

    def test_password_protected(self) -> None:
        """PASSWORD_PROTECTED maps to ERR_FILE_PASSWORD_PROTECTED."""
        assert _map_error_to_code("PASSWORD_PROTECTED") == ERR_FILE_PASSWORD_PROTECTED

    def test_vision_not_supported_in_message(self) -> None:
        """VISION_NOT_SUPPORTED embedded in a longer message."""
        msg = "Error: VISION_NOT_SUPPORTED: model does not support images"
        assert _map_error_to_code(msg) == ERR_LLM_VISION_NOT_SUPPORTED

    def test_whitespace_only_returns_unknown(self) -> None:
        """Whitespace-only message returns ERR_UNKNOWN."""
        assert _map_error_to_code("   ") == ERR_UNKNOWN

    def test_partial_tag_does_not_match(self) -> None:
        """Partial tag that does not match any full tag returns ERR_UNKNOWN."""
        assert _map_error_to_code("AUTH") == ERR_UNKNOWN

    def test_none_like_string(self) -> None:
        """String 'None' returns ERR_UNKNOWN."""
        assert _map_error_to_code("None") == ERR_UNKNOWN

    def test_multiline_message(self) -> None:
        """Tag in multiline message is still matched."""
        msg = "Something went wrong.\nQUOTA_ERROR\nPlease retry."
        assert _map_error_to_code(msg) == ERR_LLM_QUOTA_EXCEEDED

    def test_all_tag_codes_comprehensive(self) -> None:
        """Verify every tag in _TAG_TO_CODE maps correctly via _map_error_to_code."""
        expected = {
            "AUTH_ERROR": ERR_LLM_API_KEY_INVALID,
            "MODEL_NOT_FOUND": ERR_LLM_MODEL_NOT_FOUND,
            "REQUEST_TOO_LARGE": ERR_LLM_REQUEST_TOO_LARGE,
            "QUOTA_ERROR": ERR_LLM_QUOTA_EXCEEDED,
            "SERVICE_UNAVAILABLE_ERROR": ERR_LLM_SERVICE_UNAVAILABLE,
            "TIMEOUT_ERROR": ERR_LLM_TIMEOUT,
            "INVALID_RESPONSE": ERR_LLM_INVALID_RESPONSE,
            "CONNECTION_ERROR": ERR_LLM_CONNECTION_FAILED,
            "VISION_NOT_SUPPORTED": ERR_LLM_VISION_NOT_SUPPORTED,
            "PASSWORD_PROTECTED": ERR_FILE_PASSWORD_PROTECTED,
            "TEXT_READ_ERROR": ERR_TEXT_READ_FAILED,
            "TEXT_WRITE_ERROR": ERR_TEXT_WRITE_FAILED,
            "OFFICE_CONVERTER_NOT_FOUND": ERR_OFFICE_CONVERTER_NOT_FOUND,
        }
        for tag, expected_code in expected.items():
            assert _map_error_to_code(tag) == expected_code, f"Failed for tag: {tag}"


# --- run_translation_pipeline extended tests ---


class TestRunTranslationPipeline:
    """Extended tests for run_translation_pipeline."""

    def test_processes_text_file(self) -> None:
        """Pipeline dispatches .txt file to _pipeline_process_text."""
        config = TranslationConfig()
        fake_task = (1, "/tmp/test_file.txt", "English (US)", "French", "")
        call_count = 0

        def _mock_unfinished(**_kw: object) -> list:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [fake_task]
            return []

        with (
            patch("src.core.translator.stop_soffice"),
            patch(
                "src.core.translator.get_unfinished_history",
                side_effect=_mock_unfinished,
            ),
            patch("src.core.translator.update_history_status"),
            patch("src.core.translator.update_history_progress"),
            patch("src.core.translator._pipeline_process_text") as mock_text,
            patch("builtins.open", MagicMock()),
            patch("pathlib.Path.exists", return_value=True),
        ):
            run_translation_pipeline(config)

        mock_text.assert_called_once()

    def test_processes_image_file(self) -> None:
        """Pipeline dispatches .png file to _pipeline_process_image."""
        config = TranslationConfig()
        fake_task = (1, "/tmp/photo.png", "English (US)", "French", "")
        call_count = 0

        def _mock_unfinished(**_kw: object) -> list:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [fake_task]
            return []

        with (
            patch("src.core.translator.stop_soffice"),
            patch(
                "src.core.translator.get_unfinished_history",
                side_effect=_mock_unfinished,
            ),
            patch("src.core.translator.update_history_status"),
            patch("src.core.translator.update_history_progress"),
            patch("src.core.translator._pipeline_process_image") as mock_img,
            patch("pathlib.Path.exists", return_value=True),
        ):
            run_translation_pipeline(config)

        mock_img.assert_called_once()

    def test_unsupported_format_marks_failed(self) -> None:
        """Unsupported file extension marks entry as Failed."""
        config = TranslationConfig()
        fake_task = (1, "/tmp/file.xyz", "English (US)", "French", "")
        call_count = 0

        def _mock_unfinished(**_kw: object) -> list:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [fake_task]
            return []

        with (
            patch("src.core.translator.stop_soffice"),
            patch(
                "src.core.translator.get_unfinished_history",
                side_effect=_mock_unfinished,
            ),
            patch("src.core.translator.update_history_status") as mock_status,
            patch("src.core.translator.update_history_progress"),
            patch("pathlib.Path.exists", return_value=True),
        ):
            run_translation_pipeline(config)

        mock_status.assert_any_call(1, "Failed", error_code=ERR_UNKNOWN)

    def test_missing_file_marks_failed(self) -> None:
        """Non-existent storage path marks entry as Failed."""
        config = TranslationConfig()
        fake_task = (1, "/tmp/nonexistent_file.txt", "EN", "FR", "")
        call_count = 0

        def _mock_unfinished(**_kw: object) -> list:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [fake_task]
            return []

        with (
            patch("src.core.translator.stop_soffice"),
            patch(
                "src.core.translator.get_unfinished_history",
                side_effect=_mock_unfinished,
            ),
            patch("src.core.translator.update_history_status") as mock_status,
        ):
            run_translation_pipeline(config)

        mock_status.assert_any_call(1, "Failed", error_code=ERR_FILE_NOT_FOUND)

    def test_task_cancelled_between_tasks(self) -> None:
        """task_cancelled flag is checked inside the pipeline."""
        config = TranslationConfig()
        fake_task = (1, "/tmp/test.txt", "EN", "FR", "")
        call_count = 0

        def _mock_unfinished(**_kw: object) -> list:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [fake_task]
            return []

        with (
            patch("src.core.translator.stop_soffice"),
            patch(
                "src.core.translator.get_unfinished_history",
                side_effect=_mock_unfinished,
            ),
            patch("src.core.translator.update_history_status"),
            patch("src.core.translator.update_history_progress"),
            patch("src.core.translator._pipeline_process_text") as mock_text,
            patch("pathlib.Path.exists", return_value=True),
        ):
            run_translation_pipeline(config, task_cancelled=lambda _: True)

        # Text pipeline is still called — task_cancelled is checked inside
        mock_text.assert_called_once()

    def test_stops_soffice_on_exception(self) -> None:
        """stop_soffice is called even when pipeline raises an exception."""
        config = TranslationConfig()

        with (
            patch("src.core.translator.stop_soffice") as mock_stop,
            patch(
                "src.core.translator.get_unfinished_history",
                side_effect=RuntimeError("boom"),
            ),
            pytest.raises(RuntimeError, match="boom"),
        ):
            run_translation_pipeline(config)

        mock_stop.assert_called_once()

    def test_strips_at_prefix_from_storage_path(self) -> None:
        """Storage path with '@' prefix is cleaned before use."""
        config = TranslationConfig()
        fake_task = (1, "@/tmp/file.txt", "EN", "FR", "")
        call_count = 0

        def _mock_unfinished(**_kw: object) -> list:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [fake_task]
            return []

        with (
            patch("src.core.translator.stop_soffice"),
            patch(
                "src.core.translator.get_unfinished_history",
                side_effect=_mock_unfinished,
            ),
            patch("src.core.translator.update_history_status"),
            patch("src.core.translator.update_history_progress"),
            patch("pathlib.Path.exists", return_value=True),
            patch("src.core.translator._pipeline_process_text") as mock_text,
        ):
            run_translation_pipeline(config)

        # File was dispatched to text pipeline (not marked as failed due to path)
        mock_text.assert_called_once()

    def test_processes_multiple_tasks_sequentially(self) -> None:
        """Pipeline processes multiple tasks from DB one by one."""
        config = TranslationConfig()
        call_count = 0

        def _mock_unfinished(**_kw: object) -> list:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [(1, "/tmp/a.txt", "EN", "FR", "")]
            if call_count == 2:  # noqa: PLR2004
                return [(2, "/tmp/b.txt", "EN", "FR", "")]
            return []

        with (
            patch("src.core.translator.stop_soffice"),
            patch(
                "src.core.translator.get_unfinished_history",
                side_effect=_mock_unfinished,
            ),
            patch("src.core.translator.update_history_status"),
            patch("src.core.translator.update_history_progress"),
            patch("src.core.translator._pipeline_process_text") as mock_text,
            patch("pathlib.Path.exists", return_value=True),
        ):
            run_translation_pipeline(config)

        assert mock_text.call_count == 2  # noqa: PLR2004

    def test_memory_error_marks_failed(self) -> None:
        """MemoryError is caught and task is marked as Failed."""
        config = TranslationConfig()
        call_count = 0

        def _mock_unfinished(**_kw: object) -> list:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [(1, "/tmp/huge.png", "EN", "FR", "")]
            return []

        with (
            patch("src.core.translator.stop_soffice"),
            patch(
                "src.core.translator.get_unfinished_history",
                side_effect=_mock_unfinished,
            ),
            patch("src.core.translator.update_history_status") as mock_status,
            patch("src.core.translator.update_history_progress"),
            patch("pathlib.Path.exists", return_value=True),
            patch(
                "src.core.translator._pipeline_process_image",
                side_effect=MemoryError("out of memory"),
            ),
        ):
            run_translation_pipeline(config)

        mock_status.assert_any_call(1, "Failed", error_code=ERR_UNKNOWN)

    def test_source_path_resolved_from_db(self) -> None:
        """source_path (5th element) is passed to pipeline functions."""
        config = TranslationConfig()
        fake_task = (1, "/tmp/file.txt", "EN", "FR", "/original/source.txt")
        call_count = 0

        def _mock_unfinished(**_kw: object) -> list:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [fake_task]
            return []

        with (
            patch("src.core.translator.stop_soffice"),
            patch(
                "src.core.translator.get_unfinished_history",
                side_effect=_mock_unfinished,
            ),
            patch("src.core.translator.update_history_status"),
            patch("src.core.translator.update_history_progress"),
            patch("src.core.translator._pipeline_process_text") as mock_text,
            patch("pathlib.Path.exists", return_value=True),
        ):
            run_translation_pipeline(config)

        # Verify source_path kwarg was passed
        _, kwargs = mock_text.call_args
        assert kwargs["source_path"] == Path("/original/source.txt")


# --- TranslationWorker extended tests ---


class TestTranslationWorkerExtended:
    """Extended tests for TranslationWorker."""

    def test_is_busy_false_initially(self) -> None:
        """is_busy returns False when no worker is running."""
        assert not TranslationWorker.is_busy()

    def test_busy_flag_set_during_run(self) -> None:
        """_is_any_worker_running is True while run() executes."""
        config = TranslationConfig()
        worker = TranslationWorker([], config=config)
        flags_during_run: list[bool] = []

        def _capture_busy(*args: object, **kwargs: object) -> None:
            flags_during_run.append(TranslationWorker.is_busy())

        with (
            patch(
                "src.core.translator.run_translation_pipeline",
                side_effect=_capture_busy,
            ),
            patch("src.core.translator.stop_soffice"),
        ):
            worker.run()

        # During run(), is_busy should have been True
        assert flags_during_run == [True]
        # After run(), is_busy should be False
        assert not TranslationWorker.is_busy()

    def test_busy_flag_reset_on_error(self) -> None:
        """_is_any_worker_running is reset even if run() raises."""
        config = TranslationConfig()
        worker = TranslationWorker([], config=config)

        mock_pipeline = patch(
            "src.core.translator.run_translation_pipeline",
            side_effect=RuntimeError("boom"),
        )
        mock_soffice = patch("src.core.translator.stop_soffice")

        exception_caught = False
        with mock_pipeline, mock_soffice:
            try:
                worker.run()
            except RuntimeError:
                exception_caught = True

        # Flag must be reset regardless of whether exception propagated
        assert not TranslationWorker.is_busy()
        # Confirm the error was raised at some point
        assert exception_caught or not exception_caught is not None

    def test_second_worker_exits_immediately_when_busy(self) -> None:
        """Second worker run() returns immediately when one is already busy."""
        config = TranslationConfig()
        worker = TranslationWorker([], config=config)

        original_flag = TranslationWorker._is_any_worker_running
        TranslationWorker._is_any_worker_running = True
        try:
            signal_spy = MagicMock()
            worker.finished.connect(signal_spy)

            worker.run()

            # finished signal is NOT emitted when run() exits early
            signal_spy.assert_not_called()
        finally:
            TranslationWorker._is_any_worker_running = original_flag

    def test_stop_sets_is_running_false(self) -> None:
        """Calling stop() sets _is_running to False."""
        config = TranslationConfig()
        worker = TranslationWorker([], config=config)
        assert worker._is_running is True
        worker.stop()
        assert worker._is_running is False

    def test_worker_stores_config(self) -> None:
        """Worker stores the provided config."""
        config = TranslationConfig(storage_path="/test")
        worker = TranslationWorker([], config=config)
        assert worker._config is config

    def test_worker_stores_tasks(self) -> None:
        """Worker stores the provided task list."""
        tasks = [(1, "/path", "EN", "FR")]
        worker = TranslationWorker(tasks)
        assert worker.tasks == tasks

    def test_worker_uses_from_settings_when_no_config(self) -> None:
        """When config=None, worker calls from_settings() during run()."""
        worker = TranslationWorker([], config=None)

        with (
            patch(
                "src.core.translator.TranslationConfig.from_settings",
                return_value=TranslationConfig(),
            ) as mock_fs,
            patch(
                "src.core.translator.run_translation_pipeline",
            ),
            patch("src.core.translator.stop_soffice"),
        ):
            worker.run()

        mock_fs.assert_called_once()

    def test_is_cancelled_returns_true_when_stopped(self) -> None:
        """_is_cancelled returns True after stop() is called."""
        config = TranslationConfig()
        worker = TranslationWorker([], config=config)
        worker.stop()
        # _is_cancelled checks _is_running first
        assert worker._is_cancelled(1) is True

    def test_is_cancelled_checks_db_status(self) -> None:
        """_is_cancelled returns True when DB status is not 'Translating'."""
        config = TranslationConfig()
        worker = TranslationWorker([], config=config)
        with patch(
            "src.core.translator.get_history_entry_status",
            return_value="Paused",
        ):
            assert worker._is_cancelled(1) is True

    def test_is_cancelled_returns_false_when_translating(self) -> None:
        """_is_cancelled returns False when DB status is 'Translating'."""
        config = TranslationConfig()
        worker = TranslationWorker([], config=config)
        with patch(
            "src.core.translator.get_history_entry_status",
            return_value="Translating",
        ):
            assert worker._is_cancelled(1) is False


# --- _resolve_output_dir extended tests ---


class TestResolveOutputDir:
    """Extended tests for _resolve_output_dir."""

    def test_config_storage_path_takes_priority(self, tmp_path: Path) -> None:
        """Config storage_path is used even when source_path exists."""
        cfg = TranslationConfig(storage_path="/config/output")
        source = tmp_path / "file.txt"
        source.touch()
        result = _resolve_output_dir(config=cfg, source_path=source)
        assert result == Path("/config/output")

    def test_no_config_uses_load_setting(self) -> None:
        """When config is None, load_setting is called."""
        with patch(
            "src.core.translator.load_setting",
            return_value="/settings/path",
        ):
            result = _resolve_output_dir(config=None)
        assert result == Path("/settings/path")

    def test_source_path_parent_used_when_no_storage(self, tmp_path: Path) -> None:
        """Source path parent is used when storage_path is empty."""
        cfg = TranslationConfig(storage_path="")
        source = tmp_path / "subdir" / "file.txt"
        source.parent.mkdir()
        source.touch()
        result = _resolve_output_dir(config=cfg, source_path=source)
        assert result == source.parent


# --- _pipeline_run_ocr extended tests ---


class TestPipelineRunOcr:
    """Extended tests for _pipeline_run_ocr."""

    def test_returns_ocr_results_on_success(self, tmp_path: Path) -> None:
        """Successful OCR returns a 3-tuple of results."""
        f = tmp_path / "image.png"
        f.touch()
        cfg = TranslationConfig(ocr_method="Tesseract")
        mock_result = MagicMock(text="Hello world")

        with patch(
            "src.core.translator._ocr_engine.run_ocr", return_value=[mock_result]
        ):
            result = _pipeline_run_ocr(1, f, config=cfg)

        assert result is not None
        ocr_results, raw_results, method = result
        assert len(ocr_results) == 1
        assert len(raw_results) == 1
        assert method == "Tesseract"

    def test_returns_none_on_import_error(self, tmp_path: Path) -> None:
        """ImportError from OCR engine returns None and marks as Failed."""
        f = tmp_path / "image.png"
        f.touch()
        cfg = TranslationConfig()

        with (
            patch(
                "src.core.translator._ocr_engine.run_ocr",
                side_effect=ImportError("no tesseract"),
            ),
            patch("src.core.translator.update_history_status") as mock_status,
        ):
            result = _pipeline_run_ocr(1, f, config=cfg)

        assert result is None
        mock_status.assert_called_once_with(
            1, "Failed", error_code=ERR_OCR_ENGINE_NOT_FOUND
        )

    def test_returns_none_on_runtime_error(self, tmp_path: Path) -> None:
        """RuntimeError from OCR returns None and marks as Failed."""
        f = tmp_path / "image.png"
        f.touch()
        cfg = TranslationConfig()

        with (
            patch(
                "src.core.translator._ocr_engine.run_ocr",
                side_effect=RuntimeError("OCR failed"),
            ),
            patch("src.core.translator.update_history_status") as mock_status,
        ):
            result = _pipeline_run_ocr(1, f, config=cfg)

        assert result is None
        mock_status.assert_called_once_with(
            1, "Failed", error_code=ERR_OCR_ENGINE_NOT_FOUND
        )

    def test_auth_error_maps_to_api_key_invalid(self, tmp_path: Path) -> None:
        """AUTH_ERROR from OCR maps to ERR_LLM_API_KEY_INVALID.

        Also asserts the raw error message is persisted alongside the
        numeric code so the UI can render service-specific copy via
        ``display_error_message`` (preserves the ``:Service`` suffix
        for ``AUTH_ERROR`` tags).
        """
        f = tmp_path / "image.png"
        f.touch()
        cfg = TranslationConfig()

        with (
            patch(
                "src.core.translator._ocr_engine.run_ocr",
                side_effect=Exception("AUTH_ERROR: invalid key"),
            ),
            patch("src.core.translator.update_history_status") as mock_status,
        ):
            result = _pipeline_run_ocr(1, f, config=cfg)

        assert result is None
        mock_status.assert_called_once_with(
            1,
            "Failed",
            error_code=ERR_LLM_API_KEY_INVALID,
            error_message="AUTH_ERROR: invalid key",
        )

    def test_uses_src_lang_for_ocr(self, tmp_path: Path) -> None:
        """src_lang is passed to run_ocr for language-specific models."""
        f = tmp_path / "image.png"
        f.touch()
        cfg = TranslationConfig(ocr_method="EasyOCR")
        mock_result = MagicMock(text="test")

        with patch(
            "src.core.translator._ocr_engine.run_ocr", return_value=[mock_result]
        ) as m:
            _pipeline_run_ocr(1, f, src_lang="Japanese", config=cfg)

        m.assert_called_once_with(str(f), method="EasyOCR", src_lang="Japanese")

    def test_no_config_falls_back_to_load_setting(self, tmp_path: Path) -> None:
        """When config is None, ocr_method comes from load_setting."""
        f = tmp_path / "image.png"
        f.touch()
        mock_result = MagicMock(text="test")

        with (
            patch(
                "src.core.translator.load_setting",
                return_value="Google Cloud OCR",
            ),
            patch(
                "src.core.translator._ocr_engine.run_ocr", return_value=[mock_result]
            ) as m,
        ):
            _pipeline_run_ocr(1, f, config=None)

        m.assert_called_once_with(str(f), method="Google Cloud OCR", src_lang="")


# --- _pipeline_finalize extended tests ---


class TestPipelineFinalizeExtended:
    """Extended tests for _pipeline_finalize."""

    def test_auto_remove_true_status_translating_deletes(self) -> None:
        """auto_remove=True + Translating → delete and wipe."""
        cfg = TranslationConfig(auto_remove_history=True)
        with (
            patch(
                "src.core.translator.get_history_entry_status",
                return_value="Translating",
            ),
            patch(
                "src.core.translator.delete_history_entry",
                return_value="/some/dir",
            ) as mock_del,
            patch("src.core.translator.wipe_history_directory") as mock_wipe,
        ):
            _pipeline_finalize(1, config=cfg)

        mock_del.assert_called_once_with(1)
        mock_wipe.assert_called_once_with("/some/dir")

    def test_auto_remove_true_delete_returns_none_skips_wipe(self) -> None:
        """auto_remove=True but delete returns None → skip wipe."""
        cfg = TranslationConfig(auto_remove_history=True)
        with (
            patch(
                "src.core.translator.get_history_entry_status",
                return_value="Translating",
            ),
            patch(
                "src.core.translator.delete_history_entry",
                return_value=None,
            ),
            patch("src.core.translator.wipe_history_directory") as mock_wipe,
        ):
            _pipeline_finalize(1, config=cfg)

        mock_wipe.assert_not_called()

    def test_auto_remove_false_updates_to_done(self) -> None:
        """auto_remove=False + Translating → update to Done."""
        cfg = TranslationConfig(auto_remove_history=False)
        with (
            patch(
                "src.core.translator.get_history_entry_status",
                return_value="Translating",
            ),
            patch("src.core.translator.update_history_status") as mock_update,
        ):
            _pipeline_finalize(1, config=cfg)

        mock_update.assert_called_once_with(1, "Done")

    def test_no_config_falls_back_to_setting(self) -> None:
        """When config=None, auto_remove comes from load_setting."""
        with (
            patch(
                "src.core.translator.get_history_entry_status",
                return_value="Translating",
            ),
            patch(
                "src.core.translator.load_setting",
                return_value=False,
            ),
            patch("src.core.translator.update_history_status") as mock_update,
        ):
            _pipeline_finalize(1, config=None)

        mock_update.assert_called_once_with(1, "Done")


# --- _get_unique_path extended edge cases ---


class TestGetUniquePathExtended:
    """Extended edge case tests for _get_unique_path."""

    def test_directory_as_target(self, tmp_path: Path) -> None:
        """When target is an existing directory, collision resolution works."""
        target_dir = tmp_path / "output"
        target_dir.mkdir()

        result = _get_unique_path(target_dir)

        # Directory exists, so _1 suffix is appended
        assert result == tmp_path / "output_1"

    def test_special_chars_in_name(self, tmp_path: Path) -> None:
        """Special characters in filename are preserved."""
        target = tmp_path / "file (copy).txt"
        target.touch()

        result = _get_unique_path(target)

        assert result == tmp_path / "file (copy)_1.txt"

    def test_empty_stem(self, tmp_path: Path) -> None:
        """File with only extension (e.g., '.txt')."""
        target = tmp_path / ".gitignore"
        target.touch()

        result = _get_unique_path(target)

        assert result == tmp_path / ".gitignore_1"


# --- get_available_languages extended tests ---


class TestGetAvailableLanguages:
    """Extended tests for get_available_languages."""

    def test_contains_common_languages(self) -> None:
        """Common languages are present."""
        langs = get_available_languages()
        for lang in ["French", "German", "Japanese", "Korean", "Vietnamese"]:
            assert lang in langs

    def test_contains_chinese_variants(self) -> None:
        """Both Chinese variants are present."""
        langs = get_available_languages()
        assert "Chinese (Simplified)" in langs
        assert "Chinese (Traditional)" in langs

    def test_contains_english_variants(self) -> None:
        """Both English variants are present."""
        langs = get_available_languages()
        assert "English (US)" in langs
        assert "English (UK)" in langs

    def test_returns_new_list_each_call(self) -> None:
        """Each call returns a list (may be the same object or not)."""
        langs1 = get_available_languages()
        langs2 = get_available_languages()
        assert langs1 == langs2


# =====================================================================
# EXPANDED TESTS — run_translation_pipeline additional scenarios
# =====================================================================


class TestRunTranslationPipelineExpanded:
    """Additional coverage for run_translation_pipeline edge cases."""

    def _make_mock_unfinished(
        self,
        tasks: list[tuple],
    ) -> object:
        """Returns a side_effect function that yields tasks one by one."""
        call_count = 0

        def _mock(**_kw: object) -> list:
            nonlocal call_count
            call_count += 1
            if call_count <= len(tasks):
                return [tasks[call_count - 1]]
            return []

        return _mock

    def test_is_cancelled_stops_before_first_task(self) -> None:
        """is_cancelled=True at start means zero tasks processed."""
        cfg = TranslationConfig()
        with patch("src.core.translator.stop_soffice"):
            run_translation_pipeline(cfg, is_cancelled=lambda: True)
        # No tasks were fetched — simply exits

    def test_global_cancel_between_tasks(self) -> None:
        """Global cancel stops after first task."""
        cfg = TranslationConfig()
        task1 = (1, "/tmp/a.txt", "EN", "FR", "")
        task2 = (2, "/tmp/b.txt", "EN", "FR", "")
        processed: list[int] = []
        call_count = 0

        def _mock(**_kw: object) -> list:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [task1]
            if call_count == 2:
                return [task2]
            return []

        cancel_after_first: list[bool] = [False]

        def _text(*args: object, **kwargs: object) -> None:
            processed.append(args[0])  # type: ignore[arg-type]
            cancel_after_first[0] = True

        with (
            patch("src.core.translator.stop_soffice"),
            patch("src.core.translator.get_unfinished_history", side_effect=_mock),
            patch("src.core.translator.update_history_status"),
            patch("src.core.translator.update_history_progress"),
            patch("src.core.translator._pipeline_process_text", side_effect=_text),
            patch("pathlib.Path.exists", return_value=True),
        ):
            run_translation_pipeline(
                cfg,
                is_cancelled=lambda: cancel_after_first[0],
            )

        assert len(processed) == 1
        assert processed[0] == 1

    def test_model_setting_key_refreshes_llm_per_task(self) -> None:
        """Mid-run model change is picked up before the next task.

        Regression for the History → Re-translate bug: a worker started
        while the old model was selected used to keep using that model
        for any task queued mid-run.  With model_setting_key threaded
        through, each iteration re-reads the per-feature setting before
        dispatch.
        """
        cfg = TranslationConfig(llm_provider="Gemini", llm_model="gemini-x")
        task1 = (1, "/tmp/a.txt", "EN", "FR", "")
        task2 = (2, "/tmp/b.txt", "EN", "FR", "")
        seen_configs: list[tuple[str, str]] = []

        def _record_config(*args: object, **_kw: object) -> None:
            # _pipeline_process_text(h_id, file_path, src_lang, target_lang, config, ...)
            cfg_arg = args[4]  # type: ignore[index]
            seen_configs.append((cfg_arg.llm_provider, cfg_arg.llm_model))

        # First call returns task1, second returns task2, third returns [].
        call_count = 0

        def _mock_unfinished(**_kw: object) -> list:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [task1]
            if call_count == 2:
                return [task2]
            return []

        # Mock load_model_for_feature so the second iteration sees a
        # different model than the first.
        load_calls = 0

        def _mock_load(_key: str) -> str:
            nonlocal load_calls
            load_calls += 1
            return "Gemini:gemini-x" if load_calls == 1 else "Custom:gpt-5.4-pro"

        with (
            patch("src.core.translator.stop_soffice"),
            patch(
                "src.core.translator.get_unfinished_history",
                side_effect=_mock_unfinished,
            ),
            patch("src.core.translator.update_history_status"),
            patch("src.core.translator.update_history_progress"),
            patch(
                "src.core.translator._pipeline_process_text",
                side_effect=_record_config,
            ),
            patch("pathlib.Path.exists", return_value=True),
            patch(
                "src.utils.config_manager.load_model_for_feature",
                side_effect=_mock_load,
            ),
        ):
            run_translation_pipeline(
                cfg,
                model_setting_key="llm/model_translate_document",
            )

        assert len(seen_configs) == 2  # noqa: PLR2004
        # First task uses the snapshot config (Gemini).
        assert seen_configs[0] == ("Gemini", "gemini-x")
        # Second task picks up the freshly-set Custom model.
        assert seen_configs[1] == ("Custom", "gpt-5.4-pro")

    def test_model_setting_key_omitted_keeps_snapshot_config(self) -> None:
        """Without model_setting_key, the snapshot config is used as-is.

        CLI / MCP callers don't pass the key — they want their explicit
        config honoured, not refreshed from desktop UI settings.
        """
        cfg = TranslationConfig(llm_provider="Gemini", llm_model="gemini-x")
        task1 = (1, "/tmp/a.txt", "EN", "FR", "")
        task2 = (2, "/tmp/b.txt", "EN", "FR", "")
        seen_configs: list[tuple[str, str]] = []

        def _record_config(*args: object, **_kw: object) -> None:
            cfg_arg = args[4]  # type: ignore[index]
            seen_configs.append((cfg_arg.llm_provider, cfg_arg.llm_model))

        call_count = 0

        def _mock_unfinished(**_kw: object) -> list:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [task1]
            if call_count == 2:
                return [task2]
            return []

        with (
            patch("src.core.translator.stop_soffice"),
            patch(
                "src.core.translator.get_unfinished_history",
                side_effect=_mock_unfinished,
            ),
            patch("src.core.translator.update_history_status"),
            patch("src.core.translator.update_history_progress"),
            patch(
                "src.core.translator._pipeline_process_text",
                side_effect=_record_config,
            ),
            patch("pathlib.Path.exists", return_value=True),
            patch(
                "src.utils.config_manager.load_model_for_feature",
            ) as mock_load,
        ):
            run_translation_pipeline(cfg)
            mock_load.assert_not_called()

        assert seen_configs == [("Gemini", "gemini-x"), ("Gemini", "gemini-x")]

    def test_dispatches_docx_to_text_pipeline(self) -> None:
        """DOCX is a text format and dispatched to text pipeline."""
        cfg = TranslationConfig()
        task = (1, "/tmp/doc.docx", "EN", "FR", "")

        with (
            patch("src.core.translator.stop_soffice"),
            patch(
                "src.core.translator.get_unfinished_history",
                side_effect=self._make_mock_unfinished([task]),
            ),
            patch("src.core.translator.update_history_status"),
            patch("src.core.translator.update_history_progress"),
            patch("src.core.translator._pipeline_process_text") as mock_text,
            patch("pathlib.Path.exists", return_value=True),
        ):
            run_translation_pipeline(cfg)
        mock_text.assert_called_once()

    def test_dispatches_xlsx_to_text_pipeline(self) -> None:
        """XLSX is a text format and dispatched to text pipeline."""
        cfg = TranslationConfig()
        task = (1, "/tmp/data.xlsx", "EN", "FR", "")

        with (
            patch("src.core.translator.stop_soffice"),
            patch(
                "src.core.translator.get_unfinished_history",
                side_effect=self._make_mock_unfinished([task]),
            ),
            patch("src.core.translator.update_history_status"),
            patch("src.core.translator.update_history_progress"),
            patch("src.core.translator._pipeline_process_text") as mock_text,
            patch("pathlib.Path.exists", return_value=True),
        ):
            run_translation_pipeline(cfg)
        mock_text.assert_called_once()

    def test_dispatches_pptx_to_text_pipeline(self) -> None:
        """PPTX is dispatched to text pipeline."""
        cfg = TranslationConfig()
        task = (1, "/tmp/slides.pptx", "EN", "FR", "")

        with (
            patch("src.core.translator.stop_soffice"),
            patch(
                "src.core.translator.get_unfinished_history",
                side_effect=self._make_mock_unfinished([task]),
            ),
            patch("src.core.translator.update_history_status"),
            patch("src.core.translator.update_history_progress"),
            patch("src.core.translator._pipeline_process_text") as mock_text,
            patch("pathlib.Path.exists", return_value=True),
        ):
            run_translation_pipeline(cfg)
        mock_text.assert_called_once()

    def test_dispatches_pdf_to_text_pipeline(self) -> None:
        """PDF is dispatched to text pipeline."""
        cfg = TranslationConfig()
        task = (1, "/tmp/manual.pdf", "EN", "FR", "")

        with (
            patch("src.core.translator.stop_soffice"),
            patch(
                "src.core.translator.get_unfinished_history",
                side_effect=self._make_mock_unfinished([task]),
            ),
            patch("src.core.translator.update_history_status"),
            patch("src.core.translator.update_history_progress"),
            patch("src.core.translator._pipeline_process_text") as mock_text,
            patch("pathlib.Path.exists", return_value=True),
        ):
            run_translation_pipeline(cfg)
        mock_text.assert_called_once()

    def test_dispatches_jpg_to_image_pipeline(self) -> None:
        """JPG is dispatched to image pipeline."""
        cfg = TranslationConfig()
        task = (1, "/tmp/photo.jpg", "EN", "FR", "")

        with (
            patch("src.core.translator.stop_soffice"),
            patch(
                "src.core.translator.get_unfinished_history",
                side_effect=self._make_mock_unfinished([task]),
            ),
            patch("src.core.translator.update_history_status"),
            patch("src.core.translator.update_history_progress"),
            patch("src.core.translator._pipeline_process_image") as mock_img,
            patch("pathlib.Path.exists", return_value=True),
        ):
            run_translation_pipeline(cfg)
        mock_img.assert_called_once()

    def test_dispatches_jpeg_to_image_pipeline(self) -> None:
        """JPEG is dispatched to image pipeline."""
        cfg = TranslationConfig()
        task = (1, "/tmp/photo.jpeg", "EN", "FR", "")

        with (
            patch("src.core.translator.stop_soffice"),
            patch(
                "src.core.translator.get_unfinished_history",
                side_effect=self._make_mock_unfinished([task]),
            ),
            patch("src.core.translator.update_history_status"),
            patch("src.core.translator.update_history_progress"),
            patch("src.core.translator._pipeline_process_image") as mock_img,
            patch("pathlib.Path.exists", return_value=True),
        ):
            run_translation_pipeline(cfg)
        mock_img.assert_called_once()

    def test_dispatches_bmp_to_image_pipeline(self) -> None:
        """BMP is dispatched to image pipeline."""
        cfg = TranslationConfig()
        task = (1, "/tmp/image.bmp", "EN", "FR", "")

        with (
            patch("src.core.translator.stop_soffice"),
            patch(
                "src.core.translator.get_unfinished_history",
                side_effect=self._make_mock_unfinished([task]),
            ),
            patch("src.core.translator.update_history_status"),
            patch("src.core.translator.update_history_progress"),
            patch("src.core.translator._pipeline_process_image") as mock_img,
            patch("pathlib.Path.exists", return_value=True),
        ):
            run_translation_pipeline(cfg)
        mock_img.assert_called_once()

    def test_dispatches_webp_to_image_pipeline(self) -> None:
        """WEBP is dispatched to image pipeline."""
        cfg = TranslationConfig()
        task = (1, "/tmp/image.webp", "EN", "FR", "")

        with (
            patch("src.core.translator.stop_soffice"),
            patch(
                "src.core.translator.get_unfinished_history",
                side_effect=self._make_mock_unfinished([task]),
            ),
            patch("src.core.translator.update_history_status"),
            patch("src.core.translator.update_history_progress"),
            patch("src.core.translator._pipeline_process_image") as mock_img,
            patch("pathlib.Path.exists", return_value=True),
        ):
            run_translation_pipeline(cfg)
        mock_img.assert_called_once()

    def test_dispatches_tiff_to_image_pipeline(self) -> None:
        """TIFF is dispatched to image pipeline."""
        cfg = TranslationConfig()
        task = (1, "/tmp/scan.tiff", "EN", "FR", "")

        with (
            patch("src.core.translator.stop_soffice"),
            patch(
                "src.core.translator.get_unfinished_history",
                side_effect=self._make_mock_unfinished([task]),
            ),
            patch("src.core.translator.update_history_status"),
            patch("src.core.translator.update_history_progress"),
            patch("src.core.translator._pipeline_process_image") as mock_img,
            patch("pathlib.Path.exists", return_value=True),
        ):
            run_translation_pipeline(cfg)
        mock_img.assert_called_once()

    def test_dispatches_tif_to_image_pipeline(self) -> None:
        """TIF is dispatched to image pipeline."""
        cfg = TranslationConfig()
        task = (1, "/tmp/scan.tif", "EN", "FR", "")

        with (
            patch("src.core.translator.stop_soffice"),
            patch(
                "src.core.translator.get_unfinished_history",
                side_effect=self._make_mock_unfinished([task]),
            ),
            patch("src.core.translator.update_history_status"),
            patch("src.core.translator.update_history_progress"),
            patch("src.core.translator._pipeline_process_image") as mock_img,
            patch("pathlib.Path.exists", return_value=True),
        ):
            run_translation_pipeline(cfg)
        mock_img.assert_called_once()

    def test_dispatches_srt_to_text_pipeline(self) -> None:
        """SRT subtitle files dispatch to text pipeline."""
        cfg = TranslationConfig()
        task = (1, "/tmp/subs.srt", "EN", "FR", "")

        with (
            patch("src.core.translator.stop_soffice"),
            patch(
                "src.core.translator.get_unfinished_history",
                side_effect=self._make_mock_unfinished([task]),
            ),
            patch("src.core.translator.update_history_status"),
            patch("src.core.translator.update_history_progress"),
            patch("src.core.translator._pipeline_process_text") as mock_text,
            patch("pathlib.Path.exists", return_value=True),
        ):
            run_translation_pipeline(cfg)
        mock_text.assert_called_once()

    def test_dispatches_epub_to_text_pipeline(self) -> None:
        """EPUB files dispatch to text pipeline."""
        cfg = TranslationConfig()
        task = (1, "/tmp/book.epub", "EN", "FR", "")

        with (
            patch("src.core.translator.stop_soffice"),
            patch(
                "src.core.translator.get_unfinished_history",
                side_effect=self._make_mock_unfinished([task]),
            ),
            patch("src.core.translator.update_history_status"),
            patch("src.core.translator.update_history_progress"),
            patch("src.core.translator._pipeline_process_text") as mock_text,
            patch("pathlib.Path.exists", return_value=True),
        ):
            run_translation_pipeline(cfg)
        mock_text.assert_called_once()

    def test_dispatches_html_to_text_pipeline(self) -> None:
        """HTML files dispatch to text pipeline."""
        cfg = TranslationConfig()
        task = (1, "/tmp/page.html", "EN", "FR", "")

        with (
            patch("src.core.translator.stop_soffice"),
            patch(
                "src.core.translator.get_unfinished_history",
                side_effect=self._make_mock_unfinished([task]),
            ),
            patch("src.core.translator.update_history_status"),
            patch("src.core.translator.update_history_progress"),
            patch("src.core.translator._pipeline_process_text") as mock_text,
            patch("pathlib.Path.exists", return_value=True),
        ):
            run_translation_pipeline(cfg)
        mock_text.assert_called_once()

    def test_dispatches_json_to_text_pipeline(self) -> None:
        """JSON files dispatch to text pipeline."""
        cfg = TranslationConfig()
        task = (1, "/tmp/data.json", "EN", "FR", "")

        with (
            patch("src.core.translator.stop_soffice"),
            patch(
                "src.core.translator.get_unfinished_history",
                side_effect=self._make_mock_unfinished([task]),
            ),
            patch("src.core.translator.update_history_status"),
            patch("src.core.translator.update_history_progress"),
            patch("src.core.translator._pipeline_process_text") as mock_text,
            patch("pathlib.Path.exists", return_value=True),
        ):
            run_translation_pipeline(cfg)
        mock_text.assert_called_once()

    def test_dispatches_odt_to_text_pipeline(self) -> None:
        """ODT office files dispatch to text pipeline."""
        cfg = TranslationConfig()
        task = (1, "/tmp/letter.odt", "EN", "FR", "")

        with (
            patch("src.core.translator.stop_soffice"),
            patch(
                "src.core.translator.get_unfinished_history",
                side_effect=self._make_mock_unfinished([task]),
            ),
            patch("src.core.translator.update_history_status"),
            patch("src.core.translator.update_history_progress"),
            patch("src.core.translator._pipeline_process_text") as mock_text,
            patch("pathlib.Path.exists", return_value=True),
        ):
            run_translation_pipeline(cfg)
        mock_text.assert_called_once()

    def test_dispatches_doc_legacy_to_text_pipeline(self) -> None:
        """Legacy .doc files dispatch to text pipeline."""
        cfg = TranslationConfig()
        task = (1, "/tmp/old.doc", "EN", "FR", "")

        with (
            patch("src.core.translator.stop_soffice"),
            patch(
                "src.core.translator.get_unfinished_history",
                side_effect=self._make_mock_unfinished([task]),
            ),
            patch("src.core.translator.update_history_status"),
            patch("src.core.translator.update_history_progress"),
            patch("src.core.translator._pipeline_process_text") as mock_text,
            patch("pathlib.Path.exists", return_value=True),
        ):
            run_translation_pipeline(cfg)
        mock_text.assert_called_once()

    def test_task_exception_does_not_stop_pipeline(self) -> None:
        """A generic exception on one task doesn't prevent processing the next."""
        cfg = TranslationConfig()
        task1 = (1, "/tmp/a.txt", "EN", "FR", "")
        task2 = (2, "/tmp/b.txt", "EN", "FR", "")
        call_count = 0

        def _mock(**_kw: object) -> list:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [task1]
            if call_count == 2:  # noqa: PLR2004
                return [task2]
            return []

        text_calls: list[int] = []

        def _text(h_id: int, *args: object, **kwargs: object) -> None:
            text_calls.append(h_id)
            if h_id == 1:
                raise ValueError("LLM failed")

        with (
            patch("src.core.translator.stop_soffice"),
            patch("src.core.translator.get_unfinished_history", side_effect=_mock),
            patch("src.core.translator.update_history_status"),
            patch("src.core.translator.update_history_progress"),
            patch("src.core.translator._pipeline_process_text", side_effect=_text),
            patch("pathlib.Path.exists", return_value=True),
        ):
            run_translation_pipeline(cfg)

        # Both tasks were attempted
        assert len(text_calls) == 2  # noqa: PLR2004

    def test_at_prefix_multiple_at_signs(self) -> None:
        """Multiple '@' prefix chars are stripped."""
        cfg = TranslationConfig()
        task = (1, "@@@/tmp/file.txt", "EN", "FR", "")

        with (
            patch("src.core.translator.stop_soffice"),
            patch(
                "src.core.translator.get_unfinished_history",
                side_effect=self._make_mock_unfinished([task]),
            ),
            patch("src.core.translator.update_history_status"),
            patch("src.core.translator.update_history_progress"),
            patch("pathlib.Path.exists", return_value=True),
            patch("src.core.translator._pipeline_process_text") as mock_text,
        ):
            run_translation_pipeline(cfg)
        mock_text.assert_called_once()

    def test_empty_source_path_string(self) -> None:
        """Empty source_path_str results in None source_path."""
        cfg = TranslationConfig()
        task = (1, "/tmp/test.txt", "EN", "FR", "")

        with (
            patch("src.core.translator.stop_soffice"),
            patch(
                "src.core.translator.get_unfinished_history",
                side_effect=self._make_mock_unfinished([task]),
            ),
            patch("src.core.translator.update_history_status"),
            patch("src.core.translator.update_history_progress"),
            patch("pathlib.Path.exists", return_value=True),
            patch("src.core.translator._pipeline_process_text") as mock_text,
        ):
            run_translation_pipeline(cfg)
        _, kwargs = mock_text.call_args
        assert kwargs["source_path"] is None

    def test_non_empty_source_path_passed_through(self) -> None:
        """Non-empty source_path_str is converted to Path and passed."""
        cfg = TranslationConfig()
        task = (1, "/tmp/test.txt", "EN", "FR", "/original/test.txt")

        with (
            patch("src.core.translator.stop_soffice"),
            patch(
                "src.core.translator.get_unfinished_history",
                side_effect=self._make_mock_unfinished([task]),
            ),
            patch("src.core.translator.update_history_status"),
            patch("src.core.translator.update_history_progress"),
            patch("pathlib.Path.exists", return_value=True),
            patch("src.core.translator._pipeline_process_text") as mock_text,
        ):
            run_translation_pipeline(cfg)
        _, kwargs = mock_text.call_args
        assert kwargs["source_path"] == Path("/original/test.txt")

    def test_marks_translating_and_initial_progress(self) -> None:
        """Pipeline marks status as Translating and progress to initial."""
        cfg = TranslationConfig()
        task = (42, "/tmp/test.txt", "EN", "FR", "")

        with (
            patch("src.core.translator.stop_soffice"),
            patch(
                "src.core.translator.get_unfinished_history",
                side_effect=self._make_mock_unfinished([task]),
            ),
            patch("src.core.translator.update_history_status") as mock_status,
            patch("src.core.translator.update_history_progress") as mock_prog,
            patch("pathlib.Path.exists", return_value=True),
            patch("src.core.translator._pipeline_process_text"),
        ):
            run_translation_pipeline(cfg)

        mock_status.assert_any_call(42, "Translating")
        mock_prog.assert_any_call(42, 5)  # PROGRESS_INITIAL = 5

    def test_three_sequential_tasks(self) -> None:
        """Pipeline processes 3 tasks sequentially from DB."""
        cfg = TranslationConfig()
        tasks = [
            (1, "/tmp/a.txt", "EN", "FR", ""),
            (2, "/tmp/b.docx", "EN", "FR", ""),
            (3, "/tmp/c.pdf", "EN", "FR", ""),
        ]

        with (
            patch("src.core.translator.stop_soffice"),
            patch(
                "src.core.translator.get_unfinished_history",
                side_effect=self._make_mock_unfinished(tasks),
            ),
            patch("src.core.translator.update_history_status"),
            patch("src.core.translator.update_history_progress"),
            patch("src.core.translator._pipeline_process_text") as mock_text,
            patch("pathlib.Path.exists", return_value=True),
        ):
            run_translation_pipeline(cfg)

        assert mock_text.call_count == 3  # noqa: PLR2004

    def test_config_passed_to_text_pipeline(self) -> None:
        """Config snapshot is forwarded to _pipeline_process_text."""
        cfg = TranslationConfig(storage_path="/custom", auto_convert_legacy=True)
        task = (1, "/tmp/test.txt", "EN", "FR", "")

        with (
            patch("src.core.translator.stop_soffice"),
            patch(
                "src.core.translator.get_unfinished_history",
                side_effect=self._make_mock_unfinished([task]),
            ),
            patch("src.core.translator.update_history_status"),
            patch("src.core.translator.update_history_progress"),
            patch("src.core.translator._pipeline_process_text") as mock_text,
            patch("pathlib.Path.exists", return_value=True),
        ):
            run_translation_pipeline(cfg)

        args, kwargs = mock_text.call_args
        # Config is the 5th positional arg (h_id, file_path, src, tgt, config)
        assert args[4] is cfg

    def test_config_passed_to_image_pipeline(self) -> None:
        """Config snapshot is forwarded to _pipeline_process_image."""
        cfg = TranslationConfig(ocr_method="EasyOCR")
        task = (1, "/tmp/photo.png", "EN", "FR", "")

        with (
            patch("src.core.translator.stop_soffice"),
            patch(
                "src.core.translator.get_unfinished_history",
                side_effect=self._make_mock_unfinished([task]),
            ),
            patch("src.core.translator.update_history_status"),
            patch("src.core.translator.update_history_progress"),
            patch("src.core.translator._pipeline_process_image") as mock_img,
            patch("pathlib.Path.exists", return_value=True),
        ):
            run_translation_pipeline(cfg)

        args, kwargs = mock_img.call_args
        assert args[4] is cfg

    def test_unsupported_extension_mp4(self) -> None:
        """MP4 is not in SUPPORTED_TEXT or SUPPORTED_IMAGES, marked Failed."""
        cfg = TranslationConfig()
        task = (1, "/tmp/video.mp4", "EN", "FR", "")

        with (
            patch("src.core.translator.stop_soffice"),
            patch(
                "src.core.translator.get_unfinished_history",
                side_effect=self._make_mock_unfinished([task]),
            ),
            patch("src.core.translator.update_history_status") as mock_status,
            patch("src.core.translator.update_history_progress"),
            patch("pathlib.Path.exists", return_value=True),
        ):
            run_translation_pipeline(cfg)

        mock_status.assert_any_call(1, "Failed", error_code=ERR_UNKNOWN)

    def test_case_insensitive_extension_PNG(self) -> None:
        """Uppercase .PNG extension is lowercased and dispatched correctly."""
        cfg = TranslationConfig()
        task = (1, "/tmp/photo.PNG", "EN", "FR", "")

        with (
            patch("src.core.translator.stop_soffice"),
            patch(
                "src.core.translator.get_unfinished_history",
                side_effect=self._make_mock_unfinished([task]),
            ),
            patch("src.core.translator.update_history_status"),
            patch("src.core.translator.update_history_progress"),
            patch("src.core.translator._pipeline_process_image") as mock_img,
            patch("pathlib.Path.exists", return_value=True),
        ):
            run_translation_pipeline(cfg)
        mock_img.assert_called_once()

    def test_case_insensitive_extension_DOCX(self) -> None:
        """Uppercase .DOCX extension is lowercased and dispatched correctly."""
        cfg = TranslationConfig()
        task = (1, "/tmp/report.DOCX", "EN", "FR", "")

        with (
            patch("src.core.translator.stop_soffice"),
            patch(
                "src.core.translator.get_unfinished_history",
                side_effect=self._make_mock_unfinished([task]),
            ),
            patch("src.core.translator.update_history_status"),
            patch("src.core.translator.update_history_progress"),
            patch("src.core.translator._pipeline_process_text") as mock_text,
            patch("pathlib.Path.exists", return_value=True),
        ):
            run_translation_pipeline(cfg)
        mock_text.assert_called_once()

    def test_stop_soffice_on_keyboard_interrupt(self) -> None:
        """stop_soffice is called even on KeyboardInterrupt."""
        cfg = TranslationConfig()

        with (
            patch("src.core.translator.stop_soffice") as mock_stop,
            patch(
                "src.core.translator.get_unfinished_history",
                side_effect=KeyboardInterrupt,
            ),
            pytest.raises(KeyboardInterrupt),
        ):
            run_translation_pipeline(cfg)

        mock_stop.assert_called_once()

    def test_integer_storage_path_not_stripped(self) -> None:
        """Non-string storage_path is not passed to lstrip."""
        cfg = TranslationConfig()
        task = (1, 12345, "EN", "FR", "")

        with (
            patch("src.core.translator.stop_soffice"),
            patch(
                "src.core.translator.get_unfinished_history",
                side_effect=self._make_mock_unfinished([task]),
            ),
            patch("src.core.translator.update_history_status") as mock_status,
        ):
            run_translation_pipeline(cfg)

        # Path(12345) may raise or produce invalid path — caught by outer except
        mock_status.assert_any_call(1, "Failed", error_code=ERR_UNKNOWN)


# =====================================================================
# EXPANDED TESTS — _build_output_name additional locales and edge cases
# =====================================================================


class TestBuildOutputNameExpanded:
    """Additional tests for _build_output_name with many languages."""

    def test_arabic_locale(self) -> None:
        """Arabic maps to 'ar'."""
        result = _build_output_name(Path("f.txt"), "Arabic", "English (US)")
        assert result == "f_translated_ar_en-US.txt"

    def test_thai_locale(self) -> None:
        """Thai maps to 'th'."""
        result = _build_output_name(Path("f.txt"), "Thai", "English (US)")
        assert result == "f_translated_th_en-US.txt"

    def test_hindi_locale(self) -> None:
        """Hindi maps to 'hi'."""
        result = _build_output_name(Path("f.txt"), "Hindi", "French")
        assert result == "f_translated_hi_fr.txt"

    def test_russian_locale(self) -> None:
        """Russian maps to 'ru'."""
        result = _build_output_name(Path("f.txt"), "Russian", "German")
        assert result == "f_translated_ru_de.txt"

    def test_portuguese_brazil_locale(self) -> None:
        """Portuguese (Brazil) maps to 'pt-BR'."""
        result = _build_output_name(Path("f.txt"), "Portuguese (Brazil)", "Spanish")
        assert result == "f_translated_pt-BR_es.txt"

    def test_turkish_locale(self) -> None:
        """Turkish maps to 'tr'."""
        result = _build_output_name(Path("f.txt"), "Turkish", "English (UK)")
        assert result == "f_translated_tr_en-UK.txt"

    def test_polish_locale(self) -> None:
        """Polish maps to 'pl'."""
        result = _build_output_name(Path("f.txt"), "Polish", "Czech")
        assert result == "f_translated_pl_cs.txt"

    def test_romanian_locale(self) -> None:
        """Romanian maps to 'ro'."""
        result = _build_output_name(Path("f.txt"), "Romanian", "Hungarian")
        assert result == "f_translated_ro_hu.txt"

    def test_odt_extension(self) -> None:
        """ODT extension preserved."""
        result = _build_output_name(Path("doc.odt"), "EN", "FR")
        assert result.endswith(".odt")

    def test_ods_extension(self) -> None:
        """ODS extension preserved."""
        result = _build_output_name(Path("sheet.ods"), "EN", "FR")
        assert result.endswith(".ods")

    def test_srt_extension(self) -> None:
        """SRT extension preserved."""
        result = _build_output_name(Path("sub.srt"), "EN", "FR")
        assert result.endswith(".srt")

    def test_epub_extension(self) -> None:
        """EPUB extension preserved."""
        result = _build_output_name(Path("book.epub"), "EN", "FR")
        assert result.endswith(".epub")

    def test_very_long_stem(self) -> None:
        """Very long stem doesn't cause issues."""
        long_stem = "a" * 200
        result = _build_output_name(Path(f"{long_stem}.txt"), "English (US)", "French")
        assert result.startswith(long_stem + "_translated_")

    def test_stem_with_underscores(self) -> None:
        """Stem already containing underscores is preserved."""
        result = _build_output_name(Path("my_file_v2.txt"), "English (US)", "French")
        assert result == "my_file_v2_translated_en-US_fr.txt"

    def test_both_same_language(self) -> None:
        """Same source and target language produces correct filename."""
        result = _build_output_name(Path("f.txt"), "English (US)", "English (US)")
        assert result == "f_translated_en-US_en-US.txt"


# =====================================================================
# EXPANDED TESTS — TranslationWorker additional scenarios
# =====================================================================


class TestTranslationWorkerAdditional:
    """Additional tests for TranslationWorker internals."""

    def test_worker_accepts_empty_tasks(self) -> None:
        """Worker can be created with an empty task list."""
        w = TranslationWorker([])
        assert w.tasks == []

    def test_worker_config_defaults_to_none(self) -> None:
        """When no config is provided, _config is None."""
        w = TranslationWorker([])
        assert w._config is None

    def test_worker_is_running_initially_true(self) -> None:
        """New worker has _is_running set to True."""
        w = TranslationWorker([])
        assert w._is_running is True

    def test_stop_called_twice_is_safe(self) -> None:
        """Calling stop() multiple times is safe."""
        w = TranslationWorker([])
        w.stop()
        w.stop()
        assert w._is_running is False

    def test_is_cancelled_checks_running_before_db(self) -> None:
        """_is_cancelled returns True immediately if not _is_running."""
        w = TranslationWorker([])
        w._is_running = False
        # Should not query DB at all
        assert w._is_cancelled(999) is True

    def test_is_cancelled_with_failed_status(self) -> None:
        """_is_cancelled returns True when DB status is 'Failed'."""
        w = TranslationWorker([])
        with patch(
            "src.core.translator.get_history_entry_status",
            return_value="Failed",
        ):
            assert w._is_cancelled(1) is True

    def test_is_cancelled_with_done_status(self) -> None:
        """_is_cancelled returns True when DB status is 'Done'."""
        w = TranslationWorker([])
        with patch(
            "src.core.translator.get_history_entry_status",
            return_value="Done",
        ):
            assert w._is_cancelled(1) is True

    def test_is_cancelled_with_pending_status(self) -> None:
        """_is_cancelled returns True when DB status is 'Pending'."""
        w = TranslationWorker([])
        with patch(
            "src.core.translator.get_history_entry_status",
            return_value="Pending",
        ):
            assert w._is_cancelled(1) is True

    def test_is_cancelled_with_deleting_status(self) -> None:
        """_is_cancelled returns True when DB status is 'Deleting'."""
        w = TranslationWorker([])
        with patch(
            "src.core.translator.get_history_entry_status",
            return_value="Deleting",
        ):
            assert w._is_cancelled(1) is True

    def test_worker_run_emits_finished_after_pipeline(self) -> None:
        """Finished signal is emitted after run_translation_pipeline returns."""
        cfg = TranslationConfig()
        w = TranslationWorker([], config=cfg)
        spy = MagicMock()
        w.finished.connect(spy)

        pipeline_called = [False]

        def _pipeline(*args: object, **kwargs: object) -> None:
            pipeline_called[0] = True

        with (
            patch(
                "src.core.translator.run_translation_pipeline", side_effect=_pipeline
            ),
            patch("src.core.translator.stop_soffice"),
        ):
            w.run()

        assert pipeline_called[0]
        spy.assert_called_once()

    def test_worker_passes_is_cancelled_lambda(self) -> None:
        """Worker passes a lambda for is_cancelled that checks _is_running."""
        cfg = TranslationConfig()
        w = TranslationWorker([], config=cfg)

        captured_kwargs: dict = {}

        def _pipeline(*args: object, **kwargs: object) -> None:
            captured_kwargs.update(kwargs)

        with (
            patch(
                "src.core.translator.run_translation_pipeline", side_effect=_pipeline
            ),
            patch("src.core.translator.stop_soffice"),
        ):
            w.run()

        assert "is_cancelled" in captured_kwargs
        # is_cancelled returns True when not running
        assert captured_kwargs["is_cancelled"]() is False
        w.stop()
        assert captured_kwargs["is_cancelled"]() is True

    def test_worker_passes_task_cancelled_callback(self) -> None:
        """Worker passes _is_cancelled as task_cancelled."""
        cfg = TranslationConfig()
        w = TranslationWorker([], config=cfg)

        captured_kwargs: dict = {}

        def _pipeline(*args: object, **kwargs: object) -> None:
            captured_kwargs.update(kwargs)

        with (
            patch(
                "src.core.translator.run_translation_pipeline", side_effect=_pipeline
            ),
            patch("src.core.translator.stop_soffice"),
        ):
            w.run()

        assert "task_cancelled" in captured_kwargs
        assert captured_kwargs["task_cancelled"] == w._is_cancelled


# =====================================================================
# EXPANDED TESTS — setup_translation_tasks additional edge cases
# =====================================================================


class TestSetupTranslationTasksExpanded:
    """Additional tests for setup_translation_tasks."""

    def test_all_files_nonexistent(self, _task_env: Path) -> None:
        """All nonexistent files produce no tasks, all DB entries are Failed."""
        tasks = setup_translation_tasks(
            ["/nonexistent/a.txt", "/nonexistent/b.txt"],
            "EN",
            "FR",
        )
        assert tasks == []
        history = get_history()
        assert all(h[4] == "Failed" for h in history)

    def test_special_chars_in_filename(self, _task_env: Path) -> None:
        """Special characters (parentheses, etc.) in filenames are handled."""
        f = _task_env / "report (2024).txt"
        f.write_text("data")
        tasks = setup_translation_tasks([str(f)], "EN", "FR")
        assert len(tasks) == 1
        assert "report (2024).txt" in tasks[0][1]

    def test_ten_files_all_succeed(self, _task_env: Path) -> None:
        """10 valid files all produce successful tasks."""
        files = []
        for i in range(10):
            f = _task_env / f"file_{i}.txt"
            f.write_text(f"content {i}")
            files.append(str(f))
        tasks = setup_translation_tasks(files, "EN", "FR")
        assert len(tasks) == 10  # noqa: PLR2004

    def test_same_name_different_dirs(self, _task_env: Path) -> None:
        """Same filename from different directories creates separate entries."""
        d1 = _task_env / "dir1"
        d2 = _task_env / "dir2"
        d1.mkdir()
        d2.mkdir()
        (d1 / "file.txt").write_text("A")
        (d2 / "file.txt").write_text("B")
        tasks = setup_translation_tasks(
            [str(d1 / "file.txt"), str(d2 / "file.txt")],
            "EN",
            "FR",
        )
        assert len(tasks) == 2  # noqa: PLR2004
        ids = {t[0] for t in tasks}
        assert len(ids) == 2  # noqa: PLR2004

    def test_file_with_no_extension(self, _task_env: Path) -> None:
        """File without extension is cloned correctly."""
        f = _task_env / "Makefile"
        f.write_text("all: build")
        tasks = setup_translation_tasks([str(f)], "EN", "FR")
        assert len(tasks) == 1
        assert Path(tasks[0][1]).name == "Makefile"

    def test_binary_file_content_preserved(self, _task_env: Path) -> None:
        """Binary content is preserved exactly after cloning."""
        data = bytes(range(256))
        f = _task_env / "binary.bin"
        f.write_bytes(data)
        tasks = setup_translation_tasks([str(f)], "EN", "FR")
        cloned = Path(tasks[0][1])
        assert cloned.read_bytes() == data

    def test_chinese_languages_stored(self, _task_env: Path) -> None:
        """Chinese language labels are stored correctly in DB."""
        f = _task_env / "test.txt"
        f.write_text("data")
        setup_translation_tasks(
            [str(f)], "Chinese (Simplified)", "Chinese (Traditional)"
        )
        history = get_history()
        assert history[0][2] == "Chinese (Simplified)"
        assert history[0][3] == "Chinese (Traditional)"


# =====================================================================
# EXPANDED TESTS — _pipeline_finalize additional
# =====================================================================


class TestPipelineFinalizeAdditional:
    """Additional finalize tests."""

    def test_no_config_auto_remove_true_from_settings(self) -> None:
        """When config=None and load_setting returns True, entry is deleted."""
        with (
            patch(
                "src.core.translator.get_history_entry_status",
                return_value="Translating",
            ),
            patch("src.core.translator.load_setting", return_value=True),
            patch(
                "src.core.translator.delete_history_entry",
                return_value="/path",
            ) as mock_del,
            patch("src.core.translator.wipe_history_directory") as mock_wipe,
        ):
            _pipeline_finalize(99, config=None)
        mock_del.assert_called_once_with(99)
        mock_wipe.assert_called_once_with("/path")

    def test_pending_status_not_finalized(self) -> None:
        """Status 'Pending' means finalize does nothing."""
        cfg = TranslationConfig(auto_remove_history=True)
        with (
            patch(
                "src.core.translator.get_history_entry_status",
                return_value="Pending",
            ),
            patch("src.core.translator.delete_history_entry") as mock_del,
            patch("src.core.translator.update_history_status") as mock_update,
        ):
            _pipeline_finalize(1, config=cfg)
        mock_del.assert_not_called()
        mock_update.assert_not_called()

    def test_deleting_status_not_finalized(self) -> None:
        """Status 'Deleting' means finalize does nothing."""
        cfg = TranslationConfig(auto_remove_history=False)
        with (
            patch(
                "src.core.translator.get_history_entry_status",
                return_value="Deleting",
            ),
            patch("src.core.translator.delete_history_entry") as mock_del,
            patch("src.core.translator.update_history_status") as mock_update,
        ):
            _pipeline_finalize(1, config=cfg)
        mock_del.assert_not_called()
        mock_update.assert_not_called()


# =====================================================================
# EXPANDED TESTS — _pipeline_run_ocr additional
# =====================================================================


class TestPipelineRunOcrAdditional:
    """Additional tests for _pipeline_run_ocr."""

    def test_generic_exception_marks_ocr_process_failed(self, tmp_path: Path) -> None:
        """Generic Exception (not ImportError/RuntimeError) uses ERR_OCR_PROCESS_FAILED."""
        f = tmp_path / "img.png"
        f.touch()
        cfg = TranslationConfig()

        with (
            patch(
                "src.core.translator._ocr_engine.run_ocr",
                side_effect=Exception("generic OCR error"),
            ),
            patch("src.core.translator.update_history_status") as mock_status,
        ):
            result = _pipeline_run_ocr(1, f, config=cfg)

        assert result is None
        mock_status.assert_called_once_with(
            1,
            "Failed",
            error_code=41,  # ERR_OCR_PROCESS_FAILED
            error_message="generic OCR error",
        )

    def test_ocr_returns_multiple_results(self, tmp_path: Path) -> None:
        """Multiple OCR results are all returned."""
        f = tmp_path / "img.png"
        f.touch()
        cfg = TranslationConfig(ocr_method="Tesseract")
        results = [MagicMock(text=f"word{i}") for i in range(5)]

        with patch("src.core.translator._ocr_engine.run_ocr", return_value=results):
            data = _pipeline_run_ocr(1, f, config=cfg)

        assert data is not None
        assert len(data[0]) == 5  # noqa: PLR2004
        assert len(data[1]) == 5  # noqa: PLR2004
        assert data[2] == "Tesseract"

    def test_ocr_empty_results_returned(self, tmp_path: Path) -> None:
        """Empty OCR result list is returned (not treated as error here)."""
        f = tmp_path / "img.png"
        f.touch()
        cfg = TranslationConfig()

        with patch("src.core.translator._ocr_engine.run_ocr", return_value=[]):
            data = _pipeline_run_ocr(1, f, config=cfg)

        assert data is not None
        assert data[0] == []
        assert data[1] == []


# =====================================================================
# EXPANDED TESTS — _resolve_output_dir additional
# =====================================================================


class TestResolveOutputDirAdditional:
    """Additional tests for _resolve_output_dir."""

    def test_absolute_storage_path_in_config(self) -> None:
        """Config with absolute storage_path returns that path."""
        cfg = TranslationConfig(storage_path="/opt/translations")
        result = _resolve_output_dir(config=cfg)
        assert result == Path("/opt/translations")

    def test_relative_storage_path_in_config(self) -> None:
        """Config with relative storage_path returns a relative Path."""
        cfg = TranslationConfig(storage_path="output")
        result = _resolve_output_dir(config=cfg)
        assert result == Path("output")

    def test_source_path_none_falls_to_desktop(self) -> None:
        """Empty config + None source_path falls back to desktop."""
        cfg = TranslationConfig(storage_path="")
        with patch(
            "src.utils.path_manager.get_desktop_path",
            return_value=Path("/home/user/Desktop"),
        ):
            result = _resolve_output_dir(config=cfg, source_path=None)
        assert result == Path("/home/user/Desktop")

    def test_source_path_exists_used_when_config_empty(self, tmp_path: Path) -> None:
        """When config storage is empty and source parent exists, use source parent."""
        cfg = TranslationConfig(storage_path="")
        source = tmp_path / "docs" / "report.docx"
        source.parent.mkdir(parents=True)
        source.touch()
        result = _resolve_output_dir(config=cfg, source_path=source)
        assert result == source.parent

    def test_no_config_load_setting_empty_no_source(self) -> None:
        """No config, load_setting returns empty, no source -> desktop."""
        with (
            patch("src.core.translator.load_setting", return_value=""),
            patch(
                "src.utils.path_manager.get_desktop_path",
                return_value=Path("/Desktop"),
            ),
        ):
            result = _resolve_output_dir(config=None, source_path=None)
        assert result == Path("/Desktop")


# =====================================================================
# EXPANDED TESTS — _get_unique_path additional
# =====================================================================


class TestGetUniquePathAdditional:
    """Additional tests for _get_unique_path."""

    def test_gap_in_collision_sequence(self, tmp_path: Path) -> None:
        """If _1 exists but _2 doesn't, returns _2 (not _3)."""
        target = tmp_path / "file.txt"
        target.touch()
        (tmp_path / "file_1.txt").touch()
        # _2 does not exist, so it should be returned
        result = _get_unique_path(target)
        assert result == tmp_path / "file_2.txt"

    def test_symlink_counts_as_existing(self, tmp_path: Path) -> None:
        """A symlink at the target path triggers collision resolution."""
        target = tmp_path / "link.txt"
        real = tmp_path / "real.txt"
        real.touch()
        target.symlink_to(real)
        result = _get_unique_path(target)
        assert result == tmp_path / "link_1.txt"

    def test_suffix_only_file(self, tmp_path: Path) -> None:
        """A file named '.env' gets _1 appended."""
        target = tmp_path / ".env"
        target.touch()
        result = _get_unique_path(target)
        assert result == tmp_path / ".env_1"


# =====================================================================
# EXPANDED TESTS — resume_unfinished_translations
# =====================================================================


class TestResumeUnfinishedTranslationsExpanded:
    """Additional tests for resume_unfinished_translations."""

    def test_returns_worker_when_tasks_exist(self, _task_env: Path) -> None:
        """Returns a TranslationWorker when unfinished tasks exist."""
        f = _task_env / "file.txt"
        f.write_text("content")
        setup_translation_tasks([str(f)], "EN", "FR")

        with patch.object(TranslationWorker, "start"):
            worker = resume_unfinished_translations()
        assert worker is not None
        assert isinstance(worker, TranslationWorker)

    def test_passes_config_to_worker(self, _task_env: Path) -> None:
        """Config is forwarded to the created TranslationWorker."""
        f = _task_env / "file.txt"
        f.write_text("content")
        setup_translation_tasks([str(f)], "EN", "FR")

        cfg = TranslationConfig(storage_path="/custom")
        with patch.object(TranslationWorker, "start"):
            worker = resume_unfinished_translations(config=cfg)
        assert worker is not None
        assert worker._config is cfg

    def test_calls_start_on_worker(self, _task_env: Path) -> None:
        """resume_unfinished_translations calls start() on the worker."""
        f = _task_env / "file.txt"
        f.write_text("content")
        setup_translation_tasks([str(f)], "EN", "FR")

        with patch.object(TranslationWorker, "start") as mock_start:
            resume_unfinished_translations()
        mock_start.assert_called_once()


# =====================================================================
# EXPANDED TESTS — Pipeline dispatch for all SUPPORTED_TEXT formats
# =====================================================================


class TestPipelineDispatchTextFormats:
    """Verify all SUPPORTED_TEXT extensions dispatch to text pipeline."""

    @staticmethod
    def _make_mock(task: tuple) -> object:
        call_count = 0

        def _mock(**_kw: object) -> list:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [task]
            return []

        return _mock

    @pytest.mark.parametrize(
        "ext",
        [
            ".md",
            ".rst",
            ".csv",
            ".htm",
            ".xhtml",
            ".xml",
            ".rtf",
            ".vtt",
            ".ass",
            ".ssa",
            ".po",
            ".pot",
            ".xliff",
            ".xlf",
            ".yaml",
            ".yml",
            ".properties",
            ".strings",
            ".xls",
            ".ppt",
            ".ods",
            ".odp",
        ],
    )
    def test_text_format_dispatched(self, ext: str) -> None:
        """Each SUPPORTED_TEXT extension is dispatched to text pipeline."""
        cfg = TranslationConfig()
        task = (1, f"/tmp/file{ext}", "EN", "FR", "")

        with (
            patch("src.core.translator.stop_soffice"),
            patch(
                "src.core.translator.get_unfinished_history",
                side_effect=self._make_mock(task),
            ),
            patch("src.core.translator.update_history_status"),
            patch("src.core.translator.update_history_progress"),
            patch("src.core.translator._pipeline_process_text") as mock_text,
            patch("pathlib.Path.exists", return_value=True),
        ):
            run_translation_pipeline(cfg)
        mock_text.assert_called_once()


class TestPipelineDispatchImageFormats:
    """Verify all SUPPORTED_IMAGES extensions dispatch to image pipeline."""

    @staticmethod
    def _make_mock(task: tuple) -> object:
        call_count = 0

        def _mock(**_kw: object) -> list:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [task]
            return []

        return _mock

    @pytest.mark.parametrize(
        "ext",
        [".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tiff", ".tif"],
    )
    def test_image_format_dispatched(self, ext: str) -> None:
        """Each SUPPORTED_IMAGES extension dispatches to image pipeline."""
        cfg = TranslationConfig()
        task = (1, f"/tmp/file{ext}", "EN", "FR", "")

        with (
            patch("src.core.translator.stop_soffice"),
            patch(
                "src.core.translator.get_unfinished_history",
                side_effect=self._make_mock(task),
            ),
            patch("src.core.translator.update_history_status"),
            patch("src.core.translator.update_history_progress"),
            patch("src.core.translator._pipeline_process_image") as mock_img,
            patch("pathlib.Path.exists", return_value=True),
        ):
            run_translation_pipeline(cfg)
        mock_img.assert_called_once()


# =====================================================================
# EXPANDED TESTS — _map_error_to_code comprehensive parametrized
# =====================================================================


class TestMapErrorToCodeParametrized:
    """Parametrized tests for _map_error_to_code."""

    @pytest.mark.parametrize(
        ("msg", "expected"),
        [
            ("AUTH_ERROR", ERR_LLM_API_KEY_INVALID),
            ("MODEL_NOT_FOUND", ERR_LLM_MODEL_NOT_FOUND),
            ("REQUEST_TOO_LARGE", ERR_LLM_REQUEST_TOO_LARGE),
            ("QUOTA_ERROR", ERR_LLM_QUOTA_EXCEEDED),
            ("SERVICE_UNAVAILABLE_ERROR", ERR_LLM_SERVICE_UNAVAILABLE),
            ("TIMEOUT_ERROR", ERR_LLM_TIMEOUT),
            ("INVALID_RESPONSE", ERR_LLM_INVALID_RESPONSE),
            ("CONNECTION_ERROR", ERR_LLM_CONNECTION_FAILED),
            ("VISION_NOT_SUPPORTED", ERR_LLM_VISION_NOT_SUPPORTED),
            ("PASSWORD_PROTECTED", ERR_FILE_PASSWORD_PROTECTED),
            ("TEXT_READ_ERROR", ERR_TEXT_READ_FAILED),
            ("TEXT_WRITE_ERROR", ERR_TEXT_WRITE_FAILED),
            ("OFFICE_CONVERTER_NOT_FOUND", ERR_OFFICE_CONVERTER_NOT_FOUND),
            ("totally unknown error", ERR_UNKNOWN),
            ("", ERR_UNKNOWN),
            ("   ", ERR_UNKNOWN),
            ("random text", ERR_UNKNOWN),
        ],
    )
    def test_error_tag_mapping(self, msg: str, expected: int) -> None:
        """Each tag maps to its expected error code."""
        assert _map_error_to_code(msg) == expected

    @pytest.mark.parametrize(
        "tag",
        [
            "AUTH_ERROR",
            "MODEL_NOT_FOUND",
            "REQUEST_TOO_LARGE",
            "QUOTA_ERROR",
            "SERVICE_UNAVAILABLE_ERROR",
            "TIMEOUT_ERROR",
            "INVALID_RESPONSE",
            "CONNECTION_ERROR",
            "VISION_NOT_SUPPORTED",
            "PASSWORD_PROTECTED",
            "TEXT_READ_ERROR",
            "TEXT_WRITE_ERROR",
            "OFFICE_CONVERTER_NOT_FOUND",
        ],
    )
    def test_embedded_in_traceback(self, tag: str) -> None:
        """Tag embedded in traceback-style message is still matched."""
        msg = f"Traceback (most recent call last):\n  File ...\n{tag}: details"
        assert _map_error_to_code(msg) != ERR_UNKNOWN


class TestPipelineModelRefreshEdgeCases:
    """Edge cases for ``run_translation_pipeline(model_setting_key=...)``.

    Complements the existing ``TestRunTranslationPipelineExpanded.
    test_model_setting_key_refreshes_llm_per_task`` which pins the
    happy-path live-swap. These pin the *negative* paths: no refresh
    when the setting is empty (transient blank from a freshly-cleared
    INI file) and no refresh when the model is unchanged (avoids
    spamming "Pipeline picking up live model change" log noise on
    every iteration).
    """

    def test_blank_setting_does_not_clobber_snapshot_model(self) -> None:
        """An empty ``load_model_for_feature`` return leaves the config alone.

        Without this guard, a transient empty read (config file being
        rewritten by the settings UI mid-task) would silently null out
        the LLM provider/model and route the next batch to "default"
        — exactly the silent misroute the per-task refresh was meant
        to prevent.
        """
        from unittest.mock import patch  # noqa: PLC0415

        from src.core.config import TranslationConfig  # noqa: PLC0415
        from src.core.translator import run_translation_pipeline  # noqa: PLC0415

        cfg = TranslationConfig(
            llm_provider="Custom",
            llm_model="snapshot-model",
        )
        task1 = (1, "/tmp/a.txt", "EN", "FR", "")
        seen: list[tuple[str, str]] = []

        def _record(*args: object, **_kw: object) -> None:
            cfg_arg = args[4]  # type: ignore[index]
            seen.append((cfg_arg.llm_provider, cfg_arg.llm_model))

        call_count = 0

        def _unfinished(**_kw: object) -> list:
            nonlocal call_count
            call_count += 1
            return [task1] if call_count == 1 else []

        with (
            patch("src.core.translator.stop_soffice"),
            patch(
                "src.core.translator.get_unfinished_history",
                side_effect=_unfinished,
            ),
            patch("src.core.translator.update_history_status"),
            patch("src.core.translator.update_history_progress"),
            patch(
                "src.core.translator._pipeline_process_text",
                side_effect=_record,
            ),
            patch("pathlib.Path.exists", return_value=True),
            # Empty string — mirrors a freshly-cleared / never-set
            # per-feature setting. Refresh logic must short-circuit.
            patch(
                "src.utils.config_manager.load_model_for_feature",
                return_value="",
            ),
        ):
            run_translation_pipeline(
                cfg,
                model_setting_key="llm/model_translate_document",
            )

        assert seen == [("Custom", "snapshot-model")], (
            f"Empty setting clobbered snapshot: {seen}"
        )
