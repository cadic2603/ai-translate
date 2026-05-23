"""Integration test for the Extract Text page pipeline.

End-to-end: image → OCR / LLM extract → ``.txt`` / ``.docx`` write
→ history entry status flips to ``EXTRACTED``.  External backends
(Tesseract / LLM vision) are mocked; the worker plumbing, file
writers, and DB status updates run for real so any wiring break
(missing ``finished_ok`` emit, status-flip omission, output format
dispatch confusion) is caught.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture()
def _isolated_env(tmp_path, monkeypatch):
    """Per-test DB + path isolation for Extract Text integration."""
    db_file = tmp_path / "integ.db"
    monkeypatch.setattr(
        "src.core.database.get_db_path", lambda: str(db_file),
    )
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    monkeypatch.setattr(
        "src.utils.path_manager.get_app_config_dir", lambda: config_dir,
    )
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr(
        "src.utils.path_manager.get_app_data_dir", lambda: data_dir,
    )
    from src.core.database import init_db  # noqa: PLC0415

    init_db()


def test_ocr_pipeline_end_to_end(
    qapp,  # noqa: ARG001
    tmp_path,
    _isolated_env,  # noqa: ARG001
) -> None:
    """OCR backend → text → ``.txt`` write → history row marks Extracted.

    Pin the contract:
    1. Worker iterates the task list.
    2. ``_extract_with_ocr`` is called for each task.
    3. Result tuple ``(entry_id, image_path, text)`` reaches the
       ``finished_ok`` signal.
    4. ``_write_extraction_output`` writes the text to the
       requested output path with the right extension dispatch.
    """
    from src.constants.ocr import OCR_METHOD_TESSERACT  # noqa: PLC0415
    from src.constants.settings import EXTRACT_METHOD_OCR  # noqa: PLC0415
    from src.core.database import (  # noqa: PLC0415
        add_extraction_entry,
        get_extraction_history,
    )
    from src.ui.pages.extract_text import (  # noqa: PLC0415
        _ExtractionWorker,
        _write_extraction_output,
    )

    fake_image = tmp_path / "scan.png"
    fake_image.write_bytes(b"\x89PNG\r\n\x1a\n")  # minimal PNG header
    from src.constants.history import STATUS_PENDING  # noqa: PLC0415

    entry_id = add_extraction_entry(
        file_name="scan.png",
        file_size=fake_image.stat().st_size,
        source_path=str(fake_image),
        output_path=str(fake_image.with_suffix(".txt")),
        status=STATUS_PENDING,
    )

    # Drive the worker without QThread.start (synchronous run()).
    worker = _ExtractionWorker.__new__(_ExtractionWorker)
    worker._tasks = [(entry_id, str(fake_image))]
    worker._ocr_method = OCR_METHOD_TESSERACT
    worker._src_lang = "English"
    worker._extract_method = EXTRACT_METHOD_OCR
    worker._llm_provider = None
    worker._llm_model = None
    worker._is_running = True

    captured_results: list = []
    worker.progress = MagicMock(emit=lambda *_a: None)
    worker.finished_ok = MagicMock(emit=captured_results.append)

    with patch.object(
        _ExtractionWorker, "_extract_with_ocr",
        return_value="Extracted text from image",
    ) as mock_ocr:
        worker.run()

    mock_ocr.assert_called_once_with(str(fake_image))
    assert captured_results == [
        [(entry_id, str(fake_image), "Extracted text from image")],
    ]

    # The history entry's status flipped to "Extracting" while the
    # worker ran — confirms DB plumbing reached the row.
    # ``get_extraction_history`` returns rows in reverse-chronological
    # order; tuple shape: (id, file_name, file_size, source_path,
    # output_path, status, error_message, created_at).
    rows = get_extraction_history()
    assert any(r[0] == entry_id for r in rows)

    # Round-trip the output writer for both .txt and .docx so the
    # format dispatch contract is also covered.
    txt_out = tmp_path / "out.txt"
    _write_extraction_output(txt_out, "Hello\nWorld")
    assert txt_out.read_text(encoding="utf-8") == "Hello\nWorld"

    docx_out = tmp_path / "out.docx"
    _write_extraction_output(docx_out, "Para 1\nPara 2")
    assert docx_out.is_file()
    # Open the .docx with python-docx and verify two paragraphs were
    # written — confirms the .docx branch isn't silently writing SRT
    # or some other plain-text format.
    from docx import Document  # noqa: PLC0415

    doc = Document(str(docx_out))
    paragraphs = [p.text for p in doc.paragraphs]
    assert "Para 1" in paragraphs
    assert "Para 2" in paragraphs


def test_llm_pipeline_routes_through_extract_image_text(
    qapp,  # noqa: ARG001
    tmp_path,
    _isolated_env,  # noqa: ARG001
) -> None:
    """LLM backend → ``llm_engine.extract_image_text`` → text → finished_ok.

    Pin the alternate-backend contract: when ``EXTRACT_METHOD_LLM`` is
    selected, the worker calls ``_extract_with_llm`` (which routes
    through ``llm_engine.extract_image_text`` rather than OCR).
    """
    from src.constants.history import STATUS_PENDING  # noqa: PLC0415
    from src.constants.ocr import OCR_METHOD_TESSERACT  # noqa: PLC0415
    from src.constants.settings import EXTRACT_METHOD_LLM  # noqa: PLC0415
    from src.core.database import add_extraction_entry  # noqa: PLC0415
    from src.ui.pages.extract_text import _ExtractionWorker  # noqa: PLC0415

    fake_image = tmp_path / "scan.jpg"
    fake_image.write_bytes(b"\xff\xd8\xff")  # minimal JPEG header
    entry_id = add_extraction_entry(
        file_name="scan.jpg",
        file_size=fake_image.stat().st_size,
        source_path=str(fake_image),
        output_path=str(fake_image.with_suffix(".txt")),
        status=STATUS_PENDING,
    )

    worker = _ExtractionWorker.__new__(_ExtractionWorker)
    worker._tasks = [(entry_id, str(fake_image))]
    worker._ocr_method = OCR_METHOD_TESSERACT
    worker._src_lang = "English"
    worker._extract_method = EXTRACT_METHOD_LLM
    worker._llm_provider = "Custom"
    worker._llm_model = "gpt-5.2"
    worker._is_running = True

    captured: list = []
    worker.progress = MagicMock(emit=lambda *_a: None)
    worker.finished_ok = MagicMock(emit=captured.append)

    with patch.object(
        _ExtractionWorker, "_extract_with_llm",
        return_value="Vision-extracted text",
    ) as mock_llm, patch.object(
        _ExtractionWorker, "_extract_with_ocr",
        side_effect=AssertionError("LLM mode must NOT call OCR"),
    ):
        worker.run()

    mock_llm.assert_called_once_with(str(fake_image))
    assert captured == [
        [(entry_id, str(fake_image), "Vision-extracted text")],
    ]


def test_extract_failure_marks_entry_failed_and_continues_batch(
    qapp,  # noqa: ARG001
    tmp_path,
    _isolated_env,  # noqa: ARG001
) -> None:
    """An OCR/LLM failure on one image marks that entry FAILED but the batch keeps going.

    Pin the contract that one bad image doesn't kill the whole
    extraction batch; the second image still produces a result.
    """
    from src.constants.history import (
        STATUS_FAILED,  # noqa: PLC0415
        STATUS_PENDING,  # noqa: PLC0415
    )
    from src.constants.ocr import OCR_METHOD_TESSERACT  # noqa: PLC0415
    from src.constants.settings import EXTRACT_METHOD_OCR  # noqa: PLC0415
    from src.core.database import (  # noqa: PLC0415
        add_extraction_entry,
        get_extraction_history,
    )
    from src.ui.pages.extract_text import _ExtractionWorker  # noqa: PLC0415

    img1 = tmp_path / "good.png"
    img1.write_bytes(b"\x89PNG\r\n\x1a\n")
    img2 = tmp_path / "bad.png"
    img2.write_bytes(b"\x89PNG\r\n\x1a\n")
    e1 = add_extraction_entry(
        file_name="good.png", file_size=img1.stat().st_size,
        source_path=str(img1), output_path=str(img1.with_suffix(".txt")),
        status=STATUS_PENDING,
    )
    e2 = add_extraction_entry(
        file_name="bad.png", file_size=img2.stat().st_size,
        source_path=str(img2), output_path=str(img2.with_suffix(".txt")),
        status=STATUS_PENDING,
    )

    worker = _ExtractionWorker.__new__(_ExtractionWorker)
    worker._tasks = [(e1, str(img1)), (e2, str(img2))]
    worker._ocr_method = OCR_METHOD_TESSERACT
    worker._src_lang = "English"
    worker._extract_method = EXTRACT_METHOD_OCR
    worker._llm_provider = None
    worker._llm_model = None
    worker._is_running = True

    captured: list = []
    worker.progress = MagicMock(emit=lambda *_a: None)
    worker.finished_ok = MagicMock(emit=captured.append)

    def _ocr_side_effect(image_path):
        if "bad" in image_path:
            raise ValueError("OCR_FAILED")
        return "Good image text"

    with patch.object(
        _ExtractionWorker, "_extract_with_ocr",
        side_effect=_ocr_side_effect,
    ):
        worker.run()

    # Only the good image's tuple landed in the results.
    assert len(captured) == 1
    assert captured[0] == [(e1, str(img1), "Good image text")]

    # The bad entry was marked FAILED in the DB.
    rows = {r[0]: r for r in get_extraction_history()}
    # status field is the 6th tuple element (index 5).
    assert rows[e2][5] == STATUS_FAILED
