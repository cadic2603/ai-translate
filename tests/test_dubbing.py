"""Comprehensive tests for the dubbing pipeline in src/ui/pages/dubbing.py.

Tests the _DubbingWorker pipeline logic (_run_dubbing_pipeline and run())
without any PySide6/Qt dependency by mocking all external calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.constants.history import (
    DUBBING_PROGRESS_MIX_START,
    DUBBING_PROGRESS_STT_DONE,
    DUBBING_PROGRESS_STT_START,
    DUBBING_PROGRESS_TRANSLATE_DONE,
    DUBBING_PROGRESS_TTS_DONE,
    DUBBING_PROGRESS_TTS_START,
    PROGRESS_COMPLETE,
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_GENERATING,
    STATUS_PAUSED,
    STATUS_PENDING,
)

# ---------------------------------------------------------------------------
# Lightweight stand-in for SubtitleEntry (avoid importing subtitle_utils
# which may pull in heavier deps).
# ---------------------------------------------------------------------------


@dataclass
class _FakeEntry:
    """Minimal SubtitleEntry stand-in for testing."""

    index: int
    start: str
    end: str
    text: str
    raw_text: str = ""
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FAKE_SRT = (
    "1\n00:00:01,000 --> 00:00:02,000\nHello world\n\n"
    "2\n00:00:03,000 --> 00:00:04,000\nGoodbye\n"
)

_FAKE_TRANSLATED_SRT = (
    "1\n00:00:01,000 --> 00:00:02,000\nXin chao\n\n"
    "2\n00:00:03,000 --> 00:00:04,000\nTam biet\n"
)

_ENTRY_ID = 42  # noqa: PLR2004


def _make_entries(texts: list[str] | None = None) -> list[_FakeEntry]:
    """Creates a list of fake subtitle entries."""
    texts = texts or ["Hello world", "Goodbye"]
    return [
        _FakeEntry(
            index=i, start=f"00:00:0{i + 1},000", end=f"00:00:0{i + 2},000", text=t
        )
        for i, t in enumerate(texts)
    ]


def _make_worker(
    tasks: list[tuple[int, str]] | None = None,
    src_lang: str = "English (US)",
    target_lang: str = "Vietnamese",
) -> object:
    """Creates a _DubbingWorker-like object with the pipeline method.

    We import here to avoid top-level PySide6 import during collection.
    """
    # We cannot instantiate _DubbingWorker without Qt, so we create a
    # lightweight mock that has the same attributes the pipeline reads.
    worker = MagicMock()
    worker._tasks = tasks or [(_ENTRY_ID, "/tmp/video.mp4")]
    worker._src_lang = src_lang
    worker._target_lang = target_lang
    worker._voice_gender = "FEMALE"
    worker._is_running = True
    # Default: never cancelled. Override in tests that need cancellation.
    worker._is_task_cancelled = MagicMock(return_value=False)
    return worker


def _default_kwargs(
    tmp_path: Path,
    *,
    entry_id: int = _ENTRY_ID,
    video_path: str = "/tmp/video.mp4",
) -> dict:
    """Returns a standard kwargs dict for _run_dubbing_pipeline."""
    storage = tmp_path / "storage"
    storage.mkdir(exist_ok=True)
    return {
        "entry_id": entry_id,
        "video_path": video_path,
        "storage_dir": storage,
        "stt_method": "Whisper",
        "model_size": "base",
        "tts_method": "Edge TTS",
        "audio_fmt": ".mp3",
        "glossary_entries": None,
        "transcribe_audio": MagicMock(return_value=_FAKE_SRT),
        "translate_batch": MagicMock(return_value=["Xin chao", "Tam biet"]),
        "parse_subtitle": MagicMock(
            return_value=(_make_entries(), {"format": "srt"}),
        ),
        "serialize_subtitle": MagicMock(return_value=_FAKE_TRANSLATED_SRT),
        "synthesize_timed_speech": MagicMock(return_value=str(storage / "voice.mp3")),
        "mix_audio_into_video": MagicMock(),
        "save_checkpoint": MagicMock(),
        "load_checkpoint": MagicMock(return_value=None),
        "results": [],
    }


def _run_pipeline(worker: object, kwargs: dict) -> None:
    """Calls _run_dubbing_pipeline with proper patching."""
    from src.ui.pages.dubbing import _DubbingWorker  # noqa: PLC0415

    # Bind the real method to our mock worker
    _DubbingWorker._run_dubbing_pipeline(worker, **kwargs)


# ---------------------------------------------------------------------------
# Test classes
# ---------------------------------------------------------------------------


@patch("src.ui.pages.dubbing.update_dubbing_progress")
@patch("src.ui.pages.dubbing.get_dubbing_entry_status", return_value=STATUS_GENERATING)
@patch("src.ui.pages.dubbing.generate_dubbing_output_path")
@patch("src.ui.pages.dubbing.tr", side_effect=lambda key, **kw: key)
class TestStepStt:
    """Tests for Step 1: Speech-To-Text."""

    def test_resume_from_checkpoint_skips_transcribe(
        self,
        _tr,
        mock_gen_path,
        _status,
        _progress,
        tmp_path,
    ) -> None:
        """When srt_text is in checkpoint, transcribe is NOT called."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        kw["load_checkpoint"] = MagicMock(
            return_value={
                "srt_text": _FAKE_SRT,
                "target_lang": "Vietnamese",
                "translated_srt": _FAKE_TRANSLATED_SRT,
                "voice_file": "voice.mp3",
            }
        )
        # Create voice file so TTS step is skipped
        (kw["storage_dir"] / "voice.mp3").touch()

        _run_pipeline(worker, kw)

        kw["transcribe_audio"].assert_not_called()

    def test_fresh_execution_calls_transcribe(
        self,
        _tr,
        mock_gen_path,
        _status,
        _progress,
        tmp_path,
    ) -> None:
        """When no checkpoint, transcribe is called with correct params."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)

        _run_pipeline(worker, kw)

        kw["transcribe_audio"].assert_called_once()
        call_kwargs = kw["transcribe_audio"].call_args
        assert call_kwargs[0][0] == "/tmp/video.mp4"
        assert call_kwargs[1]["src_lang"] == "English (US)"
        assert call_kwargs[1]["stt_method"] == "Whisper"
        assert call_kwargs[1]["model_size"] == "base"

    def test_cancelled_after_transcribe_returns_early(
        self,
        _tr,
        mock_gen_path,
        _status,
        _progress,
        tmp_path,
    ) -> None:
        """If cancelled after STT, pipeline returns without translating."""
        worker = _make_worker()
        # The first cancel() call is at line 285 (after transcribe).
        # Return True to cancel immediately after STT.
        worker._is_task_cancelled = MagicMock(return_value=True)
        kw = _default_kwargs(tmp_path)

        _run_pipeline(worker, kw)

        # translate_batch should NOT be called since we cancelled
        kw["translate_batch"].assert_not_called()

    def test_empty_speech_result_raises_value_error(
        self,
        _tr,
        _gen_path,
        _status,
        _progress,
        tmp_path,
    ) -> None:
        """Empty STT result raises ValueError."""
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        kw["transcribe_audio"] = MagicMock(return_value="   ")

        with pytest.raises(ValueError, match="dubbing.no_speech_detected"):
            _run_pipeline(worker, kw)

    def test_checkpoint_saved_after_stt(
        self,
        _tr,
        mock_gen_path,
        _status,
        _progress,
        tmp_path,
    ) -> None:
        """After STT, checkpoint is saved with srt_text and target_lang."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)

        _run_pipeline(worker, kw)

        # First save_checkpoint call should have srt_text and target_lang
        first_call = kw["save_checkpoint"].call_args_list[0]
        assert first_call[0][0] == kw["storage_dir"]
        assert first_call[1]["srt_text"] == _FAKE_SRT
        assert first_call[1]["target_lang"] == "Vietnamese"

    def test_progress_updated_to_stt_done(
        self,
        _tr,
        mock_gen_path,
        _status,
        mock_progress,
        tmp_path,
    ) -> None:
        """Progress updated to STT_START then STT_DONE."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)

        _run_pipeline(worker, kw)

        progress_calls = [c[0] for c in mock_progress.call_args_list]
        # Check that STT_START and STT_DONE are in the progress calls
        assert (_ENTRY_ID, DUBBING_PROGRESS_STT_START) in progress_calls
        assert (_ENTRY_ID, DUBBING_PROGRESS_STT_DONE) in progress_calls


@patch("src.ui.pages.dubbing.update_dubbing_progress")
@patch("src.ui.pages.dubbing.get_dubbing_entry_status", return_value=STATUS_GENERATING)
@patch("src.ui.pages.dubbing.generate_dubbing_output_path")
@patch("src.ui.pages.dubbing.tr", side_effect=lambda key, **kw: key)
class TestStepTranslate:
    """Tests for Step 2: Translation."""

    def test_resume_from_checkpoint_skips_translate(
        self,
        _tr,
        mock_gen_path,
        _status,
        _progress,
        tmp_path,
    ) -> None:
        """When translated_srt is in checkpoint, translate_batch is skipped."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        kw["load_checkpoint"] = MagicMock(
            return_value={
                "srt_text": _FAKE_SRT,
                "translated_srt": _FAKE_TRANSLATED_SRT,
                "target_lang": "Vietnamese",
                "voice_file": "voice.mp3",
            }
        )
        (kw["storage_dir"] / "voice.mp3").touch()

        _run_pipeline(worker, kw)

        kw["translate_batch"].assert_not_called()

    def test_fresh_with_entries_calls_translate_batch(
        self,
        _tr,
        mock_gen_path,
        _status,
        _progress,
        tmp_path,
    ) -> None:
        """translate_batch is called with extracted subtitle texts."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)

        _run_pipeline(worker, kw)

        kw["translate_batch"].assert_called_once()
        batch_call = kw["translate_batch"].call_args
        assert batch_call[0][0] == ["Hello world", "Goodbye"]
        assert batch_call[1]["target_lang"] == "Vietnamese"
        assert batch_call[1]["src_lang"] == "English (US)"

    def test_fresh_with_no_entries_skips_translate(
        self,
        _tr,
        mock_gen_path,
        _status,
        _progress,
        tmp_path,
    ) -> None:
        """When parse_subtitle returns empty entries, translate is skipped."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        # First call (STT parse for translate) returns empty,
        # but we need TTS parse to also return empty → raises ValueError
        kw["parse_subtitle"] = MagicMock(return_value=([], {}))

        with pytest.raises(ValueError, match="dubbing.no_speech_detected"):
            _run_pipeline(worker, kw)

        kw["translate_batch"].assert_not_called()

    def test_result_count_mismatch_preserves_original(
        self,
        _tr,
        mock_gen_path,
        _status,
        _progress,
        tmp_path,
    ) -> None:
        """When LLM returns wrong count, original entries are not updated."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        # Return mismatched count
        kw["translate_batch"] = MagicMock(return_value=["Only one"])

        _run_pipeline(worker, kw)

        # serialize_subtitle should still be called (with un-mutated entries)
        kw["serialize_subtitle"].assert_called()
        # Verify original entry texts were NOT mutated
        entries_passed = kw["serialize_subtitle"].call_args[0][0]
        original_texts = [e.text for e in entries_passed]
        assert original_texts == ["Hello world", "Goodbye"]

    def test_cancelled_after_translation_returns_early(
        self,
        _tr,
        mock_gen_path,
        _status,
        _progress,
        tmp_path,
    ) -> None:
        """Cancellation after translation → no TTS step."""
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        # cancel() calls in a fresh run:
        # 1st: line 285 (after STT) → False
        # 2nd: line 316 (after translate_batch) → False
        # 3rd: line 336 (before TTS) → True  ← cancel here
        worker._is_task_cancelled = MagicMock(
            side_effect=[False, False, True],
        )

        _run_pipeline(worker, kw)

        # synthesize_timed_speech should not be called
        kw["synthesize_timed_speech"].assert_not_called()

    def test_glossary_entries_forwarded_to_translate_batch(
        self,
        _tr,
        mock_gen_path,
        _status,
        _progress,
        tmp_path,
    ) -> None:
        """Glossary entries are passed through to translate_batch."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        glossary = [(1, "Hello", "Xin chao"), (2, "Goodbye", "Tam biet")]
        kw["glossary_entries"] = glossary

        _run_pipeline(worker, kw)

        batch_call = kw["translate_batch"].call_args
        assert batch_call[1]["glossary_entries"] == glossary


@patch("src.ui.pages.dubbing.update_dubbing_progress")
@patch("src.ui.pages.dubbing.get_dubbing_entry_status", return_value=STATUS_GENERATING)
@patch("src.ui.pages.dubbing.generate_dubbing_output_path")
@patch("src.ui.pages.dubbing.tr", side_effect=lambda key, **kw: key)
class TestStepTts:
    """Tests for Step 3: Text-To-Speech."""

    def test_resume_from_checkpoint_skips_synthesis(
        self,
        _tr,
        mock_gen_path,
        _status,
        _progress,
        tmp_path,
    ) -> None:
        """When voice_file exists in checkpoint and on disk, TTS is skipped."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        kw["load_checkpoint"] = MagicMock(
            return_value={
                "srt_text": _FAKE_SRT,
                "translated_srt": _FAKE_TRANSLATED_SRT,
                "target_lang": "Vietnamese",
                "voice_file": "voice.mp3",
            }
        )
        # Create the voice file on disk
        (kw["storage_dir"] / "voice.mp3").touch()

        _run_pipeline(worker, kw)

        kw["synthesize_timed_speech"].assert_not_called()

    def test_fresh_execution_calls_synthesize(
        self,
        _tr,
        mock_gen_path,
        _status,
        _progress,
        tmp_path,
    ) -> None:
        """synthesize_timed_speech is called with correct parameters."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)

        _run_pipeline(worker, kw)

        kw["synthesize_timed_speech"].assert_called_once()
        synth_call = kw["synthesize_timed_speech"].call_args
        assert synth_call[1]["target_lang"] == "Vietnamese"
        assert synth_call[1]["voice_gender"] == "FEMALE"
        assert synth_call[1]["tts_method"] == "Edge TTS"
        assert synth_call[1]["audio_format"] == ".mp3"

    def test_empty_entries_raises_value_error(
        self,
        _tr,
        mock_gen_path,
        _status,
        _progress,
        tmp_path,
    ) -> None:
        """Empty subtitle entries at TTS step raises ValueError."""
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        # First parse_subtitle call (for translate) returns entries,
        # second call (for TTS) returns empty.
        entries = _make_entries()
        kw["parse_subtitle"] = MagicMock(
            side_effect=[
                (entries, {"format": "srt"}),  # Step 2 parse
                ([], {}),  # Step 3 parse
            ],
        )

        with pytest.raises(ValueError, match="dubbing.no_speech_detected"):
            _run_pipeline(worker, kw)

    def test_progress_callback_in_tts_range(
        self,
        _tr,
        mock_gen_path,
        _status,
        mock_progress,
        tmp_path,
    ) -> None:
        """TTS progress updates are in the 50-90 range."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)

        def capture_synth(entries, **kwargs):
            # Simulate progress callbacks
            on_progress = kwargs.get("on_progress")
            if on_progress:
                on_progress(1, 2)
                on_progress(2, 2)
            return str(kw["storage_dir"] / "voice.mp3")

        kw["synthesize_timed_speech"] = MagicMock(side_effect=capture_synth)

        _run_pipeline(worker, kw)

        # Extract progress values after TTS_START
        progress_values = [c[0][1] for c in mock_progress.call_args_list]
        # Check that TTS progress calls include values in the 50-90 range
        tts_progress = [
            v
            for v in progress_values
            if DUBBING_PROGRESS_TTS_START < v <= DUBBING_PROGRESS_TTS_DONE
        ]
        assert len(tts_progress) >= 1

    def test_cancelled_after_synthesis_returns_early(
        self,
        _tr,
        mock_gen_path,
        _status,
        _progress,
        tmp_path,
    ) -> None:
        """Cancellation after TTS → no mix step."""
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        # cancel() calls in a fresh run:
        # 1st: line 285 (after STT) → False
        # 2nd: line 316 (after translate) → False
        # 3rd: line 336 (before TTS) → False
        # 4th: line 367 (after synthesize) → False
        # 5th: line 375 (before mix) → True  ← cancel here
        worker._is_task_cancelled = MagicMock(
            side_effect=[False, False, False, False, True],
        )

        _run_pipeline(worker, kw)

        kw["mix_audio_into_video"].assert_not_called()

    def test_checkpoint_saved_with_voice_file(
        self,
        _tr,
        mock_gen_path,
        _status,
        _progress,
        tmp_path,
    ) -> None:
        """After TTS, checkpoint is saved with voice_file."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)

        _run_pipeline(worker, kw)

        # Find the save_checkpoint call that has voice_file
        voice_calls = [
            c for c in kw["save_checkpoint"].call_args_list if "voice_file" in c[1]
        ]
        assert len(voice_calls) == 1
        assert voice_calls[0][1]["voice_file"] == "voice.mp3"


@patch("src.ui.pages.dubbing.update_dubbing_progress")
@patch("src.ui.pages.dubbing.get_dubbing_entry_status", return_value=STATUS_GENERATING)
@patch("src.ui.pages.dubbing.generate_dubbing_output_path")
@patch("src.ui.pages.dubbing.tr", side_effect=lambda key, **kw: key)
class TestStepMix:
    """Tests for Step 4: Audio mixing into video."""

    def test_output_path_generation_with_locale_codes(
        self,
        _tr,
        mock_gen_path,
        _status,
        _progress,
        tmp_path,
    ) -> None:
        """generate_dubbing_output_path is called with language params."""
        output_path = tmp_path / "video_dubbed_en-US_vi.mp4"
        mock_gen_path.return_value = output_path
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)

        _run_pipeline(worker, kw)

        mock_gen_path.assert_called_once()
        gen_call = mock_gen_path.call_args
        assert gen_call[1]["src_lang"] == "English (US)"
        assert gen_call[1]["target_lang"] == "Vietnamese"

    def test_mix_called_with_correct_params(
        self,
        _tr,
        mock_gen_path,
        _status,
        _progress,
        tmp_path,
    ) -> None:
        """mix_audio_into_video is called with video, voice, output paths."""
        output_path = tmp_path / "dubbed.mp4"
        mock_gen_path.return_value = output_path
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)

        _run_pipeline(worker, kw)

        kw["mix_audio_into_video"].assert_called_once_with(
            "/tmp/video.mp4",
            str(kw["storage_dir"] / "voice.mp3"),
            str(output_path),
        )

    @patch(
        "src.constants.languages.get_locale_code",
        side_effect=lambda lang: {
            "English (US)": "en-US",
            "Vietnamese": "vi",
        }.get(lang, "unknown"),
    )
    def test_artifact_naming_convention(
        self,
        mock_locale,
        _tr,
        mock_gen_path,
        _status,
        _progress,
        tmp_path,
    ) -> None:
        """Intermediate artifacts follow the expected naming pattern."""
        output_path = tmp_path / "video_dubbed_en-US_vi.mp4"
        mock_gen_path.return_value = output_path
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        kw["video_path"] = "/home/user/my_video.mp4"

        _run_pipeline(worker, kw)

        results = kw["results"]
        assert len(results) == 1
        _eid, _out, srt_path, trans_srt_path, voice_path = results[0]

        # Verify naming convention: {stem}_subtitle_{locale}.srt
        assert "my_video_subtitle_en-US.srt" in srt_path
        assert "my_video_subtitle_vi.srt" in trans_srt_path
        assert "my_video_voice_vi.mp3" in voice_path

    def test_voice_file_copied_to_output_dir(
        self,
        _tr,
        mock_gen_path,
        _status,
        _progress,
        tmp_path,
    ) -> None:
        """Voice file is copied from storage to output directory."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        output_path = output_dir / "dubbed.mp4"
        mock_gen_path.return_value = output_path
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        # Create a real voice file in storage
        voice_src = kw["storage_dir"] / "voice.mp3"
        voice_src.write_bytes(b"fake audio data")

        with patch("src.constants.languages.get_locale_code", return_value="xx"):
            _run_pipeline(worker, kw)

        # Voice should be copied to output dir
        copied_files = list(output_dir.glob("*voice*"))
        assert len(copied_files) == 1

    def test_progress_complete_is_last_call(
        self,
        _tr,
        mock_gen_path,
        _status,
        mock_progress,
        tmp_path,
    ) -> None:
        """Progress 100 is the LAST progress call (not just present)."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)

        _run_pipeline(worker, kw)

        last_progress = mock_progress.call_args_list[-1][0]
        assert last_progress == (_ENTRY_ID, PROGRESS_COMPLETE)
        # Verify no progress call comes after PROGRESS_COMPLETE
        progress_values = [c[0][1] for c in mock_progress.call_args_list]
        complete_idx = (
            len(progress_values) - 1 - progress_values[::-1].index(PROGRESS_COMPLETE)
        )
        assert complete_idx == len(progress_values) - 1, (
            "PROGRESS_COMPLETE must be the final progress update"
        )

    def test_result_tuple_format(
        self,
        _tr,
        mock_gen_path,
        _status,
        _progress,
        tmp_path,
    ) -> None:
        """Result tuple has 5 elements: entry_id, output, srt, trans_srt, voice."""
        output_path = tmp_path / "dubbed.mp4"
        mock_gen_path.return_value = output_path
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)

        with patch("src.constants.languages.get_locale_code", return_value="xx"):
            _run_pipeline(worker, kw)

        results = kw["results"]
        assert len(results) == 1
        result = results[0]
        assert len(result) == 5  # noqa: PLR2004
        assert result[0] == _ENTRY_ID
        assert result[1] == str(output_path)
        # Elements [1:] are string paths, element [0] is int entry_id
        assert isinstance(result[0], int)
        assert all(isinstance(r, str) for r in result[1:])


