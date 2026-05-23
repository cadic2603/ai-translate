"""PDF processing engine for translating text-based and scanned PDF files.

Uses PyMuPDF's extract-overlay approach: extract text blocks with style
metadata, translate via LLM, redact originals, and overlay translated
text at the same positions.  Scanned pages are handled via the existing
OCR pipeline when the embedded image translation setting is enabled.
"""

from __future__ import annotations

import contextlib
import html
import logging
import os
import re
import shutil
import subprocess
import tempfile
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pymupdf

if TYPE_CHECKING:
    from src.core.config import TranslationConfig

from src.constants.errors import base_error_tag
from src.constants.llm import CONTENT_PDF
from src.constants.ocr import OCR_METHOD_TESSERACT
from src.constants.settings import (
    SETTING_OCR_METHOD,
    SETTING_TRANSLATE_DOC_COMMENTS,
    SETTING_TRANSLATE_DOC_IMAGES,
    SETTING_TRANSLATE_DOC_SHAPES,
)
from src.core.checkpoint import load_pdf_checkpoint, save_pdf_page_progress
from src.core.llm_engine import translate_batch
from src.utils import config_manager as _config

logger = logging.getLogger("pdf_processor")


# Annotation type constants (PyMuPDF PDF_ANNOT_* values)
_ANNOT_TYPE_TEXT = 0  # Sticky-note comment
_ANNOT_TYPE_FREE_TEXT = 2  # Visible text box


def _should_translate_pdf_comments(config: TranslationConfig | None = None) -> bool:
    """Checks whether PDF sticky-note comment translation is enabled.

    Gated by ``SETTING_TRANSLATE_DOC_COMMENTS`` — the same toggle used for
    Office comments.

    Args:
        config: Optional TranslationConfig snapshot; falls back to
            ``_config.load_setting()``.

    Returns:
        True if sticky-note translation should proceed.
    """
    if config is not None:
        return config.translate_doc_comments
    return bool(_config.load_setting(SETTING_TRANSLATE_DOC_COMMENTS, False))


def _should_translate_pdf_textboxes(config: TranslationConfig | None = None) -> bool:
    """Checks whether PDF FreeText annotation and form widget translation is enabled.

    Gated by ``SETTING_TRANSLATE_DOC_SHAPES`` — the same toggle used for
    Office shapes/text boxes.

    Args:
        config: Optional TranslationConfig snapshot; falls back to
            ``_config.load_setting()``.

    Returns:
        True if FreeText and widget translation should proceed.
    """
    if config is not None:
        return config.translate_doc_shapes
    return bool(_config.load_setting(SETTING_TRANSLATE_DOC_SHAPES, False))


def _extract_page_comments(page: Any) -> list[dict[str, Any]]:  # noqa: ANN401
    """Extracts sticky-note (Text) annotations from a PDF page.

    Iterates over ``page.annots()``, filtering to type 0 (sticky notes).
    Whitespace-only content is skipped.

    Args:
        page: A PyMuPDF Page object.

    Returns:
        List of annotation dicts with keys: type ("annot"), annot_type,
        annot_id, text.
    """
    entries: list[dict[str, Any]] = []
    try:
        annots = page.annots()
        if annots is None:
            return entries
        for annot in annots:
            if annot.type[0] != _ANNOT_TYPE_TEXT:
                continue
            info = annot.info
            content = info.get("content", "")
            if not content or not content.strip():
                continue
            entries.append(
                {
                    "type": "annot",
                    "annot_type": _ANNOT_TYPE_TEXT,
                    "annot_id": info.get("id", ""),
                    "text": content,
                }
            )
    except Exception:
        logger.warning("Failed to extract comments from page", exc_info=True)
    return entries


def _extract_page_freetext(page: Any) -> list[dict[str, Any]]:  # noqa: ANN401
    """Extracts FreeText (visible text box) annotations from a PDF page.

    Iterates over ``page.annots()``, filtering to type 2 (FreeText).
    Whitespace-only content is skipped.

    Args:
        page: A PyMuPDF Page object.

    Returns:
        List of annotation dicts with keys: type ("annot"), annot_type,
        annot_id, text, rect.
    """
    entries: list[dict[str, Any]] = []
    try:
        annots = page.annots()
        if annots is None:
            return entries
        for annot in annots:
            if annot.type[0] != _ANNOT_TYPE_FREE_TEXT:
                continue
            info = annot.info
            content = info.get("content", "")
            if not content or not content.strip():
                continue
            entries.append(
                {
                    "type": "annot",
                    "annot_type": _ANNOT_TYPE_FREE_TEXT,
                    "annot_id": info.get("id", ""),
                    "text": content,
                    "rect": list(annot.rect),
                }
            )
    except Exception:
        logger.warning(
            "Failed to extract FreeText annotations from page",
            exc_info=True,
        )
    return entries


def _inject_page_annotations(
    page: Any,  # noqa: ANN401
    annot_entries: list[dict[str, Any]],
) -> None:
    """Injects translated text back into PDF annotations on a page.

    Builds a lookup from annotation ID to translated text, then iterates
    ``page.annots()`` and updates matching annotations via ``set_info``
    and ``update()``.

    Args:
        page: A PyMuPDF Page object.
        annot_entries: List of annotation dicts containing ``annot_id``
            and ``translated_text`` keys.
    """
    if not annot_entries:
        return

    # Build lookup: annot_id → translated_text
    lookup: dict[str, str] = {}
    for entry in annot_entries:
        translated = entry.get("translated_text", "")
        annot_id = entry.get("annot_id", "")
        if annot_id and translated:
            lookup[annot_id] = translated

    if not lookup:
        return

    try:
        annots = page.annots()
        if annots is None:
            return
        for annot in annots:
            aid = annot.info.get("id", "")
            if aid not in lookup:
                continue
            try:
                annot.set_info(content=lookup[aid])
                annot.update()
            except Exception:
                logger.warning("Failed to inject annotation id=%s", aid, exc_info=True)
    except Exception:
        logger.warning("Failed to iterate annotations for injection", exc_info=True)


# ── Bookmark / outline translation ────────────────────────────────────


def _translate_bookmarks(  # noqa: PLR0913
    doc: Any,  # noqa: ANN401
    target_lang: str,
    src_lang: str,
    glossary_entries: list[tuple[int, str, str]] | None,
    cancel_check: Callable[[], bool] | None,
    *,
    provider: str | None = None,
    model: str | None = None,
) -> bool:
    """Translates the document outline (bookmarks / table of contents).

    Extracts all TOC entries via ``doc.get_toc()``, translates their
    titles in a single batch, and writes the updated TOC back via
    ``doc.set_toc()``.  Structure (level, page, destination) is
    preserved.

    Args:
        doc: An open PyMuPDF Document.
        target_lang: Target language name.
        src_lang: Source language name, or empty for auto-detect.
        glossary_entries: Optional glossary entries for translation.
        cancel_check: Returns True if the task was cancelled.
        provider: Optional LLM provider override.
        model: Optional LLM model override.

    Returns:
        True on success, False on cancellation.
    """
    try:
        toc = doc.get_toc(simple=False)
    except Exception:
        logger.warning("Failed to read PDF bookmarks", exc_info=True)
        return True  # Non-fatal — continue without bookmarks

    if not toc:
        return True

    # Extract titles (toc entries: [level, title, page, dest_dict])
    texts = [entry[1] for entry in toc]
    if not any(t.strip() for t in texts):
        return True

    translated = translate_batch(
        texts,
        target_lang,
        src_lang,
        glossary_entries=glossary_entries,
        cancel_check=cancel_check,
        content_type=CONTENT_PDF,
        provider=provider,
        model=model,
    )
    if translated is None:
        return False  # Cancelled

    # Rebuild TOC with translated titles
    new_toc: list[list[Any]] = []
    for i, entry in enumerate(toc):
        new_entry = list(entry)
        new_entry[1] = translated[i]
        new_toc.append(new_entry)

    try:
        doc.set_toc(new_toc)
    except Exception:
        logger.warning("Failed to write translated bookmarks", exc_info=True)

    return True


# ── Widget / form field translation ──────────────────────────────────

# PyMuPDF PDF_WIDGET_TYPE_* constants
_WIDGET_TYPE_TEXT = 7
_WIDGET_TYPE_COMBOBOX = 3
_WIDGET_TYPE_LISTBOX = 4

# Minimum image dimension (pixels) to consider for translation
_MIN_IMAGE_DIM = 50
# Image covering > 90% of page area is treated as a scanned page
_FULL_PAGE_IMAGE_RATIO = 0.9

# LLM errors that abort image translation immediately (non-retryable).
# Matched against the BASE tag (before any ``:Service`` suffix the
# engine appends for AUTH_ERROR), so ``"AUTH_ERROR:Gemini"`` still
# qualifies as fatal — without this, the suffix-bearing variant
# would slip past the set-membership check and the loop would
# skip-with-warning through every image while the same auth error
# keeps repeating, finishing "Done" with zero translated images.
_FATAL_LLM_ERRORS = {"AUTH_ERROR", "QUOTA_ERROR", "VISION_NOT_SUPPORTED"}


def _is_fatal_llm_error(error_tag: str) -> bool:
    """Returns True when *error_tag* is in ``_FATAL_LLM_ERRORS``.

    Delegates to :func:`src.constants.errors.base_error_tag` to strip
    the optional ``:Service`` suffix the engine appends to AUTH_ERROR
    so ``"AUTH_ERROR:Gemini"`` matches as fatal alongside the bare
    ``"AUTH_ERROR"``.
    """
    return base_error_tag(error_tag) in _FATAL_LLM_ERRORS


def _extract_page_widgets(page: Any) -> list[dict[str, Any]]:  # noqa: ANN401
    """Extracts translatable form field values from a PDF page.

    Handles text fields, combo boxes, and list boxes.  Whitespace-only
    values are skipped.

    Args:
        page: A PyMuPDF Page object.

    Returns:
        List of widget dicts with keys: type ("widget"), widget_type,
        field_name, text, and choice_index (combo/list only).
    """
    entries: list[dict[str, Any]] = []
    try:
        widgets = page.widgets()
        if widgets is None:
            return entries
        for widget in widgets:
            wtype = widget.field_type
            if wtype == _WIDGET_TYPE_TEXT:
                value = widget.field_value or ""
                if not value.strip():
                    continue
                entries.append(
                    {
                        "type": "widget",
                        "widget_type": wtype,
                        "field_name": widget.field_name or "",
                        "text": value,
                    }
                )
            elif wtype in (_WIDGET_TYPE_COMBOBOX, _WIDGET_TYPE_LISTBOX):
                choices = widget.choice_values or []
                for ci, choice in enumerate(choices):
                    # PyMuPDF may return (export, display) pairs
                    if isinstance(choice, (list, tuple)):
                        display = choice[-1]
                    else:
                        display = choice
                    if not str(display).strip():
                        continue
                    entries.append(
                        {
                            "type": "widget",
                            "widget_type": wtype,
                            "field_name": widget.field_name or "",
                            "text": str(display),
                            "choice_index": ci,
                        }
                    )
    except Exception:
        logger.warning("Failed to extract form fields from page", exc_info=True)
    return entries


def _inject_page_widgets(  # noqa: PLR0912
    page: Any,  # noqa: ANN401
    widget_entries: list[dict[str, Any]],
) -> None:
    """Injects translated text back into form fields on a PDF page.

    Builds a lookup from (field_name, widget_type) to translated values,
    then iterates ``page.widgets()`` and updates matching fields.

    Args:
        page: A PyMuPDF Page object.
        widget_entries: List of widget dicts with ``translated_text`` key.
    """
    if not widget_entries:
        return

    # Build lookups: text fields → single value, choice fields → list
    text_lookup: dict[str, str] = {}
    choice_lookup: dict[tuple[str, int], dict[int, str]] = {}
    for entry in widget_entries:
        translated = entry.get("translated_text", "")
        if not translated:
            continue
        fname = entry.get("field_name", "")
        wtype = entry.get("widget_type", 0)
        if wtype == _WIDGET_TYPE_TEXT:
            text_lookup[fname] = translated
        elif wtype in (_WIDGET_TYPE_COMBOBOX, _WIDGET_TYPE_LISTBOX):
            key = (fname, wtype)
            if key not in choice_lookup:
                choice_lookup[key] = {}
            ci = entry.get("choice_index", 0)
            choice_lookup[key][ci] = translated

    if not text_lookup and not choice_lookup:
        return

    try:
        widgets = page.widgets()
        if widgets is None:
            return
        for widget in widgets:
            fname = widget.field_name or ""
            wtype = widget.field_type
            try:
                if wtype == _WIDGET_TYPE_TEXT and fname in text_lookup:
                    widget.field_value = text_lookup[fname]
                    widget.update()
                elif wtype in (_WIDGET_TYPE_COMBOBOX, _WIDGET_TYPE_LISTBOX):
                    key = (fname, wtype)
                    if key in choice_lookup:
                        old_choices = widget.choice_values or []
                        new_choices = list(old_choices)
                        for ci, translated_choice in choice_lookup[key].items():
                            if ci < len(new_choices):
                                new_choices[ci] = translated_choice
                        widget.choice_values = new_choices
                        # Update selected value if it was translated
                        old_val = widget.field_value or ""
                        for ci, translated_choice in choice_lookup[key].items():
                            if ci < len(old_choices):
                                orig = old_choices[ci]
                                if isinstance(orig, (list, tuple)):
                                    orig = orig[-1]
                                if str(orig) == old_val:
                                    widget.field_value = translated_choice
                                    break
                        widget.update()
            except Exception:
                logger.warning(
                    "Failed to inject widget '%s'",
                    fname,
                    exc_info=True,
                )
    except Exception:
        logger.warning(
            "Failed to iterate widgets for injection",
            exc_info=True,
        )


# ── Embedded image translation ───────────────────────────────────────


def _translate_page_images(  # noqa: PLR0913, PLR0912, PLR0915
    doc: Any,  # noqa: ANN401
    page: Any,  # noqa: ANN401
    target_lang: str,
    src_lang: str,
    glossary_entries: list[tuple[int, str, str]] | None,
    ocr_method: str,
    cancel_check: Callable[[], bool] | None,
    translated_xrefs: set[int],
    *,
    provider: str | None = None,
    model: str | None = None,
) -> None:
    """Translates embedded raster images within a text-based PDF page.

    Extracts each image by xref, runs OCR → LLM translation → render,
    and replaces the original image via ``page.replace_image()``.
    Skips tiny images (icons/bullets) and full-page images (handled by
    the scanned-page pipeline).

    Args:
        doc: An open PyMuPDF Document.
        page: A PyMuPDF Page object (text page with embedded images).
        target_lang: Target language name.
        src_lang: Source language name.
        glossary_entries: Optional glossary entries.
        ocr_method: OCR method name.
        cancel_check: Returns True if the task was cancelled.
        translated_xrefs: Set of already-translated image xrefs
            (mutated in-place to track progress across pages).
        provider: Optional LLM provider override.
        model: Optional LLM model override.
    """
    try:
        images = page.get_images(full=True)
    except Exception:
        return

    if not images:
        return

    # Get image bounding info to filter by size
    try:
        img_info_list = page.get_image_info(xrefs=True)
    except Exception:
        img_info_list = []

    page_area = abs(page.rect.width * page.rect.height) or 1

    for img_tuple in images:
        if cancel_check and cancel_check():
            return

        xref = img_tuple[0]
        if xref in translated_xrefs:
            continue

        # Find bounding box from image info
        img_rect = None
        for info in img_info_list:
            if info.get("xref") == xref:
                bbox = info.get("bbox")
                if bbox:
                    img_rect = bbox  # (x0, y0, x1, y1)
                break

        # Filter by size: skip tiny images (icons, bullets, decorations)
        if img_rect:
            img_w = abs(img_rect[2] - img_rect[0])
            img_h = abs(img_rect[3] - img_rect[1])
            if img_w < _MIN_IMAGE_DIM or img_h < _MIN_IMAGE_DIM:
                translated_xrefs.add(xref)
                continue
            # Skip full-page images (handled by scanned-page pipeline)
            img_area = img_w * img_h
            if img_area > page_area * _FULL_PAGE_IMAGE_RATIO:
                continue

        try:
            img_data = doc.extract_image(xref)
        except Exception:
            logger.debug("Cannot extract image xref=%d", xref)
            translated_xrefs.add(xref)
            continue

        if not img_data or not img_data.get("image"):
            translated_xrefs.add(xref)
            continue

        image_bytes = img_data["image"]
        ext = img_data.get("ext", "png")
        if not ext.startswith("."):
            ext = f".{ext}"

        # Run OCR → LLM → render pipeline
        try:
            result_bytes = _translate_single_pdf_image(
                image_bytes,
                ext,
                target_lang,
                src_lang,
                glossary_entries,
                ocr_method,
                provider=provider,
                model=model,
            )
        except Exception as exc:
            # Fatal LLM errors propagate immediately (non-retryable).
            # ``_is_fatal_llm_error`` strips the ``:Service`` suffix
            # (e.g. ``"AUTH_ERROR:Gemini"``) so the suffix-bearing
            # variants the engine raises still qualify as fatal.
            if isinstance(exc, ValueError) and _is_fatal_llm_error(str(exc)):
                raise
            logger.warning(
                "Non-fatal error translating image xref=%d: %s",
                xref,
                exc,
            )
            translated_xrefs.add(xref)
            continue

        if result_bytes:
            try:
                page.replace_image(xref, stream=result_bytes)
            except Exception:
                logger.warning(
                    "Failed to replace image xref=%d",
                    xref,
                    exc_info=True,
                )

        translated_xrefs.add(xref)


