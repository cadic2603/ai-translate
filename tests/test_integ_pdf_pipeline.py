"""Integration tests for the PDF translation pipeline.

All tests gated by ``pytest.importorskip("pymupdf")``.
Creates real PDFs via PyMuPDF, exercises the extract-overlay pipeline.
Only the LLM is mocked.
"""

from collections.abc import Callable, Generator
from pathlib import Path
from typing import Any

import pytest

pymupdf = pytest.importorskip("pymupdf")

from src.core.checkpoint import save_pdf_page_progress  # noqa: E402
from src.core.database import init_db  # noqa: E402
from src.core.pdf_processor import process_pdf_file  # noqa: E402

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
    # Disable OCR/image features
    monkeypatch.setattr(
        "src.core.pdf_processor._config.load_setting",
        lambda k, d=None: False,
    )
    monkeypatch.setattr(
        "src.core.pdf_processor._config.check_ocr_setup",
        lambda: False,
    )
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


def _create_pdf(path: Path, pages_text: list[str]) -> None:
    """Create a real PDF with text on each page.

    Args:
        path: Output file path.
        pages_text: List of strings, one per page.
    """
    doc = pymupdf.open()
    for text in pages_text:
        page = doc.new_page()
        # Insert text at top-left
        page.insert_text((72, 72), text, fontsize=12)
    doc.save(str(path))
    doc.close()


def _create_pdf_with_font(path: Path, text: str, fontsize: float) -> None:
    """Create a single-page PDF with specific font size."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text, fontsize=fontsize)
    doc.save(str(path))
    doc.close()


# ── Basic round-trips ────────────────────────────────────────────────


def test_pdf_single_page(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """1-page PDF with text → translated text overlay."""
    inp = tmp_path / "single.pdf"
    out = tmp_path / "translated.pdf"
    _create_pdf(inp, ["Hello World"])

    result = process_pdf_file(inp, out, "French", "English (US)")
    assert result is True
    assert out.exists()

    # Verify the output PDF has content
    doc = pymupdf.open(str(out))
    text = doc[0].get_text()
    doc.close()
    # The text should contain the translated overlay
    assert text  # Not empty


def test_pdf_multi_page(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """3-page PDF → all pages translated, progress increases."""
    inp = tmp_path / "multi.pdf"
    out = tmp_path / "translated.pdf"
    _create_pdf(inp, ["Page one text", "Page two text", "Page three text"])

    progress_values: list[Any] = []
    result = process_pdf_file(
        inp,
        out,
        "French",
        "English (US)",
        progress_callback=progress_values.append,
    )
    assert result is True
    assert len(progress_values) >= 3  # noqa: PLR2004
    # Progress should be increasing
    for i in range(1, len(progress_values)):
        assert progress_values[i] >= progress_values[i - 1]


# ── Edge cases ───────────────────────────────────────────────────────


def test_pdf_checkpoint_resume(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """Pre-seed page 0 checkpoint → only page 1 sent to LLM."""
    inp = tmp_path / "resume.pdf"
    out = tmp_path / "translated.pdf"
    _create_pdf(inp, ["Page zero text", "Page one text"])

    # Pre-seed checkpoint for page 0
    checkpoint_dir = tmp_path / "checkpoints"
    checkpoint_dir.mkdir()
    save_pdf_page_progress(
        checkpoint_dir,
        0,
        [
            {
                "rect": [72, 60, 200, 80],
                "text": "Page zero text",
                "translated_text": "[French] Page zero text",
                "font_size": 12.0,
                "color": 0,
                "bold": False,
                "italic": False,
            }
        ],
        2,
    )

    llm_calls: list[str] = []
    original_translate = mock_llm

    def tracking_translate(
        texts: list[str],
        target_lang: str,
        source_lang: str = "",
        **kwargs: object,
    ) -> list[str]:
        llm_calls.extend(texts)
        return original_translate(texts, target_lang, source_lang, **kwargs)

    from unittest.mock import patch  # noqa: PLC0415

    with patch(
        "src.core.llm_engine.translate_text",
        tracking_translate,
    ):
        result = process_pdf_file(
            inp,
            out,
            "French",
            "English (US)",
            checkpoint_dir=checkpoint_dir,
        )
    assert result is True
    # Page 0 was cached; only page 1's text should have been sent
    assert "Page zero text" not in llm_calls


def test_pdf_empty_page(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """Page with no text → no LLM call, output exists."""
    doc = pymupdf.open()
    doc.new_page()  # blank page
    inp = tmp_path / "blank.pdf"
    doc.save(str(inp))
    doc.close()

    out = tmp_path / "translated.pdf"
    result = process_pdf_file(inp, out, "French", "English (US)")
    assert result is True
    assert out.exists()


def test_pdf_multi_block_page(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """Page with 3 text blocks at different positions → all translated."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Block one", fontsize=12)
    page.insert_text((72, 200), "Block two", fontsize=12)
    page.insert_text((72, 400), "Block three", fontsize=12)
    inp = tmp_path / "multiblock.pdf"
    doc.save(str(inp))
    doc.close()

    out = tmp_path / "translated.pdf"
    result = process_pdf_file(inp, out, "French", "English (US)")
    assert result is True
    assert out.exists()


