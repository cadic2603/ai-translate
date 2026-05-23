"""Unit tests for the Soniox real-time speech-to-text engine."""

import asyncio
import json
import queue
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.soniox_engine import (
    _MODEL,
    _RECONNECT_BASE_DELAY,
    _RECONNECT_MAX,
    _WS_URL,
    SonioxTranscriber,
)

_MOD = "src.core.soniox_engine"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_transcriber(**overrides) -> SonioxTranscriber:
    """Creates a SonioxTranscriber with sensible defaults."""
    defaults = {
        "api_key": "test-key-123",
        "on_sentence": MagicMock(),
        "on_status": MagicMock(),
        "on_stopped": MagicMock(),
        "source_lang": "",
        "target_lang": "",
        "enable_diarization": True,
        "translation_terms": None,
    }
    defaults.update(overrides)
    return SonioxTranscriber(**defaults)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    """Tests for module-level constants."""

    def test_ws_url_is_wss(self) -> None:
        """WebSocket URL uses secure wss:// scheme."""
        assert _WS_URL.startswith("wss://")

    def test_model_is_set(self) -> None:
        """Model name is a non-empty string."""
        assert isinstance(_MODEL, str)
        assert len(_MODEL) > 0

    def test_reconnect_max_is_positive(self) -> None:
        """Maximum reconnection attempts is a positive integer."""
        assert _RECONNECT_MAX > 0

    def test_reconnect_base_delay_is_positive(self) -> None:
        """Base reconnection delay is a positive number."""
        assert _RECONNECT_BASE_DELAY > 0


# ---------------------------------------------------------------------------
# SonioxTranscriber.__init__
# ---------------------------------------------------------------------------


class TestSonioxTranscriberInit:
    """Tests for SonioxTranscriber construction and stored parameters."""

    def test_stores_api_key(self) -> None:
        """API key is stored on the instance."""
        t = _make_transcriber(api_key="my-secret-key")
        assert t._api_key == "my-secret-key"

    def test_stores_on_sentence_callback(self) -> None:
        """on_sentence callback is stored."""
        cb = MagicMock()
        t = _make_transcriber(on_sentence=cb)
        assert t._on_sentence is cb

    def test_stores_on_status_callback(self) -> None:
        """on_status callback is stored."""
        cb = MagicMock()
        t = _make_transcriber(on_status=cb)
        assert t._on_status is cb

    def test_stores_on_stopped_callback(self) -> None:
        """on_stopped callback is stored."""
        cb = MagicMock()
        t = _make_transcriber(on_stopped=cb)
        assert t._on_stopped is cb

    def test_on_status_defaults_to_none(self) -> None:
        """on_status is None when not provided."""
        t = SonioxTranscriber(api_key="k", on_sentence=MagicMock())
        assert t._on_status is None

    def test_on_stopped_defaults_to_none(self) -> None:
        """on_stopped is None when not provided."""
        t = SonioxTranscriber(api_key="k", on_sentence=MagicMock())
        assert t._on_stopped is None

    def test_stores_source_lang(self) -> None:
        """Source language is stored."""
        t = _make_transcriber(source_lang="en")
        assert t._source_lang == "en"

    def test_stores_target_lang(self) -> None:
        """Target language is stored."""
        t = _make_transcriber(target_lang="fr")
        assert t._target_lang == "fr"

    def test_source_lang_defaults_to_empty(self) -> None:
        """Source language defaults to empty string."""
        t = SonioxTranscriber(api_key="k", on_sentence=MagicMock())
        assert t._source_lang == ""

    def test_target_lang_defaults_to_empty(self) -> None:
        """Target language defaults to empty string."""
        t = SonioxTranscriber(api_key="k", on_sentence=MagicMock())
        assert t._target_lang == ""

    def test_stores_enable_diarization(self) -> None:
        """Diarization flag is stored."""
        t = _make_transcriber(enable_diarization=False)
        assert t._enable_diarization is False

    def test_enable_diarization_defaults_to_true(self) -> None:
        """Diarization defaults to True."""
        t = SonioxTranscriber(api_key="k", on_sentence=MagicMock())
        assert t._enable_diarization is True

    def test_stores_translation_terms(self) -> None:
        """Translation terms list is stored."""
        terms = [{"source": "hello", "target": "bonjour"}]
        t = _make_transcriber(translation_terms=terms)
        assert t._translation_terms is terms

    def test_translation_terms_defaults_to_none(self) -> None:
        """Translation terms defaults to None."""
        t = SonioxTranscriber(api_key="k", on_sentence=MagicMock())
        assert t._translation_terms is None

    def test_initial_is_running_false(self) -> None:
        """Transcriber starts in stopped state."""
        t = _make_transcriber()
        assert t._is_running is False

    def test_initial_thread_is_none(self) -> None:
        """Background thread is initially None."""
        t = _make_transcriber()
        assert t._thread is None

    def test_initial_audio_queue_empty(self) -> None:
        """Audio queue is initially empty."""
        t = _make_transcriber()
        assert t._audio_queue.empty()


# ---------------------------------------------------------------------------
# is_running property
# ---------------------------------------------------------------------------


class TestIsRunningProperty:
    """Tests for the is_running property."""

    def test_returns_false_by_default(self) -> None:
        """Returns False on a fresh instance."""
        t = _make_transcriber()
        assert t.is_running is False

    def test_reflects_internal_flag_true(self) -> None:
        """Returns True when _is_running is set to True."""
        t = _make_transcriber()
        t._is_running = True
        assert t.is_running is True

    def test_reflects_internal_flag_false(self) -> None:
        """Returns False when _is_running is set back to False."""
        t = _make_transcriber()
        t._is_running = True
        t._is_running = False
        assert t.is_running is False


# ---------------------------------------------------------------------------
# send_audio()
# ---------------------------------------------------------------------------


class TestSendAudio:
    """Tests for send_audio() method."""

    def test_enqueues_when_running(self) -> None:
        """Audio bytes are added to the queue when running."""
        t = _make_transcriber()
        t._is_running = True
        data = b"\x00\x01\x02\x03"
        t.send_audio(data)
        assert not t._audio_queue.empty()
        assert t._audio_queue.get_nowait() == data

    def test_ignores_when_stopped(self) -> None:
        """Audio bytes are silently discarded when not running."""
        t = _make_transcriber()
        t._is_running = False
        t.send_audio(b"\xff\xfe")
        assert t._audio_queue.empty()

    def test_multiple_enqueues(self) -> None:
        """Multiple audio chunks are enqueued in order."""
        t = _make_transcriber()
        t._is_running = True
        t.send_audio(b"chunk1")
        t.send_audio(b"chunk2")
        t.send_audio(b"chunk3")
        assert t._audio_queue.get_nowait() == b"chunk1"
        assert t._audio_queue.get_nowait() == b"chunk2"
        assert t._audio_queue.get_nowait() == b"chunk3"

    def test_ignores_after_stop(self) -> None:
        """Audio sent after stop is discarded."""
        t = _make_transcriber()
        t._is_running = True
        t.send_audio(b"before")
        t._is_running = False
        t.send_audio(b"after")
        assert t._audio_queue.qsize() == 1
        assert t._audio_queue.get_nowait() == b"before"


# ---------------------------------------------------------------------------
# start() / stop() lifecycle
# ---------------------------------------------------------------------------


