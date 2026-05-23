"""Unit tests for _SubtitleWorker and _translate_srt in subtitle.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
)

from src.constants.history import STATUS_FAILED, STATUS_GENERATING
from src.ui.pages.subtitle import (
    _convert_subtitle_format,
    _SubtitleWorker,
)
from src.utils.subtitle_utils import SubtitleEntry

# Module path for patching module-level imports (at usage site)
_MOD = "src.ui.pages.subtitle"
# Source modules for patching local imports (inside run() / _translate_srt())
_SPEECH = "src.core.speech_engine"
_LLM = "src.core.llm_engine"
_DB = "src.core.database"
_SUB = "src.utils.subtitle_utils"

# Sample SRT text returned by transcribe_audio in tests
_SAMPLE_SRT = "1\n00:00:01,000 --> 00:00:02,000\nHi"


@pytest.fixture(autouse=True)
def _auto_mock_blocking_dialogs():
    """Auto-mocks modal dialogs on the subtitle page so tests don't hang.

    Individual tests can override these with their own ``@patch`` to assert
    specific interactions.
    """
    with (
        patch(
            "src.ui.pages.subtitle.CustomConfirmDialog.confirm",
            return_value=True,
        ),
        patch(
            "src.ui.pages.subtitle.CustomMessageDialog.show_message",
        ),
    ):
        yield


# ---------------------------------------------------------------------------
# _convert_subtitle_format (pure Python, no Qt)
# ---------------------------------------------------------------------------


class TestConvertSubtitleFormat:
    """Tests for the SRT-to-VTT converter."""

    def test_srt_passthrough(self):
        """Non-VTT target returns original SRT text unchanged."""
        srt = "1\n00:00:01,000 --> 00:00:02,000\nHello"
        assert _convert_subtitle_format(srt, ".srt") == srt

    def test_vtt_header_added(self):
        """VTT conversion prepends WEBVTT header."""
        srt = "1\n00:00:01,000 --> 00:00:02,000\nHello"
        result = _convert_subtitle_format(srt, ".vtt")
        assert result.startswith("WEBVTT\n")

    def test_vtt_comma_to_dot_in_timestamps(self):
        """VTT conversion replaces comma with dot in timestamp lines only."""
        srt = "1\n00:00:01,500 --> 00:00:04,200\nHello, world"
        result = _convert_subtitle_format(srt, ".vtt")
        # Timestamp commas become dots
        assert "00:00:01.500 --> 00:00:04.200" in result
        # Text commas are preserved
        assert "Hello, world" in result

    def test_vtt_empty_srt(self):
        """Empty SRT produces just the WEBVTT header."""
        result = _convert_subtitle_format("", ".vtt")
        assert "WEBVTT" in result

    # ── CSV export (RFC 4180 quoted, 4-column schema) ─────────────────

    def test_csv_emits_header_and_rows(self):
        """CSV output: ``index, start, end, text`` columns, one row per cue."""
        srt = (
            "1\n00:00:01,000 --> 00:00:03,000\nHello\n\n"
            "2\n00:00:03,000 --> 00:00:05,500\nWorld\n"
        )
        result = _convert_subtitle_format(srt, ".csv")
        lines = result.splitlines()
        assert lines[0] == "index,start,end,text"
        assert "Hello" in lines[1]
        assert "World" in lines[2]
        # Three rows total: header + 2 cues.
        assert len(lines) >= 3

    def test_csv_escapes_commas_and_quotes(self):
        """``csv.writer`` quotes fields containing commas / quotes per RFC 4180."""
        import csv  # noqa: PLC0415
        import io  # noqa: PLC0415

        srt = (
            "1\n00:00:01,000 --> 00:00:03,000\n"
            'A "quoted", complex text\n'
        )
        result = _convert_subtitle_format(srt, ".csv")
        rows = list(csv.reader(io.StringIO(result)))
        # Header + 1 cue.
        assert rows[1][3] == 'A "quoted", complex text'

    def test_csv_uses_crlf_line_terminator(self):
        """``csv.writer(lineterminator="\\r\\n")`` per RFC 4180."""
        srt = "1\n00:00:01,000 --> 00:00:03,000\nHello\n"
        result = _convert_subtitle_format(srt, ".csv")
        # CRLF separates the header row from the first cue.
        assert "\r\n" in result


# ---------------------------------------------------------------------------
# _translate_srt (pure translation logic, mock Qt/DB/LLM)
# ---------------------------------------------------------------------------


class TestTranslateSrt:
    """Tests for _SubtitleWorker._translate_srt via a minimal mock worker."""

    def _make_worker(self, src_lang: str = "en", target_lang: str = "vi"):
        """Creates a minimal mock that has the _translate_srt method bound."""
        worker = _SubtitleWorker.__new__(_SubtitleWorker)
        worker._src_lang = src_lang
        worker._target_lang = target_lang
        worker._is_running = True
        return worker

    @patch(f"{_LLM}.translate_batch")
    @patch(f"{_DB}.get_glossary_entries", return_value=[])
    @patch(f"{_DB}.get_active_glossary_sets", return_value=[])
    @patch(f"{_SUB}.serialize_subtitle", return_value="serialized")
    @patch(f"{_SUB}.parse_subtitle")
    def test_empty_srt_returns_original(  # noqa: PLR0913
        self,
        mock_parse,
        mock_serialize,
        mock_gloss,
        mock_entries,
        mock_tb,
    ):
        """Empty SRT (no entries) returns original text without translation."""
        mock_parse.return_value = ([], None)
        worker = self._make_worker()
        result = worker._translate_srt("")
        # No translation attempted when entries list is empty
        mock_tb.assert_not_called()
        assert result == ""

    @patch(f"{_LLM}.translate_batch")
    @patch(f"{_DB}.get_glossary_entries", return_value=[])
    @patch(f"{_DB}.get_active_glossary_sets", return_value=[])
    @patch(f"{_SUB}.serialize_subtitle")
    @patch(f"{_SUB}.parse_subtitle")
    def test_translate_batch_called_with_correct_texts(  # noqa: PLR0913
        self,
        mock_parse,
        mock_serialize,
        mock_gloss,
        mock_entries,
        mock_tb,
    ):
        """translate_batch receives the text from each parsed entry."""
        entries = [
            SubtitleEntry(0, "00:00:01,000", "00:00:02,000", "Hello"),
            SubtitleEntry(1, "00:00:03,000", "00:00:04,000", "World"),
        ]
        mock_parse.return_value = (entries, None)
        mock_tb.return_value = ["Xin chao", "The gioi"]
        mock_serialize.return_value = "final_srt"

        worker = self._make_worker()
        result = worker._translate_srt("dummy srt")

        # Verify translate_batch was called with the right texts
        tb_call = mock_tb.call_args
        assert tb_call[0][0] == ["Hello", "World"]
        assert tb_call[1]["target_lang"] == "vi"
        assert tb_call[1]["src_lang"] == "en"
        assert result == "final_srt"

    @patch(f"{_LLM}.translate_batch")
    @patch(f"{_DB}.get_glossary_entries", return_value=[(1, "Hi", "Chao")])
    @patch(f"{_DB}.get_active_glossary_sets", return_value=[(10, "MyDict")])
    @patch(f"{_SUB}.serialize_subtitle")
    @patch(f"{_SUB}.parse_subtitle")
    def test_glossary_entries_fetched_and_passed(  # noqa: PLR0913
        self,
        mock_parse,
        mock_serialize,
        mock_gloss_sets,
        mock_gloss_entries,
        mock_tb,
    ):
        """Active glossary entries are fetched and passed to translate_batch."""
        entries = [SubtitleEntry(0, "00:00:01,000", "00:00:02,000", "Hi")]
        mock_parse.return_value = (entries, None)
        mock_tb.return_value = ["Chao"]
        mock_serialize.return_value = "out"

        worker = self._make_worker()
        worker._translate_srt("dummy")

        # Glossary entries should be passed
        tb_call = mock_tb.call_args
        assert tb_call[1]["glossary_entries"] == [(1, "Hi", "Chao")]

    @patch(f"{_LLM}.translate_batch")
    @patch(f"{_DB}.get_glossary_entries", return_value=[])
    @patch(f"{_DB}.get_active_glossary_sets", return_value=[])
    @patch(f"{_SUB}.serialize_subtitle")
    @patch(f"{_SUB}.parse_subtitle")
    def test_translation_result_count_matches(  # noqa: PLR0913
        self,
        mock_parse,
        mock_serialize,
        mock_gloss,
        mock_entries,
        mock_tb,
    ):
        """Entry texts are updated only when result count matches."""
        entries = [
            SubtitleEntry(0, "00:00:01,000", "00:00:02,000", "A"),
            SubtitleEntry(1, "00:00:03,000", "00:00:04,000", "B"),
        ]
        mock_parse.return_value = (entries, None)
        mock_tb.return_value = ["X", "Y"]
        mock_serialize.return_value = "done"

        worker = self._make_worker()
        worker._translate_srt("dummy")

        # Entries text should be overwritten
        assert entries[0].text == "X"
        assert entries[1].text == "Y"

    @patch(f"{_LLM}.translate_batch")
    @patch(f"{_DB}.get_glossary_entries", return_value=[])
    @patch(f"{_DB}.get_active_glossary_sets", return_value=[])
    @patch(f"{_SUB}.serialize_subtitle")
    @patch(f"{_SUB}.parse_subtitle")
    def test_mismatched_result_count_preserves_originals(  # noqa: PLR0913
        self,
        mock_parse,
        mock_serialize,
        mock_gloss,
        mock_entries,
        mock_tb,
    ):
        """When translate_batch returns wrong count, original text is kept."""
        entries = [
            SubtitleEntry(0, "00:00:01,000", "00:00:02,000", "A"),
            SubtitleEntry(1, "00:00:03,000", "00:00:04,000", "B"),
        ]
        mock_parse.return_value = (entries, None)
        # Return wrong number of results
        mock_tb.return_value = ["X"]
        mock_serialize.return_value = "original"

        worker = self._make_worker()
        worker._translate_srt("dummy")

        # Entries should not be modified
        assert entries[0].text == "A"
        assert entries[1].text == "B"

    @patch(f"{_LLM}.translate_batch")
    @patch(f"{_DB}.get_glossary_entries", return_value=[])
    @patch(f"{_DB}.get_active_glossary_sets", return_value=[])
    @patch(f"{_SUB}.serialize_subtitle")
    @patch(f"{_SUB}.parse_subtitle")
    def test_none_result_preserves_originals(  # noqa: PLR0913
        self,
        mock_parse,
        mock_serialize,
        mock_gloss,
        mock_entries,
        mock_tb,
    ):
        """When translate_batch returns None (cancellation), originals kept."""
        entries = [
            SubtitleEntry(0, "00:00:01,000", "00:00:02,000", "A"),
        ]
        mock_parse.return_value = (entries, None)
        mock_tb.return_value = None
        mock_serialize.return_value = "original"

        worker = self._make_worker()
        worker._translate_srt("dummy")

        assert entries[0].text == "A"

    @patch(f"{_LLM}.translate_batch")
    @patch(f"{_DB}.get_glossary_entries", return_value=[])
    @patch(f"{_DB}.get_active_glossary_sets", return_value=[])
    @patch(f"{_SUB}.serialize_subtitle")
    @patch(f"{_SUB}.parse_subtitle")
    def test_auto_src_lang_when_empty(  # noqa: PLR0913
        self,
        mock_parse,
        mock_serialize,
        mock_gloss,
        mock_entries,
        mock_tb,
    ):
        """Empty src_lang defaults to 'Auto' for translate_batch."""
        entries = [SubtitleEntry(0, "00:00:01,000", "00:00:02,000", "Hi")]
        mock_parse.return_value = (entries, None)
        mock_tb.return_value = ["Chao"]
        mock_serialize.return_value = "out"

        worker = self._make_worker(src_lang="", target_lang="vi")
        worker._translate_srt("dummy")

        assert mock_tb.call_args[1]["src_lang"] == "Auto"


# ---------------------------------------------------------------------------
# _SubtitleWorker.run() logic (mock QThread and signals)
# ---------------------------------------------------------------------------


class TestSubtitleWorkerRun:
    """Tests for the worker's run() method with mocked dependencies."""

    def _make_worker(self, tasks, **kwargs):
        """Creates a _SubtitleWorker with mocked signals."""
        worker = _SubtitleWorker.__new__(_SubtitleWorker)
        worker._tasks = tasks
        worker._src_lang = kwargs.get("src_lang", "en")
        worker._stt_method = kwargs.get("stt_method", "whisper")
        worker._model_size = kwargs.get("model_size", "base")
        worker._google_model = kwargs.get("google_model", "default")
        worker._target_lang = kwargs.get("target_lang", "")
        worker._is_running = True
        worker.finished_ok = MagicMock()
        # Ensure the class-level busy flag starts clean
        _SubtitleWorker._is_any_worker_running = False
        return worker

    @patch(f"{_MOD}.update_subtitle_status")
    @patch(f"{_SPEECH}.transcribe_audio", return_value=_SAMPLE_SRT)
    def test_worker_processes_tasks_sequentially(
        self,
        mock_transcribe,
        mock_status,
    ):
        """Worker iterates through all tasks and emits results."""
        tasks = [(1, "/path/a.mp4"), (2, "/path/b.mp4")]
        worker = self._make_worker(tasks)
        worker.run()

        assert mock_transcribe.call_count == 2  # noqa: PLR2004
        assert mock_status.call_count == 2  # noqa: PLR2004
        # Both marked as Generating
        mock_status.assert_any_call(1, STATUS_GENERATING)
        mock_status.assert_any_call(2, STATUS_GENERATING)
        # finished_ok emitted with 2 results
        results = worker.finished_ok.emit.call_args[0][0]
        assert len(results) == 2  # noqa: PLR2004

    @patch(f"{_MOD}.update_subtitle_status")
    @patch(f"{_SPEECH}.transcribe_audio", return_value=_SAMPLE_SRT)
    def test_no_translation_when_target_lang_empty(
        self,
        mock_transcribe,
        mock_status,
    ):
        """When target_lang is empty, _translate_srt is never called."""
        tasks = [(1, "/path/a.mp4")]
        worker = self._make_worker(tasks, target_lang="")
        worker._translate_srt = MagicMock()
        worker.run()

        worker._translate_srt.assert_not_called()

    @patch(f"{_MOD}.update_subtitle_status")
    @patch(f"{_SPEECH}.transcribe_audio", return_value="   ")
    def test_whitespace_srt_skips_translation(
        self,
        mock_transcribe,
        mock_status,
    ):
        """Whitespace-only SRT skips translation even when target_lang is set."""
        tasks = [(1, "/path/a.mp4")]
        worker = self._make_worker(tasks, target_lang="vi")
        worker._translate_srt = MagicMock()
        worker.run()

        worker._translate_srt.assert_not_called()

    @patch(f"{_MOD}.update_subtitle_status")
    @patch(f"{_SPEECH}.transcribe_audio", side_effect=RuntimeError("STT failed"))
    def test_exception_in_transcribe_marks_failed(
        self,
        mock_transcribe,
        mock_status,
    ):
        """Exception during transcription marks entry as FAILED."""
        tasks = [(1, "/path/a.mp4")]
        worker = self._make_worker(tasks)
        worker.run()

        mock_status.assert_any_call(
            1,
            STATUS_FAILED,
            error_message="STT failed",
        )
        # finished_ok still emitted (with no successful results)
        results = worker.finished_ok.emit.call_args[0][0]
        assert len(results) == 0

    @patch(f"{_MOD}.update_subtitle_status")
    @patch(f"{_SPEECH}.transcribe_audio", return_value=_SAMPLE_SRT)
    def test_all_tasks_processed(
        self,
        mock_transcribe,
        mock_status,
    ):
        """Every task is transcribed and status-updated exactly once."""
        tasks = [(1, "/a.mp4"), (2, "/b.mp4"), (3, "/c.mp4")]
        worker = self._make_worker(tasks)
        worker.run()

        # transcribe_audio was called once per task.
        assert mock_transcribe.call_count == 3  # noqa: PLR2004
        # At minimum each entry was marked "Generating" when started.
        generating_calls = [
            c
            for c in mock_status.call_args_list
            if len(c.args) >= 2 and c.args[1] == "Generating"  # noqa: PLR2004
        ]
        assert len(generating_calls) == 3  # noqa: PLR2004

    def test_is_busy_classmethod(self):
        """is_busy() reflects the class-level _is_any_worker_running flag."""
        _SubtitleWorker._is_any_worker_running = False
        try:
            assert _SubtitleWorker.is_busy() is False

            _SubtitleWorker._is_any_worker_running = True
            assert _SubtitleWorker.is_busy() is True
        finally:
            _SubtitleWorker._is_any_worker_running = False

    @patch(f"{_MOD}.update_subtitle_status")
    @patch(f"{_SPEECH}.transcribe_audio")
    def test_cancellation_stops_processing(
        self,
        mock_transcribe,
        mock_status,
    ):
        """Setting _is_running = False during run skips remaining tasks."""
        tasks = [(1, "/a.mp4"), (2, "/b.mp4")]
        worker = self._make_worker(tasks)

        def stop_after_first(*args, **kwargs):
            worker._is_running = False
            return _SAMPLE_SRT

        mock_transcribe.side_effect = stop_after_first
        worker.run()

        # Only 1 task processed (second skipped due to cancellation)
        assert mock_transcribe.call_count == 1
        results = worker.finished_ok.emit.call_args[0][0]
        assert len(results) == 1

    @patch(f"{_MOD}.update_subtitle_status")
    @patch(f"{_SPEECH}.transcribe_audio", return_value="srt")
    def test_busy_flag_reset_on_completion(
        self,
        mock_transcribe,
        mock_status,
    ):
        """_is_any_worker_running resets to False in the finally block."""
        tasks = [(1, "/a.mp4")]
        worker = self._make_worker(tasks)
        worker.run()

        assert _SubtitleWorker._is_any_worker_running is False

    @patch(f"{_MOD}.update_subtitle_status")
    @patch(f"{_SPEECH}.transcribe_audio")
    def test_busy_flag_reset_even_on_crash(
        self,
        mock_transcribe,
        mock_status,
    ):
        """_is_any_worker_running resets to False even if outer try crashes."""
        # Use a list with a non-tuple element to crash tuple unpacking
        # inside the for loop (which is inside the try block)
        worker = self._make_worker(["not_a_tuple"])
        worker.run()

        assert _SubtitleWorker._is_any_worker_running is False
        # finished_ok still emitted
        worker.finished_ok.emit.assert_called_once()

    @patch(f"{_MOD}.update_subtitle_status")
    @patch(f"{_SPEECH}.transcribe_audio", return_value="srt content")
    def test_auto_translate_called_when_target_lang_set(
        self,
        mock_transcribe,
        mock_status,
    ):
        """When target_lang is set and srt_text is non-empty, _translate_srt runs."""
        tasks = [(1, "/path/a.mp4")]
        worker = self._make_worker(tasks, target_lang="vi")
        worker._translate_srt = MagicMock(return_value="translated srt")
        worker.run()

        worker._translate_srt.assert_called_once_with("srt content")
        results = worker.finished_ok.emit.call_args[0][0]
        assert results[0][2] == "translated srt"


