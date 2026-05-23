"""Speech engine for subtitle generation (STT) and voice generation (TTS).

Speech-to-Text backends:
- faster-whisper: local/offline transcription via CTranslate2.
- Google Cloud Speech-to-Text v1 REST API (``longrunningrecognize``).
Audio is converted to FLAC via FFmpeg before sending to the Google API.

Text-to-Speech backends:
- Edge TTS: free, async synthesis via Microsoft Edge online service.
- ElevenLabs TTS: high-quality neural voice synthesis via REST API.
- Google Cloud Text-to-Speech v1 REST API.
Text is split into API-sized chunks, each synthesized to a temp file,
then concatenated via FFmpeg. Memory-safe by design — audio data is written
to disk immediately, never accumulated in memory.
"""

from __future__ import annotations

import base64
import json
import logging
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.utils.config_manager import load_google_cloud_api_key

if TYPE_CHECKING:
    from src.utils.subtitle_utils import SubtitleEntry

logger = logging.getLogger("speech_engine")

# Google Cloud Speech-to-Text API base URL
_SPEECH_API_BASE = "https://speech.googleapis.com/v1"

# Maximum inline audio size (10 MB base64 ≈ 7.5 MB raw)
_MAX_AUDIO_BYTES = 10 * 1024 * 1024

# Polling intervals for long-running operations
_POLL_INITIAL_DELAY = 2.0
_POLL_MAX_DELAY = 15.0
_POLL_BACKOFF_FACTOR = 1.5

# Maximum characters per subtitle line
_MAX_CHARS_PER_SEGMENT = 80

# Maximum duration (seconds) per subtitle segment
_MAX_SEGMENT_DURATION = 5.0


def check_ffmpeg_available() -> bool:
    """Checks if FFmpeg is available on the system PATH."""
    return shutil.which("ffmpeg") is not None


def _get_speech_language_code(src_lang: str) -> str:
    """Maps a language label to a BCP-47 code for Speech-to-Text.

    Args:
        src_lang: Language label (e.g. "Vietnamese"). Empty for auto-detect.

    Returns:
        BCP-47 language code (e.g. "vi-VN"), or empty string for auto.
    """
    if not src_lang:
        return ""

    from src.constants.languages import get_locale_code  # noqa: PLC0415

    return get_locale_code(src_lang)


def _extract_audio_to_flac(file_path: str) -> Path:
    """Converts an audio/video file to FLAC format using FFmpeg.

    Args:
        file_path: Path to the source audio/video file.

    Returns:
        Path to the temporary FLAC file.

    Raises:
        RuntimeError: If FFmpeg is not available or conversion fails.
    """
    if not check_ffmpeg_available():
        raise RuntimeError("FFMPEG_NOT_FOUND")

    temp_dir = Path(tempfile.mkdtemp(prefix="subtitle_"))
    flac_path = temp_dir / "audio.flac"

    try:
        subprocess.run(  # noqa: S603
            [
                "ffmpeg",
                "-i",
                str(file_path),
                "-ac",
                "1",  # mono channel
                "-ar",
                "16000",  # 16kHz sample rate
                "-f",
                "flac",  # FLAC format
                "-y",  # overwrite
                str(flac_path),
            ],
            capture_output=True,
            check=True,
            timeout=300,
        )
    except subprocess.CalledProcessError as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        msg = e.stderr.decode("utf-8", errors="replace")[:500]
        logger.error("FFmpeg conversion failed: %s", msg)
        raise RuntimeError("FFMPEG_CONVERSION_FAILED") from e
    except subprocess.TimeoutExpired as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise RuntimeError("FFMPEG_NOT_FOUND") from e
    except FileNotFoundError as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise RuntimeError("FFMPEG_NOT_FOUND") from e

    return flac_path


def _call_long_running_recognize(
    audio_content_b64: str,
    language_code: str,
    api_key: str,
    model: str = "default",
) -> str:
    """Sends a longrunningrecognize request and returns the operation name.

    Args:
        audio_content_b64: Base64-encoded audio content.
        language_code: BCP-47 language code (e.g. "en-US").
        api_key: Google Cloud API key.
        model: Google Cloud STT model name.

    Returns:
        Operation name string for polling.
    """
    url = f"{_SPEECH_API_BASE}/speech:longrunningrecognize?key={api_key}"

    config: dict = {
        "encoding": "FLAC",
        "sampleRateHertz": 16000,
        "enableWordTimeOffsets": True,
        "enableAutomaticPunctuation": True,
        "model": model,
    }
    if language_code:
        config["languageCode"] = language_code
    else:
        config["languageCode"] = "en-US"

    payload = {
        "config": config,
        "audio": {"content": audio_content_b64},
    }

    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
    )

    logger.debug("Speech-to-Text request: lang=%s", language_code)
    try:
        with urllib.request.urlopen(req, timeout=60) as response:  # noqa: S310
            result = json.loads(response.read().decode("utf-8"))
            return result["name"]
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")[:500]
        logger.error("STT API error %d: %s", e.code, error_body)
        if e.code in (401, 403):
            raise ValueError("AUTH_ERROR:Google Cloud") from e
        if e.code == 429:  # noqa: PLR2004
            raise ValueError("QUOTA_ERROR") from e
        if e.code == 400:  # noqa: PLR2004
            # Google's quirk (shared with TTS + Gemini): invalid API
            # keys return HTTP 400 with the auth-failure reason in
            # the body — NOT 401/403 like most APIs.  Heuristic:
            # if BOTH "api" and "key" appear in the body it's almost
            # certainly an auth failure (non-auth 400s rarely
            # mention both words together).
            body_lower = error_body.lower()
            if "api" in body_lower and "key" in body_lower:
                raise ValueError("AUTH_ERROR:Google Cloud") from e
        raise ValueError(f"SPEECH_API_ERROR: HTTP {e.code}") from e


def _poll_operation(
    operation_name: str,
    api_key: str,
    is_cancelled: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Polls a long-running operation until completion.

    Args:
        operation_name: The operation name to poll.
        api_key: Google Cloud API key.
        is_cancelled: Optional callback to check for cancellation.

    Returns:
        The completed operation response dict.

    Raises:
        ValueError: If the operation fails.
    """
    url = f"https://speech.googleapis.com/v1/operations/{operation_name}?key={api_key}"
    delay = _POLL_INITIAL_DELAY

    while True:
        if is_cancelled and is_cancelled():
            raise ValueError("CANCELLED")

        time.sleep(delay)

        req = urllib.request.Request(url)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
                result = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")[:500]
            logger.error("STT poll error %d: %s", e.code, error_body)
            if e.code in (401, 403):
                raise ValueError("AUTH_ERROR:Google Cloud") from e
            if e.code == 429:  # noqa: PLR2004
                raise ValueError("QUOTA_ERROR") from e
            if e.code == 400:  # noqa: PLR2004
                # Same Google quirk as the submit handler above:
                # 400 + ``API_KEY_INVALID`` body for invalid keys.
                body_lower = error_body.lower()
                if "api" in body_lower and "key" in body_lower:
                    raise ValueError("AUTH_ERROR:Google Cloud") from e
            raise ValueError(f"SPEECH_API_ERROR: HTTP {e.code}") from e

        if result.get("done"):
            if "error" in result:
                error = result["error"]
                msg = error.get("message", "Unknown error")
                raise ValueError(f"SPEECH_API_ERROR: {msg}")
            return result.get("response", {})

        # Exponential backoff
        delay = min(delay * _POLL_BACKOFF_FACTOR, _POLL_MAX_DELAY)


def _parse_results_to_srt(results: list[dict[str, Any]]) -> str:
    """Converts Speech-to-Text results to SRT subtitle format.

    Groups words into segments of reasonable length/duration.

    Args:
        results: The ``results`` list from the Speech-to-Text response.

    Returns:
        SRT-formatted subtitle string.
    """
    # Collect all words with timing
    words: list[dict] = []
    for result in results:
        alts = result.get("alternatives", [{}])
        alt = alts[0] if alts else {}
        for word_info in alt.get("words", []):
            words.append(word_info)

    if not words:
        # Fall back to transcript-only (no word timing)
        lines = []
        for i, result in enumerate(results, 1):
            alts = result.get("alternatives", [{}])
            alt = alts[0] if alts else {}
            transcript = alt.get("transcript", "").strip()
            if transcript:
                lines.append(f"{i}")
                lines.append("00:00:00,000 --> 00:00:00,000")
                lines.append(transcript)
                lines.append("")
        return "\n".join(lines)

    # Group words into subtitle segments
    segments: list[tuple[float, float, str]] = []
    seg_words: list[str] = []
    seg_start: float = 0.0
    seg_end: float = 0.0

    for word_info in words:
        start = _parse_duration(word_info.get("startTime", "0s"))
        end = _parse_duration(word_info.get("endTime", "0s"))
        word = word_info.get("word", "")

        if not seg_words:
            seg_start = start

        current_text = " ".join(seg_words + [word])
        duration = end - seg_start

        # Split if too long or too much time
        if seg_words and (
            len(current_text) > _MAX_CHARS_PER_SEGMENT
            or duration > _MAX_SEGMENT_DURATION
        ):
            segments.append((seg_start, seg_end, " ".join(seg_words)))
            seg_words = [word]
            seg_start = start
        else:
            seg_words.append(word)

        seg_end = end

    # Flush remaining
    if seg_words:
        segments.append((seg_start, seg_end, " ".join(seg_words)))

    # Format as SRT
    lines: list[str] = []
    for i, (start, end, text) in enumerate(segments, 1):
        lines.append(str(i))
        lines.append(f"{_format_srt_time(start)} --> {_format_srt_time(end)}")
        lines.append(text)
        lines.append("")

    return "\n".join(lines)


def _parse_duration(duration_str: str) -> float:
    """Parses a Google API duration string (e.g. '1.500s') to seconds."""
    if duration_str.endswith("s"):
        duration_str = duration_str[:-1]
    try:
        return float(duration_str)
    except ValueError:
        return 0.0


def _format_srt_time(seconds: float) -> str:
    """Formats seconds to SRT timestamp (HH:MM:SS,mmm)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _transcribe_whisper(
    file_path: str,
    src_lang: str = "",
    model_size: str = "base",
) -> str:
    """Transcribes audio using faster-whisper (local, offline).

    Args:
        file_path: Path to the audio/video file.
        src_lang: Source language label. Empty for auto-detect.
        model_size: Whisper model size (tiny, base, small, medium, large).

    Returns:
        SRT-formatted subtitle string.
    """
    from faster_whisper import WhisperModel  # noqa: PLC0415

    logger.debug("Whisper transcribe: model=%s, lang=%s", model_size, src_lang)

    model = WhisperModel(model_size, device="cpu", compute_type="int8")

    # Resolve language code for Whisper (ISO 639-1)
    lang_code = _get_speech_language_code(src_lang) if src_lang else None
    # Whisper uses short codes like "vi", "en", "ja"
    if lang_code and "-" in lang_code:
        lang_code = lang_code.split("-")[0]

    kwargs: dict[str, object] = {"word_timestamps": False}
    if lang_code:
        kwargs["language"] = lang_code

    segments, _info = model.transcribe(file_path, **kwargs)

    # Convert segments to SRT
    lines: list[str] = []
    for i, segment in enumerate(segments, 1):
        lines.append(str(i))
        lines.append(
            f"{_format_srt_time(segment.start)} --> {_format_srt_time(segment.end)}"
        )
        lines.append(segment.text.strip())
        lines.append("")

    return "\n".join(lines)


def _transcribe_google_cloud(
    file_path: str,
    src_lang: str = "",
    model: str = "default",
    is_cancelled: Callable[[], bool] | None = None,
) -> str:
    """Transcribes audio using Google Cloud Speech-to-Text API.

    Args:
        file_path: Path to the audio/video file.
        src_lang: Source language label. Empty for auto-detect.
        model: Google Cloud STT model name.
        is_cancelled: Optional callback for cancellation.

    Returns:
        SRT-formatted subtitle string.
    """
    api_key = load_google_cloud_api_key()
    if not api_key:
        raise ValueError("AUTH_ERROR:Google Cloud")

    flac_path = _extract_audio_to_flac(file_path)
    try:
        flac_size = flac_path.stat().st_size
        if flac_size > _MAX_AUDIO_BYTES:
            raise ValueError(
                f"AUDIO_TOO_LARGE: {flac_size // (1024 * 1024)}MB"
                f" exceeds {_MAX_AUDIO_BYTES // (1024 * 1024)}MB limit"
            )

        audio_b64 = base64.b64encode(flac_path.read_bytes()).decode("utf-8")
        lang_code = _get_speech_language_code(src_lang)

        operation_name = _call_long_running_recognize(
            audio_b64,
            lang_code,
            api_key,
            model=model,
        )
        response = _poll_operation(operation_name, api_key, is_cancelled)

        results = response.get("results", [])
        return _parse_results_to_srt(results)

    finally:
        shutil.rmtree(flac_path.parent, ignore_errors=True)


def transcribe_audio(  # noqa: PLR0913
    file_path: str,
    src_lang: str = "",
    *,
    stt_method: str = "",
    model_size: str = "base",
    google_model: str = "default",
    is_cancelled: Callable[[], bool] | None = None,
) -> str:
    """Transcribes an audio/video file to SRT subtitle format.

    Dispatches to Whisper (local) or Google Cloud STT based on
    ``stt_method``.

    Args:
        file_path: Path to the audio/video file.
        src_lang: Source language label (e.g. "Vietnamese"). Empty for auto.
        stt_method: STT engine ("Whisper" or "Google Cloud").
        model_size: Whisper model size (only for Whisper).
        google_model: Google Cloud STT model (only for Google Cloud).
        is_cancelled: Optional callback for cancellation.

    Returns:
        SRT-formatted subtitle string.

    Raises:
        ValueError: On API errors or missing credentials.
        RuntimeError: On FFmpeg errors.
    """
    from src.constants.settings import STT_WHISPER  # noqa: PLC0415

    if stt_method == STT_WHISPER:
        return _transcribe_whisper(file_path, src_lang, model_size)
    return _transcribe_google_cloud(
        file_path,
        src_lang,
        model=google_model,
        is_cancelled=is_cancelled,
    )


# ── Text-to-Speech (TTS) ──────────────────────────────────────────────────

# Google Cloud TTS API endpoint
_TTS_API_URL = "https://texttospeech.googleapis.com/v1/text:synthesize"

# Conservative byte limit per TTS request (API allows 5000)
_TTS_MAX_BYTES = 4500

# Sentence-splitting regex: split after sentence-ending punctuation
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?。！？])\s+")