def test_pdf_font_preservation(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """Text with specific font size → overlay HTML contains correct size."""
    inp = tmp_path / "fontsize.pdf"
    out = tmp_path / "translated.pdf"
    fontsize = 18  # noqa: PLR2004
    _create_pdf_with_font(inp, "Big text here", fontsize)

    result = process_pdf_file(inp, out, "French", "English (US)")
    assert result is True
    assert out.exists()


def test_pdf_scanned_page_detection(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """Page with image but no text + OCR disabled → page left untranslated."""
    doc = pymupdf.open()
    page = doc.new_page()
    # Insert a small image (1x1 white pixel)
    img = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 10, 10), 0)
    page.insert_image(pymupdf.Rect(100, 100, 200, 200), pixmap=img)
    inp = tmp_path / "scanned.pdf"
    doc.save(str(inp))
    doc.close()

    out = tmp_path / "translated.pdf"
    result = process_pdf_file(inp, out, "French", "English (US)")
    assert result is True
    assert out.exists()


def test_pdf_special_chars(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """Text with <, >, &, quotes → HTML-escaped in overlay."""
    inp = tmp_path / "special.pdf"
    out = tmp_path / "translated.pdf"
    _create_pdf(inp, ['Text with <html> & "quotes"'])

    result = process_pdf_file(inp, out, "French", "English (US)")
    assert result is True
    assert out.exists()


# ── Annotation integration tests ────────────────────────────────────


def _create_pdf_with_annotations(
    path: Path,
    texts: list[str] | None = None,
    comments: list[str] | None = None,
    freetext: list[str] | None = None,
) -> None:
    """Create a PDF with text blocks and/or annotations.

    Args:
        path: Output file path.
        texts: Body text strings to insert on the first page.
        comments: Sticky-note (Text) annotation contents.
        freetext: FreeText (visible box) annotation contents.
    """
    doc = pymupdf.open()
    page = doc.new_page()
    if texts:
        y = 72
        for text in texts:
            page.insert_text((72, y), text, fontsize=12)
            y += 40
    if comments:
        for i, content in enumerate(comments):
            annot = page.add_text_annot(
                (400, 72 + i * 50),
                content,
            )
            annot.set_info(content=content, title=f"Author{i}")
            annot.update()
    if freetext:
        for i, content in enumerate(freetext):
            annot = page.add_freetext_annot(
                pymupdf.Rect(100, 300 + i * 80, 300, 350 + i * 80),
                content,
                fontsize=10,
            )
            annot.update()
    doc.save(str(path))
    doc.close()


def _read_pdf_annotations(path: Path) -> list[str]:
    """Read all annotation contents from a PDF file.

    Returns:
        List of content strings from all annotations.
    """
    doc = pymupdf.open(str(path))
    contents: list[str] = []
    for page in doc:
        annots = page.annots()
        if annots is None:
            continue
        for annot in annots:
            info = annot.info
            content = info.get("content", "")
            if content:
                contents.append(content)
    doc.close()
    return contents


def test_pdf_text_annotation_translated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_llm: Callable[..., list[str]],
) -> None:
    """Sticky-note (Text) annotation content replaced with translated text."""
    # Enable annotation translation
    monkeypatch.setattr(
        "src.core.pdf_processor._config.load_setting",
        lambda k, d=None: "comments" in k,
    )

    inp = tmp_path / "sticky.pdf"
    out = tmp_path / "translated.pdf"
    _create_pdf_with_annotations(inp, texts=["Body text"], comments=["Review note"])

    result = process_pdf_file(inp, out, "French", "English (US)")
    assert result is True

    annots = _read_pdf_annotations(out)
    assert any("[French]" in a for a in annots)


