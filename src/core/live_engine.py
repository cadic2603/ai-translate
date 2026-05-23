"""Live audio capture and streaming transcription engine.

Captures microphone audio in real-time, transcribes using faster-whisper,
and emits recognized sentences for translation.
"""

from __future__ import annotations

import contextlib
import logging
import platform
import queue
import shutil
import subprocess
import threading
import types
import wave
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from faster_whisper import WhisperModel

logger = logging.getLogger("live_engine")

# Audio capture settings
_SAMPLE_RATE = 16000
_CHANNELS = 1
_BLOCK_DURATION = 0.5  # seconds per audio block
_BLOCK_SIZE = int(_SAMPLE_RATE * _BLOCK_DURATION)

# Silence detection
_SILENCE_THRESHOLD = 0.01  # RMS threshold for silence
_SILENCE_BLOCKS = 2  # consecutive silent blocks to trigger transcription
_MIN_AUDIO_BLOCKS = 2  # minimum blocks to consider as speech
_MAX_BUFFER_SECONDS = 5.0  # force transcription after this many seconds
_MAX_BUFFER_BLOCKS = int(_MAX_BUFFER_SECONDS / _BLOCK_DURATION)

# Upper bound on queued audio blocks per source before the producer
# starts dropping oldest.  20 blocks × 0.5 s = 10 s — plenty to absorb
# one slow whisper pass, not so much that slow models accumulate a
# minute of lag on long sessions.
_QUEUE_MAX_BLOCKS = 20

# Module-level model cache — avoids reloading on every Start/Stop cycle
_cached_model: WhisperModel | None = None
_cached_model_size: str = ""

# Maps the user-facing model-size keyword to the canonical HuggingFace
# repo ID used by faster-whisper for snapshot lookup.  Used by
# ``is_whisper_model_cached`` to detect a hot model without paying the
# cost of a real load.  ``large`` maps to ``large-v3`` — same alias
# faster-whisper applies internally.
_WHISPER_REPO_BY_SIZE = {
    "tiny": "Systran/faster-whisper-tiny",
    "base": "Systran/faster-whisper-base",
    "small": "Systran/faster-whisper-small",
    "medium": "Systran/faster-whisper-medium",
    "large": "Systran/faster-whisper-large-v3",
    "large-v1": "Systran/faster-whisper-large-v1",
    "large-v2": "Systran/faster-whisper-large-v2",
    "large-v3": "Systran/faster-whisper-large-v3",
}


def is_whisper_model_cached(model_size: str) -> bool:
    """Returns True when the faster-whisper model files are already on disk.

    Used by the Live page's ``showEvent`` preload to avoid silently
    triggering a multi-hundred-MB download for users who navigate to
    the page without intending to start a session.  Returns ``False``
    for unknown sizes and for environments without ``huggingface_hub``.
    """
    repo = _WHISPER_REPO_BY_SIZE.get(model_size)
    if not repo:
        return False
    try:
        from huggingface_hub import try_to_load_from_cache  # noqa: PLC0415
    except ImportError:
        return False
    # ``config.json`` is the smallest file every snapshot ships;
    # presence guarantees the repo was downloaded at least once.
    return isinstance(try_to_load_from_cache(repo, "config.json"), str)


def preload_whisper_model(model_size: str) -> None:
    """Loads the named Whisper model into the module cache, if not present.

    Idempotent: returns immediately when the cache already holds the
    requested size.  Safe to call from a background thread; the GIL
    plus the simple two-line cache write make a partial concurrent
    update harmless (the second writer just rebinds to its own model
    instance, which becomes garbage immediately).  Errors are swallowed
    — a failed preload is a UX optimisation miss, not a bug.
    """
    global _cached_model, _cached_model_size  # noqa: PLW0603

    if _cached_model is not None and _cached_model_size == model_size:
        return
    try:
        from faster_whisper import WhisperModel  # noqa: PLC0415

        model = WhisperModel(model_size, device="cpu", compute_type="int8")
    except Exception:
        logger.exception("Whisper preload failed for size=%s", model_size)
        return
    _cached_model = model
    _cached_model_size = model_size


def _put_drop_oldest(q: queue.Queue[Any], item: Any) -> None:  # noqa: ANN401
    """Non-blocking put that drops the oldest item when the queue is full.

    Producers (sounddevice callbacks, parec reader threads) must never
    block on the Python-level queue: a stalled producer would either
    drop device samples at the OS level or stall the callback.  When a
    slow consumer (slow whisper model) can't keep up, drop the oldest
    item so the queue keeps representing the *latest* audio available.
    """
    while True:
        try:
            q.put_nowait(item)
            return
        except queue.Full:
            try:
                q.get_nowait()
            except queue.Empty:
                # Consumer drained between our two ops; retry put.
                continue


def next_block(
    q: queue.Queue[Any] | None,
    timeout: float,
) -> Any | None:  # noqa: ANN401
    """Returns the oldest pending item from *q*, or ``None`` on timeout.

    Simple FIFO consumption.  Prior versions of this helper drained to
    the newest block to cap real-time drift between mic and system
    streams, but that discarded 2–3 seconds of audio per whisper
    transcription cycle (the queues grow ~5 blocks during a 1.3 s
    ``transcribe()`` call; the drop left whisper with non-contiguous
    audio and triggered the "Compression ratio > 2.4 → reject"
    failure mode).  FIFO keeps audio contiguous; queues grow during
    transcription and drain again on the next idle iteration — whisper
    is faster than capture on base model, so the queue size oscillates
    but doesn't grow unbounded.

    Shared between ``LiveTranscriber._read_block`` (whisper internal
    mixer) and the Soniox / Gemini Live "both"-mode mixer in the UI
    layer so the two paths have identical consumption semantics.
    """
    if q is None:
        return None
    try:
        return q.get(timeout=timeout)
    except queue.Empty:
        return None