class TestStartStopLifecycle:
    """Tests for start() and stop() lifecycle management."""

    def test_start_sets_running(self) -> None:
        """start() sets is_running to True and creates a thread."""
        t = _make_transcriber()
        with patch.object(t, "_run_loop"):
            t.start()
            assert t.is_running is True
            assert t._thread is not None
            t._is_running = False
            t._thread.join(timeout=2)

    def test_start_emits_connecting_status(self) -> None:
        """start() emits a 'connecting' status via _emit_status."""
        t = _make_transcriber()
        with patch.object(t, "_run_loop"), patch.object(t, "_emit_status") as mock_emit:
            t.start()
            mock_emit.assert_called_once_with("live.status_connecting")
            t._is_running = False
            t._thread.join(timeout=2)

    def test_start_spawns_daemon_thread(self) -> None:
        """start() creates a daemon thread."""
        t = _make_transcriber()
        with patch.object(t, "_run_loop"):
            t.start()
            assert t._thread.daemon is True
            t._is_running = False
            t._thread.join(timeout=2)

    def test_start_is_idempotent(self) -> None:
        """Calling start() twice does not create a second thread."""
        t = _make_transcriber()
        with patch.object(t, "_run_loop"):
            t.start()
            first_thread = t._thread
            t.start()
            assert t._thread is first_thread
            t._is_running = False
            first_thread.join(timeout=2)

    def test_stop_clears_running_flag(self) -> None:
        """stop() sets is_running to False."""
        t = _make_transcriber()
        t._is_running = True
        t._thread = MagicMock()
        t.stop()
        assert t.is_running is False

    def test_stop_joins_thread(self) -> None:
        """stop() joins the background thread with a timeout."""
        t = _make_transcriber()
        mock_thread = MagicMock()
        t._is_running = True
        t._thread = mock_thread
        t.stop()
        mock_thread.join.assert_called_once_with(timeout=5)

    def test_stop_clears_thread(self) -> None:
        """stop() sets _thread to None."""
        t = _make_transcriber()
        t._is_running = True
        t._thread = MagicMock()
        t.stop()
        assert t._thread is None

    def test_stop_noop_when_already_stopped(self) -> None:
        """stop() is safe when already stopped (no thread to join)."""
        t = _make_transcriber()
        t._is_running = False
        t._thread = None
        t.stop()  # should not raise
        assert t._thread is None
        assert t.is_running is False


# ---------------------------------------------------------------------------
# _build_config()
# ---------------------------------------------------------------------------


class TestBuildConfig:
    """Tests for _build_config() WebSocket configuration builder."""

    def test_minimal_config(self) -> None:
        """Builds correct config with defaults (no source/target/terms)."""
        t = _make_transcriber()
        config = t._build_config()
        assert config["api_key"] == "test-key-123"
        assert config["model"] == _MODEL
        assert config["audio_format"] == "pcm_s16le"
        assert config["sample_rate"] == 16000  # noqa: PLR2004
        assert config["num_channels"] == 1
        assert config["enable_endpoint_detection"] is True
        assert config["max_endpoint_delay_ms"] == 3000  # noqa: PLR2004
        assert config["enable_speaker_diarization"] is True
        assert config["enable_language_identification"] is True

    def test_no_language_hints_without_source_lang(self) -> None:
        """language_hints is absent when source_lang is empty."""
        t = _make_transcriber(source_lang="")
        config = t._build_config()
        assert "language_hints" not in config

    def test_language_hints_with_source_lang(self) -> None:
        """language_hints contains the source language code."""
        t = _make_transcriber(source_lang="en")
        config = t._build_config()
        assert config["language_hints"] == ["en"]

    def test_no_translation_without_target_lang(self) -> None:
        """Translation key is absent when target_lang is empty."""
        t = _make_transcriber(target_lang="")
        config = t._build_config()
        assert "translation" not in config

    def test_translation_with_target_lang(self) -> None:
        """Translation dict is set correctly when target_lang is provided."""
        t = _make_transcriber(target_lang="fr")
        config = t._build_config()
        assert config["translation"] == {
            "type": "one_way",
            "target_language": "fr",
        }

    def test_no_context_without_translation_terms(self) -> None:
        """Context key is absent when translation_terms is None."""
        t = _make_transcriber(translation_terms=None)
        config = t._build_config()
        assert "context" not in config

    def test_no_context_with_empty_translation_terms(self) -> None:
        """Context key is absent when translation_terms is an empty list."""
        t = _make_transcriber(translation_terms=[])
        config = t._build_config()
        assert "context" not in config

    def test_context_with_translation_terms(self) -> None:
        """Context contains translation_terms when provided."""
        terms = [
            {"source": "hello", "target": "bonjour"},
            {"source": "bye", "target": "au revoir"},
        ]
        t = _make_transcriber(translation_terms=terms)
        config = t._build_config()
        assert config["context"] == {"translation_terms": terms}

    def test_diarization_disabled(self) -> None:
        """enable_speaker_diarization is False when diarization is off."""
        t = _make_transcriber(enable_diarization=False)
        config = t._build_config()
        assert config["enable_speaker_diarization"] is False

    def test_diarization_enabled(self) -> None:
        """enable_speaker_diarization is True when diarization is on."""
        t = _make_transcriber(enable_diarization=True)
        config = t._build_config()
        assert config["enable_speaker_diarization"] is True

    def test_full_config(self) -> None:
        """All optional fields are present when fully configured."""
        terms = [{"source": "cat", "target": "gato"}]
        t = _make_transcriber(
            api_key="full-key",
            source_lang="en",
            target_lang="es",
            enable_diarization=True,
            translation_terms=terms,
        )
        config = t._build_config()
        assert config["api_key"] == "full-key"
        assert config["language_hints"] == ["en"]
        assert config["translation"]["target_language"] == "es"
        assert config["context"]["translation_terms"] is terms
        assert config["enable_speaker_diarization"] is True


# ---------------------------------------------------------------------------
# _emit_status()
# ---------------------------------------------------------------------------


class TestEmitStatus:
    """Tests for _emit_status() method."""

    def test_calls_on_status_with_translated_text(self) -> None:
        """_emit_status calls on_status with the result of tr()."""
        on_status = MagicMock()
        t = _make_transcriber(on_status=on_status)
        with patch("src.constants.i18n.tr", return_value="Connecting...") as mock_tr:
            t._emit_status("live.status_connecting")
            mock_tr.assert_called_once_with("live.status_connecting")
            on_status.assert_called_once_with("Connecting...")

    def test_does_nothing_when_on_status_is_none(self) -> None:
        """_emit_status is a no-op when on_status is None."""
        t = SonioxTranscriber(api_key="k", on_sentence=MagicMock())
        assert t._on_status is None
        # Should not raise
        t._emit_status("live.status_connecting")

    def test_multiple_status_emissions(self) -> None:
        """Multiple status calls are forwarded correctly."""
        on_status = MagicMock()
        t = _make_transcriber(on_status=on_status)
        with patch("src.constants.i18n.tr", side_effect=lambda k: f"translated:{k}"):
            t._emit_status("live.status_connecting")
            t._emit_status("live.status_listening")
        assert on_status.call_count == 2  # noqa: PLR2004
        on_status.assert_any_call("translated:live.status_connecting")
        on_status.assert_any_call("translated:live.status_listening")


# ---------------------------------------------------------------------------
# _run_loop() — error handling
# ---------------------------------------------------------------------------


