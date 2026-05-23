"""Tests for DubbingPage UI interactions.

Covers page construction, widget structure, stacked view switching,
file selection and drop handling, clear all, generate flow,
worker lifecycle, theme/language application, and the _DubbingWorker
class-level busy flag.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
)

# ---------------------------------------------------------------------------
# Module-level patch path constants
# ---------------------------------------------------------------------------
_MOD = "src.ui.pages.dubbing"
_HIST_MOD = "src.ui.pages.dubbing_history"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _auto_mock_blocking_dialogs():
    """Auto-mocks modal dialogs on the dubbing page so tests don't hang.

    Also stubs FFmpeg to report "available" so test builds don't fail on
    machines without FFmpeg installed. Individual tests can override these
    with their own ``@patch`` to assert specific interactions.
    """
    with (
        patch(
            "src.ui.pages.dubbing.CustomConfirmDialog.confirm",
            return_value=True,
        ),
        patch("src.ui.pages.dubbing.CustomMessageDialog.show_message"),
        patch(
            "src.core.speech_engine.check_ffmpeg_available",
            return_value=True,
        ),
    ):
        yield


@pytest.fixture()
def _mock_db():
    """Mocks database calls used during DubbingPage and DubbingHistoryPage init."""
    with (
        patch(f"{_HIST_MOD}.get_dubbing_fingerprint", return_value=None),
        patch(f"{_HIST_MOD}.get_dubbing_history", return_value=[]),
        patch(f"{_MOD}.get_unfinished_dubbing", return_value=[]),
    ):
        yield


@pytest.fixture()
def window(qtbot) -> QMainWindow:
    """Creates a minimal QMainWindow for parenting."""
    w = QMainWindow()
    w.navigate_to_settings_tab = MagicMock()
    qtbot.addWidget(w)
    return w


@pytest.fixture()
def page(_mock_db, window, qtbot):
    """Creates a DubbingPage widget for testing."""
    from src.ui.pages.dubbing import DubbingPage  # noqa: PLC0415

    p = DubbingPage(window)
    qtbot.addWidget(p)
    return p


# ===================================================================
# Widget Construction
# ===================================================================


class TestConstruction:
    """Tests for DubbingPage widget construction."""

    def test_page_created(self, page) -> None:  # noqa: ANN001
        """Page is created without error."""
        assert page is not None

    def test_has_stack_widget(self, page) -> None:  # noqa: ANN001
        """Page has a QStackedWidget for view switching."""
        assert isinstance(page.stack, QStackedWidget)

    def test_stack_has_two_views(self, page) -> None:  # noqa: ANN001
        """Stack has exactly 2 views (history and files)."""
        assert page.stack.count() == 2  # noqa: PLR2004

    def test_initial_view_is_history(self, page) -> None:  # noqa: ANN001
        """Initial view shows the history view (index 0)."""
        assert page.stack.currentIndex() == 0

    def test_has_drop_area(self, page) -> None:  # noqa: ANN001
        """Page has a FileDropWidget."""
        from src.ui.components import FileDropWidget  # noqa: PLC0415

        assert isinstance(page.drop_area, FileDropWidget)

    def test_has_history_view(self, page) -> None:  # noqa: ANN001
        """Page embeds a DubbingHistoryPage."""
        from src.ui.pages.dubbing_history import DubbingHistoryPage  # noqa: PLC0415

        assert isinstance(page.history_view, DubbingHistoryPage)

    def test_has_generate_button(self, page) -> None:  # noqa: ANN001
        """Page has a generate button."""
        assert isinstance(page.generate_btn, QPushButton)

    def test_has_clear_all_button(self, page) -> None:  # noqa: ANN001
        """Page has a clear-all button."""
        assert isinstance(page.clear_all_btn, QPushButton)

    def test_has_files_badge(self, page) -> None:  # noqa: ANN001
        """Page has a file count badge label."""
        assert isinstance(page.files_badge, QLabel)

    def test_has_section_label(self, page) -> None:  # noqa: ANN001
        """Page has a 'files selected' section label."""
        assert isinstance(page.section_label, QLabel)

    def test_generate_button_disabled_initially(self, page) -> None:  # noqa: ANN001
        """Generate button is disabled when no files are selected."""
        assert not page.generate_btn.isEnabled()

    def test_selected_files_empty_initially(self, page) -> None:  # noqa: ANN001
        """No files are selected at construction time."""
        assert page.selected_files == []

    def test_badge_shows_zero_initially(self, page) -> None:  # noqa: ANN001
        """File count badge shows '0' initially."""
        assert page.files_badge.text() == "0"

    def test_worker_is_none_initially(self, page) -> None:  # noqa: ANN001
        """No worker is running at construction time."""
        assert page._worker is None

    def test_pending_tasks_empty_initially(self, page) -> None:  # noqa: ANN001
        """No pending tasks at construction time."""
        assert page._pending_tasks == []


# ===================================================================
# View Switching (_update_ui_state)
# ===================================================================


class TestViewSwitching:
    """Tests for stacked view switching based on file selection."""

    def test_no_files_shows_history_view(self, page) -> None:  # noqa: ANN001
        """With no files, stack shows history view (index 0)."""
        page.selected_files.clear()
        page._update_ui_state()
        assert page.stack.currentIndex() == 0

    def test_files_selected_shows_files_view(self, page) -> None:  # noqa: ANN001
        """With files selected, stack switches to files view (index 1)."""
        page.selected_files = ["/tmp/test.mp4"]
        page._update_ui_state()
        assert page.stack.currentIndex() == 1

    def test_badge_updates_with_file_count(self, page) -> None:  # noqa: ANN001
        """File count badge updates when files are added."""
        page.selected_files = ["/tmp/a.mp4", "/tmp/b.mkv", "/tmp/c.avi"]
        page._update_ui_state()
        assert page.files_badge.text() == "3"

    def test_generate_button_enabled_with_files(self, page) -> None:  # noqa: ANN001
        """Generate button is enabled when files are selected."""
        page.selected_files = ["/tmp/test.mp4"]
        page._update_ui_state()
        assert page.generate_btn.isEnabled()

    def test_generate_button_disabled_without_files(self, page) -> None:  # noqa: ANN001
        """Generate button is disabled after files are cleared."""
        page.selected_files = ["/tmp/test.mp4"]
        page._update_ui_state()
        page.selected_files.clear()
        page._update_ui_state()
        assert not page.generate_btn.isEnabled()


# ===================================================================
# File Handling (_handle_files_dropped)
# ===================================================================


class TestFileSelection:
    """Tests for file selection and drop interactions."""

    def test_files_dropped_switches_to_files_view(
        self,
        page,  # noqa: ANN001
        tmp_path,
    ) -> None:
        """Drop files switches stack to files view (index 1)."""
        video = tmp_path / "test.mp4"
        video.write_bytes(b"\x00" * 100)

        page._handle_files_dropped([str(video)])
        assert page.stack.currentIndex() == 1

    def test_files_dropped_updates_file_count(
        self,
        page,  # noqa: ANN001
        tmp_path,
    ) -> None:
        """Dropping 3 video files results in 3 items in selected_files."""
        videos = []
        for name in ("a.mp4", "b.mkv", "c.avi"):
            f = tmp_path / name
            f.write_bytes(b"\x00" * 100)
            videos.append(str(f))

        page._handle_files_dropped(videos)
        assert len(page.selected_files) == 3  # noqa: PLR2004

    def test_files_dropped_updates_badge(
        self,
        page,  # noqa: ANN001
        tmp_path,
    ) -> None:
        """File count badge reflects the number of selected files."""
        video = tmp_path / "movie.mp4"
        video.write_bytes(b"\x00" * 100)

        page._handle_files_dropped([str(video)])
        assert page.files_badge.text() == "1"

    def test_unsupported_file_ignored(
        self,
        page,  # noqa: ANN001
        tmp_path,
    ) -> None:
        """Non-video files (e.g. .txt) are not added to selected_files."""
        txt = tmp_path / "notes.txt"
        txt.write_text("hello", encoding="utf-8")

        with patch(f"{_MOD}.CustomMessageDialog.show_message"):
            page._handle_files_dropped([str(txt)])

        assert len(page.selected_files) == 0

    def test_duplicate_file_not_added(
        self,
        page,  # noqa: ANN001
        tmp_path,
    ) -> None:
        """Dropping the same file twice does not create duplicates."""
        video = tmp_path / "dup.mp4"
        video.write_bytes(b"\x00" * 100)
        path = str(video)

        page._handle_files_dropped([path])
        page._handle_files_dropped([path])
        assert len(page.selected_files) == 1

    def test_empty_file_ignored(
        self,
        page,  # noqa: ANN001
        tmp_path,
    ) -> None:
        """Empty (0-byte) video files are rejected."""
        video = tmp_path / "empty.mp4"
        video.write_bytes(b"")

        with patch(f"{_MOD}.CustomMessageDialog.show_message"):
            page._handle_files_dropped([str(video)])

        assert len(page.selected_files) == 0

    def test_mixed_valid_and_invalid_files(
        self,
        page,  # noqa: ANN001
        tmp_path,
    ) -> None:
        """Only valid video files are accepted from a mixed batch."""
        mp4 = tmp_path / "good.mp4"
        mp4.write_bytes(b"\x00" * 100)
        txt = tmp_path / "bad.txt"
        txt.write_text("hello", encoding="utf-8")

        with patch(f"{_MOD}.CustomMessageDialog.show_message"):
            page._handle_files_dropped([str(mp4), str(txt)])

        assert len(page.selected_files) == 1
        assert page.selected_files[0] == str(mp4)

    def test_empty_drop_opens_file_dialog(
        self,
        page,  # noqa: ANN001
    ) -> None:
        """Dropping no files triggers QFileDialog.getOpenFileNames."""
        with patch(
            f"{_MOD}.QFileDialog.getOpenFileNames",
            return_value=([], ""),
        ) as mock_dialog:
            page._handle_files_dropped([])
            mock_dialog.assert_called_once()


# ===================================================================
# Clear All (_handle_clear_all)
# ===================================================================


class TestClearAll:
    """Tests for _handle_clear_all behavior."""

    def test_clear_all_empties_selected_files(
        self,
        page,  # noqa: ANN001
        tmp_path,
    ) -> None:
        """_handle_clear_all empties the selected_files list."""
        video = tmp_path / "test.mp4"
        video.write_bytes(b"\x00" * 100)
        page._handle_files_dropped([str(video)])

        page._handle_clear_all()
        assert page.selected_files == []

    def test_clear_all_switches_to_history_view(
        self,
        page,  # noqa: ANN001
        tmp_path,
    ) -> None:
        """_handle_clear_all switches back to history view."""
        video = tmp_path / "test.mp4"
        video.write_bytes(b"\x00" * 100)
        page._handle_files_dropped([str(video)])
        assert page.stack.currentIndex() == 1

        page._handle_clear_all()
        assert page.stack.currentIndex() == 0

    def test_clear_all_resets_badge(
        self,
        page,  # noqa: ANN001
        tmp_path,
    ) -> None:
        """_handle_clear_all resets the file count badge to '0'."""
        video = tmp_path / "test.mp4"
        video.write_bytes(b"\x00" * 100)
        page._handle_files_dropped([str(video)])

        page._handle_clear_all()
        assert page.files_badge.text() == "0"

    def test_clear_all_disables_generate(
        self,
        page,  # noqa: ANN001
        tmp_path,
    ) -> None:
        """_handle_clear_all disables the generate button."""
        video = tmp_path / "test.mp4"
        video.write_bytes(b"\x00" * 100)
        page._handle_files_dropped([str(video)])
        assert page.generate_btn.isEnabled()

        page._handle_clear_all()
        assert not page.generate_btn.isEnabled()


# ===================================================================
# Generate (_handle_generate)
# ===================================================================


class TestHandleGenerate:
    """Tests for _handle_generate and requirements checking."""

    def test_generate_noop_when_no_files(self, page) -> None:  # noqa: ANN001
        """_handle_generate does nothing when selected_files is empty."""
        page.selected_files.clear()
        page._handle_generate()  # Should not raise

    def test_generate_noop_when_worker_running(
        self,
        page,  # noqa: ANN001
    ) -> None:
        """_handle_generate does nothing when a worker is already running."""
        page.selected_files = ["/tmp/test.mp4"]
        page._worker = MagicMock()  # Simulate a running worker
        page._handle_generate()
        # No dialog or crash expected — early return

    @patch(f"{_MOD}.require_setup", return_value=False)
    @patch(f"{_MOD}.load_setting", return_value="faster-whisper")
    def test_generate_checks_llm_setup(
        self,
        mock_load,
        mock_require,
        page,  # noqa: ANN001
    ) -> None:
        """Generate with missing LLM setup blocks and calls require_setup."""
        page.selected_files = ["/tmp/test.mp4"]
        page._handle_generate()
        # require_setup should have been called (for LLM or STT check)
        mock_require.assert_called()

    @patch(f"{_MOD}._DubbingWorker")
    @patch(f"{_MOD}.add_dubbing_entry", return_value=1)
    @patch(
        f"{_MOD}.LanguageSelectionDialog.get_selection",
        return_value=("English", "Vietnamese", None, True),
    )
    @patch(f"{_MOD}.DubbingPage._check_all_requirements", return_value=True)
    def test_generate_shows_language_dialog(  # noqa: PLR0913
        self,
        mock_req,
        mock_dialog,
        mock_add,
        mock_worker_cls,
        page,  # noqa: ANN001
        tmp_path,
    ) -> None:
        """Generate with valid setup shows the language selection dialog."""
        video = tmp_path / "test.mp4"
        video.write_bytes(b"\x00" * 100)
        page.selected_files = [str(video)]

        mock_worker = MagicMock()
        mock_worker_cls.return_value = mock_worker

        with (
            patch(f"{_HIST_MOD}.get_dubbing_fingerprint", return_value=None),
            patch(f"{_HIST_MOD}.get_dubbing_history", return_value=[]),
        ):
            page._handle_generate()

        mock_dialog.assert_called_once()

    @patch(f"{_MOD}._DubbingWorker")
    @patch(f"{_MOD}.add_dubbing_entry", return_value=1)
    @patch(
        f"{_MOD}.LanguageSelectionDialog.get_selection",
        return_value=("English", "Vietnamese", None, True),
    )
    @patch(f"{_MOD}.DubbingPage._check_all_requirements", return_value=True)
    def test_generate_starts_worker(  # noqa: PLR0913
        self,
        mock_req,
        mock_dialog,
        mock_add,
        mock_worker_cls,
        page,  # noqa: ANN001
        tmp_path,
    ) -> None:
        """After dialog acceptance, worker is created and started."""
        video = tmp_path / "test.mp4"
        video.write_bytes(b"\x00" * 100)
        page.selected_files = [str(video)]

        mock_worker = MagicMock()
        mock_worker_cls.return_value = mock_worker

        with (
            patch(f"{_HIST_MOD}.get_dubbing_fingerprint", return_value=None),
            patch(f"{_HIST_MOD}.get_dubbing_history", return_value=[]),
        ):
            page._handle_generate()

        mock_worker.start.assert_called_once()

    @patch(f"{_MOD}._DubbingWorker")
    @patch(f"{_MOD}.add_dubbing_entry", return_value=1)
    @patch(
        f"{_MOD}.LanguageSelectionDialog.get_selection",
        return_value=("English", "Vietnamese", None, True),
    )
    @patch(f"{_MOD}.DubbingPage._check_all_requirements", return_value=True)
    def test_generate_clears_selection_after_start(  # noqa: PLR0913
        self,
        mock_req,
        mock_dialog,
        mock_add,
        mock_worker_cls,
        page,  # noqa: ANN001
        tmp_path,
    ) -> None:
        """After starting the worker, selected files are cleared."""
        video = tmp_path / "test.mp4"
        video.write_bytes(b"\x00" * 100)
        page.selected_files = [str(video)]

        mock_worker = MagicMock()
        mock_worker_cls.return_value = mock_worker

        with (
            patch(f"{_HIST_MOD}.get_dubbing_fingerprint", return_value=None),
            patch(f"{_HIST_MOD}.get_dubbing_history", return_value=[]),
        ):
            page._handle_generate()

        assert page.selected_files == []

    @patch(
        f"{_MOD}.LanguageSelectionDialog.get_selection",
        return_value=("English", "Vietnamese", None, False),
    )
    @patch(f"{_MOD}.DubbingPage._check_all_requirements", return_value=True)
    def test_generate_cancelled_dialog_keeps_files(
        self,
        mock_req,
        mock_dialog,
        page,  # noqa: ANN001
    ) -> None:
        """Files are kept when user cancels the language dialog."""
        page.selected_files = ["/tmp/test.mp4"]
        page._handle_generate()
        assert page.selected_files == ["/tmp/test.mp4"]

    @patch(f"{_MOD}.add_dubbing_entry", return_value=None)
    @patch(
        f"{_MOD}.LanguageSelectionDialog.get_selection",
        return_value=("English", "Vietnamese", None, True),
    )
    @patch(f"{_MOD}.DubbingPage._check_all_requirements", return_value=True)
    def test_generate_no_worker_when_db_fails(
        self,
        mock_req,
        mock_dialog,
        mock_add,
        page,  # noqa: ANN001
        tmp_path,
    ) -> None:
        """No worker is started when DB entry creation returns None."""
        video = tmp_path / "test.mp4"
        video.write_bytes(b"\x00" * 100)
        page.selected_files = [str(video)]

        with (
            patch(f"{_HIST_MOD}.get_dubbing_fingerprint", return_value=None),
            patch(f"{_HIST_MOD}.get_dubbing_history", return_value=[]),
        ):
            page._handle_generate()

        assert page._worker is None


# ===================================================================
# Worker Lifecycle
# ===================================================================


class TestWorkerLifecycle:
    """Tests for worker lifecycle from the UI perspective."""

    @patch(f"{_MOD}._DubbingWorker")
    @patch(f"{_MOD}.add_dubbing_entry", return_value=1)
    @patch(
        f"{_MOD}.LanguageSelectionDialog.get_selection",
        return_value=("English", "Vietnamese", None, True),
    )
    @patch(f"{_MOD}.DubbingPage._check_all_requirements", return_value=True)
    def test_worker_stored_after_generate(  # noqa: PLR0913
        self,
        mock_req,
        mock_dialog,
        mock_add,
        mock_worker_cls,
        page,  # noqa: ANN001
        tmp_path,
    ) -> None:
        """After generate, page._worker references the created worker."""
        video = tmp_path / "test.mp4"
        video.write_bytes(b"\x00" * 100)
        page.selected_files = [str(video)]

        mock_worker = MagicMock()
        mock_worker_cls.return_value = mock_worker

        with (
            patch(f"{_HIST_MOD}.get_dubbing_fingerprint", return_value=None),
            patch(f"{_HIST_MOD}.get_dubbing_history", return_value=[]),
        ):
            page._handle_generate()

        assert page._worker is mock_worker

    def test_on_finished_clears_worker(self, page) -> None:  # noqa: ANN001
        """_on_finished cleans up the worker reference."""
        mock_worker = MagicMock()
        mock_worker.wait = MagicMock()
        page._worker = mock_worker

        with (
            patch(f"{_MOD}.load_setting", return_value=False),
            patch(f"{_MOD}.get_unfinished_dubbing", return_value=[]),
            patch(f"{_HIST_MOD}.get_dubbing_fingerprint", return_value=None),
            patch(f"{_HIST_MOD}.get_dubbing_history", return_value=[]),
        ):
            page._on_finished([])

        assert page._worker is None

    def test_on_finished_refreshes_history(self, page) -> None:  # noqa: ANN001
        """_on_finished triggers history refresh."""
        mock_worker = MagicMock()
        mock_worker.wait = MagicMock()
        page._worker = mock_worker

        with (
            patch(f"{_MOD}.load_setting", return_value=False),
            patch(f"{_MOD}.get_unfinished_dubbing", return_value=[]),
            patch(f"{_HIST_MOD}.get_dubbing_fingerprint", return_value=None),
            patch(f"{_HIST_MOD}.get_dubbing_history", return_value=[]),
        ):
            page.history_view.refresh_history = MagicMock()
            page._on_finished([])

        page.history_view.refresh_history.assert_called()

    def test_on_finished_updates_done_status(
        self,
        page,  # noqa: ANN001
    ) -> None:
        """_on_finished updates DB status to Done for each result."""
        mock_worker = MagicMock()
        mock_worker.wait = MagicMock()
        page._worker = mock_worker

        result = (
            1,
            "/out/video.mp4",
            "/out/sub.srt",
            "/out/trans.srt",
            "/out/voice.mp3",
        )

        with (
            patch(f"{_MOD}.load_setting", return_value=False),
            patch(f"{_MOD}.update_dubbing_status") as mock_status,
            patch(f"{_MOD}.get_unfinished_dubbing", return_value=[]),
            patch(f"{_HIST_MOD}.get_dubbing_fingerprint", return_value=None),
            patch(f"{_HIST_MOD}.get_dubbing_history", return_value=[]),
        ):
            page._on_finished([result])

        mock_status.assert_called_once()
        call_kwargs = mock_status.call_args[1]
        assert call_kwargs["output_path"] == "/out/video.mp4"

    def test_on_finished_auto_remove_deletes_entry(
        self,
        page,  # noqa: ANN001
        tmp_path,
    ) -> None:
        """_on_finished with auto_remove deletes the entry and output files."""
        mock_worker = MagicMock()
        mock_worker.wait = MagicMock()
        page._worker = mock_worker

        result = (1, "/nonexistent/video.mp4", "", "", "")

        with (
            patch(f"{_MOD}.load_setting", return_value=True),
            patch(f"{_MOD}.delete_dubbing_entry", return_value=[]) as mock_del,
            patch(f"{_MOD}.get_unfinished_dubbing", return_value=[]),
            patch(f"{_HIST_MOD}.get_dubbing_fingerprint", return_value=None),
            patch(f"{_HIST_MOD}.get_dubbing_history", return_value=[]),
            patch("shutil.rmtree"),
            patch(
                "src.utils.path_manager.get_dubbing_storage_dir",
                return_value=tmp_path / "storage",
            ),
        ):
            page._on_finished([result])

        mock_del.assert_called_once_with(1)


# ===================================================================
# Resume Pending (_resume_pending)
# ===================================================================


class TestResumePending:
    """Tests for _resume_pending auto-resume logic."""

    def test_resume_pending_no_unfinished(self, page) -> None:  # noqa: ANN001
        """_resume_pending does nothing when no unfinished tasks exist."""
        with patch(f"{_MOD}.get_unfinished_dubbing", return_value=[]):
            page._resume_pending()

        assert page._worker is None

    @patch(f"{_MOD}._DubbingWorker")
    def test_resume_pending_starts_worker(
        self,
        mock_worker_cls,
        page,  # noqa: ANN001
    ) -> None:
        """_resume_pending starts a worker when unfinished tasks exist."""
        mock_worker = MagicMock()
        mock_worker_cls.return_value = mock_worker

        # Format: (entry_id, source_path, src_lang, target_lang)
        unfinished = [(10, "/tmp/video.mp4", "English", "Vietnamese")]

        with patch(f"{_MOD}.get_unfinished_dubbing", return_value=unfinished):
            page._resume_pending()

        mock_worker.start.assert_called_once()

    def test_resume_pending_skips_when_worker_active(
        self,
        page,  # noqa: ANN001
    ) -> None:
        """_resume_pending does nothing when a worker is already running."""
        page._worker = MagicMock()
        page._resume_pending()
        # No crash, no new worker created


# ===================================================================
# Continue / Re-dub
# ===================================================================


class TestContinueAndRedub:
    """Tests for _handle_continue_dub and _handle_re_dub."""

    @patch(f"{_MOD}._DubbingWorker")
    @patch(f"{_MOD}.DubbingPage._check_all_requirements", return_value=True)
    def test_continue_dub_starts_worker(
        self,
        mock_req,
        mock_worker_cls,
        page,  # noqa: ANN001
    ) -> None:
        """_handle_continue_dub starts a worker with the given tasks."""
        mock_worker = MagicMock()
        mock_worker_cls.return_value = mock_worker

        tasks = [(5, "/tmp/video.mp4")]
        page._handle_continue_dub(tasks, "English", "Vietnamese")
        mock_worker.start.assert_called_once()

    @patch(f"{_MOD}.DubbingPage._check_all_requirements", return_value=False)
    def test_continue_dub_blocked_when_setup_missing(
        self,
        mock_req,
        page,  # noqa: ANN001
    ) -> None:
        """_handle_continue_dub is blocked when requirements check fails."""
        tasks = [(5, "/tmp/video.mp4")]
        page._handle_continue_dub(tasks, "English", "Vietnamese")
        assert page._worker is None

    @patch(f"{_MOD}._DubbingWorker")
    @patch(f"{_MOD}.update_dubbing_status")
    @patch(
        f"{_MOD}.LanguageSelectionDialog.get_selection",
        return_value=("English", "French", None, True),
    )
    @patch(f"{_MOD}.DubbingPage._check_all_requirements", return_value=True)
    def test_re_dub_starts_worker(  # noqa: PLR0913
        self,
        mock_req,
        mock_dialog,
        mock_status,
        mock_worker_cls,
        page,  # noqa: ANN001
    ) -> None:
        """_handle_re_dub shows language dialog and starts worker."""
        mock_worker = MagicMock()
        mock_worker_cls.return_value = mock_worker

        with (
            patch(f"{_HIST_MOD}.get_dubbing_fingerprint", return_value=None),
            patch(f"{_HIST_MOD}.get_dubbing_history", return_value=[]),
        ):
            page._handle_re_dub([(5, "/tmp/video.mp4")])

        mock_dialog.assert_called_once()
        mock_worker.start.assert_called_once()

    @patch(f"{_MOD}.DubbingPage._check_all_requirements", return_value=False)
    def test_re_dub_blocked_when_setup_missing(
        self,
        mock_req,
        page,  # noqa: ANN001
    ) -> None:
        """_handle_re_dub is blocked when requirements check fails."""
        page._handle_re_dub([(5, "/tmp/video.mp4")])
        assert page._worker is None

    @patch(
        f"{_MOD}.LanguageSelectionDialog.get_selection",
        return_value=("English", "French", None, False),
    )
    @patch(f"{_MOD}.DubbingPage._check_all_requirements", return_value=True)
    def test_re_dub_cancelled_dialog_no_worker(
        self,
        mock_req,
        mock_dialog,
        page,  # noqa: ANN001
    ) -> None:
        """Re-dub does nothing when user cancels language dialog."""
        page._handle_re_dub([(5, "/tmp/video.mp4")])
        assert page._worker is None


# ===================================================================
# Theme / Language
# ===================================================================


class TestThemeAndLanguage:
    """Tests for apply_theme and apply_language methods."""

    def test_apply_theme_runs(self, page) -> None:  # noqa: ANN001
        """apply_theme() completes without error."""
        page.apply_theme()

    def test_apply_language_runs(self, page) -> None:  # noqa: ANN001
        """apply_language() completes without error."""
        with (
            patch(f"{_HIST_MOD}.get_dubbing_fingerprint", return_value=None),
            patch(f"{_HIST_MOD}.get_dubbing_history", return_value=[]),
        ):
            page.apply_language()

    def test_apply_theme_updates_button_styles(self, page) -> None:  # noqa: ANN001
        """apply_theme updates styles for action buttons."""
        page.apply_theme()
        assert page.generate_btn.styleSheet()
        assert page.clear_all_btn.styleSheet()

    def test_apply_language_updates_button_text(self, page) -> None:  # noqa: ANN001
        """apply_language updates button labels."""
        with (
            patch(f"{_HIST_MOD}.get_dubbing_fingerprint", return_value=None),
            patch(f"{_HIST_MOD}.get_dubbing_history", return_value=[]),
        ):
            page.apply_language()

        assert page.generate_btn.text()
        assert page.clear_all_btn.text()
        assert page.section_label.text()

    def test_apply_theme_updates_badge_style(self, page) -> None:  # noqa: ANN001
        """apply_theme updates the files_badge stylesheet."""
        page.apply_theme()
        assert page.files_badge.styleSheet()


# ===================================================================
# _DubbingWorker class-level tests (no Qt thread)
# ===================================================================


class TestDubbingWorkerClassLevel:
    """Tests for _DubbingWorker class attributes and methods."""

    def test_is_busy_initially_false(self) -> None:
        """is_busy() returns False before any worker starts."""
        from src.ui.pages.dubbing import _DubbingWorker  # noqa: PLC0415

        _DubbingWorker._is_any_worker_running = False
        assert not _DubbingWorker.is_busy()

    def test_is_busy_when_flag_set(self) -> None:
        """is_busy() returns True when class flag is set."""
        from src.ui.pages.dubbing import _DubbingWorker  # noqa: PLC0415

        try:
            _DubbingWorker._is_any_worker_running = True
            assert _DubbingWorker.is_busy() is True
        finally:
            _DubbingWorker._is_any_worker_running = False

    def test_stop_sets_is_running_false(self) -> None:
        """Calling stop() sets _is_running to False."""
        from src.ui.pages.dubbing import _DubbingWorker  # noqa: PLC0415

        worker = _DubbingWorker.__new__(_DubbingWorker)
        worker._is_running = True
        worker.stop()
        assert worker._is_running is False

    def test_is_task_cancelled_when_worker_stopped(self) -> None:
        """``_is_task_cancelled`` returns True the moment ``stop()`` is called.

        The mid-pipeline cancel check fires on every step boundary
        (STT → translate → TTS → mix).  When ``stop()`` clears
        ``_is_running`` the check must trip immediately so the
        pipeline aborts before kicking off the next step.
        """
        from src.ui.pages.dubbing import _DubbingWorker  # noqa: PLC0415

        worker = _DubbingWorker.__new__(_DubbingWorker)
        worker._is_running = False  # stop() already flipped this
        # No DB lookup needed when worker is stopped — short-circuits
        # on the first ``if not self._is_running:`` check.
        assert worker._is_task_cancelled(entry_id=1) is True

    def test_is_task_cancelled_when_db_status_changed(self) -> None:
        """``_is_task_cancelled`` returns True when DB says the task is paused.

        User pauses a task mid-dub via the history table; the DB
        row status flips from ``Generating`` to ``Paused``.  The
        running worker must see this on the next check and bail
        without writing further checkpoints for that task.
        """
        from unittest.mock import patch  # noqa: PLC0415

        from src.ui.pages.dubbing import _DubbingWorker  # noqa: PLC0415

        worker = _DubbingWorker.__new__(_DubbingWorker)
        worker._is_running = True
        with patch(
            "src.ui.pages.dubbing.get_dubbing_entry_status",
            return_value="Paused",
        ):
            assert worker._is_task_cancelled(entry_id=1) is True

    def test_is_task_cancelled_when_task_is_generating(self) -> None:
        """Active ``Generating`` status keeps the pipeline running.

        The negative case: worker active AND DB status is the
        expected ``Generating`` value → cancel check returns False
        → pipeline proceeds to next step.
        """
        from unittest.mock import patch  # noqa: PLC0415

        from src.constants.history import STATUS_GENERATING  # noqa: PLC0415
        from src.ui.pages.dubbing import _DubbingWorker  # noqa: PLC0415

        worker = _DubbingWorker.__new__(_DubbingWorker)
        worker._is_running = True
        with patch(
            "src.ui.pages.dubbing.get_dubbing_entry_status",
            return_value=STATUS_GENERATING,
        ):
            assert worker._is_task_cancelled(entry_id=1) is False


# ===================================================================
# Factory function
# ===================================================================


class TestFactory:
    """Tests for the create_dubbing_page factory function."""

    def test_factory_returns_widget(self, _mock_db, window) -> None:  # noqa: ANN001
        """create_dubbing_page returns a QWidget."""
        from src.ui.pages.dubbing import create_dubbing_page  # noqa: PLC0415

        widget = create_dubbing_page(window)
        assert widget is not None


# ===================================================================
# Remove single file
# ===================================================================


class TestRemoveFile:
    """Tests for removing a single file from the selection."""

    def test_remove_file_decrements_count(
        self,
        page,  # noqa: ANN001
        tmp_path,
    ) -> None:
        """Removing a file decrements the selected file count."""
        a = tmp_path / "a.mp4"
        b = tmp_path / "b.mp4"
        a.write_bytes(b"\x00" * 100)
        b.write_bytes(b"\x00" * 100)
        page._handle_files_dropped([str(a), str(b)])
        assert len(page.selected_files) == 2  # noqa: PLR2004

        # Simulate removing one file via internal method
        widget = MagicMock()
        widget.setParent = MagicMock()
        widget.deleteLater = MagicMock()
        page._handle_remove_file(str(a), widget)

        assert len(page.selected_files) == 1
        assert str(a) not in page.selected_files

    def test_remove_last_file_switches_to_history(
        self,
        page,  # noqa: ANN001
        tmp_path,
    ) -> None:
        """Removing the last file switches back to history view."""
        video = tmp_path / "only.mp4"
        video.write_bytes(b"\x00" * 100)
        page._handle_files_dropped([str(video)])
        assert page.stack.currentIndex() == 1

        widget = MagicMock()
        widget.setParent = MagicMock()
        widget.deleteLater = MagicMock()
        page._handle_remove_file(str(video), widget)

        assert page.stack.currentIndex() == 0
        assert page.selected_files == []


# ===================================================================
# Edge Case: Directory Drop
# ===================================================================


class TestDubbingPageDirectoryDrop:
    """Tests for dropping a directory containing video files."""

    def test_directory_with_videos_adds_them(
        self,
        page,  # noqa: ANN001
        tmp_path,
    ) -> None:
        """Dropping a directory traverses it and adds video files."""
        subdir = tmp_path / "videos"
        subdir.mkdir()
        mp4 = subdir / "clip.mp4"
        mp4.write_bytes(b"\x00" * 100)
        mkv = subdir / "movie.mkv"
        mkv.write_bytes(b"\x00" * 100)

        page._handle_files_dropped([str(subdir)])

        assert str(mp4) in page.selected_files
        assert str(mkv) in page.selected_files
        assert page.stack.currentIndex() == 1

    def test_nested_directory_traversal(
        self,
        page,  # noqa: ANN001
        tmp_path,
    ) -> None:
        """Nested subdirectories are traversed recursively."""
        subdir = tmp_path / "videos" / "nested"
        subdir.mkdir(parents=True)
        avi = subdir / "deep.avi"
        avi.write_bytes(b"\x00" * 100)

        page._handle_files_dropped([str(tmp_path / "videos")])

        assert str(avi) in page.selected_files

    def test_hidden_files_in_directory_skipped(
        self,
        page,  # noqa: ANN001
        tmp_path,
    ) -> None:
        """Hidden files (dotfiles) inside directories are skipped."""
        subdir = tmp_path / "media"
        subdir.mkdir()
        hidden = subdir / ".hidden.mp4"
        hidden.write_bytes(b"\x00" * 100)
        visible = subdir / "visible.mp4"
        visible.write_bytes(b"\x00" * 100)

        page._handle_files_dropped([str(subdir)])

        assert str(hidden) not in page.selected_files
        assert str(visible) in page.selected_files


# ===================================================================
# Edge Case: Duplicate File Prevention
# ===================================================================


class TestDubbingPageDuplicateFilePrevention:
    """Tests that the same file cannot be added twice."""

    def test_same_file_dropped_twice_only_added_once(
        self,
        page,  # noqa: ANN001
        tmp_path,
    ) -> None:
        """Dropping the exact same file path twice results in a single entry."""
        video = tmp_path / "dup.mp4"
        video.write_bytes(b"\x00" * 100)

        page._handle_files_dropped([str(video)])
        page._handle_files_dropped([str(video)])

        assert page.selected_files.count(str(video)) == 1
        assert page.files_badge.text() == "1"

    def test_same_file_in_single_drop_only_added_once(
        self,
        page,  # noqa: ANN001
        tmp_path,
    ) -> None:
        """Same file appearing twice in one drop list is only added once."""
        video = tmp_path / "dup2.mp4"
        video.write_bytes(b"\x00" * 100)

        page._handle_files_dropped([str(video), str(video)])

        assert page.selected_files.count(str(video)) == 1


# ===================================================================
# Edge Case: Unsupported File Filtering
# ===================================================================


class TestDubbingPageUnsupportedFileFiltering:
    """Tests that non-video files in a mixed drop are filtered out."""

    @patch(f"{_MOD}.CustomMessageDialog")
    def test_mixed_drop_filters_unsupported(
        self,
        mock_dialog,
        page,  # noqa: ANN001
        tmp_path,
    ) -> None:
        """Unsupported files are filtered and dialog is shown."""
        video = tmp_path / "good.mp4"
        video.write_bytes(b"\x00" * 100)
        txt = tmp_path / "bad.txt"
        txt.write_text("nope", encoding="utf-8")
        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"\x00" * 100)

        page._handle_files_dropped([str(video), str(txt), str(pdf)])

        assert str(video) in page.selected_files
        assert str(txt) not in page.selected_files
        assert str(pdf) not in page.selected_files
        mock_dialog.show_message.assert_called_once()

    @patch(f"{_MOD}.CustomMessageDialog")
    def test_all_unsupported_files_no_view_switch(
        self,
        mock_dialog,
        page,  # noqa: ANN001
        tmp_path,
    ) -> None:
        """Dropping only unsupported files does not switch view."""
        txt = tmp_path / "file.docx"
        txt.write_bytes(b"\x00" * 100)

        page._handle_files_dropped([str(txt)])

        assert page.stack.currentIndex() == 0
        assert page.selected_files == []

    @patch(f"{_MOD}.CustomMessageDialog")
    def test_empty_files_skipped_as_unsupported(
        self,
        mock_dialog,
        page,  # noqa: ANN001
        tmp_path,
    ) -> None:
        """Zero-byte video files are rejected."""
        empty = tmp_path / "empty.mp4"
        empty.write_bytes(b"")

        page._handle_files_dropped([str(empty)])

        assert str(empty) not in page.selected_files


# ===================================================================
# Edge Case: Generate While Busy
# ===================================================================


class TestDubbingPageGenerateWhileBusy:
    """Tests that generate does nothing when a worker is already active."""

    def test_generate_noop_when_worker_active(
        self,
        page,  # noqa: ANN001
        tmp_path,
    ) -> None:
        """_handle_generate returns early when _worker is not None."""
        video = tmp_path / "busy.mp4"
        video.write_bytes(b"\x00" * 100)
        page._handle_files_dropped([str(video)])

        page._worker = MagicMock()
        original_worker = page._worker
        page._handle_generate()

        # Worker should not have been replaced
        assert page._worker is original_worker

    def test_start_worker_noop_when_worker_exists(
        self,
        page,  # noqa: ANN001
    ) -> None:
        """_start_worker returns immediately when a worker is already set."""
        page._worker = MagicMock()
        original_worker = page._worker
        page._start_worker([(1, "/tmp/x.mp4")], "en", "vi")

        assert page._worker is original_worker


# ===================================================================
# Edge Case: Worker Finished Auto Remove
# ===================================================================


class TestDubbingPageWorkerFinishedAutoRemove:
    """Tests for _on_finished with auto-remove enabled."""

    @patch(f"{_MOD}.get_unfinished_dubbing", return_value=[])
    @patch(f"{_MOD}.delete_dubbing_entry", return_value=[])
    @patch(f"{_MOD}.load_setting", return_value=True)
    def test_auto_remove_deletes_entry(
        self,
        mock_load,
        mock_delete,
        mock_unfinished,
        page,  # noqa: ANN001
    ) -> None:
        """When auto_remove is True, entries are deleted after completion."""
        with (
            patch(f"{_HIST_MOD}.get_dubbing_fingerprint", return_value=None),
            patch(f"{_HIST_MOD}.get_dubbing_history", return_value=[]),
        ):
            page._worker = MagicMock()
            results = [(1, "/tmp/out.mp4", "", "", "")]
            page._on_finished(results)

        mock_delete.assert_called_once_with(1)

    @patch(f"{_MOD}.get_unfinished_dubbing", return_value=[])
    @patch(f"{_MOD}.update_dubbing_status")
    @patch(f"{_MOD}.load_setting", return_value=False)
    def test_no_auto_remove_marks_done(
        self,
        mock_load,
        mock_status,
        mock_unfinished,
        page,  # noqa: ANN001
    ) -> None:
        """When auto_remove is False, entries are marked as Done."""
        with (
            patch(f"{_HIST_MOD}.get_dubbing_fingerprint", return_value=None),
            patch(f"{_HIST_MOD}.get_dubbing_history", return_value=[]),
        ):
            page._worker = MagicMock()
            results = [(1, "/tmp/out.mp4", "/tmp/srt", "/tmp/trans", "/tmp/voice")]
            page._on_finished(results)

        mock_status.assert_called_once()


# ===================================================================
# Edge Case: Clear All While Worker Running
# ===================================================================


class TestDubbingPageClearAllWhileWorkerRunning:
    """Tests for clear-all behavior when a worker is active."""

    def test_clear_all_clears_files_while_worker_active(
        self,
        page,  # noqa: ANN001
        tmp_path,
    ) -> None:
        """Clear all removes selected files even when a worker is running."""
        video = tmp_path / "running.mp4"
        video.write_bytes(b"\x00" * 100)
        page._handle_files_dropped([str(video)])

        page._worker = MagicMock()
        page._handle_clear_all()

        assert page.selected_files == []
        assert page.stack.currentIndex() == 0

    def test_clear_all_does_not_affect_worker(
        self,
        page,  # noqa: ANN001
        tmp_path,
    ) -> None:
        """Clear all does not stop or replace the running worker."""
        video = tmp_path / "running2.mp4"
        video.write_bytes(b"\x00" * 100)
        page._handle_files_dropped([str(video)])

        mock_worker = MagicMock()
        page._worker = mock_worker
        page._handle_clear_all()

        assert page._worker is mock_worker
        mock_worker.stop.assert_not_called()


# ===================================================================
# Edge Case: File Count Badge
# ===================================================================


class TestDubbingPageFileCountBadge:
    """Tests for the file count badge updating correctly."""

    def test_badge_shows_zero_initially(
        self,
        page,  # noqa: ANN001
    ) -> None:
        """Badge shows '0' when no files are selected."""
        assert page.files_badge.text() == "0"

    def test_badge_updates_after_adding_files(
        self,
        page,  # noqa: ANN001
        tmp_path,
    ) -> None:
        """Badge text reflects the number of selected files."""
        f1 = tmp_path / "a.mp4"
        f2 = tmp_path / "b.mp4"
        f3 = tmp_path / "c.mkv"
        f1.write_bytes(b"\x00" * 100)
        f2.write_bytes(b"\x00" * 100)
        f3.write_bytes(b"\x00" * 100)

        page._handle_files_dropped([str(f1), str(f2), str(f3)])

        assert page.files_badge.text() == "3"

    def test_badge_decrements_after_remove(
        self,
        page,  # noqa: ANN001
        tmp_path,
    ) -> None:
        """Badge updates after removing a file."""
        f1 = tmp_path / "x.mp4"
        f2 = tmp_path / "y.mp4"
        f1.write_bytes(b"\x00" * 100)
        f2.write_bytes(b"\x00" * 100)
        page._handle_files_dropped([str(f1), str(f2)])
        assert page.files_badge.text() == "2"

        widget = MagicMock()
        widget.setParent = MagicMock()
        widget.deleteLater = MagicMock()
        page._handle_remove_file(str(f1), widget)

        assert page.files_badge.text() == "1"

    def test_badge_resets_after_clear_all(
        self,
        page,  # noqa: ANN001
        tmp_path,
    ) -> None:
        """Badge resets to '0' after clearing all files."""
        video = tmp_path / "z.mp4"
        video.write_bytes(b"\x00" * 100)
        page._handle_files_dropped([str(video)])

        page._handle_clear_all()

        assert page.files_badge.text() == "0"


# ===================================================================
# Edge Case: Empty Drop
# ===================================================================


class TestDubbingPageEmptyDrop:
    """Tests that an empty file list drop does not switch views."""

    def test_empty_drop_opens_file_dialog(
        self,
        page,  # noqa: ANN001
    ) -> None:
        """Empty file list triggers QFileDialog instead of switching view."""
        with patch(f"{_MOD}.QFileDialog") as mock_fd:
            mock_fd.getOpenFileNames.return_value = ([], "")
            page._handle_files_dropped([])
            mock_fd.getOpenFileNames.assert_called_once()

        assert page.stack.currentIndex() == 0
        assert page.selected_files == []

    def test_empty_drop_cancelled_dialog_no_change(
        self,
        page,  # noqa: ANN001
    ) -> None:
        """Cancelled file dialog after empty drop leaves state unchanged."""
        with patch(f"{_MOD}.QFileDialog") as mock_fd:
            mock_fd.getOpenFileNames.return_value = ([], "")
            page._handle_files_dropped([])

        assert page.stack.currentIndex() == 0
        assert not page.generate_btn.isEnabled()


# ---------------------------------------------------------------------------
# NEW: Review-fix behaviours for Dubbing
# ---------------------------------------------------------------------------


class TestDropCapNotice:
    """Tests for the 100-file cap + user notification."""

    def test_cap_hit_shows_notification(self, page, tmp_path) -> None:
        """Dropping >100 video files notifies and keeps first 100."""
        dir_path = tmp_path / "bulk"
        dir_path.mkdir()
        for i in range(105):
            (dir_path / f"v{i:03d}.mp4").write_bytes(b"\x00")

        with patch(f"{_MOD}.CustomMessageDialog.show_message") as mock_msg:
            page._handle_files_dropped([str(dir_path)])

        assert len(page.selected_files) == 100  # noqa: PLR2004
        assert mock_msg.called
        args = mock_msg.call_args.args
        assert any("drop_capped" in str(a) for a in args)


class TestDropDuplicateNotice:
    """Tests for silent-duplicate-skip notification."""

    def test_duplicate_drop_is_reported(self, page, tmp_path) -> None:
        """Re-dropping a file surfaces the duplicates notice."""
        f = tmp_path / "clip.mp4"
        f.write_bytes(b"\x00")
        page._handle_files_dropped([str(f)])
        assert len(page.selected_files) == 1

        with patch(f"{_MOD}.CustomMessageDialog.show_message") as mock_msg:
            page._handle_files_dropped([str(f)])

        assert len(page.selected_files) == 1
        mock_msg.assert_called_once()
        args = mock_msg.call_args.args
        assert any("drop_duplicates" in str(a) for a in args)


class TestClearAllConfirmation:
    """Tests for the confirm dialog before clearing selection."""

    def test_confirm_accept_clears(self, page, tmp_path) -> None:
        """Accepting the confirm dialog clears the selection."""
        f = tmp_path / "a.mp4"
        f.write_bytes(b"\x00")
        page._handle_files_dropped([str(f)])

        with patch(
            f"{_MOD}.CustomConfirmDialog.confirm",
            return_value=True,
        ):
            page._handle_clear_all()

        assert page.selected_files == []

    def test_confirm_reject_keeps(self, page, tmp_path) -> None:
        """Rejecting the confirm dialog keeps files."""
        f = tmp_path / "a.mp4"
        f.write_bytes(b"\x00")
        page._handle_files_dropped([str(f)])

        with patch(
            f"{_MOD}.CustomConfirmDialog.confirm",
            return_value=False,
        ):
            page._handle_clear_all()

        assert len(page.selected_files) == 1

    def test_internal_confirm_false_skips_dialog(
        self,
        page,
        tmp_path,
    ) -> None:
        """confirm=False bypasses the dialog (used by internal cleanup)."""
        f = tmp_path / "a.mp4"
        f.write_bytes(b"\x00")
        page._handle_files_dropped([str(f)])

        with patch(f"{_MOD}.CustomConfirmDialog.confirm") as mock_confirm:
            page._handle_clear_all(confirm=False)

        mock_confirm.assert_not_called()
        assert page.selected_files == []


class TestGenerateEmptyTasksKeepsFiles:
    """Covers the fix: empty-tasks result should NOT clear the selection."""

    @patch(f"{_MOD}.add_dubbing_entry", return_value=0)
    @patch(f"{_MOD}.LanguageSelectionDialog.get_selection")
    def test_empty_tasks_keeps_files_and_notifies(
        self,
        mock_dialog,
        _mock_add,
        page,
        tmp_path,
    ) -> None:
        """When every add_dubbing_entry returns falsy, selection is preserved."""
        f = tmp_path / "a.mp4"
        f.write_bytes(b"\x00")
        page._handle_files_dropped([str(f)])
        mock_dialog.return_value = ("English", "French", "", True)

        with (
            patch.object(page, "_check_all_requirements", return_value=True),
            patch(f"{_MOD}.CustomMessageDialog.show_message") as mock_msg,
        ):
            page._handle_generate()

        assert len(page.selected_files) == 1
        mock_msg.assert_called_once()


class TestStopButton:
    """Tests for the Stop button that cancels an in-flight worker."""

    def test_stop_btn_hidden_by_default(self, page) -> None:
        """Stop button is not visible before any worker starts."""
        assert page.stop_btn.isHidden()

    @patch(f"{_MOD}._DubbingWorker")
    def test_start_worker_reveals_stop_button(
        self,
        mock_worker_cls,
        page,
    ) -> None:
        """Starting a worker shows Stop and hides Generate."""
        worker_inst = MagicMock()
        mock_worker_cls.return_value = worker_inst

        page._start_worker([(1, "/a.mp4")], "English", "French")

        assert not page.stop_btn.isHidden()
        assert page.generate_btn.isHidden()

    @patch(f"{_MOD}._DubbingWorker")
    def test_handle_stop_forwards_to_worker(
        self,
        mock_worker_cls,
        page,
    ) -> None:
        """_handle_stop calls worker.stop() and disables the button."""
        worker_inst = MagicMock()
        mock_worker_cls.return_value = worker_inst
        page._start_worker([(1, "/a.mp4")], "English", "French")

        page._handle_stop()
        worker_inst.stop.assert_called_once()
        assert not page.stop_btn.isEnabled()

    @patch(f"{_MOD}.update_dubbing_status")
    def test_on_finished_restores_generate_button(
        self,
        _mock_status,
        page,
    ) -> None:
        """_on_finished hides Stop and re-shows Generate."""
        page.stop_btn.setVisible(True)
        page.generate_btn.setVisible(False)

        page._on_finished([])

        assert page.stop_btn.isHidden()
        assert not page.generate_btn.isHidden()


class TestReDubAndContinueBusy:
    """Tests for the busy-guard paths in re-dub / continue-dub."""

    def test_re_dub_busy_shows_message(self, page) -> None:
        """Re-dub while a worker runs surfaces a busy dialog."""
        page._worker = MagicMock()

        with patch(f"{_MOD}.CustomMessageDialog.show_message") as mock_msg:
            page._handle_re_dub([(1, "/a.mp4")])

        mock_msg.assert_called_once()
        args = mock_msg.call_args.args
        assert any("dubbing_busy" in str(a) for a in args)

    def test_continue_dub_busy_shows_message(self, page) -> None:
        """Continue while a worker runs surfaces a busy dialog."""
        page._worker = MagicMock()

        with patch(f"{_MOD}.CustomMessageDialog.show_message") as mock_msg:
            page._handle_continue_dub([(1, "/a.mp4")], "English", "French")

        mock_msg.assert_called_once()
        args = mock_msg.call_args.args
        assert any("dubbing_busy" in str(a) for a in args)


class TestCheckAllRequirementsElevenLabs:
    """ElevenLabs TTS credential pre-check."""

    def test_elevenlabs_missing_key_blocks_generation(self, page) -> None:
        """ElevenLabs with no API key fails _check_all_requirements."""

        # Simulate: LLM ok, STT is Whisper (no API key), TTS is ElevenLabs.
        def _fake_load(key, default=None):
            if "stt_method" in key:
                return "Whisper"
            if "tts_method" in key:
                return "ElevenLabs"
            return default

        def _fake_require_setup(
            _parent,
            checker,
            _t,
            _m,
            _n,
        ):
            # Pass LLM (index 2), fail ElevenLabs (checker is check_elevenlabs_setup).
            return checker.__name__ != "check_elevenlabs_setup"

        with (
            patch(f"{_MOD}.load_setting", side_effect=_fake_load),
            patch(f"{_MOD}.require_setup", side_effect=_fake_require_setup),
        ):
            assert page._check_all_requirements() is False


class TestCheckAllRequirementsFFmpeg:
    """FFmpeg pre-check."""

    def test_no_ffmpeg_blocks_generation(self, page) -> None:
        """Missing FFmpeg fails _check_all_requirements with a clear error."""

        def _fake_load(key, default=None):
            if "stt_method" in key:
                return "Whisper"
            if "tts_method" in key:
                return "Edge TTS"
            return default

        with (
            patch(f"{_MOD}.load_setting", side_effect=_fake_load),
            patch(f"{_MOD}.require_setup", return_value=True),
            patch(
                "src.core.speech_engine.check_ffmpeg_available",
                return_value=False,
            ),
            patch(f"{_MOD}.CustomMessageDialog.show_message") as mock_msg,
        ):
            result = page._check_all_requirements()

        assert result is False
        mock_msg.assert_called_once()
        args = mock_msg.call_args.args
        assert any("ffmpeg_required" in str(a) for a in args)


class TestCtrlEnterShortcut:
    """Tests for the new Ctrl+Enter shortcut."""

    def test_shortcut_is_registered(self, page) -> None:
        """A Ctrl+Enter QShortcut exists on the page."""
        from PySide6.QtCore import Qt  # noqa: PLC0415
        from PySide6.QtGui import QKeySequence, QShortcut  # noqa: PLC0415

        target = QKeySequence(Qt.Modifier.CTRL | Qt.Key.Key_Return)
        shortcuts = [s for s in page.findChildren(QShortcut) if s.key() == target]
        assert shortcuts, "Ctrl+Enter shortcut not registered"


class TestStopAllWorkersBoundedWait:
    """``aboutToQuit`` must drain the worker with a bounded wait.

    Pins the ``stop()`` → ``wait(2000)`` contract so a future refactor
    can't regress to an unbounded ``wait()`` and block app exit when a
    stage (FFmpeg mux, OCR call, LLM stream) takes too long to honour
    the cancel flag.
    """

    def test_worker_gets_stop_then_bounded_wait(self, page) -> None:
        """``_stop_all_workers`` calls ``stop()`` then ``wait(2000)``."""
        from unittest.mock import MagicMock  # noqa: PLC0415

        worker = MagicMock()
        worker.wait.return_value = True
        page._worker = worker
        page._stop_all_workers()

        worker.stop.assert_called_once()
        worker.wait.assert_called_once_with(2000)
        assert page._worker is None

    def test_no_worker_is_noop(self, page) -> None:
        """Empty worker slot is a safe no-op."""
        page._worker = None
        page._stop_all_workers()
        assert page._worker is None


class TestPerFeaturePersistenceKeys:
    """Dubbing uses ``SETTING_LAST_DUBBING_*`` keys, not the global ones.

    Same regression guard as Subtitle — the dialog must receive the
    per-feature setting keys so the user's last Dubbing language pick
    doesn't leak into Translate Document, Subtitle, or Voice flows
    (and vice versa).
    """

    @patch(f"{_MOD}.LanguageSelectionDialog.get_selection")
    def test_handle_generate_passes_dubbing_specific_setting_keys(
        self,
        mock_dialog,  # noqa: ANN001
        page,  # noqa: ANN001
    ) -> None:
        from src.constants.settings import (  # noqa: PLC0415
            SETTING_LAST_DUBBING_SRC_LANG,
            SETTING_LAST_DUBBING_TGT_LANG,
        )

        mock_dialog.return_value = ("en", "", None, False)  # cancelled
        page.selected_files = ["/tmp/test.mp4"]
        page._worker = None
        # Skip the require-setup gate by patching it inside _handle_generate.
        with patch(f"{_MOD}.require_setup", return_value=True):
            page._handle_generate()

        mock_dialog.assert_called_once()
        kwargs = mock_dialog.call_args.kwargs
        assert (
            kwargs.get("source_setting_key") == SETTING_LAST_DUBBING_SRC_LANG
        ), (
            f"Dubbing page must use its own source-lang setting key; "
            f"got {kwargs.get('source_setting_key')!r}"
        )
        assert (
            kwargs.get("target_setting_key") == SETTING_LAST_DUBBING_TGT_LANG
        ), (
            f"Dubbing page must use its own target-lang setting key; "
            f"got {kwargs.get('target_setting_key')!r}"
        )


# ===================================================================
# _DubbingWorker.run() pipeline-level tests
# ===================================================================


class TestDubbingWorkerFullPipelineSmoke:
    """Drives ``_DubbingWorker.run()`` end-to-end with all 4 stages mocked.

    The worker glues together STT → translate → TTS → mix. Each stage
    has its own engine, but the worker's ORCHESTRATION (stage
    sequencing, status updates, checkpoint saves, error propagation)
    has only been exercised through integration tests until now.
    This pins the per-stage call ordering and DB-status-flip
    sequence so a refactor that, say, drops the post-translate
    ``save_checkpoint()`` would surface as a clear test failure.
    """

    @staticmethod
    def _wire_paths(monkeypatch, tmp_path) -> None:
        """Redirects DB + app-data dir into tmp_path and inits the schema."""
        from src.core.database import init_db  # noqa: PLC0415

        db_file = tmp_path / "dub.db"
        monkeypatch.setattr(
            "src.core.database.get_db_path", lambda: str(db_file),
        )
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        monkeypatch.setattr(
            "src.utils.path_manager.get_app_data_dir",
            lambda: data_dir,
        )
        init_db()

    def test_pipeline_runs_all_four_stages_in_order(
        self, tmp_path, monkeypatch,
    ) -> None:
        """One task → STT → translate → TTS → mix → cleanup."""
        from src.constants.history import STATUS_PENDING  # noqa: PLC0415
        from src.core.database import add_dubbing_entry  # noqa: PLC0415
        from src.ui.pages.dubbing import _DubbingWorker  # noqa: PLC0415

        self._wire_paths(monkeypatch, tmp_path)

        video = tmp_path / "input.mp4"
        video.write_bytes(b"fake video bytes")
        entry_id = add_dubbing_entry(
            file_name="input.mp4",
            file_size=video.stat().st_size,
            source_path=str(video),
            output_path="",
            status=STATUS_PENDING,
            src_lang="English",
            target_lang="French",
        )

        # Pipeline stage trace
        stage_calls: list[str] = []

        def _fake_transcribe(*_a, **_kw):
            stage_calls.append("stt")
            return (
                "1\n00:00:01,000 --> 00:00:02,000\nHello world\n\n"
            )

        def _fake_translate_batch(texts, **_kw):
            stage_calls.append("translate")
            return ["Bonjour" for _ in texts]

        def _fake_synth(_entries, **kwargs):
            stage_calls.append("tts")
            audio_path = kwargs.get("output_path")
            assert audio_path, "synthesize_timed_speech needs an output path"
            import pathlib  # noqa: PLC0415

            pathlib.Path(audio_path).write_bytes(b"fake audio")

        def _fake_mix(*_a, **_kw):
            stage_calls.append("mix")

        # Build the worker without invoking QThread.__init__
        worker = _DubbingWorker.__new__(_DubbingWorker)
        worker._tasks = [(entry_id, str(video))]
        worker._src_lang = "English"
        worker._target_lang = "French"
        worker._voice_gender = "FEMALE"
        worker._llm_provider = None
        worker._llm_model = None
        worker._is_running = True
        worker.finished_ok = MagicMock()

        # Reset the class-level singleton so prior tests don't block us
        _DubbingWorker._is_any_worker_running = False

        with (
            patch(
                "src.core.speech_engine.transcribe_audio",
                side_effect=_fake_transcribe,
            ),
            patch(
                "src.core.llm_engine.translate_batch",
                side_effect=_fake_translate_batch,
            ),
            patch(
                "src.core.speech_engine.synthesize_timed_speech",
                side_effect=_fake_synth,
            ),
            patch(
                "src.core.speech_engine.mix_audio_into_video",
                side_effect=_fake_mix,
            ),
        ):
            worker.run()

        assert stage_calls == ["stt", "translate", "tts", "mix"], (
            f"Pipeline didn't run all 4 stages in order — got {stage_calls}"
        )
        # Class flag must be released after a successful run
        assert _DubbingWorker._is_any_worker_running is False
        worker.finished_ok.emit.assert_called_once()

    def test_resume_from_translate_checkpoint_skips_stt(
        self, tmp_path, monkeypatch,
    ) -> None:
        """Pre-seeded checkpoint with translated_srt → STT is bypassed.

        Pins the 4-step resumption documented in AGENTS.md — when
        a checkpoint exists from a previous run, the worker must
        not re-transcribe (slow, expensive) and instead skip
        directly to the next stage.
        """
        from src.constants.history import STATUS_PENDING  # noqa: PLC0415
        from src.core.checkpoint import (  # noqa: PLC0415
            save_dubbing_checkpoint,
        )
        from src.core.database import add_dubbing_entry  # noqa: PLC0415
        from src.ui.pages.dubbing import _DubbingWorker  # noqa: PLC0415
        from src.utils.path_manager import (  # noqa: PLC0415
            get_dubbing_storage_dir,
        )

        self._wire_paths(monkeypatch, tmp_path)

        video = tmp_path / "input.mp4"
        video.write_bytes(b"fake video bytes")
        entry_id = add_dubbing_entry(
            file_name="input.mp4",
            file_size=video.stat().st_size,
            source_path=str(video),
            output_path="",
            status=STATUS_PENDING,
            src_lang="English",
            target_lang="French",
        )

        # Pre-seed both STT and translation checkpoints. Worker
        # should jump straight to TTS.
        storage_dir = get_dubbing_storage_dir(entry_id)
        srt_text = (
            "1\n00:00:01,000 --> 00:00:02,000\nHello world\n\n"
        )
        translated_srt = (
            "1\n00:00:01,000 --> 00:00:02,000\nBonjour\n\n"
        )
        save_dubbing_checkpoint(
            storage_dir,
            srt_text=srt_text,
            translated_srt=translated_srt,
            target_lang="French",
        )

        stage_calls: list[str] = []

        def _fake_transcribe(*_a, **_kw):
            stage_calls.append("stt")
            return srt_text

        def _fake_translate_batch(texts, **_kw):
            stage_calls.append("translate")
            return ["Bonjour" for _ in texts]

        def _fake_synth(_entries, **kwargs):
            stage_calls.append("tts")
            import pathlib  # noqa: PLC0415

            pathlib.Path(kwargs["output_path"]).write_bytes(b"fake audio")

        def _fake_mix(*_a, **_kw):
            stage_calls.append("mix")

        worker = _DubbingWorker.__new__(_DubbingWorker)
        worker._tasks = [(entry_id, str(video))]
        worker._src_lang = "English"
        worker._target_lang = "French"
        worker._voice_gender = "FEMALE"
        worker._llm_provider = None
        worker._llm_model = None
        worker._is_running = True
        worker.finished_ok = MagicMock()

        _DubbingWorker._is_any_worker_running = False

        with (
            patch(
                "src.core.speech_engine.transcribe_audio",
                side_effect=_fake_transcribe,
            ),
            patch(
                "src.core.llm_engine.translate_batch",
                side_effect=_fake_translate_batch,
            ),
            patch(
                "src.core.speech_engine.synthesize_timed_speech",
                side_effect=_fake_synth,
            ),
            patch(
                "src.core.speech_engine.mix_audio_into_video",
                side_effect=_fake_mix,
            ),
        ):
            worker.run()

        # STT and translate checkpoints both pre-seeded — both must
        # be skipped. TTS + mix should still run.
        assert "stt" not in stage_calls, (
            f"STT must be skipped when srt_text checkpoint exists — "
            f"got {stage_calls}"
        )
        assert "translate" not in stage_calls, (
            f"Translation must be skipped when translated_srt "
            f"checkpoint exists — got {stage_calls}"
        )
        assert stage_calls == ["tts", "mix"], (
            f"Resumed pipeline must only execute TTS + mix; "
            f"got {stage_calls}"
        )


class TestEmbeddedHistoryHeaderHidden:
    """Inner history page's header_label is hidden when embedded.

    AGENTS.md: "Pages that embed another `create_page_container`-based
    widget hide the inner title via `page.header_label.setVisible(False)`;
    never match the label by translated text, since language-switch
    ordering can make the comparison miss."
    """

    def test_inner_history_header_is_hidden(self, page) -> None:  # noqa: ANN001
        inner_page = page.history_view.page
        assert inner_page.header_label.isVisible() is False
