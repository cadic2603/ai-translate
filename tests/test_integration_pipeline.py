"""End-to-end integration tests for the image translation pipeline.

Covers all 7 supported image formats, OCR/LLM/render failure modes,
checkpoint-based resume, cancellation between stages, batch processing,
and error code mapping.
"""

from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage

from src.constants.errors import (
    ERR_IMAGE_INVALID,
    ERR_LLM_API_KEY_INVALID,
    ERR_OCR_ENGINE_NOT_FOUND,
    ERR_OCR_NO_TEXT_FOUND,
    ERR_OCR_PROCESS_FAILED,
)
from src.core.config import TranslationConfig
from src.core.database import get_history, get_history_entry_status, init_db
from src.core.ocr_engine import OCRResult
from src.core.translator import (
    TranslationWorker,
    run_translation_pipeline,
    setup_translation_tasks,
)

# Shared mock data
_OCR_RESULT = OCRResult("Hello", 10, 10, 50, 20, 1.0)
_LLM_PARAGRAPH = {
    "ids": [0],
    "translated_html": "Bonjour",
    "color": "#000000",
    "alignment": "left",
}


@pytest.fixture(autouse=True)
def setup_integration_env(monkeypatch, tmp_path):
    """Sets up a clean database and mock environment."""
    db_file = tmp_path / "integration.db"
    monkeypatch.setattr("src.core.database.get_db_path", lambda: str(db_file))

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    monkeypatch.setattr("src.utils.path_manager.get_app_config_dir", lambda: config_dir)

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr("src.utils.path_manager.get_app_data_dir", lambda: data_dir)

    init_db()
    yield


def _make_image(tmp_path: Path, name: str = "input.png") -> str:
    """Creates a real image file and returns its path as a string."""
    img_path = tmp_path / name
    img = QImage(100, 100, QImage.Format.Format_RGB32)
    img.fill(QColor(Qt.GlobalColor.white))
    img.save(str(img_path))
    return str(img_path)


@pytest.fixture()
def sample_image(tmp_path):
    """Creates a real PNG image file for the pipeline to process."""
    return _make_image(tmp_path)


def _run_worker(tasks, monkeypatch):
    """Runs a TranslationWorker synchronously."""
    TranslationWorker._is_any_worker_running = False
    worker = TranslationWorker(tasks)
    monkeypatch.setattr("time.sleep", lambda _: None)
    worker.run()


def _no_auto_remove(monkeypatch):
    """Disables auto-remove so we can inspect DB state after completion."""
    monkeypatch.setattr(
        "src.core.translator.load_setting",
        lambda k, d: False if "auto_remove" in k else d,
    )


def _force_auto_remove(monkeypatch):
    """Forces auto-remove ON so tests can assert post-success entry deletion.

    The production default for ``auto_remove_history`` is **False**
    (matches the 4 sibling page-level features — Voice / Subtitle /
    Dubbing / Extract Text) so history rows persist after a
    successful run unless the user opts in via Settings.  Tests that
    want to verify the auto-remove cascade fires must opt in
    explicitly via this helper.

    Patches BOTH callsites: ``translator.load_setting`` (used by
    the legacy in-loop read when no config snapshot is passed) AND
    ``utils.config_manager.load_setting`` (used by
    ``TranslationConfig.from_settings()`` which the worker
    constructs internally when given no explicit config).  Without
    the second patch the worker builds a config with
    ``auto_remove_history=False`` and the override never takes effect.
    """

    def _override(k, d):
        return True if "auto_remove" in k else d

    monkeypatch.setattr("src.core.translator.load_setting", _override)
    monkeypatch.setattr("src.utils.config_manager.load_setting", _override)


def _get_error_code(h_id: int) -> int | None:
    """Returns the error_code column for a history entry."""
    from src.core.database import db_transaction  # noqa: PLC0415

    @db_transaction
    def _fetch(cursor, hid):  # noqa: ANN001, ANN202
        cursor.execute("SELECT error_code FROM history WHERE id = ?", (hid,))
        row = cursor.fetchone()
        return row[0] if row else None

    return _fetch(h_id)


# ===================================================================
# Full pipeline success
# ===================================================================