def _get_install_hint(packages: dict[str, str]) -> str:
    """Returns a distro-specific install command hint, or empty string.

    Args:
        packages: Mapping of package-manager binary to full install command.
    """
    if platform.system() != "Linux":
        return ""
    for binary, cmd in packages.items():
        if shutil.which(binary):
            return cmd
    return ""


# Per-package-manager install commands
_PORTAUDIO_PACKAGES: dict[str, str] = {
    "apt-get": "sudo apt-get install libportaudio2",
    "dnf": "sudo dnf install portaudio",
    "pacman": "sudo pacman -S portaudio",
    "zypper": "sudo zypper install libportaudio2",
    "apk": "sudo apk add portaudio",
}

_PULSEAUDIO_PACKAGES: dict[str, str] = {
    "apt-get": "sudo apt-get install pulseaudio",
    "dnf": "sudo dnf install pulseaudio",
    "pacman": "sudo pacman -S pulseaudio",
    "zypper": "sudo zypper install pulseaudio",
    "apk": "sudo apk add pulseaudio",
}


def _get_portaudio_install_hint() -> str:
    """Returns a distro-specific PortAudio install command, or empty string."""
    return _get_install_hint(_PORTAUDIO_PACKAGES)


def _get_pulseaudio_install_hint() -> str:
    """Returns a distro-specific PulseAudio install command, or empty string."""
    return _get_install_hint(_PULSEAUDIO_PACKAGES)


# ── Audio-availability probe caches ───────────────────────────────────────
# ``check_audio_available()`` and ``check_system_audio_available()`` shell
# out to ALSA / PortAudio / pactl / ffmpeg, which can each stall up to
# their (newly-tight) timeouts when the audio stack is busy.  The Live
# page's ``showEvent`` and ``_sync_system_audio_warning`` both call these
# probes — re-shelling out on every page show or audio-source combo
# refresh blocked the UI thread once per visit even though the answer
# rarely changes session-to-session.  Cache the result; the page calls
# :func:`invalidate_audio_caches` when the user actually clicks Start or
# changes audio source, so a freshly-installed BlackHole / re-plugged
# mic is still picked up.  Sentinel ``_UNSET`` distinguishes "not yet
# probed" from "probed and got falsy value" without conflating ``None``
# / empty-string semantics.
_UNSET: Any = object()
_audio_available_cache: Any = _UNSET
_system_audio_available_cache: Any = _UNSET


def invalidate_audio_caches() -> None:
    """Forces the next probe call to re-shell-out instead of using cached state.

    Called from the Live page when the user clicks Start or changes
    the audio source combo — both are points where the user has
    intent + we want a fresh diagnosis.  Cheap; safe to call
    redundantly.
    """
    global _audio_available_cache, _system_audio_available_cache  # noqa: PLW0603
    _audio_available_cache = _UNSET
    _system_audio_available_cache = _UNSET


def check_audio_available() -> str:
    """Pre-validates that audio capture is possible.

    Returns:
        Empty string on success, or an i18n error key string.
        When PortAudio is missing on Linux, the key includes a
        ``{cmd}`` placeholder populated with the install command.

    Result is cached in :data:`_audio_available_cache` so repeated
    calls (showEvent re-probe) skip the ``sd.query_devices()``
    enumeration after the first call.  Invalidate explicitly via
    :func:`invalidate_audio_caches` when the user signals a
    re-probe (Start click / source combo change).
    """
    global _audio_available_cache  # noqa: PLW0603
    if _audio_available_cache is not _UNSET:
        return _audio_available_cache

    try:
        import sounddevice as sd  # noqa: PLC0415
    except OSError:
        _audio_available_cache = "live.error_no_portaudio"
        return _audio_available_cache

    try:
        devices = sd.query_devices()
        if not any(d["max_input_channels"] > 0 for d in devices):
            _audio_available_cache = "live.error_no_mic"
            return _audio_available_cache
    except Exception as exc:
        logger.error("Audio device query failed: %s", exc)
        _audio_available_cache = "live.error_no_mic"
        return _audio_available_cache

    _audio_available_cache = ""
    return _audio_available_cache


def list_input_devices() -> list[tuple[int, str]]:
    """Returns a list of available audio input devices.

    Returns:
        List of (device_index, device_name) tuples.
    """
    import sounddevice as sd  # noqa: PLC0415

    devices = sd.query_devices()
    result = []
    for i, dev in enumerate(devices):
        if dev["max_input_channels"] > 0:
            result.append((i, dev["name"]))
    return result


def _get_default_monitor_source() -> str | None:
    """Returns the PulseAudio monitor source name for the default output sink.

    Queries ``pactl`` for the default sink and appends ``.monitor``.
    Returns None when ``pactl`` is absent or the query fails.

    Timeout is intentionally tight (1 s).  ``pactl get-default-sink``
    normally responds in <10 ms; a multi-second wait only ever
    happens when PulseAudio / PipeWire is restarting or its dbus
    socket is wedged.  This function runs on the UI thread via
    ``check_system_audio_available``'s ``showEvent`` path, so an
    over-generous timeout there used to freeze the page for 5 s
    and trigger window-manager "application not responding" hints.
    1 s keeps the worst case well below the WM threshold while
    still leaving headroom for typical recovery.
    """
    if not shutil.which("pactl"):
        return None
    try:
        result = subprocess.run(  # noqa: S603, S607
            ["pactl", "get-default-sink"],
            capture_output=True,
            text=True,
            timeout=1,
            check=False,
        )
        sink = result.stdout.strip()
        if result.returncode == 0 and sink:
            return f"{sink}.monitor"
    except Exception as exc:
        logger.debug("pactl query failed: %s", exc)
    return None


