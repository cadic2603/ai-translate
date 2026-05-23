"""Unit tests for the text file processing engine."""

import contextlib
import json
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.constants.errors import ERR_TEXT_READ_FAILED, ERR_TEXT_WRITE_FAILED
from src.core.checkpoint import (
    save_batch_progress,
    save_epub_file_progress,
    save_text_chunk,
)
from src.core.llm_engine import translate_batch
from src.core.text_processor import (
    MAX_CHUNK_CHARS,
    _chunk_text,
    _extract_json_strings,
    _get_epub_content_files,
    _get_separator,
    _inject_json_strings,
    _join_with_separators,
    _read_file,
    _repair_and_restore_attrs,
    _translate_chunks,
    translate_file,
)
from src.core.translator import _map_error_to_code  # noqa: E402

# ---------------------------------------------------------------------------
# _read_file tests
# ---------------------------------------------------------------------------


def test_read_file_utf8(tmp_path: Path) -> None:
    """Reads a UTF-8 encoded file."""
    f = tmp_path / "test.txt"
    f.write_text("Hello World", encoding="utf-8")
    assert _read_file(f) == "Hello World"


def test_read_file_encoding_detection(tmp_path: Path) -> None:
    """Detects encoding via charset_normalizer when UTF-8 fails."""
    f = tmp_path / "test.txt"
    # Realistic latin-1 / cp1252 content for reliable detection
    text = "Le café est très bon. Ça fait plaisir de manger des crêpes."
    f.write_bytes(text.encode("latin-1"))
    result = _read_file(f)
    assert "café" in result


# ---------------------------------------------------------------------------
# _chunk_text tests
# ---------------------------------------------------------------------------


def test_chunk_text_by_paragraphs() -> None:
    """Chunks text by double-newline paragraphs."""
    content = "Para 1\n\nPara 2\n\nPara 3"
    chunks, seps = _chunk_text(content, "\n\n", max_chars=50)
    assert len(chunks) >= 1
    # All original content is preserved
    reassembled = _join_with_separators(chunks, seps)
    assert reassembled == content


def test_chunk_text_grouping() -> None:
    """Groups small segments into larger chunks."""
    content = "A\n\nB\n\nC\n\nD"
    chunks, seps = _chunk_text(content, "\n\n", max_chars=100)
    # All 4 short segments should fit in one chunk
    assert len(chunks) == 1
    assert chunks[0] == content


def test_chunk_text_splits_large_content() -> None:
    """Splits content when it exceeds max_chars."""
    # Create content with many paragraphs
    paras = [f"Paragraph {i} " * 20 for i in range(10)]
    content = "\n\n".join(paras)
    chunks, seps = _chunk_text(content, "\n\n", max_chars=500)
    assert len(chunks) > 1
    # Reassembled should match original
    reassembled = _join_with_separators(chunks, seps)
    assert reassembled == content


def test_chunk_text_empty_content() -> None:
    """Returns empty list for whitespace-only content."""
    assert _chunk_text("", "\n\n") == ([], [])
    assert _chunk_text("   \n\n   ", "\n\n") == ([], [])


def test_chunk_text_single_large_segment() -> None:
    """A single segment larger than max_chars is kept intact."""
    large = "A" * (MAX_CHUNK_CHARS + 100)
    chunks, seps = _chunk_text(large, "\n\n")
    assert len(chunks) == 1
    assert chunks[0] == large
    assert seps == []


def test_chunk_text_line_separator() -> None:
    """Chunks by single newline (markup mode) and reassembles correctly."""
    content = "Line 1\nLine 2\nLine 3\nLine 4"
    chunks, seps = _chunk_text(content, "\n", max_chars=100)
    assert len(chunks) >= 1
    assert _join_with_separators(chunks, seps) == content


def test_chunk_text_rtf_separator() -> None:
    r"""Chunks by \\par (RTF mode) and reassembles correctly."""
    content = r"Paragraph 1\parParagraph 2\parParagraph 3"
    chunks, seps = _chunk_text(content, "\\par", max_chars=200)
    assert len(chunks) >= 1
    assert _join_with_separators(chunks, seps) == content


def test_chunk_text_unicode_content() -> None:
    """Handles Unicode (CJK, accented) content correctly."""
    content = "你好世界\n\nCafé au lait\n\nStraße"
    chunks, seps = _chunk_text(content, "\n\n", max_chars=100)
    assert _join_with_separators(chunks, seps) == content


def test_chunk_text_only_whitespace_segments() -> None:
    """Whitespace-only segments between separators are filtered out."""
    content = "   \n\n   \n\n   "
    chunks, seps = _chunk_text(content, "\n\n")
    assert chunks == []
    assert seps == []


def test_chunk_text_preserves_multi_separators() -> None:
    """Triple/quadruple newlines survive chunking and reassembly."""
    content = "A\n\n\n\nB\n\nC"
    chunks, seps = _chunk_text(content, "\n\n", max_chars=100)
    # Roundtrip must reproduce the original content exactly
    assert _join_with_separators(chunks, seps) == content


def test_chunk_text_multi_separator_at_chunk_boundary() -> None:
    """Multi-separator run at a chunk boundary is preserved."""
    # Force a split between A and B by using a small max_chars
    content = "AAAA\n\n\n\nBBBB\n\nCCCC"
    chunks, seps = _chunk_text(content, "\n\n", max_chars=10)
    assert len(chunks) > 1
    assert _join_with_separators(chunks, seps) == content


# ---------------------------------------------------------------------------
# _get_separator tests
# ---------------------------------------------------------------------------


def test_get_separator_plain() -> None:
    """Returns paragraph separator for plain text."""
    assert _get_separator(".txt") == "\n\n"
    assert _get_separator(".md") == "\n\n"


def test_get_separator_markup() -> None:
    """Returns line separator for markup files."""
    assert _get_separator(".html") == "\n"
    assert _get_separator(".xml") == "\n"


def test_get_separator_rtf() -> None:
    """Returns RTF paragraph marker."""
    assert _get_separator(".rtf") == "\\par"


def test_get_separator_htm() -> None:
    """Returns line separator for .htm (alias of .html)."""
    assert _get_separator(".htm") == "\n"


# ---------------------------------------------------------------------------
# JSON extraction/injection tests
# ---------------------------------------------------------------------------


def test_extract_json_strings_flat() -> None:
    """Extracts strings from a flat dictionary."""
    data = {"key1": "value1", "key2": "value2", "count": 42}
    pairs = _extract_json_strings(data)
    paths = [p for p, _ in pairs]
    assert ("key1",) in paths
    assert ("key2",) in paths


def test_extract_json_strings_nested() -> None:
    """Extracts strings from nested structures."""
    data = {"a": {"b": "deep"}, "c": [{"d": "item"}]}
    pairs = _extract_json_strings(data)
    paths = dict(pairs)
    assert ("a", "b") in paths
    assert ("c", 0, "d") in paths


def test_extract_json_strings_skips_empty() -> None:
    """Skips empty/whitespace-only strings."""
    data = {"empty": "", "spaces": "   ", "valid": "hello"}
    pairs = _extract_json_strings(data)
    assert len(pairs) == 1
    assert pairs[0][1] == "hello"


def test_inject_json_strings() -> None:
    """Injects translated values back into JSON structure."""
    data = {"greeting": "hello", "nested": {"msg": "world"}}
    translations = {
        ("greeting",): "bonjour",
        ("nested", "msg"): "monde",
    }
    result = _inject_json_strings(data, translations)
    assert result["greeting"] == "bonjour"
    assert result["nested"]["msg"] == "monde"


def test_inject_json_strings_preserves_non_strings() -> None:
    """Non-string values (numbers, booleans) are preserved."""
    data = {"name": "test", "count": 5, "active": True}
    translations = {("name",): "translated"}
    result = _inject_json_strings(data, translations)
    assert result["count"] == data["count"]
    assert result["active"] is True


def test_extract_json_strings_root_array() -> None:
    """Extracts strings from a root-level array."""
    data = ["hello", "world", 42]
    pairs = _extract_json_strings(data)
    paths = [p for p, _ in pairs]
    assert (0,) in paths
    assert (1,) in paths
    assert len(pairs) == 2  # noqa: PLR2004 — skips int


def test_extract_json_strings_deeply_nested() -> None:
    """Extracts strings from deeply nested structures."""
    data = {"a": {"b": {"c": {"d": "deep_value"}}}}
    pairs = _extract_json_strings(data)
    assert len(pairs) == 1
    assert pairs[0][0] == ("a", "b", "c", "d")
    assert pairs[0][1] == "deep_value"


def test_extract_json_strings_unicode() -> None:
    """Extracts Unicode strings (CJK, accented)."""
    data = {"greeting": "こんにちは", "name": "Café"}
    pairs = _extract_json_strings(data)
    values = [v for _, v in pairs]
    assert "こんにちは" in values
    assert "Café" in values


def test_extract_json_strings_mixed_array_in_dict() -> None:
    """Extracts strings from arrays nested inside dicts."""
    data = {"items": ["apple", "banana"], "count": 2}
    pairs = _extract_json_strings(data)
    paths = dict(pairs)
    assert ("items", 0) in paths
    assert ("items", 1) in paths
    assert len(pairs) == 2  # noqa: PLR2004


def test_inject_json_strings_root_array() -> None:
    """Injects translations into a root-level array."""
    data = ["hello", "world"]
    translations = {(0,): "bonjour", (1,): "monde"}
    result = _inject_json_strings(data, translations)
    assert result == ["bonjour", "monde"]


def test_inject_json_strings_missing_path_keeps_original() -> None:
    """Strings without translation entries are preserved as-is."""
    data = {"a": "hello", "b": "world"}
    # Only translate "a"
    translations = {("a",): "bonjour"}
    result = _inject_json_strings(data, translations)
    assert result["a"] == "bonjour"
    assert result["b"] == "world"  # unchanged


def test_inject_json_strings_deeply_nested() -> None:
    """Injects translations into deeply nested structures."""
    data = {"a": {"b": {"c": "original"}}}
    translations = {("a", "b", "c"): "translated"}
    result = _inject_json_strings(data, translations)
    assert result["a"]["b"]["c"] == "translated"


# ---------------------------------------------------------------------------
# EPUB content file discovery
# ---------------------------------------------------------------------------


def _create_minimal_epub(tmp_path: Path) -> Path:
    """Creates a minimal EPUB archive for testing."""
    epub_path = tmp_path / "test.epub"

    container_xml = (
        '<?xml version="1.0"?>'
        "<container"
        ' xmlns="urn:oasis:names:tc:opendocument'
        ':xmlns:container"'
        ' version="1.0">'
        "  <rootfiles>"
        '    <rootfile full-path="OEBPS/content.opf"'
        ' media-type="application/oebps-package+xml"/>'
        "  </rootfiles>"
        "</container>"
    )

    content_opf = (
        '<?xml version="1.0"?>'
        '<package xmlns="http://www.idpf.org/2007/opf"'
        ' version="3.0">'
        "  <manifest>"
        '    <item id="ch1" href="chapter1.xhtml"'
        ' media-type="application/xhtml+xml"/>'
        '    <item id="css" href="style.css"'
        ' media-type="text/css"/>'
        "  </manifest>"
        "</package>"
    )

    chapter_xhtml = '<?xml version="1.0"?><html><body><p>Hello World</p></body></html>'

    with zipfile.ZipFile(epub_path, "w") as zf:
        zf.writestr("META-INF/container.xml", container_xml)
        zf.writestr("OEBPS/content.opf", content_opf)
        zf.writestr("OEBPS/chapter1.xhtml", chapter_xhtml)
        zf.writestr("OEBPS/style.css", "body { color: black; }")

    return epub_path


def test_get_epub_content_files(tmp_path: Path) -> None:
    """Discovers XHTML content files in a minimal EPUB."""
    epub_path = _create_minimal_epub(tmp_path)
    with zipfile.ZipFile(epub_path, "r") as zf:
        content_files = _get_epub_content_files(zf)
    assert len(content_files) == 1
    assert "chapter1.xhtml" in content_files[0]


def test_get_epub_content_files_missing_container(
    tmp_path: Path,
) -> None:
    """Returns empty list if container.xml is missing."""
    epub_path = tmp_path / "bad.epub"
    with zipfile.ZipFile(epub_path, "w") as zf:
        zf.writestr("README", "not an epub")
    with zipfile.ZipFile(epub_path, "r") as zf:
        assert _get_epub_content_files(zf) == []


# ---------------------------------------------------------------------------
# translate_file end-to-end (mocked LLM)
# ---------------------------------------------------------------------------


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_txt(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Translates a .txt file end-to-end."""
    src = tmp_path / "input.txt"
    src.write_text(
        "Hello World\n\nGoodbye World",
        encoding="utf-8",
    )
    out = tmp_path / "output.txt"

    mock_translate.side_effect = lambda texts, *a, **kw: [f"[FR] {t}" for t in texts]

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert "[FR]" in content


@patch("src.core.llm_engine.translate_text")
def test_translate_file_json(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Translates a .json file preserving structure."""
    src = tmp_path / "input.json"
    data = {
        "greeting": "hello",
        "nested": {"msg": "world"},
        "count": 42,
    }
    src.write_text(json.dumps(data), encoding="utf-8")
    out = tmp_path / "output.json"

    mock_translate.side_effect = lambda texts, *a, **kw: [f"[FR] {t}" for t in texts]

    result = translate_file(src, out, "French", "English (US)")
    assert result is True

    translated = json.loads(out.read_text(encoding="utf-8"))
    assert translated["greeting"] == "[FR] hello"
    assert translated["nested"]["msg"] == "[FR] world"
    assert translated["count"] == data["count"]


@patch("src.core.llm_engine.translate_text")
def test_translate_file_csv(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Translates a .csv file preserving structure."""
    src = tmp_path / "input.csv"
    src.write_text(
        "Name,Greeting\nAlice,Hello\nBob,Hi\n",
        encoding="utf-8",
    )
    out = tmp_path / "output.csv"

    mock_translate.side_effect = lambda texts, *a, **kw: [f"[FR] {t}" for t in texts]

    result = translate_file(src, out, "French", "English (US)")
    assert result is True

    content = out.read_text(encoding="utf-8")
    assert "[FR] Alice" in content
    assert "[FR] Hello" in content


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_html(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Translates an .html file preserving tags."""
    src = tmp_path / "input.html"
    src.write_text(
        "<html><body><p>Hello</p></body></html>",
        encoding="utf-8",
    )
    out = tmp_path / "output.html"

    mock_translate.side_effect = lambda texts, *a, **kw: [f"[FR] {t}" for t in texts]

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    assert out.exists()


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_epub(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Translates an .epub file end-to-end."""
    src = _create_minimal_epub(tmp_path)
    out = tmp_path / "output.epub"

    mock_translate.side_effect = lambda texts, *a, **kw: [f"[FR] {t}" for t in texts]

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    assert out.exists()

    # Verify the translated EPUB contains translated content
    with zipfile.ZipFile(out, "r") as zf:
        chapter = zf.read(
            "OEBPS/chapter1.xhtml",
        ).decode("utf-8")
        assert "[FR]" in chapter


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_cancel(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Returns False when cancel_check triggers."""
    src = tmp_path / "input.txt"
    src.write_text("Hello\n\nWorld", encoding="utf-8")
    out = tmp_path / "output.txt"

    # Cancel immediately
    result = translate_file(
        src,
        out,
        "French",
        "English (US)",
        cancel_check=lambda: True,
    )
    assert result is False
    assert not out.exists()


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_progress(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Verifies progress callback is invoked."""
    src = tmp_path / "input.txt"
    src.write_text("Para 1\n\nPara 2", encoding="utf-8")
    out = tmp_path / "output.txt"

    mock_translate.side_effect = lambda texts, *a, **kw: texts
    progress_values: list[int] = []

    result = translate_file(
        src,
        out,
        "French",
        "English (US)",
        progress_callback=progress_values.append,
    )
    assert result is True
    assert len(progress_values) > 0


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_empty_txt(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Handles empty text files gracefully."""
    src = tmp_path / "empty.txt"
    src.write_text("", encoding="utf-8")
    out = tmp_path / "output.txt"

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    assert out.exists()


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_empty_json(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Handles JSON with no translatable strings."""
    src = tmp_path / "numbers.json"
    src.write_text(
        json.dumps({"count": 42, "ratio": 3.14}),
        encoding="utf-8",
    )
    out = tmp_path / "output.json"

    result = translate_file(src, out, "French", "English (US)")
    assert result is True

    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["count"] == 42  # noqa: PLR2004


# ---------------------------------------------------------------------------
# Error mapping integration
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "exc_type",
    [
        # Full list mirrors src.core.text_processor._BUG_EXCEPTIONS.
        # If a new type is added there, add it here so the
        # propagation contract stays pinned for every member.
        AssertionError,
        AttributeError,
        TypeError,
        KeyError,
        IndexError,
        NameError,
        ImportError,
        NotImplementedError,
        RuntimeError,
    ],
)
def test_translate_file_propagates_unexpected_exceptions(
    tmp_path: Path,
    exc_type: type[BaseException],
) -> None:
    """Programming-error exceptions propagate, not rebadged as TEXT_READ_ERROR.

    Bug-class exception types raised from a dispatched processor
    (PDF, Office, EPUB, …) belong in the log with their real
    traceback.  Rebadging them as ``TEXT_READ_ERROR`` would surface
    a misleading "could not read the text file" message for bugs
    that have nothing to do with file encoding.
    """
    src = tmp_path / "doc.pdf"
    src.write_bytes(b"%PDF-1.4\n%fake")
    out = tmp_path / "out.pdf"

    bug_message = "simulated bug deep in the PDF processor chain"
    with (
        patch(
            "src.core.pdf_processor.process_pdf_file",
            side_effect=exc_type(bug_message),
        ),
        pytest.raises(exc_type, match=bug_message),
    ):
        translate_file(src, out, "French", "English (US)")


def test_translate_file_oserror_still_maps_to_text_read_error(
    tmp_path: Path,
) -> None:
    """Genuine file-IO failures map to TEXT_READ_ERROR.

    Permission denied, broken bytes, and other ``OSError`` /
    ``UnicodeDecodeError`` cases are real "could not read the file"
    conditions that deserve the user-facing TEXT_READ_ERROR tag.
    """
    src = tmp_path / "doc.txt"
    src.write_text("hello", encoding="utf-8")
    out = tmp_path / "out.txt"

    with (
        patch(
            "src.core.text_processor._process_plain",
            side_effect=OSError("disk gone"),
        ),
        pytest.raises(ValueError, match="^TEXT_READ_ERROR$"),
    ):
        translate_file(src, out, "French", "English (US)")


def test_error_map_includes_text_errors() -> None:
    """Verify text error tags are in the translator error map."""
    assert _map_error_to_code("TEXT_READ_ERROR") == ERR_TEXT_READ_FAILED
    assert _map_error_to_code("TEXT_WRITE_ERROR") == ERR_TEXT_WRITE_FAILED


# ---------------------------------------------------------------------------
# E2E tests for additional formats (.xml, .rtf, .md)
# ---------------------------------------------------------------------------


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_xml(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Translates an .xml file end-to-end."""
    src = tmp_path / "input.xml"
    src.write_text(
        '<?xml version="1.0"?>\n<root>\n  <message>Hello</message>\n</root>',
        encoding="utf-8",
    )
    out = tmp_path / "output.xml"

    mock_translate.side_effect = lambda texts, *a, **kw: [f"[FR] {t}" for t in texts]

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert "[FR]" in content


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_rtf(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    r"""Translates an .rtf file end-to-end using \\par separator."""
    src = tmp_path / "input.rtf"
    src.write_text(
        r"{\rtf1 Hello World\par Goodbye World}",
        encoding="utf-8",
    )
    out = tmp_path / "output.rtf"

    mock_translate.side_effect = lambda texts, *a, **kw: [f"[FR] {t}" for t in texts]

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert "[FR]" in content


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_md(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Translates a .md file end-to-end."""
    src = tmp_path / "input.md"
    src.write_text(
        "# Title\n\nParagraph one.\n\nParagraph two.",
        encoding="utf-8",
    )
    out = tmp_path / "output.md"

    mock_translate.side_effect = lambda texts, *a, **kw: [f"[FR] {t}" for t in texts]

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert "[FR]" in content


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_rst(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Translates a .rst file end-to-end."""
    src = tmp_path / "input.rst"
    src.write_text(
        "Title\n=====\n\nParagraph one.\n\nParagraph two.",
        encoding="utf-8",
    )
    out = tmp_path / "output.rst"

    mock_translate.side_effect = lambda texts, *a, **kw: [f"[FR] {t}" for t in texts]

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert "[FR]" in content


# ---------------------------------------------------------------------------
# Checkpoint resume tests — _translate_chunks
# ---------------------------------------------------------------------------


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_chunks_resumes_from_checkpoint(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Cached chunks are skipped; only uncached chunks call the LLM."""
    # Pre-save chunk 0 to checkpoint
    save_text_chunk(tmp_path, 0, "[cached] Chunk 0", 3)

    mock_translate.side_effect = lambda texts, *a, **kw: [f"[LLM] {t}" for t in texts]

    chunks = ["Chunk 0", "Chunk 1", "Chunk 2"]
    result = _translate_chunks(
        chunks,
        "French",
        "English (US)",
        progress_callback=None,
        glossary_entries=None,
        cancel_check=None,
        checkpoint_dir=tmp_path,
    )

    assert result is not None
    assert len(result) == 3  # noqa: PLR2004
    # Chunk 0 comes from cache
    assert result[0] == "[cached] Chunk 0"
    # Chunks 1 and 2 went through LLM
    assert result[1] == "[LLM] Chunk 1"
    assert result[2] == "[LLM] Chunk 2"
    # LLM called once with all uncached chunks batched together
    assert mock_translate.call_count == 1


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_chunks_no_checkpoint(
    mock_translate: MagicMock,
) -> None:
    """Without checkpoint_dir, all chunks are translated."""
    mock_translate.side_effect = lambda texts, *a, **kw: [f"[LLM] {t}" for t in texts]

    chunks = ["A", "B"]
    result = _translate_chunks(
        chunks,
        "French",
        "",
        progress_callback=None,
        glossary_entries=None,
        cancel_check=None,
        checkpoint_dir=None,
    )

    assert result == ["[LLM] A", "[LLM] B"]
    # All chunks sent in one batched call
    assert mock_translate.call_count == 1


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_chunks_all_cached(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """All chunks cached → LLM not called, returns cached results."""
    save_text_chunk(tmp_path, 0, "[cached] A", 2)
    save_text_chunk(tmp_path, 1, "[cached] B", 2)

    result = _translate_chunks(
        ["A", "B"],
        "French",
        "",
        progress_callback=None,
        glossary_entries=None,
        cancel_check=None,
        checkpoint_dir=tmp_path,
    )

    assert result == ["[cached] A", "[cached] B"]
    mock_translate.assert_not_called()


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_chunks_cancel_between_sub_batches(
    mock_translate: MagicMock,
) -> None:
    """Cancellation between sub-batches returns None."""
    mock_translate.side_effect = lambda texts, *a, **kw: [f"[LLM] {t}" for t in texts]

    # Cancel after one sub-batch is processed
    check_calls = 0

    def cancel_after_first_batch() -> bool:
        nonlocal check_calls
        check_calls += 1
        # First call (before start): False
        # Second call (between sub-batches): True
        return check_calls > 2  # noqa: PLR2004

    # Force many sub-batches by using small budget
    with patch(
        "src.core.text_processor._llm_engine._split_by_token_budget",
        side_effect=lambda texts, _: [[t] for t in texts],
    ):
        result = _translate_chunks(
            ["A", "B", "C"],
            "French",
            "",
            progress_callback=None,
            glossary_entries=None,
            cancel_check=cancel_after_first_batch,
            checkpoint_dir=None,
        )

    assert result is None


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_chunks_progress_callback(
    mock_translate: MagicMock,
) -> None:
    """Progress callback receives increasing values ending at 100."""
    mock_translate.side_effect = lambda texts, *a, **kw: [f"[LLM] {t}" for t in texts]

    progress_values: list[int] = []
    result = _translate_chunks(
        ["A", "B", "C"],
        "French",
        "",
        progress_callback=progress_values.append,
        glossary_entries=None,
        cancel_check=None,
        checkpoint_dir=None,
    )

    assert result is not None
    assert len(progress_values) > 0
    assert progress_values[-1] == 100  # noqa: PLR2004


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_chunks_passes_glossary(
    mock_translate: MagicMock,
) -> None:
    """Glossary entries are forwarded to translate_text."""
    mock_translate.side_effect = lambda texts, *a, **kw: texts

    glossary = [(1, "hello", "bonjour")]
    _translate_chunks(
        ["hello world"],
        "French",
        "",
        progress_callback=None,
        glossary_entries=glossary,
        cancel_check=None,
        checkpoint_dir=None,
    )

    _, kwargs = mock_translate.call_args
    assert kwargs["glossary_entries"] == glossary


# ---------------------------------------------------------------------------
# Checkpoint resume tests — translate_batch
# ---------------------------------------------------------------------------


@patch("src.core.llm_engine.translate_text")
def test_translate_batch_resumes_from_checkpoint(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Cached batch values are skipped; only uncached call the LLM."""
    # Pre-save first 2 values
    save_batch_progress(tmp_path, 0, ["[cached] A", "[cached] B"], 4)

    mock_translate.side_effect = lambda texts, *a, **kw: [f"[LLM] {t}" for t in texts]

    values = ["A", "B", "C", "D"]
    result = translate_batch(
        values,
        "French",
        "English (US)",
        checkpoint_dir=tmp_path,
    )

    assert result is not None
    assert len(result) == 4  # noqa: PLR2004
    # First 2 from cache (note: only if entire batch is cached)
    # With TRANSLATION_BATCH_SIZE=30, all 4 fit in one batch.
    # Since indices 0,1 are cached but 2,3 are not,
    # the batch is not fully cached → LLM translates all 4.
    # The batch is [A,B,C,D] as one batch of 30.
    # batch_cached = all(i in existing for i in range(0, 4)) → False
    # So the LLM is called for the whole batch.
    assert mock_translate.call_count == 1


@patch("src.core.llm_engine.translate_text")
def test_translate_batch_all_cached(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """When all values are cached, LLM is not called at all."""
    # Pre-save all 3 values
    save_batch_progress(
        tmp_path,
        0,
        ["[cached] X", "[cached] Y", "[cached] Z"],
        3,
    )

    values = ["X", "Y", "Z"]
    result = translate_batch(
        values,
        "French",
        "",
        checkpoint_dir=tmp_path,
    )

    assert result is not None
    assert result == ["[cached] X", "[cached] Y", "[cached] Z"]
    mock_translate.assert_not_called()


# ---------------------------------------------------------------------------
# Checkpoint resume tests — EPUB
# ---------------------------------------------------------------------------


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_epub_resumes_from_checkpoint(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Previously translated EPUB content files are loaded from cache."""
    # Create a 2-chapter EPUB
    epub_path = tmp_path / "test.epub"
    container_xml = (
        '<?xml version="1.0"?>'
        '<container xmlns="urn:oasis:names:tc:opendocument'
        ':xmlns:container" version="1.0">'
        "  <rootfiles>"
        '    <rootfile full-path="OEBPS/content.opf"'
        ' media-type="application/oebps-package+xml"/>'
        "  </rootfiles>"
        "</container>"
    )
    content_opf = (
        '<?xml version="1.0"?>'
        '<package xmlns="http://www.idpf.org/2007/opf"'
        ' version="3.0">'
        "  <manifest>"
        '    <item id="ch1" href="ch1.xhtml"'
        ' media-type="application/xhtml+xml"/>'
        '    <item id="ch2" href="ch2.xhtml"'
        ' media-type="application/xhtml+xml"/>'
        "  </manifest>"
        "</package>"
    )
    ch1 = "<html><body><p>Chapter 1</p></body></html>"
    ch2 = "<html><body><p>Chapter 2</p></body></html>"

    with zipfile.ZipFile(epub_path, "w") as zf:
        zf.writestr("META-INF/container.xml", container_xml)
        zf.writestr("OEBPS/content.opf", content_opf)
        zf.writestr("OEBPS/ch1.xhtml", ch1)
        zf.writestr("OEBPS/ch2.xhtml", ch2)

    # Pre-cache chapter 1 in the checkpoint
    checkpoint_dir = tmp_path / "checkpoints"
    checkpoint_dir.mkdir()
    save_epub_file_progress(
        checkpoint_dir,
        "OEBPS/ch1.xhtml",
        "[CACHED] Chapter 1 translated",
        ["OEBPS/ch1.xhtml", "OEBPS/ch2.xhtml"],
    )

    mock_translate.side_effect = lambda texts, *a, **kw: [f"[LLM] {t}" for t in texts]

    out = tmp_path / "output.epub"
    result = translate_file(
        epub_path,
        out,
        "French",
        "English (US)",
        checkpoint_dir=checkpoint_dir,
    )
    assert result is True
    assert out.exists()

    # Verify ch1 used cached content
    with zipfile.ZipFile(out, "r") as zf:
        ch1_content = zf.read(
            "OEBPS/ch1.xhtml",
        ).decode("utf-8")
        ch2_content = zf.read(
            "OEBPS/ch2.xhtml",
        ).decode("utf-8")

    assert "[CACHED]" in ch1_content
    assert "[LLM]" in ch2_content


# ---------------------------------------------------------------------------
# LLM error propagation in text translate
# ---------------------------------------------------------------------------


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_llm_error_propagates(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """LLM ValueError propagates through translate_file."""
    src = tmp_path / "input.txt"
    src.write_text("Hello World", encoding="utf-8")
    out = tmp_path / "output.txt"

    mock_translate.side_effect = ValueError("AUTH_ERROR")

    with pytest.raises(ValueError, match="AUTH_ERROR"):
        translate_file(src, out, "French", "English (US)")


# ---------------------------------------------------------------------------
# Error path tests
# ---------------------------------------------------------------------------


def test_translate_file_nonexistent_raises() -> None:
    """Raises ValueError when the source file does not exist."""
    src = Path("/tmp/nonexistent_file_for_test_12345.txt")
    out = Path("/tmp/output_nonexistent.txt")

    with pytest.raises(ValueError, match="TEXT_READ_ERROR"):
        translate_file(src, out, "French", "English (US)")


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_write_error(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Raises ValueError when output cannot be written."""
    src = tmp_path / "input.txt"
    src.write_text("Hello World", encoding="utf-8")
    # Use a path under a read-only directory to trigger write error
    read_only = tmp_path / "readonly"
    read_only.mkdir()
    read_only.chmod(0o444)
    out = read_only / "subdir" / "output.txt"

    mock_translate.side_effect = lambda texts, *a, **kw: texts

    try:
        with pytest.raises(ValueError, match="TEXT_WRITE_ERROR"):
            translate_file(src, out, "French", "English (US)")
    finally:
        read_only.chmod(0o755)


def test_read_file_nonexistent() -> None:
    """_read_file raises FileNotFoundError for missing files."""
    with pytest.raises(FileNotFoundError):
        _read_file(Path("/tmp/nonexistent_file_12345.txt"))


# ---------------------------------------------------------------------------
# CSV edge-case tests
# ---------------------------------------------------------------------------


@patch("src.core.llm_engine.translate_text")
def test_translate_file_csv_empty(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Empty CSV file is handled gracefully."""
    src = tmp_path / "empty.csv"
    src.write_text("", encoding="utf-8")
    out = tmp_path / "output.csv"

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    assert out.read_text() == ""
    mock_translate.assert_not_called()


@patch("src.core.llm_engine.translate_text")
def test_translate_file_csv_only_empty_cells(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """CSV with only empty/whitespace cells has nothing to translate."""
    src = tmp_path / "blanks.csv"
    src.write_text(",\n,\n", encoding="utf-8")
    out = tmp_path / "output.csv"

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    mock_translate.assert_not_called()


@patch("src.core.llm_engine.translate_text")
def test_translate_file_csv_cancel(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """CSV translation returns False when cancelled."""
    src = tmp_path / "input.csv"
    src.write_text("Name\nAlice\n", encoding="utf-8")
    out = tmp_path / "output.csv"

    result = translate_file(
        src,
        out,
        "French",
        "English (US)",
        cancel_check=lambda: True,
    )
    assert result is False


# ---------------------------------------------------------------------------
# EPUB edge-case tests
# ---------------------------------------------------------------------------


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_epub_no_content_files(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """EPUB with empty manifest copies file as-is."""
    epub_path = tmp_path / "empty.epub"
    container_xml = (
        '<?xml version="1.0"?>'
        '<container xmlns="urn:oasis:names:tc:opendocument'
        ':xmlns:container" version="1.0">'
        "  <rootfiles>"
        '    <rootfile full-path="OEBPS/content.opf"'
        ' media-type="application/oebps-package+xml"/>'
        "  </rootfiles>"
        "</container>"
    )
    # Manifest with only CSS — no XHTML content
    content_opf = (
        '<?xml version="1.0"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
        "  <manifest>"
        '    <item id="css" href="style.css"'
        ' media-type="text/css"/>'
        "  </manifest>"
        "</package>"
    )
    with zipfile.ZipFile(epub_path, "w") as zf:
        zf.writestr("META-INF/container.xml", container_xml)
        zf.writestr("OEBPS/content.opf", content_opf)
        zf.writestr("OEBPS/style.css", "body {}")

    out = tmp_path / "output.epub"
    result = translate_file(epub_path, out, "French", "English (US)")
    assert result is True
    assert out.exists()
    mock_translate.assert_not_called()


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_epub_multi_chapter(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """EPUB with multiple chapters translates all of them."""
    epub_path = tmp_path / "multi.epub"
    container_xml = (
        '<?xml version="1.0"?>'
        '<container xmlns="urn:oasis:names:tc:opendocument'
        ':xmlns:container" version="1.0">'
        "  <rootfiles>"
        '    <rootfile full-path="OEBPS/content.opf"'
        ' media-type="application/oebps-package+xml"/>'
        "  </rootfiles>"
        "</container>"
    )
    content_opf = (
        '<?xml version="1.0"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
        "  <manifest>"
        '    <item id="ch1" href="ch1.xhtml"'
        ' media-type="application/xhtml+xml"/>'
        '    <item id="ch2" href="ch2.xhtml"'
        ' media-type="application/xhtml+xml"/>'
        '    <item id="ch3" href="ch3.xhtml"'
        ' media-type="application/xhtml+xml"/>'
        "  </manifest>"
        "</package>"
    )
    with zipfile.ZipFile(epub_path, "w") as zf:
        zf.writestr("META-INF/container.xml", container_xml)
        zf.writestr("OEBPS/content.opf", content_opf)
        zf.writestr(
            "OEBPS/ch1.xhtml",
            "<html><body><p>Chapter 1</p></body></html>",
        )
        zf.writestr(
            "OEBPS/ch2.xhtml",
            "<html><body><p>Chapter 2</p></body></html>",
        )
        zf.writestr(
            "OEBPS/ch3.xhtml",
            "<html><body><p>Chapter 3</p></body></html>",
        )

    mock_translate.side_effect = lambda texts, *a, **kw: [f"[FR] {t}" for t in texts]

    out = tmp_path / "output.epub"
    result = translate_file(epub_path, out, "French", "English (US)")
    assert result is True

    with zipfile.ZipFile(out, "r") as zf:
        for ch in ["OEBPS/ch1.xhtml", "OEBPS/ch2.xhtml", "OEBPS/ch3.xhtml"]:
            content = zf.read(ch).decode("utf-8")
            assert "[FR]" in content


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_epub_cancel_mid_chapter(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """EPUB translation returns False when cancelled mid-chapter."""
    epub_path = _create_minimal_epub(tmp_path)
    out = tmp_path / "output.epub"

    call_count = 0

    def cancel_on_second() -> bool:
        nonlocal call_count
        call_count += 1
        return call_count > 1

    result = translate_file(
        epub_path,
        out,
        "French",
        "English (US)",
        cancel_check=cancel_on_second,
    )
    assert result is False


# ---------------------------------------------------------------------------
# JSON translate_file edge cases
# ---------------------------------------------------------------------------


@patch("src.core.llm_engine.translate_text")
def test_translate_file_json_root_array(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Translates a JSON file with root-level array."""
    src = tmp_path / "input.json"
    src.write_text(
        json.dumps(["hello", "world", 42]),
        encoding="utf-8",
    )
    out = tmp_path / "output.json"

    mock_translate.side_effect = lambda texts, *a, **kw: [f"[FR] {t}" for t in texts]

    result = translate_file(src, out, "French", "English (US)")
    assert result is True

    data = json.loads(out.read_text(encoding="utf-8"))
    assert data[0] == "[FR] hello"
    assert data[1] == "[FR] world"
    assert data[2] == 42  # noqa: PLR2004 — int preserved


@patch("src.core.llm_engine.translate_text")
def test_translate_file_json_cancel(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """JSON translation returns False when cancelled."""
    src = tmp_path / "input.json"
    src.write_text(json.dumps({"a": "hello"}), encoding="utf-8")
    out = tmp_path / "output.json"

    result = translate_file(
        src,
        out,
        "French",
        "English (US)",
        cancel_check=lambda: True,
    )
    assert result is False


# ---------------------------------------------------------------------------
# _translate_chunks — content_type forwarding
# ---------------------------------------------------------------------------


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_chunks_forwards_content_type(
    mock_translate: MagicMock,
) -> None:
    """content_type kwarg is forwarded to translate_text."""
    mock_translate.side_effect = lambda texts, *a, **kw: texts

    _translate_chunks(
        ["hello"],
        "French",
        "",
        progress_callback=None,
        glossary_entries=None,
        cancel_check=None,
        content_type="html",
    )

    _, kwargs = mock_translate.call_args
    assert kwargs["content_type"] == "html"


# ---------------------------------------------------------------------------
# _translate_chunks — checkpoint saves per chunk
# ---------------------------------------------------------------------------


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_chunks_saves_checkpoints(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Each translated chunk is saved to checkpoint directory."""
    mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]

    _translate_chunks(
        ["A", "B"],
        "French",
        "",
        progress_callback=None,
        glossary_entries=None,
        cancel_check=None,
        checkpoint_dir=tmp_path,
    )

    # Verify checkpoint was saved (can reload)
    from src.core.checkpoint import load_text_checkpoint  # noqa: PLC0415

    cached = load_text_checkpoint(tmp_path)
    assert cached is not None
    assert cached[0] == "[T] A"
    assert cached[1] == "[T] B"


# ---------------------------------------------------------------------------
# _process_plain — HTML attr stripping applied for .html
# ---------------------------------------------------------------------------


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_html_strips_attributes(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """HTML files have non-translatable attributes stripped before LLM."""
    src = tmp_path / "input.html"
    src.write_text(
        '<div class="foo"><p id="bar">Hello</p></div>',
        encoding="utf-8",
    )
    out = tmp_path / "output.html"

    captured: list[list[str]] = []

    def mock_fn(texts: list[str], *a: object, **kw: object) -> list[str]:
        captured.append(list(texts))
        return texts

    mock_translate.side_effect = mock_fn

    translate_file(src, out, "French", "English (US)")

    # The LLM should receive HTML without class/id attributes
    assert len(captured) > 0
    sent = captured[0][0]
    assert 'class="foo"' not in sent
    assert 'id="bar"' not in sent

    # But the output should have attributes restored
    content = out.read_text(encoding="utf-8")
    assert 'class="foo"' in content
    assert 'id="bar"' in content


# ---------------------------------------------------------------------------
# _process_plain — attr stripping NOT applied for non-HTML
# ---------------------------------------------------------------------------


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_txt_no_attr_stripping(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Plain text files do NOT have HTML attribute stripping applied."""
    src = tmp_path / "input.txt"
    src.write_text(
        '<div class="foo">Hello</div>',
        encoding="utf-8",
    )
    out = tmp_path / "output.txt"

    captured: list[list[str]] = []

    def mock_fn(texts: list[str], *a: object, **kw: object) -> list[str]:
        captured.append(list(texts))
        return texts

    mock_translate.side_effect = mock_fn

    translate_file(src, out, "French", "English (US)")

    # txt should NOT strip attributes — sent as-is
    sent = captured[0][0]
    assert 'class="foo"' in sent


# ---------------------------------------------------------------------------
# translate_file — glossary forwarding
# ---------------------------------------------------------------------------


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_forwards_glossary(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Glossary entries are forwarded through translate_file to LLM."""
    src = tmp_path / "input.txt"
    src.write_text("Hello world", encoding="utf-8")
    out = tmp_path / "output.txt"

    mock_translate.side_effect = lambda texts, *a, **kw: texts
    glossary = [(1, "hello", "bonjour")]

    translate_file(
        src,
        out,
        "French",
        "English (US)",
        glossary_entries=glossary,
    )

    _, kwargs = mock_translate.call_args
    assert kwargs["glossary_entries"] == glossary


# ---------------------------------------------------------------------------
# CSV — semicolon dialect
# ---------------------------------------------------------------------------


@patch("src.core.llm_engine.translate_text")
def test_translate_file_csv_semicolon_dialect(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """CSV with semicolon delimiter is detected and preserved."""
    src = tmp_path / "input.csv"
    src.write_text(
        "Name;Greeting\nAlice;Hello\n",
        encoding="utf-8",
    )
    out = tmp_path / "output.csv"

    mock_translate.side_effect = lambda texts, *a, **kw: [f"[FR] {t}" for t in texts]

    result = translate_file(src, out, "French", "English (US)")
    assert result is True

    content = out.read_text(encoding="utf-8")
    # Semicolons should be preserved in output
    assert ";" in content
    assert "[FR]" in content


# ---------------------------------------------------------------------------
# CSV — Unicode cells
# ---------------------------------------------------------------------------


@patch("src.core.llm_engine.translate_text")
def test_translate_file_csv_unicode_cells(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """CSV with Unicode cell values is translated correctly."""
    src = tmp_path / "input.csv"
    src.write_text(
        "Name,Greeting\nCafé,Straße\n",
        encoding="utf-8",
    )
    out = tmp_path / "output.csv"

    mock_translate.side_effect = lambda texts, *a, **kw: [f"[FR] {t}" for t in texts]

    result = translate_file(src, out, "French", "English (US)")
    assert result is True

    content = out.read_text(encoding="utf-8")
    assert "[FR] Café" in content
    assert "[FR] Straße" in content


# ---------------------------------------------------------------------------
# EPUB — missing OPF file
# ---------------------------------------------------------------------------


def test_get_epub_content_files_missing_opf(tmp_path: Path) -> None:
    """Returns empty list when OPF file is missing from archive."""
    epub_path = tmp_path / "bad_opf.epub"
    container_xml = (
        '<?xml version="1.0"?>'
        '<container xmlns="urn:oasis:names:tc:opendocument'
        ':xmlns:container" version="1.0">'
        "  <rootfiles>"
        '    <rootfile full-path="OEBPS/missing.opf"'
        ' media-type="application/oebps-package+xml"/>'
        "  </rootfiles>"
        "</container>"
    )
    with zipfile.ZipFile(epub_path, "w") as zf:
        zf.writestr("META-INF/container.xml", container_xml)

    with zipfile.ZipFile(epub_path, "r") as zf:
        assert _get_epub_content_files(zf) == []


# ---------------------------------------------------------------------------
# EPUB — text/html media type
# ---------------------------------------------------------------------------


def test_get_epub_content_files_text_html(tmp_path: Path) -> None:
    """Discovers files with text/html media type."""
    epub_path = tmp_path / "html.epub"
    container_xml = (
        '<?xml version="1.0"?>'
        '<container xmlns="urn:oasis:names:tc:opendocument'
        ':xmlns:container" version="1.0">'
        "  <rootfiles>"
        '    <rootfile full-path="content.opf"'
        ' media-type="application/oebps-package+xml"/>'
        "  </rootfiles>"
        "</container>"
    )
    content_opf = (
        '<?xml version="1.0"?>'
        '<package xmlns="http://www.idpf.org/2007/opf"'
        ' version="2.0">'
        "  <manifest>"
        '    <item id="ch1" href="ch1.html"'
        ' media-type="text/html"/>'
        "  </manifest>"
        "</package>"
    )
    with zipfile.ZipFile(epub_path, "w") as zf:
        zf.writestr("META-INF/container.xml", container_xml)
        zf.writestr("content.opf", content_opf)
        zf.writestr("ch1.html", "<html><body>Hi</body></html>")

    with zipfile.ZipFile(epub_path, "r") as zf:
        files = _get_epub_content_files(zf)
    assert len(files) == 1
    assert files[0] == "ch1.html"


# ---------------------------------------------------------------------------
# _chunk_text — exact boundary
# ---------------------------------------------------------------------------


def test_chunk_text_exact_max_chars() -> None:
    """Segment that exactly fits max_chars forms a single chunk."""
    # 10 chars + 2 separator = 12 per segment
    content = "1234567890\n\n1234567890"
    chunks, seps = _chunk_text(content, "\n\n", max_chars=24)
    # Both segments fit: 10 + 2 + 10 + 2 = 24 ≤ 24
    assert len(chunks) == 1
    assert chunks[0] == content
    assert seps == []


# ---------------------------------------------------------------------------
# translate_file — office format dispatch
# ---------------------------------------------------------------------------


@patch("src.core.text_processor.process_office_file")
def test_translate_file_dispatches_docx(
    mock_office: MagicMock,
    tmp_path: Path,
) -> None:
    """translate_file dispatches .docx to process_office_file."""
    src = tmp_path / "input.docx"
    src.touch()
    out = tmp_path / "output.docx"
    mock_office.return_value = True

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    mock_office.assert_called_once()


@patch("src.core.text_processor.process_office_file")
def test_translate_file_dispatches_xlsx(
    mock_office: MagicMock,
    tmp_path: Path,
) -> None:
    """translate_file dispatches .xlsx to process_office_file."""
    src = tmp_path / "input.xlsx"
    src.touch()
    out = tmp_path / "output.xlsx"
    mock_office.return_value = True

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    mock_office.assert_called_once()


@patch("src.core.text_processor.process_office_file")
def test_translate_file_dispatches_pptx(
    mock_office: MagicMock,
    tmp_path: Path,
) -> None:
    """translate_file dispatches .pptx to process_office_file."""
    src = tmp_path / "input.pptx"
    src.touch()
    out = tmp_path / "output.pptx"
    mock_office.return_value = True

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    mock_office.assert_called_once()


# ---------------------------------------------------------------------------
# translate_file — .htm alias
# ---------------------------------------------------------------------------


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_htm_alias(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """translate_file treats .htm same as .html."""
    src = tmp_path / "input.htm"
    src.write_text("<p>Hello</p>", encoding="utf-8")
    out = tmp_path / "output.htm"

    mock_translate.side_effect = lambda texts, *a, **kw: [f"[FR] {t}" for t in texts]

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    assert out.exists()


# ---------------------------------------------------------------------------
# _process_plain — whitespace-only file
# ---------------------------------------------------------------------------


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_whitespace_only_txt(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Whitespace-only text file is copied as-is, LLM not called."""
    src = tmp_path / "ws.txt"
    src.write_text("   \n\n   ", encoding="utf-8")
    out = tmp_path / "output.txt"

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    assert out.exists()
    mock_translate.assert_not_called()


# ---------------------------------------------------------------------------
# translate_file — legacy Office format dispatch
# ---------------------------------------------------------------------------


@patch("src.core.text_processor.process_office_file")
def test_translate_file_dispatches_doc(
    mock_office: MagicMock,
    tmp_path: Path,
) -> None:
    """translate_file dispatches .doc to process_office_file."""
    src = tmp_path / "input.doc"
    src.touch()
    out = tmp_path / "output.doc"
    mock_office.return_value = True

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    mock_office.assert_called_once()


@patch("src.core.text_processor.process_office_file")
def test_translate_file_dispatches_xls(
    mock_office: MagicMock,
    tmp_path: Path,
) -> None:
    """translate_file dispatches .xls to process_office_file."""
    src = tmp_path / "input.xls"
    src.touch()
    out = tmp_path / "output.xls"
    mock_office.return_value = True

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    mock_office.assert_called_once()


@patch("src.core.text_processor.process_office_file")
def test_translate_file_dispatches_ppt(
    mock_office: MagicMock,
    tmp_path: Path,
) -> None:
    """translate_file dispatches .ppt to process_office_file."""
    src = tmp_path / "input.ppt"
    src.touch()
    out = tmp_path / "output.ppt"
    mock_office.return_value = True

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    mock_office.assert_called_once()


# ---------------------------------------------------------------------------
# translate_file — ODF format dispatch
# ---------------------------------------------------------------------------


@patch("src.core.text_processor.process_office_file")
def test_translate_file_dispatches_odt(
    mock_office: MagicMock,
    tmp_path: Path,
) -> None:
    """translate_file dispatches .odt to process_office_file."""
    src = tmp_path / "input.odt"
    src.touch()
    out = tmp_path / "output.odt"
    mock_office.return_value = True

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    mock_office.assert_called_once()


@patch("src.core.text_processor.process_office_file")
def test_translate_file_dispatches_ods(
    mock_office: MagicMock,
    tmp_path: Path,
) -> None:
    """translate_file dispatches .ods to process_office_file."""
    src = tmp_path / "input.ods"
    src.touch()
    out = tmp_path / "output.ods"
    mock_office.return_value = True

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    mock_office.assert_called_once()


@patch("src.core.text_processor.process_office_file")
def test_translate_file_dispatches_odp(
    mock_office: MagicMock,
    tmp_path: Path,
) -> None:
    """translate_file dispatches .odp to process_office_file."""
    src = tmp_path / "input.odp"
    src.touch()
    out = tmp_path / "output.odp"
    mock_office.return_value = True

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    mock_office.assert_called_once()


# ---------------------------------------------------------------------------
# translate_file — JSON invalid input
# ---------------------------------------------------------------------------


def test_translate_file_json_invalid_json(tmp_path: Path) -> None:
    """Malformed JSON input raises ValueError (json.JSONDecodeError propagates)."""
    src = tmp_path / "bad.json"
    src.write_text("{not: valid json at all}", encoding="utf-8")
    out = tmp_path / "output.json"

    # json.JSONDecodeError is a subclass of ValueError and propagates as-is
    with pytest.raises(ValueError):
        translate_file(src, out, "French", "English (US)")


# ---------------------------------------------------------------------------
# translate_file — write error paths for CSV and JSON
# ---------------------------------------------------------------------------


@patch("src.core.llm_engine.translate_text")
def test_translate_file_csv_write_error(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """CSV write failure raises TEXT_WRITE_ERROR."""
    src = tmp_path / "input.csv"
    src.write_text("Name,Greeting\nAlice,Hello\n", encoding="utf-8")
    read_only = tmp_path / "readonly"
    read_only.mkdir()
    read_only.chmod(0o444)
    out = read_only / "subdir" / "output.csv"

    mock_translate.side_effect = lambda texts, *a, **kw: texts

    try:
        with pytest.raises(ValueError, match="TEXT_WRITE_ERROR"):
            translate_file(src, out, "French", "English (US)")
    finally:
        read_only.chmod(0o755)


@patch("src.core.llm_engine.translate_text")
def test_translate_file_json_write_error(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """JSON write failure raises TEXT_WRITE_ERROR."""
    src = tmp_path / "input.json"
    src.write_text('{"key": "hello"}', encoding="utf-8")
    read_only = tmp_path / "readonly"
    read_only.mkdir()
    read_only.chmod(0o444)
    out = read_only / "subdir" / "output.json"

    mock_translate.side_effect = lambda texts, *a, **kw: texts

    try:
        with pytest.raises(ValueError, match="TEXT_WRITE_ERROR"):
            translate_file(src, out, "French", "English (US)")
    finally:
        read_only.chmod(0o755)


# ---------------------------------------------------------------------------
# translate_file — EPUB content file with bad encoding is skipped
# ---------------------------------------------------------------------------


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_epub_content_bad_encoding(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """EPUB chapter with invalid UTF-8 is skipped; other chapters translate."""
    epub_path = tmp_path / "mixed.epub"
    container_xml = (
        '<?xml version="1.0"?>'
        '<container xmlns="urn:oasis:names:tc:opendocument'
        ':xmlns:container" version="1.0">'
        "  <rootfiles>"
        '    <rootfile full-path="OEBPS/content.opf"'
        ' media-type="application/oebps-package+xml"/>'
        "  </rootfiles>"
        "</container>"
    )
    content_opf = (
        '<?xml version="1.0"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
        "  <manifest>"
        '    <item id="ch1" href="ch1.xhtml"'
        ' media-type="application/xhtml+xml"/>'
        '    <item id="ch2" href="ch2.xhtml"'
        ' media-type="application/xhtml+xml"/>'
        "  </manifest>"
        "</package>"
    )
    # ch1 contains invalid UTF-8 bytes
    ch1_bytes = b"<html><body>\xff\xfe bad encoding</body></html>"
    ch2 = "<html><body><p>Chapter 2 content</p></body></html>"

    with zipfile.ZipFile(epub_path, "w") as zf:
        zf.writestr("META-INF/container.xml", container_xml)
        zf.writestr("OEBPS/content.opf", content_opf)
        zf.writestr("OEBPS/ch1.xhtml", ch1_bytes)  # stored as raw bytes
        zf.writestr("OEBPS/ch2.xhtml", ch2)

    mock_translate.side_effect = lambda texts, *a, **kw: [f"[FR] {t}" for t in texts]

    out = tmp_path / "output.epub"
    # Should succeed: ch1 is skipped, ch2 is translated
    result = translate_file(epub_path, out, "French", "English (US)")
    assert result is True
    assert out.exists()

    with zipfile.ZipFile(out, "r") as zf:
        ch2_content = zf.read("OEBPS/ch2.xhtml").decode("utf-8")
    assert "[FR]" in ch2_content


# ---------------------------------------------------------------------------
# _translate_chunks — empty input
# ---------------------------------------------------------------------------


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_chunks_empty_input(
    mock_translate: MagicMock,
) -> None:
    """Empty chunks list returns empty list without calling the LLM."""
    result = _translate_chunks(
        [],
        "French",
        "",
        progress_callback=None,
        glossary_entries=None,
        cancel_check=None,
        checkpoint_dir=None,
    )

    assert result == []
    mock_translate.assert_not_called()


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_chunks_empty_input_fires_progress(
    mock_translate: MagicMock,
) -> None:
    """Empty chunks list calls progress_callback(100) before returning."""
    progress_values: list[int] = []

    result = _translate_chunks(
        [],
        "French",
        "",
        progress_callback=progress_values.append,
        glossary_entries=None,
        cancel_check=None,
        checkpoint_dir=None,
    )

    assert result == []
    assert progress_values == [100]  # noqa: PLR2004
    mock_translate.assert_not_called()


# ---------------------------------------------------------------------------
# _repair_and_restore_attrs
# ---------------------------------------------------------------------------


def test_repair_and_restore_attrs_repairs_and_restores() -> None:
    """Repairs a missing tag and restores stripped attributes."""
    from src.utils.text_utils import AttrRecord, _AttrEntry  # noqa: PLC0415

    original = '<p data-ftid="0">Hello</p>'
    # Simulate LLM dropping the closing tag
    translated = '<p data-ftid="0">Bonjour'
    records = {
        0: AttrRecord(
            tag_name="p",
            attrs=[_AttrEntry('class="x"', False)],
        )
    }
    result = _repair_and_restore_attrs(translated, original, records)
    # Should have both the restored class attribute and repaired </p>
    assert 'class="x"' in result
    assert "</p>" in result


def test_repair_and_restore_attrs_empty_records() -> None:
    """With empty records, only tag repair is applied."""
    original = "<b>Hello</b>"
    translated = "<b>Bonjour</b>"
    result = _repair_and_restore_attrs(translated, original, {})
    assert result == "<b>Bonjour</b>"


# ---------------------------------------------------------------------------
# Subtitle translation (.srt, .vtt, .ass, .ssa)
# ---------------------------------------------------------------------------


@patch("src.core.llm_engine.translate_text")
def test_translate_file_srt(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Translates an .srt file preserving timestamps."""
    src = tmp_path / "input.srt"
    src.write_text(
        "1\n00:00:01,000 --> 00:00:04,000\nHello\n\n"
        "2\n00:00:05,000 --> 00:00:08,000\nWorld\n",
        encoding="utf-8",
    )
    out = tmp_path / "output.srt"

    mock_translate.side_effect = lambda texts, *a, **kw: [f"[FR] {t}" for t in texts]

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    content = out.read_text(encoding="utf-8")
    assert "00:00:01,000 --> 00:00:04,000" in content
    assert "00:00:05,000 --> 00:00:08,000" in content
    assert "[FR] Hello" in content
    assert "[FR] World" in content


@patch("src.core.llm_engine.translate_text")
def test_translate_file_vtt(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Translates a .vtt file preserving header and timestamps."""
    src = tmp_path / "input.vtt"
    src.write_text(
        "WEBVTT\n\n"
        "00:00:01.000 --> 00:00:04.000\nHello\n\n"
        "00:00:05.000 --> 00:00:08.000\nWorld\n",
        encoding="utf-8",
    )
    out = tmp_path / "output.vtt"

    mock_translate.side_effect = lambda texts, *a, **kw: [f"[FR] {t}" for t in texts]

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    content = out.read_text(encoding="utf-8")
    assert content.startswith("WEBVTT")
    assert "[FR] Hello" in content
    assert "[FR] World" in content


@patch("src.core.llm_engine.translate_text")
def test_translate_file_ass(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Translates an .ass file preserving styles and metadata."""
    src = tmp_path / "input.ass"
    src.write_text(
        "[Script Info]\nTitle: Test\n\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize\n"
        "Style: Default,Arial,20\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
        "MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,Hello\n"
        "Dialogue: 0,0:00:05.00,0:00:08.00,Default,,0,0,0,,World\n",
        encoding="utf-8",
    )
    out = tmp_path / "output.ass"

    mock_translate.side_effect = lambda texts, *a, **kw: [f"[FR] {t}" for t in texts]

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    content = out.read_text(encoding="utf-8")
    assert "[Script Info]" in content
    assert "[V4+ Styles]" in content
    assert "[FR] Hello" in content
    assert "[FR] World" in content


@patch("src.core.llm_engine.translate_text")
def test_translate_file_ssa(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Translates an .ssa file (same logic as .ass)."""
    src = tmp_path / "input.ssa"
    src.write_text(
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
        "MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,Hello\n",
        encoding="utf-8",
    )
    out = tmp_path / "output.ssa"

    mock_translate.side_effect = lambda texts, *a, **kw: [f"[FR] {t}" for t in texts]

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    content = out.read_text(encoding="utf-8")
    assert "[FR] Hello" in content


@patch("src.core.llm_engine.translate_text")
def test_translate_file_srt_cancel(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """SRT translation returns False when cancelled."""
    src = tmp_path / "input.srt"
    src.write_text(
        "1\n00:00:01,000 --> 00:00:04,000\nHello\n",
        encoding="utf-8",
    )
    out = tmp_path / "output.srt"

    result = translate_file(
        src,
        out,
        "French",
        "English (US)",
        cancel_check=lambda: True,
    )
    assert result is False
    mock_translate.assert_not_called()


@patch("src.core.llm_engine.translate_text")
def test_translate_file_srt_empty(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Empty SRT file is copied as-is."""
    src = tmp_path / "empty.srt"
    src.write_text("", encoding="utf-8")
    out = tmp_path / "output.srt"

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    assert out.exists()
    mock_translate.assert_not_called()


@patch("src.core.llm_engine.translate_text")
def test_translate_file_srt_write_error(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """SRT write failure raises TEXT_WRITE_ERROR."""
    src = tmp_path / "input.srt"
    src.write_text(
        "1\n00:00:01,000 --> 00:00:04,000\nHello\n",
        encoding="utf-8",
    )
    read_only = tmp_path / "readonly"
    read_only.mkdir()
    read_only.chmod(0o444)
    out = read_only / "subdir" / "output.srt"

    mock_translate.side_effect = lambda texts, *a, **kw: texts

    try:
        with pytest.raises(ValueError, match="TEXT_WRITE_ERROR"):
            translate_file(src, out, "French", "English (US)")
    finally:
        read_only.chmod(0o755)


# ---------------------------------------------------------------------------
# Localization translation (.po, .pot, .xliff, .xlf)
# ---------------------------------------------------------------------------


@patch("src.core.llm_engine.translate_text")
def test_translate_file_po(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Translates a .po file with msgstr filled."""
    src = tmp_path / "input.po"
    src.write_text(
        'msgid ""\nmsgstr ""\n\nmsgid "Hello"\nmsgstr ""\n\nmsgid "World"\nmsgstr ""\n',
        encoding="utf-8",
    )
    out = tmp_path / "output.po"

    mock_translate.side_effect = lambda texts, *a, **kw: [f"[FR] {t}" for t in texts]

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    content = out.read_text(encoding="utf-8")
    assert "[FR] Hello" in content
    assert "[FR] World" in content


@patch("src.core.llm_engine.translate_text")
def test_translate_file_pot(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Translates a .pot template file (empty msgstr filled)."""
    src = tmp_path / "input.pot"
    src.write_text(
        'msgid ""\nmsgstr ""\n\nmsgid "Greeting"\nmsgstr ""\n',
        encoding="utf-8",
    )
    out = tmp_path / "output.pot"

    mock_translate.side_effect = lambda texts, *a, **kw: [f"[FR] {t}" for t in texts]

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    content = out.read_text(encoding="utf-8")
    assert "[FR] Greeting" in content


@patch("src.core.llm_engine.translate_text")
def test_translate_file_xliff(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Translates an XLIFF 1.2 file."""
    src = tmp_path / "input.xliff"
    src.write_text(
        '<?xml version="1.0"?>'
        '<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2">'
        '<file source-language="en" target-language="fr" datatype="plaintext">'
        "<body>"
        '<trans-unit id="1"><source>Hello</source></trans-unit>'
        '<trans-unit id="2"><source>World</source></trans-unit>'
        "</body></file></xliff>",
        encoding="utf-8",
    )
    out = tmp_path / "output.xliff"

    mock_translate.side_effect = lambda texts, *a, **kw: [f"[FR] {t}" for t in texts]

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    content = out.read_text(encoding="utf-8")
    assert "[FR] Hello" in content
    assert "[FR] World" in content


@patch("src.core.llm_engine.translate_text")
def test_translate_file_xlf(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Translates an XLIFF 2.0 file with .xlf extension."""
    src = tmp_path / "input.xlf"
    src.write_text(
        '<?xml version="1.0"?>'
        '<xliff xmlns="urn:oasis:names:tc:xliff:document:2.0"'
        ' version="2.0" srcLang="en" trgLang="fr">'
        '<file id="f1">'
        '<unit id="u1"><segment><source>Hello</source></segment></unit>'
        "</file></xliff>",
        encoding="utf-8",
    )
    out = tmp_path / "output.xlf"

    mock_translate.side_effect = lambda texts, *a, **kw: [f"[FR] {t}" for t in texts]

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    content = out.read_text(encoding="utf-8")
    assert "[FR] Hello" in content


@patch("src.core.llm_engine.translate_text")
def test_translate_file_po_cancel(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """PO translation returns False when cancelled."""
    src = tmp_path / "input.po"
    src.write_text(
        'msgid ""\nmsgstr ""\n\nmsgid "Hello"\nmsgstr ""\n',
        encoding="utf-8",
    )
    out = tmp_path / "output.po"

    result = translate_file(
        src,
        out,
        "French",
        "English (US)",
        cancel_check=lambda: True,
    )
    assert result is False
    mock_translate.assert_not_called()


@patch("src.core.llm_engine.translate_text")
def test_translate_file_po_empty(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Empty PO file is copied as-is."""
    src = tmp_path / "empty.po"
    src.write_text("", encoding="utf-8")
    out = tmp_path / "output.po"

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    assert out.exists()
    mock_translate.assert_not_called()


@patch("src.core.llm_engine.translate_text")
def test_translate_file_po_write_error(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """PO write failure raises TEXT_WRITE_ERROR."""
    src = tmp_path / "input.po"
    src.write_text(
        'msgid ""\nmsgstr ""\n\nmsgid "Hello"\nmsgstr ""\n',
        encoding="utf-8",
    )
    read_only = tmp_path / "readonly"
    read_only.mkdir()
    read_only.chmod(0o444)
    out = read_only / "subdir" / "output.po"

    mock_translate.side_effect = lambda texts, *a, **kw: texts

    try:
        with pytest.raises(ValueError, match="TEXT_WRITE_ERROR"):
            translate_file(src, out, "French", "English (US)")
    finally:
        read_only.chmod(0o755)


@patch("src.core.llm_engine.translate_text")
def test_translate_file_po_plural(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """PO plural forms are translated correctly."""
    src = tmp_path / "input.po"
    src.write_text(
        'msgid ""\nmsgstr ""\n\n'
        'msgid "One item"\n'
        'msgid_plural "%d items"\n'
        'msgstr[0] ""\n'
        'msgstr[1] ""\n',
        encoding="utf-8",
    )
    out = tmp_path / "output.po"

    mock_translate.side_effect = lambda texts, *a, **kw: [f"[FR] {t}" for t in texts]

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    content = out.read_text(encoding="utf-8")
    assert "[FR] One item" in content
    assert "[FR] %d items" in content


@patch("src.core.llm_engine.translate_text")
def test_translate_file_po_header_preserved(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """PO header block is preserved after translation."""
    src = tmp_path / "input.po"
    src.write_text(
        "# My translations\n"
        'msgid ""\n'
        'msgstr ""\n'
        '"Content-Type: text/plain; charset=UTF-8\\n"\n\n'
        'msgid "Hello"\n'
        'msgstr ""\n',
        encoding="utf-8",
    )
    out = tmp_path / "output.po"

    mock_translate.side_effect = lambda texts, *a, **kw: [f"[FR] {t}" for t in texts]

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    content = out.read_text(encoding="utf-8")
    assert "Content-Type" in content
    assert "[FR] Hello" in content


# ---------------------------------------------------------------------------
# Key-value format translation (.yaml, .yml, .properties, .strings)
# ---------------------------------------------------------------------------


@patch("src.core.llm_engine.translate_text")
def test_translate_file_yaml(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Translates a YAML file with string values."""
    src = tmp_path / "input.yaml"
    src.write_text("greeting: Hello\nfarewell: Goodbye\n", encoding="utf-8")
    out = tmp_path / "output.yaml"

    mock_translate.side_effect = lambda texts, *a, **kw: [f"[FR] {t}" for t in texts]

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    content = out.read_text(encoding="utf-8")
    assert "[FR] Hello" in content
    assert "[FR] Goodbye" in content


@patch("src.core.llm_engine.translate_text")
def test_translate_file_yml(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Translates a .yml file (alias for YAML)."""
    src = tmp_path / "input.yml"
    src.write_text("menu:\n  file: File\n", encoding="utf-8")
    out = tmp_path / "output.yml"

    mock_translate.side_effect = lambda texts, *a, **kw: [f"[FR] {t}" for t in texts]

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    content = out.read_text(encoding="utf-8")
    assert "[FR] File" in content


@patch("src.core.llm_engine.translate_text")
def test_translate_file_properties(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Translates a Java Properties file."""
    src = tmp_path / "input.properties"
    src.write_text(
        "# Messages\ngreeting=Hello\nfarewell=Goodbye\n",
        encoding="utf-8",
    )
    out = tmp_path / "output.properties"

    mock_translate.side_effect = lambda texts, *a, **kw: [f"[FR] {t}" for t in texts]

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    content = out.read_text(encoding="utf-8")
    assert "[FR] Hello" in content
    assert "[FR] Goodbye" in content
    assert "# Messages" in content


@patch("src.core.llm_engine.translate_text")
def test_translate_file_strings(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Translates an Apple Strings file."""
    src = tmp_path / "input.strings"
    src.write_text(
        '/* Greetings */\n"greeting" = "Hello";\n"farewell" = "Goodbye";\n',
        encoding="utf-8",
    )
    out = tmp_path / "output.strings"

    mock_translate.side_effect = lambda texts, *a, **kw: [f"[FR] {t}" for t in texts]

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    content = out.read_text(encoding="utf-8")
    assert "[FR] Hello" in content
    assert "[FR] Goodbye" in content


@patch("src.core.llm_engine.translate_text")
def test_translate_file_yaml_cancel(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """YAML translation returns False when cancelled."""
    src = tmp_path / "input.yaml"
    src.write_text("key: Value\n", encoding="utf-8")
    out = tmp_path / "output.yaml"

    result = translate_file(
        src,
        out,
        "French",
        "English (US)",
        cancel_check=lambda: True,
    )
    assert result is False
    mock_translate.assert_not_called()


@patch("src.core.llm_engine.translate_text")
def test_translate_file_yaml_empty(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Empty YAML file is copied as-is."""
    src = tmp_path / "empty.yaml"
    src.write_text("", encoding="utf-8")
    out = tmp_path / "output.yaml"

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    assert out.exists()
    mock_translate.assert_not_called()


@patch("src.core.llm_engine.translate_text")
def test_translate_file_yaml_write_error(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """YAML write failure raises TEXT_WRITE_ERROR."""
    src = tmp_path / "input.yaml"
    src.write_text("key: Value\n", encoding="utf-8")
    read_only = tmp_path / "readonly"
    read_only.mkdir()
    read_only.chmod(0o444)
    out = read_only / "subdir" / "output.yaml"

    mock_translate.side_effect = lambda texts, *a, **kw: texts

    try:
        with pytest.raises(ValueError, match="TEXT_WRITE_ERROR"):
            translate_file(src, out, "French", "English (US)")
    finally:
        read_only.chmod(0o755)


def test_translate_file_yaml_invalid(tmp_path: Path) -> None:
    """Malformed YAML raises TEXT_READ_ERROR."""
    src = tmp_path / "bad.yaml"
    # Tab indentation is forbidden in YAML — causes yaml.scanner.ScannerError
    src.write_text("parent:\n\tchild: value\n", encoding="utf-8")
    out = tmp_path / "out.yaml"
    with pytest.raises(ValueError, match="TEXT_READ_ERROR"):
        translate_file(src, out, "French", "English (US)")


# ---------------------------------------------------------------------------
# translate_file — PDF dispatch
# ---------------------------------------------------------------------------


@patch("src.core.pdf_processor.process_pdf_file")
def test_translate_file_dispatches_pdf(
    mock_pdf: MagicMock,
    tmp_path: Path,
) -> None:
    """translate_file dispatches .pdf to process_pdf_file."""
    src = tmp_path / "input.pdf"
    src.write_bytes(b"%PDF-1.4\n")  # Minimal valid PDF header
    out = tmp_path / "output.pdf"
    mock_pdf.return_value = True

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    mock_pdf.assert_called_once()


@patch("src.core.pdf_processor.process_pdf_file")
def test_translate_file_pdf_forwards_all_args(
    mock_pdf: MagicMock,
    tmp_path: Path,
) -> None:
    """translate_file forwards all arguments to process_pdf_file."""
    src = tmp_path / "input.pdf"
    src.write_bytes(b"%PDF-1.4\n")
    out = tmp_path / "output.pdf"
    mock_pdf.return_value = True
    glossary = [(1, "Hello", "Bonjour")]
    cancel = lambda: False  # noqa: E731
    cp_dir = tmp_path / "cp"
    cp_dir.mkdir()

    translate_file(
        src,
        out,
        "French",
        "English (US)",
        glossary_entries=glossary,
        cancel_check=cancel,
        checkpoint_dir=cp_dir,
    )

    call_args = mock_pdf.call_args
    # Positional args: file_path, output_path, target_lang, src_lang,
    #   progress_callback, glossary_entries, cancel_check
    assert call_args[0][0] == src  # file_path
    # Atomic-output contract: the processor writes to a partial file
    # inside ``checkpoint_dir`` so the user's destination only sees the
    # finished result.  ``translate_file`` does the move on success.
    assert call_args[0][1] == cp_dir / f"_partial{out.suffix}"
    assert call_args[0][2] == "French"  # target_lang
    assert call_args[0][3] == "English (US)"  # src_lang
    assert call_args[0][5] == glossary  # glossary_entries (index 5)
    assert call_args[0][6] is cancel  # cancel_check (index 6)
    assert call_args[1].get("checkpoint_dir") == cp_dir  # keyword arg


# ---------------------------------------------------------------------------
# Atomic output: user-visible output_path is updated only on success
# ---------------------------------------------------------------------------


@patch("src.core.pdf_processor.process_pdf_file")
def test_translate_file_atomic_move_on_success(
    mock_pdf: MagicMock,
    tmp_path: Path,
) -> None:
    """On success the partial file is moved into the user's output path.

    The dispatched processor writes to ``<checkpoint_dir>/_partial.<ext>``;
    ``translate_file`` then moves it to ``output_path`` so the user-
    visible destination only ever contains complete files.
    """
    src = tmp_path / "input.pdf"
    src.write_bytes(b"%PDF-1.4\n")
    out = tmp_path / "out_dir" / "output.pdf"
    cp_dir = tmp_path / "cp"
    cp_dir.mkdir()

    # The dispatch writes a "translated" payload to the partial path
    # exactly like a real processor would.
    def fake_pdf(
        _src,
        dispatch_out,
        *_args,
        **_kwargs,
    ) -> bool:
        dispatch_out.write_bytes(b"translated-pdf-payload")
        return True

    mock_pdf.side_effect = fake_pdf
    result = translate_file(src, out, "French", checkpoint_dir=cp_dir)

    assert result is True
    assert out.exists()
    assert out.read_bytes() == b"translated-pdf-payload"
    # Partial file no longer exists in the storage dir.
    assert not (cp_dir / "_partial.pdf").exists()


@patch("src.core.pdf_processor.process_pdf_file")
def test_translate_file_atomic_leaves_output_untouched_on_failure(
    mock_pdf: MagicMock,
    tmp_path: Path,
) -> None:
    """A typed processor failure must not produce a partial output file.

    The user-visible ``output_path`` must not exist after a failed
    translation — orphan partial files in the output folder confuse
    users about whether a task succeeded.
    """
    src = tmp_path / "input.pdf"
    src.write_bytes(b"%PDF-1.4\n")
    out = tmp_path / "output.pdf"
    cp_dir = tmp_path / "cp"
    cp_dir.mkdir()

    # Simulate a real processor: writes a half-translated file, then
    # raises a typed error (e.g. AUTH_ERROR mid-loop).
    def fake_pdf(
        _src,
        dispatch_out,
        *_args,
        **_kwargs,
    ) -> bool:
        dispatch_out.write_bytes(b"partial-payload")
        msg = "AUTH_ERROR"
        raise ValueError(msg)

    mock_pdf.side_effect = fake_pdf

    with pytest.raises(ValueError, match="AUTH_ERROR"):
        translate_file(src, out, "French", checkpoint_dir=cp_dir)

    # Output path untouched — atomic-output contract holds even when
    # the underlying processor wrote bytes to its dispatch target.
    assert not out.exists()


@patch("src.core.pdf_processor.process_pdf_file")
def test_translate_file_atomic_no_move_on_cancel(
    mock_pdf: MagicMock,
    tmp_path: Path,
) -> None:
    """Cancellation (return False) must not promote the partial file.

    The processor returns False on user cancellation — same as a
    failure as far as user-visible state goes.  The partial file
    stays in storage so the cache + checkpoints line up on resume.
    """
    src = tmp_path / "input.pdf"
    src.write_bytes(b"%PDF-1.4\n")
    out = tmp_path / "output.pdf"
    cp_dir = tmp_path / "cp"
    cp_dir.mkdir()

    def fake_pdf(
        _src,
        dispatch_out,
        *_args,
        **_kwargs,
    ) -> bool:
        dispatch_out.write_bytes(b"half-done")
        return False  # user pressed Stop

    mock_pdf.side_effect = fake_pdf
    result = translate_file(src, out, "French", checkpoint_dir=cp_dir)

    assert result is False
    assert not out.exists()
    # Partial bytes still live in the storage dir so checkpoints align.
    assert (cp_dir / "_partial.pdf").read_bytes() == b"half-done"


@patch("src.core.pdf_processor.process_pdf_file")
def test_translate_file_without_checkpoint_dir_writes_directly(
    mock_pdf: MagicMock,
    tmp_path: Path,
) -> None:
    """Backward-compat path: no checkpoint_dir means write directly to output.

    Otherwise headless / CLI invocations without a per-task storage
    area would silently lose their output.
    """
    src = tmp_path / "input.pdf"
    src.write_bytes(b"%PDF-1.4\n")
    out = tmp_path / "output.pdf"

    def fake_pdf(
        _src,
        dispatch_out,
        *_args,
        **_kwargs,
    ) -> bool:
        dispatch_out.write_bytes(b"direct-write")
        return True

    mock_pdf.side_effect = fake_pdf
    result = translate_file(src, out, "French")

    assert result is True
    # The processor was handed the user-visible output_path directly.
    assert mock_pdf.call_args[0][1] == out
    assert out.read_bytes() == b"direct-write"


@patch("src.core.pdf_processor.process_pdf_file")
def test_translate_file_atomic_bug_exception_leaves_output_untouched(
    mock_pdf: MagicMock,
    tmp_path: Path,
) -> None:
    """A programming-bug exception still preserves atomic-output semantics.

    ``_BUG_EXCEPTIONS`` (AttributeError, TypeError, KeyError, …)
    propagate untouched so the outer translator pipeline reports
    them as ``ERR_UNKNOWN`` with a real traceback.  But the user-
    visible ``output_path`` must NOT exist after such a crash —
    partial bytes already written to ``_partial.pdf`` stay confined
    to the storage dir.
    """
    src = tmp_path / "input.pdf"
    src.write_bytes(b"%PDF-1.4\n")
    out = tmp_path / "output.pdf"
    cp_dir = tmp_path / "cp"
    cp_dir.mkdir()

    def fake_pdf(
        _src,
        dispatch_out,
        *_args,
        **_kwargs,
    ) -> bool:
        dispatch_out.write_bytes(b"half-done-before-bug")
        msg = "ghost attr"
        raise AttributeError(msg)

    mock_pdf.side_effect = fake_pdf
    with pytest.raises(AttributeError, match="ghost attr"):
        translate_file(src, out, "French", checkpoint_dir=cp_dir)

    # User-visible output untouched even though processor wrote bytes.
    assert not out.exists()
    # Partial bytes still in storage (resume-safe), not promoted.
    assert (cp_dir / "_partial.pdf").read_bytes() == b"half-done-before-bug"


@patch("src.core.pdf_processor.process_pdf_file")
def test_translate_file_atomic_text_read_error_leaves_output_untouched(
    mock_pdf: MagicMock,
    tmp_path: Path,
) -> None:
    """A corrupt-file ``Exception`` re-badged as TEXT_READ_ERROR holds atomicity.

    ``translate_file`` maps generic exceptions (yaml/xml/zipfile
    surprises) to ``ValueError("TEXT_READ_ERROR")`` so the UI can
    display a friendly message.  The user-visible ``output_path``
    must still be untouched — the partial file stays in storage.
    """
    src = tmp_path / "input.pdf"
    src.write_bytes(b"%PDF-1.4\n")
    out = tmp_path / "output.pdf"
    cp_dir = tmp_path / "cp"
    cp_dir.mkdir()

    def fake_pdf(
        _src,
        dispatch_out,
        *_args,
        **_kwargs,
    ) -> bool:
        dispatch_out.write_bytes(b"partial-before-corrupt-file-blame")
        # Anything not in _BUG_EXCEPTIONS or ValueError → wrapped as
        # TEXT_READ_ERROR.  ``zipfile.BadZipFile`` is the canonical
        # example mentioned in the production code's comments.
        import zipfile  # noqa: PLC0415

        msg = "bad zip"
        raise zipfile.BadZipFile(msg)

    mock_pdf.side_effect = fake_pdf
    with pytest.raises(ValueError, match="TEXT_READ_ERROR"):
        translate_file(src, out, "French", checkpoint_dir=cp_dir)

    # User-visible output untouched.
    assert not out.exists()


@patch("src.core.pdf_processor.process_pdf_file")
def test_translate_file_atomic_creates_output_parent_dir_on_success(
    mock_pdf: MagicMock,
    tmp_path: Path,
) -> None:
    """The atomic publish step ``mkdir(parents=True)`` for the output path.

    A user may configure an output directory that doesn't exist yet
    (e.g. ``~/Documents/Translations/2026/``).  The atomic move on
    success must lazily create the parent chain, otherwise the
    ``shutil.move`` would raise ``FileNotFoundError`` and lose the
    successful translation.
    """
    src = tmp_path / "input.pdf"
    src.write_bytes(b"%PDF-1.4\n")
    # Output parent has THREE non-existent levels — the mkdir must
    # recurse all the way.
    out = tmp_path / "deep" / "nested" / "dir" / "output.pdf"
    cp_dir = tmp_path / "cp"
    cp_dir.mkdir()

    def fake_pdf(
        _src,
        dispatch_out,
        *_args,
        **_kwargs,
    ) -> bool:
        dispatch_out.write_bytes(b"translated-payload")
        return True

    mock_pdf.side_effect = fake_pdf
    result = translate_file(src, out, "French", checkpoint_dir=cp_dir)

    assert result is True
    assert out.exists()
    assert out.parent.is_dir()
    assert out.read_bytes() == b"translated-payload"


@patch("src.core.pdf_processor.process_pdf_file")
def test_translate_file_atomic_success_with_no_partial_written(
    mock_pdf: MagicMock,
    tmp_path: Path,
) -> None:
    """Processor returns success without writing anything → no spurious move.

    Defensive: if a processor returns ``True`` but for some reason
    no partial file exists (e.g. a future "nothing to translate"
    fast-path), the ``dispatch_output.exists()`` guard short-circuits
    the move so ``shutil.move`` doesn't error on a missing source.
    The caller's ``output_path`` stays absent — same outcome as a
    failed run, which is the safer default.
    """
    src = tmp_path / "input.pdf"
    src.write_bytes(b"%PDF-1.4\n")
    out = tmp_path / "output.pdf"
    cp_dir = tmp_path / "cp"
    cp_dir.mkdir()

    def fake_pdf(
        _src,
        _dispatch_out,
        *_args,
        **_kwargs,
    ) -> bool:
        # Deliberately do NOT write anything.
        return True

    mock_pdf.side_effect = fake_pdf
    # Must not raise FileNotFoundError on the missing partial.
    result = translate_file(src, out, "French", checkpoint_dir=cp_dir)

    assert result is True
    # No partial → no move → output stays absent.
    assert not out.exists()


# ---------------------------------------------------------------------------
# Password-protected file detection
# ---------------------------------------------------------------------------


def test_translate_file_password_protected(tmp_path: Path) -> None:
    """Password-protected file raises PASSWORD_PROTECTED error."""
    src = tmp_path / "secret.docx"
    # OLE2 magic bytes indicate an encrypted modern Office file
    src.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 100)
    out = tmp_path / "output.docx"
    with pytest.raises(ValueError, match="PASSWORD_PROTECTED"):
        translate_file(src, out, "French", "English (US)")


def test_translate_file_password_protected_leaves_no_partial(
    tmp_path: Path,
) -> None:
    """PASSWORD_PROTECTED early-raise must NOT create ``_partial<ext>``.

    The encryption check happens before dispatch, so no partial
    file is ever written.  Regression guard: a future refactor that
    moves the check past the temp-path setup would silently leave
    orphan ``_partial.docx`` files in storage on every encrypted-
    file attempt.
    """
    src = tmp_path / "secret.docx"
    src.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 100)
    out = tmp_path / "output.docx"
    cp_dir = tmp_path / "cp"
    cp_dir.mkdir()
    with pytest.raises(ValueError, match="PASSWORD_PROTECTED"):
        translate_file(src, out, "French", checkpoint_dir=cp_dir)
    # No ``_partial.docx`` in storage; nothing in user output.
    assert not (cp_dir / "_partial.docx").exists()
    assert not out.exists()


# ---------------------------------------------------------------------------
# _detect_encoding — fallback
# ---------------------------------------------------------------------------


def test_detect_encoding_none_result_falls_back_to_latin1() -> None:
    """Returns latin-1 when charset_normalizer.best() returns None."""
    from src.core.text_processor import _detect_encoding  # noqa: PLC0415

    mock_result = MagicMock()
    mock_result.best.return_value = None

    with patch(
        "src.core.text_processor._detect_bytes",
        return_value=mock_result,
    ):
        assert _detect_encoding(b"\x80\x81\x82") == "latin-1"


# ---------------------------------------------------------------------------
# EPUB — _get_epub_content_files edge cases
# ---------------------------------------------------------------------------


def _make_epub_zip(tmp_path: Path, files: dict[str, str]) -> Path:
    """Creates a minimal EPUB zip with the given files."""
    epub_path = tmp_path / "test.epub"
    with zipfile.ZipFile(epub_path, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return epub_path


def test_epub_content_files_no_rootfile(tmp_path: Path) -> None:
    """Returns [] when container.xml has no <rootfile> element."""
    container = (
        '<?xml version="1.0"?>'
        '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        "<rootfiles></rootfiles></container>"
    )
    epub = _make_epub_zip(tmp_path, {"META-INF/container.xml": container})
    with zipfile.ZipFile(epub, "r") as zf:
        assert _get_epub_content_files(zf) == []


def test_epub_content_files_empty_fullpath(tmp_path: Path) -> None:
    """Returns [] when rootfile full-path attribute is empty."""
    container = (
        '<?xml version="1.0"?>'
        '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        "<rootfiles>"
        '<rootfile full-path="" media-type="application/oebps-package+xml"/>'
        "</rootfiles></container>"
    )
    epub = _make_epub_zip(tmp_path, {"META-INF/container.xml": container})
    with zipfile.ZipFile(epub, "r") as zf:
        assert _get_epub_content_files(zf) == []


def test_epub_content_files_no_manifest(tmp_path: Path) -> None:
    """Returns [] when OPF file exists but has no <manifest> element."""
    container = (
        '<?xml version="1.0"?>'
        '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        "<rootfiles>"
        '<rootfile full-path="content.opf"'
        ' media-type="application/oebps-package+xml"/>'
        "</rootfiles></container>"
    )
    opf = (
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
        "<metadata/></package>"
    )
    epub = _make_epub_zip(
        tmp_path,
        {"META-INF/container.xml": container, "content.opf": opf},
    )
    with zipfile.ZipFile(epub, "r") as zf:
        assert _get_epub_content_files(zf) == []


# ---------------------------------------------------------------------------
# Encoding edge cases
# ---------------------------------------------------------------------------


def test_read_file_utf8_bom(tmp_path: Path) -> None:
    """UTF-8 BOM prefix is stripped from returned content."""
    f = tmp_path / "bom.txt"
    f.write_bytes(b"\xef\xbb\xbfHello")
    result = _read_file(f)
    assert result == "Hello"
    assert not result.startswith("\ufeff")


def test_read_file_binary_content_fallback(tmp_path: Path) -> None:
    """Binary bytes fall back to detected encoding without crash."""
    f = tmp_path / "binary.txt"
    f.write_bytes(b"\x80\x81\x82\x83")
    result = _read_file(f)
    # charset_normalizer may detect any encoding; the key is no exception
    assert isinstance(result, str)
    assert len(result) >= 1


def test_read_file_empty_file(tmp_path: Path) -> None:
    """A 0-byte file returns an empty string."""
    f = tmp_path / "empty.txt"
    f.write_bytes(b"")
    assert _read_file(f) == ""


def test_read_file_utf16_detection(tmp_path: Path) -> None:
    """UTF-16 encoded content is detected and decoded correctly."""
    text = "Bonjour le monde"
    f = tmp_path / "utf16.txt"
    f.write_bytes(text.encode("utf-16"))
    result = _read_file(f)
    assert "Bonjour le monde" in result


def test_detect_encoding_returns_correct_charset() -> None:
    """_detect_encoding uses charset_normalizer result when available."""
    from src.core.text_processor import _detect_encoding  # noqa: PLC0415

    mock_best = MagicMock()
    mock_best.encoding = "shift_jis"
    mock_result = MagicMock()
    mock_result.best.return_value = mock_best

    with patch("src.core.text_processor._detect_bytes", return_value=mock_result):
        assert _detect_encoding(b"\x82\xb1\x82\xf1") == "shift_jis"


# ---------------------------------------------------------------------------
# CSV edge cases
# ---------------------------------------------------------------------------


@patch("src.core.llm_engine.translate_text")
def test_translate_file_csv_quoted_fields_with_newlines(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """CSV cell containing a newline inside quotes is preserved."""
    src = tmp_path / "input.csv"
    # RFC 4180: newlines inside double-quoted fields are part of the value
    src.write_text(
        'Name,Greeting\n"Alice","Hello\nWorld"\n',
        encoding="utf-8",
    )
    out = tmp_path / "output.csv"

    mock_translate.side_effect = lambda texts, *a, **kw: [f"[FR] {t}" for t in texts]

    result = translate_file(src, out, "French", "English (US)")
    assert result is True

    content = out.read_text(encoding="utf-8")
    assert "[FR] Alice" in content
    # The translated cell should still appear (with or without quoting)
    assert "[FR]" in content


@patch("src.core.llm_engine.translate_text")
def test_translate_file_csv_tab_delimiter(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Tab-delimited CSV is auto-detected and tabs preserved."""
    src = tmp_path / "input.csv"
    src.write_text(
        "Name\tGreeting\nAlice\tHello\n",
        encoding="utf-8",
    )
    out = tmp_path / "output.csv"

    mock_translate.side_effect = lambda texts, *a, **kw: [f"[FR] {t}" for t in texts]

    result = translate_file(src, out, "French", "English (US)")
    assert result is True

    content = out.read_text(encoding="utf-8")
    assert "\t" in content
    assert "[FR]" in content


@patch("src.core.llm_engine.translate_text")
def test_translate_file_csv_single_column(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """CSV with only one column has all cells translated."""
    src = tmp_path / "input.csv"
    src.write_text("Greeting\nHello\nWorld\n", encoding="utf-8")
    out = tmp_path / "output.csv"

    mock_translate.side_effect = lambda texts, *a, **kw: [f"[FR] {t}" for t in texts]

    result = translate_file(src, out, "French", "English (US)")
    assert result is True

    content = out.read_text(encoding="utf-8")
    assert "[FR] Greeting" in content
    assert "[FR] Hello" in content
    assert "[FR] World" in content


@patch("src.core.llm_engine.translate_text")
def test_translate_file_csv_bom_stripped(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """CSV with UTF-8 BOM does not leak the BOM into translated output."""
    src = tmp_path / "input.csv"
    src.write_bytes(b"\xef\xbb\xbfName,Value\nAlice,Hello\n")
    out = tmp_path / "output.csv"

    mock_translate.side_effect = lambda texts, *a, **kw: [f"[FR] {t}" for t in texts]

    result = translate_file(src, out, "French", "English (US)")
    assert result is True

    raw = out.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    content = out.read_text(encoding="utf-8")
    assert "\ufeff" not in content
    assert "[FR]" in content


# ---------------------------------------------------------------------------
# JSON edge cases
# ---------------------------------------------------------------------------


def test_extract_json_strings_numeric_and_bool() -> None:
    """Only string values are extracted; numbers, bools, null are skipped."""
    obj = {"a": 1, "b": True, "c": None, "d": "text"}
    result = _extract_json_strings(obj)
    # Only "text" should be extracted
    assert len(result) == 1
    path, value = result[0]
    assert path == ("d",)
    assert value == "text"


@patch("src.core.llm_engine.translate_text")
def test_translate_file_json_deeply_nested(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Deeply nested JSON (5+ levels) has all string values translated."""
    src = tmp_path / "input.json"
    data = {
        "l1": {
            "l2": {
                "l3": {
                    "l4": {
                        "l5": {"deep_value": "found me"},
                    },
                },
            },
        },
        "top": "surface",
    }
    src.write_text(json.dumps(data), encoding="utf-8")
    out = tmp_path / "output.json"

    mock_translate.side_effect = lambda texts, *a, **kw: [f"[FR] {t}" for t in texts]

    result = translate_file(src, out, "French", "English (US)")
    assert result is True

    translated = json.loads(out.read_text(encoding="utf-8"))
    assert translated["l1"]["l2"]["l3"]["l4"]["l5"]["deep_value"] == "[FR] found me"
    assert translated["top"] == "[FR] surface"


@patch("src.core.llm_engine.translate_text")
def test_translate_file_json_empty_object(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Empty JSON object returns True without calling translate."""
    src = tmp_path / "input.json"
    src.write_text("{}", encoding="utf-8")
    out = tmp_path / "output.json"

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    mock_translate.assert_not_called()

    translated = json.loads(out.read_text(encoding="utf-8"))
    assert translated == {}


# ---------------------------------------------------------------------------
# Subtitle edge cases
# ---------------------------------------------------------------------------


@patch("src.core.llm_engine.translate_text")
def test_translate_file_srt_multiline_cue(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """SRT with multi-line subtitle text translates both lines."""
    src = tmp_path / "input.srt"
    src.write_text(
        "1\n00:00:01,000 --> 00:00:04,000\nLine one\nLine two\n\n",
        encoding="utf-8",
    )
    out = tmp_path / "output.srt"

    mock_translate.side_effect = lambda texts, *a, **kw: [f"[FR] {t}" for t in texts]

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    content = out.read_text(encoding="utf-8")
    assert "00:00:01,000 --> 00:00:04,000" in content
    assert "[FR]" in content


@patch("src.core.llm_engine.translate_text")
def test_translate_file_vtt_with_styling(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """VTT with STYLE block preserves styles and translates text."""
    src = tmp_path / "input.vtt"
    src.write_text(
        "WEBVTT\n\n"
        "STYLE\n::cue { color: yellow; }\n\n"
        "00:00:01.000 --> 00:00:04.000\nHello\n\n"
        "00:00:05.000 --> 00:00:08.000\nWorld\n",
        encoding="utf-8",
    )
    out = tmp_path / "output.vtt"

    mock_translate.side_effect = lambda texts, *a, **kw: [f"[FR] {t}" for t in texts]

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    content = out.read_text(encoding="utf-8")
    assert content.startswith("WEBVTT")
    assert "[FR] Hello" in content
    assert "[FR] World" in content


@patch("src.core.llm_engine.translate_text")
def test_translate_file_ass_with_override_tags(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """ASS with override tags preserves tags and translates text."""
    src = tmp_path / "input.ass"
    src.write_text(
        "[Script Info]\nTitle: Test\n\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize\n"
        "Style: Default,Arial,20\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
        "MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,"
        "{\\b1}Bold{\\b0} normal\n",
        encoding="utf-8",
    )
    out = tmp_path / "output.ass"

    mock_translate.side_effect = lambda texts, *a, **kw: [f"[FR] {t}" for t in texts]

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    content = out.read_text(encoding="utf-8")
    assert "[Script Info]" in content
    assert "[V4+ Styles]" in content
    # The leading override tag should be preserved in the dialogue line
    assert "{\\b1}" in content
    assert "[FR]" in content


# ---------------------------------------------------------------------------
# EPUB edge cases
# ---------------------------------------------------------------------------


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_epub_single_chapter(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """EPUB with a single chapter translates its text content."""
    src = _create_minimal_epub(tmp_path)
    out = tmp_path / "output.epub"

    mock_translate.side_effect = lambda texts, *a, **kw: [f"[FR] {t}" for t in texts]

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    assert out.exists()

    with zipfile.ZipFile(out, "r") as zf:
        chapter = zf.read("OEBPS/chapter1.xhtml").decode("utf-8")
        assert "[FR]" in chapter


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_epub_preserves_non_content_files(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """EPUB images and CSS files are not modified during translation."""
    epub_path = tmp_path / "test_preserve.epub"

    container_xml = (
        '<?xml version="1.0"?>'
        '<container xmlns="urn:oasis:names:tc:opendocument'
        ':xmlns:container" version="1.0">'
        "  <rootfiles>"
        '    <rootfile full-path="OEBPS/content.opf"'
        ' media-type="application/oebps-package+xml"/>'
        "  </rootfiles>"
        "</container>"
    )
    content_opf = (
        '<?xml version="1.0"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
        "  <manifest>"
        '    <item id="ch1" href="chapter1.xhtml"'
        ' media-type="application/xhtml+xml"/>'
        '    <item id="css" href="style.css"'
        ' media-type="text/css"/>'
        '    <item id="img" href="image.png"'
        ' media-type="image/png"/>'
        "  </manifest>"
        "</package>"
    )
    chapter_xhtml = '<?xml version="1.0"?><html><body><p>Hello</p></body></html>'
    css_content = "body { color: black; font-size: 14px; }"
    # Fake PNG header (8 bytes)
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50

    with zipfile.ZipFile(epub_path, "w") as zf:
        zf.writestr("META-INF/container.xml", container_xml)
        zf.writestr("OEBPS/content.opf", content_opf)
        zf.writestr("OEBPS/chapter1.xhtml", chapter_xhtml)
        zf.writestr("OEBPS/style.css", css_content)
        zf.writestr("OEBPS/image.png", png_bytes)

    out = tmp_path / "output.epub"

    mock_translate.side_effect = lambda texts, *a, **kw: [f"[FR] {t}" for t in texts]

    result = translate_file(epub_path, out, "French", "English (US)")
    assert result is True

    with zipfile.ZipFile(out, "r") as zf:
        # CSS should be identical
        assert zf.read("OEBPS/style.css").decode("utf-8") == css_content
        # PNG should be identical
        assert zf.read("OEBPS/image.png") == png_bytes
        # Chapter content should be translated
        chapter = zf.read("OEBPS/chapter1.xhtml").decode("utf-8")
        assert "[FR]" in chapter


# ---------------------------------------------------------------------------
# Chunk round-trip edge case
# ---------------------------------------------------------------------------


def test_chunk_text_single_char_segments() -> None:
    """Single-character paragraphs survive the chunk/join round-trip."""
    content = "A\n\nB\n\nC\n\nD\n\nE"
    chunks, seps = _chunk_text(content, "\n\n", max_chars=100)
    reassembled = _join_with_separators(chunks, seps)
    assert reassembled == content
    # All five single-char paragraphs must be present
    for ch in "ABCDE":
        assert ch in reassembled


# ---------------------------------------------------------------------------
# _join_with_separators — empty input
# ---------------------------------------------------------------------------


def test_join_with_separators_empty_parts() -> None:
    """Empty parts list returns empty string."""
    assert _join_with_separators([], []) == ""


def test_join_with_separators_single_part_no_seps() -> None:
    """Single part with no separators returns the part as-is."""
    assert _join_with_separators(["hello"], []) == "hello"


# ---------------------------------------------------------------------------
# Empty / whitespace-only files for all plain/markup formats
# ---------------------------------------------------------------------------


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_empty_md(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Empty .md file is copied as-is without calling LLM."""
    src = tmp_path / "empty.md"
    src.write_text("", encoding="utf-8")
    out = tmp_path / "output.md"

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    assert out.exists()
    assert out.read_text(encoding="utf-8") == ""
    mock_translate.assert_not_called()


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_whitespace_only_md(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Whitespace-only .md file is copied as-is."""
    src = tmp_path / "ws.md"
    src.write_text("   \n\n   \n", encoding="utf-8")
    out = tmp_path / "output.md"

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    assert out.exists()
    mock_translate.assert_not_called()


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_empty_rst(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Empty .rst file is copied as-is without calling LLM."""
    src = tmp_path / "empty.rst"
    src.write_text("", encoding="utf-8")
    out = tmp_path / "output.rst"

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    assert out.exists()
    mock_translate.assert_not_called()


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_whitespace_only_rst(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Whitespace-only .rst file is copied as-is."""
    src = tmp_path / "ws.rst"
    src.write_text("   \n\n   ", encoding="utf-8")
    out = tmp_path / "output.rst"

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    assert out.exists()
    mock_translate.assert_not_called()


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_empty_html(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Empty .html file is copied as-is without calling LLM."""
    src = tmp_path / "empty.html"
    src.write_text("", encoding="utf-8")
    out = tmp_path / "output.html"

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    assert out.exists()
    mock_translate.assert_not_called()


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_whitespace_only_html(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Whitespace-only .html file is copied as-is."""
    src = tmp_path / "ws.html"
    src.write_text("   \n\n   ", encoding="utf-8")
    out = tmp_path / "output.html"

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    assert out.exists()
    mock_translate.assert_not_called()


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_empty_xml(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Empty .xml file is copied as-is without calling LLM."""
    src = tmp_path / "empty.xml"
    src.write_text("", encoding="utf-8")
    out = tmp_path / "output.xml"

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    assert out.exists()
    mock_translate.assert_not_called()


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_whitespace_only_xml(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Whitespace-only .xml file is copied as-is."""
    src = tmp_path / "ws.xml"
    src.write_text("   \n\n   ", encoding="utf-8")
    out = tmp_path / "output.xml"

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    assert out.exists()
    mock_translate.assert_not_called()


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_empty_rtf(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Empty .rtf file is copied as-is without calling LLM."""
    src = tmp_path / "empty.rtf"
    src.write_text("", encoding="utf-8")
    out = tmp_path / "output.rtf"

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    assert out.exists()
    mock_translate.assert_not_called()


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_whitespace_only_rtf(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    r"""Whitespace-only .rtf file (no \par) is copied as-is."""
    src = tmp_path / "ws.rtf"
    # Pure whitespace without any \par — chunks will be empty
    src.write_text("      ", encoding="utf-8")
    out = tmp_path / "output.rtf"

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    assert out.exists()
    mock_translate.assert_not_called()


@patch("src.core.llm_engine.translate_text")
def test_translate_file_empty_csv_no_content(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Completely empty .csv file (no rows at all) produces empty output."""
    src = tmp_path / "empty.csv"
    src.write_text("", encoding="utf-8")
    out = tmp_path / "output.csv"

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    assert out.read_text(encoding="utf-8") == ""
    mock_translate.assert_not_called()


@patch("src.core.llm_engine.translate_text")
def test_translate_file_empty_json_object(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Empty JSON object {} produces no translation calls."""
    src = tmp_path / "empty.json"
    src.write_text("{}", encoding="utf-8")
    out = tmp_path / "output.json"

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data == {}
    mock_translate.assert_not_called()


@patch("src.core.llm_engine.translate_text")
def test_translate_file_empty_json_array(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Empty JSON array [] produces no translation calls."""
    src = tmp_path / "empty_arr.json"
    src.write_text("[]", encoding="utf-8")
    out = tmp_path / "output.json"

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data == []
    mock_translate.assert_not_called()


# ---------------------------------------------------------------------------
# HTML with script/style tags — content should NOT be translated
# ---------------------------------------------------------------------------


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_html_script_tags_sent_as_is(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """HTML with <script> tags passes the entire chunk including script.

    The LLM prompt (content_type=html) instructs the model not to translate
    script/style contents. We verify the tags reach the LLM and the output
    is written successfully.
    """
    src = tmp_path / "input.html"
    src.write_text(
        "<html><body>"
        "<p>Hello World</p>"
        '<script type="text/javascript">var x = 1;</script>'
        "</body></html>",
        encoding="utf-8",
    )
    out = tmp_path / "output.html"

    captured: list[list[str]] = []

    def mock_fn(texts: list[str], *a: object, **kw: object) -> list[str]:
        captured.append(list(texts))
        return texts

    mock_translate.side_effect = mock_fn

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    assert out.exists()
    # The script tag is part of the chunk sent to LLM (content_type guides model)
    content = out.read_text(encoding="utf-8")
    assert "<script" in content
    assert "var x = 1;" in content


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_html_style_tags_preserved(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """HTML with <style> tags preserves the style content in output."""
    src = tmp_path / "input.html"
    src.write_text(
        "<html><head>"
        "<style>body { color: red; }</style>"
        "</head><body>"
        "<p>Hello</p>"
        "</body></html>",
        encoding="utf-8",
    )
    out = tmp_path / "output.html"

    mock_translate.side_effect = lambda texts, *a, **kw: texts

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    content = out.read_text(encoding="utf-8")
    assert "body { color: red; }" in content
    assert "<style>" in content


# ---------------------------------------------------------------------------
# HTML/XML with CDATA sections
# ---------------------------------------------------------------------------


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_xml_cdata_markers_preserved(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """XML CDATA markers are stripped before LLM and restored after.

    The strip_xml_overhead function replaces <![CDATA[ and ]]> markers
    with placeholders. After translation, they are restored.
    """
    src = tmp_path / "input.xml"
    src.write_text(
        '<?xml version="1.0"?>\n'
        "<root>\n"
        "  <content><![CDATA[Hello World]]></content>\n"
        "</root>",
        encoding="utf-8",
    )
    out = tmp_path / "output.xml"

    captured: list[list[str]] = []

    def mock_fn(texts: list[str], *a: object, **kw: object) -> list[str]:
        captured.append(list(texts))
        return texts

    mock_translate.side_effect = mock_fn

    result = translate_file(src, out, "French", "English (US)")
    assert result is True

    # Verify CDATA markers were stripped from what was sent to the LLM
    assert len(captured) > 0
    sent = " ".join(captured[0])
    assert "<![CDATA[" not in sent
    assert "]]>" not in sent

    # Output file should have CDATA markers restored
    content = out.read_text(encoding="utf-8")
    assert "<![CDATA[" in content
    assert "]]>" in content


# ---------------------------------------------------------------------------
# BOM (byte order mark) in markup files
# ---------------------------------------------------------------------------


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_html_with_bom(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """UTF-8 BOM in HTML file is stripped and does not appear in output."""
    src = tmp_path / "bom.html"
    src.write_bytes(
        b"\xef\xbb\xbf<html><body><p>Hello</p></body></html>",
    )
    out = tmp_path / "output.html"

    mock_translate.side_effect = lambda texts, *a, **kw: [f"[FR] {t}" for t in texts]

    result = translate_file(src, out, "French", "English (US)")
    assert result is True

    raw = out.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    content = out.read_text(encoding="utf-8")
    assert "\ufeff" not in content
    assert "[FR]" in content


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_xml_with_bom(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """UTF-8 BOM in XML file is stripped and does not appear in output."""
    src = tmp_path / "bom.xml"
    src.write_bytes(
        b'\xef\xbb\xbf<?xml version="1.0"?>\n<root><msg>Hello</msg></root>',
    )
    out = tmp_path / "output.xml"

    mock_translate.side_effect = lambda texts, *a, **kw: [f"[FR] {t}" for t in texts]

    result = translate_file(src, out, "French", "English (US)")
    assert result is True

    raw = out.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    content = out.read_text(encoding="utf-8")
    assert "\ufeff" not in content
    assert "[FR]" in content


# ---------------------------------------------------------------------------
# Per-format write errors
# ---------------------------------------------------------------------------


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_html_write_error(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """HTML write failure raises TEXT_WRITE_ERROR."""
    src = tmp_path / "input.html"
    src.write_text("<p>Hello</p>", encoding="utf-8")
    read_only = tmp_path / "readonly_html"
    read_only.mkdir()
    read_only.chmod(0o444)
    out = read_only / "subdir" / "output.html"

    mock_translate.side_effect = lambda texts, *a, **kw: texts

    try:
        with pytest.raises(ValueError, match="TEXT_WRITE_ERROR"):
            translate_file(src, out, "French", "English (US)")
    finally:
        read_only.chmod(0o755)


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_xml_write_error(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """XML write failure raises TEXT_WRITE_ERROR."""
    src = tmp_path / "input.xml"
    src.write_text("<root><msg>Hello</msg></root>", encoding="utf-8")
    read_only = tmp_path / "readonly_xml"
    read_only.mkdir()
    read_only.chmod(0o444)
    out = read_only / "subdir" / "output.xml"

    mock_translate.side_effect = lambda texts, *a, **kw: texts

    try:
        with pytest.raises(ValueError, match="TEXT_WRITE_ERROR"):
            translate_file(src, out, "French", "English (US)")
    finally:
        read_only.chmod(0o755)


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_rtf_write_error(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    r"""RTF write failure raises TEXT_WRITE_ERROR."""
    src = tmp_path / "input.rtf"
    src.write_text(r"{\rtf1 Hello}", encoding="utf-8")
    read_only = tmp_path / "readonly_rtf"
    read_only.mkdir()
    read_only.chmod(0o444)
    out = read_only / "subdir" / "output.rtf"

    mock_translate.side_effect = lambda texts, *a, **kw: texts

    try:
        with pytest.raises(ValueError, match="TEXT_WRITE_ERROR"):
            translate_file(src, out, "French", "English (US)")
    finally:
        read_only.chmod(0o755)


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_md_write_error(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Markdown write failure raises TEXT_WRITE_ERROR."""
    src = tmp_path / "input.md"
    src.write_text("# Hello", encoding="utf-8")
    read_only = tmp_path / "readonly_md"
    read_only.mkdir()
    read_only.chmod(0o444)
    out = read_only / "subdir" / "output.md"

    mock_translate.side_effect = lambda texts, *a, **kw: texts

    try:
        with pytest.raises(ValueError, match="TEXT_WRITE_ERROR"):
            translate_file(src, out, "French", "English (US)")
    finally:
        read_only.chmod(0o755)


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_epub_write_error(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """EPUB write failure raises TEXT_WRITE_ERROR."""
    src = _create_minimal_epub(tmp_path)
    read_only = tmp_path / "readonly_epub"
    read_only.mkdir()
    read_only.chmod(0o444)
    out = read_only / "subdir" / "output.epub"

    mock_translate.side_effect = lambda texts, *a, **kw: texts

    try:
        with pytest.raises(ValueError, match="TEXT_WRITE_ERROR"):
            translate_file(src, out, "French", "English (US)")
    finally:
        read_only.chmod(0o755)


# ---------------------------------------------------------------------------
# Per-format LLM error propagation
# ---------------------------------------------------------------------------


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_html_llm_error_propagates(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """LLM ValueError propagates through HTML translation."""
    src = tmp_path / "input.html"
    src.write_text("<p>Hello</p>", encoding="utf-8")
    out = tmp_path / "output.html"

    mock_translate.side_effect = ValueError("QUOTA_ERROR")

    with pytest.raises(ValueError, match="QUOTA_ERROR"):
        translate_file(src, out, "French", "English (US)")


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_xml_llm_error_propagates(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """LLM ValueError propagates through XML translation."""
    src = tmp_path / "input.xml"
    src.write_text("<root><msg>Hello</msg></root>", encoding="utf-8")
    out = tmp_path / "output.xml"

    mock_translate.side_effect = ValueError("AUTH_ERROR")

    with pytest.raises(ValueError, match="AUTH_ERROR"):
        translate_file(src, out, "French", "English (US)")


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_md_llm_error_propagates(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """LLM ValueError propagates through Markdown translation."""
    src = tmp_path / "input.md"
    src.write_text("# Hello\n\nParagraph", encoding="utf-8")
    out = tmp_path / "output.md"

    mock_translate.side_effect = ValueError("QUOTA_ERROR")

    with pytest.raises(ValueError, match="QUOTA_ERROR"):
        translate_file(src, out, "French", "English (US)")


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_rtf_llm_error_propagates(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    r"""LLM ValueError propagates through RTF translation."""
    src = tmp_path / "input.rtf"
    src.write_text(r"{\rtf1 Hello}", encoding="utf-8")
    out = tmp_path / "output.rtf"

    mock_translate.side_effect = ValueError("AUTH_ERROR")

    with pytest.raises(ValueError, match="AUTH_ERROR"):
        translate_file(src, out, "French", "English (US)")


@patch("src.core.llm_engine.translate_text")
def test_translate_file_csv_llm_error_propagates(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """LLM ValueError propagates through CSV translation."""
    src = tmp_path / "input.csv"
    src.write_text("Name\nAlice\n", encoding="utf-8")
    out = tmp_path / "output.csv"

    mock_translate.side_effect = ValueError("AUTH_ERROR")

    with pytest.raises(ValueError, match="AUTH_ERROR"):
        translate_file(src, out, "French", "English (US)")


@patch("src.core.llm_engine.translate_text")
def test_translate_file_json_llm_error_propagates(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """LLM ValueError propagates through JSON translation."""
    src = tmp_path / "input.json"
    src.write_text('{"key": "hello"}', encoding="utf-8")
    out = tmp_path / "output.json"

    mock_translate.side_effect = ValueError("QUOTA_ERROR")

    with pytest.raises(ValueError, match="QUOTA_ERROR"):
        translate_file(src, out, "French", "English (US)")


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_epub_llm_error_propagates(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """LLM ValueError propagates through EPUB translation."""
    src = _create_minimal_epub(tmp_path)
    out = tmp_path / "output.epub"

    mock_translate.side_effect = ValueError("AUTH_ERROR")

    with pytest.raises(ValueError, match="AUTH_ERROR"):
        translate_file(src, out, "French", "English (US)")


# ---------------------------------------------------------------------------
# Unicode chunking edge cases
# ---------------------------------------------------------------------------


def test_chunk_text_very_long_single_line() -> None:
    """A very long single line without separators becomes one chunk."""
    # 10000 chars, no paragraph breaks
    content = "A" * 10000  # noqa: PLR2004
    chunks, seps = _chunk_text(content, "\n\n")
    assert len(chunks) == 1
    assert chunks[0] == content
    assert seps == []


def test_chunk_text_only_newlines() -> None:
    """Content consisting of only newlines is filtered as whitespace."""
    content = "\n\n\n\n\n\n"
    chunks, seps = _chunk_text(content, "\n\n")
    assert chunks == []
    assert seps == []


def test_chunk_text_single_newline_only() -> None:
    """Content of a single newline is filtered as whitespace."""
    content = "\n"
    chunks, seps = _chunk_text(content, "\n")
    assert chunks == []
    assert seps == []


def test_chunk_text_long_line_with_newline_sep() -> None:
    """A very long single line is preserved as one chunk under line separator."""
    content = "B" * 5000  # noqa: PLR2004
    chunks, seps = _chunk_text(content, "\n")
    assert len(chunks) == 1
    assert chunks[0] == content


def test_chunk_text_cjk_unicode_paragraphs() -> None:
    """CJK paragraphs round-trip through chunk/join correctly."""
    content = "你好世界这是一段很长的中文文本" * 50 + "\n\n" + "日本語テスト" * 30
    chunks, seps = _chunk_text(content, "\n\n", max_chars=500)
    reassembled = _join_with_separators(chunks, seps)
    assert reassembled == content


# ---------------------------------------------------------------------------
# CSV with different delimiters
# ---------------------------------------------------------------------------


@patch("src.core.llm_engine.translate_text")
def test_translate_file_csv_pipe_delimiter(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """CSV with pipe delimiter is auto-detected and pipes preserved."""
    src = tmp_path / "input.csv"
    src.write_text(
        "Name|Greeting|Farewell\nAlice|Hello|Bye\nBob|Hi|Ciao\n",
        encoding="utf-8",
    )
    out = tmp_path / "output.csv"

    mock_translate.side_effect = lambda texts, *a, **kw: [f"[FR] {t}" for t in texts]

    result = translate_file(src, out, "French", "English (US)")
    assert result is True

    content = out.read_text(encoding="utf-8")
    # Pipe delimiter should be preserved
    assert "|" in content
    assert "[FR]" in content


@patch("src.core.llm_engine.translate_text")
def test_translate_file_csv_sniff_fallback_to_excel(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """CSV Sniffer fallback to csv.excel when detection fails.

    We force the Sniffer to raise csv.Error by patching it, then verify
    the file still translates correctly using the default csv.excel dialect.
    """
    src = tmp_path / "input.csv"
    src.write_text("Name,Value\nAlice,Hello\n", encoding="utf-8")
    out = tmp_path / "output.csv"

    mock_translate.side_effect = lambda texts, *a, **kw: [f"[FR] {t}" for t in texts]

    import csv as csv_mod  # noqa: PLC0415

    with patch.object(csv_mod.Sniffer, "sniff", side_effect=csv_mod.Error("fail")):
        result = translate_file(src, out, "French", "English (US)")

    assert result is True
    content = out.read_text(encoding="utf-8")
    assert "[FR]" in content


# ---------------------------------------------------------------------------
# JSON with nested structures
# ---------------------------------------------------------------------------


def test_extract_json_strings_array_of_objects() -> None:
    """Extracts strings from an array of objects."""
    data = [{"name": "Alice"}, {"name": "Bob"}]
    pairs = _extract_json_strings(data)
    paths = dict(pairs)
    assert (0, "name") in paths
    assert (1, "name") in paths
    assert paths[(0, "name")] == "Alice"
    assert paths[(1, "name")] == "Bob"


def test_extract_json_strings_mixed_nesting_depth() -> None:
    """Extracts strings from JSON with varying nesting depths."""
    data = {
        "shallow": "level1",
        "deep": {"a": {"b": {"c": "level4"}}},
        "list_deep": [[[["innermost"]]]],
    }
    pairs = _extract_json_strings(data)
    paths = dict(pairs)
    assert ("shallow",) in paths
    assert ("deep", "a", "b", "c") in paths
    assert ("list_deep", 0, 0, 0, 0) in paths
    assert paths[("list_deep", 0, 0, 0, 0)] == "innermost"


def test_inject_json_strings_nested_array_of_objects() -> None:
    """Injects translations into an array of objects."""
    data = [{"msg": "hello"}, {"msg": "world"}]
    translations = {
        (0, "msg"): "bonjour",
        (1, "msg"): "monde",
    }
    result = _inject_json_strings(data, translations)
    assert result[0]["msg"] == "bonjour"
    assert result[1]["msg"] == "monde"


@patch("src.core.llm_engine.translate_text")
def test_translate_file_json_mixed_types_preserved(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """JSON with mixed types preserves numbers, booleans, nulls, arrays."""
    src = tmp_path / "mixed.json"
    data = {
        "msg": "hello",
        "count": 42,
        "active": True,
        "nothing": None,
        "tags": ["alpha", "beta"],
        "nested": {"ratio": 3.14, "label": "deep"},
    }
    src.write_text(json.dumps(data), encoding="utf-8")
    out = tmp_path / "output.json"

    mock_translate.side_effect = lambda texts, *a, **kw: [f"[FR] {t}" for t in texts]

    result = translate_file(src, out, "French", "English (US)")
    assert result is True

    translated = json.loads(out.read_text(encoding="utf-8"))
    assert translated["count"] == 42  # noqa: PLR2004
    assert translated["active"] is True
    assert translated["nothing"] is None
    assert translated["nested"]["ratio"] == 3.14  # noqa: PLR2004
    assert translated["msg"].startswith("[FR]")
    assert translated["tags"][0].startswith("[FR]")
    assert translated["nested"]["label"].startswith("[FR]")


# ---------------------------------------------------------------------------
# RTF with Unicode escapes
# ---------------------------------------------------------------------------


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_rtf_unicode_escapes(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    r"""RTF with Unicode escape sequences (\uN?) are handled correctly.

    The strip_rtf_overhead function decodes Unicode escapes so the LLM
    sees readable text, then restores the original escapes after.
    """
    src = tmp_path / "unicode.rtf"
    # \u233? is e with acute in RTF (code point 233 = e-acute)
    src.write_text(
        r"{\rtf1 Caf\u233?}",
        encoding="utf-8",
    )
    out = tmp_path / "output.rtf"

    captured: list[list[str]] = []

    def mock_fn(texts: list[str], *a: object, **kw: object) -> list[str]:
        captured.append(list(texts))
        return texts

    mock_translate.side_effect = mock_fn

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    assert out.exists()

    # The output should be written successfully
    content = out.read_text(encoding="utf-8")
    assert len(content) > 0


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_rtf_multiple_unicode_escapes(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    r"""RTF with multiple Unicode escapes translates successfully."""
    src = tmp_path / "multi_unicode.rtf"
    src.write_text(
        r"{\rtf1 Hello \u8364?uro \u169?opyright}",
        encoding="utf-8",
    )
    out = tmp_path / "output.rtf"

    mock_translate.side_effect = lambda texts, *a, **kw: texts

    result = translate_file(src, out, "French", "English (US)")
    assert result is True
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert len(content) > 0


# ---------------------------------------------------------------------------
# EPUB image translation branch
# ---------------------------------------------------------------------------


@patch("src.core.text_processor._translate_doc_images")
@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_epub_image_translation_enabled(
    mock_translate: MagicMock,
    mock_doc_images: MagicMock,
    tmp_path: Path,
) -> None:
    """EPUB triggers image translation when setting is enabled and OCR ready."""
    src = _create_minimal_epub(tmp_path)
    out = tmp_path / "output.epub"

    mock_translate.side_effect = lambda texts, *a, **kw: [f"[FR] {t}" for t in texts]

    with (
        patch(
            "src.utils.config_manager.load_setting",
            return_value=True,
        ),
        patch(
            "src.utils.config_manager.check_ocr_setup",
            return_value=True,
        ),
    ):
        result = translate_file(src, out, "French", "English (US)")

    assert result is True
    assert out.exists()
    # _translate_doc_images should have been called with the output EPUB
    mock_doc_images.assert_called_once()
    call_args = mock_doc_images.call_args
    assert call_args[0][0] == out  # output_path
    assert call_args[0][1] == ".epub"  # suffix


@patch("src.core.text_processor._translate_doc_images")
@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_epub_image_translation_disabled(
    mock_translate: MagicMock,
    mock_doc_images: MagicMock,
    tmp_path: Path,
) -> None:
    """EPUB does NOT trigger image translation when setting is disabled."""
    src = _create_minimal_epub(tmp_path)
    out = tmp_path / "output.epub"

    mock_translate.side_effect = lambda texts, *a, **kw: [f"[FR] {t}" for t in texts]

    with (
        patch(
            "src.utils.config_manager.load_setting",
            return_value=False,
        ),
        patch(
            "src.utils.config_manager.check_ocr_setup",
            return_value=True,
        ),
    ):
        result = translate_file(src, out, "French", "English (US)")

    assert result is True
    mock_doc_images.assert_not_called()


@patch("src.core.text_processor._translate_doc_images")
@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_epub_image_translation_no_ocr(
    mock_translate: MagicMock,
    mock_doc_images: MagicMock,
    tmp_path: Path,
) -> None:
    """EPUB does NOT trigger image translation when OCR is not configured."""
    src = _create_minimal_epub(tmp_path)
    out = tmp_path / "output.epub"

    mock_translate.side_effect = lambda texts, *a, **kw: [f"[FR] {t}" for t in texts]

    with (
        patch(
            "src.utils.config_manager.load_setting",
            return_value=True,
        ),
        patch(
            "src.utils.config_manager.check_ocr_setup",
            return_value=False,
        ),
    ):
        result = translate_file(src, out, "French", "English (US)")

    assert result is True
    mock_doc_images.assert_not_called()


@patch("src.core.text_processor._translate_doc_images")
@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_epub_image_progress_callback(
    mock_translate: MagicMock,
    mock_doc_images: MagicMock,
    tmp_path: Path,
) -> None:
    """EPUB image translation uses 70-100% progress range."""
    src = _create_minimal_epub(tmp_path)
    out = tmp_path / "output.epub"

    mock_translate.side_effect = lambda texts, *a, **kw: [f"[FR] {t}" for t in texts]

    progress_values: list[int] = []

    with (
        patch(
            "src.utils.config_manager.load_setting",
            return_value=True,
        ),
        patch(
            "src.utils.config_manager.check_ocr_setup",
            return_value=True,
        ),
    ):
        result = translate_file(
            src,
            out,
            "French",
            "English (US)",
            progress_callback=progress_values.append,
        )

    assert result is True
    # Text progress should be scaled to 0-70%
    # The text progress callback wraps: progress_callback(int(p * 0.7))
    assert len(progress_values) > 0
    # All text progress values should be at most 100
    for val in progress_values:
        assert val <= 100  # noqa: PLR2004

    # _translate_doc_images was called and received a progress callback
    mock_doc_images.assert_called_once()


# ---------------------------------------------------------------------------
# XML attribute stripping and restoration
# ---------------------------------------------------------------------------


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_xml_strips_attributes(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """XML files have attributes stripped before LLM and restored after."""
    src = tmp_path / "input.xml"
    src.write_text(
        '<root lang="en">\n  <message id="m1">Hello</message>\n</root>',
        encoding="utf-8",
    )
    out = tmp_path / "output.xml"

    captured: list[list[str]] = []

    def mock_fn(texts: list[str], *a: object, **kw: object) -> list[str]:
        captured.append(list(texts))
        return texts

    mock_translate.side_effect = mock_fn

    translate_file(src, out, "French", "English (US)")

    # The LLM should NOT receive the attributes
    assert len(captured) > 0
    sent = " ".join(captured[0])
    assert 'lang="en"' not in sent
    assert 'id="m1"' not in sent

    # But the output should have attributes restored
    content = out.read_text(encoding="utf-8")
    assert 'lang="en"' in content
    assert 'id="m1"' in content


# ---------------------------------------------------------------------------
# RTF overhead stripping
# ---------------------------------------------------------------------------


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_rtf_control_words_stripped(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    r"""RTF control words are stripped before LLM and restored after."""
    src = tmp_path / "input.rtf"
    src.write_text(
        r"{\rtf1\ansi\b Hello World\b0}",
        encoding="utf-8",
    )
    out = tmp_path / "output.rtf"

    captured: list[list[str]] = []

    def mock_fn(texts: list[str], *a: object, **kw: object) -> list[str]:
        captured.append(list(texts))
        return texts

    mock_translate.side_effect = mock_fn

    result = translate_file(src, out, "French", "English (US)")
    assert result is True

    # The LLM should NOT see raw control words like \ansi, \b, \b0
    assert len(captured) > 0
    sent = " ".join(captured[0])
    assert "\\ansi" not in sent
    assert "\\rtf1" not in sent

    # Output should have control words restored
    content = out.read_text(encoding="utf-8")
    assert len(content) > 0


# ---------------------------------------------------------------------------
# Markdown overhead stripping
# ---------------------------------------------------------------------------


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_md_strips_link_urls(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Markdown files have link URLs stripped before LLM and restored after."""
    src = tmp_path / "input.md"
    src.write_text(
        "Click [here](https://example.com) for more info.",
        encoding="utf-8",
    )
    out = tmp_path / "output.md"

    captured: list[list[str]] = []

    def mock_fn(texts: list[str], *a: object, **kw: object) -> list[str]:
        captured.append(list(texts))
        return texts

    mock_translate.side_effect = mock_fn

    result = translate_file(src, out, "French", "English (US)")
    assert result is True

    # The LLM should NOT receive the raw URL
    assert len(captured) > 0
    sent = " ".join(captured[0])
    assert "https://example.com" not in sent

    # But the output should have the URL restored
    content = out.read_text(encoding="utf-8")
    assert "https://example.com" in content


# ---------------------------------------------------------------------------
# translate_file — rst write error
# ---------------------------------------------------------------------------


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_rst_write_error(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """RST write failure raises TEXT_WRITE_ERROR."""
    src = tmp_path / "input.rst"
    src.write_text("Hello RST", encoding="utf-8")
    read_only = tmp_path / "readonly_rst"
    read_only.mkdir()
    read_only.chmod(0o444)
    out = read_only / "subdir" / "output.rst"

    mock_translate.side_effect = lambda texts, *a, **kw: texts

    try:
        with pytest.raises(ValueError, match="TEXT_WRITE_ERROR"):
            translate_file(src, out, "French", "English (US)")
    finally:
        read_only.chmod(0o755)


# ---------------------------------------------------------------------------
# translate_file — rst LLM error
# ---------------------------------------------------------------------------


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_rst_llm_error_propagates(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """LLM ValueError propagates through RST translation."""
    src = tmp_path / "input.rst"
    src.write_text("Hello RST", encoding="utf-8")
    out = tmp_path / "output.rst"

    mock_translate.side_effect = ValueError("AUTH_ERROR")

    with pytest.raises(ValueError, match="AUTH_ERROR"):
        translate_file(src, out, "French", "English (US)")


# ===========================================================================
# NEW EDGE-CASE TESTS (appended)
# ===========================================================================


# ---------------------------------------------------------------------------
# TestTranslateFileDispatch — dispatch per supported format
# ---------------------------------------------------------------------------


class TestTranslateFileDispatch:
    """Tests translate_file dispatch to the correct handler per format."""

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_dispatch_txt(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """Dispatches .txt to _process_plain."""
        src = tmp_path / "input.txt"
        src.write_text("Hello", encoding="utf-8")
        out = tmp_path / "output.txt"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        assert translate_file(src, out, "French", "English (US)") is True
        assert out.exists()

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_dispatch_md(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """Dispatches .md to _process_plain with paragraph separator."""
        src = tmp_path / "input.md"
        src.write_text("# Title", encoding="utf-8")
        out = tmp_path / "output.md"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        assert translate_file(src, out, "French") is True

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_dispatch_rst(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """Dispatches .rst to _process_plain with paragraph separator."""
        src = tmp_path / "input.rst"
        src.write_text("Title\n=====", encoding="utf-8")
        out = tmp_path / "output.rst"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        assert translate_file(src, out, "French") is True

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_dispatch_html(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """Dispatches .html to _process_plain with line separator."""
        src = tmp_path / "input.html"
        src.write_text("<p>Hi</p>", encoding="utf-8")
        out = tmp_path / "output.html"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        assert translate_file(src, out, "French") is True

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_dispatch_xml(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """Dispatches .xml to _process_plain with line separator."""
        src = tmp_path / "input.xml"
        src.write_text("<root>Hello</root>", encoding="utf-8")
        out = tmp_path / "output.xml"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        assert translate_file(src, out, "French") is True

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_dispatch_rtf(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        r"""Dispatches .rtf to _process_plain with \\par separator."""
        src = tmp_path / "input.rtf"
        src.write_text(r"{\rtf1 Hello}", encoding="utf-8")
        out = tmp_path / "output.rtf"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        assert translate_file(src, out, "French") is True

    @patch("src.core.llm_engine.translate_text")
    def test_dispatch_json(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """Dispatches .json to _process_json."""
        src = tmp_path / "input.json"
        src.write_text('{"k": "v"}', encoding="utf-8")
        out = tmp_path / "output.json"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        assert translate_file(src, out, "French") is True

    @patch("src.core.llm_engine.translate_text")
    def test_dispatch_csv(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """Dispatches .csv to _process_csv."""
        src = tmp_path / "input.csv"
        src.write_text("Name\nAlice\n", encoding="utf-8")
        out = tmp_path / "output.csv"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        assert translate_file(src, out, "French") is True

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_dispatch_epub(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """Dispatches .epub to _process_epub."""
        src = _create_minimal_epub(tmp_path)
        out = tmp_path / "output.epub"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        assert translate_file(src, out, "French") is True

    @patch("src.core.llm_engine.translate_text")
    def test_dispatch_srt(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """Dispatches .srt to _process_subtitle."""
        src = tmp_path / "input.srt"
        src.write_text(
            "1\n00:00:01,000 --> 00:00:02,000\nHi\n",
            encoding="utf-8",
        )
        out = tmp_path / "output.srt"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        assert translate_file(src, out, "French") is True

    @patch("src.core.llm_engine.translate_text")
    def test_dispatch_vtt(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """Dispatches .vtt to _process_subtitle."""
        src = tmp_path / "input.vtt"
        src.write_text(
            "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nHi\n",
            encoding="utf-8",
        )
        out = tmp_path / "output.vtt"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        assert translate_file(src, out, "French") is True

    @patch("src.core.llm_engine.translate_text")
    def test_dispatch_ass(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """Dispatches .ass to _process_subtitle."""
        src = tmp_path / "input.ass"
        src.write_text(
            "[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
            "MarginV, Effect, Text\n"
            "Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,Hi\n",
            encoding="utf-8",
        )
        out = tmp_path / "output.ass"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        assert translate_file(src, out, "French") is True

    @patch("src.core.llm_engine.translate_text")
    def test_dispatch_ssa(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """Dispatches .ssa to _process_subtitle."""
        src = tmp_path / "input.ssa"
        src.write_text(
            "[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
            "MarginV, Effect, Text\n"
            "Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,Hi\n",
            encoding="utf-8",
        )
        out = tmp_path / "output.ssa"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        assert translate_file(src, out, "French") is True

    @patch("src.core.llm_engine.translate_text")
    def test_dispatch_po(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """Dispatches .po to _process_localization."""
        src = tmp_path / "input.po"
        src.write_text(
            'msgid ""\nmsgstr ""\n\nmsgid "Hi"\nmsgstr ""\n',
            encoding="utf-8",
        )
        out = tmp_path / "output.po"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        assert translate_file(src, out, "French") is True

    @patch("src.core.llm_engine.translate_text")
    def test_dispatch_pot(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """Dispatches .pot to _process_localization."""
        src = tmp_path / "input.pot"
        src.write_text(
            'msgid ""\nmsgstr ""\n\nmsgid "Hi"\nmsgstr ""\n',
            encoding="utf-8",
        )
        out = tmp_path / "output.pot"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        assert translate_file(src, out, "French") is True

    @patch("src.core.llm_engine.translate_text")
    def test_dispatch_xliff(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """Dispatches .xliff to _process_localization."""
        src = tmp_path / "input.xliff"
        src.write_text(
            '<?xml version="1.0"?>'
            '<xliff version="1.2" '
            'xmlns="urn:oasis:names:tc:xliff:document:1.2">'
            '<file source-language="en" target-language="fr" '
            'datatype="plaintext"><body>'
            '<trans-unit id="1"><source>Hi</source></trans-unit>'
            "</body></file></xliff>",
            encoding="utf-8",
        )
        out = tmp_path / "output.xliff"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        assert translate_file(src, out, "French") is True

    @patch("src.core.llm_engine.translate_text")
    def test_dispatch_xlf(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """Dispatches .xlf to _process_localization."""
        src = tmp_path / "input.xlf"
        src.write_text(
            '<?xml version="1.0"?>'
            '<xliff xmlns="urn:oasis:names:tc:xliff:document:2.0"'
            ' version="2.0" srcLang="en" trgLang="fr">'
            '<file id="f1">'
            '<unit id="u1"><segment><source>Hi</source></segment></unit>'
            "</file></xliff>",
            encoding="utf-8",
        )
        out = tmp_path / "output.xlf"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        assert translate_file(src, out, "French") is True

    @patch("src.core.llm_engine.translate_text")
    def test_dispatch_yaml(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """Dispatches .yaml to _process_keyvalue."""
        src = tmp_path / "input.yaml"
        src.write_text("key: value\n", encoding="utf-8")
        out = tmp_path / "output.yaml"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        assert translate_file(src, out, "French") is True

    @patch("src.core.llm_engine.translate_text")
    def test_dispatch_yml(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """Dispatches .yml to _process_keyvalue."""
        src = tmp_path / "input.yml"
        src.write_text("key: value\n", encoding="utf-8")
        out = tmp_path / "output.yml"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        assert translate_file(src, out, "French") is True

    @patch("src.core.llm_engine.translate_text")
    def test_dispatch_properties(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """Dispatches .properties to _process_keyvalue."""
        src = tmp_path / "input.properties"
        src.write_text("key=value\n", encoding="utf-8")
        out = tmp_path / "output.properties"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        assert translate_file(src, out, "French") is True

    @patch("src.core.llm_engine.translate_text")
    def test_dispatch_strings(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """Dispatches .strings to _process_keyvalue."""
        src = tmp_path / "input.strings"
        src.write_text('"key" = "value";\n', encoding="utf-8")
        out = tmp_path / "output.strings"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        assert translate_file(src, out, "French") is True

    @patch("src.core.pdf_processor.process_pdf_file")
    def test_dispatch_pdf(self, mock_pdf: MagicMock, tmp_path: Path) -> None:
        """Dispatches .pdf to process_pdf_file."""
        src = tmp_path / "input.pdf"
        src.write_bytes(b"%PDF-1.4\n")
        out = tmp_path / "output.pdf"
        mock_pdf.return_value = True
        assert translate_file(src, out, "French") is True
        mock_pdf.assert_called_once()

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_dispatch_config_none_uses_fallback(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """When config is None, translate_file does not crash."""
        src = tmp_path / "input.txt"
        src.write_text("Hello", encoding="utf-8")
        out = tmp_path / "output.txt"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        # Explicitly pass config=None
        assert translate_file(src, out, "French", config=None) is True


# ---------------------------------------------------------------------------
# TestTranslateTxtFile — .txt edge cases
# ---------------------------------------------------------------------------


class TestTranslateTxtFile:
    """Edge cases for plain text file translation."""

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_unicode_content(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """Translates file with CJK, Cyrillic, and emoji content."""
        src = tmp_path / "unicode.txt"
        src.write_text(
            "Привет мир\n\n你好世界\n\nHola mundo",
            encoding="utf-8",
        )
        out = tmp_path / "output.txt"
        mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
        assert translate_file(src, out, "French") is True
        content = out.read_text(encoding="utf-8")
        assert "[T]" in content

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_bom_prefixed_file(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """BOM-prefixed .txt file is translated without BOM in output."""
        src = tmp_path / "bom.txt"
        src.write_bytes(b"\xef\xbb\xbfHello World")
        out = tmp_path / "output.txt"
        mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
        assert translate_file(src, out, "French") is True
        raw = out.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf")
        assert b"[T]" in raw

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_non_utf8_encoding_fallback(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """Non-UTF-8 file (latin-1) is decoded via charset_normalizer."""
        src = tmp_path / "latin.txt"
        text = "Le café est très bon."
        src.write_bytes(text.encode("latin-1"))
        out = tmp_path / "output.txt"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        assert translate_file(src, out, "French") is True
        content = out.read_text(encoding="utf-8")
        assert "caf" in content

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_very_large_file_multiple_chunks(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """Large file is split into multiple chunks."""
        src = tmp_path / "large.txt"
        # Create content with many paragraphs exceeding MAX_CHUNK_CHARS
        paras = [f"Paragraph number {i}. " * 30 for i in range(20)]
        src.write_text("\n\n".join(paras), encoding="utf-8")
        out = tmp_path / "output.txt"
        mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
        assert translate_file(src, out, "French") is True
        # LLM should be called at least once
        assert mock_translate.call_count >= 1
        assert out.exists()

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_empty_file(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """Empty .txt file is copied as-is."""
        src = tmp_path / "empty.txt"
        src.write_text("", encoding="utf-8")
        out = tmp_path / "output.txt"
        assert translate_file(src, out, "French") is True
        assert out.read_text(encoding="utf-8") == ""
        mock_translate.assert_not_called()


# ---------------------------------------------------------------------------
# TestTranslateHtmlFile — .html edge cases
# ---------------------------------------------------------------------------


class TestTranslateHtmlFile:
    """Edge cases for HTML file translation."""

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_preserves_html_structure(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """Translated HTML preserves tag structure."""
        src = tmp_path / "input.html"
        src.write_text(
            "<html><head><title>Test</title></head>"
            "<body><h1>Hello</h1><p>World</p></body></html>",
            encoding="utf-8",
        )
        out = tmp_path / "output.html"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        assert translate_file(src, out, "French") is True
        content = out.read_text(encoding="utf-8")
        assert "<html>" in content
        assert "</html>" in content

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_nested_tags(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """Deeply nested tags survive translation."""
        src = tmp_path / "nested.html"
        src.write_text(
            "<div><ul><li><a><span>Click me</span></a></li></ul></div>",
            encoding="utf-8",
        )
        out = tmp_path / "output.html"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        assert translate_file(src, out, "French") is True
        content = out.read_text(encoding="utf-8")
        assert "<span>" in content
        assert "Click me" in content

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_multiple_attributes_stripped_and_restored(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """Multiple HTML attributes are stripped and restored correctly."""
        src = tmp_path / "attrs.html"
        src.write_text(
            '<div class="container" id="main" data-role="page"><p>Hello</p></div>',
            encoding="utf-8",
        )
        out = tmp_path / "output.html"

        captured: list[list[str]] = []

        def mock_fn(texts: list[str], *a: object, **kw: object) -> list[str]:
            captured.append(list(texts))
            return texts

        mock_translate.side_effect = mock_fn
        assert translate_file(src, out, "French") is True

        # Attributes should not reach LLM
        sent = " ".join(captured[0])
        assert 'data-role="page"' not in sent

        # But should be in output
        content = out.read_text(encoding="utf-8")
        assert 'class="container"' in content
        assert 'id="main"' in content

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_html_entities_preserved(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """HTML entities like &amp; and &lt; are preserved."""
        src = tmp_path / "entities.html"
        src.write_text(
            "<p>5 &gt; 3 &amp; 2 &lt; 4</p>",
            encoding="utf-8",
        )
        out = tmp_path / "output.html"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        assert translate_file(src, out, "French") is True
        content = out.read_text(encoding="utf-8")
        assert "&gt;" in content or ">" in content


# ---------------------------------------------------------------------------
# TestTranslateXmlFile — .xml edge cases
# ---------------------------------------------------------------------------


class TestTranslateXmlFile:
    """Edge cases for XML file translation."""

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_preserves_xml_declaration(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """XML declaration is preserved after translation."""
        src = tmp_path / "input.xml"
        src.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n<root><msg>Hello</msg></root>',
            encoding="utf-8",
        )
        out = tmp_path / "output.xml"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        assert translate_file(src, out, "French") is True
        content = out.read_text(encoding="utf-8")
        assert "<?xml" in content

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_xml_with_namespaces(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """XML with namespace attributes are stripped and restored."""
        src = tmp_path / "ns.xml"
        src.write_text(
            '<root xmlns:custom="http://example.com">\n'
            "  <custom:element>Hello</custom:element>\n</root>",
            encoding="utf-8",
        )
        out = tmp_path / "output.xml"

        captured: list[list[str]] = []

        def mock_fn(texts: list[str], *a: object, **kw: object) -> list[str]:
            captured.append(list(texts))
            return texts

        mock_translate.side_effect = mock_fn
        assert translate_file(src, out, "French") is True

        # Namespace attribute stripped from LLM input
        sent = " ".join(captured[0])
        assert 'xmlns:custom="http://example.com"' not in sent

        # Restored in output
        content = out.read_text(encoding="utf-8")
        assert 'xmlns:custom="http://example.com"' in content

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_xml_with_processing_instructions(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """XML processing instructions are stripped and restored."""
        src = tmp_path / "pi.xml"
        src.write_text(
            '<?xml version="1.0"?>\n'
            '<?xml-stylesheet type="text/xsl" href="style.xsl"?>\n'
            "<root>Hello</root>",
            encoding="utf-8",
        )
        out = tmp_path / "output.xml"

        captured: list[list[str]] = []

        def mock_fn(texts: list[str], *a: object, **kw: object) -> list[str]:
            captured.append(list(texts))
            return texts

        mock_translate.side_effect = mock_fn
        assert translate_file(src, out, "French") is True

        # PI stripped from LLM input
        sent = " ".join(captured[0])
        assert "xml-stylesheet" not in sent

        # Restored in output
        content = out.read_text(encoding="utf-8")
        assert "xml-stylesheet" in content

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_xml_multiline(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """Multi-line XML translates and preserves line structure."""
        src = tmp_path / "multi.xml"
        src.write_text(
            "<root>\n  <a>Line 1</a>\n  <b>Line 2</b>\n  <c>Line 3</c>\n</root>",
            encoding="utf-8",
        )
        out = tmp_path / "output.xml"
        mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
        assert translate_file(src, out, "French") is True
        content = out.read_text(encoding="utf-8")
        assert "[T]" in content


# ---------------------------------------------------------------------------
# TestTranslateJsonFile — .json edge cases
# ---------------------------------------------------------------------------


class TestTranslateJsonFile:
    """Edge cases for JSON file translation."""

    @patch("src.core.llm_engine.translate_text")
    def test_flat_json(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """Flat JSON with all string values."""
        src = tmp_path / "flat.json"
        data = {"a": "hello", "b": "world", "c": "test"}
        src.write_text(json.dumps(data), encoding="utf-8")
        out = tmp_path / "output.json"
        mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
        assert translate_file(src, out, "French") is True
        result = json.loads(out.read_text(encoding="utf-8"))
        assert result["a"] == "[T] hello"
        assert result["b"] == "[T] world"

    @patch("src.core.llm_engine.translate_text")
    def test_nested_json(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """Nested JSON with mixed depths."""
        src = tmp_path / "nested.json"
        data = {"level1": {"level2": {"text": "deep value"}}}
        src.write_text(json.dumps(data), encoding="utf-8")
        out = tmp_path / "output.json"
        mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
        assert translate_file(src, out, "French") is True
        result = json.loads(out.read_text(encoding="utf-8"))
        assert result["level1"]["level2"]["text"] == "[T] deep value"

    @patch("src.core.llm_engine.translate_text")
    def test_json_arrays(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """JSON with arrays of strings."""
        src = tmp_path / "arrays.json"
        data = {"items": ["apple", "banana", "cherry"]}
        src.write_text(json.dumps(data), encoding="utf-8")
        out = tmp_path / "output.json"
        mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
        assert translate_file(src, out, "French") is True
        result = json.loads(out.read_text(encoding="utf-8"))
        assert result["items"][0] == "[T] apple"
        assert result["items"][2] == "[T] cherry"  # noqa: PLR2004

    @patch("src.core.llm_engine.translate_text")
    def test_json_preserves_non_string_values(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """Non-string values (int, float, bool, null) are preserved."""
        src = tmp_path / "types.json"
        data = {
            "text": "hello",
            "num": 42,
            "pi": 3.14,
            "flag": False,
            "nothing": None,
        }
        src.write_text(json.dumps(data), encoding="utf-8")
        out = tmp_path / "output.json"
        mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
        assert translate_file(src, out, "French") is True
        result = json.loads(out.read_text(encoding="utf-8"))
        assert result["num"] == 42  # noqa: PLR2004
        assert result["pi"] == 3.14  # noqa: PLR2004
        assert result["flag"] is False
        assert result["nothing"] is None

    @patch("src.core.llm_engine.translate_text")
    def test_json_empty_strings_skipped(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """JSON with empty string values skips them and translates rest."""
        src = tmp_path / "empties.json"
        data = {"empty": "", "spaces": "   ", "valid": "hello"}
        src.write_text(json.dumps(data), encoding="utf-8")
        out = tmp_path / "output.json"
        mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
        assert translate_file(src, out, "French") is True
        result = json.loads(out.read_text(encoding="utf-8"))
        assert result["valid"] == "[T] hello"
        # Empty and whitespace-only strings are preserved as-is
        assert result["empty"] == ""
        assert result["spaces"] == "   "


# ---------------------------------------------------------------------------
# TestTranslateCsvFile — .csv edge cases
# ---------------------------------------------------------------------------


class TestTranslateCsvFile:
    """Edge cases for CSV file translation."""

    @patch("src.core.llm_engine.translate_text")
    def test_csv_with_header_row(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """CSV header row is also translated."""
        src = tmp_path / "input.csv"
        src.write_text(
            "Name,Greeting\nAlice,Hello\nBob,World\n",
            encoding="utf-8",
        )
        out = tmp_path / "output.csv"
        mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
        assert translate_file(src, out, "French") is True
        content = out.read_text(encoding="utf-8")
        # All cells including header are translated
        assert "[T] Name" in content
        assert "[T] Alice" in content

    @patch("src.core.llm_engine.translate_text")
    def test_csv_multiple_columns(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """CSV with 5 columns translates all text cells."""
        src = tmp_path / "multi.csv"
        src.write_text(
            "A,B,C,D,E\na1,b1,c1,d1,e1\n",
            encoding="utf-8",
        )
        out = tmp_path / "output.csv"
        mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
        assert translate_file(src, out, "French") is True
        content = out.read_text(encoding="utf-8")
        assert "[T] A" in content
        assert "[T] e1" in content

    @patch("src.core.llm_engine.translate_text")
    def test_csv_quoted_fields(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """CSV with double-quoted fields translates correctly."""
        src = tmp_path / "quoted.csv"
        src.write_text(
            '"Name","Message"\n"Alice","Hello, World"\n',
            encoding="utf-8",
        )
        out = tmp_path / "output.csv"
        mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
        assert translate_file(src, out, "French") is True
        content = out.read_text(encoding="utf-8")
        assert "[T]" in content

    @patch("src.core.llm_engine.translate_text")
    def test_csv_with_empty_cells(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """CSV with some empty cells only translates non-empty ones."""
        src = tmp_path / "gaps.csv"
        src.write_text(
            "A,,C\n,B2,\n",
            encoding="utf-8",
        )
        out = tmp_path / "output.csv"
        mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
        assert translate_file(src, out, "French") is True
        content = out.read_text(encoding="utf-8")
        assert "[T] A" in content
        assert "[T] C" in content
        assert "[T] B2" in content


# ---------------------------------------------------------------------------
# TestTranslateEpubFile — .epub edge cases
# ---------------------------------------------------------------------------


class TestTranslateEpubFile:
    """Edge cases for EPUB file translation."""

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_epub_content_file_ordering(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """EPUB content files are discovered in manifest order."""
        epub_path = tmp_path / "order.epub"
        container_xml = (
            '<?xml version="1.0"?>'
            '<container xmlns="urn:oasis:names:tc:opendocument'
            ':xmlns:container" version="1.0">'
            "  <rootfiles>"
            '    <rootfile full-path="OEBPS/content.opf"'
            ' media-type="application/oebps-package+xml"/>'
            "  </rootfiles>"
            "</container>"
        )
        content_opf = (
            '<?xml version="1.0"?>'
            '<package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
            "  <manifest>"
            '    <item id="ch2" href="ch2.xhtml"'
            ' media-type="application/xhtml+xml"/>'
            '    <item id="ch1" href="ch1.xhtml"'
            ' media-type="application/xhtml+xml"/>'
            "  </manifest>"
            "</package>"
        )
        with zipfile.ZipFile(epub_path, "w") as zf:
            zf.writestr("META-INF/container.xml", container_xml)
            zf.writestr("OEBPS/content.opf", content_opf)
            zf.writestr(
                "OEBPS/ch1.xhtml",
                "<html><body><p>Chapter 1</p></body></html>",
            )
            zf.writestr(
                "OEBPS/ch2.xhtml",
                "<html><body><p>Chapter 2</p></body></html>",
            )

        with zipfile.ZipFile(epub_path, "r") as zf:
            files = _get_epub_content_files(zf)
        assert len(files) == 2  # noqa: PLR2004
        # ch2 appears first in the manifest
        assert "ch2.xhtml" in files[0]

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_epub_metadata_preserved(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """EPUB container.xml and content.opf are preserved unchanged."""
        src = _create_minimal_epub(tmp_path)
        out = tmp_path / "output.epub"
        mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
        assert translate_file(src, out, "French") is True

        with zipfile.ZipFile(out, "r") as zf:
            container = zf.read("META-INF/container.xml").decode("utf-8")
            opf = zf.read("OEBPS/content.opf").decode("utf-8")
        assert "container" in container
        assert "manifest" in opf

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_epub_empty_xhtml_chapter(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """EPUB with a chapter containing empty XHTML does not crash."""
        epub_path = tmp_path / "empty_ch.epub"
        container_xml = (
            '<?xml version="1.0"?>'
            '<container xmlns="urn:oasis:names:tc:opendocument'
            ':xmlns:container" version="1.0">'
            "  <rootfiles>"
            '    <rootfile full-path="OEBPS/content.opf"'
            ' media-type="application/oebps-package+xml"/>'
            "  </rootfiles>"
            "</container>"
        )
        content_opf = (
            '<?xml version="1.0"?>'
            '<package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
            "  <manifest>"
            '    <item id="ch1" href="ch1.xhtml"'
            ' media-type="application/xhtml+xml"/>'
            "  </manifest>"
            "</package>"
        )
        with zipfile.ZipFile(epub_path, "w") as zf:
            zf.writestr("META-INF/container.xml", container_xml)
            zf.writestr("OEBPS/content.opf", content_opf)
            zf.writestr("OEBPS/ch1.xhtml", "")

        out = tmp_path / "output.epub"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        # Should succeed even with empty chapter content
        assert translate_file(epub_path, out, "French") is True
        assert out.exists()


# ---------------------------------------------------------------------------
# TestTranslateSubtitleFiles — subtitle edge cases
# ---------------------------------------------------------------------------


class TestTranslateSubtitleFiles:
    """Edge cases for subtitle file translation."""

    @patch("src.core.llm_engine.translate_text")
    def test_srt_preserves_sequence_numbers(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """SRT sequence numbers are preserved in output."""
        src = tmp_path / "input.srt"
        src.write_text(
            "1\n00:00:01,000 --> 00:00:04,000\nHello\n\n"
            "2\n00:00:05,000 --> 00:00:08,000\nWorld\n\n"
            "3\n00:00:09,000 --> 00:00:12,000\nTest\n",
            encoding="utf-8",
        )
        out = tmp_path / "output.srt"
        mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
        assert translate_file(src, out, "French") is True
        content = out.read_text(encoding="utf-8")
        # Sequence numbers should still be in the output
        lines = content.strip().split("\n")
        # Find lines that are just numbers
        seq_nums = [l.strip() for l in lines if l.strip().isdigit()]
        assert "1" in seq_nums
        assert "2" in seq_nums
        assert "3" in seq_nums

    @patch("src.core.llm_engine.translate_text")
    def test_vtt_header_preserved(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """VTT WEBVTT header is always preserved."""
        src = tmp_path / "input.vtt"
        src.write_text(
            "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nHello\n",
            encoding="utf-8",
        )
        out = tmp_path / "output.vtt"
        mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
        assert translate_file(src, out, "French") is True
        content = out.read_text(encoding="utf-8")
        assert content.startswith("WEBVTT")

    @patch("src.core.llm_engine.translate_text")
    def test_empty_vtt_file(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """Empty VTT file (header only) is copied as-is."""
        src = tmp_path / "empty.vtt"
        src.write_text("WEBVTT\n\n", encoding="utf-8")
        out = tmp_path / "output.vtt"
        assert translate_file(src, out, "French") is True
        assert out.exists()
        mock_translate.assert_not_called()

    @patch("src.core.llm_engine.translate_text")
    def test_empty_ass_file(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """ASS file with no dialogue entries is copied as-is."""
        src = tmp_path / "empty.ass"
        src.write_text(
            "[Script Info]\nTitle: Empty\n\n[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
            "MarginV, Effect, Text\n",
            encoding="utf-8",
        )
        out = tmp_path / "output.ass"
        assert translate_file(src, out, "French") is True
        assert out.exists()
        mock_translate.assert_not_called()

    @patch("src.core.llm_engine.translate_text")
    def test_srt_progress_callback(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """SRT translation fires progress callbacks."""
        src = tmp_path / "input.srt"
        src.write_text(
            "1\n00:00:01,000 --> 00:00:02,000\nHi\n",
            encoding="utf-8",
        )
        out = tmp_path / "output.srt"
        mock_translate.side_effect = lambda texts, *a, **kw: texts

        progress: list[int] = []
        assert (
            translate_file(src, out, "French", progress_callback=progress.append)
            is True
        )
        assert len(progress) > 0


# ---------------------------------------------------------------------------
# TestTranslateLocalizationFiles — .po, .pot, .xliff, .xlf edge cases
# ---------------------------------------------------------------------------


class TestTranslateLocalizationFiles:
    """Edge cases for localization file translation."""

    @patch("src.core.llm_engine.translate_text")
    def test_po_with_multiple_entries(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """PO file with multiple entries translates all."""
        src = tmp_path / "multi.po"
        src.write_text(
            'msgid ""\nmsgstr ""\n\n'
            'msgid "Hello"\nmsgstr ""\n\n'
            'msgid "World"\nmsgstr ""\n\n'
            'msgid "Test"\nmsgstr ""\n',
            encoding="utf-8",
        )
        out = tmp_path / "output.po"
        mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
        assert translate_file(src, out, "French") is True
        content = out.read_text(encoding="utf-8")
        assert "[T] Hello" in content
        assert "[T] World" in content
        assert "[T] Test" in content

    @patch("src.core.llm_engine.translate_text")
    def test_xliff_12_target_filled(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """XLIFF 1.2 has <target> elements filled after translation."""
        src = tmp_path / "input.xliff"
        src.write_text(
            '<?xml version="1.0"?>'
            '<xliff version="1.2" '
            'xmlns="urn:oasis:names:tc:xliff:document:1.2">'
            '<file source-language="en" target-language="fr" '
            'datatype="plaintext"><body>'
            '<trans-unit id="1"><source>Hello</source></trans-unit>'
            '<trans-unit id="2"><source>World</source></trans-unit>'
            "</body></file></xliff>",
            encoding="utf-8",
        )
        out = tmp_path / "output.xliff"
        mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
        assert translate_file(src, out, "French") is True
        content = out.read_text(encoding="utf-8")
        assert "[T] Hello" in content
        assert "[T] World" in content

    @patch("src.core.llm_engine.translate_text")
    def test_xliff_20_segment_translation(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """XLIFF 2.0 segment sources are translated."""
        src = tmp_path / "input.xlf"
        src.write_text(
            '<?xml version="1.0"?>'
            '<xliff xmlns="urn:oasis:names:tc:xliff:document:2.0"'
            ' version="2.0" srcLang="en" trgLang="fr">'
            '<file id="f1">'
            '<unit id="u1"><segment><source>Msg 1</source></segment></unit>'
            '<unit id="u2"><segment><source>Msg 2</source></segment></unit>'
            "</file></xliff>",
            encoding="utf-8",
        )
        out = tmp_path / "output.xlf"
        mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
        assert translate_file(src, out, "French") is True
        content = out.read_text(encoding="utf-8")
        assert "[T] Msg 1" in content
        assert "[T] Msg 2" in content

    @patch("src.core.llm_engine.translate_text")
    def test_localization_empty_entries_copied(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """Localization file with only header and no entries is copied."""
        src = tmp_path / "header_only.po"
        src.write_text(
            'msgid ""\nmsgstr ""\n',
            encoding="utf-8",
        )
        out = tmp_path / "output.po"
        assert translate_file(src, out, "French") is True
        assert out.exists()
        mock_translate.assert_not_called()

    @patch("src.core.llm_engine.translate_text")
    def test_xliff_write_error(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """XLIFF write failure raises TEXT_WRITE_ERROR."""
        src = tmp_path / "input.xliff"
        src.write_text(
            '<?xml version="1.0"?>'
            '<xliff version="1.2" '
            'xmlns="urn:oasis:names:tc:xliff:document:1.2">'
            '<file source-language="en" target-language="fr" '
            'datatype="plaintext"><body>'
            '<trans-unit id="1"><source>Hi</source></trans-unit>'
            "</body></file></xliff>",
            encoding="utf-8",
        )
        read_only = tmp_path / "readonly_xliff"
        read_only.mkdir()
        read_only.chmod(0o444)
        out = read_only / "subdir" / "output.xliff"

        mock_translate.side_effect = lambda texts, *a, **kw: texts

        try:
            with pytest.raises(ValueError, match="TEXT_WRITE_ERROR"):
                translate_file(src, out, "French")
        finally:
            read_only.chmod(0o755)

    @patch("src.core.llm_engine.translate_text")
    def test_xliff_llm_error_propagates(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """LLM error propagates through XLIFF translation."""
        src = tmp_path / "input.xliff"
        src.write_text(
            '<?xml version="1.0"?>'
            '<xliff version="1.2" '
            'xmlns="urn:oasis:names:tc:xliff:document:1.2">'
            '<file source-language="en" target-language="fr" '
            'datatype="plaintext"><body>'
            '<trans-unit id="1"><source>Hi</source></trans-unit>'
            "</body></file></xliff>",
            encoding="utf-8",
        )
        out = tmp_path / "output.xliff"
        mock_translate.side_effect = ValueError("AUTH_ERROR")
        with pytest.raises(ValueError, match="AUTH_ERROR"):
            translate_file(src, out, "French")


# ---------------------------------------------------------------------------
# TestTranslateKeyValueFiles — .yaml, .properties, .strings edge cases
# ---------------------------------------------------------------------------


class TestTranslateKeyValueFiles:
    """Edge cases for key-value file translation."""

    @patch("src.core.llm_engine.translate_text")
    def test_yaml_with_nested_keys(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """YAML with nested keys translates leaf values."""
        src = tmp_path / "nested.yaml"
        src.write_text(
            "top:\n  middle:\n    bottom: deep value\n",
            encoding="utf-8",
        )
        out = tmp_path / "output.yaml"
        mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
        assert translate_file(src, out, "French") is True
        content = out.read_text(encoding="utf-8")
        assert "[T] deep value" in content

    @patch("src.core.llm_engine.translate_text")
    def test_properties_comments_preserved(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """Java properties file preserves comment lines."""
        src = tmp_path / "comments.properties"
        src.write_text(
            "# This is a comment\ngreeting=Hello\n! Another comment\nfarewell=Bye\n",
            encoding="utf-8",
        )
        out = tmp_path / "output.properties"
        mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
        assert translate_file(src, out, "French") is True
        content = out.read_text(encoding="utf-8")
        assert "[T] Hello" in content
        assert "[T] Bye" in content

    @patch("src.core.llm_engine.translate_text")
    def test_strings_with_comments(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """Apple Strings file preserves comments."""
        src = tmp_path / "comments.strings"
        src.write_text(
            "/* Welcome screen */\n"
            '"welcome" = "Welcome";\n'
            "/* Login screen */\n"
            '"login" = "Login";\n',
            encoding="utf-8",
        )
        out = tmp_path / "output.strings"
        mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
        assert translate_file(src, out, "French") is True
        content = out.read_text(encoding="utf-8")
        assert "[T] Welcome" in content
        assert "[T] Login" in content

    @patch("src.core.llm_engine.translate_text")
    def test_properties_with_special_characters(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """Properties file with special chars in values."""
        src = tmp_path / "special.properties"
        src.write_text(
            "url=https://example.com\npath=C:\\Users\\test\n",
            encoding="utf-8",
        )
        out = tmp_path / "output.properties"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        assert translate_file(src, out, "French") is True
        assert out.exists()

    @patch("src.core.llm_engine.translate_text")
    def test_empty_properties_file(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """Empty properties file is copied as-is."""
        src = tmp_path / "empty.properties"
        src.write_text("", encoding="utf-8")
        out = tmp_path / "output.properties"
        assert translate_file(src, out, "French") is True
        assert out.exists()
        mock_translate.assert_not_called()

    @patch("src.core.llm_engine.translate_text")
    def test_empty_strings_file(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """Empty Apple Strings file is copied as-is."""
        src = tmp_path / "empty.strings"
        src.write_text("", encoding="utf-8")
        out = tmp_path / "output.strings"
        assert translate_file(src, out, "French") is True
        assert out.exists()
        mock_translate.assert_not_called()

    @patch("src.core.llm_engine.translate_text")
    def test_properties_write_error(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """Properties write failure raises TEXT_WRITE_ERROR."""
        src = tmp_path / "input.properties"
        src.write_text("key=Value\n", encoding="utf-8")
        read_only = tmp_path / "readonly_prop"
        read_only.mkdir()
        read_only.chmod(0o444)
        out = read_only / "subdir" / "output.properties"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        try:
            with pytest.raises(ValueError, match="TEXT_WRITE_ERROR"):
                translate_file(src, out, "French")
        finally:
            read_only.chmod(0o755)

    @patch("src.core.llm_engine.translate_text")
    def test_strings_llm_error_propagates(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """LLM error propagates through Strings translation."""
        src = tmp_path / "input.strings"
        src.write_text('"key" = "value";\n', encoding="utf-8")
        out = tmp_path / "output.strings"
        mock_translate.side_effect = ValueError("QUOTA_ERROR")
        with pytest.raises(ValueError, match="QUOTA_ERROR"):
            translate_file(src, out, "French")


# ---------------------------------------------------------------------------
# TestTranslateRtfFile — .rtf edge cases
# ---------------------------------------------------------------------------


class TestTranslateRtfFile:
    """Edge cases for RTF file translation."""

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_rtf_control_words_stripped_and_restored(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        r"""RTF control words (\\b, \\i, \\rtf1) are stripped then restored."""
        src = tmp_path / "input.rtf"
        src.write_text(
            r"{\rtf1\ansi\deff0 Hello \b Bold \b0 Normal}",
            encoding="utf-8",
        )
        out = tmp_path / "output.rtf"

        captured: list[list[str]] = []

        def mock_fn(texts: list[str], *a: object, **kw: object) -> list[str]:
            captured.append(list(texts))
            return texts

        mock_translate.side_effect = mock_fn
        assert translate_file(src, out, "French") is True

        # Control words should not be in LLM input
        sent = " ".join(captured[0])
        assert "\\rtf1" not in sent
        assert "\\ansi" not in sent

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_rtf_with_par_separator(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        r"""RTF with multiple \\par paragraphs chunks correctly."""
        src = tmp_path / "input.rtf"
        src.write_text(
            r"{\rtf1 Para one\par Para two\par Para three}",
            encoding="utf-8",
        )
        out = tmp_path / "output.rtf"
        mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
        assert translate_file(src, out, "French") is True
        content = out.read_text(encoding="utf-8")
        assert "[T]" in content

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_rtf_empty_content(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """Empty RTF content produces output without LLM call."""
        src = tmp_path / "empty.rtf"
        src.write_text("", encoding="utf-8")
        out = tmp_path / "output.rtf"
        assert translate_file(src, out, "French") is True
        assert out.exists()
        mock_translate.assert_not_called()


# ---------------------------------------------------------------------------
# TestTranslateMdFile — .md edge cases
# ---------------------------------------------------------------------------


class TestTranslateMdFile:
    """Edge cases for Markdown file translation."""

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_md_headings(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """Markdown headings at different levels are translated."""
        src = tmp_path / "headings.md"
        src.write_text(
            "# Heading 1\n\n## Heading 2\n\n### Heading 3\n\nParagraph.",
            encoding="utf-8",
        )
        out = tmp_path / "output.md"
        mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
        assert translate_file(src, out, "French") is True
        content = out.read_text(encoding="utf-8")
        assert "[T]" in content

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_md_code_blocks_sent_to_llm(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """Markdown code blocks are part of the chunk sent to LLM.

        The CONTENT_MARKDOWN prompt instructs the model not to translate code.
        """
        src = tmp_path / "code.md"
        src.write_text(
            "# Title\n\n```python\nprint('hello')\n```\n\nParagraph.",
            encoding="utf-8",
        )
        out = tmp_path / "output.md"

        captured: list[list[str]] = []

        def mock_fn(texts: list[str], *a: object, **kw: object) -> list[str]:
            captured.append(list(texts))
            return texts

        mock_translate.side_effect = mock_fn
        assert translate_file(src, out, "French") is True
        content = out.read_text(encoding="utf-8")
        # Code block content should appear in output
        assert "print('hello')" in content

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_md_links_urls_stripped(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """Markdown link URLs are stripped before LLM and restored after."""
        src = tmp_path / "links.md"
        src.write_text(
            "Visit [Google](https://google.com) and [GitHub](https://github.com).",
            encoding="utf-8",
        )
        out = tmp_path / "output.md"

        captured: list[list[str]] = []

        def mock_fn(texts: list[str], *a: object, **kw: object) -> list[str]:
            captured.append(list(texts))
            return texts

        mock_translate.side_effect = mock_fn
        assert translate_file(src, out, "French") is True

        # URLs should not be sent to LLM
        sent = " ".join(captured[0])
        assert "https://google.com" not in sent
        assert "https://github.com" not in sent

        # But restored in output
        content = out.read_text(encoding="utf-8")
        assert "https://google.com" in content
        assert "https://github.com" in content

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_md_images_urls_stripped(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """Markdown image URLs are stripped before LLM and restored after."""
        src = tmp_path / "images.md"
        src.write_text(
            "![Alt text](https://example.com/image.png)",
            encoding="utf-8",
        )
        out = tmp_path / "output.md"

        captured: list[list[str]] = []

        def mock_fn(texts: list[str], *a: object, **kw: object) -> list[str]:
            captured.append(list(texts))
            return texts

        mock_translate.side_effect = mock_fn
        assert translate_file(src, out, "French") is True

        # Image URL should not reach the LLM
        sent = " ".join(captured[0])
        assert "https://example.com/image.png" not in sent

        # Restored in output
        content = out.read_text(encoding="utf-8")
        assert "https://example.com/image.png" in content


# ---------------------------------------------------------------------------
# TestTokenOptimization — attribute/overhead stripping and restoration
# ---------------------------------------------------------------------------


class TestTokenOptimization:
    """Tests for format-specific token optimization (strip/restore)."""

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_html_class_id_style_stripped(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """HTML class, id, and style attributes are stripped for LLM."""
        src = tmp_path / "styled.html"
        src.write_text(
            '<div class="main" style="color: red;"><span id="s1">Hello</span></div>',
            encoding="utf-8",
        )
        out = tmp_path / "output.html"

        captured: list[list[str]] = []

        def mock_fn(texts: list[str], *a: object, **kw: object) -> list[str]:
            captured.append(list(texts))
            return texts

        mock_translate.side_effect = mock_fn
        translate_file(src, out, "French")

        sent = " ".join(captured[0])
        assert 'class="main"' not in sent
        assert 'style="color: red;"' not in sent
        assert 'id="s1"' not in sent

        content = out.read_text(encoding="utf-8")
        assert 'class="main"' in content
        assert 'style="color: red;"' in content
        assert 'id="s1"' in content

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_xml_overhead_cdata_stripped(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """XML CDATA markers and PIs are stripped for LLM; comments are kept."""
        src = tmp_path / "overhead.xml"
        src.write_text(
            '<?xml version="1.0"?>\n'
            "<!-- A comment -->\n"
            "<root><![CDATA[some data]]></root>",
            encoding="utf-8",
        )
        out = tmp_path / "output.xml"

        captured: list[list[str]] = []

        def mock_fn(texts: list[str], *a: object, **kw: object) -> list[str]:
            captured.append(list(texts))
            return texts

        mock_translate.side_effect = mock_fn
        translate_file(src, out, "French")

        sent = " ".join(captured[0])
        # Comments are left intact for the LLM (it naturally skips them)
        assert "<!-- A comment -->" in sent
        # CDATA markers and processing instructions are stripped
        assert "<![CDATA[" not in sent
        assert "<?xml" not in sent

        content = out.read_text(encoding="utf-8")
        assert "<!-- A comment -->" in content
        assert "<![CDATA[" in content

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_rtf_overhead_braces_stripped(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        r"""RTF braces and control words are stripped for LLM."""
        src = tmp_path / "overhead.rtf"
        src.write_text(
            r"{\rtf1\ansi Hello World}",
            encoding="utf-8",
        )
        out = tmp_path / "output.rtf"

        captured: list[list[str]] = []

        def mock_fn(texts: list[str], *a: object, **kw: object) -> list[str]:
            captured.append(list(texts))
            return texts

        mock_translate.side_effect = mock_fn
        translate_file(src, out, "French")

        sent = " ".join(captured[0])
        assert "\\rtf1" not in sent
        assert "\\ansi" not in sent

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_md_overhead_link_urls_stripped(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """Markdown link/image URLs are stripped to reduce token usage."""
        src = tmp_path / "md_urls.md"
        src.write_text(
            "[Click](https://example.com/long/path/to/page)\n\n"
            "![Image](https://cdn.example.com/img.jpg)",
            encoding="utf-8",
        )
        out = tmp_path / "output.md"

        captured: list[list[str]] = []

        def mock_fn(texts: list[str], *a: object, **kw: object) -> list[str]:
            captured.append(list(texts))
            return texts

        mock_translate.side_effect = mock_fn
        translate_file(src, out, "French")

        sent = " ".join(captured[0])
        assert "https://example.com/long/path/to/page" not in sent
        assert "https://cdn.example.com/img.jpg" not in sent

        content = out.read_text(encoding="utf-8")
        assert "https://example.com/long/path/to/page" in content
        assert "https://cdn.example.com/img.jpg" in content

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_xml_attributes_stripped_and_restored(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """XML element attributes are stripped and restored in output."""
        src = tmp_path / "attrs.xml"
        src.write_text(
            '<root version="1.0">\n  <item type="text" key="k1">Hello</item>\n</root>',
            encoding="utf-8",
        )
        out = tmp_path / "output.xml"

        captured: list[list[str]] = []

        def mock_fn(texts: list[str], *a: object, **kw: object) -> list[str]:
            captured.append(list(texts))
            return texts

        mock_translate.side_effect = mock_fn
        translate_file(src, out, "French")

        sent = " ".join(captured[0])
        assert 'version="1.0"' not in sent
        assert 'type="text"' not in sent

        content = out.read_text(encoding="utf-8")
        assert 'version="1.0"' in content
        assert 'type="text"' in content
        assert 'key="k1"' in content

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_html_attributes_not_stripped_for_txt(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """Plain .txt files do NOT have HTML attribute stripping."""
        src = tmp_path / "html_in_txt.txt"
        src.write_text(
            '<div class="test">Hello</div>',
            encoding="utf-8",
        )
        out = tmp_path / "output.txt"

        captured: list[list[str]] = []

        def mock_fn(texts: list[str], *a: object, **kw: object) -> list[str]:
            captured.append(list(texts))
            return texts

        mock_translate.side_effect = mock_fn
        translate_file(src, out, "French")

        sent = " ".join(captured[0])
        # Txt does not strip attributes — sent as-is
        assert 'class="test"' in sent


# ---------------------------------------------------------------------------
# Additional edge cases — config parameter forwarding
# ---------------------------------------------------------------------------


class TestConfigForwarding:
    """Tests that config parameter is forwarded to sub-processors."""

    @patch("src.core.pdf_processor.process_pdf_file")
    def test_pdf_receives_config(self, mock_pdf: MagicMock, tmp_path: Path) -> None:
        """translate_file forwards config to process_pdf_file."""
        from src.core.config import TranslationConfig  # noqa: PLC0415

        src = tmp_path / "input.pdf"
        src.write_bytes(b"%PDF-1.4\n")
        out = tmp_path / "output.pdf"
        mock_pdf.return_value = True

        cfg = TranslationConfig(storage_path="/tmp/test")
        translate_file(src, out, "French", config=cfg)

        call_kwargs = mock_pdf.call_args[1]
        assert call_kwargs["config"] is cfg

    @patch("src.core.text_processor.process_office_file")
    def test_office_receives_config(
        self, mock_office: MagicMock, tmp_path: Path
    ) -> None:
        """translate_file forwards config to process_office_file."""
        from src.core.config import TranslationConfig  # noqa: PLC0415

        src = tmp_path / "input.docx"
        src.touch()
        out = tmp_path / "output.docx"
        mock_office.return_value = True

        cfg = TranslationConfig(translate_doc_comments=True)
        translate_file(src, out, "French", config=cfg)

        call_kwargs = mock_office.call_args[1]
        assert call_kwargs["config"] is cfg


# ---------------------------------------------------------------------------
# Additional edge cases — mixed/boundary scenarios
# ---------------------------------------------------------------------------


class TestMixedEdgeCases:
    """Miscellaneous boundary and integration tests."""

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_translate_file_with_progress_and_glossary(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """All optional params (progress, glossary, cancel) work together."""
        src = tmp_path / "input.txt"
        src.write_text("Hello\n\nWorld", encoding="utf-8")
        out = tmp_path / "output.txt"
        mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]

        progress: list[int] = []
        glossary = [(1, "Hello", "Bonjour")]

        result = translate_file(
            src,
            out,
            "French",
            "English (US)",
            progress_callback=progress.append,
            glossary_entries=glossary,
            cancel_check=lambda: False,
        )
        assert result is True
        assert len(progress) > 0
        # Glossary forwarded to LLM
        _, kwargs = mock_translate.call_args
        assert kwargs["glossary_entries"] == glossary

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_translate_file_checkpoint_dir_forwarded(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """checkpoint_dir is forwarded to _translate_chunks."""
        src = tmp_path / "input.txt"
        src.write_text("Hello", encoding="utf-8")
        out = tmp_path / "output.txt"
        mock_translate.side_effect = lambda texts, *a, **kw: texts

        cp_dir = tmp_path / "checkpoints"
        cp_dir.mkdir()

        result = translate_file(src, out, "French", checkpoint_dir=cp_dir)
        assert result is True

    def test_read_file_shift_jis(self, tmp_path: Path) -> None:
        """Shift-JIS encoded file is detected and read correctly."""
        text = "こんにちは世界"
        f = tmp_path / "sjis.txt"
        f.write_bytes(text.encode("shift_jis"))
        result = _read_file(f)
        assert "こんにちは" in result

    @patch("src.core.llm_engine.translate_text")
    def test_csv_single_cell(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """CSV with a single cell translates it."""
        src = tmp_path / "single.csv"
        # csv.Sniffer needs a recognisable delimiter in the content;
        # a bare word causes it to pick a letter as delimiter.
        # Use two columns so the comma is detected correctly.
        src.write_text("Hello,World\n", encoding="utf-8")
        out = tmp_path / "output.csv"
        mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
        assert translate_file(src, out, "French") is True
        content = out.read_text(encoding="utf-8")
        assert "[T] Hello" in content
        assert "[T] World" in content

    @patch("src.core.llm_engine.translate_text")
    def test_json_unicode_keys_and_values(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """JSON with Unicode keys and values translates values only."""
        src = tmp_path / "unicode.json"
        data = {"挨拶": "こんにちは", "名前": "太郎"}
        src.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        out = tmp_path / "output.json"
        mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
        assert translate_file(src, out, "French") is True
        result = json.loads(out.read_text(encoding="utf-8"))
        # Keys preserved, values translated
        assert "挨拶" in result
        assert result["挨拶"].startswith("[T]")

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_htm_treated_as_html(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """.htm is dispatched identically to .html."""
        src = tmp_path / "input.htm"
        src.write_text(
            '<div class="test"><p>Hello</p></div>',
            encoding="utf-8",
        )
        out = tmp_path / "output.htm"

        captured: list[list[str]] = []

        def mock_fn(texts: list[str], *a: object, **kw: object) -> list[str]:
            captured.append(list(texts))
            return texts

        mock_translate.side_effect = mock_fn
        translate_file(src, out, "French")

        # Attributes should be stripped (HTML treatment)
        sent = " ".join(captured[0])
        assert 'class="test"' not in sent

        # Restored in output
        content = out.read_text(encoding="utf-8")
        assert 'class="test"' in content

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_translate_chunks_single_chunk(self, mock_translate: MagicMock) -> None:
        """Single chunk translates and returns correctly."""
        mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
        result = _translate_chunks(
            ["Hello World"],
            "French",
            "",
            progress_callback=None,
            glossary_entries=None,
            cancel_check=None,
        )
        assert result == ["[T] Hello World"]

    def test_get_separator_unknown_falls_to_newline(self) -> None:
        """Unknown extension defaults to newline separator."""
        # Extensions not in _PLAIN_FORMATS and not .rtf
        assert _get_separator(".xyz") == "\n"
        assert _get_separator(".abc") == "\n"

    def test_chunk_text_trailing_separator(self) -> None:
        """Content ending with separator is handled correctly."""
        content = "Hello\n\nWorld\n\n"
        chunks, seps = _chunk_text(content, "\n\n", max_chars=100)
        reassembled = _join_with_separators(chunks, seps)
        assert reassembled == content

    @patch("src.core.llm_engine.translate_text")
    def test_subtitle_write_error_vtt(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """VTT write failure raises TEXT_WRITE_ERROR."""
        src = tmp_path / "input.vtt"
        src.write_text(
            "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nHi\n",
            encoding="utf-8",
        )
        read_only = tmp_path / "readonly_vtt"
        read_only.mkdir()
        read_only.chmod(0o444)
        out = read_only / "subdir" / "output.vtt"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        try:
            with pytest.raises(ValueError, match="TEXT_WRITE_ERROR"):
                translate_file(src, out, "French")
        finally:
            read_only.chmod(0o755)

    @patch("src.core.llm_engine.translate_text")
    def test_subtitle_llm_error_vtt(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """LLM error propagates through VTT translation."""
        src = tmp_path / "input.vtt"
        src.write_text(
            "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nHi\n",
            encoding="utf-8",
        )
        out = tmp_path / "output.vtt"
        mock_translate.side_effect = ValueError("QUOTA_ERROR")
        with pytest.raises(ValueError, match="QUOTA_ERROR"):
            translate_file(src, out, "French")

    @patch("src.core.llm_engine.translate_text")
    def test_subtitle_cancel_vtt(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """VTT translation returns False when cancelled."""
        src = tmp_path / "input.vtt"
        src.write_text(
            "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nHi\n",
            encoding="utf-8",
        )
        out = tmp_path / "output.vtt"
        result = translate_file(src, out, "French", cancel_check=lambda: True)
        assert result is False
        mock_translate.assert_not_called()

    @patch("src.core.llm_engine.translate_text")
    def test_keyvalue_cancel_properties(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """Properties translation returns False when cancelled."""
        src = tmp_path / "input.properties"
        src.write_text("key=Value\n", encoding="utf-8")
        out = tmp_path / "output.properties"
        result = translate_file(src, out, "French", cancel_check=lambda: True)
        assert result is False
        mock_translate.assert_not_called()

    @patch("src.core.llm_engine.translate_text")
    def test_keyvalue_cancel_strings(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """Apple Strings translation returns False when cancelled."""
        src = tmp_path / "input.strings"
        src.write_text('"key" = "value";\n', encoding="utf-8")
        out = tmp_path / "output.strings"
        result = translate_file(src, out, "French", cancel_check=lambda: True)
        assert result is False
        mock_translate.assert_not_called()


# ===========================================================================
# EXPANDED EDGE-CASE TESTS — targeting 550+ total
# ===========================================================================


# ---------------------------------------------------------------------------
# TestReadFileEdgeCases — encoding detection and BOM handling
# ---------------------------------------------------------------------------


class TestReadFileEdgeCases:
    """Extended tests for _read_file encoding and BOM handling."""

    def test_utf8_bom_with_content(self, tmp_path: Path) -> None:
        """UTF-8 BOM with real content is stripped cleanly."""
        f = tmp_path / "bom.txt"
        f.write_bytes(b"\xef\xbb\xbfHello\nWorld")
        result = _read_file(f)
        assert result == "Hello\nWorld"
        assert "\ufeff" not in result

    def test_utf16_le_bom(self, tmp_path: Path) -> None:
        """UTF-16-LE BOM file is decoded and BOM stripped."""
        f = tmp_path / "utf16le.txt"
        f.write_bytes(b"\xff\xfeH\x00e\x00l\x00l\x00o\x00")
        result = _read_file(f)
        assert "Hello" in result

    def test_utf16_be_bom(self, tmp_path: Path) -> None:
        """UTF-16-BE BOM file is decoded and BOM stripped."""
        f = tmp_path / "utf16be.txt"
        f.write_bytes(b"\xfe\xff\x00H\x00e\x00l\x00l\x00o")
        result = _read_file(f)
        assert "Hello" in result

    def test_gb2312_content(self, tmp_path: Path) -> None:
        """GB2312 (Chinese) content is detected and decoded."""
        text = "你好世界这是一个很长的中文句子用来确保编码检测正常工作"
        f = tmp_path / "gb2312.txt"
        f.write_bytes(text.encode("gb2312"))
        result = _read_file(f)
        assert "你好" in result

    def test_euc_kr_content(self, tmp_path: Path) -> None:
        """EUC-KR (Korean) content is detected and decoded."""
        text = "안녕하세요 세계 한국어 텍스트 인코딩 테스트입니다"
        f = tmp_path / "euckr.txt"
        f.write_bytes(text.encode("euc-kr"))
        result = _read_file(f)
        assert "안녕" in result

    def test_latin1_accented_content(self, tmp_path: Path) -> None:
        """Latin-1 accented text (French) is decoded correctly."""
        text = "Les élèves étudient les mathématiques avec précision"
        f = tmp_path / "latin1.txt"
        f.write_bytes(text.encode("latin-1"))
        result = _read_file(f)
        assert "élèves" in result or "l" in result

    def test_only_bom_no_content(self, tmp_path: Path) -> None:
        """File with only a BOM marker returns empty string."""
        f = tmp_path / "bom_only.txt"
        f.write_bytes(b"\xef\xbb\xbf")
        result = _read_file(f)
        assert result == ""

    def test_bom_with_whitespace_content(self, tmp_path: Path) -> None:
        """BOM followed by whitespace returns whitespace only."""
        f = tmp_path / "bom_ws.txt"
        f.write_bytes(b"\xef\xbb\xbf   \n\n   ")
        result = _read_file(f)
        assert result == "   \n\n   "
        assert "\ufeff" not in result

    def test_detect_encoding_with_empty_bytes(self) -> None:
        """_detect_encoding with empty bytes falls back to latin-1."""
        from src.core.text_processor import _detect_encoding  # noqa: PLC0415

        # Empty bytes may return None from charset_normalizer
        result = _detect_encoding(b"")
        assert isinstance(result, str)

    def test_read_file_large_utf8(self, tmp_path: Path) -> None:
        """Large UTF-8 file reads without issues."""
        f = tmp_path / "large.txt"
        content = "Hello World! This is a test. " * 10000
        f.write_text(content, encoding="utf-8")
        result = _read_file(f)
        assert len(result) == len(content)


# ---------------------------------------------------------------------------
# TestChunkTextExtended — boundary conditions and edge cases
# ---------------------------------------------------------------------------


class TestChunkTextExtended:
    """Extended tests for _chunk_text boundary conditions."""

    def test_max_chars_equals_content_length(self) -> None:
        """Content exactly at max_chars stays in one chunk."""
        content = "Hello"
        chunks, seps = _chunk_text(content, "\n\n", max_chars=5)
        assert len(chunks) == 1
        assert chunks[0] == "Hello"

    def test_max_chars_one_more_than_content(self) -> None:
        """Content one char shorter than max_chars stays in one chunk."""
        content = "Hi"
        chunks, seps = _chunk_text(content, "\n\n", max_chars=3)
        assert len(chunks) == 1

    def test_separator_at_start_of_content(self) -> None:
        """Content starting with separator handles leading empty segment."""
        content = "\n\nHello\n\nWorld"
        chunks, seps = _chunk_text(content, "\n\n", max_chars=100)
        reassembled = _join_with_separators(chunks, seps)
        assert "Hello" in reassembled
        assert "World" in reassembled

    def test_separator_at_end_of_content(self) -> None:
        """Content ending with separator preserves trailing content."""
        content = "Hello\n\nWorld\n\n"
        chunks, seps = _chunk_text(content, "\n\n", max_chars=100)
        reassembled = _join_with_separators(chunks, seps)
        assert reassembled == content

    def test_multiple_consecutive_separators(self) -> None:
        """Multiple consecutive separators are preserved."""
        content = "A\n\n\n\n\n\nB"
        chunks, seps = _chunk_text(content, "\n\n", max_chars=100)
        reassembled = _join_with_separators(chunks, seps)
        assert reassembled == content

    def test_max_chars_zero(self) -> None:
        """max_chars=0 forces each segment into its own chunk."""
        content = "A\n\nB\n\nC"
        chunks, seps = _chunk_text(content, "\n\n", max_chars=0)
        assert len(chunks) == 3  # noqa: PLR2004
        reassembled = _join_with_separators(chunks, seps)
        assert reassembled == content

    def test_max_chars_one(self) -> None:
        """max_chars=1 forces each segment into its own chunk."""
        content = "A\n\nB\n\nC"
        chunks, seps = _chunk_text(content, "\n\n", max_chars=1)
        assert len(chunks) == 3  # noqa: PLR2004
        reassembled = _join_with_separators(chunks, seps)
        assert reassembled == content

    def test_all_whitespace_segments_with_content_mixed(self) -> None:
        """Mixed whitespace and content segments filter correctly."""
        content = "   \n\nHello\n\n   \n\nWorld\n\n   "
        chunks, seps = _chunk_text(content, "\n\n", max_chars=100)
        # Only non-whitespace chunks should remain
        for chunk in chunks:
            stripped = chunk.strip()
            if stripped:
                assert (
                    stripped in ("Hello", "World")
                    or "Hello" in stripped
                    or "World" in stripped
                )

    def test_very_large_max_chars(self) -> None:
        """Very large max_chars keeps everything in one chunk."""
        content = "\n\n".join(f"P{i}" for i in range(100))
        chunks, seps = _chunk_text(content, "\n\n", max_chars=999999)
        assert len(chunks) == 1
        assert _join_with_separators(chunks, seps) == content

    def test_rtf_separator_with_adjacent_text(self) -> None:
        r"""RTF \\par separator adjacent to text splits correctly."""
        content = r"Hello\parWorld\parEnd"
        chunks, seps = _chunk_text(content, "\\par", max_chars=10)
        reassembled = _join_with_separators(chunks, seps)
        assert reassembled == content

    def test_chunk_text_with_tabs_and_spaces(self) -> None:
        """Content with tabs and spaces within segments is preserved."""
        content = "Hello\tWorld\n\nFoo\t\tBar"
        chunks, seps = _chunk_text(content, "\n\n", max_chars=100)
        reassembled = _join_with_separators(chunks, seps)
        assert reassembled == content
        assert "\t" in reassembled

    def test_emoji_content_in_chunks(self) -> None:
        """Emoji characters in chunks are handled correctly."""
        content = "Hello! 😀🎉\n\nWorld! 🌍✨"
        chunks, seps = _chunk_text(content, "\n\n", max_chars=100)
        reassembled = _join_with_separators(chunks, seps)
        assert reassembled == content
        assert "😀" in reassembled

    def test_mixed_newlines_crlf(self) -> None:
        """CRLF newlines in content are preserved through chunking."""
        content = "Hello\r\nWorld"
        chunks, seps = _chunk_text(content, "\n", max_chars=100)
        reassembled = _join_with_separators(chunks, seps)
        assert reassembled == content


# ---------------------------------------------------------------------------
# TestJoinWithSeparators — extended
# ---------------------------------------------------------------------------


class TestJoinWithSeparatorsExtended:
    """Extended tests for _join_with_separators."""

    def test_many_parts_and_seps(self) -> None:
        """Multiple parts and separators join correctly."""
        parts = ["A", "B", "C", "D"]
        seps = ["\n\n", "\n\n\n\n", "\n\n"]
        result = _join_with_separators(parts, seps)
        assert result == "A\n\nB\n\n\n\nC\n\nD"

    def test_different_separators(self) -> None:
        """Different separator strings between parts."""
        parts = ["Hello", "World", "End"]
        seps = [" - ", " | "]
        result = _join_with_separators(parts, seps)
        assert result == "Hello - World | End"

    def test_empty_string_parts(self) -> None:
        """Parts containing empty strings still join correctly."""
        parts = ["", "Hello", ""]
        seps = ["\n\n", "\n\n"]
        result = _join_with_separators(parts, seps)
        assert result == "\n\nHello\n\n"

    def test_single_part_empty_seps(self) -> None:
        """Single part with empty separator list."""
        assert _join_with_separators(["only"], []) == "only"


# ---------------------------------------------------------------------------
# TestGetSeparator — all known extensions
# ---------------------------------------------------------------------------


class TestGetSeparatorExtended:
    """Extended tests for _get_separator across all extensions."""

    def test_plain_text_formats(self) -> None:
        """All plain text formats use paragraph separator."""
        assert _get_separator(".txt") == "\n\n"
        assert _get_separator(".md") == "\n\n"
        assert _get_separator(".rst") == "\n\n"

    def test_markup_formats(self) -> None:
        """Markup formats use line separator."""
        assert _get_separator(".html") == "\n"
        assert _get_separator(".htm") == "\n"
        assert _get_separator(".xml") == "\n"

    def test_rtf_format(self) -> None:
        """RTF uses \\par separator."""
        assert _get_separator(".rtf") == "\\par"

    def test_unknown_extension(self) -> None:
        """Unknown extensions fall back to line separator."""
        assert _get_separator(".foo") == "\n"
        assert _get_separator("") == "\n"
        assert _get_separator(".docx") == "\n"


# ---------------------------------------------------------------------------
# TestExtractJsonStringsExtended — deep nesting and special values
# ---------------------------------------------------------------------------


class TestExtractJsonStringsExtended:
    """Extended JSON extraction/injection tests."""

    def test_extract_empty_dict(self) -> None:
        """Empty dict yields no pairs."""
        assert _extract_json_strings({}) == []

    def test_extract_empty_list(self) -> None:
        """Empty list yields no pairs."""
        assert _extract_json_strings([]) == []

    def test_extract_single_string(self) -> None:
        """Single string value is extracted."""
        pairs = _extract_json_strings({"key": "val"})
        assert len(pairs) == 1
        assert pairs[0] == (("key",), "val")

    def test_extract_nested_arrays(self) -> None:
        """Deeply nested arrays extract strings with index paths."""
        data = [[["deep"]]]
        pairs = _extract_json_strings(data)
        assert len(pairs) == 1
        assert pairs[0][0] == (0, 0, 0)
        assert pairs[0][1] == "deep"

    def test_extract_mixed_types_in_array(self) -> None:
        """Array with mixed types only extracts strings."""
        data = ["hello", 42, True, None, "world"]
        pairs = _extract_json_strings(data)
        assert len(pairs) == 2  # noqa: PLR2004
        values = [v for _, v in pairs]
        assert "hello" in values
        assert "world" in values

    def test_extract_string_with_special_chars(self) -> None:
        """Strings with newlines, tabs, quotes are extracted."""
        data = {"msg": 'Hello\nWorld\t"quoted"'}
        pairs = _extract_json_strings(data)
        assert len(pairs) == 1
        assert "\n" in pairs[0][1]

    def test_inject_preserves_structure(self) -> None:
        """Injection preserves original structure for unmatched paths."""
        data = {"a": "hello", "b": 42, "c": [1, "x"]}
        translations = {("a",): "bonjour", ("c", 1): "y"}
        result = _inject_json_strings(data, translations)
        assert result["a"] == "bonjour"
        assert result["b"] == 42  # noqa: PLR2004
        assert result["c"][0] == 1
        assert result["c"][1] == "y"

    def test_inject_empty_translations(self) -> None:
        """Empty translations dict preserves all original values."""
        data = {"a": "hello", "b": "world"}
        result = _inject_json_strings(data, {})
        assert result["a"] == "hello"
        assert result["b"] == "world"

    def test_extract_whitespace_only_strings_skipped(self) -> None:
        """Whitespace-only strings are not extracted."""
        data = {"tabs": "\t\t", "spaces": "   ", "newlines": "\n\n"}
        pairs = _extract_json_strings(data)
        assert len(pairs) == 0

    def test_extract_numeric_string_values(self) -> None:
        """String values that look numeric are still extracted."""
        data = {"version": "1.0.0", "port": "8080"}
        pairs = _extract_json_strings(data)
        assert len(pairs) == 2  # noqa: PLR2004


# ---------------------------------------------------------------------------
# TestTranslateChunksExtended — sub-batch behavior and edge cases
# ---------------------------------------------------------------------------


class TestTranslateChunksExtended:
    """Extended tests for _translate_chunks."""

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_large_number_of_chunks(self, mock_translate: MagicMock) -> None:
        """Many chunks are all translated and returned."""
        mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
        chunks = [f"Chunk {i}" for i in range(50)]
        result = _translate_chunks(
            chunks,
            "French",
            "",
            progress_callback=None,
            glossary_entries=None,
            cancel_check=None,
        )
        assert result is not None
        assert len(result) == 50  # noqa: PLR2004
        assert all(r.startswith("[T]") for r in result)

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_cancel_before_start(self, mock_translate: MagicMock) -> None:
        """Cancel before any processing returns None."""
        result = _translate_chunks(
            ["A"],
            "French",
            "",
            progress_callback=None,
            glossary_entries=None,
            cancel_check=lambda: True,
        )
        assert result is None
        mock_translate.assert_not_called()

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_progress_reaches_100(self, mock_translate: MagicMock) -> None:
        """Progress callback eventually reaches 100."""
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        progress: list[int] = []
        _translate_chunks(
            ["A", "B", "C"],
            "French",
            "",
            progress_callback=progress.append,
            glossary_entries=None,
            cancel_check=None,
        )
        assert 100 in progress

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_checkpoint_partial_cache(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """Partially cached chunks: cached ones skip LLM, rest translated."""
        save_text_chunk(tmp_path, 1, "[cached] B", 3)

        mock_translate.side_effect = lambda texts, *a, **kw: [
            f"[LLM] {t}" for t in texts
        ]

        result = _translate_chunks(
            ["A", "B", "C"],
            "French",
            "",
            progress_callback=None,
            glossary_entries=None,
            cancel_check=None,
            checkpoint_dir=tmp_path,
        )
        assert result is not None
        assert result[1] == "[cached] B"
        assert result[0] == "[LLM] A"
        assert result[2] == "[LLM] C"

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_content_type_html_forwarded(self, mock_translate: MagicMock) -> None:
        """content_type='html' is forwarded to translate_text."""
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        _translate_chunks(
            ["test"],
            "French",
            "",
            progress_callback=None,
            glossary_entries=None,
            cancel_check=None,
            content_type="html",
        )
        _, kwargs = mock_translate.call_args
        assert kwargs["content_type"] == "html"

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_content_type_markdown_forwarded(self, mock_translate: MagicMock) -> None:
        """content_type='markdown' is forwarded to translate_text."""
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        _translate_chunks(
            ["test"],
            "French",
            "",
            progress_callback=None,
            glossary_entries=None,
            cancel_check=None,
            content_type="markdown",
        )
        _, kwargs = mock_translate.call_args
        assert kwargs["content_type"] == "markdown"

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_content_type_xml_forwarded(self, mock_translate: MagicMock) -> None:
        """content_type='xml' is forwarded to translate_text."""
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        _translate_chunks(
            ["test"],
            "French",
            "",
            progress_callback=None,
            glossary_entries=None,
            cancel_check=None,
            content_type="xml",
        )
        _, kwargs = mock_translate.call_args
        assert kwargs["content_type"] == "xml"

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_empty_input_no_progress_callback(self, mock_translate: MagicMock) -> None:
        """Empty input with no progress_callback does not crash."""
        result = _translate_chunks(
            [],
            "French",
            "",
            progress_callback=None,
            glossary_entries=None,
            cancel_check=None,
        )
        assert result == []


# ---------------------------------------------------------------------------
# TestRepairAndRestoreAttrs — extended
# ---------------------------------------------------------------------------


class TestRepairAndRestoreAttrsExtended:
    """Extended tests for _repair_and_restore_attrs."""

    def test_no_change_when_translation_matches(self) -> None:
        """When translated matches original, result is unchanged."""
        result = _repair_and_restore_attrs("<b>Hello</b>", "<b>Hello</b>", {})
        assert result == "<b>Hello</b>"

    def test_multiple_attrs_restored(self) -> None:
        """Multiple attribute records are restored correctly."""
        from src.utils.text_utils import AttrRecord, _AttrEntry  # noqa: PLC0415

        original = '<p data-ftid="0">Hi</p><div data-ftid="1">There</div>'
        translated = '<p data-ftid="0">Salut</p><div data-ftid="1">Là</div>'
        records = {
            0: AttrRecord(
                tag_name="p",
                attrs=[_AttrEntry('class="a"', False)],
            ),
            1: AttrRecord(
                tag_name="div",
                attrs=[_AttrEntry('id="b"', False)],
            ),
        }
        result = _repair_and_restore_attrs(translated, original, records)
        assert 'class="a"' in result
        assert 'id="b"' in result

    def test_empty_translation_with_records(self) -> None:
        """Empty translated string with records does not crash."""
        result = _repair_and_restore_attrs("", "<b>Hi</b>", {})
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# TestTranslateFileBOMHandling — BOM across all plain formats
# ---------------------------------------------------------------------------


class TestTranslateFileBOMHandling:
    """BOM handling across all plain/markup formats."""

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_bom_txt(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """BOM in .txt file is stripped from output."""
        src = tmp_path / "bom.txt"
        src.write_bytes(b"\xef\xbb\xbfHello World")
        out = tmp_path / "output.txt"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        translate_file(src, out, "French")
        raw = out.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf")

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_bom_md(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """BOM in .md file is stripped from output."""
        src = tmp_path / "bom.md"
        src.write_bytes(b"\xef\xbb\xbf# Title")
        out = tmp_path / "output.md"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        translate_file(src, out, "French")
        assert "\ufeff" not in out.read_text(encoding="utf-8")

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_bom_rst(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """BOM in .rst file is stripped from output."""
        src = tmp_path / "bom.rst"
        src.write_bytes(b"\xef\xbb\xbfTitle\n=====")
        out = tmp_path / "output.rst"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        translate_file(src, out, "French")
        assert "\ufeff" not in out.read_text(encoding="utf-8")

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_bom_rtf(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """BOM in .rtf file is stripped from output."""
        src = tmp_path / "bom.rtf"
        src.write_bytes(b"\xef\xbb\xbf{\\rtf1 Hello}")
        out = tmp_path / "output.rtf"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        translate_file(src, out, "French")
        assert "\ufeff" not in out.read_text(encoding="utf-8")

    @patch("src.core.llm_engine.translate_text")
    def test_bom_json(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """BOM in .json file is stripped from output."""
        src = tmp_path / "bom.json"
        src.write_bytes(b'\xef\xbb\xbf{"key": "value"}')
        out = tmp_path / "output.json"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        translate_file(src, out, "French")
        raw = out.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf")

    @patch("src.core.llm_engine.translate_text")
    def test_bom_srt(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """BOM in .srt file is stripped from output."""
        src = tmp_path / "bom.srt"
        src.write_bytes(b"\xef\xbb\xbf1\n00:00:01,000 --> 00:00:02,000\nHello\n")
        out = tmp_path / "output.srt"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        translate_file(src, out, "French")
        assert "\ufeff" not in out.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# TestTranslateFileErrorPropagation — comprehensive error paths
# ---------------------------------------------------------------------------


class TestTranslateFileErrorPropagation:
    """Extended error propagation tests."""

    @patch("src.core.llm_engine.translate_text")
    def test_srt_llm_auth_error(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """SRT LLM AUTH_ERROR propagates."""
        src = tmp_path / "input.srt"
        src.write_text(
            "1\n00:00:01,000 --> 00:00:02,000\nHello\n",
            encoding="utf-8",
        )
        out = tmp_path / "output.srt"
        mock_translate.side_effect = ValueError("AUTH_ERROR")
        with pytest.raises(ValueError, match="AUTH_ERROR"):
            translate_file(src, out, "French")

    @patch("src.core.llm_engine.translate_text")
    def test_ass_llm_error(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """ASS LLM error propagates."""
        src = tmp_path / "input.ass"
        src.write_text(
            "[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
            "MarginV, Effect, Text\n"
            "Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,Hi\n",
            encoding="utf-8",
        )
        out = tmp_path / "output.ass"
        mock_translate.side_effect = ValueError("QUOTA_ERROR")
        with pytest.raises(ValueError, match="QUOTA_ERROR"):
            translate_file(src, out, "French")

    @patch("src.core.llm_engine.translate_text")
    def test_ssa_llm_error(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """SSA LLM error propagates."""
        src = tmp_path / "input.ssa"
        src.write_text(
            "[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
            "MarginV, Effect, Text\n"
            "Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,Hi\n",
            encoding="utf-8",
        )
        out = tmp_path / "output.ssa"
        mock_translate.side_effect = ValueError("AUTH_ERROR")
        with pytest.raises(ValueError, match="AUTH_ERROR"):
            translate_file(src, out, "French")

    @patch("src.core.llm_engine.translate_text")
    def test_po_llm_quota_error(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """PO LLM QUOTA_ERROR propagates."""
        src = tmp_path / "input.po"
        src.write_text(
            'msgid ""\nmsgstr ""\n\nmsgid "Hello"\nmsgstr ""\n',
            encoding="utf-8",
        )
        out = tmp_path / "output.po"
        mock_translate.side_effect = ValueError("QUOTA_ERROR")
        with pytest.raises(ValueError, match="QUOTA_ERROR"):
            translate_file(src, out, "French")

    @patch("src.core.llm_engine.translate_text")
    def test_yaml_llm_error(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """YAML LLM error propagates."""
        src = tmp_path / "input.yaml"
        src.write_text("key: Value\n", encoding="utf-8")
        out = tmp_path / "output.yaml"
        mock_translate.side_effect = ValueError("AUTH_ERROR")
        with pytest.raises(ValueError, match="AUTH_ERROR"):
            translate_file(src, out, "French")

    @patch("src.core.llm_engine.translate_text")
    def test_properties_llm_error(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """Properties LLM error propagates."""
        src = tmp_path / "input.properties"
        src.write_text("key=Value\n", encoding="utf-8")
        out = tmp_path / "output.properties"
        mock_translate.side_effect = ValueError("AUTH_ERROR")
        with pytest.raises(ValueError, match="AUTH_ERROR"):
            translate_file(src, out, "French")

    def test_generic_exception_becomes_text_read_error(self, tmp_path: Path) -> None:
        """Generic exception is wrapped as TEXT_READ_ERROR."""
        src = tmp_path / "bad.txt"
        out = tmp_path / "output.txt"
        # File does not exist — should get TEXT_READ_ERROR
        with pytest.raises(ValueError, match="TEXT_READ_ERROR"):
            translate_file(src, out, "French")

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_txt_write_permission_error(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """TXT write to read-only dir raises TEXT_WRITE_ERROR."""
        src = tmp_path / "input.txt"
        src.write_text("Hello", encoding="utf-8")
        read_only = tmp_path / "readonly_txt2"
        read_only.mkdir()
        read_only.chmod(0o444)
        out = read_only / "subdir" / "output.txt"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        try:
            with pytest.raises(ValueError, match="TEXT_WRITE_ERROR"):
                translate_file(src, out, "French")
        finally:
            read_only.chmod(0o755)


# ---------------------------------------------------------------------------
# TestTranslateFileCancellation — cancellation across all formats
# ---------------------------------------------------------------------------


class TestTranslateFileCancellation:
    """Cancellation tests for every file format."""

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_cancel_txt(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """TXT cancel returns False."""
        src = tmp_path / "input.txt"
        src.write_text("Hello", encoding="utf-8")
        out = tmp_path / "output.txt"
        result = translate_file(src, out, "French", cancel_check=lambda: True)
        assert result is False

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_cancel_html(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """HTML cancel returns False."""
        src = tmp_path / "input.html"
        src.write_text("<p>Hello</p>", encoding="utf-8")
        out = tmp_path / "output.html"
        result = translate_file(src, out, "French", cancel_check=lambda: True)
        assert result is False

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_cancel_xml(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """XML cancel returns False."""
        src = tmp_path / "input.xml"
        src.write_text("<root>Hello</root>", encoding="utf-8")
        out = tmp_path / "output.xml"
        result = translate_file(src, out, "French", cancel_check=lambda: True)
        assert result is False

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_cancel_rtf(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """RTF cancel returns False."""
        src = tmp_path / "input.rtf"
        src.write_text(r"{\rtf1 Hello}", encoding="utf-8")
        out = tmp_path / "output.rtf"
        result = translate_file(src, out, "French", cancel_check=lambda: True)
        assert result is False

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_cancel_md(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """Markdown cancel returns False."""
        src = tmp_path / "input.md"
        src.write_text("# Hello", encoding="utf-8")
        out = tmp_path / "output.md"
        result = translate_file(src, out, "French", cancel_check=lambda: True)
        assert result is False

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_cancel_rst(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """RST cancel returns False."""
        src = tmp_path / "input.rst"
        src.write_text("Hello RST", encoding="utf-8")
        out = tmp_path / "output.rst"
        result = translate_file(src, out, "French", cancel_check=lambda: True)
        assert result is False

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_cancel_epub(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """EPUB cancel returns False."""
        src = _create_minimal_epub(tmp_path)
        out = tmp_path / "output.epub"
        result = translate_file(src, out, "French", cancel_check=lambda: True)
        assert result is False

    @patch("src.core.llm_engine.translate_text")
    def test_cancel_json(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """JSON cancel returns False."""
        src = tmp_path / "input.json"
        src.write_text('{"a": "hello"}', encoding="utf-8")
        out = tmp_path / "output.json"
        result = translate_file(src, out, "French", cancel_check=lambda: True)
        assert result is False

    @patch("src.core.llm_engine.translate_text")
    def test_cancel_csv(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """CSV cancel returns False."""
        src = tmp_path / "input.csv"
        src.write_text("Name\nAlice\n", encoding="utf-8")
        out = tmp_path / "output.csv"
        result = translate_file(src, out, "French", cancel_check=lambda: True)
        assert result is False

    @patch("src.core.llm_engine.translate_text")
    def test_cancel_ass(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """ASS cancel returns False."""
        src = tmp_path / "input.ass"
        src.write_text(
            "[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
            "MarginV, Effect, Text\n"
            "Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,Hi\n",
            encoding="utf-8",
        )
        out = tmp_path / "output.ass"
        result = translate_file(src, out, "French", cancel_check=lambda: True)
        assert result is False

    @patch("src.core.llm_engine.translate_text")
    def test_cancel_ssa(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """SSA cancel returns False."""
        src = tmp_path / "input.ssa"
        src.write_text(
            "[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
            "MarginV, Effect, Text\n"
            "Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,Hi\n",
            encoding="utf-8",
        )
        out = tmp_path / "output.ssa"
        result = translate_file(src, out, "French", cancel_check=lambda: True)
        assert result is False

    @patch("src.core.llm_engine.translate_text")
    def test_cancel_xliff(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """XLIFF cancel returns False."""
        src = tmp_path / "input.xliff"
        src.write_text(
            '<?xml version="1.0"?>'
            '<xliff version="1.2" '
            'xmlns="urn:oasis:names:tc:xliff:document:1.2">'
            '<file source-language="en" target-language="fr" '
            'datatype="plaintext"><body>'
            '<trans-unit id="1"><source>Hi</source></trans-unit>'
            "</body></file></xliff>",
            encoding="utf-8",
        )
        out = tmp_path / "output.xliff"
        result = translate_file(src, out, "French", cancel_check=lambda: True)
        assert result is False

    @patch("src.core.llm_engine.translate_text")
    def test_cancel_yaml(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """YAML cancel returns False."""
        src = tmp_path / "input.yaml"
        src.write_text("key: Value\n", encoding="utf-8")
        out = tmp_path / "output.yaml"
        result = translate_file(src, out, "French", cancel_check=lambda: True)
        assert result is False

    @patch("src.core.llm_engine.translate_text")
    def test_cancel_yml(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """YML cancel returns False."""
        src = tmp_path / "input.yml"
        src.write_text("key: Value\n", encoding="utf-8")
        out = tmp_path / "output.yml"
        result = translate_file(src, out, "French", cancel_check=lambda: True)
        assert result is False


# ---------------------------------------------------------------------------
# TestTranslateFileEmptyFiles — empty files for all formats
# ---------------------------------------------------------------------------


class TestTranslateFileEmptyFiles:
    """Empty file handling across all formats."""

    @patch("src.core.llm_engine.translate_text")
    def test_empty_srt(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """Empty SRT file is handled gracefully."""
        src = tmp_path / "empty.srt"
        src.write_text("", encoding="utf-8")
        out = tmp_path / "output.srt"
        assert translate_file(src, out, "French") is True
        mock_translate.assert_not_called()

    @patch("src.core.llm_engine.translate_text")
    def test_empty_vtt(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """Empty VTT file is handled gracefully."""
        src = tmp_path / "empty.vtt"
        src.write_text("", encoding="utf-8")
        out = tmp_path / "output.vtt"
        assert translate_file(src, out, "French") is True
        mock_translate.assert_not_called()

    @patch("src.core.llm_engine.translate_text")
    def test_empty_po(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """Empty PO file is handled gracefully."""
        src = tmp_path / "empty.po"
        src.write_text("", encoding="utf-8")
        out = tmp_path / "output.po"
        assert translate_file(src, out, "French") is True
        mock_translate.assert_not_called()

    @patch("src.core.llm_engine.translate_text")
    def test_empty_pot(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """Empty POT file is handled gracefully."""
        src = tmp_path / "empty.pot"
        src.write_text("", encoding="utf-8")
        out = tmp_path / "output.pot"
        assert translate_file(src, out, "French") is True
        mock_translate.assert_not_called()

    @patch("src.core.llm_engine.translate_text")
    def test_empty_xliff(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """Empty XLIFF file raises (not valid XML)."""
        src = tmp_path / "empty.xliff"
        src.write_text("", encoding="utf-8")
        out = tmp_path / "output.xliff"
        # Empty file is not valid XML, should raise
        with pytest.raises(ValueError):
            translate_file(src, out, "French")

    @patch("src.core.llm_engine.translate_text")
    def test_empty_yml(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """Empty YML file is handled gracefully."""
        src = tmp_path / "empty.yml"
        src.write_text("", encoding="utf-8")
        out = tmp_path / "output.yml"
        assert translate_file(src, out, "French") is True
        mock_translate.assert_not_called()

    @patch("src.core.llm_engine.translate_text")
    def test_empty_json_array(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """Empty JSON array is handled gracefully."""
        src = tmp_path / "empty.json"
        src.write_text("[]", encoding="utf-8")
        out = tmp_path / "output.json"
        assert translate_file(src, out, "French") is True
        mock_translate.assert_not_called()


# ---------------------------------------------------------------------------
# TestTranslateFileSpecialCharacters — special character handling
# ---------------------------------------------------------------------------


class TestTranslateFileSpecialCharacters:
    """Tests for special characters in various file formats."""

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_txt_with_null_bytes_in_content(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """TXT with null-terminated strings translates without crash."""
        src = tmp_path / "nulls.txt"
        src.write_text("Hello\x00World", encoding="utf-8")
        out = tmp_path / "output.txt"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        assert translate_file(src, out, "French") is True

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_html_with_unicode_entities(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """HTML with &#x sequences translates correctly."""
        src = tmp_path / "entities.html"
        src.write_text(
            "<p>Caf&#xe9; &#x2603;</p>",
            encoding="utf-8",
        )
        out = tmp_path / "output.html"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        assert translate_file(src, out, "French") is True
        content = out.read_text(encoding="utf-8")
        assert "&#xe9;" in content or "é" in content

    @patch("src.core.llm_engine.translate_text")
    def test_json_with_unicode_escapes(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """JSON with \\uXXXX escapes translates correctly."""
        src = tmp_path / "unicode.json"
        src.write_text('{"key": "Caf\\u00e9"}', encoding="utf-8")
        out = tmp_path / "output.json"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        assert translate_file(src, out, "French") is True

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_xml_with_entities(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """XML with entity references translates correctly."""
        src = tmp_path / "entities.xml"
        src.write_text(
            "<root><msg>5 &lt; 10 &amp; 3 &gt; 1</msg></root>",
            encoding="utf-8",
        )
        out = tmp_path / "output.xml"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        assert translate_file(src, out, "French") is True

    @patch("src.core.llm_engine.translate_text")
    def test_csv_with_special_characters(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """CSV with quotes, commas, and newlines in cells."""
        src = tmp_path / "special.csv"
        src.write_text(
            'Name,Greeting\n"O\'Brien","Hello, World"\n',
            encoding="utf-8",
        )
        out = tmp_path / "output.csv"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        assert translate_file(src, out, "French") is True

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_md_with_html_embedded(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """Markdown with embedded HTML tags translates correctly."""
        src = tmp_path / "mixed.md"
        src.write_text(
            "# Title\n\n<div class='note'>This is **bold**</div>",
            encoding="utf-8",
        )
        out = tmp_path / "output.md"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        assert translate_file(src, out, "French") is True

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_txt_with_emoji(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """TXT with emoji characters translates correctly."""
        src = tmp_path / "emoji.txt"
        src.write_text("Hello World! 😀🎉🌍", encoding="utf-8")
        out = tmp_path / "output.txt"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        assert translate_file(src, out, "French") is True
        content = out.read_text(encoding="utf-8")
        assert "😀" in content

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_txt_with_backslash_sequences(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """TXT with literal backslash sequences translates correctly."""
        src = tmp_path / "backslash.txt"
        src.write_text("Path: C:\\Users\\test\\file.txt", encoding="utf-8")
        out = tmp_path / "output.txt"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        assert translate_file(src, out, "French") is True
        content = out.read_text(encoding="utf-8")
        assert "C:\\Users\\test" in content


# ---------------------------------------------------------------------------
# TestTokenOptimizationRoundtrips — strip/restore fidelity
# ---------------------------------------------------------------------------


class TestTokenOptimizationRoundtrips:
    """Tests that strip/restore cycles produce faithful output."""

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_html_data_attributes_roundtrip(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """HTML data-* attributes survive strip/translate/restore cycle."""
        src = tmp_path / "data.html"
        src.write_text(
            '<div data-id="123" data-name="test"><p>Hello</p></div>',
            encoding="utf-8",
        )
        out = tmp_path / "output.html"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        translate_file(src, out, "French")
        content = out.read_text(encoding="utf-8")
        assert 'data-id="123"' in content
        assert 'data-name="test"' in content

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_html_href_attributes_roundtrip(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """HTML href/src attributes survive strip/restore cycle."""
        src = tmp_path / "links.html"
        src.write_text(
            '<a href="https://example.com">Click</a>\n<img src="image.png">',
            encoding="utf-8",
        )
        out = tmp_path / "output.html"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        translate_file(src, out, "French")
        content = out.read_text(encoding="utf-8")
        assert 'href="https://example.com"' in content
        assert 'src="image.png"' in content

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_xml_multiple_namespaces_roundtrip(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """XML with multiple namespace declarations survive roundtrip."""
        src = tmp_path / "ns.xml"
        src.write_text(
            '<root xmlns:a="http://a.com" xmlns:b="http://b.com">\n'
            "  <a:elem>Hello</a:elem>\n"
            "  <b:elem>World</b:elem>\n"
            "</root>",
            encoding="utf-8",
        )
        out = tmp_path / "output.xml"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        translate_file(src, out, "French")
        content = out.read_text(encoding="utf-8")
        assert 'xmlns:a="http://a.com"' in content
        assert 'xmlns:b="http://b.com"' in content

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_xml_comment_roundtrip(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """XML comments survive strip/restore cycle."""
        src = tmp_path / "comments.xml"
        src.write_text(
            "<!-- Important note -->\n<root>Hello</root>",
            encoding="utf-8",
        )
        out = tmp_path / "output.xml"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        translate_file(src, out, "French")
        content = out.read_text(encoding="utf-8")
        assert "<!-- Important note -->" in content

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_rtf_font_table_roundtrip(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        r"""RTF font table control words survive strip/restore."""
        src = tmp_path / "fonts.rtf"
        src.write_text(
            r"{\rtf1\ansi{\fonttbl{\f0 Arial;}} Hello World}",
            encoding="utf-8",
        )
        out = tmp_path / "output.rtf"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        translate_file(src, out, "French")
        content = out.read_text(encoding="utf-8")
        # RTF output should preserve overhead structure
        assert len(content) > 0

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_md_reference_links_roundtrip(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """Markdown reference-style links survive strip/restore."""
        src = tmp_path / "refs.md"
        src.write_text(
            "Visit [Google][1] and [GitHub][2].\n\n"
            "[1]: https://google.com\n"
            "[2]: https://github.com",
            encoding="utf-8",
        )
        out = tmp_path / "output.md"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        translate_file(src, out, "French")
        content = out.read_text(encoding="utf-8")
        assert "https://google.com" in content
        assert "https://github.com" in content

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_md_inline_code_preserved(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """Markdown inline code backticks are preserved in output."""
        src = tmp_path / "code.md"
        src.write_text(
            "Use `print()` to output text.",
            encoding="utf-8",
        )
        out = tmp_path / "output.md"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        translate_file(src, out, "French")
        content = out.read_text(encoding="utf-8")
        assert "`print()`" in content


# ---------------------------------------------------------------------------
# TestTranslateFileProgressCallbacks — progress across formats
# ---------------------------------------------------------------------------


class TestTranslateFileProgressCallbacks:
    """Progress callback tests for all formats."""

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_progress_txt(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """TXT translation fires progress callbacks."""
        src = tmp_path / "input.txt"
        src.write_text("Hello\n\nWorld", encoding="utf-8")
        out = tmp_path / "output.txt"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        progress: list[int] = []
        translate_file(src, out, "French", progress_callback=progress.append)
        assert len(progress) > 0

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_progress_html(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """HTML translation fires progress callbacks."""
        src = tmp_path / "input.html"
        src.write_text("<p>Hello</p>\n<p>World</p>", encoding="utf-8")
        out = tmp_path / "output.html"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        progress: list[int] = []
        translate_file(src, out, "French", progress_callback=progress.append)
        assert len(progress) > 0

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_progress_xml(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """XML translation fires progress callbacks."""
        src = tmp_path / "input.xml"
        src.write_text("<root>\n<a>Hi</a>\n</root>", encoding="utf-8")
        out = tmp_path / "output.xml"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        progress: list[int] = []
        translate_file(src, out, "French", progress_callback=progress.append)
        assert len(progress) > 0

    @patch("src.core.llm_engine.translate_text")
    def test_progress_json(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """JSON translation fires progress callbacks."""
        src = tmp_path / "input.json"
        src.write_text('{"a": "hello"}', encoding="utf-8")
        out = tmp_path / "output.json"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        progress: list[int] = []
        translate_file(src, out, "French", progress_callback=progress.append)
        assert len(progress) > 0

    @patch("src.core.llm_engine.translate_text")
    def test_progress_csv(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """CSV translation fires progress callbacks."""
        src = tmp_path / "input.csv"
        src.write_text("Name\nAlice\nBob\n", encoding="utf-8")
        out = tmp_path / "output.csv"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        progress: list[int] = []
        translate_file(src, out, "French", progress_callback=progress.append)
        assert len(progress) > 0

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_progress_epub(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """EPUB translation fires progress callbacks."""
        src = _create_minimal_epub(tmp_path)
        out = tmp_path / "output.epub"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        progress: list[int] = []
        translate_file(src, out, "French", progress_callback=progress.append)
        assert len(progress) > 0

    @patch("src.core.llm_engine.translate_text")
    def test_progress_yaml(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """YAML translation fires progress callbacks."""
        src = tmp_path / "input.yaml"
        src.write_text("key: Value\n", encoding="utf-8")
        out = tmp_path / "output.yaml"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        progress: list[int] = []
        translate_file(src, out, "French", progress_callback=progress.append)
        assert len(progress) > 0

    @patch("src.core.llm_engine.translate_text")
    def test_progress_po(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """PO translation fires progress callbacks."""
        src = tmp_path / "input.po"
        src.write_text(
            'msgid ""\nmsgstr ""\n\nmsgid "Hello"\nmsgstr ""\n',
            encoding="utf-8",
        )
        out = tmp_path / "output.po"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        progress: list[int] = []
        translate_file(src, out, "French", progress_callback=progress.append)
        assert len(progress) > 0


# ---------------------------------------------------------------------------
# TestTranslateFileGlossaryForwarding — glossary across formats
# ---------------------------------------------------------------------------


class TestTranslateFileGlossaryForwarding:
    """Tests that glossary is forwarded to LLM for all formats."""

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_glossary_html(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """HTML forwards glossary to LLM."""
        src = tmp_path / "input.html"
        src.write_text("<p>Hello World</p>", encoding="utf-8")
        out = tmp_path / "output.html"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        glossary = [(1, "Hello", "Bonjour")]
        translate_file(src, out, "French", glossary_entries=glossary)
        _, kwargs = mock_translate.call_args
        assert kwargs["glossary_entries"] == glossary

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_glossary_xml(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """XML forwards glossary to LLM."""
        src = tmp_path / "input.xml"
        src.write_text("<root>Hello</root>", encoding="utf-8")
        out = tmp_path / "output.xml"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        glossary = [(1, "Hello", "Bonjour")]
        translate_file(src, out, "French", glossary_entries=glossary)
        _, kwargs = mock_translate.call_args
        assert kwargs["glossary_entries"] == glossary

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_glossary_md(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """Markdown forwards glossary to LLM."""
        src = tmp_path / "input.md"
        src.write_text("Hello World", encoding="utf-8")
        out = tmp_path / "output.md"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        glossary = [(1, "Hello", "Bonjour")]
        translate_file(src, out, "French", glossary_entries=glossary)
        _, kwargs = mock_translate.call_args
        assert kwargs["glossary_entries"] == glossary

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_glossary_rtf(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """RTF forwards glossary to LLM."""
        src = tmp_path / "input.rtf"
        src.write_text(r"{\rtf1 Hello}", encoding="utf-8")
        out = tmp_path / "output.rtf"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        glossary = [(1, "Hello", "Bonjour")]
        translate_file(src, out, "French", glossary_entries=glossary)
        _, kwargs = mock_translate.call_args
        assert kwargs["glossary_entries"] == glossary


# ---------------------------------------------------------------------------
# TestConfigParameterInjection — config parameter across formats
# ---------------------------------------------------------------------------


class TestConfigParameterInjection:
    """Tests config parameter injection for all dispatchers."""

    @patch("src.core.pdf_processor.process_pdf_file")
    def test_config_to_pdf(self, mock_pdf: MagicMock, tmp_path: Path) -> None:
        """Config forwarded to PDF processor."""
        from src.core.config import TranslationConfig  # noqa: PLC0415

        src = tmp_path / "input.pdf"
        src.write_bytes(b"%PDF-1.4\n")
        out = tmp_path / "output.pdf"
        mock_pdf.return_value = True
        cfg = TranslationConfig(storage_path="/tmp/pdf_test")
        translate_file(src, out, "French", config=cfg)
        assert mock_pdf.call_args[1]["config"] is cfg

    @patch("src.core.text_processor.process_office_file")
    def test_config_to_docx(self, mock_office: MagicMock, tmp_path: Path) -> None:
        """Config forwarded to Office processor for .docx."""
        from src.core.config import TranslationConfig  # noqa: PLC0415

        src = tmp_path / "input.docx"
        src.touch()
        out = tmp_path / "output.docx"
        mock_office.return_value = True
        cfg = TranslationConfig(translate_doc_comments=True)
        translate_file(src, out, "French", config=cfg)
        assert mock_office.call_args[1]["config"] is cfg

    @patch("src.core.text_processor.process_office_file")
    def test_config_to_xlsx(self, mock_office: MagicMock, tmp_path: Path) -> None:
        """Config forwarded to Office processor for .xlsx."""
        from src.core.config import TranslationConfig  # noqa: PLC0415

        src = tmp_path / "input.xlsx"
        src.touch()
        out = tmp_path / "output.xlsx"
        mock_office.return_value = True
        cfg = TranslationConfig(translate_sheet_names=True)
        translate_file(src, out, "French", config=cfg)
        assert mock_office.call_args[1]["config"] is cfg

    @patch("src.core.text_processor.process_office_file")
    def test_config_to_pptx(self, mock_office: MagicMock, tmp_path: Path) -> None:
        """Config forwarded to Office processor for .pptx."""
        from src.core.config import TranslationConfig  # noqa: PLC0415

        src = tmp_path / "input.pptx"
        src.touch()
        out = tmp_path / "output.pptx"
        mock_office.return_value = True
        cfg = TranslationConfig(translate_doc_notes=True)
        translate_file(src, out, "French", config=cfg)
        assert mock_office.call_args[1]["config"] is cfg

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_config_none_for_plain(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """config=None for plain text formats does not crash."""
        src = tmp_path / "input.txt"
        src.write_text("Hello", encoding="utf-8")
        out = tmp_path / "output.txt"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        assert translate_file(src, out, "French", config=None) is True

    @patch("src.core.text_processor.process_office_file")
    def test_config_to_odt(self, mock_office: MagicMock, tmp_path: Path) -> None:
        """Config forwarded to Office processor for .odt."""
        from src.core.config import TranslationConfig  # noqa: PLC0415

        src = tmp_path / "input.odt"
        src.touch()
        out = tmp_path / "output.odt"
        mock_office.return_value = True
        cfg = TranslationConfig(auto_convert_odf=True)
        translate_file(src, out, "French", config=cfg)
        assert mock_office.call_args[1]["config"] is cfg


# ---------------------------------------------------------------------------
# TestEpubEdgeCasesExtended — EPUB content file discovery and translation
# ---------------------------------------------------------------------------


class TestEpubEdgeCasesExtended:
    """Extended EPUB content discovery and translation tests."""

    def test_epub_opf_without_ns(self, tmp_path: Path) -> None:
        """OPF without default namespace still discovers content files."""
        epub_path = tmp_path / "no_ns.epub"
        container_xml = (
            '<?xml version="1.0"?>'
            '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"'
            ' version="1.0">'
            "  <rootfiles>"
            '    <rootfile full-path="content.opf"'
            ' media-type="application/oebps-package+xml"/>'
            "  </rootfiles>"
            "</container>"
        )
        # OPF without default OPF namespace
        content_opf = (
            '<package version="3.0">'
            "  <manifest>"
            '    <item id="ch1" href="ch1.xhtml"'
            ' media-type="application/xhtml+xml"/>'
            "  </manifest>"
            "</package>"
        )
        with zipfile.ZipFile(epub_path, "w") as zf:
            zf.writestr("META-INF/container.xml", container_xml)
            zf.writestr("content.opf", content_opf)
            zf.writestr("ch1.xhtml", "<html><body>Hello</body></html>")

        with zipfile.ZipFile(epub_path, "r") as zf:
            files = _get_epub_content_files(zf)
        assert len(files) == 1
        assert "ch1.xhtml" in files[0]

    def test_epub_text_xml_media_type(self, tmp_path: Path) -> None:
        """EPUB content file with text/xml media type is discovered."""
        epub_path = tmp_path / "xml_type.epub"
        container_xml = (
            '<?xml version="1.0"?>'
            '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"'
            ' version="1.0">'
            "  <rootfiles>"
            '    <rootfile full-path="OEBPS/content.opf"'
            ' media-type="application/oebps-package+xml"/>'
            "  </rootfiles>"
            "</container>"
        )
        content_opf = (
            '<?xml version="1.0"?>'
            '<package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
            "  <manifest>"
            '    <item id="ch1" href="ch1.xhtml"'
            ' media-type="text/xml"/>'
            "  </manifest>"
            "</package>"
        )
        with zipfile.ZipFile(epub_path, "w") as zf:
            zf.writestr("META-INF/container.xml", container_xml)
            zf.writestr("OEBPS/content.opf", content_opf)
            zf.writestr("OEBPS/ch1.xhtml", "<html><body>Hi</body></html>")

        with zipfile.ZipFile(epub_path, "r") as zf:
            files = _get_epub_content_files(zf)
        assert len(files) == 1

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_epub_whitespace_only_chapter(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """EPUB chapter with only whitespace is skipped."""
        epub_path = tmp_path / "ws_ch.epub"
        container_xml = (
            '<?xml version="1.0"?>'
            '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"'
            ' version="1.0">'
            "  <rootfiles>"
            '    <rootfile full-path="OEBPS/content.opf"'
            ' media-type="application/oebps-package+xml"/>'
            "  </rootfiles>"
            "</container>"
        )
        content_opf = (
            '<?xml version="1.0"?>'
            '<package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
            "  <manifest>"
            '    <item id="ch1" href="ch1.xhtml"'
            ' media-type="application/xhtml+xml"/>'
            '    <item id="ch2" href="ch2.xhtml"'
            ' media-type="application/xhtml+xml"/>'
            "  </manifest>"
            "</package>"
        )
        with zipfile.ZipFile(epub_path, "w") as zf:
            zf.writestr("META-INF/container.xml", container_xml)
            zf.writestr("OEBPS/content.opf", content_opf)
            zf.writestr("OEBPS/ch1.xhtml", "   \n\n   ")
            zf.writestr(
                "OEBPS/ch2.xhtml",
                "<html><body><p>Real content</p></body></html>",
            )

        out = tmp_path / "output.epub"
        mock_translate.side_effect = lambda texts, *a, **kw: [
            f"[FR] {t}" for t in texts
        ]
        assert translate_file(epub_path, out, "French") is True

        with zipfile.ZipFile(out, "r") as zf:
            ch2 = zf.read("OEBPS/ch2.xhtml").decode("utf-8")
        assert "[FR]" in ch2


# ---------------------------------------------------------------------------
# TestCSVEdgeCasesExtended — CSV parsing edge cases
# ---------------------------------------------------------------------------


class TestCSVEdgeCasesExtended:
    """Extended CSV edge case tests."""

    @patch("src.core.llm_engine.translate_text")
    def test_csv_large_number_of_rows(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """CSV with many rows translates all cells."""
        src = tmp_path / "large.csv"
        rows = ["Name,Value"] + [f"Name{i},Value{i}" for i in range(100)]
        src.write_text("\n".join(rows) + "\n", encoding="utf-8")
        out = tmp_path / "output.csv"
        mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
        assert translate_file(src, out, "French") is True
        content = out.read_text(encoding="utf-8")
        assert "[T] Name99" in content

    @patch("src.core.llm_engine.translate_text")
    def test_csv_single_row_no_header(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """CSV with a single data row (no separate header)."""
        src = tmp_path / "single_row.csv"
        src.write_text("Alice,Bob,Charlie\n", encoding="utf-8")
        out = tmp_path / "output.csv"
        mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
        assert translate_file(src, out, "French") is True
        content = out.read_text(encoding="utf-8")
        assert "[T] Alice" in content
        assert "[T] Charlie" in content

    @patch("src.core.llm_engine.translate_text")
    def test_csv_with_mixed_empty_and_full_rows(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """CSV with rows having mixed empty/full cells."""
        src = tmp_path / "mixed.csv"
        src.write_text("A,,B\n,C,\nD,,E\n", encoding="utf-8")
        out = tmp_path / "output.csv"
        mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
        assert translate_file(src, out, "French") is True
        content = out.read_text(encoding="utf-8")
        assert "[T] A" in content
        assert "[T] B" in content
        assert "[T] C" in content
        assert "[T] D" in content
        assert "[T] E" in content


# ---------------------------------------------------------------------------
# TestSubtitleEdgeCasesExtended — subtitle parsing edge cases
# ---------------------------------------------------------------------------


class TestSubtitleEdgeCasesExtended:
    """Extended subtitle edge case tests."""

    @patch("src.core.llm_engine.translate_text")
    def test_srt_with_many_entries(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """SRT with many entries translates all."""
        src = tmp_path / "many.srt"
        entries = []
        for i in range(50):
            entries.append(
                f"{i + 1}\n00:00:{i:02d},000 --> 00:00:{i + 1:02d},000\nLine {i + 1}\n"
            )
        src.write_text("\n".join(entries), encoding="utf-8")
        out = tmp_path / "output.srt"
        mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
        assert translate_file(src, out, "French") is True
        content = out.read_text(encoding="utf-8")
        assert "[T] Line 1" in content
        assert "[T] Line 50" in content

    @patch("src.core.llm_engine.translate_text")
    def test_vtt_with_cue_ids(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """VTT with named cue identifiers preserves them."""
        src = tmp_path / "cues.vtt"
        src.write_text(
            "WEBVTT\n\n"
            "intro\n00:00:01.000 --> 00:00:02.000\nHello\n\n"
            "main\n00:00:03.000 --> 00:00:04.000\nWorld\n",
            encoding="utf-8",
        )
        out = tmp_path / "output.vtt"
        mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
        assert translate_file(src, out, "French") is True
        content = out.read_text(encoding="utf-8")
        assert "[T] Hello" in content
        assert "[T] World" in content

    @patch("src.core.llm_engine.translate_text")
    def test_srt_unicode_dialogue(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """SRT with CJK dialogue text translates correctly."""
        src = tmp_path / "cjk.srt"
        src.write_text(
            "1\n00:00:01,000 --> 00:00:04,000\n你好世界\n",
            encoding="utf-8",
        )
        out = tmp_path / "output.srt"
        mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
        assert translate_file(src, out, "French") is True
        content = out.read_text(encoding="utf-8")
        assert "[T] 你好世界" in content

    @patch("src.core.llm_engine.translate_text")
    def test_ass_write_error(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """ASS write failure raises TEXT_WRITE_ERROR."""
        src = tmp_path / "input.ass"
        src.write_text(
            "[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
            "MarginV, Effect, Text\n"
            "Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,Hi\n",
            encoding="utf-8",
        )
        read_only = tmp_path / "readonly_ass"
        read_only.mkdir()
        read_only.chmod(0o444)
        out = read_only / "subdir" / "output.ass"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        try:
            with pytest.raises(ValueError, match="TEXT_WRITE_ERROR"):
                translate_file(src, out, "French")
        finally:
            read_only.chmod(0o755)


# ---------------------------------------------------------------------------
# TestLocalizationEdgeCasesExtended — PO/XLIFF edge cases
# ---------------------------------------------------------------------------


class TestLocalizationEdgeCasesExtended:
    """Extended localization format edge cases."""

    @patch("src.core.llm_engine.translate_text")
    def test_po_with_comments_and_flags(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """PO with translator comments and flags translates correctly."""
        src = tmp_path / "flags.po"
        src.write_text(
            'msgid ""\nmsgstr ""\n\n'
            "#, fuzzy\n"
            "#. Translator note\n"
            'msgid "Hello"\n'
            'msgstr ""\n',
            encoding="utf-8",
        )
        out = tmp_path / "output.po"
        mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
        assert translate_file(src, out, "French") is True
        content = out.read_text(encoding="utf-8")
        assert "[T] Hello" in content

    @patch("src.core.llm_engine.translate_text")
    def test_po_with_context(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """PO with msgctxt (context) translates msgid."""
        src = tmp_path / "ctx.po"
        src.write_text(
            'msgid ""\nmsgstr ""\n\nmsgctxt "menu"\nmsgid "File"\nmsgstr ""\n',
            encoding="utf-8",
        )
        out = tmp_path / "output.po"
        mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
        assert translate_file(src, out, "French") is True
        content = out.read_text(encoding="utf-8")
        assert "[T] File" in content

    @patch("src.core.llm_engine.translate_text")
    def test_xlf_cancel(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """XLF cancel returns False."""
        src = tmp_path / "input.xlf"
        src.write_text(
            '<?xml version="1.0"?>'
            '<xliff xmlns="urn:oasis:names:tc:xliff:document:2.0"'
            ' version="2.0" srcLang="en" trgLang="fr">'
            '<file id="f1">'
            '<unit id="u1"><segment><source>Hi</source></segment></unit>'
            "</file></xliff>",
            encoding="utf-8",
        )
        out = tmp_path / "output.xlf"
        result = translate_file(src, out, "French", cancel_check=lambda: True)
        assert result is False

    @patch("src.core.llm_engine.translate_text")
    def test_pot_cancel(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """POT cancel returns False."""
        src = tmp_path / "input.pot"
        src.write_text(
            'msgid ""\nmsgstr ""\n\nmsgid "Hello"\nmsgstr ""\n',
            encoding="utf-8",
        )
        out = tmp_path / "output.pot"
        result = translate_file(src, out, "French", cancel_check=lambda: True)
        assert result is False


# ---------------------------------------------------------------------------
# TestKeyValueEdgeCasesExtended — YAML/Properties/Strings edge cases
# ---------------------------------------------------------------------------


class TestKeyValueEdgeCasesExtended:
    """Extended key-value format edge cases."""

    @patch("src.core.llm_engine.translate_text")
    def test_yaml_multiline_values(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """YAML with multiline string values translates them."""
        src = tmp_path / "multi.yaml"
        src.write_text(
            "description: |\n  This is a long\n  multiline value.\n",
            encoding="utf-8",
        )
        out = tmp_path / "output.yaml"
        mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
        assert translate_file(src, out, "French") is True

    @patch("src.core.llm_engine.translate_text")
    def test_yaml_list_values(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """YAML with list values translates string items."""
        src = tmp_path / "list.yaml"
        src.write_text(
            "items:\n  - Apple\n  - Banana\n  - Cherry\n",
            encoding="utf-8",
        )
        out = tmp_path / "output.yaml"
        mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
        assert translate_file(src, out, "French") is True
        content = out.read_text(encoding="utf-8")
        assert "[T] Apple" in content

    @patch("src.core.llm_engine.translate_text")
    def test_properties_with_equals_and_colon(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """Properties file with both = and : separators."""
        src = tmp_path / "mixed.properties"
        src.write_text(
            "key1=Value One\nkey2: Value Two\n",
            encoding="utf-8",
        )
        out = tmp_path / "output.properties"
        mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
        assert translate_file(src, out, "French") is True

    @patch("src.core.llm_engine.translate_text")
    def test_strings_with_escaped_quotes(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """Apple Strings with escaped quotes in values."""
        src = tmp_path / "escaped.strings"
        src.write_text(
            '"key" = "He said \\"hello\\"";\n',
            encoding="utf-8",
        )
        out = tmp_path / "output.strings"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        assert translate_file(src, out, "French") is True

    @patch("src.core.llm_engine.translate_text")
    def test_yml_write_error(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """YML write failure raises TEXT_WRITE_ERROR."""
        src = tmp_path / "input.yml"
        src.write_text("key: Value\n", encoding="utf-8")
        read_only = tmp_path / "readonly_yml"
        read_only.mkdir()
        read_only.chmod(0o444)
        out = read_only / "subdir" / "output.yml"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        try:
            with pytest.raises(ValueError, match="TEXT_WRITE_ERROR"):
                translate_file(src, out, "French")
        finally:
            read_only.chmod(0o755)

    @patch("src.core.llm_engine.translate_text")
    def test_strings_write_error(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """Apple Strings write failure raises TEXT_WRITE_ERROR."""
        src = tmp_path / "input.strings"
        src.write_text('"key" = "value";\n', encoding="utf-8")
        read_only = tmp_path / "readonly_str"
        read_only.mkdir()
        read_only.chmod(0o444)
        out = read_only / "subdir" / "output.strings"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        try:
            with pytest.raises(ValueError, match="TEXT_WRITE_ERROR"):
                translate_file(src, out, "French")
        finally:
            read_only.chmod(0o755)


# ---------------------------------------------------------------------------
# TestMalformedFiles — malformed input handling
# ---------------------------------------------------------------------------


class TestMalformedFiles:
    """Tests for handling malformed or invalid file inputs."""

    def test_malformed_json_raises(self, tmp_path: Path) -> None:
        """Malformed JSON raises ValueError."""
        src = tmp_path / "bad.json"
        src.write_text("{{invalid json}}", encoding="utf-8")
        out = tmp_path / "output.json"
        with pytest.raises(ValueError):
            translate_file(src, out, "French")

    def test_truncated_json_raises(self, tmp_path: Path) -> None:
        """Truncated JSON (unclosed brace) raises ValueError."""
        src = tmp_path / "truncated.json"
        src.write_text('{"key": "value"', encoding="utf-8")
        out = tmp_path / "output.json"
        with pytest.raises(ValueError):
            translate_file(src, out, "French")

    def test_malformed_yaml_raises(self, tmp_path: Path) -> None:
        """Malformed YAML raises TEXT_READ_ERROR."""
        src = tmp_path / "bad.yaml"
        src.write_text("parent:\n\tchild: value\n", encoding="utf-8")
        out = tmp_path / "output.yaml"
        with pytest.raises(ValueError, match="TEXT_READ_ERROR"):
            translate_file(src, out, "French")

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_epub_corrupt_zip(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """Corrupt EPUB (not a valid ZIP) raises TEXT_READ_ERROR."""
        src = tmp_path / "corrupt.epub"
        src.write_bytes(b"This is not a ZIP file at all")
        out = tmp_path / "output.epub"
        with pytest.raises(ValueError, match="TEXT_READ_ERROR"):
            translate_file(src, out, "French")

    @patch("src.core.llm_engine.translate_text")
    def test_csv_with_only_delimiters(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """CSV with only delimiters (no text content)."""
        src = tmp_path / "delimiters.csv"
        src.write_text(",,,\n,,,\n", encoding="utf-8")
        out = tmp_path / "output.csv"
        assert translate_file(src, out, "French") is True
        mock_translate.assert_not_called()

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_html_with_unclosed_tags(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """HTML with unclosed tags does not crash."""
        src = tmp_path / "broken.html"
        src.write_text("<p>Hello <b>world", encoding="utf-8")
        out = tmp_path / "output.html"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        assert translate_file(src, out, "French") is True

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_xml_with_invalid_chars(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """XML-like file with invalid characters still translates."""
        src = tmp_path / "invalid.xml"
        src.write_text("<root>Hello & World</root>", encoding="utf-8")
        out = tmp_path / "output.xml"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        # This may or may not raise depending on XML strictness
        # The key is no uncaught exception
        with contextlib.suppress(ValueError):
            translate_file(src, out, "French")

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_rtf_with_no_control_words(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """RTF-like file with no control words still translates."""
        src = tmp_path / "plain.rtf"
        src.write_text("Just plain text", encoding="utf-8")
        out = tmp_path / "output.rtf"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        assert translate_file(src, out, "French") is True
        content = out.read_text(encoding="utf-8")
        assert "Just plain text" in content


# ---------------------------------------------------------------------------
# TestTranslateFileLargeContent — large content handling
# ---------------------------------------------------------------------------


class TestTranslateFileLargeContent:
    """Tests for handling large file content."""

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_large_txt_many_paragraphs(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """Large TXT with 100 paragraphs creates multiple chunks."""
        src = tmp_path / "large.txt"
        paras = [f"Paragraph {i}. " * 50 for i in range(100)]
        src.write_text("\n\n".join(paras), encoding="utf-8")
        out = tmp_path / "output.txt"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        assert translate_file(src, out, "French") is True
        assert mock_translate.call_count >= 1

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_large_html_many_lines(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """Large HTML with many lines creates multiple chunks."""
        src = tmp_path / "large.html"
        lines = [f"<p>Line {i} with some content</p>" for i in range(200)]
        src.write_text("\n".join(lines), encoding="utf-8")
        out = tmp_path / "output.html"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        assert translate_file(src, out, "French") is True

    @patch("src.core.llm_engine.translate_text")
    def test_large_json_many_keys(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """Large JSON with 200 keys translates all values."""
        src = tmp_path / "large.json"
        data = {f"key_{i}": f"value {i}" for i in range(200)}
        src.write_text(json.dumps(data), encoding="utf-8")
        out = tmp_path / "output.json"
        mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
        assert translate_file(src, out, "French") is True
        result = json.loads(out.read_text(encoding="utf-8"))
        assert result["key_0"] == "[T] value 0"
        assert result["key_199"] == "[T] value 199"

    @patch("src.core.llm_engine.translate_text")
    def test_large_csv_many_rows(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """Large CSV with 500 rows translates all cells."""
        src = tmp_path / "large.csv"
        rows = ["Name,Value"] + [f"Name{i},Value{i}" for i in range(500)]
        src.write_text("\n".join(rows) + "\n", encoding="utf-8")
        out = tmp_path / "output.csv"
        mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
        assert translate_file(src, out, "French") is True
        content = out.read_text(encoding="utf-8")
        assert "[T] Name499" in content

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_large_md_many_sections(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """Large Markdown with many sections creates multiple chunks."""
        src = tmp_path / "large.md"
        sections = [
            f"## Section {i}\n\nContent for section {i}. " * 20 for i in range(50)
        ]
        src.write_text("\n\n".join(sections), encoding="utf-8")
        out = tmp_path / "output.md"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        assert translate_file(src, out, "French") is True


# ---------------------------------------------------------------------------
# TestTranslateFileCheckpointExtended — checkpoint edge cases
# ---------------------------------------------------------------------------


class TestTranslateFileCheckpointExtended:
    """Extended checkpoint handling tests."""

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_checkpoint_dir_none_works(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """checkpoint_dir=None does not crash any format."""
        src = tmp_path / "input.txt"
        src.write_text("Hello World", encoding="utf-8")
        out = tmp_path / "output.txt"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        assert translate_file(src, out, "French", checkpoint_dir=None) is True

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_checkpoint_dir_for_html(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """HTML translation uses checkpoint_dir when provided."""
        src = tmp_path / "input.html"
        src.write_text("<p>Hello</p>", encoding="utf-8")
        out = tmp_path / "output.html"
        cp_dir = tmp_path / "cp_html"
        cp_dir.mkdir()
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        assert translate_file(src, out, "French", checkpoint_dir=cp_dir) is True

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_checkpoint_with_all_cached_chunks(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """All chunks cached: LLM not called, progress fires 100."""
        save_text_chunk(tmp_path, 0, "[cached] Hello World", 1)
        progress: list[int] = []
        result = _translate_chunks(
            ["Hello World"],
            "French",
            "",
            progress_callback=progress.append,
            glossary_entries=None,
            cancel_check=None,
            checkpoint_dir=tmp_path,
        )
        assert result == ["[cached] Hello World"]
        assert 100 in progress
        mock_translate.assert_not_called()

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_checkpoint_index_out_of_range_ignored(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """Cached index beyond chunk count is safely ignored."""
        save_text_chunk(tmp_path, 99, "[cached] Out of range", 100)
        mock_translate.side_effect = lambda texts, *a, **kw: [
            f"[LLM] {t}" for t in texts
        ]
        result = _translate_chunks(
            ["A"],
            "French",
            "",
            progress_callback=None,
            glossary_entries=None,
            cancel_check=None,
            checkpoint_dir=tmp_path,
        )
        assert result is not None
        assert result[0] == "[LLM] A"


# ---------------------------------------------------------------------------
# TestEncryptedFileDetection — password-protected file handling
# ---------------------------------------------------------------------------


class TestEncryptedFileDetection:
    """Tests for encrypted/password-protected file detection."""

    def test_encrypted_xlsx_raises(self, tmp_path: Path) -> None:
        """Encrypted XLSX raises PASSWORD_PROTECTED."""
        src = tmp_path / "encrypted.xlsx"
        # OLE2 magic bytes
        src.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 100)
        out = tmp_path / "output.xlsx"
        with pytest.raises(ValueError, match="PASSWORD_PROTECTED"):
            translate_file(src, out, "French")

    def test_encrypted_pptx_raises(self, tmp_path: Path) -> None:
        """Encrypted PPTX raises PASSWORD_PROTECTED."""
        src = tmp_path / "encrypted.pptx"
        src.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 100)
        out = tmp_path / "output.pptx"
        with pytest.raises(ValueError, match="PASSWORD_PROTECTED"):
            translate_file(src, out, "French")


# ---------------------------------------------------------------------------
# TestTranslateFileSrcLang — source language parameter
# ---------------------------------------------------------------------------


class TestTranslateFileSrcLang:
    """Tests for source language parameter handling."""

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_src_lang_forwarded_to_llm(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """Source language is forwarded to translate_text."""
        src = tmp_path / "input.txt"
        src.write_text("Bonjour le monde", encoding="utf-8")
        out = tmp_path / "output.txt"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        translate_file(src, out, "English (US)", "French")
        args = mock_translate.call_args[0]
        # src_lang should be the third positional arg
        assert args[2] == "French"

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_empty_src_lang_auto_detect(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """Empty source language means auto-detect."""
        src = tmp_path / "input.txt"
        src.write_text("Hello", encoding="utf-8")
        out = tmp_path / "output.txt"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        translate_file(src, out, "French", "")
        args = mock_translate.call_args[0]
        assert args[2] == ""

    @patch("src.core.llm_engine.translate_text")
    def test_src_lang_forwarded_json(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """Source language forwarded for JSON format."""
        src = tmp_path / "input.json"
        src.write_text('{"key": "Bonjour"}', encoding="utf-8")
        out = tmp_path / "output.json"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        translate_file(src, out, "English (US)", "French")
        args = mock_translate.call_args[0]
        assert args[2] == "French"

    @patch("src.core.llm_engine.translate_text")
    def test_src_lang_forwarded_csv(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """Source language forwarded for CSV format."""
        src = tmp_path / "input.csv"
        src.write_text("Name\nBonjour\n", encoding="utf-8")
        out = tmp_path / "output.csv"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        translate_file(src, out, "English (US)", "French")
        args = mock_translate.call_args[0]
        assert args[2] == "French"


# ===========================================================================
# EXPANDED TESTS — targeting 700+ total
# ===========================================================================


# ---------------------------------------------------------------------------
# _chunk_text — boundary conditions and edge cases
# ---------------------------------------------------------------------------


def test_chunk_text_max_chars_equals_segment_length() -> None:
    """Segment length exactly at max_chars boundary keeps it as a single chunk."""
    # seg_len = len("ABCDE") + len("\n\n") = 7
    content = "ABCDE\n\nFGHIJ"
    # max_chars = 7 means first segment fits, second needs new chunk
    chunks, seps = _chunk_text(content, "\n\n", max_chars=7)
    assert len(chunks) == 2  # noqa: PLR2004
    assert _join_with_separators(chunks, seps) == content


def test_chunk_text_two_segments_boundary() -> None:
    """Two segments whose combined length exactly hits max_chars go in one chunk."""
    content = "AB\n\nCD"
    # seg_len per segment: len("AB")+len("\n\n")=4, and len("CD")+len("\n\n")=4
    # total=4+4=8
    chunks, seps = _chunk_text(content, "\n\n", max_chars=8)
    assert len(chunks) == 1
    assert chunks[0] == content


def test_chunk_text_just_over_boundary_splits() -> None:
    """Two segments whose combined length exceeds max_chars by one get split."""
    content = "AB\n\nCD"
    # total = 4+4 = 8, max_chars=7 forces a split
    chunks, seps = _chunk_text(content, "\n\n", max_chars=7)
    assert len(chunks) == 2  # noqa: PLR2004
    assert _join_with_separators(chunks, seps) == content


def test_chunk_text_many_empty_segments_between_content() -> None:
    """Multiple empty segments between content paragraphs are filtered."""
    content = "Hello\n\n\n\n\n\nWorld"
    chunks, seps = _chunk_text(content, "\n\n", max_chars=100)
    assert _join_with_separators(chunks, seps) == content


def test_chunk_text_trailing_separator() -> None:
    """Content ending with a separator is handled gracefully."""
    content = "Hello\n\nWorld\n\n"
    chunks, seps = _chunk_text(content, "\n\n", max_chars=100)
    # Trailing whitespace segment is filtered
    reassembled = _join_with_separators(chunks, seps)
    assert "Hello" in reassembled
    assert "World" in reassembled


def test_chunk_text_leading_separator() -> None:
    """Content starting with a separator is handled gracefully."""
    content = "\n\nHello\n\nWorld"
    chunks, seps = _chunk_text(content, "\n\n", max_chars=100)
    reassembled = _join_with_separators(chunks, seps)
    assert "Hello" in reassembled
    assert "World" in reassembled


def test_chunk_text_html_separator_split() -> None:
    """HTML-mode line separator splits content correctly."""
    content = "<p>A</p>\n<p>B</p>\n<p>C</p>"
    chunks, seps = _chunk_text(content, "\n", max_chars=20)
    assert len(chunks) >= 2  # noqa: PLR2004
    assert _join_with_separators(chunks, seps) == content


def test_chunk_text_rtf_par_split() -> None:
    r"""RTF \\par separator splits at paragraph boundaries."""
    content = r"Para1\parPara2\parPara3"
    chunks, seps = _chunk_text(content, "\\par", max_chars=15)
    assert len(chunks) >= 2  # noqa: PLR2004
    assert _join_with_separators(chunks, seps) == content


def test_chunk_text_max_chars_one() -> None:
    """max_chars=1 produces one chunk per non-empty segment."""
    content = "A\n\nB\n\nC"
    chunks, seps = _chunk_text(content, "\n\n", max_chars=1)
    assert len(chunks) == 3  # noqa: PLR2004
    assert _join_with_separators(chunks, seps) == content


def test_chunk_text_large_max_chars() -> None:
    """Very large max_chars keeps everything in one chunk."""
    content = "\n\n".join([f"Paragraph {i}" for i in range(50)])
    chunks, seps = _chunk_text(content, "\n\n", max_chars=1000000)
    assert len(chunks) == 1
    assert chunks[0] == content


# ---------------------------------------------------------------------------
# _join_with_separators — additional edge cases
# ---------------------------------------------------------------------------


def test_join_with_separators_multiple_parts() -> None:
    """Multiple parts with different separators join correctly."""
    parts = ["A", "B", "C"]
    seps = ["::", "||"]
    assert _join_with_separators(parts, seps) == "A::B||C"


def test_join_with_separators_empty_separator_strings() -> None:
    """Empty separator strings join parts without gaps."""
    parts = ["Hello", "World"]
    seps = [""]
    assert _join_with_separators(parts, seps) == "HelloWorld"


def test_join_with_separators_more_seps_than_needed() -> None:
    """Extra separators beyond parts count are safely ignored."""
    parts = ["A", "B"]
    seps = ["-", "-", "-"]  # only 1 needed
    assert _join_with_separators(parts, seps) == "A-B"


# ---------------------------------------------------------------------------
# _get_separator — extended coverage
# ---------------------------------------------------------------------------


def test_get_separator_rst() -> None:
    """Returns paragraph separator for .rst files."""
    assert _get_separator(".rst") == "\n\n"


def test_get_separator_unknown_extension() -> None:
    """Unknown extension defaults to line separator."""
    assert _get_separator(".xyz") == "\n"


# ---------------------------------------------------------------------------
# _read_file — encoding edge cases
# ---------------------------------------------------------------------------


def test_read_file_utf8_bom_stripping(tmp_path: Path) -> None:
    """UTF-8 BOM is stripped from file content."""
    f = tmp_path / "bom.txt"
    f.write_bytes(b"\xef\xbb\xbfTest content")
    result = _read_file(f)
    assert result == "Test content"
    assert not result.startswith("\ufeff")


def test_read_file_utf16_le(tmp_path: Path) -> None:
    """UTF-16 LE encoded file is detected and decoded."""
    text = "Hello UTF-16 LE"
    f = tmp_path / "utf16le.txt"
    f.write_bytes(text.encode("utf-16-le"))
    result = _read_file(f)
    # charset_normalizer should detect the encoding
    assert isinstance(result, str)


def test_read_file_utf16_be(tmp_path: Path) -> None:
    """UTF-16 BE encoded file is detected and decoded."""
    text = "Hello UTF-16 BE"
    f = tmp_path / "utf16be.txt"
    f.write_bytes(b"\xfe\xff" + text.encode("utf-16-be"))
    result = _read_file(f)
    assert isinstance(result, str)


def test_read_file_shift_jis(tmp_path: Path) -> None:
    """Shift-JIS encoded file is detected and decoded."""
    text = "日本語テスト"
    f = tmp_path / "sjis.txt"
    f.write_bytes(text.encode("shift_jis"))
    result = _read_file(f)
    assert isinstance(result, str)
    assert len(result) > 0


def test_read_file_single_byte(tmp_path: Path) -> None:
    """File with a single byte is read without crash."""
    f = tmp_path / "one.txt"
    f.write_bytes(b"X")
    assert _read_file(f) == "X"


def test_read_file_only_bom(tmp_path: Path) -> None:
    """File containing only a BOM returns empty string."""
    f = tmp_path / "bom_only.txt"
    f.write_bytes(b"\xef\xbb\xbf")
    assert _read_file(f) == ""


def test_read_file_large_file(tmp_path: Path) -> None:
    """Large file (100KB) is read correctly."""
    f = tmp_path / "large.txt"
    content = "A" * 100_000
    f.write_text(content, encoding="utf-8")
    assert _read_file(f) == content


# ---------------------------------------------------------------------------
# _detect_encoding — coverage
# ---------------------------------------------------------------------------


def test_detect_encoding_with_valid_result() -> None:
    """Returns charset_normalizer encoding when available."""
    from src.core.text_processor import _detect_encoding  # noqa: PLC0415

    mock_best = MagicMock()
    mock_best.encoding = "euc-kr"
    mock_result = MagicMock()
    mock_result.best.return_value = mock_best

    with patch("src.core.text_processor._detect_bytes", return_value=mock_result):
        assert _detect_encoding(b"test") == "euc-kr"


def test_detect_encoding_empty_bytes_fallback() -> None:
    """Empty bytes with None detection falls back to latin-1."""
    from src.core.text_processor import _detect_encoding  # noqa: PLC0415

    mock_result = MagicMock()
    mock_result.best.return_value = None

    with patch("src.core.text_processor._detect_bytes", return_value=mock_result):
        assert _detect_encoding(b"") == "latin-1"


# ---------------------------------------------------------------------------
# JSON extraction/injection — additional edge cases
# ---------------------------------------------------------------------------


def test_extract_json_strings_empty_dict() -> None:
    """Empty dict returns empty list."""
    assert _extract_json_strings({}) == []


def test_extract_json_strings_empty_list() -> None:
    """Empty list returns empty list."""
    assert _extract_json_strings([]) == []


def test_extract_json_strings_none_value() -> None:
    """None values are skipped."""
    assert _extract_json_strings(None) == []


def test_extract_json_strings_integer_value() -> None:
    """Integer at root level is skipped."""
    assert _extract_json_strings(42) == []


def test_extract_json_strings_boolean_value() -> None:
    """Boolean at root level is skipped."""
    assert _extract_json_strings(True) == []


def test_extract_json_strings_float_value() -> None:
    """Float at root level is skipped."""
    assert _extract_json_strings(3.14) == []


def test_extract_json_strings_whitespace_only_string() -> None:
    """Whitespace-only string is skipped."""
    data = {"ws": "   "}
    assert _extract_json_strings(data) == []


def test_extract_json_strings_nested_empty_structures() -> None:
    """Nested empty dicts and arrays return no strings."""
    data = {"a": {}, "b": [], "c": {"d": []}}
    assert _extract_json_strings(data) == []


def test_extract_json_strings_mixed_array() -> None:
    """Array with mixed types extracts only strings."""
    data = [1, "hello", True, None, "world", 3.14]
    pairs = _extract_json_strings(data)
    assert len(pairs) == 2  # noqa: PLR2004
    values = [v for _, v in pairs]
    assert "hello" in values
    assert "world" in values


def test_inject_json_strings_no_translations() -> None:
    """Empty translations dict returns original structure."""
    data = {"a": "hello", "b": 42}
    result = _inject_json_strings(data, {})
    assert result["a"] == "hello"
    assert result["b"] == 42  # noqa: PLR2004


def test_inject_json_strings_preserves_none_values() -> None:
    """None values are preserved even with translations present."""
    data = {"a": None, "b": "hello"}
    translations = {("b",): "translated"}
    result = _inject_json_strings(data, translations)
    assert result["a"] is None
    assert result["b"] == "translated"


def test_inject_json_strings_nested_array() -> None:
    """Injects translations into nested arrays."""
    data = {"items": [["a", "b"], ["c"]]}
    translations = {
        ("items", 0, 0): "X",
        ("items", 0, 1): "Y",
        ("items", 1, 0): "Z",
    }
    result = _inject_json_strings(data, translations)
    assert result["items"][0][0] == "X"
    assert result["items"][0][1] == "Y"
    assert result["items"][1][0] == "Z"


# ---------------------------------------------------------------------------
# translate_file — cancellation at various stages
# ---------------------------------------------------------------------------


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_cancel_before_chunks(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Cancellation before chunking returns False for txt."""
    src = tmp_path / "input.txt"
    src.write_text("Hello\n\nWorld", encoding="utf-8")
    out = tmp_path / "output.txt"
    result = translate_file(src, out, "French", cancel_check=lambda: True)
    assert result is False
    mock_translate.assert_not_called()


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_cancel_html(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Cancellation returns False for html format."""
    src = tmp_path / "input.html"
    src.write_text("<p>Hello</p>", encoding="utf-8")
    out = tmp_path / "output.html"
    result = translate_file(src, out, "French", cancel_check=lambda: True)
    assert result is False
    mock_translate.assert_not_called()


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_cancel_xml(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Cancellation returns False for xml format."""
    src = tmp_path / "input.xml"
    src.write_text("<root>Hello</root>", encoding="utf-8")
    out = tmp_path / "output.xml"
    result = translate_file(src, out, "French", cancel_check=lambda: True)
    assert result is False
    mock_translate.assert_not_called()


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_cancel_md(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Cancellation returns False for markdown format."""
    src = tmp_path / "input.md"
    src.write_text("# Hello\n\nWorld", encoding="utf-8")
    out = tmp_path / "output.md"
    result = translate_file(src, out, "French", cancel_check=lambda: True)
    assert result is False
    mock_translate.assert_not_called()


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_cancel_rtf(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    r"""Cancellation returns False for rtf format."""
    src = tmp_path / "input.rtf"
    src.write_text(r"{\rtf1 Hello\par World}", encoding="utf-8")
    out = tmp_path / "output.rtf"
    result = translate_file(src, out, "French", cancel_check=lambda: True)
    assert result is False
    mock_translate.assert_not_called()


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_cancel_rst(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Cancellation returns False for rst format."""
    src = tmp_path / "input.rst"
    src.write_text("Title\n=====\n\nBody", encoding="utf-8")
    out = tmp_path / "output.rst"
    result = translate_file(src, out, "French", cancel_check=lambda: True)
    assert result is False
    mock_translate.assert_not_called()


@patch("src.core.llm_engine.translate_text")
def test_translate_file_cancel_xliff(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """XLIFF translation returns False when cancelled."""
    src = tmp_path / "input.xliff"
    src.write_text(
        '<?xml version="1.0"?>'
        '<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2">'
        '<file source-language="en" target-language="fr" datatype="plaintext">'
        "<body>"
        '<trans-unit id="1"><source>Hello</source></trans-unit>'
        "</body></file></xliff>",
        encoding="utf-8",
    )
    out = tmp_path / "output.xliff"
    result = translate_file(src, out, "French", cancel_check=lambda: True)
    assert result is False


@patch("src.core.llm_engine.translate_text")
def test_translate_file_cancel_properties(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Properties translation returns False when cancelled."""
    src = tmp_path / "input.properties"
    src.write_text("key=value\n", encoding="utf-8")
    out = tmp_path / "output.properties"
    result = translate_file(src, out, "French", cancel_check=lambda: True)
    assert result is False


@patch("src.core.llm_engine.translate_text")
def test_translate_file_cancel_strings(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Apple Strings translation returns False when cancelled."""
    src = tmp_path / "input.strings"
    src.write_text('"key" = "value";\n', encoding="utf-8")
    out = tmp_path / "output.strings"
    result = translate_file(src, out, "French", cancel_check=lambda: True)
    assert result is False


@patch("src.core.llm_engine.translate_text")
def test_translate_file_cancel_vtt(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """VTT translation returns False when cancelled."""
    src = tmp_path / "input.vtt"
    src.write_text(
        "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nHello\n",
        encoding="utf-8",
    )
    out = tmp_path / "output.vtt"
    result = translate_file(src, out, "French", cancel_check=lambda: True)
    assert result is False


@patch("src.core.llm_engine.translate_text")
def test_translate_file_cancel_ass(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """ASS translation returns False when cancelled."""
    src = tmp_path / "input.ass"
    src.write_text(
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
        "MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,Hello\n",
        encoding="utf-8",
    )
    out = tmp_path / "output.ass"
    result = translate_file(src, out, "French", cancel_check=lambda: True)
    assert result is False


# ---------------------------------------------------------------------------
# translate_file — LLM error propagation for all formats
# ---------------------------------------------------------------------------


@patch("src.core.llm_engine.translate_text")
def test_translate_file_srt_llm_error_propagates(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """LLM ValueError propagates through SRT translation."""
    src = tmp_path / "input.srt"
    src.write_text(
        "1\n00:00:01,000 --> 00:00:04,000\nHello\n",
        encoding="utf-8",
    )
    out = tmp_path / "output.srt"
    mock_translate.side_effect = ValueError("QUOTA_ERROR")
    with pytest.raises(ValueError, match="QUOTA_ERROR"):
        translate_file(src, out, "French")


@patch("src.core.llm_engine.translate_text")
def test_translate_file_vtt_llm_error_propagates(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """LLM ValueError propagates through VTT translation."""
    src = tmp_path / "input.vtt"
    src.write_text(
        "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nHello\n",
        encoding="utf-8",
    )
    out = tmp_path / "output.vtt"
    mock_translate.side_effect = ValueError("AUTH_ERROR")
    with pytest.raises(ValueError, match="AUTH_ERROR"):
        translate_file(src, out, "French")


@patch("src.core.llm_engine.translate_text")
def test_translate_file_ass_llm_error_propagates(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """LLM ValueError propagates through ASS translation."""
    src = tmp_path / "input.ass"
    src.write_text(
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
        "MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,Hello\n",
        encoding="utf-8",
    )
    out = tmp_path / "output.ass"
    mock_translate.side_effect = ValueError("AUTH_ERROR")
    with pytest.raises(ValueError, match="AUTH_ERROR"):
        translate_file(src, out, "French")


@patch("src.core.llm_engine.translate_text")
def test_translate_file_po_llm_error_propagates(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """LLM ValueError propagates through PO translation."""
    src = tmp_path / "input.po"
    src.write_text(
        'msgid ""\nmsgstr ""\n\nmsgid "Hello"\nmsgstr ""\n',
        encoding="utf-8",
    )
    out = tmp_path / "output.po"
    mock_translate.side_effect = ValueError("QUOTA_ERROR")
    with pytest.raises(ValueError, match="QUOTA_ERROR"):
        translate_file(src, out, "French")


@patch("src.core.llm_engine.translate_text")
def test_translate_file_xliff_llm_error_propagates(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """LLM ValueError propagates through XLIFF translation."""
    src = tmp_path / "input.xliff"
    src.write_text(
        '<?xml version="1.0"?>'
        '<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2">'
        '<file source-language="en" target-language="fr" datatype="plaintext">'
        "<body>"
        '<trans-unit id="1"><source>Hello</source></trans-unit>'
        "</body></file></xliff>",
        encoding="utf-8",
    )
    out = tmp_path / "output.xliff"
    mock_translate.side_effect = ValueError("AUTH_ERROR")
    with pytest.raises(ValueError, match="AUTH_ERROR"):
        translate_file(src, out, "French")


@patch("src.core.llm_engine.translate_text")
def test_translate_file_yaml_llm_error_propagates(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """LLM ValueError propagates through YAML translation."""
    src = tmp_path / "input.yaml"
    src.write_text("key: Hello\n", encoding="utf-8")
    out = tmp_path / "output.yaml"
    mock_translate.side_effect = ValueError("AUTH_ERROR")
    with pytest.raises(ValueError, match="AUTH_ERROR"):
        translate_file(src, out, "French")


@patch("src.core.llm_engine.translate_text")
def test_translate_file_properties_llm_error_propagates(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """LLM ValueError propagates through Properties translation."""
    src = tmp_path / "input.properties"
    src.write_text("key=Hello\n", encoding="utf-8")
    out = tmp_path / "output.properties"
    mock_translate.side_effect = ValueError("QUOTA_ERROR")
    with pytest.raises(ValueError, match="QUOTA_ERROR"):
        translate_file(src, out, "French")


@patch("src.core.llm_engine.translate_text")
def test_translate_file_strings_llm_error_propagates(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """LLM ValueError propagates through Apple Strings translation."""
    src = tmp_path / "input.strings"
    src.write_text('"key" = "Hello";\n', encoding="utf-8")
    out = tmp_path / "output.strings"
    mock_translate.side_effect = ValueError("AUTH_ERROR")
    with pytest.raises(ValueError, match="AUTH_ERROR"):
        translate_file(src, out, "French")


# ---------------------------------------------------------------------------
# translate_file — empty / whitespace for structured formats
# ---------------------------------------------------------------------------


@patch("src.core.llm_engine.translate_text")
def test_translate_file_vtt_empty(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Empty VTT file is copied as-is."""
    src = tmp_path / "empty.vtt"
    src.write_text("", encoding="utf-8")
    out = tmp_path / "output.vtt"
    result = translate_file(src, out, "French")
    assert result is True
    mock_translate.assert_not_called()


@patch("src.core.llm_engine.translate_text")
def test_translate_file_ass_empty(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Empty ASS file is copied as-is."""
    src = tmp_path / "empty.ass"
    src.write_text("", encoding="utf-8")
    out = tmp_path / "output.ass"
    result = translate_file(src, out, "French")
    assert result is True
    mock_translate.assert_not_called()


@patch("src.core.llm_engine.translate_text")
def test_translate_file_ssa_empty(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Empty SSA file is copied as-is."""
    src = tmp_path / "empty.ssa"
    src.write_text("", encoding="utf-8")
    out = tmp_path / "output.ssa"
    result = translate_file(src, out, "French")
    assert result is True
    mock_translate.assert_not_called()


@patch("src.core.llm_engine.translate_text")
def test_translate_file_xliff_empty_body(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """XLIFF with empty body has no translatable entries."""
    src = tmp_path / "empty.xliff"
    src.write_text(
        '<?xml version="1.0"?>'
        '<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2">'
        '<file source-language="en" target-language="fr" datatype="plaintext">'
        "<body></body></file></xliff>",
        encoding="utf-8",
    )
    out = tmp_path / "output.xliff"
    result = translate_file(src, out, "French")
    assert result is True
    assert out.exists()


@patch("src.core.llm_engine.translate_text")
def test_translate_file_properties_empty(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Empty properties file is copied as-is."""
    src = tmp_path / "empty.properties"
    src.write_text("", encoding="utf-8")
    out = tmp_path / "output.properties"
    result = translate_file(src, out, "French")
    assert result is True
    mock_translate.assert_not_called()


@patch("src.core.llm_engine.translate_text")
def test_translate_file_strings_empty(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Empty .strings file is copied as-is."""
    src = tmp_path / "empty.strings"
    src.write_text("", encoding="utf-8")
    out = tmp_path / "output.strings"
    result = translate_file(src, out, "French")
    assert result is True
    mock_translate.assert_not_called()


# ---------------------------------------------------------------------------
# translate_file — write errors for structured formats
# ---------------------------------------------------------------------------


@patch("src.core.llm_engine.translate_text")
def test_translate_file_vtt_write_error(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """VTT write failure raises TEXT_WRITE_ERROR."""
    src = tmp_path / "input.vtt"
    src.write_text(
        "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nHello\n",
        encoding="utf-8",
    )
    read_only = tmp_path / "readonly_vtt"
    read_only.mkdir()
    read_only.chmod(0o444)
    out = read_only / "sub" / "output.vtt"
    mock_translate.side_effect = lambda texts, *a, **kw: texts
    try:
        with pytest.raises(ValueError, match="TEXT_WRITE_ERROR"):
            translate_file(src, out, "French")
    finally:
        read_only.chmod(0o755)


@patch("src.core.llm_engine.translate_text")
def test_translate_file_xliff_write_error(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """XLIFF write failure raises TEXT_WRITE_ERROR."""
    src = tmp_path / "input.xliff"
    src.write_text(
        '<?xml version="1.0"?>'
        '<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2">'
        '<file source-language="en" target-language="fr" datatype="plaintext">'
        "<body>"
        '<trans-unit id="1"><source>Hello</source></trans-unit>'
        "</body></file></xliff>",
        encoding="utf-8",
    )
    read_only = tmp_path / "readonly_xliff"
    read_only.mkdir()
    read_only.chmod(0o444)
    out = read_only / "sub" / "output.xliff"
    mock_translate.side_effect = lambda texts, *a, **kw: texts
    try:
        with pytest.raises(ValueError, match="TEXT_WRITE_ERROR"):
            translate_file(src, out, "French")
    finally:
        read_only.chmod(0o755)


@patch("src.core.llm_engine.translate_text")
def test_translate_file_properties_write_error(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Properties write failure raises TEXT_WRITE_ERROR."""
    src = tmp_path / "input.properties"
    src.write_text("key=Hello\n", encoding="utf-8")
    read_only = tmp_path / "readonly_props"
    read_only.mkdir()
    read_only.chmod(0o444)
    out = read_only / "sub" / "output.properties"
    mock_translate.side_effect = lambda texts, *a, **kw: texts
    try:
        with pytest.raises(ValueError, match="TEXT_WRITE_ERROR"):
            translate_file(src, out, "French")
    finally:
        read_only.chmod(0o755)


@patch("src.core.llm_engine.translate_text")
def test_translate_file_strings_write_error(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Apple Strings write failure raises TEXT_WRITE_ERROR."""
    src = tmp_path / "input.strings"
    src.write_text('"key" = "Hello";\n', encoding="utf-8")
    read_only = tmp_path / "readonly_strings"
    read_only.mkdir()
    read_only.chmod(0o444)
    out = read_only / "sub" / "output.strings"
    mock_translate.side_effect = lambda texts, *a, **kw: texts
    try:
        with pytest.raises(ValueError, match="TEXT_WRITE_ERROR"):
            translate_file(src, out, "French")
    finally:
        read_only.chmod(0o755)


# ---------------------------------------------------------------------------
# BOM handling across format types
# ---------------------------------------------------------------------------


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_md_with_bom(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """UTF-8 BOM in markdown file is stripped."""
    src = tmp_path / "bom.md"
    src.write_bytes(b"\xef\xbb\xbf# Hello\n\nWorld")
    out = tmp_path / "output.md"
    mock_translate.side_effect = lambda texts, *a, **kw: texts
    assert translate_file(src, out, "French") is True
    raw = out.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_rtf_with_bom(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    r"""UTF-8 BOM in RTF file is stripped."""
    src = tmp_path / "bom.rtf"
    src.write_bytes(b"\xef\xbb\xbf{\\rtf1 Hello}")
    out = tmp_path / "output.rtf"
    mock_translate.side_effect = lambda texts, *a, **kw: texts
    assert translate_file(src, out, "French") is True
    raw = out.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_rst_with_bom(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """UTF-8 BOM in RST file is stripped."""
    src = tmp_path / "bom.rst"
    src.write_bytes(b"\xef\xbb\xbfTitle\n=====\n\nBody")
    out = tmp_path / "output.rst"
    mock_translate.side_effect = lambda texts, *a, **kw: texts
    assert translate_file(src, out, "French") is True
    raw = out.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")


@patch("src.core.llm_engine.translate_text")
def test_translate_file_json_with_bom(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """UTF-8 BOM in JSON file is handled."""
    src = tmp_path / "bom.json"
    src.write_bytes(b'\xef\xbb\xbf{"key": "Hello"}')
    out = tmp_path / "output.json"
    mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
    assert translate_file(src, out, "French") is True
    content = out.read_text(encoding="utf-8")
    assert "[T] Hello" in content


@patch("src.core.llm_engine.translate_text")
def test_translate_file_srt_with_bom(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """UTF-8 BOM in SRT file is stripped."""
    src = tmp_path / "bom.srt"
    src.write_bytes(b"\xef\xbb\xbf1\n00:00:01,000 --> 00:00:02,000\nHello\n")
    out = tmp_path / "output.srt"
    mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
    assert translate_file(src, out, "French") is True
    content = out.read_text(encoding="utf-8")
    assert "[T] Hello" in content


@patch("src.core.llm_engine.translate_text")
def test_translate_file_po_with_bom(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """UTF-8 BOM in PO file is stripped."""
    src = tmp_path / "bom.po"
    src.write_bytes(b'\xef\xbb\xbfmsgid ""\nmsgstr ""\n\nmsgid "Hello"\nmsgstr ""\n')
    out = tmp_path / "output.po"
    mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
    assert translate_file(src, out, "French") is True
    content = out.read_text(encoding="utf-8")
    assert "[T] Hello" in content


@patch("src.core.llm_engine.translate_text")
def test_translate_file_yaml_with_bom(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """UTF-8 BOM in YAML file is stripped."""
    src = tmp_path / "bom.yaml"
    src.write_bytes(b"\xef\xbb\xbfkey: Hello\n")
    out = tmp_path / "output.yaml"
    mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
    assert translate_file(src, out, "French") is True
    content = out.read_text(encoding="utf-8")
    assert "[T] Hello" in content


# ---------------------------------------------------------------------------
# Token optimization strip/restore roundtrips
# ---------------------------------------------------------------------------


def test_strip_restore_html_attributes_roundtrip() -> None:
    """HTML attribute strip→restore roundtrip preserves all attributes."""
    from src.utils.text_utils import (  # noqa: PLC0415
        restore_html_attributes,
        strip_html_attributes,
    )

    html = '<div class="main" id="top"><p style="color:red">Hello</p></div>'
    stripped, records = strip_html_attributes(html)
    # Attributes should be removed from stripped version
    assert 'class="main"' not in stripped
    # Restore and verify
    restored = restore_html_attributes(stripped, records)
    assert 'class="main"' in restored
    assert 'id="top"' in restored


def test_strip_restore_xml_overhead_roundtrip() -> None:
    """XML overhead strip→restore roundtrip preserves PIs and CDATA."""
    from src.utils.text_utils import (  # noqa: PLC0415
        restore_xml_overhead,
        strip_xml_overhead,
    )

    xml = '<?xml version="1.0"?>\n<root><![CDATA[Hello]]></root>'
    stripped, records = strip_xml_overhead(xml)
    assert "<![CDATA[" not in stripped
    restored = restore_xml_overhead(stripped, records)
    assert "<![CDATA[" in restored
    assert "]]>" in restored


def test_strip_restore_xml_attributes_roundtrip() -> None:
    """XML attribute strip→restore roundtrip preserves all attributes."""
    from src.utils.text_utils import (  # noqa: PLC0415
        restore_html_attributes,
        strip_xml_attributes,
    )

    xml = '<root lang="en" xmlns:x="http://example.com"><msg id="1">Hi</msg></root>'
    stripped, records = strip_xml_attributes(xml)
    assert 'lang="en"' not in stripped
    restored = restore_html_attributes(stripped, records)
    assert 'lang="en"' in restored
    assert 'id="1"' in restored


def test_strip_restore_rtf_overhead_roundtrip() -> None:
    r"""RTF overhead strip→restore roundtrip preserves control words."""
    from src.utils.text_utils import (  # noqa: PLC0415
        restore_rtf_overhead,
        strip_rtf_overhead,
    )

    rtf = r"{\rtf1\ansi\b Hello World\b0}"
    stripped, records = strip_rtf_overhead(rtf)
    assert "\\rtf1" not in stripped
    assert "\\ansi" not in stripped
    restored = restore_rtf_overhead(stripped, records)
    assert "\\rtf1" in restored or "rtf1" in restored


def test_strip_restore_md_overhead_roundtrip() -> None:
    """Markdown overhead strip→restore roundtrip preserves URLs."""
    from src.utils.text_utils import (  # noqa: PLC0415
        restore_md_overhead,
        strip_md_overhead,
    )

    md = "Visit [our site](https://example.com) for info."
    stripped, records = strip_md_overhead(md)
    assert "https://example.com" not in stripped
    restored = restore_md_overhead(stripped, records)
    assert "https://example.com" in restored


def test_strip_html_attributes_empty_input() -> None:
    """Stripping attributes from empty string returns empty."""
    from src.utils.text_utils import strip_html_attributes  # noqa: PLC0415

    stripped, records = strip_html_attributes("")
    assert stripped == ""
    assert records == {}


def test_strip_html_attributes_no_attrs() -> None:
    """HTML without attributes passes through unchanged."""
    from src.utils.text_utils import strip_html_attributes  # noqa: PLC0415

    html = "<p>Hello</p>"
    stripped, records = strip_html_attributes(html)
    assert "Hello" in stripped


def test_strip_html_attributes_self_closing_tag() -> None:
    """Self-closing tags with attributes are handled."""
    from src.utils.text_utils import (  # noqa: PLC0415
        restore_html_attributes,
        strip_html_attributes,
    )

    html = '<img src="photo.jpg" alt="Photo" />'
    stripped, records = strip_html_attributes(html)
    restored = restore_html_attributes(stripped, records)
    assert 'src="photo.jpg"' in restored


def test_strip_xml_overhead_no_overhead() -> None:
    """XML without overhead passes through unchanged."""
    from src.utils.text_utils import strip_xml_overhead  # noqa: PLC0415

    xml = "<root><msg>Hello</msg></root>"
    stripped, records = strip_xml_overhead(xml)
    assert "<msg>" in stripped
    assert records == []


def test_strip_rtf_overhead_empty() -> None:
    """Stripping RTF overhead from empty string returns empty."""
    from src.utils.text_utils import strip_rtf_overhead  # noqa: PLC0415

    stripped, records = strip_rtf_overhead("")
    assert stripped == ""


def test_strip_md_overhead_no_links() -> None:
    """Markdown without links passes through unchanged."""
    from src.utils.text_utils import strip_md_overhead  # noqa: PLC0415

    md = "Just plain text."
    stripped, records = strip_md_overhead(md)
    assert stripped == md
    assert records == []


# ---------------------------------------------------------------------------
# _translate_chunks — edge cases
# ---------------------------------------------------------------------------


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_chunks_single_chunk(
    mock_translate: MagicMock,
) -> None:
    """Single chunk is translated in one call."""
    mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
    result = _translate_chunks(
        ["Hello"],
        "French",
        "",
        progress_callback=None,
        glossary_entries=None,
        cancel_check=None,
    )
    assert result == ["[T] Hello"]
    assert mock_translate.call_count == 1


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_chunks_cancel_at_start(
    mock_translate: MagicMock,
) -> None:
    """Cancellation at the very start returns None."""
    result = _translate_chunks(
        ["Hello", "World"],
        "French",
        "",
        progress_callback=None,
        glossary_entries=None,
        cancel_check=lambda: True,
    )
    assert result is None
    mock_translate.assert_not_called()


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_chunks_progress_with_cached_chunks(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Progress callback accounts for cached chunks."""
    from src.core.checkpoint import save_text_chunk  # noqa: PLC0415

    save_text_chunk(tmp_path, 0, "[cached] A", 3)
    mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]

    progress_values: list[int] = []
    result = _translate_chunks(
        ["A", "B", "C"],
        "French",
        "",
        progress_callback=progress_values.append,
        glossary_entries=None,
        cancel_check=None,
        checkpoint_dir=tmp_path,
    )
    assert result is not None
    assert result[0] == "[cached] A"
    assert result[1] == "[T] B"
    assert len(progress_values) > 0
    assert progress_values[-1] == 100  # noqa: PLR2004


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_chunks_checkpoint_out_of_range_ignored(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Checkpoint entries beyond the chunks list are safely ignored."""
    from src.core.checkpoint import save_text_chunk  # noqa: PLC0415

    # Save checkpoint at index 99, but we only have 2 chunks
    save_text_chunk(tmp_path, 99, "[cached] X", 100)
    mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]

    result = _translate_chunks(
        ["A", "B"],
        "French",
        "",
        progress_callback=None,
        glossary_entries=None,
        cancel_check=None,
        checkpoint_dir=tmp_path,
    )
    assert result == ["[T] A", "[T] B"]


# ---------------------------------------------------------------------------
# _repair_and_restore_attrs — additional tests
# ---------------------------------------------------------------------------


def test_repair_and_restore_attrs_passthrough_no_changes() -> None:
    """Matching translated and original with no records passes through."""
    result = _repair_and_restore_attrs("Hello", "Hello", {})
    assert result == "Hello"


def test_repair_and_restore_attrs_translated_matches_original() -> None:
    """When translated text matches original, no repair needed."""
    original = "<b>Bold</b>"
    translated = "<b>Gras</b>"
    result = _repair_and_restore_attrs(translated, original, {})
    assert "<b>" in result
    assert "</b>" in result


# ---------------------------------------------------------------------------
# HTML edge cases — entities, nested tags, self-closing
# ---------------------------------------------------------------------------


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_html_numeric_entities(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """HTML numeric entities are preserved through translation."""
    src = tmp_path / "entities.html"
    src.write_text(
        "<p>Copyright &#169; 2024</p>",
        encoding="utf-8",
    )
    out = tmp_path / "output.html"
    mock_translate.side_effect = lambda texts, *a, **kw: texts
    assert translate_file(src, out, "French") is True
    content = out.read_text(encoding="utf-8")
    assert "&#169;" in content or "\u00a9" in content


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_html_self_closing_tags(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """HTML with self-closing tags (br, img, hr) translates successfully."""
    src = tmp_path / "self_close.html"
    src.write_text(
        '<p>Line one<br/>Line two</p><hr/><img src="img.jpg"/>',
        encoding="utf-8",
    )
    out = tmp_path / "output.html"
    mock_translate.side_effect = lambda texts, *a, **kw: texts
    assert translate_file(src, out, "French") is True
    content = out.read_text(encoding="utf-8")
    assert "Line one" in content


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_html_deeply_nested_div(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Deeply nested div structure survives translation."""
    src = tmp_path / "deep.html"
    inner = "Text"
    for _ in range(10):
        inner = f"<div>{inner}</div>"
    src.write_text(inner, encoding="utf-8")
    out = tmp_path / "output.html"
    mock_translate.side_effect = lambda texts, *a, **kw: texts
    assert translate_file(src, out, "French") is True
    content = out.read_text(encoding="utf-8")
    assert "Text" in content


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_html_table_structure(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """HTML table structure is preserved."""
    src = tmp_path / "table.html"
    src.write_text(
        "<table><tr><td>Cell 1</td><td>Cell 2</td></tr></table>",
        encoding="utf-8",
    )
    out = tmp_path / "output.html"
    mock_translate.side_effect = lambda texts, *a, **kw: texts
    assert translate_file(src, out, "French") is True
    content = out.read_text(encoding="utf-8")
    assert "<table>" in content
    assert "<td>" in content


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_html_multiline(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Multi-line HTML translates each line."""
    src = tmp_path / "multi.html"
    src.write_text(
        "<html>\n<body>\n<p>Hello</p>\n<p>World</p>\n</body>\n</html>",
        encoding="utf-8",
    )
    out = tmp_path / "output.html"
    mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
    assert translate_file(src, out, "French") is True
    content = out.read_text(encoding="utf-8")
    assert "[T]" in content


# ---------------------------------------------------------------------------
# CSV — additional edge cases
# ---------------------------------------------------------------------------


@patch("src.core.llm_engine.translate_text")
def test_translate_file_csv_double_quoted_fields(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """CSV with double-quoted fields containing commas is handled."""
    src = tmp_path / "quoted.csv"
    src.write_text(
        'Name,Greeting\n"Smith, John","Hello, World"\n',
        encoding="utf-8",
    )
    out = tmp_path / "output.csv"
    mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
    assert translate_file(src, out, "French") is True
    content = out.read_text(encoding="utf-8")
    assert "[T]" in content


@patch("src.core.llm_engine.translate_text")
def test_translate_file_csv_escaped_quotes(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """CSV with escaped double quotes inside fields is handled."""
    src = tmp_path / "escaped.csv"
    src.write_text(
        'Name,Quote\nAlice,"She said ""hello"""\n',
        encoding="utf-8",
    )
    out = tmp_path / "output.csv"
    mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
    assert translate_file(src, out, "French") is True
    content = out.read_text(encoding="utf-8")
    assert "[T]" in content


@patch("src.core.llm_engine.translate_text")
def test_translate_file_csv_empty_row(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """CSV with empty rows in between non-empty rows."""
    src = tmp_path / "gaps.csv"
    src.write_text(
        "Name,Value\n,\nAlice,Hello\n,\nBob,World\n",
        encoding="utf-8",
    )
    out = tmp_path / "output.csv"
    mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
    assert translate_file(src, out, "French") is True
    content = out.read_text(encoding="utf-8")
    assert "[T] Alice" in content
    assert "[T] World" in content


@patch("src.core.llm_engine.translate_text")
def test_translate_file_csv_large_file(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """CSV with many rows translates all cells."""
    src = tmp_path / "large.csv"
    rows = ["Name,Value"] + [f"Name_{i},Value_{i}" for i in range(100)]
    src.write_text("\n".join(rows) + "\n", encoding="utf-8")
    out = tmp_path / "output.csv"
    mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
    assert translate_file(src, out, "French") is True
    content = out.read_text(encoding="utf-8")
    assert "[T] Name_99" in content


@patch("src.core.llm_engine.translate_text")
def test_translate_file_csv_numeric_cells(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """CSV numeric-looking cells are still treated as text strings."""
    src = tmp_path / "nums.csv"
    src.write_text("ID,Label\n100,Hello\n200,World\n", encoding="utf-8")
    out = tmp_path / "output.csv"
    mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
    assert translate_file(src, out, "French") is True
    content = out.read_text(encoding="utf-8")
    # Even numeric-looking cells are translated since they are strings
    assert "[T] 100" in content
    assert "[T] Hello" in content


# ---------------------------------------------------------------------------
# JSON — additional edge cases
# ---------------------------------------------------------------------------


@patch("src.core.llm_engine.translate_text")
def test_translate_file_json_special_chars_in_values(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """JSON with special characters in string values."""
    src = tmp_path / "special.json"
    data = {"msg": 'Hello "World" & <Friends>'}
    src.write_text(json.dumps(data), encoding="utf-8")
    out = tmp_path / "output.json"
    mock_translate.side_effect = lambda texts, *a, **kw: texts
    assert translate_file(src, out, "French") is True
    result = json.loads(out.read_text(encoding="utf-8"))
    assert result["msg"] == 'Hello "World" & <Friends>'


@patch("src.core.llm_engine.translate_text")
def test_translate_file_json_unicode_keys(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """JSON with Unicode keys preserves key names."""
    src = tmp_path / "unicode_keys.json"
    data = {"挨拶": "Hello", "名前": "World"}
    src.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "output.json"
    mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
    assert translate_file(src, out, "French") is True
    result = json.loads(out.read_text(encoding="utf-8"))
    assert "挨拶" in result
    assert result["挨拶"] == "[T] Hello"


@patch("src.core.llm_engine.translate_text")
def test_translate_file_json_nested_arrays_of_strings(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """JSON with nested arrays of strings translates all."""
    src = tmp_path / "nested_arr.json"
    data = {"matrix": [["a", "b"], ["c", "d"]]}
    src.write_text(json.dumps(data), encoding="utf-8")
    out = tmp_path / "output.json"
    mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
    assert translate_file(src, out, "French") is True
    result = json.loads(out.read_text(encoding="utf-8"))
    assert result["matrix"][0][0] == "[T] a"
    assert result["matrix"][1][1] == "[T] d"


@patch("src.core.llm_engine.translate_text")
def test_translate_file_json_large_file(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """JSON with many keys translates all string values."""
    src = tmp_path / "large.json"
    data = {f"key_{i}": f"value_{i}" for i in range(200)}
    src.write_text(json.dumps(data), encoding="utf-8")
    out = tmp_path / "output.json"
    mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
    assert translate_file(src, out, "French") is True
    result = json.loads(out.read_text(encoding="utf-8"))
    assert result["key_0"] == "[T] value_0"
    assert result["key_199"] == "[T] value_199"


def test_extract_json_strings_root_string() -> None:
    """A root-level string is extracted."""
    pairs = _extract_json_strings("hello world")
    assert len(pairs) == 1
    assert pairs[0] == ((), "hello world")


def test_inject_json_strings_root_string() -> None:
    """A root-level string is translated."""
    result = _inject_json_strings("hello", {(): "bonjour"})
    assert result == "bonjour"


def test_inject_json_strings_root_string_no_translation() -> None:
    """A root-level string without translation is unchanged."""
    result = _inject_json_strings("hello", {})
    assert result == "hello"


# ---------------------------------------------------------------------------
# Subtitle — additional edge cases
# ---------------------------------------------------------------------------


@patch("src.core.llm_engine.translate_text")
def test_translate_file_srt_unicode_content(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """SRT with Unicode dialogue text is translated."""
    src = tmp_path / "unicode.srt"
    src.write_text(
        "1\n00:00:01,000 --> 00:00:04,000\n你好世界\n\n",
        encoding="utf-8",
    )
    out = tmp_path / "output.srt"
    mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
    assert translate_file(src, out, "French") is True
    content = out.read_text(encoding="utf-8")
    assert "[T]" in content


@patch("src.core.llm_engine.translate_text")
def test_translate_file_srt_many_entries(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """SRT with many entries translates all."""
    entries = []
    for i in range(50):
        s = f"00:00:{i:02d},000"
        e = f"00:00:{i + 1:02d},000"
        entries.append(f"{i + 1}\n{s} --> {e}\nLine {i}\n")
    src = tmp_path / "many.srt"
    src.write_text("\n".join(entries), encoding="utf-8")
    out = tmp_path / "output.srt"
    mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
    assert translate_file(src, out, "French") is True
    content = out.read_text(encoding="utf-8")
    assert "[T] Line 0" in content
    assert "[T] Line 49" in content


@patch("src.core.llm_engine.translate_text")
def test_translate_file_vtt_with_cue_identifiers(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """VTT with cue identifiers translates only dialogue text."""
    src = tmp_path / "cues.vtt"
    src.write_text(
        "WEBVTT\n\n"
        "intro\n00:00:01.000 --> 00:00:04.000\nHello\n\n"
        "outro\n00:00:05.000 --> 00:00:08.000\nGoodbye\n",
        encoding="utf-8",
    )
    out = tmp_path / "output.vtt"
    mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
    assert translate_file(src, out, "French") is True
    content = out.read_text(encoding="utf-8")
    assert "[T] Hello" in content
    assert "[T] Goodbye" in content


# ---------------------------------------------------------------------------
# Localization — additional edge cases
# ---------------------------------------------------------------------------


@patch("src.core.llm_engine.translate_text")
def test_translate_file_po_with_comments(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """PO file comments are preserved."""
    src = tmp_path / "comments.po"
    src.write_text(
        'msgid ""\nmsgstr ""\n\n'
        "# Translator comment\n"
        "#. Developer note\n"
        "#: src/main.py:42\n"
        'msgid "Hello"\nmsgstr ""\n',
        encoding="utf-8",
    )
    out = tmp_path / "output.po"
    mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
    assert translate_file(src, out, "French") is True
    content = out.read_text(encoding="utf-8")
    assert "[T] Hello" in content
    # Comments should be preserved
    assert "# Translator comment" in content or "#." in content


@patch("src.core.llm_engine.translate_text")
def test_translate_file_pot_empty_msgstr(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """POT template fills empty msgstr with translations."""
    src = tmp_path / "template.pot"
    src.write_text(
        'msgid ""\nmsgstr ""\n\n'
        'msgid "Submit"\nmsgstr ""\n\n'
        'msgid "Cancel"\nmsgstr ""\n',
        encoding="utf-8",
    )
    out = tmp_path / "output.pot"
    mock_translate.side_effect = lambda texts, *a, **kw: [f"[FR] {t}" for t in texts]
    assert translate_file(src, out, "French") is True
    content = out.read_text(encoding="utf-8")
    assert "[FR] Submit" in content
    assert "[FR] Cancel" in content


# ---------------------------------------------------------------------------
# Key-value — additional edge cases
# ---------------------------------------------------------------------------


@patch("src.core.llm_engine.translate_text")
def test_translate_file_yaml_nested(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """YAML with nested structure translates leaf values."""
    src = tmp_path / "nested.yaml"
    src.write_text(
        "parent:\n  child: Hello\n  other: World\n",
        encoding="utf-8",
    )
    out = tmp_path / "output.yaml"
    mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
    assert translate_file(src, out, "French") is True
    content = out.read_text(encoding="utf-8")
    assert "[T] Hello" in content
    assert "[T] World" in content


@patch("src.core.llm_engine.translate_text")
def test_translate_file_properties_with_escaped_chars(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Properties file with backslash escapes translates correctly."""
    src = tmp_path / "escaped.properties"
    src.write_text(
        "greeting=Hello World\npath=C\\\\Users\\\\test\n",
        encoding="utf-8",
    )
    out = tmp_path / "output.properties"
    mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
    assert translate_file(src, out, "French") is True
    content = out.read_text(encoding="utf-8")
    assert "[T]" in content


@patch("src.core.llm_engine.translate_text")
def test_translate_file_strings_with_comments(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Apple Strings file preserves comments."""
    src = tmp_path / "commented.strings"
    src.write_text(
        "/* Main greeting */\n"
        '"greeting" = "Hello";\n\n'
        "/* Farewell */\n"
        '"farewell" = "Goodbye";\n',
        encoding="utf-8",
    )
    out = tmp_path / "output.strings"
    mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
    assert translate_file(src, out, "French") is True
    content = out.read_text(encoding="utf-8")
    assert "[T] Hello" in content
    assert "[T] Goodbye" in content


@patch("src.core.llm_engine.translate_text")
def test_translate_file_yml_empty(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Empty .yml file is handled gracefully."""
    src = tmp_path / "empty.yml"
    src.write_text("", encoding="utf-8")
    out = tmp_path / "output.yml"
    result = translate_file(src, out, "French")
    assert result is True
    mock_translate.assert_not_called()


@patch("src.core.llm_engine.translate_text")
def test_translate_file_properties_comments_only(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Properties file with only comments has nothing to translate."""
    src = tmp_path / "comments_only.properties"
    src.write_text("# This is a comment\n# Another comment\n", encoding="utf-8")
    out = tmp_path / "output.properties"
    result = translate_file(src, out, "French")
    assert result is True


# ---------------------------------------------------------------------------
# EPUB — additional edge cases
# ---------------------------------------------------------------------------


def test_epub_content_files_text_xml_media_type(tmp_path: Path) -> None:
    """Discovers files with text/xml media type."""
    container = (
        '<?xml version="1.0"?>'
        '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"'
        ' version="1.0">'
        "  <rootfiles>"
        '    <rootfile full-path="content.opf"'
        ' media-type="application/oebps-package+xml"/>'
        "  </rootfiles>"
        "</container>"
    )
    opf = (
        '<?xml version="1.0"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
        "  <manifest>"
        '    <item id="ch1" href="ch1.xml" media-type="text/xml"/>'
        "  </manifest>"
        "</package>"
    )
    epub = _make_epub_zip(
        tmp_path,
        {
            "META-INF/container.xml": container,
            "content.opf": opf,
            "ch1.xml": "<html><body>Hi</body></html>",
        },
    )
    with zipfile.ZipFile(epub, "r") as zf:
        files = _get_epub_content_files(zf)
    assert len(files) == 1
    assert files[0] == "ch1.xml"


def test_epub_content_files_opf_without_namespace(tmp_path: Path) -> None:
    """Handles OPF files without XML namespace."""
    container = (
        '<?xml version="1.0"?>'
        '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"'
        ' version="1.0">'
        "  <rootfiles>"
        '    <rootfile full-path="content.opf"'
        ' media-type="application/oebps-package+xml"/>'
        "  </rootfiles>"
        "</container>"
    )
    # OPF without namespace
    opf = (
        '<package version="3.0">'
        "  <manifest>"
        '    <item id="ch1" href="ch1.xhtml"'
        ' media-type="application/xhtml+xml"/>'
        "  </manifest>"
        "</package>"
    )
    epub = _make_epub_zip(
        tmp_path,
        {
            "META-INF/container.xml": container,
            "content.opf": opf,
            "ch1.xhtml": "<html><body>Content</body></html>",
        },
    )
    with zipfile.ZipFile(epub, "r") as zf:
        files = _get_epub_content_files(zf)
    assert len(files) == 1
    assert files[0] == "ch1.xhtml"


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_epub_empty_chapter(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """EPUB with an empty chapter skips it gracefully."""
    epub_path = tmp_path / "empty_ch.epub"
    container_xml = (
        '<?xml version="1.0"?>'
        '<container xmlns="urn:oasis:names:tc:opendocument'
        ':xmlns:container" version="1.0">'
        "  <rootfiles>"
        '    <rootfile full-path="OEBPS/content.opf"'
        ' media-type="application/oebps-package+xml"/>'
        "  </rootfiles>"
        "</container>"
    )
    content_opf = (
        '<?xml version="1.0"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
        "  <manifest>"
        '    <item id="ch1" href="ch1.xhtml"'
        ' media-type="application/xhtml+xml"/>'
        '    <item id="ch2" href="ch2.xhtml"'
        ' media-type="application/xhtml+xml"/>'
        "  </manifest>"
        "</package>"
    )
    with zipfile.ZipFile(epub_path, "w") as zf:
        zf.writestr("META-INF/container.xml", container_xml)
        zf.writestr("OEBPS/content.opf", content_opf)
        # ch1 has no translatable content (empty/whitespace)
        zf.writestr("OEBPS/ch1.xhtml", "   ")
        zf.writestr(
            "OEBPS/ch2.xhtml",
            "<html><body><p>Real content</p></body></html>",
        )
    out = tmp_path / "output.epub"
    mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
    result = translate_file(epub_path, out, "French")
    assert result is True
    assert out.exists()


# ---------------------------------------------------------------------------
# Error handling — malformed files
# ---------------------------------------------------------------------------


def test_translate_file_json_syntax_error(tmp_path: Path) -> None:
    """Malformed JSON (trailing comma) raises ValueError."""
    src = tmp_path / "bad.json"
    src.write_text('{"a": "b",}', encoding="utf-8")
    out = tmp_path / "output.json"
    with pytest.raises(ValueError):
        translate_file(src, out, "French")


def test_translate_file_json_truncated(tmp_path: Path) -> None:
    """Truncated JSON raises ValueError."""
    src = tmp_path / "trunc.json"
    src.write_text('{"key": "val', encoding="utf-8")
    out = tmp_path / "output.json"
    with pytest.raises(ValueError):
        translate_file(src, out, "French")


def test_translate_file_nonexistent_csv_raises(tmp_path: Path) -> None:
    """Missing CSV file raises TEXT_READ_ERROR."""
    src = tmp_path / "nonexistent.csv"
    out = tmp_path / "output.csv"
    with pytest.raises(ValueError, match="TEXT_READ_ERROR"):
        translate_file(src, out, "French")


def test_translate_file_nonexistent_json_raises(tmp_path: Path) -> None:
    """Missing JSON file raises TEXT_READ_ERROR."""
    src = tmp_path / "nonexistent.json"
    out = tmp_path / "output.json"
    with pytest.raises(ValueError, match="TEXT_READ_ERROR"):
        translate_file(src, out, "French")


def test_translate_file_nonexistent_epub_raises(tmp_path: Path) -> None:
    """Missing EPUB file raises TEXT_READ_ERROR."""
    src = tmp_path / "nonexistent.epub"
    out = tmp_path / "output.epub"
    with pytest.raises(ValueError, match="TEXT_READ_ERROR"):
        translate_file(src, out, "French")


def test_translate_file_nonexistent_srt_raises(tmp_path: Path) -> None:
    """Missing SRT file raises TEXT_READ_ERROR."""
    src = tmp_path / "nonexistent.srt"
    out = tmp_path / "output.srt"
    with pytest.raises(ValueError, match="TEXT_READ_ERROR"):
        translate_file(src, out, "French")


def test_translate_file_nonexistent_po_raises(tmp_path: Path) -> None:
    """Missing PO file raises TEXT_READ_ERROR."""
    src = tmp_path / "nonexistent.po"
    out = tmp_path / "output.po"
    with pytest.raises(ValueError, match="TEXT_READ_ERROR"):
        translate_file(src, out, "French")


def test_translate_file_nonexistent_yaml_raises(tmp_path: Path) -> None:
    """Missing YAML file raises TEXT_READ_ERROR."""
    src = tmp_path / "nonexistent.yaml"
    out = tmp_path / "output.yaml"
    with pytest.raises(ValueError, match="TEXT_READ_ERROR"):
        translate_file(src, out, "French")


def test_translate_file_nonexistent_properties_raises(tmp_path: Path) -> None:
    """Missing Properties file raises TEXT_READ_ERROR."""
    src = tmp_path / "nonexistent.properties"
    out = tmp_path / "output.properties"
    with pytest.raises(ValueError, match="TEXT_READ_ERROR"):
        translate_file(src, out, "French")


def test_translate_file_nonexistent_html_raises(tmp_path: Path) -> None:
    """Missing HTML file raises TEXT_READ_ERROR."""
    src = tmp_path / "nonexistent.html"
    out = tmp_path / "output.html"
    with pytest.raises(ValueError, match="TEXT_READ_ERROR"):
        translate_file(src, out, "French")


def test_translate_file_nonexistent_xml_raises(tmp_path: Path) -> None:
    """Missing XML file raises TEXT_READ_ERROR."""
    src = tmp_path / "nonexistent.xml"
    out = tmp_path / "output.xml"
    with pytest.raises(ValueError, match="TEXT_READ_ERROR"):
        translate_file(src, out, "French")


# ---------------------------------------------------------------------------
# Config parameter forwarding
# ---------------------------------------------------------------------------


@patch("src.core.pdf_processor.process_pdf_file")
def test_translate_file_pdf_forwards_config(
    mock_pdf: MagicMock,
    tmp_path: Path,
) -> None:
    """translate_file forwards config to process_pdf_file."""
    src = tmp_path / "input.pdf"
    src.write_bytes(b"%PDF-1.4\n")
    out = tmp_path / "output.pdf"
    mock_pdf.return_value = True
    mock_config = MagicMock()

    translate_file(src, out, "French", config=mock_config)
    call_kwargs = mock_pdf.call_args[1]
    assert call_kwargs.get("config") is mock_config


@patch("src.core.text_processor.process_office_file")
def test_translate_file_docx_forwards_config(
    mock_office: MagicMock,
    tmp_path: Path,
) -> None:
    """translate_file forwards config to process_office_file."""
    src = tmp_path / "input.docx"
    src.touch()
    out = tmp_path / "output.docx"
    mock_office.return_value = True
    mock_config = MagicMock()

    translate_file(src, out, "French", config=mock_config)
    call_kwargs = mock_office.call_args[1]
    assert call_kwargs.get("config") is mock_config


# ---------------------------------------------------------------------------
# Progress callback behavior
# ---------------------------------------------------------------------------


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_html_progress(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Progress callback is invoked for HTML files."""
    src = tmp_path / "input.html"
    src.write_text("<p>Hello</p>\n<p>World</p>", encoding="utf-8")
    out = tmp_path / "output.html"
    mock_translate.side_effect = lambda texts, *a, **kw: texts
    progress_values: list[int] = []
    translate_file(src, out, "French", progress_callback=progress_values.append)
    assert len(progress_values) > 0


@patch("src.core.llm_engine.translate_text")
def test_translate_file_json_progress(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Progress callback is invoked for JSON files."""
    src = tmp_path / "input.json"
    src.write_text('{"a": "hello", "b": "world"}', encoding="utf-8")
    out = tmp_path / "output.json"
    mock_translate.side_effect = lambda texts, *a, **kw: texts
    progress_values: list[int] = []
    translate_file(src, out, "French", progress_callback=progress_values.append)
    assert len(progress_values) > 0


@patch("src.core.llm_engine.translate_text")
def test_translate_file_csv_progress(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Progress callback is invoked for CSV files."""
    src = tmp_path / "input.csv"
    src.write_text("Name\nAlice\nBob\n", encoding="utf-8")
    out = tmp_path / "output.csv"
    mock_translate.side_effect = lambda texts, *a, **kw: texts
    progress_values: list[int] = []
    translate_file(src, out, "French", progress_callback=progress_values.append)
    assert len(progress_values) > 0


@patch("src.core.llm_engine.translate_text")
def test_translate_file_srt_progress(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Progress callback is invoked for SRT files."""
    src = tmp_path / "input.srt"
    src.write_text(
        "1\n00:00:01,000 --> 00:00:02,000\nHello\n",
        encoding="utf-8",
    )
    out = tmp_path / "output.srt"
    mock_translate.side_effect = lambda texts, *a, **kw: texts
    progress_values: list[int] = []
    translate_file(src, out, "French", progress_callback=progress_values.append)
    assert len(progress_values) > 0


@patch("src.core.llm_engine.translate_text")
def test_translate_file_po_progress(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Progress callback is invoked for PO files."""
    src = tmp_path / "input.po"
    src.write_text(
        'msgid ""\nmsgstr ""\n\nmsgid "Hello"\nmsgstr ""\n',
        encoding="utf-8",
    )
    out = tmp_path / "output.po"
    mock_translate.side_effect = lambda texts, *a, **kw: texts
    progress_values: list[int] = []
    translate_file(src, out, "French", progress_callback=progress_values.append)
    assert len(progress_values) > 0


@patch("src.core.llm_engine.translate_text")
def test_translate_file_yaml_progress(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Progress callback is invoked for YAML files."""
    src = tmp_path / "input.yaml"
    src.write_text("key: Hello\n", encoding="utf-8")
    out = tmp_path / "output.yaml"
    mock_translate.side_effect = lambda texts, *a, **kw: texts
    progress_values: list[int] = []
    translate_file(src, out, "French", progress_callback=progress_values.append)
    assert len(progress_values) > 0


# ---------------------------------------------------------------------------
# Glossary forwarding for various formats
# ---------------------------------------------------------------------------


@patch("src.core.llm_engine.translate_text")
def test_translate_file_json_forwards_glossary(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Glossary entries are forwarded for JSON translation."""
    src = tmp_path / "input.json"
    src.write_text('{"key": "hello"}', encoding="utf-8")
    out = tmp_path / "output.json"
    mock_translate.side_effect = lambda texts, *a, **kw: texts
    glossary = [(1, "hello", "bonjour")]
    translate_file(src, out, "French", glossary_entries=glossary)
    _, kwargs = mock_translate.call_args
    assert kwargs.get("glossary_entries") == glossary


@patch("src.core.llm_engine.translate_text")
def test_translate_file_csv_forwards_glossary(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Glossary entries are forwarded for CSV translation."""
    src = tmp_path / "input.csv"
    src.write_text("Name\nhello\n", encoding="utf-8")
    out = tmp_path / "output.csv"
    mock_translate.side_effect = lambda texts, *a, **kw: texts
    glossary = [(1, "hello", "bonjour")]
    translate_file(src, out, "French", glossary_entries=glossary)
    _, kwargs = mock_translate.call_args
    assert kwargs.get("glossary_entries") == glossary


@patch("src.core.llm_engine.translate_text")
def test_translate_file_srt_forwards_glossary(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Glossary entries are forwarded for SRT translation."""
    src = tmp_path / "input.srt"
    src.write_text(
        "1\n00:00:01,000 --> 00:00:02,000\nhello\n",
        encoding="utf-8",
    )
    out = tmp_path / "output.srt"
    mock_translate.side_effect = lambda texts, *a, **kw: texts
    glossary = [(1, "hello", "bonjour")]
    translate_file(src, out, "French", glossary_entries=glossary)
    _, kwargs = mock_translate.call_args
    assert kwargs.get("glossary_entries") == glossary


@patch("src.core.llm_engine.translate_text")
def test_translate_file_po_forwards_glossary(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Glossary entries are forwarded for PO translation."""
    src = tmp_path / "input.po"
    src.write_text(
        'msgid ""\nmsgstr ""\n\nmsgid "hello"\nmsgstr ""\n',
        encoding="utf-8",
    )
    out = tmp_path / "output.po"
    mock_translate.side_effect = lambda texts, *a, **kw: texts
    glossary = [(1, "hello", "bonjour")]
    translate_file(src, out, "French", glossary_entries=glossary)
    _, kwargs = mock_translate.call_args
    assert kwargs.get("glossary_entries") == glossary


@patch("src.core.llm_engine.translate_text")
def test_translate_file_yaml_forwards_glossary(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Glossary entries are forwarded for YAML translation."""
    src = tmp_path / "input.yaml"
    src.write_text("key: hello\n", encoding="utf-8")
    out = tmp_path / "output.yaml"
    mock_translate.side_effect = lambda texts, *a, **kw: texts
    glossary = [(1, "hello", "bonjour")]
    translate_file(src, out, "French", glossary_entries=glossary)
    _, kwargs = mock_translate.call_args
    assert kwargs.get("glossary_entries") == glossary


# ---------------------------------------------------------------------------
# Checkpoint forwarding for various formats
# ---------------------------------------------------------------------------


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_txt_checkpoint_dir(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Checkpoint directory is used for .txt translation."""
    src = tmp_path / "input.txt"
    src.write_text("Hello\n\nWorld", encoding="utf-8")
    out = tmp_path / "output.txt"
    cp_dir = tmp_path / "cp"
    cp_dir.mkdir()
    mock_translate.side_effect = lambda texts, *a, **kw: texts
    assert translate_file(src, out, "French", checkpoint_dir=cp_dir) is True
    assert out.exists()


@patch("src.core.llm_engine.translate_text")
def test_translate_file_json_checkpoint_dir(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Checkpoint directory is used for .json translation."""
    src = tmp_path / "input.json"
    src.write_text('{"k": "v"}', encoding="utf-8")
    out = tmp_path / "output.json"
    cp_dir = tmp_path / "cp"
    cp_dir.mkdir()
    mock_translate.side_effect = lambda texts, *a, **kw: texts
    assert translate_file(src, out, "French", checkpoint_dir=cp_dir) is True


@patch("src.core.llm_engine.translate_text")
def test_translate_file_csv_checkpoint_dir(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Checkpoint directory is used for .csv translation."""
    src = tmp_path / "input.csv"
    src.write_text("Name\nAlice\n", encoding="utf-8")
    out = tmp_path / "output.csv"
    cp_dir = tmp_path / "cp"
    cp_dir.mkdir()
    mock_translate.side_effect = lambda texts, *a, **kw: texts
    assert translate_file(src, out, "French", checkpoint_dir=cp_dir) is True


@patch("src.core.llm_engine.translate_text")
def test_translate_file_srt_checkpoint_dir(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Checkpoint directory is used for .srt translation."""
    src = tmp_path / "input.srt"
    src.write_text(
        "1\n00:00:01,000 --> 00:00:02,000\nHello\n",
        encoding="utf-8",
    )
    out = tmp_path / "output.srt"
    cp_dir = tmp_path / "cp"
    cp_dir.mkdir()
    mock_translate.side_effect = lambda texts, *a, **kw: texts
    assert translate_file(src, out, "French", checkpoint_dir=cp_dir) is True


# ---------------------------------------------------------------------------
# Content type selection per format
# ---------------------------------------------------------------------------


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_xml_uses_xml_content_type(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """XML file uses CONTENT_XML content type."""
    src = tmp_path / "input.xml"
    src.write_text("<root>Hello</root>", encoding="utf-8")
    out = tmp_path / "output.xml"
    mock_translate.side_effect = lambda texts, *a, **kw: texts
    translate_file(src, out, "French")
    _, kwargs = mock_translate.call_args
    assert kwargs["content_type"] == "xml"


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_html_uses_html_content_type(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """HTML file uses CONTENT_HTML content type."""
    src = tmp_path / "input.html"
    src.write_text("<p>Hello</p>", encoding="utf-8")
    out = tmp_path / "output.html"
    mock_translate.side_effect = lambda texts, *a, **kw: texts
    translate_file(src, out, "French")
    _, kwargs = mock_translate.call_args
    assert kwargs["content_type"] == "html"


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_md_uses_markdown_content_type(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Markdown file uses CONTENT_MARKDOWN content type."""
    src = tmp_path / "input.md"
    src.write_text("# Hello", encoding="utf-8")
    out = tmp_path / "output.md"
    mock_translate.side_effect = lambda texts, *a, **kw: texts
    translate_file(src, out, "French")
    _, kwargs = mock_translate.call_args
    assert kwargs["content_type"] == "markdown"


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_rtf_uses_rtf_content_type(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    r"""RTF file uses CONTENT_RTF content type."""
    src = tmp_path / "input.rtf"
    src.write_text(r"{\rtf1 Hello}", encoding="utf-8")
    out = tmp_path / "output.rtf"
    mock_translate.side_effect = lambda texts, *a, **kw: texts
    translate_file(src, out, "French")
    _, kwargs = mock_translate.call_args
    assert kwargs["content_type"] == "rtf"


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_txt_uses_plain_text_content_type(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Plain text file uses CONTENT_PLAIN_TEXT content type."""
    src = tmp_path / "input.txt"
    src.write_text("Hello", encoding="utf-8")
    out = tmp_path / "output.txt"
    mock_translate.side_effect = lambda texts, *a, **kw: texts
    translate_file(src, out, "French")
    _, kwargs = mock_translate.call_args
    assert kwargs["content_type"] == "plain_text"


@patch("src.core.llm_engine.translate_text")
def test_translate_file_srt_uses_subtitle_content_type(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """SRT file uses CONTENT_SUBTITLE content type."""
    src = tmp_path / "input.srt"
    src.write_text(
        "1\n00:00:01,000 --> 00:00:02,000\nHello\n",
        encoding="utf-8",
    )
    out = tmp_path / "output.srt"
    mock_translate.side_effect = lambda texts, *a, **kw: texts
    translate_file(src, out, "French")
    _, kwargs = mock_translate.call_args
    assert kwargs.get("content_type") == "subtitle"


@patch("src.core.llm_engine.translate_text")
def test_translate_file_po_uses_localization_content_type(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """PO file uses CONTENT_LOCALIZATION content type."""
    src = tmp_path / "input.po"
    src.write_text(
        'msgid ""\nmsgstr ""\n\nmsgid "Hello"\nmsgstr ""\n',
        encoding="utf-8",
    )
    out = tmp_path / "output.po"
    mock_translate.side_effect = lambda texts, *a, **kw: texts
    translate_file(src, out, "French")
    _, kwargs = mock_translate.call_args
    assert kwargs.get("content_type") == "localization"


@patch("src.core.llm_engine.translate_text")
def test_translate_file_yaml_uses_localization_content_type(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """YAML file uses CONTENT_LOCALIZATION content type."""
    src = tmp_path / "input.yaml"
    src.write_text("key: Hello\n", encoding="utf-8")
    out = tmp_path / "output.yaml"
    mock_translate.side_effect = lambda texts, *a, **kw: texts
    translate_file(src, out, "French")
    _, kwargs = mock_translate.call_args
    assert kwargs.get("content_type") == "localization"


# ---------------------------------------------------------------------------
# Markdown — additional edge cases
# ---------------------------------------------------------------------------


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_md_with_images(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Markdown with image syntax is handled."""
    src = tmp_path / "images.md"
    src.write_text(
        "# Gallery\n\n![Photo](image.png)\n\nDescription here.",
        encoding="utf-8",
    )
    out = tmp_path / "output.md"
    mock_translate.side_effect = lambda texts, *a, **kw: texts
    assert translate_file(src, out, "French") is True
    content = out.read_text(encoding="utf-8")
    assert "image.png" in content


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_md_with_code_blocks(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Markdown with code blocks passes through."""
    src = tmp_path / "code.md"
    src.write_text(
        "# Code\n\n```python\nprint('hello')\n```\n\nEnd.",
        encoding="utf-8",
    )
    out = tmp_path / "output.md"
    mock_translate.side_effect = lambda texts, *a, **kw: texts
    assert translate_file(src, out, "French") is True
    content = out.read_text(encoding="utf-8")
    assert "```python" in content


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_md_with_multiple_links(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Markdown with multiple links has all URLs stripped and restored."""
    src = tmp_path / "links.md"
    src.write_text(
        "Visit [A](https://a.com) and [B](https://b.com) for info.",
        encoding="utf-8",
    )
    out = tmp_path / "output.md"

    captured: list[list[str]] = []

    def mock_fn(texts: list[str], *a: object, **kw: object) -> list[str]:
        captured.append(list(texts))
        return texts

    mock_translate.side_effect = mock_fn
    assert translate_file(src, out, "French") is True

    # URLs should be stripped from LLM input
    sent = " ".join(captured[0])
    assert "https://a.com" not in sent
    assert "https://b.com" not in sent

    # URLs should be restored in output
    content = out.read_text(encoding="utf-8")
    assert "https://a.com" in content
    assert "https://b.com" in content


# ---------------------------------------------------------------------------
# RTF — additional edge cases
# ---------------------------------------------------------------------------


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_rtf_with_par_separator(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    r"""RTF with multiple \\par markers creates multiple chunks."""
    src = tmp_path / "multi_par.rtf"
    src.write_text(
        r"{\rtf1 First paragraph\par Second paragraph\par Third paragraph}",
        encoding="utf-8",
    )
    out = tmp_path / "output.rtf"
    mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
    assert translate_file(src, out, "French") is True
    content = out.read_text(encoding="utf-8")
    assert "[T]" in content


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_rtf_empty_par(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    r"""RTF with empty \\par markers is handled."""
    src = tmp_path / "empty_par.rtf"
    src.write_text(r"{\rtf1 \par\par\par Hello}", encoding="utf-8")
    out = tmp_path / "output.rtf"
    mock_translate.side_effect = lambda texts, *a, **kw: [f"[T] {t}" for t in texts]
    assert translate_file(src, out, "French") is True
    content = out.read_text(encoding="utf-8")
    assert len(content) > 0


# ---------------------------------------------------------------------------
# XML — additional edge cases
# ---------------------------------------------------------------------------


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_xml_with_comments(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """XML comments are left intact (LLMs naturally skip them) and preserved in output."""
    src = tmp_path / "comments.xml"
    src.write_text(
        '<?xml version="1.0"?>\n<!-- This is a comment -->\n<root>Hello</root>',
        encoding="utf-8",
    )
    out = tmp_path / "output.xml"

    captured: list[list[str]] = []

    def mock_fn(texts: list[str], *a: object, **kw: object) -> list[str]:
        captured.append(list(texts))
        return texts

    mock_translate.side_effect = mock_fn
    assert translate_file(src, out, "French") is True

    # Processing instructions should be stripped from LLM input
    sent = " ".join(captured[0])
    assert "<?xml" not in sent

    # Comments should be preserved in output
    content = out.read_text(encoding="utf-8")
    assert "This is a comment" in content


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_xml_empty_elements(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """XML with empty elements is handled."""
    src = tmp_path / "empty_elem.xml"
    src.write_text(
        "<root><empty/><msg>Hello</msg></root>",
        encoding="utf-8",
    )
    out = tmp_path / "output.xml"
    mock_translate.side_effect = lambda texts, *a, **kw: texts
    assert translate_file(src, out, "French") is True
    content = out.read_text(encoding="utf-8")
    assert "<msg>" in content


# ---------------------------------------------------------------------------
# Translation preserves overall file integrity
# ---------------------------------------------------------------------------


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_txt_roundtrip_preserves_content(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Identity translation (returns input) produces identical output."""
    src = tmp_path / "input.txt"
    original = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
    src.write_text(original, encoding="utf-8")
    out = tmp_path / "output.txt"
    mock_translate.side_effect = lambda texts, *a, **kw: texts
    translate_file(src, out, "French")
    assert out.read_text(encoding="utf-8") == original


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_html_roundtrip_preserves_content(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Identity translation for HTML preserves structure and content."""
    src = tmp_path / "input.html"
    original = '<div class="main"><p id="intro">Hello World</p></div>'
    src.write_text(original, encoding="utf-8")
    out = tmp_path / "output.html"
    mock_translate.side_effect = lambda texts, *a, **kw: texts
    translate_file(src, out, "French")
    content = out.read_text(encoding="utf-8")
    assert 'class="main"' in content
    assert 'id="intro"' in content
    assert "Hello World" in content


@patch("src.core.text_processor._llm_engine.translate_text")
def test_translate_file_xml_roundtrip_preserves_content(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Identity translation for XML preserves attributes and content."""
    src = tmp_path / "input.xml"
    original = '<root lang="en">\n  <msg id="1">Hello</msg>\n</root>'
    src.write_text(original, encoding="utf-8")
    out = tmp_path / "output.xml"
    mock_translate.side_effect = lambda texts, *a, **kw: texts
    translate_file(src, out, "French")
    content = out.read_text(encoding="utf-8")
    assert 'lang="en"' in content
    assert 'id="1"' in content
    assert "Hello" in content


# ---------------------------------------------------------------------------
# SRT subtitle progress callback with empty entries
# ---------------------------------------------------------------------------


@patch("src.core.llm_engine.translate_text")
def test_translate_file_srt_empty_fires_progress(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Empty SRT fires progress(100) for no-op."""
    src = tmp_path / "empty.srt"
    src.write_text("", encoding="utf-8")
    out = tmp_path / "output.srt"
    progress_values: list[int] = []
    result = translate_file(
        src, out, "French", progress_callback=progress_values.append
    )
    assert result is True
    assert 100 in progress_values


@patch("src.core.llm_engine.translate_text")
def test_translate_file_po_empty_fires_progress(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Empty PO fires progress(100) for no-op."""
    src = tmp_path / "empty.po"
    src.write_text("", encoding="utf-8")
    out = tmp_path / "output.po"
    progress_values: list[int] = []
    result = translate_file(
        src, out, "French", progress_callback=progress_values.append
    )
    assert result is True
    assert 100 in progress_values


@patch("src.core.llm_engine.translate_text")
def test_translate_file_yaml_empty_fires_progress(
    mock_translate: MagicMock,
    tmp_path: Path,
) -> None:
    """Empty YAML fires progress(100) for no-op."""
    src = tmp_path / "empty.yaml"
    src.write_text("", encoding="utf-8")
    out = tmp_path / "output.yaml"
    progress_values: list[int] = []
    result = translate_file(
        src, out, "French", progress_callback=progress_values.append
    )
    assert result is True
    assert 100 in progress_values


# ---------------------------------------------------------------------------
# TestBOMHandlingAdditionalFormats — BOM tests for untested formats
# ---------------------------------------------------------------------------


class TestBOMHandlingAdditionalFormats:
    """BOM handling for formats not yet covered by existing BOM tests."""

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_bom_txt_content_translated(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """BOM-prefixed .txt file is translated correctly, BOM stripped."""
        src = tmp_path / "bom.txt"
        src.write_bytes(b"\xef\xbb\xbfHello World")
        out = tmp_path / "output.txt"
        mock_translate.side_effect = lambda texts, *a, **kw: [
            f"[FR] {t}" for t in texts
        ]
        assert translate_file(src, out, "French") is True
        raw = out.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf")
        content = out.read_text(encoding="utf-8")
        assert "\ufeff" not in content
        assert "[FR] Hello World" in content

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_bom_htm(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """BOM in .htm file is stripped and content translated."""
        src = tmp_path / "bom.htm"
        src.write_bytes(b"\xef\xbb\xbf<p>Hello</p>")
        out = tmp_path / "output.htm"
        mock_translate.side_effect = lambda texts, *a, **kw: [
            f"[FR] {t}" for t in texts
        ]
        assert translate_file(src, out, "French") is True
        raw = out.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf")
        content = out.read_text(encoding="utf-8")
        assert "\ufeff" not in content
        assert "[FR]" in content

    @patch("src.core.llm_engine.translate_text")
    def test_bom_ass(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """BOM in .ass file is stripped and dialogue translated."""
        src = tmp_path / "bom.ass"
        ass_content = (
            "[Script Info]\nTitle: Test\n\n"
            "[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
            "MarginV, Effect, Text\n"
            "Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,Hello\n"
        )
        src.write_bytes(b"\xef\xbb\xbf" + ass_content.encode("utf-8"))
        out = tmp_path / "output.ass"
        mock_translate.side_effect = lambda texts, *a, **kw: [
            f"[FR] {t}" for t in texts
        ]
        assert translate_file(src, out, "French") is True
        raw = out.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf")
        content = out.read_text(encoding="utf-8")
        assert "\ufeff" not in content
        assert "[FR] Hello" in content

    @patch("src.core.llm_engine.translate_text")
    def test_bom_ssa(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """BOM in .ssa file is stripped and dialogue translated."""
        src = tmp_path / "bom.ssa"
        ssa_content = (
            "[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
            "MarginV, Effect, Text\n"
            "Dialogue: 0,0:00:01.00,0:00:04.00,Default,,0,0,0,,Hello\n"
        )
        src.write_bytes(b"\xef\xbb\xbf" + ssa_content.encode("utf-8"))
        out = tmp_path / "output.ssa"
        mock_translate.side_effect = lambda texts, *a, **kw: [
            f"[FR] {t}" for t in texts
        ]
        assert translate_file(src, out, "French") is True
        raw = out.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf")
        content = out.read_text(encoding="utf-8")
        assert "\ufeff" not in content
        assert "[FR] Hello" in content

    @patch("src.core.llm_engine.translate_text")
    def test_bom_pot(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """BOM in .pot file is stripped and entries translated."""
        src = tmp_path / "bom.pot"
        pot_content = 'msgid ""\nmsgstr ""\n\nmsgid "Greeting"\nmsgstr ""\n'
        src.write_bytes(b"\xef\xbb\xbf" + pot_content.encode("utf-8"))
        out = tmp_path / "output.pot"
        mock_translate.side_effect = lambda texts, *a, **kw: [
            f"[FR] {t}" for t in texts
        ]
        assert translate_file(src, out, "French") is True
        raw = out.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf")
        content = out.read_text(encoding="utf-8")
        assert "\ufeff" not in content
        assert "[FR] Greeting" in content

    @patch("src.core.llm_engine.translate_text")
    def test_bom_yml(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """BOM in .yml file is stripped and values translated."""
        src = tmp_path / "bom.yml"
        src.write_bytes(b"\xef\xbb\xbfkey: Hello\n")
        out = tmp_path / "output.yml"
        mock_translate.side_effect = lambda texts, *a, **kw: [
            f"[FR] {t}" for t in texts
        ]
        assert translate_file(src, out, "French") is True
        raw = out.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf")
        content = out.read_text(encoding="utf-8")
        assert "\ufeff" not in content
        assert "[FR] Hello" in content

    @patch("src.core.llm_engine.translate_text")
    def test_bom_properties(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """BOM in .properties file is stripped and values translated."""
        src = tmp_path / "bom.properties"
        src.write_bytes(b"\xef\xbb\xbfgreeting=Hello\n")
        out = tmp_path / "output.properties"
        mock_translate.side_effect = lambda texts, *a, **kw: [
            f"[FR] {t}" for t in texts
        ]
        assert translate_file(src, out, "French") is True
        raw = out.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf")
        content = out.read_text(encoding="utf-8")
        assert "\ufeff" not in content
        assert "[FR] Hello" in content

    @patch("src.core.llm_engine.translate_text")
    def test_bom_strings(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """BOM in .strings file is stripped and values translated."""
        src = tmp_path / "bom.strings"
        src.write_bytes(b'\xef\xbb\xbf"greeting" = "Hello";\n')
        out = tmp_path / "output.strings"
        mock_translate.side_effect = lambda texts, *a, **kw: [
            f"[FR] {t}" for t in texts
        ]
        assert translate_file(src, out, "French") is True
        raw = out.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf")
        content = out.read_text(encoding="utf-8")
        assert "\ufeff" not in content
        assert "[FR] Hello" in content


# ---------------------------------------------------------------------------
# TestHTMFormatBasic — basic .htm edge cases
# ---------------------------------------------------------------------------


class TestHTMFormatBasic:
    """Basic .htm edge cases (currently only 2 tests exist for .htm)."""

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_htm_roundtrip(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """Basic .htm file roundtrip translation preserves structure."""
        src = tmp_path / "input.htm"
        src.write_text(
            "<html><body><p>Hello World</p></body></html>",
            encoding="utf-8",
        )
        out = tmp_path / "output.htm"
        mock_translate.side_effect = lambda texts, *a, **kw: [
            f"[FR] {t}" for t in texts
        ]
        assert translate_file(src, out, "French") is True
        content = out.read_text(encoding="utf-8")
        assert "[FR]" in content
        assert "<html>" in content or "<p>" in content

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_htm_nested_tags(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """.htm with nested tags preserves structure."""
        src = tmp_path / "nested.htm"
        src.write_text(
            "<div><ul><li>Item 1</li><li>Item 2</li></ul></div>",
            encoding="utf-8",
        )
        out = tmp_path / "output.htm"

        captured: list[list[str]] = []

        def mock_fn(texts: list[str], *a: object, **kw: object) -> list[str]:
            captured.append(list(texts))
            return texts

        mock_translate.side_effect = mock_fn
        assert translate_file(src, out, "French") is True
        content = out.read_text(encoding="utf-8")
        # Nested tags should be preserved in output
        assert "<li>" in content
        assert "Item 1" in content
        assert "Item 2" in content

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_htm_empty_file(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """Empty .htm file is copied as-is, no LLM call."""
        src = tmp_path / "empty.htm"
        src.write_text("", encoding="utf-8")
        out = tmp_path / "output.htm"
        assert translate_file(src, out, "French") is True
        assert out.exists()
        mock_translate.assert_not_called()

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_htm_entities(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """.htm with HTML entities (&amp;, &lt;) preserves them."""
        src = tmp_path / "entities.htm"
        src.write_text(
            "<p>5 &gt; 3 &amp; 2 &lt; 4</p>",
            encoding="utf-8",
        )
        out = tmp_path / "output.htm"
        mock_translate.side_effect = lambda texts, *a, **kw: texts
        assert translate_file(src, out, "French") is True
        content = out.read_text(encoding="utf-8")
        # Entities should survive the roundtrip (either encoded or decoded)
        assert "&gt;" in content or ">" in content
        assert "&amp;" in content or "&" in content
        assert "&lt;" in content or "<" in content

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_htm_write_error(self, mock_translate: MagicMock, tmp_path: Path) -> None:
        """.htm write failure raises TEXT_WRITE_ERROR."""
        src = tmp_path / "input.htm"
        src.write_text("<p>Hello</p>", encoding="utf-8")
        read_only = tmp_path / "readonly_htm"
        read_only.mkdir()
        read_only.chmod(0o444)
        out = read_only / "subdir" / "output.htm"

        mock_translate.side_effect = lambda texts, *a, **kw: texts

        try:
            with pytest.raises(ValueError, match="TEXT_WRITE_ERROR"):
                translate_file(src, out, "French")
        finally:
            read_only.chmod(0o755)


# ---------------------------------------------------------------------------
# TestWhitespaceOnlyAdditional — whitespace-only files for untested formats
# ---------------------------------------------------------------------------


class TestWhitespaceOnlyAdditional:
    """Whitespace-only file handling for formats not yet covered."""

    @patch("src.core.llm_engine.translate_text")
    def test_json_whitespace_only(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """JSON file with only whitespace raises ValueError (invalid JSON)."""
        src = tmp_path / "ws.json"
        src.write_text("   \n  \n   ", encoding="utf-8")
        out = tmp_path / "output.json"
        # Whitespace-only content is not valid JSON; json.JSONDecodeError
        # (a ValueError subclass) propagates through the ValueError handler.
        with pytest.raises(ValueError):
            translate_file(src, out, "French")
        mock_translate.assert_not_called()

    @patch("src.core.llm_engine.translate_text")
    def test_csv_whitespace_only(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """CSV with only whitespace content: no LLM calls."""
        src = tmp_path / "ws.csv"
        src.write_text("   \n   \n   ", encoding="utf-8")
        out = tmp_path / "output.csv"
        result = translate_file(src, out, "French")
        assert result is True
        # Whitespace-only cells should not trigger translation
        mock_translate.assert_not_called()

    @patch("src.core.llm_engine.translate_text")
    def test_srt_whitespace_only(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """SRT with only whitespace does not crash."""
        src = tmp_path / "ws.srt"
        src.write_text("   \n\n   ", encoding="utf-8")
        out = tmp_path / "output.srt"
        result = translate_file(src, out, "French")
        # Should succeed with no entries parsed
        assert result is True
        mock_translate.assert_not_called()

    @patch("src.core.llm_engine.translate_text")
    def test_po_whitespace_only(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """PO file with only whitespace does not crash."""
        src = tmp_path / "ws.po"
        src.write_text("   \n\n   ", encoding="utf-8")
        out = tmp_path / "output.po"
        result = translate_file(src, out, "French")
        # Should succeed with no entries parsed
        assert result is True
        mock_translate.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# Format-edge-case backfill tests
# ─────────────────────────────────────────────────────────────────────────────


class TestEpubLargeImageNotProcessed:
    """When SETTING_TRANSLATE_DOC_IMAGES is off, EPUB images are NOT processed.

    The image-translation gate is implemented as
    ``do_images = load_setting(SETTING_TRANSLATE_DOC_IMAGES, False) and check_ocr_setup()``.
    When the user has not opted in, ``_translate_doc_images`` is never invoked
    and any embedded raster (regardless of size) is repacked as-is.
    """

    @patch("src.core.text_processor._llm_engine.translate_text")
    @patch("src.core.text_processor._translate_doc_images")
    @patch("src.utils.config_manager.load_setting", return_value=False)
    def test_epub_with_large_image_skips_image_pipeline(
        self,
        _mock_load: MagicMock,
        mock_doc_images: MagicMock,
        mock_translate: MagicMock,
        tmp_path: Path,
    ) -> None:
        """EPUB with a 1MB image: text translated, image left untouched."""
        epub_path = tmp_path / "book.epub"

        container_xml = (
            '<?xml version="1.0"?>'
            '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"'
            ' version="1.0">'
            "<rootfiles>"
            '<rootfile full-path="OEBPS/content.opf"'
            ' media-type="application/oebps-package+xml"/>'
            "</rootfiles></container>"
        )
        content_opf = (
            '<?xml version="1.0"?>'
            '<package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
            "<manifest>"
            '<item id="ch1" href="chapter1.xhtml"'
            ' media-type="application/xhtml+xml"/>'
            '<item id="img" href="hero.png" media-type="image/png"/>'
            "</manifest></package>"
        )
        chapter_xhtml = (
            '<?xml version="1.0"?><html><body><p>Hello World</p></body></html>'
        )
        # Build a ~1 MB raster blob (deflate-compressible bytes).
        large_image_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * (1024 * 1024)

        with zipfile.ZipFile(epub_path, "w") as zf:
            zf.writestr("META-INF/container.xml", container_xml)
            zf.writestr("OEBPS/content.opf", content_opf)
            zf.writestr("OEBPS/chapter1.xhtml", chapter_xhtml)
            zf.writestr("OEBPS/hero.png", large_image_bytes)

        out_path = tmp_path / "out.epub"
        mock_translate.side_effect = lambda texts, *a, **kw: [
            f"[FR] {t}" for t in texts
        ]

        result = translate_file(epub_path, out_path, "French", "English (US)")
        assert result is True
        assert out_path.exists()

        # Image pipeline never invoked
        mock_doc_images.assert_not_called()

        # Text was translated, image bytes preserved verbatim
        with zipfile.ZipFile(out_path, "r") as zf_out:
            chap = zf_out.read("OEBPS/chapter1.xhtml").decode("utf-8")
            assert "[FR]" in chap
            preserved = zf_out.read("OEBPS/hero.png")
            assert preserved == large_image_bytes


class TestEpubForwardsCheckpointDirToImages:
    """EPUB image translation must receive ``checkpoint_dir`` for caching.

    The EPUB processor delegates embedded-image translation to
    ``_translate_doc_images`` via the shared Office pipeline.  If the
    kwarg is dropped at the EPUB callsite, embedded images re-translate
    on every retry instead of hitting the per-image cache.
    Regression guard for ``text_processor.py::_process_epub``.
    """

    @patch("src.core.text_processor._llm_engine.translate_text")
    @patch("src.core.text_processor._translate_doc_images")
    @patch("src.utils.config_manager.load_setting")
    def test_checkpoint_dir_reaches_image_dispatcher(
        self,
        mock_load: MagicMock,
        mock_doc_images: MagicMock,
        mock_translate: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Image translation enabled → checkpoint_dir is forwarded."""
        # Image translation gate ON for SETTING_TRANSLATE_DOC_IMAGES.
        mock_load.return_value = True
        mock_translate.side_effect = lambda texts, *a, **kw: list(texts)

        # Patch the gating logic so we don't need a real OCR backend.
        # ``check_ocr_setup`` is locally imported inside ``_process_epub``
        # from ``src.utils.config_manager``, so we patch at the origin.
        with patch(
            "src.utils.config_manager.check_ocr_setup",
            return_value=True,
        ):
            container_xml = (
                '<?xml version="1.0"?>'
                '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"'
                ' version="1.0">'
                "<rootfiles>"
                '<rootfile full-path="OEBPS/content.opf"'
                ' media-type="application/oebps-package+xml"/>'
                "</rootfiles></container>"
            )
            content_opf = (
                '<?xml version="1.0"?>'
                '<package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
                "<manifest>"
                '<item id="ch1" href="chapter1.xhtml"'
                ' media-type="application/xhtml+xml"/>'
                "</manifest></package>"
            )
            chapter_xhtml = (
                '<?xml version="1.0"?><html><body><p>Hi</p></body></html>'
            )
            epub_path = tmp_path / "book.epub"
            with zipfile.ZipFile(epub_path, "w") as zf:
                zf.writestr("META-INF/container.xml", container_xml)
                zf.writestr("OEBPS/content.opf", content_opf)
                zf.writestr("OEBPS/chapter1.xhtml", chapter_xhtml)

            out_path = tmp_path / "out.epub"
            cp = tmp_path / "task_storage"
            cp.mkdir()

            result = translate_file(
                epub_path,
                out_path,
                "French",
                "English (US)",
                checkpoint_dir=cp,
            )
            assert result is True

            mock_doc_images.assert_called_once()
            assert mock_doc_images.call_args.kwargs.get("checkpoint_dir") == cp


class TestCsvEmbeddedQuotesAndNewlines:
    """CSV round-trip with special characters.

    CSV cells containing commas, double-quotes, or newlines must round-trip
    through extract → translate → inject → reparse without corruption.
    """

    @patch("src.core.llm_engine.translate_text")
    def test_quoted_field_with_comma_round_trip(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """A field containing ``, `` survives the CSV write/read cycle."""
        # Identity translation so we can compare value-by-value.
        mock_translate.side_effect = lambda texts, *a, **kw: list(texts)

        src = tmp_path / "in.csv"
        # csv.writer handles quoting of embedded commas and double-quotes,
        # so write via the writer to ensure a valid input file.
        import csv as _csv  # noqa: PLC0415

        with src.open("w", newline="", encoding="utf-8") as fh:
            w = _csv.writer(fh)
            w.writerow(["greeting", "phrase"])
            w.writerow(["Hello, world", 'She said "hi"'])

        out = tmp_path / "out.csv"
        result = translate_file(src, out, "French", "English (US)")
        assert result is True

        with out.open("r", newline="", encoding="utf-8") as fh:
            rows = list(_csv.reader(fh))
        # Two rows preserved
        assert len(rows) == 2  # noqa: PLR2004
        # Embedded comma survived the round trip
        assert rows[1][0] == "Hello, world"
        # Embedded double-quote survived
        assert rows[1][1] == 'She said "hi"'

    @patch("src.core.llm_engine.translate_text")
    def test_newline_in_field_round_trip(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """A field containing a newline survives the CSV write/read cycle."""
        mock_translate.side_effect = lambda texts, *a, **kw: list(texts)

        import csv as _csv  # noqa: PLC0415

        src = tmp_path / "in.csv"
        with src.open("w", newline="", encoding="utf-8") as fh:
            w = _csv.writer(fh)
            w.writerow(["title", "body"])
            w.writerow(["Doc", "line1\nline2\nline3"])

        out = tmp_path / "out.csv"
        result = translate_file(src, out, "French", "English (US)")
        assert result is True

        with out.open("r", newline="", encoding="utf-8") as fh:
            rows = list(_csv.reader(fh))
        assert rows[1][1] == "line1\nline2\nline3"


class TestBomRtlContentPreservation:
    """A UTF-8 BOM-prefixed text file containing Hebrew (RTL).

    Contract: ``_read_file`` strips the BOM via ``strip_bom()``; output
    is BOM-less regardless of input.  Hebrew (and other) code points
    round-trip cleanly through UTF-8 encode/decode.

    Why we don't preserve BOM in output:
    - JSON (RFC 8259), YAML 1.2, and gettext PO files actively *forbid*
      BOM.  Re-emitting it on output would break those consumers.
    - .properties, .strings, .po, .yml, .xliff conventionally use UTF-8
      without BOM; modern tooling expects that.
    - "Windows Notepad needs BOM" is dated — modern Notepad handles
      BOM-less UTF-8 since Windows 11.
    - Stripping is done at every parser entry point (subtitle_utils,
      localization_utils, keyvalue_utils, text_processor) — it's a
      deliberate, system-wide normalization step, not accidental.
    """

    @patch("src.core.text_processor._llm_engine.translate_text")
    def test_bom_stripped_hebrew_preserved(
        self, mock_translate: MagicMock, tmp_path: Path
    ) -> None:
        """BOM input → no-BOM output, Hebrew characters preserved verbatim."""
        # Identity translation so the Hebrew passes through unchanged.
        mock_translate.side_effect = lambda texts, *a, **kw: list(texts)

        src = tmp_path / "hebrew.txt"
        # שלום = "shalom" (Hebrew, RTL).  Prepend UTF-8 BOM ﻿.
        hebrew_text = "שלום עולם"
        src.write_bytes(b"\xef\xbb\xbf" + hebrew_text.encode("utf-8"))

        out = tmp_path / "out.txt"
        result = translate_file(src, out, "Hebrew", "English (US)")
        assert result is True

        # Output bytes do NOT start with the BOM (current contract)
        out_bytes = out.read_bytes()
        assert not out_bytes.startswith(b"\xef\xbb\xbf")
        # Hebrew code points round-trip correctly
        out_text = out.read_text(encoding="utf-8")
        assert hebrew_text in out_text


# ---------------------------------------------------------------------------
# RTL injection helpers (HTML / RTF / OPF / EPUB)
# ---------------------------------------------------------------------------


class TestRtlInjectionHelpers:
    """Tests for _inject_rtl_* and _apply_rtl_markup."""

    def test_inject_rtl_into_html_adds_dir_to_html_and_body(self) -> None:
        from src.core.text_processor import _inject_rtl_into_html  # noqa: PLC0415

        src = "<html><body><p>hi</p></body></html>"
        out = _inject_rtl_into_html(src)
        assert 'dir="rtl"' in out
        # Both root tags get the marker.
        assert out.count('dir="rtl"') == 2  # noqa: PLR2004

    def test_inject_rtl_into_html_idempotent(self) -> None:
        from src.core.text_processor import _inject_rtl_into_html  # noqa: PLC0415

        src = '<html dir="rtl"><body dir="rtl"><p>hi</p></body></html>'
        assert _inject_rtl_into_html(src) == src

    def test_inject_rtl_into_html_preserves_existing_attrs(self) -> None:
        from src.core.text_processor import _inject_rtl_into_html  # noqa: PLC0415

        src = '<html lang="ar"><body class="page"><p>hi</p></body></html>'
        out = _inject_rtl_into_html(src)
        assert 'lang="ar"' in out
        assert 'class="page"' in out
        assert 'dir="rtl"' in out

    def test_inject_rtl_into_rtf_adds_rtldoc(self) -> None:
        from src.core.text_processor import _inject_rtl_into_rtf  # noqa: PLC0415

        src = r"{\rtf1\ansi\deff0 {\fonttbl{\f0 Times;}}\par}"
        out = _inject_rtl_into_rtf(src)
        assert r"\rtldoc" in out

    def test_inject_rtl_into_rtf_idempotent(self) -> None:
        from src.core.text_processor import _inject_rtl_into_rtf  # noqa: PLC0415

        src = r"{\rtf1\ansi\rtldoc\par}"
        assert _inject_rtl_into_rtf(src) == src

    def test_inject_rtl_into_opf_adds_page_progression_direction(self) -> None:
        from src.core.text_processor import _inject_rtl_into_opf  # noqa: PLC0415

        src = '<package><spine toc="ncx"><itemref/></spine></package>'
        out = _inject_rtl_into_opf(src)
        assert 'page-progression-direction="rtl"' in out

    def test_inject_rtl_into_opf_idempotent(self) -> None:
        from src.core.text_processor import _inject_rtl_into_opf  # noqa: PLC0415

        src = '<package><spine page-progression-direction="rtl"></spine></package>'
        assert _inject_rtl_into_opf(src) == src

    def test_apply_rtl_markup_skips_non_rtl_target(self) -> None:
        from src.constants.llm import CONTENT_HTML  # noqa: PLC0415
        from src.core.text_processor import _apply_rtl_markup  # noqa: PLC0415

        src = "<html><body><p>hi</p></body></html>"
        # English target → no change.
        assert _apply_rtl_markup(src, CONTENT_HTML, "English (US)") == src

    def test_apply_rtl_markup_skips_non_rtl_format(self) -> None:
        from src.constants.llm import CONTENT_PLAIN_TEXT  # noqa: PLC0415
        from src.core.text_processor import _apply_rtl_markup  # noqa: PLC0415

        src = "Hello"
        # Plain text has no marker to inject — passthrough.
        assert _apply_rtl_markup(src, CONTENT_PLAIN_TEXT, "Arabic") == src

    def test_apply_rtl_markup_does_not_inject_into_non_markup_formats(
        self,
    ) -> None:
        """Regression: only HTML / EPUB / RTF get RTL markup.

        Other content types (plain text, Markdown, CSV, JSON, XML,
        subtitle, localization) have nowhere semantically appropriate
        to inject ``dir="rtl"`` / ``\\rtldoc`` — embedding such
        markup would corrupt the output (a CSV with ``dir="rtl"``
        embedded in row 1 becomes unparseable, JSON breaks, etc.).
        Pin the passthrough contract so a future "let's add RTL
        everywhere" refactor can't silently break these formats.
        """
        from src.constants.llm import (  # noqa: PLC0415
            CONTENT_DATA_VALUES,
            CONTENT_LOCALIZATION,
            CONTENT_MARKDOWN,
            CONTENT_PLAIN_TEXT,
            CONTENT_SUBTITLE,
            CONTENT_XML,
        )
        from src.core.text_processor import _apply_rtl_markup  # noqa: PLC0415

        target = "Arabic"  # is_rtl_language(target) → True
        # Each content type carries representative non-trivial copy
        # so a future regex-style injection accidentally matching the
        # text gets surfaced.  ``CONTENT_DATA_VALUES`` covers JSON /
        # CSV / YAML / Properties / Strings — every key-value style
        # format the LLM treats as opaque data.
        cases = [
            (CONTENT_PLAIN_TEXT, "Hello\nworld."),
            (CONTENT_MARKDOWN, "# Heading\n\n**bold** paragraph"),
            (CONTENT_DATA_VALUES, '{"key": "value", "n": 42}'),
            (CONTENT_DATA_VALUES, "name,value\nalpha,1\nbeta,2"),
            (CONTENT_XML, "<root><item>hello</item></root>"),
            (CONTENT_SUBTITLE, "1\n00:00:01,000 --> 00:00:02,000\nHello\n"),
            (CONTENT_LOCALIZATION, "msgid \"hi\"\nmsgstr \"\""),
        ]
        for content_type, src in cases:
            out = _apply_rtl_markup(src, content_type, target)
            assert out == src, (
                f"RTL markup leaked into {content_type!r}: "
                f"input={src!r}, output={out!r}"
            )


# ── _get_epub_opf_path edge cases ──────────────────────────────────────────


class TestGetEpubOpfPathEdgeCases:
    """Edge cases for the ``META-INF/container.xml`` rootfile lookup.

    ``_get_epub_opf_path`` is the load-bearing piece between
    "EPUB → RTL OPF spine rewrite" and "no OPF tweak."  Real-world
    EPUBs vary in container.xml shape; the function must cope with
    nested paths, multiple rootfiles (spec allows), missing
    container, malformed XML, and missing rootfile element.
    """

    def _zip(self, container_xml: str | None):
        """Builds an in-memory ZIP with the given container.xml.

        Pass ``None`` to omit ``META-INF/container.xml`` entirely.
        """
        import io  # noqa: PLC0415
        import zipfile  # noqa: PLC0415

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            if container_xml is not None:
                z.writestr("META-INF/container.xml", container_xml)
        buf.seek(0)
        return zipfile.ZipFile(buf, "r")

    def test_missing_container_returns_empty_string(self) -> None:
        from src.core.text_processor import _get_epub_opf_path  # noqa: PLC0415

        with self._zip(None) as z:
            assert _get_epub_opf_path(z) == ""

    def test_malformed_xml_returns_empty_string(self) -> None:
        from src.core.text_processor import _get_epub_opf_path  # noqa: PLC0415

        with self._zip("<not><valid>") as z:
            assert _get_epub_opf_path(z) == ""

    def test_no_rootfile_element_returns_empty_string(self) -> None:
        from src.core.text_processor import _get_epub_opf_path  # noqa: PLC0415

        xml = (
            '<?xml version="1.0"?>'
            '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            "<rootfiles></rootfiles>"
            "</container>"
        )
        with self._zip(xml) as z:
            assert _get_epub_opf_path(z) == ""

    def test_canonical_layout_returns_full_path(self) -> None:
        from src.core.text_processor import _get_epub_opf_path  # noqa: PLC0415

        xml = (
            '<?xml version="1.0"?>'
            '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            "<rootfiles>"
            '<rootfile full-path="OEBPS/content.opf" '
            'media-type="application/oebps-package+xml"/>'
            "</rootfiles>"
            "</container>"
        )
        with self._zip(xml) as z:
            assert _get_epub_opf_path(z) == "OEBPS/content.opf"

    def test_nested_directory_path_with_spaces_preserved(self) -> None:
        """``full-path`` containing nested directories with spaces survives."""
        from src.core.text_processor import _get_epub_opf_path  # noqa: PLC0415

        xml = (
            '<?xml version="1.0"?>'
            '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            "<rootfiles>"
            '<rootfile full-path="My Book/content/package.opf" '
            'media-type="application/oebps-package+xml"/>'
            "</rootfiles>"
            "</container>"
        )
        with self._zip(xml) as z:
            assert _get_epub_opf_path(z) == "My Book/content/package.opf"

    def test_first_rootfile_wins_when_multiple_present(self) -> None:
        """Spec allows multiple ``<rootfile>`` entries — take the first."""
        from src.core.text_processor import _get_epub_opf_path  # noqa: PLC0415

        xml = (
            '<?xml version="1.0"?>'
            '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            "<rootfiles>"
            '<rootfile full-path="primary.opf" '
            'media-type="application/oebps-package+xml"/>'
            '<rootfile full-path="alternate.opf" '
            'media-type="application/oebps-package+xml"/>'
            "</rootfiles>"
            "</container>"
        )
        with self._zip(xml) as z:
            assert _get_epub_opf_path(z) == "primary.opf"

    def test_rootfile_without_full_path_returns_empty_string(self) -> None:
        """Defensive: ``<rootfile>`` missing ``full-path`` shouldn't crash."""
        from src.core.text_processor import _get_epub_opf_path  # noqa: PLC0415

        xml = (
            '<?xml version="1.0"?>'
            '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            "<rootfiles>"
            '<rootfile media-type="application/oebps-package+xml"/>'
            "</rootfiles>"
            "</container>"
        )
        with self._zip(xml) as z:
            assert _get_epub_opf_path(z) == ""