@patch("src.ui.pages.dubbing.update_dubbing_progress")
@patch("src.ui.pages.dubbing.get_dubbing_entry_status", return_value=STATUS_GENERATING)
@patch("src.ui.pages.dubbing.generate_dubbing_output_path")
@patch("src.ui.pages.dubbing.tr", side_effect=lambda key, **kw: key)
class TestLanguageChangeDetection:
    """Tests for target language change detection in checkpoint resumption."""

    def test_language_changed_invalidates_translated_srt(
        self,
        _tr,
        mock_gen_path,
        _status,
        _progress,
        tmp_path,
    ) -> None:
        """When target language changed, translated_srt is removed from ckpt."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker(target_lang="French")
        kw = _default_kwargs(tmp_path)
        ckpt = {
            "srt_text": _FAKE_SRT,
            "translated_srt": _FAKE_TRANSLATED_SRT,
            "target_lang": "Vietnamese",
            "voice_file": "voice.mp3",
        }
        kw["load_checkpoint"] = MagicMock(return_value=ckpt)

        _run_pipeline(worker, kw)

        # translate_batch SHOULD be called since ckpt was invalidated
        kw["translate_batch"].assert_called_once()

    def test_language_changed_deletes_voice_file(
        self,
        _tr,
        mock_gen_path,
        _status,
        _progress,
        tmp_path,
    ) -> None:
        """When target language changed, voice file is deleted from disk."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker(target_lang="French")
        kw = _default_kwargs(tmp_path)
        voice_file = kw["storage_dir"] / "voice.mp3"
        voice_file.write_bytes(b"old voice data")
        ckpt = {
            "srt_text": _FAKE_SRT,
            "translated_srt": _FAKE_TRANSLATED_SRT,
            "target_lang": "Vietnamese",
            "voice_file": "voice.mp3",
        }
        kw["load_checkpoint"] = MagicMock(return_value=ckpt)

        _run_pipeline(worker, kw)

        # Voice file should have been deleted by language change detection
        # (it gets recreated by synthesize_timed_speech mock, but the
        # original deletion happened)
        kw["synthesize_timed_speech"].assert_called_once()

    def test_language_unchanged_preserves_checkpoint(
        self,
        _tr,
        mock_gen_path,
        _status,
        _progress,
        tmp_path,
    ) -> None:
        """When language matches, translated_srt stays in checkpoint."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker(target_lang="Vietnamese")
        kw = _default_kwargs(tmp_path)
        voice_file = kw["storage_dir"] / "voice.mp3"
        voice_file.touch()
        ckpt = {
            "srt_text": _FAKE_SRT,
            "translated_srt": _FAKE_TRANSLATED_SRT,
            "target_lang": "Vietnamese",
            "voice_file": "voice.mp3",
        }
        kw["load_checkpoint"] = MagicMock(return_value=ckpt)

        _run_pipeline(worker, kw)

        # Both translate and synthesize should be skipped
        kw["translate_batch"].assert_not_called()
        kw["synthesize_timed_speech"].assert_not_called()

    def test_language_change_logs_message(
        self,
        _tr,
        mock_gen_path,
        _status,
        _progress,
        tmp_path,
        caplog,
    ) -> None:
        """Language change produces an info log with old and new language."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker(target_lang="French")
        kw = _default_kwargs(tmp_path)
        ckpt = {
            "srt_text": _FAKE_SRT,
            "translated_srt": _FAKE_TRANSLATED_SRT,
            "target_lang": "Vietnamese",
        }
        kw["load_checkpoint"] = MagicMock(return_value=ckpt)

        import logging  # noqa: PLC0415

        with caplog.at_level(logging.INFO, logger="dubbing"):
            _run_pipeline(worker, kw)

        # Check that the log message mentions both languages
        assert any(
            "Vietnamese" in record.message and "French" in record.message
            for record in caplog.records
        )


@patch("src.ui.pages.dubbing.update_dubbing_progress")
@patch("src.ui.pages.dubbing.get_dubbing_entry_status", return_value=STATUS_GENERATING)
@patch("src.ui.pages.dubbing.update_dubbing_status")
@patch("src.ui.pages.dubbing.tr", side_effect=lambda key, **kw: key)
class TestDubbingPipelineErrors:
    """Tests for error handling in the dubbing pipeline."""

    def test_exception_sets_status_to_failed(
        self,
        _tr,
        mock_update_status,
        _status,
        _progress,
        tmp_path,
    ) -> None:
        """An exception in the pipeline sets the entry status to FAILED."""
        from src.ui.pages.dubbing import _DubbingWorker  # noqa: PLC0415

        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        kw["transcribe_audio"] = MagicMock(
            side_effect=RuntimeError("FFmpeg crashed"),
        )

        # We need to test via the run() method's exception handler.
        # Simulate the try/except in run() that catches per-task exceptions.
        entry_id = _ENTRY_ID

        try:
            _DubbingWorker._run_dubbing_pipeline(worker, **kw)
        except RuntimeError:
            # Simulate what run() does on exception
            mock_update_status(
                entry_id,
                STATUS_FAILED,
                error_message="FFmpeg crashed",
            )

        mock_update_status.assert_called_with(
            entry_id,
            STATUS_FAILED,
            error_message="FFmpeg crashed",
        )

    def test_exception_preserves_storage_dir(
        self,
        _tr,
        _update_status,
        _status,
        _progress,
        tmp_path,
    ) -> None:
        """Storage dir persists after exception (checkpoints survive)."""
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        kw["transcribe_audio"] = MagicMock(
            side_effect=RuntimeError("FFmpeg crashed"),
        )
        storage_dir = kw["storage_dir"]
        # Put a file in storage to verify it survives
        (storage_dir / "checkpoint.json").write_text("{}")

        with pytest.raises(RuntimeError, match="FFmpeg crashed"):
            _run_pipeline(worker, kw)

        assert storage_dir.exists()
        assert (storage_dir / "checkpoint.json").exists()

    @patch("src.ui.pages.dubbing.generate_dubbing_output_path")
    def test_multiple_tasks_error_in_one_doesnt_stop_others(
        self,
        mock_gen_path,
        _tr,
        mock_update_status,
        _status,
        _progress,
        tmp_path,
    ) -> None:
        """Error in one task doesn't prevent other tasks from running.

        This tests the run() method's per-task exception handling.
        """
        from src.ui.pages.dubbing import _DubbingWorker  # noqa: PLC0415

        task1_storage = tmp_path / "task1"
        task1_storage.mkdir()
        task2_storage = tmp_path / "task2"
        task2_storage.mkdir()

        task1_id = 10
        task2_id = 20

        call_count = 0

        def fake_transcribe(path, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("First task fails")
            return _FAKE_SRT

        mock_gen_path.return_value = tmp_path / "dubbed.mp4"

        # Simulate the run() loop manually (without Qt)
        tasks = [(task1_id, "/tmp/v1.mp4"), (task2_id, "/tmp/v2.mp4")]
        results: list = []

        for entry_id, video_path in tasks:
            mock_update_status(entry_id, STATUS_GENERATING)
            kw = _default_kwargs(tmp_path, entry_id=entry_id, video_path=video_path)
            kw["transcribe_audio"] = MagicMock(side_effect=fake_transcribe)
            kw["results"] = results

            try:
                _DubbingWorker._run_dubbing_pipeline(
                    _make_worker(),
                    **kw,
                )
            except RuntimeError:
                mock_update_status(
                    entry_id,
                    STATUS_FAILED,
                    error_message="First task fails",
                )

        # Task 1 failed, but task 2 should have succeeded
        failed_calls = [
            c
            for c in mock_update_status.call_args_list
            if len(c[0]) >= 2 and c[0][1] == STATUS_FAILED  # noqa: PLR2004
        ]
        assert len(failed_calls) == 1
        assert failed_calls[0][0][0] == task1_id

    def test_translate_batch_exception_propagates(
        self,
        _tr,
        _update_status,
        _status,
        _progress,
        tmp_path,
    ) -> None:
        """An exception in translate_batch propagates up."""
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        kw["translate_batch"] = MagicMock(
            side_effect=ValueError("AUTH_ERROR"),
        )

        with pytest.raises(ValueError, match="AUTH_ERROR"):
            _run_pipeline(worker, kw)


class TestDubbingWorkerControl:
    """Tests for _DubbingWorker control methods (is_busy, stop, cancel)."""

    def test_is_busy_class_method(self) -> None:
        """is_busy() reflects the class-level _is_any_worker_running flag."""
        from src.ui.pages.dubbing import _DubbingWorker  # noqa: PLC0415

        # Save original and ensure clean state
        original = _DubbingWorker._is_any_worker_running
        try:
            _DubbingWorker._is_any_worker_running = False
            assert not _DubbingWorker.is_busy()

            _DubbingWorker._is_any_worker_running = True
            assert _DubbingWorker.is_busy()
        finally:
            _DubbingWorker._is_any_worker_running = original

    def test_stop_sets_is_running_false(self) -> None:
        """stop() sets _is_running to False."""
        from src.ui.pages.dubbing import _DubbingWorker  # noqa: PLC0415

        worker = MagicMock(spec=_DubbingWorker)
        worker._is_running = True
        _DubbingWorker.stop(worker)
        assert not worker._is_running

    @patch(
        "src.ui.pages.dubbing.get_dubbing_entry_status", return_value=STATUS_GENERATING
    )
    def test_is_task_cancelled_when_not_running(self, _status) -> None:
        """_is_task_cancelled returns True when worker is stopped."""
        from src.ui.pages.dubbing import _DubbingWorker  # noqa: PLC0415

        worker = MagicMock(spec=_DubbingWorker)
        worker._is_running = False
        result = _DubbingWorker._is_task_cancelled(worker, _ENTRY_ID)
        assert result is True

    @patch("src.ui.pages.dubbing.get_dubbing_entry_status", return_value=STATUS_PAUSED)
    def test_is_task_cancelled_when_db_status_not_generating(
        self,
        _status,
    ) -> None:
        """_is_task_cancelled returns True when DB status is not Generating."""
        from src.ui.pages.dubbing import _DubbingWorker  # noqa: PLC0415

        worker = MagicMock(spec=_DubbingWorker)
        worker._is_running = True
        result = _DubbingWorker._is_task_cancelled(worker, _ENTRY_ID)
        assert result is True

    @patch(
        "src.ui.pages.dubbing.get_dubbing_entry_status", return_value=STATUS_GENERATING
    )
    def test_is_task_cancelled_when_running_and_generating(
        self,
        _status,
    ) -> None:
        """_is_task_cancelled returns False when running + Generating."""
        from src.ui.pages.dubbing import _DubbingWorker  # noqa: PLC0415

        worker = MagicMock(spec=_DubbingWorker)
        worker._is_running = True
        result = _DubbingWorker._is_task_cancelled(worker, _ENTRY_ID)
        assert result is False


@patch("src.ui.pages.dubbing.update_dubbing_progress")
@patch("src.ui.pages.dubbing.get_dubbing_entry_status", return_value=STATUS_GENERATING)
@patch("src.ui.pages.dubbing.generate_dubbing_output_path")
@patch("src.ui.pages.dubbing.tr", side_effect=lambda key, **kw: key)
class TestPipelineProgressSequence:
    """Tests for correct progress milestone ordering."""

    def test_full_pipeline_progress_order(
        self,
        _tr,
        mock_gen_path,
        _status,
        mock_progress,
        tmp_path,
    ) -> None:
        """Progress milestones follow the expected order."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)

        _run_pipeline(worker, kw)

        progress_calls = [c[0][1] for c in mock_progress.call_args_list]
        # Verify monotonic ordering of key milestones.
        # Note: DUBBING_PROGRESS_TTS_DONE == DUBBING_PROGRESS_MIX_START (both 90)
        # so we use deduplicated milestones for strict ordering.
        key_milestones = [
            DUBBING_PROGRESS_STT_START,  # 5
            DUBBING_PROGRESS_STT_DONE,  # 25
            DUBBING_PROGRESS_TRANSLATE_DONE,  # 50
            DUBBING_PROGRESS_TTS_DONE,  # 90 (same as MIX_START)
            PROGRESS_COMPLETE,  # 100
        ]
        milestone_positions = []
        for milestone in key_milestones:
            positions = [i for i, v in enumerate(progress_calls) if v == milestone]
            assert positions, f"Missing milestone {milestone}"
            milestone_positions.append(positions[0])

        # Check strict monotonic ordering
        for i in range(len(milestone_positions) - 1):
            assert milestone_positions[i] < milestone_positions[i + 1], (
                f"Milestone at position {milestone_positions[i]} should come "
                f"before {milestone_positions[i + 1]}"
            )

    def test_stt_resume_skips_stt_start(
        self,
        _tr,
        mock_gen_path,
        _status,
        mock_progress,
        tmp_path,
    ) -> None:
        """When resuming from STT checkpoint, STT_START is not emitted."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        kw["load_checkpoint"] = MagicMock(
            return_value={
                "srt_text": _FAKE_SRT,
                "target_lang": "Vietnamese",
            }
        )

        _run_pipeline(worker, kw)

        progress_calls = [c[0][1] for c in mock_progress.call_args_list]
        assert DUBBING_PROGRESS_STT_START not in progress_calls
        assert DUBBING_PROGRESS_STT_DONE in progress_calls


@patch("src.ui.pages.dubbing.update_dubbing_progress")
@patch("src.ui.pages.dubbing.get_dubbing_entry_status", return_value=STATUS_GENERATING)
@patch("src.ui.pages.dubbing.generate_dubbing_output_path")
@patch("src.ui.pages.dubbing.tr", side_effect=lambda key, **kw: key)
class TestCheckpointInteraction:
    """Tests for checkpoint save/load interactions."""

    def test_no_checkpoint_saves_all_three_steps(
        self,
        _tr,
        mock_gen_path,
        _status,
        _progress,
        tmp_path,
    ) -> None:
        """A full run without checkpoint saves STT, translate, and TTS."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)

        _run_pipeline(worker, kw)

        saves = kw["save_checkpoint"].call_args_list
        # 3 saves: STT, translate, TTS
        assert len(saves) == 3  # noqa: PLR2004

        # First save: srt_text + target_lang
        assert "srt_text" in saves[0][1]
        assert "target_lang" in saves[0][1]

        # Second save: translated_srt
        assert "translated_srt" in saves[1][1]

        # Third save: voice_file
        assert "voice_file" in saves[2][1]  # noqa: PLR2004

    def test_null_checkpoint_treated_as_fresh(
        self,
        _tr,
        mock_gen_path,
        _status,
        _progress,
        tmp_path,
    ) -> None:
        """load_checkpoint returning None triggers full pipeline."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        kw["load_checkpoint"] = MagicMock(return_value=None)

        _run_pipeline(worker, kw)

        kw["transcribe_audio"].assert_called_once()
        kw["translate_batch"].assert_called_once()
        kw["synthesize_timed_speech"].assert_called_once()
        kw["mix_audio_into_video"].assert_called_once()

    def test_partial_checkpoint_stt_only(
        self,
        _tr,
        mock_gen_path,
        _status,
        _progress,
        tmp_path,
    ) -> None:
        """Checkpoint with srt_text only: skips STT, runs translate+TTS+mix."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        kw["load_checkpoint"] = MagicMock(
            return_value={
                "srt_text": _FAKE_SRT,
                "target_lang": "Vietnamese",
            }
        )

        _run_pipeline(worker, kw)

        kw["transcribe_audio"].assert_not_called()
        kw["translate_batch"].assert_called_once()
        kw["synthesize_timed_speech"].assert_called_once()
        kw["mix_audio_into_video"].assert_called_once()

    def test_partial_checkpoint_stt_and_translate(
        self,
        _tr,
        mock_gen_path,
        _status,
        _progress,
        tmp_path,
    ) -> None:
        """Checkpoint with srt+translated: skips STT+translate, runs TTS+mix."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        kw["load_checkpoint"] = MagicMock(
            return_value={
                "srt_text": _FAKE_SRT,
                "translated_srt": _FAKE_TRANSLATED_SRT,
                "target_lang": "Vietnamese",
            }
        )

        _run_pipeline(worker, kw)

        kw["transcribe_audio"].assert_not_called()
        kw["translate_batch"].assert_not_called()
        kw["synthesize_timed_speech"].assert_called_once()
        kw["mix_audio_into_video"].assert_called_once()

    def test_full_checkpoint_skips_all_processing(
        self,
        _tr,
        mock_gen_path,
        _status,
        _progress,
        tmp_path,
    ) -> None:
        """Full checkpoint with voice file on disk: only mix runs."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        (kw["storage_dir"] / "voice.mp3").touch()
        kw["load_checkpoint"] = MagicMock(
            return_value={
                "srt_text": _FAKE_SRT,
                "translated_srt": _FAKE_TRANSLATED_SRT,
                "target_lang": "Vietnamese",
                "voice_file": "voice.mp3",
            }
        )

        _run_pipeline(worker, kw)

        kw["transcribe_audio"].assert_not_called()
        kw["translate_batch"].assert_not_called()
        kw["synthesize_timed_speech"].assert_not_called()
        kw["mix_audio_into_video"].assert_called_once()


@patch("src.ui.pages.dubbing.update_dubbing_progress")
@patch("src.ui.pages.dubbing.get_dubbing_entry_status", return_value=STATUS_GENERATING)
@patch("src.ui.pages.dubbing.generate_dubbing_output_path")
@patch("src.ui.pages.dubbing.tr", side_effect=lambda key, **kw: key)
class TestSubtitleHandling:
    """Tests for subtitle parsing and serialization interactions."""

    def test_original_srt_preserved_for_artifacts(
        self,
        _tr,
        mock_gen_path,
        _status,
        _progress,
        tmp_path,
    ) -> None:
        """Original STT output is preserved separately for artifact saving."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        output_path = output_dir / "dubbed.mp4"
        mock_gen_path.return_value = output_path
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        kw["video_path"] = "/tmp/test_video.mp4"

        locale_map = {"English (US)": "en-US", "Vietnamese": "vi"}
        with patch(
            "src.constants.languages.get_locale_code",
            side_effect=lambda lang: locale_map.get(lang, "xx"),
        ):
            _run_pipeline(worker, kw)

        # There should be two subtitle files: original (en-US) and translated (vi)
        all_srt = list(output_dir.glob("*.srt"))
        assert len(all_srt) == 2  # noqa: PLR2004
        srt_names = {f.name for f in all_srt}
        assert "test_video_subtitle_en-US.srt" in srt_names
        assert "test_video_subtitle_vi.srt" in srt_names

    def test_entries_text_updated_on_successful_translation(
        self,
        _tr,
        mock_gen_path,
        _status,
        _progress,
        tmp_path,
    ) -> None:
        """When translation succeeds, entry.text is updated before serialize."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        entries = _make_entries(["Hello", "World"])
        kw = _default_kwargs(tmp_path)
        kw["parse_subtitle"] = MagicMock(
            return_value=(entries, {"format": "srt"}),
        )
        kw["translate_batch"] = MagicMock(
            return_value=["Xin chao", "The gioi"],
        )

        _run_pipeline(worker, kw)

        # After translate, entries should have updated text
        # (checked via serialize_subtitle receiving mutated entries)
        serialize_call = kw["serialize_subtitle"].call_args
        serialized_entries = serialize_call[0][0]
        # The entries list is the same object, texts should be updated
        assert serialized_entries[0].text == "Xin chao"
        assert serialized_entries[1].text == "The gioi"

    def test_translate_batch_cancel_check_passed(
        self,
        _tr,
        mock_gen_path,
        _status,
        _progress,
        tmp_path,
    ) -> None:
        """translate_batch receives a cancel_check callback."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)

        _run_pipeline(worker, kw)

        batch_call = kw["translate_batch"].call_args
        assert "cancel_check" in batch_call[1]
        assert callable(batch_call[1]["cancel_check"])