class TestRunLoopErrorHandling:
    """Tests for error handling in _run_loop()."""

    def test_calls_on_error_with_classified_category(self) -> None:
        """on_error is called with a classified category, not raw text.

        The user-facing surface in :class:`LivePage` resolves the
        category through ``display_error_message`` to a localised
        sentence — passing raw exception text would defeat that.
        ``on_status`` is reserved for non-error status updates
        ("Connecting…", "Listening").
        """
        on_status = MagicMock()
        on_stopped = MagicMock()
        on_error = MagicMock()
        t = _make_transcriber(
            on_status=on_status, on_stopped=on_stopped, on_error=on_error,
        )

        with patch.object(
            t,
            "_ws_loop",
            new_callable=AsyncMock,
            side_effect=OSError("DNS failure"),
        ):
            t._run_loop()

        on_error.assert_called_once()
        category, raw = on_error.call_args.args
        # OSError → STT_CONNECTION_LOST per classify_soniox_exception.
        assert category == "STT_CONNECTION_LOST"
        assert "DNS" in raw

    def test_calls_on_stopped_on_error(self) -> None:
        """on_stopped is called after _ws_loop raises."""
        on_stopped = MagicMock()
        t = _make_transcriber(on_stopped=on_stopped)

        with patch.object(
            t,
            "_ws_loop",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ):
            t._run_loop()

        on_stopped.assert_called_once()

    def test_clears_is_running_on_error(self) -> None:
        """_is_running is set to False after an error."""
        t = _make_transcriber()
        t._is_running = True

        with patch.object(
            t,
            "_ws_loop",
            new_callable=AsyncMock,
            side_effect=RuntimeError("fail"),
        ):
            t._run_loop()

        assert t._is_running is False

    def test_calls_on_stopped_on_normal_exit(self) -> None:
        """on_stopped is called after _ws_loop completes normally."""
        on_stopped = MagicMock()
        t = _make_transcriber(on_stopped=on_stopped)

        with patch.object(t, "_ws_loop", new_callable=AsyncMock):
            t._run_loop()

        on_stopped.assert_called_once()

    def test_clears_is_running_on_normal_exit(self) -> None:
        """_is_running is set to False after normal completion."""
        t = _make_transcriber()
        t._is_running = True

        with patch.object(t, "_ws_loop", new_callable=AsyncMock):
            t._run_loop()

        assert t._is_running is False

    def test_on_stopped_exception_is_suppressed(self) -> None:
        """Exception in on_stopped callback is silently suppressed."""
        on_stopped = MagicMock(side_effect=RuntimeError("callback boom"))
        t = _make_transcriber(on_stopped=on_stopped)

        with patch.object(t, "_ws_loop", new_callable=AsyncMock):
            t._run_loop()  # Should not raise

        on_stopped.assert_called_once()

    def test_on_status_exception_during_error_is_suppressed(self) -> None:
        """Exception in on_status during error handling is suppressed."""
        on_status = MagicMock(side_effect=RuntimeError("status boom"))
        on_stopped = MagicMock()
        t = _make_transcriber(on_status=on_status, on_stopped=on_stopped)

        with patch.object(
            t,
            "_ws_loop",
            new_callable=AsyncMock,
            side_effect=ValueError("ws error"),
        ):
            t._run_loop()  # Should not raise

        # on_stopped should still be called despite on_status failure
        on_stopped.assert_called_once()

    def test_run_loop_without_callbacks(self) -> None:
        """_run_loop handles error gracefully with no optional callbacks."""
        t = SonioxTranscriber(api_key="k", on_sentence=MagicMock())
        assert t._on_status is None
        assert t._on_stopped is None
        t._is_running = True

        with patch.object(
            t,
            "_ws_loop",
            new_callable=AsyncMock,
            side_effect=RuntimeError("fail"),
        ):
            t._run_loop()  # Should not raise

        assert t._is_running is False


# ---------------------------------------------------------------------------
# _ws_loop() — WebSocket lifecycle
# ---------------------------------------------------------------------------


class TestWsLoop:
    """Tests for the _ws_loop() async method."""

    def test_sends_config_on_connect(self) -> None:
        """Config JSON is sent immediately after WebSocket connect."""
        t = _make_transcriber(api_key="ws-key")
        t._is_running = False  # Will exit while-loop immediately

        mock_ws = AsyncMock()
        mock_ws.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_ws.__aexit__ = AsyncMock(return_value=False)

        with patch(f"{_MOD}.websockets", create=True) as mock_websockets:
            mock_websockets.connect.return_value = mock_ws
            asyncio.run(t._ws_loop())

        # Loop exits immediately since _is_running is False -- no connect call
        # Verify the loop respects the _is_running guard
        mock_websockets.connect.assert_not_called()

    def test_reconnect_on_transient_error(self) -> None:
        """Transient errors trigger reconnection with backoff."""
        t = _make_transcriber()
        t._is_running = True
        connect_count = 0

        class _FailingConnect:
            """Async context manager that always raises on __aenter__."""

            def __init__(self, *args, **kwargs) -> None:
                nonlocal connect_count
                connect_count += 1

            async def __aenter__(self):
                if connect_count >= _RECONNECT_MAX:
                    raise ConnectionError("persistent failure")
                raise ConnectionError("transient failure")

            async def __aexit__(self, *args):
                pass

        mock_ws_mod = MagicMock()
        mock_ws_mod.connect = _FailingConnect

        with (
            patch.dict("sys.modules", {"websockets": mock_ws_mod}),
            patch("asyncio.sleep", new_callable=AsyncMock),
            pytest.raises(ConnectionError, match="persistent failure"),
        ):
            asyncio.run(t._ws_loop())

        assert connect_count == _RECONNECT_MAX

    def test_successful_connect_sends_config_and_runs_sender_receiver(self) -> None:
        """Successful connect sends config, emits listening status, runs tasks."""
        t = _make_transcriber(api_key="abc")
        t._is_running = True
        sent_messages: list[str] = []

        class _Ws:
            """Fake WebSocket that captures sent messages."""

            async def send(self, msg) -> None:  # noqa: ANN001, ANN202
                sent_messages.append(msg)

        class _Connect:
            """Async context manager returning the fake WebSocket."""

            def __init__(self, *args, **kwargs) -> None:
                pass

            async def __aenter__(self) -> _Ws:
                return _Ws()

            async def __aexit__(self, *args) -> None:
                pass

        mock_ws_mod = MagicMock()
        mock_ws_mod.connect = _Connect

        # Sender/receiver complete immediately and flip _is_running so the
        # outer while-loop exits after one iteration.
        async def _stop_loop(_ws) -> None:  # noqa: ANN001
            t._is_running = False

        with (
            patch.dict("sys.modules", {"websockets": mock_ws_mod}),
            patch.object(t, "_send_audio", side_effect=_stop_loop),
            patch.object(t, "_receive_tokens", side_effect=_stop_loop),
        ):
            asyncio.run(t._ws_loop())

        # The config JSON was the first message sent.
        assert sent_messages, "No messages were sent over the WebSocket"
        parsed = json.loads(sent_messages[0])
        assert parsed.get("api_key") == "abc"
        # Listening status was emitted.
        t._on_status.assert_any_call("live.status_listening")

    def test_cancelled_error_breaks_loop(self) -> None:
        """asyncio.CancelledError inside the loop breaks out cleanly."""
        t = _make_transcriber()
        t._is_running = True

        class _Connect:
            """Raises CancelledError on entry."""

            def __init__(self, *args, **kwargs) -> None:
                pass

            async def __aenter__(self):
                raise asyncio.CancelledError

            async def __aexit__(self, *args) -> None:
                pass

        mock_ws_mod = MagicMock()
        mock_ws_mod.connect = _Connect

        with patch.dict("sys.modules", {"websockets": mock_ws_mod}):
            # Should NOT raise — CancelledError is caught and breaks the loop.
            asyncio.run(t._ws_loop())


# ---------------------------------------------------------------------------
# _send_audio() — keepalive + connection-closed handling
# ---------------------------------------------------------------------------