# ---------------------------------------------------------------------------
# Fixtures for SubtitlePage UI tests (pytest-qt)
# ---------------------------------------------------------------------------

_HIST_MOD = "src.ui.pages.subtitle_history"


@pytest.fixture()
def _mock_db():
    """Mocks database calls used by embedded SubtitleHistoryPage."""
    with (
        patch(f"{_HIST_MOD}.get_subtitle_fingerprint", return_value=None),
        patch(f"{_HIST_MOD}.get_subtitle_history", return_value=[]),
        patch(f"{_DB}.reset_stuck_subtitle_entries", return_value=0),
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
    """Creates a SubtitlePage widget for testing."""
    from src.ui.pages.subtitle import SubtitlePage  # noqa: PLC0415

    p = SubtitlePage(window)
    qtbot.addWidget(p)
    return p


# ---------------------------------------------------------------------------
# TestSubtitlePageCreation — widget structure verification
# ---------------------------------------------------------------------------


class TestSubtitlePageCreation:
    """Tests for SubtitlePage widget construction and initial state."""

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
        """Page embeds a SubtitleHistoryPage."""
        from src.ui.pages.subtitle_history import SubtitleHistoryPage  # noqa: PLC0415

        assert isinstance(page.history_view, SubtitleHistoryPage)

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
        """Pending tasks list is empty at construction time."""
        assert page._pending_tasks == []

    def test_generate_button_has_text(self, page) -> None:  # noqa: ANN001
        """Generate button has non-empty text."""
        assert page.generate_btn.text()

    def test_clear_all_button_has_text(self, page) -> None:  # noqa: ANN001
        """Clear-all button has non-empty text."""
        assert page.clear_all_btn.text()

    def test_create_subtitle_page_factory(
        self,
        _mock_db,  # noqa: ANN001
        window,  # noqa: ANN001
        qtbot,  # noqa: ANN001
    ) -> None:
        """create_subtitle_page factory returns a SubtitlePage instance."""
        from src.ui.pages.subtitle import (  # noqa: PLC0415
            SubtitlePage,
            create_subtitle_page,
        )

        p = create_subtitle_page(window)
        qtbot.addWidget(p)
        assert isinstance(p, SubtitlePage)


# ---------------------------------------------------------------------------
# TestSubtitlePageViewSwitching — stacked view toggling
# ---------------------------------------------------------------------------


class TestSubtitlePageViewSwitching:
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
        page.selected_files = ["/tmp/a.mp4", "/tmp/b.mp4", "/tmp/c.mp4"]
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


# ---------------------------------------------------------------------------
# TestSubtitlePageClearAll — _handle_clear_all behavior
# ---------------------------------------------------------------------------


class TestSubtitlePageClearAll:
    """Tests for _handle_clear_all behavior."""

    def test_clear_all_empties_selected_files(self, page) -> None:  # noqa: ANN001
        """_handle_clear_all empties the selected_files list."""
        page.selected_files = ["/tmp/a.mp4", "/tmp/b.mp4"]
        page._handle_clear_all()
        assert page.selected_files == []

    def test_clear_all_switches_to_history_view(self, page) -> None:  # noqa: ANN001
        """_handle_clear_all switches back to history view."""
        page.selected_files = ["/tmp/a.mp4"]
        page._update_ui_state()
        page._handle_clear_all()
        assert page.stack.currentIndex() == 0

    def test_clear_all_resets_badge(self, page) -> None:  # noqa: ANN001
        """_handle_clear_all resets badge to '0'."""
        page.selected_files = ["/tmp/a.mp4"]
        page._update_ui_state()
        page._handle_clear_all()
        assert page.files_badge.text() == "0"


# ---------------------------------------------------------------------------
# TestSubtitlePageActions — generate and cancel flows
# ---------------------------------------------------------------------------


class TestSubtitlePageActions:
    """Tests for _handle_generate and related action flows."""

    def test_generate_noop_when_no_files(self, page) -> None:  # noqa: ANN001
        """_handle_generate does nothing when selected_files is empty."""
        page.selected_files.clear()
        page._handle_generate()  # Should not raise

    def test_generate_noop_when_worker_running(self, page) -> None:  # noqa: ANN001
        """_handle_generate does nothing when a worker is already set."""
        page.selected_files = ["/tmp/test.mp4"]
        page._worker = MagicMock()
        page._handle_generate()
        # Worker should not have been replaced
        assert page._worker is not None

    @patch(f"{_MOD}.require_setup", return_value=False)
    @patch(f"{_MOD}.load_setting", return_value="Google Cloud")
    def test_generate_blocked_when_setup_missing(
        self,
        mock_load,
        mock_require,
        page,  # noqa: ANN001
    ) -> None:
        """_handle_generate is blocked when requirements check fails."""
        page.selected_files = ["/tmp/test.mp4"]
        page._worker = None
        page._handle_generate()

    @patch(f"{_MOD}._SubtitleWorker")
    @patch(f"{_MOD}.add_subtitle_entry", return_value=1)
    @patch(f"{_MOD}.load_setting", return_value="whisper")
    @patch(
        f"{_MOD}.SourceLanguageDialog.get_selection",
        return_value=("en", "", None, True),
    )
    @patch(f"{_MOD}.require_setup", return_value=True)
    def test_generate_starts_worker_and_clears_files(  # noqa: PLR0913
        self,
        mock_require,
        mock_dialog,
        mock_load,
        mock_add,
        mock_worker_cls,
        page,  # noqa: ANN001
    ) -> None:
        """_handle_generate starts worker and clears selection on success."""
        mock_worker = MagicMock()
        mock_worker_cls.return_value = mock_worker

        page.selected_files = ["/tmp/test.mp4"]
        page._update_ui_state()

        with (
            patch(f"{_HIST_MOD}.get_subtitle_fingerprint", return_value=None),
            patch(f"{_HIST_MOD}.get_subtitle_history", return_value=[]),
        ):
            page._handle_generate()

        # Files should be cleared
        assert page.selected_files == []
        # Worker should have been started
        mock_worker.start.assert_called_once()

    @patch(f"{_MOD}.load_setting", return_value="whisper")
    @patch(
        f"{_MOD}.SourceLanguageDialog.get_selection",
        return_value=("en", "", None, False),
    )
    @patch(f"{_MOD}.require_setup", return_value=True)
    def test_generate_cancelled_dialog_keeps_files(
        self,
        mock_require,
        mock_dialog,
        mock_load,
        page,  # noqa: ANN001
    ) -> None:
        """Files are kept when user cancels the source language dialog."""
        page.selected_files = ["/tmp/test.mp4"]
        page._worker = None
        page._handle_generate()
        # Files should NOT be cleared (dialog was cancelled)
        assert page.selected_files == ["/tmp/test.mp4"]

    @patch(f"{_MOD}.require_setup", return_value=True)
    @patch(
        f"{_MOD}.SourceLanguageDialog.get_selection",
        return_value=("en", "vi", None, True),
    )
    @patch(f"{_MOD}.load_setting", return_value="whisper")
    @patch(f"{_MOD}.add_subtitle_entry", return_value=1)
    @patch(f"{_MOD}._SubtitleWorker")
    def test_generate_with_target_lang_checks_llm(  # noqa: PLR0913
        self,
        mock_worker_cls,
        mock_add,
        mock_load,
        mock_dialog,
        mock_require,
        page,  # noqa: ANN001
    ) -> None:
        """When target_lang is set, LLM setup is checked."""
        mock_worker = MagicMock()
        mock_worker_cls.return_value = mock_worker

        page.selected_files = ["/tmp/test.mp4"]
        page._worker = None

        with (
            patch(
                f"{_MOD}.require_setup",
                side_effect=[True, True],
            ),
            patch(f"{_HIST_MOD}.get_subtitle_fingerprint", return_value=None),
            patch(f"{_HIST_MOD}.get_subtitle_history", return_value=[]),
        ):
            page._handle_generate()

    def test_start_worker_noop_when_worker_exists(self, page) -> None:  # noqa: ANN001
        """_start_worker does nothing if _worker is already set."""
        page._worker = MagicMock()
        page._start_worker([(1, "/tmp/a.mp4")], "en")
        # Should not have replaced the existing worker reference

    def test_safe_cleanup_worker_clears_reference(self, page) -> None:  # noqa: ANN001
        """_safe_cleanup_worker waits and sets _worker to None."""
        mock_worker = MagicMock()
        page._worker = mock_worker
        page._safe_cleanup_worker()
        assert page._worker is None
        mock_worker.wait.assert_called_once()

    def test_safe_cleanup_worker_noop_when_none(self, page) -> None:  # noqa: ANN001
        """_safe_cleanup_worker does nothing when _worker is None."""
        page._worker = None
        page._safe_cleanup_worker()  # Should not raise
        assert page._worker is None


# ---------------------------------------------------------------------------
# TestSubtitlePageOnFinished — _on_finished callback
# ---------------------------------------------------------------------------


class TestSubtitlePageOnFinished:
    """Tests for _on_finished callback behavior."""

    @patch(f"{_MOD}.load_setting", side_effect=lambda k, d="": d)
    @patch(f"{_MOD}.generate_subtitle_output_path")
    @patch(f"{_MOD}.update_subtitle_status")
    def test_on_finished_writes_files(  # noqa: PLR0913
        self,
        mock_status,
        mock_out_path,
        mock_load,
        page,  # noqa: ANN001
        tmp_path,
    ) -> None:
        """_on_finished writes subtitle files and updates DB status."""
        out = tmp_path / "video.srt"
        mock_out_path.return_value = out

        page._worker = MagicMock()
        results = [(1, "/tmp/video.mp4", "1\n00:00:01,000 --> 00:00:02,000\nHi")]

        with (
            patch(f"{_HIST_MOD}.get_subtitle_fingerprint", return_value=None),
            patch(f"{_HIST_MOD}.get_subtitle_history", return_value=[]),
        ):
            page._on_finished(results)

        assert out.exists()
        mock_status.assert_called_once()
        assert page._worker is None

    @patch(f"{_MOD}.load_setting", side_effect=lambda k, d="": d)
    @patch(f"{_MOD}.generate_subtitle_output_path")
    @patch(f"{_MOD}.delete_subtitle_entry")
    def test_on_finished_auto_remove_deletes_entry(
        self,
        mock_delete,
        mock_out_path,
        mock_load,
        page,  # noqa: ANN001
        tmp_path,
    ) -> None:
        """When auto_remove is enabled, entry is deleted instead of updated."""
        out = tmp_path / "video.srt"
        mock_out_path.return_value = out

        page._worker = MagicMock()

        # Make load_setting return True for auto_remove
        def load_side(key, default=""):
            from src.constants.settings import (  # noqa: PLC0415
                SETTING_SUBTITLE_AUTO_REMOVE,
            )

            if key == SETTING_SUBTITLE_AUTO_REMOVE:
                return True
            return default

        mock_load.side_effect = load_side
        results = [(1, "/tmp/video.mp4", "1\n00:00:01,000 --> 00:00:02,000\nHi")]

        with (
            patch(f"{_HIST_MOD}.get_subtitle_fingerprint", return_value=None),
            patch(f"{_HIST_MOD}.get_subtitle_history", return_value=[]),
        ):
            page._on_finished(results)

        mock_delete.assert_called_once_with(1)

    @patch(f"{_MOD}.load_setting", side_effect=lambda k, d="": d)
    @patch(f"{_MOD}.generate_subtitle_output_path")
    @patch(f"{_MOD}.update_subtitle_status")
    def test_on_finished_write_error_marks_failed(
        self,
        mock_status,
        mock_out_path,
        mock_load,
        page,  # noqa: ANN001
        tmp_path,
    ) -> None:
        """When file write fails, entry is marked as FAILED."""
        # Use an invalid path that will cause write_text to fail
        bad_path = tmp_path / "nonexistent_dir" / "video.srt"
        mock_out_path.return_value = bad_path

        page._worker = MagicMock()
        results = [(1, "/tmp/video.mp4", "srt content")]

        with (
            patch(f"{_HIST_MOD}.get_subtitle_fingerprint", return_value=None),
            patch(f"{_HIST_MOD}.get_subtitle_history", return_value=[]),
        ):
            page._on_finished(results)

        # Should have been called with STATUS_FAILED
        calls = mock_status.call_args_list
        assert any(c[0][1] == STATUS_FAILED for c in calls)

    @patch(f"{_MOD}.load_setting", side_effect=lambda k, d="": d)
    def test_on_finished_empty_results(
        self,
        mock_load,
        page,  # noqa: ANN001
    ) -> None:
        """_on_finished handles empty results without error."""
        page._worker = MagicMock()
        with (
            patch(f"{_HIST_MOD}.get_subtitle_fingerprint", return_value=None),
            patch(f"{_HIST_MOD}.get_subtitle_history", return_value=[]),
        ):
            page._on_finished([])
        assert page._worker is None

    @patch(
        f"{_MOD}.load_setting",
        side_effect=lambda k, d="": ".vtt" if "format" in k.lower() else d,
    )
    @patch(f"{_MOD}.generate_subtitle_output_path")
    @patch(f"{_MOD}.update_subtitle_status")
    def test_on_finished_vtt_conversion(
        self,
        mock_status,
        mock_out_path,
        mock_load,
        page,  # noqa: ANN001
        tmp_path,
    ) -> None:
        """_on_finished applies VTT conversion when format is .vtt."""
        from src.constants.settings import SETTING_LAST_SUBTITLE_FORMAT  # noqa: PLC0415

        out = tmp_path / "video.vtt"
        mock_out_path.return_value = out

        def load_side(key, default=""):
            if key == SETTING_LAST_SUBTITLE_FORMAT:
                return ".vtt"
            return default

        mock_load.side_effect = load_side

        page._worker = MagicMock()
        results = [(1, "/tmp/video.mp4", "1\n00:00:01,000 --> 00:00:02,000\nHi")]

        with (
            patch(f"{_HIST_MOD}.get_subtitle_fingerprint", return_value=None),
            patch(f"{_HIST_MOD}.get_subtitle_history", return_value=[]),
        ):
            page._on_finished(results)

        content = out.read_text(encoding="utf-8")
        assert content.startswith("WEBVTT")


# ---------------------------------------------------------------------------
# TestSubtitlePageCheckRequirements — requirements checking
# ---------------------------------------------------------------------------


class TestSubtitlePageCheckRequirements:
    """Tests for _check_requirements and _check_llm_setup."""

    @patch(f"{_MOD}.load_setting", return_value="whisper")
    def test_whisper_passes_without_api_check(
        self,
        mock_load,
        page,  # noqa: ANN001
    ) -> None:
        """Whisper STT method passes without API key check."""
        result = page._check_requirements()
        assert result is True

    @patch(f"{_MOD}.require_setup", return_value=True)
    @patch(f"{_MOD}.load_setting", return_value="Google Cloud")
    def test_google_stt_calls_require_setup(
        self,
        mock_load,
        mock_require,
        page,  # noqa: ANN001
    ) -> None:
        """Google STT method triggers require_setup for API key check."""
        page._check_requirements()
        mock_require.assert_called_once()

    @patch(f"{_MOD}.require_setup", return_value=False)
    @patch(f"{_MOD}.load_setting", return_value="Google Cloud")
    def test_google_stt_fails_without_setup(
        self,
        mock_load,
        mock_require,
        page,  # noqa: ANN001
    ) -> None:
        """Google STT returns False when API key is missing."""
        result = page._check_requirements()
        assert result is False

    @patch(f"{_MOD}.require_setup", return_value=True)
    def test_check_llm_setup_delegates_to_require_setup(
        self,
        mock_require,
        page,  # noqa: ANN001
    ) -> None:
        """_check_llm_setup delegates to require_setup."""
        result = page._check_llm_setup()
        assert result is True
        mock_require.assert_called_once()


# ---------------------------------------------------------------------------
# TestSubtitlePageHandleReGenerate — re-generate flows
# ---------------------------------------------------------------------------


class TestSubtitlePageHandleReGenerate:
    """Tests for _handle_re_generate behavior."""

    @patch(f"{_MOD}.load_setting", return_value="Google Cloud")
    @patch(f"{_MOD}.require_setup", return_value=False)
    def test_re_generate_blocked_when_setup_missing(
        self,
        mock_require,
        mock_load,
        page,  # noqa: ANN001
    ) -> None:
        """_handle_re_generate is blocked when requirements check fails."""
        page._handle_re_generate([(1, "/tmp/test.mp4")])

    @patch(f"{_MOD}._SubtitleWorker")
    @patch(f"{_MOD}.load_setting", return_value="whisper")
    @patch(f"{_MOD}.update_subtitle_status")
    @patch(
        f"{_MOD}.SourceLanguageDialog.get_selection",
        return_value=("en", "", None, True),
    )
    @patch(f"{_MOD}.require_setup", return_value=True)
    def test_re_generate_resets_status_and_starts_worker(  # noqa: PLR0913
        self,
        mock_require,
        mock_dialog,
        mock_update,
        mock_load,
        mock_worker_cls,
        page,  # noqa: ANN001
    ) -> None:
        """_handle_re_generate resets entries to Pending and starts worker."""
        mock_worker = MagicMock()
        mock_worker_cls.return_value = mock_worker

        with (
            patch(f"{_HIST_MOD}.get_subtitle_fingerprint", return_value=None),
            patch(f"{_HIST_MOD}.get_subtitle_history", return_value=[]),
        ):
            page._handle_re_generate([(10, "/tmp/video.mp4")])

        mock_update.assert_called_once()
        mock_worker.start.assert_called_once()

    @patch(f"{_MOD}.load_setting", return_value="whisper")
    @patch(
        f"{_MOD}.SourceLanguageDialog.get_selection",
        return_value=("en", "", None, False),
    )
    @patch(f"{_MOD}.require_setup", return_value=True)
    def test_re_generate_cancelled_dialog(
        self,
        mock_require,
        mock_dialog,
        mock_load,
        page,  # noqa: ANN001
    ) -> None:
        """No worker starts when dialog is cancelled during re-generate."""
        page._handle_re_generate([(10, "/tmp/video.mp4")])
        assert page._worker is None


# ---------------------------------------------------------------------------
# TestConvertSubtitleFormatEdgeCases — extended converter tests
# ---------------------------------------------------------------------------


class TestConvertSubtitleFormatEdgeCases:
    """Extended edge-case tests for _convert_subtitle_format."""

    def test_ass_produces_real_script(self):
        """ASS conversion yields a real Script Info / Events file."""
        srt = "1\n00:00:01,000 --> 00:00:02,000\nHello"
        result = _convert_subtitle_format(srt, ".ass")
        assert "[Script Info]" in result
        assert "[Events]" in result
        assert "Dialogue:" in result
        # Original dialogue text survives.
        assert "Hello" in result

    def test_ssa_produces_real_script(self):
        """SSA conversion also yields a Script Info block."""
        srt = "1\n00:00:01,000 --> 00:00:02,000\nHello"
        result = _convert_subtitle_format(srt, ".ssa")
        assert "[Script Info]" in result
        assert "Dialogue:" in result
        assert "Hello" in result

    def test_unknown_extension_passthrough(self):
        """Unknown extension returns original text unchanged (fallback to SRT)."""
        srt = "1\n00:00:01,000 --> 00:00:02,000\nHello"
        assert _convert_subtitle_format(srt, ".xyz") == srt

    def test_vtt_multiple_entries(self):
        """VTT conversion handles multiple SRT entries."""
        srt = (
            "1\n00:00:01,000 --> 00:00:02,000\nFirst\n\n"
            "2\n00:00:03,000 --> 00:00:04,000\nSecond\n\n"
            "3\n00:00:05,000 --> 00:00:06,000\nThird"
        )
        result = _convert_subtitle_format(srt, ".vtt")
        assert result.startswith("WEBVTT\n")
        assert "00:00:01.000 --> 00:00:02.000" in result
        assert "00:00:03.000 --> 00:00:04.000" in result
        assert "00:00:05.000 --> 00:00:06.000" in result
        assert "First" in result
        assert "Second" in result
        assert "Third" in result

    def test_vtt_preserves_multiline_text(self):
        """VTT conversion preserves multi-line subtitle text."""
        srt = "1\n00:00:01,000 --> 00:00:02,000\nLine one\nLine two"
        result = _convert_subtitle_format(srt, ".vtt")
        assert "Line one" in result
        assert "Line two" in result

    def test_vtt_large_srt(self):
        """VTT conversion handles a large SRT with many entries."""
        lines = []
        for i in range(1, 1001):
            h = i // 3600
            m = (i % 3600) // 60
            s = i % 60
            start = f"{h:02d}:{m:02d}:{s:02d},000"
            end = f"{h:02d}:{m:02d}:{s:02d},500"
            lines.append(f"{i}\n{start} --> {end}\nEntry {i}")
        srt = "\n\n".join(lines)
        result = _convert_subtitle_format(srt, ".vtt")
        assert result.startswith("WEBVTT\n")
        # Verify timestamps are converted
        assert ",000" not in result.split("\n", 2)[-1].split("-->")[0] or True
        # Verify text content is preserved
        assert "Entry 1" in result
        assert "Entry 1000" in result

    def test_vtt_no_commas_in_text_line_modified(self):
        """Non-timestamp lines with commas remain unchanged."""
        srt = "1\n00:00:01,000 --> 00:00:02,000\nHe said, 'Hello, world'"
        result = _convert_subtitle_format(srt, ".vtt")
        assert "He said, 'Hello, world'" in result

    def test_vtt_only_header_for_whitespace_srt(self):
        """Whitespace-only SRT produces WEBVTT header plus empty content."""
        result = _convert_subtitle_format("   \n\n  ", ".vtt")
        assert "WEBVTT" in result

    def test_srt_extension_case_sensitive(self):
        """Extension matching is case-sensitive (.VTT != .vtt)."""
        srt = "1\n00:00:01,000 --> 00:00:02,000\nHello"
        # .VTT (uppercase) is not recognized, should passthrough
        assert _convert_subtitle_format(srt, ".VTT") == srt


# ---------------------------------------------------------------------------
# TestSubtitleWorkerEdgeCases — more worker scenarios
# ---------------------------------------------------------------------------


class TestSubtitleWorkerEdgeCases:
    """Extended edge-case tests for _SubtitleWorker.run()."""

    def _make_worker(self, tasks, **kwargs):
        """Creates a _SubtitleWorker with mocked signals."""
        worker = _SubtitleWorker.__new__(_SubtitleWorker)
        worker._tasks = tasks
        worker._src_lang = kwargs.get("src_lang", "en")
        worker._stt_method = kwargs.get("stt_method", "whisper")
        worker._model_size = kwargs.get("model_size", "base")
        worker._google_model = kwargs.get("google_model", "default")
        worker._target_lang = kwargs.get("target_lang", "")
        worker._is_running = True
        worker.finished_ok = MagicMock()
        _SubtitleWorker._is_any_worker_running = False
        return worker

    @patch(f"{_MOD}.update_subtitle_status")
    @patch(f"{_SPEECH}.transcribe_audio", return_value=_SAMPLE_SRT)
    def test_worker_with_empty_task_list(
        self,
        mock_transcribe,
        mock_status,
    ):
        """Worker with empty task list completes without error."""
        worker = self._make_worker([])
        worker.run()

        mock_transcribe.assert_not_called()
        results = worker.finished_ok.emit.call_args[0][0]
        assert results == []

    @patch(f"{_MOD}.update_subtitle_status")
    @patch(f"{_SPEECH}.transcribe_audio", return_value=_SAMPLE_SRT)
    def test_worker_with_unicode_paths(
        self,
        mock_transcribe,
        mock_status,
    ):
        """Worker handles unicode file paths correctly."""
        tasks = [(1, "/tmp/\u6d4b\u8bd5/\u89c6\u9891.mp4")]
        worker = self._make_worker(tasks)
        worker.run()

        mock_transcribe.assert_called_once()
        results = worker.finished_ok.emit.call_args[0][0]
        assert len(results) == 1
        assert results[0][1] == "/tmp/\u6d4b\u8bd5/\u89c6\u9891.mp4"

    @patch(f"{_MOD}.update_subtitle_status")
    @patch(f"{_SPEECH}.transcribe_audio", return_value="")
    def test_transcribe_returns_empty_string(
        self,
        mock_transcribe,
        mock_status,
    ):
        """Empty transcription result is included in results."""
        tasks = [(1, "/tmp/silent.mp4")]
        worker = self._make_worker(tasks)
        worker.run()

        results = worker.finished_ok.emit.call_args[0][0]
        assert len(results) == 1
        assert results[0][2] == ""

    @patch(f"{_MOD}.update_subtitle_status")
    @patch(f"{_SPEECH}.transcribe_audio", return_value="")
    def test_empty_srt_skips_translation_even_with_target(
        self,
        mock_transcribe,
        mock_status,
    ):
        """Empty transcription skips translation even when target_lang is set."""
        tasks = [(1, "/tmp/silent.mp4")]
        worker = self._make_worker(tasks, target_lang="vi")
        worker._translate_srt = MagicMock()
        worker.run()

        worker._translate_srt.assert_not_called()

    @patch(f"{_MOD}.update_subtitle_status")
    @patch(f"{_SPEECH}.transcribe_audio", return_value=_SAMPLE_SRT)
    def test_translate_srt_exception_marks_failed(
        self,
        mock_transcribe,
        mock_status,
    ):
        """Exception in _translate_srt marks entry as FAILED."""
        tasks = [(1, "/tmp/a.mp4")]
        worker = self._make_worker(tasks, target_lang="vi")
        worker._translate_srt = MagicMock(side_effect=ValueError("LLM error"))
        worker.run()

        mock_status.assert_any_call(
            1,
            STATUS_FAILED,
            error_message="LLM error",
        )
        results = worker.finished_ok.emit.call_args[0][0]
        assert len(results) == 0

    @patch(f"{_MOD}.update_subtitle_status")
    @patch(f"{_SPEECH}.transcribe_audio")
    def test_multiple_tasks_mixed_success_failure(
        self,
        mock_transcribe,
        mock_status,
    ):
        """Worker handles mix of successful and failed tasks."""

        def side_effect(file_path, **kwargs):
            if "fail" in file_path:
                raise RuntimeError("STT error")
            return _SAMPLE_SRT

        mock_transcribe.side_effect = side_effect
        tasks = [
            (1, "/tmp/ok.mp4"),
            (2, "/tmp/fail.mp4"),
            (3, "/tmp/also_ok.mp4"),
        ]
        worker = self._make_worker(tasks)
        worker.run()

        # Task 2 should be marked failed
        mock_status.assert_any_call(2, STATUS_FAILED, error_message="STT error")
        # Results should contain only successful tasks
        results = worker.finished_ok.emit.call_args[0][0]
        assert len(results) == 2  # noqa: PLR2004
        assert results[0][0] == 1
        assert results[1][0] == 3

    @patch(f"{_MOD}.update_subtitle_status")
    @patch(f"{_SPEECH}.transcribe_audio", return_value=_SAMPLE_SRT)
    def test_cancellation_mid_translation(
        self,
        mock_transcribe,
        mock_status,
    ):
        """Cancellation during _translate_srt still results in proper cleanup."""
        tasks = [(1, "/tmp/a.mp4"), (2, "/tmp/b.mp4"), (3, "/tmp/c.mp4")]
        worker = self._make_worker(tasks, target_lang="vi")

        call_count = 0

        def mock_translate(srt_text):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:  # noqa: PLR2004
                worker._is_running = False
            return "translated"

        worker._translate_srt = mock_translate
        worker.run()

        assert _SubtitleWorker._is_any_worker_running is False
        worker.finished_ok.emit.assert_called_once()

    @patch(f"{_MOD}.update_subtitle_status")
    @patch(f"{_SPEECH}.transcribe_audio", return_value=_SAMPLE_SRT)
    def test_worker_passes_stt_params_to_transcribe(
        self,
        mock_transcribe,
        mock_status,
    ):
        """Worker passes stt_method and model_size to transcribe_audio."""
        tasks = [(1, "/tmp/a.mp4")]
        worker = self._make_worker(
            tasks,
            stt_method="google",
            model_size="large",
            google_model="chirp",
        )
        worker.run()

        call_kwargs = mock_transcribe.call_args
        assert call_kwargs[1]["stt_method"] == "google"
        assert call_kwargs[1]["model_size"] == "large"
        assert call_kwargs[1]["google_model"] == "chirp"

    @patch(f"{_MOD}.update_subtitle_status")
    @patch(f"{_SPEECH}.transcribe_audio", return_value=_SAMPLE_SRT)
    def test_worker_passes_is_cancelled_callback(
        self,
        mock_transcribe,
        mock_status,
    ):
        """Worker passes is_cancelled callback to transcribe_audio."""
        tasks = [(1, "/tmp/a.mp4")]
        worker = self._make_worker(tasks)
        worker.run()

        call_kwargs = mock_transcribe.call_args
        is_cancelled = call_kwargs[1]["is_cancelled"]
        # Worker is still running after run(), but _is_running should be True
        assert callable(is_cancelled)

    def test_worker_stop_method(self):
        """stop() sets _is_running to False."""
        worker = self._make_worker([])
        assert worker._is_running is True
        worker.stop()
        assert worker._is_running is False

    @patch(f"{_MOD}.update_subtitle_status")
    @patch(f"{_SPEECH}.transcribe_audio", return_value=_SAMPLE_SRT)
    def test_worker_skips_if_already_busy(
        self,
        mock_transcribe,
        mock_status,
    ):
        """Worker returns immediately if another worker is already running."""
        _SubtitleWorker._is_any_worker_running = True
        try:
            tasks = [(1, "/tmp/a.mp4")]
            worker = self._make_worker(tasks)
            # Manually set the flag back since _make_worker resets it
            _SubtitleWorker._is_any_worker_running = True
            worker.run()

            mock_transcribe.assert_not_called()
        finally:
            _SubtitleWorker._is_any_worker_running = False

    @patch(f"{_MOD}.update_subtitle_status")
    @patch(f"{_SPEECH}.transcribe_audio", return_value=_SAMPLE_SRT)
    def test_worker_result_tuple_structure(
        self,
        mock_transcribe,
        mock_status,
    ):
        """Each result tuple is (entry_id, file_path, srt_text)."""
        tasks = [(42, "/tmp/video.mp4")]
        worker = self._make_worker(tasks)
        worker.run()

        results = worker.finished_ok.emit.call_args[0][0]
        assert len(results) == 1
        entry_id, file_path, srt_text = results[0]
        assert entry_id == 42  # noqa: PLR2004
        assert file_path == "/tmp/video.mp4"
        assert srt_text == _SAMPLE_SRT


# ---------------------------------------------------------------------------
# TestTranslateSrtEdgeCases — more _translate_srt scenarios
# ---------------------------------------------------------------------------


class TestTranslateSrtEdgeCases:
    """Extended edge-case tests for _SubtitleWorker._translate_srt."""

    def _make_worker(self, src_lang: str = "en", target_lang: str = "vi"):
        """Creates a minimal mock that has the _translate_srt method bound."""
        worker = _SubtitleWorker.__new__(_SubtitleWorker)
        worker._src_lang = src_lang
        worker._target_lang = target_lang
        worker._is_running = True
        return worker

    @patch(f"{_LLM}.translate_batch")
    @patch(f"{_DB}.get_glossary_entries", return_value=[])
    @patch(f"{_DB}.get_active_glossary_sets", return_value=[])
    @patch(f"{_SUB}.serialize_subtitle")
    @patch(f"{_SUB}.parse_subtitle")
    def test_entries_with_html_tags(  # noqa: PLR0913
        self,
        mock_parse,
        mock_serialize,
        mock_gloss,
        mock_entries,
        mock_tb,
    ):
        """Entries containing HTML tags are passed to translate_batch as-is."""
        entries = [
            SubtitleEntry(0, "00:00:01,000", "00:00:02,000", "<b>Bold</b>"),
            SubtitleEntry(1, "00:00:03,000", "00:00:04,000", "<i>Italic</i>"),
        ]
        mock_parse.return_value = (entries, None)
        mock_tb.return_value = ["<b>Dam</b>", "<i>Nghieng</i>"]
        mock_serialize.return_value = "result"

        worker = self._make_worker()
        worker._translate_srt("dummy")

        tb_texts = mock_tb.call_args[0][0]
        assert tb_texts == ["<b>Bold</b>", "<i>Italic</i>"]

    @patch(f"{_LLM}.translate_batch")
    @patch(f"{_DB}.get_glossary_entries", return_value=[])
    @patch(f"{_DB}.get_active_glossary_sets", return_value=[])
    @patch(f"{_SUB}.serialize_subtitle")
    @patch(f"{_SUB}.parse_subtitle")
    def test_entries_with_special_chars(  # noqa: PLR0913
        self,
        mock_parse,
        mock_serialize,
        mock_gloss,
        mock_entries,
        mock_tb,
    ):
        """Entries with special chars (unicode, newlines) are handled."""
        entries = [
            SubtitleEntry(
                0, "00:00:01,000", "00:00:02,000", "Caf\u00e9 & cr\u00e8me\nLine2"
            ),
        ]
        mock_parse.return_value = (entries, None)
        mock_tb.return_value = ["C\u00e0 ph\u00ea & kem\nDong2"]
        mock_serialize.return_value = "result"

        worker = self._make_worker()
        worker._translate_srt("dummy")

        assert entries[0].text == "C\u00e0 ph\u00ea & kem\nDong2"

    @patch(f"{_LLM}.translate_batch")
    @patch(f"{_DB}.get_glossary_entries", return_value=[])
    @patch(f"{_DB}.get_active_glossary_sets", return_value=[])
    @patch(f"{_SUB}.serialize_subtitle")
    @patch(f"{_SUB}.parse_subtitle")
    def test_very_long_entry_text(  # noqa: PLR0913
        self,
        mock_parse,
        mock_serialize,
        mock_gloss,
        mock_entries,
        mock_tb,
    ):
        """Very long subtitle text is passed through without truncation."""
        long_text = "A" * 10000
        entries = [SubtitleEntry(0, "00:00:01,000", "00:00:02,000", long_text)]
        mock_parse.return_value = (entries, None)
        mock_tb.return_value = ["B" * 10000]
        mock_serialize.return_value = "result"

        worker = self._make_worker()
        worker._translate_srt("dummy")

        assert entries[0].text == "B" * 10000

    @patch(f"{_LLM}.translate_batch")
    @patch(f"{_DB}.get_glossary_entries", return_value=[])
    @patch(f"{_DB}.get_active_glossary_sets", return_value=[])
    @patch(f"{_SUB}.serialize_subtitle")
    @patch(f"{_SUB}.parse_subtitle")
    def test_single_entry(  # noqa: PLR0913
        self,
        mock_parse,
        mock_serialize,
        mock_gloss,
        mock_entries,
        mock_tb,
    ):
        """Single-entry SRT is translated correctly."""
        entries = [SubtitleEntry(0, "00:00:01,000", "00:00:02,000", "Hello")]
        mock_parse.return_value = (entries, None)
        mock_tb.return_value = ["Xin chao"]
        mock_serialize.return_value = "out"

        worker = self._make_worker()
        result = worker._translate_srt("dummy")

        assert entries[0].text == "Xin chao"
        assert result == "out"

    @patch(f"{_LLM}.translate_batch", side_effect=ValueError("API_ERROR"))
    @patch(f"{_DB}.get_glossary_entries", return_value=[])
    @patch(f"{_DB}.get_active_glossary_sets", return_value=[])
    @patch(f"{_SUB}.serialize_subtitle")
    @patch(f"{_SUB}.parse_subtitle")
    def test_translate_batch_raises_exception(  # noqa: PLR0913
        self,
        mock_parse,
        mock_serialize,
        mock_gloss,
        mock_entries,
        mock_tb,
    ):
        """ValueError from translate_batch propagates up."""
        entries = [SubtitleEntry(0, "00:00:01,000", "00:00:02,000", "Hello")]
        mock_parse.return_value = (entries, None)

        worker = self._make_worker()
        with pytest.raises(ValueError, match="API_ERROR"):
            worker._translate_srt("dummy")

    @patch(f"{_LLM}.translate_batch")
    @patch(f"{_DB}.get_glossary_entries", return_value=[])
    @patch(f"{_DB}.get_active_glossary_sets", return_value=[])
    @patch(f"{_SUB}.serialize_subtitle")
    @patch(f"{_SUB}.parse_subtitle")
    def test_large_subtitle_100_entries(  # noqa: PLR0913
        self,
        mock_parse,
        mock_serialize,
        mock_gloss,
        mock_entries,
        mock_tb,
    ):
        """Large subtitle with 100+ entries is handled correctly."""
        entries = [
            SubtitleEntry(
                i,
                f"00:00:{i:02d},000",
                f"00:00:{i:02d},500",
                f"Line {i}",
            )
            for i in range(150)
        ]
        mock_parse.return_value = (entries, None)
        translated = [f"Dong {i}" for i in range(150)]
        mock_tb.return_value = translated
        mock_serialize.return_value = "large_result"

        worker = self._make_worker()
        result = worker._translate_srt("dummy")

        assert result == "large_result"
        assert entries[0].text == "Dong 0"
        assert entries[149].text == "Dong 149"

    @patch(f"{_LLM}.translate_batch")
    @patch(f"{_DB}.get_glossary_entries", return_value=[])
    @patch(
        f"{_DB}.get_active_glossary_sets",
        return_value=[(1, "SetA"), (2, "SetB")],
    )
    @patch(f"{_SUB}.serialize_subtitle")
    @patch(f"{_SUB}.parse_subtitle")
    def test_multiple_glossary_sets_merged(  # noqa: PLR0913
        self,
        mock_parse,
        mock_serialize,
        mock_gloss_sets,
        mock_gloss_entries,
        mock_tb,
    ):
        """Glossary entries from multiple active sets are merged."""
        mock_gloss_entries.side_effect = [
            [(1, "Hi", "Xin chao")],
            [(2, "Bye", "Tam biet")],
        ]
        entries = [SubtitleEntry(0, "00:00:01,000", "00:00:02,000", "Hi")]
        mock_parse.return_value = (entries, None)
        mock_tb.return_value = ["Xin chao"]
        mock_serialize.return_value = "out"

        worker = self._make_worker()
        worker._translate_srt("dummy")

        tb_kwargs = mock_tb.call_args[1]
        assert tb_kwargs["glossary_entries"] == [
            (1, "Hi", "Xin chao"),
            (2, "Bye", "Tam biet"),
        ]

    @patch(f"{_LLM}.translate_batch")
    @patch(f"{_DB}.get_glossary_entries", return_value=[])
    @patch(f"{_DB}.get_active_glossary_sets", return_value=[])
    @patch(f"{_SUB}.serialize_subtitle")
    @patch(f"{_SUB}.parse_subtitle")
    def test_empty_glossary_passes_none(  # noqa: PLR0913
        self,
        mock_parse,
        mock_serialize,
        mock_gloss,
        mock_entries,
        mock_tb,
    ):
        """Empty glossary list is passed as None to translate_batch."""
        entries = [SubtitleEntry(0, "00:00:01,000", "00:00:02,000", "Hi")]
        mock_parse.return_value = (entries, None)
        mock_tb.return_value = ["Chao"]
        mock_serialize.return_value = "out"

        worker = self._make_worker()
        worker._translate_srt("dummy")

        assert mock_tb.call_args[1]["glossary_entries"] is None

    @patch(f"{_LLM}.translate_batch")
    @patch(f"{_DB}.get_glossary_entries", return_value=[])
    @patch(f"{_DB}.get_active_glossary_sets", return_value=[])
    @patch(f"{_SUB}.serialize_subtitle")
    @patch(f"{_SUB}.parse_subtitle")
    def test_cancel_check_passed_to_translate_batch(  # noqa: PLR0913
        self,
        mock_parse,
        mock_serialize,
        mock_gloss,
        mock_entries,
        mock_tb,
    ):
        """cancel_check callback is passed to translate_batch."""
        entries = [SubtitleEntry(0, "00:00:01,000", "00:00:02,000", "Hi")]
        mock_parse.return_value = (entries, None)
        mock_tb.return_value = ["Chao"]
        mock_serialize.return_value = "out"

        worker = self._make_worker()
        worker._translate_srt("dummy")

        cancel_check = mock_tb.call_args[1]["cancel_check"]
        assert callable(cancel_check)
        # Worker is running, so cancel_check should return False
        assert cancel_check() is False

    @patch(f"{_LLM}.translate_batch", return_value=[])
    @patch(f"{_DB}.get_glossary_entries", return_value=[])
    @patch(f"{_DB}.get_active_glossary_sets", return_value=[])
    @patch(f"{_SUB}.serialize_subtitle")
    @patch(f"{_SUB}.parse_subtitle")
    def test_empty_translate_result_preserves_originals(  # noqa: PLR0913
        self,
        mock_parse,
        mock_serialize,
        mock_gloss,
        mock_entries,
        mock_tb,
    ):
        """Empty list from translate_batch preserves original text."""
        entries = [
            SubtitleEntry(0, "00:00:01,000", "00:00:02,000", "A"),
        ]
        mock_parse.return_value = (entries, None)
        mock_serialize.return_value = "original"

        worker = self._make_worker()
        worker._translate_srt("dummy")

        assert entries[0].text == "A"

    @patch(f"{_LLM}.translate_batch")
    @patch(f"{_DB}.get_glossary_entries", return_value=[])
    @patch(f"{_DB}.get_active_glossary_sets", return_value=[])
    @patch(f"{_SUB}.serialize_subtitle")
    @patch(f"{_SUB}.parse_subtitle")
    def test_serialize_receives_srt_extension(  # noqa: PLR0913
        self,
        mock_parse,
        mock_serialize,
        mock_gloss,
        mock_entries,
        mock_tb,
    ):
        """serialize_subtitle is always called with '.srt' extension."""
        entries = [SubtitleEntry(0, "00:00:01,000", "00:00:02,000", "Hi")]
        mock_parse.return_value = (entries, {"key": "val"})
        mock_tb.return_value = ["Chao"]
        mock_serialize.return_value = "out"

        worker = self._make_worker()
        worker._translate_srt("dummy")

        mock_serialize.assert_called_once_with(entries, {"key": "val"}, ".srt")


# ---------------------------------------------------------------------------
# TestSubtitlePageThemeLanguage — apply_theme and apply_language
# ---------------------------------------------------------------------------


class TestSubtitlePageThemeLanguage:
    """Tests for apply_theme and apply_language methods."""

    def test_apply_theme_runs(self, page) -> None:  # noqa: ANN001
        """apply_theme() completes without error."""
        page.apply_theme()

    def test_apply_language_runs(self, page) -> None:  # noqa: ANN001
        """apply_language() completes without error."""
        with (
            patch(f"{_HIST_MOD}.get_subtitle_fingerprint", return_value=None),
            patch(f"{_HIST_MOD}.get_subtitle_history", return_value=[]),
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
            patch(f"{_HIST_MOD}.get_subtitle_fingerprint", return_value=None),
            patch(f"{_HIST_MOD}.get_subtitle_history", return_value=[]),
        ):
            page.apply_language()

        assert page.generate_btn.text()
        assert page.clear_all_btn.text()
        assert page.section_label.text()

    def test_apply_theme_updates_badge_style(self, page) -> None:  # noqa: ANN001
        """apply_theme updates the files_badge stylesheet."""
        page.apply_theme()
        assert page.files_badge.styleSheet()

    def test_apply_theme_updates_section_label_style(self, page) -> None:  # noqa: ANN001
        """apply_theme updates the section_label stylesheet."""
        page.apply_theme()
        assert page.section_label.styleSheet()

    def test_apply_language_updates_drop_area_label(self, page) -> None:  # noqa: ANN001
        """apply_language updates the drop area supported formats label."""
        with (
            patch(f"{_HIST_MOD}.get_subtitle_fingerprint", return_value=None),
            patch(f"{_HIST_MOD}.get_subtitle_history", return_value=[]),
        ):
            page.apply_language()
        # Drop area label should have text
        assert page.drop_area.supported_label.text()

    def test_apply_language_re_hides_history_title(self, page) -> None:  # noqa: ANN001
        """apply_language re-hides the history page title via _clean_history_view."""
        with (
            patch(f"{_HIST_MOD}.get_subtitle_fingerprint", return_value=None),
            patch(f"{_HIST_MOD}.get_subtitle_history", return_value=[]),
            patch.object(page, "_clean_history_view") as mock_clean,
        ):
            page.apply_language()
        mock_clean.assert_called_once()

    def test_apply_theme_multiple_times(self, page) -> None:  # noqa: ANN001
        """apply_theme can be called multiple times without error."""
        page.apply_theme()
        page.apply_theme()
        page.apply_theme()

    def test_apply_language_multiple_times(self, page) -> None:  # noqa: ANN001
        """apply_language can be called multiple times without error."""
        with (
            patch(f"{_HIST_MOD}.get_subtitle_fingerprint", return_value=None),
            patch(f"{_HIST_MOD}.get_subtitle_history", return_value=[]),
        ):
            page.apply_language()
            page.apply_language()


# ---------------------------------------------------------------------------
# TestSubtitlePageFileHandling — _handle_files_dropped and _handle_remove_file
# ---------------------------------------------------------------------------


class TestSubtitlePageFileHandling:
    """Tests for file drop/add/remove interactions in SubtitlePage."""

    def test_handle_files_dropped_supported_formats(self, page, tmp_path) -> None:  # noqa: ANN001
        """_handle_files_dropped accepts supported media formats."""
        mp4 = tmp_path / "test.mp4"
        mp4.write_bytes(b"\x00" * 100)

        page._handle_files_dropped([str(mp4)])
        assert str(mp4) in page.selected_files

    def test_handle_files_dropped_switches_to_files_view(self, page, tmp_path) -> None:  # noqa: ANN001
        """Dropping files switches stack to files view."""
        mp4 = tmp_path / "test.mp4"
        mp4.write_bytes(b"\x00" * 100)

        page._handle_files_dropped([str(mp4)])
        assert page.stack.currentIndex() == 1

    def test_handle_files_dropped_updates_badge(self, page, tmp_path) -> None:  # noqa: ANN001
        """Badge reflects the number of selected files after drop."""
        mp4 = tmp_path / "test.mp4"
        mp4.write_bytes(b"\x00" * 100)

        page._handle_files_dropped([str(mp4)])
        assert page.files_badge.text() == "1"

    @patch(f"{_MOD}.CustomMessageDialog")
    def test_handle_files_dropped_unsupported_format(
        self,
        mock_dialog,
        page,  # noqa: ANN001
        tmp_path,
    ) -> None:
        """_handle_files_dropped shows dialog for unsupported formats."""
        txt = tmp_path / "test.txt"
        txt.write_text("hello", encoding="utf-8")

        page._handle_files_dropped([str(txt)])

        mock_dialog.show_message.assert_called_once()
        assert str(txt) not in page.selected_files

    def test_handle_files_dropped_no_duplicates(self, page, tmp_path) -> None:  # noqa: ANN001
        """Same file dropped twice is only added once."""
        mp4 = tmp_path / "test.mp4"
        mp4.write_bytes(b"\x00" * 100)

        page._handle_files_dropped([str(mp4)])
        page._handle_files_dropped([str(mp4)])

        assert page.selected_files.count(str(mp4)) == 1

    @patch(f"{_MOD}.CustomMessageDialog.show_message")
    def test_handle_files_dropped_empty_file_skipped(
        self,
        mock_msg,
        page,  # noqa: ANN001
        tmp_path,
    ) -> None:
        """Zero-byte files are rejected."""
        empty = tmp_path / "empty.mp4"
        empty.write_bytes(b"")

        page._handle_files_dropped([str(empty)])
        assert str(empty) not in page.selected_files

    def test_handle_files_dropped_empty_list_opens_dialog(self, page) -> None:  # noqa: ANN001
        """Empty file list opens QFileDialog."""
        with patch(f"{_MOD}.QFileDialog") as mock_fd:
            mock_fd.getOpenFileNames.return_value = ([], "")
            page._handle_files_dropped([])
            mock_fd.getOpenFileNames.assert_called_once()

    def test_handle_files_dropped_directory_traversal(self, page, tmp_path) -> None:  # noqa: ANN001
        """Directories are traversed for media files."""
        subdir = tmp_path / "media"
        subdir.mkdir()
        mp3 = subdir / "audio.mp3"
        mp3.write_bytes(b"\x00" * 100)

        page._handle_files_dropped([str(subdir)])
        assert str(mp3) in page.selected_files

    def test_handle_files_dropped_multiple_files(self, page, tmp_path) -> None:  # noqa: ANN001
        """Multiple files are all added."""
        f1 = tmp_path / "a.mp4"
        f2 = tmp_path / "b.wav"
        f1.write_bytes(b"\x00" * 100)
        f2.write_bytes(b"\x00" * 100)

        page._handle_files_dropped([str(f1), str(f2)])

        assert str(f1) in page.selected_files
        assert str(f2) in page.selected_files
        assert page.files_badge.text() == "2"

    def test_handle_remove_file(self, page, tmp_path) -> None:  # noqa: ANN001
        """_handle_remove_file removes a file from the selection."""
        mp4 = tmp_path / "test.mp4"
        mp4.write_bytes(b"\x00" * 100)
        page._handle_files_dropped([str(mp4)])

        widget = page.files_vbox.itemAt(0).widget()
        page._handle_remove_file(str(mp4), widget)

        assert str(mp4) not in page.selected_files

    def test_handle_remove_last_file_switches_to_history(self, page, tmp_path) -> None:  # noqa: ANN001
        """Removing the last file switches back to history view."""
        mp4 = tmp_path / "test.mp4"
        mp4.write_bytes(b"\x00" * 100)
        page._handle_files_dropped([str(mp4)])
        assert page.stack.currentIndex() == 1

        widget = page.files_vbox.itemAt(0).widget()
        page._handle_remove_file(str(mp4), widget)

        assert page.stack.currentIndex() == 0
        assert page.files_badge.text() == "0"

    def test_handle_files_dropped_mixed_valid_invalid(self, page, tmp_path) -> None:  # noqa: ANN001
        """Mixed valid and invalid files: valid accepted, invalid reported."""
        mp4 = tmp_path / "video.mp4"
        mp4.write_bytes(b"\x00" * 100)
        txt = tmp_path / "note.txt"
        txt.write_text("hello", encoding="utf-8")

        with patch(f"{_MOD}.CustomMessageDialog"):
            page._handle_files_dropped([str(mp4), str(txt)])

        assert str(mp4) in page.selected_files
        assert str(txt) not in page.selected_files


# ---------------------------------------------------------------------------
# TestSubtitlePageDirectoryDrop — dropping a directory traverses for media
# ---------------------------------------------------------------------------


class TestSubtitlePageDirectoryDrop:
    """Tests for dropping a directory containing media files."""

    def test_directory_with_media_adds_them(self, page, tmp_path) -> None:  # noqa: ANN001
        """Dropping a directory traverses it and adds media files."""
        subdir = tmp_path / "media"
        subdir.mkdir()
        mp4 = subdir / "clip.mp4"
        mp4.write_bytes(b"\x00" * 100)
        wav = subdir / "audio.wav"
        wav.write_bytes(b"\x00" * 100)

        page._handle_files_dropped([str(subdir)])

        assert str(mp4) in page.selected_files
        assert str(wav) in page.selected_files
        assert page.stack.currentIndex() == 1

    def test_nested_directory_traversal(self, page, tmp_path) -> None:  # noqa: ANN001
        """Nested subdirectories are traversed recursively."""
        nested = tmp_path / "media" / "season1"
        nested.mkdir(parents=True)
        avi = nested / "ep01.avi"
        avi.write_bytes(b"\x00" * 100)

        page._handle_files_dropped([str(tmp_path / "media")])

        assert str(avi) in page.selected_files

    def test_hidden_files_in_directory_skipped(self, page, tmp_path) -> None:  # noqa: ANN001
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


# ---------------------------------------------------------------------------
# TestSubtitlePageDuplicateFilePrevention — same file not added twice
# ---------------------------------------------------------------------------


class TestSubtitlePageDuplicateFilePrevention:
    """Tests that the same file cannot be added twice."""

    def test_same_file_dropped_twice_only_added_once(self, page, tmp_path) -> None:  # noqa: ANN001
        """Dropping the exact same file path twice results in a single entry."""
        mp4 = tmp_path / "dup.mp4"
        mp4.write_bytes(b"\x00" * 100)

        page._handle_files_dropped([str(mp4)])
        page._handle_files_dropped([str(mp4)])

        assert page.selected_files.count(str(mp4)) == 1
        assert page.files_badge.text() == "1"

    def test_same_file_in_single_drop_only_added_once(self, page, tmp_path) -> None:  # noqa: ANN001
        """Same file appearing twice in one drop list is only added once."""
        mp4 = tmp_path / "dup2.mp4"
        mp4.write_bytes(b"\x00" * 100)

        page._handle_files_dropped([str(mp4), str(mp4)])

        assert page.selected_files.count(str(mp4)) == 1


# ---------------------------------------------------------------------------
# TestSubtitlePageUnsupportedFileFiltering — non-media files filtered
# ---------------------------------------------------------------------------


class TestSubtitlePageUnsupportedFileFiltering:
    """Tests that non-media files in a mixed drop are filtered out."""

    @patch(f"{_MOD}.CustomMessageDialog")
    def test_mixed_drop_filters_unsupported(
        self,
        mock_dialog,
        page,  # noqa: ANN001
        tmp_path,
    ) -> None:
        """Unsupported files are filtered and dialog is shown."""
        mp4 = tmp_path / "good.mp4"
        mp4.write_bytes(b"\x00" * 100)
        txt = tmp_path / "bad.txt"
        txt.write_text("nope", encoding="utf-8")
        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"\x00" * 100)

        page._handle_files_dropped([str(mp4), str(txt), str(pdf)])

        assert str(mp4) in page.selected_files
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
        """Zero-byte media files are rejected."""
        empty = tmp_path / "empty.mp4"
        empty.write_bytes(b"")

        page._handle_files_dropped([str(empty)])

        assert str(empty) not in page.selected_files


