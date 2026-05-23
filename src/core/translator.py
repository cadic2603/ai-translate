"""Core translation logic for the AI Translate application."""

from __future__ import annotations

import dataclasses
import logging
import shutil
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.ocr_engine import OCRResult

from PySide6.QtCore import QThread, Signal

from src.constants import (
    AVAILABLE_LANGUAGES,
    OCR_METHOD_TESSERACT,
    PROGRESS_COMPLETE,
    PROGRESS_IMAGE_LLM_WEIGHT,
    PROGRESS_INITIAL,
    PROGRESS_LLM_DONE,
    PROGRESS_OCR_DONE,
    PROGRESS_TEXT_WEIGHT,
    SETTING_AUTO_CONVERT_LEGACY,
    SETTING_AUTO_CONVERT_ODF,
    SETTING_AUTO_REMOVE_HISTORY,
    SETTING_OCR_METHOD,
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_TRANSLATING,
)
from src.constants.errors import (
    ERR_FILE_NOT_FOUND,
    ERR_IMAGE_INVALID,
    ERR_LLM_API_KEY_INVALID,
    ERR_OCR_ENGINE_NOT_FOUND,
    ERR_OCR_NO_TEXT_FOUND,
    ERR_OCR_PROCESS_FAILED,
    ERR_UNKNOWN,
    map_tag_to_code,
)
from src.constants.files import SUPPORTED_IMAGES, SUPPORTED_TEXT
from src.constants.languages import get_locale_code
from src.constants.settings import SETTING_STORAGE_PATH
from src.core import llm_engine as _llm_engine
from src.core import ocr_engine as _ocr_engine
from src.core.checkpoint import (
    clear_checkpoints,
    get_storage_dir,
    load_llm_checkpoint,
    load_ocr_checkpoint,
    save_llm_checkpoint,
    save_ocr_checkpoint,
)
from src.core.config import TranslationConfig
from src.core.database import (
    add_history_entry,
    db_transaction,
    delete_history_entry,
    get_active_glossary_sets,
    get_glossary_entries,
    get_history_entry_status,
    get_unfinished_history,
    update_history_file_name,
    update_history_progress,
    update_history_status,
)
from src.core.image_processor import process_image_translation
from src.core.layout_analysis import merge_to_paragraphs
from src.core.office_lifecycle import stop_soffice
from src.core.office_processor import (
    LEGACY_CONVERT_MAP,
    ODF_CONVERT_MAP,
    convert_to_modern_format,
)
from src.core.text_processor import translate_file
from src.utils import path_manager as _path_manager
from src.utils.config_manager import load_setting
from src.utils.file_utils import wipe_history_directory

logger = logging.getLogger("translator")


# ---------------------------------------------------------------------------
# Pure-Python helpers (no PySide6 dependency)
# ---------------------------------------------------------------------------


def _resolve_output_dir(
    config: TranslationConfig | None = None,
    *,
    source_path: Path | None = None,
) -> Path:
    """Resolves the output directory for translated files.

    Priority:
      1. User-configured storage path (from config or settings).
      2. Original source file's parent directory (if it still exists).
      3. Desktop folder as a last-resort fallback.

    Args:
        config: Optional config snapshot; falls back to load_setting().
        source_path: Original source file path before cloning.

    Returns:
        Path: The resolved output directory.
    """
    if config is not None:
        output_dir_str = config.storage_path
    else:
        output_dir_str = load_setting(SETTING_STORAGE_PATH, "")
    if output_dir_str:
        return Path(output_dir_str)

    # Fall back to original source file's directory
    if source_path is not None and source_path.parent.exists():
        return source_path.parent

    from src.utils.path_manager import get_desktop_path  # noqa: PLC0415

    return get_desktop_path()


def _fetch_all_glossary_entries() -> list[tuple[int, str, str]]:
    """Collects glossary entries from all active glossary sets.

    Returns:
        list[tuple[int, str, str]]: Flat list of (id, source, target)
        tuples from every active glossary set.
    """
    entries: list[tuple[int, str, str]] = []
    for set_id, _name in get_active_glossary_sets():
        entries.extend(get_glossary_entries(set_id))
    return entries


