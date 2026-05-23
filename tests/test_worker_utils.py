"""Unit tests for worker management utilities.

Covers:
- start_translation_worker() — creates, attaches, and starts TranslationWorker
- Worker lifecycle management on the main window (_workers list)
- Busy state checking (returns None when worker is already running)
- Signal connections (finished signal triggers cleanup and auto-resume)
- resume_unfinished_translations() — rescans DB and restarts workers
- Cleanup resilience (already-removed worker, multiple sequential workers)
"""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QMainWindow

from src.ui.worker_utils import resume_unfinished_translations, start_translation_worker

# ---------------------------------------------------------------------------
# Module path prefix
# ---------------------------------------------------------------------------
_W = "src.ui.worker_utils"


@pytest.fixture()
def mock_window() -> MagicMock:
    """Provides a mocked QMainWindow."""
    window = MagicMock(spec=QMainWindow)
    # Mock inherits to satisfy the 'resume' logic
    window.inherits.return_value = True
    return window


# ===========================================================================
# start_translation_worker — basic behaviour
# ===========================================================================


@patch(f"{_W}.TranslationWorker")
def test_start_translation_worker(
    mock_worker_class: Any,  # noqa: ANN401
    mock_window: MagicMock,
) -> None:
    """Verify that worker is started and attached to window."""
    mock_worker_class.is_busy.return_value = False

    tasks = [(1, "path", "en", "fr")]
    worker = start_translation_worker(mock_window, tasks)

    assert worker is not None
    assert worker in mock_window._workers
    worker.start.assert_called_once()


@patch(f"{_W}.TranslationWorker")
def test_start_translation_worker_busy(
    mock_worker_class: Any,  # noqa: ANN401
    mock_window: MagicMock,
) -> None:
    """Verify that worker is not started if busy."""
    mock_worker_class.is_busy.return_value = True

    tasks = [(1, "path", "en", "fr")]
    worker = start_translation_worker(mock_window, tasks)

    assert worker is None
    assert not hasattr(mock_window, "_workers")


@patch(f"{_W}.TranslationWorker")
def test_start_worker_creates_workers_list_if_missing(
    mock_worker_class: Any,  # noqa: ANN401
    mock_window: MagicMock,
) -> None:
    """start_translation_worker creates _workers list if window lacks one."""
    mock_worker_class.is_busy.return_value = False
    # Remove _workers attribute if present
    if hasattr(mock_window, "_workers"):
        delattr(mock_window, "_workers")

    worker = start_translation_worker(mock_window, [(1, "p", "en", "fr")])

    assert hasattr(mock_window, "_workers")
    assert worker in mock_window._workers


@patch(f"{_W}.TranslationWorker")
def test_start_worker_passes_tasks_to_constructor(
    mock_worker_class: Any,  # noqa: ANN401
    mock_window: MagicMock,
) -> None:
    """Tasks list is forwarded unchanged to the TranslationWorker constructor."""
    mock_worker_class.is_busy.return_value = False
    tasks = [(1, "/a.txt", "English", "French"), (2, "/b.txt", "English", "German")]

    start_translation_worker(mock_window, tasks)

    mock_worker_class.assert_called_once_with(tasks)


@patch(f"{_W}.TranslationWorker")
def test_start_worker_with_empty_tasks(
    mock_worker_class: Any,  # noqa: ANN401
    mock_window: MagicMock,
) -> None:
    """An empty tasks list still creates a worker (no filtering here)."""
    mock_worker_class.is_busy.return_value = False

    worker = start_translation_worker(mock_window, [])

    assert worker is not None
    mock_worker_class.assert_called_once_with([])
    worker.start.assert_called_once()


@patch(f"{_W}.TranslationWorker")
def test_start_worker_busy_does_not_create_worker(
    mock_worker_class: Any,  # noqa: ANN401
    mock_window: MagicMock,
) -> None:
    """When busy, no TranslationWorker is instantiated at all."""
    mock_worker_class.is_busy.return_value = True

    start_translation_worker(mock_window, [(1, "p", "en", "fr")])

    # Constructor should never be called
    mock_worker_class.assert_not_called()


# ===========================================================================
# start_translation_worker — _workers list management
# ===========================================================================


@patch(f"{_W}.TranslationWorker")
def test_start_worker_reuses_existing_workers_list(
    mock_worker_class: Any,  # noqa: ANN401
    mock_window: MagicMock,
) -> None:
    """If the window already has _workers, the new worker is appended."""
    mock_worker_class.is_busy.return_value = False
    existing = MagicMock()
    mock_window._workers = [existing]

    worker = start_translation_worker(mock_window, [(1, "p", "en", "fr")])

    assert len(mock_window._workers) == 2  # noqa: PLR2004
    assert existing in mock_window._workers
    assert worker in mock_window._workers


# ===========================================================================
# start_translation_worker — finished signal / cleanup
# ===========================================================================


@patch(f"{_W}.TranslationWorker")
@patch(f"{_W}.resume_unfinished_translations")
def test_worker_cleanup_removes_from_list(
    mock_resume: Any,  # noqa: ANN401
    mock_worker_class: Any,  # noqa: ANN401
    mock_window: MagicMock,
) -> None:
    """Worker finished signal triggers cleanup: removes from _workers list."""
    mock_worker_class.is_busy.return_value = False

    worker = start_translation_worker(mock_window, [(1, "p", "en", "fr")])
    assert worker in mock_window._workers

    # Extract the cleanup callback attached via finished.connect
    cleanup_fn = worker.finished.connect.call_args[0][0]
    cleanup_fn()

    assert worker not in mock_window._workers
    mock_resume.assert_called_once()


@patch(f"{_W}.TranslationWorker")
@patch(f"{_W}.resume_unfinished_translations")
def test_cleanup_connects_finished_signal(
    mock_resume: Any,  # noqa: ANN401
    mock_worker_class: Any,  # noqa: ANN401
    mock_window: MagicMock,
) -> None:
    """The finished signal is connected to a cleanup callback."""
    mock_worker_class.is_busy.return_value = False

    worker = start_translation_worker(mock_window, [(1, "p", "en", "fr")])

    worker.finished.connect.assert_called_once()


@patch(f"{_W}.TranslationWorker")
@patch(f"{_W}.resume_unfinished_translations")
def test_cleanup_calls_resume_unfinished(
    mock_resume: Any,  # noqa: ANN401
    mock_worker_class: Any,  # noqa: ANN401
    mock_window: MagicMock,
) -> None:
    """The cleanup callback invokes resume_unfinished_translations()."""
    mock_worker_class.is_busy.return_value = False

    worker = start_translation_worker(mock_window, [(1, "p", "en", "fr")])
    cleanup_fn = worker.finished.connect.call_args[0][0]
    cleanup_fn()

    mock_resume.assert_called_once()