# Mapping from BCP-47 locale codes to Google Cloud TTS language codes.
_TTS_LANG_MAP: dict[str, str] = {
    "ar": "ar-XA",
    "bn": "bn-IN",
    "bg": "bg-BG",
    "zh-CN": "cmn-CN",
    "zh-TW": "cmn-TW",
    "cs": "cs-CZ",
    "da": "da-DK",
    "nl": "nl-NL",
    "en-UK": "en-GB",
    "en-US": "en-US",
    "fi": "fi-FI",
    "fr": "fr-FR",
    "de": "de-DE",
    "el": "el-GR",
    "he": "he-IL",
    "hi": "hi-IN",
    "hu": "hu-HU",
    "id": "id-ID",
    "it": "it-IT",
    "ja": "ja-JP",
    "km": "km-KH",
    "ko": "ko-KR",
    "lv": "lv-LV",
    "lt": "lt-LT",
    "ms": "ms-MY",
    "nb": "nb-NO",
    "fa": "fa-IR",
    "pl": "pl-PL",
    "pt-BR": "pt-BR",
    "pt-PT": "pt-PT",
    "ro": "ro-RO",
    "ru": "ru-RU",
    "sk": "sk-SK",
    "es": "es-ES",
    "sv": "sv-SE",
    "th": "th-TH",
    "tr": "tr-TR",
    "uk": "uk-UA",
    "vi": "vi-VN",
}


def _get_tts_language_code(lang_label: str) -> str:
    """Maps a language label to a Google Cloud TTS language code.

    Args:
        lang_label: Language label (e.g. "Vietnamese").

    Returns:
        TTS language code (e.g. "vi-VN"). Falls back to "en-US".
    """
    if not lang_label:
        return "en-US"

    from src.constants.languages import get_locale_code  # noqa: PLC0415

    locale = get_locale_code(lang_label)
    return _TTS_LANG_MAP.get(locale, locale)


def extract_subtitle_text(content: str, suffix: str = ".srt") -> str:
    """Extracts plain text from subtitle file content.

    Args:
        content: Raw subtitle file content (SRT, VTT, ASS, SSA).
        suffix: File extension for format detection.

    Returns:
        Concatenated text lines without timestamps or metadata.
    """
    from src.utils.subtitle_utils import (  # noqa: PLC0415
        is_subtitle_format,
        parse_subtitle,
    )

    if is_subtitle_format(suffix):
        entries, _ = parse_subtitle(content, suffix)
        return "\n".join(e.text for e in entries if e.text.strip())

    # Plain text fallback
    return content


def _split_text_for_tts(
    text: str,
    max_bytes: int = _TTS_MAX_BYTES,
) -> list[str]:
    """Splits text into chunks that fit within the TTS API byte limit.

    Splits at sentence boundaries first, then word boundaries if needed.

    Args:
        text: Input text to split.
        max_bytes: Maximum bytes per chunk.

    Returns:
        List of text chunks, each within the byte limit.
    """
    text = text.strip()
    if not text:
        return []

    # If entire text fits, return as-is
    if len(text.encode("utf-8")) <= max_bytes:
        return [text]

    # Split by sentences
    sentences = _SENTENCE_SPLIT_RE.split(text)
    chunks: list[str] = []
    current = ""

    for raw_sentence in sentences:
        sentence = raw_sentence.strip()
        if not sentence:
            continue

        test = f"{current} {sentence}".strip() if current else sentence
        if len(test.encode("utf-8")) <= max_bytes:
            current = test
        else:
            # Flush current chunk
            if current:
                chunks.append(current)
            # Check if single sentence fits
            if len(sentence.encode("utf-8")) <= max_bytes:
                current = sentence
            else:
                # Split sentence by words
                current = _split_long_sentence(sentence, max_bytes, chunks)

    if current:
        chunks.append(current)

    return chunks


def _split_long_sentence(
    sentence: str,
    max_bytes: int,
    chunks: list[str],
) -> str:
    """Splits a long sentence by words, appending complete chunks.

    Args:
        sentence: The sentence to split.
        max_bytes: Maximum bytes per chunk.
        chunks: List to append complete chunks to.

    Returns:
        The remaining incomplete chunk.
    """
    words = sentence.split()
    current = ""
    for word in words:
        test = f"{current} {word}".strip() if current else word
        if len(test.encode("utf-8")) <= max_bytes:
            current = test
        else:
            if current:
                chunks.append(current)
            # A single whitespace-bounded "word" can still exceed the
            # cap on CJK / emoji-heavy text where there's no inner
            # whitespace to split on (Chinese / Japanese sentences,
            # long URLs, base64 blobs).  Fall back to a codepoint-
            # safe slice so the chunk passed to the TTS API stays
            # under ``max_bytes`` AND never lands mid-character (which
            # would corrupt multi-byte UTF-8 sequences and either
            # break TTS or produce mojibake audio).
            if len(word.encode("utf-8")) > max_bytes:
                _split_oversized_word(word, max_bytes, chunks)
                current = ""
            else:
                current = word
    return current


def _split_oversized_word(
    word: str,
    max_bytes: int,
    chunks: list[str],
) -> None:
    """Splits a single oversized "word" at codepoint boundaries.

    Used only as the last-resort fallback inside
    :func:`_split_long_sentence` when a whitespace-bounded token's
    UTF-8 encoding already exceeds ``max_bytes`` (typical for CJK
    runs with no inner whitespace).  Walks character-by-character so
    each emitted chunk stays under the limit AND every chunk
    boundary lands on a codepoint boundary — slicing by byte index
    would corrupt multi-byte sequences.  Appends complete chunks to
    *chunks* and returns nothing (no remaining partial: the entire
    oversized word is consumed).
    """
    current = ""
    current_bytes = 0
    for ch in word:
        ch_bytes = len(ch.encode("utf-8"))
        if current_bytes + ch_bytes > max_bytes and current:
            chunks.append(current)
            current = ch
            current_bytes = ch_bytes
        else:
            current += ch
            current_bytes += ch_bytes
    if current:
        chunks.append(current)


# Maximum TTS speaking rate.  Google Cloud TTS's AudioConfig reference
# documents the range as 0.25–2.0 — values above 2.0 are rejected with
# HTTP 400 ``INVALID_ARGUMENT``.  Cap here so the pre-flight clamp in
# ``_synthesize_chunk`` never sends an out-of-range request.  Edge TTS
# uses ffmpeg ``atempo`` for speed-up which goes higher (see
# ``_ATEMPO_MAX_FACTOR``) — that's a separate range and unrelated.
_TTS_MAX_SPEAKING_RATE = 2.0

# Maximum tempo factor for FFmpeg atempo (Edge TTS speed-up)
_ATEMPO_MAX_FACTOR = 4.0

# Minimum TTS speaking rate
_TTS_MIN_SPEAKING_RATE = 0.25

# Overflow tolerance: how far audio may extend past its subtitle end time.
# Capped at the smaller of (ratio * slot_duration) and an absolute maximum.
_OVERFLOW_RATIO = 0.5  # up to 50 % longer than the original slot
_OVERFLOW_MAX_SECONDS = 2.0  # but never more than 2 s

# MP3 constant bitrate assumed for duration estimation (bytes per second)
# Google Cloud TTS outputs ~32kbps MP3 by default
_MP3_BYTES_PER_SECOND = 4000


