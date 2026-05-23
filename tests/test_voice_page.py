"""Unit tests for _VoiceWorker.run() logic and VoicePage UI in voice.py."""

from unittest.mock import MagicMock, call, patch

import pytest
from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QWidget,
)

from src.constants.history import (
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_GENERATING,
    STATUS_PENDING,
)
from src.ui.pages.voice import _VoiceWorker
from src.utils.subtitle_utils import SubtitleEntry

# Module path for patching module-level imports (at usage site)
_MOD = "src.ui.pages.voice"
# Module path for voice_history page (used by VoicePage internally)
_HIST_MOD = "src.ui.pages.voice_history"
# Source modules for patching local imports (inside run())
_SPEECH = "src.core.speech_engine"
_SUB = "src.utils.subtitle_utils"


@pytest.fixture(autouse=True)
def _auto_mock_blocking_dialogs():
    """Auto-mocks modal dialogs on the voice page so tests don't hang."""
    with (
        patch(
            "src.ui.pages.voice.CustomConfirmDialog.confirm",
            return_value=True,
        ),
        patch("src.ui.pages.voice.CustomMessageDialog.show_message"),
        patch(
            "src.core.speech_engine.check_ffmpeg_available",
            return_value=True,
        ),
    ):
        yield


# ---------------------------------------------------------------------------
# _VoiceWorker.run() logic (mock QThread and signals)
# ---------------------------------------------------------------------------


class TestVoiceWorkerRun:
    """Tests for the voice worker's run() method with mocked dependencies."""

    def _make_worker(self, tasks, **kwargs):
        """Creates a _VoiceWorker with mocked signals."""
        worker = _VoiceWorker.__new__(_VoiceWorker)
        worker._tasks = tasks
        worker._target_lang = kwargs.get("target_lang", "en-US")
        worker._voice_gender = kwargs.get("voice_gender", "Female")
        worker._tts_method = kwargs.get("tts_method", "edge")
        worker._audio_format = kwargs.get("audio_format", ".mp3")
        worker._is_running = True
        worker.finished_ok = MagicMock()
        # Ensure the class-level busy flag starts clean
        _VoiceWorker._is_any_worker_running = False
        return worker

    @patch(f"{_MOD}.generate_voice_output_path")
    @patch(f"{_MOD}.update_voice_status")
    @patch(f"{_SPEECH}.synthesize_speech")
    @patch(f"{_SPEECH}.synthesize_timed_speech")
    @patch(f"{_SUB}.is_subtitle_format", return_value=True)
    @patch(f"{_SUB}.parse_subtitle")
    def test_subtitle_format_uses_timed_speech(  # noqa: PLR0913
        self,
        mock_parse,
        mock_is_sub,
        mock_timed,
        mock_speech,
        mock_status,
        mock_out_path,
        tmp_path,
    ):
        """Subtitle files are routed to synthesize_timed_speech."""
        srt_file = tmp_path / "test.srt"
        srt_file.write_text(
            "1\n00:00:01,000 --> 00:00:02,000\nHello",
            encoding="utf-8",
        )
        entries = [SubtitleEntry(0, "00:00:01,000", "00:00:02,000", "Hello")]
        mock_parse.return_value = (entries, None)
        out = tmp_path / "test.mp3"
        mock_out_path.return_value = out

        tasks = [(1, str(srt_file))]
        worker = self._make_worker(tasks)
        worker.run()

        mock_timed.assert_called_once()
        mock_speech.assert_not_called()
        results = worker.finished_ok.emit.call_args[0][0]
        assert len(results) == 1

    @patch(f"{_MOD}.generate_voice_output_path")
    @patch(f"{_MOD}.update_voice_status")
    @patch(f"{_SPEECH}.synthesize_speech")
    @patch(f"{_SPEECH}.synthesize_timed_speech")
    @patch(f"{_SUB}.is_subtitle_format", return_value=False)
    @patch(f"{_SUB}.parse_subtitle")
    def test_plain_text_uses_synthesize_speech(  # noqa: PLR0913
        self,
        mock_parse,
        mock_is_sub,
        mock_timed,
        mock_speech,
        mock_status,
        mock_out_path,
        tmp_path,
    ):
        """Plain text files are routed to synthesize_speech."""
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("Hello world", encoding="utf-8")
        out = tmp_path / "test.mp3"
        mock_out_path.return_value = out

        tasks = [(1, str(txt_file))]
        worker = self._make_worker(tasks)
        worker.run()

        mock_speech.assert_called_once()
        mock_timed.assert_not_called()

    @patch(f"{_MOD}.generate_voice_output_path")
    @patch(f"{_MOD}.update_voice_status")
    @patch(f"{_SPEECH}.synthesize_timed_speech")
    @patch(f"{_SUB}.is_subtitle_format", return_value=True)
    @patch(f"{_SUB}.parse_subtitle")
    def test_empty_subtitle_entries_marks_failed(  # noqa: PLR0913
        self,
        mock_parse,
        mock_is_sub,
        mock_timed,
        mock_status,
        mock_out_path,
        tmp_path,
    ):
        """Empty subtitle entries result in STATUS_FAILED with EMPTY_TEXT."""
        srt_file = tmp_path / "empty.srt"
        srt_file.write_text("", encoding="utf-8")
        mock_parse.return_value = ([], None)
        mock_out_path.return_value = tmp_path / "empty.mp3"

        tasks = [(1, str(srt_file))]
        worker = self._make_worker(tasks)
        worker.run()

        mock_status.assert_any_call(
            1,
            STATUS_FAILED,
            error_message="EMPTY_TEXT",
        )
        mock_timed.assert_not_called()
        # No successful result for this entry
        results = worker.finished_ok.emit.call_args[0][0]
        assert len(results) == 0

    @patch(f"{_MOD}.generate_voice_output_path")
    @patch(f"{_MOD}.update_voice_status")
    @patch(
        f"{_SPEECH}.synthesize_timed_speech",
        side_effect=RuntimeError("TTS crashed"),
    )
    @patch(f"{_SUB}.is_subtitle_format", return_value=True)
    @patch(f"{_SUB}.parse_subtitle")
    def test_exception_in_timed_synthesis_marks_failed(  # noqa: PLR0913
        self,
        mock_parse,
        mock_is_sub,
        mock_timed,
        mock_status,
        mock_out_path,
        tmp_path,
    ):
        """Exception during timed synthesis marks the entry as FAILED."""
        srt_file = tmp_path / "test.srt"
        srt_file.write_text("1\n00:00:01,000 --> 00:00:02,000\nHi", encoding="utf-8")
        entries = [SubtitleEntry(0, "00:00:01,000", "00:00:02,000", "Hi")]
        mock_parse.return_value = (entries, None)
        mock_out_path.return_value = tmp_path / "test.mp3"

        tasks = [(1, str(srt_file))]
        worker = self._make_worker(tasks)
        worker.run()

        mock_status.assert_any_call(
            1,
            STATUS_FAILED,
            error_message="TTS crashed",
        )
        results = worker.finished_ok.emit.call_args[0][0]
        assert len(results) == 0

    @patch(f"{_MOD}.generate_voice_output_path")
    @patch(f"{_MOD}.update_voice_status")
    @patch(f"{_SPEECH}.synthesize_speech", side_effect=RuntimeError("synth error"))
    @patch(f"{_SPEECH}.synthesize_timed_speech")
    @patch(f"{_SUB}.is_subtitle_format", return_value=False)
    @patch(f"{_SUB}.parse_subtitle")
    def test_exception_in_plain_synthesis_marks_failed(  # noqa: PLR0913
        self,
        mock_parse,
        mock_is_sub,
        mock_timed,
        mock_speech,
        mock_status,
        mock_out_path,
        tmp_path,
    ):
        """Exception during plain-text synthesis marks entry as FAILED."""
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("Hello", encoding="utf-8")
        mock_out_path.return_value = tmp_path / "test.mp3"

        tasks = [(1, str(txt_file))]
        worker = self._make_worker(tasks)
        worker.run()

        mock_status.assert_any_call(
            1,
            STATUS_FAILED,
            error_message="synth error",
        )

    @patch(f"{_MOD}.generate_voice_output_path")
    @patch(f"{_MOD}.update_voice_status")
    @patch(f"{_SPEECH}.synthesize_speech")
    @patch(f"{_SPEECH}.synthesize_timed_speech")
    @patch(f"{_SUB}.is_subtitle_format")
    @patch(f"{_SUB}.parse_subtitle")
    def test_file_read_failure_marks_failed(  # noqa: PLR0913
        self,
        mock_parse,
        mock_is_sub,
        mock_timed,
        mock_speech,
        mock_status,
        mock_out_path,
        tmp_path,
    ):
        """OSError when reading a nonexistent source file marks FAILED."""
        missing = tmp_path / "nonexistent.srt"
        mock_out_path.return_value = tmp_path / "out.mp3"

        tasks = [(1, str(missing))]
        worker = self._make_worker(tasks)
        worker.run()

        # The FileNotFoundError from read_text is caught
        failed_calls = [
            c
            for c in mock_status.call_args_list
            if len(c[0]) >= 2 and c[0][1] == STATUS_FAILED  # noqa: PLR2004
        ]
        assert len(failed_calls) == 1

    @patch(f"{_MOD}.generate_voice_output_path")
    @patch(f"{_MOD}.update_voice_status")
    @patch(f"{_SPEECH}.synthesize_speech")
    @patch(f"{_SPEECH}.synthesize_timed_speech")
    @patch(f"{_SUB}.is_subtitle_format", return_value=False)
    @patch(f"{_SUB}.parse_subtitle")
    def test_worker_processes_multiple_tasks(  # noqa: PLR0913
        self,
        mock_parse,
        mock_is_sub,
        mock_timed,
        mock_speech,
        mock_status,
        mock_out_path,
        tmp_path,
    ):
        """Worker processes all tasks sequentially, emitting progress."""
        tasks = []
        for i in range(3):  # noqa: PLR2004
            f = tmp_path / f"file{i}.txt"
            f.write_text(f"Content {i}", encoding="utf-8")
            tasks.append((i + 1, str(f)))

        mock_out_path.side_effect = [
            tmp_path / "file0.mp3",
            tmp_path / "file1.mp3",
            tmp_path / "file2.mp3",
        ]

        worker = self._make_worker(tasks)
        worker.run()

        assert mock_speech.call_count == 3  # noqa: PLR2004
        assert mock_status.call_count == 3  # noqa: PLR2004
        results = worker.finished_ok.emit.call_args[0][0]
        assert len(results) == 3  # noqa: PLR2004

    def test_is_busy_classmethod(self):
        """is_busy() reflects the class-level _is_any_worker_running flag."""
        _VoiceWorker._is_any_worker_running = False
        try:
            assert _VoiceWorker.is_busy() is False

            _VoiceWorker._is_any_worker_running = True
            assert _VoiceWorker.is_busy() is True
        finally:
            _VoiceWorker._is_any_worker_running = False

    @patch(f"{_MOD}.generate_voice_output_path")
    @patch(f"{_MOD}.update_voice_status")
    @patch(f"{_SPEECH}.synthesize_speech")
    @patch(f"{_SPEECH}.synthesize_timed_speech")
    @patch(f"{_SUB}.is_subtitle_format", return_value=False)
    @patch(f"{_SUB}.parse_subtitle")
    def test_cancellation_stops_processing(  # noqa: PLR0913
        self,
        mock_parse,
        mock_is_sub,
        mock_timed,
        mock_speech,
        mock_status,
        mock_out_path,
        tmp_path,
    ):
        """Setting _is_running = False stops processing remaining tasks."""
        f1 = tmp_path / "a.txt"
        f1.write_text("Hello", encoding="utf-8")
        f2 = tmp_path / "b.txt"
        f2.write_text("World", encoding="utf-8")
        mock_out_path.return_value = tmp_path / "out.mp3"

        tasks = [(1, str(f1)), (2, str(f2))]
        worker = self._make_worker(tasks)

        def stop_after_first(*args, **kwargs):
            worker._is_running = False

        mock_speech.side_effect = stop_after_first
        worker.run()

        # Only first task processed
        assert mock_speech.call_count == 1
        results = worker.finished_ok.emit.call_args[0][0]
        assert len(results) == 1

    @patch(f"{_MOD}.generate_voice_output_path")
    @patch(f"{_MOD}.update_voice_status")
    @patch(f"{_SPEECH}.synthesize_speech")
    @patch(f"{_SPEECH}.synthesize_timed_speech")
    @patch(f"{_SUB}.is_subtitle_format", return_value=False)
    @patch(f"{_SUB}.parse_subtitle")
    def test_busy_flag_reset_on_completion(  # noqa: PLR0913
        self,
        mock_parse,
        mock_is_sub,
        mock_timed,
        mock_speech,
        mock_status,
        mock_out_path,
        tmp_path,
    ):
        """_is_any_worker_running resets to False after run completes."""
        f = tmp_path / "test.txt"
        f.write_text("Hello", encoding="utf-8")
        mock_out_path.return_value = tmp_path / "test.mp3"

        tasks = [(1, str(f))]
        worker = self._make_worker(tasks)
        worker.run()

        assert _VoiceWorker._is_any_worker_running is False

    @patch(f"{_MOD}.update_voice_status")
    def test_busy_flag_reset_even_on_crash(self, mock_status):
        """_is_any_worker_running resets to False even if outer try crashes."""
        # Use a list with a non-tuple element to crash tuple unpacking
        # inside the for loop (which is inside the try block)
        worker = self._make_worker(["not_a_tuple"])
        worker.run()

        assert _VoiceWorker._is_any_worker_running is False
        worker.finished_ok.emit.assert_called_once()

    @patch(f"{_MOD}.generate_voice_output_path")
    @patch(f"{_MOD}.update_voice_status")
    @patch(f"{_SPEECH}.synthesize_speech")
    @patch(f"{_SPEECH}.synthesize_timed_speech")
    @patch(f"{_SUB}.is_subtitle_format", return_value=False)
    @patch(f"{_SUB}.parse_subtitle")
    def test_all_tasks_processed(  # noqa: PLR0913
        self,
        mock_parse,
        mock_is_sub,
        mock_timed,
        mock_speech,
        mock_status,
        mock_out_path,
        tmp_path,
    ):
        """Every task is processed and status-updated to Generating."""
        tasks = []
        for i in range(2):  # noqa: PLR2004
            f = tmp_path / f"f{i}.txt"
            f.write_text("content", encoding="utf-8")
            tasks.append((i + 1, str(f)))

        mock_out_path.side_effect = [
            tmp_path / "f0.mp3",
            tmp_path / "f1.mp3",
        ]

        worker = self._make_worker(tasks)
        worker.run()

        assert mock_speech.call_count == 2  # noqa: PLR2004
        # Each task was marked Generating.
        generating_calls = [
            c
            for c in mock_status.call_args_list
            if len(c.args) >= 2 and c.args[1] == "Generating"  # noqa: PLR2004
        ]
        assert len(generating_calls) == 2  # noqa: PLR2004

    @patch(f"{_MOD}.generate_voice_output_path")
    @patch(f"{_MOD}.update_voice_status")
    @patch(f"{_SPEECH}.synthesize_timed_speech")
    @patch(f"{_SUB}.is_subtitle_format", return_value=True)
    @patch(f"{_SUB}.parse_subtitle")
    def test_timed_speech_receives_correct_params(  # noqa: PLR0913
        self,
        mock_parse,
        mock_is_sub,
        mock_timed,
        mock_status,
        mock_out_path,
        tmp_path,
    ):
        """synthesize_timed_speech receives target_lang, gender, format."""
        srt_file = tmp_path / "test.srt"
        srt_file.write_text("1\n00:00:01,000 --> 00:00:02,000\nHi", encoding="utf-8")
        entries = [SubtitleEntry(0, "00:00:01,000", "00:00:02,000", "Hi")]
        mock_parse.return_value = (entries, None)
        out = tmp_path / "test.wav"
        mock_out_path.return_value = out

        tasks = [(1, str(srt_file))]
        worker = self._make_worker(
            tasks,
            target_lang="ja-JP",
            voice_gender="Male",
            tts_method="google",
            audio_format=".wav",
        )
        worker.run()

        timed_call = mock_timed.call_args
        assert timed_call[1]["target_lang"] == "ja-JP"
        assert timed_call[1]["voice_gender"] == "Male"
        assert timed_call[1]["tts_method"] == "google"
        assert timed_call[1]["audio_format"] == ".wav"

    @patch(f"{_MOD}.generate_voice_output_path")
    @patch(f"{_MOD}.update_voice_status")
    @patch(f"{_SPEECH}.synthesize_speech")
    @patch(f"{_SPEECH}.synthesize_timed_speech")
    @patch(f"{_SUB}.is_subtitle_format", return_value=False)
    @patch(f"{_SUB}.parse_subtitle")
    def test_status_set_to_generating_before_synthesis(  # noqa: PLR0913
        self,
        mock_parse,
        mock_is_sub,
        mock_timed,
        mock_speech,
        mock_status,
        mock_out_path,
        tmp_path,
    ):
        """Each task is set to STATUS_GENERATING before synthesis begins."""
        f = tmp_path / "test.txt"
        f.write_text("Hello", encoding="utf-8")
        mock_out_path.return_value = tmp_path / "test.mp3"

        entry_id = 42  # noqa: PLR2004
        tasks = [(entry_id, str(f))]
        worker = self._make_worker(tasks)
        worker.run()

        # First call to update_voice_status should be GENERATING
        first_status_call = mock_status.call_args_list[0]
        assert first_status_call == call(entry_id, STATUS_GENERATING)


