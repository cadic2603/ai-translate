"""Shared FFmpeg post-encoding helpers for audio output.

Both the Live page (post-encode session WAV → user-chosen format on Stop)
and the Voice page (post-encode synthesised WAV → user-chosen format) need
the same WAV → MP3/FLAC/OGG transcoder.  Keep the codec args + encode
helper in one place so adding a new encoded format is a single-edit.
"""

import contextlib
import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger("audio_encoding")


# Per-format FFmpeg codec arguments.  Keyed by the lowercase format name
# (mp3 / flac / ogg); value is the codec args inserted between ``-i <wav>``
# and the output path.  Adding a new encoded format is one entry here +
# wiring the option into the UI picker.
#   MP3:  libmp3lame at 64 kbps mono — plenty for speech.
#   FLAC: lossless, default compression level (5).  No bitrate arg —
#         bitrate doesn't apply to lossless codecs.
#   OGG:  Vorbis at ~64 kbps via the audio-quality flag (-q:a 2 is
#         roughly that on the libvorbis scale).  Vorbis is the safest
#         Ogg container codec — Opus needs the ``.opus`` container
#         which is a different file-extension story.
FFMPEG_CODEC_ARGS: dict[str, list[str]] = {
    "mp3": ["-codec:a", "libmp3lame", "-b:a", "64k"],
    "flac": ["-codec:a", "flac"],
    "ogg": ["-codec:a", "libvorbis", "-q:a", "2"],
}

# Formats that don't need post-encoding — the engine writes them
# natively or the source IS the target.
PASSTHROUGH_FORMATS = frozenset({"wav"})


def post_encode_audio(
    source_wav: Path,
    target_format: str,
    *,
    output_path: Path | None = None,
    delete_source: bool = True,
) -> Path:
    """Post-encodes a WAV file to one of the supported encoded formats.

    Returns the path of the encoded output on success.  Raises
    :class:`RuntimeError` with a sentinel message on any failure
    (missing ffmpeg, bad format, ffmpeg subprocess error, empty
    output).  The source WAV is left intact when raising so the
    caller can surface a dialog AND still preserve the user's audio
    by pointing at the source path; the previous "silent fallback to
    WAV" behaviour hid encode failures and is intentionally removed.

    Sentinels (the RuntimeError's first arg):
        * ``"FFMPEG_NOT_FOUND"`` — ffmpeg isn't on PATH.
        * ``"UNKNOWN_FORMAT"`` — ``target_format`` isn't supported.
        * ``"FFMPEG_FAILED"`` — ffmpeg ran but returned non-zero or
          produced an empty file.

    Args:
        source_wav: Path to the WAV file to encode.  Read-only.
        target_format: Lowercase format name (``"mp3"`` / ``"flac"`` /
            ``"ogg"``).  ``"wav"`` is a no-op passthrough.
        output_path: Optional explicit output path.  When omitted, the
            output sits next to *source_wav* with the matching extension.
        delete_source: When True (default), delete the source WAV after
            a successful encode so only the target file remains.  Set
            False when the source is a user-visible artefact that should
            survive alongside the encoded copy.
    """
    fmt = target_format.lstrip(".").lower()
    if fmt in PASSTHROUGH_FORMATS or fmt == source_wav.suffix.lstrip(".").lower():
        return source_wav

    codec_args = FFMPEG_CODEC_ARGS.get(fmt)
    if codec_args is None:
        logger.warning(
            "Unknown audio format %r for %s", fmt, source_wav,
        )
        raise RuntimeError("UNKNOWN_FORMAT")

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        logger.warning(
            "%s post-encode failed: ffmpeg not on PATH (WAV kept at %s)",
            fmt.upper(), source_wav,
        )
        raise RuntimeError("FFMPEG_NOT_FOUND")

    encoded_path = output_path or source_wav.with_suffix(f".{fmt}")
    try:
        result = subprocess.run(  # noqa: S603
            [
                ffmpeg, "-y", "-loglevel", "error",
                "-i", str(source_wav),
                *codec_args,
                str(encoded_path),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning(
            "%s post-encode failed (%s); WAV kept at %s",
            fmt.upper(), exc, source_wav,
        )
        raise RuntimeError("FFMPEG_FAILED") from exc

    encoded_ok = (
        result.returncode == 0
        and encoded_path.exists()
        and encoded_path.stat().st_size > 0
    )
    if not encoded_ok:
        logger.warning(
            "%s post-encode produced no output (rc=%d stderr=%s); "
            "WAV kept at %s",
            fmt.upper(), result.returncode, result.stderr[:200], source_wav,
        )
        # Clean up a failed/empty encoded file so it doesn't masquerade
        # as a real output.
        if encoded_path.exists():
            with contextlib.suppress(OSError):
                encoded_path.unlink()
        raise RuntimeError("FFMPEG_FAILED")

    if delete_source:
        try:
            source_wav.unlink()
        except OSError as exc:
            logger.warning(
                "Could not remove source WAV %s after encode: %s",
                source_wav, exc,
            )
    return encoded_path
