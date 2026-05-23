"""MCP server exposing AI Translate capabilities to LLM agents.

Provides text/document translation, image text extraction, audio
transcription, speech synthesis, glossary queries, and language listing
as MCP tools that any compatible client (Claude Desktop, Claude Code,
etc.) can invoke.

Usage::

    ait-mcp                     # stdio transport (default)
    ait-mcp --transport sse     # SSE transport for web clients
"""

from __future__ import annotations

import contextlib
import logging
import os
import threading
from pathlib import Path
from typing import Any

# Pre-load pymupdf before LibreOffice UNO can corrupt sys.path
# (same workaround as main.py and cli.py).
with contextlib.suppress(ImportError):
    import pymupdf  # noqa: F401

# Headless — no display needed.
if "QT_QPA_PLATFORM" not in os.environ:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"

from mcp.server.fastmcp import FastMCP

from src.constants.languages import AVAILABLE_LANGUAGES, LANGUAGES

logger = logging.getLogger("mcp_server")

# ── Server instance ────────────────────────────────────────────────

mcp = FastMCP(
    "AI Translate",
    instructions="Translate text and documents, extract text from images, "
    "transcribe audio, synthesize speech, query glossaries, and list "
    "supported languages via LLM-powered translation.",
)

# ── Bootstrap ─────────────────────────────────────────────────────
# Lazy one-time init of DB / dirs / logging (same as cli.py).

_bootstrapped = False
_bootstrap_lock = threading.Lock()


def _bootstrap() -> None:
    """Initializes app directories, logging, and the database once."""
    global _bootstrapped  # noqa: PLW0603
    if _bootstrapped:
        return

    with _bootstrap_lock:
        if _bootstrapped:
            return

        from src.core.database import init_db  # noqa: PLC0415
        from src.utils.path_manager import (  # noqa: PLC0415
            configure_logging,
            ensure_app_dirs_exist,
        )

        ensure_app_dirs_exist()
        configure_logging()
        init_db()

        # Restore the per-(endpoint, model) variant cache so MCP
        # invocations against a known reasoning model skip the variant
        # probe and go straight to the working payload on first call.
        from src.core.llm_engine import (  # noqa: PLC0415
            _load_persistent_caches,
        )

        _load_persistent_caches()
        _bootstrapped = True


# ── Validation helpers ─────────────────────────────────────────────


# Cached case-insensitive lookup: lowercased label → canonical label.
_LANG_LOWER_MAP: dict[str, str] = {lang.lower(): lang for lang in AVAILABLE_LANGUAGES}


def _validate_language(label: str, param_name: str) -> str:
    """Validates and resolves a language label case-insensitively.

    Args:
        label: Language name provided by the caller.
        param_name: Parameter name for the error message
            (e.g. "target language", "source language").

    Returns:
        The canonical language label from AVAILABLE_LANGUAGES.

    Raises:
        ValueError: If the label does not match any known language.
    """
    resolved = _LANG_LOWER_MAP.get(label.lower())
    if resolved is None:
        msg = (
            f"Unknown {param_name} '{label}'. "
            "Call list_languages to see supported values."
        )
        raise ValueError(msg)
    return resolved


def _validate_source_language(label: str) -> str:
    """Validates an optional source language label.

    Returns empty string for auto-detect, or the canonical label.
    """
    if not label:
        return ""
    return _validate_language(label, "source language")


def _require_llm() -> None:
    """Raises RuntimeError if the LLM backend is not configured."""
    from src.utils.config_manager import check_llm_setup  # noqa: PLC0415

    if not check_llm_setup():
        msg = (
            "LLM is not configured. "
            "Run the desktop app and set up your API key in Settings > LLM."
        )
        raise RuntimeError(msg)


# Map user-facing content_type strings to internal constants. Initialised
# on first call under `_content_type_lock` so concurrent SSE requests don't
# race on the lazy import.
_CONTENT_TYPE_ALIASES: dict[str, str] = {}
_content_type_lock = threading.Lock()


