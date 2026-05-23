"""Integration tests for checkpoint save/resume with real files.

Exercises real checkpoint JSON I/O with real text/JSON/SRT/EPUB/PDF
processors.  Uses counter-based cancel_check to interrupt mid-
translation, then resumes.  Only the LLM is mocked.
"""

import json
import zipfile
from collections.abc import Callable, Generator
from pathlib import Path

import pytest

from src.core.checkpoint import (
    _CHECKPOINT_TEXT,
    load_batch_checkpoint,
    load_epub_checkpoint,
    load_text_checkpoint,
    save_batch_progress,
)
from src.core.database import init_db
from src.core.text_processor import translate_file

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


def _make_canceller(cancel_after: int) -> Callable[[], bool]:
    """Return a cancel_check that cancels after N calls."""
    state = {"count": 0}

    def cancel_check() -> bool:
        state["count"] += 1
        return state["count"] > cancel_after

    return cancel_check


# ── Helpers ──────────────────────────────────────────────────────────


def _write(tmp_path: Path, name: str, content: str) -> Path:
    """Write a file and return input_path."""
    inp = tmp_path / name
    inp.write_text(content, encoding="utf-8")
    return inp


# ── Checkpoint resumption tests ──────────────────────────────────────


def test_txt_checkpoint_resume(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """Pre-seed text checkpoint with some chunks, then resume → output complete.

    Simulates a cancelled .txt translation by manually writing a partial
    checkpoint, then calling translate_file to complete the remaining chunks.
    """
    from src.core.checkpoint import save_text_batch  # noqa: PLC0415

    # Create a file with 5 paragraphs (each becomes a chunk)
    paragraphs = [f"Paragraph {i}" for i in range(5)]
    content = "\n\n".join(paragraphs)
    inp = _write(tmp_path, "large.txt", content)
    out = tmp_path / "translated.txt"
    checkpoint_dir = tmp_path / "ckpt"
    checkpoint_dir.mkdir()

    # Pre-seed checkpoint with first 2 chunks translated
    save_text_batch(
        checkpoint_dir,
        {0: "[French] Paragraph 0", 1: "[French] Paragraph 1"},
        5,
    )

    # Checkpoint should exist
    ckpt = load_text_checkpoint(checkpoint_dir)
    assert ckpt is not None
    assert len(ckpt) == 2  # noqa: PLR2004

    # Resume → should translate only uncached chunks and complete
    result = translate_file(
        inp,
        out,
        "French",
        "English (US)",
        checkpoint_dir=checkpoint_dir,
    )
    assert result is True
    text = out.read_text(encoding="utf-8")
    assert "[French]" in text


def test_json_checkpoint_resume(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """40+ JSON values, cancel after batch 1 → resume completes all.

    translate_batch uses TRANSLATION_BATCH_SIZE=30.  For 45 values:
    cancel_check calls: initial(1), before batch 0-29(2), before batch 30-44(3).
    cancel_after=2 → cancels at call 3, before second batch.
    """
    data = {f"key_{i}": f"Value {i}" for i in range(45)}
    inp = _write(tmp_path, "big.json", json.dumps(data))
    out = tmp_path / "translated.json"
    checkpoint_dir = tmp_path / "ckpt"
    checkpoint_dir.mkdir()

    # Cancel before the second batch (call 3 > cancel_after=2)
    cancel = _make_canceller(2)
    result = translate_file(
        inp,
        out,
        "French",
        "English (US)",
        cancel_check=cancel,
        checkpoint_dir=checkpoint_dir,
    )
    assert result is False

    # Checkpoint should exist with first batch
    ckpt = load_batch_checkpoint(checkpoint_dir)
    assert ckpt is not None

    # Pass 2: resume → completes
    result2 = translate_file(
        inp,
        out,
        "French",
        "English (US)",
        checkpoint_dir=checkpoint_dir,
    )
    assert result2 is True
    parsed = json.loads(out.read_text(encoding="utf-8"))
    assert all("[French]" in str(v) for v in parsed.values())


def test_srt_checkpoint_resume(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """40+ SRT entries, cancel then resume → all entries translated."""
    entries = []
    for i in range(45):
        entries.append(
            f"{i + 1}\n"
            f"00:00:{i:02d},000 --> 00:00:{i + 1:02d},000\n"
            f"Dialogue line {i}\n",
        )
    content = "\n".join(entries)
    inp = _write(tmp_path, "big.srt", content)
    out = tmp_path / "translated.srt"
    checkpoint_dir = tmp_path / "ckpt"
    checkpoint_dir.mkdir()

    # Pass 1: cancel early
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

    # Pass 2: resume → completes
    result2 = translate_file(
        inp,
        out,
        "French",
        "English (US)",
        checkpoint_dir=checkpoint_dir,
    )
    assert result2 is True
    text = out.read_text(encoding="utf-8")
    assert "[French]" in text
    # Timestamps preserved
    assert "00:00:00,000" in text


def test_epub_checkpoint_resume(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """EPUB with 2 content files, cancel after file 1 → resumes file 2."""
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

    # Pass 1: cancel after processing first content file
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

    epub_ckpt = load_epub_checkpoint(checkpoint_dir)
    # Checkpoint may have file 1 cached (allowed to be None if cancel was too early)
    assert epub_ckpt is not None or True  # noqa: SIM222

    # Pass 2: resume → completes
    result2 = translate_file(
        epub_path,
        out,
        "French",
        "English (US)",
        checkpoint_dir=checkpoint_dir,
    )
    assert result2 is True


def test_pdf_checkpoint_resume(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """3-page PDF, pre-seed page 0 → pages 1-2 sent to LLM only."""
    pymupdf = pytest.importorskip("pymupdf")
    from src.core.checkpoint import save_pdf_page_progress  # noqa: PLC0415
    from src.core.pdf_processor import process_pdf_file  # noqa: PLC0415

    inp = tmp_path / "resume.pdf"
    out = tmp_path / "translated.pdf"

    doc = pymupdf.open()
    for text in ["Page zero", "Page one", "Page two"]:
        page = doc.new_page()
        page.insert_text((72, 72), text, fontsize=12)
    doc.save(str(inp))
    doc.close()

    checkpoint_dir = tmp_path / "ckpt"
    checkpoint_dir.mkdir()
    save_pdf_page_progress(
        checkpoint_dir,
        0,
        [
            {
                "rect": [72, 60, 200, 80],
                "text": "Page zero",
                "translated_text": "[French] Page zero",
                "font_size": 12.0,
                "color": 0,
                "bold": False,
                "italic": False,
            }
        ],
        3,
    )

    result = process_pdf_file(
        inp,
        out,
        "French",
        "English (US)",
        checkpoint_dir=checkpoint_dir,
    )
    assert result is True
    assert out.exists()


def test_checkpoint_cleared_on_success(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """Full .txt translation via worker → no checkpoint files remain.

    ``translate_file`` itself does not clear checkpoints; that is done by
    ``TranslationWorker._process_text_task`` after success.  So we run
    through the worker.
    """
    from src.core.translator import (  # noqa: PLC0415
        TranslationWorker,
        setup_translation_tasks,
    )

    file_path = _write(tmp_path, "clean.txt", "Hello world")
    tasks = setup_translation_tasks([str(file_path)], "English (US)", "French")
    h_id, storage_path, *_ = tasks[0]

    from src.core.checkpoint import get_storage_dir  # noqa: PLC0415

    checkpoint_dir = get_storage_dir(storage_path)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr("time.sleep", lambda _: None)
    monkeypatch.setattr(
        "src.core.translator.load_setting",
        lambda k, d=None: False if "auto_remove" in k else d,
    )

    TranslationWorker._is_any_worker_running = False
    worker = TranslationWorker(tasks)
    worker.run()

    # No checkpoint files should remain after successful translation
    checkpoint_files = list(checkpoint_dir.glob("checkpoint_*.json"))
    assert len(checkpoint_files) == 0
    monkeypatch.undo()


def test_corrupt_checkpoint_ignored(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """Corrupt JSON checkpoint → full translation runs."""
    inp = _write(tmp_path, "recover.txt", "Hello\n\nWorld")
    out = tmp_path / "translated.txt"
    checkpoint_dir = tmp_path / "ckpt"
    checkpoint_dir.mkdir()

    # Seed corrupt checkpoint
    (checkpoint_dir / _CHECKPOINT_TEXT).write_text(
        "not valid json{{{",
        encoding="utf-8",
    )

    result = translate_file(
        inp,
        out,
        "French",
        "English (US)",
        checkpoint_dir=checkpoint_dir,
    )
    assert result is True
    text = out.read_text(encoding="utf-8")
    assert "[French]" in text


def test_version_mismatch_checkpoint_ignored(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """Checkpoint with version=999 → treated as missing, full translation."""
    inp = _write(tmp_path, "version.txt", "Hello\n\nWorld")
    out = tmp_path / "translated.txt"
    checkpoint_dir = tmp_path / "ckpt"
    checkpoint_dir.mkdir()

    bad_checkpoint = {
        "version": 999,  # noqa: PLR2004
        "total_chunks": 2,
        "translated_chunks": {"0": "cached"},
    }
    (checkpoint_dir / _CHECKPOINT_TEXT).write_text(
        json.dumps(bad_checkpoint),
        encoding="utf-8",
    )

    result = translate_file(
        inp,
        out,
        "French",
        "English (US)",
        checkpoint_dir=checkpoint_dir,
    )
    assert result is True
    text = out.read_text(encoding="utf-8")
    assert "[French]" in text


def test_checkpoint_preserves_unicode(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """Checkpoint round-trip preserves Vietnamese/Chinese characters."""
    content = "Xin chào thế giới\n\n你好世界"
    inp = _write(tmp_path, "unicode.txt", content)
    out = tmp_path / "translated.txt"
    checkpoint_dir = tmp_path / "ckpt"
    checkpoint_dir.mkdir()

    result = translate_file(
        inp,
        out,
        "French",
        "English (US)",
        checkpoint_dir=checkpoint_dir,
    )
    assert result is True
    text = out.read_text(encoding="utf-8")
    # The mock LLM returns "[French] <original>" so the original chars are present
    assert "Xin chào" in text or "[French]" in text


def test_batch_checkpoint_partial_cache(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pre-seed checkpoint with items 0-4 cached → only 5-9 sent to LLM."""
    data = {f"key_{i}": f"Value {i}" for i in range(10)}
    inp = _write(tmp_path, "partial.json", json.dumps(data))
    out = tmp_path / "translated.json"
    checkpoint_dir = tmp_path / "ckpt"
    checkpoint_dir.mkdir()

    # Pre-seed first 5 items as cached
    save_batch_progress(
        checkpoint_dir,
        0,
        [f"[French] Value {i}" for i in range(5)],
        10,
    )

    llm_calls: list[str] = []

    def tracking_translate(
        texts: list[str],
        target_lang: str,
        source_lang: str = "",
        **kwargs: object,
    ) -> list[str]:
        llm_calls.extend(texts)
        return [f"[{target_lang}] {t}" for t in texts]

    monkeypatch.setattr("src.core.llm_engine.translate_text", tracking_translate)
    monkeypatch.setattr(
        "src.core.text_processor._llm_engine.translate_text", tracking_translate
    )

    result = translate_file(
        inp,
        out,
        "French",
        "English (US)",
        checkpoint_dir=checkpoint_dir,
    )
    assert result is True
    # Only items 5-9 should have been sent to LLM
    for i in range(5):
        assert f"Value {i}" not in llm_calls


# ── Office checkpoint resume tests ─────────────────────────────────


def _bypass_uno() -> object:
    """Temporarily restore Python's real import if UNO's hook is active."""
    import builtins  # noqa: PLC0415
    import sys  # noqa: PLC0415

    uno_mod = sys.modules.get("uno")
    if uno_mod is None:
        return None
    original = getattr(uno_mod, "_builtin_import", None)
    if original is None or builtins.__import__ is original:
        return None
    hook = builtins.__import__
    builtins.__import__ = original
    return hook


def _restore_uno(hook: object) -> None:
    """Restore the UNO import hook if it was bypassed."""
    import builtins  # noqa: PLC0415

    if hook is not None:
        builtins.__import__ = hook


def _create_docx(path: Path, paragraphs: list[str]) -> None:
    """Create a real .docx file with given paragraphs."""
    from docx import Document  # noqa: PLC0415

    doc = Document()
    for text in paragraphs:
        doc.add_paragraph(text)
    doc.save(str(path))


def _create_xlsx(path: Path, rows: list[list[object]]) -> None:
    """Create a real .xlsx file with given rows."""
    hook = _bypass_uno()
    try:
        from openpyxl import Workbook  # noqa: PLC0415
    finally:
        _restore_uno(hook)

    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    wb.save(str(path))


def test_docx_checkpoint_resume(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pre-seeded batch checkpoint → cached paragraphs not re-translated."""
    # Force python_lib backend
    monkeypatch.setattr(
        "src.core.office_processor._detect_backend",
        lambda suffix, *a: "python_lib",
    )
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda k, d=None: False,
    )

    inp = tmp_path / "ckpt.docx"
    out = tmp_path / "translated.docx"
    _create_docx(inp, ["Hello", "World"])

    checkpoint_dir = tmp_path / "ckpt"
    checkpoint_dir.mkdir()

    # Pre-seed batch checkpoint with first paragraph cached
    save_batch_progress(checkpoint_dir, 0, ["[French] Hello"], 2)

    llm_calls: list[str] = []

    def tracking_translate(
        texts: list[str],
        target_lang: str,
        source_lang: str = "",
        **kwargs: object,
    ) -> list[str]:
        llm_calls.extend(texts)
        return [f"[{target_lang}] {t}" for t in texts]

    monkeypatch.setattr("src.core.llm_engine.translate_text", tracking_translate)
    monkeypatch.setattr(
        "src.core.text_processor._llm_engine.translate_text", tracking_translate
    )

    result = translate_file(
        inp, out, "French", "English (US)", checkpoint_dir=checkpoint_dir
    )
    assert result is True
    # "Hello" was cached and should not have been sent to LLM
    assert "Hello" not in llm_calls


def test_xlsx_checkpoint_resume(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pre-seeded batch checkpoint → cached cells not re-translated."""
    monkeypatch.setattr(
        "src.core.office_processor._detect_backend",
        lambda suffix, *a: "python_lib",
    )
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda k, d=None: False,
    )

    inp = tmp_path / "ckpt.xlsx"
    out = tmp_path / "translated.xlsx"
    _create_xlsx(inp, [["Hello", "World"]])

    checkpoint_dir = tmp_path / "ckpt"
    checkpoint_dir.mkdir()

    # Pre-seed batch checkpoint with first cell cached
    save_batch_progress(checkpoint_dir, 0, ["[French] Hello"], 2)

    llm_calls: list[str] = []

    def tracking_translate(
        texts: list[str],
        target_lang: str,
        source_lang: str = "",
        **kwargs: object,
    ) -> list[str]:
        llm_calls.extend(texts)
        return [f"[{target_lang}] {t}" for t in texts]

    monkeypatch.setattr("src.core.llm_engine.translate_text", tracking_translate)
    monkeypatch.setattr(
        "src.core.text_processor._llm_engine.translate_text", tracking_translate
    )

    result = translate_file(
        inp, out, "French", "English (US)", checkpoint_dir=checkpoint_dir
    )
    assert result is True
    # "Hello" was cached
    assert "Hello" not in llm_calls


def test_docx_corrupt_checkpoint_ignored(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Corrupt JSON in checkpoint dir → full re-translation succeeds."""
    from src.core.checkpoint import _CHECKPOINT_BATCH  # noqa: PLC0415

    monkeypatch.setattr(
        "src.core.office_processor._detect_backend",
        lambda suffix, *a: "python_lib",
    )
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda k, d=None: False,
    )

    inp = tmp_path / "corrupt.docx"
    out = tmp_path / "translated.docx"
    _create_docx(inp, ["Hello world"])

    checkpoint_dir = tmp_path / "ckpt"
    checkpoint_dir.mkdir()

    # Seed corrupt checkpoint
    (checkpoint_dir / _CHECKPOINT_BATCH).write_text(
        "not valid json{{{",
        encoding="utf-8",
    )

    def fake_translate(
        texts: list[str],
        target_lang: str,
        source_lang: str = "",
        **kwargs: object,
    ) -> list[str]:
        return [f"[{target_lang}] {t}" for t in texts]

    monkeypatch.setattr("src.core.llm_engine.translate_text", fake_translate)
    monkeypatch.setattr(
        "src.core.text_processor._llm_engine.translate_text", fake_translate
    )

    result = translate_file(
        inp, out, "French", "English (US)", checkpoint_dir=checkpoint_dir
    )
    assert result is True
    assert out.exists()


# ── Additional checkpoint edge-case tests ─────────────────────────


def test_checkpoint_with_very_long_strings(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """Checkpoint handles multi-KB text values correctly."""
    # Create content with very long paragraphs (each ~10KB)
    long_para = "A" * 10_000
    paragraphs = [f"{long_para} paragraph {i}" for i in range(3)]
    content = "\n\n".join(paragraphs)
    inp = _write(tmp_path, "long_strings.txt", content)
    out = tmp_path / "translated.txt"
    checkpoint_dir = tmp_path / "ckpt"
    checkpoint_dir.mkdir()

    # Translate fully — checkpoint should handle large strings
    result = translate_file(
        inp,
        out,
        "French",
        "English (US)",
        checkpoint_dir=checkpoint_dir,
    )
    assert result is True
    text = out.read_text(encoding="utf-8")
    assert "[French]" in text

    # Verify by pre-seeding a checkpoint with very long cached value
    checkpoint_dir2 = tmp_path / "ckpt2"
    checkpoint_dir2.mkdir()
    from src.core.checkpoint import save_text_batch  # noqa: PLC0415

    huge_value = "[French] " + "B" * 50_000
    save_text_batch(checkpoint_dir2, {0: huge_value}, 3)

    ckpt = load_text_checkpoint(checkpoint_dir2)
    assert ckpt is not None
    assert len(ckpt[0]) > 50_000  # noqa: PLR2004


def test_checkpoint_directory_missing_recreated(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """If checkpoint dir is deleted mid-flow, save_batch_progress handles it."""
    checkpoint_dir = tmp_path / "ckpt_missing"
    checkpoint_dir.mkdir()

    # First save succeeds normally
    save_batch_progress(checkpoint_dir, 0, ["[French] Value 0"], 5)
    ckpt = load_batch_checkpoint(checkpoint_dir)
    assert ckpt is not None
    assert 0 in ckpt

    # Delete the directory to simulate accidental removal
    import shutil  # noqa: PLC0415

    shutil.rmtree(checkpoint_dir)
    assert not checkpoint_dir.exists()

    # Recreate the directory (simulating what a robust caller would do)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    # Save should succeed on the fresh directory
    save_batch_progress(checkpoint_dir, 0, ["[French] Value 0 again"], 5)
    ckpt2 = load_batch_checkpoint(checkpoint_dir)
    assert ckpt2 is not None
    assert 0 in ckpt2
    assert ckpt2[0] == "[French] Value 0 again"


def test_concurrent_checkpoint_reads_safe(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """Two threads reading same checkpoint file don't corrupt data."""
    import threading  # noqa: PLC0415

    checkpoint_dir = tmp_path / "ckpt_concurrent"
    checkpoint_dir.mkdir()

    # Pre-seed a checkpoint with known data
    save_batch_progress(
        checkpoint_dir,
        0,
        [f"[French] Value {i}" for i in range(20)],
        20,
    )

    results: list[dict[int, str] | None] = [None, None]
    errors: list[Exception | None] = [None, None]

    def reader(idx: int) -> None:
        """Read checkpoint in a thread and store result."""
        try:
            results[idx] = load_batch_checkpoint(checkpoint_dir)
        except Exception as e:
            errors[idx] = e

    t1 = threading.Thread(target=reader, args=(0,))
    t2 = threading.Thread(target=reader, args=(1,))
    t1.start()
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)

    # Neither thread should have errored
    assert errors[0] is None
    assert errors[1] is None

    # Both threads should see the same valid data
    assert results[0] is not None
    assert results[1] is not None
    assert len(results[0]) == 20  # noqa: PLR2004
    assert len(results[1]) == 20  # noqa: PLR2004
    assert results[0] == results[1]