@patch("src.core.translator._ocr_engine.run_ocr")
@patch("src.core.translator._llm_engine.translate_image_content")
@patch("src.core.translator.process_image_translation")
def test_full_image_pipeline_success(
    mock_process,
    mock_llm,
    mock_ocr,
    sample_image,
    monkeypatch,
) -> None:
    """Full OCR → LLM → render pipeline completes and auto-removes history."""
    mock_ocr.return_value = [_OCR_RESULT]
    mock_llm.return_value = [_LLM_PARAGRAPH]
    mock_process.return_value = True

    tasks = setup_translation_tasks([sample_image], "English (US)", "French")
    assert len(tasks) == 1

    _force_auto_remove(monkeypatch)
    _run_worker(tasks, monkeypatch)

    mock_ocr.assert_called_once()
    mock_llm.assert_called_once()
    mock_process.assert_called_once()

    # auto-remove explicitly enabled → entry deleted after success.
    assert len(get_history()) == 0


# ===================================================================
# Image format variants
# ===================================================================


@pytest.mark.parametrize(
    "ext", [".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tiff", ".tif"]
)
@patch("src.core.translator._ocr_engine.run_ocr")
@patch("src.core.translator._llm_engine.translate_image_content")
@patch("src.core.translator.process_image_translation")
def test_image_format_accepted(
    mock_process,
    mock_llm,
    mock_ocr,
    ext,
    tmp_path,
    monkeypatch,
) -> None:
    """All 7 supported image extensions are accepted by the pipeline."""
    mock_ocr.return_value = [_OCR_RESULT]
    mock_llm.return_value = [_LLM_PARAGRAPH]
    mock_process.return_value = True

    img_path = _make_image(tmp_path, f"photo{ext}")
    tasks = setup_translation_tasks([img_path], "English (US)", "French")
    assert len(tasks) == 1

    _force_auto_remove(monkeypatch)
    _run_worker(tasks, monkeypatch)

    mock_ocr.assert_called_once()
    assert len(get_history()) == 0  # auto-removed after success


# ===================================================================
# OCR failure modes
# ===================================================================


@patch("src.core.translator._ocr_engine.run_ocr")
def test_pipeline_failure_ocr(mock_ocr, sample_image, monkeypatch) -> None:
    """OCR failure is correctly handled and recorded as Failed."""
    mock_ocr.side_effect = Exception("OCR_FAILED")

    tasks = setup_translation_tasks([sample_image], "English (US)", "French")
    h_id = tasks[0][0]

    _no_auto_remove(monkeypatch)
    _run_worker(tasks, monkeypatch)

    assert get_history_entry_status(h_id) == "Failed"


@patch("src.core.translator._ocr_engine.run_ocr")
def test_ocr_import_error_sets_engine_not_found(
    mock_ocr,
    sample_image,
    monkeypatch,
) -> None:
    """ImportError during OCR maps to ERR_OCR_ENGINE_NOT_FOUND."""
    mock_ocr.side_effect = ImportError("no tesseract")

    tasks = setup_translation_tasks([sample_image], "English (US)", "French")
    h_id = tasks[0][0]

    _no_auto_remove(monkeypatch)
    _run_worker(tasks, monkeypatch)

    assert get_history_entry_status(h_id) == "Failed"
    assert _get_error_code(h_id) == ERR_OCR_ENGINE_NOT_FOUND


@patch("src.core.translator._ocr_engine.run_ocr")
def test_ocr_runtime_error_sets_engine_not_found(
    mock_ocr,
    sample_image,
    monkeypatch,
) -> None:
    """RuntimeError during OCR maps to ERR_OCR_ENGINE_NOT_FOUND."""
    mock_ocr.side_effect = RuntimeError("tesseract binary missing")

    tasks = setup_translation_tasks([sample_image], "English (US)", "French")
    h_id = tasks[0][0]

    _no_auto_remove(monkeypatch)
    _run_worker(tasks, monkeypatch)

    assert get_history_entry_status(h_id) == "Failed"
    assert _get_error_code(h_id) == ERR_OCR_ENGINE_NOT_FOUND


@patch("src.core.translator._ocr_engine.run_ocr")
def test_ocr_auth_error_sets_api_key_invalid(
    mock_ocr,
    sample_image,
    monkeypatch,
) -> None:
    """AUTH_ERROR during OCR (Google Cloud) maps to ERR_LLM_API_KEY_INVALID."""
    mock_ocr.side_effect = Exception("AUTH_ERROR: invalid key")

    tasks = setup_translation_tasks([sample_image], "English (US)", "French")
    h_id = tasks[0][0]

    _no_auto_remove(monkeypatch)
    _run_worker(tasks, monkeypatch)

    assert get_history_entry_status(h_id) == "Failed"
    assert _get_error_code(h_id) == ERR_LLM_API_KEY_INVALID