@patch(f"{_W}.TranslationWorker")
@patch(f"{_W}.resume_unfinished_translations")
def test_cleanup_tolerates_already_removed_worker(
    mock_resume: Any,  # noqa: ANN401
    mock_worker_class: Any,  # noqa: ANN401
    mock_window: MagicMock,
) -> None:
    """Cleanup does not crash if the worker was already removed."""
    mock_worker_class.is_busy.return_value = False

    worker = start_translation_worker(mock_window, [(1, "p", "en", "fr")])
    cleanup_fn = worker.finished.connect.call_args[0][0]

    # Manually remove the worker before cleanup runs
    mock_window._workers.remove(worker)
    cleanup_fn()  # should not raise

    # resume_unfinished is still called
    mock_resume.assert_called_once()


@patch(f"{_W}.TranslationWorker")
@patch(f"{_W}.resume_unfinished_translations")
def test_cleanup_only_removes_its_own_worker(
    mock_resume: Any,  # noqa: ANN401
    mock_worker_class: Any,  # noqa: ANN401
    mock_window: MagicMock,
) -> None:
    """Cleanup removes only the finished worker, not others."""
    mock_worker_class.is_busy.return_value = False

    # Pre-existing worker reference in the list
    other_worker = MagicMock()
    mock_window._workers = [other_worker]

    worker = start_translation_worker(mock_window, [(1, "p", "en", "fr")])
    cleanup_fn = worker.finished.connect.call_args[0][0]
    cleanup_fn()

    assert other_worker in mock_window._workers
    assert worker not in mock_window._workers


# ===========================================================================
# start_translation_worker — multiple sequential workers
# ===========================================================================


@patch(f"{_W}.TranslationWorker")
@patch(f"{_W}.resume_unfinished_translations")
def test_multiple_workers_sequentially(
    mock_resume: Any,  # noqa: ANN401
    mock_worker_class: Any,  # noqa: ANN401
    mock_window: MagicMock,
) -> None:
    """Multiple workers can be started after each finishes."""
    mock_worker_class.is_busy.return_value = False

    worker_a = MagicMock()
    worker_b = MagicMock()
    mock_worker_class.side_effect = [worker_a, worker_b]

    # Start first worker
    result_a = start_translation_worker(mock_window, [(1, "a", "en", "fr")])
    assert result_a is worker_a

    # Simulate first worker finishing
    cleanup_a = worker_a.finished.connect.call_args[0][0]
    cleanup_a()
    assert worker_a not in mock_window._workers

    # Start second worker
    result_b = start_translation_worker(mock_window, [(2, "b", "en", "de")])
    assert result_b is worker_b
    assert worker_b in mock_window._workers


# ===========================================================================
# resume_unfinished_translations
# ===========================================================================


@patch(f"{_W}.get_unfinished_history")
@patch(f"{_W}.QApplication")
@patch(f"{_W}.start_translation_worker")
def test_resume_unfinished_translations(
    mock_start: Any,  # noqa: ANN401
    mock_qapp: Any,  # noqa: ANN401
    mock_get_history: Any,  # noqa: ANN401
    mock_window: MagicMock,
) -> None:
    """Verify that resume logic finds the window and restarts tasks."""
    mock_get_history.return_value = [(1, "path", "en", "fr")]
    mock_qapp.topLevelWidgets.return_value = [mock_window]

    resume_unfinished_translations()

    mock_start.assert_called_once_with(
        mock_window,
        [(1, "path", "en", "fr")],
    )


@patch(f"{_W}.get_unfinished_history")
def test_resume_no_unfinished_returns_none(
    mock_get_history: Any,  # noqa: ANN401
) -> None:
    """When no unfinished tasks exist, resume returns None immediately."""
    mock_get_history.return_value = []

    result = resume_unfinished_translations()

    assert result is None


@patch(f"{_W}.get_unfinished_history")
@patch(f"{_W}.QApplication")
def test_resume_no_main_window_returns_none(
    mock_qapp: Any,  # noqa: ANN401
    mock_get_history: Any,  # noqa: ANN401
) -> None:
    """When no QMainWindow is found, resume returns None."""
    mock_get_history.return_value = [(1, "path", "en", "fr")]
    # Provide a widget that does NOT inherit QMainWindow
    mock_widget = MagicMock()
    mock_widget.inherits.return_value = False
    mock_qapp.topLevelWidgets.return_value = [mock_widget]

    result = resume_unfinished_translations()

    assert result is None


@patch(f"{_W}.get_unfinished_history")
def test_resume_passes_correct_statuses(
    mock_get_history: Any,  # noqa: ANN401
) -> None:
    """Verifies that STATUS_PENDING and STATUS_TRANSLATING are queried."""
    mock_get_history.return_value = []

    resume_unfinished_translations()

    mock_get_history.assert_called_once_with(
        statuses=("Pending", "Translating"),
    )


@patch(f"{_W}.get_unfinished_history")
@patch(f"{_W}.QApplication")
@patch(f"{_W}.start_translation_worker")
def test_resume_picks_first_main_window(
    mock_start: Any,  # noqa: ANN401
    mock_qapp: Any,  # noqa: ANN401
    mock_get_history: Any,  # noqa: ANN401
) -> None:
    """When multiple top-level widgets exist, the first QMainWindow is used."""
    unfinished = [(10, "/tmp/f.txt", "English", "French")]
    mock_get_history.return_value = unfinished

    non_mw = MagicMock()
    non_mw.inherits.return_value = False
    first_mw = MagicMock()
    first_mw.inherits.return_value = True
    second_mw = MagicMock()
    second_mw.inherits.return_value = True
    mock_qapp.topLevelWidgets.return_value = [non_mw, first_mw, second_mw]
    mock_start.return_value = MagicMock()

    resume_unfinished_translations()

    # Should pass first_mw, not second_mw
    mock_start.assert_called_once_with(first_mw, unfinished)


@patch(f"{_W}.get_unfinished_history")
@patch(f"{_W}.QApplication")
@patch(f"{_W}.start_translation_worker")
def test_resume_returns_worker_from_start(
    mock_start: Any,  # noqa: ANN401
    mock_qapp: Any,  # noqa: ANN401
    mock_get_history: Any,  # noqa: ANN401
    mock_window: MagicMock,
) -> None:
    """Returns whatever start_translation_worker() returns."""
    sentinel = MagicMock(name="sentinel_worker")
    mock_get_history.return_value = [(10, "/tmp/f.txt", "English", "French")]
    mock_qapp.topLevelWidgets.return_value = [mock_window]
    mock_start.return_value = sentinel

    result = resume_unfinished_translations()

    assert result is sentinel


