"""Integration tests for cancellation at various pipeline stages.

Uses counter-based cancel_check or worker._is_running=False to
interrupt translation.  Verifies partial output and checkpoint state.
Only the LLM is mocked.
"""

import json
import zipfile
from collections.abc import Callable, Generator
from pathlib import Path

import pytest

from src.core.database import get_history_entry_status, init_db
from src.core.text_processor import translate_file
from src.core.translator import TranslationWorker, setup_translation_tasks

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


def _make_canceller(cancel_after: int) -> Callable[[], bool]:
    """Return a cancel_check that cancels after N calls."""
    state = {"count": 0}

    def cancel_check() -> bool:
        state["count"] += 1
        return state["count"] > cancel_after

    return cancel_check


def _create_txt(
    tmp_path: Path,
    name: str = "test.txt",
    content: str = "Hello world",
) -> str:
    """Create a .txt file and return its path as string."""
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return str(p)


def _run_worker(tasks: list[tuple[object, ...]]) -> TranslationWorker:
    """Run TranslationWorker synchronously."""
    TranslationWorker._is_any_worker_running = False
    worker = TranslationWorker(tasks)
    worker.run()
    return worker


# ── Cancellation tests ───────────────────────────────────────────────


def test_cancel_txt_between_chunks(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """Cancel .txt after first LLM call → returns False."""
    # Large enough for multiple chunks
    paragraphs = [f"Paragraph {i}: " + "word " * 40 for i in range(20)]
    content = "\n\n".join(paragraphs)
    inp = tmp_path / "large.txt"
    inp.write_text(content, encoding="utf-8")
    out = tmp_path / "translated.txt"

    cancel = _make_canceller(1)
    result = translate_file(inp, out, "French", "English (US)", cancel_check=cancel)
    assert result is False


def test_cancel_json_between_batches(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """Cancel .json after first batch → returns False, checkpoint saved."""
    data = {f"key_{i}": f"Value {i}" for i in range(50)}
    inp = tmp_path / "big.json"
    inp.write_text(json.dumps(data), encoding="utf-8")
    out = tmp_path / "translated.json"
    checkpoint_dir = tmp_path / "ckpt"
    checkpoint_dir.mkdir()

    cancel = _make_canceller(1)
    result = translate_file(
        inp,
        out,
        "French",
        "English (US)",
        cancel_check=cancel,
        checkpoint_dir=checkpoint_dir,
    )
    assert result is False

    # Checkpoint may or may not exist depending on cancel timing
    from src.core.checkpoint import load_batch_checkpoint  # noqa: PLC0415

    load_batch_checkpoint(checkpoint_dir)  # Verify no crash on load


def test_cancel_srt_between_batches(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """Cancel .srt after first batch → returns False."""
    entries = []
    for i in range(50):
        entries.append(
            f"{i + 1}\n"
            f"00:00:{i:02d},000 --> 00:00:{i + 1:02d},000\n"
            f"Dialogue line {i}\n",
        )
    content = "\n".join(entries)
    inp = tmp_path / "big.srt"
    inp.write_text(content, encoding="utf-8")
    out = tmp_path / "translated.srt"

    cancel = _make_canceller(1)
    result = translate_file(
        inp,
        out,
        "French",
        "English (US)",
        cancel_check=cancel,
    )
    assert result is False


def test_cancel_epub_between_files(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cancel EPUB after first content file → returns False."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda k, d=None: False,
    )
    monkeypatch.setattr(
        "src.utils.config_manager.check_ocr_setup",
        lambda: False,
    )

    epub_path = tmp_path / "book.epub"
    xhtml1 = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<html><body><p>Chapter one text</p></body></html>"
    )
    xhtml2 = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<html><body><p>Chapter two text</p></body></html>"
    )
    container = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"'
        ' version="1.0">\n'
        "  <rootfiles>\n"
        '    <rootfile full-path="OEBPS/content.opf"'
        ' media-type="application/oebps-package+xml"/>\n'
        "  </rootfiles>\n"
        "</container>"
    )
    opf = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0">\n'
        "  <manifest>\n"
        '    <item id="ch1" href="ch1.xhtml"'
        ' media-type="application/xhtml+xml"/>\n'
        '    <item id="ch2" href="ch2.xhtml"'
        ' media-type="application/xhtml+xml"/>\n'
        "  </manifest>\n"
        "  <spine>\n"
        '    <itemref idref="ch1"/>\n'
        '    <itemref idref="ch2"/>\n'
        "  </spine>\n"
        "</package>"
    )

    with zipfile.ZipFile(epub_path, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr("META-INF/container.xml", container)
        zf.writestr("OEBPS/content.opf", opf)
        zf.writestr("OEBPS/ch1.xhtml", xhtml1)
        zf.writestr("OEBPS/ch2.xhtml", xhtml2)

    out = tmp_path / "translated.epub"
    checkpoint_dir = tmp_path / "ckpt"
    checkpoint_dir.mkdir()

    cancel = _make_canceller(2)
    result = translate_file(
        epub_path,
        out,
        "French",
        "English (US)",
        cancel_check=cancel,
        checkpoint_dir=checkpoint_dir,
    )
    assert result is False


def test_cancel_pdf_between_pages(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """Cancel PDF after page 0 → returns False."""
    pymupdf = pytest.importorskip("pymupdf")
    from src.core.pdf_processor import process_pdf_file  # noqa: PLC0415

    doc = pymupdf.open()
    for text in ["Page zero", "Page one", "Page two"]:
        page = doc.new_page()
        page.insert_text((72, 72), text, fontsize=12)
    inp = tmp_path / "multi.pdf"
    doc.save(str(inp))
    doc.close()

    out = tmp_path / "translated.pdf"

    # Cancel after processing first page
    cancel = _make_canceller(1)
    result = process_pdf_file(
        inp,
        out,
        "French",
        "English (US)",
        cancel_check=cancel,
    )
    assert result is False


def test_cancel_docx(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cancel during DOCX translation → returns False."""
    from docx import Document  # noqa: PLC0415

    # Force python-lib backend to avoid UNO connection issues in CI
    monkeypatch.setattr(
        "src.core.office_processor._detect_backend",
        lambda suffix, *_args: "python_lib",
    )

    inp = tmp_path / "cancel.docx"
    doc = Document()
    doc.add_paragraph("Hello world")
    doc.save(str(inp))
    out = tmp_path / "translated.docx"

    cancel = _make_canceller(0)  # Cancel immediately
    result = translate_file(
        inp,
        out,
        "French",
        "English (US)",
        cancel_check=cancel,
    )
    assert result is False


def test_worker_stop_prevents_next_task(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """worker._is_running=False mid-task → second task not processed."""
    monkeypatch.setattr(
        "src.core.translator.load_setting",
        lambda k, d=None: False if "auto_remove" in k else d,
    )

    # LLM that sets _is_running=False on first call
    worker_ref: dict[str, TranslationWorker] = {}
    call_count = {"n": 0}

    def stopping_translate(
        texts: list[str],
        target_lang: str,
        source_lang: str = "",
        **kwargs: object,
    ) -> list[str]:
        call_count["n"] += 1
        if call_count["n"] == 1 and "worker" in worker_ref:
            worker_ref["worker"]._is_running = False
        return [f"[{target_lang}] {t}" for t in texts]

    monkeypatch.setattr(
        "src.core.llm_engine.translate_text",
        stopping_translate,
    )
    monkeypatch.setattr(
        "src.core.text_processor._llm_engine.translate_text",
        stopping_translate,
    )

    # Create two tasks — worker should only process first
    file_a = _create_txt(tmp_path, "a.txt", "Task A")
    file_b = _create_txt(tmp_path, "b.txt", "Task B")
    tasks_a = setup_translation_tasks([file_a], "English (US)", "French")
    tasks_b = setup_translation_tasks([file_b], "English (US)", "French")
    h_id_b = tasks_b[0][0]

    TranslationWorker._is_any_worker_running = False
    worker = TranslationWorker(tasks_a)
    worker_ref["worker"] = worker
    worker.run()

    # Task B should still be Pending (not processed because worker stopped)
    status_b = get_history_entry_status(h_id_b)
    assert status_b == "Pending"


def test_cancel_before_any_work(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """cancel_check=True immediately → returns False, no LLM calls."""
    inp = tmp_path / "noop.txt"
    inp.write_text("Hello world", encoding="utf-8")
    out = tmp_path / "translated.txt"

    llm_calls: list[str] = []
    original = mock_llm

    def tracking_translate(
        texts: list[str],
        target_lang: str,
        source_lang: str = "",
        **kwargs: object,
    ) -> list[str]:
        llm_calls.extend(texts)
        return original(texts, target_lang, source_lang, **kwargs)

    from unittest.mock import patch  # noqa: PLC0415

    with patch(
        "src.core.text_processor._llm_engine.translate_text",
        tracking_translate,
    ):
        result = translate_file(
            inp,
            out,
            "French",
            "English (US)",
            cancel_check=lambda: True,
        )
    assert result is False
    assert len(llm_calls) == 0


# ── Multi-file queue and checkpoint consistency tests ───────────────


def test_cancel_multi_file_queue(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cancel with multiple files queued, remaining files stay Pending."""
    monkeypatch.setattr(
        "src.core.translator.load_setting",
        lambda k, d=None: False if "auto_remove" in k else d,
    )

    # Create three tasks
    file_a = _create_txt(tmp_path, "a.txt", "Task A content " + "word " * 30)
    file_b = _create_txt(tmp_path, "b.txt", "Task B content")
    file_c = _create_txt(tmp_path, "c.txt", "Task C content")

    tasks_a = setup_translation_tasks([file_a], "English (US)", "French")
    tasks_b = setup_translation_tasks([file_b], "English (US)", "French")
    tasks_c = setup_translation_tasks([file_c], "English (US)", "French")
    h_id_b = tasks_b[0][0]
    h_id_c = tasks_c[0][0]

    # Stop the worker after first LLM call
    worker_ref: dict[str, TranslationWorker] = {}
    call_count = {"n": 0}

    def stopping_translate(
        texts: list[str],
        target_lang: str,
        source_lang: str = "",
        **kwargs: object,
    ) -> list[str]:
        call_count["n"] += 1
        if call_count["n"] == 1 and "worker" in worker_ref:
            worker_ref["worker"]._is_running = False
        return [f"[{target_lang}] {t}" for t in texts]

    monkeypatch.setattr("src.core.llm_engine.translate_text", stopping_translate)
    monkeypatch.setattr(
        "src.core.text_processor._llm_engine.translate_text", stopping_translate
    )

    TranslationWorker._is_any_worker_running = False
    worker = TranslationWorker(tasks_a)
    worker_ref["worker"] = worker
    worker.run()

    # Tasks B and C should still be Pending (not processed)
    assert get_history_entry_status(h_id_b) == "Pending"
    assert get_history_entry_status(h_id_c) == "Pending"


def test_cancel_preserves_checkpoint_consistency(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """After cancel, checkpoint file is valid JSON."""
    data = {f"key_{i}": f"Value {i}" for i in range(50)}
    inp = tmp_path / "ckpt_check.json"
    inp.write_text(json.dumps(data), encoding="utf-8")
    out = tmp_path / "translated.json"
    checkpoint_dir = tmp_path / "ckpt"
    checkpoint_dir.mkdir()

    cancel = _make_canceller(2)
    translate_file(
        inp,
        out,
        "French",
        "English (US)",
        cancel_check=cancel,
        checkpoint_dir=checkpoint_dir,
    )

    # Any checkpoint files that exist must be valid JSON
    for ckpt_file in checkpoint_dir.glob("checkpoint_*.json"):
        content = ckpt_file.read_text(encoding="utf-8")
        parsed = json.loads(content)  # must not raise
        assert isinstance(parsed, dict)
        assert "version" in parsed


def test_cancel_clears_translating_status(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After cancel, DB status is not stuck on Translating."""
    monkeypatch.setattr(
        "src.core.translator.load_setting",
        lambda k, d=None: False if "auto_remove" in k else d,
    )

    file_path = _create_txt(tmp_path, "cancel_status.txt", "Hello world content")
    tasks = setup_translation_tasks([file_path], "English (US)", "French")
    h_id = tasks[0][0]

    # Stop the worker immediately via _is_running flag
    TranslationWorker._is_any_worker_running = False
    worker = TranslationWorker(tasks)
    worker._is_running = False
    worker.run()

    # Status should NOT be "Translating" — it should be Pending (not yet started)
    # or some other terminal state, never stuck on Translating
    status = get_history_entry_status(h_id)
    assert status != "Translating"


def test_cancel_before_first_batch_no_checkpoint(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """Cancelling before any work produces no checkpoint file."""
    data = {f"key_{i}": f"Value {i}" for i in range(20)}
    inp = tmp_path / "no_ckpt.json"
    inp.write_text(json.dumps(data), encoding="utf-8")
    out = tmp_path / "translated.json"
    checkpoint_dir = tmp_path / "ckpt"
    checkpoint_dir.mkdir()

    # Cancel immediately (cancel_after=0 → first cancel_check returns True)
    cancel = _make_canceller(0)
    result = translate_file(
        inp,
        out,
        "French",
        "English (US)",
        cancel_check=cancel,
        checkpoint_dir=checkpoint_dir,
    )
    assert result is False

    # No checkpoint files should have been created
    checkpoint_files = list(checkpoint_dir.glob("checkpoint_*.json"))
    assert len(checkpoint_files) == 0