def _resolve_content_type(label: str) -> str:
    """Maps a user-facing content_type string to the internal constant.

    Unknown labels fall back to plain text.
    """
    if not _CONTENT_TYPE_ALIASES:
        with _content_type_lock:
            if not _CONTENT_TYPE_ALIASES:
                from src.constants.llm import (  # noqa: PLC0415
                    CONTENT_HTML,
                    CONTENT_LOCALIZATION,
                    CONTENT_MARKDOWN,
                    CONTENT_PLAIN_TEXT,
                    CONTENT_RTF,
                    CONTENT_SUBTITLE,
                    CONTENT_XML,
                )

                _CONTENT_TYPE_ALIASES.update(
                    {
                        "plain_text": CONTENT_PLAIN_TEXT,
                        "html": CONTENT_HTML,
                        "subtitle": CONTENT_SUBTITLE,
                        "markdown": CONTENT_MARKDOWN,
                        "xml": CONTENT_XML,
                        "rtf": CONTENT_RTF,
                        "localization": CONTENT_LOCALIZATION,
                        "json": CONTENT_PLAIN_TEXT,
                    }
                )

    return _CONTENT_TYPE_ALIASES.get(label.lower(), _CONTENT_TYPE_ALIASES["plain_text"])


# ── Tools ──────────────────────────────────────────────────────────


@mcp.tool()
def translate_text(  # noqa: PLR0913
    texts: list[str],
    target_language: str,
    source_language: str = "",
    content_type: str = "plain_text",
    model: str = "",
) -> list[str]:
    """Translate a list of text strings into the target language.

    Args:
        texts: One or more strings to translate.
        target_language: Target language name (e.g. "French", "Vietnamese").
            Use list_languages to see all supported values.
        source_language: Source language name, or empty string for
            auto-detection (default).
        content_type: Hint about the text format — one of "plain_text",
            "html", "subtitle", "markdown", "xml", "rtf", "json",
            "localization". Helps the LLM preserve formatting tags.
        model: LLM model to use (e.g. "Gemini:gemini-3-flash-preview").
            Defaults to the last model selected in the desktop app.

    Returns:
        Translated strings in the same order as the input.
    """
    _bootstrap()
    target = _validate_language(target_language, "target language")
    source = _validate_source_language(source_language)
    _require_llm()

    from src.utils.config_manager import (  # noqa: PLC0415
        get_available_models,
        parse_model_id,
    )

    provider: str | None = None
    model_name: str | None = None
    if model:
        # ``parse_model_id`` silently defaults to Gemini when the
        # ``Provider:model`` separator is missing — that's a footgun
        # at the public MCP surface, so reject up front.
        if ":" not in model:
            msg = (
                f"model expects 'Provider:model_name' format (got '{model}'). "
                "Available models can be listed via the desktop app's LLM tab."
            )
            raise ValueError(msg)
        provider, model_name = parse_model_id(model)
        available = get_available_models()
        if (provider, model_name) not in available:
            msg = (
                f"Model '{model}' is not available. "
                f"Available: {', '.join(f'{p}:{m}' for p, m in available)}"
            )
            raise ValueError(msg)

    from src.core.llm_engine import translate_text as _translate  # noqa: PLC0415

    return _translate(
        texts=texts,
        target_lang=target,
        source_lang=source,
        content_type=_resolve_content_type(content_type),
        provider=provider,
        model=model_name,
    )


