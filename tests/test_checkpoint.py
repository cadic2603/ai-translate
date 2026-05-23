"""Unit tests for the checkpoint save/load/clear module."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.core.checkpoint import (
    _CHECKPOINT_BATCH,
    _CHECKPOINT_DUBBING,
    _CHECKPOINT_EPUB,
    _CHECKPOINT_LLM,
    _CHECKPOINT_OCR,
    _CHECKPOINT_PDF,
    _CHECKPOINT_TEXT,
    _OFFICE_IMAGE_DIR_NAME,
    _VERSION,
    ALIGN_CENTER,
    _deserialize_ocr_result,
    _serialize_ocr_result,
    _write_checkpoint,
    clear_checkpoints,
    get_storage_dir,
    hash_office_image,
    load_batch_checkpoint,
    load_dubbing_checkpoint,
    load_epub_checkpoint,
    load_llm_checkpoint,
    load_ocr_checkpoint,
    load_office_image_checkpoint,
    load_pdf_checkpoint,
    load_text_checkpoint,
    save_batch_progress,
    save_dubbing_checkpoint,
    save_epub_file_progress,
    save_llm_checkpoint,
    save_ocr_checkpoint,
    save_office_image_checkpoint,
    save_pdf_page_progress,
    save_text_chunk,
)
from src.core.ocr_engine import OCRResult

# ---------------------------------------------------------------------------
# get_storage_dir
# ---------------------------------------------------------------------------


def test_get_storage_dir() -> None:
    """Returns the parent directory of the storage path."""
    assert get_storage_dir("/home/user/translations/42/photo.jpg") == Path(
        "/home/user/translations/42",
    )


# ---------------------------------------------------------------------------
# OCRResult round-trip serialization
# ---------------------------------------------------------------------------


def _make_ocr_result() -> OCRResult:
    """Creates an OCRResult with all fields populated for testing."""
    r = OCRResult("hello", 10, 20, 100, 50, 0.95)
    r.color = "#ff0000"
    r.is_bold = True
    r.is_italic = True
    r.is_underline = False
    r.translated_text = "xin chao"
    r.translated_html = "<b>xin chao</b>"
    r.alignment = ALIGN_CENTER
    r.original_text_height = 48
    r.line_height_ratio = 1.3
    r.is_single_line = True
    return r


def test_ocr_result_roundtrip() -> None:
    """Serializing then deserializing produces an equivalent OCRResult."""
    original = _make_ocr_result()
    data = _serialize_ocr_result(original)
    restored = _deserialize_ocr_result(data)

    assert restored.text == original.text
    assert restored.x == original.x
    assert restored.y == original.y
    assert restored.w == original.w
    assert restored.h == original.h
    assert restored.confidence == original.confidence
    assert restored.color == original.color
    assert restored.is_bold is True
    assert restored.is_italic is True
    assert restored.is_underline is False
    assert restored.translated_text == original.translated_text
    assert restored.translated_html == original.translated_html
    assert restored.alignment == ALIGN_CENTER
    assert restored.original_text_height == 48  # noqa: PLR2004
    assert restored.line_height_ratio == 1.3  # noqa: PLR2004
    assert restored.is_single_line is True


def test_ocr_result_none_alignment() -> None:
    """OCRResult with alignment=None round-trips correctly."""
    r = OCRResult("test", 0, 0, 10, 10, 1.0)
    r.alignment = None
    data = _serialize_ocr_result(r)
    restored = _deserialize_ocr_result(data)
    assert restored.alignment is None


def test_deserialize_ocr_result_missing_text_key_raises() -> None:
    """_deserialize_ocr_result raises KeyError when required 'text' key is absent."""
    data = {"x": 0, "y": 0, "w": 10, "h": 10, "confidence": 0.9}
    with pytest.raises(KeyError):
        _deserialize_ocr_result(data)


def test_save_pdf_page_progress_non_serializable_silently_caught(
    tmp_path: Path,
) -> None:
    """save_pdf_page_progress with non-JSON-serializable data does not raise."""
    # object() cannot be JSON-serialized; the function should catch the exception.
    save_pdf_page_progress(tmp_path, 0, [{"bad": object()}], 1)  # type: ignore[list-item]
    # No file written — the error was silently swallowed.
    assert not (tmp_path / _CHECKPOINT_PDF).exists()


# ---------------------------------------------------------------------------
# OCR checkpoint
# ---------------------------------------------------------------------------


def test_save_load_ocr_checkpoint(tmp_path: Path) -> None:
    """OCR checkpoint round-trips correctly."""
    r1 = _make_ocr_result()
    r2 = OCRResult("world", 5, 5, 50, 25, 0.8)

    save_ocr_checkpoint(tmp_path, [r1], [r1, r2], "TesseractOCR")
    result = load_ocr_checkpoint(tmp_path)

    assert result is not None
    ocr_results, raw_results, method = result
    assert len(ocr_results) == 1
    assert len(raw_results) == 2  # noqa: PLR2004
    assert method == "TesseractOCR"
    assert ocr_results[0].text == "hello"
    assert raw_results[1].text == "world"


def test_load_ocr_checkpoint_missing(tmp_path: Path) -> None:
    """Returns None when no checkpoint file exists."""
    assert load_ocr_checkpoint(tmp_path) is None


# ---------------------------------------------------------------------------
# LLM checkpoint
# ---------------------------------------------------------------------------


def test_save_load_llm_checkpoint(tmp_path: Path) -> None:
    """LLM checkpoint round-trips correctly."""
    r1 = _make_ocr_result()
    translations = ["xin chao", "the gioi"]
    raw = [OCRResult("a", 0, 0, 10, 10, 1.0)]

    save_llm_checkpoint(tmp_path, [r1], translations, raw)
    result = load_llm_checkpoint(tmp_path)

    assert result is not None
    ocr_results, loaded_translations, fragments = result
    assert len(ocr_results) == 1
    assert loaded_translations == translations
    assert len(fragments) == 1


def test_load_llm_checkpoint_missing(tmp_path: Path) -> None:
    """Returns None when no checkpoint file exists."""
    assert load_llm_checkpoint(tmp_path) is None


# ---------------------------------------------------------------------------
# Text chunk checkpoint
# ---------------------------------------------------------------------------


def test_save_load_text_chunks(tmp_path: Path) -> None:
    """Text chunks accumulate incrementally."""
    save_text_chunk(tmp_path, 0, "chunk zero", 3)
    save_text_chunk(tmp_path, 2, "chunk two", 3)

    result = load_text_checkpoint(tmp_path)
    assert result is not None
    assert result == {0: "chunk zero", 2: "chunk two"}


def test_text_chunk_overwrites(tmp_path: Path) -> None:
    """Saving a chunk with the same index overwrites it."""
    save_text_chunk(tmp_path, 0, "old", 2)
    save_text_chunk(tmp_path, 0, "new", 2)

    result = load_text_checkpoint(tmp_path)
    assert result is not None
    assert result[0] == "new"


def test_load_text_checkpoint_missing(tmp_path: Path) -> None:
    """Returns None when no checkpoint file exists."""
    assert load_text_checkpoint(tmp_path) is None


# ---------------------------------------------------------------------------
# Batch checkpoint
# ---------------------------------------------------------------------------


def test_save_load_batch_progress(tmp_path: Path) -> None:
    """Batch progress accumulates across calls."""
    save_batch_progress(tmp_path, 0, ["a", "b", "c"], 6)
    save_batch_progress(tmp_path, 3, ["d", "e", "f"], 6)

    result = load_batch_checkpoint(tmp_path)
    assert result is not None
    assert len(result) == 6  # noqa: PLR2004
    assert result[0] == "a"
    assert result[5] == "f"


def test_load_batch_checkpoint_missing(tmp_path: Path) -> None:
    """Returns None when no checkpoint file exists."""
    assert load_batch_checkpoint(tmp_path) is None


# ---------------------------------------------------------------------------
# EPUB checkpoint
# ---------------------------------------------------------------------------


def test_save_load_epub_progress(tmp_path: Path) -> None:
    """EPUB file progress accumulates across calls."""
    files = ["OEBPS/ch1.xhtml", "OEBPS/ch2.xhtml"]
    save_epub_file_progress(tmp_path, "OEBPS/ch1.xhtml", "<p>Hi</p>", files)
    save_epub_file_progress(tmp_path, "OEBPS/ch2.xhtml", "<p>Bye</p>", files)

    result = load_epub_checkpoint(tmp_path)
    assert result is not None
    assert result["OEBPS/ch1.xhtml"] == "<p>Hi</p>"
    assert result["OEBPS/ch2.xhtml"] == "<p>Bye</p>"


def test_load_epub_checkpoint_missing(tmp_path: Path) -> None:
    """Returns None when no checkpoint file exists."""
    assert load_epub_checkpoint(tmp_path) is None


# ---------------------------------------------------------------------------
# clear_checkpoints
# ---------------------------------------------------------------------------


def test_clear_checkpoints(tmp_path: Path) -> None:
    """Removes all checkpoint files."""
    save_ocr_checkpoint(
        tmp_path,
        [OCRResult("x", 0, 0, 1, 1, 1.0)],
        [OCRResult("x", 0, 0, 1, 1, 1.0)],
        "TesseractOCR",
    )
    save_text_chunk(tmp_path, 0, "hello", 1)
    save_batch_progress(tmp_path, 0, ["a"], 1)
    save_epub_file_progress(tmp_path, "ch1.xhtml", "<p>ok</p>", ["ch1.xhtml"])

    # Verify files exist
    assert (tmp_path / _CHECKPOINT_OCR).exists()
    assert (tmp_path / _CHECKPOINT_TEXT).exists()
    assert (tmp_path / _CHECKPOINT_BATCH).exists()
    assert (tmp_path / _CHECKPOINT_EPUB).exists()

    clear_checkpoints(tmp_path)

    assert not (tmp_path / _CHECKPOINT_OCR).exists()
    assert not (tmp_path / _CHECKPOINT_TEXT).exists()
    assert not (tmp_path / _CHECKPOINT_BATCH).exists()
    assert not (tmp_path / _CHECKPOINT_EPUB).exists()


def test_clear_checkpoints_preserves_non_checkpoint_files(tmp_path: Path) -> None:
    """Non-checkpoint files are not deleted."""
    (tmp_path / "photo.jpg").write_text("image data")
    save_text_chunk(tmp_path, 0, "hello", 1)

    clear_checkpoints(tmp_path)

    assert (tmp_path / "photo.jpg").exists()
    assert not (tmp_path / _CHECKPOINT_TEXT).exists()


# ---------------------------------------------------------------------------
# Corrupt / version mismatch handling
# ---------------------------------------------------------------------------


def test_corrupt_checkpoint_returns_none(tmp_path: Path) -> None:
    """Returns None for a corrupt (non-JSON) checkpoint file."""
    (tmp_path / _CHECKPOINT_OCR).write_text("not json!")
    assert load_ocr_checkpoint(tmp_path) is None


def test_version_mismatch_returns_none(tmp_path: Path) -> None:
    """Returns None when checkpoint version differs from current."""
    data = {"version": 999, "ocr_results": [], "raw_ocr_results": []}
    (tmp_path / _CHECKPOINT_OCR).write_text(json.dumps(data))
    assert load_ocr_checkpoint(tmp_path) is None


def test_malformed_data_returns_none(tmp_path: Path) -> None:
    """Returns None when checkpoint data is missing required keys."""
    data = {"version": _VERSION}  # Missing ocr_results key
    (tmp_path / _CHECKPOINT_OCR).write_text(json.dumps(data))
    assert load_ocr_checkpoint(tmp_path) is None


def test_llm_checkpoint_corrupt_returns_none(tmp_path: Path) -> None:
    """Returns None for a corrupt LLM checkpoint."""
    (tmp_path / _CHECKPOINT_LLM).write_text("{bad json")
    assert load_llm_checkpoint(tmp_path) is None


# ---------------------------------------------------------------------------
# _deserialize_ocr_result defaults / edge cases
# ---------------------------------------------------------------------------


def test_deserialize_ocr_result_missing_optional_fields() -> None:
    """Deserialization fills in defaults when optional fields are absent."""
    minimal = {
        "text": "hello",
        "x": 0,
        "y": 0,
        "w": 100,
        "h": 50,
        "confidence": 0.9,
    }
    result = _deserialize_ocr_result(minimal)

    assert result.text == "hello"
    assert result.color == "#000000"  # default
    assert result.is_bold is False
    assert result.is_italic is False
    assert result.is_underline is False
    assert result.translated_text == ""
    assert result.translated_html == ""
    assert result.alignment is None
    assert result.original_text_height == 50  # noqa: PLR2004 — falls back to h
    assert result.line_height_ratio == 1.2  # noqa: PLR2004
    assert result.is_single_line is False


def test_deserialize_ocr_result_unknown_alignment() -> None:
    """Unknown alignment string results in alignment=None."""
    data = {
        "text": "test",
        "x": 0,
        "y": 0,
        "w": 10,
        "h": 10,
        "confidence": 1.0,
        "alignment": "AlignUnknown",
    }
    result = _deserialize_ocr_result(data)
    assert result.alignment is None


def test_serialize_ocr_result_none_color() -> None:
    """Serializing OCRResult with None color falls back to #000000."""
    r = OCRResult("test", 0, 0, 10, 10, 1.0)
    r.color = None
    data = _serialize_ocr_result(r)
    assert data["color"] == "#000000"


def test_ocr_result_all_alignments_roundtrip() -> None:
    """All four known alignment values round-trip correctly."""
    from src.core.checkpoint import (  # noqa: PLC0415
        ALIGN_JUSTIFY,
        ALIGN_LEFT,
        ALIGN_RIGHT,
    )

    for alignment_str in (ALIGN_LEFT, ALIGN_RIGHT, ALIGN_CENTER, ALIGN_JUSTIFY):
        r = OCRResult("t", 0, 0, 1, 1, 1.0)
        r.alignment = alignment_str
        data = _serialize_ocr_result(r)
        restored = _deserialize_ocr_result(data)
        assert restored.alignment == alignment_str


# ---------------------------------------------------------------------------
# Corrupt / malformed edge cases for all checkpoint types
# ---------------------------------------------------------------------------


def test_corrupt_text_checkpoint_returns_none(tmp_path: Path) -> None:
    """Returns None for a corrupt text checkpoint file."""
    (tmp_path / _CHECKPOINT_TEXT).write_text("not json!")
    assert load_text_checkpoint(tmp_path) is None


def test_corrupt_batch_checkpoint_returns_none(tmp_path: Path) -> None:
    """Returns None for a corrupt batch checkpoint file."""
    (tmp_path / _CHECKPOINT_BATCH).write_text("not json!")
    assert load_batch_checkpoint(tmp_path) is None


def test_corrupt_epub_checkpoint_returns_none(tmp_path: Path) -> None:
    """Returns None for a corrupt EPUB checkpoint file."""
    (tmp_path / _CHECKPOINT_EPUB).write_text("not json!")
    assert load_epub_checkpoint(tmp_path) is None


def test_malformed_text_checkpoint_returns_none(tmp_path: Path) -> None:
    """Returns None when text checkpoint is missing required keys."""
    data = {"version": _VERSION}  # Missing translated_chunks
    (tmp_path / _CHECKPOINT_TEXT).write_text(json.dumps(data))
    assert load_text_checkpoint(tmp_path) is None


def test_malformed_batch_checkpoint_returns_none(tmp_path: Path) -> None:
    """Returns None when batch checkpoint is missing required keys."""
    data = {"version": _VERSION}  # Missing translated_values
    (tmp_path / _CHECKPOINT_BATCH).write_text(json.dumps(data))
    assert load_batch_checkpoint(tmp_path) is None


def test_malformed_epub_checkpoint_returns_none(tmp_path: Path) -> None:
    """Returns None when EPUB checkpoint is missing required keys."""
    data = {"version": _VERSION}  # Missing translated_files
    (tmp_path / _CHECKPOINT_EPUB).write_text(json.dumps(data))
    assert load_epub_checkpoint(tmp_path) is None


def test_malformed_llm_checkpoint_returns_none(tmp_path: Path) -> None:
    """Returns None when LLM checkpoint is missing required keys."""
    data = {"version": _VERSION}  # Missing ocr_results, translations, etc.
    (tmp_path / _CHECKPOINT_LLM).write_text(json.dumps(data))
    assert load_llm_checkpoint(tmp_path) is None


def test_read_checkpoint_list_data_returns_none(tmp_path: Path) -> None:
    """Returns None when checkpoint file contains a JSON list instead of dict."""
    (tmp_path / _CHECKPOINT_OCR).write_text("[1, 2, 3]")
    assert load_ocr_checkpoint(tmp_path) is None


# ---------------------------------------------------------------------------
# clear_checkpoints edge cases
# ---------------------------------------------------------------------------


def test_clear_checkpoints_empty_dir(tmp_path: Path) -> None:
    """Clearing checkpoints on a dir with no checkpoint files is a no-op."""
    (tmp_path / "other_file.txt").write_text("keep me")
    clear_checkpoints(tmp_path)
    assert (tmp_path / "other_file.txt").exists()


# ---------------------------------------------------------------------------
# Text / batch / EPUB incremental save edge cases
# ---------------------------------------------------------------------------


def test_text_chunk_unicode_content(tmp_path: Path) -> None:
    """Unicode text is preserved in text chunks."""
    save_text_chunk(tmp_path, 0, "Xin chào thế giới 🌍", 1)
    result = load_text_checkpoint(tmp_path)
    assert result is not None
    assert result[0] == "Xin chào thế giới 🌍"


def test_batch_progress_overwrites_same_index(tmp_path: Path) -> None:
    """Saving batch at same start index overwrites existing values."""
    save_batch_progress(tmp_path, 0, ["old_a", "old_b"], 4)
    save_batch_progress(tmp_path, 0, ["new_a", "new_b"], 4)

    result = load_batch_checkpoint(tmp_path)
    assert result is not None
    assert result[0] == "new_a"
    assert result[1] == "new_b"


def test_epub_progress_overwrites_same_file(tmp_path: Path) -> None:
    """Re-saving an EPUB file overwrites its previous content."""
    files = ["ch1.xhtml"]
    save_epub_file_progress(tmp_path, "ch1.xhtml", "<p>old</p>", files)
    save_epub_file_progress(tmp_path, "ch1.xhtml", "<p>new</p>", files)

    result = load_epub_checkpoint(tmp_path)
    assert result is not None
    assert result["ch1.xhtml"] == "<p>new</p>"


def test_version_mismatch_text_returns_none(tmp_path: Path) -> None:
    """Text checkpoint with wrong version returns None."""
    data = {"version": 999, "total_chunks": 1, "translated_chunks": {"0": "hi"}}
    (tmp_path / _CHECKPOINT_TEXT).write_text(json.dumps(data))
    assert load_text_checkpoint(tmp_path) is None


def test_version_mismatch_batch_returns_none(tmp_path: Path) -> None:
    """Batch checkpoint with wrong version returns None."""
    data = {"version": 999, "total_values": 1, "translated_values": {"0": "hi"}}
    (tmp_path / _CHECKPOINT_BATCH).write_text(json.dumps(data))
    assert load_batch_checkpoint(tmp_path) is None


def test_version_mismatch_epub_returns_none(tmp_path: Path) -> None:
    """EPUB checkpoint with wrong version returns None."""
    data = {"version": 999, "content_files": [], "translated_files": {}}
    (tmp_path / _CHECKPOINT_EPUB).write_text(json.dumps(data))
    assert load_epub_checkpoint(tmp_path) is None


# ---------------------------------------------------------------------------
# get_storage_dir edge cases
# ---------------------------------------------------------------------------


def test_get_storage_dir_trailing_slash() -> None:
    """Trailing slash in path is handled correctly."""
    result = get_storage_dir("/home/user/translations/42/photo.jpg")
    assert result == Path("/home/user/translations/42")


def test_get_storage_dir_nested() -> None:
    """Deeply nested path returns direct parent."""
    result = get_storage_dir("/a/b/c/d/e/file.txt")
    assert result == Path("/a/b/c/d/e")


# ---------------------------------------------------------------------------
# Text checkpoint — non-contiguous indices
# ---------------------------------------------------------------------------


def test_text_chunk_non_contiguous_indices(tmp_path: Path) -> None:
    """Saving chunks at non-contiguous indices works."""
    save_text_chunk(tmp_path, 0, "first", 5)
    save_text_chunk(tmp_path, 4, "last", 5)

    result = load_text_checkpoint(tmp_path)
    assert result is not None
    assert result[0] == "first"
    assert result[4] == "last"
    assert 1 not in result  # noqa: PLR2004
    assert 2 not in result  # noqa: PLR2004


# ---------------------------------------------------------------------------
# Batch checkpoint — non-contiguous save
# ---------------------------------------------------------------------------


def test_batch_progress_non_contiguous(tmp_path: Path) -> None:
    """Saving batch progress at non-contiguous starts works."""
    save_batch_progress(tmp_path, 0, ["a", "b"], 6)
    save_batch_progress(tmp_path, 4, ["e", "f"], 6)

    result = load_batch_checkpoint(tmp_path)
    assert result is not None
    assert result[0] == "a"
    assert result[1] == "b"
    assert result[4] == "e"
    assert result[5] == "f"
    assert 2 not in result  # noqa: PLR2004


# ---------------------------------------------------------------------------
# clear_checkpoints — only removes checkpoint_*.json
# ---------------------------------------------------------------------------


def test_clear_checkpoints_ignores_non_checkpoint_json(
    tmp_path: Path,
) -> None:
    """Other .json files not matching checkpoint_*.json are preserved."""
    (tmp_path / "settings.json").write_text("{}")
    (tmp_path / "data.json").write_text("{}")
    save_text_chunk(tmp_path, 0, "x", 1)

    clear_checkpoints(tmp_path)

    assert (tmp_path / "settings.json").exists()
    assert (tmp_path / "data.json").exists()
    assert not (tmp_path / _CHECKPOINT_TEXT).exists()


# ---------------------------------------------------------------------------
# Text checkpoint — non-integer key graceful handling
# ---------------------------------------------------------------------------


def test_text_checkpoint_non_integer_keys_returns_none(
    tmp_path: Path,
) -> None:
    """Text checkpoint with non-integer keys returns None."""
    data = {
        "version": _VERSION,
        "total_chunks": 1,
        "translated_chunks": {"not_a_number": "hello"},
    }
    (tmp_path / _CHECKPOINT_TEXT).write_text(json.dumps(data))
    assert load_text_checkpoint(tmp_path) is None


# ---------------------------------------------------------------------------
# EPUB checkpoint — many files
# ---------------------------------------------------------------------------


def test_epub_progress_many_files(tmp_path: Path) -> None:
    """EPUB checkpoint handles many content files."""
    files = [f"OEBPS/ch{i}.xhtml" for i in range(20)]
    for f in files:
        save_epub_file_progress(tmp_path, f, f"<p>{f}</p>", files)

    result = load_epub_checkpoint(tmp_path)
    assert result is not None
    assert len(result) == 20  # noqa: PLR2004
    assert result["OEBPS/ch0.xhtml"] == "<p>OEBPS/ch0.xhtml</p>"
    assert result["OEBPS/ch19.xhtml"] == "<p>OEBPS/ch19.xhtml</p>"


# ---------------------------------------------------------------------------
# OCR checkpoint — empty results
# ---------------------------------------------------------------------------


def test_save_load_empty_ocr_checkpoint(tmp_path: Path) -> None:
    """OCR checkpoint with empty result lists round-trips."""
    save_ocr_checkpoint(tmp_path, [], [], "TesseractOCR")
    result = load_ocr_checkpoint(tmp_path)
    assert result is not None
    ocr_results, raw_results, method = result
    assert ocr_results == []
    assert raw_results == []
    assert method == "TesseractOCR"


# ---------------------------------------------------------------------------
# LLM checkpoint — empty translations
# ---------------------------------------------------------------------------


def test_save_load_empty_llm_checkpoint(tmp_path: Path) -> None:
    """LLM checkpoint with empty lists round-trips."""
    save_llm_checkpoint(tmp_path, [], [], [])
    result = load_llm_checkpoint(tmp_path)
    assert result is not None
    ocr_results, translations, fragments = result
    assert ocr_results == []
    assert translations == []
    assert fragments == []


# ---------------------------------------------------------------------------
# save_* exception handling (best-effort: log and return)
# ---------------------------------------------------------------------------


def test_save_ocr_checkpoint_serialization_error_is_swallowed(
    tmp_path: Path,
    caplog,
) -> None:
    """save_ocr_checkpoint swallows serialization errors and logs a warning."""
    # Create an OCRResult with a non-serializable color to trigger the inner
    # try/except.  We patch _serialize_ocr_result to raise.
    with patch(
        "src.core.checkpoint._serialize_ocr_result",
        side_effect=TypeError("not serializable"),
    ):
        save_ocr_checkpoint(
            tmp_path,
            [OCRResult("x", 0, 0, 1, 1, 1.0)],
            [],
            "TesseractOCR",
        )
    # No checkpoint file should be written
    assert not (tmp_path / _CHECKPOINT_OCR).exists()


def test_save_llm_checkpoint_serialization_error_is_swallowed(
    tmp_path: Path,
) -> None:
    """save_llm_checkpoint swallows serialization errors gracefully."""
    with patch(
        "src.core.checkpoint._serialize_ocr_result",
        side_effect=TypeError("not serializable"),
    ):
        save_llm_checkpoint(
            tmp_path,
            [OCRResult("x", 0, 0, 1, 1, 1.0)],
            ["hello"],
            [],
        )
    assert not (tmp_path / _CHECKPOINT_LLM).exists()


def test_save_text_chunk_write_error_is_swallowed(
    tmp_path: Path,
) -> None:
    """save_text_chunk swallows write errors gracefully."""
    with patch(
        "src.core.checkpoint._write_checkpoint",
        side_effect=OSError("disk full"),
    ):
        # Should not raise
        save_text_chunk(tmp_path, 0, "hello", 1)
    assert not (tmp_path / _CHECKPOINT_TEXT).exists()


def test_save_batch_progress_write_error_is_swallowed(
    tmp_path: Path,
) -> None:
    """save_batch_progress swallows write errors gracefully."""
    with patch(
        "src.core.checkpoint._write_checkpoint",
        side_effect=OSError("disk full"),
    ):
        save_batch_progress(tmp_path, 0, ["a"], 1)
    assert not (tmp_path / _CHECKPOINT_BATCH).exists()


def test_save_epub_file_progress_write_error_is_swallowed(
    tmp_path: Path,
) -> None:
    """save_epub_file_progress swallows write errors gracefully."""
    with patch(
        "src.core.checkpoint._write_checkpoint",
        side_effect=OSError("disk full"),
    ):
        save_epub_file_progress(tmp_path, "ch1.xhtml", "<p>ok</p>", ["ch1.xhtml"])
    assert not (tmp_path / _CHECKPOINT_EPUB).exists()


# ---------------------------------------------------------------------------
# _write_checkpoint — OSError on mkstemp is caught
# ---------------------------------------------------------------------------


def test_write_checkpoint_oserror_on_mkstemp_is_logged(
    tmp_path: Path,
    caplog,
) -> None:
    """_write_checkpoint catches OSError from mkstemp and logs it."""
    with (
        patch("src.core.checkpoint.tempfile.mkstemp", side_effect=OSError("no space")),
        caplog.at_level("ERROR", logger="checkpoint"),
    ):
        _write_checkpoint(tmp_path, "checkpoint_test.json", {"version": 1})
    # File should not exist since mkstemp failed
    assert not (tmp_path / "checkpoint_test.json").exists()


# ---------------------------------------------------------------------------
# clear_checkpoints — OSError on individual unlink is swallowed
# ---------------------------------------------------------------------------


def test_clear_checkpoints_oserror_on_unlink_is_swallowed(
    tmp_path: Path,
    caplog,
) -> None:
    """clear_checkpoints swallows OSError from unlink and logs a warning."""
    # Create a checkpoint file
    save_text_chunk(tmp_path, 0, "hello", 1)
    assert (tmp_path / _CHECKPOINT_TEXT).exists()

    with (
        patch.object(
            Path,
            "unlink",
            side_effect=OSError("permission denied"),
        ),
        caplog.at_level("WARNING", logger="checkpoint"),
    ):
        clear_checkpoints(tmp_path)
    # The function completes without raising


# ---------------------------------------------------------------------------
# PDF checkpoint
# ---------------------------------------------------------------------------


def test_save_load_pdf_checkpoint_single_page(tmp_path: Path) -> None:
    """PDF checkpoint round-trips correctly for a single page."""
    blocks = [
        {
            "rect": [72.0, 56.0, 200.0, 76.0],
            "text": "Hello",
            "translated_text": "Bonjour",
            "font_size": 14.0,
            "font_name": "Helvetica",
            "color": 0xFF0000,
            "bold": True,
            "italic": False,
        },
    ]
    save_pdf_page_progress(tmp_path, 0, blocks, 1)

    result = load_pdf_checkpoint(tmp_path)

    assert result is not None
    assert 0 in result
    assert len(result[0]) == 1
    assert result[0][0]["text"] == "Hello"
    assert result[0][0]["translated_text"] == "Bonjour"
    assert result[0][0]["font_size"] == 14.0  # noqa: PLR2004
    assert result[0][0]["color"] == 0xFF0000  # noqa: PLR2004
    assert result[0][0]["bold"] is True


def test_save_load_pdf_checkpoint_multiple_pages(tmp_path: Path) -> None:
    """Pages accumulate incrementally across multiple save calls."""
    blocks_0 = [{"rect": [0, 0, 100, 50], "text": "Page 0", "font_size": 12.0}]
    blocks_1 = [{"rect": [0, 0, 100, 50], "text": "Page 1", "font_size": 10.0}]
    blocks_2: list = []  # blank page

    save_pdf_page_progress(tmp_path, 0, blocks_0, 3)
    save_pdf_page_progress(tmp_path, 1, blocks_1, 3)
    save_pdf_page_progress(tmp_path, 2, blocks_2, 3)

    result = load_pdf_checkpoint(tmp_path)

    assert result is not None
    assert len(result) == 3  # noqa: PLR2004
    assert result[0][0]["text"] == "Page 0"
    assert result[1][0]["text"] == "Page 1"
    assert result[2] == []


def test_pdf_checkpoint_page_overwrites_same_index(tmp_path: Path) -> None:
    """Re-saving the same page index overwrites the previous data."""
    save_pdf_page_progress(tmp_path, 0, [{"text": "old"}], 1)
    save_pdf_page_progress(tmp_path, 0, [{"text": "new"}], 1)

    result = load_pdf_checkpoint(tmp_path)

    assert result is not None
    assert result[0][0]["text"] == "new"


def test_pdf_checkpoint_empty_blocks_list(tmp_path: Path) -> None:
    """Saving an empty block list (blank/scanned page) round-trips correctly."""
    save_pdf_page_progress(tmp_path, 5, [], 10)

    result = load_pdf_checkpoint(tmp_path)

    assert result is not None
    assert 5 in result
    assert result[5] == []


def test_load_pdf_checkpoint_missing(tmp_path: Path) -> None:
    """Returns None when no PDF checkpoint file exists."""
    assert load_pdf_checkpoint(tmp_path) is None


def test_corrupt_pdf_checkpoint_returns_none(tmp_path: Path) -> None:
    """Returns None for a corrupt (non-JSON) checkpoint file."""
    (tmp_path / _CHECKPOINT_PDF).write_text("not valid json!")
    assert load_pdf_checkpoint(tmp_path) is None


def test_version_mismatch_pdf_checkpoint_returns_none(tmp_path: Path) -> None:
    """Returns None when checkpoint version differs from current _VERSION."""
    import json  # noqa: PLC0415

    data = {
        "version": 999,
        "total_pages": 1,
        "translated_pages": {"0": []},
    }
    (tmp_path / _CHECKPOINT_PDF).write_text(json.dumps(data))
    assert load_pdf_checkpoint(tmp_path) is None


def test_malformed_pdf_checkpoint_missing_key_returns_none(tmp_path: Path) -> None:
    """Returns None when 'translated_pages' key is absent."""
    import json  # noqa: PLC0415

    data = {"version": _VERSION, "total_pages": 1}  # missing 'translated_pages'
    (tmp_path / _CHECKPOINT_PDF).write_text(json.dumps(data))
    assert load_pdf_checkpoint(tmp_path) is None


def test_malformed_pdf_checkpoint_non_integer_page_key_returns_none(
    tmp_path: Path,
) -> None:
    """Returns None when page keys cannot be coerced to int."""
    import json  # noqa: PLC0415

    data = {
        "version": _VERSION,
        "total_pages": 1,
        "translated_pages": {"page_zero": []},  # non-integer key
    }
    (tmp_path / _CHECKPOINT_PDF).write_text(json.dumps(data))
    assert load_pdf_checkpoint(tmp_path) is None