class TestSendAudio:
    """Tests for the _send_audio() async method."""

    def test_idle_sends_no_application_messages(self) -> None:
        """Regression: idle queue → NO application-level JSON sent.

        Earlier code shipped an undocumented ``{"type": "keepalive"}``
        JSON every 10 s when audio was idle.  The Soniox spec doesn't
        document any keepalive mechanism (the ``websockets`` library
        already handles WebSocket protocol-level PING/PONG), and the
        official reference implementation never sends one.  Pin the
        new contract: an idle period yields ZERO ``ws.send`` calls
        before the loop is asked to stop.  The only ``send`` after
        ``_is_running = False`` should be the graceful-close empty
        bytes (``b""``) — which we verify lands as the LAST and ONLY
        send.
        """
        t = _make_transcriber()
        t._is_running = True
        sent: list = []

        ws = AsyncMock()

        # Track every send so we can assert the entire sequence.
        async def _record(msg) -> None:  # noqa: ANN001, ANN202
            sent.append(msg)

        ws.send = _record

        call_count = 0

        def _stop_after_a_few_idle_iterations(timeout: float) -> None:  # noqa: ARG001
            nonlocal call_count
            call_count += 1
            if call_count >= 5:  # noqa: PLR2004
                t._is_running = False
            raise queue.Empty

        with patch.object(
            t._audio_queue, "get",
            side_effect=_stop_after_a_few_idle_iterations,
        ):
            asyncio.run(t._send_audio(ws))

        # Exactly one send: the graceful-close empty-bytes frame.
        # NO keepalive JSON, no application-level messages during
        # the 5 idle iterations.
        assert sent == [b""], (
            f"Expected only the graceful-close b'' frame, got: {sent}"
        )

    def test_send_audio_breaks_on_generic_exception(self) -> None:
        """A non-Empty exception from the queue breaks out of the loop."""
        t = _make_transcriber()
        t._is_running = True
        ws = AsyncMock()

        with patch.object(
            t._audio_queue,
            "get",
            side_effect=RuntimeError("boom"),
        ):
            # Should not raise — generic exception is caught and breaks.
            asyncio.run(t._send_audio(ws))


# ---------------------------------------------------------------------------
# _receive_tokens() — token processing
# ---------------------------------------------------------------------------


class _FakeWs:
    """Fake WebSocket that yields pre-loaded messages via ``async for``."""

    def __init__(self, messages: list[str]) -> None:
        self._messages = list(messages)
        self._index = 0

    def __aiter__(self):  # noqa: ANN204
        self._index = 0
        return self

    async def __anext__(self) -> str:
        if self._index >= len(self._messages):
            raise StopAsyncIteration
        msg = self._messages[self._index]
        self._index += 1
        return msg


def _make_ws(messages: list[str]) -> _FakeWs:
    """Creates a fake WebSocket that yields *messages* via ``async for``."""
    return _FakeWs(messages)


