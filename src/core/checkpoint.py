"""Checkpoint I/O for resumable translation tasks.

Saves and loads intermediate artifacts as JSON files in each task's
storage directory.  Uses atomic write-then-rename to prevent corruption
on crash.  All public functions are pure (no side effects beyond the
filesystem) and return None on any load failure so callers fall back
to a full restart.
"""

import hashlib
import json
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from src.core.ocr_engine import OCRResult

logger = logging.getLogger("checkpoint")

# Checkpoint version for forward-compatibility checks
_VERSION = 1

# Checkpoint file names
_CHECKPOINT_OCR = "checkpoint_ocr.json"
_CHECKPOINT_LLM = "checkpoint_llm.json"
_CHECKPOINT_TEXT = "checkpoint_text.json"
_CHECKPOINT_BATCH = "checkpoint_batch.json"
_CHECKPOINT_EPUB = "checkpoint_epub.json"
_CHECKPOINT_PDF = "checkpoint_pdf.json"
_CHECKPOINT_DUBBING = "checkpoint_dubbing.json"

# Per-image checkpoint cache for embedded-image translation in Office
# documents.  Each translated image is stored as a separate binary
# file keyed by SHA256 of the *original* image bytes — that way a
# document with N copies of the same logo only pays for one OCR + LLM
# round-trip, and a resumed run skips images that were already
# translated before the previous attempt was interrupted.
_OFFICE_IMAGE_DIR_NAME = "office_images"

# Alignment string constants persisted in checkpoint JSON.  Stored as
# strings (not Qt.AlignmentFlag enums) so checkpoints stay readable
# without a PySide6 dependency.
ALIGN_LEFT = "AlignLeft"
ALIGN_RIGHT = "AlignRight"
ALIGN_CENTER = "AlignHCenter"
ALIGN_JUSTIFY = "AlignJustify"

_VALID_ALIGNMENTS: set[str] = {ALIGN_LEFT, ALIGN_RIGHT, ALIGN_CENTER, ALIGN_JUSTIFY}


# ── Storage helpers ────────────────────────────────────────────────


def get_storage_dir(storage_path: str) -> Path:
    """Returns the task's storage directory from its cloned file path.

    Args:
        storage_path: Absolute path to the cloned file in storage.

    Returns:
        Path: The parent directory of the cloned file.
    """
    return Path(storage_path).parent


# ── Atomic file I/O ────────────────────────────────────────────────


def _write_checkpoint(storage_dir: Path, filename: str, data: dict[str, Any]) -> None:
    """Writes a checkpoint JSON file atomically (write-tmp then rename).

    Args:
        storage_dir: Task storage directory.
        filename: Checkpoint file name.
        data: Dictionary to serialise as JSON.
    """
    target = storage_dir / filename
    try:
        fd, tmp_path = tempfile.mkstemp(
            dir=str(storage_dir),
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False)
        except BaseException:
            Path(tmp_path).unlink(missing_ok=True)
            raise
        Path(tmp_path).replace(target)
    except OSError:
        logger.exception("Failed to write checkpoint %s", target)


