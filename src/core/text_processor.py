"""Text file processing engine for translating structured and plain text files.

Handles all supported text formats: .pdf, .txt, .md, .html, .htm, .xml, .rtf,
.json, .csv, .epub, .srt, .vtt, .ass, .ssa, .po, .pot, .xliff, .xlf,
.yaml, .yml, .properties, and .strings.
Each format uses a strategy appropriate for its structure — PDF extract-overlay,
plain text chunking, structured value extraction, subtitle entry extraction,
localization string extraction, or archive-based XHTML translation.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import re
import shutil
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from charset_normalizer import from_bytes as _detect_bytes

from src.constants.llm import (
    CONTENT_EPUB,
    CONTENT_HTML,
    CONTENT_LOCALIZATION,
    CONTENT_MARKDOWN,
    CONTENT_RTF,
    CONTENT_SUBTITLE,
    CONTENT_XML,
    TOKEN_BUDGET,
    get_content_type,
)
from src.core import llm_engine as _llm_engine
from src.core.checkpoint import (
    load_epub_checkpoint,
    load_text_checkpoint,
    save_epub_file_progress,
    save_text_batch,
)
from src.core.office_processor import _translate_doc_images, process_office_file
from src.utils.file_utils import is_file_encrypted
from src.utils.keyvalue_utils import (
    is_keyvalue_format,
    parse_keyvalue,
    serialize_keyvalue,
)
from src.utils.localization_utils import (
    is_localization_format,
    parse_localization,
    serialize_localization,
)
from src.utils.subtitle_utils import (
    is_subtitle_format,
    mirror_ass_alignment_for_rtl,
    parse_subtitle,
    serialize_subtitle,
)
from src.utils.text_utils import (
    AttrRecord,
    repair_html_tags,
    restore_html_attributes,
    restore_md_overhead,
    restore_rtf_overhead,
    restore_xml_overhead,
    strip_bom,
    strip_html_attributes,
    strip_md_overhead,
    strip_rtf_overhead,
    strip_xml_attributes,
    strip_xml_overhead,
)

if TYPE_CHECKING:
    from src.core.config import TranslationConfig

logger = logging.getLogger("text_processor")

# Programming-error exception types that ``translate_file`` re-raises
# unchanged instead of rebadging as ``TEXT_READ_ERROR``.  A bug in any
# dispatched processor (PDF, Office, EPUB, …) belongs in the log with
# its real traceback, not behind a misleading "could not read the text
# file" message in the UI.  Anything NOT in this tuple (yaml.YAMLError,
# lxml.etree.XMLSyntaxError, zipfile.BadZipFile, charset_normalizer
# surprises, …) is treated as a legitimate "file is corrupt" condition.
_BUG_EXCEPTIONS: tuple[type[BaseException], ...] = (
    AssertionError,
    AttributeError,
    TypeError,
    KeyError,
    IndexError,
    NameError,
    ImportError,
    NotImplementedError,
    RuntimeError,
)

# Maximum characters per chunk sent to the LLM
MAX_CHUNK_CHARS = 3000

# Formats that use plain text chunking (sent as-is, LLM preserves structure)
_PLAIN_FORMATS = {".txt", ".md", ".rst"}
_RTF_FORMAT = ".rtf"

# ``dir`` injection regexes for HTML / XHTML / EPUB content files.
_HTML_TAG_WITH_DIR_RE = re.compile(r"<html\b[^>]*\bdir\s*=", re.IGNORECASE)
_HTML_OPEN_TAG_RE = re.compile(r"<html\b([^>]*)>", re.IGNORECASE)
_BODY_TAG_WITH_DIR_RE = re.compile(r"<body\b[^>]*\bdir\s*=", re.IGNORECASE)
_BODY_OPEN_TAG_RE = re.compile(r"<body\b([^>]*)>", re.IGNORECASE)
# RTF document-direction control word lookup.
_RTF_RTLDOC_RE = re.compile(r"\\rtldoc\b")
_RTF_HEADER_RE = re.compile(r"\{\\rtf1[^{}]*")


def _inject_rtl_into_html(html_text: str) -> str:
    """Adds ``dir="rtl"`` to ``<html>`` and ``<body>`` when missing.

    Idempotent — already-marked tags are left alone so EPUB chapters
    that are RTL-by-source survive a translation round-trip without
    duplicate attributes.
    """
    if "<html" in html_text.lower() and not _HTML_TAG_WITH_DIR_RE.search(html_text):
        html_text = _HTML_OPEN_TAG_RE.sub(r'<html\1 dir="rtl">', html_text, count=1)
    if "<body" in html_text.lower() and not _BODY_TAG_WITH_DIR_RE.search(html_text):
        html_text = _BODY_OPEN_TAG_RE.sub(r'<body\1 dir="rtl">', html_text, count=1)
    return html_text


_OPF_SPINE_TAG_RE = re.compile(r"<spine\b([^>]*)>", re.IGNORECASE)
_OPF_SPINE_HAS_PPD_RE = re.compile(
    r"<spine\b[^>]*\bpage-progression-direction\s*=",
    re.IGNORECASE,
)


def _inject_rtl_into_opf(opf_xml: str) -> str:
    """Sets ``page-progression-direction="rtl"`` on the OPF ``<spine>``.

    Idempotent — leaves the attribute alone if it's already there
    (covers the source-was-RTL case).
    """
    if _OPF_SPINE_HAS_PPD_RE.search(opf_xml):
        return opf_xml
    return _OPF_SPINE_TAG_RE.sub(
        r'<spine\1 page-progression-direction="rtl">',
        opf_xml,
        count=1,
    )


def _get_epub_opf_path(zip_ref: zipfile.ZipFile) -> str:
    """Returns the OPF file path inside an EPUB, or ``""`` if missing."""
    try:
        container_xml = zip_ref.read("META-INF/container.xml").decode("utf-8")
    except KeyError:
        return ""
    try:
        container_root = ET.fromstring(container_xml)
    except ET.ParseError:
        return ""
    ns = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}
    rootfile_elem = container_root.find(".//c:rootfile", ns)
    if rootfile_elem is None:
        return ""
    return rootfile_elem.get("full-path", "") or ""


def _inject_rtl_into_rtf(rtf_text: str) -> str:
    r"""Inserts ``\rtldoc`` into the RTF header when not already present.

    ``\rtldoc`` flips the document-default reading direction so Word /
    LibreOffice render every paragraph as RTL unless an explicit
    ``\ltrpar`` overrides it.  Idempotent.
    """
    if _RTF_RTLDOC_RE.search(rtf_text):
        return rtf_text
    match = _RTF_HEADER_RE.search(rtf_text)
    if not match:
        return rtf_text
    insert_at = match.end()
    return rtf_text[:insert_at] + r"\rtldoc" + rtf_text[insert_at:]


def _apply_rtl_markup(text: str, content_type: str, target_lang: str) -> str:
    """Adds RTL direction markers to *text* when *target_lang* is RTL.

    Centralises the format-specific marker logic so every text-output
    path (HTML, XHTML, EPUB chapters, RTF) gets the same treatment.
    Returns *text* unchanged for non-RTL targets or unsupported formats.
    """
    from src.constants.languages import is_rtl_language  # noqa: PLC0415

    if not is_rtl_language(target_lang):
        return text
    if content_type in (CONTENT_HTML, CONTENT_EPUB):
        return _inject_rtl_into_html(text)
    if content_type == CONTENT_RTF:
        return _inject_rtl_into_rtf(text)
    return text


def _repair_and_restore_attrs(
    translated: str,
    original: str,
    attr_records: dict[int, AttrRecord],
) -> str:
    """Repairs missing HTML tags and restores stripped attributes.

    Applies two post-processing passes to a translated chunk:
    1. Repairs tags that the LLM may have dropped by comparing
       against the original pre-translation text.
    2. Re-injects non-translatable attributes that were stripped
       before translation to save tokens.

    Args:
        translated: The LLM-translated text chunk.
        original: The original chunk (after attribute stripping).
        attr_records: Attribute records from strip_html_attributes().

    Returns:
        str: Chunk with tags repaired and attributes restored.
    """
    repaired = repair_html_tags(original, translated)
    return restore_html_attributes(repaired, attr_records)


def translate_file(  # noqa: PLR0913, PLR0911, PLR0912, PLR0915
    file_path: Path,
    output_path: Path,
    target_lang: str,
    src_lang: str = "",
    progress_callback: Callable[[int], None] | None = None,
    glossary_entries: list[tuple[int, str, str]] | None = None,
    cancel_check: Callable[[], bool] | None = None,
    checkpoint_dir: Path | None = None,
    config: TranslationConfig | None = None,
    *,
    provider: str | None = None,
    model: str | None = None,
) -> bool:
    """Translates a text file and writes the result to output_path.

    Dispatches to format-specific handlers based on file extension.

    **Atomic output**: when ``checkpoint_dir`` is provided, the
    dispatched processor writes to a hidden ``_partial<ext>`` file
    inside the task's storage directory.  Only after the processor
    returns success is the partial file moved to ``output_path`` —
    so the user's output folder only ever contains complete files,
    never half-translated artefacts from interrupted or failed
    runs.  Crashes, cancellations, and exceptions leave the in-
    progress bytes in the (internal) storage dir where checkpoints
    live, and a retry overwrites them on the next inject step.

    Args:
        file_path: Path to the source file.
        output_path: Path to write the translated file.
        target_lang: Target language name.
        src_lang: Source language name.
        progress_callback: Called with 0-100 progress percentage.
        glossary_entries: Optional glossary entries for translation.
        cancel_check: Returns True if the task was cancelled.
        checkpoint_dir: Directory for saving/loading checkpoints.
        config: Optional TranslationConfig snapshot; forwarded to sub-processors.
        provider: Optional LLM provider override.
        model: Optional LLM model override.

    Returns:
        bool: True on success, False on failure.
    """
    suffix = file_path.suffix.lower()

    # Early check: password-protected / DRM-encrypted files
    if is_file_encrypted(file_path):
        raise ValueError("PASSWORD_PROTECTED")

    # Atomic output: dispatch writes to a partial file inside the task
    # storage dir, and we move it to ``output_path`` only on success.
    # ``checkpoint_dir`` is None when callers don't supply a per-task
    # storage area (e.g. some test paths) — in that case we fall back
    # to the legacy "write directly to output_path" behaviour.
    if checkpoint_dir is not None:
        dispatch_output = checkpoint_dir / f"_partial{output_path.suffix}"
    else:
        dispatch_output = output_path

    try:
        success = _dispatch_translate(
            suffix,
            file_path,
            dispatch_output,
            target_lang,
            src_lang,
            progress_callback,
            glossary_entries,
            cancel_check,
            checkpoint_dir,
            config,
            provider,
            model,
        )
    except ValueError:
        # Domain exceptions (AUTH_ERROR, QUOTA_ERROR, PASSWORD_PROTECTED,
        # CANCELLED, TEXT_READ_ERROR, etc.) carry actionable tag
        # strings the UI uses to route the user to relevant help.
        # Propagate untouched.  Leave the partial file in storage so
        # a future retry's checkpoints (text batches, image cache)
        # line up against its content; the next inject step rewrites it.
        raise
    except _BUG_EXCEPTIONS:
        # Programming-error exception types almost certainly indicate a
        # bug in a dispatched processor (PDF, Office, EPUB, …) rather
        # than a corrupt-file condition.  Rebadging them as
        # ``TEXT_READ_ERROR`` would hide the real cause behind a
        # misleading "could not read the text file" message in the UI;
        # the translator pipeline's outer ``except Exception`` maps
        # them to ``ERR_UNKNOWN`` with a real traceback in ``app.log``.
        raise
    except Exception as e:
        # Everything else — yaml.YAMLError, lxml.etree.XMLSyntaxError,
        # zipfile.BadZipFile, charset_normalizer surprises, etc. — is
        # a legitimate "file is corrupt or unreadable" case.  Map to
        # the user-facing TEXT_READ_ERROR tag.
        logger.error(
            "Text processing error for %s: %s",
            file_path.name,
            e,
        )
        raise ValueError("TEXT_READ_ERROR") from e

    # Atomic publish: move the completed partial file into the user's
    # output directory.  If dispatch was already writing directly to
    # ``output_path`` (no checkpoint_dir), there's nothing to move.
    if success and checkpoint_dir is not None and dispatch_output.exists():
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(dispatch_output), str(output_path))
    return success


def _dispatch_translate(  # noqa: PLR0913, PLR0911
    suffix: str,
    file_path: Path,
    output_path: Path,
    target_lang: str,
    src_lang: str,
    progress_callback: Callable[[int], None] | None,
    glossary_entries: list[tuple[int, str, str]] | None,
    cancel_check: Callable[[], bool] | None,
    checkpoint_dir: Path | None,
    config: TranslationConfig | None,
    provider: str | None,
    model: str | None,
) -> bool:
    """Routes a file to the right format-specific processor.

    Extracted from ``translate_file`` so the wrapper around it can
    own the atomic-output behaviour (temp-file dispatch + final move)
    in one place, instead of repeating the swap at every return
    statement of the dispatch table.
    """
    if suffix == ".pdf":
        from src.core.pdf_processor import process_pdf_file  # noqa: PLC0415

        return process_pdf_file(
            file_path,
            output_path,
            target_lang,
            src_lang,
            progress_callback,
            glossary_entries,
            cancel_check,
            checkpoint_dir=checkpoint_dir,
            config=config,
            provider=provider,
            model=model,
        )
    if suffix in {
        ".docx",
        ".xlsx",
        ".pptx",
        ".doc",
        ".xls",
        ".ppt",
        ".odt",
        ".ods",
        ".odp",
    }:
        return process_office_file(
            file_path,
            output_path,
            target_lang,
            src_lang,
            progress_callback,
            glossary_entries,
            cancel_check,
            checkpoint_dir=checkpoint_dir,
            config=config,
            provider=provider,
            model=model,
        )
    if suffix == ".epub":
        return _process_epub(
            file_path,
            output_path,
            target_lang,
            src_lang,
            progress_callback,
            glossary_entries,
            cancel_check,
            checkpoint_dir=checkpoint_dir,
            provider=provider,
            model=model,
        )
    if suffix == ".json":
        return _process_json(
            file_path,
            output_path,
            target_lang,
            src_lang,
            progress_callback,
            glossary_entries,
            cancel_check,
            checkpoint_dir=checkpoint_dir,
            provider=provider,
            model=model,
        )
    if suffix == ".csv":
        return _process_csv(
            file_path,
            output_path,
            target_lang,
            src_lang,
            progress_callback,
            glossary_entries,
            cancel_check,
            checkpoint_dir=checkpoint_dir,
            provider=provider,
            model=model,
        )
    if is_subtitle_format(suffix):
        return _process_subtitle(
            file_path,
            output_path,
            target_lang,
            src_lang,
            progress_callback,
            glossary_entries,
            cancel_check,
            checkpoint_dir=checkpoint_dir,
            provider=provider,
            model=model,
        )
    if is_localization_format(suffix):
        return _process_localization(
            file_path,
            output_path,
            target_lang,
            src_lang,
            progress_callback,
            glossary_entries,
            cancel_check,
            checkpoint_dir=checkpoint_dir,
            provider=provider,
            model=model,
        )
    if is_keyvalue_format(suffix):
        return _process_keyvalue(
            file_path,
            output_path,
            target_lang,
            src_lang,
            progress_callback,
            glossary_entries,
            cancel_check,
            checkpoint_dir=checkpoint_dir,
            provider=provider,
            model=model,
        )
    # .txt, .md, .html, .htm, .xml, .rtf — chunked text approach
    return _process_plain(
        file_path,
        output_path,
        target_lang,
        src_lang,
        progress_callback,
        glossary_entries,
        cancel_check,
        checkpoint_dir=checkpoint_dir,
        provider=provider,
        model=model,
    )


# ---------------------------------------------------------------------------
# File reading
# ---------------------------------------------------------------------------


def _read_file(path: Path) -> str:
    """Reads a text file, detecting encoding automatically.

    Tries UTF-8 first (fast path for the vast majority of files).
    On failure, reads raw bytes and uses ``charset_normalizer`` to
    detect the actual encoding (Shift-JIS, GB2312, EUC-KR, etc.),
    falling back to latin-1 as a last resort.

    Args:
        path: Path to the file.

    Returns:
        str: The file content.

    Raises:
        ValueError: If the file cannot be read.
    """
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raw = path.read_bytes()
        detected_encoding = _detect_encoding(raw)
        logger.warning(
            "UTF-8 decode failed for %s, detected %s",
            path.name,
            detected_encoding,
        )
        content = raw.decode(detected_encoding)
    return strip_bom(content)


def _detect_encoding(data: bytes) -> str:
    """Detects the encoding of raw bytes via charset_normalizer.

    Falls back to latin-1 if detection fails.

    Args:
        data: Raw file bytes.

    Returns:
        Detected encoding name (e.g. "shift_jis", "gb2312").
    """
    result = _detect_bytes(data).best()
    if result is not None:
        return result.encoding
    return "latin-1"


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------


def _join_with_separators(parts: list[str], separators: list[str]) -> str:
    """Joins text parts using the corresponding separator between each pair.

    Args:
        parts: Text segments to join.
        separators: Separator strings; ``separators[i]`` is placed
            between ``parts[i]`` and ``parts[i+1]``.

    Returns:
        str: Reassembled text with original separators preserved.
    """
    if not parts:
        return ""
    result = [parts[0]]
    for sep, part in zip(separators, parts[1:], strict=False):
        result.append(sep)
        result.append(part)
    return "".join(result)


def _chunk_text(
    content: str,
    separator: str,
    max_chars: int = MAX_CHUNK_CHARS,
) -> tuple[list[str], list[str]]:
    r"""Splits content into chunks by separator, respecting max size.

    Uses ``re.split`` with a capturing group to preserve the actual
    separator runs (e.g. ``\\n\\n\\n\\n`` stays as-is rather than
    being normalised to ``\\n\\n``).

    Args:
        content: The full text content.
        separator: The delimiter to split on (e.g. "\\n\\n").
        max_chars: Maximum characters per chunk.

    Returns:
        tuple[list[str], list[str]]: ``(chunks, between_seps)`` where
            ``between_seps[i]`` is the original separator string between
            ``chunks[i]`` and ``chunks[i+1]``.
    """
    # Split preserving actual separator runs
    parts = re.split(f"({re.escape(separator)}+)", content)
    text_parts = parts[::2]  # text segments
    sep_parts = parts[1::2]  # actual separators between segments

    chunks: list[str] = []
    between_seps: list[str] = []
    current_texts: list[str] = []
    current_inner_seps: list[str] = []
    current_len = 0

    for i, seg in enumerate(text_parts):
        seg_len = len(seg) + len(separator)
        # If adding this segment would exceed limit, flush current
        if current_texts and (current_len + seg_len > max_chars):
            chunks.append(_join_with_separators(current_texts, current_inner_seps))
            # The separator between old chunk and new chunk
            between_seps.append(sep_parts[i - 1])
            current_texts = []
            current_inner_seps = []
            current_len = 0
        elif current_texts and i > 0:
            # This separator is internal to the current chunk
            current_inner_seps.append(sep_parts[i - 1])
        current_texts.append(seg)
        current_len += seg_len

    # Flush remaining
    if current_texts:
        chunks.append(_join_with_separators(current_texts, current_inner_seps))

    # Filter out empty/whitespace-only chunks, merging adjacent separators
    filtered: list[str] = []
    filtered_seps: list[str] = []
    for i, chunk in enumerate(chunks):
        if chunk.strip():
            if filtered:
                # Collect the separator bridging to this chunk.
                # If previous chunks were dropped, merge all skipped separators.
                filtered_seps.append(between_seps[i - 1] if i > 0 else separator)
            filtered.append(chunk)

    return filtered, filtered_seps


def _get_separator(suffix: str) -> str:
    """Returns the appropriate chunk separator for a file format.

    Args:
        suffix: Lowercase file extension (e.g. ".txt").

    Returns:
        str: The separator string.
    """
    if suffix in _PLAIN_FORMATS:
        return "\n\n"  # Paragraphs
    if suffix == _RTF_FORMAT:
        return "\\par"  # RTF paragraph marker
    # .html, .htm, .xml — split by lines
    return "\n"


# ---------------------------------------------------------------------------
# Subtitle translation
# ---------------------------------------------------------------------------


def _process_subtitle(  # noqa: PLR0913
    file_path: Path,
    output_path: Path,
    target_lang: str,
    src_lang: str,
    progress_callback: Callable[[int], None] | None,
    glossary_entries: list[tuple[int, str, str]] | None,
    cancel_check: Callable[[], bool] | None,
    checkpoint_dir: Path | None = None,
    *,
    provider: str | None = None,
    model: str | None = None,
) -> bool:
    """Translates a subtitle file (.srt, .vtt, .ass, .ssa).

    Parses the file into entries, translates only the dialogue text via
    ``translate_batch()``, and reconstructs the file with the original
    timing and formatting intact.

    Args:
        file_path: Path to the source subtitle file.
        output_path: Path to write the translated file.
        target_lang: Target language name.
        src_lang: Source language name, or empty for auto-detect.
        progress_callback: Called with 0-100 progress percentage.
        glossary_entries: Optional glossary entries for the LLM.
        cancel_check: Returns True if the task was cancelled.
        checkpoint_dir: Directory for saving/loading checkpoints.
        provider: Optional LLM provider override.
        model: Optional LLM model override.

    Returns:
        bool: True on success, False if cancelled.
    """
    content = _read_file(file_path)
    suffix = file_path.suffix.lower()

    # Parse into structured entries + format-specific data
    entries, format_data = parse_subtitle(content, suffix)

    if not entries:
        # No translatable entries — copy file as-is
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")
        if progress_callback:
            progress_callback(100)
        return True

    # Extract translatable dialogue text
    texts = [e.text for e in entries]

    # Translate using the batch pipeline (same as JSON/CSV)
    translated = _llm_engine.translate_batch(
        texts,
        target_lang,
        src_lang,
        progress_callback,
        glossary_entries,
        cancel_check,
        checkpoint_dir=checkpoint_dir,
        content_type=CONTENT_SUBTITLE,
        provider=provider,
        model=model,
    )
    if translated is None:
        return False  # Cancelled

    # Inject translations back into entries
    for i, entry in enumerate(entries):
        entry.text = translated[i]

    # Serialize back to the original format
    result = serialize_subtitle(entries, format_data, suffix)

    # ASS/SSA: mirror left/right alignment codes when target is RTL.
    if suffix in (".ass", ".ssa"):
        from src.constants.languages import is_rtl_language  # noqa: PLC0415

        if is_rtl_language(target_lang):
            result = mirror_ass_alignment_for_rtl(result)

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(result, encoding="utf-8")
    except OSError as e:
        logger.error(
            "Failed to write subtitle output %s: %s",
            output_path,
            e,
        )
        raise ValueError("TEXT_WRITE_ERROR") from e
    return True


# ---------------------------------------------------------------------------
# Localization file translation
# ---------------------------------------------------------------------------


def _process_localization(  # noqa: PLR0913
    file_path: Path,
    output_path: Path,
    target_lang: str,
    src_lang: str,
    progress_callback: Callable[[int], None] | None,
    glossary_entries: list[tuple[int, str, str]] | None,
    cancel_check: Callable[[], bool] | None,
    checkpoint_dir: Path | None = None,
    *,
    provider: str | None = None,
    model: str | None = None,
) -> bool:
    """Translates a localization file (.po, .pot, .xliff, .xlf).

    Parses the file into entries, translates source strings via
    ``translate_batch()``, and reconstructs the file preserving all
    metadata, comments, and structure.  For PO files with plural forms,
    both singular and plural source texts are translated.

    Args:
        file_path: Path to the source localization file.
        output_path: Path to write the translated file.
        target_lang: Target language name.
        src_lang: Source language name, or empty for auto-detect.
        progress_callback: Called with 0-100 progress percentage.
        glossary_entries: Optional glossary entries for the LLM.
        cancel_check: Returns True if the task was cancelled.
        checkpoint_dir: Directory for saving/loading checkpoints.
        provider: Optional LLM provider override.
        model: Optional LLM model override.

    Returns:
        bool: True on success, False if cancelled.
    """
    content = _read_file(file_path)
    suffix = file_path.suffix.lower()

    # Parse into structured entries + format-specific data
    entries, format_data = parse_localization(content, suffix)

    if not entries:
        # No translatable entries — copy file as-is
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")
        if progress_callback:
            progress_callback(100)
        return True

    # Build list of texts to translate:
    # - All msgid values (singular source strings)
    # - Append msgid_plural values for PO entries with plural forms
    texts = [e.msgid for e in entries]

    plural_indices: list[int] = []
    for i, entry in enumerate(entries):
        if entry.metadata.get("msgid_plural"):
            texts.append(entry.metadata["msgid_plural"])
            plural_indices.append(i)

    # Translate using the batch pipeline
    translated = _llm_engine.translate_batch(
        texts,
        target_lang,
        src_lang,
        progress_callback,
        glossary_entries,
        cancel_check,
        checkpoint_dir=checkpoint_dir,
        content_type=CONTENT_LOCALIZATION,
        provider=provider,
        model=model,
    )
    if translated is None:
        return False  # Cancelled

    # Inject singular translations
    for i, entry in enumerate(entries):
        entry.msgstr = translated[i]

    # Inject plural translations
    plural_offset = len(entries)
    for j, entry_idx in enumerate(plural_indices):
        entry = entries[entry_idx]
        entry.metadata["msgstr_plural"] = {
            0: translated[entry_idx],
            1: translated[plural_offset + j],
        }

    # Serialize back to the original format
    result = serialize_localization(entries, format_data, suffix)

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(result, encoding="utf-8")
    except OSError as e:
        logger.error(
            "Failed to write localization output %s: %s",
            output_path,
            e,
        )
        raise ValueError("TEXT_WRITE_ERROR") from e
    return True


# ---------------------------------------------------------------------------
# Key-value format translation (.yaml, .yml, .properties, .strings)
# ---------------------------------------------------------------------------


def _process_keyvalue(  # noqa: PLR0913
    file_path: Path,
    output_path: Path,
    target_lang: str,
    src_lang: str,
    progress_callback: Callable[[int], None] | None,
    glossary_entries: list[tuple[int, str, str]] | None,
    cancel_check: Callable[[], bool] | None,
    checkpoint_dir: Path | None = None,
    *,
    provider: str | None = None,
    model: str | None = None,
) -> bool:
    """Translates a key-value file (.yaml, .yml, .properties, .strings).

    Parses the file into entries, translates values via
    ``translate_batch()``, and reconstructs the file preserving
    structure, comments, and key ordering.

    Args:
        file_path: Path to the source key-value file.
        output_path: Path to write the translated file.
        target_lang: Target language name.
        src_lang: Source language name, or empty for auto-detect.
        progress_callback: Called with 0-100 progress percentage.
        glossary_entries: Optional glossary entries for the LLM.
        cancel_check: Returns True if the task was cancelled.
        checkpoint_dir: Directory for saving/loading checkpoints.
        provider: Optional LLM provider override.
        model: Optional LLM model override.

    Returns:
        bool: True on success, False if cancelled.
    """
    content = _read_file(file_path)
    suffix = file_path.suffix.lower()

    # Parse into structured entries + format-specific data
    entries, format_data = parse_keyvalue(content, suffix)

    if not entries:
        # No translatable entries — copy file as-is
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")
        if progress_callback:
            progress_callback(100)
        return True

    # Extract translatable texts
    texts = [e.msgid for e in entries]

    # Translate using the batch pipeline
    translated = _llm_engine.translate_batch(
        texts,
        target_lang,
        src_lang,
        progress_callback,
        glossary_entries,
        cancel_check,
        checkpoint_dir=checkpoint_dir,
        content_type=CONTENT_LOCALIZATION,
        provider=provider,
        model=model,
    )
    if translated is None:
        return False  # Cancelled

    # Inject translations
    for i, entry in enumerate(entries):
        entry.msgstr = translated[i]

    # Serialize back to the original format
    result = serialize_keyvalue(entries, format_data, suffix)

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(result, encoding="utf-8")
    except OSError as e:
        logger.error(
            "Failed to write key-value output %s: %s",
            output_path,
            e,
        )
        raise ValueError("TEXT_WRITE_ERROR") from e
    return True


# ---------------------------------------------------------------------------
# Plain text / markup translation
# ---------------------------------------------------------------------------


def _process_plain(  # noqa: PLR0913, PLR0912, PLR0915
    file_path: Path,
    output_path: Path,
    target_lang: str,
    src_lang: str,
    progress_callback: Callable[[int], None] | None,
    glossary_entries: list[tuple[int, str, str]] | None,
    cancel_check: Callable[[], bool] | None,
    checkpoint_dir: Path | None = None,
    *,
    provider: str | None = None,
    model: str | None = None,
) -> bool:
    """Translates plain text, markdown, HTML, XML, and RTF files.

    Reads the file, chunks it by an appropriate separator, translates
    each chunk via the LLM, and writes the concatenated result.

    Args:
        file_path: Source file path.
        output_path: Output file path.
        target_lang: Target language.
        src_lang: Source language.
        progress_callback: Progress reporter (0-100).
        glossary_entries: Optional glossary.
        cancel_check: Cancellation checker.
        checkpoint_dir: Directory for saving/loading checkpoints.
        provider: Optional LLM provider override.
        model: Optional LLM model override.

    Returns:
        bool: True on success.
    """
    content = _read_file(file_path)
    suffix = file_path.suffix.lower()
    separator = _get_separator(suffix)
    chunks, chunk_seps = _chunk_text(content, separator)

    if not chunks:
        # Empty file — just copy
        output_path.write_text(content, encoding="utf-8")
        return True

    # Translate chunks with format-specific prompt
    content_type = get_content_type(suffix)

    # Strip non-translatable content before sending to LLM
    attr_records_per_chunk: list[dict[int, AttrRecord]] | None = None
    original_stripped: list[str] | None = None
    xml_overhead_per_chunk: list[list[str]] | None = None
    rtf_overhead_per_chunk: list[list[str]] | None = None
    md_overhead_per_chunk: list[list[str]] | None = None

    if content_type in (CONTENT_HTML, CONTENT_EPUB):
        original_stripped = []
        attr_records_per_chunk = []
        stripped_chunks: list[str] = []
        for chunk in chunks:
            stripped, records = strip_html_attributes(chunk)
            stripped_chunks.append(stripped)
            original_stripped.append(stripped)
            attr_records_per_chunk.append(records)
        translate_input = stripped_chunks

    elif content_type == CONTENT_MARKDOWN:
        # Strip Markdown URLs, then embedded HTML attributes
        original_stripped = []
        attr_records_per_chunk = []
        md_overhead_per_chunk = []
        stripped_chunks = []
        for chunk in chunks:
            md_stripped, md_recs = strip_md_overhead(chunk)
            md_overhead_per_chunk.append(md_recs)
            html_stripped, html_recs = strip_html_attributes(md_stripped)
            stripped_chunks.append(html_stripped)
            original_stripped.append(html_stripped)
            attr_records_per_chunk.append(html_recs)
        translate_input = stripped_chunks

    elif content_type == CONTENT_XML:
        # Strip overhead (PIs, comments, CDATA markers) then all attributes
        original_stripped = []
        attr_records_per_chunk = []
        xml_overhead_per_chunk = []
        stripped_chunks = []
        for chunk in chunks:
            overhead_stripped, overhead_recs = strip_xml_overhead(chunk)
            xml_overhead_per_chunk.append(overhead_recs)
            attr_stripped, attr_recs = strip_xml_attributes(overhead_stripped)
            stripped_chunks.append(attr_stripped)
            original_stripped.append(attr_stripped)
            attr_records_per_chunk.append(attr_recs)
        translate_input = stripped_chunks

    elif content_type == CONTENT_RTF:
        # Strip control words, symbols, braces, and Unicode escapes
        rtf_overhead_per_chunk = []
        stripped_chunks = []
        for chunk in chunks:
            stripped, recs = strip_rtf_overhead(chunk)
            stripped_chunks.append(stripped)
            rtf_overhead_per_chunk.append(recs)
        translate_input = stripped_chunks

    else:
        translate_input = chunks

    translated = _translate_chunks(
        translate_input,
        target_lang,
        src_lang,
        progress_callback,
        glossary_entries,
        cancel_check,
        content_type=content_type,
        checkpoint_dir=checkpoint_dir,
        provider=provider,
        model=model,
    )
    if translated is None:
        return False  # Cancelled

    # Post-process: repair missing tags and restore stripped content
    if content_type in (CONTENT_HTML, CONTENT_EPUB):
        for i in range(len(translated)):
            translated[i] = _repair_and_restore_attrs(
                translated[i],
                original_stripped[i],
                attr_records_per_chunk[i],
            )
    elif content_type == CONTENT_MARKDOWN and md_overhead_per_chunk is not None:
        for i in range(len(translated)):
            translated[i] = _repair_and_restore_attrs(
                translated[i],
                original_stripped[i],
                attr_records_per_chunk[i],
            )
            translated[i] = restore_md_overhead(
                translated[i],
                md_overhead_per_chunk[i],
            )
    elif content_type == CONTENT_XML and original_stripped is not None:
        for i in range(len(translated)):
            translated[i] = _repair_and_restore_attrs(
                translated[i],
                original_stripped[i],
                attr_records_per_chunk[i],
            )
            translated[i] = restore_xml_overhead(
                translated[i],
                xml_overhead_per_chunk[i],
            )
    elif content_type == CONTENT_RTF and rtf_overhead_per_chunk is not None:
        for i in range(len(translated)):
            translated[i] = restore_rtf_overhead(
                translated[i],
                rtf_overhead_per_chunk[i],
            )

    # Reassemble with the same separator
    result = _join_with_separators(translated, chunk_seps)

    # Inject RTL direction markers when target is Arabic / Hebrew / Persian.
    result = _apply_rtl_markup(result, content_type, target_lang)

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(result, encoding="utf-8")
    except OSError as e:
        logger.error("Failed to write output %s: %s", output_path, e)
        raise ValueError("TEXT_WRITE_ERROR") from e

    return True


# ---------------------------------------------------------------------------
# Chunk translation with progress and cancellation
# ---------------------------------------------------------------------------


def _translate_chunks(  # noqa: PLR0913
    chunks: list[str],
    target_lang: str,
    src_lang: str,
    progress_callback: Callable[[int], None] | None,
    glossary_entries: list[tuple[int, str, str]] | None,
    cancel_check: Callable[[], bool] | None,
    content_type: str = "plain_text",
    checkpoint_dir: Path | None = None,
    *,
    provider: str | None = None,
    model: str | None = None,
) -> list[str] | None:
    """Translates a list of text chunks via the LLM.

    Uncached chunks are grouped into token-budget sub-batches and
    translated one sub-batch at a time.  Checkpoints are saved after
    each successful sub-batch so progress is preserved even if the
    LLM fails partway through.

    On resume, previously-translated chunks are loaded from the
    checkpoint file and skipped.

    Args:
        chunks: Text chunks to translate.
        target_lang: Target language.
        src_lang: Source language.
        progress_callback: Progress reporter (0-100).
        glossary_entries: Optional glossary.
        cancel_check: Returns True if cancelled.
        content_type: Format type for prompt selection.
        checkpoint_dir: Directory for saving/loading checkpoints.
        provider: Optional LLM provider override.
        model: Optional LLM model override.

    Returns:
        list[str]: Translated chunks, or None if cancelled.
    """
    total = len(chunks)

    # Check cancellation before starting
    if cancel_check and cancel_check():
        return None

    # Load previously-translated chunks from checkpoint
    existing: dict[int, str] = {}
    if checkpoint_dir:
        existing = load_text_checkpoint(checkpoint_dir) or {}

    # Pre-populate results with originals as fallback
    translated: list[str] = list(chunks)
    for i in existing:
        if i < total:
            translated[i] = existing[i]

    # Collect uncached chunks with their original indices
    uncached: list[tuple[int, str]] = [
        (i, chunks[i]) for i in range(total) if i not in existing
    ]

    if not uncached:
        # All chunks were cached
        if progress_callback:
            progress_callback(100)
        return translated

    # Split uncached texts into token-budget sub-batches and iterate
    # here so that checkpoints are saved after each successful batch.
    uncached_texts = [text for _, text in uncached]
    sub_batches = _llm_engine._split_by_token_budget(uncached_texts, TOKEN_BUDGET)

    cached_count = total - len(uncached)
    done_uncached = 0

    for batch_texts in sub_batches:
        # Check cancellation between sub-batches
        if cancel_check and cancel_check():
            return None

        batch_results = _llm_engine.translate_text(
            batch_texts,
            target_lang,
            src_lang,
            glossary_entries=glossary_entries,
            content_type=content_type,
            provider=provider,
            model=model,
        )

        # Map results back to original indices
        batch_checkpoint: dict[int, str] = {}
        for j, result_text in enumerate(batch_results):
            orig_idx = uncached[done_uncached + j][0]
            translated[orig_idx] = result_text
            batch_checkpoint[orig_idx] = result_text

        # Save all chunks from this sub-batch in a single write
        if checkpoint_dir and batch_checkpoint:
            save_text_batch(checkpoint_dir, batch_checkpoint, total)

        done_uncached += len(batch_texts)

        if progress_callback:
            overall = int(
                ((cached_count + done_uncached) / total) * 100,
            )
            progress_callback(overall)

    return translated


# ---------------------------------------------------------------------------
# JSON translation
# ---------------------------------------------------------------------------


def _extract_json_strings(
    obj: dict | list | str | int | float | bool | None,
    path: tuple[str | int, ...] = (),
    result: list[tuple[tuple[str | int, ...], str]] | None = None,
) -> list[tuple[tuple[str | int, ...], str]]:
    """Recursively extracts all string values from a JSON object.

    Args:
        obj: The JSON object (dict, list, or primitive).
        path: Current key path as a tuple.
        result: Accumulator for (path, value) pairs.

    Returns:
        list: List of (path_tuple, string_value) pairs.
    """
    if result is None:
        result = []

    if isinstance(obj, dict):
        for key, val in obj.items():
            _extract_json_strings(val, (*path, key), result)
    elif isinstance(obj, list):
        for idx, val in enumerate(obj):
            _extract_json_strings(val, (*path, idx), result)
    elif isinstance(obj, str) and obj.strip():
        result.append((path, obj))

    return result


def _inject_json_strings(
    obj: Any,  # noqa: ANN401
    translations: dict[tuple[str | int, ...], str],
) -> Any:  # noqa: ANN401
    """Reconstructs a JSON object with translated string values.

    Args:
        obj: The original JSON object.
        translations: Mapping from path tuple to translated string.

    Returns:
        The reconstructed JSON with translations applied.
    """
    return _inject_recursive(obj, translations, ())


def _inject_recursive(
    obj: Any,  # noqa: ANN401
    translations: dict[tuple[str | int, ...], str],
    path: tuple[str | int, ...],
) -> Any:  # noqa: ANN401
    """Recursively walks JSON and replaces strings with translations.

    Args:
        obj: Current node.
        translations: Path-to-translation mapping.
        path: Current path.

    Returns:
        Reconstructed node.
    """
    if isinstance(obj, dict):
        return {
            key: _inject_recursive(val, translations, (*path, key))
            for key, val in obj.items()
        }
    if isinstance(obj, list):
        return [
            _inject_recursive(val, translations, (*path, idx))
            for idx, val in enumerate(obj)
        ]
    if isinstance(obj, str) and path in translations:
        return translations[path]
    return obj


def _process_json(  # noqa: PLR0913
    file_path: Path,
    output_path: Path,
    target_lang: str,
    src_lang: str,
    progress_callback: Callable[[int], None] | None,
    glossary_entries: list[tuple[int, str, str]] | None,
    cancel_check: Callable[[], bool] | None,
    checkpoint_dir: Path | None = None,
    *,
    provider: str | None = None,
    model: str | None = None,
) -> bool:
    """Translates a JSON file by extracting and translating string values.

    Keys and structure are preserved exactly. Only string values
    are translated.

    Args:
        file_path: Source JSON file.
        output_path: Output file path.
        target_lang: Target language.
        src_lang: Source language.
        progress_callback: Progress reporter (0-100).
        glossary_entries: Optional glossary.
        cancel_check: Cancellation checker.
        checkpoint_dir: Directory for saving/loading checkpoints.
        provider: Optional LLM provider override.
        model: Optional LLM model override.

    Returns:
        bool: True on success.
    """
    content = _read_file(file_path)
    data = json.loads(content)

    # Extract all translatable string values
    pairs = _extract_json_strings(data)
    if not pairs:
        # No translatable strings — write as-is
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")
        return True

    paths, values = zip(*pairs, strict=True)

    # Translate using regular text mode (structure handled programmatically)
    translated_values = _llm_engine.translate_batch(
        list(values),
        target_lang,
        src_lang,
        progress_callback,
        glossary_entries,
        cancel_check,
        checkpoint_dir=checkpoint_dir,
        provider=provider,
        model=model,
    )
    if translated_values is None:
        return False  # Cancelled

    # Reconstruct JSON with translations
    translations = dict(zip(paths, translated_values, strict=True))
    translated_data = _inject_json_strings(data, translations)

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(
                translated_data,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    except OSError as e:
        logger.error(
            "Failed to write JSON output %s: %s",
            output_path,
            e,
        )
        raise ValueError("TEXT_WRITE_ERROR") from e

    return True


# ---------------------------------------------------------------------------
# CSV translation
# ---------------------------------------------------------------------------


def _process_csv(  # noqa: PLR0913
    file_path: Path,
    output_path: Path,
    target_lang: str,
    src_lang: str,
    progress_callback: Callable[[int], None] | None,
    glossary_entries: list[tuple[int, str, str]] | None,
    cancel_check: Callable[[], bool] | None,
    checkpoint_dir: Path | None = None,
    *,
    provider: str | None = None,
    model: str | None = None,
) -> bool:
    """Translates a CSV file by extracting and translating cell values.

    Structure (rows, columns, delimiters) is preserved exactly.

    Args:
        file_path: Source CSV file.
        output_path: Output file path.
        target_lang: Target language.
        src_lang: Source language.
        progress_callback: Progress reporter (0-100).
        glossary_entries: Optional glossary.
        cancel_check: Cancellation checker.
        checkpoint_dir: Directory for saving/loading checkpoints.
        provider: Optional LLM provider override.
        model: Optional LLM model override.

    Returns:
        bool: True on success.
    """
    content = _read_file(file_path)

    # Detect dialect for faithful reconstruction
    try:
        dialect = csv.Sniffer().sniff(content[:8192])
    except csv.Error:
        dialect = csv.excel

    reader = csv.reader(io.StringIO(content), dialect=dialect)
    rows = list(reader)

    if not rows:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("", encoding="utf-8")
        return True

    # Collect all non-empty cell values with their positions
    cell_map: list[tuple[int, int, str]] = []
    for r_idx, row in enumerate(rows):
        for c_idx, cell in enumerate(row):
            if cell.strip():
                cell_map.append((r_idx, c_idx, cell))

    if not cell_map:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")
        return True

    values = [cell for _, _, cell in cell_map]

    # Translate all cell values
    translated_values = _llm_engine.translate_batch(
        values,
        target_lang,
        src_lang,
        progress_callback,
        glossary_entries,
        cancel_check,
        checkpoint_dir=checkpoint_dir,
        provider=provider,
        model=model,
    )
    if translated_values is None:
        return False  # Cancelled

    # Inject translations back into the row structure
    for idx, (r_idx, c_idx, _) in enumerate(cell_map):
        rows[r_idx][c_idx] = translated_values[idx]

    # Write output
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        buf = io.StringIO()
        writer = csv.writer(buf, dialect=dialect)
        writer.writerows(rows)
        output_path.write_text(buf.getvalue(), encoding="utf-8")
    except OSError as e:
        logger.error(
            "Failed to write CSV output %s: %s",
            output_path,
            e,
        )
        raise ValueError("TEXT_WRITE_ERROR") from e

    return True


# ---------------------------------------------------------------------------
# EPUB translation
# ---------------------------------------------------------------------------


def _get_epub_content_files(  # noqa: PLR0912
    zip_ref: zipfile.ZipFile,
) -> list[str]:
    """Discovers translatable XHTML content files in an EPUB archive.

    Parses META-INF/container.xml to find the OPF file, then parses
    the OPF manifest to find all XHTML/HTML content documents.

    Args:
        zip_ref: An open ZipFile for the EPUB.

    Returns:
        list[str]: List of content file paths within the ZIP.
    """
    # 1. Parse container.xml to find OPF location
    try:
        container_xml = zip_ref.read(
            "META-INF/container.xml",
        ).decode("utf-8")
    except KeyError:
        logger.warning("EPUB missing META-INF/container.xml")
        return []

    container_root = ET.fromstring(container_xml)
    ns = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}
    rootfile_elem = container_root.find(".//c:rootfile", ns)
    if rootfile_elem is None:
        logger.warning("EPUB container.xml missing rootfile element")
        return []

    opf_path = rootfile_elem.get("full-path", "")
    if not opf_path:
        return []

    # 2. Parse OPF to find content documents
    try:
        opf_xml = zip_ref.read(opf_path).decode("utf-8")
    except KeyError:
        logger.warning("EPUB OPF file not found: %s", opf_path)
        return []

    opf_root = ET.fromstring(opf_xml)
    opf_dir = str(Path(opf_path).parent)

    # Handle default OPF namespace
    opf_ns_match = re.match(r"\{(.+?)\}", opf_root.tag)
    opf_ns = {"opf": opf_ns_match.group(1)} if opf_ns_match else {}

    # Find manifest items with XHTML/HTML media types
    content_types = {
        "application/xhtml+xml",
        "text/html",
        "text/xml",
    }
    content_files: list[str] = []

    if opf_ns:
        manifest = opf_root.find("opf:manifest", opf_ns)
    else:
        manifest = opf_root.find("manifest")
    if manifest is None:
        return []

    items = manifest.findall("opf:item", opf_ns) if opf_ns else manifest.findall("item")
    for item in items:
        media_type = item.get("media-type", "")
        href = item.get("href", "")
        if media_type in content_types and href:
            # Resolve path relative to OPF directory
            full_path = f"{opf_dir}/{href}" if opf_dir != "." else href
            # Normalize path separators
            full_path = full_path.replace("\\", "/")
            if full_path in zip_ref.namelist():
                content_files.append(full_path)

    return content_files


def _process_epub(  # noqa: PLR0912, PLR0913, PLR0915
    file_path: Path,
    output_path: Path,
    target_lang: str,
    src_lang: str,
    progress_callback: Callable[[int], None] | None,
    glossary_entries: list[tuple[int, str, str]] | None,
    cancel_check: Callable[[], bool] | None,
    checkpoint_dir: Path | None = None,
    *,
    provider: str | None = None,
    model: str | None = None,
) -> bool:
    """Translates an EPUB by processing each XHTML content document.

    On resume, previously-translated content files are loaded from the
    checkpoint and skipped.

    Args:
        file_path: Source EPUB file.
        output_path: Output file path.
        target_lang: Target language.
        src_lang: Source language.
        progress_callback: Progress reporter (0-100).
        glossary_entries: Optional glossary.
        cancel_check: Cancellation checker.
        checkpoint_dir: Directory for saving/loading checkpoints.
        provider: Optional LLM provider override.
        model: Optional LLM model override.

    Returns:
        bool: True on success.
    """
    # Check whether embedded image translation is enabled and possible
    from src.constants.settings import SETTING_TRANSLATE_DOC_IMAGES  # noqa: PLC0415
    from src.utils.config_manager import (  # noqa: PLC0415
        check_ocr_setup,
        load_setting,
    )

    do_images = (
        bool(
            load_setting(SETTING_TRANSLATE_DOC_IMAGES, False),
        )
        and check_ocr_setup()
    )

    # When image translation is active, text gets 0-70% and images 70-100%
    text_cb: Callable[[int], None] | None = progress_callback
    if do_images and progress_callback:

        def text_cb(p: int) -> None:  # type: ignore[misc]
            progress_callback(int(p * 0.7))  # type: ignore[misc]

    from src.constants.languages import is_rtl_language  # noqa: PLC0415

    is_rtl_target = is_rtl_language(target_lang)

    with zipfile.ZipFile(file_path, "r") as zip_in:
        content_files = _get_epub_content_files(zip_in)
        opf_path = _get_epub_opf_path(zip_in) if is_rtl_target else ""

        if not content_files:
            logger.warning(
                "No translatable content in EPUB: %s",
                file_path.name,
            )
            # Just copy the file as-is
            output_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file_path, output_path)
            return True

        # Load previously-translated EPUB files from checkpoint
        epub_cached: dict[str, str] = {}
        if checkpoint_dir:
            epub_cached = load_epub_checkpoint(checkpoint_dir) or {}

        # Translate each content file
        translated_contents: dict[str, bytes] = {}
        total_files = len(content_files)

        for file_idx, cf_path in enumerate(content_files):
            if cancel_check and cancel_check():
                return False

            # Use cached translation if available
            if cf_path in epub_cached:
                translated_contents[cf_path] = epub_cached[cf_path].encode("utf-8")
                if text_cb:
                    text_cb(
                        int(((file_idx + 1) / total_files) * 100),
                    )
                continue

            # Read content file
            try:
                raw = zip_in.read(cf_path)
                xhtml_content = raw.decode("utf-8")
            except (KeyError, UnicodeDecodeError) as e:
                logger.warning(
                    "Skipping EPUB file %s: %s",
                    cf_path,
                    e,
                )
                continue

            # Chunk and translate the XHTML content
            chunks, epub_chunk_seps = _chunk_text(xhtml_content, "\n")
            if not chunks:
                continue

            # Strip non-translatable attributes before LLM
            epub_stripped: list[str] = []
            epub_attr_records: list[dict[int, AttrRecord]] = []
            stripped_epub_chunks: list[str] = []
            for chunk in chunks:
                stripped, records = strip_html_attributes(chunk)
                stripped_epub_chunks.append(stripped)
                epub_stripped.append(stripped)
                epub_attr_records.append(records)

            # Per-file progress scoped to this file's range
            def _file_progress(
                p: int,
                _idx: int = file_idx,
                _total: int = total_files,
            ) -> None:
                if text_cb:
                    base = int((_idx / _total) * 100)
                    span = int((1 / _total) * 100)
                    text_cb(
                        base + int(p * span / 100),
                    )

            translated = _translate_chunks(
                stripped_epub_chunks,
                target_lang,
                src_lang,
                _file_progress,
                glossary_entries,
                cancel_check,
                content_type=CONTENT_EPUB,
                provider=provider,
                model=model,
            )
            if translated is None:
                return False  # Cancelled

            # Post-process: repair missing tags and restore attrs
            for ci in range(len(translated)):
                translated[ci] = _repair_and_restore_attrs(
                    translated[ci],
                    epub_stripped[ci],
                    epub_attr_records[ci],
                )

            result = _join_with_separators(translated, epub_chunk_seps)
            # Per-chapter dir="rtl" injection for Arabic / Hebrew / Persian.
            result = _apply_rtl_markup(result, CONTENT_EPUB, target_lang)
            translated_contents[cf_path] = result.encode("utf-8")

            # Save EPUB checkpoint after each content file
            if checkpoint_dir:
                save_epub_file_progress(
                    checkpoint_dir,
                    cf_path,
                    result,
                    content_files,
                )

        # Re-pack the EPUB with translated content
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(
                output_path,
                "w",
                zipfile.ZIP_DEFLATED,
            ) as zip_out:
                for item in zip_in.infolist():
                    if item.filename in translated_contents:
                        zip_out.writestr(
                            item,
                            translated_contents[item.filename],
                        )
                    elif opf_path and item.filename == opf_path:
                        # RTL target: rewrite the OPF spine so EPUB readers
                        # page-turn right-to-left.
                        try:
                            opf_text = zip_in.read(item.filename).decode("utf-8")
                            patched = _inject_rtl_into_opf(opf_text)
                            zip_out.writestr(item, patched.encode("utf-8"))
                        except (UnicodeDecodeError, OSError):
                            zip_out.writestr(
                                item,
                                zip_in.read(item.filename),
                            )
                    else:
                        zip_out.writestr(
                            item,
                            zip_in.read(item.filename),
                        )
        except OSError as e:
            logger.error(
                "Failed to write EPUB output %s: %s",
                output_path,
                e,
            )
            raise ValueError("TEXT_WRITE_ERROR") from e

    # Translate embedded images (70-100% progress range)
    if do_images:

        def _img_progress(p: int) -> None:
            if progress_callback:
                progress_callback(70 + int(p * 0.3))

        _translate_doc_images(
            output_path,
            ".epub",
            "",
            target_lang,
            src_lang,
            glossary_entries,
            _img_progress,
            cancel_check,
            provider=provider,
            model=model,
            checkpoint_dir=checkpoint_dir,
        )

    return True