class TestReceiveTokens:
    """Tests for _receive_tokens() message processing."""

    def test_emits_sentence_on_end_token(self) -> None:
        """A complete sentence is emitted when <end> token arrives."""
        on_sentence = MagicMock()
        t = _make_transcriber(on_sentence=on_sentence)
        t._is_running = True

        messages = [
            json.dumps(
                {
                    "tokens": [
                        {
                            "text": "Hello ",
                            "is_final": True,
                            "translation_status": "original",
                            "speaker": "S1",
                            "start_ms": 1000,
                            "end_ms": 1500,
                        },
                        {
                            "text": "world",
                            "is_final": True,
                            "translation_status": "original",
                            "speaker": "S1",
                            "start_ms": 1500,
                            "end_ms": 2000,
                        },
                        {
                            "text": "Bonjour monde",
                            "is_final": True,
                            "translation_status": "translation",
                        },
                        {"text": "<end>"},
                    ],
                }
            ),
        ]

        ws = _make_ws(messages)
        asyncio.run(t._receive_tokens(ws))

        on_sentence.assert_called_once_with(
            "Hello world",
            1.0,
            2.0,
            "S1",
            "Bonjour monde",
        )

    def test_skips_non_final_tokens(self) -> None:
        """Non-final tokens are not accumulated."""
        on_sentence = MagicMock()
        t = _make_transcriber(on_sentence=on_sentence)
        t._is_running = True

        messages = [
            json.dumps(
                {
                    "tokens": [
                        {
                            "text": "partial",
                            "is_final": False,
                            "translation_status": "original",
                        },
                        {
                            "text": "Final",
                            "is_final": True,
                            "translation_status": "original",
                            "start_ms": 0,
                            "end_ms": 500,
                        },
                        {"text": "<end>"},
                    ],
                }
            ),
        ]

        ws = _make_ws(messages)
        asyncio.run(t._receive_tokens(ws))

        on_sentence.assert_called_once_with("Final", 0.0, 0.5, "", "")

    def test_flushes_remaining_on_disconnect(self) -> None:
        """Remaining accumulated tokens are flushed when messages end."""
        on_sentence = MagicMock()
        t = _make_transcriber(on_sentence=on_sentence)
        t._is_running = True

        messages = [
            json.dumps(
                {
                    "tokens": [
                        {
                            "text": "incomplete",
                            "is_final": True,
                            "translation_status": "original",
                            "start_ms": 100,
                            "end_ms": 200,
                        },
                    ],
                }
            ),
            # No <end> token; messages just stop
        ]

        ws = _make_ws(messages)
        asyncio.run(t._receive_tokens(ws))

        on_sentence.assert_called_once_with("incomplete", 0.1, 0.2, "", "")

    def test_does_not_emit_empty_sentence(self) -> None:
        """Empty original text after stripping is not emitted."""
        on_sentence = MagicMock()
        t = _make_transcriber(on_sentence=on_sentence)
        t._is_running = True

        messages = [
            json.dumps(
                {
                    "tokens": [
                        {
                            "text": "   ",
                            "is_final": True,
                            "translation_status": "original",
                        },
                        {"text": "<end>"},
                    ],
                }
            ),
        ]

        ws = _make_ws(messages)
        asyncio.run(t._receive_tokens(ws))

        on_sentence.assert_not_called()

    def test_error_event_breaks_loop(self) -> None:
        """An ``error_code`` payload classifies + emits via on_error.

        Soniox transmits errors as JSON payload integers, so the
        engine MUST classify the payload (not just blindly toast a
        generic "Soniox error" string) so the user sees an actionable
        message like *"API key is invalid"* instead of a raw 401.
        """
        on_sentence = MagicMock()
        on_error = MagicMock()
        t = _make_transcriber(on_sentence=on_sentence, on_error=on_error)
        t._is_running = True

        messages = [
            json.dumps(
                {
                    "error_code": 401,
                    "error_message": "Invalid API key",
                }
            ),
        ]

        ws = _make_ws(messages)
        asyncio.run(t._receive_tokens(ws))

        on_error.assert_called_once()
        category, raw = on_error.call_args.args
        assert category == "STT_AUTH_INVALID"
        assert "401" in raw
        on_sentence.assert_not_called()
        # ``_payload_error_emitted`` flips so the close that follows
        # doesn't get re-classified by the outer exception handler.
        assert t._payload_error_emitted is True

    def test_finished_event_breaks_loop(self) -> None:
        """A finished event from the server breaks the receive loop."""
        on_sentence = MagicMock()
        t = _make_transcriber(on_sentence=on_sentence)
        t._is_running = True

        messages = [
            json.dumps({"finished": True}),
        ]

        ws = _make_ws(messages)
        asyncio.run(t._receive_tokens(ws))
        on_sentence.assert_not_called()

    def test_multiple_sentences(self) -> None:
        """Multiple sentences are emitted independently."""
        on_sentence = MagicMock()
        t = _make_transcriber(on_sentence=on_sentence)
        t._is_running = True

        messages = [
            json.dumps(
                {
                    "tokens": [
                        {
                            "text": "First",
                            "is_final": True,
                            "translation_status": "original",
                            "start_ms": 0,
                            "end_ms": 1000,
                        },
                        {"text": "<end>"},
                        {
                            "text": "Second",
                            "is_final": True,
                            "translation_status": "original",
                            "start_ms": 2000,
                            "end_ms": 3000,
                        },
                        {"text": "<end>"},
                    ],
                }
            ),
        ]

        ws = _make_ws(messages)
        asyncio.run(t._receive_tokens(ws))

        assert on_sentence.call_count == 2  # noqa: PLR2004
        on_sentence.assert_any_call("First", 0.0, 1.0, "", "")
        on_sentence.assert_any_call("Second", 2.0, 3.0, "", "")

    def test_speaker_diarization_tracking(self) -> None:
        """Speaker label is correctly tracked across tokens."""
        on_sentence = MagicMock()
        t = _make_transcriber(on_sentence=on_sentence)
        t._is_running = True

        messages = [
            json.dumps(
                {
                    "tokens": [
                        {
                            "text": "Hi",
                            "is_final": True,
                            "translation_status": "original",
                            "speaker": "Speaker_0",
                            "start_ms": 0,
                            "end_ms": 500,
                        },
                        {"text": "<end>"},
                    ],
                }
            ),
        ]

        ws = _make_ws(messages)
        asyncio.run(t._receive_tokens(ws))

        on_sentence.assert_called_once_with("Hi", 0.0, 0.5, "Speaker_0", "")

    def test_timing_defaults_to_zero(self) -> None:
        """Timestamps default to 0.0 when not provided in tokens."""
        on_sentence = MagicMock()
        t = _make_transcriber(on_sentence=on_sentence)
        t._is_running = True

        messages = [
            json.dumps(
                {
                    "tokens": [
                        {
                            "text": "No time",
                            "is_final": True,
                            "translation_status": "original",
                        },
                        {"text": "<end>"},
                    ],
                }
            ),
        ]

        ws = _make_ws(messages)
        asyncio.run(t._receive_tokens(ws))

        on_sentence.assert_called_once_with("No time", 0.0, 0.0, "", "")

    def test_stops_when_not_running(self) -> None:
        """Receive loop exits when is_running becomes False."""
        on_sentence = MagicMock()
        t = _make_transcriber(on_sentence=on_sentence)
        t._is_running = False  # Already stopped

        messages = [
            json.dumps(
                {
                    "tokens": [
                        {
                            "text": "Should not see this",
                            "is_final": True,
                            "translation_status": "original",
                            "start_ms": 0,
                            "end_ms": 100,
                        },
                        {"text": "<end>"},
                    ],
                }
            ),
        ]

        ws = _make_ws(messages)
        asyncio.run(t._receive_tokens(ws))

        on_sentence.assert_not_called()

    def test_translation_tokens_accumulated(self) -> None:
        """Translation tokens are accumulated separately from originals."""
        on_sentence = MagicMock()
        t = _make_transcriber(on_sentence=on_sentence)
        t._is_running = True

        messages = [
            json.dumps(
                {
                    "tokens": [
                        {
                            "text": "Hola ",
                            "is_final": True,
                            "translation_status": "original",
                            "start_ms": 0,
                            "end_ms": 500,
                        },
                        {
                            "text": "mundo",
                            "is_final": True,
                            "translation_status": "original",
                            "start_ms": 500,
                            "end_ms": 1000,
                        },
                        {
                            "text": "Hello ",
                            "is_final": True,
                            "translation_status": "translation",
                        },
                        {
                            "text": "world",
                            "is_final": True,
                            "translation_status": "translation",
                        },
                        {"text": "<end>"},
                    ],
                }
            ),
        ]

        ws = _make_ws(messages)
        asyncio.run(t._receive_tokens(ws))

        on_sentence.assert_called_once_with(
            "Hola mundo",
            0.0,
            1.0,
            "",
            "Hello world",
        )

    def test_state_resets_between_sentences(self) -> None:
        """Accumulator state is cleared between sentences."""
        on_sentence = MagicMock()
        t = _make_transcriber(on_sentence=on_sentence)
        t._is_running = True

        messages = [
            json.dumps(
                {
                    "tokens": [
                        {
                            "text": "One",
                            "is_final": True,
                            "translation_status": "original",
                            "speaker": "A",
                            "start_ms": 0,
                            "end_ms": 100,
                        },
                        {"text": "<end>"},
                        {
                            "text": "Two",
                            "is_final": True,
                            "translation_status": "original",
                            "start_ms": 200,
                            "end_ms": 300,
                        },
                        {"text": "<end>"},
                    ],
                }
            ),
        ]

        ws = _make_ws(messages)
        asyncio.run(t._receive_tokens(ws))

        assert on_sentence.call_count == 2  # noqa: PLR2004
        # Second sentence should NOT carry over speaker "A"
        on_sentence.assert_any_call("One", 0.0, 0.1, "A", "")
        on_sentence.assert_any_call("Two", 0.2, 0.3, "", "")

    def test_empty_tokens_list_ignored(self) -> None:
        """Messages with an empty tokens list produce no output."""
        on_sentence = MagicMock()
        t = _make_transcriber(on_sentence=on_sentence)
        t._is_running = True

        messages = [
            json.dumps({"tokens": []}),
        ]

        ws = _make_ws(messages)
        asyncio.run(t._receive_tokens(ws))
        on_sentence.assert_not_called()


# ---------------------------------------------------------------------------
# _send_audio() — audio streaming
# ---------------------------------------------------------------------------


class TestSendAudioStream:
    """Tests for _send_audio() async method."""

    def test_sends_queued_audio(self) -> None:
        """Queued PCM bytes are sent over the WebSocket."""
        t = _make_transcriber()
        t._is_running = True
        t._audio_queue.put(b"\x00\x01")

        mock_ws = AsyncMock()

        async def run():
            """Run sender that stops after sending one chunk."""
            original_get = t._audio_queue.get
            call_count = 0

            def get_and_stop(**kwargs):
                nonlocal call_count
                call_count += 1
                if call_count > 1:
                    t._is_running = False
                    raise queue.Empty
                return original_get(timeout=kwargs.get("timeout", 0.1))

            t._audio_queue.get = get_and_stop
            await t._send_audio(mock_ws)

        asyncio.run(run())

        # Should have sent the audio chunk and empty bytes for graceful close
        mock_ws.send.assert_any_call(b"\x00\x01")

    def test_sends_empty_bytes_on_graceful_close(self) -> None:
        """Empty bytes are sent when the loop exits for graceful close."""
        t = _make_transcriber()
        t._is_running = False  # Exit immediately

        mock_ws = AsyncMock()

        asyncio.run(t._send_audio(mock_ws))

        # The last send should be the graceful close empty bytes
        mock_ws.send.assert_called_with(b"")


# ---------------------------------------------------------------------------
# _build_config() — combined translation + translation_terms
# ---------------------------------------------------------------------------


class TestBuildConfigCombined:
    """Tests for _build_config with translation AND translation_terms together."""

    def test_config_has_both_translation_and_terms(self) -> None:
        """Config includes both translation and context.translation_terms."""
        from src.core.soniox_engine import SonioxTranscriber

        t = SonioxTranscriber(
            api_key="key",
            on_sentence=MagicMock(),
            target_lang="vi",
            translation_terms=[{"source": "AI", "target": "Trí tuệ nhân tạo"}],
        )
        cfg = t._build_config()
        assert "translation" in cfg
        assert cfg["translation"]["target_language"] == "vi"
        assert "context" in cfg
        assert cfg["context"]["translation_terms"][0]["source"] == "AI"


