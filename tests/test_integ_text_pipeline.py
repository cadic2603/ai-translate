"""Integration tests for the text file translation pipeline.

Exercises translate_file() with real file I/O, real DB, and real
checkpoints.  Only the LLM is mocked (returns "[target] text").
"""

import json
import re
import zipfile
from collections.abc import Callable, Generator
from pathlib import Path

import pytest

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


# ── Helpers ──────────────────────────────────────────────────────────


def _write(
    tmp_path: Path,
    name: str,
    content: str,
    encoding: str = "utf-8",
) -> tuple[Path, Path]:
    """Write a file and return (input_path, output_path)."""
    inp = tmp_path / name
    inp.write_text(content, encoding=encoding)
    out = tmp_path / f"translated_{name}"
    return inp, out


def _write_bytes(
    tmp_path: Path,
    name: str,
    data: bytes,
) -> tuple[Path, Path]:
    """Write raw bytes and return (input_path, output_path)."""
    inp = tmp_path / name
    inp.write_bytes(data)
    out = tmp_path / f"translated_{name}"
    return inp, out


# ── Basic round-trip per format ──────────────────────────────────────


def test_txt_roundtrip(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """Plain .txt with 2 paragraphs separated by blank line."""
    inp, out = _write(tmp_path, "sample.txt", "Hello world\n\nGoodbye world")
    result = translate_file(inp, out, "French", "English (US)")
    assert result is True
    text = out.read_text(encoding="utf-8")
    assert "[French]" in text
    # Both paragraphs translated
    assert "Hello" not in text or "[French] Hello world" in text


def test_html_preserves_tags(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """HTML tags and attributes must survive translation."""
    html_content = '<h1 class="title">Title</h1>\n<p>Body</p>'
    inp, out = _write(tmp_path, "page.html", html_content)
    result = translate_file(inp, out, "French", "English (US)")
    assert result is True
    text = out.read_text(encoding="utf-8")
    # Tags preserved
    assert "<h1" in text
    assert "<p>" in text or "<p " in text


def test_srt_preserves_timing(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """SRT timestamps and sequence numbers must be unchanged."""
    srt = (
        "1\n00:00:01,000 --> 00:00:04,000\nHello world\n\n"
        "2\n00:00:05,000 --> 00:00:08,000\nGoodbye world\n\n"
        "3\n00:00:09,000 --> 00:00:12,000\nSee you\n"
    )
    inp, out = _write(tmp_path, "sub.srt", srt)
    result = translate_file(inp, out, "French", "English (US)")
    assert result is True
    text = out.read_text(encoding="utf-8")
    assert "00:00:01,000 --> 00:00:04,000" in text
    assert "00:00:05,000 --> 00:00:08,000" in text
    assert "[French]" in text


def test_vtt_preserves_format(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """WEBVTT header and timestamps must be preserved."""
    vtt = (
        "WEBVTT\n\n"
        "00:00:01.000 --> 00:00:04.000\nHello\n\n"
        "00:00:05.000 --> 00:00:08.000\nWorld\n\n"
        "00:00:09.000 --> 00:00:12.000\nGoodbye\n"
    )
    inp, out = _write(tmp_path, "sub.vtt", vtt)
    result = translate_file(inp, out, "French", "English (US)")
    assert result is True
    text = out.read_text(encoding="utf-8")
    assert "WEBVTT" in text
    assert "00:00:01.000 --> 00:00:04.000" in text
    assert "[French]" in text


def test_json_preserves_structure(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """JSON keys, ints, and nesting must be unchanged."""
    data = {"title": "Hello", "count": 42, "items": ["World", "Foo"]}
    inp, out = _write(tmp_path, "data.json", json.dumps(data))
    result = translate_file(inp, out, "French", "English (US)")
    assert result is True
    parsed = json.loads(out.read_text(encoding="utf-8"))
    assert parsed["count"] == 42  # noqa: PLR2004
    assert isinstance(parsed["items"], list)
    assert len(parsed["items"]) == 2  # noqa: PLR2004
    assert "[French]" in parsed["title"]


def test_csv_preserves_rows(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """CSV row/column count must be preserved."""
    csv_content = "Name,City\nAlice,Paris\nBob,London"
    inp, out = _write(tmp_path, "data.csv", csv_content)
    result = translate_file(inp, out, "French", "English (US)")
    assert result is True
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3  # noqa: PLR2004
    # Each row still has 2 columns
    for line in lines:
        assert "," in line


def test_md_roundtrip(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """Markdown heading syntax and URLs must survive."""
    md = "# Heading\n\nSome paragraph text.\n\n[link](https://example.com)"
    inp, out = _write(tmp_path, "doc.md", md)
    result = translate_file(inp, out, "French", "English (US)")
    assert result is True
    text = out.read_text(encoding="utf-8")
    assert "#" in text  # heading marker preserved
    assert "https://example.com" in text


def test_xml_preserves_attributes(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """XML attributes must be preserved after translation."""
    xml = '<root><item id="1">Hello</item></root>'
    inp, out = _write(tmp_path, "data.xml", xml)
    result = translate_file(inp, out, "French", "English (US)")
    assert result is True
    text = out.read_text(encoding="utf-8")
    assert 'id="1"' in text or "id='1'" in text


def test_po_preserves_structure(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """PO msgid must be untouched; msgstr should be filled."""
    po = (
        '# comment\nmsgid ""\nmsgstr ""\n'
        '"Content-Type: text/plain; charset=UTF-8\\n"\n\n'
        'msgid "Hello"\nmsgstr ""\n\n'
        'msgid "World"\nmsgstr ""\n'
    )
    inp, out = _write(tmp_path, "messages.po", po)
    result = translate_file(inp, out, "French", "English (US)")
    assert result is True
    text = out.read_text(encoding="utf-8")
    assert 'msgid "Hello"' in text
    assert "[French]" in text


def test_yaml_preserves_keys(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """YAML keys must be unchanged; values translated."""
    yaml_content = "greeting: Hello\nfarewell: Goodbye\n"
    inp, out = _write(tmp_path, "strings.yaml", yaml_content)
    result = translate_file(inp, out, "French", "English (US)")
    assert result is True
    text = out.read_text(encoding="utf-8")
    assert "greeting:" in text
    assert "farewell:" in text
    assert "[French]" in text


def test_properties_roundtrip(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """Java .properties keys unchanged, values translated."""
    content = "app.name=My App\napp.greeting=Hello World\n"
    inp, out = _write(tmp_path, "messages.properties", content)
    result = translate_file(inp, out, "French", "English (US)")
    assert result is True
    text = out.read_text(encoding="utf-8")
    assert "app.name" in text
    assert "[French]" in text


def test_strings_roundtrip(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """Apple .strings keys unchanged, values translated."""
    content = '"greeting" = "Hello";\n"farewell" = "Goodbye";\n'
    inp, out = _write(tmp_path, "Localizable.strings", content)
    result = translate_file(inp, out, "French", "English (US)")
    assert result is True
    text = out.read_text(encoding="utf-8")
    assert '"greeting"' in text
    assert "[French]" in text


# ── Edge cases ───────────────────────────────────────────────────────


def test_txt_with_bom(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """UTF-8 BOM must be stripped; content translated correctly."""
    bom = b"\xef\xbb\xbf"
    content = bom + b"Hello world"
    inp, out = _write_bytes(tmp_path, "bom.txt", content)
    result = translate_file(inp, out, "French", "English (US)")
    assert result is True
    text = out.read_text(encoding="utf-8")
    assert "[French]" in text
    assert not text.startswith("\ufeff")


def test_txt_empty_file(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """Empty file should produce empty output, no LLM call."""
    inp, out = _write(tmp_path, "empty.txt", "")
    result = translate_file(inp, out, "French", "English (US)")
    assert result is True
    assert out.read_text(encoding="utf-8") == ""


def test_txt_whitespace_only(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """Whitespace-only file should produce output, no LLM call."""
    inp, out = _write(tmp_path, "ws.txt", "   \n\n   \n")
    result = translate_file(inp, out, "French", "English (US)")
    assert result is True
    assert out.exists()


def test_txt_large_file_chunking(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """A large file must be chunked; all paragraphs translated."""
    # 25 paragraphs of ~200 chars each → multiple chunks (3000 chars/chunk)
    paragraphs = [f"Paragraph {i}: " + "word " * 60 for i in range(25)]
    content = "\n\n".join(paragraphs)
    inp, out = _write(tmp_path, "large.txt", content)
    progress_values: list[int] = []
    result = translate_file(
        inp,
        out,
        "French",
        "English (US)",
        progress_callback=progress_values.append,
    )
    assert result is True
    text = out.read_text(encoding="utf-8")
    assert "[French]" in text
    # Progress called at least once
    assert len(progress_values) >= 1


def test_json_invalid_syntax(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """Malformed JSON should raise ValueError (JSON decode or TEXT_READ_ERROR)."""
    inp, out = _write(tmp_path, "bad.json", "{bad:}")
    with pytest.raises((ValueError, Exception)):
        translate_file(inp, out, "French", "English (US)")


def test_rtf_roundtrip(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """RTF file → content translated, output file valid."""
    # Minimal RTF content with a visible text paragraph
    rtf_content = r"{\rtf1\ansi Hello world\par Goodbye world\par}"
    inp, out = _write(tmp_path, "doc.rtf", rtf_content)
    result = translate_file(inp, out, "French", "English (US)")
    assert result is True
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert "[French]" in text


def test_ass_subtitle_roundtrip(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """ASS subtitle: dialogue text translated, non-dialogue lines preserved."""
    ass_content = (
        "[Script Info]\nScriptType: v4.00+\n\n"
        "[V4+ Styles]\nFormat: Name, Fontname\nStyle: Default,Arial\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, Text\n"
        "Dialogue: 0,0:00:01.00,0:00:04.00,Default,,Hello world\n"
        "Dialogue: 0,0:00:05.00,0:00:08.00,Default,,Goodbye world\n"
    )
    inp, out = _write(tmp_path, "sub.ass", ass_content)
    result = translate_file(inp, out, "French", "English (US)")
    assert result is True
    text = out.read_text(encoding="utf-8")
    # Header sections preserved
    assert "[Events]" in text
    # Dialogue text translated
    assert "[French]" in text
    # Timing preserved
    assert "0:00:01.00" in text


def test_ssa_subtitle_roundtrip(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """SSA subtitle (older format): dialogue text translated."""
    ssa_content = (
        "[Script Info]\nScriptType: v4.00\n\n"
        "[Events]\nFormat: Marked, Start, End, Style, Name, Text\n"
        "Dialogue: Marked=0,0:00:01.00,0:00:04.00,Default,,See you\n"
    )
    inp, out = _write(tmp_path, "sub.ssa", ssa_content)
    result = translate_file(inp, out, "French", "English (US)")
    assert result is True
    text = out.read_text(encoding="utf-8")
    assert "[French]" in text
    assert "0:00:01.00" in text


def test_xliff_12_roundtrip(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """XLIFF 1.2: source elements left unchanged, target filled with translation."""
    xliff_content = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2">\n'
        '  <file source-language="en" target-language="fr">\n'
        "    <body>\n"
        '      <trans-unit id="1">\n'
        "        <source>Hello world</source>\n"
        "        <target></target>\n"
        "      </trans-unit>\n"
        '      <trans-unit id="2">\n'
        "        <source>Goodbye world</source>\n"
        "        <target></target>\n"
        "      </trans-unit>\n"
        "    </body>\n"
        "  </file>\n"
        "</xliff>\n"
    )
    inp, out = _write(tmp_path, "messages.xliff", xliff_content)
    result = translate_file(inp, out, "French", "English (US)")
    assert result is True
    text = out.read_text(encoding="utf-8")
    # Source text preserved
    assert "Hello world" in text
    # Translation present
    assert "[French]" in text


def test_txt_cancel_returns_false(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """cancel_check=lambda: True aborts translation and returns False."""
    paragraphs = [f"Paragraph {i}: " + "word " * 20 for i in range(10)]
    content = "\n\n".join(paragraphs)
    inp, out = _write(tmp_path, "cancel.txt", content)
    result = translate_file(
        inp,
        out,
        "French",
        "English (US)",
        cancel_check=lambda: True,
    )
    assert result is False


def test_txt_src_lang_forwarded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """source_lang parameter is forwarded to translate_text."""
    captured: dict[str, str] = {}

    def tracking_translate(
        texts: list[str],
        target_lang: str,
        source_lang: str = "",
        **kwargs: object,
    ) -> list[str]:
        captured["source_lang"] = source_lang
        return [f"[{target_lang}] {t}" for t in texts]

    monkeypatch.setattr("src.core.llm_engine.translate_text", tracking_translate)
    monkeypatch.setattr(
        "src.core.text_processor._llm_engine.translate_text", tracking_translate
    )

    inp, out = _write(tmp_path, "src.txt", "Hello world")
    translate_file(inp, out, "French", "English (US)")
    assert captured.get("source_lang") == "English (US)"


def test_epub_roundtrip(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Minimal EPUB with 2 content files: both translated, ZIP intact."""
    # Disable image translation — patch at source modules since EPUB imports locally
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

    out = tmp_path / "translated_book.epub"
    result = translate_file(epub_path, out, "French", "English (US)")
    assert result is True
    assert out.exists()
    # Verify ZIP structure
    with zipfile.ZipFile(out, "r") as zf:
        names = zf.namelist()
        assert "OEBPS/ch1.xhtml" in names
        assert "OEBPS/ch2.xhtml" in names
        ch1 = zf.read("OEBPS/ch1.xhtml").decode("utf-8")
        assert "[French]" in ch1


# ── Missing format round-trips ──────────────────────────────────────


def test_rst_roundtrip(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """reStructuredText: headings and directives survive translation."""
    rst = (
        "============\n"
        "Main Heading\n"
        "============\n\n"
        "A paragraph of body text.\n\n"
        ".. note::\n\n"
        "   This is a note directive.\n"
    )
    inp, out = _write(tmp_path, "doc.rst", rst)
    result = translate_file(inp, out, "French", "English (US)")
    assert result is True
    text = out.read_text(encoding="utf-8")
    assert "[French]" in text


def test_pot_preserves_structure(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """POT template: msgid untouched, msgstr filled with translation."""
    pot = (
        '# POT template\nmsgid ""\nmsgstr ""\n'
        '"Content-Type: text/plain; charset=UTF-8\\n"\n\n'
        'msgid "Save"\nmsgstr ""\n\n'
        'msgid "Cancel"\nmsgstr ""\n'
    )
    inp, out = _write(tmp_path, "messages.pot", pot)
    result = translate_file(inp, out, "French", "English (US)")
    assert result is True
    text = out.read_text(encoding="utf-8")
    assert 'msgid "Save"' in text
    assert 'msgid "Cancel"' in text
    assert "[French]" in text


def test_xliff_20_roundtrip(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """XLIFF 2.0: source preserved, target filled with translation."""
    xliff20 = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<xliff xmlns="urn:oasis:names:tc:xliff:document:2.0"'
        ' version="2.0" srcLang="en" trgLang="fr">\n'
        '  <file id="f1">\n'
        '    <unit id="u1">\n'
        "      <segment>\n"
        "        <source>Hello world</source>\n"
        "      </segment>\n"
        "    </unit>\n"
        '    <unit id="u2">\n'
        "      <segment>\n"
        "        <source>Goodbye world</source>\n"
        "      </segment>\n"
        "    </unit>\n"
        "  </file>\n"
        "</xliff>\n"
    )
    inp, out = _write(tmp_path, "messages.xlf", xliff20)
    result = translate_file(inp, out, "French", "English (US)")
    assert result is True
    text = out.read_text(encoding="utf-8")
    # Source text preserved
    assert "Hello world" in text
    assert "Goodbye world" in text
    # Translation injected
    assert "[French]" in text


def test_yaml_nested_structure(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """Nested YAML: keys and nesting preserved, leaf values translated."""
    yaml_content = (
        "app:\n"
        "  ui:\n"
        "    title: My Application\n"
        "    buttons:\n"
        "      save: Save Changes\n"
        "      cancel: Cancel\n"
        "  messages:\n"
        "    - Welcome back\n"
        "    - See you later\n"
    )
    inp, out = _write(tmp_path, "nested.yaml", yaml_content)
    result = translate_file(inp, out, "French", "English (US)")
    assert result is True
    text = out.read_text(encoding="utf-8")
    # Nested keys preserved
    assert "app:" in text
    assert "buttons:" in text or "save:" in text
    # Leaf values translated
    assert "[French]" in text
    # Non-string structure intact (parse back as YAML)
    import yaml  # noqa: PLC0415

    data = yaml.safe_load(text)
    assert isinstance(data["app"]["ui"]["buttons"], dict)
    assert isinstance(data["app"]["messages"], list)
    assert len(data["app"]["messages"]) == 2  # noqa: PLR2004


def test_yaml_with_list_values(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """YAML with list values: list structure preserved, items translated."""
    yaml_content = "colors:\n  - Red\n  - Blue\n  - Green\n"
    inp, out = _write(tmp_path, "list.yml", yaml_content)
    result = translate_file(inp, out, "French", "English (US)")
    assert result is True
    import yaml  # noqa: PLC0415

    data = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert isinstance(data["colors"], list)
    assert len(data["colors"]) == 3  # noqa: PLR2004
    assert all("[French]" in item for item in data["colors"])


def test_xliff_12_via_xlf_extension(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """XLIFF 1.2 via .xlf extension works identically to .xliff."""
    xliff_content = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<xliff version="1.2"'
        ' xmlns="urn:oasis:names:tc:xliff:document:1.2">\n'
        '  <file source-language="en" target-language="fr">\n'
        "    <body>\n"
        '      <trans-unit id="1">\n'
        "        <source>Submit</source>\n"
        "        <target></target>\n"
        "      </trans-unit>\n"
        "    </body>\n"
        "  </file>\n"
        "</xliff>\n"
    )
    inp, out = _write(tmp_path, "ui.xlf", xliff_content)
    result = translate_file(inp, out, "French", "English (US)")
    assert result is True
    text = out.read_text(encoding="utf-8")
    assert "Submit" in text
    assert "[French]" in text


def test_htm_alias_works(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """.htm extension is handled identically to .html."""
    html = "<html><body><p>Greetings</p></body></html>"
    inp, out = _write(tmp_path, "page.htm", html)
    result = translate_file(inp, out, "French", "English (US)")
    assert result is True
    text = out.read_text(encoding="utf-8")
    assert "[French]" in text


def test_glossary_forwarded_to_llm(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """glossary_entries parameter is forwarded to translate_text."""
    captured_kwargs: dict[str, object] = {}

    def tracking_translate(
        texts: list[str],
        target_lang: str,
        source_lang: str = "",
        **kwargs: object,
    ) -> list[str]:
        captured_kwargs.update(kwargs)
        return [f"[{target_lang}] {t}" for t in texts]

    monkeypatch.setattr(
        "src.core.llm_engine.translate_text",
        tracking_translate,
    )
    monkeypatch.setattr(
        "src.core.text_processor._llm_engine.translate_text",
        tracking_translate,
    )

    glossary = [(1, "Hello", "Bonjour")]
    inp, out = _write(tmp_path, "gloss.txt", "Hello world")
    translate_file(
        inp,
        out,
        "French",
        "English (US)",
        glossary_entries=glossary,
    )
    assert captured_kwargs.get("glossary_entries") == glossary


def test_progress_callback_called(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """progress_callback receives incremental values ending at 100."""
    inp, out = _write(tmp_path, "prog.txt", "Hello world\n\nGoodbye world")
    progress: list[int] = []
    result = translate_file(
        inp,
        out,
        "French",
        "English (US)",
        progress_callback=progress.append,
    )
    assert result is True
    assert len(progress) >= 1
    assert progress[-1] == 100  # noqa: PLR2004


# ── Phase 1: HTML attribute quality tests ─────────────────────────────


def test_html_non_translatable_attrs_preserved(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """Non-translatable attrs (class, id, style, data-*) survive translation."""
    html_content = (
        '<h1 class="title" id="main" style="color:red"'
        ' data-section="intro">Title</h1>'
        "\n<p>Body</p>"
    )
    inp, out = _write(tmp_path, "attrs.html", html_content)
    result = translate_file(inp, out, "French", "English (US)")
    assert result is True
    text = out.read_text(encoding="utf-8")
    assert 'class="title"' in text
    assert 'id="main"' in text
    assert 'style="color:red"' in text
    assert 'data-section="intro"' in text


def test_html_translatable_attrs_kept_for_llm(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tracking mock verifies LLM receives alt but NOT class."""
    llm_inputs: list[str] = []

    def tracking_translate(
        texts: list[str],
        target_lang: str,
        source_lang: str = "",
        **kwargs: object,
    ) -> list[str]:
        llm_inputs.extend(texts)
        return [f"[{target_lang}] {t}" for t in texts]

    monkeypatch.setattr("src.core.llm_engine.translate_text", tracking_translate)
    monkeypatch.setattr(
        "src.core.text_processor._llm_engine.translate_text", tracking_translate
    )

    html_content = '<img src="photo.jpg" alt="A cat" class="photo" />'
    inp, out = _write(tmp_path, "track.html", html_content)
    translate_file(inp, out, "French", "English (US)")

    combined = " ".join(llm_inputs)
    # Translatable attr should reach the LLM
    assert 'alt="A cat"' in combined
    # Non-translatable attr should be stripped before LLM
    assert 'class="photo"' not in combined


def test_html_multiple_attrs_same_element(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Element with mixed attrs: src/class preserved, alt/title reach LLM."""
    llm_inputs: list[str] = []

    def tracking_translate(
        texts: list[str],
        target_lang: str,
        source_lang: str = "",
        **kwargs: object,
    ) -> list[str]:
        llm_inputs.extend(texts)
        return [f"[{target_lang}] {t}" for t in texts]

    monkeypatch.setattr("src.core.llm_engine.translate_text", tracking_translate)
    monkeypatch.setattr(
        "src.core.text_processor._llm_engine.translate_text", tracking_translate
    )

    html_content = '<img src="x.png" alt="cat" class="photo" title="Cat photo" />'
    inp, out = _write(tmp_path, "multi_attr.html", html_content)
    translate_file(inp, out, "French", "English (US)")

    # Output file: non-translatable attrs restored
    text = out.read_text(encoding="utf-8")
    assert 'src="x.png"' in text
    assert 'class="photo"' in text

    # LLM input: translatable attrs present, non-translatable stripped
    combined = " ".join(llm_inputs)
    assert 'alt="cat"' in combined
    assert 'title="Cat photo"' in combined
    assert 'class="photo"' not in combined


def test_html_self_closing_tag_attrs(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """Self-closing <img/> with attrs: src restored, self-closing preserved."""
    html_content = '<p>Text</p>\n<img src="x.png" alt="photo" />'
    inp, out = _write(tmp_path, "selfclose.html", html_content)
    result = translate_file(inp, out, "French", "English (US)")
    assert result is True
    text = out.read_text(encoding="utf-8")
    assert 'src="x.png"' in text
    # Self-closing slash preserved
    assert "/>" in text


def test_html_empty_translatable_attr(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """Empty alt="" is not corrupted, src is restored."""
    html_content = '<img alt="" src="x.png" />\n<p>Body</p>'
    inp, out = _write(tmp_path, "empty_alt.html", html_content)
    result = translate_file(inp, out, "French", "English (US)")
    assert result is True
    text = out.read_text(encoding="utf-8")
    assert 'src="x.png"' in text
    assert 'alt=""' in text


def test_html_aria_attrs_translated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """aria-label reaches LLM, class is preserved in output."""
    llm_inputs: list[str] = []

    def tracking_translate(
        texts: list[str],
        target_lang: str,
        source_lang: str = "",
        **kwargs: object,
    ) -> list[str]:
        llm_inputs.extend(texts)
        return [f"[{target_lang}] {t}" for t in texts]

    monkeypatch.setattr("src.core.llm_engine.translate_text", tracking_translate)
    monkeypatch.setattr(
        "src.core.text_processor._llm_engine.translate_text", tracking_translate
    )

    html_content = '<button aria-label="Close dialog" class="btn">X</button>'
    inp, out = _write(tmp_path, "aria.html", html_content)
    translate_file(inp, out, "French", "English (US)")

    text = out.read_text(encoding="utf-8")
    assert 'class="btn"' in text

    combined = " ".join(llm_inputs)
    assert 'aria-label="Close dialog"' in combined
    assert 'class="btn"' not in combined


def test_html_mixed_content_with_nested_tags(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """Nested tags: both class and id are preserved, text is translated."""
    html_content = '<div class="outer"><p id="inner">Text</p></div>'
    inp, out = _write(tmp_path, "nested.html", html_content)
    result = translate_file(inp, out, "French", "English (US)")
    assert result is True
    text = out.read_text(encoding="utf-8")
    assert 'class="outer"' in text
    assert 'id="inner"' in text
    assert "[French]" in text


# ── Phase 2: XML attribute quality tests ──────────────────────────────


def test_xml_all_attrs_preserved_in_output(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """XML attrs (id, type) are ALL preserved — none translatable in XML."""
    xml = '<root><item id="1" type="widget">Hello</item></root>'
    inp, out = _write(tmp_path, "attrs.xml", xml)
    result = translate_file(inp, out, "French", "English (US)")
    assert result is True
    text = out.read_text(encoding="utf-8")
    assert 'id="1"' in text
    assert 'type="widget"' in text


def test_xml_namespace_attrs_preserved(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """Namespace attrs (xmlns, ns:attr) survive XML translation."""
    xml = (
        '<root xmlns:ns="http://example.com"><ns:item ns:id="1">Hello</ns:item></root>'
    )
    inp, out = _write(tmp_path, "ns.xml", xml)
    result = translate_file(inp, out, "French", "English (US)")
    assert result is True
    text = out.read_text(encoding="utf-8")
    assert "http://example.com" in text
    assert 'ns:id="1"' in text


def test_xml_processing_instructions_preserved(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """XML processing instructions (<?xml ...?>) survive translation."""
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n<root><item>Hello</item></root>'
    inp, out = _write(tmp_path, "pi.xml", xml)
    result = translate_file(inp, out, "French", "English (US)")
    assert result is True
    text = out.read_text(encoding="utf-8")
    assert "<?xml" in text
    assert 'version="1.0"' in text


# ── Phase 3: Markdown quality tests ──────────────────────────────────


def test_md_inline_link_url_preserved(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """Inline link URL preserved exactly, text translated."""
    md = "Visit [Click here](https://example.com/path?q=1) for info."
    inp, out = _write(tmp_path, "link.md", md)
    result = translate_file(inp, out, "French", "English (US)")
    assert result is True
    text = out.read_text(encoding="utf-8")
    assert "https://example.com/path?q=1" in text
    assert "[French]" in text


def test_md_image_with_url_preserved(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """Image URL preserved, alt text translated."""
    md = "![alt text](https://cdn.example.com/img.png)"
    inp, out = _write(tmp_path, "image.md", md)
    result = translate_file(inp, out, "French", "English (US)")
    assert result is True
    text = out.read_text(encoding="utf-8")
    assert "https://cdn.example.com/img.png" in text


def test_md_reference_link_preserved(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    """Reference-style link URL in definition preserved."""
    md = "See [link][ref] for details.\n\n[ref]: https://example.com/ref"
    inp, out = _write(tmp_path, "reflink.md", md)
    result = translate_file(inp, out, "French", "English (US)")
    assert result is True
    text = out.read_text(encoding="utf-8")
    assert "https://example.com/ref" in text


# ── Phase 4: RTF quality tests ───────────────────────────────────────


def test_rtf_control_words_preserved(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    r"""RTF control words (\rtf1, \ansi, \par) survive round-trip."""
    rtf_content = r"{\rtf1\ansi Hello world\par Goodbye world\par}"
    inp, out = _write(tmp_path, "ctrl.rtf", rtf_content)
    result = translate_file(inp, out, "French", "English (US)")
    assert result is True
    text = out.read_text(encoding="utf-8")
    assert r"\rtf1" in text or "rtf1" in text
    assert r"\ansi" in text or "ansi" in text
    assert r"\par" in text


def test_rtf_unicode_escape_roundtrip(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
) -> None:
    r"""RTF Unicode escape \u233? (é) survives round-trip."""
    rtf_content = r"{\rtf1\ansi caf\u233?}\par"
    inp, out = _write(tmp_path, "unicode.rtf", rtf_content)
    result = translate_file(inp, out, "French", "English (US)")
    assert result is True
    text = out.read_text(encoding="utf-8")
    # The unicode escape or its decoded form should be present
    assert r"\u233" in text or "é" in text


# ── Phase 5: EPUB attribute quality tests ─────────────────────────────


def test_epub_xhtml_attrs_preserved(
    tmp_path: Path,
    mock_llm: Callable[..., list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """EPUB XHTML: class and id attrs preserved through ZIP round-trip."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda k, d=None: False,
    )
    monkeypatch.setattr("src.utils.config_manager.check_ocr_setup", lambda: False)

    epub_path = tmp_path / "attrs.epub"
    xhtml = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html><body><p class="chapter" id="c1">Hello world</p></body></html>'
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
        "  </manifest>\n"
        "  <spine>\n"
        '    <itemref idref="ch1"/>\n'
        "  </spine>\n"
        "</package>"
    )

    with zipfile.ZipFile(epub_path, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr("META-INF/container.xml", container)
        zf.writestr("OEBPS/content.opf", opf)
        zf.writestr("OEBPS/ch1.xhtml", xhtml)

    out = tmp_path / "translated_attrs.epub"
    result = translate_file(epub_path, out, "French", "English (US)")
    assert result is True

    with zipfile.ZipFile(out, "r") as zf:
        ch1 = zf.read("OEBPS/ch1.xhtml").decode("utf-8")
        assert 'class="chapter"' in ch1
        assert 'id="c1"' in ch1
        assert "[French]" in ch1


def test_epub_translatable_attrs_in_xhtml(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """EPUB: src preserved, alt reaches LLM through ZIP round-trip."""
    llm_inputs: list[str] = []

    def tracking_translate(
        texts: list[str],
        target_lang: str,
        source_lang: str = "",
        **kwargs: object,
    ) -> list[str]:
        llm_inputs.extend(texts)
        return [f"[{target_lang}] {t}" for t in texts]

    monkeypatch.setattr("src.core.llm_engine.translate_text", tracking_translate)
    monkeypatch.setattr(
        "src.core.text_processor._llm_engine.translate_text", tracking_translate
    )
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda k, d=None: False,
    )
    monkeypatch.setattr("src.utils.config_manager.check_ocr_setup", lambda: False)

    epub_path = tmp_path / "img_attrs.epub"
    xhtml = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html><body><img alt="Hero image" src="img.png"/>'
        "<p>Text</p></body></html>"
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
        "  </manifest>\n"
        "  <spine>\n"
        '    <itemref idref="ch1"/>\n'
        "  </spine>\n"
        "</package>"
    )

    with zipfile.ZipFile(epub_path, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr("META-INF/container.xml", container)
        zf.writestr("OEBPS/content.opf", opf)
        zf.writestr("OEBPS/ch1.xhtml", xhtml)

    out = tmp_path / "translated_img.epub"
    translate_file(epub_path, out, "French", "English (US)")

    # Output: src preserved
    with zipfile.ZipFile(out, "r") as zf:
        ch1 = zf.read("OEBPS/ch1.xhtml").decode("utf-8")
        assert 'src="img.png"' in ch1

    # LLM input: alt reached, src stripped
    combined = " ".join(llm_inputs)
    assert 'alt="Hero image"' in combined
    assert 'src="img.png"' not in combined


# ── Phase 6: Tag repair integration tests ─────────────────────────────


def test_html_tag_repair_when_llm_drops_closing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When LLM drops </b>, tag repair re-inserts it."""

    def tag_dropping_translate(
        texts: list[str],
        target_lang: str,
        source_lang: str = "",
        **kwargs: object,
    ) -> list[str]:
        results = []
        for t in texts:
            dropped = re.sub(r"</b>", "", t)
            results.append(f"[{target_lang}] {dropped}")
        return results

    monkeypatch.setattr(
        "src.core.llm_engine.translate_text",
        tag_dropping_translate,
    )
    monkeypatch.setattr(
        "src.core.text_processor._llm_engine.translate_text",
        tag_dropping_translate,
    )

    html_content = "<p>Normal <b>bold text</b> end</p>"
    inp, out = _write(tmp_path, "repair_b.html", html_content)
    result = translate_file(inp, out, "French", "English (US)")
    assert result is True
    text = out.read_text(encoding="utf-8")
    # Tag repair should re-insert the dropped </b>
    assert "</b>" in text
    assert "<b>" in text


def test_html_tag_repair_preserves_text(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When LLM strips <em> and </em>, text content still present, tags re-inserted."""

    def tag_dropping_translate(
        texts: list[str],
        target_lang: str,
        source_lang: str = "",
        **kwargs: object,
    ) -> list[str]:
        results = []
        for t in texts:
            dropped = re.sub(r"</?em>", "", t)
            results.append(f"[{target_lang}] {dropped}")
        return results

    monkeypatch.setattr(
        "src.core.llm_engine.translate_text",
        tag_dropping_translate,
    )
    monkeypatch.setattr(
        "src.core.text_processor._llm_engine.translate_text",
        tag_dropping_translate,
    )

    html_content = "<p>Some <em>emphasized</em> words</p>"
    inp, out = _write(tmp_path, "repair_em.html", html_content)
    result = translate_file(inp, out, "French", "English (US)")
    assert result is True
    text = out.read_text(encoding="utf-8")
    # Text content should survive
    assert "emphasized" in text or "words" in text
    # Tags should be re-inserted by repair
    assert "<em>" in text
    assert "</em>" in text


def test_xml_tag_repair_after_llm_drop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When LLM drops a closing </item>, it's restored in XML output."""

    def tag_dropping_translate(
        texts: list[str],
        target_lang: str,
        source_lang: str = "",
        **kwargs: object,
    ) -> list[str]:
        results = []
        for t in texts:
            # Drop only the first </item>
            dropped = t.replace("</item>", "", 1)
            results.append(f"[{target_lang}] {dropped}")
        return results

    monkeypatch.setattr(
        "src.core.llm_engine.translate_text",
        tag_dropping_translate,
    )
    monkeypatch.setattr(
        "src.core.text_processor._llm_engine.translate_text",
        tag_dropping_translate,
    )

    xml = "<root><item>Hello</item><item>World</item></root>"
    inp, out = _write(tmp_path, "repair.xml", xml)
    result = translate_file(inp, out, "French", "English (US)")
    assert result is True
    text = out.read_text(encoding="utf-8")
    # The repair step should have re-inserted the dropped </item>
    assert text.count("</item>") >= 2  # noqa: PLR2004


# ── Phase 8: Content type dispatch verification ──────────────────────


def test_html_content_type_forwarded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tracking mock verifies content_type='html' reaches LLM for .html."""
    captured_kwargs: dict[str, object] = {}

    def tracking_translate(
        texts: list[str],
        target_lang: str,
        source_lang: str = "",
        **kwargs: object,
    ) -> list[str]:
        captured_kwargs.update(kwargs)
        return [f"[{target_lang}] {t}" for t in texts]

    monkeypatch.setattr("src.core.llm_engine.translate_text", tracking_translate)
    monkeypatch.setattr(
        "src.core.text_processor._llm_engine.translate_text", tracking_translate
    )

    inp, out = _write(tmp_path, "type.html", "<p>Hello</p>")
    translate_file(inp, out, "French", "English (US)")
    assert captured_kwargs.get("content_type") == "html"


def test_xml_content_type_forwarded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tracking mock verifies content_type='xml' reaches LLM for .xml."""
    captured_kwargs: dict[str, object] = {}

    def tracking_translate(
        texts: list[str],
        target_lang: str,
        source_lang: str = "",
        **kwargs: object,
    ) -> list[str]:
        captured_kwargs.update(kwargs)
        return [f"[{target_lang}] {t}" for t in texts]

    monkeypatch.setattr("src.core.llm_engine.translate_text", tracking_translate)
    monkeypatch.setattr(
        "src.core.text_processor._llm_engine.translate_text", tracking_translate
    )

    inp, out = _write(tmp_path, "type.xml", "<root><item>Hello</item></root>")
    translate_file(inp, out, "French", "English (US)")
    assert captured_kwargs.get("content_type") == "xml"