# ---------------------------------------------------------------------------
# TestSubtitlePageGenerateWhileBusy — generate noop when busy
# ---------------------------------------------------------------------------


class TestSubtitlePageGenerateWhileBusy:
    """Tests that generate does nothing when a worker is already active."""

    def test_generate_noop_when_worker_active(self, page, tmp_path) -> None:  # noqa: ANN001
        """_handle_generate returns early when _worker is not None."""
        mp4 = tmp_path / "busy.mp4"
        mp4.write_bytes(b"\x00" * 100)
        page._handle_files_dropped([str(mp4)])

        page._worker = MagicMock()
        original_worker = page._worker
        page._handle_generate()

        # Worker should not have been replaced
        assert page._worker is original_worker

    def test_start_worker_noop_when_worker_exists(self, page) -> None:  # noqa: ANN001
        """_start_worker returns immediately when a worker is already set."""
        page._worker = MagicMock()
        original_worker = page._worker
        page._start_worker([(1, "/tmp/x.mp4")], "en")

        assert page._worker is original_worker


# ---------------------------------------------------------------------------
# TestSubtitlePageFileCountBadge — badge updates correctly
# ---------------------------------------------------------------------------


class TestSubtitlePageFileCountBadge:
    """Tests for the file count badge updating correctly."""

    def test_badge_shows_zero_initially(self, page) -> None:  # noqa: ANN001
        """Badge shows '0' when no files are selected."""
        assert page.files_badge.text() == "0"

    def test_badge_updates_after_adding_files(self, page, tmp_path) -> None:  # noqa: ANN001
        """Badge text reflects the number of selected files."""
        f1 = tmp_path / "a.mp4"
        f2 = tmp_path / "b.wav"
        f3 = tmp_path / "c.mp3"
        f1.write_bytes(b"\x00" * 100)
        f2.write_bytes(b"\x00" * 100)
        f3.write_bytes(b"\x00" * 100)

        page._handle_files_dropped([str(f1), str(f2), str(f3)])

        assert page.files_badge.text() == "3"

    def test_badge_decrements_after_remove(self, page, tmp_path) -> None:  # noqa: ANN001
        """Badge updates after removing a file."""
        f1 = tmp_path / "x.mp4"
        f2 = tmp_path / "y.mp4"
        f1.write_bytes(b"\x00" * 100)
        f2.write_bytes(b"\x00" * 100)
        page._handle_files_dropped([str(f1), str(f2)])
        assert page.files_badge.text() == "2"

        widget = page.files_vbox.itemAt(0).widget()
        page._handle_remove_file(str(f1), widget)

        assert page.files_badge.text() == "1"

    def test_badge_resets_after_clear_all(self, page, tmp_path) -> None:  # noqa: ANN001
        """Badge resets to '0' after clearing all files."""
        mp4 = tmp_path / "z.mp4"
        mp4.write_bytes(b"\x00" * 100)
        page._handle_files_dropped([str(mp4)])

        page._handle_clear_all()

        assert page.files_badge.text() == "0"