@patch(f"{_W}.get_unfinished_history")
@patch(f"{_W}.QApplication")
@patch(f"{_W}.start_translation_worker")
def test_resume_returns_none_when_start_returns_none(
    mock_start: Any,  # noqa: ANN401
    mock_qapp: Any,  # noqa: ANN401
    mock_get_history: Any,  # noqa: ANN401
    mock_window: MagicMock,
) -> None:
    """Returns None when start_translation_worker returns None (busy)."""
    mock_get_history.return_value = [(10, "/tmp/f.txt", "en", "fr")]
    mock_qapp.topLevelWidgets.return_value = [mock_window]
    mock_start.return_value = None

    result = resume_unfinished_translations()

    assert result is None


@patch(f"{_W}.get_unfinished_history")
@patch(f"{_W}.QApplication")
def test_resume_no_top_level_widgets_returns_none(
    mock_qapp: Any,  # noqa: ANN401
    mock_get_history: Any,  # noqa: ANN401
) -> None:
    """Returns None when there are no top-level widgets at all."""
    mock_get_history.return_value = [(1, "p", "en", "fr")]
    mock_qapp.topLevelWidgets.return_value = []

    result = resume_unfinished_translations()

    assert result is None


@patch(f"{_W}.get_unfinished_history")
@patch(f"{_W}.QApplication")
@patch(f"{_W}.start_translation_worker")
def test_resume_multiple_unfinished_tasks(
    mock_start: Any,  # noqa: ANN401
    mock_qapp: Any,  # noqa: ANN401
    mock_get_history: Any,  # noqa: ANN401
    mock_window: MagicMock,
) -> None:
    """All unfinished tasks are forwarded to start_translation_worker."""
    unfinished = [
        (1, "/tmp/a.txt", "English", "French"),
        (2, "/tmp/b.txt", "English", "German"),
        (3, "/tmp/c.txt", "English", "Spanish"),
    ]
    mock_get_history.return_value = unfinished
    mock_qapp.topLevelWidgets.return_value = [mock_window]
    mock_start.return_value = MagicMock()

    resume_unfinished_translations()

    mock_start.assert_called_once_with(mock_window, unfinished)


# ===========================================================================
# start_translation_worker — return type validation
# ===========================================================================


@patch(f"{_W}.TranslationWorker")
def test_start_worker_returns_worker_instance(
    mock_worker_class: Any,  # noqa: ANN401
    mock_window: MagicMock,
) -> None:
    """start_translation_worker returns the created worker."""
    mock_worker_class.is_busy.return_value = False
    result = start_translation_worker(mock_window, [(1, "p", "en", "fr")])
    assert result is mock_worker_class.return_value


@patch(f"{_W}.TranslationWorker")
def test_start_worker_busy_returns_none(
    mock_worker_class: Any,  # noqa: ANN401
    mock_window: MagicMock,
) -> None:
    """start_translation_worker returns None when busy."""
    mock_worker_class.is_busy.return_value = True
    result = start_translation_worker(mock_window, [(1, "p", "en", "fr")])
    assert result is None


# ===========================================================================
# start_translation_worker — tasks content validation
# ===========================================================================


@patch(f"{_W}.TranslationWorker")
def test_start_worker_single_task(
    mock_worker_class: Any,  # noqa: ANN401
    mock_window: MagicMock,
) -> None:
    """Worker created with a single task."""
    mock_worker_class.is_busy.return_value = False
    tasks = [(99, "/file.txt", "Spanish", "English")]
    start_translation_worker(mock_window, tasks)
    mock_worker_class.assert_called_once_with(tasks)


@patch(f"{_W}.TranslationWorker")
def test_start_worker_multiple_tasks(
    mock_worker_class: Any,  # noqa: ANN401
    mock_window: MagicMock,
) -> None:
    """Worker created with multiple tasks."""
    mock_worker_class.is_busy.return_value = False
    tasks = [
        (1, "/a.txt", "English", "French"),
        (2, "/b.txt", "English", "German"),
        (3, "/c.txt", "English", "Spanish"),
    ]
    start_translation_worker(mock_window, tasks)
    mock_worker_class.assert_called_once_with(tasks)


@patch(f"{_W}.TranslationWorker")
def test_start_worker_large_batch(
    mock_worker_class: Any,  # noqa: ANN401
    mock_window: MagicMock,
) -> None:
    """Worker handles large batch of tasks."""
    mock_worker_class.is_busy.return_value = False
    tasks = [(i, f"/file{i}.txt", "English", "French") for i in range(100)]
    start_translation_worker(mock_window, tasks)
    mock_worker_class.assert_called_once_with(tasks)


# ===========================================================================
# start_translation_worker — worker start verification
# ===========================================================================


@patch(f"{_W}.TranslationWorker")
def test_start_worker_start_called(
    mock_worker_class: Any,  # noqa: ANN401
    mock_window: MagicMock,
) -> None:
    """Worker.start() is called exactly once."""
    mock_worker_class.is_busy.return_value = False
    worker = start_translation_worker(mock_window, [(1, "p", "en", "fr")])
    worker.start.assert_called_once()


@patch(f"{_W}.TranslationWorker")
def test_start_worker_busy_no_start_called(
    mock_worker_class: Any,  # noqa: ANN401
    mock_window: MagicMock,
) -> None:
    """Worker.start() is never called when busy."""
    mock_worker_class.is_busy.return_value = True
    start_translation_worker(mock_window, [(1, "p", "en", "fr")])
    mock_worker_class.return_value.start.assert_not_called()


# ===========================================================================
# start_translation_worker — finished signal and cleanup (extended)
# ===========================================================================


@patch(f"{_W}.TranslationWorker")
@patch(f"{_W}.resume_unfinished_translations")
def test_cleanup_removes_correct_worker_from_many(
    mock_resume: Any,  # noqa: ANN401
    mock_worker_class: Any,  # noqa: ANN401
    mock_window: MagicMock,
) -> None:
    """Cleanup removes only the specific worker from a list with many."""
    mock_worker_class.is_busy.return_value = False
    existing = [MagicMock() for _ in range(5)]
    mock_window._workers = list(existing)

    worker = start_translation_worker(mock_window, [(1, "p", "en", "fr")])
    cleanup_fn = worker.finished.connect.call_args[0][0]
    cleanup_fn()

    assert worker not in mock_window._workers
    for e in existing:
        assert e in mock_window._workers


@patch(f"{_W}.TranslationWorker")
@patch(f"{_W}.resume_unfinished_translations")
def test_cleanup_resume_called_after_removal(
    mock_resume: Any,  # noqa: ANN401
    mock_worker_class: Any,  # noqa: ANN401
    mock_window: MagicMock,
) -> None:
    """resume_unfinished_translations is called after worker removal."""
    mock_worker_class.is_busy.return_value = False
    worker = start_translation_worker(mock_window, [(1, "p", "en", "fr")])
    cleanup_fn = worker.finished.connect.call_args[0][0]
    cleanup_fn()
    mock_resume.assert_called_once()


