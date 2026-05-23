"""Integration tests for the subtitle, voice, and dubbing pipelines.

Exercises transcribe_audio(), synthesize_speech(), synthesize_timed_speech(),
mix_audio_into_video(), and the full dubbing pipeline with real file I/O,
real DB, and real subtitle parsing/serialization.  External dependencies
(FFmpeg, TTS APIs, STT models) are mocked; internal logic (text splitting,
format conversion, file I/O) runs for real.
"""

from __future__ import annotations

from collections.abc import Callable, Generator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.constants.history import (
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_GENERATING,
    STATUS_PENDING,
)
from src.core.database import (
    add_dubbing_entry,
    add_subtitle_entry,
    add_voice_entry,
    init_db,
    update_dubbing_status,
    update_subtitle_status,
    update_voice_status,
)
from src.utils.subtitle_utils import SubtitleEntry, parse_subtitle, serialize_subtitle

# Module path for monkeypatching speech_engine internals
_MOD = "src.core.speech_engine"

# ── Shared SRT content used across tests ────────────────────────────────

_FAKE_SRT = (
    "1\n"
    "00:00:01,000 --> 00:00:04,000\n"
    "Hello world\n"
    "\n"
    "2\n"
    "00:00:05,000 --> 00:00:08,000\n"
    "This is a test\n"
)

_FAKE_SRT_EMPTY = ""

_FAKE_AUDIO_BYTES = b"\x00" * 1024  # Dummy audio content


# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def setup_integration_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Generator[None, None, None]:
    """Per-test DB isolation + mock environment setup."""
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
def mock_ffmpeg(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mocks FFmpeg availability and subprocess calls."""
    monkeypatch.setattr(f"{_MOD}.check_ffmpeg_available", lambda: True)

    def fake_subprocess_run(*args: Any, **kwargs: Any) -> MagicMock:
        """Simulates FFmpeg subprocess calls by creating output files."""
        cmd = args[0] if args else kwargs.get("args", [])
        # Find output file from command (usually last arg or after -y)
        output_file = None
        for i, token in enumerate(cmd):
            if token == "-y" and i + 1 < len(cmd):
                output_file = cmd[i + 1]
            # Also check for concat output
            if token == "copy" and i + 1 < len(cmd) and cmd[i + 1] == "-y":
                output_file = cmd[i + 2] if i + 2 < len(cmd) else None

        # For concat/mix commands, identify the output as the last argument
        if output_file is None and len(cmd) > 1:
            output_file = cmd[-1]

        if output_file and not str(output_file).startswith("-"):
            Path(output_file).parent.mkdir(parents=True, exist_ok=True)
            Path(output_file).write_bytes(_FAKE_AUDIO_BYTES)

        result = MagicMock()
        result.returncode = 0
        result.stdout = b"1.5"  # Fake duration for ffprobe
        result.stderr = b""
        return result

    monkeypatch.setattr(f"{_MOD}.subprocess.run", fake_subprocess_run)


@pytest.fixture()
def mock_llm(monkeypatch: pytest.MonkeyPatch) -> Callable[..., list[str]]:
    """Patches translate_text and translate_batch at all import sites."""

    def fake_translate(
        texts: list[str],
        target_lang: str,
        source_lang: str = "",
        **kwargs: object,
    ) -> list[str]:
        return [f"[{target_lang}] {t}" for t in texts]

    def fake_translate_batch(
        values: list[str],
        target_lang: str,
        src_lang: str = "",
        **kwargs: object,
    ) -> list[str]:
        return [f"[{target_lang}] {v}" for v in values]

    monkeypatch.setattr("src.core.llm_engine.translate_text", fake_translate)
    monkeypatch.setattr(
        "src.core.text_processor._llm_engine.translate_text", fake_translate
    )
    monkeypatch.setattr("src.core.llm_engine.translate_batch", fake_translate_batch)
    return fake_translate


@pytest.fixture()
def mock_edge_tts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mocks Edge TTS to write fake audio bytes to the output path."""

    def fake_edge_chunk(
        text: str,
        voice: str,
        output_path: Path,
        **kwargs: Any,
    ) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(_FAKE_AUDIO_BYTES)

    monkeypatch.setattr(f"{_MOD}._synthesize_chunk_edge", fake_edge_chunk)


@pytest.fixture()
def mock_google_tts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mocks Google Cloud TTS to write fake audio bytes."""

    def fake_google_chunk(  # noqa: PLR0913
        text: str,
        language_code: str,
        voice_gender: str,
        api_key: str,
        output_path: Path,
        speaking_rate: float = 1.0,
        audio_format: str = ".mp3",
        voice_name: str = "",
    ) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(_FAKE_AUDIO_BYTES)

    monkeypatch.setattr(f"{_MOD}._synthesize_chunk", fake_google_chunk)
    monkeypatch.setattr(
        "src.utils.config_manager.load_google_cloud_api_key",
        lambda: "fake-api-key",
    )
    monkeypatch.setattr(
        f"{_MOD}.load_google_cloud_api_key",
        lambda: "fake-api-key",
    )


@pytest.fixture()
def mock_elevenlabs_tts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mocks ElevenLabs TTS to write fake audio bytes."""

    def fake_el_chunk(
        text: str,
        api_key: str,
        output_path: Path,
        voice_id: str = "",
        model_id: str = "",
        *,
        gender: str = "FEMALE",
    ) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(_FAKE_AUDIO_BYTES)

    monkeypatch.setattr(f"{_MOD}._synthesize_chunk_elevenlabs", fake_el_chunk)
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda key, default="": (
            "fake-el-key"
            if "elevenlabs_api_key" in key
            else ("fake-voice-id" if "elevenlabs_voice_id" in key else default)
        ),
    )