# ---------------------------------------------------------------------------
# Additional _VoiceWorker edge-case tests
# ---------------------------------------------------------------------------


class TestVoiceWorkerEdgeCases:
    """Extended edge-case tests for _VoiceWorker.run()."""

    def _make_worker(self, tasks, **kwargs):
        """Creates a _VoiceWorker with mocked signals (no QThread init)."""
        worker = _VoiceWorker.__new__(_VoiceWorker)
        worker._tasks = tasks
        worker._target_lang = kwargs.get("target_lang", "en-US")
        worker._voice_gender = kwargs.get("voice_gender", "Female")
        worker._tts_method = kwargs.get("tts_method", "edge")
        worker._audio_format = kwargs.get("audio_format", ".mp3")
        worker._is_running = True
        worker.finished_ok = MagicMock()
        _VoiceWorker._is_any_worker_running = False
        return worker

    @patch(f"{_MOD}.update_voice_status")
    def test_empty_task_list(self, mock_status):
        """Worker with empty task list emits finished immediately."""
        worker = self._make_worker([])
        worker.run()

        mock_status.assert_not_called()
        results = worker.finished_ok.emit.call_args[0][0]
        assert results == []

    @patch(f"{_MOD}.generate_voice_output_path")
    @patch(f"{_MOD}.update_voice_status")
    @patch(f"{_SPEECH}.synthesize_speech")
    @patch(f"{_SPEECH}.synthesize_timed_speech")
    @patch(f"{_SUB}.is_subtitle_format", return_value=False)
    @patch(f"{_SUB}.parse_subtitle")
    def test_large_batch_processing(  # noqa: PLR0913
        self,
        mock_parse,
        mock_is_sub,
        mock_timed,
        mock_speech,
        mock_status,
        mock_out_path,
        tmp_path,
    ):
        """Worker handles a large number of tasks (20) without issue."""
        count = 20
        tasks = []
        out_paths = []
        for i in range(count):
            f = tmp_path / f"file_{i}.txt"
            f.write_text(f"Content {i}", encoding="utf-8")
            tasks.append((i + 1, str(f)))
            out_paths.append(tmp_path / f"file_{i}.mp3")

        mock_out_path.side_effect = out_paths

        worker = self._make_worker(tasks)
        worker.run()

        assert mock_speech.call_count == count
        results = worker.finished_ok.emit.call_args[0][0]
        assert len(results) == count

    @patch(f"{_MOD}.generate_voice_output_path")
    @patch(f"{_MOD}.update_voice_status")
    @patch(f"{_SPEECH}.synthesize_speech")
    @patch(f"{_SPEECH}.synthesize_timed_speech")
    @patch(f"{_SUB}.is_subtitle_format", return_value=False)
    @patch(f"{_SUB}.parse_subtitle")
    def test_unicode_file_paths(  # noqa: PLR0913
        self,
        mock_parse,
        mock_is_sub,
        mock_timed,
        mock_speech,
        mock_status,
        mock_out_path,
        tmp_path,
    ):
        """Worker handles files with unicode characters in their paths."""
        uni_file = tmp_path / "tieng_viet.txt"
        uni_file.write_text("Xin chao the gioi", encoding="utf-8")
        out = tmp_path / "tieng_viet.mp3"
        mock_out_path.return_value = out

        tasks = [(1, str(uni_file))]
        worker = self._make_worker(tasks)
        worker.run()

        mock_speech.assert_called_once()
        results = worker.finished_ok.emit.call_args[0][0]
        assert len(results) == 1

    @patch(f"{_MOD}.generate_voice_output_path")
    @patch(f"{_MOD}.update_voice_status")
    @patch(f"{_SPEECH}.synthesize_speech")
    @patch(f"{_SPEECH}.synthesize_timed_speech")
    @patch(f"{_SUB}.is_subtitle_format", return_value=False)
    @patch(f"{_SUB}.parse_subtitle")
    def test_special_characters_in_text(  # noqa: PLR0913
        self,
        mock_parse,
        mock_is_sub,
        mock_timed,
        mock_speech,
        mock_status,
        mock_out_path,
        tmp_path,
    ):
        """Worker handles files with special characters in content."""
        txt_file = tmp_path / "special.txt"
        txt_file.write_text("<tag>\"Hello\" & 'World'</tag>", encoding="utf-8")
        mock_out_path.return_value = tmp_path / "special.mp3"

        tasks = [(1, str(txt_file))]
        worker = self._make_worker(tasks)
        worker.run()

        mock_speech.assert_called_once()
        # Verify the content was passed through correctly
        speech_call = mock_speech.call_args
        assert "<tag>\"Hello\" & 'World'</tag>" in speech_call[0][0]

    @patch(f"{_MOD}.generate_voice_output_path")
    @patch(f"{_MOD}.update_voice_status")
    @patch(f"{_SPEECH}.synthesize_timed_speech")
    @patch(f"{_SUB}.is_subtitle_format", return_value=True)
    @patch(f"{_SUB}.parse_subtitle")
    def test_timed_speech_wav_format(  # noqa: PLR0913
        self,
        mock_parse,
        mock_is_sub,
        mock_timed,
        mock_status,
        mock_out_path,
        tmp_path,
    ):
        """Timed speech correctly passes .wav audio format."""
        srt_file = tmp_path / "test.srt"
        srt_file.write_text(
            "1\n00:00:01,000 --> 00:00:02,000\nHi",
            encoding="utf-8",
        )
        entries = [SubtitleEntry(0, "00:00:01,000", "00:00:02,000", "Hi")]
        mock_parse.return_value = (entries, None)
        mock_out_path.return_value = tmp_path / "test.wav"

        tasks = [(1, str(srt_file))]
        worker = self._make_worker(tasks, audio_format=".wav")
        worker.run()

        timed_call = mock_timed.call_args
        assert timed_call[1]["audio_format"] == ".wav"

    @patch(f"{_MOD}.generate_voice_output_path")
    @patch(f"{_MOD}.update_voice_status")
    @patch(f"{_SPEECH}.synthesize_timed_speech")
    @patch(f"{_SUB}.is_subtitle_format", return_value=True)
    @patch(f"{_SUB}.parse_subtitle")
    def test_timed_speech_ogg_format(  # noqa: PLR0913
        self,
        mock_parse,
        mock_is_sub,
        mock_timed,
        mock_status,
        mock_out_path,
        tmp_path,
    ):
        """OGG goes through a WAV intermediate that ffmpeg post-encodes.

        TTS backends don't speak FLAC / OGG natively, so when the user
        picks one of those, the worker tells the engine to produce
        ``.wav`` and then post-encodes via ``post_encode_audio``.  This
        test pins the contract that the *engine* sees ``.wav`` (not
        ``.ogg``) when the user-facing format is OGG.
        """
        srt_file = tmp_path / "test.srt"
        srt_file.write_text(
            "1\n00:00:01,000 --> 00:00:02,000\nHi",
            encoding="utf-8",
        )
        entries = [SubtitleEntry(0, "00:00:01,000", "00:00:02,000", "Hi")]
        mock_parse.return_value = (entries, None)
        mock_out_path.return_value = tmp_path / "test.ogg"

        tasks = [(1, str(srt_file))]
        worker = self._make_worker(tasks, audio_format=".ogg")
        with patch(
            "src.utils.audio_encoding.post_encode_audio",
            side_effect=lambda src, fmt, output_path=None: output_path or src,
        ):
            worker.run()

        timed_call = mock_timed.call_args
        # Engine receives WAV (intermediate); user-facing extension stays .ogg.
        assert timed_call[1]["audio_format"] == ".wav"
        assert timed_call[1]["output_path"].endswith(".intermediate.wav")

    @patch(f"{_MOD}.generate_voice_output_path")
    @patch(f"{_MOD}.update_voice_status")
    @patch(f"{_SPEECH}.synthesize_timed_speech")
    @patch(f"{_SUB}.is_subtitle_format", return_value=True)
    @patch(f"{_SUB}.parse_subtitle")
    def test_post_encode_failure_marks_task_failed(  # noqa: PLR0913
        self,
        mock_parse,
        mock_is_sub,
        mock_timed,
        mock_status,
        mock_out_path,
        tmp_path,
    ):
        """``post_encode_audio`` raising → task marked FAILED, error recorded.

        Pins the contract that the worker doesn't silently swallow a
        post-encode failure — the user sees a FAILED status with the
        sentinel as the error message, not a phantom 'success' with
        the WAV intermediate sitting in the output folder.

        Voice's ``_check_requirements`` pre-check normally prevents
        this path (blocks the worker before queue when ffmpeg is
        missing), but defence in depth — ffmpeg can disappear
        mid-batch if the user uninstalls between Generate clicks.
        """
        from src.constants.history import STATUS_FAILED  # noqa: PLC0415

        srt_file = tmp_path / "test.srt"
        srt_file.write_text(
            "1\n00:00:01,000 --> 00:00:02,000\nHi",
            encoding="utf-8",
        )
        entries = [SubtitleEntry(0, "00:00:01,000", "00:00:02,000", "Hi")]
        mock_parse.return_value = (entries, None)
        mock_out_path.return_value = tmp_path / "test.flac"

        tasks = [(1, str(srt_file))]
        worker = self._make_worker(tasks, audio_format=".flac")
        with patch(
            "src.utils.audio_encoding.post_encode_audio",
            side_effect=RuntimeError("FFMPEG_NOT_FOUND"),
        ):
            worker.run()

        # Last status update for this entry: FAILED with the sentinel
        # passed through as ``error_message``.
        failed_calls = [
            c
            for c in mock_status.call_args_list
            if c.args[0] == 1 and c.args[1] == STATUS_FAILED
        ]
        assert failed_calls, "Task 1 should have been marked FAILED"
        # Error message includes the sentinel.
        call = failed_calls[0]
        err = call.kwargs.get("error_message") or (
            call.args[2] if len(call.args) > 2 else ""
        )
        assert "FFMPEG_NOT_FOUND" in str(err)

    @patch(f"{_MOD}.generate_voice_output_path")
    @patch(f"{_MOD}.update_voice_status")
    @patch(f"{_SPEECH}.synthesize_speech")
    @patch(f"{_SPEECH}.synthesize_timed_speech")
    @patch(f"{_SUB}.is_subtitle_format", return_value=False)
    @patch(f"{_SUB}.parse_subtitle")
    def test_synthesize_speech_parameter_passing(  # noqa: PLR0913
        self,
        mock_parse,
        mock_is_sub,
        mock_timed,
        mock_speech,
        mock_status,
        mock_out_path,
        tmp_path,
    ):
        """synthesize_speech receives target_lang, gender, tts_method, format.

        Uses MP3 (a native engine format) so the format passed to the
        engine equals the user-facing format — keeps this test focused
        on parameter wiring rather than the FLAC/OGG post-encode dance
        which has its own dedicated test.
        """
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("Hello", encoding="utf-8")
        out = tmp_path / "test.mp3"
        mock_out_path.return_value = out

        tasks = [(1, str(txt_file))]
        worker = self._make_worker(
            tasks,
            target_lang="fr-FR",
            voice_gender="Male",
            tts_method="google",
            audio_format=".mp3",
        )
        worker.run()

        speech_call = mock_speech.call_args
        assert speech_call[1]["target_lang"] == "fr-FR"
        assert speech_call[1]["voice_gender"] == "Male"
        assert speech_call[1]["tts_method"] == "google"
        assert speech_call[1]["audio_format"] == ".mp3"

    @patch(f"{_MOD}.generate_voice_output_path")
    @patch(f"{_MOD}.update_voice_status")
    @patch(f"{_SPEECH}.synthesize_speech")
    @patch(f"{_SPEECH}.synthesize_timed_speech")
    @patch(f"{_SUB}.is_subtitle_format", return_value=False)
    @patch(f"{_SUB}.parse_subtitle")
    def test_worker_continues_after_one_failure(  # noqa: PLR0913
        self,
        mock_parse,
        mock_is_sub,
        mock_timed,
        mock_speech,
        mock_status,
        mock_out_path,
        tmp_path,
    ):
        """Worker processes remaining tasks after one task fails."""
        f1 = tmp_path / "fail.txt"
        f1.write_text("fail", encoding="utf-8")
        f2 = tmp_path / "ok.txt"
        f2.write_text("ok", encoding="utf-8")

        mock_out_path.side_effect = [
            tmp_path / "fail.mp3",
            tmp_path / "ok.mp3",
        ]

        # First call raises, second succeeds
        mock_speech.side_effect = [RuntimeError("boom"), None]

        tasks = [(1, str(f1)), (2, str(f2))]
        worker = self._make_worker(tasks)
        worker.run()

        # Both tasks were attempted
        assert mock_speech.call_count == 2  # noqa: PLR2004
        # Only the second succeeded
        results = worker.finished_ok.emit.call_args[0][0]
        assert len(results) == 1
        assert results[0][0] == 2  # noqa: PLR2004

    def test_stop_sets_is_running_false(self):
        """Calling stop() sets _is_running to False."""
        worker = self._make_worker([(1, "/tmp/x.txt")])
        assert worker._is_running is True
        worker.stop()
        assert worker._is_running is False

    def test_run_skips_when_already_busy(self):
        """run() returns immediately if another worker is already running."""
        _VoiceWorker._is_any_worker_running = True
        try:
            worker = self._make_worker([(1, "/tmp/x.txt")])
            # Override: set _is_any_worker_running manually before run
            _VoiceWorker._is_any_worker_running = True
            worker.run()
            # finished_ok should NOT be emitted since the worker bailed out
            worker.finished_ok.emit.assert_not_called()
        finally:
            _VoiceWorker._is_any_worker_running = False

    @patch(f"{_MOD}.generate_voice_output_path")
    @patch(f"{_MOD}.update_voice_status")
    @patch(f"{_SPEECH}.synthesize_speech")
    @patch(f"{_SPEECH}.synthesize_timed_speech")
    @patch(f"{_SUB}.is_subtitle_format", return_value=False)
    @patch(f"{_SUB}.parse_subtitle")
    def test_output_path_in_results(  # noqa: PLR0913
        self,
        mock_parse,
        mock_is_sub,
        mock_timed,
        mock_speech,
        mock_status,
        mock_out_path,
        tmp_path,
    ):
        """Result tuples contain (entry_id, source_path, output_path)."""
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("Hello", encoding="utf-8")
        out = tmp_path / "test.mp3"
        mock_out_path.return_value = out

        tasks = [(42, str(txt_file))]
        worker = self._make_worker(tasks)
        worker.run()

        results = worker.finished_ok.emit.call_args[0][0]
        entry_id, source_path, output_path = results[0]
        assert entry_id == 42  # noqa: PLR2004
        assert source_path == str(txt_file)
        assert output_path == str(out)

    @patch(f"{_MOD}.generate_voice_output_path")
    @patch(f"{_MOD}.update_voice_status")
    @patch(f"{_SPEECH}.synthesize_timed_speech")
    @patch(f"{_SUB}.is_subtitle_format", return_value=True)
    @patch(f"{_SUB}.parse_subtitle")
    def test_is_cancelled_lambda_passed_to_timed_speech(  # noqa: PLR0913
        self,
        mock_parse,
        mock_is_sub,
        mock_timed,
        mock_status,
        mock_out_path,
        tmp_path,
    ):
        """synthesize_timed_speech receives an is_cancelled callable."""
        srt_file = tmp_path / "test.srt"
        srt_file.write_text(
            "1\n00:00:01,000 --> 00:00:02,000\nHi",
            encoding="utf-8",
        )
        entries = [SubtitleEntry(0, "00:00:01,000", "00:00:02,000", "Hi")]
        mock_parse.return_value = (entries, None)
        mock_out_path.return_value = tmp_path / "test.mp3"

        tasks = [(1, str(srt_file))]
        worker = self._make_worker(tasks)
        worker.run()

        timed_call = mock_timed.call_args
        is_cancelled = timed_call[1]["is_cancelled"]
        # Worker is running, so is_cancelled should return False
        assert callable(is_cancelled)

    @patch(f"{_MOD}.generate_voice_output_path")
    @patch(f"{_MOD}.update_voice_status")
    @patch(f"{_SPEECH}.synthesize_speech")
    @patch(f"{_SPEECH}.synthesize_timed_speech")
    @patch(f"{_SUB}.is_subtitle_format", return_value=False)
    @patch(f"{_SUB}.parse_subtitle")
    def test_is_cancelled_lambda_passed_to_plain_speech(  # noqa: PLR0913
        self,
        mock_parse,
        mock_is_sub,
        mock_timed,
        mock_speech,
        mock_status,
        mock_out_path,
        tmp_path,
    ):
        """synthesize_speech receives an is_cancelled callable."""
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("Hello", encoding="utf-8")
        mock_out_path.return_value = tmp_path / "test.mp3"

        tasks = [(1, str(txt_file))]
        worker = self._make_worker(tasks)
        worker.run()

        speech_call = mock_speech.call_args
        is_cancelled = speech_call[1]["is_cancelled"]
        assert callable(is_cancelled)

    @patch(f"{_MOD}.generate_voice_output_path")
    @patch(f"{_MOD}.update_voice_status")
    @patch(f"{_SPEECH}.synthesize_speech")
    @patch(f"{_SPEECH}.synthesize_timed_speech")
    @patch(f"{_SUB}.is_subtitle_format", return_value=True)
    @patch(f"{_SUB}.parse_subtitle")
    def test_mixed_subtitle_and_plain_tasks(  # noqa: PLR0913
        self,
        mock_parse,
        mock_is_sub,
        mock_timed,
        mock_speech,
        mock_status,
        mock_out_path,
        tmp_path,
    ):
        """Worker routes subtitle vs plain-text tasks correctly in same batch."""
        srt_file = tmp_path / "test.srt"
        srt_file.write_text(
            "1\n00:00:01,000 --> 00:00:02,000\nHi",
            encoding="utf-8",
        )
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("Hello", encoding="utf-8")

        entries = [SubtitleEntry(0, "00:00:01,000", "00:00:02,000", "Hi")]
        mock_parse.return_value = (entries, None)

        # is_subtitle_format returns True for both since we mock at module level,
        # but we can control it per call
        mock_is_sub.side_effect = [True, False]
        mock_out_path.side_effect = [
            tmp_path / "test.mp3",
            tmp_path / "test2.mp3",
        ]

        tasks = [(1, str(srt_file)), (2, str(txt_file))]
        worker = self._make_worker(tasks)
        worker.run()

        mock_timed.assert_called_once()
        mock_speech.assert_called_once()

    @patch(f"{_MOD}.generate_voice_output_path")
    @patch(f"{_MOD}.update_voice_status")
    @patch(f"{_SPEECH}.synthesize_speech")
    @patch(f"{_SPEECH}.synthesize_timed_speech")
    @patch(f"{_SUB}.is_subtitle_format", return_value=False)
    @patch(f"{_SUB}.parse_subtitle")
    def test_default_audio_format_is_mp3(  # noqa: PLR0913
        self,
        mock_parse,
        mock_is_sub,
        mock_timed,
        mock_speech,
        mock_status,
        mock_out_path,
        tmp_path,
    ):
        """Worker defaults to .mp3 audio format."""
        worker = self._make_worker([])
        assert worker._audio_format == ".mp3"