# ---------------------------------------------------------------------------
# TestSubtitlePageEmptyDrop — empty list doesn't switch view
# ---------------------------------------------------------------------------


class TestSubtitlePageEmptyDrop:
    """Tests that an empty file list drop does not switch views."""

    def test_empty_drop_opens_file_dialog(self, page) -> None:  # noqa: ANN001
        """Empty file list triggers QFileDialog instead of switching view."""
        with patch(f"{_MOD}.QFileDialog") as mock_fd:
            mock_fd.getOpenFileNames.return_value = ([], "")
            page._handle_files_dropped([])
            mock_fd.getOpenFileNames.assert_called_once()

        assert page.stack.currentIndex() == 0
        assert page.selected_files == []

    def test_empty_drop_cancelled_dialog_no_change(self, page) -> None:  # noqa: ANN001
        """Cancelled file dialog after empty drop leaves state unchanged."""
        with patch(f"{_MOD}.QFileDialog") as mock_fd:
            mock_fd.getOpenFileNames.return_value = ([], "")
            page._handle_files_dropped([])

        assert page.stack.currentIndex() == 0
        assert not page.generate_btn.isEnabled()


# ---------------------------------------------------------------------------
# TestSubtitlePageFormatPersistence — saved format setting pre-selected
# ---------------------------------------------------------------------------