@db_transaction
def _update_storage_path(cursor: sqlite3.Cursor, h_id: int, path: str) -> None:
    """Updates the storage_path column for a history entry."""
    cursor.execute(
        "UPDATE history SET storage_path = ? WHERE id = ?",
        (path, h_id),
    )


def _map_error_to_code(msg: str) -> int:
    """Maps an error message string to a standardized error code.

    Args:
        msg: The exception message string.

    Returns:
        int: The corresponding error code constant.
    """
    return map_tag_to_code(msg)


def _build_output_name(file_path: Path, src_lang: str, target_lang: str) -> str:
    """Builds the translated output filename.

    Format: ``{stem}_translated_{src_locale}_{target_locale}{suffix}``
    e.g. ``report_translated_en-US_vi.docx``.

    Args:
        file_path: Original source file path.
        src_lang: Source language label (e.g. "English (US)").
        target_lang: Target language label (e.g. "Vietnamese").

    Returns:
        The formatted output filename string.
    """
    src_code = get_locale_code(src_lang)
    tgt_code = get_locale_code(target_lang)
    return f"{file_path.stem}_translated_{src_code}_{tgt_code}{file_path.suffix}"


def _get_unique_path(target_path: Path) -> Path:
    """Returns a unique path by appending a numeric suffix if the file exists."""
    if not target_path.exists():
        return target_path

    base = target_path.stem
    suffix = target_path.suffix
    directory = target_path.parent
    counter = 1

    while True:
        new_path = directory / f"{base}_{counter}{suffix}"
        if not new_path.exists():
            return new_path
        counter += 1


# ---------------------------------------------------------------------------
# Pipeline step functions (pure Python — no PySide6 dependency)
# ---------------------------------------------------------------------------


def _pipeline_run_ocr(
    h_id: int,
    file_path: Path,
    src_lang: str = "",
    config: TranslationConfig | None = None,
) -> tuple[list[OCRResult], list[OCRResult], str] | None:
    """Runs OCR and returns results, or None on failure.

    Args:
        h_id: The history entry ID.
        file_path: Path to the image file.
        src_lang: Source language label for OCR language selection.
        config: Optional config snapshot; falls back to load_setting().

    Returns:
        Tuple of (ocr_results, raw_ocr_results, ocr_method) or None.
    """
    try:
        if config is not None:
            ocr_method = config.ocr_method
        else:
            ocr_method = load_setting(SETTING_OCR_METHOD, OCR_METHOD_TESSERACT)
        ocr_results = _ocr_engine.run_ocr(
            str(file_path),
            method=ocr_method,
            src_lang=src_lang,
        )
        return ocr_results, list(ocr_results), ocr_method
    except (ImportError, RuntimeError):
        update_history_status(h_id, STATUS_FAILED, error_code=ERR_OCR_ENGINE_NOT_FOUND)
    except Exception as e:
        msg = str(e)
        is_auth = "AUTH_ERROR" in msg
        code = ERR_LLM_API_KEY_INVALID if is_auth else ERR_OCR_PROCESS_FAILED
        # Persist the raw tag so the UI can render the service-specific
        # copy ("Invalid Google Cloud API key") via display_error_message,
        # not just the generic message derived from ``code`` alone.
        update_history_status(
            h_id,
            STATUS_FAILED,
            error_code=code,
            error_message=msg,
        )
    return None


