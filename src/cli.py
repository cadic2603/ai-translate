"""Command-line interface for AI Translate.

Translates files using the same LLM-powered pipeline as the desktop app,
without requiring a graphical display.

Usage::

    ait report.docx --target French
    ait *.pdf --target Japanese --source "English (US)"
    ait image.png --target Vietnamese --output ./out/

Note: shell glob patterns like ``*.pdf`` are expanded by the shell on Unix
but not by Windows ``cmd.exe``. On Windows, list files explicitly or use
PowerShell's ``Get-ChildItem`` piping.
"""

from __future__ import annotations

import argparse
import contextlib
import logging
import os
import signal
import sys
import threading
from pathlib import Path

# Pre-load pymupdf before LibreOffice UNO can corrupt sys.path
# (same workaround as src/main.py — see comment there).
with contextlib.suppress(ImportError):
    import pymupdf  # noqa: F401

# Force offscreen Qt platform so PySide6 imports (pulled in transitively
# by the translation pipeline for image rendering) don't try to open a
# display connection on headless servers.
if "QT_QPA_PLATFORM" not in os.environ:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"

from src.constants.files import ALL_SUPPORTED_EXTENSIONS
from src.constants.languages import AVAILABLE_LANGUAGES

# ── Exit codes ──────────────────────────────────────────────────────

EXIT_OK = 0
EXIT_ARGS_ERROR = 2
EXIT_SETUP_ERROR = 3
EXIT_PARTIAL_FAILURE = 4
EXIT_ALL_FAILED = 5
EXIT_INTERRUPTED = 130


# ── Console logging polish ──────────────────────────────────────────
#
# Maps internal error tags raised by the translation pipeline to a
# human-friendly one-line message. Keeps CLI output readable when a
# backend fails.
_FRIENDLY_ERROR_MESSAGES: dict[str, str] = {
    "QUOTA_ERROR": "API quota exceeded — try again later or upgrade your plan.",
    "AUTH_ERROR": "API authentication failed — check your API key in settings.",
    "TIMEOUT_ERROR": "Request timed out — check your internet connection.",
    "CONNECTION_ERROR": "Could not reach the translation API.",
    "SERVICE_UNAVAILABLE_ERROR": "Translation API is temporarily unavailable.",
    "RATE_LIMIT_ERROR": "API rate limit reached — retry automatically.",
    "VISION_NOT_SUPPORTED": "This model doesn't support image translation.",
    "INVALID_REQUEST_ERROR": "The translation request was rejected by the API.",
    "INVALID_RESPONSE_ERROR": "The API returned an unexpected response.",
    "CANCELLED": "Translation was cancelled.",
}
# Max characters of an ERROR message to keep on the console before we
# strip the trailing "Body: {...}" dump (full payload still goes to
# app.log via the file handler).
_CLI_CONSOLE_MESSAGE_LIMIT = 240


class _CliConsoleFilter(logging.Filter):
    """Trims noisy log records before they reach the CLI console.

    Keeps the full record intact for the file handler — this filter is
    only installed on the console StreamHandler — while doing three
    things to the message seen by the user:

    * Drops tracebacks (``exc_info`` / ``exc_text``) unless ``--verbose``.
    * Replaces known error-tag messages (e.g. ``QUOTA_ERROR``) with a
      friendly one-line explanation.
    * Truncates "Body: {...}" dumps after a reasonable length.
    """

    def __init__(self, *, verbose: bool) -> None:
        """Stores the verbosity flag; behaviour is per-record in ``filter``."""
        super().__init__()
        self._verbose = verbose

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003 (stdlib name)
        """Always returns True — we mutate the record in place for display."""
        if self._verbose:
            return True

        # Tracebacks stay in app.log; drop them on the console.
        record.exc_info = None
        record.exc_text = None

        message = record.getMessage()

        # Map well-known error tags to friendly text.
        for tag, friendly in _FRIENDLY_ERROR_MESSAGES.items():
            if tag in message:
                record.msg = friendly
                record.args = None
                return True

        # Truncate giant HTTP body dumps.
        if "Body:" in message and len(message) > _CLI_CONSOLE_MESSAGE_LIMIT:
            record.msg = (
                message.split("Body:", 1)[0].rstrip() + "  (full body in app.log)"
            )
            record.args = None
        return True


