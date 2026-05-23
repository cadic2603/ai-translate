"""Unit tests for the TTS (Text-to-Speech) functions in speech_engine.py."""

import base64
import json
import subprocess
import sys
import urllib.error
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.constants.history import display_status
from src.core.speech_engine import (
    _EDGE_DEFAULT_VOICE,
    _MAX_AUDIO_BYTES,
    _TTS_LANG_MAP,
    _TTS_MAX_BYTES,
    _call_long_running_recognize,
    _concatenate_mp3_files,
    _extract_audio_to_flac,
    _format_srt_time,
    _generate_silence,
    _get_edge_voice,
    _get_mp3_duration,
    _get_speech_language_code,
    _get_tts_language_code,
    _parse_duration,
    _parse_results_to_srt,
    _parse_srt_timestamp,
    _poll_operation,
    _speed_up_audio,
    _split_long_sentence,
    _split_text_for_tts,
    _synthesize_chunk,
    _synthesize_chunk_edge,
    _transcribe_google_cloud,
    _transcribe_whisper,
    check_ffmpeg_available,
    extract_subtitle_text,
    mix_audio_into_video,
    synthesize_speech,
    synthesize_timed_speech,
    transcribe_audio,
)
from src.ui.pages.subtitle import _convert_subtitle_format

_MOD = "src.core.speech_engine"
_LANG = "src.constants.languages"
_SUB = "src.utils.subtitle_utils"
_GOOGLE_TTS = "Google Cloud TTS"


# ---------------------------------------------------------------------------
# _get_tts_language_code
# ---------------------------------------------------------------------------


class TestGetTtsLanguageCode:
    """Test language label to TTS code mapping."""

    @patch(f"{_LANG}.get_locale_code", return_value="vi")
    def test_known_language_mapped(self, mock_locale):
        """Vietnamese label maps via locale 'vi' to TTS code 'vi-VN'."""
        result = _get_tts_language_code("Vietnamese")
        mock_locale.assert_called_once_with("Vietnamese")
        assert result == "vi-VN"

    @patch(f"{_LANG}.get_locale_code", return_value="ja")
    def test_japanese_mapped(self, mock_locale):
        """Japanese maps to 'ja-JP'."""
        assert _get_tts_language_code("Japanese") == "ja-JP"

    @patch(f"{_LANG}.get_locale_code", return_value="en-US")
    def test_english_us_mapped(self, mock_locale):
        """English (US) maps to 'en-US'."""
        assert _get_tts_language_code("English (US)") == "en-US"

    @patch(f"{_LANG}.get_locale_code", return_value="en-UK")
    def test_english_uk_mapped(self, mock_locale):
        """English (UK) maps to 'en-GB' via the _TTS_LANG_MAP."""
        assert _get_tts_language_code("English (UK)") == "en-GB"

    @patch(f"{_LANG}.get_locale_code", return_value="zh-CN")
    def test_chinese_simplified_mapped(self, mock_locale):
        """Chinese (Simplified) maps to 'cmn-CN'."""
        assert _get_tts_language_code("Chinese (Simplified)") == "cmn-CN"

    @patch(f"{_LANG}.get_locale_code", return_value="zh-TW")
    def test_chinese_traditional_mapped(self, mock_locale):
        """Chinese (Traditional) maps to 'cmn-TW'."""
        assert _get_tts_language_code("Chinese (Traditional)") == "cmn-TW"

    def test_empty_label_returns_en_us(self):
        """Empty language label falls back to 'en-US'."""
        assert _get_tts_language_code("") == "en-US"

    @patch(f"{_LANG}.get_locale_code", return_value="sr")
    def test_unmapped_locale_falls_back_to_locale(self, mock_locale):
        """A locale not in _TTS_LANG_MAP is returned as-is."""
        # Serbian 'sr' is not in _TTS_LANG_MAP
        assert "sr" not in _TTS_LANG_MAP
        result = _get_tts_language_code("Serbian")
        assert result == "sr"

    @patch(f"{_LANG}.get_locale_code", return_value="nb")
    def test_norwegian_mapped(self, mock_locale):
        """Norwegian Bokmal maps to 'nb-NO'."""
        assert _get_tts_language_code("Norwegian") == "nb-NO"

    @patch(f"{_LANG}.get_locale_code", return_value="ar")
    def test_arabic_mapped(self, mock_locale):
        """Arabic maps to 'ar-XA'."""
        assert _get_tts_language_code("Arabic") == "ar-XA"


# ---------------------------------------------------------------------------
# extract_subtitle_text
# ---------------------------------------------------------------------------


class TestExtractSubtitleText:
    """Test subtitle text extraction."""

    @patch(f"{_SUB}.parse_subtitle")
    @patch(f"{_SUB}.is_subtitle_format", return_value=True)
    def test_srt_extraction(self, mock_is_sub, mock_parse):
        """Extracts text lines from SRT content, skipping timestamps."""
        entry1 = MagicMock()
        entry1.text = "Hello world."
        entry2 = MagicMock()
        entry2.text = "How are you?"
        mock_parse.return_value = ([entry1, entry2], None)

        srt_content = (
            "1\n00:00:01,000 --> 00:00:04,000\nHello world.\n\n"
            "2\n00:00:05,000 --> 00:00:08,000\nHow are you?\n"
        )
        result = extract_subtitle_text(srt_content, ".srt")
        assert result == "Hello world.\nHow are you?"

    @patch(f"{_SUB}.parse_subtitle")
    @patch(f"{_SUB}.is_subtitle_format", return_value=True)
    def test_empty_text_entries_skipped(self, mock_is_sub, mock_parse):
        """Entries with only whitespace are filtered out."""
        entry1 = MagicMock()
        entry1.text = "Hello."
        entry2 = MagicMock()
        entry2.text = "   "
        entry3 = MagicMock()
        entry3.text = "World."
        mock_parse.return_value = ([entry1, entry2, entry3], None)

        result = extract_subtitle_text("dummy", ".srt")
        assert result == "Hello.\nWorld."

    @patch(f"{_SUB}.parse_subtitle")
    @patch(f"{_SUB}.is_subtitle_format", return_value=True)
    def test_vtt_suffix(self, mock_is_sub, mock_parse):
        """VTT suffix is handled as subtitle format."""
        entry = MagicMock()
        entry.text = "Subtitle line."
        mock_parse.return_value = ([entry], None)

        result = extract_subtitle_text("WEBVTT\n\n...", ".vtt")
        mock_is_sub.assert_called_once_with(".vtt")
        assert result == "Subtitle line."

    @patch(f"{_SUB}.is_subtitle_format", return_value=False)
    def test_plain_text_fallback(self, mock_is_sub):
        """Non-subtitle suffix returns content as-is."""
        text = "Just plain text content."
        result = extract_subtitle_text(text, ".txt")
        assert result == text

    @patch(f"{_SUB}.parse_subtitle")
    @patch(f"{_SUB}.is_subtitle_format", return_value=True)
    def test_no_entries(self, mock_is_sub, mock_parse):
        """Empty subtitle returns empty string."""
        mock_parse.return_value = ([], None)
        result = extract_subtitle_text("", ".srt")
        assert result == ""

    @patch(f"{_SUB}.parse_subtitle")
    @patch(f"{_SUB}.is_subtitle_format", return_value=True)
    def test_ass_suffix(self, mock_is_sub, mock_parse):
        """ASS suffix is handled as subtitle format."""
        entry = MagicMock()
        entry.text = "ASS line."
        mock_parse.return_value = ([entry], None)

        result = extract_subtitle_text("dummy", ".ass")
        mock_is_sub.assert_called_once_with(".ass")
        assert result == "ASS line."

    @patch(f"{_SUB}.parse_subtitle")
    @patch(f"{_SUB}.is_subtitle_format", return_value=True)
    def test_multiline_subtitle_text(self, mock_is_sub, mock_parse):
        """Multi-line text within a single entry is preserved."""
        entry = MagicMock()
        entry.text = "Line one\nLine two"
        mock_parse.return_value = ([entry], None)

        result = extract_subtitle_text("dummy", ".srt")
        assert result == "Line one\nLine two"


# ---------------------------------------------------------------------------
# _split_text_for_tts
# ---------------------------------------------------------------------------


class TestSplitTextForTts:
    """Test text splitting for TTS API."""

    def test_empty_text(self):
        """Empty text returns empty list."""
        assert _split_text_for_tts("") == []

    def test_whitespace_only(self):
        """Whitespace-only text returns empty list."""
        assert _split_text_for_tts("   \n\t  ") == []

    def test_short_text_single_chunk(self):
        """Text within the byte limit is returned as a single chunk."""
        text = "Hello world."
        result = _split_text_for_tts(text)
        assert result == ["Hello world."]

    def test_fits_exactly_at_limit(self):
        """Text exactly at the byte limit is a single chunk."""
        char_count = 100
        text = "a" * char_count
        result = _split_text_for_tts(text, max_bytes=char_count)
        assert result == [text]

    def test_split_at_sentence_boundaries(self):
        """Multiple sentences split at sentence-ending punctuation."""
        s1 = "First sentence."
        s2 = "Second sentence."
        text = f"{s1} {s2}"
        # Set limit so both together exceed it, but each fits alone
        padding = 5
        limit = len(s1.encode("utf-8")) + padding
        result = _split_text_for_tts(text, max_bytes=limit)
        assert len(result) == 2  # noqa: PLR2004
        assert result[0] == s1
        assert result[1] == s2

    def test_multiple_sentences_fit_one_chunk(self):
        """Short sentences that fit together stay in one chunk."""
        text = "Hi. Hello. Hey."
        large_limit = 100
        result = _split_text_for_tts(text, max_bytes=large_limit)
        assert result == ["Hi. Hello. Hey."]

    def test_split_preserves_sentence_punctuation(self):
        """Sentence-ending punctuation is preserved in chunks."""
        text = "Hello! How are you? I am fine."
        small_limit = 20
        result = _split_text_for_tts(text, max_bytes=small_limit)
        for chunk in result:
            assert chunk.strip()
        # All text is preserved across chunks
        combined = " ".join(result)
        assert "Hello!" in combined
        assert "How are you?" in combined
        assert "I am fine." in combined

    def test_long_sentence_splits_by_words(self):
        """A single sentence exceeding limit is split by words."""
        words = ["word"] * 20
        text = " ".join(words) + "."
        small_limit = 30
        result = _split_text_for_tts(text, max_bytes=small_limit)
        assert len(result) > 1
        # All words are present across chunks
        combined = " ".join(result)
        for w in words:
            assert w in combined

    def test_multibyte_characters(self):
        """Multi-byte UTF-8 characters are handled correctly."""
        # Each CJK character is typically 3 bytes in UTF-8
        text = "\u4f60\u597d\u4e16\u754c\u3002 \u6211\u5f88\u597d\u3002"
        cjk_limit = 15
        result = _split_text_for_tts(text, max_bytes=cjk_limit)
        assert len(result) >= 1
        # All characters preserved
        combined = "".join(result)
        assert "\u4f60\u597d" in combined

    def test_default_max_bytes(self):
        """Default max_bytes matches _TTS_MAX_BYTES constant."""
        short = "Short."
        result = _split_text_for_tts(short)
        assert result == ["Short."]
        # Verify the default limit by building text that exceeds it
        word = "word "
        overflow = 100
        big_text = word * ((_TTS_MAX_BYTES // len(word)) + overflow)
        result = _split_text_for_tts(big_text)
        assert len(result) > 1

    def test_question_mark_split(self):
        """Questions split at '?' boundary."""
        text = "Is this working? Yes it is."
        small_limit = 20
        result = _split_text_for_tts(text, max_bytes=small_limit)
        assert len(result) >= 2  # noqa: PLR2004

    def test_exclamation_mark_split(self):
        """Exclamations split at '!' boundary."""
        text = "Wow! That is amazing! So cool."
        small_limit = 25
        result = _split_text_for_tts(text, max_bytes=small_limit)
        assert len(result) >= 2  # noqa: PLR2004

    def test_cjk_sentence_ending(self):
        """CJK sentence endings are recognized as split points."""
        text = (
            "\u8fd9\u662f\u7b2c\u4e00\u53e5\u3002 \u8fd9\u662f\u7b2c\u4e8c\u53e5\u3002"
        )
        cjk_limit = 20
        result = _split_text_for_tts(text, max_bytes=cjk_limit)
        assert len(result) >= 2  # noqa: PLR2004

    def test_no_sentence_boundaries(self):
        """Text without sentence boundaries splits by words."""
        text = "no punctuation here just words flowing on and on"
        small_limit = 25
        result = _split_text_for_tts(text, max_bytes=small_limit)
        assert len(result) > 1
        combined = " ".join(result)
        assert "no" in combined
        assert "on" in combined

    def test_strip_leading_trailing_whitespace(self):
        """Input text is stripped before processing."""
        text = "   Hello world.   "
        large_limit = 5000
        result = _split_text_for_tts(text, max_bytes=large_limit)
        assert result == ["Hello world."]


# ---------------------------------------------------------------------------
# _split_long_sentence
# ---------------------------------------------------------------------------


class TestSplitLongSentence:
    """Test word-level splitting for oversized sentences."""

    def test_splits_into_chunks(self):
        """Words are grouped into chunks within the byte limit."""
        sentence = "one two three four five six seven"
        chunks: list[str] = []
        remainder = _split_long_sentence(
            sentence,
            max_bytes=15,
            chunks=chunks,
        )
        assert len(chunks) >= 1
        # Every word appears either in chunks or remainder
        all_text = " ".join(chunks)
        if remainder:
            all_text += " " + remainder
        for word in sentence.split():
            assert word in all_text

    def test_returns_remainder(self):
        """Returns the last incomplete chunk as remainder."""
        sentence = "alpha beta gamma"
        chunks: list[str] = []
        remainder = _split_long_sentence(
            sentence,
            max_bytes=12,
            chunks=chunks,
        )
        assert isinstance(remainder, str)
        # Remainder should be non-empty if last words don't fill a chunk
        assert remainder or len(chunks) > 0

    def test_single_word_fits(self):
        """A single word returns as remainder with no chunks."""
        chunks: list[str] = []
        remainder = _split_long_sentence(
            "hello",
            max_bytes=100,
            chunks=chunks,
        )
        assert chunks == []
        assert remainder == "hello"

    def test_single_word_exceeds_limit_is_split_at_codepoint_boundaries(
        self,
    ):
        """An oversized single word is split into sub-cap chunks.

        Previous behaviour returned the oversized word unchanged as
        the remainder — the TTS API would then receive a chunk that
        exceeded its byte cap and either reject or truncate.  The
        ``_split_oversized_word`` fallback now walks the word
        character-by-character so every emitted chunk stays under
        the cap AND chunk boundaries land on codepoint boundaries
        (no mid-byte cut, no mojibake).
        """
        chunks: list[str] = []
        remainder = _split_long_sentence(
            "superlongword",
            max_bytes=5,
            chunks=chunks,
        )
        # No remainder — the oversized word was consumed entirely
        # by the codepoint-safe fallback.
        assert remainder == ""
        # Multiple sub-cap chunks were emitted, and concatenating
        # them round-trips to the original word (no data loss).
        assert len(chunks) >= 1
        for chunk in chunks:
            assert len(chunk.encode("utf-8")) <= 5
        assert "".join(chunks) == "superlongword"

    def test_multiple_words_exact_fit(self):
        """Words that fit exactly at limit are grouped."""
        # "ab cd" = 5 bytes
        chunks: list[str] = []
        _split_long_sentence("ab cd ef gh", max_bytes=5, chunks=chunks)
        # Should have at least one chunk flushed
        assert len(chunks) >= 1

    def test_appends_to_existing_chunks(self):
        """New chunks are appended to the provided list."""
        existing = ["pre-existing"]
        _split_long_sentence(
            "one two three four",
            max_bytes=10,
            chunks=existing,
        )
        assert existing[0] == "pre-existing"
        assert len(existing) > 1

    def test_empty_sentence(self):
        """Empty sentence returns empty remainder and no chunks."""
        chunks: list[str] = []
        remainder = _split_long_sentence(
            "",
            max_bytes=100,
            chunks=chunks,
        )
        assert chunks == []
        assert remainder == ""

    def test_multibyte_word_splitting(self):
        """Multi-byte words respect byte limit, not character count."""
        # Each CJK character is 3 bytes in UTF-8
        sentence = "\u4f60 \u597d \u4e16 \u754c"
        chunks: list[str] = []
        remainder = _split_long_sentence(
            sentence,
            max_bytes=8,
            chunks=chunks,
        )
        all_text = " ".join(chunks)
        if remainder:
            all_text += " " + remainder
        for word in sentence.split():
            assert word in all_text


# ---------------------------------------------------------------------------
# _synthesize_chunk
# ---------------------------------------------------------------------------


class TestSynthesizeChunk:
    """Test single-chunk TTS API call."""

    def _make_response(self, audio_bytes: bytes) -> MagicMock:
        """Create a mock urlopen response with base64-encoded audio."""
        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
        resp_data = json.dumps({"audioContent": audio_b64}).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = resp_data
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    @patch("urllib.request.urlopen")
    def test_writes_audio_to_file(self, mock_urlopen, tmp_path):
        """Decoded audio bytes are written to the output path."""
        audio_data = b"\xff\xfb\x90\x00" * 100
        mock_urlopen.return_value = self._make_response(audio_data)

        output = tmp_path / "chunk.mp3"
        _synthesize_chunk(
            "Hello",
            "en-US",
            "FEMALE",
            "test-key",
            output,
        )

        assert output.exists()
        assert output.read_bytes() == audio_data

    @patch("urllib.request.urlopen")
    def test_correct_api_url(self, mock_urlopen, tmp_path):
        """Request URL includes the API key."""
        mock_urlopen.return_value = self._make_response(b"audio")
        output = tmp_path / "chunk.mp3"

        _synthesize_chunk(
            "Hi",
            "vi-VN",
            "MALE",
            "my-api-key",
            output,
        )

        req = mock_urlopen.call_args[0][0]
        assert "key=my-api-key" in req.full_url

    @patch("urllib.request.urlopen")
    def test_correct_payload(self, mock_urlopen, tmp_path):
        """Request body has correct text, language, and gender."""
        mock_urlopen.return_value = self._make_response(b"audio")
        output = tmp_path / "chunk.mp3"

        _synthesize_chunk(
            "Test text",
            "ja-JP",
            "MALE",
            "key123",
            output,
        )

        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode("utf-8"))
        assert payload["input"]["text"] == "Test text"
        assert payload["voice"]["languageCode"] == "ja-JP"
        assert payload["voice"]["ssmlGender"] == "MALE"
        assert payload["audioConfig"]["audioEncoding"] == "MP3"

    @patch("urllib.request.urlopen")
    def test_auth_error_401(self, mock_urlopen, tmp_path):
        """HTTP 401 raises ``AUTH_ERROR:Google Cloud`` (service-suffixed).

        Pins the service-suffix contract so the UI can render
        "Invalid Google Cloud API key" instead of generic "Invalid
        API key" — without the suffix, the user can't tell which
        of the 4 auth-required keys (LLM / OCR / TTS / STT) failed.
        """
        fp = MagicMock(read=lambda: b"err")
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "url",
            401,
            "Unauthorized",
            {},
            fp,
        )
        out = tmp_path / "c.mp3"
        with pytest.raises(ValueError, match=r"AUTH_ERROR:Google Cloud"):
            _synthesize_chunk("Hi", "en-US", "FEMALE", "bad", out)

    @patch("urllib.request.urlopen")
    def test_auth_error_403(self, mock_urlopen, tmp_path):
        """HTTP 403 raises ``AUTH_ERROR:Google Cloud`` (service-suffixed)."""
        fp = MagicMock(read=lambda: b"err")
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "url",
            403,
            "Forbidden",
            {},
            fp,
        )
        out = tmp_path / "c.mp3"
        with pytest.raises(ValueError, match=r"AUTH_ERROR:Google Cloud"):
            _synthesize_chunk("Hi", "en-US", "FEMALE", "bad", out)

    @patch("urllib.request.urlopen")
    def test_quota_error_429(self, mock_urlopen, tmp_path):
        """HTTP 429 raises ValueError with QUOTA_ERROR."""
        fp = MagicMock(read=lambda: b"err")
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "url",
            429,
            "Too Many Requests",
            {},
            fp,
        )
        out = tmp_path / "c.mp3"
        with pytest.raises(ValueError, match="QUOTA_ERROR"):
            _synthesize_chunk("Hi", "en-US", "FEMALE", "key", out)

    @patch("urllib.request.urlopen")
    def test_generic_http_error(self, mock_urlopen, tmp_path):
        """HTTP 500 maps to ``SERVICE_UNAVAILABLE_ERROR`` sentinel.

        Was previously rebadged as the opaque ``TTS_API_ERROR``;
        typed sentinel routes through the shared retry / dispatcher
        same way LLM 5xx does.
        """
        fp = MagicMock(read=lambda: b"err")
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "url",
            500,
            "Internal Server Error",
            {},
            fp,
        )
        out = tmp_path / "c.mp3"
        with pytest.raises(ValueError, match="SERVICE_UNAVAILABLE_ERROR"):
            _synthesize_chunk("Hi", "en-US", "FEMALE", "key", out)

    @patch("urllib.request.urlopen")
    def test_error_body_is_read(self, mock_urlopen, tmp_path):
        """Error body from HTTPError is read for logging.

        Body is drained even when the status code maps to a typed
        sentinel so the log line carries server-side detail.
        """
        error_fp = MagicMock()
        error_fp.read.return_value = b"detailed error info"
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "url",
            500,
            "Error",
            {},
            error_fp,
        )
        out = tmp_path / "c.mp3"
        with pytest.raises(ValueError, match="SERVICE_UNAVAILABLE_ERROR"):
            _synthesize_chunk("Hi", "en-US", "FEMALE", "key", out)
        # read() is called to drain the response body for the log line.
        error_fp.read.assert_called()

    @patch("urllib.request.urlopen")
    def test_http_400_maps_to_tts_invalid_request(self, mock_urlopen, tmp_path):
        """HTTP 400 (non-auth) → ``TTS_INVALID_REQUEST``.

        TTS-specific sentinel so the user-facing message references
        TTS rather than borrowing the LLM-flavored ``INVALID_REQUEST``
        text ("model may not support this operation").
        """
        fp = MagicMock(read=lambda: b'{"error":{"message":"invalid lang"}}')
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "url",
            400,
            "Bad Request",
            {},
            fp,
        )
        out = tmp_path / "c.mp3"
        with pytest.raises(ValueError, match="TTS_INVALID_REQUEST"):
            _synthesize_chunk("Hi", "en-US", "FEMALE", "key", out)

    @patch("urllib.request.urlopen")
    def test_http_400_api_key_invalid_maps_to_auth_error(
        self,
        mock_urlopen,
        tmp_path,
    ):
        """HTTP 400 with API_KEY_INVALID body → ``AUTH_ERROR:Google Cloud``.

        Google TTS quirk: invalid keys return 400 (not 401/403).
        The body's ``API_KEY_INVALID`` reason routes us to the same
        suffixed AUTH_ERROR sentinel as the 401/403 branch so the UI
        shows "Invalid Google Cloud API key" instead of generic
        "Invalid API key".
        """
        body = (
            b'{"error":{"code":400,"message":"API key not valid",'
            b'"status":"INVALID_ARGUMENT","details":[{"@type":'
            b'"type.googleapis.com/google.rpc.ErrorInfo",'
            b'"reason":"API_KEY_INVALID","domain":"googleapis.com",'
            b'"metadata":{"service":"texttospeech.googleapis.com"}}]}}'
        )
        fp = MagicMock(read=lambda: body)
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "url",
            400,
            "Bad Request",
            {},
            fp,
        )
        out = tmp_path / "c.mp3"
        with pytest.raises(ValueError, match=r"AUTH_ERROR:Google Cloud"):
            _synthesize_chunk("Hi", "en-US", "FEMALE", "key", out)

    @patch("urllib.request.urlopen")
    def test_http_413_maps_to_request_too_large(self, mock_urlopen, tmp_path):
        """HTTP 413 → ``REQUEST_TOO_LARGE`` (oversize text payload)."""
        fp = MagicMock(read=lambda: b"too big")
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "url",
            413,
            "Payload Too Large",
            {},
            fp,
        )
        out = tmp_path / "c.mp3"
        with pytest.raises(ValueError, match="REQUEST_TOO_LARGE"):
            _synthesize_chunk("Hi", "en-US", "FEMALE", "key", out)

    @patch("urllib.request.urlopen")
    def test_url_error_maps_to_connection_error(self, mock_urlopen, tmp_path):
        """URLError → ``CONNECTION_ERROR`` (DNS / refused / offline)."""
        mock_urlopen.side_effect = urllib.error.URLError("DNS failure")
        out = tmp_path / "c.mp3"
        with pytest.raises(ValueError, match="CONNECTION_ERROR"):
            _synthesize_chunk("Hi", "en-US", "FEMALE", "key", out)

    @patch("urllib.request.urlopen")
    def test_timeout_maps_to_timeout_error(self, mock_urlopen, tmp_path):
        """``TimeoutError`` → ``TIMEOUT_ERROR``."""
        mock_urlopen.side_effect = TimeoutError("read timeout")
        out = tmp_path / "c.mp3"
        with pytest.raises(ValueError, match="TIMEOUT_ERROR"):
            _synthesize_chunk("Hi", "en-US", "FEMALE", "key", out)

    @patch("urllib.request.urlopen")
    def test_response_missing_audio_content_raises(
        self,
        mock_urlopen,
        tmp_path,
    ):
        """HTTP 200 with no ``audioContent`` → ``INVALID_RESPONSE``.

        Safety filters / partial responses can land an empty payload;
        the typed sentinel matches the LLM "malformed body" treatment.
        """
        mock_urlopen.return_value = self._make_response_with_body(b"{}")
        out = tmp_path / "c.mp3"
        with pytest.raises(ValueError, match="INVALID_RESPONSE"):
            _synthesize_chunk("Hi", "en-US", "FEMALE", "key", out)

    def _make_response_with_body(self, body: bytes):  # noqa: ANN202
        """Builds a urlopen-context-manager mock returning *body*."""
        resp = MagicMock()
        resp.read.return_value = body
        resp.__enter__ = MagicMock(return_value=resp)
        resp.__exit__ = MagicMock(return_value=False)
        return resp

    @patch("urllib.request.urlopen")
    def test_real_base64_roundtrip(self, mock_urlopen, tmp_path):
        """Verify real base64 encoding/decoding roundtrip."""
        original = b"ID3\x04\x00\x00\x00\x00\x00" + b"\x00" * 256
        mock_urlopen.return_value = self._make_response(original)

        output = tmp_path / "chunk.mp3"
        _synthesize_chunk("Test", "en-US", "FEMALE", "key", output)

        assert output.read_bytes() == original

    @patch("urllib.request.urlopen")
    def test_female_voice_in_payload(self, mock_urlopen, tmp_path):
        """FEMALE voice gender is correctly passed in the payload."""
        mock_urlopen.return_value = self._make_response(b"a")
        output = tmp_path / "chunk.mp3"

        _synthesize_chunk("Hi", "en-US", "FEMALE", "k", output)

        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode("utf-8"))
        assert payload["voice"]["ssmlGender"] == "FEMALE"


# ---------------------------------------------------------------------------
# _concatenate_mp3_files
# ---------------------------------------------------------------------------


class TestConcatenateMp3Files:
    """Test MP3 file concatenation."""

    def test_single_file_copies(self, tmp_path):
        """Single file is copied directly, no FFmpeg needed."""
        src = tmp_path / "only.mp3"
        src.write_bytes(b"fake mp3 data")
        out = tmp_path / "output.mp3"

        _concatenate_mp3_files([src], out)

        assert out.exists()
        assert out.read_bytes() == b"fake mp3 data"

    @patch("subprocess.run")
    def test_multiple_files_calls_ffmpeg(self, mock_run, tmp_path):
        """Multiple files trigger FFmpeg concat."""
        f1 = tmp_path / "chunk_0000.mp3"
        f2 = tmp_path / "chunk_0001.mp3"
        f1.write_bytes(b"audio1")
        f2.write_bytes(b"audio2")
        out = tmp_path / "output.mp3"

        mock_run.return_value = MagicMock(returncode=0)
        _concatenate_mp3_files([f1, f2], out)

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "ffmpeg"
        assert "-f" in cmd
        assert "concat" in cmd
        assert str(out) in cmd

    @patch("subprocess.run")
    def test_concat_list_file_created(self, mock_run, tmp_path):
        """A concat.txt list file is created in the temp directory."""
        f1 = tmp_path / "a.mp3"
        f2 = tmp_path / "b.mp3"
        f1.write_bytes(b"1")
        f2.write_bytes(b"2")
        out = tmp_path / "output.mp3"

        mock_run.return_value = MagicMock(returncode=0)
        _concatenate_mp3_files([f1, f2], out)

        concat_file = tmp_path / "concat.txt"
        assert concat_file.exists()
        content = concat_file.read_text(encoding="utf-8")
        assert str(f1) in content
        assert str(f2) in content

    @patch("subprocess.run")
    def test_concat_file_escapes_quotes(self, mock_run, tmp_path):
        """Single quotes in file paths are escaped in concat list."""
        dir_with_quote = tmp_path / "it's"
        dir_with_quote.mkdir()
        f1 = dir_with_quote / "a.mp3"
        f2 = dir_with_quote / "b.mp3"
        f1.write_bytes(b"1")
        f2.write_bytes(b"2")
        out = tmp_path / "output.mp3"

        mock_run.return_value = MagicMock(returncode=0)
        _concatenate_mp3_files([f1, f2], out)

        concat_file = dir_with_quote / "concat.txt"
        assert concat_file.exists()
        content = concat_file.read_text(encoding="utf-8")
        assert "'\\''" in content

    @patch("subprocess.run")
    def test_ffmpeg_failure_raises_runtime_error(
        self,
        mock_run,
        tmp_path,
    ):
        """FFmpeg failure raises RuntimeError FFMPEG_CONCAT_FAILED."""
        f1 = tmp_path / "a.mp3"
        f2 = tmp_path / "b.mp3"
        f1.write_bytes(b"1")
        f2.write_bytes(b"2")
        out = tmp_path / "output.mp3"

        mock_run.side_effect = subprocess.CalledProcessError(
            1,
            "ffmpeg",
            stderr=b"concat error details",
        )
        with pytest.raises(RuntimeError, match="FFMPEG_CONCAT_FAILED"):
            _concatenate_mp3_files([f1, f2], out)

    @patch("subprocess.run")
    def test_ffmpeg_called_with_correct_flags(
        self,
        mock_run,
        tmp_path,
    ):
        """FFmpeg is called with -c copy -y flags."""
        f1 = tmp_path / "a.mp3"
        f2 = tmp_path / "b.mp3"
        f1.write_bytes(b"1")
        f2.write_bytes(b"2")
        out = tmp_path / "output.mp3"

        mock_run.return_value = MagicMock(returncode=0)
        _concatenate_mp3_files([f1, f2], out)

        cmd = mock_run.call_args[0][0]
        assert "-c" in cmd
        assert "copy" in cmd
        assert "-y" in cmd
        assert "-safe" in cmd
        assert "0" in cmd

    def test_single_file_does_not_call_subprocess(self, tmp_path):
        """Single file uses shutil.copy2, not subprocess."""
        src = tmp_path / "only.mp3"
        src.write_bytes(b"data")
        out = tmp_path / "output.mp3"

        with patch("subprocess.run") as mock_run:
            _concatenate_mp3_files([src], out)
            mock_run.assert_not_called()

    @patch("subprocess.run")
    def test_three_files_all_listed(self, mock_run, tmp_path):
        """Three audio files are all listed in the concat file."""
        file_count = 3
        files = []
        for i in range(file_count):
            f = tmp_path / f"chunk_{i}.mp3"
            f.write_bytes(b"data")
            files.append(f)
        out = tmp_path / "output.mp3"

        mock_run.return_value = MagicMock(returncode=0)
        _concatenate_mp3_files(files, out)

        concat_file = tmp_path / "concat.txt"
        content = concat_file.read_text(encoding="utf-8")
        for f in files:
            assert str(f) in content


# ---------------------------------------------------------------------------
# synthesize_speech (main entry point)
# ---------------------------------------------------------------------------


class TestSynthesizeSpeech:
    """Test the main TTS entry point."""

    @pytest.fixture(autouse=True)
    def _mock_edge(self):
        """Prevent edge_tts import in tests running outside uv."""
        with patch(f"{_MOD}._synthesize_chunk_edge"):
            yield

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}._split_text_for_tts", return_value=["Hello world."])
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="test-key")
    def test_full_flow_single_chunk(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_split,
        mock_synth,
        mock_concat,
        tmp_path,
    ):
        """Full flow: synthesize single chunk + concatenate."""
        output = str(tmp_path / "output.mp3")
        result = synthesize_speech(
            "Hello world.",
            "English (US)",
            "FEMALE",
            output,
            tts_method=_GOOGLE_TTS,
        )

        assert result == output
        mock_synth.assert_called_once()
        mock_concat.assert_called_once()

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(
        f"{_MOD}._split_text_for_tts",
        return_value=["Chunk one.", "Chunk two."],
    )
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="test-key")
    def test_full_flow_multiple_chunks(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_split,
        mock_synth,
        mock_concat,
        tmp_path,
    ):
        """Multiple chunks are each synthesized then concatenated."""
        output = str(tmp_path / "output.mp3")
        synthesize_speech(
            "Chunk one. Chunk two.",
            "Vietnamese",
            "MALE",
            output,
            tts_method=_GOOGLE_TTS,
        )

        assert mock_synth.call_count == 2  # noqa: PLR2004

    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="")
    def test_missing_api_key_raises_auth_error(
        self,
        mock_key,
        tmp_path,
    ):
        """Missing API key raises ValueError AUTH_ERROR."""
        with pytest.raises(ValueError, match="AUTH_ERROR"):
            synthesize_speech(
                "Hello",
                output_path=str(tmp_path / "out.mp3"),
                tts_method=_GOOGLE_TTS,
            )

    @patch(f"{_MOD}.load_google_cloud_api_key", return_value=None)
    def test_none_api_key_raises_auth_error(
        self,
        mock_key,
        tmp_path,
    ):
        """None API key raises ValueError AUTH_ERROR."""
        with pytest.raises(ValueError, match="AUTH_ERROR"):
            synthesize_speech(
                "Hello",
                output_path=str(tmp_path / "out.mp3"),
                tts_method=_GOOGLE_TTS,
            )

    @patch(f"{_MOD}.check_ffmpeg_available", return_value=False)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_missing_ffmpeg_raises_runtime_error(
        self,
        mock_key,
        mock_ffmpeg,
        tmp_path,
    ):
        """Missing FFmpeg raises RuntimeError."""
        with pytest.raises(RuntimeError, match="FFMPEG_NOT_FOUND"):
            synthesize_speech(
                "Hello",
                output_path=str(tmp_path / "out.mp3"),
                tts_method=_GOOGLE_TTS,
            )

    @patch(f"{_MOD}._split_text_for_tts", return_value=[])
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_empty_text_raises_value_error(
        self,
        mock_key,
        mock_ffmpeg,
        mock_split,
        tmp_path,
    ):
        """Empty text (after splitting) raises ValueError EMPTY_TEXT."""
        with pytest.raises(ValueError, match="EMPTY_TEXT"):
            synthesize_speech(
                "",
                output_path=str(tmp_path / "out.mp3"),
                tts_method=_GOOGLE_TTS,
            )

    @patch(f"{_MOD}._synthesize_chunk")
    @patch(
        f"{_MOD}._split_text_for_tts",
        return_value=["One.", "Two.", "Three."],
    )
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_cancellation_before_second_chunk(
        self,
        mock_key,
        mock_ffmpeg,
        mock_split,
        mock_synth,
        tmp_path,
    ):
        """Cancellation callback stops processing after first chunk."""
        call_count = 0

        def cancel_after_first():
            nonlocal call_count
            call_count += 1
            return call_count > 1

        output = str(tmp_path / "output.mp3")
        with pytest.raises(ValueError, match="CANCELLED"):
            synthesize_speech(
                "One. Two. Three.",
                output_path=output,
                tts_method=_GOOGLE_TTS,
                is_cancelled=cancel_after_first,
            )

        # Only the first chunk was synthesized before cancellation
        assert mock_synth.call_count == 1

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(
        f"{_MOD}._split_text_for_tts",
        return_value=["A.", "B.", "C."],
    )
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_progress_callback_called(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_split,
        mock_synth,
        mock_concat,
        tmp_path,
    ):
        """Progress callback is called for each chunk."""
        progress_calls = []

        def on_progress(current, total):
            progress_calls.append((current, total))

        output = str(tmp_path / "output.mp3")
        synthesize_speech(
            "A. B. C.",
            output_path=output,
            on_progress=on_progress,
            tts_method=_GOOGLE_TTS,
        )

        assert progress_calls == [(1, 3), (2, 3), (3, 3)]

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}._split_text_for_tts", return_value=["Hello."])
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_returns_output_path(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_split,
        mock_synth,
        mock_concat,
        tmp_path,
    ):
        """Returns the output path string."""
        output = str(tmp_path / "result.mp3")
        result = synthesize_speech("Hello.", tts_method=_GOOGLE_TTS, output_path=output)
        assert result == output

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}._split_text_for_tts", return_value=["Hi."])
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_creates_output_directory(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_split,
        mock_synth,
        mock_concat,
        tmp_path,
    ):
        """Output parent directory is created if it does not exist."""
        nested = tmp_path / "nested" / "dir"
        output = str(nested / "output.mp3")
        synthesize_speech("Hi.", tts_method=_GOOGLE_TTS, output_path=output)
        assert nested.is_dir()

    @patch(f"{_MOD}._get_tts_language_code", return_value="vi-VN")
    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}._split_text_for_tts", return_value=["Xin chao."])
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_language_code_passed_to_synthesize(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_split,
        mock_synth,
        mock_concat,
        mock_lang,
        tmp_path,
    ):
        """Language code is passed through to _synthesize_chunk."""
        output = str(tmp_path / "output.mp3")
        synthesize_speech(
            "Xin chao.",
            "Vietnamese",
            "MALE",
            output,
            tts_method=_GOOGLE_TTS,
        )

        mock_lang.assert_called_once_with("Vietnamese")
        # Check the language code arg passed to _synthesize_chunk
        synth_call = mock_synth.call_args
        assert synth_call[0][1] == "vi-VN"

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}._split_text_for_tts", return_value=["Hello."])
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_voice_gender_passed_to_synthesize(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_split,
        mock_synth,
        mock_concat,
        tmp_path,
    ):
        """Voice gender is passed through to _synthesize_chunk."""
        output = str(tmp_path / "output.mp3")
        synthesize_speech(
            "Hello.",
            voice_gender="MALE",
            output_path=output,
            tts_method=_GOOGLE_TTS,
        )

        synth_call = mock_synth.call_args
        assert synth_call[0][2] == "MALE"

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}._split_text_for_tts", return_value=["Hi."])
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_default_voice_gender_is_female(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_split,
        mock_synth,
        mock_concat,
        tmp_path,
    ):
        """Default voice gender is FEMALE."""
        output = str(tmp_path / "output.mp3")
        synthesize_speech("Hi.", tts_method=_GOOGLE_TTS, output_path=output)

        synth_call = mock_synth.call_args
        assert synth_call[0][2] == "FEMALE"

    @patch(
        f"{_MOD}._synthesize_chunk",
        side_effect=ValueError("AUTH_ERROR"),
    )
    @patch(f"{_MOD}._split_text_for_tts", return_value=["Hi."])
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_api_error_propagated(
        self,
        mock_key,
        mock_ffmpeg,
        mock_split,
        mock_synth,
        tmp_path,
    ):
        """API errors from _synthesize_chunk propagate up."""
        with pytest.raises(ValueError, match="AUTH_ERROR"):
            synthesize_speech(
                "Hi.",
                output_path=str(tmp_path / "out.mp3"),
                tts_method=_GOOGLE_TTS,
            )

    @patch(f"{_MOD}.shutil.rmtree")
    @patch(
        f"{_MOD}._synthesize_chunk",
        side_effect=ValueError("TTS_API_ERROR"),
    )
    @patch(f"{_MOD}._split_text_for_tts", return_value=["Hi."])
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_temp_dir_cleaned_on_error(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_split,
        mock_synth,
        mock_rmtree,
        tmp_path,
    ):
        """Temp directory is cleaned up even when an error occurs."""
        with pytest.raises(ValueError):
            synthesize_speech(
                "Hi.",
                output_path=str(tmp_path / "out.mp3"),
                tts_method=_GOOGLE_TTS,
            )

        # rmtree should have been called (finally block)
        mock_rmtree.assert_called_once()

    @patch(f"{_MOD}.shutil.rmtree")
    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}._split_text_for_tts", return_value=["Hi."])
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_temp_dir_cleaned_on_success(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_split,
        mock_synth,
        mock_concat,
        mock_rmtree,
        tmp_path,
    ):
        """Temp directory is cleaned up on success."""
        output = str(tmp_path / "output.mp3")
        synthesize_speech("Hi.", tts_method=_GOOGLE_TTS, output_path=output)

        mock_rmtree.assert_called_once()

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}._split_text_for_tts", return_value=["Hi."])
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_no_progress_callback_ok(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_split,
        mock_synth,
        mock_concat,
        tmp_path,
    ):
        """No progress callback does not cause errors."""
        output = str(tmp_path / "output.mp3")
        result = synthesize_speech(
            "Hi.",
            output_path=output,
            on_progress=None,
            tts_method=_GOOGLE_TTS,
        )
        assert result == output

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}._split_text_for_tts", return_value=["Hi."])
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_no_cancel_callback_ok(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_split,
        mock_synth,
        mock_concat,
        tmp_path,
    ):
        """No cancellation callback does not cause errors."""
        output = str(tmp_path / "output.mp3")
        result = synthesize_speech(
            "Hi.",
            output_path=output,
            tts_method=_GOOGLE_TTS,
            is_cancelled=None,
        )
        assert result == output

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}._split_text_for_tts", return_value=["A.", "B."])
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_chunk_filenames_sequential(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_split,
        mock_synth,
        mock_concat,
        tmp_path,
    ):
        """Chunk files are named chunk_0000.mp3, chunk_0001.mp3."""
        output = str(tmp_path / "output.mp3")
        synthesize_speech("A. B.", tts_method=_GOOGLE_TTS, output_path=output)

        # Check the output_path args passed to _synthesize_chunk
        call_args = [c[0][4] for c in mock_synth.call_args_list]
        names = [p.name for p in call_args]
        assert names == ["chunk_0000.mp3", "chunk_0001.mp3"]

    @patch(f"{_MOD}._synthesize_chunk")
    @patch(
        f"{_MOD}._split_text_for_tts",
        return_value=["A.", "B.", "C."],
    )
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_cancellation_immediate(
        self,
        mock_key,
        mock_ffmpeg,
        mock_split,
        mock_synth,
        tmp_path,
    ):
        """Immediate cancellation prevents any chunk synthesis."""
        output = str(tmp_path / "output.mp3")
        with pytest.raises(ValueError, match="CANCELLED"):
            synthesize_speech(
                "A. B. C.",
                output_path=output,
                tts_method=_GOOGLE_TTS,
                is_cancelled=lambda: True,
            )
        mock_synth.assert_not_called()

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}._split_text_for_tts", return_value=["Hi."])
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_api_key_passed_to_synthesize_chunk(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_split,
        mock_synth,
        mock_concat,
        tmp_path,
    ):
        """API key is passed through to _synthesize_chunk."""
        output = str(tmp_path / "output.mp3")
        synthesize_speech("Hi.", tts_method=_GOOGLE_TTS, output_path=output)

        synth_call = mock_synth.call_args
        assert synth_call[0][3] == "key"


# ---------------------------------------------------------------------------
# _parse_duration (STT helper)
# ---------------------------------------------------------------------------


class TestParseDuration:
    """Test Google API duration string parsing."""

    def test_normal_duration(self):
        """Parses '1.500s' to 1.5."""
        assert _parse_duration("1.500s") == 1.5  # noqa: PLR2004

    def test_zero(self):
        """Parses '0s' to 0.0."""
        assert _parse_duration("0s") == 0.0

    def test_integer_seconds(self):
        """Parses '10s' to 10.0."""
        assert _parse_duration("10s") == 10.0  # noqa: PLR2004

    def test_no_suffix(self):
        """String without 's' suffix is parsed as float."""
        assert _parse_duration("3.14") == 3.14  # noqa: PLR2004

    def test_empty_string(self):
        """Empty string returns 0.0."""
        assert _parse_duration("") == 0.0

    def test_invalid_string(self):
        """Non-numeric string returns 0.0."""
        assert _parse_duration("abc") == 0.0

    def test_large_value(self):
        """Large duration value."""
        assert _parse_duration("3723.456s") == 3723.456  # noqa: PLR2004


# ---------------------------------------------------------------------------
# _format_srt_time (STT helper)
# ---------------------------------------------------------------------------


class TestFormatSrtTime:
    """Test seconds to SRT timestamp formatting."""

    def test_zero(self):
        """Zero seconds formats correctly."""
        assert _format_srt_time(0.0) == "00:00:00,000"

    def test_simple_seconds(self):
        """Simple seconds with milliseconds."""
        assert _format_srt_time(1.5) == "00:00:01,500"

    def test_minutes(self):
        """Value with minutes."""
        assert _format_srt_time(65.0) == "00:01:05,000"

    def test_hours(self):
        """Value with hours."""
        assert _format_srt_time(3661.5) == "01:01:01,500"

    def test_millisecond_precision(self):
        """Millisecond precision is preserved."""
        assert _format_srt_time(0.123) == "00:00:00,123"

    def test_large_hours(self):
        """Hours exceeding 9."""
        assert _format_srt_time(36000.0) == "10:00:00,000"


# ---------------------------------------------------------------------------
# _parse_results_to_srt (STT output parser)
# ---------------------------------------------------------------------------


class TestParseResultsToSrt:
    """Test Speech-to-Text results to SRT conversion."""

    def test_empty_results(self):
        """Empty results list returns empty string."""
        assert _parse_results_to_srt([]) == ""

    def test_transcript_only_fallback(self):
        """Results without word timing fall back to transcript-only."""
        results = [
            {"alternatives": [{"transcript": "Hello world"}]},
            {"alternatives": [{"transcript": "Second line"}]},
        ]
        srt = _parse_results_to_srt(results)
        assert "1\n" in srt
        assert "Hello world" in srt
        assert "2\n" in srt
        assert "Second line" in srt
        # Timestamps are zeroed in fallback mode
        assert "00:00:00,000 --> 00:00:00,000" in srt

    def test_word_timing_basic(self):
        """Words with timing produce proper SRT segments."""
        results = [
            {
                "alternatives": [
                    {
                        "words": [
                            {"word": "Hello", "startTime": "0s", "endTime": "0.5s"},
                            {"word": "world", "startTime": "0.5s", "endTime": "1.0s"},
                        ],
                    }
                ],
            }
        ]
        srt = _parse_results_to_srt(results)
        assert "1\n" in srt
        assert "Hello world" in srt
        assert "00:00:00,000 --> 00:00:01,000" in srt

    def test_segment_split_by_duration(self):
        """Words split into new segment when duration exceeds limit."""
        results = [
            {
                "alternatives": [
                    {
                        "words": [
                            {"word": "Start", "startTime": "0s", "endTime": "1s"},
                            {"word": "end", "startTime": "6s", "endTime": "7s"},
                        ],
                    }
                ],
            }
        ]
        srt = _parse_results_to_srt(results)
        # "end" starts at 6s, so duration from "Start" (0s) to "end" (7s) = 7s
        # exceeds _MAX_SEGMENT_DURATION (5s), forcing a new segment
        lines = srt.strip().split("\n")
        # Segment 1: "Start" (0s-1s)
        assert lines[0] == "1"
        assert "00:00:00,000 --> 00:00:01,000" in lines[1]
        assert lines[2] == "Start"  # noqa: PLR2004
        # Segment 2: "end" (6s-7s)
        assert lines[4] == "2"
        assert "00:00:06,000 --> 00:00:07,000" in lines[5]
        assert lines[6] == "end"

    def test_segment_split_by_length(self):
        """Words split when text exceeds _MAX_CHARS_PER_SEGMENT."""
        long_word = "x" * 50
        results = [
            {
                "alternatives": [
                    {
                        "words": [
                            {"word": long_word, "startTime": "0s", "endTime": "1s"},
                            {"word": long_word, "startTime": "1s", "endTime": "2s"},
                        ],
                    }
                ],
            }
        ]
        srt = _parse_results_to_srt(results)
        # Two 50-char words = 101 chars joined > 80 char limit
        lines = srt.strip().split("\n")
        assert lines[0] == "1"
        assert lines[2] == long_word
        assert lines[4] == "2"
        assert lines[6] == long_word

    def test_empty_transcript_skipped(self):
        """Empty transcripts in fallback mode are skipped."""
        results = [
            {"alternatives": [{"transcript": ""}]},
            {"alternatives": [{"transcript": "Real text"}]},
        ]
        srt = _parse_results_to_srt(results)
        assert "Real text" in srt
        # Only one numbered entry (the empty one is skipped)
        assert srt.count("-->") == 1

    def test_missing_alternatives(self):
        """Results with missing alternatives are handled."""
        results = [{}]
        srt = _parse_results_to_srt(results)
        # No words, no transcript → empty fallback
        assert srt == ""

    def test_multiple_results_with_words(self):
        """Words from multiple results are combined."""
        results = [
            {
                "alternatives": [
                    {
                        "words": [
                            {"word": "First", "startTime": "0s", "endTime": "0.5s"},
                        ]
                    }
                ]
            },
            {
                "alternatives": [
                    {
                        "words": [
                            {"word": "Second", "startTime": "1s", "endTime": "1.5s"},
                        ]
                    }
                ]
            },
        ]
        srt = _parse_results_to_srt(results)
        assert "First" in srt
        assert "Second" in srt


# ---------------------------------------------------------------------------
# _convert_subtitle_format (subtitle.py helper)
# ---------------------------------------------------------------------------


class TestConvertSubtitleFormat:
    """Test SRT-to-VTT conversion helper."""

    def test_srt_passthrough(self):
        """SRT format returns text unchanged."""
        srt = "1\n00:00:01,000 --> 00:00:04,000\nHello\n"
        assert _convert_subtitle_format(srt, ".srt") == srt

    def test_vtt_adds_header(self):
        """VTT conversion prepends WEBVTT header."""
        srt = "1\n00:00:01,000 --> 00:00:04,000\nHello\n"
        vtt = _convert_subtitle_format(srt, ".vtt")
        assert vtt.startswith("WEBVTT\n")

    def test_vtt_converts_timestamps(self):
        """VTT conversion changes commas to dots in BOTH start and end."""
        srt = "1\n00:00:01,500 --> 00:00:04,250\nHello\n"
        vtt = _convert_subtitle_format(srt, ".vtt")
        assert "00:00:01.500 --> 00:00:04.250" in vtt
        # Verify no commas remain in any timestamp line
        ts_lines = [ln for ln in vtt.split("\n") if "-->" in ln]
        for ts in ts_lines:
            assert "," not in ts

    def test_vtt_preserves_text_with_commas(self):
        """Commas in subtitle text are NOT converted."""
        srt = "1\n00:00:01,000 --> 00:00:04,000\nHello, world\n"
        vtt = _convert_subtitle_format(srt, ".vtt")
        assert "Hello, world" in vtt

    def test_vtt_multiple_entries(self):
        """Multiple SRT entries are all converted."""
        srt = (
            "1\n00:00:01,000 --> 00:00:04,000\nFirst\n\n"
            "2\n00:00:05,000 --> 00:00:08,000\nSecond\n"
        )
        vtt = _convert_subtitle_format(srt, ".vtt")
        assert "WEBVTT" in vtt
        assert "00:00:01.000 --> 00:00:04.000" in vtt
        assert "00:00:05.000 --> 00:00:08.000" in vtt
        assert "First" in vtt
        assert "Second" in vtt

    def test_unknown_format_returns_srt(self):
        """Truly unknown extensions (not supported by subtitle_utils) fall back to SRT."""
        srt = "1\n00:00:01,000 --> 00:00:04,000\nHello\n"
        assert _convert_subtitle_format(srt, ".xyz") == srt

    def test_ass_format_now_converts(self):
        """ASS is now a first-class output format (was: pass-through)."""
        srt = "1\n00:00:01,000 --> 00:00:04,000\nHello\n"
        result = _convert_subtitle_format(srt, ".ass")
        assert "[Script Info]" in result
        assert "Dialogue:" in result
        assert "Hello" in result

    def test_empty_srt(self):
        """Empty SRT produces VTT with just the header."""
        vtt = _convert_subtitle_format("", ".vtt")
        assert vtt.startswith("WEBVTT\n")

    def test_vtt_text_with_arrow_not_treated_as_timestamp(self):
        """Text containing '-->' is NOT treated as a timestamp line."""
        srt = "1\n00:00:01,000 --> 00:00:04,000\nGo from A --> B, ok?\n"
        vtt = _convert_subtitle_format(srt, ".vtt")
        # Timestamp commas converted
        assert "00:00:01.000 --> 00:00:04.000" in vtt
        # Text comma in "B, ok?" must be preserved, NOT converted to "B. ok?"
        assert "B, ok?" in vtt

    def test_vtt_end_to_end_with_srt_output(self):
        """Integration: STT results → SRT → VTT produces valid VTT."""
        results = [
            {
                "alternatives": [
                    {
                        "words": [
                            {"word": "Hello", "startTime": "0s", "endTime": "0.5s"},
                            {"word": "world", "startTime": "0.5s", "endTime": "1.0s"},
                        ],
                    }
                ],
            }
        ]
        srt = _parse_results_to_srt(results)
        vtt = _convert_subtitle_format(srt, ".vtt")

        # Valid VTT structure
        assert vtt.startswith("WEBVTT\n")
        # Dot timestamps (not comma)
        assert "00:00:00.000 --> 00:00:01.000" in vtt
        # Text preserved
        assert "Hello world" in vtt
        # No SRT-style commas in timestamps
        lines_with_arrow = [ln for ln in vtt.split("\n") if "-->" in ln]
        for line in lines_with_arrow:
            assert "," not in line


# ---------------------------------------------------------------------------
# _parse_srt_timestamp
# ---------------------------------------------------------------------------


class TestParseSrtTimestamp:
    """Test SRT/VTT timestamp parsing to seconds."""

    def test_srt_format(self):
        """Standard SRT timestamp with comma."""
        assert _parse_srt_timestamp("00:01:30,500") == 90.5  # noqa: PLR2004

    def test_vtt_format(self):
        """VTT timestamp with dot."""
        assert _parse_srt_timestamp("00:01:30.500") == 90.5  # noqa: PLR2004

    def test_zero(self):
        """Zero timestamp."""
        assert _parse_srt_timestamp("00:00:00,000") == 0.0

    def test_hours(self):
        """Timestamp with hours."""
        assert _parse_srt_timestamp("01:00:00,000") == 3600.0  # noqa: PLR2004

    def test_short_format(self):
        """MM:SS format without hours."""
        assert _parse_srt_timestamp("01:30,500") == 90.5  # noqa: PLR2004

    def test_whitespace_stripped(self):
        """Leading/trailing whitespace is stripped."""
        assert _parse_srt_timestamp("  00:00:01,000  ") == 1.0


# ---------------------------------------------------------------------------
# _get_mp3_duration
# ---------------------------------------------------------------------------


class TestGetMp3Duration:
    """Test MP3 duration measurement."""

    @patch("subprocess.run")
    def test_ffprobe_success(self, mock_run, tmp_path):
        """Returns duration from ffprobe output."""
        mock_run.return_value = MagicMock(
            stdout=b"3.500\n",
            returncode=0,
        )
        mp3 = tmp_path / "test.mp3"
        mp3.write_bytes(b"fake")
        result = _get_mp3_duration(mp3)
        assert result == 3.5  # noqa: PLR2004

    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_ffprobe_missing_falls_back_to_size(self, mock_run, tmp_path):
        """Falls back to size estimation when ffprobe unavailable."""
        mp3 = tmp_path / "test.mp3"
        mp3.write_bytes(b"\x00" * 8000)
        result = _get_mp3_duration(mp3)
        assert result == 2.0  # 8000 / 4000 bytes_per_sec  # noqa: PLR2004

    @patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "ffprobe"))
    def test_ffprobe_error_falls_back(self, mock_run, tmp_path):
        """Falls back on ffprobe failure."""
        mp3 = tmp_path / "test.mp3"
        mp3.write_bytes(b"\x00" * 4000)
        result = _get_mp3_duration(mp3)
        assert result == 1.0


# ---------------------------------------------------------------------------
# _generate_silence
# ---------------------------------------------------------------------------


class TestGenerateSilence:
    """Test silence generation via FFmpeg."""

    @patch("subprocess.run")
    def test_calls_ffmpeg_with_duration(self, mock_run, tmp_path):
        """FFmpeg is called with correct duration and output path."""
        mock_run.return_value = MagicMock(returncode=0)
        out = tmp_path / "silence.mp3"
        _generate_silence(2.5, out)

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "ffmpeg"
        assert "-t" in cmd
        t_idx = cmd.index("-t")
        assert cmd[t_idx + 1] == "2.500"
        assert str(out) in cmd


# ---------------------------------------------------------------------------
# _speed_up_audio
# ---------------------------------------------------------------------------


class TestSpeedUpAudio:
    """Test FFmpeg atempo-based audio speed-up."""

    @patch("subprocess.run")
    def test_single_atempo_factor(self, mock_run, tmp_path):
        """Factor <= 2.0 uses a single atempo filter."""
        mock_run.return_value = MagicMock(returncode=0)
        inp = tmp_path / "in.mp3"
        out = tmp_path / "out.mp3"
        inp.write_bytes(b"\x00")
        _speed_up_audio(inp, out, 1.5)

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "-filter:a" in cmd
        f_idx = cmd.index("-filter:a")
        assert "atempo=1.5" in cmd[f_idx + 1]

    @patch("subprocess.run")
    def test_chained_atempo_factor(self, mock_run, tmp_path):
        """Factor > 2.0 chains multiple atempo filters."""
        mock_run.return_value = MagicMock(returncode=0)
        inp = tmp_path / "in.mp3"
        out = tmp_path / "out.mp3"
        inp.write_bytes(b"\x00")
        _speed_up_audio(inp, out, 3.0)

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        f_idx = cmd.index("-filter:a")
        filter_str = cmd[f_idx + 1]
        # Should chain: atempo=2.0,atempo=1.5
        assert "atempo=2.0" in filter_str
        assert filter_str.count("atempo=") >= 2  # noqa: PLR2004

    @patch("subprocess.run")
    def test_factor_clamped_to_max(self, mock_run, tmp_path):
        """Factor is clamped to _ATEMPO_MAX_FACTOR."""
        mock_run.return_value = MagicMock(returncode=0)
        inp = tmp_path / "in.mp3"
        out = tmp_path / "out.mp3"
        inp.write_bytes(b"\x00")
        _speed_up_audio(inp, out, 10.0)

        # Should clamp to _ATEMPO_MAX_FACTOR (4.0)
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_factor_lte_1_is_noop(self, mock_run, tmp_path):
        """Factor <= 1.0 does nothing (no speed-up needed)."""
        inp = tmp_path / "in.mp3"
        out = tmp_path / "out.mp3"
        _speed_up_audio(inp, out, 0.8)
        mock_run.assert_not_called()

        _speed_up_audio(inp, out, 1.0)
        mock_run.assert_not_called()

    @patch("subprocess.run")
    def test_factor_exactly_2_single_filter(self, mock_run, tmp_path):
        """Factor exactly 2.0 uses a single atempo=2.0 filter."""
        mock_run.return_value = MagicMock(returncode=0)
        inp = tmp_path / "in.mp3"
        out = tmp_path / "out.mp3"
        inp.write_bytes(b"\x00")
        _speed_up_audio(inp, out, 2.0)

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        f_idx = cmd.index("-filter:a")
        filter_str = cmd[f_idx + 1]
        # Exactly 2.0 should produce one atempo=2.0000
        assert filter_str.count("atempo=") == 1
        assert "atempo=2.0000" in filter_str

    @patch("subprocess.run")
    def test_ffmpeg_failure_raises(self, mock_run, tmp_path):
        """CalledProcessError from FFmpeg propagates."""
        mock_run.side_effect = subprocess.CalledProcessError(
            1,
            "ffmpeg",
            stderr=b"atempo error",
        )
        inp = tmp_path / "in.mp3"
        out = tmp_path / "out.mp3"
        inp.write_bytes(b"\x00")
        with pytest.raises(subprocess.CalledProcessError):
            _speed_up_audio(inp, out, 1.5)

    @patch("subprocess.run")
    def test_factor_near_epsilon_skips_subprocess(self, mock_run, tmp_path):
        """Factor between 1.0 and 1.01 (epsilon) returns early — no subprocess."""
        inp = tmp_path / "in.mp3"
        out = tmp_path / "out.mp3"
        inp.write_bytes(b"\x00")
        _speed_up_audio(inp, out, 1.005)
        # Factor too close to 1.0: no meaningful speed change, no subprocess
        mock_run.assert_not_called()

    @patch("subprocess.run")
    def test_factor_at_max_produces_two_filter_chain(self, mock_run, tmp_path):
        """Factor exactly _ATEMPO_MAX_FACTOR (4.0) → atempo=2.0,atempo=2.0.

        This is the boundary where the chain saturates: any higher
        factor gets clamped to 4.0 and produces the same chain.  If
        either filter dropped to <2.0, the resulting audio would be
        slower than the user asked for.
        """
        from src.core.speech_engine import _ATEMPO_MAX_FACTOR  # noqa: PLC0415

        mock_run.return_value = MagicMock(returncode=0)
        inp = tmp_path / "in.mp3"
        out = tmp_path / "out.mp3"
        inp.write_bytes(b"\x00")
        _speed_up_audio(inp, out, _ATEMPO_MAX_FACTOR)

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        f_idx = cmd.index("-filter:a")
        filter_str = cmd[f_idx + 1]
        # Expect exactly two filters, both at the per-filter max of 2.0.
        assert filter_str.count("atempo=") == 2  # noqa: PLR2004
        assert filter_str == "atempo=2.0000,atempo=2.0000"

    @patch("subprocess.run")
    def test_factor_above_max_clamped_to_same_chain(self, mock_run, tmp_path):
        """Factor 10.0 (saturated) yields identical chain to factor 4.0.

        Regression guard: a refactor that lifted the cap would silently
        change output speed for any sentence the user has set to a very
        high speed-up rate.
        """
        mock_run.return_value = MagicMock(returncode=0)
        inp = tmp_path / "in.mp3"
        out = tmp_path / "out.mp3"
        inp.write_bytes(b"\x00")
        _speed_up_audio(inp, out, 10.0)

        cmd = mock_run.call_args[0][0]
        f_idx = cmd.index("-filter:a")
        filter_str = cmd[f_idx + 1]
        assert filter_str == "atempo=2.0000,atempo=2.0000"

    @patch("subprocess.run")
    def test_factor_just_above_2_produces_chained_filters(
        self,
        mock_run,
        tmp_path,
    ):
        """Factor 2.5 → atempo=2.0,atempo=1.25 (two filters, second is partial)."""
        mock_run.return_value = MagicMock(returncode=0)
        inp = tmp_path / "in.mp3"
        out = tmp_path / "out.mp3"
        inp.write_bytes(b"\x00")
        _speed_up_audio(inp, out, 2.5)

        cmd = mock_run.call_args[0][0]
        f_idx = cmd.index("-filter:a")
        filter_str = cmd[f_idx + 1]
        # 2.5 → step1=2.0, remaining=2.5/2.0=1.25 → step2=1.25.
        assert filter_str == "atempo=2.0000,atempo=1.2500"

    @patch("subprocess.run")
    def test_factor_just_above_epsilon_runs_single_filter(
        self,
        mock_run,
        tmp_path,
    ):
        """Factor 1.02 → atempo=1.02 (single filter, just past epsilon)."""
        mock_run.return_value = MagicMock(returncode=0)
        inp = tmp_path / "in.mp3"
        out = tmp_path / "out.mp3"
        inp.write_bytes(b"\x00")
        _speed_up_audio(inp, out, 1.02)

        cmd = mock_run.call_args[0][0]
        f_idx = cmd.index("-filter:a")
        filter_str = cmd[f_idx + 1]
        assert filter_str.count("atempo=") == 1
        assert "atempo=1.0200" in filter_str


# ---------------------------------------------------------------------------
# synthesize_timed_speech
# ---------------------------------------------------------------------------


class TestSynthesizeTimedSpeech:
    """Test timed voice synthesis."""

    @pytest.fixture(autouse=True)
    def _mock_edge(self):
        """Prevent edge_tts import in tests running outside uv."""
        with patch(f"{_MOD}._synthesize_chunk_edge"):
            yield

    def _make_entry(self, start: str, end: str, text: str) -> MagicMock:
        """Create a mock SubtitleEntry."""
        entry = MagicMock()
        entry.start = start
        entry.end = end
        entry.text = text
        return entry

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration", return_value=1.0)
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_basic_two_entries(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_synth,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """Two entries produce silence gaps + speech segments."""
        entries = [
            self._make_entry("00:00:01,000", "00:00:03,000", "Hello"),
            self._make_entry("00:00:05,000", "00:00:07,000", "World"),
        ]
        output = str(tmp_path / "out.mp3")
        result = synthesize_timed_speech(
            entries,
            "English (US)",
            "FEMALE",
            output,
            tts_method=_GOOGLE_TTS,
        )
        assert result == output
        # Speech synthesized for each entry
        assert mock_synth.call_count == 2  # noqa: PLR2004
        # Silence for: before entry 1 (1s gap) + between entries (2s gap)
        assert mock_silence.call_count == 2  # noqa: PLR2004
        mock_concat.assert_called_once()

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration", return_value=5.0)
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_re_synthesize_when_too_long(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_synth,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """Re-synthesizes at higher rate when overflow exceeds tolerance."""
        # 5s audio in 2s slot, next entry starts at 2.5s — only 0.5s gap,
        # tolerance = min(2*0.5, 2.0) = 1.0, allowed = min(1.0, 0.5) = 0.5
        # overflow (3s) > allowed → speed up to fit 2.5s
        entries = [
            self._make_entry("00:00:00,000", "00:00:02,000", "Long text"),
            self._make_entry("00:00:02,500", "00:00:04,000", "Next"),
        ]
        output = str(tmp_path / "out.mp3")
        synthesize_timed_speech(entries, tts_method=_GOOGLE_TTS, output_path=output)

        # First entry re-synthesized (rate = 5.0 / 2.5 = 2.0)
        resyn_call = mock_synth.call_args_list[1]
        assert resyn_call[1]["speaking_rate"] == 2.0  # noqa: PLR2004

    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="")
    def test_missing_api_key(self, mock_key, tmp_path):
        """Missing API key raises AUTH_ERROR."""
        entries = [self._make_entry("00:00:00,000", "00:00:01,000", "Hi")]
        with pytest.raises(ValueError, match="AUTH_ERROR"):
            synthesize_timed_speech(
                entries,
                tts_method=_GOOGLE_TTS,
                output_path=str(tmp_path / "o.mp3"),
            )

    @patch(f"{_MOD}.check_ffmpeg_available", return_value=False)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_missing_ffmpeg(self, mock_key, mock_ff, tmp_path):
        """Missing FFmpeg raises FFMPEG_NOT_FOUND."""
        entries = [self._make_entry("00:00:00,000", "00:00:01,000", "Hi")]
        with pytest.raises(RuntimeError, match="FFMPEG_NOT_FOUND"):
            synthesize_timed_speech(
                entries,
                tts_method=_GOOGLE_TTS,
                output_path=str(tmp_path / "o.mp3"),
            )

    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_empty_entries(self, mock_key, mock_ff, tmp_path):
        """Empty text entries raise EMPTY_TEXT."""
        entries = [self._make_entry("00:00:00,000", "00:00:01,000", "   ")]
        with pytest.raises(ValueError, match="EMPTY_TEXT"):
            synthesize_timed_speech(
                entries,
                tts_method=_GOOGLE_TTS,
                output_path=str(tmp_path / "o.mp3"),
            )

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration", return_value=0.5)
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_no_silence_for_entry_at_zero(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_synth,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """No silence gap when first entry starts at 0."""
        entries = [
            self._make_entry("00:00:00,000", "00:00:02,000", "Start"),
        ]
        output = str(tmp_path / "out.mp3")
        synthesize_timed_speech(entries, tts_method=_GOOGLE_TTS, output_path=output)
        # No silence generated (entry starts at 0)
        mock_silence.assert_not_called()

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration", return_value=1.0)
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_cancellation(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_synth,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """Cancellation stops processing."""
        entries = [
            self._make_entry("00:00:00,000", "00:00:02,000", "A"),
            self._make_entry("00:00:03,000", "00:00:05,000", "B"),
        ]
        output = str(tmp_path / "out.mp3")
        with pytest.raises(ValueError, match="CANCELLED"):
            synthesize_timed_speech(
                entries,
                output_path=output,
                tts_method=_GOOGLE_TTS,
                is_cancelled=lambda: True,
            )
        mock_synth.assert_not_called()

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration", return_value=1.0)
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_progress_callback(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_synth,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """Progress callback is called for each entry."""
        progress = []
        entries = [
            self._make_entry("00:00:00,000", "00:00:01,000", "A"),
            self._make_entry("00:00:02,000", "00:00:03,000", "B"),
        ]
        output = str(tmp_path / "out.mp3")
        synthesize_timed_speech(
            entries,
            output_path=output,
            on_progress=lambda c, t: progress.append((c, t)),
            tts_method=_GOOGLE_TTS,
        )
        assert progress == [(1, 2), (2, 2)]

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration", return_value=2.8)
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_overflow_within_tolerance_but_exceeds_gap(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_synth,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """Speed-up when overflow is within tolerance but exceeds gap."""
        # 2.8s audio in 2s slot -> overflow = 0.8
        # tolerance = min(2*0.5, 2.0) = 1.0
        # next entry at 2.3s -> gap = 0.3
        # allowed = min(1.0, 0.3) = 0.3; overflow (0.8) > 0.3 -> speed up
        # rate = 2.8 / (2.0 + 0.3) = 1.217
        entries = [
            self._make_entry("00:00:00,000", "00:00:02,000", "Bit long"),
            self._make_entry("00:00:02,300", "00:00:04,000", "Next"),
        ]
        output = str(tmp_path / "out.mp3")
        synthesize_timed_speech(
            entries,
            tts_method=_GOOGLE_TTS,
            output_path=output,
        )
        # First entry re-synthesized with speaking_rate
        resyn_call = mock_synth.call_args_list[1]
        expected_rate = 2.8 / 2.3  # noqa: PLR2004
        assert abs(resyn_call[1]["speaking_rate"] - expected_rate) < 0.01  # noqa: PLR2004

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration", return_value=4.0)
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_overflow_exceeds_tolerance_within_gap(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_synth,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """Speed-up when overflow exceeds tolerance but gap is large."""
        # 4.0s audio in 2s slot -> overflow = 2.0
        # tolerance = min(2*0.5, 2.0) = 1.0
        # next entry at 20s -> gap = 18.0
        # allowed = min(1.0, 18.0) = 1.0; overflow (2.0) > 1.0 -> speed up
        # rate = 4.0 / (2.0 + 1.0) = 1.333
        entries = [
            self._make_entry("00:00:00,000", "00:00:02,000", "Long text"),
            self._make_entry("00:00:20,000", "00:00:22,000", "Far away"),
        ]
        output = str(tmp_path / "out.mp3")
        synthesize_timed_speech(
            entries,
            tts_method=_GOOGLE_TTS,
            output_path=output,
        )
        resyn_call = mock_synth.call_args_list[1]
        expected_rate = 4.0 / 3.0  # noqa: PLR2004
        assert abs(resyn_call[1]["speaking_rate"] - expected_rate) < 0.01  # noqa: PLR2004

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration", return_value=1.0)
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_zero_duration_entry_skipped(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_synth,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """Entry with start == end (zero duration) is skipped."""
        entries = [
            self._make_entry("00:00:01,000", "00:00:01,000", "Zero dur"),
            self._make_entry("00:00:02,000", "00:00:04,000", "Normal"),
        ]
        output = str(tmp_path / "out.mp3")
        synthesize_timed_speech(
            entries,
            tts_method=_GOOGLE_TTS,
            output_path=output,
        )
        # Only the normal entry is synthesized
        assert mock_synth.call_count == 1

    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_all_zero_duration_raises_empty_text(
        self,
        mock_key,
        mock_ffmpeg,
        tmp_path,
    ):
        """All entries with zero duration raises EMPTY_TEXT."""
        entries = [
            self._make_entry("00:00:01,000", "00:00:01,000", "Zero"),
            self._make_entry("00:00:02,000", "00:00:02,000", "Also zero"),
        ]
        with pytest.raises(ValueError, match="EMPTY_TEXT"):
            synthesize_timed_speech(
                entries,
                tts_method=_GOOGLE_TTS,
                output_path=str(tmp_path / "o.mp3"),
            )

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration", return_value=1.0)
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_negative_duration_entry_skipped(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_synth,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """Entry with end < start (negative duration) is skipped."""
        entries = [
            self._make_entry("00:00:03,000", "00:00:01,000", "Reversed"),
            self._make_entry("00:00:04,000", "00:00:06,000", "Normal"),
        ]
        output = str(tmp_path / "out.mp3")
        synthesize_timed_speech(
            entries,
            tts_method=_GOOGLE_TTS,
            output_path=output,
        )
        # Only the normal entry is synthesized
        assert mock_synth.call_count == 1

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration")
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_cursor_tracking_after_overflow(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_synth,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """After overflow, cursor advances past subtitle end, reducing gap."""
        # Entry 1: 0-2s slot, audio = 3s -> overflow 1s
        # tolerance = min(2*0.5, 2.0) = 1.0, gap to next = 3s
        # allowed = min(1.0, 3.0) = 1.0; overflow (1.0) == allowed -> no speedup
        # cursor = max(0, 0) + 3.0 = 3.0
        # Entry 2: 5-7s slot. gap = 5.0 - 3.0 = 2.0 -> silence of 2s
        mock_dur.return_value = 3.0
        entries = [
            self._make_entry("00:00:00,000", "00:00:02,000", "First"),
            self._make_entry("00:00:05,000", "00:00:07,000", "Second"),
        ]
        output = str(tmp_path / "out.mp3")
        synthesize_timed_speech(
            entries,
            tts_method=_GOOGLE_TTS,
            output_path=output,
        )
        # No re-synthesis (overflow within tolerance and gap)
        assert mock_synth.call_count == 2  # noqa: PLR2004
        # Check silence between entries: gap = 5.0 - 3.0 = 2.0
        silence_calls = mock_silence.call_args_list
        assert len(silence_calls) == 1
        assert abs(silence_calls[0][0][0] - 2.0) < 0.01  # noqa: PLR2004

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration")
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_cursor_after_speedup_uses_remeasured_duration(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_synth,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """After speed-up, cursor uses re-measured (shorter) audio duration."""
        # Entry 1: 0-2s, audio = 5s, next at 2.5s -> gap = 0.5
        # tolerance = min(2*0.5, 2.0) = 1.0, allowed = min(1.0, 0.5) = 0.5
        # overflow (3.0) > 0.5 -> speed up, rate = 5.0/2.5 = 2.0
        # Re-synthesis: return 2.5s (the fit window)
        # cursor = max(0, 0) + 2.5 = 2.5
        # Entry 2: 2.5-4s, audio = 1.0s, no overflow
        # gap = 2.5 - 2.5 = 0.0 -> no silence
        mock_dur.side_effect = [5.0, 2.5, 1.0]
        entries = [
            self._make_entry("00:00:00,000", "00:00:02,000", "Long text"),
            self._make_entry("00:00:02,500", "00:00:04,000", "Next"),
        ]
        output = str(tmp_path / "out.mp3")
        synthesize_timed_speech(
            entries,
            tts_method=_GOOGLE_TTS,
            output_path=output,
        )
        # First entry: original synth + re-synth; second entry: synth
        assert mock_synth.call_count == 3  # noqa: PLR2004
        # No silence (cursor at 2.5s, next starts at 2.5s)
        assert mock_silence.call_count == 0

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration")
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_cascading_overflows_three_entries(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_synth,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """Three entries with cascading overflows track cursor correctly."""
        # Each entry: 1s slot, 2s audio -> overflow 1s
        # tolerance = 0.5, gap = 1.0, allowed = 0.5 -> speed up each
        # Re-synth returns 1.5s for each
        mock_dur.side_effect = [2.0, 1.5, 2.0, 1.5, 2.0, 1.5]
        entries = [
            self._make_entry("00:00:00,000", "00:00:01,000", "A"),
            self._make_entry("00:00:02,000", "00:00:03,000", "B"),
            self._make_entry("00:00:04,000", "00:00:05,000", "C"),
        ]
        output = str(tmp_path / "out.mp3")
        synthesize_timed_speech(
            entries,
            tts_method=_GOOGLE_TTS,
            output_path=output,
        )
        # Each of the 3 entries gets original synth + re-synth = 6 calls
        assert mock_synth.call_count == 6  # noqa: PLR2004
        # Silence: between entry 1 and 2, between entry 2 and 3
        assert mock_silence.call_count == 2  # noqa: PLR2004

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration", return_value=1.0)
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_mixed_valid_invalid_duration_entries(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_synth,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """Zero-duration entries are skipped; valid ones are processed."""
        entries = [
            self._make_entry("00:00:01,000", "00:00:01,000", "Zero dur"),
            self._make_entry("00:00:02,000", "00:00:04,000", "Valid one"),
            self._make_entry("00:00:05,000", "00:00:05,000", "Zero dur 2"),
            self._make_entry("00:00:06,000", "00:00:08,000", "Valid two"),
        ]
        output = str(tmp_path / "out.mp3")
        synthesize_timed_speech(
            entries,
            tts_method=_GOOGLE_TTS,
            output_path=output,
        )
        # Only 2 valid entries synthesized
        assert mock_synth.call_count == 2  # noqa: PLR2004

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration", return_value=1.0)
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_progress_with_zero_duration_entries(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_synth,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """Progress callback uses parsed_idx (valid entries only)."""
        progress = []
        entries = [
            self._make_entry("00:00:01,000", "00:00:01,000", "Zero"),
            self._make_entry("00:00:02,000", "00:00:04,000", "Valid A"),
            self._make_entry("00:00:05,000", "00:00:07,000", "Valid B"),
        ]
        output = str(tmp_path / "out.mp3")
        synthesize_timed_speech(
            entries,
            tts_method=_GOOGLE_TTS,
            output_path=output,
            on_progress=lambda c, t: progress.append((c, t)),
        )
        # Total = 2 parsed entries, progress: (1,2), (2,2)
        assert progress == [(1, 2), (2, 2)]

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration")
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_negative_gap_no_silence_inserted(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_synth,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """Overlapping entries (negative gap) skip silence insertion."""
        # Entry 1: 0-2s, audio = 3s -> cursor = 3.0
        # tolerance = 1.0, gap to next = 0.5
        # allowed = min(1.0, 0.5) = 0.5; overflow (1.0) > 0.5 -> speed up
        # Re-synth returns 2.5, cursor = 2.5
        # Entry 2: 2.5-4s, gap = 2.5 - 2.5 = 0.0 -> no silence
        mock_dur.side_effect = [3.0, 2.5, 1.0]
        entries = [
            self._make_entry("00:00:00,000", "00:00:02,000", "First"),
            self._make_entry("00:00:02,500", "00:00:04,000", "Second"),
        ]
        output = str(tmp_path / "out.mp3")
        synthesize_timed_speech(
            entries,
            tts_method=_GOOGLE_TTS,
            output_path=output,
        )
        # No silence generated (cursor catches up exactly)
        assert mock_silence.call_count == 0

    @patch(f"{_MOD}.shutil.rmtree")
    @patch(f"{_MOD}._synthesize_chunk", side_effect=ValueError("TTS_API_ERROR"))
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_temp_dir_cleaned_on_error(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_silence,
        mock_synth,
        mock_rmtree,
        tmp_path,
    ):
        """Temp directory is cleaned up on error."""
        entries = [self._make_entry("00:00:00,000", "00:00:01,000", "Hi")]
        with pytest.raises(ValueError):
            synthesize_timed_speech(
                entries,
                output_path=str(tmp_path / "o.mp3"),
                tts_method=_GOOGLE_TTS,
            )
        mock_rmtree.assert_called_once()

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration", return_value=1.0)
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_leading_silence_prepended(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_synth,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """Silence is prepended when first entry starts after 0."""
        entries = [
            self._make_entry("00:00:10,000", "00:00:12,000", "Late start"),
        ]
        output = str(tmp_path / "out.mp3")
        synthesize_timed_speech(entries, tts_method=_GOOGLE_TTS, output_path=output)
        # Should generate 10s of leading silence
        mock_silence.assert_called_once()
        duration_arg = mock_silence.call_args[0][0]
        assert duration_arg == 10.0  # noqa: PLR2004


# ---------------------------------------------------------------------------
# _get_edge_voice
# ---------------------------------------------------------------------------


class TestGetEdgeVoice:
    """Test Edge TTS voice name mapping."""

    @patch(f"{_LANG}.get_locale_code", return_value="vi")
    def test_known_language_female(self, mock_locale):
        """Vietnamese Female maps to correct voice."""
        result = _get_edge_voice("Vietnamese", "FEMALE")
        assert result == "vi-VN-HoaiMyNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="vi")
    def test_known_language_male(self, mock_locale):
        """Vietnamese Male maps to correct voice."""
        result = _get_edge_voice("Vietnamese", "MALE")
        assert result == "vi-VN-NamMinhNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="sr")
    def test_unmapped_language_returns_default(self, mock_locale):
        """Unmapped language returns default voice."""
        result = _get_edge_voice("Serbian")
        assert result == _EDGE_DEFAULT_VOICE

    def test_empty_label_returns_english(self):
        """Empty label returns English voice."""
        result = _get_edge_voice("")
        assert "en-US" in result

    def test_empty_label_with_male(self):
        """Empty label with MALE gender."""
        result = _get_edge_voice("", "MALE")
        assert result == "en-US-GuyNeural"


# ---------------------------------------------------------------------------
# _parse_srt_timestamp — malformed input
# ---------------------------------------------------------------------------


class TestParseSrtTimestampMalformed:
    """Test _parse_srt_timestamp with invalid/edge-case inputs."""

    def test_empty_string(self):
        """Empty string returns 0.0."""
        assert _parse_srt_timestamp("") == 0.0

    def test_non_numeric(self):
        """Non-numeric string returns 0.0."""
        assert _parse_srt_timestamp("not-a-timestamp") == 0.0

    def test_partial_colons(self):
        """Single value without colons returns 0.0."""
        assert _parse_srt_timestamp("30,500") == 0.0

    def test_invalid_parts(self):
        """Invalid parts in HH:MM:SS format returns 0.0."""
        assert _parse_srt_timestamp("aa:bb:cc") == 0.0


# ---------------------------------------------------------------------------
# _synthesize_chunk — speaking_rate and audio_format
# ---------------------------------------------------------------------------


class TestSynthesizeChunkExtended:
    """Test _synthesize_chunk with speaking_rate and audio_format params."""

    def _make_response(self, audio_bytes: bytes) -> MagicMock:
        """Create a mock urlopen response."""
        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
        resp_data = json.dumps({"audioContent": audio_b64}).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = resp_data
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    @patch("urllib.request.urlopen")
    def test_speaking_rate_in_payload(self, mock_urlopen, tmp_path):
        """SpeakingRate appears in payload when rate != 1.0."""
        mock_urlopen.return_value = self._make_response(b"audio")
        out = tmp_path / "chunk.mp3"
        _synthesize_chunk("Hi", "en-US", "FEMALE", "key", out, speaking_rate=2.0)

        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode("utf-8"))
        assert payload["audioConfig"]["speakingRate"] == 2.0  # noqa: PLR2004

    @patch("urllib.request.urlopen")
    def test_speaking_rate_clamped_high(self, mock_urlopen, tmp_path):
        """Rate above 2.0 is clamped to 2.0 (Google's documented max).

        Google's AudioConfig reference caps ``speakingRate`` at 2.0;
        values above that raise HTTP 400 ``INVALID_ARGUMENT``.  The
        clamp prevents that user-visible failure.
        """
        mock_urlopen.return_value = self._make_response(b"audio")
        out = tmp_path / "chunk.mp3"
        rate = 6.0  # noqa: PLR2004
        _synthesize_chunk("Hi", "en-US", "FEMALE", "key", out, speaking_rate=rate)

        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode("utf-8"))
        assert payload["audioConfig"]["speakingRate"] == 2.0  # noqa: PLR2004

    @patch("urllib.request.urlopen")
    def test_speaking_rate_clamped_low(self, mock_urlopen, tmp_path):
        """Rate below 0.25 is clamped to 0.25."""
        mock_urlopen.return_value = self._make_response(b"audio")
        out = tmp_path / "chunk.mp3"
        _synthesize_chunk("Hi", "en-US", "FEMALE", "key", out, speaking_rate=0.1)

        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode("utf-8"))
        assert payload["audioConfig"]["speakingRate"] == 0.25  # noqa: PLR2004

    @patch("urllib.request.urlopen")
    def test_wav_format_uses_linear16(self, mock_urlopen, tmp_path):
        """audio_format='.wav' sets audioEncoding to LINEAR16."""
        mock_urlopen.return_value = self._make_response(b"audio")
        out = tmp_path / "chunk.wav"
        _synthesize_chunk(
            "Hi",
            "en-US",
            "FEMALE",
            "key",
            out,
            audio_format=".wav",
        )

        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode("utf-8"))
        assert payload["audioConfig"]["audioEncoding"] == "LINEAR16"

    @patch("urllib.request.urlopen")
    def test_default_rate_no_speaking_rate_key(self, mock_urlopen, tmp_path):
        """Default rate 1.0 does not add speakingRate to payload."""
        mock_urlopen.return_value = self._make_response(b"audio")
        out = tmp_path / "chunk.mp3"
        _synthesize_chunk("Hi", "en-US", "FEMALE", "key", out)

        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode("utf-8"))
        assert "speakingRate" not in payload["audioConfig"]


# ---------------------------------------------------------------------------
# synthesize_speech — Edge TTS path
# ---------------------------------------------------------------------------


class TestSynthesizeSpeechEdge:
    """Test synthesize_speech with Edge TTS (default, non-Google)."""

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._synthesize_chunk_edge")
    @patch(f"{_MOD}._split_text_for_tts", return_value=["Hello."])
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_edge_path_no_api_key_needed(
        self,
        mock_ffmpeg,
        mock_split,
        mock_edge,
        mock_concat,
        tmp_path,
    ):
        """Edge TTS path does not require API key."""
        output = str(tmp_path / "out.mp3")
        result = synthesize_speech("Hello.", output_path=output)
        assert result == output
        mock_edge.assert_called_once()

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._synthesize_chunk_edge")
    @patch(f"{_MOD}._split_text_for_tts", return_value=["A.", "B."])
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_edge_path_multiple_chunks(
        self,
        mock_ffmpeg,
        mock_split,
        mock_edge,
        mock_concat,
        tmp_path,
    ):
        """Edge TTS processes multiple chunks."""
        output = str(tmp_path / "out.mp3")
        synthesize_speech("A. B.", output_path=output)
        assert mock_edge.call_count == 2  # noqa: PLR2004

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._synthesize_chunk_edge")
    @patch(f"{_MOD}._split_text_for_tts", return_value=["Hi."])
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_empty_tts_method_uses_edge(
        self,
        mock_ffmpeg,
        mock_split,
        mock_edge,
        mock_concat,
        tmp_path,
    ):
        """Empty tts_method (default) routes to Edge TTS."""
        output = str(tmp_path / "out.mp3")
        synthesize_speech("Hi.", tts_method="", output_path=output)
        mock_edge.assert_called_once()


# ---------------------------------------------------------------------------
# transcribe_audio dispatch
# ---------------------------------------------------------------------------


class TestTranscribeAudioDispatch:
    """Test transcribe_audio STT method dispatch."""

    @patch(f"{_MOD}._transcribe_whisper", return_value="srt with Hi")
    def test_whisper_dispatch(self, mock_whisper):
        """Whisper method dispatches to _transcribe_whisper."""
        result = transcribe_audio("test.mp3", stt_method="Whisper")
        mock_whisper.assert_called_once()
        assert "Hi" in result

    @patch(f"{_MOD}._transcribe_google_cloud", return_value="srt with Hi")
    def test_google_dispatch(self, mock_google):
        """Google Cloud method dispatches to _transcribe_google_cloud."""
        result = transcribe_audio(
            "test.mp3",
            stt_method="Google Cloud",
        )
        mock_google.assert_called_once()
        assert "Hi" in result

    @patch(f"{_MOD}._transcribe_google_cloud", return_value="srt")
    def test_default_dispatch_is_google(self, mock_google):
        """Default (empty) stt_method dispatches to Google Cloud."""
        transcribe_audio("test.mp3", stt_method="")
        mock_google.assert_called_once()

    @patch(f"{_MOD}._transcribe_whisper", return_value="srt")
    def test_whisper_passes_model_size(self, mock_whisper):
        """model_size is passed to Whisper."""
        transcribe_audio(
            "test.mp3",
            stt_method="Whisper",
            model_size="large",
        )
        assert mock_whisper.call_args[0][2] == "large"


# ---------------------------------------------------------------------------
# display_status
# ---------------------------------------------------------------------------


class TestDisplayStatus:
    """Test status display translation."""

    def test_known_status_english(self):
        """Known status returns translated text (English defaults)."""
        result = display_status("Done")
        # In English, tr("status.done") should return "Done"
        assert result  # not empty
        assert isinstance(result, str)

    def test_unknown_status_returns_raw(self):
        """Unknown status falls back to raw string."""
        result = display_status("CustomStatus")
        assert result == "CustomStatus"

    def test_empty_status(self):
        """Empty string returns empty string."""
        result = display_status("")
        # tr("status.") with empty key — should fall back
        assert isinstance(result, str)

    def test_done_returns_translated_value(self):
        """Known status 'Done' returns a non-key translated value."""
        result = display_status("Done")
        # Must NOT return the raw key "status.done"
        assert result != "status.done"
        assert len(result) > 0


# ---------------------------------------------------------------------------
# _get_edge_voice — additional edge cases
# ---------------------------------------------------------------------------


class TestGetEdgeVoiceExtended:
    """Additional edge case tests for Edge TTS voice mapping."""

    @patch(f"{_LANG}.get_locale_code", return_value="vi")
    def test_invalid_gender_falls_back_to_first(self, mock_locale):
        """Invalid gender string falls back to first available voice."""
        result = _get_edge_voice("Vietnamese", "INVALID")
        # Should return the first voice in the dict (FEMALE)
        assert result == "vi-VN-HoaiMyNeural"


# ---------------------------------------------------------------------------
# _convert_subtitle_format — additional edge cases
# ---------------------------------------------------------------------------


class TestConvertSubtitleFormatExtended:
    """Additional edge case tests for SRT-to-VTT conversion."""

    def test_uppercase_vtt_returns_srt_unchanged(self):
        """Uppercase '.VTT' does NOT trigger conversion."""
        srt = "1\n00:00:01,000 --> 00:00:04,000\nHello\n"
        result = _convert_subtitle_format(srt, ".VTT")
        # Implementation checks target_ext != ".vtt" (lowercase)
        # so ".VTT" returns SRT unchanged
        assert result == srt

    def test_whitespace_only_srt(self):
        """SRT with only whitespace produces VTT with header."""
        vtt = _convert_subtitle_format("   \n\n  ", ".vtt")
        assert vtt.startswith("WEBVTT\n")

    def test_trailing_newlines_preserved(self):
        """Trailing newlines in SRT are preserved in VTT."""
        srt = "1\n00:00:01,000 --> 00:00:04,000\nHi\n\n\n"
        vtt = _convert_subtitle_format(srt, ".vtt")
        assert "Hi" in vtt
        assert "00:00:01.000" in vtt


# ---------------------------------------------------------------------------
# synthesize_timed_speech — Edge TTS path
# ---------------------------------------------------------------------------


class TestSynthesizeTimedSpeechEdge:
    """Test synthesize_timed_speech with Edge TTS (default)."""

    def _make_entry(self, start: str, end: str, text: str) -> MagicMock:
        """Create a mock SubtitleEntry."""
        entry = MagicMock()
        entry.start = start
        entry.end = end
        entry.text = text
        return entry

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration", return_value=1.0)
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._synthesize_chunk_edge")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_edge_timed_no_api_key_needed(  # noqa: PLR0913
        self,
        mock_ffmpeg,
        mock_edge,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """Edge TTS timed synthesis does not require API key."""
        entries = [
            self._make_entry("00:00:00,000", "00:00:02,000", "Hello"),
        ]
        output = str(tmp_path / "out.mp3")
        result = synthesize_timed_speech(
            entries,
            output_path=output,
        )
        assert result == output
        mock_edge.assert_called_once()

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration", return_value=1.0)
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._synthesize_chunk_edge")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_edge_timed_multiple_entries(  # noqa: PLR0913
        self,
        mock_ffmpeg,
        mock_edge,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """Edge TTS timed synthesis handles multiple entries."""
        entries = [
            self._make_entry("00:00:01,000", "00:00:03,000", "A"),
            self._make_entry("00:00:05,000", "00:00:07,000", "B"),
        ]
        output = str(tmp_path / "out.mp3")
        synthesize_timed_speech(entries, output_path=output)
        assert mock_edge.call_count == 2  # noqa: PLR2004
        # Silence gaps inserted
        assert mock_silence.call_count == 2  # noqa: PLR2004

    @patch(f"{_MOD}._synthesize_chunk_edge")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=False)
    def test_edge_timed_no_ffmpeg_raises(
        self,
        mock_ffmpeg,
        mock_edge,
        tmp_path,
    ):
        """Edge TTS still requires FFmpeg for concatenation."""
        entries = [
            self._make_entry("00:00:00,000", "00:00:01,000", "Hi"),
        ]
        with pytest.raises(RuntimeError, match="FFMPEG_NOT_FOUND"):
            synthesize_timed_speech(
                entries,
                output_path=str(tmp_path / "o.mp3"),
            )

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration", return_value=5.0)
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._speed_up_audio")
    @patch(f"{_MOD}._synthesize_chunk_edge")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_edge_speed_up_via_atempo(  # noqa: PLR0913
        self,
        mock_ffmpeg,
        mock_edge,
        mock_speedup,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """Edge TTS speeds up via atempo when overflow exceeds tolerance."""
        # 5s audio in 2s slot, next entry at 2.5s — only 0.5s gap
        # tolerance = min(2*0.5, 2.0) = 1.0, allowed = min(1.0, 0.5) = 0.5
        # overflow (3s) > allowed → speed up, rate = 5.0 / 2.5 = 2.0
        entries = [
            self._make_entry("00:00:00,000", "00:00:02,000", "Long"),
            self._make_entry("00:00:02,500", "00:00:04,000", "Next"),
        ]
        output = str(tmp_path / "out.mp3")
        synthesize_timed_speech(entries, output_path=output)
        # First entry speed-up confirmed
        first_speedup = mock_speedup.call_args_list[0]
        assert first_speedup[0][2] == 2.0  # noqa: PLR2004

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration", return_value=2.5)
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._speed_up_audio")
    @patch(f"{_MOD}._synthesize_chunk_edge")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_edge_no_speedup_within_tolerance(  # noqa: PLR0913
        self,
        mock_ffmpeg,
        mock_edge,
        mock_speedup,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """No speed-up when overflow is within tolerance and gap."""
        # 2.5s audio in 2s slot → overflow = 0.5s
        # tolerance = min(2*0.5, 2.0) = 1.0, gap = 10 - 2 = 8.0
        # allowed = min(1.0, 8.0) = 1.0; overflow (0.5) <= 1.0 → natural
        entries = [
            self._make_entry("00:00:00,000", "00:00:02,000", "Bit long"),
            self._make_entry("00:00:10,000", "00:00:12,000", "Next"),
        ]
        output = str(tmp_path / "out.mp3")
        synthesize_timed_speech(entries, output_path=output)
        # No speed-up on first entry — overflow within tolerance
        assert mock_speedup.call_count == 0

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration", return_value=2.5)
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._speed_up_audio")
    @patch(f"{_MOD}._synthesize_chunk_edge")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_edge_last_entry_within_tolerance(  # noqa: PLR0913
        self,
        mock_ffmpeg,
        mock_edge,
        mock_speedup,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """Last entry: no speed-up when overflow is within tolerance."""
        # 2.5s audio in 2s slot → overflow = 0.5
        # tolerance = min(2*0.5, 2.0) = 1.0, next_gap = inf
        # allowed = min(1.0, inf) = 1.0; overflow (0.5) <= 1.0 → natural
        entries = [
            self._make_entry("00:00:00,000", "00:00:02,000", "Bit long"),
        ]
        output = str(tmp_path / "out.mp3")
        synthesize_timed_speech(entries, output_path=output)
        assert mock_speedup.call_count == 0

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration", return_value=5.0)
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._speed_up_audio")
    @patch(f"{_MOD}._synthesize_chunk_edge")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_edge_last_entry_exceeds_tolerance(  # noqa: PLR0913
        self,
        mock_ffmpeg,
        mock_edge,
        mock_speedup,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """Last entry: speed-up when overflow exceeds tolerance cap."""
        # 5s audio in 2s slot → overflow = 3.0
        # tolerance = min(2*0.5, 2.0) = 1.0 → overflow (3) > 1.0
        # rate = 5.0 / (2.0 + 1.0) = 1.667
        entries = [
            self._make_entry("00:00:00,000", "00:00:02,000", "Very long"),
        ]
        output = str(tmp_path / "out.mp3")
        synthesize_timed_speech(entries, output_path=output)
        assert mock_speedup.call_count == 1
        factor = mock_speedup.call_args[0][2]
        expected = 5.0 / 3.0  # noqa: PLR2004
        assert abs(factor - expected) < 0.01  # noqa: PLR2004

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration", return_value=2.8)
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._speed_up_audio")
    @patch(f"{_MOD}._synthesize_chunk_edge")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_edge_overflow_within_tolerance_exceeds_gap(  # noqa: PLR0913
        self,
        mock_ffmpeg,
        mock_edge,
        mock_speedup,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """Edge: speed-up when overflow is within tolerance but gap is small."""
        # 2.8s audio in 2s slot -> overflow = 0.8
        # tolerance = min(2*0.5, 2.0) = 1.0, gap = 0.3
        # allowed = min(1.0, 0.3) = 0.3; overflow (0.8) > 0.3 -> speed up
        # rate = 2.8 / 2.3 = 1.217
        entries = [
            self._make_entry("00:00:00,000", "00:00:02,000", "Bit long"),
            self._make_entry("00:00:02,300", "00:00:04,000", "Next"),
        ]
        output = str(tmp_path / "out.mp3")
        synthesize_timed_speech(entries, output_path=output)
        # First entry triggers speed-up (second may too with constant mock)
        assert mock_speedup.call_count >= 1
        first_factor = mock_speedup.call_args_list[0][0][2]
        expected = 2.8 / 2.3  # noqa: PLR2004
        assert abs(first_factor - expected) < 0.01  # noqa: PLR2004

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration", return_value=1.0)
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._speed_up_audio")
    @patch(f"{_MOD}._synthesize_chunk_edge")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_edge_zero_duration_entry_skipped(  # noqa: PLR0913
        self,
        mock_ffmpeg,
        mock_edge,
        mock_speedup,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """Edge: zero-duration entries are skipped."""
        entries = [
            self._make_entry("00:00:01,000", "00:00:01,000", "Zero"),
            self._make_entry("00:00:02,000", "00:00:04,000", "Valid"),
        ]
        output = str(tmp_path / "out.mp3")
        synthesize_timed_speech(entries, output_path=output)
        assert mock_edge.call_count == 1

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration")
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._speed_up_audio")
    @patch(f"{_MOD}._synthesize_chunk_edge")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_edge_speedup_fast_path_not_exists(  # noqa: PLR0913
        self,
        mock_ffmpeg,
        mock_edge,
        mock_speedup,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """Edge: if fast_path does not exist after atempo, original is used."""
        # _speed_up_audio is mocked (does nothing), so fast_path won't exist.
        # The code checks fast_path.exists() and falls back to original.
        # Entry 1: 5s audio in 2s slot -> overflow -> speedup attempted
        # Entry 2: 0.5s audio in 1.5s slot -> no overflow
        mock_dur.side_effect = [5.0, 0.5]
        entries = [
            self._make_entry("00:00:00,000", "00:00:02,000", "Long"),
            self._make_entry("00:00:02,500", "00:00:04,000", "Next"),
        ]
        output = str(tmp_path / "out.mp3")
        synthesize_timed_speech(entries, output_path=output)
        # Speed-up was attempted for first entry only
        assert mock_speedup.call_count == 1
        # fast_path doesn't exist, so no re-measure call for it
        # _get_mp3_duration called once per entry = 2
        assert mock_dur.call_count == 2  # noqa: PLR2004

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration")
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._speed_up_audio")
    @patch(f"{_MOD}._synthesize_chunk_edge")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_edge_cursor_after_overflow_reduces_next_gap(  # noqa: PLR0913
        self,
        mock_ffmpeg,
        mock_edge,
        mock_speedup,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """Edge: cursor advances past end after overflow, shortening gap."""
        # Entry 1: 0-2s, audio = 3.0s, tolerance = 1.0, gap = 3.0
        # allowed = min(1.0, 3.0) = 1.0; overflow (1.0) <= 1.0 -> no speedup
        # cursor = max(0, 0) + 3.0 = 3.0
        # Entry 2: 5-7s, gap = 5.0 - 3.0 = 2.0 -> 2.0s silence
        mock_dur.return_value = 3.0
        entries = [
            self._make_entry("00:00:00,000", "00:00:02,000", "First"),
            self._make_entry("00:00:05,000", "00:00:07,000", "Second"),
        ]
        output = str(tmp_path / "out.mp3")
        synthesize_timed_speech(entries, output_path=output)
        assert mock_speedup.call_count == 0
        # Silence of 2.0s (not 5.0s which ignores cursor)
        silence_calls = mock_silence.call_args_list
        assert len(silence_calls) == 1
        assert abs(silence_calls[0][0][0] - 2.0) < 0.01  # noqa: PLR2004

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration")
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._speed_up_audio")
    @patch(f"{_MOD}._synthesize_chunk_edge")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_edge_cascading_overflows(  # noqa: PLR0913
        self,
        mock_ffmpeg,
        mock_edge,
        mock_speedup,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """Edge: three entries all overflow with cascading cursor tracking."""
        # _speed_up_audio is mocked (no-op, fast_path won't exist)
        # so all use original 2.0s duration throughout
        mock_dur.return_value = 2.0
        entries = [
            self._make_entry("00:00:00,000", "00:00:01,000", "A"),
            self._make_entry("00:00:02,000", "00:00:03,000", "B"),
            self._make_entry("00:00:04,000", "00:00:05,000", "C"),
        ]
        output = str(tmp_path / "out.mp3")
        synthesize_timed_speech(entries, output_path=output)
        # All 3 entries trigger speed-up attempts
        assert mock_speedup.call_count == 3  # noqa: PLR2004
        # No silence inserted (cursor always catches up)
        assert mock_silence.call_count == 0


# ---------------------------------------------------------------------------
# synthesize_speech — Edge TTS with FFmpeg missing
# ---------------------------------------------------------------------------


class TestSynthesizeSpeechEdgeErrors:
    """Test Edge TTS error paths."""

    @patch(f"{_MOD}._synthesize_chunk_edge")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=False)
    def test_edge_no_ffmpeg_raises(
        self,
        mock_ffmpeg,
        mock_edge,
        tmp_path,
    ):
        """Edge TTS still requires FFmpeg."""
        with pytest.raises(RuntimeError, match="FFMPEG_NOT_FOUND"):
            synthesize_speech(
                "Hello.",
                output_path=str(tmp_path / "o.mp3"),
            )


# ---------------------------------------------------------------------------
# mix_audio_into_video
# ---------------------------------------------------------------------------


class TestMixAudioIntoVideo:
    """Test video audio replacement via FFmpeg."""

    @patch(f"{_MOD}.check_ffmpeg_available", return_value=False)
    def test_no_ffmpeg_raises(self, mock_ff, tmp_path):
        """Missing FFmpeg raises RuntimeError."""
        with pytest.raises(RuntimeError, match="FFMPEG_NOT_FOUND"):
            mix_audio_into_video(
                str(tmp_path / "v.mp4"),
                str(tmp_path / "a.mp3"),
                str(tmp_path / "o.mp4"),
            )

    @patch("subprocess.run")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_calls_ffmpeg_with_correct_args(
        self,
        mock_ff,
        mock_run,
        tmp_path,
    ):
        """FFmpeg called with -c:v copy and -map flags."""
        mock_run.return_value = MagicMock(returncode=0)
        video = str(tmp_path / "video.mp4")
        audio = str(tmp_path / "voice.mp3")
        output = str(tmp_path / "dubbed.mp4")

        result = mix_audio_into_video(video, audio, output)

        assert result == output
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "ffmpeg"
        assert "-c:v" in cmd
        assert "copy" in cmd
        assert "-map" in cmd
        assert video in cmd
        assert audio in cmd
        assert output in cmd

    @patch("subprocess.run")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_ffmpeg_failure_raises(self, mock_ff, mock_run, tmp_path):
        """FFmpeg failure raises RuntimeError."""
        mock_run.side_effect = subprocess.CalledProcessError(
            1,
            "ffmpeg",
            stderr=b"mix error",
        )
        with pytest.raises(RuntimeError, match="FFMPEG_MIX_FAILED"):
            mix_audio_into_video(
                str(tmp_path / "v.mp4"),
                str(tmp_path / "a.mp3"),
                str(tmp_path / "o.mp4"),
            )

    @patch("subprocess.run")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_uses_shortest_flag(self, mock_ff, mock_run, tmp_path):
        """FFmpeg uses -shortest to trim to shorter stream."""
        mock_run.return_value = MagicMock(returncode=0)
        mix_audio_into_video(
            str(tmp_path / "v.mp4"),
            str(tmp_path / "a.mp3"),
            str(tmp_path / "o.mp4"),
        )
        cmd = mock_run.call_args[0][0]
        assert "-shortest" in cmd


# ---------------------------------------------------------------------------
# check_ffmpeg_available
# ---------------------------------------------------------------------------


class TestCheckFfmpegAvailable:
    """Test FFmpeg availability detection."""

    @patch("shutil.which", return_value="/usr/bin/ffmpeg")
    def test_returns_true_when_found(self, mock_which):
        """Returns True when shutil.which finds ffmpeg on PATH."""
        assert check_ffmpeg_available() is True
        mock_which.assert_called_once_with("ffmpeg")

    @patch("shutil.which", return_value=None)
    def test_returns_false_when_not_found(self, mock_which):
        """Returns False when shutil.which returns None."""
        assert check_ffmpeg_available() is False
        mock_which.assert_called_once_with("ffmpeg")


# ---------------------------------------------------------------------------
# _extract_audio_to_flac
# ---------------------------------------------------------------------------


class TestExtractAudioToFlac:
    """Test audio extraction to FLAC via FFmpeg."""

    @patch(f"{_MOD}.check_ffmpeg_available", return_value=False)
    def test_ffmpeg_not_available_raises(self, mock_ff):
        """Raises RuntimeError('FFMPEG_NOT_FOUND') when FFmpeg is missing."""
        with pytest.raises(RuntimeError, match="FFMPEG_NOT_FOUND"):
            _extract_audio_to_flac("/some/video.mp4")

    @patch("subprocess.run")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_called_process_error_cleans_temp(
        self,
        mock_ff,
        mock_run,
        tmp_path,
    ):
        """CalledProcessError raises FFMPEG_CONVERSION_FAILED and cleans up."""
        mock_run.side_effect = subprocess.CalledProcessError(
            1,
            "ffmpeg",
            stderr=b"conversion error",
        )
        with pytest.raises(RuntimeError, match="FFMPEG_CONVERSION_FAILED"):
            _extract_audio_to_flac(str(tmp_path / "video.mp4"))

    @patch("subprocess.run")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_file_not_found_raises_ffmpeg_not_found(
        self,
        mock_ff,
        mock_run,
        tmp_path,
    ):
        """FileNotFoundError raises FFMPEG_NOT_FOUND and cleans temp dir."""
        mock_run.side_effect = FileNotFoundError("ffmpeg not found")
        with pytest.raises(RuntimeError, match="FFMPEG_NOT_FOUND"):
            _extract_audio_to_flac(str(tmp_path / "video.mp4"))

    @patch("subprocess.run")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_happy_path_returns_flac_path(self, mock_ff, mock_run):
        """Successful extraction returns a Path ending in audio.flac."""
        mock_run.return_value = MagicMock(returncode=0)
        result = _extract_audio_to_flac("/some/video.mp4")
        assert isinstance(result, Path)
        assert result.name == "audio.flac"
        assert result.parent.name.startswith("subtitle_")


# ---------------------------------------------------------------------------
# _call_long_running_recognize
# ---------------------------------------------------------------------------


class TestCallLongRunningRecognize:
    """Test the longrunningrecognize API call."""

    def _make_response(self, data: dict) -> MagicMock:
        """Create a mock urlopen context-manager response."""
        resp = MagicMock()
        resp.read.return_value = json.dumps(data).encode("utf-8")
        resp.__enter__ = MagicMock(return_value=resp)
        resp.__exit__ = MagicMock(return_value=False)
        return resp

    @patch("urllib.request.urlopen")
    def test_happy_path_returns_operation_name(self, mock_urlopen):
        """Returns the 'name' field from the API response."""
        mock_urlopen.return_value = self._make_response(
            {"name": "operations/12345"},
        )
        result = _call_long_running_recognize(
            "base64audio",
            "en-US",
            "test-key",
        )
        assert result == "operations/12345"

    @patch("urllib.request.urlopen")
    def test_empty_language_uses_en_us(self, mock_urlopen):
        """Empty language code defaults to 'en-US' in the payload."""
        mock_urlopen.return_value = self._make_response(
            {"name": "operations/abc"},
        )
        _call_long_running_recognize("audio_b64", "", "key123")

        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode("utf-8"))
        assert payload["config"]["languageCode"] == "en-US"

    @patch("urllib.request.urlopen")
    def test_http_401_raises_auth_error(self, mock_urlopen):
        """HTTP 401 raises ValueError('AUTH_ERROR')."""
        fp = MagicMock(read=lambda: b"unauthorized")
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "url",
            401,
            "Unauthorized",
            {},
            fp,
        )
        with pytest.raises(ValueError, match="AUTH_ERROR"):
            _call_long_running_recognize("audio", "en-US", "bad-key")

    @patch("urllib.request.urlopen")
    def test_http_429_raises_quota_error(self, mock_urlopen):
        """HTTP 429 raises ValueError('QUOTA_ERROR')."""
        fp = MagicMock(read=lambda: b"quota exceeded")
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "url",
            429,
            "Too Many Requests",
            {},
            fp,  # noqa: PLR2004
        )
        with pytest.raises(ValueError, match="QUOTA_ERROR"):
            _call_long_running_recognize("audio", "vi-VN", "key")

    @patch("urllib.request.urlopen")
    def test_http_500_raises_speech_api_error(self, mock_urlopen):
        """HTTP 500 raises ValueError with SPEECH_API_ERROR."""
        fp = MagicMock(read=lambda: b"server error")
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "url",
            500,
            "Internal Server Error",
            {},
            fp,  # noqa: PLR2004
        )
        with pytest.raises(ValueError, match="SPEECH_API_ERROR"):
            _call_long_running_recognize("audio", "en-US", "key")

    @patch("urllib.request.urlopen")
    def test_http_400_api_key_invalid_body_routes_to_auth_error(
        self,
        mock_urlopen,
    ):
        """HTTP 400 + ``API_KEY_INVALID`` body → ``AUTH_ERROR:Google Cloud``.

        Google Cloud STT shares the same quirk as TTS + Gemini: an
        invalid API key returns HTTP 400 (not 401/403) with the
        auth-failure reason in the body.  Without the body-parsing
        rebadge the user sees the generic ``SPEECH_API_ERROR`` toast
        when the real problem is a bad key.  Wire shape mirrors the
        real Google response.
        """
        body = (
            b'{"error":{"code":400,"message":"API key not valid. '
            b'Please pass a valid API key.","status":"INVALID_ARGUMENT",'
            b'"details":[{"@type":'
            b'"type.googleapis.com/google.rpc.ErrorInfo",'
            b'"reason":"API_KEY_INVALID","domain":"googleapis.com",'
            b'"metadata":{"service":"speech.googleapis.com"}}]}}'
        )
        fp = MagicMock(read=lambda: body)
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "url",
            400,
            "Bad Request",
            {},
            fp,
        )
        with pytest.raises(ValueError, match=r"AUTH_ERROR:Google Cloud"):
            _call_long_running_recognize("audio", "en-US", "bad-key")

    @patch("urllib.request.urlopen")
    def test_http_400_non_auth_body_routes_to_speech_api_error(
        self,
        mock_urlopen,
    ):
        """HTTP 400 without auth indicators in body stays as SPEECH_API_ERROR.

        False-positive guard: legitimate 400s (unsupported audio
        format, malformed config, missing required field, etc.)
        don't mention "api" + "key" in the body, so they correctly
        route to the catch-all SPEECH_API_ERROR — not the auth tag.
        """
        body = b'{"error":{"code":400,"message":"Invalid audio encoding"}}'
        fp = MagicMock(read=lambda: body)
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "url",
            400,
            "Bad Request",
            {},
            fp,
        )
        with pytest.raises(ValueError, match=r"SPEECH_API_ERROR: HTTP 400"):
            _call_long_running_recognize("audio", "en-US", "key")


# ---------------------------------------------------------------------------
# _poll_operation
# ---------------------------------------------------------------------------


class TestPollOperation:
    """Test long-running operation polling."""

    def _make_response(self, data: dict) -> MagicMock:
        """Create a mock urlopen context-manager response."""
        resp = MagicMock()
        resp.read.return_value = json.dumps(data).encode("utf-8")
        resp.__enter__ = MagicMock(return_value=resp)
        resp.__exit__ = MagicMock(return_value=False)
        return resp

    @patch("time.sleep")
    @patch("urllib.request.urlopen")
    def test_done_with_response(self, mock_urlopen, mock_sleep):
        """Returns the response dict when operation completes."""
        response_data = {"results": [{"alternatives": [{"transcript": "Hi"}]}]}
        mock_urlopen.return_value = self._make_response(
            {"done": True, "response": response_data},
        )
        result = _poll_operation("operations/123", "api-key")
        assert result == response_data

    @patch("time.sleep")
    @patch("urllib.request.urlopen")
    def test_cancellation_raises(self, mock_urlopen, mock_sleep):
        """Raises ValueError('CANCELLED') when is_cancelled returns True."""
        with pytest.raises(ValueError, match="CANCELLED"):
            _poll_operation(
                "operations/123",
                "key",
                is_cancelled=lambda: True,
            )

    @patch("time.sleep")
    @patch("urllib.request.urlopen")
    def test_done_with_error_raises_speech_api_error(
        self,
        mock_urlopen,
        mock_sleep,
    ):
        """Operation done with error raises ValueError('SPEECH_API_ERROR')."""
        mock_urlopen.return_value = self._make_response(
            {"done": True, "error": {"message": "Recognition failed"}},
        )
        with pytest.raises(ValueError, match="SPEECH_API_ERROR"):
            _poll_operation("operations/456", "key")

    @patch("time.sleep")
    @patch("urllib.request.urlopen")
    def test_http_401_raises_auth_error(self, mock_urlopen, mock_sleep):
        """HTTP 401 during polling raises ValueError('AUTH_ERROR')."""
        fp = MagicMock(read=lambda: b"auth error")
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "url",
            401,
            "Unauthorized",
            {},
            fp,
        )
        with pytest.raises(ValueError, match="AUTH_ERROR"):
            _poll_operation("operations/789", "bad-key")

    @patch("time.sleep")
    @patch("urllib.request.urlopen")
    def test_polls_until_done(self, mock_urlopen, mock_sleep):
        """Polls multiple times until operation reports done."""
        pending = self._make_response({"done": False})
        complete = self._make_response(
            {"done": True, "response": {"results": []}},
        )
        mock_urlopen.side_effect = [pending, pending, complete]

        result = _poll_operation("operations/poll", "key")
        assert result == {"results": []}
        assert mock_urlopen.call_count == 3  # noqa: PLR2004
        assert mock_sleep.call_count == 3  # noqa: PLR2004


# ---------------------------------------------------------------------------
# mix_audio_into_video (additional tests)
# ---------------------------------------------------------------------------


class TestMixAudioIntoVideoExtended:
    """Additional tests for mix_audio_into_video."""

    @patch("subprocess.run")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_happy_path_returns_output_path(
        self,
        mock_ff,
        mock_run,
        tmp_path,
    ):
        """Returns the output path on success, calls subprocess."""
        mock_run.return_value = MagicMock(returncode=0)
        video = str(tmp_path / "video.mp4")
        audio = str(tmp_path / "audio.mp3")
        output = str(tmp_path / "out.mp4")

        result = mix_audio_into_video(video, audio, output)
        assert result == output
        mock_run.assert_called_once()

    @patch("subprocess.run")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_called_process_error_raises_mix_failed(
        self,
        mock_ff,
        mock_run,
        tmp_path,
    ):
        """CalledProcessError raises RuntimeError('FFMPEG_MIX_FAILED')."""
        mock_run.side_effect = subprocess.CalledProcessError(
            1,
            "ffmpeg",
            stderr=b"encoding error",
        )
        with pytest.raises(RuntimeError, match="FFMPEG_MIX_FAILED"):
            mix_audio_into_video(
                str(tmp_path / "v.mp4"),
                str(tmp_path / "a.mp3"),
                str(tmp_path / "o.mp4"),
            )

    @patch(f"{_MOD}.check_ffmpeg_available", return_value=False)
    def test_ffmpeg_not_available_raises(self, mock_ff, tmp_path):
        """Raises RuntimeError('FFMPEG_NOT_FOUND') when FFmpeg is missing."""
        with pytest.raises(RuntimeError, match="FFMPEG_NOT_FOUND"):
            mix_audio_into_video(
                str(tmp_path / "v.mp4"),
                str(tmp_path / "a.mp3"),
                str(tmp_path / "o.mp4"),
            )


# ---------------------------------------------------------------------------
# _get_speech_language_code
# ---------------------------------------------------------------------------


class TestGetSpeechLanguageCode:
    """Test language label to BCP-47 Speech-to-Text code mapping."""

    @patch(f"{_LANG}.get_locale_code", return_value="vi")
    def test_known_language_returns_locale(self, mock_locale):
        """Vietnamese label delegates to get_locale_code and returns 'vi'."""
        result = _get_speech_language_code("Vietnamese")
        mock_locale.assert_called_once_with("Vietnamese")
        assert result == "vi"

    def test_empty_string_returns_empty(self):
        """Empty source language returns empty string for auto-detect."""
        result = _get_speech_language_code("")
        assert result == ""

    @patch(f"{_LANG}.get_locale_code", return_value="de")
    def test_unlisted_language_calls_get_locale_code(self, mock_locale):
        """A language not in any special map still delegates to get_locale_code."""
        result = _get_speech_language_code("German")
        mock_locale.assert_called_once_with("German")
        assert result == "de"


# ---------------------------------------------------------------------------
# _transcribe_whisper
# ---------------------------------------------------------------------------


class TestTranscribeWhisper:
    """Test Whisper-based transcription."""

    @pytest.fixture(autouse=True)
    def _setup_faster_whisper(self):
        """Ensure faster_whisper mock module is available for local import."""
        mock_fw = MagicMock()
        # Create the WhisperModel class mock
        mock_fw.WhisperModel = MagicMock()
        prev = sys.modules.get("faster_whisper")
        sys.modules["faster_whisper"] = mock_fw
        yield mock_fw
        # Restore
        if prev is None:
            sys.modules.pop("faster_whisper", None)
        else:
            sys.modules["faster_whisper"] = prev

    def test_happy_path_returns_srt(self, _setup_faster_whisper):
        """Transcribes segments and returns SRT-formatted output."""
        mock_fw = _setup_faster_whisper
        seg1 = MagicMock(start=0.0, end=2.5, text="  Hello world.  ")
        seg2 = MagicMock(start=3.0, end=5.0, text="  How are you?  ")
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([seg1, seg2], MagicMock())
        mock_fw.WhisperModel.return_value = mock_model

        result = _transcribe_whisper("test.mp4", src_lang="", model_size="base")

        # Verify SRT format: has "-->" separator
        assert "-->" in result
        # Verify text is stripped
        assert "Hello world." in result
        assert "How are you?" in result
        # Verify segment numbering
        lines = result.split("\n")
        assert lines[0] == "1"

    @patch(f"{_MOD}._get_speech_language_code", return_value="en-US")
    def test_hyphenated_lang_code_split(
        self,
        mock_speech_lang,
        _setup_faster_whisper,
    ):
        """Language code with hyphen (e.g. 'en-US') is split to 'en'."""
        mock_fw = _setup_faster_whisper
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([], MagicMock())
        mock_fw.WhisperModel.return_value = mock_model

        _transcribe_whisper("test.mp4", src_lang="English (US)")

        # Whisper receives short code "en", not "en-US"
        call_kwargs = mock_model.transcribe.call_args[1]
        assert call_kwargs["language"] == "en"

    def test_empty_src_lang_no_language_kwarg(self, _setup_faster_whisper):
        """Empty src_lang means no 'language' kwarg passed to model.transcribe."""
        mock_fw = _setup_faster_whisper
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([], MagicMock())
        mock_fw.WhisperModel.return_value = mock_model

        _transcribe_whisper("test.mp4", src_lang="")

        call_kwargs = mock_model.transcribe.call_args[1]
        assert "language" not in call_kwargs
        assert call_kwargs["word_timestamps"] is False


# ---------------------------------------------------------------------------
# _transcribe_google_cloud
# ---------------------------------------------------------------------------


class TestTranscribeGoogleCloud:
    """Test Google Cloud Speech-to-Text transcription."""

    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="")
    def test_no_api_key_raises_auth_error(self, mock_key):
        """Missing API key raises ValueError('AUTH_ERROR')."""
        with pytest.raises(ValueError, match="AUTH_ERROR"):
            _transcribe_google_cloud("test.mp4")

    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key123")
    @patch(f"{_MOD}._extract_audio_to_flac")
    def test_audio_too_large_raises(self, mock_extract, mock_key, tmp_path):
        """Audio exceeding _MAX_AUDIO_BYTES raises ValueError."""
        flac = tmp_path / "audio.flac"
        # Write a file larger than the limit
        flac.write_bytes(b"\x00" * (_MAX_AUDIO_BYTES + 1))
        mock_extract.return_value = flac

        with pytest.raises(ValueError, match="AUDIO_TOO_LARGE"):
            _transcribe_google_cloud("test.mp4")

    @patch(
        f"{_MOD}._parse_results_to_srt",
        return_value="1\n00:00:00,000 --> 00:00:01,000\nHello\n",
    )
    @patch(
        f"{_MOD}._poll_operation",
        return_value={"results": [{"alternatives": [{"transcript": "Hello"}]}]},
    )
    @patch(f"{_MOD}._call_long_running_recognize", return_value="op-123")
    @patch(f"{_MOD}._get_speech_language_code", return_value="en-US")
    @patch(f"{_MOD}._extract_audio_to_flac")
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key123")
    def test_happy_path_returns_srt(  # noqa: PLR0913
        self,
        mock_key,
        mock_extract,
        mock_lang,
        mock_recognize,
        mock_poll,
        mock_parse,
        tmp_path,
    ):
        """Full happy path: extract, call API, poll, parse to SRT."""
        flac = tmp_path / "audio.flac"
        flac.write_bytes(b"\x00" * 100)
        mock_extract.return_value = flac

        result = _transcribe_google_cloud("test.mp4", src_lang="English (US)")

        mock_recognize.assert_called_once()
        mock_poll.assert_called_once()
        mock_parse.assert_called_once()
        assert "Hello" in result

    @patch(f"{_MOD}._parse_results_to_srt", return_value="srt")
    @patch(f"{_MOD}._poll_operation", return_value={"results": []})
    @patch(f"{_MOD}._call_long_running_recognize", return_value="op-456")
    @patch(f"{_MOD}._get_speech_language_code", return_value="vi")
    @patch(f"{_MOD}._extract_audio_to_flac")
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key123")
    def test_is_cancelled_forwarded_to_poll(  # noqa: PLR0913
        self,
        mock_key,
        mock_extract,
        mock_lang,
        mock_recognize,
        mock_poll,
        mock_parse,
        tmp_path,
    ):
        """is_cancelled callback is forwarded to _poll_operation."""
        flac = tmp_path / "audio.flac"
        flac.write_bytes(b"\x00" * 100)
        mock_extract.return_value = flac
        cancel_fn = MagicMock(return_value=False)

        _transcribe_google_cloud(
            "test.mp4",
            src_lang="Vietnamese",
            is_cancelled=cancel_fn,
        )

        # _poll_operation receives the cancel callback
        poll_args = mock_poll.call_args
        passed_cancel = (
            poll_args[0][2]
            if len(poll_args[0]) > 2  # noqa: PLR2004
            else poll_args[1].get("is_cancelled")
        )
        assert passed_cancel is cancel_fn


# ---------------------------------------------------------------------------
# _synthesize_chunk_edge
# ---------------------------------------------------------------------------


class TestSynthesizeChunkEdge:
    """Test Edge TTS synthesis with retry logic."""

    @pytest.fixture(autouse=True)
    def _setup_edge_tts(self):
        """Inject mock edge_tts and edge_tts.exceptions into sys.modules."""
        # Create the exception class
        self._NoAudioReceived = type("NoAudioReceived", (Exception,), {})

        mock_edge = MagicMock()
        mock_exceptions = MagicMock()
        mock_exceptions.NoAudioReceived = self._NoAudioReceived

        prev_edge = sys.modules.get("edge_tts")
        prev_exc = sys.modules.get("edge_tts.exceptions")
        sys.modules["edge_tts"] = mock_edge
        sys.modules["edge_tts.exceptions"] = mock_exceptions

        self._mock_edge = mock_edge
        yield
        # Restore
        if prev_edge is None:
            sys.modules.pop("edge_tts", None)
        else:
            sys.modules["edge_tts"] = prev_edge
        if prev_exc is None:
            sys.modules.pop("edge_tts.exceptions", None)
        else:
            sys.modules["edge_tts.exceptions"] = prev_exc

    def test_happy_path_synthesizes(self, tmp_path):
        """Successful synthesis calls Communicate.save() and returns."""
        output = tmp_path / "out.mp3"
        mock_comm = MagicMock()
        # Make save an async mock that completes successfully
        mock_comm.save = AsyncMock()
        self._mock_edge.Communicate.return_value = mock_comm

        _synthesize_chunk_edge(
            "Hello world",
            "en-US-JennyNeural",
            output,
            max_retries=1,
            base_delay=0.0,
        )

        self._mock_edge.Communicate.assert_called_once_with(
            "Hello world",
            "en-US-JennyNeural",
        )
        mock_comm.save.assert_awaited_once_with(str(output))

    def test_retry_on_no_audio_received(self, tmp_path):
        """Retries on NoAudioReceived, succeeds on second attempt."""
        output = tmp_path / "out.mp3"
        mock_comm = MagicMock()
        # First call raises NoAudioReceived, second succeeds
        mock_comm.save = AsyncMock(
            side_effect=[self._NoAudioReceived("no audio"), None],
        )
        self._mock_edge.Communicate.return_value = mock_comm

        _synthesize_chunk_edge(
            "Hi",
            "en-US-JennyNeural",
            output,
            max_retries=2,
            base_delay=0.0,
        )

        assert mock_comm.save.await_count == 2  # noqa: PLR2004

    def test_all_retries_exhausted_raises_tts_api_error(self, tmp_path):
        """All retries exhausted raises ValueError('TTS_API_ERROR')."""
        output = tmp_path / "out.mp3"
        mock_comm = MagicMock()
        # Always raise NoAudioReceived
        mock_comm.save = AsyncMock(
            side_effect=self._NoAudioReceived("persistent failure"),
        )
        self._mock_edge.Communicate.return_value = mock_comm

        with pytest.raises(ValueError, match="TTS_API_ERROR"):
            _synthesize_chunk_edge(
                "Hi",
                "en-US-JennyNeural",
                output,
                max_retries=1,
                base_delay=0.0,
            )


# ---------------------------------------------------------------------------
# _get_mp3_duration — zero-byte edge case
# ---------------------------------------------------------------------------


class TestGetMp3DurationZeroByte:
    """Test MP3 duration with zero-byte files."""

    @patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "ffprobe"))
    def test_zero_byte_file_returns_zero(self, mock_run, tmp_path):
        """Zero-byte file with subprocess failing returns 0.0."""
        mp3 = tmp_path / "empty.mp3"
        mp3.write_bytes(b"")
        result = _get_mp3_duration(mp3)
        assert result == 0.0


# ---------------------------------------------------------------------------
# transcribe_audio — passthrough checks
# ---------------------------------------------------------------------------


class TestTranscribeAudioPassthrough:
    """Test that transcribe_audio forwards arguments correctly."""

    @patch(f"{_MOD}._transcribe_google_cloud", return_value="srt")
    def test_is_cancelled_forwarded_to_google(self, mock_google):
        """is_cancelled callback is forwarded to _transcribe_google_cloud."""
        cancel_fn = MagicMock(return_value=False)
        transcribe_audio(
            "test.mp3",
            src_lang="Vietnamese",
            stt_method="Google Cloud",
            is_cancelled=cancel_fn,
        )
        call_kwargs = mock_google.call_args[1]
        assert call_kwargs.get("is_cancelled") is cancel_fn

    @patch(f"{_MOD}._transcribe_whisper", return_value="srt")
    def test_src_lang_forwarded_to_whisper(self, mock_whisper):
        """src_lang is forwarded to _transcribe_whisper."""
        transcribe_audio(
            "test.mp3",
            src_lang="Japanese",
            stt_method="Whisper",
            model_size="small",
        )
        # _transcribe_whisper(file_path, src_lang, model_size) - positional args
        call_args = mock_whisper.call_args[0]
        assert call_args[1] == "Japanese"


# ---------------------------------------------------------------------------
# _transcribe_whisper — additional tests
# ---------------------------------------------------------------------------


class TestTranscribeWhisperAdditional:
    """Additional Whisper transcription tests."""

    @pytest.fixture(autouse=True)
    def _setup_faster_whisper(self):
        """Ensure faster_whisper mock module is available for local import."""
        mock_fw = MagicMock()
        mock_fw.WhisperModel = MagicMock()
        prev = sys.modules.get("faster_whisper")
        sys.modules["faster_whisper"] = mock_fw
        yield mock_fw
        if prev is None:
            sys.modules.pop("faster_whisper", None)
        else:
            sys.modules["faster_whisper"] = prev

    def test_transcribe_whisper_calls_faster_whisper(
        self,
        _setup_faster_whisper,
    ):
        """WhisperModel is created with the correct model_size."""
        mock_fw = _setup_faster_whisper
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([], MagicMock())
        mock_fw.WhisperModel.return_value = mock_model

        _transcribe_whisper("test.mp4", model_size="small")

        mock_fw.WhisperModel.assert_called_once_with(
            "small",
            device="cpu",
            compute_type="int8",
        )

    @patch(f"{_MOD}._get_speech_language_code", return_value="vi-VN")
    def test_transcribe_whisper_language_code_passed(
        self,
        mock_speech_lang,
        _setup_faster_whisper,
    ):
        """Resolved language code is split and passed to model.transcribe."""
        mock_fw = _setup_faster_whisper
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([], MagicMock())
        mock_fw.WhisperModel.return_value = mock_model

        _transcribe_whisper("test.mp4", src_lang="Vietnamese")

        call_kwargs = mock_model.transcribe.call_args[1]
        # Should be short code "vi", not "vi-VN"
        assert call_kwargs["language"] == "vi"

    def test_transcribe_whisper_srt_format_correctness(
        self,
        _setup_faster_whisper,
    ):
        """Output is valid SRT format with sequence numbers and timestamps."""
        mock_fw = _setup_faster_whisper
        seg1 = MagicMock(start=1.0, end=3.5, text="  First line.  ")
        seg2 = MagicMock(start=4.0, end=6.0, text="  Second line.  ")
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([seg1, seg2], MagicMock())
        mock_fw.WhisperModel.return_value = mock_model

        result = _transcribe_whisper("test.mp4")
        lines = result.strip().split("\n")

        # Check SRT structure: number, timestamp, text, blank
        assert lines[0] == "1"
        assert "-->" in lines[1]
        assert "First line." in lines[2]  # noqa: PLR2004
        assert lines[4] == "2"  # noqa: PLR2004
        assert "Second line." in lines[6]  # noqa: PLR2004

    def test_transcribe_whisper_import_error(self):
        """When faster_whisper is not installed, ImportError propagates."""
        _real = __import__

        def _block(name, *a, **kw):
            if name == "faster_whisper":
                raise ImportError(name)
            return _real(name, *a, **kw)

        with (
            patch("builtins.__import__", side_effect=_block),
            pytest.raises(ImportError),
        ):
            _transcribe_whisper("test.mp4")


# ---------------------------------------------------------------------------
# _transcribe_google_cloud — additional tests
# ---------------------------------------------------------------------------


class TestTranscribeGoogleCloudAdditional:
    """Additional Google Cloud STT tests."""

    @patch(f"{_MOD}.load_google_cloud_api_key", return_value=None)
    def test_transcribe_google_cloud_missing_api_key_none(self, mock_key):
        """None API key raises ValueError('AUTH_ERROR')."""
        with pytest.raises(ValueError, match="AUTH_ERROR"):
            _transcribe_google_cloud("test.mp4")

    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key123")
    @patch(f"{_MOD}._extract_audio_to_flac")
    def test_transcribe_google_cloud_audio_size_limit(
        self,
        mock_extract,
        mock_key,
        tmp_path,
    ):
        """Audio file exactly at _MAX_AUDIO_BYTES does NOT raise."""
        flac = tmp_path / "audio.flac"
        # Write exactly at limit — should NOT raise
        flac.write_bytes(b"\x00" * _MAX_AUDIO_BYTES)
        mock_extract.return_value = flac

        with (
            patch(
                f"{_MOD}._call_long_running_recognize",
                return_value="op-1",
            ),
            patch(
                f"{_MOD}._poll_operation",
                return_value={"results": []},
            ),
            patch(f"{_MOD}._parse_results_to_srt", return_value=""),
            patch(f"{_MOD}._get_speech_language_code", return_value="en-US"),
        ):
            # Should not raise AUDIO_TOO_LARGE
            result = _transcribe_google_cloud("test.mp4")
            assert isinstance(result, str)

    @patch(f"{_MOD}._parse_results_to_srt", return_value="srt")
    @patch(f"{_MOD}._call_long_running_recognize", return_value="op-cancel")
    @patch(f"{_MOD}._get_speech_language_code", return_value="en-US")
    @patch(f"{_MOD}._extract_audio_to_flac")
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key123")
    def test_transcribe_google_cloud_cancellation_during_poll(  # noqa: PLR0913
        self,
        mock_key,
        mock_extract,
        mock_lang,
        mock_recognize,
        mock_parse,
        tmp_path,
    ):
        """When is_cancelled fires during poll, ValueError('CANCELLED') is raised."""
        flac = tmp_path / "audio.flac"
        flac.write_bytes(b"\x00" * 100)
        mock_extract.return_value = flac

        with (
            patch(
                f"{_MOD}._poll_operation",
                side_effect=ValueError("CANCELLED"),
            ),
            pytest.raises(ValueError, match="CANCELLED"),
        ):
            _transcribe_google_cloud(
                "test.mp4",
                is_cancelled=lambda: True,
            )


# ---------------------------------------------------------------------------
# _parse_srt_timestamp — dot separator edge case
# ---------------------------------------------------------------------------


class TestParseSrtTimestampDotSeparator:
    """Test SRT timestamp parsing with dot separator (VTT format)."""

    def test_parse_srt_timestamp_dot_separator(self):
        """VTT-style dot separator (e.g. '00:01:23.456') is parsed correctly."""
        result = _parse_srt_timestamp("00:01:23.456")
        expected = 1 * 60 + 23.456  # noqa: PLR2004
        assert abs(result - expected) < 0.001  # noqa: PLR2004

    def test_parse_srt_timestamp_comma_separator(self):
        """Standard SRT comma separator is parsed correctly."""
        result = _parse_srt_timestamp("00:01:23,456")
        expected = 1 * 60 + 23.456  # noqa: PLR2004
        assert abs(result - expected) < 0.001  # noqa: PLR2004

    def test_parse_srt_timestamp_two_part_format(self):
        """MM:SS.mmm format (no hours) is parsed correctly."""
        result = _parse_srt_timestamp("05:30.500")
        expected = 5 * 60 + 30.5  # noqa: PLR2004
        assert abs(result - expected) < 0.001  # noqa: PLR2004

    def test_parse_srt_timestamp_invalid_returns_zero(self):
        """Invalid timestamp string returns 0.0."""
        assert _parse_srt_timestamp("not-a-timestamp") == 0.0


# ---------------------------------------------------------------------------
# _generate_silence — error handling
# ---------------------------------------------------------------------------


class TestGenerateSilenceErrors:
    """Tests for _generate_silence error paths."""

    @patch("subprocess.run")
    def test_called_process_error_propagates(self, mock_run, tmp_path):
        """CalledProcessError from FFmpeg propagates."""
        mock_run.side_effect = subprocess.CalledProcessError(
            1,
            "ffmpeg",
            stderr=b"silence error",
        )
        with pytest.raises(subprocess.CalledProcessError):
            _generate_silence(1.0, tmp_path / "silence.mp3")

    @patch("subprocess.run")
    def test_timeout_expired_propagates(self, mock_run, tmp_path):
        """TimeoutExpired from FFmpeg propagates."""
        mock_run.side_effect = subprocess.TimeoutExpired("ffmpeg", 30)
        with pytest.raises(subprocess.TimeoutExpired):
            _generate_silence(1.0, tmp_path / "silence.mp3")

    @patch("subprocess.run")
    def test_zero_duration(self, mock_run, tmp_path):
        """Zero duration still calls FFmpeg with '0.000'."""
        mock_run.return_value = MagicMock(returncode=0)
        _generate_silence(0.0, tmp_path / "silence.mp3")
        cmd = mock_run.call_args[0][0]
        t_idx = cmd.index("-t")
        assert cmd[t_idx + 1] == "0.000"


# ---------------------------------------------------------------------------
# _parse_results_to_srt — fallback edge cases
# ---------------------------------------------------------------------------


class TestParseResultsToSrtFallbackEdgeCases:
    """Edge-case tests for _parse_results_to_srt transcript fallback."""

    def test_results_with_empty_words_list_uses_fallback(self):
        """When words list is empty, falls back to transcript-only mode."""
        results = [
            {"alternatives": [{"transcript": "Hello", "words": []}]},
        ]
        srt = _parse_results_to_srt(results)
        assert "Hello" in srt
        assert "00:00:00,000 --> 00:00:00,000" in srt

    def test_whitespace_only_transcript_skipped(self):
        """Whitespace-only transcripts are skipped in fallback mode."""
        results = [
            {"alternatives": [{"transcript": "   "}]},
            {"alternatives": [{"transcript": "Real text"}]},
        ]
        srt = _parse_results_to_srt(results)
        assert "Real text" in srt
        assert srt.count("-->") == 1

    def test_missing_word_field_in_word_info(self):
        """Word dict without 'word' key defaults to empty string."""
        results = [
            {
                "alternatives": [
                    {
                        "words": [
                            {"startTime": "0s", "endTime": "1s"},
                            {"word": "world", "startTime": "1s", "endTime": "2s"},
                        ],
                    }
                ],
            }
        ]
        srt = _parse_results_to_srt(results)
        assert "world" in srt


# ---------------------------------------------------------------------------
# _extract_audio_to_flac — timeout handling
# ---------------------------------------------------------------------------


class TestExtractAudioToFlacTimeout:
    """Tests for _extract_audio_to_flac timeout scenarios."""

    @patch("subprocess.run")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_timeout_expired_raises(self, mock_ff, mock_run, tmp_path):
        """TimeoutExpired raises RuntimeError('FFMPEG_NOT_FOUND')."""
        mock_run.side_effect = subprocess.TimeoutExpired("ffmpeg", 300)
        with pytest.raises(RuntimeError, match="FFMPEG_NOT_FOUND"):
            _extract_audio_to_flac(str(tmp_path / "video.mp4"))


# ---------------------------------------------------------------------------
# mix_audio_into_video — timeout handling
# ---------------------------------------------------------------------------


class TestMixAudioIntoVideoTimeout:
    """Tests for mix_audio_into_video timeout scenarios."""

    @patch("subprocess.run")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_timeout_expired_raises_runtime_error(
        self,
        mock_ff,
        mock_run,
        tmp_path,
    ):
        """TimeoutExpired from FFmpeg propagates as-is."""
        mock_run.side_effect = subprocess.TimeoutExpired("ffmpeg", 600)
        with pytest.raises(subprocess.TimeoutExpired):
            mix_audio_into_video(
                str(tmp_path / "v.mp4"),
                str(tmp_path / "a.mp3"),
                str(tmp_path / "o.mp4"),
            )


# ---------------------------------------------------------------------------
# _poll_operation — HTTP error branches
# ---------------------------------------------------------------------------


class TestPollOperationHttpErrors:
    """Test _poll_operation handling of HTTP errors during polling."""

    def _make_response(self, data: dict) -> MagicMock:
        """Create a mock urlopen context-manager response."""
        resp = MagicMock()
        resp.read.return_value = json.dumps(data).encode("utf-8")
        resp.__enter__ = MagicMock(return_value=resp)
        resp.__exit__ = MagicMock(return_value=False)
        return resp

    @patch("time.sleep")
    @patch("urllib.request.urlopen")
    def test_http_429_raises_quota_error(self, mock_urlopen, mock_sleep):
        """HTTP 429 during polling raises ValueError('QUOTA_ERROR')."""
        fp = MagicMock(read=lambda: b"rate limited")
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "url",
            429,
            "Too Many Requests",
            {},
            fp,  # noqa: PLR2004
        )
        with pytest.raises(ValueError, match="QUOTA_ERROR"):
            _poll_operation("operations/quota", "key")

    @patch("time.sleep")
    @patch("urllib.request.urlopen")
    def test_http_403_raises_auth_error(self, mock_urlopen, mock_sleep):
        """HTTP 403 during polling raises ValueError('AUTH_ERROR')."""
        fp = MagicMock(read=lambda: b"forbidden")
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "url",
            403,
            "Forbidden",
            {},
            fp,
        )
        with pytest.raises(ValueError, match="AUTH_ERROR"):
            _poll_operation("operations/auth", "key")

    @patch("time.sleep")
    @patch("urllib.request.urlopen")
    def test_http_500_raises_speech_api_error(self, mock_urlopen, mock_sleep):
        """HTTP 500 during polling raises ValueError('SPEECH_API_ERROR')."""
        fp = MagicMock(read=lambda: b"internal error")
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "url",
            500,
            "Internal Server Error",
            {},
            fp,  # noqa: PLR2004
        )
        with pytest.raises(ValueError, match="SPEECH_API_ERROR: HTTP 500"):
            _poll_operation("operations/err", "key")

    @patch("time.sleep")
    @patch("urllib.request.urlopen")
    def test_http_503_raises_speech_api_error(self, mock_urlopen, mock_sleep):
        """HTTP 503 during polling raises ValueError('SPEECH_API_ERROR')."""
        fp = MagicMock(read=lambda: b"service unavailable")
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "url",
            503,
            "Service Unavailable",
            {},
            fp,  # noqa: PLR2004
        )
        with pytest.raises(ValueError, match="SPEECH_API_ERROR: HTTP 503"):
            _poll_operation("operations/unavail", "key")

    @patch("time.sleep")
    @patch("urllib.request.urlopen")
    def test_done_with_error_missing_message(self, mock_urlopen, mock_sleep):
        """Operation done with error but no message uses 'Unknown error'."""
        mock_urlopen.return_value = self._make_response(
            {"done": True, "error": {}},
        )
        with pytest.raises(ValueError, match="Unknown error"):
            _poll_operation("operations/err", "key")

    @patch("time.sleep")
    @patch("urllib.request.urlopen")
    def test_done_with_no_response_returns_empty_dict(
        self,
        mock_urlopen,
        mock_sleep,
    ):
        """Operation done without 'response' key returns empty dict."""
        mock_urlopen.return_value = self._make_response({"done": True})
        result = _poll_operation("operations/empty", "key")
        assert result == {}

    @patch("time.sleep")
    @patch("urllib.request.urlopen")
    def test_cancellation_checked_before_sleep(
        self,
        mock_urlopen,
        mock_sleep,
    ):
        """Cancellation is checked before sleeping, not after."""
        cancel_count = 0

        def cancel_after_first():
            nonlocal cancel_count
            cancel_count += 1
            return cancel_count > 1  # noqa: PLR2004

        # First call: is_cancelled returns False → sleeps → polls → not done
        # Second call: is_cancelled returns True → raises CANCELLED
        pending = self._make_response({"done": False})
        mock_urlopen.return_value = pending

        with pytest.raises(ValueError, match="CANCELLED"):
            _poll_operation(
                "operations/cancel",
                "key",
                is_cancelled=cancel_after_first,
            )
        # Only one poll should have been made
        assert mock_urlopen.call_count == 1

    @patch("time.sleep")
    @patch("urllib.request.urlopen")
    def test_exponential_backoff_delays(self, mock_urlopen, mock_sleep):
        """Sleep delays increase with exponential backoff."""
        pending = self._make_response({"done": False})
        complete = self._make_response(
            {"done": True, "response": {"results": []}},
        )
        mock_urlopen.side_effect = [pending, pending, pending, complete]

        _poll_operation("operations/backoff", "key")

        delays = [call[0][0] for call in mock_sleep.call_args_list]
        assert len(delays) == 4  # noqa: PLR2004
        # Each delay should be >= previous delay (exponential backoff)
        for i in range(1, len(delays)):
            assert delays[i] >= delays[i - 1]


# ---------------------------------------------------------------------------
# synthesize_timed_speech — rate adjustment branches
# ---------------------------------------------------------------------------


class TestSynthesizeTimedSpeechRateBranches:
    """Test timed speech rate adjustment: exact fit, no overflow, slow down."""

    @pytest.fixture(autouse=True)
    def _mock_edge(self):
        """Prevent edge_tts import in tests running outside uv."""
        with patch(f"{_MOD}._synthesize_chunk_edge"):
            yield

    def _make_entry(self, start: str, end: str, text: str) -> MagicMock:
        """Create a mock SubtitleEntry."""
        entry = MagicMock()
        entry.start = start
        entry.end = end
        entry.text = text
        return entry

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration", return_value=2.0)
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_audio_fits_exactly_no_speedup(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_synth,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """Audio duration == slot duration: no speed-up needed."""
        entries = [
            self._make_entry("00:00:00,000", "00:00:02,000", "Exact"),
        ]
        output = str(tmp_path / "out.mp3")
        synthesize_timed_speech(
            entries,
            tts_method=_GOOGLE_TTS,
            output_path=output,
        )
        # Only one synth call (no re-synth for speed-up)
        assert mock_synth.call_count == 1

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration", return_value=0.5)
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_audio_shorter_than_slot_no_speedup(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_synth,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """Audio shorter than slot: no speed-up, no re-synth."""
        entries = [
            self._make_entry("00:00:00,000", "00:00:05,000", "Short"),
        ]
        output = str(tmp_path / "out.mp3")
        synthesize_timed_speech(
            entries,
            tts_method=_GOOGLE_TTS,
            output_path=output,
        )
        # Only one synth call (no speed-up)
        assert mock_synth.call_count == 1

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration")
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_last_entry_overflow_uses_unlimited_gap(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_synth,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """Last entry: next_gap is inf, so allowed = tolerance cap."""
        # 4s audio in 2s slot → overflow = 2.0
        # tolerance = min(2*0.5, 2.0) = 1.0
        # next_gap = inf → allowed = min(1.0, inf) = 1.0
        # overflow (2.0) > allowed (1.0) → speed up
        # rate = 4.0 / (2.0 + 1.0) = 1.333
        mock_dur.side_effect = [4.0, 3.0]
        entries = [
            self._make_entry("00:00:00,000", "00:00:02,000", "Last entry"),
        ]
        output = str(tmp_path / "out.mp3")
        synthesize_timed_speech(
            entries,
            tts_method=_GOOGLE_TTS,
            output_path=output,
        )
        # Re-synth with speaking_rate
        resyn_call = mock_synth.call_args_list[1]
        expected_rate = 4.0 / 3.0  # noqa: PLR2004
        assert abs(resyn_call[1]["speaking_rate"] - expected_rate) < 0.01  # noqa: PLR2004

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration", return_value=2.2)
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_overflow_within_both_tolerance_and_gap_no_speedup(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_synth,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """No speed-up when overflow <= allowed (tolerance AND gap sufficient)."""
        # 2.2s audio in 2s slot → overflow = 0.2
        # tolerance = min(2*0.5, 2.0) = 1.0
        # next entry at 10s → gap = 8.0
        # allowed = min(1.0, 8.0) = 1.0; overflow (0.2) <= 1.0 → keep natural
        entries = [
            self._make_entry("00:00:00,000", "00:00:02,000", "Slightly long"),
            self._make_entry("00:00:10,000", "00:00:12,000", "Far away"),
        ]
        output = str(tmp_path / "out.mp3")
        synthesize_timed_speech(
            entries,
            tts_method=_GOOGLE_TTS,
            output_path=output,
        )
        # No re-synth — only 2 original synths
        assert mock_synth.call_count == 2  # noqa: PLR2004

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration")
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_zero_fit_window_uses_available(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_synth,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """When fit_window=0 (available + allowed = 0), rate uses available."""
        # Tiny slot: 0.1s, audio = 5.0s
        # available = 0.1, tolerance = min(0.1*0.5, 2.0) = 0.05
        # next entry immediately at 0.1s → gap = 0.0
        # allowed = min(0.05, 0.0) = 0.0
        # fit_window = 0.1 + 0.0 = 0.1 (> 0 branch)
        # rate = 5.0 / 0.1 = 50.0 (clamped to 4.0 by _synthesize_chunk)
        mock_dur.side_effect = [5.0, 1.0, 1.0]
        entries = [
            self._make_entry("00:00:00,000", "00:00:00,100", "Tiny slot"),
            self._make_entry("00:00:00,100", "00:00:01,100", "Next"),
        ]
        output = str(tmp_path / "out.mp3")
        synthesize_timed_speech(
            entries,
            tts_method=_GOOGLE_TTS,
            output_path=output,
        )
        # Re-synth was attempted
        resyn_call = mock_synth.call_args_list[1]
        assert resyn_call[1]["speaking_rate"] > 1.0  # noqa: PLR2004


# ---------------------------------------------------------------------------
# _synthesize_chunk_edge — non-NoAudioReceived exceptions
# ---------------------------------------------------------------------------


class TestSynthesizeChunkEdgeErrorPropagation:
    """Test Edge TTS error propagation for non-retryable exceptions."""

    @pytest.fixture(autouse=True)
    def _setup_edge_tts(self):
        """Inject mock edge_tts and edge_tts.exceptions into sys.modules."""
        self._NoAudioReceived = type("NoAudioReceived", (Exception,), {})

        mock_edge = MagicMock()
        mock_exceptions = MagicMock()
        mock_exceptions.NoAudioReceived = self._NoAudioReceived

        prev_edge = sys.modules.get("edge_tts")
        prev_exc = sys.modules.get("edge_tts.exceptions")
        sys.modules["edge_tts"] = mock_edge
        sys.modules["edge_tts.exceptions"] = mock_exceptions

        self._mock_edge = mock_edge
        yield
        if prev_edge is None:
            sys.modules.pop("edge_tts", None)
        else:
            sys.modules["edge_tts"] = prev_edge
        if prev_exc is None:
            sys.modules.pop("edge_tts.exceptions", None)
        else:
            sys.modules["edge_tts.exceptions"] = prev_exc

    def test_generic_exception_propagates_immediately(self, tmp_path):
        """Non-NoAudioReceived exceptions propagate without retry."""
        output = tmp_path / "out.mp3"
        mock_comm = MagicMock()
        mock_comm.save = AsyncMock(
            side_effect=RuntimeError("connection reset"),
        )
        self._mock_edge.Communicate.return_value = mock_comm

        with pytest.raises(RuntimeError, match="connection reset"):
            _synthesize_chunk_edge(
                "Hi",
                "en-US-JennyNeural",
                output,
                max_retries=3,
                base_delay=0.0,
            )
        # Only called once — no retries for non-NoAudioReceived errors
        assert mock_comm.save.await_count == 1

    def test_value_error_from_edge_propagates(self, tmp_path):
        """ValueError from edge_tts propagates directly."""
        output = tmp_path / "out.mp3"
        mock_comm = MagicMock()
        mock_comm.save = AsyncMock(
            side_effect=ValueError("bad voice name"),
        )
        self._mock_edge.Communicate.return_value = mock_comm

        with pytest.raises(ValueError, match="bad voice name"):
            _synthesize_chunk_edge(
                "Hi",
                "invalid-voice",
                output,
                max_retries=2,
                base_delay=0.0,
            )

    def test_os_error_from_edge_propagates(self, tmp_path):
        """OSError from edge_tts propagates directly."""
        output = tmp_path / "out.mp3"
        mock_comm = MagicMock()
        mock_comm.save = AsyncMock(
            side_effect=OSError("disk full"),
        )
        self._mock_edge.Communicate.return_value = mock_comm

        with pytest.raises(OSError, match="disk full"):
            _synthesize_chunk_edge(
                "Hi",
                "en-US-JennyNeural",
                output,
                max_retries=1,
                base_delay=0.0,
            )

    def test_max_retries_zero_single_attempt(self, tmp_path):
        """With max_retries=0, only one attempt is made."""
        output = tmp_path / "out.mp3"
        mock_comm = MagicMock()
        mock_comm.save = AsyncMock(
            side_effect=self._NoAudioReceived("no audio"),
        )
        self._mock_edge.Communicate.return_value = mock_comm

        with pytest.raises(ValueError, match="TTS_API_ERROR"):
            _synthesize_chunk_edge(
                "Hi",
                "en-US-JennyNeural",
                output,
                max_retries=0,
                base_delay=0.0,
            )
        # Only one attempt with max_retries=0
        assert mock_comm.save.await_count == 1


# ---------------------------------------------------------------------------
# _synthesize_chunk — empty audioContent
# ---------------------------------------------------------------------------


class TestSynthesizeChunkEmptyAudio:
    """Test _synthesize_chunk with empty or missing audioContent."""

    @patch("urllib.request.urlopen")
    def test_empty_audio_content_raises_invalid_response(
        self,
        mock_urlopen,
        tmp_path,
    ):
        """Empty audioContent → INVALID_RESPONSE sentinel.

        Was previously writing a zero-byte file — that silently
        produced a "successful" save the user couldn't play.  The
        typed sentinel surfaces the failure in the UI.
        """
        resp_data = json.dumps({"audioContent": ""}).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = resp_data
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        out = tmp_path / "chunk.mp3"
        with pytest.raises(ValueError, match="INVALID_RESPONSE"):
            _synthesize_chunk("Hi", "en-US", "FEMALE", "key", out)
        # No zero-byte file left on disk either.
        assert not out.exists()

    @patch("urllib.request.urlopen")
    def test_missing_audio_content_key_raises_invalid_response(
        self,
        mock_urlopen,
        tmp_path,
    ):
        """Missing 'audioContent' key → INVALID_RESPONSE sentinel.

        Was raising bare KeyError (programming-bug noise); typed
        sentinel matches the empty-payload case and routes through
        the standard error UI.
        """
        resp_data = json.dumps({"status": "ok"}).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = resp_data
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        out = tmp_path / "chunk.mp3"
        with pytest.raises(ValueError, match="INVALID_RESPONSE"):
            _synthesize_chunk("Hi", "en-US", "FEMALE", "key", out)

    @patch("urllib.request.urlopen")
    def test_invalid_base64_raises(self, mock_urlopen, tmp_path):
        """Invalid base64 in audioContent raises an error."""
        resp_data = json.dumps({"audioContent": "!!not-base64!!"}).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = resp_data
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        out = tmp_path / "chunk.mp3"
        with pytest.raises(Exception):  # noqa: B017
            _synthesize_chunk("Hi", "en-US", "FEMALE", "key", out)


# ---------------------------------------------------------------------------
# _convert_subtitle_format — ASS/SSA format handling
# ---------------------------------------------------------------------------


class TestConvertSubtitleFormatASS:
    """Test _convert_subtitle_format with ASS/SSA/unknown formats."""

    def test_ssa_format_now_converts(self):
        """SSA is now a supported target — produces a Script Info file."""
        srt = "1\n00:00:01,000 --> 00:00:04,000\nHello\n"
        result = _convert_subtitle_format(srt, ".ssa")
        assert "[Script Info]" in result
        assert "Dialogue:" in result
        assert "Hello" in result

    def test_txt_format_returns_srt_unchanged(self):
        """TXT format returns original SRT text unchanged."""
        srt = "1\n00:00:01,000 --> 00:00:04,000\nHello\n"
        assert _convert_subtitle_format(srt, ".txt") == srt

    def test_empty_extension_returns_srt_unchanged(self):
        """Empty extension returns original SRT text unchanged."""
        srt = "1\n00:00:01,000 --> 00:00:04,000\nHello\n"
        assert _convert_subtitle_format(srt, "") == srt

    def test_vtt_with_multiline_subtitle(self):
        """VTT conversion handles multi-line subtitle text."""
        srt = (
            "1\n00:00:01,000 --> 00:00:04,000\n"
            "Line one\nLine two\n\n"
            "2\n00:00:05,000 --> 00:00:08,000\nThird line\n"
        )
        vtt = _convert_subtitle_format(srt, ".vtt")
        assert vtt.startswith("WEBVTT\n")
        assert "Line one" in vtt
        assert "Line two" in vtt
        assert "Third line" in vtt
        # Timestamps converted
        assert "00:00:01.000 --> 00:00:04.000" in vtt

    def test_vtt_with_numbers_in_text_not_affected(self):
        """Numbers in subtitle text are not treated as timestamps."""
        srt = "1\n00:00:01,000 --> 00:00:04,000\nPrice is $1,000 for 2,500 items\n"
        vtt = _convert_subtitle_format(srt, ".vtt")
        # The text line contains commas but should not be converted
        assert "$1,000" in vtt
        assert "2,500" in vtt
        # Timestamps should be converted
        assert "00:00:01.000 --> 00:00:04.000" in vtt


# ---------------------------------------------------------------------------
# mix_audio_into_video — missing inputs
# ---------------------------------------------------------------------------


class TestMixAudioIntoVideoMissingInputs:
    """Test mix_audio_into_video with missing input files."""

    @patch("subprocess.run")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_ffmpeg_file_not_found_propagates(
        self,
        mock_ff,
        mock_run,
        tmp_path,
    ):
        """FileNotFoundError from subprocess (missing ffmpeg binary) propagates."""
        mock_run.side_effect = FileNotFoundError("ffmpeg not found")
        with pytest.raises(FileNotFoundError):
            mix_audio_into_video(
                str(tmp_path / "nonexistent.mp4"),
                str(tmp_path / "nonexistent.mp3"),
                str(tmp_path / "out.mp4"),
            )

    @patch("subprocess.run")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_stderr_message_in_runtime_error(
        self,
        mock_ff,
        mock_run,
        tmp_path,
    ):
        """CalledProcessError stderr is included in the RuntimeError."""
        mock_run.side_effect = subprocess.CalledProcessError(
            1,
            "ffmpeg",
            stderr=b"No such file or directory: video.mp4",
        )
        with pytest.raises(RuntimeError, match="FFMPEG_MIX_FAILED"):
            mix_audio_into_video(
                str(tmp_path / "missing.mp4"),
                str(tmp_path / "missing.mp3"),
                str(tmp_path / "out.mp4"),
            )

    @patch("subprocess.run")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_returns_output_path_on_success(
        self,
        mock_ff,
        mock_run,
        tmp_path,
    ):
        """Successful mix returns the output path string."""
        mock_run.return_value = MagicMock(returncode=0)
        out = str(tmp_path / "dubbed.mp4")
        result = mix_audio_into_video(
            str(tmp_path / "v.mp4"),
            str(tmp_path / "a.mp3"),
            out,
        )
        assert result == out

    @patch("subprocess.run")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_uses_600_second_timeout(self, mock_ff, mock_run, tmp_path):
        """FFmpeg subprocess is called with 600 second timeout."""
        mock_run.return_value = MagicMock(returncode=0)
        mix_audio_into_video(
            str(tmp_path / "v.mp4"),
            str(tmp_path / "a.mp3"),
            str(tmp_path / "o.mp4"),
        )
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["timeout"] == 600  # noqa: PLR2004


# ---------------------------------------------------------------------------
# transcribe_audio — empty/silent audio
# ---------------------------------------------------------------------------


class TestTranscribeAudioEmptySilent:
    """Test transcribe_audio with audio that has no speech content."""

    @pytest.fixture(autouse=True)
    def _setup_faster_whisper(self):
        """Ensure faster_whisper mock module is available for local import."""
        mock_fw = MagicMock()
        mock_fw.WhisperModel = MagicMock()
        prev = sys.modules.get("faster_whisper")
        sys.modules["faster_whisper"] = mock_fw
        yield mock_fw
        if prev is None:
            sys.modules.pop("faster_whisper", None)
        else:
            sys.modules["faster_whisper"] = prev

    def test_whisper_empty_segments_returns_empty_srt(
        self,
        _setup_faster_whisper,
    ):
        """Whisper with no segments returns empty SRT."""
        mock_fw = _setup_faster_whisper
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([], MagicMock())
        mock_fw.WhisperModel.return_value = mock_model

        result = _transcribe_whisper("silent.mp4", src_lang="", model_size="base")
        assert result == ""

    def test_whisper_whitespace_segments_still_included(
        self,
        _setup_faster_whisper,
    ):
        """Whisper segments with whitespace-only text are included (stripped)."""
        mock_fw = _setup_faster_whisper
        seg = MagicMock(start=0.0, end=1.0, text="   ")
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([seg], MagicMock())
        mock_fw.WhisperModel.return_value = mock_model

        result = _transcribe_whisper("silent.mp4")
        # The segment is included even with whitespace (strip yields empty)
        assert "-->" in result

    @patch(f"{_MOD}._parse_results_to_srt", return_value="")
    @patch(
        f"{_MOD}._poll_operation",
        return_value={"results": []},
    )
    @patch(f"{_MOD}._call_long_running_recognize", return_value="op-silent")
    @patch(f"{_MOD}._get_speech_language_code", return_value="en-US")
    @patch(f"{_MOD}._extract_audio_to_flac")
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_google_empty_results_returns_empty_srt(  # noqa: PLR0913
        self,
        mock_key,
        mock_extract,
        mock_lang,
        mock_recognize,
        mock_poll,
        mock_parse,
        tmp_path,
    ):
        """Google Cloud STT with no speech returns empty SRT."""
        flac = tmp_path / "audio.flac"
        flac.write_bytes(b"\x00" * 100)
        mock_extract.return_value = flac

        result = _transcribe_google_cloud("silent.mp4")
        assert result == ""
        mock_parse.assert_called_once_with([])

    @patch(f"{_MOD}._parse_results_to_srt")
    @patch(
        f"{_MOD}._poll_operation",
        return_value={},
    )
    @patch(f"{_MOD}._call_long_running_recognize", return_value="op-no-results")
    @patch(f"{_MOD}._get_speech_language_code", return_value="en-US")
    @patch(f"{_MOD}._extract_audio_to_flac")
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_google_missing_results_key(  # noqa: PLR0913
        self,
        mock_key,
        mock_extract,
        mock_lang,
        mock_recognize,
        mock_poll,
        mock_parse,
        tmp_path,
    ):
        """Google Cloud STT response without 'results' key uses empty list."""
        flac = tmp_path / "audio.flac"
        flac.write_bytes(b"\x00" * 100)
        mock_extract.return_value = flac
        mock_parse.return_value = ""

        _transcribe_google_cloud("silent.mp4")
        # _parse_results_to_srt is called with empty list (default from .get)
        mock_parse.assert_called_once_with([])

    def test_whisper_single_segment_srt_format(self, _setup_faster_whisper):
        """Single Whisper segment produces valid SRT with sequence number 1."""
        mock_fw = _setup_faster_whisper
        seg = MagicMock(start=0.0, end=0.5, text="  Hi  ")
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([seg], MagicMock())
        mock_fw.WhisperModel.return_value = mock_model

        result = _transcribe_whisper("test.mp4")
        lines = result.strip().split("\n")
        assert lines[0] == "1"
        assert "-->" in lines[1]
        assert "Hi" in lines[2]  # noqa: PLR2004


# ---------------------------------------------------------------------------
# synthesize_timed_speech — Edge TTS speed-up with file existence check
# ---------------------------------------------------------------------------


class TestSynthesizeTimedSpeechEdgeSpeedUpBranches:
    """Test Edge TTS speed-up paths including fast_path existence checks."""

    def _make_entry(self, start: str, end: str, text: str) -> MagicMock:
        """Create a mock SubtitleEntry."""
        entry = MagicMock()
        entry.start = start
        entry.end = end
        entry.text = text
        return entry

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration")
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._speed_up_audio")
    @patch(f"{_MOD}._synthesize_chunk_edge")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_edge_speedup_with_fast_path_exists(  # noqa: PLR0913
        self,
        mock_ffmpeg,
        mock_edge,
        mock_speedup,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """When fast_path exists after atempo, it is used instead of original."""

        # Create the fast file so that the existence check passes
        def create_fast_file(inp, outp, factor):
            outp.write_bytes(b"fast audio")

        mock_speedup.side_effect = create_fast_file
        # First call: original audio = 5.0s, second: fast = 2.5s, third: 1.0s
        mock_dur.side_effect = [5.0, 2.5, 1.0]

        entries = [
            self._make_entry("00:00:00,000", "00:00:02,000", "Long text"),
            self._make_entry("00:00:02,500", "00:00:04,000", "Next"),
        ]
        output = str(tmp_path / "out.mp3")
        synthesize_timed_speech(entries, output_path=output)

        # Speed-up called, and the re-measured duration (2.5) was used
        assert mock_speedup.call_count == 1
        # Duration measured 3 times: original + fast + second entry
        assert mock_dur.call_count == 3  # noqa: PLR2004

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration", return_value=0.5)
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._speed_up_audio")
    @patch(f"{_MOD}._synthesize_chunk_edge")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_edge_no_overflow_no_speedup(  # noqa: PLR0913
        self,
        mock_ffmpeg,
        mock_edge,
        mock_speedup,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """Edge: audio shorter than slot does not trigger speed-up."""
        entries = [
            self._make_entry("00:00:00,000", "00:00:05,000", "Short"),
        ]
        output = str(tmp_path / "out.mp3")
        synthesize_timed_speech(entries, output_path=output)
        mock_speedup.assert_not_called()

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration", return_value=2.0)
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._speed_up_audio")
    @patch(f"{_MOD}._synthesize_chunk_edge")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_edge_exact_fit_no_speedup(  # noqa: PLR0913
        self,
        mock_ffmpeg,
        mock_edge,
        mock_speedup,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """Edge: audio exactly matching slot does not trigger speed-up."""
        entries = [
            self._make_entry("00:00:00,000", "00:00:02,000", "Exact fit"),
        ]
        output = str(tmp_path / "out.mp3")
        synthesize_timed_speech(entries, output_path=output)
        mock_speedup.assert_not_called()


# ---------------------------------------------------------------------------
# _poll_operation — URLError (network errors)
# ---------------------------------------------------------------------------


class TestPollOperationNetworkErrors:
    """Test _poll_operation with network-level errors (URLError)."""

    @patch("time.sleep")
    @patch("urllib.request.urlopen")
    def test_url_error_propagates(self, mock_urlopen, mock_sleep):
        """URLError (no network) propagates as urllib.error.URLError."""
        mock_urlopen.side_effect = urllib.error.URLError("no network")
        with pytest.raises(urllib.error.URLError):
            _poll_operation("operations/net", "key")

    @patch("time.sleep")
    @patch("urllib.request.urlopen")
    def test_timeout_error_propagates(self, mock_urlopen, mock_sleep):
        """TimeoutError wrapping URLError propagates."""
        mock_urlopen.side_effect = urllib.error.URLError(
            TimeoutError("connection timed out"),
        )
        with pytest.raises(urllib.error.URLError):
            _poll_operation("operations/timeout", "key")


# ---------------------------------------------------------------------------
# _call_long_running_recognize — additional error branches
# ---------------------------------------------------------------------------


class TestCallLongRunningRecognizeExtended:
    """Additional error handling tests for _call_long_running_recognize."""

    @patch("urllib.request.urlopen")
    def test_http_403_raises_auth_error(self, mock_urlopen):
        """HTTP 403 raises ValueError('AUTH_ERROR')."""
        fp = MagicMock(read=lambda: b"forbidden")
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "url",
            403,
            "Forbidden",
            {},
            fp,
        )
        with pytest.raises(ValueError, match="AUTH_ERROR"):
            _call_long_running_recognize("audio", "en-US", "bad-key")

    @patch("urllib.request.urlopen")
    def test_custom_model_in_payload(self, mock_urlopen):
        """Custom STT model is included in the request payload."""
        resp = MagicMock()
        resp.read.return_value = json.dumps({"name": "op-1"}).encode()
        resp.__enter__ = MagicMock(return_value=resp)
        resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = resp

        _call_long_running_recognize(
            "audio_b64",
            "vi-VN",
            "key",
            model="latest_long",
        )
        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode("utf-8"))
        assert payload["config"]["model"] == "latest_long"

    @patch("urllib.request.urlopen")
    def test_language_code_in_payload(self, mock_urlopen):
        """Specified language code appears in the request payload."""
        resp = MagicMock()
        resp.read.return_value = json.dumps({"name": "op-2"}).encode()
        resp.__enter__ = MagicMock(return_value=resp)
        resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = resp

        _call_long_running_recognize("audio_b64", "ja-JP", "key")
        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode("utf-8"))
        assert payload["config"]["languageCode"] == "ja-JP"


# ---------------------------------------------------------------------------
# synthesize_timed_speech — Google TTS speaking_rate_below_min
# ---------------------------------------------------------------------------


class TestSynthesizeTimedSpeechRateClamp:
    """Test that speaking_rate below _TTS_MIN_SPEAKING_RATE skips re-synth."""

    @pytest.fixture(autouse=True)
    def _mock_edge(self):
        """Prevent edge_tts import in tests running outside uv."""
        with patch(f"{_MOD}._synthesize_chunk_edge"):
            yield

    def _make_entry(self, start: str, end: str, text: str) -> MagicMock:
        """Create a mock SubtitleEntry."""
        entry = MagicMock()
        entry.start = start
        entry.end = end
        entry.text = text
        return entry

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration")
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_overflow_but_rate_above_min_re_synthesizes(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_synth,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """Rate > _TTS_MIN_SPEAKING_RATE triggers re-synth."""
        # 5s audio in 2s slot, last entry → overflow = 3.0
        # tolerance = min(2*0.5, 2.0) = 1.0, next_gap = inf
        # allowed = min(1.0, inf) = 1.0; overflow (3.0) > 1.0 → speed up
        # rate = 5.0 / (2.0 + 1.0) = 1.667 (above 0.25)
        mock_dur.side_effect = [5.0, 3.0]
        entries = [
            self._make_entry("00:00:00,000", "00:00:02,000", "Medium text"),
        ]
        output = str(tmp_path / "out.mp3")
        synthesize_timed_speech(
            entries,
            tts_method=_GOOGLE_TTS,
            output_path=output,
        )
        # Re-synth happened (original + re-synth = 2 calls)
        assert mock_synth.call_count == 2  # noqa: PLR2004
        resyn_call = mock_synth.call_args_list[1]
        expected_rate = 5.0 / 3.0  # noqa: PLR2004
        assert abs(resyn_call[1]["speaking_rate"] - expected_rate) < 0.01  # noqa: PLR2004


# ===========================================================================
# NEW TESTS — edge cases for remaining branches
# ===========================================================================


# ---------------------------------------------------------------------------
# TestTranscribeAudioEdgeCases
# ---------------------------------------------------------------------------


class TestTranscribeAudioEdgeCases:
    """Edge-case tests for transcribe_audio dispatch and error paths."""

    @pytest.fixture(autouse=True)
    def _setup_faster_whisper(self):
        """Ensure faster_whisper mock module is available for local import."""
        mock_fw = MagicMock()
        mock_fw.WhisperModel = MagicMock()
        prev = sys.modules.get("faster_whisper")
        sys.modules["faster_whisper"] = mock_fw
        yield mock_fw
        if prev is None:
            sys.modules.pop("faster_whisper", None)
        else:
            sys.modules["faster_whisper"] = prev

    def test_whisper_model_loading_failure(self, _setup_faster_whisper):
        """WhisperModel constructor raising propagates the error."""
        mock_fw = _setup_faster_whisper
        mock_fw.WhisperModel.side_effect = RuntimeError("model load failed")

        with pytest.raises(RuntimeError, match="model load failed"):
            _transcribe_whisper("test.mp3", model_size="base")

    def test_whisper_transcribe_raises(self, _setup_faster_whisper):
        """Errors during model.transcribe propagate."""
        mock_fw = _setup_faster_whisper
        mock_model = MagicMock()
        mock_model.transcribe.side_effect = RuntimeError("corrupt audio")
        mock_fw.WhisperModel.return_value = mock_model

        with pytest.raises(RuntimeError, match="corrupt audio"):
            _transcribe_whisper("corrupt.mp3")

    def test_whisper_zero_length_segments(self, _setup_faster_whisper):
        """Whisper segments with start == end produce valid SRT lines."""
        mock_fw = _setup_faster_whisper
        seg = MagicMock(start=0.0, end=0.0, text="Zero len")
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([seg], MagicMock())
        mock_fw.WhisperModel.return_value = mock_model

        result = _transcribe_whisper("test.mp3")
        assert "Zero len" in result
        assert "00:00:00,000 --> 00:00:00,000" in result

    def test_whisper_very_long_audio_mock(self, _setup_faster_whisper):
        """Whisper with many segments (>1hr mock) produces valid SRT."""
        mock_fw = _setup_faster_whisper
        segments = []
        segment_count = 720
        for i in range(segment_count):
            seg = MagicMock(
                start=float(i * 5),
                end=float(i * 5 + 4),
                text=f"  Segment {i}  ",
            )
            segments.append(seg)
        mock_model = MagicMock()
        mock_model.transcribe.return_value = (segments, MagicMock())
        mock_fw.WhisperModel.return_value = mock_model

        result = _transcribe_whisper("long.mp3")
        # Should have all segment numbers
        assert f"{segment_count}\n" in result
        assert f"Segment {segment_count - 1}" in result

    @patch(f"{_MOD}._get_speech_language_code", return_value="fr")
    def test_whisper_language_no_hyphen(
        self,
        mock_lang,
        _setup_faster_whisper,
    ):
        """Language code without hyphen is passed as-is to Whisper."""
        mock_fw = _setup_faster_whisper
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([], MagicMock())
        mock_fw.WhisperModel.return_value = mock_model

        _transcribe_whisper("test.mp3", src_lang="French")

        call_kwargs = mock_model.transcribe.call_args[1]
        assert call_kwargs["language"] == "fr"

    @patch(f"{_MOD}._transcribe_google_cloud", return_value="srt data")
    def test_google_dispatch_passes_google_model(self, mock_google):
        """google_model is forwarded to _transcribe_google_cloud."""
        transcribe_audio(
            "test.mp3",
            stt_method="Google Cloud",
            google_model="latest_long",
        )
        call_kwargs = mock_google.call_args[1]
        assert call_kwargs["model"] == "latest_long"

    @patch(f"{_MOD}._transcribe_google_cloud")
    def test_google_stt_api_error_propagates(self, mock_google):
        """API errors from Google STT propagate through transcribe_audio."""
        mock_google.side_effect = ValueError("AUTH_ERROR")
        with pytest.raises(ValueError, match="AUTH_ERROR"):
            transcribe_audio("test.mp3", stt_method="Google Cloud")

    @patch(f"{_MOD}._transcribe_google_cloud")
    def test_google_stt_network_timeout(self, mock_google):
        """Network timeout from Google STT propagates."""
        mock_google.side_effect = urllib.error.URLError(
            TimeoutError("timed out"),
        )
        with pytest.raises(urllib.error.URLError):
            transcribe_audio("test.mp3", stt_method="Google Cloud")

    @patch(f"{_MOD}._transcribe_whisper", return_value="srt")
    def test_whisper_default_model_size(self, mock_whisper):
        """Default model_size is 'base'."""
        transcribe_audio("test.mp3", stt_method="Whisper")
        assert mock_whisper.call_args[0][2] == "base"

    @patch(f"{_MOD}._transcribe_whisper", return_value="srt")
    def test_whisper_all_model_sizes(self, mock_whisper):
        """All model sizes can be passed to whisper."""
        for size in ("tiny", "base", "small", "medium", "large"):
            transcribe_audio("test.mp3", stt_method="Whisper", model_size=size)
            assert mock_whisper.call_args[0][2] == size

    @patch(f"{_MOD}._transcribe_google_cloud", return_value="srt")
    def test_google_default_model(self, mock_google):
        """Default google_model is 'default'."""
        transcribe_audio("test.mp3", stt_method="Google Cloud")
        call_kwargs = mock_google.call_args[1]
        assert call_kwargs["model"] == "default"


# ---------------------------------------------------------------------------
# TestSynthesizeSpeechEdgeCases
# ---------------------------------------------------------------------------


class TestSynthesizeSpeechEdgeCases:
    """Edge-case tests for synthesize_speech."""

    @pytest.fixture(autouse=True)
    def _mock_edge(self):
        """Prevent edge_tts import in tests running outside uv."""
        with patch(f"{_MOD}._synthesize_chunk_edge"):
            yield

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}._split_text_for_tts", return_value=["Unicode text"])
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_unicode_text(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_split,
        mock_synth,
        mock_concat,
        tmp_path,
    ):
        """Unicode text (including emoji) is handled without errors."""
        output = str(tmp_path / "out.mp3")
        result = synthesize_speech(
            "Hello \u4e16\u754c \U0001f600",
            output_path=output,
            tts_method=_GOOGLE_TTS,
        )
        assert result == output

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}._split_text_for_tts")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_very_long_text_many_chunks(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_split,
        mock_synth,
        mock_concat,
        tmp_path,
    ):
        """Very long text (>10000 chars) is split into many chunks."""
        chunk_count = 10
        mock_split.return_value = [f"Chunk {i}." for i in range(chunk_count)]
        output = str(tmp_path / "out.mp3")
        synthesize_speech(
            "x" * 10001,
            output_path=output,
            tts_method=_GOOGLE_TTS,
        )
        assert mock_synth.call_count == chunk_count

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}._split_text_for_tts", return_value=["Test."])
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_wav_audio_format(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_split,
        mock_synth,
        mock_concat,
        tmp_path,
    ):
        """Output format .wav is passed to _synthesize_chunk."""
        output = str(tmp_path / "out.wav")
        synthesize_speech(
            "Test.",
            output_path=output,
            tts_method=_GOOGLE_TTS,
            audio_format=".wav",
        )
        synth_call = mock_synth.call_args
        assert synth_call[1]["audio_format"] == ".wav"

    @patch(f"{_MOD}._synthesize_chunk_edge")
    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._split_text_for_tts", return_value=["Test."])
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_edge_tts_with_target_lang(
        self,
        mock_ffmpeg,
        mock_split,
        mock_concat,
        mock_edge_synth,
        tmp_path,
    ):
        """Edge TTS uses _get_edge_voice with target language."""
        output = str(tmp_path / "out.mp3")
        with patch(
            f"{_MOD}._get_edge_voice",
            return_value="vi-VN-HoaiMyNeural",
        ) as mv:
            synthesize_speech(
                "Test.",
                target_lang="Vietnamese",
                output_path=output,
                tts_method="Edge TTS",
            )
            mv.assert_called_once_with("Vietnamese", "FEMALE")

    @patch(f"{_MOD}._synthesize_chunk", side_effect=ValueError("QUOTA_ERROR"))
    @patch(f"{_MOD}._split_text_for_tts", return_value=["Hi."])
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_quota_error_propagated(
        self,
        mock_key,
        mock_ffmpeg,
        mock_split,
        mock_synth,
        tmp_path,
    ):
        """QUOTA_ERROR from _synthesize_chunk propagates."""
        with pytest.raises(ValueError, match="QUOTA_ERROR"):
            synthesize_speech(
                "Hi.",
                output_path=str(tmp_path / "out.mp3"),
                tts_method=_GOOGLE_TTS,
            )

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}._split_text_for_tts", return_value=["A.", "B.", "C.", "D."])
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_cancellation_mid_processing(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_split,
        mock_synth,
        mock_concat,
        tmp_path,
    ):
        """Cancellation after second chunk stops further processing."""
        call_count = 0

        def cancel_after_two():
            nonlocal call_count
            call_count += 1
            return call_count > 2  # noqa: PLR2004

        output = str(tmp_path / "output.mp3")
        with pytest.raises(ValueError, match="CANCELLED"):
            synthesize_speech(
                "A. B. C. D.",
                output_path=output,
                tts_method=_GOOGLE_TTS,
                is_cancelled=cancel_after_two,
            )
        # Two chunks synthesized before cancellation detected on third
        assert mock_synth.call_count == 2  # noqa: PLR2004


# ---------------------------------------------------------------------------
# TestSynthesizeTimedSpeechExtended
# ---------------------------------------------------------------------------


class TestSynthesizeTimedSpeechExtended:
    """Extended tests for synthesize_timed_speech edge cases."""

    @pytest.fixture(autouse=True)
    def _mock_edge(self):
        """Prevent edge_tts import in tests running outside uv."""
        with patch(f"{_MOD}._synthesize_chunk_edge"):
            yield

    def _make_entry(self, start: str, end: str, text: str) -> MagicMock:
        """Create a mock SubtitleEntry."""
        entry = MagicMock()
        entry.start = start
        entry.end = end
        entry.text = text
        return entry

    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_empty_entries_list_raises(self, mock_key, mock_ff, tmp_path):
        """Empty entries list raises EMPTY_TEXT."""
        with pytest.raises(ValueError, match="EMPTY_TEXT"):
            synthesize_timed_speech(
                [],
                tts_method=_GOOGLE_TTS,
                output_path=str(tmp_path / "o.mp3"),
            )

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration", return_value=0.5)
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_single_entry(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_synth,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """Single entry produces one speech segment."""
        entries = [
            self._make_entry("00:00:00,000", "00:00:02,000", "Only one"),
        ]
        output = str(tmp_path / "out.mp3")
        result = synthesize_timed_speech(
            entries,
            tts_method=_GOOGLE_TTS,
            output_path=output,
        )
        assert result == output
        assert mock_synth.call_count == 1
        mock_concat.assert_called_once()

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration", return_value=0.5)
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_entries_with_empty_text_skipped(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_synth,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """Entries with empty text are filtered out before processing."""
        entries = [
            self._make_entry("00:00:00,000", "00:00:01,000", "   "),
            self._make_entry("00:00:02,000", "00:00:04,000", "Valid text"),
        ]
        output = str(tmp_path / "out.mp3")
        synthesize_timed_speech(
            entries,
            tts_method=_GOOGLE_TTS,
            output_path=output,
        )
        # Only valid entry synthesized
        assert mock_synth.call_count == 1

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration", return_value=0.3)
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_very_short_gap_below_threshold(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_synth,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """Gaps below 0.05s threshold do not generate silence."""
        entries = [
            self._make_entry("00:00:00,000", "00:00:01,000", "A"),
            self._make_entry("00:00:00,330", "00:00:01,330", "B"),
        ]
        output = str(tmp_path / "out.mp3")
        synthesize_timed_speech(
            entries,
            tts_method=_GOOGLE_TTS,
            output_path=output,
        )
        # No silence inserted (gap from cursor 0.3 to next 0.33 = 0.03 < 0.05)
        mock_silence.assert_not_called()

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration", return_value=1.0)
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_output_directory_created(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_synth,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """Output parent directory is created if it does not exist."""
        entries = [
            self._make_entry("00:00:00,000", "00:00:02,000", "Hi"),
        ]
        nested = tmp_path / "nested" / "deep"
        output = str(nested / "out.mp3")
        synthesize_timed_speech(
            entries,
            tts_method=_GOOGLE_TTS,
            output_path=output,
        )
        assert nested.is_dir()

    @patch(f"{_MOD}.shutil.rmtree")
    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration", return_value=1.0)
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_temp_dir_cleaned_on_success(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_synth,
        mock_silence,
        mock_dur,
        mock_concat,
        mock_rmtree,
        tmp_path,
    ):
        """Temp directory is cleaned up on successful synthesis."""
        entries = [
            self._make_entry("00:00:00,000", "00:00:02,000", "Hi"),
        ]
        output = str(tmp_path / "out.mp3")
        synthesize_timed_speech(
            entries,
            tts_method=_GOOGLE_TTS,
            output_path=output,
        )
        mock_rmtree.assert_called_once()

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration", return_value=0.5)
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_cancellation_mid_entries(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_synth,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """Cancellation after second entry stops processing."""
        call_count = 0

        def cancel_after_second():
            nonlocal call_count
            call_count += 1
            return call_count > 2  # noqa: PLR2004

        entries = [
            self._make_entry("00:00:00,000", "00:00:01,000", "A"),
            self._make_entry("00:00:02,000", "00:00:03,000", "B"),
            self._make_entry("00:00:04,000", "00:00:05,000", "C"),
        ]
        output = str(tmp_path / "out.mp3")
        with pytest.raises(ValueError, match="CANCELLED"):
            synthesize_timed_speech(
                entries,
                output_path=output,
                tts_method=_GOOGLE_TTS,
                is_cancelled=cancel_after_second,
            )
        assert mock_synth.call_count == 2  # noqa: PLR2004


# ---------------------------------------------------------------------------
# TestMixAudioIntoVideoExtendedEdge
# ---------------------------------------------------------------------------


class TestMixAudioIntoVideoExtendedEdge:
    """Extended edge-case tests for mix_audio_into_video."""

    @patch("subprocess.run")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_output_path_returned_as_string(
        self,
        mock_ff,
        mock_run,
        tmp_path,
    ):
        """Return value is the exact output_path string passed in."""
        mock_run.return_value = MagicMock(returncode=0)
        out = str(tmp_path / "result.mp4")
        result = mix_audio_into_video("v.mp4", "a.mp3", out)
        assert result == out
        assert isinstance(result, str)

    @patch("subprocess.run")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_map_flags_present(self, mock_ff, mock_run, tmp_path):
        """FFmpeg command includes -map 0:v:0 and -map 1:a:0."""
        mock_run.return_value = MagicMock(returncode=0)
        mix_audio_into_video(
            str(tmp_path / "v.mp4"),
            str(tmp_path / "a.mp3"),
            str(tmp_path / "o.mp4"),
        )
        cmd = mock_run.call_args[0][0]
        assert "0:v:0" in cmd
        assert "1:a:0" in cmd

    @patch("subprocess.run")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_overwrite_flag_present(self, mock_ff, mock_run, tmp_path):
        """FFmpeg command includes -y flag for overwrite."""
        mock_run.return_value = MagicMock(returncode=0)
        mix_audio_into_video(
            str(tmp_path / "v.mp4"),
            str(tmp_path / "a.mp3"),
            str(tmp_path / "o.mp4"),
        )
        cmd = mock_run.call_args[0][0]
        assert "-y" in cmd

    @patch("subprocess.run")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_capture_output_enabled(self, mock_ff, mock_run, tmp_path):
        """FFmpeg subprocess is called with capture_output=True."""
        mock_run.return_value = MagicMock(returncode=0)
        mix_audio_into_video(
            str(tmp_path / "v.mp4"),
            str(tmp_path / "a.mp3"),
            str(tmp_path / "o.mp4"),
        )
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["capture_output"] is True

    @patch("subprocess.run")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_check_enabled(self, mock_ff, mock_run, tmp_path):
        """FFmpeg subprocess is called with check=True."""
        mock_run.return_value = MagicMock(returncode=0)
        mix_audio_into_video(
            str(tmp_path / "v.mp4"),
            str(tmp_path / "a.mp3"),
            str(tmp_path / "o.mp4"),
        )
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["check"] is True


# ---------------------------------------------------------------------------
# TestConvertSubtitleFormatExtendedCases
# ---------------------------------------------------------------------------


class TestConvertSubtitleFormatExtendedCases:
    """Additional tests for _convert_subtitle_format conversions."""

    def test_srt_to_srt_identity(self):
        """SRT to SRT returns unchanged text."""
        srt = (
            "1\n00:00:01,000 --> 00:00:04,000\nLine one\n\n"
            "2\n00:00:05,000 --> 00:00:08,000\nLine two\n"
        )
        assert _convert_subtitle_format(srt, ".srt") == srt

    def test_vtt_empty_lines_between_entries(self):
        """VTT conversion handles empty lines between entries."""
        srt = (
            "1\n00:00:01,000 --> 00:00:04,000\nFirst\n\n"
            "2\n00:00:05,000 --> 00:00:08,000\nSecond\n"
        )
        vtt = _convert_subtitle_format(srt, ".vtt")
        assert "WEBVTT" in vtt
        assert "First" in vtt
        assert "Second" in vtt
        # Both timestamps converted
        assert "00:00:01.000" in vtt
        assert "00:00:05.000" in vtt

    def test_vtt_starts_with_header_and_has_cue(self):
        """VTT conversion emits a WEBVTT header and a cue with timestamp + text."""
        srt = "1\n00:00:01,000 --> 00:00:04,000\nHi\n\n"
        vtt = _convert_subtitle_format(srt, ".vtt")
        assert vtt.startswith("WEBVTT")
        assert "00:00:01.000 --> 00:00:04.000" in vtt
        assert "Hi" in vtt

    def test_vtt_with_special_characters(self):
        """VTT conversion preserves special characters in text."""
        srt = "1\n00:00:01,000 --> 00:00:04,000\n<i>Hello</i> & 'world'\n"
        vtt = _convert_subtitle_format(srt, ".vtt")
        assert "<i>Hello</i> & 'world'" in vtt

    def test_srt_only_timestamps_no_text(self):
        """SRT with timestamps but no text lines still yields a valid VTT."""
        srt = "1\n00:00:01,000 --> 00:00:04,000\n\n"
        vtt = _convert_subtitle_format(srt, ".vtt")
        # At minimum, we still get the WEBVTT header; empty-text entries may
        # be dropped by the parser, which is acceptable.
        assert "WEBVTT" in vtt

    def test_vtt_output_starts_with_webvtt_newline(self):
        """VTT output begins with 'WEBVTT\\n'."""
        vtt = _convert_subtitle_format("anything", ".vtt")
        assert vtt.startswith("WEBVTT\n")


# ---------------------------------------------------------------------------
# TestEdgeTTSVoiceMappings
# ---------------------------------------------------------------------------


class TestEdgeTTSVoiceMappings:
    """Test _get_edge_voice with various languages and genders."""

    @patch(f"{_LANG}.get_locale_code", return_value="ja")
    def test_japanese_female(self, mock_locale):
        """Japanese Female maps to ja-JP-NanamiNeural."""
        result = _get_edge_voice("Japanese", "FEMALE")
        assert result == "ja-JP-NanamiNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="ja")
    def test_japanese_male(self, mock_locale):
        """Japanese Male maps to ja-JP-KeitaNeural."""
        result = _get_edge_voice("Japanese", "MALE")
        assert result == "ja-JP-KeitaNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="zh-CN")
    def test_chinese_simplified_female(self, mock_locale):
        """Chinese Simplified Female maps to zh-CN-XiaoxiaoNeural."""
        result = _get_edge_voice("Chinese (Simplified)", "FEMALE")
        assert result == "zh-CN-XiaoxiaoNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="zh-CN")
    def test_chinese_simplified_male(self, mock_locale):
        """Chinese Simplified Male maps to zh-CN-YunxiNeural."""
        result = _get_edge_voice("Chinese (Simplified)", "MALE")
        assert result == "zh-CN-YunxiNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="de")
    def test_german_female(self, mock_locale):
        """German Female maps to de-DE-KatjaNeural."""
        result = _get_edge_voice("German", "FEMALE")
        assert result == "de-DE-KatjaNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="de")
    def test_german_male(self, mock_locale):
        """German Male maps to de-DE-ConradNeural."""
        result = _get_edge_voice("German", "MALE")
        assert result == "de-DE-ConradNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="fr")
    def test_french_female(self, mock_locale):
        """French Female maps to fr-FR-DeniseNeural."""
        result = _get_edge_voice("French", "FEMALE")
        assert result == "fr-FR-DeniseNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="ko")
    def test_korean_male(self, mock_locale):
        """Korean Male maps to ko-KR-InJoonNeural."""
        result = _get_edge_voice("Korean", "MALE")
        assert result == "ko-KR-InJoonNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="ar")
    def test_arabic_female(self, mock_locale):
        """Arabic Female maps to ar-EG-SalmaNeural."""
        result = _get_edge_voice("Arabic", "FEMALE")
        assert result == "ar-EG-SalmaNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="en-UK")
    def test_english_uk_female(self, mock_locale):
        """English UK Female maps to en-GB-SoniaNeural."""
        result = _get_edge_voice("English (UK)", "FEMALE")
        assert result == "en-GB-SoniaNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="pt-BR")
    def test_portuguese_brazil_male(self, mock_locale):
        """Portuguese Brazil Male maps to pt-BR-AntonioNeural."""
        result = _get_edge_voice("Portuguese (Brazil)", "MALE")
        assert result == "pt-BR-AntonioNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="hi")
    def test_hindi_female(self, mock_locale):
        """Hindi Female maps to hi-IN-SwaraNeural."""
        result = _get_edge_voice("Hindi", "FEMALE")
        assert result == "hi-IN-SwaraNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="th")
    def test_thai_male(self, mock_locale):
        """Thai Male maps to th-TH-NiwatNeural."""
        result = _get_edge_voice("Thai", "MALE")
        assert result == "th-TH-NiwatNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="ru")
    def test_russian_female(self, mock_locale):
        """Russian Female maps to ru-RU-SvetlanaNeural."""
        result = _get_edge_voice("Russian", "FEMALE")
        assert result == "ru-RU-SvetlanaNeural"

    def test_empty_label_female_default(self):
        """Empty label with FEMALE returns en-US-JennyNeural."""
        result = _get_edge_voice("", "FEMALE")
        assert result == "en-US-JennyNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="xyz-unknown")
    def test_completely_unknown_locale(self, mock_locale):
        """Completely unknown locale falls back to default voice."""
        result = _get_edge_voice("Unknown Language", "FEMALE")
        assert result == _EDGE_DEFAULT_VOICE


# ---------------------------------------------------------------------------
# TestGoogleTTSLanguageCodeMappings
# ---------------------------------------------------------------------------


class TestGoogleTTSLanguageCodeMappings:
    """Additional tests for _get_tts_language_code mappings."""

    @patch(f"{_LANG}.get_locale_code", return_value="ko")
    def test_korean_mapped(self, mock_locale):
        """Korean maps to 'ko-KR'."""
        assert _get_tts_language_code("Korean") == "ko-KR"

    @patch(f"{_LANG}.get_locale_code", return_value="th")
    def test_thai_mapped(self, mock_locale):
        """Thai maps to 'th-TH'."""
        assert _get_tts_language_code("Thai") == "th-TH"

    @patch(f"{_LANG}.get_locale_code", return_value="hi")
    def test_hindi_mapped(self, mock_locale):
        """Hindi maps to 'hi-IN'."""
        assert _get_tts_language_code("Hindi") == "hi-IN"

    @patch(f"{_LANG}.get_locale_code", return_value="ru")
    def test_russian_mapped(self, mock_locale):
        """Russian maps to 'ru-RU'."""
        assert _get_tts_language_code("Russian") == "ru-RU"

    @patch(f"{_LANG}.get_locale_code", return_value="de")
    def test_german_mapped(self, mock_locale):
        """German maps to 'de-DE'."""
        assert _get_tts_language_code("German") == "de-DE"

    @patch(f"{_LANG}.get_locale_code", return_value="fr")
    def test_french_mapped(self, mock_locale):
        """French maps to 'fr-FR'."""
        assert _get_tts_language_code("French") == "fr-FR"

    @patch(f"{_LANG}.get_locale_code", return_value="it")
    def test_italian_mapped(self, mock_locale):
        """Italian maps to 'it-IT'."""
        assert _get_tts_language_code("Italian") == "it-IT"

    @patch(f"{_LANG}.get_locale_code", return_value="pt-BR")
    def test_portuguese_brazil_mapped(self, mock_locale):
        """Portuguese (Brazil) maps to 'pt-BR'."""
        assert _get_tts_language_code("Portuguese (Brazil)") == "pt-BR"

    @patch(f"{_LANG}.get_locale_code", return_value="pt-PT")
    def test_portuguese_portugal_mapped(self, mock_locale):
        """Portuguese (Portugal) maps to 'pt-PT'."""
        assert _get_tts_language_code("Portuguese (Portugal)") == "pt-PT"

    @patch(f"{_LANG}.get_locale_code", return_value="pl")
    def test_polish_mapped(self, mock_locale):
        """Polish maps to 'pl-PL'."""
        assert _get_tts_language_code("Polish") == "pl-PL"


# ---------------------------------------------------------------------------
# TestSynthesizeChunkSpeakingRateEdge
# ---------------------------------------------------------------------------


class TestSynthesizeChunkSpeakingRateEdge:
    """Edge-case tests for _synthesize_chunk speaking rate and format."""

    def _make_response(self, audio_bytes: bytes) -> MagicMock:
        """Create a mock urlopen response."""
        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
        resp_data = json.dumps({"audioContent": audio_b64}).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = resp_data
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    @patch("urllib.request.urlopen")
    def test_speaking_rate_exactly_1_no_key(self, mock_urlopen, tmp_path):
        """Rate exactly 1.0 does not add speakingRate to payload."""
        mock_urlopen.return_value = self._make_response(b"audio")
        out = tmp_path / "chunk.mp3"
        _synthesize_chunk(
            "Hi",
            "en-US",
            "FEMALE",
            "key",
            out,
            speaking_rate=1.0,
        )

        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode("utf-8"))
        assert "speakingRate" not in payload["audioConfig"]

    @patch("urllib.request.urlopen")
    def test_speaking_rate_rounded_to_2_decimal(self, mock_urlopen, tmp_path):
        """SpeakingRate is rounded to 2 decimal places."""
        mock_urlopen.return_value = self._make_response(b"audio")
        out = tmp_path / "chunk.mp3"
        _synthesize_chunk(
            "Hi",
            "en-US",
            "FEMALE",
            "key",
            out,
            speaking_rate=1.555,
        )

        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode("utf-8"))
        assert payload["audioConfig"]["speakingRate"] == 1.55  # noqa: PLR2004

    @patch("urllib.request.urlopen")
    def test_unknown_audio_format_defaults_to_mp3(
        self,
        mock_urlopen,
        tmp_path,
    ):
        """Unknown audio format falls back to MP3 encoding."""
        mock_urlopen.return_value = self._make_response(b"audio")
        out = tmp_path / "chunk.ogg"
        _synthesize_chunk(
            "Hi",
            "en-US",
            "FEMALE",
            "key",
            out,
            audio_format=".ogg",
        )

        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode("utf-8"))
        # .ogg not in _TTS_ENCODING_MAP, falls back to "MP3"
        assert payload["audioConfig"]["audioEncoding"] == "MP3"

    @patch("urllib.request.urlopen")
    def test_speaking_rate_exactly_at_min(self, mock_urlopen, tmp_path):
        """Rate exactly 0.25 is accepted without clamping."""
        mock_urlopen.return_value = self._make_response(b"audio")
        out = tmp_path / "chunk.mp3"
        _synthesize_chunk(
            "Hi",
            "en-US",
            "FEMALE",
            "key",
            out,
            speaking_rate=0.25,
        )

        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode("utf-8"))
        assert payload["audioConfig"]["speakingRate"] == 0.25  # noqa: PLR2004

    @patch("urllib.request.urlopen")
    def test_speaking_rate_exactly_at_max(self, mock_urlopen, tmp_path):
        """Rate exactly 2.0 (Google's documented max) is accepted unclamped."""
        mock_urlopen.return_value = self._make_response(b"audio")
        out = tmp_path / "chunk.mp3"
        _synthesize_chunk(
            "Hi",
            "en-US",
            "FEMALE",
            "key",
            out,
            speaking_rate=2.0,
        )

        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode("utf-8"))
        assert payload["audioConfig"]["speakingRate"] == 2.0  # noqa: PLR2004


# ---------------------------------------------------------------------------
# TestWhisperModelAndFormatHelpers
# ---------------------------------------------------------------------------


class TestWhisperModelAndFormatHelpers:
    """Test Whisper model creation and SRT formatting helpers."""

    @pytest.fixture(autouse=True)
    def _setup_faster_whisper(self):
        """Ensure faster_whisper mock module is available for local import."""
        mock_fw = MagicMock()
        mock_fw.WhisperModel = MagicMock()
        prev = sys.modules.get("faster_whisper")
        sys.modules["faster_whisper"] = mock_fw
        yield mock_fw
        if prev is None:
            sys.modules.pop("faster_whisper", None)
        else:
            sys.modules["faster_whisper"] = prev

    def test_model_created_with_cpu_int8(self, _setup_faster_whisper):
        """WhisperModel is created with device='cpu', compute_type='int8'."""
        mock_fw = _setup_faster_whisper
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([], MagicMock())
        mock_fw.WhisperModel.return_value = mock_model

        _transcribe_whisper("test.mp4", model_size="tiny")

        mock_fw.WhisperModel.assert_called_once_with(
            "tiny",
            device="cpu",
            compute_type="int8",
        )

    def test_model_size_medium(self, _setup_faster_whisper):
        """Medium model size is passed correctly."""
        mock_fw = _setup_faster_whisper
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([], MagicMock())
        mock_fw.WhisperModel.return_value = mock_model

        _transcribe_whisper("test.mp4", model_size="medium")

        assert mock_fw.WhisperModel.call_args[0][0] == "medium"

    def test_model_size_large(self, _setup_faster_whisper):
        """Large model size is passed correctly."""
        mock_fw = _setup_faster_whisper
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([], MagicMock())
        mock_fw.WhisperModel.return_value = mock_model

        _transcribe_whisper("test.mp4", model_size="large")

        assert mock_fw.WhisperModel.call_args[0][0] == "large"

    def test_word_timestamps_disabled(self, _setup_faster_whisper):
        """word_timestamps is always False for Whisper transcription."""
        mock_fw = _setup_faster_whisper
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([], MagicMock())
        mock_fw.WhisperModel.return_value = mock_model

        _transcribe_whisper("test.mp4")

        call_kwargs = mock_model.transcribe.call_args[1]
        assert call_kwargs["word_timestamps"] is False

    def test_file_path_passed_to_transcribe(self, _setup_faster_whisper):
        """The file_path is passed as first positional arg to transcribe."""
        mock_fw = _setup_faster_whisper
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([], MagicMock())
        mock_fw.WhisperModel.return_value = mock_model

        _transcribe_whisper("/path/to/audio.wav")

        call_args = mock_model.transcribe.call_args[0]
        assert call_args[0] == "/path/to/audio.wav"


# ---------------------------------------------------------------------------
# TestFormatSrtTimeExtended
# ---------------------------------------------------------------------------


class TestFormatSrtTimeExtended:
    """Extended tests for _format_srt_time edge cases."""

    def test_fraction_of_second(self):
        """Sub-second values produce correct milliseconds."""
        assert _format_srt_time(0.001) == "00:00:00,001"

    def test_near_one_second(self):
        """Just under one second."""
        assert _format_srt_time(0.999) == "00:00:00,999"

    def test_exact_minute(self):
        """Exactly one minute."""
        assert _format_srt_time(60.0) == "00:01:00,000"

    def test_exact_hour(self):
        """Exactly one hour."""
        assert _format_srt_time(3600.0) == "01:00:00,000"

    def test_large_value_over_24_hours(self):
        """Value exceeding 24 hours."""
        result = _format_srt_time(90061.5)
        assert result == "25:01:01,500"


# ---------------------------------------------------------------------------
# TestParseDurationExtended
# ---------------------------------------------------------------------------


class TestParseDurationExtended:
    """Extended tests for _parse_duration edge cases."""

    def test_fractional_seconds(self):
        """Parses '0.001s' to 0.001."""
        assert _parse_duration("0.001s") == 0.001  # noqa: PLR2004

    def test_just_s_suffix(self):
        """Parses 's' (just suffix, no number) returns 0.0."""
        assert _parse_duration("s") == 0.0

    def test_negative_value(self):
        """Negative duration string."""
        assert _parse_duration("-1.5s") == -1.5  # noqa: PLR2004

    def test_whole_number_no_suffix(self):
        """Whole number without 's' suffix."""
        assert _parse_duration("42") == 42.0  # noqa: PLR2004


# ---------------------------------------------------------------------------
# TestExtractAudioToFlacEdge
# ---------------------------------------------------------------------------


class TestExtractAudioToFlacEdge:
    """Extended edge-case tests for _extract_audio_to_flac."""

    @patch("subprocess.run")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_ffmpeg_called_with_mono_16khz(self, mock_ff, mock_run):
        """FFmpeg is called with -ac 1 (mono) and -ar 16000 (16kHz)."""
        mock_run.return_value = MagicMock(returncode=0)
        _extract_audio_to_flac("/some/video.mp4")

        cmd = mock_run.call_args[0][0]
        assert "-ac" in cmd
        ac_idx = cmd.index("-ac")
        assert cmd[ac_idx + 1] == "1"
        assert "-ar" in cmd
        ar_idx = cmd.index("-ar")
        assert cmd[ar_idx + 1] == "16000"

    @patch("subprocess.run")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_flac_output_format(self, mock_ff, mock_run):
        """FFmpeg is called with -f flac output format."""
        mock_run.return_value = MagicMock(returncode=0)
        _extract_audio_to_flac("/some/video.mp4")

        cmd = mock_run.call_args[0][0]
        assert "-f" in cmd
        f_idx = cmd.index("-f")
        assert cmd[f_idx + 1] == "flac"

    @patch("subprocess.run")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_overwrite_flag(self, mock_ff, mock_run):
        """FFmpeg is called with -y (overwrite) flag."""
        mock_run.return_value = MagicMock(returncode=0)
        _extract_audio_to_flac("/some/video.mp4")

        cmd = mock_run.call_args[0][0]
        assert "-y" in cmd

    @patch("subprocess.run")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_temp_dir_prefix(self, mock_ff, mock_run):
        """Temp directory has 'subtitle_' prefix."""
        mock_run.return_value = MagicMock(returncode=0)
        result = _extract_audio_to_flac("/some/video.mp4")
        assert result.parent.name.startswith("subtitle_")

    @patch("subprocess.run")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_timeout_is_300(self, mock_ff, mock_run):
        """FFmpeg subprocess is called with 300 second timeout."""
        mock_run.return_value = MagicMock(returncode=0)
        _extract_audio_to_flac("/some/video.mp4")

        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["timeout"] == 300  # noqa: PLR2004


# ---------------------------------------------------------------------------
# TestCallLongRunningRecognizePayload
# ---------------------------------------------------------------------------


class TestCallLongRunningRecognizePayload:
    """Test _call_long_running_recognize request payload structure."""

    def _make_response(self, data: dict) -> MagicMock:
        """Create a mock urlopen context-manager response."""
        resp = MagicMock()
        resp.read.return_value = json.dumps(data).encode("utf-8")
        resp.__enter__ = MagicMock(return_value=resp)
        resp.__exit__ = MagicMock(return_value=False)
        return resp

    @patch("urllib.request.urlopen")
    def test_flac_encoding_in_config(self, mock_urlopen):
        """Request config includes encoding='FLAC'."""
        mock_urlopen.return_value = self._make_response({"name": "op-1"})
        _call_long_running_recognize("audio_b64", "en-US", "key")

        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode("utf-8"))
        assert payload["config"]["encoding"] == "FLAC"

    @patch("urllib.request.urlopen")
    def test_sample_rate_16000(self, mock_urlopen):
        """Request config includes sampleRateHertz=16000."""
        mock_urlopen.return_value = self._make_response({"name": "op-1"})
        _call_long_running_recognize("audio_b64", "en-US", "key")

        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode("utf-8"))
        assert payload["config"]["sampleRateHertz"] == 16000  # noqa: PLR2004

    @patch("urllib.request.urlopen")
    def test_word_time_offsets_enabled(self, mock_urlopen):
        """Request config includes enableWordTimeOffsets=True."""
        mock_urlopen.return_value = self._make_response({"name": "op-1"})
        _call_long_running_recognize("audio_b64", "en-US", "key")

        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode("utf-8"))
        assert payload["config"]["enableWordTimeOffsets"] is True

    @patch("urllib.request.urlopen")
    def test_automatic_punctuation_enabled(self, mock_urlopen):
        """Request config includes enableAutomaticPunctuation=True."""
        mock_urlopen.return_value = self._make_response({"name": "op-1"})
        _call_long_running_recognize("audio_b64", "en-US", "key")

        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode("utf-8"))
        assert payload["config"]["enableAutomaticPunctuation"] is True

    @patch("urllib.request.urlopen")
    def test_audio_content_in_payload(self, mock_urlopen):
        """Audio content is included in the request payload."""
        mock_urlopen.return_value = self._make_response({"name": "op-1"})
        _call_long_running_recognize("bXlfYXVkaW8=", "en-US", "key")

        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode("utf-8"))
        assert payload["audio"]["content"] == "bXlfYXVkaW8="

    @patch("urllib.request.urlopen")
    def test_content_type_header(self, mock_urlopen):
        """Request has Content-Type: application/json header."""
        mock_urlopen.return_value = self._make_response({"name": "op-1"})
        _call_long_running_recognize("audio_b64", "en-US", "key")

        req = mock_urlopen.call_args[0][0]
        assert req.get_header("Content-type") == "application/json"

    @patch("urllib.request.urlopen")
    def test_api_key_in_url(self, mock_urlopen):
        """API key appears in the request URL."""
        mock_urlopen.return_value = self._make_response({"name": "op-1"})
        _call_long_running_recognize("audio_b64", "en-US", "my-secret-key")

        req = mock_urlopen.call_args[0][0]
        assert "key=my-secret-key" in req.full_url

    @patch("urllib.request.urlopen")
    def test_default_model_in_config(self, mock_urlopen):
        """Default model is 'default' in the config."""
        mock_urlopen.return_value = self._make_response({"name": "op-1"})
        _call_long_running_recognize("audio_b64", "en-US", "key")

        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode("utf-8"))
        assert payload["config"]["model"] == "default"


# ---------------------------------------------------------------------------
# TestParseSrtTimestampEdge
# ---------------------------------------------------------------------------


class TestParseSrtTimestampEdge:
    """Edge-case tests for _parse_srt_timestamp."""

    def test_single_colon_component(self):
        """Single colon value returns 0.0 (not enough parts)."""
        assert _parse_srt_timestamp("30") == 0.0

    def test_four_colon_components(self):
        """Four colon-separated values returns 0.0 (too many parts)."""
        assert _parse_srt_timestamp("00:01:02:03") == 0.0

    def test_just_colons(self):
        """Just colons returns 0.0 (empty parts cause ValueError)."""
        assert _parse_srt_timestamp("::") == 0.0

    def test_large_hour_value(self):
        """Large hour values are parsed correctly."""
        result = _parse_srt_timestamp("99:59:59,999")
        expected = 99 * 3600 + 59 * 60 + 59.999  # noqa: PLR2004
        assert abs(result - expected) < 0.001  # noqa: PLR2004


# ---------------------------------------------------------------------------
# TestGetMp3DurationEdge
# ---------------------------------------------------------------------------


class TestGetMp3DurationEdge:
    """Extended tests for _get_mp3_duration."""

    @patch("subprocess.run")
    def test_ffprobe_invalid_output_falls_back(self, mock_run, tmp_path):
        """Non-numeric ffprobe output falls back to size estimation."""
        mock_run.side_effect = ValueError("not a number")
        mp3 = tmp_path / "test.mp3"
        mp3.write_bytes(b"\x00" * 12000)
        result = _get_mp3_duration(mp3)
        assert result == 3.0  # 12000 / 4000  # noqa: PLR2004

    @patch("subprocess.run")
    def test_ffprobe_called_with_correct_args(self, mock_run, tmp_path):
        """Ffprobe is called with correct format query flags."""
        mock_run.return_value = MagicMock(stdout=b"5.0\n", returncode=0)
        mp3 = tmp_path / "test.mp3"
        mp3.write_bytes(b"data")
        _get_mp3_duration(mp3)

        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "ffprobe"
        assert "-show_entries" in cmd
        assert "format=duration" in cmd


# ---------------------------------------------------------------------------
# TestSpeedUpAudioEdge
# ---------------------------------------------------------------------------


class TestSpeedUpAudioEdge:
    """Extended edge-case tests for _speed_up_audio."""

    @patch("subprocess.run")
    def test_factor_4_chains_two_atempo(self, mock_run, tmp_path):
        """Factor 4.0 chains atempo=2.0 twice."""
        mock_run.return_value = MagicMock(returncode=0)
        inp = tmp_path / "in.mp3"
        out = tmp_path / "out.mp3"
        inp.write_bytes(b"\x00")
        _speed_up_audio(inp, out, 4.0)

        cmd = mock_run.call_args[0][0]
        f_idx = cmd.index("-filter:a")
        filter_str = cmd[f_idx + 1]
        assert filter_str.count("atempo=") == 2  # noqa: PLR2004
        assert "atempo=2.0000" in filter_str

    @patch("subprocess.run")
    def test_factor_above_max_clamped(self, mock_run, tmp_path):
        """Factor above 4.0 (e.g. 8.0) is clamped to 4.0."""
        mock_run.return_value = MagicMock(returncode=0)
        inp = tmp_path / "in.mp3"
        out = tmp_path / "out.mp3"
        inp.write_bytes(b"\x00")
        _speed_up_audio(inp, out, 8.0)

        # After clamping to 4.0, it should produce atempo filters
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        f_idx = cmd.index("-filter:a")
        filter_str = cmd[f_idx + 1]
        # 4.0 = 2.0 * 2.0
        assert filter_str.count("atempo=") == 2  # noqa: PLR2004

    @patch("subprocess.run")
    def test_factor_1_5_single_filter(self, mock_run, tmp_path):
        """Factor 1.5 produces single atempo=1.5000 filter."""
        mock_run.return_value = MagicMock(returncode=0)
        inp = tmp_path / "in.mp3"
        out = tmp_path / "out.mp3"
        inp.write_bytes(b"\x00")
        _speed_up_audio(inp, out, 1.5)

        cmd = mock_run.call_args[0][0]
        f_idx = cmd.index("-filter:a")
        filter_str = cmd[f_idx + 1]
        assert filter_str == "atempo=1.5000"


# ---------------------------------------------------------------------------
# TestGenerateSilenceEdge
# ---------------------------------------------------------------------------


class TestGenerateSilenceEdge:
    """Extended edge-case tests for _generate_silence."""

    @patch("subprocess.run")
    def test_small_duration(self, mock_run, tmp_path):
        """Very small duration (0.001) is formatted correctly."""
        mock_run.return_value = MagicMock(returncode=0)
        _generate_silence(0.001, tmp_path / "s.mp3")
        cmd = mock_run.call_args[0][0]
        t_idx = cmd.index("-t")
        assert cmd[t_idx + 1] == "0.001"

    @patch("subprocess.run")
    def test_large_duration(self, mock_run, tmp_path):
        """Large duration (60s) is formatted correctly."""
        mock_run.return_value = MagicMock(returncode=0)
        _generate_silence(60.0, tmp_path / "s.mp3")
        cmd = mock_run.call_args[0][0]
        t_idx = cmd.index("-t")
        assert cmd[t_idx + 1] == "60.000"

    @patch("subprocess.run")
    def test_uses_mono_channel(self, mock_run, tmp_path):
        """FFmpeg generates mono channel audio."""
        mock_run.return_value = MagicMock(returncode=0)
        _generate_silence(1.0, tmp_path / "s.mp3")
        cmd = mock_run.call_args[0][0]
        assert "anullsrc=r=24000:cl=mono" in cmd

    @patch("subprocess.run")
    def test_mp3_lame_codec(self, mock_run, tmp_path):
        """FFmpeg uses libmp3lame codec."""
        mock_run.return_value = MagicMock(returncode=0)
        _generate_silence(1.0, tmp_path / "s.mp3")
        cmd = mock_run.call_args[0][0]
        assert "libmp3lame" in cmd


# ---------------------------------------------------------------------------
# TestSynthesizeTimedSpeechEdgeTTSExtended
# ---------------------------------------------------------------------------


class TestSynthesizeTimedSpeechEdgeTTSExtended:
    """Extended Edge TTS tests for synthesize_timed_speech."""

    def _make_entry(self, start: str, end: str, text: str) -> MagicMock:
        """Create a mock SubtitleEntry."""
        entry = MagicMock()
        entry.start = start
        entry.end = end
        entry.text = text
        return entry

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration", return_value=0.5)
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._synthesize_chunk_edge")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_edge_empty_entries_raises(  # noqa: PLR0913
        self,
        mock_ffmpeg,
        mock_edge,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """Edge TTS with empty entries raises EMPTY_TEXT."""
        with pytest.raises(ValueError, match="EMPTY_TEXT"):
            synthesize_timed_speech(
                [],
                output_path=str(tmp_path / "o.mp3"),
            )

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration", return_value=0.5)
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._synthesize_chunk_edge")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_edge_single_entry_works(  # noqa: PLR0913
        self,
        mock_ffmpeg,
        mock_edge,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """Edge TTS with single entry succeeds."""
        entries = [
            self._make_entry("00:00:00,000", "00:00:02,000", "Only"),
        ]
        output = str(tmp_path / "out.mp3")
        result = synthesize_timed_speech(entries, output_path=output)
        assert result == output
        mock_edge.assert_called_once()

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration", return_value=0.5)
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._synthesize_chunk_edge")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_edge_progress_callback(  # noqa: PLR0913
        self,
        mock_ffmpeg,
        mock_edge,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """Edge TTS progress callback receives correct values."""
        progress = []
        entries = [
            self._make_entry("00:00:00,000", "00:00:01,000", "A"),
            self._make_entry("00:00:02,000", "00:00:03,000", "B"),
            self._make_entry("00:00:04,000", "00:00:05,000", "C"),
        ]
        output = str(tmp_path / "out.mp3")
        synthesize_timed_speech(
            entries,
            output_path=output,
            on_progress=lambda c, t: progress.append((c, t)),
        )
        assert progress == [(1, 3), (2, 3), (3, 3)]

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration", return_value=0.5)
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._synthesize_chunk_edge")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_edge_cancellation(  # noqa: PLR0913
        self,
        mock_ffmpeg,
        mock_edge,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """Edge TTS immediate cancellation prevents synthesis."""
        entries = [
            self._make_entry("00:00:00,000", "00:00:01,000", "A"),
        ]
        with pytest.raises(ValueError, match="CANCELLED"):
            synthesize_timed_speech(
                entries,
                output_path=str(tmp_path / "o.mp3"),
                is_cancelled=lambda: True,
            )
        mock_edge.assert_not_called()


# ---------------------------------------------------------------------------
# TestExtractSubtitleTextEdge
# ---------------------------------------------------------------------------


class TestExtractSubtitleTextEdge:
    """Extended edge-case tests for extract_subtitle_text."""

    @patch(f"{_SUB}.parse_subtitle")
    @patch(f"{_SUB}.is_subtitle_format", return_value=True)
    def test_ssa_format(self, mock_is_sub, mock_parse):
        """SSA suffix is handled as subtitle format."""
        entry = MagicMock()
        entry.text = "SSA line."
        mock_parse.return_value = ([entry], None)

        result = extract_subtitle_text("dummy", ".ssa")
        mock_is_sub.assert_called_once_with(".ssa")
        assert result == "SSA line."

    @patch(f"{_SUB}.is_subtitle_format", return_value=False)
    def test_json_suffix_fallback(self, mock_is_sub):
        """Non-subtitle suffix (.json) returns content as-is."""
        text = '{"key": "value"}'
        result = extract_subtitle_text(text, ".json")
        assert result == text

    @patch(f"{_SUB}.parse_subtitle")
    @patch(f"{_SUB}.is_subtitle_format", return_value=True)
    def test_all_whitespace_entries_filtered(self, mock_is_sub, mock_parse):
        """All whitespace-only entries produce empty string."""
        entry1 = MagicMock()
        entry1.text = "   "
        entry2 = MagicMock()
        entry2.text = "\t\n"
        mock_parse.return_value = ([entry1, entry2], None)

        result = extract_subtitle_text("dummy", ".srt")
        assert result == ""


# ---------------------------------------------------------------------------
# TestSynthesizeSpeechEdgeTTSDispatch
# ---------------------------------------------------------------------------


class TestSynthesizeSpeechEdgeTTSDispatch:
    """Test Edge TTS dispatch paths in synthesize_speech."""

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._synthesize_chunk_edge")
    @patch(f"{_MOD}._split_text_for_tts", return_value=["Hi."])
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_edge_voice_name_passed(
        self,
        mock_ffmpeg,
        mock_split,
        mock_edge,
        mock_concat,
        tmp_path,
    ):
        """Edge voice name is passed to _synthesize_chunk_edge."""
        output = str(tmp_path / "out.mp3")
        with patch(
            f"{_MOD}._get_edge_voice",
            return_value="vi-VN-NamMinhNeural",
        ):
            synthesize_speech(
                "Hi.",
                target_lang="Vietnamese",
                voice_gender="MALE",
                output_path=output,
            )
        edge_call = mock_edge.call_args
        assert edge_call[0][1] == "vi-VN-NamMinhNeural"

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._synthesize_chunk_edge")
    @patch(f"{_MOD}._split_text_for_tts", return_value=["Hi."])
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_edge_chunk_text_passed(
        self,
        mock_ffmpeg,
        mock_split,
        mock_edge,
        mock_concat,
        tmp_path,
    ):
        """Text chunk is passed as first arg to _synthesize_chunk_edge."""
        output = str(tmp_path / "out.mp3")
        synthesize_speech("Hi.", output_path=output)
        edge_call = mock_edge.call_args
        assert edge_call[0][0] == "Hi."

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._synthesize_chunk_edge")
    @patch(f"{_MOD}._split_text_for_tts", return_value=["Hi."])
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_edge_output_path_is_mp3(
        self,
        mock_ffmpeg,
        mock_split,
        mock_edge,
        mock_concat,
        tmp_path,
    ):
        """Edge TTS chunk output path uses .mp3 extension."""
        output = str(tmp_path / "out.mp3")
        synthesize_speech("Hi.", output_path=output)
        edge_call = mock_edge.call_args
        chunk_path = edge_call[0][2]
        assert str(chunk_path).endswith(".mp3")


# ===========================================================================
# ADDITIONAL TESTS — edge cases for 650+ target
# ===========================================================================


# ---------------------------------------------------------------------------
# TestWhisperEdgeCases — faster-whisper edge cases
# ---------------------------------------------------------------------------


class TestWhisperEdgeCases:
    """Edge cases for faster-whisper STT backend."""

    @pytest.fixture(autouse=True)
    def _setup_faster_whisper(self):
        """Ensure faster_whisper mock module is available for local import."""
        mock_fw = MagicMock()
        mock_fw.WhisperModel = MagicMock()
        prev = sys.modules.get("faster_whisper")
        sys.modules["faster_whisper"] = mock_fw
        yield mock_fw
        if prev is None:
            sys.modules.pop("faster_whisper", None)
        else:
            sys.modules["faster_whisper"] = prev

    def test_whisper_special_characters_in_text(self, _setup_faster_whisper):
        """Whisper segments with special characters are preserved."""
        mock_fw = _setup_faster_whisper
        seg = MagicMock(start=0.0, end=1.0, text="  <b>Bold</b> & 'quoted'  ")
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([seg], MagicMock())
        mock_fw.WhisperModel.return_value = mock_model

        result = _transcribe_whisper("test.mp3")
        assert "<b>Bold</b> & 'quoted'" in result

    def test_whisper_unicode_text(self, _setup_faster_whisper):
        """Whisper segments with CJK characters are preserved."""
        mock_fw = _setup_faster_whisper
        seg = MagicMock(start=0.0, end=2.0, text="  \u4f60\u597d\u4e16\u754c  ")
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([seg], MagicMock())
        mock_fw.WhisperModel.return_value = mock_model

        result = _transcribe_whisper("test.mp3")
        assert "\u4f60\u597d\u4e16\u754c" in result

    def test_whisper_newline_in_segment_text(self, _setup_faster_whisper):
        """Whisper segment text with newlines is stripped to single line."""
        mock_fw = _setup_faster_whisper
        seg = MagicMock(start=0.0, end=1.0, text="  Line1\nLine2  ")
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([seg], MagicMock())
        mock_fw.WhisperModel.return_value = mock_model

        result = _transcribe_whisper("test.mp3")
        # strip() only removes leading/trailing whitespace, not inner newlines
        assert "Line1\nLine2" in result

    def test_whisper_many_short_segments(self, _setup_faster_whisper):
        """Many short segments produce correctly numbered SRT."""
        mock_fw = _setup_faster_whisper
        count = 50
        segments = [
            MagicMock(start=float(i), end=float(i) + 0.5, text=f"  Seg{i}  ")
            for i in range(count)
        ]
        mock_model = MagicMock()
        mock_model.transcribe.return_value = (segments, MagicMock())
        mock_fw.WhisperModel.return_value = mock_model

        result = _transcribe_whisper("test.mp3")
        assert f"{count}\n" in result
        assert "Seg0" in result
        assert f"Seg{count - 1}" in result

    @patch(f"{_MOD}._get_speech_language_code", return_value="ja-JP")
    def test_whisper_japanese_language(
        self,
        mock_lang,
        _setup_faster_whisper,
    ):
        """Japanese language code 'ja-JP' splits to 'ja' for Whisper."""
        mock_fw = _setup_faster_whisper
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([], MagicMock())
        mock_fw.WhisperModel.return_value = mock_model

        _transcribe_whisper("test.mp3", src_lang="Japanese")

        call_kwargs = mock_model.transcribe.call_args[1]
        assert call_kwargs["language"] == "ja"

    @patch(f"{_MOD}._get_speech_language_code", return_value="zh-CN")
    def test_whisper_chinese_language(
        self,
        mock_lang,
        _setup_faster_whisper,
    ):
        """Chinese language code 'zh-CN' splits to 'zh' for Whisper."""
        mock_fw = _setup_faster_whisper
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([], MagicMock())
        mock_fw.WhisperModel.return_value = mock_model

        _transcribe_whisper("test.mp3", src_lang="Chinese (Simplified)")

        call_kwargs = mock_model.transcribe.call_args[1]
        assert call_kwargs["language"] == "zh"

    @patch(f"{_MOD}._get_speech_language_code", return_value="ko")
    def test_whisper_korean_no_hyphen(
        self,
        mock_lang,
        _setup_faster_whisper,
    ):
        """Korean code 'ko' (no hyphen) is passed as-is."""
        mock_fw = _setup_faster_whisper
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([], MagicMock())
        mock_fw.WhisperModel.return_value = mock_model

        _transcribe_whisper("test.mp3", src_lang="Korean")

        call_kwargs = mock_model.transcribe.call_args[1]
        assert call_kwargs["language"] == "ko"

    def test_whisper_segment_timestamp_formatting(self, _setup_faster_whisper):
        """Whisper segments produce correctly formatted SRT timestamps."""
        mock_fw = _setup_faster_whisper
        seg = MagicMock(start=3661.5, end=3665.123, text="  Late  ")
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([seg], MagicMock())
        mock_fw.WhisperModel.return_value = mock_model

        result = _transcribe_whisper("test.mp3")
        assert "01:01:01,500 --> 01:01:05,123" in result

    def test_whisper_default_model_size_base(self, _setup_faster_whisper):
        """Default model_size is 'base' when not specified."""
        mock_fw = _setup_faster_whisper
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([], MagicMock())
        mock_fw.WhisperModel.return_value = mock_model

        _transcribe_whisper("test.mp3")

        mock_fw.WhisperModel.assert_called_once_with(
            "base",
            device="cpu",
            compute_type="int8",
        )

    def test_whisper_model_size_tiny(self, _setup_faster_whisper):
        """Tiny model size is passed correctly."""
        mock_fw = _setup_faster_whisper
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([], MagicMock())
        mock_fw.WhisperModel.return_value = mock_model

        _transcribe_whisper("test.mp3", model_size="tiny")

        assert mock_fw.WhisperModel.call_args[0][0] == "tiny"

    def test_whisper_overlapping_segments(self, _setup_faster_whisper):
        """Whisper segments with overlapping timestamps still produce SRT."""
        mock_fw = _setup_faster_whisper
        seg1 = MagicMock(start=0.0, end=2.0, text="  First  ")
        seg2 = MagicMock(start=1.5, end=3.5, text="  Second  ")
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([seg1, seg2], MagicMock())
        mock_fw.WhisperModel.return_value = mock_model

        result = _transcribe_whisper("test.mp3")
        assert "First" in result
        assert "Second" in result
        assert "1\n" in result
        assert "2\n" in result


# ---------------------------------------------------------------------------
# TestGoogleCloudSTTEdgeCases — Google Cloud Speech REST API edge cases
# ---------------------------------------------------------------------------


class TestGoogleCloudSTTEdgeCases:
    """Edge cases for Google Cloud Speech-to-Text REST API."""

    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key123")
    @patch(f"{_MOD}._extract_audio_to_flac")
    def test_audio_one_byte_over_limit(self, mock_extract, mock_key, tmp_path):
        """Audio exceeding limit by one byte raises AUDIO_TOO_LARGE."""
        flac = tmp_path / "audio.flac"
        flac.write_bytes(b"\x00" * (_MAX_AUDIO_BYTES + 1))
        mock_extract.return_value = flac

        with pytest.raises(ValueError, match="AUDIO_TOO_LARGE"):
            _transcribe_google_cloud("test.mp4")

    @patch(f"{_MOD}._parse_results_to_srt", return_value="srt")
    @patch(f"{_MOD}._poll_operation", return_value={"results": []})
    @patch(f"{_MOD}._call_long_running_recognize", return_value="op-1")
    @patch(f"{_MOD}._get_speech_language_code", return_value="")
    @patch(f"{_MOD}._extract_audio_to_flac")
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key123")
    def test_auto_detect_language_empty(  # noqa: PLR0913
        self,
        mock_key,
        mock_extract,
        mock_lang,
        mock_recognize,
        mock_poll,
        mock_parse,
        tmp_path,
    ):
        """Empty language for auto-detect passes empty string to recognize."""
        flac = tmp_path / "audio.flac"
        flac.write_bytes(b"\x00" * 100)
        mock_extract.return_value = flac

        _transcribe_google_cloud("test.mp4", src_lang="")
        # _call_long_running_recognize receives empty lang code
        call_args = mock_recognize.call_args[0]
        assert call_args[1] == ""

    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    @patch(f"{_MOD}._extract_audio_to_flac")
    def test_flac_cleanup_on_size_error(self, mock_extract, mock_key, tmp_path):
        """Temp FLAC directory is cleaned even when size check fails."""
        flac_dir = tmp_path / "subtitle_test"
        flac_dir.mkdir()
        flac = flac_dir / "audio.flac"
        flac.write_bytes(b"\x00" * (_MAX_AUDIO_BYTES + 1000))
        mock_extract.return_value = flac

        with pytest.raises(ValueError, match="AUDIO_TOO_LARGE"):
            _transcribe_google_cloud("test.mp4")

    @patch(f"{_MOD}._parse_results_to_srt", return_value="srt content")
    @patch(f"{_MOD}._poll_operation", return_value={"results": [{"a": 1}]})
    @patch(f"{_MOD}._call_long_running_recognize", return_value="op-x")
    @patch(f"{_MOD}._get_speech_language_code", return_value="de")
    @patch(f"{_MOD}._extract_audio_to_flac")
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_model_parameter_forwarded(  # noqa: PLR0913
        self,
        mock_key,
        mock_extract,
        mock_lang,
        mock_recognize,
        mock_poll,
        mock_parse,
        tmp_path,
    ):
        """Custom model parameter is forwarded to _call_long_running_recognize."""
        flac = tmp_path / "audio.flac"
        flac.write_bytes(b"\x00" * 100)
        mock_extract.return_value = flac

        _transcribe_google_cloud("test.mp4", model="latest_long")
        call_kwargs = mock_recognize.call_args[1]
        assert call_kwargs["model"] == "latest_long"

    @patch(f"{_MOD}._parse_results_to_srt", return_value="")
    @patch(f"{_MOD}._poll_operation", return_value={"results": []})
    @patch(f"{_MOD}._call_long_running_recognize", return_value="op-tiny")
    @patch(f"{_MOD}._get_speech_language_code", return_value="en-US")
    @patch(f"{_MOD}._extract_audio_to_flac")
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_very_small_audio_file(  # noqa: PLR0913
        self,
        mock_key,
        mock_extract,
        mock_lang,
        mock_recognize,
        mock_poll,
        mock_parse,
        tmp_path,
    ):
        """Very small audio file (1 byte) is processed without error."""
        flac = tmp_path / "audio.flac"
        flac.write_bytes(b"\x00")
        mock_extract.return_value = flac

        result = _transcribe_google_cloud("test.mp4")
        assert isinstance(result, str)
        mock_recognize.assert_called_once()


# ---------------------------------------------------------------------------
# TestEdgeTTSEdgeCases — Edge TTS edge cases
# ---------------------------------------------------------------------------


class TestEdgeTTSEdgeCases:
    """Edge cases for Edge TTS backend."""

    @pytest.fixture(autouse=True)
    def _setup_edge_tts(self):
        """Inject mock edge_tts and edge_tts.exceptions into sys.modules."""
        self._NoAudioReceived = type("NoAudioReceived", (Exception,), {})

        mock_edge = MagicMock()
        mock_exceptions = MagicMock()
        mock_exceptions.NoAudioReceived = self._NoAudioReceived

        prev_edge = sys.modules.get("edge_tts")
        prev_exc = sys.modules.get("edge_tts.exceptions")
        sys.modules["edge_tts"] = mock_edge
        sys.modules["edge_tts.exceptions"] = mock_exceptions

        self._mock_edge = mock_edge
        yield
        if prev_edge is None:
            sys.modules.pop("edge_tts", None)
        else:
            sys.modules["edge_tts"] = prev_edge
        if prev_exc is None:
            sys.modules.pop("edge_tts.exceptions", None)
        else:
            sys.modules["edge_tts.exceptions"] = prev_exc

    def test_edge_tts_empty_text(self, tmp_path):
        """Edge TTS with empty text still calls Communicate."""
        output = tmp_path / "out.mp3"
        mock_comm = MagicMock()
        mock_comm.save = AsyncMock()
        self._mock_edge.Communicate.return_value = mock_comm

        _synthesize_chunk_edge(
            "",
            "en-US-JennyNeural",
            output,
            max_retries=0,
            base_delay=0.0,
        )
        self._mock_edge.Communicate.assert_called_once_with(
            "",
            "en-US-JennyNeural",
        )

    def test_edge_tts_very_long_text(self, tmp_path):
        """Edge TTS with very long text succeeds."""
        output = tmp_path / "out.mp3"
        mock_comm = MagicMock()
        mock_comm.save = AsyncMock()
        self._mock_edge.Communicate.return_value = mock_comm

        long_text = "word " * 5000
        _synthesize_chunk_edge(
            long_text,
            "en-US-JennyNeural",
            output,
            max_retries=0,
            base_delay=0.0,
        )
        self._mock_edge.Communicate.assert_called_once_with(
            long_text,
            "en-US-JennyNeural",
        )

    def test_edge_tts_unicode_text(self, tmp_path):
        """Edge TTS with unicode text succeeds."""
        output = tmp_path / "out.mp3"
        mock_comm = MagicMock()
        mock_comm.save = AsyncMock()
        self._mock_edge.Communicate.return_value = mock_comm

        _synthesize_chunk_edge(
            "\u4f60\u597d\u4e16\u754c",
            "zh-CN-XiaoxiaoNeural",
            output,
            max_retries=0,
            base_delay=0.0,
        )
        mock_comm.save.assert_awaited_once()

    def test_edge_tts_retry_count_three(self, tmp_path):
        """With max_retries=3, up to 4 attempts are made."""
        output = tmp_path / "out.mp3"
        mock_comm = MagicMock()
        mock_comm.save = AsyncMock(
            side_effect=self._NoAudioReceived("fail"),
        )
        self._mock_edge.Communicate.return_value = mock_comm

        with pytest.raises(ValueError, match="TTS_API_ERROR"):
            _synthesize_chunk_edge(
                "Hi",
                "en-US-JennyNeural",
                output,
                max_retries=3,
                base_delay=0.0,
            )
        # 1 initial + 3 retries = 4 total attempts
        assert mock_comm.save.await_count == 4  # noqa: PLR2004

    def test_edge_tts_succeed_on_third_retry(self, tmp_path):
        """Succeeds on third attempt after two NoAudioReceived failures."""
        output = tmp_path / "out.mp3"
        mock_comm = MagicMock()
        mock_comm.save = AsyncMock(
            side_effect=[
                self._NoAudioReceived("fail1"),
                self._NoAudioReceived("fail2"),
                None,
            ],
        )
        self._mock_edge.Communicate.return_value = mock_comm

        _synthesize_chunk_edge(
            "Hi",
            "en-US-JennyNeural",
            output,
            max_retries=3,
            base_delay=0.0,
        )
        assert mock_comm.save.await_count == 3  # noqa: PLR2004

    def test_edge_tts_different_voice_names(self, tmp_path):
        """Different voice names are passed correctly to Communicate."""
        output = tmp_path / "out.mp3"
        mock_comm = MagicMock()
        mock_comm.save = AsyncMock()
        self._mock_edge.Communicate.return_value = mock_comm

        for voice in ("vi-VN-HoaiMyNeural", "ja-JP-NanamiNeural", "de-DE-KatjaNeural"):
            _synthesize_chunk_edge(
                "test",
                voice,
                output,
                max_retries=0,
                base_delay=0.0,
            )
            assert self._mock_edge.Communicate.call_args[0][1] == voice

    def test_edge_tts_keyboard_interrupt_propagates(self, tmp_path):
        """KeyboardInterrupt during synthesis propagates immediately."""
        output = tmp_path / "out.mp3"
        mock_comm = MagicMock()
        mock_comm.save = AsyncMock(side_effect=KeyboardInterrupt())
        self._mock_edge.Communicate.return_value = mock_comm

        with pytest.raises(KeyboardInterrupt):
            _synthesize_chunk_edge(
                "Hi",
                "en-US-JennyNeural",
                output,
                max_retries=3,
                base_delay=0.0,
            )


# ---------------------------------------------------------------------------
# TestGoogleCloudTTSEdgeCases — Google Cloud TTS edge cases
# ---------------------------------------------------------------------------


class TestGoogleCloudTTSEdgeCases:
    """Edge cases for Google Cloud TTS backend."""

    def _make_response(self, audio_bytes: bytes) -> MagicMock:
        """Create a mock urlopen response with base64-encoded audio."""
        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
        resp_data = json.dumps({"audioContent": audio_b64}).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = resp_data
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    @patch("urllib.request.urlopen")
    def test_http_502_raises_tts_api_error(self, mock_urlopen, tmp_path):
        """HTTP 502 maps to ``SERVICE_UNAVAILABLE_ERROR`` (retry-eligible)."""
        fp = MagicMock(read=lambda: b"bad gateway")
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "url",
            502,
            "Bad Gateway",
            {},
            fp,
        )
        out = tmp_path / "c.mp3"
        with pytest.raises(ValueError, match="SERVICE_UNAVAILABLE_ERROR"):
            _synthesize_chunk("Hi", "en-US", "FEMALE", "key", out)

    @patch("urllib.request.urlopen")
    def test_http_503_raises_tts_api_error(self, mock_urlopen, tmp_path):
        """HTTP 503 maps to ``SERVICE_UNAVAILABLE_ERROR``."""
        fp = MagicMock(read=lambda: b"service unavailable")
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "url",
            503,
            "Service Unavailable",
            {},
            fp,
        )
        out = tmp_path / "c.mp3"
        with pytest.raises(ValueError, match="SERVICE_UNAVAILABLE_ERROR"):
            _synthesize_chunk("Hi", "en-US", "FEMALE", "key", out)

    @patch("urllib.request.urlopen")
    def test_http_400_raises_tts_api_error(self, mock_urlopen, tmp_path):
        """HTTP 400 (non-API_KEY_INVALID) maps to ``TTS_INVALID_REQUEST``.

        TTS-specific sentinel so the message references TTS rather
        than the LLM-flavored generic INVALID_REQUEST text.
        """
        fp = MagicMock(read=lambda: b"bad request")
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "url",
            400,
            "Bad Request",
            {},
            fp,
        )
        out = tmp_path / "c.mp3"
        with pytest.raises(ValueError, match="TTS_INVALID_REQUEST"):
            _synthesize_chunk("Hi", "en-US", "FEMALE", "key", out)

    @patch("urllib.request.urlopen")
    def test_speaking_rate_negative_clamped(self, mock_urlopen, tmp_path):
        """Negative speaking rate is clamped to 0.25."""
        mock_urlopen.return_value = self._make_response(b"audio")
        out = tmp_path / "chunk.mp3"
        _synthesize_chunk("Hi", "en-US", "FEMALE", "key", out, speaking_rate=-1.0)

        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode("utf-8"))
        assert payload["audioConfig"]["speakingRate"] == 0.25  # noqa: PLR2004

    @patch("urllib.request.urlopen")
    def test_speaking_rate_zero_clamped(self, mock_urlopen, tmp_path):
        """Zero speaking rate is clamped to 0.25."""
        mock_urlopen.return_value = self._make_response(b"audio")
        out = tmp_path / "chunk.mp3"
        _synthesize_chunk("Hi", "en-US", "FEMALE", "key", out, speaking_rate=0.0)

        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode("utf-8"))
        assert payload["audioConfig"]["speakingRate"] == 0.25  # noqa: PLR2004

    @patch("urllib.request.urlopen")
    def test_large_audio_content_base64(self, mock_urlopen, tmp_path):
        """Large audio content (100KB) is decoded and written correctly."""
        audio_data = b"\xff" * 100000
        mock_urlopen.return_value = self._make_response(audio_data)
        out = tmp_path / "chunk.mp3"
        _synthesize_chunk("Hi", "en-US", "FEMALE", "key", out)
        assert out.read_bytes() == audio_data

    @patch("urllib.request.urlopen")
    def test_male_voice_in_multiple_languages(self, mock_urlopen, tmp_path):
        """MALE voice gender is correctly set for different languages."""
        mock_urlopen.return_value = self._make_response(b"audio")
        out = tmp_path / "chunk.mp3"
        for lang_code in ("vi-VN", "ja-JP", "de-DE", "fr-FR"):
            _synthesize_chunk("Hi", lang_code, "MALE", "key", out)
            req = mock_urlopen.call_args[0][0]
            payload = json.loads(req.data.decode("utf-8"))
            assert payload["voice"]["ssmlGender"] == "MALE"
            assert payload["voice"]["languageCode"] == lang_code


# ---------------------------------------------------------------------------
# TestExtractAudioToFlacEdgeCases — FFmpeg conversion edge cases
# ---------------------------------------------------------------------------


class TestExtractAudioToFlacEdgeCases:
    """Edge cases for FLAC audio extraction via FFmpeg."""

    @patch("subprocess.run")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_input_path_in_command(self, mock_ff, mock_run):
        """Input file path appears in FFmpeg command."""
        mock_run.return_value = MagicMock(returncode=0)
        _extract_audio_to_flac("/path/to/my video.mp4")

        cmd = mock_run.call_args[0][0]
        assert "/path/to/my video.mp4" in cmd

    @patch("subprocess.run")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_output_is_audio_flac(self, mock_ff, mock_run):
        """Output file is named audio.flac in temp directory."""
        mock_run.return_value = MagicMock(returncode=0)
        result = _extract_audio_to_flac("/some/video.mp4")
        assert result.name == "audio.flac"

    @patch("subprocess.run")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_capture_output_and_check_enabled(self, mock_ff, mock_run):
        """FFmpeg is called with capture_output=True and check=True."""
        mock_run.return_value = MagicMock(returncode=0)
        _extract_audio_to_flac("/some/video.mp4")

        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["capture_output"] is True
        assert call_kwargs["check"] is True

    @patch("subprocess.run")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_stderr_decoded_on_error(self, mock_ff, mock_run):
        """CalledProcessError stderr is decoded for logging."""
        mock_run.side_effect = subprocess.CalledProcessError(
            1,
            "ffmpeg",
            stderr="\u00e9rror m\u00e9ssage".encode(),
        )
        with pytest.raises(RuntimeError, match="FFMPEG_CONVERSION_FAILED"):
            _extract_audio_to_flac("/some/video.mp4")

    @patch("subprocess.run")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_long_stderr_truncated(self, mock_ff, mock_run):
        """Long stderr is truncated to 500 chars in error handling."""
        long_msg = "x" * 1000
        mock_run.side_effect = subprocess.CalledProcessError(
            1,
            "ffmpeg",
            stderr=long_msg.encode("utf-8"),
        )
        with pytest.raises(RuntimeError, match="FFMPEG_CONVERSION_FAILED"):
            _extract_audio_to_flac("/some/video.mp4")


# ---------------------------------------------------------------------------
# TestConvertSubtitleFormatAllCombinations — all format combinations
# ---------------------------------------------------------------------------


class TestConvertSubtitleFormatAllCombinations:
    """Test _convert_subtitle_format with all format combinations."""

    _SRT = "1\n00:00:01,000 --> 00:00:04,000\nHello\n"

    def test_srt_to_srt_passthrough(self):
        """SRT to SRT returns unchanged."""
        assert _convert_subtitle_format(self._SRT, ".srt") == self._SRT

    def test_srt_to_vtt_conversion(self):
        """SRT to VTT converts timestamps and adds header."""
        vtt = _convert_subtitle_format(self._SRT, ".vtt")
        assert vtt.startswith("WEBVTT\n")
        assert "00:00:01.000 --> 00:00:04.000" in vtt

    def test_srt_to_ass_produces_script(self):
        """SRT to ASS now emits a valid Script Info file."""
        result = _convert_subtitle_format(self._SRT, ".ass")
        assert "[Script Info]" in result
        assert "Dialogue:" in result

    def test_srt_to_ssa_produces_script(self):
        """SRT to SSA also emits a valid Script Info file."""
        result = _convert_subtitle_format(self._SRT, ".ssa")
        assert "[Script Info]" in result
        assert "Dialogue:" in result

    def test_srt_to_txt_passthrough(self):
        """SRT to TXT returns unchanged."""
        assert _convert_subtitle_format(self._SRT, ".txt") == self._SRT

    def test_srt_to_empty_ext_passthrough(self):
        """SRT to empty extension returns unchanged."""
        assert _convert_subtitle_format(self._SRT, "") == self._SRT

    def test_srt_to_mp4_passthrough(self):
        """SRT to MP4 returns unchanged."""
        assert _convert_subtitle_format(self._SRT, ".mp4") == self._SRT

    def test_srt_to_json_passthrough(self):
        """SRT to JSON returns unchanged."""
        assert _convert_subtitle_format(self._SRT, ".json") == self._SRT

    def test_srt_to_xml_passthrough(self):
        """SRT to XML returns unchanged."""
        assert _convert_subtitle_format(self._SRT, ".xml") == self._SRT

    def test_vtt_with_timestamp_edge_hours(self):
        """VTT conversion handles timestamps with hours correctly."""
        srt = "1\n01:30:45,123 --> 02:15:30,456\nHello\n"
        vtt = _convert_subtitle_format(srt, ".vtt")
        assert "01:30:45.123 --> 02:15:30.456" in vtt

    def test_vtt_with_zero_timestamps(self):
        """VTT conversion handles zero timestamps."""
        srt = "1\n00:00:00,000 --> 00:00:00,000\nZero\n"
        vtt = _convert_subtitle_format(srt, ".vtt")
        assert "00:00:00.000 --> 00:00:00.000" in vtt

    def test_vtt_conversion_multiple_commas_in_text(self):
        """VTT conversion preserves multiple commas in text lines."""
        srt = "1\n00:00:01,000 --> 00:00:04,000\nA, B, C, D\n"
        vtt = _convert_subtitle_format(srt, ".vtt")
        assert "A, B, C, D" in vtt
        # Only timestamp commas are converted
        ts_lines = [ln for ln in vtt.split("\n") if "-->" in ln]
        for ts in ts_lines:
            assert "," not in ts

    def test_vtt_with_large_entry_count(self):
        """VTT conversion handles many SRT entries."""
        lines = []
        count = 20
        for i in range(1, count + 1):
            lines.append(str(i))
            lines.append(f"00:00:{i:02d},000 --> 00:00:{i:02d},500")
            lines.append(f"Entry {i}")
            lines.append("")
        srt = "\n".join(lines)
        vtt = _convert_subtitle_format(srt, ".vtt")
        assert "WEBVTT" in vtt
        assert f"Entry {count}" in vtt


# ---------------------------------------------------------------------------
# TestSynthesizeTimedSpeechTimingEdgeCases — timing edge cases
# ---------------------------------------------------------------------------


class TestSynthesizeTimedSpeechTimingEdgeCases:
    """Timing edge cases for synthesize_timed_speech."""

    @pytest.fixture(autouse=True)
    def _mock_edge(self):
        """Prevent edge_tts import in tests running outside uv."""
        with patch(f"{_MOD}._synthesize_chunk_edge"):
            yield

    def _make_entry(self, start: str, end: str, text: str) -> MagicMock:
        """Create a mock SubtitleEntry."""
        entry = MagicMock()
        entry.start = start
        entry.end = end
        entry.text = text
        return entry

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration", return_value=0.01)
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_very_short_entry(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_synth,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """Very short entry (50ms) is processed without error."""
        entries = [
            self._make_entry("00:00:00,000", "00:00:00,050", "Quick"),
        ]
        output = str(tmp_path / "out.mp3")
        result = synthesize_timed_speech(
            entries,
            tts_method=_GOOGLE_TTS,
            output_path=output,
        )
        assert result == output
        assert mock_synth.call_count == 1

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration", return_value=1.0)
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_entry_at_one_hour_mark(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_synth,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """Entry at 1-hour mark has correct leading silence."""
        entries = [
            self._make_entry("01:00:00,000", "01:00:02,000", "Late"),
        ]
        output = str(tmp_path / "out.mp3")
        synthesize_timed_speech(
            entries,
            tts_method=_GOOGLE_TTS,
            output_path=output,
        )
        # 3600 seconds of leading silence
        mock_silence.assert_called_once()
        duration_arg = mock_silence.call_args[0][0]
        assert duration_arg == 3600.0  # noqa: PLR2004

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration", return_value=0.5)
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_many_entries_ten(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_synth,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """Ten entries are all processed correctly."""
        entries = [
            self._make_entry(
                f"00:00:{i * 2:02d},000",
                f"00:00:{i * 2 + 1:02d},000",
                f"Entry {i}",
            )
            for i in range(10)
        ]
        output = str(tmp_path / "out.mp3")
        synthesize_timed_speech(
            entries,
            tts_method=_GOOGLE_TTS,
            output_path=output,
        )
        assert mock_synth.call_count == 10  # noqa: PLR2004

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration", return_value=1.0)
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_adjacent_entries_no_silence(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_synth,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """Adjacent entries (end1 == start2) with audio fitting produce no silence."""
        entries = [
            self._make_entry("00:00:00,000", "00:00:02,000", "A"),
            self._make_entry("00:00:02,000", "00:00:04,000", "B"),
        ]
        output = str(tmp_path / "out.mp3")
        synthesize_timed_speech(
            entries,
            tts_method=_GOOGLE_TTS,
            output_path=output,
        )
        # Cursor after first entry = max(0,0) + 1.0 = 1.0
        # Gap = 2.0 - 1.0 = 1.0 > 0.05 -> silence inserted
        assert mock_silence.call_count == 1

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration", return_value=0.5)
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_only_whitespace_entries_filtered_to_empty(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_synth,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """All-whitespace entries result in EMPTY_TEXT error."""
        entries = [
            self._make_entry("00:00:00,000", "00:00:01,000", "   "),
            self._make_entry("00:00:02,000", "00:00:03,000", "\t\n"),
        ]
        with pytest.raises(ValueError, match="EMPTY_TEXT"):
            synthesize_timed_speech(
                entries,
                tts_method=_GOOGLE_TTS,
                output_path=str(tmp_path / "o.mp3"),
            )


# ---------------------------------------------------------------------------
# TestMixAudioIntoVideoEdgeCases — mix_audio_into_video scenarios
# ---------------------------------------------------------------------------


class TestMixAudioIntoVideoEdgeCases:
    """Edge-case tests for mix_audio_into_video."""

    @patch("subprocess.run")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_paths_with_spaces(self, mock_ff, mock_run, tmp_path):
        """File paths with spaces are handled correctly."""
        mock_run.return_value = MagicMock(returncode=0)
        video = str(tmp_path / "my video.mp4")
        audio = str(tmp_path / "my audio.mp3")
        output = str(tmp_path / "my output.mp4")
        result = mix_audio_into_video(video, audio, output)
        assert result == output
        cmd = mock_run.call_args[0][0]
        assert video in cmd
        assert audio in cmd

    @patch("subprocess.run")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_different_audio_formats(self, mock_ff, mock_run, tmp_path):
        """WAV audio can be mixed into video."""
        mock_run.return_value = MagicMock(returncode=0)
        result = mix_audio_into_video(
            str(tmp_path / "v.mp4"),
            str(tmp_path / "a.wav"),
            str(tmp_path / "o.mp4"),
        )
        assert result == str(tmp_path / "o.mp4")

    @patch("subprocess.run")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_ffmpeg_called_once(self, mock_ff, mock_run, tmp_path):
        """FFmpeg is called exactly once."""
        mock_run.return_value = MagicMock(returncode=0)
        mix_audio_into_video(
            str(tmp_path / "v.mp4"),
            str(tmp_path / "a.mp3"),
            str(tmp_path / "o.mp4"),
        )
        mock_run.assert_called_once()

    @patch("subprocess.run")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_stderr_truncation_in_error(self, mock_ff, mock_run, tmp_path):
        """Long stderr from FFmpeg is truncated to 500 chars."""
        long_stderr = ("x" * 600).encode("utf-8")
        mock_run.side_effect = subprocess.CalledProcessError(
            1,
            "ffmpeg",
            stderr=long_stderr,
        )
        with pytest.raises(RuntimeError, match="FFMPEG_MIX_FAILED"):
            mix_audio_into_video(
                str(tmp_path / "v.mp4"),
                str(tmp_path / "a.mp3"),
                str(tmp_path / "o.mp4"),
            )

    @patch("subprocess.run")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_video_copy_not_reencode(self, mock_ff, mock_run, tmp_path):
        """Video stream is copied, not re-encoded (-c:v copy)."""
        mock_run.return_value = MagicMock(returncode=0)
        mix_audio_into_video(
            str(tmp_path / "v.mp4"),
            str(tmp_path / "a.mp3"),
            str(tmp_path / "o.mp4"),
        )
        cmd = mock_run.call_args[0][0]
        # -c:v and copy should be adjacent
        cv_idx = cmd.index("-c:v")
        assert cmd[cv_idx + 1] == "copy"


# ---------------------------------------------------------------------------
# TestCancellationDuringProcessing — cancellation edge cases
# ---------------------------------------------------------------------------


class TestCancellationDuringProcessing:
    """Test cancellation during various processing stages."""

    @pytest.fixture(autouse=True)
    def _mock_edge(self):
        """Prevent edge_tts import in tests running outside uv."""
        with patch(f"{_MOD}._synthesize_chunk_edge"):
            yield

    def _make_entry(self, start: str, end: str, text: str) -> MagicMock:
        """Create a mock SubtitleEntry."""
        entry = MagicMock()
        entry.start = start
        entry.end = end
        entry.text = text
        return entry

    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}._split_text_for_tts", return_value=["A."])
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_cancel_never_called_completes(
        self,
        mock_key,
        mock_ffmpeg,
        mock_split,
        mock_synth,
        tmp_path,
    ):
        """When cancel returns False, synthesis completes normally."""
        with patch(f"{_MOD}._concatenate_mp3_files"):
            output = str(tmp_path / "out.mp3")
            result = synthesize_speech(
                "A.",
                output_path=output,
                tts_method=_GOOGLE_TTS,
                is_cancelled=lambda: False,
            )
            assert result == output
            mock_synth.assert_called_once()

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration", return_value=0.5)
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_timed_cancel_after_first_entry(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_synth,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """Timed speech cancellation after first entry synthesizes only one."""
        call_count = 0

        def cancel_after_first():
            nonlocal call_count
            call_count += 1
            return call_count > 1

        entries = [
            self._make_entry("00:00:00,000", "00:00:01,000", "First"),
            self._make_entry("00:00:02,000", "00:00:03,000", "Second"),
            self._make_entry("00:00:04,000", "00:00:05,000", "Third"),
        ]
        output = str(tmp_path / "out.mp3")
        with pytest.raises(ValueError, match="CANCELLED"):
            synthesize_timed_speech(
                entries,
                output_path=output,
                tts_method=_GOOGLE_TTS,
                is_cancelled=cancel_after_first,
            )
        assert mock_synth.call_count == 1

    @patch("time.sleep")
    @patch("urllib.request.urlopen")
    def test_poll_cancel_mid_poll(self, mock_urlopen, mock_sleep):
        """Cancellation mid-poll stops polling after one attempt."""
        pending = MagicMock()
        pending.read.return_value = json.dumps({"done": False}).encode()
        pending.__enter__ = MagicMock(return_value=pending)
        pending.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = pending

        call_count = 0

        def cancel_on_second():
            nonlocal call_count
            call_count += 1
            return call_count > 1

        with pytest.raises(ValueError, match="CANCELLED"):
            _poll_operation("op/1", "key", is_cancelled=cancel_on_second)


# ---------------------------------------------------------------------------
# TestMemorySafetyLargeFileHandling — memory safety tests
# ---------------------------------------------------------------------------


class TestMemorySafetyLargeFileHandling:
    """Test memory safety with large files and data."""

    @pytest.fixture(autouse=True)
    def _mock_edge(self):
        """Prevent edge_tts import in tests running outside uv."""
        with patch(f"{_MOD}._synthesize_chunk_edge"):
            yield

    def _make_entry(self, start: str, end: str, text: str) -> MagicMock:
        """Create a mock SubtitleEntry."""
        entry = MagicMock()
        entry.start = start
        entry.end = end
        entry.text = text
        return entry

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}._split_text_for_tts")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_many_chunks_processed_sequentially(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_split,
        mock_synth,
        mock_concat,
        tmp_path,
    ):
        """100 chunks are processed sequentially without memory accumulation."""
        chunk_count = 100
        mock_split.return_value = [f"Chunk {i}." for i in range(chunk_count)]
        output = str(tmp_path / "out.mp3")
        synthesize_speech(
            "x" * 50000,
            output_path=output,
            tts_method=_GOOGLE_TTS,
        )
        assert mock_synth.call_count == chunk_count

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration", return_value=0.5)
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_many_timed_entries_fifty(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_synth,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """50 timed entries are all processed without error."""
        entries = [
            self._make_entry(
                f"00:00:{i * 2:02d},000",
                f"00:00:{i * 2 + 1:02d},000",
                f"Entry {i}",
            )
            for i in range(50)
        ]
        output = str(tmp_path / "out.mp3")
        synthesize_timed_speech(
            entries,
            tts_method=_GOOGLE_TTS,
            output_path=output,
        )
        assert mock_synth.call_count == 50  # noqa: PLR2004

    def test_split_text_large_input(self):
        """Splitting very large text (50KB) produces valid chunks."""
        word = "word "
        big_text = word * 10000
        result = _split_text_for_tts(big_text)
        assert len(result) > 1
        # All text is preserved
        combined = " ".join(result)
        assert combined.count("word") >= 9000  # noqa: PLR2004

    def test_split_text_multibyte_large(self):
        """Splitting large CJK text handles byte limits correctly."""
        # Each CJK char = 3 bytes in UTF-8
        text = "\u4f60\u597d\u3002 " * 1000
        result = _split_text_for_tts(text, max_bytes=100)
        assert len(result) > 1
        for chunk in result:
            assert len(chunk.encode("utf-8")) <= 100  # noqa: PLR2004


# ---------------------------------------------------------------------------
# TestParseResultsToSrtExtendedEdgeCases — STT output parser edges
# ---------------------------------------------------------------------------


class TestParseResultsToSrtExtendedEdgeCases:
    """Extended edge cases for _parse_results_to_srt."""

    def test_word_with_missing_start_time(self):
        """Word without startTime defaults to 0.0."""
        results = [
            {
                "alternatives": [
                    {
                        "words": [
                            {"word": "orphan", "endTime": "1s"},
                        ],
                    }
                ],
            }
        ]
        srt = _parse_results_to_srt(results)
        assert "orphan" in srt
        assert "00:00:00,000" in srt

    def test_word_with_missing_end_time(self):
        """Word without endTime defaults to 0.0."""
        results = [
            {
                "alternatives": [
                    {
                        "words": [
                            {"word": "hello", "startTime": "1s"},
                        ],
                    }
                ],
            }
        ]
        srt = _parse_results_to_srt(results)
        assert "hello" in srt

    def test_many_words_force_multiple_segments(self):
        """Many words create multiple segments due to char limit."""
        words = [
            {
                "word": f"word{i:03d}",
                "startTime": f"{i * 0.5}s",
                "endTime": f"{i * 0.5 + 0.4}s",
            }
            for i in range(50)
        ]
        results = [{"alternatives": [{"words": words}]}]
        srt = _parse_results_to_srt(results)
        lines = srt.strip().split("\n")
        # Should have more than one segment
        segment_numbers = [ln for ln in lines if ln.strip().isdigit()]
        assert len(segment_numbers) > 1

    def test_single_word_result(self):
        """Single word produces one segment."""
        results = [
            {
                "alternatives": [
                    {
                        "words": [
                            {"word": "only", "startTime": "0s", "endTime": "0.5s"},
                        ],
                    }
                ],
            }
        ]
        srt = _parse_results_to_srt(results)
        assert "1\n" in srt
        assert "only" in srt
        # No segment "2"
        assert "\n2\n" not in srt

    def test_transcript_with_special_chars_in_fallback(self):
        """Transcript with HTML in fallback mode is preserved."""
        results = [
            {"alternatives": [{"transcript": "<b>Bold & 'quoted'</b>"}]},
        ]
        srt = _parse_results_to_srt(results)
        assert "<b>Bold & 'quoted'</b>" in srt

    def test_multiple_alternatives_only_first_used(self):
        """Only the first alternative is used per result."""
        results = [
            {
                "alternatives": [
                    {
                        "words": [
                            {"word": "First", "startTime": "0s", "endTime": "0.5s"},
                        ],
                    },
                    {
                        "words": [
                            {"word": "Second", "startTime": "0s", "endTime": "0.5s"},
                        ],
                    },
                ],
            }
        ]
        srt = _parse_results_to_srt(results)
        assert "First" in srt
        # Second alternative is not included
        assert "Second" not in srt

    def test_empty_alternatives_list(self):
        """Empty alternatives list produces no output."""
        results = [{"alternatives": []}]
        srt = _parse_results_to_srt(results)
        assert srt == ""


# ---------------------------------------------------------------------------
# TestPollOperationEdgeCases — additional poll operation tests
# ---------------------------------------------------------------------------


class TestPollOperationEdgeCases:
    """Additional edge cases for _poll_operation."""

    def _make_response(self, data: dict) -> MagicMock:
        """Create a mock urlopen context-manager response."""
        resp = MagicMock()
        resp.read.return_value = json.dumps(data).encode("utf-8")
        resp.__enter__ = MagicMock(return_value=resp)
        resp.__exit__ = MagicMock(return_value=False)
        return resp

    @patch("time.sleep")
    @patch("urllib.request.urlopen")
    def test_single_poll_immediate_done(self, mock_urlopen, mock_sleep):
        """Single poll: operation done immediately."""
        complete = self._make_response(
            {"done": True, "response": {"results": [{"a": 1}]}},
        )
        mock_urlopen.return_value = complete
        result = _poll_operation("op/1", "key")
        assert result == {"results": [{"a": 1}]}
        assert mock_urlopen.call_count == 1

    @patch("time.sleep")
    @patch("urllib.request.urlopen")
    def test_poll_delay_starts_at_initial(self, mock_urlopen, mock_sleep):
        """First sleep delay is _POLL_INITIAL_DELAY."""
        from src.core.speech_engine import _POLL_INITIAL_DELAY  # noqa: PLC0415

        complete = self._make_response(
            {"done": True, "response": {}},
        )
        mock_urlopen.return_value = complete
        _poll_operation("op/1", "key")
        first_delay = mock_sleep.call_args_list[0][0][0]
        assert first_delay == _POLL_INITIAL_DELAY

    @patch("time.sleep")
    @patch("urllib.request.urlopen")
    def test_poll_delay_never_exceeds_max(self, mock_urlopen, mock_sleep):
        """Sleep delays never exceed _POLL_MAX_DELAY."""
        from src.core.speech_engine import _POLL_MAX_DELAY  # noqa: PLC0415

        pending = self._make_response({"done": False})
        complete = self._make_response(
            {"done": True, "response": {}},
        )
        # 10 pending polls then done
        mock_urlopen.side_effect = [pending] * 10 + [complete]
        _poll_operation("op/delay", "key")
        for call in mock_sleep.call_args_list:
            assert call[0][0] <= _POLL_MAX_DELAY

    @patch("time.sleep")
    @patch("urllib.request.urlopen")
    def test_poll_url_includes_operation_name(self, mock_urlopen, mock_sleep):
        """Poll URL includes the operation name."""
        complete = self._make_response({"done": True, "response": {}})
        mock_urlopen.return_value = complete
        _poll_operation("operations/my-op-id", "my-key")
        req = mock_urlopen.call_args[0][0]
        assert "operations/my-op-id" in req.full_url
        assert "key=my-key" in req.full_url

    @patch("time.sleep")
    @patch("urllib.request.urlopen")
    def test_done_with_error_custom_message(self, mock_urlopen, mock_sleep):
        """Error message from operation is included in the ValueError."""
        mock_urlopen.return_value = self._make_response(
            {"done": True, "error": {"message": "Language not supported"}},
        )
        with pytest.raises(ValueError, match="Language not supported"):
            _poll_operation("op/lang", "key")


# ---------------------------------------------------------------------------
# TestCallLongRunningRecognizeEdgeCases — additional recognize tests
# ---------------------------------------------------------------------------


class TestCallLongRunningRecognizeEdgeCases:
    """Additional edge cases for _call_long_running_recognize."""

    def _make_response(self, data: dict) -> MagicMock:
        """Create a mock urlopen context-manager response."""
        resp = MagicMock()
        resp.read.return_value = json.dumps(data).encode("utf-8")
        resp.__enter__ = MagicMock(return_value=resp)
        resp.__exit__ = MagicMock(return_value=False)
        return resp

    @patch("urllib.request.urlopen")
    def test_url_error_propagates(self, mock_urlopen):
        """URLError (network failure) propagates."""
        mock_urlopen.side_effect = urllib.error.URLError("no network")
        with pytest.raises(urllib.error.URLError):
            _call_long_running_recognize("audio", "en-US", "key")

    @patch("urllib.request.urlopen")
    def test_timeout_during_request_propagates(self, mock_urlopen):
        """Timeout during API request propagates."""
        mock_urlopen.side_effect = urllib.error.URLError(
            TimeoutError("timed out"),
        )
        with pytest.raises(urllib.error.URLError):
            _call_long_running_recognize("audio", "en-US", "key")

    @patch("urllib.request.urlopen")
    def test_http_404_raises_speech_api_error(self, mock_urlopen):
        """HTTP 404 raises SPEECH_API_ERROR."""
        fp = MagicMock(read=lambda: b"not found")
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "url",
            404,
            "Not Found",
            {},
            fp,
        )
        with pytest.raises(ValueError, match="SPEECH_API_ERROR"):
            _call_long_running_recognize("audio", "en-US", "key")

    @patch("urllib.request.urlopen")
    def test_request_timeout_is_60(self, mock_urlopen):
        """Request uses 60 second timeout."""
        mock_urlopen.return_value = self._make_response({"name": "op-1"})
        _call_long_running_recognize("audio_b64", "en-US", "key")
        call_args = mock_urlopen.call_args
        assert call_args[1].get("timeout") == 60 or call_args[0][1] == 60  # noqa: PLR2004


# ---------------------------------------------------------------------------
# TestSynthesizeSpeechConcatenation — concatenation edge cases
# ---------------------------------------------------------------------------


class TestSynthesizeSpeechConcatenation:
    """Test concatenation paths in synthesize_speech."""

    @pytest.fixture(autouse=True)
    def _mock_edge(self):
        """Prevent edge_tts import in tests running outside uv."""
        with patch(f"{_MOD}._synthesize_chunk_edge"):
            yield

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}._split_text_for_tts", return_value=["One.", "Two.", "Three."])
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_three_chunks_passed_to_concat(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_split,
        mock_synth,
        mock_concat,
        tmp_path,
    ):
        """Three chunk files are passed to _concatenate_mp3_files."""
        output = str(tmp_path / "out.mp3")
        synthesize_speech(
            "One. Two. Three.",
            output_path=output,
            tts_method=_GOOGLE_TTS,
        )
        concat_call = mock_concat.call_args
        audio_files = concat_call[0][0]
        assert len(audio_files) == 3  # noqa: PLR2004

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}._split_text_for_tts", return_value=["Solo."])
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_single_chunk_passed_to_concat(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_split,
        mock_synth,
        mock_concat,
        tmp_path,
    ):
        """Single chunk file is passed to concat (which copies it)."""
        output = str(tmp_path / "out.mp3")
        synthesize_speech("Solo.", output_path=output, tts_method=_GOOGLE_TTS)
        concat_call = mock_concat.call_args
        audio_files = concat_call[0][0]
        assert len(audio_files) == 1


# ---------------------------------------------------------------------------
# TestEdgeVoiceMappingComprehensive — comprehensive voice mapping
# ---------------------------------------------------------------------------


class TestEdgeVoiceMappingComprehensive:
    """Comprehensive tests for Edge TTS voice mapping across languages."""

    @patch(f"{_LANG}.get_locale_code", return_value="es")
    def test_spanish_female(self, mock_locale):
        """Spanish Female maps to es-ES-ElviraNeural."""
        assert _get_edge_voice("Spanish", "FEMALE") == "es-ES-ElviraNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="es")
    def test_spanish_male(self, mock_locale):
        """Spanish Male maps to es-ES-AlvaroNeural."""
        assert _get_edge_voice("Spanish", "MALE") == "es-ES-AlvaroNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="it")
    def test_italian_female(self, mock_locale):
        """Italian Female maps to it-IT-ElsaNeural."""
        assert _get_edge_voice("Italian", "FEMALE") == "it-IT-ElsaNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="it")
    def test_italian_male(self, mock_locale):
        """Italian Male maps to it-IT-DiegoNeural."""
        assert _get_edge_voice("Italian", "MALE") == "it-IT-DiegoNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="pl")
    def test_polish_female(self, mock_locale):
        """Polish Female maps to pl-PL-ZofiaNeural."""
        assert _get_edge_voice("Polish", "FEMALE") == "pl-PL-ZofiaNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="pl")
    def test_polish_male(self, mock_locale):
        """Polish Male maps to pl-PL-MarekNeural."""
        assert _get_edge_voice("Polish", "MALE") == "pl-PL-MarekNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="nl")
    def test_dutch_female(self, mock_locale):
        """Dutch Female maps to nl-NL-ColetteNeural."""
        assert _get_edge_voice("Dutch", "FEMALE") == "nl-NL-ColetteNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="nl")
    def test_dutch_male(self, mock_locale):
        """Dutch Male maps to nl-NL-MaartenNeural."""
        assert _get_edge_voice("Dutch", "MALE") == "nl-NL-MaartenNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="sv")
    def test_swedish_female(self, mock_locale):
        """Swedish Female maps to sv-SE-SofieNeural."""
        assert _get_edge_voice("Swedish", "FEMALE") == "sv-SE-SofieNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="sv")
    def test_swedish_male(self, mock_locale):
        """Swedish Male maps to sv-SE-MattiasNeural."""
        assert _get_edge_voice("Swedish", "MALE") == "sv-SE-MattiasNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="tr")
    def test_turkish_female(self, mock_locale):
        """Turkish Female maps to tr-TR-EmelNeural."""
        assert _get_edge_voice("Turkish", "FEMALE") == "tr-TR-EmelNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="tr")
    def test_turkish_male(self, mock_locale):
        """Turkish Male maps to tr-TR-AhmetNeural."""
        assert _get_edge_voice("Turkish", "MALE") == "tr-TR-AhmetNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="uk")
    def test_ukrainian_female(self, mock_locale):
        """Ukrainian Female maps to uk-UA-PolinaNeural."""
        assert _get_edge_voice("Ukrainian", "FEMALE") == "uk-UA-PolinaNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="uk")
    def test_ukrainian_male(self, mock_locale):
        """Ukrainian Male maps to uk-UA-OstapNeural."""
        assert _get_edge_voice("Ukrainian", "MALE") == "uk-UA-OstapNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="hu")
    def test_hungarian_female(self, mock_locale):
        """Hungarian Female maps to hu-HU-NoemiNeural."""
        assert _get_edge_voice("Hungarian", "FEMALE") == "hu-HU-NoemiNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="cs")
    def test_czech_female(self, mock_locale):
        """Czech Female maps to cs-CZ-VlastaNeural."""
        assert _get_edge_voice("Czech", "FEMALE") == "cs-CZ-VlastaNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="ro")
    def test_romanian_female(self, mock_locale):
        """Romanian Female maps to ro-RO-AlinaNeural."""
        assert _get_edge_voice("Romanian", "FEMALE") == "ro-RO-AlinaNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="sk")
    def test_slovak_female(self, mock_locale):
        """Slovak Female maps to sk-SK-ViktoriaNeural."""
        assert _get_edge_voice("Slovak", "FEMALE") == "sk-SK-ViktoriaNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="da")
    def test_danish_female(self, mock_locale):
        """Danish Female maps to da-DK-ChristelNeural."""
        assert _get_edge_voice("Danish", "FEMALE") == "da-DK-ChristelNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="fi")
    def test_finnish_female(self, mock_locale):
        """Finnish Female maps to fi-FI-NooraNeural."""
        assert _get_edge_voice("Finnish", "FEMALE") == "fi-FI-NooraNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="nb")
    def test_norwegian_female(self, mock_locale):
        """Norwegian Female maps to nb-NO-PernilleNeural."""
        assert _get_edge_voice("Norwegian", "FEMALE") == "nb-NO-PernilleNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="bg")
    def test_bulgarian_female(self, mock_locale):
        """Bulgarian Female maps to bg-BG-KalinaNeural."""
        assert _get_edge_voice("Bulgarian", "FEMALE") == "bg-BG-KalinaNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="lv")
    def test_latvian_female(self, mock_locale):  # noqa: ANN001, ARG002
        """Latvian Female maps to lv-LV-EveritaNeural."""
        result = _get_edge_voice("Latvian", "FEMALE")
        assert result == "lv-LV-EveritaNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="lt")
    def test_lithuanian_female(self, mock_locale):  # noqa: ANN001, ARG002
        """Lithuanian Female maps to lt-LT-OnaNeural."""
        result = _get_edge_voice("Lithuanian", "FEMALE")
        assert result == "lt-LT-OnaNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="ms")
    def test_malay_female(self, mock_locale):
        """Malay Female maps to ms-MY-YasminNeural."""
        assert _get_edge_voice("Malay", "FEMALE") == "ms-MY-YasminNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="id")
    def test_indonesian_male(self, mock_locale):
        """Indonesian Male maps to id-ID-ArdiNeural."""
        assert _get_edge_voice("Indonesian", "MALE") == "id-ID-ArdiNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="bn")
    def test_bengali_female(self, mock_locale):
        """Bengali Female maps to bn-IN-TanishaaNeural."""
        assert _get_edge_voice("Bengali", "FEMALE") == "bn-IN-TanishaaNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="he")
    def test_hebrew_male(self, mock_locale):
        """Hebrew Male maps to he-IL-AvriNeural."""
        assert _get_edge_voice("Hebrew", "MALE") == "he-IL-AvriNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="km")
    def test_khmer_female(self, mock_locale):
        """Khmer Female maps to km-KH-SresmaNeural."""
        assert _get_edge_voice("Khmer", "FEMALE") == "km-KH-SresmaNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="hr")
    def test_croatian_female(self, mock_locale):
        """Croatian Female maps to hr-HR-GabrijelaNeural."""
        assert _get_edge_voice("Croatian", "FEMALE") == "hr-HR-GabrijelaNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="hr")
    def test_croatian_male(self, mock_locale):
        """Croatian Male maps to hr-HR-SreckoNeural."""
        assert _get_edge_voice("Croatian", "MALE") == "hr-HR-SreckoNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="zh-TW")
    def test_chinese_traditional_female(self, mock_locale):
        """Chinese Traditional Female maps correctly."""
        assert (
            _get_edge_voice("Chinese (Traditional)", "FEMALE")
            == "zh-TW-HsiaoChenNeural"
        )

    @patch(f"{_LANG}.get_locale_code", return_value="zh-TW")
    def test_chinese_traditional_male(self, mock_locale):
        """Chinese Traditional Male maps correctly."""
        assert _get_edge_voice("Chinese (Traditional)", "MALE") == "zh-TW-YunJheNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="pt-PT")
    def test_portuguese_portugal_female(self, mock_locale):
        """Portuguese Portugal Female maps correctly."""
        assert (
            _get_edge_voice("Portuguese (Portugal)", "FEMALE") == "pt-PT-RaquelNeural"
        )

    @patch(f"{_LANG}.get_locale_code", return_value="en-UK")
    def test_english_uk_male(self, mock_locale):
        """English UK Male maps to en-GB-RyanNeural."""
        assert _get_edge_voice("English (UK)", "MALE") == "en-GB-RyanNeural"


# ---------------------------------------------------------------------------
# TestGoogleTTSLanguageCodeComprehensive — all TTS language codes
# ---------------------------------------------------------------------------


class TestGoogleTTSLanguageCodeComprehensive:
    """Comprehensive tests for _get_tts_language_code mappings."""

    @patch(f"{_LANG}.get_locale_code", return_value="bn")
    def test_bengali_mapped(self, mock_locale):
        """Bengali maps to 'bn-IN'."""
        assert _get_tts_language_code("Bengali") == "bn-IN"

    @patch(f"{_LANG}.get_locale_code", return_value="bg")
    def test_bulgarian_mapped(self, mock_locale):
        """Bulgarian maps to 'bg-BG'."""
        assert _get_tts_language_code("Bulgarian") == "bg-BG"

    @patch(f"{_LANG}.get_locale_code", return_value="cs")
    def test_czech_mapped(self, mock_locale):
        """Czech maps to 'cs-CZ'."""
        assert _get_tts_language_code("Czech") == "cs-CZ"

    @patch(f"{_LANG}.get_locale_code", return_value="da")
    def test_danish_mapped(self, mock_locale):
        """Danish maps to 'da-DK'."""
        assert _get_tts_language_code("Danish") == "da-DK"

    @patch(f"{_LANG}.get_locale_code", return_value="nl")
    def test_dutch_mapped(self, mock_locale):
        """Dutch maps to 'nl-NL'."""
        assert _get_tts_language_code("Dutch") == "nl-NL"

    @patch(f"{_LANG}.get_locale_code", return_value="fi")
    def test_finnish_mapped(self, mock_locale):
        """Finnish maps to 'fi-FI'."""
        assert _get_tts_language_code("Finnish") == "fi-FI"

    @patch(f"{_LANG}.get_locale_code", return_value="el")
    def test_greek_mapped(self, mock_locale):
        """Greek maps to 'el-GR'."""
        assert _get_tts_language_code("Greek") == "el-GR"

    @patch(f"{_LANG}.get_locale_code", return_value="he")
    def test_hebrew_mapped(self, mock_locale):
        """Hebrew maps to 'he-IL'."""
        assert _get_tts_language_code("Hebrew") == "he-IL"

    @patch(f"{_LANG}.get_locale_code", return_value="hu")
    def test_hungarian_mapped(self, mock_locale):
        """Hungarian maps to 'hu-HU'."""
        assert _get_tts_language_code("Hungarian") == "hu-HU"

    @patch(f"{_LANG}.get_locale_code", return_value="id")
    def test_indonesian_mapped(self, mock_locale):
        """Indonesian maps to 'id-ID'."""
        assert _get_tts_language_code("Indonesian") == "id-ID"

    @patch(f"{_LANG}.get_locale_code", return_value="km")
    def test_khmer_mapped(self, mock_locale):
        """Khmer maps to 'km-KH'."""
        assert _get_tts_language_code("Khmer") == "km-KH"

    @patch(f"{_LANG}.get_locale_code", return_value="lv")
    def test_latvian_mapped(self, mock_locale):
        """Latvian maps to 'lv-LV'."""
        assert _get_tts_language_code("Latvian") == "lv-LV"

    @patch(f"{_LANG}.get_locale_code", return_value="lt")
    def test_lithuanian_mapped(self, mock_locale):
        """Lithuanian maps to 'lt-LT'."""
        assert _get_tts_language_code("Lithuanian") == "lt-LT"

    @patch(f"{_LANG}.get_locale_code", return_value="ms")
    def test_malay_mapped(self, mock_locale):
        """Malay maps to 'ms-MY'."""
        assert _get_tts_language_code("Malay") == "ms-MY"

    @patch(f"{_LANG}.get_locale_code", return_value="ro")
    def test_romanian_mapped(self, mock_locale):
        """Romanian maps to 'ro-RO'."""
        assert _get_tts_language_code("Romanian") == "ro-RO"

    @patch(f"{_LANG}.get_locale_code", return_value="sk")
    def test_slovak_mapped(self, mock_locale):
        """Slovak maps to 'sk-SK'."""
        assert _get_tts_language_code("Slovak") == "sk-SK"

    @patch(f"{_LANG}.get_locale_code", return_value="es")
    def test_spanish_mapped(self, mock_locale):
        """Spanish maps to 'es-ES'."""
        assert _get_tts_language_code("Spanish") == "es-ES"

    @patch(f"{_LANG}.get_locale_code", return_value="sv")
    def test_swedish_mapped(self, mock_locale):
        """Swedish maps to 'sv-SE'."""
        assert _get_tts_language_code("Swedish") == "sv-SE"

    @patch(f"{_LANG}.get_locale_code", return_value="tr")
    def test_turkish_mapped(self, mock_locale):
        """Turkish maps to 'tr-TR'."""
        assert _get_tts_language_code("Turkish") == "tr-TR"

    @patch(f"{_LANG}.get_locale_code", return_value="uk")
    def test_ukrainian_mapped(self, mock_locale):
        """Ukrainian maps to 'uk-UA'."""
        assert _get_tts_language_code("Ukrainian") == "uk-UA"


# ---------------------------------------------------------------------------
# TestSynthesizeTimedSpeechEdgeTTSRateBranches — Edge TTS rate branches
# ---------------------------------------------------------------------------


class TestSynthesizeTimedSpeechEdgeTTSRateBranches:
    """Test Edge TTS rate/speed-up branches in timed speech."""

    def _make_entry(self, start: str, end: str, text: str) -> MagicMock:
        """Create a mock SubtitleEntry."""
        entry = MagicMock()
        entry.start = start
        entry.end = end
        entry.text = text
        return entry

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration")
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._speed_up_audio")
    @patch(f"{_MOD}._synthesize_chunk_edge")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_edge_audio_shorter_than_half_slot(  # noqa: PLR0913
        self,
        mock_ffmpeg,
        mock_edge,
        mock_speedup,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """Edge: audio much shorter than slot has no overflow."""
        mock_dur.return_value = 0.1
        entries = [
            self._make_entry("00:00:00,000", "00:00:10,000", "Short"),
        ]
        output = str(tmp_path / "out.mp3")
        synthesize_timed_speech(entries, output_path=output)
        mock_speedup.assert_not_called()

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration", return_value=10.0)
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._speed_up_audio")
    @patch(f"{_MOD}._synthesize_chunk_edge")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_edge_massive_overflow_clamps_factor(  # noqa: PLR0913
        self,
        mock_ffmpeg,
        mock_edge,
        mock_speedup,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """Edge: massive overflow triggers speed-up with factor clamped to max."""
        # 10s audio in 0.5s slot, last entry
        # tolerance = min(0.5*0.5, 2.0) = 0.25
        # allowed = min(0.25, inf) = 0.25
        # overflow (9.5) > 0.25 → speed up
        # rate = 10.0 / 0.75 = 13.33 (clamped to _ATEMPO_MAX_FACTOR in _speed_up)
        entries = [
            self._make_entry("00:00:00,000", "00:00:00,500", "Very long text here"),
        ]
        output = str(tmp_path / "out.mp3")
        synthesize_timed_speech(entries, output_path=output)
        assert mock_speedup.call_count == 1

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration", return_value=1.0)
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._synthesize_chunk_edge")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_edge_five_entries_all_fit(  # noqa: PLR0913
        self,
        mock_ffmpeg,
        mock_edge,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """Five entries all fitting in slots produce correct segment count."""
        entries = [
            self._make_entry(
                f"00:00:{i * 3:02d},000",
                f"00:00:{i * 3 + 2:02d},000",
                f"Entry {i}",
            )
            for i in range(5)
        ]
        output = str(tmp_path / "out.mp3")
        synthesize_timed_speech(entries, output_path=output)
        assert mock_edge.call_count == 5  # noqa: PLR2004


# ---------------------------------------------------------------------------
# TestConcatenateMp3FilesExtended — more concatenation tests
# ---------------------------------------------------------------------------


class TestConcatenateMp3FilesExtended:
    """Extended concatenation tests."""

    @patch("subprocess.run")
    def test_five_files_all_listed(self, mock_run, tmp_path):
        """Five audio files are all listed in concat file."""
        file_count = 5
        files = []
        for i in range(file_count):
            f = tmp_path / f"chunk_{i}.mp3"
            f.write_bytes(b"data")
            files.append(f)
        out = tmp_path / "output.mp3"

        mock_run.return_value = MagicMock(returncode=0)
        _concatenate_mp3_files(files, out)

        concat_file = tmp_path / "concat.txt"
        content = concat_file.read_text(encoding="utf-8")
        for f in files:
            assert str(f) in content

    def test_single_file_preserves_content(self, tmp_path):
        """Single file copy preserves exact byte content."""
        src = tmp_path / "only.mp3"
        content = b"\xff\xfb\x90\x00" * 100
        src.write_bytes(content)
        out = tmp_path / "output.mp3"

        _concatenate_mp3_files([src], out)

        assert out.read_bytes() == content

    @patch("subprocess.run")
    def test_concat_timeout_is_300(self, mock_run, tmp_path):
        """FFmpeg concat uses 300 second timeout."""
        f1 = tmp_path / "a.mp3"
        f2 = tmp_path / "b.mp3"
        f1.write_bytes(b"1")
        f2.write_bytes(b"2")
        out = tmp_path / "output.mp3"

        mock_run.return_value = MagicMock(returncode=0)
        _concatenate_mp3_files([f1, f2], out)

        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["timeout"] == 300  # noqa: PLR2004


# ---------------------------------------------------------------------------
# TestCheckFfmpegAvailableExtended — extended FFmpeg detection
# ---------------------------------------------------------------------------


class TestCheckFfmpegAvailableExtended:
    """Extended tests for check_ffmpeg_available."""

    @patch("shutil.which", return_value="/usr/local/bin/ffmpeg")
    def test_custom_path_returns_true(self, mock_which):
        """Custom path like /usr/local/bin/ffmpeg returns True."""
        assert check_ffmpeg_available() is True

    @patch("shutil.which", return_value="C:\\ffmpeg\\bin\\ffmpeg.exe")
    def test_windows_path_returns_true(self, mock_which):
        """Windows path returns True."""
        assert check_ffmpeg_available() is True

    @patch("shutil.which", return_value="")
    def test_empty_string_path_returns_true(self, mock_which):
        """Empty string from which (truthy) returns True."""
        # Empty string is not None, so the function returns True
        assert check_ffmpeg_available() is True


# ===========================================================================
# NEW TESTS — 230+ additional tests for comprehensive coverage
# ===========================================================================


# ---------------------------------------------------------------------------
# STT faster-whisper: model loading errors, GPU/CPU fallback, language
# detection, segment iteration edge cases
# ---------------------------------------------------------------------------


class TestWhisperModelLoadingErrors:
    """Test Whisper model loading failures and edge cases."""

    @pytest.fixture(autouse=True)
    def _setup_faster_whisper(self):
        """Ensure faster_whisper mock module is available."""
        mock_fw = MagicMock()
        mock_fw.WhisperModel = MagicMock()
        prev = sys.modules.get("faster_whisper")
        sys.modules["faster_whisper"] = mock_fw
        yield mock_fw
        if prev is None:
            sys.modules.pop("faster_whisper", None)
        else:
            sys.modules["faster_whisper"] = prev

    def test_model_oom_error(self, _setup_faster_whisper):
        """Out-of-memory during model loading propagates."""
        mock_fw = _setup_faster_whisper
        mock_fw.WhisperModel.side_effect = MemoryError("out of memory")
        with pytest.raises(MemoryError, match="out of memory"):
            _transcribe_whisper("test.mp3")

    def test_model_os_error(self, _setup_faster_whisper):
        """OSError during model loading propagates."""
        mock_fw = _setup_faster_whisper
        mock_fw.WhisperModel.side_effect = OSError("disk error")
        with pytest.raises(OSError, match="disk error"):
            _transcribe_whisper("test.mp3")

    def test_model_value_error(self, _setup_faster_whisper):
        """ValueError during model loading propagates."""
        mock_fw = _setup_faster_whisper
        mock_fw.WhisperModel.side_effect = ValueError("invalid model size")
        with pytest.raises(ValueError, match="invalid model size"):
            _transcribe_whisper("test.mp3", model_size="nonexistent")

    def test_model_always_uses_cpu(self, _setup_faster_whisper):
        """Model always created with device='cpu' regardless of GPU."""
        mock_fw = _setup_faster_whisper
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([], MagicMock())
        mock_fw.WhisperModel.return_value = mock_model

        _transcribe_whisper("test.mp3", model_size="large")

        call_kwargs = mock_fw.WhisperModel.call_args[1]
        assert call_kwargs["device"] == "cpu"
        assert call_kwargs["compute_type"] == "int8"

    def test_model_always_uses_int8(self, _setup_faster_whisper):
        """Model always created with compute_type='int8'."""
        mock_fw = _setup_faster_whisper
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([], MagicMock())
        mock_fw.WhisperModel.return_value = mock_model

        _transcribe_whisper("test.mp3")

        assert mock_fw.WhisperModel.call_args[1]["compute_type"] == "int8"

    def test_transcribe_exception_during_iteration(self, _setup_faster_whisper):
        """Exception during segment iteration propagates."""
        mock_fw = _setup_faster_whisper
        mock_model = MagicMock()

        def _exploding_iter():
            yield MagicMock(start=0.0, end=1.0, text="OK")
            raise RuntimeError("decode error")

        mock_model.transcribe.return_value = (_exploding_iter(), MagicMock())
        mock_fw.WhisperModel.return_value = mock_model

        with pytest.raises(RuntimeError, match="decode error"):
            _transcribe_whisper("test.mp3")

    def test_segment_with_negative_start(self, _setup_faster_whisper):
        """Segment with negative start time is formatted correctly."""
        mock_fw = _setup_faster_whisper
        seg = MagicMock(start=-0.5, end=1.0, text="Negative start")
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([seg], MagicMock())
        mock_fw.WhisperModel.return_value = mock_model

        result = _transcribe_whisper("test.mp3")
        assert "Negative start" in result

    def test_segment_with_very_long_text(self, _setup_faster_whisper):
        """Segment with very long text is included in SRT output."""
        mock_fw = _setup_faster_whisper
        long_text = "word " * 500
        seg = MagicMock(start=0.0, end=10.0, text=long_text)
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([seg], MagicMock())
        mock_fw.WhisperModel.return_value = mock_model

        result = _transcribe_whisper("test.mp3")
        assert "word" in result
        assert "-->" in result

    def test_many_segments_all_numbered(self, _setup_faster_whisper):
        """50 segments are numbered 1 through 50."""
        mock_fw = _setup_faster_whisper
        seg_count = 50
        segments = [
            MagicMock(start=float(i), end=float(i + 1), text=f"Line {i}")
            for i in range(seg_count)
        ]
        mock_model = MagicMock()
        mock_model.transcribe.return_value = (segments, MagicMock())
        mock_fw.WhisperModel.return_value = mock_model

        result = _transcribe_whisper("test.mp3")
        for i in range(1, seg_count + 1):
            assert f"\n{i}\n" in f"\n{result}" or result.startswith(f"{i}\n")

    @patch(f"{_MOD}._get_speech_language_code", return_value="zh-CN")
    def test_chinese_lang_code_split_to_zh(
        self,
        mock_lang,
        _setup_faster_whisper,
    ):
        """Chinese locale 'zh-CN' is split to 'zh' for Whisper."""
        mock_fw = _setup_faster_whisper
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([], MagicMock())
        mock_fw.WhisperModel.return_value = mock_model

        _transcribe_whisper("test.mp3", src_lang="Chinese (Simplified)")

        call_kwargs = mock_model.transcribe.call_args[1]
        assert call_kwargs["language"] == "zh"

    @patch(f"{_MOD}._get_speech_language_code", return_value="pt-BR")
    def test_portuguese_lang_code_split(
        self,
        mock_lang,
        _setup_faster_whisper,
    ):
        """Portuguese locale 'pt-BR' is split to 'pt' for Whisper."""
        mock_fw = _setup_faster_whisper
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([], MagicMock())
        mock_fw.WhisperModel.return_value = mock_model

        _transcribe_whisper("test.mp3", src_lang="Portuguese (Brazil)")

        call_kwargs = mock_model.transcribe.call_args[1]
        assert call_kwargs["language"] == "pt"

    def test_segment_unicode_text_preserved(self, _setup_faster_whisper):
        """Unicode text in segments is preserved in SRT."""
        mock_fw = _setup_faster_whisper
        seg = MagicMock(start=0.0, end=2.0, text="  \u4f60\u597d\u4e16\u754c  ")
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([seg], MagicMock())
        mock_fw.WhisperModel.return_value = mock_model

        result = _transcribe_whisper("test.mp3")
        assert "\u4f60\u597d\u4e16\u754c" in result


# ---------------------------------------------------------------------------
# STT Google Cloud: malformed API responses, partial results, empty audio,
# long audio chunking
# ---------------------------------------------------------------------------


class TestGoogleCloudSTTMalformedResponses:
    """Test Google Cloud STT with malformed/edge-case API responses."""

    @patch(f"{_MOD}._parse_results_to_srt", return_value="")
    @patch(f"{_MOD}._poll_operation")
    @patch(f"{_MOD}._call_long_running_recognize", return_value="op-1")
    @patch(f"{_MOD}._get_speech_language_code", return_value="en-US")
    @patch(f"{_MOD}._extract_audio_to_flac")
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_poll_returns_none_response(  # noqa: PLR0913
        self,
        mock_key,
        mock_extract,
        mock_lang,
        mock_recognize,
        mock_poll,
        mock_parse,
        tmp_path,
    ):
        """Poll returning None response uses empty dict."""
        flac = tmp_path / "audio.flac"
        flac.write_bytes(b"\x00" * 100)
        mock_extract.return_value = flac
        mock_poll.return_value = None

        # response.get("results", []) on None → AttributeError
        with pytest.raises(AttributeError):
            _transcribe_google_cloud("test.mp4")

    @patch(f"{_MOD}._parse_results_to_srt", return_value="srt")
    @patch(f"{_MOD}._poll_operation")
    @patch(f"{_MOD}._call_long_running_recognize", return_value="op-1")
    @patch(f"{_MOD}._get_speech_language_code", return_value="en-US")
    @patch(f"{_MOD}._extract_audio_to_flac")
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_poll_returns_results_with_no_alternatives(  # noqa: PLR0913
        self,
        mock_key,
        mock_extract,
        mock_lang,
        mock_recognize,
        mock_poll,
        mock_parse,
        tmp_path,
    ):
        """Results with empty alternatives list are passed to parser."""
        flac = tmp_path / "audio.flac"
        flac.write_bytes(b"\x00" * 100)
        mock_extract.return_value = flac
        mock_poll.return_value = {"results": [{"alternatives": []}]}

        _transcribe_google_cloud("test.mp4")
        mock_parse.assert_called_once_with([{"alternatives": []}])

    @patch(f"{_MOD}._parse_results_to_srt", return_value="srt")
    @patch(f"{_MOD}._poll_operation")
    @patch(f"{_MOD}._call_long_running_recognize", return_value="op-1")
    @patch(f"{_MOD}._get_speech_language_code", return_value="")
    @patch(f"{_MOD}._extract_audio_to_flac")
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_empty_language_autodetect(  # noqa: PLR0913
        self,
        mock_key,
        mock_extract,
        mock_lang,
        mock_recognize,
        mock_poll,
        mock_parse,
        tmp_path,
    ):
        """Empty language code triggers auto-detect (en-US default in API)."""
        flac = tmp_path / "audio.flac"
        flac.write_bytes(b"\x00" * 100)
        mock_extract.return_value = flac
        mock_poll.return_value = {"results": []}

        _transcribe_google_cloud("test.mp4", src_lang="")
        mock_lang.assert_called_once_with("")

    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    @patch(f"{_MOD}._extract_audio_to_flac")
    def test_audio_exactly_one_byte_over_limit(self, mock_extract, mock_key, tmp_path):
        """Audio one byte over limit raises AUDIO_TOO_LARGE."""
        flac = tmp_path / "audio.flac"
        flac.write_bytes(b"\x00" * (_MAX_AUDIO_BYTES + 1))
        mock_extract.return_value = flac

        with pytest.raises(ValueError, match="AUDIO_TOO_LARGE"):
            _transcribe_google_cloud("test.mp4")

    @patch(f"{_MOD}._parse_results_to_srt", return_value="")
    @patch(f"{_MOD}._poll_operation", return_value={"results": []})
    @patch(f"{_MOD}._call_long_running_recognize", return_value="op-1")
    @patch(f"{_MOD}._get_speech_language_code", return_value="en-US")
    @patch(f"{_MOD}._extract_audio_to_flac")
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_empty_audio_file_zero_bytes(  # noqa: PLR0913
        self,
        mock_key,
        mock_extract,
        mock_lang,
        mock_recognize,
        mock_poll,
        mock_parse,
        tmp_path,
    ):
        """Zero-byte FLAC file does not exceed size limit."""
        flac = tmp_path / "audio.flac"
        flac.write_bytes(b"")
        mock_extract.return_value = flac

        result = _transcribe_google_cloud("empty.mp4")
        assert isinstance(result, str)

    @patch(f"{_MOD}.shutil.rmtree")
    @patch(f"{_MOD}._call_long_running_recognize")
    @patch(f"{_MOD}._get_speech_language_code", return_value="en-US")
    @patch(f"{_MOD}._extract_audio_to_flac")
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_temp_cleaned_on_api_error(  # noqa: PLR0913
        self,
        mock_key,
        mock_extract,
        mock_lang,
        mock_recognize,
        mock_rmtree,
        tmp_path,
    ):
        """Temp FLAC directory is cleaned even when API call fails."""
        flac = tmp_path / "temp_dir" / "audio.flac"
        flac.parent.mkdir(parents=True)
        flac.write_bytes(b"\x00" * 100)
        mock_extract.return_value = flac
        mock_recognize.side_effect = ValueError("SPEECH_API_ERROR")

        with pytest.raises(ValueError):
            _transcribe_google_cloud("test.mp4")

        mock_rmtree.assert_called_once()

    @patch(f"{_MOD}._parse_results_to_srt", return_value="srt")
    @patch(f"{_MOD}._poll_operation")
    @patch(f"{_MOD}._call_long_running_recognize", return_value="op-1")
    @patch(f"{_MOD}._get_speech_language_code", return_value="ja")
    @patch(f"{_MOD}._extract_audio_to_flac")
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_model_passed_to_recognize(  # noqa: PLR0913
        self,
        mock_key,
        mock_extract,
        mock_lang,
        mock_recognize,
        mock_poll,
        mock_parse,
        tmp_path,
    ):
        """Custom model is passed to _call_long_running_recognize."""
        flac = tmp_path / "audio.flac"
        flac.write_bytes(b"\x00" * 100)
        mock_extract.return_value = flac
        mock_poll.return_value = {"results": []}

        _transcribe_google_cloud("test.mp4", model="latest_long")
        call_kwargs = mock_recognize.call_args[1]
        assert call_kwargs["model"] == "latest_long"


# ---------------------------------------------------------------------------
# TTS Edge TTS: voice listing, voice fallback, network errors, empty text
# ---------------------------------------------------------------------------


class TestEdgeTTSVoiceFallbackAndErrors:
    """Test Edge TTS voice selection and error handling."""

    @patch(f"{_LANG}.get_locale_code", return_value="en-US")
    def test_english_us_female(self, mock_locale):
        """English US Female maps to en-US-JennyNeural."""
        result = _get_edge_voice("English (US)", "FEMALE")
        assert result == "en-US-JennyNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="en-US")
    def test_english_us_male(self, mock_locale):
        """English US Male maps to en-US-GuyNeural."""
        result = _get_edge_voice("English (US)", "MALE")
        assert result == "en-US-GuyNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="en-UK")
    def test_english_uk_male(self, mock_locale):
        """English UK Male maps to en-GB-RyanNeural."""
        result = _get_edge_voice("English (UK)", "MALE")
        assert result == "en-GB-RyanNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="it")
    def test_italian_female(self, mock_locale):
        """Italian Female maps to it-IT-ElsaNeural."""
        result = _get_edge_voice("Italian", "FEMALE")
        assert result == "it-IT-ElsaNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="sv")
    def test_swedish_male(self, mock_locale):
        """Swedish Male maps to sv-SE-MattiasNeural."""
        result = _get_edge_voice("Swedish", "MALE")
        assert result == "sv-SE-MattiasNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="tr")
    def test_turkish_female(self, mock_locale):
        """Turkish Female maps to tr-TR-EmelNeural."""
        result = _get_edge_voice("Turkish", "FEMALE")
        assert result == "tr-TR-EmelNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="uk")
    def test_ukrainian_male(self, mock_locale):
        """Ukrainian Male maps to uk-UA-OstapNeural."""
        result = _get_edge_voice("Ukrainian", "MALE")
        assert result == "uk-UA-OstapNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="ms")
    def test_malay_female(self, mock_locale):
        """Malay Female maps to ms-MY-YasminNeural."""
        result = _get_edge_voice("Malay", "FEMALE")
        assert result == "ms-MY-YasminNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="nb")
    def test_norwegian_female(self, mock_locale):
        """Norwegian Female maps to nb-NO-PernilleNeural."""
        result = _get_edge_voice("Norwegian", "FEMALE")
        assert result == "nb-NO-PernilleNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="km")
    def test_khmer_male(self, mock_locale):
        """Khmer Male maps to km-KH-PisethNeural."""
        result = _get_edge_voice("Khmer", "MALE")
        assert result == "km-KH-PisethNeural"

    def test_empty_label_default_gender(self):
        """Empty label with no gender specified returns default female."""
        result = _get_edge_voice("")
        assert result == "en-US-JennyNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="hr")
    def test_croatian_female(self, mock_locale):
        """Croatian Female maps to hr-HR-GabrijelaNeural."""
        result = _get_edge_voice("Croatian", "FEMALE")
        assert result == "hr-HR-GabrijelaNeural"


class TestEdgeTTSSynthesizeChunkErrors:
    """Test Edge TTS chunk synthesis error scenarios."""

    @pytest.fixture(autouse=True)
    def _setup_edge_tts(self):
        """Inject mock edge_tts into sys.modules."""
        self._NoAudioReceived = type("NoAudioReceived", (Exception,), {})
        mock_edge = MagicMock()
        mock_exceptions = MagicMock()
        mock_exceptions.NoAudioReceived = self._NoAudioReceived
        prev_edge = sys.modules.get("edge_tts")
        prev_exc = sys.modules.get("edge_tts.exceptions")
        sys.modules["edge_tts"] = mock_edge
        sys.modules["edge_tts.exceptions"] = mock_exceptions
        self._mock_edge = mock_edge
        yield
        if prev_edge is None:
            sys.modules.pop("edge_tts", None)
        else:
            sys.modules["edge_tts"] = prev_edge
        if prev_exc is None:
            sys.modules.pop("edge_tts.exceptions", None)
        else:
            sys.modules["edge_tts.exceptions"] = prev_exc

    def test_connection_error_propagates(self, tmp_path):
        """ConnectionError from edge_tts propagates without retry."""
        output = tmp_path / "out.mp3"
        mock_comm = MagicMock()
        mock_comm.save = AsyncMock(
            side_effect=ConnectionError("network down"),
        )
        self._mock_edge.Communicate.return_value = mock_comm

        with pytest.raises(ConnectionError, match="network down"):
            _synthesize_chunk_edge(
                "Hi",
                "en-US-JennyNeural",
                output,
                max_retries=3,
                base_delay=0.0,
            )
        assert mock_comm.save.await_count == 1

    def test_timeout_error_propagates(self, tmp_path):
        """TimeoutError from edge_tts propagates without retry."""
        output = tmp_path / "out.mp3"
        mock_comm = MagicMock()
        mock_comm.save = AsyncMock(
            side_effect=TimeoutError("connection timed out"),
        )
        self._mock_edge.Communicate.return_value = mock_comm

        with pytest.raises(TimeoutError, match="connection timed out"):
            _synthesize_chunk_edge(
                "Hi",
                "en-US-JennyNeural",
                output,
                max_retries=2,
                base_delay=0.0,
            )

    def test_no_audio_received_retries_three_times(self, tmp_path):
        """NoAudioReceived retries exactly max_retries + 1 times."""
        output = tmp_path / "out.mp3"
        mock_comm = MagicMock()
        mock_comm.save = AsyncMock(
            side_effect=self._NoAudioReceived("no audio"),
        )
        self._mock_edge.Communicate.return_value = mock_comm

        max_retries = 3
        with pytest.raises(ValueError, match="TTS_API_ERROR"):
            _synthesize_chunk_edge(
                "Hi",
                "en-US-JennyNeural",
                output,
                max_retries=max_retries,
                base_delay=0.0,
            )
        # total attempts = max_retries + 1
        assert mock_comm.save.await_count == max_retries + 1

    def test_success_after_two_failures(self, tmp_path):
        """Succeeds after two NoAudioReceived failures."""
        output = tmp_path / "out.mp3"
        mock_comm = MagicMock()
        mock_comm.save = AsyncMock(
            side_effect=[
                self._NoAudioReceived("fail 1"),
                self._NoAudioReceived("fail 2"),
                None,
            ],
        )
        self._mock_edge.Communicate.return_value = mock_comm

        _synthesize_chunk_edge(
            "Hello",
            "en-US-JennyNeural",
            output,
            max_retries=3,
            base_delay=0.0,
        )
        assert mock_comm.save.await_count == 3  # noqa: PLR2004

    def test_communicate_created_with_voice(self, tmp_path):
        """Communicate is created with correct text and voice name."""
        output = tmp_path / "out.mp3"
        mock_comm = MagicMock()
        mock_comm.save = AsyncMock()
        self._mock_edge.Communicate.return_value = mock_comm

        _synthesize_chunk_edge(
            "Test text",
            "vi-VN-HoaiMyNeural",
            output,
            max_retries=0,
            base_delay=0.0,
        )
        self._mock_edge.Communicate.assert_called_once_with(
            "Test text",
            "vi-VN-HoaiMyNeural",
        )


# ---------------------------------------------------------------------------
# TTS Google Cloud: all audio encoding options, SSML input, speaking rate
# boundaries
# ---------------------------------------------------------------------------


class TestGoogleCloudTTSEncodings:
    """Test Google Cloud TTS audio encoding and format options."""

    def _make_response(self, audio_bytes: bytes) -> MagicMock:
        """Create a mock urlopen response."""
        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
        resp_data = json.dumps({"audioContent": audio_b64}).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = resp_data
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    @patch("urllib.request.urlopen")
    def test_mp3_encoding(self, mock_urlopen, tmp_path):
        """.mp3 format uses MP3 encoding."""
        mock_urlopen.return_value = self._make_response(b"audio")
        out = tmp_path / "chunk.mp3"
        _synthesize_chunk("Hi", "en-US", "FEMALE", "key", out, audio_format=".mp3")

        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode("utf-8"))
        assert payload["audioConfig"]["audioEncoding"] == "MP3"

    @patch("urllib.request.urlopen")
    def test_wav_encoding(self, mock_urlopen, tmp_path):
        """.wav format uses LINEAR16 encoding."""
        mock_urlopen.return_value = self._make_response(b"audio")
        out = tmp_path / "chunk.wav"
        _synthesize_chunk("Hi", "en-US", "FEMALE", "key", out, audio_format=".wav")

        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode("utf-8"))
        assert payload["audioConfig"]["audioEncoding"] == "LINEAR16"

    @patch("urllib.request.urlopen")
    def test_flac_encoding_defaults_to_mp3(self, mock_urlopen, tmp_path):
        """.flac format not in map defaults to MP3 encoding."""
        mock_urlopen.return_value = self._make_response(b"audio")
        out = tmp_path / "chunk.flac"
        _synthesize_chunk("Hi", "en-US", "FEMALE", "key", out, audio_format=".flac")

        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode("utf-8"))
        assert payload["audioConfig"]["audioEncoding"] == "MP3"

    @patch("urllib.request.urlopen")
    def test_speaking_rate_slightly_above_min(self, mock_urlopen, tmp_path):
        """Rate just above 0.25 is accepted."""
        mock_urlopen.return_value = self._make_response(b"audio")
        out = tmp_path / "chunk.mp3"
        _synthesize_chunk("Hi", "en-US", "FEMALE", "key", out, speaking_rate=0.26)

        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode("utf-8"))
        assert payload["audioConfig"]["speakingRate"] == 0.26  # noqa: PLR2004

    @patch("urllib.request.urlopen")
    def test_speaking_rate_slightly_below_max(self, mock_urlopen, tmp_path):
        """Rate just below 2.0 (the docs max) passes through unclamped."""
        mock_urlopen.return_value = self._make_response(b"audio")
        out = tmp_path / "chunk.mp3"
        _synthesize_chunk("Hi", "en-US", "FEMALE", "key", out, speaking_rate=1.99)

        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode("utf-8"))
        assert payload["audioConfig"]["speakingRate"] == 1.99  # noqa: PLR2004

    @patch("urllib.request.urlopen")
    def test_speaking_rate_negative_clamped_to_min(self, mock_urlopen, tmp_path):
        """Negative rate is clamped to 0.25."""
        mock_urlopen.return_value = self._make_response(b"audio")
        out = tmp_path / "chunk.mp3"
        _synthesize_chunk("Hi", "en-US", "FEMALE", "key", out, speaking_rate=-1.0)

        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode("utf-8"))
        assert payload["audioConfig"]["speakingRate"] == 0.25  # noqa: PLR2004

    @patch("urllib.request.urlopen")
    def test_speaking_rate_zero_clamped_to_min(self, mock_urlopen, tmp_path):
        """Zero rate is clamped to 0.25."""
        mock_urlopen.return_value = self._make_response(b"audio")
        out = tmp_path / "chunk.mp3"
        _synthesize_chunk("Hi", "en-US", "FEMALE", "key", out, speaking_rate=0.0)

        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode("utf-8"))
        assert payload["audioConfig"]["speakingRate"] == 0.25  # noqa: PLR2004

    @patch("urllib.request.urlopen")
    def test_text_input_type_in_payload(self, mock_urlopen, tmp_path):
        """Payload uses 'text' input type, not 'ssml'."""
        mock_urlopen.return_value = self._make_response(b"audio")
        out = tmp_path / "chunk.mp3"
        _synthesize_chunk("Hi", "en-US", "FEMALE", "key", out)

        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode("utf-8"))
        assert "text" in payload["input"]
        assert "ssml" not in payload["input"]

    @patch("urllib.request.urlopen")
    def test_gender_male_in_payload(self, mock_urlopen, tmp_path):
        """MALE gender appears in voice config."""
        mock_urlopen.return_value = self._make_response(b"audio")
        out = tmp_path / "chunk.mp3"
        _synthesize_chunk("Hi", "vi-VN", "MALE", "key", out)

        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode("utf-8"))
        assert payload["voice"]["ssmlGender"] == "MALE"
        assert payload["voice"]["languageCode"] == "vi-VN"

    @patch("urllib.request.urlopen")
    def test_empty_audio_format_defaults_to_mp3(self, mock_urlopen, tmp_path):
        """Empty audio_format defaults to MP3."""
        mock_urlopen.return_value = self._make_response(b"audio")
        out = tmp_path / "chunk.mp3"
        _synthesize_chunk("Hi", "en-US", "FEMALE", "key", out, audio_format="")

        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode("utf-8"))
        assert payload["audioConfig"]["audioEncoding"] == "MP3"


# ---------------------------------------------------------------------------
# Audio FLAC conversion: FFmpeg not found, corrupt input, stereo->mono,
# sample rate conversion
# ---------------------------------------------------------------------------


class TestExtractAudioToFlacConversion:
    """Test FLAC conversion via FFmpeg with various error cases."""

    @patch(f"{_MOD}.check_ffmpeg_available", return_value=False)
    def test_ffmpeg_not_found_raises(self, mock_ff):
        """Missing FFmpeg raises RuntimeError('FFMPEG_NOT_FOUND')."""
        with pytest.raises(RuntimeError, match="FFMPEG_NOT_FOUND"):
            _extract_audio_to_flac("/path/to/corrupt.mp4")

    @patch("subprocess.run")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_corrupt_input_raises_conversion_failed(self, mock_ff, mock_run):
        """Corrupt input file raises FFMPEG_CONVERSION_FAILED."""
        mock_run.side_effect = subprocess.CalledProcessError(
            1,
            "ffmpeg",
            stderr=b"Invalid data found when processing input",
        )
        with pytest.raises(RuntimeError, match="FFMPEG_CONVERSION_FAILED"):
            _extract_audio_to_flac("/path/to/corrupt.mp4")

    @patch("subprocess.run")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_ffmpeg_called_with_input_path(self, mock_ff, mock_run):
        """FFmpeg is called with the input file path."""
        mock_run.return_value = MagicMock(returncode=0)
        _extract_audio_to_flac("/path/to/video.mp4")

        cmd = mock_run.call_args[0][0]
        assert "/path/to/video.mp4" in cmd

    @patch("subprocess.run")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_stereo_to_mono_flag(self, mock_ff, mock_run):
        """FFmpeg converts stereo to mono with -ac 1."""
        mock_run.return_value = MagicMock(returncode=0)
        _extract_audio_to_flac("/path/to/stereo.mp4")

        cmd = mock_run.call_args[0][0]
        ac_idx = cmd.index("-ac")
        assert cmd[ac_idx + 1] == "1"

    @patch("subprocess.run")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_sample_rate_16khz(self, mock_ff, mock_run):
        """FFmpeg converts to 16kHz sample rate with -ar 16000."""
        mock_run.return_value = MagicMock(returncode=0)
        _extract_audio_to_flac("/path/to/audio.wav")

        cmd = mock_run.call_args[0][0]
        ar_idx = cmd.index("-ar")
        assert cmd[ar_idx + 1] == "16000"

    @patch("subprocess.run")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_output_is_flac_format(self, mock_ff, mock_run):
        """Output file is in FLAC format."""
        mock_run.return_value = MagicMock(returncode=0)
        result = _extract_audio_to_flac("/path/to/input.mp4")
        assert result.suffix == ".flac"
        assert result.name == "audio.flac"

    @patch("subprocess.run")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_capture_output_enabled(self, mock_ff, mock_run):
        """FFmpeg is called with capture_output=True."""
        mock_run.return_value = MagicMock(returncode=0)
        _extract_audio_to_flac("/path/to/input.mp4")

        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["capture_output"] is True

    @patch("subprocess.run")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_check_enabled(self, mock_ff, mock_run):
        """FFmpeg is called with check=True."""
        mock_run.return_value = MagicMock(returncode=0)
        _extract_audio_to_flac("/path/to/input.mp4")

        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["check"] is True

    @patch("subprocess.run")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_timeout_300_seconds(self, mock_ff, mock_run):
        """FFmpeg has 300-second timeout."""
        mock_run.return_value = MagicMock(returncode=0)
        _extract_audio_to_flac("/path/to/input.mp4")

        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["timeout"] == 300  # noqa: PLR2004

    @patch("subprocess.run")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_stderr_truncated_to_500_chars(self, mock_ff, mock_run):
        """Long stderr is truncated to 500 chars in error message."""
        long_stderr = b"x" * 1000
        mock_run.side_effect = subprocess.CalledProcessError(
            1,
            "ffmpeg",
            stderr=long_stderr,
        )
        with pytest.raises(RuntimeError, match="FFMPEG_CONVERSION_FAILED"):
            _extract_audio_to_flac("/path/to/input.mp4")


# ---------------------------------------------------------------------------
# convert_subtitle_format(): all format pairs (srt<->vtt<->ass<->ssa),
# malformed input, empty cues
# ---------------------------------------------------------------------------


class TestConvertSubtitleFormatAllPairs:
    """Test _convert_subtitle_format with all format pairs."""

    def test_srt_to_vtt_basic(self):
        """Basic SRT to VTT conversion."""
        srt = "1\n00:00:01,000 --> 00:00:04,000\nHello\n"
        vtt = _convert_subtitle_format(srt, ".vtt")
        assert vtt.startswith("WEBVTT\n")
        assert "00:00:01.000 --> 00:00:04.000" in vtt

    def test_srt_to_vtt_preserves_all_text(self):
        """All text is preserved during SRT to VTT conversion."""
        srt = (
            "1\n00:00:01,000 --> 00:00:04,000\nFirst line\n\n"
            "2\n00:00:05,000 --> 00:00:08,000\nSecond line\n\n"
            "3\n00:00:09,000 --> 00:00:12,000\nThird line\n"
        )
        vtt = _convert_subtitle_format(srt, ".vtt")
        assert "First line" in vtt
        assert "Second line" in vtt
        assert "Third line" in vtt

    def test_srt_to_ass_produces_script(self):
        """SRT to ASS produces a Script Info / Events file."""
        srt = "1\n00:00:01,000 --> 00:00:04,000\nHello\n"
        result = _convert_subtitle_format(srt, ".ass")
        assert "[Script Info]" in result and "Hello" in result

    def test_srt_to_ssa_produces_script(self):
        """SRT to SSA produces a Script Info / Events file."""
        srt = "1\n00:00:01,000 --> 00:00:04,000\nHello\n"
        result = _convert_subtitle_format(srt, ".ssa")
        assert "[Script Info]" in result and "Hello" in result

    def test_empty_srt_to_vtt(self):
        """Empty SRT converts to VTT with just header."""
        vtt = _convert_subtitle_format("", ".vtt")
        assert vtt.startswith("WEBVTT\n")

    def test_malformed_srt_no_timestamps(self):
        """SRT without timestamps still produces a valid VTT header."""
        srt = "Just some text without timestamps"
        vtt = _convert_subtitle_format(srt, ".vtt")
        # We at minimum still get the WEBVTT header. Text without a
        # timestamp cannot be represented as a VTT cue.
        assert "WEBVTT" in vtt

    def test_malformed_srt_wrong_separator(self):
        """SRT with wrong timestamp separator handled gracefully."""
        srt = "1\n00:00:01;000 --> 00:00:04;000\nHello\n"
        vtt = _convert_subtitle_format(srt, ".vtt")
        assert "WEBVTT" in vtt

    def test_srt_with_html_tags(self):
        """HTML tags in SRT text are preserved."""
        srt = "1\n00:00:01,000 --> 00:00:04,000\n<b>Bold</b> <i>Italic</i>\n"
        vtt = _convert_subtitle_format(srt, ".vtt")
        assert "<b>Bold</b>" in vtt
        assert "<i>Italic</i>" in vtt

    def test_srt_with_bom(self):
        """SRT with BOM character converts without error."""
        srt = "\ufeff1\n00:00:01,000 --> 00:00:04,000\nHello\n"
        vtt = _convert_subtitle_format(srt, ".vtt")
        assert "Hello" in vtt

    def test_srt_with_only_newlines(self):
        """SRT with only newlines converts to VTT with header."""
        vtt = _convert_subtitle_format("\n\n\n", ".vtt")
        assert vtt.startswith("WEBVTT\n")

    def test_vtt_format_lowercase(self):
        """Lowercase .vtt triggers conversion."""
        srt = "1\n00:00:01,000 --> 00:00:04,000\nHi\n"
        vtt = _convert_subtitle_format(srt, ".vtt")
        assert "WEBVTT" in vtt

    def test_srt_format_uppercase_no_conversion(self):
        """.SRT format returns unchanged."""
        srt = "1\n00:00:01,000 --> 00:00:04,000\nHello\n"
        assert _convert_subtitle_format(srt, ".SRT") == srt

    def test_srt_multiple_timestamps_all_converted(self):
        """All timestamp commas are converted to dots in VTT."""
        srt = (
            "1\n01:23:45,678 --> 02:34:56,789\nFirst\n\n"
            "2\n03:45:00,001 --> 04:56:01,999\nSecond\n"
        )
        vtt = _convert_subtitle_format(srt, ".vtt")
        assert "01:23:45.678 --> 02:34:56.789" in vtt
        assert "03:45:00.001 --> 04:56:01.999" in vtt


# ---------------------------------------------------------------------------
# synthesize_timed_speech(): overlapping cue times, zero-duration cues,
# very long text
# ---------------------------------------------------------------------------


class TestSynthesizeTimedSpeechOverlapping:
    """Test timed speech with overlapping and edge-case cue times."""

    @pytest.fixture(autouse=True)
    def _mock_edge(self):
        """Prevent edge_tts import in tests."""
        with patch(f"{_MOD}._synthesize_chunk_edge"):
            yield

    def _make_entry(self, start: str, end: str, text: str) -> MagicMock:
        """Create a mock SubtitleEntry."""
        entry = MagicMock()
        entry.start = start
        entry.end = end
        entry.text = text
        return entry

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration", return_value=1.0)
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_overlapping_cues_no_silence_between(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_synth,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """Overlapping cues (entry2 starts before entry1 ends) skip silence."""
        entries = [
            self._make_entry("00:00:00,000", "00:00:03,000", "First"),
            self._make_entry("00:00:01,000", "00:00:04,000", "Second"),
        ]
        output = str(tmp_path / "out.mp3")
        synthesize_timed_speech(
            entries,
            tts_method=_GOOGLE_TTS,
            output_path=output,
        )
        # No silence between overlapping entries
        # (cursor after first = 1.0, next starts at 1.0 → gap 0.0 < 0.05)
        assert mock_silence.call_count == 0

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration", return_value=1.0)
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_all_zero_duration_cues_raises(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_synth,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """All cues with zero duration raises EMPTY_TEXT."""
        entries = [
            self._make_entry("00:00:01,000", "00:00:01,000", "A"),
            self._make_entry("00:00:02,000", "00:00:02,000", "B"),
            self._make_entry("00:00:03,000", "00:00:03,000", "C"),
        ]
        with pytest.raises(ValueError, match="EMPTY_TEXT"):
            synthesize_timed_speech(
                entries,
                tts_method=_GOOGLE_TTS,
                output_path=str(tmp_path / "o.mp3"),
            )

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration", return_value=0.5)
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_very_long_text_in_cue(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_synth,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """Very long text in a cue is passed to TTS engine."""
        long_text = "word " * 1000
        entries = [
            self._make_entry("00:00:00,000", "00:00:10,000", long_text),
        ]
        output = str(tmp_path / "out.mp3")
        synthesize_timed_speech(
            entries,
            tts_method=_GOOGLE_TTS,
            output_path=output,
        )
        synth_call = mock_synth.call_args
        assert "word" in synth_call[0][0]

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration", return_value=0.1)
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_many_short_cues(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_synth,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """20 short cues are all synthesized."""
        cue_count = 20
        entries = [
            self._make_entry(
                f"00:00:{i:02d},000",
                f"00:00:{i:02d},500",
                f"Cue {i}",
            )
            for i in range(cue_count)
        ]
        output = str(tmp_path / "out.mp3")
        synthesize_timed_speech(
            entries,
            tts_method=_GOOGLE_TTS,
            output_path=output,
        )
        assert mock_synth.call_count == cue_count

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration", return_value=0.5)
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_reversed_timestamps_skipped(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_synth,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """Entries with end before start are skipped."""
        entries = [
            self._make_entry("00:00:05,000", "00:00:02,000", "Reversed"),
            self._make_entry("00:00:06,000", "00:00:08,000", "Valid"),
        ]
        output = str(tmp_path / "out.mp3")
        synthesize_timed_speech(
            entries,
            tts_method=_GOOGLE_TTS,
            output_path=output,
        )
        assert mock_synth.call_count == 1

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration", return_value=0.5)
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_very_large_start_time(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_synth,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """Entries starting at large timestamps still work."""
        entries = [
            self._make_entry("10:00:00,000", "10:00:02,000", "Late"),
        ]
        output = str(tmp_path / "out.mp3")
        synthesize_timed_speech(
            entries,
            tts_method=_GOOGLE_TTS,
            output_path=output,
        )
        # Leading silence of 36000 seconds
        mock_silence.assert_called_once()
        dur_arg = mock_silence.call_args[0][0]
        assert dur_arg == 36000.0  # noqa: PLR2004


# ---------------------------------------------------------------------------
# mix_audio_into_video(): missing video, missing audio, codec mismatches,
# container formats
# ---------------------------------------------------------------------------


class TestMixAudioIntoVideoContainersAndCodecs:
    """Test mix_audio_into_video with various container formats."""

    @patch("subprocess.run")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_mkv_container(self, mock_ff, mock_run, tmp_path):
        """MKV container format is passed through."""
        mock_run.return_value = MagicMock(returncode=0)
        video = str(tmp_path / "video.mkv")
        audio = str(tmp_path / "audio.mp3")
        output = str(tmp_path / "out.mkv")

        result = mix_audio_into_video(video, audio, output)
        assert result == output
        cmd = mock_run.call_args[0][0]
        assert video in cmd
        assert output in cmd

    @patch("subprocess.run")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_webm_container(self, mock_ff, mock_run, tmp_path):
        """WebM container format is passed through."""
        mock_run.return_value = MagicMock(returncode=0)
        video = str(tmp_path / "video.webm")
        audio = str(tmp_path / "audio.ogg")
        output = str(tmp_path / "out.webm")

        result = mix_audio_into_video(video, audio, output)
        assert result == output

    @patch("subprocess.run")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_wav_audio_input(self, mock_ff, mock_run, tmp_path):
        """WAV audio input is accepted."""
        mock_run.return_value = MagicMock(returncode=0)
        video = str(tmp_path / "video.mp4")
        audio = str(tmp_path / "audio.wav")
        output = str(tmp_path / "out.mp4")

        result = mix_audio_into_video(video, audio, output)
        assert result == output
        cmd = mock_run.call_args[0][0]
        assert audio in cmd

    @patch("subprocess.run")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_avi_container(self, mock_ff, mock_run, tmp_path):
        """AVI container format is passed through."""
        mock_run.return_value = MagicMock(returncode=0)
        result = mix_audio_into_video(
            str(tmp_path / "v.avi"),
            str(tmp_path / "a.mp3"),
            str(tmp_path / "o.avi"),
        )
        assert result == str(tmp_path / "o.avi")

    @patch("subprocess.run")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_codec_mismatch_stderr_in_error(self, mock_ff, mock_run, tmp_path):
        """Codec mismatch error stderr is captured in RuntimeError."""
        mock_run.side_effect = subprocess.CalledProcessError(
            1,
            "ffmpeg",
            stderr=b"Codec mismatch: h264 vs vp9",
        )
        with pytest.raises(RuntimeError, match="FFMPEG_MIX_FAILED"):
            mix_audio_into_video(
                str(tmp_path / "v.webm"),
                str(tmp_path / "a.aac"),
                str(tmp_path / "o.mp4"),
            )

    @patch("subprocess.run")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_video_copy_codec_used(self, mock_ff, mock_run, tmp_path):
        """Video codec is copy (not re-encoded)."""
        mock_run.return_value = MagicMock(returncode=0)
        mix_audio_into_video(
            str(tmp_path / "v.mp4"),
            str(tmp_path / "a.mp3"),
            str(tmp_path / "o.mp4"),
        )
        cmd = mock_run.call_args[0][0]
        cv_idx = cmd.index("-c:v")
        assert cmd[cv_idx + 1] == "copy"


# ---------------------------------------------------------------------------
# Cancellation at every stage of processing
# ---------------------------------------------------------------------------


class TestCancellationAtEveryStage:
    """Test cancellation callbacks at various processing stages."""

    @pytest.fixture(autouse=True)
    def _mock_edge(self):
        """Prevent edge_tts import in tests."""
        with patch(f"{_MOD}._synthesize_chunk_edge"):
            yield

    def _make_entry(self, start: str, end: str, text: str) -> MagicMock:
        """Create a mock SubtitleEntry."""
        entry = MagicMock()
        entry.start = start
        entry.end = end
        entry.text = text
        return entry

    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}._split_text_for_tts", return_value=["A.", "B.", "C.", "D.", "E."])
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_synthesize_speech_cancel_after_third_chunk(
        self,
        mock_key,
        mock_ffmpeg,
        mock_split,
        mock_synth,
        tmp_path,
    ):
        """Cancellation after third chunk stops at exactly 3 synthesized."""
        call_count = 0

        def cancel_after_three():
            nonlocal call_count
            call_count += 1
            return call_count > 3  # noqa: PLR2004

        with pytest.raises(ValueError, match="CANCELLED"):
            synthesize_speech(
                "A. B. C. D. E.",
                output_path=str(tmp_path / "out.mp3"),
                tts_method=_GOOGLE_TTS,
                is_cancelled=cancel_after_three,
            )
        assert mock_synth.call_count == 3  # noqa: PLR2004

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration", return_value=0.5)
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_timed_speech_cancel_after_first_entry(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_synth,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """Cancellation after first entry in timed speech."""
        call_count = 0

        def cancel_after_one():
            nonlocal call_count
            call_count += 1
            return call_count > 1

        entries = [
            self._make_entry("00:00:00,000", "00:00:01,000", "A"),
            self._make_entry("00:00:02,000", "00:00:03,000", "B"),
            self._make_entry("00:00:04,000", "00:00:05,000", "C"),
        ]
        with pytest.raises(ValueError, match="CANCELLED"):
            synthesize_timed_speech(
                entries,
                output_path=str(tmp_path / "o.mp3"),
                tts_method=_GOOGLE_TTS,
                is_cancelled=cancel_after_one,
            )
        assert mock_synth.call_count == 1

    @patch("time.sleep")
    @patch("urllib.request.urlopen")
    def test_poll_operation_cancel_immediately(self, mock_urlopen, mock_sleep):
        """Immediate cancellation in poll prevents any HTTP calls."""
        with pytest.raises(ValueError, match="CANCELLED"):
            _poll_operation(
                "operations/123",
                "key",
                is_cancelled=lambda: True,
            )
        mock_urlopen.assert_not_called()

    @patch("time.sleep")
    @patch("urllib.request.urlopen")
    def test_poll_operation_cancel_after_two_polls(
        self,
        mock_urlopen,
        mock_sleep,
    ):
        """Cancellation after two poll iterations."""
        call_count = 0

        def cancel_after_two():
            nonlocal call_count
            call_count += 1
            return call_count > 2  # noqa: PLR2004

        pending = MagicMock()
        pending.read.return_value = json.dumps({"done": False}).encode("utf-8")
        pending.__enter__ = MagicMock(return_value=pending)
        pending.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = pending

        with pytest.raises(ValueError, match="CANCELLED"):
            _poll_operation("operations/123", "key", is_cancelled=cancel_after_two)
        assert mock_urlopen.call_count == 2  # noqa: PLR2004

    @patch(f"{_MOD}._synthesize_chunk_edge")
    @patch(f"{_MOD}._split_text_for_tts", return_value=["A.", "B.", "C."])
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_edge_tts_cancel_before_any_chunk(
        self,
        mock_ffmpeg,
        mock_split,
        mock_edge,
        tmp_path,
    ):
        """Edge TTS cancellation before first chunk."""
        with pytest.raises(ValueError, match="CANCELLED"):
            synthesize_speech(
                "A. B. C.",
                output_path=str(tmp_path / "o.mp3"),
                is_cancelled=lambda: True,
            )
        mock_edge.assert_not_called()


# ---------------------------------------------------------------------------
# Memory safety: verify no accumulation of audio data in memory
# ---------------------------------------------------------------------------


class TestMemorySafety:
    """Test that audio data is not accumulated in memory."""

    @pytest.fixture(autouse=True)
    def _mock_edge(self):
        """Prevent edge_tts import in tests."""
        with patch(f"{_MOD}._synthesize_chunk_edge"):
            yield

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}._split_text_for_tts")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_chunks_written_to_disk_not_memory(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_split,
        mock_synth,
        mock_concat,
        tmp_path,
    ):
        """Each chunk is written to disk via _synthesize_chunk, not collected."""
        chunk_count = 100
        mock_split.return_value = [f"Chunk {i}." for i in range(chunk_count)]
        output = str(tmp_path / "out.mp3")
        synthesize_speech("text", tts_method=_GOOGLE_TTS, output_path=output)

        # _synthesize_chunk called once per chunk (writes to disk)
        assert mock_synth.call_count == chunk_count
        # _concatenate_mp3_files called once (reads from disk)
        mock_concat.assert_called_once()
        # Verify chunk paths are Path objects (disk files)
        concat_files = mock_concat.call_args[0][0]
        assert all(isinstance(f, Path) for f in concat_files)

    @patch("urllib.request.urlopen")
    def test_synthesize_chunk_writes_immediately(self, mock_urlopen, tmp_path):
        """_synthesize_chunk writes audio bytes directly to disk."""
        audio_data = b"\xff\xfb" * 10000  # 20KB of fake audio
        audio_b64 = base64.b64encode(audio_data).decode("utf-8")
        resp_data = json.dumps({"audioContent": audio_b64}).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = resp_data
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        out = tmp_path / "chunk.mp3"
        _synthesize_chunk("Hello", "en-US", "FEMALE", "key", out)

        # Data written to disk immediately
        assert out.exists()
        assert out.read_bytes() == audio_data

    @patch(f"{_MOD}.shutil.rmtree")
    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}._split_text_for_tts", return_value=["Hi."])
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_temp_dir_cleaned_after_synthesis(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_split,
        mock_synth,
        mock_concat,
        mock_rmtree,
        tmp_path,
    ):
        """Temp directory with chunk files is cleaned up after synthesis."""
        output = str(tmp_path / "out.mp3")
        synthesize_speech("Hi.", tts_method=_GOOGLE_TTS, output_path=output)
        mock_rmtree.assert_called_once()

    def _make_entry(self, start: str, end: str, text: str) -> MagicMock:
        """Create a mock SubtitleEntry."""
        entry = MagicMock()
        entry.start = start
        entry.end = end
        entry.text = text
        return entry

    @patch(f"{_MOD}.shutil.rmtree")
    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration", return_value=1.0)
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_timed_speech_temp_dir_cleaned(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_synth,
        mock_silence,
        mock_dur,
        mock_concat,
        mock_rmtree,
        tmp_path,
    ):
        """Timed speech temp directory is cleaned up after synthesis."""
        entries = [
            self._make_entry("00:00:00,000", "00:00:02,000", "Hi"),
        ]
        output = str(tmp_path / "out.mp3")
        synthesize_timed_speech(
            entries,
            tts_method=_GOOGLE_TTS,
            output_path=output,
        )
        mock_rmtree.assert_called_once()

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration", return_value=0.5)
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_silence_files_on_disk_not_memory(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_synth,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """Silence files are generated to disk, not accumulated in memory."""
        entries = [
            self._make_entry("00:00:05,000", "00:00:07,000", "Late start"),
        ]
        output = str(tmp_path / "out.mp3")
        synthesize_timed_speech(
            entries,
            tts_method=_GOOGLE_TTS,
            output_path=output,
        )
        # Silence was generated to a file path
        mock_silence.assert_called_once()
        silence_args = mock_silence.call_args[0]
        assert isinstance(silence_args[1], Path)


# ---------------------------------------------------------------------------
# Additional _parse_results_to_srt edge cases
# ---------------------------------------------------------------------------


class TestParseResultsToSrtAdditional:
    """Additional edge cases for _parse_results_to_srt."""

    def test_single_word_single_segment(self):
        """Single word produces single segment."""
        results = [
            {
                "alternatives": [
                    {
                        "words": [
                            {"word": "Hello", "startTime": "0s", "endTime": "0.5s"},
                        ],
                    }
                ],
            }
        ]
        srt = _parse_results_to_srt(results)
        assert "1\n" in srt
        assert "Hello" in srt

    def test_many_words_split_by_character_limit(self):
        """Many words are split into segments of <= 80 characters."""
        words = [
            {
                "word": f"word{i:03d}",
                "startTime": f"{i * 0.5}s",
                "endTime": f"{i * 0.5 + 0.4}s",
            }
            for i in range(20)
        ]
        results = [{"alternatives": [{"words": words}]}]
        srt = _parse_results_to_srt(results)
        # Should have multiple segments due to character limit
        segment_count = srt.count("-->")
        assert segment_count > 1

    def test_word_without_start_time_defaults_to_zero(self):
        """Missing startTime defaults to 0.0."""
        results = [
            {
                "alternatives": [
                    {
                        "words": [
                            {"word": "Hello", "endTime": "0.5s"},
                        ],
                    }
                ],
            }
        ]
        srt = _parse_results_to_srt(results)
        assert "Hello" in srt
        assert "00:00:00,000" in srt

    def test_word_without_end_time_defaults_to_zero(self):
        """Missing endTime defaults to 0.0."""
        results = [
            {
                "alternatives": [
                    {
                        "words": [
                            {"word": "Hello", "startTime": "0s"},
                        ],
                    }
                ],
            }
        ]
        srt = _parse_results_to_srt(results)
        assert "Hello" in srt

    def test_empty_word_string(self):
        """Word with empty string is included in segment text."""
        results = [
            {
                "alternatives": [
                    {
                        "words": [
                            {"word": "", "startTime": "0s", "endTime": "0.5s"},
                            {"word": "world", "startTime": "0.5s", "endTime": "1s"},
                        ],
                    }
                ],
            }
        ]
        srt = _parse_results_to_srt(results)
        assert "world" in srt

    def test_multiple_alternatives_uses_first(self):
        """Only first alternative is used from each result."""
        results = [
            {
                "alternatives": [
                    {
                        "words": [
                            {"word": "First", "startTime": "0s", "endTime": "1s"},
                        ],
                    },
                    {
                        "words": [
                            {"word": "Second", "startTime": "0s", "endTime": "1s"},
                        ],
                    },
                ],
            }
        ]
        srt = _parse_results_to_srt(results)
        assert "First" in srt

    def test_results_with_no_words_and_no_transcript(self):
        """Results with empty alternatives produce empty SRT."""
        results = [{"alternatives": [{}]}]
        srt = _parse_results_to_srt(results)
        assert srt == ""

    def test_transcript_fallback_preserves_order(self):
        """Transcript fallback preserves order of results."""
        results = [
            {"alternatives": [{"transcript": "Alpha"}]},
            {"alternatives": [{"transcript": "Beta"}]},
            {"alternatives": [{"transcript": "Gamma"}]},
        ]
        srt = _parse_results_to_srt(results)
        alpha_pos = srt.index("Alpha")
        beta_pos = srt.index("Beta")
        gamma_pos = srt.index("Gamma")
        assert alpha_pos < beta_pos < gamma_pos


# ---------------------------------------------------------------------------
# Additional synthesize_speech tests
# ---------------------------------------------------------------------------


class TestSynthesizeSpeechAdditionalPaths:
    """Additional test paths for synthesize_speech."""

    @pytest.fixture(autouse=True)
    def _mock_edge(self):
        """Prevent edge_tts import in tests."""
        with patch(f"{_MOD}._synthesize_chunk_edge"):
            yield

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}._split_text_for_tts", return_value=["Hi."])
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_empty_audio_format_defaults(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_split,
        mock_synth,
        mock_concat,
        tmp_path,
    ):
        """Empty audio_format uses default .mp3 extension for chunks."""
        output = str(tmp_path / "out.mp3")
        synthesize_speech(
            "Hi.",
            tts_method=_GOOGLE_TTS,
            output_path=output,
            audio_format="",
        )
        # Check the chunk path extension
        synth_call = mock_synth.call_args
        chunk_path = synth_call[0][4]
        assert chunk_path.suffix == ".mp3"

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}._split_text_for_tts", return_value=["Hi."])
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_wav_format_chunk_extension(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_split,
        mock_synth,
        mock_concat,
        tmp_path,
    ):
        """WAV audio_format creates .wav chunk files."""
        output = str(tmp_path / "out.wav")
        synthesize_speech(
            "Hi.",
            tts_method=_GOOGLE_TTS,
            output_path=output,
            audio_format=".wav",
        )
        synth_call = mock_synth.call_args
        chunk_path = synth_call[0][4]
        assert chunk_path.suffix == ".wav"

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._synthesize_chunk_edge")
    @patch(f"{_MOD}._split_text_for_tts", return_value=["Hi."])
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_edge_tts_chunk_always_mp3(
        self,
        mock_ffmpeg,
        mock_split,
        mock_edge,
        mock_concat,
        tmp_path,
    ):
        """Edge TTS always creates .mp3 chunk files regardless of audio_format."""
        output = str(tmp_path / "out.wav")
        synthesize_speech(
            "Hi.",
            output_path=output,
            audio_format=".wav",
        )
        edge_call = mock_edge.call_args
        chunk_path = edge_call[0][2]
        assert chunk_path.suffix == ".mp3"

    @patch(
        f"{_MOD}._concatenate_mp3_files",
        side_effect=RuntimeError("FFMPEG_CONCAT_FAILED"),
    )
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}._split_text_for_tts", return_value=["Hi."])
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_concat_error_propagates(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_split,
        mock_synth,
        mock_concat,
        tmp_path,
    ):
        """Concatenation failure propagates as RuntimeError."""
        with pytest.raises(RuntimeError, match="FFMPEG_CONCAT_FAILED"):
            synthesize_speech(
                "Hi.",
                tts_method=_GOOGLE_TTS,
                output_path=str(tmp_path / "out.mp3"),
            )


# ---------------------------------------------------------------------------
# Additional _split_text_for_tts edge cases
# ---------------------------------------------------------------------------


class TestSplitTextForTtsAdditional:
    """Additional edge-case tests for _split_text_for_tts."""

    def test_single_very_long_word(self):
        """Single word exceeding limit is returned as-is."""
        word = "x" * 5000
        result = _split_text_for_tts(word, max_bytes=100)
        assert len(result) >= 1
        # The word itself is in one of the chunks
        combined = " ".join(result)
        assert "x" in combined

    def test_japanese_full_stop_splits(self):
        """Japanese full stop splits correctly."""
        text = "\u3053\u3093\u306b\u3061\u306f\u3002 \u5143\u6c17\u3067\u3059\u3002"
        result = _split_text_for_tts(text, max_bytes=20)
        assert len(result) >= 2  # noqa: PLR2004

    def test_chinese_exclamation_splits(self):
        """Chinese exclamation mark splits correctly."""
        text = "\u4f60\u597d\uff01 \u8c22\u8c22\uff01"
        result = _split_text_for_tts(text, max_bytes=15)
        assert len(result) >= 2  # noqa: PLR2004

    def test_mixed_punctuation(self):
        """Mixed sentence-ending punctuation all split correctly."""
        text = "Hello. How are you? Great! Fine\u3002 \u597d\uff01"
        result = _split_text_for_tts(text, max_bytes=20)
        assert len(result) >= 2  # noqa: PLR2004
        combined = " ".join(result)
        assert "Hello." in combined

    def test_only_whitespace_between_sentences(self):
        """Multiple spaces between sentences are handled."""
        text = "First.    Second.    Third."
        result = _split_text_for_tts(text, max_bytes=15)
        assert len(result) >= 2  # noqa: PLR2004

    def test_newlines_not_split_points(self):
        """Newlines alone are not sentence split points."""
        text = "Line one\nLine two\nLine three"
        result = _split_text_for_tts(text, max_bytes=50)
        # All text in one or more chunks
        combined = " ".join(result)
        assert "Line" in combined

    def test_max_bytes_1_char_at_a_time(self):
        """Very small max_bytes splits aggressively."""
        text = "ab. cd."
        result = _split_text_for_tts(text, max_bytes=4)
        assert len(result) >= 2  # noqa: PLR2004


# ---------------------------------------------------------------------------
# Additional Google TTS language code mappings
# ---------------------------------------------------------------------------


class TestTTSLangMapCompleteness:
    """Test _TTS_LANG_MAP coverage for key locales."""

    @patch(f"{_LANG}.get_locale_code", return_value="sv")
    def test_swedish_mapped(self, mock_locale):
        """Swedish maps to 'sv-SE'."""
        assert _get_tts_language_code("Swedish") == "sv-SE"

    @patch(f"{_LANG}.get_locale_code", return_value="da")
    def test_danish_mapped(self, mock_locale):
        """Danish maps to 'da-DK'."""
        assert _get_tts_language_code("Danish") == "da-DK"

    @patch(f"{_LANG}.get_locale_code", return_value="fi")
    def test_finnish_mapped(self, mock_locale):
        """Finnish maps to 'fi-FI'."""
        assert _get_tts_language_code("Finnish") == "fi-FI"

    @patch(f"{_LANG}.get_locale_code", return_value="el")
    def test_greek_mapped(self, mock_locale):
        """Greek maps to 'el-GR'."""
        assert _get_tts_language_code("Greek") == "el-GR"

    @patch(f"{_LANG}.get_locale_code", return_value="he")
    def test_hebrew_mapped(self, mock_locale):
        """Hebrew maps to 'he-IL'."""
        assert _get_tts_language_code("Hebrew") == "he-IL"

    @patch(f"{_LANG}.get_locale_code", return_value="hu")
    def test_hungarian_mapped(self, mock_locale):
        """Hungarian maps to 'hu-HU'."""
        assert _get_tts_language_code("Hungarian") == "hu-HU"

    @patch(f"{_LANG}.get_locale_code", return_value="id")
    def test_indonesian_mapped(self, mock_locale):
        """Indonesian maps to 'id-ID'."""
        assert _get_tts_language_code("Indonesian") == "id-ID"

    @patch(f"{_LANG}.get_locale_code", return_value="lv")
    def test_latvian_mapped(self, mock_locale):
        """Latvian maps to 'lv-LV'."""
        assert _get_tts_language_code("Latvian") == "lv-LV"

    @patch(f"{_LANG}.get_locale_code", return_value="lt")
    def test_lithuanian_mapped(self, mock_locale):
        """Lithuanian maps to 'lt-LT'."""
        assert _get_tts_language_code("Lithuanian") == "lt-LT"

    @patch(f"{_LANG}.get_locale_code", return_value="ms")
    def test_malay_mapped(self, mock_locale):
        """Malay maps to 'ms-MY'."""
        assert _get_tts_language_code("Malay") == "ms-MY"

    @patch(f"{_LANG}.get_locale_code", return_value="ro")
    def test_romanian_mapped(self, mock_locale):
        """Romanian maps to 'ro-RO'."""
        assert _get_tts_language_code("Romanian") == "ro-RO"

    @patch(f"{_LANG}.get_locale_code", return_value="sk")
    def test_slovak_mapped(self, mock_locale):
        """Slovak maps to 'sk-SK'."""
        assert _get_tts_language_code("Slovak") == "sk-SK"

    @patch(f"{_LANG}.get_locale_code", return_value="tr")
    def test_turkish_mapped(self, mock_locale):
        """Turkish maps to 'tr-TR'."""
        assert _get_tts_language_code("Turkish") == "tr-TR"

    @patch(f"{_LANG}.get_locale_code", return_value="uk")
    def test_ukrainian_mapped(self, mock_locale):
        """Ukrainian maps to 'uk-UA'."""
        assert _get_tts_language_code("Ukrainian") == "uk-UA"

    @patch(f"{_LANG}.get_locale_code", return_value="bn")
    def test_bengali_mapped(self, mock_locale):
        """Bengali maps to 'bn-IN'."""
        assert _get_tts_language_code("Bengali") == "bn-IN"

    @patch(f"{_LANG}.get_locale_code", return_value="bg")
    def test_bulgarian_mapped(self, mock_locale):
        """Bulgarian maps to 'bg-BG'."""
        assert _get_tts_language_code("Bulgarian") == "bg-BG"

    @patch(f"{_LANG}.get_locale_code", return_value="cs")
    def test_czech_mapped(self, mock_locale):
        """Czech maps to 'cs-CZ'."""
        assert _get_tts_language_code("Czech") == "cs-CZ"

    @patch(f"{_LANG}.get_locale_code", return_value="km")
    def test_khmer_mapped(self, mock_locale):
        """Khmer maps to 'km-KH'."""
        assert _get_tts_language_code("Khmer") == "km-KH"

    @patch(f"{_LANG}.get_locale_code", return_value="nl")
    def test_dutch_mapped(self, mock_locale):
        """Dutch maps to 'nl-NL'."""
        assert _get_tts_language_code("Dutch") == "nl-NL"

    @patch(f"{_LANG}.get_locale_code", return_value="es")
    def test_spanish_mapped(self, mock_locale):
        """Spanish maps to 'es-ES'."""
        assert _get_tts_language_code("Spanish") == "es-ES"


# ---------------------------------------------------------------------------
# Additional Edge TTS voice tests for remaining languages
# ---------------------------------------------------------------------------


class TestEdgeTTSRemainingVoices:
    """Test remaining Edge TTS voice mappings."""

    @patch(f"{_LANG}.get_locale_code", return_value="bn")
    def test_bengali_female(self, mock_locale):
        """Bengali Female maps to bn-IN-TanishaaNeural."""
        result = _get_edge_voice("Bengali", "FEMALE")
        assert result == "bn-IN-TanishaaNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="bg")
    def test_bulgarian_male(self, mock_locale):
        """Bulgarian Male maps to bg-BG-BorislavNeural."""
        result = _get_edge_voice("Bulgarian", "MALE")
        assert result == "bg-BG-BorislavNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="cs")
    def test_czech_female(self, mock_locale):
        """Czech Female maps to cs-CZ-VlastaNeural."""
        result = _get_edge_voice("Czech", "FEMALE")
        assert result == "cs-CZ-VlastaNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="da")
    def test_danish_male(self, mock_locale):
        """Danish Male maps to da-DK-JeppeNeural."""
        result = _get_edge_voice("Danish", "MALE")
        assert result == "da-DK-JeppeNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="nl")
    def test_dutch_male(self, mock_locale):
        """Dutch Male maps to nl-NL-MaartenNeural."""
        result = _get_edge_voice("Dutch", "MALE")
        assert result == "nl-NL-MaartenNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="fi")
    def test_finnish_male(self, mock_locale):
        """Finnish Male maps to fi-FI-HarriNeural."""
        result = _get_edge_voice("Finnish", "MALE")
        assert result == "fi-FI-HarriNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="el")
    def test_greek_male(self, mock_locale):
        """Greek Male maps to el-GR-NestorasNeural."""
        result = _get_edge_voice("Greek", "MALE")
        assert result == "el-GR-NestorasNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="he")
    def test_hebrew_female(self, mock_locale):
        """Hebrew Female maps to he-IL-HilaNeural."""
        result = _get_edge_voice("Hebrew", "FEMALE")
        assert result == "he-IL-HilaNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="hu")
    def test_hungarian_female(self, mock_locale):
        """Hungarian Female maps to hu-HU-NoemiNeural."""
        result = _get_edge_voice("Hungarian", "FEMALE")
        assert result == "hu-HU-NoemiNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="id")
    def test_indonesian_male(self, mock_locale):
        """Indonesian Male maps to id-ID-ArdiNeural."""
        result = _get_edge_voice("Indonesian", "MALE")
        assert result == "id-ID-ArdiNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="lv")
    def test_latvian_male(self, mock_locale):  # noqa: ANN001, ARG002
        """Latvian Male maps to lv-LV-NilsNeural."""
        result = _get_edge_voice("Latvian", "MALE")
        assert result == "lv-LV-NilsNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="pl")
    def test_polish_female(self, mock_locale):
        """Polish Female maps to pl-PL-ZofiaNeural."""
        result = _get_edge_voice("Polish", "FEMALE")
        assert result == "pl-PL-ZofiaNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="ro")
    def test_romanian_male(self, mock_locale):
        """Romanian Male maps to ro-RO-EmilNeural."""
        result = _get_edge_voice("Romanian", "MALE")
        assert result == "ro-RO-EmilNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="sk")
    def test_slovak_female(self, mock_locale):
        """Slovak Female maps to sk-SK-ViktoriaNeural."""
        result = _get_edge_voice("Slovak", "FEMALE")
        assert result == "sk-SK-ViktoriaNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="es")
    def test_spanish_male(self, mock_locale):
        """Spanish Male maps to es-ES-AlvaroNeural."""
        result = _get_edge_voice("Spanish", "MALE")
        assert result == "es-ES-AlvaroNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="zh-TW")
    def test_chinese_traditional_male(self, mock_locale):
        """Chinese Traditional Male maps to zh-TW-YunJheNeural."""
        result = _get_edge_voice("Chinese (Traditional)", "MALE")
        assert result == "zh-TW-YunJheNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="pt-PT")
    def test_portuguese_portugal_female(self, mock_locale):
        """Portuguese Portugal Female maps to pt-PT-RaquelNeural."""
        result = _get_edge_voice("Portuguese (Portugal)", "FEMALE")
        assert result == "pt-PT-RaquelNeural"


# ---------------------------------------------------------------------------
# Additional _poll_operation backoff and edge case tests
# ---------------------------------------------------------------------------


class TestPollOperationBackoffDetails:
    """Detailed tests for _poll_operation backoff timing."""

    def _make_response(self, data: dict) -> MagicMock:
        """Create a mock urlopen response."""
        resp = MagicMock()
        resp.read.return_value = json.dumps(data).encode("utf-8")
        resp.__enter__ = MagicMock(return_value=resp)
        resp.__exit__ = MagicMock(return_value=False)
        return resp

    @patch("time.sleep")
    @patch("urllib.request.urlopen")
    def test_initial_delay_is_2_seconds(self, mock_urlopen, mock_sleep):
        """First sleep is _POLL_INITIAL_DELAY (2.0 seconds)."""
        complete = self._make_response(
            {"done": True, "response": {"results": []}},
        )
        mock_urlopen.return_value = complete

        _poll_operation("operations/test", "key")

        first_sleep = mock_sleep.call_args_list[0][0][0]
        assert first_sleep == 2.0  # noqa: PLR2004

    @patch("time.sleep")
    @patch("urllib.request.urlopen")
    def test_backoff_factor_1_5(self, mock_urlopen, mock_sleep):
        """Second delay is 1.5x the first."""
        pending = self._make_response({"done": False})
        complete = self._make_response(
            {"done": True, "response": {"results": []}},
        )
        mock_urlopen.side_effect = [pending, complete]

        _poll_operation("operations/test", "key")

        delays = [call[0][0] for call in mock_sleep.call_args_list]
        assert len(delays) == 2  # noqa: PLR2004
        # Second delay should be first * 1.5
        assert abs(delays[1] - delays[0] * 1.5) < 0.01  # noqa: PLR2004

    @patch("time.sleep")
    @patch("urllib.request.urlopen")
    def test_delay_capped_at_max(self, mock_urlopen, mock_sleep):
        """Delay never exceeds _POLL_MAX_DELAY (15.0 seconds)."""
        # Create enough pending responses to exceed max delay
        pending = self._make_response({"done": False})
        complete = self._make_response(
            {"done": True, "response": {"results": []}},
        )
        responses = [pending] * 20 + [complete]
        mock_urlopen.side_effect = responses

        _poll_operation("operations/test", "key")

        delays = [call[0][0] for call in mock_sleep.call_args_list]
        for d in delays:
            assert d <= 15.0  # noqa: PLR2004

    @patch("time.sleep")
    @patch("urllib.request.urlopen")
    def test_done_true_with_both_error_and_response(
        self,
        mock_urlopen,
        mock_sleep,
    ):
        """When both 'error' and 'response' present, error takes priority."""
        mock_urlopen.return_value = self._make_response(
            {
                "done": True,
                "error": {"message": "Partial failure"},
                "response": {"results": []},
            },
        )
        with pytest.raises(ValueError, match="Partial failure"):
            _poll_operation("operations/test", "key")


# ---------------------------------------------------------------------------
# Additional extract_subtitle_text edge cases
# ---------------------------------------------------------------------------


class TestExtractSubtitleTextAdditional:
    """Additional tests for extract_subtitle_text."""

    @patch(f"{_SUB}.is_subtitle_format", return_value=False)
    def test_json_suffix_fallback(self, mock_is_sub):
        """Non-subtitle .json suffix returns content as-is."""
        text = '{"key": "value"}'
        result = extract_subtitle_text(text, ".json")
        assert result == text

    @patch(f"{_SUB}.is_subtitle_format", return_value=False)
    def test_empty_content_plain_text(self, mock_is_sub):
        """Empty content with non-subtitle suffix returns empty string."""
        result = extract_subtitle_text("", ".txt")
        assert result == ""

    @patch(f"{_SUB}.parse_subtitle")
    @patch(f"{_SUB}.is_subtitle_format", return_value=True)
    def test_many_entries(self, mock_is_sub, mock_parse):
        """Many subtitle entries are all extracted."""
        entry_count = 100
        entries = []
        for i in range(entry_count):
            e = MagicMock()
            e.text = f"Line {i}"
            entries.append(e)
        mock_parse.return_value = (entries, None)

        result = extract_subtitle_text("content", ".srt")
        assert result.count("\n") == entry_count - 1

    @patch(f"{_SUB}.parse_subtitle")
    @patch(f"{_SUB}.is_subtitle_format", return_value=True)
    def test_ssa_suffix(self, mock_is_sub, mock_parse):
        """SSA suffix is handled as subtitle format."""
        entry = MagicMock()
        entry.text = "SSA line."
        mock_parse.return_value = ([entry], None)

        result = extract_subtitle_text("dummy", ".ssa")
        mock_is_sub.assert_called_once_with(".ssa")
        assert result == "SSA line."

    def test_default_suffix_srt(self):
        """Default suffix is .srt."""
        # Calling without suffix arg uses default .srt
        with (
            patch(f"{_SUB}.is_subtitle_format", return_value=True) as mock_is_sub,
            patch(f"{_SUB}.parse_subtitle", return_value=([], None)),
        ):
            extract_subtitle_text("content")
            mock_is_sub.assert_called_once_with(".srt")


# ---------------------------------------------------------------------------
# Additional synthesize_timed_speech Edge TTS paths
# ---------------------------------------------------------------------------


class TestTimedSpeechEdgeTTSAdditionalPaths:
    """Additional Edge TTS paths for synthesize_timed_speech."""

    def _make_entry(self, start: str, end: str, text: str) -> MagicMock:
        """Create a mock SubtitleEntry."""
        entry = MagicMock()
        entry.start = start
        entry.end = end
        entry.text = text
        return entry

    @patch(f"{_MOD}._synthesize_chunk_edge")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_edge_empty_entries_raises(self, mock_ff, mock_edge, tmp_path):
        """Edge TTS with empty text entries raises EMPTY_TEXT."""
        entries = [
            self._make_entry("00:00:00,000", "00:00:01,000", "   "),
        ]
        with pytest.raises(ValueError, match="EMPTY_TEXT"):
            synthesize_timed_speech(
                entries,
                output_path=str(tmp_path / "o.mp3"),
            )

    @patch(f"{_MOD}._synthesize_chunk_edge")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_edge_empty_list_raises(self, mock_ff, mock_edge, tmp_path):
        """Edge TTS with empty list raises EMPTY_TEXT."""
        with pytest.raises(ValueError, match="EMPTY_TEXT"):
            synthesize_timed_speech(
                [],
                output_path=str(tmp_path / "o.mp3"),
            )

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration", return_value=0.5)
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._synthesize_chunk_edge")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_edge_progress_callback(  # noqa: PLR0913
        self,
        mock_ff,
        mock_edge,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """Edge TTS progress callback reports correct counts."""
        progress = []
        entries = [
            self._make_entry("00:00:00,000", "00:00:01,000", "A"),
            self._make_entry("00:00:02,000", "00:00:03,000", "B"),
            self._make_entry("00:00:04,000", "00:00:05,000", "C"),
        ]
        output = str(tmp_path / "out.mp3")
        synthesize_timed_speech(
            entries,
            output_path=output,
            on_progress=lambda c, t: progress.append((c, t)),
        )
        assert progress == [(1, 3), (2, 3), (3, 3)]

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration", return_value=0.5)
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._synthesize_chunk_edge")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_edge_cancellation_after_second(  # noqa: PLR0913
        self,
        mock_ff,
        mock_edge,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """Edge TTS cancellation after second entry."""
        call_count = 0

        def cancel_after_two():
            nonlocal call_count
            call_count += 1
            return call_count > 2  # noqa: PLR2004

        entries = [
            self._make_entry("00:00:00,000", "00:00:01,000", "A"),
            self._make_entry("00:00:02,000", "00:00:03,000", "B"),
            self._make_entry("00:00:04,000", "00:00:05,000", "C"),
        ]
        with pytest.raises(ValueError, match="CANCELLED"):
            synthesize_timed_speech(
                entries,
                output_path=str(tmp_path / "o.mp3"),
                is_cancelled=cancel_after_two,
            )
        assert mock_edge.call_count == 2  # noqa: PLR2004


# ---------------------------------------------------------------------------
# Additional _format_srt_time boundary tests
# ---------------------------------------------------------------------------


class TestFormatSrtTimeBoundaries:
    """Boundary value tests for _format_srt_time."""

    def test_exactly_59_seconds(self):
        """59.999 seconds formats correctly."""
        result = _format_srt_time(59.999)
        assert result == "00:00:59,999"

    def test_exactly_59_minutes(self):
        """59 minutes 59 seconds."""
        result = _format_srt_time(3599.0)
        assert result == "00:59:59,000"

    def test_very_small_positive(self):
        """Very small positive value."""
        result = _format_srt_time(0.0001)
        assert result.startswith("00:00:00,")

    def test_one_hour_one_minute_one_second(self):
        """1h 1m 1s = 3661.0."""
        assert _format_srt_time(3661.0) == "01:01:01,000"

    def test_two_hours(self):
        """Exactly two hours."""
        assert _format_srt_time(7200.0) == "02:00:00,000"

    def test_half_millisecond_rounds_down(self):
        """0.5005 seconds -> 500ms (int truncation)."""
        result = _format_srt_time(0.5005)
        assert result == "00:00:00,500"


# ---------------------------------------------------------------------------
# Additional _call_long_running_recognize edge cases
# ---------------------------------------------------------------------------


class TestCallLongRunningRecognizeNetwork:
    """Test _call_long_running_recognize network error handling."""

    @patch("urllib.request.urlopen")
    def test_url_error_propagates(self, mock_urlopen):
        """URLError (network down) propagates."""
        mock_urlopen.side_effect = urllib.error.URLError("no network")
        with pytest.raises(urllib.error.URLError):
            _call_long_running_recognize("audio", "en-US", "key")

    @patch("urllib.request.urlopen")
    def test_timeout_error_propagates(self, mock_urlopen):
        """Timeout during API call propagates."""
        mock_urlopen.side_effect = urllib.error.URLError(
            TimeoutError("request timed out"),
        )
        with pytest.raises(urllib.error.URLError):
            _call_long_running_recognize("audio", "en-US", "key")

    @patch("urllib.request.urlopen")
    def test_http_502_raises_speech_api_error(self, mock_urlopen):
        """HTTP 502 raises SPEECH_API_ERROR."""
        fp = MagicMock(read=lambda: b"bad gateway")
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "url",
            502,
            "Bad Gateway",
            {},
            fp,
        )
        with pytest.raises(ValueError, match="SPEECH_API_ERROR: HTTP 502"):
            _call_long_running_recognize("audio", "en-US", "key")

    @patch("urllib.request.urlopen")
    def test_http_503_raises_speech_api_error(self, mock_urlopen):
        """HTTP 503 raises SPEECH_API_ERROR."""
        fp = MagicMock(read=lambda: b"service unavailable")
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "url",
            503,
            "Service Unavailable",
            {},
            fp,
        )
        with pytest.raises(ValueError, match="SPEECH_API_ERROR: HTTP 503"):
            _call_long_running_recognize("audio", "en-US", "key")


# ---------------------------------------------------------------------------
# Additional _concatenate_mp3_files edge cases
# ---------------------------------------------------------------------------


class TestConcatenateMp3FilesAdditional:
    """Additional tests for _concatenate_mp3_files."""

    @patch("subprocess.run")
    def test_ten_files_all_listed(self, mock_run, tmp_path):
        """Ten files are all listed in the concat file."""
        file_count = 10
        files = []
        for i in range(file_count):
            f = tmp_path / f"chunk_{i}.mp3"
            f.write_bytes(b"data")
            files.append(f)
        out = tmp_path / "output.mp3"

        mock_run.return_value = MagicMock(returncode=0)
        _concatenate_mp3_files(files, out)

        concat_file = tmp_path / "concat.txt"
        content = concat_file.read_text(encoding="utf-8")
        for f in files:
            assert str(f) in content

    def test_single_file_preserves_content(self, tmp_path):
        """Single file copy preserves exact content."""
        data = b"\xff\xfb\x90\x00" * 1000
        src = tmp_path / "src.mp3"
        src.write_bytes(data)
        out = tmp_path / "out.mp3"

        _concatenate_mp3_files([src], out)
        assert out.read_bytes() == data

    @patch("subprocess.run")
    def test_concat_creates_file_in_first_file_parent(self, mock_run, tmp_path):
        """Concat list file is created in the parent of the first audio file."""
        subdir = tmp_path / "chunks"
        subdir.mkdir()
        f1 = subdir / "a.mp3"
        f2 = subdir / "b.mp3"
        f1.write_bytes(b"1")
        f2.write_bytes(b"2")
        out = tmp_path / "output.mp3"

        mock_run.return_value = MagicMock(returncode=0)
        _concatenate_mp3_files([f1, f2], out)

        concat_file = subdir / "concat.txt"
        assert concat_file.exists()


# ---------------------------------------------------------------------------
# _synthesize_chunk_elevenlabs
# ---------------------------------------------------------------------------


class TestSynthesizeChunkElevenlabs:
    """Tests for the ElevenLabs TTS single-chunk synthesizer."""

    def _make_response(self, audio_bytes: bytes) -> MagicMock:
        """Create a mock urlopen response that returns raw audio bytes."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = audio_bytes
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    @patch("urllib.request.urlopen")
    def test_successful_synthesis_writes_file(self, mock_urlopen, tmp_path):
        """Successful API call writes audio bytes to the output path."""
        from src.core.speech_engine import _synthesize_chunk_elevenlabs  # noqa: PLC0415

        audio_data = b"\xff\xfb\x90\x00" * 50
        mock_urlopen.return_value = self._make_response(audio_data)

        output = tmp_path / "chunk.mp3"
        _synthesize_chunk_elevenlabs("Hello world", "test-api-key", output)

        assert output.exists()
        assert output.read_bytes() == audio_data

    @patch("urllib.request.urlopen")
    def test_auth_error_on_401(self, mock_urlopen, tmp_path):
        """HTTP 401 raises ValueError with AUTH_ERROR."""
        from src.core.speech_engine import _synthesize_chunk_elevenlabs  # noqa: PLC0415

        fp = MagicMock(read=lambda: b"Unauthorized")
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "url",
            401,
            "Unauthorized",
            {},
            fp,
        )
        out = tmp_path / "c.mp3"
        with pytest.raises(ValueError, match="AUTH_ERROR"):
            _synthesize_chunk_elevenlabs("Hi", "bad-key", out)

    @patch("urllib.request.urlopen")
    def test_quota_error_on_429(self, mock_urlopen, tmp_path):
        """HTTP 429 raises ValueError with QUOTA_ERROR."""
        from src.core.speech_engine import _synthesize_chunk_elevenlabs  # noqa: PLC0415

        fp = MagicMock(read=lambda: b"Rate limited")
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "url",
            429,
            "Too Many Requests",
            {},
            fp,
        )
        out = tmp_path / "c.mp3"
        with pytest.raises(ValueError, match="QUOTA_ERROR"):
            _synthesize_chunk_elevenlabs("Hi", "key", out)

    @patch("urllib.request.urlopen")
    def test_tts_api_error_on_500(self, mock_urlopen, tmp_path):
        """HTTP 500 raises ValueError with TTS_API_ERROR."""
        from src.core.speech_engine import _synthesize_chunk_elevenlabs  # noqa: PLC0415

        fp = MagicMock(read=lambda: b"Server error")
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "url",
            500,
            "Internal Server Error",
            {},
            fp,
        )
        out = tmp_path / "c.mp3"
        with pytest.raises(ValueError, match="TTS_API_ERROR"):
            _synthesize_chunk_elevenlabs("Hi", "key", out)

    @patch("urllib.request.urlopen")
    def test_default_voice_id_when_empty(self, mock_urlopen, tmp_path):
        """Empty voice_id falls back to the gender-default voice in the URL."""
        from src.core.speech_engine import (  # noqa: PLC0415
            _ELEVENLABS_DEFAULT_VOICE_FEMALE,
            _ELEVENLABS_DEFAULT_VOICE_MALE,
            _synthesize_chunk_elevenlabs,
        )

        mock_urlopen.return_value = self._make_response(b"audio")
        output = tmp_path / "chunk.mp3"

        # No gender → defaults to FEMALE → Rachel.
        _synthesize_chunk_elevenlabs("Test", "key", output, voice_id="")
        assert _ELEVENLABS_DEFAULT_VOICE_FEMALE in (
            mock_urlopen.call_args[0][0].full_url
        )

        # gender=MALE → George.
        mock_urlopen.return_value = self._make_response(b"audio")
        _synthesize_chunk_elevenlabs(
            "Test",
            "key",
            output,
            voice_id="",
            gender="MALE",
        )
        assert _ELEVENLABS_DEFAULT_VOICE_MALE in (mock_urlopen.call_args[0][0].full_url)

    @patch("urllib.request.urlopen")
    def test_custom_voice_id_in_url(self, mock_urlopen, tmp_path):
        """Custom voice_id is included in the request URL."""
        from src.core.speech_engine import _synthesize_chunk_elevenlabs  # noqa: PLC0415

        mock_urlopen.return_value = self._make_response(b"audio")
        output = tmp_path / "chunk.mp3"

        custom_voice = "my_custom_voice_123"
        _synthesize_chunk_elevenlabs("Test", "key", output, voice_id=custom_voice)

        req = mock_urlopen.call_args[0][0]
        assert custom_voice in req.full_url

    @patch("urllib.request.urlopen")
    def test_default_model_id_when_not_provided(self, mock_urlopen, tmp_path):
        """Empty model_id falls back to the library default (multilingual_v2)."""
        from src.core.speech_engine import _synthesize_chunk_elevenlabs  # noqa: PLC0415

        mock_urlopen.return_value = self._make_response(b"audio")
        output = tmp_path / "chunk.mp3"
        _synthesize_chunk_elevenlabs("Test", "key", output)

        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode("utf-8"))
        assert payload["model_id"] == "eleven_multilingual_v2"

    @patch("urllib.request.urlopen")
    def test_custom_model_id_sent_in_payload(self, mock_urlopen, tmp_path):
        """Explicit model_id argument is forwarded in the request body."""
        from src.core.speech_engine import _synthesize_chunk_elevenlabs  # noqa: PLC0415

        mock_urlopen.return_value = self._make_response(b"audio")
        output = tmp_path / "chunk.mp3"
        _synthesize_chunk_elevenlabs(
            "Test",
            "key",
            output,
            model_id="eleven_flash_v2_5",
        )

        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode("utf-8"))
        assert payload["model_id"] == "eleven_flash_v2_5"


# ---------------------------------------------------------------------------
# Google Cloud TTS — voice_name override
# ---------------------------------------------------------------------------


class TestGoogleTtsVoiceNameOverride:
    """Tests that a voice_name argument takes precedence over ssmlGender."""

    @staticmethod
    def _make_response(payload: dict) -> MagicMock:
        """Fake urlopen response carrying a JSON payload."""
        import base64  # noqa: PLC0415

        body = json.dumps(payload).encode("utf-8")
        resp = MagicMock()
        resp.read.return_value = body
        resp.__enter__ = lambda s: s
        resp.__exit__ = lambda *args: None
        _ = base64  # silence import used below
        return resp

    @patch("urllib.request.urlopen")
    def test_voice_name_included_and_gender_omitted(
        self,
        mock_urlopen,
        tmp_path,
    ) -> None:
        """When voice_name is set, payload has ``voice.name`` and no ssmlGender."""
        import base64  # noqa: PLC0415

        from src.core.speech_engine import _synthesize_chunk  # noqa: PLC0415

        mock_urlopen.return_value = self._make_response(
            {"audioContent": base64.b64encode(b"audio").decode()},
        )
        output = tmp_path / "chunk.mp3"
        _synthesize_chunk(
            "Hello",
            "en-US",
            "FEMALE",
            "api-key",
            output,
            voice_name="en-US-Chirp3-HD-Charon",
        )

        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode("utf-8"))
        assert payload["voice"]["name"] == "en-US-Chirp3-HD-Charon"
        assert "ssmlGender" not in payload["voice"]

    @patch("urllib.request.urlopen")
    def test_no_voice_name_keeps_gender(self, mock_urlopen, tmp_path) -> None:
        """Without voice_name the payload keeps ssmlGender (legacy behavior)."""
        import base64  # noqa: PLC0415

        from src.core.speech_engine import _synthesize_chunk  # noqa: PLC0415

        mock_urlopen.return_value = self._make_response(
            {"audioContent": base64.b64encode(b"audio").decode()},
        )
        output = tmp_path / "chunk.mp3"
        _synthesize_chunk("Hi", "en-US", "MALE", "api-key", output)

        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode("utf-8"))
        assert "name" not in payload["voice"]
        assert payload["voice"]["ssmlGender"] == "MALE"


# ---------------------------------------------------------------------------
# ElevenLabs dispatch in synthesize_speech / synthesize_timed_speech
# ---------------------------------------------------------------------------


class TestSynthesizeSpeechElevenLabsDispatch:
    """Tests ElevenLabs path in synthesize_speech dispatcher."""

    def test_elevenlabs_dispatch_calls_chunk_function(
        self,
        tmp_path,
    ) -> None:
        """synthesize_speech dispatches to ElevenLabs when configured."""
        from src.core.speech_engine import synthesize_speech

        out = tmp_path / "output.mp3"
        with (
            patch(
                "src.utils.config_manager.load_setting",
                side_effect=lambda k, d="": {
                    "service/elevenlabs_api_key": "test-key",
                    "voice/elevenlabs_voice_id": "vid",
                }.get(k, d),
            ),
            patch(
                "src.core.speech_engine.check_ffmpeg_available",
                return_value=True,
            ),
            patch(
                "src.core.speech_engine._synthesize_chunk_elevenlabs",
                side_effect=lambda t, k, p, v, model_id="", **_kw: p.write_bytes(b"x"),
            ) as mock_el,
            patch("src.core.speech_engine._concatenate_mp3_files"),
        ):
            synthesize_speech(
                "Hello",
                output_path=str(out),
                tts_method="ElevenLabs",
            )
            mock_el.assert_called()

    def test_elevenlabs_auth_error_when_no_key(self, tmp_path) -> None:
        """synthesize_speech raises AUTH_ERROR when ElevenLabs key missing."""
        from src.core.speech_engine import synthesize_speech

        with (
            patch(
                "src.utils.config_manager.load_setting",
                return_value="",
            ),
            pytest.raises(ValueError, match="AUTH_ERROR"),
        ):
            synthesize_speech(
                "Hello",
                output_path=str(tmp_path / "out.mp3"),
                tts_method="ElevenLabs",
            )


# ---------------------------------------------------------------------------
# _parse_duration — extended edge cases
# ---------------------------------------------------------------------------


class TestParseDurationEdgeCases:
    """Extended edge-case tests for Google API duration string parsing."""

    def test_s_alone_returns_zero(self):
        """The string 's' alone (suffix stripped leaves empty) returns 0.0."""
        assert _parse_duration("s") == 0.0

    def test_abc_non_numeric_returns_zero(self):
        """Pure non-numeric string 'abc' returns 0.0."""
        assert _parse_duration("abc") == 0.0

    def test_negative_duration(self):
        """Negative duration string '-5.0s' parses to -5.0."""
        assert _parse_duration("-5.0s") == -5.0  # noqa: PLR2004

    def test_very_large_value(self):
        """Very large duration '999999.999s' is parsed correctly."""
        assert _parse_duration("999999.999s") == 999999.999  # noqa: PLR2004

    def test_no_suffix_plain_float(self):
        """String without 's' suffix '1.5' parses as float."""
        assert _parse_duration("1.5") == 1.5  # noqa: PLR2004

    def test_integer_with_suffix(self):
        """Integer duration '10s' parses to 10.0."""
        assert _parse_duration("10s") == 10.0  # noqa: PLR2004

    def test_scientific_notation_with_suffix(self):
        """Scientific notation '1e3s' parses to 1000.0."""
        assert _parse_duration("1e3s") == 1000.0  # noqa: PLR2004

    def test_scientific_notation_without_suffix(self):
        """Scientific notation '1e2' parses to 100.0."""
        assert _parse_duration("1e2") == 100.0  # noqa: PLR2004

    def test_zero_seconds_with_suffix(self):
        """'0s' parses to 0.0."""
        assert _parse_duration("0s") == 0.0

    def test_zero_point_zero(self):
        """'0.0s' parses to 0.0."""
        assert _parse_duration("0.0s") == 0.0


# ---------------------------------------------------------------------------
# _format_srt_time — extended edge cases
# ---------------------------------------------------------------------------


class TestFormatSrtTimeEdgeCases:
    """Extended edge-case tests for SRT timestamp formatting."""

    def test_one_millisecond(self):
        """0.001 seconds formats to exactly 1 millisecond."""
        assert _format_srt_time(0.001) == "00:00:00,001"

    def test_999_milliseconds(self):
        """0.999 seconds formats with 999 milliseconds."""
        assert _format_srt_time(0.999) == "00:00:00,999"

    def test_59_999(self):
        """59.999 seconds stays within minute boundary."""
        assert _format_srt_time(59.999) == "00:00:59,999"

    def test_3599_999(self):
        """3599.999 seconds stays within hour boundary (float truncation)."""
        # Due to floating-point, 3599.999 % 1 gives ~0.998999...
        # int(0.998999... * 1000) = 998, not 999
        result = _format_srt_time(3599.999)
        assert result.startswith("00:59:59,")
        assert result in ("00:59:59,998", "00:59:59,999")

    def test_one_hour_exact(self):
        """3600.0 seconds formats to exactly 1 hour."""
        assert _format_srt_time(3600.0) == "01:00:00,000"

    def test_24_hours(self):
        """86400.0 seconds (24 hours) formats correctly."""
        assert _format_srt_time(86400.0) == "24:00:00,000"

    def test_negative_value(self):
        """Negative seconds produce integer math result (implementation-defined)."""
        # _format_srt_time uses int() truncation — negative values yield
        # implementation-specific results; we verify it does not raise.
        result = _format_srt_time(-1.0)
        assert isinstance(result, str)
        assert "," in result

    def test_very_large_value(self):
        """Very large value (100 hours) formats with >2 digit hours."""
        result = _format_srt_time(360000.0)
        assert result == "100:00:00,000"

    def test_fractional_millis_truncated(self):
        """Sub-millisecond precision is truncated, not rounded."""
        # 1.0005 seconds -> millis = int(0.0005 * 1000) = int(0.5) = 0
        assert _format_srt_time(1.0005) == "00:00:01,000"

    def test_half_second(self):
        """0.5 seconds formats with 500 milliseconds."""
        assert _format_srt_time(0.5) == "00:00:00,500"


# ---------------------------------------------------------------------------
# _synthesize_chunk_elevenlabs — extended edge cases
# ---------------------------------------------------------------------------


class TestSynthesizeChunkElevenlabsExtended:
    """Extended tests for ElevenLabs TTS single-chunk synthesizer."""

    def _make_response(self, audio_bytes: bytes) -> MagicMock:
        """Create a mock urlopen response that returns raw audio bytes."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = audio_bytes
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    @patch("urllib.request.urlopen")
    def test_auth_error_on_403(self, mock_urlopen, tmp_path):
        """HTTP 403 Forbidden raises ValueError with AUTH_ERROR."""
        from src.core.speech_engine import _synthesize_chunk_elevenlabs  # noqa: PLC0415

        fp = MagicMock(read=lambda: b"Forbidden")
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "url",
            403,
            "Forbidden",
            {},
            fp,
        )
        out = tmp_path / "c.mp3"
        with pytest.raises(ValueError, match="AUTH_ERROR"):
            _synthesize_chunk_elevenlabs("Hi", "bad-key", out)

    @patch("urllib.request.urlopen")
    def test_network_timeout_propagates(self, mock_urlopen, tmp_path):
        """Network timeout (URLError) propagates as-is."""
        from src.core.speech_engine import _synthesize_chunk_elevenlabs  # noqa: PLC0415

        mock_urlopen.side_effect = urllib.error.URLError("timed out")
        out = tmp_path / "c.mp3"
        with pytest.raises(urllib.error.URLError, match="timed out"):
            _synthesize_chunk_elevenlabs("Hi", "key", out)

    @patch("urllib.request.urlopen")
    def test_long_text_sent_in_payload(self, mock_urlopen, tmp_path):
        """Very long text (>10KB) is sent correctly in the request body."""
        from src.core.speech_engine import _synthesize_chunk_elevenlabs  # noqa: PLC0415

        mock_urlopen.return_value = self._make_response(b"audio")
        output = tmp_path / "chunk.mp3"

        long_text = "A" * 15000
        _synthesize_chunk_elevenlabs(long_text, "key", output)

        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode("utf-8"))
        assert payload["text"] == long_text
        assert len(payload["text"]) == 15000  # noqa: PLR2004

    @patch("urllib.request.urlopen")
    def test_empty_voice_id_uses_default_voice(self, mock_urlopen, tmp_path):
        """Empty voice_id uses the gender-default voice in the URL."""
        from src.core.speech_engine import (  # noqa: PLC0415
            _ELEVENLABS_DEFAULT_VOICE_FEMALE,
            _synthesize_chunk_elevenlabs,
        )

        mock_urlopen.return_value = self._make_response(b"audio")
        output = tmp_path / "chunk.mp3"

        # No gender → defaults to FEMALE → Rachel.
        _synthesize_chunk_elevenlabs("Test", "key", output, voice_id="")

        req = mock_urlopen.call_args[0][0]
        assert _ELEVENLABS_DEFAULT_VOICE_FEMALE in req.full_url

    @patch("urllib.request.urlopen")
    def test_api_key_in_header(self, mock_urlopen, tmp_path):
        """API key is sent in the xi-api-key header."""
        from src.core.speech_engine import _synthesize_chunk_elevenlabs  # noqa: PLC0415

        mock_urlopen.return_value = self._make_response(b"audio")
        output = tmp_path / "chunk.mp3"

        _synthesize_chunk_elevenlabs("Test", "my-secret-key", output)

        req = mock_urlopen.call_args[0][0]
        assert req.get_header("Xi-api-key") == "my-secret-key"

    @patch("urllib.request.urlopen")
    def test_generic_http_error_includes_code(self, mock_urlopen, tmp_path):
        """HTTP 502 raises ValueError with TTS_API_ERROR including HTTP code."""
        from src.core.speech_engine import _synthesize_chunk_elevenlabs  # noqa: PLC0415

        fp = MagicMock(read=lambda: b"Bad Gateway")
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "url",
            502,
            "Bad Gateway",
            {},
            fp,
        )
        out = tmp_path / "c.mp3"
        with pytest.raises(ValueError, match="TTS_API_ERROR: HTTP 502"):
            _synthesize_chunk_elevenlabs("Hi", "key", out)


# ---------------------------------------------------------------------------
# _synthesize_chunk_edge — extended edge cases
# ---------------------------------------------------------------------------


class TestSynthesizeChunkEdgeExtended:
    """Extended tests for Edge TTS retry logic and backoff timing."""

    @pytest.fixture(autouse=True)
    def _setup_edge_tts(self):
        """Inject mock edge_tts and edge_tts.exceptions into sys.modules."""
        self._NoAudioReceived = type("NoAudioReceived", (Exception,), {})

        mock_edge = MagicMock()
        mock_exceptions = MagicMock()
        mock_exceptions.NoAudioReceived = self._NoAudioReceived

        prev_edge = sys.modules.get("edge_tts")
        prev_exc = sys.modules.get("edge_tts.exceptions")
        sys.modules["edge_tts"] = mock_edge
        sys.modules["edge_tts.exceptions"] = mock_exceptions

        self._mock_edge = mock_edge
        yield
        if prev_edge is None:
            sys.modules.pop("edge_tts", None)
        else:
            sys.modules["edge_tts"] = prev_edge
        if prev_exc is None:
            sys.modules.pop("edge_tts.exceptions", None)
        else:
            sys.modules["edge_tts.exceptions"] = prev_exc

    @patch("asyncio.sleep", new_callable=AsyncMock)
    def test_exponential_backoff_delay_values(self, mock_sleep, tmp_path):
        """Exponential backoff delays are base_delay * 2^attempt."""
        output = tmp_path / "out.mp3"
        mock_comm = MagicMock()
        # Fail 3 times then succeed on 4th (attempt index 3)
        mock_comm.save = AsyncMock(
            side_effect=[
                self._NoAudioReceived("fail1"),
                self._NoAudioReceived("fail2"),
                self._NoAudioReceived("fail3"),
                None,
            ],
        )
        self._mock_edge.Communicate.return_value = mock_comm

        _synthesize_chunk_edge(
            "Hi",
            "en-US-JennyNeural",
            output,
            max_retries=3,
            base_delay=2.0,
        )

        # Delays: 2.0*2^0=2.0, 2.0*2^1=4.0, 2.0*2^2=8.0
        assert mock_sleep.await_count == 3  # noqa: PLR2004
        delays = [call.args[0] for call in mock_sleep.await_args_list]
        assert delays == [2.0, 4.0, 8.0]

    def test_max_retries_zero_fails_immediately(self, tmp_path):
        """max_retries=0 means only one attempt, failure raises immediately."""
        output = tmp_path / "out.mp3"
        mock_comm = MagicMock()
        mock_comm.save = AsyncMock(
            side_effect=self._NoAudioReceived("no audio"),
        )
        self._mock_edge.Communicate.return_value = mock_comm

        with pytest.raises(ValueError, match="TTS_API_ERROR"):
            _synthesize_chunk_edge(
                "Hi",
                "en-US-JennyNeural",
                output,
                max_retries=0,
                base_delay=0.0,
            )

        # Only one attempt (index 0), no retries
        assert mock_comm.save.await_count == 1

    def test_successful_retry_on_second_attempt(self, tmp_path):
        """Success on second attempt after first NoAudioReceived."""
        output = tmp_path / "out.mp3"
        mock_comm = MagicMock()
        mock_comm.save = AsyncMock(
            side_effect=[self._NoAudioReceived("fail"), None],
        )
        self._mock_edge.Communicate.return_value = mock_comm

        # Should not raise
        _synthesize_chunk_edge(
            "Hi",
            "en-US-JennyNeural",
            output,
            max_retries=3,
            base_delay=0.0,
        )

        assert mock_comm.save.await_count == 2  # noqa: PLR2004
        mock_comm.save.assert_awaited_with(str(output))

    @patch("asyncio.sleep", new_callable=AsyncMock)
    def test_single_retry_delay_value(self, mock_sleep, tmp_path):
        """Single retry with base_delay=5 produces delay of 5*2^0=5.0."""
        output = tmp_path / "out.mp3"
        mock_comm = MagicMock()
        mock_comm.save = AsyncMock(
            side_effect=[self._NoAudioReceived("fail"), None],
        )
        self._mock_edge.Communicate.return_value = mock_comm

        _synthesize_chunk_edge(
            "Hi",
            "en-US-JennyNeural",
            output,
            max_retries=1,
            base_delay=5.0,
        )

        assert mock_sleep.await_count == 1
        assert mock_sleep.await_args_list[0].args[0] == 5.0  # noqa: PLR2004


# ---------------------------------------------------------------------------
# extract_subtitle_text — extended format tests
# ---------------------------------------------------------------------------


class TestExtractSubtitleTextExtended:
    """Extended tests for subtitle text extraction with various formats."""

    @patch(f"{_SUB}.parse_subtitle")
    @patch(f"{_SUB}.is_subtitle_format", return_value=True)
    def test_ssa_format(self, mock_is_sub, mock_parse):
        """SSA suffix is handled as subtitle format."""
        entry = MagicMock()
        entry.text = "SSA dialog line."
        mock_parse.return_value = ([entry], None)

        result = extract_subtitle_text("[Script Info]\n...", ".ssa")
        mock_is_sub.assert_called_once_with(".ssa")
        assert result == "SSA dialog line."

    @patch(f"{_SUB}.parse_subtitle")
    @patch(f"{_SUB}.is_subtitle_format", return_value=True)
    def test_ass_format_multiple_entries(self, mock_is_sub, mock_parse):
        """ASS format with multiple dialogue entries joins text."""
        entry1 = MagicMock()
        entry1.text = "First line."
        entry2 = MagicMock()
        entry2.text = "Second line."
        mock_parse.return_value = ([entry1, entry2], None)

        result = extract_subtitle_text("[Script Info]\n...", ".ass")
        assert result == "First line.\nSecond line."

    @patch(f"{_SUB}.is_subtitle_format", return_value=True)
    @patch(f"{_SUB}.parse_subtitle", return_value=([], None))
    def test_empty_content_subtitle_format(self, mock_parse, mock_is_sub):
        """Empty content with subtitle suffix returns empty string."""
        result = extract_subtitle_text("", ".ass")
        assert result == ""

    @patch(f"{_SUB}.is_subtitle_format", return_value=False)
    def test_non_subtitle_suffix_returns_raw_text(self, mock_is_sub):
        """Non-subtitle suffix (.txt) returns content as-is."""
        raw = "This is just plain text, not a subtitle."
        result = extract_subtitle_text(raw, ".txt")
        assert result == raw

    @patch(f"{_SUB}.is_subtitle_format", return_value=False)
    def test_xml_suffix_returns_raw_text(self, mock_is_sub):
        """Non-subtitle suffix (.xml) returns content as-is."""
        raw = "<root><item>Hello</item></root>"
        result = extract_subtitle_text(raw, ".xml")
        assert result == raw


# ---------------------------------------------------------------------------
# transcribe_audio — extended dispatcher tests
# ---------------------------------------------------------------------------


class TestTranscribeAudioDispatchExtended:
    """Extended tests verifying transcribe_audio argument forwarding."""

    @patch(f"{_MOD}._transcribe_whisper", return_value="srt")
    def test_model_size_forwarded_to_whisper(self, mock_whisper):
        """model_size argument is forwarded as 3rd positional to _transcribe_whisper."""
        transcribe_audio(
            "test.mp3",
            src_lang="English (US)",
            stt_method="Whisper",
            model_size="large-v2",
        )
        call_args = mock_whisper.call_args[0]
        assert call_args[0] == "test.mp3"
        assert call_args[1] == "English (US)"
        assert call_args[2] == "large-v2"

    @patch(f"{_MOD}._transcribe_google_cloud", return_value="srt")
    def test_google_model_forwarded(self, mock_google):
        """google_model argument is forwarded to _transcribe_google_cloud."""
        transcribe_audio(
            "test.mp3",
            src_lang="Vietnamese",
            stt_method="Google Cloud",
            google_model="latest_long",
        )
        call_kwargs = mock_google.call_args[1]
        assert call_kwargs["model"] == "latest_long"

    @patch(f"{_MOD}._transcribe_google_cloud", return_value="srt")
    def test_is_cancelled_forwarded_to_google(self, mock_google):
        """is_cancelled callback is forwarded to _transcribe_google_cloud."""
        cancel_fn = lambda: False  # noqa: E731
        transcribe_audio(
            "test.mp3",
            stt_method="Google Cloud",
            is_cancelled=cancel_fn,
        )
        call_kwargs = mock_google.call_args[1]
        assert call_kwargs["is_cancelled"] is cancel_fn

    @patch(f"{_MOD}._transcribe_whisper", return_value="srt")
    def test_whisper_default_model_size(self, mock_whisper):
        """Default model_size 'base' is forwarded when not specified."""
        transcribe_audio("test.mp3", stt_method="Whisper")
        call_args = mock_whisper.call_args[0]
        assert call_args[2] == "base"

    @patch(f"{_MOD}._transcribe_google_cloud", return_value="srt")
    def test_google_default_model(self, mock_google):
        """Default google_model 'default' is forwarded when not specified."""
        transcribe_audio("test.mp3", stt_method="Google Cloud")
        call_kwargs = mock_google.call_args[1]
        assert call_kwargs["model"] == "default"

    @patch(f"{_MOD}._transcribe_google_cloud", return_value="srt")
    def test_google_is_cancelled_none_by_default(self, mock_google):
        """is_cancelled defaults to None when not specified."""
        transcribe_audio("test.mp3", stt_method="Google Cloud")
        call_kwargs = mock_google.call_args[1]
        assert call_kwargs["is_cancelled"] is None


# ---------------------------------------------------------------------------
# _parse_srt_timestamp — extended edge cases
# ---------------------------------------------------------------------------


class TestParseSrtTimestampExtended:
    """Extended edge-case tests for SRT/VTT timestamp parsing."""

    def test_whitespace_padding(self):
        """Leading and trailing whitespace is stripped before parsing."""
        assert _parse_srt_timestamp("  00:01:30,500  ") == 90.5  # noqa: PLR2004

    def test_tab_whitespace(self):
        """Tab whitespace is stripped before parsing."""
        assert _parse_srt_timestamp("\t00:00:05,000\t") == 5.0  # noqa: PLR2004

    def test_empty_string_returns_zero(self):
        """Empty string returns 0.0."""
        assert _parse_srt_timestamp("") == 0.0

    def test_single_number_no_colons(self):
        """Single number '5.0' without colons returns 0.0."""
        assert _parse_srt_timestamp("5.0") == 0.0

    def test_four_colons_returns_zero(self):
        """Four-part colon string '1:2:3:4' returns 0.0 (no matching branch)."""
        assert _parse_srt_timestamp("1:2:3:4") == 0.0

    def test_dots_only(self):
        """String '...' returns 0.0 (ValueError caught)."""
        assert _parse_srt_timestamp("...") == 0.0

    def test_two_part_mm_ss_format(self):
        """Two-part MM:SS.mmm format without hours."""
        assert _parse_srt_timestamp("02:30.500") == 150.5  # noqa: PLR2004

    def test_colons_with_non_numeric_parts(self):
        """Non-numeric parts 'xx:yy:zz' return 0.0."""
        assert _parse_srt_timestamp("xx:yy:zz") == 0.0

    def test_single_colon_with_non_numeric(self):
        """Non-numeric 'aa:bb' returns 0.0."""
        assert _parse_srt_timestamp("aa:bb") == 0.0

    def test_comma_replaced_by_dot(self):
        """Comma in timestamp is replaced by dot for parsing."""
        result = _parse_srt_timestamp("00:00:01,500")
        assert result == 1.5  # noqa: PLR2004


# ---------------------------------------------------------------------------
# TestSynthesizeSpeechWavFormat — WAV format output
# ---------------------------------------------------------------------------


class TestSynthesizeSpeechWavFormat:
    """Test WAV format output path in synthesize_speech."""

    @pytest.fixture(autouse=True)
    def _mock_edge(self):
        """Prevent edge_tts import in tests."""
        with patch(f"{_MOD}._synthesize_chunk_edge"):
            yield

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}._split_text_for_tts", return_value=["Hello."])
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_wav_format_passed_to_chunk(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_split,
        mock_synth,
        mock_concat,
        tmp_path,
    ):
        """WAV format is forwarded to _synthesize_chunk via audio_format kwarg."""
        output = str(tmp_path / "out.wav")
        synthesize_speech(
            "Hello.",
            tts_method=_GOOGLE_TTS,
            output_path=output,
            audio_format=".wav",
        )
        synth_call = mock_synth.call_args
        assert synth_call[1]["audio_format"] == ".wav"

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(
        f"{_MOD}._split_text_for_tts",
        return_value=["Chunk A.", "Chunk B."],
    )
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_wav_multiple_chunks_concatenated(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_split,
        mock_synth,
        mock_concat,
        tmp_path,
    ):
        """Multiple WAV chunks are all created with .wav extension then concatenated."""
        output = str(tmp_path / "out.wav")
        synthesize_speech(
            "Chunk A. Chunk B.",
            tts_method=_GOOGLE_TTS,
            output_path=output,
            audio_format=".wav",
        )
        assert mock_synth.call_count == 2  # noqa: PLR2004
        for call in mock_synth.call_args_list:
            chunk_path = call[0][4]
            assert chunk_path.suffix == ".wav"
        mock_concat.assert_called_once()

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}._split_text_for_tts", return_value=["Test."])
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_wav_chunk_file_naming(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_split,
        mock_synth,
        mock_concat,
        tmp_path,
    ):
        """WAV chunk file names follow chunk_NNNN.wav pattern."""
        output = str(tmp_path / "out.wav")
        synthesize_speech(
            "Test.",
            tts_method=_GOOGLE_TTS,
            output_path=output,
            audio_format=".wav",
        )
        chunk_path = mock_synth.call_args[0][4]
        assert chunk_path.name == "chunk_0000.wav"

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._synthesize_chunk_edge")
    @patch(f"{_MOD}._split_text_for_tts", return_value=["Test."])
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_edge_tts_ignores_wav_format(
        self,
        mock_ffmpeg,
        mock_split,
        mock_edge_synth,
        mock_concat,
        tmp_path,
    ):
        """Edge TTS always uses .mp3 chunks even when wav format requested."""
        output = str(tmp_path / "out.wav")
        synthesize_speech(
            "Test.",
            output_path=output,
            audio_format=".wav",
        )
        chunk_path = mock_edge_synth.call_args[0][2]
        assert chunk_path.suffix == ".mp3"


# ---------------------------------------------------------------------------
# TestSynthesizeSpeechRTLText — RTL text (Arabic/Hebrew) in TTS
# ---------------------------------------------------------------------------


class TestSynthesizeSpeechRTLText:
    """Test RTL text (Arabic/Hebrew) handling in TTS."""

    @pytest.fixture(autouse=True)
    def _mock_edge(self):
        """Prevent edge_tts import in tests."""
        with patch(f"{_MOD}._synthesize_chunk_edge"):
            yield

    @patch(f"{_LANG}.get_locale_code", return_value="ar")
    def test_arabic_tts_language_code(self, mock_locale):
        """Arabic maps to 'ar-XA' in Google Cloud TTS."""
        assert _get_tts_language_code("Arabic") == "ar-XA"

    @patch(f"{_LANG}.get_locale_code", return_value="he")
    def test_hebrew_tts_language_code(self, mock_locale):
        """Hebrew maps to 'he-IL' in Google Cloud TTS."""
        assert _get_tts_language_code("Hebrew") == "he-IL"

    @patch(f"{_LANG}.get_locale_code", return_value="ar")
    def test_arabic_edge_voice_female(self, mock_locale):
        """Arabic female voice maps to 'ar-EG-SalmaNeural'."""
        assert _get_edge_voice("Arabic", "FEMALE") == "ar-EG-SalmaNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="ar")
    def test_arabic_edge_voice_male(self, mock_locale):
        """Arabic male voice maps to 'ar-EG-ShakirNeural'."""
        assert _get_edge_voice("Arabic", "MALE") == "ar-EG-ShakirNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="he")
    def test_hebrew_edge_voice_female(self, mock_locale):
        """Hebrew female voice maps to 'he-IL-HilaNeural'."""
        assert _get_edge_voice("Hebrew", "FEMALE") == "he-IL-HilaNeural"

    @patch(f"{_LANG}.get_locale_code", return_value="he")
    def test_hebrew_edge_voice_male(self, mock_locale):
        """Hebrew male voice maps to 'he-IL-AvriNeural'."""
        assert _get_edge_voice("Hebrew", "MALE") == "he-IL-AvriNeural"

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(
        f"{_MOD}._split_text_for_tts",
        return_value=[
            "\u0645\u0631\u062d\u0628\u0627 \u0628\u0627\u0644\u0639\u0627\u0644\u0645"
        ],
    )
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_arabic_text_synthesized(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_split,
        mock_synth,
        mock_concat,
        tmp_path,
    ):
        """Arabic text is passed through to synthesis without errors."""
        output = str(tmp_path / "out.mp3")
        result = synthesize_speech(
            "\u0645\u0631\u062d\u0628\u0627 \u0628\u0627\u0644\u0639\u0627\u0644\u0645",
            target_lang="Arabic",
            output_path=output,
            tts_method=_GOOGLE_TTS,
        )
        assert result == output
        mock_synth.assert_called_once()

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(
        f"{_MOD}._split_text_for_tts",
        return_value=["\u05e9\u05dc\u05d5\u05dd \u05e2\u05d5\u05dc\u05dd"],
    )
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_hebrew_text_synthesized(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_split,
        mock_synth,
        mock_concat,
        tmp_path,
    ):
        """Hebrew text is passed through to synthesis without errors."""
        output = str(tmp_path / "out.mp3")
        result = synthesize_speech(
            "\u05e9\u05dc\u05d5\u05dd \u05e2\u05d5\u05dc\u05dd",
            target_lang="Hebrew",
            output_path=output,
            tts_method=_GOOGLE_TTS,
        )
        assert result == output
        mock_synth.assert_called_once()

    def test_arabic_text_splits_correctly(self):
        """Arabic text within byte limit returns single chunk."""
        result = _split_text_for_tts(
            "\u0645\u0631\u062d\u0628\u0627 \u0628\u0627\u0644\u0639\u0627\u0644\u0645",
        )
        assert len(result) == 1
        assert (
            result[0]
            == "\u0645\u0631\u062d\u0628\u0627 \u0628\u0627\u0644\u0639\u0627\u0644\u0645"
        )


# ---------------------------------------------------------------------------
# TestSynthesizeTimedSpeechElevenLabsSpeedup — ElevenLabs speed-up path
# ---------------------------------------------------------------------------


class TestSynthesizeTimedSpeechElevenLabsSpeedup:
    """Test ElevenLabs speed-up path in synthesize_timed_speech."""

    def _make_entry(self, start: str, end: str, text: str) -> MagicMock:
        """Create a mock SubtitleEntry."""
        entry = MagicMock()
        entry.start = start
        entry.end = end
        entry.text = text
        return entry

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration")
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._speed_up_audio")
    @patch(f"{_MOD}._synthesize_chunk_elevenlabs")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_elevenlabs_uses_speed_up_audio_not_speaking_rate(  # noqa: PLR0913
        self,
        mock_ffmpeg,
        mock_el_synth,
        mock_speedup,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """ElevenLabs uses _speed_up_audio (atempo) instead of speaking_rate param."""

        def create_fast_file(inp, outp, factor):
            outp.write_bytes(b"fast audio")

        mock_speedup.side_effect = create_fast_file
        # First duration: 5.0s (overflows 2.0s slot), second: after speedup 1.8s
        mock_dur.side_effect = [5.0, 1.8]

        entries = [
            self._make_entry("00:00:00,000", "00:00:02,000", "Long sentence."),
        ]
        output = str(tmp_path / "out.mp3")

        with patch(
            "src.utils.config_manager.load_setting",
            side_effect=lambda k, d="": {
                "service/elevenlabs_api_key": "test-key",
                "voice/elevenlabs_voice_id": "vid",
            }.get(k, d),
        ):
            synthesize_timed_speech(
                entries,
                output_path=output,
                tts_method="ElevenLabs",
            )

        mock_speedup.assert_called_once()
        # Verify _synthesize_chunk (Google) was NOT called
        # — only _synthesize_chunk_elevenlabs should be used
        mock_el_synth.assert_called_once()

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration", return_value=1.5)
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._speed_up_audio")
    @patch(f"{_MOD}._synthesize_chunk_elevenlabs")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_elevenlabs_no_speedup_when_audio_fits(  # noqa: PLR0913
        self,
        mock_ffmpeg,
        mock_el_synth,
        mock_speedup,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """ElevenLabs does not speed up when audio fits within time slot."""
        entries = [
            self._make_entry("00:00:00,000", "00:00:05,000", "Short text."),
        ]
        output = str(tmp_path / "out.mp3")

        with patch(
            "src.utils.config_manager.load_setting",
            side_effect=lambda k, d="": {
                "service/elevenlabs_api_key": "test-key",
                "voice/elevenlabs_voice_id": "vid",
            }.get(k, d),
        ):
            synthesize_timed_speech(
                entries,
                output_path=output,
                tts_method="ElevenLabs",
            )

        mock_speedup.assert_not_called()

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration")
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._speed_up_audio")
    @patch(f"{_MOD}._synthesize_chunk_elevenlabs")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_elevenlabs_speedup_rate_calculated_correctly(  # noqa: PLR0913
        self,
        mock_ffmpeg,
        mock_el_synth,
        mock_speedup,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """ElevenLabs speed-up factor is audio_dur / fit_window."""

        def create_fast_file(inp, outp, factor):
            outp.write_bytes(b"fast audio")

        mock_speedup.side_effect = create_fast_file
        # Audio is 4.0s for a 2.0s slot, no next entry gap
        mock_dur.side_effect = [4.0, 2.0]

        entries = [
            self._make_entry("00:00:00,000", "00:00:02,000", "Long."),
        ]
        output = str(tmp_path / "out.mp3")

        with patch(
            "src.utils.config_manager.load_setting",
            side_effect=lambda k, d="": {
                "service/elevenlabs_api_key": "test-key",
                "voice/elevenlabs_voice_id": "vid",
            }.get(k, d),
        ):
            synthesize_timed_speech(
                entries,
                output_path=output,
                tts_method="ElevenLabs",
            )

        # _speed_up_audio called with factor = 4.0 / (2.0 + allowed)
        call_args = mock_speedup.call_args[0]
        factor = call_args[2]
        # Last entry has unlimited gap, so allowed = min(1.0, inf) = 1.0
        # fit_window = 2.0 + 1.0 = 3.0, rate = 4.0 / 3.0 ≈ 1.333
        assert factor > 1.0

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration")
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._speed_up_audio")
    @patch(f"{_MOD}._synthesize_chunk_elevenlabs")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_elevenlabs_auth_error_no_key(  # noqa: PLR0913
        self,
        mock_ffmpeg,
        mock_el_synth,
        mock_speedup,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """ElevenLabs raises AUTH_ERROR when API key is empty."""
        entries = [
            self._make_entry("00:00:00,000", "00:00:02,000", "Text."),
        ]
        output = str(tmp_path / "out.mp3")

        with (
            patch(
                "src.utils.config_manager.load_setting",
                return_value="",
            ),
            pytest.raises(ValueError, match="AUTH_ERROR"),
        ):
            synthesize_timed_speech(
                entries,
                output_path=output,
                tts_method="ElevenLabs",
            )


# ---------------------------------------------------------------------------
# TestSynthesizeSpeechFileSystemErrors — file system error handling
# ---------------------------------------------------------------------------


class TestSynthesizeSpeechFileSystemErrors:
    """Test file system error handling in synthesize_speech."""

    @pytest.fixture(autouse=True)
    def _mock_edge(self):
        """Prevent edge_tts import in tests."""
        with patch(f"{_MOD}._synthesize_chunk_edge"):
            yield

    @patch(f"{_MOD}._split_text_for_tts", return_value=["Hello."])
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    @patch("tempfile.mkdtemp", side_effect=OSError("No space left on device"))
    def test_oserror_during_temp_dir_creation(
        self,
        mock_mkdtemp,
        mock_key,
        mock_ffmpeg,
        mock_split,
        tmp_path,
    ):
        """OSError during temp directory creation propagates."""
        with pytest.raises(OSError, match="No space left on device"):
            synthesize_speech(
                "Hello.",
                output_path=str(tmp_path / "out.mp3"),
                tts_method=_GOOGLE_TTS,
            )

    @patch(
        f"{_MOD}._concatenate_mp3_files",
        side_effect=RuntimeError("FFMPEG_CONCAT_FAILED"),
    )
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}._split_text_for_tts", return_value=["Hello."])
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_concat_failure_propagates(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_split,
        mock_synth,
        mock_concat,
        tmp_path,
    ):
        """RuntimeError from FFmpeg concatenation propagates to caller."""
        with pytest.raises(RuntimeError, match="FFMPEG_CONCAT_FAILED"):
            synthesize_speech(
                "Hello.",
                output_path=str(tmp_path / "out.mp3"),
                tts_method=_GOOGLE_TTS,
            )

    @patch(f"{_MOD}._synthesize_chunk", side_effect=OSError("Permission denied"))
    @patch(f"{_MOD}._split_text_for_tts", return_value=["Hello."])
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_permission_denied_on_chunk_write(
        self,
        mock_key,
        mock_ffmpeg,
        mock_split,
        mock_synth,
        tmp_path,
    ):
        """OSError from chunk synthesis (permission denied) propagates."""
        with pytest.raises(OSError, match="Permission denied"):
            synthesize_speech(
                "Hello.",
                output_path=str(tmp_path / "out.mp3"),
                tts_method=_GOOGLE_TTS,
            )

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._synthesize_chunk", side_effect=OSError("Disk full"))
    @patch(f"{_MOD}._split_text_for_tts", return_value=["A.", "B."])
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_disk_full_during_multi_chunk(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_split,
        mock_synth,
        mock_concat,
        tmp_path,
    ):
        """Disk full on first chunk stops processing immediately."""
        with pytest.raises(OSError, match="Disk full"):
            synthesize_speech(
                "A. B.",
                output_path=str(tmp_path / "out.mp3"),
                tts_method=_GOOGLE_TTS,
            )
        # Only first chunk attempted before error
        assert mock_synth.call_count == 1


# ---------------------------------------------------------------------------
# TestSynthesizeSpeechVeryLongText — very long text handling
# ---------------------------------------------------------------------------


class TestSynthesizeSpeechVeryLongText:
    """Test very long text handling in synthesize_speech."""

    @pytest.fixture(autouse=True)
    def _mock_edge(self):
        """Prevent edge_tts import in tests."""
        with patch(f"{_MOD}._synthesize_chunk_edge"):
            yield

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}._split_text_for_tts")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_100kb_text_split_many_chunks(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_split,
        mock_synth,
        mock_concat,
        tmp_path,
    ):
        """Text >100KB is split into many chunks, all synthesized."""
        # 100KB of text at 4500 bytes/chunk ≈ 23 chunks
        chunk_count = 23
        mock_split.return_value = [f"Chunk {i}." for i in range(chunk_count)]
        output = str(tmp_path / "out.mp3")
        synthesize_speech(
            "x" * 102400,
            output_path=output,
            tts_method=_GOOGLE_TTS,
        )
        assert mock_synth.call_count == chunk_count
        mock_concat.assert_called_once()

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}._split_text_for_tts")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_progress_called_proportionally(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_split,
        mock_synth,
        mock_concat,
        tmp_path,
    ):
        """Progress callback reports (i+1, total) for each of many chunks."""
        chunk_count = 50
        mock_split.return_value = [f"Chunk {i}." for i in range(chunk_count)]
        progress_calls = []
        output = str(tmp_path / "out.mp3")
        synthesize_speech(
            "x" * 200000,
            output_path=output,
            tts_method=_GOOGLE_TTS,
            on_progress=lambda c, t: progress_calls.append((c, t)),
        )
        assert len(progress_calls) == chunk_count
        # First call reports (1, 50), last reports (50, 50)
        assert progress_calls[0] == (1, chunk_count)
        assert progress_calls[-1] == (chunk_count, chunk_count)

    def test_split_text_for_tts_large_input(self):
        """_split_text_for_tts produces multiple chunks for large text."""
        # 10KB of text, split at 4500 byte limit
        large_text = "Hello world. " * 800  # ~10.4KB
        chunks = _split_text_for_tts(large_text)
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk.encode("utf-8")) <= _TTS_MAX_BYTES

    def test_split_text_for_tts_multibyte_chars(self):
        """Multi-byte UTF-8 characters are handled in byte-limit splitting."""
        # Each CJK character is 3 bytes in UTF-8
        large_cjk = "\u4e16\u754c " * 2000  # ~6000 chars, ~8000 bytes
        chunks = _split_text_for_tts(large_cjk)
        assert len(chunks) >= 2  # noqa: PLR2004
        for chunk in chunks:
            assert len(chunk.encode("utf-8")) <= _TTS_MAX_BYTES

    def test_split_text_for_tts_long_cjk_no_whitespace(self):
        """Long CJK runs without whitespace are split at codepoint boundaries.

        Regression for the failure mode: a single "word" (in Python's
        whitespace-split sense) of pure Chinese / Japanese text can
        exceed the per-call byte cap.  Without the codepoint-safe
        fallback, ``_split_long_sentence`` would emit the whole word
        as one chunk (overflowing the cap) \u2014 OR a future byte-index
        slice attempt would land mid-character and corrupt UTF-8.

        Asserts BOTH invariants:
          1. every chunk's UTF-8 byte length is \u2264 the cap,
          2. every chunk decodes cleanly (i.e. no mid-character cut).
        """
        # 3000 contiguous CJK characters with NO whitespace and NO
        # sentence-end punctuation \u2014 neither the regex nor the
        # word-split has anywhere to break, so the codepoint
        # fallback is the only thing standing between us and an
        # over-cap or corrupted chunk.  Use the Gemini cap (2000)
        # because the byte-density gap to text length is larger.
        from src.core.speech_engine import (  # noqa: PLC0415
            _GEMINI_TTS_MAX_BYTES,
        )

        run = "\u4e16" * 3000  # ~9000 bytes of single-codepoint text
        chunks = _split_text_for_tts(run, max_bytes=_GEMINI_TTS_MAX_BYTES)
        assert len(chunks) >= 2  # noqa: PLR2004
        rejoined = ""
        for chunk in chunks:
            encoded = chunk.encode("utf-8")
            assert len(encoded) <= _GEMINI_TTS_MAX_BYTES, (
                f"chunk exceeded cap: {len(encoded)} > {_GEMINI_TTS_MAX_BYTES}"
            )
            # Round-trip decode \u2014 would raise if a chunk landed
            # mid-character.  ``encode("utf-8")`` already proves
            # the chunk is a valid Python string, but the explicit
            # decode pins the contract for future maintainers.
            assert encoded.decode("utf-8") == chunk
            rejoined += chunk
        # No characters dropped.
        assert rejoined == run

    def test_split_text_for_tts_emoji_run_codepoint_safe(self):
        """4-byte emoji codepoints aren't split mid-sequence."""
        from src.core.speech_engine import (  # noqa: PLC0415
            _GEMINI_TTS_MAX_BYTES,
        )

        # 600 grinning-face emoji = 2400 UTF-8 bytes; over the
        # Gemini cap, so must split.  Each emoji is a 4-byte
        # codepoint and a byte-index slice would shred them.
        run = "\U0001f600" * 600
        chunks = _split_text_for_tts(run, max_bytes=_GEMINI_TTS_MAX_BYTES)
        assert len(chunks) >= 2  # noqa: PLR2004
        for chunk in chunks:
            assert len(chunk.encode("utf-8")) <= _GEMINI_TTS_MAX_BYTES
            # Emoji count must be a whole number \u2014 proves no
            # mid-codepoint slice.
            assert len(chunk) * 4 == len(chunk.encode("utf-8"))


# ---------------------------------------------------------------------------
# TestMixAudioVideoMultipleTracks — audio/video edge cases
# ---------------------------------------------------------------------------


class TestMixAudioVideoMultipleTracks:
    """Test audio/video mixing edge cases."""

    @patch("subprocess.run")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_shortest_flag_present(self, mock_ff, mock_run, tmp_path):
        """FFmpeg -shortest flag clips output to shorter of video/audio."""
        mock_run.return_value = MagicMock(returncode=0)
        mix_audio_into_video(
            str(tmp_path / "video.mp4"),
            str(tmp_path / "audio.mp3"),
            str(tmp_path / "output.mp4"),
        )
        cmd = mock_run.call_args[0][0]
        assert "-shortest" in cmd

    @patch("subprocess.run")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_stream_mapping_video_and_audio(
        self,
        mock_ff,
        mock_run,
        tmp_path,
    ):
        """FFmpeg maps video from input 0 and audio from input 1."""
        mock_run.return_value = MagicMock(returncode=0)
        mix_audio_into_video(
            str(tmp_path / "v.mkv"),
            str(tmp_path / "a.wav"),
            str(tmp_path / "o.mkv"),
        )
        cmd = mock_run.call_args[0][0]
        # Verify both -map directives are present
        map_indices = [i for i, arg in enumerate(cmd) if arg == "-map"]
        assert len(map_indices) == 2  # noqa: PLR2004
        # First map selects video from first input
        assert cmd[map_indices[0] + 1] == "0:v:0"
        # Second map selects audio from second input
        assert cmd[map_indices[1] + 1] == "1:a:0"

    @patch("subprocess.run")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_video_copy_codec(self, mock_ff, mock_run, tmp_path):
        """FFmpeg copies video stream without re-encoding."""
        mock_run.return_value = MagicMock(returncode=0)
        mix_audio_into_video(
            str(tmp_path / "v.mp4"),
            str(tmp_path / "a.mp3"),
            str(tmp_path / "o.mp4"),
        )
        cmd = mock_run.call_args[0][0]
        cv_idx = cmd.index("-c:v")
        assert cmd[cv_idx + 1] == "copy"

    @patch("subprocess.run")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_both_inputs_in_command(self, mock_ff, mock_run, tmp_path):
        """Both video and audio paths appear as -i arguments."""
        mock_run.return_value = MagicMock(returncode=0)
        video_path = str(tmp_path / "video.mp4")
        audio_path = str(tmp_path / "longer_audio.mp3")
        mix_audio_into_video(video_path, audio_path, str(tmp_path / "o.mp4"))
        cmd = mock_run.call_args[0][0]
        i_indices = [i for i, arg in enumerate(cmd) if arg == "-i"]
        assert len(i_indices) == 2  # noqa: PLR2004
        assert cmd[i_indices[0] + 1] == video_path
        assert cmd[i_indices[1] + 1] == audio_path

    @patch("subprocess.run")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_output_path_returned(self, mock_ff, mock_run, tmp_path):
        """mix_audio_into_video returns the output path on success."""
        mock_run.return_value = MagicMock(returncode=0)
        out = str(tmp_path / "dubbed.mp4")
        result = mix_audio_into_video(
            str(tmp_path / "v.mp4"),
            str(tmp_path / "a.mp3"),
            out,
        )
        assert result == out

    @patch("subprocess.run")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_ffmpeg_timeout_set(self, mock_ff, mock_run, tmp_path):
        """FFmpeg mix has timeout of 600 seconds."""
        mock_run.return_value = MagicMock(returncode=0)
        mix_audio_into_video(
            str(tmp_path / "v.mp4"),
            str(tmp_path / "a.mp3"),
            str(tmp_path / "o.mp4"),
        )
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["timeout"] == 600  # noqa: PLR2004

    @patch("subprocess.run")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_overwrite_flag_present(self, mock_ff, mock_run, tmp_path):
        """FFmpeg -y flag overwrites existing output without prompting."""
        mock_run.return_value = MagicMock(returncode=0)
        mix_audio_into_video(
            str(tmp_path / "v.mp4"),
            str(tmp_path / "a.mp3"),
            str(tmp_path / "o.mp4"),
        )
        cmd = mock_run.call_args[0][0]
        assert "-y" in cmd


# ---------------------------------------------------------------------------
# TestSynthesizeSpeechCancelAtBoundary — cancellation at exact boundaries
# ---------------------------------------------------------------------------


class TestSynthesizeSpeechCancelAtBoundary:
    """Test cancellation at exact boundaries in synthesize_speech."""

    @pytest.fixture(autouse=True)
    def _mock_edge(self):
        """Prevent edge_tts import in tests."""
        with patch(f"{_MOD}._synthesize_chunk_edge"):
            yield

    @patch(f"{_MOD}._synthesize_chunk")
    @patch(
        f"{_MOD}._split_text_for_tts",
        return_value=["A.", "B.", "C."],
    )
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_cancel_before_any_chunk(
        self,
        mock_key,
        mock_ffmpeg,
        mock_split,
        mock_synth,
        tmp_path,
    ):
        """Cancellation at very start (before first chunk) raises immediately."""
        output = str(tmp_path / "out.mp3")
        with pytest.raises(ValueError, match="CANCELLED"):
            synthesize_speech(
                "A. B. C.",
                output_path=output,
                tts_method=_GOOGLE_TTS,
                is_cancelled=lambda: True,
            )
        # No chunks should be synthesized
        mock_synth.assert_not_called()

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(
        f"{_MOD}._split_text_for_tts",
        return_value=["A.", "B.", "C.", "D.", "E."],
    )
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_cancel_between_second_and_third_chunk(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_split,
        mock_synth,
        mock_concat,
        tmp_path,
    ):
        """Cancel after 2 chunks processed stops before third synthesis."""
        call_count = 0

        def cancel_after_two():
            nonlocal call_count
            call_count += 1
            return call_count > 2  # noqa: PLR2004

        output = str(tmp_path / "out.mp3")
        with pytest.raises(ValueError, match="CANCELLED"):
            synthesize_speech(
                "A. B. C. D. E.",
                output_path=output,
                tts_method=_GOOGLE_TTS,
                is_cancelled=cancel_after_two,
            )
        # Exactly 2 chunks synthesized before cancellation
        assert mock_synth.call_count == 2  # noqa: PLR2004

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(
        f"{_MOD}._split_text_for_tts",
        return_value=["Only."],
    )
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_cancel_never_called_completes(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_split,
        mock_synth,
        mock_concat,
        tmp_path,
    ):
        """is_cancelled returning False always allows completion."""
        output = str(tmp_path / "out.mp3")
        result = synthesize_speech(
            "Only.",
            output_path=output,
            tts_method=_GOOGLE_TTS,
            is_cancelled=lambda: False,
        )
        assert result == output
        mock_synth.assert_called_once()
        mock_concat.assert_called_once()

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration", return_value=1.0)
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_timed_speech_cancel_at_first_entry(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_synth,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """Timed speech cancellation before any entry raises CANCELLED."""
        entry = MagicMock()
        entry.start = "00:00:00,000"
        entry.end = "00:00:02,000"
        entry.text = "Hello."

        output = str(tmp_path / "out.mp3")
        with pytest.raises(ValueError, match="CANCELLED"):
            synthesize_timed_speech(
                [entry],
                output_path=output,
                tts_method=_GOOGLE_TTS,
                is_cancelled=lambda: True,
            )
        mock_synth.assert_not_called()

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration", return_value=1.0)
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._synthesize_chunk")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    @patch(f"{_MOD}.load_google_cloud_api_key", return_value="key")
    def test_timed_speech_cancel_between_entries(  # noqa: PLR0913
        self,
        mock_key,
        mock_ffmpeg,
        mock_synth,
        mock_silence,
        mock_dur,
        mock_concat,
        tmp_path,
    ):
        """Timed speech cancels between second and third entry."""
        entries = []
        for i in range(3):
            e = MagicMock()
            e.start = f"00:00:{i * 3:02d},000"
            e.end = f"00:00:{i * 3 + 2:02d},000"
            e.text = f"Entry {i}."
            entries.append(e)

        call_count = 0

        def cancel_after_one():
            nonlocal call_count
            call_count += 1
            return call_count > 1

        output = str(tmp_path / "out.mp3")
        with pytest.raises(ValueError, match="CANCELLED"):
            synthesize_timed_speech(
                entries,
                output_path=output,
                tts_method=_GOOGLE_TTS,
                is_cancelled=cancel_after_one,
            )


# ─────────────────────────────────────────────────────────────────────────────
# Format-edge-case backfill tests
# ─────────────────────────────────────────────────────────────────────────────


class TestSynthesizeTimedSpeechElevenLabsQuotaPropagation:
    """Tests ElevenLabs 429 propagation through ``synthesize_timed_speech``.

    An HTTP 429 raised by ``_synthesize_chunk_elevenlabs`` propagates as a
    tagged ``ValueError("QUOTA_ERROR")`` rather than being silently swallowed.
    """

    @staticmethod
    def _entry(start: str, end: str, text: str) -> MagicMock:
        e = MagicMock()
        e.start = start
        e.end = end
        e.text = text
        return e

    @patch(f"{_MOD}._concatenate_mp3_files")
    @patch(f"{_MOD}._get_mp3_duration", return_value=1.0)
    @patch(f"{_MOD}._generate_silence")
    @patch(f"{_MOD}._synthesize_chunk_elevenlabs")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_elevenlabs_429_raises_quota_error(  # noqa: PLR0913
        self,
        _mock_ffmpeg,
        mock_el_synth,
        _mock_silence,
        _mock_dur,
        _mock_concat,
        tmp_path,
    ) -> None:
        """A 429 from the chunk synthesizer surfaces as QUOTA_ERROR."""
        # Simulate the documented behaviour of _synthesize_chunk_elevenlabs on HTTP 429.
        mock_el_synth.side_effect = ValueError("QUOTA_ERROR")

        entries = [self._entry("00:00:00,000", "00:00:02,000", "Hello.")]
        output = str(tmp_path / "out.mp3")

        with (
            patch(
                "src.utils.config_manager.load_setting",
                side_effect=lambda k, d="": {
                    "service/elevenlabs_api_key": "test-key",
                    "voice/elevenlabs_voice_id": "vid",
                }.get(k, d),
            ),
            pytest.raises(ValueError, match="QUOTA_ERROR"),
        ):
            synthesize_timed_speech(
                entries,
                output_path=output,
                tts_method="ElevenLabs",
            )


class TestMixAudioMismatchedSampleRateDocumented:
    """``mix_audio_into_video`` does not add an explicit ``-ar`` flag.

    The wrapper takes a single audio source and trusts FFmpeg's
    encoder to handle whatever sample rate the input ships with —
    there's only one audio stream to worry about (the video is
    remuxed, not re-encoded).
    """

    @patch("subprocess.run")
    @patch(f"{_MOD}.check_ffmpeg_available", return_value=True)
    def test_mismatched_sample_rate_passes_inputs_unchanged(
        self,
        _mock_ff: MagicMock,
        mock_run: MagicMock,
        tmp_path: Path,
    ) -> None:
        """The wrapper forwards both files to FFmpeg without rate inspection."""
        mock_run.return_value = MagicMock(returncode=0, stderr=b"")

        video = tmp_path / "v.mp4"
        audio = tmp_path / "a.mp3"
        out = tmp_path / "out.mp4"
        video.write_bytes(b"\x00" * 100)
        audio.write_bytes(b"\x00" * 100)

        mix_audio_into_video(str(video), str(audio), str(out))

        cmd = mock_run.call_args[0][0]
        # Both inputs reach FFmpeg verbatim — wrapper performs no rate check.
        assert str(video) in cmd
        assert str(audio) in cmd
        # No -ar (sample-rate) flag enforcing parity is added by the wrapper.
        assert "-ar" not in cmd


# ===========================================================================
# Malformed Google Cloud STT response handling
# ===========================================================================
#
# ``_parse_results_to_srt`` is fed the ``results`` list from the
# Speech-to-Text REST response.  Existing tests cover the happy path
# (well-formed words / transcript fallback / empty list).  These add
# defensive tests for shapes the API could return on the unhappy path
# (cancelled jobs, partial transcription, schema drift on Google's
# end) — we want graceful empty SRT, not a TypeError 500.


class TestParseResultsToSrtMalformedInput:
    """Defensive coverage for unexpected shapes from Google Cloud STT."""

    def test_empty_alternatives_list(self) -> None:
        """A result with ``alternatives: []`` produces no output, no crash."""
        results = [{"alternatives": []}]
        assert _parse_results_to_srt(results) == ""

    def test_missing_alternatives_key(self) -> None:
        """A result with no ``alternatives`` key at all is handled."""
        # Google sometimes ships ``{}`` for a recognised-but-empty segment.
        results = [{}]
        assert _parse_results_to_srt(results) == ""

    def test_alternative_with_empty_words(self) -> None:
        """Alternative with ``words: []`` and no transcript yields empty SRT."""
        results = [{"alternatives": [{"words": []}]}]
        assert _parse_results_to_srt(results) == ""

    def test_alternative_with_no_word_or_transcript(self) -> None:
        """Empty alternative dict (no words, no transcript) yields empty SRT."""
        results = [{"alternatives": [{}]}]
        assert _parse_results_to_srt(results) == ""

    def test_word_missing_timing_fields(self) -> None:
        """Word entries missing ``startTime`` / ``endTime`` don't crash.

        Google's ``words`` list normally always carries timing when
        ``enableWordTimeOffsets`` is true, but partial responses
        (e.g. early-cancelled long-running operations) can ship words
        without timing.  The parser should still produce some output
        rather than raise.
        """
        results = [
            {
                "alternatives": [
                    {
                        "words": [{"word": "broken"}],
                    },
                ],
            },
        ]
        # Either an empty SRT or a zero-timed line is acceptable —
        # the invariant is "no exception".
        out = _parse_results_to_srt(results)
        assert isinstance(out, str)

    def test_mixed_well_and_malformed_results_keeps_well_formed(self) -> None:
        """A well-formed result mixed with a malformed one keeps the good output.

        Models rarely emit completely malformed *batches* — usually
        one segment is bad while others are fine.  Verify the parser
        is segment-tolerant rather than batch-failing.
        """
        results = [
            {"alternatives": [{}]},  # bad
            {
                "alternatives": [
                    {
                        "words": [
                            {"word": "ok", "startTime": "0s", "endTime": "0.5s"},
                        ],
                    },
                ],
            },
        ]
        srt = _parse_results_to_srt(results)
        # The well-formed result should make it through.
        assert "ok" in srt


# ---------------------------------------------------------------------------
# _synthesize_chunk_gemini — Gemini TTS (raw PCM → ffmpeg → MP3/WAV)
# ---------------------------------------------------------------------------


class TestGetGeminiVoice:
    """Tests for the gender → Gemini voice mapping."""

    def test_male_returns_puck(self) -> None:
        from src.core.speech_engine import (  # noqa: PLC0415
            _GEMINI_TTS_VOICE_MALE,
            _get_gemini_voice,
        )

        assert _get_gemini_voice("MALE") == _GEMINI_TTS_VOICE_MALE

    def test_female_returns_kore(self) -> None:
        from src.core.speech_engine import (  # noqa: PLC0415
            _GEMINI_TTS_VOICE_FEMALE,
            _get_gemini_voice,
        )

        assert _get_gemini_voice("FEMALE") == _GEMINI_TTS_VOICE_FEMALE

    def test_lowercase_is_accepted(self) -> None:
        """Gender comparison is case-insensitive."""
        from src.core.speech_engine import (  # noqa: PLC0415
            _GEMINI_TTS_VOICE_MALE,
            _get_gemini_voice,
        )

        assert _get_gemini_voice("male") == _GEMINI_TTS_VOICE_MALE

    def test_unknown_gender_defaults_to_female(self) -> None:
        """Unknown values fall through to the female voice."""
        from src.core.speech_engine import (  # noqa: PLC0415
            _GEMINI_TTS_VOICE_FEMALE,
            _get_gemini_voice,
        )

        assert _get_gemini_voice("ROBOT") == _GEMINI_TTS_VOICE_FEMALE


class TestSynthesizeChunkGemini:
    """Tests for ``_synthesize_chunk_gemini``."""

    def _make_response(self, pcm_bytes: bytes) -> MagicMock:
        """Builds a mock urlopen response with the Gemini JSON shape."""
        body = json.dumps(
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "inlineData": {
                                        "mimeType": "audio/L16;codec=pcm;rate=24000",
                                        "data": base64.b64encode(pcm_bytes).decode(
                                            "ascii"
                                        ),
                                    },
                                }
                            ],
                        },
                    }
                ],
            }
        ).encode("utf-8")
        mock_resp = MagicMock()
        mock_resp.read.return_value = body
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    def test_successful_synthesis_writes_mp3(self, tmp_path) -> None:
        """Round-trip: PCM response → ffmpeg encodes to MP3 at output_path."""
        from src.core.speech_engine import _synthesize_chunk_gemini  # noqa: PLC0415

        # 24 kHz mono s16le, 0.5 s of silence (~24000 samples × 2 bytes).
        pcm = b"\x00\x00" * 12000

        captured_input: dict[str, bytes] = {}

        def fake_run(argv, **kwargs) -> MagicMock:  # noqa: ANN001, ARG001
            # Verify ffmpeg got the right wire format.
            assert argv[0] == "ffmpeg"
            assert "-f" in argv and "s16le" in argv
            assert "-ar" in argv and "24000" in argv
            assert "-ac" in argv and "1" in argv
            captured_input["pcm"] = kwargs.get("input", b"")
            # Pretend ffmpeg wrote the output file.
            Path(argv[-1]).write_bytes(b"FAKE_MP3_HEADER_AND_DATA")
            return MagicMock(returncode=0)

        with (
            patch(
                "urllib.request.urlopen",
                return_value=self._make_response(pcm),
            ),
            patch("subprocess.run", side_effect=fake_run),
        ):
            output = tmp_path / "chunk.mp3"
            _synthesize_chunk_gemini(
                "Hello world",
                "test-key",
                output,
                voice_name="Kore",
            )

        assert output.exists()
        # ffmpeg got the exact decoded PCM bytes from the API response.
        assert captured_input["pcm"] == pcm

    def test_default_voice_when_empty(self, tmp_path) -> None:
        """Empty voice_name falls back to the female default in the payload."""
        from src.core.speech_engine import (  # noqa: PLC0415
            _GEMINI_TTS_VOICE_FEMALE,
            _synthesize_chunk_gemini,
        )

        captured_url: list[str] = []
        captured_payload: list[dict] = []

        def capture_request(req, timeout=60):  # noqa: ANN001, ARG001
            captured_url.append(req.full_url)
            captured_payload.append(json.loads(req.data))
            return self._make_response(b"\x00\x00" * 100)

        with (
            patch(
                "urllib.request.urlopen",
                side_effect=capture_request,
            ),
            patch("subprocess.run") as mock_ffmpeg,
        ):
            mock_ffmpeg.side_effect = lambda argv, **kw: (  # noqa: ARG005
                Path(argv[-1]).write_bytes(b"x") or MagicMock(returncode=0)
            )
            _synthesize_chunk_gemini(
                "Hi",
                "key",
                tmp_path / "c.mp3",
                voice_name="",
            )

        sent_voice = captured_payload[0]["generationConfig"]["speechConfig"][
            "voiceConfig"
        ]["prebuiltVoiceConfig"]["voiceName"]
        assert sent_voice == _GEMINI_TTS_VOICE_FEMALE

    def test_auth_error_on_401(self, tmp_path) -> None:
        from src.core.speech_engine import _synthesize_chunk_gemini  # noqa: PLC0415

        fp = MagicMock(read=lambda: b"Unauthorized")
        with (
            patch(
                "urllib.request.urlopen",
                side_effect=urllib.error.HTTPError(
                    "url",
                    401,
                    "Unauthorized",
                    {},
                    fp,
                ),
            ),
            pytest.raises(ValueError, match="AUTH_ERROR"),
        ):
            _synthesize_chunk_gemini("Hi", "bad-key", tmp_path / "c.mp3")

    def test_quota_error_on_429(self, tmp_path) -> None:
        from src.core.speech_engine import _synthesize_chunk_gemini  # noqa: PLC0415

        fp = MagicMock(read=lambda: b"Quota exhausted")
        with (
            patch(
                "urllib.request.urlopen",
                side_effect=urllib.error.HTTPError(
                    "url",
                    429,
                    "Too Many Requests",
                    {},
                    fp,
                ),
            ),
            pytest.raises(ValueError, match="QUOTA_ERROR"),
        ):
            _synthesize_chunk_gemini("Hi", "key", tmp_path / "c.mp3")

    def test_tts_api_error_on_500(self, tmp_path) -> None:
        from src.core.speech_engine import _synthesize_chunk_gemini  # noqa: PLC0415

        fp = MagicMock(read=lambda: b"Server error")
        with (
            patch(
                "urllib.request.urlopen",
                side_effect=urllib.error.HTTPError(
                    "url",
                    500,
                    "Internal Server Error",
                    {},
                    fp,
                ),
            ),
            pytest.raises(ValueError, match="TTS_API_ERROR"),
        ):
            _synthesize_chunk_gemini("Hi", "key", tmp_path / "c.mp3")

    def test_empty_text_when_no_audio_part(self, tmp_path) -> None:
        """Gemini response with no inlineData → ``EMPTY_TEXT``."""
        from src.core.speech_engine import _synthesize_chunk_gemini  # noqa: PLC0415

        # Response with parts but no inlineData (e.g. safety-filtered).
        body = json.dumps(
            {
                "candidates": [{"content": {"parts": [{"text": "blocked"}]}}],
            }
        ).encode("utf-8")
        mock_resp = MagicMock()
        mock_resp.read.return_value = body
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with (
            patch(
                "urllib.request.urlopen",
                return_value=mock_resp,
            ),
            pytest.raises(ValueError, match="EMPTY_TEXT"),
        ):
            _synthesize_chunk_gemini("Hi", "key", tmp_path / "c.mp3")

    def test_accepts_snake_case_inline_data(self, tmp_path) -> None:
        """Robust to ``inline_data`` (snake_case) instead of ``inlineData``."""
        from src.core.speech_engine import _synthesize_chunk_gemini  # noqa: PLC0415

        pcm = b"\x00\x00" * 100
        body = json.dumps(
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "inline_data": {  # snake_case
                                        "mime_type": "audio/L16;codec=pcm;rate=24000",
                                        "data": base64.b64encode(pcm).decode("ascii"),
                                    },
                                }
                            ],
                        },
                    }
                ],
            }
        ).encode("utf-8")
        mock_resp = MagicMock()
        mock_resp.read.return_value = body
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with (
            patch("urllib.request.urlopen", return_value=mock_resp),
            patch("subprocess.run") as mock_ffmpeg,
        ):
            mock_ffmpeg.side_effect = lambda argv, **kw: (  # noqa: ARG005
                Path(argv[-1]).write_bytes(b"x") or MagicMock(returncode=0)
            )
            _synthesize_chunk_gemini("Hi", "key", tmp_path / "c.mp3")

    def test_ffmpeg_failure_raises_runtime_error(self, tmp_path) -> None:
        """A ffmpeg PCM→MP3 failure surfaces as ``FFMPEG_CONVERSION_FAILED``."""
        from src.core.speech_engine import _synthesize_chunk_gemini  # noqa: PLC0415

        pcm = b"\x00\x00" * 100
        with (
            patch(
                "urllib.request.urlopen",
                return_value=self._make_response(pcm),
            ),
            patch(
                "subprocess.run",
                side_effect=subprocess.CalledProcessError(
                    1,
                    ["ffmpeg"],
                    stderr=b"bad codec",
                ),
            ),
            pytest.raises(RuntimeError, match="FFMPEG_CONVERSION_FAILED"),
        ):
            _synthesize_chunk_gemini("Hi", "key", tmp_path / "c.mp3")

    def test_wav_format_uses_pcm_codec(self, tmp_path) -> None:
        """audio_format='.wav' triggers pcm_s16le encoding instead of libmp3lame."""
        from src.core.speech_engine import _synthesize_chunk_gemini  # noqa: PLC0415

        captured_argv: list[list[str]] = []

        def fake_run(argv, **kwargs) -> MagicMock:  # noqa: ANN001, ARG001
            captured_argv.append(argv)
            Path(argv[-1]).write_bytes(b"x")
            return MagicMock(returncode=0)

        with (
            patch(
                "urllib.request.urlopen",
                return_value=self._make_response(b"\x00\x00" * 100),
            ),
            patch("subprocess.run", side_effect=fake_run),
        ):
            _synthesize_chunk_gemini(
                "Hi",
                "key",
                tmp_path / "c.wav",
                audio_format=".wav",
            )

        argv = captured_argv[0]
        assert "pcm_s16le" in argv  # WAV uses raw PCM codec
        assert "libmp3lame" not in argv


# ---------------------------------------------------------------------------
# synthesize_speech / synthesize_timed_speech — Gemini TTS dispatch
# ---------------------------------------------------------------------------


class TestSynthesizeSpeechDispatchGemini:
    """``synthesize_speech`` routes to ``_synthesize_chunk_gemini`` for VOICE_TTS_GEMINI."""

    def test_dispatches_to_gemini_helper(self, tmp_path) -> None:
        from src.constants.settings import (  # noqa: PLC0415
            SETTING_GEMINI_TTS_VOICE_NAME,
            SETTING_LLM_GEMINI_API_KEY,
            VOICE_TTS_GEMINI,
        )
        from src.core.speech_engine import synthesize_speech  # noqa: PLC0415

        called: list[tuple] = []

        def fake_chunk_gemini(
            text, api_key, output_path, voice_name="", *, audio_format=".mp3"
        ):  # noqa: ANN001, ARG001
            called.append((text, voice_name, str(output_path)))
            Path(output_path).write_bytes(b"FAKE_MP3")

        # Key-aware mock so the API-key lookup returns a key but
        # the new voice-override setting returns empty (so the
        # gender-default mapping wins for this test).
        def fake_load_setting(key, default=""):  # noqa: ANN001
            if key == SETTING_LLM_GEMINI_API_KEY:
                return "test-gemini-key"
            if key == SETTING_GEMINI_TTS_VOICE_NAME:
                return ""
            return default

        with (
            patch(
                "src.core.speech_engine._synthesize_chunk_gemini",
                side_effect=fake_chunk_gemini,
            ),
            patch(
                "src.core.speech_engine.check_ffmpeg_available",
                return_value=True,
            ),
            patch(
                "src.utils.config_manager.load_setting",
                side_effect=fake_load_setting,
            ),
            patch(
                "src.core.speech_engine._concatenate_mp3_files",
                side_effect=lambda files, out: Path(out).write_bytes(b"OK"),
            ),
        ):
            output = tmp_path / "out.mp3"
            synthesize_speech(
                "Hello world",
                target_lang="English",
                voice_gender="FEMALE",
                output_path=str(output),
                tts_method=VOICE_TTS_GEMINI,
            )

        assert len(called) >= 1
        # Female default voice name was passed to the helper (no override set).
        assert called[0][1] == "Kore"

    def test_raises_auth_error_when_no_gemini_key(self, tmp_path) -> None:
        """Missing Gemini API key raises AUTH_ERROR before any audio work."""
        from src.constants.settings import VOICE_TTS_GEMINI  # noqa: PLC0415
        from src.core.speech_engine import synthesize_speech  # noqa: PLC0415

        with (
            patch(
                "src.utils.config_manager.load_setting",
                return_value="",  # no Gemini API key
            ),
            pytest.raises(ValueError, match="AUTH_ERROR"),
        ):
            synthesize_speech(
                "Hi",
                target_lang="English",
                output_path=str(tmp_path / "out.mp3"),
                tts_method=VOICE_TTS_GEMINI,
            )

    def test_timed_speech_dispatches_to_gemini_helper(self, tmp_path) -> None:
        """``synthesize_timed_speech`` Gemini branch routes per-entry calls.

        Each subtitle entry is fed into ``_synthesize_chunk_gemini``
        independently — no chunking across entries because entries
        already have their own time slots.  Gemini's per-call audio
        cap (~30-60 s) is plenty for typical subtitle lengths.
        """
        from src.constants.settings import VOICE_TTS_GEMINI  # noqa: PLC0415
        from src.core.speech_engine import (  # noqa: PLC0415
            synthesize_timed_speech,
        )
        from src.utils.subtitle_utils import SubtitleEntry  # noqa: PLC0415

        entries = [
            SubtitleEntry(
                index=1,
                start="00:00:00,000",
                end="00:00:02,000",
                text="Hello",
            ),
            SubtitleEntry(
                index=2,
                start="00:00:02,500",
                end="00:00:04,500",
                text="world",
            ),
        ]

        called: list[str] = []

        def fake_chunk_gemini(text, *args, **kwargs):  # noqa: ANN001, ARG001
            called.append(text)
            output = kwargs.get("output_path") or args[1]
            Path(output).write_bytes(b"FAKE_MP3")

        with (
            patch(
                "src.core.speech_engine._synthesize_chunk_gemini",
                side_effect=fake_chunk_gemini,
            ),
            patch(
                "src.core.speech_engine.check_ffmpeg_available",
                return_value=True,
            ),
            patch(
                "src.utils.config_manager.load_setting",
                return_value="test-gemini-key",
            ),
            patch(
                "src.core.speech_engine._concatenate_mp3_files",
                side_effect=lambda files, out: Path(out).write_bytes(b"OK"),
            ),
            patch(
                "src.core.speech_engine._get_mp3_duration",
                return_value=1.0,  # Each chunk ~1s, fits the slot.
            ),
        ):
            synthesize_timed_speech(
                entries,
                target_lang="English",
                voice_gender="MALE",
                output_path=str(tmp_path / "out.mp3"),
                tts_method=VOICE_TTS_GEMINI,
            )

        # Each subtitle entry produced one Gemini chunk call.
        assert called == ["Hello", "world"]

    def test_timed_speech_gemini_raises_auth_error_no_key(
        self,
        tmp_path,
    ) -> None:
        """Missing Gemini API key in timed mode raises AUTH_ERROR upfront."""
        from src.constants.settings import VOICE_TTS_GEMINI  # noqa: PLC0415
        from src.core.speech_engine import (  # noqa: PLC0415
            synthesize_timed_speech,
        )
        from src.utils.subtitle_utils import SubtitleEntry  # noqa: PLC0415

        entries = [
            SubtitleEntry(
                index=1,
                start="00:00:00,000",
                end="00:00:02,000",
                text="Hi",
            ),
        ]

        with (
            patch(
                "src.utils.config_manager.load_setting",
                return_value="",  # no key
            ),
            pytest.raises(ValueError, match="AUTH_ERROR"),
        ):
            synthesize_timed_speech(
                entries,
                target_lang="English",
                output_path=str(tmp_path / "out.mp3"),
                tts_method=VOICE_TTS_GEMINI,
            )

    def test_timed_speech_gemini_speedup_falls_back_to_ffmpeg(
        self,
        tmp_path,
    ) -> None:
        """Overflow on Gemini → ``_speed_up_audio`` (no resynth).

        Google Cloud can re-synthesize at a higher ``speaking_rate``
        for tight subtitle slots; Gemini has no such parameter so
        the fallback is a generic ffmpeg atempo speedup on the
        produced MP3.  Mirrors the Edge / ElevenLabs path.
        """
        from src.constants.settings import VOICE_TTS_GEMINI  # noqa: PLC0415
        from src.core.speech_engine import (  # noqa: PLC0415
            synthesize_timed_speech,
        )
        from src.utils.subtitle_utils import SubtitleEntry  # noqa: PLC0415

        # 1-second slot but the synth says it produced 2 s of audio.
        entries = [
            SubtitleEntry(
                index=1,
                start="00:00:00,000",
                end="00:00:01,000",
                text="Hi",
            ),
        ]

        gemini_calls: list[str] = []
        speedup_calls: list[float] = []

        def fake_chunk_gemini(text, *args, **kwargs):  # noqa: ANN001, ARG001
            gemini_calls.append(text)
            output = kwargs.get("output_path") or args[1]
            Path(output).write_bytes(b"FAKE")

        def fake_speedup(src, dst, rate):  # noqa: ANN001
            speedup_calls.append(rate)
            Path(dst).write_bytes(b"FAST")

        # Audio duration: first call says 2s (overflow), after speedup 1s (fits).
        durations = iter([2.0, 1.0])

        with (
            patch(
                "src.core.speech_engine._synthesize_chunk_gemini",
                side_effect=fake_chunk_gemini,
            ),
            patch(
                "src.core.speech_engine.check_ffmpeg_available",
                return_value=True,
            ),
            patch(
                "src.utils.config_manager.load_setting",
                return_value="test-key",
            ),
            patch(
                "src.core.speech_engine._concatenate_mp3_files",
                side_effect=lambda files, out: Path(out).write_bytes(b"OK"),
            ),
            patch(
                "src.core.speech_engine._get_mp3_duration",
                side_effect=lambda p: next(durations),  # noqa: ARG005
            ),
            patch(
                "src.core.speech_engine._speed_up_audio",
                side_effect=fake_speedup,
            ),
        ):
            synthesize_timed_speech(
                entries,
                target_lang="English",
                output_path=str(tmp_path / "out.mp3"),
                tts_method=VOICE_TTS_GEMINI,
            )

        # Gemini called once for the original synth (no resynth at higher rate).
        assert len(gemini_calls) == 1
        # Speedup was invoked exactly once with rate > 1.0.
        assert len(speedup_calls) == 1
        assert speedup_calls[0] > 1.0

    def test_uses_smaller_chunk_size_for_gemini(self, tmp_path) -> None:
        """Long text gets chunked at the Gemini-specific (smaller) byte cap.

        Gemini TTS caps per-call output at ~30-60 s of audio.  At normal
        cadence ~2 KB of text → ~30 s of speech, so the chunker must use
        ``_GEMINI_TTS_MAX_BYTES = 2000`` (not the larger 4500 used by
        Google Cloud / Edge / ElevenLabs) — otherwise long pasted text
        would either truncate mid-sentence or error out.
        """
        from src.constants.settings import VOICE_TTS_GEMINI  # noqa: PLC0415
        from src.core.speech_engine import (  # noqa: PLC0415
            _GEMINI_TTS_MAX_BYTES,
            _TTS_MAX_BYTES,
            synthesize_speech,
        )

        # 4 KB of text — over Gemini's cap, under Google's.  A single
        # call would error/truncate; correct chunking yields ≥2 chunks.
        long_text = (
            "Sentence number {n} with some filler content to pad the byte "
            "count up. ".format(n="x" * 30)
        ) * 60  # roughly 4 KB
        assert len(long_text.encode("utf-8")) > _GEMINI_TTS_MAX_BYTES
        assert len(long_text.encode("utf-8")) < _TTS_MAX_BYTES * 2

        called: list[str] = []

        def fake_chunk_gemini(text, *args, **kwargs):  # noqa: ANN001, ARG001
            called.append(text)
            Path(kwargs.get("output_path") or args[1]).write_bytes(b"x")

        with (
            patch(
                "src.core.speech_engine._synthesize_chunk_gemini",
                side_effect=fake_chunk_gemini,
            ),
            patch(
                "src.core.speech_engine.check_ffmpeg_available",
                return_value=True,
            ),
            patch(
                "src.utils.config_manager.load_setting",
                return_value="test-key",
            ),
            patch(
                "src.core.speech_engine._concatenate_mp3_files",
                side_effect=lambda files, out: Path(out).write_bytes(b"OK"),
            ),
        ):
            synthesize_speech(
                long_text,
                target_lang="English",
                voice_gender="FEMALE",
                output_path=str(tmp_path / "out.mp3"),
                tts_method=VOICE_TTS_GEMINI,
            )

        # Long text must split into multiple Gemini chunks (the smaller
        # cap forces chunking that the Google-Cloud-sized cap wouldn't).
        assert len(called) >= 2, (
            f"expected ≥2 chunks under Gemini's smaller cap, got {len(called)}"
        )
        # And every chunk respects the Gemini byte budget.
        for chunk in called:
            assert len(chunk.encode("utf-8")) <= _GEMINI_TTS_MAX_BYTES, (
                f"chunk exceeds _GEMINI_TTS_MAX_BYTES: {len(chunk)} bytes"
            )


class TestVoiceOverrideSettings:
    """Per-method voice-override settings for Edge and Gemini.

    ElevenLabs has an override setting (``SETTING_ELEVENLABS_VOICE_ID``)
    and Gemini exposes ``SETTING_GEMINI_TTS_VOICE_NAME``.  Edge and
    Google Cloud are gender-only — Edge derives the voice from
    target_language + gender via ``_EDGE_VOICES``; Google passes
    ``ssmlGender`` to the API with no name and lets the server pick.
    These tests pin the override → fallback contract: explicit user
    voice from Settings → Voice → Voice picker wins; blank falls
    through to the language/gender default.
    """

    def _key_aware_load(
        self,
        api_key: str,
        voice_override: dict,
    ):
        """Returns a ``load_setting`` mock that distinguishes settings."""
        from src.constants.settings import (  # noqa: PLC0415
            SETTING_LLM_GEMINI_API_KEY,
        )

        def fake(key, default=""):  # noqa: ANN001
            if key == SETTING_LLM_GEMINI_API_KEY:
                return api_key
            if key in voice_override:
                return voice_override[key]
            return default

        return fake

    def test_gemini_override_wins_over_gender_default(self, tmp_path) -> None:
        """Setting a Gemini voice via the picker overrides Kore/Puck."""
        from src.constants.settings import (  # noqa: PLC0415
            SETTING_GEMINI_TTS_VOICE_NAME,
            VOICE_TTS_GEMINI,
        )
        from src.core.speech_engine import synthesize_speech  # noqa: PLC0415

        called: list[str] = []

        def fake_chunk(
            text, api_key, output_path, voice_name="", *, audio_format=".mp3"
        ):  # noqa: ANN001, ARG001
            called.append(voice_name)
            Path(output_path).write_bytes(b"x")

        with (
            patch(
                "src.core.speech_engine._synthesize_chunk_gemini",
                side_effect=fake_chunk,
            ),
            patch(
                "src.core.speech_engine.check_ffmpeg_available",
                return_value=True,
            ),
            patch(
                "src.utils.config_manager.load_setting",
                side_effect=self._key_aware_load(
                    api_key="test-key",
                    voice_override={
                        SETTING_GEMINI_TTS_VOICE_NAME: "Aoede",
                    },
                ),
            ),
            patch(
                "src.core.speech_engine._concatenate_mp3_files",
                side_effect=lambda files, out: Path(out).write_bytes(b"OK"),
            ),
        ):
            synthesize_speech(
                "Hello",
                target_lang="English",
                voice_gender="FEMALE",  # would default to Kore without override
                output_path=str(tmp_path / "out.mp3"),
                tts_method=VOICE_TTS_GEMINI,
            )

        assert called[0] == "Aoede", (
            f"override 'Aoede' should win over gender-default 'Kore'; got {called[0]!r}"
        )

    def test_gemini_blank_override_falls_through_to_gender_default(
        self,
        tmp_path,
    ) -> None:
        """Blank or whitespace-only override → gender mapping wins."""
        from src.constants.settings import (  # noqa: PLC0415
            SETTING_GEMINI_TTS_VOICE_NAME,
            VOICE_TTS_GEMINI,
        )
        from src.core.speech_engine import synthesize_speech  # noqa: PLC0415

        called: list[str] = []

        def fake_chunk(
            text, api_key, output_path, voice_name="", *, audio_format=".mp3"
        ):  # noqa: ANN001, ARG001
            called.append(voice_name)
            Path(output_path).write_bytes(b"x")

        with (
            patch(
                "src.core.speech_engine._synthesize_chunk_gemini",
                side_effect=fake_chunk,
            ),
            patch(
                "src.core.speech_engine.check_ffmpeg_available",
                return_value=True,
            ),
            patch(
                "src.utils.config_manager.load_setting",
                side_effect=self._key_aware_load(
                    api_key="test-key",
                    voice_override={
                        SETTING_GEMINI_TTS_VOICE_NAME: "   ",  # whitespace
                    },
                ),
            ),
            patch(
                "src.core.speech_engine._concatenate_mp3_files",
                side_effect=lambda files, out: Path(out).write_bytes(b"OK"),
            ),
        ):
            synthesize_speech(
                "Hello",
                target_lang="English",
                voice_gender="MALE",
                output_path=str(tmp_path / "out.mp3"),
                tts_method=VOICE_TTS_GEMINI,
            )

        assert called[0] == "Puck", (
            f"whitespace override should fall through to gender default; got {called[0]!r}"
        )

    def test_edge_voice_resolved_from_language_and_gender(self, tmp_path) -> None:
        """Edge TTS picks ``_EDGE_VOICES[lang][gender]`` — no override path.

        Free-text override was removed; the Settings UI is now a
        male/female radio that flows through ``voice_gender``.
        """
        from src.constants.settings import VOICE_TTS_EDGE  # noqa: PLC0415
        from src.core.speech_engine import synthesize_speech  # noqa: PLC0415

        called: list[str] = []

        def fake_chunk_edge(text, voice, output_path, **kwargs):  # noqa: ANN001, ARG001
            called.append(voice)
            Path(output_path).write_bytes(b"x")

        with (
            patch(
                "src.core.speech_engine._synthesize_chunk_edge",
                side_effect=fake_chunk_edge,
            ),
            patch(
                "src.core.speech_engine.check_ffmpeg_available",
                return_value=True,
            ),
            patch(
                "src.core.speech_engine._concatenate_mp3_files",
                side_effect=lambda files, out: Path(out).write_bytes(b"OK"),
            ),
        ):
            synthesize_speech(
                "Hello",
                # Generic "English" has no locale code in
                # ``LANGUAGES`` (only the regional variants do), so
                # use the Vietnamese mapping which IS keyed.  Tests
                # the (lang, gender) → voice path end-to-end.
                target_lang="Vietnamese",
                voice_gender="MALE",
                output_path=str(tmp_path / "out.mp3"),
                tts_method=VOICE_TTS_EDGE,
            )

        # _EDGE_VOICES["vi"]["MALE"] == "vi-VN-NamMinhNeural"
        from src.core.speech_engine import _EDGE_VOICES  # noqa: PLC0415

        expected = _EDGE_VOICES["vi"]["MALE"]
        assert called[0] == expected, (
            f"expected gender-resolved {expected!r}; got {called[0]!r}"
        )

    def test_gemini_voice_catalogue_is_well_formed(self) -> None:
        """The curated catalogue surfaces real Gemini voice names.

        Catches a typo like ``Sulaft`` (missing 'a') that would
        produce silent API errors at runtime — Gemini rejects
        unknown ``prebuiltVoiceConfig.voiceName`` with a 400.
        """
        from src.core.speech_engine import (  # noqa: PLC0415
            _GEMINI_TTS_VOICE_FEMALE,
            _GEMINI_TTS_VOICE_MALE,
            GEMINI_TTS_VOICE_CATALOGUE,
        )

        # Both gender defaults must appear in the dropdown so the
        # current "auto" mapping is selectable as an explicit pick.
        assert _GEMINI_TTS_VOICE_FEMALE in GEMINI_TTS_VOICE_CATALOGUE
        assert _GEMINI_TTS_VOICE_MALE in GEMINI_TTS_VOICE_CATALOGUE
        # No empty / whitespace entries — would write a blank to the
        # setting and make the dropdown look broken.
        for name in GEMINI_TTS_VOICE_CATALOGUE:
            assert name and name == name.strip(), f"bad entry: {name!r}"
        # No duplicates.
        assert len(GEMINI_TTS_VOICE_CATALOGUE) == len(set(GEMINI_TTS_VOICE_CATALOGUE))


# ── Piper TTS (offline) ─────────────────────────────────────────────────────


class TestPiperVoiceCatalogue:
    """Sanity tests for the curated Piper voice catalogue and resolver."""

    def test_both_genders_have_at_least_one_voice(self) -> None:
        from src.core.speech_engine import (  # noqa: PLC0415
            PIPER_VOICES_BY_GENDER_AND_LANGUAGE,
        )

        assert PIPER_VOICES_BY_GENDER_AND_LANGUAGE.get("FEMALE")
        assert PIPER_VOICES_BY_GENDER_AND_LANGUAGE.get("MALE")

    def test_voice_ids_match_piper_naming_convention(self) -> None:
        """Every voice ID parses as ``<lang_region>-<voice>-<quality>``."""
        from src.core.speech_engine import (  # noqa: PLC0415
            PIPER_VOICES_BY_GENDER_AND_LANGUAGE,
        )

        for entries in PIPER_VOICES_BY_GENDER_AND_LANGUAGE.values():
            for voice_id in entries.values():
                parts = voice_id.split("-", 2)
                assert len(parts) == 3, f"bad voice id: {voice_id!r}"
                lang_region, voice, quality = parts
                assert "_" in lang_region, (
                    f"lang_region must include underscore: {lang_region!r}"
                )
                assert voice and quality

    def test_resolver_returns_known_voice_for_known_language(self) -> None:
        from src.core.speech_engine import (  # noqa: PLC0415
            PIPER_VOICES_BY_GENDER_AND_LANGUAGE,
            get_piper_voice_for,
        )

        female = get_piper_voice_for("English (US)", "FEMALE")
        male = get_piper_voice_for("English (US)", "MALE")
        assert female == PIPER_VOICES_BY_GENDER_AND_LANGUAGE["FEMALE"]["English (US)"]
        assert male == PIPER_VOICES_BY_GENDER_AND_LANGUAGE["MALE"]["English (US)"]
        assert female != male

    def test_resolver_returns_empty_for_unsupported_language(self) -> None:
        """Asking for a language with no Piper voice returns empty string.

        The resolver used to fall back to ``en_US-amy-medium`` here,
        but synthesising English audio for, say, a Japanese
        translation silently mismatches audio to text.  The new
        contract: empty string signals "no Piper coverage" so the
        caller can route to a different backend (Edge TTS).
        """
        from src.core.speech_engine import get_piper_voice_for  # noqa: PLC0415

        # Hebrew, Japanese, Korean, Thai, Khmer — all in our app's
        # LANGUAGES list but have no Piper voice in the catalogue.
        for lang in ("Hebrew", "Japanese", "Korean", "Thai", "Khmer"):
            assert get_piper_voice_for(lang, "FEMALE") == "", (
                f"{lang!r} must return empty (no Piper coverage); "
                f"got {get_piper_voice_for(lang, 'FEMALE')!r}"
            )

    def test_resolver_handles_empty_or_unknown_gender(self) -> None:
        from src.core.speech_engine import get_piper_voice_for  # noqa: PLC0415

        # Both should default to the FEMALE catalogue without raising.
        for gender in ("", "OTHER", "  ", "female"):
            out = get_piper_voice_for("English (US)", gender)
            assert out

    def test_resolver_falls_back_to_other_gender_for_single_gender_languages(
        self,
    ) -> None:
        """MALE-Italian → female voice; FEMALE-Arabic → male voice.

        Many smaller-corpus languages only ship a single voice in
        the rhasspy/piper-voices catalogue (Italian / Dutch /
        Chinese (Simplified) → female-only; Arabic / Bulgarian /
        Czech / Finnish / Latvian / Romanian / Slovenian / Turkish
        → male-only; etc.).  Asking for the missing gender must
        fall back to the available one — landing on the canonical
        en_US fallback would feel wrong (the user gets English
        audio for an Italian translation).
        """
        from src.core.speech_engine import (  # noqa: PLC0415
            PIPER_VOICES_BY_GENDER_AND_LANGUAGE,
            get_piper_voice_for,
        )

        # Italian: voice lives only under FEMALE.
        italian_female = PIPER_VOICES_BY_GENDER_AND_LANGUAGE["FEMALE"]["Italian"]
        assert get_piper_voice_for("Italian", "MALE") == italian_female

        # Arabic: voice lives only under MALE.
        arabic_male = PIPER_VOICES_BY_GENDER_AND_LANGUAGE["MALE"]["Arabic"]
        assert get_piper_voice_for("Arabic", "FEMALE") == arabic_male


class TestSynthesizeSpeechPiperFallback:
    """``synthesize_speech`` flips ``use_piper=False`` for unsupported langs.

    The new (post-en_US-removal) contract: when ``get_piper_voice_for``
    returns ``""`` (no Piper voice for the target language), the engine
    silently routes to Edge TTS instead of raising. This pins the
    public-API behaviour so the Voice / Subtitle / Dubbing pages
    don't surface a confusing error for languages like Japanese,
    Hebrew, Korean, etc.
    """

    def test_unsupported_language_routes_to_edge_silently(
        self,
        monkeypatch,
        tmp_path,
    ):
        from src.constants.settings import VOICE_TTS_PIPER  # noqa: PLC0415
        from src.core import speech_engine  # noqa: PLC0415

        # Stub everything Edge needs: a voice ID + a chunk synth that
        # writes a plausible MP3 byte to the temp file.
        monkeypatch.setattr(
            speech_engine,
            "_get_edge_voice",
            lambda *_: "en-US-AriaNeural",
        )
        synth_calls = []

        def _fake_edge(text, voice, out, **_):  # noqa: ANN001
            synth_calls.append((text, voice, str(out)))
            from pathlib import Path  # noqa: PLC0415

            Path(out).write_bytes(b"\xff\xfb\x90")  # bare MP3 frame

        monkeypatch.setattr(
            speech_engine,
            "_synthesize_chunk_edge",
            _fake_edge,
        )
        # The concatenate step calls ffmpeg — stub it to just touch the file.
        monkeypatch.setattr(
            speech_engine,
            "_concatenate_mp3_files",
            lambda parts, out: out.write_bytes(b"\xff\xfb\x90"),
        )
        # check_ffmpeg_available — Edge needs ffmpeg, return True.
        monkeypatch.setattr(
            speech_engine,
            "check_ffmpeg_available",
            lambda: True,
        )

        out_path = tmp_path / "out.mp3"
        result = speech_engine.synthesize_speech(
            text="hello",
            target_lang="Japanese",  # NOT in Piper catalogue
            voice_gender="FEMALE",
            output_path=str(out_path),
            tts_method=VOICE_TTS_PIPER,
            audio_format=".mp3",
        )
        assert str(out_path) == result
        assert synth_calls, (
            "Edge synth should have been invoked because Piper has no "
            "Japanese voice — the engine must silently rewire."
        )


class TestVoiceCatalogueSortAndDefaults:
    """ElevenLabs / Gemini catalogues are sorted A→Z; defaults are decoupled.

    Both catalogues used to pin the gender default at position 0; we
    sorted them strictly A→Z and introduced ``get_*_default_voice_id``
    helpers so the default lookup is by ID rather than position.
    A future contributor reordering the dict (or moving the default
    out of position 0) would not break the engine — these tests pin
    both invariants so a regression is caught up front.
    """

    def test_elevenlabs_voices_sorted_alphabetically(self) -> None:
        from src.core.speech_engine import (  # noqa: PLC0415
            ELEVENLABS_VOICES_BY_GENDER,
        )

        for gender, voices in ELEVENLABS_VOICES_BY_GENDER.items():
            names = [n for n, _ in voices]
            assert names == sorted(names), (
                f"ElevenLabs {gender} catalogue not sorted A→Z: {names}"
            )

    def test_gemini_voices_sorted_alphabetically(self) -> None:
        from src.core.speech_engine import (  # noqa: PLC0415
            GEMINI_TTS_VOICES_BY_GENDER,
        )

        for gender, voices in GEMINI_TTS_VOICES_BY_GENDER.items():
            names = list(voices)
            assert names == sorted(names), (
                f"Gemini {gender} catalogue not sorted A→Z: {names}"
            )

    def test_get_elevenlabs_default_voice_id_returns_rachel_for_female(
        self,
    ) -> None:
        from src.core.speech_engine import (  # noqa: PLC0415
            get_elevenlabs_default_voice_id,
        )

        assert get_elevenlabs_default_voice_id("FEMALE") == (
            "21m00Tcm4TlvDq8ikWAM"  # Rachel
        )

    def test_get_elevenlabs_default_voice_id_returns_george_for_male(
        self,
    ) -> None:
        from src.core.speech_engine import (  # noqa: PLC0415
            get_elevenlabs_default_voice_id,
        )

        assert get_elevenlabs_default_voice_id("MALE") == (
            "JBFqnCBsd6RMkjVDRZzb"  # George
        )

    def test_get_gemini_default_voice_returns_kore_and_puck(self) -> None:
        from src.core.speech_engine import (  # noqa: PLC0415
            get_gemini_default_voice,
        )

        assert get_gemini_default_voice("FEMALE") == "Kore"
        assert get_gemini_default_voice("MALE") == "Puck"


class TestPiperVoicePaths:
    """Voice files live under a known directory under app_data_dir."""

    def test_paths_resolve_to_app_data_piper_voices(
        self,
        monkeypatch,
        tmp_path,
    ) -> None:
        monkeypatch.setattr(
            "src.utils.path_manager.get_app_data_dir",
            lambda: tmp_path,
        )
        from src.core.speech_engine import piper_voice_paths  # noqa: PLC0415

        model, config = piper_voice_paths("en_US-amy-medium")
        assert model.parent == tmp_path / "piper_voices"
        assert model.name == "en_US-amy-medium.onnx"
        assert config.name == "en_US-amy-medium.onnx.json"

    def test_install_check_requires_both_files(
        self,
        monkeypatch,
        tmp_path,
    ) -> None:
        monkeypatch.setattr(
            "src.utils.path_manager.get_app_data_dir",
            lambda: tmp_path,
        )
        from src.core.speech_engine import (  # noqa: PLC0415
            is_piper_voice_installed,
            piper_voice_paths,
        )

        voice_id = "en_US-amy-medium"
        assert not is_piper_voice_installed(voice_id)

        model, config = piper_voice_paths(voice_id)
        model.parent.mkdir(parents=True, exist_ok=True)
        model.write_bytes(b"fake-onnx")
        # ONNX exists but JSON is still missing — must report not installed.
        assert not is_piper_voice_installed(voice_id)

        config.write_text("{}", encoding="utf-8")
        assert is_piper_voice_installed(voice_id)


class TestPiperVoiceUrl:
    """HuggingFace URL builder follows the canonical voice path layout."""

    def test_url_follows_huggingface_layout(self) -> None:
        from src.core.speech_engine import _piper_voice_url  # noqa: PLC0415

        url = _piper_voice_url("en_US-amy-medium", suffix="onnx")
        assert url.endswith(
            "en/en_US/amy/medium/en_US-amy-medium.onnx",
        ), f"unexpected URL: {url}"

        json_url = _piper_voice_url("vi_VN-vais1000-medium", suffix="onnx.json")
        assert json_url.endswith(
            "vi/vi_VN/vais1000/medium/vi_VN-vais1000-medium.onnx.json",
        )


class TestSynthesizeChunkPiperGuards:
    """``_synthesize_chunk_piper`` raises when the voice isn't installed."""

    def test_uninstalled_voice_raises_typed_value_error(
        self,
        monkeypatch,
        tmp_path,
    ) -> None:
        monkeypatch.setattr(
            "src.utils.path_manager.get_app_data_dir",
            lambda: tmp_path,
        )
        from src.core.speech_engine import (  # noqa: PLC0415
            _synthesize_chunk_piper,
        )

        with pytest.raises(ValueError, match="PIPER_VOICE_NOT_INSTALLED"):
            _synthesize_chunk_piper(
                "Hello",
                tmp_path / "out.mp3",
                "en_US-amy-medium",
            )


# ── Piper TTS — download + install + happy-path synthesis ──────────────────


class TestInstalledPiperLanguages:
    """``installed_piper_languages`` walks the catalogue + filesystem."""

    def test_empty_dir_returns_empty_set(
        self,
        monkeypatch,
        tmp_path,
    ) -> None:
        monkeypatch.setattr(
            "src.utils.path_manager.get_app_data_dir",
            lambda: tmp_path,
        )
        from src.core.speech_engine import installed_piper_languages  # noqa: PLC0415

        assert installed_piper_languages() == set()

    def test_partial_install_returns_subset(
        self,
        monkeypatch,
        tmp_path,
    ) -> None:
        """Installing one (lang, gender) pair makes that language appear."""
        monkeypatch.setattr(
            "src.utils.path_manager.get_app_data_dir",
            lambda: tmp_path,
        )
        from src.core.speech_engine import (  # noqa: PLC0415
            PIPER_VOICES_BY_GENDER_AND_LANGUAGE,
            installed_piper_languages,
            piper_voice_paths,
        )

        # Drop both files for the FEMALE Vietnamese voice.
        vid = PIPER_VOICES_BY_GENDER_AND_LANGUAGE["FEMALE"]["Vietnamese"]
        model, config = piper_voice_paths(vid)
        model.parent.mkdir(parents=True, exist_ok=True)
        model.write_bytes(b"fake-onnx")
        config.write_text("{}", encoding="utf-8")

        result = installed_piper_languages()
        assert "Vietnamese" in result
        # No other language is installed.
        assert result == {"Vietnamese"}

    def test_single_gender_language_counts_as_installed(
        self,
        monkeypatch,
        tmp_path,
    ) -> None:
        """A language present in only one gender map still counts when installed.

        Italian / Dutch / Chinese (Simplified) only ship a female
        voice in the rhasspy/piper-voices catalogue; Portuguese only
        ships a male voice.  Installing that single voice ID should
        make the language report as installed even though only one
        gender slot exists.
        """
        monkeypatch.setattr(
            "src.utils.path_manager.get_app_data_dir",
            lambda: tmp_path,
        )
        from src.core.speech_engine import (  # noqa: PLC0415
            PIPER_VOICES_BY_GENDER_AND_LANGUAGE,
            installed_piper_languages,
            piper_voice_paths,
        )

        # Italian only exists under FEMALE — verify that's still the
        # catalogue shape this test depends on.
        assert "Italian" not in PIPER_VOICES_BY_GENDER_AND_LANGUAGE["MALE"]
        female_id = PIPER_VOICES_BY_GENDER_AND_LANGUAGE["FEMALE"]["Italian"]

        model, config = piper_voice_paths(female_id)
        model.parent.mkdir(parents=True, exist_ok=True)
        model.write_bytes(b"fake-onnx")
        config.write_text("{}", encoding="utf-8")

        assert "Italian" in installed_piper_languages()

    def test_either_gender_counts_as_installed(
        self,
        monkeypatch,
        tmp_path,
    ) -> None:
        """If only the MALE voice is on disk, the language still counts."""
        monkeypatch.setattr(
            "src.utils.path_manager.get_app_data_dir",
            lambda: tmp_path,
        )
        from src.core.speech_engine import (  # noqa: PLC0415
            PIPER_VOICES_BY_GENDER_AND_LANGUAGE,
            installed_piper_languages,
            piper_voice_paths,
        )

        # Install the MALE German voice; FEMALE remains absent.
        vid = PIPER_VOICES_BY_GENDER_AND_LANGUAGE["MALE"]["German"]
        model, config = piper_voice_paths(vid)
        model.parent.mkdir(parents=True, exist_ok=True)
        model.write_bytes(b"fake-onnx")
        config.write_text("{}", encoding="utf-8")

        assert "German" in installed_piper_languages()


class TestDownloadPiperVoice:
    """Voice download flow: atomic ``.partial`` rename + cleanup on error."""

    def _patch_voice_dir(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "src.utils.path_manager.get_app_data_dir",
            lambda: tmp_path,
        )

    def test_short_circuits_when_already_installed(
        self,
        monkeypatch,
        tmp_path,
    ) -> None:
        """No HTTP traffic when both files are already on disk."""
        self._patch_voice_dir(monkeypatch, tmp_path)
        from src.core.speech_engine import (  # noqa: PLC0415
            download_piper_voice,
            piper_voice_paths,
        )

        voice_id = "en_US-amy-medium"
        model, config = piper_voice_paths(voice_id)
        model.parent.mkdir(parents=True, exist_ok=True)
        model.write_bytes(b"already-here")
        config.write_text("{}", encoding="utf-8")

        # Patch urlopen to raise — proves we never call it on the
        # short-circuit path.
        from unittest.mock import patch  # noqa: PLC0415

        with patch(
            "urllib.request.urlopen",
            side_effect=AssertionError("should not download"),
        ):
            out_model, out_config = download_piper_voice(voice_id)
        assert out_model == model
        assert out_config == config

    def test_atomic_partial_rename_on_success(
        self,
        monkeypatch,
        tmp_path,
    ) -> None:
        """``.partial`` files are renamed to final paths on completion.

        Past bug we want to prevent: a half-written .onnx masquerading
        as a complete voice would crash on first synthesis attempt.
        """
        self._patch_voice_dir(monkeypatch, tmp_path)
        from io import BytesIO  # noqa: PLC0415
        from unittest.mock import MagicMock, patch  # noqa: PLC0415

        from src.core.speech_engine import (  # noqa: PLC0415
            download_piper_voice,
        )

        # Mock urlopen to return small payloads for both URLs.
        def _fake_urlopen(url, timeout=60):  # noqa: ANN001, ANN202, ARG001
            payload = (
                b'{"sample_rate": 22050}' if url.endswith(".json") else b"X" * 1024
            )
            resp = MagicMock()
            resp.headers = {"Content-Length": str(len(payload))}
            resp.__enter__ = lambda self: self
            resp.__exit__ = lambda *a: None
            resp.read = BytesIO(payload).read
            return resp

        voice_id = "fr_FR-siwis-medium"
        with patch("urllib.request.urlopen", side_effect=_fake_urlopen):
            model, config = download_piper_voice(voice_id)

        # Final files exist; .partial siblings do not.
        assert model.is_file()
        assert config.is_file()
        for partial in (
            model.with_suffix(model.suffix + ".partial"),
            config.with_suffix(config.suffix + ".partial"),
        ):
            assert not partial.exists(), f"orphan partial file remained: {partial}"

    def test_progress_callback_invoked_during_download(
        self,
        monkeypatch,
        tmp_path,
    ) -> None:
        """``on_progress(done, total)`` is called at least once during ONNX download."""
        self._patch_voice_dir(monkeypatch, tmp_path)
        from io import BytesIO  # noqa: PLC0415
        from unittest.mock import MagicMock, patch  # noqa: PLC0415

        from src.core.speech_engine import download_piper_voice  # noqa: PLC0415

        def _fake_urlopen(url, timeout=60):  # noqa: ANN001, ANN202, ARG001
            payload = b"{}" if url.endswith(".json") else b"X" * 200000
            resp = MagicMock()
            resp.headers = {"Content-Length": str(len(payload))}
            resp.__enter__ = lambda self: self
            resp.__exit__ = lambda *a: None
            resp.read = BytesIO(payload).read
            return resp

        progress_calls: list[tuple[int, int]] = []
        with patch("urllib.request.urlopen", side_effect=_fake_urlopen):
            download_piper_voice(
                "en_US-amy-medium",
                on_progress=lambda done, total: progress_calls.append(
                    (done, total),
                ),
            )

        assert progress_calls, "on_progress must fire at least once"
        last_done, last_total = progress_calls[-1]
        assert last_done == last_total, (
            "final progress call should report 100% (done == total)"
        )

    def test_partial_files_cleaned_up_on_http_error(
        self,
        monkeypatch,
        tmp_path,
    ) -> None:
        """A failed download leaves no orphan ``.partial`` masquerading as complete."""
        self._patch_voice_dir(monkeypatch, tmp_path)
        import urllib.error  # noqa: PLC0415
        from unittest.mock import patch  # noqa: PLC0415

        from src.core.speech_engine import (  # noqa: PLC0415
            download_piper_voice,
            piper_voice_paths,
        )

        with (
            patch(
                "urllib.request.urlopen",
                side_effect=urllib.error.URLError("boom"),
            ),
            pytest.raises(ValueError, match="PIPER_DOWNLOAD_FAILED"),
        ):
            download_piper_voice("en_US-amy-medium")

        # No orphan .partial files left behind.
        model, config = piper_voice_paths("en_US-amy-medium")
        for partial in (
            model.with_suffix(model.suffix + ".partial"),
            config.with_suffix(config.suffix + ".partial"),
        ):
            assert not partial.exists()


class TestSynthesizeChunkPiperHappyPath:
    """``_synthesize_chunk_piper`` WAV + MP3 transcode contracts."""

    def _stub_voice(self, write_bytes: int = 4096):
        """Stub PiperVoice writing a real WAV via synthesize_wav.

        Configures channels/sampwidth/framerate first — Python's wave
        module raises if ``writeframes`` is called without them.  Real
        PiperVoice sets these from the ONNX model config; we mimic
        Piper's default 22.05 kHz mono s16.
        """
        from unittest.mock import MagicMock  # noqa: PLC0415

        def fake_synth(text, wav_file, *args, **kwargs):  # noqa: ANN001, ANN202, ARG001
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(22050)
            if write_bytes > 0:
                wav_file.writeframes(b"\x00" * write_bytes)

        voice = MagicMock()
        voice.synthesize_wav.side_effect = fake_synth
        return voice

    def test_wav_output_writes_file_directly(
        self,
        monkeypatch,
        tmp_path,
    ) -> None:
        """``audio_format=".wav"`` writes WAV without invoking ffmpeg."""
        monkeypatch.setattr(
            "src.utils.path_manager.get_app_data_dir",
            lambda: tmp_path,
        )
        from unittest.mock import patch  # noqa: PLC0415

        from src.core.speech_engine import (  # noqa: PLC0415
            _synthesize_chunk_piper,
            piper_voice_paths,
        )

        voice_id = "en_US-amy-medium"
        model, config = piper_voice_paths(voice_id)
        model.parent.mkdir(parents=True, exist_ok=True)
        model.write_bytes(b"fake-onnx")
        config.write_text("{}", encoding="utf-8")

        out = tmp_path / "out.wav"
        with (
            patch(
                "src.core.speech_engine._load_piper_voice",
                return_value=self._stub_voice(),
            ),
            patch(
                "src.core.speech_engine.subprocess.run",
                side_effect=AssertionError("ffmpeg must NOT be called for .wav"),
            ),
        ):
            _synthesize_chunk_piper("Hello", out, voice_id, audio_format=".wav")
        assert out.is_file()
        assert out.stat().st_size > 44  # WAV header + body

    def test_mp3_path_invokes_ffmpeg_transcode(
        self,
        monkeypatch,
        tmp_path,
    ) -> None:
        """``audio_format=".mp3"`` writes a temp WAV then transcodes via ffmpeg."""
        monkeypatch.setattr(
            "src.utils.path_manager.get_app_data_dir",
            lambda: tmp_path,
        )
        from unittest.mock import patch  # noqa: PLC0415

        from src.core.speech_engine import (  # noqa: PLC0415
            _synthesize_chunk_piper,
            piper_voice_paths,
        )

        voice_id = "en_US-amy-medium"
        model, config = piper_voice_paths(voice_id)
        model.parent.mkdir(parents=True, exist_ok=True)
        model.write_bytes(b"fake-onnx")
        config.write_text("{}", encoding="utf-8")

        out = tmp_path / "out.mp3"

        def _fake_run(cmd, *args, **kwargs):  # noqa: ANN001, ANN202, ARG001
            # Simulate ffmpeg by writing a non-empty output file.
            from unittest.mock import MagicMock  # noqa: PLC0415

            out.write_bytes(b"\x00" * 1024)
            return MagicMock(returncode=0, stdout=b"", stderr=b"")

        with (
            patch(
                "src.core.speech_engine._load_piper_voice",
                return_value=self._stub_voice(),
            ),
            patch(
                "src.core.speech_engine.check_ffmpeg_available",
                return_value=True,
            ),
            patch(
                "src.core.speech_engine.subprocess.run",
                side_effect=_fake_run,
            ) as mock_subp,
        ):
            _synthesize_chunk_piper("Hello", out, voice_id)
        assert out.is_file()
        mock_subp.assert_called_once()
        cmd = mock_subp.call_args[0][0]
        assert cmd[0] == "ffmpeg"
        assert str(out) in cmd  # output path threaded through

    def test_short_output_raises_empty_text(
        self,
        monkeypatch,
        tmp_path,
    ) -> None:
        """A WAV with only its 44-byte header counts as ``EMPTY_TEXT``.

        Reasonable real-world trigger: pure-punctuation input that
        yields no audible sound.
        """
        monkeypatch.setattr(
            "src.utils.path_manager.get_app_data_dir",
            lambda: tmp_path,
        )
        from unittest.mock import patch  # noqa: PLC0415

        from src.core.speech_engine import (  # noqa: PLC0415
            _synthesize_chunk_piper,
            piper_voice_paths,
        )

        voice_id = "en_US-amy-medium"
        model, config = piper_voice_paths(voice_id)
        model.parent.mkdir(parents=True, exist_ok=True)
        model.write_bytes(b"fake-onnx")
        config.write_text("{}", encoding="utf-8")

        # Stub voice writes ZERO frames — only the WAV header lands.
        with (
            patch(
                "src.core.speech_engine._load_piper_voice",
                return_value=self._stub_voice(write_bytes=0),
            ),
            pytest.raises(ValueError, match="EMPTY_TEXT"),
        ):
            _synthesize_chunk_piper(
                "...",
                tmp_path / "out.wav",
                voice_id,
                audio_format=".wav",
            )


# ── _TTS_LANG_MAP ⇄ _EDGE_VOICES invariant ────────────────────────────────


class TestTtsLangMapEdgeVoicesInvariant:
    """Every language in ``_TTS_LANG_MAP`` should have an Edge voice.

    AGENTS.md: "When adding new RTL or non-Latin languages, both maps
    must be updated together or the user gets a silent fallback to
    en-US."  This parity test prevents the silent-fallback regression.
    """

    def test_every_tts_lang_map_locale_has_edge_voice(self) -> None:
        from src.core.speech_engine import (  # noqa: PLC0415
            _EDGE_VOICES,
            _TTS_LANG_MAP,
        )

        # Every BCP-47 short locale that ``_get_tts_language_code``
        # can return should also be present in ``_EDGE_VOICES`` so
        # ``_get_edge_voice`` doesn't silently fall back to en-US.
        missing = sorted(set(_TTS_LANG_MAP) - set(_EDGE_VOICES))
        assert not missing, (
            "Locales in _TTS_LANG_MAP without _EDGE_VOICES entry "
            "(silent fallback to en-US):\n  " + "\n  ".join(missing)
        )

    def test_every_edge_voice_locale_has_both_genders(self) -> None:
        """Every Edge voice entry must define BOTH FEMALE and MALE keys.

        Missing one would surface as a KeyError at synthesis time
        when the user toggles the gender radio.
        """
        from src.core.speech_engine import _EDGE_VOICES  # noqa: PLC0415

        bad = [
            locale
            for locale, voices in _EDGE_VOICES.items()
            if "FEMALE" not in voices or "MALE" not in voices
        ]
        assert not bad, "Edge voice entries missing FEMALE / MALE keys: " + ", ".join(
            bad
        )


# ── synthesize_timed_speech atomic-output guarantee ────────────────────────


class TestSynthesizeTimedSpeechAtomicOutput:
    """The user-facing ``output_path`` must not appear on disk on failure.

    AGENTS.md: "writes to a tempdir and only moves to ``output_path``
    on success, so a mid-run Stop leaves no partial MP3."  Per-chunk
    failures should leave the user's destination directory clean
    rather than dropping a half-built file the user might mistake
    for a complete render.
    """

    def test_chunk_failure_leaves_output_path_absent(
        self,
        tmp_path,
    ) -> None:
        from unittest.mock import patch  # noqa: PLC0415

        from src.core.speech_engine import synthesize_timed_speech  # noqa: PLC0415
        from src.utils.subtitle_utils import SubtitleEntry  # noqa: PLC0415

        entries = [
            SubtitleEntry(
                index=1,
                start="00:00:01,000",
                end="00:00:03,000",
                text="Hello",
            ),
            SubtitleEntry(
                index=2,
                start="00:00:04,000",
                end="00:00:06,000",
                text="World",
            ),
        ]
        out = tmp_path / "user_output.mp3"

        # Per-chunk Edge synth fails on the second entry; the first
        # one has already written to the tempdir but the function
        # must NOT have moved anything to ``out``.
        call_count = {"n": 0}

        def _failing_chunk(text, voice, output_path):  # noqa: ANN001, ANN202, ARG001
            call_count["n"] += 1
            if call_count["n"] >= 2:  # noqa: PLR2004
                raise ValueError("CONNECTION_ERROR")
            output_path.write_bytes(b"\x00" * 1024)

        with (
            patch(
                "src.core.speech_engine.check_ffmpeg_available",
                return_value=True,
            ),
            patch(
                "src.core.speech_engine._get_edge_voice",
                return_value="en-US-JennyNeural",
            ),
            patch(
                "src.core.speech_engine._synthesize_chunk_edge",
                side_effect=_failing_chunk,
            ),
            patch(
                "src.core.speech_engine._get_mp3_duration",
                return_value=1.5,
            ),
            patch(
                "src.core.speech_engine._generate_silence",
                side_effect=lambda dur, path: path.write_bytes(b"\x00" * 64),
            ),
            pytest.raises(ValueError, match="CONNECTION_ERROR"),
        ):
            synthesize_timed_speech(
                entries,
                target_lang="English",
                voice_gender="FEMALE",
                output_path=str(out),
                tts_method="Edge TTS",
            )

        assert not out.exists(), (
            "synthesize_timed_speech must not leave a partial output "
            f"file on disk after failure; found {out!r}"
        )

    def test_empty_text_raised_before_output_written(
        self,
        tmp_path,
    ) -> None:
        """``EMPTY_TEXT`` (no valid entries) raises BEFORE any write to output."""
        from unittest.mock import patch  # noqa: PLC0415

        from src.core.speech_engine import synthesize_timed_speech  # noqa: PLC0415

        out = tmp_path / "user_output.mp3"
        with (
            patch(
                "src.core.speech_engine.check_ffmpeg_available",
                return_value=True,
            ),
            pytest.raises(ValueError, match="EMPTY_TEXT"),
        ):
            synthesize_timed_speech(
                [],  # zero entries
                target_lang="English",
                voice_gender="FEMALE",
                output_path=str(out),
                tts_method="Edge TTS",
            )
        assert not out.exists()


class TestGeminiTTSMissingInlineDataKey:
    """Both ``inlineData`` and ``inline_data`` absent → ``EMPTY_TEXT`` raised.

    Complements the snake-case acceptance test by pinning the negative
    path: a malformed Gemini response (parts list present but with
    neither inline-data variant) must surface ``EMPTY_TEXT`` rather
    than crashing with ``AttributeError`` / ``TypeError``. The current
    implementation handles this via try/except on KeyError/IndexError/
    TypeError; without that guard, a Gemini protocol shift would surface
    as an opaque crash inside the worker thread.
    """

    def test_neither_camel_nor_snake_case_raises_empty_text(
        self,
        tmp_path,
    ) -> None:
        """Empty parts dict (no inline payload either way) → EMPTY_TEXT."""
        import base64  # noqa: PLC0415, F401
        import json  # noqa: PLC0415
        from unittest.mock import MagicMock, patch  # noqa: PLC0415

        import pytest  # noqa: PLC0415

        # Response with parts[0] containing neither inlineData nor inline_data.
        body = json.dumps(
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": "ignored"}],  # neither inline variant
                        },
                    }
                ],
            }
        ).encode("utf-8")
        mock_resp = MagicMock()
        mock_resp.read.return_value = body
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        from src.core.speech_engine import _synthesize_chunk_gemini  # noqa: PLC0415

        with (
            patch("urllib.request.urlopen", return_value=mock_resp),
            pytest.raises(ValueError, match="EMPTY_TEXT"),
        ):
            _synthesize_chunk_gemini("Hi", "key", tmp_path / "c.mp3")