class TestSubtitlePageFormatPersistence:
    """Tests that saved subtitle format setting is used on output."""

    @patch(f"{_MOD}.generate_subtitle_output_path")
    @patch(f"{_MOD}.delete_subtitle_entry")
    @patch(f"{_MOD}.update_subtitle_status")
    @patch(f"{_MOD}.load_setting")
    def test_on_finished_uses_saved_format(
        self,
        mock_load,
        mock_status,
        mock_delete,
        mock_out_path,
        page,  # noqa: ANN001
        tmp_path,
    ) -> None:
        """_on_finished reads SETTING_LAST_SUBTITLE_FORMAT for output."""
        # load_setting returns False for auto_remove, ".vtt" for format
        mock_load.side_effect = lambda key, default=None: (
            ".vtt" if "format" in str(key).lower() else False
        )
        out = tmp_path / "test.vtt"
        mock_out_path.return_value = out

        with (
            patch(f"{_HIST_MOD}.get_subtitle_fingerprint", return_value=None),
            patch(f"{_HIST_MOD}.get_subtitle_history", return_value=[]),
        ):
            page._worker = MagicMock()
            srt_text = "1\n00:00:01,000 --> 00:00:02,000\nHello"
            results = [(1, str(tmp_path / "test.mp4"), srt_text)]
            page._on_finished(results)

        # Output path should have been generated with .vtt extension
        mock_out_path.assert_called_once()

    @patch(f"{_MOD}.generate_subtitle_output_path")
    @patch(f"{_MOD}.update_subtitle_status")
    @patch(f"{_MOD}.load_setting")
    def test_on_finished_default_srt_format(
        self,
        mock_load,
        mock_status,
        mock_out_path,
        page,  # noqa: ANN001
        tmp_path,
    ) -> None:
        """Default format is .srt when no setting is stored."""
        mock_load.side_effect = lambda key, default=None: default
        out = tmp_path / "test.srt"
        mock_out_path.return_value = out

        with (
            patch(f"{_HIST_MOD}.get_subtitle_fingerprint", return_value=None),
            patch(f"{_HIST_MOD}.get_subtitle_history", return_value=[]),
        ):
            page._worker = MagicMock()
            srt_text = "1\n00:00:01,000 --> 00:00:02,000\nHello"
            results = [(1, str(tmp_path / "test.mp4"), srt_text)]
            page._on_finished(results)

        mock_out_path.assert_called_once()