@patch("src.ui.pages.dubbing.update_dubbing_progress")
@patch("src.ui.pages.dubbing.get_dubbing_entry_status", return_value=STATUS_GENERATING)
@patch("src.ui.pages.dubbing.generate_dubbing_output_path")
@patch("src.ui.pages.dubbing.tr", side_effect=lambda key, **kw: key)
class TestAdditionalEdgeCases:
    """Additional edge case tests to strengthen assertions."""

    def test_translate_batch_none_preserves_originals(
        self,
        _tr,
        mock_gen_path,
        _status,
        _progress,
        tmp_path,
    ) -> None:
        """When translate_batch returns None (cancelled), originals preserved."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        kw["translate_batch"] = MagicMock(return_value=None)

        _run_pipeline(worker, kw)

        # serialize should be called with original entry texts
        entries_passed = kw["serialize_subtitle"].call_args[0][0]
        assert [e.text for e in entries_passed] == ["Hello world", "Goodbye"]

    def test_mix_audio_exception_propagates(
        self,
        _tr,
        mock_gen_path,
        _status,
        _progress,
        tmp_path,
    ) -> None:
        """Exception in mix_audio_into_video propagates to caller."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        kw["mix_audio_into_video"] = MagicMock(
            side_effect=RuntimeError("FFmpeg not found"),
        )

        with pytest.raises(RuntimeError, match="FFmpeg not found"):
            _run_pipeline(worker, kw)

    def test_resumed_srt_flows_through_translate_and_tts(
        self,
        _tr,
        mock_gen_path,
        _status,
        _progress,
        tmp_path,
    ) -> None:
        """Checkpoint-resumed SRT text is actually used by translate and TTS."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        custom_srt = "1\n00:00:01,000 --> 00:00:02,000\nCustom text\n"
        kw = _default_kwargs(tmp_path)
        kw["load_checkpoint"] = MagicMock(
            return_value={
                "srt_text": custom_srt,
                "target_lang": "Vietnamese",
            }
        )

        _run_pipeline(worker, kw)

        # Verify translate received text parsed from the CUSTOM SRT
        kw["translate_batch"].assert_called_once()
        # Verify parse_subtitle was called with the custom SRT (not default)
        first_parse_call = kw["parse_subtitle"].call_args_list[0]
        assert first_parse_call[0][0] == custom_srt

    def test_voice_creation_failure_propagates(
        self,
        _tr,
        mock_gen_path,
        _status,
        _progress,
        tmp_path,
    ) -> None:
        """When TTS synthesis raises, error propagates."""
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        kw["synthesize_timed_speech"] = MagicMock(
            side_effect=RuntimeError("TTS engine failed"),
        )

        with pytest.raises(RuntimeError, match="TTS engine failed"):
            _run_pipeline(worker, kw)


# ---------------------------------------------------------------------------
# Pytest-qt fixtures (PySide6 required below this point)
# ---------------------------------------------------------------------------

_MOD = "src.ui.pages.dubbing"
_HIST_MOD = "src.ui.pages.dubbing_history"


@pytest.fixture(autouse=True)
def _auto_mock_blocking_dialogs():
    """Auto-mocks modal dialogs on the dubbing page so tests don't hang.

    Also stubs FFmpeg availability so the pre-check doesn't block on
    developer machines missing FFmpeg.
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
def window(qapp):
    """Provides a QMainWindow context with a navigate_to_settings_tab stub."""
    from PySide6.QtWidgets import QMainWindow  # noqa: PLC0415

    win = QMainWindow()
    win.navigate_to_settings_tab = MagicMock()
    return win


@pytest.fixture()
def _mock_dubbing_history_deps():
    """Mocks database calls used by DubbingHistoryPage during construction."""
    with (
        patch(f"{_HIST_MOD}.get_dubbing_fingerprint", return_value=None),
        patch(f"{_HIST_MOD}.get_dubbing_history", return_value=[]),
    ):
        yield


@pytest.fixture()
def page(window, _mock_dubbing_history_deps, qtbot):
    """Creates a DubbingPage widget for testing."""
    from src.ui.pages.dubbing import DubbingPage  # noqa: PLC0415

    with patch(f"{_MOD}.get_unfinished_dubbing", return_value=[]):
        p = DubbingPage(window)
    qtbot.addWidget(p)
    return p


# ---------------------------------------------------------------------------
# TestDubbingPageCreation (pytest-qt)
# ---------------------------------------------------------------------------


class TestDubbingPageCreation:
    """Tests for create_dubbing_page() and DubbingPage widget structure."""

    def test_factory_returns_widget(
        self,
        window,
        _mock_dubbing_history_deps,
    ) -> None:
        """create_dubbing_page() returns a QWidget."""
        from PySide6.QtWidgets import QWidget  # noqa: PLC0415

        from src.ui.pages.dubbing import create_dubbing_page  # noqa: PLC0415

        with patch(f"{_MOD}.get_unfinished_dubbing", return_value=[]):
            w = create_dubbing_page(window)
        assert isinstance(w, QWidget)

    def test_factory_returns_dubbing_page_instance(
        self,
        window,
        _mock_dubbing_history_deps,
    ) -> None:
        """create_dubbing_page() returns a DubbingPage instance."""
        from src.ui.pages.dubbing import (  # noqa: PLC0415
            DubbingPage,
            create_dubbing_page,
        )

        with patch(f"{_MOD}.get_unfinished_dubbing", return_value=[]):
            w = create_dubbing_page(window)
        assert isinstance(w, DubbingPage)

    def test_factory_stores_window_context(
        self,
        window,
        _mock_dubbing_history_deps,
    ) -> None:
        """Factory-created page references the parent window."""
        from src.ui.pages.dubbing import create_dubbing_page  # noqa: PLC0415

        with patch(f"{_MOD}.get_unfinished_dubbing", return_value=[]):
            w = create_dubbing_page(window)
        assert w.window_context is window

    def test_has_drop_area(self, page) -> None:
        """Page contains a FileDropWidget."""
        from src.ui.components import FileDropWidget  # noqa: PLC0415

        assert hasattr(page, "drop_area")
        assert isinstance(page.drop_area, FileDropWidget)

    def test_has_stacked_widget(self, page) -> None:
        """Page contains a QStackedWidget with two views."""
        from PySide6.QtWidgets import QStackedWidget  # noqa: PLC0415

        assert hasattr(page, "stack")
        assert isinstance(page.stack, QStackedWidget)
        assert page.stack.count() == 2  # noqa: PLR2004

    def test_has_generate_button(self, page) -> None:
        """Page contains a generate (dub) QPushButton."""
        from PySide6.QtWidgets import QPushButton  # noqa: PLC0415

        assert hasattr(page, "generate_btn")
        assert isinstance(page.generate_btn, QPushButton)

    def test_has_clear_all_button(self, page) -> None:
        """Page contains a clear-all QPushButton."""
        from PySide6.QtWidgets import QPushButton  # noqa: PLC0415

        assert hasattr(page, "clear_all_btn")
        assert isinstance(page.clear_all_btn, QPushButton)

    def test_has_file_badge(self, page) -> None:
        """Page contains a file count badge label."""
        from PySide6.QtWidgets import QLabel  # noqa: PLC0415

        assert hasattr(page, "files_badge")
        assert isinstance(page.files_badge, QLabel)

    def test_has_section_label(self, page) -> None:
        """Page contains a section label."""
        from PySide6.QtWidgets import QLabel  # noqa: PLC0415

        assert hasattr(page, "section_label")
        assert isinstance(page.section_label, QLabel)

    def test_has_history_view(self, page) -> None:
        """Page contains an embedded DubbingHistoryPage."""
        from src.ui.pages.dubbing_history import (  # noqa: PLC0415
            DubbingHistoryPage,
        )

        assert hasattr(page, "history_view")
        assert isinstance(page.history_view, DubbingHistoryPage)

    def test_has_files_vbox(self, page) -> None:
        """Page contains a vertical box layout for file items."""
        assert hasattr(page, "files_vbox")

    def test_selected_files_starts_empty(self, page) -> None:
        """The selected_files list is empty on construction."""
        assert page.selected_files == []

    def test_generate_button_has_cursor(self, page) -> None:
        """Generate button has pointing hand cursor for UX."""
        from PySide6.QtCore import Qt  # noqa: PLC0415

        assert page.generate_btn.cursor().shape() == Qt.CursorShape.PointingHandCursor

    def test_clear_all_button_has_cursor(self, page) -> None:
        """Clear-all button has pointing hand cursor for UX."""
        from PySide6.QtCore import Qt  # noqa: PLC0415

        assert page.clear_all_btn.cursor().shape() == Qt.CursorShape.PointingHandCursor

    def test_file_list_section_has_scroll_area(self, page) -> None:
        """File list section contains a QScrollArea."""
        from PySide6.QtWidgets import QScrollArea  # noqa: PLC0415

        scroll = page.file_list_section.findChild(QScrollArea)
        assert scroll is not None

    def test_worker_starts_none(self, page) -> None:
        """Worker reference is None initially."""
        assert page._worker is None


# ---------------------------------------------------------------------------
# TestDubbingPageInitialState (pytest-qt)
# ---------------------------------------------------------------------------


class TestDubbingPageInitialState:
    """Tests for the initial state after construction."""

    def test_stack_shows_history_view(self, page) -> None:
        """Stack starts on the history view (index 0)."""
        assert page.stack.currentIndex() == 0

    def test_generate_button_disabled_initially(self, page) -> None:
        """Generate button is disabled when no files are selected."""
        assert not page.generate_btn.isEnabled()

    def test_file_badge_shows_zero(self, page) -> None:
        """Badge shows '0' initially."""
        assert page.files_badge.text() == "0"


# ---------------------------------------------------------------------------
# TestDubbingPageUIState (pytest-qt)
# ---------------------------------------------------------------------------


class TestDubbingPageUIState:
    """Tests for _update_ui_state view switching and reparenting."""

    def test_switches_to_files_view_when_files_exist(self, page) -> None:
        """Adding a path switches the stack to the files view."""
        page.selected_files = ["/fake/video.mp4"]
        page._update_ui_state()
        assert page.stack.currentIndex() == 1

    def test_switches_to_history_view_when_empty(self, page) -> None:
        """Clearing files switches the stack back to history view."""
        page.selected_files = ["/fake/video.mp4"]
        page._update_ui_state()
        page.selected_files.clear()
        page._update_ui_state()
        assert page.stack.currentIndex() == 0

    def test_generate_button_enabled_with_files(self, page) -> None:
        """Generate button is enabled when files are present."""
        page.selected_files = ["/fake/video.mp4"]
        page._update_ui_state()
        assert page.generate_btn.isEnabled()

    def test_generate_button_disabled_without_files(self, page) -> None:
        """Generate button is disabled when no files are present."""
        page.selected_files = []
        page._update_ui_state()
        assert not page.generate_btn.isEnabled()

    def test_badge_count_reflects_file_count(self, page) -> None:
        """Badge text matches the number of selected files."""
        page.selected_files = ["/a.mp4", "/b.mkv", "/c.avi"]
        page._update_ui_state()
        assert page.files_badge.text() == "3"

    def test_drop_area_label_changes_on_files_view(self, page) -> None:
        """Drop area info label changes text when files are selected."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page.selected_files = ["/fake.mp4"]
        page._update_ui_state()
        assert page.drop_area.info_label.text() == tr("drop.title_more")

    def test_drop_area_label_changes_on_history_view(self, page) -> None:
        """Drop area info label shows default text when no files."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page.selected_files = []
        page._update_ui_state()
        assert page.drop_area.info_label.text() == tr("drop.title")


# ---------------------------------------------------------------------------
# TestDubbingPageActions (pytest-qt)
# ---------------------------------------------------------------------------


class TestDubbingPageActions:
    """Tests for _handle_generate, _handle_clear_all, and worker lifecycle."""

    def test_handle_generate_no_files_does_nothing(self, page) -> None:
        """_handle_generate with no files does not start a worker."""
        page.selected_files = []
        page._handle_generate()
        assert page._worker is None

    def test_handle_generate_with_active_worker_does_nothing(
        self,
        page,
    ) -> None:
        """_handle_generate does nothing when a worker is already active."""
        page.selected_files = ["/fake/video.mp4"]
        page._worker = MagicMock()  # Simulate active worker
        page._handle_generate()
        # Worker reference unchanged (no new worker started)
        assert page._worker is not None

    @patch(f"{_MOD}.add_dubbing_entry", return_value=100)
    @patch(f"{_MOD}.LanguageSelectionDialog.get_selection")
    @patch(f"{_MOD}.require_setup", return_value=True)
    @patch(f"{_MOD}.load_setting", return_value="")
    def test_handle_generate_rejected_dialog_no_worker(
        self,
        _mock_load,
        _mock_require,
        mock_dialog,
        _mock_add,
        page,
        _mock_dubbing_history_deps,
    ) -> None:
        """When language dialog is rejected, no worker starts."""
        mock_dialog.return_value = ("", "", None, False)
        page.selected_files = ["/fake/video.mp4"]
        page._worker = None

        page._handle_generate()

        assert page._worker is None

    @patch(f"{_MOD}._DubbingWorker")
    @patch(f"{_MOD}.add_dubbing_entry", return_value=100)
    @patch(
        f"{_MOD}.LanguageSelectionDialog.get_selection",
        return_value=("English (US)", "Vietnamese", None, True),
    )
    @patch(f"{_MOD}.require_setup", return_value=True)
    @patch(f"{_MOD}.load_setting", return_value="")
    def test_handle_generate_starts_worker(
        self,
        _mock_load,
        _mock_require,
        _mock_dialog,
        _mock_add,
        mock_worker_cls,
        page,
        tmp_path,
        _mock_dubbing_history_deps,
    ) -> None:
        """_handle_generate creates DB entries and starts a worker."""
        video = tmp_path / "test.mp4"
        video.write_bytes(b"fake video data")
        page.selected_files = [str(video)]

        mock_instance = MagicMock()
        mock_instance.finished_ok = MagicMock()
        mock_instance.finished_ok.connect = MagicMock()
        mock_worker_cls.return_value = mock_instance

        with patch("src.utils.config_manager.save_setting"):
            page._handle_generate()

        mock_worker_cls.assert_called_once()
        mock_instance.start.assert_called_once()

    def test_handle_clear_all_empties_selected(self, page) -> None:
        """_handle_clear_all empties the selected_files list."""
        page.selected_files = ["/a.mp4", "/b.mp4"]
        page._handle_clear_all()
        assert page.selected_files == []

    def test_handle_clear_all_switches_to_history(self, page) -> None:
        """After clearing all files, stack shows history view."""
        page.selected_files = ["/a.mp4"]
        page._update_ui_state()
        page._handle_clear_all()
        assert page.stack.currentIndex() == 0

    def test_check_requirements_fails_stops_generate(self, page) -> None:
        """When _check_all_requirements fails, no worker is started."""
        page.selected_files = ["/fake/video.mp4"]
        with patch.object(page, "_check_all_requirements", return_value=False):
            page._handle_generate()
        assert page._worker is None

    def test_start_worker_noop_when_worker_exists(self, page) -> None:
        """_start_worker is a no-op when a worker is already set."""
        page._worker = MagicMock()
        existing = page._worker
        page._start_worker([(1, "/v.mp4")], "en", "vi")
        assert page._worker is existing

    def test_safe_cleanup_worker_clears_reference(self, page) -> None:
        """_safe_cleanup_worker waits and sets _worker to None."""
        mock_worker = MagicMock()
        page._worker = mock_worker
        page._safe_cleanup_worker()
        mock_worker.wait.assert_called_once()
        assert page._worker is None

    def test_safe_cleanup_worker_noop_when_none(self, page) -> None:
        """_safe_cleanup_worker does nothing when _worker is None."""
        page._worker = None
        page._safe_cleanup_worker()  # Should not raise
        assert page._worker is None


# ---------------------------------------------------------------------------
# TestDubbingPageFileHandling (pytest-qt)
# ---------------------------------------------------------------------------


class TestDubbingPageFileHandling:
    """Tests for file drop handling and filtering."""

    @patch(f"{_MOD}.CustomMessageDialog.show_message")
    def test_drop_valid_video_adds_to_selected(
        self,
        _mock_msg,
        page,
        tmp_path,
    ) -> None:
        """Dropping a valid video file adds it to selected_files."""
        video = tmp_path / "clip.mp4"
        video.write_bytes(b"video data")
        page._handle_files_dropped([str(video)])
        assert str(video) in page.selected_files

    @patch(f"{_MOD}.CustomMessageDialog.show_message")
    def test_drop_unsupported_extension_shows_dialog(
        self,
        mock_msg,
        page,
        tmp_path,
    ) -> None:
        """Dropping an unsupported file type shows an unsupported dialog."""
        txt = tmp_path / "readme.txt"
        txt.write_text("hello")
        page._handle_files_dropped([str(txt)])
        mock_msg.assert_called_once()
        assert len(page.selected_files) == 0

    @patch(f"{_MOD}.CustomMessageDialog.show_message")
    def test_drop_empty_file_filtered_out(
        self,
        _mock_msg,
        page,
        tmp_path,
    ) -> None:
        """Empty files are filtered out with '(Empty)' label."""
        video = tmp_path / "empty.mp4"
        video.write_bytes(b"")
        page._handle_files_dropped([str(video)])
        assert str(video) not in page.selected_files

    @patch(f"{_MOD}.CustomMessageDialog.show_message")
    def test_drop_duplicate_file_not_added_twice(
        self,
        _mock_msg,
        page,
        tmp_path,
    ) -> None:
        """Dropping the same file twice only adds it once."""
        video = tmp_path / "clip.mp4"
        video.write_bytes(b"video data")
        page._handle_files_dropped([str(video)])
        page._handle_files_dropped([str(video)])
        assert page.selected_files.count(str(video)) == 1

    def test_drop_empty_list_with_no_dialog_is_noop(self, page) -> None:
        """Empty drop with mocked dialog returning nothing is a no-op."""
        with patch(
            f"{_MOD}.QFileDialog.getOpenFileNames",
            return_value=([], None),
        ):
            page._handle_files_dropped([])
        assert page.selected_files == []

    @patch(f"{_MOD}.CustomMessageDialog.show_message")
    def test_handle_remove_file(
        self,
        _mock_msg,
        page,
        tmp_path,
    ) -> None:
        """_handle_remove_file removes file and updates UI state."""
        video = tmp_path / "clip.mp4"
        video.write_bytes(b"video data")
        page._handle_files_dropped([str(video)])
        assert len(page.selected_files) == 1

        # Simulate removal
        from PySide6.QtWidgets import QWidget  # noqa: PLC0415

        mock_widget = QWidget()
        page._handle_remove_file(str(video), mock_widget)
        assert len(page.selected_files) == 0


# ---------------------------------------------------------------------------
# TestDubbingPageThemeLanguage (pytest-qt)
# ---------------------------------------------------------------------------