def _install_cli_console_filter(*, verbose: bool) -> None:
    """Installs :class:`_CliConsoleFilter` on every non-file handler."""
    root = logging.getLogger()
    for handler in root.handlers:
        # File handlers get the full, unfiltered record. Everything else
        # (typically a console StreamHandler) gets the polished view.
        if isinstance(handler, logging.FileHandler):
            continue
        if isinstance(handler, logging.StreamHandler):
            handler.addFilter(_CliConsoleFilter(verbose=verbose))


# ── Argument parser ─────────────────────────────────────────────────


def _get_app_version() -> str:
    """Returns the installed package version, or 'unknown' if not packaged."""
    from importlib.metadata import PackageNotFoundError, version  # noqa: PLC0415

    try:
        return version("ai-translate")
    except PackageNotFoundError:
        return "unknown"


def _build_parser() -> argparse.ArgumentParser:
    """Builds the argument parser."""
    parser = argparse.ArgumentParser(
        prog="ait",
        description="Translate files using AI (LLM-powered translation).",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {_get_app_version()}",
    )
    parser.add_argument(
        "files",
        nargs="*",
        type=Path,
        help="One or more input files to translate.",
    )
    parser.add_argument(
        "--target",
        "-t",
        default=None,
        metavar="LANG",
        help="Target language (e.g. 'French', 'Vietnamese', 'Chinese (Simplified)').",
    )
    parser.add_argument(
        "--source",
        "-s",
        default="",
        metavar="LANG",
        help="Source language (default: auto-detect).",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        metavar="DIR",
        help="Output directory (default: same directory as source file).",
    )

    # ── Translation options ──
    parser.add_argument(
        "--translate-images",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Translate embedded images in documents (requires OCR).",
    )
    parser.add_argument(
        "--translate-comments",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Translate comments in Office documents.",
    )
    parser.add_argument(
        "--translate-shapes",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Translate shapes and text boxes in documents.",
    )
    parser.add_argument(
        "--translate-notes",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Translate speaker notes in PowerPoint files.",
    )
    parser.add_argument(
        "--translate-sheet-names",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Translate sheet names in Excel files.",
    )
    parser.add_argument(
        "--ocr-method",
        default=None,
        metavar="METHOD",
        help="OCR engine: Tesseract, EasyOCR, or 'Google Cloud OCR'.",
    )
    parser.add_argument(
        "--convert-legacy",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Pre-convert .doc/.xls/.ppt to modern formats before translation.",
    )
    parser.add_argument(
        "--convert-odf",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Pre-convert .odt/.ods/.odp to OOXML before translation.",
    )
    parser.add_argument(
        "--keep-history",
        action="store_true",
        default=False,
        help="Keep translation history entries after completion.",
    )
    parser.add_argument(
        "--model",
        "-m",
        default=None,
        metavar="MODEL",
        help=(
            "LLM model to use (e.g. 'Gemini:gemini-3-flash-preview'). "
            "Defaults to the last model selected in the desktop app."
        ),
    )

    # ── Output control ──
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress progress output (errors only).",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable debug logging.",
    )
    parser.add_argument(
        "--list-languages",
        action="store_true",
        help="Print all supported languages and exit.",
    )
    return parser


# ── Validation helpers ──────────────────────────────────────────────


def _resolve_language(label: str) -> str | None:
    """Resolves a language label case-insensitively.

    Returns the canonical label from AVAILABLE_LANGUAGES, or None if no
    match is found.  An empty / whitespace-only string is treated as
    auto-detect (returned as ``""``) — a shell-quoted ``--source " "``
    is almost certainly user shorthand for "let the engine pick", not
    an attempt to translate from a language literally named " ".
    """
    stripped = label.strip() if label else ""
    if not stripped:
        return ""
    lower_map = {lang.lower(): lang for lang in AVAILABLE_LANGUAGES}
    return lower_map.get(stripped.lower())


def _suggest_language_matches(label: str) -> list[str]:
    """Returns canonical languages that contain *label* as a substring.

    Used to print a friendly hint for ambiguous input like ``"Chinese"``
    where multiple variants (Simplified / Traditional) exist.  An
    empty / whitespace-only label returns an empty list rather than
    every language — a "did you mean: ..." hint with every supported
    language attached would drown the user.
    """
    stripped = label.strip() if label else ""
    if not stripped:
        return []
    lower = stripped.lower()
    return [lang for lang in AVAILABLE_LANGUAGES if lower in lang.lower()]