def _get_mp3_duration(file_path: Path) -> float:
    """Returns the duration of an MP3 file in seconds.

    Uses ffprobe for accurate measurement. Falls back to file-size
    estimation if ffprobe is unavailable.

    Args:
        file_path: Path to the MP3 file.

    Returns:
        Duration in seconds.
    """
    try:
        result = subprocess.run(  # noqa: S603
            [
                "ffprobe",
                "-v",
                "quiet",
                "-show_entries",
                "format=duration",
                "-of",
                "csv=p=0",
                str(file_path),
            ],
            capture_output=True,
            check=True,
            timeout=10,
        )
        return float(result.stdout.decode().strip())
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError):
        # Fallback: estimate from file size
        size = file_path.stat().st_size
        return size / _MP3_BYTES_PER_SECOND if size > 0 else 0.0


def _generate_silence(duration: float, output_path: Path) -> None:
    """Generates a silent MP3 file of the specified duration.

    Args:
        duration: Duration in seconds.
        output_path: Path to write the silent MP3 file.
    """
    subprocess.run(  # noqa: S603
        [
            "ffmpeg",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=24000:cl=mono",
            "-t",
            f"{duration:.3f}",
            "-c:a",
            "libmp3lame",
            "-q:a",
            "9",
            "-y",
            str(output_path),
        ],
        capture_output=True,
        check=True,
        timeout=30,
    )


def _speed_up_audio(input_path: Path, output_path: Path, factor: float) -> None:
    """Speeds up an audio file using FFmpeg's atempo filter.

    FFmpeg atempo only accepts values in [0.5, 100.0], so factors above 2.0
    are chained (e.g. 3.0 → atempo=2.0,atempo=1.5).

    Args:
        input_path: Path to the source audio file.
        output_path: Path to write the sped-up audio.
        factor: Speed-up factor (e.g. 1.5 = 50% faster). Clamped to
            ``_ATEMPO_MAX_FACTOR``.
    """
    factor = min(factor, _ATEMPO_MAX_FACTOR)
    if factor <= 1.0:
        return

    # Build atempo filter chain (each filter maxes at 2.0).
    # Epsilon avoids a useless atempo≈1.0 pass from float rounding.
    _epsilon = 1.01
    filters: list[str] = []
    remaining = factor
    while remaining > _epsilon:
        step = min(remaining, 2.0)
        filters.append(f"atempo={step:.4f}")
        remaining /= step

    # Factor too close to 1.0 — no meaningful speed change needed
    if not filters:
        return

    filter_str = ",".join(filters)

    subprocess.run(  # noqa: S603
        [
            "ffmpeg",
            "-i",
            str(input_path),
            "-filter:a",
            filter_str,
            "-y",
            str(output_path),
        ],
        capture_output=True,
        check=True,
        timeout=60,
    )


def _parse_srt_timestamp(ts: str) -> float:
    """Parses an SRT/VTT timestamp string to seconds.

    Supports both SRT (comma) and VTT (dot) formats:
    ``HH:MM:SS,mmm`` or ``HH:MM:SS.mmm`` or ``MM:SS,mmm``.

    Args:
        ts: Timestamp string.

    Returns:
        Time in seconds.
    """
    ts = ts.strip().replace(",", ".")
    try:
        parts = ts.split(":")
        if len(parts) == 3:  # noqa: PLR2004
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
        if len(parts) == 2:  # noqa: PLR2004
            return float(parts[0]) * 60 + float(parts[1])
    except ValueError:
        pass
    return 0.0


# ── Edge TTS ───────────────────────────────────────────────────────────────

# Mapping from (locale, gender) to Edge TTS voice short names.
# Falls back to en-US voices if the locale is not mapped.
_EDGE_VOICES: dict[str, dict[str, str]] = {
    "ar": {"FEMALE": "ar-EG-SalmaNeural", "MALE": "ar-EG-ShakirNeural"},
    "bn": {"FEMALE": "bn-IN-TanishaaNeural", "MALE": "bn-IN-BashkarNeural"},
    "bg": {"FEMALE": "bg-BG-KalinaNeural", "MALE": "bg-BG-BorislavNeural"},
    "zh-CN": {"FEMALE": "zh-CN-XiaoxiaoNeural", "MALE": "zh-CN-YunxiNeural"},
    "zh-TW": {"FEMALE": "zh-TW-HsiaoChenNeural", "MALE": "zh-TW-YunJheNeural"},
    "hr": {"FEMALE": "hr-HR-GabrijelaNeural", "MALE": "hr-HR-SreckoNeural"},
    "cs": {"FEMALE": "cs-CZ-VlastaNeural", "MALE": "cs-CZ-AntoninNeural"},
    "da": {"FEMALE": "da-DK-ChristelNeural", "MALE": "da-DK-JeppeNeural"},
    "nl": {"FEMALE": "nl-NL-ColetteNeural", "MALE": "nl-NL-MaartenNeural"},
    "en-UK": {"FEMALE": "en-GB-SoniaNeural", "MALE": "en-GB-RyanNeural"},
    "en-US": {"FEMALE": "en-US-JennyNeural", "MALE": "en-US-GuyNeural"},
    "fi": {"FEMALE": "fi-FI-NooraNeural", "MALE": "fi-FI-HarriNeural"},
    "fr": {"FEMALE": "fr-FR-DeniseNeural", "MALE": "fr-FR-HenriNeural"},
    "de": {"FEMALE": "de-DE-KatjaNeural", "MALE": "de-DE-ConradNeural"},
    "el": {"FEMALE": "el-GR-AthinaNeural", "MALE": "el-GR-NestorasNeural"},
    "he": {"FEMALE": "he-IL-HilaNeural", "MALE": "he-IL-AvriNeural"},
    "hi": {"FEMALE": "hi-IN-SwaraNeural", "MALE": "hi-IN-MadhurNeural"},
    "hu": {"FEMALE": "hu-HU-NoemiNeural", "MALE": "hu-HU-TamasNeural"},
    "id": {"FEMALE": "id-ID-GadisNeural", "MALE": "id-ID-ArdiNeural"},
    "it": {"FEMALE": "it-IT-ElsaNeural", "MALE": "it-IT-DiegoNeural"},
    "ja": {"FEMALE": "ja-JP-NanamiNeural", "MALE": "ja-JP-KeitaNeural"},
    "km": {"FEMALE": "km-KH-SresmaNeural", "MALE": "km-KH-PisethNeural"},
    "ko": {"FEMALE": "ko-KR-SunHiNeural", "MALE": "ko-KR-InJoonNeural"},
    "lv": {"FEMALE": "lv-LV-EveritaNeural", "MALE": "lv-LV-NilsNeural"},
    "lt": {"FEMALE": "lt-LT-OnaNeural", "MALE": "lt-LT-LeonasNeural"},
    "ms": {"FEMALE": "ms-MY-YasminNeural", "MALE": "ms-MY-OsmanNeural"},
    "nb": {"FEMALE": "nb-NO-PernilleNeural", "MALE": "nb-NO-FinnNeural"},
    "fa": {"FEMALE": "fa-IR-DilaraNeural", "MALE": "fa-IR-FaridNeural"},
    "pl": {"FEMALE": "pl-PL-ZofiaNeural", "MALE": "pl-PL-MarekNeural"},
    "pt-BR": {"FEMALE": "pt-BR-FranciscaNeural", "MALE": "pt-BR-AntonioNeural"},
    "pt-PT": {"FEMALE": "pt-PT-RaquelNeural", "MALE": "pt-PT-DuarteNeural"},
    "ro": {"FEMALE": "ro-RO-AlinaNeural", "MALE": "ro-RO-EmilNeural"},
    "ru": {"FEMALE": "ru-RU-SvetlanaNeural", "MALE": "ru-RU-DmitryNeural"},
    "sk": {"FEMALE": "sk-SK-ViktoriaNeural", "MALE": "sk-SK-LukasNeural"},
    "es": {"FEMALE": "es-ES-ElviraNeural", "MALE": "es-ES-AlvaroNeural"},
    "sv": {"FEMALE": "sv-SE-SofieNeural", "MALE": "sv-SE-MattiasNeural"},
    "th": {"FEMALE": "th-TH-PremwadeeNeural", "MALE": "th-TH-NiwatNeural"},
    "tr": {"FEMALE": "tr-TR-EmelNeural", "MALE": "tr-TR-AhmetNeural"},
    "uk": {"FEMALE": "uk-UA-PolinaNeural", "MALE": "uk-UA-OstapNeural"},
    "vi": {"FEMALE": "vi-VN-HoaiMyNeural", "MALE": "vi-VN-NamMinhNeural"},
}

# Default fallback voice
_EDGE_DEFAULT_VOICE = "en-US-JennyNeural"


def _get_edge_voice(lang_label: str, gender: str = "FEMALE") -> str:
    """Maps a language label + gender to an Edge TTS voice name.

    Args:
        lang_label: Language label (e.g. "Vietnamese").
        gender: "MALE" or "FEMALE".

    Returns:
        Edge TTS voice name (e.g. "vi-VN-HoaiMyNeural").
    """
    if not lang_label:
        return _EDGE_VOICES["en-US"].get(gender, _EDGE_DEFAULT_VOICE)

    from src.constants.languages import get_locale_code  # noqa: PLC0415

    locale = get_locale_code(lang_label)
    voices = _EDGE_VOICES.get(locale)
    if voices:
        return voices.get(gender, next(iter(voices.values())))
    return _EDGE_DEFAULT_VOICE


def _synthesize_chunk_edge(
    text: str,
    voice: str,
    output_path: Path,
    *,
    max_retries: int = 3,
    base_delay: float = 2.0,
) -> None:
    """Synthesizes a single text chunk using Edge TTS with retry.

    Retries on ``NoAudioReceived`` (transient service error) with
    exponential backoff.

    Args:
        text: Text to synthesize.
        voice: Edge TTS voice name (e.g. "vi-VN-HoaiMyNeural").
        output_path: Path to write the MP3 audio file.
        max_retries: Maximum number of retry attempts.
        base_delay: Initial delay in seconds between retries.
    """
    import asyncio  # noqa: PLC0415

    import edge_tts  # noqa: PLC0415
    from edge_tts.exceptions import NoAudioReceived  # noqa: PLC0415

    async def _run() -> None:
        last_error: Exception | None = None
        _preview = 80  # noqa: PLR2004
        logger.debug(
            "Edge TTS: voice=%s, text=%r",
            voice,
            text[:_preview] + ("..." if len(text) > _preview else ""),
        )
        for attempt in range(max_retries + 1):
            try:
                communicate = edge_tts.Communicate(text, voice)
                await communicate.save(str(output_path))
                return
            except NoAudioReceived as exc:
                last_error = exc
                if attempt < max_retries:
                    delay = base_delay * (2**attempt)
                    logger.warning(
                        "Edge TTS returned no audio (attempt %d/%d),"
                        " retrying in %.1fs...",
                        attempt + 1,
                        max_retries + 1,
                        delay,
                    )
                    await asyncio.sleep(delay)
        # All retries exhausted — wrap with our tag for error display
        raise ValueError(
            f"TTS_API_ERROR: {last_error}",
        ) from last_error

    asyncio.run(_run())


# ── ElevenLabs TTS ─────────────────────────────────────────────────────────