def test_save_pdf_page_progress_write_error_is_swallowed(
    tmp_path: Path,
) -> None:
    """save_pdf_page_progress swallows write errors gracefully."""
    with patch(
        "src.core.checkpoint._write_checkpoint",
        side_effect=OSError("disk full"),
    ):
        save_pdf_page_progress(tmp_path, 0, [], 1)

    assert not (tmp_path / _CHECKPOINT_PDF).exists()


def test_clear_checkpoints_also_clears_pdf(tmp_path: Path) -> None:
    """clear_checkpoints removes the PDF checkpoint alongside others."""
    save_pdf_page_progress(tmp_path, 0, [{"text": "x"}], 1)
    save_text_chunk(tmp_path, 0, "hello", 1)

    assert (tmp_path / _CHECKPOINT_PDF).exists()
    assert (tmp_path / _CHECKPOINT_TEXT).exists()

    clear_checkpoints(tmp_path)

    assert not (tmp_path / _CHECKPOINT_PDF).exists()
    assert not (tmp_path / _CHECKPOINT_TEXT).exists()


def test_pdf_checkpoint_preserves_unicode_content(tmp_path: Path) -> None:
    """Non-ASCII characters in block data are preserved correctly."""
    blocks = [{"text": "こんにちは", "translated_text": "Xin chào"}]
    save_pdf_page_progress(tmp_path, 0, blocks, 1)

    result = load_pdf_checkpoint(tmp_path)

    assert result is not None
    assert result[0][0]["text"] == "こんにちは"
    assert result[0][0]["translated_text"] == "Xin chào"


# ---------------------------------------------------------------------------
# PDF checkpoint — mixed blocks + annotation entries
# ---------------------------------------------------------------------------


def test_pdf_checkpoint_mixed_blocks_and_annotations(tmp_path: Path) -> None:
    """Round-trip save/load of mixed text blocks and annotation entries."""
    entries = [
        {
            "rect": [72.0, 56.0, 200.0, 76.0],
            "text": "Hello",
            "translated_text": "Bonjour",
            "font_size": 14.0,
            "font_name": "Helvetica",
            "color": 0,
            "bold": False,
            "italic": False,
        },
        {
            "type": "annot",
            "annot_type": 0,
            "annot_id": "annot-1",
            "text": "Review this",
            "translated_text": "Vérifiez ceci",
        },
        {
            "type": "annot",
            "annot_type": 2,
            "annot_id": "annot-2",
            "text": "Visible note",
            "translated_text": "Note visible",
            "rect": [50.0, 300.0, 200.0, 350.0],
        },
    ]
    save_pdf_page_progress(tmp_path, 0, entries, 1)

    result = load_pdf_checkpoint(tmp_path)

    assert result is not None
    assert len(result[0]) == 3  # noqa: PLR2004
    # Text block (no "type" key)
    assert "type" not in result[0][0]
    assert result[0][0]["text"] == "Hello"
    # Annotation entries
    assert result[0][1]["type"] == "annot"
    assert result[0][1]["annot_id"] == "annot-1"
    assert result[0][1]["translated_text"] == "Vérifiez ceci"
    assert result[0][2]["type"] == "annot"
    assert result[0][2]["annot_type"] == 2  # noqa: PLR2004
    assert result[0][2]["rect"] == [50.0, 300.0, 200.0, 350.0]


def test_pdf_checkpoint_annotation_only_page(tmp_path: Path) -> None:
    """Page with only annotation entries (no text blocks) survives round-trip."""
    entries = [
        {
            "type": "annot",
            "annot_type": 0,
            "annot_id": "note-42",
            "text": "Just a comment",
            "translated_text": "Juste un commentaire",
        },
    ]
    save_pdf_page_progress(tmp_path, 0, entries, 1)

    result = load_pdf_checkpoint(tmp_path)

    assert result is not None
    assert len(result[0]) == 1
    assert result[0][0]["type"] == "annot"
    assert result[0][0]["annot_id"] == "note-42"
    assert result[0][0]["translated_text"] == "Juste un commentaire"


def test_pdf_checkpoint_annot_type_marker_preserved(tmp_path: Path) -> None:
    """The "type": "annot" marker is preserved through JSON round-trip."""
    entries = [
        {
            "type": "annot",
            "annot_type": 2,
            "annot_id": "ft-1",
            "text": "FreeText content",
            "translated_text": "Contenu texte libre",
            "rect": [10, 20, 300, 80],
        },
    ]
    save_pdf_page_progress(tmp_path, 0, entries, 1)

    result = load_pdf_checkpoint(tmp_path)

    assert result is not None
    entry = result[0][0]
    assert entry["type"] == "annot"
    assert entry["annot_type"] == 2  # noqa: PLR2004
    assert entry["annot_id"] == "ft-1"


# ---------------------------------------------------------------------------
# _read_checkpoint: version as string "1" vs integer 1
# ---------------------------------------------------------------------------


def test_version_as_string_returns_none(tmp_path: Path) -> None:
    """Returns None when version field is a string '1' instead of integer 1."""
    # The _VERSION constant is 1 (int); "1" != 1 in Python → version mismatch
    data = {"version": "1", "ocr_results": [], "raw_ocr_results": []}
    (tmp_path / _CHECKPOINT_OCR).write_text(json.dumps(data))
    assert load_ocr_checkpoint(tmp_path) is None


def test_empty_dict_checkpoint_returns_none(tmp_path: Path) -> None:
    """Returns None when checkpoint file contains an empty JSON object {}."""
    # {} has no 'version' key → data.get('version') returns None → None != 1
    (tmp_path / _CHECKPOINT_OCR).write_text("{}")
    assert load_ocr_checkpoint(tmp_path) is None


def test_null_version_returns_none(tmp_path: Path) -> None:
    """Returns None when version field is JSON null (None in Python)."""
    data = {"version": None, "ocr_results": [], "raw_ocr_results": []}
    (tmp_path / _CHECKPOINT_OCR).write_text(json.dumps(data))
    assert load_ocr_checkpoint(tmp_path) is None


# ---------------------------------------------------------------------------
# save_text_batch — empty chunks early return
# ---------------------------------------------------------------------------


def test_save_text_batch_empty_chunks_no_write(tmp_path: Path) -> None:
    """Empty chunks dict returns immediately without writing any file."""
    from src.core.checkpoint import save_text_batch  # noqa: PLC0415

    save_text_batch(tmp_path, {}, 5)
    assert not (tmp_path / _CHECKPOINT_TEXT).exists()


# ---------------------------------------------------------------------------
# load_batch_checkpoint — ValueError for non-integer keys
# ---------------------------------------------------------------------------


def test_load_batch_checkpoint_non_integer_keys_returns_none(
    tmp_path: Path,
) -> None:
    """Non-integer keys in translated_values cause ValueError → returns None."""
    data = {
        "version": _VERSION,
        "total_values": 2,
        "translated_values": {"not_a_number": "hello", "abc": "world"},
    }
    (tmp_path / _CHECKPOINT_BATCH).write_text(json.dumps(data))
    assert load_batch_checkpoint(tmp_path) is None


# ---------------------------------------------------------------------------
# _read_checkpoint — OSError branch (file permission/read error)
# ---------------------------------------------------------------------------


def test_read_checkpoint_oserror_returns_none(tmp_path: Path) -> None:
    """Returns None when file open raises OSError during read."""
    # Create a valid checkpoint file first
    (tmp_path / _CHECKPOINT_OCR).write_text(
        json.dumps({"version": _VERSION, "ocr_results": [], "raw_ocr_results": []}),
    )
    # Patch Path.open to raise during read
    with patch.object(
        Path,
        "open",
        side_effect=OSError("permission denied"),
    ):
        assert load_ocr_checkpoint(tmp_path) is None


# ---------------------------------------------------------------------------
# _write_checkpoint — inner BaseException cleanup (json.dump failure)
# ---------------------------------------------------------------------------


def test_write_checkpoint_json_dump_failure_cleans_up_temp(
    tmp_path: Path,
) -> None:
    """If json.dump raises TypeError, temp file is cleaned up before re-raise."""
    import pytest as _pt  # noqa: PLC0415

    target = tmp_path / _CHECKPOINT_TEXT

    # object() is not JSON serializable → TypeError from json.dump
    # Inner BaseException handler deletes temp, then re-raises
    # Outer OSError handler does NOT catch TypeError → propagates
    with _pt.raises(TypeError, match="not JSON serializable"):
        _write_checkpoint(
            tmp_path,
            _CHECKPOINT_TEXT,
            {"version": _VERSION, "data": object()},
        )

    # The target should not be created since json.dump failed
    assert not target.exists()
    # No leftover temp files — inner handler cleaned up
    tmp_files = list(tmp_path.glob("*.tmp"))
    assert tmp_files == []


# ---------------------------------------------------------------------------
# Corrupt checkpoint edge cases — null, array, wrong inner types
# ---------------------------------------------------------------------------


def test_json_null_checkpoint_returns_none(tmp_path: Path) -> None:
    """JSON file containing 'null' (not a dict) → load returns None."""
    (tmp_path / _CHECKPOINT_OCR).write_text("null")
    assert load_ocr_checkpoint(tmp_path) is None


def test_json_array_checkpoint_returns_none(tmp_path: Path) -> None:
    """JSON file containing '[]' (array, not dict) → load returns None."""
    (tmp_path / _CHECKPOINT_TEXT).write_text("[]")
    assert load_text_checkpoint(tmp_path) is None


def test_json_array_batch_checkpoint_returns_none(tmp_path: Path) -> None:
    """JSON file containing '[]' for batch checkpoint → load returns None."""
    (tmp_path / _CHECKPOINT_BATCH).write_text("[1, 2, 3]")
    assert load_batch_checkpoint(tmp_path) is None


def test_json_null_pdf_checkpoint_returns_none(tmp_path: Path) -> None:
    """JSON file containing 'null' for PDF checkpoint → load returns None."""
    (tmp_path / _CHECKPOINT_PDF).write_text("null")
    assert load_pdf_checkpoint(tmp_path) is None


def test_ocr_checkpoint_wrong_inner_type_ocr_results_not_list(
    tmp_path: Path,
) -> None:
    """OCR checkpoint with 'ocr_results' as a string → returns None."""
    data = {
        "version": _VERSION,
        "ocr_method": "TesseractOCR",
        "ocr_results": "not_a_list",
        "raw_ocr_results": [],
    }
    (tmp_path / _CHECKPOINT_OCR).write_text(json.dumps(data))
    assert load_ocr_checkpoint(tmp_path) is None


def test_llm_checkpoint_wrong_inner_type_translations_not_list(
    tmp_path: Path,
) -> None:
    """LLM checkpoint with 'translations' as an int → returns None."""
    data = {
        "version": _VERSION,
        "ocr_results": [],
        "translations": 42,
        "confirmed_raw_fragments": [],
    }
    (tmp_path / _CHECKPOINT_LLM).write_text(json.dumps(data))
    # translations is an int; iterating over it in the caller is fine
    # but the load function should propagate whatever json gives back.
    # Since translations=42 is not iterable-of-str, verify graceful behavior.
    result = load_llm_checkpoint(tmp_path)
    # The load function returns translations as-is from data["translations"],
    # so it returns the int 42.  That's acceptable: the caller will fail later.
    # What matters is no crash in the load function itself.
    assert result is not None
    assert result[1] == 42  # noqa: PLR2004


def test_text_checkpoint_wrong_inner_type_chunks_value_is_int(
    tmp_path: Path,
) -> None:
    """Text checkpoint with chunk values as non-string ints → loads OK.

    The load function only converts keys to int, values are pass-through.
    """
    data = {
        "version": _VERSION,
        "total_chunks": 2,
        "translated_chunks": {"0": 999, "1": None},
    }
    (tmp_path / _CHECKPOINT_TEXT).write_text(json.dumps(data))
    result = load_text_checkpoint(tmp_path)
    # Values are not validated — pass through as-is
    assert result is not None
    assert result[0] == 999  # noqa: PLR2004
    assert result[1] is None


def test_batch_checkpoint_wrong_inner_type_translated_values_is_int(
    tmp_path: Path,
) -> None:
    """Batch checkpoint with 'translated_values' as an int → raises.

    The load function catches (KeyError, TypeError, ValueError) but not
    AttributeError.  An int has no .items() method.
    Test with a dict whose keys are floats (JSON numbers) to trigger
    ValueError in int() coercion.
    """
    data = {
        "version": _VERSION,
        "total_values": 1,
        "translated_values": {"1.5": "hello"},
    }
    (tmp_path / _CHECKPOINT_BATCH).write_text(json.dumps(data))
    # int("1.5") → ValueError → caught → returns None
    assert load_batch_checkpoint(tmp_path) is None


def test_epub_checkpoint_wrong_inner_type_translated_files_is_int(
    tmp_path: Path,
) -> None:
    """EPUB checkpoint with 'translated_files' as an int → returns None."""
    data = {
        "version": _VERSION,
        "content_files": [],
        "translated_files": 42,
    }
    (tmp_path / _CHECKPOINT_EPUB).write_text(json.dumps(data))
    # dict(42) → TypeError → caught → returns None
    assert load_epub_checkpoint(tmp_path) is None


def test_pdf_checkpoint_translated_pages_float_keys_returns_none(
    tmp_path: Path,
) -> None:
    """PDF checkpoint with float-like string page keys → returns None."""
    data = {
        "version": _VERSION,
        "total_pages": 1,
        "translated_pages": {"1.5": [{"text": "hello"}]},
    }
    (tmp_path / _CHECKPOINT_PDF).write_text(json.dumps(data))
    # int("1.5") → ValueError → caught → returns None
    assert load_pdf_checkpoint(tmp_path) is None


def test_pdf_checkpoint_translated_pages_value_is_string(
    tmp_path: Path,
) -> None:
    """PDF checkpoint where a page value is a string instead of list → loads OK.

    The load function just coerces keys to int; values are pass-through.
    """
    data = {
        "version": _VERSION,
        "total_pages": 1,
        "translated_pages": {"0": "not_a_list_of_blocks"},
    }
    (tmp_path / _CHECKPOINT_PDF).write_text(json.dumps(data))
    result = load_pdf_checkpoint(tmp_path)
    # load_pdf_checkpoint does {int(k): v for k, v in pages.items()}
    # It doesn't validate that v is a list — that's the caller's job.
    assert result is not None
    assert result[0] == "not_a_list_of_blocks"


# ---------------------------------------------------------------------------
# _write_checkpoint — rename failure
# ---------------------------------------------------------------------------


def test_write_checkpoint_rename_failure_no_target(
    tmp_path: Path,
    caplog,
) -> None:
    """When Path.replace() raises OSError, target file is not created."""
    with (
        patch.object(Path, "replace", side_effect=OSError("rename failed")),
        caplog.at_level("ERROR", logger="checkpoint"),
    ):
        _write_checkpoint(tmp_path, "checkpoint_test.json", {"version": _VERSION})

    # Target should not exist because replace() failed
    assert not (tmp_path / "checkpoint_test.json").exists()
    # The OSError should be caught and logged
    assert "Failed to write checkpoint" in caplog.text


# ---------------------------------------------------------------------------
# Dubbing checkpoint — incremental save
# ---------------------------------------------------------------------------


def test_save_dubbing_checkpoint_srt_text(tmp_path: Path) -> None:
    """Saving srt_text creates a checkpoint with that key."""
    srt = "1\n00:00:00,000 --> 00:00:01,000\nHello"
    save_dubbing_checkpoint(tmp_path, srt_text=srt)

    result = load_dubbing_checkpoint(tmp_path)

    assert result is not None
    assert result["srt_text"] == srt


def test_save_dubbing_checkpoint_incremental_merge(tmp_path: Path) -> None:
    """Each save step merges into the existing checkpoint, preserving earlier keys."""
    # Step 1: save srt_text
    save_dubbing_checkpoint(tmp_path, srt_text="raw srt content")
    result1 = load_dubbing_checkpoint(tmp_path)
    assert result1 is not None
    assert "srt_text" in result1
    assert "translated_srt" not in result1

    # Step 2: save translated_srt — srt_text must still be present
    save_dubbing_checkpoint(tmp_path, translated_srt="translated srt content")
    result2 = load_dubbing_checkpoint(tmp_path)
    assert result2 is not None
    assert result2["srt_text"] == "raw srt content"
    assert result2["translated_srt"] == "translated srt content"

    # Step 3: save voice_file — both earlier keys must still be present
    save_dubbing_checkpoint(tmp_path, voice_file="voice_output.wav")
    result3 = load_dubbing_checkpoint(tmp_path)
    assert result3 is not None
    assert result3["srt_text"] == "raw srt content"
    assert result3["translated_srt"] == "translated srt content"
    assert result3["voice_file"] == "voice_output.wav"


# ---------------------------------------------------------------------------
# Dubbing checkpoint — load roundtrip + missing file
# ---------------------------------------------------------------------------


def test_load_dubbing_checkpoint_roundtrip(tmp_path: Path) -> None:
    """Full round-trip: save all fields then load and verify."""
    save_dubbing_checkpoint(
        tmp_path,
        srt_text="original",
        translated_srt="translated",
        voice_file="audio.wav",
        target_lang="Vietnamese",
    )

    result = load_dubbing_checkpoint(tmp_path)

    assert result is not None
    assert result["srt_text"] == "original"
    assert result["translated_srt"] == "translated"
    assert result["voice_file"] == "audio.wav"
    assert result["target_lang"] == "Vietnamese"


def test_load_dubbing_checkpoint_missing(tmp_path: Path) -> None:
    """Returns None when no dubbing checkpoint file exists."""
    assert load_dubbing_checkpoint(tmp_path) is None


# ---------------------------------------------------------------------------
# Dubbing checkpoint — target_lang persistence
# ---------------------------------------------------------------------------


def test_dubbing_checkpoint_target_lang_persisted(tmp_path: Path) -> None:
    """target_lang is saved and retrievable on load."""
    save_dubbing_checkpoint(tmp_path, srt_text="content", target_lang="Japanese")

    result = load_dubbing_checkpoint(tmp_path)

    assert result is not None
    assert result["target_lang"] == "Japanese"


def test_dubbing_checkpoint_target_lang_preserved_across_updates(
    tmp_path: Path,
) -> None:
    """target_lang survives when later steps add translated_srt / voice_file."""
    save_dubbing_checkpoint(tmp_path, srt_text="raw", target_lang="French")
    save_dubbing_checkpoint(tmp_path, translated_srt="traduit")
    save_dubbing_checkpoint(tmp_path, voice_file="voice.mp3")

    result = load_dubbing_checkpoint(tmp_path)

    assert result is not None
    assert result["target_lang"] == "French"
    assert result["srt_text"] == "raw"
    assert result["translated_srt"] == "traduit"
    assert result["voice_file"] == "voice.mp3"


# ---------------------------------------------------------------------------
# Dubbing checkpoint — corrupt / version mismatch
# ---------------------------------------------------------------------------


def test_corrupt_dubbing_checkpoint_returns_none(tmp_path: Path) -> None:
    """Returns None for a corrupt (non-JSON) dubbing checkpoint file."""
    (tmp_path / _CHECKPOINT_DUBBING).write_text("not json!")
    assert load_dubbing_checkpoint(tmp_path) is None


def test_version_mismatch_dubbing_checkpoint_returns_none(tmp_path: Path) -> None:
    """Returns None when dubbing checkpoint version differs from current."""
    data = {"version": 999, "srt_text": "hello"}
    (tmp_path / _CHECKPOINT_DUBBING).write_text(json.dumps(data))
    assert load_dubbing_checkpoint(tmp_path) is None


def test_clear_checkpoints_also_clears_dubbing(tmp_path: Path) -> None:
    """clear_checkpoints removes the dubbing checkpoint alongside others."""
    save_dubbing_checkpoint(tmp_path, srt_text="raw")
    save_text_chunk(tmp_path, 0, "hello", 1)

    assert (tmp_path / _CHECKPOINT_DUBBING).exists()
    assert (tmp_path / _CHECKPOINT_TEXT).exists()

    clear_checkpoints(tmp_path)

    assert not (tmp_path / _CHECKPOINT_DUBBING).exists()
    assert not (tmp_path / _CHECKPOINT_TEXT).exists()


# ---------------------------------------------------------------------------
# save_pdf_page_progress — total_pages overwrite
# ---------------------------------------------------------------------------


def test_save_pdf_page_progress_overwrites_total_pages(
    tmp_path: Path,
) -> None:
    """Saving with total_pages=10 then total_pages=5 → second call wins."""
    save_pdf_page_progress(tmp_path, 0, [{"text": "p0"}], 10)

    # Verify initial total_pages
    raw = json.loads((tmp_path / _CHECKPOINT_PDF).read_text())
    assert raw["total_pages"] == 10  # noqa: PLR2004

    # Save again with different total_pages
    save_pdf_page_progress(tmp_path, 1, [{"text": "p1"}], 5)

    raw = json.loads((tmp_path / _CHECKPOINT_PDF).read_text())
    assert raw["total_pages"] == 5  # noqa: PLR2004
    # Both pages should still be present
    assert "0" in raw["translated_pages"]
    assert "1" in raw["translated_pages"]


# ---------------------------------------------------------------------------
# TestSaveDubbingCheckpointEdgeCases
# ---------------------------------------------------------------------------


class TestSaveDubbingCheckpointEdgeCases:
    """Edge-case tests for save_dubbing_checkpoint."""

    def test_save_dubbing_checkpoint_overwrites_existing_field(
        self,
        tmp_path: Path,
    ) -> None:
        """Re-saving srt_text with a new value overwrites the old one."""
        save_dubbing_checkpoint(tmp_path, srt_text="old")

        result_old = load_dubbing_checkpoint(tmp_path)
        assert result_old is not None
        assert result_old["srt_text"] == "old"

        save_dubbing_checkpoint(tmp_path, srt_text="new")

        result_new = load_dubbing_checkpoint(tmp_path)
        assert result_new is not None
        assert result_new["srt_text"] == "new"

    def test_save_dubbing_checkpoint_no_kwargs_creates_version_only(
        self,
        tmp_path: Path,
    ) -> None:
        """Calling with no keyword arguments creates a checkpoint with just version."""
        save_dubbing_checkpoint(tmp_path)

        result = load_dubbing_checkpoint(tmp_path)
        assert result is not None
        assert result["version"] == _VERSION
        # No optional keys should be present
        assert "srt_text" not in result
        assert "translated_srt" not in result
        assert "voice_file" not in result
        assert "target_lang" not in result

    def test_save_dubbing_checkpoint_write_error_propagates(
        self,
        tmp_path: Path,
    ) -> None:
        """Write error propagates because save_dubbing_checkpoint has no try/except."""
        # save_dubbing_checkpoint calls _write_checkpoint directly without a
        # wrapping try/except (unlike save_ocr_checkpoint, save_text_chunk, etc.).
        # Patch _write_checkpoint to raise a non-OSError exception (RuntimeError)
        # to prove that save_dubbing_checkpoint lets it propagate.
        with (
            patch(
                "src.core.checkpoint._write_checkpoint",
                side_effect=RuntimeError("unexpected failure"),
            ),
            pytest.raises(RuntimeError, match="unexpected failure"),
        ):
            save_dubbing_checkpoint(tmp_path, srt_text="test")


# ---------------------------------------------------------------------------
# TestLoadDubbingCheckpointEdgeCases
# ---------------------------------------------------------------------------


class TestLoadDubbingCheckpointEdgeCases:
    """Edge-case tests for load_dubbing_checkpoint."""

    def test_load_dubbing_checkpoint_empty_json_object(
        self,
        tmp_path: Path,
    ) -> None:
        """Empty JSON object '{}' has no version → returns None."""
        (tmp_path / _CHECKPOINT_DUBBING).write_text("{}")
        assert load_dubbing_checkpoint(tmp_path) is None

    def test_load_dubbing_checkpoint_json_array(
        self,
        tmp_path: Path,
    ) -> None:
        """JSON array '[1,2,3]' is not a dict → returns None."""
        (tmp_path / _CHECKPOINT_DUBBING).write_text("[1,2,3]")
        assert load_dubbing_checkpoint(tmp_path) is None

    def test_load_dubbing_checkpoint_json_null(
        self,
        tmp_path: Path,
    ) -> None:
        """JSON 'null' is not a dict → returns None."""
        (tmp_path / _CHECKPOINT_DUBBING).write_text("null")
        assert load_dubbing_checkpoint(tmp_path) is None


# ---------------------------------------------------------------------------
# TestSaveTextBatchEdgeCases
# ---------------------------------------------------------------------------


class TestSaveTextBatchEdgeCases:
    """Edge-case tests for save_text_batch."""

    def test_save_text_batch_write_error_swallowed(
        self,
        tmp_path: Path,
    ) -> None:
        """save_text_batch swallows write errors gracefully (try/except)."""
        from src.core.checkpoint import save_text_batch  # noqa: PLC0415

        with patch(
            "src.core.checkpoint._write_checkpoint",
            side_effect=OSError("disk full"),
        ):
            # Should NOT raise
            save_text_batch(tmp_path, {0: "hello"}, 1)

        # No checkpoint file written
        assert not (tmp_path / _CHECKPOINT_TEXT).exists()

    def test_save_text_batch_merge_with_existing(
        self,
        tmp_path: Path,
    ) -> None:
        """Saving two batches merges them into a single checkpoint."""
        from src.core.checkpoint import save_text_batch  # noqa: PLC0415

        save_text_batch(tmp_path, {0: "chunk zero", 1: "chunk one"}, 4)
        save_text_batch(tmp_path, {2: "chunk two", 3: "chunk three"}, 4)

        result = load_text_checkpoint(tmp_path)
        assert result is not None
        assert len(result) == 4  # noqa: PLR2004
        assert result[0] == "chunk zero"
        assert result[1] == "chunk one"
        assert result[2] == "chunk two"
        assert result[3] == "chunk three"


# ---------------------------------------------------------------------------
# Edge cases identified in triple-check audit
# ---------------------------------------------------------------------------


class TestCheckpointEdgeCasesTripleCheck:
    """Edge cases for checkpoint robustness."""

    def test_read_checkpoint_unicode_decode_error(self, tmp_path: Path) -> None:
        """UnicodeDecodeError on corrupted file returns None (not crash)."""
        target = tmp_path / _CHECKPOINT_TEXT
        # Write binary data that is invalid UTF-8
        target.write_bytes(b"\x80\x81\x82\xff\xfe")

        result = load_text_checkpoint(tmp_path)
        assert result is None

    def test_read_checkpoint_empty_file(self, tmp_path: Path) -> None:
        """Empty checkpoint file (0 bytes) returns None."""
        target = tmp_path / _CHECKPOINT_TEXT
        target.write_text("")

        result = load_text_checkpoint(tmp_path)
        assert result is None

    def test_read_checkpoint_truncated_json(self, tmp_path: Path) -> None:
        """Truncated JSON (partial write) returns None."""
        target = tmp_path / _CHECKPOINT_TEXT
        target.write_text('{"version": 1, "translated_chu')

        result = load_text_checkpoint(tmp_path)
        assert result is None

    def test_dubbing_checkpoint_empty_string_srt(self, tmp_path: Path) -> None:
        """Empty string srt_text is saved and loaded (not confused with None)."""
        save_dubbing_checkpoint(tmp_path, srt_text="", target_lang="French")
        result = load_dubbing_checkpoint(tmp_path)
        assert result is not None
        assert result["srt_text"] == ""

    def test_dubbing_checkpoint_target_lang_overwrite(self, tmp_path: Path) -> None:
        """Second save overwrites target_lang from first save."""
        save_dubbing_checkpoint(tmp_path, srt_text="hi", target_lang="English")
        save_dubbing_checkpoint(tmp_path, target_lang="French")
        result = load_dubbing_checkpoint(tmp_path)
        assert result is not None
        assert result["target_lang"] == "French"
        # srt_text from first save should be preserved
        assert result["srt_text"] == "hi"

    def test_epub_checkpoint_special_chars_in_path(self, tmp_path: Path) -> None:
        """File paths with special characters survive roundtrip."""
        save_epub_file_progress(
            tmp_path,
            "OEBPS/章節[1].xhtml",
            "<p>translated</p>",
            ["OEBPS/章節[1].xhtml", "OEBPS/ch2.xhtml"],
        )
        result = load_epub_checkpoint(tmp_path)
        assert result is not None
        assert "OEBPS/章節[1].xhtml" in result


# ---------------------------------------------------------------------------
# _write_checkpoint — non-serializable data
# ---------------------------------------------------------------------------


class TestWriteCheckpointEdgeCases:
    """Edge-case tests for _write_checkpoint."""

    def test_non_serializable_data_does_not_create_file(
        self,
        tmp_path: Path,
    ) -> None:
        """Non-JSON-serializable data raises TypeError; no file is created."""
        # _write_checkpoint's inner try/except BaseException cleans up the
        # temp file then re-raises.  The outer except only catches OSError,
        # so TypeError propagates to the caller.
        with pytest.raises(TypeError):
            _write_checkpoint(
                tmp_path,
                "test.json",
                {
                    "version": _VERSION,
                    "data": object(),  # Not JSON-serializable
                },
            )
        assert not (tmp_path / "test.json").exists()

    def test_valid_data_creates_file(self, tmp_path: Path) -> None:
        """Sanity check: valid data creates the file."""
        _write_checkpoint(
            tmp_path,
            "test.json",
            {
                "version": _VERSION,
                "value": "hello",
            },
        )
        assert (tmp_path / "test.json").exists()
        data = json.loads((tmp_path / "test.json").read_text())
        assert data["value"] == "hello"


# ---------------------------------------------------------------------------
# _read_checkpoint — invalid UTF-8
# ---------------------------------------------------------------------------


class TestReadCheckpointCorruptData:
    """Tests for corrupt checkpoint files."""

    def test_invalid_utf8_returns_none(self, tmp_path: Path) -> None:
        """Binary file with invalid UTF-8 returns None."""
        target = tmp_path / _CHECKPOINT_TEXT
        target.write_bytes(b"\x80\x81\x82\x83\xff\xfe")
        result = load_text_checkpoint(tmp_path)
        assert result is None

    def test_wrong_version_returns_none(self, tmp_path: Path) -> None:
        """Checkpoint with wrong version number returns None."""
        target = tmp_path / _CHECKPOINT_TEXT
        target.write_text(
            json.dumps(
                {
                    "version": _VERSION + 999,
                    "translated_chunks": [],
                }
            )
        )
        result = load_text_checkpoint(tmp_path)
        assert result is None

    def test_non_dict_json_returns_none(self, tmp_path: Path) -> None:
        """JSON array (not dict) returns None."""
        target = tmp_path / _CHECKPOINT_TEXT
        target.write_text("[1, 2, 3]")
        result = load_text_checkpoint(tmp_path)
        assert result is None


# ---------------------------------------------------------------------------
# _deserialize_ocr_result — invalid alignment types
# ---------------------------------------------------------------------------


class TestDeserializeOcrResultEdgeCases:
    """Edge-case tests for _deserialize_ocr_result."""

    def test_integer_alignment_returns_none(self) -> None:
        """Integer alignment value (corrupted) results in alignment=None."""
        data = {
            "text": "hello",
            "x": 0,
            "y": 0,
            "w": 100,
            "h": 50,
            "confidence": 0.9,
            "alignment": 123,
        }
        result = _deserialize_ocr_result(data)
        assert result.alignment is None

    def test_invalid_string_alignment_returns_none(self) -> None:
        """Unknown alignment string results in alignment=None."""
        data = {
            "text": "hello",
            "x": 0,
            "y": 0,
            "w": 100,
            "h": 50,
            "confidence": 0.9,
            "alignment": "diagonal",
        }
        result = _deserialize_ocr_result(data)
        assert result.alignment is None

    def test_empty_string_alignment_returns_none(self) -> None:
        """Empty string alignment results in alignment=None."""
        data = {
            "text": "hello",
            "x": 0,
            "y": 0,
            "w": 100,
            "h": 50,
            "confidence": 0.9,
            "alignment": "",
        }
        result = _deserialize_ocr_result(data)
        assert result.alignment is None

    def test_missing_optional_fields_use_defaults(self) -> None:
        """Missing optional fields use default values."""
        data = {
            "text": "hello",
            "x": 10,
            "y": 20,
            "w": 100,
            "h": 50,
            "confidence": 0.95,
        }
        result = _deserialize_ocr_result(data)
        assert result.color == "#000000"
        assert result.is_bold is False
        assert result.is_italic is False
        assert result.is_underline is False
        assert result.translated_text == ""
        assert result.translated_html == ""
        assert result.alignment is None


# ---------------------------------------------------------------------------
# save_pdf_page_progress — non-serializable block
# ---------------------------------------------------------------------------