@patch(f"{_W}.TranslationWorker")
@patch(f"{_W}.resume_unfinished_translations")
def test_cleanup_idempotent(
    mock_resume: Any,  # noqa: ANN401
    mock_worker_class: Any,  # noqa: ANN401
    mock_window: MagicMock,
) -> None:
    """Calling cleanup twice does not crash."""
    mock_worker_class.is_busy.return_value = False
    worker = start_translation_worker(mock_window, [(1, "p", "en", "fr")])
    cleanup_fn = worker.finished.connect.call_args[0][0]
    cleanup_fn()
    cleanup_fn()  # Second call should not raise
    assert mock_resume.call_count == 2  # noqa: PLR2004


# ===========================================================================
# start_translation_worker — _workers list growth
# ===========================================================================


@patch(f"{_W}.TranslationWorker")
def test_workers_list_grows_with_each_start(
    mock_worker_class: Any,  # noqa: ANN401
    mock_window: MagicMock,
) -> None:
    """Each start_translation_worker call adds to _workers list."""
    mock_worker_class.is_busy.return_value = False
    workers_created = []
    for i in range(5):
        w = MagicMock()
        mock_worker_class.side_effect = [w]
        mock_worker_class.reset_mock()
        mock_worker_class.is_busy.return_value = False
        mock_worker_class.return_value = w
        result = start_translation_worker(mock_window, [(i, "p", "en", "fr")])
        workers_created.append(result)

    assert len(mock_window._workers) == 5  # noqa: PLR2004


# ===========================================================================
# Multiple sequential workers — extended
# ===========================================================================


@patch(f"{_W}.TranslationWorker")
@patch(f"{_W}.resume_unfinished_translations")
def test_three_sequential_workers(
    mock_resume: Any,  # noqa: ANN401
    mock_worker_class: Any,  # noqa: ANN401
    mock_window: MagicMock,
) -> None:
    """Three sequential workers can start and clean up."""
    mock_worker_class.is_busy.return_value = False

    w_a, w_b, w_c = MagicMock(), MagicMock(), MagicMock()
    mock_worker_class.side_effect = [w_a, w_b, w_c]

    # Start and finish first
    start_translation_worker(mock_window, [(1, "a", "en", "fr")])
    w_a.finished.connect.call_args[0][0]()
    assert w_a not in mock_window._workers

    # Start and finish second
    start_translation_worker(mock_window, [(2, "b", "en", "de")])
    w_b.finished.connect.call_args[0][0]()
    assert w_b not in mock_window._workers

    # Start third
    result = start_translation_worker(mock_window, [(3, "c", "en", "es")])
    assert result is w_c
    assert w_c in mock_window._workers


@patch(f"{_W}.TranslationWorker")
@patch(f"{_W}.resume_unfinished_translations")
def test_worker_cleanup_leaves_list_empty(
    mock_resume: Any,  # noqa: ANN401
    mock_worker_class: Any,  # noqa: ANN401
    mock_window: MagicMock,
) -> None:
    """After single worker finishes, _workers list is empty."""
    mock_worker_class.is_busy.return_value = False
    worker = start_translation_worker(mock_window, [(1, "p", "en", "fr")])
    cleanup_fn = worker.finished.connect.call_args[0][0]
    cleanup_fn()
    assert len(mock_window._workers) == 0


# ===========================================================================
# resume_unfinished_translations — extended
# ===========================================================================


@patch(f"{_W}.get_unfinished_history")
def test_resume_calls_get_unfinished_history(
    mock_get_history: Any,  # noqa: ANN401
) -> None:
    """resume_unfinished_translations always calls get_unfinished_history."""
    mock_get_history.return_value = []
    resume_unfinished_translations()
    mock_get_history.assert_called_once()


@patch(f"{_W}.get_unfinished_history")
@patch(f"{_W}.QApplication")
@patch(f"{_W}.start_translation_worker")
def test_resume_with_single_unfinished_task(
    mock_start: Any,  # noqa: ANN401
    mock_qapp: Any,  # noqa: ANN401
    mock_get_history: Any,  # noqa: ANN401
    mock_window: MagicMock,
) -> None:
    """Single unfinished task triggers start_translation_worker."""
    task = [(99, "/single.txt", "Spanish", "English")]
    mock_get_history.return_value = task
    mock_qapp.topLevelWidgets.return_value = [mock_window]
    mock_start.return_value = MagicMock()

    resume_unfinished_translations()

    mock_start.assert_called_once_with(mock_window, task)


@patch(f"{_W}.get_unfinished_history")
@patch(f"{_W}.QApplication")
@patch(f"{_W}.start_translation_worker")
def test_resume_passes_all_tasks_not_just_first(
    mock_start: Any,  # noqa: ANN401
    mock_qapp: Any,  # noqa: ANN401
    mock_get_history: Any,  # noqa: ANN401
    mock_window: MagicMock,
) -> None:
    """All tasks are passed to start_translation_worker, not just first."""
    tasks = [
        (1, "/a.txt", "en", "fr"),
        (2, "/b.txt", "en", "de"),
        (3, "/c.txt", "en", "es"),
        (4, "/d.txt", "en", "ja"),
    ]
    mock_get_history.return_value = tasks
    mock_qapp.topLevelWidgets.return_value = [mock_window]
    mock_start.return_value = MagicMock()

    resume_unfinished_translations()

    mock_start.assert_called_once_with(mock_window, tasks)
    assert mock_start.call_args[0][1] == tasks


@patch(f"{_W}.get_unfinished_history")
@patch(f"{_W}.QApplication")
def test_resume_skips_non_main_windows(
    mock_qapp: Any,  # noqa: ANN401
    mock_get_history: Any,  # noqa: ANN401
) -> None:
    """Resume skips widgets that are not QMainWindow."""
    mock_get_history.return_value = [(1, "p", "en", "fr")]
    dialog1 = MagicMock()
    dialog1.inherits.return_value = False
    dialog2 = MagicMock()
    dialog2.inherits.return_value = False
    mock_qapp.topLevelWidgets.return_value = [dialog1, dialog2]

    result = resume_unfinished_translations()

    assert result is None