_ELEVENLABS_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech"
_ELEVENLABS_MODEL = "eleven_multilingual_v2"
_ELEVENLABS_DEFAULT_VOICE_FEMALE = "21m00Tcm4TlvDq8ikWAM"  # Rachel
_ELEVENLABS_DEFAULT_VOICE_MALE = "JBFqnCBsd6RMkjVDRZzb"  # George
_ELEVENLABS_DEFAULT_VOICE = _ELEVENLABS_DEFAULT_VOICE_MALE  # legacy fallback

# Curated subset of the ElevenLabs free voice library, grouped by
# gender so the UI can filter the dropdown the same way Gemini's combo
# does.  Voice IDs are stable identifiers from the public catalogue;
# users with cloned / custom voices can still type their own ID via
# the "Custom" escape hatch in the voice picker.
ELEVENLABS_VOICES_BY_GENDER: dict[str, tuple[tuple[str, str], ...]] = {
    # Strictly alphabetical A→Z so the combo reads predictably.
    # The "default" voice (Rachel for FEMALE, George for MALE) is
    # NOT pinned at position 0 any more — call
    # :func:`get_elevenlabs_default_voice_id` for that lookup so the
    # default is decoupled from catalogue order.
    "FEMALE": (
        ("Aria", "9BWtsMINqrJLrRacOk9x"),
        ("Charlotte", "XB0fDUnXU5powFXDhCwa"),
        ("Domi", "AZnzlk1XvdvUeBnXmlld"),
        ("Lily", "pFZP5JQG7iQjIQuC4Bku"),
        ("Matilda", "XrExE9yKIg1WjnnlVkGX"),
        ("Rachel", "21m00Tcm4TlvDq8ikWAM"),
    ),
    "MALE": (
        ("Adam", "pNInz6obpgDQGcFmaJgB"),
        ("Antoni", "ErXwobaYiN019PkySvjV"),
        ("Charlie", "IKne3meq5aSn9XLyUdCD"),
        ("Daniel", "onwK4e9ZLuTAKqWW03F9"),
        ("George", "JBFqnCBsd6RMkjVDRZzb"),
        ("Liam", "TX3LPaxmHKxFdv7VOQHJ"),
    ),
}


def get_elevenlabs_voices_for_gender(gender: str) -> tuple[tuple[str, str], ...]:
    """Returns the curated ElevenLabs voices matching *gender*.

    Falls back to the female list for unknown values so the UI never
    renders an empty combo.

    Args:
        gender: ``"MALE"`` or ``"FEMALE"`` (case-insensitive).

    Returns:
        Tuple of ``(display_name, voice_id)`` pairs from
        :data:`ELEVENLABS_VOICES_BY_GENDER`.
    """
    key = gender.upper() if gender else "FEMALE"
    return ELEVENLABS_VOICES_BY_GENDER.get(
        key,
        ELEVENLABS_VOICES_BY_GENDER["FEMALE"],
    )


def _get_elevenlabs_voice(gender: str) -> str:
    """Returns the gender-default ElevenLabs voice ID."""
    return (
        _ELEVENLABS_DEFAULT_VOICE_MALE
        if gender.upper() == "MALE"
        else _ELEVENLABS_DEFAULT_VOICE_FEMALE
    )


def get_elevenlabs_default_voice_id(gender: str) -> str:
    """Public accessor for the gender-default ElevenLabs voice ID.

    Used by the settings UI to pick the recommended voice when the
    user hasn't saved a preference — the catalogue itself is now
    sorted strictly A→Z so the default can no longer be inferred
    from position 0 of ``ELEVENLABS_VOICES_BY_GENDER``.
    """
    return _get_elevenlabs_voice(gender)


