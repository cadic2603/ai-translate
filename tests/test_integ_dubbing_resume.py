"""Integration tests for the dubbing pipeline pause / resume.

Exercises ``_DubbingWorker._run_dubbing_pipeline`` directly via __new__()
so we don't need a real QThread.  Real checkpoint files on tmp_path,
real DB entries, real subtitle parse/serialize.  STT, translate, TTS,
and mix callables are mocked.
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest

from src.constants.history import (
    STATUS_GENERATING,
    STATUS_PAUSED,
    STATUS_PENDING,
)
from src.core.checkpoint import (
    load_dubbing_checkpoint,
    save_dubbing_checkpoint,
)
from src.core.database import (
    add_dubbing_entry,
    get_dubbing_entry_status,
    init_db,
    update_dubbing_status,
)
from src.utils.subtitle_utils import parse_subtitle, serialize_subtitle

_FAKE_AUDIO = b"\x00" * 1024
_FAKE_VIDEO = b"\x00" * 2048

_SRT_TEXT = (
    "1\n00:00:01,000 --> 00:00:04,000\nHello world\n\n"
    "2\n00:00:05,000 --> 00:00:08,000\nThis is a test\n"
)


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def setup_integration_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Generator[None, None, None]:
    """Per-test DB isolation + path redirection."""
    db_file = tmp_path / "integration.db"
    monkeypatch.setattr("src.core.database.get_db_path", lambda: str(db_file))
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    monkeypatch.setattr(
        "src.utils.path_manager.get_app_config_dir",
        lambda: config_dir,
    )
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr(
        "src.utils.path_manager.get_app_data_dir",
        lambda: data_dir,
    )
    init_db()
    yield


@pytest.fixture()
def video_path(tmp_path: Path) -> Path:
    """Creates a fake video file."""
    video = tmp_path / "input.mp4"
    video.write_bytes(_FAKE_VIDEO)
    return video


@pytest.fixture()
def storage_dir(tmp_path: Path) -> Path:
    """Creates a fresh storage directory for the dubbing task."""
    d = tmp_path / "dub_storage"
    d.mkdir()
    return d


# ── Worker construction helper ───────────────────────────────────────


def _make_worker(
    src_lang: str = "English (US)",
    target_lang: str = "French",
    voice_gender: str = "FEMALE",
) -> Any:
    """Builds a _DubbingWorker instance bypassing QThread.__init__.

    Mirrors the pattern used by the page-worker tests in test_dubbing.py.
    """
    from src.ui.pages.dubbing import _DubbingWorker  # noqa: PLC0415

    worker = _DubbingWorker.__new__(_DubbingWorker)
    worker._src_lang = src_lang
    worker._target_lang = target_lang
    worker._voice_gender = voice_gender
    worker._is_running = True
    worker._tasks = []
    return worker


def _add_dubbing_entry(video_path: Path) -> int:
    """Adds a dubbing history entry in the DB and returns the ID."""
    return add_dubbing_entry(
        file_name=video_path.name,
        file_size=video_path.stat().st_size,
        source_path=str(video_path),
        output_path=str(video_path.parent / f"dub_{video_path.name}"),
        status=STATUS_PENDING,
        src_lang="English (US)",
        target_lang="French",
    )


# ── Tests ────────────────────────────────────────────────────────────


def test_cancel_during_tts_persists_translation_checkpoint(
    tmp_path: Path,
    video_path: Path,
    storage_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cancel during TTS → STT + translation checkpoints persist; mix not run.

    This places the cancel point AFTER the translate step's
    save_checkpoint() call, so the translated_srt key has time to land on
    disk before cancellation observes it.  Demonstrates the resume-from-
    translation-checkpoint guarantee.
    """
    entry_id = _add_dubbing_entry(video_path)
    update_dubbing_status(entry_id, STATUS_GENERATING)

    stt_calls: list[str] = []
    translate_calls: list[list[str]] = []
    tts_calls: list[Any] = []
    mix_calls: list[Any] = []

    def fake_stt(file_path: str, **kwargs: Any) -> str:
        stt_calls.append(file_path)
        return _SRT_TEXT

    def fake_translate(values: list[str], **kwargs: Any) -> list[str]:
        translate_calls.append(list(values))
        return [f"[FR] {v}" for v in values]

    def cancelling_tts(*args: Any, **kwargs: Any) -> None:
        tts_calls.append((args, kwargs))
        # Abort TTS immediately by stopping the worker; produce no audio.
        worker._is_running = False

    def fake_mix(video: str, audio: str, output: str) -> None:
        mix_calls.append((video, audio, output))
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_bytes(_FAKE_AUDIO)

    worker = _make_worker()
    results: list[Any] = []

    worker._run_dubbing_pipeline(
        entry_id,
        str(video_path),
        storage_dir,
        stt_method="Whisper",
        model_size="base",
        tts_method="Edge TTS",
        audio_fmt=".mp3",
        glossary_entries=None,
        transcribe_audio=fake_stt,
        translate_batch=fake_translate,
        parse_subtitle=parse_subtitle,
        serialize_subtitle=serialize_subtitle,
        synthesize_timed_speech=cancelling_tts,
        mix_audio_into_video=fake_mix,
        save_checkpoint=save_dubbing_checkpoint,
        load_checkpoint=load_dubbing_checkpoint,
        results=results,
    )

    # STT, translate, and TTS were entered; mix was not.
    assert len(stt_calls) == 1
    assert len(translate_calls) == 1
    assert len(tts_calls) == 1
    assert mix_calls == []
    assert results == []

    # STT + translation checkpoints persist; voice_file does NOT (TTS aborted).
    # ``srt_text`` keeps the raw STT output (the post-translate save no
    # longer overwrites it), and ``translated_srt`` is the translated copy.
    ckpt = load_dubbing_checkpoint(storage_dir)
    assert ckpt is not None
    assert ckpt.get("srt_text") == _SRT_TEXT
    assert ckpt.get("translated_srt", "").strip()
    assert ckpt.get("translated_srt") != ckpt.get("srt_text")
    assert ckpt.get("target_lang") == "French"
    assert not ckpt.get("voice_file")