# ── Cross-platform system-audio capture ───────────────────────────────────
# Each platform needs different glue to grab "what the speakers are
# playing" alongside the user's mic.  The cleanest portable contract:
# spawn a subprocess that emits raw 16-kHz mono s16le PCM on stdout,
# regardless of the underlying capture API.  The reader thread then
# converts those bytes to float32 numpy blocks the same way the parec
# path always has — so the rest of the pipeline (whisper / Soniox /
# Gemini Live) stays unchanged.
#
# - Linux: ``parec`` against PulseAudio's default-sink monitor source.
#   Built into PulseAudio / PipeWire-pulse, no extra software needed.
# - macOS: ``ffmpeg -f avfoundation`` against a virtual loopback device
#   (BlackHole, Loopback, etc.) the user installs.  CoreAudio doesn't
#   expose the system mix natively, so a virtual device is required.
# - Windows: ``ffmpeg -f dshow`` against ``virtual-audio-capturer``
#   (from Screen Capture Recorder) or a VB-Audio Virtual Cable.  Newer
#   ffmpeg builds also support ``-f wasapi`` for native loopback, but
#   the dshow path is the most widely-supported install today.
#
# Discovery + start helpers live below this banner; the dispatchers on
# ``LiveTranscriber`` (``_start_system_audio`` / ``_stop_system_audio``)
# pick one based on ``platform.system()``.


# Substrings that identify a virtual-loopback audio device the user has
# installed.  The macOS-side ``ffmpeg -f avfoundation -list_devices true``
# dump prints a numbered list of audio inputs; we match these names
# case-insensitively.  Add new options to widen support without code
# changes elsewhere.
_MACOS_LOOPBACK_KEYWORDS: tuple[str, ...] = (
    "blackhole",
    "loopback",
    "soundflower",
    "ishowu",
)

# DirectShow audio device names used for system-audio loopback on
# Windows.  Order matters: probed first → succeeds first.
_WINDOWS_LOOPBACK_DEVICES: tuple[str, ...] = (
    "virtual-audio-capturer",  # Screen Capture Recorder
    "CABLE Output (VB-Audio Virtual Cable)",
    "Stereo Mix (Realtek Audio)",  # Legacy on-board option
)


def _get_macos_loopback_device_index() -> int | None:
    """Returns the avfoundation audio device index of a virtual loopback.

    Runs ``ffmpeg -f avfoundation -list_devices true -i ""`` and parses
    the audio-device list out of stderr (avfoundation prints to stderr,
    not stdout).  Matches device names against
    ``_MACOS_LOOPBACK_KEYWORDS`` so the user's specific virtual device
    (BlackHole / Loopback / Soundflower / iShowU) is auto-detected.

    Returns the zero-based audio index suitable for
    ``ffmpeg -f avfoundation -i ":<index>"``.  Returns None when ffmpeg
    is missing or no virtual loopback is installed.
    """
    if not shutil.which("ffmpeg"):
        return None
    try:
        result = subprocess.run(  # noqa: S603, S607
            [
                "ffmpeg", "-hide_banner", "-f", "avfoundation",
                "-list_devices", "true", "-i", "",
            ],
            capture_output=True,
            text=True,
            # Tight cap so a slow ffmpeg / hung CoreAudio probe can't
            # freeze the Live page's ``showEvent`` on macOS for 10 s
            # (the prior value).  ffmpeg's device list normally returns
            # in <200 ms; 2 s keeps headroom while staying below the
            # WM "not responding" threshold.
            timeout=2,
            check=False,
        )
    except Exception as exc:
        logger.debug("ffmpeg avfoundation list failed: %s", exc)
        return None

    # avfoundation prints its device list to stderr.  Format per line:
    #   ``[AVFoundation indev @ 0x...] [<idx>] <Device Name>``
    # We scan the section that follows the ``AVFoundation audio devices``
    # header, splitting each line on ``"] ["`` to separate the indev
    # bracket from the index bracket, then partitioning on ``"] "`` to
    # peel the integer index off the device name.
    in_audio_section = False
    for raw in result.stderr.splitlines():
        line = raw.strip()
        if "AVFoundation audio devices" in line:
            in_audio_section = True
            continue
        if not in_audio_section:
            continue
        # End of section: another header or blank line ⇒ stop scanning.
        if "AVFoundation video devices" in line or not line.startswith("["):
            break
        parts = line.split("] [", 1)
        if len(parts) != 2:  # noqa: PLR2004
            continue  # Doesn't match the [indev] [idx] shape.
        idx_str, sep, name = parts[1].partition("] ")
        if not sep:
            continue  # Malformed line — skip without crashing.
        try:
            idx = int(idx_str)
        except ValueError:
            continue
        if any(kw in name.lower() for kw in _MACOS_LOOPBACK_KEYWORDS):
            logger.debug("macOS loopback device: [%d] %s", idx, name.strip())
            return idx
    return None