def _synthesize_chunk_elevenlabs(  # noqa: PLR0913 — TTS callers pass several config knobs as positional args; keeping a flat signature avoids forcing every callsite into a wrapper struct
    text: str,
    api_key: str,
    output_path: Path,
    voice_id: str = "",
    model_id: str = "",
    *,
    gender: str = "FEMALE",
) -> None:
    """Synthesizes a single text chunk using ElevenLabs TTS.

    Args:
        text: Text to synthesize.
        api_key: ElevenLabs API key.
        output_path: Path to write the MP3 audio file.
        voice_id: ElevenLabs voice ID.  When empty, falls back to the
            gender-default voice (Rachel for FEMALE, George for MALE).
        model_id: ElevenLabs model ID. Uses ``_ELEVENLABS_MODEL`` when empty.
        gender: Used as the fallback selector when ``voice_id`` is empty.
            Defaults to ``"FEMALE"`` for backward compatibility with
            callers that don't yet thread gender through.
    """
    vid = voice_id or _get_elevenlabs_voice(gender)
    url = f"{_ELEVENLABS_TTS_URL}/{vid}"
    payload = {
        "text": text,
        "model_id": model_id or _ELEVENLABS_MODEL,
    }

    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "xi-api-key": api_key,
            "Accept": "audio/mpeg",
        },
    )

    logger.debug(
        "ElevenLabs TTS: voice=%s, %d bytes",
        vid,
        len(text.encode("utf-8")),
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as response:  # noqa: S310
            output_path.write_bytes(response.read())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")[:500]
        logger.error("ElevenLabs TTS error %d: %s", e.code, error_body)
        if e.code in (401, 403):
            raise ValueError("AUTH_ERROR:ElevenLabs") from e
        if e.code == 429:  # noqa: PLR2004
            raise ValueError("QUOTA_ERROR") from e
        raise ValueError(f"TTS_API_ERROR: HTTP {e.code}") from e


# ── Gemini TTS ─────────────────────────────────────────────────────────────
# Gemini's preview TTS models speak natural, expressive voices in 24+
# languages without per-locale voice setup — pick a "prebuilt" voice
# name and the same model handles everything.  Free tier on the
# Developer API; Vertex routing is identical via the same SDK.
#
# Wire-level differences from the other backends:
#   - Returns RAW PCM (s16le, 24 kHz, mono) base64-encoded inside
#     ``candidates[0].content.parts[0].inlineData.data`` — no MP3, no
#     WAV header.  We pipe the bytes through ffmpeg per-chunk to land
#     in the same MP3 / WAV shape ``_concatenate_mp3_files`` expects.
#   - The endpoint is the standard ``generativelanguage.googleapis.com``
#     ``models/<model>:generateContent`` URL with ``responseModalities=["AUDIO"]``
#     and a ``speechConfig.voiceConfig.prebuiltVoiceConfig.voiceName``.
#   - Uses ``urllib.request`` directly (matching the ElevenLabs / Google
#     Cloud REST patterns) instead of the google-genai SDK, because the
#     SDK's ``generate_content`` doesn't expose ``responseModalities``
#     in a stable shape across versions and we'd need the raw bytes
#     either way for the ffmpeg pipe.
_GEMINI_TTS_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
# All Gemini TTS models are preview-tier today (no GA option exists).
# Tracked alternatives (verified via ``GET /v1beta/models``):
#   - gemini-2.5-flash-preview-tts   (older, slightly slower)
#   - gemini-2.5-pro-preview-tts     (higher quality, tighter quotas)
# Default tracks the ``flash-tts`` line for free-tier latency; bump
# this when Google rotates the preview ID.
_GEMINI_TTS_MODEL = "gemini-3.1-flash-tts-preview"
_GEMINI_TTS_SAMPLE_RATE = 24000  # PCM rate Gemini emits — fixed by the model.

# Per-request input-byte cap for Gemini TTS.  Although the input-token
# limit is ~32K, the binding constraint is the output-audio length
# (~30-60 seconds per call) — not the prompt size.  ~2000 bytes of
# text turns into roughly 25-30 seconds of speech at normal cadence,
# safely under the cap.  We pass this to ``_split_text_for_tts`` so
# longer pasted text chunks at sentence boundaries instead of
# truncating mid-paragraph or hitting the model's audio-length cap.
# (Google Cloud, Edge, and ElevenLabs all use the larger
# ``_TTS_MAX_BYTES = 4500`` because their per-request audio cap is
# minutes, not seconds.)
_GEMINI_TTS_MAX_BYTES = 2000

# Default prebuilt voice per gender.  Picked as clear, neutral
# defaults that work well across languages without sounding too
# character-y.  Users can override via the Voice-tab voice picker
# (``SETTING_GEMINI_TTS_VOICE_NAME``); when blank the gender-default
# applies via :func:`_get_gemini_voice`.
_GEMINI_TTS_VOICE_FEMALE = "Kore"
_GEMINI_TTS_VOICE_MALE = "Puck"

# Curated subset of the Gemini prebuilt voice catalogue surfaced in
# the Voice-tab picker, grouped by gender so the UI can filter the
# dropdown to only voices matching the selected gender — picking a
# male voice when the gender radio is set to Female would silently
# override gender in a confusing way.  Advanced users can paste any
# other catalogue name into the picker (engine accepts unknown names).
GEMINI_TTS_VOICES_BY_GENDER: dict[str, tuple[str, ...]] = {
    # Strictly alphabetical A→Z so the combo reads predictably.
    # The "default" voice (Kore for FEMALE, Puck for MALE) is NOT
    # pinned at position 0 any more — call
    # :func:`get_gemini_default_voice` for that lookup so the
    # default is decoupled from catalogue order.
    "FEMALE": (
        "Aoede",
        "Callirrhoe",
        "Despina",
        "Erinome",
        "Kore",
        "Laomedeia",
        "Sulafat",
        "Vindemiatrix",
        "Zephyr",
    ),
    "MALE": (
        "Charon",
        "Fenrir",
        "Iapetus",
        "Orus",
        "Puck",
        "Schedar",
    ),
}

# Flat union of all gendered voices — kept as the public catalogue
# constant for callers that don't care about gender (engine fallback,
# tests that pin the full set).
GEMINI_TTS_VOICE_CATALOGUE: tuple[str, ...] = (
    *GEMINI_TTS_VOICES_BY_GENDER["FEMALE"],
    *GEMINI_TTS_VOICES_BY_GENDER["MALE"],
)


def get_gemini_voices_for_gender(gender: str) -> tuple[str, ...]:
    """Returns the curated Gemini voices matching *gender*.

    Falls back to the female list for unknown values so the UI never
    renders an empty combo.

    Args:
        gender: ``"MALE"`` or ``"FEMALE"`` (case-insensitive).

    Returns:
        Tuple of voice names from :data:`GEMINI_TTS_VOICES_BY_GENDER`.
    """
    key = gender.upper() if gender else "FEMALE"
    return GEMINI_TTS_VOICES_BY_GENDER.get(key, GEMINI_TTS_VOICES_BY_GENDER["FEMALE"])


def _get_gemini_voice(gender: str) -> str:
    """Returns the default Gemini prebuilt voice name for the given gender.

    Args:
        gender: ``"MALE"`` or ``"FEMALE"`` (case-insensitive).

    Returns:
        A voice name from the Gemini prebuilt catalogue.
    """
    return (
        _GEMINI_TTS_VOICE_MALE if gender.upper() == "MALE" else _GEMINI_TTS_VOICE_FEMALE
    )


def get_gemini_default_voice(gender: str) -> str:
    """Public accessor for the gender-default Gemini voice name.

    Used by the settings UI to pick the recommended voice when the
    user hasn't saved a preference — the catalogue itself is now
    sorted strictly A→Z so the default can no longer be inferred
    from position 0 of ``GEMINI_TTS_VOICES_BY_GENDER``.
    """
    return _get_gemini_voice(gender)


def _synthesize_chunk_gemini(
    text: str,
    api_key: str,
    output_path: Path,
    voice_name: str = "",
    *,
    audio_format: str = ".mp3",
) -> None:
    """Synthesizes a single text chunk using Gemini TTS.

    Posts a JSON request asking for ``responseModalities=["AUDIO"]``,
    receives base64-encoded raw PCM (s16le, 24 kHz mono), then pipes
    those bytes through ffmpeg to land at *output_path* in the
    requested *audio_format*.  Per-chunk ffmpeg is fine — chunks are
    short enough (~5 KB text → ~1 s audio) that the encode cost is
    negligible compared to the network round-trip.

    Args:
        text: Text to synthesize.
        api_key: Gemini API key.
        output_path: Path to write the audio file.
        voice_name: Gemini prebuilt voice name (e.g. ``"Kore"``).
            Defaults to the female voice when empty.
        audio_format: Output container — ``".mp3"`` or ``".wav"``.

    Raises:
        ValueError: With a tagged code (``AUTH_ERROR``, ``QUOTA_ERROR``,
            ``TTS_API_ERROR``) for HTTP failures, ``EMPTY_TEXT`` if
            Gemini returns no audio part.
        RuntimeError: ``FFMPEG_CONVERSION_FAILED`` when the PCM → MP3
            transcode fails.
    """
    voice = voice_name or _GEMINI_TTS_VOICE_FEMALE
    url = f"{_GEMINI_TTS_BASE_URL}/{_GEMINI_TTS_MODEL}:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {
                        "voiceName": voice,
                    },
                },
            },
        },
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
    )
    logger.debug(
        "Gemini TTS: voice=%s, %d bytes",
        voice,
        len(text.encode("utf-8")),
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as response:  # noqa: S310
            response_data = json.loads(response.read())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")[:500]
        logger.error("Gemini TTS error %d: %s", e.code, error_body)
        if e.code in (401, 403):
            raise ValueError("AUTH_ERROR:Gemini") from e
        if e.code == 429:  # noqa: PLR2004
            raise ValueError("QUOTA_ERROR") from e
        raise ValueError(f"TTS_API_ERROR: HTTP {e.code}") from e

    # Pull base64 PCM out of the response.  The JSON shape can vary
    # slightly between SDK versions (sometimes ``inlineData``,
    # sometimes ``inline_data``); accept either to stay robust.
    try:
        parts = response_data["candidates"][0]["content"]["parts"]
        inline = parts[0].get("inlineData") or parts[0].get("inline_data")
        pcm_b64 = inline["data"]
    except (KeyError, IndexError, TypeError) as e:
        logger.error(
            "Gemini TTS returned no audio part: %s",
            json.dumps(response_data)[:500],
        )
        raise ValueError("EMPTY_TEXT") from e

    pcm_bytes = base64.b64decode(pcm_b64)
    if not pcm_bytes:
        raise ValueError("EMPTY_TEXT")

    # PCM → final container via ffmpeg stdin pipe.  Match the existing
    # backends' output shapes so ``_concatenate_mp3_files`` (which
    # uses ``-c copy``) sees uniform format across all chunks.
    codec = "libmp3lame" if audio_format == ".mp3" else "pcm_s16le"
    try:
        subprocess.run(  # noqa: S603
            [
                "ffmpeg",
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "s16le",
                "-ar",
                str(_GEMINI_TTS_SAMPLE_RATE),
                "-ac",
                "1",
                "-i",
                "pipe:0",
                "-codec:a",
                codec,
                str(output_path),
            ],
            input=pcm_bytes,
            capture_output=True,
            check=True,
            timeout=60,
        )
    except subprocess.CalledProcessError as e:
        msg = e.stderr.decode("utf-8", errors="replace")[:500]
        logger.error("Gemini TTS PCM→%s failed: %s", audio_format, msg)
        raise RuntimeError("FFMPEG_CONVERSION_FAILED") from e


# ── Piper TTS (offline) ────────────────────────────────────────────────────

# Size of an empty PCM WAV header — used to detect "Piper produced no
# audio" (the file gets created but only contains the 44-byte header).
_WAV_HEADER_SIZE = 44

# Curated subset of the Piper voice catalogue, grouped by language and
# gender so the engine can resolve ``(target_lang, gender)`` to a
# concrete voice ID without the user having to know voice names.  Voice
# IDs follow Piper's HuggingFace naming convention:
# ``<lang>_<region>-<voice>-<quality>``.  Each is downloaded as a pair
# of files: ``<voice_id>.onnx`` and ``<voice_id>.onnx.json``, fetched
# from the official ``rhasspy/piper-voices`` HF repo.
#
# Quality choice: ``medium`` is the sweet spot — ``low`` sounds robotic,
# ``high`` is 2–3× larger with diminishing returns over medium for
# most languages.  Using ``low`` for languages where ``medium`` isn't
# available (e.g. Vietnamese) is preferable to "no offline support".
PIPER_VOICES_BY_GENDER_AND_LANGUAGE: dict[str, dict[str, str]] = {
    "FEMALE": {
        "Danish": "da_DK-talesyntese-medium",
        "Dutch": "nl_NL-mls-medium",
        "English (UK)": "en_GB-alba-medium",
        "English (US)": "en_US-amy-medium",
        "French": "fr_FR-siwis-medium",
        "German": "de_DE-eva_k-x_low",
        "Greek": "el_GR-rapunzelina-medium",
        "Hindi": "hi_IN-priyamvada-medium",
        "Hungarian": "hu_HU-anna-medium",
        "Indonesian": "id_ID-news_tts-medium",
        "Italian": "it_IT-paola-medium",
        "Nepali": "ne_NP-chitwan-medium",
        "Persian": "fa_IR-ganji_adabi-medium",
        "Polish": "pl_PL-mc_speech-medium",
        "Russian": "ru_RU-irina-medium",
        "Serbian": "sr_RS-serbski_institut-medium",
        "Slovak": "sk_SK-lili-medium",
        "Spanish": "es_ES-mls_9972-low",
        "Swedish": "sv_SE-alma-medium",
        "Ukrainian": "uk_UA-lada-x_low",
        "Vietnamese": "vi_VN-vais1000-medium",
        "Chinese (Simplified)": "zh_CN-huayan-medium",
    },
    "MALE": {
        "Arabic": "ar_JO-kareem-medium",
        "Bulgarian": "bg_BG-dimitar-medium",
        "Czech": "cs_CZ-jirka-medium",
        "English (UK)": "en_GB-alan-medium",
        "English (US)": "en_US-ryan-medium",
        "Finnish": "fi_FI-harri-medium",
        "French": "fr_FR-tom-medium",
        "German": "de_DE-thorsten-medium",
        "Hindi": "hi_IN-pratham-medium",
        "Hungarian": "hu_HU-imre-medium",
        "Latvian": "lv_LV-aivars-medium",
        "Persian": "fa_IR-amir-medium",
        "Polish": "pl_PL-darkman-medium",
        "Portuguese (Brazil)": "pt_BR-faber-medium",
        "Portuguese (Portugal)": "pt_PT-tugão-medium",
        "Romanian": "ro_RO-mihai-medium",
        "Russian": "ru_RU-dmitri-medium",
        "Slovenian": "sl_SI-artur-medium",
        "Spanish": "es_ES-davefx-medium",
        "Swedish": "sv_SE-nst-medium",
        "Turkish": "tr_TR-dfki-medium",
        "Ukrainian": "uk_UA-ukrainian_tts-medium",
        "Vietnamese": "vi_VN-25hours_single-low",
    },
    # Single-gender languages.  The rhasspy/piper-voices catalogue
    # doesn't ship paired male/female voices for many smaller-corpus
    # languages — entries appear in only one gender map below:
    #
    # - FEMALE only: Italian, Dutch, Chinese (Simplified), Danish,
    #   Greek, Indonesian, Nepali, Serbian, Slovak.
    # - MALE only: Arabic, Bulgarian, Czech, Finnish, Latvian,
    #   Portuguese (Brazil), Portuguese (Portugal), Romanian,
    #   Slovenian, Turkish.
    #
    # ``get_piper_voice_for`` falls back to whichever gender IS
    # populated for the language before dropping to the en_US default,
    # so a MALE-Italian or FEMALE-Arabic request still resolves to an
    # in-language voice instead of speaking English.  Some assignments
    # (Danish "talesyntese", Indonesian "news_tts", Persian
    # "ganji_adabi", Serbian "serbski_institut", Swedish "nst",
    # Turkish "dfki", Nepali "chitwan") are best-guesses based on
    # voice/corpus naming conventions because Piper's voices.json
    # doesn't encode gender — if any of these are wrong, the
    # cross-gender fallback still produces an in-language voice.
}

# HuggingFace base URL for the rhasspy/piper-voices repo.  Each voice
# lives at ``{base}/{lang}/{lang_region}/{voice}/{quality}/{voice_id}.onnx[.json]``.
_PIPER_HF_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main"


def get_piper_voice_for(target_lang: str, gender: str) -> str:
    """Resolves ``(target_lang, gender)`` to a Piper voice ID.

    Resolution order:

    1. The voice mapped to the requested gender for *target_lang*.
    2. The voice mapped to the OTHER gender for *target_lang* — some
       languages (Italian, Dutch, Chinese (Simplified) → female;
       Portuguese → male) only ship a single voice in the rhasspy
       catalogue, so a request for the missing gender falls back to
       the available one rather than dropping the user to en_US.
    3. Empty string when the language isn't in the curated catalogue
       at all — the caller is expected to interpret this as "no
       Piper coverage" and route to a different backend (Edge TTS)
       rather than synthesise English audio for, say, a Japanese
       translation.  Returning a usable-but-wrong-language voice
       (the old en_US-amy fallback) silently mismatched audio to
       text for any user translating into a Piper-unsupported
       language.

    Args:
        target_lang: Language label from ``LANGUAGES`` (e.g. "French").
        gender: ``"MALE"`` or ``"FEMALE"`` (case-insensitive).

    Returns:
        Piper voice ID like ``"fr_FR-siwis-medium"``, or ``""`` when
        no Piper voice exists for *target_lang*.
    """
    key = gender.upper() if gender else "FEMALE"
    if key not in PIPER_VOICES_BY_GENDER_AND_LANGUAGE:
        key = "FEMALE"
    other_key = "MALE" if key == "FEMALE" else "FEMALE"
    by_lang = PIPER_VOICES_BY_GENDER_AND_LANGUAGE[key]
    other_lang = PIPER_VOICES_BY_GENDER_AND_LANGUAGE[other_key]
    return by_lang.get(target_lang) or other_lang.get(target_lang) or ""


def piper_voice_paths(voice_id: str) -> tuple[Path, Path]:
    """Returns the on-disk ``(model_path, config_path)`` for a voice ID.

    Both files may not exist yet — call :func:`is_piper_voice_installed`
    first or :func:`download_piper_voice` to fetch them.
    """
    from src.utils.path_manager import get_piper_voice_dir  # noqa: PLC0415

    base = get_piper_voice_dir()
    model_path = base / f"{voice_id}.onnx"
    config_path = base / f"{voice_id}.onnx.json"
    return model_path, config_path


def is_piper_voice_installed(voice_id: str) -> bool:
    """Returns True iff both the ONNX model and its JSON config are on disk."""
    model_path, config_path = piper_voice_paths(voice_id)
    return model_path.is_file() and config_path.is_file()


def installed_piper_languages() -> set[str]:
    """Returns the English language labels with at least one installed voice.

    Walks :data:`PIPER_VOICES_BY_GENDER_AND_LANGUAGE` and tests each
    voice with :func:`is_piper_voice_installed`; a language is counted
    as installed when ANY of its catalogued voices (across genders) has
    its ``.onnx`` + ``.onnx.json`` pair on disk.

    Used by the settings UI to show a Tesseract-style banner above the
    Piper picker — "Piper TTS: 3 language(s) installed" — without the
    user having to click through every voice row to check.
    """
    installed: set[str] = set()
    for entries in PIPER_VOICES_BY_GENDER_AND_LANGUAGE.values():
        for language, voice_id in entries.items():
            if is_piper_voice_installed(voice_id):
                installed.add(language)
    return installed


def _piper_voice_url(voice_id: str, *, suffix: str) -> str:
    """Builds the HuggingFace URL for a voice file.

    Voice IDs follow ``<lang>_<region>-<voice>-<quality>``.  The HF
    layout is ``{lang}/{lang_region}/{voice}/{quality}/{voice_id}.{suffix}``.
    """
    # Split "en_US-amy-medium" → lang_region="en_US", voice="amy", quality="medium"
    lang_region, voice, quality = voice_id.split("-", 2)
    lang = lang_region.split("_", 1)[0]
    return (
        f"{_PIPER_HF_BASE}/{lang}/{lang_region}/{voice}/{quality}/{voice_id}.{suffix}"
    )


def download_piper_voice(
    voice_id: str,
    on_progress: Callable[[int, int], None] | None = None,
) -> tuple[Path, Path]:
    """Downloads the ONNX + JSON pair for a Piper voice from HuggingFace.

    Atomic-rename pattern: each file is fetched to a ``.partial`` path
    first, then renamed on completion.  A failed/cancelled download
    leaves no half-written file masquerading as a complete voice.

    Args:
        voice_id: Voice ID like ``"en_US-amy-medium"``.
        on_progress: Optional callback ``(bytes_done, bytes_total)``.
            Called periodically during the ONNX download (the larger
            of the two files); the JSON config is small enough to skip.

    Returns:
        ``(model_path, config_path)`` — both files now on disk.

    Raises:
        ValueError: ``"PIPER_DOWNLOAD_FAILED"`` on HTTP / network error.
    """
    model_path, config_path = piper_voice_paths(voice_id)
    if model_path.is_file() and config_path.is_file():
        return model_path, config_path

    try:
        # Config first (small, fast); fail early if the voice ID is wrong
        # so the user doesn't wait for a 50 MB download to discover a typo.
        if not config_path.is_file():
            config_url = _piper_voice_url(voice_id, suffix="onnx.json")
            _download_to_file(config_url, config_path)

        if not model_path.is_file():
            model_url = _piper_voice_url(voice_id, suffix="onnx")
            _download_to_file(model_url, model_path, on_progress=on_progress)
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
        # Don't leave half-written files masquerading as complete.
        for partial in (
            model_path.with_suffix(model_path.suffix + ".partial"),
            config_path.with_suffix(config_path.suffix + ".partial"),
        ):
            partial.unlink(missing_ok=True)
        logger.error("Piper voice %s download failed: %s", voice_id, e)
        raise ValueError("PIPER_DOWNLOAD_FAILED") from e

    return model_path, config_path


def _download_to_file(
    url: str,
    dest: Path,
    on_progress: Callable[[int, int], None] | None = None,
) -> None:
    """Streams *url* into *dest*, atomic-rename via ``.partial`` suffix."""
    partial = dest.with_suffix(dest.suffix + ".partial")
    partial.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=60) as resp:  # noqa: S310
        total = int(resp.headers.get("Content-Length", "0") or 0)
        done = 0
        chunk_size = 64 * 1024
        with partial.open("wb") as f:
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if on_progress is not None and total:
                    on_progress(done, total)
    partial.replace(dest)


