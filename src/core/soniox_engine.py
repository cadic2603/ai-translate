"""Soniox real-time speech-to-text engine via WebSocket.

Streams audio to the Soniox API and receives transcription tokens
with optional translation and speaker diarization.
"""

from __future__ import annotations

import asyncio
import json
import logging
import queue
import threading
from collections.abc import Callable
from typing import Any

logger = logging.getLogger("soniox_engine")

_WS_URL = "wss://stt-rt.soniox.com/transcribe-websocket"
_MODEL = "stt-rt-v4"
# Application-level keepalive interval.  Soniox doesn't *document* a
# keepalive mechanism, but the reference JS client at
# ``~/my-translator/src/js/soniox.js`` sends ``{"type": "keepalive"}``
# every 15 s, which is empirical evidence the server tolerates (and
# probably benefits from) it.  Without it, an idle mic — user paused
# speaking — could trip a server-side idle timeout that protocol-
# level PING/PONG alone might not refresh.  15 s matches the
# reference client.
_KEEPALIVE_INTERVAL = 15  # seconds
_RECONNECT_MAX = 3
_RECONNECT_BASE_DELAY = 2.0  # seconds


class SonioxTranscriber:
    """Streams audio to Soniox and emits transcribed/translated sentences.

    Callback signature:
        on_sentence(text, start_sec, end_sec, speaker, translated)
    """

    def __init__(  # noqa: PLR0913
        self,
        api_key: str,
        on_sentence: Callable[[str, float, float, str, str], None],
        on_status: Callable[[str], None] | None = None,
        on_stopped: Callable[[], None] | None = None,
        source_lang: str = "",
        target_lang: str = "",
        enable_diarization: bool = True,
        translation_terms: list[dict[str, str]] | None = None,
        on_error: Callable[[str, str], None] | None = None,
    ) -> None:
        """Initializes the Soniox transcriber.

        Args:
            api_key: Soniox API key.
            on_sentence: Called with (text, start_sec, end_sec, speaker, translated).
            on_status: Called with status messages (non-errors only — for
                the new error path use ``on_error``).
            on_stopped: Called when the engine stops.
            source_lang: Source language hint (2-letter code), empty for auto.
            target_lang: Target language (2-letter code), empty to skip translation.
            enable_diarization: Enable speaker diarization.
            translation_terms: Glossary terms as [{"source": "...", "target": "..."}].
            on_error: Called with ``(category_tag, raw_message)`` when a
                fatal session error is classified.  ``category_tag`` is
                an ``STT_*`` constant from ``src.core.live_errors``;
                ``raw_message`` is the underlying exception / payload
                string for logging.  When None, errors are logged but
                not surfaced — caller is responsible for noticing the
                ``on_stopped`` callback that follows.
        """
        self._api_key = api_key
        self._on_sentence = on_sentence
        self._on_status = on_status
        self._on_stopped = on_stopped
        self._on_error = on_error
        self._source_lang = source_lang
        self._target_lang = target_lang
        self._enable_diarization = enable_diarization
        self._translation_terms = translation_terms
        self._audio_queue: queue.Queue[bytes] = queue.Queue()
        self._is_running = False
        self._thread: threading.Thread | None = None
        # Set by _receive_tokens on the first ``error_code`` JSON it
        # sees, so _run_loop's exception handler knows the close that
        # follows is just cleanup, not a separate diagnosis.
        self._payload_error_emitted = False

    def send_audio(self, pcm_bytes: bytes) -> None:
        """Enqueues raw PCM audio (s16le, 16kHz, mono) for streaming."""
        if self._is_running:
            self._audio_queue.put(pcm_bytes)

    def start(self) -> None:
        """Starts the WebSocket connection and audio streaming."""
        if self._is_running:
            return
        self._is_running = True
        self._emit_status("live.status_connecting")
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stops the transcriber."""
        self._is_running = False
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    @property
    def is_running(self) -> bool:
        """Returns True if the transcriber is active."""
        return self._is_running

    def _emit_status(self, key: str) -> None:
        """Emits a translated status message."""
        if self._on_status:
            from src.constants.i18n import tr  # noqa: PLC0415

            self._on_status(tr(key))

    def _emit_error(self, category: str, raw_message: str = "") -> None:
        """Surfaces a classified error category to the caller.

        Logs at error level regardless of whether ``on_error`` is wired,
        so the underlying cause survives in app.log even when the UI
        chose not to listen.  Sets ``_payload_error_emitted`` so the
        outer exception handler knows not to re-classify the close
        that immediately follows the error JSON.
        """
        logger.error(
            "Soniox error: %s (raw: %s)", category, raw_message,
        )
        self._payload_error_emitted = True
        if self._on_error:
            try:
                self._on_error(category, raw_message)
            except Exception:
                logger.debug("on_error callback failed", exc_info=True)

    def _build_config(self) -> dict[str, Any]:
        """Builds the Soniox WebSocket configuration message."""
        config: dict = {
            "api_key": self._api_key,
            "model": _MODEL,
            "audio_format": "pcm_s16le",
            "sample_rate": 16000,
            "num_channels": 1,
            "enable_endpoint_detection": True,
            "max_endpoint_delay_ms": 3000,
            "enable_speaker_diarization": self._enable_diarization,
            "enable_language_identification": True,
        }
        if self._source_lang:
            config["language_hints"] = [self._source_lang]

        if self._target_lang:
            config["translation"] = {
                "type": "one_way",
                "target_language": self._target_lang,
            }

        if self._translation_terms:
            config["context"] = {
                "translation_terms": self._translation_terms,
            }

        return config

    def _run_loop(self) -> None:
        """Runs the async event loop in the background thread."""
        from src.core.live_errors import (  # noqa: PLC0415
            classify_soniox_exception,
        )

        try:
            asyncio.run(self._ws_loop())
        except Exception as exc:
            # If we already emitted a payload-level error inside the
            # receive loop, the transport-level close that bubbled up
            # here is just cleanup — don't double-toast the user.
            if not self._payload_error_emitted:
                category = classify_soniox_exception(exc)
                if category is not None:
                    self._emit_error(category, str(exc))
                else:
                    # Graceful close (ConnectionClosedOK) — just log.
                    logger.info("Soniox session ended cleanly")
        finally:
            self._is_running = False
            if self._on_stopped:
                try:
                    self._on_stopped()
                except Exception:
                    logger.debug("on_stopped callback failed", exc_info=True)

    async def _ws_loop(self) -> None:
        """Main WebSocket loop with reconnection support."""
        import websockets  # noqa: PLC0415

        attempt = 0
        while self._is_running and attempt < _RECONNECT_MAX:
            try:
                async with websockets.connect(_WS_URL) as ws:
                    # Send config
                    await ws.send(json.dumps(self._build_config()))
                    self._emit_status("live.status_listening")
                    attempt = 0  # reset on successful connect

                    # Run sender and receiver concurrently
                    sender = asyncio.create_task(self._send_audio(ws))
                    receiver = asyncio.create_task(self._receive_tokens(ws))

                    done, pending = await asyncio.wait(
                        {sender, receiver},
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    for task in pending:
                        task.cancel()
                    # Re-raise any exceptions
                    for task in done:
                        task.result()

            except asyncio.CancelledError:
                break
            except Exception as exc:
                attempt += 1
                if attempt >= _RECONNECT_MAX or not self._is_running:
                    raise
                delay = _RECONNECT_BASE_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    "Soniox connection failed (attempt %d/%d): %s, retrying in %.1fs",
                    attempt,
                    _RECONNECT_MAX,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)

    async def _send_audio(self, ws: Any) -> None:  # noqa: ANN401
        """Sends audio chunks + a 15s keepalive to the WebSocket.

        The keepalive (``{"type": "keepalive"}``) matches the
        reference JS client at ~/my-translator/src/js/soniox.js.
        Soniox doesn't *document* a keepalive mechanism but the
        production JS client uses one — empirical evidence the
        server tolerates it.  Without it, an idle mic risks tripping
        a server-side idle timeout that the ``websockets`` library's
        protocol-level PING/PONG alone might not refresh.
        """
        last_send = asyncio.get_event_loop().time()
        while self._is_running:
            try:
                pcm = self._audio_queue.get(timeout=0.1)
                await ws.send(pcm)
                last_send = asyncio.get_event_loop().time()
            except queue.Empty:
                # No audio for a tick — send keepalive when the
                # configured idle window has elapsed since the last
                # outbound frame.  Audio frames already count as
                # activity, so during normal speech the keepalive
                # never fires.
                now = asyncio.get_event_loop().time()
                if now - last_send > _KEEPALIVE_INTERVAL:
                    try:
                        await ws.send(json.dumps({"type": "keepalive"}))
                        last_send = now
                    except Exception:
                        break
                continue
            except Exception:
                break

        # Graceful close: send empty bytes (per Soniox docs,
        # "Send an empty WebSocket frame (binary or text)" — the
        # server replies with a ``finished`` response then closes).
        import contextlib  # noqa: PLC0415

        with contextlib.suppress(Exception):
            await ws.send(b"")

    async def _receive_tokens(self, ws: Any) -> None:  # noqa: ANN401, PLR0912, PLR0915
        """Receives and processes token events from the WebSocket."""
        # Accumulate tokens into sentences
        current_original = []
        current_translated = []
        current_speaker = ""
        start_ms: int | None = None
        end_ms: int | None = None

        async for message in ws:
            if not self._is_running:
                break

            event = json.loads(message)

            # Check for documented errors — Soniox sends these as JSON
            # payload integers, not WebSocket close codes.  Classify
            # AND emit before breaking; the close that follows is just
            # cleanup and shouldn't trigger transport-level reclassification.
            if event.get("error_code"):
                from src.core.live_errors import (  # noqa: PLC0415
                    classify_soniox_event,
                )

                category = classify_soniox_event(event) or "STT_UNKNOWN"
                raw = (
                    f"{event['error_code']}: "
                    f"{event.get('error_message') or ''}"
                )
                self._emit_error(category, raw)
                break

            if event.get("finished"):
                # Soniox sends ``final_audio_proc_ms`` /
                # ``total_audio_proc_ms`` in the close payload as
                # diagnostic timing fields — log them so a slow
                # session shows up in app.log without needing a
                # network capture.
                logger.info(
                    "Soniox finished: final_proc=%sms total_proc=%sms",
                    event.get("final_audio_proc_ms", "?"),
                    event.get("total_audio_proc_ms", "?"),
                )
                break

            for token in event.get("tokens", []):
                text = token.get("text", "")

                # Sentence boundary
                if text == "<end>":
                    if current_original:
                        orig = "".join(current_original).strip()
                        trans = "".join(current_translated).strip()
                        s = (start_ms or 0) / 1000.0
                        e = (end_ms or 0) / 1000.0
                        if orig:
                            self._on_sentence(
                                orig,
                                s,
                                e,
                                current_speaker,
                                trans,
                            )
                    current_original.clear()
                    current_translated.clear()
                    current_speaker = ""
                    start_ms = None
                    end_ms = None
                    continue

                if not token.get("is_final", False):
                    continue

                # Token routing — three known ``translation_status``
                # values per Soniox docs + the reference JS client at
                # ~/my-translator/src/js/soniox.js:
                #   ``"original"``    → source-language token
                #   ``"translation"`` → translated token
                #   ``"none"``        → third-language token in
                #                       two-way mode (untranslated;
                #                       belongs with originals)
                #   missing/null      → transcription-only session
                #                       (no translation config) — also
                #                       belongs with originals
                # The simplest robust rule: ONLY ``"translation"`` goes
                # to the translation buffer; everything else
                # (including unknown future statuses) routes to the
                # original buffer.  Catches the "transcription-only
                # silent drop" bug AND the future "Soniox adds a new
                # status value" forward-compat hazard.
                status = token.get("translation_status")
                if status == "translation":
                    current_translated.append(text)
                else:
                    current_original.append(text)
                    speaker = token.get("speaker") or ""
                    if speaker:
                        current_speaker = speaker
                    if token.get("start_ms") is not None:
                        if start_ms is None:
                            start_ms = token["start_ms"]
                        end_ms = token.get("end_ms", end_ms)

        # Flush remaining
        if current_original:
            orig = "".join(current_original).strip()
            trans = "".join(current_translated).strip()
            s = (start_ms or 0) / 1000.0
            e = (end_ms or 0) / 1000.0
            if orig:
                self._on_sentence(orig, s, e, current_speaker, trans)