# ---------------------------------------------------------------------------
# pytest-qt fixtures for VoicePage UI tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def window(qapp):
    """Provides a QMainWindow context."""
    return QMainWindow()


@pytest.fixture()
def _mock_voice_deps():
    """Mocks all external dependencies for VoicePage construction."""
    with (
        patch(
            "src.core.database.reset_stuck_voice_entries",
        ),
        patch(
            f"{_HIST_MOD}.get_voice_fingerprint",
            return_value=None,
        ),
        patch(
            f"{_HIST_MOD}.get_voice_history",
            return_value=[],
        ),
    ):
        yield


@pytest.fixture()
def voice_page(window, _mock_voice_deps, qtbot):
    """Creates a VoicePage widget for testing."""
    from src.ui.pages.voice import VoicePage  # noqa: PLC0415

    p = VoicePage(window)
    qtbot.addWidget(p)
    return p


# ---------------------------------------------------------------------------
# TestVoicePageCreation (pytest-qt)
# ---------------------------------------------------------------------------


class TestVoicePageCreation:
    """Tests for create_voice_page() and VoicePage widget structure."""

    def test_create_voice_page_returns_qwidget(self, window, _mock_voice_deps):
        """create_voice_page() returns a QWidget."""
        from src.ui.pages.voice import create_voice_page  # noqa: PLC0415

        page = create_voice_page(window)
        assert isinstance(page, QWidget)

    def test_has_generate_button(self, voice_page):
        """Page has a generate button."""
        assert hasattr(voice_page, "generate_btn")
        assert isinstance(voice_page.generate_btn, QPushButton)

    def test_has_clear_all_button(self, voice_page):
        """Page has a clear all / delete all button."""
        assert hasattr(voice_page, "clear_all_btn")
        assert isinstance(voice_page.clear_all_btn, QPushButton)

    def test_has_file_drop_area(self, voice_page):
        """Page has a FileDropWidget drop area."""
        from src.ui.components import FileDropWidget  # noqa: PLC0415

        assert hasattr(voice_page, "drop_area")
        assert isinstance(voice_page.drop_area, FileDropWidget)

    def test_has_stacked_widget(self, voice_page):
        """Page uses a QStackedWidget for view switching."""
        assert hasattr(voice_page, "stack")
        assert isinstance(voice_page.stack, QStackedWidget)

    def test_has_history_view(self, voice_page):
        """Page has an embedded VoiceHistoryPage."""
        from src.ui.pages.voice_history import VoiceHistoryPage  # noqa: PLC0415

        assert hasattr(voice_page, "history_view")
        assert isinstance(voice_page.history_view, VoiceHistoryPage)

    def test_has_files_badge(self, voice_page):
        """Page has a file count badge label."""
        assert hasattr(voice_page, "files_badge")
        assert isinstance(voice_page.files_badge, QLabel)

    def test_has_section_label(self, voice_page):
        """Page has a section label for files selected."""
        assert hasattr(voice_page, "section_label")
        assert isinstance(voice_page.section_label, QLabel)

    def test_has_files_vbox_layout(self, voice_page):
        """Page has a vertical layout for file item widgets."""
        assert hasattr(voice_page, "files_vbox")

    def test_history_view_has_search_input(self, voice_page):
        """Embedded history view has a search input."""
        assert hasattr(voice_page.history_view, "search_input")

    def test_history_view_has_table(self, voice_page):
        """Embedded history view has a history table."""
        assert hasattr(voice_page.history_view, "table")

    def test_history_view_has_open_button(self, voice_page):
        """Embedded history view has an open button."""
        assert hasattr(voice_page.history_view, "open_btn")
        assert isinstance(voice_page.history_view.open_btn, QPushButton)

    def test_history_view_has_delete_button(self, voice_page):
        """Embedded history view has a delete button."""
        assert hasattr(voice_page.history_view, "delete_btn")
        assert isinstance(voice_page.history_view.delete_btn, QPushButton)

    def test_history_view_has_re_generate_button(self, voice_page):
        """Embedded history view has a re-generate button."""
        assert hasattr(voice_page.history_view, "re_generate_btn")
        assert isinstance(voice_page.history_view.re_generate_btn, QPushButton)