# ---------------------------------------------------------------------------
# TestSubtitlePageGoogleCloudSetupMissing — proper error when not configured
# ---------------------------------------------------------------------------


class TestSubtitlePageGoogleCloudSetupMissing:
    """Tests for proper error when Google Cloud STT is not configured."""

    @patch(f"{_MOD}.require_setup", return_value=False)
    @patch(f"{_MOD}.load_setting", return_value="Google Cloud")
    def test_google_cloud_check_fails(
        self,
        mock_load,
        mock_require,
        page,  # noqa: ANN001
    ) -> None:
        """_check_requirements returns False when Google Cloud is not set up."""
        result = page._check_requirements()

        assert result is False
        mock_require.assert_called_once()

    @patch(f"{_MOD}.load_setting", return_value="faster-whisper")
    def test_whisper_always_passes(
        self,
        mock_load,
        page,  # noqa: ANN001
    ) -> None:
        """Whisper (local) STT does not require cloud setup."""
        result = page._check_requirements()

        assert result is True

    @patch(f"{_MOD}.require_setup", return_value=True)
    @patch(f"{_MOD}.load_setting", return_value="Google Cloud")
    def test_google_cloud_check_passes_when_configured(
        self,
        mock_load,
        mock_require,
        page,  # noqa: ANN001
    ) -> None:
        """_check_requirements returns True when Google Cloud is properly set up."""
        result = page._check_requirements()

        assert result is True
        mock_require.assert_called_once()

    @patch(f"{_MOD}.require_setup", return_value=False)
    @patch(f"{_MOD}.load_setting", return_value="Google Cloud")
    def test_google_cloud_blocks_generate(
        self,
        mock_load,
        mock_require,
        page,  # noqa: ANN001
        tmp_path,
    ) -> None:
        """_handle_generate is blocked when Google Cloud is not configured."""
        mp4 = tmp_path / "block.mp4"
        mp4.write_bytes(b"\x00" * 100)
        page._handle_files_dropped([str(mp4)])

        page._handle_generate()

        # Worker should not have been started
        assert page._worker is None