@patch("src.core.translator._ocr_engine.run_ocr")
def test_ocr_generic_exception_sets_process_failed(
    mock_ocr,
    sample_image,
    monkeypatch,
) -> None:
    """Generic exception during OCR maps to ERR_OCR_PROCESS_FAILED."""
    mock_ocr.side_effect = Exception("something unexpected")

    tasks = setup_translation_tasks([sample_image], "English (US)", "French")
    h_id = tasks[0][0]

    _no_auto_remove(monkeypatch)
    _run_worker(tasks, monkeypatch)

    assert get_history_entry_status(h_id) == "Failed"
    assert _get_error_code(h_id) == ERR_OCR_PROCESS_FAILED


@patch("src.core.translator._ocr_engine.run_ocr")
def test_ocr_empty_results_sets_no_text_found(
    mock_ocr,
    sample_image,
    monkeypatch,
) -> None:
    """Empty OCR results (no text detected) map to ERR_OCR_NO_TEXT_FOUND."""
    mock_ocr.return_value = []

    tasks = setup_translation_tasks([sample_image], "English (US)", "French")
    h_id = tasks[0][0]

    _no_auto_remove(monkeypatch)
    _run_worker(tasks, monkeypatch)

    assert get_history_entry_status(h_id) == "Failed"
    assert _get_error_code(h_id) == ERR_OCR_NO_TEXT_FOUND


# ===================================================================
# LLM failure modes
# ===================================================================


@patch("src.core.translator._ocr_engine.run_ocr")
@patch("src.core.translator._llm_engine.translate_image_content")
def test_llm_failure_sets_failed(mock_llm, mock_ocr, sample_image, monkeypatch) -> None:
    """LLM translation failure marks the task as Failed."""
    mock_ocr.return_value = [_OCR_RESULT]
    mock_llm.side_effect = ValueError("QUOTA_ERROR")

    tasks = setup_translation_tasks([sample_image], "English (US)", "French")
    h_id = tasks[0][0]

    _no_auto_remove(monkeypatch)
    _run_worker(tasks, monkeypatch)

    assert get_history_entry_status(h_id) == "Failed"


@patch("src.core.translator._ocr_engine.run_ocr")
@patch("src.core.translator._llm_engine.translate_image_content")
def test_llm_auth_error_maps_correctly(
    mock_llm,
    mock_ocr,
    sample_image,
    monkeypatch,
) -> None:
    """AUTH_ERROR from LLM maps to ERR_LLM_API_KEY_INVALID."""
    mock_ocr.return_value = [_OCR_RESULT]
    mock_llm.side_effect = ValueError("AUTH_ERROR")

    tasks = setup_translation_tasks([sample_image], "English (US)", "French")
    h_id = tasks[0][0]

    _no_auto_remove(monkeypatch)
    _run_worker(tasks, monkeypatch)

    assert get_history_entry_status(h_id) == "Failed"
    assert _get_error_code(h_id) == ERR_LLM_API_KEY_INVALID


# ===================================================================
# Image render failure
# ===================================================================


@patch("src.core.translator._ocr_engine.run_ocr")
@patch("src.core.translator._llm_engine.translate_image_content")
@patch("src.core.translator.process_image_translation")
def test_render_failure_sets_image_invalid(
    mock_process,
    mock_llm,
    mock_ocr,
    sample_image,
    monkeypatch,
) -> None:
    """Image rendering failure maps to ERR_IMAGE_INVALID."""
    mock_ocr.return_value = [_OCR_RESULT]
    mock_llm.return_value = [_LLM_PARAGRAPH]
    mock_process.return_value = False  # render failed

    tasks = setup_translation_tasks([sample_image], "English (US)", "French")
    h_id = tasks[0][0]

    _no_auto_remove(monkeypatch)
    _run_worker(tasks, monkeypatch)

    assert get_history_entry_status(h_id) == "Failed"
    assert _get_error_code(h_id) == ERR_IMAGE_INVALID


# ===================================================================
# Cancellation between stages
# ===================================================================