# ---------------------------------------------------------------------------
# TestVoicePageInitialState (pytest-qt)
# ---------------------------------------------------------------------------


class TestVoicePageInitialState:
    """Tests for VoicePage initial state after construction."""

    def test_no_worker_initially(self, voice_page):
        """No worker thread is active on construction."""
        assert voice_page._worker is None

    def test_selected_files_empty(self, voice_page):
        """Selected files list starts empty."""
        assert voice_page.selected_files == []

    def test_stack_shows_history_view(self, voice_page):
        """Stacked widget starts on the history view (index 0)."""
        assert voice_page.stack.currentIndex() == 0

    def test_generate_button_disabled_initially(self, voice_page):
        """Generate button is disabled when no files are selected."""
        assert not voice_page.generate_btn.isEnabled()

    def test_files_badge_shows_zero(self, voice_page):
        """File count badge shows 0 initially."""
        assert voice_page.files_badge.text() == "0"

    def test_pending_tasks_empty(self, voice_page):
        """Pending tasks list starts empty."""
        assert voice_page._pending_tasks == []


# ---------------------------------------------------------------------------
# TestVoicePageActions (pytest-qt)
# ---------------------------------------------------------------------------


class TestVoicePageActions:
    """Tests for VoicePage user actions."""

    def test_handle_generate_returns_when_no_files(self, voice_page):
        """_handle_generate returns immediately if no files are selected."""
        voice_page.selected_files = []
        # Should not crash or spawn a worker
        voice_page._handle_generate()
        assert voice_page._worker is None

    def test_handle_generate_returns_when_worker_running(self, voice_page):
        """_handle_generate returns if a worker is already running."""
        voice_page.selected_files = ["/tmp/test.srt"]
        voice_page._worker = MagicMock()
        voice_page._handle_generate()
        # Worker should remain unchanged (not replaced)
        assert voice_page._worker is not None

    @patch(f"{_MOD}.VoiceSetupDialog")
    @patch(f"{_MOD}.load_setting", return_value="Edge TTS")
    @patch(f"{_MOD}.add_voice_entry", return_value=1)
    def test_handle_generate_with_files_requires_dialog(
        self,
        mock_add,
        mock_load,
        mock_dialog,
        voice_page,
    ):
        """_handle_generate shows voice setup dialog when files present."""
        voice_page.selected_files = ["/tmp/test.srt"]
        # Dialog not accepted
        mock_dialog.get_selection.return_value = ("English", "Female", None, False)

        with patch.object(voice_page, "_check_requirements", return_value=True):
            voice_page._handle_generate()

        mock_dialog.get_selection.assert_called_once()
        # Worker should not start since dialog was not accepted
        assert voice_page._worker is None

    @patch(f"{_HIST_MOD}.get_voice_fingerprint", return_value=None)
    @patch(f"{_HIST_MOD}.get_voice_history", return_value=[])
    @patch(f"{_MOD}.VoiceSetupDialog")
    @patch(f"{_MOD}.load_setting", return_value="Edge TTS")
    @patch(f"{_MOD}.add_voice_entry", return_value=1)
    def test_handle_generate_creates_db_entries(  # noqa: PLR0913
        self,
        mock_add,
        mock_load,
        mock_dialog,
        mock_hist,
        mock_fp,
        voice_page,
        tmp_path,
    ):
        """_handle_generate creates DB entries for each selected file."""
        f = tmp_path / "test.srt"
        f.write_text("content", encoding="utf-8")
        voice_page.selected_files = [str(f)]
        mock_dialog.get_selection.return_value = ("English", "Female", None, True)

        with (
            patch.object(voice_page, "_check_requirements", return_value=True),
            patch.object(voice_page, "_start_worker"),
        ):
            voice_page._handle_generate()

        mock_add.assert_called_once()

    def test_handle_clear_all(self, voice_page, tmp_path):
        """_handle_clear_all removes all files and resets view."""
        f = tmp_path / "test.srt"
        f.write_text("content", encoding="utf-8")
        voice_page.selected_files = [str(f)]
        voice_page._add_file_widget(str(f))
        voice_page._update_ui_state()

        voice_page._handle_clear_all()

        assert voice_page.selected_files == []
        assert voice_page.stack.currentIndex() == 0

    def test_start_worker_skips_when_worker_exists(self, voice_page):
        """_start_worker returns if a worker is already set."""
        voice_page._worker = MagicMock()
        voice_page._start_worker([(1, "/tmp/x.srt")], "en", "Female", "edge", ".mp3")
        # Should not replace the existing worker

    def test_safe_cleanup_worker_clears_reference(self, voice_page):
        """_safe_cleanup_worker waits and clears the worker reference."""
        mock_worker = MagicMock()
        voice_page._worker = mock_worker
        voice_page._safe_cleanup_worker()

        mock_worker.wait.assert_called_once()
        assert voice_page._worker is None

    def test_safe_cleanup_worker_noop_when_none(self, voice_page):
        """_safe_cleanup_worker does nothing when worker is None."""
        voice_page._worker = None
        voice_page._safe_cleanup_worker()  # Should not crash