# Cache loaded PiperVoice instances so repeated synthesis on the same
# voice doesn't re-load the ONNX model (loading is ~500 ms cold).
_piper_voice_cache: dict[str, object] = {}


def _load_piper_voice(voice_id: str) -> object:
    """Returns a cached :class:`PiperVoice` for *voice_id*.

    Raises ``ValueError("PIPER_VOICE_NOT_INSTALLED")`` when the voice
    files aren't on disk — the UI is expected to gate synthesis on
    :func:`is_piper_voice_installed` and prompt the user to download,
    rather than silently auto-fetching mid-translation.
    """
    cached = _piper_voice_cache.get(voice_id)
    if cached is not None:
        return cached

    if not is_piper_voice_installed(voice_id):
        raise ValueError("PIPER_VOICE_NOT_INSTALLED")

    from piper.voice import PiperVoice  # noqa: PLC0415

    model_path, config_path = piper_voice_paths(voice_id)
    voice = PiperVoice.load(str(model_path), config_path=str(config_path))
    _piper_voice_cache[voice_id] = voice
    return voice


def _synthesize_chunk_piper(
    text: str,
    output_path: Path,
    voice_id: str,
    *,
    audio_format: str = ".mp3",
) -> None:
    """Synthesizes *text* with Piper and writes to *output_path*.

    Piper's native output format is WAV (16-bit PCM, 22.05 kHz mono).
    We synthesize to a temp WAV, then transcode to the requested
    format via FFmpeg — same pattern as the Gemini path.

    Args:
        text: Text to synthesize.
        output_path: Final audio file path.  Container format is
            controlled by *audio_format*.
        voice_id: Voice ID like ``"en_US-amy-medium"``.
        audio_format: Output container — ``".mp3"`` or ``".wav"``.

    Raises:
        ValueError: ``"PIPER_VOICE_NOT_INSTALLED"`` if the voice files
            aren't downloaded; ``"EMPTY_TEXT"`` if Piper produced
            zero audio (e.g. text was only punctuation).
        RuntimeError: ``"FFMPEG_CONVERSION_FAILED"`` on transcode error,
            ``"FFMPEG_NOT_FOUND"`` if ffmpeg is missing for non-WAV.
    """
    voice = _load_piper_voice(voice_id)

    import wave  # noqa: PLC0415

    # Synthesize to an intermediate WAV either at the final path
    # (when audio_format == .wav and we can avoid the transcode) or
    # to a temp file we'll feed through ffmpeg.
    if audio_format.lower() == ".wav":
        wav_target = output_path
        wav_target.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(wav_target), "wb") as wav_file:
            voice.synthesize_wav(text, wav_file)
        if wav_target.stat().st_size <= _WAV_HEADER_SIZE:
            wav_target.unlink(missing_ok=True)
            raise ValueError("EMPTY_TEXT")
        return

    # Transcode path: WAV → MP3 (or other) via FFmpeg.
    if not check_ffmpeg_available():
        raise RuntimeError("FFMPEG_NOT_FOUND")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        with wave.open(str(tmp_path), "wb") as wav_file:
            voice.synthesize_wav(text, wav_file)
        if tmp_path.stat().st_size <= _WAV_HEADER_SIZE:
            raise ValueError("EMPTY_TEXT")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(  # noqa: S603
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(tmp_path),
                    str(output_path),
                ],
                capture_output=True,
                check=True,
                timeout=60,
            )
        except subprocess.CalledProcessError as e:
            msg = e.stderr.decode("utf-8", errors="replace")[:500]
            logger.error("Piper WAV→%s failed: %s", audio_format, msg)
            raise RuntimeError("FFMPEG_CONVERSION_FAILED") from e
    finally:
        tmp_path.unlink(missing_ok=True)


# ── Google Cloud TTS ───────────────────────────────────────────────────────

# Mapping from file extension to Google Cloud TTS audio encoding
_TTS_ENCODING_MAP: dict[str, str] = {
    ".mp3": "MP3",
    ".wav": "LINEAR16",
}