@patch(f"{_W}.get_unfinished_history")
@patch(f"{_W}.QApplication")
@patch(f"{_W}.start_translation_worker")
def test_resume_inherits_check_with_qmainwindow_string(
    mock_start: Any,  # noqa: ANN401
    mock_qapp: Any,  # noqa: ANN401
    mock_get_history: Any,  # noqa: ANN401
) -> None:
    """Resume checks widget.inherits('QMainWindow')."""
    mock_get_history.return_value = [(1, "p", "en", "fr")]
    mw = MagicMock()
    mw.inherits.return_value = True
    mock_qapp.topLevelWidgets.return_value = [mw]
    mock_start.return_value = MagicMock()

    resume_unfinished_translations()

    mw.inherits.assert_called_with("QMainWindow")


@patch(f"{_W}.get_unfinished_history")
def test_resume_statuses_pending_and_translating(
    mock_get_history: Any,  # noqa: ANN401
) -> None:
    """Resume passes both Pending and Translating statuses."""
    mock_get_history.return_value = []
    resume_unfinished_translations()
    mock_get_history.assert_called_once_with(
        statuses=("Pending", "Translating"),
    )


# ===========================================================================
# Edge cases — window with existing workers
# ===========================================================================


@patch(f"{_W}.TranslationWorker")
def test_start_worker_with_preexisting_workers(
    mock_worker_class: Any,  # noqa: ANN401
    mock_window: MagicMock,
) -> None:
    """Worker added to existing non-empty _workers list."""
    mock_worker_class.is_busy.return_value = False
    existing = [MagicMock(), MagicMock()]
    mock_window._workers = list(existing)

    worker = start_translation_worker(mock_window, [(1, "p", "en", "fr")])

    assert len(mock_window._workers) == 3  # noqa: PLR2004
    assert worker in mock_window._workers
    for e in existing:
        assert e in mock_window._workers


@patch(f"{_W}.TranslationWorker")
def test_start_worker_does_not_modify_tasks(
    mock_worker_class: Any,  # noqa: ANN401
    mock_window: MagicMock,
) -> None:
    """Original tasks list is not modified."""
    mock_worker_class.is_busy.return_value = False
    tasks = [(1, "/a.txt", "en", "fr")]
    original_tasks = list(tasks)
    start_translation_worker(mock_window, tasks)
    assert tasks == original_tasks


# ===========================================================================
# is_busy checks
# ===========================================================================


@patch(f"{_W}.TranslationWorker")
def test_is_busy_called_before_creation(
    mock_worker_class: Any,  # noqa: ANN401
    mock_window: MagicMock,
) -> None:
    """is_busy is checked before creating a worker."""
    mock_worker_class.is_busy.return_value = False
    start_translation_worker(mock_window, [(1, "p", "en", "fr")])
    mock_worker_class.is_busy.assert_called_once()


@patch(f"{_W}.TranslationWorker")
def test_is_busy_true_prevents_worker_creation(
    mock_worker_class: Any,  # noqa: ANN401
    mock_window: MagicMock,
) -> None:
    """When is_busy returns True, no worker is created."""
    mock_worker_class.is_busy.return_value = True
    result = start_translation_worker(mock_window, [(1, "p", "en", "fr")])
    assert result is None
    mock_worker_class.assert_not_called()


# ===========================================================================
# finished signal connection
# ===========================================================================


@patch(f"{_W}.TranslationWorker")
def test_finished_signal_connected(
    mock_worker_class: Any,  # noqa: ANN401
    mock_window: MagicMock,
) -> None:
    """Finished signal has exactly one connection."""
    mock_worker_class.is_busy.return_value = False
    worker = start_translation_worker(mock_window, [(1, "p", "en", "fr")])
    worker.finished.connect.assert_called_once()


@patch(f"{_W}.TranslationWorker")
def test_finished_signal_callback_is_callable(
    mock_worker_class: Any,  # noqa: ANN401
    mock_window: MagicMock,
) -> None:
    """The callback connected to finished is callable."""
    mock_worker_class.is_busy.return_value = False
    worker = start_translation_worker(mock_window, [(1, "p", "en", "fr")])
    callback = worker.finished.connect.call_args[0][0]
    assert callable(callback)


# ===========================================================================
# resume with various widget configurations
# ===========================================================================


@patch(f"{_W}.get_unfinished_history")
@patch(f"{_W}.QApplication")
@patch(f"{_W}.start_translation_worker")
def test_resume_only_one_call_to_start(
    mock_start: Any,  # noqa: ANN401
    mock_qapp: Any,  # noqa: ANN401
    mock_get_history: Any,  # noqa: ANN401
) -> None:
    """Resume calls start_translation_worker exactly once."""
    mock_get_history.return_value = [(1, "p", "en", "fr")]
    mw1 = MagicMock()
    mw1.inherits.return_value = True
    mw2 = MagicMock()
    mw2.inherits.return_value = True
    mock_qapp.topLevelWidgets.return_value = [mw1, mw2]
    mock_start.return_value = MagicMock()

    resume_unfinished_translations()

    mock_start.assert_called_once()


@patch(f"{_W}.get_unfinished_history")
@patch(f"{_W}.QApplication")
def test_resume_empty_widgets_list(
    mock_qapp: Any,  # noqa: ANN401
    mock_get_history: Any,  # noqa: ANN401
) -> None:
    """Empty widget list returns None."""
    mock_get_history.return_value = [(1, "p", "en", "fr")]
    mock_qapp.topLevelWidgets.return_value = []
    result = resume_unfinished_translations()
    assert result is None


@patch(f"{_W}.get_unfinished_history")
@patch(f"{_W}.QApplication")
@patch(f"{_W}.start_translation_worker")
def test_resume_with_mixed_widgets(
    mock_start: Any,  # noqa: ANN401
    mock_qapp: Any,  # noqa: ANN401
    mock_get_history: Any,  # noqa: ANN401
) -> None:
    """Resume picks QMainWindow from mixed widget types."""
    mock_get_history.return_value = [(1, "p", "en", "fr")]
    dialog = MagicMock()
    dialog.inherits.return_value = False
    toolbar = MagicMock()
    toolbar.inherits.return_value = False
    main_win = MagicMock()
    main_win.inherits.return_value = True
    mock_qapp.topLevelWidgets.return_value = [dialog, toolbar, main_win]
    mock_start.return_value = MagicMock()

    resume_unfinished_translations()

    mock_start.assert_called_once_with(main_win, [(1, "p", "en", "fr")])


# ===========================================================================
# start_translation_worker — task tuple structure
# ===========================================================================


@patch(f"{_W}.TranslationWorker")
def test_start_worker_preserves_task_paths(
    mock_worker_class: Any,  # noqa: ANN401
    mock_window: MagicMock,
) -> None:
    """Task file paths are preserved in the constructor call."""
    mock_worker_class.is_busy.return_value = False
    tasks = [(1, "/deep/nested/path/file.docx", "en", "vi")]
    start_translation_worker(mock_window, tasks)
    assert mock_worker_class.call_args[0][0][0][1] == "/deep/nested/path/file.docx"