@mcp.tool()
def extract_image_text(image_path: str) -> dict[str, Any]:
    """Extract text from an image using OCR or the configured LLM vision model.

    Tries the LLM vision provider first (Gemini / custom endpoint). Falls
    back to OCR when LLM isn't configured OR when LLM returns empty/whitespace
    text. LLM errors (auth, quota, network) propagate as-is rather than
    silently falling back — otherwise misconfiguration would be invisible
    to the caller.

    Args:
        image_path: Absolute path to an image file
            (PNG, JPG, BMP, WEBP, TIFF).

    Returns:
        A dict with:
        - "text": the full extracted text as a single string.
        - "method": "llm" or "ocr" indicating which backend was used.
        - "blocks": (OCR only) list of dicts with keys "text", "box"
            [x, y, w, h], and "confidence".

    Raises:
        RuntimeError: if neither LLM nor OCR is configured.
        ValueError: if the image format is unsupported.
        FileNotFoundError: if the image path doesn't exist.
    """
    _bootstrap()

    path = Path(image_path)
    if not path.is_file():
        msg = f"File not found: {image_path}"
        raise FileNotFoundError(msg)

    from src.constants.files import SUPPORTED_IMAGES  # noqa: PLC0415

    if path.suffix.lower() not in SUPPORTED_IMAGES:
        msg = (
            f"Unsupported image format '{path.suffix}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_IMAGES))}"
        )
        raise ValueError(msg)

    # Try LLM vision first
    from src.utils.config_manager import check_llm_setup  # noqa: PLC0415

    if check_llm_setup():
        from src.core.llm_engine import (  # noqa: PLC0415
            extract_image_text as _extract_llm,
        )

        text = _extract_llm(image_path)
        if text.strip():
            return {"text": text, "method": "llm", "blocks": []}

    # Fall back to OCR
    from src.utils.config_manager import check_ocr_setup  # noqa: PLC0415

    if check_ocr_setup():
        from src.constants.ocr import OCR_METHOD_TESSERACT  # noqa: PLC0415
        from src.constants.settings import SETTING_OCR_METHOD  # noqa: PLC0415
        from src.core.ocr_engine import run_ocr  # noqa: PLC0415
        from src.utils.config_manager import load_setting  # noqa: PLC0415

        method = load_setting(SETTING_OCR_METHOD, OCR_METHOD_TESSERACT)
        results = run_ocr(image_path, method=method)
        full_text = " ".join(r.text for r in results if r.text.strip())
        blocks = [
            {"text": r.text, "box": [r.x, r.y, r.w, r.h], "confidence": r.confidence}
            for r in results
        ]
        return {"text": full_text, "method": "ocr", "blocks": blocks}

    msg = (
        "Neither LLM nor OCR is configured. "
        "Run the desktop app and set up an API key in Settings."
    )
    raise RuntimeError(msg)


@mcp.tool()
def list_languages() -> list[dict[str, str]]:
    """List all supported languages for translation.

    Returns:
        A list of dicts, each with:
        - "locale": BCP-47 locale code (e.g. "vi", "zh-CN").
        - "name": English language name (e.g. "Vietnamese").
        - "native_name": Name in the language's own script.
    """
    return [
        {"locale": locale, "name": label, "native_name": native}
        for locale, label, _icon, native in LANGUAGES
    ]


# ── Background pipeline management ─────────────────────────────────
# Each task ID maps to the (thread, cancel_event) running for it, so
# cancel_task() can signal the right pipeline without tearing down threads
# it doesn't own.

_active_pipelines: dict[int, tuple[threading.Thread, threading.Event]] = {}
_pipelines_lock = threading.Lock()


def _run_pipeline_background(
    task_ids: list[int],
    config: object,
    cancel_event: threading.Event,
) -> None:
    """Runs the translation pipeline and cleans up tracking state.

    Called as the target of a daemon thread started by
    ``translate_document``.  Catches all exceptions so the thread
    never crashes silently.

    Args:
        task_ids: Task IDs owned by this pipeline invocation.
        config: TranslationConfig to drive the pipeline.
        cancel_event: Signalled by ``cancel_task`` to request cooperative
            shutdown.  Cancellation is checked between tasks and between
            LLM batches within a task; a mid-batch cancel lets the current
            batch finish first.
    """
    from src.core.translator import run_translation_pipeline  # noqa: PLC0415

    def _task_cancelled(task_id: int) -> bool:
        """Cancel a specific task when its entry was removed from tracking."""
        with _pipelines_lock:
            return task_id not in _active_pipelines

    try:
        run_translation_pipeline(
            config=config,
            is_cancelled=cancel_event.is_set,
            task_cancelled=_task_cancelled,
            task_ids=task_ids,
        )
    except Exception:
        logger.exception("Pipeline error for tasks %s", task_ids)
    finally:
        with _pipelines_lock:
            for tid in task_ids:
                _active_pipelines.pop(tid, None)