# ---------------------------------------------------------------------------
# _ws_loop() — reconnection exhaustion
# ---------------------------------------------------------------------------


class TestWsLoopReconnectionExhaustion:
    """Tests for _ws_loop() when all reconnection attempts are exhausted."""

    def test_exception_re_raised_after_max_retries(self) -> None:
        """After _RECONNECT_MAX retries all fail, the last exception propagates."""
        t = _make_transcriber()
        t._is_running = True
        connect_count = 0

        class _AlwaysFailConnect:
            """Async context manager that always raises on __aenter__."""

            def __init__(self, *args, **kwargs) -> None:
                nonlocal connect_count
                connect_count += 1

            async def __aenter__(self):
                raise ConnectionError(f"failure #{connect_count}")

            async def __aexit__(self, *args):
                pass

        mock_ws_mod = MagicMock()
        mock_ws_mod.connect = _AlwaysFailConnect

        with (
            patch.dict("sys.modules", {"websockets": mock_ws_mod}),
            patch("asyncio.sleep", new_callable=AsyncMock),
            pytest.raises(ConnectionError, match=f"failure #{_RECONNECT_MAX}"),
        ):
            asyncio.run(t._ws_loop())

        # All _RECONNECT_MAX attempts should have been made
        assert connect_count == _RECONNECT_MAX

    def test_is_running_checked_after_each_failure(self) -> None:
        """If _is_running becomes False mid-retry, the exception still propagates."""
        t = _make_transcriber()
        t._is_running = True
        connect_count = 0

        class _FailAndStopConnect:
            """Fails on __aenter__ and stops the transcriber after first attempt."""

            def __init__(self, *args, **kwargs) -> None:
                nonlocal connect_count
                connect_count += 1

            async def __aenter__(self):
                # After first failure, simulate external stop
                if connect_count >= 2:  # noqa: PLR2004
                    t._is_running = False
                raise ConnectionError("transient error")

            async def __aexit__(self, *args):
                pass

        mock_ws_mod = MagicMock()
        mock_ws_mod.connect = _FailAndStopConnect

        # When _is_running is False and attempt < _RECONNECT_MAX,
        # the code checks `not self._is_running` and re-raises
        with (
            patch.dict("sys.modules", {"websockets": mock_ws_mod}),
            patch("asyncio.sleep", new_callable=AsyncMock),
            pytest.raises(ConnectionError, match="transient error"),
        ):
            asyncio.run(t._ws_loop())

        # Should have attempted at most 2 connections before stopping
        assert connect_count <= _RECONNECT_MAX

    def test_backoff_delays_are_exponential(self) -> None:
        """Reconnection delays follow exponential backoff pattern."""
        t = _make_transcriber()
        t._is_running = True
        connect_count = 0
        sleep_delays: list[float] = []

        class _AlwaysFailConnect:
            """Async context manager that always raises on __aenter__."""

            def __init__(self, *args, **kwargs) -> None:
                nonlocal connect_count
                connect_count += 1

            async def __aenter__(self):
                raise ConnectionError(f"fail #{connect_count}")

            async def __aexit__(self, *args):
                pass

        async def _capture_sleep(delay: float) -> None:
            sleep_delays.append(delay)

        mock_ws_mod = MagicMock()
        mock_ws_mod.connect = _AlwaysFailConnect

        with (
            patch.dict("sys.modules", {"websockets": mock_ws_mod}),
            patch("asyncio.sleep", side_effect=_capture_sleep),
            pytest.raises(ConnectionError),
        ):
            asyncio.run(t._ws_loop())

        # _RECONNECT_MAX - 1 sleeps happen (last failure re-raises immediately)
        expected_sleeps = _RECONNECT_MAX - 1
        assert len(sleep_delays) == expected_sleeps
        # Verify exponential backoff: delay = _RECONNECT_BASE_DELAY * 2^(attempt-1)
        for i, delay in enumerate(sleep_delays):
            expected = _RECONNECT_BASE_DELAY * (2**i)
            assert delay == pytest.approx(expected)


# ---------------------------------------------------------------------------
# send_audio — concurrent and edge-case tests
# ---------------------------------------------------------------------------


class TestSonioxConcurrentSendAudio:
    """Test send_audio thread safety and edge cases."""

    def test_concurrent_send_audio_no_crash(self) -> None:
        """Five threads calling send_audio simultaneously should not crash.

        Since queue.Queue is thread-safe and send_audio uses a simple
        boolean guard + put(), concurrent access should work without
        corruption or exceptions.
        """
        import threading as _th

        t = _make_transcriber()
        t._is_running = True
        errors: list[Exception] = []

        def _sender(thread_id: int) -> None:
            try:
                for i in range(50):
                    t.send_audio(f"t{thread_id}-{i}".encode())
            except Exception as exc:
                errors.append(exc)

        threads = [_th.Thread(target=_sender, args=(tid,)) for tid in range(5)]
        for th in threads:
            th.start()
        for th in threads:
            th.join(timeout=5)

        assert errors == []
        # 5 threads * 50 chunks = 250 total
        assert t._audio_queue.qsize() == 250  # noqa: PLR2004

    def test_send_audio_when_not_running_drops(self) -> None:
        """send_audio when _is_running is False silently drops data."""
        t = _make_transcriber()
        assert t._is_running is False
        t.send_audio(b"\x00\x01\x02\x03")
        t.send_audio(b"\x04\x05\x06\x07")
        assert t._audio_queue.empty()

    def test_send_audio_large_payload(self) -> None:
        """send_audio handles a large payload without issue.

        Even a 1 MB chunk should be enqueued successfully since the
        queue has no maxsize limit.
        """
        t = _make_transcriber()
        t._is_running = True
        big_chunk = b"\x00" * (1024 * 1024)
        t.send_audio(big_chunk)
        assert t._audio_queue.qsize() == 1
        assert t._audio_queue.get_nowait() == big_chunk


# ---------------------------------------------------------------------------
# _receive_tokens — malformed token data
# ---------------------------------------------------------------------------