def _translate_single_pdf_image(  # noqa: PLR0913
    image_bytes: bytes,
    ext: str,
    target_lang: str,
    src_lang: str,
    glossary_entries: list[tuple[int, str, str]] | None,
    ocr_method: str,
    *,
    provider: str | None = None,
    model: str | None = None,
) -> bytes | None:
    """Translates a single embedded PDF image using the OCR pipeline.

    Writes the image to a temp file, processes OCR → LLM → render,
    and returns the translated image bytes.  Returns None if the image
    has no translatable text.

    Args:
        image_bytes: Raw image data.
        ext: File extension including dot (e.g. ".png").
        target_lang: Target language name.
        src_lang: Source language name.
        glossary_entries: Optional glossary entries.
        ocr_method: OCR method name.
        provider: Optional LLM provider override.
        model: Optional LLM model override.

    Returns:
        Translated image bytes, or None.
    """
    from src.core.image_processor import process_image_translation  # noqa: PLC0415
    from src.core.layout_analysis import merge_to_paragraphs  # noqa: PLC0415
    from src.core.llm_engine import translate_image_content  # noqa: PLC0415
    from src.core.ocr_engine import run_ocr  # noqa: PLC0415

    with tempfile.TemporaryDirectory(prefix="ftrans_pdfimg_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        input_path = tmp_path / f"input{ext}"
        output_path = tmp_path / f"output{ext}"

        input_path.write_bytes(image_bytes)

        # 1. OCR
        ocr_results = run_ocr(
            str(input_path),
            method=ocr_method,
            src_lang=src_lang,
        )
        if not ocr_results:
            return None

        raw_ocr_results = list(ocr_results)

        # 2. LLM translation (may raise ValueError for fatal errors)
        paragraph_data = translate_image_content(
            str(input_path),
            ocr_results,
            target_lang,
            src_lang,
            glossary_entries=glossary_entries,
            provider=provider,
            model=model,
        )

        # 3. Merge paragraphs
        merged_results, translations, raw_fragments = merge_to_paragraphs(
            paragraph_data,
            raw_ocr_results,
            ocr_method,
        )
        if not merged_results:
            return None

        # 4. Render translated image
        success = process_image_translation(
            str(input_path),
            str(output_path),
            merged_results,
            translations,
            target_lang=target_lang,
            raw_ocr_results=raw_fragments,
            ocr_method=ocr_method,
        )

        if success and output_path.exists():
            return output_path.read_bytes()
        return None


# ── Entry point ───────────────────────────────────────────────────────


def process_pdf_file(  # noqa: PLR0913, PLR0912, PLR0915
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
    """Translates a PDF file and writes the result to output_path.

    For text-based pages: extracts text blocks, translates via LLM,
    redacts originals, and overlays translated text.
    For scanned pages (no embedded text): falls back to OCR pipeline
    when the translate-document-images setting is enabled.

    Args:
        file_path: Path to the source PDF.
        output_path: Path to write the translated PDF.
        target_lang: Target language name.
        src_lang: Source language name, or empty for auto-detect.
        progress_callback: Called with 0-100 progress percentage.
        glossary_entries: Optional glossary entries for translation.
        cancel_check: Returns True if the task was cancelled.
        checkpoint_dir: Directory for saving/loading checkpoints.
        config: Optional TranslationConfig for dependency injection.
        provider: Optional LLM provider override.
        model: Optional LLM model override.

    Returns:
        True on success, False on cancellation.

    Raises:
        ValueError: With error tag on import/open/save failures.
    """
    # Suppress verbose LLM logging during PDF translation so
    # line-join debug output is not drowned out.
    _llm_logger = logging.getLogger("llm")
    _llm_prev_level = _llm_logger.level
    _llm_logger.setLevel(logging.WARNING)

    try:
        # Determine whether to process scanned pages via OCR
        if config is not None:
            do_images = config.should_translate_images
        else:
            do_images = bool(
                _config.load_setting(SETTING_TRANSLATE_DOC_IMAGES, False)
                and _config.check_ocr_setup()
            )
        # Determine whether to translate PDF comments (sticky notes)
        do_comments = _should_translate_pdf_comments(config)
        # Determine whether to translate PDF text boxes (FreeText) and widgets
        do_textboxes = _should_translate_pdf_textboxes(config)

        # Text pages get most of the progress weight; OCR pages get the rest
        text_weight = 0.8 if do_images else 1.0

        doc = pymupdf.open(str(file_path))
        try:
            total = doc.page_count

            # Load checkpoint for resumption.  Pass total to detect a
            # source-PDF replacement between runs (different page count
            # → discard stale checkpoint instead of resuming with mismatched
            # per-page mappings).
            checkpoint: dict[int, list[dict[str, Any]]] = {}
            if checkpoint_dir:
                checkpoint = (
                    load_pdf_checkpoint(checkpoint_dir, expected_total_pages=total)
                    or {}
                )

            scanned_page_indices: list[int] = []
            translated_xrefs: set[int] = set()  # Track processed images

            # Resolve OCR method for embedded image translation
            if config is not None:
                ocr_method = config.ocr_method
            else:
                ocr_method = _config.load_setting(
                    SETTING_OCR_METHOD,
                    OCR_METHOD_TESSERACT,
                )

            for page_idx in range(total):
                # Cancel check between pages
                if cancel_check and cancel_check():
                    return False

                page = doc[page_idx]

                # Check checkpoint cache for this page.
                # NOTE: Embedded image translations are not checkpointed,
                # so images on cached pages will be re-processed from the
                # original on resume.  This is acceptable because the doc
                # is reopened from the source file each time.
                if page_idx in checkpoint:
                    cached_entries = checkpoint[page_idx]
                    if cached_entries:
                        # Split into text blocks, annotations, widgets,
                        # and links
                        cached_blocks = [
                            e
                            for e in cached_entries
                            if e.get("type") not in ("annot", "widget", "link")
                        ]
                        cached_annots = [
                            e for e in cached_entries if e.get("type") == "annot"
                        ]
                        cached_widgets = [
                            e for e in cached_entries if e.get("type") == "widget"
                        ]
                        cached_links = [
                            e for e in cached_entries if e.get("type") == "link"
                        ]
                        if cached_blocks:
                            # Restore saved links from checkpoint.
                            # They carry _translated, _block_idx,
                            # _left_char, _right_char from the original
                            # run, enabling precise char-level matching
                            # (Path A) on resume.
                            _apply_translated_blocks(
                                page,
                                cached_blocks,
                                pymupdf,
                                saved_links=cached_links or None,
                                target_lang=target_lang,
                            )
                        if cached_annots:
                            _inject_page_annotations(page, cached_annots)
                        if cached_widgets:
                            _inject_page_widgets(page, cached_widgets)
                    # Progress update for cached page
                    if progress_callback:
                        progress_callback(
                            int(
                                ((page_idx + 1) / total) * 100 * text_weight,
                            ),
                        )
                    continue

                # Extract text blocks from the page
                blocks = _extract_page_blocks(page)

                # Extract sticky-note comments if enabled
                comment_entries: list[dict[str, Any]] = []
                if do_comments:
                    comment_entries = _extract_page_comments(page)

                # Extract FreeText annotations and form widgets if enabled
                freetext_entries: list[dict[str, Any]] = []
                widget_entries: list[dict[str, Any]] = []
                if do_textboxes:
                    freetext_entries = _extract_page_freetext(page)
                    widget_entries = _extract_page_widgets(page)

                # Merge annotation entries for batch translation
                annot_entries = comment_entries + freetext_entries

                # Save links early and inject <a> tags into block text
                # so the LLM translates link text in context.
                saved_links = _save_page_links(page) if blocks else []
                if saved_links and blocks:
                    _inject_link_tags(blocks, saved_links, pymupdf)

                if blocks or annot_entries or widget_entries:
                    # Build combined texts list for a single
                    # translate_batch call
                    texts = (
                        [b["text"] for b in blocks]
                        + [a["text"] for a in annot_entries]
                        + [w["text"] for w in widget_entries]
                    )
                    translated = translate_batch(
                        texts,
                        target_lang,
                        src_lang,
                        glossary_entries=glossary_entries,
                        cancel_check=cancel_check,
                        content_type=CONTENT_PDF,
                        provider=provider,
                        model=model,
                    )
                    if translated is None:
                        return False

                    # Split results: blocks, then annotations, then
                    # widgets.  Skip items where the translation is
                    # identical to the original (untranslatable).
                    num_blocks = len(blocks)
                    num_annots = len(annot_entries)
                    for i, block in enumerate(blocks):
                        if translated[i] != block["text"]:
                            block["translated_text"] = translated[i]
                    for j, entry in enumerate(annot_entries):
                        tr_text = translated[num_blocks + j]
                        if tr_text != entry["text"]:
                            entry["translated_text"] = tr_text
                    for k, entry in enumerate(widget_entries):
                        tr_text = translated[num_blocks + num_annots + k]
                        if tr_text != entry["text"]:
                            entry["translated_text"] = tr_text

                    # Extract translated link text from <a> tags,
                    # then strip tags for clean overlay
                    if saved_links:
                        _extract_link_translations(
                            blocks,
                            saved_links,
                        )

                    # Restore math placeholders: ⟪N⟫ → font-tagged HTML
                    for block in blocks:
                        mm = block.get("_math_map")
                        if mm and "translated_text" in block:
                            block["translated_text"] = _restore_math_placeholders(
                                block["translated_text"],
                                mm,
                            )
                            # Restored text now contains <span> tags
                            block["has_mixed_formatting"] = True

                    # Redact originals and overlay translations
                    if blocks:
                        _apply_translated_blocks(
                            page,
                            blocks,
                            pymupdf,
                            saved_links=saved_links,
                            target_lang=target_lang,
                        )

                    # Inject translated annotations
                    if annot_entries:
                        _inject_page_annotations(page, annot_entries)

                    # Inject translated form fields
                    if widget_entries:
                        _inject_page_widgets(page, widget_entries)

                    # Translate embedded images on text pages
                    if do_images and _page_has_images(page):
                        _translate_page_images(
                            doc,
                            page,
                            target_lang,
                            src_lang,
                            glossary_entries,
                            ocr_method,
                            cancel_check,
                            translated_xrefs,
                            provider=provider,
                            model=model,
                        )

                    # Save per-page checkpoint (include links so
                    # char-level matching works on resume)
                    if checkpoint_dir:
                        link_entries = (
                            _links_to_checkpoint(saved_links) if saved_links else []
                        )
                        save_pdf_page_progress(
                            checkpoint_dir,
                            page_idx,
                            blocks + annot_entries + widget_entries + link_entries,
                            total,
                        )
                elif do_images and _page_has_images(page):
                    # No text but has raster images — treat as scanned
                    scanned_page_indices.append(page_idx)
                elif checkpoint_dir:
                    # Save empty checkpoint for text-less page
                    save_pdf_page_progress(
                        checkpoint_dir,
                        page_idx,
                        [],
                        total,
                    )

                # Report progress for text phase
                if progress_callback:
                    progress_callback(
                        int(
                            ((page_idx + 1) / total) * 100 * text_weight,
                        ),
                    )

            # Translate bookmarks / outline entries
            if cancel_check and cancel_check():
                return False
            if not _translate_bookmarks(
                doc,
                target_lang,
                src_lang,
                glossary_entries,
                cancel_check,
                provider=provider,
                model=model,
            ):
                return False

            # Save the translated document
            doc.save(str(output_path), garbage=4, deflate=True)
        finally:
            doc.close()

        # Process scanned pages via OCR pipeline
        if scanned_page_indices and do_images:
            success = _process_scanned_pages(
                output_path,
                scanned_page_indices,
                target_lang,
                src_lang,
                glossary_entries,
                progress_callback,
                cancel_check,
                text_weight,
                config=config,
                provider=provider,
                model=model,
            )
            if not success:
                return False

        # Ensure progress reaches 100% (text_weight < 1.0 when OCR is
        # enabled but no scanned pages were found, capped at 80%)
        if progress_callback:
            progress_callback(100)

        return True
    finally:
        _llm_logger.setLevel(_llm_prev_level)


# ── Form XObject detection ─────────────────────────────────────────────


def _get_form_xobject_rects(page: Any) -> list[Any]:  # noqa: ANN401, PLR0912, PLR0915
    """Compute page-level bounding boxes of Form XObjects that render text.

    Some PDFs embed diagrams as Form XObjects that render text as both
    text operators *and* path/outline commands.  ``apply_redactions()``
    removes the text operators but the path-based rendering survives
    (when ``graphics=PDF_REDACT_LINE_ART_NONE``), leaving original text
    visually present.  Blocks inside these regions must be skipped so
    translated text is not overlaid on irremovable originals.

    The function:

    1. Identifies Form XObjects (type 0) whose stream contains text
       drawing operators (``Tj`` / ``TJ``).
    2. Parses the page content stream to track the Current Transformation
       Matrix (CTM) and locates ``/Name Do`` commands.
    3. Transforms each XObject's internal ``BBox`` to page coordinates.

    Args:
        page: A PyMuPDF Page object.

    Returns:
        List of ``pymupdf.Rect`` objects in page coordinates (origin at
        top-left).  Empty if no text-bearing Form XObjects are found.
    """
    xobjects = page.get_xobjects()
    if not xobjects:
        return []

    doc = page.parent

    # Filter to Form XObjects (type 0) whose stream draws text.
    text_xobjects: dict[str, tuple[float, ...]] = {}
    for xref, name, xtype, internal_bbox in xobjects:
        if xtype != 0:
            continue
        try:
            stream = doc.xref_stream(xref).decode("latin-1", errors="replace")
            if "Tj" in stream or "TJ" in stream:
                text_xobjects[name] = internal_bbox
        except Exception:  # noqa: BLE001
            continue

    if not text_xobjects:
        return []

    # Parse page content stream to find the CTM for each XObject reference.
    page_height = page.rect.height
    rects: list[Any] = []

    for cxref in page.get_contents():
        try:
            content = doc.xref_stream(cxref).decode("latin-1", errors="replace")
        except Exception:  # noqa: BLE001
            continue

        tokens = content.split()
        ctm_stack: list[list[float]] = []
        current_ctm = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]

        i = 0
        while i < len(tokens):
            tok = tokens[i]
            if tok == "q":
                ctm_stack.append(current_ctm[:])
            elif tok == "Q" and ctm_stack:
                current_ctm = ctm_stack.pop()
            elif tok == "cm" and i >= 6:  # noqa: PLR2004
                try:
                    a = float(tokens[i - 6])
                    b = float(tokens[i - 5])
                    c = float(tokens[i - 4])
                    d = float(tokens[i - 3])
                    e = float(tokens[i - 2])
                    f = float(tokens[i - 1])
                    ca, cb, cc, cd, ce, cf = current_ctm
                    current_ctm = [
                        a * ca + b * cc,
                        a * cb + b * cd,
                        c * ca + d * cc,
                        c * cb + d * cd,
                        e * ca + f * cc + ce,
                        e * cb + f * cd + cf,
                    ]
                except (ValueError, IndexError):
                    pass
            elif tok == "Do" and i >= 1:
                name = tokens[i - 1].lstrip("/")
                if name in text_xobjects:
                    ix0, iy0, ix1, iy1 = text_xobjects[name]
                    a, b, c, d, e, f = current_ctm
                    corners = [
                        (a * ix0 + c * iy0 + e, b * ix0 + d * iy0 + f),
                        (a * ix1 + c * iy0 + e, b * ix1 + d * iy0 + f),
                        (a * ix0 + c * iy1 + e, b * ix0 + d * iy1 + f),
                        (a * ix1 + c * iy1 + e, b * ix1 + d * iy1 + f),
                    ]
                    px0 = min(cx for cx, _ in corners)
                    py0_pdf = min(cy for _, cy in corners)
                    px1 = max(cx for cx, _ in corners)
                    py1_pdf = max(cy for _, cy in corners)
                    rects.append(
                        pymupdf.Rect(
                            px0,
                            page_height - py1_pdf,
                            px1,
                            page_height - py0_pdf,
                        )
                    )
            i += 1

    return rects


def _block_inside_any_xobject(
    block_rect: list[float],
    xobject_rects: list[Any],
) -> bool:
    """Check if a block is completely inside any Form XObject region.

    Args:
        block_rect: [x0, y0, x1, y1] of the text block.
        xobject_rects: List of ``pymupdf.Rect`` for XObject regions.

    Returns:
        True if the block is fully contained in an XObject region.
    """
    br = pymupdf.Rect(block_rect)
    return any(xr.contains(br) for xr in xobject_rects)


# ── Raster image overlap detection ────────────────────────────────────

# Minimum overlap ratio (block area inside image / block area) to consider
# a text block as an invisible OCR layer sitting on top of a raster image.
_IMAGE_OVERLAP_THRESHOLD = 0.5


def _get_image_rects(page_dict: dict[str, Any]) -> list[tuple[float, ...]]:
    """Collect bounding boxes of image blocks from the page text dict.

    Image blocks have ``type == 1`` in PyMuPDF's ``get_text("dict")``
    output.

    Args:
        page_dict: Result of ``page.get_text("dict")``.

    Returns:
        List of ``(x0, y0, x1, y1)`` tuples for each raster image.
    """
    rects: list[tuple[float, ...]] = []
    for block in page_dict.get("blocks", []):
        if block.get("type") == 1:
            rects.append(tuple(block["bbox"]))
    return rects


def _block_overlaps_image(
    block_rect: list[float],
    image_rects: list[tuple[float, ...]],
) -> bool:
    """Check if a text block is mostly inside any raster image.

    Returns True when the intersection area between the block and any
    image exceeds ``_IMAGE_OVERLAP_THRESHOLD`` of the block's area.
    Such blocks are almost certainly invisible OCR text layers placed
    on top of raster images for searchability.  Since redaction cannot
    remove text baked into image pixels, translating these blocks would
    overlay translated text on top of still-visible originals.

    Args:
        block_rect: ``[x0, y0, x1, y1]`` of the text block.
        image_rects: Image bounding boxes from ``_get_image_rects()``.

    Returns:
        True if the block should be skipped to avoid overlap.
    """
    bx0, by0, bx1, by1 = block_rect
    block_area = (bx1 - bx0) * (by1 - by0)
    if block_area <= 0:
        return False
    for ix0, iy0, ix1, iy1 in image_rects:
        # Compute intersection
        ox0 = max(bx0, ix0)
        oy0 = max(by0, iy0)
        ox1 = min(bx1, ix1)
        oy1 = min(by1, iy1)
        if ox0 < ox1 and oy0 < oy1:
            overlap = (ox1 - ox0) * (oy1 - oy0)
            if overlap / block_area > _IMAGE_OVERLAP_THRESHOLD:
                return True
    return False


# ── Text block extraction ─────────────────────────────────────────────


def _get_freetext_annot_rects(page: Any) -> list[Any]:  # noqa: ANN401
    """Collect bounding rects of FreeText annotations on the page.

    FreeText annotations (type 2) render their text directly on the
    page.  ``get_text("dict")`` includes this text as ordinary text
    blocks.  Redacting those blocks destroys the annotation, so they
    must be identified and skipped during text block extraction.

    Args:
        page: A PyMuPDF Page object.

    Returns:
        List of ``pymupdf.Rect`` for each FreeText annotation, or
        empty if none exist.
    """
    rects: list[Any] = []
    try:
        annots = page.annots()
        if annots is None:
            return rects
        for annot in annots:
            if annot.type[0] == _ANNOT_TYPE_FREE_TEXT:
                rects.append(pymupdf.Rect(annot.rect))
    except Exception:  # noqa: BLE001
        logger.debug("Failed to read FreeText annotation rects", exc_info=True)
    return rects


def _block_inside_freetext(
    block_rect: list[float],
    freetext_rects: list[Any],
) -> bool:
    """Check if a text block's center falls inside any FreeText annotation.

    Uses center-point containment because the rendered text bbox from
    ``get_text("dict")`` often extends slightly beyond the annotation
    rect (e.g. font descenders), so strict ``contains()`` would miss it.

    Args:
        block_rect: ``[x0, y0, x1, y1]`` of the text block.
        freetext_rects: Rects from ``_get_freetext_annot_rects()``.

    Returns:
        True if the block is rendered by a FreeText annotation.
    """
    bx0, by0, bx1, by1 = block_rect
    center = pymupdf.Point((bx0 + bx1) / 2, (by0 + by1) / 2)
    return any(fr.contains(center) for fr in freetext_rects)


def _span_in_any_table(
    span_bbox: tuple[float, ...] | list[float],
    table_bboxes: list[tuple[float, ...]],
) -> bool:
    """Check if a span's center falls within any table bounding box."""
    sx0, sy0, sx1, sy1 = span_bbox
    scx = (sx0 + sx1) / 2
    scy = (sy0 + sy1) / 2
    for tx0, ty0, tx1, ty1 in table_bboxes:
        if tx0 <= scx <= tx1 and ty0 <= scy <= ty1:
            return True
    return False


# Horizontal text has dir ≈ (1, 0); anything deviating more than this
# tolerance is considered non-horizontal (vertical, rotated, etc.).
_DIR_HORIZONTAL_TOLERANCE = 0.1


def _is_vertical_block(lines: list[dict[str, Any]]) -> bool:
    """Returns True if all lines in the block are non-horizontal.

    Horizontal text has ``dir`` close to ``(1, 0)``.  Vertical or
    rotated text (e.g. arXiv identifiers, watermarks) has a different
    direction vector and cannot be faithfully redacted + re-overlaid
    via ``insert_htmlbox``.

    Args:
        lines: List of line dicts from ``get_text("dict")``.

    Returns:
        True if every line has a non-horizontal direction.
    """
    for line in lines:
        dx, dy = line.get("dir", (1.0, 0.0))
        # Horizontal: dx ≈ 1.0, dy ≈ 0.0
        tol = _DIR_HORIZONTAL_TOLERANCE
        if abs(dx - 1.0) < tol and abs(dy) < tol:
            return False
    return True


# Standard leading ratio (line-spacing / font-size) used in most PDF
# producers.  Gaps close to font_size × this ratio are line wraps.
_LEADING_RATIO = 1.2
# A gap up to this factor × expected leading is still a line wrap.
_LEADING_TOLERANCE = 1.5
# Relative font-size change above which two lines are different
# structural elements (e.g. heading → body).
_SIZE_CHANGE_THRESHOLD = 0.15
# Minimum block width (points) to enable layout-based detection.
# Narrow blocks (e.g. single-column numbers) should not trigger it.
_MIN_BLOCK_WIDTH_FOR_LAYOUT = 50.0
# A span whose font size is below this ratio of the line's dominant
# font size is classified as superscript or subscript.
_SUP_SUB_SIZE_RATIO = 0.85

# Prefixes of font names used for mathematical typesetting.  Covers
# all Computer Modern variants (CMR, CMMI, CMSY, CMEX, CMSS, CMTT, …)
# and AMS Blackboard Bold (MSBM).  Blocks dominated by these fonts
# contain formulas whose 2D layout cannot be represented as linear
# text — translating them produces garbled output.
_MATH_FONT_PREFIXES = ("CM", "MSB")
# First printable ASCII char; codes below this are control characters
# used by CMEX for delimiter pieces (hooks, extensions).
_CTRL_CHAR_LIMIT = 0x20
# Minimum vertical overlap (pt) required to merge two math-adjacent
# blocks.  Tiny overlaps (< 5 pt) are typically ascender/descender
# bleed between separate paragraphs, not genuine visual collision.
_MATH_MERGE_MIN_OVERLAP = 5.0
# Minimum font-size ratio for split-paragraph detection.  Both halves
# of a split paragraph come from the same body text, so sizes must be
# close (within 20%).
_SPLIT_PARA_SIZE_RATIO = 0.8
# Factor for detecting display-equation gaps within a PyMuPDF block.
# When the vertical gap between consecutive visual lines exceeds
# this multiple of the estimated font size, the block is split so
# display equations become separate blocks (and can be skipped when
# they contain no body text).
_DISPLAY_GAP_FACTOR = 1.0
# Tolerance for detecting inline math vs display equations.
# A pure-math line whose x0 is within this multiple of the dominant
# font size from the body text's left margin is treated as inline
# (continuation of a paragraph) and kept.  Lines further right are
# treated as display equations and dropped.
_INLINE_MATH_X_TOL = 2.0
# Minimum number of distinct y-levels occupied by math-font spans
# before the region is considered a complex 2D math layout.  Inline
# math (footnote markers, small formulas like O(n²)) occupies 1–2
# y-levels.  Complex layouts (fractions, stacked operators, algorithm
# pseudocode) span many more.
_COMPLEX_MATH_YLEVELS = 3
# Math operator characters that must never be tagged as <sup>/<sub>.
# These are spanning/stacking operators whose rendered size should be
# preserved as-is.  The radical "√" appears in CMSY at subscript
# design size for fractions (e.g. 1/√dk), but rendering it as
# <sup>√</sup> incorrectly shrinks and raises it.
_MATH_NO_ROLE_CHARS = frozenset(
    {
        "\u221a",  # √  radical
    }
)
# Placeholder delimiters for math-font spans.  Consecutive math-font
# spans are merged into a single placeholder ``⟪N⟫`` so the LLM only
# translates the surrounding body text.  After translation the
# placeholders are restored with the original math notation.
_MATH_PH_START = "\u27ea"  # ⟪  Mathematical Left Double Angle Bracket
_MATH_PH_END = "\u27eb"  # ⟫  Mathematical Right Double Angle Bracket
_MATH_PH_RE = re.compile(
    re.escape(_MATH_PH_START) + r"(\d+)" + re.escape(_MATH_PH_END),
)


def _is_math_font(font_name: str) -> bool:
    """Return True if *font_name* belongs to a math-typesetting family."""
    return any(font_name.startswith(p) for p in _MATH_FONT_PREFIXES)


def _has_complex_math_layout(spans: list[dict[str, Any]]) -> bool:
    """Return True if *spans* form a complex 2D math arrangement.

    Counts the number of distinct y-levels (baselines) occupied by
    math-font spans.  Inline math — footnote markers (†/‡), small
    formulas like ``O(n²)``, isolated symbols (∼) — sits on 1–2
    y-levels.  Complex 2D layouts — fractions, stacked operators,
    algorithm pseudocode — span many more.

    Returns True when the math y-level count reaches
    ``_COMPLEX_MATH_YLEVELS`` (default 3).  Works on any collection
    of spans (table cells, blocks, arbitrary regions).
    """
    math_y: set[float] = set()
    for s in spans:
        if s.get("text", "").strip() and _is_math_font(s.get("font", "")):
            math_y.add(round(s["bbox"][1], 1))
    return len(math_y) >= _COMPLEX_MATH_YLEVELS


def _is_pure_math_line(
    line_span_items: list[dict[str, Any]],
) -> bool:
    """Return True if every text-bearing span in the line uses a math font.

    Separator spans (from same-y / subscript merges) and math-placeholder
    spans are ignored.  Returns False when the line has no text spans.
    """
    text_spans = [
        s for s in line_span_items if s.get("text", "").strip() and "font" in s
    ]
    return bool(text_spans) and all(
        _is_math_font(s["font"]) or s.get("_is_math") for s in text_spans
    )


def _split_at_display_gaps(
    block: dict[str, Any],
) -> list[dict[str, Any]]:
    """Split a PyMuPDF text block at large vertical gaps between lines.

    Display equations often appear within the same PyMuPDF block as the
    preceding body text, separated by a gap much larger than normal line
    spacing.  This function detects such gaps and returns a list of
    synthetic sub-blocks, each with its own ``lines`` list and a
    recomputed ``bbox``.

    A gap is "large" when it exceeds *_DISPLAY_GAP_FACTOR* × the
    dominant font size of the preceding line group.

    If no large gaps are found, the original block is returned as-is
    (wrapped in a single-element list) to avoid unnecessary copies.
    """
    lines = block.get("lines", [])
    if len(lines) < 2:  # noqa: PLR2004
        return [block]

    # Compute bottom-y of each line from its bbox.
    y_bottoms = [ln["bbox"][3] for ln in lines]
    y_tops = [ln["bbox"][1] for ln in lines]

    # Dominant font size per line (max span size).
    def _line_font_size(ln: dict[str, Any]) -> float:
        """Return the dominant (max) font size of a line's spans."""
        sizes = [s.get("size", 12.0) for s in ln.get("spans", [])]
        return max(sizes) if sizes else 12.0

    # Find split points: indices where the gap before line[i] is large.
    split_indices: list[int] = []
    for i in range(1, len(lines)):
        gap = y_tops[i] - y_bottoms[i - 1]
        if gap <= 0:
            continue
        # Use the font size of the previous line as the reference.
        ref_size = _line_font_size(lines[i - 1])
        if gap > _DISPLAY_GAP_FACTOR * ref_size:
            split_indices.append(i)

    if not split_indices:
        return [block]

    # Build sub-blocks at each split point.
    sub_blocks: list[dict[str, Any]] = []
    boundaries = [0, *split_indices, len(lines)]
    for seg_idx in range(len(boundaries) - 1):
        start = boundaries[seg_idx]
        end = boundaries[seg_idx + 1]
        seg_lines = lines[start:end]
        # Recompute bbox from the line bboxes in this segment.
        x0 = min(ln["bbox"][0] for ln in seg_lines)
        y0 = min(ln["bbox"][1] for ln in seg_lines)
        x1 = max(ln["bbox"][2] for ln in seg_lines)
        y1 = max(ln["bbox"][3] for ln in seg_lines)
        sub = dict(block)  # shallow copy — shares span dicts
        sub["lines"] = seg_lines
        sub["bbox"] = (x0, y0, x1, y1)
        sub_blocks.append(sub)

    return sub_blocks


# Maximum x-gap (points) between adjacent raw blocks for their lines
# to be considered part of the same visual line.  When PyMuPDF splits
# a continuation (e.g. a radical's radicand "2/δ") into a new block,
# the gap is typically 0 — this threshold catches such cases while
# avoiding merges across genuine column gaps.
_ADJACENT_BLOCK_MAX_GAP = 5.0


def _merge_continuation_lines(
    blocks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Transfer continuation lines from adjacent blocks.

    PyMuPDF sometimes places the tail of a visual line (e.g. a
    radicand ``2/δ`` after a radical ``√``) into a separate raw block.
    When this happens the pure-math line is later misclassified as a
    display equation and dropped, orphaning the math content.

    This function detects such splits by checking whether the first
    line of block *N+1* is on the same visual line (within
    ``_LINE_Y_TOLERANCE``) as the last line of block *N* **and** is
    x-adjacent (gap < ``_ADJACENT_BLOCK_MAX_GAP``).  Matching lines
    are transferred to block *N* so the same-y merge inside
    ``_extract_page_blocks`` can reunite the spans.
    """
    if len(blocks) < 2:  # noqa: PLR2004
        return blocks

    result = list(blocks)
    i = 0
    while i < len(result) - 1:
        cur = result[i]
        nxt = result[i + 1]
        if cur.get("type") != 0 or nxt.get("type") != 0:
            i += 1
            continue
        cur_lines = cur.get("lines", [])
        nxt_lines = nxt.get("lines", [])
        if not cur_lines or not nxt_lines:
            i += 1
            continue

        # Skip vertical text blocks — adjacent vertical words (e.g.
        # attention visualization labels) share similar y0 and x-gap
        # but are separate words, not continuations.
        cur_dir = cur_lines[-1].get("dir", (1, 0))
        nxt_dir = nxt_lines[0].get("dir", (1, 0))
        if abs(cur_dir[0]) < 0.5 or abs(nxt_dir[0]) < 0.5:  # noqa: PLR2004
            i += 1
            continue

        # y-check: first line of next block on same line as last
        # line of current block.
        last_y0 = cur_lines[-1]["bbox"][1]
        first_y0 = nxt_lines[0]["bbox"][1]
        if abs(first_y0 - last_y0) >= _LINE_Y_TOLERANCE:
            i += 1
            continue

        # x-check: the continuation line starts at (or very near)
        # where the current block's last line ends.
        cur_x1 = cur_lines[-1]["bbox"][2]
        nxt_x0 = nxt_lines[0]["bbox"][0]
        gap = nxt_x0 - cur_x1
        if gap < -_ADJACENT_BLOCK_MAX_GAP or gap > _ADJACENT_BLOCK_MAX_GAP:
            i += 1
            continue

        # Transfer the first line of the next block into current.
        cur_lines.append(nxt_lines.pop(0))
        # Recompute current block bbox.
        all_bboxes = [ln["bbox"] for ln in cur_lines]
        cur["bbox"] = (
            min(b[0] for b in all_bboxes),
            min(b[1] for b in all_bboxes),
            max(b[2] for b in all_bboxes),
            max(b[3] for b in all_bboxes),
        )
        if not nxt_lines:
            # Next block is now empty — remove it.
            result.pop(i + 1)
        else:
            # Recompute next block bbox.
            all_bboxes = [ln["bbox"] for ln in nxt_lines]
            nxt["bbox"] = (
                min(b[0] for b in all_bboxes),
                min(b[1] for b in all_bboxes),
                max(b[2] for b in all_bboxes),
                max(b[3] for b in all_bboxes),
            )
            i += 1
        # Don't increment i — the current block might absorb more
        # continuation lines from the (now-modified) next block.

    return result


# Regex to extract the design-size suffix from CM font names
# (e.g. "CMMI10" → 10, "CMR7" → 7, "CMSY5" → 5).
_CM_DESIGN_SIZE_RE = re.compile(r"(\d+)$")


def _cm_design_size(font_name: str) -> int:
    """Extract the numeric design size from a CM font name.

    Returns 10 (body-text default) when no trailing digits are found.
    """
    m = _CM_DESIGN_SIZE_RE.search(font_name)
    return int(m.group(1)) if m else 10  # noqa: PLR2004


# ── Computer Modern glyph → Unicode remapping ─────────────────────
#
# TeX CM fonts use non-standard encodings.  When a PDF lacks a
# ToUnicode CMap, PyMuPDF falls back to raw character codes — e.g.
# CMEX10 glyph 0x70 (square root) is extracted as ASCII 'p'.
# These dicts remap the raw codes to correct Unicode equivalents.

# CMEX (TeX Math Extension) — large delimiters, radicals, operators.
# This font contains NO regular letters; any letter extracted from it
# is a mis-mapped glyph that needs correction.
_CMEX_UNICODE_MAP: dict[str, str] = {
    # Sized delimiters — Bigg (0x20-0x2F)
    # NOTE: space (0x20) is excluded — MuPDF inserts synthetic
    # inter-glyph spaces that would be incorrectly remapped.
    "!": ")",
    '"': "[",
    "#": "]",
    "$": "\u230a",
    "%": "\u230b",
    "&": "\u2308",
    "'": "\u2309",
    "(": "{",
    ")": "}",
    "*": "\u27e8",
    "+": "\u27e9",
    ",": "/",
    "-": "\u2216",
    ".": "/",
    "/": "\u2216",
    # Extensible glyph pieces (0x30-0x43)
    "0": "(",
    "1": ")",
    "2": "[",
    "3": "]",
    "4": "[",
    "5": "]",
    "6": "[",
    "7": "]",
    "8": "{",
    "9": "}",
    ":": "{",
    ";": "}",
    "<": "{",
    "=": "}",
    ">": "\u2502",
    "?": "\u2195",
    "@": "(",
    "A": ")",
    "B": "(",
    "C": ")",
    # Angle Big + operators text/display (0x44-0x61)
    "D": "\u27e8",
    "E": "\u27e9",
    "F": "\u2294",
    "G": "\u2294",  # ⊔ square union
    "H": "\u222e",
    "I": "\u222e",  # ∮ contour integral
    "J": "\u2299",
    "K": "\u2299",  # ⊙ circled dot
    "L": "\u2295",
    "M": "\u2295",  # ⊕ circled plus
    "N": "\u2297",
    "O": "\u2297",  # ⊗ circled times
    "P": "\u2211",
    "Q": "\u220f",  # ∑ ∏
    "R": "\u222b",  # ∫
    "S": "\u22c3",
    "T": "\u22c2",  # ⋃ ⋂
    "U": "\u228e",
    "V": "\u2227",
    "W": "\u2228",  # ⊎ ∧ ∨
    "X": "\u2211",
    "Y": "\u220f",
    "Z": "\u222b",  # ∑ ∏ ∫ display
    "[": "\u22c3",
    "\\": "\u22c2",
    "]": "\u228e",
    "^": "\u2227",
    "_": "\u2228",
    "`": "\u2210",
    "a": "\u2210",  # ∐ coproduct
    # Wide accents (0x62-0x67)
    "b": "\u02c6",
    "c": "\u02c6",
    "d": "\u02c6",  # ˆ hat
    "e": "\u02dc",
    "f": "\u02dc",
    "g": "\u02dc",  # ˜ tilde
    # Sized delimiters — Big (0x68-0x6F)
    "h": "[",
    "i": "]",
    "j": "\u230a",
    "k": "\u230b",  # ⌊ ⌋
    "l": "\u2308",
    "m": "\u2309",  # ⌈ ⌉
    "n": "{",
    "o": "}",
    # Radicals (0x70-0x76)
    "p": "\u221a",
    "q": "\u221a",
    "r": "\u221a",  # √
    "s": "\u221a",
    "t": "\u221a",
    "u": "\u2502",  # √ + │ ext
    "v": "\u221a",
    # Arrow parts (0x77-0x7E)
    "w": "\u21d5",
    "x": "\u2191",
    "y": "\u2193",  # ⇕ ↑ ↓
    "z": "\u23de",
    "{": "\u23de",  # ⏞ overbrace
    "|": "\u23df",
    "}": "\u23df",  # ⏟ underbrace
    "~": "\u21d1",  # ⇑
}

# CMSY (TeX Math Symbols) — operators, arrows, relations, delimiters.
_CMSY_UNICODE_MAP: dict[str, str] = {
    # Math operators at control-char positions (0x00-0x1F).
    # These are common TeX math symbols that PyMuPDF extracts as
    # control characters when the PDF lacks a ToUnicode CMap.
    "\x00": "\u2212",  # − minus sign
    "\x01": "\u22c5",  # ⋅ dot operator
    "\x02": "\u00d7",  # × multiplication sign
    "\x03": "\u2217",  # ∗ asterisk operator
    "\x04": "\u00f7",  # ÷ division sign
    "\x05": "\u22c4",  # ⋄ diamond operator
    "\x06": "\u00b1",  # ± plus-minus
    "\x07": "\u2213",  # ∓ minus-or-plus
    "\x08": "\u2295",  # ⊕ circled plus
    "\x09": "\u2296",  # ⊖ circled minus
    "\x0a": "\u2297",  # ⊗ circled times
    "\x0b": "\u2298",  # ⊘ circled division slash
    "\x0c": "\u2299",  # ⊙ circled dot
    "\x0d": "\u25cb",  # ○ white circle
    "\x0e": "\u2218",  # ∘ ring operator
    "\x0f": "\u2022",  # • bullet
    "\x10": "\u224d",  # ≍ equivalent to
    "\x11": "\u2261",  # ≡ identical to
    "\x12": "\u2286",  # ⊆ subset of or equal to
    "\x13": "\u2287",  # ⊇ superset of or equal to
    "\x14": "\u2264",  # ≤ less-than or equal to
    "\x15": "\u2265",  # ≥ greater-than or equal to
    "\x16": "\u227c",  # ≼ precedes or equal to
    "\x17": "\u227d",  # ≽ succeeds or equal to
    "\x18": "\u223c",  # ∼ tilde operator
    "\x19": "\u2248",  # ≈ almost equal to
    "\x1a": "\u2282",  # ⊂ subset of
    "\x1b": "\u2283",  # ⊃ superset of
    "\x1c": "\u226a",  # ≪ much less-than
    "\x1d": "\u226b",  # ≫ much greater-than
    "\x1e": "\u227a",  # ≺ precedes
    "\x1f": "\u227b",  # ≻ succeeds
    # Arrows (0x20-0x2E)
    # NOTE: space (0x20) is excluded — MuPDF inserts synthetic
    # inter-glyph spaces that would be incorrectly remapped.
    "!": "\u2192",  # →
    '"': "\u2191",
    "#": "\u2193",  # ↑ ↓
    "$": "\u2194",
    "%": "\u2197",
    "&": "\u2198",  # ↔ ↗ ↘
    "'": "\u2242",  # ≂
    "(": "\u21d0",
    ")": "\u21d2",  # ⇐ ⇒
    "*": "\u21d1",
    "+": "\u21d3",
    ",": "\u21d4",  # ⇑ ⇓ ⇔
    "-": "\u2196",
    ".": "\u2199",  # ↖ ↙
    # Relations + quantifiers (0x2F-0x40)
    "/": "\u221d",  # ∝
    "0": "\u2032",
    "1": "\u221e",  # ′ ∞
    "2": "\u2208",
    "3": "\u220b",  # ∈ ∋
    "4": "\u25b3",
    "5": "\u25bd",  # △ ▽
    "6": "/",
    "7": "\u21a6",  # slash overlay, ↦
    "8": "\u2200",
    "9": "\u2203",  # ∀ ∃
    ":": "\u00ac",
    ";": "\u2205",  # ¬ ∅
    "<": "\u211c",
    "=": "\u2111",  # ℜ ℑ
    ">": "\u22a4",
    "?": "\u22a5",  # ⊤ ⊥
    "@": "\u2135",  # ℵ
    # Script capitals (0x41-0x5A) — calligraphic A-Z.
    # BMP chars used where available; SMP Mathematical Script otherwise.
    "A": "\U0001d49c",  # 𝒜
    "B": "\u212c",  # ℬ
    "C": "\U0001d49e",  # 𝒞
    "D": "\U0001d49f",  # 𝒟
    "E": "\u2130",  # ℰ
    "F": "\u2131",  # ℱ
    "G": "\U0001d4a2",  # 𝒢
    "H": "\u210b",  # ℋ
    "I": "\u2110",  # ℐ
    "J": "\U0001d4a5",  # 𝒥
    "K": "\U0001d4a6",  # 𝒦
    "L": "\u2112",  # ℒ
    "M": "\u2133",  # ℳ
    "N": "\U0001d4a9",  # 𝒩
    "O": "\U0001d4aa",  # 𝒪
    "P": "\U0001d4ab",  # 𝒫
    "Q": "\U0001d4ac",  # 𝒬
    "R": "\u211b",  # ℛ
    "S": "\U0001d4ae",  # 𝒮
    "T": "\U0001d4af",  # 𝒯
    "U": "\U0001d4b0",  # 𝒰
    "V": "\U0001d4b1",  # 𝒱
    "W": "\U0001d4b2",  # 𝒲
    "X": "\U0001d4b3",  # 𝒳
    "Y": "\U0001d4b4",  # 𝒴
    "Z": "\U0001d4b5",  # 𝒵
    # Delimiters + operators (0x5B-0x7E)
    "[": "\u222a",
    "\\": "\u2229",  # ∪ ∩
    "]": "\u228e",
    "^": "\u2227",
    "_": "\u2228",  # ⊎ ∧ ∨
    "`": "\u22a2",
    "a": "\u22a3",  # ⊢ ⊣
    "b": "\u230a",
    "c": "\u230b",  # ⌊ ⌋
    "d": "\u2308",
    "e": "\u2309",  # ⌈ ⌉
    "f": "{",
    "g": "}",
    "h": "\u27e8",
    "i": "\u27e9",  # ⟨ ⟩
    "j": "\u2223",
    "k": "\u2225",  # ∣ ∥
    "l": "\u2195",
    "m": "\u21d5",  # ↕ ⇕
    "n": "\u2216",
    "o": "\u2240",  # ∖ ≀
    "p": "\u221a",
    "q": "\u2210",  # √ ∐
    "r": "\u2207",
    "s": "\u222b",  # ∇ ∫
    "t": "\u2294",
    "u": "\u2293",  # ⊔ ⊓
    "v": "\u2291",
    "w": "\u2292",  # ⊑ ⊒
    "x": "\u00a7",
    "y": "\u2020",
    "z": "\u2021",  # § † ‡
    # 0x7B-0x7E (¶ ♣ ♢ ♡) are omitted: when a ToUnicode CMap is
    # present, positions 0x66→{ 0x67→} 0x6A→| are already correct
    # and these entries would collide with those CMap-mapped values.
}


# MSBM (AMS Blackboard Bold) — double-struck letters (ℕ, ℝ, ℤ, …).
# Positions 0x41-0x5A are blackboard-bold A-Z.  BMP codepoints are
# used where available (ℂ, ℍ, ℕ, ℙ, ℚ, ℝ, ℤ); the rest fall back
# to SMP Mathematical Double-Struck (U+1D538–U+1D551).
# Positions 0x61-0x7A are blackboard-bold a-z (SMP U+1D552–U+1D56B).
# Positions 0x00-0x0D are additional AMS symbols (rarely extracted).
_MSBM_UNICODE_MAP: dict[str, str] = {
    # Uppercase blackboard bold (0x41-0x5A)
    "A": "\U0001d538",  # 𝔸
    "B": "\U0001d539",  # 𝔹
    "C": "\u2102",  # ℂ
    "D": "\U0001d53b",  # 𝔻
    "E": "\U0001d53c",  # 𝔼
    "F": "\U0001d53d",  # 𝔽
    "G": "\U0001d53e",  # 𝔾
    "H": "\u210d",  # ℍ
    "I": "\U0001d540",  # 𝕀
    "J": "\U0001d541",  # 𝕁
    "K": "\U0001d542",  # 𝕂
    "L": "\U0001d543",  # 𝕃
    "M": "\U0001d544",  # 𝕄
    "N": "\u2115",  # ℕ
    "O": "\U0001d546",  # 𝕆
    "P": "\u2119",  # ℙ
    "Q": "\u211a",  # ℚ
    "R": "\u211d",  # ℝ
    "S": "\U0001d54a",  # 𝕊
    "T": "\U0001d54b",  # 𝕋
    "U": "\U0001d54c",  # 𝕌
    "V": "\U0001d54d",  # 𝕍
    "W": "\U0001d54e",  # 𝕎
    "X": "\U0001d54f",  # 𝕏
    "Y": "\U0001d550",  # 𝕐
    "Z": "\u2124",  # ℤ
    # Lowercase blackboard bold (0x61-0x7A)
    "a": "\U0001d552",  # 𝕒
    "b": "\U0001d553",  # 𝕓
    "c": "\U0001d554",  # 𝕔
    "d": "\U0001d555",  # 𝕕
    "e": "\U0001d556",  # 𝕖
    "f": "\U0001d557",  # 𝕗
    "g": "\U0001d558",  # 𝕘
    "h": "\U0001d559",  # 𝕙
    "i": "\U0001d55a",  # 𝕚
    "j": "\U0001d55b",  # 𝕛
    "k": "\U0001d55c",  # 𝕜
    "l": "\U0001d55d",  # 𝕝
    "m": "\U0001d55e",  # 𝕞
    "n": "\U0001d55f",  # 𝕟
    "o": "\U0001d560",  # 𝕠
    "p": "\U0001d561",  # 𝕡
    "q": "\U0001d562",  # 𝕢
    "r": "\U0001d563",  # 𝕣
    "s": "\U0001d564",  # 𝕤
    "t": "\U0001d565",  # 𝕥
    "u": "\U0001d566",  # 𝕦
    "v": "\U0001d567",  # 𝕧
    "w": "\U0001d568",  # 𝕨
    "x": "\U0001d569",  # 𝕩
    "y": "\U0001d56a",  # 𝕪
    "z": "\U0001d56b",  # 𝕫
    # AMS extra symbols at low positions (0x00-0x0D)
    "0": "\u22d0",  # ⋐ double subset
    "1": "\u22d1",  # ⋑ double superset
    "2": "\u2288",  # ⊈ not subset or equal
    "3": "\u2289",  # ⊉ not superset or equal
    "4": "\u2270",  # ≰ not less-equal
    "5": "\u2271",  # ≱ not greater-equal
    "6": "\u2268",  # ≨ less but not equal
    "7": "\u2269",  # ≩ greater but not equal
}

# CMBSY (Computer Modern Bold Math Symbols) — same encoding as CMSY.
_CMBSY_UNICODE_MAP = _CMSY_UNICODE_MAP


def _remap_cm_char(ch: str, font_name: str) -> str:
    """Remap a raw-extracted character to its correct Unicode glyph.

    TeX CM fonts use non-standard encodings.  When a PDF lacks a
    ToUnicode CMap, PyMuPDF outputs the raw character code as ASCII.
    This function converts those mis-mapped characters to correct
    Unicode using the CMEX / CMSY / MSBM encoding tables.

    If the font is not a recognized math font, or the character is
    not in the map (e.g. already correctly mapped via a ToUnicode
    CMap), the character is returned unchanged.

    The Unicode replacement character (U+FFFD) is suppressed: it
    represents an undecoded glyph (e.g. CMEX delimiter extensions)
    that would render as a garbled box in the overlay.
    """
    # Suppress undecoded glyphs from CM fonts
    if ch == "\ufffd" and any(font_name.startswith(p) for p in ("CM", "MSB")):
        return ""
    if font_name.startswith("CMEX"):
        return _CMEX_UNICODE_MAP.get(ch, ch)
    if font_name.startswith("CMSY"):
        return _CMSY_UNICODE_MAP.get(ch, ch)
    if font_name.startswith("CMBSY"):
        return _CMBSY_UNICODE_MAP.get(ch, ch)
    if font_name.startswith("MSBM"):
        return _MSBM_UNICODE_MAP.get(ch, ch)
    return ch


# Characters used as arrow shafts in TeX composed sequences.
_DASH_CHARS = frozenset({"-", "\u2212", "\u2013"})  # hyphen, minus, en-dash

# Minimum element count to attempt composed-sequence collapsing.
_MIN_COMPOSE_LEN = 2


def _skip_middle(
    remapped: list[tuple[str, str]],
    start: int,
    middle_set: frozenset[str],
) -> int:
    """Return index after consecutive chars matching *middle_set*."""
    j = start
    while j < len(remapped) and remapped[j][0] in middle_set:
        j += 1
    return j


def _try_compose(  # noqa: PLR0913
    remapped: list[tuple[str, str]],
    i: int,
    middle_set: frozenset[str],
    suffix_ch: str,
    with_middle: str,
    without_middle: str,
) -> tuple[str, int] | None:
    """Try prefix + middles + suffix pattern, return (char, end_index).

    *with_middle* is used when middle chars are present;
    *without_middle* is used when no middle chars exist (prefix + suffix).
    If *without_middle* is empty the match requires at least one middle.
    """
    j = _skip_middle(remapped, i + 1, middle_set)
    has_mid = j > i + 1
    if j < len(remapped) and remapped[j][0] == suffix_ch:
        if has_mid:
            return with_middle, j + 1
        if without_middle:
            return without_middle, j + 1
    # No suffix — check middle-only patterns (e.g. ← + dashes, ⇐ + =)
    if has_mid and not without_middle:
        return with_middle, j
    return None


def _collapse_tex_composed(
    remapped: list[tuple[str, str, str | None]],
) -> list[tuple[str, str, str | None]]:
    """Collapse TeX-composed multi-glyph sequences to single Unicode chars.

    TeX renders certain symbols (long arrows, mapsto variants) as
    overlapping glyphs from different CM fonts.  After per-character
    remapping, these appear as two or three Unicode characters that
    should be a single symbol.

    Each entry is ``(char, font, role)`` where *role* is ``"sup"``,
    ``"sub"``, or ``None``.  The role of the first glyph in a
    collapsed group is preserved.

    Supported collapses:

    * ``↦ (+ dashes) + →``  →  ``↦`` (mapsto) or ``⟼`` (longmapsto)
    * ``dashes + →``  →  ``⟶`` (longrightarrow)
    * ``← + dashes``  →  ``⟵`` (longleftarrow)
    * ``← + dashes + →``  →  ``⟷`` (longleftrightarrow)
    * ``= + ⇒``  →  ``⟹`` (Longrightarrow)
    * ``⇐ + =``  →  ``⟸`` (Longleftarrow)
    * ``⇐ + = + ⇒``  →  ``⟺`` (Longleftrightarrow)
    """
    if len(remapped) < _MIN_COMPOSE_LEN:
        return remapped

    _eq = frozenset({"="})
    result: list[tuple[str, str, str | None]] = []
    i = 0
    n = len(remapped)
    while i < n:
        ch = remapped[i][0]
        font = remapped[i][1]
        role = remapped[i][2] if len(remapped[i]) > 2 else None  # noqa: PLR2004
        hit: tuple[str, int] | None = None

        if ch == "\u21a6":  # ↦ mapsto / longmapsto
            hit = _try_compose(
                remapped,
                i,
                _DASH_CHARS,
                "\u2192",
                "\u27fc",
                "\u21a6",
            )
        elif ch == "\u2190":  # ← longleft(right)arrow
            j = _skip_middle(remapped, i + 1, _DASH_CHARS)
            if j > i + 1:  # has dashes
                has_right = j < n and remapped[j][0] == "\u2192"
                hit = ("\u27f7", j + 1) if has_right else ("\u27f5", j)
        elif ch == "\u21d0":  # ⇐ Longleft(right)arrow
            j = _skip_middle(remapped, i + 1, _eq)
            if j > i + 1:  # has equals
                has_right = j < n and remapped[j][0] == "\u21d2"
                hit = ("\u27fa", j + 1) if has_right else ("\u27f8", j)
        elif ch in _DASH_CHARS:  # longrightarrow (prefix is itself a dash)
            hit = _try_compose(
                remapped,
                i,
                _DASH_CHARS,
                "\u2192",
                "\u27f6",
                "\u27f6",
            )
        elif ch == "=":  # Longrightarrow (prefix is itself an =)
            hit = _try_compose(
                remapped,
                i,
                _eq,
                "\u21d2",
                "\u27f9",
                "\u27f9",
            )

        if hit:
            result.append((hit[0], font, role))
            i = hit[1]
        else:
            # Normalize to 3-tuple for backward compatibility
            result.append((ch, font, role))
            i += 1
    return result


def _capture_glyph_image(
    page: Any,  # noqa: ANN401
    bbox: tuple[float, float, float, float],
    pymupdf: Any,  # noqa: ANN401
) -> str:
    """Render a small glyph region as an inline ``<img>`` tag.

    Captures the page region at 2× resolution for crisp rendering,
    then returns an HTML ``<img>`` tag with base64-encoded PNG data
    sized to the original glyph's point dimensions.

    Args:
        page: PyMuPDF Page object.
        bbox: (x0, y0, x1, y1) bounding box in points.
        pymupdf: The pymupdf module reference.

    Returns:
        HTML ``<img>`` tag string with inline base64 data.
    """
    import base64  # noqa: PLC0415

    clip = pymupdf.Rect(bbox)
    if clip.is_empty or clip.is_infinite:
        return ""
    pix = page.get_pixmap(clip=clip, dpi=144)
    img_data = pix.tobytes("png")
    b64 = base64.b64encode(img_data).decode("ascii")
    w = clip.width
    h = clip.height
    return f'<img src="data:image/png;base64,{b64}" width="{w:.1f}" height="{h:.1f}">'


# Sentinel font name for inline glyph images stored in math_map.
_IMG_FONT = "_IMG_"


def _merge_math_spans(  # noqa: PLR0912, PLR0913, PLR0915
    span_texts: list[str],
    line_span_items: list[dict[str, Any]],
    math_map: dict[str, Any],
    ph_counter: int,
    page: Any = None,  # noqa: ANN401
    pymupdf: Any = None,  # noqa: ANN401
    line_dom_size: float = 0,
    line_y0: float = 0,
    line_y1: float = 0,
) -> tuple[list[str], list[dict[str, Any]], int]:
    """Merge consecutive math-font spans into placeholders.

    Walks *span_texts* / *line_span_items* (parallel, 1:1) and groups
    consecutive math-font spans into a single placeholder token
    ``⟪N⟫``.  The mapping ``placeholder → char_font_list`` is added to
    *math_map*, where each value is a list of ``(char, font_name, role)``
    tuples preserving per-character font identity and super/subscript
    role (``"sup"``, ``"sub"``, or ``None``).

    When *page* and *pymupdf* are provided, undecoded glyphs
    (``U+FFFD``) from CM fonts are captured as inline images
    instead of being suppressed.

    Returns:
        (merged_texts, merged_items, updated_counter)
    """
    line_mid = (line_y0 + line_y1) / 2 if line_y1 > line_y0 else 0

    merged_texts: list[str] = []
    merged_items: list[dict[str, Any]] = []
    i = 0
    while i < len(span_texts):
        item = line_span_items[i]
        if _is_math_font(item.get("font", "")):
            # Accumulate consecutive math spans with per-char fonts
            char_fonts: list[tuple[str, str, str | None]] = []
            acc_item = dict(item)  # shallow copy for the merged entry
            group_max_sz = 0.0  # track max span size in this group
            j = i
            while j < len(span_texts):
                jitem = line_span_items[j]
                if not _is_math_font(jitem.get("font", "")):
                    break
                font = jitem.get("font", "").split("+")[-1]
                is_cm = any(font.startswith(p) for p in ("CM", "MSB"))

                # Determine superscript/subscript role from position
                span_sz = jitem.get("size", 12.0)
                group_max_sz = max(group_max_sz, span_sz)
                role: str | None = None
                if (
                    line_dom_size > 0
                    and span_sz < line_dom_size * _SUP_SUB_SIZE_RATIO
                    and line_mid > 0
                ):
                    span_mid = (jitem["sy0"] + jitem["sy1"]) / 2
                    role = "sup" if span_mid < line_mid else "sub"

                # Check if span has any undecoded glyphs that
                # should be captured as inline images.  Control
                # chars (< 0x20) from CMEX are delimiter pieces
                # with no Unicode equivalent.  CMSY control chars
                # (operators like ≤, ×, ±) DO have remap entries
                # and are processed as text instead.
                span_text = span_texts[j]
                needs_image = False
                if is_cm:
                    for c in span_text:
                        if c == "\ufffd" or ord(c) < _CTRL_CHAR_LIMIT:
                            rc = _remap_cm_char(c, font)
                            if (
                                not rc
                                or rc == c
                                or (len(rc) == 1 and ord(rc) < _CTRL_CHAR_LIMIT)
                            ):
                                needs_image = True
                                break
                if needs_image and page is not None and pymupdf is not None:
                    # Capture entire span bbox as one inline image
                    bbox = (
                        jitem["sx0"],
                        jitem["sy0"],
                        jitem["sx1"],
                        jitem["sy1"],
                    )
                    img_tag = _capture_glyph_image(
                        page,
                        bbox,
                        pymupdf,
                    )
                    if img_tag:
                        char_fonts.append(
                            (img_tag, _IMG_FONT, None),
                        )
                    # else: suppress (empty/invalid bbox)
                else:
                    for ch in span_text:
                        # Operators like √ must keep normal size —
                        # never shrink/raise as sup/sub.
                        ch_role = role
                        if ch in _MATH_NO_ROLE_CHARS or (
                            font.startswith("CMEX")
                            and _remap_cm_char(ch, font) in _MATH_NO_ROLE_CHARS
                        ):
                            ch_role = None
                        char_fonts.append((ch, font, ch_role))
                if j > i:
                    # Extend bbox to cover all merged spans
                    acc_item["sx1"] = jitem["sx1"]
                    acc_item["sy1"] = max(
                        acc_item["sy1"],
                        jitem["sy1"],
                    )
                j += 1

            # Re-evaluate roles using the group's local max size.
            # In fractions/denominators all chars are uniformly smaller
            # than line_dom_size, making the line-level classification
            # tag everything as sub/sup.  Re-check against the group's
            # own dominant design size: chars whose design size is close
            # to the group's max are "normal" within this context and
            # should lose their role.
            if (
                group_max_sz > 0
                and group_max_sz < line_dom_size * _SUP_SUB_SIZE_RATIO
                and len(char_fonts) > 1
            ):
                group_max_ds = max(_cm_design_size(ft) for _, ft, _ in char_fonts)
                threshold = group_max_ds * _SUP_SUB_SIZE_RATIO
                char_fonts = [
                    (ch, ft, None if _cm_design_size(ft) >= threshold else role)
                    for ch, ft, role in char_fonts
                ]

            # Create placeholder
            ph = f"{_MATH_PH_START}{ph_counter}{_MATH_PH_END}"
            math_map[ph] = char_fonts
            ph_counter += 1
            merged_texts.append(ph)
            acc_item["text"] = ph
            acc_item["_is_math"] = True
            acc_item["_ph_key"] = ph
            merged_items.append(acc_item)
            i = j
        else:
            merged_texts.append(span_texts[i])
            merged_items.append(item)
            i += 1
    return merged_texts, merged_items, ph_counter


def _reclassify_merged_math_roles(
    line_spans_data: list[list[dict[str, Any]]],
    math_map: dict[str, Any],
    line_y_positions: list[float],
    line_y_ends: list[float],
    line_font_sizes: list[float],
) -> None:
    """Re-evaluate unclassified math roles after same-y merging.

    ``_merge_math_spans`` runs per raw line *before* same-y merging.
    A math span that was alone on its line (e.g. a fraction numerator
    "1") has ``span_mid == line_mid``, so the size-based classifier
    leaves ``role=None``.  The fallback in ``_restore_math_placeholders``
    then blindly picks ``"sub"``, which is wrong for numerators.

    After same-y / subscript-fragment merging, the math span now shares
    a line with body text, providing a proper dominant size and midpoint.
    This function finds such unclassified math placeholders and assigns
    the correct role (``"sup"`` or ``"sub"``) using the merged line
    geometry.
    """
    for idx, spans in enumerate(line_spans_data):
        line_mid = (line_y_positions[idx] + line_y_ends[idx]) / 2
        dom_sz = line_font_sizes[idx]
        if dom_sz <= 0 or line_mid <= 0:
            continue
        for span in spans:
            ph_key = span.get("_ph_key")
            if not ph_key or ph_key not in math_map:
                continue
            char_fonts = math_map[ph_key]
            if isinstance(char_fonts, str):
                continue
            # Only fix placeholders where ALL chars have role=None
            # (i.e. none were classified during extraction).
            if not all(
                (e[2] if len(e) > 2 else None) is None  # noqa: PLR2004
                for e in char_fonts
            ):
                continue
            span_sz = span.get("size", 12.0)
            if span_sz >= dom_sz * _SUP_SUB_SIZE_RATIO:
                continue
            span_mid = (span.get("sy0", 0) + span.get("sy1", 0)) / 2
            if span_mid <= 0:
                continue
            role = "sup" if span_mid < line_mid else "sub"
            math_map[ph_key] = [(ch, ft, role) for ch, ft, _old in char_fonts]


def _absorb_math_sub_labels(  # noqa: PLR0912
    line_texts: list[str],
    line_spans_data: list[list[dict[str, Any]]],
    math_map: dict[str, Any],
    line_dom_sizes: list[float],
) -> None:
    """Absorb body-font subscript labels following math placeholders.

    TeX renders subscript labels (e.g. ``schematic`` in R²_schematic)
    in the body/text font at subscript size.  After same-y and
    fragment merges, these labels sit right after the math placeholder
    in the span list.  This function detects them and absorbs their
    characters into the placeholder's ``char_fonts``, then removes the
    absorbed spans so the LLM does not translate variable-name
    fragments.

    Modifies *line_spans_data*, *line_texts*, and *math_map* in place.
    """
    for li, spans in enumerate(line_spans_data):
        if not spans:
            continue
        dom_sz = line_dom_sizes[li] if li < len(line_dom_sizes) else 12.0
        if dom_sz <= 0:
            continue

        modified = False
        i = 0
        while i < len(spans):
            s = spans[i]
            if not s.get("_is_math"):
                i += 1
                continue

            ph_key = s.get("_ph_key")
            if not ph_key or ph_key not in math_map:
                i += 1
                continue

            # Skip separator spans (inserted by line merges) that
            # lack position info — they are not real text.
            j = i + 1
            while j < len(spans) and "sx0" not in spans[j]:
                j += 1

            if j >= len(spans):
                i += 1
                continue

            # Collect consecutive subscript-sized body-font spans
            label_start = j
            label_end = j
            while label_end < len(spans):
                ls = spans[label_end]
                if "sx0" not in ls:
                    break  # separator
                if ls.get("_is_math"):
                    break
                if _is_math_font(ls.get("font", "")):
                    break
                if ls.get("size", 12.0) >= dom_sz * _SUP_SUB_SIZE_RATIO:
                    break
                label_end += 1

            if label_end == label_start:
                i += 1
                continue

            # Joined text must be a single word (no spaces)
            label_text = "".join(
                ls.get("text", "") for ls in spans[label_start:label_end]
            ).strip()
            if not label_text or " " in label_text:
                i += 1
                continue

            # Absorb into the math placeholder as subscript
            for ls in spans[label_start:label_end]:
                font = ls.get("font", "").split("+")[-1]
                for ch in ls.get("text", ""):
                    math_map[ph_key].append(
                        (ch, font, "sub"),
                    )

            # Remove absorbed spans (and any skipped separators)
            del spans[i + 1 : label_end]
            modified = True
            i += 1

        if modified:
            line_texts[li] = "".join(s.get("text", "") for s in spans)


def _restore_math_placeholders(
    text: str,
    math_map: dict[str, Any],
) -> str:
    """Replace ``⟪N⟫`` placeholders with Unicode text.

    Each placeholder maps to a list of ``(char, font_name, role)``
    tuples.  *role* is ``"sup"``, ``"sub"``, or ``None`` (determined
    from span y-position during extraction).  When *role* is ``None``,
    the function falls back to the CM design-size heuristic (smaller
    design size → subscript).

    Characters from italic math fonts (CMMI*) are wrapped in ``<i>``
    tags.  This avoids re-embedding CM subset fonts (which share a
    common PostScript family name and break in external PDF viewers).
    """
    if not math_map:
        return text
    # Compute block-level base design size across ALL placeholders so
    # single-char subscript-only placeholders (e.g. ⟪2⟫ = ('2','CMR7'))
    # can still detect sub/sup by comparing against the block's main size.
    global_base_ds = max(
        (
            _cm_design_size(entry[1])
            for v in math_map.values()
            if not isinstance(v, str)
            for entry in v
        ),
        default=10,  # noqa: PLR2004
    )
    for ph, char_fonts in math_map.items():
        if isinstance(char_fonts, str):
            # Legacy format (plain text) — fallback
            text = text.replace(ph, char_fonts)
            continue
        # Determine the base (largest) design size in the group.
        # Multi-char placeholders have enough local context to detect
        # sub/sup within the group.  Using global_base_ds on multi-char
        # groups would wrongly classify TeX fraction content (ds=7) as
        # subscript when the main line uses ds=10.
        # Single-char placeholders lack local context, so they fall
        # back to global_base_ds (e.g. isolated ₂ in ∆*₂).
        # CMEX fonts contain operators/delimiters, never subscripts.
        local_ds = max(
            (_cm_design_size(entry[1]) for entry in char_fonts),
            default=10,  # noqa: PLR2004
        )
        if len(char_fonts) == 1 and not char_fonts[0][1].startswith("CMEX"):
            base_ds = max(local_ds, global_base_ds)
        else:
            base_ds = local_ds
        # Remap characters and collapse TeX-composed sequences.
        # TeX renders composite arrows (e.g. \mapsto, \longrightarrow)
        # as overlapping glyphs; _collapse_tex_composed merges them
        # into single Unicode characters.
        remapped: list[tuple[str, str, str | None]] = [
            (
                _remap_cm_char(entry[0], entry[1]),
                entry[1],
                entry[2] if len(entry) > 2 else None,  # noqa: PLR2004
            )
            for entry in char_fonts
        ]
        remapped = _collapse_tex_composed(remapped)

        # Group consecutive chars by (italic, role) status
        html_parts: list[str] = []
        cur_key: tuple[bool, str | None] | None = None
        cur_chars: list[str] = []
        for ch, font, role in remapped:
            is_italic = font.startswith("CMMI")
            # Use stored role; fall back to design-size heuristic
            effective_role = role
            if effective_role is None and _cm_design_size(font) < base_ds:
                effective_role = "sub"
            key = (is_italic, effective_role)
            if key != cur_key:
                if cur_chars:
                    html_parts.append(
                        _wrap_math_chars("".join(cur_chars), cur_key),
                    )
                cur_key = key
                cur_chars = [ch]
            else:
                cur_chars.append(ch)
        if cur_chars and cur_key is not None:
            html_parts.append(
                _wrap_math_chars("".join(cur_chars), cur_key),
            )
        text = text.replace(ph, "".join(html_parts))
    return text


def _wrap_math_chars(
    chars: str,
    key: tuple[bool, str | None],
) -> str:
    """Wrap math characters in appropriate HTML tags.

    Args:
        chars: The concatenated characters.
        key: ``(is_italic, role)`` tuple where *role* is ``"sup"``,
             ``"sub"``, or ``None``.

    Returns:
        HTML string with ``<i>`` and/or ``<sup>``/``<sub>`` wrapping.
    """
    is_italic, role = key
    result = chars
    if is_italic:
        result = f"<i>{result}</i>"
    if role == "sub":
        result = f"<sub>{result}</sub>"
    elif role == "sup":
        result = f"<sup>{result}</sup>"
    return result


def _body_len(b: dict[str, Any]) -> int:
    """Non-math (body) text length of a block.

    Returns the length of text remaining after removing all math
    placeholders and surrounding whitespace.  A block whose body is
    only whitespace and placeholders returns 0.
    """
    mm = b.get("_math_map", {})
    text = b.get("text", "")
    for k in mm:
        text = text.replace(k, "")
    return len(text.strip())


# Display equations wider than this fraction of page width are kept as
# body text (they likely contain substantial prose, not just labels).
_DISPLAY_EQ_MAX_WIDTH_RATIO = 0.5

# Maximum offset (as fraction of page width) between block centre and
# page centre for a block to be considered horizontally centred.
_DISPLAY_EQ_CENTER_TOL = 0.1


def _is_display_equation(b: dict[str, Any], page_width: float) -> bool:
    """Return True if *b* is a display equation with body-font labels.

    TeX display equations like ``R²_schematic = max(R²_linear, R²_poly)``
    use body fonts for subscript labels ("schematic", "linear") so
    ``_body_len > 0``.  They are distinguished from real body text by
    being **narrow** (< 50 % page width) **and centred** on the page.
    Body text paragraphs start at the left margin and are not centred.
    """
    if not b.get("_math_map"):
        return False
    rect = b.get("rect", (0, 0, 0, 0))
    block_w = rect[2] - rect[0]
    if block_w >= page_width * _DISPLAY_EQ_MAX_WIDTH_RATIO:
        return False
    # Check horizontal centring
    block_cx = (rect[0] + rect[2]) / 2
    page_cx = page_width / 2
    return abs(block_cx - page_cx) <= page_width * _DISPLAY_EQ_CENTER_TOL


def _coalesce_line_extents(
    a: dict[str, Any],
    b: dict[str, Any],
    ra: list[float] | tuple[float, ...],
    rb: list[float] | tuple[float, ...],
) -> tuple[
    list[tuple[float, float]],
    list[float],
    list[float],
]:
    """Merge line-extent fragments from two blocks into full lines.

    Fragments on the same y-row (same printed line) are coalesced
    so ``_detect_block_alignment`` sees complete line widths instead
    of partial sub-block fragments.

    Returns (extents, sizes, y_mids) ready to store on the merged block.
    """
    a_ext = a.get("_line_extents", [(ra[0], ra[2])])
    b_ext = b.get("_line_extents", [(rb[0], rb[2])])
    a_ymids = a.get("_line_y_mids", [(ra[1] + ra[3]) / 2.0])
    b_ymids = b.get("_line_y_mids", [(rb[1] + rb[3]) / 2.0])
    a_sizes = a.get("_line_sizes", [a.get("font_size", 12.0)])
    b_sizes = b.get("_line_sizes", [b.get("font_size", 12.0)])
    all_ext = a_ext + b_ext
    all_ymids = a_ymids + b_ymids
    all_sizes = a_sizes + b_sizes
    # Group fragments by y-midpoint proximity (within font size).
    frag_tol = max(a.get("font_size", 12.0), b.get("font_size", 12.0))
    order = sorted(range(len(all_ymids)), key=lambda k: all_ymids[k])
    merged_ext: list[tuple[float, float]] = []
    merged_sizes: list[float] = []
    merged_ymids: list[float] = []
    for k in order:
        ym = all_ymids[k]
        ex = all_ext[k]
        sz = all_sizes[k]
        if merged_ymids and abs(ym - merged_ymids[-1]) < frag_tol:
            # Same y-row: widen the extent.
            prev = merged_ext[-1]
            merged_ext[-1] = (min(prev[0], ex[0]), max(prev[1], ex[1]))
            merged_sizes[-1] = max(merged_sizes[-1], sz)
        else:
            merged_ext.append(ex)
            merged_sizes.append(sz)
            merged_ymids.append(ym)
    return merged_ext, merged_sizes, merged_ymids


def _merge_two_math_blocks(  # noqa: PLR0912
    a: dict[str, Any],
    b: dict[str, Any],
) -> dict[str, Any]:
    """Merge two overlapping blocks into one, renumbering placeholders.

    When blocks are on separate visual lines, the higher block (smaller
    y0) provides text first.  When blocks share the same visual line
    (significant vertical overlap), the leftmost block (smaller x0)
    provides text first — this preserves left-to-right reading order
    for inline formula fragments split across blocks by PyMuPDF.

    Placeholders in the second block are renumbered so indices don't
    collide with the first block's placeholders.

    Font properties are taken from the block with more body text.
    """
    ra, rb = a["rect"], b["rect"]
    # Determine if blocks share the same visual line.
    # Use the *taller* block's height as reference so that a short
    # inline fragment overlapping the top of a tall multi-paragraph
    # block is NOT treated as same-line.
    overlap_y = min(ra[3], rb[3]) - max(ra[1], rb[1])
    max_height = max(ra[3] - ra[1], rb[3] - rb[1])
    if max_height > 0 and overlap_y > max_height * 0.5:
        # Same visual line — order left-to-right by x0.
        if ra[0] > rb[0]:
            a, b = b, a
    elif ra[1] > rb[1]:
        # Different lines — order top-to-bottom by y0.
        a, b = b, a

    a_map = dict(a.get("_math_map", {}))
    b_map = dict(b.get("_math_map", {}))

    # Renumber b's placeholders: offset by a's placeholder count.
    offset = len(a_map)
    b_text = b.get("text", "")
    if offset and b_map:
        b_text = _MATH_PH_RE.sub(
            lambda m: f"{_MATH_PH_START}{int(m.group(1)) + offset}{_MATH_PH_END}",
            b_text,
        )
    new_b_map: dict[str, Any] = {}
    for ph, orig in b_map.items():
        m = _MATH_PH_RE.match(ph)
        if m:
            new_n = int(m.group(1)) + offset
            new_ph = f"{_MATH_PH_START}{new_n}{_MATH_PH_END}"
            new_b_map[new_ph] = orig
        else:
            new_b_map[ph] = orig

    merged_map = {**a_map, **new_b_map}
    merged_text = a.get("text", "") + " " + b_text

    # Union of bounding boxes.
    ra, rb = a["rect"], b["rect"]
    merged_rect = [
        min(ra[0], rb[0]),
        min(ra[1], rb[1]),
        max(ra[2], rb[2]),
        max(ra[3], rb[3]),
    ]

    # Keep font properties from block with more body text.
    primary = a if _body_len(a) >= _body_len(b) else b

    merged: dict[str, Any] = {
        "rect": merged_rect,
        "text": merged_text,
        "font_size": primary.get("font_size", 12.0),
        "font_name": primary.get("font_name", ""),
        "color": primary.get("color", 0),
        "bold": primary.get("bold", False),
        "italic": primary.get("italic", False),
        "font_flags": primary.get("font_flags", 0),
        "text_align": primary.get("text_align", "left"),
    }
    if merged_map:
        merged["_math_map"] = merged_map
    if a.get("has_mixed_formatting") or b.get("has_mixed_formatting"):
        merged["has_mixed_formatting"] = True
    if a.get("is_table_cell") or b.get("is_table_cell"):
        merged["is_table_cell"] = True
    # Merge line extents for alignment re-derivation after merge.
    m_ext, m_sizes, m_ymids = _coalesce_line_extents(a, b, ra, rb)
    merged["_line_extents"] = m_ext
    merged["_line_sizes"] = m_sizes
    merged["_line_y_mids"] = m_ymids
    # Carry forward optional keys from the primary block.
    for key in (
        "para_indents",
        "para_colors",
        "text_indent",
        "is_space_between",
        "is_vertical",
    ):
        if key in primary:
            merged[key] = primary[key]
    return merged


def _is_split_paragraph(  # noqa: PLR0911
    a: dict[str, Any],
    b: dict[str, Any],
) -> bool:
    """Return True when *a* and *b* are halves of a split paragraph.

    PyMuPDF sometimes splits a paragraph into two blocks when math-font
    subscripts/superscripts create overlapping bboxes.  The halves are
    detected by four criteria:

    1. **Spatial proximity**: block B's top is near block A's bottom
       (within one line height), and their x-ranges overlap significantly
       (same column, not a two-column false match).
    2. **Font size similarity**: both blocks share the same dominant font
       size (within 20%), since split halves come from the same paragraph.
    3. **Mid-sentence end**: block A does not end with ``.!?``.
    4. **Lowercase continuation**: block B starts with a lowercase letter.

    Math placeholders are stripped before text checks.
    """
    ra, rb = a["rect"], b["rect"]
    # Order by vertical position.
    if ra[1] > rb[1]:
        a, b = b, a
        ra, rb = rb, ra
    # ── Spatial checks ──────────────────────────────────────────────
    # X-ranges must overlap (same column).
    x_overlap = min(ra[2], rb[2]) - max(ra[0], rb[0])
    a_width = ra[2] - ra[0]
    b_width = rb[2] - rb[0]
    min_width = min(a_width, b_width) if min(a_width, b_width) > 0 else 1.0
    if x_overlap < min_width * 0.5:
        return False
    # Block B top must be near block A bottom (within one line height).
    a_height = ra[3] - ra[1]
    line_height = a_height if a_height > 0 else 12.0
    if rb[1] > ra[3] + line_height:
        return False
    # ── Font size check ─────────────────────────────────────────────
    # Split halves come from the same paragraph — sizes must be close.
    a_size = a.get("font_size", 12.0)
    b_size = b.get("font_size", 12.0)
    max_size = max(a_size, b_size)
    if max_size > 0 and min(a_size, b_size) / max_size < _SPLIT_PARA_SIZE_RATIO:
        return False
    # ── Text checks ─────────────────────────────────────────────────
    a_text = _MATH_PH_RE.sub("", a.get("text", "")).rstrip()
    b_text = _MATH_PH_RE.sub("", b.get("text", "")).lstrip()
    if not a_text or not b_text:
        return False
    # Block a does NOT end a sentence.
    if a_text[-1] in ".!?":
        return False
    # Block b starts with a lowercase letter — clear continuation.
    for ch in b_text:
        if ch.isalpha():
            return ch.islower()
        break
    return False


def _merge_overlapping_math_blocks(
    blocks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge blocks that overlap vertically when at least one has math.

    When two blocks overlap vertically and at least one carries
    ``_math_map``, overlaid translations collide visually.  Instead of
    dropping one, both are merged into a single block so all body text
    is preserved and only one overlay rectangle is rendered.

    Blocks with small overlaps (below ``_MATH_MERGE_MIN_OVERLAP``) are
    also merged when text-continuity analysis shows they are halves of
    the same paragraph that PyMuPDF split due to math subscripts.

    Placeholders in the absorbed block are renumbered to avoid
    collisions with the primary block's placeholder indices.
    """
    if len(blocks) < 2:  # noqa: PLR2004
        return blocks

    result = list(blocks)
    changed = True
    while changed:
        changed = False
        for i in range(len(result)):
            ri = result[i]["rect"]
            has_math_i = bool(result[i].get("_math_map"))
            for j in range(i + 1, len(result)):
                rj = result[j]["rect"]
                has_math_j = bool(result[j].get("_math_map"))
                # Only care when at least one block has math content
                if not has_math_i and not has_math_j:
                    continue
                # Skip vertical blocks: they span tall, narrow strips
                # (e.g. arXiv sidebar, axis labels) that bridge unrelated
                # content blocks and cause mega-merges.
                if result[i].get("is_vertical") or result[j].get("is_vertical"):
                    continue
                # Check vertical overlap (y-ranges intersect).
                overlap = min(ri[3], rj[3]) - max(ri[1], rj[1])
                # Large overlap: always merge (visual collision).
                # Small overlap (> 0): merge only if text analysis
                # shows the blocks are halves of a split paragraph.
                is_split = (
                    overlap > 0
                    and overlap < _MATH_MERGE_MIN_OVERLAP
                    and _is_split_paragraph(result[i], result[j])
                )
                should_merge = overlap >= _MATH_MERGE_MIN_OVERLAP or is_split
                if should_merge:
                    result[i] = _merge_two_math_blocks(
                        result[i],
                        result[j],
                    )
                    # Re-derive alignment from merged line extents.
                    # Individual sub-block alignments are unreliable
                    # when math subscripts fragment lines across
                    # blocks (each sees only partial line extents).
                    merged_ext = result[i].get("_line_extents", [])
                    merged_sizes = result[i].get("_line_sizes")
                    if merged_ext:
                        new_align, _ = _detect_block_alignment(
                            merged_ext,
                            result[i]["rect"],
                            merged_sizes,
                        )
                        result[i]["text_align"] = new_align
                    result.pop(j)
                    changed = True
                    break
            if changed:
                break
    return result


# When two same-y text segments are separated by a gap wider than this
# fraction of the block width, the block is a "space-between" layout
# (e.g. page headers with left-side and right-side text).
_SPACE_BETWEEN_GAP_RATIO = 0.2
# Minimum absolute gap (pt) for space-between classification.  Prevents
# narrow section titles like "6  Results" (gap ≈ 12pt) from being
# misclassified as space-between layout.  Smallest legitimate gap
# observed is ~57pt (table data); false positives are ≤ 12pt.
_SPACE_BETWEEN_MIN_GAP = 20.0

# Minimum indent (in multiples of font size) for a line to be
# considered the first line of a new paragraph.
_INDENT_FACTOR = 0.5
# Maximum indent (in multiples of font size).  Shifts larger than this
# are short lines, not indents (e.g. RTL last line in LTR-detected
# block).
_MAX_INDENT_FACTOR = 3.0
# A line whose width is less than this ratio of the block width is the
# last line of a paragraph.  Only used for justified text where
# mid-paragraph lines span the full block width.
_SHORT_LINE_RATIO = 0.90
# Tolerance when comparing dominant font sizes between lines in the
# list-join Pass 2 demote guard.  Lines whose sizes differ by more
# than this are treated as belonging to different typographic levels
# (e.g. heading vs body), preventing a false demote.
_LIST_DEMOTE_SIZE_TOL = 0.1
# Dynamic short-line threshold for table cells.  Narrow cells need a
# lower threshold (word wrapping leaves large gaps), wide cells need
# a higher one (wrapped lines fill most of the width).
# threshold = 1.0 - _CELL_WRAP_GAP_FACTOR * font_size / cell_width,
# clamped to [_CELL_SHORT_LINE_MIN, _CELL_SHORT_LINE_MAX].
_CELL_SHORT_LINE_MIN = 0.50
_CELL_SHORT_LINE_MAX = 0.85
_CELL_WRAP_GAP_FACTOR = 3.0


def _cell_short_line_ratio(font_size: float, cell_w: float) -> float:
    """Compute a dynamic short-line threshold for a table cell.

    Narrow cells (few characters per line) need a low threshold because
    word wrapping can leave large gaps.  Wide cells behave like
    paragraphs — wrapped lines fill most of the width.

    Formula: ``1.0 − k × font_size / cell_w``, where *k* approximates
    the gap left by an average word at the end of a wrapped line.
    Result is clamped to ``[_CELL_SHORT_LINE_MIN, _CELL_SHORT_LINE_MAX]``.
    """
    if cell_w <= 0 or font_size <= 0:
        return _CELL_SHORT_LINE_MIN
    ratio = 1.0 - _CELL_WRAP_GAP_FACTOR * font_size / cell_w
    return max(_CELL_SHORT_LINE_MIN, min(_CELL_SHORT_LINE_MAX, ratio))


# Minimum leftward shift (points) to treat as a paragraph-ending
# dedent when exiting a list item's continuation body.
_MIN_DEDENT_PT = 3.0

# Regex matching common list/bullet markers at the start of a line.
# Used to upgrade space joins to newlines when the next line begins a
# new list item.
_LIST_MARKER_RE = re.compile(
    r"\s*("
    r"\d{1,3}\s*[-–—]\s"  # 1 - 2 – 3 —  (number-dash lists)
    r"|\d{1,3}[.):]\s"  # 1. 1) 1: 2. 2) 2:  (max 3 digits to avoid matching years)
    r"|\(\d{1,3}\)\s"  # (1) (2)
    r"|\[\d{1,3}\]\s"  # [1] [2]
    r"|[a-zA-Z]\)\s"  # a) b) A) B)
    r"|\([a-zA-Z]+\)\s"  # (a) (b) (iv)
    r"|\[[a-zA-Z]+\]\s"  # [a] [b] [iv]
    r"|[•●○▪▸‣◦◆►]\s*"  # bullet characters
    r"|[-–—]\s"  # dashes followed by space
    r")"
)


def _upgrade_list_joins(  # noqa: PLR0912, PLR0915
    line_texts: list[str],
    joins: list[str],
    line_extents: list[tuple[float, float]] | None = None,
    line_font_sizes: list[float] | None = None,
    line_font_styles: list[tuple[bool, bool]] | None = None,
) -> None:
    """Upgrade space→newline when the next line starts with a list marker.

    Detects numbered lists (``1.``, ``(1)``, ``[1]``), lettered lists
    (``a)``, ``(a)``), bullet characters, and dash prefixes.  Only
    promotes existing space joins — never demotes newlines.

    After upgrading list marker boundaries, also **demotes** joins
    between a marker line and its non-marker continuation back to
    space.  This fixes false paragraph breaks from indent-shift
    detection in ``_detect_line_joins`` that misidentify hanging-
    indent continuations as new paragraphs.  The demote is guarded
    by three checks:

    * **(a) Font size** — sizes differ by more than
      ``_LIST_DEMOTE_SIZE_TOL`` → heading at a different scale.
    * **(b) Short marker** — the marker line is shorter than
      ``_SHORT_LINE_RATIO`` of the block width → text ended
      naturally rather than being forced to wrap.
    * **(c) Font style + full-width continuation** — the marker
      and continuation differ in bold or italic AND the
      continuation is full-width → a styled heading followed by
      a body paragraph.

    Finally, when *line_extents* is provided, detects **dedent** after
    list continuation lines: if a non-marker line is followed by a
    line that shifts significantly to the left, the join is upgraded
    to newline.  This catches the transition from a list item's
    continuation body back to regular body text.

    Args:
        line_texts: Text content of each line.
        joins: Mutable list of join characters to update in-place.
        line_extents: Optional ``(x0, x1)`` per line for dedent
            detection.
        line_font_sizes: Optional dominant font size per line for
            heading detection in Pass 2.
        line_font_styles: Optional ``(is_bold, is_italic)`` per line
            for styled-heading detection in Pass 2.
    """
    # Pass 1: upgrade space→newline before list markers.
    for i in range(len(joins)):
        if joins[i] == "\n":
            continue
        if _LIST_MARKER_RE.match(line_texts[i + 1]):
            joins[i] = "\n"

    # Pass 2: demote newline→space for hanging-indent continuations.
    # If line i starts with a list marker but line i+1 does NOT,
    # line i+1 is the continuation body of that list item — keep
    # them in the same paragraph so _compute_para_indents sees
    # the hanging-indent pattern correctly.
    #
    # Guards prevent false demotes for section headings like
    # "2. Application..." that match _LIST_MARKER_RE:
    #   (a) Font size differs → differently-sized heading.
    #   (b) Short marker → text ended naturally, not wrapped.
    #   (c) Font style differs + full-width continuation →
    #       styled heading followed by a body paragraph.
    # Pre-compute block width once for guards (b)–(c).
    _blk_w = 0.0
    if line_extents is not None and len(line_extents) >= 2:  # noqa: PLR2004
        _blk_x0 = min(e[0] for e in line_extents)
        _blk_x1 = max(e[1] for e in line_extents)
        _blk_w = _blk_x1 - _blk_x0
    for i in range(len(joins)):
        if joins[i] != "\n":
            continue
        if _LIST_MARKER_RE.match(line_texts[i]) and not _LIST_MARKER_RE.match(
            line_texts[i + 1]
        ):
            # Guard (a): font size mismatch → likely heading.
            if (
                line_font_sizes is not None
                and i < len(line_font_sizes)
                and i + 1 < len(line_font_sizes)
                and abs(line_font_sizes[i] - line_font_sizes[i + 1])
                > _LIST_DEMOTE_SIZE_TOL
            ):
                continue
            # Guard (b): short marker → text ended naturally.
            if _blk_w > 0 and i < len(line_extents):
                marker_w = line_extents[i][1] - line_extents[i][0]
                if marker_w < _blk_w * _SHORT_LINE_RATIO:
                    continue
            # Guard (c): font style differs + full-width cont.
            if (
                _blk_w > 0
                and i + 1 < len(line_extents)
                and line_font_styles is not None
                and i < len(line_font_styles)
                and i + 1 < len(line_font_styles)
            ):
                m_bold, m_ital = line_font_styles[i]
                c_bold, c_ital = line_font_styles[i + 1]
                style_differs = m_bold != c_bold or m_ital != c_ital
                cont_w = line_extents[i + 1][1] - line_extents[i + 1][0]
                if style_differs and cont_w >= _blk_w * _SHORT_LINE_RATIO:
                    continue
            joins[i] = " "

    # Pass 3: upgrade space→newline for dedent after list continuation.
    # When a non-marker continuation line (indented) is followed by a
    # line that shifts LEFT (dedents), it marks the end of the list
    # item body and the start of a new paragraph.  Only active when
    # we have seen a list marker recently (``in_list_ctx``).
    if line_extents is not None:
        in_list_ctx = False
        for i in range(len(joins)):
            # Track list context — set when we encounter a marker.
            if _LIST_MARKER_RE.match(line_texts[i]):
                in_list_ctx = True
            if joins[i] != " ":
                continue
            if not in_list_ctx:
                continue
            # Skip if either line is a marker (handled by Pass 1/2).
            if _LIST_MARKER_RE.match(line_texts[i]) or _LIST_MARKER_RE.match(
                line_texts[i + 1]
            ):
                continue
            # Skip if line i is the first line of its paragraph.
            # A first-line indent (joins[i-1]==NL or i==0) naturally
            # sits to the right of continuation lines — that is normal
            # paragraph formatting, not a list continuation dedent.
            if i == 0 or joins[i - 1] == "\n":
                continue
            # Detect dedent: current line left edge > next line left edge.
            curr_x0 = line_extents[i][0]
            next_x0 = line_extents[i + 1][0]
            dedent = curr_x0 - next_x0
            if dedent > _MIN_DEDENT_PT:
                joins[i] = "\n"
                in_list_ctx = False


def _get_first_content_flags(
    spans: list[dict[str, Any]],
) -> int:
    """Return the flags of the first non-math, non-whitespace span."""
    for s in spans:
        if s.get("_is_math") or not s.get("text", "").strip():
            continue
        return s.get("flags", 0)
    return 0


def _upgrade_emphasis_start_joins(  # noqa: PLR0912
    line_spans_data: list[list[dict[str, Any]]],
    joins: list[str],
) -> None:
    """Promote space→newline when a repeating emphasis-start pattern is found.

    Academic and technical PDFs often use a definition-list pattern
    where each paragraph opens with a bold or italic term (e.g.
    ``**Hyperparameters.** We use ...`` or ``*Term:* Description``)
    followed by plain body text.  When vertical spacing between such
    paragraphs is tight, ``_detect_line_joins`` incorrectly marks them
    as line wraps.

    Two guards prevent false positives on inline emphasis (e.g.
    "*uniquely* to the overall"):

    1. The **current paragraph must also start with the same emphasis
       type** — this captures the repeating structural pattern of
       definition lists while rejecting isolated mid-sentence emphasis.
    2. The emphasized text at line i+1 must **end with definition-list
       punctuation** (``. : ; ) ! ]``).  Real terms always have a
       separator before the body text; plain words like "*uniquely*"
       do not.

    Each emphasis type (bold, italic) is checked independently.

    Note: PDF underline is a drawn rule, not a font flag, so it cannot
    be detected from span metadata.

    Args:
        line_spans_data: Per-line span data (list of span dicts with
            ``flags``, ``text``, and optional ``_is_math`` keys).
        joins: Mutable list of join characters to update in-place.
    """
    # PyMuPDF flag bits: bit 4 (16) = bold, bit 1 (2) = italic.
    _emphasis_bits = (16, 2)

    for i in range(len(joins)):
        if joins[i] == "\n":
            continue

        next_spans = line_spans_data[i + 1]
        curr_spans = line_spans_data[i]

        # Collect flags of first content span in line i+1.
        first_next_flags = _get_first_content_flags(next_spans)
        # Early exit: no emphasis on first span → nothing to detect.
        if not any(first_next_flags & b for b in _emphasis_bits):
            continue

        # Collect flags of last content span in line i.
        last_curr_flags: int | None = None
        for s in reversed(curr_spans):
            if s.get("_is_math") or not s.get("text", "").strip():
                continue
            last_curr_flags = s.get("flags", 0)
            break
        if last_curr_flags is None:
            continue

        # Find the current paragraph's start line: trace back to the
        # line after the last NL join, or line 0 if no NL precedes.
        para_start = 0
        for j in range(i - 1, -1, -1):
            if joins[j] == "\n":
                para_start = j + 1
                break
        para_start_flags = _get_first_content_flags(
            line_spans_data[para_start],
        )

        # Check each emphasis type independently.
        for bit in _emphasis_bits:
            # Next line must start with this emphasis.
            if not (first_next_flags & bit):
                continue
            # Current paragraph must also start with this emphasis
            # (repeating definition-list pattern).  Without this,
            # inline emphasis like "*uniquely*" at a line start
            # would be mistaken for a paragraph header.
            if not (para_start_flags & bit):
                continue
            # Current line must end WITHOUT this emphasis (otherwise
            # it could be a wrapped all-emphasis paragraph).
            if last_curr_flags & bit:
                continue
            # The emphasized text at the start of line i+1 must end
            # with definition-list punctuation (e.g. "**Term.** Body"
            # or "**Heading:** Body").  Plain words like "*uniquely*"
            # lack a separator and are inline emphasis, not terms.
            emph_text = ""
            for s in next_spans:
                if s.get("_is_math") or not s.get("text", "").strip():
                    continue
                if s.get("flags", 0) & bit:
                    emph_text += s.get("text", "")
                else:
                    break
            last_emph_ch = emph_text.rstrip()[-1] if emph_text.strip() else ""
            if last_emph_ch not in ".:;)!]":
                continue
            # Verify line i+1 has a transition (not all-emphasised).
            has_plain = any(
                not (s.get("flags", 0) & bit)
                for s in next_spans
                if not s.get("_is_math") and s.get("text", "").strip()
            )
            if has_plain:
                joins[i] = "\n"
                break


def _compute_para_indents(
    line_extents: list[tuple[float, float]],
    line_sizes: list[float],
    joins: list[str],
) -> list[tuple[float, float]]:
    """Compute block-level and first-line indent for each paragraph.

    Three indent patterns are detected:

    * **Block indent** (``padding-left``) — all lines of the paragraph
      are shifted inward from the block margin.  Detected by looking at
      the *body* lines (lines after the first) of multi-line paragraphs.
    * **First-line indent** (positive ``text-indent``) — the first line
      is shifted further inward than the body.
    * **Hanging indent** (negative ``text-indent``) — the first line
      (e.g. a list marker) starts further *left* than the body.  Common
      in numbered/bulleted lists where the marker and content form two
      visual columns.

    Args:
        line_extents: ``(x0, x1)`` per line.
        line_sizes: Dominant font size per line.
        joins: Join characters between consecutive lines.

    Returns:
        List of ``(block_indent_pt, first_line_indent_pt)`` tuples,
        one per paragraph.  ``first_line_indent_pt`` is negative for
        hanging indents.  Empty list when no indentation is detected.
    """
    if not line_extents or not joins:
        return []

    # Margin reference: leftmost line start across the whole block.
    margin_ref = min(ext[0] for ext in line_extents)
    dom_sz = max(line_sizes) if line_sizes else 12.0
    indent_lo = dom_sz * _INDENT_FACTOR
    indent_hi = dom_sz * _MAX_INDENT_FACTOR

    # Split line indices into paragraph ranges based on \n joins.
    para_ranges: list[tuple[int, int]] = []
    start = 0
    for i, join_char in enumerate(joins):
        if join_char == "\n":
            para_ranges.append((start, i))
            start = i + 1
    para_ranges.append((start, len(line_extents) - 1))

    indents: list[tuple[float, float]] = []
    for p_start, p_end in para_ranges:
        first_left = line_extents[p_start][0]

        if p_start < p_end:
            # Multi-line paragraph: body = lines after the first.
            body_left = min(line_extents[j][0] for j in range(p_start + 1, p_end + 1))
        else:
            # Single-line: no body lines to distinguish block indent
            # from first-line indent.  Treat all shift as first-line
            # by setting body_left = margin_ref (→ block_shift = 0).
            body_left = margin_ref

        # Block indent: how far the body is shifted from the margin.
        block_shift = body_left - margin_ref
        block_indent = (
            round(block_shift, 1) if indent_lo <= block_shift <= indent_hi else 0.0
        )

        # First-line indent: how far the first line is shifted from
        # the body edge (multi-line) or the margin (single-line).
        # Positive = regular first-line indent.
        # Negative = hanging indent (marker left of body, like lists).
        if p_start < p_end:
            fl_shift = first_left - body_left
        else:
            fl_shift = first_left - margin_ref
        fl_indent = (
            round(fl_shift, 1) if indent_lo <= abs(fl_shift) <= indent_hi else 0.0
        )

        indents.append((block_indent, fl_indent))

    # Only return when at least one paragraph has indentation.
    if any(bi > 0 or fi != 0.0 for bi, fi in indents):
        return indents
    return []


def _detect_line_joins(  # noqa: PLR0912, PLR0915
    y_positions: list[float],
    line_sizes: list[float],
    line_extents: list[tuple[float, float]] | None = None,
    line_texts: list[str] | None = None,
    line_y_ends: list[float] | None = None,
) -> list[str]:
    """Decides whether consecutive lines should be joined by space or newline.

    Uses **font size** as the reference for expected line spacing rather
    than comparing gaps to each other (median).  Typical leading is
    ~1.2× font size; gaps within ``_LEADING_TOLERANCE`` × that value are
    treated as line wraps (joined with space).  Larger gaps or
    significant font-size changes between adjacent lines indicate a
    paragraph / section break (joined with newline).

    When *line_extents* is supplied, two layout-based upgrades can
    promote a space join to a newline:

    * **Short line** (justified text only) — line *i* is significantly
      narrower than the block width → it is the last line of a
      paragraph.  Width-based so it works for both LTR and RTL.
    * **Indent** — line *i + 1* is shifted inward from the reading-start
      margin while line *i* sits at the margin.  Supports both LTR
      (left-margin indent) and RTL (right-margin indent).

    Args:
        y_positions: Y-coordinates of each line (from ``line["bbox"][1]``).
        line_sizes: Dominant font size **per line** (same length as
            *y_positions*).
        line_extents: Optional ``(x0, x1)`` per line for layout-based
            detection.
        line_texts: Optional text content per line for sentence-ending
            detection (upgrades space→newline when a line ends with
            sentence-terminating punctuation and doesn't fill the block).
        line_y_ends: Optional bottom y-coordinates per line.  When
            provided, the gap is measured from the bottom of line *i*
            to the top of line *i + 1* instead of top-to-top.  This
            prevents tall merged lines (e.g. math subscripts expanding
            a line's bbox) from inflating the gap and causing false
            paragraph breaks.

    Returns:
        List of join characters (``" "`` or newline) with length
        ``len(y_positions) - 1``.  Empty list if fewer than 2 lines.
    """
    n = len(y_positions)
    if n < 2:  # noqa: PLR2004
        return []

    joins: list[str] = []
    for i in range(n - 1):
        # Use bottom-to-top gap when line y-ends are available.
        # Tall merged lines (math subscripts) inflate the top-to-top
        # distance, causing false paragraph breaks.  The visual gap
        # (bottom of line i → top of line i+1) is the true measure.
        if line_y_ends is not None and i < len(line_y_ends):
            gap = y_positions[i + 1] - line_y_ends[i]
        else:
            gap = y_positions[i + 1] - y_positions[i]
        sz_a = line_sizes[i]
        sz_b = line_sizes[i + 1]
        bigger = max(sz_a, sz_b) or 12.0

        # Significant font-size change → structural break
        if abs(sz_a - sz_b) > bigger * _SIZE_CHANGE_THRESHOLD:
            joins.append("\n")
            continue

        # Expected leading from the larger font of the pair
        expected_leading = bigger * _LEADING_RATIO
        # If gap fits within tolerance of expected leading → line wrap
        if gap <= expected_leading * _LEADING_TOLERANCE:
            joins.append(" ")
        else:
            joins.append("\n")

    # Layout-based upgrades (short-line + indent + centered).
    if line_extents and n >= 2:  # noqa: PLR2004
        block_right = max(ext[1] for ext in line_extents)
        block_left = min(ext[0] for ext in line_extents)
        block_width = block_right - block_left
        if block_width >= _MIN_BLOCK_WIDTH_FOR_LAYOUT:
            dominant_size = max(line_sizes) if line_sizes else 12.0

            # Filter out very narrow fragment lines (e.g. math sub-
            # expressions like "2(f,D)" at 31pt) from alignment
            # analysis.  These fragments don't represent real content
            # lines and distort left/right edge statistics.
            _frag_min_w = block_width * 0.2
            sig_extents = [
                ext for ext in line_extents if (ext[1] - ext[0]) >= _frag_min_w
            ]
            if not sig_extents:
                sig_extents = list(line_extents)
            n_sig = len(sig_extents)

            # Use median edges as reference (robust to outliers like
            # short last lines or indented first lines).
            sorted_lefts = sorted(ext[0] for ext in sig_extents)
            sorted_rights = sorted(ext[1] for ext in sig_extents)
            typical_left = sorted_lefts[n_sig // 2]
            typical_right = sorted_rights[n_sig // 2]
            typical_width = typical_right - typical_left

            # Dynamic alignment tolerance based on font size.
            # Fixed-point thresholds (e.g. 2pt) fail for real PDFs
            # where justified right edges vary by 3-5pt.
            align_tol = max(dominant_size * 0.5, 3.0)

            # Left-aligned: majority start near the median left edge
            # or near the block's minimum left (handles mixed-indent
            # blocks like lists + body text at different indent levels).
            margin_left_ref = sorted_lefts[0]
            lines_at_left = sum(
                1
                for ext in sig_extents
                if abs(ext[0] - typical_left) <= align_tol
                or abs(ext[0] - margin_left_ref) <= align_tol
            )
            is_left_aligned = lines_at_left > n_sig / 2

            # Right-aligned: majority end near the median right edge.
            lines_at_right = sum(
                1 for ext in sig_extents if abs(ext[1] - typical_right) <= align_tol
            )
            is_right_aligned = lines_at_right > n_sig / 2

            # Justified: both edges aligned for a majority of lines.
            is_justified = is_left_aligned and is_right_aligned

            # Centered layout detection: check margin symmetry on
            # non-full-width lines (mirrors _detect_block_alignment).
            # Full-width lines (>95% of block) confuse left/right
            # alignment checks, making centered blocks look justified.
            _full_w_thresh = block_width * 0.95
            left_margins = [ext[0] - block_left for ext in line_extents]
            right_margins = [block_right - ext[1] for ext in line_extents]
            narrow_lm = [
                lm
                for lm, rm in zip(left_margins, right_margins, strict=False)
                if (block_width - lm - rm) < _full_w_thresh
            ]
            narrow_rm = [
                rm
                for lm, rm in zip(left_margins, right_margins, strict=False)
                if (block_width - lm - rm) < _full_w_thresh
            ]
            min_margin = block_width * 0.05
            is_centered_layout = False
            if narrow_lm:
                avg_nl = sum(narrow_lm) / len(narrow_lm)
                avg_nr = sum(narrow_rm) / len(narrow_rm)
                is_centered_layout = (
                    avg_nl > min_margin
                    and avg_nr > min_margin
                    and abs(avg_nl - avg_nr) < block_width * 0.15
                )

            for i in range(n - 1):
                if joins[i] == "\n":
                    continue

                # Centered text: each line is intentionally placed.
                # In centered blocks, a space join only makes sense when
                # text wraps (one line fills the available width and
                # continues on the next).  If line i doesn't fill the
                # block width, it ended intentionally → newline.
                # Check this BEFORE justified short-line since centered
                # blocks can be misclassified as justified when a
                # full-width line satisfies both edge checks.
                if is_centered_layout:
                    line_w = line_extents[i][1] - line_extents[i][0]
                    if line_w < block_width * _SHORT_LINE_RATIO:
                        joins[i] = "\n"
                        continue

                # Short-line (justified only): line i is significantly
                # narrower than the typical width → last line of a
                # paragraph.  Width-based: works for LTR and RTL.
                # Skip lines whose narrowness is caused by indent
                # (shift from margin in the 0.5–3× font-size range)
                # rather than being the last line of a paragraph.
                if is_justified and not is_centered_layout:
                    line_w = line_extents[i][1] - line_extents[i][0]
                    l_shift = line_extents[i][0] - typical_left
                    r_shift = typical_right - line_extents[i][1]
                    indent_lo = dominant_size * _INDENT_FACTOR
                    indent_hi = dominant_size * _MAX_INDENT_FACTOR
                    is_indented = (
                        indent_lo <= l_shift <= indent_hi
                        or indent_lo <= r_shift <= indent_hi
                    )
                    if not is_indented and line_w < typical_width * _SHORT_LINE_RATIO:
                        joins[i] = "\n"
                        continue

                # Indent: line i+1 shifts inward from the reading-start
                # margin while line i sits at the margin.
                indent_min = line_sizes[i + 1] * _INDENT_FACTOR
                indent_max = line_sizes[i + 1] * _MAX_INDENT_FACTOR
                # LTR indent (left margin — works for both left-aligned
                # and justified LTR text)
                if is_left_aligned:
                    curr_at_left = abs(line_extents[i][0] - typical_left) < indent_min
                    shift_left = line_extents[i + 1][0] - typical_left
                    if curr_at_left and indent_min <= shift_left <= indent_max:
                        joins[i] = "\n"
                        continue
                # RTL indent (right margin, ragged left)
                if is_right_aligned and not is_left_aligned:
                    curr_at_right = abs(typical_right - line_extents[i][1]) < indent_min
                    shift_right = typical_right - line_extents[i + 1][1]
                    if curr_at_right and indent_min <= shift_right <= indent_max:
                        joins[i] = "\n"

    # Sentence-ending upgrade: if a line ends with sentence-terminating
    # punctuation (. ! ?) and doesn't fill the block width, it's very
    # likely a complete paragraph.  Works for any alignment and any n.
    if line_texts and line_extents:
        block_right = max(ext[1] for ext in line_extents)
        block_left = min(ext[0] for ext in line_extents)
        bw = block_right - block_left
        if bw > 0:
            for i in range(n - 1):
                if joins[i] == "\n":
                    continue
                text_stripped = line_texts[i].rstrip()
                if not text_stripped:
                    continue
                if text_stripped[-1] in ".!?":
                    line_w = line_extents[i][1] - line_extents[i][0]
                    if line_w < bw * _SHORT_LINE_RATIO:
                        joins[i] = "\n"

    return joins


def _fix_url_line_joins(
    line_texts: list[str],
    joins: list[str],
) -> None:
    """Convert space joins to empty joins when a line ends mid-URL.

    When a URL wraps across PDF lines, ``_detect_line_joins`` inserts a
    space between the two fragments.  This function detects the pattern
    (``://`` present and URL extends to end of line) and removes the
    space so the URL stays intact.

    Modifies *joins* in place.
    """
    for i in range(len(joins)):
        if joins[i] != " ":
            continue
        text = line_texts[i]
        # Check if the line text ends inside a URL (://...no whitespace to end)
        idx = text.rfind("://")
        if idx == -1:
            continue
        after_protocol = text[idx:]
        if " " not in after_protocol and "\t" not in after_protocol:
            joins[i] = ""


def _join_lines(lines: list[str], joins: list[str]) -> str:
    """Joins line texts using the join characters from ``_detect_line_joins``.

    Args:
        lines: Text content of each line.
        joins: Join characters between consecutive lines.

    Returns:
        Combined text string.
    """
    if not lines:
        return ""
    parts = [lines[0]]
    for i, join_char in enumerate(joins):
        parts.append(join_char)
        parts.append(lines[i + 1])
    return "".join(parts)


# Minimum number of vertical blocks sharing a y-range to form a
# label row eligible for alignment resolution.
_MIN_LABEL_ROW_COUNT = 3

# Rows with this many or more vertical blocks are treated as
# figure-axis label grids (e.g. attention visualisation tokens).
# Translating single-word labels without sentence context produces
# meaningless results and misaligns labels with the heatmap.
_MIN_AXIS_LABEL_COUNT = 6


def _resolve_vertical_alignment(  # noqa: PLR0912
    blocks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Resolves rotation and insertion point for grouped vertical blocks.

    PyMuPDF reports ``dir=(0, -1)`` for ALL vertical text regardless of
    visual orientation.  This function groups vertical blocks by y-overlap,
    then determines the actual growth direction by comparing the variance
    of ``bbox_y0`` (top), ``bbox_y1`` (bottom), and ``mid_y`` (center):

    * **Smallest variance on bbox_y1** → bottom-aligned → ``rotate=90``
      (text grows upward from the shared bottom edge).
    * **Smallest variance on bbox_y0** → top-aligned → ``rotate=270``
      (text grows downward from the shared top edge).
    * **Smallest variance on mid_y** → center-aligned → ``rotate=90``
      (text grows upward, insertion point adjusted to center).

    Each vertical block in a resolved group receives ``_vert_align``
    (``"bottom"``, ``"top"``, or ``"center"``) and ``_vert_align_y``
    (the shared edge coordinate).  The overlay function uses these to
    compute the correct insertion point based on text length.

    Rows with ``_MIN_AXIS_LABEL_COUNT`` or more blocks are treated as
    figure-axis label grids (e.g. attention visualisation tokens) and
    are removed — translating single-word labels without sentence
    context produces meaningless results.

    Args:
        blocks: List of block dicts (some may have ``is_vertical=True``).

    Returns:
        Filtered list with alignment metadata set on grouped vertical
        blocks and axis-label rows removed.
    """
    # Collect vertical block indices and rects.
    vert_items: list[tuple[int, list[float]]] = []
    for i, b in enumerate(blocks):
        if b.get("is_vertical"):
            vert_items.append((i, b["rect"]))

    if len(vert_items) < _MIN_LABEL_ROW_COUNT:
        return blocks

    # Group by y-overlap so each figure row is separate.
    vert_items.sort(key=lambda t: t[1][1])  # sort by y0
    y_groups: list[list[tuple[int, list[float]]]] = [[vert_items[0]]]
    grp_y1 = vert_items[0][1][3]
    for item in vert_items[1:]:
        y0 = item[1][1]
        if y0 <= grp_y1 + 5.0:
            y_groups[-1].append(item)
            grp_y1 = max(grp_y1, item[1][3])
        else:
            y_groups.append([item])
            grp_y1 = item[1][3]

    # For each group with enough blocks, determine alignment.
    # Rows exceeding _MIN_AXIS_LABEL_COUNT are marked for removal.
    remove: set[int] = set()
    for y_grp in y_groups:
        if len(y_grp) < _MIN_LABEL_ROW_COUNT:
            continue

        # Axis-label grid: too many single-word labels to translate
        # meaningfully.  Mark for removal.
        if len(y_grp) >= _MIN_AXIS_LABEL_COUNT:
            remove.update(idx for idx, _ in y_grp)
            continue

        # Compute variance of top, bottom, and mid y-values.
        y0s = [r[1] for _, r in y_grp]
        y1s = [r[3] for _, r in y_grp]
        mids = [(r[1] + r[3]) / 2 for _, r in y_grp]

        def _variance(vals: list[float]) -> float:
            """Return the population variance of a list of floats."""
            mean = sum(vals) / len(vals)
            return sum((v - mean) ** 2 for v in vals) / len(vals)

        var_y0 = _variance(y0s)
        var_y1 = _variance(y1s)
        var_mid = _variance(mids)

        min_var = min(var_y0, var_y1, var_mid)
        if min_var == var_y1:
            # Bottom-aligned: all share the same bottom edge.
            shared_y = sum(y1s) / len(y1s)
            for idx, _ in y_grp:
                blocks[idx]["_vert_align"] = "bottom"
                blocks[idx]["_vert_align_y"] = shared_y
        elif min_var == var_y0:
            # Top-aligned: all share the same top edge.
            shared_y = sum(y0s) / len(y0s)
            for idx, _ in y_grp:
                blocks[idx]["_vert_align"] = "top"
                blocks[idx]["_vert_align_y"] = shared_y
        else:
            # Center-aligned: all share the same vertical midpoint.
            shared_mid = sum(mids) / len(mids)
            for idx, _ in y_grp:
                blocks[idx]["_vert_align"] = "center"
                blocks[idx]["_vert_align_y"] = shared_mid

    if remove:
        return [b for i, b in enumerate(blocks) if i not in remove]
    return blocks


def _extract_page_blocks(page: Any) -> list[dict[str, Any]]:  # noqa: ANN401, PLR0912, PLR0915
    """Extracts text blocks with style metadata from a PDF page.

    Detects tables via ``find_tables()`` and splits them into per-cell
    blocks so each cell is translated independently.  Regular (non-table)
    text blocks are extracted as before.  For blocks that partially
    overlap a table, spans inside the table region are filtered out so
    that only non-table text remains (e.g. captions below a table).

    Args:
        page: A PyMuPDF Page object.

    Returns:
        List of block dicts with keys: rect, text, font_size, font_name,
        color, bold, italic.  Table cells additionally carry text_align
        and is_table_cell.  Whitespace-only blocks are skipped.
    """
    page_dict = page.get_text("dict")

    # Detect tables and build per-cell blocks.
    # Use cell-level bboxes (not full table bboxes) for span filtering
    # so that cells skipped by _extract_table_cell_blocks (those with
    # math fonts, e.g. algorithm bodies) can go through normal block
    # extraction with full math-placeholder support.
    page_tables = _find_page_tables(page, page_dict)
    table_bboxes = _get_extracted_cell_bboxes(page_tables, page_dict)

    # Detect Form XObject regions — text inside these cannot be
    # visually redacted (the XObject renders it as path outlines).
    xobject_rects = _get_form_xobject_rects(page)

    # Detect raster image regions — text blocks overlapping these are
    # invisible OCR layers whose originals survive redaction as pixels.
    image_rects = _get_image_rects(page_dict)

    # Detect FreeText annotation regions — their rendered text appears
    # in get_text("dict") as normal text blocks.  Redacting these
    # blocks destroys the annotation, so they must be excluded here;
    # annotation translation is handled separately by
    # _inject_page_annotations which updates the content in-place.
    freetext_rects = _get_freetext_annot_rects(page)

    result: list[dict[str, Any]] = []

    # Pre-split blocks at display-equation gaps so large vertical
    # breaks within a single PyMuPDF block produce separate entries.
    # Pure-math sub-blocks (body_len=0) are then skipped later,
    # preserving the original TeX rendering.
    raw_blocks = page_dict.get("blocks", [])
    expanded_blocks: list[dict[str, Any]] = []
    for blk in raw_blocks:
        if blk.get("type") == 0:
            expanded_blocks.extend(_split_at_display_gaps(blk))
        else:
            expanded_blocks.append(blk)

    # Merge continuation lines that PyMuPDF split across adjacent
    # blocks (e.g. a radicand "2/δ" placed in a new block after the
    # radical "√").  Must run after display-gap splitting so we don't
    # undo intentional splits.
    expanded_blocks = _merge_continuation_lines(expanded_blocks)

    for block in expanded_blocks:
        # Skip image blocks (type 1)
        if block.get("type") != 0:
            continue

        # Skip blocks inside Form XObjects (their text survives redaction)
        if xobject_rects and _block_inside_any_xobject(
            list(block["bbox"]),
            xobject_rects,
        ):
            continue

        # Skip blocks that are invisible OCR layers over raster images
        if image_rects and _block_overlaps_image(
            list(block["bbox"]),
            image_rects,
        ):
            continue

        # Skip blocks rendered by FreeText annotations (handled by
        # annotation injection; redacting would destroy the annotation)
        if freetext_rects and _block_inside_freetext(
            list(block["bbox"]),
            freetext_rects,
        ):
            continue

        lines = block.get("lines", [])
        if not lines:
            continue

        # Vertical/rotated text: mark for overlay via insert_text
        # (insert_htmlbox cannot render rotated text).
        is_vertical = _is_vertical_block(lines)

        # Collect span texts and font properties, skipping spans inside
        # table regions (those are handled by per-cell blocks below).
        line_texts: list[str] = []
        font_names: list[str] = []
        font_sizes: list[float] = []
        body_font_sizes: list[float] = []  # excludes sup/sub
        font_flags: list[int] = []
        font_colors: list[int] = []
        span_roles: list[str | None] = []  # sup/sub classification
        # Track bbox of remaining (non-table) spans
        rx0, ry0, rx1, ry1 = float("inf"), float("inf"), 0.0, 0.0
        # Track per-line x-extents for alignment detection
        line_extents: list[tuple[float, float]] = []
        # Track per-line span data for mixed formatting detection
        line_spans_data: list[list[dict[str, Any]]] = []
        # Track per-line y-positions for same-line merging
        line_y_positions: list[float] = []
        line_y_ends: list[float] = []
        # Track per-line dominant font size for line-join detection
        line_font_sizes: list[float] = []
        # Math-font placeholder map for this block
        block_math_map: dict[str, str] = {}
        math_ph_counter = 0

        for line in lines:
            span_texts: list[str] = []
            line_span_items: list[dict[str, Any]] = []
            line_span_sizes: list[float] = []
            lx0_min = float("inf")
            lx1_max = 0.0
            prev_sx1 = 0.0  # right edge of previous span
            for span in line.get("spans", []):
                # Filter out spans that belong to a detected table
                if table_bboxes and _span_in_any_table(span["bbox"], table_bboxes):
                    continue
                text = span.get("text", "")
                font = span.get("font", "")
                # CM font spans with empty text contain undecoded
                # glyphs (e.g. CMEX10 delimiter extensions).  Treat
                # them as U+FFFD so _merge_math_spans can capture
                # them as inline images.
                if not text and _is_math_font(font):
                    base_font = font.split("+")[-1]
                    if any(base_font.startswith(p) for p in ("CM", "MSB")):
                        text = "\ufffd"
                if text:
                    sx0, sy0, sx1, sy1 = span["bbox"]
                    # Insert space when consecutive spans have a
                    # horizontal gap > 1pt (same logic as _build_cell_text).
                    # PyMuPDF does not always embed inter-word spaces in
                    # span text when the font changes (e.g. math → body).
                    if span_texts and sx0 - prev_sx1 > 1.0:
                        sz_gap = span.get("size", 12.0)
                        span_texts.append(" ")
                        line_span_items.append(
                            {
                                "text": " ",
                                "font": "",
                                "flags": 0,
                                "size": sz_gap,
                                "color": 0,
                                "sx0": prev_sx1,
                                "sy0": sy0,
                                "sx1": sx0,
                                "sy1": sy1,
                                "_is_gap": True,
                            },
                        )
                        line_span_sizes.append(sz_gap)
                    prev_sx1 = sx1
                    span_texts.append(text)
                    sz = span.get("size", 12.0)
                    line_span_sizes.append(sz)
                    line_span_items.append(
                        {
                            "text": text,
                            "font": font,
                            "flags": span.get("flags", 0),
                            "size": sz,
                            "color": span.get("color", 0),
                            "sx0": sx0,
                            "sy0": sy0,
                            "sx1": sx1,
                            "sy1": sy1,
                        }
                    )
                    # Expand running bbox
                    rx0 = min(rx0, sx0)
                    ry0 = min(ry0, sy0)
                    rx1 = max(rx1, sx1)
                    ry1 = max(ry1, sy1)
                    lx0_min = min(lx0_min, sx0)
                    lx1_max = max(lx1_max, sx1)

            # Merge consecutive math-font spans into placeholders
            # so the LLM only translates surrounding body text.
            has_math = any(_is_math_font(it.get("font", "")) for it in line_span_items)
            if span_texts and has_math:
                pre_dom_sz = max(line_span_sizes) if line_span_sizes else 12.0
                ly0 = line["bbox"][1]
                ly1 = line["bbox"][3]
                span_texts, line_span_items, math_ph_counter = _merge_math_spans(
                    span_texts,
                    line_span_items,
                    block_math_map,
                    math_ph_counter,
                    page=page,
                    pymupdf=pymupdf,
                    line_dom_size=pre_dom_sz,
                    line_y0=ly0,
                    line_y1=ly1,
                )

            if span_texts:
                # Classify superscript/subscript per span FIRST so we
                # can exclude sub/sup from dominant size calculation.
                # Use max() rather than _most_common() because sup/sub
                # spans are always smaller — the largest size is the
                # true dominant text size (avoids tie-breaking issues
                # when a line has only 2 spans of different sizes).
                line_dom_sz = max(line_span_sizes)
                ly0, ly1 = line["bbox"][1], line["bbox"][3]
                for item in line_span_items:
                    if item.get("_is_gap"):
                        item["role"] = None
                        continue
                    role = _classify_sup_sub(
                        item["size"],
                        item["sy0"],
                        item["sy1"],
                        line_dom_sz,
                        ly0,
                        ly1,
                    )
                    item["role"] = role
                    if not item.get("_is_math"):
                        span_roles.append(role)

                # Accumulate font properties for dominant-value
                # detection.  Math placeholder spans AND sup/sub spans
                # are excluded so dominants reflect body text properties.
                # Body-font subscripts (e.g. "model" in d_model at 5pt)
                # would otherwise outnumber body text and skew the size.
                for item in line_span_items:
                    if item.get("_is_math") or item.get("_is_gap"):
                        continue
                    font_names.append(item.get("font", ""))
                    font_flags.append(item.get("flags", 0))
                    font_colors.append(item.get("color", 0))
                    # Sizes: all non-math for general list, but
                    # exclude sup/sub from dominant size candidate.
                    font_sizes.append(item.get("size", 12.0))
                    if not item.get("role"):
                        body_font_sizes.append(
                            item.get("size", 12.0),
                        )
                line_texts.append("".join(span_texts))
                line_extents.append((lx0_min, lx1_max))
                line_spans_data.append(line_span_items)
                line_y_positions.append(line["bbox"][1])
                line_y_ends.append(line["bbox"][3])
                line_font_sizes.append(line_dom_sz)

        # Merge consecutive same-y lines (e.g. "2" + "THE SYSTEM" on one
        # visual line split by a horizontal gap in PyMuPDF's dict output).
        # When the gap is very large relative to block width, mark as
        # "space-between" layout (e.g. page header/footer) using \t.
        is_space_between = False
        block_width = block["bbox"][2] - block["bbox"][0]
        i = 1
        while i < len(line_texts):
            if abs(line_y_positions[i] - line_y_positions[i - 1]) < _LINE_Y_TOLERANCE:
                gap = line_extents[i][0] - line_extents[i - 1][1]
                if (
                    gap > block_width * _SPACE_BETWEEN_GAP_RATIO
                    and gap >= _SPACE_BETWEEN_MIN_GAP
                ):
                    separator = "\t"
                    is_space_between = True
                else:
                    separator = " "
                line_texts[i - 1] += separator + line_texts[i]
                line_extents[i - 1] = (
                    min(line_extents[i - 1][0], line_extents[i][0]),
                    max(line_extents[i - 1][1], line_extents[i][1]),
                )
                line_spans_data[i - 1].append(
                    {"text": separator, "flags": 0, "role": None},
                )
                line_spans_data[i - 1].extend(line_spans_data[i])
                line_texts.pop(i)
                line_extents.pop(i)
                line_spans_data.pop(i)
                line_y_positions.pop(i)
                line_y_ends.pop(i)
                line_font_sizes.pop(i)
            else:
                i += 1

        # Merge subscript/superscript fragment lines into their parent.
        # PyMuPDF sometimes places a subscript (e.g. "i" in W^Q_i) on a
        # separate line whose y-range overlaps the main text line.  These
        # fragments are narrow, vertically overlap with the previous line,
        # and their x-range is adjacent.  Merge them so they don't create
        # spurious newlines in _detect_line_joins.
        i = 1
        while i < len(line_texts):
            prev_y0 = line_y_positions[i - 1]
            prev_y1 = line_y_ends[i - 1]
            cur_y0 = line_y_positions[i]
            cur_y1 = line_y_ends[i]
            # Check vertical overlap: the current line's y-range must
            # overlap at least 30% of its own height with the previous line.
            overlap = min(prev_y1, cur_y1) - max(prev_y0, cur_y0)
            cur_height = cur_y1 - cur_y0
            if cur_height > 0 and overlap >= cur_height * 0.3:
                # Merge into previous line
                line_texts[i - 1] += " " + line_texts[i]
                line_extents[i - 1] = (
                    min(line_extents[i - 1][0], line_extents[i][0]),
                    max(line_extents[i - 1][1], line_extents[i][1]),
                )
                line_spans_data[i - 1].append(
                    {"text": " ", "flags": 0, "role": None},
                )
                line_spans_data[i - 1].extend(line_spans_data[i])
                line_y_ends[i - 1] = max(prev_y1, cur_y1)
                line_texts.pop(i)
                line_extents.pop(i)
                line_spans_data.pop(i)
                line_y_positions.pop(i)
                line_y_ends.pop(i)
                line_font_sizes.pop(i)
            else:
                i += 1

        # Re-evaluate unclassified math placeholder roles using the
        # merged line geometry.  _merge_math_spans runs per-line
        # BEFORE same-y merging, so single-span math lines (e.g. a
        # fraction numerator "1") have span_mid == line_mid and
        # leave role=None.  After merging, these spans share a line
        # with body text, giving a proper midpoint for classification.
        if block_math_map:
            _reclassify_merged_math_roles(
                line_spans_data,
                block_math_map,
                line_y_positions,
                line_y_ends,
                line_font_sizes,
            )

        # Absorb body-font subscript/superscript labels that now sit
        # next to their math placeholders after the line merges above.
        # TeX renders labels like "schematic" in R²_schematic in the
        # body font at subscript size — absorb them so the LLM does
        # not translate variable-name fragments.
        if block_math_map:
            _absorb_math_sub_labels(
                line_texts,
                line_spans_data,
                block_math_map,
                line_font_sizes,
            )

        # ── Drop pure-math lines (display equations only) ─────────────
        # After same-y / subscript merges, check if any processed lines
        # consist entirely of math-font spans (no body font).  These
        # MAY be display equations whose original TeX rendering should
        # be preserved — but only if they look like *display* equations
        # (centered, separated from body).  Pure-math lines that are
        # inline continuations must be kept.  Two criteria identify
        # inline math:
        #   (a) x0 near the body text's left margin (e.g. "τ > L B"),
        #   (b) x0 near a body line's right edge with y-overlap —
        #       the math continues right after the body text
        #       (e.g. "divide through by √" where √ is the next glyph).
        #
        # We do NOT create separate block entries for the dropped math
        # lines because they could overlap with blocks from adjacent
        # PyMuPDF blocks and trigger incorrect merges in
        # _merge_overlapping_math_blocks.
        if block_math_map and len(line_texts) >= 2:  # noqa: PLR2004
            math_flags = [_is_pure_math_line(sd) for sd in line_spans_data]
            if any(math_flags) and not all(math_flags):
                # Compute the body text's left margin from non-math
                # lines and the dominant font size for tolerance.
                body_indices = [i for i, f in enumerate(math_flags) if not f]
                body_left = min(line_extents[i][0] for i in body_indices)
                dom_size = max(
                    (line_font_sizes[i] for i in body_indices),
                    default=12.0,
                )
                tol = _INLINE_MATH_X_TOL * dom_size

                # Keep non-math lines AND inline-math lines.
                keep: list[int] = []
                for idx in range(len(math_flags)):
                    if not math_flags[idx]:
                        keep.append(idx)
                        continue
                    mx0 = line_extents[idx][0]
                    # (a) Near body left margin → inline.
                    if mx0 - body_left < tol:
                        keep.append(idx)
                        continue
                    # (b) Near a body line's right edge with
                    #     y-proximity → inline continuation.
                    my0 = line_y_positions[idx]
                    my1 = line_y_ends[idx]
                    adjacent = False
                    for bi in body_indices:
                        if abs(mx0 - line_extents[bi][1]) < tol:
                            by0 = line_y_positions[bi]
                            by1 = line_y_ends[bi]
                            y_gap = max(my0, by0) - min(my1, by1)
                            if y_gap < dom_size:
                                adjacent = True
                                break
                    if adjacent:
                        keep.append(idx)
                    # else: display equation — not added to keep

                # Chain detection: iteratively keep math lines
                # adjacent to already-kept lines' right edges.
                # Handles multi-segment inline formulas like
                # √(S²fmt + S²psy + S²sch)/3 where continuation
                # lines are only reachable through other math lines.
                #
                # Also keeps math lines that vertically OVERLAP with
                # already-kept lines.  Fraction numerators and
                # denominators share the same vertical space as the
                # preceding "8: σ ←" but can be horizontally distant
                # due to the fraction's width.  The kept line may be
                # a merged body+math line (not pure-math), so we
                # check overlap against ALL kept lines.
                keep_set = set(keep)
                changed = True
                while changed:
                    changed = False
                    for idx in range(len(math_flags)):
                        if idx in keep_set or not math_flags[idx]:
                            continue
                        mx0 = line_extents[idx][0]
                        my0 = line_y_positions[idx]
                        my1 = line_y_ends[idx]
                        for ki in keep_set:
                            ky0 = line_y_positions[ki]
                            ky1 = line_y_ends[ki]
                            # (a) Horizontal right-edge adjacency
                            if abs(mx0 - line_extents[ki][1]) < tol:
                                y_gap = max(my0, ky0) - min(my1, ky1)
                                if y_gap < dom_size:
                                    keep.append(idx)
                                    keep_set.add(idx)
                                    changed = True
                                    break
                            # (b) Vertical overlap with any kept
                            #     line — catches fraction parts that
                            #     share y-range with "8: σ ←" etc.
                            if my0 < ky1 and my1 > ky0:
                                keep.append(idx)
                                keep_set.add(idx)
                                changed = True
                                break
                keep.sort()
                if keep:
                    line_texts = [line_texts[i] for i in keep]
                    line_extents = [line_extents[i] for i in keep]
                    line_spans_data = [line_spans_data[i] for i in keep]
                    line_y_positions = [line_y_positions[i] for i in keep]
                    line_y_ends = [line_y_ends[i] for i in keep]
                    line_font_sizes = [line_font_sizes[i] for i in keep]
                    # Recalculate bbox from remaining lines
                    ry0 = min(line_y_positions)
                    ry1 = max(line_y_ends)
                    rx0 = min(e[0] for e in line_extents)
                    rx1 = max(e[1] for e in line_extents)
                else:
                    # All lines were pure math — nothing left.
                    continue

        # Join lines: space for paragraph-internal line wraps (based on
        # font-size-derived leading), newline for structural breaks.
        line_joins = _detect_line_joins(
            line_y_positions,
            line_font_sizes,
            line_extents,
            line_texts,
            line_y_ends=line_y_ends,
        )
        # Compute per-line dominant bold/italic for Pass 2 guards.
        line_font_styles: list[tuple[bool, bool]] = []
        for spans in line_spans_data:
            bolds = [bool(s.get("flags", 0) & 16) for s in spans]
            italics = [bool(s.get("flags", 0) & 2) for s in spans]
            line_font_styles.append(
                (
                    _most_common(bolds, False),
                    _most_common(italics, False),
                )
            )
        _upgrade_list_joins(
            line_texts,
            line_joins,
            line_extents,
            line_font_sizes,
            line_font_styles,
        )
        _upgrade_emphasis_start_joins(line_spans_data, line_joins)
        _fix_url_line_joins(line_texts, line_joins)

        # Compute per-paragraph indents so each paragraph rendered in
        # the overlay can have its own text-indent CSS.
        para_indents = _compute_para_indents(
            line_extents,
            line_font_sizes,
            line_joins,
        )

        # Compute per-line dominant colors for per-paragraph color
        # overrides.  When consecutive lines have different colors
        # (e.g. blue author names followed by black affiliation text),
        # each paragraph preserves its own color in the overlay.
        line_dom_colors: list[int] = []
        for items in line_spans_data:
            lc = [s["color"] for s in items if "color" in s]
            line_dom_colors.append(
                _most_common(lc, 0) if lc else 0,
            )
        # Map line colors to paragraph colors using line_joins.
        # Lines joined by space are in the same paragraph; newline
        # starts a new paragraph.
        para_colors: list[int] = []
        if line_dom_colors:
            group: list[int] = [line_dom_colors[0]]
            for ji, jc in enumerate(line_joins):
                if jc == "\n":
                    para_colors.append(_most_common(group, 0))
                    group = [line_dom_colors[ji + 1]]
                else:
                    group.append(line_dom_colors[ji + 1])
            para_colors.append(_most_common(group, 0))

        plain_text = _join_lines(line_texts, line_joins)
        if not plain_text.strip():
            continue

        # Determine dominant font properties (most common across spans)
        dominant_name = _most_common(font_names, "")
        # Prefer body-only sizes (excludes sup/sub) so subscript text
        # like "model" in d_model doesn't skew the dominant size.
        dominant_size = _most_common(
            body_font_sizes or font_sizes,
            12.0,
        )
        dominant_flags = _most_common(font_flags, 0)
        dominant_color = _most_common(font_colors, 0)

        # Font flags: bit 4 (16) = bold, bit 1 (2) = italic
        is_bold = bool(dominant_flags & 16)
        is_italic = bool(dominant_flags & 2)

        # Check for mixed bold/italic/color/size/super/subscript
        mixed = _has_mixed_formatting(
            font_flags,
            roles=span_roles,
            colors=font_colors,
            sizes=font_sizes,
        )
        if mixed:
            # Encode formatting as inline HTML tags for LLM roundtrip
            tagged_lines: list[str] = []
            for line_items in line_spans_data:
                parts = [
                    # Math placeholders pass through untagged
                    s["text"]
                    if s.get("_is_math")
                    else _tag_span_text(
                        s["text"],
                        s["flags"],
                        is_bold,
                        is_italic,
                        role=s.get("role"),
                        color=s.get("color"),
                        base_color=dominant_color,
                        size=s.get("size"),
                        base_size=dominant_size,
                    )
                    for s in line_items
                ]
                tagged_lines.append("".join(parts))
            full_text = _merge_adjacent_tags(
                _join_lines(tagged_lines, line_joins),
            )
        else:
            full_text = plain_text

        # Use recalculated bbox from remaining spans (not the original
        # block bbox which may extend into table regions).
        block_rect = [rx0, ry0, rx1, ry1] if rx1 > rx0 else list(block["bbox"])

        block_entry: dict[str, Any] = {
            "rect": block_rect,
            "text": full_text,
            "font_size": dominant_size,
            "font_name": dominant_name,
            "color": dominant_color,
            "bold": is_bold,
            "italic": is_italic,
            "font_flags": dominant_flags,
            "text_align": "left",
        }
        # Detect alignment and first-line indent
        detected_align, indent_pt = _detect_block_alignment(
            line_extents,
            block_rect,
            line_font_sizes,
            page_width=page.rect.width,
        )
        block_entry["text_align"] = detected_align
        # Store line extents + y-midpoints for alignment re-derivation
        # after merge.  y-midpoints allow fragment reconstruction.
        block_entry["_line_extents"] = list(line_extents)
        block_entry["_line_sizes"] = list(line_font_sizes)
        block_entry["_line_y_mids"] = [
            (line_y_positions[k] + line_y_ends[k]) / 2.0
            for k in range(len(line_y_positions))
        ]
        # Store line y-boundaries and join array for sub-block splitting.
        # _split_multiline_blocks uses these to create per-paragraph
        # sub-blocks with independent rects for widening.
        block_entry["_line_y0s"] = list(line_y_positions)
        block_entry["_line_y1s"] = list(line_y_ends)
        block_entry["_line_joins"] = list(line_joins)
        if indent_pt > 0:
            block_entry["text_indent"] = indent_pt
        # Indents are meaningless for centered text — they shift
        # the first line off-center.
        if para_indents and detected_align != "center":
            block_entry["para_indents"] = para_indents
        # Store per-paragraph colors only when paragraphs differ
        if para_colors and len(set(para_colors)) > 1:
            block_entry["para_colors"] = para_colors
        if mixed:
            block_entry["has_mixed_formatting"] = True
        if is_space_between:
            block_entry["is_space_between"] = True
        if is_vertical:
            block_entry["is_vertical"] = True
            # Capture the text direction and origin for re-insertion.
            # For vertical text (dir=(0,-1), rotate=90) the origin is
            # the bottom-left of the text run — insert_text needs this.
            first_line = lines[0]
            block_entry["_dir"] = first_line.get("dir", (1.0, 0.0))
            first_spans = first_line.get("spans", [])
            if first_spans:
                block_entry["_origin"] = first_spans[0].get("origin")
        # Store math placeholder map (if any spans were shielded).
        if block_math_map:
            block_entry["_math_map"] = block_math_map

        # NOTE: pure-math blocks (no body text) are NOT dropped here.
        # They must survive into _merge_overlapping_math_blocks so that
        # inline math fragments split across blocks by PyMuPDF (e.g.
        # nested sqrt radicals) can be absorbed into adjacent body
        # blocks.  The post-merge filter below handles the actual drop.

        result.append(block_entry)

    # Merge blocks that overlap vertically when at least one has math
    # content.  Overlapping overlays produce garbled output because
    # redaction rectangles and HTML boxes collide visually.  Pure-math
    # fragments (e.g. "2σ²(d + 2") split off by PyMuPDF are absorbed
    # into adjacent body blocks here.
    result = _merge_overlapping_math_blocks(result)

    # NOW drop display-equation blocks that survived the merge.
    # Preserves the original TeX rendering (precise glyph positioning)
    # instead of redacting and re-overlaying.
    # Two categories:
    #  1. Pure-math blocks (_body_len == 0): no body text at all.
    #  2. Narrow math blocks with body-font labels: TeX equations like
    #     R²_schematic = max(R²_linear, R²_poly) use body fonts for
    #     subscript labels, giving _body_len > 0.  Detected by
    #     _is_display_equation (narrow + has _math_map).
    page_w = page.rect.width
    result = [
        b
        for b in result
        if not b.get("_math_map")
        or (_body_len(b) > 0 and not _is_display_equation(b, page_w))
    ]

    # Resolve rotation for grouped vertical blocks.  PyMuPDF reports
    # dir=(0,-1) for all vertical text; determine the actual growth
    # direction (up / down / center) from bbox edge alignment.
    result = _resolve_vertical_alignment(result)

    # Append per-cell blocks from detected tables
    if page_tables:
        result.extend(_extract_table_cell_blocks(page_tables, page_dict))

    # Upgrade ambiguous "left" blocks to "justify" when surrounding
    # body-text blocks consistently use justify (contextual bias).
    _refine_alignments_from_context(result)

    # Split multi-line blocks into per-paragraph sub-blocks so each
    # paragraph can be independently widened by _widen_render_rects.
    result = _split_multiline_blocks(result)

    # Extend narrow blocks to the full column width for rendering
    _widen_render_rects(result)

    return result


def _most_common(values: list[Any], default: Any) -> Any:  # noqa: ANN401
    """Returns the most common value in a list, or default if empty."""
    if not values:
        return default
    counter = Counter(values)
    return counter.most_common(1)[0][0]


# ── Table-aware extraction ─────────────────────────────────────────────

# Tolerance in points for grouping spans on the same text line.
_LINE_Y_TOLERANCE = 2.0
# Tolerance in points for grouping blocks into the same column.
_COL_X_TOLERANCE = 30.0
# Minimum horizontal line width (points) to qualify as a table rule.
_MIN_RULE_WIDTH = 50.0
# Tolerance for matching horizontal lines to the same table x-range.
_RULE_XRANGE_TOLERANCE = 5.0
# Minimum number of horizontal rules to form a table (top + mid + bottom).
_MIN_RULES_PER_TABLE = 3
# Minimum columns for a ruled region to be treated as a table.
_MIN_RULED_COLUMNS = 2
# Minimum vertical line height (points) to qualify as a column separator.
_MIN_VLINE_HEIGHT = 30.0
# Tolerance for matching vertical lines to the same table y-range.
_VLINE_YRANGE_TOLERANCE = 5.0
# Minimum number of vertical lines to form a table (3+ = at least 2 columns).
_MIN_VLINES_PER_TABLE = 3
# Minimum size (points) for a rectangle to be considered a table frame.
_MIN_FRAME_WIDTH = 50.0
_MIN_FRAME_HEIGHT = 30.0
# Minimum data rows matching the column count to confirm tabular content.
_MIN_TABULAR_ROWS = 2
# Minimum overlap ratio to consider two table regions as duplicates.
_DEDUP_OVERLAP_THRESHOLD = 0.3
# Minimum fraction of table cells that must contain text.  Tables
# below this threshold are likely false positives from figure grid
# lines (e.g. attention visualization heatmaps) where thousands of
# drawing paths create a grid but < 5% of cells have text.
_MIN_TABLE_TEXT_DENSITY = 0.15
# Only apply the density check to tables with at least this many cells.
# Small tables (< 10 cells) can legitimately have some empty cells.
_MIN_CELLS_FOR_DENSITY_CHECK = 20


def _find_overlap_index(
    bbox: tuple[float, ...],
    existing: list[dict[str, Any]],
) -> int | None:
    """Return the index of the first significantly overlapping table.

    Returns the index when the intersection area exceeds
    ``_DEDUP_OVERLAP_THRESHOLD`` of either the candidate or existing
    table bbox (whichever is smaller).

    Args:
        bbox: (x0, y0, x1, y1) of the candidate table.
        existing: List of already-accepted table dicts with 'bbox' key.

    Returns:
        Index into *existing*, or ``None`` if no overlap.
    """
    ax0, ay0, ax1, ay1 = bbox
    a_area = max((ax1 - ax0) * (ay1 - ay0), 1e-6)
    for idx, table in enumerate(existing):
        bx0, by0, bx1, by1 = table["bbox"]
        ix0 = max(ax0, bx0)
        iy0 = max(ay0, by0)
        ix1 = min(ax1, bx1)
        iy1 = min(ay1, by1)
        if ix0 < ix1 and iy0 < iy1:
            inter = (ix1 - ix0) * (iy1 - iy0)
            b_area = max((bx1 - bx0) * (by1 - by0), 1e-6)
            smaller = min(a_area, b_area)
            if inter / smaller >= _DEDUP_OVERLAP_THRESHOLD:
                return idx
    return None


def _bbox_overlaps_any(
    bbox: tuple[float, ...],
    existing: list[dict[str, Any]],
) -> bool:
    """Check if a bbox overlaps significantly with any existing table.

    Returns True when the intersection area exceeds
    ``_DEDUP_OVERLAP_THRESHOLD`` of either the new bbox or any existing
    table bbox (whichever is smaller).  This prevents both a large table
    from swallowing a smaller one and vice-versa.

    Args:
        bbox: (x0, y0, x1, y1) of the candidate table.
        existing: List of already-accepted table dicts with 'bbox' key.
    """
    return _find_overlap_index(bbox, existing) is not None


def _table_text_density(
    table_info: dict[str, Any],
    page_dict: dict[str, Any],
) -> float:
    """Fraction of table cells that contain at least one text span.

    Used to filter false-positive tables from figure grid lines where
    hundreds of cells exist but almost none contain text.
    """
    cells = table_info.get("cells", [])
    if not cells:
        return 0.0
    non_empty = sum(1 for cell in cells if _get_spans_in_rect(page_dict, cell))
    return non_empty / len(cells)


def _find_page_tables(  # noqa: PLR0912
    page: Any,  # noqa: ANN401
    page_dict: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Detect tables on a page.

    Runs all detectors and combines their results.  Later detectors only
    add tables whose bounding box does not overlap a region already found
    by an earlier (higher-confidence) detector.

    Tables with many cells but very low text density (< 15%) are
    discarded as false positives from figure grid lines.

    Detector priority (highest confidence first):
    1. PyMuPDF ``find_tables()`` — full-grid tables.
    2. ``_detect_ruled_tables()`` — booktabs-style (horizontal rules only).
    3. ``_detect_vline_tables()`` — vertical column separators only.
    4. ``_detect_framed_tables()`` — outer-border rectangle with tabular
       content verification.

    Args:
        page: A PyMuPDF Page object.
        page_dict: Optional pre-computed ``page.get_text("dict")``.

    Returns:
        List of dicts with 'bbox' (4-tuple) and 'cells' (list of 4-tuples).
        Empty list if no tables are found or on error.
    """
    found: list[dict[str, Any]] = []

    # Cache drawings once — get_drawings() is extremely expensive on
    # pages with complex vector graphics (e.g. matplotlib plots).
    # On such pages a single call can take 20+ seconds and create
    # millions of Point objects.
    try:
        drawings: list[dict[str, Any]] | None = page.get_drawings()
    except Exception:
        logger.debug("get_drawings failed", exc_info=True)
        drawings = None

    # Skip ALL table detection if the page has an excessive number of
    # drawing elements (likely complex figures/charts, not tables).
    _MAX_DRAWINGS = 500000  # noqa: N806
    if drawings is not None and len(drawings) > _MAX_DRAWINGS:
        return []

    # 1. PyMuPDF built-in (highest confidence)
    try:
        tables = page.find_tables()
        if tables.tables:
            for table in tables.tables:
                found.append(
                    {
                        "bbox": table.bbox,
                        "cells": [c for c in table.cells if c is not None],
                    }
                )
    except Exception:
        logger.debug("find_tables failed on page", exc_info=True)

    if page_dict is None:
        page_dict = page.get_text("dict")

    # 2. Ruled-table detector — hybrid merge with find_tables() results.
    # Visual borders from find_tables() are geometrically exact (drawn
    # lines).  The ruled detector infers sub-columns from text gaps.
    # When both find the same table, we keep visual borders as anchors
    # and add inferred sub-dividers within visual columns.
    for table_info in _detect_ruled_tables(page, page_dict, drawings=drawings):
        overlap_idx = _find_overlap_index(table_info["bbox"], found)
        if overlap_idx is None:
            # No overlap — add as new table
            found.append(table_info)
        elif len(table_info["cells"]) > len(found[overlap_idx]["cells"]):
            # Overlaps but ruled table has more cells — hybrid merge
            merged = _merge_visual_and_inferred(
                found[overlap_idx],
                table_info,
                page_dict,
            )
            found[overlap_idx] = merged

    # 3–4. Other fallback detectors (only add non-overlapping regions)
    for detector in (
        _detect_vline_tables,
        _detect_framed_tables,
    ):
        for table_info in detector(page, page_dict, drawings=drawings):
            if not _bbox_overlaps_any(table_info["bbox"], found):
                found.append(table_info)

    # Filter out false-positive tables from figure grid lines.
    # Real tables have text in most cells; figure grids have hundreds
    # of cells but almost no text content.
    filtered: list[dict[str, Any]] = []
    for table_info in found:
        n_cells = len(table_info.get("cells", []))
        if n_cells >= _MIN_CELLS_FOR_DENSITY_CHECK:
            density = _table_text_density(table_info, page_dict)
            if density < _MIN_TABLE_TEXT_DENSITY:
                continue
        filtered.append(table_info)

    return filtered


# Minimum sub-column width (points) when merging visual + inferred dividers.
_MIN_SUBCOL_WIDTH = 8.0
# Maximum distance (points) to consider two dividers as duplicates.
_DIVIDER_SNAP_TOLERANCE = 2.0


def _merge_visual_and_inferred(
    visual_table: dict[str, Any],
    ruled_table: dict[str, Any],
    page_dict: dict[str, Any],
) -> dict[str, Any]:
    """Merge visual borders (from ``find_tables``) with inferred sub-columns.

    Visual borders from drawn lines are geometrically exact and are kept
    as anchors.  Inferred dividers from text-gap analysis are added only
    when they fall *inside* a visual column and create sub-columns that
    are at least ``_MIN_SUBCOL_WIDTH`` wide.

    Args:
        visual_table: Table dict from ``find_tables()`` with 'bbox' and 'cells'.
        ruled_table:  Table dict from ``_detect_ruled_tables()`` with the same.
        page_dict:    Result of ``page.get_text("dict")``.

    Returns:
        A new table dict with merged column dividers and rebuilt cells.
    """
    # --- Extract visual x-dividers (ground truth from drawn lines) ---
    visual_x: set[float] = set()
    for cell in visual_table["cells"]:
        visual_x.add(cell[0])
        visual_x.add(cell[2])
    visual_dividers = sorted(visual_x)

    # --- Extract inferred x-dividers (from text gap analysis) ---
    inferred_x: set[float] = set()
    for cell in ruled_table["cells"]:
        inferred_x.add(cell[0])
        inferred_x.add(cell[2])
    inferred_dividers = sorted(inferred_x)

    # --- Merge: visual as anchors, inferred as sub-dividers ---
    merged = list(visual_dividers)
    for inf_d in inferred_dividers:
        # Skip if it duplicates (snaps to) a visual divider
        if any(abs(inf_d - vd) < _DIVIDER_SNAP_TOLERANCE for vd in visual_dividers):
            continue
        # Find the visual column this divider falls into
        for i in range(len(visual_dividers) - 1):
            v_left = visual_dividers[i]
            v_right = visual_dividers[i + 1]
            if v_left < inf_d < v_right:
                # Check both resulting sub-columns are wide enough
                left_w = inf_d - v_left
                right_w = v_right - inf_d
                # Also check against existing merged dividers in this column
                # to avoid creating a narrow sliver next to a previously
                # added sub-divider.
                neighbours = [d for d in merged if v_left <= d <= v_right]
                neighbours.sort()
                ok = True
                for nb in neighbours:
                    if abs(inf_d - nb) < _MIN_SUBCOL_WIDTH:
                        ok = False
                        break
                if ok and left_w >= _MIN_SUBCOL_WIDTH and right_w >= _MIN_SUBCOL_WIDTH:
                    merged.append(inf_d)
                break
    merged = sorted(set(merged))

    # --- Extract row boundaries from both tables ---
    visual_y: set[float] = set()
    for cell in visual_table["cells"]:
        visual_y.add(cell[1])
        visual_y.add(cell[3])
    ruled_y: set[float] = set()
    for cell in ruled_table["cells"]:
        ruled_y.add(cell[1])
        ruled_y.add(cell[3])
    # Use the finer set of row boundaries (ruled detector has horizontal rules)
    row_bounds = sorted(visual_y | ruled_y)

    # --- Use the larger bbox (union) ---
    bbox = ruled_table["bbox"]

    # --- Rebuild cells using merged dividers + row boundaries ---
    cells: list[tuple[float, ...]] = []
    for r in range(len(row_bounds) - 1):
        ry0, ry1 = row_bounds[r], row_bounds[r + 1]
        row_cells = _build_row_cells_with_spanning(
            page_dict,
            merged,
            ry0,
            ry1,
        )
        cells.extend(row_cells)

    return {"bbox": bbox, "cells": cells}


# ── Ruled (booktabs) table detection ───────────────────────────────────


def _find_horizontal_rules(
    page: Any,  # noqa: ANN401
    drawings: list[dict[str, Any]] | None = None,
) -> list[dict[str, float]]:
    """Find wide horizontal lines drawn on a page.

    Scans all vector drawings for line items that are horizontal
    (Δy < 1pt) and wider than ``_MIN_RULE_WIDTH``.

    Args:
        page: A PyMuPDF Page object.
        drawings: Optional pre-computed ``page.get_drawings()`` result.

    Returns:
        List of dicts with keys 'y', 'x0', 'x1'.
    """
    h_lines: list[dict[str, float]] = []
    try:
        for drawing in drawings if drawings is not None else page.get_drawings():
            for item in drawing.get("items", []):
                if item[0] != "l":
                    continue
                p1, p2 = item[1], item[2]
                if abs(p1.y - p2.y) < 1.0 and abs(p1.x - p2.x) > _MIN_RULE_WIDTH:
                    h_lines.append(
                        {
                            "y": (p1.y + p2.y) / 2,
                            "x0": min(p1.x, p2.x),
                            "x1": max(p1.x, p2.x),
                        }
                    )
    except Exception:
        logger.debug("get_drawings failed", exc_info=True)
    return h_lines


def _group_rules_by_xrange(
    h_lines: list[dict[str, float]],
) -> list[list[dict[str, float]]]:
    """Group horizontal lines that share the same x-range.

    Two lines are considered part of the same group when their left and
    right endpoints are both within ``_RULE_XRANGE_TOLERANCE`` of the
    group's first line.

    Returns:
        List of groups, each a list of line dicts.
    """
    groups: list[list[dict[str, float]]] = []
    for line in h_lines:
        placed = False
        for group in groups:
            ref = group[0]
            if (
                abs(line["x0"] - ref["x0"]) < _RULE_XRANGE_TOLERANCE
                and abs(line["x1"] - ref["x1"]) < _RULE_XRANGE_TOLERANCE
            ):
                group.append(line)
                placed = True
                break
        if not placed:
            groups.append([line])
    return groups


def _adjust_dividers_for_text(  # noqa: PLR0912
    dividers: list[float],
    text_rows: list[list[dict[str, Any]]],
) -> None:
    """Adjust column dividers so they don't cut through text.

    Gap-voting and most-common strategies compute dividers from a subset
    of rows (typically the densest ones).  Rows excluded from the analysis
    may have wider text that extends past the computed divider.

    Two adjustments are applied to each interior divider:

    1. **Shift left**: when a span starts before the divider but its center
       is past it (e.g. a header like "Maximum Path Length" that is wider
       than the data rows used to compute the gap).

    2. **Shift right**: when a span whose center is clearly in the left
       column has its right edge past the divider (e.g. "Self-Attention
       (restricted)" is wider than "Recurrent" used for gap computation).
       The divider moves to the midpoint between that span's right edge
       and the nearest right-column span's left edge.

    Args:
        dividers: Column boundary x-positions (modified in place).
        text_rows: List of rows (each a sorted list of span dicts).
    """
    # Compute maximum allowed span width for adjustment triggers.
    # Spans wider than twice the median column width are likely cross-column
    # annotations (footnotes, captions) and must not shift dividers.
    if len(dividers) >= 3:  # noqa: PLR2004
        col_widths = [dividers[i + 1] - dividers[i] for i in range(len(dividers) - 1)]
        col_widths.sort()
        median_w = col_widths[len(col_widths) // 2]
        max_span_w = max(median_w * 2, 60.0)
    else:
        max_span_w = float("inf")

    for di in range(1, len(dividers) - 1):
        d = dividers[di]

        # --- Adjustment 1: shift LEFT for right-column text that starts
        # before the divider (center past it) ---
        min_sx0: float | None = None
        for row in text_rows:
            for span in row:
                sx0 = span["bbox"][0]
                sx1 = span["bbox"][2]
                scx = (sx0 + sx1) / 2
                # Skip cross-column spans (footnotes, captions)
                if sx1 - sx0 > max_span_w:
                    continue
                if sx0 < d - 1.0 and scx > d and (min_sx0 is None or sx0 < min_sx0):
                    min_sx0 = sx0
        if min_sx0 is not None:
            max_right = dividers[di - 1]
            for row in text_rows:
                for span in row:
                    scx = (span["bbox"][0] + span["bbox"][2]) / 2
                    if scx < d:
                        max_right = max(max_right, span["bbox"][2])
            new_d = (max_right + min_sx0) / 2
            if new_d < d:
                dividers[di] = new_d
                d = new_d  # update for adjustment 2

        # --- Adjustment 2: shift RIGHT for left-column text whose right
        # edge extends past the divider ---
        max_overflow: float | None = None
        for row in text_rows:
            for span in row:
                sx0 = span["bbox"][0]
                sx1 = span["bbox"][2]
                scx = (sx0 + sx1) / 2
                # Skip cross-column spans (footnotes, captions)
                if sx1 - sx0 > max_span_w:
                    continue
                # Span center is in the left column but right edge overflows
                if (
                    scx < d
                    and sx1 > d + 1.0
                    and (max_overflow is None or sx1 > max_overflow)
                ):
                    max_overflow = sx1
        if max_overflow is not None:
            # Find the leftmost span start in the right column
            min_right_x0: float | None = None
            for row in text_rows:
                for span in row:
                    scx = (span["bbox"][0] + span["bbox"][2]) / 2
                    if scx > d:
                        sx0 = span["bbox"][0]
                        if min_right_x0 is None or sx0 < min_right_x0:
                            min_right_x0 = sx0
            if min_right_x0 is not None and min_right_x0 > max_overflow:
                new_d = (max_overflow + min_right_x0) / 2
                if new_d > d:
                    dividers[di] = new_d


def _infer_columns(
    text_rows: list[list[dict[str, Any]]],
    table_bbox: tuple[float, ...],
) -> tuple[int, list[float]]:
    """Infer column count and x-boundaries from text row data.

    Two strategies are tried and the one producing more columns wins:

    1. **Most-common**: uses the most common span count across rows and
       derives dividers from rows matching that count.  Works well when
       most rows have the same number of populated cells.

    2. **Gap-voting**: collects inter-span gaps across all rows and
       clusters them by x-position.  A gap position that appears in at
       least 2 rows becomes a column divider.  Handles sparse tables
       where row span counts vary widely.

    Args:
        text_rows: List of rows, each a list of PyMuPDF span dicts
            (already sorted by x within each row).
        table_bbox: (x0, y0, x1, y1) of the table region.

    Returns:
        Tuple of (column_count, col_dividers) where col_dividers is a
        list of length column_count + 1 (table-left, dividers, table-right).
    """
    x0, _, x1, _ = table_bbox

    # Strip whitespace-only spans — they inflate per-row span counts
    # and cause the most-common strategy to create spurious columns
    # (e.g. a space span between "Petrov et al." and "(2006) [29]").
    text_rows = [
        [s for s in row if "text" not in s or s["text"].strip()] for row in text_rows
    ]
    text_rows = [r for r in text_rows if r]

    span_counts = [len(r) for r in text_rows]
    if not span_counts:
        return 0, []

    # --- Strategy 1: most-common span count ---
    mc_count = Counter(span_counts).most_common(1)[0][0]
    mc_dividers: list[float] = []
    if mc_count >= _MIN_RULED_COLUMNS:
        col_rights: list[list[float]] = [[] for _ in range(mc_count)]
        col_lefts: list[list[float]] = [[] for _ in range(mc_count)]
        for row in text_rows:
            if len(row) != mc_count:
                continue
            for k, span in enumerate(row):
                col_lefts[k].append(span["bbox"][0])
                col_rights[k].append(span["bbox"][2])
        mc_dividers = [x0]
        for k in range(mc_count - 1):
            right_max = max(col_rights[k]) if col_rights[k] else x0
            left_min = min(col_lefts[k + 1]) if col_lefts[k + 1] else x1
            # Only add a divider when there is a real gap between
            # adjacent span groups.  Tiny gaps (e.g. "Petrov et al."
            # followed by "(2006) [29]") are intra-cell spacing, not
            # column boundaries.
            if left_min - right_max >= _MIN_COL_GAP:
                mc_dividers.append((right_max + left_min) / 2)
        mc_dividers.append(x1)
        mc_count = len(mc_dividers) - 1

    # --- Strategy 2: gap-voting across all rows ---
    gap_dividers = _infer_columns_by_gaps(text_rows, table_bbox)
    gap_count = len(gap_dividers) - 1 if gap_dividers else 0

    # Validate the mc result: if many columns are too narrow (< 8pt),
    # character-level span splitting is inflating the count.
    mc_valid = mc_count >= _MIN_RULED_COLUMNS and mc_dividers
    if mc_valid:
        widths = [
            mc_dividers[i + 1] - mc_dividers[i] for i in range(len(mc_dividers) - 1)
        ]
        narrow_count = sum(1 for w in widths if w < 8.0)  # noqa: PLR2004
        if narrow_count > mc_count * 0.3:
            mc_valid = False

    # Prefer gap approach when mc is invalid (character-level splits)
    # or when gap finds substantially more columns.
    if gap_count >= _MIN_RULED_COLUMNS and (not mc_valid or gap_count > mc_count * 2):
        _adjust_dividers_for_text(gap_dividers, text_rows)
        return gap_count, gap_dividers
    if mc_valid:
        _adjust_dividers_for_text(mc_dividers, text_rows)
        return mc_count, mc_dividers
    if gap_count >= _MIN_RULED_COLUMNS:
        _adjust_dividers_for_text(gap_dividers, text_rows)
        return gap_count, gap_dividers
    return 0, []


# Minimum gap width (points) for gap-voting column detection.
_MIN_COL_GAP = 5.0
# Clustering tolerance for gap center positions (points).
_GAP_CLUSTER_TOL = 10.0
# Minimum number of rows that must share a gap for it to count.
_GAP_MIN_VOTES = 2


def _infer_columns_by_gaps(
    text_rows: list[list[dict[str, Any]]],
    table_bbox: tuple[float, ...],
) -> list[float]:
    """Infer column dividers from inter-span gaps in the densest rows.

    Uses only the rows with the highest span counts (≥70% of the max
    span count) for gap analysis.  These rows have the most complete
    column structure and produce the most reliable gaps — sparse rows
    would contribute noisy wide gaps that span multiple real columns.

    Gaps at similar x-positions across multiple dense rows are clustered
    and each cluster with sufficient support becomes a column divider.

    Args:
        text_rows: List of rows (each a sorted list of span dicts).
        table_bbox: (x0, y0, x1, y1) of the table region.

    Returns:
        Column dividers list (table-left, dividers, table-right), or
        empty list if no meaningful gaps are found.
    """
    x0, _, x1, _ = table_bbox
    if not text_rows:
        return []

    # Select the densest rows — those within 2 spans of the maximum.
    # These rows have the most populated cells and their inter-span
    # gaps best reflect the true column structure.
    max_spans = max(len(r) for r in text_rows)
    threshold = max(max_spans - 2, _MIN_RULED_COLUMNS)
    dense_rows = [r for r in text_rows if len(r) >= threshold]
    if not dense_rows:
        return []

    # With very few dense rows, accept every gap (min_votes=1).
    min_votes = max(1, len(dense_rows) // 3)

    # Collect inter-span gaps from dense rows
    gaps: list[tuple[float, float]] = []
    for row in dense_rows:
        for i in range(len(row) - 1):
            right = row[i]["bbox"][2]
            left = row[i + 1]["bbox"][0]
            gap_w = left - right
            if gap_w >= _MIN_COL_GAP:
                gaps.append(((right + left) / 2, gap_w))

    if not gaps:
        return []

    # Cluster gaps by x-center proximity.  Compare with the cluster
    # anchor (first element) to prevent chain drift.
    gaps.sort()
    clusters: list[list[float]] = [[gaps[0][0]]]
    for center, _ in gaps[1:]:
        if center - clusters[-1][0] < _GAP_CLUSTER_TOL:
            clusters[-1].append(center)
        else:
            clusters.append([center])

    # Keep clusters with enough votes
    divider_positions: list[float] = []
    for cluster in clusters:
        if len(cluster) >= min_votes:
            cluster.sort()
            divider_positions.append(cluster[len(cluster) // 2])

    if not divider_positions:
        return []

    return [x0, *divider_positions, x1]


def _group_spans_into_rows(
    spans: list[dict[str, Any]],
) -> list[list[dict[str, Any]]]:
    """Group spans by y-position into text rows, sorted by x within each.

    Args:
        spans: Flat list of PyMuPDF span dicts.

    Returns:
        List of rows, each a list of spans sorted by x.
    """
    if not spans:
        return []
    sorted_spans = sorted(spans, key=lambda s: (s["bbox"][1], s["bbox"][0]))
    rows: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = [sorted_spans[0]]
    for span in sorted_spans[1:]:
        if abs(span["bbox"][1] - current[0]["bbox"][1]) < _LINE_Y_TOLERANCE:
            current.append(span)
        else:
            current.sort(key=lambda s: s["bbox"][0])
            rows.append(current)
            current = [span]
    current.sort(key=lambda s: s["bbox"][0])
    rows.append(current)
    return rows


def _row_column_count(
    row: list[dict[str, Any]],
    col_dividers: list[float],
) -> int:
    """Count how many distinct column regions a text row occupies."""
    cols_hit: set[int] = set()
    n_cols = len(col_dividers) - 1
    for span in row:
        cx = (span["bbox"][0] + span["bbox"][2]) / 2
        for c in range(n_cols):
            if col_dividers[c] <= cx <= col_dividers[c + 1]:
                cols_hit.add(c)
                break
    return len(cols_hit)


def _build_row_boundaries(
    text_rows: list[list[dict[str, Any]]],
    rule_ys: list[float],
    col_count: int,
    table_bbox: tuple[float, ...],
    col_dividers: list[float] | None = None,
) -> list[float]:
    """Compute row y-boundaries for a ruled table.

    For horizontal-rule intervals that contain multiple data-like text
    rows (each having spans across multiple columns), each text row
    becomes its own row.  For intervals where a row spans only one
    column (e.g. wrapped text within a cell), the entire interval
    remains one row.

    Args:
        text_rows: Text rows within the table (sorted by y).
        rule_ys: Sorted y-positions of horizontal rules.
        col_count: Expected number of columns.
        table_bbox: (x0, y0, x1, y1) of the table.
        col_dividers: Column boundary x-positions for multi-column check.

    Returns:
        Sorted list of row boundary y-values (length = row_count + 1).
    """
    _, y0, _, y1 = table_bbox

    # For each horizontal-rule interval, decide whether to subdivide
    boundaries: set[float] = {y0, y1}
    boundaries.update(rule_ys)

    sorted_rules = sorted(boundaries)
    final_boundaries: list[float] = []

    for idx in range(len(sorted_rules) - 1):
        interval_top = sorted_rules[idx]
        interval_bot = sorted_rules[idx + 1]

        # Find text rows within this interval
        interval_rows = [
            row
            for row in text_rows
            if interval_top <= row[0]["bbox"][1] <= interval_bot
        ]

        if not interval_rows:
            # No text in this interval — still include boundaries
            if not final_boundaries:
                final_boundaries.append(interval_top)
            continue

        # Check if this interval should be subdivided.
        # A text row is "data-like" when its spans cover at least half
        # the table's columns.  This is more robust than the exact match
        # ``len(r) == col_count`` because superscripts and scientific
        # notation inflate span counts, yet avoids splitting header
        # intervals where a grouped header row has far fewer columns
        # than the full table.
        min_cols = max(col_count // 2, _MIN_RULED_COLUMNS)
        should_subdivide = len(interval_rows) > 1 and all(
            _row_column_count(r, col_dividers) >= min_cols
            if col_dividers
            else len(r) >= min_cols
            for r in interval_rows
        )

        if not final_boundaries:
            final_boundaries.append(interval_top)

        if should_subdivide:
            # Each text row becomes a separate row; compute mid-boundaries
            for i in range(len(interval_rows) - 1):
                bot_y = max(s["bbox"][3] for s in interval_rows[i])
                top_y = min(s["bbox"][1] for s in interval_rows[i + 1])
                final_boundaries.append((bot_y + top_y) / 2)
        # Always close the interval
        final_boundaries.append(interval_bot)

    return sorted(set(final_boundaries))


def _build_row_cells_with_spanning(  # noqa: PLR0912
    page_dict: dict[str, Any],
    col_dividers: list[float],
    ry0: float,
    ry1: float,
) -> list[tuple[float, ...]]:
    """Build cells for one table row, merging columns when spans cross dividers.

    For most rows in sparse tables, each span sits within a single column
    and produces a narrow cell.  When a span extends across multiple column
    dividers (e.g. a label like "(E) positional embedding..."), the affected
    columns are merged into a single wider cell for that row.

    Args:
        page_dict: Result of ``page.get_text("dict")``.
        col_dividers: Sorted list of column boundary x-positions.
        ry0: Top y of the row.
        ry1: Bottom y of the row.

    Returns:
        List of cell tuples ``(x0, y0, x1, y1)`` for this row.
    """
    n_cols = len(col_dividers) - 1
    if n_cols <= 0:
        return []

    # Find spans whose vertical center falls within this row
    row_spans = _get_spans_in_rect(
        page_dict,
        (col_dividers[0], ry0, col_dividers[-1], ry1),
    )
    if not row_spans:
        # No text — produce the simple grid for this row
        return [(col_dividers[c], ry0, col_dividers[c + 1], ry1) for c in range(n_cols)]

    # For each span, find the column range [left_col, right_col] it covers.
    # A span "covers" a column only when the overlap is significant —
    # either the span center falls within the column, or the overlap
    # exceeds 30% of the column width.  This prevents labels that
    # slightly spill past a divider from merging adjacent columns.
    occupied: list[bool] = [False] * n_cols
    merge_groups: list[tuple[int, int]] = []  # (left_col, right_col) inclusive
    for span in row_spans:
        sx0, sx1 = span["bbox"][0], span["bbox"][2]
        scx = (sx0 + sx1) / 2
        left_col = right_col = -1
        for c in range(n_cols):
            cx0, cx1 = col_dividers[c], col_dividers[c + 1]
            cw = cx1 - cx0
            overlap = min(sx1, cx1) - max(sx0, cx0)
            if overlap > 0 and (cx0 <= scx <= cx1 or overlap > cw * 0.3):
                if left_col == -1:
                    left_col = c
                right_col = c
        if left_col >= 0:
            merge_groups.append((left_col, right_col))
            for c in range(left_col, right_col + 1):
                occupied[c] = True

    # Resolve overlapping merge groups into non-overlapping ranges
    if merge_groups:
        merge_groups.sort()
        merged: list[tuple[int, int]] = [merge_groups[0]]
        for lo, hi in merge_groups[1:]:
            prev_lo, prev_hi = merged[-1]
            if lo <= prev_hi:
                merged[-1] = (prev_lo, max(prev_hi, hi))
            else:
                merged.append((lo, hi))
    else:
        merged = []

    # Build cells: merged ranges become single wide cells,
    # unoccupied columns become individual cells.
    cells: list[tuple[float, ...]] = []
    used: set[int] = set()
    for lo, hi in merged:
        cells.append((col_dividers[lo], ry0, col_dividers[hi + 1], ry1))
        for c in range(lo, hi + 1):
            used.add(c)
    for c in range(n_cols):
        if c not in used:
            cells.append((col_dividers[c], ry0, col_dividers[c + 1], ry1))

    return cells


def _detect_ruled_tables(  # noqa: PLR0912, PLR0915
    page: Any,  # noqa: ANN401
    page_dict: dict[str, Any],
    drawings: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Detect booktabs-style tables bounded by horizontal rules only.

    Academic papers commonly use tables with horizontal rules (top, header
    separator, bottom) but no vertical column separators.  ``find_tables()``
    cannot detect these.  This function identifies them from drawn horizontal
    lines, then infers column structure from text span positions.

    Args:
        page: A PyMuPDF Page object.
        page_dict: Result of ``page.get_text("dict")``.
        drawings: Optional pre-computed ``page.get_drawings()`` result.

    Returns:
        Same format as ``_find_page_tables``: list of dicts with 'bbox'
        and 'cells'.
    """
    h_lines = _find_horizontal_rules(page, drawings=drawings)
    if len(h_lines) < _MIN_RULES_PER_TABLE:
        return []

    groups = _group_rules_by_xrange(h_lines)
    table_groups = [g for g in groups if len(g) >= _MIN_RULES_PER_TABLE]
    if not table_groups:
        return []

    results: list[dict[str, Any]] = []

    for group in table_groups:
        group.sort(key=lambda line: line["y"])
        bbox = (
            min(line["x0"] for line in group),
            group[0]["y"],
            max(line["x1"] for line in group),
            group[-1]["y"],
        )

        spans = _get_spans_in_rect(page_dict, bbox)
        if not spans:
            continue

        text_rows = _group_spans_into_rows(spans)
        col_count, col_dividers = _infer_columns(text_rows, bbox)
        if col_count < _MIN_RULED_COLUMNS:
            continue

        rule_ys = sorted({round(line["y"], 1) for line in group})
        row_bounds = _build_row_boundaries(
            text_rows,
            rule_ys,
            col_count,
            bbox,
            col_dividers,
        )

        # Include partial horizontal rules as additional row boundaries.
        # Multi-level headers (e.g. "BLEU" above "EN-DE") use a partial
        # rule that doesn't span the full table width.  These are grouped
        # separately by _group_rules_by_xrange and would otherwise be
        # lost.  Adding their y-positions splits header rows into
        # sub-rows so each header level gets its own cell.
        #
        # Only add partial rules whose combined span at a given y covers
        # at least half the table width.  Narrow rules (e.g. under 3 of
        # 12 columns) would split the entire row — squeezing unrelated
        # columns into thin sub-rows.
        table_width = bbox[2] - bbox[0]
        has_partial_rules = False
        # Group partial rules by y-position (within 2pt tolerance).
        partial_by_y: dict[float, float] = {}  # y → total width
        for line in h_lines:
            lw = line["x1"] - line["x0"]
            if lw >= table_width * 0.9:
                continue  # full-width rule, already in group
            ly = line["y"]
            if not (bbox[1] < ly < bbox[3]):
                continue
            # Skip rules that don't overlap the table's x-range.
            # Lines from adjacent tables in multi-column layouts can
            # share the same y-range but be horizontally disjoint.
            if line["x1"] < bbox[0] or line["x0"] > bbox[2]:
                continue
            # Find existing y-bucket or create new one
            matched = False
            for ey in list(partial_by_y):
                if abs(ly - ey) <= 2.0:  # noqa: PLR2004
                    partial_by_y[ey] += lw
                    matched = True
                    break
            if not matched:
                partial_by_y[ly] = lw
        for ly, total_w in partial_by_y.items():
            if total_w < table_width * 0.5:
                continue  # too narrow — would hurt unrelated columns
            has_partial_rules = True
            if all(abs(ly - rb) > 2.0 for rb in row_bounds):  # noqa: PLR2004
                row_bounds.append(ly)
        row_bounds.sort()

        # Multi-level headers with merged parent cells (e.g. "Cost"
        # spanning sub-columns "A" and "B") cause the most-common
        # strategy to undercount columns.  Re-infer via gap-voting
        # when partial rules confirm a multi-level header structure.
        if has_partial_rules:
            gap_dividers = _infer_columns_by_gaps(text_rows, bbox)
            gap_count = len(gap_dividers) - 1 if gap_dividers else 0
            # Accept gap-voting only if it produces more columns AND
            # none of the resulting columns are extremely narrow (< 8pt),
            # which indicates a spurious split.
            if gap_count > col_count:
                gap_widths = [
                    gap_dividers[k + 1] - gap_dividers[k] for k in range(gap_count)
                ]
                if all(w >= 8.0 for w in gap_widths):  # noqa: PLR2004
                    col_count, col_dividers = gap_count, gap_dividers

        # Build cells with per-row spanning detection.
        # For each row, check if any span crosses column dividers;
        # if so, merge the affected columns into one wider cell.
        cells: list[tuple[float, ...]] = []
        for r in range(len(row_bounds) - 1):
            ry0, ry1 = row_bounds[r], row_bounds[r + 1]
            row_cells = _build_row_cells_with_spanning(
                page_dict,
                col_dividers,
                ry0,
                ry1,
            )
            cells.extend(row_cells)

        results.append({"bbox": bbox, "cells": cells})

    return results


def _get_spans_in_rect(
    page_dict: dict[str, Any],
    rect: tuple[float, ...] | list[float],
) -> list[dict[str, Any]]:
    """Find all text spans whose center falls within the given rect.

    Args:
        page_dict: Result of page.get_text("dict").
        rect: (x0, y0, x1, y1) bounding box.

    Returns:
        List of span dicts from PyMuPDF.
    """
    rx0, ry0, rx1, ry1 = rect
    tol = _DIR_HORIZONTAL_TOLERANCE
    spans: list[dict[str, Any]] = []
    for block in page_dict.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            # Skip rotated/vertical lines (figure axis labels).
            dx, dy = line.get("dir", (1.0, 0.0))
            if not (abs(dx - 1.0) < tol and abs(dy) < tol):
                continue
            for span in line.get("spans", []):
                sx0, sy0, sx1, sy1 = span["bbox"]
                scx = (sx0 + sx1) / 2
                scy = (sy0 + sy1) / 2
                if rx0 <= scx <= rx1 and ry0 <= scy <= ry1:
                    spans.append(span)
    return spans


def _detect_block_alignment(  # noqa: PLR0912, PLR0915
    line_extents: list[tuple[float, float]],
    block_rect: list[float] | tuple[float, ...],
    line_sizes: list[float] | None = None,
    page_width: float = 0.0,
) -> tuple[str, float]:
    """Detect text alignment and first-line indent for a text block.

    Uses the same median-based approach as ``_detect_line_joins`` for
    robust alignment detection.  Adds "justify" to the possible results
    and computes a first-line indent in points when the first line is
    shifted rightward from the typical left margin.

    For single-line blocks, multi-line heuristics cannot work so the
    function falls back to page-level centering detection: if the block
    has significant, roughly symmetric margins relative to the page
    width, it is classified as centered.

    Args:
        line_extents: List of (line_x0, line_x1) for each text line.
        block_rect: (x0, y0, x1, y1) bounding box of the block.
        line_sizes: Optional per-line dominant font sizes.
        page_width: Full page width in points for single-line centering.

    Returns:
        Tuple of (css_text_align, first_line_indent_pt).
        css_text_align is "left", "center", "right", or "justify".
        first_line_indent_pt is 0.0 when no indent is detected.
    """
    n = len(line_extents)
    if n == 0:
        return ("left", 0.0)

    bx0 = block_rect[0]
    bx1 = block_rect[2]
    bw = bx1 - bx0
    if bw <= 0:
        return ("left", 0.0)

    # Single-line: can only detect page-level centering.
    # Multi-line detection needs line variation; with 1 line there is
    # no left/right edge variance to analyze.  Instead, check whether
    # the block is positioned centrally relative to the page width.
    # The width cap (65%) excludes full-width body paragraphs whose
    # margins are naturally symmetric on standard-layout pages.
    if n == 1:
        if page_width > 0:
            left_m = bx0
            right_m = page_width - bx1
            if (
                bw < page_width * 0.65
                and left_m > page_width * 0.05
                and right_m > page_width * 0.05
                and abs(left_m - right_m) < page_width * 0.1
            ):
                return ("center", 0.0)
        return ("left", 0.0)

    # Median-based reference edges (robust to outliers).
    sorted_lefts = sorted(ext[0] for ext in line_extents)
    sorted_rights = sorted(ext[1] for ext in line_extents)
    typical_left = sorted_lefts[n // 2]
    typical_right = sorted_rights[n // 2]

    # Dynamic tolerance based on font size.
    dom_size = max(line_sizes) if line_sizes else 12.0
    align_tol = max(dom_size * 0.75, 3.0)

    # Count lines at the left edge.  Check both the median left (typical_left)
    # and the minimum left (margin) to handle blocks with multiple indent
    # levels (e.g. list items indented from body text).
    margin_left_ref = sorted_lefts[0]
    lines_at_left = sum(
        1
        for ext in line_extents
        if abs(ext[0] - typical_left) <= align_tol
        or abs(ext[0] - margin_left_ref) <= align_tol
    )
    is_left = lines_at_left > n / 2

    lines_at_right = sum(
        1 for ext in line_extents if abs(ext[1] - typical_right) <= align_tol
    )
    # In justified text the last line is naturally short — it should
    # not count against right-edge alignment.  Detect a short final
    # line: left-aligned start but right edge far from typical_right.
    # Near-full-width last lines (>90% but <100%) that slip through
    # this check are caught later by _refine_alignments_from_context,
    # which upgrades ambiguous "left" blocks using neighbor alignment.
    last = line_extents[-1]
    last_is_short_final = (
        n >= 2  # noqa: PLR2004
        and (
            abs(last[0] - typical_left) <= align_tol
            or abs(last[0] - margin_left_ref) <= align_tol
        )
        and abs(last[1] - typical_right) > align_tol
        and (last[1] - last[0]) < (typical_right - typical_left) * _SHORT_LINE_RATIO
    )
    n_for_right = n - 1 if last_is_short_final else n
    is_right = lines_at_right > n_for_right / 2

    # Centered: significant margins on both sides, symmetric.
    left_margins = [lx0 - bx0 for lx0, _ in line_extents]
    right_margins = [bx1 - lx1 for _, lx1 in line_extents]
    avg_left = sum(left_margins) / len(left_margins)
    avg_right = sum(right_margins) / len(right_margins)
    min_margin = bw * 0.05
    is_centered = (
        avg_left > min_margin
        and avg_right > min_margin
        and abs(avg_left - avg_right) < bw * 0.15
    )

    # Detect first-line indent: first line shifted right of the left
    # margin.  Use the minimum left edge (not median) as the margin
    # reference since the indented first line inflates the median for
    # short blocks (2-3 lines).
    indent_pt = 0.0
    margin_left = sorted_lefts[0]
    first_shift = line_extents[0][0] - margin_left
    if (
        is_left
        and dom_size * _INDENT_FACTOR <= first_shift <= dom_size * _MAX_INDENT_FACTOR
    ):
        indent_pt = round(first_shift, 1)

    if is_left and is_right:
        # Both edges consistently aligned → justified text.  Takes priority
        # over centering heuristic because short paragraph-ending lines and
        # hanging indents can inflate average margins enough to trigger
        # is_centered even for clearly justified blocks.
        #
        # Exception: if the block also looks centered, check whether the
        # "justify" classification is driven by lines that span nearly the
        # full block width (>95%).  Such full-width lines are ambiguous —
        # they satisfy both left and right edge checks regardless of the
        # true alignment.  If the non-full-width lines are centered (i.e.
        # have roughly symmetric margins), prefer "center".
        if is_centered:
            _full_w_thresh = bw * 0.95
            narrow_lefts = [
                lm
                for lm, rm in zip(left_margins, right_margins, strict=False)
                if (bw - lm - rm) < _full_w_thresh
            ]
            narrow_rights = [
                rm
                for lm, rm in zip(left_margins, right_margins, strict=False)
                if (bw - lm - rm) < _full_w_thresh
            ]
            if narrow_lefts:
                avg_nl = sum(narrow_lefts) / len(narrow_lefts)
                avg_nr = sum(narrow_rights) / len(narrow_rights)
                if (
                    avg_nl > min_margin
                    and avg_nr > min_margin
                    and abs(avg_nl - avg_nr) < bw * 0.15
                ):
                    result = ("center", 0.0)
                else:
                    result = ("justify", indent_pt)
            else:
                # All lines are full-width — ambiguous, keep justify.
                result = ("justify", indent_pt)
        else:
            result = ("justify", indent_pt)
    elif is_centered:
        # If any line hugs the block's left edge but NOT the right
        # edge, the block is left-aligned — the margin symmetry is
        # caused by math or continuation lines with large offsets.
        # Full-width lines (both edges) are ambiguous and don't count.
        has_left_only_line = any(
            abs(ext[0] - bx0) <= align_tol and abs(ext[1] - bx1) > align_tol
            for ext in line_extents
        )
        if is_left and has_left_only_line:
            result = ("left", indent_pt)
        else:
            result = ("center", 0.0)
    elif is_right and not is_left:
        result = ("right", 0.0)
    else:
        result = ("left", indent_pt)

    return result


# Minimum number of ``justify`` body-text blocks required before
# contextual refinement upgrades ambiguous ``left`` blocks.
_CONTEXT_ALIGN_MIN_NEIGHBORS = 3

# Font-size ratio tolerance for contextual refinement.  Blocks whose
# dominant font size differs by more than this factor from the median
# are treated as headings / captions and excluded.
_CONTEXT_ALIGN_SIZE_TOL = 1.3


def _is_body_text_block(
    block: dict[str, Any],
    median_size: float,
) -> bool:
    """Return True if *block* is a multi-line body-text block.

    A block qualifies when it has ≥ 2 text lines and its font size is
    within ``_CONTEXT_ALIGN_SIZE_TOL`` of *median_size*.  Single-line
    blocks, headings, and captions are excluded.
    """
    if len(block.get("_line_extents", [])) < 2:  # noqa: PLR2004
        return False
    sz = block.get("font_size", 0.0)
    if sz <= 0 or median_size <= 0:
        return False
    ratio = max(sz, median_size) / min(sz, median_size)
    return ratio <= _CONTEXT_ALIGN_SIZE_TOL


def _refine_alignments_from_context(
    blocks: list[dict[str, Any]],
) -> None:
    """Upgrade ambiguous ``left`` alignments to ``justify`` using context.

    Per-block alignment detection is purely geometric; short or 2-line
    paragraphs can be ambiguous (left vs justify).  This function
    determines the *dominant body-text alignment* across all blocks on
    the page and upgrades ambiguous ``left`` blocks when ``justify``
    clearly dominates.

    Only multi-line blocks in the same font-size band qualify as body
    text — single-line blocks and different-sized headings / captions
    are excluded from both the vote and the upgrade.

    Modifies *blocks* in place (only upgrades, never downgrades).
    """
    # Collect font sizes of multi-line blocks to find the body-text
    # median.  Single-line blocks are excluded — their alignment is
    # inherently ambiguous and shouldn't define the dominant style.
    body_sizes = sorted(
        b.get("font_size", 0.0)
        for b in blocks
        if len(b.get("_line_extents", [])) >= 2  # noqa: PLR2004
        and b.get("font_size", 0.0) > 0
    )
    if not body_sizes:
        return
    median_size = body_sizes[len(body_sizes) // 2]

    # Count justify vs total among body-text blocks.
    justify_count = 0
    body_count = 0
    for b in blocks:
        if not _is_body_text_block(b, median_size):
            continue
        body_count += 1
        if b.get("text_align") == "justify":
            justify_count += 1

    # Justify must dominate: enough total AND majority.
    if justify_count < _CONTEXT_ALIGN_MIN_NEIGHBORS or justify_count <= body_count // 2:
        return

    # Upgrade all ambiguous "left" body-text blocks.
    for block in blocks:
        if block.get("text_align") == "left" and _is_body_text_block(
            block, median_size
        ):
            block["text_align"] = "justify"


def _build_cell_text(  # noqa: PLR0912, PLR0915
    spans: list[dict[str, Any]],
    *,
    base_bold: bool | None = None,
    base_italic: bool | None = None,
    cell_rect: tuple[float, ...] | list[float] | None = None,
) -> tuple[str, list[float]]:
    """Build cell text from spans, preserving line breaks.

    Groups spans by y-position into lines, joins same-line spans
    based on horizontal gap (space if gap > 1pt, else concatenate),
    then joins lines with newlines.

    When *base_bold* is not None, spans whose bold/italic differs
    from the base value are wrapped with ``<b>``/``<i>`` tags.

    Args:
        spans: List of PyMuPDF span dicts, sorted by (y, x).
        base_bold: If not None, enables tagged mode with this base bold.
        base_italic: Base italic value (used only when base_bold is set).
        cell_rect: Optional (x0, y0, x1, y1) cell rectangle.  When
            provided, cell width is computed from this rectangle
            rather than from text extents, preventing false space
            joins in sparse columns where all values have similar
            widths.

    Returns:
        Tuple of (reconstructed text, list of line y0 positions).
    """
    if not spans:
        return "", []

    tagged = base_bold is not None

    # Sort by y then x
    sorted_spans = sorted(spans, key=lambda s: (s["bbox"][1], s["bbox"][0]))

    # Group by y-position.  Two criteria for same-line:
    # 1. y-top within tolerance of the line's reference y-top, OR
    # 2. vertical overlap with the line (handles sub/superscript spans
    #    whose y-top is offset but still visually on the same line).
    lines: list[list[dict[str, Any]]] = []
    current_line = [sorted_spans[0]]
    cur_y0 = sorted_spans[0]["bbox"][1]
    cur_y1 = sorted_spans[0]["bbox"][3]
    for span in sorted_spans[1:]:
        sy0, sy1 = span["bbox"][1], span["bbox"][3]
        y_close = abs(sy0 - current_line[0]["bbox"][1]) < _LINE_Y_TOLERANCE
        v_overlap = sy0 < cur_y1 and sy1 > cur_y0
        if y_close or v_overlap:
            current_line.append(span)
            cur_y0 = min(cur_y0, sy0)
            cur_y1 = max(cur_y1, sy1)
        else:
            lines.append(current_line)
            current_line = [span]
            cur_y0, cur_y1 = sy0, sy1
    lines.append(current_line)

    # Build text per line, tracking y-positions and dominant font sizes.
    line_texts: list[str] = []
    line_y0s: list[float] = []
    line_dom_sizes: list[float] = []
    for line_spans in lines:
        line_spans.sort(key=lambda s: s["bbox"][0])
        # Compute line metrics for super/subscript classification.
        # Use max() — sup/sub spans are smaller by definition.
        line_sizes = [s.get("size", 12.0) for s in line_spans]
        line_dom_sz = max(line_sizes)
        line_dom_sizes.append(line_dom_sz)
        ly0 = min(s["bbox"][1] for s in line_spans)
        ly1 = max(s["bbox"][3] for s in line_spans)
        parts: list[str] = []
        for i, span in enumerate(line_spans):
            if i > 0:
                prev_end = line_spans[i - 1]["bbox"][2]
                curr_start = span["bbox"][0]
                if curr_start - prev_end > 1.0:
                    parts.append(" ")
            text = span.get("text", "")
            if tagged:
                role = _classify_sup_sub(
                    span.get("size", 12.0),
                    span["bbox"][1],
                    span["bbox"][3],
                    line_dom_sz,
                    ly0,
                    ly1,
                )
                text = _tag_span_text(
                    text,
                    span.get("flags", 0),
                    base_bold,
                    base_italic or False,
                    role=role,
                )
            parts.append(text)
        line_texts.append("".join(parts))
        line_y0s.append(ly0)

    # Decide per-line join: space (word wrap) vs newline (intentional break).
    # A line that doesn't fill the cell width ended intentionally → newline.
    # A line that fills most of the width just wrapped → space.
    # The threshold is dynamic: narrow cells (few chars per line) use a
    # lower ratio; wide cells use a higher one (see _cell_short_line_ratio).
    if len(lines) >= 2:  # noqa: PLR2004
        # Prefer the actual cell rectangle width over text extents.
        # Text extents can be misleadingly narrow in sparse columns
        # where all values have similar widths (e.g. 2-digit numbers),
        # making every line appear to "fill" the cell.
        if cell_rect is not None:
            cell_w = cell_rect[2] - cell_rect[0]
        else:
            cell_x0 = min(s["bbox"][0] for s in spans)
            cell_x1 = max(s["bbox"][2] for s in spans)
            cell_w = cell_x1 - cell_x0
        parts: list[str] = [line_texts[0]]
        for i in range(1, len(line_texts)):
            prev_line = lines[i - 1]
            prev_x1 = max(s["bbox"][2] for s in prev_line)
            prev_x0 = min(s["bbox"][0] for s in prev_line)
            prev_w = prev_x1 - prev_x0
            threshold = _cell_short_line_ratio(line_dom_sizes[i - 1], cell_w)
            # Previous line fills most of cell width → word wrap (space).
            if cell_w > 0 and prev_w >= cell_w * threshold:
                parts.append(" ")
            else:
                parts.append("\n")
            parts.append(line_texts[i])
        result = "".join(parts)
    else:
        result = line_texts[0] if line_texts else ""
    if tagged:
        result = _merge_adjacent_tags(result)
    return result, line_y0s


def _detect_column_alignment(
    col_spans: list[list[dict[str, Any]]],
) -> str:
    """Detect alignment for an entire table column.

    Compares consistency (variance) of left edges, right edges, and
    center points across all cells in the column.  The most consistent
    edge/center indicates the alignment.

    Args:
        col_spans: List of span lists, one per cell in the column.

    Returns:
        CSS text-align value: "left", "center", or "right".
    """
    cell_lefts: list[float] = []
    cell_rights: list[float] = []
    cell_centers: list[float] = []
    for spans in col_spans:
        if spans:
            left = min(s["bbox"][0] for s in spans)
            right = max(s["bbox"][2] for s in spans)
            cell_lefts.append(left)
            cell_rights.append(right)
            cell_centers.append((left + right) / 2)

    if len(cell_lefts) < 2:  # noqa: PLR2004
        return "left"

    def _variance(vals: list[float]) -> float:
        """Return the population variance of a list of floats."""
        mean = sum(vals) / len(vals)
        return sum((x - mean) ** 2 for x in vals) / len(vals)

    var_l = _variance(cell_lefts)
    var_r = _variance(cell_rights)
    var_c = _variance(cell_centers)

    # Center-aligned text has consistent center points but varying
    # left/right edges.  Detect center when center variance is
    # substantially lower than both edge variances.
    _edge_threshold = 0.5  # variance must differ by >0.5pt² to matter
    if var_c + _edge_threshold < var_l and var_c + _edge_threshold < var_r:
        return "center"
    if var_l + _edge_threshold < var_r:
        return "left"
    if var_r + _edge_threshold < var_l:
        return "right"
    # Near-equal variances (uniform-width text) — default to center
    return "center"


def _get_extracted_cell_bboxes(
    page_tables: list[dict[str, Any]],
    page_dict: dict[str, Any],
) -> list[tuple[float, ...]]:
    """Return bboxes of table cells that will be extracted (not skipped).

    Math-heavy cells (algorithm/theorem box bodies) are skipped by
    ``_extract_table_cell_blocks`` — their content goes through normal
    block extraction with full math-placeholder support.  This function
    pre-computes the list of cell bboxes that WILL be extracted so the
    main extraction loop can filter spans only in those cells, letting
    skipped cells' spans pass through to normal extraction.

    Cells with incidental math (footnote markers, isolated symbols) are
    NOT skipped — they are extracted as normal table cells.
    """
    bboxes: list[tuple[float, ...]] = []
    for table_info in page_tables:
        for cell in table_info["cells"]:
            spans = _get_spans_in_rect(page_dict, cell)
            if not spans:
                continue
            if _has_complex_math_layout(spans):
                continue  # Math-heavy — will be skipped
            bboxes.append(cell)
    return bboxes


def _extract_table_cell_blocks(  # noqa: PLR0912
    page_tables: list[dict[str, Any]],
    page_dict: dict[str, Any],
) -> list[dict[str, Any]]:
    """Create per-cell blocks from detected tables.

    For each cell in each table, finds matching spans, extracts text
    and font properties, detects alignment, and creates a block dict
    compatible with ``_apply_translated_blocks``.

    Args:
        page_tables: List of table info dicts from ``_find_page_tables``.
        page_dict: Result of ``page.get_text("dict")``.

    Returns:
        List of block dicts with keys: rect, text, font_size, font_name,
        color, bold, italic, text_align, is_table_cell.
    """
    cell_blocks: list[dict[str, Any]] = []
    for table_info in page_tables:
        # First pass: collect spans per cell and group by column
        # for column-level alignment detection.
        col_spans: dict[int, list[list[dict[str, Any]]]] = {}
        cell_span_map: list[tuple[tuple[float, ...], list[dict[str, Any]], int]] = []
        for cell in table_info["cells"]:
            raw_spans = _get_spans_in_rect(page_dict, cell)
            if not raw_spans:
                continue
            col_key = round(cell[0])
            col_spans.setdefault(col_key, []).append(raw_spans)
            cell_span_map.append((cell, raw_spans, col_key))

        # Detect alignment at the column level (consistent across rows)
        col_alignments: dict[int, str] = {}
        for col_key, span_lists in col_spans.items():
            col_alignments[col_key] = _detect_column_alignment(span_lists)

        # Second pass: build cell blocks with column-level alignment
        for cell, spans, col_key in cell_span_map:
            # Skip math-heavy cells (e.g. algorithm box bodies where
            # >50% of characters come from math fonts).  Their 2D
            # math layout cannot be linearised as cell text; content
            # goes through normal block extraction with full
            # math-placeholder support instead.  Cells with incidental
            # math (footnote markers †/‡, isolated ∼) are kept.
            if _has_complex_math_layout(spans):
                continue

            # Dominant font properties
            all_fonts = [s.get("font", "") for s in spans]
            all_sizes = [s.get("size", 12.0) for s in spans]
            all_flags = [s.get("flags", 0) for s in spans]
            all_colors = [s.get("color", 0) for s in spans]

            dominant_size = _most_common(all_sizes, 12.0)
            dominant_flags = _most_common(all_flags, 0)
            dominant_color = _most_common(all_colors, 0)
            is_bold = bool(dominant_flags & 16)
            is_italic = bool(dominant_flags & 2)

            # Check for mixed bold/italic/super/subscript within the cell
            mixed = _has_mixed_formatting(all_flags)
            if (
                not mixed
                and len(all_sizes) >= 2  # noqa: PLR2004
                and dominant_size > 0
                and min(all_sizes) < dominant_size * _SUP_SUB_SIZE_RATIO
            ):
                mixed = True
            if mixed:
                full_text, line_y0s = _build_cell_text(
                    spans,
                    base_bold=is_bold,
                    base_italic=is_italic,
                    cell_rect=cell,
                )
            else:
                full_text, line_y0s = _build_cell_text(
                    spans,
                    cell_rect=cell,
                )
            if not full_text.strip():
                continue

            # Track actual span extent — text can overflow the cell
            # boundary (e.g. "Self-Attention (restricted)" extends past
            # its column).  The overflow must be redacted to prevent
            # stray original text from showing through.
            span_x0 = min(s["bbox"][0] for s in spans)
            span_x1 = max(s["bbox"][2] for s in spans)
            cell_entry: dict[str, Any] = {
                "rect": list(cell),
                "text": full_text,
                "font_size": dominant_size,
                "font_name": _most_common(all_fonts, ""),
                "color": dominant_color,
                "bold": is_bold,
                "italic": is_italic,
                "font_flags": dominant_flags,
                "text_align": col_alignments.get(col_key, "left"),
                "is_table_cell": True,
            }
            if span_x0 < cell[0] - 1.0:
                cell_entry["_redact_x0"] = span_x0
            if span_x1 > cell[2] + 1.0:
                cell_entry["_redact_x1"] = span_x1
            if mixed:
                cell_entry["has_mixed_formatting"] = True
            # Store original line y-positions so the overlay can
            # replicate vertical spacing (important when one column
            # has sparse text that must align with a dense column).
            if len(line_y0s) > 1:
                cell_entry["cell_line_y0s"] = line_y0s
            cell_blocks.append(cell_entry)
    return cell_blocks


# ── Vertical-line table detection ──────────────────────────────────────


def _find_vertical_lines(
    page: Any,  # noqa: ANN401
    drawings: list[dict[str, Any]] | None = None,
) -> list[dict[str, float]]:
    """Find tall vertical lines drawn on a page.

    Scans all vector drawings for line items that are vertical
    (Δx < 1pt) and taller than ``_MIN_VLINE_HEIGHT``.

    Args:
        page: A PyMuPDF Page object.
        drawings: Optional pre-computed ``page.get_drawings()`` result.

    Returns:
        List of dicts with keys 'x', 'y0', 'y1'.
    """
    v_lines: list[dict[str, float]] = []
    try:
        for drawing in drawings if drawings is not None else page.get_drawings():
            for item in drawing.get("items", []):
                if item[0] != "l":
                    continue
                p1, p2 = item[1], item[2]
                if abs(p1.x - p2.x) < 1.0 and abs(p1.y - p2.y) > _MIN_VLINE_HEIGHT:
                    v_lines.append(
                        {
                            "x": (p1.x + p2.x) / 2,
                            "y0": min(p1.y, p2.y),
                            "y1": max(p1.y, p2.y),
                        }
                    )
    except Exception:
        logger.debug("get_drawings failed for vlines", exc_info=True)
    return v_lines


def _group_vlines_by_yrange(
    v_lines: list[dict[str, float]],
) -> list[list[dict[str, float]]]:
    """Group vertical lines that share the same y-range.

    Two lines are considered part of the same group when their top and
    bottom endpoints are both within ``_VLINE_YRANGE_TOLERANCE`` of the
    group's first line.

    Returns:
        List of groups, each a list of line dicts.
    """
    groups: list[list[dict[str, float]]] = []
    for line in v_lines:
        placed = False
        for group in groups:
            ref = group[0]
            if (
                abs(line["y0"] - ref["y0"]) < _VLINE_YRANGE_TOLERANCE
                and abs(line["y1"] - ref["y1"]) < _VLINE_YRANGE_TOLERANCE
            ):
                group.append(line)
                placed = True
                break
        if not placed:
            groups.append([line])
    return groups


def _detect_vline_tables(
    page: Any,  # noqa: ANN401
    page_dict: dict[str, Any],
    drawings: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Detect tables defined by vertical column separators only.

    Some tables use vertical lines between columns but no horizontal
    rules.  This function identifies them from drawn vertical lines,
    uses their x-positions as column dividers, and infers row boundaries
    from text span y-positions.

    Args:
        page: A PyMuPDF Page object.
        page_dict: Result of ``page.get_text("dict")``.
        drawings: Pre-fetched drawing items, or None to fetch.

    Returns:
        Same format as ``_find_page_tables``: list of dicts with 'bbox'
        and 'cells'.
    """
    v_lines = _find_vertical_lines(page, drawings=drawings)
    if len(v_lines) < _MIN_VLINES_PER_TABLE:
        return []

    groups = _group_vlines_by_yrange(v_lines)
    table_groups = [g for g in groups if len(g) >= _MIN_VLINES_PER_TABLE]
    if not table_groups:
        return []

    results: list[dict[str, Any]] = []

    for group in table_groups:
        group.sort(key=lambda line: line["x"])
        y0 = min(line["y0"] for line in group)
        y1 = max(line["y1"] for line in group)
        x0 = group[0]["x"]
        x1 = group[-1]["x"]
        bbox = (x0, y0, x1, y1)

        # Column dividers come directly from the vertical line x-positions
        col_dividers = sorted({line["x"] for line in group})
        if len(col_dividers) < _MIN_VLINES_PER_TABLE:
            continue

        # Find text spans within the table region
        spans = _get_spans_in_rect(page_dict, bbox)
        if not spans:
            continue

        text_rows = _group_spans_into_rows(spans)
        if not text_rows:
            continue

        # Row boundaries from text row y-positions
        row_bounds: list[float] = [y0]
        for i in range(len(text_rows) - 1):
            bot_y = max(s["bbox"][3] for s in text_rows[i])
            top_y = min(s["bbox"][1] for s in text_rows[i + 1])
            row_bounds.append((bot_y + top_y) / 2)
        row_bounds.append(y1)

        # Build cells
        cells: list[tuple[float, ...]] = []
        for r in range(len(row_bounds) - 1):
            for c in range(len(col_dividers) - 1):
                cells.append(
                    (
                        col_dividers[c],
                        row_bounds[r],
                        col_dividers[c + 1],
                        row_bounds[r + 1],
                    )
                )

        results.append({"bbox": bbox, "cells": cells})

    return results


# ── Framed (outer-border) table detection ──────────────────────────────


def _detect_framed_tables(  # noqa: PLR0912
    page: Any,  # noqa: ANN401
    page_dict: dict[str, Any],
    drawings: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Detect tables enclosed in a rectangular frame (outer borders only).

    Some tables have only an outer rectangle with no internal grid lines.
    This function finds rectangle drawing items, verifies that the content
    inside has a consistent columnar structure, and if so creates per-cell
    blocks.

    To avoid false positives on boxed paragraphs and callout boxes, the
    content must have at least ``_MIN_TABULAR_ROWS`` text rows matching
    the inferred column count.

    Args:
        page: A PyMuPDF Page object.
        page_dict: Result of ``page.get_text("dict")``.
        drawings: Pre-fetched drawing items, or None to fetch.

    Returns:
        Same format as ``_find_page_tables``: list of dicts with 'bbox'
        and 'cells'.
    """
    frames: list[tuple[float, float, float, float]] = []
    try:
        for drawing in drawings if drawings is not None else page.get_drawings():
            for item in drawing.get("items", []):
                if item[0] == "re":
                    rect = item[1]
                    if (
                        rect.width >= _MIN_FRAME_WIDTH
                        and rect.height >= _MIN_FRAME_HEIGHT
                    ):
                        frames.append((rect.x0, rect.y0, rect.x1, rect.y1))
    except Exception:
        logger.debug("get_drawings failed for frames", exc_info=True)

    if not frames:
        return []

    results: list[dict[str, Any]] = []

    for frame in frames:
        spans = _get_spans_in_rect(page_dict, frame)
        if not spans:
            continue

        text_rows = _group_spans_into_rows(spans)
        col_count, col_dividers = _infer_columns(text_rows, frame)
        if col_count < _MIN_RULED_COLUMNS:
            continue

        # Verify tabular structure: enough rows must match the column count
        matching = sum(1 for r in text_rows if len(r) == col_count)
        if matching < _MIN_TABULAR_ROWS:
            continue

        # Row boundaries from text row y-positions
        _, y0, _, y1 = frame
        row_bounds: list[float] = [y0]
        for i in range(len(text_rows) - 1):
            bot_y = max(s["bbox"][3] for s in text_rows[i])
            top_y = min(s["bbox"][1] for s in text_rows[i + 1])
            row_bounds.append((bot_y + top_y) / 2)
        row_bounds.append(y1)

        cells: list[tuple[float, ...]] = []
        for r in range(len(row_bounds) - 1):
            for c in range(len(col_dividers) - 1):
                cells.append(
                    (
                        col_dividers[c],
                        row_bounds[r],
                        col_dividers[c + 1],
                        row_bounds[r + 1],
                    )
                )

        results.append({"bbox": frame, "cells": cells})

    return results


# ── Page classification ───────────────────────────────────────────────


def _page_has_images(page: Any) -> bool:  # noqa: ANN401
    """Returns True if the page contains at least one raster image.

    Used to distinguish truly scanned pages (raster-only, worth OCR)
    from vector-only pages (diagrams, charts) that should be left alone.

    Args:
        page: A PyMuPDF Page object.
    """
    try:
        return len(page.get_images(full=False)) > 0
    except Exception:
        return False


# ── Text overlay ──────────────────────────────────────────────────────


def _join_textbox_lines(text: str) -> str:
    r"""Join multi-line ``get_textbox()`` output into a single search string.

    * **Hyphen break** — ``"Mod-\\nels"`` → ``"Models"`` (dehyphenate).
    * **Normal break** — ``"Hello\\nWorld"`` → ``"Hello World"`` (space).

    Args:
        text: Raw text from ``page.get_textbox()``.

    Returns:
        Single-line string suitable for ``search_for()``.
    """
    if "\n" not in text:
        return text.strip()
    lines = text.splitlines()
    result = lines[0].strip()
    for line in lines[1:]:
        seg = line.strip()
        if not seg:
            continue
        result = result[:-1] + seg if result.endswith("-") else result + " " + seg
    return result


# Maximum y-center gap (points) for grouping characters on the same
# visual line when extracting or restoring link inner-text.  Used by
# both ``_save_page_links`` and ``_find_link_in_chars``.
_LINK_LINE_Y_GAP = 3.0


def _save_page_links(page: Any) -> list[dict[str, Any]]:  # noqa: ANN401, PLR0912, PLR0915
    """Save all links on a page for later restoration.

    Preserves ``LINK_NAMED`` (kind 4) links with their ``nameddest``
    field so the PDF viewer resolves them at display time.  Named
    destinations survive page redaction (they live in the document
    name tree, not the page content stream).

    Extracts visible text under each link rect as ``_inner`` via
    character-level majority overlap (>50% of char width AND
    y-intersection).  When chars span multiple lines, only the line
    closest to the link rect center is kept to prevent contamination
    from adjacent body text.

    Args:
        page: A PyMuPDF Page object.

    Returns:
        List of cleaned link dicts suitable for ``insert_link()``.
    """
    saved: list[dict[str, Any]] = []
    try:
        # Pre-fetch character-level data for precise inner-text extraction
        raw_dict = page.get_text("rawdict")
        all_chars: list[tuple[str, tuple[float, float, float, float]]] = [
            (ch["c"], ch["bbox"])
            for blk in raw_dict.get("blocks", [])
            if blk.get("type") == 0
            for line in blk.get("lines", [])
            for span in line.get("spans", [])
            for ch in span.get("chars", [])
        ]
        for link in page.get_links():
            entry: dict[str, Any] = {"kind": link["kind"], "from": link["from"]}
            if link.get("uri"):
                entry["uri"] = link["uri"]
            if "page" in link and link["page"] >= 0:
                entry["page"] = link["page"]
            if "to" in link:
                entry["to"] = link["to"]
            if "zoom" in link:
                entry["zoom"] = link["zoom"]
            if link.get("nameddest"):
                entry["nameddest"] = link["nameddest"]
            # Extract visible text under the link rect via char-level
            # majority overlap (>50% width AND vertical intersection).
            link_rect = pymupdf.Rect(entry["from"])
            char_items: list[tuple[str, float]] = []
            matched_indices: list[int] = []
            for ac_idx, (ch_c, ch_bbox) in enumerate(all_chars):
                cr = pymupdf.Rect(ch_bbox)
                if not cr.intersects(link_rect):
                    continue
                overlap_w = max(
                    0,
                    min(cr.x1, link_rect.x1) - max(cr.x0, link_rect.x0),
                )
                char_w = cr.width or 1
                if overlap_w / char_w > 0.5:  # noqa: PLR2004
                    cy = (cr.y0 + cr.y1) / 2
                    char_items.append((ch_c, cy))
                    matched_indices.append(ac_idx)
            # When chars span multiple lines, keep only the line
            # whose vertical center is closest to the link rect
            # center.  This prevents body text on adjacent lines
            # from contaminating the inner text (e.g. "la" from
            # "scalar" bleeding into a footnote-4 link).
            if char_items:
                link_cy = (link_rect.y0 + link_rect.y1) / 2
                # Group by line: chars within 3pt y-gap
                lines: list[list[tuple[str, float]]] = [
                    [char_items[0]],
                ]
                for ci in char_items[1:]:
                    if abs(ci[1] - lines[-1][-1][1]) < _LINK_LINE_Y_GAP:
                        lines[-1].append(ci)
                    else:
                        lines.append([ci])
                if len(lines) > 1:
                    best = min(
                        lines,
                        key=lambda ln: abs(
                            sum(t[1] for t in ln) / len(ln) - link_cy,
                        ),
                    )
                    char_items = best
            inner = "".join(c for c, _ in char_items).strip()
            if inner:
                entry["_inner"] = inner
                # Store neighboring chars for disambiguation.
                # The char immediately before/after the link's
                # characters in the page stream lets downstream
                # matching pick the correct occurrence when _inner
                # is short and ambiguous (e.g. "2" in "2.0" vs
                # "Table 2)").
                if matched_indices:
                    first_idx = matched_indices[0]
                    last_idx = matched_indices[-1]
                    if first_idx > 0:
                        entry["_src_left"] = all_chars[first_idx - 1][0]
                    if last_idx + 1 < len(all_chars):
                        entry["_src_right"] = all_chars[last_idx + 1][0]
            # Preserve link visual style (border color, border width)
            # get_links() omits these — read from xref directly
            xref = link.get("xref", 0)
            if xref:
                style: dict[str, str] = {}
                doc = page.parent
                for key in ("C", "Border", "BS"):
                    kind, val = doc.xref_get_key(xref, key)
                    if kind != "null":
                        style[key] = val
                if style:
                    entry["_style"] = style
            logger.debug(
                "link[orig] inner=%r rect=%s uri=%r",
                entry.get("_inner", ""),
                entry["from"],
                entry.get("uri", ""),
            )
            saved.append(entry)
    except Exception:
        logger.debug("Failed to save page links", exc_info=True)

    return saved


def _links_to_checkpoint(saved_links: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert saved link dicts to JSON-serializable checkpoint entries.

    PyMuPDF ``Rect`` / ``Point`` objects are converted to plain lists.
    Each entry is tagged with ``"type": "link"`` for checkpoint
    discrimination.

    Args:
        saved_links: Link dicts from ``_save_page_links()`` enriched
            with ``_translated``, ``_block_idx``, etc.

    Returns:
        List of JSON-safe dicts.
    """
    result: list[dict[str, Any]] = []
    for sl in saved_links:
        entry: dict[str, Any] = {"type": "link"}
        for key, val in sl.items():
            if key in ("from", "to") and not isinstance(val, (list, str)):
                entry[key] = list(val)
            else:
                entry[key] = val
        result.append(entry)
    return result


# Regex matching any HTML tag (opening or closing).
_ANY_TAG_RE = re.compile(r"<[^>]+>")


def _map_stripped_pos(text: str, stripped_pos: int) -> int:
    """Map a character position in tag-stripped text to the original.

    Walks *text* counting only non-tag characters.  Returns the index
    in the original string corresponding to *stripped_pos* characters
    of visible content.  Any tags immediately following the landing
    position are skipped so the result points past closing tags like
    ``</sup>`` rather than into the middle of one.

    Args:
        text: Original text potentially containing HTML tags.
        stripped_pos: Character offset in the tag-free version.

    Returns:
        Corresponding index in *text*.
    """
    count = 0
    i = 0
    while i < len(text) and count < stripped_pos:
        if text[i] == "<":
            end = text.find(">", i)
            i = end + 1 if end != -1 else i + 1
        else:
            count += 1
            i += 1
    # Skip any tags at the landing position so the result sits on
    # the next visible character (or end of string), not mid-tag.
    while i < len(text) and text[i] == "<":
        end = text.find(">", i)
        i = end + 1 if end != -1 else i + 1
    return i


def _inject_link_tags(  # noqa: PLR0912
    blocks: list[dict[str, Any]],
    saved_links: list[dict[str, Any]],
    pymupdf: Any,  # noqa: ANN401
) -> None:
    """Wrap link text inside block text with ``<a id="N">`` tags.

    Links are grouped by intersecting block and sorted in reading
    order (top-to-bottom, left-to-right) within each block.  A shared
    ``search_start`` is advanced after each successful injection so
    that short/ambiguous ``_inner`` strings match sequentially.

    Searches in the **tag-stripped** version of the block text so that
    inline formatting tags (``<sup>``, ``<b>``, etc.) do not prevent
    matching.  Positions are mapped back to the original tagged text
    and trailing closing tags are included for valid HTML nesting.

    Args:
        blocks: Block dicts with ``text`` and ``rect`` keys.
        saved_links: Link dicts from ``_save_page_links()``.
        pymupdf: The pymupdf module reference.
    """
    # Group links by intersecting block for sequential processing.
    block_groups: dict[int, list[tuple[int, dict[str, Any]]]] = {}
    for link_id, sl in enumerate(saved_links):
        if not sl.get("_inner"):
            continue
        link_rect = pymupdf.Rect(sl["from"])
        for block_idx, block in enumerate(blocks):
            if link_rect.intersects(pymupdf.Rect(block["rect"])):
                block_groups.setdefault(block_idx, []).append(
                    (link_id, sl),
                )
                break

    # Process each block's links in reading order (y then x).
    for block_idx, group in block_groups.items():
        group.sort(
            key=lambda item: (
                pymupdf.Rect(item[1]["from"]).y0,
                pymupdf.Rect(item[1]["from"]).x0,
            ),
        )
        block = blocks[block_idx]
        search_start = 0
        for link_id, sl in group:
            inner = sl["_inner"]
            src_left = sl.get("_src_left")
            src_right = sl.get("_src_right")
            text = block["text"]
            stripped = _ANY_TAG_RE.sub("", text)
            injected = False
            # Two-pass: prefer context-char match, fall back to raw.
            # Context chars (_src_left / _src_right) are the page
            # characters immediately adjacent to the link text in the
            # original PDF, stored by _save_page_links.
            has_ctx = src_left is not None or src_right is not None
            for require_ctx in (True, False):
                if injected:
                    break
                if require_ctx and not has_ctx:
                    continue
                local_start = search_start
                while not injected:
                    pos = stripped.find(inner, local_start)
                    if pos == -1:
                        break
                    if require_ctx:
                        end = pos + len(inner)
                        left_ok = src_left is None or (
                            pos > 0 and stripped[pos - 1] == src_left
                        )
                        right_ok = src_right is None or (
                            end < len(stripped) and stripped[end] == src_right
                        )
                        if not (left_ok and right_ok):
                            local_start = pos + 1
                            continue
                    orig_start = _map_stripped_pos(text, pos)
                    orig_end = _map_stripped_pos(
                        text,
                        pos + len(inner),
                    )
                    before = text[:orig_start]
                    if before.count("<a ") > before.count("</a>"):
                        local_start = pos + 1
                        continue
                    block["text"] = (
                        text[:orig_start]
                        + f'<a id="{link_id}">'
                        + text[orig_start:orig_end]
                        + "</a>"
                        + text[orig_end:]
                    )
                    injected = True
                    search_start = pos + len(inner)
            if injected:
                sl["_block_idx"] = block_idx


# Regex to parse <a id="N">...</a> tags from translated text.
_LINK_TAG_RE = re.compile(r'<a\s+id="(\d+)">(.*?)</a>')


def _extract_link_translations(
    blocks: list[dict[str, Any]],
    saved_links: list[dict[str, Any]],
) -> None:
    """Extract translated link text from ``<a>`` tags and strip them.

    After LLM translation, ``<a id="N">translated</a>`` tags in
    ``translated_text`` are parsed.  The translated content is stored
    as ``_translated`` on the corresponding saved link so that
    ``_restore_page_links`` can search for the translated text on the
    overlay page.  Then all ``<a>`` tags are removed for clean overlay.

    Args:
        blocks: Block dicts with ``translated_text`` keys.
        saved_links: Link dicts to receive ``_translated``.
    """
    for block in blocks:
        translated = block.get("translated_text", "")
        if "<a " not in translated:
            continue
        # Plain text with <a> content inlined (for context-char lookup)
        plain = _ANY_TAG_RE.sub("", _LINK_TAG_RE.sub(r"\2", translated))
        for match in _LINK_TAG_RE.finditer(translated):
            link_id = int(match.group(1))
            if link_id >= len(saved_links):
                continue
            # Strip inner HTML tags (e.g. <sup>) so _translated
            # is plain text suitable for page.search_for().
            plain_tr = _ANY_TAG_RE.sub("", match.group(2))
            saved_links[link_id]["_translated"] = plain_tr
            # Store neighbouring chars from translated text so
            # _find_link_in_chars can verify the correct match
            # in the rendered block characters.
            before_plain = _ANY_TAG_RE.sub(
                "",
                _LINK_TAG_RE.sub(r"\2", translated[: match.start()]),
            )
            pos = len(before_plain)
            end = pos + len(plain_tr)
            if pos > 0:
                saved_links[link_id]["_left_char"] = plain[pos - 1]
            if end < len(plain):
                saved_links[link_id]["_right_char"] = plain[end]
        # Strip <a> tags for clean overlay
        block["translated_text"] = _LINK_TAG_RE.sub(r"\2", translated)


def _get_block_chars(
    all_chars: list[tuple[str, Any]],
    block_rect: Any,  # noqa: ANN401
) -> list[tuple[str, Any]]:
    """Return characters whose center falls within a block rect.

    Args:
        all_chars: List of (char, pymupdf.Rect) tuples for the page.
        block_rect: pymupdf.Rect for the block area.

    Returns:
        Filtered list of (char, rect) tuples in reading order.
    """
    result: list[tuple[str, Any]] = []
    for ch_c, ch_r in all_chars:
        cx = (ch_r.x0 + ch_r.x1) / 2
        cy = (ch_r.y0 + ch_r.y1) / 2
        in_x = block_rect.x0 <= cx <= block_rect.x1
        in_y = block_rect.y0 <= cy <= block_rect.y1
        if in_x and in_y:
            result.append((ch_c, ch_r))
    return result


# Ligature → expanded-ASCII mapping for text matching.
_LIGATURE_MAP: dict[str, str] = {
    "\ufb00": "ff",
    "\ufb01": "fi",
    "\ufb02": "fl",
    "\ufb03": "ffi",
    "\ufb04": "ffl",
}


def _expand_ligatures(
    text: str,
) -> tuple[str, list[int]]:
    """Expand Unicode ligatures to ASCII equivalents.

    Returns the expanded text and a position map: ``pos_map[i]``
    is the index in the *original* ``text`` that expanded char ``i``
    came from.  Ligatures expand to multiple chars sharing the same
    original index.
    """
    expanded: list[str] = []
    pos_map: list[int] = []
    for orig_idx, ch in enumerate(text):
        replacement = _LIGATURE_MAP.get(ch)
        if replacement:
            for rc in replacement:
                expanded.append(rc)
                pos_map.append(orig_idx)
        else:
            expanded.append(ch)
            pos_map.append(orig_idx)
    return "".join(expanded), pos_map


def _find_link_in_chars(  # noqa: PLR0912, PLR0915
    block_chars: list[tuple[str, Any]],
    block_text: str,
    link: dict[str, Any],
    search_pos: int,
) -> tuple[list[Any], int]:
    """Find a link's rects in block characters by text search.

    Searches sequentially from ``search_pos`` for ``_translated``
    (preferred) then ``_inner`` (fallback).  Context-char matching
    (``_left_char`` / ``_right_char``) is tried first to pick the
    correct occurrence; raw substring is used as a last resort.

    Handles Unicode ligatures (e.g. ``ﬂ`` → ``fl``) that PyMuPDF
    may produce after ``insert_htmlbox`` rendering.

    When the matched text spans multiple visual lines, a separate rect
    is returned for each line so that link borders follow the text
    instead of creating a single oversized rectangle.

    Args:
        block_chars: Characters within the block as (char, rect) tuples.
        block_text: Concatenated text from block_chars.
        link: Saved link dict.
        search_pos: Start position for sequential search.

    Returns:
        (link_rects, next_search_pos) where link_rects is a list of
        per-line Rect objects (empty list if not found).
    """
    # Expand ligatures for matching; pos_map maps expanded → original
    exp_text, pos_map = _expand_ligatures(block_text)

    matched_start_exp = -1
    matched_end_exp = -1

    # Map search_pos from original to expanded coordinates
    exp_search_pos = 0
    if search_pos > 0 and pos_map:
        for ei, oi in enumerate(pos_map):
            if oi >= search_pos:
                exp_search_pos = ei
                break
        else:
            exp_search_pos = len(exp_text)

    # Context chars stored by _extract_link_translations
    left_char = link.get("_left_char")
    right_char = link.get("_right_char")
    has_ctx = left_char is not None or right_char is not None

    # Try _translated first, then _inner as fallback
    translated = link.get("_translated", "")
    for candidate in (translated, link.get("_inner", "")):
        if not candidate:
            continue
        # Two-pass: context-char match first, then raw substring
        for require_ctx in (True, False):
            if matched_start_exp >= 0:
                break
            if require_ctx and not has_ctx:
                continue
            idx = exp_search_pos
            while idx < len(exp_text):
                idx = exp_text.find(candidate, idx)
                if idx < 0:
                    break
                if require_ctx:
                    end = idx + len(candidate)
                    l_ok = left_char is None or (
                        idx > 0 and exp_text[idx - 1] == left_char
                    )
                    r_ok = right_char is None or (
                        end < len(exp_text) and exp_text[end] == right_char
                    )
                    if not (l_ok and r_ok):
                        idx += 1
                        continue
                matched_start_exp = idx
                matched_end_exp = idx + len(candidate)
                break
        if matched_start_exp >= 0:
            break

    if matched_start_exp < 0:
        return [], search_pos

    s_exp, e_exp = matched_start_exp, matched_end_exp

    # Map expanded positions back to original char indices
    start = pos_map[s_exp]
    end = pos_map[e_exp - 1] + 1
    end_orig = end

    if end > len(block_chars):
        return [], search_pos

    matched = block_chars[start:end]
    if not matched:
        return [], search_pos

    # Group matched chars into visual lines by y-center proximity.
    # This prevents a single oversized rect when link text wraps
    # across multiple lines (e.g. long URLs).
    line_groups: list[list[tuple[str, Any]]] = [[matched[0]]]
    for ch_c, ch_r in matched[1:]:
        cy = (ch_r.y0 + ch_r.y1) / 2
        prev_cy = (line_groups[-1][-1][1].y0 + line_groups[-1][-1][1].y1) / 2
        if abs(cy - prev_cy) < _LINK_LINE_Y_GAP:
            line_groups[-1].append((ch_c, ch_r))
        else:
            line_groups.append([(ch_c, ch_r)])

    # Build per-line rects, preserving original link height
    orig_rect = link.get("from")
    orig_h = pymupdf.Rect(orig_rect).height if orig_rect else None
    rects: list[Any] = []
    for line_chars in line_groups:
        lx0 = min(r.x0 for _, r in line_chars)
        ly0 = min(r.y0 for _, r in line_chars)
        lx1 = max(r.x1 for _, r in line_chars)
        ly1 = max(r.y1 for _, r in line_chars)
        if orig_h is not None:
            char_h = ly1 - ly0
            if orig_h < char_h:
                cy = (ly0 + ly1) / 2
                ly0 = cy - orig_h / 2
                ly1 = cy + orig_h / 2
        rects.append(pymupdf.Rect(lx0, ly0, lx1, ly1))

    return rects, end_orig


def _insert_link_with_style(
    page: Any,  # noqa: ANN401
    link: dict[str, Any],
    link_rect: Any | None,  # noqa: ANN401
) -> None:
    """Insert a link annotation and restore its visual style.

    Args:
        page: A PyMuPDF Page object.
        link: Saved link dict with optional ``_style``.
        link_rect: New rect for the link, or ``None`` to use original.
    """
    doc = page.parent
    link_entry = {
        k: v for k, v in link.items() if not k.startswith("_") and k != "type"
    }
    # Ensure 'from' is a Rect (checkpoint stores plain lists)
    if "from" in link_entry and not isinstance(link_entry["from"], pymupdf.Rect):
        link_entry["from"] = pymupdf.Rect(link_entry["from"])
    if link_rect is not None:
        link_entry["from"] = link_rect
    # Ensure 'to' is a Point (checkpoint stores plain lists)
    if "to" in link_entry and not isinstance(link_entry["to"], pymupdf.Point):
        link_entry["to"] = pymupdf.Point(link_entry["to"])
    page.insert_link(link_entry)
    # Restore visual style (border color/width) via xref.
    # insert_link() always creates BS <</W 0>> which suppresses
    # borders.  When the original had Border but no BS, remove
    # the injected BS so the Border array takes effect.
    saved_style = link.get("_style")
    if saved_style and doc:
        xrefs = page.annot_xrefs()
        if xrefs:
            new_xref = xrefs[-1][0]
            for key, val in saved_style.items():
                doc.xref_set_key(new_xref, key, val)
                logger.debug(
                    "link border set: xref=%d %s=%s",
                    new_xref,
                    key,
                    val,
                )
            if "Border" in saved_style and "BS" not in saved_style:
                doc.xref_set_key(new_xref, "BS", "null")
                logger.debug(
                    "link border: removed injected BS for xref=%d (Border-only style)",
                    new_xref,
                )
        else:
            logger.debug(
                "link border: no annot xrefs found after insert_link for uri=%r",
                link.get("uri", ""),
            )
    elif not saved_style:
        logger.debug(
            "link border: no _style saved for uri=%r rect=%s",
            link.get("uri", ""),
            link_rect or link.get("from"),
        )


def _restore_page_links(  # noqa: PLR0912, PLR0915
    page: Any,  # noqa: ANN401
    saved_links: list[dict[str, Any]],
    redact_rects: list[Any] | None = None,
    blocks: list[dict[str, Any]] | None = None,
) -> None:
    """Re-insert previously saved links onto a page.

    Uses **character-level position mapping** when block information
    is available (``_block_idx`` set by ``_inject_link_tags``):

    1. Extracts all character bounding boxes from the rendered page.
    2. For each block, collects characters within its rect.
    3. Finds each link's text sequentially in the block's character
       stream, ensuring correct disambiguation by reading order.
    4. Computes the link rect from matched character bounding boxes.

    Falls back to ``search_for`` for links without ``_block_idx``.

    Args:
        page: A PyMuPDF Page object.
        saved_links: Link dicts from ``_save_page_links()``.
        redact_rects: Rects that were redacted (used for position
            remapping).
        blocks: Block dicts with ``rect`` / ``render_rect`` keys.
    """
    # Build page-wide character data for char-level matching
    all_chars: list[tuple[str, Any]] | None = None
    if blocks:
        try:
            raw = page.get_text("rawdict")
            all_chars = [
                (ch["c"], pymupdf.Rect(ch["bbox"]))
                for blk in raw.get("blocks", [])
                if blk.get("type") == 0
                for line in blk.get("lines", [])
                for span in line.get("spans", [])
                for ch in span.get("chars", [])
            ]
        except Exception:
            logger.debug("Failed to get char data", exc_info=True)

    # Group links by block index for sequential char-level matching
    block_link_groups: dict[int, list[dict[str, Any]]] = {}
    unassigned: list[dict[str, Any]] = []
    for link in saved_links:
        bidx = link.get("_block_idx")
        if bidx is not None and all_chars is not None and blocks:
            block_link_groups.setdefault(bidx, []).append(link)
        else:
            unassigned.append(link)

    # Char-level matching: process each block's links sequentially
    for bidx, group_links in block_link_groups.items():
        if bidx >= len(blocks):
            unassigned.extend(group_links)
            continue
        block = blocks[bidx]
        block_rect = pymupdf.Rect(
            block.get("render_rect", block["rect"]),
        )
        block_chars = _get_block_chars(all_chars, block_rect)
        block_text = "".join(c for c, _ in block_chars)

        search_pos = 0
        for link in group_links:
            try:
                link_rects, search_pos = _find_link_in_chars(
                    block_chars,
                    block_text,
                    link,
                    search_pos,
                )
                # Insert one annotation per visual line so multi-line
                # links (e.g. wrapped URLs) get per-line borders.
                if link_rects:
                    for lr in link_rects:
                        _insert_link_with_style(page, link, lr)
                    logger.debug(
                        "link[translated] text=%r rects=%s "
                        "(found via block_chars at pos=%d)",
                        link.get("_translated") or link.get("_inner"),
                        [str(r) for r in link_rects],
                        search_pos,
                    )
                else:
                    logger.debug(
                        "link[translated] text=%r NOT FOUND in "
                        "block %d chars (len=%d), using original rect",
                        link.get("_translated") or link.get("_inner"),
                        bidx,
                        len(block_text),
                    )
                    _insert_link_with_style(page, link, None)
            except Exception:
                logger.debug(
                    "Failed to restore link %s",
                    link,
                    exc_info=True,
                )

    # Fallback: search_for for links without block assignment
    for link in unassigned:
        try:
            link_rect = None
            if redact_rects and link.get("_inner"):
                fr = pymupdf.Rect(link["from"])
                overlapped = any(fr.intersects(r) for r in redact_rects)
                if overlapped:
                    oc = fr.tl + (fr.br - fr.tl) * 0.5
                    _closest = lambda h, c=oc: (  # noqa: E731
                        abs((h.x0 + h.x1) / 2 - c.x) + abs((h.y0 + h.y1) / 2 - c.y)
                    )
                    for candidate in (
                        link.get("_translated", ""),
                        link.get("_inner", ""),
                    ):
                        if candidate:
                            hits = page.search_for(candidate)
                            if hits:
                                link_rect = min(hits, key=_closest)
                                break
            _insert_link_with_style(page, link, link_rect)
            logger.debug(
                "link[translated][fallback] text=%r rect=%s (search_for=%s)",
                link.get("_translated") or link.get("_inner"),
                str(link_rect) if link_rect else "original",
                "hit" if link_rect else "skipped",
            )
        except Exception:
            logger.debug("Failed to restore link %s", link, exc_info=True)


def _dir_to_rotate(direction: tuple[float, float]) -> int:
    """Converts a PyMuPDF line direction vector to a rotation angle.

    Args:
        direction: ``(dx, dy)`` from the line's ``dir`` field.

    Returns:
        Rotation angle for ``insert_text``: 0, 90, 180, or 270.
    """
    dx, dy = direction
    if abs(dy + 1.0) < 0.3:  # noqa: PLR2004
        return 90  # bottom-to-top
    if abs(dy - 1.0) < 0.3:  # noqa: PLR2004
        return 270  # top-to-bottom
    if abs(dx + 1.0) < 0.3:  # noqa: PLR2004
        return 180  # right-to-left
    return 0


def _overlay_vertical_block(  # noqa: PLR0912, PLR0915
    page: Any,  # noqa: ANN401
    block: dict[str, Any],
    pymupdf: Any,  # noqa: ANN401
    fontname: str | None = None,
    font_obj: Any | None = None,  # noqa: ANN401
) -> None:
    """Overlays translated text for a vertical (rotated) text block.

    Uses ``insert_text`` with the appropriate ``rotate`` parameter
    instead of ``insert_htmlbox`` (which does not support vertical text).

    The text **direction** (rotation angle) comes from the ``_dir``
    vector via ``_dir_to_rotate()``.  The **alignment** (where to
    anchor the text within a label row) comes from
    ``_resolve_vertical_alignment()`` — stored as ``_vert_align``
    (``"bottom"`` / ``"top"`` / ``"center"``) and ``_vert_align_y``
    on the block dict.

    For ``rotate=90`` (bottom-to-top, the common case):

    * **bottom** — insert at the shared bottom y; text grows upward.
    * **top** — insert at ``shared_top + text_length`` so the text
      grows upward and its top edge lands on the shared top.
    * **center** — insert at ``shared_mid + text_length / 2``.

    Args:
        page: A PyMuPDF Page object.
        block: Block dict with ``translated_text``, ``_dir``, ``_origin``,
            ``font_size``, ``color`` keys.  May also have ``_vert_align``
            and ``_vert_align_y`` from alignment resolution.
        pymupdf: The pymupdf module reference.
        fontname: Registered font name for Unicode support.  When ``None``,
            falls back to the built-in ``helv`` (Latin-1 only).
        font_obj: A ``pymupdf.Font`` object for ``text_length()``
            calculation.  Required for top/center alignment offset.
    """
    text = block["translated_text"]
    size = block.get("font_size", 12.0)
    color_int = block.get("color", 0)
    r = (color_int >> 16) & 0xFF
    g = (color_int >> 8) & 0xFF
    b = color_int & 0xFF
    color_rgb = (r / 255.0, g / 255.0, b / 255.0)

    direction = block.get("_dir", (0.0, -1.0))
    rotate = _dir_to_rotate(direction)

    rect = pymupdf.Rect(block["rect"])
    origin = block.get("_origin")

    # Compute text length and scale font to fit within the rect.
    # Unlike insert_htmlbox, insert_text does not auto-shrink —
    # translated text that is longer than the original would overflow
    # the rect and overlap adjacent labels.
    text_len = 0.0
    if font_obj:
        try:
            text_len = font_obj.text_length(text, fontsize=size)
        except Exception:
            text_len = 0.0

        # Available space along the text direction
        if rotate in (90, 270):  # noqa: PLR2004
            available = rect.height
        elif rotate == 180:  # noqa: PLR2004
            available = rect.width
        else:
            available = rect.width

        if text_len > 0 and available > 0 and text_len > available:
            scale = available / text_len
            size = max(size * scale, 4.0)
            # Recompute text_len after scaling
            try:
                text_len = font_obj.text_length(text, fontsize=size)
            except Exception:
                text_len = available

    # Determine insertion point from alignment or origin.
    x_mid = rect.x0 + rect.width / 2
    vert_align = block.get("_vert_align")
    align_y = block.get("_vert_align_y")

    if vert_align and align_y is not None:
        ox = origin[0] if origin else x_mid
        if vert_align == "bottom":
            # Insert at shared bottom; text grows upward.
            point = pymupdf.Point(ox, align_y)
        elif vert_align == "top":
            # Text grows upward from insertion point.  Place the
            # insertion point so the top end lands on align_y.
            point = pymupdf.Point(ox, align_y + text_len)
        else:
            # Center: insertion so text is centered on align_y.
            point = pymupdf.Point(ox, align_y + text_len / 2)
    elif origin:
        point = pymupdf.Point(origin[0], origin[1])
    elif rotate == 90:  # noqa: PLR2004
        point = pymupdf.Point(x_mid, rect.y1)
    elif rotate == 270:  # noqa: PLR2004
        point = pymupdf.Point(x_mid, rect.y0)
    elif rotate == 180:  # noqa: PLR2004
        point = pymupdf.Point(rect.x1, rect.y0)
    else:
        point = pymupdf.Point(rect.x0, rect.y0)

    font_kwargs: dict[str, Any] = {}
    if fontname:
        font_kwargs["fontname"] = fontname

    page.insert_text(
        point,
        text,
        fontsize=size,
        rotate=rotate,
        color=color_rgb,
        **font_kwargs,
    )


def _apply_translated_blocks(  # noqa: PLR0912, PLR0913, PLR0915
    page: Any,  # noqa: ANN401
    blocks: list[dict[str, Any]],
    pymupdf: Any,  # noqa: ANN401
    saved_links: list[dict[str, Any]] | None = None,
    target_lang: str = "",
) -> None:
    """Redacts original text and overlays translated text on a PDF page.

    For each block with ``translated_text``:
    1. Adds a white-filled redaction annotation over the original area.
    2. Applies all redactions, preserving images and vector graphics.
    3. Inserts translated text via ``insert_htmlbox``.
    4. Restores all saved links.

    Args:
        page: A PyMuPDF Page object.
        blocks: Block dicts, each with at least ``rect`` and optionally
            ``translated_text``, ``font_size``, ``color``, ``bold``, ``italic``.
        pymupdf: The pymupdf module reference.
        saved_links: Pre-saved links from ``_save_page_links()`` with
            optional ``_translated`` keys.  When ``None``, links are
            saved on the fly (no translated search text).
        target_lang: Target language name for font selection.
    """
    has_redactions = False
    redact_rects: list[Any] = []
    for block in blocks:
        if "translated_text" not in block:
            continue
        rect = pymupdf.Rect(block["rect"])
        # Table cell spans can overflow the cell boundary (e.g.
        # merged cells or wide text like "Self-Attention (restricted)").
        # Extend redaction to cover the actual text extent so stray
        # original text doesn't show through.
        redact_x0 = block.get("_redact_x0")
        redact_x1 = block.get("_redact_x1")
        if redact_x0 is not None and redact_x0 < rect.x0:
            rect = pymupdf.Rect(redact_x0, rect.y0, rect.x1, rect.y1)
        if redact_x1 is not None and redact_x1 > rect.x1:
            rect = pymupdf.Rect(rect.x0, rect.y0, redact_x1, rect.y1)
        redact_rects.append(rect)
        has_redactions = True

    if not has_redactions:
        return

    # Use pre-saved links (with translated text) or save on the fly
    if saved_links is None:
        saved_links = _save_page_links(page)

    # Delete all links before redaction to prevent stale survivors.
    # Goto links (kind=1) can survive redaction at their ORIGINAL position,
    # creating duplicates and misaligned clickable areas after text overlay.
    for link in page.get_links():
        try:
            page.delete_link(link)
        except Exception:
            logger.debug("Failed to delete link before redaction", exc_info=True)

    # Try proper redaction first; fall back to white-rect overlay
    # for pages where apply_redactions() is too slow or fails.
    # Redaction rewrites the entire page content stream, which is
    # extremely expensive on pages with many vector drawings (charts,
    # matplotlib plots).  White-rect overlay is O(N) in block count
    # and avoids content stream rewriting entirely.
    _use_overlay = False
    try:
        # Quick complexity check — pages with many drawings are
        # better served by white-rect overlay (100x+ faster).
        n_drawings = len(page.get_cdrawings())
        if n_drawings > 10000:  # noqa: PLR2004
            _use_overlay = True
    except Exception:
        pass

    if _use_overlay:
        # Cover original text with white rectangles
        for rect in redact_rects:
            page.draw_rect(rect, color=(1, 1, 1), fill=(1, 1, 1))
    else:
        try:
            for rect in redact_rects:
                page.add_redact_annot(rect)
            page.apply_redactions(
                images=pymupdf.PDF_REDACT_IMAGE_NONE,
                graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
            )
        except Exception:
            logger.debug(
                "apply_redactions failed, falling back to overlay",
                exc_info=True,
            )
            # Fallback: remove any remaining annotations and use
            # white rectangles instead
            for annot in list(page.annots() or []):
                with contextlib.suppress(Exception):
                    page.delete_annot(annot)
            for rect in redact_rects:
                page.draw_rect(rect, color=(1, 1, 1), fill=(1, 1, 1))

    # Register a Unicode font for vertical text overlay.
    # insert_text() with the built-in "helv" only supports Latin-1;
    # non-Latin characters (Vietnamese, CJK, Cyrillic, …) are replaced
    # by ".".  Registering a system font via insert_font() fixes this.
    vert_fontname: str | None = None
    vert_font_obj: Any = None  # pymupdf.Font for text_length()
    has_vertical = any(b.get("is_vertical") for b in blocks if "translated_text" in b)
    if has_vertical:
        from src.utils.font_utils import (  # noqa: PLC0415
            classify_generic_family,
            get_font_for_language,
        )

        generic = classify_generic_family(font_flags=0)
        font_family = (
            get_font_for_language(target_lang, generic) if target_lang else generic
        )
        fontfile = _resolve_fontfile(font_family)
        if fontfile:
            try:
                page.insert_font(
                    fontname=_VERTICAL_FONT_NAME,
                    fontfile=fontfile,
                )
                vert_fontname = _VERTICAL_FONT_NAME
                vert_font_obj = pymupdf.Font(fontfile=fontfile)
            except Exception:
                logger.debug(
                    "Failed to register font %s from %s",
                    font_family,
                    fontfile,
                    exc_info=True,
                )

    # Overlay translated text (use render_rect when available for wider area)
    # A scratch doc is used to pre-measure spare height so each block is
    # rendered exactly once on the real page (avoids duplicate characters
    # that would break char-level link restoration).
    measure_doc = pymupdf.open()
    try:
        for block in blocks:
            if "translated_text" not in block:
                continue

            # Vertical text: use insert_text with rotation
            if block.get("is_vertical"):
                _overlay_vertical_block(
                    page,
                    block,
                    pymupdf,
                    fontname=vert_fontname,
                    font_obj=vert_font_obj,
                )
                continue

            rect = pymupdf.Rect(block.get("render_rect", block["rect"]))
            # Expand height for single-line blocks where the rect is barely
            # taller than the font — insert_htmlbox needs ~1.3× font size
            # for line-height and internal metrics.  Only expand downward;
            # the top edge stays put so the text baseline stays aligned.
            fs = block.get("font_size", 0)
            if fs > 0 and not block.get("is_table_cell"):
                min_h = fs * 1.3
                if rect.height < min_h:
                    rect = pymupdf.Rect(
                        rect.x0,
                        rect.y0,
                        rect.x1,
                        rect.y0 + min_h,
                    )
            # For table cells, inset horizontally so text does not touch
            # cell borders.  Vertical space is left untouched to maximise
            # the available height for text fitting.
            if block.get("is_table_cell") and rect.width > 10:  # noqa: PLR2004
                inset = 4.0
                rect = pymupdf.Rect(
                    rect.x0 + inset,
                    rect.y0,
                    rect.x1 - inset,
                    rect.y1,
                )
            overlay_html = _build_overlay_html(block, target_lang=target_lang)

            # Vertical centering: measure spare height on a scratch page,
            # then shift the rect down so text is vertically centered.
            # Only for single-line blocks where shrinkage is most visible.
            # Multi-line paragraphs keep top-alignment for even spacing.
            # Multi-line table cells use margin-top vertical positioning
            # in _build_overlay_html and are also excluded.
            if not _is_multiline_block(block):
                spare_h, _ = _measure_htmlbox_spare(
                    measure_doc,
                    overlay_html,
                    rect,
                )
                if spare_h > _VCENTER_SPARE_THRESHOLD:
                    rect = pymupdf.Rect(
                        rect.x0,
                        rect.y0 + spare_h / 2,
                        rect.x1,
                        rect.y1,
                    )
            page.insert_htmlbox(rect, overlay_html)
    finally:
        measure_doc.close()

    # Restore links with position remapping for translated text
    _restore_page_links(page, saved_links, redact_rects, blocks)


def _font_family_from_flags(flags: int) -> str:
    """Derive a CSS generic font-family from PyMuPDF font flags.

    Delegates to :func:`src.utils.font_utils.classify_generic_family`.
    """
    from src.utils.font_utils import classify_generic_family  # noqa: PLC0415

    return classify_generic_family(font_flags=flags)


# Module-level cache for font name → file path resolution.
_fontfile_cache: dict[str, str | None] = {}


def _resolve_fontfile(font_name: str) -> str | None:
    """Resolve a font family name to a font file path.

    Uses ``fc-match`` (fontconfig) on Linux/macOS, falling back to
    known system paths for common universal fonts.  Results are cached
    at module level.

    Args:
        font_name: Font family name (e.g. "DejaVu Sans", "Noto Sans CJK SC").

    Returns:
        Absolute path to a ``.ttf``/``.ttc``/``.otf`` file, or ``None``.
    """
    if font_name in _fontfile_cache:
        return _fontfile_cache[font_name]

    path: str | None = None

    # Try fc-match (Linux / macOS with fontconfig)
    if shutil.which("fc-match"):
        try:
            result = subprocess.run(
                ["fc-match", font_name, "--format=%{file}"],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                candidate = result.stdout.strip()
                if Path(candidate).is_file():
                    path = candidate
        except Exception:
            logger.debug("fc-match failed for '%s'", font_name, exc_info=True)

    # Fallback: known paths for common universal fonts
    if path is None:
        windir = os.environ.get("WINDIR", r"C:\Windows")
        home = Path.home()
        fallback_fonts = (
            # Linux
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            # macOS — system, shared, and user fonts (Intel and Apple Silicon)
            "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "/Library/Fonts/Arial Unicode MS.ttf",
            str(home / "Library" / "Fonts" / "Arial Unicode.ttf"),
            # Windows — use WINDIR env var for non-standard installs
            str(Path(windir) / "Fonts" / "arial.ttf"),
        )
        for fallback in fallback_fonts:
            if Path(fallback).is_file():
                path = fallback
                break

    _fontfile_cache[font_name] = path
    return path


# Internal name used to register the vertical-text font on a page.
_VERTICAL_FONT_NAME = "FVert"


def _classify_sup_sub(  # noqa: PLR0913
    span_size: float,
    span_y0: float,
    span_y1: float,
    line_dom_size: float,
    line_y0: float,
    line_y1: float,
) -> str | None:
    """Classify a span as superscript or subscript.

    A span is a candidate when its font size is significantly smaller
    than the line's dominant size.  Position within the line determines
    whether it is superscript (upper half) or subscript (lower half).

    Args:
        span_size: Font size of the span.
        span_y0: Top of span bounding box.
        span_y1: Bottom of span bounding box.
        line_dom_size: Dominant font size for the line.
        line_y0: Top of line bounding box.
        line_y1: Bottom of line bounding box.

    Returns:
        ``"sup"``, ``"sub"``, or ``None``.
    """
    if line_dom_size <= 0 or span_size >= line_dom_size * _SUP_SUB_SIZE_RATIO:
        return None
    line_mid = (line_y0 + line_y1) / 2
    span_mid = (span_y0 + span_y1) / 2
    return "sup" if span_mid < line_mid else "sub"


def _has_mixed_formatting(  # noqa: PLR0911, PLR0913
    flags_list: list[int],
    roles: list[str | None] | None = None,
    colors: list[int] | None = None,
    sizes: list[float] | None = None,
) -> bool:
    """Check if spans have varying bold/italic/color/size or super/subscript.

    Returns True when at least one span differs in bold, italic, color,
    or font size from the others, or when any span is classified as
    superscript or subscript — indicating formatting that should be
    preserved via inline HTML tags during translation.

    Font size variation is only counted for non-sup/sub spans so that
    size differences already captured by ``<sup>``/``<sub>`` do not
    redundantly trigger mixed formatting.

    Args:
        flags_list: List of PyMuPDF span flag integers.
        roles: Optional parallel list of ``"sup"``/``"sub"``/``None``
            from :func:`_classify_sup_sub`.
        colors: Optional parallel list of color integers (0xRRGGBB).
        sizes: Optional parallel list of font sizes in pt.

    Returns:
        True if formatting varies across spans.
    """
    if len(flags_list) < 2:  # noqa: PLR2004
        return False
    bolds = {bool(f & 16) for f in flags_list}
    italics = {bool(f & 2) for f in flags_list}
    if len(bolds) > 1 or len(italics) > 1:
        return True
    # Check for super/subscript roles
    if roles and any(r is not None for r in roles):
        return True
    # Check for color variation across spans
    if colors and len(set(colors)) > 1:
        return True
    # Check for font size variation (excluding sup/sub spans whose
    # size difference is already handled by <sup>/<sub> tags).
    if sizes and roles:
        normal_sizes = {
            s
            for s, r in zip(sizes, roles)  # noqa: B905
            if r is None
        }
        if len(normal_sizes) > 1:
            return True
    elif sizes and len(set(sizes)) > 1:
        return True
    return False


def _tag_span_text(  # noqa: PLR0913
    text: str,
    flags: int,
    base_bold: bool,
    base_italic: bool,
    role: str | None = None,
    color: int | None = None,
    base_color: int | None = None,
    size: float | None = None,
    base_size: float | None = None,
) -> str:
    """Wrap span text with formatting tags when it deviates from base.

    Only wraps when the span's formatting differs from the dominant
    (base) value.  Tags are ``<b>``/``<i>``/``<sup>``/``<sub>`` for
    weight/style/position, ``<span style="color:#rrggbb">`` for color
    deviations, and ``<span style="font-size:Xpt">`` for size
    deviations (only when the span is not already sup/sub).

    When both color and size deviate, they are combined in a single
    ``<span>`` tag to reduce token noise.

    Whitespace-only spans are never wrapped — tagging spaces adds
    noise without visual effect.

    Note: when the base *is* bold/italic and a span is *not*, we
    cannot easily undo the ``<p>``-level weight/style with plain
    HTML.  This is acceptable because in practice the minority
    formatting (bold labels, italic headings) is almost always the
    deviation, not the base.

    Args:
        text: Plain span text (not HTML-escaped).
        flags: PyMuPDF span flags integer.
        base_bold: Dominant bold value for the block/cell.
        base_italic: Dominant italic value for the block/cell.
        role: ``"sup"``, ``"sub"``, or ``None`` from
            :func:`_classify_sup_sub`.
        color: Span color as 0xRRGGBB integer, or ``None``.
        base_color: Dominant block color as 0xRRGGBB integer, or
            ``None``.
        size: Span font size in pt, or ``None``.
        base_size: Dominant block font size in pt, or ``None``.

    Returns:
        Text optionally wrapped with formatting tags.
    """
    # Whitespace-only spans never need formatting tags
    if not text.strip():
        return text
    result = text
    if bool(flags & 16) and not base_bold:
        result = f"<b>{result}</b>"
    if bool(flags & 2) and not base_italic:
        result = f"<i>{result}</i>"
    if role == "sup":
        result = f"<sup>{result}</sup>"
    elif role == "sub":
        result = f"<sub>{result}</sub>"
    # Build <span> style for color and/or size deviations.
    # Combine into a single <span> tag when both differ.
    span_parts: list[str] = []
    if color is not None and base_color is not None and color != base_color:
        r = (color >> 16) & 0xFF
        g = (color >> 8) & 0xFF
        b_ = color & 0xFF
        span_parts.append(f"color:#{r:02x}{g:02x}{b_:02x}")
    # Font size deviation (skip for sup/sub — already visually smaller).
    # Use a 0.5pt tolerance to ignore PDF authoring artifacts where
    # citation numbers or punctuation have a trivially different size
    # (e.g. 9.96pt vs 10.06pt).  Without the tolerance, single-char
    # spans like [<span>7</span>] create separate text runs that
    # insert_htmlbox may fail to render.
    if (
        size is not None
        and base_size is not None
        and abs(size - base_size) > 0.5  # noqa: PLR2004
        and role is None
    ):
        span_parts.append(f"font-size:{size:.1f}pt")
    if span_parts:
        style = ";".join(span_parts)
        result = f'<span style="{style}">{result}</span>'
    return result


# Matches a full <span style=X>CONTENT</span> followed by <span style=X>
# (same style via backreference) so they can be collapsed into one.
# The content uses a tempered greedy token to allow inner tags except </span>.
_MERGE_SAME_SPAN_RE = re.compile(
    r'(<span style="([^"]+)">)'  # grp1: open tag, grp2: style value
    r"((?:(?!</span>).)*)"  # grp3: content (no </span>)
    r"</span>(\s?)"  # grp4: optional space
    r'<span style="\2">',  # same style (backreference)
    re.DOTALL,
)


def _merge_adjacent_tags(text: str) -> str:
    """Merge adjacent identical formatting tags into single spans.

    Replaces patterns like ``</b><b>`` or ``</b> <b>`` with just the
    space (or nothing), collapsing consecutive same-format runs into
    one pair of tags.  Also merges adjacent ``<span>`` tags that share
    the same style.  Reduces token noise sent to the LLM.

    Args:
        text: Tagged text potentially containing redundant adjacent tags.

    Returns:
        Text with adjacent same tags merged.
    """
    for tag in ("b", "i", "sup", "sub"):
        # </b><b> → nothing (directly adjacent)
        text = text.replace(f"</{tag}><{tag}>", "")
        # </b> <b> → single space (separated by whitespace)
        text = text.replace(f"</{tag}> <{tag}>", " ")
    # Merge adjacent <span> tags with identical style (backreference).
    # Loop until stable because merging can create new adjacent pairs.
    prev = None
    while text != prev:
        prev = text
        text = _MERGE_SAME_SPAN_RE.sub(r"\1\3\4", text)
    return text


def _cap_by_neighbors(  # noqa: PLR0913
    block: dict[str, Any],
    all_blocks: list[dict[str, Any]],
    bx1: float,
    by0: float,
    by1: float,
    proposed_x1: float,
) -> float:
    """Cap *proposed_x1* so it doesn't collide with any other block.

    Checks ALL blocks (including table cells) for vertical overlap.
    For blocks starting to the right of *bx1*, caps at their left edge.
    For blocks that straddle *bx1* (start before, extend past), caps
    at *bx1* itself so the extension doesn't overlap.
    """
    capped = proposed_x1
    for other in all_blocks:
        if other is block:
            continue
        or_ = other["rect"]
        # Must overlap vertically
        if or_[3] <= by0 or or_[1] >= by1:
            continue
        # Must have area past our right edge
        if or_[2] <= bx1:
            continue
        # Barrier: other's left edge, but not before our right edge
        barrier = max(or_[0], bx1)
        capped = min(capped, barrier)
    return capped


def _cap_by_left_neighbors(  # noqa: PLR0913
    block: dict[str, Any],
    all_blocks: list[dict[str, Any]],
    bx0: float,
    by0: float,
    by1: float,
    proposed_x0: float,
) -> float:
    """Cap *proposed_x0* so leftward growth doesn't collide with any block.

    Symmetric to :func:`_cap_by_neighbors` but for growing leftward.
    For blocks ending to the left of *bx0*, caps at their right edge.
    For blocks that straddle *bx0* (end after, start before), caps
    at *bx0* itself so the extension doesn't overlap.
    """
    capped = proposed_x0
    for other in all_blocks:
        if other is block:
            continue
        or_ = other["rect"]
        # Must overlap vertically
        if or_[3] <= by0 or or_[1] >= by1:
            continue
        # Must have area before our left edge
        if or_[0] >= bx0:
            continue
        # Barrier: other's right edge, but not after our left edge
        barrier = min(or_[2], bx0)
        capped = max(capped, barrier)
    return capped


def _split_multiline_blocks(  # noqa: PLR0912, PLR0915
    blocks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    r"""Split multi-line blocks at ``\n`` boundaries into sub-blocks.

    When a block contains multiple paragraphs (joined by ``\n``),
    ``_widen_render_rects`` skips it because widening a multi-line block
    changes line breaks.  By splitting into per-paragraph sub-blocks,
    each paragraph can be independently widened without affecting others.

    Each sub-block gets its own ``rect`` derived from the y-extents of
    its constituent lines and inherits all properties from the parent.
    The ``_math_map`` placeholders are distributed to the sub-block
    whose text contains them.

    Table cells and vertical text are never split — their layout depends
    on the enclosing cell / rotation origin.

    Args:
        blocks: List of block dicts (not modified; returns a new list).

    Returns:
        New list with multi-line blocks replaced by sub-blocks.
    """
    result: list[dict[str, Any]] = []
    for block in blocks:
        text = block.get("text", "")
        # Only split blocks with explicit paragraph breaks
        if "\n" not in text:
            result.append(block)
            continue
        # Never split table cells or vertical text
        if block.get("is_table_cell") or block.get("is_vertical"):
            result.append(block)
            continue
        # Need stored line data to reconstruct sub-block rects
        joins = block.get("_line_joins")
        y0s = block.get("_line_y0s")
        y1s = block.get("_line_y1s")
        extents = block.get("_line_extents")
        if not joins or not y0s or not y1s or not extents:
            result.append(block)
            continue

        # Group lines into paragraphs based on joins.
        # joins[i] connects line i to line i+1.
        # "\n" = paragraph break, " " = same paragraph.
        n_lines = len(y0s)
        para_line_groups: list[list[int]] = [[0]]
        for ji, jc in enumerate(joins):
            if ji + 1 >= n_lines:
                break
            if jc == "\n":
                para_line_groups.append([ji + 1])
            else:
                para_line_groups[-1].append(ji + 1)

        # If only one paragraph group, no split needed
        if len(para_line_groups) <= 1:
            result.append(block)
            continue

        paras = text.split("\n")
        # Sanity: paragraph count must match group count
        if len(paras) != len(para_line_groups):
            result.append(block)
            continue

        math_map = block.get("_math_map", {})
        parent_line_sizes = block.get("_line_sizes", [])
        para_colors = block.get("para_colors", [])

        for pi, (para_text, line_indices) in enumerate(
            zip(paras, para_line_groups, strict=False),
        ):
            if not para_text.strip():
                continue
            # Compute sub-block rect from its lines' y-extents
            sub_y0 = min(y0s[li] for li in line_indices)
            sub_y1 = max(y1s[li] for li in line_indices)
            sub_x0 = min(extents[li][0] for li in line_indices)
            sub_x1 = max(extents[li][1] for li in line_indices)

            sub: dict[str, Any] = {
                "rect": [sub_x0, sub_y0, sub_x1, sub_y1],
                "text": para_text,
                "font_size": block.get("font_size", 12.0),
                "font_name": block.get("font_name", ""),
                "color": block.get("color", 0),
                "bold": block.get("bold", False),
                "italic": block.get("italic", False),
                "font_flags": block.get("font_flags", 0),
                "text_align": block.get("text_align", "left"),
            }
            # Recompute indents using only this sub-block's own line
            # data.  The parent's para_indents were computed relative to
            # a block-wide margin_ref that includes lines from OTHER
            # paragraphs; inheriting them would double-count offsets
            # already encoded in the sub-block's rect x0.
            sub_extents = [extents[li] for li in line_indices]
            sub_sizes = [
                parent_line_sizes[li]
                for li in line_indices
                if li < len(parent_line_sizes)
            ]
            # Joins between consecutive lines within this paragraph
            # (all spaces — newlines were used to split paragraphs).
            sub_joins = [
                joins[line_indices[j]]
                for j in range(len(line_indices) - 1)
                if line_indices[j] < len(joins)
            ]
            sub_indents = _compute_para_indents(
                sub_extents,
                sub_sizes or [12.0],
                sub_joins,
            )
            if sub_indents:
                sub["para_indents"] = sub_indents
            # Inherit per-paragraph color
            if pi < len(para_colors):
                sub["para_colors"] = [para_colors[pi]]
            # Mixed formatting
            if block.get("has_mixed_formatting"):
                sub["has_mixed_formatting"] = True
            # Space-between (unlikely in multi-para but preserve)
            if block.get("is_space_between"):
                sub["is_space_between"] = True
            # Distribute math placeholders to sub-blocks
            if math_map:
                sub_math: dict[str, Any] = {}
                for key, val in math_map.items():
                    if key in para_text:
                        sub_math[key] = val
                if sub_math:
                    sub["_math_map"] = sub_math
            # Line data for the sub-block's own lines
            sub["_line_extents"] = [extents[li] for li in line_indices]
            sub["_line_sizes"] = [
                block["_line_sizes"][li]
                for li in line_indices
                if li < len(block["_line_sizes"])
            ]
            sub["_line_y_mids"] = [
                block["_line_y_mids"][li]
                for li in line_indices
                if li < len(block["_line_y_mids"])
            ]
            # Mark as originating from a split for debugging
            sub["_split_from_parent"] = True
            result.append(sub)

    return result


# Threshold for multi-line detection: if block height exceeds this
# multiple of the font size, the block is considered multi-line and
# should NOT be widened (it already wraps within its rect width).
_MULTILINE_HEIGHT_RATIO = 2.0

# Minimum spare height (pt) before vertical centering kicks in.
# Below this threshold the offset is imperceptible; above it the
# render rect is shifted down by half the spare height.
_VCENTER_SPARE_THRESHOLD = 2.0


def _measure_htmlbox_spare(
    measure_doc: Any,  # noqa: ANN401
    html: str,
    rect: Any,  # noqa: ANN401
) -> tuple[float, float]:
    """Measure spare height and scale factor on a scratch page.

    Renders *html* into *rect* on a temporary page of *measure_doc*
    and returns ``(spare_height, scale_factor)`` without touching the
    real page.  The scratch page is deleted immediately so the temp
    doc stays lightweight.
    """
    tp = measure_doc.new_page(
        width=rect.x1 + 1,
        height=rect.y1 + 1,
    )
    try:
        rc = tp.insert_htmlbox(rect, html)
    finally:
        measure_doc.delete_page(-1)
    if isinstance(rc, (tuple, list)) and len(rc) >= 2:  # noqa: PLR2004
        return float(rc[0]), float(rc[1])
    return 0.0, 1.0


def _is_multiline_block(block: dict[str, Any]) -> bool:
    r"""Return True if a block contains multiple visual lines.

    Detects both explicit newlines (``\n``) and implicit line wrapping
    (block height > 2× font size).
    """
    if "\n" in block.get("text", ""):
        return True
    fs = block.get("font_size", 0)
    rect = block.get("rect")
    if fs > 0 and rect:
        bh = rect[3] - rect[1]
        if bh > fs * _MULTILINE_HEIGHT_RATIO:
            return True
    return False


def _ends_with_math_placeholder(block: dict[str, Any]) -> bool:
    """Return True if block text ends with a math placeholder.

    Predominantly-math blocks ending with math (e.g. radical ``√``,
    delimiters) should not be widened — the math content fills the
    original rect's right edge, and widening causes radical overlines /
    delimiter bars to extend into empty space.
    """
    text = block.get("text", "").rstrip()
    return text.endswith(_MATH_PH_END)


def _widen_render_rects(blocks: list[dict[str, Any]]) -> None:  # noqa: PLR0912, PLR0915
    """Extend render_rect to fill available column width.

    Groups non-table blocks by column (similar left edge) and extends
    each block's rendering rectangle to the column's right boundary.
    This prevents font shrinkage when translated text is longer than
    the original — headings and short lines get the full column width.

    Full-width blocks (spanning > 60% of the page width, inferred from
    the widest block) are excluded from column boundary calculation so
    they don't inflate narrow columns on pages with few blocks.

    Only sets ``render_rect`` when the column boundary exceeds the
    block's own right edge.  The original ``rect`` is preserved for
    redaction so only the actual text area is cleared.

    Args:
        blocks: List of block dicts (modified in place).
    """
    non_table = [b for b in blocks if not b.get("is_table_cell")]
    if not non_table:
        return

    # Detect full-width threshold: 60% of the widest block on the page.
    # Blocks wider than this are headers/footers that span both columns.
    max_width = max(b["rect"][2] - b["rect"][0] for b in non_table)
    full_width_threshold = max_width * 0.6

    # Build columns: group column-width blocks by x0 proximity
    columns: list[tuple[float, list[float]]] = []  # (repr_x0, [x1_values])
    for block in sorted(non_table, key=lambda b: b["rect"][0]):
        bw = block["rect"][2] - block["rect"][0]
        if bw > full_width_threshold:
            continue  # Skip full-width blocks (headers, footers)
        bx0 = block["rect"][0]
        bx1 = block["rect"][2]
        placed = False
        for _ci, (cx0, x1s) in enumerate(columns):
            if abs(bx0 - cx0) < _COL_X_TOLERANCE:
                x1s.append(bx1)
                placed = True
                break
        if not placed:
            columns.append((bx0, [bx1]))

    if not columns:
        return

    # Compute column right boundary as median x1
    col_boundaries: list[tuple[float, float]] = []
    for cx0, x1s in columns:
        sorted_x1 = sorted(x1s)
        col_x1 = sorted_x1[len(sorted_x1) // 2]
        col_boundaries.append((cx0, col_x1))

    # Assign render_rect to blocks narrower than their column,
    # but cap the right edge so it doesn't overlap any other block
    # (including table cells) at the same vertical level.
    for block in non_table:
        # Multi-line paragraphs already wrap — widening changes line
        # breaks and may push text beyond the column boundary.
        if _is_multiline_block(block):
            continue
        # Blocks ending with math (radical √, delimiters) already fill
        # their rect — widening causes overline/bar artifacts.
        if _ends_with_math_placeholder(block):
            continue
        bx0 = block["rect"][0]
        for cx0, col_x1 in col_boundaries:
            if abs(bx0 - cx0) < _COL_X_TOLERANCE:
                if col_x1 > block["rect"][2] + 1.0:
                    by0, by1 = block["rect"][1], block["rect"][3]
                    bx1 = block["rect"][2]
                    max_x1 = col_x1
                    max_x1 = _cap_by_neighbors(
                        block,
                        blocks,
                        bx1,
                        by0,
                        by1,
                        max_x1,
                    )
                    if max_x1 > bx1 + 1.0:
                        block["render_rect"] = [
                            bx0,
                            block["rect"][1],
                            max_x1,
                            block["rect"][3],
                        ]
                break

    # Fallback: widen single-line blocks using the full content-area
    # edges.  On single-column pages, body text is excluded as
    # "full-width" so the column boundary only reflects narrow blocks
    # (section titles).  This pass considers ALL same-x0 blocks to find
    # the true content edges, then caps by nearest neighbors.
    # Only applies to single-line text — multi-line paragraphs already
    # wrap and don't benefit from a wider render rect.
    #
    # On multi-column pages, full-width blocks (headers/footers spanning
    # both columns) are excluded to prevent cross-column overflow.
    # Multi-column is detected only when ≥ 2 columns each have ≥ 2
    # non-full-width blocks — isolated blocks at different x0 positions
    # don't constitute a real column layout.
    #
    # Alignment-aware direction:
    #   left/justify → grow rightward
    #   right        → grow leftward
    #   center       → grow both directions
    min_column_blocks = 2
    multi_col_count = sum(1 for _cx0, x1s in columns if len(x1s) >= min_column_blocks)
    is_multicolumn = multi_col_count >= min_column_blocks

    for block in non_table:
        if _is_multiline_block(block):
            continue
        if _ends_with_math_placeholder(block):
            continue
        align = block.get("text_align", "left")
        bx0 = block["rect"][0]
        bx1 = block["rect"][2]
        by0, by1 = block["rect"][1], block["rect"][3]
        current_x0 = block["render_rect"][0] if block.get("render_rect") else bx0
        current_x1 = block["render_rect"][2] if block.get("render_rect") else bx1
        grow_right = align in ("left", "justify", "center")
        grow_left = align in ("right", "center")

        new_x0 = current_x0
        new_x1 = current_x1

        if align == "center":
            # Center-aligned blocks (e.g. "Abstract") don't share x0 or
            # x1 with body text.  Find the content area by looking for
            # blocks whose x-range contains this block's center.
            block_cx = (bx0 + bx1) / 2
            target_x0 = bx0
            target_x1 = bx1
            for other in non_table:
                if other is block:
                    continue
                ox0 = other["rect"][0]
                ox1 = other["rect"][2]
                # On multi-column pages, skip full-width blocks
                # (headers/footers spanning both columns).
                if is_multicolumn and (ox1 - ox0) > full_width_threshold:
                    continue
                if ox0 <= block_cx <= ox1:
                    target_x0 = min(target_x0, ox0)
                    target_x1 = max(target_x1, ox1)
            if target_x1 > current_x1 + 1.0:
                capped_x1 = _cap_by_neighbors(
                    block,
                    blocks,
                    bx1,
                    by0,
                    by1,
                    target_x1,
                )
                if capped_x1 > current_x1 + 1.0:
                    new_x1 = capped_x1
            if target_x0 < current_x0 - 1.0:
                capped_x0 = _cap_by_left_neighbors(
                    block,
                    blocks,
                    bx0,
                    by0,
                    by1,
                    target_x0,
                )
                if capped_x0 < current_x0 - 1.0:
                    new_x0 = capped_x0
        else:
            if grow_right:
                # Find max x1 among all blocks sharing the same x0.
                # On multi-column pages, skip full-width blocks
                # (headers/footers spanning both columns).
                max_col_x1 = bx1
                for other in non_table:
                    if other is block:
                        continue
                    ox0 = other["rect"][0]
                    ox1 = other["rect"][2]
                    if is_multicolumn and (ox1 - ox0) > full_width_threshold:
                        continue
                    if abs(ox0 - bx0) < _COL_X_TOLERANCE and ox1 > max_col_x1:
                        max_col_x1 = ox1
                if max_col_x1 > current_x1 + 1.0:
                    capped_x1 = _cap_by_neighbors(
                        block,
                        blocks,
                        bx1,
                        by0,
                        by1,
                        max_col_x1,
                    )
                    if capped_x1 > current_x1 + 1.0:
                        new_x1 = capped_x1

            if grow_left:
                # Find min x0 among all blocks sharing the same x1.
                # On multi-column pages, skip full-width blocks.
                min_col_x0 = bx0
                for other in non_table:
                    if other is block:
                        continue
                    ox0 = other["rect"][0]
                    ox1 = other["rect"][2]
                    if is_multicolumn and (ox1 - ox0) > full_width_threshold:
                        continue
                    if abs(ox1 - bx1) < _COL_X_TOLERANCE and ox0 < min_col_x0:
                        min_col_x0 = ox0
                if min_col_x0 < current_x0 - 1.0:
                    capped_x0 = _cap_by_left_neighbors(
                        block,
                        blocks,
                        bx0,
                        by0,
                        by1,
                        min_col_x0,
                    )
                    if capped_x0 < current_x0 - 1.0:
                        new_x0 = capped_x0

        if new_x0 < current_x0 - 1.0 or new_x1 > current_x1 + 1.0:
            block["render_rect"] = [
                new_x0,
                block["rect"][1],
                new_x1,
                block["rect"][3],
            ]


# Matches escaped <span style="..."> tags containing only allowed CSS
# properties (color, font-size) so they can be restored after escaping.
_ALLOWED_CSS_PROP = (
    r"color:#[0-9a-fA-F]{6}"
    r"|font-size:[\d.]+pt"
)
_ESCAPED_SPAN_STYLE_RE = re.compile(
    r"&lt;span style=&quot;"
    rf"(?:{_ALLOWED_CSS_PROP})"
    rf"(?:;(?:{_ALLOWED_CSS_PROP}))*"
    r";?"  # optional trailing semicolon
    r"&quot;&gt;",
)
# Matches escaped <img> tags with data-URI src (inline glyph images).
_ESCAPED_IMG_TAG_RE = re.compile(
    r"&lt;img src=&quot;data:image/png;base64,[A-Za-z0-9+/=]+"
    r"&quot; width=&quot;[\d.]+&quot; height=&quot;[\d.]+&quot;&gt;",
)


def _escape_preserving_tags(text: str) -> str:
    """HTML-escape text while preserving allowed inline formatting tags.

    Escapes all HTML entities first, then selectively restores
    ``<b>``, ``<i>``, ``<sup>``, ``<sub>``, ``</span>``, and
    ``<span style="...">`` tags whose style contains only allowed
    CSS properties (``color`` and ``font-size``) so they render
    correctly in ``insert_htmlbox()``.

    Args:
        text: Text potentially containing formatting tags.

    Returns:
        HTML-safe string with allowed tags preserved.
    """
    escaped = html.escape(text)
    for tag in (
        "<b>",
        "</b>",
        "<i>",
        "</i>",
        "<sup>",
        "</sup>",
        "<sub>",
        "</sub>",
        "</span>",
    ):
        escaped = escaped.replace(html.escape(tag), tag)
    # Restore <span style="..."> tags with allowed CSS properties
    escaped = _ESCAPED_SPAN_STYLE_RE.sub(
        lambda m: html.unescape(m.group(0)),
        escaped,
    )
    # Restore <img> tags with inline base64 glyph images
    return _ESCAPED_IMG_TAG_RE.sub(
        lambda m: html.unescape(m.group(0)),
        escaped,
    )


def _build_overlay_html(  # noqa: PLR0912, PLR0915
    block: dict[str, Any],
    target_lang: str = "",
) -> str:
    """Builds an HTML snippet for overlaying translated text.

    Extracts RGB from the block's color int and applies font properties.
    When *target_lang* is provided, selects a concrete font that supports
    the target language within the same generic family (serif / sans-serif /
    monospace) as the source font.  Falls back to the generic family name
    when no concrete match is found.

    For blocks with ``has_mixed_formatting``, inline ``<b>``/``<i>`` tags
    in the translated text are preserved so ``insert_htmlbox`` renders
    them with the correct weight/style.

    Args:
        block: Block dict with translated_text, font_size, color,
            bold, italic, font_flags keys.  Optionally text_align,
            is_table_cell, and has_mixed_formatting.
        target_lang: Target language name for font selection.

    Returns:
        HTML string for ``insert_htmlbox``.
    """
    text = block.get("translated_text", "")
    size = block.get("font_size", 12.0)
    color_int = block.get("color", 0)
    is_bold = block.get("bold", False)
    is_italic = block.get("italic", False)
    text_align = block.get("text_align", "left")
    text_indent = block.get("text_indent", 0.0)
    cell_line_y0s: list[float] = block.get("cell_line_y0s", [])
    font_flags = block.get("font_flags", 0)
    font_name = block.get("font_name", "")
    mixed = block.get("has_mixed_formatting", False)
    is_space_between = block.get("is_space_between", False)

    # Extract RGB from color int (0xRRGGBB format)
    r = (color_int >> 16) & 0xFF
    g = (color_int >> 8) & 0xFF
    b = color_int & 0xFF

    weight = "bold" if is_bold else "normal"
    style = "italic" if is_italic else "normal"

    # Select font: classify generic family from source, pick concrete for target
    from src.utils.font_utils import (  # noqa: PLC0415
        classify_generic_family,
        get_font_for_language,
    )

    generic = classify_generic_family(font_name=font_name, font_flags=font_flags)
    family = get_font_for_language(target_lang, generic) if target_lang else generic

    # RTL targets: emit dir="rtl" on every <p> and flip ambiguous "left"
    # to "right" so the natural reading anchor matches the script.  The
    # geometric text_align is derived from LTR-extracted span coordinates
    # so it can't be trusted to mean "start of line" for an Arabic /
    # Hebrew / Persian translation overlay.
    from src.constants.languages import is_rtl_language  # noqa: PLC0415

    is_rtl_target = is_rtl_language(target_lang)
    if is_rtl_target and text_align == "left":
        text_align = "right"
    dir_attr = ' dir="rtl"' if is_rtl_target else ""

    # Build shared CSS for <p> tags
    base_css = (
        f"font-family:{family}; font-size:{size}pt;"
        f" color:#{r:02x}{g:02x}{b:02x};"
        f" font-weight:{weight}; font-style:{style};"
        f" text-align:{text_align};"
    )
    indent_css = f" text-indent:{text_indent}pt;" if text_indent else ""

    # Space-between layout: left text + right text separated by \t.
    # Render as a two-cell table so text hugs opposite edges.
    if is_space_between and "\t" in text:
        cell_css = (
            f"font-family:{family}; font-size:{size}pt;"
            f" color:#{r:02x}{g:02x}{b:02x};"
            f" font-weight:{weight}; font-style:{style};"
            " padding:0; margin:0;"
        )
        left_part, right_part = text.split("\t", 1)
        _esc = _escape_preserving_tags if mixed else html.escape
        esc_l = _esc(left_part)
        esc_r = _esc(right_part)
        # Mirror the two cells for RTL targets: the natural left side
        # of an LTR space-between layout becomes the right side in RTL.
        if is_rtl_target:
            return (
                f'<table{dir_attr} style="width:100%;"><tr>'
                f'<td style="{cell_css} text-align:right;">{esc_l}</td>'
                f'<td style="{cell_css} text-align:left;">{esc_r}</td>'
                "</tr></table>"
            )
        return (
            '<table style="width:100%;"><tr>'
            f'<td style="{cell_css} text-align:left;">{esc_l}</td>'
            f'<td style="{cell_css} text-align:right;">{esc_r}</td>'
            "</tr></table>"
        )

    # Table cells with original line y-positions: use margin-top to
    # replicate the original vertical spacing so sparse columns align
    # with dense columns (e.g. left column prompt names aligning with
    # multi-line right column prompt text).
    if cell_line_y0s and "\n" in text:
        paras = text.split("\n")
        if len(paras) == len(cell_line_y0s):
            cell_top = block.get("rect", [0, 0, 0, 0])[1]
            line_height = size * 1.2
            parts_y: list[str] = []
            for idx, para in enumerate(paras):
                if idx == 0:
                    mt = cell_line_y0s[0] - cell_top
                else:
                    gap = cell_line_y0s[idx] - cell_line_y0s[idx - 1]
                    mt = max(0.0, gap - line_height)
                mt_css = f" margin-top:{mt:.1f}pt;" if mt > 0.5 else ""  # noqa: PLR2004
                p_css = f"{base_css} margin:0;{mt_css}"
                esc = _escape_preserving_tags(para) if mixed else html.escape(para)
                parts_y.append(f'<p{dir_attr} style="{p_css}">{esc}</p>')
            return "".join(parts_y)

    # When text has paragraph breaks (\n), always use separate <p> tags
    # so each paragraph can have its own indentation.  With a single <p>
    # and <br/>, paragraphs would run together without visual separation.
    if "\n" in text:
        paras = text.split("\n")
        para_indents = block.get("para_indents", [])
        para_colors = block.get("para_colors", [])
        parts: list[str] = []
        for idx, para in enumerate(paras):
            # Per-paragraph indents: (block_indent, first_line_indent).
            # block_indent shifts the whole paragraph (padding-left);
            # first_line_indent shifts only the first line (text-indent).
            if idx < len(para_indents):
                blk_ind, fl_ind = para_indents[idx]
            else:
                blk_ind, fl_ind = 0.0, text_indent
            pad_css = f" padding-left:{blk_ind}pt;" if blk_ind else ""
            fl_css = f" text-indent:{fl_ind}pt;" if fl_ind else ""
            # Per-paragraph color override: when a block contains
            # paragraphs with different colors (e.g. blue author
            # names followed by black affiliation), each <p> gets
            # its own color instead of the block's dominant color.
            if para_colors and idx < len(para_colors):
                pc = para_colors[idx]
                pr_ = (pc >> 16) & 0xFF
                pg_ = (pc >> 8) & 0xFF
                pb_ = pc & 0xFF
                para_base = (
                    f"font-family:{family}; font-size:{size}pt;"
                    f" color:#{pr_:02x}{pg_:02x}{pb_:02x};"
                    f" font-weight:{weight}; font-style:{style};"
                    f" text-align:{text_align};"
                )
            else:
                para_base = base_css
            para_style = f"{para_base}{pad_css}{fl_css} margin:0;"
            esc = _escape_preserving_tags(para) if mixed else html.escape(para)
            parts.append(f'<p{dir_attr} style="{para_style}">{esc}</p>')
        return "".join(parts)

    # Single paragraph: no \n, use one <p>.
    # Apply para_indents if available (e.g. hanging indent for headings
    # like "2.1  Advantages of ...").
    para_indents = block.get("para_indents", [])
    if para_indents:
        blk_ind, fl_ind = para_indents[0]
        pad_css = f" padding-left:{blk_ind}pt;" if blk_ind else ""
        fl_css = f" text-indent:{fl_ind}pt;" if fl_ind else ""
        indent_css = f"{pad_css}{fl_css}"
    escaped = _escape_preserving_tags(text) if mixed else html.escape(text)

    # For originally single-line blocks, prevent wrapping so
    # translated text stays on one line.  insert_htmlbox shrinks
    # uniformly if the text is too wide rather than wrapping.
    nowrap_css = ""
    if not _is_multiline_block(block) and not block.get("is_table_cell"):
        nowrap_css = " white-space:nowrap;"

    return (
        f'<p{dir_attr} style="{base_css}{indent_css}{nowrap_css} margin:0;">'
        f"{escaped}</p>"
    )


# ── Scanned page processing (OCR pipeline) ───────────────────────────


def _process_scanned_pages(  # noqa: PLR0913, PLR0912, PLR0915
    output_path: Path,
    scanned_indices: list[int],
    target_lang: str,
    src_lang: str,
    glossary_entries: list[tuple[int, str, str]] | None,
    progress_callback: Callable[[int], None] | None,
    cancel_check: Callable[[], bool] | None,
    text_weight: float,
    config: TranslationConfig | None = None,
    *,
    provider: str | None = None,
    model: str | None = None,
) -> bool:
    """Processes scanned PDF pages using the OCR → LLM → render pipeline.

    Re-opens the saved output PDF, renders each scanned page to a temp
    image, runs OCR + vision translation, and replaces the page content.

    Args:
        output_path: Path to the (already saved) output PDF.
        scanned_indices: List of zero-based page indices to OCR.
        target_lang: Target language name.
        src_lang: Source language name.
        glossary_entries: Optional glossary entries.
        progress_callback: Called with 0-100 progress percentage.
        cancel_check: Returns True if the task was cancelled.
        text_weight: Fraction of progress already consumed by text pages.
        config: Optional TranslationConfig snapshot; falls back to
            ``_config.load_setting()``.
        provider: Optional LLM provider override.
        model: Optional LLM model override.

    Returns:
        True on success, False on cancellation.
    """
    from src.core.image_processor import process_image_translation  # noqa: PLC0415
    from src.core.layout_analysis import merge_to_paragraphs  # noqa: PLC0415
    from src.core.llm_engine import translate_image_content  # noqa: PLC0415
    from src.core.ocr_engine import run_ocr  # noqa: PLC0415

    if config is not None:
        ocr_method = config.ocr_method
    else:
        ocr_method = _config.load_setting(SETTING_OCR_METHOD, OCR_METHOD_TESSERACT)

    doc = pymupdf.open(str(output_path))
    try:
        total_scanned = len(scanned_indices)
        for i, page_idx in enumerate(scanned_indices):
            # Cancel check between pages
            if cancel_check and cancel_check():
                return False

            page = doc[page_idx]

            # Render page to temporary PNG at 300 DPI
            tmp_png_path: str | None = None
            tmp_out_path: str | None = None
            try:
                pix = page.get_pixmap(dpi=300)
                fd, tmp_png_path = tempfile.mkstemp(suffix=".png")
                os.close(fd)
                pix.save(tmp_png_path)

                # Run OCR on the rendered image
                ocr_results = run_ocr(
                    tmp_png_path,
                    method=ocr_method,
                    src_lang=src_lang,
                )

                if ocr_results:
                    # Vision-based LLM translation
                    paragraph_data = translate_image_content(
                        tmp_png_path,
                        ocr_results,
                        target_lang,
                        src_lang,
                        glossary_entries=glossary_entries,
                        provider=provider,
                        model=model,
                    )

                    merged, translations, raw_frags = merge_to_paragraphs(
                        paragraph_data,
                        list(ocr_results),
                        ocr_method,
                    )

                    # Create temp output image
                    fd_out, tmp_out_path = tempfile.mkstemp(suffix=".png")
                    os.close(fd_out)

                    success = process_image_translation(
                        tmp_png_path,
                        tmp_out_path,
                        merged,
                        translations,
                        target_lang,
                        raw_ocr_results=raw_frags,
                        ocr_method=ocr_method,
                    )

                    if success:
                        # Clear page and insert translated image,
                        # preserving vector graphics (borders, lines)
                        page.add_redact_annot(page.rect)
                        page.apply_redactions(
                            images=pymupdf.PDF_REDACT_IMAGE_REMOVE,
                            graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
                        )
                        page.insert_image(page.rect, filename=tmp_out_path)
            finally:
                # Clean up temp files
                if tmp_png_path:
                    Path(tmp_png_path).unlink(missing_ok=True)
                if tmp_out_path:
                    Path(tmp_out_path).unlink(missing_ok=True)

            # Report progress for OCR phase
            if progress_callback:
                progress_callback(
                    int(
                        text_weight * 100
                        + ((i + 1) / total_scanned) * (1.0 - text_weight) * 100
                    ),
                )

        # Save incrementally (preserves already-translated text pages)
        doc.save(str(output_path), incremental=True, encryption=0)
    finally:
        doc.close()

    return True