def _resolve_ocr_method(label: str) -> str | None:
    """Thin wrapper around :func:`src.constants.ocr.resolve_ocr_method`.

    Kept as an underscore-prefixed name so existing tests targeting
    ``src.cli._resolve_ocr_method`` continue to work.
    """
    from src.constants.ocr import resolve_ocr_method  # noqa: PLC0415

    return resolve_ocr_method(label)


def _validate_files(paths: list[Path]) -> list[Path]:
    """Filters input paths to those that exist and are supported.

    Prints warnings for skipped files to stderr.
    """
    valid: list[Path] = []
    for p in paths:
        resolved = p.resolve()
        if not resolved.is_file():
            print(f"Warning: skipping (not found): {p}", file=sys.stderr)
            continue
        if resolved.suffix.lower() not in ALL_SUPPORTED_EXTENSIONS:
            print(
                f"Warning: skipping (unsupported type '{resolved.suffix}'): {p}",
                file=sys.stderr,
            )
            continue
        valid.append(resolved)
    return valid


# ── Progress reporter ───────────────────────────────────────────────


def _progress_reporter(
    task_ids: list[int],
    stop_event: threading.Event,
) -> None:
    """Polls the DB for task status and prints progress to stdout.

    Runs in a daemon thread; stops when *stop_event* is set.
    """
    from src.constants.history import STATUS_DONE, STATUS_FAILED  # noqa: PLC0415
    from src.core.database import get_history_entry_status  # noqa: PLC0415

    completed: set[int] = set()
    while not stop_event.is_set():
        for h_id in task_ids:
            if h_id in completed:
                continue
            status = get_history_entry_status(h_id)
            if status == STATUS_DONE:
                print(f"  [OK]   Task {h_id}: Done")
                completed.add(h_id)
            elif status == STATUS_FAILED:
                print(f"  [FAIL] Task {h_id}: Failed")
                completed.add(h_id)
            elif status is None:
                # auto_remove_history deleted the entry → treat as done
                completed.add(h_id)
        if len(completed) >= len(task_ids):
            break
        stop_event.wait(timeout=1.0)


# ── Entry point ─────────────────────────────────────────────────────