def _pipeline_run_llm(  # noqa: PLR0913
    h_id: int,
    file_path: Path,
    ocr_data: tuple[list[OCRResult], list[OCRResult], str],
    src_lang: str,
    target_lang: str,
    *,
    provider: str | None = None,
    model: str | None = None,
) -> tuple[list[OCRResult], list[str], list[OCRResult]] | None:
    """Runs LLM translation + paragraph merge, or None on failure.

    Args:
        h_id: The history entry ID.
        file_path: Path to the image file.
        ocr_data: (ocr_results, raw_ocr_results, ocr_method) from OCR step.
        src_lang: Source language.
        target_lang: Target language.
        provider: Optional LLM provider override.
        model: Optional LLM model override.

    Returns:
        Tuple of (ocr_results, translations, raw_fragments) or None.
    """
    ocr_results, raw_ocr_results, ocr_method = ocr_data

    def update_llm_progress(p: int, h_id: int = h_id) -> None:
        update_history_progress(
            h_id, PROGRESS_OCR_DONE + int(p * PROGRESS_IMAGE_LLM_WEIGHT)
        )

    try:
        all_glossary_entries = _fetch_all_glossary_entries()

        paragraph_data = _llm_engine.translate_image_content(
            str(file_path),
            ocr_results,
            target_lang,
            src_lang,
            progress_callback=update_llm_progress,
            glossary_entries=all_glossary_entries,
            provider=provider,
            model=model,
        )

        return merge_to_paragraphs(paragraph_data, raw_ocr_results, ocr_method)
    except Exception as e:
        msg = str(e)
        logger.error("Translation step failed: %s", msg)
        update_history_status(
            h_id,
            STATUS_FAILED,
            error_code=_map_error_to_code(msg),
            error_message=msg,
        )
    return None