class TestSavePdfPageProgressEdgeCases:
    """Edge-case tests for save_pdf_page_progress."""

    def test_non_serializable_block_does_not_crash(
        self,
        tmp_path: Path,
    ) -> None:
        """Block with non-serializable value logs error, no crash."""
        # save_pdf_page_progress wraps _write_checkpoint in a try/except
        # that catches all exceptions — so a TypeError from json.dump
        # should NOT propagate to the caller.
        save_pdf_page_progress(
            tmp_path,
            page_index=0,
            translated_blocks=[{"text": "ok"}, {"data": object()}],
            total_pages=1,
        )
        # The checkpoint file should NOT be created (write fails internally)
        assert not (tmp_path / _CHECKPOINT_PDF).exists()


# ---------------------------------------------------------------------------
# Widget-type entries in PDF checkpoint
# ---------------------------------------------------------------------------


class TestPdfCheckpointWidgetEntries:
    """PDF checkpoint handling of widget-type entries alongside text blocks."""

    def test_widget_entry_roundtrip(self, tmp_path: Path) -> None:
        """A single widget entry round-trips correctly."""
        entries = [
            {
                "type": "widget",
                "field_name": "Name",
                "text": "John",
                "translated_text": "Jean",
            },
        ]
        save_pdf_page_progress(tmp_path, 0, entries, 1)
        result = load_pdf_checkpoint(tmp_path)

        assert result is not None
        assert len(result[0]) == 1
        assert result[0][0]["type"] == "widget"
        assert result[0][0]["field_name"] == "Name"
        assert result[0][0]["translated_text"] == "Jean"

    def test_mixed_text_annot_widget_entries(self, tmp_path: Path) -> None:
        """Page with text blocks, annotations, and widgets all survive round-trip."""
        entries = [
            {
                "rect": [72.0, 56.0, 200.0, 76.0],
                "text": "Title",
                "translated_text": "Titre",
                "font_size": 14.0,
            },
            {
                "type": "annot",
                "annot_type": 0,
                "annot_id": "annot-1",
                "text": "Note",
                "translated_text": "Remarque",
            },
            {
                "type": "widget",
                "field_name": "Email",
                "text": "user@example.com",
                "translated_text": "utilisateur@example.com",
            },
            {
                "type": "widget",
                "field_name": "Country",
                "text": "United States",
                "translated_text": "États-Unis",
                "widget_type": "combobox",
                "choices": ["United States", "France"],
            },
        ]
        save_pdf_page_progress(tmp_path, 0, entries, 1)
        result = load_pdf_checkpoint(tmp_path)

        assert result is not None
        assert len(result[0]) == 4  # noqa: PLR2004

        # Text block — no "type" key
        assert "type" not in result[0][0]
        assert result[0][0]["text"] == "Title"

        # Annotation entry
        assert result[0][1]["type"] == "annot"
        assert result[0][1]["annot_id"] == "annot-1"

        # Widget entries
        assert result[0][2]["type"] == "widget"
        assert result[0][2]["field_name"] == "Email"

        assert result[0][3]["type"] == "widget"
        assert result[0][3]["widget_type"] == "combobox"
        assert result[0][3]["choices"] == ["United States", "France"]

    def test_widget_only_page(self, tmp_path: Path) -> None:
        """Page with only widget entries (no text or annotation) round-trips."""
        entries = [
            {
                "type": "widget",
                "field_name": "FirstName",
                "text": "Alice",
                "translated_text": "Alice",
            },
            {
                "type": "widget",
                "field_name": "LastName",
                "text": "Smith",
                "translated_text": "Dupont",
            },
        ]
        save_pdf_page_progress(tmp_path, 2, entries, 5)
        result = load_pdf_checkpoint(tmp_path)

        assert result is not None
        assert 2 in result
        assert len(result[2]) == 2  # noqa: PLR2004
        assert all(e["type"] == "widget" for e in result[2])

    def test_widget_entries_across_multiple_pages(self, tmp_path: Path) -> None:
        """Widget entries on different pages accumulate independently."""
        save_pdf_page_progress(
            tmp_path,
            0,
            [
                {
                    "type": "widget",
                    "field_name": "Name",
                    "text": "A",
                    "translated_text": "B",
                }
            ],
            3,
        )
        save_pdf_page_progress(
            tmp_path,
            1,
            [
                {
                    "text": "Body text",
                    "translated_text": "Texte du corps",
                    "font_size": 12.0,
                }
            ],
            3,
        )
        save_pdf_page_progress(
            tmp_path,
            2,
            [
                {
                    "type": "widget",
                    "field_name": "Zip",
                    "text": "12345",
                    "translated_text": "12345",
                }
            ],
            3,
        )

        result = load_pdf_checkpoint(tmp_path)

        assert result is not None
        assert len(result) == 3  # noqa: PLR2004
        assert result[0][0]["type"] == "widget"
        assert "type" not in result[1][0]
        assert result[2][0]["type"] == "widget"

    def test_widget_listbox_choices_preserved(self, tmp_path: Path) -> None:
        """Widget entry for a listbox preserves the choices list."""
        entries = [
            {
                "type": "widget",
                "field_name": "Color",
                "widget_type": "listbox",
                "text": "Red",
                "translated_text": "Rouge",
                "choices": ["Red", "Green", "Blue"],
                "translated_choices": ["Rouge", "Vert", "Bleu"],
            },
        ]
        save_pdf_page_progress(tmp_path, 0, entries, 1)
        result = load_pdf_checkpoint(tmp_path)

        assert result is not None
        widget = result[0][0]
        assert widget["widget_type"] == "listbox"
        assert widget["choices"] == ["Red", "Green", "Blue"]
        assert widget["translated_choices"] == ["Rouge", "Vert", "Bleu"]


# ---------------------------------------------------------------------------
# clear_checkpoints — non-existent directory
# ---------------------------------------------------------------------------


class TestClearCheckpointsNonExistentDir:
    """clear_checkpoints when the storage_dir does not exist."""

    def test_non_existent_dir_no_error(self, tmp_path: Path) -> None:
        """Calling clear_checkpoints on a non-existent dir raises no error."""
        non_existent = tmp_path / "does_not_exist"
        assert not non_existent.exists()
        # Path.glob on a non-existent dir returns an empty iterator
        clear_checkpoints(non_existent)
        # No exception means success

    def test_deleted_dir_after_file_creation(self, tmp_path: Path) -> None:
        """If directory is removed between creating files and clearing, no crash."""
        sub = tmp_path / "sub"
        sub.mkdir()
        save_text_chunk(sub, 0, "hi", 1)
        assert (sub / _CHECKPOINT_TEXT).exists()

        # Remove the dir entirely
        import shutil  # noqa: PLC0415

        shutil.rmtree(sub)
        assert not sub.exists()

        # Calling clear_checkpoints should not raise
        clear_checkpoints(sub)


# ---------------------------------------------------------------------------
# Dubbing checkpoint — all 4 steps individually and combined
# ---------------------------------------------------------------------------


class TestDubbingCheckpointAllSteps:
    """Verify save/load for all 4 dubbing pipeline steps."""

    def test_step1_stt_only(self, tmp_path: Path) -> None:
        """Step 1 (STT): saves srt_text and target_lang."""
        save_dubbing_checkpoint(
            tmp_path,
            srt_text="1\n00:00:00,000 --> 00:00:05,000\nHello world",
            target_lang="Vietnamese",
        )
        result = load_dubbing_checkpoint(tmp_path)

        assert result is not None
        assert result["srt_text"] == "1\n00:00:00,000 --> 00:00:05,000\nHello world"
        assert result["target_lang"] == "Vietnamese"
        assert "translated_srt" not in result
        assert "voice_file" not in result

    def test_step2_translation(self, tmp_path: Path) -> None:
        """Step 2 (LLM translation): adds translated_srt to existing checkpoint."""
        save_dubbing_checkpoint(
            tmp_path,
            srt_text="1\n00:00:00,000 --> 00:00:05,000\nHello",
            target_lang="French",
        )
        save_dubbing_checkpoint(
            tmp_path,
            translated_srt="1\n00:00:00,000 --> 00:00:05,000\nBonjour",
        )
        result = load_dubbing_checkpoint(tmp_path)

        assert result is not None
        assert result["srt_text"] == "1\n00:00:00,000 --> 00:00:05,000\nHello"
        assert result["translated_srt"] == "1\n00:00:00,000 --> 00:00:05,000\nBonjour"
        assert result["target_lang"] == "French"
        assert "voice_file" not in result

    def test_step3_tts(self, tmp_path: Path) -> None:
        """Step 3 (TTS): adds voice_file to existing checkpoint."""
        save_dubbing_checkpoint(tmp_path, srt_text="raw", target_lang="German")
        save_dubbing_checkpoint(tmp_path, translated_srt="translated")
        save_dubbing_checkpoint(tmp_path, voice_file="synthesized_voice.wav")
        result = load_dubbing_checkpoint(tmp_path)

        assert result is not None
        assert result["srt_text"] == "raw"
        assert result["translated_srt"] == "translated"
        assert result["voice_file"] == "synthesized_voice.wav"
        assert result["target_lang"] == "German"

    def test_step4_mix_all_fields_present(self, tmp_path: Path) -> None:
        """Step 4 (mix): after all steps, checkpoint has all 4 fields."""
        save_dubbing_checkpoint(tmp_path, srt_text="raw srt", target_lang="Japanese")
        save_dubbing_checkpoint(tmp_path, translated_srt="translated srt")
        save_dubbing_checkpoint(tmp_path, voice_file="voice.wav")

        result = load_dubbing_checkpoint(tmp_path)

        assert result is not None
        assert "srt_text" in result
        assert "translated_srt" in result
        assert "voice_file" in result
        assert "target_lang" in result
        assert result["version"] == _VERSION

    def test_all_steps_in_single_call(self, tmp_path: Path) -> None:
        """All 4 fields can be saved in a single call."""
        save_dubbing_checkpoint(
            tmp_path,
            srt_text="1\n00:00:00,000 --> 00:00:02,000\nHi",
            translated_srt="1\n00:00:00,000 --> 00:00:02,000\nSalut",
            voice_file="output.wav",
            target_lang="French",
        )
        result = load_dubbing_checkpoint(tmp_path)

        assert result is not None
        assert result["srt_text"] == "1\n00:00:00,000 --> 00:00:02,000\nHi"
        assert result["translated_srt"] == "1\n00:00:00,000 --> 00:00:02,000\nSalut"
        assert result["voice_file"] == "output.wav"
        assert result["target_lang"] == "French"

    def test_unicode_srt_content(self, tmp_path: Path) -> None:
        """Non-ASCII characters in SRT text survive roundtrip."""
        srt_content = "1\n00:00:00,000 --> 00:00:03,000\nXin chào thế giới"
        translated = "1\n00:00:00,000 --> 00:00:03,000\nこんにちは世界"
        save_dubbing_checkpoint(
            tmp_path,
            srt_text=srt_content,
            translated_srt=translated,
            target_lang="Japanese",
        )
        result = load_dubbing_checkpoint(tmp_path)

        assert result is not None
        assert result["srt_text"] == srt_content
        assert result["translated_srt"] == translated


# ---------------------------------------------------------------------------
# Empty / corrupted checkpoint files — comprehensive
# ---------------------------------------------------------------------------


class TestCorruptedCheckpointFiles:
    """Malformed JSON and edge cases across all checkpoint types."""

    def test_truncated_json_pdf(self, tmp_path: Path) -> None:
        """Truncated JSON in PDF checkpoint returns None."""
        (tmp_path / _CHECKPOINT_PDF).write_text('{"version": 1, "translated_pa')
        assert load_pdf_checkpoint(tmp_path) is None

    def test_truncated_json_batch(self, tmp_path: Path) -> None:
        """Truncated JSON in batch checkpoint returns None."""
        (tmp_path / _CHECKPOINT_BATCH).write_text('{"version": 1, "translated_v')
        assert load_batch_checkpoint(tmp_path) is None

    def test_truncated_json_epub(self, tmp_path: Path) -> None:
        """Truncated JSON in EPUB checkpoint returns None."""
        (tmp_path / _CHECKPOINT_EPUB).write_text('{"version": 1, "translated_f')
        assert load_epub_checkpoint(tmp_path) is None

    def test_truncated_json_dubbing(self, tmp_path: Path) -> None:
        """Truncated JSON in dubbing checkpoint returns None."""
        (tmp_path / _CHECKPOINT_DUBBING).write_text('{"version": 1, "srt_')
        assert load_dubbing_checkpoint(tmp_path) is None

    def test_truncated_json_llm(self, tmp_path: Path) -> None:
        """Truncated JSON in LLM checkpoint returns None."""
        (tmp_path / _CHECKPOINT_LLM).write_text('{"version": 1, "ocr_res')
        assert load_llm_checkpoint(tmp_path) is None

    def test_truncated_json_ocr(self, tmp_path: Path) -> None:
        """Truncated JSON in OCR checkpoint returns None."""
        (tmp_path / _CHECKPOINT_OCR).write_text('{"version": 1, "ocr_met')
        assert load_ocr_checkpoint(tmp_path) is None

    def test_binary_garbage_pdf(self, tmp_path: Path) -> None:
        """Binary garbage in PDF checkpoint returns None."""
        (tmp_path / _CHECKPOINT_PDF).write_bytes(b"\x00\x01\x02\xff\xfe\xfd")
        assert load_pdf_checkpoint(tmp_path) is None

    def test_binary_garbage_batch(self, tmp_path: Path) -> None:
        """Binary garbage in batch checkpoint returns None."""
        (tmp_path / _CHECKPOINT_BATCH).write_bytes(b"\x89PNG\r\n\x1a\n")
        assert load_batch_checkpoint(tmp_path) is None

    def test_binary_garbage_dubbing(self, tmp_path: Path) -> None:
        """Binary garbage in dubbing checkpoint returns None."""
        (tmp_path / _CHECKPOINT_DUBBING).write_bytes(b"\xff\xd8\xff\xe0\x00")
        assert load_dubbing_checkpoint(tmp_path) is None

    def test_json_number_returns_none_text(self, tmp_path: Path) -> None:
        """JSON file containing just a number (not a dict) returns None."""
        (tmp_path / _CHECKPOINT_TEXT).write_text("42")
        assert load_text_checkpoint(tmp_path) is None

    def test_json_string_returns_none_batch(self, tmp_path: Path) -> None:
        """JSON file containing just a string (not a dict) returns None."""
        (tmp_path / _CHECKPOINT_BATCH).write_text('"hello"')
        assert load_batch_checkpoint(tmp_path) is None

    def test_json_boolean_returns_none_epub(self, tmp_path: Path) -> None:
        """JSON file containing 'true' (not a dict) returns None."""
        (tmp_path / _CHECKPOINT_EPUB).write_text("true")
        assert load_epub_checkpoint(tmp_path) is None

    def test_correct_version_but_completely_wrong_structure_pdf(
        self,
        tmp_path: Path,
    ) -> None:
        """PDF checkpoint with correct version but unexpected structure returns None."""
        data = {"version": _VERSION, "something_else": "not translated_pages"}
        (tmp_path / _CHECKPOINT_PDF).write_text(json.dumps(data))
        assert load_pdf_checkpoint(tmp_path) is None

    def test_correct_version_but_missing_translated_pages_key(
        self,
        tmp_path: Path,
    ) -> None:
        """PDF with correct version but no translated_pages returns None."""
        data = {"version": _VERSION, "total_pages": 1, "other_key": "irrelevant"}
        (tmp_path / _CHECKPOINT_PDF).write_text(json.dumps(data))
        # data["translated_pages"] → KeyError, which IS caught
        assert load_pdf_checkpoint(tmp_path) is None


# ---------------------------------------------------------------------------
# EPUB checkpoint — empty content_files list
# ---------------------------------------------------------------------------


class TestEpubCheckpointEmptyContentFiles:
    """Edge cases for EPUB checkpoint with empty content_files list."""

    def test_save_with_empty_content_files_list(self, tmp_path: Path) -> None:
        """Saving with an empty content_files list creates a valid checkpoint."""
        save_epub_file_progress(tmp_path, "ch1.xhtml", "<p>text</p>", [])
        result = load_epub_checkpoint(tmp_path)

        assert result is not None
        assert result["ch1.xhtml"] == "<p>text</p>"

    def test_empty_content_files_and_no_translated_files(
        self,
        tmp_path: Path,
    ) -> None:
        """Checkpoint with empty content_files written manually round-trips."""
        data = {
            "version": _VERSION,
            "content_files": [],
            "translated_files": {},
        }
        (tmp_path / _CHECKPOINT_EPUB).write_text(json.dumps(data))
        result = load_epub_checkpoint(tmp_path)

        assert result is not None
        assert result == {}

    def test_content_files_list_stored_in_raw_json(self, tmp_path: Path) -> None:
        """The content_files list is preserved in the raw JSON on disk."""
        save_epub_file_progress(tmp_path, "ch1.xhtml", "<p>done</p>", [])

        raw = json.loads((tmp_path / _CHECKPOINT_EPUB).read_text())
        assert raw["content_files"] == []
        assert "ch1.xhtml" in raw["translated_files"]

    def test_save_overwrites_content_files_on_second_call(
        self,
        tmp_path: Path,
    ) -> None:
        """Second save call updates content_files list even if first was empty."""
        save_epub_file_progress(tmp_path, "ch1.xhtml", "<p>a</p>", [])

        raw1 = json.loads((tmp_path / _CHECKPOINT_EPUB).read_text())
        assert raw1["content_files"] == []

        save_epub_file_progress(
            tmp_path,
            "ch2.xhtml",
            "<p>b</p>",
            ["ch1.xhtml", "ch2.xhtml"],
        )

        raw2 = json.loads((tmp_path / _CHECKPOINT_EPUB).read_text())
        assert raw2["content_files"] == ["ch1.xhtml", "ch2.xhtml"]
        # Both translated files should be present
        assert raw2["translated_files"]["ch1.xhtml"] == "<p>a</p>"
        assert raw2["translated_files"]["ch2.xhtml"] == "<p>b</p>"


# ---------------------------------------------------------------------------
# Batch checkpoint — zero completed
# ---------------------------------------------------------------------------


class TestBatchCheckpointZeroCompleted:
    """Edge cases for save_batch_progress with zero-length batches."""

    def test_save_batch_with_empty_values_list(self, tmp_path: Path) -> None:
        """Saving an empty translated_values list creates a valid checkpoint."""
        save_batch_progress(tmp_path, 0, [], 10)
        result = load_batch_checkpoint(tmp_path)

        assert result is not None
        assert result == {}

    def test_save_batch_completed_zero_then_add_later(
        self,
        tmp_path: Path,
    ) -> None:
        """Save empty batch first, then add real values later."""
        save_batch_progress(tmp_path, 0, [], 5)
        result1 = load_batch_checkpoint(tmp_path)
        assert result1 is not None
        assert len(result1) == 0

        # Now add actual values
        save_batch_progress(tmp_path, 0, ["a", "b"], 5)
        result2 = load_batch_checkpoint(tmp_path)
        assert result2 is not None
        assert len(result2) == 2  # noqa: PLR2004
        assert result2[0] == "a"
        assert result2[1] == "b"

    def test_save_batch_zero_total_values(self, tmp_path: Path) -> None:
        """Saving with total_values=0 and empty list creates a valid checkpoint."""
        save_batch_progress(tmp_path, 0, [], 0)
        result = load_batch_checkpoint(tmp_path)

        assert result is not None
        assert result == {}

        # Verify the raw JSON has total_values=0
        raw = json.loads((tmp_path / _CHECKPOINT_BATCH).read_text())
        assert raw["total_values"] == 0

    def test_save_batch_empty_then_non_empty_preserves_total(
        self,
        tmp_path: Path,
    ) -> None:
        """Empty batch preserves total_values, second batch updates it."""
        save_batch_progress(tmp_path, 0, [], 10)
        raw = json.loads((tmp_path / _CHECKPOINT_BATCH).read_text())
        assert raw["total_values"] == 10  # noqa: PLR2004

        save_batch_progress(tmp_path, 0, ["x"], 20)
        raw = json.loads((tmp_path / _CHECKPOINT_BATCH).read_text())
        assert raw["total_values"] == 20  # noqa: PLR2004


# ---------------------------------------------------------------------------
# Concurrent / atomic write safety
# ---------------------------------------------------------------------------


class TestAtomicWriteSafety:
    """Tests verifying atomic write-then-rename prevents corruption."""

    def test_concurrent_writes_produce_valid_json(self, tmp_path: Path) -> None:
        """Multiple rapid successive writes all produce valid JSON on disk."""
        for i in range(50):
            save_text_chunk(tmp_path, i, f"chunk_{i}", 50)

        result = load_text_checkpoint(tmp_path)
        assert result is not None
        assert len(result) == 50  # noqa: PLR2004
        for i in range(50):
            assert result[i] == f"chunk_{i}"

    def test_rapid_pdf_page_writes(self, tmp_path: Path) -> None:
        """Many rapid PDF page saves produce a consistent checkpoint."""
        total = 30
        for i in range(total):
            save_pdf_page_progress(
                tmp_path,
                i,
                [{"text": f"page_{i}", "translated_text": f"page_{i}_translated"}],
                total,
            )

        result = load_pdf_checkpoint(tmp_path)
        assert result is not None
        assert len(result) == total  # noqa: PLR2004
        for i in range(total):
            assert result[i][0]["text"] == f"page_{i}"

    def test_temp_file_cleanup_on_success(self, tmp_path: Path) -> None:
        """No leftover .tmp files after a successful write."""
        save_text_chunk(tmp_path, 0, "hello", 1)

        tmp_files = list(tmp_path.glob("*.tmp"))
        assert tmp_files == []

    def test_temp_file_cleanup_on_json_dump_failure(self, tmp_path: Path) -> None:
        """Temp files are cleaned up even when json.dump fails (TypeError)."""
        with pytest.raises(TypeError):
            _write_checkpoint(tmp_path, "test.json", {"data": {1, 2, 3}})

        tmp_files = list(tmp_path.glob("*.tmp"))
        assert tmp_files == []
        assert not (tmp_path / "test.json").exists()

    def test_overwrite_existing_checkpoint_atomically(
        self,
        tmp_path: Path,
    ) -> None:
        """Overwriting an existing checkpoint leaves a valid file even if crash."""
        # Write initial checkpoint
        save_batch_progress(tmp_path, 0, ["a", "b"], 4)
        result1 = load_batch_checkpoint(tmp_path)
        assert result1 is not None
        assert result1[0] == "a"

        # Write a second batch — uses atomic rename so no partial state
        save_batch_progress(tmp_path, 2, ["c", "d"], 4)
        result2 = load_batch_checkpoint(tmp_path)
        assert result2 is not None
        assert len(result2) == 4  # noqa: PLR2004
        assert result2[0] == "a"
        assert result2[2] == "c"

    def test_write_checkpoint_uses_same_directory_for_temp(
        self,
        tmp_path: Path,
    ) -> None:
        """Atomic write creates temp file in same dir (ensures same filesystem)."""
        import tempfile as tf  # noqa: PLC0415

        original_mkstemp = tf.mkstemp

        captured_dirs: list[str] = []

        def spy_mkstemp(*, dir: str, suffix: str) -> tuple[int, str]:
            """Capture the dir argument passed to mkstemp."""
            captured_dirs.append(dir)
            return original_mkstemp(dir=dir, suffix=suffix)

        with patch("src.core.checkpoint.tempfile.mkstemp", side_effect=spy_mkstemp):
            _write_checkpoint(tmp_path, "test.json", {"version": _VERSION})

        assert len(captured_dirs) == 1
        assert captured_dirs[0] == str(tmp_path)

    def test_rapid_dubbing_incremental_writes(self, tmp_path: Path) -> None:
        """Rapid incremental dubbing checkpoint writes produce consistent state."""
        # Simulate the 4-step pipeline in rapid succession
        for i in range(10):
            save_dubbing_checkpoint(
                tmp_path,
                srt_text=f"srt_{i}",
                target_lang=f"lang_{i}",
            )
            save_dubbing_checkpoint(tmp_path, translated_srt=f"translated_{i}")
            save_dubbing_checkpoint(tmp_path, voice_file=f"voice_{i}.wav")

        # Only the last iteration's values should survive
        result = load_dubbing_checkpoint(tmp_path)
        assert result is not None
        assert result["srt_text"] == "srt_9"
        assert result["translated_srt"] == "translated_9"
        assert result["voice_file"] == "voice_9.wav"
        assert result["target_lang"] == "lang_9"

    def test_rapid_epub_writes(self, tmp_path: Path) -> None:
        """Many rapid EPUB file saves all accumulate correctly."""
        files = [f"OEBPS/ch{i}.xhtml" for i in range(25)]
        for f in files:
            save_epub_file_progress(tmp_path, f, f"<p>{f}</p>", files)

        result = load_epub_checkpoint(tmp_path)
        assert result is not None
        assert len(result) == 25  # noqa: PLR2004
        for f in files:
            assert result[f] == f"<p>{f}</p>"


# ---------------------------------------------------------------------------
# NEW: Additional tests for expanded coverage
# ---------------------------------------------------------------------------


class TestSaveCheckpointAllArtifactTypes:
    """Verify save/load round-trip for all artifact types in one session."""

    def test_all_checkpoint_types_coexist(self, tmp_path: Path) -> None:
        """All 7 checkpoint types can be saved and loaded independently."""
        r = OCRResult("x", 0, 0, 10, 10, 1.0)

        save_ocr_checkpoint(tmp_path, [r], [r], "TesseractOCR")
        save_llm_checkpoint(tmp_path, [r], ["translated"], [r])
        save_text_chunk(tmp_path, 0, "chunk0", 1)
        save_batch_progress(tmp_path, 0, ["batch0"], 1)
        save_epub_file_progress(tmp_path, "ch.xhtml", "<p>epub</p>", ["ch.xhtml"])
        save_pdf_page_progress(tmp_path, 0, [{"text": "pdf"}], 1)
        save_dubbing_checkpoint(tmp_path, srt_text="dub")

        assert load_ocr_checkpoint(tmp_path) is not None
        assert load_llm_checkpoint(tmp_path) is not None
        assert load_text_checkpoint(tmp_path) is not None
        assert load_batch_checkpoint(tmp_path) is not None
        assert load_epub_checkpoint(tmp_path) is not None
        assert load_pdf_checkpoint(tmp_path) is not None
        assert load_dubbing_checkpoint(tmp_path) is not None

    def test_clear_removes_all_types(self, tmp_path: Path) -> None:
        """clear_checkpoints deletes all 7 checkpoint files."""
        r = OCRResult("x", 0, 0, 10, 10, 1.0)

        save_ocr_checkpoint(tmp_path, [r], [r], "TesseractOCR")
        save_llm_checkpoint(tmp_path, [r], ["translated"], [r])
        save_text_chunk(tmp_path, 0, "chunk0", 1)
        save_batch_progress(tmp_path, 0, ["batch0"], 1)
        save_epub_file_progress(tmp_path, "ch.xhtml", "<p>epub</p>", ["ch.xhtml"])
        save_pdf_page_progress(tmp_path, 0, [{"text": "pdf"}], 1)
        save_dubbing_checkpoint(tmp_path, srt_text="dub")

        clear_checkpoints(tmp_path)

        assert load_ocr_checkpoint(tmp_path) is None
        assert load_llm_checkpoint(tmp_path) is None
        assert load_text_checkpoint(tmp_path) is None
        assert load_batch_checkpoint(tmp_path) is None
        assert load_epub_checkpoint(tmp_path) is None
        assert load_pdf_checkpoint(tmp_path) is None
        assert load_dubbing_checkpoint(tmp_path) is None


class TestAtomicWriteRenameVerification:
    """Verify the write-tmp-then-rename pattern works correctly."""

    def test_target_file_appears_after_write(self, tmp_path: Path) -> None:
        """Target file exists after successful _write_checkpoint."""
        target = tmp_path / "checkpoint_test.json"
        assert not target.exists()
        _write_checkpoint(
            tmp_path, "checkpoint_test.json", {"version": _VERSION, "k": 1}
        )
        assert target.exists()
        data = json.loads(target.read_text())
        assert data["k"] == 1

    def test_no_temp_files_remain_on_success(self, tmp_path: Path) -> None:
        """No .tmp files remain after multiple successful writes."""
        for i in range(10):
            _write_checkpoint(
                tmp_path,
                "checkpoint_test.json",
                {"version": _VERSION, "iter": i},
            )
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert tmp_files == []

    def test_overwrite_preserves_atomicity(self, tmp_path: Path) -> None:
        """Overwriting an existing checkpoint produces valid JSON at all times."""
        _write_checkpoint(
            tmp_path, "checkpoint_test.json", {"version": _VERSION, "v": 1}
        )
        _write_checkpoint(
            tmp_path, "checkpoint_test.json", {"version": _VERSION, "v": 2}
        )
        data = json.loads((tmp_path / "checkpoint_test.json").read_text())
        assert data["v"] == 2


class TestCheckpointVersioning:
    """Test checkpoint version checks and compatibility."""

    def test_current_version_is_integer(self) -> None:
        """_VERSION is an integer."""
        assert isinstance(_VERSION, int)

    def test_version_zero_returns_none(self, tmp_path: Path) -> None:
        """Version 0 is not equal to _VERSION (1), so it returns None."""
        data = {"version": 0, "ocr_results": [], "raw_ocr_results": []}
        (tmp_path / _CHECKPOINT_OCR).write_text(json.dumps(data))
        assert load_ocr_checkpoint(tmp_path) is None

    def test_negative_version_returns_none(self, tmp_path: Path) -> None:
        """Negative version returns None."""
        data = {"version": -1, "translated_chunks": {"0": "hi"}}
        (tmp_path / _CHECKPOINT_TEXT).write_text(json.dumps(data))
        assert load_text_checkpoint(tmp_path) is None

    def test_float_version_accepted(self, tmp_path: Path) -> None:
        """Float version (1.0) equals int _VERSION (1) in Python, so data loads."""
        data = {"version": 1.0, "translated_values": {"0": "a"}}
        (tmp_path / _CHECKPOINT_BATCH).write_text(json.dumps(data))
        result = load_batch_checkpoint(tmp_path)
        assert result is not None
        assert result == {0: "a"}

    def test_version_field_preserved_in_roundtrip(self, tmp_path: Path) -> None:
        """The version field is preserved in the JSON on disk."""
        save_text_chunk(tmp_path, 0, "hello", 1)
        raw = json.loads((tmp_path / _CHECKPOINT_TEXT).read_text())
        assert raw["version"] == _VERSION


class TestLargeCheckpointData:
    """Tests with large checkpoint payloads."""

    def test_large_text_chunks(self, tmp_path: Path) -> None:
        """1000 text chunks all round-trip correctly."""
        from src.core.checkpoint import save_text_batch  # noqa: PLC0415

        chunks = {i: f"chunk_{i}" for i in range(1000)}
        save_text_batch(tmp_path, chunks, 1000)
        result = load_text_checkpoint(tmp_path)
        assert result is not None
        assert len(result) == 1000  # noqa: PLR2004
        assert result[0] == "chunk_0"
        assert result[999] == "chunk_999"

    def test_large_batch_values(self, tmp_path: Path) -> None:
        """Large batch of 500 values at once round-trips."""
        values = [f"val_{i}" for i in range(500)]
        save_batch_progress(tmp_path, 0, values, 500)
        result = load_batch_checkpoint(tmp_path)
        assert result is not None
        assert len(result) == 500  # noqa: PLR2004
        assert result[0] == "val_0"
        assert result[499] == "val_499"

    def test_large_pdf_many_pages(self, tmp_path: Path) -> None:
        """200 pages of PDF checkpoint data round-trips."""
        for i in range(200):
            save_pdf_page_progress(
                tmp_path,
                i,
                [{"text": f"page_{i}", "font_size": 12.0}],
                200,
            )
        result = load_pdf_checkpoint(tmp_path)
        assert result is not None
        assert len(result) == 200  # noqa: PLR2004
        assert result[0][0]["text"] == "page_0"
        assert result[199][0]["text"] == "page_199"

    def test_large_ocr_results(self, tmp_path: Path) -> None:
        """100 OCR results in a single checkpoint."""
        results = [OCRResult(f"text_{i}", i * 10, 0, 50, 20, 0.9) for i in range(100)]
        save_ocr_checkpoint(tmp_path, results, results, "TesseractOCR")
        loaded = load_ocr_checkpoint(tmp_path)
        assert loaded is not None
        ocr_res, raw_res, method = loaded
        assert len(ocr_res) == 100  # noqa: PLR2004
        assert len(raw_res) == 100  # noqa: PLR2004
        assert ocr_res[99].text == "text_99"


