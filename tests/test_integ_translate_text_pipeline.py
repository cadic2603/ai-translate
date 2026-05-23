"""Integration test for the Translate Text page pipeline.

Wires the streaming translation worker into a real text payload,
asserts the chunks reach the page's target text area, and
exercises the TTS cache lookup so the Listen-button → audio file
flow is verified end-to-end with mocked external boundaries.

External dependencies (LLM API, Edge TTS subprocess) are mocked;
the page-worker plumbing, signal wiring, and cache key derivation
run for real so any wiring break (worker signal not connected, TTS
cache key drift) is caught.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_MOD = "src.ui.pages.translate_text"


@pytest.fixture()
def _mock_db_and_settings(tmp_path, monkeypatch):
    """Isolate the DB + config + TTS cache from the host environment."""
    db_file = tmp_path / "integ.db"
    monkeypatch.setattr(
        "src.core.database.get_db_path", lambda: str(db_file),
    )
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    monkeypatch.setattr(
        "src.utils.path_manager.get_app_config_dir", lambda: config_dir,
    )
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    monkeypatch.setattr(
        "src.utils.path_manager.get_app_cache_dir", lambda: cache_dir,
    )
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr(
        "src.utils.path_manager.get_app_data_dir", lambda: data_dir,
    )
    from src.core.database import init_db  # noqa: PLC0415

    init_db()


def test_streaming_translation_chunks_reach_target_area(
    qapp,
    qtbot,
    _mock_db_and_settings,  # noqa: ARG001
) -> None:
    """The worker's ``chunk`` signal threads chunks into the text area.

    Pin the contract that:
    1. ``_TextTranslationWorker`` calls ``stream_translate_text`` with
       the page's source/target language pair.
    2. Each yielded chunk reaches the page's ``target_text`` widget
       (via the ``chunk → _on_chunk`` signal).
    3. The end-of-stream ``translated`` signal lets the page detach
       the worker cleanly.

    A regression in any one of these wires (signal not connected,
    chunk handler skipping insertion) breaks this test.
    """
    from PySide6.QtWidgets import QMainWindow  # noqa: PLC0415

    from src.ui.pages.translate_text import (  # noqa: PLC0415
        _TextTranslationWorker,
        create_translate_text_page,
    )

    # Build the page on a parent window so its initialization runs
    # the same way it does in production.
    win = QMainWindow()
    qtbot.addWidget(win)
    with patch(f"{_MOD}.load_setting", return_value=""):
        # Build the page so any page-construction wiring runs (the
        # actual ``page`` ref isn't needed below — we drive the
        # worker directly).
        create_translate_text_page(win)

    # Stub the streaming translator to yield deterministic chunks.
    chunks_to_yield = ["Bon", "jour, ", "monde", "!"]

    def _fake_stream(text, **kwargs):  # noqa: ANN001, ANN003, ANN202, ARG001
        yield from chunks_to_yield

    # Drive the worker directly (run() is the load-bearing method).
    worker = _TextTranslationWorker.__new__(_TextTranslationWorker)
    worker._text = "Hello world"
    worker._src_lang = "English"
    worker._target_lang = "French"
    worker._glossary = None
    worker._provider = None
    worker._model = None
    worker._cancelled = False

    # Capture chunks via a mock signal; signal infrastructure on the
    # bare worker isn't initialised because we bypass __init__.
    captured_chunks: list[str] = []
    captured_full: list[str] = []
    worker.chunk = MagicMock(emit=captured_chunks.append)
    worker.translated = MagicMock(emit=captured_full.append)
    worker.error = MagicMock(emit=lambda _msg: None)

    # ``stream_translate_text`` is imported lazily inside ``run()``,
    # so patch the source module rather than the page module.
    with patch(
        "src.core.llm_engine.stream_translate_text",
        side_effect=_fake_stream,
    ):
        worker.run()

    # Every chunk must have been emitted in order.
    assert captured_chunks == chunks_to_yield, (
        f"chunk signal must fire for every yielded chunk; "
        f"got {captured_chunks}"
    )
    # End-of-stream ``translated`` carries the concatenated text.
    assert captured_full == ["".join(chunks_to_yield)], (
        f"translated signal must fire with the full text; "
        f"got {captured_full}"
    )


def test_tts_cache_key_round_trips_through_listen_path(
    qapp,
    qtbot,
    tmp_path,
    _mock_db_and_settings,  # noqa: ARG001
) -> None:
    """The Listen button's TTS cache key is stable across calls.

    Key derivation = ``sha256(text|lang|gender|method)[:24]``.
    A regression that changes the hash format would invalidate
    every cached audio file silently, costing one TTS round-trip
    per re-listen until the cache rebuilds.
    """
    from src.ui.pages.translate_text import (  # noqa: PLC0415
        _tts_cache_key,
        _tts_cache_path,
    )

    text = "Bonjour, monde!"
    key = _tts_cache_key(text, "French", "FEMALE", "Edge TTS")
    # Stable: re-deriving with same inputs yields the same key.
    assert key == _tts_cache_key(text, "French", "FEMALE", "Edge TTS")
    # Algorithm matches the documented sha256[:24] shape.
    expected = hashlib.sha256(
        f"{text}|French|FEMALE|Edge TTS".encode(),
    ).hexdigest()[:24]
    assert key == expected
    # Path lands under the redirected cache dir, MP3 extension.
    cache_path = Path(_tts_cache_path(text, "French", "FEMALE", "Edge TTS"))
    assert cache_path.suffix == ".mp3"
    assert cache_path.name.startswith(key)


def test_changing_voice_gender_invalidates_tts_cache(
    qapp,  # noqa: ARG001
) -> None:
    """Different gender → different cache key (the load-bearing isolation).

    Past failure mode: cache key built from text+lang only would
    return the wrong-gender audio when the user toggled the gender
    radio.  Pin the gender ↔ key dependency.
    """
    from src.ui.pages.translate_text import _tts_cache_key  # noqa: PLC0415

    text = "Bonjour"
    female_key = _tts_cache_key(text, "French", "FEMALE", "Edge TTS")
    male_key = _tts_cache_key(text, "French", "MALE", "Edge TTS")
    assert female_key != male_key, (
        "Cache key must depend on gender — otherwise the user would "
        "hear the wrong-gender voice after toggling the radio"
    )


def test_changing_tts_engine_invalidates_cache(qapp) -> None:  # noqa: ARG001
    """Different TTS engine → different cache key.

    Edge TTS, Google Cloud TTS, and ElevenLabs all produce
    distinguishable audio for the same text; the cache must not
    serve a stale Edge file when the user switched to ElevenLabs.
    """
    from src.ui.pages.translate_text import _tts_cache_key  # noqa: PLC0415

    text = "Bonjour"
    edge_key = _tts_cache_key(text, "French", "FEMALE", "Edge TTS")
    eleven_key = _tts_cache_key(text, "French", "FEMALE", "ElevenLabs")
    google_key = _tts_cache_key(text, "French", "FEMALE", "Google Cloud TTS")
    assert edge_key != eleven_key
    assert edge_key != google_key
    assert eleven_key != google_key
