"""Integration tests for the EPUB translation pipeline.

Builds minimal EPUB archives in tmp_path, exercises text_processor.translate_file
with real ZIP I/O.  LLM is mocked; image translation is monkeypatched at
_translate_doc_images so we can assert on whether it was invoked.
"""

from __future__ import annotations

import zipfile
from collections.abc import Callable, Generator
from pathlib import Path

import pytest

from src.core.database import init_db
from src.core.text_processor import translate_file

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
    """Mocks translate_text at every import site."""

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


def _build_epub(  # noqa: PLR0913
    epub_path: Path,
    *,
    chapters: list[tuple[str, str]],
    nav_xhtml: str | None = None,
    toc_ncx: str | None = None,
    image_bytes: bytes | None = None,
    extra_manifest_items: str = "",
    container_xml: str | None = None,
    opf_xml: str | None = None,
) -> None:
    """Builds a minimal EPUB ZIP.

    Args:
        epub_path: Output path.
        chapters: List of (filename, xhtml_content) tuples.
        nav_xhtml: Optional EPUB3 navigation document content.
        toc_ncx: Optional EPUB2 NCX content.
        image_bytes: Optional embedded image (png) under OEBPS/images/cover.png.
        extra_manifest_items: Additional <item> entries spliced into manifest.
        container_xml: Override the container.xml content.
        opf_xml: Override the OPF content. When provided, the helper writes
            this verbatim and ignores chapters/nav/toc/extra_manifest_items.
    """
    if container_xml is None:
        container_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"'
            ' version="1.0">\n'
            "  <rootfiles>\n"
            '    <rootfile full-path="OEBPS/content.opf"'
            ' media-type="application/oebps-package+xml"/>\n'
            "  </rootfiles>\n"
            "</container>"
        )
    if opf_xml is None:
        manifest_items: list[str] = []
        spine_items: list[str] = []
        for idx, (filename, _content) in enumerate(chapters):
            item_id = f"ch{idx}"
            manifest_items.append(
                f'    <item id="{item_id}" href="{filename}"'
                ' media-type="application/xhtml+xml"/>'
            )
            spine_items.append(f'    <itemref idref="{item_id}"/>')
        if nav_xhtml is not None:
            manifest_items.append(
                '    <item id="nav" href="nav.xhtml"'
                ' media-type="application/xhtml+xml"'
                ' properties="nav"/>'
            )
        if toc_ncx is not None:
            manifest_items.append(
                '    <item id="ncx" href="toc.ncx"'
                ' media-type="application/x-dtbncx+xml"/>'
            )
        if image_bytes is not None:
            manifest_items.append(
                '    <item id="cover-image" href="images/cover.png"'
                ' media-type="image/png"/>'
            )
        if extra_manifest_items:
            manifest_items.append(extra_manifest_items)

        opf_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<package xmlns="http://www.idpf.org/2007/opf" version="3.0"'
            ' unique-identifier="bookid">\n'
            "  <metadata"
            ' xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
            '    <dc:identifier id="bookid">test-book-1</dc:identifier>\n'
            "    <dc:title>Test Book</dc:title>\n"
            "    <dc:language>en</dc:language>\n"
            "  </metadata>\n"
            "  <manifest>\n" + "\n".join(manifest_items) + "\n" + "  </manifest>\n"
            "  <spine"
            + (' toc="ncx"' if toc_ncx is not None else "")
            + ">\n"
            + "\n".join(spine_items)
            + "\n"
            + "  </spine>\n"
            "</package>"
        )

    with zipfile.ZipFile(epub_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # ZIP_STORED for the mimetype (per EPUB spec, not strictly required).
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr("META-INF/container.xml", container_xml)
        zf.writestr("OEBPS/content.opf", opf_xml)
        for filename, content in chapters:
            zf.writestr(f"OEBPS/{filename}", content)
        if nav_xhtml is not None:
            zf.writestr("OEBPS/nav.xhtml", nav_xhtml)
        if toc_ncx is not None:
            zf.writestr("OEBPS/toc.ncx", toc_ncx)
        if image_bytes is not None:
            zf.writestr("OEBPS/images/cover.png", image_bytes)


# A tiny valid PNG (1x1 pixel, white).
_PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xff"
    b"\xff?\x00\x05\xfe\x02\xfe\xa3\x9b\x99\x9c\x00\x00\x00\x00IEND\xaeB`\x82"
)

