"""Utilities for managing background translation workers."""

import logging

from PySide6.QtWidgets import QApplication, QMainWindow

from src.constants.history import STATUS_PENDING, STATUS_TRANSLATING
from src.core.database import get_unfinished_history
from src.core.translator import TranslationWorker

logger = logging.getLogger("worker_utils")

# Module-level set of in-flight workers, drained by the
# ``aboutToQuit`` cleanup hook below.  We use a module-level set
# rather than a window-attached list because resume_unfinished_*
# may build a worker BEFORE the window assigns ``_workers``,
# and the cleanup must catch every worker regardless of which
# code path constructed it.  Using a set keeps the membership
# check O(1) and gives idempotent ``discard`` semantics.
_TRACKED_WORKERS: set[TranslationWorker] = set()
_QUIT_HOOK_CONNECTED = False


def _stop_translation_workers_on_quit() -> None:
    """Bounded-wait every tracked translation worker on app exit.

    Mirrors the ``wait(2000)`` shutdown contract documented in
    AGENTS.md for every page-owned ``QThread`` — without it,
    quitting mid-translation surfaces "QThread destroyed while
    still running" warnings and the in-flight HTTP / file I/O
    is torn down ungracefully.  Worker's ``stop()`` flips the
    cooperative-cancel flag; the bounded wait gives the run
    loop one full iteration to notice and exit cleanly.
    """
    for worker in list(_TRACKED_WORKERS):
        try:
            if hasattr(worker, "stop"):
                worker.stop()
            if hasattr(worker, "wait"):
                worker.wait(2000)
        except Exception:
            logger.exception("Error stopping translation worker on quit")
    _TRACKED_WORKERS.clear()


def start_translation_worker(
    window: QMainWindow, tasks: list[tuple[int, str, str, str]]
) -> TranslationWorker | None:
    """Helper to safely spawn or retrieve the background worker.

    Manages the lifecycle of the worker thread by attaching it to the
    window instance to prevent premature garbage collection.

    Args:
        window: The main window instance (keeps the thread alive).
        tasks: List of translation tasks.

    Returns:
        The started TranslationWorker or None if busy.
    """
    if not TranslationWorker.is_busy():
        worker = TranslationWorker(tasks)

        # Ensure the window has a list to hold worker references
        if not hasattr(window, "_workers"):
            window._workers = []
        window._workers.append(worker)
        _TRACKED_WORKERS.add(worker)

        # Lazy ``aboutToQuit`` connect — module-level so we wire it
        # exactly once across the whole session.  Connecting it
        # inside ``start_translation_worker`` keeps the import-time
        # graph free of QApplication side effects (helpful for
        # CLI / MCP entry points that build their own offscreen
        # QApplication later).
        global _QUIT_HOOK_CONNECTED  # noqa: PLW0603
        if not _QUIT_HOOK_CONNECTED:
            app = QApplication.instance()
            if app is not None:
                app.aboutToQuit.connect(_stop_translation_workers_on_quit)
                _QUIT_HOOK_CONNECTED = True

        def cleanup() -> None:
            """Remove finished worker and auto-resume pending tasks."""
            if worker in window._workers:
                window._workers.remove(worker)
            _TRACKED_WORKERS.discard(worker)
            # Auto-resume any pending tasks
            resume_unfinished_translations()

        worker.finished.connect(cleanup)
        worker.start()
        return worker
    return None


def resume_unfinished_translations() -> TranslationWorker | None:
    """Auto-resumes interrupted tasks upon app startup or worker idle.

    Scans the database for 'Pending' or 'Translating' tasks and restarts
    the worker if found. Finds the active QMainWindow to anchor the thread.

    Returns:
        The restarted TranslationWorker or None.
    """
    unfinished = get_unfinished_history(
        statuses=(STATUS_PENDING, STATUS_TRANSLATING),
    )
    if not unfinished:
        return None

    # Find the main window to keep the thread alive
    main_window = None
    for widget in QApplication.topLevelWidgets():
        if widget.inherits("QMainWindow"):
            main_window = widget
            break

    if main_window:
        return start_translation_worker(main_window, unfinished)
    return None