# ---------------------------------------------------------------------------
# TestVoicePageOnFinished (pytest-qt)
# ---------------------------------------------------------------------------


class TestVoicePageOnFinished:
    """Tests for _on_finished callback."""

    @patch(f"{_HIST_MOD}.get_voice_fingerprint", return_value=None)
    @patch(f"{_HIST_MOD}.get_voice_history", return_value=[])
    @patch(f"{_MOD}.update_voice_status")
    @patch(f"{_MOD}.load_setting", return_value=False)
    def test_on_finished_marks_done(
        self,
        mock_load,
        mock_status,
        mock_hist,
        mock_fp,
        voice_page,
    ):
        """_on_finished marks results as STATUS_DONE when auto_remove=False."""
        voice_page._worker = MagicMock()
        results = [(1, "/tmp/src.srt", "/tmp/out.mp3")]
        voice_page._on_finished(results)

        mock_status.assert_called_once_with(
            1,
            STATUS_DONE,
            output_path="/tmp/out.mp3",
        )
        assert voice_page._worker is None

    @patch(f"{_HIST_MOD}.get_voice_fingerprint", return_value=None)
    @patch(f"{_HIST_MOD}.get_voice_history", return_value=[])
    @patch(f"{_MOD}.delete_voice_entry")
    @patch(f"{_MOD}.load_setting", return_value=True)
    def test_on_finished_auto_remove_deletes(
        self,
        mock_load,
        mock_delete,
        mock_hist,
        mock_fp,
        voice_page,
    ):
        """_on_finished deletes entries when auto_remove is enabled."""
        voice_page._worker = MagicMock()
        results = [(1, "/tmp/src.srt", "/tmp/out.mp3")]
        voice_page._on_finished(results)

        mock_delete.assert_called_once_with(1)

    @patch(f"{_HIST_MOD}.get_voice_fingerprint", return_value=None)
    @patch(f"{_HIST_MOD}.get_voice_history", return_value=[])
    @patch(f"{_MOD}.load_setting", return_value=False)
    def test_on_finished_empty_results(
        self,
        mock_load,
        mock_hist,
        mock_fp,
        voice_page,
    ):
        """_on_finished handles empty results gracefully."""
        voice_page._worker = MagicMock()
        voice_page._on_finished([])
        assert voice_page._worker is None


# ---------------------------------------------------------------------------
# TestVoicePageFileHandling (pytest-qt)
# ---------------------------------------------------------------------------