@mcp.tool()
def translate_document(  # noqa: PLR0913, PLR0915
    file_paths: list[str],
    target_language: str,
    source_language: str = "",
    output_directory: str = "",
    translate_images: bool = False,
    translate_comments: bool = False,
    translate_shapes: bool = False,
    translate_notes: bool = False,
    translate_sheet_names: bool = False,
    model: str = "",
    ocr_method: str = "",
) -> dict[str, Any]:
    """Translate one or more files asynchronously.

    Queues translation tasks and starts the pipeline in the background.
    Use get_task_status to poll for progress and results, and cancel_task
    to stop a running batch cooperatively.

    Args:
        file_paths: Absolute paths to files to translate. Supported
            formats include images (.png, .jpg), documents (.docx, .pdf,
            .pptx), text (.txt, .md, .html, .epub), subtitles (.srt),
            and localization files (.po, .xliff, .yaml).
        target_language: Target language name (e.g. "French", "Vietnamese").
            Use list_languages to see all supported values.
        source_language: Source language name, or empty string for
            auto-detection (default).
        output_directory: Directory for translated output files. Defaults
            to the same directory as each source file.
        translate_images: Translate embedded images in Office/PDF documents
            using OCR (requires OCR to be configured).
        translate_comments: Translate comments in Office documents.
        translate_shapes: Translate shapes and text boxes in documents.
        translate_notes: Translate speaker notes in PowerPoint files.
        translate_sheet_names: Translate sheet names in Excel files.
        model: LLM model to use (e.g. "Gemini:gemini-3-flash-preview").
            Defaults to the last model selected in the desktop app.
        ocr_method: OCR engine for translate_images. One of "TesseractOCR"
            (default), "EasyOCR", or "Google Cloud OCR". Friendly spellings
            like "tesseract" / "easyocr" / "google cloud" are accepted.

    Returns:
        A dict with:
        - "task_ids": list of integer task IDs for polling via get_task_status.
        - "file_count": number of files queued.
    """
    _bootstrap()
    target = _validate_language(target_language, "target language")
    source = _validate_source_language(source_language)
    _require_llm()

    # Validate files
    from src.constants.files import ALL_SUPPORTED_EXTENSIONS  # noqa: PLC0415

    valid_paths: list[str] = []
    for fp in file_paths:
        p = Path(fp).resolve()
        if not p.is_file():
            msg = f"File not found: {fp}"
            raise FileNotFoundError(msg)
        if p.suffix.lower() not in ALL_SUPPORTED_EXTENSIONS:
            msg = f"Unsupported file format '{p.suffix}': {fp}"
            raise ValueError(msg)
        valid_paths.append(str(p))

    # Resolve the output directory once and reuse — the pipeline writes
    # relative to storage_path, so if we only resolved for mkdir() the
    # caller's relative path would later be interpreted against whatever
    # cwd the pipeline thread happens to inherit.
    resolved_output = ""
    if output_directory:
        resolved = Path(output_directory).resolve()
        resolved.mkdir(parents=True, exist_ok=True)
        resolved_output = str(resolved)

    # Build config
    from src.constants.ocr import (  # noqa: PLC0415
        OCR_METHOD_TESSERACT,
        OCR_METHODS,
        resolve_ocr_method,
    )
    from src.core.config import TranslationConfig  # noqa: PLC0415
    from src.utils.config_manager import (  # noqa: PLC0415
        check_ocr_setup_for_method,
        get_available_models,
        parse_model_id,
    )

    llm_provider, llm_model = "", ""
    if model:
        # ``parse_model_id`` silently defaults to Gemini when the
        # ``Provider:model`` separator is missing — guard at the public
        # tool boundary so callers don't accidentally invoke a backend
        # they didn't intend.
        if ":" not in model:
            msg = (
                f"model expects 'Provider:model_name' format (got '{model}'). "
                "Available models can be listed via the desktop app's LLM tab."
            )
            raise ValueError(msg)
        llm_provider, llm_model = parse_model_id(model)
        available = get_available_models()
        if (llm_provider, llm_model) not in available:
            msg = (
                f"Model '{model}' is not available. "
                f"Available: {', '.join(f'{p}:{m}' for p, m in available)}"
            )
            raise ValueError(msg)

    resolved_ocr = OCR_METHOD_TESSERACT
    if ocr_method:
        resolved = resolve_ocr_method(ocr_method)
        if resolved is None:
            msg = (
                f"Unknown OCR method '{ocr_method}'. "
                f"Available: {', '.join(OCR_METHODS)}"
            )
            raise ValueError(msg)
        resolved_ocr = resolved

    config = TranslationConfig(
        storage_path=resolved_output,
        ocr_method=resolved_ocr,
        translate_doc_images=translate_images,
        translate_doc_comments=translate_comments,
        translate_doc_shapes=translate_shapes,
        translate_doc_notes=translate_notes,
        translate_sheet_names=translate_sheet_names,
        ocr_is_configured=(
            check_ocr_setup_for_method(resolved_ocr) if translate_images else False
        ),
        auto_remove_history=False,
        llm_provider=llm_provider,
        llm_model=llm_model,
    )

    # Clone files and create DB entries
    from src.core.translator import setup_translation_tasks  # noqa: PLC0415

    tasks = setup_translation_tasks(valid_paths, source, target)
    if not tasks:
        msg = "Failed to set up translation tasks."
        raise RuntimeError(msg)

    task_ids = [t[0] for t in tasks]

    # Run pipeline in a daemon thread with a per-batch cancel event so
    # cancel_task() can signal only this invocation's pipeline.
    cancel_event = threading.Event()
    thread = threading.Thread(
        target=_run_pipeline_background,
        args=(task_ids, config, cancel_event),
        daemon=True,
    )
    with _pipelines_lock:
        for tid in task_ids:
            _active_pipelines[tid] = (thread, cancel_event)
    thread.start()

    return {"task_ids": task_ids, "file_count": len(task_ids)}


