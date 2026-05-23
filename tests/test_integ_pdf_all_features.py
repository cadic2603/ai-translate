"""Integration test: PDF with all features simultaneously.

Builds a real PDF containing text blocks (single-line + multi-line),
a bookmark/TOC entry, a form field, an embedded image, a comment annotation,
and a hyperlink.  Then exercises the full PDF translation pipeline with
images, comments, and shapes/widgets all enabled.

LLM and image-translation pipeline are mocked; PyMuPDF runs for real.
"""

from __future__ import annotations

from collections.abc import Callable, Generator
from pathlib import Path
from typing import Any

import pytest

pymupdf = pytest.importorskip("pymupdf")

from src.core.database import init_db  # noqa: E402
from src.core.pdf_processor import process_pdf_file  # noqa: E402

# A 1×1 white PNG used as the embedded image.
_PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xff"
    b"\xff?\x00\x05\xfe\x02\xfe\xa3\x9b\x99\x9c\x00\x00\x00\x00IEND\xaeB`\x82"
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
    yield


@pytest.fixture()
def mock_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[..., list[str]]:
    """Mocks translate_text so every input gets a "[lang] " prefix."""

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


def _build_full_feature_pdf(path: Path) -> dict[str, Any]:
    """Builds a 2-page PDF with every translatable feature exercised.

    Returns a dict describing the original content (texts, link uri, etc.)
    so the test can assert exact recovery.
    """
    doc = pymupdf.open()

    # ── Page 0 ────────────────────────────────────────────────────────
    page0 = doc.new_page()
    # Single-line block
    page0.insert_text((72, 72), "Single line block", fontsize=12)
    # Multi-line block (separate insert_textbox call)
    page0.insert_textbox(
        pymupdf.Rect(72, 120, 500, 250),
        (
            "First line of multi line block. "
            "Second line of multi line block. "
            "Third line of multi line block."
        ),
        fontsize=11,
    )
    # Hyperlink: insert visible text, then attach a link rect on it.
    link_text = "click here"
    body = f"Visit our site, {link_text} for more info."
    page0.insert_text((72, 320), body, fontsize=12)
    hits = page0.search_for(link_text)
    link_uri = "https://example.org/landing?lang=en"
    if hits:
        page0.insert_link({"kind": 2, "from": hits[0], "uri": link_uri})

    # Comment annotation (sticky note)
    annot = page0.add_text_annot((420, 72), "Reviewer note text")
    annot.set_info(content="Reviewer note text", title="Reviewer")
    annot.update()

    # Embedded image (raster)
    img_rect = pymupdf.Rect(72, 400, 220, 500)
    page0.insert_image(img_rect, stream=_PNG_1X1)

    # Text form field (widget)
    widget = pymupdf.Widget()
    widget.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
    widget.field_value = "Enter address"
    widget.field_name = "addr_field"
    widget.rect = pymupdf.Rect(72, 540, 400, 580)
    page0.add_widget(widget)

    # ── Page 1 ────────────────────────────────────────────────────────
    page1 = doc.new_page()
    page1.insert_text((72, 72), "Page two body text", fontsize=12)

    # Set bookmarks/TOC: one entry per page.
    doc.set_toc(
        [
            [1, "Chapter One", 1],
            [1, "Chapter Two", 2],
        ]
    )

    doc.save(str(path))
    doc.close()
    return {
        "link_uri": link_uri,
        "field_name": "addr_field",
    }


def _read_annotations(path: Path) -> list[str]:
    """Read every annotation content string from a PDF."""
    doc = pymupdf.open(str(path))
    contents: list[str] = []
    for page in doc:
        annots = page.annots()
        if annots is None:
            continue
        for annot in annots:
            content = annot.info.get("content", "")
            if content:
                contents.append(content)
    doc.close()
    return contents


# ── The single end-to-end test ───────────────────────────────────────


def test_pdf_with_every_feature_translated(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One PDF, every feature: text + bookmark + form field + image + link + comment.

    Asserts every translatable element ends up translated and structural
    metadata (link URI, TOC structure, widget field name) is preserved.
    """
    # Enable images, comments, and shapes/textboxes (which gates widgets).
    truthy_keys = {"image", "comment", "shape", "textbox"}

    def fake_load_setting(key: str, default: object = None) -> object:
        if any(k in (key or "").lower() for k in truthy_keys):
            return True
        return default

    monkeypatch.setattr(
        "src.core.pdf_processor._config.load_setting",
        fake_load_setting,
    )
    # OCR is "configured" so should_translate_images evaluates True.
    monkeypatch.setattr(
        "src.core.pdf_processor._config.check_ocr_setup",
        lambda: True,
    )

    # Stub the embedded-image translation pipeline so we don't need a real
    # OCR model.  The spy verifies _translate_page_images was invoked.
    image_calls: list[object] = []

    def spy_translate_page_images(*args: object, **kwargs: object) -> None:
        image_calls.append((args, kwargs))

    monkeypatch.setattr(
        "src.core.pdf_processor._translate_page_images",
        spy_translate_page_images,
    )

    inp = tmp_path / "all_features.pdf"
    out = tmp_path / "translated.pdf"
    meta = _build_full_feature_pdf(inp)

    result = process_pdf_file(
        inp,
        out,
        "French",
        "English (US)",
    )
    assert result is True
    assert out.exists()

    doc = pymupdf.open(str(out))
    try:
        # ── Body text translated on both pages ──
        page0_text = doc[0].get_text()
        page1_text = doc[1].get_text()
        # On page 0, both single-line and multi-line should be translated.
        # The mock prefixes each LLM input with "[French] " so the marker
        # must appear in the rendered output.
        assert "[French]" in page0_text
        assert "[French]" in page1_text

        # ── Bookmarks/TOC translated ──
        toc = doc.get_toc()
        assert len(toc) == 2
        assert all("[French]" in entry[1] for entry in toc), (
            f"Bookmark titles should be translated: {toc}"
        )
        # TOC structure (level, page) preserved.
        assert [e[0] for e in toc] == [1, 1]
        assert [e[2] for e in toc] == [1, 2]

        # ── Form field translated, name preserved ──
        widgets = list(doc[0].widgets() or [])
        assert len(widgets) >= 1
        addr_widgets = [w for w in widgets if w.field_name == meta["field_name"]]
        assert addr_widgets, (
            f"Form field '{meta['field_name']}' should be preserved, "
            f"got {[w.field_name for w in widgets]}"
        )
        assert any("[French]" in (w.field_value or "") for w in addr_widgets), (
            f"Form field value should be translated, "
            f"got: {[w.field_value for w in addr_widgets]}"
        )

        # ── Hyperlink URI preserved ──
        links = doc[0].get_links()
        assert any(lk.get("uri") == meta["link_uri"] for lk in links), (
            f"Hyperlink URI must be preserved, got: {[lk.get('uri') for lk in links]}"
        )

        # ── Comment annotation translated ──
        contents = _read_annotations(out)
        assert any("[French]" in c for c in contents), (
            f"Comment annotation should be translated: {contents}"
        )
    finally:
        doc.close()

    # ── Image translation pipeline was invoked at least once ──
    assert image_calls, "_translate_page_images should have been called"