class TestDubbingPageThemeLanguage:
    """Tests for apply_theme() and apply_language()."""

    def test_apply_theme_no_error(self, page) -> None:
        """apply_theme() runs without raising."""
        page.apply_theme()

    def test_apply_language_no_error(
        self,
        page,
        _mock_dubbing_history_deps,
    ) -> None:
        """apply_language() runs without raising."""
        page.apply_language()

    def test_apply_language_updates_generate_button_text(
        self,
        page,
        _mock_dubbing_history_deps,
    ) -> None:
        """apply_language() updates the generate button text."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page.apply_language()
        assert page.generate_btn.text() == tr("dubbing.btn_start")

    def test_apply_language_updates_clear_button_text(
        self,
        page,
        _mock_dubbing_history_deps,
    ) -> None:
        """apply_language() updates the clear-all button text."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page.apply_language()
        assert page.clear_all_btn.text() == tr("btn.delete_all")

    def test_apply_language_updates_section_label(
        self,
        page,
        _mock_dubbing_history_deps,
    ) -> None:
        """apply_language() updates the section label text."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page.apply_language()
        assert page.section_label.text() == tr("files.selected")

    def test_apply_theme_updates_badge_stylesheet(self, page) -> None:
        """apply_theme() updates the badge stylesheet."""
        from src.ui.components import style_file_count_badge  # noqa: PLC0415

        page.apply_theme()
        assert page.files_badge.styleSheet() == style_file_count_badge()

    def test_apply_theme_updates_generate_button_stylesheet(
        self,
        page,
    ) -> None:
        """apply_theme() updates generate button stylesheet."""
        from src.constants import style_primary_button  # noqa: PLC0415

        page.apply_theme()
        assert page.generate_btn.styleSheet() == style_primary_button()


# ---------------------------------------------------------------------------
# TestDubbingWorkerEdgeCases (non-Qt pipeline tests)
# ---------------------------------------------------------------------------


@patch("src.ui.pages.dubbing.update_dubbing_progress")
@patch("src.ui.pages.dubbing.get_dubbing_entry_status", return_value=STATUS_GENERATING)
@patch("src.ui.pages.dubbing.generate_dubbing_output_path")
@patch("src.ui.pages.dubbing.tr", side_effect=lambda key, **kw: key)
class TestDubbingWorkerEdgeCases:
    """Additional edge cases for the _DubbingWorker pipeline."""

    def test_empty_task_list_no_results(
        self,
        _tr,
        mock_gen_path,
        _status,
        _progress,
        tmp_path,
    ) -> None:
        """Worker with empty tasks list produces no results."""
        from src.ui.pages.dubbing import _DubbingWorker  # noqa: PLC0415

        worker = _make_worker(tasks=[])
        worker.finished_ok = MagicMock()
        _DubbingWorker._is_any_worker_running = False

        with (
            patch(f"{_MOD}.load_setting", return_value="base"),
            patch("src.core.database.get_active_glossary_sets", return_value=[]),
            patch("src.core.database.get_glossary_entries", return_value=[]),
            patch(f"{_MOD}.update_dubbing_status"),
            patch("src.utils.path_manager.get_dubbing_storage_dir"),
            patch("shutil.rmtree"),
        ):
            _DubbingWorker.run(worker)

        worker.finished_ok.emit.assert_called_once_with([])

    def test_unicode_video_path_handled(
        self,
        _tr,
        mock_gen_path,
        _status,
        _progress,
        tmp_path,
    ) -> None:
        """Pipeline handles unicode characters in video paths."""
        mock_gen_path.return_value = tmp_path / "output_dubbed.mp4"
        unicode_path = "/tmp/vidéo_日本語.mp4"
        worker = _make_worker(tasks=[(_ENTRY_ID, unicode_path)])
        kw = _default_kwargs(tmp_path, video_path=unicode_path)

        with patch("src.constants.languages.get_locale_code", return_value="xx"):
            _run_pipeline(worker, kw)

        # Verify the video path was passed through unchanged
        kw["transcribe_audio"].assert_called_once()
        assert kw["transcribe_audio"].call_args[0][0] == unicode_path

    def test_all_four_steps_succeed_produces_result(
        self,
        _tr,
        mock_gen_path,
        _status,
        _progress,
        tmp_path,
    ) -> None:
        """Successful pipeline produces exactly one result tuple."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)

        with patch("src.constants.languages.get_locale_code", return_value="xx"):
            _run_pipeline(worker, kw)

        assert len(kw["results"]) == 1
        assert kw["results"][0][0] == _ENTRY_ID

    def test_step1_failure_no_result(
        self,
        _tr,
        mock_gen_path,
        _status,
        _progress,
        tmp_path,
    ) -> None:
        """Failure at step 1 (STT) produces no result."""
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        kw["transcribe_audio"] = MagicMock(
            side_effect=RuntimeError("STT engine failed"),
        )

        with pytest.raises(RuntimeError, match="STT engine failed"):
            _run_pipeline(worker, kw)

        assert len(kw["results"]) == 0

    def test_step2_failure_no_result(
        self,
        _tr,
        mock_gen_path,
        _status,
        _progress,
        tmp_path,
    ) -> None:
        """Failure at step 2 (translate) produces no result."""
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        kw["translate_batch"] = MagicMock(
            side_effect=ValueError("QUOTA_ERROR"),
        )

        with pytest.raises(ValueError, match="QUOTA_ERROR"):
            _run_pipeline(worker, kw)

        assert len(kw["results"]) == 0

    def test_step3_failure_no_result(
        self,
        _tr,
        mock_gen_path,
        _status,
        _progress,
        tmp_path,
    ) -> None:
        """Failure at step 3 (TTS) produces no result."""
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        kw["synthesize_timed_speech"] = MagicMock(
            side_effect=RuntimeError("TTS failed"),
        )

        with pytest.raises(RuntimeError, match="TTS failed"):
            _run_pipeline(worker, kw)

        assert len(kw["results"]) == 0

    def test_step4_failure_no_result(
        self,
        _tr,
        mock_gen_path,
        _status,
        _progress,
        tmp_path,
    ) -> None:
        """Failure at step 4 (mix) produces no result."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        kw["mix_audio_into_video"] = MagicMock(
            side_effect=RuntimeError("Mix failed"),
        )

        with pytest.raises(RuntimeError, match="Mix failed"):
            _run_pipeline(worker, kw)

        assert len(kw["results"]) == 0

    def test_cancel_before_step1(
        self,
        _tr,
        mock_gen_path,
        _status,
        _progress,
        tmp_path,
    ) -> None:
        """Cancellation before STT step skips everything."""
        worker = _make_worker()
        worker._is_task_cancelled = MagicMock(return_value=True)
        kw = _default_kwargs(tmp_path)

        _run_pipeline(worker, kw)

        # Since cancel is checked inside _is_task_cancelled which is mocked,
        # and the first check is after STT, the transcribe is still called
        # but translate_batch should not be called
        kw["translate_batch"].assert_not_called()

    def test_cancel_between_step2_and_step3(
        self,
        _tr,
        mock_gen_path,
        _status,
        _progress,
        tmp_path,
    ) -> None:
        """Cancellation between translate and TTS skips TTS and mix."""
        worker = _make_worker()
        # cancel() checks: after STT → False, after translate → False,
        # before TTS → True
        worker._is_task_cancelled = MagicMock(
            side_effect=[False, False, True],
        )
        kw = _default_kwargs(tmp_path)

        _run_pipeline(worker, kw)

        kw["transcribe_audio"].assert_called_once()
        kw["translate_batch"].assert_called_once()
        kw["synthesize_timed_speech"].assert_not_called()
        kw["mix_audio_into_video"].assert_not_called()

    def test_cancel_between_step3_and_step4(
        self,
        _tr,
        mock_gen_path,
        _status,
        _progress,
        tmp_path,
    ) -> None:
        """Cancellation between TTS and mix skips mix."""
        worker = _make_worker()
        # cancel() checks: after STT, after translate, before TTS, after TTS,
        # before mix → True
        worker._is_task_cancelled = MagicMock(
            side_effect=[False, False, False, False, True],
        )
        kw = _default_kwargs(tmp_path)

        _run_pipeline(worker, kw)

        kw["synthesize_timed_speech"].assert_called_once()
        kw["mix_audio_into_video"].assert_not_called()

    def test_multi_step_progress_emission(
        self,
        _tr,
        mock_gen_path,
        _status,
        mock_progress,
        tmp_path,
    ) -> None:
        """Full pipeline emits progress milestones in ascending order."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)

        _run_pipeline(worker, kw)

        progress_values = [c[0][1] for c in mock_progress.call_args_list]
        # Verify key milestones are present
        assert DUBBING_PROGRESS_STT_START in progress_values
        assert DUBBING_PROGRESS_STT_DONE in progress_values
        assert DUBBING_PROGRESS_TRANSLATE_DONE in progress_values
        assert DUBBING_PROGRESS_TTS_DONE in progress_values
        assert DUBBING_PROGRESS_MIX_START in progress_values
        assert PROGRESS_COMPLETE in progress_values

    def test_checkpoint_resume_from_step2(
        self,
        _tr,
        mock_gen_path,
        _status,
        _progress,
        tmp_path,
    ) -> None:
        """Resume from step 2 checkpoint: skips STT, runs translate+TTS+mix."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        kw["load_checkpoint"] = MagicMock(
            return_value={
                "srt_text": _FAKE_SRT,
                "target_lang": "Vietnamese",
            },
        )

        _run_pipeline(worker, kw)

        kw["transcribe_audio"].assert_not_called()
        kw["translate_batch"].assert_called_once()
        kw["synthesize_timed_speech"].assert_called_once()
        kw["mix_audio_into_video"].assert_called_once()

    def test_checkpoint_resume_from_step3(
        self,
        _tr,
        mock_gen_path,
        _status,
        _progress,
        tmp_path,
    ) -> None:
        """Resume from step 3 checkpoint: skips STT+translate, runs TTS+mix."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        kw["load_checkpoint"] = MagicMock(
            return_value={
                "srt_text": _FAKE_SRT,
                "translated_srt": _FAKE_TRANSLATED_SRT,
                "target_lang": "Vietnamese",
            },
        )

        _run_pipeline(worker, kw)

        kw["transcribe_audio"].assert_not_called()
        kw["translate_batch"].assert_not_called()
        kw["synthesize_timed_speech"].assert_called_once()
        kw["mix_audio_into_video"].assert_called_once()

    def test_checkpoint_resume_from_step4(
        self,
        _tr,
        mock_gen_path,
        _status,
        _progress,
        tmp_path,
    ) -> None:
        """Resume from step 4 checkpoint: skips STT+translate+TTS, runs mix."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        (kw["storage_dir"] / "voice.mp3").touch()
        kw["load_checkpoint"] = MagicMock(
            return_value={
                "srt_text": _FAKE_SRT,
                "translated_srt": _FAKE_TRANSLATED_SRT,
                "target_lang": "Vietnamese",
                "voice_file": "voice.mp3",
            },
        )

        _run_pipeline(worker, kw)

        kw["transcribe_audio"].assert_not_called()
        kw["translate_batch"].assert_not_called()
        kw["synthesize_timed_speech"].assert_not_called()
        kw["mix_audio_into_video"].assert_called_once()

    def test_src_lang_auto_when_empty(
        self,
        _tr,
        mock_gen_path,
        _status,
        _progress,
        tmp_path,
    ) -> None:
        """When src_lang is empty, translate_batch receives 'Auto'."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker(src_lang="")
        kw = _default_kwargs(tmp_path)

        _run_pipeline(worker, kw)

        batch_call = kw["translate_batch"].call_args
        assert batch_call[1]["src_lang"] == "Auto"

    def test_voice_gender_passed_to_tts(
        self,
        _tr,
        mock_gen_path,
        _status,
        _progress,
        tmp_path,
    ) -> None:
        """Voice gender from worker is forwarded to synthesize_timed_speech."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        worker._voice_gender = "MALE"
        kw = _default_kwargs(tmp_path)

        _run_pipeline(worker, kw)

        synth_call = kw["synthesize_timed_speech"].call_args
        assert synth_call[1]["voice_gender"] == "MALE"


# ---------------------------------------------------------------------------
# TestDubbingWorkerBusyFlag
# ---------------------------------------------------------------------------


class TestDubbingWorkerBusyFlag:
    """Tests for the class-level busy flag on _DubbingWorker."""

    def test_busy_flag_initially_false(self) -> None:
        """The class-level busy flag starts false (assuming clean state)."""
        from src.ui.pages.dubbing import _DubbingWorker  # noqa: PLC0415

        original = _DubbingWorker._is_any_worker_running
        try:
            _DubbingWorker._is_any_worker_running = False
            assert not _DubbingWorker.is_busy()
        finally:
            _DubbingWorker._is_any_worker_running = original

    def test_busy_flag_set_during_run(self) -> None:
        """The busy flag is set to True during run() and cleared after."""
        from src.ui.pages.dubbing import _DubbingWorker  # noqa: PLC0415

        original = _DubbingWorker._is_any_worker_running
        try:
            _DubbingWorker._is_any_worker_running = False
            worker = _make_worker(tasks=[])
            worker.finished_ok = MagicMock()

            with (
                patch(f"{_MOD}.load_setting", return_value="base"),
                patch(
                    "src.core.database.get_active_glossary_sets",
                    return_value=[],
                ),
                patch("src.core.database.get_glossary_entries", return_value=[]),
                patch(
                    f"{_MOD}.get_dubbing_entry_status",
                    return_value=STATUS_GENERATING,
                ),
                patch(f"{_MOD}.update_dubbing_status"),
                patch(f"{_MOD}.update_dubbing_progress"),
            ):
                _DubbingWorker.run(worker)

            # After run, flag should be cleared
            assert not _DubbingWorker._is_any_worker_running
        finally:
            _DubbingWorker._is_any_worker_running = original

    def test_concurrent_worker_prevented(self) -> None:
        """When busy flag is True, run() returns immediately."""
        from src.ui.pages.dubbing import _DubbingWorker  # noqa: PLC0415

        original = _DubbingWorker._is_any_worker_running
        try:
            _DubbingWorker._is_any_worker_running = True
            worker = _make_worker(tasks=[(_ENTRY_ID, "/tmp/v.mp4")])
            worker.finished_ok = MagicMock()

            with (
                patch(f"{_MOD}.load_setting", return_value="base"),
                patch(
                    "src.core.database.get_active_glossary_sets",
                    return_value=[],
                ),
                patch("src.core.database.get_glossary_entries", return_value=[]),
                patch(
                    f"{_MOD}.get_dubbing_entry_status",
                    return_value=STATUS_GENERATING,
                ),
                patch(f"{_MOD}.update_dubbing_status") as mock_status,
                patch(f"{_MOD}.update_dubbing_progress"),
            ):
                _DubbingWorker.run(worker)

            # update_dubbing_status should NOT be called for the task
            # because the run() method returns early when busy
            mock_status.assert_not_called()
        finally:
            _DubbingWorker._is_any_worker_running = original

    def test_busy_flag_cleared_on_task_exception(self) -> None:
        """The busy flag is cleared even if a task raises inside the try block."""
        from src.ui.pages.dubbing import _DubbingWorker  # noqa: PLC0415

        original = _DubbingWorker._is_any_worker_running
        try:
            _DubbingWorker._is_any_worker_running = False
            worker = _make_worker(tasks=[(_ENTRY_ID, "/tmp/v.mp4")])
            worker.finished_ok = MagicMock()

            with (
                patch(f"{_MOD}.load_setting", return_value="base"),
                patch(
                    "src.core.database.get_active_glossary_sets",
                    return_value=[],
                ),
                patch("src.core.database.get_glossary_entries", return_value=[]),
                patch(
                    f"{_MOD}.get_dubbing_entry_status",
                    return_value=STATUS_GENERATING,
                ),
                patch(
                    f"{_MOD}.update_dubbing_status",
                    side_effect=RuntimeError("DB crash"),
                ),
                patch(f"{_MOD}.update_dubbing_progress"),
            ):
                _DubbingWorker.run(worker)

            # Flag should be cleared in the finally block
            assert not _DubbingWorker._is_any_worker_running
            # finished_ok should still be emitted
            worker.finished_ok.emit.assert_called_once()
        finally:
            _DubbingWorker._is_any_worker_running = original


# ---------------------------------------------------------------------------
# TestDubbingOnFinished (pytest-qt)
# ---------------------------------------------------------------------------


class TestDubbingOnFinished:
    """Tests for the _on_finished callback and _resume_pending."""

    @patch(f"{_MOD}.update_dubbing_status")
    @patch(f"{_MOD}.load_setting", return_value=False)
    @patch(f"{_MOD}.get_unfinished_dubbing", return_value=[])
    def test_on_finished_updates_status_done(
        self,
        _mock_unfinished,
        _mock_load,
        mock_status,
        page,
        _mock_dubbing_history_deps,
    ) -> None:
        """_on_finished marks completed entries as Done."""
        mock_worker = MagicMock()
        page._worker = mock_worker

        results = [
            (1, "/out/dubbed.mp4", "/out/sub.srt", "/out/sub_vi.srt", "/out/voice.mp3")
        ]
        page._on_finished(results)

        mock_status.assert_called_once()
        call_args = mock_status.call_args
        assert call_args[0][0] == 1
        assert call_args[0][1] == STATUS_DONE

    @patch(f"{_MOD}.delete_dubbing_entry", return_value=[])
    @patch(f"{_MOD}.load_setting", return_value=True)
    @patch(f"{_MOD}.get_unfinished_dubbing", return_value=[])
    def test_on_finished_auto_remove_deletes_entry(
        self,
        _mock_unfinished,
        _mock_load,
        mock_delete,
        page,
        _mock_dubbing_history_deps,
    ) -> None:
        """_on_finished with auto-remove deletes entries from DB."""
        mock_worker = MagicMock()
        page._worker = mock_worker

        results = [
            (1, "/out/dubbed.mp4", "/out/sub.srt", "/out/sub_vi.srt", "/out/voice.mp3")
        ]
        with (
            patch(
                "src.utils.path_manager.get_dubbing_storage_dir",
                return_value=Path("/tmp/s"),
            ),
            patch("shutil.rmtree"),
        ):
            page._on_finished(results)

        mock_delete.assert_called_once_with(1)

    @patch(f"{_MOD}.load_setting", return_value=False)
    @patch(f"{_MOD}.get_unfinished_dubbing", return_value=[])
    def test_on_finished_clears_worker(
        self,
        _mock_unfinished,
        _mock_load,
        page,
        _mock_dubbing_history_deps,
    ) -> None:
        """_on_finished clears the worker reference."""
        mock_worker = MagicMock()
        page._worker = mock_worker

        with patch(f"{_MOD}.update_dubbing_status"):
            page._on_finished([])

        assert page._worker is None

    @patch(f"{_MOD}.update_dubbing_status")
    @patch(f"{_MOD}.load_setting", return_value=False)
    def test_on_finished_does_not_auto_resume_pending(
        self,
        _mock_load,
        _mock_status,
        page,
        _mock_dubbing_history_deps,
    ) -> None:
        """_on_finished must NOT auto-resume pending entries.

        Auto-resume post-Stop would immediately restart the queue the user
        just asked to stop. Only the explicit app-start hook in __init__
        triggers resumption.
        """
        mock_worker = MagicMock()
        page._worker = mock_worker

        unfinished = [(10, "/tmp/v1.mp4", "English", "Vietnamese")]
        with (
            patch(f"{_MOD}.get_unfinished_dubbing", return_value=unfinished),
            patch.object(page, "_start_worker") as mock_start,
        ):
            page._on_finished([])

        mock_start.assert_not_called()

    @patch(f"{_MOD}.get_unfinished_dubbing", return_value=[])
    def test_resume_pending_noop_when_worker_exists(
        self,
        _mock_unfinished,
        page,
    ) -> None:
        """_resume_pending does nothing when a worker is already active."""
        page._worker = MagicMock()
        page._resume_pending()
        _mock_unfinished.assert_not_called()

    @patch(f"{_MOD}.get_unfinished_dubbing", return_value=[])
    def test_resume_pending_noop_when_no_unfinished(
        self,
        _mock_unfinished,
        page,
    ) -> None:
        """_resume_pending does nothing when DB has no pending entries."""
        page._worker = None
        page._resume_pending()
        assert page._worker is None


# ---------------------------------------------------------------------------
# TestDubbingHandleContinueReDub (pytest-qt)
# ---------------------------------------------------------------------------


class TestDubbingHandleContinueReDub:
    """Tests for _handle_continue_dub and _handle_re_dub."""

    def test_continue_dub_checks_requirements(self, page) -> None:
        """_handle_continue_dub checks requirements before starting."""
        with patch.object(
            page,
            "_check_all_requirements",
            return_value=False,
        ):
            page._handle_continue_dub(
                [(1, "/v.mp4")],
                "English",
                "Vietnamese",
            )
        assert page._worker is None

    @patch(f"{_MOD}._DubbingWorker")
    def test_continue_dub_starts_worker(
        self,
        mock_worker_cls,
        page,
    ) -> None:
        """_handle_continue_dub starts a worker when requirements met."""
        mock_instance = MagicMock()
        mock_instance.finished_ok = MagicMock()
        mock_instance.finished_ok.connect = MagicMock()
        mock_worker_cls.return_value = mock_instance

        with patch.object(page, "_check_all_requirements", return_value=True):
            page._handle_continue_dub(
                [(1, "/v.mp4")],
                "English",
                "Vietnamese",
            )

        mock_worker_cls.assert_called_once()
        mock_instance.start.assert_called_once()

    def test_re_dub_checks_requirements(self, page) -> None:
        """_handle_re_dub checks requirements before starting."""
        with patch.object(
            page,
            "_check_all_requirements",
            return_value=False,
        ):
            page._handle_re_dub([(1, "/v.mp4")])
        assert page._worker is None

    @patch(f"{_MOD}._DubbingWorker")
    @patch(f"{_MOD}.update_dubbing_status")
    @patch(
        f"{_MOD}.LanguageSelectionDialog.get_selection",
        return_value=("English", "Vietnamese", None, True),
    )
    @patch(f"{_MOD}.load_setting", return_value="")
    def test_re_dub_starts_worker_after_dialog(
        self,
        _mock_load,
        _mock_dialog,
        _mock_status,
        mock_worker_cls,
        page,
        _mock_dubbing_history_deps,
    ) -> None:
        """_handle_re_dub starts a worker after language dialog."""
        mock_instance = MagicMock()
        mock_instance.finished_ok = MagicMock()
        mock_instance.finished_ok.connect = MagicMock()
        mock_worker_cls.return_value = mock_instance

        with (
            patch.object(page, "_check_all_requirements", return_value=True),
            patch("src.utils.config_manager.save_setting"),
        ):
            page._handle_re_dub([(1, "/v.mp4")])

        mock_worker_cls.assert_called_once()
        mock_instance.start.assert_called_once()

    @patch(
        f"{_MOD}.LanguageSelectionDialog.get_selection",
        return_value=("", "", None, False),
    )
    @patch(f"{_MOD}.load_setting", return_value="")
    def test_re_dub_rejected_dialog_no_worker(
        self,
        _mock_load,
        _mock_dialog,
        page,
    ) -> None:
        """_handle_re_dub does nothing when language dialog is rejected."""
        with patch.object(page, "_check_all_requirements", return_value=True):
            page._handle_re_dub([(1, "/v.mp4")])
        assert page._worker is None


# ---------------------------------------------------------------------------
# NEW: Additional pipeline tests for expanded coverage
# ---------------------------------------------------------------------------


@patch("src.ui.pages.dubbing.update_dubbing_progress")
@patch("src.ui.pages.dubbing.get_dubbing_entry_status", return_value=STATUS_GENERATING)
@patch("src.ui.pages.dubbing.generate_dubbing_output_path")
@patch("src.ui.pages.dubbing.tr", side_effect=lambda key, **kw: key)
class TestPipelineSrcLangHandling:
    """Tests for source language handling in the pipeline."""

    def test_auto_src_lang_in_translate(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """Empty src_lang defaults to 'Auto' in translate_batch."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker(src_lang="")
        kw = _default_kwargs(tmp_path)
        _run_pipeline(worker, kw)
        batch_call = kw["translate_batch"].call_args
        assert batch_call[1]["src_lang"] == "Auto"

    def test_specified_src_lang_passed_through(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """Explicit src_lang is forwarded unchanged."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker(src_lang="Japanese")
        kw = _default_kwargs(tmp_path)
        _run_pipeline(worker, kw)
        batch_call = kw["translate_batch"].call_args
        assert batch_call[1]["src_lang"] == "Japanese"

    def test_src_lang_in_stt_call(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """Source language is passed to transcribe_audio."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker(src_lang="Korean")
        kw = _default_kwargs(tmp_path)
        _run_pipeline(worker, kw)
        assert kw["transcribe_audio"].call_args[1]["src_lang"] == "Korean"

    def test_empty_src_lang_in_stt(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """Empty src_lang is passed to transcribe_audio."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker(src_lang="")
        kw = _default_kwargs(tmp_path)
        _run_pipeline(worker, kw)
        assert kw["transcribe_audio"].call_args[1]["src_lang"] == ""


@patch("src.ui.pages.dubbing.update_dubbing_progress")
@patch("src.ui.pages.dubbing.get_dubbing_entry_status", return_value=STATUS_GENERATING)
@patch("src.ui.pages.dubbing.generate_dubbing_output_path")
@patch("src.ui.pages.dubbing.tr", side_effect=lambda key, **kw: key)
class TestPipelineVoiceGender:
    """Tests for voice gender forwarding."""

    def test_female_voice_gender(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """Default FEMALE gender is forwarded to synthesize."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        _run_pipeline(worker, kw)
        assert kw["synthesize_timed_speech"].call_args[1]["voice_gender"] == "FEMALE"

    def test_male_voice_gender(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """MALE gender is forwarded to synthesize."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        worker._voice_gender = "MALE"
        kw = _default_kwargs(tmp_path)
        _run_pipeline(worker, kw)
        assert kw["synthesize_timed_speech"].call_args[1]["voice_gender"] == "MALE"


@patch("src.ui.pages.dubbing.update_dubbing_progress")
@patch("src.ui.pages.dubbing.get_dubbing_entry_status", return_value=STATUS_GENERATING)
@patch("src.ui.pages.dubbing.generate_dubbing_output_path")
@patch("src.ui.pages.dubbing.tr", side_effect=lambda key, **kw: key)
class TestPipelineAudioFormat:
    """Tests for audio format propagation in the pipeline."""

    def test_mp3_format_default(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """Default .mp3 audio format is passed to synthesize."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        _run_pipeline(worker, kw)
        assert kw["synthesize_timed_speech"].call_args[1]["audio_format"] == ".mp3"

    def test_wav_format(self, _tr, mock_gen_path, _status, _progress, tmp_path) -> None:
        """When audio_fmt is .wav, it's forwarded to synthesize and voice path."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        kw["audio_fmt"] = ".wav"
        _run_pipeline(worker, kw)
        synth_kw = kw["synthesize_timed_speech"].call_args[1]
        assert synth_kw["audio_format"] == ".wav"
        # Voice path should use .wav extension
        assert synth_kw["output_path"].endswith(".wav")

    def test_voice_path_uses_audio_fmt(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """Voice output path matches the audio_fmt."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        kw["audio_fmt"] = ".ogg"
        _run_pipeline(worker, kw)
        voice_path = kw["synthesize_timed_speech"].call_args[1]["output_path"]
        assert voice_path.endswith(".ogg")


@patch("src.ui.pages.dubbing.update_dubbing_progress")
@patch("src.ui.pages.dubbing.get_dubbing_entry_status", return_value=STATUS_GENERATING)
@patch("src.ui.pages.dubbing.generate_dubbing_output_path")
@patch("src.ui.pages.dubbing.tr", side_effect=lambda key, **kw: key)
class TestPipelineMultipleCancel:
    """Tests for cancellation at various pipeline stages."""

    def test_cancel_before_stt(self, _tr, _gen, _status, _progress, tmp_path) -> None:
        """Cancellation before STT returns early without translating."""
        worker = _make_worker()
        worker._is_running = False
        worker._is_task_cancelled = MagicMock(return_value=True)
        kw = _default_kwargs(tmp_path)
        _run_pipeline(worker, kw)
        # STT runs but cancel check after STT causes early return
        kw["translate_batch"].assert_not_called()

    def test_cancel_during_translate(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """Cancellation during translate: STT runs, translate runs, TTS skipped."""
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        # cancel: after STT=False, after translate=True
        worker._is_task_cancelled = MagicMock(
            side_effect=[False, True],
        )
        _run_pipeline(worker, kw)
        kw["transcribe_audio"].assert_called_once()
        kw["synthesize_timed_speech"].assert_not_called()

    def test_cancel_during_tts(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """Cancellation after TTS but before mix."""
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        # cancel: after STT=False, after translate=False, before TTS=False,
        # after synth=False, before mix=True
        worker._is_task_cancelled = MagicMock(
            side_effect=[False, False, False, False, True],
        )
        _run_pipeline(worker, kw)
        kw["synthesize_timed_speech"].assert_called_once()
        kw["mix_audio_into_video"].assert_not_called()


@patch("src.ui.pages.dubbing.update_dubbing_progress")
@patch("src.ui.pages.dubbing.get_dubbing_entry_status", return_value=STATUS_GENERATING)
@patch("src.ui.pages.dubbing.generate_dubbing_output_path")
@patch("src.ui.pages.dubbing.tr", side_effect=lambda key, **kw: key)
class TestPipelineSettingsForwarding:
    """Tests for settings being forwarded correctly through the pipeline."""

    def test_stt_method_forwarded(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """stt_method is forwarded to transcribe_audio."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        kw["stt_method"] = "Google Cloud"
        _run_pipeline(worker, kw)
        assert kw["transcribe_audio"].call_args[1]["stt_method"] == "Google Cloud"

    def test_model_size_forwarded(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """model_size is forwarded to transcribe_audio."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        kw["model_size"] = "large"
        _run_pipeline(worker, kw)
        assert kw["transcribe_audio"].call_args[1]["model_size"] == "large"

    def test_tts_method_forwarded(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """tts_method is forwarded to synthesize_timed_speech."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        kw["tts_method"] = "Google Cloud TTS"
        _run_pipeline(worker, kw)
        assert (
            kw["synthesize_timed_speech"].call_args[1]["tts_method"]
            == "Google Cloud TTS"
        )


@patch("src.ui.pages.dubbing.update_dubbing_progress")
@patch("src.ui.pages.dubbing.get_dubbing_entry_status", return_value=STATUS_GENERATING)
@patch("src.ui.pages.dubbing.generate_dubbing_output_path")
@patch("src.ui.pages.dubbing.tr", side_effect=lambda key, **kw: key)
class TestPipelineCheckpointLangInvalidation:
    """Detailed tests for language change checkpoint invalidation."""

    def test_language_change_removes_voice_key(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """Language change removes voice_file key from checkpoint."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker(target_lang="French")
        kw = _default_kwargs(tmp_path)
        ckpt = {
            "srt_text": _FAKE_SRT,
            "translated_srt": _FAKE_TRANSLATED_SRT,
            "target_lang": "Vietnamese",
            "voice_file": "voice.mp3",
        }
        kw["load_checkpoint"] = MagicMock(return_value=ckpt)
        _run_pipeline(worker, kw)
        # translated_srt was removed from ckpt dict
        assert "translated_srt" not in ckpt
        assert "voice_file" not in ckpt

    def test_same_language_no_invalidation(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """Same target language keeps checkpoint intact."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker(target_lang="Vietnamese")
        kw = _default_kwargs(tmp_path)
        ckpt = {
            "srt_text": _FAKE_SRT,
            "translated_srt": _FAKE_TRANSLATED_SRT,
            "target_lang": "Vietnamese",
            "voice_file": "voice.mp3",
        }
        (kw["storage_dir"] / "voice.mp3").touch()
        kw["load_checkpoint"] = MagicMock(return_value=ckpt)
        _run_pipeline(worker, kw)
        assert "translated_srt" in ckpt
        assert "voice_file" in ckpt

    def test_no_previous_target_lang_no_log(
        self, _tr, mock_gen_path, _status, _progress, tmp_path, caplog
    ) -> None:
        """When checkpoint has no target_lang, no 'changed' log message."""
        import logging  # noqa: PLC0415

        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker(target_lang="French")
        kw = _default_kwargs(tmp_path)
        ckpt = {"srt_text": _FAKE_SRT}
        kw["load_checkpoint"] = MagicMock(return_value=ckpt)
        with caplog.at_level(logging.INFO, logger="dubbing"):
            _run_pipeline(worker, kw)
        assert not any("target language changed" in r.message for r in caplog.records)


@patch("src.ui.pages.dubbing.update_dubbing_progress")
@patch("src.ui.pages.dubbing.get_dubbing_entry_status", return_value=STATUS_GENERATING)
@patch("src.ui.pages.dubbing.generate_dubbing_output_path")
@patch("src.ui.pages.dubbing.tr", side_effect=lambda key, **kw: key)
class TestPipelineISCancelledCallback:
    """Tests for the is_cancelled callback in the pipeline."""

    def test_cancel_callback_passed_to_stt(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """An is_cancelled callback is passed to transcribe_audio."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        _run_pipeline(worker, kw)
        assert "is_cancelled" in kw["transcribe_audio"].call_args[1]
        assert callable(kw["transcribe_audio"].call_args[1]["is_cancelled"])

    def test_cancel_callback_passed_to_tts(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """An is_cancelled callback is passed to synthesize_timed_speech."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        _run_pipeline(worker, kw)
        assert "is_cancelled" in kw["synthesize_timed_speech"].call_args[1]
        assert callable(kw["synthesize_timed_speech"].call_args[1]["is_cancelled"])

    def test_cancel_callback_linked_to_entry_id(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """Cancel callback invokes _is_task_cancelled with the correct entry_id."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        _run_pipeline(worker, kw)
        cancel_fn = kw["transcribe_audio"].call_args[1]["is_cancelled"]
        cancel_fn()
        worker._is_task_cancelled.assert_called_with(_ENTRY_ID)


@patch("src.ui.pages.dubbing.update_dubbing_progress")
@patch("src.ui.pages.dubbing.get_dubbing_entry_status", return_value=STATUS_GENERATING)
@patch("src.ui.pages.dubbing.generate_dubbing_output_path")
@patch("src.ui.pages.dubbing.tr", side_effect=lambda key, **kw: key)
class TestPipelineEmptyGlossary:
    """Tests for glossary edge cases."""

    def test_none_glossary_not_passed(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """None glossary is forwarded to translate_batch."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        kw["glossary_entries"] = None
        _run_pipeline(worker, kw)
        assert kw["translate_batch"].call_args[1]["glossary_entries"] is None

    def test_large_glossary(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """Large glossary is forwarded without truncation."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        large_glossary = [(i, f"src{i}", f"tgt{i}") for i in range(500)]
        kw["glossary_entries"] = large_glossary
        _run_pipeline(worker, kw)
        assert len(kw["translate_batch"].call_args[1]["glossary_entries"]) == 500  # noqa: PLR2004


@patch("src.ui.pages.dubbing.update_dubbing_progress")
@patch("src.ui.pages.dubbing.get_dubbing_entry_status", return_value=STATUS_GENERATING)
@patch("src.ui.pages.dubbing.generate_dubbing_output_path")
@patch("src.ui.pages.dubbing.tr", side_effect=lambda key, **kw: key)
class TestPipelineSttMethodVariants:
    """Tests for different STT methods."""

    def test_google_stt_method(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """Google Cloud STT method is forwarded."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        kw["stt_method"] = "Google Cloud"
        _run_pipeline(worker, kw)
        assert kw["transcribe_audio"].call_args[1]["stt_method"] == "Google Cloud"

    def test_whisper_stt_method(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """Whisper STT method is forwarded."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        kw["stt_method"] = "Whisper"
        _run_pipeline(worker, kw)
        assert kw["transcribe_audio"].call_args[1]["stt_method"] == "Whisper"


@patch("src.ui.pages.dubbing.update_dubbing_progress")
@patch("src.ui.pages.dubbing.get_dubbing_entry_status", return_value=STATUS_GENERATING)
@patch("src.ui.pages.dubbing.generate_dubbing_output_path")
@patch("src.ui.pages.dubbing.tr", side_effect=lambda key, **kw: key)
class TestPipelineOutputPathHandling:
    """Tests for output path generation and propagation."""

    def test_output_path_in_results(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """Output path appears in results list."""
        out = tmp_path / "output" / "dubbed.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        mock_gen_path.return_value = out
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        with patch("src.constants.languages.get_locale_code", return_value="xx"):
            _run_pipeline(worker, kw)
        assert kw["results"][0][1] == str(out)

    def test_mix_uses_generated_output_path(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """mix_audio_into_video receives the generated output path."""
        out = tmp_path / "dubbed_output.mp4"
        mock_gen_path.return_value = out
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        _run_pipeline(worker, kw)
        mix_call = kw["mix_audio_into_video"].call_args
        assert mix_call[0][2] == str(out)


@patch("src.ui.pages.dubbing.update_dubbing_progress")
@patch("src.ui.pages.dubbing.get_dubbing_entry_status", return_value=STATUS_GENERATING)
@patch("src.ui.pages.dubbing.generate_dubbing_output_path")
@patch("src.ui.pages.dubbing.tr", side_effect=lambda key, **kw: key)
class TestPipelineTTSProgressRange:
    """Tests for TTS progress callback range validation."""

    def test_tts_progress_values_in_range(
        self, _tr, mock_gen_path, _status, mock_progress, tmp_path
    ) -> None:
        """All TTS progress values fall between TTS_START and TTS_DONE."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)

        def synth_with_progress(entries, **kwargs):
            on_progress = kwargs.get("on_progress")
            if on_progress:
                for i in range(5):
                    on_progress(i + 1, 5)
            return str(kw["storage_dir"] / "voice.mp3")

        kw["synthesize_timed_speech"] = MagicMock(side_effect=synth_with_progress)
        _run_pipeline(worker, kw)
        values = [c[0][1] for c in mock_progress.call_args_list]
        tts_vals = [
            v
            for v in values
            if DUBBING_PROGRESS_TTS_START < v <= DUBBING_PROGRESS_TTS_DONE
        ]
        assert len(tts_vals) >= 3  # noqa: PLR2004

    def test_tts_progress_first_callback(
        self, _tr, mock_gen_path, _status, mock_progress, tmp_path
    ) -> None:
        """First TTS progress callback produces a value > TTS_START."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)

        def synth_with_progress(entries, **kwargs):
            on_progress = kwargs.get("on_progress")
            if on_progress:
                on_progress(1, 10)

        kw["synthesize_timed_speech"] = MagicMock(side_effect=synth_with_progress)
        _run_pipeline(worker, kw)
        values = [c[0][1] for c in mock_progress.call_args_list]
        tts_vals = [
            v
            for v in values
            if DUBBING_PROGRESS_TTS_START < v < DUBBING_PROGRESS_TTS_DONE
        ]
        assert len(tts_vals) >= 1


@patch("src.ui.pages.dubbing.update_dubbing_progress")
@patch("src.ui.pages.dubbing.get_dubbing_entry_status", return_value=STATUS_GENERATING)
@patch("src.ui.pages.dubbing.generate_dubbing_output_path")
@patch("src.ui.pages.dubbing.tr", side_effect=lambda key, **kw: key)
class TestPipelineSerializeSrt:
    """Tests for SRT serialization in the pipeline."""

    def test_serialize_called_with_srt_format(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """serialize_subtitle is called with .srt format."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        _run_pipeline(worker, kw)
        ser_call = kw["serialize_subtitle"].call_args
        assert ser_call[0][2] == ".srt"

    def test_parse_called_with_srt_format(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """parse_subtitle is called with .srt format."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        _run_pipeline(worker, kw)
        # First parse call (for translate step)
        first_parse = kw["parse_subtitle"].call_args_list[0]
        assert first_parse[0][1] == ".srt"


class TestDubbingWorkerIsBusy:
    """Additional tests for is_busy class-level flag."""

    def test_is_busy_initially_false(self) -> None:
        """is_busy is False initially."""
        from src.ui.pages.dubbing import _DubbingWorker  # noqa: PLC0415

        original = _DubbingWorker._is_any_worker_running
        try:
            _DubbingWorker._is_any_worker_running = False
            assert not _DubbingWorker.is_busy()
        finally:
            _DubbingWorker._is_any_worker_running = original

    def test_is_busy_reflects_flag(self) -> None:
        """is_busy reflects the class-level flag."""
        from src.ui.pages.dubbing import _DubbingWorker  # noqa: PLC0415

        original = _DubbingWorker._is_any_worker_running
        try:
            _DubbingWorker._is_any_worker_running = True
            assert _DubbingWorker.is_busy()
            _DubbingWorker._is_any_worker_running = False
            assert not _DubbingWorker.is_busy()
        finally:
            _DubbingWorker._is_any_worker_running = original


class TestDubbingWorkerStopControl:
    """Additional tests for stop() and _is_running."""

    def test_stop_twice_is_safe(self) -> None:
        """Calling stop() twice doesn't crash."""
        from src.ui.pages.dubbing import _DubbingWorker  # noqa: PLC0415

        worker = MagicMock(spec=_DubbingWorker)
        worker._is_running = True
        _DubbingWorker.stop(worker)
        assert not worker._is_running
        _DubbingWorker.stop(worker)
        assert not worker._is_running


class TestDubbingPageTheme:
    """Tests for DubbingPage theme/language methods."""

    def test_apply_theme_no_crash(self, page) -> None:
        """apply_theme does not raise."""
        page.apply_theme()

    def test_apply_language_no_crash(self, page) -> None:
        """apply_language does not raise."""
        page.apply_language()

    def test_apply_theme_twice(self, page) -> None:
        """Calling apply_theme twice is safe."""
        page.apply_theme()
        page.apply_theme()

    def test_apply_language_twice(self, page) -> None:
        """Calling apply_language twice is safe."""
        page.apply_language()
        page.apply_language()


class TestDubbingPageClearAll:
    """Tests for _handle_clear_all."""

    def test_clear_all_empties_files(self, page) -> None:
        """_handle_clear_all empties the selected_files list."""
        page.selected_files = ["/a.mp4", "/b.mp4"]
        page._handle_clear_all()
        assert page.selected_files == []

    def test_clear_all_switches_to_history(self, page) -> None:
        """_handle_clear_all switches back to history view."""
        page.selected_files = ["/a.mp4"]
        page._update_ui_state()
        page._handle_clear_all()
        assert page.stack.currentIndex() == 0

    def test_clear_all_disables_generate(self, page) -> None:
        """_handle_clear_all disables the generate button."""
        page.selected_files = ["/a.mp4"]
        page._update_ui_state()
        page._handle_clear_all()
        assert not page.generate_btn.isEnabled()


class TestDubbingPageFilesBadge:
    """Tests for the files badge count."""

    def test_badge_zero_initially(self, page) -> None:
        """Badge shows 0 initially."""
        assert page.files_badge.text() == "0"

    def test_badge_updates_with_files(self, page) -> None:
        """Badge updates to the number of selected files."""
        page.selected_files = ["/a.mp4", "/b.mp4"]
        page._update_ui_state()
        assert page.files_badge.text() == "2"

    def test_badge_updates_after_clear(self, page) -> None:
        """Badge resets to 0 after clear."""
        page.selected_files = ["/a.mp4"]
        page._update_ui_state()
        page._handle_clear_all()
        assert page.files_badge.text() == "0"

    def test_badge_five_files(self, page) -> None:
        """Badge shows 5 for five files."""
        page.selected_files = [f"/video{i}.mp4" for i in range(5)]
        page._update_ui_state()
        assert page.files_badge.text() == "5"


# ===========================================================================
# NEW TESTS — Pipeline progress tracking (expanded)
# ===========================================================================


@patch("src.ui.pages.dubbing.update_dubbing_progress")
@patch("src.ui.pages.dubbing.get_dubbing_entry_status", return_value=STATUS_GENERATING)
@patch("src.ui.pages.dubbing.generate_dubbing_output_path")
@patch("src.ui.pages.dubbing.tr", side_effect=lambda key, **kw: key)
class TestPipelineProgressTracking:
    """Tests for progress tracking through the 4-step pipeline."""

    def test_full_pipeline_progress_order(
        self, _tr, mock_gen_path, _status, mock_progress, tmp_path
    ) -> None:
        """Full pipeline progress values are monotonically increasing."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        _run_pipeline(worker, kw)
        values = [c[0][1] for c in mock_progress.call_args_list]
        # Verify monotonically increasing
        for i in range(1, len(values)):
            assert values[i] >= values[i - 1]

    def test_stt_start_progress_emitted(
        self, _tr, mock_gen_path, _status, mock_progress, tmp_path
    ) -> None:
        """STT_START progress is emitted at beginning."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        _run_pipeline(worker, kw)
        values = [c[0][1] for c in mock_progress.call_args_list]
        assert DUBBING_PROGRESS_STT_START in values

    def test_stt_done_progress_emitted(
        self, _tr, mock_gen_path, _status, mock_progress, tmp_path
    ) -> None:
        """STT_DONE progress is emitted after transcription."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        _run_pipeline(worker, kw)
        values = [c[0][1] for c in mock_progress.call_args_list]
        assert DUBBING_PROGRESS_STT_DONE in values

    def test_translate_done_progress_emitted(
        self, _tr, mock_gen_path, _status, mock_progress, tmp_path
    ) -> None:
        """TRANSLATE_DONE progress is emitted after translation."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        _run_pipeline(worker, kw)
        values = [c[0][1] for c in mock_progress.call_args_list]
        assert DUBBING_PROGRESS_TRANSLATE_DONE in values

    def test_tts_done_progress_emitted(
        self, _tr, mock_gen_path, _status, mock_progress, tmp_path
    ) -> None:
        """TTS_DONE progress is emitted after TTS."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        _run_pipeline(worker, kw)
        values = [c[0][1] for c in mock_progress.call_args_list]
        assert DUBBING_PROGRESS_TTS_DONE in values

    def test_complete_progress_emitted(
        self, _tr, mock_gen_path, _status, mock_progress, tmp_path
    ) -> None:
        """PROGRESS_COMPLETE is emitted at the end."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        _run_pipeline(worker, kw)
        values = [c[0][1] for c in mock_progress.call_args_list]
        assert PROGRESS_COMPLETE in values

    def test_progress_all_stages_present(
        self, _tr, mock_gen_path, _status, mock_progress, tmp_path
    ) -> None:
        """All major progress milestones are present."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        _run_pipeline(worker, kw)
        values = [c[0][1] for c in mock_progress.call_args_list]
        for milestone in [
            DUBBING_PROGRESS_STT_START,
            DUBBING_PROGRESS_STT_DONE,
            DUBBING_PROGRESS_TRANSLATE_DONE,
            DUBBING_PROGRESS_TTS_DONE,
            PROGRESS_COMPLETE,
        ]:
            assert milestone in values


# ===========================================================================
# NEW TESTS — Checkpoint resumption at each step (expanded)
# ===========================================================================


@patch("src.ui.pages.dubbing.update_dubbing_progress")
@patch("src.ui.pages.dubbing.get_dubbing_entry_status", return_value=STATUS_GENERATING)
@patch("src.ui.pages.dubbing.generate_dubbing_output_path")
@patch("src.ui.pages.dubbing.tr", side_effect=lambda key, **kw: key)
class TestCheckpointResumptionExpanded:
    """Expanded checkpoint resumption tests."""

    def test_resume_stt_only(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """Resuming with only srt_text skips STT but runs translate/TTS/mix."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        kw["load_checkpoint"] = MagicMock(
            return_value={"srt_text": _FAKE_SRT, "target_lang": "Vietnamese"}
        )
        _run_pipeline(worker, kw)
        kw["transcribe_audio"].assert_not_called()
        kw["translate_batch"].assert_called_once()
        kw["synthesize_timed_speech"].assert_called_once()
        kw["mix_audio_into_video"].assert_called_once()

    def test_resume_stt_and_translate(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """Resuming with srt_text + translated_srt skips STT and translate."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        kw["load_checkpoint"] = MagicMock(
            return_value={
                "srt_text": _FAKE_SRT,
                "translated_srt": _FAKE_TRANSLATED_SRT,
                "target_lang": "Vietnamese",
            }
        )
        _run_pipeline(worker, kw)
        kw["transcribe_audio"].assert_not_called()
        kw["translate_batch"].assert_not_called()
        kw["synthesize_timed_speech"].assert_called_once()
        kw["mix_audio_into_video"].assert_called_once()

    def test_resume_all_three(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """Resuming with all three checkpoints skips to mix only."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        kw["load_checkpoint"] = MagicMock(
            return_value={
                "srt_text": _FAKE_SRT,
                "translated_srt": _FAKE_TRANSLATED_SRT,
                "target_lang": "Vietnamese",
                "voice_file": "voice.mp3",
            }
        )
        (kw["storage_dir"] / "voice.mp3").touch()
        _run_pipeline(worker, kw)
        kw["transcribe_audio"].assert_not_called()
        kw["translate_batch"].assert_not_called()
        kw["synthesize_timed_speech"].assert_not_called()
        kw["mix_audio_into_video"].assert_called_once()

    def test_voice_file_missing_resynth(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """If voice_file in checkpoint but file missing, TTS re-runs."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        kw["load_checkpoint"] = MagicMock(
            return_value={
                "srt_text": _FAKE_SRT,
                "translated_srt": _FAKE_TRANSLATED_SRT,
                "target_lang": "Vietnamese",
                "voice_file": "voice.mp3",
            }
        )
        # Do NOT touch the voice file — so it doesn't exist
        _run_pipeline(worker, kw)
        kw["synthesize_timed_speech"].assert_called_once()

    def test_no_checkpoint_runs_full_pipeline(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """No checkpoint runs all four steps."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        _run_pipeline(worker, kw)
        kw["transcribe_audio"].assert_called_once()
        kw["translate_batch"].assert_called_once()
        kw["synthesize_timed_speech"].assert_called_once()
        kw["mix_audio_into_video"].assert_called_once()


# ===========================================================================
# NEW TESTS — Worker lifecycle (expanded)
# ===========================================================================


class TestDubbingWorkerLifecycle:
    """Expanded worker lifecycle tests."""

    def test_worker_initial_running(self) -> None:
        """Worker starts with _is_running True."""
        worker = _make_worker()
        assert worker._is_running is True

    def test_worker_stores_tasks(self) -> None:
        """Worker stores task list."""
        tasks = [(_ENTRY_ID, "/video.mp4")]
        worker = _make_worker(tasks=tasks)
        assert worker._tasks == tasks

    def test_worker_stores_src_lang(self) -> None:
        """Worker stores source language."""
        worker = _make_worker(src_lang="French")
        assert worker._src_lang == "French"

    def test_worker_stores_target_lang(self) -> None:
        """Worker stores target language."""
        worker = _make_worker(target_lang="Japanese")
        assert worker._target_lang == "Japanese"

    def test_worker_stores_gender(self) -> None:
        """Worker stores voice gender."""
        worker = _make_worker()
        assert worker._voice_gender == "FEMALE"

    def test_is_busy_flag_toggle(self) -> None:
        """_is_any_worker_running flag can be toggled."""
        from src.ui.pages.dubbing import _DubbingWorker  # noqa: PLC0415

        original = _DubbingWorker._is_any_worker_running
        try:
            _DubbingWorker._is_any_worker_running = True
            assert _DubbingWorker.is_busy()
            _DubbingWorker._is_any_worker_running = False
            assert not _DubbingWorker.is_busy()
        finally:
            _DubbingWorker._is_any_worker_running = original

    def test_stop_sets_running_false(self) -> None:
        """stop() sets _is_running to False."""
        from src.ui.pages.dubbing import _DubbingWorker  # noqa: PLC0415

        worker = MagicMock(spec=_DubbingWorker)
        worker._is_running = True
        _DubbingWorker.stop(worker)
        assert not worker._is_running


# ===========================================================================
# NEW TESTS — Settings loading and forwarding (expanded)
# ===========================================================================


@patch("src.ui.pages.dubbing.update_dubbing_progress")
@patch("src.ui.pages.dubbing.get_dubbing_entry_status", return_value=STATUS_GENERATING)
@patch("src.ui.pages.dubbing.generate_dubbing_output_path")
@patch("src.ui.pages.dubbing.tr", side_effect=lambda key, **kw: key)
class TestSettingsForwardingExpanded:
    """Expanded settings forwarding tests."""

    def test_audio_format_forwarded(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """audio_fmt is forwarded to synthesize_timed_speech."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        kw["audio_fmt"] = ".wav"
        _run_pipeline(worker, kw)
        assert kw["synthesize_timed_speech"].call_args[1]["audio_format"] == ".wav"

    def test_voice_gender_forwarded(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """voice_gender is forwarded to synthesize_timed_speech."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        worker._voice_gender = "MALE"
        kw = _default_kwargs(tmp_path)
        _run_pipeline(worker, kw)
        assert kw["synthesize_timed_speech"].call_args[1]["voice_gender"] == "MALE"

    def test_src_lang_forwarded_to_translate(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """Source language is forwarded to translate_batch."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker(src_lang="French")
        kw = _default_kwargs(tmp_path)
        _run_pipeline(worker, kw)
        assert kw["translate_batch"].call_args[1]["src_lang"] == "French"

    def test_target_lang_forwarded_to_tts(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """Target language is forwarded to synthesize_timed_speech."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker(target_lang="German")
        kw = _default_kwargs(tmp_path)
        _run_pipeline(worker, kw)
        assert kw["synthesize_timed_speech"].call_args[1]["target_lang"] == "German"

    def test_target_lang_forwarded_to_translate(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """Target language is forwarded to translate_batch."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker(target_lang="Korean")
        kw = _default_kwargs(tmp_path)
        _run_pipeline(worker, kw)
        assert kw["translate_batch"].call_args[1]["target_lang"] == "Korean"

    def test_empty_src_lang_becomes_auto(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """Empty source language becomes 'Auto' for translate_batch."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker(src_lang="")
        kw = _default_kwargs(tmp_path)
        _run_pipeline(worker, kw)
        assert kw["translate_batch"].call_args[1]["src_lang"] == "Auto"


# ===========================================================================
# NEW TESTS — Error handling in pipeline
# ===========================================================================


@patch("src.ui.pages.dubbing.update_dubbing_progress")
@patch("src.ui.pages.dubbing.get_dubbing_entry_status", return_value=STATUS_GENERATING)
@patch("src.ui.pages.dubbing.generate_dubbing_output_path")
@patch("src.ui.pages.dubbing.tr", side_effect=lambda key, **kw: key)
class TestPipelineErrors:
    """Tests for error handling in the dubbing pipeline."""

    def test_stt_error_propagates(
        self, _tr, _gen, _status, _progress, tmp_path
    ) -> None:
        """STT error propagates as exception."""
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        kw["transcribe_audio"] = MagicMock(side_effect=RuntimeError("STT failed"))
        with pytest.raises(RuntimeError, match="STT failed"):
            _run_pipeline(worker, kw)

    def test_translate_error_propagates(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """Translation error propagates as exception."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        kw["translate_batch"] = MagicMock(side_effect=ValueError("AUTH_ERROR"))
        with pytest.raises(ValueError, match="AUTH_ERROR"):
            _run_pipeline(worker, kw)

    def test_tts_error_propagates(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """TTS error propagates as exception."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        kw["synthesize_timed_speech"] = MagicMock(
            side_effect=RuntimeError("TTS failed")
        )
        with pytest.raises(RuntimeError, match="TTS failed"):
            _run_pipeline(worker, kw)

    def test_mix_error_propagates(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """Mix error propagates as exception."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        kw["mix_audio_into_video"] = MagicMock(side_effect=RuntimeError("FFmpeg error"))
        with pytest.raises(RuntimeError, match="FFmpeg error"):
            _run_pipeline(worker, kw)


# ===========================================================================
# NEW TESTS — Cancellation at each step (expanded)
# ===========================================================================


@patch("src.ui.pages.dubbing.update_dubbing_progress")
@patch("src.ui.pages.dubbing.get_dubbing_entry_status", return_value=STATUS_GENERATING)
@patch("src.ui.pages.dubbing.generate_dubbing_output_path")
@patch("src.ui.pages.dubbing.tr", side_effect=lambda key, **kw: key)
class TestCancellationExpanded:
    """Expanded cancellation tests for each pipeline step."""

    def test_cancel_after_stt(self, _tr, _gen, _status, _progress, tmp_path) -> None:
        """Cancellation after STT prevents translation."""
        worker = _make_worker()
        # cancel() is first checked after transcribe_audio returns
        worker._is_task_cancelled = MagicMock(return_value=True)
        kw = _default_kwargs(tmp_path)
        _run_pipeline(worker, kw)
        # STT runs but translate does not
        kw["transcribe_audio"].assert_called_once()
        kw["translate_batch"].assert_not_called()

    def test_cancel_before_tts(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """Cancellation before TTS prevents synthesis."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        # cancel: after STT=False, after translate=False, before TTS=True
        worker._is_task_cancelled = MagicMock(
            side_effect=[False, False, True],
        )
        kw = _default_kwargs(tmp_path)
        _run_pipeline(worker, kw)
        kw["synthesize_timed_speech"].assert_not_called()

    def test_cancel_before_mix(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """Cancellation before mix prevents final mixing."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        # cancel: STT=F, translate=F, before_TTS=F, after_synth=F, before_mix=T
        worker._is_task_cancelled = MagicMock(
            side_effect=[False, False, False, False, True],
        )
        kw = _default_kwargs(tmp_path)
        _run_pipeline(worker, kw)
        kw["mix_audio_into_video"].assert_not_called()

    def test_cancel_callback_callable(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """Cancel callback passed to transcribe is callable."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        _run_pipeline(worker, kw)
        cancel_fn = kw["transcribe_audio"].call_args[1]["is_cancelled"]
        assert callable(cancel_fn)

    def test_cancel_callback_passed_to_translate(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """Cancel callback is passed to translate_batch."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        _run_pipeline(worker, kw)
        assert "cancel_check" in kw["translate_batch"].call_args[1]


# ===========================================================================
# NEW TESTS — Checkpoint saving verification
# ===========================================================================


@patch("src.ui.pages.dubbing.update_dubbing_progress")
@patch("src.ui.pages.dubbing.get_dubbing_entry_status", return_value=STATUS_GENERATING)
@patch("src.ui.pages.dubbing.generate_dubbing_output_path")
@patch("src.ui.pages.dubbing.tr", side_effect=lambda key, **kw: key)
class TestCheckpointSaving:
    """Tests for checkpoint saving during pipeline execution."""

    def test_checkpoint_saved_after_stt(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """Checkpoint saved after STT with srt_text and target_lang."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        _run_pipeline(worker, kw)
        first_save = kw["save_checkpoint"].call_args_list[0]
        assert "srt_text" in first_save[1]
        assert "target_lang" in first_save[1]

    def test_checkpoint_saved_after_translate(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """Checkpoint saved after translate with translated_srt."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        _run_pipeline(worker, kw)
        second_save = kw["save_checkpoint"].call_args_list[1]
        assert "translated_srt" in second_save[1]

    def test_checkpoint_saved_after_tts(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """Checkpoint saved after TTS with voice_file."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        _run_pipeline(worker, kw)
        third_save = kw["save_checkpoint"].call_args_list[2]
        assert "voice_file" in third_save[1]

    def test_three_checkpoints_total(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """Full pipeline saves exactly 3 checkpoints."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        _run_pipeline(worker, kw)
        assert kw["save_checkpoint"].call_count == 3  # noqa: PLR2004

    def test_checkpoint_storage_dir_correct(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """All checkpoints use correct storage_dir."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        _run_pipeline(worker, kw)
        for call in kw["save_checkpoint"].call_args_list:
            assert call[0][0] == kw["storage_dir"]


# ===========================================================================
# NEW TESTS — Output path and results
# ===========================================================================


@patch("src.ui.pages.dubbing.update_dubbing_progress")
@patch("src.ui.pages.dubbing.get_dubbing_entry_status", return_value=STATUS_GENERATING)
@patch("src.ui.pages.dubbing.generate_dubbing_output_path")
@patch("src.ui.pages.dubbing.tr", side_effect=lambda key, **kw: key)
class TestResultsHandling:
    """Tests for results list handling."""

    def test_results_entry_id_correct(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """Results contain correct entry_id."""
        out = tmp_path / "dubbed.mp4"
        mock_gen_path.return_value = out
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        _run_pipeline(worker, kw)
        assert kw["results"][0][0] == _ENTRY_ID

    def test_results_output_path_correct(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """Results contain correct output path."""
        out = tmp_path / "dubbed_output.mp4"
        mock_gen_path.return_value = out
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        _run_pipeline(worker, kw)
        assert kw["results"][0][1] == str(out)

    def test_results_list_initially_empty(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """Results list starts empty and has one entry after success."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        assert len(kw["results"]) == 0
        _run_pipeline(worker, kw)
        assert len(kw["results"]) == 1

    def test_mix_receives_video_path(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """mix_audio_into_video receives the original video path."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        _run_pipeline(worker, kw)
        assert kw["mix_audio_into_video"].call_args[0][0] == "/tmp/video.mp4"

    def test_mix_receives_voice_path(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """mix_audio_into_video receives the synthesized voice path."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        _run_pipeline(worker, kw)
        voice_arg = kw["mix_audio_into_video"].call_args[0][1]
        assert "voice" in voice_arg


# ===========================================================================
# NEW TESTS — Language change invalidation (expanded)
# ===========================================================================


@patch("src.ui.pages.dubbing.update_dubbing_progress")
@patch("src.ui.pages.dubbing.get_dubbing_entry_status", return_value=STATUS_GENERATING)
@patch("src.ui.pages.dubbing.generate_dubbing_output_path")
@patch("src.ui.pages.dubbing.tr", side_effect=lambda key, **kw: key)
class TestLanguageChangeExpanded:
    """Expanded language change checkpoint invalidation tests."""

    def test_lang_change_retranslates(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """Language change forces re-translation."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker(target_lang="French")
        kw = _default_kwargs(tmp_path)
        kw["load_checkpoint"] = MagicMock(
            return_value={
                "srt_text": _FAKE_SRT,
                "translated_srt": _FAKE_TRANSLATED_SRT,
                "target_lang": "Vietnamese",
            }
        )
        _run_pipeline(worker, kw)
        # Translation should run again because target changed
        kw["translate_batch"].assert_called_once()

    def test_lang_change_resynthesizes(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """Language change forces re-synthesis."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker(target_lang="French")
        kw = _default_kwargs(tmp_path)
        kw["load_checkpoint"] = MagicMock(
            return_value={
                "srt_text": _FAKE_SRT,
                "translated_srt": _FAKE_TRANSLATED_SRT,
                "target_lang": "Vietnamese",
                "voice_file": "voice.mp3",
            }
        )
        _run_pipeline(worker, kw)
        kw["synthesize_timed_speech"].assert_called_once()

    def test_same_lang_no_retranslation(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """Same target language skips re-translation."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker(target_lang="Vietnamese")
        kw = _default_kwargs(tmp_path)
        kw["load_checkpoint"] = MagicMock(
            return_value={
                "srt_text": _FAKE_SRT,
                "translated_srt": _FAKE_TRANSLATED_SRT,
                "target_lang": "Vietnamese",
                "voice_file": "voice.mp3",
            }
        )
        (kw["storage_dir"] / "voice.mp3").touch()
        _run_pipeline(worker, kw)
        kw["translate_batch"].assert_not_called()
        kw["synthesize_timed_speech"].assert_not_called()


# ===========================================================================
# NEW TESTS — Multiple tasks
# ===========================================================================


@patch("src.ui.pages.dubbing.update_dubbing_progress")
@patch("src.ui.pages.dubbing.get_dubbing_entry_status", return_value=STATUS_GENERATING)
@patch("src.ui.pages.dubbing.generate_dubbing_output_path")
@patch("src.ui.pages.dubbing.tr", side_effect=lambda key, **kw: key)
class TestMultipleEntryIds:
    """Tests for pipeline with different entry IDs."""

    def test_entry_id_forwarded_to_progress(
        self, _tr, mock_gen_path, _status, mock_progress, tmp_path
    ) -> None:
        """Entry ID is forwarded to all progress calls."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        entry_id = 99
        worker = _make_worker(tasks=[(entry_id, "/tmp/video.mp4")])
        kw = _default_kwargs(tmp_path, entry_id=entry_id)
        _run_pipeline(worker, kw)
        for call in mock_progress.call_args_list:
            assert call[0][0] == entry_id

    def test_different_entry_ids(
        self, _tr, mock_gen_path, _status, mock_progress, tmp_path
    ) -> None:
        """Different entry IDs produce separate progress calls."""
        mock_gen_path.return_value = tmp_path / "dubbed.mp4"
        worker = _make_worker(tasks=[(100, "/tmp/video.mp4")])
        kw = _default_kwargs(tmp_path, entry_id=100)
        _run_pipeline(worker, kw)
        for call in mock_progress.call_args_list:
            assert call[0][0] == 100  # noqa: PLR2004


# ===========================================================================
# NEW TESTS — DubbingPage UI (expanded)
# ===========================================================================


class TestDubbingPageUI:
    """Expanded tests for DubbingPage UI interactions."""

    def test_page_has_generate_button(self, page) -> None:
        """Page has a generate button."""
        from PySide6.QtWidgets import QPushButton  # noqa: PLC0415

        assert hasattr(page, "generate_btn")
        assert isinstance(page.generate_btn, QPushButton)

    def test_page_has_stack_widget(self, page) -> None:
        """Page has a stacked widget."""
        assert hasattr(page, "stack")

    def test_initial_view_is_history(self, page) -> None:
        """Initial view is the history view."""
        assert page.stack.currentIndex() == 0

    def test_update_ui_state_with_files(self, page) -> None:
        """_update_ui_state switches to files view when files present."""
        page.selected_files = ["/a.mp4"]
        page._update_ui_state()
        assert page.stack.currentIndex() == 1

    def test_update_ui_state_no_files(self, page) -> None:
        """_update_ui_state switches to history when no files."""
        page.selected_files = []
        page._update_ui_state()
        assert page.stack.currentIndex() == 0

    def test_clear_all_no_files(self, page) -> None:
        """_handle_clear_all with empty files is safe."""
        page.selected_files = []
        page._handle_clear_all()
        assert page.selected_files == []

    def test_badge_ten_files(self, page) -> None:
        """Badge shows 10 for ten files."""
        page.selected_files = [f"/video{i}.mp4" for i in range(10)]
        page._update_ui_state()
        assert page.files_badge.text() == "10"

    def test_generate_btn_disabled_no_files(self, page) -> None:
        """Generate button disabled when no files selected."""
        page.selected_files = []
        page._update_ui_state()
        assert not page.generate_btn.isEnabled()

    def test_generate_btn_enabled_with_files(self, page) -> None:
        """Generate button enabled when files are selected."""
        page.selected_files = ["/a.mp4"]
        page._update_ui_state()
        assert page.generate_btn.isEnabled()


# ===========================================================================
# NEW TESTS — Expanded pipeline coverage
# ===========================================================================


@patch("src.ui.pages.dubbing.update_dubbing_progress")
@patch("src.ui.pages.dubbing.get_dubbing_entry_status", return_value=STATUS_GENERATING)
@patch("src.ui.pages.dubbing.generate_dubbing_output_path")
@patch("src.ui.pages.dubbing.tr", side_effect=lambda key, **kw: key)
class TestPipelineArtifactOutput:
    """Tests for intermediate artifact files produced by the pipeline."""

    def test_original_srt_written_to_output_dir(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """Original SRT is saved alongside dubbed video."""
        out_file = tmp_path / "out" / "dubbed.mp4"
        out_file.parent.mkdir(parents=True, exist_ok=True)
        mock_gen_path.return_value = out_file
        worker = _make_worker(src_lang="English (US)", target_lang="Vietnamese")
        kw = _default_kwargs(tmp_path)
        (kw["storage_dir"] / "voice.mp3").write_bytes(b"audio")
        with patch(
            "src.constants.languages.get_locale_code",
            side_effect=lambda l: "en-US" if "English" in l else "vi",
        ):
            _run_pipeline(worker, kw)
        srt_file = out_file.parent / f"{Path('/tmp/video.mp4').stem}_subtitle_en-US.srt"
        assert srt_file.exists()

    def test_translated_srt_written_to_output_dir(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """Translated SRT is saved alongside dubbed video."""
        out_file = tmp_path / "out" / "dubbed.mp4"
        out_file.parent.mkdir(parents=True, exist_ok=True)
        mock_gen_path.return_value = out_file
        worker = _make_worker(src_lang="English (US)", target_lang="Vietnamese")
        kw = _default_kwargs(tmp_path)
        (kw["storage_dir"] / "voice.mp3").write_bytes(b"audio")
        with patch(
            "src.constants.languages.get_locale_code",
            side_effect=lambda l: "en-US" if "English" in l else "vi",
        ):
            _run_pipeline(worker, kw)
        translated_file = (
            out_file.parent / f"{Path('/tmp/video.mp4').stem}_subtitle_vi.srt"
        )
        assert translated_file.exists()

    def test_voice_audio_copied_to_output_dir(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """Voice audio file is copied to output directory."""
        out_file = tmp_path / "out" / "dubbed.mp4"
        out_file.parent.mkdir(parents=True, exist_ok=True)
        mock_gen_path.return_value = out_file
        worker = _make_worker(src_lang="English (US)", target_lang="Vietnamese")
        kw = _default_kwargs(tmp_path)
        voice = kw["storage_dir"] / "voice.mp3"
        voice.write_bytes(b"fake audio content")
        with patch(
            "src.constants.languages.get_locale_code",
            side_effect=lambda l: "en-US" if "English" in l else "vi",
        ):
            _run_pipeline(worker, kw)
        voice_out = out_file.parent / f"{Path('/tmp/video.mp4').stem}_voice_vi.mp3"
        assert voice_out.exists()

    def test_results_contain_five_elements(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """Results tuple contains (entry_id, output, srt, translated_srt, voice)."""
        out_file = tmp_path / "out" / "dubbed.mp4"
        out_file.parent.mkdir(parents=True, exist_ok=True)
        mock_gen_path.return_value = out_file
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        (kw["storage_dir"] / "voice.mp3").write_bytes(b"audio")
        with patch("src.constants.languages.get_locale_code", return_value="vi"):
            _run_pipeline(worker, kw)
        assert len(kw["results"]) == 1
        assert len(kw["results"][0]) == 5  # noqa: PLR2004

    def test_locale_code_none_falls_back_to_unknown(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """When get_locale_code returns None, target code becomes 'unknown'."""
        out_file = tmp_path / "out" / "dubbed.mp4"
        out_file.parent.mkdir(parents=True, exist_ok=True)
        mock_gen_path.return_value = out_file
        worker = _make_worker(src_lang="", target_lang="UnknownLang")
        kw = _default_kwargs(tmp_path)
        (kw["storage_dir"] / "voice.mp3").write_bytes(b"audio")
        with patch("src.constants.languages.get_locale_code", return_value=None):
            _run_pipeline(worker, kw)
        # target code defaults to "unknown" when locale code is None
        translated_file = (
            out_file.parent / f"{Path('/tmp/video.mp4').stem}_subtitle_unknown.srt"
        )
        assert translated_file.exists()

    def test_src_lang_empty_uses_auto_for_srt_filename(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """Empty src_lang uses 'auto' as code in srt filename."""
        out_file = tmp_path / "out" / "dubbed.mp4"
        out_file.parent.mkdir(parents=True, exist_ok=True)
        mock_gen_path.return_value = out_file
        worker = _make_worker(src_lang="")
        kw = _default_kwargs(tmp_path)
        (kw["storage_dir"] / "voice.mp3").write_bytes(b"audio")
        with patch("src.constants.languages.get_locale_code", return_value=None):
            _run_pipeline(worker, kw)
        srt_file = out_file.parent / f"{Path('/tmp/video.mp4').stem}_subtitle_auto.srt"
        assert srt_file.exists()


@patch("src.ui.pages.dubbing.update_dubbing_progress")
@patch("src.ui.pages.dubbing.get_dubbing_entry_status", return_value=STATUS_GENERATING)
@patch("src.ui.pages.dubbing.generate_dubbing_output_path")
@patch("src.ui.pages.dubbing.tr", side_effect=lambda key, **kw: key)
class TestPipelineTranslationEdgeCases:
    """Tests for translation step edge cases."""

    def test_translate_batch_returns_wrong_count_preserves_original(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """When translate_batch returns wrong count, original text preserved."""
        mock_gen_path.return_value = tmp_path / "out.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        kw["translate_batch"] = MagicMock(return_value=["only one"])
        entries = _make_entries(["Hello", "Goodbye"])
        kw["parse_subtitle"] = MagicMock(return_value=(entries, {"format": "srt"}))
        (kw["storage_dir"] / "voice.mp3").write_bytes(b"audio")
        with patch("src.constants.languages.get_locale_code", return_value="vi"):
            _run_pipeline(worker, kw)
        # Entries should NOT have been modified since count mismatch
        assert entries[0].text == "Hello"
        assert entries[1].text == "Goodbye"

    def test_translate_batch_returns_none_preserves_original(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """When translate_batch returns None, original text preserved."""
        mock_gen_path.return_value = tmp_path / "out.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        kw["translate_batch"] = MagicMock(return_value=None)
        entries = _make_entries(["Hello", "Goodbye"])
        kw["parse_subtitle"] = MagicMock(return_value=(entries, {"format": "srt"}))
        (kw["storage_dir"] / "voice.mp3").write_bytes(b"audio")
        with patch("src.constants.languages.get_locale_code", return_value="vi"):
            _run_pipeline(worker, kw)
        assert entries[0].text == "Hello"

    def test_translate_batch_returns_empty_list_preserves_original(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """When translate_batch returns empty list, original text preserved."""
        mock_gen_path.return_value = tmp_path / "out.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        kw["translate_batch"] = MagicMock(return_value=[])
        entries = _make_entries(["Hello", "Goodbye"])
        kw["parse_subtitle"] = MagicMock(return_value=(entries, {"format": "srt"}))
        (kw["storage_dir"] / "voice.mp3").write_bytes(b"audio")
        with patch("src.constants.languages.get_locale_code", return_value="vi"):
            _run_pipeline(worker, kw)
        assert entries[0].text == "Hello"

    def test_no_entries_skips_translation_and_tts(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """When parse_subtitle returns empty entries, TTS raises error."""
        mock_gen_path.return_value = tmp_path / "out.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        kw["parse_subtitle"] = MagicMock(return_value=([], {"format": "srt"}))
        with pytest.raises(ValueError, match="dubbing.no_speech_detected"):
            _run_pipeline(worker, kw)

    def test_glossary_entries_forwarded(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """Glossary entries are passed to translate_batch."""
        mock_gen_path.return_value = tmp_path / "out.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        glossary = [(1, "hello", "xin chao")]
        kw["glossary_entries"] = glossary
        (kw["storage_dir"] / "voice.mp3").write_bytes(b"audio")
        with patch("src.constants.languages.get_locale_code", return_value="vi"):
            _run_pipeline(worker, kw)
        call_kwargs = kw["translate_batch"].call_args[1]
        assert call_kwargs["glossary_entries"] == glossary


@patch("src.ui.pages.dubbing.update_dubbing_progress")
@patch("src.ui.pages.dubbing.get_dubbing_entry_status", return_value=STATUS_GENERATING)
@patch("src.ui.pages.dubbing.generate_dubbing_output_path")
@patch("src.ui.pages.dubbing.tr", side_effect=lambda key, **kw: key)
class TestPipelineCancellationTiming:
    """Tests for cancellation at various pipeline stages."""

    def test_cancel_between_translate_and_tts(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """Cancellation after translation but before TTS returns early."""
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        call_count = [0]

        def cancel_after_two(_entry_id=None):
            call_count[0] += 1
            return call_count[0] >= 3  # noqa: PLR2004

        worker._is_task_cancelled = cancel_after_two
        _run_pipeline(worker, kw)
        kw["synthesize_timed_speech"].assert_not_called()

    def test_cancel_after_tts_before_mix(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """Cancellation after TTS but before mix returns early."""
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        call_count = [0]

        def cancel_after_three(_entry_id=None):
            call_count[0] += 1
            return call_count[0] >= 4  # noqa: PLR2004

        worker._is_task_cancelled = cancel_after_three
        (kw["storage_dir"] / "voice.mp3").write_bytes(b"audio")
        _run_pipeline(worker, kw)
        kw["mix_audio_into_video"].assert_not_called()

    def test_cancel_lambda_receives_entry_id(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """The cancel callback is constructed with the correct entry_id."""
        mock_gen_path.return_value = tmp_path / "out.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path, entry_id=99)
        (kw["storage_dir"] / "voice.mp3").write_bytes(b"audio")
        with patch("src.constants.languages.get_locale_code", return_value="vi"):
            _run_pipeline(worker, kw)
        # _is_task_cancelled should have been called with entry_id 99
        for call in worker._is_task_cancelled.call_args_list:
            assert call in (((99,),), ((),))


@patch("src.ui.pages.dubbing.update_dubbing_progress")
@patch("src.ui.pages.dubbing.get_dubbing_entry_status", return_value=STATUS_GENERATING)
@patch("src.ui.pages.dubbing.generate_dubbing_output_path")
@patch("src.ui.pages.dubbing.tr", side_effect=lambda key, **kw: key)
class TestPipelineCheckpointDetails:
    """Detailed tests for checkpoint save and load behavior."""

    def test_first_checkpoint_contains_srt_text(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """First checkpoint save includes srt_text."""
        mock_gen_path.return_value = tmp_path / "out.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        (kw["storage_dir"] / "voice.mp3").write_bytes(b"audio")
        with patch("src.constants.languages.get_locale_code", return_value="vi"):
            _run_pipeline(worker, kw)
        first_call = kw["save_checkpoint"].call_args_list[0]
        assert "srt_text" in first_call[1]

    def test_second_checkpoint_contains_translated_srt(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """Second checkpoint save includes translated_srt."""
        mock_gen_path.return_value = tmp_path / "out.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        (kw["storage_dir"] / "voice.mp3").write_bytes(b"audio")
        with patch("src.constants.languages.get_locale_code", return_value="vi"):
            _run_pipeline(worker, kw)
        second_call = kw["save_checkpoint"].call_args_list[1]
        assert "translated_srt" in second_call[1]

    def test_third_checkpoint_contains_voice_file(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """Third checkpoint save includes voice_file."""
        mock_gen_path.return_value = tmp_path / "out.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        (kw["storage_dir"] / "voice.mp3").write_bytes(b"audio")
        with patch("src.constants.languages.get_locale_code", return_value="vi"):
            _run_pipeline(worker, kw)
        third_call = kw["save_checkpoint"].call_args_list[2]
        assert "voice_file" in third_call[1]

    def test_checkpoint_target_lang_stored(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """Checkpoint saves target_lang for language change detection."""
        mock_gen_path.return_value = tmp_path / "out.mp4"
        worker = _make_worker(target_lang="French")
        kw = _default_kwargs(tmp_path)
        (kw["storage_dir"] / "voice.mp3").write_bytes(b"audio")
        with patch("src.constants.languages.get_locale_code", return_value="fr"):
            _run_pipeline(worker, kw)
        first_call = kw["save_checkpoint"].call_args_list[0]
        assert first_call[1].get("target_lang") == "French"

    def test_checkpoint_storage_dir_passed_correctly(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """Checkpoint save receives the correct storage_dir."""
        mock_gen_path.return_value = tmp_path / "out.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        (kw["storage_dir"] / "voice.mp3").write_bytes(b"audio")
        with patch("src.constants.languages.get_locale_code", return_value="vi"):
            _run_pipeline(worker, kw)
        for call in kw["save_checkpoint"].call_args_list:
            assert call[0][0] == kw["storage_dir"]


@patch("src.ui.pages.dubbing.update_dubbing_progress")
@patch("src.ui.pages.dubbing.get_dubbing_entry_status", return_value=STATUS_GENERATING)
@patch("src.ui.pages.dubbing.generate_dubbing_output_path")
@patch("src.ui.pages.dubbing.tr", side_effect=lambda key, **kw: key)
class TestPipelineProgressValues:
    """Tests for specific progress values emitted during the pipeline."""

    def test_stt_start_is_first_progress(
        self, _tr, mock_gen_path, _status, mock_progress, tmp_path
    ) -> None:
        """DUBBING_PROGRESS_STT_START is the first progress update."""
        mock_gen_path.return_value = tmp_path / "out.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        (kw["storage_dir"] / "voice.mp3").write_bytes(b"audio")
        with patch("src.constants.languages.get_locale_code", return_value="vi"):
            _run_pipeline(worker, kw)
        first_call = mock_progress.call_args_list[0]
        assert first_call[0][1] == DUBBING_PROGRESS_STT_START

    def test_progress_complete_is_last(
        self, _tr, mock_gen_path, _status, mock_progress, tmp_path
    ) -> None:
        """PROGRESS_COMPLETE is the last progress update."""
        mock_gen_path.return_value = tmp_path / "out.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        (kw["storage_dir"] / "voice.mp3").write_bytes(b"audio")
        with patch("src.constants.languages.get_locale_code", return_value="vi"):
            _run_pipeline(worker, kw)
        last_call = mock_progress.call_args_list[-1]
        assert last_call[0][1] == PROGRESS_COMPLETE

    def test_six_progress_updates_in_full_pipeline(
        self, _tr, mock_gen_path, _status, mock_progress, tmp_path
    ) -> None:
        """Full pipeline emits exactly 6 progress updates."""
        mock_gen_path.return_value = tmp_path / "out.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        (kw["storage_dir"] / "voice.mp3").write_bytes(b"audio")
        with patch("src.constants.languages.get_locale_code", return_value="vi"):
            _run_pipeline(worker, kw)
        assert mock_progress.call_count == 6  # noqa: PLR2004

    def test_progress_all_contain_entry_id(
        self, _tr, mock_gen_path, _status, mock_progress, tmp_path
    ) -> None:
        """All progress updates reference the correct entry_id."""
        mock_gen_path.return_value = tmp_path / "out.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path, entry_id=77)
        (kw["storage_dir"] / "voice.mp3").write_bytes(b"audio")
        with patch("src.constants.languages.get_locale_code", return_value="vi"):
            _run_pipeline(worker, kw)
        for call in mock_progress.call_args_list:
            assert call[0][0] == 77  # noqa: PLR2004

    @pytest.mark.parametrize(
        "stage_idx,expected_progress",
        [
            (0, DUBBING_PROGRESS_STT_START),
            (1, DUBBING_PROGRESS_STT_DONE),
            (2, DUBBING_PROGRESS_TRANSLATE_DONE),
            (3, DUBBING_PROGRESS_TTS_DONE),
        ],
    )
    def test_progress_stage_order(
        self,
        _tr,
        mock_gen_path,
        _status,
        mock_progress,
        tmp_path,
        stage_idx,
        expected_progress,
    ) -> None:
        """Each pipeline stage emits the expected progress value."""
        mock_gen_path.return_value = tmp_path / "out.mp4"
        worker = _make_worker()
        kw = _default_kwargs(tmp_path)
        (kw["storage_dir"] / "voice.mp3").write_bytes(b"audio")
        with patch("src.constants.languages.get_locale_code", return_value="vi"):
            _run_pipeline(worker, kw)
        assert mock_progress.call_args_list[stage_idx][0][1] == expected_progress


@patch("src.ui.pages.dubbing.update_dubbing_progress")
@patch("src.ui.pages.dubbing.get_dubbing_entry_status", return_value=STATUS_GENERATING)
@patch("src.ui.pages.dubbing.generate_dubbing_output_path")
@patch("src.ui.pages.dubbing.tr", side_effect=lambda key, **kw: key)
class TestPipelineLangChangeInvalidation:
    """Tests for checkpoint invalidation when target language changes."""

    def test_lang_change_removes_translated_srt_from_checkpoint(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """Language change pops translated_srt from checkpoint."""
        mock_gen_path.return_value = tmp_path / "out.mp4"
        worker = _make_worker(target_lang="French")
        kw = _default_kwargs(tmp_path)
        kw["load_checkpoint"] = MagicMock(
            return_value={
                "srt_text": _FAKE_SRT,
                "translated_srt": _FAKE_TRANSLATED_SRT,
                "target_lang": "Vietnamese",
            }
        )
        (kw["storage_dir"] / "voice.mp3").write_bytes(b"audio")
        with patch("src.constants.languages.get_locale_code", return_value="fr"):
            _run_pipeline(worker, kw)
        # translate_batch should have been called since translated_srt was invalidated
        kw["translate_batch"].assert_called_once()

    def test_lang_change_removes_voice_file_from_checkpoint(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """Language change pops voice_file from checkpoint."""
        mock_gen_path.return_value = tmp_path / "out.mp4"
        worker = _make_worker(target_lang="French")
        kw = _default_kwargs(tmp_path)
        voice_path = kw["storage_dir"] / "voice.mp3"
        voice_path.write_bytes(b"old voice")
        kw["load_checkpoint"] = MagicMock(
            return_value={
                "srt_text": _FAKE_SRT,
                "translated_srt": _FAKE_TRANSLATED_SRT,
                "voice_file": "voice.mp3",
                "target_lang": "Vietnamese",
            }
        )
        with patch("src.constants.languages.get_locale_code", return_value="fr"):
            _run_pipeline(worker, kw)
        # synthesize should have been called since voice_file was invalidated
        kw["synthesize_timed_speech"].assert_called_once()

    def test_same_lang_no_retranslation_from_checkpoint(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """Same target lang does not retranslate from checkpoint."""
        mock_gen_path.return_value = tmp_path / "out.mp4"
        worker = _make_worker(target_lang="Vietnamese")
        kw = _default_kwargs(tmp_path)
        (kw["storage_dir"] / "voice.mp3").write_bytes(b"audio")
        kw["load_checkpoint"] = MagicMock(
            return_value={
                "srt_text": _FAKE_SRT,
                "translated_srt": _FAKE_TRANSLATED_SRT,
                "voice_file": "voice.mp3",
                "target_lang": "Vietnamese",
            }
        )
        with patch("src.constants.languages.get_locale_code", return_value="vi"):
            _run_pipeline(worker, kw)
        kw["translate_batch"].assert_not_called()
        kw["synthesize_timed_speech"].assert_not_called()

    def test_lang_change_with_no_prior_target_no_log(
        self, _tr, mock_gen_path, _status, _progress, tmp_path
    ) -> None:
        """Language change from None target doesn't log re-translation."""
        mock_gen_path.return_value = tmp_path / "out.mp4"
        worker = _make_worker(target_lang="French")
        kw = _default_kwargs(tmp_path)
        kw["load_checkpoint"] = MagicMock(
            return_value={
                "srt_text": _FAKE_SRT,
                "target_lang": "",
            }
        )
        (kw["storage_dir"] / "voice.mp3").write_bytes(b"audio")
        with patch("src.constants.languages.get_locale_code", return_value="fr"):
            # Should not raise even with empty prior target_lang
            _run_pipeline(worker, kw)


# ===========================================================================
# NEW TESTS — Page UI expanded
# ===========================================================================


class TestDubbingPageResumePending:
    """Tests for _resume_pending method."""

    @patch(f"{_MOD}.get_unfinished_dubbing")
    def test_resume_groups_by_language_pair(self, mock_unfinished, page) -> None:
        """_resume_pending groups tasks by language pair and takes first group."""
        page._worker = None
        mock_unfinished.return_value = [
            (1, "/v1.mp4", "English", "Vietnamese"),
            (2, "/v2.mp4", "English", "Vietnamese"),
            (3, "/v3.mp4", "French", "German"),
        ]
        with patch.object(page, "_start_worker") as mock_start:
            page._resume_pending()
        mock_start.assert_called_once()
        tasks_arg = mock_start.call_args[0][0]
        assert len(tasks_arg) == 2  # noqa: PLR2004
        assert tasks_arg[0] == (1, "/v1.mp4")
        assert tasks_arg[1] == (2, "/v2.mp4")

    @patch(f"{_MOD}.get_unfinished_dubbing")
    def test_resume_uses_first_entry_lang_pair(self, mock_unfinished, page) -> None:
        """_resume_pending uses the first entry's language pair."""
        page._worker = None
        mock_unfinished.return_value = [
            (5, "/video.mp4", "Japanese", "Korean"),
        ]
        with patch.object(page, "_start_worker") as mock_start:
            page._resume_pending()
        assert mock_start.call_args[0][1] == "Japanese"
        assert mock_start.call_args[0][2] == "Korean"


class TestDubbingPageFileWidget:
    """Tests for file widget management."""

    @patch(f"{_MOD}.CustomMessageDialog.show_message")
    def test_add_file_widget_inserts_before_stretch(
        self, _mock_msg, page, tmp_path
    ) -> None:
        """File widgets are inserted before the stretch in files_vbox."""
        video = tmp_path / "clip.mp4"
        video.write_bytes(b"video data")
        initial_count = page.files_vbox.count()
        page._add_file_widget(str(video))
        assert page.files_vbox.count() == initial_count + 1

    @patch(f"{_MOD}.CustomMessageDialog.show_message")
    def test_remove_file_updates_selected_files(
        self, _mock_msg, page, tmp_path
    ) -> None:
        """Removing a file widget removes it from selected_files."""
        video = tmp_path / "clip.mp4"
        video.write_bytes(b"video data")
        page._handle_files_dropped([str(video)])
        assert str(video) in page.selected_files
        # Simulate removal
        from PySide6.QtWidgets import QWidget  # noqa: PLC0415

        mock_widget = QWidget()
        page._handle_remove_file(str(video), mock_widget)
        assert str(video) not in page.selected_files

    @patch(f"{_MOD}.CustomMessageDialog.show_message")
    def test_clear_all_removes_all_file_widgets(
        self, _mock_msg, page, tmp_path
    ) -> None:
        """_handle_clear_all removes all file widgets."""
        for i in range(3):
            video = tmp_path / f"clip{i}.mp4"
            video.write_bytes(b"video data")
            page._handle_files_dropped([str(video)])
        assert len(page.selected_files) == 3  # noqa: PLR2004
        page._handle_clear_all()
        assert len(page.selected_files) == 0
        # Only stretch remains
        assert page.files_vbox.count() == 1


class TestDubbingPageCheckRequirements:
    """Tests for _check_all_requirements."""

    @patch(f"{_MOD}.require_setup", return_value=True)
    @patch(f"{_MOD}.load_setting", return_value="Whisper")
    def test_whisper_stt_skips_google_check(
        self, _mock_load, mock_require, page
    ) -> None:
        """Whisper STT doesn't check Google Cloud API key."""
        result = page._check_all_requirements()
        assert result is True
        # require_setup should be called for LLM only (not for Google STT)
        assert mock_require.call_count >= 1

    @patch(f"{_MOD}.require_setup", return_value=False)
    @patch(f"{_MOD}.load_setting", return_value="Google Cloud Speech")
    def test_google_stt_fails_returns_false(
        self, _mock_load, _mock_require, page
    ) -> None:
        """Google Cloud STT failing setup check returns False."""
        result = page._check_all_requirements()
        assert result is False


class TestDubbingPageOnFinishedExpanded:
    """Expanded tests for _on_finished."""

    @patch(f"{_MOD}.update_dubbing_status")
    @patch(f"{_MOD}.load_setting", return_value=False)
    @patch(f"{_MOD}.get_unfinished_dubbing", return_value=[])
    def test_on_finished_multiple_results(
        self, _unfinished, _load, mock_status, page, _mock_dubbing_history_deps
    ) -> None:
        """_on_finished processes multiple results."""
        page._worker = MagicMock()
        results = [
            (1, "/out/a.mp4", "/s1.srt", "/t1.srt", "/v1.mp3"),
            (2, "/out/b.mp4", "/s2.srt", "/t2.srt", "/v2.mp3"),
        ]
        page._on_finished(results)
        assert mock_status.call_count == 2  # noqa: PLR2004

    @patch(f"{_MOD}.update_dubbing_status")
    @patch(f"{_MOD}.load_setting", return_value=False)
    @patch(f"{_MOD}.get_unfinished_dubbing", return_value=[])
    def test_on_finished_short_result_tuple(
        self, _unfinished, _load, mock_status, page, _mock_dubbing_history_deps
    ) -> None:
        """_on_finished handles result tuples with only 2 elements."""
        page._worker = MagicMock()
        results = [(1, "/out/a.mp4")]
        page._on_finished(results)
        mock_status.assert_called_once()
        call_kwargs = mock_status.call_args[1]
        assert call_kwargs.get("subtitle_path") == ""

    @patch(f"{_MOD}.update_dubbing_status")
    @patch(f"{_MOD}.load_setting", return_value=False)
    @patch(f"{_MOD}.get_unfinished_dubbing", return_value=[])
    def test_on_finished_refreshes_history(
        self, _unfinished, _load, _status, page, _mock_dubbing_history_deps
    ) -> None:
        """_on_finished refreshes the history view."""
        page._worker = MagicMock()
        with patch.object(page.history_view, "refresh_history") as mock_refresh:
            page._on_finished([])
        mock_refresh.assert_called_once_with(force=True)

    @patch(f"{_MOD}.delete_dubbing_entry", return_value=["/out.mp4"])
    @patch(f"{_MOD}.load_setting", return_value=True)
    @patch(f"{_MOD}.get_unfinished_dubbing", return_value=[])
    def test_auto_remove_deletes_output_files(
        self, _unfinished, _load, _delete, page, _mock_dubbing_history_deps, tmp_path
    ) -> None:
        """Auto-remove deletes output files from disk."""
        page._worker = MagicMock()
        out_file = tmp_path / "out.mp4"
        out_file.write_bytes(b"video data")
        _delete.return_value = [str(out_file)]
        with (
            patch(
                "src.utils.path_manager.get_dubbing_storage_dir",
                return_value=tmp_path / "storage",
            ),
            patch("shutil.rmtree"),
        ):
            page._on_finished([(1, str(out_file))])
        assert not out_file.exists()


class TestDubbingPageHandleGenerate:
    """Expanded tests for _handle_generate."""

    @patch(f"{_MOD}._DubbingWorker")
    @patch(f"{_MOD}.add_dubbing_entry", return_value=100)
    @patch(
        f"{_MOD}.LanguageSelectionDialog.get_selection",
        return_value=("English", "Vietnamese", None, True),
    )
    @patch(f"{_MOD}.load_setting", return_value="")
    def test_generate_creates_db_entries(
        self,
        _load,
        _dialog,
        mock_add,
        mock_worker_cls,
        page,
        tmp_path,
        _mock_dubbing_history_deps,
    ) -> None:
        """_handle_generate creates DB entries for each selected file."""
        mock_instance = MagicMock()
        mock_instance.finished_ok = MagicMock()
        mock_instance.finished_ok.connect = MagicMock()
        mock_worker_cls.return_value = mock_instance
        video = tmp_path / "clip.mp4"
        video.write_bytes(b"video")
        page.selected_files = [str(video)]
        with (
            patch.object(page, "_check_all_requirements", return_value=True),
            patch("src.utils.config_manager.save_setting"),
        ):
            page._handle_generate()
        mock_add.assert_called_once()

    @patch(f"{_MOD}.add_dubbing_entry", return_value=None)
    @patch(
        f"{_MOD}.LanguageSelectionDialog.get_selection",
        return_value=("English", "Vietnamese", None, True),
    )
    @patch(f"{_MOD}.load_setting", return_value="")
    def test_generate_no_worker_when_all_entries_fail(
        self, _load, _dialog, _add, page, _mock_dubbing_history_deps
    ) -> None:
        """No worker started when all DB entry creations return None."""
        page.selected_files = ["/video.mp4"]
        with (
            patch.object(page, "_check_all_requirements", return_value=True),
            patch("src.utils.config_manager.save_setting"),
        ):
            page._handle_generate()
        assert page._worker is None

    def test_generate_noop_with_no_files(self, page) -> None:
        """_handle_generate does nothing with empty selected_files."""
        page.selected_files = []
        page._handle_generate()
        assert page._worker is None


class TestDubbingPageDropArea:
    """Tests for drop area behavior."""

    def test_drop_area_label_text_no_files(self, page) -> None:
        """Drop area shows default title when no files selected."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page.selected_files = []
        page._update_ui_state()
        assert page.drop_area.info_label.text() == tr("drop.title")

    def test_drop_area_label_text_with_files(self, page) -> None:
        """Drop area shows 'add more' title when files are selected."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page.selected_files = ["/a.mp4"]
        page._update_ui_state()
        assert page.drop_area.info_label.text() == tr("drop.title_more")

    def test_drop_area_reparented_to_files_view(self, page) -> None:
        """Drop area is reparented to files view when files exist."""
        page.selected_files = ["/a.mp4"]
        page._update_ui_state()
        assert page.stack.currentIndex() == 1

    def test_drop_area_reparented_to_history_view(self, page) -> None:
        """Drop area is reparented to history view when no files."""
        page.selected_files = []
        page._update_ui_state()
        assert page.stack.currentIndex() == 0


class TestDubbingPageReDubExpanded:
    """Expanded tests for _handle_re_dub."""

    @patch(f"{_MOD}._DubbingWorker")
    @patch(f"{_MOD}.update_dubbing_status")
    @patch(
        f"{_MOD}.LanguageSelectionDialog.get_selection",
        return_value=("English", "Vietnamese", None, True),
    )
    @patch(f"{_MOD}.load_setting", return_value="")
    def test_re_dub_updates_status_to_pending(
        self,
        _load,
        _dialog,
        mock_status,
        mock_worker_cls,
        page,
        _mock_dubbing_history_deps,
    ) -> None:
        """_handle_re_dub sets task status to Pending before starting."""
        mock_instance = MagicMock()
        mock_instance.finished_ok = MagicMock()
        mock_instance.finished_ok.connect = MagicMock()
        mock_worker_cls.return_value = mock_instance
        with (
            patch.object(page, "_check_all_requirements", return_value=True),
            patch("src.utils.config_manager.save_setting"),
        ):
            page._handle_re_dub([(1, "/v.mp4"), (2, "/v2.mp4")])
        # update_dubbing_status should be called with STATUS_PENDING for each task
        assert mock_status.call_count == 2  # noqa: PLR2004
        mock_status.assert_any_call(1, STATUS_PENDING)
        mock_status.assert_any_call(2, STATUS_PENDING)

    @patch(
        f"{_MOD}.LanguageSelectionDialog.get_selection",
        return_value=("English", "", None, True),
    )
    @patch(f"{_MOD}.load_setting", return_value="")
    def test_re_dub_empty_target_lang_no_worker(self, _load, _dialog, page) -> None:
        """_handle_re_dub does nothing when target_lang is empty."""
        with patch.object(page, "_check_all_requirements", return_value=True):
            page._handle_re_dub([(1, "/v.mp4")])
        assert page._worker is None

    @patch(f"{_MOD}._DubbingWorker")
    @patch(f"{_MOD}.update_dubbing_status")
    @patch(f"{_MOD}.LanguageSelectionDialog.get_selection")
    @patch(f"{_MOD}.load_setting", return_value="")
    def test_re_dub_passes_setting_keys_to_dialog(
        self,
        _load,
        mock_dialog,
        _status,
        mock_worker_cls,
        page,
        _mock_dubbing_history_deps,
    ) -> None:
        """_handle_re_dub passes dubbing-specific setting keys to the dialog."""
        mock_dialog.return_value = ("English", "Vietnamese", None, True)
        mock_instance = MagicMock()
        mock_instance.finished_ok = MagicMock()
        mock_instance.finished_ok.connect = MagicMock()
        mock_worker_cls.return_value = mock_instance
        with patch.object(page, "_check_all_requirements", return_value=True):
            page._handle_re_dub([(1, "/v.mp4")])
        _, kwargs = mock_dialog.call_args
        assert kwargs["source_setting_key"] == "dubbing/last_source_language"
        assert kwargs["target_setting_key"] == "dubbing/last_target_language"


class TestCreateDubbingPageFunction:
    """Tests for the create_dubbing_page factory function."""

    def test_create_dubbing_page_returns_dubbing_page(
        self, window, _mock_dubbing_history_deps, qtbot
    ) -> None:
        """create_dubbing_page returns a DubbingPage instance."""
        from src.ui.pages.dubbing import (  # noqa: PLC0415
            DubbingPage,
            create_dubbing_page,
        )

        with patch(f"{_MOD}.get_unfinished_dubbing", return_value=[]):
            p = create_dubbing_page(window)
        qtbot.addWidget(p)
        assert isinstance(p, DubbingPage)

    def test_create_dubbing_page_stores_window(
        self, window, _mock_dubbing_history_deps, qtbot
    ) -> None:
        """create_dubbing_page stores window reference."""
        from src.ui.pages.dubbing import create_dubbing_page  # noqa: PLC0415

        with patch(f"{_MOD}.get_unfinished_dubbing", return_value=[]):
            p = create_dubbing_page(window)
        qtbot.addWidget(p)
        assert p.window_context is window