@patch(f"{_W}.TranslationWorker")
def test_start_worker_preserves_language_pairs(
    mock_worker_class: Any,  # noqa: ANN401
    mock_window: MagicMock,
) -> None:
    """Language codes are preserved in the constructor call."""
    mock_worker_class.is_busy.return_value = False
    tasks = [(1, "f.txt", "Vietnamese", "Japanese")]
    start_translation_worker(mock_window, tasks)
    task = mock_worker_class.call_args[0][0][0]
    assert task[2] == "Vietnamese"
    assert task[3] == "Japanese"


@patch(f"{_W}.TranslationWorker")
def test_start_worker_preserves_entry_ids(
    mock_worker_class: Any,  # noqa: ANN401
    mock_window: MagicMock,
) -> None:
    """Entry IDs are preserved exactly."""
    mock_worker_class.is_busy.return_value = False
    tasks = [(999, "f.txt", "en", "fr"), (1000, "g.txt", "en", "de")]
    start_translation_worker(mock_window, tasks)
    passed_tasks = mock_worker_class.call_args[0][0]
    assert passed_tasks[0][0] == 999  # noqa: PLR2004
    assert passed_tasks[1][0] == 1000  # noqa: PLR2004


# ===========================================================================
# Cleanup callback — detailed behavior
# ===========================================================================


@patch(f"{_W}.TranslationWorker")
@patch(f"{_W}.resume_unfinished_translations")
def test_cleanup_runs_resume_even_if_worker_missing(
    mock_resume: Any,  # noqa: ANN401
    mock_worker_class: Any,  # noqa: ANN401
    mock_window: MagicMock,
) -> None:
    """Resume is called even if the worker was already removed."""
    mock_worker_class.is_busy.return_value = False
    worker = start_translation_worker(mock_window, [(1, "p", "en", "fr")])
    cleanup_fn = worker.finished.connect.call_args[0][0]
    mock_window._workers.clear()  # Remove all workers
    cleanup_fn()
    mock_resume.assert_called_once()


@patch(f"{_W}.TranslationWorker")
@patch(f"{_W}.resume_unfinished_translations")
def test_cleanup_does_not_remove_other_workers(
    mock_resume: Any,  # noqa: ANN401
    mock_worker_class: Any,  # noqa: ANN401
    mock_window: MagicMock,
) -> None:
    """Cleanup does not affect unrelated workers."""
    mock_worker_class.is_busy.return_value = False
    other = MagicMock()
    mock_window._workers = [other]
    worker = start_translation_worker(mock_window, [(1, "p", "en", "fr")])
    cleanup_fn = worker.finished.connect.call_args[0][0]
    cleanup_fn()
    assert other in mock_window._workers
    assert len(mock_window._workers) == 1


@patch(f"{_W}.TranslationWorker")
@patch(f"{_W}.resume_unfinished_translations")
def test_cleanup_handles_empty_workers_list(
    mock_resume: Any,  # noqa: ANN401
    mock_worker_class: Any,  # noqa: ANN401
    mock_window: MagicMock,
) -> None:
    """Cleanup handles empty _workers list gracefully."""
    mock_worker_class.is_busy.return_value = False
    worker = start_translation_worker(mock_window, [(1, "p", "en", "fr")])
    cleanup_fn = worker.finished.connect.call_args[0][0]
    mock_window._workers = []
    cleanup_fn()  # Should not raise
    mock_resume.assert_called_once()


# ===========================================================================
# Multiple workers — concurrent management
# ===========================================================================


@patch(f"{_W}.TranslationWorker")
def test_five_workers_concurrent(
    mock_worker_class: Any,  # noqa: ANN401
    mock_window: MagicMock,
) -> None:
    """Five concurrent workers all appear in _workers list."""
    mock_worker_class.is_busy.return_value = False
    workers = [MagicMock() for _ in range(5)]
    mock_worker_class.side_effect = workers

    for i, w in enumerate(workers):
        mock_worker_class.return_value = w
        mock_worker_class.side_effect = None
        mock_worker_class.return_value = w
        start_translation_worker(mock_window, [(i, "p", "en", "fr")])

    assert len(mock_window._workers) == 5  # noqa: PLR2004


@patch(f"{_W}.TranslationWorker")
@patch(f"{_W}.resume_unfinished_translations")
def test_cleanup_middle_worker(
    mock_resume: Any,  # noqa: ANN401
    mock_worker_class: Any,  # noqa: ANN401
    mock_window: MagicMock,
) -> None:
    """Cleaning up a middle worker leaves others intact."""
    mock_worker_class.is_busy.return_value = False
    w1 = MagicMock()
    w2 = MagicMock()
    w3 = MagicMock()
    mock_window._workers = [w1]
    mock_worker_class.return_value = w2
    start_translation_worker(mock_window, [(1, "p", "en", "fr")])
    mock_worker_class.return_value = w3
    start_translation_worker(mock_window, [(2, "p", "en", "de")])

    # Cleanup w2 (middle)
    cleanup_w2 = w2.finished.connect.call_args[0][0]
    cleanup_w2()

    assert w1 in mock_window._workers
    assert w2 not in mock_window._workers
    assert w3 in mock_window._workers


# ===========================================================================
# resume — edge cases and parametrized tests
# ===========================================================================


@patch(f"{_W}.get_unfinished_history")
@patch(f"{_W}.QApplication")
@patch(f"{_W}.start_translation_worker")
def test_resume_with_many_tasks(
    mock_start: Any,  # noqa: ANN401
    mock_qapp: Any,  # noqa: ANN401
    mock_get_history: Any,  # noqa: ANN401
    mock_window: MagicMock,
) -> None:
    """Resume handles 50 unfinished tasks."""
    tasks = [(i, f"/file{i}.txt", "en", "fr") for i in range(50)]
    mock_get_history.return_value = tasks
    mock_qapp.topLevelWidgets.return_value = [mock_window]
    mock_start.return_value = MagicMock()

    resume_unfinished_translations()

    assert len(mock_start.call_args[0][1]) == 50  # noqa: PLR2004


@patch(f"{_W}.get_unfinished_history")
@patch(f"{_W}.QApplication")
@patch(f"{_W}.start_translation_worker")
def test_resume_does_not_call_start_when_no_window(
    mock_start: Any,  # noqa: ANN401
    mock_qapp: Any,  # noqa: ANN401
    mock_get_history: Any,  # noqa: ANN401
) -> None:
    """Resume does not call start when no QMainWindow found."""
    mock_get_history.return_value = [(1, "p", "en", "fr")]
    non_mw = MagicMock()
    non_mw.inherits.return_value = False
    mock_qapp.topLevelWidgets.return_value = [non_mw]

    resume_unfinished_translations()

    mock_start.assert_not_called()