def _pipeline_process_image(  # noqa: PLR0912, PLR0913
    h_id: int,
    file_path: Path,
    src_lang: str,
    target_lang: str,
    config: TranslationConfig | None = None,
    cancel_check: Callable[[int], bool] | None = None,
    *,
    source_path: Path | None = None,
) -> None:
    """Runs the full image translation pipeline: OCR → LLM → merge → render.

    Checks for checkpoints from a previous run so expensive stages
    (OCR, LLM) can be skipped on resume.  Checks for cancellation
    (e.g. user pause) between each stage.

    Args:
        h_id: The history entry ID.
        file_path: Path to the image file.
        src_lang: Source language.
        target_lang: Target language.
        config: Optional config snapshot; falls back to load_setting().
        cancel_check: Callable taking h_id, returns True if cancelled.
        source_path: Original source file path for output directory fallback.
    """
    storage_dir = get_storage_dir(str(file_path))

    # Try to resume from LLM checkpoint (skips both OCR and LLM)
    llm_saved = load_llm_checkpoint(storage_dir)
    if llm_saved:
        ocr_results, translations, confirmed_raw_fragments = llm_saved
        logger.info("Resumed task %d from LLM checkpoint", h_id)
        update_history_progress(h_id, PROGRESS_LLM_DONE)
    else:
        # Try to resume from OCR checkpoint (skips OCR only)
        ocr_saved = load_ocr_checkpoint(storage_dir)
        if ocr_saved:
            ocr_data = ocr_saved
            logger.info("Resumed task %d from OCR checkpoint", h_id)
        else:
            # 1. Run OCR from scratch
            ocr_data = _pipeline_run_ocr(h_id, file_path, src_lang, config)
            if ocr_data is None:
                return
            # Save OCR checkpoint for future resume
            save_ocr_checkpoint(
                storage_dir,
                ocr_data[0],
                ocr_data[1],
                ocr_data[2],
            )

        update_history_progress(h_id, PROGRESS_OCR_DONE)

        if not ocr_data[0]:
            clear_checkpoints(storage_dir)
            update_history_status(h_id, STATUS_FAILED, error_code=ERR_OCR_NO_TEXT_FOUND)
            return

        # Check cancellation between OCR and LLM steps
        if cancel_check and cancel_check(h_id):
            return

        # 2. Enriched Translate content (Text + Style + Alignment)
        llm_data = _pipeline_run_llm(
            h_id,
            file_path,
            ocr_data,
            src_lang,
            target_lang,
            provider=(config.llm_provider or None) if config else None,
            model=(config.llm_model or None) if config else None,
        )
        if llm_data is None:
            return
        ocr_results, translations, confirmed_raw_fragments = llm_data
        update_history_progress(h_id, PROGRESS_LLM_DONE)

        # Save LLM checkpoint for future resume
        save_llm_checkpoint(
            storage_dir,
            ocr_results,
            translations,
            confirmed_raw_fragments,
        )

    # Check cancellation between LLM and render steps
    if cancel_check and cancel_check(h_id):
        return

    # 3. Image processing (Remove text & Insert translation)
    output_dir = _resolve_output_dir(config, source_path=source_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_name = _build_output_name(file_path, src_lang, target_lang)
    output_path = _get_unique_path(output_dir / output_name)

    success = process_image_translation(
        str(file_path),
        str(output_path),
        ocr_results,
        translations,
        target_lang=target_lang,
        raw_ocr_results=confirmed_raw_fragments,
    )

    if success:
        update_history_progress(h_id, PROGRESS_COMPLETE)
        clear_checkpoints(storage_dir)
        _pipeline_finalize(h_id, config)
    else:
        update_history_status(h_id, STATUS_FAILED, error_code=ERR_IMAGE_INVALID)


def _pipeline_process_text(  # noqa: PLR0913
    h_id: int,
    file_path: Path,
    src_lang: str,
    target_lang: str,
    config: TranslationConfig | None = None,
    cancel_check: Callable[[int], bool] | None = None,
    *,
    source_path: Path | None = None,
) -> None:
    """Runs the full text file translation pipeline: read → LLM → write.

    Computes the output path, fetches glossary entries, and delegates
    to the text_processor module for format-specific handling.
    Passes the storage directory for per-chunk/batch checkpointing.

    Args:
        h_id: The history entry ID.
        file_path: Path to the cloned text file.
        src_lang: Source language.
        target_lang: Target language.
        config: Optional config snapshot; falls back to load_setting().
        cancel_check: Callable taking h_id, returns True if cancelled.
        source_path: Original source file path for output directory fallback.
    """
    # 0. Pre-convert legacy/ODF to modern format if enabled
    suffix = file_path.suffix.lower()
    modern_suffix = None
    auto_legacy = (
        config.auto_convert_legacy
        if config is not None
        else load_setting(SETTING_AUTO_CONVERT_LEGACY, False)
    )
    auto_odf = (
        config.auto_convert_odf
        if config is not None
        else load_setting(SETTING_AUTO_CONVERT_ODF, False)
    )
    if auto_legacy and suffix in LEGACY_CONVERT_MAP:
        modern_suffix = LEGACY_CONVERT_MAP[suffix]
    elif auto_odf and suffix in ODF_CONVERT_MAP:
        modern_suffix = ODF_CONVERT_MAP[suffix]

    if modern_suffix:
        modern_path = file_path.with_suffix(modern_suffix)
        if convert_to_modern_format(file_path, modern_path):
            original_name = file_path.name
            file_path.unlink(missing_ok=True)
            file_path = modern_path
            _update_storage_path(h_id, str(modern_path.resolve()))
            # Update the DB filename to reflect the modern extension.
            update_history_file_name(h_id, modern_path.name)
            logger.info(
                "Pre-converted %s → %s",
                original_name,
                modern_path.name,
            )
        else:
            logger.warning(
                "Pre-conversion failed for %s, translating in original format",
                file_path.name,
            )

    storage_dir = get_storage_dir(str(file_path))

    # 1. Determine output path
    output_dir = _resolve_output_dir(config, source_path=source_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_name = _build_output_name(file_path, src_lang, target_lang)
    output_path = _get_unique_path(output_dir / output_name)

    # 2. Fetch active glossary entries
    all_glossary_entries = _fetch_all_glossary_entries()

    # 3. Progress callback: maps text_processor's 0-100 to history's 10-90
    def update_text_progress(p: int, _hid: int = h_id) -> None:
        update_history_progress(_hid, PROGRESS_INITIAL + int(p * PROGRESS_TEXT_WEIGHT))

    # 4. Cancel check: wraps the provided cancel_check for text_processor
    def _cancel() -> bool:
        return cancel_check(h_id) if cancel_check else False

    try:
        success = translate_file(
            file_path,
            output_path,
            target_lang,
            src_lang,
            progress_callback=update_text_progress,
            glossary_entries=all_glossary_entries or None,
            cancel_check=_cancel,
            checkpoint_dir=storage_dir,
            config=config,
            provider=(config.llm_provider or None) if config else None,
            model=(config.llm_model or None) if config else None,
        )

        if success:
            update_history_progress(h_id, PROGRESS_COMPLETE)
            clear_checkpoints(storage_dir)
            _pipeline_finalize(h_id, config)
        else:
            # Cancelled by user (pause/delete)
            logger.info("Text task %d was cancelled", h_id)
    except Exception as e:
        msg = str(e)
        logger.error(
            "Text translation failed for task %d: %s", h_id, msg, exc_info=True
        )
        update_history_status(
            h_id,
            STATUS_FAILED,
            error_code=_map_error_to_code(msg),
            error_message=msg,
        )


def _pipeline_finalize(
    h_id: int,
    config: TranslationConfig | None = None,
) -> None:
    """Finalizes a translation task based on user settings.

    Args:
        h_id: The history entry ID.
        config: Optional config snapshot; falls back to load_setting().
    """
    final_status = get_history_entry_status(h_id)
    if final_status not in (STATUS_TRANSLATING, STATUS_FAILED):
        return

    auto_remove = (
        config.auto_remove_history
        if config is not None
        else load_setting(SETTING_AUTO_REMOVE_HISTORY, False)
    )
    if auto_remove and final_status != STATUS_FAILED:
        storage_path = delete_history_entry(h_id)
        if storage_path:
            wipe_history_directory(storage_path)
    elif final_status == STATUS_TRANSLATING:
        update_history_status(h_id, STATUS_DONE)


# ---------------------------------------------------------------------------
# Top-level pipeline entry point (pure Python — no PySide6 dependency)
# ---------------------------------------------------------------------------


def run_translation_pipeline(  # noqa: PLR0912, PLR0913
    config: TranslationConfig,
    is_cancelled: Callable[[], bool] | None = None,
    task_cancelled: Callable[[int], bool] | None = None,
    task_ids: list[int] | tuple[int, ...] | None = None,
    model_setting_key: str = "",
) -> None:
    """Pure-Python translation loop. No PySide6 dependency.

    Fetches pending tasks from DB, processes them sequentially.
    Suitable for CLI, MCP server, REST API, or any headless caller.

    Args:
        config: Frozen snapshot of translation settings.
        is_cancelled: Returns True when the overall pipeline should stop.
        task_cancelled: Returns True when a specific task (by h_id) is
            cancelled (e.g. user paused it).
        task_ids: Optional set of history IDs this invocation owns. When
            provided, the loop ignores unrelated pending work.
        model_setting_key: Optional per-feature LLM model setting key.
            When provided, the loop re-reads it before each task so a
            mid-run model change (e.g. user picks a new model in the
            Re-translate dialog) takes effect on the next queued task
            without waiting for the current worker to exit.
    """
    scoped_task_ids = tuple(task_ids) if task_ids is not None else None
    try:
        while True:
            # Respect global cancellation
            if is_cancelled and is_cancelled():
                break

            # Refresh the LLM model from settings so a re-translate that
            # picks a different model after this worker started actually
            # takes effect on the next task instead of inheriting the
            # snapshot from worker construction.  Only the LLM fields
            # are refreshed; everything else (storage path, glossary,
            # OCR config) stays snapshotted.
            if model_setting_key:
                from src.utils.config_manager import (  # noqa: PLC0415
                    load_model_for_feature,
                    parse_model_id,
                )

                fresh_model = load_model_for_feature(model_setting_key)
                if fresh_model:
                    fresh_provider, fresh_name = parse_model_id(fresh_model)
                    if (
                        fresh_provider != config.llm_provider
                        or fresh_name != config.llm_model
                    ):
                        logger.info(
                            "Pipeline picking up live model change: %s/%s -> %s/%s",
                            config.llm_provider,
                            config.llm_model,
                            fresh_provider,
                            fresh_name,
                        )
                        config = dataclasses.replace(
                            config,
                            llm_provider=fresh_provider,
                            llm_model=fresh_name,
                        )

            # Fetch next pending task from DB
            pending_tasks = get_unfinished_history(
                statuses=(STATUS_PENDING, STATUS_TRANSLATING),
                task_ids=scoped_task_ids,
            )
            if not pending_tasks:
                break

            h_id, storage_path, src_lang, target_lang, source_path_str = pending_tasks[
                0
            ]

            try:
                # Clean path if somehow corrupted with '@'
                if isinstance(storage_path, str):
                    storage_path = storage_path.lstrip("@")

                file_path = Path(storage_path)
                if not file_path.exists():
                    update_history_status(
                        h_id, STATUS_FAILED, error_code=ERR_FILE_NOT_FOUND
                    )
                    continue

                # Resolve original source path for output directory fallback
                source_path = Path(source_path_str) if source_path_str else None

                # Mark as translating
                update_history_status(h_id, STATUS_TRANSLATING)
                update_history_progress(h_id, PROGRESS_INITIAL)

                logger.info(
                    "Translating task %d (%s) with %s/%s",
                    h_id,
                    file_path.name,
                    config.llm_provider or "default",
                    config.llm_model or "default",
                )

                suffix = file_path.suffix.lower()

                # Build a per-task cancel_check that also respects global cancellation
                def _task_cancel(hid: int) -> bool:
                    if is_cancelled and is_cancelled():
                        return True
                    if task_cancelled:
                        return task_cancelled(hid)
                    return False

                if suffix in SUPPORTED_IMAGES:
                    _pipeline_process_image(
                        h_id,
                        file_path,
                        src_lang,
                        target_lang,
                        config,
                        _task_cancel,
                        source_path=source_path,
                    )
                elif suffix in SUPPORTED_TEXT:
                    _pipeline_process_text(
                        h_id,
                        file_path,
                        src_lang,
                        target_lang,
                        config,
                        _task_cancel,
                        source_path=source_path,
                    )
                else:
                    logger.warning("Unsupported file format: %s", suffix)
                    update_history_status(h_id, STATUS_FAILED, error_code=ERR_UNKNOWN)

            except MemoryError:
                logger.critical(
                    "MemoryError while processing task %d",
                    h_id,
                )
                update_history_status(
                    h_id,
                    STATUS_FAILED,
                    error_code=ERR_UNKNOWN,
                )
            except Exception as e:
                logger.error("Error processing task %d: %s", h_id, e)
                update_history_status(h_id, STATUS_FAILED, error_code=ERR_UNKNOWN)
    finally:
        # Always stop soffice so the user can open files in LibreOffice GUI.
        # Using finally ensures cleanup even on KeyboardInterrupt / SystemExit.
        stop_soffice()


# ---------------------------------------------------------------------------
# QThread wrapper (PySide6 — thin delegation to pure pipeline)
# ---------------------------------------------------------------------------


class TranslationWorker(QThread):
    """Worker thread for processing translation tasks.

    Thin QThread wrapper that delegates to ``run_translation_pipeline()``.
    Only one instance can run at a time.
    """

    finished = Signal()
    _is_any_worker_running = False  # Class-level flag

    def __init__(
        self,
        tasks: list[tuple[int, str, str, str]],
        config: TranslationConfig | None = None,
    ) -> None:
        """Initializes the TranslationWorker.

        Args:
            tasks: List of (h_id, storage_path, src_lang, target_lang).
            config: Optional config snapshot; when None, from_settings()
                    is called at the start of run().
        """
        super().__init__()
        self.tasks = tasks
        self._is_running = True
        self._config = config

    @classmethod
    def is_busy(cls) -> bool:
        """Checks if a translation worker is already running."""
        return cls._is_any_worker_running

    def stop(self) -> None:
        """Signals the worker to stop processing."""
        self._is_running = False

    def _is_cancelled(self, h_id: int) -> bool:
        """Checks if a task was paused or deleted while in progress.

        Reads the current DB status; returns True if it is no longer
        'Translating' (e.g. user clicked Pause).
        """
        if not self._is_running:
            return True
        status = get_history_entry_status(h_id)
        return status != STATUS_TRANSLATING

    def run(self) -> None:
        """Processes queued translation tasks for already cloned files."""
        if TranslationWorker._is_any_worker_running:
            return

        TranslationWorker._is_any_worker_running = True
        try:
            from src.constants.settings import (  # noqa: PLC0415
                SETTING_LLM_MODEL_TRANSLATE_DOCUMENT,
            )

            config = self._config or TranslationConfig.from_settings(
                model_setting_key=SETTING_LLM_MODEL_TRANSLATE_DOCUMENT,
            )
            # Pass the same key into the pipeline so a mid-run model
            # change (Re-translate dialog) is picked up before the next
            # task instead of waiting for this worker to exit.  Workers
            # constructed with an explicit `_config` snapshot opt out of
            # the refresh — they want their snapshot honoured exactly.
            refresh_key = (
                "" if self._config is not None else SETTING_LLM_MODEL_TRANSLATE_DOCUMENT
            )
            run_translation_pipeline(
                config=config,
                is_cancelled=lambda: not self._is_running,
                task_cancelled=self._is_cancelled,
                model_setting_key=refresh_key,
            )
        finally:
            TranslationWorker._is_any_worker_running = False
            self.finished.emit()


# ---------------------------------------------------------------------------
# Task setup & resume helpers
# ---------------------------------------------------------------------------


def setup_translation_tasks(
    file_paths: list[str], src_lang: str, target_lang: str
) -> list[tuple[int, str, str, str]]:
    """Creates DB entries and clones files to storage for a set of translation tasks.

    Args:
        file_paths: List of absolute paths to files to translate.
        src_lang: Source language name.
        target_lang: Target language name.

    Returns:
        list: List of (history_id, storage_path, src_lang, target_lang) tuples.
    """
    base_dir = _path_manager.get_app_data_dir() / "translations"
    base_dir.mkdir(parents=True, exist_ok=True)

    tasks = []
    for file_path in file_paths:
        p = Path(file_path)
        file_name = p.name
        try:
            f_size = p.stat().st_size
        except OSError:
            f_size = 0

        # Create DB record
        h_id = add_history_entry(
            file_name,
            src_lang,
            target_lang,
            STATUS_PENDING,
            source_path=str(p.absolute()),
            file_size=f_size,
        )

        if h_id:
            # Create folder named by ID and clone file
            storage_dir = base_dir / str(h_id)
            storage_dir.mkdir(parents=True, exist_ok=True)
            dest_path = storage_dir / file_name
            try:
                shutil.copy2(file_path, dest_path)
                storage_full_path = str(dest_path.absolute())
                _update_storage_path(h_id, storage_full_path)
                tasks.append((h_id, storage_full_path, src_lang, target_lang))
            except Exception as e:
                logger.error("Error cloning file %s: %s", file_name, e)
                update_history_status(h_id, STATUS_FAILED, error_code=ERR_UNKNOWN)

    return tasks


def resume_unfinished_translations(
    statuses: tuple[str, ...] = (STATUS_PENDING, STATUS_TRANSLATING),
    config: TranslationConfig | None = None,
) -> TranslationWorker | None:
    """Resumes unfinished translation tasks from the database.

    Args:
        statuses: Tuple of status strings to filter unfinished tasks.
        config: Optional config snapshot; forwarded to TranslationWorker.
    """
    unfinished = get_unfinished_history(statuses=statuses)
    if not unfinished:
        return None

    worker = TranslationWorker(unfinished, config=config)
    worker.start()
    return worker


def get_available_languages() -> list[str]:
    """Returns a list of supported languages for translation.

    Returns:
        List[str]: A list of language names.
    """
    return AVAILABLE_LANGUAGES