def test_resume_skips_stt_runs_translate_tts_mix(
    tmp_path: Path,
    video_path: Path,
    storage_dir: Path,
) -> None:
    """Resume from STT-only checkpoint → STT skipped; translate, TTS, mix run."""
    # Pre-seed an STT checkpoint (simulates a prior cancelled run).
    save_dubbing_checkpoint(
        storage_dir,
        srt_text=_SRT_TEXT,
        target_lang="French",
    )

    entry_id = _add_dubbing_entry(video_path)
    update_dubbing_status(entry_id, STATUS_GENERATING)

    stt_calls: list[Any] = []
    translate_calls: list[list[str]] = []
    tts_calls: list[Any] = []
    mix_calls: list[Any] = []

    def fake_stt(*args: Any, **kwargs: Any) -> str:
        stt_calls.append((args, kwargs))
        return _SRT_TEXT

    def fake_translate(values: list[str], **kwargs: Any) -> list[str]:
        translate_calls.append(list(values))
        return [f"[FR] {v}" for v in values]

    def fake_tts(*args: Any, **kwargs: Any) -> None:
        tts_calls.append((args, kwargs))
        out_path = Path(kwargs.get("output_path") or args[3])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(_FAKE_AUDIO)

    def fake_mix(video: str, audio: str, output: str) -> None:
        mix_calls.append((video, audio, output))
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_bytes(_FAKE_AUDIO)

    worker = _make_worker()
    results: list[Any] = []
    worker._run_dubbing_pipeline(
        entry_id,
        str(video_path),
        storage_dir,
        stt_method="Whisper",
        model_size="base",
        tts_method="Edge TTS",
        audio_fmt=".mp3",
        glossary_entries=None,
        transcribe_audio=fake_stt,
        translate_batch=fake_translate,
        parse_subtitle=parse_subtitle,
        serialize_subtitle=serialize_subtitle,
        synthesize_timed_speech=fake_tts,
        mix_audio_into_video=fake_mix,
        save_checkpoint=save_dubbing_checkpoint,
        load_checkpoint=load_dubbing_checkpoint,
        results=results,
    )

    # STT was NOT re-run.
    assert stt_calls == []
    # Translate, TTS, mix all ran.
    assert len(translate_calls) == 1
    assert translate_calls[0] == ["Hello world", "This is a test"]
    assert len(tts_calls) == 1
    assert len(mix_calls) == 1
    # Successful result tuple appended.
    assert len(results) == 1
    assert results[0][0] == entry_id