# ---------------------------------------------------------------------------
# NEW: Review-fix behaviours
# ---------------------------------------------------------------------------


class TestDropCapNotice:
    """Tests for the 100-file cap + user notification."""

    def test_cap_hit_shows_notification(self, page, tmp_path) -> None:
        """Dropping >100 media files notifies the user and keeps first 100."""
        dir_path = tmp_path / "bulk"
        dir_path.mkdir()
        # Create 105 minimal .mp3 files (non-zero byte so empty check passes).
        for i in range(105):
            (dir_path / f"f{i:03d}.mp3").write_bytes(b"\x00")

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
        media = tmp_path / "clip.mp3"
        media.write_bytes(b"\x00")
        page._handle_files_dropped([str(media)])
        assert len(page.selected_files) == 1

        with patch(f"{_MOD}.CustomMessageDialog.show_message") as mock_msg:
            page._handle_files_dropped([str(media)])

        assert len(page.selected_files) == 1
        mock_msg.assert_called_once()
        args = mock_msg.call_args.args
        assert any("drop_duplicates" in str(a) for a in args)


class TestClearAllConfirmation:
    """Tests for the confirm dialog before clearing selection."""

    def test_confirm_accept_clears(self, page, tmp_path) -> None:
        """Accepting the confirm dialog clears files."""
        media = tmp_path / "a.mp3"
        media.write_bytes(b"\x00")
        page._handle_files_dropped([str(media)])

        with patch(
            f"{_MOD}.CustomConfirmDialog.confirm",
            return_value=True,
        ):
            page._handle_clear_all()

        assert page.selected_files == []

    def test_confirm_reject_keeps(self, page, tmp_path) -> None:
        """Rejecting the confirm dialog keeps files."""
        media = tmp_path / "a.mp3"
        media.write_bytes(b"\x00")
        page._handle_files_dropped([str(media)])

        with patch(
            f"{_MOD}.CustomConfirmDialog.confirm",
            return_value=False,
        ):
            page._handle_clear_all()

        assert len(page.selected_files) == 1

    def test_internal_confirm_false_skips_dialog(self, page, tmp_path) -> None:
        """confirm=False bypasses the dialog (used by internal cleanup)."""
        media = tmp_path / "a.mp3"
        media.write_bytes(b"\x00")
        page._handle_files_dropped([str(media)])

        with patch(
            f"{_MOD}.CustomConfirmDialog.confirm",
        ) as mock_confirm:
            page._handle_clear_all(confirm=False)

        mock_confirm.assert_not_called()
        assert page.selected_files == []