@patch("src.core.translator._ocr_engine.run_ocr")
@patch("src.core.translator._llm_engine.translate_image_content")
def test_global_cancel_after_ocr_skips_llm(
    mock_llm,
    mock_ocr,
    sample_image,
    monkeypatch,
) -> None:
    """Global is_cancelled after OCR prevents LLM from running."""
    mock_ocr.return_value = [_OCR_RESULT]

    tasks = setup_translation_tasks([sample_image], "English (US)", "French")
    h_id = tasks[0][0]

    config = TranslationConfig(auto_remove_history=False)

    # Allow OCR to complete, then signal global cancellation.
    # The _task_cancel closure checks is_cancelled() first, so
    # flipping it to True between OCR and LLM stops the pipeline.
    cancelled = False

    def _ocr_then_cancel(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        nonlocal cancelled
        result = [_OCR_RESULT]
        cancelled = True  # signal stop after OCR finishes
        return result

    mock_ocr.side_effect = _ocr_then_cancel

    run_translation_pipeline(
        config=config,
        is_cancelled=lambda: cancelled,
    )

    mock_llm.assert_not_called()
    assert get_history_entry_status(h_id) == "Translating"


@patch("src.core.translator._ocr_engine.run_ocr")
@patch("src.core.translator._llm_engine.translate_image_content")
@patch("src.core.translator.process_image_translation")
def test_global_cancel_after_llm_skips_render(
    mock_process,
    mock_llm,
    mock_ocr,
    sample_image,
    monkeypatch,
) -> None:
    """Global is_cancelled after LLM prevents render from running."""
    mock_ocr.return_value = [_OCR_RESULT]

    cancelled = False

    def _llm_then_cancel(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        nonlocal cancelled
        cancelled = True
        return [_LLM_PARAGRAPH]

    mock_llm.side_effect = _llm_then_cancel

    tasks = setup_translation_tasks([sample_image], "English (US)", "French")
    h_id = tasks[0][0]

    config = TranslationConfig(auto_remove_history=False)

    run_translation_pipeline(
        config=config,
        is_cancelled=lambda: cancelled,
    )

    mock_process.assert_not_called()
    assert get_history_entry_status(h_id) == "Translating"


# ===================================================================
# Checkpoint resume
# ===================================================================


@patch("src.core.translator._ocr_engine.run_ocr")
@patch("src.core.translator._llm_engine.translate_image_content")
@patch("src.core.translator.process_image_translation")
def test_resume_from_ocr_checkpoint(
    mock_process,
    mock_llm,
    mock_ocr,
    sample_image,
    monkeypatch,
) -> None:
    """Pipeline resumes from OCR checkpoint — skips OCR, runs LLM + render."""
    mock_llm.return_value = [_LLM_PARAGRAPH]
    mock_process.return_value = True

    tasks = setup_translation_tasks([sample_image], "English (US)", "French")

    # Simulate an existing OCR checkpoint
    from src.core.checkpoint import (  # noqa: PLC0415
        get_storage_dir,
        save_ocr_checkpoint,
    )

    storage_dir = get_storage_dir(tasks[0][1])
    save_ocr_checkpoint(storage_dir, [_OCR_RESULT], [_OCR_RESULT], "Tesseract")

    _force_auto_remove(monkeypatch)
    _run_worker(tasks, monkeypatch)

    # OCR should be skipped (checkpoint loaded)
    mock_ocr.assert_not_called()
    # LLM and render should be called
    mock_llm.assert_called_once()
    mock_process.assert_called_once()
    assert len(get_history()) == 0  # auto-removed


@patch("src.core.translator._ocr_engine.run_ocr")
@patch("src.core.translator._llm_engine.translate_image_content")
@patch("src.core.translator.process_image_translation")
def test_resume_from_llm_checkpoint(
    mock_process,
    mock_llm,
    mock_ocr,
    sample_image,
    monkeypatch,
) -> None:
    """Pipeline resumes from LLM checkpoint — skips both OCR and LLM."""
    mock_process.return_value = True

    tasks = setup_translation_tasks([sample_image], "English (US)", "French")

    # Simulate an existing LLM checkpoint
    from src.core.checkpoint import (  # noqa: PLC0415
        get_storage_dir,
        save_llm_checkpoint,
    )

    storage_dir = get_storage_dir(tasks[0][1])
    save_llm_checkpoint(
        storage_dir,
        [_OCR_RESULT],
        ["Bonjour"],
        [_OCR_RESULT],
    )

    _force_auto_remove(monkeypatch)
    _run_worker(tasks, monkeypatch)

    # Both OCR and LLM should be skipped
    mock_ocr.assert_not_called()
    mock_llm.assert_not_called()
    # Render should be called
    mock_process.assert_called_once()
    assert len(get_history()) == 0  # auto-removed


# ===================================================================
# Batch processing
# ===================================================================


@patch("src.core.translator._ocr_engine.run_ocr")
@patch("src.core.translator._llm_engine.translate_image_content")
@patch("src.core.translator.process_image_translation")
def test_batch_multiple_images(
    mock_process,
    mock_llm,
    mock_ocr,
    tmp_path,
    monkeypatch,
) -> None:
    """Multiple image files are processed sequentially in one batch."""
    mock_ocr.return_value = [_OCR_RESULT]
    mock_llm.return_value = [_LLM_PARAGRAPH]
    mock_process.return_value = True

    images = [_make_image(tmp_path, f"img{i}.png") for i in range(3)]
    tasks = setup_translation_tasks(images, "English (US)", "French")
    assert len(tasks) == 3

    _force_auto_remove(monkeypatch)
    _run_worker(tasks, monkeypatch)

    assert mock_ocr.call_count == 3
    assert mock_llm.call_count == 3
    assert mock_process.call_count == 3
    assert len(get_history()) == 0  # all auto-removed


@patch("src.core.translator._ocr_engine.run_ocr")
@patch("src.core.translator._llm_engine.translate_image_content")
@patch("src.core.translator.process_image_translation")
def test_batch_first_fails_second_succeeds(
    mock_process,
    mock_llm,
    mock_ocr,
    tmp_path,
    monkeypatch,
) -> None:
    """First image fails, second succeeds — both are processed."""
    # First call fails, second succeeds
    mock_ocr.side_effect = [
        Exception("OCR_FAILED"),
        [_OCR_RESULT],
    ]
    mock_llm.return_value = [_LLM_PARAGRAPH]
    mock_process.return_value = True

    images = [_make_image(tmp_path, f"img{i}.png") for i in range(2)]
    tasks = setup_translation_tasks(images, "English (US)", "French")
    h_id_1, h_id_2 = tasks[0][0], tasks[1][0]

    config = TranslationConfig(auto_remove_history=False)
    run_translation_pipeline(config=config)

    assert get_history_entry_status(h_id_1) == "Failed"
    assert get_history_entry_status(h_id_2) == "Done"


# ===================================================================
# Config injection
# ===================================================================


@patch("src.core.translator._ocr_engine.run_ocr")
@patch("src.core.translator._llm_engine.translate_image_content")
@patch("src.core.translator.process_image_translation")
def test_config_ocr_method_forwarded(
    mock_process,
    mock_llm,
    mock_ocr,
    sample_image,
    monkeypatch,
) -> None:
    """TranslationConfig.ocr_method is forwarded to run_ocr."""
    mock_ocr.return_value = [_OCR_RESULT]
    mock_llm.return_value = [_LLM_PARAGRAPH]
    mock_process.return_value = True

    setup_translation_tasks([sample_image], "English (US)", "French")

    config = TranslationConfig(ocr_method="EasyOCR")
    run_translation_pipeline(config=config)

    # Verify OCR was called with the configured method
    _, kwargs = mock_ocr.call_args
    assert kwargs.get("method") == "EasyOCR"


@patch("src.core.translator._ocr_engine.run_ocr")
@patch("src.core.translator._llm_engine.translate_image_content")
@patch("src.core.translator.process_image_translation")
def test_keep_history_preserves_entry(
    mock_process,
    mock_llm,
    mock_ocr,
    sample_image,
    monkeypatch,
) -> None:
    """auto_remove_history=False keeps the history entry after success."""
    mock_ocr.return_value = [_OCR_RESULT]
    mock_llm.return_value = [_LLM_PARAGRAPH]
    mock_process.return_value = True

    tasks = setup_translation_tasks([sample_image], "English (US)", "French")
    h_id = tasks[0][0]

    config = TranslationConfig(auto_remove_history=False)
    run_translation_pipeline(config=config)

    assert get_history_entry_status(h_id) == "Done"


@patch("src.core.translator._ocr_engine.run_ocr")
@patch("src.core.translator._llm_engine.translate_image_content")
@patch("src.core.translator.process_image_translation")
def test_src_lang_forwarded_to_ocr(
    mock_process,
    mock_llm,
    mock_ocr,
    sample_image,
    monkeypatch,
) -> None:
    """Source language is forwarded to run_ocr for language-specific models."""
    mock_ocr.return_value = [_OCR_RESULT]
    mock_llm.return_value = [_LLM_PARAGRAPH]
    mock_process.return_value = True

    setup_translation_tasks([sample_image], "Japanese", "English (US)")
    run_translation_pipeline(config=TranslationConfig())

    _, kwargs = mock_ocr.call_args
    assert kwargs.get("src_lang") == "Japanese"