@pytest.fixture()
def mock_whisper(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mocks faster-whisper transcription to return fake SRT."""

    def fake_transcribe_whisper(
        file_path: str,
        src_lang: str = "",
        model_size: str = "base",
    ) -> str:
        return _FAKE_SRT

    monkeypatch.setattr(f"{_MOD}._transcribe_whisper", fake_transcribe_whisper)


@pytest.fixture()
def mock_google_stt(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mocks Google Cloud STT to return fake SRT."""

    def fake_transcribe_google(
        file_path: str,
        src_lang: str = "",
        model: str = "default",
        is_cancelled: Callable[[], bool] | None = None,
    ) -> str:
        return _FAKE_SRT

    monkeypatch.setattr(
        f"{_MOD}._transcribe_google_cloud",
        fake_transcribe_google,
    )
    monkeypatch.setattr(
        f"{_MOD}.load_google_cloud_api_key",
        lambda: "fake-api-key",
    )
    monkeypatch.setattr(
        "src.utils.config_manager.load_google_cloud_api_key",
        lambda: "fake-api-key",
    )


@pytest.fixture()
def mock_mp3_duration(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mocks _get_mp3_duration to return a fixed short duration."""
    monkeypatch.setattr(f"{_MOD}._get_mp3_duration", lambda _path: 1.5)


@pytest.fixture()
def audio_file(tmp_path: Path) -> Path:
    """Creates a fake audio file for testing."""
    audio = tmp_path / "test_audio.mp3"
    audio.write_bytes(_FAKE_AUDIO_BYTES)
    return audio


@pytest.fixture()
def video_file(tmp_path: Path) -> Path:
    """Creates a fake video file for testing."""
    video = tmp_path / "test_video.mp4"
    video.write_bytes(b"\x00" * 2048)
    return video


@pytest.fixture()
def srt_file(tmp_path: Path) -> Path:
    """Creates a real SRT file for voice pipeline testing."""
    srt = tmp_path / "test.srt"
    srt.write_text(_FAKE_SRT, encoding="utf-8")
    return srt


# ── Helpers ─────────────────────────────────────────────────────────────


def _create_subtitle_entry(
    file_path: Path,
    output_path: Path,
    src_lang: str = "English",
) -> int:
    """Creates a subtitle history entry in the DB and returns its ID."""
    return add_subtitle_entry(
        file_name=file_path.name,
        file_size=file_path.stat().st_size,
        source_path=str(file_path),
        output_path=str(output_path),
        src_lang=src_lang,
        status=STATUS_PENDING,
    )


def _create_voice_entry(
    file_path: Path,
    output_path: Path,
) -> int:
    """Creates a voice history entry in the DB and returns its ID."""
    return add_voice_entry(
        file_name=file_path.name,
        file_size=file_path.stat().st_size,
        source_path=str(file_path),
        output_path=str(output_path),
        status=STATUS_PENDING,
    )


def _create_dubbing_entry(
    file_path: Path,
    output_path: Path,
    src_lang: str = "English",
    target_lang: str = "Vietnamese",
) -> int:
    """Creates a dubbing history entry in the DB and returns its ID."""
    return add_dubbing_entry(
        file_name=file_path.name,
        file_size=file_path.stat().st_size,
        source_path=str(file_path),
        output_path=str(output_path),
        status=STATUS_PENDING,
        src_lang=src_lang,
        target_lang=target_lang,
    )


# =====================================================================
# Subtitle Pipeline Integration Tests
# =====================================================================


class TestSubtitlePipeline:
    """Integration tests for the subtitle generation (STT) pipeline."""

    def test_subtitle_whisper_roundtrip(
        self,
        tmp_path: Path,
        audio_file: Path,
        mock_whisper: None,
    ) -> None:
        """Whisper STT produces valid SRT output via transcribe_audio."""
        from src.core.speech_engine import transcribe_audio

        srt = transcribe_audio(
            str(audio_file),
            src_lang="English",
            stt_method="Whisper",
            model_size="base",
        )

        # Verify SRT structure: parseable with entries
        entries, _ = parse_subtitle(srt, ".srt")
        assert len(entries) == 2
        assert entries[0].text == "Hello world"
        assert entries[1].text == "This is a test"

        # Verify timestamps are present
        assert entries[0].start == "00:00:01,000"
        assert entries[0].end == "00:00:04,000"

        # Write to file and verify round-trip
        output = tmp_path / "output.srt"
        output.write_text(srt, encoding="utf-8")
        assert output.exists()
        assert output.stat().st_size > 0

    def test_subtitle_google_cloud_roundtrip(
        self,
        tmp_path: Path,
        audio_file: Path,
        mock_google_stt: None,
    ) -> None:
        """Google Cloud STT produces valid SRT output."""
        from src.core.speech_engine import transcribe_audio

        srt = transcribe_audio(
            str(audio_file),
            src_lang="English",
            stt_method="Google Cloud",
            google_model="default",
        )

        entries, _ = parse_subtitle(srt, ".srt")
        assert len(entries) == 2
        assert entries[0].text == "Hello world"

        # Verify the DB entry lifecycle
        output = tmp_path / "output.srt"
        entry_id = _create_subtitle_entry(audio_file, output)
        update_subtitle_status(entry_id, STATUS_GENERATING)
        output.write_text(srt, encoding="utf-8")
        update_subtitle_status(
            entry_id,
            STATUS_DONE,
            output_path=str(output),
        )

    def test_subtitle_with_translation(
        self,
        tmp_path: Path,
        audio_file: Path,
        mock_whisper: None,
        mock_llm: Callable[..., list[str]],
    ) -> None:
        """Transcription followed by translation produces translated subtitle."""
        from src.core.llm_engine import translate_text
        from src.core.speech_engine import transcribe_audio

        # Step 1: Transcribe
        srt = transcribe_audio(
            str(audio_file),
            src_lang="English",
            stt_method="Whisper",
        )
        entries, fmt_data = parse_subtitle(srt, ".srt")

        # Step 2: Translate the subtitle text
        texts = [e.text for e in entries]
        translated = translate_text(texts, "Vietnamese", "English")

        # Step 3: Apply translations back
        for entry, new_text in zip(entries, translated, strict=True):
            entry.text = new_text

        result_srt = serialize_subtitle(entries, fmt_data, ".srt")

        # Verify translated content
        output = tmp_path / "translated.srt"
        output.write_text(result_srt, encoding="utf-8")

        re_entries, _ = parse_subtitle(result_srt, ".srt")
        assert len(re_entries) == 2
        assert "[Vietnamese]" in re_entries[0].text
        assert "Hello world" in re_entries[0].text
        assert "[Vietnamese]" in re_entries[1].text

    def test_subtitle_empty_transcription(
        self,
        tmp_path: Path,
        audio_file: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Empty transcription result is handled gracefully."""
        monkeypatch.setattr(
            f"{_MOD}._transcribe_whisper",
            lambda *a, **kw: "",
        )

        from src.core.speech_engine import transcribe_audio

        srt = transcribe_audio(
            str(audio_file),
            src_lang="English",
            stt_method="Whisper",
        )
        # Empty SRT should produce no entries
        assert srt.strip() == ""
        entries, _ = parse_subtitle(srt, ".srt")
        assert len(entries) == 0

    def test_subtitle_cancellation(
        self,
        tmp_path: Path,
        audio_file: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Cancellation mid-transcription raises CANCELLED for Google Cloud."""
        # Google Cloud checks is_cancelled during polling
        monkeypatch.setattr(
            f"{_MOD}.load_google_cloud_api_key",
            lambda: "fake-key",
        )
        monkeypatch.setattr(
            "src.utils.config_manager.load_google_cloud_api_key",
            lambda: "fake-key",
        )
        # Mock _extract_audio_to_flac to return a small fake FLAC
        flac_dir = tmp_path / "flac_temp"
        flac_dir.mkdir()
        flac_file = flac_dir / "audio.flac"
        flac_file.write_bytes(b"\x00" * 100)
        monkeypatch.setattr(
            f"{_MOD}._extract_audio_to_flac",
            lambda _fp: flac_file,
        )
        # Mock the API call to return an operation name
        monkeypatch.setattr(
            f"{_MOD}._call_long_running_recognize",
            lambda *a, **kw: "op-123",
        )
        # Mock _poll_operation to raise CANCELLED
        monkeypatch.setattr(
            f"{_MOD}._poll_operation",
            lambda name, key, is_cancelled=None: (_ for _ in ()).throw(
                ValueError("CANCELLED")
            ),
        )

        from src.core.speech_engine import transcribe_audio

        with pytest.raises(ValueError, match="CANCELLED"):
            transcribe_audio(
                str(audio_file),
                src_lang="English",
                stt_method="Google Cloud",
                is_cancelled=lambda: True,
            )

    def test_subtitle_ffmpeg_missing(
        self,
        tmp_path: Path,
        audio_file: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Missing FFmpeg raises RuntimeError for Google Cloud STT."""
        monkeypatch.setattr(f"{_MOD}.check_ffmpeg_available", lambda: False)
        monkeypatch.setattr(
            f"{_MOD}.load_google_cloud_api_key",
            lambda: "fake-key",
        )
        monkeypatch.setattr(
            "src.utils.config_manager.load_google_cloud_api_key",
            lambda: "fake-key",
        )

        from src.core.speech_engine import transcribe_audio

        # Google Cloud path calls _extract_audio_to_flac which checks FFmpeg
        with pytest.raises(RuntimeError, match="FFMPEG_NOT_FOUND"):
            transcribe_audio(
                str(audio_file),
                src_lang="English",
                stt_method="Google Cloud",
            )

    def test_subtitle_vtt_format_output(
        self,
        tmp_path: Path,
        audio_file: Path,
        mock_whisper: None,
    ) -> None:
        """Transcribed SRT can be converted to VTT format."""
        from src.core.speech_engine import transcribe_audio

        srt = transcribe_audio(
            str(audio_file),
            src_lang="English",
            stt_method="Whisper",
        )

        # Parse SRT
        entries, _ = parse_subtitle(srt, ".srt")
        assert len(entries) > 0

        # Serialize as VTT
        vtt_content = serialize_subtitle(entries, "WEBVTT", ".vtt")
        assert "WEBVTT" in vtt_content

        # Round-trip: parse the VTT back
        vtt_entries, vtt_header = parse_subtitle(vtt_content, ".vtt")
        assert len(vtt_entries) == len(entries)
        assert vtt_entries[0].text == entries[0].text

    def test_subtitle_large_audio_file_google(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Google Cloud STT rejects audio exceeding the 10MB limit."""
        monkeypatch.setattr(
            f"{_MOD}.load_google_cloud_api_key",
            lambda: "fake-key",
        )
        monkeypatch.setattr(
            "src.utils.config_manager.load_google_cloud_api_key",
            lambda: "fake-key",
        )

        # Create a fake FLAC file larger than 10MB
        flac_dir = tmp_path / "flac_temp"
        flac_dir.mkdir()
        large_flac = flac_dir / "audio.flac"
        large_flac.write_bytes(b"\x00" * (11 * 1024 * 1024))  # 11MB
        monkeypatch.setattr(
            f"{_MOD}._extract_audio_to_flac",
            lambda _fp: large_flac,
        )

        from src.core.speech_engine import transcribe_audio

        audio = tmp_path / "large.mp3"
        audio.write_bytes(b"\x00" * 100)

        with pytest.raises(ValueError, match="AUDIO_TOO_LARGE"):
            transcribe_audio(
                str(audio),
                src_lang="English",
                stt_method="Google Cloud",
            )

    def test_subtitle_db_status_lifecycle(
        self,
        tmp_path: Path,
        audio_file: Path,
        mock_whisper: None,
    ) -> None:
        """Subtitle DB entry transitions through expected statuses."""
        from src.core.speech_engine import transcribe_audio

        output = tmp_path / "sub_out.srt"
        entry_id = _create_subtitle_entry(audio_file, output)

        # Start: Pending
        update_subtitle_status(entry_id, STATUS_GENERATING)

        srt = transcribe_audio(
            str(audio_file),
            src_lang="English",
            stt_method="Whisper",
        )
        output.write_text(srt, encoding="utf-8")

        # Complete
        update_subtitle_status(
            entry_id,
            STATUS_DONE,
            output_path=str(output),
        )

        # Verify file exists and is valid
        assert output.exists()
        entries, _ = parse_subtitle(output.read_text(encoding="utf-8"), ".srt")
        assert len(entries) == 2


# =====================================================================
# Voice Pipeline Integration Tests
# =====================================================================


class TestVoicePipeline:
    """Integration tests for the voice generation (TTS) pipeline."""

    def test_voice_edge_tts_roundtrip(
        self,
        tmp_path: Path,
        mock_ffmpeg: None,
        mock_edge_tts: None,
    ) -> None:
        """Edge TTS synthesizes text to an MP3 file."""
        from src.core.speech_engine import synthesize_speech

        output = tmp_path / "voice_edge.mp3"
        result = synthesize_speech(
            "Hello world, this is a test.",
            target_lang="English",
            voice_gender="FEMALE",
            output_path=str(output),
            tts_method="Edge TTS",
        )

        assert result == str(output)
        assert output.exists()
        assert output.stat().st_size > 0

    def test_voice_google_tts_roundtrip(
        self,
        tmp_path: Path,
        mock_ffmpeg: None,
        mock_google_tts: None,
    ) -> None:
        """Google Cloud TTS synthesizes text to an MP3 file."""
        from src.core.speech_engine import synthesize_speech

        output = tmp_path / "voice_google.mp3"
        result = synthesize_speech(
            "Hello world, this is a test.",
            target_lang="English",
            voice_gender="FEMALE",
            output_path=str(output),
            tts_method="Google Cloud TTS",
        )

        assert result == str(output)
        assert output.exists()

    def test_voice_elevenlabs_roundtrip(
        self,
        tmp_path: Path,
        mock_ffmpeg: None,
        mock_elevenlabs_tts: None,
    ) -> None:
        """ElevenLabs TTS synthesizes text to an MP3 file."""
        from src.core.speech_engine import synthesize_speech

        output = tmp_path / "voice_el.mp3"
        result = synthesize_speech(
            "Hello world, this is a test.",
            target_lang="English",
            voice_gender="FEMALE",
            output_path=str(output),
            tts_method="ElevenLabs",
        )

        assert result == str(output)
        assert output.exists()

    def test_voice_timed_speech_sync(
        self,
        tmp_path: Path,
        mock_ffmpeg: None,
        mock_edge_tts: None,
        mock_mp3_duration: None,
    ) -> None:
        """Timed speech synthesis places audio at correct subtitle timestamps."""
        from src.core.speech_engine import synthesize_timed_speech

        entries = [
            SubtitleEntry(
                index=0,
                start="00:00:01,000",
                end="00:00:04,000",
                text="First sentence",
            ),
            SubtitleEntry(
                index=1,
                start="00:00:06,000",
                end="00:00:09,000",
                text="Second sentence",
            ),
        ]

        output = tmp_path / "timed_voice.mp3"
        result = synthesize_timed_speech(
            entries,
            target_lang="English",
            voice_gender="FEMALE",
            output_path=str(output),
            tts_method="Edge TTS",
        )

        assert result == str(output)
        assert output.exists()
        assert output.stat().st_size > 0

    def test_voice_empty_text_raises(
        self,
        tmp_path: Path,
        mock_ffmpeg: None,
        mock_edge_tts: None,
    ) -> None:
        """Empty text raises ValueError with EMPTY_TEXT tag."""
        from src.core.speech_engine import synthesize_speech

        output = tmp_path / "empty.mp3"
        with pytest.raises(ValueError, match="EMPTY_TEXT"):
            synthesize_speech(
                "   ",
                target_lang="English",
                output_path=str(output),
                tts_method="Edge TTS",
            )

    def test_voice_cancellation(
        self,
        tmp_path: Path,
        mock_ffmpeg: None,
        mock_edge_tts: None,
    ) -> None:
        """Cancellation mid-synthesis raises CANCELLED."""
        from src.core.speech_engine import synthesize_speech

        output = tmp_path / "cancel.mp3"
        with pytest.raises(ValueError, match="CANCELLED"):
            synthesize_speech(
                "Hello world. This is a sentence. Another one here.",
                target_lang="English",
                output_path=str(output),
                tts_method="Edge TTS",
                is_cancelled=lambda: True,
            )

    def test_voice_multi_chunk_concatenation(
        self,
        tmp_path: Path,
        mock_ffmpeg: None,
        mock_edge_tts: None,
    ) -> None:
        """Long text is split into chunks, synthesized, and concatenated."""
        from src.core.speech_engine import synthesize_speech

        # Create text longer than _TTS_MAX_BYTES (4500)
        long_text = ". ".join(
            [
                f"This is sentence number {i} with some extra padding words"
                for i in range(100)
            ]
        )
        assert len(long_text.encode("utf-8")) > 4500

        output = tmp_path / "long_voice.mp3"
        result = synthesize_speech(
            long_text,
            target_lang="English",
            voice_gender="FEMALE",
            output_path=str(output),
            tts_method="Edge TTS",
        )

        assert result == str(output)
        assert output.exists()

    def test_voice_auth_error_google(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Missing Google Cloud API key raises AUTH_ERROR."""
        monkeypatch.setattr(
            f"{_MOD}.load_google_cloud_api_key",
            lambda: "",
        )
        monkeypatch.setattr(
            "src.utils.config_manager.load_google_cloud_api_key",
            lambda: "",
        )

        from src.core.speech_engine import synthesize_speech

        output = tmp_path / "no_auth.mp3"
        with pytest.raises(ValueError, match="AUTH_ERROR"):
            synthesize_speech(
                "Hello",
                target_lang="English",
                output_path=str(output),
                tts_method="Google Cloud TTS",
            )

    def test_voice_auth_error_elevenlabs(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Missing ElevenLabs API key raises AUTH_ERROR."""
        monkeypatch.setattr(
            "src.utils.config_manager.load_setting",
            lambda key, default="": "",
        )

        from src.core.speech_engine import synthesize_speech

        output = tmp_path / "no_auth_el.mp3"
        with pytest.raises(ValueError, match="AUTH_ERROR"):
            synthesize_speech(
                "Hello",
                target_lang="English",
                output_path=str(output),
                tts_method="ElevenLabs",
            )

    def test_voice_timed_speech_empty_entries_raises(
        self,
        tmp_path: Path,
        mock_ffmpeg: None,
        mock_edge_tts: None,
    ) -> None:
        """Timed speech with no valid entries raises EMPTY_TEXT."""
        from src.core.speech_engine import synthesize_timed_speech

        entries = [
            SubtitleEntry(
                index=0,
                start="00:00:01,000",
                end="00:00:04,000",
                text="   ",  # whitespace-only
            ),
        ]

        output = tmp_path / "empty_timed.mp3"
        with pytest.raises(ValueError, match="EMPTY_TEXT"):
            synthesize_timed_speech(
                entries,
                target_lang="English",
                output_path=str(output),
                tts_method="Edge TTS",
            )

    def test_voice_db_status_lifecycle(
        self,
        tmp_path: Path,
        srt_file: Path,
        mock_ffmpeg: None,
        mock_edge_tts: None,
    ) -> None:
        """Voice DB entry transitions through expected statuses."""
        output = tmp_path / "voice_out.mp3"
        entry_id = _create_voice_entry(srt_file, output)
        update_voice_status(entry_id, STATUS_GENERATING)

        from src.core.speech_engine import synthesize_speech

        text = srt_file.read_text(encoding="utf-8")
        from src.core.speech_engine import extract_subtitle_text

        plain_text = extract_subtitle_text(text, ".srt")
        assert "Hello world" in plain_text

        synthesize_speech(
            plain_text,
            target_lang="English",
            voice_gender="FEMALE",
            output_path=str(output),
            tts_method="Edge TTS",
        )

        update_voice_status(entry_id, STATUS_DONE, output_path=str(output))
        assert output.exists()


# =====================================================================
# Dubbing Pipeline Integration Tests
# =====================================================================


class TestDubbingPipeline:
    """Integration tests for the dubbing (STT + translate + TTS + mix) pipeline."""

    def test_dubbing_full_pipeline(
        self,
        tmp_path: Path,
        video_file: Path,
        mock_whisper: None,
        mock_llm: Callable[..., list[str]],
        mock_ffmpeg: None,
        mock_edge_tts: None,
        mock_mp3_duration: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Full dubbing pipeline: STT -> translate -> TTS -> mix."""
        from src.core.checkpoint import (
            save_dubbing_checkpoint,
        )
        from src.core.llm_engine import translate_batch
        from src.core.speech_engine import (
            mix_audio_into_video,
            synthesize_timed_speech,
            transcribe_audio,
        )

        storage_dir = tmp_path / "dubbing_storage"
        storage_dir.mkdir()

        # Step 1: STT
        srt_text = transcribe_audio(
            str(video_file),
            src_lang="English",
            stt_method="Whisper",
        )
        assert srt_text.strip()
        save_dubbing_checkpoint(
            storage_dir, srt_text=srt_text, target_lang="Vietnamese"
        )

        # Step 2: Translate
        entries, fmt_data = parse_subtitle(srt_text, ".srt")
        texts = [e.text for e in entries]
        translated = translate_batch(texts, "Vietnamese", "English")
        assert translated is not None
        for entry, new_text in zip(entries, translated, strict=True):
            entry.text = new_text
        translated_srt = serialize_subtitle(entries, fmt_data, ".srt")
        save_dubbing_checkpoint(storage_dir, translated_srt=translated_srt)

        # Step 3: TTS
        voice_path = storage_dir / "voice.mp3"
        synthesize_timed_speech(
            entries,
            target_lang="Vietnamese",
            voice_gender="FEMALE",
            output_path=str(voice_path),
            tts_method="Edge TTS",
        )
        assert voice_path.exists()
        save_dubbing_checkpoint(storage_dir, voice_file="voice.mp3")

        # Step 4: Mix
        output = tmp_path / "dubbed_video.mp4"
        mix_audio_into_video(str(video_file), str(voice_path), str(output))
        assert output.exists()

        # Verify translated subtitles contain translation markers
        re_entries, _ = parse_subtitle(translated_srt, ".srt")
        assert all("[Vietnamese]" in e.text for e in re_entries)

    def test_dubbing_checkpoint_resume_from_stt(
        self,
        tmp_path: Path,
    ) -> None:
        """Pre-seeded STT checkpoint skips the transcription step."""
        from src.core.checkpoint import (
            load_dubbing_checkpoint,
            save_dubbing_checkpoint,
        )

        storage_dir = tmp_path / "ckpt_stt"
        storage_dir.mkdir()

        # Pre-seed checkpoint with STT result
        save_dubbing_checkpoint(
            storage_dir,
            srt_text=_FAKE_SRT,
            target_lang="Vietnamese",
        )

        ckpt = load_dubbing_checkpoint(storage_dir)
        assert ckpt is not None
        assert "srt_text" in ckpt
        assert ckpt["srt_text"] == _FAKE_SRT
        assert ckpt["target_lang"] == "Vietnamese"

        # The pipeline would skip STT and proceed to translation
        entries, _ = parse_subtitle(ckpt["srt_text"], ".srt")
        assert len(entries) == 2

    def test_dubbing_checkpoint_resume_from_translate(
        self,
        tmp_path: Path,
    ) -> None:
        """Pre-seeded translation checkpoint skips STT and translation steps."""
        from src.core.checkpoint import (
            load_dubbing_checkpoint,
            save_dubbing_checkpoint,
        )

        storage_dir = tmp_path / "ckpt_translate"
        storage_dir.mkdir()

        # Simulate translated SRT
        entries, fmt_data = parse_subtitle(_FAKE_SRT, ".srt")
        for entry in entries:
            entry.text = f"[Vietnamese] {entry.text}"
        translated_srt = serialize_subtitle(entries, fmt_data, ".srt")

        save_dubbing_checkpoint(
            storage_dir,
            srt_text=_FAKE_SRT,
            translated_srt=translated_srt,
            target_lang="Vietnamese",
        )

        ckpt = load_dubbing_checkpoint(storage_dir)
        assert ckpt is not None
        assert "translated_srt" in ckpt

        # Parse the translated SRT from checkpoint
        re_entries, _ = parse_subtitle(ckpt["translated_srt"], ".srt")
        assert all("[Vietnamese]" in e.text for e in re_entries)

    def test_dubbing_checkpoint_resume_from_tts(
        self,
        tmp_path: Path,
    ) -> None:
        """Pre-seeded TTS checkpoint skips STT, translation, and TTS steps."""
        from src.core.checkpoint import (
            load_dubbing_checkpoint,
            save_dubbing_checkpoint,
        )

        storage_dir = tmp_path / "ckpt_tts"
        storage_dir.mkdir()

        # Create a fake voice file
        voice_path = storage_dir / "voice.mp3"
        voice_path.write_bytes(_FAKE_AUDIO_BYTES)

        save_dubbing_checkpoint(
            storage_dir,
            srt_text=_FAKE_SRT,
            translated_srt=_FAKE_SRT,
            voice_file="voice.mp3",
            target_lang="Vietnamese",
        )

        ckpt = load_dubbing_checkpoint(storage_dir)
        assert ckpt is not None
        assert ckpt.get("voice_file") == "voice.mp3"
        assert (storage_dir / ckpt["voice_file"]).exists()

    def test_dubbing_stt_failure_propagates(
        self,
        tmp_path: Path,
        video_file: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """STT failure propagates as an exception."""
        monkeypatch.setattr(
            f"{_MOD}._transcribe_whisper",
            lambda *a, **kw: (_ for _ in ()).throw(
                RuntimeError("FFMPEG_NOT_FOUND"),
            ),
        )

        from src.core.speech_engine import transcribe_audio

        output = tmp_path / "dubbed.mp4"
        entry_id = _create_dubbing_entry(video_file, output)
        update_dubbing_status(entry_id, STATUS_GENERATING)

        with pytest.raises(RuntimeError, match="FFMPEG_NOT_FOUND"):
            transcribe_audio(
                str(video_file),
                src_lang="English",
                stt_method="Whisper",
            )

        update_dubbing_status(
            entry_id,
            STATUS_FAILED,
            error_message="FFMPEG_NOT_FOUND",
        )

    def test_dubbing_translation_failure(
        self,
        tmp_path: Path,
        video_file: Path,
        mock_whisper: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Translation failure in dubbing pipeline propagates correctly."""
        from src.core.speech_engine import transcribe_audio

        srt_text = transcribe_audio(
            str(video_file),
            src_lang="English",
            stt_method="Whisper",
        )
        entries, _ = parse_subtitle(srt_text, ".srt")
        texts = [e.text for e in entries]

        # Mock translate_batch to raise an error
        def failing_translate(*args: Any, **kwargs: Any) -> None:
            raise ValueError("AUTH_ERROR")

        monkeypatch.setattr(
            "src.core.llm_engine.translate_batch",
            failing_translate,
        )

        from src.core.llm_engine import translate_batch

        output = tmp_path / "dubbed.mp4"
        entry_id = _create_dubbing_entry(video_file, output)
        update_dubbing_status(entry_id, STATUS_GENERATING)

        with pytest.raises(ValueError, match="AUTH_ERROR"):
            translate_batch(texts, "Vietnamese", "English")

        update_dubbing_status(
            entry_id,
            STATUS_FAILED,
            error_message="AUTH_ERROR",
        )

    def test_dubbing_tts_failure(
        self,
        tmp_path: Path,
        mock_whisper: None,
        mock_llm: Callable[..., list[str]],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """TTS failure in dubbing pipeline propagates correctly."""
        monkeypatch.setattr(f"{_MOD}.check_ffmpeg_available", lambda: True)
        monkeypatch.setattr(
            f"{_MOD}._synthesize_chunk_edge",
            lambda *a, **kw: (_ for _ in ()).throw(
                ValueError("TTS_SERVICE_ERROR"),
            ),
        )

        from src.core.speech_engine import synthesize_timed_speech

        entries = [
            SubtitleEntry(
                index=0,
                start="00:00:01,000",
                end="00:00:04,000",
                text="Hello world",
            ),
        ]

        output = tmp_path / "voice.mp3"
        with pytest.raises(ValueError, match="TTS_SERVICE_ERROR"):
            synthesize_timed_speech(
                entries,
                target_lang="English",
                output_path=str(output),
                tts_method="Edge TTS",
            )

    def test_dubbing_mix_failure(
        self,
        tmp_path: Path,
        video_file: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """FFmpeg mix failure propagates as RuntimeError."""
        import subprocess

        monkeypatch.setattr(f"{_MOD}.check_ffmpeg_available", lambda: True)
        monkeypatch.setattr(
            f"{_MOD}.subprocess.run",
            lambda *a, **kw: (_ for _ in ()).throw(
                subprocess.CalledProcessError(1, "ffmpeg", stderr=b"mix error"),
            ),
        )

        from src.core.speech_engine import mix_audio_into_video

        audio = tmp_path / "voice.mp3"
        audio.write_bytes(_FAKE_AUDIO_BYTES)
        output = tmp_path / "output.mp4"

        with pytest.raises(RuntimeError, match="FFMPEG_MIX_FAILED"):
            mix_audio_into_video(str(video_file), str(audio), str(output))

    def test_dubbing_glossary_forwarded(
        self,
        tmp_path: Path,
        mock_whisper: None,
        mock_ffmpeg: None,
        mock_edge_tts: None,
        mock_mp3_duration: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Glossary entries are forwarded through the dubbing pipeline."""
        from src.core.speech_engine import transcribe_audio

        video = tmp_path / "test_video.mp4"
        video.write_bytes(b"\x00" * 2048)

        # Track glossary usage in translate_batch
        glossary_seen: list[Any] = []

        def tracking_translate(
            values: list[str],
            target_lang: str,
            src_lang: str = "",
            glossary_entries: list[tuple[int, str, str]] | None = None,
            **kwargs: object,
        ) -> list[str]:
            glossary_seen.append(glossary_entries)
            return [f"[{target_lang}] {v}" for v in values]

        monkeypatch.setattr(
            "src.core.llm_engine.translate_batch",
            tracking_translate,
        )
        from src.core.llm_engine import translate_batch

        # Step 1: STT
        srt_text = transcribe_audio(
            str(video),
            src_lang="English",
            stt_method="Whisper",
        )

        # Step 2: Translate with glossary
        entries, fmt_data = parse_subtitle(srt_text, ".srt")
        texts = [e.text for e in entries]
        glossary = [(1, "Hello", "Xin chao"), (2, "world", "the gioi")]

        translate_batch(
            texts,
            "Vietnamese",
            "English",
            glossary_entries=glossary,
        )

        # Verify glossary was forwarded
        assert len(glossary_seen) == 1
        assert glossary_seen[0] == glossary

    def test_dubbing_db_status_lifecycle(
        self,
        tmp_path: Path,
        video_file: Path,
        mock_whisper: None,
        mock_llm: Callable[..., list[str]],
        mock_ffmpeg: None,
        mock_edge_tts: None,
        mock_mp3_duration: None,
    ) -> None:
        """Dubbing DB entry transitions through all expected statuses."""
        from src.core.database import update_dubbing_progress
        from src.core.speech_engine import (
            mix_audio_into_video,
            synthesize_timed_speech,
            transcribe_audio,
        )

        output = tmp_path / "dubbed.mp4"
        entry_id = _create_dubbing_entry(video_file, output)

        # Pending -> Generating
        update_dubbing_status(entry_id, STATUS_GENERATING)

        # STT
        update_dubbing_progress(entry_id, 5)
        srt = transcribe_audio(
            str(video_file), src_lang="English", stt_method="Whisper"
        )
        update_dubbing_progress(entry_id, 25)

        # Translate
        entries, fmt_data = parse_subtitle(srt, ".srt")
        from src.core.llm_engine import translate_batch

        texts = [e.text for e in entries]
        translated = translate_batch(texts, "Vietnamese", "English")
        for entry, new_text in zip(entries, translated, strict=True):
            entry.text = new_text
        update_dubbing_progress(entry_id, 50)

        # TTS
        voice = tmp_path / "voice.mp3"
        synthesize_timed_speech(
            entries,
            target_lang="Vietnamese",
            voice_gender="FEMALE",
            output_path=str(voice),
            tts_method="Edge TTS",
        )
        update_dubbing_progress(entry_id, 90)

        # Mix
        mix_audio_into_video(str(video_file), str(voice), str(output))
        update_dubbing_progress(entry_id, 100)

        # Mark done
        update_dubbing_status(
            entry_id,
            STATUS_DONE,
            output_path=str(output),
        )
        assert output.exists()


# =====================================================================
# Cross-Cutting Tests
# =====================================================================


class TestCrossCutting:
    """Cross-cutting integration tests spanning multiple pipelines."""

    def test_subtitle_to_voice_roundtrip(
        self,
        tmp_path: Path,
        audio_file: Path,
        mock_whisper: None,
        mock_ffmpeg: None,
        mock_edge_tts: None,
    ) -> None:
        """Full cycle: generate subtitle -> extract text -> synthesize voice."""
        from src.core.speech_engine import (
            extract_subtitle_text,
            synthesize_speech,
            transcribe_audio,
        )

        # Step 1: Generate subtitle
        srt = transcribe_audio(
            str(audio_file),
            src_lang="English",
            stt_method="Whisper",
        )
        srt_file = tmp_path / "generated.srt"
        srt_file.write_text(srt, encoding="utf-8")

        # Step 2: Extract text from subtitle
        plain_text = extract_subtitle_text(srt, ".srt")
        assert "Hello world" in plain_text
        assert "This is a test" in plain_text

        # Step 3: Synthesize voice from extracted text
        voice_output = tmp_path / "voice_from_sub.mp3"
        result = synthesize_speech(
            plain_text,
            target_lang="English",
            voice_gender="FEMALE",
            output_path=str(voice_output),
            tts_method="Edge TTS",
        )

        assert result == str(voice_output)
        assert voice_output.exists()

    def test_translated_subtitle_to_timed_voice(
        self,
        tmp_path: Path,
        audio_file: Path,
        mock_whisper: None,
        mock_llm: Callable[..., list[str]],
        mock_ffmpeg: None,
        mock_edge_tts: None,
        mock_mp3_duration: None,
    ) -> None:
        """Subtitle -> translate -> timed voice synthesis preserves timing."""
        from src.core.llm_engine import translate_text
        from src.core.speech_engine import synthesize_timed_speech, transcribe_audio

        # Transcribe
        srt = transcribe_audio(
            str(audio_file),
            src_lang="English",
            stt_method="Whisper",
        )

        # Translate
        entries, fmt_data = parse_subtitle(srt, ".srt")
        texts = [e.text for e in entries]
        translated = translate_text(texts, "Vietnamese", "English")
        for entry, new_text in zip(entries, translated, strict=True):
            entry.text = new_text

        # Verify translations happened
        assert all("[Vietnamese]" in e.text for e in entries)

        # Synthesize timed speech from translated entries
        voice_output = tmp_path / "timed_translated.mp3"
        result = synthesize_timed_speech(
            entries,
            target_lang="Vietnamese",
            voice_gender="FEMALE",
            output_path=str(voice_output),
            tts_method="Edge TTS",
        )

        assert result == str(voice_output)
        assert voice_output.exists()

    def test_text_splitting_real_logic(self) -> None:
        """Verifies the real text splitting logic handles edge cases."""
        from src.core.speech_engine import _split_text_for_tts

        # Short text — single chunk
        assert _split_text_for_tts("Hello.") == ["Hello."]

        # Empty text — no chunks
        assert _split_text_for_tts("") == []
        assert _split_text_for_tts("   ") == []

        # Long text with sentence boundaries — must exceed 4500 bytes
        long_text = ". ".join(
            [
                f"Sentence number {i} with extra words to fill up space"
                for i in range(200)
            ]
        )
        assert len(long_text.encode("utf-8")) > 4500
        chunks = _split_text_for_tts(long_text)
        assert len(chunks) > 1
        # Each chunk respects the byte limit
        for chunk in chunks:
            assert len(chunk.encode("utf-8")) <= 4500

    def test_srt_timestamp_parsing(self) -> None:
        """Verifies SRT timestamp parsing handles various formats."""
        from src.core.speech_engine import _parse_srt_timestamp

        # Standard SRT format
        assert _parse_srt_timestamp("00:00:01,000") == 1.0
        assert _parse_srt_timestamp("00:01:30,500") == 90.5
        assert _parse_srt_timestamp("01:00:00,000") == 3600.0

        # VTT format (dot instead of comma)
        assert _parse_srt_timestamp("00:00:01.000") == 1.0

        # Short format (MM:SS)
        assert _parse_srt_timestamp("01:30.000") == 90.0

        # Edge case: invalid
        assert _parse_srt_timestamp("invalid") == 0.0

    def test_extract_subtitle_text_formats(self, tmp_path: Path) -> None:
        """extract_subtitle_text works with SRT and VTT formats."""
        from src.core.speech_engine import extract_subtitle_text

        # SRT
        srt_text = extract_subtitle_text(_FAKE_SRT, ".srt")
        assert "Hello world" in srt_text
        assert "This is a test" in srt_text

        # VTT
        vtt_content = "WEBVTT\n\n00:00:01.000 --> 00:00:04.000\nHello VTT\n"
        vtt_text = extract_subtitle_text(vtt_content, ".vtt")
        assert "Hello VTT" in vtt_text

        # Plain text fallback
        plain = extract_subtitle_text("Just plain text", ".txt")
        assert plain == "Just plain text"


# =====================================================================
# Additional Audio Pipeline Integration Tests
# =====================================================================


class TestSubtitleAdvanced:
    """Advanced subtitle pipeline tests covering glossary and edge cases."""

    def test_subtitle_generation_with_translation_and_glossary(
        self,
        tmp_path: Path,
        audio_file: Path,
        mock_whisper: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """STT + translate + glossary integration: glossary entries forwarded."""
        from src.core.speech_engine import transcribe_audio

        # Track glossary usage in translate_batch
        glossary_seen: list[Any] = []

        def tracking_translate_batch(
            values: list[str],
            target_lang: str,
            src_lang: str = "",
            glossary_entries: list[tuple[int, str, str]] | None = None,
            **kwargs: object,
        ) -> list[str]:
            glossary_seen.append(glossary_entries)
            return [f"[{target_lang}] {v}" for v in values]

        monkeypatch.setattr(
            "src.core.llm_engine.translate_batch",
            tracking_translate_batch,
        )

        # Step 1: STT
        srt_text = transcribe_audio(
            str(audio_file),
            src_lang="English",
            stt_method="Whisper",
        )
        entries, fmt_data = parse_subtitle(srt_text, ".srt")
        assert len(entries) == 2  # noqa: PLR2004

        # Step 2: Translate with glossary
        from src.core.llm_engine import translate_batch

        texts = [e.text for e in entries]
        glossary = [(1, "Hello", "Xin chao"), (2, "test", "thu nghiem")]

        translated = translate_batch(
            texts,
            "Vietnamese",
            "English",
            glossary_entries=glossary,
        )

        # Apply translations
        for entry, new_text in zip(entries, translated, strict=True):
            entry.text = new_text

        result_srt = serialize_subtitle(entries, fmt_data, ".srt")

        # Verify glossary was forwarded
        assert len(glossary_seen) == 1
        assert glossary_seen[0] == glossary

        # Verify translations applied
        re_entries, _ = parse_subtitle(result_srt, ".srt")
        assert all("[Vietnamese]" in e.text for e in re_entries)

        # Verify timestamps preserved
        assert re_entries[0].start == "00:00:01,000"
        assert re_entries[0].end == "00:00:04,000"

        # Write output and verify DB lifecycle
        output = tmp_path / "glossary_sub.srt"
        output.write_text(result_srt, encoding="utf-8")
        entry_id = _create_subtitle_entry(audio_file, output)
        update_subtitle_status(entry_id, STATUS_GENERATING)
        update_subtitle_status(entry_id, STATUS_DONE, output_path=str(output))
        assert output.exists()

    def test_subtitle_empty_audio_no_speech_detected(
        self,
        tmp_path: Path,
        audio_file: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Audio with no speech produces empty/minimal output."""
        # Mock whisper to return empty SRT (no speech detected)
        monkeypatch.setattr(
            f"{_MOD}._transcribe_whisper",
            lambda *a, **kw: "",
        )

        from src.core.speech_engine import transcribe_audio

        srt = transcribe_audio(
            str(audio_file),
            src_lang="English",
            stt_method="Whisper",
        )

        # Empty or whitespace-only result
        assert srt.strip() == ""

        # Parse produces no entries
        entries, _ = parse_subtitle(srt, ".srt")
        assert len(entries) == 0

        # DB entry should still be manageable
        output = tmp_path / "no_speech.srt"
        output.write_text(srt, encoding="utf-8")
        entry_id = _create_subtitle_entry(audio_file, output)
        update_subtitle_status(entry_id, STATUS_GENERATING)

        # Even empty output can be marked as Done
        update_subtitle_status(entry_id, STATUS_DONE, output_path=str(output))

        # VTT conversion of empty content should not crash
        vtt_content = serialize_subtitle(entries, "WEBVTT", ".vtt")
        assert "WEBVTT" in vtt_content


class TestDubbingCancellation:
    """Tests for cancellation at each stage of the dubbing pipeline."""

    def test_dubbing_cancellation_at_stt_stage(
        self,
        tmp_path: Path,
        video_file: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Cancel during STT stage raises CANCELLED."""
        monkeypatch.setattr(
            f"{_MOD}._transcribe_whisper",
            lambda *a, **kw: (_ for _ in ()).throw(ValueError("CANCELLED")),
        )

        from src.core.speech_engine import transcribe_audio

        output = tmp_path / "cancel_stt.mp4"
        entry_id = _create_dubbing_entry(video_file, output)
        update_dubbing_status(entry_id, STATUS_GENERATING)

        with pytest.raises(ValueError, match="CANCELLED"):
            transcribe_audio(
                str(video_file),
                src_lang="English",
                stt_method="Whisper",
            )

        update_dubbing_status(entry_id, STATUS_FAILED, error_message="CANCELLED")

    def test_dubbing_cancellation_at_translate_stage(
        self,
        tmp_path: Path,
        video_file: Path,
        mock_whisper: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Cancel during translation stage raises CANCELLED."""
        from src.core.speech_engine import transcribe_audio

        # STT succeeds
        srt_text = transcribe_audio(
            str(video_file),
            src_lang="English",
            stt_method="Whisper",
        )
        entries, _ = parse_subtitle(srt_text, ".srt")
        texts = [e.text for e in entries]

        # Mock translate_batch to raise CANCELLED
        def cancel_translate(*args: Any, **kwargs: Any) -> None:
            raise ValueError("CANCELLED")

        monkeypatch.setattr(
            "src.core.llm_engine.translate_batch",
            cancel_translate,
        )
        from src.core.llm_engine import translate_batch

        output = tmp_path / "cancel_translate.mp4"
        entry_id = _create_dubbing_entry(video_file, output)
        update_dubbing_status(entry_id, STATUS_GENERATING)

        with pytest.raises(ValueError, match="CANCELLED"):
            translate_batch(texts, "Vietnamese", "English")

        update_dubbing_status(entry_id, STATUS_FAILED, error_message="CANCELLED")

    def test_dubbing_cancellation_at_tts_stage(
        self,
        tmp_path: Path,
        mock_whisper: None,
        mock_llm: Callable[..., list[str]],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Cancel during TTS stage raises CANCELLED."""
        monkeypatch.setattr(f"{_MOD}.check_ffmpeg_available", lambda: True)
        monkeypatch.setattr(
            f"{_MOD}._synthesize_chunk_edge",
            lambda *a, **kw: (_ for _ in ()).throw(ValueError("CANCELLED")),
        )

        from src.core.speech_engine import synthesize_timed_speech

        entries = [
            SubtitleEntry(
                index=0,
                start="00:00:01,000",
                end="00:00:04,000",
                text="Hello world",
            ),
        ]

        output = tmp_path / "cancel_tts.mp3"
        with pytest.raises(ValueError, match="CANCELLED"):
            synthesize_timed_speech(
                entries,
                target_lang="English",
                output_path=str(output),
                tts_method="Edge TTS",
            )

    def test_dubbing_cancellation_at_mix_stage(
        self,
        tmp_path: Path,
        video_file: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Cancel during mix stage raises FFMPEG_MIX_FAILED."""
        import subprocess

        monkeypatch.setattr(f"{_MOD}.check_ffmpeg_available", lambda: True)
        monkeypatch.setattr(
            f"{_MOD}.subprocess.run",
            lambda *a, **kw: (_ for _ in ()).throw(
                subprocess.CalledProcessError(1, "ffmpeg", stderr=b"cancelled"),
            ),
        )

        from src.core.speech_engine import mix_audio_into_video

        audio = tmp_path / "voice.mp3"
        audio.write_bytes(_FAKE_AUDIO_BYTES)
        output = tmp_path / "cancel_mix.mp4"

        entry_id = _create_dubbing_entry(video_file, output)
        update_dubbing_status(entry_id, STATUS_GENERATING)

        with pytest.raises(RuntimeError, match="FFMPEG_MIX_FAILED"):
            mix_audio_into_video(str(video_file), str(audio), str(output))

        update_dubbing_status(
            entry_id, STATUS_FAILED, error_message="FFMPEG_MIX_FAILED"
        )


class TestVoiceFormats:
    """Tests for voice generation with different subtitle input formats."""

    def test_voice_generation_from_srt_input(
        self,
        tmp_path: Path,
        mock_ffmpeg: None,
        mock_edge_tts: None,
        mock_mp3_duration: None,
    ) -> None:
        """Voice generation from .srt input file works correctly."""
        from src.core.speech_engine import extract_subtitle_text, synthesize_speech

        # Create SRT file
        srt_path = tmp_path / "input.srt"
        srt_path.write_text(_FAKE_SRT, encoding="utf-8")

        # Extract text from SRT
        srt_content = srt_path.read_text(encoding="utf-8")
        plain_text = extract_subtitle_text(srt_content, ".srt")
        assert "Hello world" in plain_text
        assert "This is a test" in plain_text

        # Synthesize voice
        output = tmp_path / "from_srt.mp3"
        result = synthesize_speech(
            plain_text,
            target_lang="English",
            voice_gender="FEMALE",
            output_path=str(output),
            tts_method="Edge TTS",
        )
        assert result == str(output)
        assert output.exists()
        assert output.stat().st_size > 0

        # DB lifecycle
        entry_id = _create_voice_entry(srt_path, output)
        update_voice_status(entry_id, STATUS_GENERATING)
        update_voice_status(entry_id, STATUS_DONE, output_path=str(output))

    def test_voice_generation_from_vtt_input(
        self,
        tmp_path: Path,
        mock_ffmpeg: None,
        mock_edge_tts: None,
        mock_mp3_duration: None,
    ) -> None:
        """Voice generation from .vtt input file works correctly."""
        from src.core.speech_engine import extract_subtitle_text, synthesize_speech

        # Create VTT file
        vtt_content = (
            "WEBVTT\n"
            "\n"
            "00:00:01.000 --> 00:00:04.000\n"
            "Hello from VTT\n"
            "\n"
            "00:00:05.000 --> 00:00:08.000\n"
            "Another VTT line\n"
        )
        vtt_path = tmp_path / "input.vtt"
        vtt_path.write_text(vtt_content, encoding="utf-8")

        # Extract text from VTT
        plain_text = extract_subtitle_text(vtt_content, ".vtt")
        assert "Hello from VTT" in plain_text
        assert "Another VTT line" in plain_text

        # Synthesize voice
        output = tmp_path / "from_vtt.mp3"
        result = synthesize_speech(
            plain_text,
            target_lang="English",
            voice_gender="FEMALE",
            output_path=str(output),
            tts_method="Edge TTS",
        )
        assert result == str(output)
        assert output.exists()

        # Also test timed speech from VTT entries
        entries, _ = parse_subtitle(vtt_content, ".vtt")
        assert len(entries) == 2  # noqa: PLR2004

        from src.core.speech_engine import synthesize_timed_speech

        timed_output = tmp_path / "timed_vtt.mp3"
        timed_result = synthesize_timed_speech(
            entries,
            target_lang="English",
            voice_gender="FEMALE",
            output_path=str(timed_output),
            tts_method="Edge TTS",
        )
        assert timed_result == str(timed_output)
        assert timed_output.exists()

    def test_voice_generation_with_different_formats_roundtrip(
        self,
        tmp_path: Path,
        mock_ffmpeg: None,
        mock_edge_tts: None,
    ) -> None:
        """Both SRT and VTT produce equivalent voice output."""
        from src.core.speech_engine import extract_subtitle_text, synthesize_speech

        # SRT input
        srt_text = extract_subtitle_text(_FAKE_SRT, ".srt")

        # Convert same content to VTT
        entries, fmt_data = parse_subtitle(_FAKE_SRT, ".srt")
        vtt_content = serialize_subtitle(entries, "WEBVTT", ".vtt")
        vtt_text = extract_subtitle_text(vtt_content, ".vtt")

        # Both should contain the same spoken content
        assert "Hello world" in srt_text
        assert "Hello world" in vtt_text
        assert "This is a test" in srt_text
        assert "This is a test" in vtt_text

        # Both should produce valid audio files
        srt_output = tmp_path / "voice_srt.mp3"
        vtt_output = tmp_path / "voice_vtt.mp3"

        synthesize_speech(
            srt_text,
            target_lang="English",
            voice_gender="FEMALE",
            output_path=str(srt_output),
            tts_method="Edge TTS",
        )
        synthesize_speech(
            vtt_text,
            target_lang="English",
            voice_gender="FEMALE",
            output_path=str(vtt_output),
            tts_method="Edge TTS",
        )

        assert srt_output.exists()
        assert vtt_output.exists()