@mcp.tool()
def get_task_status(task_ids: list[int]) -> list[dict[str, Any]]:
    """Get the current status and progress of translation tasks.

    Use this to poll tasks created by translate_document.

    Args:
        task_ids: List of task IDs returned by translate_document.

    Returns:
        A list of dicts (one per task ID), each with:
        - "task_id": the integer task ID.
        - "status": one of "Pending", "Translating", "Done", "Failed",
            "Paused", or null if the entry was auto-removed.
        - "progress": integer 0-100.
        - "file_name": original file name.
        - "source_lang": source language.
        - "target_lang": target language.
        - "error_code": integer error code (0 = no error), or null.
        - "error_message": raw error tag string preserving any
            ``:Service`` suffix (e.g. ``"AUTH_ERROR:Gemini"``),
            or null when the task hasn't failed.  The suffix names
            the backend whose API key needs attention.  Localised
            human-readable text is the client's responsibility —
            the raw tag is exposed so service-aware client UIs can
            extract the suffix or display the tag verbatim.
    """
    _bootstrap()

    from src.core.database import get_history_entry_details  # noqa: PLC0415

    # Single batch query for all requested IDs — the previous
    # per-id loop was a textbook N+1 (100 task_ids → 100 SELECTs).
    # Missing IDs come back absent from the map; we synthesise the
    # "auto-removed" sentinel record for them below.
    details = get_history_entry_details(task_ids)

    results: list[dict[str, Any]] = []
    for tid in task_ids:
        detail = details.get(tid)
        if detail is None:
            results.append(
                {
                    "task_id": tid,
                    "status": None,
                    "progress": 100,
                    "file_name": None,
                    "source_lang": None,
                    "target_lang": None,
                    "error_code": None,
                    "error_message": None,
                }
            )
        else:
            results.append(
                {
                    "task_id": detail["id"],
                    "status": detail["status"],
                    "progress": detail["progress"],
                    "file_name": detail["file_name"],
                    "source_lang": detail["source_lang"],
                    "target_lang": detail["target_lang"],
                    "error_code": detail["error_code"],
                    "error_message": detail.get("error_message"),
                }
            )
    return results


@mcp.tool()
def cancel_task(task_ids: list[int]) -> dict[str, Any]:
    """Request cancellation of translation tasks started by translate_document.

    Cancellation is cooperative: the pipeline checks the flag between tasks
    and between LLM batches, so an in-flight LLM call completes before the
    pipeline exits. Unknown task IDs are ignored — no error is raised so
    callers can safely over-request.

    Args:
        task_ids: Task IDs returned by translate_document.

    Returns:
        A dict with:
        - "cancelled": list of task IDs for which a cancel was signalled.
        - "unknown": list of task IDs that were not active (already finished,
            already cancelled, or never queued here).
    """
    _bootstrap()

    cancelled: list[int] = []
    unknown: list[int] = []
    seen_events: set[int] = set()
    ids_to_pause: set[int] = set()
    with _pipelines_lock:
        for tid in task_ids:
            entry = _active_pipelines.get(tid)
            if entry is None:
                unknown.append(tid)
                continue
            _thread, event = entry
            # Dedupe: multiple task IDs can share one pipeline thread; only
            # call set() once per event for cleanliness.
            if id(event) not in seen_events:
                event.set()
                seen_events.add(id(event))
                ids_to_pause.update(
                    active_tid
                    for active_tid, (_active_thread, active_event) in (
                        _active_pipelines.items()
                    )
                    if active_event is event
                )
            cancelled.append(tid)
    if ids_to_pause:
        from src.core.database import batch_pause_history_entries  # noqa: PLC0415

        batch_pause_history_entries(sorted(ids_to_pause))
    return {"cancelled": cancelled, "unknown": unknown}