class TestSonioxMalformedTokens:
    """Test _receive_tokens with malformed or unexpected token data."""

    def test_token_missing_text_field(self) -> None:
        """Token dict without 'text' key uses empty string via .get() default.

        The code does ``text = token.get("text", "")``, so a missing text
        field produces an empty string.  With only an <end> following,
        the sentence should be empty after strip() and thus not emitted.
        """
        on_sentence = MagicMock()
        t = _make_transcriber(on_sentence=on_sentence)
        t._is_running = True

        messages = [
            json.dumps(
                {
                    "tokens": [
                        {
                            "is_final": True,
                            "translation_status": "original",
                            "start_ms": 0,
                            "end_ms": 100,
                            # "text" key intentionally missing
                        },
                        {"text": "<end>"},
                    ],
                }
            ),
        ]

        ws = _make_ws(messages)
        asyncio.run(t._receive_tokens(ws))

        # Empty text after strip() → not emitted
        on_sentence.assert_not_called()

    def test_token_empty_text_with_is_final(self) -> None:
        """Token with empty text and is_final=True does not produce output.

        An empty string is appended to current_original, and after
        join + strip the result is empty, so on_sentence is not called.
        """
        on_sentence = MagicMock()
        t = _make_transcriber(on_sentence=on_sentence)
        t._is_running = True

        messages = [
            json.dumps(
                {
                    "tokens": [
                        {
                            "text": "",
                            "is_final": True,
                            "translation_status": "original",
                            "start_ms": 0,
                            "end_ms": 100,
                        },
                        {"text": "<end>"},
                    ],
                }
            ),
        ]

        ws = _make_ws(messages)
        asyncio.run(t._receive_tokens(ws))

        on_sentence.assert_not_called()

    def test_token_missing_translation_status_routes_to_original(self) -> None:
        """Missing ``translation_status`` → token treated as original.

        Soniox only emits the ``translation_status`` field when the
        session has a ``translation`` config.  In transcription-only
        mode (no ``target_lang``) every token has no status — those
        are the source text.  Earlier behaviour silently dropped them
        because the parser only matched ``status == "original"``.

        See ``TestReceiveTokensTranscriptionOnly`` for the full
        end-to-end contract; this test pins the per-token routing.
        """
        on_sentence = MagicMock()
        t = _make_transcriber(on_sentence=on_sentence)
        t._is_running = True

        messages = [
            json.dumps(
                {
                    "tokens": [
                        {
                            "text": "mystery",
                            "is_final": True,
                            # "translation_status" intentionally missing
                            "start_ms": 0,
                            "end_ms": 500,
                        },
                        {"text": "<end>"},
                    ],
                }
            ),
        ]

        ws = _make_ws(messages)
        asyncio.run(t._receive_tokens(ws))

        # Token routed to original → sentence emitted with the text.
        on_sentence.assert_called_once_with(
            "mystery", 0.0, 0.5, "", "",
        )

    def test_speaker_change_mid_sentence(self) -> None:
        """Tokens with different speaker fields in the same sentence.

        The code sets ``current_speaker`` to the last non-empty speaker
        seen before <end>.  If Speaker_0 speaks first and Speaker_1
        speaks second, the emitted speaker should be Speaker_1.
        """
        on_sentence = MagicMock()
        t = _make_transcriber(on_sentence=on_sentence)
        t._is_running = True

        messages = [
            json.dumps(
                {
                    "tokens": [
                        {
                            "text": "Hello ",
                            "is_final": True,
                            "translation_status": "original",
                            "speaker": "Speaker_0",
                            "start_ms": 0,
                            "end_ms": 500,
                        },
                        {
                            "text": "world",
                            "is_final": True,
                            "translation_status": "original",
                            "speaker": "Speaker_1",
                            "start_ms": 500,
                            "end_ms": 1000,
                        },
                        {"text": "<end>"},
                    ],
                }
            ),
        ]

        ws = _make_ws(messages)
        asyncio.run(t._receive_tokens(ws))

        on_sentence.assert_called_once()
        args = on_sentence.call_args[0]
        assert args[0] == "Hello world"
        # Last speaker wins
        assert args[3] == "Speaker_1"

    def test_token_with_unknown_translation_status_treated_as_original(
        self,
    ) -> None:
        """Unknown ``translation_status`` value → safer-default original.

        Forward-compat contract: only the documented ``"translation"``
        value routes to the translated buffer; every other value
        (``"original"``, ``"none"`` from two-way mode third-language,
        ``None`` from transcription-only sessions, AND any future
        ``"partial_translation"``-style unknown) routes to original.
        The alternative — silently dropping unknowns — was the cause
        of the transcription-only "empty transcript" bug.
        """
        on_sentence = MagicMock()
        t = _make_transcriber(on_sentence=on_sentence)
        t._is_running = True

        messages = [
            json.dumps(
                {
                    "tokens": [
                        {
                            "text": "Known ",
                            "is_final": True,
                            "translation_status": "original",
                            "start_ms": 0,
                            "end_ms": 500,
                        },
                        {
                            "text": "extra",
                            "is_final": True,
                            "translation_status": "partial_translation",
                        },
                        {"text": "<end>"},
                    ],
                }
            ),
        ]

        ws = _make_ws(messages)
        asyncio.run(t._receive_tokens(ws))

        on_sentence.assert_called_once()
        args = on_sentence.call_args[0]
        # Both tokens land in the original buffer.
        assert args[0] == "Known extra"
        # Translation is empty because no token had status == "translation".
        assert args[4] == ""


# ---------------------------------------------------------------------------
# Reconnection state tests
# ---------------------------------------------------------------------------


