"""Tests for handling translation failures in the TranslationWorker."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.constants.errors import (
    ERR_FILE_NOT_FOUND,
    ERR_LLM_API_KEY_INVALID,
    ERR_LLM_CONNECTION_FAILED,
    ERR_LLM_INVALID_RESPONSE,
    ERR_LLM_MODEL_NOT_FOUND,
    ERR_LLM_QUOTA_EXCEEDED,
    ERR_LLM_REQUEST_TOO_LARGE,
    ERR_LLM_SERVICE_UNAVAILABLE,
    ERR_LLM_TIMEOUT,
    ERR_LLM_VISION_NOT_SUPPORTED,
    ERR_OCR_NO_TEXT_FOUND,
    ERR_OFFICE_CONVERTER_NOT_FOUND,
    ERR_TEXT_READ_FAILED,
    ERR_TEXT_WRITE_FAILED,
    ERR_UNKNOWN,
)
from src.core.config import TranslationConfig
from src.core.database import (
    add_history_entry,
    get_history,
    get_history_entry_status,
)
from src.core.database import get_history as _db_get_history
from src.core.database import update_history_status as _db_update_status
from src.core.translator import TranslationWorker, setup_translation_tasks


@pytest.fixture(autouse=True)
def _clear_pending_entries():
    """Mark leftover pending entries from the shared session DB as Done.

    Without this, run_translation_pipeline() would pick up stale entries
    from earlier test modules and try to process them with unmocked LLM calls.
    """
    from src.core.database import (  # noqa: PLC0415
        get_unfinished_history,
        update_history_status,
    )

    for h_id, *_ in get_unfinished_history(
        statuses=("Pending", "Translating"),
    ):
        update_history_status(h_id, "Done")
    original_state = TranslationWorker._is_any_worker_running
    TranslationWorker._is_any_worker_running = False
    yield
    TranslationWorker._is_any_worker_running = original_state


def test_translation_worker_failed_status(
    tmp_path: Path,
) -> None:
    """Verifies TranslationWorker sets 'Failed' on LLM error."""
    test_file = tmp_path / "fail_test.png"
    test_file.write_text("dummy")

    h_id = add_history_entry(
        file_name="fail_test.png",
        src="English (US)",
        target="German",
        status="Pending",
        storage_path=str(test_file),
    )

    config = TranslationConfig()

    with (
        patch("src.core.translator._ocr_engine.run_ocr") as mock_ocr,
        patch(
            "src.core.translator._llm_engine.translate_image_content",
        ) as mock_translate,
    ):
        mock_ocr.return_value = [
            MagicMock(text="Hello", x=0, y=0, w=10, h=10),
        ]
        error_msg = "CONNECTION_ERROR: URL can't contain control characters."
        mock_translate.side_effect = ValueError(error_msg)

        worker = TranslationWorker(
            [
                (h_id, str(test_file), "English (US)", "German"),
            ],
            config=config,
        )
        worker.run()

        status = get_history_entry_status(h_id)
        assert status == "Failed"

        history = get_history()
        entry = next(h for h in history if h[0] == h_id)
        assert entry[9] == ERR_LLM_CONNECTION_FAILED


def test_translation_worker_quota_error(
    tmp_path: Path,
) -> None:
    """Verifies TranslationWorker sets ERR_LLM_QUOTA_EXCEEDED."""
    test_file = tmp_path / "quota_test.png"
    test_file.touch()
    h_id = add_history_entry(
        "quota_test.png",
        "En",
        "De",
        "Pending",
        storage_path=str(test_file),
    )

    config = TranslationConfig()

    with (
        patch("src.core.translator._ocr_engine.run_ocr") as mock_ocr,
        patch(
            "src.core.translator._llm_engine.translate_image_content",
        ) as mock_translate,
    ):
        mock_ocr.return_value = [
            MagicMock(text="Hello", x=0, y=0, w=10, h=10),
        ]
        mock_translate.side_effect = ValueError(
            "QUOTA_ERROR",
        )

        worker = TranslationWorker(
            [
                (h_id, str(test_file), "En", "De"),
            ],
            config=config,
        )
        worker.run()

        history = get_history()
        entry = next(h for h in history if h[0] == h_id)
        assert entry[4] == "Failed"
        assert entry[9] == ERR_LLM_QUOTA_EXCEEDED


def test_translation_worker_auth_error(
    tmp_path: Path,
) -> None:
    """Verifies TranslationWorker sets ERR_LLM_API_KEY_INVALID."""
    test_file = tmp_path / "auth_test.png"
    test_file.touch()
    h_id = add_history_entry(
        "auth_test.png",
        "En",
        "De",
        "Pending",
        storage_path=str(test_file),
    )

    config = TranslationConfig()

    with (
        patch("src.core.translator._ocr_engine.run_ocr") as mock_ocr,
        patch(
            "src.core.translator._llm_engine.translate_image_content",
        ) as mock_translate,
    ):
        mock_ocr.return_value = [
            MagicMock(text="Hello", x=0, y=0, w=10, h=10),
        ]
        mock_translate.side_effect = ValueError(
            "AUTH_ERROR",
        )

        worker = TranslationWorker(
            [
                (h_id, str(test_file), "En", "De"),
            ],
            config=config,
        )
        worker.run()

        history = get_history()
        entry = next(h for h in history if h[0] == h_id)
        assert entry[4] == "Failed"
        assert entry[9] == ERR_LLM_API_KEY_INVALID


def test_translation_worker_file_not_found(
    tmp_path: Path,
) -> None:
    """Verifies TranslationWorker sets ERR_FILE_NOT_FOUND."""
    missing_file = tmp_path / "deleted.png"
    h_id = add_history_entry(
        "deleted.png",
        "En",
        "De",
        "Pending",
        storage_path=str(missing_file),
    )

    config = TranslationConfig()

    worker = TranslationWorker(
        [
            (h_id, str(missing_file), "En", "De"),
        ],
        config=config,
    )
    worker.run()

    assert get_history_entry_status(h_id) == "Failed"
    history = get_history()
    entry = next(h for h in history if h[0] == h_id)
    assert entry[9] == ERR_FILE_NOT_FOUND


# --- Text task failure tests ---


def test_translation_worker_text_task_auth_error(
    tmp_path: Path,
) -> None:
    """Verifies text task LLM error sets Failed + error code."""
    test_file = tmp_path / "fail_text.txt"
    test_file.write_text("Hello world")

    h_id = add_history_entry(
        "fail_text.txt",
        "English (US)",
        "French",
        "Pending",
        storage_path=str(test_file),
    )

    config = TranslationConfig()

    with (
        patch(
            "src.core.translator.translate_file",
            side_effect=ValueError("AUTH_ERROR"),
        ),
        patch(
            "src.core.translator.get_active_glossary_sets",
            return_value=[],
        ),
    ):
        worker = TranslationWorker(
            [
                (h_id, str(test_file), "English (US)", "French"),
            ],
            config=config,
        )
        worker.run()

        assert get_history_entry_status(h_id) == "Failed"
        history = get_history()
        entry = next(h for h in history if h[0] == h_id)
        assert entry[9] == ERR_LLM_API_KEY_INVALID


def test_translation_worker_text_task_quota_error(
    tmp_path: Path,
) -> None:
    """Verifies text task QUOTA_ERROR sets correct error code."""
    test_file = tmp_path / "quota_text.txt"
    test_file.write_text("Some content")

    h_id = add_history_entry(
        "quota_text.txt",
        "En",
        "Fr",
        "Pending",
        storage_path=str(test_file),
    )

    config = TranslationConfig()

    with (
        patch(
            "src.core.translator.translate_file",
            side_effect=ValueError("QUOTA_ERROR"),
        ),
        patch(
            "src.core.translator.get_active_glossary_sets",
            return_value=[],
        ),
    ):
        worker = TranslationWorker(
            [
                (h_id, str(test_file), "En", "Fr"),
            ],
            config=config,
        )
        worker.run()

        assert get_history_entry_status(h_id) == "Failed"
        history = get_history()
        entry = next(h for h in history if h[0] == h_id)
        assert entry[9] == ERR_LLM_QUOTA_EXCEEDED


# ---------------------------------------------------------------------------
# Additional image-task LLM error codes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("error_keyword", "expected_code"),
    [
        ("TIMEOUT_ERROR", ERR_LLM_TIMEOUT),
        ("SERVICE_UNAVAILABLE_ERROR", ERR_LLM_SERVICE_UNAVAILABLE),
        ("INVALID_RESPONSE", ERR_LLM_INVALID_RESPONSE),
        ("MODEL_NOT_FOUND", ERR_LLM_MODEL_NOT_FOUND),
        ("REQUEST_TOO_LARGE", ERR_LLM_REQUEST_TOO_LARGE),
        ("VISION_NOT_SUPPORTED", ERR_LLM_VISION_NOT_SUPPORTED),
    ],
)
def test_translation_worker_image_llm_error_codes(
    error_keyword: str,
    expected_code: int,
    tmp_path: Path,
) -> None:
    """Image task: each LLM error keyword maps to the correct error code."""
    test_file = tmp_path / f"img_{error_keyword.lower()}.png"
    test_file.write_text("dummy")

    h_id = add_history_entry(
        test_file.name,
        "En",
        "Fr",
        "Pending",
        storage_path=str(test_file),
    )

    config = TranslationConfig()

    with (
        patch("src.core.translator._ocr_engine.run_ocr") as mock_ocr,
        patch(
            "src.core.translator._llm_engine.translate_image_content"
        ) as mock_translate,
    ):
        mock_ocr.return_value = [MagicMock(text="Hello", x=0, y=0, w=10, h=10)]
        mock_translate.side_effect = ValueError(error_keyword)

        worker = TranslationWorker([(h_id, str(test_file), "En", "Fr")], config=config)
        worker.run()

    assert get_history_entry_status(h_id) == "Failed"
    entry = next(h for h in get_history() if h[0] == h_id)
    assert entry[9] == expected_code


# ---------------------------------------------------------------------------
# Additional text-task error codes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("error_keyword", "expected_code"),
    [
        ("TEXT_READ_ERROR", ERR_TEXT_READ_FAILED),
        ("TEXT_WRITE_ERROR", ERR_TEXT_WRITE_FAILED),
        ("OFFICE_CONVERTER_NOT_FOUND", ERR_OFFICE_CONVERTER_NOT_FOUND),
        ("TIMEOUT_ERROR", ERR_LLM_TIMEOUT),
        ("SERVICE_UNAVAILABLE_ERROR", ERR_LLM_SERVICE_UNAVAILABLE),
        ("INVALID_RESPONSE", ERR_LLM_INVALID_RESPONSE),
        ("MODEL_NOT_FOUND", ERR_LLM_MODEL_NOT_FOUND),
        ("REQUEST_TOO_LARGE", ERR_LLM_REQUEST_TOO_LARGE),
    ],
)
def test_translation_worker_text_task_error_codes(
    error_keyword: str,
    expected_code: int,
    tmp_path: Path,
) -> None:
    """Text task: each error keyword maps to the correct error code."""
    test_file = tmp_path / f"txt_{error_keyword.lower()}.txt"
    test_file.write_text("hello world")

    h_id = add_history_entry(
        test_file.name,
        "En",
        "Fr",
        "Pending",
        storage_path=str(test_file),
    )

    config = TranslationConfig()

    with (
        patch(
            "src.core.translator.translate_file",
            side_effect=ValueError(error_keyword),
        ),
        patch("src.core.translator.get_active_glossary_sets", return_value=[]),
    ):
        worker = TranslationWorker([(h_id, str(test_file), "En", "Fr")], config=config)
        worker.run()

    assert get_history_entry_status(h_id) == "Failed"
    entry = next(h for h in get_history() if h[0] == h_id)
    assert entry[9] == expected_code


# ---------------------------------------------------------------------------
# Unsupported file format
# ---------------------------------------------------------------------------


def test_translation_worker_unsupported_format(tmp_path: Path) -> None:
    """Files with unsupported extensions are set to Failed with ERR_UNKNOWN."""
    test_file = tmp_path / "unsupported_fmt.xyz"
    test_file.write_text("dummy")

    h_id = add_history_entry(
        "unsupported_fmt.xyz",
        "En",
        "Fr",
        "Pending",
        storage_path=str(test_file),
    )

    config = TranslationConfig()

    worker = TranslationWorker([(h_id, str(test_file), "En", "Fr")], config=config)
    worker.run()

    assert get_history_entry_status(h_id) == "Failed"
    entry = next(h for h in get_history() if h[0] == h_id)
    assert entry[9] == ERR_UNKNOWN


# ---------------------------------------------------------------------------
# OCR returns no text
# ---------------------------------------------------------------------------


def test_translation_worker_ocr_empty_results(tmp_path: Path) -> None:
    """Empty OCR results set the task to Failed with ERR_OCR_NO_TEXT_FOUND."""
    test_file = tmp_path / "ocr_empty.png"
    test_file.write_text("dummy")

    h_id = add_history_entry(
        "ocr_empty.png",
        "En",
        "Fr",
        "Pending",
        storage_path=str(test_file),
    )

    config = TranslationConfig()

    with patch("src.core.translator._ocr_engine.run_ocr", return_value=[]):
        worker = TranslationWorker([(h_id, str(test_file), "En", "Fr")], config=config)
        worker.run()

    assert get_history_entry_status(h_id) == "Failed"
    entry = next(h for h in get_history() if h[0] == h_id)
    assert entry[9] == ERR_OCR_NO_TEXT_FOUND


# ---------------------------------------------------------------------------
# Image render failure → ERR_IMAGE_INVALID
# ---------------------------------------------------------------------------


def test_translation_worker_render_failure_sets_image_invalid(
    tmp_path: Path,
) -> None:
    """process_image_translation returning False sets ERR_IMAGE_INVALID."""
    from src.constants.errors import ERR_IMAGE_INVALID  # noqa: PLC0415

    test_file = tmp_path / "render_fail.png"
    test_file.write_text("dummy")

    h_id = add_history_entry(
        "render_fail.png",
        "En",
        "Fr",
        "Pending",
        storage_path=str(test_file),
    )

    config = TranslationConfig()

    with (
        patch("src.core.translator._ocr_engine.run_ocr") as mock_ocr,
        patch("src.core.translator._llm_engine.translate_image_content") as mock_llm,
        patch("src.core.translator.merge_to_paragraphs") as mock_merge,
        patch(
            "src.core.translator.process_image_translation",
            return_value=False,
        ),
        patch("src.core.translator.load_llm_checkpoint", return_value=None),
        patch("src.core.translator.load_ocr_checkpoint", return_value=None),
        patch("src.core.translator.save_ocr_checkpoint"),
        patch("src.core.translator.save_llm_checkpoint"),
        patch("src.core.translator._resolve_output_dir", return_value=tmp_path),
        patch(
            "src.core.translator._get_unique_path",
            return_value=tmp_path / "out.png",
        ),
    ):
        mock_result = MagicMock(text="Hello", x=0, y=0, w=10, h=10)
        mock_ocr.return_value = [mock_result]
        mock_llm.return_value = MagicMock()
        mock_merge.return_value = ([mock_result], ["Hello"], [])

        worker = TranslationWorker([(h_id, str(test_file), "En", "Fr")], config=config)
        worker.run()

    assert get_history_entry_status(h_id) == "Failed"
    entry = next(h for h in get_history() if h[0] == h_id)
    assert entry[9] == ERR_IMAGE_INVALID


# ---------------------------------------------------------------------------
# Image task: resume from LLM checkpoint (skips OCR + LLM)
# ---------------------------------------------------------------------------


def test_translation_worker_resume_from_llm_checkpoint(
    tmp_path: Path,
) -> None:
    """When an LLM checkpoint exists, OCR and LLM are both skipped."""
    test_file = tmp_path / "resume_llm.png"
    test_file.write_text("dummy")

    h_id = add_history_entry(
        "resume_llm.png",
        "En",
        "Fr",
        "Pending",
        storage_path=str(test_file),
    )

    config = TranslationConfig()
    mock_ocr_result = MagicMock(text="Hello", x=0, y=0, w=10, h=10)
    saved_llm = ([mock_ocr_result], ["Bonjour"], [])

    with (
        patch("src.core.translator._ocr_engine.run_ocr") as mock_ocr,
        patch("src.core.translator._llm_engine.translate_image_content") as mock_llm,
        patch("src.core.translator.load_llm_checkpoint", return_value=saved_llm),
        patch(
            "src.core.translator.process_image_translation",
            return_value=True,
        ),
        patch("src.core.translator.clear_checkpoints"),
        patch("src.core.translator._resolve_output_dir", return_value=tmp_path),
        patch(
            "src.core.translator._get_unique_path",
            return_value=tmp_path / "out.png",
        ),
    ):
        worker = TranslationWorker([(h_id, str(test_file), "En", "Fr")], config=config)
        worker.run()

    # OCR and LLM should not have been called
    mock_ocr.assert_not_called()
    mock_llm.assert_not_called()
    # Task should be finalized (Done or auto-removed)
    final_status = get_history_entry_status(h_id)
    assert final_status in ("Done", None)  # None if auto-removed


# ---------------------------------------------------------------------------
# Image task: cancel after OCR (between OCR and LLM steps)
# ---------------------------------------------------------------------------


def test_translation_worker_cancel_after_ocr(
    tmp_path: Path,
) -> None:
    """When cancelled after OCR completes, LLM is not called and task stays Paused."""
    test_file = tmp_path / "cancel_after_ocr.png"
    test_file.write_text("dummy")

    h_id = add_history_entry(
        "cancel_after_ocr.png",
        "En",
        "Fr",
        "Pending",
        storage_path=str(test_file),
    )

    config = TranslationConfig()

    def pause_after_ocr(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        """Simulate user pausing the task after OCR runs."""
        _db_update_status(h_id, "Paused")

    with (
        patch("src.core.translator._ocr_engine.run_ocr") as mock_ocr,
        patch("src.core.translator._llm_engine.translate_image_content") as mock_llm,
        patch("src.core.translator.load_llm_checkpoint", return_value=None),
        patch("src.core.translator.load_ocr_checkpoint", return_value=None),
        patch(
            "src.core.translator.save_ocr_checkpoint",
            side_effect=pause_after_ocr,
        ),
    ):
        mock_result = MagicMock(text="Hello", x=0, y=0, w=10, h=10)
        mock_ocr.return_value = [mock_result]

        worker = TranslationWorker([(h_id, str(test_file), "En", "Fr")], config=config)
        worker.run()

    # LLM should not have been called since task was cancelled
    mock_llm.assert_not_called()
    # Status should remain Paused (not overwritten by the worker)
    assert get_history_entry_status(h_id) == "Paused"


# ---------------------------------------------------------------------------
# Image task: cancel after LLM (between LLM and render steps)
# ---------------------------------------------------------------------------


def test_translation_worker_cancel_after_llm(
    tmp_path: Path,
) -> None:
    """When cancelled after LLM, render is not called and task stays Paused."""
    test_file = tmp_path / "cancel_after_llm.png"
    test_file.write_text("dummy")

    h_id = add_history_entry(
        "cancel_after_llm.png",
        "En",
        "Fr",
        "Pending",
        storage_path=str(test_file),
    )

    config = TranslationConfig()
    mock_ocr_result = MagicMock(text="Hello", x=0, y=0, w=10, h=10)

    def pause_after_llm(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        """Simulate user pausing the task after LLM runs."""
        _db_update_status(h_id, "Paused")

    with (
        patch(
            "src.core.translator._ocr_engine.run_ocr", return_value=[mock_ocr_result]
        ),
        patch("src.core.translator._llm_engine.translate_image_content") as mock_llm,
        patch("src.core.translator.merge_to_paragraphs") as mock_merge,
        patch("src.core.translator.load_llm_checkpoint", return_value=None),
        patch("src.core.translator.load_ocr_checkpoint", return_value=None),
        patch("src.core.translator.save_ocr_checkpoint"),
        patch(
            "src.core.translator.save_llm_checkpoint",
            side_effect=pause_after_llm,
        ),
        patch("src.core.translator.process_image_translation") as mock_render,
    ):
        mock_llm.return_value = MagicMock()
        mock_merge.return_value = ([mock_ocr_result], ["Bonjour"], [])

        worker = TranslationWorker([(h_id, str(test_file), "En", "Fr")], config=config)
        worker.run()

    # Render should not have been called since task was cancelled
    mock_render.assert_not_called()
    # Status should remain Paused
    assert get_history_entry_status(h_id) == "Paused"


# ---------------------------------------------------------------------------
# setup_translation_tasks: shutil.copy2 failure
# ---------------------------------------------------------------------------


def test_setup_translation_tasks_copy_failure(
    tmp_path: Path,
) -> None:
    """When shutil.copy2 fails, the DB entry is marked Failed."""
    src = tmp_path / "doc.txt"
    src.write_text("hello")

    def failing_copy2(src_path, dst_path, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
        raise OSError("Disk full")

    with (
        patch(
            "src.core.translator._path_manager.get_app_data_dir", return_value=tmp_path
        ),
        patch("src.core.translator.shutil.copy2", side_effect=failing_copy2),
    ):
        tasks = setup_translation_tasks([str(src)], "En", "Fr")

    # No tasks returned since clone failed
    assert tasks == []
    # DB entry should exist and be marked Failed
    history = _db_get_history()
    entry = next((h for h in history if h[1] == "doc.txt"), None)
    assert entry is not None
    assert entry[4] == "Failed"
    assert entry[9] == ERR_UNKNOWN


# ---------------------------------------------------------------------------
# _process_text_task: convert_to_modern_format returning False
# ---------------------------------------------------------------------------


def test_translation_worker_convert_to_modern_fails_continues(
    tmp_path: Path,
) -> None:
    """When convert_to_modern_format returns False, translation continues."""
    # Create a .doc file (legacy format) to trigger conversion path
    test_file = tmp_path / "legacy.doc"
    test_file.write_bytes(b"\xd0\xcf\x11\xe0dummy content")  # Fake OLE2 header

    h_id = add_history_entry(
        "legacy.doc",
        "En",
        "Fr",
        "Pending",
        storage_path=str(test_file),
    )

    # Enable auto-convert so the conversion path is exercised
    config = TranslationConfig(auto_convert_legacy=True, auto_convert_odf=True)

    with (
        patch("src.core.translator.translate_file", return_value=True) as mock_tf,
        patch("src.core.translator.convert_to_modern_format", return_value=False),
        patch("src.core.translator.get_active_glossary_sets", return_value=[]),
    ):
        worker = TranslationWorker([(h_id, str(test_file), "En", "Fr")], config=config)
        worker.run()

    # translate_file should still have been called with the original file path
    mock_tf.assert_called_once()
    call_args = mock_tf.call_args
    # The first positional arg is the file_path; it should still be the .doc
    assert call_args.args[0].suffix == ".doc"


# ---------------------------------------------------------------------------
# _pipeline_finalize: non-Translating statuses → no DB update
# ---------------------------------------------------------------------------


def test_pipeline_finalize_done_status_no_update(tmp_path: Path) -> None:
    """_pipeline_finalize with status 'Done' → no DB update occurs."""
    from src.core.translator import _pipeline_finalize  # noqa: PLC0415

    test_file = tmp_path / "finalize_done.txt"
    test_file.write_text("content")

    h_id = add_history_entry(
        "finalize_done.txt",
        "En",
        "Fr",
        "Done",
        storage_path=str(test_file),
    )

    config = TranslationConfig(auto_remove_history=False)
    _pipeline_finalize(h_id, config)

    # Status should remain "Done" — _pipeline_finalize early-returns
    # because "Done" is not in (STATUS_TRANSLATING, STATUS_FAILED).
    assert get_history_entry_status(h_id) == "Done"


def test_pipeline_finalize_paused_status_no_update(tmp_path: Path) -> None:
    """_pipeline_finalize with status 'Paused' → no DB update occurs."""
    from src.core.translator import _pipeline_finalize  # noqa: PLC0415

    test_file = tmp_path / "finalize_paused.txt"
    test_file.write_text("content")

    h_id = add_history_entry(
        "finalize_paused.txt",
        "En",
        "Fr",
        "Paused",
        storage_path=str(test_file),
    )

    config = TranslationConfig(auto_remove_history=False)
    _pipeline_finalize(h_id, config)

    # Status should remain "Paused"
    assert get_history_entry_status(h_id) == "Paused"


def test_pipeline_finalize_pending_status_no_update(tmp_path: Path) -> None:
    """_pipeline_finalize with status 'Pending' → no DB update occurs."""
    from src.core.translator import _pipeline_finalize  # noqa: PLC0415

    test_file = tmp_path / "finalize_pending.txt"
    test_file.write_text("content")

    h_id = add_history_entry(
        "finalize_pending.txt",
        "En",
        "Fr",
        "Pending",
        storage_path=str(test_file),
    )

    # Manually move to Done so the _clear_pending_entries fixture won't
    # interfere, then set back to Pending for the actual test.
    _db_update_status(h_id, "Done")
    _db_update_status(h_id, "Pending")

    config = TranslationConfig(auto_remove_history=False)
    _pipeline_finalize(h_id, config)

    # Status should remain "Pending"
    assert get_history_entry_status(h_id) == "Pending"

    # Clean up: mark as Done to avoid interference with other tests
    _db_update_status(h_id, "Done")


# ---------------------------------------------------------------------------
# setup_translation_tasks: duplicate files
# ---------------------------------------------------------------------------


def test_setup_translation_tasks_duplicate_files(tmp_path: Path) -> None:
    """Passing the same file path twice creates two separate DB entries."""
    src = tmp_path / "duplicate.txt"
    src.write_text("hello")

    with patch(
        "src.core.translator._path_manager.get_app_data_dir", return_value=tmp_path
    ):
        tasks = setup_translation_tasks([str(src), str(src)], "En", "Fr")

    # Two separate entries should be created
    assert len(tasks) == 2  # noqa: PLR2004
    h_id_1 = tasks[0][0]
    h_id_2 = tasks[1][0]
    # They should have different history IDs
    assert h_id_1 != h_id_2
    # Both should be Pending
    assert get_history_entry_status(h_id_1) == "Pending"
    assert get_history_entry_status(h_id_2) == "Pending"

    # Clean up: mark as Done
    _db_update_status(h_id_1, "Done")
    _db_update_status(h_id_2, "Done")


# ---------------------------------------------------------------------------
# run_translation_pipeline: MemoryError handling
# ---------------------------------------------------------------------------


def test_run_translation_pipeline_memory_error(tmp_path: Path) -> None:
    """MemoryError during translate_file → task marked Failed, pipeline continues."""
    from src.core.translator import run_translation_pipeline  # noqa: PLC0415

    # Create two text files — first will raise MemoryError, second succeeds
    file_1 = tmp_path / "memory_error.txt"
    file_1.write_text("some text")
    file_2 = tmp_path / "normal.txt"
    file_2.write_text("other text")

    h_id_1 = add_history_entry(
        "memory_error.txt",
        "En",
        "Fr",
        "Pending",
        storage_path=str(file_1),
    )
    h_id_2 = add_history_entry(
        "normal.txt",
        "En",
        "Fr",
        "Pending",
        storage_path=str(file_2),
    )

    config = TranslationConfig(auto_remove_history=False)

    call_count = 0

    def side_effect_translate(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        """First call raises MemoryError, second returns True."""
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise MemoryError("out of memory")
        return True

    with (
        patch(
            "src.core.translator.translate_file",
            side_effect=side_effect_translate,
        ),
        patch("src.core.translator.get_active_glossary_sets", return_value=[]),
    ):
        run_translation_pipeline(config)

    # First task should be Failed
    assert get_history_entry_status(h_id_1) == "Failed"
    entry_1 = next(h for h in get_history() if h[0] == h_id_1)
    assert entry_1[9] == ERR_UNKNOWN

    # Second task should be Done (pipeline continued after MemoryError)
    status_2 = get_history_entry_status(h_id_2)
    assert status_2 in ("Done", None)  # None if auto-removed


def test_run_translation_pipeline_memory_error_in_process_image(
    tmp_path: Path,
) -> None:
    """MemoryError bubbling from _pipeline_process_image → Failed + continues."""
    from src.core.translator import run_translation_pipeline  # noqa: PLC0415

    img_file = tmp_path / "oom_image.png"
    img_file.write_text("dummy")

    txt_file = tmp_path / "after_oom.txt"
    txt_file.write_text("content")

    h_id_img = add_history_entry(
        "oom_image.png",
        "En",
        "Fr",
        "Pending",
        storage_path=str(img_file),
    )
    h_id_txt = add_history_entry(
        "after_oom.txt",
        "En",
        "Fr",
        "Pending",
        storage_path=str(txt_file),
    )

    config = TranslationConfig(auto_remove_history=False)

    with (
        patch(
            "src.core.translator._pipeline_process_image",
            side_effect=MemoryError("out of memory"),
        ),
        patch(
            "src.core.translator.translate_file",
            return_value=True,
        ),
        patch("src.core.translator.get_active_glossary_sets", return_value=[]),
    ):
        run_translation_pipeline(config)

    # Image task should be Failed (caught by outer MemoryError handler)
    assert get_history_entry_status(h_id_img) == "Failed"
    entry_img = next(h for h in get_history() if h[0] == h_id_img)
    assert entry_img[9] == ERR_UNKNOWN

    # Text task should complete (pipeline continued to next task)
    status_txt = get_history_entry_status(h_id_txt)
    assert status_txt in ("Done", None)  # None if auto-removed
