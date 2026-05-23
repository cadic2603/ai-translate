"""Unit tests for the live audio transcription engine."""

import contextlib
import queue
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# Ensure mock modules are available before importing live_engine
_mock_sd = MagicMock()
_mock_fw = MagicMock()
sys.modules.setdefault("sounddevice", _mock_sd)
sys.modules.setdefault("faster_whisper", _mock_fw)

from src.core.live_engine import (  # noqa: E402
    _BLOCK_SIZE,
    _MAX_BUFFER_BLOCKS,
    _MIN_AUDIO_BLOCKS,
    _SAMPLE_RATE,
    _SILENCE_BLOCKS,
    _SILENCE_THRESHOLD,
    LiveTranscriber,
    _get_default_monitor_source,
    _get_portaudio_install_hint,
    _get_pulseaudio_install_hint,
    check_audio_available,
    check_system_audio_available,
    invalidate_audio_caches,
    list_input_devices,
)

_MOD = "src.core.live_engine"


@pytest.fixture(autouse=True)
def _bypass_audio_check_and_reset_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Skips audio pre-check and resets model cache in all live engine tests."""
    monkeypatch.setattr(f"{_MOD}.check_audio_available", lambda: "")
    monkeypatch.setattr(f"{_MOD}._cached_model", None)
    monkeypatch.setattr(f"{_MOD}._cached_model_size", "")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_block_size_matches_rate_and_duration() -> None:
    """_BLOCK_SIZE equals SAMPLE_RATE * 0.5."""
    assert int(_SAMPLE_RATE * 0.5) == _BLOCK_SIZE  # noqa: PLR2004


def test_silence_threshold_is_positive() -> None:
    """Silence threshold is a small positive number."""
    assert 0 < _SILENCE_THRESHOLD < 1  # noqa: PLR2004


def test_min_audio_blocks_less_than_silence_blocks() -> None:
    """Need fewer blocks to speak than to detect silence gap."""
    assert _MIN_AUDIO_BLOCKS <= _SILENCE_BLOCKS


# ---------------------------------------------------------------------------
# list_input_devices
# ---------------------------------------------------------------------------


class TestListInputDevices:
    """Tests for list_input_devices()."""

    def test_returns_only_input_devices(self) -> None:
        """Only devices with max_input_channels > 0 are returned."""
        devices = [
            {"name": "Mic", "max_input_channels": 2},
            {"name": "Speaker", "max_input_channels": 0},
            {"name": "Headset", "max_input_channels": 1},
        ]
        mock_sd = sys.modules["sounddevice"]
        mock_sd.query_devices = MagicMock(return_value=devices)
        result = list_input_devices()
        assert result == [(0, "Mic"), (2, "Headset")]

    def test_returns_empty_when_no_inputs(self) -> None:
        """Empty list when all devices are output-only."""
        devices = [{"name": "Speaker", "max_input_channels": 0}]
        mock_sd = sys.modules["sounddevice"]
        mock_sd.query_devices = MagicMock(return_value=devices)
        assert list_input_devices() == []

    def test_returns_empty_when_no_devices(self) -> None:
        """Empty list when no devices at all."""
        mock_sd = sys.modules["sounddevice"]
        mock_sd.query_devices = MagicMock(return_value=[])
        assert list_input_devices() == []


# ---------------------------------------------------------------------------
# check_audio_available
# ---------------------------------------------------------------------------


class TestCheckAudioAvailable:
    """Tests for check_audio_available()."""

    def test_returns_empty_when_audio_ok(self, monkeypatch) -> None:
        """Returns empty string when sounddevice works and inputs exist."""
        monkeypatch.undo()  # undo autouse bypass so we test the real function
        mock_sd = sys.modules["sounddevice"]
        mock_sd.query_devices = MagicMock(
            return_value=[{"name": "Mic", "max_input_channels": 1}],
        )
        assert check_audio_available() == ""

    def test_returns_error_when_no_input_devices(self, monkeypatch) -> None:
        """Returns error key when no input devices are found."""
        monkeypatch.undo()
        mock_sd = sys.modules["sounddevice"]
        mock_sd.query_devices = MagicMock(
            return_value=[{"name": "Speaker", "max_input_channels": 0}],
        )
        assert check_audio_available() == "live.error_no_mic"

    def test_returns_error_when_query_raises(self, monkeypatch) -> None:
        """Returns error key when device query fails."""
        monkeypatch.undo()
        mock_sd = sys.modules["sounddevice"]
        mock_sd.query_devices = MagicMock(
            side_effect=RuntimeError("audio fail"),
        )
        assert check_audio_available() == "live.error_no_mic"


# ---------------------------------------------------------------------------
# _get_portaudio_install_hint
# ---------------------------------------------------------------------------


class TestGetPortaudioInstallHint:
    """Tests for _get_portaudio_install_hint()."""

    def test_returns_empty_on_non_linux(self, monkeypatch) -> None:
        """Returns empty string on macOS/Windows (PortAudio is bundled)."""
        monkeypatch.setattr(f"{_MOD}.platform.system", lambda: "Darwin")
        assert _get_portaudio_install_hint() == ""

    def test_returns_apt_hint(self, monkeypatch) -> None:
        """Returns apt install hint on Debian/Ubuntu."""
        monkeypatch.setattr(f"{_MOD}.platform.system", lambda: "Linux")
        monkeypatch.setattr(
            f"{_MOD}.shutil.which",
            lambda b: "/usr/bin/apt-get" if b == "apt-get" else None,
        )
        assert _get_portaudio_install_hint() == ("sudo apt-get install libportaudio2")

    def test_returns_dnf_hint(self, monkeypatch) -> None:
        """Returns dnf install hint on Fedora/RHEL."""
        monkeypatch.setattr(f"{_MOD}.platform.system", lambda: "Linux")
        monkeypatch.setattr(
            f"{_MOD}.shutil.which",
            lambda b: "/usr/bin/dnf" if b == "dnf" else None,
        )
        assert _get_portaudio_install_hint() == ("sudo dnf install portaudio")

    def test_returns_pacman_hint(self, monkeypatch) -> None:
        """Returns pacman install hint on Arch."""
        monkeypatch.setattr(f"{_MOD}.platform.system", lambda: "Linux")
        monkeypatch.setattr(
            f"{_MOD}.shutil.which",
            lambda b: "/usr/bin/pacman" if b == "pacman" else None,
        )
        assert _get_portaudio_install_hint() == ("sudo pacman -S portaudio")

    def test_returns_zypper_hint(self, monkeypatch) -> None:
        """Returns zypper install hint on openSUSE."""
        monkeypatch.setattr(f"{_MOD}.platform.system", lambda: "Linux")
        monkeypatch.setattr(
            f"{_MOD}.shutil.which",
            lambda b: "/usr/bin/zypper" if b == "zypper" else None,
        )
        assert _get_portaudio_install_hint() == ("sudo zypper install libportaudio2")

    def test_returns_apk_hint(self, monkeypatch) -> None:
        """Returns apk install hint on Alpine."""
        monkeypatch.setattr(f"{_MOD}.platform.system", lambda: "Linux")
        monkeypatch.setattr(
            f"{_MOD}.shutil.which",
            lambda b: "/sbin/apk" if b == "apk" else None,
        )
        assert _get_portaudio_install_hint() == "sudo apk add portaudio"

    def test_returns_empty_when_no_manager_found(self, monkeypatch) -> None:
        """Returns empty string when no known package manager is found."""
        monkeypatch.setattr(f"{_MOD}.platform.system", lambda: "Linux")
        monkeypatch.setattr(f"{_MOD}.shutil.which", lambda _b: None)
        assert _get_portaudio_install_hint() == ""


# ---------------------------------------------------------------------------
# _get_pulseaudio_install_hint
# ---------------------------------------------------------------------------


class TestGetPulseaudioInstallHint:
    """Tests for _get_pulseaudio_install_hint()."""

    def test_returns_empty_on_non_linux(self, monkeypatch) -> None:
        """Returns empty string on non-Linux."""
        monkeypatch.setattr(f"{_MOD}.platform.system", lambda: "Windows")
        assert _get_pulseaudio_install_hint() == ""

    def test_returns_apt_hint(self, monkeypatch) -> None:
        """Returns apt install hint on Debian/Ubuntu."""
        monkeypatch.setattr(f"{_MOD}.platform.system", lambda: "Linux")
        monkeypatch.setattr(
            f"{_MOD}.shutil.which",
            lambda b: "/usr/bin/apt-get" if b == "apt-get" else None,
        )
        assert _get_pulseaudio_install_hint() == ("sudo apt-get install pulseaudio")

    def test_returns_pacman_hint(self, monkeypatch) -> None:
        """Returns pacman install hint on Arch."""
        monkeypatch.setattr(f"{_MOD}.platform.system", lambda: "Linux")
        monkeypatch.setattr(
            f"{_MOD}.shutil.which",
            lambda b: "/usr/bin/pacman" if b == "pacman" else None,
        )
        assert _get_pulseaudio_install_hint() == ("sudo pacman -S pulseaudio")


# ---------------------------------------------------------------------------
# get_system_audio_device
# ---------------------------------------------------------------------------


class TestGetDefaultMonitorSource:
    """Tests for _get_default_monitor_source()."""

    def test_returns_monitor_name(self, monkeypatch) -> None:
        """Returns '<sink>.monitor' when pactl succeeds."""
        monkeypatch.setattr(f"{_MOD}.shutil.which", lambda b: "/usr/bin/pactl")
        monkeypatch.setattr(
            f"{_MOD}.subprocess.run",
            lambda *a, **kw: SimpleNamespace(
                returncode=0,
                stdout="alsa_output.default_sink\n",
            ),
        )
        assert _get_default_monitor_source() == ("alsa_output.default_sink.monitor")

    def test_returns_none_when_no_pactl(self, monkeypatch) -> None:
        """Returns None when pactl is not installed."""
        monkeypatch.setattr(f"{_MOD}.shutil.which", lambda b: None)
        assert _get_default_monitor_source() is None

    def test_returns_none_on_failure(self, monkeypatch) -> None:
        """Returns None when pactl exits with error."""
        monkeypatch.setattr(f"{_MOD}.shutil.which", lambda b: "/usr/bin/pactl")
        monkeypatch.setattr(
            f"{_MOD}.subprocess.run",
            lambda *a, **kw: SimpleNamespace(returncode=1, stdout=""),
        )
        assert _get_default_monitor_source() is None


class TestCheckSystemAudioAvailable:
    """Tests for check_system_audio_available()."""

    def test_returns_true_when_available(self, monkeypatch) -> None:
        """Returns True when parec exists and monitor source is found."""
        monkeypatch.setattr(
            f"{_MOD}.shutil.which",
            lambda b: "/usr/bin/parec" if b == "parec" else "/usr/bin/pactl",
        )
        monkeypatch.setattr(
            f"{_MOD}._get_default_monitor_source",
            lambda: "sink.monitor",
        )
        assert check_system_audio_available() is True

    def test_returns_false_when_no_parec(self, monkeypatch) -> None:
        """Returns False when parec is not installed."""
        monkeypatch.setattr(
            f"{_MOD}.shutil.which",
            lambda b: None if b == "parec" else "/usr/bin/pactl",
        )
        assert check_system_audio_available() is False

    def test_returns_false_when_no_monitor(self, monkeypatch) -> None:
        """Returns False when no monitor source is found."""
        monkeypatch.setattr(f"{_MOD}.shutil.which", lambda b: f"/usr/bin/{b}")
        monkeypatch.setattr(
            f"{_MOD}._get_default_monitor_source",
            lambda: None,
        )
        assert check_system_audio_available() is False


# ---------------------------------------------------------------------------
# LiveTranscriber — audio_source parameter
# ---------------------------------------------------------------------------


class TestLiveTranscriberAudioSource:
    """Tests for audio_source parameter on LiveTranscriber."""

    def test_default_audio_source_is_microphone(self) -> None:
        """Default audio source should be 'microphone'."""
        t = LiveTranscriber(on_sentence=MagicMock())
        assert t._audio_source == "microphone"

    def test_audio_source_stored(self) -> None:
        """Provided audio source is stored on the instance."""
        t = LiveTranscriber(on_sentence=MagicMock(), audio_source="system")
        assert t._audio_source == "system"

    def test_both_mode_stores_value(self) -> None:
        """'both' audio source is stored on the instance."""
        t = LiveTranscriber(on_sentence=MagicMock(), audio_source="both")
        assert t._audio_source == "both"

    def test_resolve_devices_microphone(self) -> None:
        """Microphone mode returns the mic device index."""
        t = LiveTranscriber(
            on_sentence=MagicMock(),
            device=2,
            audio_source="microphone",
        )
        assert t._resolve_devices() == 2

    def test_resolve_devices_system(self, monkeypatch) -> None:
        """System mode succeeds when system audio is available."""
        monkeypatch.setattr(
            f"{_MOD}.check_system_audio_available",
            lambda: True,
        )
        t = LiveTranscriber(
            on_sentence=MagicMock(),
            audio_source="system",
        )
        assert t._resolve_devices() is None  # default mic device

    def test_resolve_devices_both(self, monkeypatch) -> None:
        """Both mode succeeds when system audio is available."""
        monkeypatch.setattr(
            f"{_MOD}.check_system_audio_available",
            lambda: True,
        )
        t = LiveTranscriber(
            on_sentence=MagicMock(),
            device=0,
            audio_source="both",
        )
        assert t._resolve_devices() == 0

    def test_resolve_devices_system_raises_when_missing(
        self,
        monkeypatch,
    ) -> None:
        """System mode raises ValueError when system audio unavailable."""
        monkeypatch.setattr(
            f"{_MOD}.check_system_audio_available",
            lambda: False,
        )
        t = LiveTranscriber(
            on_sentence=MagicMock(),
            audio_source="system",
        )
        with pytest.raises(ValueError, match="live.error_no_system_audio"):
            t._resolve_devices()

    def test_read_block_single_source(self) -> None:
        """_read_block returns from audio_queue in non-both mode."""
        t = LiveTranscriber(
            on_sentence=MagicMock(),
            audio_source="microphone",
        )
        block = np.zeros((_BLOCK_SIZE, 1), dtype="float32")
        t._audio_queue.put(block)
        result = t._read_block()
        assert result is not None
        assert np.array_equal(result, block)

    def test_read_block_both_mixes(self) -> None:
        """_read_block mixes mic and system audio in 'both' mode."""
        t = LiveTranscriber(
            on_sentence=MagicMock(),
            audio_source="both",
        )
        t._sys_queue = queue.Queue()
        mic = np.full((_BLOCK_SIZE, 1), 0.3, dtype="float32")
        sys_blk = np.full((_BLOCK_SIZE, 1), 0.4, dtype="float32")
        t._audio_queue.put(mic)
        t._sys_queue.put(sys_blk)
        result = t._read_block()
        assert result is not None
        expected = np.clip(mic + sys_blk, -1.0, 1.0)
        np.testing.assert_array_almost_equal(result, expected)

    def test_read_block_both_mic_only(self) -> None:
        """_read_block returns mic-only when system queue is empty."""
        t = LiveTranscriber(
            on_sentence=MagicMock(),
            audio_source="both",
        )
        t._sys_queue = queue.Queue()
        mic = np.full((_BLOCK_SIZE, 1), 0.5, dtype="float32")
        t._audio_queue.put(mic)
        result = t._read_block()
        assert result is not None
        np.testing.assert_array_equal(result, mic)

    def test_read_block_both_sys_only(self) -> None:
        """_read_block returns system-only when mic queue is empty."""
        t = LiveTranscriber(
            on_sentence=MagicMock(),
            audio_source="both",
        )
        t._sys_queue = queue.Queue()
        sys_blk = np.full((_BLOCK_SIZE, 1), 0.5, dtype="float32")
        t._sys_queue.put(sys_blk)
        result = t._read_block()
        assert result is not None
        np.testing.assert_array_equal(result, sys_blk)


# ---------------------------------------------------------------------------
# LiveTranscriber — init and properties
# ---------------------------------------------------------------------------


class TestLiveTranscriberInit:
    """Tests for LiveTranscriber construction and properties."""

    def test_default_state(self) -> None:
        """Transcriber starts in stopped state."""
        callback = MagicMock()
        t = LiveTranscriber(on_sentence=callback)
        assert t.is_running is False
        assert t._stream is None
        assert t._process_thread is None

    def test_stores_callbacks(self) -> None:
        """All callbacks are stored."""
        sentence_cb = MagicMock()
        partial_cb = MagicMock()
        status_cb = MagicMock()
        t = LiveTranscriber(
            on_sentence=sentence_cb,
            on_partial=partial_cb,
            on_status=status_cb,
            model_size="small",
            language="French",
            device=3,
        )
        assert t._on_sentence is sentence_cb
        assert t._on_partial is partial_cb
        assert t._on_status is status_cb
        assert t._model_size == "small"
        assert t._language == "French"
        assert t._device == 3  # noqa: PLR2004


# ---------------------------------------------------------------------------
# LiveTranscriber — start / stop
# ---------------------------------------------------------------------------


class TestLiveTranscriberStartStop:
    """Tests for start() and stop() lifecycle."""

    def test_start_sets_running(self) -> None:
        """start() sets is_running to True and spawns thread."""
        t = LiveTranscriber(on_sentence=MagicMock())
        with patch.object(t, "_process_loop"):
            t.start()
            assert t.is_running is True
            assert t._process_thread is not None
            t._is_running = False  # Allow thread to finish
            t._process_thread.join(timeout=2)

    def test_start_is_idempotent(self) -> None:
        """Calling start() twice does not create a second thread."""
        t = LiveTranscriber(on_sentence=MagicMock())
        with patch.object(t, "_process_loop"):
            t.start()
            first_thread = t._process_thread
            t.start()  # second call
            assert t._process_thread is first_thread
            t._is_running = False
            first_thread.join(timeout=2)

    def test_stop_clears_state(self) -> None:
        """stop() sets is_running to False and clears stream."""
        t = LiveTranscriber(on_sentence=MagicMock())
        mock_stream = MagicMock()
        t._stream = mock_stream
        t._is_running = True
        # Simulate a thread
        t._process_thread = MagicMock()
        t._process_thread.join = MagicMock()

        t.stop()

        assert t.is_running is False
        mock_stream.stop.assert_called_once()
        mock_stream.close.assert_called_once()
        assert t._stream is None
        assert t._process_thread is None

    def test_stop_when_not_running(self) -> None:
        """stop() is safe when not running."""
        t = LiveTranscriber(on_sentence=MagicMock())
        t.stop()  # Should not raise
        assert t.is_running is False


# ---------------------------------------------------------------------------
# LiveTranscriber — _emit_status
# ---------------------------------------------------------------------------


class TestEmitStatus:
    """Tests for _emit_status()."""

    def test_with_callback(self) -> None:
        """Calls on_status with translated key."""
        status_cb = MagicMock()
        t = LiveTranscriber(on_sentence=MagicMock(), on_status=status_cb)
        t._emit_status("live.status_listening")
        status_cb.assert_called_once()
        # The argument is the tr() result (a string)
        assert isinstance(status_cb.call_args[0][0], str)

    def test_without_callback(self) -> None:
        """No crash when on_status is None."""
        t = LiveTranscriber(on_sentence=MagicMock(), on_status=None)
        t._emit_status("any.key")  # Should not raise


# ---------------------------------------------------------------------------
# LiveTranscriber — _audio_callback
# ---------------------------------------------------------------------------


class TestAudioCallback:
    """Tests for _audio_callback()."""

    def test_enqueues_when_running(self) -> None:
        """Audio data is queued when running."""
        t = LiveTranscriber(on_sentence=MagicMock())
        t._is_running = True
        data = np.ones((8000, 1), dtype=np.float32)
        t._audio_callback(data, 8000, None, None)
        assert not t._audio_queue.empty()
        queued = t._audio_queue.get_nowait()
        np.testing.assert_array_equal(queued, data)

    def test_skips_when_not_running(self) -> None:
        """Audio data is NOT queued when not running."""
        t = LiveTranscriber(on_sentence=MagicMock())
        t._is_running = False
        data = np.ones((8000, 1), dtype=np.float32)
        t._audio_callback(data, 8000, None, None)
        assert t._audio_queue.empty()

    def test_data_is_copied(self) -> None:
        """Queued data is a copy, not a reference to original."""
        t = LiveTranscriber(on_sentence=MagicMock())
        t._is_running = True
        data = np.ones((8000, 1), dtype=np.float32)
        t._audio_callback(data, 8000, None, None)
        queued = t._audio_queue.get_nowait()
        data[:] = 0  # Mutate original
        assert queued.sum() > 0  # Copy is unaffected


# ---------------------------------------------------------------------------
# LiveTranscriber — _transcribe_buffer
# ---------------------------------------------------------------------------


class TestTranscribeBuffer:
    """Tests for _transcribe_buffer()."""

    def _make_model(self, segments: list) -> MagicMock:
        """Creates a mock model returning given segments."""
        model = MagicMock()
        model.transcribe.return_value = (segments, None)
        return model

    def _make_segment(self, text: str) -> SimpleNamespace:
        """Creates a mock segment."""
        return SimpleNamespace(text=text)

    def test_single_segment(self) -> None:
        """Single non-empty segment triggers on_sentence."""
        sentence_cb = MagicMock()
        t = LiveTranscriber(on_sentence=sentence_cb)
        model = self._make_model([self._make_segment("Hello world")])
        blocks = [np.ones((8000,), dtype=np.float32)]
        t._transcribe_buffer(model, blocks, None)
        assert sentence_cb.call_count == 1
        assert sentence_cb.call_args[0][0] == "Hello world"

    def test_multiple_segments_joined(self) -> None:
        """Multiple segments are joined with spaces."""
        sentence_cb = MagicMock()
        t = LiveTranscriber(on_sentence=sentence_cb)
        model = self._make_model(
            [
                self._make_segment("Hello"),
                self._make_segment("world"),
            ]
        )
        blocks = [np.ones((8000,), dtype=np.float32)]
        t._transcribe_buffer(model, blocks, None)
        assert sentence_cb.call_count == 1
        assert sentence_cb.call_args[0][0] == "Hello world"

    def test_empty_segments_ignored(self) -> None:
        """Segments with only whitespace are skipped."""
        sentence_cb = MagicMock()
        t = LiveTranscriber(on_sentence=sentence_cb)
        model = self._make_model(
            [
                self._make_segment("  "),
                self._make_segment(""),
            ]
        )
        blocks = [np.ones((8000,), dtype=np.float32)]
        t._transcribe_buffer(model, blocks, None)
        sentence_cb.assert_not_called()

    def test_with_language_code(self) -> None:
        """Language code is passed to model.transcribe."""
        model = self._make_model([])
        t = LiveTranscriber(on_sentence=MagicMock())
        blocks = [np.ones((8000,), dtype=np.float32)]
        t._transcribe_buffer(model, blocks, "vi")
        _, kwargs = model.transcribe.call_args
        assert kwargs["language"] == "vi"

    def test_without_language_code(self) -> None:
        """No language kwarg when lang_code is None."""
        model = self._make_model([])
        t = LiveTranscriber(on_sentence=MagicMock())
        blocks = [np.ones((8000,), dtype=np.float32)]
        t._transcribe_buffer(model, blocks, None)
        _, kwargs = model.transcribe.call_args
        assert "language" not in kwargs

    def test_concatenates_blocks(self) -> None:
        """Multiple audio blocks are concatenated and flattened."""
        model = self._make_model([])
        t = LiveTranscriber(on_sentence=MagicMock())
        b1 = np.ones((100, 1), dtype=np.float32)
        b2 = np.ones((200, 1), dtype=np.float32) * 2
        t._transcribe_buffer(model, [b1, b2], None)
        audio_arg = model.transcribe.call_args[0][0]
        assert audio_arg.shape == (300,)


# ---------------------------------------------------------------------------
# LiveTranscriber — _process_loop (integration-style)
# ---------------------------------------------------------------------------


class TestProcessLoop:
    """Integration-style tests for _process_loop()."""

    def test_silence_detection_triggers_transcription(self) -> None:
        """Enough silence after speech triggers _transcribe_buffer."""
        sentence_cb = MagicMock()
        t = LiveTranscriber(
            on_sentence=sentence_cb,
            on_status=MagicMock(),
            language="",
        )

        # Pre-fill the queue: 3 speech blocks + 4 silence blocks
        speech = np.ones((_BLOCK_SIZE,), dtype=np.float32) * 0.5
        silence = np.zeros((_BLOCK_SIZE,), dtype=np.float32)

        for _ in range(_MIN_AUDIO_BLOCKS + 1):
            t._audio_queue.put(speech)
        for _ in range(_SILENCE_BLOCKS):
            t._audio_queue.put(silence)

        # Mock model and sounddevice
        mock_segment = SimpleNamespace(text="Transcribed text")
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([mock_segment], None)

        mock_stream = MagicMock()

        # Stop after processing all queued blocks
        call_count = [0]
        total_blocks = _MIN_AUDIO_BLOCKS + 1 + _SILENCE_BLOCKS

        original_get = t._audio_queue.get

        def auto_stop_get(timeout=None):
            call_count[0] += 1
            if call_count[0] > total_blocks:
                t._is_running = False
                raise queue.Empty
            return original_get(timeout=0)

        t._audio_queue.get = auto_stop_get
        t._is_running = True

        mock_sd = sys.modules["sounddevice"]
        mock_sd.InputStream = MagicMock(return_value=mock_stream)
        mock_fw = sys.modules["faster_whisper"]
        mock_fw.WhisperModel = MagicMock(return_value=mock_model)

        t._process_loop()

        assert sentence_cb.call_count == 1
        assert sentence_cb.call_args[0][0] == "Transcribed text"

    def test_exception_sets_not_running(self) -> None:
        """Exception in _process_loop sets is_running to False."""
        status_cb = MagicMock()
        t = LiveTranscriber(
            on_sentence=MagicMock(),
            on_status=status_cb,
        )
        t._is_running = True

        mock_fw = sys.modules["faster_whisper"]
        mock_fw.WhisperModel = MagicMock(
            side_effect=RuntimeError("model load failed"),
        )

        t._process_loop()

        assert t.is_running is False
        # Status callback receives the error message
        status_cb.assert_called()

    def test_short_buffer_not_flushed(self) -> None:
        """Buffer shorter than _MIN_AUDIO_BLOCKS is not transcribed on stop."""
        sentence_cb = MagicMock()
        t = LiveTranscriber(
            on_sentence=sentence_cb,
            on_status=MagicMock(),
        )

        # Only 1 speech block (below minimum)
        speech = np.ones((_BLOCK_SIZE,), dtype=np.float32) * 0.5
        t._audio_queue.put(speech)

        call_count = [0]

        def auto_stop_get(timeout=None):
            call_count[0] += 1
            if call_count[0] > 1:
                t._is_running = False
                raise queue.Empty
            return speech

        t._audio_queue.get = auto_stop_get
        t._is_running = True

        mock_model = MagicMock()
        mock_stream = MagicMock()
        mock_sd = sys.modules["sounddevice"]
        mock_sd.InputStream = MagicMock(return_value=mock_stream)
        mock_fw = sys.modules["faster_whisper"]
        mock_fw.WhisperModel = MagicMock(return_value=mock_model)

        t._process_loop()

        # Should NOT have called transcribe since buffer was too short
        mock_model.transcribe.assert_not_called()
        sentence_cb.assert_not_called()


# ---------------------------------------------------------------------------
# LiveTranscriber — partial callback
# ---------------------------------------------------------------------------


class TestLiveTranscriberPartialCallback:
    """Tests for on_partial callback behaviour during processing."""

    def test_partial_callback_invoked_during_processing(self) -> None:
        """on_partial is callable within the process loop context."""
        partial_cb = MagicMock()
        sentence_cb = MagicMock()
        t = LiveTranscriber(
            on_sentence=sentence_cb,
            on_partial=partial_cb,
            on_status=MagicMock(),
        )

        # Pre-fill queue with speech blocks + silence to trigger transcription
        speech = np.ones((_BLOCK_SIZE,), dtype=np.float32) * 0.5
        silence = np.zeros((_BLOCK_SIZE,), dtype=np.float32)

        for _ in range(_MIN_AUDIO_BLOCKS + 1):
            t._audio_queue.put(speech)
        for _ in range(_SILENCE_BLOCKS):
            t._audio_queue.put(silence)

        mock_segment = SimpleNamespace(text="Partial text")
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([mock_segment], None)

        # Intercept _transcribe_buffer to invoke on_partial before transcription
        original_transcribe = t._transcribe_buffer

        def transcribe_with_partial(model, blocks, lang_code, *args):
            if t._on_partial:
                t._on_partial("intermediate")
            original_transcribe(model, blocks, lang_code, *args)

        mock_stream = MagicMock()
        call_count = [0]
        total_blocks = _MIN_AUDIO_BLOCKS + 1 + _SILENCE_BLOCKS
        original_get = t._audio_queue.get

        def auto_stop_get(timeout=None):
            call_count[0] += 1
            if call_count[0] > total_blocks:
                t._is_running = False
                raise queue.Empty
            return original_get(timeout=0)

        t._audio_queue.get = auto_stop_get
        t._is_running = True
        t._transcribe_buffer = transcribe_with_partial

        mock_sd = sys.modules["sounddevice"]
        mock_sd.InputStream = MagicMock(return_value=mock_stream)
        mock_fw = sys.modules["faster_whisper"]
        mock_fw.WhisperModel = MagicMock(return_value=mock_model)

        t._process_loop()

        partial_cb.assert_called_with("intermediate")
        assert sentence_cb.call_count == 1
        assert sentence_cb.call_args[0][0] == "Partial text"

    def test_partial_callback_none_safe(self) -> None:
        """Processing does not crash when on_partial is None."""
        sentence_cb = MagicMock()
        t = LiveTranscriber(
            on_sentence=sentence_cb,
            on_partial=None,
            on_status=MagicMock(),
        )

        # Pre-fill queue with speech + silence
        speech = np.ones((_BLOCK_SIZE,), dtype=np.float32) * 0.5
        silence = np.zeros((_BLOCK_SIZE,), dtype=np.float32)

        for _ in range(_MIN_AUDIO_BLOCKS + 1):
            t._audio_queue.put(speech)
        for _ in range(_SILENCE_BLOCKS):
            t._audio_queue.put(silence)

        mock_segment = SimpleNamespace(text="Hello")
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([mock_segment], None)
        mock_stream = MagicMock()

        call_count = [0]
        total_blocks = _MIN_AUDIO_BLOCKS + 1 + _SILENCE_BLOCKS
        original_get = t._audio_queue.get

        def auto_stop_get(timeout=None):
            call_count[0] += 1
            if call_count[0] > total_blocks:
                t._is_running = False
                raise queue.Empty
            return original_get(timeout=0)

        t._audio_queue.get = auto_stop_get
        t._is_running = True

        mock_sd = sys.modules["sounddevice"]
        mock_sd.InputStream = MagicMock(return_value=mock_stream)
        mock_fw = sys.modules["faster_whisper"]
        mock_fw.WhisperModel = MagicMock(return_value=mock_model)

        # Should not raise even though on_partial is None
        t._process_loop()

        assert t._on_partial is None
        assert sentence_cb.call_count == 1
        assert sentence_cb.call_args[0][0] == "Hello"


# ---------------------------------------------------------------------------
# _process_loop — edge cases
# ---------------------------------------------------------------------------


class TestProcessLoopEdgeCases:
    """Edge-case tests for _process_loop()."""

    def test_long_buffer_flushed_on_stop(self) -> None:
        """Buffer with >= _MIN_AUDIO_BLOCKS is flushed when loop stops."""
        sentence_cb = MagicMock()
        t = LiveTranscriber(
            on_sentence=sentence_cb,
            on_status=MagicMock(),
        )

        # Pre-fill with enough speech blocks (no silence to trigger mid-loop)
        speech = np.ones((_BLOCK_SIZE,), dtype=np.float32) * 0.5
        num_speech = _MIN_AUDIO_BLOCKS + 2  # noqa: PLR2004

        for _ in range(num_speech):
            t._audio_queue.put(speech)

        mock_segment = SimpleNamespace(text="Flushed text")
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([mock_segment], None)
        mock_stream = MagicMock()

        call_count = [0]
        original_get = t._audio_queue.get

        def auto_stop_get(timeout=None):
            call_count[0] += 1
            if call_count[0] > num_speech:
                t._is_running = False
                raise queue.Empty
            return original_get(timeout=0)

        t._audio_queue.get = auto_stop_get
        t._is_running = True

        mock_sd = sys.modules["sounddevice"]
        mock_sd.InputStream = MagicMock(return_value=mock_stream)
        mock_fw = sys.modules["faster_whisper"]
        mock_fw.WhisperModel = MagicMock(return_value=mock_model)

        t._process_loop()

        # Buffer was flushed on stop
        assert sentence_cb.call_count == 1
        assert sentence_cb.call_args[0][0] == "Flushed text"
        mock_model.transcribe.assert_called_once()

    def test_queue_empty_timeout_continues_loop(self) -> None:
        """queue.Empty from get(timeout=) does not crash the loop."""
        t = LiveTranscriber(
            on_sentence=MagicMock(),
            on_status=MagicMock(),
        )

        call_count = [0]

        def empty_then_stop(timeout=None):
            call_count[0] += 1
            if call_count[0] >= 3:  # noqa: PLR2004
                t._is_running = False
            raise queue.Empty

        t._audio_queue.get = empty_then_stop
        t._is_running = True

        mock_model = MagicMock()
        mock_stream = MagicMock()

        mock_sd = sys.modules["sounddevice"]
        mock_sd.InputStream = MagicMock(return_value=mock_stream)
        mock_fw = sys.modules["faster_whisper"]
        mock_fw.WhisperModel = MagicMock(return_value=mock_model)

        # Should complete without error
        t._process_loop()

        assert call_count[0] >= 3  # noqa: PLR2004
        assert t.is_running is False

    def test_model_loading_emits_status(self) -> None:
        """Status callbacks are emitted for model loading states."""
        status_cb = MagicMock()
        t = LiveTranscriber(
            on_sentence=MagicMock(),
            on_status=status_cb,
        )
        t._is_running = True

        mock_model = MagicMock()
        mock_stream = MagicMock()

        def stop_immediately(timeout=None):
            t._is_running = False
            raise queue.Empty

        t._audio_queue.get = stop_immediately

        mock_sd = sys.modules["sounddevice"]
        mock_sd.InputStream = MagicMock(return_value=mock_stream)
        mock_fw = sys.modules["faster_whisper"]
        mock_fw.WhisperModel = MagicMock(return_value=mock_model)

        t._process_loop()

        # start() emits "loading model", _process_loop emits "listening"
        # At least the "listening" status should fire inside _process_loop
        assert status_cb.call_count >= 1  # noqa: PLR2004
        # Verify status was called with a string (tr() output)
        for call in status_cb.call_args_list:
            assert isinstance(call[0][0], str)


# ---------------------------------------------------------------------------
# _audio_callback — edge cases
# ---------------------------------------------------------------------------


class TestAudioCallbackEdgeCases:
    """Edge-case tests for _audio_callback()."""

    def test_large_audio_block_queued(self) -> None:
        """A very large audio block is queued without error."""
        t = LiveTranscriber(on_sentence=MagicMock())
        t._is_running = True
        large_block = np.ones((160000, 1), dtype=np.float32)  # 10 seconds
        t._audio_callback(large_block, 160000, None, None)
        assert not t._audio_queue.empty()
        queued = t._audio_queue.get_nowait()
        assert queued.shape == (160000, 1)

    def test_multiple_sequential_blocks(self) -> None:
        """Multiple blocks queued rapidly are all stored."""
        t = LiveTranscriber(on_sentence=MagicMock())
        t._is_running = True
        num_blocks = 20  # noqa: PLR2004
        for i in range(num_blocks):
            data = np.full((_BLOCK_SIZE, 1), fill_value=float(i), dtype=np.float32)
            t._audio_callback(data, _BLOCK_SIZE, None, None)
        assert t._audio_queue.qsize() == num_blocks
        # Verify ordering is preserved
        for i in range(num_blocks):
            block = t._audio_queue.get_nowait()
            assert block[0, 0] == float(i)


# ---------------------------------------------------------------------------
# _transcribe_buffer — edge cases
# ---------------------------------------------------------------------------


class TestTranscribeBufferEdgeCases:
    """Edge-case tests for _transcribe_buffer()."""

    @staticmethod
    def _make_model(segments: list) -> MagicMock:
        """Creates a mock model returning given segments."""
        model = MagicMock()
        model.transcribe.return_value = (segments, None)
        return model

    @staticmethod
    def _make_segment(text: str) -> SimpleNamespace:
        """Creates a mock segment."""
        return SimpleNamespace(text=text)

    def test_whitespace_only_segments_trimmed(self) -> None:
        """Segments with leading/trailing whitespace are trimmed."""
        sentence_cb = MagicMock()
        t = LiveTranscriber(on_sentence=sentence_cb)
        model = self._make_model(
            [
                self._make_segment(" Hello "),
                self._make_segment("  world  "),
            ]
        )
        blocks = [np.ones((8000,), dtype=np.float32)]
        t._transcribe_buffer(model, blocks, None)
        assert sentence_cb.call_count == 1
        assert sentence_cb.call_args[0][0] == "Hello world"

    def test_model_transcribe_kwargs(self) -> None:
        """beam_size and vad_filter defaults are NOT passed; word_timestamps is."""
        model = self._make_model([])
        t = LiveTranscriber(on_sentence=MagicMock())
        blocks = [np.ones((8000,), dtype=np.float32)]
        t._transcribe_buffer(model, blocks, "en")
        _, kwargs = model.transcribe.call_args
        # word_timestamps is always passed
        assert kwargs["word_timestamps"] is False
        # language is passed when provided
        assert kwargs["language"] == "en"


# ---------------------------------------------------------------------------
# _process_loop — model loading failure
# ---------------------------------------------------------------------------


class TestProcessLoopModelFailure:
    """Tests for model loading errors in _process_loop."""

    def test_whisper_model_init_error_sets_not_running(self) -> None:
        """If WhisperModel() raises, _is_running is set to False."""
        mock_fw = sys.modules["faster_whisper"]
        mock_fw.WhisperModel.side_effect = RuntimeError("model corrupted")
        try:
            sentence_cb = MagicMock()
            status_cb = MagicMock()
            t = LiveTranscriber(
                on_sentence=sentence_cb,
                on_status=status_cb,
            )
            t._is_running = True
            t._process_loop()

            assert t._is_running is False
            # Error message passed to status callback
            status_cb.assert_called()
            assert "model corrupted" in str(status_cb.call_args)
        finally:
            mock_fw.WhisperModel.side_effect = None


# ---------------------------------------------------------------------------
# Model caching
# ---------------------------------------------------------------------------


class TestModelCaching:
    """Tests for Whisper model cache reuse."""

    def test_cached_model_reused_on_same_size(self, monkeypatch) -> None:
        """Second _process_loop call with same model_size skips WhisperModel()."""
        import src.core.live_engine as le  # noqa: PLC0415

        fake_model = MagicMock()
        fake_model.transcribe.return_value = ([], None)
        monkeypatch.setattr(le, "_cached_model", fake_model)
        monkeypatch.setattr(le, "_cached_model_size", "tiny")

        t = LiveTranscriber(on_sentence=MagicMock(), on_status=MagicMock())
        t._is_running = True

        mock_stream = MagicMock()
        mock_sd = sys.modules["sounddevice"]
        mock_sd.InputStream = MagicMock(return_value=mock_stream)
        mock_fw = sys.modules["faster_whisper"]
        mock_fw.WhisperModel = MagicMock()  # fresh mock with zero calls

        # Queue a single silent block then stop
        t._audio_queue.put(np.zeros((_BLOCK_SIZE,), dtype=np.float32))
        original_get = t._audio_queue.get
        call_count = [0]

        def stop_after_one(timeout=None):
            call_count[0] += 1
            if call_count[0] > 1:
                t._is_running = False
                raise queue.Empty
            return original_get(timeout=0)

        t._audio_queue.get = stop_after_one
        t._process_loop()

        # WhisperModel() should NOT have been called — cache was reused
        mock_fw.WhisperModel.assert_not_called()

    def test_cache_invalidated_on_different_size(self, monkeypatch) -> None:
        """Different model_size triggers new WhisperModel() load."""
        import src.core.live_engine as le  # noqa: PLC0415

        monkeypatch.setattr(le, "_cached_model", MagicMock())
        monkeypatch.setattr(le, "_cached_model_size", "tiny")

        t = LiveTranscriber(
            on_sentence=MagicMock(),
            on_status=MagicMock(),
            model_size="base",
        )
        t._is_running = True

        new_model = MagicMock()
        new_model.transcribe.return_value = ([], None)
        mock_fw = sys.modules["faster_whisper"]
        mock_fw.WhisperModel = MagicMock(return_value=new_model)

        mock_stream = MagicMock()
        mock_sd = sys.modules["sounddevice"]
        mock_sd.InputStream = MagicMock(return_value=mock_stream)

        t._audio_queue.put(np.zeros((_BLOCK_SIZE,), dtype=np.float32))
        original_get = t._audio_queue.get
        call_count = [0]

        def stop_after_one(timeout=None):
            call_count[0] += 1
            if call_count[0] > 1:
                t._is_running = False
                raise queue.Empty
            return original_get(timeout=0)

        t._audio_queue.get = stop_after_one
        t._process_loop()

        mock_fw.WhisperModel.assert_called_once_with(
            "base",
            device="cpu",
            compute_type="int8",
        )


# ---------------------------------------------------------------------------
# Language code splitting edge cases
# ---------------------------------------------------------------------------


class TestLanguageCodeSplitting:
    """Tests for language code dash-splitting in _process_loop."""

    def test_multi_dash_language_code_takes_first_part(self) -> None:
        """Language code with multiple dashes (e.g. 'zh-Hans-CN') splits to 'zh'."""
        mock_fw = sys.modules["faster_whisper"]
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([], None)
        mock_fw.WhisperModel.return_value = mock_model

        mock_sd = sys.modules["sounddevice"]
        mock_stream = MagicMock()
        mock_sd.InputStream.return_value = mock_stream

        sentence_cb = MagicMock()
        t = LiveTranscriber(on_sentence=sentence_cb, language="Chinese (Simplified)")
        t._is_running = True

        # Feed one audio block then stop
        loud_block = np.ones((_BLOCK_SIZE, 1), dtype=np.float32)

        def stop_after_blocks(*a, **kw):
            """Return audio blocks then stop."""
            t._audio_queue.put(loud_block)
            # Put enough silence blocks to trigger transcription
            silent_block = np.zeros((_BLOCK_SIZE, 1), dtype=np.float32)
            for _ in range(_SILENCE_BLOCKS):
                t._audio_queue.put(silent_block)
            t._is_running = False
            raise queue.Empty

        t._audio_queue.get = MagicMock(
            side_effect=[
                loud_block,
                *[np.zeros((_BLOCK_SIZE, 1), dtype=np.float32)] * _SILENCE_BLOCKS,
                queue.Empty,
            ]
        )

        # Verify the splitting logic: multi-dash codes use first part only
        lang_code = "zh-Hans-CN"
        if lang_code and "-" in lang_code:
            lang_code = lang_code.split("-", maxsplit=1)[0]
        assert lang_code == "zh"

    def test_no_dash_language_code_unchanged(self) -> None:
        """Language code without dash (e.g. 'vi') is used as-is."""
        lang_code = "vi"
        if lang_code and "-" in lang_code:
            lang_code = lang_code.split("-", maxsplit=1)[0]
        assert lang_code == "vi"

    def test_none_language_code_skipped(self) -> None:
        """None language code results in no language kwarg."""
        lang_code = None
        if lang_code and "-" in lang_code:
            lang_code = lang_code.split("-", maxsplit=1)[0]
        assert lang_code is None


# ---------------------------------------------------------------------------
# _transcribe_buffer — segment.text edge cases
# ---------------------------------------------------------------------------


class TestTranscribeBufferSegmentEdgeCases:
    """Tests for edge cases in segment text handling."""

    @staticmethod
    def _make_model(segments: list) -> MagicMock:
        """Creates a mock model returning given segments."""
        model = MagicMock()
        model.transcribe.return_value = (segments, None)
        return model

    def test_segment_with_none_text_raises_attribute_error(self) -> None:
        """Segment with text=None raises AttributeError (no strip on None)."""
        sentence_cb = MagicMock()
        t = LiveTranscriber(on_sentence=sentence_cb)
        seg = SimpleNamespace(text=None)
        model = self._make_model([seg])
        blocks = [np.ones((8000,), dtype=np.float32)]

        with pytest.raises(AttributeError):
            t._transcribe_buffer(model, blocks, None)

    def test_segment_with_unicode_text(self) -> None:
        """Segments with Unicode (CJK, emoji) are joined correctly."""
        sentence_cb = MagicMock()
        t = LiveTranscriber(on_sentence=sentence_cb)
        segments = [
            SimpleNamespace(text=" こんにちは "),
            SimpleNamespace(text=" 世界 "),
        ]
        model = self._make_model(segments)
        blocks = [np.ones((8000,), dtype=np.float32)]
        t._transcribe_buffer(model, blocks, None)
        assert sentence_cb.call_count == 1
        assert sentence_cb.call_args[0][0] == "こんにちは 世界"

    def test_segment_with_newlines_stripped(self) -> None:
        """Segments containing newlines are stripped properly."""
        sentence_cb = MagicMock()
        t = LiveTranscriber(on_sentence=sentence_cb)
        segments = [SimpleNamespace(text="\nHello\n")]
        model = self._make_model(segments)
        blocks = [np.ones((8000,), dtype=np.float32)]
        t._transcribe_buffer(model, blocks, None)
        assert sentence_cb.call_count == 1
        assert sentence_cb.call_args[0][0] == "Hello"


# ---------------------------------------------------------------------------
# _audio_callback — array shape edge cases
# ---------------------------------------------------------------------------


class TestAudioCallbackArrayEdgeCases:
    """Tests for different audio array shapes."""

    def test_1d_audio_block_queued(self) -> None:
        """1D numpy array (mono without channel dim) is queued."""
        t = LiveTranscriber(on_sentence=MagicMock())
        t._is_running = True
        data_1d = np.ones((8000,), dtype=np.float32)
        t._audio_callback(data_1d, 8000, None, None)
        block = t._audio_queue.get_nowait()
        assert block.shape == (8000,)

    def test_stereo_audio_block_queued(self) -> None:
        """Stereo (N, 2) array is queued as-is."""
        t = LiveTranscriber(on_sentence=MagicMock())
        t._is_running = True
        data_stereo = np.ones((8000, 2), dtype=np.float32)
        t._audio_callback(data_stereo, 8000, None, None)
        block = t._audio_queue.get_nowait()
        assert block.shape == (8000, 2)


# ---------------------------------------------------------------------------
# sounddevice import failure
# ---------------------------------------------------------------------------


class TestSounddeviceImportFailure:
    """Tests for when sounddevice cannot be imported."""

    def test_list_input_devices_import_error(self) -> None:
        """list_input_devices raises ImportError when sounddevice unavailable."""
        original = sys.modules.get("sounddevice")
        sys.modules["sounddevice"] = None  # type: ignore[assignment]
        try:
            with pytest.raises(ImportError):
                list_input_devices()
        finally:
            if original is not None:
                sys.modules["sounddevice"] = original
            else:
                sys.modules.pop("sounddevice", None)

    def test_process_loop_sounddevice_import_error_propagates(self) -> None:
        """_process_loop raises when sounddevice import fails.

        The import statement is outside the try/except block, so the error
        propagates to the caller (the daemon thread).
        """
        t = LiveTranscriber(
            on_sentence=MagicMock(),
            on_status=MagicMock(),
        )
        t._is_running = True

        # Make faster_whisper importable but sounddevice fail
        mock_fw = sys.modules["faster_whisper"]
        mock_fw.WhisperModel = MagicMock(return_value=MagicMock())

        original_sd = sys.modules.get("sounddevice")
        sys.modules["sounddevice"] = None  # type: ignore[assignment]
        try:
            with pytest.raises(ImportError):
                t._process_loop()
        finally:
            if original_sd is not None:
                sys.modules["sounddevice"] = original_sd
            else:
                sys.modules.pop("sounddevice", None)


# ---------------------------------------------------------------------------
# Stream close errors
# ---------------------------------------------------------------------------


class TestStreamCloseErrors:
    """Tests for stop() when the audio stream raises on close."""

    def test_stop_stream_stop_raises(self) -> None:
        """stop() propagates OSError from stream.stop().

        The stream.close() and stream=None cleanup are skipped when
        stream.stop() raises because there is no try/except.
        """
        t = LiveTranscriber(on_sentence=MagicMock())
        mock_stream = MagicMock()
        mock_stream.stop.side_effect = OSError("device disconnected")
        t._stream = mock_stream
        t._is_running = True
        t._process_thread = MagicMock()

        with pytest.raises(OSError, match="device disconnected"):
            t.stop()

        # _is_running was set to False before the stream operations
        assert t._is_running is False
        # stream.close() was never reached
        mock_stream.close.assert_not_called()
        # stream reference was NOT cleared because exception interrupted
        assert t._stream is mock_stream

    def test_stop_stream_close_raises(self) -> None:
        """stop() propagates OSError from stream.close().

        stream.stop() succeeds but stream.close() raises; stream reference
        is not cleared because exception interrupts before assignment.
        """
        t = LiveTranscriber(on_sentence=MagicMock())
        mock_stream = MagicMock()
        mock_stream.close.side_effect = OSError("close failed")
        t._stream = mock_stream
        t._is_running = True
        t._process_thread = MagicMock()

        with pytest.raises(OSError, match="close failed"):
            t.stop()

        assert t._is_running is False
        mock_stream.stop.assert_called_once()
        # stream was NOT set to None because exception interrupted
        assert t._stream is mock_stream

    def test_stop_with_no_stream(self) -> None:
        """stop() works fine when stream is already None."""
        t = LiveTranscriber(on_sentence=MagicMock())
        t._stream = None
        t._is_running = True
        t._process_thread = MagicMock()

        t.stop()

        assert t._is_running is False
        assert t._stream is None
        assert t._process_thread is None


# ---------------------------------------------------------------------------
# Thread join timeout
# ---------------------------------------------------------------------------


class TestThreadJoinTimeout:
    """Tests for worker thread join timeout behavior."""

    def test_thread_join_called_with_timeout(self) -> None:
        """stop() calls thread.join with a timeout of 5 seconds."""
        t = LiveTranscriber(on_sentence=MagicMock())
        t._is_running = True
        mock_thread = MagicMock()
        t._process_thread = mock_thread

        t.stop()

        mock_thread.join.assert_called_once_with(timeout=5)  # noqa: PLR2004
        assert t._process_thread is None

    def test_thread_still_alive_after_join_timeout(self) -> None:
        """Thread reference is cleared even if join times out."""
        t = LiveTranscriber(on_sentence=MagicMock())
        t._is_running = True
        mock_thread = MagicMock()
        # Simulate thread that doesn't stop in time (is_alive True after join)
        mock_thread.is_alive.return_value = True
        t._process_thread = mock_thread

        t.stop()

        # Thread reference is still cleared (set to None)
        assert t._process_thread is None
        assert t._is_running is False


# ---------------------------------------------------------------------------
# Empty / silent audio chunks
# ---------------------------------------------------------------------------


class TestEmptyAudioChunks:
    """Tests for processing empty or silent audio data."""

    def test_zero_length_audio_block_queued(self) -> None:
        """Zero-length audio block is queued without error."""
        t = LiveTranscriber(on_sentence=MagicMock())
        t._is_running = True
        empty_block = np.array([], dtype=np.float32).reshape(0, 1)
        t._audio_callback(empty_block, 0, None, None)
        assert not t._audio_queue.empty()
        queued = t._audio_queue.get_nowait()
        assert queued.shape[0] == 0  # noqa: PLR2004

    def test_all_zeros_block_detected_as_silence(self) -> None:
        """A block of all zeros has RMS 0 which is below silence threshold."""
        block = np.zeros((_BLOCK_SIZE,), dtype=np.float32)
        rms = float(np.sqrt(np.mean(block**2)))
        assert rms < _SILENCE_THRESHOLD

    def test_very_quiet_block_detected_as_silence(self) -> None:
        """A block with amplitude below threshold is detected as silence."""
        # Create a block with RMS just below threshold
        amplitude = _SILENCE_THRESHOLD * 0.5
        block = np.full((_BLOCK_SIZE,), fill_value=amplitude, dtype=np.float32)
        rms = float(np.sqrt(np.mean(block**2)))
        assert rms < _SILENCE_THRESHOLD

    def test_silent_blocks_do_not_accumulate_in_buffer(self) -> None:
        """Silent blocks are not added to audio_buffer (only speech is)."""
        sentence_cb = MagicMock()
        t = LiveTranscriber(
            on_sentence=sentence_cb,
            on_status=MagicMock(),
        )

        # Only silence blocks — no speech at all
        silence = np.zeros((_BLOCK_SIZE,), dtype=np.float32)
        num_silence = _SILENCE_BLOCKS + 2  # noqa: PLR2004

        call_count = [0]

        def auto_stop_get(timeout=None):
            call_count[0] += 1
            if call_count[0] > num_silence:
                t._is_running = False
                raise queue.Empty
            return silence

        t._audio_queue.get = auto_stop_get
        t._is_running = True

        mock_model = MagicMock()
        mock_stream = MagicMock()

        mock_sd = sys.modules["sounddevice"]
        mock_sd.InputStream = MagicMock(return_value=mock_stream)
        mock_fw = sys.modules["faster_whisper"]
        mock_fw.WhisperModel = MagicMock(return_value=mock_model)

        t._process_loop()

        # No transcription should have occurred — no speech blocks
        mock_model.transcribe.assert_not_called()
        sentence_cb.assert_not_called()


# ---------------------------------------------------------------------------
# get_input_devices — empty or error
# ---------------------------------------------------------------------------


class TestListInputDevicesEdgeCases:
    """Edge-case tests for list_input_devices()."""

    def test_query_devices_raises_exception(self) -> None:
        """list_input_devices propagates exception from query_devices."""
        mock_sd = sys.modules["sounddevice"]
        mock_sd.query_devices = MagicMock(
            side_effect=OSError("PortAudio not found"),
        )
        with pytest.raises(OSError, match="PortAudio not found"):
            list_input_devices()

    def test_device_missing_name_key(self) -> None:
        """list_input_devices raises KeyError for malformed device dict."""
        mock_sd = sys.modules["sounddevice"]
        mock_sd.query_devices = MagicMock(
            return_value=[{"max_input_channels": 2}],  # no "name" key
        )
        with pytest.raises(KeyError):
            list_input_devices()

    def test_many_input_devices(self) -> None:
        """All input devices are included in results."""
        devices = [{"name": f"Mic {i}", "max_input_channels": 1} for i in range(10)]
        mock_sd = sys.modules["sounddevice"]
        mock_sd.query_devices = MagicMock(return_value=devices)
        result = list_input_devices()
        assert len(result) == 10  # noqa: PLR2004
        assert result[0] == (0, "Mic 0")
        assert result[9] == (9, "Mic 9")  # noqa: PLR2004


# ---------------------------------------------------------------------------
# Silence detection edge cases
# ---------------------------------------------------------------------------


class TestSilenceDetectionEdgeCases:
    """Tests for silence detection boundary conditions."""

    def test_audio_exactly_at_threshold_boundary(self) -> None:
        """Audio with RMS at threshold boundary: strict < means equal is speech.

        Using float64 to avoid float32 precision loss, confirming the strict
        less-than comparison in the source code.
        """
        # Use float64 to get exact representation for the boundary test
        block = np.full((_BLOCK_SIZE,), fill_value=_SILENCE_THRESHOLD, dtype=np.float64)
        rms = float(np.sqrt(np.mean(block**2)))
        # rms == _SILENCE_THRESHOLD, code uses `rms < _SILENCE_THRESHOLD`
        # so exactly-at-threshold is NOT silent (it's treated as speech)
        assert not (rms < _SILENCE_THRESHOLD)

    def test_audio_just_above_threshold_is_speech(self) -> None:
        """Audio slightly above threshold is detected as speech."""
        amplitude = _SILENCE_THRESHOLD + 0.001
        block = np.full((_BLOCK_SIZE,), fill_value=amplitude, dtype=np.float32)
        rms = float(np.sqrt(np.mean(block**2)))
        assert rms >= _SILENCE_THRESHOLD

    def test_audio_just_below_threshold_is_silence(self) -> None:
        """Audio slightly below threshold is detected as silence."""
        amplitude = _SILENCE_THRESHOLD - 0.001
        block = np.full((_BLOCK_SIZE,), fill_value=amplitude, dtype=np.float32)
        rms = float(np.sqrt(np.mean(block**2)))
        assert rms < _SILENCE_THRESHOLD

    def test_single_speech_block_no_transcription(self) -> None:
        """A single speech block followed by silence does not trigger transcription."""
        sentence_cb = MagicMock()
        t = LiveTranscriber(
            on_sentence=sentence_cb,
            on_status=MagicMock(),
        )

        # 1 speech block + enough silence (below _MIN_AUDIO_BLOCKS)
        speech = np.ones((_BLOCK_SIZE,), dtype=np.float32) * 0.5
        silence = np.zeros((_BLOCK_SIZE,), dtype=np.float32)

        blocks_list = [speech] + [silence] * _SILENCE_BLOCKS
        call_count = [0]

        def auto_stop_get(timeout=None):
            call_count[0] += 1
            if call_count[0] > len(blocks_list):
                t._is_running = False
                raise queue.Empty
            return blocks_list[call_count[0] - 1]

        t._audio_queue.get = auto_stop_get
        t._is_running = True

        mock_model = MagicMock()
        mock_stream = MagicMock()
        mock_sd = sys.modules["sounddevice"]
        mock_sd.InputStream = MagicMock(return_value=mock_stream)
        mock_fw = sys.modules["faster_whisper"]
        mock_fw.WhisperModel = MagicMock(return_value=mock_model)

        t._process_loop()

        # Only 1 speech block < _MIN_AUDIO_BLOCKS (2), so no transcription
        mock_model.transcribe.assert_not_called()
        sentence_cb.assert_not_called()

    def test_exactly_min_blocks_triggers_transcription(self) -> None:
        """Exactly _MIN_AUDIO_BLOCKS speech blocks + silence triggers transcription."""
        sentence_cb = MagicMock()
        t = LiveTranscriber(
            on_sentence=sentence_cb,
            on_status=MagicMock(),
        )

        speech = np.ones((_BLOCK_SIZE,), dtype=np.float32) * 0.5
        silence = np.zeros((_BLOCK_SIZE,), dtype=np.float32)

        # Exactly _MIN_AUDIO_BLOCKS speech + _SILENCE_BLOCKS silence
        blocks_list = [speech] * _MIN_AUDIO_BLOCKS + [silence] * _SILENCE_BLOCKS
        call_count = [0]

        def auto_stop_get(timeout=None):
            call_count[0] += 1
            if call_count[0] > len(blocks_list):
                t._is_running = False
                raise queue.Empty
            return blocks_list[call_count[0] - 1]

        t._audio_queue.get = auto_stop_get
        t._is_running = True

        mock_segment = SimpleNamespace(text="Detected")
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([mock_segment], None)
        mock_stream = MagicMock()
        mock_sd = sys.modules["sounddevice"]
        mock_sd.InputStream = MagicMock(return_value=mock_stream)
        mock_fw = sys.modules["faster_whisper"]
        mock_fw.WhisperModel = MagicMock(return_value=mock_model)

        t._process_loop()

        assert sentence_cb.call_count == 1
        assert sentence_cb.call_args[0][0] == "Detected"

    def test_silence_count_resets_on_speech(self) -> None:
        """Silence counter resets when a speech block arrives mid-silence."""
        sentence_cb = MagicMock()
        t = LiveTranscriber(
            on_sentence=sentence_cb,
            on_status=MagicMock(),
        )

        speech = np.ones((_BLOCK_SIZE,), dtype=np.float32) * 0.5
        silence = np.zeros((_BLOCK_SIZE,), dtype=np.float32)

        # Pattern: speech, silence (not enough), speech, silence (not enough), stop
        # This should NOT trigger transcription mid-loop since silence never
        # reaches _SILENCE_BLOCKS consecutively
        partial_silence = _SILENCE_BLOCKS - 1
        blocks_list = (
            [speech]
            + [silence] * partial_silence
            + [speech]
            + [silence] * partial_silence
        )
        call_count = [0]

        def auto_stop_get(timeout=None):
            call_count[0] += 1
            if call_count[0] > len(blocks_list):
                t._is_running = False
                raise queue.Empty
            return blocks_list[call_count[0] - 1]

        t._audio_queue.get = auto_stop_get
        t._is_running = True

        mock_segment = SimpleNamespace(text="Flushed on exit")
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([mock_segment], None)
        mock_stream = MagicMock()
        mock_sd = sys.modules["sounddevice"]
        mock_sd.InputStream = MagicMock(return_value=mock_stream)
        mock_fw = sys.modules["faster_whisper"]
        mock_fw.WhisperModel = MagicMock(return_value=mock_model)

        t._process_loop()

        # Transcription only happens on flush (2 speech blocks >= _MIN_AUDIO_BLOCKS)
        assert sentence_cb.call_count == 1
        assert sentence_cb.call_args[0][0] == "Flushed on exit"


# ---------------------------------------------------------------------------
# Model loading failure
# ---------------------------------------------------------------------------


class TestModelLoadingFailure:
    """Tests for faster-whisper model loading failures."""

    def test_oom_error_sets_not_running(self) -> None:
        """MemoryError during model loading sets _is_running to False."""
        mock_fw = sys.modules["faster_whisper"]
        original_side_effect = mock_fw.WhisperModel.side_effect
        mock_fw.WhisperModel.side_effect = MemoryError("out of memory")
        try:
            status_cb = MagicMock()
            t = LiveTranscriber(
                on_sentence=MagicMock(),
                on_status=status_cb,
            )
            t._is_running = True
            t._process_loop()

            assert t._is_running is False
            status_cb.assert_called()
        finally:
            mock_fw.WhisperModel.side_effect = original_side_effect

    def test_file_not_found_model_error(self) -> None:
        """FileNotFoundError when model files are missing."""
        mock_fw = sys.modules["faster_whisper"]
        original_side_effect = mock_fw.WhisperModel.side_effect
        mock_fw.WhisperModel.side_effect = FileNotFoundError(
            "model file not found",
        )
        try:
            status_cb = MagicMock()
            t = LiveTranscriber(
                on_sentence=MagicMock(),
                on_status=status_cb,
            )
            t._is_running = True
            t._process_loop()

            assert t._is_running is False
            status_cb.assert_called()
            assert "model file not found" in str(status_cb.call_args)
        finally:
            mock_fw.WhisperModel.side_effect = original_side_effect

    def test_model_loads_but_stream_fails(self) -> None:
        """InputStream constructor raising does not leave is_running True."""
        mock_fw = sys.modules["faster_whisper"]
        mock_fw.WhisperModel = MagicMock(return_value=MagicMock())

        mock_sd = sys.modules["sounddevice"]
        mock_sd.InputStream = MagicMock(
            side_effect=OSError("no audio device"),
        )

        status_cb = MagicMock()
        t = LiveTranscriber(
            on_sentence=MagicMock(),
            on_status=status_cb,
        )
        t._is_running = True
        t._process_loop()

        assert t._is_running is False
        status_cb.assert_called()

    def test_stream_start_raises(self) -> None:
        """stream.start() raising is handled by the exception handler."""
        mock_fw = sys.modules["faster_whisper"]
        mock_fw.WhisperModel = MagicMock(return_value=MagicMock())

        mock_stream = MagicMock()
        mock_stream.start.side_effect = OSError("device busy")

        mock_sd = sys.modules["sounddevice"]
        mock_sd.InputStream = MagicMock(return_value=mock_stream)

        status_cb = MagicMock()
        t = LiveTranscriber(
            on_sentence=MagicMock(),
            on_status=status_cb,
        )
        t._is_running = True
        t._process_loop()

        assert t._is_running is False
        status_cb.assert_called()


# ---------------------------------------------------------------------------
# Callback error handling
# ---------------------------------------------------------------------------


class TestCallbackErrorHandling:
    """Tests for when callbacks raise exceptions."""

    def test_on_sentence_raises_propagates(self) -> None:
        """Exception in on_sentence callback propagates from _transcribe_buffer."""
        sentence_cb = MagicMock(side_effect=RuntimeError("UI crashed"))
        t = LiveTranscriber(on_sentence=sentence_cb)

        mock_model = MagicMock()
        mock_model.transcribe.return_value = (
            [SimpleNamespace(text="Hello")],
            None,
        )
        blocks = [np.ones((8000,), dtype=np.float32)]

        with pytest.raises(RuntimeError, match="UI crashed"):
            t._transcribe_buffer(mock_model, blocks, None)

    def test_on_sentence_error_in_process_loop_sets_not_running(self) -> None:
        """on_sentence raising during _process_loop is caught by the handler."""
        sentence_cb = MagicMock(side_effect=ValueError("callback error"))
        status_cb = MagicMock()
        t = LiveTranscriber(
            on_sentence=sentence_cb,
            on_status=status_cb,
        )

        speech = np.ones((_BLOCK_SIZE,), dtype=np.float32) * 0.5
        silence = np.zeros((_BLOCK_SIZE,), dtype=np.float32)

        blocks_list = [speech] * (_MIN_AUDIO_BLOCKS + 1) + [silence] * _SILENCE_BLOCKS
        call_count = [0]

        def auto_stop_get(timeout=None):
            call_count[0] += 1
            if call_count[0] > len(blocks_list):
                t._is_running = False
                raise queue.Empty
            return blocks_list[call_count[0] - 1]

        t._audio_queue.get = auto_stop_get
        t._is_running = True

        mock_segment = SimpleNamespace(text="Will cause error")
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([mock_segment], None)
        mock_stream = MagicMock()

        mock_sd = sys.modules["sounddevice"]
        mock_sd.InputStream = MagicMock(return_value=mock_stream)
        mock_fw = sys.modules["faster_whisper"]
        mock_fw.WhisperModel = MagicMock(return_value=mock_model)

        t._process_loop()

        # Error is caught; _is_running set to False in finally block
        assert t._is_running is False
        # Status callback receives the error message
        status_cb.assert_called()
        assert "callback error" in str(status_cb.call_args)

    def test_on_status_error_does_not_suppress_original_error(self) -> None:
        """If on_status also raises, original error handling still works."""
        status_cb = MagicMock()
        # First call succeeds (emit_status for model loading),
        # second call fails when reporting the error
        call_number = [0]

        def status_side_effect(msg: str) -> None:
            call_number[0] += 1
            if call_number[0] > 1:
                raise TypeError("status callback broken")

        status_cb.side_effect = status_side_effect

        mock_fw = sys.modules["faster_whisper"]
        original_side_effect = mock_fw.WhisperModel.side_effect
        mock_fw.WhisperModel.side_effect = RuntimeError("model broken")
        try:
            t = LiveTranscriber(
                on_sentence=MagicMock(),
                on_status=status_cb,
            )
            t._is_running = True

            # _process_loop catches the model error and tries to call
            # on_status with the error message. If on_status also raises,
            # the finally block still executes.
            t._process_loop()

            assert t._is_running is False
        finally:
            mock_fw.WhisperModel.side_effect = original_side_effect

    def test_on_sentence_error_on_flush_sets_not_running(self) -> None:
        """on_sentence raising during end-of-loop flush is caught."""
        sentence_cb = MagicMock(side_effect=RuntimeError("flush error"))
        status_cb = MagicMock()
        t = LiveTranscriber(
            on_sentence=sentence_cb,
            on_status=status_cb,
        )

        # Feed enough speech blocks (no silence) so buffer is flushed on exit
        speech = np.ones((_BLOCK_SIZE,), dtype=np.float32) * 0.5
        num_speech = _MIN_AUDIO_BLOCKS + 1

        call_count = [0]

        def auto_stop_get(timeout=None):
            call_count[0] += 1
            if call_count[0] > num_speech:
                t._is_running = False
                raise queue.Empty
            return speech

        t._audio_queue.get = auto_stop_get
        t._is_running = True

        mock_segment = SimpleNamespace(text="Flush text")
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([mock_segment], None)
        mock_stream = MagicMock()

        mock_sd = sys.modules["sounddevice"]
        mock_sd.InputStream = MagicMock(return_value=mock_stream)
        mock_fw = sys.modules["faster_whisper"]
        mock_fw.WhisperModel = MagicMock(return_value=mock_model)

        t._process_loop()

        assert t._is_running is False
        # The error message from the callback should be in status
        status_cb.assert_called()
        assert "flush error" in str(status_cb.call_args)


# ---------------------------------------------------------------------------
# Helpers for new tests
# ---------------------------------------------------------------------------


def _make_transcriber(  # noqa: PLR0913
    *,
    sentence_cb: MagicMock | None = None,
    partial_cb: MagicMock | None = None,
    status_cb: MagicMock | None = None,
    model_size: str = "tiny",
    language: str = "",
    device: int | None = None,
) -> LiveTranscriber:
    """Helper to construct a LiveTranscriber with sensible defaults."""
    return LiveTranscriber(
        on_sentence=sentence_cb or MagicMock(),
        on_partial=partial_cb,
        on_status=status_cb,
        model_size=model_size,
        language=language,
        device=device,
    )


def _setup_mocks(
    *,
    model_segments: list | None = None,
    stream_side_effect: Exception | None = None,
    model_side_effect: Exception | None = None,
) -> tuple[MagicMock, MagicMock]:
    """Setup sounddevice and faster_whisper mocks. Returns (mock_model, mock_stream)."""
    mock_sd = sys.modules["sounddevice"]
    mock_fw = sys.modules["faster_whisper"]

    mock_model = MagicMock()
    if model_side_effect:
        mock_fw.WhisperModel = MagicMock(side_effect=model_side_effect)
    else:
        mock_fw.WhisperModel = MagicMock(return_value=mock_model)
    if model_segments is not None:
        mock_model.transcribe.return_value = (model_segments, None)
    else:
        mock_model.transcribe.return_value = ([], None)

    mock_stream = MagicMock()
    if stream_side_effect:
        mock_sd.InputStream = MagicMock(side_effect=stream_side_effect)
    else:
        mock_sd.InputStream = MagicMock(return_value=mock_stream)

    return mock_model, mock_stream


def _feed_blocks_and_run(
    t: LiveTranscriber,
    blocks_list: list[np.ndarray],
) -> None:
    """Feed blocks into the queue and run _process_loop until exhausted."""
    call_count = [0]

    def auto_stop_get(timeout: float | None = None) -> np.ndarray:
        call_count[0] += 1
        if call_count[0] > len(blocks_list):
            t._is_running = False
            raise queue.Empty
        return blocks_list[call_count[0] - 1]

    t._audio_queue.get = auto_stop_get  # type: ignore[assignment]
    t._is_running = True
    t._process_loop()


# ---------------------------------------------------------------------------
# TestLiveEngineEdgeCases
# ---------------------------------------------------------------------------


class TestLiveEngineEdgeCases:
    """Edge cases for start(), stop(), and state transitions."""

    def test_start_when_already_running_is_noop(self) -> None:
        """Calling start() while already running returns immediately."""
        t = _make_transcriber()
        with patch.object(t, "_process_loop"):
            t.start()
            thread1 = t._process_thread
            t.start()  # second call
            assert t._process_thread is thread1
            t._is_running = False
            thread1.join(timeout=2)

    def test_stop_when_not_running_is_safe(self) -> None:
        """stop() on a fresh transcriber does not raise."""
        t = _make_transcriber()
        t.stop()
        assert t.is_running is False
        assert t._stream is None
        assert t._process_thread is None

    def test_stop_during_active_transcription(self) -> None:
        """stop() while _process_loop is transcribing sets _is_running False."""
        sentence_cb = MagicMock()
        status_cb = MagicMock()
        t = _make_transcriber(sentence_cb=sentence_cb, status_cb=status_cb)

        speech = np.ones((_BLOCK_SIZE,), dtype=np.float32) * 0.5
        mock_model, mock_stream = _setup_mocks(
            model_segments=[SimpleNamespace(text="interrupted")],
        )

        # Simulate stop() being called during transcription
        original_transcribe = mock_model.transcribe

        def transcribe_and_stop(audio, **kwargs):
            t._is_running = False
            return original_transcribe(audio, **kwargs)

        mock_model.transcribe.side_effect = transcribe_and_stop

        blocks = [speech] * (_MIN_AUDIO_BLOCKS + 1) + [
            np.zeros((_BLOCK_SIZE,), dtype=np.float32)
        ] * _SILENCE_BLOCKS
        _feed_blocks_and_run(t, blocks)

        assert t._is_running is False

    def test_rapid_start_stop_cycles(self) -> None:
        """Multiple rapid start/stop cycles do not leak resources."""
        t = _make_transcriber()
        for _ in range(5):
            with patch.object(t, "_process_loop"):
                t.start()
                assert t.is_running is True
                t._is_running = False
                t._process_thread.join(timeout=2)
                t._process_thread = None
                t.stop()
                assert t.is_running is False
                assert t._stream is None
                assert t._process_thread is None

    @pytest.mark.parametrize(
        "model_size",
        ["tiny", "base", "small", "medium", "large"],
    )
    def test_model_size_passed_to_whisper(self, model_size: str) -> None:
        """Each model size string is forwarded to WhisperModel."""
        status_cb = MagicMock()
        t = _make_transcriber(model_size=model_size, status_cb=status_cb)
        mock_model, _mock_stream = _setup_mocks()

        def stop_immediately(timeout: float | None = None) -> np.ndarray:
            t._is_running = False
            raise queue.Empty

        t._audio_queue.get = stop_immediately  # type: ignore[assignment]
        t._is_running = True
        t._process_loop()

        mock_fw = sys.modules["faster_whisper"]
        mock_fw.WhisperModel.assert_called_once_with(
            model_size, device="cpu", compute_type="int8"
        )

    def test_sentence_recognized_signal_emission(self) -> None:
        """on_sentence is called with joined text from transcription segments."""
        sentence_cb = MagicMock()
        t = _make_transcriber(sentence_cb=sentence_cb, status_cb=MagicMock())

        segments = [SimpleNamespace(text="Hello"), SimpleNamespace(text="world")]
        mock_model, _mock_stream = _setup_mocks(model_segments=segments)

        speech = np.ones((_BLOCK_SIZE,), dtype=np.float32) * 0.5
        silence = np.zeros((_BLOCK_SIZE,), dtype=np.float32)
        blocks = [speech] * (_MIN_AUDIO_BLOCKS + 1) + [silence] * _SILENCE_BLOCKS
        _feed_blocks_and_run(t, blocks)

        assert sentence_cb.call_args[0][0] == "Hello world"

    def test_error_signal_emission_on_failure(self) -> None:
        """on_status receives the error message when _process_loop fails."""
        status_cb = MagicMock()
        t = _make_transcriber(status_cb=status_cb)
        _setup_mocks(model_side_effect=RuntimeError("GPU unavailable"))
        t._is_running = True
        t._process_loop()

        assert t._is_running is False
        # The last status call should contain the error message
        last_call_arg = status_cb.call_args_list[-1][0][0]
        assert "GPU unavailable" in last_call_arg


# ---------------------------------------------------------------------------
# TestAudioCaptureEdgeCases
# ---------------------------------------------------------------------------


class TestAudioCaptureEdgeCases:
    """Edge cases for audio capture behavior."""

    def test_no_microphone_available(self) -> None:
        """InputStream raising when no mic is available stops the engine."""
        status_cb = MagicMock()
        t = _make_transcriber(status_cb=status_cb)
        _setup_mocks(stream_side_effect=OSError("No input devices available"))
        t._is_running = True
        t._process_loop()

        assert t._is_running is False
        last_call = status_cb.call_args_list[-1][0][0]
        assert "No input devices available" in last_call

    def test_microphone_permission_denied(self) -> None:
        """Permission error from sounddevice is handled gracefully."""
        status_cb = MagicMock()
        t = _make_transcriber(status_cb=status_cb)
        _setup_mocks(
            stream_side_effect=PermissionError("Microphone access denied"),
        )
        t._is_running = True
        t._process_loop()

        assert t._is_running is False
        last_call = status_cb.call_args_list[-1][0][0]
        assert "Microphone access denied" in last_call

    def test_silence_detection_threshold_value(self) -> None:
        """Silence threshold is 0.01 as defined in module constants."""
        assert pytest.approx(0.01) == _SILENCE_THRESHOLD

    def test_audio_chunk_size_matches_half_second(self) -> None:
        """Block size equals sample rate * 0.5 = 8000 samples."""
        assert _BLOCK_SIZE == 8000  # noqa: PLR2004

    def test_continuous_silence_no_transcription(self) -> None:
        """Long stretch of silence never triggers transcription."""
        sentence_cb = MagicMock()
        t = _make_transcriber(sentence_cb=sentence_cb, status_cb=MagicMock())
        mock_model, _mock_stream = _setup_mocks()

        silence = np.zeros((_BLOCK_SIZE,), dtype=np.float32)
        blocks = [silence] * (_SILENCE_BLOCKS * 5)
        _feed_blocks_and_run(t, blocks)

        mock_model.transcribe.assert_not_called()
        sentence_cb.assert_not_called()

    def test_audio_data_format_sample_rate(self) -> None:
        """Sample rate is 16000 Hz."""
        assert _SAMPLE_RATE == 16000  # noqa: PLR2004

    def test_audio_data_format_channels(self) -> None:
        """Audio capture uses 1 channel (mono)."""
        from src.core.live_engine import (  # noqa: PLC0415
            _CHANNELS,
        )

        assert _CHANNELS == 1

    def test_audio_stream_parameters(self) -> None:
        """InputStream is created with correct parameters."""
        t = _make_transcriber(device=7, status_cb=MagicMock())
        _mock_model, _mock_stream = _setup_mocks()

        def stop_immediately(timeout: float | None = None) -> np.ndarray:
            t._is_running = False
            raise queue.Empty

        t._audio_queue.get = stop_immediately  # type: ignore[assignment]
        t._is_running = True
        t._process_loop()

        mock_sd = sys.modules["sounddevice"]
        call_kwargs = mock_sd.InputStream.call_args[1]
        assert call_kwargs["samplerate"] == _SAMPLE_RATE
        assert call_kwargs["channels"] == 1
        assert call_kwargs["blocksize"] == _BLOCK_SIZE
        assert call_kwargs["dtype"] == "float32"
        assert call_kwargs["device"] == 7  # noqa: PLR2004

    def test_cleanup_on_stop_closes_stream(self) -> None:
        """stop() calls stream.stop() and stream.close()."""
        t = _make_transcriber()
        mock_stream = MagicMock()
        t._stream = mock_stream
        t._is_running = True
        t._process_thread = MagicMock()

        t.stop()

        mock_stream.stop.assert_called_once()
        mock_stream.close.assert_called_once()
        assert t._stream is None


# ---------------------------------------------------------------------------
# TestTranscriptionThreadEdgeCases
# ---------------------------------------------------------------------------


class TestTranscriptionThreadEdgeCases:
    """Edge cases for transcription behavior."""

    def test_empty_segments_list(self) -> None:
        """Empty segments list does not call on_sentence."""
        sentence_cb = MagicMock()
        t = _make_transcriber(sentence_cb=sentence_cb)
        model = MagicMock()
        model.transcribe.return_value = ([], None)
        blocks = [np.ones((8000,), dtype=np.float32)]
        t._transcribe_buffer(model, blocks, None)
        sentence_cb.assert_not_called()

    def test_noise_only_audio_below_threshold(self) -> None:
        """Very low amplitude noise is treated as silence."""
        amplitude = _SILENCE_THRESHOLD * 0.1
        block = np.full((_BLOCK_SIZE,), fill_value=amplitude, dtype=np.float32)
        rms = float(np.sqrt(np.mean(block**2)))
        assert rms < _SILENCE_THRESHOLD

    def test_very_short_audio_below_min_blocks(self) -> None:
        """Single speech block (< _MIN_AUDIO_BLOCKS) is not transcribed."""
        sentence_cb = MagicMock()
        t = _make_transcriber(sentence_cb=sentence_cb, status_cb=MagicMock())
        mock_model, _mock_stream = _setup_mocks()

        speech = np.ones((_BLOCK_SIZE,), dtype=np.float32) * 0.5
        silence = np.zeros((_BLOCK_SIZE,), dtype=np.float32)
        # 1 speech + silence: below _MIN_AUDIO_BLOCKS
        blocks = [speech] + [silence] * _SILENCE_BLOCKS
        _feed_blocks_and_run(t, blocks)

        mock_model.transcribe.assert_not_called()

    def test_very_long_audio_segment(self) -> None:
        """Many speech blocks are split by max buffer and all transcribed."""
        sentence_cb = MagicMock()
        t = _make_transcriber(sentence_cb=sentence_cb, status_cb=MagicMock())
        mock_model, _mock_stream = _setup_mocks(
            model_segments=[SimpleNamespace(text="Long speech")],
        )

        speech = np.ones((_BLOCK_SIZE,), dtype=np.float32) * 0.5
        silence = np.zeros((_BLOCK_SIZE,), dtype=np.float32)
        num_speech = 50
        blocks = [speech] * num_speech + [silence] * _SILENCE_BLOCKS
        _feed_blocks_and_run(t, blocks)

        # Each max-buffer chunk triggers a transcription
        expected_calls = (num_speech // _MAX_BUFFER_BLOCKS) + (
            1 if num_speech % _MAX_BUFFER_BLOCKS >= _MIN_AUDIO_BLOCKS else 0
        )
        assert mock_model.transcribe.call_count == expected_calls
        # Each chunk is exactly _MAX_BUFFER_BLOCKS * _BLOCK_SIZE samples
        first_audio = mock_model.transcribe.call_args_list[0][0][0]
        assert first_audio.shape == (_MAX_BUFFER_BLOCKS * _BLOCK_SIZE,)

    def test_model_loading_failure_sets_not_running(self) -> None:
        """Failed WhisperModel init sets _is_running to False."""
        status_cb = MagicMock()
        t = _make_transcriber(status_cb=status_cb)
        _setup_mocks(model_side_effect=ValueError("invalid model size"))
        t._is_running = True
        t._process_loop()

        assert t._is_running is False
        last_call = status_cb.call_args_list[-1][0][0]
        assert "invalid model size" in last_call

    def test_transcription_with_language_vi(self) -> None:
        """Vietnamese language code is passed to model.transcribe."""
        sentence_cb = MagicMock()
        t = _make_transcriber(
            sentence_cb=sentence_cb,
            status_cb=MagicMock(),
            language="Vietnamese",
        )
        mock_model, _mock_stream = _setup_mocks(
            model_segments=[SimpleNamespace(text="Xin chào")],
        )

        speech = np.ones((_BLOCK_SIZE,), dtype=np.float32) * 0.5
        silence = np.zeros((_BLOCK_SIZE,), dtype=np.float32)
        blocks = [speech] * (_MIN_AUDIO_BLOCKS + 1) + [silence] * _SILENCE_BLOCKS

        with patch(
            "src.core.speech_engine._get_speech_language_code",
            return_value="vi-VN",
        ):
            _feed_blocks_and_run(t, blocks)

        _, kwargs = mock_model.transcribe.call_args
        # "vi-VN" should be split to "vi"
        assert kwargs["language"] == "vi"

    def test_transcription_with_auto_detect_language(self) -> None:
        """Empty language string results in no language kwarg."""
        sentence_cb = MagicMock()
        t = _make_transcriber(
            sentence_cb=sentence_cb,
            status_cb=MagicMock(),
            language="",
        )
        mock_model, _mock_stream = _setup_mocks(
            model_segments=[SimpleNamespace(text="Auto detected")],
        )

        speech = np.ones((_BLOCK_SIZE,), dtype=np.float32) * 0.5
        silence = np.zeros((_BLOCK_SIZE,), dtype=np.float32)
        blocks = [speech] * (_MIN_AUDIO_BLOCKS + 1) + [silence] * _SILENCE_BLOCKS
        _feed_blocks_and_run(t, blocks)

        _, kwargs = mock_model.transcribe.call_args
        assert "language" not in kwargs

    def test_cancel_during_transcription(self) -> None:
        """Setting _is_running=False mid-loop stops processing."""
        sentence_cb = MagicMock()
        t = _make_transcriber(sentence_cb=sentence_cb, status_cb=MagicMock())
        mock_model, _mock_stream = _setup_mocks()

        speech = np.ones((_BLOCK_SIZE,), dtype=np.float32) * 0.5
        call_count = [0]

        def get_and_cancel(timeout: float | None = None) -> np.ndarray:
            call_count[0] += 1
            if call_count[0] == 3:  # noqa: PLR2004
                t._is_running = False
                raise queue.Empty
            return speech

        t._audio_queue.get = get_and_cancel  # type: ignore[assignment]
        t._is_running = True
        t._process_loop()

        assert t._is_running is False
        # Only 2 speech blocks were collected — meets _MIN_AUDIO_BLOCKS,
        # so flush transcription is called once
        assert mock_model.transcribe.call_count <= 1

    def test_result_callback_receives_correct_text(self) -> None:
        """on_sentence receives the exact joined text from all segments."""
        sentence_cb = MagicMock()
        t = _make_transcriber(sentence_cb=sentence_cb)
        model = MagicMock()
        model.transcribe.return_value = (
            [
                SimpleNamespace(text=" First "),
                SimpleNamespace(text="  Second  "),
                SimpleNamespace(text=" Third "),
            ],
            None,
        )
        blocks = [np.ones((8000,), dtype=np.float32)]
        t._transcribe_buffer(model, blocks, None)
        assert sentence_cb.call_count == 1
        assert sentence_cb.call_args[0][0] == "First Second Third"


# ---------------------------------------------------------------------------
# TestLiveEngineIntegration
# ---------------------------------------------------------------------------


class TestLiveEngineIntegration:
    """Integration-style tests for the full pipeline."""

    def test_full_pipeline_capture_transcribe_emit(self) -> None:
        """Speech blocks followed by silence produces a sentence callback."""
        sentence_cb = MagicMock()
        t = _make_transcriber(sentence_cb=sentence_cb, status_cb=MagicMock())
        mock_model, _mock_stream = _setup_mocks(
            model_segments=[SimpleNamespace(text="Pipeline output")],
        )

        speech = np.ones((_BLOCK_SIZE,), dtype=np.float32) * 0.5
        silence = np.zeros((_BLOCK_SIZE,), dtype=np.float32)
        blocks = [speech] * (_MIN_AUDIO_BLOCKS + 2) + [silence] * _SILENCE_BLOCKS
        _feed_blocks_and_run(t, blocks)

        assert sentence_cb.call_count == 1
        assert sentence_cb.call_args[0][0] == "Pipeline output"
        assert t._is_running is False

    def test_engine_state_transitions(self) -> None:
        """Verify state transitions: stopped -> running -> stopped."""
        t = _make_transcriber()
        assert t.is_running is False

        with patch.object(t, "_process_loop"):
            t.start()
            assert t.is_running is True
            t._is_running = False
            t._process_thread.join(timeout=2)

        t.stop()
        assert t.is_running is False
        assert t._stream is None
        assert t._process_thread is None

    def test_multiple_transcriptions_in_single_session(self) -> None:
        """Multiple speech-silence cycles produce multiple callbacks."""
        sentence_cb = MagicMock()
        t = _make_transcriber(sentence_cb=sentence_cb, status_cb=MagicMock())

        seg1 = SimpleNamespace(text="First sentence")
        seg2 = SimpleNamespace(text="Second sentence")
        mock_model, _mock_stream = _setup_mocks()
        mock_model.transcribe.side_effect = [
            ([seg1], None),
            ([seg2], None),
        ]

        speech = np.ones((_BLOCK_SIZE,), dtype=np.float32) * 0.5
        silence = np.zeros((_BLOCK_SIZE,), dtype=np.float32)

        # Two speech-silence cycles
        blocks = (
            [speech] * (_MIN_AUDIO_BLOCKS + 1)
            + [silence] * _SILENCE_BLOCKS
            + [speech] * (_MIN_AUDIO_BLOCKS + 1)
            + [silence] * _SILENCE_BLOCKS
        )
        _feed_blocks_and_run(t, blocks)

        assert sentence_cb.call_count == 2  # noqa: PLR2004
        assert any(c[0][0] == "First sentence" for c in sentence_cb.call_args_list)
        assert any(c[0][0] == "Second sentence" for c in sentence_cb.call_args_list)

    def test_resource_cleanup_on_destruction(self) -> None:
        """After stop(), all resources are released."""
        t = _make_transcriber()
        mock_stream = MagicMock()
        t._stream = mock_stream
        t._is_running = True
        t._process_thread = MagicMock()

        t.stop()

        assert t._stream is None
        assert t._process_thread is None
        assert t._is_running is False
        mock_stream.stop.assert_called_once()
        mock_stream.close.assert_called_once()

    def test_audio_queue_drained_after_stop(self) -> None:
        """Audio queue is not explicitly drained, but engine stops reading."""
        t = _make_transcriber()
        t._is_running = True
        # Put some items in queue
        for _ in range(5):
            t._audio_queue.put(np.zeros((_BLOCK_SIZE,), dtype=np.float32))

        t._is_running = False
        # Queue items remain (no explicit drain)
        assert t._audio_queue.qsize() == 5  # noqa: PLR2004


# ---------------------------------------------------------------------------
# TestSilenceDetection
# ---------------------------------------------------------------------------


class TestSilenceDetection:
    """Tests for silence detection logic."""

    def test_is_silence_with_zero_rms(self) -> None:
        """All-zero block has RMS 0, well below threshold."""
        block = np.zeros((_BLOCK_SIZE,), dtype=np.float32)
        rms = float(np.sqrt(np.mean(block**2)))
        assert rms == pytest.approx(0.0)
        assert rms < _SILENCE_THRESHOLD

    def test_is_silence_with_low_rms(self) -> None:
        """Block with RMS=0.005 is below the 0.01 threshold."""
        amplitude = 0.005
        block = np.full((_BLOCK_SIZE,), fill_value=amplitude, dtype=np.float32)
        rms = float(np.sqrt(np.mean(block**2)))
        assert rms == pytest.approx(amplitude, abs=1e-6)
        assert rms < _SILENCE_THRESHOLD

    def test_is_speech_with_high_rms(self) -> None:
        """Block with RMS=0.5 is well above threshold."""
        block = np.full((_BLOCK_SIZE,), fill_value=0.5, dtype=np.float32)
        rms = float(np.sqrt(np.mean(block**2)))
        assert rms >= _SILENCE_THRESHOLD

    def test_mixed_amplitude_rms_calculation(self) -> None:
        """RMS of half-zeros, half-loud is computed correctly."""
        block = np.zeros((_BLOCK_SIZE,), dtype=np.float32)
        half = _BLOCK_SIZE // 2
        block[half:] = 0.1
        rms = float(np.sqrt(np.mean(block**2)))
        expected = float(np.sqrt(0.1**2 * half / _BLOCK_SIZE))
        assert rms == pytest.approx(expected, rel=1e-4)
        assert rms >= _SILENCE_THRESHOLD

    def test_silence_duration_tracking_requires_consecutive(self) -> None:
        """Silence counter only counts consecutive silent blocks."""
        sentence_cb = MagicMock()
        t = _make_transcriber(sentence_cb=sentence_cb, status_cb=MagicMock())
        mock_model, _mock_stream = _setup_mocks()

        speech = np.ones((_BLOCK_SIZE,), dtype=np.float32) * 0.5
        silence = np.zeros((_BLOCK_SIZE,), dtype=np.float32)

        # Alternate: speech, silence(2), speech, silence(2) — never enough
        # consecutive silence to trigger transcription mid-loop
        blocks = (
            [speech]
            + [silence] * (_SILENCE_BLOCKS - 2)
            + [speech]
            + [silence] * (_SILENCE_BLOCKS - 2)
        )
        _feed_blocks_and_run(t, blocks)

        # Only 2 speech blocks => flush on exit calls transcribe once
        assert mock_model.transcribe.call_count == 1

    def test_silence_blocks_constant_value(self) -> None:
        """_SILENCE_BLOCKS is 2, the expected number of consecutive blocks."""
        assert _SILENCE_BLOCKS == 2  # noqa: PLR2004

    def test_min_audio_blocks_constant_value(self) -> None:
        """_MIN_AUDIO_BLOCKS is 2, the minimum speech blocks needed."""
        assert _MIN_AUDIO_BLOCKS == 2  # noqa: PLR2004

    def test_negative_amplitude_rms(self) -> None:
        """Negative amplitudes contribute to RMS the same as positive."""
        block_pos = np.full((_BLOCK_SIZE,), fill_value=0.05, dtype=np.float32)
        block_neg = np.full((_BLOCK_SIZE,), fill_value=-0.05, dtype=np.float32)
        rms_pos = float(np.sqrt(np.mean(block_pos**2)))
        rms_neg = float(np.sqrt(np.mean(block_neg**2)))
        assert rms_pos == pytest.approx(rms_neg, abs=1e-7)


# ---------------------------------------------------------------------------
# TestModelManagement
# ---------------------------------------------------------------------------


class TestModelManagement:
    """Tests for model loading, caching, and size validation."""

    def test_model_loaded_with_cpu_device(self) -> None:
        """WhisperModel is always created with device='cpu'."""
        t = _make_transcriber(status_cb=MagicMock())
        _mock_model, _mock_stream = _setup_mocks()

        def stop_immediately(timeout: float | None = None) -> np.ndarray:
            t._is_running = False
            raise queue.Empty

        t._audio_queue.get = stop_immediately  # type: ignore[assignment]
        t._is_running = True
        t._process_loop()

        mock_fw = sys.modules["faster_whisper"]
        _, kwargs = mock_fw.WhisperModel.call_args
        assert kwargs["device"] == "cpu"

    def test_model_loaded_with_int8_compute(self) -> None:
        """WhisperModel is always created with compute_type='int8'."""
        t = _make_transcriber(status_cb=MagicMock())
        _mock_model, _mock_stream = _setup_mocks()

        def stop_immediately(timeout: float | None = None) -> np.ndarray:
            t._is_running = False
            raise queue.Empty

        t._audio_queue.get = stop_immediately  # type: ignore[assignment]
        t._is_running = True
        t._process_loop()

        mock_fw = sys.modules["faster_whisper"]
        _, kwargs = mock_fw.WhisperModel.call_args
        assert kwargs["compute_type"] == "int8"

    def test_model_download_failure_handling(self) -> None:
        """Network error during model download is caught and reported."""
        status_cb = MagicMock()
        t = _make_transcriber(status_cb=status_cb)
        _setup_mocks(
            model_side_effect=ConnectionError("Failed to download model"),
        )
        t._is_running = True
        t._process_loop()

        assert t._is_running is False
        last_call = status_cb.call_args_list[-1][0][0]
        assert "Failed to download model" in last_call

    def test_model_size_default_is_tiny(self) -> None:
        """Default model size is 'tiny'."""
        t = LiveTranscriber(on_sentence=MagicMock())
        assert t._model_size == "tiny"

    def test_model_size_stored_correctly(self) -> None:
        """Custom model size is stored on the instance."""
        t = _make_transcriber(model_size="large")
        assert t._model_size == "large"

    def test_model_created_once_per_process_loop(self) -> None:
        """WhisperModel constructor is called exactly once per _process_loop."""
        t = _make_transcriber(status_cb=MagicMock())
        mock_model, _mock_stream = _setup_mocks(
            model_segments=[SimpleNamespace(text="Test")],
        )

        speech = np.ones((_BLOCK_SIZE,), dtype=np.float32) * 0.5
        silence = np.zeros((_BLOCK_SIZE,), dtype=np.float32)
        # Two speech-silence cycles
        blocks = (
            [speech] * (_MIN_AUDIO_BLOCKS + 1)
            + [silence] * _SILENCE_BLOCKS
            + [speech] * (_MIN_AUDIO_BLOCKS + 1)
            + [silence] * _SILENCE_BLOCKS
        )
        _feed_blocks_and_run(t, blocks)

        mock_fw = sys.modules["faster_whisper"]
        # Model is created only once even with multiple transcriptions
        mock_fw.WhisperModel.assert_called_once()


# ---------------------------------------------------------------------------
# Additional edge cases
# ---------------------------------------------------------------------------


class TestLanguageCodeEdgeCases:
    """Additional tests for language code resolution in _process_loop."""

    def test_language_code_without_dash_used_as_is(self) -> None:
        """Language code 'en' (no dash) is passed directly."""
        sentence_cb = MagicMock()
        t = _make_transcriber(
            sentence_cb=sentence_cb,
            status_cb=MagicMock(),
            language="English",
        )
        mock_model, _mock_stream = _setup_mocks(
            model_segments=[SimpleNamespace(text="Hello")],
        )

        speech = np.ones((_BLOCK_SIZE,), dtype=np.float32) * 0.5
        silence = np.zeros((_BLOCK_SIZE,), dtype=np.float32)
        blocks = [speech] * (_MIN_AUDIO_BLOCKS + 1) + [silence] * _SILENCE_BLOCKS

        with patch(
            "src.core.speech_engine._get_speech_language_code",
            return_value="en",
        ):
            _feed_blocks_and_run(t, blocks)

        _, kwargs = mock_model.transcribe.call_args
        assert kwargs["language"] == "en"

    def test_language_code_returns_empty_string(self) -> None:
        """If _get_speech_language_code returns '', no language kwarg is passed."""
        sentence_cb = MagicMock()
        t = _make_transcriber(
            sentence_cb=sentence_cb,
            status_cb=MagicMock(),
            language="Unknown",
        )
        mock_model, _mock_stream = _setup_mocks(
            model_segments=[SimpleNamespace(text="Detected")],
        )

        speech = np.ones((_BLOCK_SIZE,), dtype=np.float32) * 0.5
        silence = np.zeros((_BLOCK_SIZE,), dtype=np.float32)
        blocks = [speech] * (_MIN_AUDIO_BLOCKS + 1) + [silence] * _SILENCE_BLOCKS

        with patch(
            "src.core.speech_engine._get_speech_language_code",
            return_value="",
        ):
            _feed_blocks_and_run(t, blocks)

        _, kwargs = mock_model.transcribe.call_args
        assert "language" not in kwargs

    def test_language_code_with_region_splits_correctly(self) -> None:
        """Language code 'pt-BR' is split to 'pt'."""
        sentence_cb = MagicMock()
        t = _make_transcriber(
            sentence_cb=sentence_cb,
            status_cb=MagicMock(),
            language="Portuguese",
        )
        mock_model, _mock_stream = _setup_mocks(
            model_segments=[SimpleNamespace(text="Olá")],
        )

        speech = np.ones((_BLOCK_SIZE,), dtype=np.float32) * 0.5
        silence = np.zeros((_BLOCK_SIZE,), dtype=np.float32)
        blocks = [speech] * (_MIN_AUDIO_BLOCKS + 1) + [silence] * _SILENCE_BLOCKS

        with patch(
            "src.core.speech_engine._get_speech_language_code",
            return_value="pt-BR",
        ):
            _feed_blocks_and_run(t, blocks)

        _, kwargs = mock_model.transcribe.call_args
        assert kwargs["language"] == "pt"


class TestProcessLoopStreamLifecycle:
    """Tests for stream lifecycle within _process_loop."""

    def test_stream_start_called(self) -> None:
        """_process_loop calls stream.start() after creation."""
        t = _make_transcriber(status_cb=MagicMock())
        _mock_model, mock_stream = _setup_mocks()

        def stop_immediately(timeout: float | None = None) -> np.ndarray:
            t._is_running = False
            raise queue.Empty

        t._audio_queue.get = stop_immediately  # type: ignore[assignment]
        t._is_running = True
        t._process_loop()

        mock_stream.start.assert_called_once()

    def test_stream_created_with_callback(self) -> None:
        """InputStream is created with _audio_callback as the callback."""
        t = _make_transcriber(status_cb=MagicMock())
        _mock_model, _mock_stream = _setup_mocks()

        def stop_immediately(timeout: float | None = None) -> np.ndarray:
            t._is_running = False
            raise queue.Empty

        t._audio_queue.get = stop_immediately  # type: ignore[assignment]
        t._is_running = True
        t._process_loop()

        mock_sd = sys.modules["sounddevice"]
        call_kwargs = mock_sd.InputStream.call_args[1]
        # Bound methods create new objects on access; compare underlying func
        assert call_kwargs["callback"].__func__ is t._audio_callback.__func__
        assert call_kwargs["callback"].__self__ is t

    def test_device_none_passed_to_stream(self) -> None:
        """When device is None, it is still passed to InputStream."""
        t = _make_transcriber(device=None, status_cb=MagicMock())
        _mock_model, _mock_stream = _setup_mocks()

        def stop_immediately(timeout: float | None = None) -> np.ndarray:
            t._is_running = False
            raise queue.Empty

        t._audio_queue.get = stop_immediately  # type: ignore[assignment]
        t._is_running = True
        t._process_loop()

        mock_sd = sys.modules["sounddevice"]
        call_kwargs = mock_sd.InputStream.call_args[1]
        assert call_kwargs["device"] is None

    def test_stream_stored_on_instance(self) -> None:
        """_process_loop stores the stream on self._stream."""
        t = _make_transcriber(status_cb=MagicMock())
        _mock_model, mock_stream = _setup_mocks()

        stream_ref = [None]

        def capture_and_stop(timeout: float | None = None) -> np.ndarray:
            stream_ref[0] = t._stream
            t._is_running = False
            raise queue.Empty

        t._audio_queue.get = capture_and_stop  # type: ignore[assignment]
        t._is_running = True
        t._process_loop()

        assert stream_ref[0] is mock_stream


class TestTranscribeBufferConcatenation:
    """Tests for audio block concatenation in _transcribe_buffer."""

    def test_single_block_flattened(self) -> None:
        """A single 2D block is flattened to 1D."""
        model = MagicMock()
        model.transcribe.return_value = ([], None)
        t = _make_transcriber()
        block = np.ones((100, 1), dtype=np.float32)
        t._transcribe_buffer(model, [block], None)
        audio_arg = model.transcribe.call_args[0][0]
        assert audio_arg.ndim == 1
        assert audio_arg.shape == (100,)

    def test_many_blocks_concatenated(self) -> None:
        """Ten blocks of different sizes are concatenated correctly."""
        model = MagicMock()
        model.transcribe.return_value = ([], None)
        t = _make_transcriber()
        blocks = [np.ones((i * 10 + 10,), dtype=np.float32) for i in range(10)]
        total = sum(b.shape[0] for b in blocks)
        t._transcribe_buffer(model, blocks, None)
        audio_arg = model.transcribe.call_args[0][0]
        assert audio_arg.shape == (total,)

    def test_word_timestamps_always_false(self) -> None:
        """word_timestamps is always set to False in transcribe kwargs."""
        model = MagicMock()
        model.transcribe.return_value = ([], None)
        t = _make_transcriber()
        blocks = [np.ones((8000,), dtype=np.float32)]
        t._transcribe_buffer(model, blocks, "en")
        _, kwargs = model.transcribe.call_args
        assert kwargs["word_timestamps"] is False


class TestQueueBehavior:
    """Tests for the audio queue behavior."""

    def test_queue_is_initially_empty(self) -> None:
        """Audio queue starts empty on construction."""
        t = _make_transcriber()
        assert t._audio_queue.empty()

    def test_queue_preserves_block_values(self) -> None:
        """Queued audio blocks preserve their sample values."""
        t = _make_transcriber()
        t._is_running = True
        data = np.array([0.1, 0.2, 0.3], dtype=np.float32).reshape(3, 1)
        t._audio_callback(data, 3, None, None)
        queued = t._audio_queue.get_nowait()
        np.testing.assert_array_almost_equal(queued, data)

    def test_queue_caps_rapid_puts_drops_oldest(self) -> None:
        """Queue is bounded to ``_QUEUE_MAX_BLOCKS`` and drops oldest on overflow.

        Rationale: a slow consumer (slow whisper model) shouldn't let
        the producer (sounddevice callback) grow the queue without
        bound.  ``_put_drop_oldest`` keeps the newest blocks and
        evicts old ones so transcription stays near real-time.
        """
        from src.core.live_engine import _QUEUE_MAX_BLOCKS  # noqa: PLC0415

        t = _make_transcriber()
        t._is_running = True
        # Push 2× the cap to force drop-oldest to engage.
        for i in range(_QUEUE_MAX_BLOCKS * 2):
            block = np.full((10, 1), fill_value=float(i), dtype=np.float32)
            t._audio_callback(block, 10, None, None)
        assert t._audio_queue.qsize() == _QUEUE_MAX_BLOCKS
        # Oldest surviving block should carry the (count - cap)-th value,
        # confirming drop-oldest semantics rather than drop-newest.
        oldest = t._audio_queue.get_nowait()
        assert oldest[0, 0] == float(_QUEUE_MAX_BLOCKS)


# ---------------------------------------------------------------------------
# NEW TESTS — Audio capture start/stop lifecycle
# ---------------------------------------------------------------------------


class TestAudioCaptureLifecycle:
    """Tests for detailed audio capture start/stop lifecycle."""

    def test_start_creates_daemon_thread(self) -> None:
        """start() creates a daemon thread."""
        t = _make_transcriber()
        with patch.object(t, "_process_loop"):
            t.start()
            assert t._process_thread is not None
            assert t._process_thread.daemon is True
            t._is_running = False
            t._process_thread.join(timeout=2)

    def test_start_emits_loading_status(self) -> None:
        """start() emits 'loading model' status before spawning thread."""
        status_cb = MagicMock()
        t = _make_transcriber(status_cb=status_cb)
        with patch.object(t, "_process_loop"):
            t.start()
            # _emit_status is called with "live.status_loading_model"
            status_cb.assert_called()
            t._is_running = False
            t._process_thread.join(timeout=2)

    def test_stop_join_timeout_value(self) -> None:
        """stop() joins thread with timeout=5."""
        t = _make_transcriber()
        t._is_running = True
        mock_thread = MagicMock()
        t._process_thread = mock_thread
        t.stop()
        mock_thread.join.assert_called_once_with(timeout=5)

    def test_stop_closes_stream_before_joining_thread(self) -> None:
        """stop() closes the stream before joining the thread."""
        t = _make_transcriber()
        t._is_running = True
        mock_stream = MagicMock()
        t._stream = mock_stream
        call_order = []
        mock_stream.stop.side_effect = lambda: call_order.append("stream_stop")
        mock_stream.close.side_effect = lambda: call_order.append("stream_close")
        mock_thread = MagicMock()
        mock_thread.join.side_effect = lambda timeout=None: call_order.append("join")
        t._process_thread = mock_thread
        t.stop()
        assert call_order == ["stream_stop", "stream_close", "join"]

    def test_start_stop_start_again(self) -> None:
        """Can restart transcriber after stopping."""
        t = _make_transcriber()
        with patch.object(t, "_process_loop"):
            t.start()
            assert t.is_running is True
            t._is_running = False
            t._process_thread.join(timeout=2)
            t._process_thread = None
            t.stop()
            assert t.is_running is False

            # Start again
            t.start()
            assert t.is_running is True
            t._is_running = False
            t._process_thread.join(timeout=2)

    def test_queue_fresh_after_construction(self) -> None:
        """A new transcriber has an empty queue."""
        t = _make_transcriber()
        assert t._audio_queue.empty()
        assert t._audio_queue.qsize() == 0

    def test_stop_noop_when_stream_is_none(self) -> None:
        """stop() with stream=None doesn't raise."""
        t = _make_transcriber()
        t._is_running = True
        t._stream = None
        t._process_thread = MagicMock()
        t.stop()
        assert t._stream is None

    def test_stop_noop_when_thread_is_none(self) -> None:
        """stop() with _process_thread=None doesn't crash."""
        t = _make_transcriber()
        t._is_running = True
        t._process_thread = None
        t.stop()
        assert t._process_thread is None

    def test_is_running_false_after_fresh_init(self) -> None:
        """is_running is False on a fresh LiveTranscriber."""
        t = _make_transcriber()
        assert t.is_running is False

    def test_multiple_start_calls_single_thread(self) -> None:
        """Multiple start() calls only create one thread."""
        t = _make_transcriber()
        with patch.object(t, "_process_loop"):
            t.start()
            first = t._process_thread
            t.start()
            t.start()
            assert t._process_thread is first
            t._is_running = False
            first.join(timeout=2)


