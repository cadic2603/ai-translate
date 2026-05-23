"""Unit tests for ``src/utils/audio_encoding.py``.

Pin the failure-mode contract documented in the helper's docstring:
``post_encode_audio`` raises ``RuntimeError`` with a sentinel for every
failure path (FFMPEG_NOT_FOUND / FFMPEG_FAILED / UNKNOWN_FORMAT), and
returns the encoded path on success.  No silent fallback to WAV — that
behaviour was intentionally removed (see chat-archaeology comment in
the docstring).
"""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.utils.audio_encoding import (
    FFMPEG_CODEC_ARGS,
    PASSTHROUGH_FORMATS,
    post_encode_audio,
)

# ──────────────────────────────────────────────────────────────────────
# Codec table integrity
# ──────────────────────────────────────────────────────────────────────


class TestCodecArgs:
    """``FFMPEG_CODEC_ARGS`` stays in sync with the UI format pickers."""

    def test_mp3_uses_libmp3lame(self):
        """MP3 entry uses libmp3lame at the documented 64 kbps."""
        args = FFMPEG_CODEC_ARGS["mp3"]
        assert "libmp3lame" in args
        assert "64k" in args

    def test_flac_uses_flac_codec(self):
        """FLAC entry uses the ``flac`` codec (lossless, no bitrate arg)."""
        args = FFMPEG_CODEC_ARGS["flac"]
        assert "flac" in args
        # Lossless — no bitrate flag.
        assert "-b:a" not in args

    def test_ogg_uses_libvorbis(self):
        """OGG entry uses libvorbis with quality arg."""
        args = FFMPEG_CODEC_ARGS["ogg"]
        assert "libvorbis" in args
        assert "-q:a" in args

    def test_wav_is_passthrough(self):
        """WAV is the passthrough format (engine-native, no transcode)."""
        assert "wav" in PASSTHROUGH_FORMATS

    def test_only_three_encoded_codecs(self):
        """Adding a new encoded format here must also update the UI."""
        # Lock the set so adding a 4th encoded format triggers test +
        # UI changes together (Voice + Live audio-format picker).
        assert set(FFMPEG_CODEC_ARGS) == {"mp3", "flac", "ogg"}


# ──────────────────────────────────────────────────────────────────────
# Passthrough paths (no ffmpeg call)
# ──────────────────────────────────────────────────────────────────────


class TestPassthrough:
    """WAV target + matching-extension target = no encode, return source."""

    def test_wav_target_returns_source_unchanged(self, tmp_path):
        """``target_format='wav'`` short-circuits without invoking ffmpeg."""
        src = tmp_path / "x.wav"
        src.write_bytes(b"fake wav")
        with patch("src.utils.audio_encoding.shutil.which") as mock_which:
            result = post_encode_audio(src, "wav")
        assert result == src
        # Crucially: ffmpeg never even looked up.
        mock_which.assert_not_called()

    def test_target_matches_source_extension_returns_source(self, tmp_path):
        """``post_encode_audio(x.mp3, 'mp3')`` no-ops (already in target format)."""
        src = tmp_path / "y.mp3"
        src.write_bytes(b"fake mp3")
        with patch("src.utils.audio_encoding.shutil.which") as mock_which:
            result = post_encode_audio(src, "mp3")
        assert result == src
        mock_which.assert_not_called()

    def test_target_format_strips_leading_dot(self, tmp_path):
        """``'.wav'`` and ``'wav'`` both accepted (extension-style input)."""
        src = tmp_path / "z.wav"
        src.write_bytes(b"fake wav")
        # Both forms should hit the passthrough.
        assert post_encode_audio(src, ".wav") == src
        assert post_encode_audio(src, "wav") == src


# ──────────────────────────────────────────────────────────────────────
# Sentinel raises
# ──────────────────────────────────────────────────────────────────────