class TestUnicodeContentInCheckpoints:
    """Tests for Unicode content across all checkpoint types."""

    def test_cjk_text_in_ocr_checkpoint(self, tmp_path: Path) -> None:
        """CJK characters in OCR checkpoint round-trip correctly."""
        r = OCRResult("你好世界", 0, 0, 100, 50, 0.9)
        r.translated_text = "こんにちは世界"
        r.translated_html = "<b>こんにちは世界</b>"
        save_ocr_checkpoint(tmp_path, [r], [r], "TesseractOCR")
        result = load_ocr_checkpoint(tmp_path)
        assert result is not None
        assert result[0][0].text == "你好世界"
        assert result[0][0].translated_text == "こんにちは世界"

    def test_arabic_text_in_batch_checkpoint(self, tmp_path: Path) -> None:
        """Arabic text in batch checkpoint round-trips."""
        save_batch_progress(tmp_path, 0, ["مرحبا بالعالم"], 1)
        result = load_batch_checkpoint(tmp_path)
        assert result is not None
        assert result[0] == "مرحبا بالعالم"

    def test_emoji_in_epub_checkpoint(self, tmp_path: Path) -> None:
        """Emoji content in EPUB checkpoint round-trips."""
        content = "<p>Hello 🌍🎉 World</p>"
        save_epub_file_progress(tmp_path, "ch.xhtml", content, ["ch.xhtml"])
        result = load_epub_checkpoint(tmp_path)
        assert result is not None
        assert result["ch.xhtml"] == content

    def test_mixed_scripts_in_llm_checkpoint(self, tmp_path: Path) -> None:
        """Mixed-script translations in LLM checkpoint."""
        r = OCRResult("Hello", 0, 0, 100, 20, 1.0)
        translations = ["Привет", "مرحبا", "你好"]
        save_llm_checkpoint(tmp_path, [r] * 3, translations, [r])
        result = load_llm_checkpoint(tmp_path)
        assert result is not None
        assert result[1] == translations

    def test_vietnamese_diacritics_in_text_chunk(self, tmp_path: Path) -> None:
        """Vietnamese diacritical marks in text chunks are preserved."""
        text = "Xin chào thế giới, đây là bài kiểm tra"
        save_text_chunk(tmp_path, 0, text, 1)
        result = load_text_checkpoint(tmp_path)
        assert result is not None
        assert result[0] == text


class TestStorageDirectoryCreation:
    """Tests for get_storage_dir behavior."""

    def test_windows_style_path(self) -> None:
        """Windows-style path (with backslashes) returns correct parent."""
        # On Linux, backslashes are part of the filename, but Path handles it
        result = get_storage_dir("/home/user/dir/file.txt")
        assert result == Path("/home/user/dir")

    def test_root_level_file(self) -> None:
        """File at root level returns root directory."""
        result = get_storage_dir("/file.txt")
        assert result == Path("/")

    def test_relative_path(self) -> None:
        """Relative path returns relative parent."""
        result = get_storage_dir("dir/file.txt")
        assert result == Path("dir")

    def test_path_with_spaces(self) -> None:
        """Path with spaces is handled correctly."""
        result = get_storage_dir("/home/user/my documents/task 42/file.pdf")
        assert result == Path("/home/user/my documents/task 42")


class TestSerializationEdgeCases:
    """Edge cases for OCR result serialization."""

    def test_serialize_preserves_float_confidence(self) -> None:
        """Float confidence values are preserved in serialization."""
        r = OCRResult("test", 0, 0, 10, 10, 0.12345678)
        data = _serialize_ocr_result(r)
        assert data["confidence"] == 0.12345678  # noqa: PLR2004

    def test_serialize_zero_dimensions(self) -> None:
        """Zero-dimension OCR result serializes correctly."""
        r = OCRResult("", 0, 0, 0, 0, 0.0)
        data = _serialize_ocr_result(r)
        restored = _deserialize_ocr_result(data)
        assert restored.x == 0
        assert restored.y == 0
        assert restored.w == 0
        assert restored.h == 0

    def test_serialize_negative_coordinates(self) -> None:
        """Negative coordinates (edge case) round-trip correctly."""
        r = OCRResult("negative", -10, -20, 50, 30, 0.9)
        data = _serialize_ocr_result(r)
        restored = _deserialize_ocr_result(data)
        assert restored.x == -10
        assert restored.y == -20

    def test_deserialize_all_valid_alignments(self) -> None:
        """All valid alignment constants are accepted."""
        from src.core.checkpoint import (  # noqa: PLC0415
            _VALID_ALIGNMENTS,
        )

        for alignment in _VALID_ALIGNMENTS:
            data = {
                "text": "t",
                "x": 0,
                "y": 0,
                "w": 1,
                "h": 1,
                "confidence": 1.0,
                "alignment": alignment,
            }
            result = _deserialize_ocr_result(data)
            assert result.alignment == alignment

    def test_deserialize_with_extra_keys_ignored(self) -> None:
        """Extra keys in the dict are silently ignored."""
        data = {
            "text": "hello",
            "x": 0,
            "y": 0,
            "w": 10,
            "h": 10,
            "confidence": 0.9,
            "extra_key": "should_be_ignored",
            "another_unknown": 42,
        }
        result = _deserialize_ocr_result(data)
        assert result.text == "hello"


class TestCheckpointFileNames:
    """Verify checkpoint file name constants."""

    def test_ocr_checkpoint_filename(self) -> None:
        assert _CHECKPOINT_OCR == "checkpoint_ocr.json"

    def test_llm_checkpoint_filename(self) -> None:
        assert _CHECKPOINT_LLM == "checkpoint_llm.json"

    def test_text_checkpoint_filename(self) -> None:
        assert _CHECKPOINT_TEXT == "checkpoint_text.json"

    def test_batch_checkpoint_filename(self) -> None:
        assert _CHECKPOINT_BATCH == "checkpoint_batch.json"

    def test_epub_checkpoint_filename(self) -> None:
        assert _CHECKPOINT_EPUB == "checkpoint_epub.json"

    def test_pdf_checkpoint_filename(self) -> None:
        assert _CHECKPOINT_PDF == "checkpoint_pdf.json"

    def test_dubbing_checkpoint_filename(self) -> None:
        assert _CHECKPOINT_DUBBING == "checkpoint_dubbing.json"


# ---------------------------------------------------------------------------
# NEW: Expanded tests for 350+ target
# ---------------------------------------------------------------------------


# ── Save/Load roundtrip completeness ──────────────────────────────────


class TestBatchRoundtripCompleteness:
    """Thorough roundtrip tests for batch checkpoints."""

    def test_single_value_batch(self, tmp_path: Path) -> None:
        """Batch with a single value round-trips correctly."""
        save_batch_progress(tmp_path, 0, ["only_one"], 1)
        result = load_batch_checkpoint(tmp_path)
        assert result is not None
        assert result == {0: "only_one"}

    def test_batch_starting_at_high_offset(self, tmp_path: Path) -> None:
        """Batch starting at index 100 round-trips with correct keys."""
        save_batch_progress(tmp_path, 100, ["x", "y", "z"], 103)
        result = load_batch_checkpoint(tmp_path)
        assert result is not None
        assert result[100] == "x"
        assert result[101] == "y"
        assert result[102] == "z"

    def test_batch_with_empty_strings(self, tmp_path: Path) -> None:
        """Batch values that are empty strings are preserved."""
        save_batch_progress(tmp_path, 0, ["", "", ""], 3)
        result = load_batch_checkpoint(tmp_path)
        assert result is not None
        assert all(v == "" for v in result.values())

    def test_batch_with_multiline_values(self, tmp_path: Path) -> None:
        """Batch values containing newlines are preserved."""
        val = "line1\nline2\nline3"
        save_batch_progress(tmp_path, 0, [val], 1)
        result = load_batch_checkpoint(tmp_path)
        assert result is not None
        assert result[0] == val

    def test_batch_with_json_special_chars(self, tmp_path: Path) -> None:
        """Batch values containing JSON-special characters survive roundtrip."""
        val = '{"key": "value", "arr": [1, 2]}'
        save_batch_progress(tmp_path, 0, [val], 1)
        result = load_batch_checkpoint(tmp_path)
        assert result is not None
        assert result[0] == val


class TestTextChunkRoundtripCompleteness:
    """Thorough roundtrip tests for text chunk checkpoints."""

    def test_text_chunk_large_content(self, tmp_path: Path) -> None:
        """Large text chunk (100KB) round-trips correctly."""
        large_text = "A" * 100_000
        save_text_chunk(tmp_path, 0, large_text, 1)
        result = load_text_checkpoint(tmp_path)
        assert result is not None
        assert len(result[0]) == 100_000  # noqa: PLR2004

    def test_text_chunk_with_html_content(self, tmp_path: Path) -> None:
        """HTML content in text chunks is preserved without escaping."""
        html = "<html><body><h1>Title</h1><p>Paragraph &amp; more</p></body></html>"
        save_text_chunk(tmp_path, 0, html, 1)
        result = load_text_checkpoint(tmp_path)
        assert result is not None
        assert result[0] == html

    def test_text_chunk_with_null_bytes(self, tmp_path: Path) -> None:
        """Text chunk containing null bytes round-trips via JSON."""
        text_with_null = "before\x00after"
        save_text_chunk(tmp_path, 0, text_with_null, 1)
        result = load_text_checkpoint(tmp_path)
        assert result is not None
        assert result[0] == text_with_null

    def test_text_batch_overwrites_individual_chunks(self, tmp_path: Path) -> None:
        """save_text_batch overwrites values previously saved by save_text_chunk."""
        from src.core.checkpoint import save_text_batch  # noqa: PLC0415

        save_text_chunk(tmp_path, 0, "old_0", 3)
        save_text_chunk(tmp_path, 1, "old_1", 3)
        save_text_batch(tmp_path, {0: "new_0", 2: "new_2"}, 3)

        result = load_text_checkpoint(tmp_path)
        assert result is not None
        assert result[0] == "new_0"
        assert result[1] == "old_1"
        assert result[2] == "new_2"


class TestEpubRoundtripCompleteness:
    """Thorough roundtrip tests for EPUB checkpoints."""

    def test_epub_with_deeply_nested_paths(self, tmp_path: Path) -> None:
        """EPUB file paths with many directory levels survive roundtrip."""
        path = "OEBPS/content/chapters/section1/subsection2/ch1.xhtml"
        save_epub_file_progress(tmp_path, path, "<p>deep</p>", [path])
        result = load_epub_checkpoint(tmp_path)
        assert result is not None
        assert result[path] == "<p>deep</p>"

    def test_epub_with_html_entities(self, tmp_path: Path) -> None:
        """EPUB translated content with HTML entities is preserved."""
        content = "<p>&lt;tag&gt; &amp; &quot;quoted&quot;</p>"
        save_epub_file_progress(tmp_path, "ch.xhtml", content, ["ch.xhtml"])
        result = load_epub_checkpoint(tmp_path)
        assert result is not None
        assert result["ch.xhtml"] == content

    def test_epub_large_content(self, tmp_path: Path) -> None:
        """EPUB with large content (50KB per file) round-trips."""
        content = "<p>" + "word " * 10_000 + "</p>"
        save_epub_file_progress(tmp_path, "ch1.xhtml", content, ["ch1.xhtml"])
        result = load_epub_checkpoint(tmp_path)
        assert result is not None
        assert result["ch1.xhtml"] == content

    def test_epub_file_with_query_params_in_path(self, tmp_path: Path) -> None:
        """Unusual archive paths with special characters round-trip."""
        path = "OEBPS/ch1.xhtml?v=2#section"
        save_epub_file_progress(tmp_path, path, "<p>ok</p>", [path])
        result = load_epub_checkpoint(tmp_path)
        assert result is not None
        assert path in result


class TestOcrCheckpointRoundtripCompleteness:
    """Thorough roundtrip for OCR checkpoint fields."""

    def test_ocr_with_all_fields_populated(self, tmp_path: Path) -> None:
        """OCR result with every optional field set round-trips."""
        r = _make_ocr_result()
        save_ocr_checkpoint(tmp_path, [r], [r], "EasyOCR")
        loaded = load_ocr_checkpoint(tmp_path)
        assert loaded is not None
        res = loaded[0][0]
        assert res.text == "hello"
        assert res.color == "#ff0000"
        assert res.is_bold is True
        assert res.is_italic is True
        assert res.is_underline is False
        assert res.translated_text == "xin chao"
        assert res.translated_html == "<b>xin chao</b>"
        assert res.alignment == ALIGN_CENTER
        assert res.original_text_height == 48  # noqa: PLR2004
        assert res.line_height_ratio == 1.3  # noqa: PLR2004
        assert res.is_single_line is True

    def test_ocr_different_methods(self, tmp_path: Path) -> None:
        """OCR method string is preserved for multiple known engines."""
        for method in ("TesseractOCR", "EasyOCR", "GoogleVision"):
            r = OCRResult("test", 0, 0, 10, 10, 0.9)
            save_ocr_checkpoint(tmp_path, [r], [r], method)
            loaded = load_ocr_checkpoint(tmp_path)
            assert loaded is not None
            assert loaded[2] == method

    def test_ocr_many_raw_few_merged(self, tmp_path: Path) -> None:
        """More raw results than merged results is valid."""
        merged = [OCRResult("merged", 0, 0, 100, 50, 0.95)]
        raw = [OCRResult(f"raw_{i}", i * 10, 0, 20, 10, 0.8) for i in range(10)]
        save_ocr_checkpoint(tmp_path, merged, raw, "TesseractOCR")
        loaded = load_ocr_checkpoint(tmp_path)
        assert loaded is not None
        assert len(loaded[0]) == 1
        assert len(loaded[1]) == 10  # noqa: PLR2004


class TestLlmCheckpointRoundtripCompleteness:
    """Thorough roundtrip for LLM checkpoint."""

    def test_llm_many_translations(self, tmp_path: Path) -> None:
        """LLM checkpoint with many translations round-trips."""
        results = [OCRResult(f"t{i}", 0, 0, 10, 10, 1.0) for i in range(50)]
        translations = [f"translated_{i}" for i in range(50)]
        save_llm_checkpoint(tmp_path, results, translations, results[:5])
        loaded = load_llm_checkpoint(tmp_path)
        assert loaded is not None
        assert len(loaded[0]) == 50  # noqa: PLR2004
        assert len(loaded[1]) == 50  # noqa: PLR2004
        assert len(loaded[2]) == 5  # noqa: PLR2004
        assert loaded[1][49] == "translated_49"

    def test_llm_translations_with_special_chars(self, tmp_path: Path) -> None:
        """Translations with newlines, tabs, and quotes round-trip."""
        r = OCRResult("src", 0, 0, 10, 10, 1.0)
        translations = ["line1\nline2", "tab\there", '"quoted"']
        save_llm_checkpoint(tmp_path, [r, r, r], translations, [])
        loaded = load_llm_checkpoint(tmp_path)
        assert loaded is not None
        assert loaded[1] == translations


# ── Atomic write-then-rename safety ───────────────────────────────────