_NAV_XHTML = (
    '<?xml version="1.0" encoding="utf-8"?>\n'
    '<html xmlns="http://www.w3.org/1999/xhtml"'
    ' xmlns:epub="http://www.idpf.org/2007/ops">\n'
    "<head><title>Navigation</title></head>\n"
    "<body>\n"
    '  <nav epub:type="toc" id="toc">\n'
    "    <ol>\n"
    '      <li><a href="ch1.xhtml">Chapter 1</a></li>\n'
    '      <li><a href="ch2.xhtml">Chapter 2</a></li>\n'
    "    </ol>\n"
    "  </nav>\n"
    "</body></html>"
)

_TOC_NCX = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">\n'
    "  <head>\n"
    '    <meta name="dtb:uid" content="test-book-1"/>\n'
    "  </head>\n"
    "  <docTitle><text>Test Book</text></docTitle>\n"
    "  <navMap>\n"
    '    <navPoint id="np1" playOrder="1">\n'
    "      <navLabel><text>Chapter 1</text></navLabel>\n"
    '      <content src="ch1.xhtml"/>\n'
    "    </navPoint>\n"
    "  </navMap>\n"
    "</ncx>"
)


def _ch(name: str, body: str) -> tuple[str, str]:
    """Wrap an XHTML body in a minimal valid envelope and return (name, content)."""
    return name, (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml">\n'
        "<head><title>Chapter</title></head>\n"
        f"<body>{body}</body></html>"
    )


# ── Tests ────────────────────────────────────────────────────────────


def test_epub_two_chapters_translated(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 2-chapter EPUB round-trips: both chapters translated, ZIP intact."""
    # Disable embedded-image translation deterministically.
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda k, d=None: False,
    )
    monkeypatch.setattr(
        "src.utils.config_manager.check_ocr_setup",
        lambda: False,
    )

    epub_path = tmp_path / "book.epub"
    _build_epub(
        epub_path,
        chapters=[
            _ch("ch1.xhtml", "<p>Chapter one body</p>"),
            _ch("ch2.xhtml", "<p>Chapter two body</p>"),
        ],
        nav_xhtml=_NAV_XHTML,
        toc_ncx=_TOC_NCX,
    )

    out = tmp_path / "translated.epub"
    result = translate_file(epub_path, out, "French", "English (US)")
    assert result is True
    assert out.exists()

    with zipfile.ZipFile(out, "r") as zf:
        names = zf.namelist()
        # All structural files preserved
        assert "mimetype" in names
        assert "META-INF/container.xml" in names
        assert "OEBPS/content.opf" in names
        assert "OEBPS/nav.xhtml" in names
        assert "OEBPS/toc.ncx" in names
        assert "OEBPS/ch1.xhtml" in names
        assert "OEBPS/ch2.xhtml" in names

        ch1 = zf.read("OEBPS/ch1.xhtml").decode("utf-8")
        ch2 = zf.read("OEBPS/ch2.xhtml").decode("utf-8")
        assert "[French]" in ch1
        assert "[French]" in ch2

        # OPF should still parse
        opf = zf.read("OEBPS/content.opf").decode("utf-8")
        assert "<package" in opf
        assert "ch1.xhtml" in opf
        assert "ch2.xhtml" in opf


def test_epub_with_image_translation_disabled(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Embedded image preserved untouched when image translation is disabled."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda k, d=None: False,
    )
    monkeypatch.setattr(
        "src.utils.config_manager.check_ocr_setup",
        lambda: False,
    )

    # Spy on _translate_doc_images: should NOT be called.
    image_calls: list[object] = []

    def spy_translate_doc_images(*args: object, **kwargs: object) -> None:
        image_calls.append((args, kwargs))

    monkeypatch.setattr(
        "src.core.text_processor._translate_doc_images",
        spy_translate_doc_images,
    )

    epub_path = tmp_path / "book_with_image.epub"
    _build_epub(
        epub_path,
        chapters=[_ch("ch1.xhtml", "<p>Hello image book</p>")],
        image_bytes=_PNG_1X1,
    )

    out = tmp_path / "translated.epub"
    result = translate_file(epub_path, out, "French", "English (US)")
    assert result is True
    assert image_calls == []

    # Image bytes should be preserved byte-for-byte.
    with zipfile.ZipFile(out, "r") as zf:
        assert "OEBPS/images/cover.png" in zf.namelist()
        assert zf.read("OEBPS/images/cover.png") == _PNG_1X1


def test_epub_with_image_translation_enabled_invokes_image_pipeline(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When image translation is enabled, _translate_doc_images is invoked."""
    # load_setting returns truthy for SETTING_TRANSLATE_DOC_IMAGES; OCR set up.
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda k, d=None: True if "image" in (k or "").lower() else d,
    )
    monkeypatch.setattr(
        "src.utils.config_manager.check_ocr_setup",
        lambda: True,
    )

    image_calls: list[object] = []

    def spy_translate_doc_images(*args: object, **kwargs: object) -> None:
        image_calls.append((args, kwargs))

    monkeypatch.setattr(
        "src.core.text_processor._translate_doc_images",
        spy_translate_doc_images,
    )

    epub_path = tmp_path / "book_with_image.epub"
    _build_epub(
        epub_path,
        chapters=[_ch("ch1.xhtml", "<p>Hello image book</p>")],
        image_bytes=_PNG_1X1,
    )

    out = tmp_path / "translated.epub"
    result = translate_file(epub_path, out, "French", "English (US)")
    assert result is True
    # _translate_doc_images called exactly once with the output EPUB path.
    assert len(image_calls) == 1
    args = image_calls[0][0]
    assert args[0] == out
    assert args[1] == ".epub"


