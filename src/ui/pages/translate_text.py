"""Translate Text page — type or paste text and get instant LLM translation."""

import logging

from PySide6.QtCore import QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QKeySequence, QPalette, QShortcut, QShowEvent
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from src.constants import (
    FLAG_ICON_HEIGHT,
    FLAG_ICON_WIDTH,
    FLAGS_DIR,
    HEIGHT_CONTROL,
    RADIUS_BUTTON,
    SPINNER_FRAMES,
    SPINNER_INTERVAL_MS,
    color,
    format_language_picker_label,
    iter_languages_sorted_for_ui,
    style_delete_button,
    style_input_field,
    style_link_button,
    style_primary_button,
    style_scrollbar,
    style_secondary_button,
    style_setting_combo,
    tr,
)
from src.constants.languages import is_rtl_language
from src.constants.settings import (
    SETTING_LAST_VOICE_GENDER,
    SETTING_TRANSLATE_TEXT_AUTO_SAVE,
    SETTING_TRANSLATE_TEXT_SRC_LANG,
    SETTING_TRANSLATE_TEXT_TGT_LANG,
    SETTING_TRANSLATE_TEXT_TTS_STORAGE,
    SETTING_VOICE_TTS_METHOD,
)
from src.utils.config_manager import check_llm_setup, load_setting

logger = logging.getLogger("translate_text")

# Maximum characters allowed in the source text area
_MAX_CHAR_LIMIT = 5_000

# Maps langdetect ISO codes → app language labels in AVAILABLE_LANGUAGES.
# Ambiguous regional codes resolve to the most common variant.
_LANGDETECT_TO_LABEL: dict[str, str] = {
    "ar": "Arabic",
    "be": "Belarusian",
    "bn": "Bengali",
    "bg": "Bulgarian",
    "zh-cn": "Chinese (Simplified)",
    "zh-tw": "Chinese (Traditional)",
    "hr": "Croatian",
    "cs": "Czech",
    "da": "Danish",
    "nl": "Dutch",
    "en": "English (US)",
    "et": "Estonian",
    "fi": "Finnish",
    "fr": "French",
    "de": "German",
    "el": "Greek",
    "he": "Hebrew",
    "hi": "Hindi",
    "hu": "Hungarian",
    "id": "Indonesian",
    "it": "Italian",
    "ja": "Japanese",
    "km": "Khmer",
    "ko": "Korean",
    "lv": "Latvian",
    "lt": "Lithuanian",
    "ms": "Malay",
    "mn": "Mongolian",
    "ne": "Nepali",
    "fa": "Persian",
    "pl": "Polish",
    "pt": "Portuguese (Brazil)",
    "ro": "Romanian",
    "ru": "Russian",
    "sr": "Serbian",
    "sk": "Slovak",
    "sl": "Slovenian",
    "es": "Spanish",
    "sv": "Swedish",
    "th": "Thai",
    "tr": "Turkish",
    "uk": "Ukrainian",
    "vi": "Vietnamese",
}


def _detect_source_language(text: str) -> str | None:
    """Returns the app language label for `text`, or None if detection fails.

    Uses langdetect with a fixed seed for deterministic results across calls.
    """
    try:
        from langdetect import DetectorFactory, detect  # noqa: PLC0415
        from langdetect.lang_detect_exception import (  # noqa: PLC0415
            LangDetectException,
        )
    except ImportError:
        return None

    DetectorFactory.seed = 0
    try:
        code = detect(text).lower()
    except LangDetectException:
        return None
    return _LANGDETECT_TO_LABEL.get(code)


# Card internal padding (px) for header and footer bars
_CARD_H_PAD = 16
_CARD_V_PAD = 12
_FOOTER_V_PAD = 8


# ── Styling helpers ───────────────────────────────────────────────────────


def _style_card() -> str:
    """Returns QSS for the unified card container."""
    return (
        f"#TranslateCard {{"
        f"  background-color: {color('component_bg')};"
        f"  border: 1px solid {color('border_light')};"
        f"  border-radius: {RADIUS_BUTTON}px;"
        f"}}"
        # QStackedWidget inherits QFrame and may paint an opaque background
        # that overflows the card's rounded corners — force transparent.
        f"#TranslateCard QStackedWidget,"
        f"#TranslateCard QStackedWidget > QWidget {{"
        f"  background: transparent;"
        f"}}"
    )


def _style_text_area() -> str:
    """Returns QSS for borderless text areas inside the card."""
    return (
        f"QPlainTextEdit {{"
        f"  background-color: transparent;"
        f"  color: {color('text_primary')};"
        f"  border: none;"
        f"  padding: 12px 16px;"
        f"  font-size: 15px;"
        f"  selection-background-color: rgba(62, 121, 247, 0.2);"
        f"}}" + style_scrollbar()
    )


def _style_swap_button() -> str:
    """Returns QSS for the swap-languages button."""
    return (
        f"QPushButton {{"
        f"  background: transparent;"
        f"  color: {color('text_secondary')};"
        f"  border: none;"
        f"  font-size: 18px;"
        f"}}"
        f"QPushButton:hover {{"
        f"  color: {color('primary')};"
        f"}}"
        f"QPushButton:disabled {{"
        f"  color: {color('disabled_text')};"
        f"}}"
    )


def _style_char_count() -> str:
    """Returns QSS for the character count / status label."""
    return (
        f"color: {color('text_secondary')}; font-size: 12px;"
        " border: none; background: transparent;"
    )


def _style_error_status() -> str:
    """Returns QSS for the error status label."""
    return (
        f"color: {color('error')}; font-size: 12px;"
        " border: none; background: transparent;"
    )


def _separator_style() -> str:
    """Returns inline QSS for 1px separator widgets."""
    return f"background-color: {color('border_light')};"


def _build_globe_icon() -> QIcon:
    """Renders a globe emoji as a QIcon matching flag icon sizes."""
    from src.ui.dialogs import _create_emoji_icon  # noqa: PLC0415

    return _create_emoji_icon()


# ── Background translation worker ────────────────────────────────────────


class _TextTranslationWorker(QThread):
    """Translates text in a background thread via streaming LLM."""

    translated = Signal(str)
    error = Signal(str)
    chunk = Signal(str)

    # Class-level busy flag consumed by the sidebar spinner in window.py.
    # Flipped True when the page starts a translation, False when it ends
    # (completion, error, or cancel). The flag is not driven by the QThread's
    # own finished signal so the spinner hides immediately on cancel even
    # while the background HTTP stream is still winding down.
    _is_any_worker_running = False

    @classmethod
    def is_busy(cls) -> bool:
        """Returns True while any translate-text worker is in-flight."""
        return cls._is_any_worker_running

    def __init__(  # noqa: PLR0913
        self,
        text: str,
        src_lang: str,
        target_lang: str,
        glossary_entries: list[tuple[int, str, str]] | None = None,
        *,
        provider: str | None = None,
        model: str | None = None,
    ) -> None:
        """Initializes the worker with text and language settings."""
        super().__init__()
        self._text = text
        self._src_lang = src_lang
        self._target_lang = target_lang
        self._glossary = glossary_entries
        self._provider = provider
        self._model = model
        self._cancelled = False

    def cancel(self) -> None:
        """Requests the worker to stop."""
        self._cancelled = True

    def run(self) -> None:
        """Streams translated text chunks from the LLM."""
        from src.core.llm_engine import stream_translate_text  # noqa: PLC0415

        try:
            if not self._text.strip():
                self.translated.emit("")
                return

            full_text = ""
            for text_chunk in stream_translate_text(
                self._text,
                target_lang=self._target_lang,
                source_lang=self._src_lang,
                glossary_entries=self._glossary,
                provider=self._provider,
                model=self._model,
            ):
                if self._cancelled:
                    return
                full_text += text_chunk
                self.chunk.emit(text_chunk)

            if not self._cancelled:
                self.translated.emit(full_text)
        except Exception as exc:
            logger.error("Translation failed: %s", exc)
            self.error.emit(str(exc))


# ── TTS cache helpers ─────────────────────────────────────────────────────