class TestVoicePageFileHandling:
    """Tests for file drop/add/remove in VoicePage."""

    def test_add_file_widget_adds_to_layout(self, voice_page, tmp_path):
        """_add_file_widget adds a FileItemWidget to files_vbox."""
        f = tmp_path / "test.srt"
        f.write_text("content", encoding="utf-8")
        initial_count = voice_page.files_vbox.count()
        voice_page._add_file_widget(str(f))
        assert voice_page.files_vbox.count() == initial_count + 1

    def test_handle_remove_file(self, voice_page, tmp_path):
        """_handle_remove_file removes a file from the selection."""
        f = tmp_path / "test.srt"
        f.write_text("content", encoding="utf-8")
        voice_page.selected_files.append(str(f))
        voice_page._add_file_widget(str(f))
        voice_page._update_ui_state()

        # Get the widget that was added
        widget = voice_page.files_vbox.itemAt(0).widget()
        voice_page._handle_remove_file(str(f), widget)

        assert str(f) not in voice_page.selected_files

    def test_handle_files_dropped_supported_formats(self, voice_page, tmp_path):
        """_handle_files_dropped accepts supported voice input formats."""
        srt_file = tmp_path / "test.srt"
        srt_file.write_text("content", encoding="utf-8")

        voice_page._handle_files_dropped([str(srt_file)])

        assert str(srt_file) in voice_page.selected_files

    @patch(f"{_MOD}.CustomMessageDialog")
    def test_handle_files_dropped_unsupported(
        self,
        mock_dialog,
        voice_page,
        tmp_path,
    ):
        """_handle_files_dropped shows dialog for unsupported formats."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_text("content", encoding="utf-8")

        voice_page._handle_files_dropped([str(pdf_file)])

        mock_dialog.show_message.assert_called_once()
        assert str(pdf_file) not in voice_page.selected_files

    @patch(f"{_MOD}.CustomMessageDialog.show_message")
    def test_handle_files_dropped_skips_empty_files(
        self, mock_msg, voice_page, tmp_path
    ):
        """_handle_files_dropped skips files with zero size."""
        empty_file = tmp_path / "empty.srt"
        empty_file.write_text("", encoding="utf-8")

        voice_page._handle_files_dropped([str(empty_file)])

        assert str(empty_file) not in voice_page.selected_files

    def test_handle_files_dropped_no_duplicates(self, voice_page, tmp_path):
        """_handle_files_dropped does not add the same file twice."""
        srt_file = tmp_path / "test.srt"
        srt_file.write_text("content", encoding="utf-8")

        voice_page._handle_files_dropped([str(srt_file)])
        voice_page._handle_files_dropped([str(srt_file)])

        assert voice_page.selected_files.count(str(srt_file)) == 1

    def test_handle_files_dropped_empty_list_triggers_browse(
        self,
        voice_page,
    ):
        """_handle_files_dropped with empty list opens file dialog."""
        with patch(f"{_MOD}.QFileDialog") as mock_fd:
            mock_fd.getOpenFileNames.return_value = ([], "")
            voice_page._handle_files_dropped([])
            mock_fd.getOpenFileNames.assert_called_once()

    def test_handle_files_dropped_directory(self, voice_page, tmp_path):
        """_handle_files_dropped traverses directories for supported files."""
        subdir = tmp_path / "subtitles"
        subdir.mkdir()
        srt_file = subdir / "test.srt"
        srt_file.write_text("content", encoding="utf-8")

        voice_page._handle_files_dropped([str(subdir)])

        assert any("test.srt" in f for f in voice_page.selected_files)

    def test_handle_files_dropped_max_100_files(self, voice_page, tmp_path):
        """_handle_files_dropped limits to 100 files maximum."""
        for i in range(150):
            f = tmp_path / f"test_{i}.srt"
            f.write_text(f"content {i}", encoding="utf-8")

        all_files = [str(tmp_path / f"test_{i}.srt") for i in range(150)]
        voice_page._handle_files_dropped(all_files)

        assert len(voice_page.selected_files) <= 100  # noqa: PLR2004


# ---------------------------------------------------------------------------
# TestVoicePageUIState (pytest-qt)
# ---------------------------------------------------------------------------


class TestVoicePageUIState:
    """Tests for VoicePage view switching and UI state."""

    def test_update_ui_state_no_files_shows_history(self, voice_page):
        """With no files, stack shows history view."""
        voice_page.selected_files = []
        voice_page._update_ui_state()
        assert voice_page.stack.currentIndex() == 0

    def test_update_ui_state_with_files_shows_file_list(
        self,
        voice_page,
        tmp_path,
    ):
        """With files, stack switches to file list view."""
        f = tmp_path / "test.srt"
        f.write_text("content", encoding="utf-8")
        voice_page.selected_files = [str(f)]
        voice_page._update_ui_state()
        assert voice_page.stack.currentIndex() == 1

    def test_update_ui_state_badge_reflects_count(self, voice_page, tmp_path):
        """Badge text matches file count."""
        f1 = tmp_path / "a.srt"
        f1.write_text("a", encoding="utf-8")
        f2 = tmp_path / "b.srt"
        f2.write_text("b", encoding="utf-8")
        voice_page.selected_files = [str(f1), str(f2)]
        voice_page._update_ui_state()
        assert voice_page.files_badge.text() == "2"

    def test_update_ui_state_generate_enabled_with_files(
        self,
        voice_page,
        tmp_path,
    ):
        """Generate button is enabled when files are selected."""
        f = tmp_path / "test.srt"
        f.write_text("content", encoding="utf-8")
        voice_page.selected_files = [str(f)]
        voice_page._update_ui_state()
        assert voice_page.generate_btn.isEnabled()

    def test_update_ui_state_generate_disabled_without_files(self, voice_page):
        """Generate button is disabled when no files are selected."""
        voice_page.selected_files = []
        voice_page._update_ui_state()
        assert not voice_page.generate_btn.isEnabled()


# ---------------------------------------------------------------------------
# TestVoicePageThemeLanguage (pytest-qt)
# ---------------------------------------------------------------------------


class TestVoicePageThemeLanguage:
    """Tests for apply_theme() and apply_language() on VoicePage."""

    def test_apply_theme_updates_generate_btn(self, voice_page):
        """apply_theme updates the generate button style."""
        voice_page.apply_theme()
        # Style should be set (may or may not differ depending on theme)
        assert voice_page.generate_btn.styleSheet()

    def test_apply_theme_updates_clear_btn(self, voice_page):
        """apply_theme updates the clear all button style."""
        voice_page.apply_theme()
        assert voice_page.clear_all_btn.styleSheet()

    def test_apply_theme_updates_badge(self, voice_page):
        """apply_theme updates the file count badge style."""
        voice_page.apply_theme()
        assert voice_page.files_badge.styleSheet()

    def test_apply_theme_updates_section_label(self, voice_page):
        """apply_theme updates the section label style."""
        voice_page.apply_theme()
        assert voice_page.section_label.styleSheet()

    def test_apply_language_updates_generate_btn_text(self, voice_page):
        """apply_language updates the generate button text."""
        voice_page.apply_language()
        assert voice_page.generate_btn.text()  # Non-empty

    def test_apply_language_updates_clear_btn_text(self, voice_page):
        """apply_language updates the clear all button text."""
        voice_page.apply_language()
        assert voice_page.clear_all_btn.text()  # Non-empty

    def test_apply_language_updates_section_label_text(self, voice_page):
        """apply_language updates the section label text."""
        voice_page.apply_language()
        assert voice_page.section_label.text()  # Non-empty

    def test_apply_language_updates_drop_area_label(self, voice_page):
        """apply_language updates drop area supported formats text."""
        voice_page.apply_language()
        supported_text = voice_page.drop_area.supported_label.text()
        assert supported_text  # Non-empty

    def test_apply_theme_when_hidden(self, voice_page):
        """apply_theme does not crash when widget is hidden."""
        voice_page.hide()
        voice_page.apply_theme()  # Should not raise

    def test_apply_language_when_hidden(self, voice_page):
        """apply_language does not crash when widget is hidden."""
        voice_page.hide()
        voice_page.apply_language()  # Should not raise


# ---------------------------------------------------------------------------
# TestVoicePageCheckRequirements (pytest-qt)
# ---------------------------------------------------------------------------


class TestVoicePageCheckRequirements:
    """Tests for _check_requirements in VoicePage."""

    @patch(f"{_MOD}.load_setting", return_value="Edge TTS")
    def test_edge_tts_always_passes(self, mock_load, voice_page):
        """Edge TTS does not require setup; _check_requirements returns True."""
        assert voice_page._check_requirements() is True

    @patch(f"{_MOD}.require_setup", return_value=True)
    @patch(f"{_MOD}.load_setting", return_value="Google Cloud TTS")
    def test_google_tts_calls_require_setup(
        self,
        mock_load,
        mock_require,
        voice_page,
    ):
        """Google Cloud TTS triggers require_setup check."""
        result = voice_page._check_requirements()
        assert result is True
        mock_require.assert_called_once()

    @patch(f"{_MOD}.require_setup", return_value=False)
    @patch(f"{_MOD}.load_setting", return_value="Google Cloud TTS")
    def test_google_tts_fails_when_not_setup(
        self,
        mock_load,
        mock_require,
        voice_page,
    ):
        """Google Cloud TTS returns False when setup is incomplete."""
        assert voice_page._check_requirements() is False


# ---------------------------------------------------------------------------
# TestVoicePageReGenerate (pytest-qt)
# ---------------------------------------------------------------------------


class TestVoicePageReGenerate:
    """Tests for _handle_re_generate in VoicePage."""

    @patch(f"{_HIST_MOD}.get_voice_fingerprint", return_value=None)
    @patch(f"{_HIST_MOD}.get_voice_history", return_value=[])
    @patch(f"{_MOD}.VoiceSetupDialog")
    @patch(f"{_MOD}.load_setting", return_value="Edge TTS")
    @patch(f"{_MOD}.update_voice_status")
    def test_re_generate_not_accepted(  # noqa: PLR0913
        self,
        mock_status,
        mock_load,
        mock_dialog,
        mock_hist,
        mock_fp,
        voice_page,
    ):
        """_handle_re_generate does nothing if dialog is not accepted."""
        mock_dialog.get_selection.return_value = ("English", "Female", None, False)
        with patch.object(voice_page, "_check_requirements", return_value=True):
            voice_page._handle_re_generate([(1, "/tmp/x.srt")])

        # Status should not be updated to Pending since dialog rejected
        mock_status.assert_not_called()

    @patch(f"{_HIST_MOD}.get_voice_fingerprint", return_value=None)
    @patch(f"{_HIST_MOD}.get_voice_history", return_value=[])
    @patch(f"{_MOD}.VoiceSetupDialog")
    @patch(f"{_MOD}.load_setting", return_value="Edge TTS")
    @patch(f"{_MOD}.update_voice_status")
    def test_re_generate_resets_status_to_pending(  # noqa: PLR0913
        self,
        mock_status,
        mock_load,
        mock_dialog,
        mock_hist,
        mock_fp,
        voice_page,
    ):
        """_handle_re_generate sets tasks to STATUS_PENDING before starting."""
        mock_dialog.get_selection.return_value = ("English", "Female", None, True)
        with (
            patch.object(voice_page, "_check_requirements", return_value=True),
            patch.object(voice_page, "_start_worker"),
        ):
            voice_page._handle_re_generate([(1, "/tmp/x.srt")])

        mock_status.assert_called_once_with(1, STATUS_PENDING)

    def test_re_generate_fails_requirements(self, voice_page):
        """_handle_re_generate returns early if requirements not met."""
        with patch.object(voice_page, "_check_requirements", return_value=False):
            voice_page._handle_re_generate([(1, "/tmp/x.srt")])
        # Should not crash and worker should remain None
        assert voice_page._worker is None


# ---------------------------------------------------------------------------
# TestVoicePageDragDrop (pytest-qt)
# ---------------------------------------------------------------------------


class TestVoicePageDragDrop:
    """Tests for drag and drop on the FileDropWidget within VoicePage."""

    def test_drop_area_accepts_drops(self, voice_page):
        """Drop area has drops enabled."""
        assert voice_page.drop_area.acceptDrops()

    def test_files_dropped_signal_connected(self, voice_page, tmp_path):
        """files_dropped signal is connected to _handle_files_dropped."""
        # Verify connection by emitting the signal and checking side effect
        srt_file = tmp_path / "signal_test.srt"
        srt_file.write_text("content", encoding="utf-8")
        voice_page.drop_area.files_dropped.emit([str(srt_file)])
        assert str(srt_file) in voice_page.selected_files

    def test_drop_supported_file(self, voice_page, tmp_path):
        """Dropping a supported file adds it to selected_files."""
        srt_file = tmp_path / "drop_test.srt"
        srt_file.write_text("1\n00:00:01,000 --> 00:00:02,000\nHi", encoding="utf-8")

        # Simulate the signal
        voice_page._handle_files_dropped([str(srt_file)])

        assert str(srt_file) in voice_page.selected_files

    def test_drop_vtt_file(self, voice_page, tmp_path):
        """Dropping a .vtt file is accepted."""
        vtt_file = tmp_path / "test.vtt"
        vtt_file.write_text(
            "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nHi", encoding="utf-8"
        )

        voice_page._handle_files_dropped([str(vtt_file)])
        assert str(vtt_file) in voice_page.selected_files

    def test_drop_ass_file(self, voice_page, tmp_path):
        """Dropping a .ass file is accepted."""
        ass_file = tmp_path / "test.ass"
        ass_file.write_text("[Script Info]\nTitle: Test", encoding="utf-8")

        voice_page._handle_files_dropped([str(ass_file)])
        assert str(ass_file) in voice_page.selected_files

    def test_drop_ssa_file(self, voice_page, tmp_path):
        """Dropping a .ssa file is accepted."""
        ssa_file = tmp_path / "test.ssa"
        ssa_file.write_text("[Script Info]\nTitle: Test", encoding="utf-8")

        voice_page._handle_files_dropped([str(ssa_file)])
        assert str(ssa_file) in voice_page.selected_files

    def test_drop_txt_file(self, voice_page, tmp_path):
        """Dropping a .txt file is accepted."""
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("Hello world", encoding="utf-8")

        voice_page._handle_files_dropped([str(txt_file)])
        assert str(txt_file) in voice_page.selected_files

    @patch(f"{_MOD}.CustomMessageDialog")
    def test_drop_unsupported_file_shows_dialog(
        self,
        mock_dialog,
        voice_page,
        tmp_path,
    ):
        """Dropping an unsupported file shows an error dialog."""
        mp4_file = tmp_path / "video.mp4"
        mp4_file.write_text("fake video", encoding="utf-8")

        voice_page._handle_files_dropped([str(mp4_file)])

        mock_dialog.show_message.assert_called_once()

    @patch(f"{_MOD}.CustomMessageDialog")
    def test_drop_mixed_supported_unsupported(
        self,
        mock_dialog,
        voice_page,
        tmp_path,
    ):
        """Mixed drop adds supported files and shows dialog for unsupported."""
        srt_file = tmp_path / "good.srt"
        srt_file.write_text("content", encoding="utf-8")
        mp4_file = tmp_path / "bad.mp4"
        mp4_file.write_text("content", encoding="utf-8")

        voice_page._handle_files_dropped([str(srt_file), str(mp4_file)])

        assert str(srt_file) in voice_page.selected_files
        assert str(mp4_file) not in voice_page.selected_files
        mock_dialog.show_message.assert_called_once()


# ---------------------------------------------------------------------------
# TestVoicePageHistorySelection (pytest-qt)
# ---------------------------------------------------------------------------


class TestVoicePageHistorySelection:
    """Tests for history table button state management."""

    def test_history_buttons_disabled_initially(self, voice_page):
        """History action buttons start disabled with no selection."""
        assert not voice_page.history_view.open_btn.isEnabled()
        assert not voice_page.history_view.delete_btn.isEnabled()
        assert not voice_page.history_view.re_generate_btn.isEnabled()

    def test_clean_history_view_runs(self, voice_page):
        """_clean_history_view does not crash."""
        voice_page._clean_history_view()  # Should not raise


# ---------------------------------------------------------------------------
# TestVoicePageDirectoryDrop (pytest-qt)
# ---------------------------------------------------------------------------


class TestVoicePageDirectoryDrop:
    """Tests for dropping a directory containing subtitle/text files."""

    def test_directory_with_subtitles_adds_them(self, voice_page, tmp_path):
        """Dropping a directory traverses it and adds subtitle files."""
        subdir = tmp_path / "subs"
        subdir.mkdir()
        srt = subdir / "ep1.srt"
        srt.write_text("1\n00:00:01,000 --> 00:00:02,000\nHi", encoding="utf-8")
        vtt = subdir / "ep2.vtt"
        vtt.write_text("WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nHi", encoding="utf-8")

        voice_page._handle_files_dropped([str(subdir)])

        assert str(srt) in voice_page.selected_files
        assert str(vtt) in voice_page.selected_files

    def test_nested_directory_traversal(self, voice_page, tmp_path):
        """Nested subdirectories are traversed recursively."""
        nested = tmp_path / "subs" / "season1"
        nested.mkdir(parents=True)
        ass_file = nested / "ep01.ass"
        ass_file.write_text("[Script Info]", encoding="utf-8")

        voice_page._handle_files_dropped([str(tmp_path / "subs")])

        assert str(ass_file) in voice_page.selected_files

    def test_hidden_files_in_directory_skipped(self, voice_page, tmp_path):
        """Hidden files (dotfiles) inside directories are skipped."""
        subdir = tmp_path / "subs"
        subdir.mkdir()
        hidden = subdir / ".hidden.srt"
        hidden.write_text("content", encoding="utf-8")
        visible = subdir / "visible.srt"
        visible.write_text("content", encoding="utf-8")

        voice_page._handle_files_dropped([str(subdir)])

        assert str(hidden) not in voice_page.selected_files
        assert str(visible) in voice_page.selected_files


# ---------------------------------------------------------------------------
# TestVoicePageDuplicateFilePrevention (pytest-qt)
# ---------------------------------------------------------------------------


class TestVoicePageDuplicateFilePrevention:
    """Tests that the same file cannot be added twice."""

    def test_same_file_dropped_twice_only_added_once(self, voice_page, tmp_path):
        """Dropping the exact same file path twice results in a single entry."""
        srt = tmp_path / "dup.srt"
        srt.write_text("content", encoding="utf-8")

        voice_page._handle_files_dropped([str(srt)])
        voice_page._handle_files_dropped([str(srt)])

        assert voice_page.selected_files.count(str(srt)) == 1
        assert voice_page.files_badge.text() == "1"

    def test_same_file_in_single_drop_only_added_once(self, voice_page, tmp_path):
        """Same file appearing twice in one drop list is only added once."""
        srt = tmp_path / "dup2.srt"
        srt.write_text("content", encoding="utf-8")

        voice_page._handle_files_dropped([str(srt), str(srt)])

        assert voice_page.selected_files.count(str(srt)) == 1


# ---------------------------------------------------------------------------
# TestVoicePageUnsupportedFileFiltering (pytest-qt)
# ---------------------------------------------------------------------------


class TestVoicePageUnsupportedFileFiltering:
    """Tests that non-subtitle files in a mixed drop are filtered out."""

    @patch(f"{_MOD}.CustomMessageDialog")
    def test_mixed_drop_filters_unsupported(
        self,
        mock_dialog,
        voice_page,
        tmp_path,
    ):
        """Unsupported files are filtered and dialog is shown."""
        srt = tmp_path / "good.srt"
        srt.write_text("content", encoding="utf-8")
        mp4 = tmp_path / "bad.mp4"
        mp4.write_bytes(b"\x00" * 100)
        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"\x00" * 100)

        voice_page._handle_files_dropped([str(srt), str(mp4), str(pdf)])

        assert str(srt) in voice_page.selected_files
        assert str(mp4) not in voice_page.selected_files
        assert str(pdf) not in voice_page.selected_files
        mock_dialog.show_message.assert_called_once()

    @patch(f"{_MOD}.CustomMessageDialog")
    def test_all_unsupported_files_no_view_switch(
        self,
        mock_dialog,
        voice_page,
        tmp_path,
    ):
        """Dropping only unsupported files does not switch view."""
        mp4 = tmp_path / "file.mp4"
        mp4.write_bytes(b"\x00" * 100)

        voice_page._handle_files_dropped([str(mp4)])

        assert voice_page.stack.currentIndex() == 0
        assert voice_page.selected_files == []

    @patch(f"{_MOD}.CustomMessageDialog")
    def test_empty_files_skipped_as_unsupported(
        self,
        mock_dialog,
        voice_page,
        tmp_path,
    ):
        """Zero-byte subtitle files are rejected."""
        empty = tmp_path / "empty.srt"
        empty.write_bytes(b"")

        voice_page._handle_files_dropped([str(empty)])

        assert str(empty) not in voice_page.selected_files


# ---------------------------------------------------------------------------
# TestVoicePageGenerateWhileBusy (pytest-qt)
# ---------------------------------------------------------------------------


class TestVoicePageGenerateWhileBusy:
    """Tests that generate does nothing when a worker is already active."""

    def test_generate_noop_when_worker_active(self, voice_page, tmp_path):
        """_handle_generate returns early when _worker is not None."""
        srt = tmp_path / "busy.srt"
        srt.write_text("content", encoding="utf-8")
        voice_page.selected_files = [str(srt)]

        voice_page._worker = MagicMock()
        original_worker = voice_page._worker
        voice_page._handle_generate()

        # Worker should not have been replaced
        assert voice_page._worker is original_worker

    def test_start_worker_noop_when_worker_exists(self, voice_page):
        """_start_worker returns immediately when a worker is already set."""
        voice_page._worker = MagicMock()
        original_worker = voice_page._worker
        voice_page._start_worker([(1, "/tmp/x.srt")], "en", "Female", "edge", ".mp3")

        assert voice_page._worker is original_worker


# ---------------------------------------------------------------------------
# TestVoicePageFileCountBadge (pytest-qt)
# ---------------------------------------------------------------------------


class TestVoicePageFileCountBadge:
    """Tests for the file count badge updating correctly."""

    def test_badge_shows_zero_initially(self, voice_page):
        """Badge shows '0' when no files are selected."""
        assert voice_page.files_badge.text() == "0"

    def test_badge_updates_after_adding_files(self, voice_page, tmp_path):
        """Badge text reflects the number of selected files."""
        f1 = tmp_path / "a.srt"
        f2 = tmp_path / "b.vtt"
        f3 = tmp_path / "c.txt"
        f1.write_text("content", encoding="utf-8")
        f2.write_text("content", encoding="utf-8")
        f3.write_text("content", encoding="utf-8")

        voice_page._handle_files_dropped([str(f1), str(f2), str(f3)])

        assert voice_page.files_badge.text() == "3"

    def test_badge_decrements_after_remove(self, voice_page, tmp_path):
        """Badge updates after removing a file."""
        f1 = tmp_path / "x.srt"
        f2 = tmp_path / "y.srt"
        f1.write_text("content", encoding="utf-8")
        f2.write_text("content", encoding="utf-8")
        voice_page._handle_files_dropped([str(f1), str(f2)])
        assert voice_page.files_badge.text() == "2"

        widget = voice_page.files_vbox.itemAt(0).widget()
        voice_page._handle_remove_file(str(f1), widget)

        assert voice_page.files_badge.text() == "1"

    def test_badge_resets_after_clear_all(self, voice_page, tmp_path):
        """Badge resets to '0' after clearing all files."""
        srt = tmp_path / "z.srt"
        srt.write_text("content", encoding="utf-8")
        voice_page._handle_files_dropped([str(srt)])

        voice_page._handle_clear_all()

        assert voice_page.files_badge.text() == "0"


# ---------------------------------------------------------------------------
# TestVoicePageEmptyDrop (pytest-qt)
# ---------------------------------------------------------------------------


class TestVoicePageEmptyDrop:
    """Tests that an empty file list drop does not switch views."""

    def test_empty_drop_opens_file_dialog(self, voice_page):
        """Empty file list triggers QFileDialog instead of switching view."""
        with patch(f"{_MOD}.QFileDialog") as mock_fd:
            mock_fd.getOpenFileNames.return_value = ([], "")
            voice_page._handle_files_dropped([])
            mock_fd.getOpenFileNames.assert_called_once()

        assert voice_page.stack.currentIndex() == 0
        assert voice_page.selected_files == []

    def test_empty_drop_cancelled_dialog_no_change(self, voice_page):
        """Cancelled file dialog after empty drop leaves state unchanged."""
        with patch(f"{_MOD}.QFileDialog") as mock_fd:
            mock_fd.getOpenFileNames.return_value = ([], "")
            voice_page._handle_files_dropped([])

        assert voice_page.stack.currentIndex() == 0
        assert not voice_page.generate_btn.isEnabled()


# ---------------------------------------------------------------------------
# TestVoicePageVoiceSetupDialogCancel (pytest-qt)
# ---------------------------------------------------------------------------


class TestVoicePageVoiceSetupDialogCancel:
    """Tests that cancelling the voice setup dialog preserves files."""

    @patch(f"{_MOD}.VoiceSetupDialog")
    @patch(f"{_MOD}.load_setting", return_value="Edge TTS")
    def test_cancel_voice_setup_preserves_selected_files(
        self,
        mock_load,
        mock_dialog,
        voice_page,
        tmp_path,
    ):
        """Cancelling VoiceSetupDialog keeps files in the selection."""
        srt = tmp_path / "keep.srt"
        srt.write_text("content", encoding="utf-8")
        voice_page._handle_files_dropped([str(srt)])

        mock_dialog.get_selection.return_value = ("English", "Female", None, False)
        with patch.object(voice_page, "_check_requirements", return_value=True):
            voice_page._handle_generate()

        # Files should still be present since dialog was cancelled
        assert str(srt) in voice_page.selected_files
        assert voice_page._worker is None

    @patch(f"{_MOD}.VoiceSetupDialog")
    @patch(f"{_MOD}.load_setting", return_value="Edge TTS")
    def test_cancel_voice_setup_view_unchanged(
        self,
        mock_load,
        mock_dialog,
        voice_page,
        tmp_path,
    ):
        """Cancelling VoiceSetupDialog does not switch back to history view."""
        srt = tmp_path / "stay.srt"
        srt.write_text("content", encoding="utf-8")
        voice_page._handle_files_dropped([str(srt)])
        assert voice_page.stack.currentIndex() == 1

        mock_dialog.get_selection.return_value = ("English", "Female", None, False)
        with patch.object(voice_page, "_check_requirements", return_value=True):
            voice_page._handle_generate()

        assert voice_page.stack.currentIndex() == 1


# ---------------------------------------------------------------------------
# TestVoicePageFileDialogCancel (pytest-qt)
# ---------------------------------------------------------------------------


class TestVoicePageFileDialogCancel:
    """Tests that cancelling the file dialog does not change state."""

    def test_file_dialog_cancel_no_state_change(self, voice_page):
        """Cancelling QFileDialog from browse leaves state unchanged."""
        with patch(f"{_MOD}.QFileDialog") as mock_fd:
            mock_fd.getOpenFileNames.return_value = ([], "")
            voice_page._handle_files_dropped([])

        assert voice_page.selected_files == []
        assert voice_page.stack.currentIndex() == 0
        assert not voice_page.generate_btn.isEnabled()

    def test_file_dialog_cancel_with_existing_files(self, voice_page, tmp_path):
        """Cancelling QFileDialog preserves existing file selection."""
        srt = tmp_path / "existing.srt"
        srt.write_text("content", encoding="utf-8")
        voice_page._handle_files_dropped([str(srt)])
        assert len(voice_page.selected_files) == 1

        with patch(f"{_MOD}.QFileDialog") as mock_fd:
            mock_fd.getOpenFileNames.return_value = ([], "")
            voice_page._handle_files_dropped([])

        # Existing files should still be present
        assert str(srt) in voice_page.selected_files


# ---------------------------------------------------------------------------
# NEW: Review-fix behaviours for Generate Voice
# ---------------------------------------------------------------------------


class TestDropCapNotice:
    """Tests for the 100-file cap + user notification."""

    def test_cap_hit_shows_notification(self, voice_page, tmp_path) -> None:
        """Dropping >100 voice-input files notifies and keeps first 100."""
        dir_path = tmp_path / "bulk"
        dir_path.mkdir()
        for i in range(105):
            (dir_path / f"f{i:03d}.srt").write_text("x", encoding="utf-8")

        with patch(f"{_MOD}.CustomMessageDialog.show_message") as mock_msg:
            voice_page._handle_files_dropped([str(dir_path)])

        assert len(voice_page.selected_files) == 100  # noqa: PLR2004
        assert mock_msg.called
        args = mock_msg.call_args.args
        assert any("drop_capped" in str(a) for a in args)


class TestDropDuplicateNotice:
    """Tests for silent-duplicate-skip notification."""

    def test_duplicate_drop_is_reported(self, voice_page, tmp_path) -> None:
        """Re-dropping a file surfaces the duplicates notice."""
        f = tmp_path / "clip.srt"
        f.write_text("1\n00:00:00,000 --> 00:00:01,000\nHi\n", encoding="utf-8")
        voice_page._handle_files_dropped([str(f)])
        assert len(voice_page.selected_files) == 1

        with patch(f"{_MOD}.CustomMessageDialog.show_message") as mock_msg:
            voice_page._handle_files_dropped([str(f)])

        assert len(voice_page.selected_files) == 1
        mock_msg.assert_called_once()
        args = mock_msg.call_args.args
        assert any("drop_duplicates" in str(a) for a in args)


class TestClearAllConfirmation:
    """Tests for the confirm dialog before clearing selection."""

    def test_confirm_accept_clears(self, voice_page, tmp_path) -> None:
        """Accepting the confirm dialog clears the selection."""
        f = tmp_path / "a.srt"
        f.write_text("x", encoding="utf-8")
        voice_page._handle_files_dropped([str(f)])

        with patch(
            f"{_MOD}.CustomConfirmDialog.confirm",
            return_value=True,
        ):
            voice_page._handle_clear_all()

        assert voice_page.selected_files == []

    def test_confirm_reject_keeps(self, voice_page, tmp_path) -> None:
        """Rejecting the confirm dialog keeps files."""
        f = tmp_path / "a.srt"
        f.write_text("x", encoding="utf-8")
        voice_page._handle_files_dropped([str(f)])

        with patch(
            f"{_MOD}.CustomConfirmDialog.confirm",
            return_value=False,
        ):
            voice_page._handle_clear_all()

        assert len(voice_page.selected_files) == 1

    def test_internal_confirm_false_skips_dialog(
        self,
        voice_page,
        tmp_path,
    ) -> None:
        """confirm=False skips the dialog entirely (used by internal cleanup)."""
        f = tmp_path / "a.srt"
        f.write_text("x", encoding="utf-8")
        voice_page._handle_files_dropped([str(f)])

        with patch(f"{_MOD}.CustomConfirmDialog.confirm") as mock_confirm:
            voice_page._handle_clear_all(confirm=False)

        mock_confirm.assert_not_called()
        assert voice_page.selected_files == []


class TestGenerateEmptyTasksKeepsFiles:
    """Covers the fix: empty-tasks result should NOT clear the selection."""

    @patch(f"{_MOD}.add_voice_entry", return_value=0)
    @patch(f"{_MOD}.VoiceSetupDialog.get_selection")
    @patch(f"{_MOD}.require_setup", return_value=True)
    def test_empty_tasks_keeps_files_and_notifies(
        self,
        _mock_require,
        mock_dialog,
        _mock_add,
        voice_page,
        tmp_path,
    ) -> None:
        """When every add_voice_entry returns falsy, the selection is kept."""
        f = tmp_path / "a.srt"
        f.write_text("x", encoding="utf-8")
        voice_page._handle_files_dropped([str(f)])
        mock_dialog.return_value = ("English", "FEMALE", "", True)

        with patch(f"{_MOD}.CustomMessageDialog.show_message") as mock_msg:
            voice_page._handle_generate()

        assert len(voice_page.selected_files) == 1
        mock_msg.assert_called_once()


class TestStopButton:
    """Tests for the Stop button that cancels an in-flight worker."""

    def test_stop_btn_hidden_by_default(self, voice_page) -> None:
        """Stop button is not visible before any worker starts."""
        assert voice_page.stop_btn.isHidden()

    @patch(f"{_MOD}._VoiceWorker")
    def test_start_worker_reveals_stop_button(
        self,
        mock_worker_cls,
        voice_page,
    ) -> None:
        """Starting a worker shows Stop and hides Generate."""
        worker_inst = MagicMock()
        mock_worker_cls.return_value = worker_inst

        voice_page._start_worker(
            [(1, "/a.srt")],
            "English",
            "FEMALE",
            "Edge TTS",
            ".mp3",
        )

        assert not voice_page.stop_btn.isHidden()
        assert voice_page.generate_btn.isHidden()

    @patch(f"{_MOD}._VoiceWorker")
    def test_handle_stop_forwards_to_worker(
        self,
        mock_worker_cls,
        voice_page,
    ) -> None:
        """_handle_stop calls worker.stop() and disables the button."""
        worker_inst = MagicMock()
        mock_worker_cls.return_value = worker_inst
        voice_page._start_worker(
            [(1, "/a.srt")],
            "English",
            "FEMALE",
            "Edge TTS",
            ".mp3",
        )

        voice_page._handle_stop()
        worker_inst.stop.assert_called_once()
        assert not voice_page.stop_btn.isEnabled()

    @patch(f"{_MOD}.update_voice_status")
    def test_on_finished_restores_generate_button(
        self,
        _mock_status,
        voice_page,
    ) -> None:
        """_on_finished hides Stop and re-shows Generate."""
        # Force the mid-generation visibility state first.
        voice_page.stop_btn.setVisible(True)
        voice_page.generate_btn.setVisible(False)

        voice_page._on_finished([])

        assert voice_page.stop_btn.isHidden()
        assert not voice_page.generate_btn.isHidden()


class TestReGenerateBusy:
    """Tests for the re-generate busy-guard path."""

    def test_re_generate_busy_shows_message(self, voice_page) -> None:
        """Re-generate while a worker runs surfaces a busy dialog."""
        voice_page._worker = MagicMock()  # simulate in-flight worker

        with patch(f"{_MOD}.CustomMessageDialog.show_message") as mock_msg:
            voice_page._handle_re_generate([(1, "/a.srt")])

        mock_msg.assert_called_once()
        args = mock_msg.call_args.args
        assert any("voice_busy" in str(a) for a in args)


class TestCheckRequirementsElevenLabs:
    """Tests that ElevenLabs now gets a proper credential pre-check."""

    @patch(f"{_MOD}.check_elevenlabs_setup", return_value=False)
    @patch(
        f"{_MOD}.load_setting",
        side_effect=lambda k, d=None: "ElevenLabs" if "tts_method" in k else d,
    )
    def test_elevenlabs_missing_key_blocks_generation(
        self,
        _mock_load,
        _mock_check_el,
        voice_page,
    ) -> None:
        """ElevenLabs method with no API key fails _check_requirements."""
        with patch(f"{_MOD}.require_setup", return_value=False):
            assert voice_page._check_requirements() is False


class TestCheckRequirementsFFmpeg:
    """Tests that missing FFmpeg blocks generation with a clear message.

    Voice unconditionally requires ffmpeg because the format-needs-ffmpeg
    matrix is backend-dependent (Edge+WAV needs ffmpeg for MP3→WAV
    transcode; Piper+MP3 needs WAV→MP3; Gemini PCM always needs
    transcoding) — surfacing the block up-front is more honest than
    failing deep in the worker after queuing files.
    """

    @patch(f"{_SPEECH}.check_ffmpeg_available", return_value=False)
    @patch(
        f"{_MOD}.load_setting",
        side_effect=lambda k, d=None: "Edge TTS" if "tts_method" in k else d,
    )
    def test_no_ffmpeg_blocks_generation(
        self,
        _mock_load,
        _mock_ffmpeg,
        voice_page,
    ) -> None:
        """Without FFmpeg, _check_requirements shows an error and returns False."""
        with patch(f"{_MOD}.CustomMessageDialog.show_message") as mock_msg:
            result = voice_page._check_requirements()

        assert result is False
        mock_msg.assert_called_once()
        args = mock_msg.call_args.args
        assert any("ffmpeg_required" in str(a) for a in args)


class TestCtrlEnterShortcut:
    """Tests for the new Ctrl+Enter shortcut."""

    def test_shortcut_is_registered(self, voice_page) -> None:
        """A Ctrl+Enter QShortcut exists on the page."""
        from PySide6.QtCore import Qt  # noqa: PLC0415
        from PySide6.QtGui import QKeySequence, QShortcut  # noqa: PLC0415

        target = QKeySequence(Qt.Modifier.CTRL | Qt.Key.Key_Return)
        shortcuts = [s for s in voice_page.findChildren(QShortcut) if s.key() == target]
        assert shortcuts, "Ctrl+Enter shortcut not registered"


class TestStopAllWorkersBoundedWait:
    """``aboutToQuit`` must drain the worker with a bounded wait.

    Pins the ``stop()`` → ``wait(2000)`` contract so a future refactor
    can't regress to an unbounded ``wait()`` and block app exit when a
    stage (FFmpeg mux, OCR call, LLM stream) takes too long to honour
    the cancel flag.
    """

    def test_worker_gets_stop_then_bounded_wait(self, voice_page) -> None:
        """``_stop_all_workers`` calls ``stop()`` then ``wait(2000)``."""
        from unittest.mock import MagicMock  # noqa: PLC0415

        worker = MagicMock()
        worker.wait.return_value = True
        voice_page._worker = worker
        voice_page._stop_all_workers()

        worker.stop.assert_called_once()
        worker.wait.assert_called_once_with(2000)
        assert voice_page._worker is None

    def test_no_worker_is_noop(self, voice_page) -> None:
        """Empty worker slot is a safe no-op."""
        voice_page._worker = None
        voice_page._stop_all_workers()
        assert voice_page._worker is None


class TestEmbeddedHistoryHeaderHidden:
    """Inner history page's header_label is hidden when embedded.

    AGENTS.md: "Pages that embed another `create_page_container`-based
    widget hide the inner title via `page.header_label.setVisible(False)`;
    never match the label by translated text, since language-switch
    ordering can make the comparison miss."

    Without this regression test, a refactor could re-show the inner
    header and produce a duplicate-title visual bug.
    """

    def test_inner_history_header_is_hidden(self, voice_page) -> None:
        inner_page = voice_page.history_view.page
        assert inner_page.header_label.isVisible() is False