class TestSonioxReconnectionState:
    """Test reconnection cleanup and exhaustion."""

    def test_reconnection_resets_accumulator(self) -> None:
        """After reconnection, token accumulators are fresh.

        Each call to _receive_tokens starts with empty accumulators,
        so reconnecting (which calls _receive_tokens on a new ws)
        should not carry over partial sentences from the previous
        connection.
        """
        on_sentence = MagicMock()
        t = _make_transcriber(on_sentence=on_sentence)
        t._is_running = True

        # First connection: partial sentence with no <end> — flushes "Partial"
        messages_1 = [
            json.dumps(
                {
                    "tokens": [
                        {
                            "text": "Partial",
                            "is_final": True,
                            "translation_status": "original",
                            "start_ms": 0,
                            "end_ms": 500,
                        },
                    ],
                }
            ),
            # Connection drops (messages end without <end>)
        ]

        # Second connection: completely new sentence
        messages_2 = [
            json.dumps(
                {
                    "tokens": [
                        {
                            "text": "Fresh start",
                            "is_final": True,
                            "translation_status": "original",
                            "start_ms": 1000,
                            "end_ms": 2000,
                        },
                        {"text": "<end>"},
                    ],
                }
            ),
        ]

        ws1 = _make_ws(messages_1)
        asyncio.run(t._receive_tokens(ws1))

        # First call flushes "Partial" at the end of the message stream
        assert on_sentence.call_count == 1
        assert on_sentence.call_args_list[0][0][0] == "Partial"

        on_sentence.reset_mock()

        ws2 = _make_ws(messages_2)
        asyncio.run(t._receive_tokens(ws2))

        # Second call only contains "Fresh start" (no carryover from ws1)
        assert on_sentence.call_count == 1
        assert on_sentence.call_args_list[0][0][0] == "Fresh start"

    def test_max_reconnections_exhausted(self) -> None:
        """After _RECONNECT_MAX failed connections, _ws_loop raises.

        The _run_loop catches the exception and calls on_status with
        the error message.
        """
        on_status = MagicMock()
        on_stopped = MagicMock()
        t = _make_transcriber(on_status=on_status, on_stopped=on_stopped)
        t._is_running = True
        connect_count = 0

        class _AlwaysFail:
            """Async context manager that always raises."""

            def __init__(self, *args, **kwargs) -> None:
                nonlocal connect_count
                connect_count += 1

            async def __aenter__(self):
                raise ConnectionError(f"fail #{connect_count}")

            async def __aexit__(self, *args):
                pass

        mock_ws_mod = MagicMock()
        mock_ws_mod.connect = _AlwaysFail

        on_error = MagicMock()
        t._on_error = on_error

        with (
            patch.dict("sys.modules", {"websockets": mock_ws_mod}),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            t._run_loop()

        # Should have attempted _RECONNECT_MAX connections
        assert connect_count == _RECONNECT_MAX
        # The classifier surfaces the underlying network failure as
        # STT_CONNECTION_LOST through the new on_error channel
        # (on_status is reserved for non-error status updates).
        on_error.assert_called_once()
        category, _raw = on_error.call_args.args
        assert category == "STT_CONNECTION_LOST"
        # on_stopped is always called in finally
        on_stopped.assert_called_once()
        # Engine is no longer running
        assert t._is_running is False


# ───────────────────────────────────────────────────────────────────────
# Mid-stream errors — handshake passes, classifier kicks in later.
# ───────────────────────────────────────────────────────────────────────


class TestSonioxMidStreamErrors:
    """Errors that arrive AFTER the engine has been streaming successfully.

    Soniox can revoke a session token while a transcription is in
    flight (rotation, quota exceeded mid-call, abuse-detection
    block).  The error arrives as a JSON ``error_code`` in the same
    socket that previously delivered tokens — not as a WebSocket
    close.  The classifier must surface it via ``on_error`` with
    the right STT_* category, set ``_payload_error_emitted`` so
    the eventual close isn't double-classified, and break out of
    the receive loop cleanly.
    """

    def test_token_expiry_mid_stream_emits_auth_invalid(self) -> None:
        """A 401-style ``error_code`` arriving after sentences → STT_AUTH_INVALID."""
        on_sentence = MagicMock()
        on_error = MagicMock()
        t = _make_transcriber(
            on_sentence=on_sentence,
            on_error=on_error,
        )
        t._is_running = True

        # Stream three normal token frames and then a mid-stream auth
        # error.  The server can do this when the API key is rotated
        # or the per-key quota gets exhausted mid-call.
        messages = [
            json.dumps({
                "tokens": [
                    {
                        "text": "Hello",
                        "start_ms": 0,
                        "end_ms": 500,
                        "is_final": True,
                        "translation_status": "original",
                    },
                    {
                        "text": "<end>",
                        "start_ms": 500,
                        "end_ms": 500,
                        "is_final": True,
                    },
                ],
            }),
            json.dumps({
                "error_code": 401,
                "error_message": "Invalid API key",
            }),
        ]

        ws = _make_ws(messages)
        asyncio.run(t._receive_tokens(ws))

        # First sentence still made it through before the error.
        on_sentence.assert_called_once()

        # Error was classified and surfaced via on_error.
        on_error.assert_called_once()
        category, raw = on_error.call_args.args
        assert category == "STT_AUTH_INVALID"
        assert "401" in raw
        assert "Invalid API key" in raw

        # ``_payload_error_emitted`` short-circuits transport reclassification
        # in _run_loop so the user doesn't see two toasts for one event.
        assert t._payload_error_emitted is True

    def test_quota_exceeded_mid_stream_emits_quota(self) -> None:
        """``error_code`` 429 mid-stream → STT_QUOTA_EXCEEDED."""
        on_error = MagicMock()
        t = _make_transcriber(on_error=on_error)
        t._is_running = True

        messages = [
            json.dumps({
                "error_code": 429,
                "error_message": "Quota exceeded for the day",
            }),
        ]

        ws = _make_ws(messages)
        asyncio.run(t._receive_tokens(ws))

        on_error.assert_called_once()
        category, raw = on_error.call_args.args
        assert category == "STT_QUOTA_EXCEEDED"
        assert "429" in raw

    def test_payload_error_envelope_missing_error_message(self) -> None:
        """``error_code`` present but ``error_message`` absent → still classifies + emits.

        Some Soniox releases drop the message on policy errors.  The
        emit must still fire with the code in the raw string so the
        user gets *something* actionable, even without the prose.
        """
        on_error = MagicMock()
        t = _make_transcriber(on_error=on_error)
        t._is_running = True

        messages = [json.dumps({"error_code": 403})]

        ws = _make_ws(messages)
        asyncio.run(t._receive_tokens(ws))

        on_error.assert_called_once()
        _category, raw = on_error.call_args.args
        # 403 is in the raw string; the missing message is rendered as empty.
        assert "403" in raw

    def test_unknown_error_code_falls_back_to_stt_unknown(self) -> None:
        """Unmapped error_code → STT_UNKNOWN fallback (still surfaces, no crash)."""
        on_error = MagicMock()
        t = _make_transcriber(on_error=on_error)
        t._is_running = True

        # 9999 isn't in the classifier's known map.
        messages = [json.dumps({
            "error_code": 9999,
            "error_message": "future error code",
        })]

        ws = _make_ws(messages)
        asyncio.run(t._receive_tokens(ws))

        on_error.assert_called_once()
        category, _raw = on_error.call_args.args
        assert category == "STT_UNKNOWN"


class TestSonioxConfigPayload:
    """``_build_config`` translates init args into the Soniox WS payload."""

    def test_translation_terms_appear_in_config(self) -> None:
        """Glossary terms passed to the constructor land in ``config.context``.

        Without this, the ``translation_terms`` constructor arg would
        be accepted and stored on the instance but silently dropped on
        the wire — Soniox would translate without the user's glossary.
        """
        terms = [
            {"source": "GitHub", "target": "GitHub"},
            {"source": "USA", "target": "США"},
        ]
        t = _make_transcriber(translation_terms=terms, target_lang="ru")
        config = t._build_config()
        assert "context" in config, (
            f"translation_terms must reach config.context; got {config}"
        )
        assert config["context"]["translation_terms"] == terms

    def test_no_context_key_when_translation_terms_unset(self) -> None:
        """Empty/None terms → no ``context`` key (avoids spurious payload bytes)."""
        t = _make_transcriber(translation_terms=None, target_lang="ru")
        assert "context" not in t._build_config()

    def test_diarization_flag_propagates_to_config(self) -> None:
        """``enable_diarization=True`` → ``enable_speaker_diarization`` in config."""
        t = _make_transcriber(enable_diarization=True)
        assert t._build_config()["enable_speaker_diarization"] is True

        t = _make_transcriber(enable_diarization=False)
        assert t._build_config()["enable_speaker_diarization"] is False

    def test_target_lang_emits_translation_block(self) -> None:
        """``target_lang`` set → config.translation has the right shape."""
        t = _make_transcriber(target_lang="vi")
        config = t._build_config()
        assert config.get("translation") == {
            "type": "one_way",
            "target_language": "vi",
        }

    def test_no_translation_block_when_target_unset(self) -> None:
        """Empty target → no ``translation`` key."""
        t = _make_transcriber(target_lang="")
        assert "translation" not in t._build_config()


class TestReceiveTokensTranscriptionOnly:
    """Regression: transcription-only sessions (no translation config).

    When ``target_lang`` is empty, the Soniox config omits the
    ``translation`` object and the server responds with tokens that
    carry NO ``translation_status`` field at all.  Our parser must
    treat missing-status as ``"original"`` so the transcript still
    populates — earlier code only routed status-tagged ``"original"``
    tokens, silently dropping every token in transcription-only mode.
    """

    def test_emits_sentence_when_translation_status_missing(self) -> None:
        """No ``translation_status`` on tokens → still routes to original."""
        on_sentence = MagicMock()
        t = _make_transcriber(on_sentence=on_sentence, target_lang="")
        t._is_running = True

        # Tokens WITHOUT translation_status — matches what Soniox
        # actually emits when the session has no translation config.
        messages = [
            json.dumps(
                {
                    "tokens": [
                        {
                            "text": "Hello ",
                            "is_final": True,
                            "speaker": "S1",
                            "start_ms": 1000,
                            "end_ms": 1500,
                        },
                        {
                            "text": "world",
                            "is_final": True,
                            "speaker": "S1",
                            "start_ms": 1500,
                            "end_ms": 2000,
                        },
                        {"text": "<end>"},
                    ],
                }
            ),
        ]
        ws = _make_ws(messages)
        asyncio.run(t._receive_tokens(ws))

        # Transcription-only mode: source text emitted with empty
        # translation slot.  Previously this was silently dropped.
        on_sentence.assert_called_once_with(
            "Hello world", 1.0, 2.0, "S1", "",
        )