@patch(f"{_W}.get_unfinished_history")
def test_resume_empty_returns_none_type(
    mock_get_history: Any,  # noqa: ANN401
) -> None:
    """Resume returns exactly None (not False, not 0)."""
    mock_get_history.return_value = []
    result = resume_unfinished_translations()
    assert result is None
    assert type(result) is type(None)  # noqa: E721


@patch(f"{_W}.get_unfinished_history")
@patch(f"{_W}.QApplication")
@patch(f"{_W}.start_translation_worker")
def test_resume_return_type_matches_start(
    mock_start: Any,  # noqa: ANN401
    mock_qapp: Any,  # noqa: ANN401
    mock_get_history: Any,  # noqa: ANN401
    mock_window: MagicMock,
) -> None:
    """Resume returns exactly what start_translation_worker returns."""
    sentinel = object()
    mock_get_history.return_value = [(1, "p", "en", "fr")]
    mock_qapp.topLevelWidgets.return_value = [mock_window]
    mock_start.return_value = sentinel

    result = resume_unfinished_translations()

    assert result is sentinel


# ===========================================================================
# Window _workers attribute creation
# ===========================================================================


@patch(f"{_W}.TranslationWorker")
def test_workers_list_type_is_list(
    mock_worker_class: Any,  # noqa: ANN401
    mock_window: MagicMock,
) -> None:
    """_workers attribute is a list."""
    mock_worker_class.is_busy.return_value = False
    if hasattr(mock_window, "_workers"):
        delattr(mock_window, "_workers")
    start_translation_worker(mock_window, [(1, "p", "en", "fr")])
    assert isinstance(mock_window._workers, list)


@patch(f"{_W}.TranslationWorker")
def test_workers_list_contains_exactly_one_after_start(
    mock_worker_class: Any,  # noqa: ANN401
    mock_window: MagicMock,
) -> None:
    """_workers list has exactly one entry after single start."""
    mock_worker_class.is_busy.return_value = False
    if hasattr(mock_window, "_workers"):
        delattr(mock_window, "_workers")
    start_translation_worker(mock_window, [(1, "p", "en", "fr")])
    assert len(mock_window._workers) == 1


@patch(f"{_W}.TranslationWorker")
def test_busy_check_does_not_create_workers_list(
    mock_worker_class: Any,  # noqa: ANN401
    mock_window: MagicMock,
) -> None:
    """When busy, _workers list is NOT created."""
    mock_worker_class.is_busy.return_value = True
    if hasattr(mock_window, "_workers"):
        delattr(mock_window, "_workers")
    start_translation_worker(mock_window, [(1, "p", "en", "fr")])
    assert not hasattr(mock_window, "_workers")


# ===========================================================================
# Parametrized task variations
# ===========================================================================


@pytest.mark.parametrize(
    "task",
    [
        (1, "/file.txt", "English", "French"),
        (2, "/file.docx", "Vietnamese", "Japanese"),
        (3, "/file.pdf", "Spanish", "Chinese (Simplified)"),
        (4, "/file.xlsx", "Korean", "Arabic"),
    ],
)
@patch(f"{_W}.TranslationWorker")
def test_start_worker_with_various_task_types(
    mock_worker_class: Any,  # noqa: ANN401
    mock_window: MagicMock,
    task: tuple,
) -> None:
    """Worker handles various file types and language pairs."""
    mock_worker_class.is_busy.return_value = False
    start_translation_worker(mock_window, [task])
    mock_worker_class.assert_called_once_with([task])


@pytest.mark.parametrize("count", [1, 2, 5, 10])
@patch(f"{_W}.TranslationWorker")
def test_start_worker_various_task_counts(
    mock_worker_class: Any,  # noqa: ANN401
    mock_window: MagicMock,
    count: int,
) -> None:
    """Worker handles various task list sizes."""
    mock_worker_class.is_busy.return_value = False
    tasks = [(i, f"/file{i}.txt", "en", "fr") for i in range(count)]
    start_translation_worker(mock_window, tasks)
    assert len(mock_worker_class.call_args[0][0]) == count


# ===========================================================================
# NEW TESTS — Expanded cleanup and resume coverage
# ===========================================================================


@patch(f"{_W}.TranslationWorker")
def test_cleanup_calls_resume(
    mock_worker_class: Any,  # noqa: ANN401
    mock_window: MagicMock,
) -> None:
    """Cleanup callback calls resume_unfinished_translations."""
    mock_worker_class.is_busy.return_value = False
    worker_instance = mock_worker_class.return_value
    worker_instance.finished = MagicMock()

    start_translation_worker(mock_window, [(1, "/f.txt", "en", "fr")])

    # Get the cleanup function from the finished.connect call
    cleanup = worker_instance.finished.connect.call_args[0][0]
    with patch(f"{_W}.resume_unfinished_translations") as mock_resume:
        cleanup()
    mock_resume.assert_called_once()


@patch(f"{_W}.TranslationWorker")
def test_cleanup_removes_correct_worker(
    mock_worker_class: Any,  # noqa: ANN401
    mock_window: MagicMock,
) -> None:
    """Cleanup removes only the specific worker from _workers."""
    mock_worker_class.is_busy.return_value = False
    worker_instance = mock_worker_class.return_value
    worker_instance.finished = MagicMock()

    # Pre-populate _workers with another worker
    mock_window._workers = [MagicMock()]
    existing_count = len(mock_window._workers)

    start_translation_worker(mock_window, [(1, "/f.txt", "en", "fr")])

    cleanup = worker_instance.finished.connect.call_args[0][0]
    with patch(f"{_W}.resume_unfinished_translations"):
        cleanup()
    # The pre-existing worker should still be there
    assert len(mock_window._workers) == existing_count


@patch(f"{_W}.TranslationWorker")
def test_worker_not_double_appended(
    mock_worker_class: Any,  # noqa: ANN401
    mock_window: MagicMock,
) -> None:
    """Worker is appended to _workers exactly once."""
    mock_worker_class.is_busy.return_value = False
    mock_window._workers = []

    start_translation_worker(mock_window, [(1, "/f.txt", "en", "fr")])
    assert len(mock_window._workers) == 1


@patch(f"{_W}.TranslationWorker")
def test_worker_start_called_exactly_once(
    mock_worker_class: Any,  # noqa: ANN401
    mock_window: MagicMock,
) -> None:
    """Worker.start() is called exactly once."""
    mock_worker_class.is_busy.return_value = False
    worker_instance = mock_worker_class.return_value

    start_translation_worker(mock_window, [(1, "/f.txt", "en", "fr")])
    worker_instance.start.assert_called_once()