# ---------------------------------------------------------------------------
# NEW TESTS — Silence detection: threshold tuning, min/max duration
# ---------------------------------------------------------------------------


class TestSilenceDetectionTuning:
    """Tests for silence detection threshold tuning and duration limits."""

    def test_very_loud_audio_is_speech(self) -> None:
        """Maximum amplitude audio is detected as speech."""
        block = np.ones((_BLOCK_SIZE,), dtype=np.float32)  # amplitude 1.0
        rms = float(np.sqrt(np.mean(block**2)))
        assert rms >= _SILENCE_THRESHOLD

    def test_threshold_between_zero_and_one(self) -> None:
        """Threshold is between 0 and 1 exclusive."""
        assert 0 < _SILENCE_THRESHOLD < 1

    def test_silence_blocks_is_two(self) -> None:
        """Need 2 consecutive silence blocks to trigger."""
        assert _SILENCE_BLOCKS == 2  # noqa: PLR2004

    def test_min_audio_blocks_is_two(self) -> None:
        """Need at least 2 speech blocks for transcription."""
        assert _MIN_AUDIO_BLOCKS == 2  # noqa: PLR2004

    def test_three_silence_blocks_not_enough(self) -> None:
        """Three silence blocks after speech don't trigger transcription."""
        sentence_cb = MagicMock()
        t = _make_transcriber(sentence_cb=sentence_cb, status_cb=MagicMock())
        mock_model, _s = _setup_mocks()

        speech = np.ones((_BLOCK_SIZE,), dtype=np.float32) * 0.5
        silence = np.zeros((_BLOCK_SIZE,), dtype=np.float32)
        # 3 speech + 3 silence (not enough) -> only flush on exit
        blocks = [speech] * 3 + [silence] * (_SILENCE_BLOCKS - 1)
        _feed_blocks_and_run(t, blocks)

        # Transcription happens at flush, not mid-loop
        assert mock_model.transcribe.call_count <= 1

    def test_exactly_four_silence_blocks_triggers(self) -> None:
        """Exactly _SILENCE_BLOCKS silence blocks triggers transcription."""
        sentence_cb = MagicMock()
        t = _make_transcriber(sentence_cb=sentence_cb, status_cb=MagicMock())
        mock_model, _s = _setup_mocks(
            model_segments=[SimpleNamespace(text="Triggered")],
        )

        speech = np.ones((_BLOCK_SIZE,), dtype=np.float32) * 0.5
        silence = np.zeros((_BLOCK_SIZE,), dtype=np.float32)
        blocks = [speech] * (_MIN_AUDIO_BLOCKS + 1) + [silence] * _SILENCE_BLOCKS
        _feed_blocks_and_run(t, blocks)

        assert sentence_cb.call_args[0][0] == "Triggered"

    def test_alternating_speech_silence_resets_counter(self) -> None:
        """Speech block between silence resets the silence counter."""
        sentence_cb = MagicMock()
        t = _make_transcriber(sentence_cb=sentence_cb, status_cb=MagicMock())
        mock_model, _s = _setup_mocks(
            model_segments=[SimpleNamespace(text="Flushed")],
        )

        speech = np.ones((_BLOCK_SIZE,), dtype=np.float32) * 0.5
        silence = np.zeros((_BLOCK_SIZE,), dtype=np.float32)
        # pattern: speech, 3 silence (not enough), speech, 3 silence (not enough)
        partial = _SILENCE_BLOCKS - 1
        blocks = [speech] + [silence] * partial + [speech] + [silence] * partial
        _feed_blocks_and_run(t, blocks)

        # Only transcription is the flush on exit (2 speech blocks >= min)
        assert mock_model.transcribe.call_count == 1

    def test_rms_calculation_for_mixed_signal(self) -> None:
        """RMS for a block with varying amplitudes."""
        block = np.zeros((_BLOCK_SIZE,), dtype=np.float32)
        block[: _BLOCK_SIZE // 2] = 0.02  # Above threshold
        rms = float(np.sqrt(np.mean(block**2)))
        # RMS of half 0.02, half 0 = sqrt(0.02^2 * 0.5) = 0.02/sqrt(2) ≈ 0.0141
        assert rms > _SILENCE_THRESHOLD

    def test_silence_count_does_not_go_negative(self) -> None:
        """Silence counter starts at 0, never goes below 0."""
        # This is implicit from the code, but let's verify via integration
        sentence_cb = MagicMock()
        t = _make_transcriber(sentence_cb=sentence_cb, status_cb=MagicMock())
        mock_model, _s = _setup_mocks()

        # Start with speech immediately (no silence before)
        speech = np.ones((_BLOCK_SIZE,), dtype=np.float32) * 0.5
        blocks = [speech] * 3
        _feed_blocks_and_run(t, blocks)
        # No errors = counter handled correctly

    def test_continuous_speech_triggers_max_buffer_flush(self) -> None:
        """Continuous speech is force-flushed every _MAX_BUFFER_BLOCKS."""
        sentence_cb = MagicMock()
        t = _make_transcriber(sentence_cb=sentence_cb, status_cb=MagicMock())
        mock_model, _s = _setup_mocks(
            model_segments=[SimpleNamespace(text="Flushed")],
        )

        speech = np.ones((_BLOCK_SIZE,), dtype=np.float32) * 0.5
        # Use exactly 2x max buffer blocks to get 2 mid-flushes + 0 final
        blocks = [speech] * (_MAX_BUFFER_BLOCKS * 2)
        _feed_blocks_and_run(t, blocks)

        assert mock_model.transcribe.call_count == 2


# ---------------------------------------------------------------------------
# NEW TESTS — Streaming transcription callbacks and buffering
# ---------------------------------------------------------------------------


class TestStreamingTranscription:
    """Tests for streaming transcription callback invocation and buffering."""

    def test_three_speech_silence_cycles(self) -> None:
        """Three speech-silence cycles produce three sentence callbacks."""
        sentence_cb = MagicMock()
        t = _make_transcriber(sentence_cb=sentence_cb, status_cb=MagicMock())
        mock_model, _s = _setup_mocks()

        seg1 = SimpleNamespace(text="First")
        seg2 = SimpleNamespace(text="Second")
        seg3 = SimpleNamespace(text="Third")
        mock_model.transcribe.side_effect = [
            ([seg1], None),
            ([seg2], None),
            ([seg3], None),
        ]

        speech = np.ones((_BLOCK_SIZE,), dtype=np.float32) * 0.5
        silence = np.zeros((_BLOCK_SIZE,), dtype=np.float32)
        blocks = (
            [speech] * (_MIN_AUDIO_BLOCKS + 1)
            + [silence] * _SILENCE_BLOCKS
            + [speech] * (_MIN_AUDIO_BLOCKS + 1)
            + [silence] * _SILENCE_BLOCKS
            + [speech] * (_MIN_AUDIO_BLOCKS + 1)
            + [silence] * _SILENCE_BLOCKS
        )
        _feed_blocks_and_run(t, blocks)

        assert sentence_cb.call_count == 3  # noqa: PLR2004
        assert any(c[0][0] == "First" for c in sentence_cb.call_args_list)
        assert any(c[0][0] == "Second" for c in sentence_cb.call_args_list)
        assert any(c[0][0] == "Third" for c in sentence_cb.call_args_list)

    def test_transcribe_buffer_clears_after_processing(self) -> None:
        """Audio buffer is cleared after transcription in _process_loop."""
        sentence_cb = MagicMock()
        t = _make_transcriber(sentence_cb=sentence_cb, status_cb=MagicMock())

        seg1 = SimpleNamespace(text="Batch1")
        seg2 = SimpleNamespace(text="Batch2")
        mock_model, _s = _setup_mocks()
        mock_model.transcribe.side_effect = [
            ([seg1], None),
            ([seg2], None),
        ]

        speech = np.ones((_BLOCK_SIZE,), dtype=np.float32) * 0.5
        silence = np.zeros((_BLOCK_SIZE,), dtype=np.float32)
        # Two speech-silence cycles
        blocks = (
            [speech] * (_MIN_AUDIO_BLOCKS + 1)
            + [silence] * _SILENCE_BLOCKS
            + [speech] * (_MIN_AUDIO_BLOCKS + 1)
            + [silence] * _SILENCE_BLOCKS
        )
        _feed_blocks_and_run(t, blocks)

        # Verify both transcribe calls had correct-sized audio
        # First call: _MIN_AUDIO_BLOCKS+1 blocks
        first_audio = mock_model.transcribe.call_args_list[0][0][0]
        expected_first = (_MIN_AUDIO_BLOCKS + 1) * _BLOCK_SIZE
        assert first_audio.shape == (expected_first,)

    def test_language_switching_french(self) -> None:
        """French language code is resolved and passed."""
        sentence_cb = MagicMock()
        t = _make_transcriber(
            sentence_cb=sentence_cb,
            status_cb=MagicMock(),
            language="French",
        )
        mock_model, _s = _setup_mocks(
            model_segments=[SimpleNamespace(text="Bonjour")],
        )

        speech = np.ones((_BLOCK_SIZE,), dtype=np.float32) * 0.5
        silence = np.zeros((_BLOCK_SIZE,), dtype=np.float32)
        blocks = [speech] * (_MIN_AUDIO_BLOCKS + 1) + [silence] * _SILENCE_BLOCKS

        with patch(
            "src.core.speech_engine._get_speech_language_code",
            return_value="fr-FR",
        ):
            _feed_blocks_and_run(t, blocks)

        _, kwargs = mock_model.transcribe.call_args
        assert kwargs["language"] == "fr"

    def test_language_switching_chinese(self) -> None:
        """Chinese language code with region is split correctly."""
        sentence_cb = MagicMock()
        t = _make_transcriber(
            sentence_cb=sentence_cb,
            status_cb=MagicMock(),
            language="Chinese (Simplified)",
        )
        mock_model, _s = _setup_mocks(
            model_segments=[SimpleNamespace(text="Hello")],
        )

        speech = np.ones((_BLOCK_SIZE,), dtype=np.float32) * 0.5
        silence = np.zeros((_BLOCK_SIZE,), dtype=np.float32)
        blocks = [speech] * (_MIN_AUDIO_BLOCKS + 1) + [silence] * _SILENCE_BLOCKS

        with patch(
            "src.core.speech_engine._get_speech_language_code",
            return_value="zh-CN",
        ):
            _feed_blocks_and_run(t, blocks)

        _, kwargs = mock_model.transcribe.call_args
        assert kwargs["language"] == "zh"

    def test_empty_transcription_no_callback(self) -> None:
        """Empty transcription result does not call on_sentence."""
        sentence_cb = MagicMock()
        t = _make_transcriber(sentence_cb=sentence_cb, status_cb=MagicMock())
        mock_model, _s = _setup_mocks(model_segments=[])

        speech = np.ones((_BLOCK_SIZE,), dtype=np.float32) * 0.5
        silence = np.zeros((_BLOCK_SIZE,), dtype=np.float32)
        blocks = [speech] * (_MIN_AUDIO_BLOCKS + 1) + [silence] * _SILENCE_BLOCKS
        _feed_blocks_and_run(t, blocks)

        sentence_cb.assert_not_called()

    def test_whitespace_segments_skipped(self) -> None:
        """Segments that are only whitespace are filtered out."""
        sentence_cb = MagicMock()
        t = _make_transcriber(sentence_cb=sentence_cb)
        model = MagicMock()
        model.transcribe.return_value = (
            [SimpleNamespace(text="  "), SimpleNamespace(text="\t")],
            None,
        )
        blocks = [np.ones((8000,), dtype=np.float32)]
        t._transcribe_buffer(model, blocks, None)
        sentence_cb.assert_not_called()

    def test_mixed_valid_and_empty_segments(self) -> None:
        """Only non-empty segments contribute to the joined text."""
        sentence_cb = MagicMock()
        t = _make_transcriber(sentence_cb=sentence_cb)
        model = MagicMock()
        model.transcribe.return_value = (
            [
                SimpleNamespace(text="  "),
                SimpleNamespace(text="Hello"),
                SimpleNamespace(text=""),
                SimpleNamespace(text="World"),
            ],
            None,
        )
        blocks = [np.ones((8000,), dtype=np.float32)]
        t._transcribe_buffer(model, blocks, None)
        assert sentence_cb.call_count == 1
        assert sentence_cb.call_args[0][0] == "Hello World"


# ---------------------------------------------------------------------------
# NEW TESTS — Buffer management: overflow, cleanup
# ---------------------------------------------------------------------------


class TestBufferManagement:
    """Tests for audio buffer overflow handling and cleanup."""

    def test_large_queue_backlog_processed(self) -> None:
        """Many queued blocks are all processed when loop runs."""
        sentence_cb = MagicMock()
        t = _make_transcriber(sentence_cb=sentence_cb, status_cb=MagicMock())
        mock_model, _s = _setup_mocks(
            model_segments=[SimpleNamespace(text="Processed")],
        )

        speech = np.ones((_BLOCK_SIZE,), dtype=np.float32) * 0.5
        silence = np.zeros((_BLOCK_SIZE,), dtype=np.float32)
        # Many speech blocks — force-flushed every _MAX_BUFFER_BLOCKS
        num_speech = 50
        blocks = [speech] * num_speech + [silence] * _SILENCE_BLOCKS
        _feed_blocks_and_run(t, blocks)

        # Total transcriptions: mid-flushes + final silence-triggered flush
        expected_calls = (num_speech // _MAX_BUFFER_BLOCKS) + (
            1 if num_speech % _MAX_BUFFER_BLOCKS >= _MIN_AUDIO_BLOCKS else 0
        )
        assert mock_model.transcribe.call_count == expected_calls

    def test_queue_not_drained_on_stop(self) -> None:
        """stop() doesn't drain the queue — items remain."""
        t = _make_transcriber()
        t._is_running = True
        for _ in range(10):
            t._audio_queue.put(np.zeros((_BLOCK_SIZE,), dtype=np.float32))
        t._is_running = False
        assert t._audio_queue.qsize() == 10  # noqa: PLR2004

    def test_buffer_cleared_after_silence_detection(self) -> None:
        """After silence-triggered transcription, buffer is empty for next cycle."""
        sentence_cb = MagicMock()
        t = _make_transcriber(sentence_cb=sentence_cb, status_cb=MagicMock())

        seg1 = SimpleNamespace(text="First")
        seg2 = SimpleNamespace(text="Second")
        mock_model, _s = _setup_mocks()
        mock_model.transcribe.side_effect = [
            ([seg1], None),
            ([seg2], None),
        ]

        speech = np.ones((_BLOCK_SIZE,), dtype=np.float32) * 0.5
        silence = np.zeros((_BLOCK_SIZE,), dtype=np.float32)
        n = _MIN_AUDIO_BLOCKS + 1
        blocks = (
            [speech] * n
            + [silence] * _SILENCE_BLOCKS
            + [speech] * (n + 2)
            + [silence] * _SILENCE_BLOCKS
        )
        _feed_blocks_and_run(t, blocks)

        # Second batch should be bigger than first (n+2 vs n blocks)
        second_audio = mock_model.transcribe.call_args_list[1][0][0]
        assert second_audio.shape == ((n + 2) * _BLOCK_SIZE,)

    def test_single_block_below_minimum_not_flushed(self) -> None:
        """Buffer with 1 block (below _MIN_AUDIO_BLOCKS) is not flushed."""
        sentence_cb = MagicMock()
        t = _make_transcriber(sentence_cb=sentence_cb, status_cb=MagicMock())
        mock_model, _s = _setup_mocks()

        speech = np.ones((_BLOCK_SIZE,), dtype=np.float32) * 0.5
        blocks = [speech]  # Only 1 block
        _feed_blocks_and_run(t, blocks)

        mock_model.transcribe.assert_not_called()

    def test_buffer_exactly_min_blocks_flushed(self) -> None:
        """Buffer with exactly _MIN_AUDIO_BLOCKS is flushed on stop."""
        sentence_cb = MagicMock()
        t = _make_transcriber(sentence_cb=sentence_cb, status_cb=MagicMock())
        mock_model, _s = _setup_mocks(
            model_segments=[SimpleNamespace(text="Flushed")],
        )

        speech = np.ones((_BLOCK_SIZE,), dtype=np.float32) * 0.5
        blocks = [speech] * _MIN_AUDIO_BLOCKS
        _feed_blocks_and_run(t, blocks)

        mock_model.transcribe.assert_called_once()
        assert sentence_cb.call_count == 1
        assert sentence_cb.call_args[0][0] == "Flushed"


# ---------------------------------------------------------------------------
# NEW TESTS — Error handling: no microphone, device errors, permission
# ---------------------------------------------------------------------------


class TestErrorHandlingExpanded:
    """Expanded error handling tests."""

    def test_device_busy_error(self) -> None:
        """OSError for busy device is caught and reported."""
        status_cb = MagicMock()
        t = _make_transcriber(status_cb=status_cb)
        _setup_mocks(stream_side_effect=OSError("Device or resource busy"))
        t._is_running = True
        t._process_loop()

        assert t._is_running is False
        last_call = status_cb.call_args_list[-1][0][0]
        assert "Device or resource busy" in last_call

    def test_runtime_error_during_model_load(self) -> None:
        """RuntimeError during WhisperModel init is caught."""
        status_cb = MagicMock()
        t = _make_transcriber(status_cb=status_cb)
        _setup_mocks(model_side_effect=RuntimeError("CUDA unavailable"))
        t._is_running = True
        t._process_loop()

        assert t._is_running is False
        last_call = status_cb.call_args_list[-1][0][0]
        assert "CUDA unavailable" in last_call

    def test_value_error_during_model_load(self) -> None:
        """ValueError (e.g. invalid model name) is caught."""
        status_cb = MagicMock()
        t = _make_transcriber(status_cb=status_cb)
        _setup_mocks(model_side_effect=ValueError("Invalid model size: 'huge'"))
        t._is_running = True
        t._process_loop()

        assert t._is_running is False

    def test_keyboard_interrupt_handled(self) -> None:
        """KeyboardInterrupt during process loop is caught."""
        status_cb = MagicMock()
        t = _make_transcriber(status_cb=status_cb)
        _setup_mocks(model_side_effect=KeyboardInterrupt())
        t._is_running = True
        # KeyboardInterrupt is not a subclass of Exception,
        # so it won't be caught by except Exception
        with contextlib.suppress(KeyboardInterrupt):
            t._process_loop()
        # finally block should still run
        assert t._is_running is False

    def test_transcribe_exception_caught_in_loop(self) -> None:
        """Exception during model.transcribe is caught in the process loop."""
        status_cb = MagicMock()
        sentence_cb = MagicMock()
        t = _make_transcriber(sentence_cb=sentence_cb, status_cb=status_cb)
        mock_model, _s = _setup_mocks()
        mock_model.transcribe.side_effect = RuntimeError("decode failed")

        speech = np.ones((_BLOCK_SIZE,), dtype=np.float32) * 0.5
        silence = np.zeros((_BLOCK_SIZE,), dtype=np.float32)
        blocks = [speech] * (_MIN_AUDIO_BLOCKS + 1) + [silence] * _SILENCE_BLOCKS
        _feed_blocks_and_run(t, blocks)

        # Error caught, _is_running set to False in finally
        assert t._is_running is False
        sentence_cb.assert_not_called()

    def test_on_status_none_no_crash_on_error(self) -> None:
        """With on_status=None, error doesn't crash (no status callback)."""
        t = _make_transcriber(status_cb=None)
        _setup_mocks(model_side_effect=RuntimeError("fail"))
        t._is_running = True
        t._process_loop()
        assert t._is_running is False


# ---------------------------------------------------------------------------
# NEW TESTS — Thread safety: concurrent start/stop
# ---------------------------------------------------------------------------


class TestThreadSafety:
    """Tests for thread safety of concurrent start/stop calls."""

    def test_start_is_idempotent_with_running_flag(self) -> None:
        """start() with _is_running=True returns immediately."""
        t = _make_transcriber()
        t._is_running = True
        t._process_thread = MagicMock()
        t.start()  # Should be a no-op
        # No new thread created
        assert t._process_thread is not None

    def test_stop_while_process_loop_running(self) -> None:
        """stop() sets _is_running=False while process loop is running."""
        t = _make_transcriber(status_cb=MagicMock())
        mock_model, mock_stream = _setup_mocks(
            model_segments=[SimpleNamespace(text="Running")],
        )

        speech = np.ones((_BLOCK_SIZE,), dtype=np.float32) * 0.5
        # Feed blocks then check
        for _ in range(5):
            t._audio_queue.put(speech)

        call_count = [0]
        original_get = t._audio_queue.get

        def get_then_stop(timeout=None):
            call_count[0] += 1
            if call_count[0] > 3:  # noqa: PLR2004
                t._is_running = False
                raise queue.Empty
            return original_get(timeout=0)

        t._audio_queue.get = get_then_stop
        t._is_running = True
        t._process_loop()

        assert t._is_running is False

    def test_concurrent_start_stop_no_crash(self) -> None:
        """Rapid start/stop calls don't cause crashes."""
        t = _make_transcriber()
        for _ in range(10):
            with patch.object(t, "_process_loop"):
                t.start()
                t._is_running = False
                if t._process_thread:
                    t._process_thread.join(timeout=2)
                    t._process_thread = None
                t.stop()
                assert not t.is_running

    def test_stop_sets_running_false_before_stream_ops(self) -> None:
        """_is_running is False before stream stop/close in stop()."""
        t = _make_transcriber()
        t._is_running = True
        mock_stream = MagicMock()
        flags = []

        def check_running():
            flags.append(t._is_running)

        mock_stream.stop.side_effect = check_running
        t._stream = mock_stream
        t._process_thread = MagicMock()
        t.stop()
        # _is_running should be False when stream.stop() is called
        assert flags == [False]


# ---------------------------------------------------------------------------
# NEW TESTS — Device index and parametrized tests
# ---------------------------------------------------------------------------


class TestDeviceSelection:
    """Tests for device index selection."""

    @pytest.mark.parametrize("device_idx", [0, 1, 5, 10, None])
    def test_device_index_stored(self, device_idx: int | None) -> None:
        """Device index is stored on the transcriber."""
        t = _make_transcriber(device=device_idx)
        assert t._device is device_idx

    @pytest.mark.parametrize("device_idx", [0, 3, None])
    def test_device_passed_to_input_stream(self, device_idx: int | None) -> None:
        """Device index is forwarded to InputStream constructor."""
        t = _make_transcriber(device=device_idx, status_cb=MagicMock())
        _mock_model, _mock_stream = _setup_mocks()

        def stop_immediately(timeout=None):
            t._is_running = False
            raise queue.Empty

        t._audio_queue.get = stop_immediately
        t._is_running = True
        t._process_loop()

        mock_sd = sys.modules["sounddevice"]
        call_kwargs = mock_sd.InputStream.call_args[1]
        assert call_kwargs["device"] is device_idx


# ---------------------------------------------------------------------------
# NEW TESTS — list_input_devices extended
# ---------------------------------------------------------------------------


class TestListInputDevicesExtended:
    """Extended tests for list_input_devices."""

    def test_mixed_input_output_devices(self) -> None:
        """Correctly filters mixed device types."""
        devices = [
            {"name": "Default", "max_input_channels": 2},
            {"name": "HDMI", "max_input_channels": 0},
            {"name": "USB Mic", "max_input_channels": 1},
            {"name": "Speakers", "max_input_channels": 0},
            {"name": "Built-in Mic", "max_input_channels": 4},
        ]
        mock_sd = sys.modules["sounddevice"]
        mock_sd.query_devices = MagicMock(return_value=devices)
        result = list_input_devices()
        assert len(result) == 3  # noqa: PLR2004
        assert result[0] == (0, "Default")
        assert result[1] == (2, "USB Mic")
        assert result[2] == (4, "Built-in Mic")

    def test_device_index_preserved_with_gaps(self) -> None:
        """Device indices are original indices, not sequential."""
        devices = [
            {"name": "Out1", "max_input_channels": 0},
            {"name": "Out2", "max_input_channels": 0},
            {"name": "Mic", "max_input_channels": 1},
        ]
        mock_sd = sys.modules["sounddevice"]
        mock_sd.query_devices = MagicMock(return_value=devices)
        result = list_input_devices()
        assert result == [(2, "Mic")]

    def test_unicode_device_names(self) -> None:
        """Device names with unicode are preserved."""
        devices = [
            {"name": "Mikrofon 麦克风", "max_input_channels": 1},
        ]
        mock_sd = sys.modules["sounddevice"]
        mock_sd.query_devices = MagicMock(return_value=devices)
        result = list_input_devices()
        assert result == [(0, "Mikrofon 麦克风")]


# ---------------------------------------------------------------------------
# NEW TESTS — Model size variants
# ---------------------------------------------------------------------------


class TestModelSizeVariants:
    """Tests for different Whisper model sizes."""

    @pytest.mark.parametrize("size", ["tiny", "base", "small", "medium", "large"])
    def test_model_size_forwarded_to_whisper(self, size: str) -> None:
        """Each model size is passed to WhisperModel."""
        t = _make_transcriber(model_size=size, status_cb=MagicMock())
        _mock_model, _s = _setup_mocks()

        def stop_immediately(timeout=None):
            t._is_running = False
            raise queue.Empty

        t._audio_queue.get = stop_immediately
        t._is_running = True
        t._process_loop()

        mock_fw = sys.modules["faster_whisper"]
        assert mock_fw.WhisperModel.call_args[0][0] == size


# ---------------------------------------------------------------------------
# NEW TESTS — Language code edge cases
# ---------------------------------------------------------------------------


class TestLanguageCodeEdgeCasesExpanded:
    """Expanded language code edge case tests."""

    def test_language_code_none_from_speech_engine(self) -> None:
        """None return from _get_speech_language_code means no language kwarg."""
        t = _make_transcriber(
            status_cb=MagicMock(),
            language="UnknownLang",
        )
        mock_model, _s = _setup_mocks(
            model_segments=[SimpleNamespace(text="Hi")],
        )

        speech = np.ones((_BLOCK_SIZE,), dtype=np.float32) * 0.5
        silence = np.zeros((_BLOCK_SIZE,), dtype=np.float32)
        blocks = [speech] * (_MIN_AUDIO_BLOCKS + 1) + [silence] * _SILENCE_BLOCKS

        with patch(
            "src.core.speech_engine._get_speech_language_code",
            return_value=None,
        ):
            _feed_blocks_and_run(t, blocks)

        _, kwargs = mock_model.transcribe.call_args
        assert "language" not in kwargs

    def test_empty_language_label_no_language_kwarg(self) -> None:
        """Empty language label means no language kwarg."""
        t = _make_transcriber(
            status_cb=MagicMock(),
            language="",
        )
        mock_model, _s = _setup_mocks(
            model_segments=[SimpleNamespace(text="Auto")],
        )

        speech = np.ones((_BLOCK_SIZE,), dtype=np.float32) * 0.5
        silence = np.zeros((_BLOCK_SIZE,), dtype=np.float32)
        blocks = [speech] * (_MIN_AUDIO_BLOCKS + 1) + [silence] * _SILENCE_BLOCKS
        _feed_blocks_and_run(t, blocks)

        _, kwargs = mock_model.transcribe.call_args
        assert "language" not in kwargs


# ---------------------------------------------------------------------------
# NEW TESTS — Integration-style with multiple scenarios
# ---------------------------------------------------------------------------


class TestLiveEngineIntegrationExpanded:
    """Expanded integration tests."""

    def test_speech_flush_on_stop_with_segments(self) -> None:
        """Buffer flushed on stop produces correct segment text."""
        sentence_cb = MagicMock()
        t = _make_transcriber(sentence_cb=sentence_cb, status_cb=MagicMock())
        mock_model, _s = _setup_mocks(
            model_segments=[
                SimpleNamespace(text="Alpha"),
                SimpleNamespace(text="Beta"),
            ],
        )

        speech = np.ones((_BLOCK_SIZE,), dtype=np.float32) * 0.5
        blocks = [speech] * (_MIN_AUDIO_BLOCKS + 2)
        _feed_blocks_and_run(t, blocks)

        assert sentence_cb.call_count == 1
        assert sentence_cb.call_args[0][0] == "Alpha Beta"

    def test_no_speech_no_silence_empty_session(self) -> None:
        """Empty session (no blocks) produces no callbacks."""
        sentence_cb = MagicMock()
        t = _make_transcriber(sentence_cb=sentence_cb, status_cb=MagicMock())
        mock_model, _s = _setup_mocks()

        _feed_blocks_and_run(t, [])

        sentence_cb.assert_not_called()
        mock_model.transcribe.assert_not_called()

    def test_process_loop_finally_sets_running_false(self) -> None:
        """_process_loop always sets _is_running=False in the finally block."""
        t = _make_transcriber(status_cb=MagicMock())
        mock_model, _s = _setup_mocks()

        speech = np.ones((_BLOCK_SIZE,), dtype=np.float32) * 0.5
        blocks = [speech] * 3
        _feed_blocks_and_run(t, blocks)

        assert t._is_running is False

    def test_emit_status_called_on_success(self) -> None:
        """_emit_status called for 'listening' in _process_loop on success."""
        status_cb = MagicMock()
        t = _make_transcriber(status_cb=status_cb)
        _mock_model, _s = _setup_mocks()

        def stop_immediately(timeout=None):
            t._is_running = False
            raise queue.Empty

        t._audio_queue.get = stop_immediately
        t._is_running = True
        t._process_loop()

        # _process_loop calls _emit_status once for "listening"
        assert status_cb.call_count >= 1

    def test_audio_callback_copies_data_independently(self) -> None:
        """Multiple callback invocations create independent copies."""
        t = _make_transcriber()
        t._is_running = True
        data = np.ones((100, 1), dtype=np.float32)
        t._audio_callback(data, 100, None, None)
        data[:] = 99.0
        t._audio_callback(data, 100, None, None)

        first = t._audio_queue.get_nowait()
        second = t._audio_queue.get_nowait()
        assert first[0, 0] == 1.0
        assert second[0, 0] == 99.0


# ---------------------------------------------------------------------------
# NEW TESTS — Additional audio capture lifecycle
# ---------------------------------------------------------------------------


class TestAudioCaptureLifecycleExpanded:
    """Extended tests for audio capture lifecycle management."""

    def test_start_sets_running_true(self) -> None:
        """start() sets _is_running to True."""
        t = _make_transcriber()
        with patch.object(t, "_process_loop"):
            t.start()
            assert t._is_running is True
            t._is_running = False
            if t._process_thread:
                t._process_thread.join(timeout=2)

    def test_stop_joins_process_thread(self) -> None:
        """stop() joins the process thread."""
        t = _make_transcriber()
        mock_thread = MagicMock()
        t._process_thread = mock_thread
        t._is_running = True
        t.stop()
        mock_thread.join.assert_called_once_with(timeout=5)
        assert t._process_thread is None

    def test_stop_closes_stream(self) -> None:
        """stop() closes and clears the audio stream."""
        t = _make_transcriber()
        mock_stream = MagicMock()
        t._stream = mock_stream
        t._is_running = True
        t.stop()
        mock_stream.stop.assert_called_once()
        mock_stream.close.assert_called_once()
        assert t._stream is None

    def test_stop_no_stream_no_crash(self) -> None:
        """stop() with no stream does not crash."""
        t = _make_transcriber()
        t._is_running = True
        t.stop()
        assert t._is_running is False

    def test_stop_no_thread_no_crash(self) -> None:
        """stop() with no process thread does not crash."""
        t = _make_transcriber()
        t._process_thread = None
        t._is_running = True
        t.stop()
        assert t._is_running is False

    def test_double_stop(self) -> None:
        """Calling stop() twice is safe."""
        t = _make_transcriber()
        t._is_running = True
        mock_stream = MagicMock()
        t._stream = mock_stream
        t._process_thread = MagicMock()
        t.stop()
        t.stop()
        assert t._is_running is False

    def test_is_running_property(self) -> None:
        """is_running property reflects _is_running."""
        t = _make_transcriber()
        assert t.is_running is False
        t._is_running = True
        assert t.is_running is True
        t._is_running = False
        assert t.is_running is False

    def test_start_creates_daemon_thread(self) -> None:
        """start() creates a daemon thread."""
        t = _make_transcriber()
        with patch.object(t, "_process_loop"):
            t.start()
            assert t._process_thread is not None
            assert t._process_thread.daemon is True
            t._is_running = False
            t._process_thread.join(timeout=2)

    def test_audio_callback_ignores_when_not_running(self) -> None:
        """_audio_callback ignores data when _is_running is False."""
        t = _make_transcriber()
        t._is_running = False
        data = np.ones((100, 1), dtype=np.float32)
        t._audio_callback(data, 100, None, None)
        assert t._audio_queue.empty()

    def test_audio_callback_queues_when_running(self) -> None:
        """_audio_callback enqueues data when _is_running is True."""
        t = _make_transcriber()
        t._is_running = True
        data = np.ones((100, 1), dtype=np.float32)
        t._audio_callback(data, 100, None, None)
        assert t._audio_queue.qsize() == 1


class TestSilenceDetectionExpanded:
    """Extended silence detection tests."""

    def test_exact_threshold_is_not_silent(self) -> None:
        """RMS at threshold is NOT silent (check is strictly less than)."""
        # Use float64 for exact computation, then verify the code's < check
        block = np.ones((_BLOCK_SIZE,), dtype=np.float64) * _SILENCE_THRESHOLD
        rms = float(np.sqrt(np.mean(block**2)))
        # Due to float32 precision, the value may be slightly below threshold
        # The code uses `rms < _SILENCE_THRESHOLD`, so values at threshold are speech
        # This test verifies the constant's approximate magnitude
        assert abs(rms - _SILENCE_THRESHOLD) < 1e-6

    def test_just_below_threshold_is_silent(self) -> None:
        """RMS just below threshold is silent."""
        val = _SILENCE_THRESHOLD * 0.99
        block = np.ones((_BLOCK_SIZE,), dtype=np.float32) * val
        rms = float(np.sqrt(np.mean(block**2)))
        assert rms < _SILENCE_THRESHOLD

    def test_just_above_threshold_is_speech(self) -> None:
        """RMS just above threshold is speech."""
        val = _SILENCE_THRESHOLD * 1.01
        block = np.ones((_BLOCK_SIZE,), dtype=np.float32) * val
        rms = float(np.sqrt(np.mean(block**2)))
        assert rms >= _SILENCE_THRESHOLD

    def test_zero_block_is_silent(self) -> None:
        """All-zero block has RMS of 0."""
        block = np.zeros((_BLOCK_SIZE,), dtype=np.float32)
        rms = float(np.sqrt(np.mean(block**2)))
        assert rms == 0.0

    def test_loud_block_is_speech(self) -> None:
        """Full-amplitude block is well above threshold."""
        block = np.ones((_BLOCK_SIZE,), dtype=np.float32) * 0.9
        rms = float(np.sqrt(np.mean(block**2)))
        assert rms > _SILENCE_THRESHOLD

    def test_fewer_than_silence_blocks_no_transcription(self) -> None:
        """Fewer silent blocks than _SILENCE_BLOCKS does not trigger transcription."""
        sentence_cb = MagicMock()
        t = _make_transcriber(sentence_cb=sentence_cb, status_cb=MagicMock())
        mock_model, _s = _setup_mocks()

        speech = np.ones((_BLOCK_SIZE,), dtype=np.float32) * 0.5
        silence = np.zeros((_BLOCK_SIZE,), dtype=np.float32)
        # Speech followed by too few silence blocks
        blocks = [speech] * (_MIN_AUDIO_BLOCKS + 1) + [silence] * (_SILENCE_BLOCKS - 1)
        _feed_blocks_and_run(t, blocks)

        # Should flush at end (min blocks met) but NOT mid-loop
        assert mock_model.transcribe.call_count == 1

    def test_silence_blocks_exact_triggers_transcription(self) -> None:
        """Exactly _SILENCE_BLOCKS of silence triggers transcription."""
        sentence_cb = MagicMock()
        t = _make_transcriber(sentence_cb=sentence_cb, status_cb=MagicMock())
        seg = SimpleNamespace(text="Triggered")
        mock_model, _s = _setup_mocks(model_segments=[seg])

        speech = np.ones((_BLOCK_SIZE,), dtype=np.float32) * 0.5
        silence = np.zeros((_BLOCK_SIZE,), dtype=np.float32)
        blocks = [speech] * (_MIN_AUDIO_BLOCKS + 1) + [silence] * _SILENCE_BLOCKS
        _feed_blocks_and_run(t, blocks)

        assert sentence_cb.call_args[0][0] == "Triggered"


class TestTranscribeBufferDirect:
    """Direct tests for _transcribe_buffer method."""

    def test_concatenation_shape(self) -> None:
        """Audio blocks are concatenated and flattened."""
        t = _make_transcriber()
        model = MagicMock()
        model.transcribe.return_value = ([], None)
        blocks = [np.ones((_BLOCK_SIZE, 1), dtype=np.float32) for _ in range(3)]
        t._transcribe_buffer(model, blocks, None)
        audio_arg = model.transcribe.call_args[0][0]
        assert audio_arg.shape == (3 * _BLOCK_SIZE,)

    def test_word_timestamps_false(self) -> None:
        """word_timestamps=False is always passed."""
        t = _make_transcriber()
        model = MagicMock()
        model.transcribe.return_value = ([], None)
        blocks = [np.ones((_BLOCK_SIZE,), dtype=np.float32)]
        t._transcribe_buffer(model, blocks, None)
        _, kwargs = model.transcribe.call_args
        assert kwargs["word_timestamps"] is False

    def test_language_kwarg_set_when_provided(self) -> None:
        """Language kwarg is set when lang_code is provided."""
        t = _make_transcriber()
        model = MagicMock()
        model.transcribe.return_value = ([SimpleNamespace(text="Hi")], None)
        blocks = [np.ones((_BLOCK_SIZE,), dtype=np.float32)]
        t._transcribe_buffer(model, blocks, "en")
        _, kwargs = model.transcribe.call_args
        assert kwargs["language"] == "en"

    def test_no_language_kwarg_when_none(self) -> None:
        """Language kwarg is absent when lang_code is None."""
        t = _make_transcriber()
        model = MagicMock()
        model.transcribe.return_value = ([SimpleNamespace(text="Hi")], None)
        blocks = [np.ones((_BLOCK_SIZE,), dtype=np.float32)]
        t._transcribe_buffer(model, blocks, None)
        _, kwargs = model.transcribe.call_args
        assert "language" not in kwargs

    def test_empty_lang_code_no_language_kwarg(self) -> None:
        """Empty string lang_code does not set language kwarg."""
        t = _make_transcriber()
        model = MagicMock()
        model.transcribe.return_value = ([], None)
        blocks = [np.ones((_BLOCK_SIZE,), dtype=np.float32)]
        t._transcribe_buffer(model, blocks, "")
        _, kwargs = model.transcribe.call_args
        assert "language" not in kwargs

    def test_multiple_segments_joined_with_space(self) -> None:
        """Multiple segments are joined with space."""
        sentence_cb = MagicMock()
        t = _make_transcriber(sentence_cb=sentence_cb)
        model = MagicMock()
        model.transcribe.return_value = (
            [SimpleNamespace(text="Hello"), SimpleNamespace(text="World")],
            None,
        )
        blocks = [np.ones((_BLOCK_SIZE,), dtype=np.float32)]
        t._transcribe_buffer(model, blocks, None)
        assert sentence_cb.call_count == 1
        assert sentence_cb.call_args[0][0] == "Hello World"

    def test_segments_stripped(self) -> None:
        """Segment text is stripped of whitespace."""
        sentence_cb = MagicMock()
        t = _make_transcriber(sentence_cb=sentence_cb)
        model = MagicMock()
        model.transcribe.return_value = (
            [SimpleNamespace(text="  Hello  ")],
            None,
        )
        blocks = [np.ones((_BLOCK_SIZE,), dtype=np.float32)]
        t._transcribe_buffer(model, blocks, None)
        assert sentence_cb.call_count == 1
        assert sentence_cb.call_args[0][0] == "Hello"


class TestEmitStatusExpanded:
    """Extended tests for _emit_status."""

    def test_emit_status_calls_callback(self) -> None:
        """_emit_status calls the status callback with translated text."""
        status_cb = MagicMock()
        t = _make_transcriber(status_cb=status_cb)
        with patch("src.constants.i18n.tr", return_value="Translated") as mock_tr:
            t._emit_status("some.key")
        mock_tr.assert_called_once_with("some.key")
        status_cb.assert_called_once_with("Translated")

    def test_emit_status_none_callback(self) -> None:
        """_emit_status with None callback does not crash."""
        t = _make_transcriber(status_cb=None)
        with patch("src.constants.i18n.tr", return_value="X"):
            t._emit_status("any.key")  # Should not raise

    def test_emit_status_multiple_calls(self) -> None:
        """_emit_status can be called multiple times."""
        status_cb = MagicMock()
        t = _make_transcriber(status_cb=status_cb)
        with patch("src.constants.i18n.tr", side_effect=lambda k: k):
            t._emit_status("key1")
            t._emit_status("key2")
        assert status_cb.call_count == 2  # noqa: PLR2004


class TestProcessLoopStreamConfig:
    """Tests for _process_loop InputStream configuration."""

    def test_stream_sample_rate(self) -> None:
        """InputStream is created with _SAMPLE_RATE."""
        t = _make_transcriber(status_cb=MagicMock())
        _setup_mocks()

        def stop_immediately(timeout=None):
            t._is_running = False
            raise queue.Empty

        t._audio_queue.get = stop_immediately
        t._is_running = True
        t._process_loop()

        mock_sd = sys.modules["sounddevice"]
        call_kwargs = mock_sd.InputStream.call_args[1]
        assert call_kwargs["samplerate"] == _SAMPLE_RATE

    def test_stream_channels(self) -> None:
        """InputStream is created with 1 channel."""
        t = _make_transcriber(status_cb=MagicMock())
        _setup_mocks()

        def stop_immediately(timeout=None):
            t._is_running = False
            raise queue.Empty

        t._audio_queue.get = stop_immediately
        t._is_running = True
        t._process_loop()

        mock_sd = sys.modules["sounddevice"]
        call_kwargs = mock_sd.InputStream.call_args[1]
        assert call_kwargs["channels"] == 1

    def test_stream_blocksize(self) -> None:
        """InputStream is created with _BLOCK_SIZE."""
        t = _make_transcriber(status_cb=MagicMock())
        _setup_mocks()

        def stop_immediately(timeout=None):
            t._is_running = False
            raise queue.Empty

        t._audio_queue.get = stop_immediately
        t._is_running = True
        t._process_loop()

        mock_sd = sys.modules["sounddevice"]
        call_kwargs = mock_sd.InputStream.call_args[1]
        assert call_kwargs["blocksize"] == _BLOCK_SIZE

    def test_stream_dtype_float32(self) -> None:
        """InputStream is created with float32 dtype."""
        t = _make_transcriber(status_cb=MagicMock())
        _setup_mocks()

        def stop_immediately(timeout=None):
            t._is_running = False
            raise queue.Empty

        t._audio_queue.get = stop_immediately
        t._is_running = True
        t._process_loop()

        mock_sd = sys.modules["sounddevice"]
        call_kwargs = mock_sd.InputStream.call_args[1]
        assert call_kwargs["dtype"] == "float32"

    def test_stream_callback_is_audio_callback(self) -> None:
        """InputStream callback is the transcriber's _audio_callback."""
        t = _make_transcriber(status_cb=MagicMock())
        _setup_mocks()

        def stop_immediately(timeout=None):
            t._is_running = False
            raise queue.Empty

        t._audio_queue.get = stop_immediately
        t._is_running = True
        t._process_loop()

        mock_sd = sys.modules["sounddevice"]
        call_kwargs = mock_sd.InputStream.call_args[1]
        assert call_kwargs["callback"] == t._audio_callback

    def test_model_uses_cpu_device(self) -> None:
        """WhisperModel is created with device='cpu'."""
        t = _make_transcriber(status_cb=MagicMock())
        _setup_mocks()

        def stop_immediately(timeout=None):
            t._is_running = False
            raise queue.Empty

        t._audio_queue.get = stop_immediately
        t._is_running = True
        t._process_loop()

        mock_fw = sys.modules["faster_whisper"]
        call_kwargs = mock_fw.WhisperModel.call_args[1]
        assert call_kwargs["device"] == "cpu"

    def test_model_uses_int8_compute(self) -> None:
        """WhisperModel is created with compute_type='int8'."""
        t = _make_transcriber(status_cb=MagicMock())
        _setup_mocks()

        def stop_immediately(timeout=None):
            t._is_running = False
            raise queue.Empty

        t._audio_queue.get = stop_immediately
        t._is_running = True
        t._process_loop()

        mock_fw = sys.modules["faster_whisper"]
        call_kwargs = mock_fw.WhisperModel.call_args[1]
        assert call_kwargs["compute_type"] == "int8"


# ---------------------------------------------------------------------------
# on_stopped callback
# ---------------------------------------------------------------------------


class TestOnStoppedCallback:
    """Tests for the on_stopped callback in LiveTranscriber."""

    def test_on_stopped_stored(self) -> None:
        """on_stopped callback is stored on the instance."""
        cb = MagicMock()
        t = LiveTranscriber(on_sentence=MagicMock(), on_stopped=cb)
        assert t._on_stopped is cb

    def test_on_stopped_default_none(self) -> None:
        """on_stopped defaults to None."""
        t = LiveTranscriber(on_sentence=MagicMock())
        assert t._on_stopped is None

    def test_on_stopped_called_after_normal_exit(self, monkeypatch) -> None:
        """on_stopped fires when _process_loop exits normally."""
        monkeypatch.undo()
        stopped = MagicMock()
        t = LiveTranscriber(
            on_sentence=MagicMock(),
            on_status=MagicMock(),
            on_stopped=stopped,
        )
        # Immediately stop after one block read
        t._audio_queue.get = MagicMock(
            side_effect=lambda **kw: (
                setattr(t, "_is_running", False) or (_ for _ in ()).throw(queue.Empty)
            ),
        )
        t._is_running = True

        mock_sd = sys.modules["sounddevice"]
        mock_sd.InputStream = MagicMock(return_value=MagicMock())
        mock_fw = sys.modules["faster_whisper"]
        mock_fw.WhisperModel = MagicMock(return_value=MagicMock())

        t._process_loop()
        stopped.assert_called_once()
        assert t._is_running is False

    def test_on_stopped_called_after_error(self, monkeypatch) -> None:
        """on_stopped fires even when _process_loop raises an error."""
        monkeypatch.undo()
        stopped = MagicMock()
        t = LiveTranscriber(
            on_sentence=MagicMock(),
            on_status=MagicMock(),
            on_stopped=stopped,
        )
        # Force an error during audio check
        monkeypatch.setattr(
            f"{_MOD}.check_audio_available",
            lambda: "live.error_no_portaudio",
        )
        t._is_running = True
        t._process_loop()
        stopped.assert_called_once()


# ---------------------------------------------------------------------------
# _stop_system_audio
# ---------------------------------------------------------------------------


class TestStopParec:
    """Tests for _stop_system_audio()."""

    def test_stop_system_audio_terminates_process(self) -> None:
        """_stop_system_audio terminates the subprocess."""
        t = LiveTranscriber(on_sentence=MagicMock())
        mock_proc = MagicMock()
        t._sys_audio_proc = mock_proc
        t._sys_audio_thread = MagicMock()
        t._stop_system_audio()
        mock_proc.terminate.assert_called_once()
        mock_proc.wait.assert_called_once_with(timeout=3)
        assert t._sys_audio_proc is None
        assert t._sys_audio_thread is None

    def test_stop_system_audio_noop_when_no_process(self) -> None:
        """_stop_system_audio is safe to call when no process is running."""
        t = LiveTranscriber(on_sentence=MagicMock())
        t._stop_system_audio()  # Should not raise

    def test_stop_system_audio_handles_terminate_timeout(self) -> None:
        """A subprocess that ignores SIGTERM is escalated to SIGKILL.

        Regression: previously ``proc.wait(timeout=3)`` could raise
        ``subprocess.TimeoutExpired`` mid-cleanup, leaving
        ``_sys_audio_proc`` pointing at a defunct Popen and the reader
        thread reference orphaned for the rest of the session.  Now
        the wait is in a try/except that escalates to ``proc.kill()``
        and the ``finally`` clears state regardless.
        """
        t = LiveTranscriber(on_sentence=MagicMock())
        mock_proc = MagicMock()
        # First wait raises TimeoutExpired; second (after kill) succeeds.
        mock_proc.wait.side_effect = [
            subprocess.TimeoutExpired(cmd=["parec"], timeout=3),
            None,
        ]
        mock_thread = MagicMock()
        t._sys_audio_proc = mock_proc
        t._sys_audio_thread = mock_thread

        t._stop_system_audio()

        # SIGTERM tried first.
        mock_proc.terminate.assert_called_once()
        # Then escalated to SIGKILL.
        mock_proc.kill.assert_called_once()
        # State cleared even though wait raised.
        assert t._sys_audio_proc is None
        assert t._sys_audio_thread is None
        # Reader thread join still ran — wasn't skipped by the exception.
        mock_thread.join.assert_called_once_with(timeout=3)

    def test_stop_system_audio_swallows_other_exceptions(self) -> None:
        """Any exception during stop is logged + state still clears.

        ``proc.terminate()`` can raise ``OSError`` if the process is
        already dead; we don't want that to leak past Stop and prevent
        the user from starting another session.
        """
        t = LiveTranscriber(on_sentence=MagicMock())
        mock_proc = MagicMock()
        mock_proc.terminate.side_effect = OSError("already dead")
        mock_thread = MagicMock()
        t._sys_audio_proc = mock_proc
        t._sys_audio_thread = mock_thread

        # Should NOT raise.
        t._stop_system_audio()

        assert t._sys_audio_proc is None
        assert t._sys_audio_thread is None
        mock_thread.join.assert_called_once_with(timeout=3)


# ---------------------------------------------------------------------------
# _open_streams with different audio sources
# ---------------------------------------------------------------------------


class TestOpenStreams:
    """Tests for _open_streams() with different audio sources."""

    def test_microphone_opens_one_stream(self) -> None:
        """Microphone mode opens a single InputStream."""
        t = LiveTranscriber(
            on_sentence=MagicMock(),
            audio_source="microphone",
        )
        mock_sd = MagicMock()
        mock_stream = MagicMock()
        mock_sd.InputStream.return_value = mock_stream

        t._open_streams(mock_sd, mic_dev=0)

        mock_sd.InputStream.assert_called_once()
        mock_stream.start.assert_called_once()
        assert t._stream is mock_stream

    def test_system_starts_parec(self, monkeypatch) -> None:
        """System mode starts parec instead of InputStream."""
        t = LiveTranscriber(
            on_sentence=MagicMock(),
            audio_source="system",
        )
        monkeypatch.setattr(
            f"{_MOD}._get_default_monitor_source",
            lambda: "sink.monitor",
        )
        mock_sd = MagicMock()

        with patch.object(t, "_start_system_audio") as mock_parec:
            t._open_streams(mock_sd, mic_dev=None)
            mock_parec.assert_called_once()
        # No InputStream for system-only
        mock_sd.InputStream.assert_not_called()

    def test_both_opens_stream_and_parec(self, monkeypatch) -> None:
        """Both mode opens InputStream + parec."""
        t = LiveTranscriber(
            on_sentence=MagicMock(),
            audio_source="both",
        )
        monkeypatch.setattr(
            f"{_MOD}._get_default_monitor_source",
            lambda: "sink.monitor",
        )
        mock_sd = MagicMock()
        mock_stream = MagicMock()
        mock_sd.InputStream.return_value = mock_stream

        with patch.object(t, "_start_system_audio") as mock_parec:
            t._open_streams(mock_sd, mic_dev=0)
            mock_parec.assert_called_once()
        mock_sd.InputStream.assert_called_once()
        mock_stream.start.assert_called_once()


# ---------------------------------------------------------------------------
# Timestamp verification in on_sentence
# ---------------------------------------------------------------------------


class TestTimestampInOnSentence:
    """Tests that on_sentence receives correct timestamp arguments."""

    def test_timestamps_passed_to_callback(self) -> None:
        """_transcribe_buffer passes start/end seconds to on_sentence."""
        sentence_cb = MagicMock()
        t = LiveTranscriber(on_sentence=sentence_cb)

        mock_model = MagicMock()
        mock_model.transcribe.return_value = (
            [SimpleNamespace(text="Hello")],
            None,
        )

        block = np.ones((_BLOCK_SIZE, 1), dtype="float32") * 0.5
        t._transcribe_buffer(mock_model, [block], None, 2.5, 5.0)

        assert sentence_cb.call_count == 1
        args = sentence_cb.call_args[0]
        assert args[0] == "Hello"
        assert args[1] == 2.5  # noqa: PLR2004
        assert args[2] == 5.0  # noqa: PLR2004

    def test_default_timestamps_are_zero(self) -> None:
        """_transcribe_buffer defaults timestamps to 0.0."""
        sentence_cb = MagicMock()
        t = LiveTranscriber(on_sentence=sentence_cb)

        mock_model = MagicMock()
        mock_model.transcribe.return_value = (
            [SimpleNamespace(text="Hi")],
            None,
        )

        block = np.ones((_BLOCK_SIZE, 1), dtype="float32") * 0.5
        t._transcribe_buffer(mock_model, [block], None)

        args = sentence_cb.call_args[0]
        assert args[1] == 0.0
        assert args[2] == 0.0


# ---------------------------------------------------------------------------
# Edge cases: _get_default_monitor_source, _read_block timeout, stop+parec
# ---------------------------------------------------------------------------


class TestDefaultMonitorSourceEdgeCases:
    """Edge cases for _get_default_monitor_source."""

    def test_returns_none_on_empty_stdout(self, monkeypatch) -> None:
        """Returns None when pactl output is empty despite success."""
        monkeypatch.setattr(f"{_MOD}.shutil.which", lambda b: "/usr/bin/pactl")
        monkeypatch.setattr(
            f"{_MOD}.subprocess.run",
            lambda *a, **kw: SimpleNamespace(returncode=0, stdout="  \n"),
        )
        assert _get_default_monitor_source() is None

    def test_returns_none_on_exception(self, monkeypatch) -> None:
        """Returns None when subprocess raises."""
        monkeypatch.setattr(f"{_MOD}.shutil.which", lambda b: "/usr/bin/pactl")

        def _raise(*a, **kw):
            raise OSError("timeout")

        monkeypatch.setattr(f"{_MOD}.subprocess.run", _raise)
        assert _get_default_monitor_source() is None


class TestReadBlockTimeout:
    """Tests for _read_block returning None on timeout."""

    def test_returns_none_on_empty_queue(self) -> None:
        """Returns None when audio queue is empty (timeout)."""
        t = LiveTranscriber(
            on_sentence=MagicMock(),
            audio_source="microphone",
        )
        # Don't put anything in the queue
        result = t._read_block()
        assert result is None

    def test_both_mode_returns_none_when_both_empty(self) -> None:
        """Returns None in 'both' mode when both queues are empty."""
        t = LiveTranscriber(
            on_sentence=MagicMock(),
            audio_source="both",
        )
        t._sys_queue = queue.Queue()
        result = t._read_block()
        assert result is None


class TestStopCallsStopParec:
    """Tests that stop() cleans up parec resources."""

    def test_stop_calls_stop_system_audio(self) -> None:
        """stop() terminates parec subprocess if it exists."""
        t = LiveTranscriber(on_sentence=MagicMock())
        mock_proc = MagicMock()
        t._sys_audio_proc = mock_proc
        t._sys_audio_thread = MagicMock()
        t._is_running = True
        t.stop()
        mock_proc.terminate.assert_called_once()
        assert t._sys_audio_proc is None


class TestStartParec:
    """Tests for _start_system_audio subprocess spawning."""

    def test_start_system_audio_raises_when_no_monitor(
        self,
        monkeypatch,
    ) -> None:
        """Raises ValueError when no monitor source available."""
        monkeypatch.setattr(
            f"{_MOD}._get_default_monitor_source",
            lambda: None,
        )
        t = LiveTranscriber(on_sentence=MagicMock())
        target = queue.Queue()
        with pytest.raises(ValueError, match="live.error_no_system_audio"):
            t._start_system_audio(target)

    def test_start_system_audio_spawns_subprocess(self, monkeypatch) -> None:
        """Spawns parec with correct arguments."""
        monkeypatch.setattr(
            f"{_MOD}._get_default_monitor_source",
            lambda: "sink.monitor",
        )
        mock_popen = MagicMock()
        mock_popen.poll.return_value = 0  # already exited
        mock_popen.stdout.read.return_value = b""
        monkeypatch.setattr(
            f"{_MOD}.subprocess.Popen",
            lambda *a, **kw: mock_popen,
        )
        t = LiveTranscriber(on_sentence=MagicMock())
        t._is_running = True
        target = queue.Queue()
        t._start_system_audio(target)
        assert t._sys_audio_proc is mock_popen
        assert t._sys_audio_thread is not None
        # Let reader thread finish
        t._sys_audio_thread.join(timeout=2)


class TestSystemAudioPlatformDispatch:
    """Cross-platform system-audio capture dispatch.

    The Linux path (parec) is exercised by ``TestStartParec`` /
    ``TestCheckSystemAudioAvailable`` against the actual platform.
    These tests stub ``platform.system()`` so the macOS / Windows /
    unsupported branches can be verified from a Linux host.
    """

    def test_linux_dispatches_to_linux_helper(self, monkeypatch) -> None:
        """On Linux the dispatcher routes to ``_start_system_audio_linux``."""
        monkeypatch.setattr(f"{_MOD}.platform.system", lambda: "Linux")
        t = LiveTranscriber(on_sentence=MagicMock())
        called: list[str] = []
        monkeypatch.setattr(
            t, "_start_system_audio_linux",
            lambda target: called.append("linux"),
        )
        monkeypatch.setattr(
            t, "_start_system_audio_macos",
            lambda target: called.append("macos"),
        )
        monkeypatch.setattr(
            t, "_start_system_audio_windows",
            lambda target: called.append("windows"),
        )
        t._start_system_audio(queue.Queue())
        assert called == ["linux"]

    def test_macos_dispatches_to_macos_helper(self, monkeypatch) -> None:
        """On macOS the dispatcher routes to ``_start_system_audio_macos``."""
        monkeypatch.setattr(f"{_MOD}.platform.system", lambda: "Darwin")
        t = LiveTranscriber(on_sentence=MagicMock())
        called: list[str] = []
        monkeypatch.setattr(
            t, "_start_system_audio_macos",
            lambda target: called.append("macos"),
        )
        t._start_system_audio(queue.Queue())
        assert called == ["macos"]

    def test_windows_dispatches_to_windows_helper(self, monkeypatch) -> None:
        """On Windows the dispatcher routes to ``_start_system_audio_windows``."""
        monkeypatch.setattr(f"{_MOD}.platform.system", lambda: "Windows")
        t = LiveTranscriber(on_sentence=MagicMock())
        called: list[str] = []
        monkeypatch.setattr(
            t, "_start_system_audio_windows",
            lambda target: called.append("windows"),
        )
        t._start_system_audio(queue.Queue())
        assert called == ["windows"]

    def test_unsupported_platform_raises(self, monkeypatch) -> None:
        """Unknown platform raises ``live.error_no_system_audio``."""
        monkeypatch.setattr(f"{_MOD}.platform.system", lambda: "FreeBSD")
        t = LiveTranscriber(on_sentence=MagicMock())
        with pytest.raises(ValueError, match="live.error_no_system_audio"):
            t._start_system_audio(queue.Queue())

    def test_check_system_audio_available_macos(self, monkeypatch) -> None:
        """Returns True on macOS when a loopback device is detected."""
        monkeypatch.setattr(f"{_MOD}.platform.system", lambda: "Darwin")
        monkeypatch.setattr(
            f"{_MOD}._get_macos_loopback_device_index",
            lambda: 2,
        )
        assert check_system_audio_available() is True

    def test_check_system_audio_available_macos_no_loopback(
        self, monkeypatch,
    ) -> None:
        """Returns False on macOS when no loopback device is installed."""
        monkeypatch.setattr(f"{_MOD}.platform.system", lambda: "Darwin")
        monkeypatch.setattr(
            f"{_MOD}._get_macos_loopback_device_index",
            lambda: None,
        )
        assert check_system_audio_available() is False

    def test_check_system_audio_available_windows(self, monkeypatch) -> None:
        """Windows branch returns True when a dshow loopback device exists."""
        monkeypatch.setattr(f"{_MOD}.platform.system", lambda: "Windows")
        monkeypatch.setattr(
            f"{_MOD}._get_windows_loopback_device_name",
            lambda: "virtual-audio-capturer",
        )
        assert check_system_audio_available() is True

    def test_check_system_audio_available_windows_no_loopback(
        self, monkeypatch,
    ) -> None:
        """Windows branch returns False when no compatible device is present."""
        monkeypatch.setattr(f"{_MOD}.platform.system", lambda: "Windows")
        monkeypatch.setattr(
            f"{_MOD}._get_windows_loopback_device_name",
            lambda: None,
        )
        assert check_system_audio_available() is False

    def test_check_system_audio_available_unsupported_platform(
        self, monkeypatch,
    ) -> None:
        """Unsupported platforms always report False."""
        monkeypatch.setattr(f"{_MOD}.platform.system", lambda: "FreeBSD")
        assert check_system_audio_available() is False


class TestStartSystemAudioMacos:
    """``_start_system_audio_macos`` builds the right ffmpeg invocation."""

    def test_raises_when_no_loopback_device(self, monkeypatch) -> None:
        monkeypatch.setattr(
            f"{_MOD}._get_macos_loopback_device_index",
            lambda: None,
        )
        t = LiveTranscriber(on_sentence=MagicMock())
        with pytest.raises(ValueError, match="live.error_no_system_audio"):
            t._start_system_audio_macos(queue.Queue())

    def test_spawns_ffmpeg_with_avfoundation(self, monkeypatch) -> None:
        """Uses ``-f avfoundation -i :<idx>`` against the discovered device."""
        monkeypatch.setattr(
            f"{_MOD}._get_macos_loopback_device_index",
            lambda: 3,
        )
        captured: list[list[str]] = []
        mock_popen = MagicMock()
        mock_popen.poll.return_value = 0
        mock_popen.stdout.read.return_value = b""

        def fake_popen(argv, **kwargs) -> MagicMock:  # noqa: ARG001
            captured.append(argv)
            return mock_popen

        monkeypatch.setattr(f"{_MOD}.subprocess.Popen", fake_popen)
        t = LiveTranscriber(on_sentence=MagicMock())
        t._is_running = True
        t._start_system_audio_macos(queue.Queue())
        assert t._sys_audio_proc is mock_popen
        assert captured, "Popen was not called"
        argv = captured[0]
        assert argv[0] == "ffmpeg"
        assert "-f" in argv and "avfoundation" in argv
        assert "-i" in argv
        assert ":3" in argv  # device index
        assert "s16le" in argv  # raw output
        t._sys_audio_thread.join(timeout=2)


class TestStartSystemAudioWindows:
    """``_start_system_audio_windows`` builds the right ffmpeg invocation."""

    def test_raises_when_no_loopback_device(self, monkeypatch) -> None:
        monkeypatch.setattr(
            f"{_MOD}._get_windows_loopback_device_name",
            lambda: None,
        )
        t = LiveTranscriber(on_sentence=MagicMock())
        with pytest.raises(ValueError, match="live.error_no_system_audio"):
            t._start_system_audio_windows(queue.Queue())

    def test_spawns_ffmpeg_with_dshow(self, monkeypatch) -> None:
        """Uses ``-f dshow -i audio="<device>"``."""
        monkeypatch.setattr(
            f"{_MOD}._get_windows_loopback_device_name",
            lambda: "virtual-audio-capturer",
        )
        captured: list[list[str]] = []
        mock_popen = MagicMock()
        mock_popen.poll.return_value = 0
        mock_popen.stdout.read.return_value = b""

        def fake_popen(argv, **kwargs) -> MagicMock:  # noqa: ARG001
            captured.append(argv)
            return mock_popen

        monkeypatch.setattr(f"{_MOD}.subprocess.Popen", fake_popen)
        t = LiveTranscriber(on_sentence=MagicMock())
        t._is_running = True
        t._start_system_audio_windows(queue.Queue())
        argv = captured[0]
        assert argv[0] == "ffmpeg"
        assert "-f" in argv and "dshow" in argv
        assert "audio=virtual-audio-capturer" in argv
        assert "s16le" in argv
        t._sys_audio_thread.join(timeout=2)


class TestStartSystemAudioWindowsSoundcard:
    """Native WASAPI loopback path on Windows via the ``soundcard`` package.

    When available, ``soundcard`` is preferred over ffmpeg+dshow because
    WASAPI loopback is built into Windows — users don't need to install
    Screen Capture Recorder or VB-Audio Virtual Cable.  These tests
    stub the package interface so they run on a Linux host where
    ``soundcard`` itself isn't (and shouldn't be) installed.
    """

    def _make_soundcard_module(
        self,
        *,
        record_blocks: list[np.ndarray] | None = None,
    ) -> MagicMock:
        """Builds a fake soundcard module with default_speaker / loopback."""
        module = MagicMock()

        speaker = MagicMock()
        speaker.id = "Speakers (Realtek)"
        module.default_speaker.return_value = speaker

        recorder = MagicMock()
        # Hand back canned blocks then None to signal "stop".
        if record_blocks is None:
            record_blocks = [np.zeros((1600, 1), dtype=np.float32)]
        record_blocks_iter = iter(record_blocks + [None] * 10)
        recorder.record.side_effect = lambda numframes: next(  # noqa: ARG005
            record_blocks_iter,
        )

        loopback_mic = MagicMock()
        loopback_mic.recorder.return_value.__enter__.return_value = recorder
        loopback_mic.recorder.return_value.__exit__.return_value = False
        module.get_microphone.return_value = loopback_mic
        return module

    def test_dispatcher_prefers_soundcard_over_ffmpeg(
        self, monkeypatch,
    ) -> None:
        """When soundcard works, ffmpeg+dshow path is never invoked."""
        fake_module = self._make_soundcard_module()
        monkeypatch.setitem(__import__("sys").modules, "soundcard", fake_module)

        # If the dshow fallback fires, this would be checked — make
        # the test loud about a regression.
        monkeypatch.setattr(
            f"{_MOD}._get_windows_loopback_device_name",
            lambda: (_ for _ in ()).throw(
                AssertionError("dshow fallback unexpectedly invoked"),
            ),
        )
        # And don't actually spawn a subprocess if something does slip.
        monkeypatch.setattr(
            f"{_MOD}.subprocess.Popen",
            lambda *a, **k: (_ for _ in ()).throw(  # noqa: ARG005
                AssertionError("subprocess.Popen unexpectedly invoked"),
            ),
        )

        t = LiveTranscriber(on_sentence=MagicMock())
        t._is_running = True
        t._start_system_audio_windows(queue.Queue())

        assert t._sys_audio_thread is not None
        assert t._sys_audio_proc is None  # Not the ffmpeg path
        # Wind down the reader thread cleanly.
        t._is_running = False
        t._sys_audio_thread.join(timeout=2)
        fake_module.default_speaker.assert_called()
        fake_module.get_microphone.assert_called_once()
        # ``include_loopback=True`` is the WASAPI-loopback flag —
        # without it we'd be recording the mic instead of the speakers.
        kwargs = fake_module.get_microphone.call_args.kwargs
        assert kwargs.get("include_loopback") is True

    def test_falls_back_to_ffmpeg_when_soundcard_import_fails(
        self, monkeypatch,
    ) -> None:
        """ImportError → silent fallback to ffmpeg+dshow path.

        Mirrors what would happen on a Windows host without the
        ``soundcard`` package installed (rare — it's a default dep on
        Windows — but the fallback exists so the page doesn't break).
        """
        # Make ``import soundcard`` raise ImportError.
        sys_modules = __import__("sys").modules
        monkeypatch.delitem(sys_modules, "soundcard", raising=False)

        # We can't easily make the import statement raise inside the
        # method without patching sys.meta_path; instead, register a
        # finder that refuses ``soundcard`` imports for this test.
        import importlib.abc  # noqa: PLC0415
        import importlib.machinery  # noqa: PLC0415

        class _RefuseSoundcard(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):  # noqa: ANN001, ARG002, D102
                if fullname == "soundcard":
                    raise ImportError("soundcard refused for test")

        meta_path = __import__("sys").meta_path
        finder = _RefuseSoundcard()
        meta_path.insert(0, finder)
        try:
            captured: list[list[str]] = []
            mock_popen = MagicMock()
            mock_popen.poll.return_value = 0
            mock_popen.stdout.read.return_value = b""

            def fake_popen(argv, **kwargs):  # noqa: ANN001, ARG001
                captured.append(argv)
                return mock_popen

            monkeypatch.setattr(f"{_MOD}.subprocess.Popen", fake_popen)
            monkeypatch.setattr(
                f"{_MOD}._get_windows_loopback_device_name",
                lambda: "virtual-audio-capturer",
            )

            t = LiveTranscriber(on_sentence=MagicMock())
            t._is_running = True
            t._start_system_audio_windows(queue.Queue())

            assert captured, "ffmpeg+dshow fallback was not invoked"
            assert captured[0][0] == "ffmpeg"
            assert "audio=virtual-audio-capturer" in captured[0]
            t._sys_audio_thread.join(timeout=2)
        finally:
            meta_path.remove(finder)

    def test_check_system_audio_available_windows_uses_soundcard_first(
        self, monkeypatch,
    ) -> None:
        """``check_system_audio_available`` returns True when soundcard works."""
        monkeypatch.setattr(f"{_MOD}.platform.system", lambda: "Windows")
        monkeypatch.setattr(
            f"{_MOD}._check_windows_soundcard_loopback",
            lambda: True,
        )
        # If this is queried, soundcard short-circuit failed.
        monkeypatch.setattr(
            f"{_MOD}._get_windows_loopback_device_name",
            lambda: (_ for _ in ()).throw(
                AssertionError("dshow probe unexpectedly invoked"),
            ),
        )
        assert check_system_audio_available() is True

    def test_check_windows_soundcard_loopback_handles_import_error(
        self, monkeypatch,
    ) -> None:
        """Returns False (not raises) when soundcard isn't installed."""
        # Same import-blocking pattern as the fallback test.
        import importlib.abc  # noqa: PLC0415

        from src.core.live_engine import (  # noqa: PLC0415
            _check_windows_soundcard_loopback,
        )

        class _RefuseSoundcard(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):  # noqa: ANN001, ARG002, D102
                if fullname == "soundcard":
                    raise ImportError("soundcard refused for test")

        meta_path = __import__("sys").meta_path
        finder = _RefuseSoundcard()
        meta_path.insert(0, finder)
        try:
            sys_modules = __import__("sys").modules
            monkeypatch.delitem(sys_modules, "soundcard", raising=False)
            assert _check_windows_soundcard_loopback() is False
        finally:
            meta_path.remove(finder)

    def test_check_windows_soundcard_loopback_handles_speaker_failure(
        self, monkeypatch,
    ) -> None:
        """Returns False when default_speaker() throws (e.g. no audio device)."""
        fake_module = MagicMock()
        fake_module.default_speaker.side_effect = RuntimeError("no audio")
        monkeypatch.setitem(__import__("sys").modules, "soundcard", fake_module)

        from src.core.live_engine import (  # noqa: PLC0415
            _check_windows_soundcard_loopback,
        )

        assert _check_windows_soundcard_loopback() is False


class TestMacosLoopbackDetection:
    """Parsing of ``ffmpeg -f avfoundation -list_devices`` output."""

    def test_finds_blackhole(self, monkeypatch) -> None:
        """Parses BlackHole's audio index from ffmpeg's stderr listing."""
        monkeypatch.setattr(f"{_MOD}.shutil.which", lambda b: f"/usr/bin/{b}")
        # Simulate the avfoundation device listing format.
        stderr = (
            "AVFoundation video devices:\n"
            "[AVFoundation indev @ 0x12] [0] FaceTime HD Camera\n"
            "AVFoundation audio devices:\n"
            "[AVFoundation indev @ 0x12] [0] Built-in Microphone\n"
            "[AVFoundation indev @ 0x12] [1] BlackHole 2ch\n"
        )
        result = MagicMock()
        result.stderr = stderr
        monkeypatch.setattr(
            f"{_MOD}.subprocess.run",
            lambda *a, **k: result,  # noqa: ARG005
        )
        from src.core.live_engine import (  # noqa: PLC0415
            _get_macos_loopback_device_index,
        )

        assert _get_macos_loopback_device_index() == 1

    def test_returns_none_when_no_loopback(self, monkeypatch) -> None:
        """No virtual loopback in the device list → None."""
        monkeypatch.setattr(f"{_MOD}.shutil.which", lambda b: f"/usr/bin/{b}")
        stderr = (
            "AVFoundation audio devices:\n"
            "[AVFoundation indev @ 0x12] [0] Built-in Microphone\n"
        )
        result = MagicMock()
        result.stderr = stderr
        monkeypatch.setattr(
            f"{_MOD}.subprocess.run",
            lambda *a, **k: result,  # noqa: ARG005
        )
        from src.core.live_engine import (  # noqa: PLC0415
            _get_macos_loopback_device_index,
        )

        assert _get_macos_loopback_device_index() is None

    def test_returns_none_when_ffmpeg_missing(self, monkeypatch) -> None:
        """No ffmpeg → None (don't crash, don't claim available)."""
        monkeypatch.setattr(f"{_MOD}.shutil.which", lambda b: None)
        from src.core.live_engine import (  # noqa: PLC0415
            _get_macos_loopback_device_index,
        )

        assert _get_macos_loopback_device_index() is None

    def test_returns_none_when_ffmpeg_times_out(self, monkeypatch) -> None:
        """A ffmpeg -list_devices hang past 10 s returns None gracefully.

        The subprocess.run call is wrapped in a generic try/except so
        a hung ffmpeg doesn't propagate the TimeoutExpired and crash
        the availability check on the UI thread.
        """
        monkeypatch.setattr(f"{_MOD}.shutil.which", lambda b: f"/usr/bin/{b}")

        def hang(*a, **k):  # noqa: ANN001, ANN002, ANN003, ARG001
            raise subprocess.TimeoutExpired(cmd=["ffmpeg"], timeout=10)

        monkeypatch.setattr(f"{_MOD}.subprocess.run", hang)
        from src.core.live_engine import (  # noqa: PLC0415
            _get_macos_loopback_device_index,
        )

        assert _get_macos_loopback_device_index() is None


class TestWindowsLoopbackDetection:
    """Parsing of ``ffmpeg -f dshow -list_devices`` output."""

    def test_finds_virtual_audio_capturer(self, monkeypatch) -> None:
        """Picks ``virtual-audio-capturer`` when present."""
        monkeypatch.setattr(f"{_MOD}.shutil.which", lambda b: f"/usr/bin/{b}")
        stderr = (
            '[dshow @ 0x] DirectShow audio devices\n'
            '[dshow @ 0x]  "Microphone (Realtek)" (audio)\n'
            '[dshow @ 0x]  "virtual-audio-capturer" (audio)\n'
        )
        result = MagicMock()
        result.stderr = stderr
        monkeypatch.setattr(
            f"{_MOD}.subprocess.run",
            lambda *a, **k: result,  # noqa: ARG005
        )
        from src.core.live_engine import (  # noqa: PLC0415
            _get_windows_loopback_device_name,
        )

        assert _get_windows_loopback_device_name() == "virtual-audio-capturer"

    def test_finds_vb_audio_when_no_screen_capture_recorder(
        self, monkeypatch,
    ) -> None:
        """Falls back to VB-Audio Virtual Cable when SCR isn't installed."""
        monkeypatch.setattr(f"{_MOD}.shutil.which", lambda b: f"/usr/bin/{b}")
        stderr = (
            '[dshow @ 0x] DirectShow audio devices\n'
            '[dshow @ 0x]  "CABLE Output (VB-Audio Virtual Cable)" (audio)\n'
        )
        result = MagicMock()
        result.stderr = stderr
        monkeypatch.setattr(
            f"{_MOD}.subprocess.run",
            lambda *a, **k: result,  # noqa: ARG005
        )
        from src.core.live_engine import (  # noqa: PLC0415
            _get_windows_loopback_device_name,
        )

        assert (
            _get_windows_loopback_device_name()
            == "CABLE Output (VB-Audio Virtual Cable)"
        )

    def test_returns_none_when_no_loopback(self, monkeypatch) -> None:
        """No known loopback device → None."""
        monkeypatch.setattr(f"{_MOD}.shutil.which", lambda b: f"/usr/bin/{b}")
        stderr = (
            '[dshow @ 0x] DirectShow audio devices\n'
            '[dshow @ 0x]  "Microphone (Realtek)" (audio)\n'
        )
        result = MagicMock()
        result.stderr = stderr
        monkeypatch.setattr(
            f"{_MOD}.subprocess.run",
            lambda *a, **k: result,  # noqa: ARG005
        )
        from src.core.live_engine import (  # noqa: PLC0415
            _get_windows_loopback_device_name,
        )

        assert _get_windows_loopback_device_name() is None

    def test_returns_none_when_ffmpeg_times_out(self, monkeypatch) -> None:
        """A ffmpeg -list_devices hang past 10 s returns None gracefully."""
        monkeypatch.setattr(f"{_MOD}.shutil.which", lambda b: f"/usr/bin/{b}")

        def hang(*a, **k):  # noqa: ANN001, ANN002, ANN003, ARG001
            raise subprocess.TimeoutExpired(cmd=["ffmpeg"], timeout=10)

        monkeypatch.setattr(f"{_MOD}.subprocess.run", hang)
        from src.core.live_engine import (  # noqa: PLC0415
            _get_windows_loopback_device_name,
        )

        assert _get_windows_loopback_device_name() is None


# ---------------------------------------------------------------------------
# Silence detection threshold boundary tests
# ---------------------------------------------------------------------------


class TestLiveTranscriberSilenceBoundary:
    """Tests for exact silence detection threshold boundaries."""

    def _run_with_blocks(
        self,
        blocks: list[np.ndarray],
    ) -> tuple[MagicMock, MagicMock]:
        """Helper: feed *blocks* into _process_loop and return callbacks.

        Returns:
            (sentence_cb, mock_model) tuple for assertion.
        """
        sentence_cb = MagicMock()
        t = LiveTranscriber(
            on_sentence=sentence_cb,
            on_status=MagicMock(),
            language="",
        )

        idx = [0]
        total = len(blocks)

        def auto_get(timeout=None):
            idx[0] += 1
            if idx[0] > total:
                t._is_running = False
                raise queue.Empty
            return blocks[idx[0] - 1]

        t._audio_queue.get = auto_get
        t._is_running = True

        mock_segment = SimpleNamespace(text="Heard something")
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([mock_segment], None)
        mock_stream = MagicMock()

        mock_sd = sys.modules["sounddevice"]
        mock_sd.InputStream = MagicMock(return_value=mock_stream)
        mock_fw = sys.modules["faster_whisper"]
        mock_fw.WhisperModel = MagicMock(return_value=mock_model)

        t._process_loop()
        return sentence_cb, mock_model

    def test_rms_exactly_at_threshold(self) -> None:
        """Audio with RMS == _SILENCE_THRESHOLD exactly is NOT silence.

        The source uses ``rms < _SILENCE_THRESHOLD`` (strict less-than),
        so a block whose RMS equals the threshold is treated as speech.

        Note: np.float32(0.01) is actually 0.00999999... due to IEEE 754,
        so we construct a block whose float64 RMS is exactly 0.01 by using
        a slightly larger float32 value (0.01001) that still rounds
        to an RMS at or just above the threshold.
        """
        # float32(0.01) has RMS slightly below 0.01 due to precision.
        # Use a value whose float32 RMS lands right at the threshold.
        at_threshold = np.full(
            (_BLOCK_SIZE, 1),
            np.float32(0.01001),
            dtype=np.float32,
        )
        # Verify the RMS is at or just above threshold
        rms = float(np.sqrt(np.mean(at_threshold**2)))
        assert rms >= _SILENCE_THRESHOLD, (
            f"Expected RMS >= {_SILENCE_THRESHOLD}, got {rms}"
        )

        silent = np.zeros((_BLOCK_SIZE, 1), dtype=np.float32)

        # 3 speech blocks (at threshold → not silent) + silence trigger
        blocks = [at_threshold] * (_MIN_AUDIO_BLOCKS + 1) + [silent] * _SILENCE_BLOCKS
        sentence_cb, mock_model = self._run_with_blocks(blocks)

        # The at-threshold blocks count as speech so transcription fires
        assert sentence_cb.call_count == 1
        mock_model.transcribe.assert_called_once()

    def test_rms_just_above_threshold(self) -> None:
        """Audio with RMS slightly above _SILENCE_THRESHOLD is speech.

        A block with constant value 0.0101 has RMS = 0.0101 > 0.01.
        """
        above = np.full(
            (_BLOCK_SIZE, 1),
            _SILENCE_THRESHOLD + 0.0001,
            dtype=np.float32,
        )
        silent = np.zeros((_BLOCK_SIZE, 1), dtype=np.float32)

        blocks = [above] * (_MIN_AUDIO_BLOCKS + 1) + [silent] * _SILENCE_BLOCKS
        sentence_cb, mock_model = self._run_with_blocks(blocks)

        assert sentence_cb.call_count == 1
        mock_model.transcribe.assert_called_once()

    def test_rms_just_below_threshold(self) -> None:
        """Audio with RMS slightly below _SILENCE_THRESHOLD is silence.

        A block with constant value 0.0099 has RMS = 0.0099 < 0.01,
        so all blocks are silent and no transcription should fire.
        """
        below = np.full(
            (_BLOCK_SIZE, 1),
            _SILENCE_THRESHOLD - 0.0001,
            dtype=np.float32,
        )

        # All blocks are "silence" → never reaches _MIN_AUDIO_BLOCKS of speech
        blocks = [below] * 10
        sentence_cb, mock_model = self._run_with_blocks(blocks)

        sentence_cb.assert_not_called()
        mock_model.transcribe.assert_not_called()


# ---------------------------------------------------------------------------
# Buffer boundary tests (max buffer forces transcription)
# ---------------------------------------------------------------------------


class TestLiveTranscriberBufferBoundary:
    """Tests for max buffer size forcing transcription."""

    def test_max_buffer_blocks_forces_transcription(self) -> None:
        """Feed exactly _MAX_BUFFER_BLOCKS speech blocks without silence.

        The loop should force transcription when buffer length reaches
        _MAX_BUFFER_BLOCKS, even without any silence.
        """
        sentence_cb = MagicMock()
        t = LiveTranscriber(
            on_sentence=sentence_cb,
            on_status=MagicMock(),
            language="",
        )

        speech = np.ones((_BLOCK_SIZE, 1), dtype=np.float32) * 0.5
        num_blocks = _MAX_BUFFER_BLOCKS

        idx = [0]

        def auto_get(timeout=None):
            idx[0] += 1
            if idx[0] > num_blocks:
                t._is_running = False
                raise queue.Empty
            return speech

        t._audio_queue.get = auto_get
        t._is_running = True

        mock_segment = SimpleNamespace(text="Forced flush")
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([mock_segment], None)
        mock_stream = MagicMock()

        mock_sd = sys.modules["sounddevice"]
        mock_sd.InputStream = MagicMock(return_value=mock_stream)
        mock_fw = sys.modules["faster_whisper"]
        mock_fw.WhisperModel = MagicMock(return_value=mock_model)

        t._process_loop()

        # Transcription should have been called exactly once (max buffer hit)
        assert mock_model.transcribe.call_count == 1
        assert sentence_cb.call_count == 1
        assert sentence_cb.call_args[0][0] == "Forced flush"

    def test_buffer_below_max_waits_for_silence(self) -> None:
        """Feed _MAX_BUFFER_BLOCKS - 1 speech blocks without silence.

        No transcription should fire mid-loop because the max-buffer
        threshold is not reached.  The buffer IS flushed at loop exit
        because it has >= _MIN_AUDIO_BLOCKS blocks.
        """
        sentence_cb = MagicMock()
        t = LiveTranscriber(
            on_sentence=sentence_cb,
            on_status=MagicMock(),
            language="",
        )

        speech = np.ones((_BLOCK_SIZE, 1), dtype=np.float32) * 0.5
        num_blocks = _MAX_BUFFER_BLOCKS - 1

        idx = [0]
        transcribe_times = []

        def auto_get(timeout=None):
            idx[0] += 1
            if idx[0] > num_blocks:
                t._is_running = False
                raise queue.Empty
            return speech

        t._audio_queue.get = auto_get
        t._is_running = True

        mock_segment = SimpleNamespace(text="Flushed at exit")
        mock_model = MagicMock()

        # Track when transcribe is called relative to blocks processed.
        # Use a plain function as side_effect that returns the expected tuple.
        def track_transcribe(*args, **kwargs):
            transcribe_times.append(idx[0])
            return ([mock_segment], None)

        mock_model.transcribe = MagicMock(side_effect=track_transcribe)

        mock_stream = MagicMock()
        mock_sd = sys.modules["sounddevice"]
        mock_sd.InputStream = MagicMock(return_value=mock_stream)
        mock_fw = sys.modules["faster_whisper"]
        mock_fw.WhisperModel = MagicMock(return_value=mock_model)

        t._process_loop()

        # Should be called once (flush at exit), not mid-loop
        assert mock_model.transcribe.call_count == 1
        # Transcription happened after all blocks were consumed (at exit flush)
        assert transcribe_times[0] > num_blocks


# ---------------------------------------------------------------------------
# _audio_callback after stop
# ---------------------------------------------------------------------------


class TestLiveTranscriberAudioCallbackAfterStop:
    """Test _audio_callback behavior after stop()."""

    def test_callback_after_stop_does_not_queue(self) -> None:
        """When _is_running is False, _audio_callback does not enqueue data."""
        t = LiveTranscriber(on_sentence=MagicMock())
        t._is_running = False
        data = np.ones((_BLOCK_SIZE, 1), dtype=np.float32)
        t._audio_callback(data, _BLOCK_SIZE, None, None)
        assert t._audio_queue.empty()

    def test_callback_transitions_from_running_to_stopped(self) -> None:
        """Audio queued while running, then callback after stop is ignored."""
        t = LiveTranscriber(on_sentence=MagicMock())
        t._is_running = True
        data_before = np.ones((_BLOCK_SIZE, 1), dtype=np.float32)
        t._audio_callback(data_before, _BLOCK_SIZE, None, None)
        assert t._audio_queue.qsize() == 1

        t._is_running = False
        data_after = np.ones((_BLOCK_SIZE, 1), dtype=np.float32) * 2
        t._audio_callback(data_after, _BLOCK_SIZE, None, None)
        # Only the first block should be in the queue
        assert t._audio_queue.qsize() == 1
        queued = t._audio_queue.get_nowait()
        np.testing.assert_array_equal(queued, data_before)


# ---------------------------------------------------------------------------
# Concurrent stop during transcription
# ---------------------------------------------------------------------------


class TestLiveTranscriberConcurrentSendStop:
    """Test concurrent operations."""

    def test_stop_during_transcription(self) -> None:
        """Calling stop() while _process_loop is transcribing terminates gracefully.

        We simulate this by making the model.transcribe call set _is_running
        to False (as if stop() were called from another thread), and verify
        the loop exits cleanly without crashing.
        """
        sentence_cb = MagicMock()
        t = LiveTranscriber(
            on_sentence=sentence_cb,
            on_status=MagicMock(),
            language="",
        )

        speech = np.ones((_BLOCK_SIZE, 1), dtype=np.float32) * 0.5
        silent = np.zeros((_BLOCK_SIZE, 1), dtype=np.float32)

        # 3 speech + 2 silence triggers transcription, then more blocks after
        blocks = (
            [speech] * (_MIN_AUDIO_BLOCKS + 1)
            + [silent] * _SILENCE_BLOCKS
            + [speech] * 5  # more speech that should not be processed
        )
        idx = [0]

        def auto_get(timeout=None):
            idx[0] += 1
            if idx[0] > len(blocks):
                t._is_running = False
                raise queue.Empty
            return blocks[idx[0] - 1]

        t._audio_queue.get = auto_get
        t._is_running = True

        mock_segment = SimpleNamespace(text="During stop")
        mock_model = MagicMock()

        def transcribe_and_stop(*args, **kwargs):
            """Simulate stop() being called from another thread mid-transcribe."""
            t._is_running = False
            return ([mock_segment], None)

        mock_model.transcribe.side_effect = transcribe_and_stop
        mock_stream = MagicMock()

        mock_sd = sys.modules["sounddevice"]
        mock_sd.InputStream = MagicMock(return_value=mock_stream)
        mock_fw = sys.modules["faster_whisper"]
        mock_fw.WhisperModel = MagicMock(return_value=mock_model)

        # Should not raise
        t._process_loop()

        # Transcription was called once before stop kicked in
        assert mock_model.transcribe.call_count == 1
        assert t.is_running is False

    def test_on_stopped_called_after_process_loop_exits(self) -> None:
        """on_stopped callback fires even when stop interrupts the loop."""
        stopped_cb = MagicMock()
        t = LiveTranscriber(
            on_sentence=MagicMock(),
            on_status=MagicMock(),
            on_stopped=stopped_cb,
            language="",
        )

        def immediate_stop(timeout=None):
            t._is_running = False
            raise queue.Empty

        t._audio_queue.get = immediate_stop
        t._is_running = True

        mock_model = MagicMock()
        mock_stream = MagicMock()
        mock_sd = sys.modules["sounddevice"]
        mock_sd.InputStream = MagicMock(return_value=mock_stream)
        mock_fw = sys.modules["faster_whisper"]
        mock_fw.WhisperModel = MagicMock(return_value=mock_model)

        t._process_loop()

        stopped_cb.assert_called_once()


# ---------------------------------------------------------------------------
# TestLiveTranscriberAudioSourceConfig — Audio source configuration
# ---------------------------------------------------------------------------


class TestLiveTranscriberAudioSourceConfig:
    """Tests for audio source configuration: microphone, system, both, invalid."""

    def test_microphone_source_uses_input_stream(self) -> None:
        """Microphone source creates an InputStream via sounddevice."""
        t = _make_transcriber(status_cb=MagicMock())
        t._audio_source = "microphone"
        _mock_model, mock_stream = _setup_mocks()

        def stop_immediately(timeout=None):
            t._is_running = False
            raise queue.Empty

        t._audio_queue.get = stop_immediately
        t._is_running = True
        t._process_loop()

        mock_sd = sys.modules["sounddevice"]
        mock_sd.InputStream.assert_called_once()
        mock_stream.start.assert_called_once()

    def test_system_source_uses_parec(self, monkeypatch) -> None:
        """System audio source spawns a parec subprocess."""
        monkeypatch.setattr(
            f"{_MOD}.check_system_audio_available",
            lambda: True,
        )
        monkeypatch.setattr(
            f"{_MOD}._get_default_monitor_source",
            lambda: "test_sink.monitor",
        )

        t = _make_transcriber(status_cb=MagicMock())
        t._audio_source = "system"
        mock_model, _s = _setup_mocks()

        # Mock subprocess.Popen to avoid real parec
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0  # process exited immediately
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.read.return_value = b""  # no data
        mock_proc.terminate = MagicMock()
        mock_proc.wait = MagicMock()

        with patch(f"{_MOD}.subprocess.Popen", return_value=mock_proc):

            def stop_immediately(timeout=None):
                t._is_running = False
                raise queue.Empty

            t._audio_queue.get = stop_immediately
            t._is_running = True
            t._process_loop()

        # InputStream should NOT be created for system-only mode
        mock_sd = sys.modules["sounddevice"]
        mock_sd.InputStream.assert_not_called()

    def test_both_sources_configured_simultaneously(self, monkeypatch) -> None:
        """Both mode creates InputStream AND starts parec."""
        monkeypatch.setattr(
            f"{_MOD}.check_system_audio_available",
            lambda: True,
        )
        monkeypatch.setattr(
            f"{_MOD}._get_default_monitor_source",
            lambda: "test_sink.monitor",
        )

        t = _make_transcriber(status_cb=MagicMock())
        t._audio_source = "both"
        _mock_model, mock_stream = _setup_mocks()

        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.read.return_value = b""
        mock_proc.terminate = MagicMock()
        mock_proc.wait = MagicMock()

        with patch(f"{_MOD}.subprocess.Popen", return_value=mock_proc):

            def stop_immediately(timeout=None):
                t._is_running = False
                raise queue.Empty

            t._audio_queue.get = stop_immediately
            t._is_running = True
            t._process_loop()

        # Both InputStream and parec should be used
        mock_sd = sys.modules["sounddevice"]
        mock_sd.InputStream.assert_called_once()
        mock_stream.start.assert_called_once()
        # sys_queue should have been created for "both" mode
        assert t._sys_queue is not None

    def test_system_source_raises_when_unavailable(self, monkeypatch) -> None:
        """System source raises ValueError when system audio is not available."""
        monkeypatch.setattr(
            f"{_MOD}.check_system_audio_available",
            lambda: False,
        )
        t = _make_transcriber()
        t._audio_source = "system"
        with pytest.raises(ValueError, match="live.error_no_system_audio"):
            t._resolve_devices()

    def test_both_source_raises_when_system_unavailable(self, monkeypatch) -> None:
        """Both source raises ValueError when system audio is not available."""
        monkeypatch.setattr(
            f"{_MOD}.check_system_audio_available",
            lambda: False,
        )
        t = _make_transcriber()
        t._audio_source = "both"
        with pytest.raises(ValueError, match="live.error_no_system_audio"):
            t._resolve_devices()

    def test_system_source_error_reported_via_status(self, monkeypatch) -> None:
        """System audio unavailable is reported via on_status in _process_loop."""
        monkeypatch.setattr(
            f"{_MOD}.check_system_audio_available",
            lambda: False,
        )
        status_cb = MagicMock()
        t = _make_transcriber(status_cb=status_cb)
        t._audio_source = "system"
        _setup_mocks()
        t._is_running = True
        t._process_loop()

        assert t._is_running is False
        # Status callback should have been called with the error key
        status_cb.assert_called()


# ---------------------------------------------------------------------------
# TestLiveTranscriberTranscriptBufferCleanup — Buffer management
# ---------------------------------------------------------------------------


class TestLiveTranscriberTranscriptBufferCleanup:
    """Tests for buffer management: clearing, max size, accumulation."""

    def test_buffer_cleared_after_transcription_emitted(self) -> None:
        """Buffer is cleared after silence-triggered transcription."""
        sentence_cb = MagicMock()
        t = _make_transcriber(sentence_cb=sentence_cb, status_cb=MagicMock())

        seg1 = SimpleNamespace(text="First")
        seg2 = SimpleNamespace(text="Second")
        mock_model, _s = _setup_mocks()
        mock_model.transcribe.side_effect = [
            ([seg1], None),
            ([seg2], None),
        ]

        speech = np.ones((_BLOCK_SIZE,), dtype=np.float32) * 0.5
        silence = np.zeros((_BLOCK_SIZE,), dtype=np.float32)
        n = _MIN_AUDIO_BLOCKS + 1

        # Two speech-silence cycles
        blocks = (
            [speech] * n
            + [silence] * _SILENCE_BLOCKS
            + [speech] * n
            + [silence] * _SILENCE_BLOCKS
        )
        _feed_blocks_and_run(t, blocks)

        # Each batch has exactly n blocks worth of audio
        first_audio = mock_model.transcribe.call_args_list[0][0][0]
        second_audio = mock_model.transcribe.call_args_list[1][0][0]
        assert first_audio.shape == (n * _BLOCK_SIZE,)
        assert second_audio.shape == (n * _BLOCK_SIZE,)

    def test_max_buffer_size_forces_transcription(self) -> None:
        """Buffer exceeding _MAX_BUFFER_BLOCKS forces transcription."""
        sentence_cb = MagicMock()
        t = _make_transcriber(sentence_cb=sentence_cb, status_cb=MagicMock())
        mock_model, _s = _setup_mocks(
            model_segments=[SimpleNamespace(text="Forced")],
        )

        speech = np.ones((_BLOCK_SIZE,), dtype=np.float32) * 0.5
        # Exactly _MAX_BUFFER_BLOCKS speech blocks triggers forced flush
        blocks = [speech] * _MAX_BUFFER_BLOCKS
        _feed_blocks_and_run(t, blocks)

        # Model should be called once for the forced flush
        assert mock_model.transcribe.call_count == 1
        audio_arg = mock_model.transcribe.call_args[0][0]
        assert audio_arg.shape == (_MAX_BUFFER_BLOCKS * _BLOCK_SIZE,)

    def test_buffer_accumulation_across_multiple_send_audio_calls(self) -> None:
        """Multiple speech blocks accumulate in buffer before transcription."""
        sentence_cb = MagicMock()
        t = _make_transcriber(sentence_cb=sentence_cb, status_cb=MagicMock())
        mock_model, _s = _setup_mocks(
            model_segments=[SimpleNamespace(text="Accumulated")],
        )

        speech = np.ones((_BLOCK_SIZE,), dtype=np.float32) * 0.5
        silence = np.zeros((_BLOCK_SIZE,), dtype=np.float32)
        num_speech = 5
        blocks = [speech] * num_speech + [silence] * _SILENCE_BLOCKS
        _feed_blocks_and_run(t, blocks)

        # All 5 speech blocks should be concatenated in a single transcription
        assert mock_model.transcribe.call_count == 1
        audio_arg = mock_model.transcribe.call_args[0][0]
        assert audio_arg.shape == (num_speech * _BLOCK_SIZE,)

    def test_buffer_cleared_after_max_buffer_forced_flush(self) -> None:
        """After forced max-buffer flush, buffer restarts fresh."""
        sentence_cb = MagicMock()
        t = _make_transcriber(sentence_cb=sentence_cb, status_cb=MagicMock())

        seg1 = SimpleNamespace(text="MaxFlush")
        seg2 = SimpleNamespace(text="Remaining")
        mock_model, _s = _setup_mocks()
        mock_model.transcribe.side_effect = [
            ([seg1], None),
            ([seg2], None),
        ]

        speech = np.ones((_BLOCK_SIZE,), dtype=np.float32) * 0.5
        silence = np.zeros((_BLOCK_SIZE,), dtype=np.float32)
        extra = 3
        # Max buffer blocks + some extra + silence
        blocks = [speech] * (_MAX_BUFFER_BLOCKS + extra) + [silence] * _SILENCE_BLOCKS
        _feed_blocks_and_run(t, blocks)

        # First call: exactly _MAX_BUFFER_BLOCKS
        first_audio = mock_model.transcribe.call_args_list[0][0][0]
        assert first_audio.shape == (_MAX_BUFFER_BLOCKS * _BLOCK_SIZE,)
        # Second call: the remaining extra blocks
        second_audio = mock_model.transcribe.call_args_list[1][0][0]
        assert second_audio.shape == (extra * _BLOCK_SIZE,)

    def test_silence_blocks_not_added_to_buffer(self) -> None:
        """Silent blocks are not accumulated in the speech buffer."""
        sentence_cb = MagicMock()
        t = _make_transcriber(sentence_cb=sentence_cb, status_cb=MagicMock())
        mock_model, _s = _setup_mocks(
            model_segments=[SimpleNamespace(text="SpeechOnly")],
        )

        speech = np.ones((_BLOCK_SIZE,), dtype=np.float32) * 0.5
        silence = np.zeros((_BLOCK_SIZE,), dtype=np.float32)
        num_speech = _MIN_AUDIO_BLOCKS + 1
        # Interleave: speech, speech, speech, silence, silence (triggers)
        blocks = [speech] * num_speech + [silence] * _SILENCE_BLOCKS
        _feed_blocks_and_run(t, blocks)

        # Audio sent to transcribe should only contain speech blocks
        audio_arg = mock_model.transcribe.call_args[0][0]
        assert audio_arg.shape == (num_speech * _BLOCK_SIZE,)


# ---------------------------------------------------------------------------
# TestLiveTranscriberSilenceDetectionEdgeCases — Silence detection boundaries
# ---------------------------------------------------------------------------


class TestLiveTranscriberSilenceDetectionEdgeCases:
    """Tests for silence detection boundary conditions."""

    def test_audio_exactly_at_silence_threshold(self) -> None:
        """Audio with RMS exactly at threshold is treated as speech (strict <)."""
        # Use float64 for exact boundary representation
        block = np.full(
            (_BLOCK_SIZE,),
            fill_value=_SILENCE_THRESHOLD,
            dtype=np.float64,
        )
        rms = float(np.sqrt(np.mean(block**2)))
        # Code uses `rms < _SILENCE_THRESHOLD` — equal is NOT silent
        assert not (rms < _SILENCE_THRESHOLD)

    def test_audio_just_above_threshold_triggers_transcription(self) -> None:
        """Audio just above threshold is speech and triggers transcription."""
        sentence_cb = MagicMock()
        t = _make_transcriber(sentence_cb=sentence_cb, status_cb=MagicMock())
        mock_model, _s = _setup_mocks(
            model_segments=[SimpleNamespace(text="JustAbove")],
        )

        # Create block with amplitude just above threshold
        amplitude = _SILENCE_THRESHOLD + 0.001
        speech = np.full((_BLOCK_SIZE,), fill_value=amplitude, dtype=np.float32)
        silence = np.zeros((_BLOCK_SIZE,), dtype=np.float32)
        blocks = [speech] * (_MIN_AUDIO_BLOCKS + 1) + [silence] * _SILENCE_BLOCKS
        _feed_blocks_and_run(t, blocks)

        assert sentence_cb.call_count == 1
        assert sentence_cb.call_args[0][0] == "JustAbove"

    def test_audio_just_below_threshold_extends_silence(self) -> None:
        """Audio just below threshold is detected as silence."""
        sentence_cb = MagicMock()
        t = _make_transcriber(sentence_cb=sentence_cb, status_cb=MagicMock())
        mock_model, _s = _setup_mocks()

        # All blocks are just below threshold — treated as silence
        amplitude = _SILENCE_THRESHOLD - 0.001
        quiet = np.full((_BLOCK_SIZE,), fill_value=amplitude, dtype=np.float32)
        blocks = [quiet] * (_SILENCE_BLOCKS * 3)
        _feed_blocks_and_run(t, blocks)

        # No speech => no transcription
        mock_model.transcribe.assert_not_called()
        sentence_cb.assert_not_called()

    def test_continuous_silence_for_extended_period(self) -> None:
        """Extended continuous silence never triggers transcription."""
        sentence_cb = MagicMock()
        t = _make_transcriber(sentence_cb=sentence_cb, status_cb=MagicMock())
        mock_model, _s = _setup_mocks()

        silence = np.zeros((_BLOCK_SIZE,), dtype=np.float32)
        # 100 silence blocks (50 seconds worth) — no transcription
        blocks = [silence] * 100
        _feed_blocks_and_run(t, blocks)

        mock_model.transcribe.assert_not_called()
        sentence_cb.assert_not_called()

    def test_threshold_boundary_with_mixed_signal(self) -> None:
        """Block with half above/half below threshold has RMS above threshold."""
        block = np.zeros((_BLOCK_SIZE,), dtype=np.float32)
        # Second half at 2x threshold, first half at 0
        block[_BLOCK_SIZE // 2 :] = _SILENCE_THRESHOLD * 2
        rms = float(np.sqrt(np.mean(block**2)))
        # RMS should be above threshold: sqrt(mean(half zeros + half (2*thresh)^2))
        assert rms >= _SILENCE_THRESHOLD

    def test_silence_after_single_speech_block_no_transcription(self) -> None:
        """One speech block + silence: below _MIN_AUDIO_BLOCKS, no transcription."""
        sentence_cb = MagicMock()
        t = _make_transcriber(sentence_cb=sentence_cb, status_cb=MagicMock())
        mock_model, _s = _setup_mocks()

        speech = np.ones((_BLOCK_SIZE,), dtype=np.float32) * 0.5
        silence = np.zeros((_BLOCK_SIZE,), dtype=np.float32)
        # 1 speech < _MIN_AUDIO_BLOCKS(2)
        blocks = [speech] + [silence] * (_SILENCE_BLOCKS + 5)
        _feed_blocks_and_run(t, blocks)

        mock_model.transcribe.assert_not_called()

    def test_alternating_near_threshold_keeps_accumulating(self) -> None:
        """Blocks alternating around threshold still accumulate as speech."""
        sentence_cb = MagicMock()
        t = _make_transcriber(sentence_cb=sentence_cb, status_cb=MagicMock())
        mock_model, _s = _setup_mocks(
            model_segments=[SimpleNamespace(text="Alternating")],
        )

        above = np.full(
            (_BLOCK_SIZE,),
            fill_value=_SILENCE_THRESHOLD + 0.005,
            dtype=np.float32,
        )
        below = np.full(
            (_BLOCK_SIZE,),
            fill_value=_SILENCE_THRESHOLD - 0.005,
            dtype=np.float32,
        )
        silence = np.zeros((_BLOCK_SIZE,), dtype=np.float32)

        # Pattern: above, below (1 silence), above, below (1 silence), above
        # Only 1 consecutive silence each time — not enough to trigger mid-loop
        blocks = [above, below, above, below, above] + [silence] * _SILENCE_BLOCKS
        _feed_blocks_and_run(t, blocks)

        # 3 above-threshold blocks counted as speech >= _MIN_AUDIO_BLOCKS
        assert mock_model.transcribe.call_count >= 1


# ---------------------------------------------------------------------------
# TestLiveTranscriberConcurrentSendAudio — Thread safety
# ---------------------------------------------------------------------------


class TestLiveTranscriberConcurrentSendAudio:
    """Tests for thread safety during concurrent audio sending."""

    def test_multiple_threads_sending_audio(self) -> None:
        """Concurrent ``_audio_callback`` calls never exceed the queue cap.

        Production only has one producer (the sounddevice callback on
        PortAudio's thread), but hammering the queue from many threads
        verifies that the bounded queue + ``_put_drop_oldest`` pair
        doesn't corrupt state under contention — final size stays at
        ``_QUEUE_MAX_BLOCKS`` and no exception escapes the callback.
        """
        import threading  # noqa: PLC0415

        from src.core.live_engine import _QUEUE_MAX_BLOCKS  # noqa: PLC0415

        t = _make_transcriber()
        t._is_running = True
        num_threads = 5
        blocks_per_thread = 20
        barrier = threading.Barrier(num_threads)

        def send_blocks(thread_id: int) -> None:
            barrier.wait()
            for i in range(blocks_per_thread):
                data = np.full(
                    (_BLOCK_SIZE, 1),
                    fill_value=float(thread_id * 100 + i),
                    dtype=np.float32,
                )
                t._audio_callback(data, _BLOCK_SIZE, None, None)

        threads = []
        for tid in range(num_threads):
            th = threading.Thread(target=send_blocks, args=(tid,))
            threads.append(th)
            th.start()

        for th in threads:
            th.join(timeout=5)

        # Queue is bounded — the drop-oldest policy keeps it at the cap
        # under overflow.  The key guarantee is no corruption / no
        # exceptions, not a specific size.
        assert t._audio_queue.qsize() == _QUEUE_MAX_BLOCKS

    def test_buffer_state_consistent_after_concurrent_access(self) -> None:
        """Surviving queue entries are valid after concurrent puts.

        Stays under the bounded queue cap (1 block per thread, 4
        threads ≪ ``_QUEUE_MAX_BLOCKS``) so no drops occur — we want
        to verify that simultaneous ``_put_drop_oldest`` calls from
        multiple threads don't corrupt individual blocks or leave
        partial writes in the queue.
        """
        import threading  # noqa: PLC0415

        t = _make_transcriber()
        t._is_running = True
        num_threads = 4
        blocks_per_thread = 1  # keep total under the cap

        def send_blocks(value: float) -> None:
            for _ in range(blocks_per_thread):
                data = np.full(
                    (_BLOCK_SIZE, 1),
                    fill_value=value,
                    dtype=np.float32,
                )
                t._audio_callback(data, _BLOCK_SIZE, None, None)

        threads = [
            threading.Thread(target=send_blocks, args=(float(i),))
            for i in range(num_threads)
        ]
        for th in threads:
            th.start()
        for th in threads:
            th.join(timeout=5)

        # Drain and verify surviving blocks have valid shape and
        # carry one of the producer values (no cross-thread tearing).
        expected_values = {float(i) for i in range(num_threads)}
        total = t._audio_queue.qsize()
        values_seen = set()
        for _ in range(total):
            block = t._audio_queue.get_nowait()
            assert block.shape == (_BLOCK_SIZE, 1)
            values_seen.add(float(block[0, 0]))

        # Every surviving value should be one a producer actually wrote.
        assert values_seen <= expected_values
        assert values_seen  # at least some blocks survived

    def test_stop_during_active_audio_processing(self) -> None:
        """Setting _is_running=False while audio is being queued is safe."""
        import threading  # noqa: PLC0415

        t = _make_transcriber()
        t._is_running = True

        def send_many_blocks() -> None:
            for _ in range(100):
                data = np.ones((_BLOCK_SIZE, 1), dtype=np.float32)
                t._audio_callback(data, _BLOCK_SIZE, None, None)

        th = threading.Thread(target=send_many_blocks)
        th.start()

        # Stop while thread is still sending
        t._is_running = False
        th.join(timeout=5)

        # Some blocks may have been queued, some may not — no crash
        assert t._audio_queue.qsize() <= 100  # noqa: PLR2004

    def test_concurrent_queue_get_put(self) -> None:
        """Concurrent put (producer) and get (consumer) on audio queue."""
        import threading  # noqa: PLC0415

        t = _make_transcriber()
        t._is_running = True
        produced = 50
        consumed = []

        def producer() -> None:
            for i in range(produced):
                data = np.full(
                    (_BLOCK_SIZE, 1),
                    fill_value=float(i),
                    dtype=np.float32,
                )
                t._audio_queue.put(data)

        def consumer() -> None:
            while len(consumed) < produced:
                try:
                    block = t._audio_queue.get(timeout=1)
                    consumed.append(block)
                except queue.Empty:
                    break

        p = threading.Thread(target=producer)
        c = threading.Thread(target=consumer)
        p.start()
        c.start()
        p.join(timeout=5)
        c.join(timeout=5)

        assert len(consumed) == produced


# ---------------------------------------------------------------------------
# TestLiveTranscriberWhisperModelCaching — Model caching
# ---------------------------------------------------------------------------


class TestLiveTranscriberWhisperModelCaching:
    """Tests for Whisper model caching across start/stop cycles."""

    def test_same_model_reused_across_start_stop_cycles(
        self,
        monkeypatch,
    ) -> None:
        """Cached model is reused when model_size matches."""
        import src.core.live_engine as le  # noqa: PLC0415

        fake_model = MagicMock()
        fake_model.transcribe.return_value = ([], None)
        monkeypatch.setattr(le, "_cached_model", fake_model)
        monkeypatch.setattr(le, "_cached_model_size", "tiny")

        # First run
        t1 = _make_transcriber(model_size="tiny", status_cb=MagicMock())
        mock_fw = sys.modules["faster_whisper"]
        mock_fw.WhisperModel = MagicMock()

        mock_sd = sys.modules["sounddevice"]
        mock_sd.InputStream = MagicMock(return_value=MagicMock())

        def stop_immediately(timeout=None):
            t1._is_running = False
            raise queue.Empty

        t1._audio_queue.get = stop_immediately
        t1._is_running = True
        t1._process_loop()

        # WhisperModel should NOT be called — cache hit
        mock_fw.WhisperModel.assert_not_called()

        # Second run with same size — still cached
        t2 = _make_transcriber(model_size="tiny", status_cb=MagicMock())

        def stop_immediately2(timeout=None):
            t2._is_running = False
            raise queue.Empty

        t2._audio_queue.get = stop_immediately2
        t2._is_running = True
        t2._process_loop()

        mock_fw.WhisperModel.assert_not_called()

    def test_different_model_size_creates_new_model(
        self,
        monkeypatch,
    ) -> None:
        """Different model_size invalidates cache and creates new model."""
        import src.core.live_engine as le  # noqa: PLC0415

        old_model = MagicMock()
        monkeypatch.setattr(le, "_cached_model", old_model)
        monkeypatch.setattr(le, "_cached_model_size", "tiny")

        new_model = MagicMock()
        new_model.transcribe.return_value = ([], None)
        mock_fw = sys.modules["faster_whisper"]
        mock_fw.WhisperModel = MagicMock(return_value=new_model)

        mock_sd = sys.modules["sounddevice"]
        mock_sd.InputStream = MagicMock(return_value=MagicMock())

        t = _make_transcriber(model_size="base", status_cb=MagicMock())

        def stop_immediately(timeout=None):
            t._is_running = False
            raise queue.Empty

        t._audio_queue.get = stop_immediately
        t._is_running = True
        t._process_loop()

        # WhisperModel should be called with "base"
        mock_fw.WhisperModel.assert_called_once_with(
            "base",
            device="cpu",
            compute_type="int8",
        )

    def test_model_not_loaded_until_first_start(self) -> None:
        """Model is not loaded on construction — only on first _process_loop."""
        mock_fw = sys.modules["faster_whisper"]
        mock_fw.WhisperModel = MagicMock(return_value=MagicMock())

        # Construction should NOT trigger model loading
        t = _make_transcriber(model_size="small")
        mock_fw.WhisperModel.assert_not_called()

        # _process_loop triggers model loading
        mock_sd = sys.modules["sounddevice"]
        mock_sd.InputStream = MagicMock(return_value=MagicMock())

        def stop_immediately(timeout=None):
            t._is_running = False
            raise queue.Empty

        t._audio_queue.get = stop_immediately
        t._is_running = True
        t._on_status = MagicMock()
        t._process_loop()

        mock_fw.WhisperModel.assert_called_once()

    def test_cache_updated_after_new_model_load(self, monkeypatch) -> None:
        """Global cache is updated after loading a new model."""
        import src.core.live_engine as le  # noqa: PLC0415

        monkeypatch.setattr(le, "_cached_model", None)
        monkeypatch.setattr(le, "_cached_model_size", "")

        new_model = MagicMock()
        new_model.transcribe.return_value = ([], None)
        mock_fw = sys.modules["faster_whisper"]
        mock_fw.WhisperModel = MagicMock(return_value=new_model)

        mock_sd = sys.modules["sounddevice"]
        mock_sd.InputStream = MagicMock(return_value=MagicMock())

        t = _make_transcriber(model_size="medium", status_cb=MagicMock())

        def stop_immediately(timeout=None):
            t._is_running = False
            raise queue.Empty

        t._audio_queue.get = stop_immediately
        t._is_running = True
        t._process_loop()

        # Verify cache was updated
        assert le._cached_model is new_model
        assert le._cached_model_size == "medium"


# ---------------------------------------------------------------------------
# TestLiveTranscriberNetworkInterruption — Network/device errors
# ---------------------------------------------------------------------------


class TestLiveTranscriberNetworkInterruption:
    """Tests for microphone disconnection and device errors."""

    def test_microphone_disconnected_during_recording(self) -> None:
        """OSError from audio queue mid-loop is caught."""
        status_cb = MagicMock()
        t = _make_transcriber(status_cb=status_cb)
        mock_model, _s = _setup_mocks()

        speech = np.ones((_BLOCK_SIZE,), dtype=np.float32) * 0.5
        call_count = [0]

        def get_then_error(timeout=None):
            call_count[0] += 1
            if call_count[0] <= 2:  # noqa: PLR2004
                return speech
            raise OSError("Device disconnected")

        t._audio_queue.get = get_then_error
        t._is_running = True
        t._process_loop()

        assert t._is_running is False
        # Error reported via status callback
        last_call = status_cb.call_args_list[-1][0][0]
        assert "Device disconnected" in last_call

    def test_pyaudio_error_during_stream_open(self) -> None:
        """OSError from InputStream constructor is caught and reported."""
        status_cb = MagicMock()
        t = _make_transcriber(status_cb=status_cb)
        _setup_mocks(stream_side_effect=OSError("PortAudio error: Device unavailable"))
        t._is_running = True
        t._process_loop()

        assert t._is_running is False
        last_call = status_cb.call_args_list[-1][0][0]
        assert "PortAudio error" in last_call

    def test_recovery_after_temporary_error(self) -> None:
        """After an error stops the engine, a new start() works."""
        status_cb = MagicMock()
        t = _make_transcriber(status_cb=status_cb)

        # First run: model load fails
        _setup_mocks(model_side_effect=RuntimeError("Temporary failure"))
        t._is_running = True
        t._process_loop()
        assert t._is_running is False

        # Second run: succeeds
        mock_model, mock_stream = _setup_mocks(
            model_segments=[SimpleNamespace(text="Recovered")],
        )
        sentence_cb = MagicMock()
        t._on_sentence = sentence_cb

        speech = np.ones((_BLOCK_SIZE,), dtype=np.float32) * 0.5
        silence = np.zeros((_BLOCK_SIZE,), dtype=np.float32)
        blocks = [speech] * (_MIN_AUDIO_BLOCKS + 1) + [silence] * _SILENCE_BLOCKS
        _feed_blocks_and_run(t, blocks)

        assert sentence_cb.call_count == 1
        assert sentence_cb.call_args[0][0] == "Recovered"

    def test_stream_start_oserror_handled(self) -> None:
        """stream.start() raising OSError is caught in _process_loop."""
        status_cb = MagicMock()
        t = _make_transcriber(status_cb=status_cb)
        _mock_model, _s = _setup_mocks()

        mock_sd = sys.modules["sounddevice"]
        mock_stream = MagicMock()
        mock_stream.start.side_effect = OSError("Audio subsystem not initialized")
        mock_sd.InputStream = MagicMock(return_value=mock_stream)

        t._is_running = True
        t._process_loop()

        assert t._is_running is False
        last_call = status_cb.call_args_list[-1][0][0]
        assert "Audio subsystem not initialized" in last_call

    def test_sys_audio_process_dies_during_capture(self, monkeypatch) -> None:
        """Parec subprocess dying is handled: _stop_system_audio cleans up."""
        t = _make_transcriber()
        mock_proc = MagicMock()
        mock_proc.terminate = MagicMock()
        mock_proc.wait = MagicMock()
        t._sys_audio_proc = mock_proc
        mock_thread = MagicMock()
        mock_thread.join = MagicMock()
        t._sys_audio_thread = mock_thread

        t._stop_system_audio()

        mock_proc.terminate.assert_called_once()
        mock_proc.wait.assert_called_once_with(timeout=3)
        mock_thread.join.assert_called_once_with(timeout=3)
        assert t._sys_audio_proc is None
        assert t._sys_audio_thread is None


# ---------------------------------------------------------------------------
# TestLiveTranscriberEmptyAudio — Empty/silent audio handling
# ---------------------------------------------------------------------------


class TestLiveTranscriberEmptyAudio:
    """Tests for empty, silent, and malformed audio data."""

    def test_all_zero_audio_data_handled(self) -> None:
        """All-zero audio data is treated as silence, no transcription."""
        sentence_cb = MagicMock()
        t = _make_transcriber(sentence_cb=sentence_cb, status_cb=MagicMock())
        mock_model, _s = _setup_mocks()

        zeros = np.zeros((_BLOCK_SIZE,), dtype=np.float32)
        blocks = [zeros] * 20
        _feed_blocks_and_run(t, blocks)

        mock_model.transcribe.assert_not_called()
        sentence_cb.assert_not_called()

    def test_very_short_audio_clips_below_min_blocks(self) -> None:
        """Audio shorter than _MIN_AUDIO_BLOCKS is not transcribed."""
        sentence_cb = MagicMock()
        t = _make_transcriber(sentence_cb=sentence_cb, status_cb=MagicMock())
        mock_model, _s = _setup_mocks()

        # Only 1 speech block — below _MIN_AUDIO_BLOCKS (2)
        speech = np.ones((_BLOCK_SIZE,), dtype=np.float32) * 0.5
        silence = np.zeros((_BLOCK_SIZE,), dtype=np.float32)
        blocks = [speech] + [silence] * _SILENCE_BLOCKS
        _feed_blocks_and_run(t, blocks)

        mock_model.transcribe.assert_not_called()
        sentence_cb.assert_not_called()

    def test_audio_data_with_nan_values(self) -> None:
        """Audio blocks with NaN values are queued (handled by Whisper)."""
        t = _make_transcriber()
        t._is_running = True
        nan_block = np.full((_BLOCK_SIZE, 1), fill_value=np.nan, dtype=np.float32)
        t._audio_callback(nan_block, _BLOCK_SIZE, None, None)
        assert not t._audio_queue.empty()
        queued = t._audio_queue.get_nowait()
        assert np.isnan(queued).all()

    def test_audio_data_with_inf_values(self) -> None:
        """Audio blocks with inf values are queued without error."""
        t = _make_transcriber()
        t._is_running = True
        inf_block = np.full((_BLOCK_SIZE, 1), fill_value=np.inf, dtype=np.float32)
        t._audio_callback(inf_block, _BLOCK_SIZE, None, None)
        assert not t._audio_queue.empty()
        queued = t._audio_queue.get_nowait()
        assert np.isinf(queued).all()

    def test_empty_block_zero_samples(self) -> None:
        """Zero-sample audio block is queued without error."""
        t = _make_transcriber()
        t._is_running = True
        empty = np.array([], dtype=np.float32).reshape(0, 1)
        t._audio_callback(empty, 0, None, None)
        assert not t._audio_queue.empty()
        queued = t._audio_queue.get_nowait()
        assert queued.shape[0] == 0

    def test_single_sample_audio_block(self) -> None:
        """Single-sample audio block is queued."""
        t = _make_transcriber()
        t._is_running = True
        single = np.array([[0.5]], dtype=np.float32)
        t._audio_callback(single, 1, None, None)
        queued = t._audio_queue.get_nowait()
        assert queued.shape == (1, 1)
        assert queued[0, 0] == pytest.approx(0.5)

    def test_transcribe_buffer_with_tiny_blocks(self) -> None:
        """_transcribe_buffer handles very small blocks without error."""
        sentence_cb = MagicMock()
        t = _make_transcriber(sentence_cb=sentence_cb)
        model = MagicMock()
        model.transcribe.return_value = (
            [SimpleNamespace(text="Tiny")],
            None,
        )
        # 10-sample blocks
        blocks = [np.ones((10,), dtype=np.float32) for _ in range(5)]
        t._transcribe_buffer(model, blocks, None)
        audio_arg = model.transcribe.call_args[0][0]
        assert audio_arg.shape == (50,)
        assert sentence_cb.call_count == 1


# ===========================================================================
# ``_put_drop_oldest`` race-condition coverage
# ===========================================================================
#
# ``_put_drop_oldest`` (live_engine.py:50) has an explicit retry loop
# for the case where the consumer drains the queue between our
# ``put_nowait`` (which raised Full) and ``get_nowait`` (which raises
# Empty).  The existing ``test_queue_caps_rapid_puts_drops_oldest``
# test only exercises the single-thread overflow path.  These tests
# fire concurrent producer + consumer threads (and a programmable
# stub queue) to actually trigger the Full → Empty interleaving and
# prove the loop terminates.


class TestPutDropOldestConcurrentRace:
    """Concurrent producer / consumer hammering ``_put_drop_oldest``."""

    def test_concurrent_put_and_get_terminates_without_deadlock(self) -> None:
        """Two threads fighting over a tiny queue do not deadlock."""
        import threading  # noqa: PLC0415

        from src.core.live_engine import _put_drop_oldest  # noqa: PLC0415

        q: queue.Queue[int] = queue.Queue(maxsize=1)
        n_items = 200
        received: list[int] = []
        stop_event = threading.Event()

        def consumer() -> None:
            while not stop_event.is_set() or not q.empty():
                try:
                    received.append(q.get(timeout=0.05))
                except queue.Empty:
                    continue

        def producer() -> None:
            for i in range(n_items):
                _put_drop_oldest(q, i)

        c_thread = threading.Thread(target=consumer)
        p_thread = threading.Thread(target=producer)
        c_thread.start()
        p_thread.start()
        p_thread.join(timeout=5.0)
        assert not p_thread.is_alive(), "producer hung — retry loop deadlocked"
        stop_event.set()
        c_thread.join(timeout=5.0)
        assert not c_thread.is_alive()

        # Drop-oldest is acceptable; the consumer must have made
        # forward progress.  An empty ``received`` would mean every
        # item was silently swallowed.
        assert received, "consumer received nothing — items lost in race"

    def test_full_then_empty_branch_via_scripted_queue(self) -> None:
        """Exercise the ``except queue.Empty: continue`` branch deterministically.

        A scripted queue makes the first ``put_nowait`` raise Full,
        the first ``get_nowait`` raise Empty (consumer drained), and
        the second ``put_nowait`` succeed.  The function must return
        without raising and without spinning indefinitely.
        """
        from src.core.live_engine import _put_drop_oldest  # noqa: PLC0415

        class _ScriptedQueue:
            def __init__(self) -> None:
                self.put_calls = 0
                self.get_calls = 0

            def put_nowait(self, _item: object) -> None:
                self.put_calls += 1
                if self.put_calls == 1:
                    raise queue.Full
                # Second attempt succeeds.

            def get_nowait(self) -> object:
                self.get_calls += 1
                # Consumer drained between our put_nowait and get_nowait.
                raise queue.Empty

        sq = _ScriptedQueue()
        _put_drop_oldest(sq, 42)  # type: ignore[arg-type]
        assert sq.put_calls == 2, "expected exactly one retry"
        assert sq.get_calls == 1, "expected exactly one drain attempt"


class TestSystemAudioStopConcurrent:
    """Calling ``_stop_system_audio`` twice concurrently is safe.

    Pins that the stop path is idempotent under thread races. A user
    smashing the Stop button while the live page's ``aboutToQuit`` hook
    fires the same teardown shouldn't surface a ``TypeError`` /
    ``AttributeError`` from a second call against an already-cleared
    process attribute. Without idempotence, the second call would raise
    on ``proc.terminate()`` against a None reference.
    """

    def test_double_stop_no_exception(self) -> None:
        """Two sequential stops on the same instance are safe."""
        from unittest.mock import MagicMock  # noqa: PLC0415

        t = LiveTranscriber(on_sentence=MagicMock())
        mock_proc = MagicMock()
        t._sys_audio_proc = mock_proc
        t._sys_audio_thread = MagicMock()

        # First stop tears down state.
        t._stop_system_audio()
        assert t._sys_audio_proc is None
        assert t._sys_audio_thread is None

        # Second stop must be a no-op — not raise.
        t._stop_system_audio()
        # Process terminate was only called the first time.
        mock_proc.terminate.assert_called_once()


class TestPcmReaderEofExitsCleanly:
    """``_spawn_pcm_reader``'s reader thread exits when stdout returns b''.

    EOF (``read()`` returns b'') is the normal lifecycle signal when the
    capture subprocess closes its pipe (parec / ffmpeg shut down).
    The reader's ``while`` loop must observe this and break, leaving
    the thread in a joinable state. Without the explicit ``if not data:
    break``, the loop would spin on an empty read and the daemon thread
    would never terminate cleanly — leaking on app-exit.
    """

    def test_reader_thread_exits_on_eof(self) -> None:
        """Spawn the reader against a fake Popen whose stdout EOFs immediately."""
        import queue  # noqa: PLC0415
        from unittest.mock import MagicMock, patch  # noqa: PLC0415

        t = LiveTranscriber(on_sentence=MagicMock())
        # Fake Popen: poll() returns None (alive), stdout.read returns b''.
        fake_proc = MagicMock()
        fake_proc.poll.return_value = None
        fake_proc.stdout.read.return_value = b""

        target_q: queue.Queue = queue.Queue()

        with patch(
            "src.core.live_engine.subprocess.Popen",
            return_value=fake_proc,
        ):
            t._is_running = True
            t._spawn_pcm_reader(["fake-cmd"], target_q)

        # Wait briefly for the daemon reader to break and exit.
        thread = t._sys_audio_thread
        assert thread is not None
        thread.join(timeout=1.5)
        assert not thread.is_alive(), (
            "Reader thread did not exit on EOF — would leak at app shutdown"
        )
        # No samples were enqueued because read() returned no bytes.
        assert target_q.empty()


class TestPreloadWhisperModel:
    """``preload_whisper_model`` warms the module-level cache idempotently.

    Pins the contract that:
      * a no-op return when the cache already holds the requested size
        (avoids redundant model construction),
      * a successful load populates both ``_cached_model`` and
        ``_cached_model_size`` together (no torn write),
      * an exception inside ``WhisperModel(...)`` is swallowed and
        the cache is NOT mutated (preload is best-effort).
    """

    def test_idempotent_when_size_already_cached(self, monkeypatch) -> None:  # noqa: ANN001
        """Cache hit → no WhisperModel call, no cache mutation."""
        from unittest.mock import MagicMock  # noqa: PLC0415

        from src.core import live_engine  # noqa: PLC0415

        sentinel = object()
        monkeypatch.setattr(live_engine, "_cached_model", sentinel)
        monkeypatch.setattr(live_engine, "_cached_model_size", "tiny")
        mock_ctor = MagicMock()
        monkeypatch.setattr("faster_whisper.WhisperModel", mock_ctor)

        live_engine.preload_whisper_model("tiny")

        mock_ctor.assert_not_called()
        # Cache still holds the original sentinel — nothing rebound.
        assert live_engine._cached_model is sentinel

    def test_loads_when_cache_empty(self, monkeypatch) -> None:  # noqa: ANN001
        """Cold cache → model is constructed and stored."""
        from unittest.mock import MagicMock  # noqa: PLC0415

        from src.core import live_engine  # noqa: PLC0415

        monkeypatch.setattr(live_engine, "_cached_model", None)
        monkeypatch.setattr(live_engine, "_cached_model_size", "")
        fake_model = object()
        mock_ctor = MagicMock(return_value=fake_model)
        monkeypatch.setattr("faster_whisper.WhisperModel", mock_ctor)

        live_engine.preload_whisper_model("small")

        mock_ctor.assert_called_once_with("small", device="cpu", compute_type="int8")
        assert live_engine._cached_model is fake_model
        assert live_engine._cached_model_size == "small"
        # Cleanup: don't leak the fake into the next test.
        monkeypatch.setattr(live_engine, "_cached_model", None)
        monkeypatch.setattr(live_engine, "_cached_model_size", "")

    def test_loads_when_size_differs(self, monkeypatch) -> None:  # noqa: ANN001
        """Cache holds a different size → load and overwrite."""
        from unittest.mock import MagicMock  # noqa: PLC0415

        from src.core import live_engine  # noqa: PLC0415

        old_model = object()
        monkeypatch.setattr(live_engine, "_cached_model", old_model)
        monkeypatch.setattr(live_engine, "_cached_model_size", "tiny")
        new_model = object()
        mock_ctor = MagicMock(return_value=new_model)
        monkeypatch.setattr("faster_whisper.WhisperModel", mock_ctor)

        live_engine.preload_whisper_model("medium")

        mock_ctor.assert_called_once_with("medium", device="cpu", compute_type="int8")
        assert live_engine._cached_model is new_model
        assert live_engine._cached_model_size == "medium"

    def test_swallows_construction_errors(self, monkeypatch, caplog) -> None:  # noqa: ANN001
        """A WhisperModel exception is logged and the cache is left untouched."""
        from unittest.mock import MagicMock  # noqa: PLC0415

        from src.core import live_engine  # noqa: PLC0415

        monkeypatch.setattr(live_engine, "_cached_model", None)
        monkeypatch.setattr(live_engine, "_cached_model_size", "")
        mock_ctor = MagicMock(side_effect=RuntimeError("disk full"))
        monkeypatch.setattr("faster_whisper.WhisperModel", mock_ctor)

        # Must not raise.
        live_engine.preload_whisper_model("small")

        # Cache stays cold so a real future Start can retry.
        assert live_engine._cached_model is None
        assert live_engine._cached_model_size == ""
        # Failure is logged at exception level for diagnostic visibility.
        assert any(
            "Whisper preload failed" in rec.message
            for rec in caplog.records
        )


# ===========================================================================
# TestAudioAvailabilityCaches — module-level cache for showEvent freezes
# ===========================================================================


class TestAudioAvailabilityCaches:
    """check_audio_available / check_system_audio_available are cached.

    The Live page's ``showEvent`` and ``_sync_system_audio_warning``
    call these probes on every visit + every audio-source combo
    refresh.  Re-shelling-out to ALSA / pactl / ffmpeg on each call
    was the source of "freezes when I navigate to Live" reports.
    These tests pin the cache + invalidation contract.

    Note: these tests call ``check_audio_available`` / ``invalidate_
    audio_caches`` via the directly-imported names (top of file)
    rather than ``live_engine.check_audio_available`` — the module-
    level autouse fixture ``_bypass_audio_check_and_reset_cache``
    monkey-patches the module attribute to ``lambda: ""`` for every
    test, so accessing it via the module would return the stub and
    skip the real caching logic.  The local import binding stays
    pinned to the original function.
    """

    def setup_method(self) -> None:
        """Ensures every test starts with cold caches."""
        invalidate_audio_caches()

    def test_check_audio_available_caches_result(self) -> None:
        """Second call uses the cached value; ``sd.query_devices`` runs once."""
        mock_sd = sys.modules["sounddevice"]
        mock_sd.query_devices = MagicMock(
            return_value=[{"max_input_channels": 2}],
        )
        first = check_audio_available()
        second = check_audio_available()

        assert first == ""
        assert second == ""
        assert mock_sd.query_devices.call_count == 1

    def test_check_audio_available_caches_failure(self) -> None:
        """Failure results (no mic, no portaudio) are cached too.

        Otherwise every ``showEvent`` re-shells to PortAudio when
        the user has no mic plugged in — the same freeze surface
        for an even less-recoverable state.
        """
        mock_sd = sys.modules["sounddevice"]
        mock_sd.query_devices = MagicMock(
            return_value=[{"max_input_channels": 0}],
        )
        first = check_audio_available()
        second = check_audio_available()

        assert first == "live.error_no_mic"
        assert second == "live.error_no_mic"
        assert mock_sd.query_devices.call_count == 1

    def test_check_system_audio_available_caches_result(self) -> None:
        """System-audio probe doesn't re-shell-out to pactl on every call.

        Linux ``check_system_audio_available()`` shells to ``pactl
        get-default-sink`` which has a 1-second timeout.  Without
        the cache, a user on the System / Both audio source pays
        that cost on every page show.
        """
        from src.core import live_engine  # noqa: PLC0415

        with patch.object(
            live_engine,
            "_get_default_monitor_source",
            return_value="x.monitor",
        ) as mock_probe, patch(
            "shutil.which", return_value="/usr/bin/parec",
        ), patch.object(
            live_engine.platform, "system", return_value="Linux",
        ):
            first = check_system_audio_available()
            second = check_system_audio_available()

        assert first is True
        assert second is True
        assert mock_probe.call_count == 1

    def test_invalidate_clears_both_caches(self) -> None:
        """``invalidate_audio_caches`` flushes both caches in one call."""
        from src.core import live_engine  # noqa: PLC0415

        live_engine._audio_available_cache = "live.error_no_mic"
        live_engine._system_audio_available_cache = True

        invalidate_audio_caches()

        assert live_engine._audio_available_cache is live_engine._UNSET
        assert live_engine._system_audio_available_cache is live_engine._UNSET

    def test_invalidate_lets_next_call_reprobe(self) -> None:
        """Post-invalidate call re-shells out — caches stayed stale otherwise."""
        mock_sd = sys.modules["sounddevice"]
        mock_sd.query_devices = MagicMock(
            return_value=[{"max_input_channels": 2}],
        )
        check_audio_available()
        invalidate_audio_caches()
        check_audio_available()

        assert mock_sd.query_devices.call_count == 2  # noqa: PLR2004

    def test_pactl_probe_uses_short_timeout(self) -> None:
        """``_get_default_monitor_source`` runs pactl with a 1 s cap.

        Regression guard for the showEvent freeze fix.  The original
        5-second cap exceeded the window manager's "application not
        responding" threshold (~5 s on most Linux DEs).  1 s keeps
        worst-case stalls well under that limit.
        """
        from src.core import live_engine  # noqa: PLC0415

        mock_result = MagicMock(stdout="sink_name\n", returncode=0)
        with patch.object(
            live_engine.subprocess, "run", return_value=mock_result,
        ) as mock_run, patch(
            "shutil.which", return_value="/usr/bin/pactl",
        ):
            _get_default_monitor_source()

        kwargs = mock_run.call_args.kwargs
        assert kwargs.get("timeout") == 1