@mcp.tool()
def transcribe_audio(
    file_path: str,
    source_language: str = "",
    stt_method: str = "Whisper",
    model_size: str = "base",
) -> dict[str, str]:
    """Transcribe an audio or video file to SRT subtitle text.

    Args:
        file_path: Absolute path to an audio or video file.
            Audio: .mp3, .wav, .m4a, .flac, .ogg, .aac, .wma.
            Video: .mp4, .webm, .mkv, .avi, .mov, .wmv.
        source_language: Source language name (e.g. "French"), or empty
            string for auto-detection (default).
        stt_method: Speech-to-text engine — "Whisper" (local, default)
            or "Google Cloud".
        model_size: Whisper model size — "tiny", "base" (default),
            "small", "medium", or "large". Ignored for Google Cloud.

    Returns:
        A dict with:
        - "srt": the generated subtitle text in SRT format.
        - "method": the STT engine used.
    """
    _bootstrap()

    path = Path(file_path).resolve()
    if not path.is_file():
        msg = f"File not found: {file_path}"
        raise FileNotFoundError(msg)

    from src.constants.files import SUPPORTED_MEDIA  # noqa: PLC0415

    if path.suffix.lower() not in SUPPORTED_MEDIA:
        msg = (
            f"Unsupported audio/video format '{path.suffix}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_MEDIA))}"
        )
        raise ValueError(msg)

    source = _validate_source_language(source_language)

    from src.constants.settings import STT_GOOGLE, STT_WHISPER  # noqa: PLC0415

    method_map = {"whisper": STT_WHISPER, "google cloud": STT_GOOGLE}
    resolved_method = method_map.get(stt_method.lower())
    if resolved_method is None:
        msg = f"Unknown STT method '{stt_method}'. Use 'Whisper' or 'Google Cloud'."
        raise ValueError(msg)

    from src.core.speech_engine import transcribe_audio as _transcribe  # noqa: PLC0415

    try:
        srt_text = _transcribe(
            str(path),
            src_lang=source,
            stt_method=resolved_method,
            model_size=model_size,
        )
    except RuntimeError as exc:
        # Re-wrap the bare engine tag into a human-readable message so MCP
        # callers don't need to know about FFMPEG_NOT_FOUND / similar
        # internal sentinels.
        if "FFMPEG_NOT_FOUND" in str(exc):
            msg = (
                "FFmpeg is required to decode this audio/video file but is "
                "not installed or not on PATH. Install FFmpeg and try again."
            )
            raise RuntimeError(msg) from exc
        raise
    return {"srt": srt_text, "method": stt_method}