def _tts_cache_dir() -> str:
    """Returns the persistent TTS cache directory, creating it if needed."""
    from src.utils.path_manager import get_tts_cache_dir  # noqa: PLC0415

    return str(get_tts_cache_dir())


def _tts_cache_key(text: str, lang: str, gender: str, method: str) -> str:
    """Returns a stable hash key for the given TTS parameters."""
    import hashlib  # noqa: PLC0415

    payload = f"{text}|{lang}|{gender}|{method}"
    return hashlib.sha256(payload.encode()).hexdigest()[:24]


def _tts_cache_path(text: str, lang: str, gender: str, method: str) -> str:
    """Returns the full path for a cached TTS file."""
    from pathlib import Path  # noqa: PLC0415

    key = _tts_cache_key(text, lang, gender, method)
    return str(Path(_tts_cache_dir()) / f"{key}.mp3")


# ── Background TTS worker ─────────────────────────────────────────────────


class _TTSWorker(QThread):
    """Synthesizes speech in a background thread."""

    finished = Signal(str)  # output file path
    error = Signal(str)

    def __init__(self, text: str, lang: str, output_path: str) -> None:
        """Initializes the TTS worker."""
        super().__init__()
        self._text = text
        self._lang = lang
        self._output_path = output_path
        self._cancelled = False

    def cancel(self) -> None:
        """Requests the worker to stop."""
        self._cancelled = True

    def run(self) -> None:
        """Runs speech synthesis to a cached file."""
        from src.core.speech_engine import synthesize_speech  # noqa: PLC0415

        try:
            tts_method = load_setting(SETTING_VOICE_TTS_METHOD, "Edge TTS")
            gender = load_setting(SETTING_LAST_VOICE_GENDER, "FEMALE")

            synthesize_speech(
                self._text,
                target_lang=self._lang,
                voice_gender=gender,
                output_path=self._output_path,
                tts_method=tts_method,
                is_cancelled=lambda: self._cancelled,
            )
            if not self._cancelled:
                self.finished.emit(self._output_path)
        except Exception as exc:
            logger.error("TTS failed: %s", exc)
            if not self._cancelled:
                self.error.emit(str(exc))


# ── Upward combo box ──────────────────────────────────────────────────────


class _UpwardComboBox(QComboBox):
    """QComboBox that always opens its dropdown above the widget."""

    def showPopup(self) -> None:  # noqa: N802
        """Opens the popup above the combo box, just touching its top edge."""
        super().showPopup()
        popup = self.view().window()
        # Position the popup so its bottom edge aligns with the combo's top
        global_top_left = self.mapToGlobal(self.rect().topLeft())
        popup_height = popup.height()
        popup.move(global_top_left.x(), global_top_left.y() - popup_height)


# ── Main page ─────────────────────────────────────────────────────────────