@patch(f"{_W}.TranslationWorker")
def test_worker_finished_signal_connected(
    mock_worker_class: Any,  # noqa: ANN401
    mock_window: MagicMock,
) -> None:
    """Worker.finished signal has exactly one connection."""
    mock_worker_class.is_busy.return_value = False
    worker_instance = mock_worker_class.return_value
    worker_instance.finished = MagicMock()

    start_translation_worker(mock_window, [(1, "/f.txt", "en", "fr")])
    worker_instance.finished.connect.assert_called_once()


@patch(f"{_W}.get_unfinished_history", return_value=[])
@patch(f"{_W}.QApplication")
def test_resume_returns_none_when_no_unfinished(
    _mock_app: MagicMock,
    _mock_history: MagicMock,
) -> None:
    """resume_unfinished_translations returns None with no pending tasks."""
    result = resume_unfinished_translations()
    assert result is None


@patch(f"{_W}.get_unfinished_history")
@patch(f"{_W}.QApplication")
def test_resume_queries_correct_statuses(
    _mock_app: MagicMock,
    mock_history: MagicMock,
) -> None:
    """resume_unfinished_translations queries for Pending and Translating."""
    mock_history.return_value = []
    resume_unfinished_translations()
    call_kwargs = mock_history.call_args[1]
    assert "Pending" in call_kwargs["statuses"]
    assert "Translating" in call_kwargs["statuses"]


@patch(f"{_W}.TranslationWorker")
def test_empty_task_list_creates_worker(
    mock_worker_class: Any,  # noqa: ANN401
    mock_window: MagicMock,
) -> None:
    """Worker is created even with empty task list (upstream validation)."""
    mock_worker_class.is_busy.return_value = False
    result = start_translation_worker(mock_window, [])
    assert result is not None
    mock_worker_class.assert_called_once_with([])


# ───────────────────────────────────────────────────────────────────
# Test: aboutToQuit drains in-flight workers
# ───────────────────────────────────────────────────────────────────


class TestStopTranslationWorkersOnQuit:
    """``_stop_translation_workers_on_quit`` waits on every tracked worker.

    Pin the session-shutdown contract — without this hook,
    quitting the app mid-translation surfaces "QThread destroyed
    while still running" warnings and the in-flight HTTP / file
    I/O is torn down ungracefully.
    """

    def test_stops_and_waits_each_tracked_worker(self) -> None:
        """Every worker in _TRACKED_WORKERS gets stop() then wait(2000)."""
        from unittest.mock import MagicMock  # noqa: PLC0415

        from src.ui import worker_utils  # noqa: PLC0415

        # Reset the tracker to a known state.
        worker_utils._TRACKED_WORKERS.clear()

        fake1 = MagicMock()
        fake2 = MagicMock()
        worker_utils._TRACKED_WORKERS.add(fake1)
        worker_utils._TRACKED_WORKERS.add(fake2)

        worker_utils._stop_translation_workers_on_quit()

        fake1.stop.assert_called_once()
        fake2.stop.assert_called_once()
        fake1.wait.assert_called_once_with(2000)
        fake2.wait.assert_called_once_with(2000)
        assert set() == worker_utils._TRACKED_WORKERS, (
            "Drain must clear the tracker so a stale reference can't "
            "outlive the QApplication"
        )

    def test_drain_swallows_per_worker_exceptions(self) -> None:
        """One worker raising on stop() doesn't block the rest of the drain."""
        from unittest.mock import MagicMock  # noqa: PLC0415

        from src.ui import worker_utils  # noqa: PLC0415

        worker_utils._TRACKED_WORKERS.clear()
        bad = MagicMock()
        bad.stop.side_effect = RuntimeError("boom")
        good = MagicMock()
        worker_utils._TRACKED_WORKERS.add(bad)
        worker_utils._TRACKED_WORKERS.add(good)

        # Must not raise — finally-block on app-quit can't surface
        # an exception or the QApplication doesn't shut cleanly.
        worker_utils._stop_translation_workers_on_quit()

        good.stop.assert_called_once()
        good.wait.assert_called_once_with(2000)
        assert set() == worker_utils._TRACKED_WORKERS

    def test_start_translation_worker_registers_in_tracker(self) -> None:
        """``start_translation_worker`` adds the new worker to _TRACKED_WORKERS."""
        from unittest.mock import MagicMock, patch  # noqa: PLC0415

        from src.ui import worker_utils  # noqa: PLC0415

        worker_utils._TRACKED_WORKERS.clear()

        # Stub a fake QMainWindow + bypass the real TranslationWorker
        # so we can assert tracker membership without spinning up a
        # real QThread.
        fake_window = MagicMock()
        fake_window._workers = []  # presence avoids hasattr branch

        with patch(
            "src.ui.worker_utils.TranslationWorker.is_busy",
            return_value=False,
        ), patch(
            "src.ui.worker_utils.TranslationWorker",
        ) as mock_cls:
            mock_worker = MagicMock()
            mock_cls.return_value = mock_worker
            mock_cls.is_busy = lambda: False
            result = worker_utils.start_translation_worker(
                fake_window, tasks=[(1, "/tmp/x", "English", "French")],
            )

        assert result is mock_worker
        assert mock_worker in worker_utils._TRACKED_WORKERS
        worker_utils._TRACKED_WORKERS.clear()

    def test_cleanup_callback_discards_from_tracker(self) -> None:
        """Worker.finished → cleanup → tracker no longer holds the worker."""
        from unittest.mock import MagicMock, patch  # noqa: PLC0415

        from src.ui import worker_utils  # noqa: PLC0415

        worker_utils._TRACKED_WORKERS.clear()

        fake_window = MagicMock()
        fake_window._workers = []

        with patch(
            "src.ui.worker_utils.TranslationWorker",
        ) as mock_cls:
            # Stub ``is_busy`` directly on the patched class so the
            # ``not TranslationWorker.is_busy()`` branch evaluates True
            # and the worker actually gets created + tracked.
            mock_cls.is_busy = lambda: False
            mock_worker = MagicMock()
            mock_cls.return_value = mock_worker
            worker_utils.start_translation_worker(
                fake_window, tasks=[(1, "/tmp/x", "English", "French")],
            )
            assert mock_worker in worker_utils._TRACKED_WORKERS

            # Capture the cleanup callback that was wired to .finished.connect.
            cleanup_cb = mock_worker.finished.connect.call_args[0][0]
            # Resume tries to query the DB — stub it so cleanup doesn't
            # explode looking for unfinished tasks.
            with patch(
                "src.ui.worker_utils.resume_unfinished_translations",
                return_value=None,
            ):
                cleanup_cb()

        assert mock_worker not in worker_utils._TRACKED_WORKERS