def test_resume_from_translation_checkpoint_skips_stt_and_translate(
    tmp_path: Path,
    video_path: Path,
    storage_dir: Path,
) -> None:
    """Pre-seeded translated_srt → STT skipped, translate skipped, TTS runs."""
    translated_srt = (
        "1\n00:00:01,000 --> 00:00:04,000\n[FR] Hello world\n\n"
        "2\n00:00:05,000 --> 00:00:08,000\n[FR] This is a test\n"
    )
    save_dubbing_checkpoint(
        storage_dir,
        srt_text=_SRT_TEXT,
        translated_srt=translated_srt,
        target_lang="French",
    )

    entry_id = _add_dubbing_entry(video_path)
    update_dubbing_status(entry_id, STATUS_GENERATING)

    stt_calls: list[Any] = []
    translate_calls: list[Any] = []
    tts_calls: list[Any] = []
    mix_calls: list[Any] = []

    def boom_stt(*args: Any, **kwargs: Any) -> str:
        stt_calls.append((args, kwargs))
        return _SRT_TEXT

    def boom_translate(values: list[str], **kwargs: Any) -> list[str]:
        translate_calls.append(list(values))
        return [f"[FR] {v}" for v in values]

    def fake_tts(*args: Any, **kwargs: Any) -> None:
        tts_calls.append((args, kwargs))
        out_path = Path(kwargs.get("output_path") or args[3])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(_FAKE_AUDIO)

    def fake_mix(video: str, audio: str, output: str) -> None:
        mix_calls.append((video, audio, output))
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_bytes(_FAKE_AUDIO)

    worker = _make_worker()
    results: list[Any] = []
    worker._run_dubbing_pipeline(
        entry_id,
        str(video_path),
        storage_dir,
        stt_method="Whisper",
        model_size="base",
        tts_method="Edge TTS",
        audio_fmt=".mp3",
        glossary_entries=None,
        transcribe_audio=boom_stt,
        translate_batch=boom_translate,
        parse_subtitle=parse_subtitle,
        serialize_subtitle=serialize_subtitle,
        synthesize_timed_speech=fake_tts,
        mix_audio_into_video=fake_mix,
        save_checkpoint=save_dubbing_checkpoint,
        load_checkpoint=load_dubbing_checkpoint,
        results=results,
    )

    assert stt_calls == []
    assert translate_calls == []
    assert len(tts_calls) == 1
    assert len(mix_calls) == 1


def test_cancel_during_tts_keeps_translation_checkpoint(
    tmp_path: Path,
    video_path: Path,
    storage_dir: Path,
) -> None:
    """Cancel during TTS → translation checkpoint survives, voice not finalised."""
    entry_id = _add_dubbing_entry(video_path)
    update_dubbing_status(entry_id, STATUS_GENERATING)

    def fake_stt(*args: Any, **kwargs: Any) -> str:
        return _SRT_TEXT

    def fake_translate(values: list[str], **kwargs: Any) -> list[str]:
        return [f"[FR] {v}" for v in values]

    tts_progress_seen: list[tuple[int, int]] = []

    def cancelling_tts(*args: Any, **kwargs: Any) -> None:
        # Emit one progress tick, then flip cancel.
        cb = kwargs.get("on_progress")
        if cb:
            cb(1, 2)
            tts_progress_seen.append((1, 2))
        worker._is_running = False
        # Don't write any output file — simulate aborted synthesis.

    mix_calls: list[Any] = []

    def fake_mix(video: str, audio: str, output: str) -> None:
        mix_calls.append((video, audio, output))

    worker = _make_worker()
    results: list[Any] = []
    worker._run_dubbing_pipeline(
        entry_id,
        str(video_path),
        storage_dir,
        stt_method="Whisper",
        model_size="base",
        tts_method="Edge TTS",
        audio_fmt=".mp3",
        glossary_entries=None,
        transcribe_audio=fake_stt,
        translate_batch=fake_translate,
        parse_subtitle=parse_subtitle,
        serialize_subtitle=serialize_subtitle,
        synthesize_timed_speech=cancelling_tts,
        mix_audio_into_video=fake_mix,
        save_checkpoint=save_dubbing_checkpoint,
        load_checkpoint=load_dubbing_checkpoint,
        results=results,
    )

    # Mix never ran; results never appended.
    assert mix_calls == []
    assert results == []
    # Translation checkpoint persists (so Resume can skip translate).
    ckpt = load_dubbing_checkpoint(storage_dir)
    assert ckpt is not None
    assert "srt_text" in ckpt
    assert "translated_srt" in ckpt
    # voice_file should NOT be in the checkpoint because TTS aborted before
    # save_checkpoint(voice_file=...) was called.
    assert "voice_file" not in ckpt or not ckpt.get("voice_file")