def main() -> None:  # noqa: PLR0912, PLR0915
    """CLI entry point for AI Translate."""
    # Force line-buffered stdout so banner / progress / summary lines
    # appear in chronological order against ``logging`` output (which
    # writes to stderr unbuffered).  Without this, a pipe-redirected
    # stdout is fully buffered and error logs from the pipeline can
    # surface before the "Source: …" banner has flushed.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)

    parser = _build_parser()
    args = parser.parse_args()

    # --list-languages: print and exit
    if args.list_languages:
        for lang in AVAILABLE_LANGUAGES:
            print(lang)
        sys.exit(EXIT_OK)

    # Validate required args (deferred so --list-languages works standalone)
    if not args.target:
        parser.error("the following arguments are required: --target/-t")
    if not args.files:
        parser.error("the following arguments are required: files")

    # ── 1. Bootstrap (mirrors main.py minus Qt) ──
    from src.core.database import init_db  # noqa: PLC0415
    from src.utils.path_manager import (  # noqa: PLC0415
        configure_logging,
        ensure_app_dirs_exist,
    )

    ensure_app_dirs_exist()
    configure_logging()

    # ``configure_logging`` initialises the root logger at DEBUG so the
    # file handler captures everything; the *console* default for the
    # CLI is INFO so library chatter (keyring, urllib3, …) doesn't drown
    # out actionable messages.  ``--verbose`` opens the firehose,
    # ``--quiet`` drops to ERROR.  We only widen the root logger when
    # the user explicitly asks for verbose output — narrowing it would
    # silently throttle the file handler too.
    if args.verbose:
        console_level = logging.DEBUG
        logging.getLogger().setLevel(logging.DEBUG)
    elif args.quiet:
        console_level = logging.ERROR
    else:
        console_level = logging.INFO
    for handler in logging.getLogger().handlers:
        if not isinstance(handler, logging.FileHandler):
            handler.setLevel(console_level)

    # Replace the verbose console handler with a concise one — the full
    # detail (tracebacks, HTTP body dumps) still lands in app.log, but
    # the user's terminal gets a one-line friendly message.
    _install_cli_console_filter(verbose=args.verbose)

    init_db()

    # Restore the per-(endpoint, model) variant cache so a CLI
    # invocation against a known reasoning model (o1/o3/gpt-5.x) skips
    # the variant probe and goes straight to the working payload.
    from src.core.llm_engine import _load_persistent_caches  # noqa: PLC0415

    _load_persistent_caches()

    # ── 2. Validate arguments ──
    target_lang = _resolve_language(args.target)
    if target_lang is None:
        suggestions = _suggest_language_matches(args.target)
        hint = (
            f"Did you mean one of: {', '.join(suggestions)}?\n" if suggestions else ""
        )
        print(
            f"Error: unknown target language '{args.target}'.\n"
            f"{hint}"
            f"Run with --list-languages to see all options.",
            file=sys.stderr,
        )
        sys.exit(EXIT_ARGS_ERROR)

    source_lang: str = ""
    if args.source:
        resolved_src = _resolve_language(args.source)
        if resolved_src is None:
            suggestions = _suggest_language_matches(args.source)
            hint = (
                f"Did you mean one of: {', '.join(suggestions)}?\n"
                if suggestions
                else ""
            )
            print(
                f"Error: unknown source language '{args.source}'.\n"
                f"{hint}"
                f"Run with --list-languages to see all options.",
                file=sys.stderr,
            )
            sys.exit(EXIT_ARGS_ERROR)
        source_lang = resolved_src

    valid_files = _validate_files(args.files)
    if not valid_files:
        print("Error: no valid input files.", file=sys.stderr)
        sys.exit(EXIT_ARGS_ERROR)

    output_dir: Path | None = None
    if args.output:
        output_dir = args.output.resolve()
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            print(
                f"Error: cannot create output directory '{args.output}': {exc}",
                file=sys.stderr,
            )
            sys.exit(EXIT_ARGS_ERROR)

    # ── 3. Validate LLM setup ──
    from src.utils.config_manager import (  # noqa: PLC0415
        check_llm_setup,
        check_ocr_setup_for_method,
        get_available_models,
        parse_model_id,
    )

    if not check_llm_setup():
        print(
            "Error: LLM is not configured.\n"
            "Run the desktop app first and set up your API key in Settings > LLM.",
            file=sys.stderr,
        )
        sys.exit(EXIT_SETUP_ERROR)

    # Resolve LLM model
    llm_provider, llm_model = "", ""
    if args.model:
        # ``parse_model_id`` silently falls back to the default Gemini
        # model when the separator is missing — guard at the CLI layer
        # so the user gets an actionable error instead of an unexpected
        # backend.
        if ":" not in args.model:
            print(
                f"Error: --model expects 'Provider:model_name' (got '{args.model}').\n"
                f"Run a translation in the desktop app first to see "
                f"available identifiers.",
                file=sys.stderr,
            )
            sys.exit(EXIT_ARGS_ERROR)
        llm_provider, llm_model = parse_model_id(args.model)
        available = get_available_models()
        if (llm_provider, llm_model) not in available:
            print(
                f"Error: model '{args.model}' is not available.\n"
                f"Available models: {', '.join(f'{p}:{m}' for p, m in available)}",
                file=sys.stderr,
            )
            sys.exit(EXIT_SETUP_ERROR)

    # ── 4. Build config and set up tasks ──
    from src.constants.ocr import OCR_METHOD_TESSERACT, OCR_METHODS  # noqa: PLC0415
    from src.core.config import TranslationConfig  # noqa: PLC0415
    from src.core.translator import (  # noqa: PLC0415
        run_translation_pipeline,
        setup_translation_tasks,
    )

    if args.ocr_method:
        resolved_ocr = _resolve_ocr_method(args.ocr_method)
        if resolved_ocr is None:
            print(
                f"Error: unknown OCR method '{args.ocr_method}'.\n"
                f"Available: {', '.join(OCR_METHODS)}",
                file=sys.stderr,
            )
            sys.exit(EXIT_ARGS_ERROR)
        ocr_method = resolved_ocr
    else:
        ocr_method = OCR_METHOD_TESSERACT
    config = TranslationConfig(
        storage_path=str(output_dir) if output_dir else "",
        ocr_method=ocr_method,
        translate_doc_images=args.translate_images,
        translate_doc_comments=args.translate_comments,
        translate_doc_shapes=args.translate_shapes,
        translate_doc_notes=args.translate_notes,
        translate_sheet_names=args.translate_sheet_names,
        ocr_is_configured=(
            check_ocr_setup_for_method(ocr_method) if args.translate_images else False
        ),
        auto_convert_legacy=args.convert_legacy,
        auto_convert_odf=args.convert_odf,
        auto_remove_history=not args.keep_history,
        llm_provider=llm_provider,
        llm_model=llm_model,
    )

    if not args.quiet:
        print(f"Source:  {source_lang or 'auto-detect'}")
        print(f"Target:  {target_lang}")
        print(f"Files:   {len(valid_files)}")
        if config.storage_path:
            print(f"Output:  {config.storage_path}")
        print()

    tasks = setup_translation_tasks(
        [str(p) for p in valid_files],
        source_lang,
        target_lang,
    )
    if not tasks:
        print("Error: failed to set up translation tasks.", file=sys.stderr)
        sys.exit(EXIT_ALL_FAILED)

    task_ids = [t[0] for t in tasks]

    if not args.quiet:
        for h_id, storage_path, _src, _tgt in tasks:
            print(f"  Queued task {h_id}: {Path(storage_path).name}")
        print()

    # ── 5. Run pipeline ──
    stop_event = threading.Event()
    progress_thread = None
    if not args.quiet:
        progress_thread = threading.Thread(
            target=_progress_reporter,
            args=(task_ids, stop_event),
            daemon=True,
        )
        progress_thread.start()

    # Ctrl+C flow: the first SIGINT flips the cooperative cancel flag so the
    # pipeline can stop at its next polling point without trashing the
    # current task's checkpoint; the second SIGINT raises KeyboardInterrupt
    # from inside the handler, which Python propagates up the current frame
    # (same mechanism as signal.default_int_handler). Swapping handlers and
    # returning wouldn't work — the current signal is consumed by returning,
    # so the force path would need a third press instead of a second.
    cancel_flag = threading.Event()

    def _sigint_handler(_signum: int, _frame: object) -> None:
        if cancel_flag.is_set():
            raise KeyboardInterrupt
        cancel_flag.set()
        print(
            "\nCancel requested. Finishing current task… (Ctrl+C again to force)",
            file=sys.stderr,
        )

    previous_handler = signal.signal(signal.SIGINT, _sigint_handler)

    try:
        run_translation_pipeline(
            config=config,
            is_cancelled=cancel_flag.is_set,
            task_cancelled=lambda _hid: False,
        )
    except KeyboardInterrupt:
        cancel_flag.set()
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(EXIT_INTERRUPTED)
    finally:
        signal.signal(signal.SIGINT, previous_handler)
        stop_event.set()
        if progress_thread is not None:
            progress_thread.join(timeout=3.0)

    # ── 6. Report results ──
    from src.constants.history import STATUS_DONE, STATUS_FAILED  # noqa: PLC0415
    from src.core.database import get_history_entry_status  # noqa: PLC0415

    done = 0
    failed = 0
    incomplete = 0
    for h_id in task_ids:
        status = get_history_entry_status(h_id)
        if status == STATUS_FAILED:
            failed += 1
        elif status is None or status == STATUS_DONE:
            # None means auto_remove_history cleaned up a successful task.
            done += 1
        else:
            # Pending / Translating / Paused — pipeline returned before
            # finishing this one (e.g. a cooperative cancel).
            incomplete += 1

    if not args.quiet:
        print()
        print(f"Done: {done}/{len(tasks)}")
        if failed:
            print(f"Failed: {failed}/{len(tasks)}")
        if incomplete:
            print(f"Incomplete: {incomplete}/{len(tasks)}")

    if cancel_flag.is_set():
        sys.exit(EXIT_INTERRUPTED)
    if failed == len(tasks):
        sys.exit(EXIT_ALL_FAILED)
    if failed > 0 or incomplete > 0:
        sys.exit(EXIT_PARTIAL_FAILURE)
    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
