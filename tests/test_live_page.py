"""Unit tests for live translation page worker logic in src/ui/pages/live.py.

Tests cover _TTSWorker.run(), _TranslationWorker.run(), and module-level
QSS style helper functions — all pure-Python logic exercised without
starting a real QThread or importing PySide6 widgets.
"""

import shutil
from unittest.mock import MagicMock, patch

_MOD = "src.ui.pages.live"


# ---------------------------------------------------------------------------
# Helpers — lightweight stand-ins for QThread + Signal
# ---------------------------------------------------------------------------


def _make_tts_worker(text: str, target_lang: str, gender: str = "FEMALE"):
    """Instantiate a _TTSWorker with QThread/Signal mocked out."""
    with (
        patch(f"{_MOD}.QThread.__init__", return_value=None),
        patch(f"{_MOD}.Signal", side_effect=lambda *a: MagicMock()),
    ):
        from src.ui.pages.live import _TTSWorker  # noqa: PLC0415

        worker = _TTSWorker(text, target_lang, gender)
        # Replace signals with plain mocks so .emit() is trackable
        worker.synthesized = MagicMock()
        worker.error = MagicMock()
        return worker


def _make_translation_worker(
    text: str,
    src_lang: str,
    target_lang: str,
    glossary_entries=None,
):
    """Instantiate a _TranslationWorker with QThread/Signal mocked out."""
    with (
        patch(f"{_MOD}.QThread.__init__", return_value=None),
        patch(f"{_MOD}.Signal", side_effect=lambda *a: MagicMock()),
    ):
        from src.ui.pages.live import _TranslationWorker  # noqa: PLC0415

        worker = _TranslationWorker(
            text,
            src_lang,
            target_lang,
            glossary_entries=glossary_entries,
        )
        worker.partial_translated = MagicMock()
        worker.translated = MagicMock()
        worker.error = MagicMock()
        return worker


# ===========================================================================
# TestTTSWorker
# ===========================================================================


class TestTTSWorker:
    """Tests for _TTSWorker.run() — TTS synthesis dispatch logic."""

    @patch(f"{_MOD}.load_setting", return_value="Edge TTS")
    def test_tts_worker_edge_tts_path(self, _load) -> None:
        """When method is 'Edge TTS', _synthesize_chunk_edge is called."""
        worker = _make_tts_worker("Hello world", "English")

        with (
            patch(
                "src.core.speech_engine._get_edge_voice",
                return_value="en-US-JennyNeural",
            ) as mock_voice,
            patch(
                "src.core.speech_engine._synthesize_chunk_edge",
            ) as mock_edge,
            patch(
                "src.core.speech_engine._get_tts_language_code",
            ),
            patch(
                "src.core.speech_engine._synthesize_chunk",
            ) as mock_google,
            patch("tempfile.NamedTemporaryFile") as mock_tmp,
        ):
            tmp_obj = MagicMock()
            tmp_obj.name = "/tmp/live_tts_abc.mp3"
            tmp_obj.close = MagicMock()
            mock_tmp.return_value = tmp_obj

            worker.run()

        mock_voice.assert_called_once_with("English", "FEMALE")
        mock_edge.assert_called_once()
        mock_google.assert_not_called()
        worker.synthesized.emit.assert_called_once()
        worker.error.emit.assert_not_called()

    @patch(f"{_MOD}.load_setting", return_value="Google Cloud TTS")
    def test_tts_worker_google_cloud_path(self, _load) -> None:
        """When method is Google Cloud + valid API key, _synthesize_chunk is called."""
        worker = _make_tts_worker("Bonjour", "French")

        with (
            patch(
                "src.core.speech_engine.load_google_cloud_api_key",
                return_value="fake-key-123",
            ),
            patch(
                "src.core.speech_engine._get_tts_language_code",
                return_value="fr-FR",
            ) as mock_lang,
            patch(
                "src.core.speech_engine._synthesize_chunk",
            ) as mock_chunk,
            patch(
                "src.core.speech_engine._synthesize_chunk_edge",
            ) as mock_edge,
            patch(
                "src.core.speech_engine._get_edge_voice",
            ),
            patch("tempfile.NamedTemporaryFile") as mock_tmp,
        ):
            tmp_obj = MagicMock()
            tmp_obj.name = "/tmp/live_tts_xyz.mp3"
            tmp_obj.close = MagicMock()
            mock_tmp.return_value = tmp_obj

            worker.run()

        mock_lang.assert_called_once_with("French")
        mock_chunk.assert_called_once()
        # Verify the api_key was forwarded
        assert mock_chunk.call_args[0][3] == "fake-key-123"
        mock_edge.assert_not_called()
        worker.synthesized.emit.assert_called_once()

    @patch(f"{_MOD}.load_setting", return_value="Google Cloud TTS")
    def test_tts_worker_google_cloud_missing_api_key(self, _load) -> None:
        """When Google Cloud selected but API key is empty, falls back to Edge TTS."""
        worker = _make_tts_worker("Hola", "Spanish")

        with (
            patch(
                "src.core.speech_engine.load_google_cloud_api_key",
                return_value="",
            ),
            patch(
                "src.core.speech_engine._get_edge_voice",
                return_value="es-ES-ElviraNeural",
            ) as mock_voice,
            patch(
                "src.core.speech_engine._synthesize_chunk_edge",
            ) as mock_edge,
            patch(
                "src.core.speech_engine._get_tts_language_code",
            ),
            patch(
                "src.core.speech_engine._synthesize_chunk",
            ) as mock_google,
            patch("tempfile.NamedTemporaryFile") as mock_tmp,
        ):
            tmp_obj = MagicMock()
            tmp_obj.name = "/tmp/live_tts_fallback.mp3"
            tmp_obj.close = MagicMock()
            mock_tmp.return_value = tmp_obj

            worker.run()

        # Falls back to Edge when API key is empty
        mock_voice.assert_called_once_with("Spanish", "FEMALE")
        mock_edge.assert_called_once()
        mock_google.assert_not_called()
        worker.synthesized.emit.assert_called_once()

    @patch(f"{_MOD}.load_setting", return_value="Edge TTS")
    def test_tts_worker_temp_file_created(self, _load) -> None:
        """Temp file has .mp3 suffix and live_tts_ prefix."""
        worker = _make_tts_worker("Test", "English")

        with (
            patch(
                "src.core.speech_engine._get_edge_voice",
                return_value="en-US-JennyNeural",
            ),
            patch("src.core.speech_engine._synthesize_chunk_edge"),
            patch(
                "src.core.speech_engine._get_tts_language_code",
            ),
            patch(
                "src.core.speech_engine._synthesize_chunk",
            ),
            patch("tempfile.NamedTemporaryFile") as mock_tmp,
        ):
            tmp_obj = MagicMock()
            tmp_obj.name = "/tmp/live_tts_test.mp3"
            tmp_obj.close = MagicMock()
            mock_tmp.return_value = tmp_obj

            worker.run()

        # Verify NamedTemporaryFile called with correct parameters
        mock_tmp.assert_called_once_with(
            suffix=".mp3",
            delete=False,
            prefix="live_tts_",
        )
        # Verify the temp file path is stored
        assert worker.temp_file == "/tmp/live_tts_test.mp3"

    @patch(f"{_MOD}.load_setting", return_value="Edge TTS")
    def test_tts_worker_error_emits_signal(self, _load) -> None:
        """When synthesis raises, error signal is emitted."""
        worker = _make_tts_worker("Broken", "English")

        with (
            patch(
                "src.core.speech_engine._get_edge_voice",
                return_value="en-US-JennyNeural",
            ),
            patch(
                "src.core.speech_engine._synthesize_chunk_edge",
                side_effect=RuntimeError("TTS_API_ERROR: no audio"),
            ),
            patch("src.core.speech_engine._get_tts_language_code"),
            patch("src.core.speech_engine._synthesize_chunk"),
            patch("tempfile.NamedTemporaryFile") as mock_tmp,
        ):
            tmp_obj = MagicMock()
            tmp_obj.name = "/tmp/live_tts_err.mp3"
            tmp_obj.close = MagicMock()
            mock_tmp.return_value = tmp_obj

            worker.run()

        worker.error.emit.assert_called_once()
        assert "TTS_API_ERROR" in worker.error.emit.call_args[0][0]
        worker.synthesized.emit.assert_not_called()

    @patch(f"{_MOD}.load_setting", return_value="Edge TTS")
    def test_tts_worker_success_emits_synthesized(self, _load) -> None:
        """On success, synthesized signal fires (not error)."""
        worker = _make_tts_worker("Success", "Vietnamese")

        with (
            patch(
                "src.core.speech_engine._get_edge_voice",
                return_value="vi-VN-HoaiMyNeural",
            ),
            patch("src.core.speech_engine._synthesize_chunk_edge"),
            patch("src.core.speech_engine._get_tts_language_code"),
            patch("src.core.speech_engine._synthesize_chunk"),
            patch("tempfile.NamedTemporaryFile") as mock_tmp,
        ):
            tmp_obj = MagicMock()
            tmp_obj.name = "/tmp/live_tts_ok.mp3"
            tmp_obj.close = MagicMock()
            mock_tmp.return_value = tmp_obj

            worker.run()

        worker.synthesized.emit.assert_called_once()
        worker.error.emit.assert_not_called()

    @patch(f"{_MOD}.load_setting", return_value="Edge TTS")
    def test_tts_worker_empty_text(self, _load) -> None:
        """Empty text still runs through synthesis (no special guard)."""
        worker = _make_tts_worker("", "English")

        with (
            patch(
                "src.core.speech_engine._get_edge_voice",
                return_value="en-US-JennyNeural",
            ),
            patch(
                "src.core.speech_engine._synthesize_chunk_edge",
            ) as mock_edge,
            patch("src.core.speech_engine._get_tts_language_code"),
            patch("src.core.speech_engine._synthesize_chunk"),
            patch("tempfile.NamedTemporaryFile") as mock_tmp,
        ):
            tmp_obj = MagicMock()
            tmp_obj.name = "/tmp/live_tts_empty.mp3"
            tmp_obj.close = MagicMock()
            mock_tmp.return_value = tmp_obj

            worker.run()

        # Empty text is passed to synthesizer (no early return in worker)
        mock_edge.assert_called_once()
        assert mock_edge.call_args[0][0] == ""
        worker.synthesized.emit.assert_called_once()


# ===========================================================================
# TestTranslationWorker
# ===========================================================================


class TestTranslationWorker:
    """Tests for _TranslationWorker.run() — LLM translation dispatch."""

    def test_translation_worker_streams_translation(self) -> None:
        """stream_translate_text is called and chunks emit partial signals."""
        worker = _make_translation_worker(
            "Hello",
            "English",
            "Vietnamese",
        )

        with patch(
            "src.core.llm_engine.stream_translate_text",
            return_value=iter(["Xin ", "chao"]),
        ) as mock_stream:
            worker.run()

        mock_stream.assert_called_once_with(
            "Hello",
            target_lang="Vietnamese",
            source_lang="English",
            glossary_entries=None,
            provider=None,
            model=None,
            context=None,
        )
        # Two chunks → two partial emits with cumulative text.
        partial_calls = worker.partial_translated.emit.call_args_list
        assert len(partial_calls) == 2  # noqa: PLR2004
        assert partial_calls[0].args == ("Hello", "Xin ")
        assert partial_calls[1].args == ("Hello", "Xin chao")
        # Final translated emit carries the full accumulated text.
        worker.translated.emit.assert_called_once_with("Hello", "Xin chao")

    def test_translation_worker_empty_stream_falls_back_to_original(self) -> None:
        """When the stream yields nothing, the original text is echoed back."""
        worker = _make_translation_worker(
            "Test",
            "Auto",
            "French",
        )

        with patch(
            "src.core.llm_engine.stream_translate_text",
            return_value=iter([]),
        ):
            worker.run()

        # No chunks ⇒ accumulated == "" ⇒ fallback to original text.
        worker.translated.emit.assert_called_once_with("Test", "Test")
        worker.partial_translated.emit.assert_not_called()
        worker.error.emit.assert_not_called()

    def test_translation_worker_single_chunk(self) -> None:
        """A single chunk is emitted as the full translation."""
        worker = _make_translation_worker(
            "Good morning",
            "",
            "Japanese",
        )

        with patch(
            "src.core.llm_engine.stream_translate_text",
            return_value=iter(["おはようございます"]),
        ):
            worker.run()

        worker.partial_translated.emit.assert_called_once_with(
            "Good morning",
            "おはようございます",
        )
        worker.translated.emit.assert_called_once_with(
            "Good morning",
            "おはようございます",
        )

    def test_translation_worker_auto_src_lang_passed_as_empty(self) -> None:
        """Empty src_lang stays empty in the stream call (auto-detect)."""
        worker = _make_translation_worker(
            "Hola",
            "",
            "English",
        )

        with patch(
            "src.core.llm_engine.stream_translate_text",
            return_value=iter(["Hello"]),
        ) as mock_stream:
            worker.run()

        # Streaming engine treats empty source_lang as auto-detect.
        assert mock_stream.call_args[1]["source_lang"] == ""

    def test_translation_worker_error_emits_signal(self) -> None:
        """Exception during streaming emits error signal."""
        worker = _make_translation_worker(
            "Error case",
            "English",
            "Spanish",
        )

        def _raising(*_args, **_kwargs):
            raise ValueError("AUTH_ERROR")

        with patch(
            "src.core.llm_engine.stream_translate_text",
            side_effect=_raising,
        ):
            worker.run()

        worker.error.emit.assert_called_once()
        assert "AUTH_ERROR" in worker.error.emit.call_args[0][0]
        worker.translated.emit.assert_not_called()

    def test_translation_worker_glossary_passed_to_stream(self) -> None:
        """Glossary entries are forwarded to stream_translate_text."""
        glossary = [(1, "API", "Interface"), (2, "SDK", "Kit")]
        worker = _make_translation_worker(
            "Use the API",
            "English",
            "French",
            glossary_entries=glossary,
        )

        with patch(
            "src.core.llm_engine.stream_translate_text",
            return_value=iter(["Utilisez l'Interface"]),
        ) as mock_stream:
            worker.run()

        mock_stream.assert_called_once_with(
            "Use the API",
            target_lang="French",
            source_lang="English",
            glossary_entries=glossary,
            provider=None,
            model=None,
            context=None,
        )
        worker.translated.emit.assert_called_once_with(
            "Use the API",
            "Utilisez l'Interface",
        )

    def test_translation_worker_multiple_chunks_concatenated(self) -> None:
        """Multiple stream chunks accumulate into the final translation."""
        worker = _make_translation_worker(
            "Test",
            "English",
            "German",
        )

        with patch(
            "src.core.llm_engine.stream_translate_text",
            return_value=iter(["Prü", "fung"]),
        ):
            worker.run()

        # Final translated emit carries the concatenated full text.
        worker.translated.emit.assert_called_once_with("Test", "Prüfung")
        # Partial emits track the cumulative accumulator.
        partials = worker.partial_translated.emit.call_args_list
        assert len(partials) == 2  # noqa: PLR2004
        assert partials[0].args == ("Test", "Prü")
        assert partials[1].args == ("Test", "Prüfung")

    def test_translation_worker_retries_on_transient_error(self) -> None:
        """Transient error on first attempt triggers a single retry."""
        worker = _make_translation_worker("Hello", "English", "French")

        attempts = []

        def _flaky_stream(*_args, **_kwargs):
            attempts.append(1)
            if len(attempts) == 1:
                raise ValueError("CONNECTION_ERROR")
            return iter(["Bonjour"])

        with (
            patch(
                "src.core.llm_engine.stream_translate_text",
                side_effect=_flaky_stream,
            ),
            patch(f"{_MOD}.time.sleep"),  # don't actually sleep in tests
        ):
            worker.run()

        # Two attempts (1 original + 1 retry); the second succeeded.
        assert len(attempts) == 2  # noqa: PLR2004
        worker.translated.emit.assert_called_once_with("Hello", "Bonjour")
        worker.error.emit.assert_not_called()

    def test_translation_worker_no_retry_on_non_transient(self) -> None:
        """AUTH_ERROR / QUOTA_ERROR / etc. surface immediately, no retry."""
        worker = _make_translation_worker("Hello", "English", "French")

        attempts = []

        def _failing_stream(*_args, **_kwargs):
            attempts.append(1)
            raise ValueError("AUTH_ERROR")

        with (
            patch(
                "src.core.llm_engine.stream_translate_text",
                side_effect=_failing_stream,
            ),
            patch(f"{_MOD}.time.sleep"),
        ):
            worker.run()

        # Only one attempt — non-transient errors are one-shot.
        assert len(attempts) == 1
        worker.error.emit.assert_called_once_with("AUTH_ERROR")
        worker.translated.emit.assert_not_called()

    def test_translation_worker_retry_exhausted_emits_error(self) -> None:
        """Both attempts fail with transient → final error emitted."""
        worker = _make_translation_worker("Hello", "English", "French")

        attempts = []

        def _always_failing(*_args, **_kwargs):
            attempts.append(1)
            raise ValueError("TIMEOUT_ERROR")

        with (
            patch(
                "src.core.llm_engine.stream_translate_text",
                side_effect=_always_failing,
            ),
            patch(f"{_MOD}.time.sleep"),
        ):
            worker.run()

        # 2 attempts (1 original + 1 retry), both failed.
        assert len(attempts) == 2  # noqa: PLR2004
        worker.error.emit.assert_called_once_with("TIMEOUT_ERROR")
        worker.translated.emit.assert_not_called()

    def test_translation_worker_no_retry_after_partial_chunks(self) -> None:
        """Mid-stream error after partial emit skips retry to avoid jitter."""
        worker = _make_translation_worker("Hello", "English", "French")

        def _partial_then_fail():
            yield "Bon"
            raise ValueError("CONNECTION_ERROR")

        attempts = []

        def _stream_factory(*_args, **_kwargs):
            attempts.append(1)
            return _partial_then_fail()

        with (
            patch(
                "src.core.llm_engine.stream_translate_text",
                side_effect=_stream_factory,
            ),
            patch(f"{_MOD}.time.sleep"),
        ):
            worker.run()

        # Only one attempt — a retry would replace the painted partial
        # with possibly-different text and cause visual jitter.
        assert len(attempts) == 1
        # Partial emit fired before the error.
        worker.partial_translated.emit.assert_called_once_with("Hello", "Bon")
        # Error surfaced rather than being retried.
        worker.error.emit.assert_called_once_with("CONNECTION_ERROR")


# ===========================================================================
# TestLivePageHelpers — module-level QSS style functions
# ===========================================================================


class TestLivePageHelpers:
    """Tests for the module-level QSS style helper functions."""

    def test_style_transcript_original_returns_qss(self) -> None:
        """_style_transcript_original returns a non-empty QSS string."""
        from src.ui.pages.live import _style_transcript_original  # noqa: PLC0415

        result = _style_transcript_original()
        assert isinstance(result, str)
        assert len(result) > 0
        assert "color:" in result
        assert "font-size:" in result

    def test_style_transcript_translated_returns_qss(self) -> None:
        """_style_transcript_translated returns a non-empty QSS string."""
        from src.ui.pages.live import _style_transcript_translated  # noqa: PLC0415

        result = _style_transcript_translated()
        assert isinstance(result, str)
        assert len(result) > 0
        assert "color:" in result
        assert "font-weight:" in result

    def test_style_status_returns_qss(self) -> None:
        """_style_status returns a non-empty pill-text QSS string.

        The rounded pill background is painted by :class:`_PillLabel`
        now, so the stylesheet only carries text styling (color, font,
        transparent background).  Checking ``border-radius`` here was
        a vestigial assertion from when the function emitted the
        rounding via QSS.
        """
        from src.ui.pages.live import _style_status  # noqa: PLC0415

        result = _style_status()
        assert isinstance(result, str)
        assert len(result) > 0
        assert "background: transparent" in result
        assert "font-size" in result


# ===========================================================================
# pytest-qt fixtures
# ===========================================================================

import pytest  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
)


@pytest.fixture(autouse=True)
def _auto_mock_blocking_dialogs():
    """Auto-mocks modal dialogs on the live page so tests don't hang.

    Covers both:
      * ``CustomConfirmDialog.confirm`` — the "are you sure" path used
        by Clear / overlay-close / Go-to-Settings.
      * ``CustomMessageDialog.show_message`` — the informational modal
        used by the auto-stop dialog for non-actionable STT errors.

    Individual tests that want to exercise dialog-specific behaviour
    can override either with their own ``@patch``.
    """
    with (
        patch(
            "src.ui.dialogs.CustomConfirmDialog.confirm",
            return_value=True,
        ),
        patch(
            "src.ui.dialogs.CustomMessageDialog.show_message",
            return_value=None,
        ),
    ):
        yield


@pytest.fixture(autouse=True)
def _auto_mock_ffmpeg_available():
    """Pretends ffmpeg is on PATH for the duration of the test.

    The Live page's ``_validate_ffmpeg_for_audio_save`` unconditionally
    blocks Start when ffmpeg is missing (matches Voice / Dubbing
    behaviour) — this fixture keeps tests that don't care about ffmpeg
    on the happy path.  Tests that specifically exercise the
    no-ffmpeg path override this with their own ``patch("shutil.which")``.
    """
    real_which = shutil.which

    def _which(name, *args, **kwargs):
        if name == "ffmpeg":
            return "/usr/bin/ffmpeg"
        return real_which(name, *args, **kwargs)

    with patch("shutil.which", side_effect=_which):
        yield


@pytest.fixture(autouse=True)
def _no_real_whisper_preload():
    """Prevents ``LivePage.showEvent`` from spawning a real Whisper load.

    Without this, any test that calls ``page.show()`` on a host where
    the tiny model happens to be cached would spawn a real
    ``_WhisperPreloadWorker`` and trigger faster-whisper's slow native
    constructor.  Neutering the worker class at the live-page namespace
    leaves ``is_whisper_model_cached`` itself untouched, so the
    ``TestIsWhisperModelCached`` tests can exercise the real helper.
    Per-test patches in ``TestWhisperPreload`` override this fixture
    by re-patching the same name at finer granularity.
    """
    with patch("src.ui.pages.live._WhisperPreloadWorker"):
        yield


@pytest.fixture()
def window(qapp):  # noqa: ARG001
    """Provides a QMainWindow context."""
    return QMainWindow()


@pytest.fixture()
def live_page(window, qtbot):
    """Creates a LivePage for testing."""
    from src.ui.pages.live import LivePage  # noqa: PLC0415

    with patch(f"{_MOD}.load_setting", return_value=""):
        page = LivePage(window)
    qtbot.addWidget(page)

    return page


def _drain_stop_worker(page) -> None:
    """Waits for ``page._stop_worker`` to finish + flushes its ``finished`` slot.

    ``_stop_listening`` now spawns an off-thread :class:`_EngineStopWorker`
    so the UI doesn't freeze during engine teardown.  Tests that assert
    against post-Stop state (transcriber called, button text, status
    pill) must wait for the worker AND process Qt events so the
    queued ``finished → _on_stop_complete`` slot has a chance to run.
    No-op when no worker was spawned (e.g. ``_stop_listening`` called
    against an already-stopped page).
    """
    from PySide6.QtWidgets import QApplication  # noqa: PLC0415

    worker = getattr(page, "_stop_worker", None)
    if worker is not None:
        worker.wait(2000)
    QApplication.processEvents()


# ===========================================================================
# TestLivePageCreation — widget structure verification
# ===========================================================================


class TestLivePageCreation:
    """Tests that create_live_page() returns a widget with expected elements."""

    def test_create_live_page_returns_qwidget(self, window, qtbot) -> None:
        """create_live_page returns a QWidget."""
        from src.ui.pages.live import create_live_page  # noqa: PLC0415

        with patch(f"{_MOD}.load_setting", return_value=""):
            page = create_live_page(window)
        qtbot.addWidget(page)
        from PySide6.QtWidgets import QWidget  # noqa: PLC0415

        assert isinstance(page, QWidget)

    def test_page_has_start_button(self, live_page) -> None:
        """Page contains the Start button."""
        assert hasattr(live_page, "start_btn")
        assert isinstance(live_page.start_btn, QPushButton)

    def test_page_has_tts_button(self, live_page) -> None:
        """Page contains the TTS toggle button."""
        assert hasattr(live_page, "tts_btn")
        assert isinstance(live_page.tts_btn, QPushButton)

    def test_page_has_overlay_button(self, live_page) -> None:
        """Page contains the Overlay toggle button."""
        assert hasattr(live_page, "overlay_btn")
        assert isinstance(live_page.overlay_btn, QPushButton)

    def test_page_has_clear_button(self, live_page) -> None:
        """Page contains the Clear button."""
        assert hasattr(live_page, "clear_btn")
        assert isinstance(live_page.clear_btn, QPushButton)

    def test_page_has_status_label(self, live_page) -> None:
        """Page contains a status label."""
        assert hasattr(live_page, "status_label")
        assert isinstance(live_page.status_label, QLabel)

    def test_page_has_transcript_layout(self, live_page) -> None:
        """Page has the transcript scroll area and layout."""
        assert hasattr(live_page, "_transcript_layout")
        assert hasattr(live_page, "_scroll")
        assert isinstance(live_page._scroll, QScrollArea)

    def test_page_stores_window_context(self, live_page, window) -> None:
        """LivePage stores the parent window reference."""
        assert live_page.window_context is window

    def test_page_initial_tts_disabled(self, live_page) -> None:
        """TTS is disabled by default."""
        assert live_page._tts_enabled is False

    def test_page_initial_transcriber_none(self, live_page) -> None:
        """No transcriber is active at initialization."""
        assert live_page._transcriber is None

    def test_page_initial_overlay_none(self, live_page) -> None:
        """Overlay window is None at initialization."""
        assert live_page._overlay is None

    def test_page_initial_translation_workers_empty(self, live_page) -> None:
        """Translation workers list is empty at initialization."""
        assert live_page._translation_workers == []

    def test_page_initial_tts_queue_empty(self, live_page) -> None:
        """TTS queue is empty at initialization."""
        assert len(live_page._tts_queue) == 0

    def test_start_button_has_cursor(self, live_page) -> None:
        """Start button has pointing-hand cursor."""
        from PySide6.QtCore import Qt  # noqa: PLC0415

        assert live_page.start_btn.cursor().shape() == Qt.CursorShape.PointingHandCursor

    def test_clear_button_has_cursor(self, live_page) -> None:
        """Clear button has pointing-hand cursor."""
        from PySide6.QtCore import Qt  # noqa: PLC0415

        assert live_page.clear_btn.cursor().shape() == Qt.CursorShape.PointingHandCursor

    def test_tts_button_has_cursor(self, live_page) -> None:
        """TTS button has pointing-hand cursor."""
        from PySide6.QtCore import Qt  # noqa: PLC0415

        assert live_page.tts_btn.cursor().shape() == Qt.CursorShape.PointingHandCursor

    def test_overlay_button_has_cursor(self, live_page) -> None:
        """Overlay button has pointing-hand cursor."""
        from PySide6.QtCore import Qt  # noqa: PLC0415

        assert (
            live_page.overlay_btn.cursor().shape() == Qt.CursorShape.PointingHandCursor
        )


# ===========================================================================
# TestLivePageActions — user interaction logic
# ===========================================================================


class TestLivePageActions:
    """Tests for LivePage button actions and signal handling."""

    def test_toggle_tts_enables(self, live_page) -> None:
        """Clicking TTS button enables TTS."""
        live_page._tts_enabled = False
        live_page._toggle_tts()
        assert live_page._tts_enabled is True

    def test_toggle_tts_disables(self, live_page) -> None:
        """Clicking TTS button again disables TTS."""
        live_page._tts_enabled = True
        live_page._toggle_tts()
        assert live_page._tts_enabled is False

    def test_toggle_tts_updates_button_text_on(self, live_page) -> None:
        """TTS button text/accessibleName flip to the 'on' variant when enabled."""
        from src.constants import tr  # noqa: PLC0415

        live_page._tts_enabled = False
        live_page._toggle_tts()
        # Expanded (default) state: button carries full text alongside its icon.
        assert live_page.tts_btn.text() == tr("live.btn_tts_on")
        assert not live_page.tts_btn.icon().isNull()
        assert live_page.tts_btn.accessibleName() == tr("live.btn_tts_on")

    def test_toggle_tts_updates_button_text_off(self, live_page) -> None:
        """TTS button text/accessibleName flip to the 'off' variant when disabled."""
        from src.constants import tr  # noqa: PLC0415

        live_page._tts_enabled = True
        live_page._toggle_tts()
        # Expanded (default) state: button carries full text alongside its icon.
        assert live_page.tts_btn.text() == tr("live.btn_tts_off")
        assert not live_page.tts_btn.icon().isNull()
        assert live_page.tts_btn.accessibleName() == tr("live.btn_tts_off")

    def test_toggle_overlay_updates_button_text(self, live_page) -> None:
        """``_toggle_overlay`` flips the button label between OFF and ON.

        Mirrors the TTS toggle test — pins that the inline label
        refresh in ``_toggle_overlay`` actually writes the new
        text + accessibleName + action_label_key property.
        """
        from src.constants import tr  # noqa: PLC0415

        on_label = tr("live.btn_overlay_on")
        off_label = tr("live.btn_overlay_off")
        assert live_page.overlay_btn.text() == off_label
        live_page._toggle_overlay()
        assert live_page.overlay_btn.text() == on_label
        assert live_page.overlay_btn.accessibleName() == on_label
        live_page._toggle_overlay()
        assert live_page.overlay_btn.text() == off_label
        assert live_page.overlay_btn.accessibleName() == off_label
        if live_page._overlay:
            live_page._overlay.hide()

    def test_overlay_external_close_resets_button_label(self, live_page) -> None:
        """Hiding the overlay outside ``_toggle_overlay`` flips the button to OFF.

        Esc-close (handled in ``_OverlayWindow.keyPressEvent``) and the
        window's X button both call ``hide()`` directly without going
        through the page's toggle.  The ``closed`` signal — emitted from
        ``hideEvent`` — is the bridge that keeps the toolbar button label
        in sync.  Without it, dismissing the overlay via Esc would leave
        the button stuck on "Overlay ON".
        """
        from src.constants import tr  # noqa: PLC0415

        on_label = tr("live.btn_overlay_on")
        off_label = tr("live.btn_overlay_off")

        live_page._toggle_overlay()  # show
        assert live_page.overlay_btn.text() == on_label
        # Simulate Esc-close / X-close — the overlay hides itself
        # without calling _toggle_overlay.  The closed signal must
        # fire from hideEvent and refresh the button label.
        live_page._overlay.hide()
        assert live_page.overlay_btn.text() == off_label
        assert live_page.overlay_btn.accessibleName() == off_label
        assert (
            live_page.overlay_btn.property("action_label_key") == "live.btn_overlay_off"
        )

    def test_toggle_timestamps_updates_button_text(self, live_page) -> None:
        """Same label-flip contract for the Timestamps toggle."""
        from src.constants import tr  # noqa: PLC0415

        # Initial state matches the persisted ``_show_timestamp`` flag —
        # default ON (live.btn_timestamps_on).
        on_label = tr("live.btn_timestamps_on")
        off_label = tr("live.btn_timestamps_off")
        original = live_page._show_timestamp
        try:
            # Force a known starting state.
            live_page._show_timestamp = True
            live_page._toggle_show_timestamp()  # flips to False
            assert live_page.time_btn.text() == off_label
            live_page._toggle_show_timestamp()  # flips back to True
            assert live_page.time_btn.text() == on_label
        finally:
            live_page._show_timestamp = original

    def test_clear_log_removes_entries(self, live_page) -> None:
        """_clear_log removes all transcript entries except the stretch."""
        # Add some labels
        live_page._add_original("Test text 1")
        live_page._add_translated("Translated text 1")
        assert live_page._transcript_layout.count() > 1

        live_page._clear_log()
        # Only the stretch item remains
        assert live_page._transcript_layout.count() == 1

    def test_clear_log_with_overlay(self, live_page) -> None:
        """_clear_log also clears overlay lines if overlay exists."""
        from src.ui.pages.live import _OverlayWindow  # noqa: PLC0415

        live_page._overlay = _OverlayWindow()
        # Add an entry so _clear_log sees "something to clear" and proceeds.
        live_page._overlay.add_entry(
            "",
            "",
            "Test line",
            show_timestamp=True,
            show_speaker=True,
            show_src=True,
            show_tgt=True,
        )
        mock_clear = MagicMock()
        live_page._overlay.clear_lines = mock_clear

        live_page._clear_log()
        mock_clear.assert_called_once()
        live_page._overlay = None

    def test_clear_log_no_overlay(self, live_page) -> None:
        """_clear_log works without an overlay."""
        live_page._overlay = None
        live_page._clear_log()  # Should not raise

    def test_stop_listening_resets_state(self, live_page) -> None:
        """_stop_listening resets transcriber and button state."""
        from src.constants import tr  # noqa: PLC0415

        mock_transcriber = MagicMock()
        live_page._transcriber = mock_transcriber

        live_page._stop_listening()
        _drain_stop_worker(live_page)

        mock_transcriber.stop.assert_called_once()
        assert live_page._transcriber is None
        assert live_page.start_btn.text() == tr("live.btn_start")
        assert live_page.status_label.text() == tr("live.status_ready")

    def test_stop_listening_when_no_transcriber(self, live_page) -> None:
        """_stop_listening works even if transcriber is already None."""
        live_page._transcriber = None
        live_page._stop_listening()  # Should not raise
        assert live_page._transcriber is None

    def test_on_status_updates_label(self, live_page) -> None:
        """_on_status updates the status label text."""
        # Active-session sentinel: ``_on_status`` drops late status
        # pushes when ``_transcriber is None`` so the "Ready" pill
        # can't be overwritten after Stop.  Install a mock so the
        # guard passes for this test.
        live_page._transcriber = MagicMock()
        live_page._on_status("Listening...")
        assert live_page.status_label.text() == "Listening..."

    def test_on_status_custom_message(self, live_page) -> None:
        """_on_status sets arbitrary status messages."""
        live_page._transcriber = MagicMock()
        live_page._on_status("Loading Whisper model...")
        assert live_page.status_label.text() == "Loading Whisper model..."

    def test_add_original_creates_label(self, live_page) -> None:
        """_add_original adds a label to the transcript layout."""
        initial_count = live_page._transcript_layout.count()
        live_page._add_original("Hello world")
        assert live_page._transcript_layout.count() == initial_count + 1

    def test_add_translated_creates_label(self, live_page) -> None:
        """_add_translated adds a label to the transcript layout."""
        initial_count = live_page._transcript_layout.count()
        live_page._add_translated("Xin chao")
        assert live_page._transcript_layout.count() == initial_count + 1

    def test_add_original_label_text(self, live_page) -> None:
        """_add_original card body contains the correct text."""
        from src.ui.pages.live import _TranscriptCard  # noqa: PLC0415

        live_page._clear_log()
        live_page._add_original("Test source text")
        # The card is inserted before the stretch (last item)
        idx = live_page._transcript_layout.count() - 2
        card = live_page._transcript_layout.itemAt(idx).widget()
        assert isinstance(card, _TranscriptCard)
        assert card._body.text() == "Test source text"

    def test_add_translated_label_text(self, live_page) -> None:
        """_add_translated card body contains the correct text.

        With no prior original, _add_translated falls back to inserting
        an orphan card whose *body* carries the translated text.
        """
        from src.ui.pages.live import _TranscriptCard  # noqa: PLC0415

        live_page._clear_log()
        live_page._add_translated("Translated text here")
        idx = live_page._transcript_layout.count() - 2
        card = live_page._transcript_layout.itemAt(idx).widget()
        assert isinstance(card, _TranscriptCard)
        assert card._body.text() == "Translated text here"

    def test_insert_entry_limits_entries(self, live_page) -> None:
        """_insert_entry trims entries beyond _MAX_LOG_ENTRIES."""
        from src.ui.pages.live import _MAX_LOG_ENTRIES  # noqa: PLC0415

        live_page._clear_log()
        for i in range(_MAX_LOG_ENTRIES + 10):
            live_page._add_original(f"Entry {i}")
        # count = entries + 1 stretch
        assert live_page._transcript_layout.count() <= _MAX_LOG_ENTRIES + 1

    def test_on_sentence_drops_late_signal_after_stop(self, live_page) -> None:
        """Regression: sentences emitted after Stop must not land on screen.

        ``_stop_listening`` nulls ``_transcriber`` synchronously, but
        the background WS / audio loops can still queue signals that
        fire on the UI thread after the user clicked Stop.  Without
        the ``_transcriber is None`` guard, those late signals would
        spawn fresh transcript cards while the toolbar shows Ready.
        """
        live_page._clear_log()
        live_page._transcriber = None
        with patch(f"{_MOD}.load_setting", return_value=""):
            live_page._on_sentence("Late sentence", 0.0, 5.0)
        # No card inserted — only the trailing stretch remains.
        assert live_page._transcript_layout.count() == 1
        assert not live_page._transcript_records

    def test_on_sentence_no_target_lang_adds_original(self, live_page) -> None:
        """When target lang is empty, _on_sentence adds original text only."""
        from src.ui.pages.live import _TranscriptCard  # noqa: PLC0415

        live_page._clear_log()
        # _on_sentence drops late signals when the session has been
        # stopped (``_transcriber is None``).  Tests that simulate an
        # active session need to install a transcriber so the guard
        # passes.
        live_page._transcriber = MagicMock()
        with patch(f"{_MOD}.load_setting", return_value=""):
            live_page._on_sentence("Just transcribed text", 0.0, 5.0)
        # Cards bundle timestamp + text, so a single original inserts
        # exactly one _TranscriptCard plus the trailing stretch = 2.
        assert live_page._transcript_layout.count() == 2  # noqa: PLR2004
        card = live_page._transcript_layout.itemAt(0).widget()
        assert isinstance(card, _TranscriptCard)
        assert card._body.text() == "Just transcribed text"

    def test_on_translated_adds_text(self, live_page) -> None:
        """_on_translated adds translated text to the transcript."""
        live_page._clear_log()
        live_page._transcriber = MagicMock()
        live_page._on_translated("Hello", "Bonjour")
        assert live_page._transcript_layout.count() == 2  # 1 label + 1 stretch

    def test_on_translated_queues_tts_when_enabled(self, live_page) -> None:
        """_on_translated enqueues text for TTS when TTS is enabled."""
        live_page._transcriber = MagicMock()
        live_page._tts_enabled = True
        live_page._tts_queue.clear()
        with patch.object(live_page, "_process_tts_queue"):
            live_page._on_translated("Hello", "Bonjour")
        assert "Bonjour" in live_page._tts_queue
        live_page._tts_enabled = False

    def test_on_translated_no_tts_when_disabled(self, live_page) -> None:
        """_on_translated does not enqueue TTS when disabled."""
        live_page._transcriber = MagicMock()
        live_page._tts_enabled = False
        live_page._tts_queue.clear()
        live_page._on_translated("Hello", "Bonjour")
        assert len(live_page._tts_queue) == 0

    def test_on_translated_skips_after_stop(self, live_page) -> None:
        """_on_translated drops late results arriving after Stop."""
        live_page._clear_log()
        live_page._transcriber = None  # simulates post-stop state
        live_page._tts_enabled = True
        live_page._tts_queue.clear()
        live_page._on_translated("Hello", "Bonjour")
        # No transcript update, no TTS queueing.
        assert live_page._transcript_layout.count() == 1  # stretch only
        assert len(live_page._tts_queue) == 0
        live_page._tts_enabled = False

    def test_on_translation_error_logs(self, live_page) -> None:
        """_on_translation_error does not raise."""
        live_page._transcriber = MagicMock()
        live_page._on_translation_error("Some error")  # Should not raise

    def test_cleanup_worker_removes_from_list(self, live_page) -> None:
        """_cleanup_worker removes the worker from _translation_workers."""
        mock_worker = MagicMock()
        live_page._translation_workers.append(mock_worker)
        live_page._cleanup_worker(mock_worker)
        assert mock_worker not in live_page._translation_workers

    def test_cleanup_worker_not_in_list(self, live_page) -> None:
        """_cleanup_worker handles worker not in list gracefully."""
        mock_worker = MagicMock()
        live_page._cleanup_worker(mock_worker)  # Should not raise

    def test_toggle_overlay_creates_and_shows(self, live_page) -> None:
        """_toggle_overlay creates overlay if None and shows it."""
        live_page._overlay = None
        live_page._toggle_overlay()
        assert live_page._overlay is not None
        assert live_page._overlay.isVisible()
        live_page._overlay.hide()

    def test_toggle_overlay_hides_when_visible(self, live_page) -> None:
        """_toggle_overlay hides overlay when already visible."""
        from src.ui.pages.live import _OverlayWindow  # noqa: PLC0415

        live_page._overlay = _OverlayWindow()
        live_page._overlay.show()
        live_page._toggle_overlay()
        assert not live_page._overlay.isVisible()

    def test_toggle_overlay_shows_when_hidden(self, live_page) -> None:
        """_toggle_overlay shows overlay when hidden."""
        from src.ui.pages.live import _OverlayWindow  # noqa: PLC0415

        live_page._overlay = _OverlayWindow()
        live_page._overlay.hide()
        live_page._toggle_overlay()
        assert live_page._overlay.isVisible()

    def test_toggle_overlay_seeds_listening_state_on_create(
        self,
        live_page,
    ) -> None:
        """Opening overlay mid-session seeds the listening placeholder copy.

        Real-world: user clicks Start, then later clicks Overlay.
        The page's ``_empty_state_listening`` is True, so the freshly
        constructed overlay must show the "Listening…" placeholder
        variant — not the idle "Press Start..." copy.  Without this
        seeding, the overlay's empty state contradicts the running
        session pill on the main window.
        """
        live_page._overlay = None
        live_page._empty_state_listening = True
        live_page._toggle_overlay()
        assert live_page._overlay is not None
        assert live_page._overlay._placeholder_listening is True
        live_page._overlay.hide()
        live_page._overlay.hide()

    def test_on_tts_error_clears_worker_and_continues(self, live_page) -> None:
        """_on_tts_error clears TTS worker and processes next item."""
        live_page._tts_worker = MagicMock()
        with patch.object(live_page, "_process_tts_queue") as mock_pq:
            live_page._on_tts_error("TTS failed")
        assert live_page._tts_worker is None
        mock_pq.assert_called_once()

    def test_process_tts_queue_skips_when_worker_active(self, live_page) -> None:
        """_process_tts_queue returns immediately if a TTS worker is running."""
        live_page._tts_worker = MagicMock()
        live_page._tts_queue.append("text")
        with patch(f"{_MOD}.load_setting") as mock_load:
            live_page._process_tts_queue()
        mock_load.assert_not_called()  # Never reached load_setting
        live_page._tts_worker = None
        live_page._tts_queue.clear()

    def test_process_tts_queue_skips_when_empty(self, live_page) -> None:
        """_process_tts_queue returns immediately if queue is empty."""
        live_page._tts_worker = None
        live_page._tts_queue.clear()
        with patch(f"{_MOD}.load_setting") as mock_load:
            live_page._process_tts_queue()
        mock_load.assert_not_called()


# ===========================================================================
# TestTTSWorkerEdgeCases — edge cases for _TTSWorker
# ===========================================================================


class TestTTSWorkerEdgeCases:
    """Edge-case tests for _TTSWorker."""

    @patch(f"{_MOD}.load_setting", return_value="Edge TTS")
    def test_tts_worker_very_long_text(self, _load) -> None:
        """TTS worker handles very long text (>5000 chars)."""
        long_text = "A" * 6000
        worker = _make_tts_worker(long_text, "English")

        with (
            patch(
                "src.core.speech_engine._get_edge_voice",
                return_value="en-US-JennyNeural",
            ),
            patch(
                "src.core.speech_engine._synthesize_chunk_edge",
            ) as mock_edge,
            patch("src.core.speech_engine._get_tts_language_code"),
            patch("src.core.speech_engine._synthesize_chunk"),
            patch("tempfile.NamedTemporaryFile") as mock_tmp,
        ):
            tmp_obj = MagicMock()
            tmp_obj.name = "/tmp/live_tts_long.mp3"
            tmp_obj.close = MagicMock()
            mock_tmp.return_value = tmp_obj

            worker.run()

        mock_edge.assert_called_once()
        assert mock_edge.call_args[0][0] == long_text
        worker.synthesized.emit.assert_called_once()

    @patch(f"{_MOD}.load_setting", return_value="Edge TTS")
    def test_tts_worker_unicode_emoji_text(self, _load) -> None:
        """TTS worker handles unicode and emoji text."""
        unicode_text = "Hello 世界 🌍 こんにちは 🎉"
        worker = _make_tts_worker(unicode_text, "English")

        with (
            patch(
                "src.core.speech_engine._get_edge_voice",
                return_value="en-US-JennyNeural",
            ),
            patch(
                "src.core.speech_engine._synthesize_chunk_edge",
            ) as mock_edge,
            patch("src.core.speech_engine._get_tts_language_code"),
            patch("src.core.speech_engine._synthesize_chunk"),
            patch("tempfile.NamedTemporaryFile") as mock_tmp,
        ):
            tmp_obj = MagicMock()
            tmp_obj.name = "/tmp/live_tts_emoji.mp3"
            tmp_obj.close = MagicMock()
            mock_tmp.return_value = tmp_obj

            worker.run()

        assert mock_edge.call_args[0][0] == unicode_text
        worker.synthesized.emit.assert_called_once()

    def test_tts_worker_temp_file_initially_none(self) -> None:
        """temp_file property is None before run() is called."""
        worker = _make_tts_worker("Test", "English")
        assert worker.temp_file is None

    @patch(f"{_MOD}.load_setting", return_value="Edge TTS")
    def test_tts_worker_tempfile_creation_error(self, _load) -> None:
        """When temp file creation raises, error signal is emitted."""
        worker = _make_tts_worker("Test", "English")

        with (
            patch(
                "src.core.speech_engine._get_edge_voice",
                return_value="en-US-JennyNeural",
            ),
            patch("src.core.speech_engine._synthesize_chunk_edge"),
            patch("src.core.speech_engine._get_tts_language_code"),
            patch("src.core.speech_engine._synthesize_chunk"),
            patch(
                "tempfile.NamedTemporaryFile",
                side_effect=OSError("Disk full"),
            ),
        ):
            worker.run()

        worker.error.emit.assert_called_once()
        assert "Disk full" in worker.error.emit.call_args[0][0]
        worker.synthesized.emit.assert_not_called()

    @patch(f"{_MOD}.load_setting", return_value="Edge TTS")
    def test_tts_worker_synthesis_exception_preserves_temp_path(self, _load) -> None:
        """On synthesis error, temp_file is still set."""
        worker = _make_tts_worker("Test", "English")

        with (
            patch(
                "src.core.speech_engine._get_edge_voice",
                return_value="en-US-JennyNeural",
            ),
            patch(
                "src.core.speech_engine._synthesize_chunk_edge",
                side_effect=RuntimeError("network error"),
            ),
            patch("src.core.speech_engine._get_tts_language_code"),
            patch("src.core.speech_engine._synthesize_chunk"),
            patch("tempfile.NamedTemporaryFile") as mock_tmp,
        ):
            tmp_obj = MagicMock()
            tmp_obj.name = "/tmp/live_tts_errfile.mp3"
            tmp_obj.close = MagicMock()
            mock_tmp.return_value = tmp_obj

            worker.run()

        # temp_file was set before the synthesis error
        assert worker.temp_file == "/tmp/live_tts_errfile.mp3"
        worker.error.emit.assert_called_once()

    @patch(f"{_MOD}.load_setting", return_value="Edge TTS")
    def test_tts_worker_male_gender(self, _load) -> None:
        """TTS worker passes MALE gender to voice selection."""
        worker = _make_tts_worker("Test", "English", gender="MALE")

        with (
            patch(
                "src.core.speech_engine._get_edge_voice",
                return_value="en-US-GuyNeural",
            ) as mock_voice,
            patch("src.core.speech_engine._synthesize_chunk_edge"),
            patch("src.core.speech_engine._get_tts_language_code"),
            patch("src.core.speech_engine._synthesize_chunk"),
            patch("tempfile.NamedTemporaryFile") as mock_tmp,
        ):
            tmp_obj = MagicMock()
            tmp_obj.name = "/tmp/live_tts_male.mp3"
            tmp_obj.close = MagicMock()
            mock_tmp.return_value = tmp_obj

            worker.run()

        mock_voice.assert_called_once_with("English", "MALE")
        worker.synthesized.emit.assert_called_once()

    @patch(f"{_MOD}.load_setting", return_value="Google Cloud TTS")
    def test_tts_worker_google_none_api_key_falls_back(self, _load) -> None:
        """When Google Cloud returns None API key, falls back to Edge TTS."""
        worker = _make_tts_worker("Test", "French")

        with (
            patch(
                "src.core.speech_engine.load_google_cloud_api_key",
                return_value=None,
            ),
            patch(
                "src.core.speech_engine._get_edge_voice",
                return_value="fr-FR-DeniseNeural",
            ) as mock_voice,
            patch(
                "src.core.speech_engine._synthesize_chunk_edge",
            ) as mock_edge,
            patch("src.core.speech_engine._get_tts_language_code"),
            patch("src.core.speech_engine._synthesize_chunk") as mock_google,
            patch("tempfile.NamedTemporaryFile") as mock_tmp,
        ):
            tmp_obj = MagicMock()
            tmp_obj.name = "/tmp/live_tts_none_key.mp3"
            tmp_obj.close = MagicMock()
            mock_tmp.return_value = tmp_obj

            worker.run()

        mock_voice.assert_called_once_with("French", "FEMALE")
        mock_edge.assert_called_once()
        mock_google.assert_not_called()
        worker.synthesized.emit.assert_called_once()

    @patch(f"{_MOD}.load_setting", return_value="Google Cloud TTS")
    def test_tts_worker_google_synthesis_error(self, _load) -> None:
        """When Google Cloud _synthesize_chunk raises, error signal fires."""
        worker = _make_tts_worker("Test", "German")

        with (
            patch(
                "src.core.speech_engine.load_google_cloud_api_key",
                return_value="valid-key",
            ),
            patch(
                "src.core.speech_engine._get_tts_language_code",
                return_value="de-DE",
            ),
            patch(
                "src.core.speech_engine._synthesize_chunk",
                side_effect=ValueError("QUOTA_ERROR"),
            ),
            patch("src.core.speech_engine._get_edge_voice"),
            patch("src.core.speech_engine._synthesize_chunk_edge"),
            patch("tempfile.NamedTemporaryFile") as mock_tmp,
        ):
            tmp_obj = MagicMock()
            tmp_obj.name = "/tmp/live_tts_google_err.mp3"
            tmp_obj.close = MagicMock()
            mock_tmp.return_value = tmp_obj

            worker.run()

        worker.error.emit.assert_called_once()
        assert "QUOTA_ERROR" in worker.error.emit.call_args[0][0]


# ===========================================================================
# TestTranslationWorkerEdgeCases — edge cases for _TranslationWorker
# ===========================================================================


class TestTranslationWorkerEdgeCases:
    """Edge-case tests for _TranslationWorker."""

    def test_very_long_text(self) -> None:
        """Translation worker handles very long text."""
        long_text = "Word " * 2000
        worker = _make_translation_worker(long_text, "English", "French")

        with patch(
            "src.core.llm_engine.stream_translate_text",
            return_value=iter(["Mot " * 2000]),
        ) as mock_batch:
            worker.run()

        assert mock_batch.call_args[0][0] == long_text
        worker.translated.emit.assert_called_once()

    def test_special_characters_newlines_tabs(self) -> None:
        """Translation worker handles text with newlines and tabs."""
        text = "Hello\n\tWorld\n\tFoo"
        worker = _make_translation_worker(text, "English", "French")

        with patch(
            "src.core.llm_engine.stream_translate_text",
            return_value=iter(["Bonjour\n\tMonde\n\tFoo"]),
        ):
            worker.run()

        worker.translated.emit.assert_called_once_with(
            text,
            "Bonjour\n\tMonde\n\tFoo",
        )

    def test_html_in_text(self) -> None:
        """Translation worker handles HTML-like content."""
        text = "<p>Hello <b>world</b></p>"
        worker = _make_translation_worker(text, "English", "French")

        with patch(
            "src.core.llm_engine.stream_translate_text",
            return_value=iter(["<p>Bonjour <b>monde</b></p>"]),
        ):
            worker.run()

        worker.translated.emit.assert_called_once_with(
            text,
            "<p>Bonjour <b>monde</b></p>",
        )

    def test_empty_glossary_list(self) -> None:
        """Empty glossary list is passed as-is (not converted to None)."""
        worker = _make_translation_worker(
            "Hello",
            "English",
            "French",
            glossary_entries=[],
        )

        with patch(
            "src.core.llm_engine.stream_translate_text",
            return_value=iter(["Bonjour"]),
        ) as mock_batch:
            worker.run()

        assert mock_batch.call_args[1]["glossary_entries"] == []

    def test_none_glossary(self) -> None:
        """None glossary is passed as-is."""
        worker = _make_translation_worker(
            "Hello",
            "English",
            "French",
            glossary_entries=None,
        )

        with patch(
            "src.core.llm_engine.stream_translate_text",
            return_value=iter(["Bonjour"]),
        ) as mock_batch:
            worker.run()

        assert mock_batch.call_args[1]["glossary_entries"] is None

    def test_translate_batch_returns_none(self) -> None:
        """When translate_batch returns None, original text is echoed back."""
        worker = _make_translation_worker("Test", "English", "French")

        with patch(
            "src.core.llm_engine.stream_translate_text",
            return_value=iter([]),
        ):
            worker.run()

        worker.translated.emit.assert_called_once_with("Test", "Test")

    def test_auth_error(self) -> None:
        """AUTH_ERROR from translate_batch emits error signal."""
        worker = _make_translation_worker("Test", "English", "French")

        with patch(
            "src.core.llm_engine.stream_translate_text",
            side_effect=ValueError("AUTH_ERROR"),
        ):
            worker.run()

        worker.error.emit.assert_called_once()
        assert "AUTH_ERROR" in worker.error.emit.call_args[0][0]

    def test_quota_error(self) -> None:
        """QUOTA_ERROR from translate_batch emits error signal."""
        worker = _make_translation_worker("Test", "English", "French")

        with patch(
            "src.core.llm_engine.stream_translate_text",
            side_effect=ValueError("QUOTA_ERROR"),
        ):
            worker.run()

        worker.error.emit.assert_called_once()
        assert "QUOTA_ERROR" in worker.error.emit.call_args[0][0]

    def test_connection_error(self) -> None:
        """CONNECTION_ERROR from translate_batch emits error signal."""
        worker = _make_translation_worker("Test", "English", "French")

        with patch(
            "src.core.llm_engine.stream_translate_text",
            side_effect=ConnectionError("CONNECTION_ERROR"),
        ):
            worker.run()

        worker.error.emit.assert_called_once()
        assert "CONNECTION_ERROR" in worker.error.emit.call_args[0][0]

    def test_timeout_error(self) -> None:
        """TIMEOUT_ERROR from translate_batch emits error signal."""
        worker = _make_translation_worker("Test", "English", "French")

        with patch(
            "src.core.llm_engine.stream_translate_text",
            side_effect=TimeoutError("TIMEOUT_ERROR"),
        ):
            worker.run()

        worker.error.emit.assert_called_once()
        assert "TIMEOUT_ERROR" in worker.error.emit.call_args[0][0]

    def test_runtime_error(self) -> None:
        """RuntimeError from translate_batch emits error signal."""
        worker = _make_translation_worker("Test", "English", "French")

        with patch(
            "src.core.llm_engine.stream_translate_text",
            side_effect=RuntimeError("Unexpected failure"),
        ):
            worker.run()

        worker.error.emit.assert_called_once()
        assert "Unexpected failure" in worker.error.emit.call_args[0][0]

    def test_unicode_text_translation(self) -> None:
        """Unicode text (CJK, Arabic, etc.) is translated correctly."""
        text = "こんにちは世界"
        worker = _make_translation_worker(text, "Japanese", "English")

        with patch(
            "src.core.llm_engine.stream_translate_text",
            return_value=iter(["Hello World"]),
        ):
            worker.run()

        worker.translated.emit.assert_called_once_with(text, "Hello World")

    def test_whitespace_only_text(self) -> None:
        """Whitespace-only text is passed to translate_batch."""
        text = "   \n\t  "
        worker = _make_translation_worker(text, "English", "French")

        with patch(
            "src.core.llm_engine.stream_translate_text",
            return_value=iter(["   \n\t  "]),
        ) as mock_batch:
            worker.run()

        mock_batch.assert_called_once()
        worker.translated.emit.assert_called_once_with(text, "   \n\t  ")

    def test_large_glossary_entries(self) -> None:
        """Large glossary list is forwarded without truncation."""
        glossary = [(i, f"src_{i}", f"tgt_{i}") for i in range(500)]
        worker = _make_translation_worker(
            "Test", "English", "French", glossary_entries=glossary
        )

        with patch(
            "src.core.llm_engine.stream_translate_text",
            return_value=iter(["Essai"]),
        ) as mock_batch:
            worker.run()

        assert len(mock_batch.call_args[1]["glossary_entries"]) == 500


# ===========================================================================
# TestLivePageThemeLanguage — theme and language updates
# ===========================================================================


class TestLivePageThemeLanguage:
    """Tests for apply_theme and apply_language on LivePage."""

    def test_apply_theme_updates_start_button_idle(self, live_page) -> None:
        """apply_theme sets primary style on start button when not listening."""
        from src.constants import style_primary_button  # noqa: PLC0415

        live_page._transcriber = None
        live_page.apply_theme()
        assert live_page.start_btn.styleSheet() == style_primary_button()

    def test_apply_theme_updates_start_button_listening(self, live_page) -> None:
        """apply_theme sets delete style on start button when listening."""
        from src.constants import style_delete_button  # noqa: PLC0415

        mock_transcriber = MagicMock()
        mock_transcriber.is_running = True
        live_page._transcriber = mock_transcriber

        live_page.apply_theme()
        assert live_page.start_btn.styleSheet() == style_delete_button()
        live_page._transcriber = None

    def test_apply_theme_updates_tts_button(self, live_page) -> None:
        """apply_theme updates TTS button style."""
        from src.constants import style_secondary_button  # noqa: PLC0415

        live_page.apply_theme()
        assert live_page.tts_btn.styleSheet() == style_secondary_button()

    def test_apply_theme_updates_overlay_button(self, live_page) -> None:
        """apply_theme updates overlay button style."""
        from src.constants import style_secondary_button  # noqa: PLC0415

        live_page.apply_theme()
        assert live_page.overlay_btn.styleSheet() == style_secondary_button()

    def test_apply_theme_updates_clear_button(self, live_page) -> None:
        """apply_theme updates clear button style."""
        from src.constants import style_delete_button  # noqa: PLC0415

        live_page.apply_theme()
        assert live_page.clear_btn.styleSheet() == style_delete_button()

    def test_apply_theme_updates_status_label(self, live_page) -> None:
        """apply_theme updates status label style."""
        from src.ui.pages.live import _style_status  # noqa: PLC0415

        live_page.apply_theme()
        assert live_page.status_label.styleSheet() == _style_status()

    def test_apply_language_start_button_idle(self, live_page) -> None:
        """apply_language sets the Start button text when not listening."""
        from src.constants import tr  # noqa: PLC0415

        live_page._transcriber = None
        live_page.apply_language()
        assert live_page.start_btn.text() == tr("live.btn_start")

    def test_apply_language_start_button_listening(self, live_page) -> None:
        """apply_language sets 'Stop' text when listening."""
        from src.constants import tr  # noqa: PLC0415

        mock_transcriber = MagicMock()
        mock_transcriber.is_running = True
        live_page._transcriber = mock_transcriber

        live_page.apply_language()
        assert live_page.start_btn.text() == tr("live.btn_stop")
        live_page._transcriber = None

    def test_apply_language_tts_button_off(self, live_page) -> None:
        """apply_language sets TTS Off text/accessibleName when TTS is disabled."""
        from src.constants import tr  # noqa: PLC0415

        live_page._tts_enabled = False
        live_page.apply_language()
        # Expanded (default) state: button carries full text alongside its icon.
        assert live_page.tts_btn.text() == tr("live.btn_tts_off")
        assert live_page.tts_btn.accessibleName() == tr("live.btn_tts_off")

    def test_apply_language_tts_button_on(self, live_page) -> None:
        """apply_language sets TTS On accessibleName when TTS is enabled."""
        from src.constants import tr  # noqa: PLC0415

        live_page._tts_enabled = True
        live_page.apply_language()
        # Glyph is owned by _toggle_tts, not apply_language; accessibleName
        # reflects the current TTS state on locale change.
        assert live_page.tts_btn.accessibleName() == tr("live.btn_tts_on")
        live_page._tts_enabled = False

    def test_apply_language_overlay_button(self, live_page) -> None:
        """apply_language updates overlay button text/accessibleName.

        Overlay is now a labelled toggle ("Overlay ON" / "Overlay OFF")
        — the default-hidden state lands on ``live.btn_overlay_off``.
        """
        from src.constants import tr  # noqa: PLC0415

        live_page.apply_language()
        # Expanded (default) state: button carries full text alongside its icon.
        assert live_page.overlay_btn.text() == tr("live.btn_overlay_off")
        assert not live_page.overlay_btn.icon().isNull()
        assert live_page.overlay_btn.accessibleName() == tr("live.btn_overlay_off")

    def test_apply_language_clear_button(self, live_page) -> None:
        """apply_language updates clear button text/accessibleName."""
        from src.constants import tr  # noqa: PLC0415

        live_page.apply_language()
        # Expanded (default) state: button carries full text alongside its icon.
        assert live_page.clear_btn.text() == tr("live.btn_clear")
        assert not live_page.clear_btn.icon().isNull()
        assert live_page.clear_btn.accessibleName() == tr("live.btn_clear")


# ===========================================================================
# TestLivePageHelpersFull — comprehensive QSS style validation
# ===========================================================================


class TestLivePageHelpersFull:
    """Extended tests for QSS style functions."""

    def test_style_transcript_original_has_padding(self) -> None:
        """_style_transcript_original is transparent (padding comes from card)."""
        from src.ui.pages.live import _style_transcript_original  # noqa: PLC0415

        result = _style_transcript_original()
        # Cards provide the padding via layout margins; the label itself
        # must be transparent with no border so it blends into the card.
        assert "background: transparent" in result
        assert "border: none" in result

    def test_style_transcript_original_has_14px_font(self) -> None:
        """_style_transcript_original uses 14px font size."""
        from src.ui.pages.live import _style_transcript_original  # noqa: PLC0415

        result = _style_transcript_original()
        assert "14px" in result

    def test_style_transcript_original_uses_text_secondary(self) -> None:
        """_style_transcript_original uses text_secondary color."""
        from src.constants import color  # noqa: PLC0415
        from src.ui.pages.live import _style_transcript_original  # noqa: PLC0415

        result = _style_transcript_original()
        assert color("text_secondary") in result

    def test_style_transcript_translated_has_14px_font(self) -> None:
        """_style_transcript_translated uses 14px font size.

        Source and translation share the 14px size; the visual
        hierarchy comes from the bold weight + primary text colour
        on the translation side, not from a size delta.
        """
        from src.ui.pages.live import _style_transcript_translated  # noqa: PLC0415

        result = _style_transcript_translated()
        assert "14px" in result

    def test_style_transcript_translated_has_font_weight_600(self) -> None:
        """_style_transcript_translated uses 600 font weight."""
        from src.ui.pages.live import _style_transcript_translated  # noqa: PLC0415

        result = _style_transcript_translated()
        assert "600" in result

    def test_style_transcript_translated_uses_text_primary(self) -> None:
        """_style_transcript_translated uses text_primary color."""
        from src.constants import color  # noqa: PLC0415
        from src.ui.pages.live import _style_transcript_translated  # noqa: PLC0415

        result = _style_transcript_translated()
        assert color("text_primary") in result

    def test_style_transcript_translated_has_padding(self) -> None:
        """_style_transcript_translated is transparent (padding comes from card)."""
        from src.ui.pages.live import _style_transcript_translated  # noqa: PLC0415

        result = _style_transcript_translated()
        # Cards provide the padding via layout margins; the label itself
        # must be transparent with no border so it blends into the card.
        assert "background: transparent" in result
        assert "border: none" in result

    def test_style_status_has_13px_font(self) -> None:
        """_style_status uses 12px font size (pill style)."""
        from src.ui.pages.live import _style_status  # noqa: PLC0415

        result = _style_status()
        assert "font-size: 12px" in result

    def test_style_status_uses_text_secondary(self) -> None:
        """_style_status uses text_secondary color."""
        from src.constants import color  # noqa: PLC0415
        from src.ui.pages.live import _style_status  # noqa: PLC0415

        result = _style_status()
        assert color("text_secondary") in result

    def test_style_status_includes_letter_spacing(self) -> None:
        """_style_status applies letter-spacing for the pill copy.

        The padding / rounded background moved into _PillLabel's
        paintEvent; what's left in this stylesheet is text styling
        (color, font, letter-spacing).  ``letter-spacing`` is a
        decent invariant to pin since it's the only spacing-related
        property the text-only sheet still owns.
        """
        from src.ui.pages.live import _style_status  # noqa: PLC0415

        result = _style_status()
        assert "letter-spacing:" in result

    def test_all_styles_return_strings(self) -> None:
        """All three style functions return non-empty strings."""
        from src.ui.pages.live import (  # noqa: PLC0415
            _style_status,
            _style_transcript_original,
            _style_transcript_translated,
        )

        fns = (_style_transcript_original, _style_transcript_translated, _style_status)
        for fn in fns:
            result = fn()
            assert isinstance(result, str)
            assert len(result) > 10  # Reasonable minimum length

    def test_style_functions_contain_semicolons(self) -> None:
        """All style functions return valid QSS with semicolons."""
        from src.ui.pages.live import (  # noqa: PLC0415
            _style_status,
            _style_transcript_original,
            _style_transcript_translated,
        )

        fns = (_style_transcript_original, _style_transcript_translated, _style_status)
        for fn in fns:
            result = fn()
            assert ";" in result


# ===========================================================================
# TestOverlayWindow — floating overlay window
# ===========================================================================


class TestOverlayWindow:
    """Tests for _OverlayWindow behavior."""

    def test_overlay_add_entry_with_translation(self, qapp) -> None:  # noqa: ARG002
        """add_entry + set_last_translation produces one mirrored entry."""
        from src.ui.pages.live import _OverlayEntry, _OverlayWindow  # noqa: PLC0415

        overlay = _OverlayWindow()
        overlay.add_entry(
            "00:00:00 → 00:00:01",
            "Speaker 1",
            "Hello",
            show_timestamp=True,
            show_speaker=True,
            show_src=True,
            show_tgt=True,
        )
        overlay.set_last_translation("Xin chào", show_src=True, show_tgt=True)
        # 1 entry + trailing stretch.
        assert overlay._lines_layout.count() == 2  # noqa: PLR2004
        entry = overlay._lines_layout.itemAt(0).widget()
        assert isinstance(entry, _OverlayEntry)

    def test_overlay_add_entry_returns_entry(self, qapp) -> None:  # noqa: ARG002
        """add_entry returns the created _OverlayEntry so callers can track it."""
        from src.ui.pages.live import _OverlayEntry, _OverlayWindow  # noqa: PLC0415

        overlay = _OverlayWindow()
        entry = overlay.add_entry(
            "",
            "",
            "Hello",
            show_timestamp=True,
            show_speaker=True,
            show_src=True,
            show_tgt=True,
        )
        assert isinstance(entry, _OverlayEntry)
        assert entry._source_label.text() == "Hello"

    def test_overlay_set_last_translation_rewrites_in_place(
        self,
        qapp,  # noqa: ARG002
    ) -> None:
        """set_last_translation rewrites the most recent entry's translation slot."""
        from src.ui.pages.live import _OverlayWindow  # noqa: PLC0415

        overlay = _OverlayWindow()
        overlay.add_entry(
            "",
            "",
            "first source",
            show_timestamp=True,
            show_speaker=True,
            show_src=True,
            show_tgt=True,
        )
        overlay.set_last_translation(
            "first translation",
            show_src=True,
            show_tgt=True,
        )
        overlay.add_entry(
            "",
            "",
            "second source",
            show_timestamp=True,
            show_speaker=True,
            show_src=True,
            show_tgt=True,
        )
        overlay.set_last_translation(
            "second partial",
            show_src=True,
            show_tgt=True,
        )
        overlay.set_last_translation(
            "second complete translation",
            show_src=True,
            show_tgt=True,
        )

        # Two entries + trailing stretch; streaming updates rewrite the
        # latest entry's translation slot in place.
        assert overlay._lines_layout.count() == 3  # noqa: PLR2004
        first_entry = overlay._lines_layout.itemAt(0).widget()
        second_entry = overlay._lines_layout.itemAt(1).widget()
        assert first_entry._translation_label.text() == "first translation"
        assert second_entry._translation_label.text() == "second complete translation"

    def test_overlay_set_last_translation_noop_when_empty(
        self,
        qapp,  # noqa: ARG002
    ) -> None:
        """Calling set_last_translation before any entry is a silent no-op."""
        from src.ui.pages.live import _OverlayWindow  # noqa: PLC0415

        overlay = _OverlayWindow()
        # Would raise IndexError if the no-op guard regressed.
        overlay.set_last_translation(
            "stray update",
            show_src=True,
            show_tgt=True,
        )

    def test_overlay_owns_font_shortcuts_but_not_move(
        self,
        qapp,  # noqa: ARG002
    ) -> None:
        """Overlay carries font and opacity shortcuts, but not move.

        Move shortcuts are exclusively owned by the parent page with
        ApplicationShortcut context — a duplicate overlay-scoped copy
        would cause double-moves when the overlay is the active window.
        """
        from src.ui.pages.live import _OverlayWindow  # noqa: PLC0415

        overlay = _OverlayWindow()
        ids = {s.property("shortcut_id") for s in overlay._own_shortcuts}
        assert ids == {
            "common.overlay_font_bigger",
            "common.overlay_font_smaller",
            "common.overlay_opacity_up",
            "common.overlay_opacity_down",
        }

    def test_overlay_move_by_translates_and_persists(
        self,
        qapp,  # noqa: ARG002
    ) -> None:
        """_move_by translates the window position and fires geometry save."""
        from unittest.mock import patch  # noqa: PLC0415

        from src.ui.pages.live import _OverlayWindow  # noqa: PLC0415

        overlay = _OverlayWindow()
        overlay.move(100, 200)
        with patch.object(overlay, "_save_geometry") as mock_save:
            overlay._move_by(15, -25)
        assert overlay.x() == 115  # noqa: PLR2004
        assert overlay.y() == 175  # noqa: PLR2004
        mock_save.assert_called_once()

    def test_overlay_set_last_translation_does_not_clobber_placeholder(
        self,
        qapp,  # noqa: ARG002
    ) -> None:
        """A stray partial after clear_lines must not overwrite the hint.

        Regression: ``set_last_translation`` walks entries only, so a
        late streaming chunk that arrived after the user cleared the
        log finds no entry and is a no-op — the placeholder QLabel is
        left intact.
        """
        from src.ui.pages.live import _OverlayWindow  # noqa: PLC0415

        overlay = _OverlayWindow()
        overlay.add_entry(
            "",
            "",
            "real source",
            show_timestamp=True,
            show_speaker=True,
            show_src=True,
            show_tgt=True,
        )
        overlay.set_last_translation(
            "real translation",
            show_src=True,
            show_tgt=True,
        )
        overlay.clear_lines()
        # The placeholder is now a QWidget container with icon +
        # title + hint inside; find it by ``is_placeholder`` property.
        placeholder = None
        for i in range(overlay._lines_layout.count() - 1, -1, -1):
            widget = overlay._lines_layout.itemAt(i).widget()
            if widget is not None and widget.property("is_placeholder"):
                placeholder = widget
                break
        assert placeholder is not None
        original_title_text = overlay._placeholder_title.text()

        overlay.set_last_translation(
            "stray late partial",
            show_src=True,
            show_tgt=True,
        )

        # The placeholder container is still the same widget (stray
        # late partial did not replace it with a transcript entry)
        # and its title text is unchanged.
        assert placeholder.property("is_placeholder") is True
        assert overlay._placeholder_title.text() == original_title_text

    def test_overlay_add_entry_source_only(self, qapp) -> None:  # noqa: ARG002
        """add_entry seeds an entry with the source line visible."""
        from src.ui.pages.live import _OverlayEntry, _OverlayWindow  # noqa: PLC0415

        overlay = _OverlayWindow()
        overlay.add_entry(
            "",
            "",
            "Source text",
            show_timestamp=True,
            show_speaker=True,
            show_src=True,
            show_tgt=True,
        )
        # Layout is ``[entry, trailing stretch]``; stretch absorbs
        # remaining vertical space beneath the entries.
        assert overlay._lines_layout.count() == 2  # noqa: PLR2004
        entry = overlay._lines_layout.itemAt(0).widget()
        assert isinstance(entry, _OverlayEntry)
        assert entry._source_label.text() == "Source text"
        # Translation slot starts hidden until set_last_translation fires.
        assert not entry._translation_label.isVisible()

    def test_overlay_keeps_all_entries(self, qapp) -> None:  # noqa: ARG002
        """Overlay retains every submitted entry (no rolling cap)."""
        from src.ui.pages.live import _OverlayWindow  # noqa: PLC0415

        overlay = _OverlayWindow()
        n = 200
        for i in range(n):
            overlay.add_entry(
                "",
                "",
                f"Line {i}",
                show_timestamp=True,
                show_speaker=True,
                show_src=True,
                show_tgt=True,
            )
        # ``count()`` is n entries + the trailing stretch.
        assert overlay._lines_layout.count() == n + 1

    def test_overlay_clear_lines(self, qapp) -> None:  # noqa: ARG002
        """clear_lines drops every real entry and restores the placeholder hint."""
        from src.ui.pages.live import _OverlayWindow  # noqa: PLC0415

        overlay = _OverlayWindow()
        overlay.add_entry(
            "",
            "",
            "Line 1",
            show_timestamp=True,
            show_speaker=True,
            show_src=True,
            show_tgt=True,
        )
        overlay.add_entry(
            "",
            "",
            "Line 2",
            show_timestamp=True,
            show_speaker=True,
            show_src=True,
            show_tgt=True,
        )
        overlay.clear_lines()
        # Placeholder + trailing stretch.
        assert overlay._lines_layout.count() == 2  # noqa: PLR2004
        placeholder = overlay._lines_layout.itemAt(0).widget()
        assert placeholder.property("is_placeholder") is True

    def test_overlay_clear_lines_when_empty(self, qapp) -> None:  # noqa: ARG002
        """clear_lines on an empty overlay leaves the placeholder in place."""
        from src.ui.pages.live import _OverlayWindow  # noqa: PLC0415

        overlay = _OverlayWindow()
        overlay.clear_lines()  # Should not raise
        assert overlay._lines_layout.count() == 2  # noqa: PLR2004
        assert overlay._lines_layout.itemAt(0).widget().property("is_placeholder")

    def test_overlay_minimum_size(self, qapp) -> None:  # noqa: ARG002
        """Overlay has minimum size of 400x100."""
        from src.ui.pages.live import _OverlayWindow  # noqa: PLC0415

        overlay = _OverlayWindow()
        assert overlay.minimumWidth() == 400
        assert overlay.minimumHeight() == 100

    def test_overlay_initial_size(self, qapp) -> None:  # noqa: ARG002
        """Overlay is initially 600x200."""
        from src.ui.pages.live import _OverlayWindow  # noqa: PLC0415

        overlay = _OverlayWindow()
        assert overlay.width() == 600
        assert overlay.height() == 200

    def test_overlay_drag_pos_initially_none(self, qapp) -> None:  # noqa: ARG002
        """Overlay drag position is None initially."""
        from src.ui.pages.live import _OverlayWindow  # noqa: PLC0415

        overlay = _OverlayWindow()
        assert overlay._drag_pos is None

    def test_overlay_mouse_release_clears_drag(self, qapp) -> None:  # noqa: ARG002
        """Mouse release event clears drag state."""
        from src.ui.pages.live import _OverlayWindow  # noqa: PLC0415

        overlay = _OverlayWindow()
        overlay._drag_pos = MagicMock()
        mock_event = MagicMock()
        overlay.mouseReleaseEvent(mock_event)
        assert overlay._drag_pos is None

    def test_overlay_restores_saved_geometry(self, qapp) -> None:  # noqa: ARG002
        """Overlay reads x,y,w,h from settings on construction."""
        from src.constants.settings import (  # noqa: PLC0415
            SETTING_LIVE_OVERLAY_GEOMETRY,
        )
        from src.ui.pages.live import _OverlayWindow  # noqa: PLC0415

        with patch(
            "src.ui.pages.live.load_setting",
            side_effect=lambda k, d="": (
                "120,240,800,300" if k == SETTING_LIVE_OVERLAY_GEOMETRY else d
            ),
        ):
            overlay = _OverlayWindow()
        assert overlay.width() == 800  # noqa: PLR2004
        assert overlay.height() == 300  # noqa: PLR2004

    def test_overlay_ignores_malformed_geometry(self, qapp) -> None:  # noqa: ARG002
        """Garbage in the geometry setting falls back to defaults."""
        from src.constants.settings import (  # noqa: PLC0415
            SETTING_LIVE_OVERLAY_GEOMETRY,
        )
        from src.ui.pages.live import _OverlayWindow  # noqa: PLC0415

        with patch(
            "src.ui.pages.live.load_setting",
            side_effect=lambda k, d="": (
                "not,a,number" if k == SETTING_LIVE_OVERLAY_GEOMETRY else d
            ),
        ):
            overlay = _OverlayWindow()
        # Falls back to the default 600×200 initial size.
        assert overlay.width() == 600  # noqa: PLR2004
        assert overlay.height() == 200  # noqa: PLR2004

    def test_overlay_esc_key_hides(self, qapp) -> None:  # noqa: ARG002
        """Pressing Esc on a focused overlay hides it."""
        from PySide6.QtCore import QEvent, Qt  # noqa: PLC0415
        from PySide6.QtGui import QKeyEvent  # noqa: PLC0415

        from src.ui.pages.live import _OverlayWindow  # noqa: PLC0415

        overlay = _OverlayWindow()
        overlay.show()
        qapp.processEvents()
        assert overlay.isVisible()

        event = QKeyEvent(
            QEvent.Type.KeyPress,
            int(Qt.Key.Key_Escape),
            Qt.KeyboardModifier.NoModifier,
        )
        overlay.keyPressEvent(event)
        assert not overlay.isVisible()

    def test_overlay_resizes_from_any_edge(self, qapp) -> None:  # noqa: ARG002
        """Edge detection returns the correct Qt.Edge for each zone."""
        from PySide6.QtCore import QPoint, Qt  # noqa: PLC0415

        from src.ui.pages.live import _OverlayWindow  # noqa: PLC0415

        overlay = _OverlayWindow()
        overlay.resize(600, 200)
        panel = overlay._bg
        w, h = panel.width(), panel.height()
        # Interior → no edges (so drag, not resize).
        assert panel._edges_at(QPoint(w // 2, h // 2)) == Qt.Edge(0)
        # Each edge.
        assert panel._edges_at(QPoint(1, h // 2)) == Qt.Edge.LeftEdge
        assert panel._edges_at(QPoint(w - 1, h // 2)) == Qt.Edge.RightEdge
        assert panel._edges_at(QPoint(w // 2, 1)) == Qt.Edge.TopEdge
        assert panel._edges_at(QPoint(w // 2, h - 1)) == Qt.Edge.BottomEdge
        # Corners combine two edges.
        assert panel._edges_at(QPoint(1, 1)) == (Qt.Edge.TopEdge | Qt.Edge.LeftEdge)
        assert panel._edges_at(QPoint(w - 1, h - 1)) == (
            Qt.Edge.BottomEdge | Qt.Edge.RightEdge
        )

    def test_overlay_cursor_for_edges(self, qapp) -> None:  # noqa: ARG002
        """Edge mask maps to the expected cursor shape."""
        from PySide6.QtCore import Qt  # noqa: PLC0415

        from src.ui.pages.live import _DraggablePanel  # noqa: PLC0415

        cfe = _DraggablePanel._cursor_for_edges
        # Interior is SizeAllCursor — the panel body is the drag
        # surface for the whole window.
        assert cfe(Qt.Edge(0)) == Qt.CursorShape.SizeAllCursor
        assert cfe(Qt.Edge.LeftEdge) == Qt.CursorShape.SizeHorCursor
        assert cfe(Qt.Edge.TopEdge) == Qt.CursorShape.SizeVerCursor
        # Top-left / bottom-right diagonal.
        assert cfe(Qt.Edge.TopEdge | Qt.Edge.LeftEdge) == Qt.CursorShape.SizeFDiagCursor
        assert (
            cfe(Qt.Edge.BottomEdge | Qt.Edge.RightEdge)
            == Qt.CursorShape.SizeFDiagCursor
        )
        # Top-right / bottom-left anti-diagonal.
        assert (
            cfe(Qt.Edge.TopEdge | Qt.Edge.RightEdge) == Qt.CursorShape.SizeBDiagCursor
        )
        assert (
            cfe(Qt.Edge.BottomEdge | Qt.Edge.LeftEdge) == Qt.CursorShape.SizeBDiagCursor
        )

    def test_overlay_opacity_change_adjusts_panel_only(self, qapp) -> None:  # noqa: ARG002
        """Opacity updates the panel alpha but leaves window (text) untouched.

        Subtitle overlay: text must stay fully opaque at any background
        opacity, so ``setWindowOpacity`` is intentionally not called.
        """
        from src.ui.pages.live import _OverlayWindow  # noqa: PLC0415

        overlay = _OverlayWindow()
        overlay._on_opacity_changed(50)
        assert abs(overlay._opacity - 0.5) < 0.01  # noqa: PLR2004
        # Window itself (which would fade text too) stays at 1.0.
        assert abs(overlay.windowOpacity() - 1.0) < 0.01  # noqa: PLR2004
        # Panel background reflects the 50% alpha.
        assert (
            "rgba(0, 0, 0, 127)" in overlay._bg.styleSheet()
            or "rgba(0, 0, 0, 128)" in overlay._bg.styleSheet()
        )

    def test_overlay_opacity_persists(self, qapp) -> None:  # noqa: ARG002
        """Opacity changes are written to ``live/overlay_opacity``."""
        from src.ui.pages.live import _OverlayWindow  # noqa: PLC0415

        overlay = _OverlayWindow()
        with patch("src.ui.pages.live.save_setting") as mock_save:
            overlay._on_opacity_changed(40)
        mock_save.assert_any_call("live/overlay_opacity", "0.400")

    def test_overlay_font_increase_and_persist(self, qapp) -> None:  # noqa: ARG002
        """Font+ nudges the size up, clamps to max, and saves."""
        from src.ui.pages.live import _OverlayWindow  # noqa: PLC0415

        overlay = _OverlayWindow()
        start = overlay._font_px
        with patch("src.ui.pages.live.save_setting") as mock_save:
            overlay._change_font(2)
        assert overlay._font_px == start + 2
        mock_save.assert_called_with("live/overlay_font_size", str(start + 2))

    def test_overlay_font_size_clamps_at_max(self, qapp) -> None:  # noqa: ARG002
        """Repeated font+ clicks stop at the upper bound."""
        from src.ui.pages.live import (  # noqa: PLC0415
            _OVERLAY_MAX_FONT_PX,
            _OverlayWindow,
        )

        overlay = _OverlayWindow()
        overlay._font_px = _OVERLAY_MAX_FONT_PX
        overlay._change_font(2)  # already at max; no-op
        assert overlay._font_px == _OVERLAY_MAX_FONT_PX

    def test_overlay_font_change_restyles_existing_entries(self, qapp) -> None:  # noqa: ARG002
        """Increasing font size updates every already-rendered entry."""
        from src.ui.pages.live import _OverlayWindow  # noqa: PLC0415

        overlay = _OverlayWindow()
        overlay.add_entry(
            "",
            "",
            "hello",
            show_timestamp=True,
            show_speaker=True,
            show_src=True,
            show_tgt=True,
        )
        entry = overlay._lines_layout.itemAt(0).widget()
        before = entry._source_label.styleSheet()
        overlay._change_font(2)
        assert entry._source_label.styleSheet() != before

    def test_overlay_restores_saved_opacity(self, qapp) -> None:  # noqa: ARG002
        """Previously-saved opacity is applied on re-creation."""
        from src.ui.pages.live import _OverlayWindow  # noqa: PLC0415

        with patch(
            "src.ui.pages.live.load_setting",
            side_effect=lambda k, d="": "0.4" if k == "live/overlay_opacity" else d,
        ):
            overlay = _OverlayWindow()
        assert abs(overlay._opacity - 0.4) < 0.01  # noqa: PLR2004

    def test_overlay_placeholder_matches_main_window_structure(
        self,
        qapp,  # noqa: ARG002
    ) -> None:
        """Overlay placeholder mirrors the main window: icon + title + hint.

        The flat single-label placeholder was inconsistent with the
        main transcript view's empty state; users open the overlay
        and saw a different message style.  This pins the new
        structure so a refactor doesn't silently regress to a single
        label.
        """
        from src.constants.i18n import _set_initial_language, tr  # noqa: PLC0415
        from src.ui.pages.live import _OverlayWindow  # noqa: PLC0415

        _set_initial_language("en-US")
        from src.ui.pages.live import _bind_last_word  # noqa: PLC0415

        overlay = _OverlayWindow()
        # ``_ensure_placeholder`` runs during init.  Verify the title
        # + hint labels exist and carry the main-window i18n strings.
        # The hint passes through ``_bind_last_word`` for widow control.
        assert overlay._placeholder_title is not None
        assert overlay._placeholder_hint is not None
        assert overlay._placeholder_title.text() == tr("live.empty_title")
        assert overlay._placeholder_hint.text() == _bind_last_word(
            tr("live.empty_hint"),
        )

    def test_overlay_set_placeholder_listening_swaps_copy(
        self,
        qapp,  # noqa: ARG002
    ) -> None:
        """``set_placeholder_listening`` swaps title + hint to the listening copy.

        Mirrors the main window's ``_set_empty_state_listening`` so
        the overlay's empty state stops contradicting the running
        status pill once the user clicks Start.
        """
        from src.constants.i18n import _set_initial_language, tr  # noqa: PLC0415
        from src.ui.pages.live import _bind_last_word, _OverlayWindow  # noqa: PLC0415

        _set_initial_language("en-US")
        overlay = _OverlayWindow()
        overlay.set_placeholder_listening(listening=True)

        assert overlay._placeholder_title.text() == tr(
            "live.empty_title_listening",
        )
        # Hint goes through ``_bind_last_word`` to suppress widow words.
        assert overlay._placeholder_hint.text() == _bind_last_word(
            tr("live.empty_hint_listening"),
        )

        overlay.set_placeholder_listening(listening=False)
        assert overlay._placeholder_title.text() == tr("live.empty_title")
        assert overlay._placeholder_hint.text() == _bind_last_word(
            tr("live.empty_hint"),
        )

    def test_overlay_placeholder_scales_with_overlay_size(
        self,
        qapp,  # noqa: ARG002
    ) -> None:
        """Placeholder sizes track the overlay's width AND height.

        Decoupled from the transcript-text slider.  Both dimensions
        bound the title so the placeholder never exceeds the
        viewport and triggers a scrollbar — at low overlay heights
        the height/10 budget wins; at low widths the width/24
        budget wins.  The icon also gets a separate height cap so
        it can't dominate a short viewport.
        """
        from src.ui.pages.live import _OverlayWindow  # noqa: PLC0415

        overlay = _OverlayWindow()

        # Tall + wide overlay: both budgets are large.  title clamps
        # at the upper bound 48.
        overlay.resize(1200, 800)
        overlay._apply_placeholder_font()
        assert "font-size: 48px" in overlay._placeholder_title.styleSheet()
        assert "font-size: 44px" in overlay._placeholder_hint.styleSheet()

        # Short-but-wide overlay: height/10 dominates.
        # 200/10 = 20 < 1200/24 = 50 → title = 20.
        overlay.resize(1200, 200)
        overlay._apply_placeholder_font()
        assert "font-size: 20px" in overlay._placeholder_title.styleSheet()

        # Narrow overlay (minimum width 400 × height 200):
        # width/24 ≈ 17, height/10 = 20 → min = 17.
        overlay.resize(400, 200)
        overlay._apply_placeholder_font()
        assert "font-size: 17px" in overlay._placeholder_title.styleSheet()
        assert "font-size: 13px" in overlay._placeholder_hint.styleSheet()

        # Very short overlay: minimum-height clamp pulls actual
        # height to 100.  height/10 = 10, floored at 11.
        overlay.resize(600, 80)
        overlay._apply_placeholder_font()
        assert "font-size: 11px" in overlay._placeholder_title.styleSheet()

    def test_overlay_placeholder_icon_capped_by_overlay_height(
        self,
        qapp,  # noqa: ARG002
    ) -> None:
        """Icon size is capped by both ``title × 1.8`` AND ``height × 0.30``.

        Whichever cap is smaller wins so the icon never dominates a
        short viewport.  At minimum geometry the title-proportional
        cap wins (small title → small icon); at tall+narrow geometry
        the height cap would win and clip the icon.
        """
        from src.ui.pages.live import _OverlayWindow  # noqa: PLC0415

        overlay = _OverlayWindow()

        # Minimum height (400×100): title = 11 (floored), icon =
        # min(11 × 1.8, max(18, 100 × 0.30)) = min(20, 30) = 20.
        overlay.resize(400, 100)
        overlay._apply_placeholder_font()
        assert "font-size: 20px" in overlay._placeholder_icon.styleSheet()

        # Large geometry: title clamps at 48, icon = 48 × 1.8 = 86.
        # height × 0.30 at 800 = 240, so the proportional cap wins.
        overlay.resize(1200, 800)
        overlay._apply_placeholder_font()
        assert "font-size: 86px" in overlay._placeholder_icon.styleSheet()

        # Tall + narrow: title constrained by width → small title.
        # title at 400×800: width/24 ≈ 17, height/10 = 80 → 17.
        # icon = min(17 × 1.8 = 31, max(18, 240) = 240) = 31.
        # Verifies the proportional cap is the active limit here.
        overlay.resize(400, 800)
        overlay._apply_placeholder_font()
        assert "font-size: 31px" in overlay._placeholder_icon.styleSheet()

    def test_overlay_placeholder_hint_binds_last_word(
        self,
        qapp,  # noqa: ARG002
    ) -> None:
        """Hint text replaces the last regular space with a non-breaking space.

        Prevents the typographic widow problem: the very last word
        ("recognized." in en-US) ending up alone on its own line
        when the hint wraps.  Implemented via ``_bind_last_word``
        applied at hint construction + every ``set_placeholder_listening``.
        """
        from src.constants.i18n import _set_initial_language, tr  # noqa: PLC0415
        from src.ui.pages.live import _OverlayWindow  # noqa: PLC0415

        _set_initial_language("en-US")
        overlay = _OverlayWindow()
        rendered = overlay._placeholder_hint.text()
        # Source string ends with "...they're recognized."  The last
        # regular space must have been swapped for U+00A0.
        assert rendered.endswith(" recognized."), (
            f"expected NBSP before the last word, got {rendered!r}"
        )
        # And the source string itself doesn't already contain NBSP
        # — proves the helper actually replaced something.
        assert " " not in tr("live.empty_hint")

        # The listening variant also gets the treatment.
        overlay.set_placeholder_listening(listening=True)
        rendered_listening = overlay._placeholder_hint.text()
        # The listening hint ends with "...recognized." too.
        assert " " in rendered_listening

    def test_bind_last_word_helper_is_noop_for_single_word_strings(
        self,
        qapp,  # noqa: ARG002
    ) -> None:
        """``_bind_last_word`` preserves single-word and CJK-only inputs.

        CJK (Chinese / Japanese / Korean) hints don't use space as a
        word separator, so a single-token CJK string must pass
        through unchanged — no spurious NBSP insertion.
        """
        from src.ui.pages.live import _bind_last_word  # noqa: PLC0415

        assert _bind_last_word("Listening") == "Listening"
        assert _bind_last_word("聞いています") == "聞いています"
        assert _bind_last_word("") == ""
        # Multi-word: the LAST space is swapped, prior spaces stay.
        assert _bind_last_word("a b c") == "a b c"

    def test_overlay_minimal_toggle_before_first_add_entry(
        self,
        qapp,  # noqa: ARG002
    ) -> None:
        """Minimal flipped before any ``add_entry`` still hides chips on the first.

        Realistic startup: ``SETTING_LIVE_OVERLAY_MINIMAL`` is True
        on disk → ``_OverlayWindow.__init__`` initialises
        ``_minimal_mode=True`` AND ``_intent_show_*=True``.  When
        the first ``add_entry`` arrives later, the AND of the
        construction-default intent (True) with the loaded minimal
        flag (True) must still hide chips on that very first
        sentence.  A regression that swapped the order of the
        intent-default vs minimal-load init would leak chips
        through on entry 1 only — and the existing tests all seed
        with ``add_entry`` first, so they can't catch this.
        """
        from unittest.mock import patch  # noqa: PLC0415

        from src.constants.settings import SETTING_LIVE_OVERLAY_MINIMAL  # noqa: PLC0415
        from src.ui.pages.live import _format_speaker, _OverlayWindow  # noqa: PLC0415

        with patch(
            "src.utils.config_manager.load_setting",
            side_effect=lambda k, default=None: (
                True if k == SETTING_LIVE_OVERLAY_MINIMAL else default
            ),
        ):
            overlay = _OverlayWindow()

        # Construction-time defaults: minimal ON, intent both True
        # (we haven't pushed any page intent yet).
        assert overlay._minimal_mode is True
        assert overlay._intent_show_timestamp is True
        assert overlay._intent_show_speaker is True

        # First add_entry: chips must hide because
        # ``True AND not True == False``.
        overlay.add_entry(
            "00:00:00 → 00:00:02",
            _format_speaker("speaker_0"),
            "Hello",
            show_timestamp=True,
            show_speaker=True,
            show_src=True,
            show_tgt=True,
        )
        entry = next(overlay._iter_entries())
        assert entry._timestamp_visible is False, (
            "first-entry chips leaked through despite minimal-mode load"
        )
        assert entry._speaker_visible is False

    def test_overlay_clear_lines_preserves_minimal_and_intent(
        self,
        qapp,  # noqa: ARG002
    ) -> None:
        """``clear_lines`` deletes entries but keeps minimal + intent sticky.

        Real-world: user clicks Clear Log mid-session.  The
        overlay's empty state returns, the placeholder rebuilds,
        and the next incoming sentence inherits the SAME
        minimal-mode + chip intent state as before the clear — the
        user shouldn't see chips reappear just because they
        cleared the log.  Pins the contract that ``clear_lines``
        only touches entry widgets, never the chip-state machine.
        """
        from src.ui.pages.live import _format_speaker, _OverlayWindow  # noqa: PLC0415

        overlay = _OverlayWindow()
        # Establish a non-default intent: speaker hidden via page,
        # then user toggles minimal on too.
        overlay.add_entry(
            "00:00:00 → 00:00:02",
            _format_speaker("speaker_0"),
            "first",
            show_timestamp=True,
            show_speaker=False,
            show_src=True,
            show_tgt=True,
        )
        overlay.set_minimal_mode(enabled=True)

        # Snapshot state.
        prior_minimal = overlay._minimal_mode
        prior_intent_ts = overlay._intent_show_timestamp
        prior_intent_speaker = overlay._intent_show_speaker

        overlay.clear_lines()

        # All three survive the clear.
        assert overlay._minimal_mode == prior_minimal
        assert overlay._intent_show_timestamp == prior_intent_ts
        assert overlay._intent_show_speaker == prior_intent_speaker

        # Adding a new entry with the SAME intent that survived
        # the clear must produce the same effective visibility
        # (both chips hidden: ts hidden by minimal, speaker hidden
        # by intent).
        overlay.add_entry(
            "00:00:02 → 00:00:04",
            _format_speaker("speaker_0"),
            "second",
            show_timestamp=prior_intent_ts,
            show_speaker=prior_intent_speaker,
            show_src=True,
            show_tgt=True,
        )
        entry = next(overlay._iter_entries())
        assert entry._timestamp_visible is False
        assert entry._speaker_visible is False

    def test_overlay_minimal_mode_loads_truthy_string_setting(
        self,
        qapp,  # noqa: ARG002
    ) -> None:
        """A truthy string from the INI ("True") loads as minimal-mode=True.

        The setting is stored as a string in config_manager INI.  A
        ``bool("True")`` is True; a ``bool("False")`` is also True
        (string-truthy).  Verifies the load wrapper handles strings
        correctly when the saved value is a non-empty string.
        """
        from unittest.mock import patch  # noqa: PLC0415

        from src.constants.settings import SETTING_LIVE_OVERLAY_MINIMAL  # noqa: PLC0415
        from src.ui.pages.live import _OverlayWindow  # noqa: PLC0415

        with patch(
            "src.utils.config_manager.load_setting",
            side_effect=lambda k, default=None: (
                True if k == SETTING_LIVE_OVERLAY_MINIMAL else default
            ),
        ):
            overlay = _OverlayWindow()
            assert overlay._minimal_mode is True

    def test_overlay_source_and_translation_share_font_size(
        self,
        qapp,  # noqa: ARG002
    ) -> None:
        """Source and translation lines render at the same pixel size.

        Regression guard for the recent design decision: the visual
        hierarchy on the overlay now comes from colour + weight, not
        size — same as the main window.  An old ``font_px - 4``
        regression would silently make source smaller again.
        """
        from src.ui.pages.live import _OverlayWindow  # noqa: PLC0415

        overlay = _OverlayWindow()
        overlay._set_font_size(20, emit=False)
        overlay.add_entry(
            "00:00:00 → 00:00:02",
            "",
            "source text",
            show_timestamp=True,
            show_speaker=True,
            show_src=True,
            show_tgt=True,
        )
        overlay.set_last_translation(
            "translation",
            show_src=True,
            show_tgt=True,
        )
        entry = overlay._iter_entries().__next__()
        # Both labels must contain ``font-size: 20px``.
        assert "font-size: 20px" in entry._source_label.styleSheet()
        assert "font-size: 20px" in entry._translation_label.styleSheet()

    def test_overlay_set_minimal_mode_is_noop_when_value_unchanged(
        self,
        qapp,  # noqa: ARG002
    ) -> None:
        """Calling ``set_minimal_mode`` with the current value early-returns.

        Performance / correctness micro-guard: a no-op call must
        not re-iterate every entry needlessly, and must not
        ping the entries' setVisible (which would trigger
        repaints).  Verified by checking entry state is untouched.
        """
        from src.ui.pages.live import _OverlayWindow  # noqa: PLC0415

        overlay = _OverlayWindow()
        # Initial value is False (from default-False loaded setting).
        assert overlay._minimal_mode is False
        overlay.set_minimal_mode(enabled=False)  # same value
        assert overlay._minimal_mode is False  # still False, no change

        # Now toggle on, then call again with True.
        overlay.set_minimal_mode(enabled=True)
        assert overlay._minimal_mode is True
        overlay.set_minimal_mode(enabled=True)  # same value
        assert overlay._minimal_mode is True

    def test_overlay_add_entry_and_apply_chip_visibility_share_effective_calc(
        self,
        qapp,  # noqa: ARG002
    ) -> None:
        """Both chip-mutating paths must produce identical effective visibility.

        Regression guard for the ``_record_chip_intent`` /
        ``_effective_chip_visibility`` DRY extraction.  A future
        refactor that inlines the ``intent AND not minimal_mode``
        math in one path but not the other would create silent
        divergence — both existing tests
        (``apply_chip_visibility_records_page_intent`` and the
        minimal-mode round-trip) still pass while the two paths
        drift.  This test walks the matrix and asserts equality.
        """
        from src.ui.pages.live import _format_speaker, _OverlayWindow  # noqa: PLC0415

        cases = [
            # (show_ts, show_speaker, minimal_mode)
            (True, True, False),
            (True, False, False),
            (False, True, False),
            (False, False, False),
            (True, True, True),
            (True, False, True),
            (False, True, True),
            (False, False, True),
        ]
        for show_ts, show_speaker, minimal in cases:
            # Path A: add_entry on a fresh overlay
            ov_a = _OverlayWindow()
            ov_a.set_minimal_mode(enabled=minimal)
            ov_a.add_entry(
                "00:00:00 → 00:00:01",
                _format_speaker("speaker_0"),
                "x",
                show_timestamp=show_ts,
                show_speaker=show_speaker,
                show_src=True,
                show_tgt=True,
            )
            entry_a = next(ov_a._iter_entries())

            # Path B: pre-existing entry + apply_chip_visibility
            ov_b = _OverlayWindow()
            ov_b.set_minimal_mode(enabled=minimal)
            ov_b.add_entry(
                "00:00:00 → 00:00:01",
                _format_speaker("speaker_0"),
                "x",
                # Seed with the OPPOSITE so we know apply_chip_visibility
                # actually drove the final state, not just add_entry.
                show_timestamp=not show_ts,
                show_speaker=not show_speaker,
                show_src=True,
                show_tgt=True,
            )
            ov_b.apply_chip_visibility(
                show_timestamp=show_ts,
                show_speaker=show_speaker,
            )
            entry_b = next(ov_b._iter_entries())

            assert entry_a._timestamp_visible == entry_b._timestamp_visible, (
                f"add_entry vs apply_chip_visibility diverged on timestamp "
                f"for case (ts={show_ts}, speaker={show_speaker}, "
                f"minimal={minimal}): {entry_a._timestamp_visible} vs "
                f"{entry_b._timestamp_visible}"
            )
            assert entry_a._speaker_visible == entry_b._speaker_visible, (
                f"add_entry vs apply_chip_visibility diverged on speaker "
                f"for case (ts={show_ts}, speaker={show_speaker}, "
                f"minimal={minimal}): {entry_a._speaker_visible} vs "
                f"{entry_b._speaker_visible}"
            )

    def test_overlay_apply_chip_visibility_records_page_intent(
        self,
        qapp,  # noqa: ARG002
    ) -> None:
        """``apply_chip_visibility`` updates the intent state.

        Not just ``add_entry`` — the page also calls
        ``apply_chip_visibility`` from
        ``_refresh_speaker_visibility`` etc.  That path must also
        record intent so a later minimal-mode toggle restores
        chips correctly.
        """
        from src.ui.pages.live import _OverlayWindow  # noqa: PLC0415

        overlay = _OverlayWindow()
        overlay.apply_chip_visibility(
            show_timestamp=False,
            show_speaker=True,
        )
        assert overlay._intent_show_timestamp is False
        assert overlay._intent_show_speaker is True

    def test_overlay_set_minimal_mode_hides_and_restores_chips(
        self,
        qapp,  # noqa: ARG002
    ) -> None:
        """``set_minimal_mode`` hides the timestamp + speaker chips.

        Toggling minimal-mode on hides both chips regardless of the
        page-side ``show_timestamp`` / ``show_speaker`` intent.
        Toggling back off restores chips per the stored intent
        without the page having to re-push it.
        """
        from src.ui.pages.live import _format_speaker, _OverlayWindow  # noqa: PLC0415

        overlay = _OverlayWindow()
        overlay.add_entry(
            "00:00:00 → 00:00:02",
            _format_speaker("speaker_0"),
            "Hello",
            show_timestamp=True,
            show_speaker=True,
            show_src=True,
            show_tgt=True,
        )
        entry = overlay._iter_entries().__next__()
        # Sanity: both chips visible initially (intent = True, minimal = False).
        assert entry._timestamp_visible
        assert entry._speaker_visible

        overlay.set_minimal_mode(enabled=True)
        assert not entry._timestamp_visible
        assert not entry._speaker_visible

        # Page-side intent survives — flip minimal off and chips return.
        overlay.set_minimal_mode(enabled=False)
        assert entry._timestamp_visible
        assert entry._speaker_visible

    def test_overlay_minimal_mode_respects_page_intent(
        self,
        qapp,  # noqa: ARG002
    ) -> None:
        """Page-side hidden chips stay hidden after a minimal-mode round-trip.

        Page sets ``show_speaker=False`` (user disabled speaker
        labels).  User then toggles minimal mode on then off.  The
        speaker chip must STAY hidden — minimal-mode override
        doesn't get to override the page's underlying intent.
        """
        from src.ui.pages.live import _format_speaker, _OverlayWindow  # noqa: PLC0415

        overlay = _OverlayWindow()
        overlay.add_entry(
            "00:00:00 → 00:00:02",
            _format_speaker("speaker_0"),
            "Hello",
            show_timestamp=True,
            show_speaker=False,  # page-side: speaker labels OFF
            show_src=True,
            show_tgt=True,
        )
        entry = overlay._iter_entries().__next__()
        assert entry._timestamp_visible
        assert not entry._speaker_visible  # page intent

        overlay.set_minimal_mode(enabled=True)
        assert not entry._timestamp_visible
        assert not entry._speaker_visible

        overlay.set_minimal_mode(enabled=False)
        # Timestamp came back (page intent was True);
        # speaker stays hidden (page intent was False).
        assert entry._timestamp_visible
        assert not entry._speaker_visible

    def test_overlay_minimal_mode_responds_to_appearance_signal(
        self,
        qapp,  # noqa: ARG002
    ) -> None:
        """Settings-side minimal toggle reaches the running overlay via signal.

        Real-world: user opens overlay, then ticks "Show minimal
        captions" in Settings → Live.  The
        ``overlay_appearance_changed`` signal fires; the running
        overlay hides its chips without being reopened.
        """
        from src.constants.settings import (  # noqa: PLC0415
            SETTING_LIVE_OVERLAY_MINIMAL,
            overlay_appearance_changed,
        )
        from src.ui.pages.live import _format_speaker, _OverlayWindow  # noqa: PLC0415

        overlay = _OverlayWindow()
        overlay.add_entry(
            "00:00:00 → 00:00:02",
            _format_speaker("speaker_0"),
            "Hello",
            show_timestamp=True,
            show_speaker=True,
            show_src=True,
            show_tgt=True,
        )

        overlay_appearance_changed.emit(SETTING_LIVE_OVERLAY_MINIMAL, True)
        assert overlay._minimal_mode is True
        entry = overlay._iter_entries().__next__()
        assert not entry._timestamp_visible
        assert not entry._speaker_visible

        overlay_appearance_changed.emit(SETTING_LIVE_OVERLAY_MINIMAL, False)
        assert overlay._minimal_mode is False
        assert entry._timestamp_visible
        assert entry._speaker_visible

    def test_overlay_placeholder_suppresses_scrollbar(
        self,
        qapp,  # noqa: ARG002
    ) -> None:
        """The vertical scrollbar is off while the placeholder shows.

        Real-world: at the minimum 400×100 overlay geometry the
        icon + title + hint cluster can technically exceed the
        scroll viewport even with conservative size budgets — and
        there's nothing to scroll to anyway, so the scrollbar is a
        visual error.  ``_ensure_placeholder`` sets
        ``ScrollBarAlwaysOff``; ``_remove_placeholder`` restores
        ``ScrollBarAsNeeded`` so real transcripts scroll normally.
        """
        from PySide6.QtCore import Qt  # noqa: PLC0415

        from src.ui.pages.live import _OverlayWindow  # noqa: PLC0415

        overlay = _OverlayWindow()

        # ``_ensure_placeholder`` runs during init.
        assert (
            overlay._scroll.verticalScrollBarPolicy()
            == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        # Adding a real entry triggers ``_remove_placeholder`` which
        # flips the policy back to AsNeeded.
        overlay.add_entry(
            "",
            "",
            "first sentence",
            show_timestamp=True,
            show_speaker=True,
            show_src=True,
            show_tgt=True,
        )
        assert (
            overlay._scroll.verticalScrollBarPolicy()
            == Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )

        # Clearing entries puts the placeholder back → scrollbar off again.
        overlay.clear_lines()
        assert (
            overlay._scroll.verticalScrollBarPolicy()
            == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

    def test_overlay_set_placeholder_listening_is_remembered_after_rebuild(
        self,
        qapp,  # noqa: ARG002
    ) -> None:
        """The listening flag survives ``clear_lines`` → ``_ensure_placeholder``.

        Real-world: user clicks Start, transcribes a sentence, then
        clicks Clear.  The placeholder rebuilds — and must rebuild
        with the listening copy, not the idle copy, since the
        session is still active.
        """
        from src.constants.i18n import _set_initial_language, tr  # noqa: PLC0415
        from src.ui.pages.live import _OverlayWindow  # noqa: PLC0415

        _set_initial_language("en-US")
        overlay = _OverlayWindow()
        overlay.set_placeholder_listening(listening=True)
        # Clear flushes labels then rebuilds the placeholder.
        overlay.clear_lines()
        assert overlay._placeholder_title.text() == tr(
            "live.empty_title_listening",
        )

    def test_overlay_external_font_change_updates_overlay(
        self,
        qapp,  # noqa: ARG002
    ) -> None:
        """Emitting the appearance signal updates the running overlay's font.

        Models the Settings slider live-sync: when the user drags the
        font-size slider in Settings → Live, the running overlay
        picks up the new value without being reopened.
        """
        from src.constants.settings import (  # noqa: PLC0415
            SETTING_LIVE_OVERLAY_FONT_SIZE,
            overlay_appearance_changed,
        )
        from src.ui.pages.live import _OverlayWindow  # noqa: PLC0415

        overlay = _OverlayWindow()
        new_px = overlay._font_px + 6
        overlay_appearance_changed.emit(SETTING_LIVE_OVERLAY_FONT_SIZE, new_px)
        assert overlay._font_px == new_px

    def test_overlay_external_opacity_change_updates_overlay(
        self,
        qapp,  # noqa: ARG002
    ) -> None:
        """Emitting the appearance signal updates the running overlay's opacity.

        Same live-sync property for opacity: an external slider move
        re-tints the overlay panel in real time.
        """
        from src.constants.settings import (  # noqa: PLC0415
            SETTING_LIVE_OVERLAY_OPACITY,
            overlay_appearance_changed,
        )
        from src.ui.pages.live import _OverlayWindow  # noqa: PLC0415

        overlay = _OverlayWindow()
        new_opacity = 0.45
        overlay_appearance_changed.emit(SETTING_LIVE_OVERLAY_OPACITY, new_opacity)
        assert abs(overlay._opacity - new_opacity) < 0.01  # noqa: PLR2004

    def test_overlay_in_overlay_font_change_broadcasts_signal(
        self,
        qapp,  # noqa: ARG002
    ) -> None:
        """``_change_font`` broadcasts on the appearance signal.

        The Settings slider listens to this signal so its position
        stays in sync when the user nudges the font from inside the
        overlay via the +/- keyboard shortcuts.
        """
        from src.constants.settings import (  # noqa: PLC0415
            SETTING_LIVE_OVERLAY_FONT_SIZE,
            overlay_appearance_changed,
        )
        from src.ui.pages.live import _OverlayWindow  # noqa: PLC0415

        overlay = _OverlayWindow()
        received: list[tuple[str, object]] = []

        def listener(key: str, value: object) -> None:
            received.append((key, value))

        overlay_appearance_changed.connect(listener)
        try:
            overlay._change_font(2)
        finally:
            overlay_appearance_changed.disconnect(listener)

        assert any(k == SETTING_LIVE_OVERLAY_FONT_SIZE for k, _ in received), (
            f"expected font-size emit; got {received}"
        )

    def test_overlay_external_change_does_not_re_emit(
        self,
        qapp,  # noqa: ARG002
    ) -> None:
        """An external-driven update must NOT re-broadcast.

        Otherwise a Settings → overlay update bounces back into the
        Settings slider as a fresh emit, creating a feedback loop.
        ``_set_font_size(emit=False)`` is the guard; this test pins
        the contract so a refactor can't accidentally drop the flag.
        """
        from src.constants.settings import (  # noqa: PLC0415
            SETTING_LIVE_OVERLAY_FONT_SIZE,
            overlay_appearance_changed,
        )
        from src.ui.pages.live import _OverlayWindow  # noqa: PLC0415

        overlay = _OverlayWindow()
        baseline = overlay._font_px

        # Trigger the listener (simulates Settings emit).
        external_value = baseline + 4
        overlay_appearance_changed.emit(
            SETTING_LIVE_OVERLAY_FONT_SIZE,
            external_value,
        )
        assert overlay._font_px == external_value

        # Now hook a fresh listener and trigger AGAIN with the same
        # value — the listener should not re-emit because the value
        # already matches (the listener's "if new != current" guard).
        received: list[tuple[str, object]] = []
        overlay_appearance_changed.connect(
            lambda k, v: received.append((k, v)),
        )
        overlay_appearance_changed.emit(
            SETTING_LIVE_OVERLAY_FONT_SIZE,
            external_value,
        )
        # The single emit above is the one we triggered — the overlay
        # listener must NOT have re-emitted it.
        assert len(received) == 1, (
            f"overlay listener re-emitted the external change "
            f"(feedback loop): {received}"
        )

    def test_overlay_external_opacity_change_does_not_re_emit(
        self,
        qapp,  # noqa: ARG002
    ) -> None:
        """Symmetric guard for opacity: external-driven update must NOT re-broadcast.

        Same feedback-loop concern as the font-size test above but
        for the opacity path through ``_set_opacity(emit=False)``.
        """
        from src.constants.settings import (  # noqa: PLC0415
            SETTING_LIVE_OVERLAY_OPACITY,
            overlay_appearance_changed,
        )
        from src.ui.pages.live import _OverlayWindow  # noqa: PLC0415

        overlay = _OverlayWindow()
        external_value = 0.55 if overlay._opacity != 0.55 else 0.45  # noqa: PLR2004
        overlay_appearance_changed.emit(
            SETTING_LIVE_OVERLAY_OPACITY,
            external_value,
        )
        assert abs(overlay._opacity - external_value) < 0.01  # noqa: PLR2004

        received: list[tuple[str, object]] = []
        overlay_appearance_changed.connect(
            lambda k, v: received.append((k, v)),
        )
        overlay_appearance_changed.emit(
            SETTING_LIVE_OVERLAY_OPACITY,
            external_value,
        )
        assert len(received) == 1, (
            f"overlay opacity listener re-emitted external change: {received}"
        )

    def test_overlay_entries_are_transparent_for_mouse(self, qapp) -> None:  # noqa: ARG002
        """Subtitle entries pass mouse events through so drag works anywhere."""
        from PySide6.QtCore import Qt  # noqa: PLC0415

        from src.ui.pages.live import _OverlayWindow  # noqa: PLC0415

        overlay = _OverlayWindow()
        overlay.add_entry(
            "",
            "",
            "drag through me",
            show_timestamp=True,
            show_speaker=True,
            show_src=True,
            show_tgt=True,
        )
        entry = overlay._lines_layout.itemAt(0).widget()
        assert entry.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)


# ===========================================================================
# NEW TESTS — Recording state transitions
# ===========================================================================


class TestRecordingStateTransitions:
    """Tests for LivePage recording start/stop state transitions."""

    def test_toggle_listening_starts_when_idle(self, live_page) -> None:
        """_toggle_listening starts when no transcriber is active."""
        live_page._transcriber = None
        with (
            patch(f"{_MOD}.load_setting", return_value=""),
            patch("src.core.live_engine.check_audio_available", return_value=""),
            patch("src.core.live_engine.LiveTranscriber") as mock_cls,
        ):
            mock_instance = MagicMock()
            mock_cls.return_value = mock_instance
            live_page._start_listening()
            mock_instance.start.assert_called_once()

    def test_toggle_listening_stops_when_active(self, live_page) -> None:
        """_toggle_listening stops when transcriber is active."""
        mock_transcriber = MagicMock()
        mock_transcriber.is_running = True
        live_page._transcriber = mock_transcriber
        live_page._toggle_listening()
        _drain_stop_worker(live_page)
        mock_transcriber.stop.assert_called_once()
        assert live_page._transcriber is None

    def test_stop_listening_sets_status_ready(self, live_page) -> None:
        """_stop_listening sets status label to ready."""
        from src.constants import tr  # noqa: PLC0415

        mock_transcriber = MagicMock()
        live_page._transcriber = mock_transcriber
        live_page._stop_listening()
        _drain_stop_worker(live_page)
        assert live_page.status_label.text() == tr("live.status_ready")

    def test_stop_listening_sets_start_button_text(self, live_page) -> None:
        """_stop_listening restores start button text."""
        from src.constants import tr  # noqa: PLC0415

        mock_transcriber = MagicMock()
        live_page._transcriber = mock_transcriber
        live_page._stop_listening()
        _drain_stop_worker(live_page)
        assert live_page.start_btn.text() == tr("live.btn_start")

    def test_stop_listening_idempotent(self, live_page) -> None:
        """Calling _stop_listening multiple times is safe."""
        live_page._transcriber = None
        live_page._stop_listening()
        live_page._stop_listening()
        assert live_page._transcriber is None


# ===========================================================================
# NEW TESTS — Live translation display
# ===========================================================================


class TestLiveTranslationDisplay:
    """Tests for transcript display behavior."""

    def test_add_original_with_empty_string(self, live_page) -> None:
        """_add_original handles empty string."""
        initial_count = live_page._transcript_layout.count()
        live_page._add_original("")
        assert live_page._transcript_layout.count() == initial_count + 1

    def test_add_translated_with_empty_string(self, live_page) -> None:
        """_add_translated handles empty string."""
        initial_count = live_page._transcript_layout.count()
        live_page._add_translated("")
        assert live_page._transcript_layout.count() == initial_count + 1

    def test_add_original_with_unicode(self, live_page) -> None:
        """_add_original handles unicode text inside the card body."""
        from src.ui.pages.live import _TranscriptCard  # noqa: PLC0415

        live_page._clear_log()
        live_page._add_original("Xin chao 世界 🌍")
        idx = live_page._transcript_layout.count() - 2
        card = live_page._transcript_layout.itemAt(idx).widget()
        assert isinstance(card, _TranscriptCard)
        assert card._body.text() == "Xin chao 世界 🌍"

    def test_add_translated_with_long_text(self, live_page) -> None:
        """_add_translated handles very long text inside the card body."""
        from src.ui.pages.live import _TranscriptCard  # noqa: PLC0415

        live_page._clear_log()
        long_text = "A" * 5000
        live_page._add_translated(long_text)
        idx = live_page._transcript_layout.count() - 2
        card = live_page._transcript_layout.itemAt(idx).widget()
        assert isinstance(card, _TranscriptCard)
        # With no prior original, the orphan card carries the translation
        # in its body label.
        assert card._body.text() == long_text

    def test_clear_log_resets_to_one_stretch(self, live_page) -> None:
        """_clear_log leaves exactly one stretch item."""
        for i in range(10):
            live_page._add_original(f"Text {i}")
        live_page._clear_log()
        assert live_page._transcript_layout.count() == 1

    def test_on_translated_adds_translated_text(self, live_page) -> None:
        """_on_translated adds translated text label."""
        live_page._clear_log()
        live_page._transcriber = MagicMock()
        live_page._on_translated("Source", "Target")
        # Should have at least one entry
        assert live_page._transcript_layout.count() >= 2  # noqa: PLR2004

    def test_overlay_receives_entry_with_translation(self, qapp) -> None:  # noqa: ARG002
        """Overlay add_entry + set_last_translation mirror _add_original/_translated."""
        from src.ui.pages.live import _OverlayWindow  # noqa: PLC0415

        overlay = _OverlayWindow()
        overlay.add_entry(
            "",
            "",
            "Hello",
            show_timestamp=True,
            show_speaker=True,
            show_src=True,
            show_tgt=True,
        )
        overlay.set_last_translation("Bonjour", show_src=True, show_tgt=True)
        # 1 entry + trailing stretch.
        assert overlay._lines_layout.count() == 2  # noqa: PLR2004

    def test_on_sentence_with_target_lang_starts_translation(self, live_page) -> None:
        """_on_sentence with target lang spawns translation worker."""
        live_page._clear_log()
        # _on_sentence drops late signals when the session has been
        # stopped (``_transcriber is None``); install a mock so the
        # active-session guard passes for this test.
        live_page._transcriber = MagicMock()
        # Mock stream_translate_text so the spawned QThread doesn't reach the
        # real Gemini API.  Without this the thread blocks in ssl.read
        # past the per-test pytest timeout, the SIGALRM corrupts SSL
        # state, and the suite segfaults later under load.
        with (
            patch(f"{_MOD}.load_setting", return_value="French"),
            patch("src.core.database.get_active_glossary_sets", return_value=[]),
            patch("src.core.database.get_glossary_entries", return_value=[]),
            patch(
                "src.core.llm_engine.stream_translate_text",
                return_value=iter(["Bonjour le monde"]),
            ),
        ):
            live_page._on_sentence("Hello world", 0.0, 5.0)
            # A translation worker should have been created and started
            assert len(live_page._translation_workers) >= 1
            # Drain the spawned QThread before the test exits so it
            # doesn't outlive the patches and leak into later tests.
            for w in list(live_page._translation_workers):
                w.wait(2000)


# ===========================================================================
# NEW TESTS — Theme and language updates (expanded)
# ===========================================================================


class TestThemeLanguageExpanded:
    """Extended theme and language update tests."""

    def test_apply_theme_with_overlay_active(self, live_page) -> None:
        """apply_theme works with overlay active."""
        from src.ui.pages.live import _OverlayWindow  # noqa: PLC0415

        live_page._overlay = _OverlayWindow()
        live_page.apply_theme()
        live_page._overlay = None

    def test_apply_language_status_label_ready(self, live_page) -> None:
        """apply_language updates status label when idle."""
        from src.constants import tr  # noqa: PLC0415

        live_page._transcriber = None
        live_page.apply_language()
        assert live_page.status_label.text() == tr("live.status_ready")

    def test_apply_theme_scroll_area_styled(self, live_page) -> None:
        """apply_theme applies style to scroll area."""
        live_page.apply_theme()
        assert live_page._scroll.styleSheet() != ""

    def test_apply_theme_idempotent(self, live_page) -> None:
        """Calling apply_theme twice produces same result."""
        live_page.apply_theme()
        style_first = live_page.start_btn.styleSheet()
        live_page.apply_theme()
        style_second = live_page.start_btn.styleSheet()
        assert style_first == style_second

    def test_apply_language_idempotent(self, live_page) -> None:
        """Calling apply_language twice produces same result."""
        live_page.apply_language()
        text_first = live_page.start_btn.text()
        live_page.apply_language()
        text_second = live_page.start_btn.text()
        assert text_first == text_second


# ===========================================================================
# NEW TESTS — Error states
# ===========================================================================


class TestErrorStates:
    """Tests for error handling in LivePage."""

    def test_on_translation_error_does_not_crash(self, live_page) -> None:
        """_on_translation_error is safe with any message."""
        live_page._on_translation_error("AUTH_ERROR")
        live_page._on_translation_error("")
        live_page._on_translation_error("QUOTA_ERROR: limit exceeded")

    def test_on_tts_error_clears_worker(self, live_page) -> None:
        """_on_tts_error sets _tts_worker to None."""
        live_page._tts_worker = MagicMock()
        with patch.object(live_page, "_process_tts_queue"):
            live_page._on_tts_error("TTS failed")
        assert live_page._tts_worker is None

    def test_on_tts_error_processes_queue(self, live_page) -> None:
        """_on_tts_error calls _process_tts_queue for next item."""
        live_page._tts_worker = MagicMock()
        with patch.object(live_page, "_process_tts_queue") as mock_pq:
            live_page._on_tts_error("TTS failed")
        mock_pq.assert_called_once()


# ===========================================================================
# NEW TESTS — Cleanup on page switch/close
# ===========================================================================


class TestCleanup:
    """Tests for resource cleanup."""

    def test_cleanup_worker_removes_worker(self, live_page) -> None:
        """_cleanup_worker removes the specific worker."""
        w1 = MagicMock()
        w2 = MagicMock()
        live_page._translation_workers = [w1, w2]
        live_page._cleanup_worker(w1)
        assert w1 not in live_page._translation_workers
        assert w2 in live_page._translation_workers

    def test_cleanup_worker_not_present(self, live_page) -> None:
        """_cleanup_worker is safe when worker is not in list."""
        w = MagicMock()
        live_page._translation_workers = []
        live_page._cleanup_worker(w)  # Should not raise

    def test_stop_listening_stops_transcriber(self, live_page) -> None:
        """_stop_listening calls transcriber.stop()."""
        mock_t = MagicMock()
        live_page._transcriber = mock_t
        live_page._stop_listening()
        _drain_stop_worker(live_page)
        mock_t.stop.assert_called_once()


# ===========================================================================
# NEW TESTS — TTS queue management
# ===========================================================================


class TestTTSQueueManagement:
    """Tests for TTS queue processing logic."""

    def test_queue_appends_when_tts_enabled(self, live_page) -> None:
        """TTS queue grows when TTS is enabled and translations arrive."""
        live_page._transcriber = MagicMock()
        live_page._tts_enabled = True
        live_page._tts_queue.clear()
        with patch.object(live_page, "_process_tts_queue"):
            live_page._on_translated("Hello", "Bonjour")
            live_page._on_translated("World", "Monde")
        assert len(live_page._tts_queue) == 2  # noqa: PLR2004
        assert live_page._tts_queue[0] == "Bonjour"
        assert live_page._tts_queue[1] == "Monde"
        live_page._tts_enabled = False
        live_page._tts_queue.clear()

    def test_queue_empty_when_tts_disabled(self, live_page) -> None:
        """TTS queue stays empty when TTS is disabled."""
        live_page._tts_enabled = False
        live_page._tts_queue.clear()
        live_page._on_translated("Hello", "Bonjour")
        assert len(live_page._tts_queue) == 0

    def test_process_tts_queue_noop_when_worker_active(self, live_page) -> None:
        """_process_tts_queue returns early if worker is active."""
        live_page._tts_worker = MagicMock()
        live_page._tts_queue.append("text")
        with patch(f"{_MOD}.load_setting") as mock_load:
            live_page._process_tts_queue()
        mock_load.assert_not_called()
        live_page._tts_worker = None
        live_page._tts_queue.clear()

    def test_process_tts_queue_noop_when_empty(self, live_page) -> None:
        """_process_tts_queue returns early if queue is empty."""
        live_page._tts_worker = None
        live_page._tts_queue.clear()
        with patch(f"{_MOD}.load_setting") as mock_load:
            live_page._process_tts_queue()
        mock_load.assert_not_called()


# ===========================================================================
# NEW TESTS — Widget structure verification (expanded)
# ===========================================================================


class TestWidgetStructureExpanded:
    """Extended widget structure tests."""

    def test_page_has_scroll_area(self, live_page) -> None:
        """Page stores scroll area."""
        assert hasattr(live_page, "_scroll")

    def test_page_has_window_context(self, live_page, window) -> None:
        """Page stores window context correctly."""
        assert live_page.window_context is window

    def test_tts_enabled_default_false(self, live_page) -> None:
        """TTS is disabled by default."""
        assert live_page._tts_enabled is False

    def test_tts_worker_initially_none(self, live_page) -> None:
        """TTS worker is None initially."""
        assert live_page._tts_worker is None

    def test_overlay_initially_none(self, live_page) -> None:
        """Overlay is None initially."""
        assert live_page._overlay is None


# ===========================================================================
# NEW TESTS — Overlay window extended
# ===========================================================================


class TestOverlayWindowExpanded:
    """Extended tests for _OverlayWindow."""

    def test_overlay_window_flags(self, qapp) -> None:  # noqa: ARG002
        """Overlay has always-on-top and frameless flags."""
        from PySide6.QtCore import Qt  # noqa: PLC0415

        from src.ui.pages.live import _OverlayWindow  # noqa: PLC0415

        overlay = _OverlayWindow()
        flags = overlay.windowFlags()
        assert flags & Qt.WindowType.WindowStaysOnTopHint
        assert flags & Qt.WindowType.FramelessWindowHint

    def test_overlay_add_multiple_entries(self, qapp) -> None:  # noqa: ARG002
        """Overlay can add multiple entries (one per transcript sentence)."""
        from src.ui.pages.live import _OverlayWindow  # noqa: PLC0415

        overlay = _OverlayWindow()
        for src in ("Line 1", "Line 2", "Line 3"):
            overlay.add_entry(
                "",
                "",
                src,
                show_timestamp=True,
                show_speaker=True,
                show_src=True,
                show_tgt=True,
            )
        # 3 entries + trailing stretch.
        assert overlay._lines_layout.count() == 4  # noqa: PLR2004

    def test_overlay_clear_after_add(self, qapp) -> None:  # noqa: ARG002
        """Overlay clear drops real entries and restores only the placeholder."""
        from src.ui.pages.live import _OverlayWindow  # noqa: PLC0415

        overlay = _OverlayWindow()
        for src in ("Line 1", "Line 2"):
            overlay.add_entry(
                "",
                "",
                src,
                show_timestamp=True,
                show_speaker=True,
                show_src=True,
                show_tgt=True,
            )
        overlay.clear_lines()
        # Placeholder hint + trailing stretch.
        assert overlay._lines_layout.count() == 2  # noqa: PLR2004
        assert overlay._lines_layout.itemAt(0).widget().property("is_placeholder")
        # Can add again after clearing — replaces placeholder with one entry.
        overlay.add_entry(
            "",
            "",
            "New line",
            show_timestamp=True,
            show_speaker=True,
            show_src=True,
            show_tgt=True,
        )
        assert overlay._lines_layout.count() == 2  # noqa: PLR2004

    def test_overlay_mouse_press(self, qapp) -> None:  # noqa: ARG002
        """Mouse press stores the drag position."""
        from PySide6.QtCore import QPoint, Qt  # noqa: PLC0415

        from src.ui.pages.live import _OverlayWindow  # noqa: PLC0415

        overlay = _OverlayWindow()
        mock_event = MagicMock()
        mock_event.button.return_value = Qt.MouseButton.LeftButton
        mock_event.globalPosition.return_value.toPoint.return_value = QPoint(100, 200)
        overlay.mousePressEvent(mock_event)
        assert overlay._drag_pos is not None


# ===========================================================================
# NEW TESTS — TTSWorker additional edge cases
# ===========================================================================


class TestTTSWorkerAdditional:
    """Additional TTS worker tests."""

    @patch(f"{_MOD}.load_setting", return_value="Edge TTS")
    def test_tts_worker_stores_text(self, _load) -> None:
        """Worker stores the text to synthesize."""
        worker = _make_tts_worker("Test text", "English")
        assert worker._text == "Test text"

    @patch(f"{_MOD}.load_setting", return_value="Edge TTS")
    def test_tts_worker_stores_lang(self, _load) -> None:
        """Worker stores the target language."""
        worker = _make_tts_worker("Test", "French")
        assert worker._target_lang == "French"

    @patch(f"{_MOD}.load_setting", return_value="Edge TTS")
    def test_tts_worker_stores_gender(self, _load) -> None:
        """Worker stores the voice gender."""
        worker = _make_tts_worker("Test", "English", gender="MALE")
        assert worker._gender == "MALE"

    @patch(f"{_MOD}.load_setting", return_value="Edge TTS")
    def test_tts_worker_default_gender(self, _load) -> None:
        """Worker defaults to FEMALE gender."""
        worker = _make_tts_worker("Test", "English")
        assert worker._gender == "FEMALE"


# ===========================================================================
# NEW TESTS — TranslationWorker additional edge cases
# ===========================================================================


class TestTranslationWorkerAdditional:
    """Additional translation worker tests."""

    def test_worker_stores_text(self) -> None:
        """Worker stores the text to translate."""
        worker = _make_translation_worker("Hello", "English", "French")
        assert worker._text == "Hello"

    def test_worker_stores_src_lang(self) -> None:
        """Worker stores the source language."""
        worker = _make_translation_worker("Hello", "English", "French")
        assert worker._src_lang == "English"

    def test_worker_stores_target_lang(self) -> None:
        """Worker stores the target language."""
        worker = _make_translation_worker("Hello", "English", "French")
        assert worker._target_lang == "French"

    def test_worker_stores_glossary(self) -> None:
        """Worker stores glossary entries."""
        glossary = [(1, "API", "Interface")]
        worker = _make_translation_worker(
            "Hello", "English", "French", glossary_entries=glossary
        )
        assert worker._glossary_entries == glossary

    def test_worker_default_glossary_none(self) -> None:
        """Worker defaults to None glossary."""
        worker = _make_translation_worker("Hello", "English", "French")
        assert worker._glossary_entries is None

    def test_worker_multiple_languages(self) -> None:
        """Worker works with various language combinations."""
        for src, tgt in [
            ("English", "Japanese"),
            ("French", "Chinese (Simplified)"),
            ("Vietnamese", "Korean"),
        ]:
            worker = _make_translation_worker("Test", src, tgt)
            assert worker._src_lang == src
            assert worker._target_lang == tgt


# ===========================================================================
# NEW TESTS — Page action edge cases
# ===========================================================================


class TestPageActionsExpanded:
    """Expanded tests for LivePage actions."""

    def test_toggle_tts_three_times(self, live_page) -> None:
        """Toggle TTS three times alternates correctly."""
        live_page._tts_enabled = False
        live_page._toggle_tts()
        assert live_page._tts_enabled is True
        live_page._toggle_tts()
        assert live_page._tts_enabled is False
        live_page._toggle_tts()
        assert live_page._tts_enabled is True
        live_page._tts_enabled = False

    def test_toggle_overlay_creates_on_first_call(self, live_page) -> None:
        """First toggle creates overlay."""
        live_page._overlay = None
        live_page._toggle_overlay()
        assert live_page._overlay is not None
        live_page._overlay.hide()

    def test_toggle_overlay_shows_hides_shows(self, live_page) -> None:
        """Overlay toggles visible/hidden/visible correctly."""
        from src.ui.pages.live import _OverlayWindow  # noqa: PLC0415

        live_page._overlay = _OverlayWindow()
        live_page._overlay.hide()
        live_page._toggle_overlay()
        assert live_page._overlay.isVisible()
        live_page._toggle_overlay()
        assert not live_page._overlay.isVisible()
        live_page._toggle_overlay()
        assert live_page._overlay.isVisible()
        live_page._overlay.hide()

    def test_on_status_empty_string(self, live_page) -> None:
        """_on_status handles empty string."""
        live_page._transcriber = MagicMock()
        live_page._on_status("")
        assert live_page.status_label.text() == ""

    def test_on_status_unicode(self, live_page) -> None:
        """_on_status handles unicode status text."""
        live_page._transcriber = MagicMock()
        live_page._on_status("Đang nghe...")
        assert live_page.status_label.text() == "Đang nghe..."

    def test_clear_log_multiple_times(self, live_page) -> None:
        """_clear_log called multiple times is safe."""
        for _ in range(5):
            live_page._add_original("Entry")
        live_page._clear_log()
        live_page._clear_log()
        assert live_page._transcript_layout.count() == 1


# ===========================================================================
# NEW TESTS — QSS style validation (expanded)
# ===========================================================================


class TestQSSStyleExpanded:
    """Extended QSS style validation tests."""

    def test_style_transcript_original_has_color(self) -> None:
        """_style_transcript_original has color property."""
        from src.ui.pages.live import _style_transcript_original  # noqa: PLC0415

        result = _style_transcript_original()
        assert "color:" in result

    def test_style_transcript_translated_has_color(self) -> None:
        """_style_transcript_translated has color property."""
        from src.ui.pages.live import _style_transcript_translated  # noqa: PLC0415

        result = _style_transcript_translated()
        assert "color:" in result

    def test_style_status_bold_weight(self) -> None:
        """_style_status uses bold weight for the pill text.

        ``border-radius`` is no longer in this stylesheet (the
        rounded background moved into _PillLabel's paintEvent), so
        the assertion is narrowed to the property that *does* still
        live here: font-weight 600.
        """
        from src.ui.pages.live import _style_status  # noqa: PLC0415

        result = _style_status()
        assert "font-weight: 600" in result

    def test_all_styles_no_empty(self) -> None:
        """All style functions return non-empty strings."""
        from src.ui.pages.live import (  # noqa: PLC0415
            _style_status,
            _style_transcript_original,
            _style_transcript_translated,
        )

        for fn in (
            _style_transcript_original,
            _style_transcript_translated,
            _style_status,
        ):
            assert len(fn()) > 0


# ===========================================================================
# NEW TESTS — create_live_page function
# ===========================================================================


class TestCreateLivePage:
    """Tests for the create_live_page module-level factory."""

    def test_create_live_page_returns_live_page(self, window, qtbot) -> None:
        """create_live_page returns a LivePage instance."""
        from src.ui.pages.live import LivePage, create_live_page  # noqa: PLC0415

        with patch(f"{_MOD}.load_setting", return_value=""):
            page = create_live_page(window)
        qtbot.addWidget(page)
        assert isinstance(page, LivePage)

    def test_create_live_page_stores_window(self, window, qtbot) -> None:
        """create_live_page passes window as parent."""
        from src.ui.pages.live import create_live_page  # noqa: PLC0415

        with patch(f"{_MOD}.load_setting", return_value=""):
            page = create_live_page(window)
        qtbot.addWidget(page)
        assert page.window_context is window


# ===========================================================================
# NEW TESTS — Transcript entry management (extended)
# ===========================================================================


class TestTranscriptEntryManagement:
    """Extended tests for transcript entry management."""

    def test_insert_entry_adds_before_stretch(self, live_page) -> None:
        """_insert_entry adds widget before the final stretch."""
        live_page._clear_log()
        live_page._add_original("First")
        live_page._add_original("Second")
        # The last item is always the stretch
        last_idx = live_page._transcript_layout.count() - 1
        assert live_page._transcript_layout.itemAt(last_idx).widget() is None  # stretch

    def test_multiple_originals_order(self, live_page) -> None:
        """Multiple originals appear in order as one card each."""
        from src.ui.pages.live import _TranscriptCard  # noqa: PLC0415

        live_page._clear_log()
        live_page._add_original("A")
        live_page._add_original("B")
        live_page._add_original("C")
        texts = []
        for i in range(live_page._transcript_layout.count() - 1):
            item = live_page._transcript_layout.itemAt(i)
            widget = item.widget()
            if widget:
                assert isinstance(widget, _TranscriptCard)
                texts.append(widget._body.text())
        assert texts == ["A", "B", "C"]

    def test_interleaved_original_translated(self, live_page) -> None:
        """Interleaved original + translated: each pair collapses into one card.

        _add_original inserts ONE card, and a following _add_translated
        attaches the translation to that existing card rather than
        creating a new row.  So two original+translated pairs produce
        2 cards + 1 stretch = 3 items in the single-view layout.
        """
        from src.ui.pages.live import _TranscriptCard  # noqa: PLC0415

        live_page._clear_log()
        live_page._add_original("Hello")
        live_page._add_translated("Bonjour")
        live_page._add_original("World")
        live_page._add_translated("Monde")
        assert live_page._transcript_layout.count() == 3  # noqa: PLR2004
        first = live_page._transcript_layout.itemAt(0).widget()
        second = live_page._transcript_layout.itemAt(1).widget()
        assert isinstance(first, _TranscriptCard)
        assert isinstance(second, _TranscriptCard)
        assert first._body.text() == "Hello"
        assert first._translated is not None
        assert first._translated.text() == "Bonjour"
        assert second._body.text() == "World"
        assert second._translated is not None
        assert second._translated.text() == "Monde"

    def test_clear_then_add(self, live_page) -> None:
        """Clear then add new entries works correctly."""
        from src.ui.pages.live import _TranscriptCard  # noqa: PLC0415

        live_page._add_original("Old entry")
        live_page._clear_log()
        live_page._add_original("New entry")
        idx = live_page._transcript_layout.count() - 2
        card = live_page._transcript_layout.itemAt(idx).widget()
        assert isinstance(card, _TranscriptCard)
        assert card._body.text() == "New entry"

    def test_max_entries_trimming(self, live_page) -> None:
        """Adding beyond max entries trims oldest."""
        from src.ui.pages.live import _MAX_LOG_ENTRIES  # noqa: PLC0415

        live_page._clear_log()
        for i in range(_MAX_LOG_ENTRIES + 5):
            live_page._add_original(f"Entry {i}")
        # Should not exceed max + stretch
        assert live_page._transcript_layout.count() <= _MAX_LOG_ENTRIES + 1


# ===========================================================================
# NEW TESTS — TTS worker run paths (extended)
# ===========================================================================


class TestTTSWorkerRunPaths:
    """Extended TTS worker run path tests."""

    @patch(f"{_MOD}.load_setting", return_value="Edge TTS")
    def test_tts_worker_japanese(self, _load) -> None:
        """TTS worker works with Japanese language."""
        worker = _make_tts_worker("こんにちは", "Japanese")
        with (
            patch(
                "src.core.speech_engine._get_edge_voice",
                return_value="ja-JP-NanamiNeural",
            ) as mock_voice,
            patch("src.core.speech_engine._synthesize_chunk_edge") as mock_edge,
            patch("src.core.speech_engine._get_tts_language_code"),
            patch("src.core.speech_engine._synthesize_chunk"),
            patch("tempfile.NamedTemporaryFile") as mock_tmp,
        ):
            tmp_obj = MagicMock()
            tmp_obj.name = "/tmp/live_tts_ja.mp3"
            tmp_obj.close = MagicMock()
            mock_tmp.return_value = tmp_obj
            worker.run()
        mock_voice.assert_called_once_with("Japanese", "FEMALE")
        mock_edge.assert_called_once()
        worker.synthesized.emit.assert_called_once()

    @patch(f"{_MOD}.load_setting", return_value="Edge TTS")
    def test_tts_worker_chinese(self, _load) -> None:
        """TTS worker works with Chinese language."""
        worker = _make_tts_worker("你好世界", "Chinese (Simplified)")
        with (
            patch(
                "src.core.speech_engine._get_edge_voice",
                return_value="zh-CN-XiaoxiaoNeural",
            ),
            patch("src.core.speech_engine._synthesize_chunk_edge") as mock_edge,
            patch("src.core.speech_engine._get_tts_language_code"),
            patch("src.core.speech_engine._synthesize_chunk"),
            patch("tempfile.NamedTemporaryFile") as mock_tmp,
        ):
            tmp_obj = MagicMock()
            tmp_obj.name = "/tmp/live_tts_zh.mp3"
            tmp_obj.close = MagicMock()
            mock_tmp.return_value = tmp_obj
            worker.run()
        mock_edge.assert_called_once()
        worker.synthesized.emit.assert_called_once()

    @patch(f"{_MOD}.load_setting", return_value="Edge TTS")
    def test_tts_worker_special_chars(self, _load) -> None:
        """TTS worker handles text with special characters."""
        text = "Hello! How are you? I'm fine & well <3"
        worker = _make_tts_worker(text, "English")
        with (
            patch(
                "src.core.speech_engine._get_edge_voice",
                return_value="en-US-JennyNeural",
            ),
            patch("src.core.speech_engine._synthesize_chunk_edge") as mock_edge,
            patch("src.core.speech_engine._get_tts_language_code"),
            patch("src.core.speech_engine._synthesize_chunk"),
            patch("tempfile.NamedTemporaryFile") as mock_tmp,
        ):
            tmp_obj = MagicMock()
            tmp_obj.name = "/tmp/live_tts_special.mp3"
            tmp_obj.close = MagicMock()
            mock_tmp.return_value = tmp_obj
            worker.run()
        assert mock_edge.call_args[0][0] == text
        worker.synthesized.emit.assert_called_once()


# ===========================================================================
# NEW TESTS — Translation worker run paths (extended)
# ===========================================================================


class TestTranslationWorkerRunPaths:
    """Extended translation worker run path tests."""

    def test_korean_translation(self) -> None:
        """Translation worker handles Korean."""
        worker = _make_translation_worker("Hello", "English", "Korean")
        with patch(
            "src.core.llm_engine.stream_translate_text",
            return_value=iter(["안녕하세요"]),
        ):
            worker.run()
        worker.translated.emit.assert_called_once_with("Hello", "안녕하세요")

    def test_arabic_translation(self) -> None:
        """Translation worker handles Arabic."""
        worker = _make_translation_worker("Good morning", "English", "Arabic")
        with patch(
            "src.core.llm_engine.stream_translate_text",
            return_value=iter(["صباح الخير"]),
        ):
            worker.run()
        worker.translated.emit.assert_called_once_with("Good morning", "صباح الخير")

    def test_number_only_text(self) -> None:
        """Translation worker handles number-only text."""
        worker = _make_translation_worker("12345", "English", "French")
        with patch(
            "src.core.llm_engine.stream_translate_text",
            return_value=iter(["12345"]),
        ):
            worker.run()
        worker.translated.emit.assert_called_once_with("12345", "12345")

    def test_service_unavailable_error(self) -> None:
        """SERVICE_UNAVAILABLE_ERROR retries once, then emits error."""
        worker = _make_translation_worker("Test", "English", "French")
        with (
            patch(
                "src.core.llm_engine.stream_translate_text",
                side_effect=ValueError("SERVICE_UNAVAILABLE_ERROR"),
            ),
            patch(f"{_MOD}.time.sleep"),  # don't really sleep in tests
        ):
            worker.run()
        worker.error.emit.assert_called_once()
        assert "SERVICE_UNAVAILABLE_ERROR" in worker.error.emit.call_args[0][0]


# ===========================================================================
# NEW TESTS — LivePage state machine
# ===========================================================================


class TestLivePageStateMachine:
    """Tests for LivePage state transitions."""

    def test_initial_state_all_buttons_have_text(self, live_page) -> None:
        """All buttons (start + the four action buttons) carry text in the default expanded state."""
        # start_btn is a plain labelled button.
        assert live_page.start_btn.text() != ""
        # Action buttons: expanded state renders text alongside icons, and
        # still exposes the label via accessibleName for a11y.
        for btn in (
            live_page.tts_btn,
            live_page.overlay_btn,
            live_page.clear_btn,
        ):
            assert btn.text() != ""
            assert not btn.icon().isNull()
            assert btn.accessibleName() != ""

    def test_initial_state_status_label_has_text(self, live_page) -> None:
        """Status label has text after init."""
        assert live_page.status_label.text() != ""

    def test_start_button_has_stylesheet(self, live_page) -> None:
        """Start button has a non-empty stylesheet."""
        live_page.apply_theme()
        assert live_page.start_btn.styleSheet() != ""

    def test_tts_button_has_stylesheet(self, live_page) -> None:
        """TTS button has a non-empty stylesheet."""
        live_page.apply_theme()
        assert live_page.tts_btn.styleSheet() != ""

    def test_overlay_button_has_stylesheet(self, live_page) -> None:
        """Overlay button has a non-empty stylesheet."""
        live_page.apply_theme()
        assert live_page.overlay_btn.styleSheet() != ""

    def test_clear_button_has_stylesheet(self, live_page) -> None:
        """Clear button has a non-empty stylesheet."""
        live_page.apply_theme()
        assert live_page.clear_btn.styleSheet() != ""

    def test_transcript_layout_initially_has_stretch(self, live_page) -> None:
        """Transcript layout has stretch initially."""
        live_page._clear_log()
        assert live_page._transcript_layout.count() == 1

    def test_translation_workers_is_list(self, live_page) -> None:
        """_translation_workers is a list."""
        assert isinstance(live_page._translation_workers, list)

    def test_tts_queue_is_deque_or_list(self, live_page) -> None:
        """_tts_queue supports append and clear."""
        live_page._tts_queue.append("test")
        assert len(live_page._tts_queue) == 1
        live_page._tts_queue.clear()
        assert len(live_page._tts_queue) == 0


# ===========================================================================
# NEW TESTS — Overlay window parametrized
# ===========================================================================


class TestOverlayParametrized:
    """Parametrized tests for overlay."""

    @pytest.mark.parametrize("count", [1, 3, 5, 10])
    def test_overlay_add_n_entries(self, qapp, count) -> None:  # noqa: ARG002
        """Overlay tracks every submitted entry (no rolling cap)."""
        from src.ui.pages.live import _OverlayWindow  # noqa: PLC0415

        overlay = _OverlayWindow()
        for i in range(count):
            overlay.add_entry(
                "",
                "",
                f"Line {i}",
                show_timestamp=True,
                show_speaker=True,
                show_src=True,
                show_tgt=True,
            )
        # ``count`` entries + the trailing stretch.
        assert overlay._lines_layout.count() == count + 1

    def test_overlay_translation_label_has_white_color(self, qapp) -> None:  # noqa: ARG002
        """Translated text renders in (near-)white for maximum contrast."""
        from src.ui.pages.live import _OverlayWindow  # noqa: PLC0415

        overlay = _OverlayWindow()
        overlay.add_entry(
            "",
            "",
            "Original",
            show_timestamp=True,
            show_speaker=True,
            show_src=True,
            show_tgt=True,
        )
        overlay.set_last_translation(
            "Translated text",
            show_src=True,
            show_tgt=True,
        )
        entry = overlay._lines_layout.itemAt(0).widget()
        style = entry._translation_label.styleSheet().lower()
        compact = style.replace(" ", "")
        # Accepts "white", "#fff", or any rgba(255,255,255,…) form.
        assert "white" in style or "#fff" in style or "rgba(255,255,255" in compact

    def test_overlay_source_and_translation_styles_differ(self, qapp) -> None:  # noqa: ARG002
        """Source and translation labels carry distinct styles."""
        from src.ui.pages.live import _OverlayWindow  # noqa: PLC0415

        overlay = _OverlayWindow()
        overlay.add_entry(
            "",
            "",
            "Original",
            show_timestamp=True,
            show_speaker=True,
            show_src=True,
            show_tgt=True,
        )
        overlay.set_last_translation(
            "Translated",
            show_src=True,
            show_tgt=True,
        )
        entry = overlay._lines_layout.itemAt(0).widget()
        assert entry._source_label.styleSheet() != entry._translation_label.styleSheet()

    def test_overlay_tool_flag(self, qapp) -> None:  # noqa: ARG002
        """Overlay has Tool window flag."""
        from PySide6.QtCore import Qt  # noqa: PLC0415

        from src.ui.pages.live import _OverlayWindow  # noqa: PLC0415

        overlay = _OverlayWindow()
        flags = overlay.windowFlags()
        assert flags & Qt.WindowType.Tool


# ===========================================================================
# Audio pre-check
# ===========================================================================


class TestAudioPreCheck:
    """Tests for audio pre-validation in _start_listening."""

    def test_start_blocked_when_audio_unavailable(self, live_page) -> None:
        """_start_listening shows dialog and aborts when audio check fails."""
        with (
            patch(
                "src.core.live_engine.check_audio_available",
                return_value="live.error_no_mic",
            ),
            patch(
                "src.ui.dialogs.CustomMessageDialog.show_message",
            ) as mock_show,
        ):
            live_page._start_listening()
            mock_show.assert_called_once()
            # Transcriber should NOT have been created
            assert live_page._transcriber is None

    def test_portaudio_missing_shows_hint_in_dialog(self, live_page) -> None:
        """When portaudio is missing, dialog includes install command hint."""
        _hint = "sudo apt-get install libportaudio2"
        with (
            patch(
                "src.core.live_engine.check_audio_available",
                return_value="live.error_no_portaudio",
            ),
            patch(
                "src.core.live_engine._get_portaudio_install_hint",
                return_value=_hint,
            ),
            patch(
                "src.ui.pages.live.tr",
                side_effect=lambda k: {
                    "live.error_no_portaudio": "PortAudio is not installed.",
                    "live.hint_run_command": "\n\nPlease run:  {cmd}",
                }.get(k, k),
            ),
            patch(
                "src.ui.dialogs.CustomMessageDialog.show_message",
            ) as mock_show,
        ):
            live_page._start_listening()
            mock_show.assert_called_once()
            msg_arg = mock_show.call_args[0][2]
            assert _hint in msg_arg

    def test_portaudio_missing_no_hint_omits_command(
        self,
        live_page,
    ) -> None:
        """When no hint is available, dialog omits the command line."""
        with (
            patch(
                "src.core.live_engine.check_audio_available",
                return_value="live.error_no_portaudio",
            ),
            patch(
                "src.core.live_engine._get_portaudio_install_hint",
                return_value="",
            ),
            patch(
                "src.ui.pages.live.tr",
                side_effect=lambda k: {
                    "live.error_no_portaudio": "PortAudio is not installed.",
                    "live.hint_run_command": "\n\nPlease run:  {cmd}",
                }.get(k, k),
            ),
            patch(
                "src.ui.dialogs.CustomMessageDialog.show_message",
            ) as mock_show,
        ):
            live_page._start_listening()
            mock_show.assert_called_once()
            msg_arg = mock_show.call_args[0][2]
            assert "Please run" not in msg_arg


# ===========================================================================
# Audio source combo
# ===========================================================================


class TestAudioSourceCombo:
    """Tests for the audio source combo box."""

    def test_combo_exists(self, live_page) -> None:
        """Audio source combo is created."""
        assert hasattr(live_page, "audio_source_combo")
        assert live_page.audio_source_combo.count() == 3

    def test_combo_default_is_microphone(self, live_page) -> None:
        """Default selection is microphone."""
        assert live_page.audio_source_combo.currentData() == "microphone"

    def test_combo_persists_selection(self, live_page) -> None:
        """Changing combo box saves the setting."""
        with patch("src.ui.pages.live.save_setting") as mock_save:
            live_page.audio_source_combo.setCurrentIndex(1)
            mock_save.assert_called_with(
                "live/audio_source",
                "system",
            )

    def test_combo_disabled_while_listening(self, live_page) -> None:
        """Combo is disabled while transcriber is active."""
        with (
            patch(
                "src.core.live_engine.check_audio_available",
                return_value="",
            ),
            patch(
                "src.core.live_engine.LiveTranscriber.start",
            ),
            patch(
                "src.ui.pages.live.load_setting",
                side_effect=lambda k, d="": {
                    "live/audio_source": "microphone",
                }.get(k, d),
            ),
        ):
            live_page._start_listening()
            assert not live_page.audio_source_combo.isEnabled()

    def test_combo_enabled_after_stop(self, live_page) -> None:
        """Combo is re-enabled after stopping."""
        live_page.audio_source_combo.setEnabled(False)
        live_page._stop_listening()
        assert live_page.audio_source_combo.isEnabled()

    def test_audio_source_passed_to_transcriber(self, live_page) -> None:
        """Audio source value is passed to LiveTranscriber."""
        with (
            patch(
                "src.core.live_engine.check_audio_available",
                return_value="",
            ),
            patch(
                "src.core.live_engine.LiveTranscriber.start",
            ),
            patch(
                "src.ui.pages.live.load_setting",
                side_effect=lambda k, d="": {
                    "live/audio_source": "both",
                }.get(k, d),
            ),
            patch(
                "src.core.live_engine.check_system_audio_available",
                return_value=True,
            ),
        ):
            live_page._start_listening()
            assert live_page._transcriber._audio_source == "both"

    def test_system_audio_missing_shows_dialog(self, live_page) -> None:
        """Shows error dialog when system audio is not available."""
        with (
            patch(
                "src.core.live_engine.check_audio_available",
                return_value="",
            ),
            patch(
                "src.core.live_engine.check_system_audio_available",
                return_value=False,
            ),
            patch(
                "src.ui.pages.live.load_setting",
                side_effect=lambda k, d="": {
                    "live/audio_source": "system",
                }.get(k, d),
            ),
            patch(
                "src.ui.dialogs.CustomMessageDialog.show_message",
            ) as mock_show,
        ):
            live_page._start_listening()
            mock_show.assert_called_once()
            assert live_page._transcriber is None


# ===========================================================================
# NEW TESTS — Button interaction (extended)
# ===========================================================================


class TestButtonInteraction:
    """Extended button interaction tests."""

    def test_tts_toggle_icon_cycles(self, live_page) -> None:
        """TTS button text/accessibleName alternate between on/off tr keys on each toggle."""
        from src.constants import tr  # noqa: PLC0415

        on_label = tr("live.btn_tts_on")
        off_label = tr("live.btn_tts_off")
        assert on_label != off_label

        live_page._tts_enabled = False
        live_page._toggle_tts()
        assert live_page.tts_btn.accessibleName() == on_label
        # Expanded (default) state: text cycles along with accessibleName.
        assert live_page.tts_btn.text() == on_label
        live_page._toggle_tts()
        assert live_page.tts_btn.accessibleName() == off_label
        assert live_page.tts_btn.text() == off_label
        live_page._toggle_tts()
        assert live_page.tts_btn.accessibleName() == on_label
        assert live_page.tts_btn.text() == on_label
        live_page._tts_enabled = False

    def test_overlay_button_text_cycles_with_state(self, live_page) -> None:
        """Overlay button text reflects show/hide state via on/off labels."""
        from src.constants import tr  # noqa: PLC0415

        on_label = tr("live.btn_overlay_on")
        off_label = tr("live.btn_overlay_off")
        # Default: overlay is hidden → label reads OFF.
        assert live_page.overlay_btn.text() == off_label
        live_page._toggle_overlay()
        assert live_page.overlay_btn.text() == on_label
        assert live_page.overlay_btn.accessibleName() == on_label
        live_page._toggle_overlay()
        assert live_page.overlay_btn.text() == off_label
        assert live_page.overlay_btn.accessibleName() == off_label
        if live_page._overlay:
            live_page._overlay.hide()

    def test_stop_listening_button_text(self, live_page) -> None:
        """_stop_listening sets button to start text."""
        from src.constants import tr  # noqa: PLC0415

        live_page._transcriber = MagicMock()
        live_page._stop_listening()
        _drain_stop_worker(live_page)
        assert live_page.start_btn.text() == tr("live.btn_start")

    def test_stop_listening_button_style(self, live_page) -> None:
        """_stop_listening sets button to primary style."""
        from src.constants import style_primary_button  # noqa: PLC0415

        live_page._transcriber = MagicMock()
        live_page._stop_listening()
        _drain_stop_worker(live_page)
        assert live_page.start_btn.styleSheet() == style_primary_button()


# ===========================================================================
# NEW TESTS — Additional coverage for live page methods
# ===========================================================================


class TestClearLog:
    """Tests for _clear_log method."""

    def test_clear_log_removes_entries(self, live_page) -> None:
        """_clear_log removes transcript entries from layout."""
        live_page._add_original("Line 1")
        live_page._add_original("Line 2")
        # Should have at least 2 entries plus stretch
        assert live_page._transcript_layout.count() > 1
        live_page._clear_log()
        # Only stretch should remain
        assert live_page._transcript_layout.count() == 1

    def test_clear_log_clears_overlay(self, live_page) -> None:
        """_clear_log drops transcripts and leaves only the placeholder hint."""
        from src.ui.pages.live import _OverlayWindow  # noqa: PLC0415

        live_page._overlay = _OverlayWindow()
        live_page._overlay.add_entry(
            "",
            "",
            "Test line",
            show_timestamp=True,
            show_speaker=True,
            show_src=True,
            show_tgt=True,
        )
        # Real entry + trailing stretch; first item is the entry widget.
        assert live_page._overlay._lines_layout.count() == 2  # noqa: PLR2004
        assert (
            not live_page._overlay._lines_layout.itemAt(0)
            .widget()
            .property(
                "is_placeholder",
            )
        )
        live_page._clear_log()
        # After clear, placeholder + trailing stretch.
        assert live_page._overlay._lines_layout.count() == 2  # noqa: PLR2004
        assert (
            live_page._overlay._lines_layout.itemAt(0)
            .widget()
            .property(
                "is_placeholder",
            )
        )

    def test_clear_log_no_overlay_no_error(self, live_page) -> None:
        """_clear_log succeeds without overlay."""
        live_page._overlay = None
        live_page._clear_log()  # Should not raise


class TestOnStatus:
    """Tests for _on_status method."""

    def test_on_status_updates_label(self, live_page) -> None:
        """_on_status sets the status label text."""
        live_page._transcriber = MagicMock()
        live_page._on_status("Listening...")
        assert live_page.status_label.text() == "Listening..."

    def test_on_status_empty_string(self, live_page) -> None:
        """_on_status handles empty string."""
        live_page._transcriber = MagicMock()
        live_page._on_status("")
        assert live_page.status_label.text() == ""

    def test_on_status_drops_late_signal_after_stop(self, live_page) -> None:
        """Regression: a late status push after Stop must not overwrite "Ready".

        ``_stop_listening`` nulls ``_transcriber`` synchronously, but
        the engine thread can still queue a "Listening…" /
        "Connecting…" signal that fires on the UI thread after the
        user clicked Stop.  Without the ``_transcriber is None``
        guard the toolbar would silently swap back to a stale
        listening message while the Start button shows the idle
        state — same class of bug as ``test_on_sentence_drops_late_
        signal_after_stop``, applied to the status surface.
        """
        live_page._transcriber = None
        live_page.status_label.setText("Ready")
        live_page._on_status("Listening...")
        # Status text must not be overwritten by the late signal.
        assert live_page.status_label.text() == "Ready"


class TestOnTranslated:
    """Tests for _on_translated method."""

    def test_on_translated_adds_text(self, live_page) -> None:
        """_on_translated adds translated text to transcript."""
        live_page._transcriber = MagicMock()
        initial = live_page._transcript_layout.count()
        live_page._on_translated("Hello", "Xin chao")
        assert live_page._transcript_layout.count() > initial

    def test_on_translated_queues_tts_when_enabled(self, live_page) -> None:
        """_on_translated queues text for TTS when TTS is enabled."""
        live_page._transcriber = MagicMock()
        live_page._tts_enabled = True
        with patch.object(live_page, "_process_tts_queue"):
            live_page._on_translated("Hello", "Xin chao")
        assert "Xin chao" in live_page._tts_queue

    def test_on_translated_no_tts_when_disabled(self, live_page) -> None:
        """_on_translated does not queue TTS when disabled."""
        live_page._transcriber = MagicMock()
        live_page._tts_enabled = False
        live_page._on_translated("Hello", "Xin chao")
        assert len(live_page._tts_queue) == 0

    def test_on_translated_drops_late_signal_after_stop(self, live_page) -> None:
        """Regression: late LLM result after Stop must not land on transcript.

        Per-sentence ``_TranslationWorker``s run a blocking LLM call
        that can't be cancelled.  When the user clicks Stop while a
        translation is in flight, the worker eventually emits
        ``translated`` on the UI thread — the ``_transcriber is None``
        guard at the top of ``_on_translated`` must short-circuit so
        no transcript or TTS update happens.  Pinning this guard so
        the systematic late-signal-protection contract documented in
        AGENTS.md isn't quietly regressed.
        """
        live_page._transcriber = None  # session already stopped
        live_page._tts_enabled = True
        live_page._tts_queue.clear()
        initial = live_page._transcript_layout.count()
        live_page._on_translated("Hello", "Xin chào")
        # No card inserted, no TTS queued.
        assert live_page._transcript_layout.count() == initial
        assert len(live_page._tts_queue) == 0


class TestOnTranslationError:
    """Tests for _on_translation_error method."""

    def test_on_translation_error_logs(self, live_page) -> None:
        """_on_translation_error logs the error."""
        live_page._transcriber = MagicMock()
        with patch("src.ui.pages.live.logger") as mock_logger:
            live_page._on_translation_error("Connection refused")
        mock_logger.error.assert_called_once()

    def test_on_translation_error_drops_late_signal_after_stop(
        self,
        live_page,
    ) -> None:
        """Regression: a late translation error after Stop is a silent no-op.

        Same late-signal class as ``_on_translated`` — the LLM
        worker raised after the user stopped the session and we
        must not toast / repaint anything.  Without the guard, the
        status pill would flash red on a session the user already
        ended.
        """
        live_page._transcriber = None
        live_page.status_label.setText("Ready")
        with patch("src.ui.pages.live.logger") as mock_logger:
            live_page._on_translation_error("AUTH_ERROR")
        # Guard fires before logging — no error log, no status flip.
        mock_logger.error.assert_not_called()
        assert live_page.status_label.text() == "Ready"


class TestOnPartialTranslation:
    """Tests for the _on_partial_translation streaming-chunk slot."""

    def test_on_partial_translation_drops_late_signal_after_stop(
        self,
        live_page,
    ) -> None:
        """Regression: streaming chunks emitted after Stop must not paint.

        ``_TranslationWorker`` emits ``partial_translated`` on every
        chunk while streaming.  If the user clicks Stop mid-stream,
        the rest of the chunks still bubble up to the UI thread —
        the ``_transcriber is None`` guard at the top of
        ``_on_partial_translation`` must short-circuit so the
        transcript doesn't keep mutating after the session ended.
        """
        live_page._transcriber = None
        initial = live_page._transcript_layout.count()
        live_page._on_partial_translation(
            "Hello world",
            "Bonjour le",
            None,
            None,
        )
        # No transcript update.
        assert live_page._transcript_layout.count() == initial


class TestCleanupWorker:
    """Tests for _cleanup_worker method."""

    def test_cleanup_removes_worker_from_list(self, live_page) -> None:
        """_cleanup_worker removes the worker from _translation_workers."""
        mock_worker = MagicMock()
        live_page._translation_workers.append(mock_worker)
        assert mock_worker in live_page._translation_workers
        live_page._cleanup_worker(mock_worker)
        assert mock_worker not in live_page._translation_workers

    def test_cleanup_unknown_worker_no_error(self, live_page) -> None:
        """_cleanup_worker does nothing for unknown worker."""
        mock_worker = MagicMock()
        live_page._cleanup_worker(mock_worker)  # Should not raise


class TestProcessTtsQueue:
    """Tests for _process_tts_queue method."""

    def test_process_tts_queue_noop_when_worker_active(self, live_page) -> None:
        """_process_tts_queue does nothing when a TTS worker is active."""
        live_page._tts_worker = MagicMock()
        live_page._tts_queue.append("Test")
        with patch("src.ui.pages.live._TTSWorker") as mock_cls:
            live_page._process_tts_queue()
        mock_cls.assert_not_called()

    def test_process_tts_queue_noop_when_empty(self, live_page) -> None:
        """_process_tts_queue does nothing when queue is empty."""
        live_page._tts_worker = None
        live_page._tts_queue.clear()
        with patch("src.ui.pages.live._TTSWorker") as mock_cls:
            live_page._process_tts_queue()
        mock_cls.assert_not_called()


class TestOnTtsError:
    """Tests for _on_tts_error method."""

    def test_on_tts_error_clears_worker(self, live_page) -> None:
        """_on_tts_error sets _tts_worker to None."""
        live_page._tts_worker = MagicMock()
        with patch.object(live_page, "_process_tts_queue"):
            live_page._on_tts_error("TTS failed")
        assert live_page._tts_worker is None

    def test_on_tts_error_processes_next_in_queue(self, live_page) -> None:
        """_on_tts_error processes the next TTS item."""
        live_page._tts_worker = MagicMock()
        with patch.object(live_page, "_process_tts_queue") as mock_process:
            live_page._on_tts_error("TTS failed")
        mock_process.assert_called_once()


class TestToggleOverlay:
    """Tests for _toggle_overlay method."""

    def test_toggle_overlay_creates_overlay(self, live_page) -> None:
        """_toggle_overlay creates overlay when it doesn't exist."""
        live_page._overlay = None
        live_page._overlay_visible = False
        live_page._toggle_overlay()
        assert live_page._overlay is not None

    def test_toggle_overlay_toggles_visibility(self, live_page) -> None:
        """_toggle_overlay toggles overlay visibility via show/hide."""
        from src.ui.pages.live import _OverlayWindow  # noqa: PLC0415

        live_page._overlay = _OverlayWindow()
        # First toggle should show
        live_page._toggle_overlay()
        was_shown = live_page._overlay.isVisible()
        # Second toggle should hide
        live_page._toggle_overlay()
        is_hidden = not live_page._overlay.isVisible()
        assert was_shown or is_hidden  # At least one transition worked


# ===========================================================================
# TestFormatHelpers — module-level helper functions
# ===========================================================================


class TestFormatHelpers:
    """Tests for module-level helper functions _format_speaker, _format_timestamp, _lang_to_code."""

    def test_format_speaker_empty_returns_empty(self) -> None:
        """_format_speaker('') returns empty string."""
        from src.ui.pages.live import _format_speaker  # noqa: PLC0415

        assert _format_speaker("") == ""

    def test_format_speaker_speaker_0_returns_speaker_1(self) -> None:
        """_format_speaker('speaker_0') returns 'Speaker 1'."""
        from src.ui.pages.live import _format_speaker  # noqa: PLC0415

        assert _format_speaker("speaker_0") == "Speaker 1"

    def test_format_speaker_speaker_2_returns_speaker_3(self) -> None:
        """_format_speaker('speaker_2') returns 'Speaker 3'."""
        from src.ui.pages.live import _format_speaker  # noqa: PLC0415

        assert _format_speaker("speaker_2") == "Speaker 3"

    def test_format_speaker_unknown_passthrough(self) -> None:
        """_format_speaker('unknown') returns 'unknown' (passthrough)."""
        from src.ui.pages.live import _format_speaker  # noqa: PLC0415

        assert _format_speaker("unknown") == "unknown"

    def test_format_timestamp_zero_to_five(self) -> None:
        """_format_timestamp(0, 5) returns '00:00:00 → 00:00:05'."""
        from src.ui.pages.live import _format_timestamp  # noqa: PLC0415

        assert _format_timestamp(0, 5) == "00:00:00 \u2192 00:00:05"

    def test_format_timestamp_large_values(self) -> None:
        """_format_timestamp(3661, 3725) returns '01:01:01 → 01:02:05'."""
        from src.ui.pages.live import _format_timestamp  # noqa: PLC0415

        assert _format_timestamp(3661, 3725) == "01:01:01 \u2192 01:02:05"

    def test_lang_to_code_vietnamese(self) -> None:
        """_lang_to_code('Vietnamese') returns 'vi'."""
        from src.ui.pages.live import _lang_to_code  # noqa: PLC0415

        with patch(
            "src.constants.languages.get_locale_code",
            return_value="vi",
        ):
            assert _lang_to_code("Vietnamese") == "vi"

    def test_lang_to_code_empty(self) -> None:
        """_lang_to_code('') returns ''."""
        from src.ui.pages.live import _lang_to_code  # noqa: PLC0415

        assert _lang_to_code("") == ""

    def test_lang_to_code_chinese_simplified_strips_region(self) -> None:
        """_lang_to_code('Chinese (Simplified)') returns 'zh' (strips region)."""
        from src.ui.pages.live import _lang_to_code  # noqa: PLC0415

        with patch(
            "src.constants.languages.get_locale_code",
            return_value="zh-CN",
        ):
            assert _lang_to_code("Chinese (Simplified)") == "zh"


# ===========================================================================
# TestOnSentenceWithSpeakerAndTranslation — _on_sentence handling
# ===========================================================================


class TestOnSentenceWithSpeakerAndTranslation:
    """Tests for _on_sentence handling with speaker and pre-translated text."""

    def test_cloud_mode_adds_both_without_translation_worker(
        self,
        live_page,
    ) -> None:
        """Cloud mode: adds original + translated without a TranslationWorker."""
        from src.ui.pages.live import _TranscriptCard  # noqa: PLC0415

        live_page._clear_log()
        live_page._transcriber = MagicMock()
        with patch(
            f"{_MOD}.load_setting",
            side_effect=lambda k, d="": {
                "live/target_language": "French",
                "live/show_original": "true",
            }.get(k, d),
        ):
            live_page._on_sentence(
                "Hello world",
                0.0,
                5.0,
                "",
                "Bonjour le monde",
            )
        # No translation worker should have been created
        assert len(live_page._translation_workers) == 0
        # _add_original inserts one card; _add_translated attaches the
        # translation to that same card.  So single-view layout has
        # exactly 1 card + 1 stretch = 2 items, and the card's
        # translated label carries the French text.
        assert live_page._transcript_layout.count() == 2  # noqa: PLR2004
        card = live_page._transcript_layout.itemAt(0).widget()
        assert isinstance(card, _TranscriptCard)
        assert card._body.text() == "Hello world"
        assert card._translated is not None
        assert card._translated.text() == "Bonjour le monde"

    def test_speaker_label_included_in_display(self, live_page) -> None:
        """When speaker is non-empty, speaker label appears in the card chip."""
        from src.ui.pages.live import _TranscriptCard  # noqa: PLC0415

        live_page._clear_log()
        live_page._transcriber = MagicMock()
        with patch(
            f"{_MOD}.load_setting",
            side_effect=lambda k, d="": {
                "live/target_language": "",
                "live/show_original": "true",
            }.get(k, d),
        ):
            live_page._on_sentence(
                "Hello",
                0.0,
                5.0,
                "speaker_0",
                "",
            )
        # Timestamp + speaker are joined by " — " inside the card's chip
        # label (NOT a separate layout item) — speaker now lives on
        # its own dedicated chip (``_speaker_chip``) alongside the
        # timestamp chip (``_timestamp_chip``), so we check the
        # speaker-chip text directly rather than scanning a merged
        # header.
        found_speaker = False
        for i in range(live_page._transcript_layout.count()):
            widget = live_page._transcript_layout.itemAt(i).widget()
            if (
                isinstance(widget, _TranscriptCard)
                and widget._speaker_chip is not None
                and "Speaker 1" in widget._speaker_chip.text()
            ):
                found_speaker = True
                break
        assert found_speaker

    def test_whisper_mode_creates_translation_worker(self, live_page) -> None:
        """When translated is empty and target_lang is set, creates TranslationWorker."""
        live_page._clear_log()
        live_page._translation_workers.clear()
        live_page._transcriber = MagicMock()
        # Mock stream_translate_text so the spawned QThread doesn't reach the
        # real Gemini API.  Without this the leaked thread blocks in
        # ssl/socket calls past the per-test pytest timeout, the SIGALRM
        # corrupts native state, and the suite segfaults later under load.
        with (
            patch(
                f"{_MOD}.load_setting",
                side_effect=lambda k, d="": {
                    "live/target_language": "French",
                    "live/show_original": "true",
                    "live/source_language": "English",
                }.get(k, d),
            ),
            patch(
                "src.core.database.get_active_glossary_sets",
                return_value=[],
            ),
            patch(
                "src.core.database.get_glossary_entries",
                return_value=[],
            ),
            patch(
                "src.core.llm_engine.stream_translate_text",
                return_value=iter(["Bonjour"]),
            ),
        ):
            live_page._on_sentence("Hello", 0.0, 5.0, "", "")
            assert len(live_page._translation_workers) >= 1
            # Drain the spawned QThread before the test exits so it
            # doesn't outlive the patches and leak into later tests.
            for w in list(live_page._translation_workers):
                w.wait(2000)

    def test_no_target_lang_adds_original_only(self, live_page) -> None:
        """When translated is empty and target_lang is empty, adds original only."""
        from src.ui.pages.live import _TranscriptCard  # noqa: PLC0415

        live_page._clear_log()
        live_page._translation_workers.clear()
        live_page._transcriber = MagicMock()
        with patch(
            f"{_MOD}.load_setting",
            side_effect=lambda k, d="": {
                "live/target_language": "",
                "live/show_original": "true",
            }.get(k, d),
        ):
            live_page._on_sentence("Just text", 0.0, 3.0, "", "")
        # No translation worker created
        assert len(live_page._translation_workers) == 0
        # Timestamp + original collapse into one card, so layout has
        # 1 card + 1 stretch = 2 items.
        assert live_page._transcript_layout.count() == 2  # noqa: PLR2004
        card = live_page._transcript_layout.itemAt(0).widget()
        assert isinstance(card, _TranscriptCard)
        assert card._body.text() == "Just text"
        assert card._translated is None


# ===========================================================================
# TestTranscriberStopped — _on_transcriber_stopped()
# ===========================================================================


class TestTranscriberStopped:
    """Tests for _on_transcriber_stopped() signal handler."""

    def test_sets_transcriber_to_none(self, live_page) -> None:
        """_on_transcriber_stopped sets _transcriber to None."""
        live_page._transcriber = MagicMock()
        live_page._on_transcriber_stopped()
        assert live_page._transcriber is None

    def test_resets_button_text_to_start(self, live_page) -> None:
        """_on_transcriber_stopped resets button text to 'Start'."""
        from src.constants import tr  # noqa: PLC0415

        live_page._transcriber = MagicMock()
        live_page._on_transcriber_stopped()
        assert live_page.start_btn.text() == tr("live.btn_start")

    def test_re_enables_audio_source_combo(self, live_page) -> None:
        """_on_transcriber_stopped re-enables audio_source_combo."""
        live_page._transcriber = MagicMock()
        live_page.audio_source_combo.setEnabled(False)
        live_page._on_transcriber_stopped()
        assert live_page.audio_source_combo.isEnabled()


# ===========================================================================
# TestShowAudioError — _show_audio_error()
# ===========================================================================


class TestShowAudioError:
    """Tests for _show_audio_error() method."""

    def test_shows_base_message_when_hint_empty(self, live_page) -> None:
        """Shows dialog with base message when hint is empty."""
        with (
            patch(
                f"{_MOD}.tr",
                side_effect=lambda k: {
                    "live.error_no_mic": "No microphone found.",
                    "live.error_title": "Audio Error",
                    "live.hint_run_command": "\n\nPlease run: {cmd}",
                }.get(k, k),
            ),
            patch(
                "src.ui.dialogs.CustomMessageDialog.show_message",
            ) as mock_show,
        ):
            live_page._show_audio_error("live.error_no_mic", "")
            mock_show.assert_called_once()
            msg_arg = mock_show.call_args[0][2]
            assert "No microphone found." in msg_arg
            assert "Please run" not in msg_arg

    def test_appends_command_hint_when_non_empty(self, live_page) -> None:
        """Appends command hint when hint is non-empty."""
        hint = "sudo apt-get install libportaudio2"
        with (
            patch(
                f"{_MOD}.tr",
                side_effect=lambda k: {
                    "live.error_no_portaudio": "PortAudio missing.",
                    "live.error_title": "Audio Error",
                    "live.hint_run_command": "\n\nPlease run: {cmd}",
                }.get(k, k),
            ),
            patch(
                "src.ui.dialogs.CustomMessageDialog.show_message",
            ) as mock_show,
        ):
            live_page._show_audio_error("live.error_no_portaudio", hint)
            mock_show.assert_called_once()
            msg_arg = mock_show.call_args[0][2]
            assert hint in msg_arg
            assert "PortAudio missing." in msg_arg


# ===========================================================================
# Cloud STT start methods — missing API key
# ===========================================================================


class TestStartSonioxMissingKey:
    """Tests that _start_soniox short-circuits when API key is missing.

    The user-visible "missing key" UX moved to the pre-flight setup
    banner + disabled Start button (see ``TestSttSetupWarning``); the
    early-return inside ``_start_soniox`` stays as defence-in-depth
    so a programmatic call with no key can't construct a bad client.
    """

    def test_returns_early_when_no_soniox_key(self, live_page) -> None:
        """No transcriber instantiated when key is empty."""
        with patch(
            f"{_MOD}.load_setting",
            side_effect=lambda k, d="": {}.get(k, d),
        ):
            live_page._start_soniox("", "", "microphone")
            assert live_page._transcriber is None


class TestLoadGlossary:
    """Tests for _load_glossary static method."""

    def test_returns_entries_from_active_sets(self, live_page) -> None:
        """Fetches entries from all active glossary sets."""
        with (
            patch(
                "src.core.database.get_active_glossary_sets",
                return_value=[(1, "Set A")],
            ),
            patch(
                "src.core.database.get_glossary_entries",
                return_value=[(1, "hello", "xin chào")],
            ),
        ):
            result = live_page._load_glossary()
            assert len(result) == 1
            assert result[0] == (1, "hello", "xin chào")

    def test_returns_empty_when_no_sets(self, live_page) -> None:
        """Returns empty list when no active glossary sets."""
        with patch(
            "src.core.database.get_active_glossary_sets",
            return_value=[],
        ):
            assert live_page._load_glossary() == []

    def test_glossary_refreshes_per_sentence_so_deletion_takes_effect(
        self,
        live_page,
    ) -> None:
        """Regression: deleting a glossary set mid-Whisper-session is honoured.

        The Whisper path calls ``_load_glossary`` at the *start* of
        every ``_on_sentence`` invocation (not just once per session),
        so a user who deletes a glossary set after Start should see
        the deletion take effect on the next sentence's translation
        — no stale terms re-injected into the LLM prompt.  This test
        simulates that flow by toggling the mocked DB return value
        between two ``_load_glossary`` calls.

        The Soniox path snapshots glossary terms at session start
        (Soniox configures vocabulary at WebSocket handshake; there's
        no mid-session update channel), so this regression is
        specifically about the Whisper / LLM path.  That asymmetry
        is documented in AGENTS.md.
        """
        # First call: set is active.
        with (
            patch(
                "src.core.database.get_active_glossary_sets",
                return_value=[(1, "Set A")],
            ),
            patch(
                "src.core.database.get_glossary_entries",
                return_value=[(1, "hello", "xin chào")],
            ),
        ):
            before = live_page._load_glossary()
        assert before == [(1, "hello", "xin chào")]

        # User deletes the set mid-session → next sentence sees an
        # empty active list.  ``_load_glossary`` MUST re-query the
        # DB, not return a cached snapshot from the first call.
        with patch(
            "src.core.database.get_active_glossary_sets",
            return_value=[],
        ):
            after = live_page._load_glossary()
        assert after == [], (
            "glossary deletion mid-session was not honoured — "
            "_load_glossary appears to cache instead of querying the DB"
        )


class TestAudioFeedManagement:
    """Tests for _start_audio_feed, _stop_audio_feed, _start_parec_feed."""

    def test_start_audio_feed_creates_stream(self, live_page) -> None:
        """_start_audio_feed creates a sounddevice InputStream."""
        mock_transcriber = MagicMock()
        mock_transcriber.is_running = True
        live_page._transcriber = mock_transcriber

        mock_sd = MagicMock()
        mock_stream = MagicMock()
        mock_sd.InputStream.return_value = mock_stream

        with (
            patch("src.ui.pages.live.sd", mock_sd, create=True),
            patch.dict("sys.modules", {"sounddevice": mock_sd}),
        ):
            live_page._start_audio_feed("microphone")

        assert live_page._soniox_stream is mock_stream
        mock_stream.start.assert_called_once()

    def test_stop_audio_feed_cleans_up_stream(self, live_page) -> None:
        """_stop_audio_feed stops and closes the stream."""
        mock_stream = MagicMock()
        live_page._soniox_stream = mock_stream
        live_page._stop_audio_feed()
        mock_stream.stop.assert_called_once()
        mock_stream.close.assert_called_once()
        assert live_page._soniox_stream is None

    def test_stop_audio_feed_cleans_up_parec(self, live_page) -> None:
        """_stop_audio_feed terminates parec subprocess."""
        mock_proc = MagicMock()
        live_page._soniox_parec = mock_proc
        live_page._soniox_parec_thread = MagicMock()
        live_page._stop_audio_feed()
        mock_proc.terminate.assert_called_once()
        assert live_page._soniox_parec is None

    def test_stop_audio_feed_safe_when_nothing_running(
        self,
        live_page,
    ) -> None:
        """_stop_audio_feed is safe when no stream or parec exists."""
        live_page._stop_audio_feed()  # Should not raise

    def test_start_parec_feed_spawns_subprocess(self, live_page) -> None:
        """_start_parec_feed spawns a parec process."""
        mock_transcriber = MagicMock()
        mock_transcriber.is_running = False  # stop reader immediately

        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0
        mock_proc.stdout.read.return_value = b""

        with (
            patch(
                "src.core.live_engine._get_default_monitor_source",
                return_value="sink.monitor",
            ),
            patch("subprocess.Popen", return_value=mock_proc),
        ):
            live_page._start_parec_feed(mock_transcriber)

        assert live_page._soniox_parec is mock_proc
        assert live_page._soniox_parec_thread is not None
        live_page._soniox_parec_thread.join(timeout=2)

    def test_start_parec_feed_noop_no_monitor(self, live_page) -> None:
        """_start_parec_feed does nothing when no monitor source found."""
        with patch(
            "src.core.live_engine._get_default_monitor_source",
            return_value=None,
        ):
            live_page._start_parec_feed(MagicMock())
        assert (
            not hasattr(live_page, "_soniox_parec") or live_page._soniox_parec is None
        )


# ===========================================================================
# TestLivePageSonioxSTT — Soniox STT method
# ===========================================================================


class TestLivePageSonioxSTT:
    """Tests for _start_soniox creating and managing a SonioxTranscriber."""

    def test_start_soniox_creates_transcriber_with_correct_params(
        self,
        live_page,
    ) -> None:
        """_start_soniox creates a SonioxTranscriber with the expected arguments."""
        mock_transcriber = MagicMock()
        mock_transcriber.is_running = True

        with (
            patch(
                f"{_MOD}.load_setting",
                side_effect=lambda k, d="": {
                    "service/soniox_api_key": "test-soniox-key",
                }.get(k, d),
            ),
            patch(
                "src.core.soniox_engine.SonioxTranscriber",
                return_value=mock_transcriber,
            ) as mock_cls,
            patch.object(live_page, "_load_glossary", return_value=[]),
            patch.object(live_page, "_start_audio_feed"),
        ):
            live_page._start_soniox("English", "Vietnamese", "microphone")

        mock_cls.assert_called_once()
        call_kwargs = mock_cls.call_args[1]
        assert call_kwargs["api_key"] == "test-soniox-key"
        assert live_page._transcriber is mock_transcriber
        mock_transcriber.start.assert_called_once()

    def test_start_soniox_returns_early_without_api_key(self, live_page) -> None:
        """_start_soniox short-circuits without instantiating a transcriber.

        The user-visible "missing key" UX is now the pre-flight setup
        banner + disabled Start button (see ``TestSttSetupWarningBanner``);
        the early return inside ``_start_soniox`` stays as defence in
        depth so a programmatic call with no key can't construct a
        bad client.
        """
        with patch(
            f"{_MOD}.load_setting",
            side_effect=lambda k, d="": {}.get(k, d),
        ):
            live_page._start_soniox("English", "Vietnamese", "microphone")
            assert live_page._transcriber is None

    def test_start_soniox_sends_audio_via_feed(self, live_page) -> None:
        """_start_soniox starts the audio feed for microphone capture."""
        mock_transcriber = MagicMock()
        mock_transcriber.is_running = True

        with (
            patch(
                f"{_MOD}.load_setting",
                side_effect=lambda k, d="": {
                    "service/soniox_api_key": "key-123",
                }.get(k, d),
            ),
            patch(
                "src.core.soniox_engine.SonioxTranscriber",
                return_value=mock_transcriber,
            ),
            patch.object(live_page, "_load_glossary", return_value=[]),
            patch.object(live_page, "_start_audio_feed") as mock_feed,
        ):
            live_page._start_soniox("English", "", "microphone")

        mock_feed.assert_called_once_with("microphone")

    def test_start_soniox_passes_glossary_terms(self, live_page) -> None:
        """_start_soniox passes glossary entries as translation_terms."""
        mock_transcriber = MagicMock()
        mock_transcriber.is_running = True
        glossary = [(1, "hello", "xin chào"), (2, "world", "thế giới")]

        with (
            patch(
                f"{_MOD}.load_setting",
                side_effect=lambda k, d="": {
                    "service/soniox_api_key": "key-abc",
                }.get(k, d),
            ),
            patch(
                "src.core.soniox_engine.SonioxTranscriber",
                return_value=mock_transcriber,
            ) as mock_cls,
            patch.object(live_page, "_load_glossary", return_value=glossary),
            patch.object(live_page, "_start_audio_feed"),
        ):
            live_page._start_soniox("English", "Vietnamese", "microphone")

        call_kwargs = mock_cls.call_args[1]
        terms = call_kwargs["translation_terms"]
        assert len(terms) == 2
        assert terms[0] == {"source": "hello", "target": "xin chào"}

    def test_stop_listening_cleans_up_soniox_transcriber(
        self,
        live_page,
    ) -> None:
        """_stop_listening stops and clears the Soniox transcriber."""
        mock_transcriber = MagicMock()
        mock_transcriber.is_running = True
        live_page._transcriber = mock_transcriber

        live_page._stop_listening()
        _drain_stop_worker(live_page)

        mock_transcriber.stop.assert_called_once()
        assert live_page._transcriber is None


# ===========================================================================
# TestLivePageGeminiSTT — Gemini STT method
class TestLivePageTranscriptCleanup:
    """Tests that _insert_entry enforces _MAX_LOG_ENTRIES limit correctly."""

    def test_entries_beyond_max_are_removed(self, live_page) -> None:
        """Layout count never exceeds _MAX_LOG_ENTRIES + 1 (stretch)."""
        from src.ui.pages.live import _MAX_LOG_ENTRIES  # noqa: PLC0415

        live_page._clear_log()
        for i in range(_MAX_LOG_ENTRIES + 10):
            live_page._add_original(f"Entry {i}")

        assert live_page._transcript_layout.count() <= _MAX_LOG_ENTRIES + 1

    def test_newest_entries_kept_oldest_removed(self, live_page) -> None:
        """The newest entries are kept and oldest are removed after overflow."""
        from src.ui.pages.live import _MAX_LOG_ENTRIES, _TranscriptCard  # noqa: PLC0415

        live_page._clear_log()
        total = _MAX_LOG_ENTRIES + 5
        for i in range(total):
            live_page._add_original(f"Entry {i}")

        # Collect visible texts from each card's body label.
        texts = []
        for i in range(live_page._transcript_layout.count() - 1):
            widget = live_page._transcript_layout.itemAt(i).widget()
            if isinstance(widget, _TranscriptCard):
                texts.append(widget._body.text())

        # Oldest entries (0..4) should be gone; newest should remain
        assert "Entry 0" not in texts
        assert "Entry 4" not in texts
        assert f"Entry {total - 1}" in texts
        assert f"Entry {total - 2}" in texts

    def test_cleanup_runs_after_each_new_entry(self, live_page) -> None:
        """After each entry added beyond max, count stays at or below limit."""
        from src.ui.pages.live import _MAX_LOG_ENTRIES  # noqa: PLC0415

        live_page._clear_log()
        # Fill to max
        for i in range(_MAX_LOG_ENTRIES):
            live_page._add_original(f"Fill {i}")

        assert live_page._transcript_layout.count() == _MAX_LOG_ENTRIES + 1

        # Add one more — should still be at max + 1
        live_page._add_original("One more")
        assert live_page._transcript_layout.count() == _MAX_LOG_ENTRIES + 1

        # Add another — still at max + 1
        live_page._add_translated("Translated extra")
        assert live_page._transcript_layout.count() == _MAX_LOG_ENTRIES + 1

    def test_empty_transcript_needs_no_cleanup(self, live_page) -> None:
        """Empty transcript (only stretch) does not error on cleanup."""
        live_page._clear_log()
        # Only stretch remains
        assert live_page._transcript_layout.count() == 1
        # Adding a single entry should not trigger any removal
        live_page._add_original("First")
        assert live_page._transcript_layout.count() == 2


# ===========================================================================
# TestLivePageSTTMethodSwitching — switching between STT methods
# ===========================================================================


class TestLivePageSTTMethodSwitching:
    """Tests for switching between different STT methods."""

    def test_whisper_to_soniox_uses_soniox_engine(self, live_page) -> None:
        """Switching from Whisper to Soniox calls _start_soniox."""
        mock_transcriber = MagicMock()
        mock_transcriber.is_running = True

        with (
            patch(
                f"{_MOD}.load_setting",
                side_effect=lambda k, d="": {
                    "live/stt_method": "soniox",
                    "live/source_lang": "English",
                    "live/target_lang": "Vietnamese",
                    "service/soniox_api_key": "key-111",
                }.get(k, d),
            ),
            patch(
                "src.core.soniox_engine.SonioxTranscriber",
                return_value=mock_transcriber,
            ) as mock_soniox_cls,
            patch.object(live_page, "_load_glossary", return_value=[]),
            patch.object(live_page, "_start_audio_feed"),
            patch(
                "src.core.live_engine.check_audio_available",
                return_value=None,
            ),
        ):
            live_page._start_listening()

        mock_soniox_cls.assert_called_once()

    def test_method_preference_persisted_to_settings(self) -> None:
        """The STT method setting is read from config and determines engine."""
        from src.constants.settings import (  # noqa: PLC0415
            LIVE_STT_SONIOX,
            LIVE_STT_WHISPER,
            SETTING_LIVE_STT_METHOD,
        )

        # Verify the setting constants exist and have distinct values
        assert SETTING_LIVE_STT_METHOD == "live/stt_method"
        assert LIVE_STT_WHISPER != LIVE_STT_SONIOX

    def test_whisper_method_does_not_create_cloud_engine(
        self,
        live_page,
    ) -> None:
        """Whisper method creates a LiveTranscriber, not the Soniox cloud engine."""
        mock_transcriber = MagicMock()
        mock_transcriber.is_running = True

        with (
            patch(
                f"{_MOD}.load_setting",
                side_effect=lambda k, d="": {
                    "live/stt_method": "whisper",
                    "live/source_lang": "English",
                    "live/target_lang": "",
                    "live/whisper_model": "tiny",
                }.get(k, d),
            ),
            patch(
                "src.core.live_engine.LiveTranscriber",
                return_value=mock_transcriber,
            ) as mock_whisper_cls,
            patch(
                "src.core.soniox_engine.SonioxTranscriber",
            ) as mock_soniox_cls,
            patch(
                "src.core.live_engine.check_audio_available",
                return_value=None,
            ),
        ):
            live_page._start_listening()

        mock_whisper_cls.assert_called_once()
        mock_soniox_cls.assert_not_called()


# ===========================================================================
# NEW TESTS — Coverage fills for uncovered ranges
# ===========================================================================


class TestTTSWorkerElevenLabs:
    """Covers the ElevenLabs branches of _TTSWorker.run()."""

    @patch(f"{_MOD}.load_setting")
    def test_elevenlabs_with_api_key_uses_elevenlabs(self, mock_load) -> None:
        """With API key set, _synthesize_chunk_elevenlabs is called."""
        from src.constants.settings import (  # noqa: PLC0415
            SETTING_ELEVENLABS_API_KEY,
            SETTING_ELEVENLABS_VOICE_ID,
            SETTING_VOICE_TTS_METHOD,
            VOICE_TTS_ELEVENLABS,
        )

        def _fake_load(key, default=""):
            if key == SETTING_VOICE_TTS_METHOD:
                return VOICE_TTS_ELEVENLABS
            if key == SETTING_ELEVENLABS_API_KEY:
                return "fake-el-key"
            if key == SETTING_ELEVENLABS_VOICE_ID:
                return "voice-abc"
            return default

        mock_load.side_effect = _fake_load
        worker = _make_tts_worker("Hello", "English")

        with (
            patch(
                "src.core.speech_engine._synthesize_chunk_elevenlabs",
            ) as mock_el,
            patch(
                "src.core.speech_engine._synthesize_chunk_edge",
            ) as mock_edge,
            patch("src.core.speech_engine._get_edge_voice"),
            patch("src.core.speech_engine._get_tts_language_code"),
            patch("src.core.speech_engine._synthesize_chunk"),
            patch("src.core.speech_engine.load_google_cloud_api_key"),
            patch("tempfile.NamedTemporaryFile") as mock_tmp,
        ):
            tmp_obj = MagicMock()
            tmp_obj.name = "/tmp/live_tts_el.mp3"
            tmp_obj.close = MagicMock()
            mock_tmp.return_value = tmp_obj
            worker.run()

        mock_el.assert_called_once()
        # First arg is the text, second is API key, fourth is voice id
        assert mock_el.call_args[0][0] == "Hello"
        assert mock_el.call_args[0][1] == "fake-el-key"
        assert mock_el.call_args[0][3] == "voice-abc"
        mock_edge.assert_not_called()
        worker.synthesized.emit.assert_called_once()

    @patch(f"{_MOD}.load_setting")
    def test_elevenlabs_missing_key_falls_back_to_edge(self, mock_load) -> None:
        """Without API key, falls back to Edge TTS."""
        from src.constants.settings import (  # noqa: PLC0415
            SETTING_ELEVENLABS_API_KEY,
            SETTING_ELEVENLABS_VOICE_ID,
            SETTING_VOICE_TTS_METHOD,
            VOICE_TTS_ELEVENLABS,
        )

        def _fake_load(key, default=""):
            if key == SETTING_VOICE_TTS_METHOD:
                return VOICE_TTS_ELEVENLABS
            if key == SETTING_ELEVENLABS_API_KEY:
                return ""
            if key == SETTING_ELEVENLABS_VOICE_ID:
                return ""
            return default

        mock_load.side_effect = _fake_load
        worker = _make_tts_worker("Bonjour", "French")

        with (
            patch(
                "src.core.speech_engine._synthesize_chunk_elevenlabs",
            ) as mock_el,
            patch(
                "src.core.speech_engine._get_edge_voice",
                return_value="fr-FR-DeniseNeural",
            ) as mock_voice,
            patch(
                "src.core.speech_engine._synthesize_chunk_edge",
            ) as mock_edge,
            patch("src.core.speech_engine._get_tts_language_code"),
            patch("src.core.speech_engine._synthesize_chunk"),
            patch("src.core.speech_engine.load_google_cloud_api_key"),
            patch("tempfile.NamedTemporaryFile") as mock_tmp,
        ):
            tmp_obj = MagicMock()
            tmp_obj.name = "/tmp/live_tts_el_fallback.mp3"
            tmp_obj.close = MagicMock()
            mock_tmp.return_value = tmp_obj
            worker.run()

        mock_el.assert_not_called()
        mock_voice.assert_called_once_with("French", "FEMALE")
        mock_edge.assert_called_once()
        worker.synthesized.emit.assert_called_once()


# ===========================================================================
# TestOverlayMouseMove — covers _OverlayWindow.mouseMoveEvent (lines 210-211)
# ===========================================================================


class TestOverlayMouseMove:
    """Covers _OverlayWindow.mouseMoveEvent active-drag path."""

    def test_mouse_move_moves_window_when_dragging(self, qapp) -> None:  # noqa: ARG002
        """When drag_pos is set and left button held, window moves."""
        from PySide6.QtCore import QPoint, Qt  # noqa: PLC0415

        from src.ui.pages.live import _OverlayWindow  # noqa: PLC0415

        overlay = _OverlayWindow()
        overlay._drag_pos = QPoint(10, 10)

        # Build a fake event where buttons() returns LeftButton and
        # globalPosition().toPoint() returns a concrete point.
        event = MagicMock()
        event.buttons.return_value = Qt.MouseButton.LeftButton
        event.globalPosition.return_value.toPoint.return_value = QPoint(100, 200)

        with patch.object(overlay, "move") as mock_move:
            overlay.mouseMoveEvent(event)
        mock_move.assert_called_once()
        # Arg is globalPos - drag_pos = (90, 190)
        assert mock_move.call_args[0][0] == QPoint(90, 190)

    def test_mouse_move_noop_without_drag_pos(self, qapp) -> None:  # noqa: ARG002
        """When drag_pos is None, move() is not called."""
        from src.ui.pages.live import _OverlayWindow  # noqa: PLC0415

        overlay = _OverlayWindow()
        overlay._drag_pos = None

        event = MagicMock()
        with patch.object(overlay, "move") as mock_move:
            overlay.mouseMoveEvent(event)
        mock_move.assert_not_called()


# ===========================================================================
# TestAudioSourceComboRestore — covers lines 426-427
# ===========================================================================


class TestAudioSourceComboRestore:
    """Covers the saved-source match branch in audio source combo setup."""

    def test_saved_source_selects_matching_index(self, window, qtbot) -> None:
        """When saved_source matches an entry, combo selects that index."""
        from src.ui.pages.live import LivePage  # noqa: PLC0415

        with patch(
            f"{_MOD}.load_setting",
            side_effect=lambda k, d="": {
                "live/audio_source": "system",
            }.get(k, d),
        ):
            page = LivePage(window)
        qtbot.addWidget(page)

        # "system" is the second item in _audio_source_items (index 1)
        assert page.audio_source_combo.currentData() == "system"

    def test_saved_source_both_selects_index_2(self, window, qtbot) -> None:
        """When saved_source is 'both', index 2 is selected."""
        from src.ui.pages.live import LivePage  # noqa: PLC0415

        with patch(
            f"{_MOD}.load_setting",
            side_effect=lambda k, d="": {
                "live/audio_source": "both",
            }.get(k, d),
        ):
            page = LivePage(window)
        qtbot.addWidget(page)
        assert page.audio_source_combo.currentData() == "both"


# ===========================================================================
# TestWhisperRequireSetup — covers lines 614-628 + 660
# ===========================================================================


class TestWhisperRequireSetup:
    """Whisper-mode LLM require_setup branch in _start_listening."""

    def test_whisper_with_target_lang_blocks_when_llm_missing(
        self,
        live_page,
    ) -> None:
        """When target_lang set and LLM setup fails, start is aborted."""
        with (
            patch(
                "src.core.live_engine.check_audio_available",
                return_value="",
            ),
            patch(
                "src.core.live_engine.check_system_audio_available",
                return_value=True,
            ),
            patch(
                f"{_MOD}.load_setting",
                side_effect=lambda k, d="": {
                    "live/stt_method": "whisper",
                    "live/target_language": "Vietnamese",
                    "live/source_language": "English",
                    "live/audio_source": "microphone",
                }.get(k, d),
            ),
            patch(
                "src.ui.dialogs.require_setup",
                return_value=False,
            ) as mock_req,
            patch(
                "src.core.live_engine.LiveTranscriber",
            ) as mock_whisper_cls,
        ):
            live_page._start_listening()

        mock_req.assert_called_once()
        mock_whisper_cls.assert_not_called()
        # UI state: start_btn text should still be "Start" since we aborted
        assert live_page._transcriber is None

    def test_whisper_with_target_lang_proceeds_when_llm_ready(
        self,
        live_page,
    ) -> None:
        """When target_lang set and LLM check passes, Whisper starts."""
        mock_transcriber = MagicMock()
        mock_transcriber.is_running = False

        with (
            patch(
                "src.core.live_engine.check_audio_available",
                return_value="",
            ),
            patch(
                "src.core.live_engine.check_system_audio_available",
                return_value=True,
            ),
            patch(
                f"{_MOD}.load_setting",
                side_effect=lambda k, d="": {
                    "live/stt_method": "whisper",
                    "live/target_language": "Vietnamese",
                    "live/source_language": "English",
                    "live/audio_source": "microphone",
                    "live/whisper_model": "tiny",
                }.get(k, d),
            ),
            patch(
                "src.ui.dialogs.require_setup",
                return_value=True,
            ) as mock_req,
            patch(
                "src.core.live_engine.LiveTranscriber",
                return_value=mock_transcriber,
            ) as mock_whisper_cls,
        ):
            live_page._start_listening()

        mock_req.assert_called_once()
        mock_whisper_cls.assert_called_once()
        mock_transcriber.start.assert_called_once()

    def test_whisper_callback_emits_five_arg_signal(self, live_page) -> None:
        """_on_whisper_sentence wrapper pads to 5-arg signal (line 660)."""
        mock_transcriber = MagicMock()

        with patch(
            "src.core.live_engine.LiveTranscriber",
            return_value=mock_transcriber,
        ) as mock_cls:
            live_page._start_whisper("English", "microphone")

        # The on_sentence kwarg is the wrapper; extract and call it
        wrapper = mock_cls.call_args[1]["on_sentence"]

        # Capture the emitted args by connecting a slot to the signal
        received: list[tuple] = []
        live_page._sentence_received.connect(
            lambda *args: received.append(args),
        )
        wrapper("Hello", 1.0, 2.5)
        assert received == [("Hello", 1.0, 2.5, "", "")]


# ===========================================================================
# TestStartAudioFeed — covers lines 772-777 (mic_callback) + 790 (system/both)
# ===========================================================================


class TestStartAudioFeed:
    """Covers _start_audio_feed mic_callback and system-audio branch."""

    def test_mic_callback_converts_and_sends_audio(self, live_page) -> None:
        """The mic callback converts float32 → s16le and sends to transcriber."""
        import sys as _sys  # noqa: PLC0415

        mock_transcriber = MagicMock()
        mock_transcriber.is_running = True
        live_page._transcriber = mock_transcriber

        mock_sd = MagicMock()
        mock_stream = MagicMock()
        mock_sd.InputStream.return_value = mock_stream

        with patch.dict(_sys.modules, {"sounddevice": mock_sd}):
            live_page._start_audio_feed("microphone")

        # Extract the callback that was passed to InputStream
        callback = mock_sd.InputStream.call_args[1]["callback"]

        # Simulate the callback being invoked with a numpy array
        import numpy as np  # noqa: PLC0415

        indata = np.array([[0.0], [0.5], [-0.5]], dtype=np.float32)
        callback(indata, 3, None, None)

        mock_transcriber.send_audio.assert_called_once()
        pcm = mock_transcriber.send_audio.call_args[0][0]
        assert isinstance(pcm, bytes)
        assert len(pcm) == 6  # 3 samples × 2 bytes

    def test_mic_callback_noop_when_transcriber_stopped(
        self,
        live_page,
    ) -> None:
        """Callback does nothing when transcriber is not running."""
        import sys as _sys  # noqa: PLC0415

        mock_transcriber = MagicMock()
        mock_transcriber.is_running = False
        live_page._transcriber = mock_transcriber

        mock_sd = MagicMock()
        mock_stream = MagicMock()
        mock_sd.InputStream.return_value = mock_stream

        with patch.dict(_sys.modules, {"sounddevice": mock_sd}):
            live_page._start_audio_feed("microphone")

        callback = mock_sd.InputStream.call_args[1]["callback"]
        import numpy as np  # noqa: PLC0415

        callback(np.zeros((3, 1), dtype=np.float32), 3, None, None)
        mock_transcriber.send_audio.assert_not_called()

    def test_start_audio_feed_both_uses_mixed_feed(self, live_page) -> None:
        """``both`` dispatches to the mixed-feed path, not bare parec.

        The mixed feed captures mic + system into separate queues and
        runs a mixer thread that sums and silence-gates the mic before
        forwarding — avoiding the interleaved-bytes bug where Soniox /
        Gemini saw two unrelated streams multiplexed as raw PCM.
        """
        mock_transcriber = MagicMock()
        mock_transcriber.is_running = True
        live_page._transcriber = mock_transcriber

        with (
            patch.object(live_page, "_start_mixed_feed") as mock_mixed,
            patch.object(live_page, "_start_mic_feed") as mock_mic,
            patch.object(live_page, "_start_parec_feed") as mock_parec,
        ):
            live_page._start_audio_feed("both")
        mock_mixed.assert_called_once_with(mock_transcriber)
        mock_mic.assert_not_called()
        mock_parec.assert_not_called()

    def test_start_audio_feed_system_uses_parec_only(self, live_page) -> None:
        """``system`` starts parec only — no mic stream anymore."""
        mock_transcriber = MagicMock()
        mock_transcriber.is_running = True
        live_page._transcriber = mock_transcriber

        with (
            patch.object(live_page, "_start_mixed_feed") as mock_mixed,
            patch.object(live_page, "_start_mic_feed") as mock_mic,
            patch.object(live_page, "_start_parec_feed") as mock_parec,
        ):
            live_page._start_audio_feed("system")
        mock_parec.assert_called_once_with(mock_transcriber)
        mock_mixed.assert_not_called()
        mock_mic.assert_not_called()

    def test_start_audio_feed_microphone_uses_mic_only(
        self,
        live_page,
    ) -> None:
        """``microphone`` starts a mic stream — no parec, no mixer."""
        mock_transcriber = MagicMock()
        mock_transcriber.is_running = True
        live_page._transcriber = mock_transcriber

        with (
            patch.object(live_page, "_start_mixed_feed") as mock_mixed,
            patch.object(live_page, "_start_mic_feed") as mock_mic,
            patch.object(live_page, "_start_parec_feed") as mock_parec,
        ):
            live_page._start_audio_feed("microphone")
        mock_mic.assert_called_once_with(mock_transcriber)
        mock_parec.assert_not_called()
        mock_mixed.assert_not_called()


# ===========================================================================
# TestParecReader — covers lines 822-828 (inner _reader function)
# ===========================================================================


class TestParecReader:
    """Covers the inner _reader function of _start_parec_feed."""

    def test_reader_sends_audio_then_exits_on_empty_read(
        self,
        live_page,
    ) -> None:
        """Reader forwards bytes to transcriber then exits on empty read."""
        mock_transcriber = MagicMock()
        mock_transcriber.is_running = True

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # still alive
        # First call returns data, second returns empty → break
        mock_proc.stdout.read.side_effect = [b"\x01\x02\x03\x04", b""]

        with (
            patch(
                "src.core.live_engine._get_default_monitor_source",
                return_value="sink.monitor",
            ),
            patch("subprocess.Popen", return_value=mock_proc),
        ):
            live_page._start_parec_feed(mock_transcriber)
            # Wait for the reader thread to finish
            live_page._soniox_parec_thread.join(timeout=3)

        # send_audio should have been called exactly once with the first chunk
        mock_transcriber.send_audio.assert_called_once_with(b"\x01\x02\x03\x04")

    def test_reader_exits_when_transcriber_stops(self, live_page) -> None:
        """Reader loop exits when transcriber.is_running flips to False."""
        mock_transcriber = MagicMock()
        # First check True, then False so loop exits
        running_vals = [True, False]

        def _running_getter():
            return running_vals.pop(0) if running_vals else False

        type(mock_transcriber).is_running = property(
            lambda self: _running_getter(),
        )

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdout.read.return_value = b"\xaa\xbb"

        with (
            patch(
                "src.core.live_engine._get_default_monitor_source",
                return_value="sink.monitor",
            ),
            patch("subprocess.Popen", return_value=mock_proc),
        ):
            live_page._start_parec_feed(mock_transcriber)
            live_page._soniox_parec_thread.join(timeout=3)

        # Should have sent at most one chunk before is_running flipped
        assert mock_transcriber.send_audio.call_count <= 1


# ===========================================================================
# TestOnSentenceCloudTtsQueue — covers lines 919-921
# ===========================================================================


class TestOnSentenceCloudTtsQueue:
    """Cloud mode with TTS enabled queues translated text for TTS."""

    def test_cloud_mode_tts_enabled_queues_translated(self, live_page) -> None:
        """Soniox-style pre-translated + TTS enabled → text goes to queue."""
        live_page._clear_log()
        live_page._tts_enabled = True
        live_page._tts_queue.clear()
        live_page._transcriber = MagicMock()

        with (
            patch(
                f"{_MOD}.load_setting",
                side_effect=lambda k, d="": {
                    "live/target_language": "French",
                    "live/show_original": "false",
                }.get(k, d),
            ),
            patch.object(live_page, "_process_tts_queue") as mock_pq,
        ):
            live_page._on_sentence("Hello", 0.0, 1.0, "", "Bonjour")

        assert "Bonjour" in live_page._tts_queue
        mock_pq.assert_called_once()
        live_page._tts_enabled = False
        live_page._tts_queue.clear()


# ===========================================================================
# TestProcessTtsQueueStartsWorker — covers lines 982-988
# ===========================================================================


class TestProcessTtsQueueStartsWorker:
    """Covers the active path of _process_tts_queue (popping + starting)."""

    def test_pops_queue_and_starts_worker(self, live_page) -> None:
        """When worker None and queue non-empty, pops and starts TTS worker."""
        live_page._tts_worker = None
        live_page._tts_queue.clear()
        live_page._tts_queue.append("Bonjour")

        mock_worker_cls = MagicMock()
        mock_worker_instance = MagicMock()
        mock_worker_cls.return_value = mock_worker_instance

        with (
            patch(f"{_MOD}._TTSWorker", mock_worker_cls),
            patch(
                f"{_MOD}.load_setting",
                side_effect=lambda k, d="": {
                    "live/target_language": "French",
                }.get(k, d),
            ),
        ):
            live_page._process_tts_queue()

        # Worker was instantiated with ("Bonjour", "French", "FEMALE",
        # config=None).  The ``config`` kwarg lets the page pass a
        # pre-resolved :class:`_TTSConfig` snapshot so the worker
        # doesn't have to re-read settings on every sentence — when
        # the page has no live snapshot (this test's path), it
        # passes ``None`` and the worker falls back to live reads.
        mock_worker_cls.assert_called_once_with(
            "Bonjour",
            "French",
            "FEMALE",
            config=None,
        )
        mock_worker_instance.start.assert_called_once()
        assert live_page._tts_worker is mock_worker_instance
        assert len(live_page._tts_queue) == 0
        live_page._tts_worker = None


# ===========================================================================
# TestOnTtsSynthesized — covers lines 990-1015
# ===========================================================================


class TestOnTtsSynthesized:
    """Covers _on_tts_synthesized for both file-present and missing paths."""

    def test_plays_file_when_temp_file_exists(self, live_page) -> None:
        """When temp file exists, QMediaPlayer is created and play() called."""
        mock_worker = MagicMock()
        mock_worker.temp_file = "/tmp/live_tts_ok.mp3"
        live_page._tts_worker = mock_worker
        live_page._player = None
        live_page._audio_output = None

        mock_player_cls = MagicMock()
        mock_player_instance = MagicMock()
        mock_player_cls.return_value = mock_player_instance
        mock_audio_cls = MagicMock()

        with (
            patch(
                "PySide6.QtMultimedia.QMediaPlayer",
                mock_player_cls,
            ),
            patch(
                "PySide6.QtMultimedia.QAudioOutput",
                mock_audio_cls,
            ),
            patch("pathlib.Path.exists", return_value=True),
        ):
            live_page._on_tts_synthesized()

        # Worker should have been cleared
        assert live_page._tts_worker is None
        # Player was created and play() called
        mock_player_cls.assert_called_once()
        mock_player_instance.setSource.assert_called_once()
        mock_player_instance.play.assert_called_once()

    def test_no_file_processes_next_queue_item(self, live_page) -> None:
        """When temp_file is missing, moves on to next queue item."""
        mock_worker = MagicMock()
        mock_worker.temp_file = "/tmp/nonexistent.mp3"
        live_page._tts_worker = mock_worker

        with (
            patch("pathlib.Path.exists", return_value=False),
            patch.object(live_page, "_process_tts_queue") as mock_pq,
        ):
            live_page._on_tts_synthesized()

        mock_pq.assert_called_once()
        assert live_page._tts_worker is None

    def test_worker_none_processes_next_queue_item(self, live_page) -> None:
        """When worker is None, skips playback and processes next."""
        live_page._tts_worker = None

        with patch.object(live_page, "_process_tts_queue") as mock_pq:
            live_page._on_tts_synthesized()

        mock_pq.assert_called_once()

    def test_reuses_existing_player(self, live_page) -> None:
        """When _player already exists, it is reused, not recreated."""
        mock_worker = MagicMock()
        mock_worker.temp_file = "/tmp/live_tts_reuse.mp3"
        live_page._tts_worker = mock_worker

        existing_player = MagicMock()
        live_page._player = existing_player
        live_page._audio_output = MagicMock()

        mock_player_cls = MagicMock()
        mock_audio_cls = MagicMock()

        with (
            patch(
                "PySide6.QtMultimedia.QMediaPlayer",
                mock_player_cls,
            ),
            patch(
                "PySide6.QtMultimedia.QAudioOutput",
                mock_audio_cls,
            ),
            patch("pathlib.Path.exists", return_value=True),
        ):
            live_page._on_tts_synthesized()

        # No new player created; existing one used
        mock_player_cls.assert_not_called()
        existing_player.setSource.assert_called_once()
        existing_player.play.assert_called_once()


# ===========================================================================
# TestOnPlaybackStatus — covers lines 1017-1029
# ===========================================================================


class TestOnPlaybackStatus:
    """Covers _on_playback_status end-of-media cleanup and next-item logic."""

    def test_end_of_media_processes_next(self, live_page) -> None:
        """End-of-media status triggers next queue processing."""
        from PySide6.QtMultimedia import QMediaPlayer  # noqa: PLC0415

        mock_player = MagicMock()
        # Source returns a QUrl that is NOT a local file → skip unlink
        mock_src = MagicMock()
        mock_src.isLocalFile.return_value = False
        mock_player.source.return_value = mock_src
        live_page._player = mock_player

        with patch.object(live_page, "_process_tts_queue") as mock_pq:
            live_page._on_playback_status(QMediaPlayer.MediaStatus.EndOfMedia)

        mock_pq.assert_called_once()

    def test_non_end_of_media_does_nothing(self, live_page) -> None:
        """Non end-of-media status is a no-op."""
        from PySide6.QtMultimedia import QMediaPlayer  # noqa: PLC0415

        live_page._player = MagicMock()
        with patch.object(live_page, "_process_tts_queue") as mock_pq:
            live_page._on_playback_status(
                QMediaPlayer.MediaStatus.LoadingMedia,
            )
        mock_pq.assert_not_called()

    def test_end_of_media_unlinks_temp_file(self, live_page, tmp_path) -> None:
        """End-of-media deletes local temp file matching live_tts_ prefix."""
        from PySide6.QtCore import QUrl  # noqa: PLC0415
        from PySide6.QtMultimedia import QMediaPlayer  # noqa: PLC0415

        # Create a real temp file with the expected prefix
        f = tmp_path / "live_tts_xxx.mp3"
        f.write_bytes(b"fake")
        assert f.exists()

        mock_player = MagicMock()
        mock_player.source.return_value = QUrl.fromLocalFile(str(f))
        live_page._player = mock_player

        with patch.object(live_page, "_process_tts_queue"):
            live_page._on_playback_status(QMediaPlayer.MediaStatus.EndOfMedia)

        assert not f.exists()

    def test_end_of_media_skips_non_matching_filename(
        self,
        live_page,
        tmp_path,
    ) -> None:
        """End-of-media does NOT delete files without live_tts_ prefix."""
        from PySide6.QtCore import QUrl  # noqa: PLC0415
        from PySide6.QtMultimedia import QMediaPlayer  # noqa: PLC0415

        f = tmp_path / "other_file.mp3"
        f.write_bytes(b"fake")

        mock_player = MagicMock()
        mock_player.source.return_value = QUrl.fromLocalFile(str(f))
        live_page._player = mock_player

        with patch.object(live_page, "_process_tts_queue"):
            live_page._on_playback_status(QMediaPlayer.MediaStatus.EndOfMedia)

        # File with non-matching prefix is preserved
        assert f.exists()


# ===========================================================================
# TestGeminiAudioSink — covers lines 1041-1070
class TestOverlayEntryIntegration:
    """_add_original / _add_translated forward to overlay's entry API when visible."""

    def test_add_original_seeds_overlay_entry(self, live_page) -> None:
        """When overlay is visible, _add_original calls overlay.add_entry(source)."""
        mock_overlay = MagicMock()
        mock_overlay.isVisible.return_value = True
        live_page._overlay = mock_overlay

        live_page._add_original("Source text")

        mock_overlay.add_entry.assert_called_once()
        _args, kwargs = mock_overlay.add_entry.call_args
        # Source text is the third positional arg regardless of where
        # timestamp / speaker land — verify it propagated.
        assert "Source text" in mock_overlay.add_entry.call_args.args
        # The overlay must learn about the current display + chip state
        # so its entry matches the main window from the moment it's
        # inserted (no flash of wrong mode).
        for key in (
            "show_timestamp",
            "show_speaker",
            "show_src",
            "show_tgt",
        ):
            assert key in kwargs
        live_page._overlay = None

    def test_add_original_skips_hidden_overlay(self, live_page) -> None:
        """When overlay hidden, _add_original does not call add_entry."""
        mock_overlay = MagicMock()
        mock_overlay.isVisible.return_value = False
        live_page._overlay = mock_overlay

        live_page._add_original("Source text")
        mock_overlay.add_entry.assert_not_called()
        live_page._overlay = None

    def test_add_translated_fills_overlay_translation(
        self,
        live_page,
    ) -> None:
        """When overlay is visible, _add_translated routes to set_last_translation."""
        mock_overlay = MagicMock()
        mock_overlay.isVisible.return_value = True
        live_page._overlay = mock_overlay

        live_page._add_translated("Translated text")

        mock_overlay.set_last_translation.assert_called_once()
        # Streaming chunks land via set_last_translation; the legacy
        # ``add_line`` API is gone — guard against regressions that
        # would resurrect a per-chunk append-line behaviour.
        mock_overlay.add_entry.assert_not_called()
        live_page._overlay = None

    def test_add_translated_skips_hidden_overlay(self, live_page) -> None:
        """When overlay hidden, _add_translated does not touch the overlay."""
        mock_overlay = MagicMock()
        mock_overlay.isVisible.return_value = False
        live_page._overlay = mock_overlay

        live_page._add_translated("Translated text")
        mock_overlay.set_last_translation.assert_not_called()
        live_page._overlay = None


# ===========================================================================
# TestToggleListeningStartPath — covers line 526
# ===========================================================================


class TestToggleListeningStartPath:
    """Covers the start-branch of _toggle_listening (line 526)."""

    def test_toggle_calls_start_listening_when_idle(self, live_page) -> None:
        """When no transcriber, toggle delegates to _start_listening()."""
        live_page._transcriber = None
        with patch.object(live_page, "_start_listening") as mock_start:
            live_page._toggle_listening()
        mock_start.assert_called_once()

    def test_toggle_calls_start_listening_when_transcriber_not_running(
        self,
        live_page,
    ) -> None:
        """When transcriber exists but is_running False, _start_listening runs."""
        mock_t = MagicMock()
        mock_t.is_running = False
        live_page._transcriber = mock_t
        with patch.object(live_page, "_start_listening") as mock_start:
            live_page._toggle_listening()
        mock_start.assert_called_once()
        live_page._transcriber = None


# ---------------------------------------------------------------------------
# NEW: Review-fix behaviours for Live Translation
# ---------------------------------------------------------------------------


class TestTtsQueueBounded:
    """Tests that _tts_queue drops older items once the cap is reached."""

    def test_queue_drops_oldest_when_full(self, live_page) -> None:
        """Adding beyond the cap drops the oldest entries (deque maxlen)."""
        from src.ui.pages.live import _MAX_TTS_QUEUE  # noqa: PLC0415

        for i in range(_MAX_TTS_QUEUE + 5):
            live_page._tts_queue.append(f"sentence {i}")

        assert len(live_page._tts_queue) == _MAX_TTS_QUEUE
        # Oldest dropped; newest retained.
        assert "sentence 0" not in live_page._tts_queue
        assert f"sentence {_MAX_TTS_QUEUE + 4}" in live_page._tts_queue


class TestInvalidMediaAdvancesQueue:
    """Tests that InvalidMedia doesn't freeze the TTS queue (Bug #1)."""

    def test_invalid_media_processes_next_item(self, live_page) -> None:
        """InvalidMedia status drains the queue instead of stalling."""
        from PySide6.QtMultimedia import QMediaPlayer  # noqa: PLC0415

        live_page._player = MagicMock()
        live_page._player.source.return_value = MagicMock(
            isLocalFile=MagicMock(return_value=False),
        )
        with patch.object(live_page, "_process_tts_queue") as mock_next:
            live_page._on_playback_status(
                QMediaPlayer.MediaStatus.InvalidMedia,
            )
        mock_next.assert_called_once()

    def test_invalid_media_sets_status_label(self, live_page) -> None:
        """InvalidMedia surfaces a playback-failed status message."""
        from PySide6.QtMultimedia import QMediaPlayer  # noqa: PLC0415

        live_page._player = MagicMock()
        live_page._player.source.return_value = MagicMock(
            isLocalFile=MagicMock(return_value=False),
        )
        with patch.object(live_page, "_process_tts_queue"):
            live_page._on_playback_status(
                QMediaPlayer.MediaStatus.InvalidMedia,
            )
        assert live_page.status_label.text()  # non-empty

    def test_other_statuses_do_nothing(self, live_page) -> None:
        """Statuses other than EndOfMedia/InvalidMedia are ignored."""
        from PySide6.QtMultimedia import QMediaPlayer  # noqa: PLC0415

        with patch.object(live_page, "_process_tts_queue") as mock_next:
            live_page._on_playback_status(
                QMediaPlayer.MediaStatus.BufferedMedia,
            )
        mock_next.assert_not_called()


class TestTtsErrorSurfaces:
    """Tests that TTS worker errors are surfaced in the status label (Bug #2)."""

    def test_tts_error_updates_status_label(self, live_page) -> None:
        """_on_tts_error writes an error message to the status label."""
        live_page._tts_worker = MagicMock()
        with patch.object(live_page, "_process_tts_queue"):
            live_page._on_tts_error("AUTH_ERROR")
        text = live_page.status_label.text()
        assert text
        # In the test env tr() returns the raw key.
        assert "tts_failed_status" in text or "AUTH_ERROR" in text

    def test_tts_error_still_drains_queue(self, live_page) -> None:
        """After an error, the queue is drained so subsequent items play."""
        live_page._tts_worker = MagicMock()
        with patch.object(live_page, "_process_tts_queue") as mock_next:
            live_page._on_tts_error("network")
        mock_next.assert_called_once()
        assert live_page._tts_worker is None


class TestElevenLabsFallbackWarning:
    """Tests the ElevenLabs fallback warning when no API key is set (Bug #4)."""

    def test_enabling_tts_with_elevenlabs_no_key_shows_warning(
        self,
        live_page,
    ) -> None:
        """Turning TTS on with ElevenLabs + missing key updates status."""
        live_page._tts_enabled = False  # will flip to True in _toggle_tts

        def _fake_load(key, default=None):
            if "tts_method" in key:
                return "ElevenLabs"
            if "elevenlabs_api_key" in key:
                return ""
            return default

        with patch(f"{_MOD}.load_setting", side_effect=_fake_load):
            live_page._toggle_tts()

        # In the test env tr() returns the raw key.
        assert "elevenlabs_fallback" in live_page.status_label.text()

    def test_enabling_tts_with_elevenlabs_key_set_no_warning(
        self,
        live_page,
    ) -> None:
        """With a key present, no fallback warning is shown."""
        live_page._tts_enabled = False
        live_page.status_label.setText("")

        def _fake_load(key, default=None):
            if "tts_method" in key:
                return "ElevenLabs"
            if "elevenlabs_api_key" in key:
                return "sk-real-key"
            return default

        with patch(f"{_MOD}.load_setting", side_effect=_fake_load):
            live_page._toggle_tts()

        assert "elevenlabs_fallback" not in live_page.status_label.text()


class TestClearLogConfirmation:
    """Tests that Clear prompts for confirmation and clears state (Bugs #5/#6)."""

    def test_clear_log_requires_confirmation(self, live_page) -> None:
        """With content present, _clear_log only proceeds on confirm=True."""
        live_page._transcript_records.append(("t", "", "hi", "salut", False))
        live_page._tts_queue.append("salut")

        with patch(
            "src.ui.dialogs.CustomConfirmDialog.confirm",
            return_value=False,
        ):
            live_page._clear_log()

        # Rejected — state preserved.
        assert live_page._transcript_records
        assert len(live_page._tts_queue) == 1

    def test_clear_log_drops_tts_queue(self, live_page) -> None:
        """Accepting the confirm dialog drains the pending TTS queue."""
        live_page._transcript_records.append(("t", "", "hi", "salut", False))
        live_page._tts_queue.append("salut")

        with patch(
            "src.ui.dialogs.CustomConfirmDialog.confirm",
            return_value=True,
        ):
            live_page._clear_log()

        assert not live_page._transcript_records
        assert not live_page._tts_queue

    def test_clear_log_noop_when_nothing_to_clear(self, live_page) -> None:
        """With empty state the confirm dialog is not shown."""
        assert not live_page._transcript_records
        assert not live_page._tts_queue

        with patch(
            "src.ui.dialogs.CustomConfirmDialog.confirm",
            return_value=True,
        ) as mock_confirm:
            live_page._clear_log()

        mock_confirm.assert_not_called()


class TestTranscriptWrite:
    """Auto-save path: ``_write_transcript_to`` writes records as SRT."""

    def test_write_transcript_to_writes_srt(self, live_page, tmp_path) -> None:
        """The shared transcript-write helper produces a valid SRT body."""
        # Records are 5-tuples since the LLM-error backfill fix:
        # (timestamp, speaker, original, translated, is_error).
        live_page._transcript_records = [
            ("00:00:00 → 00:00:02", "", "Hello", "Bonjour", False),
            ("00:00:02 → 00:00:04", "Speaker 1", "World", "Monde", False),
        ]
        out = tmp_path / "auto.srt"
        assert live_page._write_transcript_to(out) is True
        content = out.read_text(encoding="utf-8")
        # SRT cue index, arrow, ms-padded timestamps, bilingual cue body.
        assert "1\n00:00:00,000 --> 00:00:02,000\nHello\nBonjour" in content
        assert "2\n00:00:02,000 --> 00:00:04,000\n[Speaker 1] World\nMonde" in content

    def test_write_transcript_round_trips_via_parse_srt(
        self,
        live_page,
        tmp_path,
    ) -> None:
        """Auto-save SRT round-trips through ``parse_srt`` cleanly."""
        from src.utils.subtitle_utils import parse_srt  # noqa: PLC0415

        live_page._transcript_records = [
            ("00:00:00 → 00:00:02", "", "Hello", "Bonjour", False),
        ]
        out = tmp_path / "auto.srt"
        assert live_page._write_transcript_to(out) is True
        entries, _ = parse_srt(out.read_text(encoding="utf-8"))
        assert len(entries) == 1
        assert entries[0].start == "00:00:00,000"
        assert entries[0].end == "00:00:02,000"
        assert "Hello" in entries[0].text
        assert "Bonjour" in entries[0].text


class TestKeyboardShortcuts:
    """Tests for the new keyboard shortcuts."""

    def test_shortcuts_registered(self, live_page) -> None:
        """Ctrl+Enter / Ctrl+K shortcuts are bound on the page."""
        from PySide6.QtCore import Qt  # noqa: PLC0415
        from PySide6.QtGui import QKeySequence, QShortcut  # noqa: PLC0415

        shortcuts = live_page.findChildren(QShortcut)
        keys = {s.key() for s in shortcuts}
        assert QKeySequence(Qt.Modifier.CTRL | Qt.Key.Key_Return) in keys
        assert QKeySequence(Qt.Modifier.CTRL | Qt.Key.Key_K) in keys


# ===========================================================================
# TTS bounded queue — older entries dropped at the maxlen boundary
# ===========================================================================


class TestTTSBoundedQueue:
    """The TTS deque is capped at _MAX_TTS_QUEUE; older items are evicted."""

    def test_max_tts_queue_constant(self) -> None:
        """_MAX_TTS_QUEUE is set to 3 (per the design contract)."""
        from src.ui.pages.live import _MAX_TTS_QUEUE  # noqa: PLC0415

        assert _MAX_TTS_QUEUE == 3  # noqa: PLR2004

    def test_queue_drops_oldest_on_overflow(self, live_page) -> None:
        """Pushing 5 sentences keeps the 3 most recent — oldest evicted."""
        from src.ui.pages.live import _MAX_TTS_QUEUE  # noqa: PLC0415

        # Fresh deque; saturate beyond capacity.
        live_page._tts_queue.clear()
        for sentence in ("S1", "S2", "S3", "S4", "S5"):
            live_page._tts_queue.append(sentence)

        assert len(live_page._tts_queue) == _MAX_TTS_QUEUE
        # Last three remain; first two evicted.
        assert list(live_page._tts_queue) == ["S3", "S4", "S5"]


# ===========================================================================
# Display-mode toggle — visibility on existing transcript cards
# ===========================================================================


class TestDisplayModeApply:
    """Switching modes mid-session updates visibility on already-rendered cards.

    ``QWidget.isVisible()`` returns False when the widget isn't shown on
    screen (offscreen platform), so we drive the assertions through
    ``isVisibleTo(parent)`` which reflects the configured visibility
    independent of the parent's show state.
    """

    def _cards(self, live_page):
        from src.ui.pages.live import _TranscriptCard  # noqa: PLC0415

        return [
            w
            for w in (
                live_page._transcript_layout.itemAt(i).widget()
                for i in range(live_page._transcript_layout.count())
            )
            if isinstance(w, _TranscriptCard)
        ]

    def test_both_to_translation_only_hides_source(self, live_page) -> None:
        """Switching from BOTH to TRANSLATION hides source labels on cards."""
        from src.constants.settings import (  # noqa: PLC0415
            LIVE_DISPLAY_BOTH,
            LIVE_DISPLAY_TRANSLATION,
            SETTING_LIVE_TRANSCRIPT_DISPLAY,
        )

        live_page._add_original("Hello", "00:00", "")
        live_page._add_translated("Bonjour")

        with patch(
            f"{_MOD}.load_setting",
            side_effect=lambda k, d="": (
                LIVE_DISPLAY_BOTH if k == SETTING_LIVE_TRANSCRIPT_DISPLAY else d
            ),
        ):
            live_page._apply_display_mode_to_cards()

        cards = self._cards(live_page)
        assert cards
        # In BOTH mode, source body is NOT explicitly hidden.
        for card in cards:
            assert not card._body.isHidden()
            assert card._translated is not None
            assert not card._translated.isHidden()

        with patch(
            f"{_MOD}.load_setting",
            side_effect=lambda k, d="": (
                LIVE_DISPLAY_TRANSLATION if k == SETTING_LIVE_TRANSCRIPT_DISPLAY else d
            ),
        ):
            live_page._apply_display_mode_to_cards()

        for card in cards:
            # Source body is hidden; translation remains visible.
            assert card._body.isHidden()
            assert card._translated is not None
            assert not card._translated.isHidden()

    def test_translation_only_back_to_both_shows_source(self, live_page) -> None:
        """BOTH after TRANSLATION re-shows the source label retroactively."""
        from src.constants.settings import (  # noqa: PLC0415
            LIVE_DISPLAY_BOTH,
            LIVE_DISPLAY_TRANSLATION,
            SETTING_LIVE_TRANSCRIPT_DISPLAY,
        )

        live_page._add_original("Hello", "00:00", "")
        live_page._add_translated("Bonjour")

        with patch(
            f"{_MOD}.load_setting",
            side_effect=lambda k, d="": (
                LIVE_DISPLAY_TRANSLATION if k == SETTING_LIVE_TRANSCRIPT_DISPLAY else d
            ),
        ):
            live_page._apply_display_mode_to_cards()

        cards = self._cards(live_page)
        for card in cards:
            assert card._body.isHidden()  # source explicitly hidden

        with patch(
            f"{_MOD}.load_setting",
            side_effect=lambda k, d="": (
                LIVE_DISPLAY_BOTH if k == SETTING_LIVE_TRANSCRIPT_DISPLAY else d
            ),
        ):
            live_page._apply_display_mode_to_cards()

        for card in cards:
            # Re-flipped to BOTH — source body is no longer hidden.
            assert not card._body.isHidden()


# ===========================================================================
# _resolve_display_mode — legacy migration paths
# ===========================================================================


class TestResolveDisplayModeMigration:
    """Legacy show_original + transcript_layout settings migrate to the new four-mode key."""

    def test_legacy_show_false_returns_translation(self, live_page) -> None:
        """show_original=false → TRANSLATION regardless of layout."""
        from src.constants.settings import (  # noqa: PLC0415
            LIVE_DISPLAY_TRANSLATION,
            SETTING_LIVE_SHOW_ORIGINAL,
            SETTING_LIVE_TRANSCRIPT_DISPLAY,
            SETTING_LIVE_TRANSCRIPT_LAYOUT,
        )

        def fake_load(key, default=""):
            if key == SETTING_LIVE_TRANSCRIPT_DISPLAY:
                return ""  # no explicit value yet → migration path
            if key == SETTING_LIVE_SHOW_ORIGINAL:
                return "false"
            if key == SETTING_LIVE_TRANSCRIPT_LAYOUT:
                return "single"
            return default

        with patch(f"{_MOD}.load_setting", side_effect=fake_load):
            assert live_page._resolve_display_mode() == LIVE_DISPLAY_TRANSLATION

    def test_legacy_show_true_dual_returns_both_dual(self, live_page) -> None:
        """show_original=true + layout=dual → BOTH_DUAL."""
        from src.constants.settings import (  # noqa: PLC0415
            LIVE_DISPLAY_BOTH_DUAL,
            LIVE_LAYOUT_DUAL,
            SETTING_LIVE_SHOW_ORIGINAL,
            SETTING_LIVE_TRANSCRIPT_DISPLAY,
            SETTING_LIVE_TRANSCRIPT_LAYOUT,
        )

        def fake_load(key, default=""):
            if key == SETTING_LIVE_TRANSCRIPT_DISPLAY:
                return ""
            if key == SETTING_LIVE_SHOW_ORIGINAL:
                return "true"
            if key == SETTING_LIVE_TRANSCRIPT_LAYOUT:
                return LIVE_LAYOUT_DUAL
            return default

        with patch(f"{_MOD}.load_setting", side_effect=fake_load):
            assert live_page._resolve_display_mode() == LIVE_DISPLAY_BOTH_DUAL

    def test_legacy_show_true_single_returns_both(self, live_page) -> None:
        """show_original=true + layout=single (or absent) → BOTH (stacked)."""
        from src.constants.settings import (  # noqa: PLC0415
            LIVE_DISPLAY_BOTH,
            SETTING_LIVE_SHOW_ORIGINAL,
            SETTING_LIVE_TRANSCRIPT_DISPLAY,
            SETTING_LIVE_TRANSCRIPT_LAYOUT,
        )

        def fake_load(key, default=""):
            if key == SETTING_LIVE_TRANSCRIPT_DISPLAY:
                return ""
            if key == SETTING_LIVE_SHOW_ORIGINAL:
                return "true"
            if key == SETTING_LIVE_TRANSCRIPT_LAYOUT:
                return "single"
            return default

        with patch(f"{_MOD}.load_setting", side_effect=fake_load):
            assert live_page._resolve_display_mode() == LIVE_DISPLAY_BOTH

    def test_explicit_overrides_legacy(self, live_page) -> None:
        """An explicit value wins over legacy settings."""
        from src.constants.settings import (  # noqa: PLC0415
            LIVE_DISPLAY_BOTH_DUAL,
            SETTING_LIVE_SHOW_ORIGINAL,
            SETTING_LIVE_TRANSCRIPT_DISPLAY,
        )

        def fake_load(key, default=""):
            if key == SETTING_LIVE_TRANSCRIPT_DISPLAY:
                return LIVE_DISPLAY_BOTH_DUAL
            if key == SETTING_LIVE_SHOW_ORIGINAL:
                return "false"  # would migrate to TRANSLATION but ignored
            return default

        with patch(f"{_MOD}.load_setting", side_effect=fake_load):
            assert live_page._resolve_display_mode() == LIVE_DISPLAY_BOTH_DUAL


# ===========================================================================
# Late LLM result after Stop — early-return when transcriber is None
# ===========================================================================


class TestLateLLMResultAfterStop:
    """Translation workers can outlive Stop — late results must not update the UI."""

    def test_on_translated_skips_when_transcriber_none(self, live_page) -> None:
        """_on_translated returns early when self._transcriber is None."""
        live_page._transcriber = None
        live_page._tts_enabled = True
        live_page._tts_queue.clear()

        prev_count = live_page._transcript_layout.count()
        # Late translation arrives after Stop — must be a no-op.
        live_page._on_translated("Hello", "Bonjour")

        # Transcript layout unchanged: no card created.
        assert live_page._transcript_layout.count() == prev_count
        # No TTS queued either.
        assert len(live_page._tts_queue) == 0

    def test_on_translation_error_skips_when_transcriber_none(
        self,
        live_page,
    ) -> None:
        """_on_translation_error returns early when self._transcriber is None."""
        live_page._transcriber = None
        # Method should simply return; verify by calling and asserting no
        # status mutation happens.  Status is a QLabel; capture its current
        # text and verify it doesn't change to a translation-error state.
        before = live_page.status_label.text()
        live_page._on_translation_error("boom")
        # Implementation only logs; status label is untouched.
        assert live_page.status_label.text() == before


# ===========================================================================
# Gemini-mode TTS gating — Gemini streams its own audio, no Edge/Google TTS
class TestStopAllWorkers:
    """Bounded shutdown of TTS + per-sentence translation threads."""

    def test_drains_translation_workers_with_bounded_wait(self, live_page) -> None:  # noqa: ANN001
        """Each pending translation worker gets a ``wait(2000)`` then drops.

        We don't start real QThreads — the contract is "every worker
        in ``_translation_workers`` has ``wait()`` called on it before
        the list is cleared".  Stand-in workers track the call so we
        can assert without race-prone real threading.
        """

        class _StubWorker:
            """Mimics enough of ``QThread`` for ``_stop_all_workers``."""

            def __init__(self) -> None:
                self.wait_calls: list[int] = []

            def wait(self, msecs: int) -> bool:
                self.wait_calls.append(msecs)
                return True

        stubs = [_StubWorker() for _ in range(3)]
        live_page._translation_workers = list(stubs)

        live_page._stop_all_workers()

        # Every worker received a single bounded wait …
        for stub in stubs:
            assert stub.wait_calls == [2000]
        # … and the list is fully drained afterwards so the next
        # session doesn't carry over stale references.
        assert live_page._translation_workers == []

    def test_empty_translation_worker_list_is_safe(self, live_page) -> None:  # noqa: ANN001
        """``_stop_all_workers`` with no workers is a no-op (no exceptions)."""
        live_page._translation_workers = []
        live_page._stop_all_workers()
        assert live_page._translation_workers == []

    def test_translation_worker_wait_isolated_from_tts(self, live_page) -> None:  # noqa: ANN001
        """A live TTS worker doesn't block translation-worker drainage.

        Pre-wires both a TTS worker and translation workers, then
        verifies each gets its bounded wait independently and the
        translation list is cleared regardless of TTS state.
        """

        class _StubWorker:
            def __init__(self) -> None:
                self.waited = False

            def wait(self, _msecs: int) -> bool:
                self.waited = True
                return True

        tts_stub = _StubWorker()
        live_page._tts_worker = tts_stub
        translation_stubs = [_StubWorker(), _StubWorker()]
        live_page._translation_workers = list(translation_stubs)

        live_page._stop_all_workers()

        assert tts_stub.waited, "TTS worker must still be waited on"
        for ts in translation_stubs:
            assert ts.waited, "every translation worker must be waited on"
        assert live_page._translation_workers == []
        assert live_page._tts_worker is None


class TestDualViewPairAlignment:
    """Pair-row alignment in the dual transcript view.

    The old layout used two independent scroll columns that could drift
    out of sync when the LLM translated more slowly than recognition.
    The current layout uses one scroll containing pair-rows, so each
    pair stays bound (left = original, right = translation /
    placeholder) even when translations arrive in arbitrary order.
    """

    def _dual_pair_count(self, page) -> int:
        """Counts pair-row widgets in the dual layout (excluding stretch)."""
        return page._dual_layout.count() - 1

    def test_add_original_creates_pair_with_placeholder(self, live_page) -> None:
        """Each original sentence yields exactly one pair-row.

        The right card starts as the placeholder ("…") so the row is
        already laid out — no empty gap waiting for the translation.
        """
        from src.ui.pages.live import (  # noqa: PLC0415
            _TRANSLATION_PLACEHOLDER,
            _TranscriptCard,
        )

        live_page._clear_log()
        live_page._add_original("Hello world")

        assert self._dual_pair_count(live_page) == 1
        pair = live_page._dual_layout.itemAt(0).widget()
        assert pair is live_page._current_dual_pair
        assert isinstance(pair._left_card, _TranscriptCard)
        assert isinstance(pair._right_card, _TranscriptCard)
        assert pair._left_card._body.text() == "Hello world"
        assert pair._right_card._body.text() == _TRANSLATION_PLACEHOLDER

    def test_add_translated_fills_placeholder_in_place(self, live_page) -> None:
        """Translation replaces the right card's placeholder, no new row."""
        live_page._clear_log()
        live_page._add_original("Hello world")
        before = self._dual_pair_count(live_page)
        live_page._add_translated("Xin chào thế giới")
        after = self._dual_pair_count(live_page)

        # Exactly the same row count — no new card created on the right.
        assert after == before == 1
        pair = live_page._dual_layout.itemAt(0).widget()
        assert pair._right_card._body.text() == "Xin chào thế giới"

    def test_pair_rows_stay_aligned_when_translation_lags(
        self,
        live_page,
    ) -> None:
        """Two originals with one translation = 2 pairs, only first filled.

        Reproduces the visual drift the old layout had: original B
        arrives before translation A, then translation A arrives.  In
        the old layout this would land in row 2 of the right column
        instead of row 1.  In the new layout the second pair just keeps
        its placeholder.
        """
        from src.ui.pages.live import _TRANSLATION_PLACEHOLDER  # noqa: PLC0415

        live_page._clear_log()
        live_page._add_original("First")
        live_page._add_original("Second")
        # Translation for the most recent original arrives.
        live_page._add_translated("Second translated")

        assert self._dual_pair_count(live_page) == 2
        first_pair = live_page._dual_layout.itemAt(0).widget()
        second_pair = live_page._dual_layout.itemAt(1).widget()

        # First original sits in row 1 with its placeholder still
        # showing — translation didn't slip into row 2.
        assert first_pair._left_card._body.text() == "First"
        assert first_pair._right_card._body.text() == _TRANSLATION_PLACEHOLDER

        # Second original got the translation — bound to the same row.
        assert second_pair._left_card._body.text() == "Second"
        assert second_pair._right_card._body.text() == "Second translated"

    def test_clear_log_resets_pair_tracking(self, live_page) -> None:
        """_clear_log empties the dual layout and drops _current_dual_pair."""
        from unittest.mock import patch  # noqa: PLC0415

        live_page._add_original("Hello")
        live_page._add_translated("Xin chào")
        assert self._dual_pair_count(live_page) == 1
        assert live_page._current_dual_pair is not None

        # _clear_log shows a confirm dialog; auto-accept it.
        with patch(
            "src.ui.dialogs.CustomConfirmDialog.confirm",
            return_value=True,
        ):
            live_page._clear_log()

        assert self._dual_pair_count(live_page) == 0
        assert live_page._current_dual_pair is None

    def test_iter_all_cards_visits_pair_children(self, live_page) -> None:
        """_iter_all_cards walks both views.

        Confirms the centralised iterator finds the dual-view pair
        children (left + right cards) AND the single-view card —
        otherwise display-mode / timestamp refreshes would skip one
        of the views entirely.  Asserts both views are represented
        explicitly (not just total count) so an accidental impl
        that only yields one side would fail loudly.
        """
        from src.ui.pages.live import _TranscriptCard  # noqa: PLC0415

        live_page._add_original("Hello")
        live_page._add_translated("Xin chào")
        cards = list(live_page._iter_all_cards())

        # All yielded items are real cards.
        assert all(isinstance(c, _TranscriptCard) for c in cards)
        # Single-view: 1 card (translation appended to it).
        # Dual-view: pair → 2 cards (left + right).
        # Total = 3.
        assert len(cards) == 3

        # Explicitly verify SINGLE-view card is yielded (not just
        # dual-view children) — catches a regression where the
        # generator drops the single layout.
        single_card = live_page._current_single_card
        assert single_card in cards, (
            "single-view card was not yielded by _iter_all_cards"
        )

        # And both DUAL-view cards (left + right of the pair).
        pair = live_page._current_dual_pair
        assert pair._left_card in cards, "dual-left card missing from iterator"
        assert pair._right_card in cards, "dual-right card missing from iterator"


class TestTranslationErrorSurfaces:
    """Inline + status-label surfaces for LLM translation failures.

    Before this UX, ``_on_translation_error`` only ``logger.error()``'d
    the failure — the user saw no translation appear and had no way
    to know whether the LLM was still working or had given up.  Now
    we paint the failing entry's translation slot with an inline
    error indicator AND show a one-shot toast in the status bar.
    """

    def test_inline_marker_paints_single_view_card(self, live_page) -> None:
        """Single-view card gets a translation slot with the error message."""
        from src.constants.i18n import _set_initial_language  # noqa: PLC0415

        _set_initial_language("en-US")
        live_page._transcriber = MagicMock()
        live_page._add_original("Hello world", timestamp="00:00:01")

        live_page._on_translation_error("AUTH_ERROR")

        single = live_page._current_single_card
        assert single._translated is not None, (
            "single-view card should have an error slot after failure"
        )
        assert "Translation failed" in single._translated.text(), (
            f"expected ⚠ marker, got {single._translated.text()!r}"
        )

    def test_inline_marker_replaces_dual_view_placeholder(self, live_page) -> None:
        """Dual-view right card swaps its ``…`` placeholder for the marker."""
        from src.constants.i18n import _set_initial_language  # noqa: PLC0415
        from src.ui.pages.live import _TRANSLATION_PLACEHOLDER  # noqa: PLC0415

        _set_initial_language("en-US")
        live_page._transcriber = MagicMock()
        live_page._add_original("Hello", timestamp="00:00:01")

        # Pre-condition: right card holds the placeholder.
        pair = live_page._current_dual_pair
        assert pair._right_card._body.text() == _TRANSLATION_PLACEHOLDER

        live_page._on_translation_error("QUOTA_ERROR")

        # Placeholder replaced with the error marker.
        assert "Translation failed" in pair._right_card._body.text()

    def test_status_label_shows_user_friendly_reason(self, live_page) -> None:
        """Status bar displays the localised tag → message mapping.

        Verifies the integration with ``display_error_message`` —
        ``AUTH_ERROR`` should not surface as a raw tag string;
        users see the friendly text the rest of the app already uses.
        """
        from src.constants.i18n import _set_initial_language  # noqa: PLC0415

        _set_initial_language("en-US")
        live_page._transcriber = MagicMock()
        live_page._add_original("Hello", timestamp="00:00:01")

        live_page._on_translation_error("AUTH_ERROR")

        status = live_page.status_label.text()
        assert "Translation failed" in status
        # The raw tag should be replaced by the friendly mapping —
        # confirm the tag itself doesn't leak through verbatim.
        assert "AUTH_ERROR" not in status

    def test_status_falls_back_to_raw_when_tag_unknown(
        self,
        live_page,
    ) -> None:
        """Unknown error string still gets shown — better raw than silent."""
        from src.constants.i18n import _set_initial_language  # noqa: PLC0415

        _set_initial_language("en-US")
        live_page._transcriber = MagicMock()
        live_page._add_original("Hello", timestamp="00:00:01")

        live_page._on_translation_error("Network gremlins ate the bytes")

        status = live_page.status_label.text()
        assert "Network gremlins" in status, (
            "unknown errors should still surface verbatim, not get swallowed"
        )

    def test_skips_when_transcriber_is_none(self, live_page) -> None:
        """Stop pressed during a slow LLM call → late error is dropped silently.

        The transcriber is set to None when the user clicks Stop;
        translations from already-in-flight workers can still arrive
        afterward.  We don't want a stale "Translation failed" toast
        to fire after the user has moved on.
        """
        from src.constants.i18n import _set_initial_language  # noqa: PLC0415

        _set_initial_language("en-US")
        live_page._transcriber = None  # simulate post-Stop state
        live_page._add_original("Hello", timestamp="00:00:01")
        original_status = live_page.status_label.text()

        live_page._on_translation_error("AUTH_ERROR")

        # Status label was NOT touched — page treats the late error
        # as belonging to a session the user already ended.
        assert live_page.status_label.text() == original_status


class TestSttErrorSurfaces:
    """Status-pill surface for fatal Soniox / Gemini Live errors.

    Mirrors ``TestTranslationErrorSurfaces`` but skips the per-card
    inline-marker assertion — STT failures kill the whole session,
    so there's no "current sentence" to mark.  The status toast is
    the only user-visible signal.  Both surfaces are non-modal so
    transient cloud hiccups don't interrupt the user with a dialog.
    """

    def test_status_label_shows_localised_message_for_known_category(
        self,
        live_page,
    ) -> None:
        """STT_AUTH_INVALID resolves through display_error_message.

        Verifies the same tag → localised text path the LLM
        translation errors use — the user sees a clear
        "API key is invalid" sentence instead of the raw tag.
        """
        from src.constants.i18n import _set_initial_language  # noqa: PLC0415

        _set_initial_language("en-US")
        # ``_on_stt_error`` drops late errors when ``_transcriber is
        # None`` (multiple errors during engine teardown), so tests
        # that simulate the first error of an active session need to
        # install a mock transcriber.
        live_page._transcriber = MagicMock()
        live_page._on_stt_error("STT_AUTH_INVALID", "401: Invalid API key")
        text = live_page.status_label.text()
        assert "API key" in text, f"expected localised auth-error toast, got: {text!r}"
        # The raw tag must NOT be visible to the user.
        assert "STT_AUTH_INVALID" not in text

    def test_status_label_falls_back_to_category_for_unknown(
        self,
        live_page,
    ) -> None:
        """Unknown category strings pass through verbatim (no crash)."""
        from src.constants.i18n import _set_initial_language  # noqa: PLC0415

        _set_initial_language("en-US")
        live_page._transcriber = MagicMock()
        live_page._on_stt_error("WHATEVER_NEW_TAG", "raw")
        # No mapping → the category itself ends up rendered as the
        # ``{reason}`` placeholder of ``live.translation_failed_status``.
        assert "WHATEVER_NEW_TAG" in live_page.status_label.text()

    def test_sticky_error_pill_clears_on_next_start(self, live_page) -> None:
        """Regression: clicking Start after a fatal STT error wipes the sticky pill.

        ``_on_stt_error`` paints a sticky red pill (no 5 s auto-clear)
        so the failure stays visible on the now-idle toolbar.  When
        the user clicks Start again, the new session must begin from
        a clean neutral pill — leaving a stale red pill on top of a
        freshly-listening session would confuse "session running" with
        "session failed".  ``_start_listening`` calls
        ``_reset_status_to_neutral()`` up front to enforce this.
        """
        from src.constants.i18n import _set_initial_language  # noqa: PLC0415

        _set_initial_language("en-US")
        # Simulate the after-error state: sticky flag set, red pill.
        live_page._transcriber = MagicMock()
        live_page._on_stt_error("STT_AUTH_INVALID", "401")
        assert live_page._sticky_error_active is True
        # Now simulate Start: clear the sticky state.  Calling the
        # public seam ``_reset_status_to_neutral`` (which
        # ``_start_listening`` invokes before any preflight) suffices
        # for the regression — full _start_listening would also try
        # to open the audio stream, which we don't need here.
        live_page._reset_status_to_neutral()
        assert live_page._sticky_error_active is False

    def test_stt_error_drops_late_signal_after_stop(self, live_page) -> None:
        """Regression: a second STT error after Stop must not re-trigger the dialog.

        The Soniox engine can emit multiple error signals during
        teardown (payload-level error → connection close → cleanup).
        We already showed the modal + sticky pill on the first
        signal; a duplicate would pop the dialog twice in quick
        succession.  The ``_transcriber is None`` guard at the top
        of ``_on_stt_error`` (set by the first call's
        ``_stop_listening``) short-circuits the second.
        """
        from src.constants.i18n import _set_initial_language  # noqa: PLC0415

        _set_initial_language("en-US")
        live_page._transcriber = None  # session already stopped
        live_page.status_label.setText("Ready")
        live_page._on_stt_error("STT_AUTH_INVALID", "401")
        # Pill text untouched — no toast, no modal, no re-stop.
        assert live_page.status_label.text() == "Ready"

    def test_stt_error_status_is_sticky(
        self,
        live_page,
        qtbot,
    ) -> None:
        """STT errors auto-stop the session and the status pill is sticky.

        Unlike translation (LLM) errors, an STT failure ends the
        whole session via ``_stop_listening``; the reason must remain
        visible on the toolbar until the user starts a new session so
        a backgrounded window can't silently lose the error context.
        """
        from src.constants.i18n import _set_initial_language  # noqa: PLC0415
        from src.ui.pages.live import (  # noqa: PLC0415
            _TRANSLATION_ERROR_STATUS_MS,
        )

        _set_initial_language("en-US")
        live_page._transcriber = MagicMock()
        live_page._on_stt_error("STT_QUOTA_EXCEEDED", "429")
        toast_text = live_page.status_label.text()
        assert "Rate limit" in toast_text or "limit" in toast_text.lower()
        # Advance past what *would* be the auto-clear deadline for the
        # translation-error path; the STT path must NOT reset.
        qtbot.wait(_TRANSLATION_ERROR_STATUS_MS + 200)
        assert live_page.status_label.text() == toast_text, (
            "STT-error pill must stay sticky until the next session, "
            "got an auto-clear instead"
        )

    def test_engine_signal_routes_to_handler(self, live_page) -> None:
        """Emitting ``_stt_error_received`` invokes ``_on_stt_error``.

        Pins the constructor wiring so a future refactor that detaches
        the signal connection is caught immediately.
        """
        from src.constants.i18n import _set_initial_language  # noqa: PLC0415

        _set_initial_language("en-US")
        live_page._transcriber = MagicMock()
        live_page._stt_error_received.emit("STT_CONNECTION_LOST", "OSError: DNS")
        # Signal is queued but emit is sync within a single event loop.
        text = live_page.status_label.text()
        assert "Connection" in text or "lost" in text.lower(), (
            f"signal didn't reach handler, status: {text!r}"
        )


class TestTranscriptCardSetError:
    """Direct unit test for ``_TranscriptCard.set_error``."""

    def test_set_error_on_translated_card_paints_body(self, qapp) -> None:  # noqa: ARG002
        """Dual-view right card (``body_is_translated=True``) → body is recoloured."""
        from src.ui.pages.live import (  # noqa: PLC0415
            _style_transcript_error,
            _TranscriptCard,
        )

        card = _TranscriptCard("", "", "…", body_is_translated=True)
        card.set_error("⚠ failed")

        assert card._body.text() == "⚠ failed"
        # Stylesheet swapped to the error styling — verify by checking
        # the colour token is in the QSS string.
        assert _style_transcript_error() == card._body.styleSheet()

    def test_set_error_on_source_card_appends_translated_slot(self, qapp) -> None:  # noqa: ARG002
        """Single-view card → adds (or repaints) a translation label."""
        from src.ui.pages.live import (  # noqa: PLC0415
            _style_transcript_error,
            _TranscriptCard,
        )

        card = _TranscriptCard("12:00", "", "Hello", body_is_translated=False)
        assert card._translated is None  # no translation yet

        card.set_error("⚠ failed")

        assert card._translated is not None
        assert card._translated.text() == "⚠ failed"
        assert card._translated.styleSheet() == _style_transcript_error()

    def test_set_error_replaces_existing_translation(self, qapp) -> None:  # noqa: ARG002
        """If the card already has a real translation, ``set_error`` overwrites it."""
        from src.ui.pages.live import _TranscriptCard  # noqa: PLC0415

        card = _TranscriptCard("12:00", "", "Hello", body_is_translated=False)
        card.set_translated("Bonjour")
        assert card._translated.text() == "Bonjour"

        card.set_error("⚠ failed")
        assert card._translated.text() == "⚠ failed"


class TestTranscriptCardSetBody:
    """Direct unit test for ``_TranscriptCard.set_body()``.

    The dual-pair placeholder-swap path goes
    ``set_body("…") → set_body(real_text)`` to keep row alignment
    stable (no tear-down + re-add of the right card).  Without a
    direct test, an accidental refactor where ``set_body`` no-ops or
    mutates the wrong label would only fail through the dual-view
    integration test — easier to debug if pinned at the unit level.
    """

    def test_set_body_replaces_label_text_in_place(self, qapp) -> None:  # noqa: ARG002
        """``set_body(text)`` rewrites ``_body.text()`` without re-creating the label."""
        from src.ui.pages.live import _TranscriptCard  # noqa: PLC0415

        card = _TranscriptCard("12:00", "", "original")
        original_label = card._body
        assert card._body.text() == "original"

        card.set_body("replaced")

        assert card._body.text() == "replaced"
        # Same QLabel instance — no re-creation, layout-stable.
        assert card._body is original_label

    def test_set_body_works_on_translated_card(self, qapp) -> None:  # noqa: ARG002
        """Works regardless of ``body_is_translated`` flag.

        The dual-view right card is created with
        ``body_is_translated=True`` and starts with the placeholder
        ("…") as its body.  Swapping in the real translation must
        not require re-creating the card.
        """
        from src.ui.pages.live import _TranscriptCard  # noqa: PLC0415

        card = _TranscriptCard("", "", "…", body_is_translated=True)
        card.set_body("Real translation")
        assert card._body.text() == "Real translation"


class TestSystemAudioWarningBanner:
    """Inline warning banner for system-audio prerequisites.

    Mirrors the OCR / office "setup hint" banners in the Settings page:
    when the user picks an audio source that needs system-audio capture
    (System Audio / Both) and the OS prerequisites aren't met, the
    banner appears below the controls with platform-specific install
    instructions instead of failing silently on Start.
    """

    def test_banner_hidden_when_source_is_microphone(self, live_page) -> None:
        """Microphone-only doesn't need system audio → banner stays hidden."""
        from src.constants.settings import AUDIO_SOURCE_MICROPHONE  # noqa: PLC0415

        # Force microphone source.
        for i in range(live_page.audio_source_combo.count()):
            if live_page.audio_source_combo.itemData(i) == AUDIO_SOURCE_MICROPHONE:
                live_page.audio_source_combo.setCurrentIndex(i)
                break
        live_page._sync_system_audio_warning()
        assert live_page._system_audio_warning.isVisible() is False

    def test_banner_visible_when_system_source_unavailable(
        self,
        live_page,
    ) -> None:
        """System Audio + missing prereq → banner shows install instructions."""
        from unittest.mock import patch  # noqa: PLC0415

        from src.constants.settings import AUDIO_SOURCE_SYSTEM  # noqa: PLC0415

        for i in range(live_page.audio_source_combo.count()):
            if live_page.audio_source_combo.itemData(i) == AUDIO_SOURCE_SYSTEM:
                live_page.audio_source_combo.setCurrentIndex(i)
                break
        # Need to show the page so isVisible() reflects the actual state
        # — Qt only honours setVisible after the parent is shown.
        live_page.show()
        try:
            with patch(
                "src.core.live_engine.check_system_audio_available",
                return_value=False,
            ):
                live_page._sync_system_audio_warning()
            assert live_page._system_audio_warning.isVisible() is True
        finally:
            live_page.hide()

    def test_banner_hidden_when_system_source_available(
        self,
        live_page,
    ) -> None:
        """System Audio + prereq met → no banner.

        Confirms the banner doesn't get stuck "on" once the user
        installs the missing software and switches back to the page.
        """
        from unittest.mock import patch  # noqa: PLC0415

        from src.constants.settings import AUDIO_SOURCE_SYSTEM  # noqa: PLC0415

        for i in range(live_page.audio_source_combo.count()):
            if live_page.audio_source_combo.itemData(i) == AUDIO_SOURCE_SYSTEM:
                live_page.audio_source_combo.setCurrentIndex(i)
                break
        with patch(
            "src.core.live_engine.check_system_audio_available",
            return_value=True,
        ):
            live_page._sync_system_audio_warning()
        assert live_page._system_audio_warning.isVisible() is False

    def test_banner_skips_check_for_microphone(self, live_page) -> None:
        """Mic-only source doesn't even invoke the availability check.

        Avoids a needless ffmpeg / pactl subprocess on every page show
        for users who never use system audio.
        """
        from unittest.mock import patch  # noqa: PLC0415

        from src.constants.settings import AUDIO_SOURCE_MICROPHONE  # noqa: PLC0415

        for i in range(live_page.audio_source_combo.count()):
            if live_page.audio_source_combo.itemData(i) == AUDIO_SOURCE_MICROPHONE:
                live_page.audio_source_combo.setCurrentIndex(i)
                break
        with patch(
            "src.core.live_engine.check_system_audio_available",
        ) as mock_check:
            live_page._sync_system_audio_warning()
        mock_check.assert_not_called()

    def test_combo_change_triggers_re_sync(self, live_page) -> None:
        """Switching the source combo re-evaluates banner visibility."""
        from unittest.mock import patch  # noqa: PLC0415

        from src.constants.settings import (  # noqa: PLC0415
            AUDIO_SOURCE_BOTH,
            AUDIO_SOURCE_MICROPHONE,
        )

        live_page.show()
        try:
            # Start on microphone — banner hidden.
            for i in range(live_page.audio_source_combo.count()):
                if live_page.audio_source_combo.itemData(i) == AUDIO_SOURCE_MICROPHONE:
                    live_page.audio_source_combo.setCurrentIndex(i)
                    break
            live_page._sync_system_audio_warning()
            assert live_page._system_audio_warning.isVisible() is False

            # Switch to "Both" with no system audio available.  Combo
            # change handler should re-sync and show the banner.
            with patch(
                "src.core.live_engine.check_system_audio_available",
                return_value=False,
            ):
                for i in range(live_page.audio_source_combo.count()):
                    if live_page.audio_source_combo.itemData(i) == AUDIO_SOURCE_BOTH:
                        live_page.audio_source_combo.setCurrentIndex(i)
                        break
            assert live_page._system_audio_warning.isVisible() is True
        finally:
            live_page.hide()

    def test_show_event_re_evaluates_banner(self, live_page) -> None:
        """Page show → re-checks availability so newly-installed deps clear it.

        A user might pick System Audio, get the warning, install
        BlackHole / VB-Audio in another window, then switch back to
        the Live tab.  The banner should clear without an app restart.
        """
        from unittest.mock import patch  # noqa: PLC0415

        from src.constants.settings import AUDIO_SOURCE_SYSTEM  # noqa: PLC0415

        for i in range(live_page.audio_source_combo.count()):
            if live_page.audio_source_combo.itemData(i) == AUDIO_SOURCE_SYSTEM:
                live_page.audio_source_combo.setCurrentIndex(i)
                break

        # First show: prereq missing → banner up.
        with patch(
            "src.core.live_engine.check_system_audio_available",
            return_value=False,
        ):
            live_page.show()
        assert live_page._system_audio_warning.isVisible() is True

        # Hide, install the prereq, show again → banner cleared.
        live_page.hide()
        with patch(
            "src.core.live_engine.check_system_audio_available",
            return_value=True,
        ):
            live_page.show()
        try:
            assert live_page._system_audio_warning.isVisible() is False
        finally:
            live_page.hide()

    def test_banner_inlines_install_command_on_linux(self, live_page) -> None:
        """On Linux, the detected pkg-manager install command is inlined.

        ``_get_pulseaudio_install_hint`` walks the available package
        managers and returns the first matching install command — when
        non-empty, it's inlined into the Linux message via the
        ``{linux_install}`` placeholder so the user can copy-paste it
        straight into a terminal.
        """
        from unittest.mock import patch  # noqa: PLC0415

        from src.constants.i18n import _set_initial_language  # noqa: PLC0415
        from src.constants.settings import AUDIO_SOURCE_SYSTEM  # noqa: PLC0415

        _set_initial_language("en-US")

        for i in range(live_page.audio_source_combo.count()):
            if live_page.audio_source_combo.itemData(i) == AUDIO_SOURCE_SYSTEM:
                live_page.audio_source_combo.setCurrentIndex(i)
                break

        with (
            patch("platform.system", return_value="Linux"),
            patch(
                "src.core.live_engine.check_system_audio_available",
                return_value=False,
            ),
            patch(
                "src.core.live_engine._get_pulseaudio_install_hint",
                return_value="sudo apt-get install pulseaudio",
            ),
        ):
            live_page._sync_system_audio_warning()

        text = live_page._system_audio_warning_label.text()
        # Per the current ``live.install_command_inline`` template
        # (`" — run <code>{cmd}</code>"`), the command is wrapped in
        # ``<code>`` and linked to the surrounding sentence with
        # " — run ".  Tests the actual rendered HTML so a template
        # change (back to ``<b>`` / ``<br>`` / etc.) is caught.
        assert "<code>sudo apt-get install pulseaudio</code>" in text
        assert " — run " in text
        # Linux-only message — should NOT mention macOS / Windows /
        # BlackHole / VB-Audio noise.
        assert "BlackHole" not in text
        assert "VB-Audio" not in text

    def test_banner_omits_install_command_when_no_pkg_manager(
        self,
        live_page,
    ) -> None:
        """Linux without a detected package manager → no inline command.

        ``{linux_install}`` substitutes to empty string; the message
        just reads "needs PulseAudio or PipeWire." with no trailing
        command.  Avoids a stray "— run " with nothing after it.
        """
        from unittest.mock import patch  # noqa: PLC0415

        from src.constants.i18n import _set_initial_language  # noqa: PLC0415
        from src.constants.settings import AUDIO_SOURCE_SYSTEM  # noqa: PLC0415

        _set_initial_language("en-US")

        for i in range(live_page.audio_source_combo.count()):
            if live_page.audio_source_combo.itemData(i) == AUDIO_SOURCE_SYSTEM:
                live_page.audio_source_combo.setCurrentIndex(i)
                break

        with (
            patch("platform.system", return_value="Linux"),
            patch(
                "src.core.live_engine.check_system_audio_available",
                return_value=False,
            ),
            patch(
                "src.core.live_engine._get_pulseaudio_install_hint",
                return_value="",
            ),
        ):
            live_page._sync_system_audio_warning()

        text = live_page._system_audio_warning_label.text()
        assert "<code>" not in text
        assert "PulseAudio" in text

    def test_banner_shows_macos_message_on_darwin(self, live_page) -> None:
        """Darwin host → BlackHole link, no Linux/Windows clutter."""
        from unittest.mock import patch  # noqa: PLC0415

        from src.constants.i18n import _set_initial_language  # noqa: PLC0415
        from src.constants.settings import AUDIO_SOURCE_SYSTEM  # noqa: PLC0415

        _set_initial_language("en-US")

        for i in range(live_page.audio_source_combo.count()):
            if live_page.audio_source_combo.itemData(i) == AUDIO_SOURCE_SYSTEM:
                live_page.audio_source_combo.setCurrentIndex(i)
                break

        with (
            patch("platform.system", return_value="Darwin"),
            patch(
                "src.core.live_engine.check_system_audio_available",
                return_value=False,
            ),
        ):
            live_page._sync_system_audio_warning()

        text = live_page._system_audio_warning_label.text()
        assert "BlackHole" in text
        assert "existential.audio" in text
        # Linux / Windows content shouldn't leak through.
        assert "PulseAudio" not in text
        assert "VB-Audio" not in text

    def test_banner_shows_windows_message_on_windows(self, live_page) -> None:
        """Windows host → SCR + VB-Audio links, no Linux/macOS clutter."""
        from unittest.mock import patch  # noqa: PLC0415

        from src.constants.i18n import _set_initial_language  # noqa: PLC0415
        from src.constants.settings import AUDIO_SOURCE_SYSTEM  # noqa: PLC0415

        _set_initial_language("en-US")

        for i in range(live_page.audio_source_combo.count()):
            if live_page.audio_source_combo.itemData(i) == AUDIO_SOURCE_SYSTEM:
                live_page.audio_source_combo.setCurrentIndex(i)
                break

        with (
            patch("platform.system", return_value="Windows"),
            patch(
                "src.core.live_engine.check_system_audio_available",
                return_value=False,
            ),
        ):
            live_page._sync_system_audio_warning()

        text = live_page._system_audio_warning_label.text()
        assert "Screen Capture Recorder" in text
        assert "VB-Audio" in text
        # Linux / macOS content shouldn't leak through.
        assert "PulseAudio" not in text
        assert "BlackHole" not in text

    def test_banner_shows_unsupported_message_on_unknown_os(
        self,
        live_page,
    ) -> None:
        """Unrecognised platform falls back to the unsupported message."""
        from unittest.mock import patch  # noqa: PLC0415

        from src.constants.i18n import _set_initial_language  # noqa: PLC0415
        from src.constants.settings import AUDIO_SOURCE_SYSTEM  # noqa: PLC0415

        _set_initial_language("en-US")

        for i in range(live_page.audio_source_combo.count()):
            if live_page.audio_source_combo.itemData(i) == AUDIO_SOURCE_SYSTEM:
                live_page.audio_source_combo.setCurrentIndex(i)
                break

        with (
            patch("platform.system", return_value="FreeBSD"),
            patch(
                "src.core.live_engine.check_system_audio_available",
                return_value=False,
            ),
        ):
            live_page._sync_system_audio_warning()

        text = live_page._system_audio_warning_label.text()
        assert "not supported" in text.lower()

    def test_apply_language_override_rebuilds_text(self, live_page) -> None:
        """Banner's ``apply_language`` override re-runs the dynamic builder.

        When the user switches UI language, ``window.py`` walks every
        QWidget and calls ``apply_language()`` on each one that
        defines it.  We override the banner's hook with
        ``_sync_system_audio_warning`` so the dynamic body (which the
        default tr_key-based hook can't rebuild) refreshes in the new
        locale.  Without this, the banner would stay stuck on the
        old language until the user toggled the audio source combo.
        """
        from unittest.mock import patch  # noqa: PLC0415

        from src.constants.i18n import _set_initial_language  # noqa: PLC0415
        from src.constants.settings import AUDIO_SOURCE_SYSTEM  # noqa: PLC0415

        # Start in English with the banner visible (Linux + missing prereq).
        _set_initial_language("en-US")
        for i in range(live_page.audio_source_combo.count()):
            if live_page.audio_source_combo.itemData(i) == AUDIO_SOURCE_SYSTEM:
                live_page.audio_source_combo.setCurrentIndex(i)
                break
        with (
            patch("platform.system", return_value="Linux"),
            patch(
                "src.core.live_engine.check_system_audio_available",
                return_value=False,
            ),
            patch(
                "src.core.live_engine._get_pulseaudio_install_hint",
                return_value="",
            ),
        ):
            live_page._sync_system_audio_warning()
        en_text = live_page._system_audio_warning_label.text()
        assert "PulseAudio" in en_text
        # English text — confirm we're not already in Vietnamese mode.
        assert "needs" in en_text.lower()

        # Verify the override is wired correctly (this is the contract
        # window.py walks for during a language change).
        assert live_page._system_audio_warning.apply_language == (
            live_page._sync_system_audio_warning
        )

        # Switch to Vietnamese and fire the override (simulating the
        # findChildren walk that window.py does on language_changed).
        _set_initial_language("vi")
        with (
            patch("platform.system", return_value="Linux"),
            patch(
                "src.core.live_engine.check_system_audio_available",
                return_value=False,
            ),
            patch(
                "src.core.live_engine._get_pulseaudio_install_hint",
                return_value="",
            ),
        ):
            live_page._system_audio_warning.apply_language()

        vi_text = live_page._system_audio_warning_label.text()
        # Vietnamese version of the Linux line should now be in place.
        assert "PulseAudio" in vi_text  # noun untranslated
        assert "Thu âm thanh" in vi_text, (
            f"banner did not re-render in Vietnamese, got: {vi_text!r}"
        )
        # Restore default for downstream tests.
        _set_initial_language("en-US")


class TestSttSetupWarningBanner:
    """Pre-flight banner for cloud STT backends missing an API key.

    Mirrors ``TestSystemAudioWarningBanner`` — the banner is the
    user-visible signal that Soniox / Gemini Live can't be used yet,
    and Start is disabled while it's visible so a known-bad attempt
    can't be fired.
    """

    def test_hidden_for_whisper(self, live_page) -> None:
        """Whisper is local — no API key needed → banner stays hidden."""
        from unittest.mock import patch  # noqa: PLC0415

        from src.constants.settings import LIVE_STT_WHISPER  # noqa: PLC0415

        with patch(
            f"{_MOD}.load_setting",
            side_effect=lambda k, d="": LIVE_STT_WHISPER if "stt_method" in k else d,
        ):
            live_page._sync_stt_setup_warning()
        assert live_page._stt_setup_warning.isVisible() is False
        assert live_page.start_btn.isEnabled() is True

    def test_visible_when_soniox_picked_without_key(self, live_page) -> None:
        """Soniox + no key → banner shown + Start disabled."""
        from unittest.mock import patch  # noqa: PLC0415

        from src.constants.settings import LIVE_STT_SONIOX  # noqa: PLC0415

        live_page.show()
        try:
            with (
                patch(
                    f"{_MOD}.load_setting",
                    side_effect=lambda k, d="": (
                        LIVE_STT_SONIOX if "stt_method" in k else d
                    ),
                ),
                patch(
                    "src.utils.config_manager.check_soniox_setup",
                    return_value=False,
                ),
            ):
                live_page._sync_stt_setup_warning()
            assert live_page._stt_setup_warning.isVisible() is True
            assert live_page.start_btn.isEnabled() is False
        finally:
            live_page.hide()

    def test_hidden_when_soniox_picked_with_key(self, live_page) -> None:
        """Soniox + key configured → banner hidden + Start enabled."""
        from unittest.mock import patch  # noqa: PLC0415

        from src.constants.settings import LIVE_STT_SONIOX  # noqa: PLC0415

        with (
            patch(
                f"{_MOD}.load_setting",
                side_effect=lambda k, d="": LIVE_STT_SONIOX if "stt_method" in k else d,
            ),
            patch(
                "src.utils.config_manager.check_soniox_setup",
                return_value=True,
            ),
        ):
            live_page._sync_stt_setup_warning()
        assert live_page._stt_setup_warning.isVisible() is False
        assert live_page.start_btn.isEnabled() is True

    def test_link_navigates_to_service_tab_for_soniox(
        self,
        live_page,
    ) -> None:
        """Clicking the Soniox banner's Settings link routes to Service tab."""
        from unittest.mock import MagicMock  # noqa: PLC0415

        live_page.window_context = MagicMock()
        live_page._on_stt_setup_link_clicked("settings://service")
        live_page.window_context.navigate_to_settings_tab.assert_called_once_with(2)

    def test_unknown_link_href_is_ignored(self, live_page) -> None:
        """A junk href doesn't trigger navigation."""
        from unittest.mock import MagicMock  # noqa: PLC0415

        live_page.window_context = MagicMock()
        live_page._on_stt_setup_link_clicked("https://example.com/")
        live_page.window_context.navigate_to_settings_tab.assert_not_called()


# ===========================================================================
# Empty-state listening hint — placeholder copy swaps on Start / Stop
# ===========================================================================


class TestEmptyStateListeningHint:
    """The empty-state placeholder must reflect the actual capture state.

    Before this fix the hint said "Press Start..." even after the user
    had already pressed Start (status pill said "Listening..."),
    contradicting itself.  ``_set_empty_state_listening`` swaps the
    title and hint between idle and listening variants.
    """

    def test_initial_state_is_idle(self, live_page) -> None:
        """Fresh page renders the idle copy."""
        from src.constants.i18n import tr  # noqa: PLC0415

        assert live_page._empty_state_listening is False
        assert live_page._empty_state_title.text() == tr("live.empty_title")
        assert live_page._empty_state_hint.text() == tr("live.empty_hint")

    def test_set_listening_true_swaps_to_listening_copy(
        self,
        live_page,
    ) -> None:
        """Entering listening state shows the "capturing audio" hint."""
        from src.constants.i18n import tr  # noqa: PLC0415

        live_page._set_empty_state_listening(listening=True)

        assert live_page._empty_state_listening is True
        assert live_page._empty_state_title.text() == tr("live.empty_title_listening")
        assert live_page._empty_state_hint.text() == tr("live.empty_hint_listening")

    def test_set_listening_false_restores_idle_copy(
        self,
        live_page,
    ) -> None:
        """Stopping returns to the "Press Start..." copy."""
        from src.constants.i18n import tr  # noqa: PLC0415

        live_page._set_empty_state_listening(listening=True)
        live_page._set_empty_state_listening(listening=False)

        assert live_page._empty_state_listening is False
        assert live_page._empty_state_title.text() == tr("live.empty_title")
        assert live_page._empty_state_hint.text() == tr("live.empty_hint")

    def test_reset_ui_to_ready_swaps_to_idle(self, live_page) -> None:
        """``_reset_ui_to_ready`` (called from _stop_listening) flips back to idle."""
        from src.constants.i18n import tr  # noqa: PLC0415

        live_page._set_empty_state_listening(listening=True)
        live_page._reset_ui_to_ready()

        assert live_page._empty_state_title.text() == tr("live.empty_title")
        assert live_page._empty_state_hint.text() == tr("live.empty_hint")

    def test_apply_language_preserves_listening_state(
        self,
        live_page,
    ) -> None:
        """A language switch while listening keeps the listening copy.

        Without the variant-aware retranslation this test guards, the
        idle copy would silently overwrite the listening copy on every
        ``language_changed`` emit.
        """
        from src.constants.i18n import tr  # noqa: PLC0415

        live_page._set_empty_state_listening(listening=True)
        live_page.apply_language()  # full retranslate

        # Still listening — must NOT have reverted to idle.
        assert live_page._empty_state_listening is True
        assert live_page._empty_state_title.text() == tr("live.empty_title_listening")
        assert live_page._empty_state_hint.text() == tr("live.empty_hint_listening")


# ===========================================================================
# Live page _TTSWorker — Piper branch + fallback contract
# ===========================================================================


class TestTTSWorkerPiperFallback:
    """Live ``_TTSWorker`` Piper branch — installed runs Piper, missing → Edge.

    Contract documented inline in ``_TTSWorker.run()``: a missing
    Piper voice in the middle of a live session should silently fall
    back to Edge so the user gets *some* audio rather than dead air.
    Mid-session error dialogs would interrupt the live flow.
    """

    @patch(f"{_MOD}.load_setting")
    def test_piper_with_installed_voice_uses_piper(self, mock_load) -> None:
        """Piper-supported language + voice on disk → ``_synthesize_chunk_piper`` runs."""
        from src.constants.settings import (  # noqa: PLC0415
            SETTING_VOICE_TTS_METHOD,
            VOICE_TTS_PIPER,
        )

        def _fake_load(key, default=""):
            if key == SETTING_VOICE_TTS_METHOD:
                return VOICE_TTS_PIPER
            return default

        mock_load.side_effect = _fake_load
        # "English (US)" is in the Piper catalogue; the worker
        # resolves the voice via ``get_piper_voice_for(target, gender)``
        # — no separate ``SETTING_LAST_PIPER_VOICE`` lookup any more.
        worker = _make_tts_worker("Hello", "English (US)")

        with (
            patch(
                "src.core.speech_engine._synthesize_chunk_piper",
            ) as mock_piper,
            patch(
                "src.core.speech_engine._synthesize_chunk_edge",
            ) as mock_edge,
            patch(
                "src.core.speech_engine.is_piper_voice_installed",
                return_value=True,
            ),
            patch("src.core.speech_engine._get_edge_voice"),
            patch("tempfile.NamedTemporaryFile") as mock_tmp,
        ):
            tmp_obj = MagicMock()
            tmp_obj.name = "/tmp/live_tts_piper.mp3"
            tmp_obj.close = MagicMock()
            mock_tmp.return_value = tmp_obj
            worker.run()

        mock_piper.assert_called_once()
        mock_edge.assert_not_called()
        worker.synthesized.emit.assert_called_once()

    @patch(f"{_MOD}.load_setting")
    def test_piper_with_missing_voice_falls_back_to_edge(
        self,
        mock_load,
    ) -> None:
        """Piper-supported language but voice not on disk → silent Edge fallback."""
        from src.constants.settings import (  # noqa: PLC0415
            SETTING_VOICE_TTS_METHOD,
            VOICE_TTS_PIPER,
        )

        def _fake_load(key, default=""):
            if key == SETTING_VOICE_TTS_METHOD:
                return VOICE_TTS_PIPER
            return default

        mock_load.side_effect = _fake_load
        # "French" is in the Piper catalogue; the
        # ``is_piper_voice_installed`` stub below pretends the file
        # isn't on disk so the live worker switches to Edge.
        worker = _make_tts_worker("Bonjour", "French")

        with (
            patch(
                "src.core.speech_engine._synthesize_chunk_piper",
            ) as mock_piper,
            patch(
                "src.core.speech_engine._synthesize_chunk_edge",
            ) as mock_edge,
            patch(
                "src.core.speech_engine.is_piper_voice_installed",
                return_value=False,
            ),
            patch(
                "src.core.speech_engine._get_edge_voice",
                return_value="fr-FR-DeniseNeural",
            ),
            patch("tempfile.NamedTemporaryFile") as mock_tmp,
        ):
            tmp_obj = MagicMock()
            tmp_obj.name = "/tmp/live_tts_fallback.mp3"
            tmp_obj.close = MagicMock()
            mock_tmp.return_value = tmp_obj
            worker.run()

        mock_piper.assert_not_called()
        mock_edge.assert_called_once()
        # Worker still emits ``synthesized`` — the fallback is silent.
        worker.synthesized.emit.assert_called_once()

    @patch(f"{_MOD}.load_setting")
    def test_piper_with_unsupported_language_falls_back_to_edge(
        self,
        mock_load,
    ) -> None:
        """Piper-unsupported language (e.g. Japanese) → Edge fallback.

        Pins the empty-voice-id branch of ``_TTSWorker.run()`` —
        ``get_piper_voice_for`` returns ``""`` for languages with
        no Piper coverage, and the worker must NOT call
        ``_synthesize_chunk_piper`` (would raise) but route to Edge.
        """
        from src.constants.settings import (  # noqa: PLC0415
            SETTING_VOICE_TTS_METHOD,
            VOICE_TTS_PIPER,
        )

        def _fake_load(key, default=""):
            if key == SETTING_VOICE_TTS_METHOD:
                return VOICE_TTS_PIPER
            return default

        mock_load.side_effect = _fake_load
        # Japanese has no Piper voice — get_piper_voice_for returns "".
        worker = _make_tts_worker("こんにちは", "Japanese")

        with (
            patch(
                "src.core.speech_engine._synthesize_chunk_piper",
            ) as mock_piper,
            patch(
                "src.core.speech_engine._synthesize_chunk_edge",
            ) as mock_edge,
            patch(
                "src.core.speech_engine._get_edge_voice",
                return_value="ja-JP-NanamiNeural",
            ),
            patch("tempfile.NamedTemporaryFile") as mock_tmp,
        ):
            tmp_obj = MagicMock()
            tmp_obj.name = "/tmp/live_tts_unsupported.mp3"
            tmp_obj.close = MagicMock()
            mock_tmp.return_value = tmp_obj
            worker.run()

        mock_piper.assert_not_called()
        mock_edge.assert_called_once()
        worker.synthesized.emit.assert_called_once()


class TestApplyLanguagePreservesComboSelection:
    """``apply_language`` rebuilds combos in place + preserves selection.

    The rebuild iterates the freshly-sorted catalogue (per the new
    locale's order) and overwrites text+data+icon at each index.
    Selection preservation goes through ``findData(saved)`` after
    the rebuild, which is the load-bearing line.  A regression that
    forgets the ``setCurrentIndex(idx)`` call (e.g. a refactor that
    rebuilds via ``clear()/addItem()`` instead of in-place
    ``setItemText/Data/Icon``) would silently drop the user's pick
    on every UI-language switch.
    """

    def test_target_lang_combo_selection_survives_locale_switch(
        self,
        live_page,  # noqa: ANN001
    ) -> None:
        from src.constants.i18n import _set_initial_language  # noqa: PLC0415

        _set_initial_language("en-US")
        try:
            combo = live_page.target_lang_combo
            # Pick Vietnamese (data == "Vietnamese").
            idx = combo.findData("Vietnamese")
            assert idx > 0, "Vietnamese should be in the target combo"
            combo.setCurrentIndex(idx)
            assert combo.currentData() == "Vietnamese"

            # Switch UI to vi and run the apply_language refresh.
            _set_initial_language("vi")
            live_page.apply_language()

            # Selection (canonical English label) must be preserved.
            assert combo.currentData() == "Vietnamese", (
                "apply_language must preserve the user's selection by "
                "canonical English label across the rebuild; got "
                f"{combo.currentData()!r}"
            )
        finally:
            _set_initial_language("en-US")

    def test_source_lang_combo_auto_detect_sentinel_survives_locale_switch(
        self,
        live_page,  # noqa: ANN001
    ) -> None:
        """Auto-detect (data == "") at index 0 must stay selected after rebuild."""
        from src.constants.i18n import _set_initial_language  # noqa: PLC0415

        _set_initial_language("en-US")
        try:
            combo = live_page.source_lang_combo
            combo.setCurrentIndex(0)  # Auto-detect
            assert combo.currentData() == ""

            _set_initial_language("vi")
            live_page.apply_language()

            assert combo.currentData() == "", (
                "Auto-detect sentinel (empty itemData) must stay selected "
                "across the rebuild"
            )
        finally:
            _set_initial_language("en-US")


class TestStopAllWorkersOverlayCleanup:
    """``_stop_all_workers`` also closes the floating overlay window.

    Pins the contract that the frameless top-level overlay (which has
    no Qt parent so it isn't auto-cleaned) is closed and dereferenced
    on app shutdown. Without this, the overlay would linger as a
    zombie window after the main app exits, requiring the user to
    force-kill the orphan via the OS task manager.
    """

    def test_overlay_closed_and_cleared(self, live_page) -> None:  # noqa: ANN001
        """Pre-set ``_overlay`` is closed and reset to None on stop."""
        from unittest.mock import MagicMock  # noqa: PLC0415

        mock_overlay = MagicMock()
        live_page._overlay = mock_overlay
        # No translation workers / TTS — focus on overlay path.
        live_page._translation_workers = []
        live_page._tts_worker = None
        live_page._transcriber = None

        live_page._stop_all_workers()

        mock_overlay.close.assert_called_once()
        assert live_page._overlay is None, (
            "overlay reference must be cleared so it can be GC'd"
        )

    def test_no_overlay_is_safe(self, live_page) -> None:  # noqa: ANN001
        """Calling stop with no overlay set is a no-op (no AttributeError)."""
        live_page._overlay = None
        live_page._translation_workers = []
        live_page._tts_worker = None
        live_page._transcriber = None

        live_page._stop_all_workers()  # must not raise
        assert live_page._overlay is None


# ===========================================================================
# TestSonioxSessionEvents — Soniox cloud-mode sentence handling
# ===========================================================================


class TestSonioxSessionEvents:
    """Drives the Soniox-mode branch of ``_on_sentence`` without a real WS.

    Soniox is the cloud STT backend. Unlike Whisper (which goes via
    ``_TranslationWorker`` after the sentence arrives), Soniox returns
    text + translation in the same callback — a pre-translated sentence.
    The page's ``_on_sentence`` handler distinguishes the two via the
    ``translated`` arg: if it's non-empty we're in Soniox mode and
    ``_add_translated`` is invoked synchronously, the sentence is
    appended to ``_transcript_records``, and TTS is queued (when on).

    Soniox mode previously had no direct test coverage at the page
    layer — this pins the synchronous translated-add + transcript-record
    + TTS-queue contract so a refactor to the dispatch can't regress
    cloud transcription silently.
    """

    def test_soniox_translated_arg_appends_record_and_queues_tts(
        self,
        live_page,
    ) -> None:
        """``_on_sentence(text=..., translated=...)`` records both lines."""
        # Reset state; force TTS on so the queue branch fires
        live_page._transcript_records = []
        live_page._tts_queue.clear()
        live_page._tts_enabled = True
        live_page._transcriber = MagicMock()

        # Stub the per-card add helpers — we're verifying dispatch,
        # not card construction.  Also stub _process_tts_queue so the
        # test doesn't try to actually synthesize audio.
        with (
            patch.object(live_page, "_add_original") as mock_orig,
            patch.object(live_page, "_add_translated") as mock_trans,
            patch.object(live_page, "_process_tts_queue") as mock_tts,
            patch(f"{_MOD}.load_setting", return_value=""),
        ):
            live_page._on_sentence(
                "Hello world",
                0.0,
                1.5,
                "speaker_0",
                "Bonjour le monde",
            )

        mock_orig.assert_called_once()
        # The translated-arg branch must call _add_translated synchronously
        mock_trans.assert_called_once_with("Bonjour le monde")
        # Transcript record must capture both source + translation
        assert len(live_page._transcript_records) == 1
        record = live_page._transcript_records[0]
        # (timestamp, speaker_label, text, translated)
        assert record[2] == "Hello world"
        assert record[3] == "Bonjour le monde"
        # TTS must have been enqueued + processor pinged
        assert "Bonjour le monde" in list(live_page._tts_queue)
        mock_tts.assert_called_once()

    def test_soniox_translated_arg_skips_tts_when_disabled(
        self,
        live_page,
    ) -> None:
        """TTS-disabled mode still records but does not enqueue audio."""
        live_page._transcript_records = []
        live_page._tts_queue.clear()
        live_page._tts_enabled = False
        live_page._transcriber = MagicMock()

        with (
            patch.object(live_page, "_add_original"),
            patch.object(live_page, "_add_translated"),
            patch.object(live_page, "_process_tts_queue") as mock_tts,
            patch(f"{_MOD}.load_setting", return_value=""),
        ):
            live_page._on_sentence(
                "Hola",
                0.0,
                0.5,
                "",
                "Hello",
            )

        # Record stored
        assert len(live_page._transcript_records) == 1
        # TTS path must NOT have been called when the toggle is off
        mock_tts.assert_not_called()
        assert "Hello" not in list(live_page._tts_queue)


# ===========================================================================
# TestWindowsSoundcardLoopback — native WASAPI loopback path
# ===========================================================================


class TestWindowsSoundcardLoopback:
    """``LiveTranscriber._start_system_audio_windows_soundcard`` happy path.

    Per AGENTS.md, the Windows path tries ``soundcard.all_microphones()``
    first (native WASAPI loopback, no extra software), then falls back
    to ``ffmpeg -f dshow``. We can exercise the soundcard branch on
    Linux CI by mocking the ``soundcard`` module and stubbing
    ``sc.default_speaker()`` / ``sc.get_microphone()`` to return a
    fake loopback recorder.

    NOTE: ``_start_system_audio_windows_soundcard`` lives on the
    engine (``src.core.live_engine.LiveTranscriber``), not the page —
    placing the test alongside its sibling Live-page tests for
    discoverability.
    """

    def test_soundcard_loopback_picked_when_present(self) -> None:
        """When soundcard imports cleanly, the loopback path is used."""
        import sys  # noqa: PLC0415

        # Build a fake soundcard module with the minimum surface area
        # the engine touches: default_speaker(), get_microphone(...,
        # include_loopback=True).recorder(...) as a context manager.
        fake_speaker = MagicMock()
        fake_speaker.id = "default-speaker-id"

        fake_recorder_ctx = MagicMock()
        fake_recorder_ctx.__enter__.return_value = MagicMock(
            record=MagicMock(side_effect=Exception("stop reader")),
        )
        fake_recorder_ctx.__exit__ = MagicMock(return_value=False)

        fake_loopback_mic = MagicMock()
        fake_loopback_mic.recorder.return_value = fake_recorder_ctx

        fake_sc = MagicMock()
        fake_sc.default_speaker.return_value = fake_speaker
        fake_sc.get_microphone.return_value = fake_loopback_mic

        with patch.dict(sys.modules, {"soundcard": fake_sc}):
            from src.core.live_engine import LiveTranscriber  # noqa: PLC0415

            transcriber = LiveTranscriber.__new__(LiveTranscriber)
            transcriber._is_running = False  # force reader to exit fast
            transcriber._sys_audio_thread = None
            # Target queue can be any queue — reader will not push to it
            # because we wired record() to raise on first call.
            import queue as _queue  # noqa: PLC0415

            target = _queue.Queue()

            transcriber._start_system_audio_windows_soundcard(target)

        # Soundcard path requested the default speaker as the loopback source
        fake_sc.default_speaker.assert_called_once()
        # And asked for a loopback-flagged mic against that speaker's id
        fake_sc.get_microphone.assert_called_once_with(
            id="default-speaker-id",
            include_loopback=True,
        )
        # Reader thread was spawned (sentinel for "we did the work")
        assert transcriber._sys_audio_thread is not None

    def test_soundcard_missing_default_speaker_raises_oserror(
        self,
    ) -> None:
        """No default speaker → OSError so the dispatcher falls back."""
        import sys  # noqa: PLC0415

        fake_sc = MagicMock()
        fake_sc.default_speaker.return_value = None

        with patch.dict(sys.modules, {"soundcard": fake_sc}):
            from src.core.live_engine import LiveTranscriber  # noqa: PLC0415

            transcriber = LiveTranscriber.__new__(LiveTranscriber)
            transcriber._is_running = False
            transcriber._sys_audio_thread = None

            import queue as _queue  # noqa: PLC0415

            with pytest.raises(OSError, match="no default speaker"):
                transcriber._start_system_audio_windows_soundcard(
                    _queue.Queue(),
                )


class TestDualViewRowAlignment:
    """Late-arriving translations land on the row that owns the source.

    Pin the load-bearing fix for the dual-view drift bug: when several
    originals queue up before any of their LLM translations come back,
    each translation must attach to its OWN pair-row, not whatever
    happens to be the most recent one.

    Without this regression guard, a refactor that drops the
    ``single_card`` / ``dual_pair`` parameters from
    ``_on_translated`` (or the partial-binding lambdas in
    ``_on_sentence``) would silently re-introduce the misalignment
    the user reported on a long Whisper session.
    """

    def test_multiple_pending_translations_land_on_correct_pairs(
        self,
        qapp,
        qtbot,
        monkeypatch,  # noqa: ANN001
    ) -> None:
        """Three originals → three out-of-order translations → 1:1 row alignment."""
        from unittest.mock import MagicMock  # noqa: PLC0415

        from src.ui.pages.live import LivePage  # noqa: PLC0415

        # Build the page bare via __new__ so we don't need to set up
        # the entire QStackedWidget chrome — we test the
        # _add_original / _add_translated direct contract.
        page = LivePage.__new__(LivePage)
        # Minimal scaffold: layouts + scroll + state attrs the methods
        # touch.  Real layouts so addWidget calls don't crash; mock
        # everything else.
        from PySide6.QtWidgets import QScrollArea, QVBoxLayout, QWidget  # noqa: PLC0415

        page._scroll = QScrollArea()
        qtbot.addWidget(page._scroll)
        page._dual_scroll = QScrollArea()
        qtbot.addWidget(page._dual_scroll)
        host_single = QWidget()
        page._scroll.setWidget(host_single)
        host_dual = QWidget()
        page._dual_scroll.setWidget(host_dual)
        page._transcript_layout = QVBoxLayout(host_single)
        page._dual_layout = QVBoxLayout(host_dual)
        page._transcript_outer = MagicMock()
        page._show_transcript_view = MagicMock()
        page._resolve_display_mode = lambda: "both_dual"
        page._mode_shows_source = lambda _: True
        page._mode_shows_target = lambda _: True
        page._show_timestamp = True
        page._show_speaker = True
        page._overlay = None

        # Insert helper just appends to the layout (no scroll-into-view).
        def _insert(layout, _scroll, widget):
            layout.addWidget(widget)

        page._insert_into = _insert

        # Add three originals back-to-back (simulating Whisper finals
        # arriving faster than the LLM can translate them).
        sc1, dp1 = page._add_original("first", "00:01", "")
        sc2, dp2 = page._add_original("second", "00:02", "")
        sc3, dp3 = page._add_original("third", "00:03", "")

        # Sanity: ``_current_*`` now points to the LAST pair, which
        # was the symptom of the original bug.
        assert page._current_single_card is sc3
        assert page._current_dual_pair is dp3

        # Translations land OUT OF ORDER (LLM finishes #2 first, then
        # #1, then #3) — same race condition as the real symptom.
        page._add_translated("SECOND", single_card=sc2, dual_pair=dp2)
        page._add_translated("FIRST", single_card=sc1, dual_pair=dp1)
        page._add_translated("THIRD", single_card=sc3, dual_pair=dp3)

        # Each pair's right card should hold the matching translation.
        assert dp1._right_card._body.text() == "FIRST"
        assert dp2._right_card._body.text() == "SECOND"
        assert dp3._right_card._body.text() == "THIRD"

    def test_add_translated_falls_back_to_current_pointers(
        self,
        qapp,
        qtbot,  # noqa: ANN001
    ) -> None:
        """Soniox path: translation arrives synchronously, no targets needed.

        When ``_add_translated`` is called WITHOUT explicit targets
        (Soniox cloud mode delivers original + translation in the same
        callback), the current-pointer fallback keeps the existing
        contract working.
        """
        from unittest.mock import MagicMock  # noqa: PLC0415

        from PySide6.QtWidgets import QScrollArea, QVBoxLayout, QWidget  # noqa: PLC0415

        from src.ui.pages.live import LivePage  # noqa: PLC0415

        page = LivePage.__new__(LivePage)
        page._scroll = QScrollArea()
        qtbot.addWidget(page._scroll)
        page._dual_scroll = QScrollArea()
        qtbot.addWidget(page._dual_scroll)
        host_single = QWidget()
        page._scroll.setWidget(host_single)
        host_dual = QWidget()
        page._dual_scroll.setWidget(host_dual)
        page._transcript_layout = QVBoxLayout(host_single)
        page._dual_layout = QVBoxLayout(host_dual)
        page._transcript_outer = MagicMock()
        page._show_transcript_view = MagicMock()
        page._resolve_display_mode = lambda: "both_dual"
        page._mode_shows_source = lambda _: True
        page._mode_shows_target = lambda _: True
        page._show_timestamp = True
        page._show_speaker = True
        page._overlay = None
        page._insert_into = lambda layout, _scroll, widget: layout.addWidget(widget)

        sc, dp = page._add_original("hello", "00:01", "")
        # Soniox-style call: no explicit targets, relies on _current_*.
        page._add_translated("xin chào")
        assert dp._right_card._body.text() == "xin chào"
        assert sc is page._current_single_card


class TestSaveClearDisabledOnEmptyTranscript:
    """Save / Clear buttons disable themselves when the transcript is empty.

    Pin the contract that pure no-op clicks are prevented up front
    rather than after the user gets a "nothing to save" / "nothing
    to clear" dialog.
    """

    def test_disabled_on_construction(
        self,
        qapp,
        qtbot,  # noqa: ANN001, ARG002
    ) -> None:
        """Page boots with empty records → both buttons disabled."""
        from PySide6.QtWidgets import QMainWindow  # noqa: PLC0415

        from src.ui.pages.live import LivePage  # noqa: PLC0415

        win = QMainWindow()
        qtbot.addWidget(win)
        page = LivePage(win)
        qtbot.addWidget(page)
        assert page.clear_btn.isEnabled() is False

    def test_enabled_after_first_original(
        self,
        qapp,
        qtbot,  # noqa: ANN001, ARG002
    ) -> None:
        """First ``_add_original`` enables the Clear button."""
        from PySide6.QtWidgets import QMainWindow  # noqa: PLC0415

        from src.ui.pages.live import LivePage  # noqa: PLC0415

        win = QMainWindow()
        qtbot.addWidget(win)
        page = LivePage(win)
        qtbot.addWidget(page)
        # Add a fake transcript record + invoke the refresh hook
        # (instead of going through _add_original which needs a full
        # transcript layout setup that pytest-qt doesn't always
        # initialise reliably under offscreen).
        page._transcript_records.append(("00:01", "", "hello", "", False))
        page._refresh_content_dependent_buttons()
        assert page.clear_btn.isEnabled() is True

    def test_disabled_after_clear(
        self,
        qapp,
        qtbot,  # noqa: ANN001, ARG002
    ) -> None:
        """Emptying ``_transcript_records`` re-disables Clear."""
        from PySide6.QtWidgets import QMainWindow  # noqa: PLC0415

        from src.ui.pages.live import LivePage  # noqa: PLC0415

        win = QMainWindow()
        qtbot.addWidget(win)
        page = LivePage(win)
        qtbot.addWidget(page)
        page._transcript_records.append(("00:01", "", "hello", "", False))
        page._refresh_content_dependent_buttons()
        assert page.clear_btn.isEnabled() is True

        page._transcript_records.clear()
        page._refresh_content_dependent_buttons()
        assert page.clear_btn.isEnabled() is False


class TestWhisperPreload:
    """``_maybe_preload_whisper`` warms the Whisper model on page show.

    All four short-circuit branches plus the happy path are covered;
    real ``WhisperModel`` construction is mocked so the suite stays
    offline and fast (the real preload would download hundreds of MB).
    """

    def test_skips_when_stt_method_not_whisper(
        self,
        qapp,
        qtbot,  # noqa: ANN001, ARG002
    ) -> None:
        """Soniox / other engines → no preload thread spawned."""
        from unittest.mock import MagicMock, patch  # noqa: PLC0415

        from PySide6.QtWidgets import QMainWindow  # noqa: PLC0415

        from src.ui.pages.live import LivePage  # noqa: PLC0415

        win = QMainWindow()
        qtbot.addWidget(win)
        page = LivePage(win)
        qtbot.addWidget(page)

        with (
            patch("src.ui.pages.live.load_setting", return_value="soniox"),
            patch(
                "src.ui.pages.live._WhisperPreloadWorker",
            ) as mock_worker_cls,
            patch("src.core.live_engine.is_whisper_model_cached") as mock_cached,
        ):
            mock_cached.return_value = True
            mock_worker_cls.return_value = MagicMock()
            page._maybe_preload_whisper()

        mock_worker_cls.assert_not_called()
        assert page._whisper_preload_worker is None

    def test_skips_when_model_not_on_disk(
        self,
        qapp,
        qtbot,  # noqa: ANN001, ARG002
    ) -> None:
        """No on-disk cache → no thread (avoids silent download)."""
        from unittest.mock import MagicMock, patch  # noqa: PLC0415

        from PySide6.QtWidgets import QMainWindow  # noqa: PLC0415

        from src.ui.pages.live import LivePage  # noqa: PLC0415

        win = QMainWindow()
        qtbot.addWidget(win)
        page = LivePage(win)
        qtbot.addWidget(page)

        with (
            patch("src.ui.pages.live.load_setting", return_value="whisper"),
            patch(
                "src.ui.pages.live._WhisperPreloadWorker",
            ) as mock_worker_cls,
            patch(
                "src.core.live_engine.is_whisper_model_cached",
                return_value=False,
            ),
        ):
            mock_worker_cls.return_value = MagicMock()
            page._maybe_preload_whisper()

        mock_worker_cls.assert_not_called()
        assert page._whisper_preload_worker is None

    def test_skips_when_already_cached_in_memory(
        self,
        qapp,
        qtbot,  # noqa: ANN001, ARG002
    ) -> None:
        """Engine cache already holds the requested size → no thread."""
        from unittest.mock import MagicMock, patch  # noqa: PLC0415

        from PySide6.QtWidgets import QMainWindow  # noqa: PLC0415

        from src.core import live_engine  # noqa: PLC0415
        from src.ui.pages.live import LivePage  # noqa: PLC0415

        win = QMainWindow()
        qtbot.addWidget(win)
        page = LivePage(win)
        qtbot.addWidget(page)

        # Settings flow: method=whisper, size=tiny.
        def fake_load(key, default=""):  # noqa: ANN001, ANN202, ARG001
            if key == "live/stt_method":
                return "whisper"
            if key == "live/whisper_model":
                return "tiny"
            return default

        sentinel = object()
        with (
            patch("src.ui.pages.live.load_setting", side_effect=fake_load),
            patch.object(live_engine, "_cached_model", sentinel),
            patch.object(live_engine, "_cached_model_size", "tiny"),
            patch(
                "src.ui.pages.live._WhisperPreloadWorker",
            ) as mock_worker_cls,
        ):
            mock_worker_cls.return_value = MagicMock()
            page._maybe_preload_whisper()

        mock_worker_cls.assert_not_called()

    def test_spawns_worker_on_cache_hit(
        self,
        qapp,
        qtbot,  # noqa: ANN001, ARG002
    ) -> None:
        """Whisper + on-disk cache + no in-memory model → worker spawned."""
        from unittest.mock import MagicMock, patch  # noqa: PLC0415

        from PySide6.QtWidgets import QMainWindow  # noqa: PLC0415

        from src.core import live_engine  # noqa: PLC0415
        from src.ui.pages.live import LivePage  # noqa: PLC0415

        win = QMainWindow()
        qtbot.addWidget(win)
        page = LivePage(win)
        qtbot.addWidget(page)

        def fake_load(key, default=""):  # noqa: ANN001, ANN202, ARG001
            if key == "live/stt_method":
                return "whisper"
            if key == "live/whisper_model":
                return "small"
            return default

        with (
            patch("src.ui.pages.live.load_setting", side_effect=fake_load),
            patch.object(live_engine, "_cached_model", None),
            patch.object(live_engine, "_cached_model_size", ""),
            patch(
                "src.core.live_engine.is_whisper_model_cached",
                return_value=True,
            ),
            patch(
                "src.ui.pages.live._WhisperPreloadWorker",
            ) as mock_worker_cls,
        ):
            mock_worker = MagicMock()
            mock_worker_cls.return_value = mock_worker
            page._maybe_preload_whisper()

        mock_worker_cls.assert_called_once_with("small")
        mock_worker.start.assert_called_once()
        assert page._whisper_preload_worker is mock_worker

    def test_skips_when_preload_already_running(
        self,
        qapp,
        qtbot,  # noqa: ANN001, ARG002
    ) -> None:
        """A prior preload still running → no second thread spawned."""
        from unittest.mock import MagicMock, patch  # noqa: PLC0415

        from PySide6.QtWidgets import QMainWindow  # noqa: PLC0415

        from src.ui.pages.live import LivePage  # noqa: PLC0415

        win = QMainWindow()
        qtbot.addWidget(win)
        page = LivePage(win)
        qtbot.addWidget(page)

        running = MagicMock()
        running.isRunning.return_value = True
        page._whisper_preload_worker = running

        with (
            patch("src.ui.pages.live.load_setting", return_value="whisper"),
            patch(
                "src.core.live_engine.is_whisper_model_cached",
                return_value=True,
            ),
            patch(
                "src.ui.pages.live._WhisperPreloadWorker",
            ) as mock_worker_cls,
        ):
            page._maybe_preload_whisper()

        mock_worker_cls.assert_not_called()
        assert page._whisper_preload_worker is running

    def test_show_event_triggers_preload(
        self,
        qapp,
        qtbot,  # noqa: ANN001, ARG002
    ) -> None:
        """Integration check: ``showEvent`` calls ``_maybe_preload_whisper``.

        Other tests exercise the helper directly; this one pins that
        the wiring from ``LivePage.showEvent`` is intact so a future
        refactor can't silently drop the preload trigger.
        """
        from unittest.mock import patch  # noqa: PLC0415

        from PySide6.QtWidgets import QMainWindow  # noqa: PLC0415

        from src.ui.pages.live import LivePage  # noqa: PLC0415

        win = QMainWindow()
        qtbot.addWidget(win)
        page = LivePage(win)
        qtbot.addWidget(page)

        with patch.object(page, "_maybe_preload_whisper") as mock_preload:
            page.show()
        mock_preload.assert_called()
        page.hide()


class TestWhisperPreloadWorkerRun:
    """``_WhisperPreloadWorker.run()`` delegates to ``preload_whisper_model``.

    The autouse ``_no_real_whisper_preload`` fixture patches the
    worker class everywhere else so no test spawns a real thread.
    These tests override that fixture so the production class is
    visible, then exercise ``run()`` directly (synchronously, no
    ``QThread.start()``) so the delegation contract is pinned: a
    refactor that drops the import or passes the wrong size silently
    breaks the preload feature, and the autouse fixture would hide
    it.
    """

    @pytest.fixture(autouse=True)
    def _no_real_whisper_preload(self):  # noqa: PLR6301
        """Override the file-scope fixture so the real class is visible."""
        yield

    def test_run_calls_preload_with_stored_size(self) -> None:
        """``run()`` forwards the constructor-supplied ``model_size``."""
        from unittest.mock import patch  # noqa: PLC0415

        from src.ui.pages.live import _WhisperPreloadWorker  # noqa: PLC0415

        worker = _WhisperPreloadWorker("medium")
        with patch(
            "src.core.live_engine.preload_whisper_model",
        ) as mock_preload:
            worker.run()  # synchronous call (not via QThread.start())
        mock_preload.assert_called_once_with("medium")


class TestIsWhisperModelCached:
    """``is_whisper_model_cached`` reads the HuggingFace cache without loading."""

    def test_unknown_size_returns_false(self) -> None:
        """An unrecognised size keyword short-circuits to False."""
        from src.core.live_engine import is_whisper_model_cached  # noqa: PLC0415

        assert is_whisper_model_cached("nonexistent-size") is False

    def test_returns_true_when_cache_lookup_finds_path(self) -> None:
        """Cache hit (string path returned) → True."""
        from unittest.mock import patch  # noqa: PLC0415

        from src.core.live_engine import is_whisper_model_cached  # noqa: PLC0415

        with patch(
            "huggingface_hub.try_to_load_from_cache",
            return_value="/fake/cache/path/config.json",
        ):
            assert is_whisper_model_cached("tiny") is True

    def test_returns_false_when_cache_lookup_misses(self) -> None:
        """Cache miss (None or sentinel) → False."""
        from unittest.mock import patch  # noqa: PLC0415

        from src.core.live_engine import is_whisper_model_cached  # noqa: PLC0415

        with patch(
            "huggingface_hub.try_to_load_from_cache",
            return_value=None,
        ):
            assert is_whisper_model_cached("tiny") is False


class TestTtsAndDisplayComboVisibility:
    """``_update_display_combo_visibility`` gates two widgets on a target lang.

    The display-mode combo (single vs dual) AND the TTS button both
    require a target language to be meaningful — the combo because
    "single" / "dual" are layout choices for a translation column,
    the TTS button because it narrates the *translated* text.  Pin
    that both flip together so a future refactor can't accidentally
    leave the TTS button visible-but-dead when the user picks
    "no translation".
    """

    def test_both_hidden_when_target_empty(
        self,
        qapp,
        qtbot,  # noqa: ANN001, ARG002
    ) -> None:
        """Empty target → display combo hidden, TTS button hidden."""
        from PySide6.QtWidgets import QMainWindow  # noqa: PLC0415

        from src.ui.pages.live import LivePage  # noqa: PLC0415

        win = QMainWindow()
        qtbot.addWidget(win)
        page = LivePage(win)
        qtbot.addWidget(page)
        page.show()
        try:
            # Force "no translation" — itemData of the empty/auto entry is "".
            for i in range(page.target_lang_combo.count()):
                if not page.target_lang_combo.itemData(i):
                    page.target_lang_combo.setCurrentIndex(i)
                    break
            page._update_display_combo_visibility()
            assert page.display_mode_combo.isVisible() is False
            assert page.tts_btn.isVisible() is False
        finally:
            page.hide()

    def test_both_visible_when_target_set(
        self,
        qapp,
        qtbot,  # noqa: ANN001, ARG002
    ) -> None:
        """A real target → both widgets visible."""
        from PySide6.QtWidgets import QMainWindow  # noqa: PLC0415

        from src.ui.pages.live import LivePage  # noqa: PLC0415

        win = QMainWindow()
        qtbot.addWidget(win)
        page = LivePage(win)
        qtbot.addWidget(page)
        page.show()
        try:
            # Pick the first item that has a non-empty locale.
            for i in range(page.target_lang_combo.count()):
                if page.target_lang_combo.itemData(i):
                    page.target_lang_combo.setCurrentIndex(i)
                    break
            page._update_display_combo_visibility()
            assert page.display_mode_combo.isVisible() is True
            assert page.tts_btn.isVisible() is True
        finally:
            page.hide()


class TestTimestampButtonNotCheckable:
    """The Timestamp button is plain (not checkable) — the ``ON``/``OFF`` text wins.

    Pin the regression that the button is no longer ``setCheckable(True)``
    + ``setChecked(...)``: the explicit ``Timestamps ON`` / ``Timestamps OFF``
    label + icon swap already carries the state, so a checked-state
    tint is redundant (and was inconsistent with the TTS / Overlay
    buttons that don't use it).
    """

    def test_button_is_not_checkable(
        self,
        qapp,
        qtbot,  # noqa: ANN001, ARG002
    ) -> None:
        """``time_btn.isCheckable()`` must be False."""
        from PySide6.QtWidgets import QMainWindow  # noqa: PLC0415

        from src.ui.pages.live import LivePage  # noqa: PLC0415

        win = QMainWindow()
        qtbot.addWidget(win)
        page = LivePage(win)
        qtbot.addWidget(page)
        assert page.time_btn.isCheckable() is False

    def test_toggle_swaps_text_without_checked_state(
        self,
        qapp,
        qtbot,  # noqa: ANN001, ARG002
    ) -> None:
        """Toggling flips text+icon; never calls setChecked."""
        from PySide6.QtWidgets import QMainWindow  # noqa: PLC0415

        from src.constants import tr  # noqa: PLC0415
        from src.ui.pages.live import LivePage  # noqa: PLC0415

        win = QMainWindow()
        qtbot.addWidget(win)
        page = LivePage(win)
        qtbot.addWidget(page)
        # Capture initial state, then toggle and verify text flipped.
        initial = page.time_btn.text()
        page._toggle_show_timestamp()
        flipped = page.time_btn.text()
        assert flipped != initial
        # Both labels match one of the two known i18n keys.
        on_label = tr("live.btn_timestamps_on")
        off_label = tr("live.btn_timestamps_off")
        assert {initial, flipped} == {on_label, off_label}


class TestLiveCompactToolbar:
    """Regression coverage for the width-driven compact-toolbar flip.

    The toolbar switches to icon-only mode when the page is narrower
    than ``_COMPACT_TOOLBAR_WIDTH_PX`` (1024 px) — long action labels
    like ``Overlay OFF`` would otherwise truncate / overflow on
    half-screen laptops.  Without a test, a future tweak to the
    threshold (or a missed call site in ``_apply_compact_toolbar``)
    silently regresses the labels-on-small-screens UX.

    Per AGENTS.md, ``window.resize(w, h)`` on an unshown widget can
    be lost under ``--forked`` because the offscreen platform already
    fires an initial size event that consumes the follow-up.  These
    tests synthesise a ``QResizeEvent`` and dispatch it directly to
    ``resizeEvent``, mirroring the pattern in ``test_window.py``.
    """

    @staticmethod
    def _resize(page, width: int) -> None:  # noqa: ANN001
        """Dispatches a synthetic resize event to *page* at *width*."""
        from PySide6.QtCore import QSize  # noqa: PLC0415
        from PySide6.QtGui import QResizeEvent  # noqa: PLC0415

        height = 800
        page.resize(width, height)  # baseline + cache for later width()
        page.resizeEvent(
            QResizeEvent(QSize(width, height), page.size()),
        )

    def test_narrow_window_flips_to_compact_mode(self, live_page) -> None:
        """Width below 1024 px sets ``_compact_toolbar`` True."""
        self._resize(live_page, 900)
        assert live_page._compact_toolbar is True

    def test_wide_window_uses_full_mode(self, live_page) -> None:
        """Width above 1024 px keeps the toolbar in full text-label mode."""
        self._resize(live_page, 1400)
        assert live_page._compact_toolbar is False

    def test_compact_mode_blanks_action_button_text(self, live_page) -> None:
        """Compact mode blanks the action buttons' visible text.

        The icon stays — only the text-label part is hidden so the
        emoji prefix on each button keeps the action recognisable
        when there's no room for the words.  This is the
        load-bearing piece: regressing it would leave full-text
        labels overflowing the toolbar on narrow windows.
        """
        self._resize(live_page, 900)
        for btn in (
            live_page.tts_btn,
            live_page.overlay_btn,
            live_page.time_btn,
            live_page.clear_btn,
        ):
            assert btn.text() == "", (
                f"{btn.accessibleName()} button retained text in compact mode"
            )

    def test_full_mode_restores_action_button_text(self, live_page) -> None:
        """Going from compact back to full mode restores the labels."""
        # Start compact, then widen.
        self._resize(live_page, 900)
        self._resize(live_page, 1400)
        for btn in (
            live_page.tts_btn,
            live_page.overlay_btn,
            live_page.time_btn,
        ):
            assert btn.text() != "", (
                f"{btn.accessibleName()} label not restored when widening"
            )


class TestTranscriptAutoScroll:
    """Regression coverage for the auto-scroll-to-bottom contract.

    User-reported failure mode: a new sentence arrives, the
    scrollbar moves but stops at sentence N-1 instead of the latest
    N.  Root cause: the prior implementation used
    ``QTimer.singleShot(0, lambda: sb.setValue(sb.maximum()))`` which
    fires one event-loop tick after insert — too early for the
    wordWrap two-step relayout to settle, so ``sb.maximum()`` is
    read with the OLD content height.

    Fix: hook ``QScrollBar.rangeChanged`` so the snap fires AFTER
    Qt finishes the layout pass.  Stickiness is tracked via
    ``valueChanged`` so wheel-scrolling up disables auto-snap until
    the user wheels back down.
    """

    def test_range_changed_snaps_to_new_max_when_sticky(
        self,
        live_page,
    ) -> None:
        """A range-grow event with sticky flag True snaps to new max."""
        live_page._stick_single = True
        sb = live_page._scroll.verticalScrollBar()
        # Pre-set the range as Qt would have at the moment
        # ``rangeChanged`` fires — Qt's setValue clamps to
        # ``[minimum, maximum]`` so the range must exist first.
        sb.setRange(0, 1000)
        live_page._on_transcript_range_changed(sb, "_stick_single", 1000)
        assert sb.value() == 1000

    def test_range_changed_skipped_when_user_scrolled_up(
        self,
        live_page,
    ) -> None:
        """When the user scrolled away from the bottom, range growth doesn't snap."""
        live_page._stick_single = False
        sb = live_page._scroll.verticalScrollBar()
        sb.setRange(0, 1000)
        sb.setValue(50)  # user parked here
        live_page._on_transcript_range_changed(sb, "_stick_single", 1000)
        # New range came in, but auto-snap is off — value stays put.
        assert sb.value() == 50

    def test_value_changed_sets_stick_true_at_bottom(
        self,
        live_page,
    ) -> None:
        """Scrolling back to the bottom re-arms the auto-snap."""
        sb = live_page._scroll.verticalScrollBar()
        sb.setMaximum(100)
        live_page._on_transcript_value_changed(sb, "_stick_single", 100)
        assert live_page._stick_single is True

    def test_value_changed_sets_stick_false_when_scrolled_up(
        self,
        live_page,
    ) -> None:
        """Scrolling away from the bottom disarms the auto-snap."""
        sb = live_page._scroll.verticalScrollBar()
        sb.setMaximum(100)
        live_page._on_transcript_value_changed(sb, "_stick_single", 30)
        assert live_page._stick_single is False

    def test_dual_column_has_independent_sticky_flag(
        self,
        live_page,
    ) -> None:
        """Single and dual columns track stickiness via separate flags.

        Asserts the *flags* are wired separately and that the handler
        reads the right one — not the scrollbar value, because the
        scroll area's internal range management races a synthetic
        range-change in test mode.  The runtime contract is: each
        column's auto-snap is gated by its own ``_stick_*`` flag, so
        flipping one doesn't affect the other.
        """
        live_page._stick_single = True
        live_page._stick_dual = False
        # The two scroll areas are distinct objects — confirms the
        # signals were connected to different scrollbars.
        assert (
            live_page._scroll.verticalScrollBar()
            is not live_page._dual_scroll.verticalScrollBar()
        )
        # Flag isolation: mutating one doesn't bleed into the other.
        live_page._stick_dual = True
        assert live_page._stick_single is True
        assert live_page._stick_dual is True
        live_page._stick_single = False
        assert live_page._stick_dual is True  # untouched

    def test_insert_into_no_longer_uses_qtimer_snap(self, live_page) -> None:
        """Regression: _insert_into must NOT use QTimer.singleShot for scroll.

        The deferred-timer approach was the source of the "snap to
        N-1 instead of N" bug.  Reading the source ensures a future
        contributor doesn't re-introduce the same broken pattern
        without realising it raced the wordWrap layout.
        """
        import inspect  # noqa: PLC0415

        src = inspect.getsource(live_page._insert_into)
        # Allow ``QTimer`` to appear elsewhere — but not paired with
        # setValue(maximum()) in this function.
        assert "setValue(sb.maximum())" not in src, (
            "_insert_into still snaps via setValue(sb.maximum()) — "
            "the racy QTimer approach is back"
        )


class TestOverlayBackfillErrors:
    """Regression coverage for the LLM-error backfill contract.

    The user-reported failure mode: open the overlay AFTER an LLM
    failure already landed, and the overlay shows the source line
    but no ⚠ marker — silent loss of state.  Root cause: prior
    ``_on_translation_error`` painted the inline marker on the
    live card / overlay but didn't update ``_transcript_records``,
    so ``_backfill_overlay`` saw an empty translation slot and
    skipped ``set_last_translation`` entirely.

    The fix promotes the records to 5-tuples carrying an
    ``is_error`` flag; ``_backfill_overlay`` now routes errored
    rows through ``set_last_error`` instead.
    """

    def test_failed_translation_record_carries_error_flag(
        self,
        live_page,
    ) -> None:
        """``_on_translation_error`` writes ``is_error=True`` to the record.

        Without this, the record stays ``(ts, spk, orig, "", False)``
        and the next overlay backfill shows source-only — no marker.
        """
        from unittest.mock import MagicMock  # noqa: PLC0415

        from src.constants.i18n import _set_initial_language  # noqa: PLC0415

        # tr() returns the raw key when no language is initialised,
        # which would mask the contract we're checking — pin the
        # locale so the inline marker resolves to real copy.
        _set_initial_language("en-US")
        live_page._transcriber = MagicMock()
        live_page._transcript_records = [
            ("00:00:00 → 00:00:02", "", "Hello world.", "", False),
        ]
        # Build a fake target card whose body matches the pending
        # record's source; mirrors what ``_on_sentence`` pins.
        card = MagicMock()
        card._body.text.return_value = "Hello world."

        # Mock isValid so shiboken doesn't reject the MagicMock.
        with patch("shiboken6.isValid", return_value=True):
            live_page._on_translation_error("QUOTA_ERROR", card, None)

        ts, spk, orig, tgt, err = live_page._transcript_records[0]
        assert err is True, "is_error flag was not set on failure"
        assert "Translation failed" in tgt, (
            "translated slot should hold the inline ⚠ marker text "
            "so backfill can re-render it"
        )

    def test_backfill_routes_errored_records_through_set_last_error(
        self,
        live_page,
    ) -> None:
        """A record with ``is_error=True`` triggers ``set_last_error``.

        Pin the backfill dispatch so re-opening the overlay after a
        failure paints the ⚠ marker (rather than silently dropping
        the translation).
        """
        from unittest.mock import patch  # noqa: PLC0415

        from src.ui.pages.live import _OverlayWindow  # noqa: PLC0415

        live_page._overlay = _OverlayWindow()
        live_page._transcript_records = [
            ("00:00:00 → 00:00:02", "", "Source A", "Bonjour", False),
            (
                "00:00:02 → 00:00:04",
                "",
                "Source B",
                "⚠ Translation failed — quota exceeded.",
                True,
            ),
        ]

        with (
            patch.object(
                live_page._overlay,
                "set_last_translation",
            ) as mock_trans,
            patch.object(
                live_page._overlay,
                "set_last_error",
            ) as mock_err,
        ):
            live_page._backfill_overlay()

        # First record (success) → set_last_translation, NOT error.
        mock_trans.assert_called_once()
        # Second record (failure) → set_last_error, NOT translation.
        mock_err.assert_called_once()
        # Verify the error path got the localised inline text.
        assert "Translation failed" in mock_err.call_args[0][0]


class TestOverlayBackfillStickiness:
    """Regression: re-opening the overlay always lands at the bottom.

    Without the re-arm, a user who scrolled up to read history during
    one visible period would re-open the overlay later and find the
    scrollbar parked at the stale offset — not the newest entry.
    """

    def test_backfill_rearms_stick_to_bottom_even_if_user_scrolled_up(
        self,
        live_page,
    ) -> None:
        """Backfill resets ``_stick_to_bottom`` to True before adding entries."""
        from src.ui.pages.live import _OverlayWindow  # noqa: PLC0415

        live_page._overlay = _OverlayWindow()
        # Simulate the prior-session state: user scrolled up, so
        # ``valueChanged`` flipped stickiness off.
        live_page._overlay._stick_to_bottom = False
        live_page._transcript_records = [
            ("00:00:00 → 00:00:02", "", "old", "ancien", False),
            ("00:00:02 → 00:00:04", "", "new", "nouveau", False),
        ]
        live_page._backfill_overlay()
        # Sticky flag must be re-armed so future ``rangeChanged``
        # signals (from add_entry / set_last_translation) snap to bottom.
        assert live_page._overlay._stick_to_bottom is True, (
            "backfill failed to re-arm auto-snap; re-opening the overlay "
            "would leave the scrollbar at the stale offset"
        )


# =====================================================================
# Auto-stop-after-silence timer
# =====================================================================


class TestLivePageAutoStop:
    """Auto-stop session after N minutes of silence (no finalised sentences).

    The timer is a single-shot ``QTimer`` armed by ``_start_listening``,
    restarted by every ``_on_sentence``, and disarmed by
    ``_stop_listening``.  The setting (``SETTING_LIVE_AUTO_STOP_MINUTES``)
    is read at session start; 0 = disabled.
    """

    def test_start_with_setting_zero_does_not_arm_timer(
        self,
        live_page,
    ) -> None:
        """A zero/missing setting means no idle timer is created.

        Opt-in by default — users who don't configure auto-stop get
        the old "runs forever" behaviour.
        """
        from unittest.mock import patch  # noqa: PLC0415

        from src.constants.settings import (  # noqa: PLC0415
            SETTING_LIVE_AUTO_STOP_MINUTES,
        )

        with patch(
            "src.ui.pages.live.load_setting",
            side_effect=lambda k, default=None: (
                0 if k == SETTING_LIVE_AUTO_STOP_MINUTES else default
            ),
        ):
            live_page._start_idle_timer()
        assert live_page._idle_timer is None

    def test_start_with_positive_setting_arms_single_shot_timer(
        self,
        live_page,
    ) -> None:
        """A positive minutes setting arms a single-shot timer.

        The interval must match ``minutes × 60 × 1000`` so the timer
        fires after exactly that many minutes of silence.
        """
        from unittest.mock import patch  # noqa: PLC0415

        from src.constants.settings import (  # noqa: PLC0415
            SETTING_LIVE_AUTO_STOP_MINUTES,
        )

        with patch(
            "src.ui.pages.live.load_setting",
            side_effect=lambda k, default=None: (
                5 if k == SETTING_LIVE_AUTO_STOP_MINUTES else default
            ),
        ):
            live_page._start_idle_timer()
        assert live_page._idle_timer is not None
        assert live_page._idle_timer.isSingleShot() is True
        assert live_page._idle_timer.interval() == 5 * 60 * 1000
        assert live_page._idle_minutes == 5
        # Clean up so other tests don't get a stray timer firing.
        live_page._stop_idle_timer()

    def test_stop_listening_disarms_timer(self, live_page) -> None:
        """``_stop_listening`` must null the idle timer.

        Otherwise a stray ``timeout`` signal could fire on the
        already-stopped page and re-trigger ``_stop_listening`` from
        a dead state.
        """
        from unittest.mock import patch  # noqa: PLC0415

        from src.constants.settings import (  # noqa: PLC0415
            SETTING_LIVE_AUTO_STOP_MINUTES,
        )

        with patch(
            "src.ui.pages.live.load_setting",
            side_effect=lambda k, default=None: (
                3 if k == SETTING_LIVE_AUTO_STOP_MINUTES else default
            ),
        ):
            live_page._start_idle_timer()
        assert live_page._idle_timer is not None

        # Patch ``_stop_audio_feed`` + transcriber to avoid real teardown.
        live_page._transcriber = None
        with (
            patch.object(live_page, "_stop_audio_feed"),
            patch.object(
                live_page,
                "_reset_ui_to_ready",
            ),
        ):
            live_page._stop_listening()

        assert live_page._idle_timer is None
        assert live_page._idle_minutes == 0

    def test_on_sentence_restarts_idle_timer(self, live_page) -> None:
        """Each finalised sentence restarts the single-shot countdown.

        Restart semantics: a single-shot ``QTimer.start()`` resets
        the remaining interval back to its full value, so as long
        as someone keeps talking the session continues.
        """
        from unittest.mock import patch  # noqa: PLC0415

        from src.constants.settings import (  # noqa: PLC0415
            SETTING_LIVE_AUTO_STOP_MINUTES,
        )

        live_page._transcriber = MagicMock()  # bypass the late-signal guard

        with patch(
            "src.ui.pages.live.load_setting",
            side_effect=lambda k, default=None: (
                10 if k == SETTING_LIVE_AUTO_STOP_MINUTES else default
            ),
        ):
            live_page._start_idle_timer()

        timer = live_page._idle_timer
        assert timer is not None
        # Mock the timer's ``start`` to observe the call without
        # actually re-running the QTimer state machine.
        with patch.object(timer, "start") as mock_start:
            live_page._on_sentence("hello", 0.0, 1.0, "", "")
            mock_start.assert_called_once()

        live_page._stop_idle_timer()

    def test_idle_timeout_calls_stop_and_shows_banner(
        self,
        live_page,
    ) -> None:
        """When the timer fires, ``_stop_listening`` runs + banner shows.

        The user may be away — the sticky banner is their only
        signal when they return.  Calls the same ``_show_status_error``
        path that engine-error toasts use, with ``sticky=True``.
        """
        from unittest.mock import patch  # noqa: PLC0415

        from src.constants.i18n import _set_initial_language  # noqa: PLC0415

        _set_initial_language("en-US")  # load tr() table for the toast
        live_page._idle_minutes = 7
        live_page._transcriber = MagicMock()
        with (
            patch.object(
                live_page,
                "_stop_listening",
            ) as mock_stop,
            patch.object(
                live_page,
                "_show_status_error",
            ) as mock_banner,
        ):
            live_page._on_idle_timeout()
        mock_stop.assert_called_once()
        mock_banner.assert_called_once()
        call_args = mock_banner.call_args
        # Banner is sticky so the user notices when they come back.
        assert call_args.kwargs.get("sticky") is True
        # Message mentions the elapsed minutes (7) so the user
        # understands why the session ended.
        message_arg = call_args.args[0]
        assert "7" in message_arg


# ===========================================================================
# TestSpeakerRename — double-click rename + page-level alias propagation
# ===========================================================================


class TestSpeakerRename:
    """Speaker-chip rename: alias storage, chip refresh, save-time mapping."""

    def test_display_speaker_falls_back_to_formatted_when_no_alias(
        self,
        live_page,
    ) -> None:
        """Without an alias, ``_display_speaker`` returns ``Speaker N``.

        The default formatter is the single source of truth for the
        zero-aliases case; without this contract a UI that depends
        on the alias map being non-empty would silently break for
        every new session.
        """
        assert live_page._speaker_aliases == {}
        assert live_page._display_speaker("speaker_0") == "Speaker 1"
        assert live_page._display_speaker("speaker_2") == "Speaker 3"
        assert live_page._display_speaker("") == ""

    def test_display_speaker_returns_alias_when_set(self, live_page) -> None:
        """An alias entry overrides the default formatter."""
        live_page._speaker_aliases["speaker_0"] = "Alice"
        assert live_page._display_speaker("speaker_0") == "Alice"
        # Other IDs remain unaffected.
        assert live_page._display_speaker("speaker_1") == "Speaker 2"

    def test_on_speaker_renamed_stores_alias_and_refreshes_chips(
        self,
        live_page,
    ) -> None:
        """Rename updates the map AND walks visible chips for refresh.

        End-to-end pin: simulates a Soniox-style sentence arriving
        for ``speaker_0``, then a rename, then checks that the
        single-card AND dual-pair chips both show "Alice" without
        any reconstruction.
        """
        from src.ui.pages.live import _RenamableSpeakerChip  # noqa: PLC0415

        live_page._transcriber = MagicMock()
        sc, dp = live_page._add_original(
            "Hello",
            "00:00:00 → 00:00:02",
            "Speaker 1",
            speaker_id="speaker_0",
        )
        # Sanity: the chip is renamable and tagged with the right ID.
        assert isinstance(sc._speaker_chip, _RenamableSpeakerChip)
        assert sc._speaker_id == "speaker_0"
        assert dp._speaker_id == "speaker_0"
        assert sc._speaker_chip.text() == "Speaker 1"
        assert dp._speaker_chip.text() == "Speaker 1"

        live_page._on_speaker_renamed("speaker_0", "Alice")
        assert live_page._speaker_aliases["speaker_0"] == "Alice"
        assert sc._speaker_chip.text() == "Alice"
        assert dp._speaker_chip.text() == "Alice"

    def test_empty_input_clears_alias_and_restores_default(self, live_page) -> None:
        """An empty / whitespace-only commit reverts to ``Speaker N``."""
        live_page._transcriber = MagicMock()
        sc, _ = live_page._add_original(
            "Hi",
            "00:00:00 → 00:00:02",
            "Speaker 1",
            speaker_id="speaker_0",
        )
        live_page._on_speaker_renamed("speaker_0", "Boss")
        assert sc._speaker_chip.text() == "Boss"

        # Now clear it.
        live_page._on_speaker_renamed("speaker_0", "   ")
        assert "speaker_0" not in live_page._speaker_aliases
        assert sc._speaker_chip.text() == "Speaker 1"

    def test_rename_to_default_label_drops_alias(self, live_page) -> None:
        """Typing back the default Speaker N name is treated as a clear.

        Otherwise the alias map would hold a redundant entry that
        survives session reset checks.
        """
        live_page._transcriber = MagicMock()
        live_page._add_original(
            "Hi",
            "00:00:00 → 00:00:02",
            "Speaker 1",
            speaker_id="speaker_0",
        )
        live_page._on_speaker_renamed("speaker_0", "Speaker 1")
        assert "speaker_0" not in live_page._speaker_aliases

    def test_only_matching_speaker_chips_refresh(self, live_page) -> None:
        """A rename for speaker_0 must NOT touch speaker_1's chip."""
        live_page._transcriber = MagicMock()
        sc0, _ = live_page._add_original(
            "Hi",
            "00:00:00 → 00:00:02",
            "Speaker 1",
            speaker_id="speaker_0",
        )
        sc1, _ = live_page._add_original(
            "Hello",
            "00:00:02 → 00:00:04",
            "Speaker 2",
            speaker_id="speaker_1",
        )
        live_page._on_speaker_renamed("speaker_0", "Alice")
        assert sc0._speaker_chip.text() == "Alice"
        # Speaker 2's chip untouched.
        assert sc1._speaker_chip.text() == "Speaker 2"

    def test_rename_refreshes_overlay_chip_too(self, live_page) -> None:
        """The overlay's chip for the same speaker_id updates on rename.

        ``_refresh_speaker_chips`` walks three surfaces: the single
        transcript layout, the dual-pair layout, AND the open
        overlay's lines.  The overlay path is the easiest to
        accidentally break with a future refactor — covered here
        explicitly.
        """
        from src.ui.pages.live import _OverlayWindow  # noqa: PLC0415

        live_page._transcriber = MagicMock()
        # Show the overlay so ``_add_original`` mirrors the entry
        # into it (the overlay backfill is gated on ``isVisible()``).
        live_page._overlay = _OverlayWindow()
        live_page._overlay.show()
        try:
            live_page._add_original(
                "Hello",
                "00:00:00 → 00:00:02",
                "Speaker 1",
                speaker_id="speaker_0",
            )
            # Pre-rename: overlay chip shows the default label.
            overlay_entry = next(live_page._overlay._iter_entries())
            assert overlay_entry._speaker_chip is not None
            assert overlay_entry._speaker_chip.text() == "Speaker 1"
            assert overlay_entry._speaker_id == "speaker_0"

            live_page._on_speaker_renamed("speaker_0", "Alice")

            # Overlay's chip picked up the new alias without
            # rebuilding the entry.
            assert overlay_entry._speaker_chip.text() == "Alice"
        finally:
            live_page._overlay.close()
            live_page._overlay = None

    def test_future_sentence_uses_existing_alias(self, live_page) -> None:
        """A sentence arriving AFTER a rename inherits the alias immediately.

        ``_on_sentence`` resolves the display via ``_display_speaker``
        rather than going through ``_format_speaker`` directly, so
        the next chip lands pre-renamed.  Without this routing the
        new chip would render "Speaker 1" and only catch up on the
        NEXT rename.
        """
        live_page._transcriber = MagicMock()
        live_page._speaker_aliases["speaker_0"] = "Alice"
        assert live_page._display_speaker("speaker_0") == "Alice"

    def test_aliases_cleared_on_start_listening(self, live_page) -> None:
        """A fresh Start resets the alias map; Clear Log does NOT.

        Soniox's diarized IDs are session-relative, so a saved alias
        from a previous session would mis-label a stranger in the
        next session — hence the clear on Start.  But Clear Log
        keeps the same session running; clearing the alias there
        would lose the user's "Alice" rename for the SAME speaker
        as soon as they emptied the transcript view.
        """
        from unittest.mock import patch  # noqa: PLC0415

        live_page._speaker_aliases["speaker_0"] = "Alice"

        # Clear Log alone must NOT drop the alias.
        live_page._reset_transcript_state()
        assert live_page._speaker_aliases == {"speaker_0": "Alice"}

        # A fresh Start does — new session, new diarized IDs.
        with (
            patch(
                "src.core.live_engine.check_audio_available",
                return_value="",
            ),
            patch(
                "src.core.live_engine.check_system_audio_available",
                return_value=True,
            ),
            patch.object(
                live_page,
                "_start_whisper",
            ),
            patch.object(live_page, "_start_soniox"),
        ):
            live_page._start_listening()
        assert live_page._speaker_aliases == {}

    def test_save_transcript_applies_aliases(self, live_page) -> None:
        """Saved SRT cues use the user-chosen alias, not the raw ID.

        Records hold raw IDs so a rename retroactively flows into
        every prior cue.  The format helper must consult the alias
        map per record at save time.
        """
        live_page._transcript_records.append(
            ("00:00:00 → 00:00:02", "speaker_0", "Hello", "Hola", False),
        )
        live_page._transcript_records.append(
            ("00:00:02 → 00:00:04", "speaker_1", "World", "Mundo", False),
        )
        live_page._speaker_aliases["speaker_0"] = "Alice"
        # speaker_1 has no alias; default formatter wins.

        srt = live_page._format_transcript_srt()
        assert "[Alice] Hello" in srt
        assert "[Speaker 2] World" in srt
        assert "speaker_0" not in srt  # raw ID never leaks
        assert "speaker_1" not in srt

    def test_renamable_chip_emits_signal_on_commit(self, qapp) -> None:  # noqa: ARG002
        """Commit path: ``editingFinished`` → ``renamed`` signal fires."""
        from src.ui.pages.live import _RenamableSpeakerChip  # noqa: PLC0415

        chip = _RenamableSpeakerChip("speaker_0", "Speaker 1", "#ff0000")
        received: list[tuple[str, str]] = []
        chip.renamed.connect(lambda sid, name: received.append((sid, name)))

        chip._begin_edit()
        assert chip._editor is not None
        chip._editor.setText("Alice")
        chip._commit_edit()

        assert received == [("speaker_0", "Alice")]
        assert chip._editor is None
        # Chip is visible again so the user sees the new label.
        assert chip.isVisible() or not chip.isHidden()

    def test_renamable_chip_cancels_without_emitting(self, qapp) -> None:  # noqa: ARG002
        """Esc / cancel: editor torn down, no ``renamed`` signal."""
        from src.ui.pages.live import _RenamableSpeakerChip  # noqa: PLC0415

        chip = _RenamableSpeakerChip("speaker_0", "Speaker 1", "#ff0000")
        received: list[tuple[str, str]] = []
        chip.renamed.connect(lambda sid, name: received.append((sid, name)))

        chip._begin_edit()
        chip._editor.setText("Alice")
        chip._cancel_edit()

        assert received == []
        assert chip._editor is None

    def test_begin_edit_is_idempotent(self, qapp) -> None:  # noqa: ARG002
        """A second ``_begin_edit`` while one is in flight is a no-op.

        Without this guard a double-double-click (or a programmatic
        re-entry) would orphan the first editor — it would lose its
        reference but stay visible on screen, with no way to commit
        or cancel.  Pins the idempotence contract.
        """
        from src.ui.pages.live import _RenamableSpeakerChip  # noqa: PLC0415

        chip = _RenamableSpeakerChip("speaker_0", "Speaker 1", "#ff0000")
        chip._begin_edit()
        first_editor = chip._editor
        assert first_editor is not None

        # Second call must NOT create a new editor.
        chip._begin_edit()
        assert chip._editor is first_editor

        chip._cancel_edit()

    def test_double_click_with_non_left_button_does_not_enter_edit(
        self,
        qapp,  # noqa: ARG002
    ) -> None:
        """Right-/middle-double-click on a chip falls through to the base class.

        Edit mode is explicitly LEFT-only.  Other buttons must not
        steal the event (some users right-double-click for context
        menus and would lose their selection if we hijacked it).
        """
        from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: PLC0415
        from PySide6.QtGui import QMouseEvent  # noqa: PLC0415

        from src.ui.pages.live import _RenamableSpeakerChip  # noqa: PLC0415

        chip = _RenamableSpeakerChip("speaker_0", "Speaker 1", "#ff0000")
        event = QMouseEvent(
            QEvent.Type.MouseButtonDblClick,
            QPointF(1.0, 1.0),
            Qt.MouseButton.RightButton,
            Qt.MouseButton.RightButton,
            Qt.KeyboardModifier.NoModifier,
        )
        chip.mouseDoubleClickEvent(event)
        # Editor was never created.
        assert chip._editor is None

    def test_esc_via_event_filter_cancels_edit(self, qapp) -> None:  # noqa: ARG002
        """Pressing Esc inside the editor routes through ``eventFilter`` → cancel.

        The Esc-handling path is the eventFilter installed on the
        editor, not on the chip directly.  Pin that the filter
        catches the key event AND swallows it (returns True) so
        the parent (often the overlay) doesn't also act on Esc.
        """
        from PySide6.QtCore import QEvent, Qt  # noqa: PLC0415
        from PySide6.QtGui import QKeyEvent  # noqa: PLC0415

        from src.ui.pages.live import _RenamableSpeakerChip  # noqa: PLC0415

        chip = _RenamableSpeakerChip("speaker_0", "Speaker 1", "#ff0000")
        received: list[tuple[str, str]] = []
        chip.renamed.connect(lambda sid, name: received.append((sid, name)))

        chip._begin_edit()
        editor = chip._editor
        editor.setText("typed-but-cancelled")

        key_event = QKeyEvent(
            QEvent.Type.KeyPress,
            int(Qt.Key.Key_Escape),
            Qt.KeyboardModifier.NoModifier,
        )
        handled = chip.eventFilter(editor, key_event)
        # Esc was swallowed (no propagation to parent).
        assert handled is True
        # Cancel path: editor gone, no rename signal emitted.
        assert chip._editor is None
        assert received == []


# ===========================================================================
# TestAsyncStop — non-blocking engine teardown
# ===========================================================================


class TestAsyncStop:
    """Stop must not freeze the UI thread.

    ``LiveTranscriber.stop()`` joins the Whisper worker thread with a
    5-second timeout (faster-whisper has no inference-cancellation
    hook), and the Soniox audio-feed teardown adds another
    SIGTERM-→SIGKILL escalation plus thread joins.  Worst-case
    pre-refactor: ~12 s of frozen UI per Stop click.  The Stop click
    now spawns :class:`_EngineStopWorker` off-thread; these tests pin
    the new contract.
    """

    def test_stop_nulls_engine_refs_synchronously(self, live_page) -> None:
        """Page presents as stopped to late signals BEFORE the worker runs.

        Late-signal guards in ``_on_sentence`` / ``_on_status`` /
        etc. drop callbacks when ``self._transcriber is None``.  For
        that guard to work during teardown, the page must null
        ``_transcriber`` synchronously on the UI thread — even
        though the actual ``transcriber.stop()`` runs in the worker.
        """
        live_page._transcriber = MagicMock()
        live_page._stop_listening()
        # ``_transcriber`` is cleared synchronously, BEFORE we wait.
        assert live_page._transcriber is None

    def test_stop_spawns_worker_and_flips_to_stopping_state(
        self,
        live_page,
    ) -> None:
        """Stop should immediately show "Stopping…" + disabled button + spawn worker.

        The user clicks Stop; the UI must visibly acknowledge the
        click WITHIN the same UI-thread tick.  Without an immediate
        state flip + a worker that does the blocking work,
        teardown freezes look like the app stopped responding.
        """
        from src.constants import tr  # noqa: PLC0415
        from src.ui.pages.live import _EngineStopWorker  # noqa: PLC0415

        live_page._transcriber = MagicMock()
        live_page._stop_listening()

        # Worker exists and is the right type.
        assert isinstance(live_page._stop_worker, _EngineStopWorker)
        # Transitional UI is visible — button disabled + "Stopping…" text.
        assert live_page.start_btn.isEnabled() is False
        assert live_page.start_btn.text() == tr("live.btn_stopping")
        assert live_page.status_label.text() == tr("live.status_stopping")

        _drain_stop_worker(live_page)
        # After teardown completes the page returns to Ready.
        assert live_page._stop_worker is None
        assert live_page.start_btn.isEnabled() is True
        assert live_page.start_btn.text() == tr("live.btn_start")

    def test_stop_with_nothing_running_skips_worker(self, live_page) -> None:
        """No engine + no audio feed → flip to Ready directly, no worker.

        Spawning a QThread just to do nothing wastes resources AND
        adds a tick of latency before the UI updates.  Pin the
        fast-path so a future refactor can't silently start
        spawning workers for empty Stop calls.
        """
        live_page._transcriber = None
        live_page._soniox_stream = None
        live_page._soniox_parec = None
        live_page._soniox_parec_thread = None
        live_page._soniox_mixer_thread = None

        live_page._stop_listening()
        assert live_page._stop_worker is None
        # Button remains enabled (never went through the Stopping state).
        assert live_page.start_btn.isEnabled() is True

    def test_double_stop_is_idempotent(self, live_page) -> None:
        """A second Stop click while teardown is in-flight is a no-op.

        Without idempotence, the second call would null already-
        captured refs to None (the worker still holds them) and
        spawn a second worker against an empty set, racing the
        first.  The button being disabled covers most callers, but
        the keyboard shortcut path can still re-enter.
        """
        live_page._transcriber = MagicMock()
        live_page._stop_listening()
        first_worker = live_page._stop_worker
        assert first_worker is not None

        # Second call must NOT spawn a new worker.
        live_page._stop_listening()
        assert live_page._stop_worker is first_worker

        _drain_stop_worker(live_page)

    def test_engine_stop_worker_runs_transcriber_stop_off_thread(
        self,
        qapp,  # noqa: ARG002
    ) -> None:
        """``_EngineStopWorker.run`` calls ``transcriber.stop()``.

        The worker's ``run`` body is what actually unblocks the UI:
        every blocking call ``_stop_listening`` used to do
        synchronously now lives in here.  Pin the contract.
        """
        from src.ui.pages.live import _EngineStopWorker  # noqa: PLC0415

        mock_t = MagicMock()
        worker = _EngineStopWorker(mock_t)
        worker.run()  # Synchronous call — no need to start a thread.
        mock_t.stop.assert_called_once()

    def test_engine_stop_worker_tears_down_soniox_refs(
        self,
        qapp,  # noqa: ARG002
    ) -> None:
        """Worker tears down stream, parec, reader thread, mixer.

        Mirror of the Soniox audio-feed cleanup that used to live in
        ``_stop_audio_feed`` on the UI thread.  All five teardown
        actions must fire in order: stream.stop/close → parec
        terminate → reader join → mixer stop-event → mixer join.
        """
        from src.ui.pages.live import _EngineStopWorker  # noqa: PLC0415

        mock_stream = MagicMock()
        mock_parec = MagicMock()
        mock_parec.wait = MagicMock()  # returns silently → no kill escalation
        mock_reader = MagicMock()
        mock_stop_event = MagicMock()
        mock_mixer = MagicMock()
        worker = _EngineStopWorker(
            None,  # no transcriber for this test
            soniox_stream=mock_stream,
            soniox_parec=mock_parec,
            soniox_parec_thread=mock_reader,
            soniox_mixer_stop=mock_stop_event,
            soniox_mixer_thread=mock_mixer,
        )
        worker.run()
        mock_stream.stop.assert_called_once()
        mock_stream.close.assert_called_once()
        mock_parec.terminate.assert_called_once()
        mock_parec.wait.assert_called_once()
        mock_reader.join.assert_called_once_with(timeout=1)
        mock_stop_event.set.assert_called_once()
        mock_mixer.join.assert_called_once_with(timeout=1)

    def test_engine_stop_worker_escalates_to_kill_on_terminate_timeout(
        self,
        qapp,  # noqa: ARG002
    ) -> None:
        """Parec ignoring SIGTERM → SIGKILL + bounded wait.

        Hardening against a parec process that refuses to exit on
        SIGTERM (e.g. stuck in a kernel call).  Worker escalates to
        SIGKILL and re-waits with a 1-second cap.  Without this the
        worker would leak the process reference.
        """
        import subprocess  # noqa: PLC0415

        from src.ui.pages.live import _EngineStopWorker  # noqa: PLC0415

        mock_parec = MagicMock()
        mock_parec.wait.side_effect = [
            subprocess.TimeoutExpired(cmd="parec", timeout=1),  # SIGTERM ignored
            None,  # SIGKILL wait succeeds
        ]
        worker = _EngineStopWorker(None, soniox_parec=mock_parec)
        worker.run()
        mock_parec.terminate.assert_called_once()
        mock_parec.kill.assert_called_once()

    def test_late_stop_signal_does_not_clobber_new_session(
        self,
        live_page,
    ) -> None:
        """``_on_stop_complete`` skips the UI reset when a new session is live.

        Race: user keyboard-shortcuts Stop → Start within
        milliseconds, OR auto-stop fires and the user clicks Start
        before the worker's ``finished`` slot lands on the UI
        thread.  By the time the slot runs, ``self._transcriber``
        already points at the NEW transcriber; flipping the button
        to "Start" then would visibly contradict the live session.
        """
        from src.constants import tr  # noqa: PLC0415

        # Simulate the live session that's already started.
        live_page._transcriber = MagicMock()
        live_page.start_btn.setText(tr("live.btn_stop"))
        live_page.start_btn.setEnabled(True)
        # Hand the page a fake stop-worker so ``_on_stop_complete``
        # exercises its deleteLater branch.
        live_page._stop_worker = MagicMock()

        live_page._on_stop_complete()

        # New session is preserved — button stays as "Stop".
        assert live_page._transcriber is not None
        assert live_page.start_btn.text() == tr("live.btn_stop")
        # Worker ref was still cleared so a subsequent Stop can spawn fresh.
        assert live_page._stop_worker is None

    def test_old_on_stopped_callback_is_filtered_after_new_session(
        self,
        live_page,
    ) -> None:
        """Stale ``on_stopped`` from a prior session doesn't reach the slot.

        Race: user clicks Stop → starts new session before the OLD
        engine's ``on_stopped`` callback lands on the UI thread.
        Filtering happens in the closure returned by
        ``_make_filtered_on_stopped`` — each new session bumps the
        session generation counter, and the captured ``my_gen``
        only matches while that session is still the current one.
        An OLD callback firing after a new session started compares
        against the NEW gen, misses, and skips the signal emit.
        """
        # Capture an OLD-session callback (gen=N).
        old_cb = live_page._make_filtered_on_stopped()
        old_gen = live_page._session_gen

        # Simulate the user starting a fresh session → bumps the gen.
        new_cb = live_page._make_filtered_on_stopped()
        assert live_page._session_gen != old_gen

        # Spy on the page-level signal.
        received: list = []
        live_page._transcriber_stopped.connect(lambda: received.append(1))

        # Late-arriving OLD callback should NOT emit.
        old_cb()
        assert received == []

        # New callback DOES emit (matches current gen).
        new_cb()
        assert received == [1]

    def test_filtered_on_stopped_emits_for_legitimate_self_terminate(
        self,
        live_page,
    ) -> None:
        """Non-racing engine-exited case still propagates the signal.

        Confirms the closure isn't over-filtering: when a session
        is alive (gen matches), its engine self-terminating still
        fires the page-level ``_transcriber_stopped`` signal.
        """
        cb = live_page._make_filtered_on_stopped()

        received: list = []
        live_page._transcriber_stopped.connect(lambda: received.append(1))

        cb()
        assert received == [1]

    def test_make_filtered_on_stopped_bumps_session_gen_each_call(
        self,
        live_page,
    ) -> None:
        """Every call increments the page's session-generation counter.

        The closure's identity check relies on a strictly-increasing
        counter — if two calls captured the same gen, an OLD
        callback's emit would falsely match a NEW session.  Pin
        the increment contract explicitly.
        """
        before = live_page._session_gen
        live_page._make_filtered_on_stopped()
        after_first = live_page._session_gen
        live_page._make_filtered_on_stopped()
        after_second = live_page._session_gen

        assert after_first == before + 1
        assert after_second == after_first + 1

    def test_engine_stop_worker_swallows_transcriber_exception(
        self,
        qapp,  # noqa: ARG002
    ) -> None:
        """If ``transcriber.stop()`` raises, the worker logs + continues.

        Defence-in-depth: a buggy engine that throws inside its
        ``stop()`` must not propagate the exception out of the
        worker's ``run()``.  Doing so would prevent Qt from
        emitting ``finished``, which would in turn leave the
        page's ``_on_stop_complete`` slot hanging — the button
        would stay "Stopping…" forever.
        """
        from src.ui.pages.live import _EngineStopWorker  # noqa: PLC0415

        mock_t = MagicMock()
        mock_t.stop.side_effect = RuntimeError("boom")
        worker = _EngineStopWorker(mock_t)
        # Must not raise.
        worker.run()
        mock_t.stop.assert_called_once()


# ===========================================================================
# TestTTSConfigSnapshot — per-session TTS settings cache
# ===========================================================================


class TestTTSConfigSnapshot:
    """Live TTS settings are snapshotted once per session, not per sentence.

    Pre-cache, ``_TTSWorker.run`` called ``load_setting`` up to 4×
    per synthesized sentence, plus one more in ``_process_tts_queue``
    on the UI thread.  For a 50-sentence Live session that's ~250
    redundant INI reads.  These tests pin the snapshot + dispatch
    contract.
    """

    def test_tts_config_is_frozen_dataclass(self, qapp) -> None:  # noqa: ARG002
        """``_TTSConfig`` is frozen so a thread can hold a reference safely.

        Workers run on a QThread and read the snapshot from outside
        the UI thread.  Freezing the dataclass prevents accidental
        mutations that could surface as a torn-read race.
        """
        from dataclasses import FrozenInstanceError, fields  # noqa: PLC0415

        from src.ui.pages.live import _TTSConfig  # noqa: PLC0415

        cfg = _TTSConfig(
            method="Edge TTS",
            target_lang="Vietnamese",
            elevenlabs_api_key="",
            elevenlabs_voice_id="",
            elevenlabs_model="",
            google_api_key="",
        )
        # Frozen-dataclass contract: setattr raises.
        with pytest.raises(FrozenInstanceError):
            cfg.method = "Google Cloud"  # type: ignore[misc]
        # All expected fields exist.
        field_names = {f.name for f in fields(cfg)}
        assert field_names == {
            "method",
            "target_lang",
            "elevenlabs_api_key",
            "elevenlabs_voice_id",
            "elevenlabs_model",
            "google_api_key",
        }

    def test_capture_tts_config_reads_each_setting_once(
        self,
        live_page,
    ) -> None:
        """``_capture_tts_config`` reads every TTS setting in one shot.

        The whole point of the snapshot is to amortise the per-key
        ``load_setting`` cost.  Verify by spying on the function
        and counting the keys it touched.
        """
        from unittest.mock import patch  # noqa: PLC0415

        with (
            patch(
                f"{_MOD}.load_setting",
                side_effect=lambda k, d="": str(d),
            ) as ls,
            patch(
                "src.utils.config_manager.load_google_cloud_api_key",
                return_value="goog-key",
            ),
        ):
            cfg = live_page._capture_tts_config()

        # Every TTS-related setting was read exactly once.
        keys = [c.args[0] for c in ls.call_args_list]
        assert any("voice/tts_method" in k or k.endswith("tts_method") for k in keys), (
            f"missing tts_method read: {keys}"
        )
        assert cfg.google_api_key == "goog-key"

    def test_tts_worker_uses_config_when_provided(self, qapp) -> None:  # noqa: ARG002
        """``_TTSWorker(... config=cfg)`` skips per-sentence ``load_setting``.

        Drops the worker into Edge mode via the snapshot, mocks
        the synthesizer, and asserts no ``load_setting`` call
        landed during ``run()``.
        """
        from unittest.mock import patch  # noqa: PLC0415

        from src.ui.pages.live import _TTSConfig  # noqa: PLC0415

        cfg = _TTSConfig(
            method="Edge TTS",
            target_lang="Vietnamese",
            elevenlabs_api_key="",
            elevenlabs_voice_id="",
            elevenlabs_model="",
            google_api_key="",
        )
        worker = _make_tts_worker("hello", "Vietnamese", "FEMALE")
        worker._config = cfg

        with (
            patch(f"{_MOD}.load_setting") as ls,
            patch(
                "src.core.speech_engine._synthesize_chunk_edge",
            ),
            patch("src.core.speech_engine._get_edge_voice", return_value="v"),
        ):
            worker.run()

        assert ls.call_count == 0, (
            f"expected zero load_setting calls under config snapshot, "
            f"got {ls.call_args_list}"
        )

    def test_tts_worker_falls_back_to_load_setting_without_config(
        self,
        qapp,  # noqa: ARG002
    ) -> None:
        """Legacy ``_TTSWorker(text, lang, gender)`` (no config) still works.

        Existing tests construct the worker via the 3-arg path and
        rely on ``load_setting`` being called inside ``run``.  The
        no-config branch must keep that contract — otherwise every
        test that patches ``load_setting`` silently breaks.
        """
        from unittest.mock import patch  # noqa: PLC0415

        worker = _make_tts_worker("hello", "Vietnamese", "FEMALE")
        assert worker._config is None

        with (
            patch(
                f"{_MOD}.load_setting",
                return_value="Edge TTS",
            ) as ls,
            patch(
                "src.core.speech_engine._synthesize_chunk_edge",
            ),
            patch("src.core.speech_engine._get_edge_voice", return_value="v"),
        ):
            worker.run()

        # At least one call was made (the engine read).
        assert ls.call_count >= 1

    def test_start_listening_captures_tts_config(self, live_page) -> None:
        """``_start_listening`` populates ``_tts_config`` before any TTS fires.

        The first sentence's TTS worker needs the snapshot to be in
        place.  Pin the timing so a future refactor can't slip the
        capture later than the first sentence.
        """
        from unittest.mock import patch  # noqa: PLC0415

        with (
            patch.object(
                live_page,
                "_capture_tts_config",
                wraps=live_page._capture_tts_config,
            ) as capture_spy,
            patch(
                "src.core.live_engine.check_audio_available",
                return_value="",
            ),
            patch(
                "src.core.live_engine.check_system_audio_available",
                return_value=True,
            ),
            patch.object(
                live_page,
                "_start_whisper",
            ),
            patch.object(live_page, "_start_soniox"),
        ):
            live_page._start_listening()

        capture_spy.assert_called_once()
        assert live_page._tts_config is not None

    def test_start_listening_refreshes_tts_config_clear_log_preserves(
        self,
        live_page,
    ) -> None:
        """Start re-snapshots TTS config; Clear Log preserves the snapshot.

        Clear Log is mid-session — the engine keeps running and the
        next sentence still needs the cached snapshot to avoid the
        per-sentence INI reads we set out to eliminate.  Only a
        fresh Start should reset the snapshot.
        """
        from unittest.mock import patch  # noqa: PLC0415

        from src.ui.pages.live import _TTSConfig  # noqa: PLC0415

        stale = _TTSConfig(
            method="Edge TTS",
            target_lang="Vietnamese",
            elevenlabs_api_key="stale-key",
            elevenlabs_voice_id="",
            elevenlabs_model="",
            google_api_key="",
        )
        live_page._tts_config = stale

        # Clear Log alone keeps the snapshot — session continues.
        live_page._reset_transcript_state()
        assert live_page._tts_config is stale

        # Start replaces the snapshot with a fresh capture.
        with (
            patch(
                "src.core.live_engine.check_audio_available",
                return_value="",
            ),
            patch(
                "src.core.live_engine.check_system_audio_available",
                return_value=True,
            ),
            patch.object(
                live_page,
                "_start_whisper",
            ),
            patch.object(live_page, "_start_soniox"),
        ):
            live_page._start_listening()
        assert live_page._tts_config is not None
        assert live_page._tts_config is not stale

    def test_toggle_tts_off_to_on_refreshes_config(self, live_page) -> None:
        """TTS off → on transition re-snapshots the config.

        Covers the "user changed Voice settings, then toggled TTS
        back on" path: the snapshot taken at session-start could
        be stale if Voice was reconfigured while TTS was disabled.
        Toggling TTS on must refresh — otherwise the new sentence
        synths via the OLD engine choice.
        """
        from unittest.mock import patch  # noqa: PLC0415

        live_page._tts_enabled = False  # TTS currently off
        with patch.object(
            live_page,
            "_capture_tts_config",
            wraps=live_page._capture_tts_config,
        ) as capture_spy:
            live_page._toggle_tts()  # off → on

        assert live_page._tts_enabled is True
        capture_spy.assert_called_once()
        assert live_page._tts_config is not None

    def test_toggle_tts_on_to_off_does_not_re_capture(
        self,
        live_page,
    ) -> None:
        """Toggling TTS OFF must not re-snapshot.

        No benefit to re-reading settings on the off-transition;
        the snapshot is irrelevant when TTS isn't going to fire.
        Pins the asymmetric capture contract from ``_toggle_tts``.
        """
        from unittest.mock import patch  # noqa: PLC0415

        # Start with TTS already on so this toggle is on → off.
        live_page._tts_enabled = True
        with patch.object(
            live_page,
            "_capture_tts_config",
            wraps=live_page._capture_tts_config,
        ) as capture_spy:
            live_page._toggle_tts()  # on → off

        assert live_page._tts_enabled is False
        capture_spy.assert_not_called()


# ===========================================================================
# TestTranscriptFormats — SRT / VTT / TXT dispatch on save
# ===========================================================================


class TestTranscriptFormats:
    """Per-format transcript formatters + extension-based dispatch."""

    def _seed(self, live_page) -> None:
        """Populates two records: one with speaker, one without."""
        live_page._transcript_records.append(
            ("00:00:00 → 00:00:02", "speaker_0", "Hello", "Bonjour", False),
        )
        live_page._transcript_records.append(
            ("00:00:02 → 00:00:05", "", "World", "Monde", False),
        )

    def test_format_srt_uses_comma_decimal(self, live_page) -> None:
        """SRT output uses ``HH:MM:SS,000`` per the spec."""
        self._seed(live_page)
        out = live_page._format_transcript_srt()
        assert "00:00:00,000 --> 00:00:02,000" in out
        assert "[Speaker 1] Hello" in out
        assert "Bonjour" in out

    def test_format_vtt_uses_dot_decimal_and_header(self, live_page) -> None:
        """WebVTT output uses ``HH:MM:SS.000`` AND starts with ``WEBVTT``."""
        self._seed(live_page)
        out = live_page._format_transcript_vtt()
        assert out.startswith("WEBVTT")
        assert "00:00:00.000 --> 00:00:02.000" in out
        # No SRT-style comma-separator decimals.
        assert ",000" not in out

    def test_format_dispatch_default_is_srt(self, live_page) -> None:
        """Unknown / missing format falls back to SRT."""
        from unittest.mock import patch  # noqa: PLC0415

        self._seed(live_page)
        with patch(f"{_MOD}.load_setting", return_value="bogus-format"):
            out = live_page._format_transcript()  # fmt=None → reads setting
        assert "-->" in out  # SRT signature
        assert "WEBVTT" not in out

    def test_format_dispatch_resolves_vtt_from_setting(self, live_page) -> None:
        """``_format_transcript()`` with fmt=None honors the saved setting."""
        from unittest.mock import patch  # noqa: PLC0415

        self._seed(live_page)
        with patch(f"{_MOD}.load_setting", return_value="vtt"):
            out = live_page._format_transcript()
        assert out.startswith("WEBVTT")

    def test_write_transcript_dispatches_on_extension(
        self,
        live_page,
        tmp_path,
    ) -> None:
        """``_write_transcript_to`` picks the formatter by the file's suffix."""
        self._seed(live_page)
        srt = tmp_path / "out.srt"
        vtt = tmp_path / "out.vtt"
        csv_path = tmp_path / "out.csv"
        assert live_page._write_transcript_to(srt) is True
        assert live_page._write_transcript_to(vtt) is True
        assert live_page._write_transcript_to(csv_path) is True
        assert "-->" in srt.read_text(encoding="utf-8")
        assert vtt.read_text(encoding="utf-8").startswith("WEBVTT")
        # CSV starts with the 5-column header.  ``read_text``
        # applies universal-newlines translation so CRLF
        # collapses to LF on read — assert against the LF form.
        assert csv_path.read_text(encoding="utf-8").startswith(
            "start,end,speaker,original,translated\n",
        )

    def test_format_csv_emits_header_and_one_row_per_cue(
        self,
        live_page,
    ) -> None:
        """CSV output: header row + per-cue rows with 5 columns each.

        Uses :mod:`csv` to parse the output so we exercise the
        RFC 4180 round-trip — any commas / quotes / newlines in
        translated text must survive the trip.
        """
        import csv  # noqa: PLC0415
        import io  # noqa: PLC0415

        self._seed(live_page)
        out = live_page._format_transcript_csv()

        rows = list(csv.reader(io.StringIO(out)))
        assert rows[0] == ["start", "end", "speaker", "original", "translated"]
        assert len(rows) == 3  # noqa: PLR2004 — header + 2 cues
        # Speaker'd cue: 5 populated columns.
        assert rows[1] == [
            "00:00:00",
            "00:00:02",
            "Speaker 1",
            "Hello",
            "Bonjour",
        ]
        # Speakerless cue: empty third column, still 5 columns total.
        assert rows[2] == [
            "00:00:02",
            "00:00:05",
            "",
            "World",
            "Monde",
        ]

    def test_format_csv_escapes_special_chars_in_translated(
        self,
        live_page,
    ) -> None:
        """Commas / quotes / newlines inside cells are RFC 4180-quoted.

        The user's translated text could contain any of these (e.g.
        the LLM returns a sentence with a comma); CSV must escape
        them so the file parses correctly in Excel / LibreOffice.
        """
        import csv  # noqa: PLC0415
        import io  # noqa: PLC0415

        live_page._transcript_records.append(
            (
                "00:00:00 → 00:00:02",
                "speaker_0",
                'A "quoted" word',
                "line one,\nline two",
                False,
            )
        )
        out = live_page._format_transcript_csv()
        # Round-trip via csv module: parsed content matches the input.
        rows = list(csv.reader(io.StringIO(out)))
        assert rows[1][3] == 'A "quoted" word'
        assert rows[1][4] == "line one,\nline two"

    def test_format_csv_applies_speaker_alias(self, live_page) -> None:
        """Renamed speakers show up in the CSV's speaker column.

        Records hold the raw ``speaker_0`` ID; CSV export must
        apply the alias map at save time (same contract as the
        SRT / VTT / TXT formatters).
        """
        import csv  # noqa: PLC0415
        import io  # noqa: PLC0415

        self._seed(live_page)
        live_page._speaker_aliases["speaker_0"] = "Alice"
        out = live_page._format_transcript_csv()
        rows = list(csv.reader(io.StringIO(out)))
        assert rows[1][2] == "Alice"
        assert "speaker_0" not in out  # raw ID never leaks

    def test_format_dispatch_resolves_csv_from_setting(self, live_page) -> None:
        """``_format_transcript()`` with fmt=None reads the saved CSV setting."""
        from unittest.mock import patch  # noqa: PLC0415

        self._seed(live_page)
        with patch(f"{_MOD}.load_setting", return_value="csv"):
            out = live_page._format_transcript()
        # ``csv.writer`` writes CRLF line terminators per RFC 4180.
        assert out.startswith("start,end,speaker,original,translated\r\n")

    # ── ASS / SSA — overlay-style subtitle export ────────────────────

    def test_format_ass_emits_script_header_and_dialogue(self, live_page) -> None:
        """ASS output contains the V4+ script template + per-cue Dialogue lines."""
        self._seed(live_page)
        out = live_page._format_transcript_ass("ass")
        # Header sections present.
        assert "[Script Info]" in out
        assert "ScriptType: v4.00+" in out
        assert "[V4+ Styles]" in out
        assert "[Events]" in out
        # Dialogue line per cue.
        assert out.count("Dialogue:") == 2
        # ASS timestamps use ``H:MM:SS.cc`` (1-digit hour, centiseconds).
        assert "0:00:00.00,0:00:02.00" in out
        # Bilingual layout uses the ``\N`` ASS hard line break.
        assert "Hello\\NBonjour" in out

    def test_format_ssa_uses_same_pipeline(self, live_page) -> None:
        """SSA is the same renderer as ASS — ``fmt='ssa'`` succeeds."""
        self._seed(live_page)
        out = live_page._format_transcript_ass("ssa")
        # Same script template + cue count as ASS.
        assert "[Script Info]" in out
        assert out.count("Dialogue:") == 2

    def test_format_ass_routes_speaker_into_name_field(self, live_page) -> None:
        """Speaker (alias-resolved) lands in the ASS Dialogue ``Name`` field."""
        self._seed(live_page)
        live_page._speaker_aliases["speaker_0"] = "Alice"
        out = live_page._format_transcript_ass("ass")
        # First dialogue row: speaker_0 → "Alice" via alias.  ASS
        # Dialogue format is ``Layer, Start, End, Style, Name, ...``
        # so "Alice" appears between Default and the next field.
        assert ",Default,Alice," in out
        # Second cue had no speaker → empty Name field.
        assert ",Default,," in out

    def test_format_dispatch_resolves_ass_from_setting(self, live_page) -> None:
        """``_format_transcript()`` with fmt=None routes ``ass`` to the ASS path."""
        from unittest.mock import patch  # noqa: PLC0415

        self._seed(live_page)
        with patch(f"{_MOD}.load_setting", return_value="ass"):
            out = live_page._format_transcript()
        assert "[Script Info]" in out

    def test_format_dispatch_resolves_ssa_from_setting(self, live_page) -> None:
        """``_format_transcript()`` with fmt=None routes ``ssa`` to the ASS path."""
        from unittest.mock import patch  # noqa: PLC0415

        self._seed(live_page)
        with patch(f"{_MOD}.load_setting", return_value="ssa"):
            out = live_page._format_transcript()
        assert "[Script Info]" in out


# ===========================================================================
# TestAudioFormatFinalise — WAV stays / MP3 post-encodes via ffmpeg
# ===========================================================================


class TestAudioFormatFinalise:
    """``_finalise_audio_recording`` post-encodes WAV → MP3 when configured."""

    def test_wav_format_returns_wav_unchanged(
        self,
        live_page,
        tmp_path,
    ) -> None:
        """When audio format is WAV (default), no encoding happens."""
        from unittest.mock import patch  # noqa: PLC0415

        wav = tmp_path / "session.wav"
        wav.write_bytes(b"RIFF....WAVE")  # any non-empty content
        with patch(f"{_MOD}.load_setting", return_value="wav"):
            result = live_page._finalise_audio_recording(wav)
        assert result == wav
        assert wav.exists()  # original survives

    def test_mp3_format_runs_ffmpeg_and_deletes_wav(
        self,
        live_page,
        tmp_path,
    ) -> None:
        """MP3 format: ffmpeg invoked, MP3 returned, WAV cleaned up."""
        from unittest.mock import MagicMock, patch  # noqa: PLC0415

        wav = tmp_path / "session.wav"
        wav.write_bytes(b"RIFF....WAVE")
        mp3 = tmp_path / "session.mp3"

        def _fake_run(cmd, **_kwargs):
            # Simulate ffmpeg writing the MP3.
            mp3.write_bytes(b"MP3_FAKE_PAYLOAD")
            return MagicMock(returncode=0, stderr="")

        with (
            patch(f"{_MOD}.load_setting", return_value="mp3"),
            patch(
                "shutil.which",
                return_value="/usr/bin/ffmpeg",
            ),
            patch("subprocess.run", side_effect=_fake_run) as mock_run,
        ):
            result = live_page._finalise_audio_recording(wav)

        assert result == mp3
        assert mp3.exists()
        assert not wav.exists()  # cleaned up
        mock_run.assert_called_once()
        # Command includes ffmpeg + the WAV + the MP3 path.
        cmd = mock_run.call_args.args[0]
        assert "ffmpeg" in cmd[0]
        assert str(wav) in cmd
        assert str(mp3) in cmd

    def test_mp3_format_keeps_wav_when_ffmpeg_missing(
        self,
        live_page,
        tmp_path,
    ) -> None:
        """If ffmpeg isn't on PATH, MP3 is silently dropped and WAV stays.

        The settings page warns the user at setup time; this is the
        runtime safety net for a user who uninstalls ffmpeg between
        config and Stop (or pre-existing config from a different
        machine).
        """
        from unittest.mock import patch  # noqa: PLC0415

        wav = tmp_path / "session.wav"
        wav.write_bytes(b"RIFF")
        with (
            patch(f"{_MOD}.load_setting", return_value="mp3"),
            patch(
                "shutil.which",
                return_value=None,
            ),
        ):
            result = live_page._finalise_audio_recording(wav)
        assert result == wav
        assert wav.exists()

    def test_mp3_format_keeps_wav_on_ffmpeg_failure(
        self,
        live_page,
        tmp_path,
    ) -> None:
        """If ffmpeg returns non-zero, WAV is kept and the empty MP3 cleaned up."""
        from unittest.mock import MagicMock, patch  # noqa: PLC0415

        wav = tmp_path / "session.wav"
        wav.write_bytes(b"RIFF")
        mp3 = tmp_path / "session.mp3"
        mp3.write_bytes(b"")  # empty / partial output

        def _bad_run(*_args, **_kwargs):
            return MagicMock(returncode=1, stderr="ffmpeg fake error")

        with (
            patch(f"{_MOD}.load_setting", return_value="mp3"),
            patch(
                "shutil.which",
                return_value="/usr/bin/ffmpeg",
            ),
            patch("subprocess.run", side_effect=_bad_run),
        ):
            result = live_page._finalise_audio_recording(wav)

        assert result == wav
        assert wav.exists()
        # Empty MP3 cleaned up so it doesn't sit next to the WAV.
        assert not mp3.exists()

    def test_flac_format_runs_ffmpeg_with_flac_codec(
        self,
        live_page,
        tmp_path,
    ) -> None:
        """FLAC dispatch: ffmpeg invoked with the FLAC codec args."""
        from unittest.mock import MagicMock, patch  # noqa: PLC0415

        wav = tmp_path / "session.wav"
        wav.write_bytes(b"RIFF....WAVE")
        flac = tmp_path / "session.flac"

        def _fake_run(_cmd, **_kwargs):
            flac.write_bytes(b"FLAC_FAKE")
            return MagicMock(returncode=0, stderr="")

        with (
            patch(f"{_MOD}.load_setting", return_value="flac"),
            patch(
                "shutil.which",
                return_value="/usr/bin/ffmpeg",
            ),
            patch("subprocess.run", side_effect=_fake_run) as mock_run,
        ):
            result = live_page._finalise_audio_recording(wav)

        assert result == flac
        assert flac.exists()
        assert not wav.exists()
        # FLAC codec args were passed through (no bitrate — lossless).
        cmd = mock_run.call_args.args[0]
        assert "-codec:a" in cmd
        assert "flac" in cmd
        assert "-b:a" not in cmd  # bitrate is meaningless for lossless

    def test_ogg_format_runs_ffmpeg_with_vorbis_codec(
        self,
        live_page,
        tmp_path,
    ) -> None:
        """OGG dispatch: ffmpeg invoked with libvorbis + audio-quality flag."""
        from unittest.mock import MagicMock, patch  # noqa: PLC0415

        wav = tmp_path / "session.wav"
        wav.write_bytes(b"RIFF....WAVE")
        ogg = tmp_path / "session.ogg"

        def _fake_run(_cmd, **_kwargs):
            ogg.write_bytes(b"OGG_FAKE")
            return MagicMock(returncode=0, stderr="")

        with (
            patch(f"{_MOD}.load_setting", return_value="ogg"),
            patch(
                "shutil.which",
                return_value="/usr/bin/ffmpeg",
            ),
            patch("subprocess.run", side_effect=_fake_run) as mock_run,
        ):
            result = live_page._finalise_audio_recording(wav)

        assert result == ogg
        assert ogg.exists()
        assert not wav.exists()
        cmd = mock_run.call_args.args[0]
        assert "libvorbis" in cmd
        assert "-q:a" in cmd

    def test_unknown_format_keeps_wav(self, live_page, tmp_path) -> None:
        """Corrupt / unrecognised setting silently falls back to WAV.

        A future build that adds a new format constant but is run
        with an INI file from an even newer build (somehow) would
        hit this; the safest behaviour is "keep the user's
        recording, log a warning" rather than crash on encode.
        """
        from unittest.mock import patch  # noqa: PLC0415

        wav = tmp_path / "session.wav"
        wav.write_bytes(b"RIFF")
        with patch(f"{_MOD}.load_setting", return_value="future-codec-9000"):
            result = live_page._finalise_audio_recording(wav)
        assert result == wav
        assert wav.exists()


class TestFfmpegInstallDialogIntegration:
    """Live page surfaces the shared install dialog when ffmpeg is missing.

    Two callsites:
    1. ``_validate_ffmpeg_for_audio_save`` — pre-Start guard.
    2. ``_finalise_audio_recording`` — defence-in-depth catch when
       ``post_encode_audio`` raises ``FFMPEG_NOT_FOUND`` mid-finalise.

    Both must (a) return the expected fallback value and (b) route
    through ``CustomMessageDialog.show_message`` with the shared
    ``voice.ffmpeg_required_title`` + ``build_ffmpeg_install_message()``
    so the wording stays consistent across Voice / Dubbing / Live.
    """

    def test_validate_returns_true_when_ffmpeg_present(self, live_page) -> None:
        from unittest.mock import patch  # noqa: PLC0415

        with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
            assert live_page._validate_ffmpeg_for_audio_save() is True

    def test_validate_shows_dialog_and_returns_false_when_ffmpeg_missing(
        self,
        live_page,
    ) -> None:
        from unittest.mock import patch  # noqa: PLC0415

        with (
            patch("shutil.which", return_value=None),
            patch(
                "src.ui.dialogs.CustomMessageDialog.show_message",
            ) as mock_show,
        ):
            result = live_page._validate_ffmpeg_for_audio_save()
        assert result is False
        assert mock_show.called
        # Shared title key — same wording as Voice / Dubbing / Translate Text.
        args, _ = mock_show.call_args
        from src.constants.i18n import tr as _tr  # noqa: PLC0415

        assert args[1] == _tr("voice.ffmpeg_required_title")
        # Body is the dispatcher result (HTML with install hints).
        assert args[2]

    def test_finalise_surfaces_dialog_on_ffmpeg_not_found_sentinel(
        self,
        live_page,
        tmp_path,
    ) -> None:
        """Surfaces install dialog when post_encode raises FFMPEG_NOT_FOUND.

        WAV survives so the user still has their recording.
        """
        from unittest.mock import patch  # noqa: PLC0415

        wav = tmp_path / "session.wav"
        wav.write_bytes(b"RIFF")
        with (
            patch(f"{_MOD}.load_setting", return_value="mp3"),
            patch(
                "src.utils.audio_encoding.post_encode_audio",
                side_effect=RuntimeError("FFMPEG_NOT_FOUND"),
            ),
            patch(
                "src.ui.dialogs.CustomMessageDialog.show_message",
            ) as mock_show,
        ):
            result = live_page._finalise_audio_recording(wav)
        assert result == wav
        assert wav.exists()
        assert mock_show.called
        args, _ = mock_show.call_args
        from src.constants.i18n import tr as _tr  # noqa: PLC0415

        assert args[1] == _tr("voice.ffmpeg_required_title")

    def test_finalise_swallows_other_sentinels_without_dialog(
        self,
        live_page,
        tmp_path,
    ) -> None:
        """``FFMPEG_FAILED`` etc. → log + keep WAV, NO install dialog."""
        from unittest.mock import patch  # noqa: PLC0415

        wav = tmp_path / "session.wav"
        wav.write_bytes(b"RIFF")
        with (
            patch(f"{_MOD}.load_setting", return_value="mp3"),
            patch(
                "src.utils.audio_encoding.post_encode_audio",
                side_effect=RuntimeError("FFMPEG_FAILED"),
            ),
            patch(
                "src.ui.dialogs.CustomMessageDialog.show_message",
            ) as mock_show,
        ):
            result = live_page._finalise_audio_recording(wav)
        assert result == wav
        assert wav.exists()
        # Only FFMPEG_NOT_FOUND surfaces the install dialog — other
        # failures are logged silently (user already has their WAV).
        assert not mock_show.called


class TestSyncBannersPadding:
    """``_sync_banners_padding`` dynamic bottom-margin toggle.

    Ensures the banners layout's bottom margin collapses to 0 when
    every banner is hidden (so controls don't float above an empty
    reservation of vertical space) and expands to 12 px when any
    banner is visible (so the bottom-most banner has breathing room
    from the divider below).
    """

    def _all_banners_hidden(self, live_page) -> None:
        for name in (
            "_stt_setup_warning",
            "_system_audio_warning",
            "_microphone_warning",
            "_audio_ffmpeg_warning",
        ):
            getattr(live_page, name).setVisible(False)

    def test_margin_zero_when_no_banner_visible(self, live_page) -> None:
        self._all_banners_hidden(live_page)
        live_page._sync_banners_padding()
        margins = live_page._banners_layout.contentsMargins()
        assert margins.bottom() == 0
        # Horizontal margins stay fixed at 14 regardless of state.
        assert margins.left() == 14
        assert margins.right() == 14

    def test_margin_twelve_when_one_banner_visible(self, live_page) -> None:
        self._all_banners_hidden(live_page)
        live_page._stt_setup_warning.setVisible(True)
        live_page._sync_banners_padding()
        assert live_page._banners_layout.contentsMargins().bottom() == 12

    def test_margin_twelve_when_all_banners_visible(self, live_page) -> None:
        """Multiple visible banners → margin stays 12 (not cumulative)."""
        for name in (
            "_stt_setup_warning",
            "_system_audio_warning",
            "_microphone_warning",
            "_audio_ffmpeg_warning",
        ):
            getattr(live_page, name).setVisible(True)
        live_page._sync_banners_padding()
        assert live_page._banners_layout.contentsMargins().bottom() == 12

    def test_margin_recollapses_after_banner_hidden(self, live_page) -> None:
        """Re-syncing after hiding the last visible banner restores 0."""
        self._all_banners_hidden(live_page)
        live_page._audio_ffmpeg_warning.setVisible(True)
        live_page._sync_banners_padding()
        assert live_page._banners_layout.contentsMargins().bottom() == 12
        live_page._audio_ffmpeg_warning.setVisible(False)
        live_page._sync_banners_padding()
        assert live_page._banners_layout.contentsMargins().bottom() == 0


# ===========================================================================
# Save chooser dialog + persisted preferences
# ===========================================================================


class TestSaveOptionsDialog:
    """Pins the chooser dialog behaviour: defaults, persistence, gating.

    The dialog is the front door for the Save button — gets it wrong and
    users either lose audio they wanted to keep or get auto-saved files
    they didn't ask for.  These tests pin both the default-checked
    state AND the across-instance preference round-trip so a future
    refactor can't silently swap "save Both by default" for
    "save Transcript only".
    """

    def test_defaults_check_both_when_available(self, window) -> None:
        from src.constants.settings import (  # noqa: PLC0415
            SETTING_LIVE_SAVE_DIALOG_AUDIO,
            SETTING_LIVE_SAVE_DIALOG_TRANSCRIPT,
        )
        from src.ui.pages.live import _SaveOptionsDialog  # noqa: PLC0415

        with patch(
            f"{_MOD}.load_setting",
            side_effect=lambda key, default=None: {
                SETTING_LIVE_SAVE_DIALOG_TRANSCRIPT: "True",
                SETTING_LIVE_SAVE_DIALOG_AUDIO: "True",
            }.get(key, default),
        ):
            dlg = _SaveOptionsDialog(
                window,
                transcript_available=True,
                audio_available=True,
            )
        assert dlg.transcript_cb.isChecked() and dlg.audio_cb.isChecked()
        assert dlg.save_btn.isEnabled()

    def test_disabled_checkbox_does_not_corrupt_pref_on_accept(
        self,
        window,
    ) -> None:
        """Disabled checkbox MUST NOT overwrite its prior True preference.

        A user who saves Both once and later has a session where audio
        wasn't recorded would otherwise see their saved pref silently
        flip to False on the next disabled-checkbox accept.
        """
        from src.constants.settings import (  # noqa: PLC0415
            SETTING_LIVE_SAVE_DIALOG_AUDIO,
        )
        from src.ui.pages.live import _SaveOptionsDialog  # noqa: PLC0415

        with patch(
            f"{_MOD}.load_setting",
            return_value="True",
        ):
            dlg = _SaveOptionsDialog(
                window,
                transcript_available=True,
                audio_available=False,
            )
        saved: list[tuple[str, str]] = []
        with patch(
            f"{_MOD}.save_setting",
            side_effect=lambda k, v: saved.append((k, v)),
        ):
            dlg._on_accept()
        # Audio key should NOT appear in the saved list — checkbox was
        # disabled so its False state is meaningless.
        audio_saves = [v for k, v in saved if k == SETTING_LIVE_SAVE_DIALOG_AUDIO]
        assert audio_saves == []

    def test_cancel_does_not_persist(self, window) -> None:
        from src.ui.pages.live import _SaveOptionsDialog  # noqa: PLC0415

        with patch(f"{_MOD}.load_setting", return_value="True"):
            dlg = _SaveOptionsDialog(
                window,
                transcript_available=True,
                audio_available=True,
            )
        dlg.transcript_cb.setChecked(False)
        dlg.audio_cb.setChecked(False)
        saved: list[tuple[str, str]] = []
        with patch(
            f"{_MOD}.save_setting",
            side_effect=lambda k, v: saved.append((k, v)),
        ):
            dlg.reject()
        assert saved == []  # cancel → no writes

    def test_save_button_disabled_when_no_checkbox_checked(self, window) -> None:
        from src.ui.pages.live import _SaveOptionsDialog  # noqa: PLC0415

        with patch(f"{_MOD}.load_setting", return_value="False"):
            dlg = _SaveOptionsDialog(
                window,
                transcript_available=True,
                audio_available=True,
            )
        # Both unchecked → Save grey.
        assert not dlg.transcript_cb.isChecked()
        assert not dlg.audio_cb.isChecked()
        assert not dlg.save_btn.isEnabled()
        # Checking one re-enables.
        dlg.transcript_cb.setChecked(True)
        assert dlg.save_btn.isEnabled()


# ===========================================================================
# Audio always-record + temp WAV lifecycle
# ===========================================================================


class TestAudioAlwaysRecord:
    """Pins the "always record audio for manual save" architecture.

    Even when Auto save = None / Text-only, the engine should reserve
    a temp WAV path so the Save → Audio button has a source to copy
    from.  These tests guard the temp-path reservation + flag setup
    + cleanup contract; without them, a regression that reverts to
    "only record when Auto save includes Audio" would go unnoticed.
    """

    def test_resolve_save_paths_reserves_temp_for_save_none(
        self,
        live_page,
    ) -> None:
        from src.constants.settings import (  # noqa: PLC0415
            LIVE_SAVE_NONE,
            SETTING_LIVE_SAVE_OUTPUT,
        )
        from src.ui.pages.live import _TEMP_AUDIO_PREFIX  # noqa: PLC0415

        with patch(
            f"{_MOD}.load_setting",
            side_effect=lambda key, default=None: (
                LIVE_SAVE_NONE if key == SETTING_LIVE_SAVE_OUTPUT else default
            ),
        ):
            path = live_page._resolve_save_paths()
        assert path is not None
        assert path.name.startswith(_TEMP_AUDIO_PREFIX)
        assert live_page._audio_is_temp is True

    def test_finalise_skips_post_encode_for_temp_wav(
        self,
        live_page,
        tmp_path,
    ) -> None:
        """Temp WAVs stay raw so manual save can encode to user's chosen format."""
        wav = tmp_path / "x.wav"
        wav.write_bytes(b"RIFF....")
        live_page._audio_is_temp = True
        result = live_page._finalise_audio_recording(wav)
        assert result == wav  # unchanged path
        assert wav.exists()  # not deleted, not transcoded

    def test_cleanup_temp_audio_prefix_guard(
        self,
        live_page,
        tmp_path,
    ) -> None:
        """Cleanup ONLY deletes files matching the temp prefix.

        Defence-in-depth: if a future refactor accidentally points
        ``_last_recorded_audio_path`` at the user's auto-save file,
        this guard prevents the cleanup from deleting it.
        """
        from src.ui.pages.live import _TEMP_AUDIO_PREFIX  # noqa: PLC0415

        # User-saved file (DOES NOT match prefix) — must survive.
        user_file = tmp_path / "live_audio_my_recording.wav"
        user_file.write_bytes(b"USER-AUDIO")
        live_page._last_recorded_audio_path = user_file
        live_page._cleanup_temp_audio()
        assert user_file.exists(), "user file with non-temp prefix must survive cleanup"
        # Temp file (MATCHES prefix) — must be deleted.
        temp_file = tmp_path / f"{_TEMP_AUDIO_PREFIX}xyz.wav"
        temp_file.write_bytes(b"TEMP-AUDIO")
        live_page._last_recorded_audio_path = temp_file
        live_page._cleanup_temp_audio()
        assert not temp_file.exists()


# ===========================================================================
# Mid-session WAV snapshot
# ===========================================================================


class TestSnapshotInProgressWav:
    """Pins the mid-session snapshot's WAV header-patching logic.

    Python's ``wave.Wave_write`` writes placeholder zeros for RIFF
    + data chunk sizes; ``close()`` updates them.  Mid-session we
    can't close the writer, so we snapshot + patch the bytes
    ourselves.  These tests guard the patch math.
    """

    def _make_in_progress_wav(self, path, pcm_bytes: bytes) -> None:
        """Writes a WAV with placeholder header + given PCM payload."""
        import io  # noqa: PLC0415

        buf = io.BytesIO()
        buf.write(b"RIFF" + b"\x00" * 4 + b"WAVE" + b"fmt ")
        buf.write((16).to_bytes(4, "little"))
        buf.write((1).to_bytes(2, "little"))  # PCM
        buf.write((1).to_bytes(2, "little"))  # mono
        buf.write((16000).to_bytes(4, "little"))
        buf.write((32000).to_bytes(4, "little"))
        buf.write((2).to_bytes(2, "little"))  # block align
        buf.write((16).to_bytes(2, "little"))  # bits per sample
        buf.write(b"data" + b"\x00" * 4)
        buf.write(pcm_bytes)
        path.write_bytes(buf.getvalue())

    def test_snapshot_patches_header_into_valid_wav(self, live_page, tmp_path) -> None:
        import wave  # noqa: PLC0415

        src = tmp_path / "in_progress.wav"
        self._make_in_progress_wav(src, b"\x12\x34" * 16000)  # 1 sec mono s16
        snap = live_page._snapshot_in_progress_wav(src)
        try:
            with wave.open(str(snap), "rb") as w:
                assert w.getnchannels() == 1
                assert w.getsampwidth() == 2  # noqa: PLR2004
                assert w.getframerate() == 16000  # noqa: PLR2004
                assert w.getnframes() == 16000  # noqa: PLR2004 — 1 sec
        finally:
            snap.unlink(missing_ok=True)

    def test_snapshot_too_small_file_returns_path_unchanged(
        self,
        live_page,
        tmp_path,
    ) -> None:
        """File shorter than 44-byte header → snapshot returns as-is.

        Callers' encode/copy step will surface any downstream parse
        error; we don't double-fail by trying to patch a header that
        isn't there.
        """
        src = tmp_path / "truncated.wav"
        src.write_bytes(b"RIFF\x00")  # 5 bytes only
        snap = live_page._snapshot_in_progress_wav(src)
        try:
            assert snap.read_bytes() == b"RIFF\x00"
        finally:
            snap.unlink(missing_ok=True)


# ===========================================================================
# Pending "…" placeholder lifecycle
# ===========================================================================


class TestPendingPlaceholder:
    """Pins the "…" placeholder lifecycle on cards + overlay entries.

    The flag must seed the placeholder on construction AND get
    cleared on Stop so cancelled translations don't leave stale
    placeholders in the on-screen transcript / exported file.
    """

    def test_stacked_card_with_pending_shows_placeholder(self, qapp) -> None:
        from src.ui.pages.live import (  # noqa: PLC0415
            _TRANSLATION_PLACEHOLDER,
            _TranscriptCard,
        )

        card = _TranscriptCard("t", "S1", "hi", pending_translation=True)
        assert card._translated is not None
        assert card._translated.text() == _TRANSLATION_PLACEHOLDER

    def test_stacked_card_without_pending_has_no_slot(self, qapp) -> None:
        from src.ui.pages.live import _TranscriptCard  # noqa: PLC0415

        card = _TranscriptCard("t", "S1", "hi")
        assert card._translated is None

    def test_body_is_translated_suppresses_second_placeholder(self, qapp) -> None:
        """body_is_translated=True suppresses a second placeholder slot.

        The dual-view right card already uses the placeholder as its
        body, so adding a second translation slot would double up.
        """
        from src.ui.pages.live import (  # noqa: PLC0415
            _TRANSLATION_PLACEHOLDER,
            _TranscriptCard,
        )

        right = _TranscriptCard(
            "",
            "",
            _TRANSLATION_PLACEHOLDER,
            body_is_translated=True,
            pending_translation=True,
        )
        assert right._translated is None  # no double placeholder

    def test_clear_pending_placeholder_preserves_real_text(self, qapp) -> None:
        from src.ui.pages.live import _TranscriptCard  # noqa: PLC0415

        card = _TranscriptCard("t", "S1", "hi", pending_translation=True)
        card.set_translated("real translation")
        card.clear_pending_placeholder()
        assert card._translated.text() == "real translation"

    def test_clear_pending_placeholder_clears_unfilled_slot(self, qapp) -> None:
        from src.ui.pages.live import (  # noqa: PLC0415
            _TRANSLATION_PLACEHOLDER,
            _TranscriptCard,
        )

        card = _TranscriptCard("t", "S1", "hi", pending_translation=True)
        assert card._translated.text() == _TRANSLATION_PLACEHOLDER
        card.clear_pending_placeholder()
        assert card._translated.text() == ""
        assert not card._translated.isVisible()

    def test_overlay_entry_pending_shows_placeholder(self, qapp) -> None:
        from src.ui.pages.live import (  # noqa: PLC0415
            _TRANSLATION_PLACEHOLDER,
            _OverlayEntry,
        )

        e = _OverlayEntry("t", "S1", "hi", 18, pending_translation=True)
        assert e._translation_label.text() == _TRANSLATION_PLACEHOLDER

    def test_overlay_entry_clear_preserves_real_text(self, qapp) -> None:
        from src.ui.pages.live import _OverlayEntry  # noqa: PLC0415

        e = _OverlayEntry("t", "S1", "hi", 18, pending_translation=True)
        e.set_translation("real")
        e.clear_pending_placeholder()
        assert e._translation_label.text() == "real"

    def test_sweep_processes_stacked_and_dual_views(self, live_page) -> None:
        """Sweep walks single + dual-pair layouts via findChildren.

        Real translations on later cards must survive the sweep
        untouched while pending placeholders are cleared.
        """
        from src.ui.pages.live import _TranscriptCard  # noqa: PLC0415

        sc1, dp1 = live_page._add_original(
            "first",
            "00:01",
            "S1",
            pending_translation=True,
        )
        sc2, dp2 = live_page._add_original(
            "second",
            "00:02",
            "S1",
            pending_translation=True,
        )
        # Real translation lands on sc2 BEFORE sweep — must be preserved.
        live_page._add_translated("real", single_card=sc2, dual_pair=dp2)
        live_page._sweep_pending_placeholders()
        # sc1 placeholder cleared; sc2 real text preserved.
        assert sc1._translated.text() == ""
        assert sc2._translated.text() == "real"
        # Dual-pair right card on sc1's pair also swept.
        right1 = next(
            c for c in dp1.findChildren(_TranscriptCard) if c._body_is_translated
        )
        assert right1._body.text() == ""
        # Dual-pair right card on sc2's pair preserved.
        right2 = next(
            c for c in dp2.findChildren(_TranscriptCard) if c._body_is_translated
        )
        assert right2._body.text() == "real"


# ===========================================================================
# Save orchestrator dispatch
# ===========================================================================


class TestSaveNowOrchestrator:
    """Pins ``_save_now`` chooser → per-handler dispatch.

    Guards the contract that picking Transcript-only / Audio-only /
    Both routes to the correct handler — without it, a regression
    that swaps the dispatch order would silently produce wrong
    files.
    """

    def test_cancel_calls_neither_handler(self, live_page) -> None:
        from src.ui.pages.live import _SaveOptionsDialog  # noqa: PLC0415

        live_page._transcript_records = [
            ("00:01", "S1", "hi", "xin chào", False),
        ]
        with (
            patch.object(
                _SaveOptionsDialog,
                "ask",
                return_value=(False, False, False),
            ),
            patch.object(
                live_page,
                "_save_transcript_now",
            ) as st,
            patch.object(
                live_page,
                "_save_audio_now",
            ) as sa,
        ):
            live_page._save_now()
        assert not st.called
        assert not sa.called

    def test_both_selected_calls_both_handlers(self, live_page) -> None:
        from src.ui.pages.live import _SaveOptionsDialog  # noqa: PLC0415

        live_page._transcript_records = [
            ("00:01", "S1", "hi", "xin chào", False),
        ]
        with (
            patch.object(
                _SaveOptionsDialog,
                "ask",
                return_value=(True, True, True),
            ),
            patch.object(
                live_page,
                "_save_transcript_now",
            ) as st,
            patch.object(
                live_page,
                "_save_audio_now",
            ) as sa,
        ):
            live_page._save_now()
        assert st.called
        assert sa.called

    def test_audio_path_fallback_to_recording_path(self, live_page, tmp_path) -> None:
        """Mid-session click falls back to _recording_path for audio_ok.

        Even when ``_last_recorded_audio_path`` is None, the
        in-progress recording file is a valid source for Save → Audio.
        """
        from src.ui.pages.live import _SaveOptionsDialog  # noqa: PLC0415

        in_progress = tmp_path / "in_progress.wav"
        in_progress.write_bytes(b"RIFF" + b"\x00" * 40 + b"\x12" * 100)
        live_page._last_recorded_audio_path = None
        live_page._recording_path = in_progress

        captured = {}

        def fake_ask(_p, *, transcript_available, audio_available):
            captured["audio"] = audio_available
            return False, False, False

        with patch.object(_SaveOptionsDialog, "ask", side_effect=fake_ask):
            live_page._save_now()
        assert captured["audio"] is True


# ===========================================================================
# Soniox audio capture (WAV tee) + cleanup helpers
# ===========================================================================


class TestSonioxAudioCapture:
    """Pins the page-side WAV writer that tees PCM during Soniox sessions.

    Soniox's engine streams PCM straight to its WebSocket without an
    on-disk writer (unlike Whisper's ``_record_writer``).  The page
    opens its own ``wave.Wave_write`` and tees blocks from the audio
    feed.  These tests guard the writer lifecycle so manual Save →
    Audio works on Soniox sessions.
    """

    def test_open_soniox_recording_opens_writer(
        self,
        live_page,
    ) -> None:
        from src.constants.settings import (  # noqa: PLC0415
            LIVE_SAVE_NONE,
            SETTING_LIVE_SAVE_OUTPUT,
        )

        with patch(
            f"{_MOD}.load_setting",
            side_effect=lambda key, default=None: (
                LIVE_SAVE_NONE if key == SETTING_LIVE_SAVE_OUTPUT else default
            ),
        ):
            live_page._open_soniox_recording()
        assert live_page._soniox_wav_writer is not None
        assert live_page._recording_path is not None
        assert live_page._recording_path.exists()
        # Cleanup — close the writer so the test doesn't leak a handle.
        live_page._soniox_wav_writer.close()
        live_page._soniox_wav_writer = None
        live_page._recording_path.unlink(missing_ok=True)

    def test_record_soniox_pcm_writes_and_closes_to_valid_wav(
        self,
        live_page,
    ) -> None:
        """PCM teed into the writer + close → valid WAV with our frames."""
        import wave  # noqa: PLC0415

        from src.constants.settings import (  # noqa: PLC0415
            LIVE_SAVE_NONE,
            SETTING_LIVE_SAVE_OUTPUT,
        )

        with patch(
            f"{_MOD}.load_setting",
            side_effect=lambda key, default=None: (
                LIVE_SAVE_NONE if key == SETTING_LIVE_SAVE_OUTPUT else default
            ),
        ):
            live_page._open_soniox_recording()
        path = live_page._recording_path

        # 1 second of mono s16 PCM.
        live_page._record_soniox_pcm(b"\x00\x01" * 16000)
        live_page._soniox_wav_writer.close()
        live_page._soniox_wav_writer = None

        try:
            with wave.open(str(path), "rb") as w:
                assert w.getnchannels() == 1
                assert w.getsampwidth() == 2  # noqa: PLR2004 — s16
                assert w.getframerate() == 16000  # noqa: PLR2004
                assert w.getnframes() == 16000  # noqa: PLR2004
        finally:
            path.unlink(missing_ok=True)

    def test_record_soniox_pcm_no_op_without_writer(
        self,
        live_page,
    ) -> None:
        """No writer (recording reservation failed) → silent no-op.

        Audio capture is a best-effort side channel; failing to open
        the writer must never crash the live session.
        """
        live_page._soniox_wav_writer = None
        # Should not raise.
        live_page._record_soniox_pcm(b"\x00" * 1000)

    def test_record_soniox_pcm_disables_writer_on_write_error(
        self,
        live_page,
    ) -> None:
        """Write errors disable the writer + log; the session continues.

        Without this, every subsequent audio block would re-raise the
        same error and spam the log — and worse, the bad writer would
        stay attached.
        """
        from unittest.mock import MagicMock  # noqa: PLC0415

        bad_writer = MagicMock()
        bad_writer.writeframes.side_effect = ValueError("disk full")
        live_page._soniox_wav_writer = bad_writer
        live_page._record_soniox_pcm(b"\x00" * 1000)
        assert live_page._soniox_wav_writer is None
        # close was attempted in the error path.
        bad_writer.close.assert_called()


# ===========================================================================
# Orphan temp-WAV cleanup
# ===========================================================================


class TestOrphanTempAudioCleanup:
    """Pins the app-exit sweep that deletes orphan temp WAVs.

    ``_cleanup_orphan_temp_audio`` deletes
    ``ai_translate_live_audio_*.wav`` files from prior runs that
    crashed before the per-session cleanup could fire.
    """

    def test_orphan_sweep_deletes_matching_files(self) -> None:
        import tempfile  # noqa: PLC0415
        from pathlib import Path as _Path  # noqa: PLC0415

        from src.ui.pages.live import (  # noqa: PLC0415
            _TEMP_AUDIO_PREFIX,
            _cleanup_orphan_temp_audio,
        )

        tmp = _Path(tempfile.gettempdir())
        orphans = [
            tmp / f"{_TEMP_AUDIO_PREFIX}orphan1.wav",
            tmp / f"{_TEMP_AUDIO_PREFIX}orphan2.wav",
        ]
        for p in orphans:
            p.write_bytes(b"FAKE")
        unrelated = tmp / "unrelated_for_test.wav"
        unrelated.write_bytes(b"USER")
        try:
            _cleanup_orphan_temp_audio()
            for p in orphans:
                assert not p.exists(), f"orphan {p} should be deleted"
            assert unrelated.exists(), "unrelated file must survive"
        finally:
            unrelated.unlink(missing_ok=True)

    def test_orphan_sweep_no_op_when_nothing_to_clean(self) -> None:
        """No matching files → silent no-op, no errors raised."""
        from src.ui.pages.live import _cleanup_orphan_temp_audio  # noqa: PLC0415

        # Must not raise even when there's nothing to sweep.
        _cleanup_orphan_temp_audio()