class TranslateTextPage(QWidget):
    """Page for direct text-to-text translation without files."""

    def __init__(
        self,
        window: QMainWindow,
        parent: QWidget | None = None,
    ) -> None:
        """Initializes the TranslateTextPage."""
        super().__init__(parent)
        self.window_context = window
        self._worker: _TextTranslationWorker | None = None
        # Cancelled workers kept alive until their QThread actually finishes.
        # Without this, Python GC can free the wrapper while the thread is
        # still winding down inside a slow HTTP stream, and Qt then aborts the
        # process with "QThread: Destroyed while thread is still running".
        self._pending_workers: set[_TextTranslationWorker] = set()
        self._separators: list[QWidget] = []
        self._status_is_error = False
        self._target_placeholder_is_error = False
        # Spinner state for the Translate→Cancel button (reuses the sidebar
        # Braille frames via SPINNER_FRAMES).
        self._spinner_timer: QTimer | None = None
        self._spinner_index = 0
        self._last_src_lang = ""
        self._last_tgt_lang = ""
        self._last_source_text = ""
        self._last_entry_id: int | None = None
        self._text_before_edit = ""
        # TTS playback state
        self._tts_worker: _TTSWorker | None = None
        self._tts_player = None
        self._tts_audio_output = None
        self._tts_active_btn: QPushButton | None = None
        # Language of the currently-active TTS request, used so that the
        # save-to-output filename reflects whichever side was synthesized.
        self._tts_active_lang: str = ""
        self._setup_ui()

        # Ensure background threads don't outlive the application. Without
        # this, a QThread blocked in a network call during shutdown can crash
        # the interpreter as the parent widget is torn down.
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._stop_all_workers)

    def _stop_all_workers(self) -> None:
        """Stops translation and TTS workers before app shutdown."""
        if self._worker is not None:
            self._worker.cancel()
            self._worker.wait(2000)
            self._worker = None
        _TextTranslationWorker._is_any_worker_running = False  # noqa: SLF001
        self._stop_tts()

    # ── Helpers ────────────────────────────────────────────────────────

    def _create_separator(self, *, vertical: bool = False) -> QWidget:
        """Creates a themed 1px separator and tracks it for theme updates."""
        sep = QWidget()
        if vertical:
            sep.setFixedWidth(1)
        else:
            sep.setFixedHeight(1)
        sep.setStyleSheet(_separator_style())
        self._separators.append(sep)
        return sep

    # ── UI Build ──────────────────────────────────────────────────────

    def _setup_ui(self) -> None:  # noqa: PLR0915
        """Builds the full page layout as a single unified card."""
        page_container = QWidget()
        content_layout = QVBoxLayout(page_container)
        content_layout.setContentsMargins(
            _CARD_H_PAD,
            _CARD_H_PAD,
            _CARD_H_PAD,
            _CARD_H_PAD,
        )
        content_layout.setSpacing(0)

        # ── Main card ─────────────────────────────────────────────
        self._card = QFrame()
        self._card.setObjectName("TranslateCard")
        self._card.setStyleSheet(_style_card())

        card_layout = QVBoxLayout(self._card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        # ── Header (language bar | history action bar) ─────────────
        self._header_stack = QStackedWidget()
        self._header_stack.addWidget(self._build_language_bar_widget())
        self._header_stack.addWidget(self._build_history_header_widget())
        card_layout.addWidget(self._header_stack)
        card_layout.addWidget(self._create_separator())

        # ── Content area (translate view / history table) ──────────
        self._content_stack = QStackedWidget()
        self._content_stack.addWidget(self._build_text_areas_widget())
        self._build_history_widget()
        self._content_stack.addWidget(self._history_widget)
        card_layout.addWidget(self._content_stack, 1)
        card_layout.addWidget(self._create_separator())

        # ── Footer bar ────────────────────────────────────────────
        card_layout.addLayout(self._build_footer())

        content_layout.addWidget(self._card, 1)

        # Shortcut bindings. Keys are looked up in the central registry so
        # the Settings → Shortcuts tab can rebind them without a restart.
        from src.constants.shortcuts import (  # noqa: PLC0415
            get_shortcut,
            shortcuts_changed,
        )

        self._translate_shortcut = QShortcut(
            QKeySequence(get_shortcut("translate_text.translate")),
            self,
        )
        self._translate_shortcut.activated.connect(self._handle_primary_shortcut)

        self._swap_shortcut = QShortcut(
            QKeySequence(get_shortcut("translate_text.swap_languages")),
            self,
        )
        self._swap_shortcut.activated.connect(self._swap_languages)

        self._escape_shortcut = QShortcut(
            QKeySequence(get_shortcut("translate_text.cancel_edit")),
            self,
        )
        self._escape_shortcut.activated.connect(self._on_escape_pressed)

        self._edit_shortcut = QShortcut(
            QKeySequence(get_shortcut("translate_text.edit")),
            self,
        )
        self._edit_shortcut.activated.connect(self._trigger_edit)

        self._save_edit_shortcut = QShortcut(
            QKeySequence(get_shortcut("translate_text.save_edit")),
            self,
        )
        self._save_edit_shortcut.activated.connect(self._trigger_save_edit)

        self._history_shortcut = QShortcut(
            QKeySequence(get_shortcut("translate_text.toggle_history")),
            self,
        )
        self._history_shortcut.activated.connect(self._toggle_history)

        self._focus_search_shortcut = QShortcut(
            QKeySequence(get_shortcut("common.focus_search")),
            self,
        )
        self._focus_search_shortcut.activated.connect(self._focus_history_search)

        def _sync_shortcuts() -> None:
            self._translate_shortcut.setKey(
                QKeySequence(get_shortcut("translate_text.translate")),
            )
            self._swap_shortcut.setKey(
                QKeySequence(get_shortcut("translate_text.swap_languages")),
            )
            self._escape_shortcut.setKey(
                QKeySequence(get_shortcut("translate_text.cancel_edit")),
            )
            self._edit_shortcut.setKey(
                QKeySequence(get_shortcut("translate_text.edit")),
            )
            self._save_edit_shortcut.setKey(
                QKeySequence(get_shortcut("translate_text.save_edit")),
            )
            self._history_shortcut.setKey(
                QKeySequence(get_shortcut("translate_text.toggle_history")),
            )
            self._focus_search_shortcut.setKey(
                QKeySequence(get_shortcut("common.focus_search")),
            )

        shortcuts_changed.connect(_sync_shortcuts)
        self._sync_shortcuts = _sync_shortcuts

        # Root layout
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(page_container)

        # Apply initial RTL alignment based on saved language selections
        self._on_lang_changed()

    def _build_language_bar_widget(self) -> QWidget:  # noqa: PLR0915
        """Builds the language selector row: src combo, swap, target combo."""
        widget = QWidget()
        lang_bar = QHBoxLayout(widget)
        lang_bar.setContentsMargins(
            _CARD_H_PAD,
            _CARD_V_PAD,
            _CARD_H_PAD,
            _CARD_V_PAD,
        )
        lang_bar.setSpacing(12)  # noqa: PLR2004

        globe_icon = _build_globe_icon()

        # Source language combo (with Auto-detect)
        self.src_combo = QComboBox()
        self.src_combo.addItem(globe_icon, tr("common.lang_auto_detect"))
        for _locale, label, icon, native in iter_languages_sorted_for_ui():
            self.src_combo.addItem(
                QIcon(f"{FLAGS_DIR}/{icon}.png"),
                format_language_picker_label(label, native),
                label,
            )
        self.src_combo.setStyleSheet(style_setting_combo())
        self.src_combo.setFixedHeight(HEIGHT_CONTROL)
        self.src_combo.setIconSize(QSize(FLAG_ICON_WIDTH, FLAG_ICON_HEIGHT))
        self.src_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.src_combo.view().setCursor(Qt.CursorShape.PointingHandCursor)

        # Restore saved source language
        last_src = load_setting(SETTING_TRANSLATE_TEXT_SRC_LANG, "")
        if last_src:
            idx = self.src_combo.findData(last_src)
            if idx >= 0:
                self.src_combo.setCurrentIndex(idx)

        # Swap button (circular)
        self.swap_btn = QPushButton("\u21c4")
        self.swap_btn.setFixedSize(HEIGHT_CONTROL, HEIGHT_CONTROL)
        self.swap_btn.setStyleSheet(_style_swap_button())
        self.swap_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.swap_btn.setEnabled(self.src_combo.currentIndex() > 0)
        self.swap_btn.setAccessibleName(tr("translate_text.swap_tooltip"))
        self.swap_btn.clicked.connect(self._swap_languages)
        self.src_combo.currentIndexChanged.connect(self._on_src_lang_changed)

        # Target language combo (no Auto-detect)
        self.target_combo = QComboBox()
        for _locale, label, icon, native in iter_languages_sorted_for_ui():
            self.target_combo.addItem(
                QIcon(f"{FLAGS_DIR}/{icon}.png"),
                format_language_picker_label(label, native),
                label,
            )
        self.target_combo.setStyleSheet(style_setting_combo())
        self.target_combo.setFixedHeight(HEIGHT_CONTROL)
        self.target_combo.setIconSize(
            QSize(FLAG_ICON_WIDTH, FLAG_ICON_HEIGHT),
        )
        self.target_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.target_combo.view().setCursor(Qt.CursorShape.PointingHandCursor)

        # Restore saved target language
        last_tgt = load_setting(SETTING_TRANSLATE_TEXT_TGT_LANG, "")
        if last_tgt:
            idx = self.target_combo.findData(last_tgt)
            if idx >= 0:
                self.target_combo.setCurrentIndex(idx)

        # Connect _on_lang_changed AFTER restoring saved languages to avoid
        # triggering it before source_text/target_text widgets exist.
        self.src_combo.currentIndexChanged.connect(self._on_lang_changed)
        self.target_combo.currentIndexChanged.connect(self._on_lang_changed)

        # TTS button for source language
        self.tts_source_btn = QPushButton(tr("translate_text.tts_play"))
        self.tts_source_btn.setFixedHeight(HEIGHT_CONTROL)
        self.tts_source_btn.setStyleSheet(style_secondary_button())
        self.tts_source_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.tts_source_btn.setEnabled(False)
        self.tts_source_btn.setAccessibleName(tr("translate_text.a11y_tts_source"))
        self.tts_source_btn.clicked.connect(
            lambda: self._toggle_tts("source"),
        )

        # TTS button for target language
        self.tts_target_btn = QPushButton(tr("translate_text.tts_play"))
        self.tts_target_btn.setFixedHeight(HEIGHT_CONTROL)
        self.tts_target_btn.setStyleSheet(style_secondary_button())
        self.tts_target_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.tts_target_btn.setEnabled(False)
        self.tts_target_btn.setAccessibleName(tr("translate_text.a11y_tts_target"))
        self.tts_target_btn.clicked.connect(
            lambda: self._toggle_tts("target"),
        )

        lang_bar.addWidget(self.tts_source_btn)
        lang_bar.addWidget(self.src_combo, 1)
        lang_bar.addWidget(self.swap_btn)
        lang_bar.addWidget(self.target_combo, 1)
        lang_bar.addWidget(self.tts_target_btn)
        return widget

    def _refresh_model_combo(self) -> None:
        """Re-populates the model combo with currently available models."""
        from src.constants.settings import (  # noqa: PLC0415
            SETTING_LLM_MODEL_TRANSLATE_TEXT,
        )
        from src.utils.config_manager import (  # noqa: PLC0415
            format_model_id,
            get_available_models,
            load_model_for_feature,
        )

        models = get_available_models()

        current = self.model_combo.currentData() or ""
        self.model_combo.blockSignals(True)
        self.model_combo.clear()

        if models:
            for prov, name in models:
                self.model_combo.addItem(name, format_model_id(prov, name))

            # Restore selection — prefer the page's own last pick, fall back
            # to the global default via the helper.
            last = current or load_model_for_feature(
                SETTING_LLM_MODEL_TRANSLATE_TEXT,
            )
            if last:
                for i in range(self.model_combo.count()):
                    if self.model_combo.itemData(i) == last:
                        self.model_combo.setCurrentIndex(i)
                        break
            self.model_combo.setEnabled(True)
        else:
            # No configured providers — show a disabled placeholder so the user
            # can tell that the control exists and sees why it's empty.
            self.model_combo.addItem(tr("translate_text.no_models"), None)
            self.model_combo.setEnabled(False)

        self.model_combo.blockSignals(False)

        # Visible whenever the translate view is active. Previously hidden when
        # only one model existed, which left users wondering where it went.
        on_translate_view = self._header_stack.currentIndex() == 0
        self.model_combo.setVisible(on_translate_view)

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        """Refreshes the model combo when the page becomes visible.

        Also focuses the source text area so the user can start typing
        immediately — skipped when the history view is active so focus
        doesn't jump out of the table.
        """
        super().showEvent(event)
        self._refresh_model_combo()
        if self._header_stack.currentIndex() == 0:
            self.source_text.setFocus()

    def _build_history_header_widget(self) -> QWidget:
        """Builds the history action bar: search + View/Delete buttons."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(
            _CARD_H_PAD,
            _CARD_V_PAD,
            _CARD_H_PAD,
            _CARD_V_PAD,
        )
        layout.setSpacing(10)

        # Search input
        self._history_search = QLineEdit()
        self._history_search.setPlaceholderText(
            tr("text_history.search_placeholder"),
        )
        self._history_search.setStyleSheet(style_input_field())
        self._history_search.setFixedHeight(HEIGHT_CONTROL)
        self._history_search.setMaximumWidth(360)
        layout.addWidget(self._history_search)

        layout.addStretch()

        # Action buttons
        self._history_view_btn = QPushButton(tr("btn.view"))
        self._history_view_btn.setFixedHeight(HEIGHT_CONTROL)
        self._history_view_btn.setStyleSheet(style_link_button())
        self._history_view_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._history_view_btn.setEnabled(False)
        layout.addWidget(self._history_view_btn)

        self._history_reuse_btn = QPushButton(tr("btn.reuse"))
        self._history_reuse_btn.setFixedHeight(HEIGHT_CONTROL)
        self._history_reuse_btn.setStyleSheet(style_primary_button())
        self._history_reuse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._history_reuse_btn.setEnabled(False)
        layout.addWidget(self._history_reuse_btn)

        self._history_delete_btn = QPushButton(tr("btn.delete"))
        self._history_delete_btn.setFixedHeight(HEIGHT_CONTROL)
        self._history_delete_btn.setStyleSheet(style_delete_button())
        self._history_delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._history_delete_btn.setEnabled(False)
        layout.addWidget(self._history_delete_btn)

        return widget

    def _build_text_areas_widget(self) -> QWidget:
        """Builds the side-by-side source and target text areas."""
        container = QWidget()
        text_row = QHBoxLayout(container)
        text_row.setContentsMargins(0, 0, 0, 0)
        text_row.setSpacing(0)

        # Source text area
        self.source_text = QPlainTextEdit()
        self.source_text.setPlaceholderText(
            tr("translate_text.source_placeholder"),
        )
        self.source_text.setStyleSheet(_style_text_area())
        self.source_text.setContextMenuPolicy(
            Qt.ContextMenuPolicy.NoContextMenu,
        )
        self.source_text.setTabChangesFocus(True)
        self.source_text.setAccessibleName(tr("translate_text.source"))
        self.source_text.textChanged.connect(self._on_source_changed)

        # Vertical divider
        v_sep = self._create_separator(vertical=True)

        # Target text area (read-only)
        self.target_text = QPlainTextEdit()
        self.target_text.setReadOnly(True)
        self.target_text.setPlaceholderText(
            tr("translate_text.target_placeholder"),
        )
        self.target_text.setStyleSheet(_style_text_area())
        self.target_text.setContextMenuPolicy(
            Qt.ContextMenuPolicy.NoContextMenu,
        )
        self.target_text.setTabChangesFocus(True)
        self.target_text.setAccessibleName(tr("translate_text.target"))

        text_row.addWidget(self.source_text, 1)
        text_row.addWidget(v_sep)
        text_row.addWidget(self.target_text, 1)
        return container

    def _build_history_widget(self) -> None:
        """Creates the embedded history table and wires header controls."""
        from src.ui.pages.text_translation_history import (  # noqa: PLC0415
            TextTranslationHistoryWidget,
        )

        self._history_widget = TextTranslationHistoryWidget(
            self.window_context,
        )

        # Wire header controls to the history widget
        self._history_search.textChanged.connect(
            self._history_widget.set_search_text,
        )
        self._history_view_btn.clicked.connect(
            self._history_widget.on_view_selected,
        )
        self._history_reuse_btn.clicked.connect(
            self._history_widget.on_reuse_selected,
        )
        self._history_delete_btn.clicked.connect(
            self._history_widget.on_delete_selected,
        )
        self._history_widget.selection_changed.connect(
            self._on_history_selection_changed,
        )
        self._history_widget.reuse_requested.connect(self._on_reuse_entry)

    def _build_footer(self) -> QHBoxLayout:  # noqa: PLR0915
        """Builds the two-column footer aligned with the text areas above."""
        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, 0, 0)
        footer.setSpacing(0)

        _vc = Qt.AlignmentFlag.AlignVCenter

        # ── Left column (under source text): clear, history, char count ──
        left_col = QHBoxLayout()
        left_col.setContentsMargins(
            _CARD_H_PAD,
            _FOOTER_V_PAD,
            _CARD_H_PAD,
            _FOOTER_V_PAD,
        )
        left_col.setSpacing(8)

        self.history_btn = QPushButton(tr("translate_text.btn_history"))
        self.history_btn.setFixedHeight(HEIGHT_CONTROL)
        self.history_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.history_btn.setStyleSheet(style_secondary_button())
        self.history_btn.clicked.connect(self._toggle_history)

        self.char_count = QPushButton(f"0 / {_MAX_CHAR_LIMIT:,}")
        self.char_count.setFixedHeight(HEIGHT_CONTROL)
        self.char_count.setStyleSheet(style_secondary_button())
        self.char_count.setEnabled(False)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet(_style_char_count())
        self.status_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )

        left_col.addWidget(self.history_btn, alignment=_vc)
        left_col.addWidget(self.char_count, alignment=_vc)
        left_col.addWidget(self.status_label, alignment=_vc)
        left_col.addStretch()

        # ── Right column (under target text): edit, model, translate ──
        right_col = QHBoxLayout()
        right_col.setContentsMargins(
            _CARD_H_PAD,
            _FOOTER_V_PAD,
            _CARD_H_PAD,
            _FOOTER_V_PAD,
        )
        right_col.setSpacing(8)

        self.edit_btn = QPushButton(tr("translate_text.btn_edit"))
        self.edit_btn.setFixedHeight(HEIGHT_CONTROL)
        self.edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.edit_btn.setStyleSheet(style_secondary_button())
        self.edit_btn.setEnabled(False)
        self.edit_btn.clicked.connect(self._toggle_edit)

        self.cancel_edit_btn = QPushButton(tr("btn.cancel"))
        self.cancel_edit_btn.setFixedHeight(HEIGHT_CONTROL)
        self.cancel_edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_edit_btn.setStyleSheet(style_secondary_button())
        self.cancel_edit_btn.setVisible(False)
        self.cancel_edit_btn.clicked.connect(self._cancel_edit)

        # Model selection combo (always created, populated in showEvent)
        self.model_combo = _UpwardComboBox()
        self.model_combo.setStyleSheet(style_setting_combo())
        self.model_combo.setFixedHeight(HEIGHT_CONTROL)
        self.model_combo.setMinimumWidth(200)
        self.model_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.model_combo.view().setCursor(Qt.CursorShape.PointingHandCursor)
        self.model_combo.setVisible(False)

        self.translate_btn = QPushButton(tr("translate_text.btn_translate"))
        self.translate_btn.setFixedHeight(HEIGHT_CONTROL)
        self.translate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.translate_btn.setStyleSheet(style_primary_button())
        self.translate_btn.setEnabled(False)
        self.translate_btn.clicked.connect(self._start_translation)

        right_col.addStretch()
        right_col.addWidget(self.cancel_edit_btn, alignment=_vc)
        right_col.addWidget(self.edit_btn, alignment=_vc)
        right_col.addWidget(self.model_combo, alignment=_vc)
        right_col.addWidget(self.translate_btn, alignment=_vc)

        # Assemble: equal-width columns
        footer.addLayout(left_col, 1)
        footer.addLayout(right_col, 1)
        return footer

    # ── Callbacks ─────────────────────────────────────────────────────

    def _on_src_lang_changed(self, index: int) -> None:
        """Disables the swap button when source language is Auto."""
        self.swap_btn.setEnabled(index > 0)

    def _on_lang_changed(self) -> None:
        """Updates text alignment and clears stale output on language change."""
        src_lang = (self.src_combo.currentData() or '')
        tgt_lang = (self.target_combo.currentData() or '')
        self._apply_rtl_alignment(self.source_text, src_lang)
        self._apply_rtl_alignment(self.target_text, tgt_lang)

        # Persist the pair immediately so reopening the app restores the
        # user's last-seen selection, even if they never pressed Translate.
        from src.utils.config_manager import save_setting  # noqa: PLC0415

        # src_lang is empty string when "Auto detect" is selected (index 0).
        save_setting(
            SETTING_TRANSLATE_TEXT_SRC_LANG,
            src_lang if self.src_combo.currentIndex() > 0 else "",
        )
        save_setting(SETTING_TRANSLATE_TEXT_TGT_LANG, tgt_lang)

        # A language change invalidates the existing translation — cancel any
        # in-flight worker, exit edit mode, and clear the output pane so the
        # user isn't left staring at results for the previous language pair.
        if self._worker is not None:
            self._cancel_translation()
        if not self.target_text.isReadOnly():
            self._cancel_edit()
        if self.target_text.toPlainText():
            self.target_text.clear()
            self.status_label.clear()
            self._status_is_error = False
            self._last_source_text = ""
            self._last_entry_id = None
            self.edit_btn.setEnabled(False)
            self._update_tts_btn_states()
        # A stale error placeholder from the previous language pair is no
        # longer meaningful — restore the default hint.
        if self._target_placeholder_is_error:
            self._reset_target_placeholder()

    def _set_target_placeholder(self, text: str, *, is_error: bool) -> None:
        """Sets the target area's placeholder text and palette colour.

        ``is_error=True`` colours the placeholder with the theme's
        error colour so a failed translation is prominent inside the
        output pane itself.  Non-error path mirrors the source pane's
        PlaceholderText colour — read live rather than captured at
        construction because Qt hasn't propagated the parent's
        themed palette to a fresh QPlainTextEdit at ``__init__``
        time (the captured value was rgba(0,0,0,128) — Qt's stock
        default — not the app's rgba(214,215,220,128) inherited
        light-grey, which is why the target placeholder rendered
        dimmer against the dark background).  ``source_text`` is
        never modified, so its current PlaceholderText colour is
        the canonical "what the user expects" reference.
        """
        self.target_text.setPlaceholderText(text)
        palette = self.target_text.palette()
        new_color = (
            QColor(color("error"))
            if is_error
            else self.source_text.palette().color(
                QPalette.ColorRole.PlaceholderText,
            )
        )
        palette.setColor(QPalette.ColorRole.PlaceholderText, new_color)
        self.target_text.setPalette(palette)
        self._target_placeholder_is_error = is_error

    def _reset_target_placeholder(self) -> None:
        """Restores the default ``translate_text.target_placeholder`` message."""
        self._set_target_placeholder(
            tr("translate_text.target_placeholder"),
            is_error=False,
        )

    def _start_spinner(self) -> None:
        """Starts the Braille spinner animation on the Translate/Cancel button."""
        if self._spinner_timer is None:
            self._spinner_timer = QTimer(self)
            self._spinner_timer.setInterval(SPINNER_INTERVAL_MS)
            self._spinner_timer.timeout.connect(self._tick_spinner)
        self._spinner_index = 0
        self._tick_spinner()
        self._spinner_timer.start()

    def _stop_spinner(self) -> None:
        """Stops the spinner animation; the caller restores the button label."""
        if self._spinner_timer is not None and self._spinner_timer.isActive():
            self._spinner_timer.stop()

    def _tick_spinner(self) -> None:
        """Advances the spinner one frame and re-renders the button label."""
        frame = SPINNER_FRAMES[self._spinner_index % len(SPINNER_FRAMES)]
        self.translate_btn.setText(f"{frame}  {tr('btn.cancel')}")
        self._spinner_index += 1

    @staticmethod
    def _apply_rtl_alignment(
        text_edit: QPlainTextEdit,
        lang: str,
    ) -> None:
        """Sets text direction based on whether the language is RTL."""
        from PySide6.QtGui import QTextOption  # noqa: PLC0415

        opt = QTextOption()
        if is_rtl_language(lang):
            opt.setTextDirection(Qt.LayoutDirection.RightToLeft)
            opt.setAlignment(Qt.AlignmentFlag.AlignRight)
        else:
            opt.setTextDirection(Qt.LayoutDirection.LeftToRight)
            opt.setAlignment(Qt.AlignmentFlag.AlignLeft)
        text_edit.document().setDefaultTextOption(opt)

    def _on_source_changed(self) -> None:
        """Updates character count, auto-truncating if over the limit."""
        text = self.source_text.toPlainText()
        if len(text) > _MAX_CHAR_LIMIT:
            # Truncate and restore cursor position
            cursor = self.source_text.textCursor()
            pos = min(cursor.position(), _MAX_CHAR_LIMIT)
            self.source_text.blockSignals(True)
            self.source_text.setPlainText(text[:_MAX_CHAR_LIMIT])
            cursor.setPosition(pos)
            self.source_text.setTextCursor(cursor)
            self.source_text.blockSignals(False)

        count = len(self.source_text.toPlainText())
        self.char_count.setText(f"{count:,} / {_MAX_CHAR_LIMIT:,}")
        self.translate_btn.setEnabled(count > 0)
        self._update_tts_btn_states()

    def _on_escape_pressed(self) -> None:
        """Handles Escape: cancels edit mode, else cancels in-flight translation."""
        if not self.target_text.isReadOnly():
            self._cancel_edit()
        elif self._worker is not None:
            self._cancel_translation()

    def _swap_languages(self) -> None:
        """Swaps source and target language selections and text content."""
        # Nothing sensible to swap when the source is Auto-detect.
        if self.src_combo.currentIndex() == 0:
            return
        src_text = (self.src_combo.currentData() or '')
        tgt_text = (self.target_combo.currentData() or '')

        # Capture text content before changing combos — _on_lang_changed
        # clears target_text on language change, which would otherwise eat the
        # value we're about to move into source_text.
        old_source = self.source_text.toPlainText()
        old_target = self.target_text.toPlainText()

        new_src_idx = self.src_combo.findData(tgt_text)
        if new_src_idx >= 0:
            self.src_combo.setCurrentIndex(new_src_idx)

        new_tgt_idx = self.target_combo.findData(src_text)
        if new_tgt_idx >= 0:
            self.target_combo.setCurrentIndex(new_tgt_idx)

        if old_target:
            self.source_text.setPlainText(old_target)
            self.target_text.setPlainText(old_source)
        self._update_tts_btn_states()

    def _handle_primary_shortcut(self) -> None:
        """Dispatches Ctrl+Enter to the focused-context action.

        When the history table has focus with a selected row, re-use the
        selected entry (loads it back into the editor); otherwise fall
        through to Translate / Cancel on the main editor.
        """
        table = getattr(self._history_widget, "table", None)
        if (
            table is not None
            and table.hasFocus()
            and table.selectionModel() is not None
            and table.selectionModel().hasSelection()
        ):
            self._history_widget.on_reuse_selected()
            return
        self._start_translation()

    def _start_translation(self) -> None:
        """Initiates translation, or cancels the in-flight worker if running."""
        if self._worker is not None:
            # Already translating — treat the click/shortcut as Cancel.
            self._cancel_translation()
            return

        # Check LLM setup before anything else
        from src.ui.dialogs import require_setup  # noqa: PLC0415

        if not require_setup(
            self.window_context,
            check_llm_setup,
            "dialog.llm_required_title",
            "dialog.llm_required_msg",
            4,
        ):
            return

        text = self.source_text.toPlainText().strip()
        if not text:
            return

        # Get language selections (already persisted on every combo change).
        src_lang = ""
        if self.src_combo.currentIndex() > 0:
            src_lang = (self.src_combo.currentData() or '')
        target_lang = (self.target_combo.currentData() or '')

        # Fetch glossary
        from src.core.database import (  # noqa: PLC0415
            get_active_glossary_sets,
            get_glossary_entries,
        )

        glossary: list[tuple[int, str, str]] = []
        for set_id, _ in get_active_glossary_sets():
            glossary.extend(get_glossary_entries(set_id))

        # Remember context for auto-save on completion
        self._last_src_lang = src_lang
        self._last_tgt_lang = target_lang
        self._last_source_text = text
        self._last_entry_id = None

        # Exit edit mode and switch Translate → Cancel so the user can abort.
        # The button's Braille spinner carries the "working" signal; the
        # target keeps its default placeholder so there's no redundant
        # "Translating…" text alongside the spinner.
        self._set_editing(False)
        self.edit_btn.setEnabled(False)
        self.translate_btn.setEnabled(True)
        self.target_text.clear()
        self._reset_target_placeholder()
        self.status_label.setText("")
        self._status_is_error = False
        self._start_spinner()

        # Get selected LLM model
        from src.constants.settings import (  # noqa: PLC0415
            SETTING_LLM_MODEL_TRANSLATE_TEXT,
        )
        from src.utils.config_manager import (  # noqa: PLC0415
            parse_model_id,
            save_model_for_feature,
        )

        llm_provider, llm_model = None, None
        model_id = self.model_combo.currentData() or ""
        if model_id:
            save_model_for_feature(SETTING_LLM_MODEL_TRANSLATE_TEXT, model_id)
            llm_provider, llm_model = parse_model_id(model_id)

        self._worker = _TextTranslationWorker(
            text,
            src_lang,
            target_lang,
            glossary_entries=glossary or None,
            provider=llm_provider,
            model=llm_model,
        )
        self._worker.chunk.connect(self._on_chunk)
        self._worker.translated.connect(self._on_translated)
        self._worker.error.connect(self._on_translation_error)
        _TextTranslationWorker._is_any_worker_running = True  # noqa: SLF001
        self._worker.start()

    def _on_chunk(self, text_chunk: str) -> None:
        """Appends a streaming text chunk to the target area."""
        cursor = self.target_text.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(text_chunk)

    def _on_translated(self, text: str) -> None:
        """Handles completed translation and auto-saves to history."""
        _TextTranslationWorker._is_any_worker_running = False  # noqa: SLF001
        self._stop_spinner()
        has_text = bool(self.source_text.toPlainText().strip())
        self.translate_btn.setEnabled(has_text)
        self.translate_btn.setText(tr("translate_text.btn_translate"))
        self.edit_btn.setEnabled(bool(text))
        self.status_label.setText("")
        self._status_is_error = False
        self._cleanup_worker()
        self._update_tts_btn_states()

        # Auto-save to history (default: enabled)
        if text and load_setting(SETTING_TRANSLATE_TEXT_AUTO_SAVE, "true") != "false":
            self._save_to_history(text)

    def _on_translation_error(self, error_msg: str) -> None:
        """Handles translation failure."""
        from src.constants.errors import display_error_message  # noqa: PLC0415

        _TextTranslationWorker._is_any_worker_running = False  # noqa: SLF001
        self._stop_spinner()
        has_text = bool(self.source_text.toPlainText().strip())
        self.translate_btn.setEnabled(has_text)
        self.translate_btn.setText(tr("translate_text.btn_translate"))
        # Discard any partial stream — the user should not mistake a
        # truncated response for a complete translation.  Surface the
        # error in the footer status label (same place TTS errors land)
        # so both error surfaces are consistent and the user only has
        # one spot to scan for failures.  The target pane is left clear
        # so a retry doesn't have to overwrite stale red placeholder
        # text.
        self.target_text.clear()
        self.edit_btn.setEnabled(False)
        friendly = display_error_message(error_msg)
        self.status_label.setText(tr("error.prefix", message=friendly))
        self.status_label.setStyleSheet(_style_error_status())
        self._status_is_error = True
        self._cleanup_worker()
        self._update_tts_btn_states()

    def _save_to_history(self, translated: str) -> None:
        """Persists the completed translation to the history table."""
        # Defensive: don't create an empty row if somehow we got here without
        # source text (e.g. _start_translation was re-entered mid-callback).
        if not self._last_source_text or not translated:
            return
        from src.core.database import add_text_translation_entry  # noqa: PLC0415

        self._last_entry_id = add_text_translation_entry(
            source_text=self._last_source_text,
            translated_text=translated,
            src_lang=self._last_src_lang,
            target_lang=self._last_tgt_lang,
            char_count=len(self._last_source_text),
        )

    def _toggle_history(self) -> None:
        """Toggles between translate view and history table view."""
        if self._header_stack.currentIndex() == 1:
            self._close_history()
        else:
            self._show_history()

    def _show_history(self) -> None:
        """Switches to the history view. No-op if already showing."""
        if self._header_stack.currentIndex() == 1:
            return
        self._header_stack.setCurrentIndex(1)
        self._content_stack.setCurrentIndex(1)
        self._history_widget.refresh_history(force=True)
        self.history_btn.setText(tr("translate_text.btn_back"))
        self._set_translate_footer_visible(False)
        # Hand focus to the table so Enter (view) / Ctrl+Enter (re-use)
        # work without an extra click.
        self._history_widget.table.setFocus()

    def _focus_history_search(self) -> None:
        """Focuses the history search input, switching to history view first."""
        if self._header_stack.currentIndex() != 1:
            self._show_history()
        self._history_search.setFocus()

    def _close_history(self) -> None:
        """Switches back to the translate view. No-op if not in history."""
        if self._header_stack.currentIndex() != 1:
            return
        self._header_stack.setCurrentIndex(0)
        self._content_stack.setCurrentIndex(0)
        self.history_btn.setText(tr("translate_text.btn_history"))
        self._set_translate_footer_visible(True)
        # Returning from history → put the user straight back into typing.
        self.source_text.setFocus()

    def _on_history_selection_changed(self, has_selection: bool) -> None:
        """Updates history action button states based on table selection."""
        self._history_view_btn.setEnabled(has_selection)
        self._history_reuse_btn.setEnabled(has_selection)
        self._history_delete_btn.setEnabled(has_selection)

    def _on_reuse_entry(  # noqa: PLR0913
        self,
        entry_id: int,
        source: str,
        translated: str,
        src_lang: str,
        target_lang: str,
    ) -> None:
        """Loads a history entry back into the translate view."""
        # Set language combos
        if src_lang:
            idx = self.src_combo.findData(src_lang)
            if idx >= 0:
                self.src_combo.setCurrentIndex(idx)
        else:
            self.src_combo.setCurrentIndex(0)  # Auto

        idx = self.target_combo.findData(target_lang)
        if idx >= 0:
            self.target_combo.setCurrentIndex(idx)

        # Populate text areas
        self.source_text.setPlainText(source)
        self.target_text.setPlainText(translated)

        # Track the reused entry so that Save-after-Edit updates THIS row
        # rather than silently dropping the edits.
        self._last_entry_id = entry_id
        self._last_src_lang = src_lang
        self._last_tgt_lang = target_lang
        self._last_source_text = source

        # Enable edit button if there's translated text
        self.edit_btn.setEnabled(bool(translated))

        # Clear any stale error / status from a prior attempt
        self.status_label.setText("")
        self._status_is_error = False
        self.status_label.setStyleSheet(_style_char_count())
        self._update_tts_btn_states()

        # Switch back to translate view
        self._header_stack.setCurrentIndex(0)
        self._content_stack.setCurrentIndex(0)
        self.history_btn.setText(tr("translate_text.btn_history"))
        self._set_translate_footer_visible(True)

    def _trigger_edit(self) -> None:
        """Ctrl+E handler: enters edit mode only.

        Gated by ``edit_btn.isEnabled()`` (no translation yet) and by the
        read-only state (already editing → no-op; Ctrl+S handles save).
        """
        if self.edit_btn.isEnabled() and self.target_text.isReadOnly():
            self._toggle_edit()

    def _trigger_save_edit(self) -> None:
        """Ctrl+S handler: saves and exits edit mode only if currently editing."""
        if not self.target_text.isReadOnly():
            self._toggle_edit()

    def _toggle_edit(self) -> None:
        """Toggles editing of the translated text area."""
        entering_edit = self.target_text.isReadOnly()
        if entering_edit:
            # Stop any in-flight TTS *before* the user starts editing.
            # Otherwise a queued chunk of the pre-edit text would
            # continue playing after the user typed over it — the
            # audio and the on-screen text would silently diverge.
            self._stop_tts()
        if not entering_edit and self._last_entry_id is not None:
            # Exiting edit mode — persist edited text to history
            from src.core.database import update_text_translation_entry  # noqa: PLC0415

            update_text_translation_entry(
                self._last_entry_id,
                self.target_text.toPlainText(),
            )
        self._set_editing(entering_edit)
        self._update_tts_btn_states()

    def _cancel_edit(self) -> None:
        """Cancels editing and restores the original translated text."""
        # Symmetry with ``_toggle_edit``: ensure no stale TTS is
        # playing when the user dismisses the edit.  ``_toggle_edit``
        # already stopped TTS on entry, but if a Listen click between
        # entering edit mode and pressing Cancel restarted playback,
        # we want to silence that too.
        self._stop_tts()
        self.target_text.setPlainText(self._text_before_edit)
        self._set_editing(False)
        self._update_tts_btn_states()

    def _set_editing(self, editing: bool) -> None:
        """Sets the target text area to editable or read-only."""
        self.target_text.setReadOnly(not editing)
        self.cancel_edit_btn.setVisible(editing)
        if editing:
            self._text_before_edit = self.target_text.toPlainText()
            self.edit_btn.setText(tr("translate_text.btn_save"))
            self.edit_btn.setStyleSheet(style_primary_button())
            self.translate_btn.setVisible(False)
            self.target_text.setFocus()
        else:
            self.edit_btn.setText(tr("translate_text.btn_edit"))
            self.edit_btn.setStyleSheet(style_secondary_button())
            self.translate_btn.setVisible(True)

    def _set_translate_footer_visible(self, visible: bool) -> None:
        """Shows/hides translate-specific footer widgets."""
        self.char_count.setVisible(visible)
        self.edit_btn.setVisible(visible)
        self.status_label.setVisible(visible)
        # Model combo decides its own visibility from the current view and
        # number of available models.
        self._refresh_model_combo()
        self.translate_btn.setVisible(visible)

    def _cleanup_worker(self) -> None:
        """Waits for the worker thread to finish and drops reference."""
        if self._worker is not None:
            self._worker.wait()
            self._worker = None

    def _cancel_translation(self) -> None:
        """Cancels the in-flight translation worker and restores UI state."""
        if self._worker is None:
            return
        _TextTranslationWorker._is_any_worker_running = False  # noqa: SLF001
        self._stop_spinner()
        worker = self._worker
        worker.cancel()
        # Detach signals and self-delete on finish rather than wait() — the
        # worker may still be blocked inside a slow HTTP stream, and we
        # don't want the UI to freeze while it winds down.
        import contextlib  # noqa: PLC0415

        for signal in (worker.chunk, worker.translated, worker.error):
            with contextlib.suppress(TypeError, RuntimeError):
                signal.disconnect()
        # Keep a Python reference until the thread finishes. A bare
        # ``finished → deleteLater`` connection is not enough on PySide6: the
        # Python wrapper can be GC'd while the C++ QThread is still running,
        # which aborts the process with "QThread: Destroyed while thread is
        # still running". The _pending_workers set anchors the wrapper; we
        # remove it once ``finished`` fires.
        self._pending_workers.add(worker)
        worker.finished.connect(
            lambda w=worker: self._pending_workers.discard(w),
        )
        worker.finished.connect(worker.deleteLater)
        self._worker = None

        has_text = bool(self.source_text.toPlainText().strip())
        self.translate_btn.setEnabled(has_text)
        self.translate_btn.setText(tr("translate_text.btn_translate"))
        self.edit_btn.setEnabled(bool(self.target_text.toPlainText().strip()))
        self.status_label.setText("")
        self._status_is_error = False
        # Clear the "Translating…" placeholder left over from _start_translation.
        if not self._target_placeholder_is_error:
            self._reset_target_placeholder()
        self._update_tts_btn_states()

    # ── TTS ───────────────────────────────────────────────────────────

    def _update_tts_btn_states(self) -> None:
        """Enables/disables TTS buttons based on text content."""
        has_source = bool(self.source_text.toPlainText().strip())
        has_target = bool(self.target_text.toPlainText().strip())
        if self._tts_active_btn is not self.tts_source_btn:
            self.tts_source_btn.setEnabled(has_source)
        if self._tts_active_btn is not self.tts_target_btn:
            self.tts_target_btn.setEnabled(has_target)

    def _toggle_tts(self, side: str) -> None:
        """Starts or stops TTS playback for the given side."""
        btn = self.tts_source_btn if side == "source" else self.tts_target_btn

        # If this button is already playing, stop it
        if self._tts_active_btn is btn:
            self._stop_tts()
            return

        # Stop any existing playback first
        self._stop_tts()

        # Determine text and language
        if side == "source":
            text = self.source_text.toPlainText().strip()
            if self.src_combo.currentIndex() > 0:
                lang = (self.src_combo.currentData() or '')
            else:
                # Source is "Auto" — detect from the text. On detection failure
                # fall back to English (a safe default with broad TTS coverage)
                # rather than the target language, which would read source text
                # aloud with the wrong accent.
                lang = _detect_source_language(text) or "English (US)"
        else:
            text = self.target_text.toPlainText().strip()
            lang = (self.target_combo.currentData() or '')

        if not text:
            from src.ui.dialogs import CustomMessageDialog  # noqa: PLC0415

            CustomMessageDialog.show_message(
                self.window_context,
                tr("translate_text.tts_play"),
                tr("translate_text.tts_no_text"),
            )
            return

        # Edge TTS is the default (free, no config needed); other backends
        # validate their own credentials during synthesize_speech().
        from src.constants.settings import VOICE_TTS_EDGE  # noqa: PLC0415

        tts_method = load_setting(SETTING_VOICE_TTS_METHOD, VOICE_TTS_EDGE)
        gender = load_setting(SETTING_LAST_VOICE_GENDER, "FEMALE")
        cached = _tts_cache_path(text, lang, gender, tts_method)

        from pathlib import Path  # noqa: PLC0415

        cache_hit = Path(cached).is_file()
        if not cache_hit:
            # Pre-flight (only when we'd actually invoke synthesis;
            # cache hits skip these because past success proves the
            # prerequisites were met before).
            #
            # 1. Piper voice file present on disk.  Without this, the
            #    worker raises PIPER_VOICE_NOT_INSTALLED and the user
            #    sees a cryptic red status line; the dialog has an
            #    "Open Settings" button to remediate.
            # 2. FFmpeg present — required defensively across all TTS
            #    engines.  Even backends that return MP3 natively
            #    (Edge / ElevenLabs / Google Cloud) currently rely on
            #    ffmpeg in some paths; matches Voice page's
            #    unconditional ffmpeg pre-check for consistency.
            #    Reuses the existing ``voice.ffmpeg_required_*``
            #    strings to avoid duplicating the wording across pages.
            from src.core.speech_engine import check_ffmpeg_available  # noqa: PLC0415
            from src.ui.dialogs import (  # noqa: PLC0415
                CustomMessageDialog,
                preflight_piper_voice,
            )

            if not preflight_piper_voice(self.window_context, lang, gender):
                return

            if not check_ffmpeg_available():
                from src.utils.install_hints import (  # noqa: PLC0415
                    build_ffmpeg_install_message,
                )

                CustomMessageDialog.show_message(
                    self.window_context,
                    tr("voice.ffmpeg_required_title"),
                    build_ffmpeg_install_message(),
                )
                return

        # Clear any stale status (e.g., previous translation or TTS error)
        self.status_label.setText("")
        self._status_is_error = False

        # Set active state
        self._tts_active_btn = btn
        self._tts_active_lang = lang
        btn.setText(tr("translate_text.tts_stop"))

        if cache_hit:
            self._play_tts_file(cached)
            return

        # Start TTS worker to generate and cache
        self._tts_worker = _TTSWorker(text, lang, cached)
        self._tts_worker.finished.connect(self._on_tts_synthesized)
        self._tts_worker.error.connect(self._on_tts_error)
        self._tts_worker.start()

    def _on_tts_synthesized(self, file_path: str) -> None:
        """Handles a freshly-synthesized TTS file: save-to-output then play."""
        self._save_tts_to_output(file_path)
        self._play_tts_file(file_path)

    def _save_tts_to_output(self, file_path: str) -> None:
        """Copies the TTS cache file to the user-configured output directory."""
        out_dir = load_setting(SETTING_TRANSLATE_TEXT_TTS_STORAGE, "")
        if not out_dir:
            return

        import shutil  # noqa: PLC0415
        from pathlib import Path  # noqa: PLC0415

        Path(out_dir).mkdir(parents=True, exist_ok=True)

        # Build a readable filename from the synthesized language and timestamp.
        # Use _tts_active_lang (the language actually spoken) rather than the
        # target combo, so that playing the source side saves under the source
        # language, not the target one.
        import time  # noqa: PLC0415

        raw_lang = self._tts_active_lang or (self.target_combo.currentData() or '')
        lang = raw_lang.replace(" ", "_")
        ts = time.strftime("%Y%m%d_%H%M%S")
        dest = Path(out_dir) / f"tts_{lang}_{ts}.mp3"
        # Avoid overwriting
        counter = 1
        while dest.exists():
            dest = Path(out_dir) / f"tts_{lang}_{ts}_{counter}.mp3"
            counter += 1

        try:
            shutil.copy2(file_path, dest)
            logger.info("TTS audio saved to %s", dest)
        except OSError:
            logger.exception("Failed to save TTS audio to %s", dest)

    def _play_tts_file(self, file_path: str) -> None:
        """Plays an audio file via QMediaPlayer."""
        from PySide6.QtCore import QUrl  # noqa: PLC0415
        from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer  # noqa: PLC0415

        if self._tts_player is None:
            self._tts_player = QMediaPlayer(self)
            self._tts_audio_output = QAudioOutput(self)
            self._tts_player.setAudioOutput(self._tts_audio_output)
            self._tts_player.mediaStatusChanged.connect(
                self._on_tts_playback_status,
            )

        self._tts_player.setSource(QUrl.fromLocalFile(file_path))
        self._tts_player.play()

    def _on_tts_error(self, msg: str) -> None:
        """Shows the TTS error in the footer status label and resets buttons."""
        from src.constants.errors import display_error_message  # noqa: PLC0415

        friendly = display_error_message(msg)
        self.status_label.setText(tr("error.prefix", message=friendly))
        self.status_label.setStyleSheet(_style_error_status())
        self._status_is_error = True
        self._reset_tts_btn()

    def _on_tts_playback_status(self, status: object) -> None:
        """Resets (or error-reports) when playback ends or fails."""
        from PySide6.QtMultimedia import QMediaPlayer  # noqa: PLC0415

        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._reset_tts_btn()
        elif status == QMediaPlayer.MediaStatus.InvalidMedia:
            # Surface the error to the user rather than leaving the button
            # stuck on "Stop" with no audio playing.
            self._on_tts_error(tr("translate_text.tts_playback_failed"))

    def _stop_tts(self) -> None:
        """Stops any active TTS worker and playback."""
        if self._tts_worker is not None:
            self._tts_worker.cancel()
            # Bounded wait — a hung TTS backend must not block interactive
            # stop requests or app shutdown via aboutToQuit.
            self._tts_worker.wait(2000)
            self._tts_worker = None

        if self._tts_player is not None:
            self._tts_player.stop()

        self._reset_tts_btn()

    def _reset_tts_btn(self) -> None:
        """Restores both TTS buttons to their default state."""
        self._tts_active_btn = None
        self._tts_active_lang = ""
        for btn in (self.tts_source_btn, self.tts_target_btn):
            btn.setText(tr("translate_text.tts_play"))
        self._update_tts_btn_states()

    # ── Theme/Language ────────────────────────────────────────────────

    def apply_theme(self) -> None:
        """Re-applies all theme-dependent styles."""
        self._card.setStyleSheet(_style_card())
        # Language bar
        self.src_combo.setStyleSheet(style_setting_combo())
        self.target_combo.setStyleSheet(style_setting_combo())
        self.swap_btn.setStyleSheet(_style_swap_button())
        # History header
        self._history_search.setStyleSheet(style_input_field())
        self._history_view_btn.setStyleSheet(style_link_button())
        self._history_reuse_btn.setStyleSheet(style_primary_button())
        self._history_delete_btn.setStyleSheet(style_delete_button())
        # Text areas
        self.source_text.setStyleSheet(_style_text_area())
        self.target_text.setStyleSheet(_style_text_area())
        # Footer
        self.translate_btn.setStyleSheet(style_primary_button())
        if self.target_text.isReadOnly():
            self.edit_btn.setStyleSheet(style_secondary_button())
        else:
            self.edit_btn.setStyleSheet(style_primary_button())
        self.cancel_edit_btn.setStyleSheet(style_secondary_button())
        self.history_btn.setStyleSheet(style_secondary_button())
        self.char_count.setStyleSheet(style_secondary_button())
        self.tts_source_btn.setStyleSheet(style_secondary_button())
        self.tts_target_btn.setStyleSheet(style_secondary_button())
        if self._status_is_error:
            self.status_label.setStyleSheet(_style_error_status())
        else:
            self.status_label.setStyleSheet(_style_char_count())
        # Re-apply the target placeholder palette so theme swaps update the
        # error colour too.
        palette = self.target_text.palette()
        role = QPalette.ColorRole.PlaceholderText
        palette_colour = (
            color("error")
            if self._target_placeholder_is_error
            else color("text_secondary")
        )
        palette.setColor(role, QColor(palette_colour))
        self.target_text.setPalette(palette)
        for sep in self._separators:
            sep.setStyleSheet(_separator_style())
        self._history_widget.apply_theme()

    def apply_language(self) -> None:
        """Re-applies all translatable text."""
        self.source_text.setPlaceholderText(
            tr("translate_text.source_placeholder"),
        )
        # Reset to the default placeholder on UI-language change. A stale
        # error message would still be in the old language anyway.
        self._reset_target_placeholder()
        # Source / target combos: re-render every item from the
        # locale-sorted catalogue.  Display labels are now per-locale
        # via ``format_language_picker_label``, so a UI-language switch
        # has to rewrite each row in place — preserving selection by
        # the canonical English label held in ``itemData``.
        from src.constants.languages import (  # noqa: PLC0415
            format_language_picker_label as _fmt,
        )
        from src.constants.languages import (  # noqa: PLC0415
            iter_languages_sorted_for_ui as _iter_sorted,
        )

        for combo, has_auto in (
            (self.src_combo, True),
            (self.target_combo, False),
        ):
            if combo.count() == 0:
                continue
            saved = combo.currentData()
            combo.blockSignals(True)
            head_offset = 1 if has_auto else 0
            if has_auto:
                combo.setItemText(0, tr("common.lang_auto_detect"))
            for i, entry in enumerate(_iter_sorted()):
                _l, label, icon, native = entry
                # Update text + data + icon together — the new sort
                # order moves position [N] to a different language,
                # so the flag has to follow or it stays frozen at the
                # pre-switch position.
                combo.setItemText(i + head_offset, _fmt(label, native))
                combo.setItemData(i + head_offset, label)
                combo.setItemIcon(
                    i + head_offset, QIcon(f"{FLAGS_DIR}/{icon}.png"),
                )
            if saved is not None:
                idx = combo.findData(saved)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
            combo.blockSignals(False)
        self.swap_btn.setAccessibleName(tr("translate_text.swap_tooltip"))
        if self._worker is None:
            self.translate_btn.setText(tr("translate_text.btn_translate"))
        # Edit / Cancel buttons
        if self.target_text.isReadOnly():
            self.edit_btn.setText(tr("translate_text.btn_edit"))
        else:
            self.edit_btn.setText(tr("translate_text.btn_save"))
        self.cancel_edit_btn.setText(tr("btn.cancel"))
        # History header
        self._history_search.setPlaceholderText(
            tr("text_history.search_placeholder"),
        )
        self._history_view_btn.setText(tr("btn.view"))
        self._history_reuse_btn.setText(tr("btn.reuse"))
        self._history_delete_btn.setText(tr("btn.delete"))
        # Toggle button
        if self._header_stack.currentIndex() == 1:
            self.history_btn.setText(tr("translate_text.btn_back"))
        else:
            self.history_btn.setText(tr("translate_text.btn_history"))
        self._history_widget.apply_language()
        # TTS buttons (only update text if not actively playing)
        if self._tts_active_btn is None:
            self.tts_source_btn.setText(tr("translate_text.tts_play"))
            self.tts_target_btn.setText(tr("translate_text.tts_play"))
        # Refresh the model combo so the "No models configured" placeholder
        # picks up the new language.
        self._refresh_model_combo()


def create_translate_text_page(window: QMainWindow) -> QWidget:
    """Creates the Translate Text page."""
    return TranslateTextPage(window)