def test_target_language_change_invalidates_translation_checkpoint(
    tmp_path: Path,
    video_path: Path,
    storage_dir: Path,
) -> None:
    """Resume with a different target_lang → translated_srt is dropped."""
    # Pre-seed translation checkpoint for German.
    save_dubbing_checkpoint(
        storage_dir,
        srt_text=_SRT_TEXT,
        translated_srt="1\n00:00:01,000 --> 00:00:04,000\n[DE] Hello world\n",
        voice_file="voice.mp3",
        target_lang="German",
    )
    # Place a stale voice file that should be removed.
    (storage_dir / "voice.mp3").write_bytes(_FAKE_AUDIO)

    entry_id = _add_dubbing_entry(video_path)
    update_dubbing_status(entry_id, STATUS_GENERATING)

    translate_calls: list[list[str]] = []
    tts_calls: list[Any] = []

    def fake_translate(values: list[str], **kwargs: Any) -> list[str]:
        translate_calls.append(list(values))
        return [f"[FR] {v}" for v in values]

    def fake_tts(*args: Any, **kwargs: Any) -> None:
        tts_calls.append((args, kwargs))
        out_path = Path(kwargs.get("output_path") or args[3])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(_FAKE_AUDIO)

    def fake_mix(video: str, audio: str, output: str) -> None:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_bytes(_FAKE_AUDIO)

    # Worker now targets French, not German.
    worker = _make_worker(target_lang="French")
    results: list[Any] = []
    worker._run_dubbing_pipeline(
        entry_id,
        str(video_path),
        storage_dir,
        stt_method="Whisper",
        model_size="base",
        tts_method="Edge TTS",
        audio_fmt=".mp3",
        glossary_entries=None,
        transcribe_audio=lambda *a, **k: _SRT_TEXT,
        translate_batch=fake_translate,
        parse_subtitle=parse_subtitle,
        serialize_subtitle=serialize_subtitle,
        synthesize_timed_speech=fake_tts,
        mix_audio_into_video=fake_mix,
        save_checkpoint=save_dubbing_checkpoint,
        load_checkpoint=load_dubbing_checkpoint,
        results=results,
    )

    # Re-translation occurred (translated_srt was invalidated).
    assert len(translate_calls) == 1
    # TTS ran with the new translation.
    assert len(tts_calls) == 1
    # Final checkpoint reflects the new target language.
    ckpt = load_dubbing_checkpoint(storage_dir)
    assert ckpt is not None
    assert ckpt.get("target_lang") == "French"


def test_db_status_change_to_paused_aborts_pipeline(
    tmp_path: Path,
    video_path: Path,
    storage_dir: Path,
) -> None:
    """Flipping DB status to Paused mid-run is observed by _is_task_cancelled."""
    entry_id = _add_dubbing_entry(video_path)
    update_dubbing_status(entry_id, STATUS_GENERATING)

    tts_calls: list[Any] = []

    def fake_stt(*args: Any, **kwargs: Any) -> str:
        return _SRT_TEXT

    def fake_translate(values: list[str], **kwargs: Any) -> list[str]:
        return [f"[FR] {v}" for v in values]

    def tts_then_pause(*args: Any, **kwargs: Any) -> None:
        # The translate-then-TTS save_checkpoint has already landed by now.
        # Flip the DB to Paused — the next cancel check (after TTS) will
        # observe status != Generating and abort before mix.
        tts_calls.append((args, kwargs))
        update_dubbing_status(entry_id, STATUS_PAUSED)

    worker = _make_worker()
    results: list[Any] = []
    worker._run_dubbing_pipeline(
        entry_id,
        str(video_path),
        storage_dir,
        stt_method="Whisper",
        model_size="base",
        tts_method="Edge TTS",
        audio_fmt=".mp3",
        glossary_entries=None,
        transcribe_audio=fake_stt,
        translate_batch=fake_translate,
        parse_subtitle=parse_subtitle,
        serialize_subtitle=serialize_subtitle,
        synthesize_timed_speech=tts_then_pause,
        mix_audio_into_video=lambda *a, **k: None,
        save_checkpoint=save_dubbing_checkpoint,
        load_checkpoint=load_dubbing_checkpoint,
        results=results,
    )

    # TTS entered once; mix never ran.
    assert len(tts_calls) == 1
    assert results == []
    # DB status still Paused (worker doesn't override it).
    assert get_dubbing_entry_status(entry_id) == STATUS_PAUSED
    # STT and translation checkpoints survived; raw STT preserved on disk.
    ckpt = load_dubbing_checkpoint(storage_dir)
    assert ckpt is not None
    assert ckpt.get("srt_text") == _SRT_TEXT
    assert ckpt.get("translated_srt", "").strip()
    assert ckpt.get("translated_srt") != ckpt.get("srt_text")