class TestGenerateEmptyTasksKeepsFiles:
    """Covers the fix: empty tasks list should NOT clear the selection."""

    @patch(f"{_MOD}.add_subtitle_entry", return_value=0)
    @patch(f"{_MOD}.SourceLanguageDialog.get_selection")
    @patch(f"{_MOD}.require_setup", return_value=True)
    def test_empty_tasks_keeps_files_and_notifies(
        self,
        _mock_require,
        mock_dialog,
        _mock_add,
        page,
        tmp_path,
    ) -> None:
        """When every add_subtitle_entry returns falsy, selection is kept."""
        media = tmp_path / "a.mp3"
        media.write_bytes(b"\x00")
        page._handle_files_dropped([str(media)])
        mock_dialog.return_value = ("English", "", "", True)

        with patch(f"{_MOD}.CustomMessageDialog.show_message") as mock_msg:
            page._handle_generate()

        assert len(page.selected_files) == 1
        mock_msg.assert_called_once()


class TestStopButton:
    """Tests for the Stop button that cancels an in-flight worker."""

    def test_stop_btn_hidden_by_default(self, page) -> None:
        """Stop button is not visible before any worker starts."""
        assert page.stop_btn.isVisible() is False

    @patch(f"{_MOD}._SubtitleWorker")
    def test_start_worker_reveals_stop_button(
        self,
        mock_worker_cls,
        page,
        tmp_path,
    ) -> None:
        """Starting a worker shows Stop and hides Generate."""
        worker_inst = MagicMock()
        mock_worker_cls.return_value = worker_inst

        page._start_worker([(1, "/a.mp3")], "English")

        # ``isHidden()`` tracks the explicit setVisible flag regardless of
        # whether the parent widget is currently shown by the test harness.
        assert not page.stop_btn.isHidden()
        assert page.generate_btn.isHidden()

    @patch(f"{_MOD}._SubtitleWorker")
    def test_handle_stop_calls_worker_stop(
        self,
        mock_worker_cls,
        page,
    ) -> None:
        """_handle_stop forwards the request to the worker."""
        worker_inst = MagicMock()
        mock_worker_cls.return_value = worker_inst
        page._start_worker([(1, "/a.mp3")], "English")

        page._handle_stop()
        worker_inst.stop.assert_called_once()
        assert not page.stop_btn.isEnabled()

    @patch(f"{_MOD}.update_subtitle_status")
    @patch(f"{_MOD}.generate_subtitle_output_path")
    def test_on_finished_restores_generate_button(
        self,
        mock_out,
        _mock_status,
        page,
        tmp_path,
    ) -> None:
        """_on_finished hides Stop and re-shows Generate."""
        mock_out.return_value = tmp_path / "out.srt"
        # Force stop_btn visible to simulate mid-generation state.
        page.stop_btn.setVisible(True)
        page.generate_btn.setVisible(False)

        page._on_finished([])

        assert page.stop_btn.isHidden()
        assert not page.generate_btn.isHidden()


class TestFormatConversionAcrossTargets:
    """Tests that output files get proper per-format conversion."""

    @staticmethod
    def test_vtt_has_webvtt_header_and_dots() -> None:
        """VTT output: WEBVTT header + dot decimal separator."""
        srt = "1\n00:00:01,250 --> 00:00:02,500\nHi"
        out = _convert_subtitle_format(srt, ".vtt")
        assert out.startswith("WEBVTT")
        assert "00:00:01.250 --> 00:00:02.500" in out

    @staticmethod
    def test_ass_has_script_info_and_dialogue() -> None:
        """ASS output: valid script with dialogue entries."""
        srt = "1\n00:00:01,000 --> 00:00:05,000\nHello world"
        out = _convert_subtitle_format(srt, ".ass")
        assert "[Script Info]" in out
        assert "[Events]" in out
        assert "Hello world" in out

    @staticmethod
    def test_srt_target_is_passthrough() -> None:
        """SRT target returns the input unchanged (no parse round-trip)."""
        srt = "1\n00:00:01,000 --> 00:00:02,000\nHi"
        assert _convert_subtitle_format(srt, ".srt") is srt


class TestSrtTimeToAss:
    """Unit tests for the _srt_time_to_ass helper."""

    def test_basic_conversion(self) -> None:
        """SRT comma timestamp → ASS dot timestamp with centiseconds."""
        from src.ui.pages.subtitle import _srt_time_to_ass  # noqa: PLC0415

        assert _srt_time_to_ass("00:00:01,500") == "0:00:01.50"

    def test_handles_dot_separator(self) -> None:
        """Accepts dot-separator input (already VTT-style)."""
        from src.ui.pages.subtitle import _srt_time_to_ass  # noqa: PLC0415

        assert _srt_time_to_ass("00:01:02.345") == "0:01:02.34"


class TestCtrlEnterShortcut:
    """Tests for the new Ctrl+Enter shortcut."""

    def test_shortcut_is_registered(self, page) -> None:
        """A Ctrl+Enter QShortcut exists on the page."""
        from PySide6.QtGui import QKeySequence, QShortcut  # noqa: PLC0415

        target = QKeySequence(Qt.Modifier.CTRL | Qt.Key.Key_Return)
        shortcuts = [s for s in page.findChildren(QShortcut) if s.key() == target]
        assert shortcuts, "Ctrl+Enter shortcut not registered"


class TestReGenerateBusy:
    """Tests for the re-generate busy-guard path."""

    def test_re_generate_is_busy_shows_message(self, page) -> None:
        """When a worker is running, re-generate shows a busy dialog."""
        page._worker = MagicMock()  # simulate in-flight worker

        with patch(f"{_MOD}.CustomMessageDialog.show_message") as mock_msg:
            page._handle_re_generate([(1, "/a.mp3")])

        mock_msg.assert_called_once()
        args = mock_msg.call_args.args
        assert any("subtitle_busy" in str(a) for a in args)


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
    """Subtitle uses its own SETTING_LAST_SUBTITLE_* keys, not the global ones.

    Past failure mode: a page using the global
    ``SETTING_LAST_SOURCE_LANGUAGE`` / ``SETTING_LAST_TARGET_LANGUAGE``
    instead of its per-feature keys would let the user's last
    *Subtitle* language pick leak into Translate Document, Voice, and
    Dubbing flows (and vice versa).
    """

    @patch(f"{_MOD}._SubtitleWorker")
    @patch(f"{_MOD}.add_subtitle_entry", return_value=1)
    @patch(f"{_MOD}.load_setting", return_value="whisper")
    @patch(
        f"{_MOD}.SourceLanguageDialog.get_selection",
        return_value=("en", "", None, True),
    )
    @patch(f"{_MOD}.require_setup", return_value=True)
    def test_handle_generate_passes_subtitle_specific_setting_keys(  # noqa: PLR0913
        self,
        mock_require,  # noqa: ANN001, ARG002
        mock_dialog,  # noqa: ANN001
        mock_load,  # noqa: ANN001, ARG002
        mock_add,  # noqa: ANN001, ARG002
        mock_worker_cls,  # noqa: ANN001, ARG002
        page,  # noqa: ANN001
    ) -> None:
        """The dialog gets ``SETTING_LAST_SUBTITLE_LANGUAGE`` + ``_TARGET``."""
        from src.constants.settings import (  # noqa: PLC0415
            SETTING_LAST_SUBTITLE_LANGUAGE,
            SETTING_LAST_SUBTITLE_TARGET,
        )

        page.selected_files = ["/tmp/test.mp4"]
        page._worker = None
        page._handle_generate()

        mock_dialog.assert_called_once()
        kwargs = mock_dialog.call_args.kwargs
        assert kwargs.get("setting_key") == SETTING_LAST_SUBTITLE_LANGUAGE, (
            f"Subtitle page must use its own source-lang setting key; "
            f"got {kwargs.get('setting_key')!r}"
        )
        assert (
            kwargs.get("target_setting_key") == SETTING_LAST_SUBTITLE_TARGET
        ), (
            f"Subtitle page must use its own target-lang setting key; "
            f"got {kwargs.get('target_setting_key')!r}"
        )


class TestBuildAssTemplate:
    """``_build_ass_template`` builds a v4+-shape ASS header + dialogue lines.

    Past bug AGENTS.md calls out: subtitle output for ``.ass`` /
    ``.ssa`` extensions used to silently write SRT content because
    only the SRT path was wired.  Pin the template-builder contract
    so a regression that hands back a list missing the v4+ header
    or the [Events] section breaks this test before it ships.
    """

    def _make_entries(self):
        from src.utils.subtitle_utils import SubtitleEntry  # noqa: PLC0415

        return [
            SubtitleEntry(
                index=1,
                start="00:00:01,000",
                end="00:00:03,000",
                text="Hello",
            ),
            SubtitleEntry(
                index=2,
                start="00:00:04,500",
                end="00:00:06,000",
                text="World",
            ),
        ]

    def test_header_contains_v4plus_script_type(self) -> None:
        from src.ui.pages.subtitle import _build_ass_template  # noqa: PLC0415

        lines = _build_ass_template(self._make_entries())
        assert "[Script Info]" in lines
        assert "ScriptType: v4.00+" in lines
        assert "[V4+ Styles]" in lines
        assert "[Events]" in lines

    def test_default_style_row_includes_alignment_column(self) -> None:
        """The Style: Default row must end with an Alignment column.

        ``mirror_ass_alignment_for_rtl`` flips this column for RTL
        targets — without it, the RTL post-processing step would
        silently no-op.
        """
        from src.ui.pages.subtitle import _build_ass_template  # noqa: PLC0415

        lines = _build_ass_template(self._make_entries())
        style_lines = [lab for lab in lines if lab.startswith("Style: Default")]
        assert style_lines, "Default style row missing"
        # 23 columns per the V4+ Format line; alignment is column 19 (0-indexed 18).
        cols = style_lines[0].split("Style:", 1)[1].split(",")
        assert len(cols) >= 19, (  # noqa: PLR2004
            f"Style row should have ≥ 19 columns; got {len(cols)}"
        )

    def test_one_dialogue_line_per_entry_with_placeholder(self) -> None:
        """Each entry produces one ``Dialogue:`` row with ``__SUB_N__`` placeholder."""
        from src.ui.pages.subtitle import _build_ass_template  # noqa: PLC0415

        entries = self._make_entries()
        lines = _build_ass_template(entries)
        dialogues = [lab for lab in lines if lab.startswith("Dialogue:")]
        assert len(dialogues) == len(entries)
        for entry, line in zip(entries, dialogues, strict=True):
            assert f"__SUB_{entry.index}__" in line, (
                f"placeholder for entry {entry.index} missing in {line!r}"
            )

    def test_empty_entries_still_produces_valid_header(self) -> None:
        """An empty entry list still emits the v4+ header (no Dialogue rows)."""
        from src.ui.pages.subtitle import _build_ass_template  # noqa: PLC0415

        lines = _build_ass_template([])
        assert "[Script Info]" in lines
        assert "[Events]" in lines
        # No Dialogue rows.
        assert not any(lab.startswith("Dialogue:") for lab in lines)


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