def _read_checkpoint(storage_dir: Path, filename: str) -> dict[str, Any] | None:
    """Reads a checkpoint JSON file.  Returns None if missing or corrupt.

    Also returns None when the file's version differs from _VERSION,
    so a schema change forces a clean restart.

    Args:
        storage_dir: Task storage directory.
        filename: Checkpoint file name.

    Returns:
        dict[str, Any] | None: Parsed data or None.
    """
    target = storage_dir / filename
    if not target.exists():
        return None
    try:
        with target.open(encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return None
        if data.get("version") != _VERSION:
            logger.warning(
                "Checkpoint version mismatch in %s (expected %d, got %s)",
                target,
                _VERSION,
                data.get("version"),
            )
            return None
        return data
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        logger.warning("Corrupt checkpoint file: %s", target)
        return None


def clear_checkpoints(storage_dir: Path) -> None:
    """Deletes all checkpoint artefacts from the storage directory.

    Removes every ``checkpoint_*.json`` file plus the
    ``office_images/`` per-image cache directory.  Best-effort; errors
    are logged but never raised because checkpoint cleanup must never
    block task completion.

    Args:
        storage_dir: Task storage directory.
    """
    for path in storage_dir.glob("checkpoint_*.json"):
        try:
            path.unlink()
        except OSError:
            logger.warning("Could not remove checkpoint: %s", path)

    image_dir = storage_dir / _OFFICE_IMAGE_DIR_NAME
    if image_dir.exists():
        try:
            shutil.rmtree(image_dir)
        except OSError:
            logger.warning("Could not remove office image cache: %s", image_dir)


# ── OCRResult serialization ────────────────────────────────────────


def _serialize_ocr_result(result: OCRResult) -> dict[str, Any]:
    """Converts an OCRResult to a fully serializable dictionary.

    Extends the built-in to_dict() with fields needed for resuming
    (translated_html, original_text_height, line_height_ratio,
    is_single_line).  Color and alignment are already strings.

    Args:
        result: An OCRResult instance.

    Returns:
        dict: JSON-safe dictionary.
    """
    return {
        "text": result.text,
        "x": result.x,
        "y": result.y,
        "w": result.w,
        "h": result.h,
        "confidence": result.confidence,
        "color": result.color or "#000000",
        "is_bold": result.is_bold,
        "is_italic": result.is_italic,
        "is_underline": result.is_underline,
        "translated_text": result.translated_text,
        "translated_html": result.translated_html,
        "alignment": result.alignment,
        "original_text_height": result.original_text_height,
        "line_height_ratio": result.line_height_ratio,
        "is_single_line": result.is_single_line,
    }


def _deserialize_ocr_result(data: dict[str, Any]) -> OCRResult:
    """Reconstructs an OCRResult from a serialized dictionary.

    Args:
        data: Dictionary produced by _serialize_ocr_result().

    Returns:
        OCRResult: Reconstructed result with all fields restored.
    """
    result = OCRResult(
        text=data["text"],
        x=data["x"],
        y=data["y"],
        w=data["w"],
        h=data["h"],
        confidence=data["confidence"],
    )
    result.color = data.get("color", "#000000")
    result.is_bold = data.get("is_bold", False)
    result.is_italic = data.get("is_italic", False)
    result.is_underline = data.get("is_underline", False)
    result.translated_text = data.get("translated_text", "")
    result.translated_html = data.get("translated_html", "")

    alignment_str = data.get("alignment")
    if alignment_str and alignment_str in _VALID_ALIGNMENTS:
        result.alignment = alignment_str
    else:
        result.alignment = None

    result.original_text_height = data.get("original_text_height", result.h)
    result.line_height_ratio = data.get("line_height_ratio", 1.2)
    result.is_single_line = data.get("is_single_line", False)

    return result


# ── Image pipeline checkpoints ─────────────────────────────────────


def save_ocr_checkpoint(
    storage_dir: Path,
    ocr_results: list[OCRResult],
    raw_ocr_results: list[OCRResult],
    ocr_method: str,
) -> None:
    """Saves OCR results after the OCR step.

    Best-effort: logs and returns on any serialization error.

    Args:
        storage_dir: Task storage directory.
        ocr_results: OCR results list.
        raw_ocr_results: Raw/unmerged OCR results.
        ocr_method: Name of the OCR engine used.
    """
    try:
        _write_checkpoint(
            storage_dir,
            _CHECKPOINT_OCR,
            {
                "version": _VERSION,
                "ocr_method": ocr_method,
                "ocr_results": [_serialize_ocr_result(r) for r in ocr_results],
                "raw_ocr_results": [_serialize_ocr_result(r) for r in raw_ocr_results],
            },
        )
    except Exception:
        logger.warning("Failed to save OCR checkpoint", exc_info=True)


def load_ocr_checkpoint(
    storage_dir: Path,
) -> tuple[list[OCRResult], list[OCRResult], str] | None:
    """Loads OCR checkpoint data.

    Args:
        storage_dir: Task storage directory.

    Returns:
        (ocr_results, raw_ocr_results, ocr_method) or None.
    """
    data = _read_checkpoint(storage_dir, _CHECKPOINT_OCR)
    if data is None:
        return None
    try:
        ocr_results = [_deserialize_ocr_result(d) for d in data["ocr_results"]]
        raw_ocr_results = [_deserialize_ocr_result(d) for d in data["raw_ocr_results"]]
        return ocr_results, raw_ocr_results, data["ocr_method"]
    except (KeyError, TypeError):
        logger.warning("Malformed OCR checkpoint in %s", storage_dir)
        return None


def save_llm_checkpoint(
    storage_dir: Path,
    ocr_results: list[OCRResult],
    translations: list[str],
    confirmed_raw_fragments: list[OCRResult],
) -> None:
    """Saves LLM results after the LLM + merge step.

    Best-effort: logs and returns on any serialization error.

    Args:
        storage_dir: Task storage directory.
        ocr_results: Merged paragraph-level OCR results.
        translations: List of translated strings.
        confirmed_raw_fragments: Raw fragments confirmed by merge.
    """
    try:
        _write_checkpoint(
            storage_dir,
            _CHECKPOINT_LLM,
            {
                "version": _VERSION,
                "ocr_results": [_serialize_ocr_result(r) for r in ocr_results],
                "translations": translations,
                "confirmed_raw_fragments": [
                    _serialize_ocr_result(r) for r in confirmed_raw_fragments
                ],
            },
        )
    except Exception:
        logger.warning("Failed to save LLM checkpoint", exc_info=True)


def load_llm_checkpoint(
    storage_dir: Path,
) -> tuple[list[OCRResult], list[str], list[OCRResult]] | None:
    """Loads LLM checkpoint data.

    Args:
        storage_dir: Task storage directory.

    Returns:
        (ocr_results, translations, confirmed_raw_fragments) or None.
    """
    data = _read_checkpoint(storage_dir, _CHECKPOINT_LLM)
    if data is None:
        return None
    try:
        ocr_results = [_deserialize_ocr_result(d) for d in data["ocr_results"]]
        translations = data["translations"]
        confirmed_raw_fragments = [
            _deserialize_ocr_result(d) for d in data["confirmed_raw_fragments"]
        ]
        return ocr_results, translations, confirmed_raw_fragments
    except (KeyError, TypeError):
        logger.warning("Malformed LLM checkpoint in %s", storage_dir)
        return None


# ── Text pipeline checkpoints (per-chunk) ──────────────────────────


def save_text_chunk(
    storage_dir: Path,
    chunk_index: int,
    translated_text: str,
    total_chunks: int,
) -> None:
    """Incrementally saves a translated text chunk.

    Reads the existing checkpoint, adds/updates the chunk, and writes
    back atomically.  Best-effort: logs and returns on error.

    Args:
        storage_dir: Task storage directory.
        chunk_index: Zero-based index of the chunk.
        translated_text: The translated chunk text.
        total_chunks: Total number of chunks in the document.
    """
    try:
        data = _read_checkpoint(storage_dir, _CHECKPOINT_TEXT) or {
            "version": _VERSION,
            "total_chunks": total_chunks,
            "translated_chunks": {},
        }
        data["translated_chunks"][str(chunk_index)] = translated_text
        data["total_chunks"] = total_chunks
        _write_checkpoint(storage_dir, _CHECKPOINT_TEXT, data)
    except Exception:
        logger.warning("Failed to save text checkpoint", exc_info=True)


def save_text_batch(
    storage_dir: Path,
    chunks: dict[int, str],
    total_chunks: int,
) -> None:
    """Saves multiple translated text chunks in a single write.

    Reads the existing checkpoint once, merges all chunks, and writes
    back atomically.  Much more efficient than calling save_text_chunk()
    in a loop (one I/O round-trip vs. N).

    Args:
        storage_dir: Task storage directory.
        chunks: Mapping of chunk_index to translated text.
        total_chunks: Total number of chunks in the document.
    """
    if not chunks:
        return
    try:
        data = _read_checkpoint(storage_dir, _CHECKPOINT_TEXT) or {
            "version": _VERSION,
            "total_chunks": total_chunks,
            "translated_chunks": {},
        }
        for idx, text in chunks.items():
            data["translated_chunks"][str(idx)] = text
        data["total_chunks"] = total_chunks
        _write_checkpoint(storage_dir, _CHECKPOINT_TEXT, data)
    except Exception:
        logger.warning("Failed to save text batch checkpoint", exc_info=True)


def load_text_checkpoint(storage_dir: Path) -> dict[int, str] | None:
    """Loads text chunk checkpoint data.

    Args:
        storage_dir: Task storage directory.

    Returns:
        dict mapping chunk_index (int) to translated text, or None.
    """
    data = _read_checkpoint(storage_dir, _CHECKPOINT_TEXT)
    if data is None:
        return None
    try:
        chunks = data["translated_chunks"]
        return {int(k): v for k, v in chunks.items()}
    except (KeyError, TypeError, ValueError):
        logger.warning("Malformed text checkpoint in %s", storage_dir)
        return None


# ── Batch pipeline checkpoints (JSON/CSV/office) ──────────────────


def save_batch_progress(
    storage_dir: Path,
    batch_start: int,
    translated_values: list[str],
    total_values: int,
) -> None:
    """Incrementally saves a batch of translated values.

    Best-effort: logs and returns on error.

    Args:
        storage_dir: Task storage directory.
        batch_start: Zero-based start index of this batch.
        translated_values: Translated strings for this batch.
        total_values: Total number of values to translate.
    """
    try:
        data = _read_checkpoint(storage_dir, _CHECKPOINT_BATCH) or {
            "version": _VERSION,
            "total_values": total_values,
            "translated_values": {},
        }
        for i, val in enumerate(translated_values):
            data["translated_values"][str(batch_start + i)] = val
        data["total_values"] = total_values
        _write_checkpoint(storage_dir, _CHECKPOINT_BATCH, data)
    except Exception:
        logger.warning("Failed to save batch checkpoint", exc_info=True)


def load_batch_checkpoint(storage_dir: Path) -> dict[int, str] | None:
    """Loads batch checkpoint data.

    Args:
        storage_dir: Task storage directory.

    Returns:
        dict mapping value_index (int) to translated string, or None.
    """
    data = _read_checkpoint(storage_dir, _CHECKPOINT_BATCH)
    if data is None:
        return None
    try:
        values = data["translated_values"]
        return {int(k): v for k, v in values.items()}
    except (KeyError, TypeError, ValueError):
        logger.warning("Malformed batch checkpoint in %s", storage_dir)
        return None


# ── EPUB pipeline checkpoints (per content file) ──────────────────


def save_epub_file_progress(
    storage_dir: Path,
    file_path: str,
    translated_content: str,
    content_files: list[str],
) -> None:
    """Incrementally saves a translated EPUB content file.

    Best-effort: logs and returns on error.

    Args:
        storage_dir: Task storage directory.
        file_path: Path within the EPUB archive (e.g. "OEBPS/ch1.xhtml").
        translated_content: Translated XHTML content.
        content_files: Full list of content file paths in the EPUB.
    """
    try:
        data = _read_checkpoint(storage_dir, _CHECKPOINT_EPUB) or {
            "version": _VERSION,
            "content_files": content_files,
            "translated_files": {},
        }
        data["translated_files"][file_path] = translated_content
        data["content_files"] = content_files
        _write_checkpoint(storage_dir, _CHECKPOINT_EPUB, data)
    except Exception:
        logger.warning("Failed to save EPUB checkpoint", exc_info=True)


def load_epub_checkpoint(storage_dir: Path) -> dict[str, str] | None:
    """Loads EPUB checkpoint data.

    Args:
        storage_dir: Task storage directory.

    Returns:
        dict mapping archive file path to translated content, or None.
    """
    data = _read_checkpoint(storage_dir, _CHECKPOINT_EPUB)
    if data is None:
        return None
    try:
        return dict(data["translated_files"])
    except (KeyError, TypeError):
        logger.warning("Malformed EPUB checkpoint in %s", storage_dir)
        return None


# ── PDF pipeline checkpoints (per page) ────────────────────────────


def save_pdf_page_progress(
    storage_dir: Path,
    page_index: int,
    translated_blocks: list[dict[str, Any]],
    total_pages: int,
) -> None:
    """Incrementally saves translated blocks for one PDF page.

    Reads the existing checkpoint, adds/updates the page entry, and
    writes back atomically.  Best-effort: logs and returns on error.

    Args:
        storage_dir: Task storage directory.
        page_index: Zero-based page index.
        translated_blocks: List of block dicts for the page.
        total_pages: Total number of pages in the PDF.
    """
    try:
        data = _read_checkpoint(storage_dir, _CHECKPOINT_PDF) or {
            "version": _VERSION,
            "total_pages": total_pages,
            "translated_pages": {},
        }
        data["translated_pages"][str(page_index)] = translated_blocks
        data["total_pages"] = total_pages
        _write_checkpoint(storage_dir, _CHECKPOINT_PDF, data)
    except Exception:
        logger.warning("Failed to save PDF checkpoint", exc_info=True)


def load_pdf_checkpoint(
    storage_dir: Path,
    expected_total_pages: int | None = None,
) -> dict[int, list[dict[str, Any]]] | None:
    """Loads PDF page checkpoint data.

    Args:
        storage_dir: Task storage directory.
        expected_total_pages: When provided, the checkpoint is discarded
            if its on-disk ``total_pages`` doesn't match (e.g. the source
            PDF was replaced with a different version between runs).

    Returns:
        dict mapping page_index (int) to list of block dicts, or None.
    """
    data = _read_checkpoint(storage_dir, _CHECKPOINT_PDF)
    if data is None:
        return None
    try:
        pages = data["translated_pages"]
        if (
            expected_total_pages is not None
            and data.get("total_pages") != expected_total_pages
        ):
            logger.warning(
                "PDF checkpoint total_pages mismatch in %s (on-disk=%s, "
                "expected=%s); discarding checkpoint",
                storage_dir,
                data.get("total_pages"),
                expected_total_pages,
            )
            return None
        return {int(k): v for k, v in pages.items()}
    except (KeyError, TypeError, ValueError):
        logger.warning("Malformed PDF checkpoint in %s", storage_dir)
        return None


# ── Dubbing pipeline checkpoints ──────────────────────────────────


def save_dubbing_checkpoint(
    storage_dir: Path,
    *,
    srt_text: str | None = None,
    translated_srt: str | None = None,
    voice_file: str | None = None,
    target_lang: str | None = None,
) -> None:
    """Saves dubbing pipeline checkpoint (incremental).

    Each step appends its result to the existing checkpoint data.

    Args:
        storage_dir: Persistent dubbing storage directory.
        srt_text: Raw SRT text from the STT step.
        translated_srt: Translated SRT text from the LLM step.
        voice_file: Filename of the synthesized voice audio in storage_dir.
        target_lang: Target language label for checkpoint validity check.
    """
    data = _read_checkpoint(storage_dir, _CHECKPOINT_DUBBING) or {
        "version": _VERSION,
    }
    if srt_text is not None:
        data["srt_text"] = srt_text
    if translated_srt is not None:
        data["translated_srt"] = translated_srt
    if voice_file is not None:
        data["voice_file"] = voice_file
    if target_lang is not None:
        data["target_lang"] = target_lang
    _write_checkpoint(storage_dir, _CHECKPOINT_DUBBING, data)


def load_dubbing_checkpoint(storage_dir: Path) -> dict[str, Any] | None:
    """Loads dubbing pipeline checkpoint.

    Returns:
        Dict with optional keys ``srt_text``, ``translated_srt``,
        ``voice_file``, or None if no valid checkpoint exists.
    """
    return _read_checkpoint(storage_dir, _CHECKPOINT_DUBBING)


# ── Office embedded-image checkpoints (per image) ─────────────────


def hash_office_image(image_bytes: bytes) -> str:
    """Returns the SHA256 hex digest of an image's bytes.

    Acts as both the cache key and the on-disk filename for the
    translated image, so identical images anywhere in any document
    naturally deduplicate.

    Args:
        image_bytes: Raw bytes of the original (untranslated) image.

    Returns:
        64-character lowercase hexadecimal digest.
    """
    return hashlib.sha256(image_bytes).hexdigest()


def _office_image_path(storage_dir: Path, image_hash: str) -> Path:
    """Returns the on-disk path for a cached translated image."""
    return storage_dir / _OFFICE_IMAGE_DIR_NAME / f"{image_hash}.bin"


def save_office_image_checkpoint(
    storage_dir: Path,
    image_hash: str,
    translated_bytes: bytes,
) -> None:
    """Persists a translated image's bytes keyed by the source hash.

    Atomic via tempfile + rename so a crash mid-write can't leave a
    half-written cache entry that future runs would silently reuse.
    Best-effort: any I/O error is logged and swallowed because cache
    failure must never abort an in-flight translation.

    Args:
        storage_dir: Task storage directory.
        image_hash: SHA256 hex digest of the original image bytes.
        translated_bytes: Rendered image bytes to cache.
    """
    target = _office_image_path(storage_dir, image_hash)
    image_dir = target.parent
    try:
        image_dir.mkdir(parents=True, exist_ok=True)
        fd, tmp_str = tempfile.mkstemp(dir=str(image_dir), suffix=".tmp")
        tmp_path = Path(tmp_str)
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(translated_bytes)
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise
        tmp_path.replace(target)
    except OSError:
        logger.warning(
            "Failed to write office image checkpoint for %s",
            image_hash,
            exc_info=True,
        )


def load_office_image_checkpoint(
    storage_dir: Path,
    image_hash: str,
) -> bytes | None:
    """Returns previously translated bytes for ``image_hash``, or ``None``.

    A missing or unreadable file is treated as a cache miss (logged
    once and the caller retranslates), never an error — corruption
    here is a defensible reason to redo work, not to abort the run.

    Args:
        storage_dir: Task storage directory.
        image_hash: SHA256 hex digest of the original image bytes.

    Returns:
        Translated image bytes if cached, otherwise ``None``.
    """
    target = _office_image_path(storage_dir, image_hash)
    if not target.exists():
        return None
    try:
        return target.read_bytes()
    except OSError:
        logger.warning("Corrupt office image checkpoint: %s", target)
        return None