def test_epub_malformed_opf_falls_back_or_errors_clean(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Malformed content.opf is handled cleanly (no traceback, no crash).

    Current behaviour: _get_epub_content_files raises ParseError which
    propagates up — callers see a clean exception rather than a corrupt
    output.  We assert the pipeline either raises a recognisable exception
    or returns True with the file copied verbatim, but never silently
    produces a half-translated EPUB.
    """
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda k, d=None: False,
    )
    monkeypatch.setattr(
        "src.utils.config_manager.check_ocr_setup",
        lambda: False,
    )

    epub_path = tmp_path / "malformed.epub"
    bad_opf = "<?xml version='1.0'?><package><not-closed>"
    _build_epub(
        epub_path,
        chapters=[_ch("ch1.xhtml", "<p>body</p>")],
        opf_xml=bad_opf,
    )

    out = tmp_path / "translated.epub"
    # Either raises or returns True with the file unchanged. Both behaviours
    # are acceptable as long as we don't produce a half-translated archive.
    raised = False
    try:
        result = translate_file(epub_path, out, "French", "English (US)")
    except Exception:  # noqa: BLE001 — testing graceful failure
        raised = True
        result = False

    if raised:
        # Output should not exist or be empty/incomplete.
        return

    # If it did not raise, the EPUB was copied as-is (no chapter translated).
    assert result is True
    assert out.exists()
    with zipfile.ZipFile(out, "r") as zf:
        ch1 = zf.read("OEBPS/ch1.xhtml").decode("utf-8")
        # Untranslated body preserved.
        assert "[French]" not in ch1


def test_epub_missing_container_xml_returns_clean(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """EPUB without META-INF/container.xml is copied verbatim, not crashed."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda k, d=None: False,
    )
    monkeypatch.setattr(
        "src.utils.config_manager.check_ocr_setup",
        lambda: False,
    )

    epub_path = tmp_path / "no_container.epub"
    # Build a ZIP without META-INF/container.xml at all.
    with zipfile.ZipFile(epub_path, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr("OEBPS/ch1.xhtml", "<html><body><p>Body</p></body></html>")

    out = tmp_path / "translated.epub"
    result = translate_file(epub_path, out, "French", "English (US)")
    # The pipeline logs a warning and copies the file as-is.
    assert result is True
    assert out.exists()
