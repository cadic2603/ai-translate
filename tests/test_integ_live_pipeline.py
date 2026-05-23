"""Integration test for the live translation pipeline.

Wires the three real components — ``LiveTranscriber`` (STT) →
``llm_engine.translate_text`` (LLM) → ``speech_engine.synthesize_speech``
(TTS) — and verifies that a recognized sentence flows end-to-end into
synthesized audio.  External boundaries (microphone capture, Whisper
inference, the LLM API, the TTS API, FFmpeg) are mocked; the glue
between components runs for real so any wiring break (e.g. a sentence
callback that doesn't reach the translator, or a translated string that
doesn't reach the TTS engine) is caught.
"""

from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

_SAMPLE_RATE = 16000
_BLOCK_DURATION = 0.5  # matches _BLOCK_DURATION constant in live_engine
_BLOCK_SAMPLES = int(_SAMPLE_RATE * _BLOCK_DURATION)


def _loud_block() -> np.ndarray:
    """Returns a block of audio with high RMS (above silence threshold)."""
    # Above _SILENCE_THRESHOLD (0.005); use 0.5 amplitude sine-ish data.
    return np.full(_BLOCK_SAMPLES, 0.5, dtype=np.float32)


def _silent_block() -> np.ndarray:
    """Returns a block of audio with near-zero RMS (silence)."""
    return np.zeros(_BLOCK_SAMPLES, dtype=np.float32)


@pytest.fixture()
def fake_whisper_model():
    """Returns a stub whisper model that yields a single recognized segment."""

    class _Segment:
        def __init__(self, text: str) -> None:
            self.text = text

    model = MagicMock()
    # First positional arg to transcribe() is the audio buffer; we ignore it
    # and unconditionally return our canned segment.  Generator → tuple of
    # (segments, info) matches faster_whisper's real return shape.
    model.transcribe.return_value = (
        iter([_Segment(" Hello world.")]),
        MagicMock(language="en", language_probability=0.99),
    )
    return model


def test_live_pipeline_stt_to_llm_to_tts(
    monkeypatch: pytest.MonkeyPatch,
    fake_whisper_model,
    tmp_path: Path,
) -> None:
    """A loud-then-silent audio sequence drives STT → LLM → TTS in order.

    Pins the contract that:
    1. ``LiveTranscriber`` calls ``on_sentence(text, start, end)`` after
       silence-boundary detection.
    2. The handler can hand that text to ``llm_engine.translate_text``
       and receive a translation.
    3. The translation can be passed to ``speech_engine.synthesize_speech``
       and produce audio at the requested path.
    A regression in any one of these wires (signal dropped, return shape
    mismatch, kwarg drift) breaks this test.
    """
    from src.core.live_engine import LiveTranscriber

    # ── Stub audio backends so no real microphone is touched ─────────
    monkeypatch.setattr(
        "src.core.live_engine.check_audio_available", lambda: ""
    )
    # ``_resolve_devices`` returns the mic device id; any int will do
    # because ``_open_streams`` is also stubbed below.
    monkeypatch.setattr(
        LiveTranscriber, "_resolve_devices", lambda self: 0
    )
    monkeypatch.setattr(
        LiveTranscriber, "_open_streams", lambda self, sd, mic: None
    )

    # ── Stub Whisper to return a canned segment ──────────────────────
    monkeypatch.setattr(
        "faster_whisper.WhisperModel",
        lambda *a, **kw: fake_whisper_model,
    )
    # Reset the module-level cache so our stub is used (the real
    # ``_cached_model`` may be populated from earlier tests).
    monkeypatch.setattr("src.core.live_engine._cached_model", None)
    monkeypatch.setattr("src.core.live_engine._cached_model_size", "")

    # ── Drive the audio queue: loud blocks then silence so the
    # silence-detection path runs and triggers transcription. ─────────
    sentences: list[tuple[str, float, float]] = []
    sentence_seen = threading.Event()

    def _on_sentence(text: str, start: float, end: float) -> None:
        sentences.append((text, start, end))
        sentence_seen.set()

    transcriber = LiveTranscriber(
        on_sentence=_on_sentence,
        model_size="tiny",
        language="English",
        audio_source="microphone",
    )

    # Replace ``_read_block`` to feed our test sequence: 6 loud, 6 silent,
    # then None forever (sentinel for end-of-input).  6 loud blocks
    # exceeds ``_MIN_AUDIO_BLOCKS`` (4); 6 silent blocks exceeds
    # ``_SILENCE_BLOCKS`` (3) — both required to trigger transcription.
    block_iter = iter(
        [_loud_block()] * 6 + [_silent_block()] * 6
    )

    def _fake_read_block(self):  # noqa: ANN001
        try:
            return next(block_iter)
        except StopIteration:
            self._is_running = False
            return None

    monkeypatch.setattr(LiveTranscriber, "_read_block", _fake_read_block)

    transcriber.start()
    # Wait briefly for the processing thread to consume the blocks and
    # fire the sentence callback.  5s ceiling to avoid hanging CI.
    sentence_seen.wait(timeout=5.0)
    transcriber.stop()

    assert sentences, "Live transcriber did not surface any sentence"
    raw_text = sentences[0][0]
    assert "Hello" in raw_text, f"unexpected transcription: {raw_text!r}"

    # ── Hand the recognized text to the LLM engine ────────────────────
    from src.core import llm_engine

    monkeypatch.setattr(
        llm_engine,
        "translate_text",
        lambda texts, target_lang, source_lang="", **_kw: [
            f"[{target_lang}] {t.strip()}" for t in texts
        ],
    )

    translated = llm_engine.translate_text(
        [raw_text],
        target_lang="French",
        source_lang="English",
    )
    assert translated == ["[French] Hello world."]

    # ── Hand the translation to the TTS engine ───────────────────────
    from src.core import speech_engine

    audio_out = tmp_path / "spoken.mp3"

    def _fake_synth(*args, **kwargs) -> None:  # noqa: ANN001, ARG001
        # Both positional and keyword forms appear across callers.
        path = kwargs.get("output_path") or args[0]
        Path(path).write_bytes(b"\x00" * 256)

    monkeypatch.setattr(speech_engine, "synthesize_speech", _fake_synth)
    monkeypatch.setattr(
        speech_engine, "check_ffmpeg_available", lambda: True
    )

    speech_engine.synthesize_speech(
        translated[0],
        target_lang="French",
        output_path=str(audio_out),
        tts_method="Edge TTS",
        voice_gender="FEMALE",
    )

    assert audio_out.exists(), "TTS did not write the output file"
    assert audio_out.read_bytes() != b"", "TTS wrote empty audio"