class TestSentinelRaises:
    """Every failure path raises ``RuntimeError`` with a known sentinel."""

    def test_unknown_format_raises(self, tmp_path):
        """Format not in ``FFMPEG_CODEC_ARGS`` → UNKNOWN_FORMAT."""
        src = tmp_path / "a.wav"
        src.write_bytes(b"fake")
        with pytest.raises(RuntimeError, match="UNKNOWN_FORMAT"):
            post_encode_audio(src, "opus")  # not in our codec table

    def test_ffmpeg_missing_raises(self, tmp_path):
        """``shutil.which('ffmpeg') is None`` → FFMPEG_NOT_FOUND."""
        src = tmp_path / "b.wav"
        src.write_bytes(b"fake")
        with (
            patch("src.utils.audio_encoding.shutil.which", return_value=None),
            pytest.raises(RuntimeError, match="FFMPEG_NOT_FOUND"),
        ):
            post_encode_audio(src, "mp3")

    def test_ffmpeg_subprocess_oserror_raises(self, tmp_path):
        """``subprocess.run`` OSError → FFMPEG_FAILED."""
        src = tmp_path / "c.wav"
        src.write_bytes(b"fake")
        with (
            patch(
                "src.utils.audio_encoding.shutil.which",
                return_value="/usr/bin/ffmpeg",
            ),
            patch(
                "src.utils.audio_encoding.subprocess.run",
                side_effect=OSError("denied"),
            ),
            pytest.raises(RuntimeError, match="FFMPEG_FAILED"),
        ):
            post_encode_audio(src, "mp3")

    def test_ffmpeg_timeout_raises(self, tmp_path):
        """``subprocess.TimeoutExpired`` → FFMPEG_FAILED."""
        src = tmp_path / "d.wav"
        src.write_bytes(b"fake")
        with (
            patch(
                "src.utils.audio_encoding.shutil.which",
                return_value="/usr/bin/ffmpeg",
            ),
            patch(
                "src.utils.audio_encoding.subprocess.run",
                side_effect=subprocess.TimeoutExpired("ffmpeg", 300),
            ),
            pytest.raises(RuntimeError, match="FFMPEG_FAILED"),
        ):
            post_encode_audio(src, "mp3")

    def test_ffmpeg_nonzero_exit_raises(self, tmp_path):
        """FFmpeg exits non-zero → FFMPEG_FAILED."""
        src = tmp_path / "e.wav"
        src.write_bytes(b"fake")
        fake_result = MagicMock(returncode=1, stderr="boom")
        with (
            patch(
                "src.utils.audio_encoding.shutil.which",
                return_value="/usr/bin/ffmpeg",
            ),
            patch(
                "src.utils.audio_encoding.subprocess.run",
                return_value=fake_result,
            ),
            pytest.raises(RuntimeError, match="FFMPEG_FAILED"),
        ):
            post_encode_audio(src, "mp3")

    def test_empty_output_file_raises(self, tmp_path):
        """FFmpeg returncode 0 but output is empty → FFMPEG_FAILED + cleanup."""
        src = tmp_path / "f.wav"
        src.write_bytes(b"fake")
        encoded = tmp_path / "f.mp3"

        def _fake_run(*_args, **_kwargs):
            # Simulate ffmpeg "succeeding" but producing an empty file.
            encoded.write_bytes(b"")
            return MagicMock(returncode=0, stderr="")

        with (
            patch(
                "src.utils.audio_encoding.shutil.which",
                return_value="/usr/bin/ffmpeg",
            ),
            patch(
                "src.utils.audio_encoding.subprocess.run",
                side_effect=_fake_run,
            ),
            pytest.raises(RuntimeError, match="FFMPEG_FAILED"),
        ):
            post_encode_audio(src, "mp3")
        # Helper cleaned up the empty file so it doesn't masquerade
        # as a real output.
        assert not encoded.exists()


# ──────────────────────────────────────────────────────────────────────
# Source preservation on failure
# ──────────────────────────────────────────────────────────────────────