def _get_windows_loopback_device_name() -> str | None:
    """Returns the dshow audio device name of an installed virtual loopback.

    Runs ``ffmpeg -f dshow -list_devices true -i dummy`` and parses the
    device list from stderr.  Returns the first name in
    ``_WINDOWS_LOOPBACK_DEVICES`` that's actually present.  None when
    ffmpeg is missing or no compatible device is installed.
    """
    if not shutil.which("ffmpeg"):
        return None
    try:
        result = subprocess.run(  # noqa: S603, S607
            [
                "ffmpeg", "-hide_banner", "-f", "dshow",
                "-list_devices", "true", "-i", "dummy",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except Exception as exc:
        logger.debug("ffmpeg dshow list failed: %s", exc)
        return None

    blob = result.stderr
    for candidate in _WINDOWS_LOOPBACK_DEVICES:
        # dshow prints ``"<name>" (audio)`` for audio devices; look for
        # the quoted name anywhere in the output.
        if f'"{candidate}"' in blob:
            return candidate
    return None


def _check_windows_soundcard_loopback() -> bool:
    """Returns True if the ``soundcard`` package can grab WASAPI loopback.

    soundcard is the preferred Windows backend: it calls WASAPI's
    native loopback flag directly — no extra software install — so
    most Windows machines are good to go without virtual-audio-capturer
    / VB-Audio.  We only need to confirm the import works AND a
    default speaker exists; the actual recorder is opened later in
    :meth:`LiveTranscriber._start_system_audio_windows_soundcard`.
    """
    try:
        import soundcard as sc  # noqa: PLC0415
    except (ImportError, OSError) as exc:
        logger.debug("soundcard import failed: %s", exc)
        return False
    try:
        return sc.default_speaker() is not None
    except Exception as exc:  # noqa: BLE001 - soundcard surfaces a wide range
        logger.debug("soundcard default_speaker() failed: %s", exc)
        return False


def check_system_audio_available() -> bool:  # noqa: PLR0911
    """Returns True if system audio capture is possible on this OS.

    Dispatches to a per-platform check:

    - Linux: ``parec`` is on PATH AND a default PulseAudio sink exists.
    - macOS: ``ffmpeg`` is on PATH AND a virtual loopback device
      (BlackHole / Loopback / Soundflower) is installed.
    - Windows: the ``soundcard`` package can reach WASAPI loopback
      (no extra software needed) OR ``ffmpeg`` plus a known
      DirectShow loopback device (virtual-audio-capturer / VB-Audio /
      Stereo Mix) is available as a fallback.

    Result is cached in :data:`_system_audio_available_cache` to
    avoid re-shelling-out to ``pactl`` / ``ffmpeg`` on every
    ``showEvent`` and audio-source combo refresh.  Invalidate via
    :func:`invalidate_audio_caches` when the user explicitly
    signals a re-probe (Start click / source combo change).
    """
    global _system_audio_available_cache  # noqa: PLW0603
    if _system_audio_available_cache is not _UNSET:
        return _system_audio_available_cache

    system = platform.system()
    if system == "Linux":
        if not shutil.which("parec"):
            _system_audio_available_cache = False
            return _system_audio_available_cache
        _system_audio_available_cache = (
            _get_default_monitor_source() is not None
        )
        return _system_audio_available_cache
    if system == "Darwin":
        _system_audio_available_cache = (
            _get_macos_loopback_device_index() is not None
        )
        return _system_audio_available_cache
    if system == "Windows":
        # Native WASAPI loopback first; ffmpeg+dshow stays as the
        # legacy fallback for users who already have a virtual cable.
        if _check_windows_soundcard_loopback():
            _system_audio_available_cache = True
            return _system_audio_available_cache
        _system_audio_available_cache = (
            _get_windows_loopback_device_name() is not None
        )
        return _system_audio_available_cache
    _system_audio_available_cache = False
    return _system_audio_available_cache


class LiveTranscriber:
    """Captures audio and transcribes in real-time.

    Supports three audio source modes:
    - ``microphone``: default input device (mic)
    - ``system``: monitor source that captures desktop/system audio
    - ``both``: mixes microphone and system audio together

    Usage:
        transcriber = LiveTranscriber(
            on_sentence=lambda text: print(f"[final] {text}"),
            model_size="tiny",
            language="Vietnamese",
            audio_source="microphone",
        )
        transcriber.start()
        # ... later ...
        transcriber.stop()
    """

    def __init__(  # noqa: PLR0913
        self,
        on_sentence: Callable[[str, float, float], None],
        on_partial: Callable[[str], None] | None = None,
        on_status: Callable[[str], None] | None = None,
        on_stopped: Callable[[], None] | None = None,
        model_size: str = "tiny",
        language: str = "",
        device: int | None = None,
        audio_source: str = "microphone",
        record_to: Path | None = None,
    ) -> None:
        """Initializes the live transcriber.

        Args:
            on_sentence: Called with (text, start_sec, end_sec) for each sentence.
            on_partial: Called with partial (in-progress) text.
            on_status: Called with status messages.
            on_stopped: Called when the processing loop exits (error or normal).
            model_size: Whisper model size.
            language: Source language label. Empty for auto-detect.
            device: Audio input device index. None for default mic.
            audio_source: One of "microphone", "system", or "both".
            record_to: Optional ``.wav`` path.  When set, every audio
                block returned by :meth:`_read_block` is written to
                this file as raw 16-kHz mono s16le PCM (wrapped in a
                WAV header).  ``stop()`` closes the file.  Off by
                default — recording is opt-in via the Live setting.
        """
        self._on_sentence = on_sentence
        self._on_partial = on_partial
        self._on_status = on_status
        self._on_stopped = on_stopped
        self._model_size = model_size
        self._language = language
        self._device = device
        self._audio_source = audio_source
        self._record_to = record_to
        # Lazy-opened WAV writer + raw PCM file handle, both kept on
        # the instance so ``stop()`` can finalise them without
        # re-resolving from the path.  ``_record_writer`` is the
        # ``wave.Wave_write`` used by ``_record_block``.
        self._record_writer: object | None = None
        # Bounded queues so a slow whisper model (small / medium / large
        # on CPU int8 can take several seconds per 5-s chunk) can't grow
        # the backlog without end.  Producers drop the oldest block
        # when full (see ``_put_drop_oldest``) so transcription stays
        # near real-time and memory is capped to ~20 blocks × 32 KB.
        self._audio_queue: queue.Queue[np.ndarray] = queue.Queue(
            maxsize=_QUEUE_MAX_BLOCKS,
        )
        self._is_running = False
        self._stream = None
        # Generic system-audio capture process + reader thread.  On
        # Linux this is parec; on macOS/Windows it's an ffmpeg subprocess.
        # All three emit raw 16-kHz s16le mono PCM on stdout, so the
        # reader thread is identical regardless of platform.
        self._sys_audio_proc: subprocess.Popen | None = None
        self._sys_audio_thread: threading.Thread | None = None
        self._process_thread: threading.Thread | None = None
        self._sys_queue: queue.Queue[np.ndarray] | None = None

    def start(self) -> None:
        """Starts audio capture and transcription."""
        if self._is_running:
            return

        self._is_running = True
        self._emit_status("live.status_loading_model")

        # Start processing thread (loads model + processes audio)
        self._process_thread = threading.Thread(
            target=self._process_loop,
            daemon=True,
        )
        self._process_thread.start()

    def stop(self) -> None:
        """Stops audio capture and transcription."""
        self._is_running = False
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self._stop_system_audio()
        if self._process_thread is not None:
            self._process_thread.join(timeout=5)
            self._process_thread = None
        self._close_recording()

    def _open_recording(self) -> None:
        """Opens the WAV recording file for the current session.

        No-op when ``record_to`` wasn't set on the constructor.  Errors
        are logged but never propagate — recording is a best-effort
        side channel; failure shouldn't abort the live session.
        """
        if self._record_to is None or self._record_writer is not None:
            return
        try:
            self._record_to.parent.mkdir(parents=True, exist_ok=True)
            # Long-lived wave handle — closed in ``_close_recording``
            # (called from ``stop()``).  Context-manager idiom doesn't
            # fit here: the writer needs to span the whole session.
            writer = wave.open(str(self._record_to), "wb")  # noqa: SIM115
            writer.setnchannels(_CHANNELS)
            writer.setsampwidth(2)  # s16le → 2 bytes/sample
            writer.setframerate(_SAMPLE_RATE)
            self._record_writer = writer
            logger.info("Live recording started: %s", self._record_to)
        except OSError as exc:
            logger.warning(
                "Live recording failed to open %s: %s — continuing without recording",
                self._record_to, exc,
            )
            self._record_writer = None

    def _record_block(self, block: np.ndarray) -> None:
        """Writes a captured audio block to the WAV file when recording.

        Block arrives as float32 in [-1.0, 1.0]; the WAV format uses
        s16le, so we scale and clip to int16 before writing.  Best-
        effort: a write error logs and disables recording for the
        rest of the session rather than crashing the live loop.
        """
        if self._record_writer is None:
            return
        try:
            scaled = np.clip(block * 32767.0, -32768, 32767).astype(np.int16)
            self._record_writer.writeframes(scaled.tobytes())
        except (OSError, ValueError) as exc:
            logger.warning(
                "Live recording write failed: %s — disabling for this session",
                exc,
            )
            with contextlib.suppress(Exception):
                self._record_writer.close()
            self._record_writer = None

    def _close_recording(self) -> None:
        """Closes the WAV writer at session end."""
        if self._record_writer is None:
            return
        with contextlib.suppress(Exception):
            self._record_writer.close()
        self._record_writer = None

    @property
    def is_running(self) -> bool:
        """Returns True if the transcriber is active."""
        return self._is_running

    def _emit_status(self, key: str) -> None:
        """Emits a status message via callback."""
        if self._on_status:
            from src.constants.i18n import tr  # noqa: PLC0415

            self._on_status(tr(key))

    def _audio_callback(
        self,
        indata: np.ndarray,
        _frames: int,
        _time: object,
        _status: object,
    ) -> None:
        """Called by sounddevice for each audio block."""
        if self._is_running:
            _put_drop_oldest(self._audio_queue, indata.copy())

    def _resolve_devices(self) -> int | None:
        """Returns the mic device index and validates system audio if needed.

        Raises:
            ValueError: If system audio is required but not available.
        """
        from src.constants.settings import (  # noqa: PLC0415
            AUDIO_SOURCE_BOTH,
            AUDIO_SOURCE_SYSTEM,
        )

        if (
            self._audio_source in (AUDIO_SOURCE_SYSTEM, AUDIO_SOURCE_BOTH)
            and not check_system_audio_available()
        ):
            raise ValueError("live.error_no_system_audio")

        return self._device

    def _start_system_audio(
        self,
        target_queue: queue.Queue[np.ndarray],
    ) -> None:
        """Spawns the platform-appropriate system-audio capture subprocess.

        Dispatches to :meth:`_start_system_audio_linux` (parec),
        :meth:`_start_system_audio_macos` (ffmpeg + avfoundation), or
        :meth:`_start_system_audio_windows` (ffmpeg + dshow) based on
        ``platform.system()``.  All three populate ``self._sys_audio_proc``
        and start a reader thread on ``self._sys_audio_thread`` that
        feeds 16-kHz mono float32 blocks into *target_queue*.

        Raises ``ValueError("live.error_no_system_audio")`` if the
        platform isn't supported or the prerequisites (PulseAudio
        monitor / virtual loopback device / ffmpeg) are missing.
        """
        system = platform.system()
        if system == "Linux":
            self._start_system_audio_linux(target_queue)
        elif system == "Darwin":
            self._start_system_audio_macos(target_queue)
        elif system == "Windows":
            self._start_system_audio_windows(target_queue)
        else:
            raise ValueError("live.error_no_system_audio")

    def _spawn_pcm_reader(
        self,
        argv: list[str],
        target_queue: queue.Queue[np.ndarray],
    ) -> None:
        """Spawns *argv*, expects raw 16-kHz s16le mono PCM on stdout.

        Shared back-end for the three per-platform capture methods.
        Stores the process on ``self._sys_audio_proc`` and starts a
        reader thread on ``self._sys_audio_thread`` that converts
        bytes → float32 → numpy blocks → *target_queue*.  The reader
        exits when either ``_is_running`` flips to False or the
        subprocess closes its stdout.
        """
        self._sys_audio_proc = subprocess.Popen(  # noqa: S603
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )

        # Reader thread: converts raw bytes → float32 numpy blocks
        bytes_per_block = _BLOCK_SIZE * 2  # 16-bit = 2 bytes per sample

        def _reader() -> None:
            proc = self._sys_audio_proc
            while self._is_running and proc and proc.poll() is None:
                data = proc.stdout.read(bytes_per_block)
                if not data:
                    break
                samples = (
                    np.frombuffer(data, dtype=np.int16).astype(
                        np.float32,
                    )
                    / 32768.0
                )
                _put_drop_oldest(target_queue, samples.reshape(-1, 1))

        self._sys_audio_thread = threading.Thread(target=_reader, daemon=True)
        self._sys_audio_thread.start()

    def _start_system_audio_linux(
        self,
        target_queue: queue.Queue[np.ndarray],
    ) -> None:
        """Captures system audio on Linux via ``parec``.

        Reads raw PCM (s16le, mono, 16 kHz) from the default sink's
        monitor source.  Requires PulseAudio or PipeWire-pulse to be
        running so a default sink (and its ``.monitor`` source) exists.
        """
        monitor = _get_default_monitor_source()
        if monitor is None:
            raise ValueError("live.error_no_system_audio")
        self._spawn_pcm_reader(
            [
                "parec",
                f"--device={monitor}",
                "--format=s16le",
                "--channels=1",
                f"--rate={_SAMPLE_RATE}",
                "--raw",
            ],
            target_queue,
        )

    def _start_system_audio_macos(
        self,
        target_queue: queue.Queue[np.ndarray],
    ) -> None:
        """Captures system audio on macOS via ffmpeg + avfoundation.

        CoreAudio doesn't expose the system mix natively, so the user
        must have a virtual loopback device installed (BlackHole,
        Loopback, Soundflower, iShowU).  We auto-detect the device
        index from ``ffmpeg -list_devices`` so the user doesn't have
        to configure anything beyond installing the loopback driver.

        ``-fflags nobuffer`` + ``-flags low_delay`` keep added latency
        below the 5-second STT chunk size; ``-acodec pcm_s16le`` plus
        ``-f s16le -`` writes raw PCM straight to stdout for the
        shared reader thread.
        """
        idx = _get_macos_loopback_device_index()
        if idx is None:
            raise ValueError("live.error_no_system_audio")
        # avfoundation input syntax: ":<audio_idx>" means no video,
        # audio device index <audio_idx>.
        self._spawn_pcm_reader(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error",
                "-fflags", "nobuffer", "-flags", "low_delay",
                "-f", "avfoundation",
                "-i", f":{idx}",
                "-ar", str(_SAMPLE_RATE),
                "-ac", "1",
                "-acodec", "pcm_s16le",
                "-f", "s16le",
                "-",
            ],
            target_queue,
        )

    def _start_system_audio_windows(
        self,
        target_queue: queue.Queue[np.ndarray],
    ) -> None:
        """Captures system audio on Windows.

        Tries the ``soundcard`` package first — it talks to WASAPI's
        native loopback flag directly, so the user doesn't need to
        install any extra software on a modern Windows machine.  Falls
        back to ``ffmpeg -f dshow`` against a virtual-loopback
        DirectShow device (``virtual-audio-capturer`` from Screen
        Capture Recorder, VB-Audio Virtual Cable, or legacy
        ``Stereo Mix``) when soundcard isn't importable or fails to
        initialise — this preserves compatibility with users who
        already have a virtual cable installed from a prior version.
        """
        # Preferred path: native WASAPI loopback via soundcard.  No
        # extra software install needed; matches the way Tauri/Rust
        # apps grab system audio on Windows.
        try:
            self._start_system_audio_windows_soundcard(target_queue)
            return
        except (ImportError, OSError) as exc:
            logger.info(
                "soundcard unavailable on this Windows install (%s); "
                "falling back to ffmpeg + DirectShow.",
                exc,
            )
        except Exception as exc:  # noqa: BLE001 - soundcard surfaces wide errors
            logger.warning(
                "soundcard loopback failed (%s); falling back to "
                "ffmpeg + DirectShow.",
                exc,
            )

        # Fallback path: ffmpeg + dshow + virtual cable.
        device = _get_windows_loopback_device_name()
        if device is None:
            raise ValueError("live.error_no_system_audio")
        self._spawn_pcm_reader(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error",
                "-fflags", "nobuffer", "-flags", "low_delay",
                "-f", "dshow",
                "-i", f"audio={device}",
                "-ar", str(_SAMPLE_RATE),
                "-ac", "1",
                "-acodec", "pcm_s16le",
                "-f", "s16le",
                "-",
            ],
            target_queue,
        )

    def _start_system_audio_windows_soundcard(
        self,
        target_queue: queue.Queue[np.ndarray],
    ) -> None:
        """Captures Windows system audio via the ``soundcard`` package.

        Opens a loopback recorder against the default speaker — this
        is WASAPI's native loopback mode, available on every Windows
        version since Vista, no virtual cable required.  The recorder
        yields float32 numpy frames at 16 kHz mono (the same shape the
        rest of the pipeline expects), so we push them straight into
        *target_queue*.

        Reader thread polls ``record(numframes=_BLOCK_SIZE)`` until
        ``_is_running`` flips to False.  No subprocess to manage —
        ``_stop_system_audio`` only needs to wait for the thread to
        notice the flag and exit naturally.

        Raises ``ImportError`` if ``soundcard`` isn't installed (the
        outer dispatcher catches this and falls back to ffmpeg+dshow).
        """
        import soundcard as sc  # noqa: PLC0415

        speaker = sc.default_speaker()
        if speaker is None:
            raise OSError("no default speaker")
        # ``include_loopback=True`` is the Windows-only flag that turns
        # a speaker into a recordable loopback source.  Soundcard
        # opens it via WASAPI's AUDCLNT_STREAMFLAGS_LOOPBACK.
        loopback_mic = sc.get_microphone(
            id=str(speaker.id),
            include_loopback=True,
        )

        def _reader() -> None:
            try:
                with loopback_mic.recorder(
                    samplerate=_SAMPLE_RATE,
                    channels=_CHANNELS,
                    blocksize=_BLOCK_SIZE,
                ) as rec:
                    while self._is_running:
                        # ``record`` returns float32 in [-1, 1] shaped
                        # (frames, channels) — already the format the
                        # rest of the pipeline expects.
                        block = rec.record(numframes=_BLOCK_SIZE)
                        if block is None or len(block) == 0:
                            continue
                        _put_drop_oldest(target_queue, block)
            except Exception as exc:  # noqa: BLE001 - thread-side, log only
                logger.warning("soundcard reader thread exited: %s", exc)

        self._sys_audio_thread = threading.Thread(target=_reader, daemon=True)
        self._sys_audio_thread.start()

    def _stop_system_audio(self) -> None:
        """Terminates the system-audio capture subprocess if running.

        Platform-agnostic: works for both the parec (Linux) and ffmpeg
        (macOS / Windows) processes, since :meth:`_start_system_audio`
        stashes them all on the same ``_sys_audio_proc`` /
        ``_sys_audio_thread`` attributes.

        Hardened against subprocesses that ignore SIGTERM — if
        ``proc.wait(timeout=3)`` raises ``subprocess.TimeoutExpired``
        we escalate to ``proc.kill()`` (SIGKILL) and wait a final
        second.  Without this, a hung child process would (a) leave
        ``self._sys_audio_proc`` pointing at a defunct Popen so the
        next ``_stop_system_audio`` call would re-enter the same
        terminate→wait→raise loop, and (b) skip the reader-thread
        join below, leaking the thread reference for the rest of
        the session.
        """
        proc = getattr(self, "_sys_audio_proc", None)
        if proc is not None:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                logger.warning(
                    "System-audio subprocess ignored SIGTERM after 3s; "
                    "escalating to SIGKILL.",
                )
                with contextlib.suppress(Exception):
                    proc.kill()
                with contextlib.suppress(subprocess.TimeoutExpired):
                    proc.wait(timeout=1)
            except Exception as exc:  # noqa: BLE001 - log + continue cleanup
                logger.warning(
                    "Error stopping system-audio subprocess: %s",
                    exc,
                )
            finally:
                self._sys_audio_proc = None
        thread = getattr(self, "_sys_audio_thread", None)
        if thread is not None:
            thread.join(timeout=3)
            self._sys_audio_thread = None

    def _open_streams(
        self,
        sd: types.ModuleType,
        mic_dev: int | None,
    ) -> None:
        """Opens audio source(s) based on audio_source setting."""
        from src.constants.settings import (  # noqa: PLC0415
            AUDIO_SOURCE_BOTH,
            AUDIO_SOURCE_MICROPHONE,
            AUDIO_SOURCE_SYSTEM,
        )

        stream_kwargs: dict[str, int | str] = {
            "samplerate": _SAMPLE_RATE,
            "channels": _CHANNELS,
            "blocksize": _BLOCK_SIZE,
            "dtype": "float32",
        }

        if self._audio_source in (AUDIO_SOURCE_MICROPHONE, AUDIO_SOURCE_BOTH):
            self._stream = sd.InputStream(
                **stream_kwargs,
                device=mic_dev,
                callback=self._audio_callback,
            )
            self._stream.start()

        if self._audio_source in (AUDIO_SOURCE_SYSTEM, AUDIO_SOURCE_BOTH):
            target = self._audio_queue
            if self._audio_source == AUDIO_SOURCE_BOTH:
                self._sys_queue = queue.Queue(maxsize=_QUEUE_MAX_BLOCKS)
                target = self._sys_queue
            self._start_system_audio(target)

    def _read_block(self) -> np.ndarray | None:
        """Reads the next audio block, mixing if in 'both' mode.

        Also mirrors the block to the recording WAV file when
        ``record_to`` was set on the constructor.  Done here (after
        mixing, before STT) so the recording matches what Whisper
        actually transcribed — same single-source or mixed waveform
        the user heard.

        Returns:
            Audio block as numpy array, or None on timeout.
        """
        block = self._read_block_raw()
        if block is not None:
            self._record_block(block)
        return block

    def _read_block_raw(self) -> np.ndarray | None:
        """Returns the next captured block (no recording side effect)."""
        from src.constants.settings import AUDIO_SOURCE_BOTH  # noqa: PLC0415

        if self._audio_source != AUDIO_SOURCE_BOTH:
            try:
                return self._audio_queue.get(timeout=0.5)
            except queue.Empty:
                return None

        # "both" mode: pull one block from each queue in order (FIFO)
        # and mix them.  Both sources produce at ~2 blocks/sec, so the
        # mic wait rarely hits the 0.5 s ceiling and the sys wait
        # almost always returns immediately with the matching block.
        mic_block = next_block(self._audio_queue, timeout=0.5)
        sys_block = next_block(self._sys_queue, timeout=0.5)

        # Skip a mic block that's effectively silent — it only adds
        # room hiss to the mix.  The user's system audio (Chrome, etc.)
        # is usually the primary content anyway; folding in silent-mic
        # noise can tip whisper's quality thresholds on borderline
        # audio and produce empty transcripts.
        if mic_block is not None:
            mic_rms = float(np.sqrt(np.mean(mic_block**2)))
            if mic_rms < _SILENCE_THRESHOLD:
                mic_block = None

        if mic_block is not None and sys_block is not None:
            return np.clip(mic_block + sys_block, -1.0, 1.0)
        return mic_block if mic_block is not None else sys_block

    def _process_loop(self) -> None:  # noqa: PLR0912, PLR0915
        """Main processing loop: validate audio, load model, transcribe."""
        global _cached_model, _cached_model_size  # noqa: PLW0603
        import sounddevice as sd  # noqa: PLC0415
        from faster_whisper import WhisperModel  # noqa: PLC0415

        try:
            # Pre-check: validate audio before spending time loading model
            audio_err = check_audio_available()
            if audio_err:
                self._emit_status(audio_err)
                return

            # Resolve audio devices for the selected source mode
            mic_dev = self._resolve_devices()

            # Load or reuse cached Whisper model
            if _cached_model is not None and _cached_model_size == self._model_size:
                model = _cached_model
            else:
                self._emit_status("live.status_loading_model")
                model = WhisperModel(
                    self._model_size,
                    device="cpu",
                    compute_type="int8",
                )
                _cached_model = model
                _cached_model_size = self._model_size

            self._emit_status("live.status_listening")

            # Resolve language code
            lang_code = None
            if self._language:
                from src.core.speech_engine import (  # noqa: PLC0415
                    _get_speech_language_code,
                )

                lang_code = _get_speech_language_code(self._language)
                if lang_code and "-" in lang_code:
                    lang_code = lang_code.split("-")[0]

            # Start audio stream(s)
            self._open_streams(sd, mic_dev)
            # Open the recording WAV file (if configured) AFTER the
            # streams start, so the recording matches actual capture
            # rather than starting with silence while we wait for the
            # first block.  No-op when ``record_to`` is None.
            self._open_recording()

            # Process audio blocks
            audio_buffer: list[np.ndarray] = []
            silence_count = 0
            buffer_start_time = 0.0  # seconds since start
            block_counter = 0  # total blocks received

            while self._is_running:
                block = self._read_block()
                if block is None:
                    continue

                block_counter += 1

                # Check if block is silence
                rms = float(np.sqrt(np.mean(block**2)))
                is_silent = rms < _SILENCE_THRESHOLD

                if is_silent:
                    silence_count += 1
                    # If enough silence after speech, transcribe
                    if (
                        silence_count >= _SILENCE_BLOCKS
                        and len(audio_buffer) >= _MIN_AUDIO_BLOCKS
                    ):
                        end_time = block_counter * _BLOCK_DURATION
                        self._transcribe_buffer(
                            model,
                            audio_buffer,
                            lang_code,
                            buffer_start_time,
                            end_time,
                        )
                        audio_buffer.clear()
                        silence_count = 0
                else:
                    silence_count = 0
                    if not audio_buffer:
                        buffer_start_time = (block_counter - 1) * _BLOCK_DURATION
                    audio_buffer.append(block)

                    # Force transcription after max buffer duration
                    if len(audio_buffer) >= _MAX_BUFFER_BLOCKS:
                        end_time = block_counter * _BLOCK_DURATION
                        self._transcribe_buffer(
                            model,
                            audio_buffer,
                            lang_code,
                            buffer_start_time,
                            end_time,
                        )
                        audio_buffer.clear()
                        silence_count = 0

            # Flush remaining audio
            if audio_buffer and len(audio_buffer) >= _MIN_AUDIO_BLOCKS:
                end_time = block_counter * _BLOCK_DURATION
                self._transcribe_buffer(
                    model,
                    audio_buffer,
                    lang_code,
                    buffer_start_time,
                    end_time,
                )

        except ValueError as exc:
            # Expected errors (e.g. no system audio device)
            err_key = str(exc)
            self._emit_status(err_key)
        except Exception as exc:
            logger.error("Live transcription error: %s", exc)
            if self._on_status:
                try:
                    self._on_status(str(exc))
                except Exception:
                    logger.debug("Status callback also failed", exc_info=True)
        finally:
            self._is_running = False
            if self._on_stopped:
                try:
                    self._on_stopped()
                except Exception:
                    logger.debug("on_stopped callback failed", exc_info=True)

    def _transcribe_buffer(
        self,
        model: WhisperModel,
        audio_blocks: list[np.ndarray],
        lang_code: str | None,
        start_sec: float = 0.0,
        end_sec: float = 0.0,
    ) -> None:
        """Transcribes accumulated audio blocks.

        Args:
            model: The Whisper model instance.
            audio_blocks: List of audio numpy arrays to transcribe.
            lang_code: Language code for Whisper, or None for auto.
            start_sec: Start time in seconds since capture began.
            end_sec: End time in seconds since capture began.
        """
        audio = np.concatenate(audio_blocks, axis=0).flatten()

        # faster-whisper defaults cause two known failure modes on live
        # audio: (a) hallucinated repeating tokens on silence or noise
        # chunks — ``condition_on_previous_text=False`` and the built-in
        # silero ``vad_filter=True`` together kill this; (b) garbage
        # segments that the quality gates (``compression_ratio_threshold``,
        # ``no_speech_threshold``) *should* reject but sometimes let
        # through.  Setting the thresholds explicitly makes them
        # consistent across backend defaults.
        kwargs: dict[str, Any] = {
            "word_timestamps": False,
            "vad_filter": True,
            "vad_parameters": {"min_silence_duration_ms": 500},
            "condition_on_previous_text": False,
            "no_speech_threshold": 0.6,
            "compression_ratio_threshold": 2.4,
        }
        if lang_code:
            kwargs["language"] = lang_code

        segments, _ = model.transcribe(audio, **kwargs)

        text_parts = []
        for segment in segments:
            text = segment.text.strip()
            if text:
                text_parts.append(text)

        if text_parts:
            full_text = " ".join(text_parts)
            self._on_sentence(full_text, start_sec, end_sec)