def _synthesize_chunk(  # noqa: PLR0912, PLR0913
    text: str,
    language_code: str,
    voice_gender: str,
    api_key: str,
    output_path: Path,
    speaking_rate: float = 1.0,
    audio_format: str = ".mp3",
    voice_name: str = "",
) -> None:
    """Synthesizes a single text chunk to audio and writes to disk.

    Memory-safe: decoded audio is written immediately, not accumulated.

    Args:
        text: Text to synthesize.
        language_code: TTS language code (e.g. "vi-VN").
        voice_gender: Voice gender ("MALE" or "FEMALE").
        api_key: Google Cloud API key.
        output_path: Path to write the audio file.
        speaking_rate: Speech speed multiplier (0.25–4.0).
        audio_format: Output format (".mp3" or ".wav").
        voice_name: Optional specific voice name (e.g. "en-US-Chirp3-HD-Charon").
            When set, the server ignores ``ssmlGender`` and uses this voice.
    """
    encoding = _TTS_ENCODING_MAP.get(audio_format, "MP3")
    url = f"{_TTS_API_URL}?key={api_key}"
    audio_config: dict = {"audioEncoding": encoding}
    if speaking_rate != 1.0:
        clamped = max(
            _TTS_MIN_SPEAKING_RATE,
            min(speaking_rate, _TTS_MAX_SPEAKING_RATE),
        )
        audio_config["speakingRate"] = round(clamped, 2)
    voice_cfg: dict = {"languageCode": language_code}
    if voice_name:
        voice_cfg["name"] = voice_name
    else:
        voice_cfg["ssmlGender"] = voice_gender
    payload = {
        "input": {"text": text},
        "voice": voice_cfg,
        "audioConfig": audio_config,
    }

    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
    )

    logger.debug(
        "TTS request: lang=%s, gender=%s, %d bytes",
        language_code,
        voice_gender,
        len(text.encode("utf-8")),
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as response:  # noqa: S310
            resp_data = response.read()
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")[:500]
        logger.error("TTS API error %d: %s", e.code, error_body)
        # Map status codes to typed sentinels — same pattern as the
        # LLM engine + Cloud Vision OCR.  Without this every non-401/
        # 403/429 leaks as ``TTS_API_ERROR: HTTP <code>`` which the
        # error-tag dispatcher rebadges to ``ERR_UNKNOWN``.
        if e.code in {401, 403}:
            raise ValueError("AUTH_ERROR:Google Cloud") from e
        if e.code == 429:  # noqa: PLR2004
            raise ValueError("QUOTA_ERROR") from e
        if e.code == 413:  # noqa: PLR2004
            # Server saw an oversize payload — text exceeded the
            # documented 5000-byte per-request cap despite our 4500-
            # byte ``_TTS_MAX_BYTES`` chunker.  Surface a typed
            # sentinel so the UI can hint at shortening the input.
            raise ValueError("REQUEST_TOO_LARGE") from e
        if 500 <= e.code < 600:  # noqa: PLR2004
            # Transient server-side failure — eligible for retry.
            raise ValueError("SERVICE_UNAVAILABLE_ERROR") from e
        if e.code == 400:  # noqa: PLR2004
            # Google's TTS quirk: an INVALID API key returns HTTP 400
            # with the auth-failure reason in the body — NOT 401/403
            # like most APIs.  Same heuristic as
            # ``llm_engine._handle_api_error``: if BOTH "api" and
            # "key" appear in the body it's almost certainly an auth
            # failure (covers "API_KEY_INVALID", "API key not valid",
            # and any future Google variants without a fragile
            # substring list).  All other 400s (unsupported language
            # code, malformed payload) use a TTS-specific sentinel so
            # the user-facing message references TTS rather than
            # borrowing the LLM-flavored INVALID_REQUEST text.
            body_lower = error_body.lower()
            if "api" in body_lower and "key" in body_lower:
                raise ValueError("AUTH_ERROR:Google Cloud") from e
            raise ValueError("TTS_INVALID_REQUEST") from e
        raise ValueError(f"TTS_API_ERROR: HTTP {e.code}") from e
    except urllib.error.URLError as e:
        logger.error("TTS connection error: %s", e)
        raise ValueError("CONNECTION_ERROR") from e
    except TimeoutError as e:
        logger.error("TTS timeout: %s", e)
        raise ValueError("TIMEOUT_ERROR") from e

    result = json.loads(resp_data)
    # Defensive: the API normally returns ``audioContent`` on success,
    # but safety filters / partial responses can land HTTP 200 with no
    # audio payload.  Surface a typed sentinel rather than the bare
    # ``KeyError`` the lookup would otherwise raise.
    audio_b64 = result.get("audioContent")
    if not audio_b64:
        logger.error("TTS response missing audioContent: %s", resp_data[:200])
        # Reuse the shared ``INVALID_RESPONSE`` sentinel — same UI
        # treatment as an LLM that returns a malformed body.
        raise ValueError("INVALID_RESPONSE")
    audio_bytes = base64.b64decode(audio_b64)
    output_path.write_bytes(audio_bytes)


def _concatenate_mp3_files(
    audio_files: list[Path],
    output_path: Path,
) -> None:
    """Concatenates multiple MP3 files using FFmpeg.

    Memory-safe: FFmpeg processes files on disk.

    Args:
        audio_files: List of MP3 file paths to concatenate.
        output_path: Path for the concatenated output.
    """
    if len(audio_files) == 1:
        shutil.copy2(audio_files[0], output_path)
        return

    # Create FFmpeg concat list file
    concat_file = audio_files[0].parent / "concat.txt"
    with concat_file.open("w", encoding="utf-8") as f:
        for audio_file in audio_files:
            # Escape single quotes for FFmpeg concat format
            safe_path = str(audio_file).replace("'", "'\\''")
            f.write(f"file '{safe_path}'\n")

    try:
        subprocess.run(  # noqa: S603
            [
                "ffmpeg",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_file),
                "-c",
                "copy",
                "-y",
                str(output_path),
            ],
            capture_output=True,
            check=True,
            timeout=300,
        )
    except subprocess.CalledProcessError as e:
        msg = e.stderr.decode("utf-8", errors="replace")[:500]
        logger.error("FFmpeg concat failed: %s", msg)
        raise RuntimeError("FFMPEG_CONCAT_FAILED") from e