class TestSourcePreservation:
    """The source WAV survives every failure path — user keeps their audio."""

    def test_source_wav_survives_ffmpeg_missing(self, tmp_path):
        """``FFMPEG_NOT_FOUND`` leaves the source WAV intact."""
        src = tmp_path / "keep.wav"
        src.write_bytes(b"my recording")
        with (
            patch("src.utils.audio_encoding.shutil.which", return_value=None),
            pytest.raises(RuntimeError),
        ):
            post_encode_audio(src, "mp3")
        assert src.exists()
        assert src.read_bytes() == b"my recording"

    def test_source_wav_survives_ffmpeg_nonzero(self, tmp_path):
        """``FFMPEG_FAILED`` leaves the source WAV intact."""
        src = tmp_path / "keep2.wav"
        src.write_bytes(b"my recording")
        with (
            patch(
                "src.utils.audio_encoding.shutil.which",
                return_value="/usr/bin/ffmpeg",
            ),
            patch(
                "src.utils.audio_encoding.subprocess.run",
                return_value=MagicMock(returncode=1, stderr="x"),
            ),pytest.raises(RuntimeError)
        ):
            post_encode_audio(src, "mp3")
        assert src.exists()


# ──────────────────────────────────────────────────────────────────────
# Success path
# ──────────────────────────────────────────────────────────────────────


class TestSuccess:
    """Success returns the encoded path and (by default) deletes the source."""

    def _fake_ffmpeg(self, tmp_path):
        """Returns a ``subprocess.run`` side_effect that fakes a successful encode.

        Writes a non-empty encoded file to the path passed in the
        ffmpeg argv's final position (where ffmpeg writes its output).
        Pairs with a separate ``shutil.which → "/usr/bin/ffmpeg"``
        patch at the test callsite.
        """
        def _run(args, **_kwargs):
            output_path = Path(args[-1])
            output_path.write_bytes(b"encoded payload")
            return MagicMock(returncode=0, stderr="")
        return _run

    def test_success_returns_encoded_path_and_deletes_source(self, tmp_path):
        """Default ``delete_source=True`` removes the WAV after success."""
        src = tmp_path / "g.wav"
        src.write_bytes(b"raw wav")
        with (
            patch(
                "src.utils.audio_encoding.shutil.which",
                return_value="/usr/bin/ffmpeg",
            ),
            patch(
                "src.utils.audio_encoding.subprocess.run",
                side_effect=self._fake_ffmpeg(tmp_path),
            ),
        ):
            result = post_encode_audio(src, "mp3")
        assert result == src.with_suffix(".mp3")
        assert result.exists()
        # Source was deleted on success.
        assert not src.exists()

    def test_delete_source_false_keeps_source(self, tmp_path):
        """``delete_source=False`` keeps the WAV alongside the encoded copy."""
        src = tmp_path / "h.wav"
        src.write_bytes(b"raw wav")
        with (
            patch(
                "src.utils.audio_encoding.shutil.which",
                return_value="/usr/bin/ffmpeg",
            ),
            patch(
                "src.utils.audio_encoding.subprocess.run",
                side_effect=self._fake_ffmpeg(tmp_path),
            ),
        ):
            result = post_encode_audio(src, "mp3", delete_source=False)
        assert result == src.with_suffix(".mp3")
        assert result.exists()
        assert src.exists()  # source survives

    def test_explicit_output_path_honoured(self, tmp_path):
        """``output_path=`` overrides the derived sibling-with-suffix."""
        src = tmp_path / "i.wav"
        src.write_bytes(b"raw")
        custom = tmp_path / "subdir" / "renamed.mp3"
        custom.parent.mkdir()
        with (
            patch(
                "src.utils.audio_encoding.shutil.which",
                return_value="/usr/bin/ffmpeg",
            ),
            patch(
                "src.utils.audio_encoding.subprocess.run",
                side_effect=self._fake_ffmpeg(tmp_path),
            ),
        ):
            result = post_encode_audio(src, "mp3", output_path=custom)
        assert result == custom
        assert custom.exists()