@mcp.tool()
def synthesize_speech(  # noqa: PLR0913
    text: str,
    target_language: str,
    output_path: str = "",
    voice_gender: str = "FEMALE",
    tts_method: str = "Edge TTS",
    audio_format: str = ".mp3",
) -> dict[str, str]:
    """Convert text to speech audio.

    Args:
        text: The text to synthesize into speech.
        target_language: Language for the voice (e.g. "French", "Vietnamese").
            Use list_languages to see all supported values.
        output_path: Absolute path for the output audio file. If empty, a
            temp file is created under the system temp directory with a
            ``tts_`` prefix and the caller is responsible for deleting it.
        voice_gender: Voice gender — "MALE" or "FEMALE" (default).
        tts_method: TTS engine — "Edge TTS" (free, default),
            "Google Cloud TTS", "ElevenLabs", "Gemini TTS", or
            "Piper TTS" (offline; requires the per-language voice to
            be downloaded first via the desktop app's Settings →
            Voice → Piper panel, otherwise raises
            PIPER_VOICE_NOT_INSTALLED).
        audio_format: Output format — ".mp3" (default) or ".wav". The
            leading dot is optional; any other value raises ValueError.

    Returns:
        A dict with:
        - "output_path": absolute path to the generated audio file.
        - "method": the TTS engine used.
    """
    _bootstrap()

    if not text.strip():
        msg = "Text cannot be empty."
        raise ValueError(msg)

    target = _validate_language(target_language, "target language")

    # Normalise audio_format up front so the suffix used for the temp file
    # and the value sent to the backend agree.  Strip whitespace and add
    # the leading dot if the caller omitted it (e.g. ``"mp3"`` vs
    # ``".mp3"``); compare lowercased so ``"MP3"`` is accepted too.
    cleaned_format = audio_format.strip()
    normalized_format = (
        cleaned_format if cleaned_format.startswith(".") else f".{cleaned_format}"
    ).lower()
    _supported_formats = (".mp3", ".wav")
    if normalized_format not in _supported_formats:
        msg = (
            f"Unsupported audio_format '{audio_format}'. "
            f"Supported: {', '.join(_supported_formats)}"
        )
        raise ValueError(msg)

    from src.constants.settings import (  # noqa: PLC0415
        VOICE_TTS_EDGE,
        VOICE_TTS_ELEVENLABS,
        VOICE_TTS_GEMINI,
        VOICE_TTS_GOOGLE,
        VOICE_TTS_PIPER,
    )

    method_map = {
        "edge tts": VOICE_TTS_EDGE,
        "elevenlabs": VOICE_TTS_ELEVENLABS,
        "google cloud tts": VOICE_TTS_GOOGLE,
        "gemini tts": VOICE_TTS_GEMINI,
        "piper tts": VOICE_TTS_PIPER,
    }
    resolved_method = method_map.get(tts_method.lower())
    if resolved_method is None:
        msg = (
            f"Unknown TTS method '{tts_method}'. "
            "Use 'Edge TTS', 'Google Cloud TTS', 'ElevenLabs', "
            "'Gemini TTS', or 'Piper TTS'."
        )
        raise ValueError(msg)

    # Generate a temp file when no output path is specified. Caller is
    # responsible for cleanup in that case.
    if not output_path:
        import tempfile  # noqa: PLC0415

        with tempfile.NamedTemporaryFile(
            suffix=normalized_format, delete=False, prefix="tts_"
        ) as tmp:
            output_path = tmp.name

    from src.core.speech_engine import synthesize_speech as _synthesize  # noqa: PLC0415

    result_path = _synthesize(
        text=text,
        target_lang=target,
        voice_gender=voice_gender.upper(),
        output_path=output_path,
        tts_method=resolved_method,
        audio_format=normalized_format,
    )
    return {"output_path": result_path, "method": tts_method}


@mcp.tool()
def query_glossary(
    set_id: int | None = None,
    active_only: bool = True,
) -> dict[str, Any]:
    """Query glossary sets and their translation term pairs.

    Glossaries enforce consistent terminology during translation.
    When no set_id is given, returns all matching glossary sets with
    their entry counts. When set_id is given, returns that set's entries.

    Args:
        set_id: If provided, return entries for this specific glossary
            set. If omitted, return all glossary sets.
        active_only: When listing sets (no set_id), only return active
            sets if True (default). Ignored when set_id is provided.

    Returns:
        A dict with either:
        - "sets": list of {"id", "name", "is_active", "entry_count"} (when no set_id)
        - "entries": list of {"id", "source", "target"} (when set_id given)
        - "set_id": the queried set ID (when set_id given)
    """
    _bootstrap()

    from src.core.database import (  # noqa: PLC0415
        get_active_glossary_sets,
        get_glossary_entries,
        get_glossary_entry_count,
        get_glossary_sets,
    )

    if set_id is not None:
        entries = get_glossary_entries(set_id)
        return {
            "set_id": set_id,
            "entries": [
                {"id": eid, "source": src, "target": tgt} for eid, src, tgt in entries
            ],
        }

    if active_only:
        raw_sets = get_active_glossary_sets()
        sets = [
            {
                "id": sid,
                "name": name,
                "is_active": True,
                "entry_count": get_glossary_entry_count(sid),
            }
            for sid, name in raw_sets
        ]
    else:
        raw_sets = get_glossary_sets()
        sets = [
            {
                "id": sid,
                "name": name,
                "is_active": bool(active),
                "entry_count": get_glossary_entry_count(sid),
            }
            for sid, name, active in raw_sets
        ]

    return {"sets": sets}


# ── Entry point ────────────────────────────────────────────────────


def main() -> None:
    """CLI entry point for the MCP server."""
    import argparse  # noqa: PLC0415

    parser = argparse.ArgumentParser(
        prog="ait-mcp",
        description="AI Translate MCP server.",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="MCP transport (default: stdio).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for SSE transport (default: 8000).",
    )
    args = parser.parse_args()

    if args.transport == "sse":
        mcp.run(transport="sse", port=args.port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