def synthesize_speech(  # noqa: PLR0912, PLR0913, PLR0915
    text: str,
    target_lang: str = "",
    voice_gender: str = "FEMALE",
    output_path: str = "",
    *,
    tts_method: str = "",
    audio_format: str = ".mp3",
    is_cancelled: Callable[[], bool] | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> str:
    """Synthesizes speech from text using the configured TTS engine.

    Dispatches to Google Cloud TTS or Edge TTS based on ``tts_method``.

    Args:
        text: Text to synthesize.
        target_lang: Target language label (e.g. "Vietnamese").
        voice_gender: Voice gender ("MALE" or "FEMALE").
        output_path: Path for the output audio file.
        tts_method: TTS engine ("Edge TTS" or "Google Cloud").
        audio_format: Output format (".mp3" or ".wav").
        is_cancelled: Optional callback to check for cancellation.
        on_progress: Optional callback (current_chunk, total_chunks).

    Returns:
        The output file path.

    Raises:
        ValueError: On API errors, empty text, or missing credentials.
        RuntimeError: On FFmpeg errors.
    """
    from src.constants.settings import (  # noqa: PLC0415
        ELEVENLABS_MODEL_DEFAULT,
        SETTING_ELEVENLABS_API_KEY,
        SETTING_ELEVENLABS_MODEL,
        SETTING_ELEVENLABS_VOICE_ID,
        SETTING_GEMINI_TTS_VOICE_NAME,
        SETTING_LLM_GEMINI_API_KEY,
        VOICE_TTS_ELEVENLABS,
        VOICE_TTS_GEMINI,
        VOICE_TTS_GOOGLE,
        VOICE_TTS_PIPER,
    )
    from src.utils.config_manager import load_setting  # noqa: PLC0415

    use_google = tts_method == VOICE_TTS_GOOGLE
    use_elevenlabs = tts_method == VOICE_TTS_ELEVENLABS
    use_gemini = tts_method == VOICE_TTS_GEMINI
    use_piper = tts_method == VOICE_TTS_PIPER

    if use_google:
        api_key_val = load_google_cloud_api_key()
        if not api_key_val:
            raise ValueError("AUTH_ERROR:Google Cloud")
    elif use_elevenlabs:
        el_api_key = load_setting(SETTING_ELEVENLABS_API_KEY, "")
        if not el_api_key:
            raise ValueError("AUTH_ERROR:ElevenLabs")
        el_voice_id = load_setting(SETTING_ELEVENLABS_VOICE_ID, "")
        el_model_id = load_setting(
            SETTING_ELEVENLABS_MODEL,
            ELEVENLABS_MODEL_DEFAULT,
        )
    elif use_gemini:
        # TTS uses the Developer API path only — Vertex routing for
        # the preview TTS models needs OAuth + a different URL shape
        # and isn't worth the extra complexity for v1 of this feature.
        # Vertex users translating with Gemini still need a Developer
        # API key here to use Gemini TTS.
        gemini_api_key = load_setting(SETTING_LLM_GEMINI_API_KEY, "")
        if not gemini_api_key:
            raise ValueError("AUTH_ERROR:Gemini")
    elif use_piper:
        # Offline path — no API key.  Two outcomes:
        #
        # - Piper has no voice for *target_lang* (e.g. Japanese,
        #   Hebrew, Korean) → silently fall back to Edge TTS for
        #   this synthesis call.  Synthesising en_US audio for
        #   Japanese text (the previous behaviour) was a worse
        #   user experience than just using Edge.
        # - Piper HAS a voice for *target_lang* but the user hasn't
        #   downloaded it yet → raise ``PIPER_VOICE_NOT_INSTALLED``
        #   so the history row marks Failed and the user is pointed
        #   at the Settings → Voice → Piper download dialog.  We do
        #   NOT auto-fetch mid-translation; downloads are user-
        #   initiated and visible.
        piper_voice_id = get_piper_voice_for(target_lang, voice_gender)
        if not piper_voice_id:
            use_piper = False  # language unsupported → Edge fallback
        elif not is_piper_voice_installed(piper_voice_id):
            raise ValueError("PIPER_VOICE_NOT_INSTALLED")

    # Piper writes WAV via the python API and only needs ffmpeg for
    # MP3 transcoding (handled per-chunk).  The other backends always
    # need ffmpeg for the final concatenate step.
    if not use_piper and not check_ffmpeg_available():
        raise RuntimeError("FFMPEG_NOT_FOUND")

    # Split text into API-sized chunks.  Gemini's per-call output is
    # capped at ~30-60 s of audio, so we use the smaller
    # ``_GEMINI_TTS_MAX_BYTES`` (~2 KB ≈ 30 s of speech) to keep
    # each chunk safely under the cap; other backends use the
    # larger byte budget.
    max_bytes = _GEMINI_TTS_MAX_BYTES if use_gemini else _TTS_MAX_BYTES
    chunks = _split_text_for_tts(text, max_bytes=max_bytes)
    if not chunks:
        raise ValueError("EMPTY_TEXT")

    # Resolve voice — explicit user override (Settings → Voice →
    # Voice picker) wins over the language-or-gender default.
    if use_google:
        language_code = _get_tts_language_code(target_lang)
    elif use_gemini:
        override = load_setting(SETTING_GEMINI_TTS_VOICE_NAME, "").strip()
        gemini_voice = override or _get_gemini_voice(voice_gender)
    elif use_piper:
        # piper_voice_id was resolved above during the install-check.
        pass
    elif not use_elevenlabs:
        # Edge TTS resolves a curated voice from the (language, gender)
        # pair in ``_EDGE_VOICES``.  No free-text override — UI exposes
        # only a male/female radio.
        edge_voice = _get_edge_voice(target_lang, voice_gender)

    # Process chunks to temp files, then concatenate
    temp_dir = Path(tempfile.mkdtemp(prefix="voice_"))
    try:
        audio_files: list[Path] = []
        for i, chunk in enumerate(chunks):
            if is_cancelled and is_cancelled():
                raise ValueError("CANCELLED")

            if on_progress:
                on_progress(i + 1, len(chunks))

            if use_google:
                chunk_ext = audio_format if audio_format else ".mp3"
                chunk_path = temp_dir / f"chunk_{i:04d}{chunk_ext}"
                _synthesize_chunk(
                    chunk,
                    language_code,
                    voice_gender,
                    api_key_val,
                    chunk_path,
                    audio_format=audio_format,
                )
            elif use_elevenlabs:
                chunk_path = temp_dir / f"chunk_{i:04d}.mp3"
                _synthesize_chunk_elevenlabs(
                    chunk,
                    el_api_key,
                    chunk_path,
                    el_voice_id,
                    model_id=el_model_id,
                    gender=voice_gender,
                )
            elif use_gemini:
                chunk_ext = audio_format if audio_format else ".mp3"
                chunk_path = temp_dir / f"chunk_{i:04d}{chunk_ext}"
                _synthesize_chunk_gemini(
                    chunk,
                    gemini_api_key,
                    chunk_path,
                    gemini_voice,
                    audio_format=audio_format,
                )
            elif use_piper:
                chunk_ext = audio_format if audio_format else ".mp3"
                chunk_path = temp_dir / f"chunk_{i:04d}{chunk_ext}"
                _synthesize_chunk_piper(
                    chunk,
                    chunk_path,
                    piper_voice_id,
                    audio_format=audio_format,
                )
            else:
                chunk_path = temp_dir / f"chunk_{i:04d}.mp3"
                _synthesize_chunk_edge(chunk, edge_voice, chunk_path)
            audio_files.append(chunk_path)

        if not audio_files:
            raise ValueError("EMPTY_TEXT")

        # Concatenate all chunks into final output
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        _concatenate_mp3_files(audio_files, out)

        return output_path

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def synthesize_timed_speech(  # noqa: PLR0912, PLR0913, PLR0915
    entries: list[SubtitleEntry],
    target_lang: str = "",
    voice_gender: str = "FEMALE",
    output_path: str = "",
    *,
    tts_method: str = "",
    audio_format: str = ".mp3",
    is_cancelled: Callable[[], bool] | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> str:
    """Synthesizes timed speech from subtitle entries.

    Dispatches to Google Cloud TTS or Edge TTS based on ``tts_method``.
    Each entry is synthesized individually and placed at its original
    timestamp. Silence is inserted for gaps.

    Args:
        entries: List of SubtitleEntry objects with start/end timestamps.
        target_lang: Target language label (e.g. "Vietnamese").
        voice_gender: Voice gender ("MALE" or "FEMALE").
        output_path: Path for the output audio file.
        tts_method: TTS engine ("Edge TTS" or "Google Cloud").
        audio_format: Output format (".mp3" or ".wav").
        is_cancelled: Optional callback to check for cancellation.
        on_progress: Optional callback (current_entry, total_entries).

    Returns:
        The output file path.

    Raises:
        ValueError: On API errors, empty entries, or missing credentials.
        RuntimeError: On FFmpeg errors.
    """
    from src.constants.settings import (  # noqa: PLC0415
        ELEVENLABS_MODEL_DEFAULT,
        SETTING_ELEVENLABS_API_KEY,
        SETTING_ELEVENLABS_MODEL,
        SETTING_ELEVENLABS_VOICE_ID,
        SETTING_GEMINI_TTS_VOICE_NAME,
        SETTING_LLM_GEMINI_API_KEY,
        VOICE_TTS_ELEVENLABS,
        VOICE_TTS_GEMINI,
        VOICE_TTS_GOOGLE,
        VOICE_TTS_PIPER,
    )
    from src.utils.config_manager import load_setting  # noqa: PLC0415

    use_google = tts_method == VOICE_TTS_GOOGLE
    use_elevenlabs = tts_method == VOICE_TTS_ELEVENLABS
    use_gemini = tts_method == VOICE_TTS_GEMINI
    use_piper = tts_method == VOICE_TTS_PIPER

    if use_google:
        api_key = load_google_cloud_api_key()
        if not api_key:
            raise ValueError("AUTH_ERROR:Google Cloud")
        language_code = _get_tts_language_code(target_lang)
    elif use_elevenlabs:
        el_api_key = load_setting(SETTING_ELEVENLABS_API_KEY, "")
        if not el_api_key:
            raise ValueError("AUTH_ERROR:ElevenLabs")
        el_voice_id = load_setting(SETTING_ELEVENLABS_VOICE_ID, "")
        el_model_id = load_setting(
            SETTING_ELEVENLABS_MODEL,
            ELEVENLABS_MODEL_DEFAULT,
        )
    elif use_gemini:
        gemini_api_key = load_setting(SETTING_LLM_GEMINI_API_KEY, "")
        if not gemini_api_key:
            raise ValueError("AUTH_ERROR:Gemini")
        # Explicit voice override (Settings → Voice → Voice picker)
        # wins over the gender-default mapping.
        override = load_setting(SETTING_GEMINI_TTS_VOICE_NAME, "").strip()
        gemini_voice = override or _get_gemini_voice(voice_gender)
    elif use_piper:
        # Same two-outcome contract as ``synthesize_speech``:
        # - language unsupported by Piper → silently route to Edge.
        # - language supported but voice not downloaded → raise
        #   ``PIPER_VOICE_NOT_INSTALLED`` so the user is sent back
        #   to the Settings download dialog.
        piper_voice_id = get_piper_voice_for(target_lang, voice_gender)
        if not piper_voice_id:
            use_piper = False  # language unsupported → Edge fallback
        elif not is_piper_voice_installed(piper_voice_id):
            raise ValueError("PIPER_VOICE_NOT_INSTALLED")
    else:
        # Edge TTS: gender → language voice via ``_EDGE_VOICES``.  No
        # free-text override — UI is gender radio only.
        edge_voice = _get_edge_voice(target_lang, voice_gender)

    # Timed-speech path always needs ffmpeg for the silence gaps and
    # the final concatenate, even on Piper.
    if not check_ffmpeg_available():
        raise RuntimeError("FFMPEG_NOT_FOUND")

    # Filter to entries with actual text
    valid_entries = [e for e in entries if e.text.strip()]
    if not valid_entries:
        raise ValueError("EMPTY_TEXT")

    # Pre-parse all start timestamps so we can look ahead for gap tolerance
    parsed: list[tuple[float, float]] = []
    for entry in valid_entries:
        s = _parse_srt_timestamp(entry.start)
        e = _parse_srt_timestamp(entry.end)
        if e > s:
            parsed.append((s, e))
        # else: skip zero/negative-duration entries

    if not parsed:
        raise ValueError("EMPTY_TEXT")

    temp_dir = Path(tempfile.mkdtemp(prefix="voice_timed_"))
    try:
        segments: list[Path] = []
        cursor = 0.0
        total = len(parsed)
        # Index into valid_entries matching parsed entries
        parsed_idx = 0

        for i, entry in enumerate(valid_entries):
            if is_cancelled and is_cancelled():
                raise ValueError("CANCELLED")

            start = _parse_srt_timestamp(entry.start)
            end = _parse_srt_timestamp(entry.end)
            available = end - start

            if available <= 0:
                continue

            if on_progress:
                on_progress(parsed_idx + 1, total)

            # Insert silence gap before this entry (based on actual cursor)
            gap = start - cursor
            if gap > 0.05:  # noqa: PLR2004
                silence_path = temp_dir / f"silence_{i:04d}.mp3"
                _generate_silence(gap, silence_path)
                segments.append(silence_path)
            elif gap < 0:
                # Previous segment overflowed — cursor already past start,
                # so no silence is inserted and audio effectively overlaps
                pass

            # Synthesize at normal speed
            if use_google:
                chunk_ext = audio_format if audio_format else ".mp3"
                speech_path = temp_dir / f"speech_{i:04d}{chunk_ext}"
                _synthesize_chunk(
                    entry.text,
                    language_code,
                    voice_gender,
                    api_key,
                    speech_path,
                    audio_format=audio_format,
                )
            elif use_elevenlabs:
                speech_path = temp_dir / f"speech_{i:04d}.mp3"
                _synthesize_chunk_elevenlabs(
                    entry.text,
                    el_api_key,
                    speech_path,
                    el_voice_id,
                    model_id=el_model_id,
                    gender=voice_gender,
                )
            elif use_gemini:
                chunk_ext = audio_format if audio_format else ".mp3"
                speech_path = temp_dir / f"speech_{i:04d}{chunk_ext}"
                _synthesize_chunk_gemini(
                    entry.text,
                    gemini_api_key,
                    speech_path,
                    gemini_voice,
                    audio_format=audio_format,
                )
            elif use_piper:
                chunk_ext = audio_format if audio_format else ".mp3"
                speech_path = temp_dir / f"speech_{i:04d}{chunk_ext}"
                _synthesize_chunk_piper(
                    entry.text,
                    speech_path,
                    piper_voice_id,
                    audio_format=audio_format,
                )
            else:
                speech_path = temp_dir / f"speech_{i:04d}.mp3"
                _synthesize_chunk_edge(entry.text, edge_voice, speech_path)

            # Measure audio duration and apply speed-up only when needed
            audio_dur = _get_mp3_duration(speech_path)
            overflow = audio_dur - available

            if overflow > 0:
                # Cap how far audio may extend past its subtitle end time
                max_tolerance = min(
                    available * _OVERFLOW_RATIO,
                    _OVERFLOW_MAX_SECONDS,
                )

                # Determine how much gap follows before the next entry
                next_start = (
                    parsed[parsed_idx + 1][0]
                    if parsed_idx + 1 < total
                    else float("inf")  # last entry — unlimited gap
                )
                next_gap = next_start - end

                # Allowed overflow is the smaller of the tolerance cap
                # and the actual gap available
                allowed = min(max_tolerance, max(next_gap, 0))

                if overflow <= allowed:
                    # Audio fits within tolerance — keep natural speed
                    pass
                else:
                    # Speed up to fit within available + allowed
                    fit_window = available + allowed
                    if fit_window > 0:
                        rate = audio_dur / fit_window
                    else:
                        rate = audio_dur / available

                    if use_google:
                        if rate > _TTS_MIN_SPEAKING_RATE:
                            resyn_ext = audio_format if audio_format else ".mp3"
                            resyn_path = temp_dir / f"speech_{i:04d}_fast{resyn_ext}"
                            _synthesize_chunk(
                                entry.text,
                                language_code,
                                voice_gender,
                                api_key,
                                resyn_path,
                                speaking_rate=rate,
                                audio_format=audio_format,
                            )
                            speech_path = resyn_path
                            audio_dur = _get_mp3_duration(speech_path)
                    else:
                        fast_path = temp_dir / f"speech_{i:04d}_fast.mp3"
                        _speed_up_audio(speech_path, fast_path, rate)
                        if fast_path.exists():
                            speech_path = fast_path
                            audio_dur = _get_mp3_duration(speech_path)

            segments.append(speech_path)
            # Track actual audio position (not subtitle end time)
            cursor = max(start, cursor) + audio_dur
            parsed_idx += 1

        if not segments:
            raise ValueError("EMPTY_TEXT")

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        _concatenate_mp3_files(segments, out)

        return output_path

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def mix_audio_into_video(
    video_path: str,
    audio_path: str,
    output_path: str,
) -> str:
    """Replaces a video's audio track with a new audio file.

    The video stream is copied (not re-encoded), so this is fast.

    Args:
        video_path: Path to the original video file.
        audio_path: Path to the new audio file (MP3/WAV).
        output_path: Path for the output video file.

    Returns:
        The output file path.

    Raises:
        RuntimeError: On FFmpeg errors.
    """
    if not check_ffmpeg_available():
        raise RuntimeError("FFMPEG_NOT_FOUND")

    try:
        subprocess.run(  # noqa: S603
            [
                "ffmpeg",
                "-i",
                str(video_path),
                "-i",
                str(audio_path),
                "-c:v",
                "copy",
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-shortest",
                "-y",
                str(output_path),
            ],
            capture_output=True,
            check=True,
            timeout=600,
        )
    except subprocess.CalledProcessError as e:
        msg = e.stderr.decode("utf-8", errors="replace")[:500]
        logger.error("FFmpeg mix failed: %s", msg)
        raise RuntimeError("FFMPEG_MIX_FAILED") from e

    return output_path