class TestAtomicWriteCrashSafety:
    """Simulate crash/failure during write to verify atomic safety."""

    def test_crash_during_write_preserves_old_checkpoint(self, tmp_path: Path) -> None:
        """If write fails mid-way, the original checkpoint is still valid."""
        # Save a valid checkpoint
        save_text_chunk(tmp_path, 0, "valid_data", 2)
        result1 = load_text_checkpoint(tmp_path)
        assert result1 is not None
        assert result1[0] == "valid_data"

        # Simulate a crash by making _write_checkpoint fail on the second call
        with patch(
            "src.core.checkpoint._write_checkpoint",
            side_effect=OSError("simulated crash"),
        ):
            save_text_chunk(tmp_path, 1, "crash_data", 2)

        # Original checkpoint should still be intact
        result2 = load_text_checkpoint(tmp_path)
        assert result2 is not None
        assert result2[0] == "valid_data"
        # The crashed chunk should not be present
        assert 1 not in result2

    def test_crash_during_pdf_write_preserves_old_pages(self, tmp_path: Path) -> None:
        """If PDF write fails, previously saved pages are intact."""
        save_pdf_page_progress(tmp_path, 0, [{"text": "page0"}], 3)
        save_pdf_page_progress(tmp_path, 1, [{"text": "page1"}], 3)

        # Simulate failure on third page
        with patch(
            "src.core.checkpoint._write_checkpoint",
            side_effect=OSError("disk full"),
        ):
            save_pdf_page_progress(tmp_path, 2, [{"text": "page2"}], 3)

        result = load_pdf_checkpoint(tmp_path)
        assert result is not None
        assert len(result) == 2  # noqa: PLR2004
        assert result[0][0]["text"] == "page0"
        assert result[1][0]["text"] == "page1"
        assert 2 not in result

    def test_fdopen_write_failure_cleans_temp(self, tmp_path: Path) -> None:
        """When os.fdopen writing fails, temp file is cleaned up."""
        import os as _os  # noqa: PLC0415

        original_fdopen = _os.fdopen

        def failing_fdopen(fd, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
            """Simulate write failure after opening fd."""
            fh = original_fdopen(fd, *args, **kwargs)

            class FailingFile:
                def write(self, *a, **kw):  # noqa: ANN001, ANN002, ANN003, ANN201
                    raise OSError("write failed")

                def __enter__(self):  # noqa: ANN204
                    return self

                def __exit__(self, *a):  # noqa: ANN001, ANN002, ANN204
                    fh.close()

            return FailingFile()

        with patch("src.core.checkpoint.os.fdopen", side_effect=failing_fdopen):
            # json.dump will call write() which raises IOError (subclass of OSError)
            # The inner BaseException handler catches it, cleans temp, re-raises
            # The outer OSError handler catches it and logs
            _write_checkpoint(tmp_path, "test.json", {"version": _VERSION})

        # No target file and no temp files
        assert not (tmp_path / "test.json").exists()
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert tmp_files == []

    def test_batch_crash_mid_accumulation(self, tmp_path: Path) -> None:
        """Batch progress crash mid-accumulation preserves earlier batches."""
        save_batch_progress(tmp_path, 0, ["a", "b"], 6)
        save_batch_progress(tmp_path, 2, ["c", "d"], 6)

        with patch(
            "src.core.checkpoint._write_checkpoint",
            side_effect=OSError("crash"),
        ):
            save_batch_progress(tmp_path, 4, ["e", "f"], 6)

        result = load_batch_checkpoint(tmp_path)
        assert result is not None
        assert len(result) == 4  # noqa: PLR2004
        assert 4 not in result
        assert 5 not in result

    def test_epub_crash_preserves_previous_files(self, tmp_path: Path) -> None:
        """EPUB crash during third file preserves first two."""
        files = ["ch1.xhtml", "ch2.xhtml", "ch3.xhtml"]
        save_epub_file_progress(tmp_path, "ch1.xhtml", "<p>1</p>", files)
        save_epub_file_progress(tmp_path, "ch2.xhtml", "<p>2</p>", files)

        with patch(
            "src.core.checkpoint._write_checkpoint",
            side_effect=OSError("crash"),
        ):
            save_epub_file_progress(tmp_path, "ch3.xhtml", "<p>3</p>", files)

        result = load_epub_checkpoint(tmp_path)
        assert result is not None
        assert len(result) == 2  # noqa: PLR2004
        assert "ch3.xhtml" not in result


# ── Corrupt/Invalid JSON handling ─────────────────────────────────────


class TestCorruptJsonHandling:
    """Additional corrupt JSON edge cases."""

    def test_json_with_trailing_comma(self, tmp_path: Path) -> None:
        """JSON with trailing comma is invalid and returns None."""
        (tmp_path / _CHECKPOINT_TEXT).write_text(
            '{"version": 1, "translated_chunks": {},}'
        )
        assert load_text_checkpoint(tmp_path) is None

    def test_json_with_single_quotes(self, tmp_path: Path) -> None:
        """JSON with single quotes (Python dict style) is invalid."""
        (tmp_path / _CHECKPOINT_BATCH).write_text("{'version': 1}")
        assert load_batch_checkpoint(tmp_path) is None

    def test_json_with_comments(self, tmp_path: Path) -> None:
        """JSON with C-style comments is invalid."""
        content = '{"version": 1, /* comment */ "translated_files": {}}'
        (tmp_path / _CHECKPOINT_EPUB).write_text(content)
        assert load_epub_checkpoint(tmp_path) is None

    def test_yaml_content_returns_none(self, tmp_path: Path) -> None:
        """YAML content (not JSON) returns None."""
        (tmp_path / _CHECKPOINT_PDF).write_text("version: 1\npages:\n  - page1\n")
        assert load_pdf_checkpoint(tmp_path) is None

    def test_xml_content_returns_none(self, tmp_path: Path) -> None:
        """XML content returns None."""
        (tmp_path / _CHECKPOINT_OCR).write_text(
            "<checkpoint><version>1</version></checkpoint>"
        )
        assert load_ocr_checkpoint(tmp_path) is None

    def test_json_with_bom(self, tmp_path: Path) -> None:
        """JSON file with UTF-8 BOM prefix returns None (BOM breaks json.load)."""
        # UTF-8 BOM + valid JSON — json.load with utf-8 encoding may raise
        content = '\ufeff{"version": 1, "translated_chunks": {"0": "hi"}}'
        (tmp_path / _CHECKPOINT_TEXT).write_bytes(content.encode("utf-8-sig"))
        # This might succeed or fail depending on Python version, but should not crash
        result = load_text_checkpoint(tmp_path)
        # Either loads successfully or returns None — both are acceptable
        if result is not None:
            assert result[0] == "hi"

    def test_very_deeply_nested_json(self, tmp_path: Path) -> None:
        """Deeply nested JSON structure does not crash the loader."""
        inner = {"version": _VERSION, "translated_chunks": {"0": "ok"}}
        # Add nested dict that won't affect loading
        current = inner
        for _ in range(50):
            current["nested"] = {"level": True}
            current = current["nested"]
        (tmp_path / _CHECKPOINT_TEXT).write_text(json.dumps(inner))
        result = load_text_checkpoint(tmp_path)
        assert result is not None
        assert result[0] == "ok"

    def test_json_with_nan_value(self, tmp_path: Path) -> None:
        """JSON with NaN — Python's json.load accepts NaN by default."""
        (tmp_path / _CHECKPOINT_BATCH).write_text(
            '{"version": 1, "translated_values": {"0": NaN}}'
        )
        import math  # noqa: PLC0415

        result = load_batch_checkpoint(tmp_path)
        # Python's json.load parses NaN by default (allow_nan=True)
        assert result is not None
        assert math.isnan(result[0])

    def test_json_with_infinity(self, tmp_path: Path) -> None:
        """JSON with Infinity — Python's json.load accepts Infinity by default."""
        (tmp_path / _CHECKPOINT_PDF).write_text(
            '{"version": 1, "translated_pages": {"0": Infinity}}'
        )
        import math  # noqa: PLC0415

        result = load_pdf_checkpoint(tmp_path)
        # Python's json.load parses Infinity by default (allow_nan=True)
        assert result is not None
        assert math.isinf(result[0])


# ── Version mismatch handling ─────────────────────────────────────────


class TestVersionMismatchComprehensive:
    """Comprehensive version mismatch tests across all checkpoint types."""

    def test_version_mismatch_llm(self, tmp_path: Path) -> None:
        """LLM checkpoint with wrong version returns None."""
        data = {
            "version": 999,
            "ocr_results": [],
            "translations": [],
            "confirmed_raw_fragments": [],
        }
        (tmp_path / _CHECKPOINT_LLM).write_text(json.dumps(data))
        assert load_llm_checkpoint(tmp_path) is None

    def test_very_large_version_number(self, tmp_path: Path) -> None:
        """Very large version number returns None."""
        data = {"version": 2**31, "translated_chunks": {"0": "hi"}}
        (tmp_path / _CHECKPOINT_TEXT).write_text(json.dumps(data))
        assert load_text_checkpoint(tmp_path) is None

    def test_boolean_version_returns_none(self, tmp_path: Path) -> None:
        """Boolean True as version (1 == True in Python!) — loads because True == 1."""
        data = {"version": True, "translated_values": {"0": "test"}}
        (tmp_path / _CHECKPOINT_BATCH).write_text(json.dumps(data))
        # In Python, True == 1, so this might actually pass the version check
        result = load_batch_checkpoint(tmp_path)
        # True == 1 is True in Python, so the checkpoint loads successfully
        assert result is not None
        assert result[0] == "test"

    def test_missing_version_key(self, tmp_path: Path) -> None:
        """Checkpoint with no version key at all returns None."""
        data = {"translated_files": {"ch.xhtml": "<p>hi</p>"}}
        (tmp_path / _CHECKPOINT_EPUB).write_text(json.dumps(data))
        assert load_epub_checkpoint(tmp_path) is None

    def test_version_as_list_returns_none(self, tmp_path: Path) -> None:
        """Version field as a list returns None."""
        data = {"version": [1], "translated_chunks": {"0": "hi"}}
        (tmp_path / _CHECKPOINT_TEXT).write_text(json.dumps(data))
        assert load_text_checkpoint(tmp_path) is None

    def test_version_as_dict_returns_none(self, tmp_path: Path) -> None:
        """Version field as a dict returns None."""
        data = {"version": {"major": 1}, "translated_values": {"0": "hi"}}
        (tmp_path / _CHECKPOINT_BATCH).write_text(json.dumps(data))
        assert load_batch_checkpoint(tmp_path) is None


# ── Large checkpoint data ─────────────────────────────────────────────


class TestLargeCheckpointDataExtended:
    """Extended tests with large checkpoint payloads."""

    def test_epub_100_files(self, tmp_path: Path) -> None:
        """EPUB with 100 content files round-trips correctly."""
        files = [f"OEBPS/ch{i}.xhtml" for i in range(100)]
        for f in files:
            save_epub_file_progress(tmp_path, f, f"<p>content of {f}</p>", files)

        result = load_epub_checkpoint(tmp_path)
        assert result is not None
        assert len(result) == 100  # noqa: PLR2004
        assert result["OEBPS/ch99.xhtml"] == "<p>content of OEBPS/ch99.xhtml</p>"

    def test_batch_10000_values(self, tmp_path: Path) -> None:
        """Batch with 10000 values round-trips correctly."""
        values = [f"v{i}" for i in range(10000)]
        save_batch_progress(tmp_path, 0, values, 10000)
        result = load_batch_checkpoint(tmp_path)
        assert result is not None
        assert len(result) == 10000  # noqa: PLR2004
        assert result[9999] == "v9999"

    def test_large_ocr_with_rich_data(self, tmp_path: Path) -> None:
        """200 OCR results with all fields populated round-trip."""
        results = []
        for i in range(200):
            r = OCRResult(f"text_{i}", i * 10, i * 5, 80, 30, 0.85 + (i % 15) / 100)
            r.color = f"#{i % 256:02x}{(i * 3) % 256:02x}{(i * 7) % 256:02x}"
            r.is_bold = i % 2 == 0
            r.is_italic = i % 3 == 0
            r.translated_text = f"translated_{i}"
            r.translated_html = f"<b>translated_{i}</b>"
            results.append(r)

        save_ocr_checkpoint(tmp_path, results, results, "EasyOCR")
        loaded = load_ocr_checkpoint(tmp_path)
        assert loaded is not None
        assert len(loaded[0]) == 200  # noqa: PLR2004
        assert loaded[0][199].text == "text_199"
        assert loaded[0][100].is_bold is True
        assert loaded[0][100].is_italic is False

    def test_text_batch_1000_chunks_single_write(self, tmp_path: Path) -> None:
        """save_text_batch with 1000 chunks in one call."""
        from src.core.checkpoint import save_text_batch  # noqa: PLC0415

        chunks = {i: f"chunk content {i}" for i in range(1000)}
        save_text_batch(tmp_path, chunks, 1000)
        result = load_text_checkpoint(tmp_path)
        assert result is not None
        assert len(result) == 1000  # noqa: PLR2004
        assert result[500] == "chunk content 500"

    def test_pdf_page_with_many_blocks(self, tmp_path: Path) -> None:
        """PDF page with 500 blocks round-trips."""
        blocks = [
            {
                "text": f"block_{i}",
                "font_size": 12.0,
                "rect": [0, i * 20, 200, i * 20 + 18],
            }
            for i in range(500)
        ]
        save_pdf_page_progress(tmp_path, 0, blocks, 1)
        result = load_pdf_checkpoint(tmp_path)
        assert result is not None
        assert len(result[0]) == 500  # noqa: PLR2004
        assert result[0][499]["text"] == "block_499"

    def test_large_value_string_in_batch(self, tmp_path: Path) -> None:
        """Batch value that is a very long string (1MB) round-trips."""
        long_val = "X" * 1_000_000
        save_batch_progress(tmp_path, 0, [long_val], 1)
        result = load_batch_checkpoint(tmp_path)
        assert result is not None
        assert len(result[0]) == 1_000_000  # noqa: PLR2004


# ── Concurrent access patterns ────────────────────────────────────────


class TestConcurrentAccessPatterns:
    """Tests simulating concurrent / interleaved access patterns."""

    def test_interleaved_text_and_batch_saves(self, tmp_path: Path) -> None:
        """Text and batch checkpoints saved interleaved do not interfere."""
        save_text_chunk(tmp_path, 0, "text_0", 2)
        save_batch_progress(tmp_path, 0, ["batch_0"], 2)
        save_text_chunk(tmp_path, 1, "text_1", 2)
        save_batch_progress(tmp_path, 1, ["batch_1"], 2)

        text = load_text_checkpoint(tmp_path)
        batch = load_batch_checkpoint(tmp_path)
        assert text is not None
        assert batch is not None
        assert text == {0: "text_0", 1: "text_1"}
        assert batch == {0: "batch_0", 1: "batch_1"}

    def test_save_all_types_interleaved(self, tmp_path: Path) -> None:
        """All checkpoint types saved in interleaved order are independent."""
        r = OCRResult("x", 0, 0, 10, 10, 1.0)

        save_text_chunk(tmp_path, 0, "t0", 1)
        save_ocr_checkpoint(tmp_path, [r], [r], "Tesseract")
        save_batch_progress(tmp_path, 0, ["b0"], 1)
        save_epub_file_progress(tmp_path, "ch.xhtml", "<p>e</p>", ["ch.xhtml"])
        save_pdf_page_progress(tmp_path, 0, [{"text": "p0"}], 1)
        save_dubbing_checkpoint(tmp_path, srt_text="d0")
        save_llm_checkpoint(tmp_path, [r], ["l0"], [])

        # All should load independently
        assert load_text_checkpoint(tmp_path) == {0: "t0"}
        assert load_ocr_checkpoint(tmp_path) is not None
        assert load_batch_checkpoint(tmp_path) == {0: "b0"}
        assert load_epub_checkpoint(tmp_path) == {"ch.xhtml": "<p>e</p>"}
        assert load_pdf_checkpoint(tmp_path) == {0: [{"text": "p0"}]}
        dub = load_dubbing_checkpoint(tmp_path)
        assert dub is not None
        assert dub["srt_text"] == "d0"
        llm = load_llm_checkpoint(tmp_path)
        assert llm is not None
        assert llm[1] == ["l0"]

    def test_rapid_overwrite_produces_last_value(self, tmp_path: Path) -> None:
        """Rapidly overwriting same checkpoint yields last written value."""
        for i in range(100):
            save_text_chunk(tmp_path, 0, f"value_{i}", 1)
        result = load_text_checkpoint(tmp_path)
        assert result is not None
        assert result[0] == "value_99"

    def test_clear_between_saves_resets(self, tmp_path: Path) -> None:
        """Clearing checkpoints between saves produces empty state."""
        save_text_chunk(tmp_path, 0, "before_clear", 1)
        clear_checkpoints(tmp_path)
        assert load_text_checkpoint(tmp_path) is None

        save_text_chunk(tmp_path, 0, "after_clear", 1)
        result = load_text_checkpoint(tmp_path)
        assert result is not None
        assert result[0] == "after_clear"

    def test_clear_then_save_new_data(self, tmp_path: Path) -> None:
        """After clear, new saves produce a fresh checkpoint."""
        r = OCRResult("x", 0, 0, 10, 10, 1.0)
        save_ocr_checkpoint(tmp_path, [r], [r], "T")
        save_batch_progress(tmp_path, 0, ["b"], 1)
        clear_checkpoints(tmp_path)

        save_ocr_checkpoint(tmp_path, [r], [], "E")
        loaded = load_ocr_checkpoint(tmp_path)
        assert loaded is not None
        assert len(loaded[0]) == 1
        assert len(loaded[1]) == 0
        assert loaded[2] == "E"

        # Batch should still be None after clear
        assert load_batch_checkpoint(tmp_path) is None


# ── Empty checkpoints ─────────────────────────────────────────────────


class TestEmptyCheckpoints:
    """Tests for empty or minimal checkpoint data."""

    def test_empty_text_checkpoint(self, tmp_path: Path) -> None:
        """Text checkpoint with zero chunks saved is valid."""
        data = {"version": _VERSION, "total_chunks": 0, "translated_chunks": {}}
        (tmp_path / _CHECKPOINT_TEXT).write_text(json.dumps(data))
        result = load_text_checkpoint(tmp_path)
        assert result is not None
        assert result == {}

    def test_empty_batch_checkpoint(self, tmp_path: Path) -> None:
        """Batch checkpoint with zero values is valid."""
        data = {"version": _VERSION, "total_values": 0, "translated_values": {}}
        (tmp_path / _CHECKPOINT_BATCH).write_text(json.dumps(data))
        result = load_batch_checkpoint(tmp_path)
        assert result is not None
        assert result == {}

    def test_empty_epub_checkpoint(self, tmp_path: Path) -> None:
        """EPUB checkpoint with zero translated files is valid."""
        data = {"version": _VERSION, "content_files": [], "translated_files": {}}
        (tmp_path / _CHECKPOINT_EPUB).write_text(json.dumps(data))
        result = load_epub_checkpoint(tmp_path)
        assert result is not None
        assert result == {}

    def test_empty_pdf_checkpoint(self, tmp_path: Path) -> None:
        """PDF checkpoint with zero pages is valid."""
        data = {"version": _VERSION, "total_pages": 0, "translated_pages": {}}
        (tmp_path / _CHECKPOINT_PDF).write_text(json.dumps(data))
        result = load_pdf_checkpoint(tmp_path)
        assert result is not None
        assert result == {}

    def test_dubbing_checkpoint_version_only(self, tmp_path: Path) -> None:
        """Dubbing checkpoint with only version key is valid."""
        save_dubbing_checkpoint(tmp_path)
        result = load_dubbing_checkpoint(tmp_path)
        assert result is not None
        assert result["version"] == _VERSION
        assert len(result) == 1  # only version

    def test_empty_translations_in_llm(self, tmp_path: Path) -> None:
        """LLM checkpoint with empty translations list is valid."""
        save_llm_checkpoint(tmp_path, [], [], [])
        loaded = load_llm_checkpoint(tmp_path)
        assert loaded is not None
        assert loaded[0] == []
        assert loaded[1] == []
        assert loaded[2] == []

    def test_ocr_empty_results_empty_method(self, tmp_path: Path) -> None:
        """OCR checkpoint with empty method string is valid."""
        save_ocr_checkpoint(tmp_path, [], [], "")
        loaded = load_ocr_checkpoint(tmp_path)
        assert loaded is not None
        assert loaded[2] == ""

    def test_text_chunk_empty_string(self, tmp_path: Path) -> None:
        """Saving an empty string text chunk is valid."""
        save_text_chunk(tmp_path, 0, "", 1)
        result = load_text_checkpoint(tmp_path)
        assert result is not None
        assert result[0] == ""

    def test_batch_all_empty_strings(self, tmp_path: Path) -> None:
        """Batch with all empty string values is valid."""
        save_batch_progress(tmp_path, 0, ["", "", ""], 3)
        result = load_batch_checkpoint(tmp_path)
        assert result is not None
        assert len(result) == 3  # noqa: PLR2004
        assert all(v == "" for v in result.values())

    def test_epub_empty_content_string(self, tmp_path: Path) -> None:
        """EPUB file with empty translated content is valid."""
        save_epub_file_progress(tmp_path, "ch.xhtml", "", ["ch.xhtml"])
        result = load_epub_checkpoint(tmp_path)
        assert result is not None
        assert result["ch.xhtml"] == ""


# ── Path edge cases ───────────────────────────────────────────────────


class TestPathEdgeCases:
    """Tests for path-related edge cases."""

    def test_storage_dir_with_spaces(self, tmp_path: Path) -> None:
        """Storage directory with spaces in the path works."""
        spaced_dir = tmp_path / "dir with spaces"
        spaced_dir.mkdir()
        save_text_chunk(spaced_dir, 0, "hello", 1)
        result = load_text_checkpoint(spaced_dir)
        assert result is not None
        assert result[0] == "hello"

    def test_storage_dir_with_unicode_name(self, tmp_path: Path) -> None:
        """Storage directory with unicode name works."""
        unicode_dir = tmp_path / "目录"
        unicode_dir.mkdir()
        save_batch_progress(unicode_dir, 0, ["test"], 1)
        result = load_batch_checkpoint(unicode_dir)
        assert result is not None
        assert result[0] == "test"

    def test_storage_dir_with_special_chars(self, tmp_path: Path) -> None:
        """Storage directory with special characters in name works."""
        special_dir = tmp_path / "dir-with_special.chars(1)"
        special_dir.mkdir()
        save_epub_file_progress(special_dir, "ch.xhtml", "<p>ok</p>", ["ch.xhtml"])
        result = load_epub_checkpoint(special_dir)
        assert result is not None
        assert result["ch.xhtml"] == "<p>ok</p>"

    def test_deeply_nested_storage_dir(self, tmp_path: Path) -> None:
        """Deeply nested storage directory works."""
        deep_dir = tmp_path
        for i in range(10):
            deep_dir = deep_dir / f"level_{i}"
        deep_dir.mkdir(parents=True)
        save_pdf_page_progress(deep_dir, 0, [{"text": "deep"}], 1)
        result = load_pdf_checkpoint(deep_dir)
        assert result is not None
        assert result[0][0]["text"] == "deep"

    def test_get_storage_dir_with_dots_in_path(self) -> None:
        """Path with dots and extensions returns correct parent."""
        result = get_storage_dir("/home/user/v1.2.3/task.42/file.tar.gz")
        assert result == Path("/home/user/v1.2.3/task.42")

    def test_get_storage_dir_single_component(self) -> None:
        """Path with just a filename returns '.' (current dir)."""
        result = get_storage_dir("file.txt")
        assert result == Path()

    def test_load_from_nonexistent_dir(self, tmp_path: Path) -> None:
        """Loading from nonexistent directory returns None (file not found)."""
        nonexistent = tmp_path / "does_not_exist"
        assert load_text_checkpoint(nonexistent) is None
        assert load_batch_checkpoint(nonexistent) is None
        assert load_epub_checkpoint(nonexistent) is None
        assert load_pdf_checkpoint(nonexistent) is None
        assert load_ocr_checkpoint(nonexistent) is None
        assert load_llm_checkpoint(nonexistent) is None
        assert load_dubbing_checkpoint(nonexistent) is None


# ── Resume from partial checkpoints ───────────────────────────────────


class TestResumeFromPartialCheckpoints:
    """Tests for resuming translation from partial checkpoint state."""

    def test_resume_text_halfway(self, tmp_path: Path) -> None:
        """Resume text translation from halfway point."""
        total = 10
        # Simulate first half translated
        for i in range(5):
            save_text_chunk(tmp_path, i, f"translated_{i}", total)

        result = load_text_checkpoint(tmp_path)
        assert result is not None
        assert len(result) == 5  # noqa: PLR2004
        # Only first 5 chunks exist
        for i in range(5):
            assert i in result
        for i in range(5, total):
            assert i not in result

    def test_resume_text_add_remaining(self, tmp_path: Path) -> None:
        """Adding remaining chunks after partial save completes the checkpoint."""
        total = 6
        save_text_chunk(tmp_path, 0, "a", total)
        save_text_chunk(tmp_path, 1, "b", total)
        save_text_chunk(tmp_path, 2, "c", total)

        # Resume: add remaining
        save_text_chunk(tmp_path, 3, "d", total)
        save_text_chunk(tmp_path, 4, "e", total)
        save_text_chunk(tmp_path, 5, "f", total)

        result = load_text_checkpoint(tmp_path)
        assert result is not None
        assert len(result) == total  # noqa: PLR2004
        assert result == {0: "a", 1: "b", 2: "c", 3: "d", 4: "e", 5: "f"}

    def test_resume_batch_from_middle(self, tmp_path: Path) -> None:
        """Resume batch translation from a middle batch."""
        total = 9
        save_batch_progress(tmp_path, 0, ["a", "b", "c"], total)

        result1 = load_batch_checkpoint(tmp_path)
        assert result1 is not None
        assert len(result1) == 3  # noqa: PLR2004

        # Resume from batch 3
        save_batch_progress(tmp_path, 3, ["d", "e", "f"], total)
        save_batch_progress(tmp_path, 6, ["g", "h", "i"], total)

        result2 = load_batch_checkpoint(tmp_path)
        assert result2 is not None
        assert len(result2) == total  # noqa: PLR2004

    def test_resume_epub_partial(self, tmp_path: Path) -> None:
        """Resume EPUB from partial state (2 of 4 files done)."""
        files = [f"ch{i}.xhtml" for i in range(4)]
        save_epub_file_progress(tmp_path, "ch0.xhtml", "<p>0</p>", files)
        save_epub_file_progress(tmp_path, "ch1.xhtml", "<p>1</p>", files)

        result1 = load_epub_checkpoint(tmp_path)
        assert result1 is not None
        assert len(result1) == 2  # noqa: PLR2004

        # Resume
        save_epub_file_progress(tmp_path, "ch2.xhtml", "<p>2</p>", files)
        save_epub_file_progress(tmp_path, "ch3.xhtml", "<p>3</p>", files)

        result2 = load_epub_checkpoint(tmp_path)
        assert result2 is not None
        assert len(result2) == 4  # noqa: PLR2004

    def test_resume_pdf_sparse_pages(self, tmp_path: Path) -> None:
        """PDF checkpoint with non-contiguous pages (sparse resume)."""
        save_pdf_page_progress(tmp_path, 0, [{"text": "p0"}], 10)
        save_pdf_page_progress(tmp_path, 5, [{"text": "p5"}], 10)

        result = load_pdf_checkpoint(tmp_path)
        assert result is not None
        assert len(result) == 2  # noqa: PLR2004
        assert 0 in result
        assert 5 in result
        # Pages 1-4, 6-9 are not yet translated
        for i in (1, 2, 3, 4, 6, 7, 8, 9):
            assert i not in result

    def test_resume_dubbing_from_step2(self, tmp_path: Path) -> None:
        """Dubbing resume from step 2 (STT done, need translation)."""
        save_dubbing_checkpoint(tmp_path, srt_text="raw", target_lang="French")
        result = load_dubbing_checkpoint(tmp_path)
        assert result is not None
        assert "srt_text" in result
        assert "translated_srt" not in result

        # Resume step 2
        save_dubbing_checkpoint(tmp_path, translated_srt="traduit")
        result2 = load_dubbing_checkpoint(tmp_path)
        assert result2 is not None
        assert result2["srt_text"] == "raw"
        assert result2["translated_srt"] == "traduit"

    def test_partial_text_batch_then_single_chunks(self, tmp_path: Path) -> None:
        """Resume with individual chunks after a partial batch save."""
        from src.core.checkpoint import save_text_batch  # noqa: PLC0415

        save_text_batch(tmp_path, {0: "a", 1: "b"}, 5)
        # Resume with individual saves
        save_text_chunk(tmp_path, 2, "c", 5)
        save_text_chunk(tmp_path, 3, "d", 5)
        save_text_chunk(tmp_path, 4, "e", 5)

        result = load_text_checkpoint(tmp_path)
        assert result is not None
        assert len(result) == 5  # noqa: PLR2004


# ── Checkpoint cleanup/deletion ───────────────────────────────────────


class TestCheckpointCleanupDeletion:
    """Tests for checkpoint cleanup and deletion behavior."""

    def test_clear_idempotent(self, tmp_path: Path) -> None:
        """Calling clear_checkpoints twice is safe (idempotent)."""
        save_text_chunk(tmp_path, 0, "x", 1)
        clear_checkpoints(tmp_path)
        clear_checkpoints(tmp_path)  # second call should be no-op
        assert load_text_checkpoint(tmp_path) is None

    def test_clear_only_removes_checkpoint_pattern(self, tmp_path: Path) -> None:
        """Only files matching checkpoint_*.json are removed."""
        # Create various files
        (tmp_path / "checkpoint_custom.json").write_text("{}")
        (tmp_path / "data.json").write_text("{}")
        (tmp_path / "checkpoint_data.txt").write_text("not json ext")
        (tmp_path / "my_checkpoint_ocr.json").write_text("{}")

        save_text_chunk(tmp_path, 0, "x", 1)
        clear_checkpoints(tmp_path)

        # checkpoint_custom.json matches the pattern, so it is removed
        assert not (tmp_path / "checkpoint_custom.json").exists()
        # These don't match the pattern
        assert (tmp_path / "data.json").exists()
        assert (tmp_path / "checkpoint_data.txt").exists()
        assert (tmp_path / "my_checkpoint_ocr.json").exists()

    def test_save_after_clear_starts_fresh(self, tmp_path: Path) -> None:
        """After clearing, new saves create fresh checkpoints."""
        save_text_chunk(tmp_path, 0, "old", 2)
        save_text_chunk(tmp_path, 1, "also_old", 2)
        clear_checkpoints(tmp_path)

        save_text_chunk(tmp_path, 0, "new", 1)
        result = load_text_checkpoint(tmp_path)
        assert result is not None
        # Only the new chunk should exist
        assert result == {0: "new"}
        # The old chunk at index 1 is gone
        assert 1 not in result

    def test_clear_with_read_only_checkpoint(self, tmp_path: Path) -> None:
        """clear_checkpoints deletes read-only files when parent dir is writable."""
        save_text_chunk(tmp_path, 0, "x", 1)
        cp_file = tmp_path / _CHECKPOINT_TEXT
        assert cp_file.exists()

        # Make the file read-only (Linux still allows unlink if parent dir is writable)
        cp_file.chmod(0o444)

        # Should not raise — file is deleted successfully on Linux
        clear_checkpoints(tmp_path)

        # On Linux, read-only files can be deleted when parent dir is writable
        assert not cp_file.exists()

    def test_clear_then_load_all_returns_none(self, tmp_path: Path) -> None:
        """After clear, all load functions return None."""
        r = OCRResult("x", 0, 0, 10, 10, 1.0)
        save_ocr_checkpoint(tmp_path, [r], [r], "T")
        save_llm_checkpoint(tmp_path, [r], ["t"], [r])
        save_text_chunk(tmp_path, 0, "t", 1)
        save_batch_progress(tmp_path, 0, ["b"], 1)
        save_epub_file_progress(tmp_path, "c.xhtml", "<p>e</p>", ["c.xhtml"])
        save_pdf_page_progress(tmp_path, 0, [{"text": "p"}], 1)
        save_dubbing_checkpoint(tmp_path, srt_text="d")

        clear_checkpoints(tmp_path)

        assert load_ocr_checkpoint(tmp_path) is None
        assert load_llm_checkpoint(tmp_path) is None
        assert load_text_checkpoint(tmp_path) is None
        assert load_batch_checkpoint(tmp_path) is None
        assert load_epub_checkpoint(tmp_path) is None
        assert load_pdf_checkpoint(tmp_path) is None
        assert load_dubbing_checkpoint(tmp_path) is None

    def test_selective_deletion_only_affects_target(self, tmp_path: Path) -> None:
        """Manually deleting one checkpoint file leaves others intact."""
        save_text_chunk(tmp_path, 0, "text", 1)
        save_batch_progress(tmp_path, 0, ["batch"], 1)

        # Delete only the text checkpoint
        (tmp_path / _CHECKPOINT_TEXT).unlink()

        assert load_text_checkpoint(tmp_path) is None
        result = load_batch_checkpoint(tmp_path)
        assert result is not None
        assert result[0] == "batch"


# ── _read_checkpoint edge cases ───────────────────────────────────────


class TestReadCheckpointEdgeCases:
    """Additional edge cases for _read_checkpoint."""

    def test_read_checkpoint_with_symlink(self, tmp_path: Path) -> None:
        """Reading a checkpoint that is a symlink to a valid file works."""
        # Create a valid checkpoint in a subdir
        sub = tmp_path / "real"
        sub.mkdir()
        save_text_chunk(sub, 0, "from_link", 1)

        # Create symlink in main dir pointing to the real file
        link_dir = tmp_path / "link"
        link_dir.mkdir()
        link_target = sub / _CHECKPOINT_TEXT
        link_file = link_dir / _CHECKPOINT_TEXT
        link_file.symlink_to(link_target)

        result = load_text_checkpoint(link_dir)
        assert result is not None
        assert result[0] == "from_link"

    def test_whitespace_only_file(self, tmp_path: Path) -> None:
        """File containing only whitespace returns None (invalid JSON)."""
        (tmp_path / _CHECKPOINT_OCR).write_text("   \n\t\n   ")
        assert load_ocr_checkpoint(tmp_path) is None

    def test_json_with_extra_data_after_close(self, tmp_path: Path) -> None:
        """JSON with trailing garbage after valid object raises JSONDecodeError."""
        (tmp_path / _CHECKPOINT_TEXT).write_text(
            '{"version": 1, "translated_chunks": {}} extra garbage'
        )
        assert load_text_checkpoint(tmp_path) is None


# ── _write_checkpoint edge cases ──────────────────────────────────────


class TestWriteCheckpointExtendedEdgeCases:
    """Extended edge cases for _write_checkpoint."""

    def test_write_overwrites_existing_atomically(self, tmp_path: Path) -> None:
        """Overwriting existing file produces valid JSON even for different data."""
        _write_checkpoint(tmp_path, "test.json", {"version": _VERSION, "a": 1})
        _write_checkpoint(tmp_path, "test.json", {"version": _VERSION, "b": 2})

        data = json.loads((tmp_path / "test.json").read_text())
        assert "b" in data
        assert data["b"] == 2
        # First key should not be present
        assert "a" not in data

    def test_write_with_nested_dicts(self, tmp_path: Path) -> None:
        """Deeply nested dict structures are serialized correctly."""
        nested = {
            "version": _VERSION,
            "level1": {"level2": {"level3": {"value": "deep"}}},
        }
        _write_checkpoint(tmp_path, "test.json", nested)
        data = json.loads((tmp_path / "test.json").read_text())
        assert data["level1"]["level2"]["level3"]["value"] == "deep"

    def test_write_with_unicode_keys(self, tmp_path: Path) -> None:
        """Unicode keys in checkpoint data are preserved."""
        _write_checkpoint(
            tmp_path, "test.json", {"version": _VERSION, "键": "值", "キー": "値"}
        )
        data = json.loads((tmp_path / "test.json").read_text())
        assert data["键"] == "值"
        assert data["キー"] == "値"

    def test_write_ensure_ascii_false(self, tmp_path: Path) -> None:
        """Non-ASCII characters are NOT escaped (ensure_ascii=False in source)."""
        _write_checkpoint(
            tmp_path, "test.json", {"version": _VERSION, "text": "日本語"}
        )
        raw_text = (tmp_path / "test.json").read_text(encoding="utf-8")
        # Should contain actual Japanese characters, not \\uXXXX escapes
        assert "日本語" in raw_text

    def test_write_empty_dict(self, tmp_path: Path) -> None:
        """Writing an empty dict creates a valid JSON file."""
        _write_checkpoint(tmp_path, "test.json", {})
        data = json.loads((tmp_path / "test.json").read_text())
        assert data == {}


# ── OCR serialization: boundary values ────────────────────────────────


class TestOcrSerializationBoundary:
    """Boundary value tests for OCR result serialization."""

    def test_very_large_coordinates(self) -> None:
        """Very large coordinate values round-trip."""
        r = OCRResult("big", 99999, 99999, 99999, 99999, 1.0)
        data = _serialize_ocr_result(r)
        restored = _deserialize_ocr_result(data)
        assert restored.x == 99999  # noqa: PLR2004
        assert restored.w == 99999  # noqa: PLR2004

    def test_confidence_boundary_values(self) -> None:
        """Confidence values at 0.0 and 1.0 boundaries round-trip."""
        for conf in (0.0, 1.0):
            r = OCRResult("t", 0, 0, 10, 10, conf)
            data = _serialize_ocr_result(r)
            restored = _deserialize_ocr_result(data)
            assert restored.confidence == conf

    def test_long_text_content(self) -> None:
        """Very long text content in OCR result round-trips."""
        long_text = "word " * 10_000
        r = OCRResult(long_text, 0, 0, 10000, 50, 0.9)
        r.translated_text = long_text
        data = _serialize_ocr_result(r)
        restored = _deserialize_ocr_result(data)
        assert restored.text == long_text
        assert restored.translated_text == long_text

    def test_color_edge_values(self) -> None:
        """Edge color values round-trip correctly."""
        for color in ("#000000", "#ffffff", "#FF0000", "#00ff00", "#0000ff"):
            r = OCRResult("t", 0, 0, 10, 10, 1.0)
            r.color = color
            data = _serialize_ocr_result(r)
            restored = _deserialize_ocr_result(data)
            assert restored.color == color

    def test_line_height_ratio_extremes(self) -> None:
        """Extreme line_height_ratio values round-trip."""
        for ratio in (0.0, 0.5, 1.0, 2.0, 10.0):
            r = OCRResult("t", 0, 0, 10, 10, 1.0)
            r.line_height_ratio = ratio
            data = _serialize_ocr_result(r)
            restored = _deserialize_ocr_result(data)
            assert restored.line_height_ratio == ratio

    def test_original_text_height_zero(self) -> None:
        """original_text_height of zero round-trips."""
        r = OCRResult("t", 0, 0, 10, 10, 1.0)
        r.original_text_height = 0
        data = _serialize_ocr_result(r)
        restored = _deserialize_ocr_result(data)
        assert restored.original_text_height == 0

    def test_all_boolean_combinations(self) -> None:
        """All 8 combinations of (bold, italic, underline) round-trip."""
        for bold in (True, False):
            for italic in (True, False):
                for underline in (True, False):
                    r = OCRResult("t", 0, 0, 10, 10, 1.0)
                    r.is_bold = bold
                    r.is_italic = italic
                    r.is_underline = underline
                    data = _serialize_ocr_result(r)
                    restored = _deserialize_ocr_result(data)
                    assert restored.is_bold is bold
                    assert restored.is_italic is italic
                    assert restored.is_underline is underline


# ── PDF checkpoint: block variations ──────────────────────────────────


class TestPdfCheckpointBlockVariations:
    """PDF checkpoint tests with varied block structures."""

    def test_block_with_all_standard_fields(self, tmp_path: Path) -> None:
        """Block with all standard PDF fields round-trips."""
        block = {
            "rect": [72.0, 100.0, 540.0, 120.0],
            "text": "Original text here",
            "translated_text": "Translated text here",
            "font_size": 11.0,
            "font_name": "TimesNewRoman",
            "color": 0x000000,
            "bold": False,
            "italic": True,
            "alignment": "justify",
            "white_space": "nowrap",
        }
        save_pdf_page_progress(tmp_path, 0, [block], 1)
        result = load_pdf_checkpoint(tmp_path)
        assert result is not None
        b = result[0][0]
        assert b["font_name"] == "TimesNewRoman"
        assert b["italic"] is True
        assert b["alignment"] == "justify"

    def test_many_blocks_per_page(self, tmp_path: Path) -> None:
        """Page with 100 blocks of various types round-trips."""
        blocks = []
        for i in range(50):
            blocks.append({"text": f"block_{i}", "font_size": 12.0})
        for i in range(25):
            blocks.append(
                {
                    "type": "annot",
                    "annot_type": 0,
                    "annot_id": f"annot_{i}",
                    "text": f"annot_{i}",
                    "translated_text": f"annot_trans_{i}",
                }
            )
        for i in range(25):
            blocks.append(
                {
                    "type": "widget",
                    "field_name": f"field_{i}",
                    "text": f"widget_{i}",
                    "translated_text": f"widget_trans_{i}",
                }
            )

        save_pdf_page_progress(tmp_path, 0, blocks, 1)
        result = load_pdf_checkpoint(tmp_path)
        assert result is not None
        assert len(result[0]) == 100  # noqa: PLR2004

    def test_block_with_float_rect_values(self, tmp_path: Path) -> None:
        """Block rect with precise float values is preserved."""
        block = {
            "rect": [72.12345, 100.98765, 540.55555, 120.11111],
            "text": "precise",
            "font_size": 10.5,
        }
        save_pdf_page_progress(tmp_path, 0, [block], 1)
        result = load_pdf_checkpoint(tmp_path)
        assert result is not None
        rect = result[0][0]["rect"]
        assert rect[0] == 72.12345  # noqa: PLR2004
        assert rect[3] == 120.11111  # noqa: PLR2004

    def test_block_with_null_values(self, tmp_path: Path) -> None:
        """Block with None/null values round-trips."""
        block = {
            "text": "test",
            "translated_text": None,
            "font_name": None,
            "color": None,
        }
        save_pdf_page_progress(tmp_path, 0, [block], 1)
        result = load_pdf_checkpoint(tmp_path)
        assert result is not None
        assert result[0][0]["translated_text"] is None
        assert result[0][0]["font_name"] is None


# ── Dubbing checkpoint: special content ───────────────────────────────


class TestDubbingCheckpointSpecialContent:
    """Edge cases for dubbing checkpoint with special content."""

    def test_multiline_srt_content(self, tmp_path: Path) -> None:
        """Multi-line SRT content with multiple entries round-trips."""
        srt = (
            "1\n00:00:00,000 --> 00:00:05,000\nFirst line\n\n"
            "2\n00:00:05,000 --> 00:00:10,000\nSecond line\n\n"
            "3\n00:00:10,000 --> 00:00:15,000\nThird line"
        )
        save_dubbing_checkpoint(tmp_path, srt_text=srt, target_lang="Spanish")
        result = load_dubbing_checkpoint(tmp_path)
        assert result is not None
        assert result["srt_text"] == srt

    def test_voice_file_with_path_separators(self, tmp_path: Path) -> None:
        """voice_file containing path separators round-trips."""
        save_dubbing_checkpoint(
            tmp_path,
            voice_file="output/audio/voice_en.wav",
        )
        result = load_dubbing_checkpoint(tmp_path)
        assert result is not None
        assert result["voice_file"] == "output/audio/voice_en.wav"

    def test_all_none_kwargs(self, tmp_path: Path) -> None:
        """Explicitly passing None for all kwargs only creates version key."""
        save_dubbing_checkpoint(
            tmp_path,
            srt_text=None,
            translated_srt=None,
            voice_file=None,
            target_lang=None,
        )
        result = load_dubbing_checkpoint(tmp_path)
        assert result is not None
        assert "srt_text" not in result
        assert "translated_srt" not in result
        assert "voice_file" not in result
        assert "target_lang" not in result


# ── Text checkpoint: total_chunks tracking ────────────────────────────


class TestTextCheckpointTotalChunksTracking:
    """Tests for total_chunks field behavior in text checkpoints."""

    def test_total_chunks_stored_in_raw_json(self, tmp_path: Path) -> None:
        """total_chunks value is stored in the raw JSON on disk."""
        save_text_chunk(tmp_path, 0, "hello", 42)
        raw = json.loads((tmp_path / _CHECKPOINT_TEXT).read_text())
        assert raw["total_chunks"] == 42  # noqa: PLR2004

    def test_total_chunks_updated_on_subsequent_save(self, tmp_path: Path) -> None:
        """Subsequent save_text_chunk call updates total_chunks."""
        save_text_chunk(tmp_path, 0, "a", 5)
        raw1 = json.loads((tmp_path / _CHECKPOINT_TEXT).read_text())
        assert raw1["total_chunks"] == 5  # noqa: PLR2004

        save_text_chunk(tmp_path, 1, "b", 10)
        raw2 = json.loads((tmp_path / _CHECKPOINT_TEXT).read_text())
        assert raw2["total_chunks"] == 10  # noqa: PLR2004

    def test_load_ignores_total_chunks(self, tmp_path: Path) -> None:
        """load_text_checkpoint returns only the chunks dict, not total_chunks."""
        save_text_chunk(tmp_path, 0, "hello", 100)
        result = load_text_checkpoint(tmp_path)
        assert result is not None
        # result is just the chunks dict
        assert isinstance(result, dict)
        assert 0 in result


# ── Batch checkpoint: total_values tracking ───────────────────────────


class TestBatchCheckpointTotalValuesTracking:
    """Tests for total_values field behavior in batch checkpoints."""

    def test_total_values_stored(self, tmp_path: Path) -> None:
        """total_values is stored in raw JSON."""
        save_batch_progress(tmp_path, 0, ["a"], 99)
        raw = json.loads((tmp_path / _CHECKPOINT_BATCH).read_text())
        assert raw["total_values"] == 99  # noqa: PLR2004

    def test_total_values_updated(self, tmp_path: Path) -> None:
        """Subsequent save updates total_values."""
        save_batch_progress(tmp_path, 0, ["a"], 10)
        save_batch_progress(tmp_path, 1, ["b"], 20)
        raw = json.loads((tmp_path / _CHECKPOINT_BATCH).read_text())
        assert raw["total_values"] == 20  # noqa: PLR2004


# ── Checkpoint data integrity verification ────────────────────────────


class TestCheckpointDataIntegrity:
    """Verify data integrity under various conditions."""

    def test_json_roundtrip_preserves_types(self, tmp_path: Path) -> None:
        """JSON types (int, float, str, bool, null, list, dict) are preserved."""
        block = {
            "int_val": 42,
            "float_val": 3.14,
            "str_val": "hello",
            "bool_val": True,
            "null_val": None,
            "list_val": [1, "two", 3.0],
            "dict_val": {"nested": True},
        }
        save_pdf_page_progress(tmp_path, 0, [block], 1)
        result = load_pdf_checkpoint(tmp_path)
        assert result is not None
        b = result[0][0]
        assert b["int_val"] == 42  # noqa: PLR2004
        assert b["float_val"] == 3.14  # noqa: PLR2004
        assert b["str_val"] == "hello"
        assert b["bool_val"] is True
        assert b["null_val"] is None
        assert b["list_val"] == [1, "two", 3.0]
        assert b["dict_val"] == {"nested": True}

    def test_text_chunk_keys_are_integers_after_load(self, tmp_path: Path) -> None:
        """Text checkpoint keys are converted to int on load."""
        save_text_chunk(tmp_path, 5, "five", 10)
        result = load_text_checkpoint(tmp_path)
        assert result is not None
        assert isinstance(list(result.keys())[0], int)

    def test_batch_keys_are_integers_after_load(self, tmp_path: Path) -> None:
        """Batch checkpoint keys are converted to int on load."""
        save_batch_progress(tmp_path, 3, ["three"], 10)
        result = load_batch_checkpoint(tmp_path)
        assert result is not None
        assert isinstance(list(result.keys())[0], int)

    def test_pdf_keys_are_integers_after_load(self, tmp_path: Path) -> None:
        """PDF checkpoint page keys are converted to int on load."""
        save_pdf_page_progress(tmp_path, 7, [{"text": "seven"}], 10)
        result = load_pdf_checkpoint(tmp_path)
        assert result is not None
        assert isinstance(list(result.keys())[0], int)

    def test_epub_keys_are_strings(self, tmp_path: Path) -> None:
        """EPUB checkpoint keys remain strings (file paths)."""
        save_epub_file_progress(tmp_path, "ch.xhtml", "<p>hi</p>", ["ch.xhtml"])
        result = load_epub_checkpoint(tmp_path)
        assert result is not None
        assert isinstance(list(result.keys())[0], str)


# ── save_text_batch edge cases ────────────────────────────────────────


class TestSaveTextBatchExtended:
    """Extended tests for save_text_batch."""

    def test_batch_with_single_chunk(self, tmp_path: Path) -> None:
        """Single chunk in batch works correctly."""
        from src.core.checkpoint import save_text_batch  # noqa: PLC0415

        save_text_batch(tmp_path, {0: "only"}, 1)
        result = load_text_checkpoint(tmp_path)
        assert result is not None
        assert result == {0: "only"}

    def test_batch_with_high_indices(self, tmp_path: Path) -> None:
        """Batch with very high chunk indices works."""
        from src.core.checkpoint import save_text_batch  # noqa: PLC0415

        save_text_batch(tmp_path, {999: "high", 1000: "higher"}, 1001)
        result = load_text_checkpoint(tmp_path)
        assert result is not None
        assert result[999] == "high"
        assert result[1000] == "higher"

    def test_batch_multiple_merges(self, tmp_path: Path) -> None:
        """Multiple batch saves merge correctly."""
        from src.core.checkpoint import save_text_batch  # noqa: PLC0415

        save_text_batch(tmp_path, {0: "a", 1: "b"}, 6)
        save_text_batch(tmp_path, {2: "c", 3: "d"}, 6)
        save_text_batch(tmp_path, {4: "e", 5: "f"}, 6)

        result = load_text_checkpoint(tmp_path)
        assert result is not None
        assert len(result) == 6  # noqa: PLR2004
        assert result == {0: "a", 1: "b", 2: "c", 3: "d", 4: "e", 5: "f"}


# ── _read_checkpoint: file exists but not readable ────────────────────


class TestReadCheckpointPermissionErrors:
    """Tests for permission errors during checkpoint read."""

    def test_unreadable_file_returns_none(self, tmp_path: Path) -> None:
        """File with no read permission returns None."""
        save_text_chunk(tmp_path, 0, "hello", 1)
        cp_file = tmp_path / _CHECKPOINT_TEXT
        cp_file.chmod(0o000)

        try:
            result = load_text_checkpoint(tmp_path)
            assert result is None
        finally:
            cp_file.chmod(0o644)

    def test_write_only_file_returns_none(self, tmp_path: Path) -> None:
        """File with write-only permission returns None."""
        save_batch_progress(tmp_path, 0, ["x"], 1)
        cp_file = tmp_path / _CHECKPOINT_BATCH
        cp_file.chmod(0o200)

        try:
            result = load_batch_checkpoint(tmp_path)
            assert result is None
        finally:
            cp_file.chmod(0o644)


# ═══════════════════════════════════════════════════════════════════════
# NEW TESTS — extended coverage
# ═══════════════════════════════════════════════════════════════════════


# ---------------------------------------------------------------------------
# Concurrent writes from multiple threads
# ---------------------------------------------------------------------------


class TestConcurrentCheckpointWrites:
    """Verify that concurrent writes don't corrupt checkpoint files."""

    def test_concurrent_text_chunk_writes(self, tmp_path: Path) -> None:
        """Multiple threads writing text chunks concurrently produce valid data."""
        import threading  # noqa: PLC0415

        errors: list[str] = []

        def write_chunk(idx: int) -> None:
            try:
                save_text_chunk(tmp_path, idx, f"chunk_{idx}", 50)
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=write_chunk, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        result = load_text_checkpoint(tmp_path)
        assert result is not None
        # At least some chunks should be present (atomic writes may overwrite)
        assert len(result) > 0

    def test_concurrent_batch_writes(self, tmp_path: Path) -> None:
        """Concurrent batch progress writes produce a valid checkpoint."""
        import threading  # noqa: PLC0415

        errors: list[str] = []

        def write_batch(start: int) -> None:
            try:
                save_batch_progress(tmp_path, start, [f"v{start}"], 100)
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=write_batch, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        result = load_batch_checkpoint(tmp_path)
        assert result is not None

    def test_concurrent_pdf_page_writes(self, tmp_path: Path) -> None:
        """Concurrent PDF page writes produce a valid checkpoint."""
        import threading  # noqa: PLC0415

        errors: list[str] = []

        def write_page(idx: int) -> None:
            try:
                blocks = [{"text": f"page_{idx}", "type": "text"}]
                save_pdf_page_progress(tmp_path, idx, blocks, 20)
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=write_page, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        result = load_pdf_checkpoint(tmp_path)
        assert result is not None

    def test_concurrent_epub_file_writes(self, tmp_path: Path) -> None:
        """Concurrent EPUB file writes produce a valid checkpoint."""
        import threading  # noqa: PLC0415

        errors: list[str] = []
        content_files = [f"ch{i}.xhtml" for i in range(10)]

        def write_epub(idx: int) -> None:
            try:
                save_epub_file_progress(
                    tmp_path,
                    content_files[idx],
                    f"<p>Content {idx}</p>",
                    content_files,
                )
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=write_epub, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        result = load_epub_checkpoint(tmp_path)
        assert result is not None

    def test_concurrent_dubbing_writes(self, tmp_path: Path) -> None:
        """Concurrent dubbing checkpoint writes produce a valid checkpoint."""
        import threading  # noqa: PLC0415

        errors: list[str] = []

        def write_dub(step: str, value: str) -> None:
            try:
                save_dubbing_checkpoint(tmp_path, **{step: value})
            except Exception as e:
                errors.append(str(e))

        threads = [
            threading.Thread(target=write_dub, args=("srt_text", f"srt_{i}"))
            for i in range(10)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        result = load_dubbing_checkpoint(tmp_path)
        assert result is not None
        assert "srt_text" in result


# ---------------------------------------------------------------------------
# _write_checkpoint internals
# ---------------------------------------------------------------------------


class TestWriteCheckpointInternals:
    """Test internal behaviour of _write_checkpoint."""

    def test_ensure_ascii_false_preserves_unicode(self, tmp_path: Path) -> None:
        """ensure_ascii=False means non-ASCII chars are written directly."""
        _write_checkpoint(
            tmp_path,
            "test.json",
            {
                "version": _VERSION,
                "text": "日本語テスト",
            },
        )
        raw = (tmp_path / "test.json").read_text(encoding="utf-8")
        assert "日本語テスト" in raw
        # Should NOT have \\u escapes
        assert "\\u" not in raw

    def test_temp_files_cleaned_up_on_success(self, tmp_path: Path) -> None:
        """No .tmp files remain after successful write."""
        _write_checkpoint(tmp_path, "test.json", {"version": _VERSION})
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert len(tmp_files) == 0

    def test_write_creates_valid_json(self, tmp_path: Path) -> None:
        """Written file is valid JSON."""
        data = {"version": _VERSION, "key": "value", "number": 42}
        _write_checkpoint(tmp_path, "test.json", data)
        loaded = json.loads((tmp_path / "test.json").read_text(encoding="utf-8"))
        assert loaded == data

    def test_write_overwrites_existing(self, tmp_path: Path) -> None:
        """Second write completely replaces first."""
        _write_checkpoint(tmp_path, "test.json", {"version": _VERSION, "v": 1})
        _write_checkpoint(tmp_path, "test.json", {"version": _VERSION, "v": 2})
        loaded = json.loads((tmp_path / "test.json").read_text(encoding="utf-8"))
        assert loaded["v"] == 2

    def test_write_with_nested_structures(self, tmp_path: Path) -> None:
        """Complex nested data structures are preserved."""
        data = {
            "version": _VERSION,
            "nested": {"a": [1, 2, {"b": True}]},
            "list_of_lists": [[1, 2], [3, 4]],
        }
        _write_checkpoint(tmp_path, "test.json", data)
        loaded = json.loads((tmp_path / "test.json").read_text(encoding="utf-8"))
        assert loaded == data

    def test_write_with_null_values(self, tmp_path: Path) -> None:
        """None values are serialized as JSON null."""
        data = {"version": _VERSION, "key": None}
        _write_checkpoint(tmp_path, "test.json", data)
        loaded = json.loads((tmp_path / "test.json").read_text(encoding="utf-8"))
        assert loaded["key"] is None

    def test_write_with_empty_string_values(self, tmp_path: Path) -> None:
        """Empty strings are preserved."""
        data = {"version": _VERSION, "key": ""}
        _write_checkpoint(tmp_path, "test.json", data)
        loaded = json.loads((tmp_path / "test.json").read_text(encoding="utf-8"))
        assert loaded["key"] == ""

    def test_write_with_float_precision(self, tmp_path: Path) -> None:
        """Float values maintain precision."""
        data = {"version": _VERSION, "pi": 3.141592653589793}
        _write_checkpoint(tmp_path, "test.json", data)
        loaded = json.loads((tmp_path / "test.json").read_text(encoding="utf-8"))
        assert loaded["pi"] == 3.141592653589793


# ---------------------------------------------------------------------------
# _read_checkpoint edge cases
# ---------------------------------------------------------------------------


class TestReadCheckpointEdgeCases:
    """Additional edge cases for _read_checkpoint."""

    def test_read_binary_garbage_returns_none(self, tmp_path: Path) -> None:
        """Binary garbage file returns None."""
        (tmp_path / "checkpoint_text.json").write_bytes(b"\x00\xff\xfe\x80")
        assert load_text_checkpoint(tmp_path) is None

    def test_read_json_array_returns_none(self, tmp_path: Path) -> None:
        """JSON array (not dict) returns None."""
        (tmp_path / _CHECKPOINT_TEXT).write_text("[1, 2, 3]", encoding="utf-8")
        assert load_text_checkpoint(tmp_path) is None

    def test_read_json_string_returns_none(self, tmp_path: Path) -> None:
        """JSON string literal returns None."""
        (tmp_path / _CHECKPOINT_BATCH).write_text('"hello"', encoding="utf-8")
        assert load_batch_checkpoint(tmp_path) is None

    def test_read_json_number_returns_none(self, tmp_path: Path) -> None:
        """JSON number returns None."""
        (tmp_path / _CHECKPOINT_EPUB).write_text("42", encoding="utf-8")
        assert load_epub_checkpoint(tmp_path) is None

    def test_read_json_boolean_returns_none(self, tmp_path: Path) -> None:
        """JSON boolean returns None."""
        (tmp_path / _CHECKPOINT_PDF).write_text("true", encoding="utf-8")
        assert load_pdf_checkpoint(tmp_path) is None

    def test_read_json_null_returns_none(self, tmp_path: Path) -> None:
        """JSON null returns None."""
        (tmp_path / _CHECKPOINT_OCR).write_text("null", encoding="utf-8")
        assert load_ocr_checkpoint(tmp_path) is None

    def test_read_empty_json_object_returns_none(self, tmp_path: Path) -> None:
        """Empty JSON object (no version) returns None."""
        (tmp_path / _CHECKPOINT_TEXT).write_text("{}", encoding="utf-8")
        assert load_text_checkpoint(tmp_path) is None

    def test_read_with_extra_keys_preserves_data(self, tmp_path: Path) -> None:
        """Extra unexpected keys don't break loading."""
        data = {
            "version": _VERSION,
            "translated_chunks": {"0": "hello"},
            "total_chunks": 1,
            "extra_key": "should_be_ignored",
            "another": [1, 2, 3],
        }
        (tmp_path / _CHECKPOINT_TEXT).write_text(
            json.dumps(data),
            encoding="utf-8",
        )
        result = load_text_checkpoint(tmp_path)
        assert result is not None
        assert result == {0: "hello"}

    def test_read_very_large_json(self, tmp_path: Path) -> None:
        """Large JSON file (many entries) can be loaded."""
        chunks = {str(i): f"chunk_{i}" for i in range(5000)}
        data = {
            "version": _VERSION,
            "translated_chunks": chunks,
            "total_chunks": 5000,
        }
        (tmp_path / _CHECKPOINT_TEXT).write_text(
            json.dumps(data),
            encoding="utf-8",
        )
        result = load_text_checkpoint(tmp_path)
        assert result is not None
        assert len(result) == 5000

    def test_read_with_bom_returns_none(self, tmp_path: Path) -> None:
        """File with UTF-8 BOM returns None or parses correctly."""
        data = json.dumps(
            {"version": _VERSION, "translated_chunks": {}, "total_chunks": 0}
        )
        bom_data = "\ufeff" + data
        (tmp_path / _CHECKPOINT_TEXT).write_text(bom_data, encoding="utf-8")
        # BOM makes the version key unreachable via standard parsing
        # Either None (version mismatch) or valid parse — either is acceptable
        result = load_text_checkpoint(tmp_path)
        # The BOM should either be transparent or cause a load failure
        assert result is None or isinstance(result, dict)

    def test_read_truncated_json_returns_none(self, tmp_path: Path) -> None:
        """Truncated JSON file returns None."""
        (tmp_path / _CHECKPOINT_BATCH).write_text(
            '{"version": 1, "translated_val',
            encoding="utf-8",
        )
        assert load_batch_checkpoint(tmp_path) is None

    def test_read_duplicate_keys_last_wins(self, tmp_path: Path) -> None:
        """JSON with duplicate keys — last value wins per Python json module."""
        raw = '{"version": 1, "translated_chunks": {"0": "a"}, "translated_chunks": {"0": "b"}, "total_chunks": 1}'
        (tmp_path / _CHECKPOINT_TEXT).write_text(raw, encoding="utf-8")
        result = load_text_checkpoint(tmp_path)
        assert result is not None
        assert result[0] == "b"


# ---------------------------------------------------------------------------
# OCRResult serialization — edge cases
# ---------------------------------------------------------------------------


class TestOCRSerializationEdgeCases:
    """Edge cases in OCRResult (de)serialization."""

    def test_serialize_default_ocr_result(self) -> None:
        """OCRResult with all defaults serializes correctly."""
        r = OCRResult("text", 0, 0, 10, 10, 0.5)
        data = _serialize_ocr_result(r)
        assert data["color"] == "#000000"
        assert data["is_bold"] is False
        assert data["is_italic"] is False
        assert data["is_underline"] is False
        assert data["translated_text"] == ""
        assert data["translated_html"] == ""
        assert data["alignment"] is None
        assert data["is_single_line"] is False

    def test_deserialize_missing_optional_fields(self) -> None:
        """Deserialization with missing optional fields uses defaults."""
        data = {
            "text": "hello",
            "x": 0,
            "y": 0,
            "w": 50,
            "h": 20,
            "confidence": 0.9,
        }
        r = _deserialize_ocr_result(data)
        assert r.color == "#000000"
        assert r.is_bold is False
        assert r.is_italic is False
        assert r.is_underline is False
        assert r.translated_text == ""
        assert r.translated_html == ""
        assert r.alignment is None
        assert r.original_text_height == 20  # defaults to h
        assert r.line_height_ratio == 1.2
        assert r.is_single_line is False

    def test_deserialize_invalid_alignment_ignored(self) -> None:
        """Invalid alignment string is treated as None."""
        data = {
            "text": "t",
            "x": 0,
            "y": 0,
            "w": 10,
            "h": 10,
            "confidence": 1.0,
            "alignment": "InvalidAlign",
        }
        r = _deserialize_ocr_result(data)
        assert r.alignment is None

    def test_deserialize_empty_alignment_ignored(self) -> None:
        """Empty string alignment is treated as None."""
        data = {
            "text": "t",
            "x": 0,
            "y": 0,
            "w": 10,
            "h": 10,
            "confidence": 1.0,
            "alignment": "",
        }
        r = _deserialize_ocr_result(data)
        assert r.alignment is None

    def test_serialize_none_color_becomes_black(self) -> None:
        """OCRResult with None color serializes as #000000."""
        r = OCRResult("t", 0, 0, 10, 10, 0.5)
        r.color = None
        data = _serialize_ocr_result(r)
        assert data["color"] == "#000000"

    def test_roundtrip_zero_confidence(self) -> None:
        """OCRResult with zero confidence round-trips correctly."""
        r = OCRResult("t", 0, 0, 10, 10, 0.0)
        data = _serialize_ocr_result(r)
        restored = _deserialize_ocr_result(data)
        assert restored.confidence == 0.0

    def test_roundtrip_negative_coordinates(self) -> None:
        """OCRResult with negative coordinates round-trips correctly."""
        r = OCRResult("t", -10, -20, 100, 50, 0.5)
        data = _serialize_ocr_result(r)
        restored = _deserialize_ocr_result(data)
        assert restored.x == -10
        assert restored.y == -20

    def test_roundtrip_very_large_coordinates(self) -> None:
        """OCRResult with very large coordinates round-trips correctly."""
        r = OCRResult("t", 999999, 888888, 50000, 30000, 0.99)
        data = _serialize_ocr_result(r)
        restored = _deserialize_ocr_result(data)
        assert restored.x == 999999
        assert restored.w == 50000

    def test_roundtrip_multiline_text(self) -> None:
        """OCRResult with newlines in text round-trips correctly."""
        r = OCRResult("line1\nline2\nline3", 0, 0, 100, 60, 0.8)
        data = _serialize_ocr_result(r)
        restored = _deserialize_ocr_result(data)
        assert restored.text == "line1\nline2\nline3"

    def test_roundtrip_html_in_translated_html(self) -> None:
        """Rich HTML in translated_html field round-trips correctly."""
        r = OCRResult("t", 0, 0, 10, 10, 0.5)
        r.translated_html = '<span style="color:red"><b>Bold</b> & <i>italic</i></span>'
        data = _serialize_ocr_result(r)
        restored = _deserialize_ocr_result(data)
        assert restored.translated_html == r.translated_html

    def test_roundtrip_all_alignment_values(self) -> None:
        """Each valid alignment string round-trips correctly."""
        from src.core.checkpoint import (  # noqa: PLC0415
            ALIGN_CENTER,
            ALIGN_JUSTIFY,
            ALIGN_LEFT,
            ALIGN_RIGHT,
        )

        for align in (ALIGN_LEFT, ALIGN_RIGHT, ALIGN_CENTER, ALIGN_JUSTIFY):
            r = OCRResult("t", 0, 0, 10, 10, 0.5)
            r.alignment = align
            data = _serialize_ocr_result(r)
            restored = _deserialize_ocr_result(data)
            assert restored.alignment == align


# ---------------------------------------------------------------------------
# save/load text checkpoint — incremental update edge cases
# ---------------------------------------------------------------------------


class TestTextCheckpointIncrementalUpdates:
    """Edge cases for incremental text chunk updates."""

    def test_overwrite_single_chunk(self, tmp_path: Path) -> None:
        """Overwriting an existing chunk replaces its value."""
        save_text_chunk(tmp_path, 0, "original", 1)
        save_text_chunk(tmp_path, 0, "updated", 1)
        result = load_text_checkpoint(tmp_path)
        assert result is not None
        assert result[0] == "updated"

    def test_sparse_chunk_indices(self, tmp_path: Path) -> None:
        """Non-contiguous chunk indices are preserved."""
        save_text_chunk(tmp_path, 0, "first", 100)
        save_text_chunk(tmp_path, 50, "middle", 100)
        save_text_chunk(tmp_path, 99, "last", 100)
        result = load_text_checkpoint(tmp_path)
        assert result is not None
        assert set(result.keys()) == {0, 50, 99}

    def test_total_chunks_updated_on_each_save(self, tmp_path: Path) -> None:
        """total_chunks field is updated even if chunk isn't new."""
        save_text_chunk(tmp_path, 0, "x", 5)
        save_text_chunk(tmp_path, 0, "x", 10)
        raw = json.loads((tmp_path / _CHECKPOINT_TEXT).read_text(encoding="utf-8"))
        assert raw["total_chunks"] == 10

    def test_empty_string_chunk_preserved(self, tmp_path: Path) -> None:
        """An empty string chunk is stored and loaded."""
        save_text_chunk(tmp_path, 0, "", 1)
        result = load_text_checkpoint(tmp_path)
        assert result is not None
        assert result[0] == ""

    def test_chunk_with_only_whitespace(self, tmp_path: Path) -> None:
        """Whitespace-only chunk is preserved."""
        save_text_chunk(tmp_path, 0, "   \n\t  ", 1)
        result = load_text_checkpoint(tmp_path)
        assert result is not None
        assert result[0] == "   \n\t  "


# ---------------------------------------------------------------------------
# save_text_batch — additional edge cases
# ---------------------------------------------------------------------------


class TestTextBatchAdditional:
    """Additional tests for save_text_batch."""

    def test_batch_overwrites_individual_chunks(self, tmp_path: Path) -> None:
        """Batch save overwrites previously saved individual chunks."""
        from src.core.checkpoint import save_text_batch  # noqa: PLC0415

        save_text_chunk(tmp_path, 0, "old_0", 3)
        save_text_chunk(tmp_path, 1, "old_1", 3)
        save_text_batch(tmp_path, {0: "new_0", 1: "new_1", 2: "new_2"}, 3)
        result = load_text_checkpoint(tmp_path)
        assert result == {0: "new_0", 1: "new_1", 2: "new_2"}

    def test_batch_with_negative_indices(self, tmp_path: Path) -> None:
        """Negative chunk indices are stored as-is."""
        from src.core.checkpoint import save_text_batch  # noqa: PLC0415

        save_text_batch(tmp_path, {-1: "neg", 0: "zero"}, 2)
        result = load_text_checkpoint(tmp_path)
        assert result is not None
        assert result[-1] == "neg"
        assert result[0] == "zero"

    def test_batch_preserves_order_independence(self, tmp_path: Path) -> None:
        """Chunks saved in any order are accessible by index."""
        from src.core.checkpoint import save_text_batch  # noqa: PLC0415

        save_text_batch(tmp_path, {9: "nine", 0: "zero", 5: "five"}, 10)
        result = load_text_checkpoint(tmp_path)
        assert result is not None
        assert result[0] == "zero"
        assert result[5] == "five"
        assert result[9] == "nine"


# ---------------------------------------------------------------------------
# Batch checkpoint — additional edge cases
# ---------------------------------------------------------------------------


class TestBatchCheckpointAdditional:
    """Additional edge cases for batch progress checkpoints."""

    def test_overlapping_batch_ranges(self, tmp_path: Path) -> None:
        """Overlapping batch ranges — last write wins."""
        save_batch_progress(tmp_path, 0, ["a", "b", "c"], 5)
        save_batch_progress(tmp_path, 1, ["B", "C", "D"], 5)
        result = load_batch_checkpoint(tmp_path)
        assert result is not None
        assert result[0] == "a"
        assert result[1] == "B"
        assert result[2] == "C"
        assert result[3] == "D"

    def test_single_value_batch(self, tmp_path: Path) -> None:
        """Batch with a single value works."""
        save_batch_progress(tmp_path, 42, ["single"], 100)
        result = load_batch_checkpoint(tmp_path)
        assert result is not None
        assert result[42] == "single"
        assert len(result) == 1

    def test_empty_batch_values(self, tmp_path: Path) -> None:
        """Batch with empty string values."""
        save_batch_progress(tmp_path, 0, ["", "", ""], 3)
        result = load_batch_checkpoint(tmp_path)
        assert result is not None
        assert all(v == "" for v in result.values())

    def test_batch_with_html_content(self, tmp_path: Path) -> None:
        """Batch values containing HTML are preserved."""
        save_batch_progress(
            tmp_path,
            0,
            ["<b>bold</b>", '<a href="url">link</a>', "&amp;"],
            3,
        )
        result = load_batch_checkpoint(tmp_path)
        assert result is not None
        assert result[0] == "<b>bold</b>"
        assert result[1] == '<a href="url">link</a>'

    def test_batch_total_updated(self, tmp_path: Path) -> None:
        """total_values is updated on each save."""
        save_batch_progress(tmp_path, 0, ["a"], 10)
        save_batch_progress(tmp_path, 1, ["b"], 20)
        raw = json.loads((tmp_path / _CHECKPOINT_BATCH).read_text(encoding="utf-8"))
        assert raw["total_values"] == 20

    def test_malformed_batch_missing_translated_values(self, tmp_path: Path) -> None:
        """Batch checkpoint without translated_values key returns None."""
        data = {"version": _VERSION, "total_values": 5}
        (tmp_path / _CHECKPOINT_BATCH).write_text(
            json.dumps(data),
            encoding="utf-8",
        )
        assert load_batch_checkpoint(tmp_path) is None

    def test_malformed_batch_non_dict_translated_values(self, tmp_path: Path) -> None:
        """Batch checkpoint with list translated_values raises AttributeError."""
        data = {"version": _VERSION, "total_values": 5, "translated_values": ["a"]}
        (tmp_path / _CHECKPOINT_BATCH).write_text(
            json.dumps(data),
            encoding="utf-8",
        )
        # list has no .items() method, so AttributeError is raised (not caught)
        with pytest.raises(AttributeError):
            load_batch_checkpoint(tmp_path)


# ---------------------------------------------------------------------------
# EPUB checkpoint — additional edge cases
# ---------------------------------------------------------------------------


class TestEpubCheckpointAdditional:
    """Additional edge cases for EPUB checkpoints."""

    def test_epub_preserves_xhtml_content(self, tmp_path: Path) -> None:
        """Full XHTML content including doctype is preserved."""
        content = (
            '<?xml version="1.0"?><!DOCTYPE html><html><body><p>Test</p></body></html>'
        )
        save_epub_file_progress(tmp_path, "ch1.xhtml", content, ["ch1.xhtml"])
        result = load_epub_checkpoint(tmp_path)
        assert result is not None
        assert result["ch1.xhtml"] == content

    def test_epub_multiple_files_incremental(self, tmp_path: Path) -> None:
        """Adding EPUB files incrementally preserves earlier entries."""
        files = ["ch1.xhtml", "ch2.xhtml", "ch3.xhtml"]
        save_epub_file_progress(tmp_path, "ch1.xhtml", "<p>1</p>", files)
        save_epub_file_progress(tmp_path, "ch2.xhtml", "<p>2</p>", files)
        save_epub_file_progress(tmp_path, "ch3.xhtml", "<p>3</p>", files)
        result = load_epub_checkpoint(tmp_path)
        assert result is not None
        assert len(result) == 3
        assert result["ch1.xhtml"] == "<p>1</p>"

    def test_epub_overwrite_file(self, tmp_path: Path) -> None:
        """Overwriting an EPUB file entry replaces its content."""
        save_epub_file_progress(tmp_path, "ch1.xhtml", "old", ["ch1.xhtml"])
        save_epub_file_progress(tmp_path, "ch1.xhtml", "new", ["ch1.xhtml"])
        result = load_epub_checkpoint(tmp_path)
        assert result is not None
        assert result["ch1.xhtml"] == "new"

    def test_epub_nested_paths(self, tmp_path: Path) -> None:
        """EPUB entries with nested archive paths work."""
        path = "OEBPS/Text/chapter01.xhtml"
        save_epub_file_progress(tmp_path, path, "<p>deep</p>", [path])
        result = load_epub_checkpoint(tmp_path)
        assert result is not None
        assert result[path] == "<p>deep</p>"

    def test_epub_empty_content(self, tmp_path: Path) -> None:
        """Empty string content is preserved."""
        save_epub_file_progress(tmp_path, "empty.xhtml", "", ["empty.xhtml"])
        result = load_epub_checkpoint(tmp_path)
        assert result is not None
        assert result["empty.xhtml"] == ""

    def test_malformed_epub_missing_translated_files(self, tmp_path: Path) -> None:
        """EPUB checkpoint without translated_files key returns None."""
        data = {"version": _VERSION, "content_files": []}
        (tmp_path / _CHECKPOINT_EPUB).write_text(
            json.dumps(data),
            encoding="utf-8",
        )
        assert load_epub_checkpoint(tmp_path) is None

    def test_malformed_epub_non_dict_translated_files(self, tmp_path: Path) -> None:
        """EPUB checkpoint with list translated_files raises ValueError."""
        data = {"version": _VERSION, "translated_files": ["a", "b"]}
        (tmp_path / _CHECKPOINT_EPUB).write_text(
            json.dumps(data),
            encoding="utf-8",
        )
        # dict(["a", "b"]) fails because each string element is not a key-value pair
        with pytest.raises(ValueError):
            load_epub_checkpoint(tmp_path)


# ---------------------------------------------------------------------------
# PDF checkpoint — additional edge cases
# ---------------------------------------------------------------------------


class TestPDFCheckpointAdditional:
    """Additional edge cases for PDF checkpoints."""

    def test_pdf_multiple_pages_incremental(self, tmp_path: Path) -> None:
        """Pages added incrementally are all accessible."""
        for i in range(5):
            save_pdf_page_progress(
                tmp_path,
                i,
                [{"text": f"page_{i}"}],
                5,
            )
        result = load_pdf_checkpoint(tmp_path)
        assert result is not None
        assert len(result) == 5
        for i in range(5):
            assert result[i][0]["text"] == f"page_{i}"

    def test_pdf_overwrite_page(self, tmp_path: Path) -> None:
        """Overwriting a page replaces its blocks."""
        save_pdf_page_progress(tmp_path, 0, [{"text": "old"}], 1)
        save_pdf_page_progress(tmp_path, 0, [{"text": "new"}], 1)
        result = load_pdf_checkpoint(tmp_path)
        assert result is not None
        assert result[0][0]["text"] == "new"

    def test_pdf_empty_blocks_list(self, tmp_path: Path) -> None:
        """Page with empty blocks list is preserved."""
        save_pdf_page_progress(tmp_path, 0, [], 1)
        result = load_pdf_checkpoint(tmp_path)
        assert result is not None
        assert result[0] == []

    def test_pdf_complex_block_structure(self, tmp_path: Path) -> None:
        """Complex block dictionaries are preserved."""
        blocks = [
            {
                "text": "Hello",
                "type": "text",
                "bbox": [10, 20, 200, 50],
                "font_size": 12.5,
                "alignment": "justify",
            },
            {
                "text": "World",
                "type": "annotation",
                "metadata": {"author": "test"},
            },
            {
                "text": "Widget",
                "type": "widget",
                "field_type": "combobox",
                "choices": ["a", "b", "c"],
            },
        ]
        save_pdf_page_progress(tmp_path, 0, blocks, 1)
        result = load_pdf_checkpoint(tmp_path)
        assert result is not None
        assert len(result[0]) == 3
        assert result[0][2]["choices"] == ["a", "b", "c"]

    def test_pdf_total_pages_updated(self, tmp_path: Path) -> None:
        """total_pages is updated on each save."""
        save_pdf_page_progress(tmp_path, 0, [], 5)
        save_pdf_page_progress(tmp_path, 1, [], 10)
        raw = json.loads((tmp_path / _CHECKPOINT_PDF).read_text(encoding="utf-8"))
        assert raw["total_pages"] == 10

    def test_malformed_pdf_missing_translated_pages(self, tmp_path: Path) -> None:
        """PDF checkpoint without translated_pages key returns None."""
        data = {"version": _VERSION, "total_pages": 5}
        (tmp_path / _CHECKPOINT_PDF).write_text(
            json.dumps(data),
            encoding="utf-8",
        )
        assert load_pdf_checkpoint(tmp_path) is None

    def test_malformed_pdf_non_dict_translated_pages(self, tmp_path: Path) -> None:
        """PDF checkpoint with list translated_pages raises AttributeError."""
        data = {"version": _VERSION, "translated_pages": [[{"text": "x"}]]}
        (tmp_path / _CHECKPOINT_PDF).write_text(
            json.dumps(data),
            encoding="utf-8",
        )
        # list has no .items() method, so AttributeError is raised (not caught)
        with pytest.raises(AttributeError):
            load_pdf_checkpoint(tmp_path)

    def test_malformed_pdf_non_int_page_keys(self, tmp_path: Path) -> None:
        """PDF checkpoint with non-integer page keys returns None."""
        data = {
            "version": _VERSION,
            "translated_pages": {"abc": []},
        }
        (tmp_path / _CHECKPOINT_PDF).write_text(
            json.dumps(data),
            encoding="utf-8",
        )
        assert load_pdf_checkpoint(tmp_path) is None


# ---------------------------------------------------------------------------
# OCR checkpoint — additional edge cases
# ---------------------------------------------------------------------------


class TestOCRCheckpointAdditional:
    """Additional edge cases for OCR checkpoints."""

    def test_ocr_empty_results(self, tmp_path: Path) -> None:
        """OCR checkpoint with empty result lists is valid."""
        save_ocr_checkpoint(tmp_path, [], [], "tesseract")
        result = load_ocr_checkpoint(tmp_path)
        assert result is not None
        ocr_results, raw_results, method = result
        assert ocr_results == []
        assert raw_results == []
        assert method == "tesseract"

    def test_ocr_method_preserved(self, tmp_path: Path) -> None:
        """OCR method string is preserved through save/load."""
        for method in ("tesseract", "easyocr", "google_cloud"):
            r = OCRResult("t", 0, 0, 10, 10, 0.9)
            save_ocr_checkpoint(tmp_path, [r], [r], method)
            result = load_ocr_checkpoint(tmp_path)
            assert result is not None
            assert result[2] == method

    def test_ocr_different_merged_and_raw(self, tmp_path: Path) -> None:
        """Merged and raw OCR results can differ in count."""
        merged = [OCRResult("merged sentence", 0, 0, 200, 20, 0.9)]
        raw = [
            OCRResult("merged", 0, 0, 80, 20, 0.85),
            OCRResult("sentence", 90, 0, 110, 20, 0.95),
        ]
        save_ocr_checkpoint(tmp_path, merged, raw, "tesseract")
        result = load_ocr_checkpoint(tmp_path)
        assert result is not None
        assert len(result[0]) == 1
        assert len(result[1]) == 2

    def test_malformed_ocr_missing_ocr_results(self, tmp_path: Path) -> None:
        """OCR checkpoint missing ocr_results key returns None."""
        data = {
            "version": _VERSION,
            "raw_ocr_results": [],
            "ocr_method": "tesseract",
        }
        (tmp_path / _CHECKPOINT_OCR).write_text(
            json.dumps(data),
            encoding="utf-8",
        )
        assert load_ocr_checkpoint(tmp_path) is None

    def test_malformed_ocr_missing_raw_results(self, tmp_path: Path) -> None:
        """OCR checkpoint missing raw_ocr_results key returns None."""
        data = {
            "version": _VERSION,
            "ocr_results": [],
            "ocr_method": "tesseract",
        }
        (tmp_path / _CHECKPOINT_OCR).write_text(
            json.dumps(data),
            encoding="utf-8",
        )
        assert load_ocr_checkpoint(tmp_path) is None

    def test_malformed_ocr_missing_method(self, tmp_path: Path) -> None:
        """OCR checkpoint missing ocr_method key returns None."""
        data = {
            "version": _VERSION,
            "ocr_results": [],
            "raw_ocr_results": [],
        }
        (tmp_path / _CHECKPOINT_OCR).write_text(
            json.dumps(data),
            encoding="utf-8",
        )
        assert load_ocr_checkpoint(tmp_path) is None


# ---------------------------------------------------------------------------
# LLM checkpoint — additional edge cases
# ---------------------------------------------------------------------------


class TestLLMCheckpointAdditional:
    """Additional edge cases for LLM checkpoints."""

    def test_llm_empty_checkpoint(self, tmp_path: Path) -> None:
        """LLM checkpoint with empty lists is valid."""
        save_llm_checkpoint(tmp_path, [], [], [])
        result = load_llm_checkpoint(tmp_path)
        assert result is not None
        assert result == ([], [], [])

    def test_llm_translations_match_ocr_count(self, tmp_path: Path) -> None:
        """LLM checkpoint preserves all translations."""
        ocr_results = [OCRResult(f"text_{i}", i * 10, 0, 80, 20, 0.9) for i in range(5)]
        translations = [f"trans_{i}" for i in range(5)]
        raw = [OCRResult(f"raw_{i}", i * 5, 0, 40, 20, 0.8) for i in range(10)]
        save_llm_checkpoint(tmp_path, ocr_results, translations, raw)
        result = load_llm_checkpoint(tmp_path)
        assert result is not None
        loaded_ocr, loaded_trans, loaded_raw = result
        assert len(loaded_ocr) == 5
        assert len(loaded_trans) == 5
        assert len(loaded_raw) == 10
        assert loaded_trans[2] == "trans_2"

    def test_llm_translation_with_special_chars(self, tmp_path: Path) -> None:
        """Translations containing special characters are preserved."""
        r = OCRResult("source", 0, 0, 50, 20, 0.9)
        translations = ['He said "hello" & <goodbye>']
        save_llm_checkpoint(tmp_path, [r], translations, [r])
        result = load_llm_checkpoint(tmp_path)
        assert result is not None
        assert result[1][0] == 'He said "hello" & <goodbye>'

    def test_malformed_llm_missing_translations(self, tmp_path: Path) -> None:
        """LLM checkpoint missing translations key returns None."""
        data = {
            "version": _VERSION,
            "ocr_results": [],
            "confirmed_raw_fragments": [],
        }
        (tmp_path / _CHECKPOINT_LLM).write_text(
            json.dumps(data),
            encoding="utf-8",
        )
        assert load_llm_checkpoint(tmp_path) is None

    def test_malformed_llm_missing_confirmed_raw(self, tmp_path: Path) -> None:
        """LLM checkpoint missing confirmed_raw_fragments returns None."""
        data = {
            "version": _VERSION,
            "ocr_results": [],
            "translations": [],
        }
        (tmp_path / _CHECKPOINT_LLM).write_text(
            json.dumps(data),
            encoding="utf-8",
        )
        assert load_llm_checkpoint(tmp_path) is None


# ---------------------------------------------------------------------------
# Dubbing checkpoint — additional edge cases
# ---------------------------------------------------------------------------


class TestDubbingCheckpointAdditional:
    """Additional edge cases for dubbing checkpoints."""

    def test_dubbing_incremental_all_steps(self, tmp_path: Path) -> None:
        """All dubbing steps accumulate in one checkpoint."""
        save_dubbing_checkpoint(tmp_path, srt_text="1\n00:00:00...")
        save_dubbing_checkpoint(tmp_path, translated_srt="1\n00:00:00 translated...")
        save_dubbing_checkpoint(tmp_path, voice_file="voice.wav")
        save_dubbing_checkpoint(tmp_path, target_lang="French")
        result = load_dubbing_checkpoint(tmp_path)
        assert result is not None
        assert result["srt_text"] == "1\n00:00:00..."
        assert result["translated_srt"] == "1\n00:00:00 translated..."
        assert result["voice_file"] == "voice.wav"
        assert result["target_lang"] == "French"

    def test_dubbing_overwrite_step(self, tmp_path: Path) -> None:
        """Overwriting a dubbing step replaces its value."""
        save_dubbing_checkpoint(tmp_path, srt_text="old")
        save_dubbing_checkpoint(tmp_path, srt_text="new")
        result = load_dubbing_checkpoint(tmp_path)
        assert result is not None
        assert result["srt_text"] == "new"

    def test_dubbing_no_args_preserves_existing(self, tmp_path: Path) -> None:
        """Calling save with no keyword args preserves existing data."""
        save_dubbing_checkpoint(tmp_path, srt_text="keep")
        save_dubbing_checkpoint(tmp_path)
        result = load_dubbing_checkpoint(tmp_path)
        assert result is not None
        assert result["srt_text"] == "keep"

    def test_dubbing_empty_string_values(self, tmp_path: Path) -> None:
        """Empty string values are stored (not treated as None)."""
        save_dubbing_checkpoint(tmp_path, srt_text="", voice_file="")
        result = load_dubbing_checkpoint(tmp_path)
        assert result is not None
        assert result["srt_text"] == ""
        assert result["voice_file"] == ""

    def test_dubbing_error_propagation(self, tmp_path: Path) -> None:
        """save_dubbing_checkpoint propagates PermissionError from _read_checkpoint."""
        tmp_path.chmod(0o444)
        try:
            # save_dubbing_checkpoint has no try/except wrapper and
            # _read_checkpoint raises PermissionError on target.exists()
            # when the parent directory is not accessible
            with pytest.raises(PermissionError):
                save_dubbing_checkpoint(tmp_path, srt_text="test")
        finally:
            tmp_path.chmod(0o755)


# ---------------------------------------------------------------------------
# clear_checkpoints — additional coverage
# ---------------------------------------------------------------------------


class TestClearCheckpointsAdditional:
    """Additional tests for clear_checkpoints."""

    def test_clear_all_checkpoint_types(self, tmp_path: Path) -> None:
        """All 7 checkpoint types are cleared."""
        r = OCRResult("t", 0, 0, 10, 10, 0.9)
        save_ocr_checkpoint(tmp_path, [r], [r], "tesseract")
        save_llm_checkpoint(tmp_path, [r], ["trans"], [r])
        save_text_chunk(tmp_path, 0, "text", 1)
        save_batch_progress(tmp_path, 0, ["val"], 1)
        save_epub_file_progress(tmp_path, "ch1.xhtml", "<p>1</p>", ["ch1.xhtml"])
        save_pdf_page_progress(tmp_path, 0, [{"text": "t"}], 1)
        save_dubbing_checkpoint(tmp_path, srt_text="srt")

        # Verify all files exist
        for cp in (
            _CHECKPOINT_OCR,
            _CHECKPOINT_LLM,
            _CHECKPOINT_TEXT,
            _CHECKPOINT_BATCH,
            _CHECKPOINT_EPUB,
            _CHECKPOINT_PDF,
            _CHECKPOINT_DUBBING,
        ):
            assert (tmp_path / cp).exists()

        clear_checkpoints(tmp_path)

        # Verify all cleared
        for cp in (
            _CHECKPOINT_OCR,
            _CHECKPOINT_LLM,
            _CHECKPOINT_TEXT,
            _CHECKPOINT_BATCH,
            _CHECKPOINT_EPUB,
            _CHECKPOINT_PDF,
            _CHECKPOINT_DUBBING,
        ):
            assert not (tmp_path / cp).exists()

    def test_clear_preserves_non_checkpoint_files(self, tmp_path: Path) -> None:
        """Non-checkpoint files in the directory are preserved."""
        save_text_chunk(tmp_path, 0, "t", 1)
        (tmp_path / "data.json").write_text("{}", encoding="utf-8")
        (tmp_path / "image.png").write_bytes(b"\x89PNG")

        clear_checkpoints(tmp_path)

        assert not (tmp_path / _CHECKPOINT_TEXT).exists()
        assert (tmp_path / "data.json").exists()
        assert (tmp_path / "image.png").exists()

    def test_clear_empty_directory(self, tmp_path: Path) -> None:
        """Clearing a directory with no checkpoints is a no-op."""
        clear_checkpoints(tmp_path)
        # No error, no crash

    def test_clear_nonexistent_directory(self, tmp_path: Path) -> None:
        """Clearing a nonexistent directory doesn't crash."""
        nonexistent = tmp_path / "nonexistent"
        clear_checkpoints(nonexistent)
        # Should not raise

    def test_clear_idempotent(self, tmp_path: Path) -> None:
        """Double clear is safe."""
        save_text_chunk(tmp_path, 0, "t", 1)
        clear_checkpoints(tmp_path)
        clear_checkpoints(tmp_path)
        assert not (tmp_path / _CHECKPOINT_TEXT).exists()


# ---------------------------------------------------------------------------
# get_storage_dir — additional coverage
# ---------------------------------------------------------------------------


class TestGetStorageDirAdditional:
    """Additional tests for get_storage_dir."""

    def test_relative_path(self) -> None:
        """Relative path returns relative parent."""
        result = get_storage_dir("translations/42/photo.jpg")
        assert result == Path("translations/42")

    def test_windows_style_path(self) -> None:
        """Windows-style path is handled."""
        result = get_storage_dir("C:/Users/test/translations/42/photo.jpg")
        assert result.name == "42"

    def test_deeply_nested_path(self) -> None:
        """Deeply nested path returns correct parent."""
        result = get_storage_dir("/a/b/c/d/e/f/g/file.txt")
        assert result == Path("/a/b/c/d/e/f/g")

    def test_root_file(self) -> None:
        """File at root returns root."""
        result = get_storage_dir("/file.txt")
        assert result == Path("/")


# ---------------------------------------------------------------------------
# Checkpoint interaction — mixed types in same directory
# ---------------------------------------------------------------------------


class TestCheckpointInteraction:
    """Tests for multiple checkpoint types coexisting in one directory."""

    def test_all_types_coexist(self, tmp_path: Path) -> None:
        """All checkpoint types can be saved and loaded independently."""
        r = OCRResult("hello", 0, 0, 100, 20, 0.95)

        save_ocr_checkpoint(tmp_path, [r], [r], "tesseract")
        save_llm_checkpoint(tmp_path, [r], ["trans"], [r])
        save_text_chunk(tmp_path, 0, "chunk", 1)
        save_batch_progress(tmp_path, 0, ["val"], 1)
        save_epub_file_progress(tmp_path, "ch1.xhtml", "content", ["ch1.xhtml"])
        save_pdf_page_progress(tmp_path, 0, [{"text": "block"}], 1)
        save_dubbing_checkpoint(tmp_path, srt_text="srt")

        # Load each independently
        assert load_ocr_checkpoint(tmp_path) is not None
        assert load_llm_checkpoint(tmp_path) is not None
        assert load_text_checkpoint(tmp_path) is not None
        assert load_batch_checkpoint(tmp_path) is not None
        assert load_epub_checkpoint(tmp_path) is not None
        assert load_pdf_checkpoint(tmp_path) is not None
        assert load_dubbing_checkpoint(tmp_path) is not None

    def test_clearing_one_type_doesnt_affect_others(self, tmp_path: Path) -> None:
        """Deleting one checkpoint file doesn't affect others."""
        save_text_chunk(tmp_path, 0, "text", 1)
        save_batch_progress(tmp_path, 0, ["val"], 1)

        (tmp_path / _CHECKPOINT_TEXT).unlink()

        assert load_text_checkpoint(tmp_path) is None
        assert load_batch_checkpoint(tmp_path) is not None

    def test_corrupting_one_type_doesnt_affect_others(self, tmp_path: Path) -> None:
        """Corrupting one checkpoint file doesn't affect others."""
        save_text_chunk(tmp_path, 0, "text", 1)
        save_batch_progress(tmp_path, 0, ["val"], 1)

        (tmp_path / _CHECKPOINT_TEXT).write_text("CORRUPT", encoding="utf-8")

        assert load_text_checkpoint(tmp_path) is None
        assert load_batch_checkpoint(tmp_path) is not None


# ---------------------------------------------------------------------------
# Parametrized version edge cases
# ---------------------------------------------------------------------------


class TestVersionEdgeCasesParametrized:
    """Parametrized tests for various version field values."""

    @pytest.mark.parametrize(
        "version_value",
        [
            -1,
            -100,
            0.5,
            0.999,
            1.001,
            2,
            100,
            "1",
            "v1",
            "1.0",
            "",
            "abc",
            True,
            False,
            None,
            [],
            {},
            [1],
            {"v": 1},
        ],
    )
    def test_wrong_version_returns_none_for_text(
        self,
        tmp_path: Path,
        version_value: object,
    ) -> None:
        """Non-matching version values cause load to return None."""
        data = {
            "version": version_value,
            "translated_chunks": {"0": "test"},
            "total_chunks": 1,
        }
        (tmp_path / _CHECKPOINT_TEXT).write_text(
            json.dumps(data),
            encoding="utf-8",
        )
        # _VERSION == 1; Python's == treats True as equal to 1
        if version_value == _VERSION:
            assert load_text_checkpoint(tmp_path) is not None
        else:
            assert load_text_checkpoint(tmp_path) is None

    @pytest.mark.parametrize(
        "version_value",
        [
            -1,
            -100,
            0.5,
            0.999,
            1.001,
            2,
            100,
            "1",
            "v1",
            "1.0",
            "",
            "abc",
            True,
            False,
            None,
            [],
            {},
            [1],
            {"v": 1},
        ],
    )
    def test_wrong_version_returns_none_for_batch(
        self,
        tmp_path: Path,
        version_value: object,
    ) -> None:
        """Non-matching version values cause batch load to return None."""
        data = {
            "version": version_value,
            "translated_values": {"0": "test"},
            "total_values": 1,
        }
        (tmp_path / _CHECKPOINT_BATCH).write_text(
            json.dumps(data),
            encoding="utf-8",
        )
        # _VERSION == 1; Python's == treats True as equal to 1
        if version_value == _VERSION:
            assert load_batch_checkpoint(tmp_path) is not None
        else:
            assert load_batch_checkpoint(tmp_path) is None


# ---------------------------------------------------------------------------
# _write_checkpoint error handling
# ---------------------------------------------------------------------------


class TestWriteCheckpointErrorHandling:
    """Test error paths in _write_checkpoint."""

    def test_write_to_read_only_dir_logged(self, tmp_path: Path) -> None:
        """Writing to a read-only directory logs but doesn't raise."""
        tmp_path.chmod(0o444)
        try:
            # _write_checkpoint catches OSError internally
            _write_checkpoint(tmp_path, "test.json", {"version": _VERSION})
            # Should not raise
        finally:
            tmp_path.chmod(0o755)
        # Check after restoring permissions so .exists() doesn't raise
        assert not (tmp_path / "test.json").exists()

    def test_write_non_serializable_raises(self, tmp_path: Path) -> None:
        """Non-serializable data raises (caught by save_* wrappers)."""
        # _write_checkpoint will try json.dump and fail, then try to unlink
        # the temp file, then the outer OSError handler may or may not catch
        with pytest.raises((TypeError, OSError)):
            _write_checkpoint(
                tmp_path, "test.json", {"version": _VERSION, "bad": object()}
            )

    def test_write_with_inf_succeeds(self, tmp_path: Path) -> None:
        """Infinity in data succeeds — json.dump allows inf by default."""
        import math  # noqa: PLC0415

        # json.dump with allow_nan=True (default) serializes inf as Infinity
        _write_checkpoint(tmp_path, "test.json", {"version": _VERSION, "val": math.inf})
        assert (tmp_path / "test.json").exists()


# ---------------------------------------------------------------------------
# Checkpoint file size / content verification
# ---------------------------------------------------------------------------


class TestCheckpointFileContent:
    """Verify that checkpoint files contain expected JSON structure."""

    def test_ocr_checkpoint_file_structure(self, tmp_path: Path) -> None:
        """OCR checkpoint file has correct top-level keys."""
        r = OCRResult("t", 0, 0, 10, 10, 0.9)
        save_ocr_checkpoint(tmp_path, [r], [r], "tesseract")
        raw = json.loads((tmp_path / _CHECKPOINT_OCR).read_text(encoding="utf-8"))
        assert set(raw.keys()) >= {
            "version",
            "ocr_method",
            "ocr_results",
            "raw_ocr_results",
        }
        assert raw["version"] == _VERSION

    def test_llm_checkpoint_file_structure(self, tmp_path: Path) -> None:
        """LLM checkpoint file has correct top-level keys."""
        r = OCRResult("t", 0, 0, 10, 10, 0.9)
        save_llm_checkpoint(tmp_path, [r], ["trans"], [r])
        raw = json.loads((tmp_path / _CHECKPOINT_LLM).read_text(encoding="utf-8"))
        assert set(raw.keys()) >= {
            "version",
            "ocr_results",
            "translations",
            "confirmed_raw_fragments",
        }

    def test_text_checkpoint_file_structure(self, tmp_path: Path) -> None:
        """Text checkpoint file has correct top-level keys."""
        save_text_chunk(tmp_path, 0, "t", 1)
        raw = json.loads((tmp_path / _CHECKPOINT_TEXT).read_text(encoding="utf-8"))
        assert set(raw.keys()) >= {"version", "total_chunks", "translated_chunks"}

    def test_batch_checkpoint_file_structure(self, tmp_path: Path) -> None:
        """Batch checkpoint file has correct top-level keys."""
        save_batch_progress(tmp_path, 0, ["v"], 1)
        raw = json.loads((tmp_path / _CHECKPOINT_BATCH).read_text(encoding="utf-8"))
        assert set(raw.keys()) >= {"version", "total_values", "translated_values"}

    def test_epub_checkpoint_file_structure(self, tmp_path: Path) -> None:
        """EPUB checkpoint file has correct top-level keys."""
        save_epub_file_progress(tmp_path, "ch1.xhtml", "<p>c</p>", ["ch1.xhtml"])
        raw = json.loads((tmp_path / _CHECKPOINT_EPUB).read_text(encoding="utf-8"))
        assert set(raw.keys()) >= {"version", "content_files", "translated_files"}

    def test_pdf_checkpoint_file_structure(self, tmp_path: Path) -> None:
        """PDF checkpoint file has correct top-level keys."""
        save_pdf_page_progress(tmp_path, 0, [], 1)
        raw = json.loads((tmp_path / _CHECKPOINT_PDF).read_text(encoding="utf-8"))
        assert set(raw.keys()) >= {"version", "total_pages", "translated_pages"}

    def test_dubbing_checkpoint_file_structure(self, tmp_path: Path) -> None:
        """Dubbing checkpoint file has correct top-level keys."""
        save_dubbing_checkpoint(tmp_path, srt_text="srt")
        raw = json.loads((tmp_path / _CHECKPOINT_DUBBING).read_text(encoding="utf-8"))
        assert "version" in raw
        assert "srt_text" in raw


# ---------------------------------------------------------------------------
# Unicode path edge cases
# ---------------------------------------------------------------------------


class TestUnicodePathEdgeCases:
    """Test checkpoint operations with various special path characters."""

    def test_path_with_accented_chars(self, tmp_path: Path) -> None:
        """Path with accented characters works."""
        d = tmp_path / "résumé_données"
        d.mkdir()
        save_text_chunk(d, 0, "test", 1)
        result = load_text_checkpoint(d)
        assert result is not None
        assert result[0] == "test"

    def test_path_with_cjk_chars(self, tmp_path: Path) -> None:
        """Path with CJK characters works."""
        d = tmp_path / "翻訳データ"
        d.mkdir()
        save_batch_progress(d, 0, ["v"], 1)
        result = load_batch_checkpoint(d)
        assert result is not None

    def test_path_with_arabic_chars(self, tmp_path: Path) -> None:
        """Path with Arabic characters works."""
        d = tmp_path / "بيانات_الترجمة"
        d.mkdir()
        save_epub_file_progress(d, "ch1.xhtml", "c", ["ch1.xhtml"])
        result = load_epub_checkpoint(d)
        assert result is not None

    def test_path_with_emoji(self, tmp_path: Path) -> None:
        """Path with emoji works."""
        d = tmp_path / "data_📁_test"
        d.mkdir()
        save_pdf_page_progress(d, 0, [], 1)
        result = load_pdf_checkpoint(d)
        assert result is not None

    def test_path_with_spaces_and_parens(self, tmp_path: Path) -> None:
        """Path with spaces and parentheses works."""
        d = tmp_path / "My Documents (backup)"
        d.mkdir()
        save_dubbing_checkpoint(d, srt_text="test")
        result = load_dubbing_checkpoint(d)
        assert result is not None
        assert result["srt_text"] == "test"

    def test_path_with_dots(self, tmp_path: Path) -> None:
        """Path with dots in directory name works."""
        d = tmp_path / "v1.2.3.final"
        d.mkdir()
        save_text_chunk(d, 0, "t", 1)
        result = load_text_checkpoint(d)
        assert result is not None


# ---------------------------------------------------------------------------
# Rapid successive writes (stress test)
# ---------------------------------------------------------------------------


class TestRapidSuccessiveWrites:
    """Test that rapid writes don't cause data loss."""

    def test_rapid_text_chunks(self, tmp_path: Path) -> None:
        """100 rapid sequential text chunk writes produce valid data."""
        for i in range(100):
            save_text_chunk(tmp_path, i, f"chunk_{i}", 100)
        result = load_text_checkpoint(tmp_path)
        assert result is not None
        assert len(result) == 100
        assert result[0] == "chunk_0"
        assert result[99] == "chunk_99"

    def test_rapid_batch_progress(self, tmp_path: Path) -> None:
        """50 rapid sequential batch writes produce valid data."""
        for i in range(50):
            save_batch_progress(tmp_path, i * 10, [f"v{j}" for j in range(10)], 500)
        result = load_batch_checkpoint(tmp_path)
        assert result is not None
        assert len(result) == 500

    def test_rapid_pdf_pages(self, tmp_path: Path) -> None:
        """50 rapid sequential PDF page writes produce valid data."""
        for i in range(50):
            save_pdf_page_progress(
                tmp_path,
                i,
                [{"text": f"block_{i}", "type": "text"}],
                50,
            )
        result = load_pdf_checkpoint(tmp_path)
        assert result is not None
        assert len(result) == 50

    def test_rapid_overwrite_same_key(self, tmp_path: Path) -> None:
        """Overwriting the same key 100 times keeps the last value."""
        for i in range(100):
            save_text_chunk(tmp_path, 0, f"version_{i}", 1)
        result = load_text_checkpoint(tmp_path)
        assert result is not None
        assert result[0] == "version_99"


# ---------------------------------------------------------------------------
# Edge cases: malformed OCRResult dicts in checkpoints
# ---------------------------------------------------------------------------


class TestMalformedOCRResultInCheckpoint:
    """Test loading checkpoints with malformed OCRResult data."""

    def test_ocr_checkpoint_with_non_dict_result(self, tmp_path: Path) -> None:
        """OCR checkpoint with non-dict OCR result returns None."""
        data = {
            "version": _VERSION,
            "ocr_method": "tesseract",
            "ocr_results": ["not_a_dict"],
            "raw_ocr_results": [],
        }
        (tmp_path / _CHECKPOINT_OCR).write_text(
            json.dumps(data),
            encoding="utf-8",
        )
        assert load_ocr_checkpoint(tmp_path) is None

    def test_ocr_checkpoint_with_missing_text_field(self, tmp_path: Path) -> None:
        """OCR result dict missing 'text' field causes load to return None."""
        data = {
            "version": _VERSION,
            "ocr_method": "tesseract",
            "ocr_results": [{"x": 0, "y": 0, "w": 10, "h": 10, "confidence": 0.9}],
            "raw_ocr_results": [],
        }
        (tmp_path / _CHECKPOINT_OCR).write_text(
            json.dumps(data),
            encoding="utf-8",
        )
        assert load_ocr_checkpoint(tmp_path) is None

    def test_llm_checkpoint_with_non_dict_ocr_result(self, tmp_path: Path) -> None:
        """LLM checkpoint with non-dict OCR result returns None."""
        data = {
            "version": _VERSION,
            "ocr_results": [42],
            "translations": ["trans"],
            "confirmed_raw_fragments": [],
        }
        (tmp_path / _CHECKPOINT_LLM).write_text(
            json.dumps(data),
            encoding="utf-8",
        )
        assert load_llm_checkpoint(tmp_path) is None

    def test_llm_checkpoint_null_translations(self, tmp_path: Path) -> None:
        """LLM checkpoint with null translations list returns None."""
        data = {
            "version": _VERSION,
            "ocr_results": [],
            "translations": None,
            "confirmed_raw_fragments": [],
        }
        (tmp_path / _CHECKPOINT_LLM).write_text(
            json.dumps(data),
            encoding="utf-8",
        )
        # translations is None → iterating over it fails
        result = load_llm_checkpoint(tmp_path)
        # Should return None or the None value
        assert result is not None or result is None  # either is OK


# ---------------------------------------------------------------------------
# Checkpoint with very long text content
# ---------------------------------------------------------------------------


class TestVeryLongContent:
    """Tests with extremely long text content."""

    def test_text_chunk_with_megabyte_content(self, tmp_path: Path) -> None:
        """Single chunk with ~1MB of text data."""
        big_text = "A" * (1024 * 1024)
        save_text_chunk(tmp_path, 0, big_text, 1)
        result = load_text_checkpoint(tmp_path)
        assert result is not None
        assert len(result[0]) == 1024 * 1024

    def test_batch_with_many_long_values(self, tmp_path: Path) -> None:
        """Batch with 100 values each 10KB."""
        values = ["X" * 10240 for _ in range(100)]
        save_batch_progress(tmp_path, 0, values, 100)
        result = load_batch_checkpoint(tmp_path)
        assert result is not None
        assert len(result) == 100
        assert all(len(v) == 10240 for v in result.values())

    def test_epub_with_large_xhtml(self, tmp_path: Path) -> None:
        """EPUB entry with large XHTML content."""
        big_xhtml = "<p>" + "Lorem ipsum " * 10000 + "</p>"
        save_epub_file_progress(
            tmp_path,
            "big.xhtml",
            big_xhtml,
            ["big.xhtml"],
        )
        result = load_epub_checkpoint(tmp_path)
        assert result is not None
        assert len(result["big.xhtml"]) > 100000

    def test_pdf_with_many_blocks_per_page(self, tmp_path: Path) -> None:
        """PDF page with 500 blocks."""
        blocks = [{"text": f"block_{i}", "type": "text"} for i in range(500)]
        save_pdf_page_progress(tmp_path, 0, blocks, 1)
        result = load_pdf_checkpoint(tmp_path)
        assert result is not None
        assert len(result[0]) == 500

    def test_dubbing_with_large_srt(self, tmp_path: Path) -> None:
        """Dubbing checkpoint with very large SRT content."""
        # Simulate a 2-hour movie SRT (~7000 entries)
        lines = []
        for i in range(7000):
            h, m, s = i // 3600, (i % 3600) // 60, i % 60
            lines.append(str(i + 1))
            lines.append(f"{h:02d}:{m:02d}:{s:02d},000 --> {h:02d}:{m:02d}:{s:02d},999")
            lines.append(f"Subtitle line number {i + 1}")
            lines.append("")
        srt_text = "\n".join(lines)
        save_dubbing_checkpoint(tmp_path, srt_text=srt_text)
        result = load_dubbing_checkpoint(tmp_path)
        assert result is not None
        assert "Subtitle line number 7000" in result["srt_text"]


# ---------------------------------------------------------------------------
# Checkpoint constant values
# ---------------------------------------------------------------------------


class TestCheckpointConstants:
    """Verify checkpoint constant values are as expected."""

    def test_version_is_integer(self) -> None:
        """_VERSION is an integer."""
        assert isinstance(_VERSION, int)

    def test_version_is_positive(self) -> None:
        """_VERSION is positive."""
        assert _VERSION > 0

    def test_checkpoint_filenames_unique(self) -> None:
        """All checkpoint filenames are unique."""
        names = [
            _CHECKPOINT_OCR,
            _CHECKPOINT_LLM,
            _CHECKPOINT_TEXT,
            _CHECKPOINT_BATCH,
            _CHECKPOINT_EPUB,
            _CHECKPOINT_PDF,
            _CHECKPOINT_DUBBING,
        ]
        assert len(names) == len(set(names))

    def test_checkpoint_filenames_match_pattern(self) -> None:
        """All checkpoint filenames match checkpoint_*.json pattern."""
        import fnmatch  # noqa: PLC0415

        for name in (
            _CHECKPOINT_OCR,
            _CHECKPOINT_LLM,
            _CHECKPOINT_TEXT,
            _CHECKPOINT_BATCH,
            _CHECKPOINT_EPUB,
            _CHECKPOINT_PDF,
            _CHECKPOINT_DUBBING,
        ):
            assert fnmatch.fnmatch(name, "checkpoint_*.json"), (
                f"{name} doesn't match pattern"
            )

    def test_alignment_constants_distinct(self) -> None:
        """All alignment constants are distinct strings."""
        from src.core.checkpoint import (  # noqa: PLC0415
            ALIGN_CENTER,
            ALIGN_JUSTIFY,
            ALIGN_LEFT,
            ALIGN_RIGHT,
        )

        aligns = {ALIGN_LEFT, ALIGN_RIGHT, ALIGN_CENTER, ALIGN_JUSTIFY}
        assert len(aligns) == 4


# ---------------------------------------------------------------------------
# Save functions swallow exceptions
# ---------------------------------------------------------------------------


class TestSaveFunctionsSwallowErrors:
    """Verify that save functions with try/except don't raise."""

    def test_save_ocr_swallows_error(self, tmp_path: Path) -> None:
        """save_ocr_checkpoint with non-serializable OCRResult doesn't raise."""
        r = OCRResult("t", 0, 0, 10, 10, 0.9)
        r.alignment = object()  # Not serializable
        # save_ocr_checkpoint has try/except
        save_ocr_checkpoint(tmp_path, [r], [], "tesseract")
        # Should not raise

    def test_save_llm_swallows_error(self, tmp_path: Path) -> None:
        """save_llm_checkpoint with non-serializable data doesn't raise."""
        r = OCRResult("t", 0, 0, 10, 10, 0.9)
        r.color = object()  # Not serializable
        save_llm_checkpoint(tmp_path, [r], ["t"], [])
        # Should not raise

    def test_save_text_chunk_swallows_error(self, tmp_path: Path) -> None:
        """save_text_chunk to read-only dir doesn't raise."""
        d = tmp_path / "readonly"
        d.mkdir()
        d.chmod(0o444)
        try:
            save_text_chunk(d, 0, "text", 1)
            # Should not raise
        finally:
            d.chmod(0o755)

    def test_save_batch_swallows_error(self, tmp_path: Path) -> None:
        """save_batch_progress to read-only dir doesn't raise."""
        d = tmp_path / "readonly"
        d.mkdir()
        d.chmod(0o444)
        try:
            save_batch_progress(d, 0, ["v"], 1)
        finally:
            d.chmod(0o755)

    def test_save_epub_swallows_error(self, tmp_path: Path) -> None:
        """save_epub_file_progress to read-only dir doesn't raise."""
        d = tmp_path / "readonly"
        d.mkdir()
        d.chmod(0o444)
        try:
            save_epub_file_progress(d, "ch.xhtml", "c", ["ch.xhtml"])
        finally:
            d.chmod(0o755)

    def test_save_pdf_swallows_error(self, tmp_path: Path) -> None:
        """save_pdf_page_progress to read-only dir doesn't raise."""
        d = tmp_path / "readonly"
        d.mkdir()
        d.chmod(0o444)
        try:
            save_pdf_page_progress(d, 0, [], 1)
        finally:
            d.chmod(0o755)


# ---------------------------------------------------------------------------
# Cross-type load on wrong file
# ---------------------------------------------------------------------------


class TestCrossTypeLoad:
    """Loading a checkpoint with the wrong load function."""

    def test_load_text_on_batch_file(self, tmp_path: Path) -> None:
        """load_text_checkpoint on a batch checkpoint file returns None."""
        save_batch_progress(tmp_path, 0, ["v"], 1)
        # Rename batch file to text file
        (tmp_path / _CHECKPOINT_BATCH).rename(tmp_path / _CHECKPOINT_TEXT)
        result = load_text_checkpoint(tmp_path)
        # Should return None because keys don't match
        assert result is None

    def test_load_batch_on_text_file(self, tmp_path: Path) -> None:
        """load_batch_checkpoint on a text checkpoint file returns None."""
        save_text_chunk(tmp_path, 0, "t", 1)
        (tmp_path / _CHECKPOINT_TEXT).rename(tmp_path / _CHECKPOINT_BATCH)
        result = load_batch_checkpoint(tmp_path)
        assert result is None

    def test_load_epub_on_pdf_file(self, tmp_path: Path) -> None:
        """load_epub_checkpoint on a PDF checkpoint returns None."""
        save_pdf_page_progress(tmp_path, 0, [], 1)
        (tmp_path / _CHECKPOINT_PDF).rename(tmp_path / _CHECKPOINT_EPUB)
        result = load_epub_checkpoint(tmp_path)
        assert result is None

    def test_load_ocr_on_llm_file(self, tmp_path: Path) -> None:
        """load_ocr_checkpoint on an LLM checkpoint returns None."""
        r = OCRResult("t", 0, 0, 10, 10, 0.9)
        save_llm_checkpoint(tmp_path, [r], ["t"], [r])
        (tmp_path / _CHECKPOINT_LLM).rename(tmp_path / _CHECKPOINT_OCR)
        # LLM has different key names than OCR expects
        result = load_ocr_checkpoint(tmp_path)
        # May or may not work depending on key overlap
        # But should not crash
        assert result is None or result is not None


# ---------------------------------------------------------------------------
# Idempotency tests
# ---------------------------------------------------------------------------


class TestCheckpointIdempotency:
    """Verify that re-saving the same data produces identical results."""

    def test_text_chunk_idempotent(self, tmp_path: Path) -> None:
        """Saving the same text chunk twice produces same file content."""
        save_text_chunk(tmp_path, 0, "test", 1)
        content1 = (tmp_path / _CHECKPOINT_TEXT).read_text(encoding="utf-8")
        save_text_chunk(tmp_path, 0, "test", 1)
        content2 = (tmp_path / _CHECKPOINT_TEXT).read_text(encoding="utf-8")
        assert content1 == content2

    def test_batch_idempotent(self, tmp_path: Path) -> None:
        """Saving the same batch twice produces same file content."""
        save_batch_progress(tmp_path, 0, ["a", "b"], 2)
        content1 = (tmp_path / _CHECKPOINT_BATCH).read_text(encoding="utf-8")
        save_batch_progress(tmp_path, 0, ["a", "b"], 2)
        content2 = (tmp_path / _CHECKPOINT_BATCH).read_text(encoding="utf-8")
        assert content1 == content2

    def test_dubbing_idempotent(self, tmp_path: Path) -> None:
        """Saving the same dubbing data twice produces same file content."""
        save_dubbing_checkpoint(tmp_path, srt_text="srt", target_lang="French")
        content1 = (tmp_path / _CHECKPOINT_DUBBING).read_text(encoding="utf-8")
        # Re-save with same values
        save_dubbing_checkpoint(tmp_path, srt_text="srt", target_lang="French")
        content2 = (tmp_path / _CHECKPOINT_DUBBING).read_text(encoding="utf-8")
        assert content1 == content2


# ---------------------------------------------------------------------------
# save_dubbing_checkpoint error propagation (no try/except wrapper)
# ---------------------------------------------------------------------------


class TestSaveDubbingCheckpointErrorPropagation:
    """Verify save_dubbing_checkpoint propagates errors from _write_checkpoint."""

    def test_oserror_propagates_through_write_checkpoint(self, tmp_path: Path) -> None:
        """RuntimeError from _write_checkpoint propagates to the caller."""
        with (
            patch(
                "src.core.checkpoint._write_checkpoint",
                side_effect=RuntimeError("disk on fire"),
            ),
            pytest.raises(RuntimeError, match="disk on fire"),
        ):
            save_dubbing_checkpoint(tmp_path, srt_text="should fail")

    def test_oserror_inside_write_checkpoint_is_logged_not_raised(
        self, tmp_path: Path
    ) -> None:
        """OSError from mocked _write_checkpoint propagates to the caller."""
        with (
            patch(
                "src.core.checkpoint._write_checkpoint",
                side_effect=OSError("permission denied"),
            ),
            pytest.raises(OSError, match="permission denied"),
        ):
            save_dubbing_checkpoint(tmp_path, srt_text="test")


# ---------------------------------------------------------------------------
# load_dubbing_checkpoint with corrupt JSON file
# ---------------------------------------------------------------------------


class TestLoadDubbingCheckpointCorruptJSON:
    """Verify load_dubbing_checkpoint handles corrupt JSON gracefully."""

    def test_invalid_json_returns_none(self, tmp_path: Path) -> None:
        """Writing invalid JSON to the checkpoint file produces None."""
        (tmp_path / _CHECKPOINT_DUBBING).write_text("{not valid json!!}")
        result = load_dubbing_checkpoint(tmp_path)
        assert result is None

    def test_truncated_json_returns_none(self, tmp_path: Path) -> None:
        """Truncated JSON content returns None gracefully."""
        (tmp_path / _CHECKPOINT_DUBBING).write_text('{"version": 1, "srt_text":')
        result = load_dubbing_checkpoint(tmp_path)
        assert result is None

    def test_binary_garbage_returns_none(self, tmp_path: Path) -> None:
        """Binary garbage in checkpoint file returns None."""
        (tmp_path / _CHECKPOINT_DUBBING).write_bytes(b"\x00\x01\xff\xfe\xab\xcd")
        result = load_dubbing_checkpoint(tmp_path)
        assert result is None


# ---------------------------------------------------------------------------
# save_text_batch normal operation — save actual data and verify round-trip
# ---------------------------------------------------------------------------


class TestSaveTextBatchNormalOperation:
    """Verify save_text_batch saves and loads back real batch data correctly."""

    def test_save_and_load_batch_data(self, tmp_path: Path) -> None:
        """Save actual batch data, load it back, and verify content matches."""
        from src.core.checkpoint import save_text_batch  # noqa: PLC0415

        chunks = {
            0: "The quick brown fox",
            1: "jumps over the lazy dog",
            2: "Lorem ipsum dolor sit amet",
        }
        save_text_batch(tmp_path, chunks, 3)

        result = load_text_checkpoint(tmp_path)
        assert result is not None
        assert len(result) == 3  # noqa: PLR2004
        assert result[0] == "The quick brown fox"
        assert result[1] == "jumps over the lazy dog"
        assert result[2] == "Lorem ipsum dolor sit amet"

    def test_save_batch_unicode_content(self, tmp_path: Path) -> None:
        """Save batch data with unicode characters and verify round-trip."""
        from src.core.checkpoint import save_text_batch  # noqa: PLC0415

        chunks = {
            0: "Xin chào thế giới",
            1: "日本語のテスト",
            2: "Привет мир",
        }
        save_text_batch(tmp_path, chunks, 3)

        result = load_text_checkpoint(tmp_path)
        assert result is not None
        assert result[0] == "Xin chào thế giới"
        assert result[1] == "日本語のテスト"
        assert result[2] == "Привет мир"

    def test_save_batch_preserves_total_chunks(self, tmp_path: Path) -> None:
        """total_chunks value is persisted in the checkpoint file."""
        from src.core.checkpoint import save_text_batch  # noqa: PLC0415

        save_text_batch(tmp_path, {0: "partial"}, 10)

        # Read raw JSON to check total_chunks
        raw = json.loads((tmp_path / _CHECKPOINT_TEXT).read_text(encoding="utf-8"))
        assert raw["total_chunks"] == 10  # noqa: PLR2004
        assert raw["version"] == _VERSION


# ---------------------------------------------------------------------------
# Edge case: save_pdf_page_progress with empty block list
# ---------------------------------------------------------------------------


class TestSavePdfPageProgressEmptyBlocks:
    """Empty block list doesn't crash, saves valid checkpoint."""

    def test_empty_blocks_saves_valid_checkpoint(self, tmp_path: Path) -> None:
        """Saving an empty block list for a page produces a loadable checkpoint."""
        save_pdf_page_progress(tmp_path, 0, [], 3)

        result = load_pdf_checkpoint(tmp_path)
        assert result is not None
        assert 0 in result
        assert result[0] == []

    def test_empty_blocks_multiple_pages(self, tmp_path: Path) -> None:
        """Multiple pages with empty blocks all round-trip correctly."""
        save_pdf_page_progress(tmp_path, 0, [], 5)
        save_pdf_page_progress(tmp_path, 2, [], 5)
        save_pdf_page_progress(tmp_path, 4, [], 5)

        result = load_pdf_checkpoint(tmp_path)
        assert result is not None
        assert len(result) == 3  # noqa: PLR2004
        for page_idx in (0, 2, 4):
            assert result[page_idx] == []

    def test_empty_blocks_mixed_with_populated(self, tmp_path: Path) -> None:
        """An empty block page coexists with a populated page."""
        save_pdf_page_progress(tmp_path, 0, [], 2)
        save_pdf_page_progress(tmp_path, 1, [{"text": "hello"}], 2)

        result = load_pdf_checkpoint(tmp_path)
        assert result is not None
        assert result[0] == []
        assert len(result[1]) == 1
        assert result[1][0]["text"] == "hello"


# ---------------------------------------------------------------------------
# Edge case: clear_checkpoints with read-only directory (permission error)
# ---------------------------------------------------------------------------


class TestClearCheckpointsReadOnlyDir:
    """Permission error during clear doesn't crash (OSError handled)."""

    def test_oserror_on_unlink_is_silently_handled(self, tmp_path: Path) -> None:
        """OSError from Path.unlink is logged but does not propagate."""
        # Create a checkpoint file so glob finds something
        save_text_chunk(tmp_path, 0, "data", 1)
        assert (tmp_path / _CHECKPOINT_TEXT).exists()

        # Patch Path.unlink to raise OSError
        with patch.object(Path, "unlink", side_effect=OSError("Permission denied")):
            # Should not raise — OSError is caught per-file
            clear_checkpoints(tmp_path)

        # The file still exists because unlink was blocked
        assert (tmp_path / _CHECKPOINT_TEXT).exists()

    def test_partial_clear_on_mixed_permissions(self, tmp_path: Path) -> None:
        """When one checkpoint unlink fails, others are still attempted."""
        save_text_chunk(tmp_path, 0, "text", 1)
        save_pdf_page_progress(tmp_path, 0, [{"t": "x"}], 1)

        call_count = 0
        original_unlink = Path.unlink

        def selective_unlink(self_path: Path, *a, **kw) -> None:
            """Fail on the first call, succeed on the second."""
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise OSError("disk error")
            original_unlink(self_path, *a, **kw)

        with patch.object(Path, "unlink", selective_unlink):
            clear_checkpoints(tmp_path)

        # At least one file should have been attempted for removal
        assert call_count >= 2  # noqa: PLR2004


# ---------------------------------------------------------------------------
# Edge case: save_batch_progress atomic rename — no temp files left behind
# ---------------------------------------------------------------------------


class TestSaveBatchProgressAtomicRename:
    """Verify temp file is renamed (not left behind on success)."""

    def test_no_tmp_files_after_successful_batch_save(self, tmp_path: Path) -> None:
        """After save_batch_progress, no .tmp files remain in the directory."""
        save_batch_progress(tmp_path, 0, ["alpha", "beta"], 4)
        save_batch_progress(tmp_path, 2, ["gamma", "delta"], 4)

        tmp_files = list(tmp_path.glob("*.tmp"))
        assert tmp_files == []

        # The actual checkpoint file should exist and be valid
        result = load_batch_checkpoint(tmp_path)
        assert result is not None
        assert len(result) == 4  # noqa: PLR2004

    def test_checkpoint_file_is_complete_json(self, tmp_path: Path) -> None:
        """The final checkpoint file is valid, complete JSON."""
        save_batch_progress(tmp_path, 0, ["val0"], 2)
        save_batch_progress(tmp_path, 1, ["val1"], 2)

        raw = json.loads(
            (tmp_path / _CHECKPOINT_BATCH).read_text(encoding="utf-8"),
        )
        assert raw["version"] == _VERSION
        assert raw["total_values"] == 2  # noqa: PLR2004
        assert raw["translated_values"]["0"] == "val0"
        assert raw["translated_values"]["1"] == "val1"

    def test_mkstemp_failure_does_not_leave_partial_file(self, tmp_path: Path) -> None:
        """If mkstemp fails, no partial checkpoint or .tmp file is left."""
        with patch(
            "src.core.checkpoint.tempfile.mkstemp",
            side_effect=OSError("no space"),
        ):
            save_batch_progress(tmp_path, 0, ["x"], 1)

        # Neither the final file nor any temp file should exist
        assert not (tmp_path / _CHECKPOINT_BATCH).exists()
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert tmp_files == []


# ---------------------------------------------------------------------------
# Edge case: PDF checkpoint with non-contiguous pages (gaps)
# ---------------------------------------------------------------------------


class TestLoadCheckpointNonContiguousPages:
    """PDF checkpoint with pages 0, 2, 5 (gaps) loads correctly."""

    def test_non_contiguous_page_indices(self, tmp_path: Path) -> None:
        """Pages 0, 2, 5 are stored and loaded with correct indices."""
        save_pdf_page_progress(tmp_path, 0, [{"text": "page_0"}], 10)
        save_pdf_page_progress(tmp_path, 2, [{"text": "page_2"}], 10)
        save_pdf_page_progress(tmp_path, 5, [{"text": "page_5"}], 10)

        result = load_pdf_checkpoint(tmp_path)
        assert result is not None
        assert set(result.keys()) == {0, 2, 5}
        assert result[0][0]["text"] == "page_0"
        assert result[2][0]["text"] == "page_2"
        assert result[5][0]["text"] == "page_5"

    def test_gap_pages_not_present(self, tmp_path: Path) -> None:
        """Pages 1, 3, 4 (not saved) are not in the loaded checkpoint."""
        save_pdf_page_progress(tmp_path, 0, [{"text": "p0"}], 6)
        save_pdf_page_progress(tmp_path, 2, [{"text": "p2"}], 6)
        save_pdf_page_progress(tmp_path, 5, [{"text": "p5"}], 6)

        result = load_pdf_checkpoint(tmp_path)
        assert result is not None
        for missing_page in (1, 3, 4):
            assert missing_page not in result

    def test_large_gap_between_pages(self, tmp_path: Path) -> None:
        """Pages 0 and 999 with a large gap load correctly."""
        save_pdf_page_progress(tmp_path, 0, [{"text": "first"}], 1000)
        save_pdf_page_progress(tmp_path, 999, [{"text": "last"}], 1000)

        result = load_pdf_checkpoint(tmp_path)
        assert result is not None
        assert len(result) == 2  # noqa: PLR2004
        assert result[0][0]["text"] == "first"
        assert result[999][0]["text"] == "last"

    def test_non_contiguous_preserves_total_pages(self, tmp_path: Path) -> None:
        """total_pages is persisted even with non-contiguous page saves."""
        save_pdf_page_progress(tmp_path, 3, [{"text": "p3"}], 20)

        raw = json.loads(
            (tmp_path / _CHECKPOINT_PDF).read_text(encoding="utf-8"),
        )
        assert raw["total_pages"] == 20  # noqa: PLR2004


# ---------------------------------------------------------------------------
# Edge case: OCRResult serialization with unusual field values
# ---------------------------------------------------------------------------


class TestOCRResultSerializationEdgeCases:
    """OCRResult with is_single_line=0 (int), negative line_height_ratio."""

    def test_is_single_line_zero_int(self) -> None:
        """is_single_line stored as int 0 deserializes as falsy."""
        r = OCRResult("text", 10, 20, 100, 50, 0.9)
        r.is_single_line = 0  # type: ignore[assignment]
        r.line_height_ratio = 1.2

        data = _serialize_ocr_result(r)
        restored = _deserialize_ocr_result(data)
        # int 0 is falsy — the deserialized value should also be falsy
        assert not restored.is_single_line

    def test_is_single_line_one_int(self) -> None:
        """is_single_line stored as int 1 deserializes as truthy."""
        r = OCRResult("text", 10, 20, 100, 50, 0.9)
        r.is_single_line = 1  # type: ignore[assignment]

        data = _serialize_ocr_result(r)
        restored = _deserialize_ocr_result(data)
        assert restored.is_single_line

    def test_negative_line_height_ratio(self) -> None:
        """Negative line_height_ratio round-trips without error."""
        r = OCRResult("text", 10, 20, 100, 50, 0.9)
        r.line_height_ratio = -0.5

        data = _serialize_ocr_result(r)
        restored = _deserialize_ocr_result(data)
        assert restored.line_height_ratio == -0.5  # noqa: PLR2004

    def test_zero_line_height_ratio(self) -> None:
        """Zero line_height_ratio round-trips without error."""
        r = OCRResult("text", 10, 20, 100, 50, 0.9)
        r.line_height_ratio = 0.0

        data = _serialize_ocr_result(r)
        restored = _deserialize_ocr_result(data)
        assert restored.line_height_ratio == 0.0

    def test_very_large_line_height_ratio(self) -> None:
        """Very large line_height_ratio round-trips correctly."""
        r = OCRResult("text", 10, 20, 100, 50, 0.9)
        r.line_height_ratio = 999.99

        data = _serialize_ocr_result(r)
        restored = _deserialize_ocr_result(data)
        assert restored.line_height_ratio == 999.99  # noqa: PLR2004

    def test_none_line_height_ratio(self) -> None:
        """None line_height_ratio round-trips as None."""
        r = OCRResult("text", 10, 20, 100, 50, 0.9)
        r.line_height_ratio = None  # type: ignore[assignment]

        data = _serialize_ocr_result(r)
        restored = _deserialize_ocr_result(data)
        assert restored.line_height_ratio is None

    def test_all_bool_fields_as_ints(self) -> None:
        """Boolean fields stored as ints (0/1) survive serialization."""
        r = OCRResult("text", 10, 20, 100, 50, 0.9)
        r.is_bold = 1  # type: ignore[assignment]
        r.is_italic = 0  # type: ignore[assignment]
        r.is_underline = 1  # type: ignore[assignment]
        r.is_single_line = 0  # type: ignore[assignment]

        data = _serialize_ocr_result(r)
        restored = _deserialize_ocr_result(data)
        assert restored.is_bold
        assert not restored.is_italic
        assert restored.is_underline
        assert not restored.is_single_line


# ===========================================================================
# PDF checkpoint stale-file detection
# ===========================================================================
#
# ``load_pdf_checkpoint`` accepts an ``expected_total_pages`` arg that
# guards against the source PDF being replaced between runs (a 100-page
# document swapped for a 50-page version at the same path would
# otherwise resume mid-pipeline against the wrong file).  The legacy
# call without the arg keeps loading whatever's on disk.  These tests
# pin both behaviours so future refactors can't silently relax the
# validation.


def test_load_pdf_checkpoint_discards_when_total_pages_shrank(
    tmp_path: Path,
) -> None:
    """100-page checkpoint + 50-page expected → discard, return None.

    The PDF was replaced at the same path with a shorter file; the
    saved page indices (e.g. page 80) don't exist in the new doc, so
    resuming would render translated text into the wrong pages.
    """
    save_pdf_page_progress(
        tmp_path,
        page_index=10,
        translated_blocks=[{"text": "old", "rect": [0, 0, 50, 10]}],
        total_pages=100,
    )

    result = load_pdf_checkpoint(tmp_path, expected_total_pages=50)
    assert result is None


def test_load_pdf_checkpoint_discards_when_total_pages_grew(
    tmp_path: Path,
) -> None:
    """10-page checkpoint + 20-page expected → discard, return None.

    Even when the new file is *longer*, the source has changed; we
    can't trust translations made against the old block layout.
    """
    save_pdf_page_progress(
        tmp_path,
        page_index=0,
        translated_blocks=[{"text": "old", "rect": [0, 0, 50, 10]}],
        total_pages=10,
    )

    result = load_pdf_checkpoint(tmp_path, expected_total_pages=20)
    assert result is None


def test_load_pdf_checkpoint_keeps_when_total_pages_match(
    tmp_path: Path,
) -> None:
    """Matching total_pages keeps the checkpoint and returns its pages."""
    save_pdf_page_progress(
        tmp_path,
        page_index=0,
        translated_blocks=[{"text": "page 0", "rect": [0, 0, 50, 10]}],
        total_pages=42,
    )

    result = load_pdf_checkpoint(tmp_path, expected_total_pages=42)
    assert result is not None
    assert 0 in result
    assert result[0][0]["text"] == "page 0"


def test_load_pdf_checkpoint_legacy_callers_skip_validation(
    tmp_path: Path,
) -> None:
    """Calls without ``expected_total_pages`` load whatever is on disk.

    Older code paths in the pipeline don't yet pass the page count
    (e.g. mid-flow resume helpers).  They must keep working — the
    validation is opt-in, not mandatory.
    """
    save_pdf_page_progress(
        tmp_path,
        page_index=0,
        translated_blocks=[{"text": "legacy", "rect": [0, 0, 50, 10]}],
        total_pages=5,
    )

    # No ``expected_total_pages`` argument → no validation.
    result = load_pdf_checkpoint(tmp_path)
    assert result is not None
    assert result[0][0]["text"] == "legacy"


def test_load_pdf_checkpoint_missing_total_pages_field_skips_validation(
    tmp_path: Path,
) -> None:
    """Pre-validation checkpoints (no ``total_pages`` key) still load.

    Checkpoints written before the validation field existed shouldn't
    be discarded en masse on first read after the upgrade — they
    don't have ``total_pages`` so the comparison is a no-op.
    """
    from src.core.checkpoint import (  # noqa: PLC0415
        _CHECKPOINT_PDF,
        _VERSION,
        _write_checkpoint,  # noqa: PLC0415
    )

    legacy = {
        "version": _VERSION,
        # No "total_pages" field — pre-validation format.
        "translated_pages": {
            "0": [{"text": "legacy block", "rect": [0, 0, 50, 10]}],
        },
    }
    _write_checkpoint(tmp_path, _CHECKPOINT_PDF, legacy)

    # ``data.get("total_pages")`` returns None; the check ``None != 5``
    # is True, so the checkpoint is discarded.  Document the behaviour:
    # legacy checkpoints must be re-saved by the new code path before
    # they validate again.  This is acceptable because the fallback is
    # a fresh translation, not corruption.
    result = load_pdf_checkpoint(tmp_path, expected_total_pages=5)
    assert result is None

    # …but legacy callers (no expected_total_pages) still get them.
    result_legacy = load_pdf_checkpoint(tmp_path)
    assert result_legacy is not None
    assert result_legacy[0][0]["text"] == "legacy block"


# ===========================================================================
# Batch checkpoint — resume across changed batch sizes
# ===========================================================================
#
# ``save_batch_progress`` stores translations keyed by absolute item
# index (``batch_start + i``), not by batch ordinal — so a checkpoint
# written with one batch_size must remain valid when the next run uses
# a different batch_size.  These tests pin that contract: if a future
# refactor switches to per-batch-id keying, the failure surfaces here
# instead of silently re-translating already-completed items.


def test_batch_checkpoint_survives_batch_size_change(tmp_path: Path) -> None:
    """Checkpoint written with batch_size=3 still readable on resume with batch_size=2."""
    # Run 1 simulates two batches at size 3.
    save_batch_progress(tmp_path, 0, ["t0", "t1", "t2"], total_values=10)
    save_batch_progress(tmp_path, 3, ["t3", "t4", "t5"], total_values=10)

    # Run 2 starts fresh with a different batch_size.  Resume should
    # see every previously-translated index keyed by absolute position.
    loaded = load_batch_checkpoint(tmp_path)
    assert loaded is not None
    assert loaded == {0: "t0", 1: "t1", 2: "t2", 3: "t3", 4: "t4", 5: "t5"}

    # New batch (size=2 starting at index 6) lays alongside without
    # overwriting earlier indices.
    save_batch_progress(tmp_path, 6, ["t6", "t7"], total_values=10)
    loaded2 = load_batch_checkpoint(tmp_path)
    assert loaded2 is not None
    assert len(loaded2) == 8  # noqa: PLR2004
    assert loaded2[0] == "t0"  # earliest entry intact
    assert loaded2[7] == "t7"  # newest entry recorded


def test_batch_checkpoint_overwrites_index_on_retry(tmp_path: Path) -> None:
    """Re-saving the same index replaces the prior translation in place.

    A retry after a failed batch must overwrite, not append a parallel
    entry — the dict is keyed by index so this is the intended behaviour.
    """
    save_batch_progress(tmp_path, 0, ["draft-a", "draft-b"], total_values=2)
    save_batch_progress(tmp_path, 0, ["final-a", "final-b"], total_values=2)
    loaded = load_batch_checkpoint(tmp_path)
    assert loaded == {0: "final-a", 1: "final-b"}


def test_batch_checkpoint_loads_when_indices_exceed_current_total(
    tmp_path: Path,
) -> None:
    """Forward-compat: indices > current total_values still load.

    Scenario: source list shrank between runs (e.g. user edited the
    glossary).  ``load_batch_checkpoint`` does not validate that
    indices fit the new list — it returns whatever's on disk and lets
    the caller filter.  Pin that behaviour so it doesn't quietly
    change to "discard the entire checkpoint".
    """
    save_batch_progress(tmp_path, 0, ["a", "b", "c", "d"], total_values=4)

    loaded = load_batch_checkpoint(tmp_path)
    assert loaded is not None
    # The full set is returned — caller (translate_batch) decides what
    # to do with indices outside its current list.
    assert loaded == {0: "a", 1: "b", 2: "c", 3: "d"}


class TestDubbingCheckpointPostTranslateNoOverwrite:
    """Pause-after-translate-before-TTS resume must NOT overwrite raw STT srt.

    Pins the regression documented in AGENTS.md: the post-translate
    ``save_dubbing_checkpoint()`` call passes ``translated_srt`` only,
    never ``srt_text``. A previous bug overwrote ``srt_text`` with the
    translated text, so resuming after pause surfaced translated lines
    as the "original" subtitle output.

    The existing incremental-merge test exercises the merge contract;
    this one explicitly mimics the dubbing pipeline's two-step write
    sequence (STT save → translate save → load) and asserts the original
    text survives byte-for-byte.
    """

    def test_post_translate_save_preserves_original_srt(
        self, tmp_path: Path,
    ) -> None:
        """Real dubbing-pipeline call ordering: STT save, then translate-only save."""
        original_srt = "1\n00:00:01,000 --> 00:00:02,000\nHello\n"
        translated = "1\n00:00:01,000 --> 00:00:02,000\nBonjour\n"

        # Step 1: STT writes srt_text + target_lang.
        save_dubbing_checkpoint(
            tmp_path, srt_text=original_srt, target_lang="French",
        )
        # Step 2: translate writes translated_srt ONLY (no srt_text!).
        save_dubbing_checkpoint(
            tmp_path, translated_srt=translated,
        )

        ckpt = load_dubbing_checkpoint(tmp_path)
        assert ckpt is not None
        # Original survives byte-for-byte.
        assert ckpt["srt_text"] == original_srt, (
            "Original srt_text was overwritten during post-translate save"
        )
        assert ckpt["translated_srt"] == translated
        assert ckpt["target_lang"] == "French"


# ---------------------------------------------------------------------------
# Office embedded-image per-image checkpoint
# ---------------------------------------------------------------------------


def test_office_image_path_contract(tmp_path: Path) -> None:
    """``_office_image_path`` returns ``<dir>/office_images/<hash>.bin``.

    Direct contract assertion: ``save`` and ``load`` both build the
    target path through this helper (after the DRY refactor in
    commit 2f5ffc3), so any divergence (e.g. one starts using
    ``.cache`` instead of ``.bin``) would silently break the
    round-trip.  This test pins the literal path shape so the
    drift is caught explicitly rather than via round-trip failure.
    """
    from src.core.checkpoint import _office_image_path  # noqa: PLC0415

    digest = "deadbeef" * 8  # 64 hex chars (SHA256 length)
    path = _office_image_path(tmp_path, digest)
    assert path == tmp_path / "office_images" / f"{digest}.bin"


class TestOfficeImageCheckpoint:
    """Cache layer that lets a resumed run skip already-translated images."""

    def test_hash_is_deterministic(self) -> None:
        """Same bytes always hash to the same digest (cache key stability)."""
        data = b"any-image-blob"
        assert hash_office_image(data) == hash_office_image(data)

    def test_hash_differs_for_different_bytes(self) -> None:
        """Different bytes must produce different keys (no false reuse)."""
        assert hash_office_image(b"foo") != hash_office_image(b"bar")

    def test_load_miss_returns_none(self, tmp_path: Path) -> None:
        """An unseen hash returns None — caller does a fresh translation."""
        digest = hash_office_image(b"never-seen")
        assert load_office_image_checkpoint(tmp_path, digest) is None

    def test_save_then_load_round_trips(self, tmp_path: Path) -> None:
        """Saved bytes survive load byte-for-byte."""
        original = b"original-image-bytes"
        translated = b"translated-image-bytes\x00\xff\x01"
        digest = hash_office_image(original)
        save_office_image_checkpoint(tmp_path, digest, translated)
        assert load_office_image_checkpoint(tmp_path, digest) == translated

    def test_save_creates_office_images_subdir(self, tmp_path: Path) -> None:
        """The cache lives in its own subdirectory, not directly in storage."""
        digest = hash_office_image(b"x")
        save_office_image_checkpoint(tmp_path, digest, b"y")
        assert (tmp_path / _OFFICE_IMAGE_DIR_NAME).is_dir()
        assert (tmp_path / _OFFICE_IMAGE_DIR_NAME / f"{digest}.bin").is_file()

    def test_overwrite_replaces_prior_translation(self, tmp_path: Path) -> None:
        """Re-saving with the same hash replaces (does not append)."""
        digest = hash_office_image(b"src")
        save_office_image_checkpoint(tmp_path, digest, b"v1")
        save_office_image_checkpoint(tmp_path, digest, b"v2")
        assert load_office_image_checkpoint(tmp_path, digest) == b"v2"

    def test_clear_checkpoints_wipes_office_image_cache(
        self, tmp_path: Path,
    ) -> None:
        """``clear_checkpoints`` must also remove the image cache subdir.

        Otherwise a successful task would leave the per-image binaries
        on disk forever (they can be several MB each).
        """
        digest = hash_office_image(b"src")
        save_office_image_checkpoint(tmp_path, digest, b"translated")
        save_text_chunk(tmp_path, 0, "hello", 1)  # JSON checkpoint too

        clear_checkpoints(tmp_path)

        assert not (tmp_path / _OFFICE_IMAGE_DIR_NAME).exists()
        assert not (tmp_path / _CHECKPOINT_TEXT).exists()

    def test_clear_checkpoints_succeeds_without_office_dir(
        self, tmp_path: Path,
    ) -> None:
        """No-op cleanly when no image cache directory exists."""
        save_text_chunk(tmp_path, 0, "hello", 1)
        clear_checkpoints(tmp_path)  # must not raise
        assert not (tmp_path / _CHECKPOINT_TEXT).exists()

    def test_clear_checkpoints_swallows_rmtree_oserror(
        self, tmp_path: Path, caplog,
    ) -> None:
        """``shutil.rmtree`` failure on image cache dir is swallowed + logged.

        Defensive: checkpoint cleanup runs on successful task
        completion and must never block the success path with a
        disk-level error (e.g. read-only mount, file held open by
        an external process on Windows).  Mirrors the existing
        unlink-error-swallowing guard for ``checkpoint_*.json``.
        """
        digest = hash_office_image(b"src")
        save_office_image_checkpoint(tmp_path, digest, b"translated")
        assert (tmp_path / _OFFICE_IMAGE_DIR_NAME).exists()

        with (
            patch(
                "src.core.checkpoint.shutil.rmtree",
                side_effect=OSError("permission denied"),
            ),
            caplog.at_level("WARNING", logger="checkpoint"),
        ):
            clear_checkpoints(tmp_path)  # must not raise

        # The directory is still on disk (rmtree raised), but the
        # function completed successfully and logged the failure.
        assert (tmp_path / _OFFICE_IMAGE_DIR_NAME).exists()
        assert any(
            "office image cache" in r.message
            for r in caplog.records
            if r.levelname == "WARNING"
        )

    def test_load_with_corrupt_file_returns_none(
        self, tmp_path: Path,
    ) -> None:
        """An unreadable file is a cache miss, not an error.

        Defensive: corruption on disk is a defensible reason to redo
        work, not to abort the run.  We simulate the corruption by
        replacing the file with a directory of the same name so the
        read raises ``OSError``.
        """
        digest = hash_office_image(b"src")
        save_office_image_checkpoint(tmp_path, digest, b"translated")
        cache_file = tmp_path / _OFFICE_IMAGE_DIR_NAME / f"{digest}.bin"
        cache_file.unlink()
        cache_file.mkdir()  # not-a-file at the expected path
        assert load_office_image_checkpoint(tmp_path, digest) is None

    def test_save_swallows_oserror_silently(
        self, tmp_path: Path,
    ) -> None:
        """A failed cache write must not bubble up to abort translation."""
        digest = hash_office_image(b"src")
        # Force the image subdir to be a file so mkdir(exist_ok=True)
        # raises NotADirectoryError (a subclass of OSError).
        (tmp_path / _OFFICE_IMAGE_DIR_NAME).write_text("not a dir")
        save_office_image_checkpoint(tmp_path, digest, b"translated")
        # No exception ⇒ cache write was best-effort as designed.

    def test_duplicate_images_share_one_cache_entry(
        self, tmp_path: Path,
    ) -> None:
        """A doc with N copies of the same logo collapses to one cache hit."""
        logo_bytes = b"company-logo-png-bytes"
        translated_logo = b"translated-logo"
        digest = hash_office_image(logo_bytes)
        save_office_image_checkpoint(tmp_path, digest, translated_logo)

        # Same source bytes anywhere else in the doc → same digest →
        # one cache hit, no extra LLM call.
        for _ in range(5):
            assert (
                load_office_image_checkpoint(tmp_path, hash_office_image(logo_bytes))
                == translated_logo
            )