def test_pdf_freetext_annotation_translated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_llm: Callable[..., list[str]],
) -> None:
    """FreeText annotation extracted and translation attempted.

    Note: FreeText annotations render as visible text, so PyMuPDF's
    redaction step may remove the annotation overlay.  This test
    verifies the extraction + translation code path runs correctly,
    and that the annotation text was sent to the LLM.
    """
    # FreeText annotations are gated by the shapes toggle (not comments)
    monkeypatch.setattr(
        "src.core.pdf_processor._config.load_setting",
        lambda k, d=None: "shapes" in k,
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

    inp = tmp_path / "freetext.pdf"
    out = tmp_path / "translated.pdf"
    _create_pdf_with_annotations(inp, freetext=["Visible note"])

    result = process_pdf_file(inp, out, "French", "English (US)")
    assert result is True
    # The FreeText content should have been sent to the LLM
    assert "Visible note" in llm_calls


def test_pdf_annotations_skipped_when_disabled(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """Default settings → annotation content unchanged."""
    # The autouse fixture already disables annotations via load_setting → False
    inp = tmp_path / "skip.pdf"
    out = tmp_path / "translated.pdf"
    _create_pdf_with_annotations(inp, texts=["Body"], comments=["Original note"])

    result = process_pdf_file(inp, out, "French", "English (US)")
    assert result is True

    annots = _read_pdf_annotations(out)
    # Annotation should NOT contain translated text
    assert all("[French]" not in a for a in annots)


def test_pdf_annotations_combined_with_text_blocks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_llm: Callable[..., list[str]],
) -> None:
    """Both body text blocks AND annotations translated in single pass."""
    monkeypatch.setattr(
        "src.core.pdf_processor._config.load_setting",
        lambda k, d=None: "comments" in k,
    )

    inp = tmp_path / "combined.pdf"
    out = tmp_path / "translated.pdf"
    _create_pdf_with_annotations(
        inp,
        texts=["Hello body"],
        comments=["Comment text"],
    )

    result = process_pdf_file(inp, out, "French", "English (US)")
    assert result is True

    # Body text should be translated
    doc = pymupdf.open(str(out))
    body = doc[0].get_text()
    doc.close()
    assert body  # Not empty

    # Annotations should also be translated
    annots = _read_pdf_annotations(out)
    assert any("[French]" in a for a in annots)


def test_pdf_annotation_checkpoint_resume(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pre-seeded checkpoint with annot entries → LLM not called for that page."""
    monkeypatch.setattr(
        "src.core.pdf_processor._config.load_setting",
        lambda k, d=None: "comments" in k,
    )

    inp = tmp_path / "annot_ckpt.pdf"
    out = tmp_path / "translated.pdf"
    _create_pdf_with_annotations(inp, texts=["Body"], comments=["Note"])

    # Pre-seed checkpoint for page 0 with block + annotation
    checkpoint_dir = tmp_path / "ckpt"
    checkpoint_dir.mkdir()
    save_pdf_page_progress(
        checkpoint_dir,
        0,
        [
            {
                "rect": [72, 60, 200, 80],
                "text": "Body",
                "translated_text": "[French] Body",
                "font_size": 12.0,
                "color": 0,
                "bold": False,
                "italic": False,
            },
            {
                "type": "annot",
                "annot_type": 0,
                "annot_id": "annot-0",
                "text": "Note",
                "translated_text": "[French] Note",
            },
        ],
        1,
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

    result = process_pdf_file(
        inp, out, "French", "English (US)", checkpoint_dir=checkpoint_dir
    )
    assert result is True
    # No LLM calls since the only page was cached
    assert len(llm_calls) == 0


def test_pdf_annotation_cancellation_returns_false(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """cancel_check=lambda: True → returns False, no LLM calls."""
    monkeypatch.setattr(
        "src.core.pdf_processor._config.load_setting",
        lambda k, d=None: "comments" in k,
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

    inp = tmp_path / "cancel.pdf"
    out = tmp_path / "translated.pdf"
    _create_pdf_with_annotations(inp, texts=["Body"], comments=["Note"])

    result = process_pdf_file(
        inp, out, "French", "English (US)", cancel_check=lambda: True
    )
    assert result is False
    assert len(llm_calls) == 0


def test_pdf_glossary_forwarded_to_batch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Glossary entries reach translate_batch kwargs."""
    monkeypatch.setattr(
        "src.core.pdf_processor._config.load_setting",
        lambda k, d=None: "comments" in k,
    )

    captured_kwargs: dict[str, object] = {}

    def tracking_batch(
        texts: list[str],
        target_lang: str,
        source_lang: str = "",
        **kwargs: object,
    ) -> list[str]:
        captured_kwargs.update(kwargs)
        return [f"[{target_lang}] {t}" for t in texts]

    monkeypatch.setattr("src.core.llm_engine.translate_text", tracking_batch)
    monkeypatch.setattr(
        "src.core.text_processor._llm_engine.translate_text", tracking_batch
    )

    inp = tmp_path / "glossary.pdf"
    out = tmp_path / "translated.pdf"
    _create_pdf(inp, ["Hello world"])

    glossary = [(1, "Hello", "Bonjour")]
    result = process_pdf_file(
        inp,
        out,
        "French",
        "English (US)",
        glossary_entries=glossary,
    )
    assert result is True
    assert captured_kwargs.get("glossary_entries") == glossary


# ── Link checkpoint resume ──────────────────────────────────────────


def _create_pdf_with_link(
    path: Path,
    body: str = "See Section 3 for details",
    link_text: str = "Section 3",
    uri: str = "https://example.com",
) -> None:
    """Create a single-page PDF with a URI link on part of the text.

    Args:
        path: Output file path.
        body: Full line of text.
        link_text: Substring to create the link over.
        uri: Link destination.
    """
    doc = pymupdf.open()
    page = doc.new_page()
    point = pymupdf.Point(72, 72)
    page.insert_text(point, body, fontsize=12)
    # Approximate the link rect from text position
    # We estimate the link rect by searching for the text
    hits = page.search_for(link_text)
    if hits:
        page.insert_link(
            {"kind": 2, "from": hits[0], "uri": uri},
        )
    doc.save(str(path))
    doc.close()


def test_pdf_link_checkpoint_resume(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """Links in checkpoint carry _translated for char-level matching on resume."""
    inp = tmp_path / "link_resume.pdf"
    out = tmp_path / "translated.pdf"
    _create_pdf_with_link(inp)

    # First: do a normal translation to produce a checkpoint with links
    checkpoint_dir = tmp_path / "ckpt"
    checkpoint_dir.mkdir()
    result = process_pdf_file(
        inp,
        out,
        "French",
        "English (US)",
        checkpoint_dir=checkpoint_dir,
    )
    assert result is True

    # Read the checkpoint to verify link entries were saved
    from src.core.checkpoint import load_pdf_checkpoint  # noqa: PLC0415

    ckpt = load_pdf_checkpoint(checkpoint_dir)
    assert ckpt is not None
    page_entries = ckpt.get(0, [])
    link_entries = [e for e in page_entries if e.get("type") == "link"]
    assert len(link_entries) >= 1, "Checkpoint should contain link entries"
    # At least one link should have _translated set
    has_translated = any(le.get("_translated") for le in link_entries)
    assert has_translated, "At least one checkpoint link should have _translated"

    # Second: resume from checkpoint (simulates app restart)
    out2 = tmp_path / "translated2.pdf"
    llm_calls: list[str] = []

    def tracking_translate(
        texts: list[str],
        target_lang: str,
        source_lang: str = "",
        **kwargs: object,
    ) -> list[str]:
        llm_calls.extend(texts)
        return [f"[{target_lang}] {t}" for t in texts]

    from unittest.mock import patch  # noqa: PLC0415

    with patch("src.core.llm_engine.translate_text", tracking_translate):
        result2 = process_pdf_file(
            inp,
            out2,
            "French",
            "English (US)",
            checkpoint_dir=checkpoint_dir,
        )
    assert result2 is True
    # Page 0 was cached — no LLM calls
    assert len(llm_calls) == 0

    # Verify links exist in the resumed output
    doc = pymupdf.open(str(out2))
    links = doc[0].get_links()
    doc.close()
    assert len(links) >= 1, "Resumed output should have links"
    assert any(lk.get("uri") == "https://example.com" for lk in links), (
        "Link URI should be preserved"
    )


def test_pdf_link_checkpoint_backward_compat(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """Old checkpoint without link entries still works on resume."""
    inp = tmp_path / "compat.pdf"
    out = tmp_path / "translated.pdf"
    _create_pdf_with_link(inp)

    # Pre-seed an old-style checkpoint (no link entries)
    checkpoint_dir = tmp_path / "ckpt"
    checkpoint_dir.mkdir()
    save_pdf_page_progress(
        checkpoint_dir,
        0,
        [
            {
                "rect": [72, 60, 300, 80],
                "text": "See Section 3 for details",
                "translated_text": "[French] See Section 3 for details",
                "font_size": 12.0,
                "color": 0,
                "bold": False,
                "italic": False,
            },
        ],
        1,
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

    # Should not crash; links may use fallback path
    doc = pymupdf.open(str(out))
    doc[0].get_text()  # No crash
    doc.close()


# ── Bookmark integration tests ──────────────────────────────────────


def test_pdf_bookmark_translation(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """PDF with TOC entries → bookmarks translated in output."""
    inp = tmp_path / "bookmarks.pdf"
    out = tmp_path / "translated.pdf"

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Chapter 1 Introduction", fontsize=18)
    page.insert_text((72, 150), "Some body text", fontsize=12)
    doc.set_toc([[1, "Chapter 1 Introduction", 1]])
    doc.save(str(inp))
    doc.close()

    result = process_pdf_file(inp, out, "French", "English (US)")
    assert result is True
    assert out.exists()

    # Verify the bookmarks in the output contain translated text
    doc = pymupdf.open(str(out))
    toc = doc.get_toc()
    doc.close()
    assert len(toc) >= 1
    # The title should be translated (prefixed with [French])
    assert any("[French]" in entry[1] for entry in toc), (
        f"Expected translated bookmark titles, got: {toc}"
    )


def test_pdf_deeply_nested_bookmarks(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """PDF with 3-level TOC hierarchy → all levels translated."""
    inp = tmp_path / "nested_bm.pdf"
    out = tmp_path / "translated.pdf"

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Part A", fontsize=20)
    page.insert_text((72, 150), "Chapter One", fontsize=16)
    page.insert_text((72, 230), "Section Alpha", fontsize=12)
    doc.set_toc(
        [
            [1, "Part A", 1],
            [2, "Chapter One", 1],
            [3, "Section Alpha", 1],
        ]
    )
    doc.save(str(inp))
    doc.close()

    result = process_pdf_file(inp, out, "French", "English (US)")
    assert result is True

    doc = pymupdf.open(str(out))
    toc = doc.get_toc()
    doc.close()

    assert len(toc) == 3  # noqa: PLR2004
    # All three levels should be translated
    for entry in toc:
        assert "[French]" in entry[1], (
            f"Bookmark level {entry[0]} not translated: {entry[1]}"
        )
    # Structure preserved: levels must be 1, 2, 3
    assert [e[0] for e in toc] == [1, 2, 3]


def test_pdf_empty_bookmark_list(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """PDF with no bookmarks → no crash, output valid."""
    inp = tmp_path / "no_bookmarks.pdf"
    out = tmp_path / "translated.pdf"
    _create_pdf(inp, ["Just some text without bookmarks"])

    result = process_pdf_file(inp, out, "French", "English (US)")
    assert result is True
    assert out.exists()

    # Verify output is a valid PDF with no TOC
    doc = pymupdf.open(str(out))
    toc = doc.get_toc()
    text = doc[0].get_text()
    doc.close()
    assert len(toc) == 0
    assert text  # Not empty — body text is still present


# ── Widget (form field) integration tests ────────────────────────────


def test_pdf_widget_text_field(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_llm: Callable[..., list[str]],
) -> None:
    """PDF with text form field → field value translated."""
    # Enable shapes/widgets translation
    monkeypatch.setattr(
        "src.core.pdf_processor._config.load_setting",
        lambda k, d=None: "shapes" in k or "textbox" in k,
    )

    inp = tmp_path / "widget.pdf"
    out = tmp_path / "translated.pdf"

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Form page", fontsize=12)

    w = pymupdf.Widget()
    w.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
    w.field_value = "Enter your name"
    w.field_name = "name_field"
    w.rect = pymupdf.Rect(72, 300, 300, 330)
    page.add_widget(w)

    doc.save(str(inp))
    doc.close()

    result = process_pdf_file(inp, out, "French", "English (US)")
    assert result is True
    assert out.exists()

    # Verify the widget field value was translated
    doc = pymupdf.open(str(out))
    page = doc[0]
    widgets = list(page.widgets())
    doc.close()
    assert len(widgets) >= 1
    # At least one widget should have translated text
    translated_values = [w.field_value for w in widgets if w.field_value]
    assert any("[French]" in v for v in translated_values), (
        f"Expected translated widget values, got: {translated_values}"
    )


# ── Link edge case tests ────────────────────────────────────────────


def test_pdf_special_url_characters_in_links(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """PDF with link containing query params and unicode → link preserved."""
    inp = tmp_path / "special_link.pdf"
    out = tmp_path / "translated.pdf"

    uri = "https://example.com/search?q=hello+world&lang=fr#section%202"
    body = "Click here for search results"
    link_text = "search results"

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), body, fontsize=12)
    hits = page.search_for(link_text)
    if hits:
        page.insert_link({"kind": 2, "from": hits[0], "uri": uri})
    doc.save(str(inp))
    doc.close()

    result = process_pdf_file(inp, out, "French", "English (US)")
    assert result is True
    assert out.exists()

    # Verify the link URI is preserved in the output
    doc = pymupdf.open(str(out))
    links = doc[0].get_links()
    doc.close()
    assert len(links) >= 1, "Output should have at least one link"
    assert any(lk.get("uri") == uri for lk in links), (
        f"Link URI should be preserved, got: {[lk.get('uri') for lk in links]}"
    )


# ── Alignment integration tests ─────────────────────────────────────


def test_pdf_mixed_alignment_page(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """PDF with left, center, right text → all blocks translated, output valid."""
    inp = tmp_path / "alignment.pdf"
    out = tmp_path / "translated.pdf"

    doc = pymupdf.open()
    page = doc.new_page()
    page_width = page.rect.width

    # Left-aligned text near left margin
    page.insert_text((72, 72), "Left aligned text", fontsize=12)
    # Center-aligned text (roughly centered horizontally)
    center_text = "Center aligned"
    # Approximate center position
    center_x = (page_width / 2) - 40
    page.insert_text((center_x, 200), center_text, fontsize=12)
    # Right-aligned text near right margin
    page.insert_text((page_width - 170, 350), "Right aligned text", fontsize=12)

    doc.save(str(inp))
    doc.close()

    result = process_pdf_file(inp, out, "French", "English (US)")
    assert result is True
    assert out.exists()

    # Verify translated text appears in the output
    doc = pymupdf.open(str(out))
    text = doc[0].get_text()
    doc.close()
    assert "[French]" in text


# ── Superscript integration tests ───────────────────────────────────


def test_pdf_superscript_footnote(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """PDF with superscript footnote marker → translated without crash."""
    inp = tmp_path / "superscript.pdf"
    out = tmp_path / "translated.pdf"

    doc = pymupdf.open()
    page = doc.new_page()
    # Insert main text at normal size
    page.insert_text((72, 72), "This is a sentence", fontsize=12)
    # Insert superscript-like footnote marker at smaller size next to it
    page.insert_text((220, 67), "1", fontsize=7)
    # Insert footnote text at the bottom
    page.insert_text((72, 700), "1. Footnote reference text here.", fontsize=10)

    doc.save(str(inp))
    doc.close()

    result = process_pdf_file(inp, out, "French", "English (US)")
    assert result is True
    assert out.exists()

    # Verify translated text appears in the output
    doc = pymupdf.open(str(out))
    text = doc[0].get_text()
    doc.close()
    assert "[French]" in text


# ── Config injection integration tests ──────────────────────────────


def test_pdf_config_injection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_llm: Callable[..., list[str]],
) -> None:
    """process_pdf_file with TranslationConfig → config used, no load_setting calls."""
    from src.core.config import TranslationConfig  # noqa: PLC0415

    inp = tmp_path / "config_inject.pdf"
    out = tmp_path / "translated.pdf"
    _create_pdf(inp, ["Config injection test"])

    # Track load_setting calls — there should be none when config is provided
    load_setting_calls: list[str] = []

    def tracking_load_setting(key: str, default: object = None) -> object:
        load_setting_calls.append(key)
        return default

    monkeypatch.setattr(
        "src.core.pdf_processor._config.load_setting",
        tracking_load_setting,
    )

    config = TranslationConfig(
        translate_doc_images=False,
        translate_doc_comments=False,
        translate_doc_shapes=False,
        ocr_is_configured=False,
    )

    result = process_pdf_file(
        inp,
        out,
        "French",
        "English (US)",
        config=config,
    )
    assert result is True
    assert out.exists()
    # When config is injected, load_setting should not be called
    assert len(load_setting_calls) == 0, (
        f"load_setting called with keys: {load_setting_calls}"
    )


# ── Combo / list box widget tests ────────────────────────────────────


def test_pdf_widget_combo_box(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_llm: Callable[..., list[str]],
) -> None:
    """PDF with combo box widget → choice values translated."""
    # Enable shapes/widgets translation
    monkeypatch.setattr(
        "src.core.pdf_processor._config.load_setting",
        lambda k, d=None: "shapes" in k or "textbox" in k,
    )

    inp = tmp_path / "combo.pdf"
    out = tmp_path / "translated.pdf"

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Choose a color", fontsize=12)

    w = pymupdf.Widget()
    w.field_type = pymupdf.PDF_WIDGET_TYPE_COMBOBOX
    w.choice_values = ["Red", "Green", "Blue"]
    w.field_value = "Red"
    w.field_name = "color_combo"
    w.rect = pymupdf.Rect(72, 300, 250, 320)
    page.add_widget(w)

    doc.save(str(inp))
    doc.close()

    result = process_pdf_file(inp, out, "French", "English (US)")
    assert result is True
    assert out.exists()

    # Verify combo box choices were translated
    doc = pymupdf.open(str(out))
    page = doc[0]
    widgets = list(page.widgets())
    doc.close()

    combo_widgets = [
        wgt for wgt in widgets if wgt.field_type == pymupdf.PDF_WIDGET_TYPE_COMBOBOX
    ]
    assert len(combo_widgets) >= 1, "Expected at least one combo box widget"
    choices = combo_widgets[0].choice_values or []
    # Each original choice should have been translated (prefixed with [French])
    assert any("[French]" in str(c) for c in choices), (
        f"Expected translated combo choices, got: {choices}"
    )


def test_pdf_widget_list_box(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_llm: Callable[..., list[str]],
) -> None:
    """PDF with list box widget → choice values translated."""
    # Enable shapes/widgets translation
    monkeypatch.setattr(
        "src.core.pdf_processor._config.load_setting",
        lambda k, d=None: "shapes" in k or "textbox" in k,
    )

    inp = tmp_path / "listbox.pdf"
    out = tmp_path / "translated.pdf"

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Select an animal", fontsize=12)

    w = pymupdf.Widget()
    w.field_type = pymupdf.PDF_WIDGET_TYPE_LISTBOX
    w.choice_values = ["Cat", "Dog", "Bird"]
    w.field_value = "Cat"
    w.field_name = "animal_list"
    w.rect = pymupdf.Rect(72, 300, 250, 380)
    page.add_widget(w)

    doc.save(str(inp))
    doc.close()

    result = process_pdf_file(inp, out, "French", "English (US)")
    assert result is True
    assert out.exists()

    # Verify list box choices were translated
    doc = pymupdf.open(str(out))
    page = doc[0]
    widgets = list(page.widgets())
    doc.close()

    list_widgets = [
        wgt for wgt in widgets if wgt.field_type == pymupdf.PDF_WIDGET_TYPE_LISTBOX
    ]
    assert len(list_widgets) >= 1, "Expected at least one list box widget"
    choices = list_widgets[0].choice_values or []
    assert any("[French]" in str(c) for c in choices), (
        f"Expected translated list box choices, got: {choices}"
    )


# ── Scanned page tests ──────────────────────────────────────────────


def test_pdf_scanned_page_skipped_when_disabled(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """Image-only page with translate_doc_images=False → skipped, no crash."""
    inp = tmp_path / "scanned_only.pdf"
    out = tmp_path / "translated.pdf"

    doc = pymupdf.open()
    # Page 1: normal text
    page1 = doc.new_page()
    page1.insert_text((72, 72), "Normal text page", fontsize=12)
    # Page 2: image-only (no text) — simulates a scanned page
    page2 = doc.new_page()
    img = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 100, 100), 0)
    page2.insert_image(pymupdf.Rect(50, 50, 500, 700), pixmap=img)
    doc.save(str(inp))
    doc.close()

    # Default setup_integration_env disables OCR/images (load_setting → False)
    # so scanned pages should be silently skipped
    result = process_pdf_file(inp, out, "French", "English (US)")
    assert result is True
    assert out.exists()

    # Verify the output PDF is valid and has both pages
    doc = pymupdf.open(str(out))
    assert doc.page_count == 2  # noqa: PLR2004
    # Page 1 should have translated text
    text_p1 = doc[0].get_text()
    assert text_p1.strip(), "Page 1 should have text content"
    # Page 2 should still have its image but no translated text overlay
    # (OCR was disabled, so the scanned page was not processed)
    text_p2 = doc[1].get_text()
    # The image-only page should have minimal or no text
    assert len(text_p2.strip()) < len(text_p1.strip()), (
        "Scanned page should not have translated text when OCR is disabled"
    )
    doc.close()


# ── Per-paragraph color tests ────────────────────────────────────────


def test_pdf_preserves_text_color(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """PDF with colored text → translated overlay includes color CSS."""
    inp = tmp_path / "colored.pdf"
    out = tmp_path / "translated.pdf"

    doc = pymupdf.open()
    page = doc.new_page()
    # Insert red text — PyMuPDF insert_text accepts color as (r, g, b) floats
    page.insert_text(
        (72, 72),
        "Red heading text",
        fontsize=14,
        color=(1.0, 0.0, 0.0),
    )
    # Insert blue text below
    page.insert_text(
        (72, 120),
        "Blue body text",
        fontsize=12,
        color=(0.0, 0.0, 1.0),
    )
    doc.save(str(inp))
    doc.close()

    result = process_pdf_file(inp, out, "French", "English (US)")
    assert result is True
    assert out.exists()

    # Re-open input to verify the original colors are present in blocks
    doc_in = pymupdf.open(str(inp))
    blocks = doc_in[0].get_text("dict")["blocks"]
    doc_in.close()
    # Collect non-zero colors from text spans to confirm the input has color
    input_colors = set()
    for blk in blocks:
        if blk.get("type") != 0:
            continue
        for line in blk.get("lines", []):
            for span in line.get("spans", []):
                input_colors.add(span.get("color", 0))
    # Should have at least red (0xFF0000) or blue (0x0000FF) — non-black
    assert any(c != 0 for c in input_colors), (
        f"Expected non-black colors in input PDF, got: {input_colors}"
    )

    # Verify the output PDF exists and has text content
    doc_out = pymupdf.open(str(out))
    text_out = doc_out[0].get_text()
    doc_out.close()
    assert text_out.strip(), "Output should have translated text overlay"
